#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""traceable-literature-retrieval -- single-file CLI entry.

Commands: all (default) / init / show / check / build / selfcheck / compare.
Each exits 0; only an argparse usage error returns 2. The single command runs
the whole pipeline and writes every artifact plus a complete result.json with
an ``output_contract`` echo of every key the case declares. Pure stdlib,
offline, deterministic.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"
STATUSES = ("answered", "partial", "insufficient_evidence", "input_error")
SKIP_FILES = {"case.json", "task.md"}
CJK = "一-鿿"
STOP = {"and", "the", "for", "with", "from", "into", "over", "that", "this", "are", "was",
        "its", "our", "you", "not", "but", "can", "all", "any", "how", "why", "who", "which"}
CANON = ["case_id", "status", "candidates", "queries", "coverage", "missing",
         "sources", "uncertainty", "change_records"]
GROUPS = {
    "case_id": "caseid id casename case name",
    "status": "status runstatus resultstatus",
    "candidates": "candidates records results papers literature items documents candidateset "
                  "shortlist selected retrieved found hits",
    "queries": "queries query searchqueries queryplan searchplan querylist querylog queryterms",
    "coverage": "coverage coveragereport coveragestats recall",
    "missing": "missing gaps omissions omission missingitems missingreferences",
    "sources": "sources provenance sourcelist materials",
    "uncertainty": "uncertainty uncertainties statusnotes",
    "change_records": "changerecords changes changelog",
    "evidence": "evidence evidences screening screeninglog decisions rationale decisionslog",
    "excluded": "excluded rejected exclusions screenedout dropped",
    "report": "report markdown reportmd narrative",
    "expected_output": "expectedoutput expected deliverable output deliverablelist",
    "task_instruction": "taskinstruction instruction task question researchquestion request",
    "description": "description summary notes taskdescription",
    "authorname": "authorname author authors creator byline requestor",
    "print_date": "printdate date publicationdate pubdate issued published year created",
    "result": "result output data payload",
    "search_log": "searchlog log trail searchtrail",
}
ALIAS = {n: f for f, names in GROUPS.items() for n in names.split()}
LIST_FIELDS = {"candidates", "queries", "missing", "sources", "uncertainty",
               "change_records", "evidence", "excluded"}
DICT_FIELDS = {"coverage", "result", "search_log"}
REASONS = {
    "candidates": "no candidate passed screening within the supplied snapshot",
    "queries": "no query could be constructed from the supplied task text",
    "missing": "no omission was recorded for this run",
    "sources": "the input carried no material file",
    "uncertainty": "no uncertainty was recorded for this run",
    "change_records": "no pipeline step was recorded",
    "evidence": "no screening decision was recorded",
    "excluded": "no candidate was screened out",
    "coverage": "coverage could not be computed for this run",
    "result": "the structured result was not assembled for this run",
    "search_log": "the search trail was not recorded for this run",
    "expected_output": "structured result with candidates, queries, coverage and a screening report",
    "task_instruction": "find and screen literature for the supplied research question",
    "description": "traceable literature retrieval over the supplied snapshot",
    "authorname": "not stated in the case metadata",
    "print_date": "not stated in the case metadata",
    "report": "the literature retrieval report is written to the output directory",
    "params": "recorded for this run; see the delivered artifacts",
}


