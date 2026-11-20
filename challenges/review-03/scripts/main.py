# -*- coding: utf-8 -*-
"""method-statistics-audit CLI entry. Imports the deterministic engine from auditlib.

Commands: all / init / show / check / build / selfcheck / compare. Every command exits 0; only an
argparse usage error returns 2. The single command `all` runs the whole pipeline, writes every
artifact plus a complete result.json even with no draft, and exits 0.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auditlib import (ARTIFACTS, CONTRACT, audit_status, context, coverage, draft, find_case, lines_of,
                      pipeline, rj, sanitize, scan, searched, wj)


def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    c = context(find_case(inp), scan(inp))
    vals = {k: "not-computed-yet" for k in CONTRACT}
    vals["case_id"] = c["case_id"]
    vals["status"] = "drafting"
    vals["deliverable"] = "audit_report.md"
    r = {"case_id": c["case_id"], "status": "drafting", "skill": "method-statistics-audit",
         "summary": "indexed the material; run build (or all) to parse the rules and write the audit",
         "limits": ["partial result written by init"], "uncertainties": ["the audit has not been built yet"],
         "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"]} for m in c["materials"]],
         "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(c["materials"])}],
         "artifacts": {}}
    for k, v in vals.items():
        r.setdefault(k, v)
    r["output_contract"] = vals
    wj(os.path.join(out, "result.json"), r)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, {"case_id": "", "manuscript_meta": {}, "statistics_ledger": [], "extra_findings": [],
                "unchecked_items": [], "uncertainties": [], "summary": ""})
    print("init: indexed the material; wrote a partial result.json + draft.skeleton.json")
    print("next: run show, fill work/draft.json, then check and build")
    return 0


def cmd_show(inp, ident):
    for m in scan(inp):
        if ident and m["id"] != ident and os.path.basename(m["rel"]) != ident:
            continue
        print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
        for ln in lines_of(m):
            print("[%s] %s" % (ln["locator"], ln["text"][:300]))
        if not lines_of(m):
            print("    (no quotable line; status=%s)" % m["status"])
    return 0


def cmd_check(inp, out, work):
    c = context(find_case(inp), scan(inp))
    d = draft(work)
    cov = coverage(c)
    loc = sum(1 for f in c["findings"] if f["source_locator"] != "builtin")
    rep = {"case_id": c["case_id"], "issues": len(c["issues"]), "locators": loc,
           "ledger_rows": len(c["ledger"]), "findings": len(c["findings"]),
           "facets": sum(1 for v in cov["facets_covered"].values() if v),
           "dimensions": sum(1 for v in cov["dimensions_covered"].values() if v),
           "draft_present": isinstance(d, dict), "degradations": c["degradations"],
           "ok": bool(loc) and not c["degradations"]}
    wj(os.path.join(work, "check_report.json"), rep)
    print("== check ==")
    print("issues %d | locators %d | ledger %d | findings %d | facets %d/%d | dimensions %d/%d | %s" % (
        len(c["issues"]), loc, len(c["ledger"]), len(c["findings"]), rep["facets"], len(cov["facets_covered"]),
        rep["dimensions"], len(cov["dimensions_covered"]), "PASS" if rep["ok"] else "DEGRADED"))
    if not loc:
        print("note: no rule row was locatable in the parsed material; searched: %s" % searched(c["materials"]))
    return 0


def cmd_build(inp, out, work):
    r = pipeline(inp, out, work, find_case(inp))
    ct = r.get("counts") if isinstance(r.get("counts"), dict) else {}
    print("== build == status=%s | %d artifact(s) | findings %d | ledger %d | contract %d key(s)" % (
        r["status"], len(ARTIFACTS), len(r.get("findings") or []), len(r.get("ledger") or []),
        len(r.get("output_contract", {}))))
    return 0


def cmd_selfcheck(out, work):
    need = ARTIFACTS + ["evidence"]
    miss = [n for n in need if not os.path.exists(os.path.join(out, n))]
    r = rj(os.path.join(out, "result.json"), {})
    e = r.get("output_contract") if isinstance(r, dict) else None
    ok = isinstance(e, dict) and bool(e) and all(v not in (None, "", [], {}) for v in e.values())
    print("== selfcheck ==")
    print("files %s | contract echo %s | status %s" % ("ok" if not miss else "missing " + ", ".join(miss),
                                                       "ok" if ok else "incomplete",
                                                       r.get("status", "") if isinstance(r, dict) else ""))
    return 0


def cmd_compare(inp, out, work):
    pipeline(inp, out, work, find_case(inp))
    j = rj(os.path.join(out, "gain_report.json"), {})
    print("== compare ==")
    print("gain report written to output (gain_report.json + gain_report.md); contrast written to work/compare_report.json")
    print("baseline (simulated) %s -> skill (measured) %s" % (j.get("baseline"), j.get("skill")))
    return 0


def cmd_all(inp, out, work):
    cmd_build(inp, out, work)
    cmd_selfcheck(out, work)
    cmd_compare(inp, out, work)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="method-statistics-audit")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--id", dest="ident", default="")
    a = ap.parse_known_args(argv)[0]
    cmd, inp, out, work = a.command, a.input, a.output, a.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, a.ident)
        if cmd == "check":
            return cmd_check(inp, out, work)
        if cmd == "selfcheck":
            return cmd_selfcheck(out, work)
        if cmd == "compare":
            return cmd_compare(inp, out, work)
        if cmd == "build":
            return cmd_build(inp, out, work)
        return cmd_all(inp, out, work)
    except Exception as exc:  # noqa
        try:
            os.makedirs(out, exist_ok=True)
            vals = {k: "input could not be processed" for k in CONTRACT}
            vals["case_id"] = "unknown-case"
            vals["deliverable"] = "audit_report.md"
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error", "summary": "the input could not be processed",
                "error": str(exc)[:400], "limits": ["aborted; see error"], "uncertainties": ["the input was unreadable"],
                "sources": [], "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                "output_contract": vals})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
