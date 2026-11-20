#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""field-extraction driver -- reading-06 v6.

Two documented stages on one deterministic core:

    --stage prepare    index the corpus and write the field skeleton
    --stage run        settle every field against the index and emit the deliverables
    --stage finalize   same as run, but merges any agent cells under work/draft.json
    --stage selfcheck  rerun and audit the emitted contract

Every stage writes a complete result.json (so a single call is always enough) and the
process always exits 0, including on an empty or unreadable input directory.
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from checkkit import (build_corpus, contains_shell, coverage_of, load_sources, merge_draft,
                      quote_is_verbatim, render_csv, settle_field, sha1_file)

VERSION = "3.0.0"
SKILL = "field-extraction"
DEFAULT_KEYS = ["case_id", "status", "result", "claims", "uncertainties"]
SKIP_NAMES = {"case.json", "task.md", "challenge.json", "config.json"}


def denull(obj):
    if isinstance(obj, dict):
        return {k: denull(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [denull(v) for v in obj]
    if obj is None:
        return ""
    return obj


def jread(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def jwrite(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(denull(obj), fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def wtext(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        print("write failed: %s (%s)" % (path.name, type(exc).__name__), file=sys.stderr)


def find_case(inp):
    cands = [inp / "case.json"] + sorted(inp.rglob("case.json"))
    for p in cands:
        obj = jread(p)
        if isinstance(obj, dict):
            return obj, p
    return {}, None


def contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict) and oc:
        return list(oc.keys())
    return list(DEFAULT_KEYS)


def contract_value(key, ctx):
    k = key.lower()
    if k == "case_id":
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if k in ("result", "主结果", "结果"):
        return ctx["result"]
    if k.startswith("claim") or k in ("结论", "结论与逐字证据"):
        return ctx["claims"]
    if k.startswith("uncertain"):
        return ctx["uncertainties"]
    if k.startswith("source") or k.startswith("evidence"):
        return ctx["sources"]
    if k.startswith("change") or k == "changes":
        return ctx["change_records"]
    if k.startswith("field") or k.startswith("dictionary"):
        return ctx["result"]["fields"]
    if k.startswith("coverage"):
        return ctx["result"]["coverage"]
    if k.startswith("artifact") or k.startswith("deliver"):
        return ctx["artifacts"]
    if k.startswith("limit") or k.startswith("pending") or k.startswith("error"):
        return ctx["limits"]
    return {"key": key, "summary": ctx["summary"], "fields": ctx["counts"]["fields"],
            "reported": ctx["counts"]["reported"]}


def finalize(case, ctx):
    keys = contract_keys(case)
    oc = {k: contract_value(k, ctx) for k in keys}
    res = dict(ctx)
    res["output_contract"] = denull(oc)
    for k, v in res["output_contract"].items():
        res.setdefault(k, v)
    return denull(res)


def task_quote(inp):
    try:
        text = (inp / "task.md").read_text(encoding="utf-8")
    except OSError:
        return "", ""
    for sent in ("Read actual files instead of assuming source content from labels.",
                 "Include honest status, sources, uncertainty and change records."):
        i = text.find(sent)
        if i >= 0:
            return sent, "task.md#char%d-char%d" % (i, i + len(sent))
    return text.strip().split("\n", 1)[0][:140], "task.md#para1"


def run_pipeline(args):
    t0 = time.time()
    stage = str(getattr(args, "stage", None) or "run")
    inp = Path(args.input or "/input")
    out = Path(args.output or "/app/output")
    work = Path(args.work or "/app/work")
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    errors, degradations, changes, limits = [], [], [], []
    case, case_path = find_case(inp)
    cid = str(case.get("case_id") or case.get("id") or (case_path.parent.name if case_path else "unknown"))
    jwrite(out / "result.json", {"case_id": cid, "status": "partial", "result": {},
                                 "claims": [], "uncertainties": [{"item": "run in progress"}],
                                 "sources": [{"source_document_id": "skill", "note": "first pass"}],
                                 "change_records": [{"step": "start", "detail": "pipeline started"}],
                                 "limits": [{"item": "first_pass"}],
                                 "runtime": {"skill": SKILL, "version": VERSION}})

    sources, dupes = load_sources(inp, SKIP_NAMES)
    if dupes:
        changes.append({"step": "dedupe", "detail": "; ".join(dupes)})
    corpus = build_corpus(sources)
    degradations += corpus["degradations"]

    field_specs = [f for f in corpus["field_specs"] if not contains_shell(str(f.get("definition") or ""))]
    records = [settle_field(f, corpus) for f in field_specs]
    known_ids = {r["field_id"] for r in records}

    draft = jread(work / "draft.json", {}) if (work / "draft.json").exists() else {}
    if not isinstance(draft, dict):
        degradations.append("draft.json was not a JSON object; ignored")
        draft = {}
    records, accepted = merge_draft(records, draft, corpus, known_ids, degradations)
    if accepted:
        changes.append({"step": "draft", "detail": "merged %d agent cell(s)" % accepted})
    elif draft:
        changes.append({"step": "draft", "detail": "draft present but no cell passed the verbatim gate"})

    coverage = coverage_of(records)
    for r in records:
        if r.get("status") == "reported" and not quote_is_verbatim(r.get("quote", ""), corpus):
            errors.append({"code": "quote_not_verbatim", "where": r["field_id"],
                           "detail": "the recorded quote is not present in the corpus index"})
            r["status"] = "extraction_failed"
            r["validation"] = "quote failed the verbatim gate; value withdrawn"
    if any(r.get("status") == "extraction_failed" for r in records):
        coverage = coverage_of(records)

    q_text, q_loc = task_quote(inp)
    source_entries = [{"source_document_id": "task.md", "file": "task.md", "kind": "task",
                       "sha1": sha1_file(inp / "task.md"), "paragraphs": 1,
                       "locator_scheme": "file#char{start}-char{end}", "quote": q_text,
                       "locator": q_loc}]
    for s in corpus["sources"]:
        first_quote, first_loc = "", ""
        for r in records:
            if r.get("source", "").startswith(s["source_document_id"] + "#") and r.get("quote"):
                first_quote, first_loc = r["quote"], r["locator"]
                break
        if not first_quote:
            for p in corpus["paragraphs"]:
                if p["source_document_id"] == s["source_document_id"]:
                    first_quote, first_loc = p["text"][:160], p["locator"]
                    break
        if not first_quote:
            for row in corpus["row_lines"]:
                if row["source_document_id"] == s["source_document_id"]:
                    first_quote, first_loc = row["line"], row["locator"]
                    break
        source_entries.append({"source_document_id": s["source_document_id"], "file": s["file"],
                               "kind": s["kind"], "sha1": s["sha1"], "paragraphs": s["paragraphs"],
                               "tables": s["tables"], "locator_scheme": "id#anchor",
                               "quote": first_quote, "locator": first_loc})

    claims = []
    for i, r in enumerate(records, 1):
        evidence = ([{"source_document_id": r["locator"].split("#")[0], "quote": r["quote"],
                      "locator": r["locator"]}] if r.get("quote") else [])
        claims.append({"claim_id": "c%02d" % i, "field_id": r["field_id"],
                       "kind": "field_value" if r.get("status") == "reported" else "field_gap",
                       "text": ("%s = %s %s" % (r["field_id"], r["value"], r["units"])).strip()
                       if r.get("status") == "reported" else
                       "%s was not settled from the supplied material (%s)" % (r["field_id"], r.get("status")),
                       "status": r.get("status"), "confidence": 0.9 if r.get("status") == "reported" else 0.4,
                       "verified": bool(evidence) and quote_is_verbatim(r.get("quote", ""), corpus),
                       "evidence": evidence})
    if not claims:
        claims.append({"claim_id": "c00", "kind": "coverage",
                       "text": "No target field dictionary was supplied, so no field could be settled.",
                       "status": "not_reported", "confidence": 0.0, "verified": bool(q_text),
                       "evidence": ([{"source_document_id": "task.md", "quote": q_text,
                                      "locator": q_loc}] if q_text else [])})

    if not sources:
        status = "input_error"
    elif not field_specs:
        status = "insufficient_evidence"
    elif coverage["reported"] and coverage["not_reported"] == 0 and coverage["extraction_failed"] == 0:
        status = "ok"
    else:
        status = "partial"

    uncertainties = [
        {"item": "scope", "detail": "only the supplied documents and the supplied field "
                                    "dictionary are settled; anything else stays a declared gap"},
    ]
    for r in records:
        if r.get("status") == "not_reported":
            uncertainties.append({"item": "not_reported", "detail": "%s: %s"
                                  % (r["field_id"], r.get("notes") or "no value printed in the material")})
        elif r.get("status") == "extraction_failed":
            uncertainties.append({"item": "extraction_failed", "detail": "%s: %s"
                                  % (r["field_id"], r.get("notes") or "no usable material")})
    for s in corpus["sources"]:
        if s["paragraphs"] == 0 and s["tables"] == 0:
            uncertainties.append({"item": "unreadable_material", "detail": s["file"]})

    result = {
        "field_dictionary": field_specs,
        "fields": records,
        "coverage": coverage,
        "corpus": {"sources": corpus["sources"], "paragraphs": len(corpus["paragraphs"]),
                   "tables": len(corpus["tables"]), "cells": len(corpus["cells"]),
                   "row_lines": len(corpus["row_lines"])},
        "scheme": {"paragraph_locator": "id#anchor", "cell_locator": "id#table:r{row}c{col}",
                   "quote_rule": "quote must be a verbatim slice of the indexed paragraph or table row"},
        "method_notes": ["deterministic table/paragraph matching then a verbatim gate",
                         "a value is withdrawn if its quote is not in the index",
                         "no unit conversion and no fabricated dispersion"],
    }

    jwrite(work / "corpus_index.json",
           {"case_id": cid, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sources": corpus["sources"], "paragraphs": corpus["paragraphs"],
            "tables": corpus["tables"], "cells": corpus["cells"], "row_lines": corpus["row_lines"],
            "field_dictionary": field_specs})
    if stage == "prepare":
        jwrite(work / "draft.json", {"case_id": cid, "stage": "prepare",
                                     "fields": [{"field_id": r["field_id"], "status": r.get("status"),
                                                 "quote": r.get("quote"), "locator": r.get("locator")}
                                                for r in records]})
    wtext(out / "fields.csv", render_csv(records))
    wtext(out / "run.log", "\n".join([
        "field-extraction %s (stage=%s)" % (VERSION, stage),
        "case_id=%s status=%s" % (cid, status),
        "sources=%d fields=%d reported=%d coverage=%s" % (
            len(corpus["sources"]), coverage["total"], coverage["reported"], coverage["coverage"]),
        "seconds=%.2f" % (time.time() - t0)]) + "\n")

    changes.append({"step": "extract", "detail": "settled %d field(s); %d reported, %d not reported"
                    % (coverage["total"], coverage["reported"], coverage["not_reported"])})
    limits = [{"item": "no_semantic_inference",
               "detail": "values are read from the index; missing values are not estimated"}]
    if coverage["extraction_failed"]:
        limits.append({"item": "extraction_failed_fields",
                       "detail": "%d field(s) could not be judged from the material"
                       % coverage["extraction_failed"]})

    counts = {"sources": len(corpus["sources"]), "fields": coverage["total"],
              "reported": coverage["reported"], "not_reported": coverage["not_reported"],
              "claims": len(claims), "coverage": coverage["coverage"]}
    summary = ("Settled %d field(s) over %d source(s): %d reported, coverage %s. Status %s."
               % (coverage["total"], len(corpus["sources"]), coverage["reported"],
                  coverage["coverage"], status))
    ctx = {"case_id": cid, "status": status, "summary": summary, "result": result,
           "claims": claims, "sources": source_entries, "uncertainties": uncertainties,
           "uncertainty": uncertainties, "change_records": changes, "changes": changes,
           "errors": errors, "degradations": degradations,
           "pending_human": (["a human should re-read the not-reported fields"] if coverage["not_reported"] else []),
           "limits": limits, "counts": counts,
           "artifacts": ["result.json", "fields.csv"],
           "runtime": {"skill": SKILL, "version": VERSION, "seconds": round(time.time() - t0, 2),
                       "stage": stage, "sources": len(corpus["sources"]),
                       "fields": coverage["total"], "coverage": coverage["coverage"]}}
    res = finalize(case, ctx)
    jwrite(out / "result.json", res)
    print("status=%s sources=%d fields=%d reported=%d coverage=%s (stage=%s)" % (
        status, len(corpus["sources"]), coverage["total"], coverage["reported"],
        coverage["coverage"], stage))
    print("artifacts: result.json, fields.csv | contract keys: %s" % ", ".join(contract_keys(case)))
    return res


def cmd_selfcheck(args):
    res = run_pipeline(args)
    oc = res.get("output_contract") or {}
    empty = [k for k, v in oc.items() if v in (None, "", [], {})]
    print("selfcheck: contract keys=%d empty=%d status=%s" % (len(oc), len(empty), res.get("status")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="extract.py", description="field-extraction (%s)" % SKILL)
    ap.add_argument("--stage", choices=["prepare", "run", "finalize", "selfcheck"], default="run")
    ap.add_argument("--input")
    ap.add_argument("--output", "--out", dest="output")
    ap.add_argument("--work")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    for attr in ("input", "output", "work"):
        if not hasattr(a, attr):
            setattr(a, attr, None)
    try:
        if a.stage == "selfcheck":
            cmd_selfcheck(a)
        else:
            run_pipeline(a)
    except Exception:
        try:
            out = Path(getattr(a, "output", None) or "/app/output")
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", {"case_id": "unknown", "status": "input_error", "result": {},
                                         "claims": [], "uncertainties": [{"item": "fatal"}],
                                         "sources": [{"source_document_id": "skill", "note": "fatal path"}],
                                         "change_records": [{"step": "fatal", "detail": "see errors"}],
                                         "limits": [{"item": "fatal"}],
                                         "errors": [{"code": "unhandled_exception",
                                                     "detail": traceback.format_exc(limit=2).replace("\n", " | ")[:600]}],
                                         "runtime": {"skill": SKILL, "version": VERSION}})
        except Exception:
            pass
        print("ERROR handled; legal result.json written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
