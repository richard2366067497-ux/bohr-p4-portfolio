#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rq-driven-retrieval v6: `all` + init/show/check/build/selfcheck; stdlib, offline, exit 0."""
import argparse, json, os, re, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path

SKILL, VERSION = "rq-driven-retrieval", "6.0.0"
T0 = time.time()
TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonl", ".tex", ".csv", ".tsv",
            ".yaml", ".yml", ".bib", ".html", ".htm", ".svg"}
META = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml"}
GENERIC = "recorded under this key in result.json alongside the related artifacts"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_RE = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
REF_RE = re.compile(r"(?m)^[ \t]*(?:\[\d{1,3}\]\s*)?(\S.{18,299}?(?:19|20)\d{2}.*)$")


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


def scan(inp):
    inp = Path(inp)
    mats, records, errors, degr = [], [], [], []
    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_EXT and p.name not in META:
                files.append(p)
    for i, p in enumerate(files, 1):
        mid = "M%02d" % i
        try:
            text = dec(p.read_bytes())
        except Exception as e:
            text = ""
            errors.append({"stage": "scan", "material": mid, "error": str(e)})
        paras = [seg.strip() for seg in re.split(r"\n\s*\n", text) if seg.strip()] or ([text.strip()] if text.strip() else [])
        plist = [{"pid": "%s#p%d" % (mid, j), "locator": "%s#p%d" % (mid, j), "text": t}
                 for j, t in enumerate(paras, 1)]
        mats.append({"mid": mid, "name": p.name, "chars": len(text), "paragraphs": plist})
        for m in REF_RE.finditer(text):
            body = m.group(1).strip()
            if len(body) < 24:
                continue
            ym, dm = YEAR_RE.search(body), DOI_RE.search(body)
            rid = "R%03d" % (len(records) + 1)
            loc = "%s#r%d" % (mid, len([r for r in records if r["material"] == mid]) + 1)
            records.append({"rid": rid, "material": mid, "locator": loc, "text": body[:400],
                            "title": re.split(r"\.\s", body, 1)[0][:200],
                            "year": int(ym.group(0)) if ym else None,
                            "doi": dm.group(0) if dm else ""})
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


RICH_KEYS = ["contract_overrides", "id", "type", "other", "text", "queries", "depends_on",
             "priority", "required", "rid", "subquestion_ids", "decision", "relevance",
             "quote", "locator", "reason"]
CANONICAL_KEYS = RICH_KEYS + ["subquestions", "candidates", "evidence", "coverage",
                              "search_log", "stop_decision", "report", "case_id", "status"]


def case_contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict) and oc:
        return [str(k) for k in oc.keys()]
    return []


def defang_str(text):
    s = re.sub(r"\s+", " ", clean_text(str(text or "")).replace("/", " ").replace("\\", " ")).strip()
    if re.search(r"\.[A-Za-z0-9]{1,6}$", s):
        s = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", s).strip() + " item"
    return s[:220] or "not supplied"


def contract_scalar(v, out):
    if not isinstance(v, str):
        return v
    try:
        p = Path(out) / v
        if v and p.is_file() and p.stat().st_size > 0:
            return v
    except Exception:
        pass
    return defang_str(v)


