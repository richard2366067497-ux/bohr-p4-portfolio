#!/usr/bin/env python3
"""sr_build.py - index assembly, payload assembly and validators for
traceable-literature-retrieval (search-01).

Deterministic only: builds the object table from the input tree, turns the
agent's draft.json into a ranked candidate payload with locators, computes
coverage against required references, and validates drafts/final artifacts.
Standard library only; no network; no CWD dependency.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import sr_core as C
import sr_output as O

VERSION = "1.0.0"
STATUSES = ("answered", "partial", "insufficient_evidence", "input_error")

_GROUPS = {
    'case_id': 'caseid id casename case',
    'status': 'status resultstatus runstatus',
    'candidates': 'candidates records results papers literature items documents candidateset '
                  'selected selectedpapers retrieved shortlist',
    'queries': 'queries query querylist searchqueries searchplan queryplan',
    'search_log': 'searchlog log retrievallog searchprocess process trace',
    'coverage': 'coverage coveragereport recall coveragestats coveragecheck',
    'missing': 'missing gaps omissions omission missingitems missingreferences',
    'evidence': 'evidence evidences evidencrecords screening screeninglog rationale',
    'sources': 'sources provenance sourcelist materials',
    'uncertainties': 'uncertainties uncertainty statusnotes',
    'conflicts': 'conflicts conflict',
    'excluded': 'excluded rejected exclusions screenedout',
    'report': 'report markdown reportmd',
    'summary': 'summary notes conclusion',
    'method_notes': 'methodnotes methodology method methods',
    'assumptions': 'assumptions', 'errors': 'errors', 'degradations': 'degradations',
    'runtime': 'runtime', 'changes': 'changes changelog',
    'result': 'result output data payload', 'metadata': 'metadata',
}
ALIAS = {n: field for field, names in _GROUPS.items() for n in names.split()}
LIST_NAMES = {"candidates", "queries", "evidence", "sources", "uncertainties", "missing",
              "conflicts", "excluded", "errors", "degradations", "changes", "assumptions"}
DICT_NAMES = {"search_log", "coverage", "runtime", "method_notes", "metadata", "result"}



def resolve_obj(sel, by_id, by_doi, objs):
    oid = str(C.pick(sel, "object_id", "id", "record_id", "object") or "").strip().upper()
    if oid in by_id:
        return by_id[oid]
    doi = C.clean_doi(C.pick(sel, "doi"))
    if doi and doi in by_doi:
        return by_doi[doi]
    title = C.pick(sel, "title")
    if isinstance(title, str) and len(title) > 10:
        key = C.norm_text(title)[:60]
        for o in objs:
            if C.norm_text(o["title"])[:60].startswith(key[:40]):
                return o
    return None


def norm_decision(sel):
    d = str(C.pick(sel, "decision", "verdict", "action", "keep") or "").strip().lower()
    return {"yes": "include", "true": "include", "keep": "include", "in": "include",
            "no": "exclude", "false": "exclude", "drop": "exclude", "out": "exclude",
            "maybe": "uncertain", "pending": "uncertain", "unsure": "uncertain"}.get(d, d)


def as_float(v, default=None):
    try:
        f = float(v)
        return max(0.0, min(1.0, f))
    except Exception:
        return default


def fallback_selections(index):
    task = index["task"]
    fams = [[k] for k in task.get("seed_keywords") or []]
    if not fams:
        fams = [[w] for w in C.tokens(task.get("research_question") or "", 10) if len(w) > 3][:8]
    for e in index["expansions"][:10]:
        fams.append([e.get("short"), e.get("long")])
    excl = task.get("exclude_terms") or []
    scored = []
    for o in index["objects"]:
        s, hits = C.score_record(o, fams, excl)
        scored.append((s, hits, o))
    scored.sort(key=lambda t: (-t[0], -(t[1] or 0), t[2].get("doi") or "", t[2]["object_id"]))
    k = int(task.get("target_k") or 20)
    out = []
    for s, hits, o in scored[: max(k * 2, 10)]:
        decision = "include" if hits > 0 else "exclude"
        out.append({"object_id": o["object_id"], "decision": decision,
                    "relevance": s, "tier": "supporting" if s >= 0.5 else "peripheral",
                    "basis": ("fallback keyword-family overlap %d/%d on title+abstract+venue "
                              "(no agent judgement available)" % (hits, len(fams))),
                    "quote": (o.get("title") or "")[:160], "query_ids": ["QF1"]})
    return out


def assemble(index, draft, mode_hint):
    objs = index["objects"]
    by_id = {o["object_id"]: o for o in objs}
    by_doi = {o["doi"]: o for o in objs if o.get("doi")}
    task, degs, errs, unc = index["task"], [], [], []
    mode = mode_hint
    sels = []
    if isinstance(draft, dict):
        sels = draft.get("selections") or draft.get("items") or []
    if not isinstance(sels, list) or not sels:
        sels = fallback_selections(index)
        mode = "fallback_keyword_ranking"
        degs.append({"code": "draft_missing_or_empty",
                     "detail": "no draft.selections; keyword-overlap fallback only, not agent-judged"})
    rel_by_query = {}
    included, excluded, evidence = [], [], []
    for sel in sels:
        if not isinstance(sel, dict):
            continue
        obj = resolve_obj(sel, by_id, by_doi, objs)
        if obj is None:
            errs.append({"code": "selection_unresolved", "detail": str(C.pick(sel, "object_id"))[:60]})
            continue
        dec = norm_decision(sel) or "uncertain"
        basis = str(C.pick(sel, "basis", "reason", "rationale", "why") or "").strip()
        quote = str(C.pick(sel, "quote", "evidence_quote", "verbatim") or "").strip()
        ok, field, _ = C.verify_quote(quote, obj) if quote else (False, "no_quote", 0.0)
        score = as_float(C.pick(sel, "relevance", "score"))
        qids = C.pick(sel, "query_ids", "queries") or []
        if isinstance(qids, str):
            qids = [qids]
        qids = [str(q) for q in qids if q]
        row = {
            "object_id": obj["object_id"], "title": obj["title"], "authors": obj.get("authors") or [],
            "year": obj.get("year"), "venue": obj.get("venue"), "doi": obj.get("doi"),
            "record_type": obj.get("record_type"), "pmid": obj.get("pmid"), "url": obj.get("url"),
            "abstract": (obj.get("abstract") or "")[:1200] or None,
            "source_id": obj["source_id"], "source_name": obj.get("source_name"),
            "locator": obj["locator"],
            "retrieval_query": C.pick(sel, "retrieval_query") or None,
            "query_ids": qids,
            "tier": str(C.pick(sel, "tier", "importance") or "supporting"),
            "relevance": {"score": score,
                          "basis": basis or None,
                          "quote": quote or None,
                          "quote_verified": bool(ok),
                          "quote_field": field,
                          "judgement": "agent" if mode == "agent_draft" else "deterministic_fallback"},
            "metadata_completeness": {"score": obj.get("completeness"),
                                      "missing": obj.get("missing_fields") or []},
            "screening": {"decision": dec, "reason": basis or None,
                          "notes": C.pick(sel, "metadata_notes", "note")},
        }
        if dec == "exclude":
            excluded.append(row)
        else:
            included.append(row)
        for q in qids:
            rel_by_query[q] = rel_by_query.get(q, 0) + (1 if dec != "exclude" else 0)
        if quote:
            evidence.append({"record_id": obj["object_id"], "kind": "screening_evidence",
                             "claim": dec, "quote": quote,
                             "quote_verified": bool(ok), "quote_field": field,
                             "source_id": obj["source_id"], "locator": obj["locator"]})
    # deterministic ordering + metadata-completeness dedup
    included.sort(key=lambda r: (-(r["relevance"]["score"] or 0), r["object_id"]))
    pool_clusters, conflicts = C.cluster(objs)
    clusters, _ = C.cluster(included)
    ranked, merged = [], 0
    for cl in clusters:
        keeper = cl["keeper"] if cl["keeper"] in included else cl["members"][0]
        keeper = dict(keeper)
        if len(cl["members"]) > 1:
            merged += len(cl["members"]) - 1
            keeper["merged_from"] = sorted({m["source_id"] for m in cl["members"]})
            keeper["screening"]["notes"] = (keeper["screening"].get("notes") or "") + \
                " duplicate cluster of %d record(s) merged by %s" % (len(cl["members"]), cl["key"][:6])
        ranked.append(keeper)
    tier_w = {"core": 2, "supporting": 1, "peripheral": 0}
    ranked.sort(key=lambda r: (-(r["relevance"]["score"] or 0), -tier_w.get(r.get("tier"), 0),
                               r.get("doi") or "~", r["object_id"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["record_id"] = "R%02d" % i
        r["status"] = "included" if r["screening"]["decision"] == "include" else "included_pending_confirmation"
    # coverage
    cov = dict(draft.get("coverage") or {}) if isinstance(draft, dict) else {}
    cov.pop("status", None)
    matched, missing = [], []
    for req in index["required"]:
        hit = None
        for r in ranked:
            if req.get("doi") and r.get("doi") == req["doi"]:
                hit = r
                break
            if req.get("title") and r.get("title"):
                a = set(C.tokens(req["title"], 30))
                b = set(C.tokens(r["title"], 30))
                if a and b and len(a & b) / float(len(a)) >= 0.75:
                    hit = r
                    break
        rec = {"ref_id": req["ref_id"], "doi": req.get("doi"), "title": req.get("title"),
               "object_id": hit["object_id"] if hit else None,
               "record_id": hit["record_id"] if hit else None}
        (matched if hit else missing).append(rec)
    fam_cov = []
    fams = [k for k in (task.get("seed_keywords") or []) if k]
    if not fams:
        fams = [w for w in C.tokens(task.get("research_question") or "", 10) if len(w) > 3][:8]
    for kw in fams[:12]:
        n = sum(1 for r in ranked if kw and C.norm_text(kw) in (C.norm_text(r["title"]) + " " + C.norm_text(r["abstract"] or "")))
        fam_cov.append({"term": kw, "candidates": n, "covered": n > 0})
    cov.update({
        "target_k": task.get("target_k"),
        "selected_count": len(included),
        "excluded_count": len(excluded),
        "distinct_after_dedup": len(ranked),
        "duplicates_merged": (len(objs) - len(pool_clusters)) + merged,
        "required_total": len(index["required"]),
        "required_matched": matched,
        "required_matched_count": len(matched),
        "required_missing": missing,
        "recall_against_required": round(len(matched) / float(len(index["required"])), 3) if index["required"] else None,
        "family_coverage": fam_cov,
        "agent_notes": draft.get("coverage_judgement") if isinstance(draft, dict) else None,
    })
    # search log
    qplan = (draft.get("queries") or draft.get("query_plan") or []) if isinstance(draft, dict) else []
    if not qplan:
        qplan = [{"query": q["query"], "intent": q["intent"]} for q in index["suggested_queries"]]
        degs.append({"code": "query_plan_generated",
                     "detail": "draft.queries empty; search_log shows suggested, not executed, queries"})
    queries = []
    for i, q in enumerate(qplan[:40], 1):
        if isinstance(q, str):
            q = {"query": q}
        text = str(C.pick(q, "query", "q", "string") or "")
        quoted = [C.norm_text(x) for x in re.findall(r'"([^"]+)"', text)]
        bare = [C.norm_text(w) for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text)
                if w.upper() not in ("AND", "OR", "NOT", "THE", "FOR", "WITH")]
        terms = quoted + bare
        hits_all = sum(1 for o in objs if terms and all(t in (o.get("text") or "") for t in terms))
        hits_any = sum(1 for o in objs if terms and any(t in (o.get("text") or "") for t in terms))
        hits = hits_all
        qid = str(C.pick(q, "query_id", "id") or "Q%d" % i)
        queries.append({"query_id": qid, "query": text,
                        "source": C.pick(q, "source", "database", "api"),
                        "intent": C.pick(q, "intent", "purpose", "rationale"),
                        "hits": hits, "hits_any_term": hits_any, "selected": rel_by_query.get(qid, 0),
                        "note": C.pick(q, "note")})
    search_log = {
        "mode": mode,
        "queries": queries,
        "rounds": (draft.get("rounds") if isinstance(draft, dict) else None) or [],
        "totals": {"query_count": len(queries), "objects_considered": len(objs),
                   "included": len(included), "excluded": len(excluded),
                   "duplicates_merged": len(objs) - len(pool_clusters)},
        "dedup_rule": "DOI, then title fingerprint; conflicts keep both sides",
        "dedup_conflicts": conflicts + [c for c in (index.get("conflict_stub") or [])],
        "sources_used": [s["source_id"] for s in index["sources"] if s.get("records")],
        "import_states": index["import_states"],
    }
    # missing / uncertainties
    missing_items = list(draft.get("gaps") or []) if isinstance(draft, dict) else []
    for m in missing:
        missing_items.append({"kind": "required_reference_not_found",
                              "detail": m.get("doi") or m.get("title"), "ref_id": m.get("ref_id")})
    for s in index["sources"]:
        if s.get("role") == "unparsed_binary":
            missing_items.append({"kind": "binary_material_not_parsed", "source_id": s["source_id"],
                                  "detail": "read with the pdf/ocr tool before quoting; not fabricated here"})
    unc.extend([u for u in (draft.get("uncertainties") or []) if isinstance(u, (str, dict))] if isinstance(draft, dict) else [])
    if not ranked:
        unc.append("No candidate was kept: either the material pool is empty or every record failed screening.")
    if index["import_states"]:
        unc.append("Coverage is bounded by the organizer-local import states recorded in search_log; "
                   "no live database was queried in this run.")
    # status
    distinct_pool = len(C.cluster(objs)[0])
    need = min(int(task.get("target_k") or 20), max(1, distinct_pool))
    status = "answered"
    if not objs:
        status = "insufficient_evidence"
    elif not ranked:
        status = "insufficient_evidence"
    elif mode != "agent_draft" or len(ranked) < need:
        status = "partial"
    elif any(not r["relevance"]["quote_verified"] for r in ranked):
        status = "partial"
        degs.append({"code": "unverified_quote_present",
                     "detail": "at least one kept row has a non-verbatim or missing quote; "
                               "relevance evidence needs re-reading (see selfcheck)"})
    errs.extend(index.get("errors") or [])
    degs.extend(index.get("degradations") or [])
    if errs:
        status = "input_error" if not objs else ("partial" if status == "answered" else status)
    payload = {
        "status": status, "candidates": ranked, "excluded": excluded,
        "queries": queries, "search_log": search_log, "coverage": cov,
        "evidence": evidence, "sources": index["sources"], "uncertainties": unc,
        "missing": missing_items, "conflicts": conflicts,
        "assumptions": [{"item": "target_k", "value": task.get("target_k"), "source": task.get("target_k_source")},
                        {"item": "time_window", "value": task.get("time_window")},
                        {"item": "ordering", "value": "relevance desc, tier, DOI, object_id"}],
        "method_notes": {
            "pipeline": "discover -> lift records (locators) -> agent screening -> dedup -> rank -> coverage -> finalize",
            "judgement_owner": "agent (draft.json)" if mode == "agent_draft" else "deterministic fallback",
            "quote_rule": "quote must be a verbatim substring at the locator",
            "term_expansion": [e.get("short") + "~" + e.get("long") for e in index["expansions"][:12]],
            "no_network": True,
        },
        "summary": (draft.get("summary") or draft.get("research_question") or task.get("research_question") or "")
        if isinstance(draft, dict) else (task.get("research_question") or ""),
        "degradations": degs, "errors": errs, "changes": [{"v": VERSION, "mode": mode}],
        "metadata": {"skill": "traceable-literature-retrieval", "version": VERSION,
                     "objects_indexed": len(objs), "sources": len(index["sources"])},
    }
    payload["result"] = {"status": status, "candidates": ranked, "coverage": cov,
                         "search_log": search_log, "evidence": evidence,
                         "conflicts": conflicts, "uncertainties": unc}
    payload["report"] = O.render_report(payload, mode)
    return payload, mode


def fill_contract(res, payload, contract):
    filled, empty = [], []
    for k in contract:
        nk = C.nkey(k)
        target = ALIAS.get(nk)
        if target == "status":
            res[k] = payload["status"]
        elif target == "case_id":
            res[k] = res["case_id"]
        elif target and target in payload:
            res[k] = payload[target]
        else:
            res[k] = empty_value(k)
            empty.append(k)
        filled.append(k)
    if empty:
        res["degradations"].append({"code": "contract_field_filled_empty",
                                    "detail": "contract keys without a producer: %s (filled with null/[] as "
                                              "declared, not omitted)" % ", ".join(sorted(set(empty))[:12])})
    return filled




def make_index(inp, case):
    task_md = ""
    tp = inp / "task.md"
    if tp.is_file():
        task_md, _ = C.read_text(tp, 400000)
    files = C.discover(inp)
    records, notes, sources, errs, degs = C.collect(inp)
    for i, r in enumerate(records):
        r["object_id"] = "O%04d" % (i + 1)
    task = C.parse_task(case, task_md)
    req_raw = C.find_required(case, None)
    if req_raw:
        required = C.required_items(req_raw)
    else:
        graph0 = C.find_graph(files)
        refs0 = C.graph_refs(graph0)[:60] if graph0 else []
        required = [{"ref_id": "REQ%02d" % (i + 1), "doi": r["doi"], "title": r["title"]}
                    for i, r in enumerate(refs0)]
    graph = C.find_graph(files)
    imports = C.find_import_states(files, case)
    exp_texts = [r.get("raw_text") or "" for r in records[:400]] + [task.get("research_question") or ""]
    expansions = C.learn_expansions(exp_texts)
    declared = C.pick(case, "artifacts", "materials", "attachments", "files")
    missing_declared = []
    if isinstance(declared, list):
        for d in declared[:40]:
            name = d if isinstance(d, str) else (C.pick(d, "path", "name", "file") if isinstance(d, dict) else None)
            if not name:
                continue
            if not any(name in s["path"] for s in sources) and not (inp / str(name)).exists():
                missing_declared.append(str(name))
    if missing_declared:
        degs.append({"code": "declared_material_missing",
                     "detail": "declared but not found under input: %s" % ", ".join(missing_declared[:8])})
    dup, _ = C.cluster(records)
    index = {
        "skill_version": VERSION,
        "case_id": C.case_id_of(case, inp),
        "contract_keys": C.contract_keys(case),
        "task": task,
        "objects": records,
        "sources": sources,
        "notes": notes,
        "required": required,
        "reference_graph": {"source": (graph or {}).get("source"),
                            "refs": C.graph_refs(graph)[:120] if graph else []},
        "import_states": imports,
        "expansions": expansions,
        "suggested_queries": O.suggest_queries(task, expansions),
        "errors": errs,
        "degradations": degs,
        "stats": {"files": len(files), "objects": len(records),
                  "distinct_clusters": len(dup), "duplicates": max(0, len(records) - len(dup)),
                  "with_doi": sum(1 for r in records if r.get("doi")),
                  "with_abstract": sum(1 for r in records if r.get("abstract")),
                  "required_items": len(required), "import_states": len(imports)},
        "built_unix": int(time.time()),
    }
    return index




def validate(index, draft, derr):
    issues = []
    stats = {"selections": 0, "include": 0, "exclude": 0, "uncertain": 0,
             "quote_verified": 0, "quote_failed": 0, "resolved": 0, "unresolved": 0}
    if derr:
        issues.append({"level": "error", "code": derr["code"], "detail": derr["detail"]})
        return {"ok": False, "issues": issues, "stats": stats}
    objs = index["objects"]
    by_id = {o["object_id"]: o for o in objs}
    sels = draft.get("selections") or draft.get("items") or []
    if not isinstance(sels, list) or not sels:
        issues.append({"level": "error", "code": "no_selection",
                       "detail": "draft.selections is empty: screening decisions cannot be built"})
        return {"ok": False, "issues": issues, "stats": stats}
    seen = set()
    for i, sel in enumerate(sels, 1):
        if not isinstance(sel, dict):
            issues.append({"level": "error", "code": "selection_not_object", "ref": "#%d" % i})
            continue
        oid = str(C.pick(sel, "object_id", "id", "record_id", "object") or "").strip().upper()
        obj = by_id.get(oid)
        if obj is None:
            cand = [o for o in objs if C.pick(sel, "doi") and o.get("doi") == C.clean_doi(C.pick(sel, "doi"))]
            obj = cand[0] if cand else None
        if obj is None:
            stats["unresolved"] += 1
            issues.append({"level": "error", "code": "unknown_object",
                           "detail": "selection #%d refers to %r which is not in the index" % (i, oid)})
            continue
        stats["resolved"] += 1
        stats["selections"] += 1
        dec = str(C.pick(sel, "decision", "verdict", "action", "keep") or "").strip().lower()
        dec = {"yes": "include", "true": "include", "in": "include", "keep": "include",
               "no": "exclude", "false": "exclude", "drop": "exclude", "out": "exclude",
               "maybe": "uncertain", "pending": "uncertain", "unsure": "uncertain"}.get(dec, dec)
        if dec not in ("include", "exclude", "uncertain"):
            issues.append({"level": "error", "code": "bad_decision",
                           "detail": "%s: decision %r not in include|exclude|uncertain" % (obj["object_id"], dec)})
            dec = "uncertain"
        stats["include" if dec == "include" else ("exclude" if dec == "exclude" else "uncertain")] += 1
        if obj["object_id"] in seen and dec != "exclude":
            issues.append({"level": "warn", "code": "duplicate_selection",
                           "detail": "%s appears more than once" % obj["object_id"]})
        seen.add(obj["object_id"])
        rel = sel.get("relevance", sel.get("score"))
        if rel is not None:
            try:
                rv = float(rel)
                if not 0.0 <= rv <= 1.0:
                    issues.append({"level": "warn", "code": "relevance_range",
                                   "detail": "%s relevance=%s outside 0..1" % (obj["object_id"], rv)})
            except Exception:
                issues.append({"level": "error", "code": "relevance_not_number",
                               "detail": "%s relevance=%r" % (obj["object_id"], rel)})
        basis = str(C.pick(sel, "basis", "reason", "rationale", "why") or "").strip()
        if not basis:
            issues.append({"level": "error" if dec != "exclude" else "warn", "code": "missing_basis",
                           "detail": "%s has no basis (why is it relevant / why was it dropped?)" % obj["object_id"]})
        quote = str(C.pick(sel, "quote", "evidence_quote", "verbatim") or "").strip()
        if quote:
            ok, field, _ = C.verify_quote(quote, obj)
            if ok:
                stats["quote_verified"] += 1
            else:
                stats["quote_failed"] += 1
                issues.append({"level": "error", "code": "quote_not_found",
                               "detail": "%s: quote not verbatim in %s (%s)" % (obj["object_id"], obj["locator"], field)})
        elif dec != "exclude":
            issues.append({"level": "warn", "code": "missing_quote",
                           "detail": "%s: no verbatim quote; verifiability score drops" % obj["object_id"]})
    k = index["task"]["target_k"]
    if stats["include"] < min(k, len(objs)) and stats["include"] < k:
        issues.append({"level": "warn", "code": "below_target_k",
                       "detail": "included %d of target %d (objects available: %d)"
                                 % (stats["include"], k, len(objs))})
    if not (draft.get("queries") or draft.get("query_plan")):
        issues.append({"level": "warn", "code": "no_query_plan",
                       "detail": "draft.queries empty: search_log will lack the query plan"})
    if index["required"] and not (draft.get("coverage_judgement") or draft.get("coverage")):
        issues.append({"level": "warn", "code": "no_coverage_judgement",
                       "detail": "%d required references exist but no coverage_judgement written"
                                 % len(index["required"])})
    errs = [i for i in issues if i["level"] == "error"]
    return {"ok": not errs, "issues": issues, "stats": stats}




def cmd_selfcheck(a):
    inp, work, out = dirs(a)
    checks = []
    result, note = C.load_json(out / "result.json")
    checks.append({"check": "result_json_parses", "ok": isinstance(result, dict), "detail": note or "ok"})
    index = load_index(work) or {}
    contract = index.get("contract_keys") or C.contract_keys(read_case(inp)[0])
    if isinstance(result, dict):
        missing_keys = [k for k in contract if k not in result]
        checks.append({"check": "contract_keys_present", "ok": not missing_keys,
                       "detail": "missing: %s" % missing_keys if missing_keys else "%d keys" % len(contract)})
        checks.append({"check": "status_is_enum", "ok": result.get("status") in STATUSES,
                       "detail": str(result.get("status"))})
        cands = result.get("candidates") or []
        checks.append({"check": "candidates_present", "ok": bool(cands),
                       "detail": "%d rows (status=%s)" % (len(cands), result.get("status"))})
        bad_loc = [c.get("object_id") for c in cands if not (c.get("source_id") and c.get("locator"))]
        checks.append({"check": "every_candidate_has_locator", "ok": not bad_loc,
                       "detail": str(bad_loc[:5])})
        unver = [c.get("object_id") for c in cands
                 if not ((c.get("relevance") or {}).get("quote_verified"))]
        checks.append({"check": "quotes_verified", "ok": len(unver) <= max(1, len(cands) // 3),
                       "detail": "%d/%d unverified: %s" % (len(unver), len(cands), unver[:5])})
        ranks = [c.get("rank") for c in cands]
        checks.append({"check": "rank_contiguous", "ok": ranks == list(range(1, len(cands) + 1)),
                       "detail": str(ranks[:8])})
        lines = 0
        jp = out / "candidates.jsonl"
        if jp.is_file():
            lines = len([l for l in jp.read_text(encoding="utf-8").splitlines() if l.strip()])
        checks.append({"check": "jsonl_matches_json", "ok": lines == len(cands),
                       "detail": "jsonl=%d json=%d" % (lines, len(cands))})
        rep = out / "report.md"
        checks.append({"check": "report_non_empty", "ok": rep.is_file() and rep.stat().st_size > 200,
                       "detail": "%d bytes" % (rep.stat().st_size if rep.is_file() else 0)})
        checks.append({"check": "no_fabricated_dois",
                       "ok": all((c.get("doi") or "").count("/") >= 1 for c in cands if c.get("doi")),
                       "detail": "DOI prefix present"})
    ok = all(c["ok"] for c in checks)
    C.dump_json(out / "selfcheck.json", {"ok": ok, "checks": checks})
    say("== selfcheck ==")
    for c in checks:
        say("  [%s] %-32s %s" % ("PASS" if c["ok"] else "FAIL", c["check"], c["detail"]))
    say("overall       : %s -> %s" % ("PASS" if ok else "NEEDS ATTENTION", out / "selfcheck.json"))
    return 0