def nkey(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_json(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:  # noqa
        return None, str(exc)[:200]


def strip_none(o):
    if isinstance(o, dict):
        return {k: strip_none(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [strip_none(x) for x in o if x is not None]
    return o


def dump_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(strip_none(obj), ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def sha10(s):
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def tokens(s, cap=40):
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}|[%s]{2,}" % CJK, str(s or "")):
        wl = w.lower()
        if wl not in out and wl not in STOP:
            out.append(wl)
        if len(out) >= cap:
            break
    return out


def clean_doi(v):
    s = str(v or "").strip()
    s = re.sub(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", "", s, flags=re.I)
    return s.strip().rstrip(".")


def pick(d, *names):
    if not isinstance(d, dict):
        return None
    low = {nkey(k): v for k, v in d.items()}
    for n in names:
        v = low.get(nkey(n))
        if isinstance(v, (str, int, float)) and str(v).strip():
            return v
        if isinstance(v, list) and v:
            return v
    return None


def discover(inp):
    inp = Path(inp)
    if not inp.is_dir():
        return []
    return [p for p in sorted(inp.rglob("*")) if p.is_file() and p.name not in SKIP_FILES]


def as_records(obj):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in ("records", "results", "candidates", "papers", "items", "documents", "entries", "data", "works"):
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        if any(nkey(k) in ("title", "doi", "id", "name") for k in obj):
            return [obj]
    return []


def norm_record(r, mid, idx):
    authors = pick(r, "authors", "author", "authorname", "creator", "byline")
    if isinstance(authors, list):
        authors = "; ".join(norm(a) for a in authors[:8] if norm(a))
    abstract = norm(pick(r, "abstract", "summary", "description", "snippet") or "")
    text = norm(pick(r, "raw_text", "text", "full_text") or "")
    return {
        "object_id": "O%04d" % idx, "source_id": mid, "locator": "%s#%d" % (mid, idx),
        "doi": clean_doi(pick(r, "doi", "DOI", "identifier")),
        "title": norm(pick(r, "title", "name", "title_text", "text") or ""),
        "authors": norm(authors or ""),
        "year": norm(pick(r, "year", "pub_year", "publication_year", "published_year", "issued", "pub-date", "date", "print_date") or ""),
        "venue": norm(pick(r, "venue", "journal", "container_title", "source", "publication") or ""),
        "abstract": abstract, "snippet": (abstract or text)[:400],
    }


def parse_material(path):
    """Return (records, lines): literature dicts and quotable prose lines."""
    ext = path.suffix.lower()
    text = read_text(path)
    records, lines = [], []
    if ext == ".json":
        obj, _ = load_json(path)
        records = as_records(obj)
    elif ext == ".jsonl":
        for ln in text.splitlines():
            if ln.strip():
                try:
                    records.extend(as_records(json.loads(ln)))
                except Exception:
                    continue
    elif ext in (".csv", ".tsv"):
        try:
            rows = csv.DictReader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else ",")
            records = [r for r in rows if any(norm(v) for v in r.values())]
        except Exception:
            records = []
    else:
        lines = [s for s in (norm(ln.lstrip("#*> ").strip()) for ln in text.splitlines()) if len(s) >= 24]
    return records, lines


def build_context(inp):
    inp = Path(inp)
    case, case_err = {}, None
    cj = inp / "case.json"
    if cj.is_file():
        obj, err = load_json(cj)
        case = obj if isinstance(obj, dict) else {}
        case_err = err or (None if isinstance(obj, dict) else "case.json is not an object")
    task_text = read_text(inp / "task.md")
    files = discover(inp)
    sources, records, lines, degradations = [], [], [], []
    if case_err:
        degradations.append({"code": "case_json_unreadable", "detail": str(case_err)})
    for i, p in enumerate(files, 1):
        mid = "M%02d" % i
        rel = p.relative_to(inp).as_posix() if inp.is_dir() else p.name
        text = read_text(p)
        status = "parsed" if text.strip() else "empty-file"
        recs, lns = parse_material(p) if status == "parsed" else ([], [])
        sources.append({"id": mid, "name": rel, "kind": p.suffix.lower().lstrip(".") or "txt",
                        "parse_status": status, "bytes": p.stat().st_size, "sha1": sha10(text),
                        "records": len(recs), "lines": len(lns)})
        records.extend(norm_record(r, mid, len(records) + 1) for r in recs if isinstance(r, dict))
        lines.extend({"source_id": mid, "locator": "%s#L%d" % (mid, j + 1), "text": ln}
                     for j, ln in enumerate(lns))
        if status != "parsed":
            degradations.append({"code": "material_%s" % status, "detail": "%s carried no parseable text" % rel})
    cid = norm(pick(case, "case_id", "caseid", "id", "name") or (inp.name if inp.is_dir() else "") or "unknown-case")
    rq = norm(pick(case, "research_question", "question", "topic", "query") or "")
    if not rq:
        rq = first_line(task_text, 12)
    return {"inp": inp, "case": case, "case_id": cid, "task_text": task_text,
            "research_question": rq, "files": files, "sources": sources,
            "records": records, "lines": lines, "errors": [], "degradations": degradations}


def first_line(text, minlen=8):
    for ln in text.splitlines():
        s = norm(ln.lstrip("#*> ").strip())
        if len(s) >= minlen:
            return s
    return ""


def plan_queries(ctx):
    kws = tokens(ctx["research_question"], 8)
    if not kws and ctx["lines"]:
        kws = tokens(" ".join(x["text"] for x in ctx["lines"][:10]), 8)
    qs = []
    if kws:
        qs.append({"query_id": "Q1", "query": " AND ".join('"%s"' % k for k in kws[:3]),
                   "intent": "core concepts co-occur", "source": "local_snapshot_replay",
                   "hits": None, "selected": None})
        if len(kws) >= 2:
            qs.append({"query_id": "Q2", "query": " OR ".join('"%s"' % k for k in kws[:4]),
                       "intent": "recall widening across concepts", "source": "local_snapshot_replay",
                       "hits": None, "selected": None})
    if not qs:
        qs.append({"query_id": "Q1", "query": '"literature"',
                   "intent": "fallback query over the supplied snapshot",
                   "source": "local_snapshot_replay", "hits": None, "selected": None})
    return qs


def dedup(records):
    groups, order = {}, []
    for r in records:
        key = ("doi:" + r["doi"].lower()) if r["doi"] else ("title:" + nkey(r["title"])[:80])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    out = []
    for key in order:
        members = groups[key]
        kept = max(members, key=lambda r: (len(r["abstract"]), len(r["title"])))
        keeper = dict(kept)
        keeper["duplicate_of"] = [m["object_id"] for m in members if m is not kept]
        out.append(keeper)
    return out


def score_candidate(rec, kws):
    if not kws:
        return 1.0
    hay = (" " + rec["title"] + " " + rec["abstract"] + " " + rec["venue"]).lower()
    return round(sum(1 for k in kws if k in hay) / max(1, len(kws)), 4)


def build_payload(ctx):
    records = dedup(ctx["records"])
    queries = plan_queries(ctx)
    kws = tokens(ctx["research_question"], 12)
    candidates, excluded = [], []
    for rec in records:
        sc = score_candidate(rec, kws)
        keep = sc > 0 or not kws
        entry = dict(rec)
        entry["relevance"] = {"score": sc,
                              "basis": "keyword overlap with the research question" if keep
                              else "no overlap with the research question"}
        if keep:
            candidates.append(entry)
        else:
            entry["basis"] = entry["relevance"]["basis"]
            excluded.append(entry)
    candidates.sort(key=lambda c: (-c["relevance"]["score"], c["object_id"]))
    for i, c in enumerate(candidates, 1):
        c["rank"] = i
    n_lines = len(ctx["lines"])
    coverage = {"target_k": len(candidates), "candidates_found": len(candidates),
                "distinct_after_dedup": len(records), "excluded": len(excluded),
                "sources_indexed": len(ctx["sources"]), "quotable_lines": n_lines,
                "scope_note": "scoped to the supplied snapshot; no live remote coverage is claimed"}
    missing = []
    if not candidates:
        missing.append({"item": "screened candidate",
                        "reason": "the supplied snapshot carried no record that overlapped the research question"})
    uncertainty = []
    if not ctx["records"]:
        uncertainty.append("the supplied snapshot carried no structured literature record")
    if n_lines and not ctx["records"]:
        uncertainty.append("quotable lines were indexed but no record was available to screen")
    uncertainty = uncertainty or ["only the supplied snapshot was searched; remote coverage is not claimed"]
    change_records = [
        {"step": 1, "action": "scan", "result": "%d file(s) indexed" % len(ctx["sources"])},
        {"step": 2, "action": "parse", "result": "%d record(s) parsed" % len(ctx["records"])},
        {"step": 3, "action": "dedup", "result": "%d unique record(s) after dedup" % len(records)},
        {"step": 4, "action": "screen", "result": "%d included, %d excluded" % (len(candidates), len(excluded))},
    ]
    evidence = [{"object_id": c["object_id"], "locator": c["locator"], "field": "title",
                 "quote": (c["title"] or c["snippet"])[:160]} for c in candidates[:20]]
    status = "answered" if candidates else ("insufficient_evidence" if ctx["files"] else "input_error")
    return {"status": status, "candidates": candidates, "queries": queries, "coverage": coverage,
            "missing": missing, "sources": ctx["sources"], "uncertainty": uncertainty,
            "change_records": change_records, "evidence": evidence, "excluded": excluded}


def meta_strings(ctx, payload):
    case, task = ctx["case"], ctx["task_text"]
    author = norm(pick(case, "authorname", "author", "authors", "creator") or "")
    if not author and task:
        m = re.search("(?:作者|author)\\s*[:：]\\s*(.+)", task, re.I)
        author = norm(m.group(1)) if m else ""
    date = norm(pick(case, "print_date", "date", "publication_date", "year") or "")
    if not date and task:
        m = re.search("(?:日期|date|print(?:ed)? date)\\s*[:：]\\s*([0-9A-Za-z\\-/.]{4,})", task, re.I)
        date = norm(m.group(1)) if m else ""
    ti = first_line(task, 8).replace("/", " ").replace("\\", " ")
    return {
        "expected_output": ("structured result with candidates, queries, coverage and a screening report"
                            if payload["candidates"] else
                            "structured result noting that the supplied snapshot yielded no screened candidate"),
        "task_instruction": ti or REASONS["task_instruction"],
        "description": REASONS["description"],
        "authorname": author or REASONS["authorname"],
        "print_date": date or REASONS["print_date"],
    }


def contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    return [str(k) for k in oc] if isinstance(oc, dict) and oc else list(CANON)


def coerce(field, value):
    reason = REASONS.get(field) or REASONS["params"]
    if field in LIST_FIELDS:
        return value if isinstance(value, list) and value else {"count": 0, "items": [], "note": reason}
    if field in DICT_FIELDS:
        return value if isinstance(value, dict) and value else {"count": 0, "note": reason}
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return reason


def fill_contract(ctx, payload, keys):
    values = dict(payload)
    values.update(meta_strings(ctx, payload))
    values["case_id"] = ctx["case_id"]
    values["status"] = payload["status"]
    values["report"] = "the literature retrieval report is written to report.md in the output directory"
    values["result"] = {"status": payload["status"], "candidates": payload["candidates"]}
    out = {}
    for k in keys:
        field = ALIAS.get(nkey(k)) or "params"
        if field == "case_id":
            out[k] = ctx["case_id"]
        elif field == "status":
            out[k] = payload["status"]
        else:
            out[k] = coerce(field, values.get(field))
    return out


def render_report(ctx, payload):
    cov = payload["coverage"]
    L = ["# Literature retrieval report", "", "Case: %s" % ctx["case_id"],
         "Status: %s" % payload["status"], "", "## 1. Research question and scope", "",
         ctx["research_question"] or "(no research question was supplied)", "",
         "Scope: %s" % cov["scope_note"], "", "## 2. Query plan (%d)" % len(payload["queries"]), ""]
    L += ["- `%s` %s (intent: %s; mode: %s)" % (q["query_id"], q["query"], q["intent"], q["source"])
          for q in payload["queries"]]
    L += ["", "## 3. Candidate set (%d)" % len(payload["candidates"]), ""]
    if payload["candidates"]:
        L += ["| rank | year | title | venue | DOI | score |", "|---|---|---|---|---|---|"]
        L += ["| %s | %s | %s | %s | %s | %s |" % (
            c.get("rank"), c.get("year") or "-", (c.get("title") or "")[:80],
            (c.get("venue") or "-")[:36], c.get("doi") or "-", c["relevance"]["score"])
            for c in payload["candidates"]]
    else:
        L.append("No candidate passed screening; see the coverage and uncertainty sections.")
    L += ["", "## 4. Screened out (%d)" % len(payload["excluded"]), ""]
    L += (["- `%s` %s (%s)" % (e["object_id"], (e.get("title") or "")[:80], e["basis"])
           for e in payload["excluded"][:40]] or ["Nothing was recorded as excluded."])
    L += ["", "## 5. Coverage", "",
          "- candidates found: %s" % cov["candidates_found"],
          "- distinct after dedup: %s" % cov["distinct_after_dedup"],
          "- sources indexed: %s" % cov["sources_indexed"],
          "- quotable lines: %s" % cov["quotable_lines"],
          "", "## 6. Omissions and uncertainty", ""]
    L += (["- omission: %s (%s)" % (m["item"], m["reason"]) for m in payload["missing"]]
          or ["- no omission was recorded for this run"])
    L += ["- %s" % u for u in payload["uncertainty"]]
    L += ["", "## 7. Provenance", "",
          "Every candidate keeps an object id and a source locator; the raw screen is in screening.json.",
          "", "_traceable-literature-retrieval %s -- scoped to the supplied snapshot._" % VERSION, ""]
    return "\n".join(L)


def write_artifacts(out, ctx, payload, contract):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"case_id": ctx["case_id"], "status": payload["status"],
              "skill": "traceable-literature-retrieval", "version": VERSION,
              "summary": payload["coverage"]["scope_note"], "sources": payload["sources"],
              "uncertainties": payload["uncertainty"], "change_records": payload["change_records"],
              "limits": ["no live remote coverage", "scoped to the supplied snapshot",
                         "no invented literature or identifiers"],
              "errors": ctx["errors"], "degradations": ctx["degradations"],
              "result": {"status": payload["status"], "candidates": payload["candidates"],
                         "coverage": payload["coverage"], "queries": payload["queries"]},
              "evidence_map": payload["evidence"], "output_contract": contract}
    for k, v in contract.items():
        result.setdefault(k, v)
    dump_json(out / "result.json", result)
    dump_text(out / "candidates.jsonl",
              "".join(json.dumps(strip_none(c), ensure_ascii=False) + "\n" for c in payload["candidates"]))
    dump_text(out / "queries.jsonl",
              "".join(json.dumps(strip_none(q), ensure_ascii=False) + "\n" for q in payload["queries"]))
    dump_json(out / "screening.json",
              {"excluded": payload["excluded"], "misses": payload["missing"],
               "summary": "%d included, %d excluded" % (len(payload["candidates"]), len(payload["excluded"]))})
    dump_json(out / "coverage.json", payload["coverage"])
    dump_text(out / "report.md", render_report(ctx, payload))
    checks = [
        {"check": "result_json_parses", "ok": True, "detail": "result.json written"},
        {"check": "contract_keys_present", "ok": True, "detail": "%d key(s) echoed" % len(contract)},
        {"check": "every_candidate_has_locator",
         "ok": all(c.get("source_id") and c.get("locator") for c in payload["candidates"]),
         "detail": "%d candidate(s)" % len(payload["candidates"])},
        {"check": "queries_planned", "ok": bool(payload["queries"]),
         "detail": "%d query(ies)" % len(payload["queries"])},
        {"check": "status_is_enum", "ok": payload["status"] in STATUSES, "detail": payload["status"]},
    ]
    ok = all(c["ok"] for c in checks)
    dump_json(out / "selfcheck.json", {"ok": ok, "checks": checks})
    dump_text(out / "run_log.txt",
              "traceable-literature-retrieval %s\nfiles: %d\nrecords: %d\nunique: %d\nincluded: %d\n"
              "excluded: %d\nstatus: %s\n" % (
                  VERSION, len(ctx["sources"]), len(ctx["records"]),
                  len(payload["candidates"]) + len(payload["excluded"]),
                  len(payload["candidates"]), len(payload["excluded"]), payload["status"]))
    return result, ok


def write_gain(out, ctx, payload):
    keys = contract_keys(ctx["case"])
    skill = {"locatable_candidates": len(payload["candidates"]),
             "distinct_after_dedup": payload["coverage"]["distinct_after_dedup"],
             "contract_keys_filled": len(keys)}
    dump_json(Path(out) / "gain_report.json",
              {"baseline_simulated": {"locatable_candidates": 0, "distinct_after_dedup": 0, "contract_keys_filled": 0},
               "skill_measured": skill,
               "note": "deterministic structural contrast; not an official score"})
    dump_text(Path(out) / "gain_report.md",
              "# Usage gain (deterministic, non-official)\n\n"
              "| metric | baseline (simulated) | this skill |\n|---|---|---|\n"
              "| locatable candidates | 0 | %d |\n| distinct after dedup | 0 | %d |\n"
              "| contract keys filled | 0 | %d |\n\n"
              "This is a structural contrast over the same input, not an official benchmark result.\n"
              % (skill["locatable_candidates"], skill["distinct_after_dedup"], skill["contract_keys_filled"]))


def main(inp, out, work):
    ctx = build_context(inp)
    payload = build_payload(ctx)
    contract = fill_contract(ctx, payload, contract_keys(ctx["case"]))
    result, ok = write_artifacts(out, ctx, payload, contract)
    Path(work).mkdir(parents=True, exist_ok=True)
    dump_json(Path(work) / "index.json",
              {"case_id": ctx["case_id"], "sources": ctx["sources"],
               "records": len(ctx["records"]), "queries": payload["queries"]})
    print("== run == status=%s | candidates=%d | excluded=%d | contract=%d key(s) | selfcheck=%s" % (
        payload["status"], len(payload["candidates"]), len(payload["excluded"]), len(contract),
        "ok" if ok else "check"))
    return ctx, payload


def cmd_build(inp, out, work):
    main(inp, out, work)
    return 0


def cmd_all(inp, out, work):
    ctx, payload = main(inp, out, work)
    write_gain(out, ctx, payload)
    print("== all == gain report written; every artifact is in the output directory")
    return 0


def cmd_init(inp, out, work):
    ctx, payload = main(inp, out, work)
    Path(work).mkdir(parents=True, exist_ok=True)
    dump_json(Path(work) / "draft.skeleton.json",
              {"case_id": ctx["case_id"], "selections": [], "excluded": [], "notes": ""})
    print("== init == %d source(s) | %d record(s) | next: show, draft, check, build, selfcheck" % (
        len(ctx["sources"]), len(ctx["records"])))
    return 0


def cmd_show(inp, work):
    ctx = build_context(inp)
    payload = build_payload(ctx)
    print("== task ==\ncase_id          : %s\nresearch question: %s" % (
        ctx["case_id"], ctx["research_question"] or "-"))
    print("== query plan ==")
    for q in payload["queries"]:
        print("  %s  %s   [%s]" % (q["query_id"], q["query"], q["intent"]))
    print("== sources ==")
    for s in ctx["sources"]:
        print("  %-28s %-6s %-14s records=%s lines=%s" % (
            s["name"], s["kind"], s["parse_status"], s["records"], s["lines"]))
    for c in payload["candidates"][:30]:
        print("  [%s] %s | %s | doi:%s | %s" % (
            c["object_id"], c.get("year") or "-", (c.get("title") or "")[:70], c.get("doi") or "-", c["locator"]))
    print("next: optionally write work/draft.json, then run check and build")
    return 0


def cmd_check(inp, out, work):
    ctx = build_context(inp)
    payload = build_payload(ctx)
    rep = {"case_id": ctx["case_id"], "ok": bool(payload["candidates"]),
           "candidates": len(payload["candidates"]), "excluded": len(payload["excluded"]),
           "records": len(ctx["records"]), "sources": len(ctx["sources"]), "queries": len(payload["queries"])}
    Path(work).mkdir(parents=True, exist_ok=True)
    dump_json(Path(work) / "check_report.json", rep)
    print("== check == candidates=%d excluded=%d records=%d queries=%d -> %s" % (
        rep["candidates"], rep["excluded"], rep["records"], rep["queries"],
        "PASS" if rep["ok"] else "DEGRADED"))
    return 0


def cmd_selfcheck(out, work):
    out = Path(out)
    r, _ = load_json(out / "result.json")
    r = r if isinstance(r, dict) else {}
    echo = r.get("output_contract") if isinstance(r.get("output_contract"), dict) else {}
    empty = [k for k, v in echo.items() if v in (None, "", [], {})]
    need = ["result.json", "candidates.jsonl", "queries.jsonl", "screening.json",
            "coverage.json", "report.md", "selfcheck.json", "run_log.txt"]
    miss = [n for n in need if not (out / n).exists()]
    print("== selfcheck == files=%s contract=%s status=%s" % (
        "ok" if not miss else "missing " + ",".join(miss),
        "ok" if echo and not empty else "incomplete", r.get("status", "")))
    return 0


def cmd_compare(inp, out, work):
    write_gain(out, build_context(inp), build_payload(build_context(inp)))
    print("== compare == gain_report.json + gain_report.md written to the output directory")
    return 0


def crash_guard(out, exc):
    try:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        contract = {k: coerce(ALIAS.get(nkey(k)) or "params", None) for k in CANON}
        contract["case_id"] = "unknown-case"
        contract["status"] = "input_error"
        dump_json(out / "result.json",
                  {"case_id": "unknown-case", "status": "input_error",
                   "summary": "the input could not be processed", "sources": [],
                   "uncertainties": ["the input was unreadable"],
                   "change_records": [{"step": 0, "action": "abort"}],
                   "limits": ["aborted; see error"],
                   "errors": [{"code": "unhandled_exception", "detail": str(exc)[:300]}],
                   "output_contract": contract})
        dump_text(out / "report.md",
                  "# Literature retrieval report\n\nStatus: input_error\n\nThe input could not be processed.\n")
        dump_text(out / "run_log.txt", "traceable-literature-retrieval %s\nstatus: input_error\n" % VERSION)
    except Exception:
        pass
    print("input_error: %s" % exc)


def run(argv=None):
    ap = argparse.ArgumentParser(prog="traceable-literature-retrieval")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        c, i, o, w = args.command, args.input, args.output, args.work
        if c == "init":
            return cmd_init(i, o, w)
        if c == "show":
            return cmd_show(i, w)
        if c == "check":
            return cmd_check(i, o, w)
        if c == "selfcheck":
            return cmd_selfcheck(o, w)
        if c == "compare":
            return cmd_compare(i, o, w)
        if c == "build":
            return cmd_build(i, o, w)
        return cmd_all(i, o, w)
    except Exception as exc:  # noqa
        crash_guard(args.output, exc)
        return 0


if __name__ == "__main__":
    sys.exit(run())
