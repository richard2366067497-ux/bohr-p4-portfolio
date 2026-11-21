# -*- coding: utf-8 -*-
"""report.py - draft verification (verbatim quotes, locators), candidate fallback, assembly."""
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core    # noqa: E402
import rules   # noqa: E402
from rules import search  # noqa: E402

VERSION = "1.1.0"
T0 = time.time()

# ---------------------------------------------------------------- quote location
QSTAT = ("answered", "partially_answered", "not_found", "blocked_by_filter")
STATUS_ALIAS = {"ok": "answered", "answer": "answered", "partial": "partially_answered",
                "blocked": "blocked_by_filter", "empty": "not_found", "none": "not_found",
                "insufficient": "partially_answered"}

def _norm_map(t):
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(t):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
            continue
        prev_space = False
        if ch in "‘’“”":
            ch = '"'
        elif ch in "‐‑‒–—":
            ch = "-"
        out.append(ch)
        idx.append(i)
    return "".join(out), idx

def _hint(doc, quote):
    q = core.norm_ws(quote)[:200]
    grams = {q[i:i + 6] for i in range(max(0, len(q) - 5))} or {q[:6]}
    best, score = None, 0
    for p in doc.get("paragraphs") or []:
        n = core.norm_ws(p.get("text"))[:1500]
        sc = sum(1 for g in grams if g and g in n)
        if sc > score:
            best, score = p, sc
    if not best:
        return {"paragraph_id": "", "section": "", "snippet": "该文档内无相似段落", "overlap": 0}
    return {"paragraph_id": best.get("pid"), "section": best.get("section"),
            "page_physical": best.get("page_physical"), "page_printed": best.get("page_printed"),
            "snippet": (best.get("text") or "")[:160], "overlap": score}

def locate(doc, quote):
    raw = str(quote or "")
    if len(core.norm_ws(raw)) < 4:
        return {"ok": False, "reason": "too_short"}
    for p in doc.get("paragraphs") or []:
        pos = (p.get("text") or "").find(raw)
        if pos >= 0:
            return _hit(p, pos, "exact", doc)
    nq = core.norm_ws(raw)
    for p in doc.get("paragraphs") or []:
        n, idx = _norm_map(p.get("text") or "")
        pos = n.find(nq)
        if pos >= 0:
            return _hit(p, idx[pos], "whitespace_normalised", doc)
    bysec = {}
    for p in doc.get("paragraphs") or []:
        bysec.setdefault(p.get("section_id"), []).append(p)
    for _sid, ps in bysec.items():
        joined = "\n".join(x.get("text") or "" for x in ps)
        n, _idx = _norm_map(joined)
        if nq in n:
            return _hit(ps[0], 0, "spanning_paragraphs", doc)
    return {"ok": False, "reason": "not_found", "suggestion": _hint(doc, raw)}

def _hit(p, pos, match, doc):
    pth = doc.get("path_input") or doc.get("path")
    pg = p.get("page_physical")
    return {"ok": True, "match": match, "doc_id": doc.get("doc_id"), "path": pth,
            "version": doc.get("version"), "paragraph_id": p.get("pid"),
            "section_id": p.get("section_id"), "section": p.get("section"),
            "page_physical": pg, "page_printed": p.get("page_printed"),
            "source": p.get("source"), "char_start": pos,
            "locator": "%s#p%s/%s@%s" % (pth, pg if pg is not None else "no-page",
                                         p.get("pid"), pos if pos is not None else "?")}

