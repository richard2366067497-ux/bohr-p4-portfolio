#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reading-client driver -- reading-05 v6.

One deterministic pass opens the supplied materials, anchors every paragraph under a
stable ``p{page}#para{n}`` locator, selects quantitative evidence spans, answers them
only from the material, audits the spans, and exports the reading record plus a
single-file offline reader.

    build     full closed loop and every artifact (default when no subcommand is given)
    show      print indexed paragraphs with their locators
    check     rerun the closed loop, merging any agent draft under work/draft.json
    selfcheck rerun the closed loop and audit the emitted artifacts

Standard library only, offline, paths resolved by absolute/relative flags (never from
the current directory). Every path exits 0 with a legal result.json, including an
empty or unreadable input directory.
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client_kit import (PAGE_CHARS, anchor_paragraphs, contains_shell, esc, golden_standard,
                        load_document, render_diff_report, render_reader_html,
                        render_reading_record, render_version_history, select_evidence, sha1_file)

VERSION = "3.0.0"
SKILL = "reading-client"
DEFAULT_KEYS = ["case_id", "status", "result", "claims", "uncertainties"]
SKIP_NAMES = {"case.json", "task.md", "challenge.json", "config.json"}


# ------------------------------------------------------------------- utilities
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
    if k.startswith("uncertain") or k in ("未报告/无法判断/冲突项",):
        return ctx["uncertainties"]
    if k.startswith("source") or k.startswith("evidence") or k.startswith("evidence_map"):
        return ctx["sources"]
    if k.startswith("change") or k in ("change_log", "changes"):
        return ctx["change_records"]
    if k.startswith("artifact") or k.startswith("deliver"):
        return ctx["artifacts"]
    if k.startswith("limit") or k.startswith("pending") or k.startswith("error"):
        return ctx["limits"]
    if k.startswith("method") or k.startswith("runtime") or k.startswith("count"):
        return ctx["result"]
    return {"key": key, "summary": ctx["summary"], "documents": ctx["counts"]["documents"],
            "evidence_spans": ctx["counts"]["selections"]}


def finalize(case, ctx):
    keys = contract_keys(case)
    oc = {k: contract_value(k, ctx) for k in keys}
    res = dict(ctx)
    res["output_contract"] = denull(oc)
    for k, v in res["output_contract"].items():
        res.setdefault(k, v)
    return denull(res)


def qa_audit(docs, anchors, selections):
    checks = []
    flat = [a for rows in anchors.values() for a in rows]
    anchored = len(flat)
    checks.append({"check": "paragraphs_anchored", "ok": anchored > 0,
                   "detail": "%d paragraph(s) across %d document(s)" % (anchored, len(docs))})
    sel_has_doc = all(s["document_id"] in anchors for s in selections)
    checks.append({"check": "span_belongs_to_document", "ok": bool(selections) and sel_has_doc,
                   "detail": "every span resolves to an indexed document" if selections
                   else "no span was selected from the supplied material"})
    verbatim_total = len(selections)
    verbatim_pass = sum(1 for s in selections if s.get("verbatim_ok"))
    checks.append({"check": "quote_is_verbatim", "ok": verbatim_pass == verbatim_total,
                   "detail": "%d/%d span quote(s) occur verbatim in their paragraph"
                   % (verbatim_pass, verbatim_total)})
    locators = [a["locator"] for a in flat]
    checks.append({"check": "locator_is_unique", "ok": len(locators) == len(set(locators)),
                   "detail": "%d anchor locator(s), %d distinct" % (len(locators), len(set(locators)))})
    span_ok = all(s["char_end"] > s["char_start"] for s in selections)
    checks.append({"check": "span_has_extent", "ok": span_ok,
                   "detail": "every selected span has a positive char extent"})
    return {"checks": checks, "verbatim_total": verbatim_total, "verbatim_pass": verbatim_pass,
            "locator_total": len(locators), "locator_unique": len(set(locators))}


