#!/usr/bin/env python3
"""multi-document comparison driver -- reading-04 v6 (entry point).

One deterministic pass reads the workorder + every corpus document, anchors each
document as locator-bearing paragraphs, then renders a per-cell comparison matrix,
a comparability test and an agreement/synthesis verdict set.

    build      full flow (discover -> anchor -> matrix -> render -> result.json)
    show       print indexed paragraphs with their locators
    check      rerun the full flow and validate the agent draft against the corpus
    selfcheck  rerun the full flow and audit the output_contract shape

Every subcommand rewrites a complete /app/output/result.json and exits 0 on all
paths (empty, unreadable or malformed input included). Standard library only;
offline; paths resolved from __file__, never from the current directory.
"""
import argparse
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from readkit import (GEN, VERSION, TEXT_EXT, build_agreement, build_claims, build_comparability,
                     contract_keys, extract_doc, fill_cells, finalize, find_case, find_workorder,
                     jread, jwrite, kind_of, normalize_draft, sha, validate, wo_dims, wo_fields,
                     wo_forbidden, wo_papers, write_artifacts)


def paths(a):
    return Path(a.input or "/input"), Path(a.output or "/app/output"), Path(a.work or "/app/work")


def run_pipeline(a):
    t0 = time.time()
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    errors, degradations, changes, pending = [], [], [], []
    case, case_path = find_case(inp, errors)
    cid = str(case.get("case_id") or case.get("id") or (case_path.parent.name if case_path else "unknown"))
    jwrite(out / "result.json", {"case_id": cid, "status": "partial", "result": {}, "claims": [],
                                 "uncertainties": [{"item": "run in progress"}],
                                 "note": "legal first-pass result", "runtime": {"skill": GEN, "version": VERSION}})
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    skip = ("task.md", "case.json")
    cand = [p for p in files if (p.suffix.lower() in TEXT_EXT or kind_of(p) in ("pdf", "docx"))
            and p.name.lower() not in skip and "workorder" not in p.name.lower()]
    seen_hash, materials, dupes = {}, [], []
    for p in cand:
        h = sha(p)
        if h in seen_hash:
            dupes.append("%s duplicates %s; the earlier copy is compared" % (p.name, Path(seen_hash[h]).name))
            continue
        seen_hash[h] = str(p)
        materials.append(p)
    wo, wo_src = find_workorder(case, files)
    fields = wo_fields(wo)
    docs = {}
    for i, p in enumerate(materials):
        try:
            d = extract_doc(p)
        except Exception as e:
            errors.append({"code": "extract_failed", "detail": "%s: %r" % (p.name, e)})
            d = {"kind": kind_of(p), "engine": "failed",
                 "paras": [{"locator": "p1#para1", "page": "p1", "text": ""}], "text": "", "quality": 0.0,
                 "notes": ["extraction failed"]}
        d["filename"] = p.name
        d["path"] = str(p)
        degradations += ["%s: %s" % (p.name, n) for n in d.get("notes") or []]
        docs["D%d" % (i + 1)] = d
    papers = wo_papers(wo)
    for wp in papers:
        b = Path(wp.get("file") or "").name.lower()
        m = next((d for d, v in docs.items() if b and (b in v["filename"].lower() or v["filename"].lower() in b)), None)
        if m:
            wp["resolved_doc_id"] = m
    for d, v in docs.items():
        v["doc_id"] = next((p["doc_id"] for p in papers if p.get("resolved_doc_id") == d), d)
    jwrite(work / "index.json", {"case_id": cid, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "workorder_source": wo_src,
                                 "docs": {v["doc_id"]: {"filename": v["filename"], "kind": v["kind"],
                                                        "engine": v["engine"], "locator_scheme": "p{page}#para{n}",
                                                        "n_paras": len(v["paras"])} for v in docs.values()},
                                 "paras": {v["doc_id"]: v["paras"] for v in docs.values()},
                                 "workorder": {"question": str(wo.get("research_question") or wo.get("question") or ""),
                                               "fields": fields, "dimensions": wo_dims(wo), "papers": papers}})
    draft = {}
    if (work / "draft.json").exists():
        try:
            draft = jread(work / "draft.json")
            if not isinstance(draft, dict):
                draft = {}
                degradations.append("draft.json was not a JSON object; ignored")
        except Exception as e:
            degradations.append("draft.json unreadable (%s); deterministic extraction used" % type(e).__name__)
    cells = normalize_draft(draft, docs, fields)
    if cells:
        changes.append({"step": "draft", "note": "merged %d agent cell(s) from work/draft.json" % len(cells)})
    else:
        changes.append({"step": "auto", "note": "no usable draft: deterministic best-effort extraction used"})
        pending.append("review the auto-extracted cells and overwrite them from work/draft.json")
    if dupes:
        changes.append({"step": "dedupe", "note": "; ".join(dupes)})
    cells = fill_cells(docs, fields, cells)
    dims = wo_dims(wo)
    comparability = build_comparability(docs, fields, cells, dims, wo_forbidden(wo))
    claims = build_claims(docs, fields, cells, comparability)
    agreement = build_agreement(docs, fields, cells, claims)
    rep = validate(cells, docs, fields, comparability, agreement)
    if not claims:
        src = next(({"source_document_id": v["doc_id"], "quote": v["paras"][0]["text"][:160],
                     "locator": v["paras"][0]["locator"]} for v in docs.values() if v["text"]), None)
        claims = [{"claim_id": "c00", "kind": "coverage", "field_id": "",
                   "text": "No field value could be anchored from the supplied paragraphs; the matrix stays unreported.",
                   "verdict": "insufficient", "evidence": [src] if src else []}]
    result = {"question": str(wo.get("research_question") or wo.get("question") or ""), "dimensions": dims,
              "fields": fields, "papers": papers,
              "matrix_preview": [{"source_document_id": c["doc_id"], "field_id": c["field_id"], "value": c["value"],
                                  "unit": c["unit"], "status": c["status"], "locator": c["locator"]} for c in cells],
              "comparability": comparability, "agreement": agreement,
              "forbidden_pooling": wo_forbidden(wo), "counts": rep["counts"]}
    if not docs:
        status = "input_error"
        pending.append("no readable corpus document was found under the input directory")
    elif rep["counts"]["reported"] and not rep["errors"] and not degradations:
        status = "ok"
    elif rep["counts"]["reported"]:
        status = "partial"
    else:
        status = "insufficient_evidence"
    uncertainties = [{"item": "counts", "detail": rep["counts"]},
                     {"item": "scope",
                      "detail": "only the supplied documents and fields are compared; unlisted material is a declared gap"}]
    for u in (draft.get("uncertainty") or draft.get("uncertainties") or []) if isinstance(draft, dict) else []:
        uncertainties.append(u if isinstance(u, dict) else {"item": str(u)})
    limits = [{"item": "no_pooling_across_unlike_conditions", "detail": "non-blocking limitation"}] \
        if wo_forbidden(wo) else \
        [{"item": "auto_extraction", "detail": "values are deterministic best-effort; verify quotes against locator"}]
    summary = ("Comparison of %d document(s) over %d field(s): %d cell(s), %d reported, coverage %s. "
               "Comparability tested on %d axis(es); agreement verdict %s." % (
                   rep["counts"]["documents"], rep["counts"]["fields"], rep["counts"]["cells"],
                   rep["counts"]["reported"], rep["counts"]["coverage"], len(comparability),
                   agreement["overall"]))
    ctx = {"case_id": cid, "status": status, "summary": summary, "result": result, "claims": claims,
           "sources": [{"source_document_id": v["doc_id"], "file": v["filename"], "kind": v["kind"],
                        "engine": v["engine"], "locator_scheme": "p{page}#para{n}"} for v in docs.values()],
           "uncertainties": uncertainties, "errors": rep["errors"] + errors, "degradations": degradations,
           "changes": changes, "pending_human": pending, "limits": limits, "counts": rep["counts"],
           "fields": fields, "papers": papers, "comparability": comparability, "agreement": agreement, "cells": cells,
           "artifacts": ["comparison_matrix.csv", "comparison_table.md", "evidence_cards.jsonl", "result.json"],
           "runtime": {"skill": GEN, "version": VERSION, "seconds": round(time.time() - t0, 2),
                       "documents": len(docs), "fields": len(fields), "cells": len(cells),
                       "reported": rep["counts"]["reported"], "quote_pass_rate": rep["counts"]["quote_pass_rate"]}}
    write_artifacts(out, ctx)
    res = finalize(case, ctx)
    jwrite(out / "result.json", res)
    print("status=%s docs=%d fields=%d cells=%d reported=%d coverage=%s quote_pass=%s" % (
        status, len(docs), len(fields), len(cells), rep["counts"]["reported"], rep["counts"]["coverage"],
        rep["counts"]["quote_pass_rate"]))
    print("artifacts:", ", ".join(ctx["artifacts"]), "| contract:", ", ".join(contract_keys(case)))
    if rep["errors"]:
        print("draft issues:", "; ".join("%s@%s" % (e["code"], e["where"]) for e in rep["errors"][:6]))
    return res