# ---------------------------------------------------------------- verification
def verify_payload(payload, index):
    contract = core.contract_keys(index.get("_contract") or {})
    chat = payload.get("contract_keys") or []
    keys = [k for k in (contract or chat) if k not in ("errors", "degradations", "changes")]
    entries = payload.get("queries") or []
    bad_q, bad_page, bad_quote, banned = [], [], [], []
    banned_ids = {x.get("doc_id") for x in (index.get("excluded_evidence") or [])}
    for en in entries:
        if en.get("status") not in QSTAT:
            bad_q.append(en.get("query_id"))
        for ev in en.get("evidence") or []:
            doc = core.doc_by_path(index, ev.get("path"))
            if doc is None:
                bad_quote.append({"query_id": en.get("query_id"), "path": ev.get("path"),
                                  "reason": "doc_not_in_index"})
                continue
            if doc.get("doc_id") in banned_ids:
                banned.append({"query_id": en.get("query_id"), "doc_id": doc.get("doc_id")})
            loc = locate(doc, ev.get("quote"))
            if not loc.get("ok"):
                bad_quote.append({"query_id": en.get("query_id"), "path": ev.get("path"),
                                  "reason": loc.get("reason")})
            elif str(loc.get("page_physical")) != str(ev.get("page_physical")) or \
                    str(loc.get("page_printed")) != str(ev.get("page_printed")):
                bad_page.append({"query_id": en.get("query_id"), "paragraph_id": ev.get("paragraph_id"),
                                 "reported": [ev.get("page_physical"), ev.get("page_printed")],
                                 "index": [loc.get("page_physical"), loc.get("page_printed")]})
    nf_scope = [en.get("query_id") for en in entries
                if en.get("status") in ("not_found", "blocked_by_filter")
                and not (en.get("search_scope") or "").strip()]
    ev_total = sum(len(en.get("evidence") or []) for en in entries)
    echo = payload.get("output_contract") if isinstance(payload.get("output_contract"), dict) else {}
    checks = [
        ("case_id_present", bool(payload.get("case_id")) or payload.get("status") == "failed"),
        ("contract_keys_present", (all(k in echo for k in keys) and all(k in payload for k in keys))
         if keys else True),
        ("queries_covered", len(entries) == (payload.get("coverage") or {}).get("queries_expected", len(entries))),
        ("status_enum_valid", not bad_q),
        ("quotes_verbatim", not bad_quote),
        ("pages_consistent", not bad_page),
        ("no_banned_evidence", not banned),
        ("not_found_has_scope", not nf_scope),
        ("coverage_present", bool(payload.get("coverage"))),
        ("dedupe_ledger_present", "excluded_evidence" in payload),
        ("filters_ledger_present", "filters" in payload),
        ("runtime_budget_present", bool((payload.get("runtime") or {}).get("budget"))),
    ]
    fails = [n for n, v in checks if not v]
    return {"ok": not fails, "checks": [{"check": n, "ok": bool(v)} for n, v in checks],
            "fails": fails, "queries": len(entries), "evidence": ev_total,
            "unmatched_quotes": bad_quote[:5], "page_mismatch": bad_page[:5],
            "banned_evidence": banned[:5], "missing_scope": nf_scope[:5],
            "quote_hit_rate": round(ev_total / float(max(1, ev_total + len(bad_quote))), 3) if ev_total else 0.0,
            "verified_at": core.now()}
EV_KEYS = ("evidence", "citations", "refs", "locators")

# ---------------------------------------------------------------- draft I/O
def load_draft(args, work):
    path = Path(args.draft) if getattr(args, "draft", None) else Path(work) / "draft.json"
    if not path.is_file():
        return None, path, "工作稿缺失"
    draft = core.jload(path)
    if not isinstance(draft, dict):
        return None, path, "工作稿不是合法 JSON 对象"
    return draft, path, None

def draft_rows(draft):
    raw = draft.get("queries") or draft.get("answers") or draft.get("results") or []
    return raw if isinstance(raw, list) else []

def row_evidence(row):
    ev = []
    for k in EV_KEYS:
        v = row.get(k)
        if isinstance(v, list):
            ev.extend([x for x in v if isinstance(x, dict)])
    return ev

def match_row(queries, rows):
    out, used = [], set()
    byid = {}
    for i, r in enumerate(rows):
        for k in ("query_id", "qid", "id", "question_id"):
            if r.get(k) is not None:
                byid[str(r[k]).strip()] = i
    for idx, q in enumerate(queries):
        hit = byid.get(str(q["query_id"]).strip())
        if hit is None:
            qn = core.squash(q["question"])
            for i, r in enumerate(rows):
                if core.squash(r.get("question") or r.get("query") or "") == qn:
                    hit = i
                    break
        if hit is None and len(rows) == len(queries) and idx not in used:
            hit = idx
        out.append((q, rows[hit] if hit is not None and hit < len(rows) else None))
        if hit is not None:
            used.add(hit)
    return out

def global_conds(case):
    return rules.parse_filters(rules.lk(case, ("filters", "filter", "constraints", "conditions",
                                               "过滤", "过滤条件")))