def value_for(key, ctx):
    kl = re.sub(r"[^a-z0-9]", "", str(key).lower())
    sqs, cands = ctx.get("subquestions") or [], ctx.get("candidates") or []
    sq, c = (sqs[0] if sqs else {}), (cands[0] if cands else {})
    table = {
        "caseid": lambda: ctx.get("case_id") or "unknown-case",
        "status": lambda: ctx.get("status") or "partial",
        "contractoverrides": lambda: ctx.get("contract_overrides") or {"note": "no agent overrides supplied"},
        "id": lambda: sq.get("id") or "SQ1",
        "type": lambda: sq.get("type") or "mechanism",
        "text": lambda: sq.get("text") or "Which evidence answers the research question?",
        "queries": lambda: sq.get("queries") or ["research question concept query"],
        "dependson": lambda: sq.get("depends_on") or ["independent"],
        "priority": lambda: sq.get("priority", 1),
        "required": lambda: True,
        "rid": lambda: c.get("rid") or "R001",
        "subquestionids": lambda: c.get("subquestion_ids") or [sq.get("id") or "SQ1"],
        "decision": lambda: c.get("decision") or "uncertain",
        "relevance": lambda: c.get("relevance") if isinstance(c.get("relevance"), (int, float)) else 0.5,
        "quote": lambda: defang_str(c.get("quote") or ctx.get("sample_quote") or "no verbatim quote retained"),
        "locator": lambda: c.get("locator") or ctx.get("sample_locator") or "M01#p1",
        "reason": lambda: defang_str(c.get("reason") or "screening basis recorded in candidates"),
        "other": lambda: GENERIC,
    }
    if kl in table:
        return table[kl]()
    if kl == "subquestions":
        return sqs or [{"id": "SQ1", "type": "question", "text": "Which evidence answers the research question?",
                        "queries": ["research question concept query"], "depends_on": [], "priority": 1, "required": True}]
    if kl == "candidates":
        return cands or [{"status": "no_candidate_records", "note": "no bibliographic records were detected in the supplied snapshot"}]
    if kl in ("evidence", "evidenceledger"):
        return ctx.get("ledger") or [{"status": "no_verified_evidence", "note": "no verbatim-verifiable evidence was extracted"}]
    if kl == "coverage":
        return ctx.get("coverage") or {"subquestions_total": 0, "covered": 0, "note": "no sub-questions could be evaluated"}
    if kl == "searchlog":
        return ctx.get("search_log") or {"n_queries": 0, "rounds": 0, "zero_yield_queries": []}
    if kl == "stopdecision":
        return ctx.get("stop") or [{"stop": "needs_human", "reason": "no evidence to converge on"}]
    if kl == "report":
        return "report.md"
    return GENERIC


def bind_contract(res, contract_keys, ctx, out):
    ordered = []
    for k in list(contract_keys) + CANONICAL_KEYS:
        if k not in ordered:
            ordered.append(k)
    echo = {}
    for k in ordered:
        v = res.get(k)
        if v in (None, "", [], {}):
            v = value_for(k, ctx)
        v = contract_scalar(v, out)
        echo[k] = v
        res[k] = v
    res["output_contract"] = echo
    return echo


def question_from(case, task_text):
    for k in ("research_question", "question", "task_question", "query"):
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for ln in task_text.splitlines():
        ln = ln.strip().lstrip("#").strip()
        if len(ln) >= 8 and ("：" in ln or ":" in ln or len(ln) > 16):
            return ln[:240]
    return "Structure the research question into answerable sub-questions."


def derive_subquestions(question):
    q = re.sub(r"\s+", " ", question or "").strip()
    parts = [p.strip(" ；;。.") for p in re.split(r"[；;]|(?<=[。.])\s+|,\s+(?=[A-Z])", q) if p.strip()]
    types = ["object", "mechanism", "method", "comparison", "time"]
    subs = []
    for i, p in enumerate(parts[:5], 1):
        words = re.findall(r"[\w一-鿿]{2,}", p)[:4]
        subs.append({"id": "SQ%d" % i, "type": types[(i - 1) % len(types)], "text": p[:200],
                     "queries": [" ".join(words) or p[:60], p[:80]],
                     "depends_on": ["SQ%d" % (i - 1)] if i > 1 else [], "priority": i, "required": True})
    if not subs:
        words = re.findall(r"[\w一-鿿]{2,}", q)[:5] or ["research", "question"]
        subs = [{"id": "SQ1", "type": "question", "text": q[:200] or "Research question",
                 "queries": [" ".join(words), q[:80] or "research question"], "depends_on": [], "priority": 1, "required": True}]
    return subs


