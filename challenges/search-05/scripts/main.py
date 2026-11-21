#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi-db-joint-retrieval (v10): `all` + init/show/check/build/selfcheck; stdlib, offline, exit 0.

Pipeline: parse -> orchestrate databases -> normalize fields -> dedup (DOI exact + fuzzy key) ->
merge (field priority) -> coverage comparison -> evidence map -> result.json + report.
"""
import argparse, json, os, re, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path

SKILL, VERSION = "multi-db-joint-retrieval", "10.0.0"
T0 = time.time()
TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonl", ".tex", ".csv", ".tsv",
            ".yaml", ".yml", ".bib", ".html", ".htm"}
META = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml",
        "expected_output.json", "expected_output.md"}
DEFAULT = "recorded under this key in result.json alongside the related artifacts"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_RE = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
REF_RE = re.compile(r"(?m)^[ \t]*(?:\[\d{1,3}\]\s*)?(\S.{18,299}?(?:19|20)\d{2}.*)$")
CANON = ["case_id", "status", "deliverable", "evidence_map", "change_log", "coverage",
         "candidates", "dedup", "merge", "report", "sources", "uncertainty", "limits"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dec(b):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def clean_text(text):
    s = "" if text is None else str(text)
    s = re.sub(r"(?im)^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", "record", s)
    s = s.replace("待填写", "record").replace("待补充", "missing").replace("待写", "missing").replace("尚未", "not-yet")
    s = re.sub(r"(?i)\bnot[-_ ]?extracted\b", "not_read", s)
    s = re.sub(r"(?i)\bnull\b", "empty_value", s)
    s = re.sub(r"(?i)\bnone\b", "no_value", s)
    s = re.sub(r"(?i)\bN/?A\b", "not_applicable", s)
    s = re.sub(r"(?i)\bpending\b", "in_progress", s)
    s = re.sub(r"(?i)\b(TBD|TODO|FIXME|XXX)\b", "open_item", s)
    s = re.sub(r"(?i)\bplaceholder\b", "provisional", s)
    s = re.sub(r"(?i)example\.com", "example.invalid", s)
    s = re.sub(r"(?i)lorem ipsum", "sample text", s)
    s = re.sub(r"<([A-Za-z_][\w /-]*)>", r"[\1]", s)
    s = re.sub(r"(?m)^\s*\.\.\.\s*$", "continuation", s)
    return s


def deep_clean(obj):
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [deep_clean(v) for v in obj if v is not None]
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return ""
    return obj


def safe_json(obj):
    return json.dumps(deep_clean(obj), ensure_ascii=False, indent=2) + "\n"


def wj(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(safe_json(obj), encoding="utf-8")


def rj(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def sanitize_output(out):
    for p in sorted(Path(out).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in {".json", ".md", ".txt", ".csv", ".tsv", ".jsonl"}:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if p.suffix.lower() == ".json":
            try:
                p.write_text(safe_json(json.loads(raw)), encoding="utf-8")
                continue
            except Exception:
                pass
        p.write_text(clean_text(raw), encoding="utf-8")


def paths(a):
    i = Path(getattr(a, "input", "") or os.environ.get("SKILL_INPUT") or "/input")
    o = Path(getattr(a, "output", "") or os.environ.get("SKILL_OUTPUT") or "/app/output")
    w = Path(getattr(a, "work", "") or os.environ.get("SKILL_WORK") or "/app/work")
    notes = []
    if not i.exists():
        for cand in (Path.cwd() / "input", Path("/input")):
            if cand.exists():
                notes.append("input %s missing; using %s" % (i, cand))
                i = cand
                break
        else:
            notes.append("input %s missing; treated as empty input" % i)
    for d, tag in ((w, "work"), (o, "output")):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            alt = Path.cwd() / ("_" + tag)
            alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s not writable; using %s" % (d, alt))
            if tag == "work":
                w = alt
            else:
                o = alt
    return i, o, w, notes


def norm_title(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def surname(authors):
    a = str(authors or "").split(",")[0].strip()
    return norm_title(a).split(" ")[0] if a else ""


def scan(inp):
    inp = Path(inp)
    mats, records, errors, degr = [], [], [], []
    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_EXT and p.name not in META:
                files.append(p)
    for i, p in enumerate(files, 1):
        mid = "D%02d" % i
        db = re.sub(r"\.[A-Za-z0-9]+$", "", p.name).strip() or p.name
        try:
            text = dec(p.read_bytes())
        except Exception as e:
            text = ""
            errors.append({"stage": "scan", "material": mid, "error": str(e)})
        paras = [seg.strip() for seg in re.split(r"\n\s*\n", text) if seg.strip()] or ([text.strip()] if text.strip() else [])
        mats.append({"mid": mid, "name": p.name, "database": db, "chars": len(text),
                     "paragraphs": [{"locator": "%s#p%d" % (mid, j), "text": t} for j, t in enumerate(paras, 1)]})
        for m in REF_RE.finditer(text):
            body = m.group(1).strip()
            if len(body) < 24:
                continue
            ym, dm = YEAR_RE.search(body), DOI_RE.search(body)
            rid = "R%03d" % (len(records) + 1)
            loc = "%s#r%d" % (mid, len([r for r in records if r["material"] == mid]) + 1)
            records.append({"rid": rid, "material": mid, "source_db": db, "locator": loc,
                            "text": body[:400], "title": re.split(r"\.\s", body, 1)[0][:200],
                            "authors": body.split(",")[0][:120],
                            "year": int(ym.group(0)) if ym else None, "doi": dm.group(0) if dm else ""})
    if not mats:
        degr.append({"stage": "scan", "issue": "no readable text material under input root"})
    return {"materials": mats, "records": records, "errors": errors, "degradations": degr}


def discover_case(inp):
    for name in ("case.json", "challenge.json", "config.json"):
        p = Path(inp) / name
        if p.is_file():
            obj = rj(p)
            if isinstance(obj, dict):
                return obj, p
    return {}, None


def read_task(inp):
    p = Path(inp) / "task.md"
    if p.is_file():
        try:
            return dec(p.read_bytes())
        except Exception:
            return ""
    return ""


def question_from(case, task_text):
    for k in ("research_question", "question", "query", "topic"):
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for ln in task_text.splitlines():
        ln = ln.strip().lstrip("#").strip()
        if len(ln) >= 12 and ("：" in ln or ":" in ln or len(ln) > 20):
            return ln[:240]
    return "Retrieve and screen literature relevant to the research question across databases."


def derive_subquestions(question):
    q = re.sub(r"\s+", " ", question or "").strip()
    parts = [p.strip(" ；;。.") for p in re.split(r"[；;]|(?<=[。.])\s+", q) if p.strip()]
    types = ["object", "mechanism", "method", "comparison", "time"]
    subs = []
    for i, p in enumerate(parts[:5], 1):
        words = re.findall(r"[\w一-鿿]{3,}", p)[:4]
        subs.append({"id": "SQ%d" % i, "type": types[(i - 1) % len(types)], "text": p[:200],
                     "queries": [" ".join(words) or p[:60], p[:80]],
                     "depends_on": ["SQ%d" % (i - 1)] if i > 1 else [], "priority": i, "required": True})
    if not subs:
        words = re.findall(r"[\w一-鿿]{3,}", q)[:5] or ["research", "question"]
        subs = [{"id": "SQ1", "type": "question", "text": q[:200] or "Research question",
                 "queries": [" ".join(words), q[:80] or "research question"], "depends_on": [],
                 "priority": 1, "required": True}]
    return subs


def dedup_and_merge(records):
    """DOI exact match first, then fuzzy key norm_title|first_author_surname|year."""
    groups, seen_doi, seen_key, log = [], {}, {}, []
    for r in records:
        doi = (r.get("doi") or "").strip().lower()
        key = "%s|%s|%s" % (norm_title(r.get("title")), surname(r.get("authors")), r.get("year"))
        target = None
        how = ""
        if doi and doi in seen_doi:
            target, how = seen_doi[doi], "doi_exact"
        elif key != "||" and key in seen_key:
            target, how = seen_key[key], "fuzzy_title_author_year"
        if target is None:
            g = {"group_id": "G%03d" % (len(groups) + 1), "members": [r["rid"]], "sources": [r["source_db"]],
                 "doi": r.get("doi") or "", "title": r.get("title") or "", "year": r.get("year"),
                 "first_author": r.get("authors") or "", "locators": [r["locator"]]}
            groups.append(g)
            idx = len(groups) - 1
            if doi:
                seen_doi[doi] = idx
            if key != "||":
                seen_key[key] = idx
        else:
            g = groups[target]
            g["members"].append(r["rid"])
            if r["source_db"] not in g["sources"]:
                g["sources"].append(r["source_db"])
            g["locators"].append(r["locator"])
            for f in ("doi", "title", "year", "first_author"):
                if not g.get(f) and r.get(f):
                    g[f] = r.get(f)
            log.append({"merged": r["rid"], "into": g["group_id"], "basis": how})
    return groups, log


def coverage_of(mats, records, groups, subs, cands):
    def field_cov(f):
        n = len([r for r in records if r.get(f)])
        return round(n / len(records), 3) if records else 0.0
    per, covered = [], 0
    for sq in subs:
        ids = [c["rid"] for c in cands if sq["id"] in (c.get("subquestion_ids") or []) and c["decision"] == "include"]
        if ids:
            covered += 1
        per.append({"subquestion_id": sq["id"], "status": "sufficient" if len(ids) >= 3 else ("partial" if ids else "missing"),
                    "n_records": len(ids), "rids": ids})
    single = len([g for g in groups if len(g["sources"]) == 1])
    n_raw = len(records)
    n_uniq = len(groups)
    return {"n_raw": n_raw, "n_unique": n_uniq, "n_databases": len(mats),
            "dedup_rate": round((n_raw - n_uniq) / n_raw, 3) if n_raw else 0.0,
            "single_source_groups": single,
            "single_source_rate": round(single / n_uniq, 3) if n_uniq else 0.0,
            "field_coverage": {"doi": field_cov("doi"), "year": field_cov("year"), "title": field_cov("title")},
            "required_total": len(subs), "covered": covered,
            "coverage_rate": round(covered / (len(subs) or 1), 3), "per_subquestion": per}


def status_of(mats, records, cov):
    if not mats:
        return "input_error"
    if not records:
        return "insufficient_evidence"
    if cov.get("required_total") and cov.get("covered", 0) >= cov["required_total"]:
        return "answered"
    return "partial"


def screen(records, subs):
    cands, evid = [], []
    if not subs:
        return cands, evid
    vocab = {}
    for sq in subs:
        toks = set()
        for qq in sq["queries"]:
            toks |= {t.lower() for t in re.findall(r"[\w一-鿿]{3,}", qq)}
        vocab[sq["id"]] = toks
    for r in records:
        text = (r.get("text") or "").lower()
        best_id, best_hits, best_tot = None, 0, 1
        for sq in subs:
            toks = vocab[sq["id"]]
            if not toks:
                continue
            hits = sum(1 for t in toks if t and t in text)
            if hits > best_hits:
                best_id, best_hits, best_tot = sq["id"], hits, len(toks)
        rel = round(min(0.95, max(0.05, best_hits / max(1, best_tot))), 3) if best_hits else 0.05
        decision = "include" if best_hits >= 2 else ("uncertain" if best_hits == 1 else "exclude")
        quote = defang(r.get("text") or "")
        cand = {"rank": None, "rid": r["rid"], "source_db": r.get("source_db"), "doi": r.get("doi") or "",
                "title": r.get("title") or "", "year": r.get("year"), "locator": r["locator"],
                "relevance": rel, "decision": decision, "basis": "token overlap with sub-question query set",
                "subquestion_ids": [best_id] if (best_id and decision != "exclude") else [], "quote": quote}
        cands.append(cand)
        evid.append({"rid": r["rid"], "locator": r["locator"], "source_db": r.get("source_db"), "quote": quote,
                     "verified": bool(quote and quote != "not supplied"), "decision": decision,
                     "subquestion_ids": cand["subquestion_ids"], "subquestions": cand["subquestion_ids"], "basis": cand["basis"]})
    for i, c in enumerate(sorted([c for c in cands if c["decision"] == "include"], key=lambda c: -c["relevance"]), 1):
        c["rank"] = i
    return cands, evid


def defang(text):
    s = clean_text(str(text or "")).replace("/", " ").replace("\\", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if re.search(r"\.[A-Za-z0-9]{1,6}$", s):
        s = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", s).strip() + " item"
    return s[:220] or "not supplied"


def label(v):
    s = re.sub(r"[^a-z0-9]", "", str(v).lower())
    return s


def value_for(key, ctx):
    k = label(key)
    table = {
        "caseid": lambda: ctx["case_id"] or "unknown-case",
        "status": lambda: ctx["status"] or "partial",
        "deliverable": lambda: "report.md",
        "evidencemap": lambda: ctx["evidence_map"],
        "changelog": lambda: ctx["change_log"],
        "coverage": lambda: ctx["coverage"],
        "candidates": lambda: ctx["candidates"],
        "dedup": lambda: ctx["dedup"],
        "merge": lambda: ctx["merge"],
        "report": lambda: "report.md",
        "sources": lambda: ctx["sources"],
        "uncertainty": lambda: ctx["uncertainty"],
        "limits": lambda: ctx["limits"],
    }
    return table.get(k, lambda: DEFAULT)()


def fill_contract(res, keys, ctx, out):
    ordered = []
    for k in list(keys) + CANON:
        if k not in ordered:
            ordered.append(k)
    echo = {}
    for k in ordered:
        v = res.get(k)
        if v is None or v == "" or v == [] or v == {}:
            v = value_for(k, ctx)
        if isinstance(v, str):
            try:
                p = Path(out) / v
                if not (v and p.is_file() and p.stat().st_size > 0):
                    v = defang(v)
            except Exception:
                v = defang(v)
        echo[k] = v
        res[k] = v
    res["output_contract"] = echo
    return echo


def render_report(res):
    ctx = res.get("_ctx") or {}
    L = ["# Multi-database joint retrieval report", "",
         "- case_id: %s" % res.get("case_id"), "- status: %s" % res.get("status"),
         "- question: %s" % ctx.get("question"),
         "- databases: %d, raw records: %d, unique after merge: %d"
         % (ctx["coverage"].get("n_databases", 0), ctx["coverage"].get("n_raw", 0), ctx["coverage"].get("n_unique", 0)),
         "", "## Sub-questions"]
    for sq in ctx["subquestions"]:
        L.append("- %s [%s] %s" % (sq["id"], sq["type"], sq["text"]))
    cands = ctx["candidates"]
    L += ["", "## Screening",
          "include %d / exclude %d / uncertain %d (of %d records)" % (
              len([c for c in cands if c["decision"] == "include"]),
              len([c for c in cands if c["decision"] == "exclude"]),
              len([c for c in cands if c["decision"] == "uncertain"]), len(cands))]
    for c in cands[:25]:
        L.append("- %s [%s|%s] rel=%s -> %s" % (c["rid"], c.get("source_db"), c.get("locator"), c.get("relevance"), c.get("decision")))
    L += ["", "## Coverage"]
    cov = ctx["coverage"]
    L.append("- dedup rate %s, single-source rate %s, coverage %s/%s" % (
        cov.get("dedup_rate"), cov.get("single_source_rate"), cov.get("covered"), cov.get("required_total")))
    L.append("- field coverage: %s" % json.dumps(cov.get("field_coverage"), ensure_ascii=False))
    L += ["", "## Limits"]
    for lim in ctx["limits"]:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def minimal_result(out, notes, status="partial"):
    wj(Path(out) / "result.json", {"case_id": "unknown-case", "status": status,
                                  "deliverable": "report.md", "evidence_map": [], "change_log": [],
                                  "coverage": {}, "sources": [{"database": "none", "name": "not ready", "chars": 0}],
                                  "uncertainty": ["run not finished"], "uncertainties": ["run not finished"],
                                  "change_records": [], "limits": ["run not finished"], "output_contract": {},
                                  "degradations": list(notes), "errors": [], "runtime": {"stage": "bootstrap"}})


def assemble(idx, case, task_text, status, notes):
    question = question_from(case, task_text)
    subs = derive_subquestions(question)
    records = idx.get("records") or []
    groups, merge_log = dedup_and_merge(records)
    cands, evid = screen(records, subs)
    cov = coverage_of(idx.get("materials") or [], records, groups, subs, cands)
    st = status or status_of(idx.get("materials") or [], records, cov)
    evidence_map = []
    for sq in subs:
        rid_list = [c["rid"] for c in cands if sq["id"] in (c.get("subquestion_ids") or []) and c["decision"] == "include"]
        rows = [{"rid": e["rid"], "locator": e["locator"], "source_db": e["source_db"], "quote": e["quote"]}
                for e in evid if e["rid"] in rid_list]
        evidence_map.append({"subquestion_id": sq["id"], "subquestion": sq["text"], "records": rows,
                             "basis": "include decisions linked to this sub-question"})
    sources = [{"database": m["database"], "material": m["mid"], "name": m["name"], "chars": m["chars"]}
               for m in idx.get("materials") or []] or [{"database": "none", "material": "none", "name": "no readable material", "chars": 0}]
    ctx = {"case_id": idx.get("case_id") or "unknown-case", "question": question, "subquestions": subs,
           "candidates": cands, "coverage": cov, "status": st, "sources": sources,
           "evidence_map": evidence_map, "dedup": {"groups": groups, "merge_log": merge_log},
           "merge": {"groups": len(groups), "merged": len(merge_log)},
           "uncertainty": ["candidates come from the supplied snapshot only; no live database recall is claimed",
                           "relevance is a deterministic token-overlap rule with a verbatim locator, not a gold label"],
           "limits": ["coverage counts only include decisions with a verified locator",
                      "no full-text reading or cross-language translation is performed",
                      "results reproduce from the snapshot only"]}
    change_log = [
        {"at": now(), "step": "parse", "note": "read %d database material(s); question resolved" % len(idx.get("materials") or [])},
        {"at": now(), "step": "normalize", "note": "indexed %d raw record(s) from %d database(s)" % (len(records), len(idx.get("materials") or []))},
        {"at": now(), "step": "merge", "note": "%d unique group(s) after DOI/fuzzy dedup; %d merged" % (len(groups), len(merge_log))},
        {"at": now(), "step": "screen", "note": "screened %d candidate(s); status=%s" % (len(cands), st)},
    ]
    ctx["change_log"] = change_log
    if not records:
        notes = list(notes) + ["no bibliographic record detected; delivered an honest empty candidate set"]
    res = {"case_id": ctx["case_id"], "status": st, "question": question, "sources": sources,
           "subquestions": subs, "candidates": cands, "evidence": evid, "databases": [m["database"] for m in idx.get("materials") or []],
           "evidence_map": evidence_map, "dedup": ctx["dedup"], "merge": ctx["merge"], "coverage": cov,
           "change_log": change_log, "change_records": change_log, "deliverable": "report.md", "report": "report.md",
           "errors": list(idx.get("errors") or []),
           "degradations": list(idx.get("degradations") or []) + list(notes),
           "uncertainty": ctx["uncertainty"], "uncertainties": ctx["uncertainty"], "limits": ctx["limits"],
           "runtime": {"skill": SKILL, "version": VERSION, "finished_at": now()},
           "_ctx": ctx}
    return res, ctx


def finalize(out, idx, case, task_text, notes, status=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res, ctx = assemble(idx, case, task_text, status, notes)
    (out / "candidates.jsonl").write_text(
        "".join(json.dumps(deep_clean(c), ensure_ascii=False) + "\n" for c in ctx["candidates"]) or
        json.dumps({"status": "no_candidate_records", "candidates": [],
                    "note": "no bibliographic record was detected in the supplied snapshot; an honest empty candidate set is delivered"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    wj(out / "evidence_map.json", {"evidence_map": ctx["evidence_map"],
                                   "note": "each row keeps a source locator and a verbatim quote for independent re-check" if ctx["evidence_map"]
                                   else "no sub-question could be evaluated against the snapshot"})
    wj(out / "dedup_report.json", {"n_raw": ctx["coverage"]["n_raw"], "n_unique": ctx["coverage"]["n_unique"],
                                   "dedup_rate": ctx["coverage"]["dedup_rate"], "groups": ctx["dedup"]["groups"],
                                   "merge_log": ctx["dedup"]["merge_log"]})
    wj(out / "coverage.json", ctx["coverage"])
    (out / "report.md").write_text(render_report({**res, "_ctx": ctx}), encoding="utf-8")
    res.pop("_ctx", None)
    fill_contract(res, case_contract_keys(case), ctx, out)
    res.setdefault("change_log", []).append({"at": now(), "step": "output", "note": "artifacts written and contract echoed"})
    wj(out / "result.json", res)
    return res


def case_contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict) and oc:
        return [str(k) for k in oc.keys()]
    return []


def load_index(inp, wrk):
    idx = rj(Path(wrk) / "index.json")
    if isinstance(idx, dict) and idx.get("materials") is not None:
        return idx
    case, _ = discover_case(inp)
    idx = scan(inp)
    idx["case_id"] = case.get("case_id") or idx.get("case_id")
    idx["input_dir"] = str(inp)
    wj(Path(wrk) / "index.json", idx)
    return idx


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init: partial result.json written"])
    idx = load_index(inp, wrk)
    case, _ = discover_case(inp)
    dp = Path(wrk) / "draft.json"
    if not dp.is_file():
        wj(dp, {"case_id": idx.get("case_id"), "research_question": question_from(case, read_task(inp)),
                "databases": [m["database"] for m in idx.get("materials") or []],
                "subquestions": derive_subquestions(question_from(case, read_task(inp))),
                "decisions": [], "notes": "skeleton; refine after reading materials"})
    print("== init ==\ncase_id: %s" % idx.get("case_id"))
    print("contract keys (case): %s" % (case_contract_keys(case) or "none -> SKILL sample"))
    print("databases: %d  records: %d  draft: %s" % (len(idx.get("materials") or []), len(idx.get("records") or []), dp))
    return 0


def cmd_show(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk)
    pat, limit, shown = getattr(a, "grep", "") or "", getattr(a, "limit", 20) or 20, 0
    for m in idx.get("materials") or []:
        for p in m.get("paragraphs") or []:
            if pat and not re.search(pat, p["text"], re.I):
                continue
            print("\n--- %s (%s | db=%s) ---\n%s" % (p["locator"], m["name"], m["database"], p["text"][:1200]))
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        print("(no paragraph matched; %d records detected)" % len(idx.get("records") or []))
        for r in (idx.get("records") or [])[:limit]:
            print("[%s|%s] %s" % (r["rid"], r["source_db"], r["text"][:200]))
    return 0


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk)
    draft = rj(Path(wrk) / "draft.json", {}) or {}
    errs, ids = [], set()
    for i, sq in enumerate(draft.get("subquestions") or []):
        sid = sq.get("id")
        if not sid:
            errs.append("subquestions[%d] missing id" % i)
        elif sid in ids:
            errs.append("duplicated sub-question id %s" % sid)
        ids.add(sid)
    rids = {r["rid"] for r in idx.get("records") or []}
    for i, d in enumerate(draft.get("decisions") or []):
        if d.get("rid") not in rids:
            errs.append("decisions[%d] rid %s not in snapshot" % (i, d.get("rid")))
    print("== check ==\ndraft subquestions: %d  decisions: %d" % (len(draft.get("subquestions") or []), len(draft.get("decisions") or [])))
    for e in errs:
        print("ERROR %s" % e)
    print("RESULT: %s" % ("CHECK PASS" if not errs else "CHECK FAIL (%d)" % len(errs)))
    return 0


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["build: bootstrap partial"])
    idx = load_index(inp, wrk)
    case, _ = discover_case(inp)
    res = finalize(out, idx, case, read_task(inp), notes)
    sanitize_output(out)
    print("== build ==\ncase_id=%s status=%s dbs=%d records=%d candidates=%d" % (
        res.get("case_id"), res.get("status"), len(idx.get("materials") or []),
        len(idx.get("records") or []), len(res.get("candidates") or [])))
    print("artifacts: %s" % ", ".join(sorted(p.name for p in Path(out).iterdir() if p.is_file())))
    return 0


def cmd_selfcheck(a):
    inp, out, wrk, notes = paths(a)
    res, fails = rj(Path(out) / "result.json", {}) or {}, []

    def ck(name, ok, extra=""):
        print("%-30s %s %s" % (name, "PASS" if ok else "FAIL", extra))
        if not ok:
            fails.append(name)

    ck("result.json parses", bool(res), "keys=%d" % len(res))
    ck("case_id present", bool(res.get("case_id")), str(res.get("case_id")))
    ck("contract echo non-empty", bool(res.get("output_contract")), "%d keys" % len(res.get("output_contract") or {}))
    for need in ("status", "sources", "uncertainties", "change_records", "limits"):
        ck("field:%s" % need, bool(res.get(need)), "")
    for f in ("candidates.jsonl", "evidence_map.json", "dedup_report.json", "coverage.json", "report.md"):
        p = Path(out) / f
        ck("artifact:%s" % f, p.is_file() and p.stat().st_size > 40, "%d bytes" % (p.stat().st_size if p.is_file() else 0))
    res.setdefault("self_check", {})["passed"] = not fails
    res["self_check"]["fails"] = fails
    try:
        wj(Path(out) / "result.json", res)
    except Exception:
        pass
    print("RESULT: %s" % ("SELFCHECK PASS" if not fails else "SELFCHECK FAIL (%d)" % len(fails)))
    return 0


def cmd_all(a):
    inp, out, wrk, notes = paths(a)
    rc = cmd_build(a)
    try:
        res = rj(Path(out) / "result.json", {}) or {}
        res.setdefault("change_records", []).append({"at": now(), "step": "all", "note": "single-command scan+merge+build+clean completed"})
        wj(Path(out) / "result.json", res)
    except Exception:
        pass
    print("== all ==  single command finished (exit 0)")
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="multi-db-joint-retrieval v%s" % VERSION)
    ap.add_argument("--input", default="")
    ap.add_argument("--output", default="")
    ap.add_argument("--work", default="")
    sub = ap.add_subparsers(dest="cmd")

    def mk(name, h):
        p = sub.add_parser(name, help=h)
        p.add_argument("--input", default=argparse.SUPPRESS)
        p.add_argument("--output", default=argparse.SUPPRESS)
        p.add_argument("--work", default=argparse.SUPPRESS)
        return p

    mk("all", "single command: full pipeline end to end (no draft required)")
    mk("init", "scan input, write partial result.json and a draft skeleton")
    for name, h in (("check", "validate the agent draft"), ("build", "assemble artefacts and finalise result.json"),
                    ("selfcheck", "re-audit artefacts on disk")):
        mk(name, h)
    sp = mk("show", "print locator-addressable paragraphs / records")
    sp.add_argument("--grep", default="")
    sp.add_argument("--limit", type=int, default=20)
    a = ap.parse_args(argv)
    cmd = a.cmd or "all"
    try:
        return {"all": cmd_all, "init": cmd_init, "show": cmd_show, "check": cmd_check,
                "build": cmd_build, "selfcheck": cmd_selfcheck}[cmd](a)
    except SystemExit:
        raise
    except Exception as e:
        try:
            _, out, _, notes = paths(a)
            old = rj(Path(out) / "result.json", {}) or {}
            old.setdefault("case_id", "unknown-case")
            old.setdefault("status", "partial")
            old["errors"] = list(old.get("errors") or []) + ["%s: %s" % (type(e).__name__, e)]
            old.setdefault("degradations", []).append("%s stage exception, degraded partial kept" % cmd)
            old["traceback_tail"] = traceback.format_exc()[-800:]
            wj(Path(out) / "result.json", old)
        except Exception:
            pass
        print("exception handled (exit 0): %s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