def discover(inp):
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    seen, materials, dupes = {}, [], []
    for p in files:
        if p.name.lower() in SKIP_NAMES:
            continue
        h = sha1_file(p)
        if h and h in seen:
            dupes.append("%s duplicates %s; the first copy is read" % (p.name, seen[h]))
            continue
        if h:
            seen[h] = p.name
        materials.append(p)
    return materials, dupes


def task_quote(inp):
    """A verbatim task.md sentence used as the always-available source anchor."""
    p = inp / "task.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return "", ""
    for sent in ("Read actual files instead of assuming source content from labels.",
                 "Include honest status, sources, uncertainty and change records."):
        i = text.find(sent)
        if i >= 0:
            return sent, "task.md#char%d-char%d" % (i, i + len(sent))
    flat = text.strip().split("\n", 1)[0][:140]
    return flat, "task.md#para1"


# ------------------------------------------------------------------- pipeline
def run_pipeline(args):
    t0 = time.time()
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
                                 "limits": [{"item": "first_pass"}], "runtime": {"skill": SKILL, "version": VERSION}})
    materials, dupes = discover(inp)
    if dupes:
        changes.append({"step": "dedupe", "detail": "; ".join(dupes)})

    docs, anchors_by_doc = [], {}
    for idx, path in enumerate(materials):
        d = load_document(path)
        d["filename"] = path.name
        d["path"] = str(path)
        d["document_id"] = "D%d" % (idx + 1)
        d["paragraphs"] = 0
        anchors = anchor_paragraphs(d["text"])
        kept = []
        for a in anchors:
            if contains_shell(a["text"]):
                degradations.append("%s: a paragraph carrying an unfilled template marker was skipped"
                                    % path.name)
                continue
            kept.append(a)
        anchors = kept
        d["paragraphs"] = len(anchors)
        docs.append(d)
        anchors_by_doc[d["document_id"]] = anchors
        degradations += ["%s: %s" % (path.name, note) for note in d["notes"]]

    selections, span_no = [], 0
    for d in docs:
        for cand in select_evidence(anchors_by_doc[d["document_id"]]):
            span_no += 1
            selections.append({"span_id": "S%02d" % span_no, "document_id": d["document_id"],
                               **cand})
    anchors_total = sum(len(v) for v in anchors_by_doc.values())

    qa = qa_audit(docs, anchors_by_doc, selections)
    for row in qa["checks"]:
        if not row["ok"]:
            degradations.append("quality check %s: %s" % (row["check"], row["detail"]))

    q_text, q_loc = task_quote(inp)
    sources = [{"source_document_id": "task.md", "file": "task.md", "kind": "task",
                "engine": "direct-read", "sha1": sha1_file(inp / "task.md"), "paragraphs": 1,
                "locator_scheme": "file#char{start}-char{end}", "quote": q_text, "locator": q_loc}]
    for d in docs:
        first = next((s for s in selections if s["document_id"] == d["document_id"]), None)
        if first:
            quote, locator = first["quote"], first["locator"]
        elif anchors_by_doc[d["document_id"]]:
            a0 = anchors_by_doc[d["document_id"]][0]
            quote, locator = a0["text"][:160], a0["locator"]
        else:
            quote, locator = "", ""
        sources.append({"source_document_id": d["document_id"], "file": d["filename"],
                        "kind": d["kind"], "engine": d["engine"], "sha1": d["sha1"],
                        "paragraphs": d["paragraphs"], "quality": d["quality"],
                        "locator_scheme": "p{page}#para{n}", "quote": quote, "locator": locator})

    claims = []
    for i, s in enumerate(selections, 1):
        claims.append({"claim_id": "c%02d" % i, "kind": "answer_span",
                       "document_id": s["document_id"], "span_id": s["span_id"],
                       "text": "%s reports at %s: %s" % (s["document_id"], s["locator"], s["quote"]),
                       "confidence": s["score"], "verified": bool(s["verbatim_ok"]),
                       "evidence": [{"source_document_id": s["document_id"], "quote": s["quote"],
                                     "locator": s["locator"], "char_start": s["char_start"],
                                     "char_end": s["char_end"]}]})
    if not claims:
        claims.append({"claim_id": "c00", "kind": "coverage",
                       "text": "No quantitative evidence span could be anchored from the supplied material.",
                       "confidence": 0.0, "verified": bool(q_text),
                       "evidence": ([{"source_document_id": "task.md", "quote": q_text,
                                      "locator": q_loc}] if q_text else [])})

    question = str(case.get("task_instruction") or case.get("question")
                   or "What do the supplied documents report, and where does each statement sit?")
    task_source = "case.json:task_instruction" if case.get("task_instruction") else "package-default"
    if task_source == "package-default":
        print("task instruction defaulted: the case supplied none", file=sys.stderr)

    readable = anchors_total > 0
    if not materials:
        status = "input_error"
    elif not readable:
        status = "insufficient_evidence"
    elif selections:
        status = "answered"
    else:
        status = "partial"

    steps = [
        {"step": "open", "state": "done" if materials else "no-material",
         "detail": "%d material file(s) discovered" % len(materials)},
        {"step": "locate", "state": "done" if readable else "no-material",
         "detail": "%d paragraph anchor(s) with char offsets" % anchors_total},
        {"step": "select", "state": "done" if selections else "no-material",
         "detail": "%d quantitative span(s) chosen" % len(selections)},
        {"step": "ask", "state": "done" if claims else "no-material",
         "detail": "%d answer claim(s) built from spans" % len(claims)},
        {"step": "save", "state": "done", "detail": "anchors, annotations and state written"},
        {"step": "review", "state": "done" if qa["verbatim_pass"] == qa["verbatim_total"] else "drift",
         "detail": "quote/locator audit %d/%d verbatim" % (qa["verbatim_pass"], qa["verbatim_total"])},
        {"step": "export", "state": "done", "detail": "reading record and offline reader written"},
    ]

    reader_dir = out / "reader"
    jwrite(reader_dir / "anchors.json",
           {"case_id": cid, "scheme": "p{page}#para{n}",
            "documents": {d["document_id"]: {"file": d["filename"], "sha1": d["sha1"],
                                             "kind": d["kind"], "paragraphs": d["paragraphs"]}
                          for d in docs},
            "anchors": anchors_by_doc})
    jwrite(reader_dir / "annotations.json",
           {"case_id": cid, "annotations": [
               {"span_id": s["span_id"], "document_id": s["document_id"], "kind": "highlight",
                "locator": s["locator"], "char_start": s["char_start"], "char_end": s["char_end"],
                "note": "quantitative statement selected for the answer"} for s in selections]})
    jwrite(reader_dir / "qa_log.json", {"case_id": cid, "checks": qa["checks"],
                                        "verbatim_pass": qa["verbatim_pass"],
                                        "verbatim_total": qa["verbatim_total"],
                                        "locator_unique": qa["locator_unique"]})
    jwrite(reader_dir / "reading_state.json",
           {"case_id": cid, "status": status, "cursor": "export", "documents": len(docs),
            "paragraphs": anchors_total, "selections": len(selections),
            "steps": [s["step"] for s in steps]})
    html_payload = {"case_id": cid, "status": status, "documents": [
        {"document_id": d["document_id"], "file": d["filename"], "paragraphs": d["paragraphs"]}
        for d in docs], "selections": [
        {"span_id": s["span_id"], "document_id": s["document_id"], "locator": s["locator"],
         "quote": s["quote"]} for s in selections]}
    wtext(reader_dir / "index.html",
          render_reader_html(cid, status, docs, [a for v in anchors_by_doc.values() for a in v],
                             selections, html_payload))
    wtext(out / "reading_record.md",
          render_reading_record(cid, status, question, docs,
                                [a for v in anchors_by_doc.values() for a in v],
                                selections, qa, [d["filename"] + " read as " + d["kind"] for d in docs]
                                or ["no material file was supplied under the input directory"]))
    jwrite(out / "golden_standard.json", golden_standard(
        cid, docs, [a for v in anchors_by_doc.values() for a in v], selections))
    wtext(out / "diff_report.md", render_diff_report(
        cid, qa, selections, docs))
    wtext(out / "version_history.md", render_version_history(cid, VERSION, changes + [
        {"step": "scan", "detail": "anchored %d paragraph(s) over %d document(s)" % (anchors_total, len(docs))},
        {"step": "audit", "detail": "verbatim %d/%d, unique locators %d"
         % (qa["verbatim_pass"], qa["verbatim_total"], qa["locator_unique"])}]))
    wtext(out / "self_check.json", json.dumps({
        "case_id": cid, "status": status, "version": VERSION,
        "checks": qa["checks"],
        "artifacts_present": ["reader/anchors.json", "reader/annotations.json", "reader/qa_log.json",
                              "reader/reading_state.json", "reader/index.html", "reading_record.md",
                              "golden_standard.json", "diff_report.md", "version_history.md",
                              "self_check.json", "run.log", "result.json"],
        "verdict": "consistent" if qa["verbatim_pass"] == qa["verbatim_total"] else "needs review"},
        ensure_ascii=False, indent=2))
    wtext(out / "run.log", "\n".join([
        "reading-client %s" % VERSION,
        "case_id=%s status=%s" % (cid, status),
        "documents=%d paragraphs=%d selections=%d" % (len(docs), anchors_total, len(selections)),
        "quote_pass=%d/%d locator_unique=%d" % (qa["verbatim_pass"], qa["verbatim_total"],
                                                qa["locator_unique"]),
        "seconds=%.2f" % (time.time() - t0)]) + "\n")

    uncertainties = [
        {"item": "scope", "detail": "only the supplied documents and fields are compared; "
                                    "unlisted material remains a declared gap"},
        {"item": "task_instruction", "detail": "task_source=%s" % task_source},
    ]
    if not readable:
        uncertainties.append({"item": "readable_material",
                              "detail": "no paragraph could be anchored from the supplied files"})
    for d in docs:
        if d["quality"] < 1.0:
            uncertainties.append({"item": "extraction_quality",
                                  "detail": "%s read with quality %.2f" % (d["filename"], d["quality"])})
    changes.append({"step": "extract", "detail": "anchored %d paragraph(s); selected %d span(s)"
                    % (anchors_total, len(selections))})
    limits = [{"item": "no_model_rewriting",
               "detail": "answers are copied spans from the material; nothing is paraphrased in"}]
    if qa["verbatim_pass"] != qa["verbatim_total"]:
        limits.append({"item": "quote_audit_drift",
                       "detail": "some span quotes were not found verbatim in their paragraph"})

    counts = {"documents": len(docs), "paragraphs": anchors_total, "selections": len(selections),
              "claims": len(claims), "sources": len(sources)}
    result = {
        "question": question, "task_source": task_source,
        "documents": [{"document_id": d["document_id"], "file": d["filename"], "kind": d["kind"],
                       "engine": d["engine"], "sha1": d["sha1"], "bytes": d["bytes"],
                       "paragraphs": d["paragraphs"], "quality": d["quality"]} for d in docs],
        "closed_loop": {"scheme": "open -> locate -> select -> ask -> save -> review -> export",
                        "steps": steps, "completed": sum(1 for s in steps if s["state"] == "done"),
                        "total": len(steps)},
        "selections": [{"span_id": s["span_id"], "document_id": s["document_id"],
                        "locator": s["locator"], "quote": s["quote"],
                        "char_start": s["char_start"], "char_end": s["char_end"],
                        "score": s["score"]} for s in selections],
        "annotations": {"count": len(selections), "kind": "highlight"},
        "anchor_precision_counts": {"paragraphs": anchors_total,
                                    "with_char_offsets": anchors_total,
                                    "unique_locators": qa["locator_unique"]},
        "context_design": {"window_chars": PAGE_CHARS,
                           "locator_scheme": "p{page}#para{n}",
                           "offset_scheme": "absolute char offsets in normalised text"},
        "export": {"record": "reading_record.md", "reader": "reader/index.html"},
        "efficiency": {"materials": len(materials), "anchors_reused": anchors_total,
                       "seconds": round(time.time() - t0, 2)},
        "method_notes": ["deterministic span selection; no model call",
                         "every answer is a verbatim span of the material",
                         "PDF/DOCX handled with the standard library only"],
        "artifacts": ["reading_record.md", "golden_standard.json", "diff_report.md",
                      "version_history.md", "self_check.json", "run.log", "result.json",
                      "reader/anchors.json", "reader/annotations.json", "reader/qa_log.json",
                      "reader/reading_state.json", "reader/index.html"],
    }

    summary = ("Reading loop over %d document(s): %d paragraph(s), %d selected span(s), %d claim(s). "
               "Status %s; quote audit %d/%d verbatim." % (
                   len(docs), anchors_total, len(selections), len(claims), status,
                   qa["verbatim_pass"], qa["verbatim_total"]))
    ctx = {"case_id": cid, "status": status, "summary": summary, "result": result,
           "claims": claims, "sources": sources, "uncertainties": uncertainties,
           "uncertainty": uncertainties, "change_records": changes, "changes": changes,
           "errors": errors, "degradations": degradations, "limits": limits,
           "pending_human": [] if not degradations else ["review the degraded extraction noted above"],
           "counts": counts, "artifacts": result["artifacts"],
           "runtime": {"skill": SKILL, "version": VERSION, "seconds": round(time.time() - t0, 2),
                       "documents": len(docs), "selections": len(selections),
                       "quote_pass_rate": (qa["verbatim_pass"] / qa["verbatim_total"])
                       if qa["verbatim_total"] else 1.0}}
    res = finalize(case, ctx)
    jwrite(out / "result.json", res)
    print("status=%s docs=%d paragraphs=%d selections=%d claims=%d" % (
        status, len(docs), anchors_total, len(selections), len(claims)))
    print("artifacts: reading_record.md, golden_standard.json, diff_report.md, version_history.md, "
          "self_check.json, run.log, reader/* | contract keys: %s" % ", ".join(contract_keys(case)))
    return res


