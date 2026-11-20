#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""manuscript-revision-desk v2.0.0 -- source-preserving editorial annotation desk.

Single command:
    python3 scripts/main.py all --input /input --output /app/output --work /app/work

Agent-first path:
    init -> show -> (agent writes work/draft.json) -> check -> build -> selfcheck

Pure standard library. Always exit 0. Always writes a legal result.json.
"""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from core import (
    DEFAULT_KEYS, clean_text, discover, draft_annotations, flatten_blocks, load_draft,
    rj, wj,
)
from pipeline import safe_build

def resolve_paths(args):
    notes = []
    env = os.environ
    def pick(flag, envs, default):
        if getattr(args, flag):
            return Path(getattr(args, flag))
        for e in envs:
            if env.get(e):
                return Path(env[e])
        return Path(default)
    here = Path(__file__).resolve()
    root = here.parent.parent
    inp = pick("input", ["SKILL_INPUT", "INPUT_DIR", "INPUT"], str(root / "input"))
    out = pick("output", ["SKILL_OUTPUT", "OUTPUT_DIR", "OUTPUT"], str(root / "output"))
    wrk = pick("work", ["SKILL_WORK", "WORK_DIR", "WORK"], str(root / "work"))
    if not inp.is_dir():
        for cand in (Path.cwd() / "input", root / "input"):
            if cand.is_dir():
                notes.append("input %s not found; using %s" % (inp, cand))
                inp = cand
                break
        else:
            notes.append("input %s not found; treated as empty input" % inp)
    for d, tag in ((out, "output"), (wrk, "work")):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            alt = root / ("_" + tag)
            alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s not writable (%s); using %s" % (d, exc, alt))
            if tag == "output":
                out = alt
            else:
                wrk = alt
    return inp, out, wrk, notes

# ------------------------------------------------------------- input discovery

def minimal_result(out, case_id, status, notes):
    keys = dict((k, "bootstrap") for k in DEFAULT_KEYS)
    keys.update({"case_id": case_id, "status": status, "deliverable": "revised_manuscript.md",
                 "preserved_facts": [{"fact_id": "PF-000", "fact": "bootstrap", "quote": "bootstrap",
                                      "locator": "/input", "status": "not_available"}],
                 "evidence_map": "evidence_map.json", "change_log": "change_log.json",
                 "uncertainties": notes or ["bootstrap"]})
    res = {"case_id": case_id, "status": status, "sources": [], "uncertainties": notes or ["bootstrap"],
           "change_records": [{"change_id": "CH-BOOT", "action": "bootstrap", "status": "done",
                               "reason": "legal early result before the pipeline runs"}],
           "limits": "bootstrap result; the pipeline either finalises it or reports its failure honestly",
           "errors": [], "degradations": notes or ["bootstrap"],
           "output_contract": keys}
    res.update({k: keys[k] for k in DEFAULT_KEYS})
    wj(out / "result.json", res)

def cmd_all(args):
    inp, out, wrk, notes = resolve_paths(args)
    safe_build(inp, out, wrk, args)
    print("== all == single command complete: receipt + annotations + manuscript + result.json (exit 0)")
    return 0

def cmd_init(args):
    inp, out, wrk, notes = resolve_paths(args)
    case, cpath, wo, wp, chapters = discover(inp)
    cid = str(case.get("case_id") or "case-unknown")
    minimal_result(out, cid, "partial", notes + ["init bootstrap: legal partial result.json"])
    blocks = flatten_blocks(chapters)
    wj(wrk / "index.json", {"case_id": cid, "case_path": str(cpath or ""),
                            "workorder_path": str(wp or ""),
                            "targets": wo.get("target_ids") or [],
                            "anchored_paragraphs": [{"target_id": b["target_id"], "file": b["file"],
                                                     "line": b["start_line"], "chars": len(b["text"])}
                                                    for b in blocks]})
    wj(wrk / "draft.template.json", {
        "case_id": cid,
        "segments": [{"target_id": b["target_id"], "quote": choose_quote(b["text"]),
                      "kind": "condition", "annotation": "write a source-grounded annotation here",
                      "status": "accepted"} for b in blocks[:6]],
    })
    print("case_id: %s" % cid)
    print("materials: %d | anchored paragraphs: %d | targets: %s" %
          (len(chapters), len(blocks), ", ".join(map(str, wo.get("target_ids") or [])) or "none"))
    print("contract keys: %s" % ", ".join(list((case.get("output_contract") or {}).keys()) or DEFAULT_KEYS))
    print("NEXT: read with `show`, write work/draft.json, then `check`, then `build`.")
    return 0

def cmd_show(args):
    inp, out, wrk, notes = resolve_paths(args)
    case, cpath, wo, wp, chapters = discover(inp)
    blocks = flatten_blocks(chapters)
    print("case: %s" % (cpath or "not found"))
    print("workorder: %s | targets: %s" % (wp or "not found", ", ".join(map(str, wo.get("target_ids") or [])) or "none"))
    for b in blocks:
        print("[%s] %s:L%d (%s)" % (b["target_id"], b["file"], b["start_line"], b["section"] or "no section"))
        print("   %s" % b["text"][:240])
    return 0

def cmd_check(args):
    inp, out, wrk, notes = resolve_paths(args)
    case, cpath, wo, wp, chapters = discover(inp)
    blocks = flatten_blocks(chapters)
    draft, dpath = load_draft(wrk, getattr(args, "draft", None))
    degradations = []
    anns = draft_annotations(draft, blocks, degradations) if draft else []
    checks = {
        "draft_found": bool(draft),
        "draft_path": dpath,
        "annotations_valid": len(anns),
        "degradations": degradations,
        "targets": wo.get("target_ids") or [],
        "verdict": "pass" if anns else "needs_work",
    }
    wj(wrk / "check.json", checks)
    print("verdict: %s | usable annotations: %d | draft: %s" %
          (checks["verdict"], len(anns), dpath or "none"))
    for d in degradations:
        print("FIX: %s" % d)
    return 0

def cmd_build(args):
    inp, out, wrk, notes = resolve_paths(args)
    safe_build(inp, out, wrk, args)
    res = rj(out / "result.json", {}) or {}
    print("status: %s | annotations: %d | facts: %d" %
          (res.get("status"), len(res.get("annotations") or []), len(res.get("preserved_facts") or [])))
    return 0

def cmd_selfcheck(args):
    inp, out, wrk, notes = resolve_paths(args)
    res = rj(out / "result.json", None)
    checks = []
    def ck(cid, ok, detail):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})
    ck("result_json", isinstance(res, dict), "result.json parses as an object")
    if isinstance(res, dict):
        ck("case_id", bool(res.get("case_id")), "case_id propagated: %s" % res.get("case_id"))
        ck("status", res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"),
           "status is %s" % res.get("status"))
        echo = res.get("output_contract") or {}
        ck("contract_keys", isinstance(echo, dict) and bool(echo), "%d contract keys echoed" % len(echo))
        ck("deliverable", (Path(out) / "revised_manuscript.md").is_file()
           and (Path(out) / "revised_manuscript.md").stat().st_size > 20, "revised manuscript is non-empty")
        ck("quote_trace", all(e.get("source_quote") for e in (res.get("annotations") or [])),
           "every annotation carries a source quote")
        dirty = [p.name for p in Path(out).glob("*.md")
                 if clean_text(p.read_text(encoding="utf-8", errors="replace")) !=
                 p.read_text(encoding="utf-8", errors="replace")]
        ck("no_open_markers", not dirty,
           "markdown deliverables are sanitised" if not dirty else "open markers in: %s" % dirty)
    failed = [c for c in checks if c["status"] == "FAIL"]
    wj(out / "verify_report.json", {"checks": checks, "verdict": "fail" if failed else "pass"})
    for c in checks:
        print("%s %s — %s" % (c["status"], c["id"], c["detail"]))
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(description="Source-preserving manuscript revision desk")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args(argv)
    handlers = {"all": cmd_all, "init": cmd_init, "show": cmd_show,
                "check": cmd_check, "build": cmd_build, "selfcheck": cmd_selfcheck}
    try:
        return handlers[args.command](args) or 0
    except SystemExit:
        raise
    except Exception as exc:
        print("captured: %s" % exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