def query_conds(case, q):
    conds = global_conds(case)
    for c in rules.parse_filters(q.get("filters_raw")):
        conds = [x for x in conds if x["key"] != c["key"]] + [c]
    return conds

def extra_syn(case):
    raw = rules.lk(case, ("synonyms", "glossary", "aliases", "terminology", "同义词"))
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = [str(x) for x in (v if isinstance(v, list) else [v])]
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                k = item.get("term") or item.get("canonical")
                vs = item.get("synonyms") or item.get("aliases") or item.get("variants")
                if k and vs:
                    out[str(k)] = [str(x) for x in (vs if isinstance(vs, list) else [vs])]
    return out

def verify_row(q, row, index, conds, fill_scope=False):
    docs = index.get("docs") or []
    banned = {x.get("doc_id") for x in (index.get("excluded_evidence") or [])}
    qid = q["query_id"]
    entry = {"query_id": qid, "question": q["question"], "answer": "",
             "status": "not_found", "filters_applied": [rules.filter_text(c) for c in conds],
             "evidence": [], "rejected_evidence": [], "excluded_docs": [],
             "search_scope": "", "notes": "", "locators": []}

    def rej(reason, detail, **kw):
        d = {"reason": reason, "detail": detail}
        d.update(kw)
        entry["rejected_evidence"].append(d)

    def chg(what, change):
        core.STATE["changes"].append({"item": f"{qid}:{what}", "change": change})

    if not isinstance(row, dict):
        entry["search_scope"] = "工作稿未提供该问的条目"
        return entry
    st = str(row.get("status") or "").strip()
    st = STATUS_ALIAS.get(st, st)
    entry["answer"] = str(row.get("answer") or row.get("conclusion") or "").strip()
    entry["status"] = st if st in QSTAT else "not_found"
    entry["search_scope"] = str(row.get("search_scope") or row.get("scope") or "").strip()
    entry["notes"] = str(row.get("notes") or "").strip()
    allowed, blocked, _ok = rules.apply_all(conds, docs)
    allowed_ids = {d.get("doc_id") for d in allowed}
    seen = set()
    for ev in row_evidence(row):
        path = ev.get("path") or ev.get("file") or ev.get("doc") or ""
        quote = ev.get("quote") or ev.get("text") or ev.get("snippet") or ""
        doc = core.doc_by_path(index, path)
        if doc is None:
            rej("document_not_found", "该路径不在索引中", path=str(path))
            continue
        if (quote, doc.get("doc_id")) in seen:
            continue
        seen.add((quote, doc.get("doc_id")))
        if doc.get("status") != "ok":
            rej("document_" + str(doc.get("status")), "该文档未能解析，不可引用", path=doc.get("path"))
            continue
        if doc.get("doc_id") in banned and not ev.get("allow_non_representative"):
            rej("non_representative_document", "副本或旧版本不得作为独立证据",
                path=doc.get("path"), doc_id=doc.get("doc_id"))
            entry["excluded_docs"].append(doc.get("doc_id"))
            continue
        if conds and doc.get("doc_id") not in allowed_ids:
            f = blocked.get(doc.get("doc_id")) or []
            rej("violates_filters", "; ".join(x["filter"] for x in f) or "不满足过滤条件",
                path=doc.get("path"), doc_id=doc.get("doc_id"))
            continue
        loc = locate(doc, quote)
        if not loc.get("ok"):
            rej("quote_" + str(loc.get("reason")), "引文无法逐字定位", path=doc.get("path"),
                quote=quote[:160], suggestion=loc.get("suggestion"))
            continue
        if loc.get("match") == "spanning_paragraphs":
            chg("quote", "quote 跨段命中，已归到最前段落")
        ev_out = {"path": loc["path"], "doc_id": loc["doc_id"], "version": loc["version"],
                  "section_id": loc.get("section_id"), "section": loc.get("section"),
                  "page_physical": loc.get("page_physical"), "page_printed": loc.get("page_printed"),
                  "paragraph_id": loc.get("paragraph_id"), "char_start": loc.get("char_start"),
                  "source": loc.get("source"), "quote": quote,
                  "quote_verified": True, "match": loc.get("match"), "locator": loc["locator"]}
        for k in ("page_printed", "page_physical"):
            v = ev.get(k)
            if v not in (None, "") and str(v) != str(ev_out[k]):
                chg(k, f"draft {v} -> index {ev_out[k]}")
        if ev.get("paragraph_id") and str(ev["paragraph_id"]) != str(ev_out["paragraph_id"]):
            chg("paragraph_id", f"draft {ev['paragraph_id']} -> index {ev_out['paragraph_id']}")
        if ev.get("section") and str(ev.get("section")) != str(ev_out.get("section")):
            ev_out["section_reported"] = str(ev.get("section"))
        entry["evidence"].append(ev_out)
        entry["locators"].append(ev_out["locator"])
    if entry["status"] in ("answered", "partially_answered") and not entry["evidence"]:
        entry["status"] = "partially_answered"
        core.degrade(f"{qid}:evidence", "no_verified_evidence", "声称作答但无可核验引文，已降级")
    if entry["status"] == "not_found" and entry["evidence"]:
        entry["status"] = "partially_answered"
        chg("status", "not_found 却有核验通过的证据 → partially_answered")
    if entry["status"] == "blocked_by_filter" and not conds:
        chg("status", "blocked_by_filter 但无过滤条件，保留并标注")
    entry["scope_provided"] = bool(entry["search_scope"].strip())
    if not entry["scope_provided"] and entry["status"] in ("not_found", "blocked_by_filter"):
        entry["search_scope_unfilled"] = True
        if fill_scope:
            entry["search_scope"] = ("未提供检索范围（工作稿缺 search_scope）；"
                                     "已对 %d/%d 个可检索文档执行过滤与检索"
                                     % (len(allowed), len(docs)))
            core.degrade(f"{qid}:search_scope", "not_found_without_scope", "空范围已回填默认统计")
    return entry