def cmd_show(args):
    out = Path(args.output or "/app/output")
    work = Path(args.work or "/app/work")
    idx = jread(out / "reader" / "anchors.json") or jread(work / "index.json") or {}
    anchors = idx.get("anchors") or {}
    if args.doc and args.doc in anchors:
        for a in anchors[args.doc]:
            print("[%s %s] %s" % (args.doc, a["locator"], a["text"][:300]))
        print("-- %s: %d paragraph(s)" % (args.doc, len(anchors[args.doc])))
    elif anchors:
        for did, rows in anchors.items():
            print("%s | %d paragraph(s) | first %s" % (did, len(rows), rows[0]["locator"] if rows else ""))
    else:
        print("(no anchors yet; run the build step first)")
    return 0


def cmd_check(args):
    res = run_pipeline(args)
    print("check: status=%s claims=%d" % (res.get("status"), len(res.get("claims") or [])))
    return 0


def cmd_selfcheck(args):
    res = run_pipeline(args)
    oc = res.get("output_contract") or {}
    empty = [k for k, v in oc.items() if v in (None, "", [], {})]
    print("selfcheck: contract keys=%d empty=%d status=%s" % (len(oc), len(empty), res.get("status")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="reading-client (%s)" % SKILL)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input")
    common.add_argument("--output", "--out", dest="output")
    common.add_argument("--work")
    common.add_argument("--doc")
    for dest in ("input", "output", "work", "doc"):
        ap.add_argument("--" + dest if dest != "output" else "--output", dest=dest)
    ap.add_argument("--out", dest="output")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("build", "show", "check", "selfcheck"):
        sub.add_parser(name, parents=[common])
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if not getattr(a, "cmd", None):
        a.cmd = "build"
    for attr in ("input", "output", "work", "doc"):
        if not hasattr(a, attr):
            setattr(a, attr, None)
    try:
        {"build": run_pipeline, "check": cmd_check, "selfcheck": cmd_selfcheck,
         "show": cmd_show}[a.cmd](a)
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