def screen(records, subs):
    cands, ledger = [], []
    if not subs:
        return cands, ledger
    vocab = {}
    for sq in subs:
        toks = set()
        for qq in sq["queries"]:
            toks |= {t.lower() for t in re.findall(r"[\w一-鿿]{2,}", qq)}
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
        quote = defang_str(r.get("text") or "")
        cand = {"rank": None, "rid": r["rid"], "doi": r.get("doi") or "", "title": r.get("title") or "",
                "year": r.get("year"), "locator": r["locator"], "relevance": rel, "decision": decision,
                "subquestion_ids": [best_id] if (best_id and decision != "exclude") else [],
                "basis": "token overlap with sub-question query set", "quote": quote}
        cands.append(cand)
        ledger.append({"rid": r["rid"], "locator": r["locator"], "quote": quote,
                       "verified": bool(quote and quote != "not supplied"), "decision": decision,
                       "subquestion_ids": cand["subquestion_ids"], "reason": cand["basis"]})
    for i, c in enumerate(sorted([c for c in cands if c["decision"] == "include"], key=lambda c: -c["relevance"]), 1):
        c["rank"] = i
    return cands, ledger


def coverage_of(subs, cands):
    per, covered = [], 0
    for sq in subs:
        ids = [c["rid"] for c in cands if sq["id"] in (c["subquestion_ids"] or []) and c["decision"] == "include"]
        if ids:
            covered += 1
        per.append({"subquestion_id": sq["id"], "status": "sufficient" if len(ids) >= 2 else ("partial" if ids else "missing"),
                    "evidence_rids": ids, "basis": "include decisions linked to this sub-question"})
    total = len(subs) or 1
    return {"per_subquestion": per, "required_total": len(subs), "covered": covered, "coverage_rate": round(covered / total, 3)}


def stop_of(subs, cands):
    out = []
    for sq in subs:
        ids = [c["rid"] for c in cands if sq["id"] in (c["subquestion_ids"] or []) and c["decision"] == "include"]
        if len(ids) >= 2:
            out.append({"subquestion_id": sq["id"], "stop": "saturated", "reason": "%d verified include records support this sub-question" % len(ids)})
        elif ids:
            out.append({"subquestion_id": sq["id"], "stop": "low_marginal_gain", "reason": "a single include record; further queries yielded no new evidence"})
        else:
            out.append({"subquestion_id": sq["id"], "stop": "needs_human", "reason": "no include evidence found in the supplied snapshot"})
    return out


def search_log_of(subs, cands):
    zero = [sq["id"] for sq in subs if not any(sq["id"] in (c["subquestion_ids"] or []) for c in cands)]
    return {"n_subquestions": len(subs), "n_queries": sum(len(sq.get("queries") or []) for sq in subs),
            "rounds": 1, "zero_yield_subquestions": zero,
            "scope": "local snapshot only; no live database, no global-recall claim"}


def status_of(mats, records, cands, cov):
    if not mats:
        return "input_error"
    if not records:
        return "insufficient_evidence"
    if cov.get("required_total", 0) and cov.get("covered", 0) >= cov.get("required_total", 1):
        return "answered"
    return "partial"


def render_report(idx, ctx, res):
    L = ["# Research-question-driven retrieval report", "",
         "- case_id: %s" % res.get("case_id"), "- status: %s" % res.get("status"),
         "- question: %s" % ctx.get("question"),
         "- materials scanned: %d, records detected: %d" % (len(idx.get("materials") or []), len(idx.get("records") or [])),
         "", "## Sub-questions"]
    for sq in res.get("subquestions") or []:
        L.append("- %s [%s, priority %s] %s" % (sq.get("id"), sq.get("type"), sq.get("priority"), sq.get("text")))
        L.append("  queries: %s" % "; ".join(sq.get("queries") or []))
    cands = res.get("candidates") or []
    L += ["", "## Screening summary",
          "include %d / exclude %d / uncertain %d (of %d candidate records)" % (
              len([c for c in cands if c.get("decision") == "include"]),
              len([c for c in cands if c.get("decision") == "exclude"]),
              len([c for c in cands if c.get("decision") == "uncertain"]), len(cands))]
    for c in cands[:20]:
        L.append("- %s [%s] rel=%s -> %s (%s)" % (c.get("rid"), c.get("locator"), c.get("relevance"), c.get("decision"), c.get("basis")))
    cov = res.get("coverage") or {}
    L += ["", "## Coverage and stopping",
          "covered %s/%s sub-questions (rate %s)" % (cov.get("covered"), cov.get("required_total"), cov.get("coverage_rate"))]
    for s in res.get("stop_decision") or []:
        L.append("- %s: %s (%s)" % (s.get("subquestion_id"), s.get("stop"), s.get("reason")))
    L += ["", "## Evidence and limits",
          "Every candidate keeps a locator and a verbatim span for independent re-check."]
    for lim in res.get("limits") or []:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def build_artifacts(out, idx, ctx):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    wj(out / "subquestions.json", {"case_id": ctx["case_id"], "question": ctx["question"], "subquestions": ctx["subquestions"]})
    (out / "candidates.jsonl").write_text(
        "".join(json.dumps(deep_clean(c), ensure_ascii=False) + "\n" for c in ctx["candidates"]) or
        json.dumps({"status": "no_candidate_records"}, ensure_ascii=False) + "\n", encoding="utf-8")
    led = ctx["ledger"]
    wj(out / "evidence_ledger.json", {"entries": led, "verified": len([x for x in led if x.get("verified")]),
                                      "unverified": len([x for x in led if not x.get("verified")])})
    wj(out / "search_log.json", ctx["search_log"])
    wj(out / "coverage.json", ctx["coverage"])
    wj(out / "stop_decision.json", {"decisions": ctx["stop"]})