def cmd_show(a):
    _, _, work = paths(a)
    idx = {}
    if (work / "index.json").exists():
        try:
            idx = jread(work / "index.json")
        except Exception:
            idx = {}
    paras = idx.get("paras") or {}
    if a.doc and a.doc in paras:
        import re as _re
        m = _re.match(r"^(\d+)\s*[:\-]\s*(\d+)$", str(a.paras or ""))
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, len(paras[a.doc]))
        for p in paras[a.doc][lo - 1:hi]:
            print("[%s %s] %s" % (a.doc, p["locator"], p["text"][:1200]))
        print("-- %s: %d paragraph(s), showed %d..%d" % (a.doc, len(paras[a.doc]), lo, min(hi, len(paras[a.doc]))))
    elif paras:
        for d, ps in paras.items():
            print("%s | %d para | first: %s" % (d, len(ps), ps[0]["locator"] if ps else ""))
    else:
        print("(no index yet; run `main.py build` first)")
    return 0


def cmd_check(a):
    res = run_pipeline(a)
    print("check: %s | errors=%d | quoted_ok=%s" % (res.get("status"), len(res.get("errors") or []),
                                                    res.get("counts", {}).get("quote_pass_rate")))
    return 0


def cmd_selfcheck(a):
    res = run_pipeline(a)
    oc = res.get("output_contract") or {}
    missing = [k for k, v in oc.items() if v in (None, "", [], {})]
    print("selfcheck: keys=%d missing=%d empty=%d status=%s" % (len(oc), len(missing), len(missing), res.get("status")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="multi-document comparison (%s)" % GEN)
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (("build", "full comparison flow"), ("show", "print paragraphs with locators"),
                           ("check", "rerun and validate the agent draft"),
                           ("selfcheck", "rerun and audit the contract")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--input")
        sp.add_argument("--output", "--out", dest="output")
        sp.add_argument("--work")
        if name == "show":
            sp.add_argument("--doc")
            sp.add_argument("--paras")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if not getattr(a, "cmd", None):
        a.cmd = "build"
    for attr in ("input", "output", "work", "doc", "paras"):
        if not hasattr(a, attr):
            setattr(a, attr, None)
    try:
        {"build": run_pipeline, "check": cmd_check, "selfcheck": cmd_selfcheck, "show": cmd_show}[a.cmd](a)
    except Exception:
        try:
            _, out, _ = paths(a)
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", {"case_id": "unknown", "status": "input_error", "result": {}, "claims": [],
                                         "uncertainties": [{"item": "fatal", "detail": "see errors"}],
                                         "errors": [{"code": "unhandled_exception",
                                                     "detail": traceback.format_exc(limit=2).replace("\n", " | ")[:700]}],
                                         "runtime": {"skill": GEN, "version": VERSION}})
        except Exception:
            pass
        print("ERROR handled; legal result.json written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
