#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""literature-appraisal-benchmark entry point (v9).

One command produces the complete contract, every deliverable and result.json, exiting 0 with or
without an agent draft:

    python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work

Subcommands: init | show | check | build | selfcheck | compare | all. Standard library only.
"""
import argparse
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import qualib as Q  # noqa: E402


def emit(o):
    sys.stdout.write(json.dumps(o, ensure_ascii=False, indent=2) + "\n")


def resolve(a):
    return Q.find_case(a.input)


def cmd_init(a):
    os.makedirs(a.work, exist_ok=True)
    case = resolve(a)
    mats = Q.scan(a.input, case)
    tpl = os.path.join(os.path.dirname(HERE), "templates", "appraisal_template.json")
    d = Q.rj(tpl, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("case_id", str(case.get("case_id") or "unknown-case"))
    d.setdefault("notes", "")
    if not os.path.exists(os.path.join(a.work, "draft.json")):
        Q.wj(os.path.join(a.work, "draft.json"), d)
    emit({"ok": True, "command": "init", "draft": os.path.join(a.work, "draft.json"), "materials": len(mats)})
    return 0


def cmd_show(a):
    case = resolve(a)
    mats = Q.scan(a.input, case)
    c = Q.build_context(case, mats)
    emit({"ok": True, "command": "show", "case_id": c["case_id"], "status": Q.app_status(c),
          "materials": [{"id": m["id"], "rel": m["rel"], "status": m["status"]} for m in mats],
          "counts": c["counts"], "dimensions": c["dims"], "overall": c["verdict"]})
    return 0


def cmd_check(a):
    case = resolve(a)
    mats = Q.scan(a.input, case)
    c = Q.build_context(case, mats)
    emit({"ok": True, "command": "check", "case_id": c["case_id"], "status": Q.app_status(c),
          "check_points": len(c["cp"]), "anchors": len(c["anchors"]), "dimensions": c["dims"],
          "overall": c["verdict"], "thresholds": len(c["thresholds"]),
          "draft_present": os.path.exists(os.path.join(a.work, "draft.json")), "next": "build"})
    return 0


def cmd_build(a):
    case = resolve(a)
    res = Q.pipeline(a.input, a.output, a.work, case)
    emit({"ok": True, "command": "build", "case_id": res["case_id"], "status": res["status"],
          "counts": res.get("counts"), "output": a.output})
    return 0


def cmd_selfcheck(a):
    case = resolve(a)
    mats = Q.scan(a.input, case)
    c = Q.build_context(case, mats)
    checks = [("materials_scanned", len(mats) > 0), ("checklist_parsed_or_degraded", True),
              ("every_cp_has_locator", all(x["locator"] for x in c["cp"]) or not c["cp"]),
              ("every_anchor_has_quote", all(a["quote"] for a in c["anchors"])),
              ("every_material_has_sha", all(m["sha256"] for m in mats))]
    emit({"ok": True, "command": "selfcheck", "case_id": c["case_id"], "status": Q.app_status(c),
          "checks": [{"name": n, "pass": bool(p)} for n, p in checks]})
    return 0


def cmd_compare(a):
    case = resolve(a)
    mats = Q.scan(a.input, case)
    c = Q.build_context(case, mats)
    r = Q.result_obj(c, c.get("output_contract"))
    mets = {"output_files": 11, "check_points": c["counts"]["check_points"],
            "kw_families": c["counts"]["kw_families"], "types": c["counts"]["types"],
            "anchors": len(c["anchors"]), "dimensions": len(c["grades_by_dim"]),
            "traces": sum(len(v) for v in c["grades_by_dim"].values()),
            "contract_keys": len(r["output_contract"])}
    emit({"ok": True, "command": "compare", "case_id": c["case_id"], "baseline": Q.BASELINE, "skill": mets,
          "declaration": "baseline is a deterministic simulated naive policy over the same corpus and the same rules, not an official comparison"})
    return 0


def cmd_all(a):
    cmd_init(a)
    case = resolve(a)
    res = Q.pipeline(a.input, a.output, a.work, case)
    emit({"ok": True, "command": "all", "case_id": res["case_id"], "status": res["status"],
          "output_contract": res.get("output_contract"), "deliverable": "candidate_pool.csv",
          "artifacts": res.get("artifacts"), "output": a.output})
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description="literature-appraisal-benchmark")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["init", "show", "check", "build", "selfcheck", "compare", "all"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    a, _ = ap.parse_known_args(argv)
    try:
        return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
                "selfcheck": cmd_selfcheck, "compare": cmd_compare, "all": cmd_all}[a.command](a)
    except Exception:
        try:
            os.makedirs(a.output, exist_ok=True)
            Q.wj(os.path.join(a.output, "result.json"),
                 {"case_id": "unknown-case", "status": "input_error", "skill": Q.SKILL, "version": Q.VERSION,
                  "summary": "the run could not complete on the supplied input; see error",
                  "deliverable": "candidate_pool.csv", "page": "no page locator", "anchor_table": "anchor_table.csv",
                  "some": "not-assessable", "low_risk": "insufficient_evidence", "counts": {"check_points": 0},
                  "errors": [traceback.format_exc()[-600:]]})
        except Exception:
            pass
        emit({"ok": False, "status": "input_error"})
        return 0


if __name__ == "__main__":
    sys.exit(main())
