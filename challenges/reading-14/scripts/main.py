# -*- coding: utf-8 -*-
"""literature-knowledge-graph CLI entry: imports the deterministic engine from kglib; commands all/init/show/check/build/selfcheck/compare; every command exits 0."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kglib import CONTRACT, context, coverage, draft, find_case, pipeline, rj, sanitize, scan, wj


def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    c = context(find_case(inp), scan(inp))
    vals = {k: "not-computed-yet" for k in CONTRACT}; vals["case_id"] = c["case_id"]; vals["status"] = "drafting"
    r = {"case_id": c["case_id"], "status": "drafting", "summary": "indexed the input; run build (or all) to ground the graph",
         "limits": ["partial result written by init"], "uncertainties": ["the graph has not been grounded yet"],
         "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"]} for m in c["materials"]],
         "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(c["materials"])}], "artifacts": {}}
    for k, v in vals.items():
        r.setdefault(k, v)
    r["output_contract"] = vals
    wj(os.path.join(out, "result.json"), r)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, {"case_id": "", "nodes": [], "edges": [], "queries": [], "notes": ""})
    print("init: indexed input; wrote a partial result.json + draft.skeleton.json"); print("next: run show, fill work/draft.json, then check and build")
    return 0


def cmd_show(inp):
    for m in scan(inp):
        print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
        for i, ln in enumerate(m["text"].splitlines()):
            print("[%s/p%d] %s" % (m["id"], i + 1, ln.strip()[:300]))
    return 0


def cmd_check(inp, work):
    c = context(find_case(inp), scan(inp))
    wj(os.path.join(work, "check_report.json"), {"case_id": c["case_id"], "grounded_nodes": len(c["nodes"]), "grounded_edges": len(c["edges"]),
                                                 "rejected_candidates": len(c["rejects"]), "draft_present": isinstance(draft(work), dict), "ok": bool(c["nodes"] or c["edges"])})
    print("check: nodes=%d edges=%d rejected=%d" % (len(c["nodes"]), len(c["edges"]), len(c["rejects"])))
    return 0


def cmd_build(inp, out, work):
    r = pipeline(inp, out, work, find_case(inp)); sanitize(out)
    print("build: status=%s artifacts=%d" % (r["status"], len(r["artifacts"])))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "graph.json", "annotations.jsonl", "query_results.json", "queries.md", "alignment_report.json", "coverage.json",
            "conflicts.json", "sources.json", "uncertainty.json", "change_log.json", "self_check.json"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    r = rj(os.path.join(out, "result.json"), {}); e = r.get("output_contract") if isinstance(r, dict) else None
    ok = isinstance(e, dict) and all(isinstance(v, str) and v.strip() for v in e.values())
    print("selfcheck: files %s, contract echo %s, status %s" % ("ok" if not miss else "missing " + ", ".join(miss), "ok" if ok else "incomplete",
                                                                r.get("status", "") if isinstance(r, dict) else ""))
    return 0


def cmd_compare(inp, out, work):
    c = context(find_case(inp), scan(inp)); cv = coverage(c)
    wj(os.path.join(work, "compare_report.json"), {"case_id": c["case_id"],
       "baseline": "a prose abstract of the papers with no per-node locator, no alias-merge basis and no query",
       "skill": {"nodes": cv["nodes_total"], "edges": cv["edges_total"], "merged_concepts": cv["merged_concepts"], "refused_merges": cv["refused_merges"], "queries_answered": cv["queries_answered"]}})
    print("compare: contrast written to work/compare_report.json")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="literature-knowledge-graph")
    ap.add_argument("command", nargs="?", default="all", choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    ap.add_argument("--input", default="/input"); ap.add_argument("--output", default="/app/output"); ap.add_argument("--work", default="/app/work")
    a = ap.parse_known_args(argv)[0]; cmd, inp, out, work = a.command, a.input, a.output, a.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp)
        if cmd == "check":
            return cmd_check(inp, work)
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
            vals = {k: "input could not be processed" for k in CONTRACT}; vals["case_id"] = "unknown-case"
            wj(os.path.join(out, "result.json"), {"case_id": "unknown-case", "status": "input_error", "summary": "the input could not be processed",
               "error": str(exc)[:400], "limits": ["aborted; see error"], "uncertainties": ["input unreadable"], "sources": [],
               "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}], "output_contract": vals})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