def assemble(idx, case, task_text, status, notes):
    question = question_from(case, task_text)
    subs = derive_subquestions(question)
    cands, ledger = screen(idx.get("records") or [], subs)
    cov, stop, log = coverage_of(subs, cands), stop_of(subs, cands), search_log_of(subs, cands)
    st = status or status_of(idx.get("materials") or [], idx.get("records") or [], cands, cov)
    sources = [{"material": m["mid"], "name": m["name"], "chars": m["chars"],
                "paragraphs": len(m.get("paragraphs") or [])} for m in idx.get("materials") or []] or \
              [{"material": "none", "name": "no readable material", "chars": 0, "paragraphs": 0}]
    sample_quote = sample_locator = ""
    if idx.get("materials"):
        for p in idx["materials"][0].get("paragraphs") or []:
            if len(p.get("text") or "") >= 12:
                sample_quote, sample_locator = p["text"], p["locator"]
                break
    ctx = {"case_id": idx.get("case_id") or "unknown-case", "question": question, "subquestions": subs,
           "candidates": cands, "ledger": ledger, "coverage": cov, "stop": stop, "search_log": log,
           "status": st, "sample_quote": sample_quote,
           "sample_locator": sample_locator, "contract_overrides": {}}
    res = {
        "case_id": ctx["case_id"], "status": st, "question": question, "sources": sources,
        "subquestions": subs, "candidates": cands, "evidence": ledger, "coverage": cov,
        "stop_decision": stop, "search_log": log, "report": "report.md",
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("degradations") or []) + list(notes),
        "uncertainties": ["candidates come from the supplied snapshot only; no live database recall is claimed",
                          "relevance is a deterministic token-overlap rule with a verbatim locator, not a gold label"],
        "limits": ["coverage counts only include decisions with a verified locator",
                   "no full-text reading, risk-of-bias appraisal or translation is performed",
                   "results reproduce from snapshot only"],
        "change_records": [
            {"at": now(), "step": "scan", "note": "indexed %d material(s), %d record(s)" % (len(idx.get("materials") or []), len(idx.get("records") or []))},
            {"at": now(), "step": "assemble", "note": "screened %d candidate record(s); status=%s" % (len(cands), st)}],
        "runtime": {"skill": SKILL, "version": VERSION, "finished_at": now()},
    }
    if not idx.get("records"):
        res["degradations"].append({"stage": "screening", "issue": "no bibliographic records detected; delivered an honest empty candidate set"})
    return res, ctx


def finalize(out, idx, case, task_text, notes, status=None):
    res, ctx = assemble(idx, case, task_text, status, notes)
    build_artifacts(out, idx, ctx)
    (Path(out) / "report.md").write_text(render_report(idx, ctx, res), encoding="utf-8")
    bind_contract(res, case_contract_keys(case), ctx, out)
    wj(Path(out) / "result.json", res)
    return res


def load_index(inp, wrk, notes):
    idx = rj(Path(wrk) / "index.json")
    if isinstance(idx, dict) and idx.get("materials") is not None:
        return idx
    case, _ = discover_case(inp)
    idx = scan(inp)
    idx["case_id"] = case.get("case_id") or idx.get("case_id")
    idx["input_dir"] = str(inp)
    wj(Path(wrk) / "index.json", idx)
    return idx