# ---------------------------------------------------------------- assemble / build
def assemble(ctx, draft, draft_err):
    index, case, meta = ctx["index"], ctx["case"], ctx["meta"]
    queries = core.find_queries(case)
    rows = draft_rows(draft or {})
    pairs = match_row(queries, rows)
    entries, hits_all = [], []
    extra = extra_syn(case)
    for q, row in pairs:
        conds = query_conds(case, q)
        if row is None:
            script_hits, _blocked, _ok = search(index, q["question"], conds, extra)
            hits_all.extend([dict(h, query_id=q["query_id"]) for h in script_hits[:5]])
            n_par = sum(len(d.get("paragraphs") or []) for d in (index.get("docs") or []))
            cands = [{k: h.get(k) for k in ("doc_id", "path", "section", "paragraph_id",
                                            "page_physical", "page_printed", "score")}
                     for h in script_hits[:3]]
            auto = None
            if script_hits:
                para = None
                doc0 = core.doc_by_path(index, script_hits[0].get("path"))
                for p in (doc0 or {}).get("paragraphs") or []:
                    if p.get("pid") == script_hits[0].get("paragraph_id"):
                        para = p
                        break
                if para is not None:
                    auto = {"query_id": q["query_id"], "status": "partially_answered", "answer": "",
                            "filters_applied": [rules.filter_text(c) for c in conds],
                            "search_scope": ("脚本兜底：过滤后检索 %d 个文档、%d 个段落，"
                                             "取最高分候选段原文作为待核引文；未经 Agent 裁决"
                                             % (len(index.get("docs") or []), n_par)),
                            "notes": "candidate_evidence_only",
                            "evidence": [{"path": script_hits[0].get("path"),
                                          "quote": para.get("text")}]}
            if auto is not None:
                entry = verify_row(q, auto, index, conds, fill_scope=True)
                entry["candidates"] = cands
                core.degrade(f"{q['query_id']}:answer", "draft_row_missing",
                             "该问无工作稿条目：已给出经逐字校验的候选引文，结论仍需 Agent 裁决")
                entries.append(entry)
            else:
                entries.append({"query_id": q["query_id"], "question": q["question"], "answer": "",
                                "status": "partially_answered",
                                "filters_applied": [rules.filter_text(c) for c in conds],
                                "evidence": [], "rejected_evidence": [], "candidates": cands,
                                "search_scope": ("脚本候选检索：检索了 %d 个文档、%d 个段落，"
                                                 "未检索到可核验段落，也未收到工作稿裁决"
                                                 % (len(index.get("docs") or []), n_par)),
                                "notes": "candidate_only"})
                core.degrade(f"{q['query_id']}:answer", "draft_row_missing",
                             "该问无工作稿条目，且脚本未找到可核验段落")
            continue
        entry = verify_row(q, row, index, conds, fill_scope=True)
        for h in search(index, q["question"], conds, extra)[0][:3]:
            hits_all.append(dict(h, query_id=q["query_id"], origin="script_candidate"))
        for ev in entry.get("evidence") or []:
            hits_all.append({"query_id": q["query_id"], "doc_id": ev["doc_id"], "path": ev["path"],
                             "version": ev["version"], "section_id": ev.get("section_id"),
                             "section": ev.get("section"), "paragraph_id": ev["paragraph_id"],
                             "page_physical": ev.get("page_physical"), "page_printed": ev.get("page_printed"),
                             "score": None, "origin": "agent", "locator": ev.get("locator")})
        entries.append(entry)
    docs = index.get("docs") or []
    ledger = rules.filter_ledger(global_conds(case), docs)
    per_query_ledger = [{"query_id": q["query_id"],
                         "filters": [rules.filter_text(c) for c in query_conds(case, q)],
                         "allowed_docs": [d.get("doc_id") for d in rules.apply_all(query_conds(case, q), docs)[0]]}
                        for q in queries]
    excluded = list(index.get("excluded_evidence") or [])
    if isinstance(draft, dict):
        for x in (draft.get("excluded_evidence") or []):
            if isinstance(x, dict) and x.get("path"):
                excluded.append({"path": x["path"], "reason": x.get("reason") or "agent_reported",
                                 "detail": x.get("detail") or "来自工作稿的排除记录"})
    evidence = [e for en in entries for e in (en.get("evidence") or [])]
    rejected = [r for en in entries for r in (en.get("rejected_evidence") or [])]
    cnt = {"queries": len(entries),
           "answered": sum(1 for e in entries if e["status"] == "answered"),
           "partially_answered": sum(1 for e in entries if e["status"] == "partially_answered"),
           "not_found": sum(1 for e in entries if e["status"] == "not_found"),
           "blocked_by_filter": sum(1 for e in entries if e["status"] == "blocked_by_filter"),
           "evidence": len(evidence), "evidence_rejected": len(rejected),
           "docs_total": len(docs), "docs_indexed": sum(1 for d in docs if d.get("status") == "ok"),
           "docs_failed": sum(1 for d in docs if d.get("status") != "ok"),
           "sections": sum(len(d.get("sections") or []) for d in docs),
           "paragraphs": sum(len(d.get("paragraphs") or []) for d in docs),
           "duplicates_excluded": len(index.get("excluded_evidence") or []),
           "quote_hit_rate": round(len(evidence) / float(max(1, len(evidence) + len(rejected))), 3) if evidence or rejected else 0.0,
           "pages_mapped": sum(1 for d in docs if (d.get("pages") or {}).get("label_source") not in
                               (None, "not_applicable", "assumed_equal"))}
    cov = {"docs_expected": index.get("scan_stats", {}).get("files_on_disk"),
           "docs_declared": index.get("scan_stats", {}).get("declared"),
           "docs_indexed": cnt["docs_indexed"], "docs_failed": cnt["docs_failed"],
           "queries_expected": len(queries), "queries_answered": cnt["answered"],
           "queries_partial": cnt["partially_answered"], "queries_not_found": cnt["not_found"],
           "queries_blocked": cnt["blocked_by_filter"],
           "sections_indexed": cnt["sections"], "paragraphs_indexed": cnt["paragraphs"],
           "docs_with_page_mapping": cnt["pages_mapped"],
           "failures": [f"{f.get('doc_id') or '-'}:{f.get('reason')}" for f in (index.get("failures") or [])][:20]}
    payload = {
        "case_id": meta.get("case_id"),
        "status": "partial",
        "summary": (f"{cnt['queries']} 问：answered {cnt['answered']}、partially_answered "
                    f"{cnt['partially_answered']}、not_found {cnt['not_found']}、blocked_by_filter "
                    f"{cnt['blocked_by_filter']}；索引 {cnt['docs_indexed']}/{cnt['docs_total']} 文档、"
                    f"{cnt['sections']} 节、{cnt['paragraphs']} 段；引文 {len(evidence)} 条"
                    f"（拒收 {len(rejected)}）；副本/旧版排除 "
                    f"{cnt['duplicates_excluded']} 条"),
        "result": {"queries": entries, "hits": hits_all, "filters": ledger,
                   "per_query_filters": per_query_ledger, "excluded_evidence": excluded,
                   "coverage": cov, "failures": index.get("failures") or [],
                   "index_summary": {"digest": index.get("index_digest"),
                                     "library_root": index.get("library_root"),
                                     "root_source": index.get("root_source"),
                                     "scan_stats": index.get("scan_stats"),
                                     "dedupe_groups": (index.get("dedupe") or {}).get("groups"),
                                     "conflicts": (index.get("dedupe") or {}).get("conflicts")},
                   "method_notes": (draft or {}).get("method_notes") or {}},
        "queries": entries, "hits": hits_all, "filters": ledger, "excluded_evidence": excluded,
        "coverage": cov, "evidence": evidence,
        "sources": [{"type": d.get("type"), "path": d.get("path"), "sha256_16": d.get("sha256_16"),
                     "bytes": d.get("bytes"), "version": d.get("version"),
                     "pages": (d.get("pages") or {}).get("count"),
                     "label_source": (d.get("pages") or {}).get("label_source"),
                     "status": d.get("status"), "representative": d.get("representative")}
                    for d in docs],
        "uncertainties": uncertainties_of(index, entries, draft),
        "errors": core.STATE["errors"], "degradations": core.STATE["degradations"],
        "changes": core.STATE["changes"], "counts": cnt,
        "method_notes": (draft or {}).get("method_notes") or {},
        "primary_result": "result.json",
        "extra_terms": extra,
        "contract_keys": core.contract_keys(meta.get("output_contract")),
        "runtime": {"version": VERSION, "script_seconds": round(time.time() - T0, 2),
                    "model_requests_by_script": 0, "python": sys.version.split()[0],
                    "draft_present": draft is not None, "draft_error": draft_err,
                    "index_digest": index.get("index_digest"),
                    "scan_stats": index.get("scan_stats"),
                    "budget": {"wall_limit_s": 900, "model_requests_limit": 64,
                               "note": "脚本不发起模型请求，秒级完成"}},
    }
    if draft is None:
        payload["degradations"] = payload["degradations"] + [
            {"item": "draft", "reason": draft_err or "missing",
             "impact": "仅倒底产物：无 Agent 判断，结论缺失"}]
    payload["status"] = overall_status(payload, draft is not None)
    payload["result"]["status"] = payload["status"]
    return core.apply_contract(payload, meta.get("output_contract"), index)

