# -*- coding: utf-8 -*-
"""five-gate research evaluator: CLI entry (all / init / show / check / build / selfcheck / compare).

Standard library only; deterministic; offline; the process always exits 0.
"""
import argparse, sys
from kglib import *  # noqa: F401,F403
from render import *  # noqa: F401,F403

# ---------------------------------------------------------------- cli
def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    mats = scan(inp)
    case = find_case(inp)
    keys = list((case.get("output_contract") or {}).keys()) or list(DEFAULT_CONTRACT)
    vals = {k: "drafting" for k in keys}
    vals["case_id"] = case.get("case_id") or "case-not-stated"
    r = {"case_id": vals["case_id"], "status": "drafting",
         "summary": "indexed the input; run build (or all) to ground the five gates",
         "limits": ["partial result written by init"], "uncertainties": ["the gates have not been grounded yet"],
         "sources": [{"source_id": m["id"], "path": m["rel"], "status": m["status"]} for m in mats],
         "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(mats)}],
         "artifacts": {}}
    for k, v in vals.items():
        r.setdefault(k, v)
    r["output_contract"] = vals
    wj(os.path.join(out, "result.json"), r)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, {"case_id": "", "proposal_title": "", "question": {}, "search_protocol": {}, "gates": [], "matrix": [],
                "novelty": [], "assumptions": [], "claims": [], "conflicts": [],
                "research_gap": {}, "decision": {}, "change_log": [],
                "notes": "fill this in with fields taken from the material; see the rule-anchor appendix in README.md"})
    print("init: indexed %d file(s); wrote a partial result.json + draft.skeleton.json" % len(mats))
    print("next: run show, fill work/draft.json, then check and build")
    return 0


def cmd_show(inp):
    for m in scan(inp):
        print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["rel"], m["status"], m["ext"], m["chars"]))
        for i, ln in enumerate(m["text"].split("\n"), 1):
            if ln.strip():
                print("[%s/p%d] %s" % (m["id"], i, ln.strip()[:220]))
    return 0


def cmd_check(inp, out, work):
    R = build_context(inp, work)
    gates = gate_verdicts(R)
    ver = len([e for e in R["evid"] if e["verified"]])
    r = {"case_id": R["case_id"], "gates": len(gates), "evidence": len(R["evid"]), "verified": ver,
         "verbatim_rate": round(ver / len(R["evid"]), 4) if R["evid"] else 0.0,
         "errors": R["errors"], "unlocated": len(R["rejects"]),
         "draft_present": os.path.isfile(os.path.join(work, "draft.json")), "ok": not R["errors"]}
    wj(os.path.join(work, "check_report.json"), r)
    print("check: gates=%d evidence=%d verified=%d errors=%d" % (len(gates), len(R["evid"]), ver, len(R["errors"])))
    for e in R["errors"]:
        print("  %s: %s" % (e["code"], e["detail"]))
    return 0


def cmd_build(inp, out, work):
    r = pipeline(inp, out, work, find_case(inp))
    print("build: status=%s artifacts=%d" % (r["status"], len(r["artifacts"])))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "decision_brief.md", "gate_scorecard.json", "prior_art_alignment_matrix.csv",
            "assumption_register.json", "evidence_index.jsonl", "conflicts.json", "coverage.json",
            "self_check.json", "change_log.json", "search_log.json", "uncertainty.json", "gain_evidence.json", "run_log.txt"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    r = rj(os.path.join(out, "result.json"), {})
    e = r.get("output_contract") if isinstance(r, dict) else None
    ok = isinstance(e, dict) and all(isinstance(v, str) and v.strip() for v in e.values())
    sc = rj(os.path.join(out, "self_check.json"), {})
    print("selfcheck: files %s, contract echo %s, evidence %s/%s, status %s" %
          ("ok" if not miss else "missing " + ", ".join(miss), "ok" if ok else "incomplete",
           sc.get("verified", 0) if isinstance(sc, dict) else 0, sc.get("evidence_items", 0) if isinstance(sc, dict) else 0,
           r.get("status", "") if isinstance(r, dict) else ""))
    return 0


def cmd_compare(inp, out, work):
    R = build_context(inp, work)
    gates = gate_verdicts(R)
    ver = len([e for e in R["evid"] if e["verified"]])
    wj(os.path.join(work, "compare_report.json"), {
        "case_id": R["case_id"],
        "baseline": "a prose answer from the same materials: no gate table, no locator, no verbatim quote, no conflict registration",
        "skill": {"artifacts": len(ART), "gates": len(gates), "evidence": len(R["evid"]), "verified": ver,
                  "verbatim_rate": round(ver / len(R["evid"]), 4) if R["evid"] else 0.0,
                  "matrix_rows": len(R["claims"]), "conflicts": len(R["conflicts"])},
        "delta": {"gates": len(gates) - 0, "locators": ver - 0, "conflicts": len(R["conflicts"]) - 0}})
    print("compare: contrast written to work/compare_report.json")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="research-topic-innovation-eval")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    a = ap.parse_known_args(argv)[0]
    cmd, inp, out, work = a.command, a.input, a.output, a.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp)
        if cmd == "check":
            return cmd_check(inp, out, work)
        if cmd == "selfcheck":
            return cmd_selfcheck(out)
        if cmd == "compare":
            return cmd_compare(inp, out, work)
        cmd_build(inp, out, work)
        if cmd == "all":
            cmd_selfcheck(out)
        return 0
    except Exception as exc:  # noqa
        try:
            os.makedirs(out, exist_ok=True)
            keys = list((find_case(inp).get("output_contract") or {}).keys()) or list(DEFAULT_CONTRACT)
            vals = {k: "input could not be processed" for k in keys}
            vals["case_id"] = "unknown-case"
            vals["status"] = "input_error"
            wj(os.path.join(out, "result.json"), {
                "case_id": "unknown-case", "status": "input_error", "summary": "the input could not be processed",
                "error": str(exc)[:400], "limits": ["aborted; see error"], "uncertainties": ["input unreadable"],
                "sources": [], "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                "output_contract": vals})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