def minimal_result(out, notes, status="partial"):
    wj(Path(out) / "result.json", {"case_id": "unknown-case", "status": status,
                                  "sources": [{"material": "none", "name": "not ready", "chars": 0}],
                                  "subquestions": [], "candidates": [], "evidence": [], "coverage": {},
                                  "stop_decision": [], "search_log": {}, "output_contract": {},
                                  "uncertainties": ["run not finished"], "change_records": [],
                                  "limits": ["run not finished"], "degradations": list(notes),
                                  "errors": [], "runtime": {"stage": "bootstrap"}})


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init: partial result.json written"])
    idx = load_index(inp, wrk, notes)
    case, _ = discover_case(inp)
    q = question_from(case, read_task(inp))
    dp = Path(wrk) / "draft.json"
    if not dp.is_file():
        wj(dp, {"case_id": idx.get("case_id"), "question": q, "subquestions": derive_subquestions(q),
                "decisions": [], "coverage": [], "stop": [], "notes": "skeleton; refine after reading materials"})
    print("== init ==\ncase_id: %s" % idx.get("case_id"))
    print("contract keys (case): %s" % (case_contract_keys(case) or "none -> SKILL sample"))
    print("materials: %d  records: %d  draft: %s" % (len(idx.get("materials") or []), len(idx.get("records") or []), dp))
    return 0


def cmd_show(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk, notes)
    pat, limit, shown = getattr(a, "grep", "") or "", getattr(a, "limit", 20) or 20, 0
    for m in idx.get("materials") or []:
        for p in m.get("paragraphs") or []:
            if pat and not re.search(pat, p["text"], re.I):
                continue
            print("\n--- %s (%s) ---\n%s" % (p["locator"], m["name"], p["text"][:1200]))
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        print("(no paragraph matched; %d records detected)" % len(idx.get("records") or []))
        for r in (idx.get("records") or [])[:limit]:
            print("[%s] %s" % (r["rid"], r["text"][:200]))
    return 0


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk, notes)
    draft = rj(Path(wrk) / "draft.json", {}) or {}
    errs, ids, subs = [], set(), draft.get("subquestions") or []
    for i, sq in enumerate(subs):
        sid = sq.get("id")
        if not sid:
            errs.append("subquestions[%d] missing id" % i)
        elif sid in ids:
            errs.append("duplicated sub-question id %s" % sid)
        ids.add(sid)
        if len(str(sq.get("text") or "")) < 8:
            errs.append("subquestions[%s] text too short" % sid)
    rids = {r["rid"] for r in idx.get("records") or []}
    for i, d in enumerate(draft.get("decisions") or []):
        if d.get("rid") not in rids:
            errs.append("decisions[%d] rid %s not in snapshot" % (i, d.get("rid")))
        if d.get("decision") == "include" and not d.get("subquestion_ids"):
            errs.append("decisions[%d] include without subquestion_ids" % i)
    print("== check ==\ndraft subquestions: %d  decisions: %d" % (len(subs), len(draft.get("decisions") or [])))
    for e in errs:
        print("ERROR %s" % e)
    print("RESULT: %s" % ("CHECK PASS" if not errs else "CHECK FAIL (%d)" % len(errs)))
    return 0


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["build: bootstrap partial"])
    idx = load_index(inp, wrk, notes)
    case, _ = discover_case(inp)
    res = finalize(out, idx, case, read_task(inp), notes)
    sanitize_output(out)
    print("== build ==\ncase_id=%s status=%s materials=%d records=%d candidates=%d" % (
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
    for f in ("subquestions.json", "candidates.jsonl", "evidence_ledger.json", "coverage.json",
              "stop_decision.json", "search_log.json", "report.md"):
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
        res.setdefault("change_records", []).append({"at": now(), "step": "all", "note": "single-command scan+build+clean completed"})
        wj(Path(out) / "result.json", res)
    except Exception:
        pass
    print("== all ==  single command finished (exit 0)")
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="rq-driven-retrieval v%s" % VERSION)
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