def uncertainties_of(index, entries, draft):
    out = list(core.STATE["uncertainties"]) + list((draft or {}).get("uncertainties") or [])
    docs = index.get("docs") or []
    assumed = [d.get("path") for d in docs if (d.get("pages") or {}).get("label_source") == "assumed_equal"]
    if assumed:
        out.append({"item": "page_labels", "detail": "印刷页码由页脚推定（assumed_equal）的文档 %d 个，引用页码前建议复核" % len(assumed), "paths": assumed[:5]})
    lowq = [d.get("path") for d in docs if d.get("status") == "low_text_quality"]
    if lowq:
        out.append({"item": "text_quality", "detail": "文本层质量过低而未纳入检索的文档 %d 个" % len(lowq), "paths": lowq[:5]})
    cand = [e.get("query_id") for e in entries if (e.get("notes") or "") .startswith("candidate")]
    if cand:
        out.append({"item": "adjudication", "detail": "以下问题只有脚本候选定位、结论未定：%s" % ", ".join(cand[:8])})
    if not index.get("excluded_evidence"):
        out.append({"item": "dedupe", "detail": "未发现 sha256 完全相同的副本；人工副本或私下版本须写入工作稿 excluded_evidence"})
    if not out:
        out.append({"item": "coverage", "detail": "全部结论均回链到脚本核验过的引文，语义完备性未经人工复核"})
    return out

def overall_status(payload, draft_present):
    cnt = payload.get("counts") or {}
    if not payload.get("case_id") and not cnt.get("queries"):
        return "failed"
    if not cnt.get("docs_total"):
        return "partial"
    if not draft_present:
        return "partial"
    if cnt.get("evidence_rejected"):
        return "partial"
    if not cnt.get("queries"):
        return "partial"
    return "ok"
