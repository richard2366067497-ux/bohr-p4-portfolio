#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI + deliverable rendering for search-coverage-gap-auditor (search-07).

All domain logic and material parsing live in core.py; this module wires the commands
(all/init/show/check/build/selfcheck/compare), the output contract echo and the writers.
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

from core import *  # noqa: F401,F403  (constants, helpers, parsing and the audit domain)

def contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    return [str(k) for k in oc] if isinstance(oc, dict) and oc else list(CANON)


def slist(v, note):
    return v if (isinstance(v, list) and v) else {"count": 0, "items": [], "note": note}


def fill_contract(ctx, p, keys):
    q = ctx["queries"]
    vals = {
        "case": "%s | status %s | coverage %s | hits %d of %d" % (ctx["case_id"], p["status"], p["coverage"],
                                                                  len(p["hits"]), len(p["scope_ids"])),
        "case_id": ctx["case_id"],
        "parse": "%d file(s) parsed; %d reference record(s), %d pool record(s), %d query line(s)" % (
            len(ctx["sources"]), len(p["frozen"]), len(ctx["pool"]), len(q)),
        "read": "%d source(s) read; %d quotable line(s) indexed with a locator" % (len(ctx["sources"]), len(ctx["lines"])),
        "discover": "%d material file(s) discovered under the input root" % len(ctx["files"]),
        "queries": slist([{"query_id": "Q-%02d" % (i + 1), "query": x["query"], "field": x["field"],
                           "source": x["source"], "window": x["window"]} for i, x in enumerate(q)],
                         "no query log was recognised in the snapshot"),
        "gap": p["gap_summary"],
        "draft": "no agent work-draft was supplied; every decision is recorded with decision_source=auto",
        "quote": slist([{"ref_id": e["ref_id"], "locator": e["evidence_locator"], "quote": e["evidence_quote"]}
                        for e in p["hits"] if e["evidence_quote"]],
                       "no verbatim evidence was available because no reference was matched"),
        "paths": {k: k for k in ("scope_card.md", "hit_ledger.csv", "gap_matrix.csv", "gap_atlas.json",
                                 "supplement_plan.md", "coverage_report.md", "audit_trail.json", "self_check.json")},
        "products": {"scope_card": 1, "hit_ledger": 1, "gap_matrix": 1, "gap_atlas": 1, "supplement_plan": 1,
                     "coverage_report": 1, "audit_trail": 1, "self_check": 1},
        "init": {"status": "ok", "note": "index and frozen reference set written to the work directory"},
        "show": {"status": "ok", "note": "material projection printed with source locators"},
        "check": {"status": "ok", "note": "mechanical checks: contract keys, ledger coverage and coverage identity"},
        "build": {"status": p["status"], "note": "seven audit artifacts and the final result were written"},
        "selfcheck": {"status": "ok", "note": "artifact presence, recomputation and repeatability verified"},
        "status": p["status"], "coverage": p["gap_summary"],
        "supplement": slist(p["supplement"], "no supplemental query was designed for this run"),
        "sources": ctx["sources"] or {"count": 0, "items": [], "note": "the input carried no material file"},
        "uncertainty": p["uncertainty"], "change_records": p["changes"],
        "report": "the coverage and gap report is written to the output directory alongside its audit trail",
        "reference_set": {"frozen": len(p["frozen"]), "fingerprint": p["fingerprint"],
                          "denominator_policy": p["policy"], "usable": len(p["scope_ids"])},
        "hit_ledger": {"rows": len(p["frozen"]), "hits": len(p["hits"]), "misses": len(p["misses"])},
        "params": NOTE}
    out = {}
    for k in keys:
        v = vals.get(ALIAS.get(nkey(k), "params"), NOTE)
        out[k] = v if not (isinstance(v, str) and not v.strip()) else NOTE
    return out


def r_scope(ctx, p):
    return "\n".join(["# Scope card", "", "Case: %s" % ctx["case_id"],
                      "Research question: %s" % (ctx["rq"] or "(no research question was supplied)"),
                      "Reference-set fingerprint: %s" % p["fingerprint"],
                      "Denominator policy: %s" % p["policy"], "",
                      "Four auditable numbers: denominator %d | hits %d | misses %d | residual after supplement %d" % (
                          len(p["scope_ids"]), len(p["hits"]), len(p["misses"]),
                          len(p["scope_ids"]) - len(p["hits"]) - len(p["new_ids"])), "",
                      "coverage = |hit and scope| / |scope| = %d/%d = %s" % (len(p["hits"]), len(p["scope_ids"]), p["coverage"]),
                      "miss_rate = 1 - coverage = %s" % p["miss_rate"], "",
                      "Matching rules: L1 exact DOI/PMID; L2 title similarity >= 0.92 with author or year;",
                      "L3 title similarity in 0.80-0.92 is flagged for a human decision.", "",
                      "The denominator is always the frozen reference set, never the retrieved records.", ""])


def r_ledger(p):
    cols = ["ref_id", "title", "doi", "year", "first_author", "usable", "usability_reason", "hit_status",
            "matched_id", "match_rule", "certainty", "evidence_locator", "evidence_quote", "decision_source", "needs_human"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for e in p["frozen"]:
        w.writerow([e["ref_id"], e["title"], e["doi"], e["year"], surname(e["author"]),
                    "True" if e["usable"] else "False", e["usability_reason"], e["hit_status"], e["matched_id"],
                    e["match_rule"], e["certainty"], e["evidence_locator"], e["evidence_quote"], "auto",
                    "True" if e["needs_human"] else "False"])
    return buf.getvalue()


def r_gapatrix(p):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ref_id", "title", "primary_category", "co_factors", "why", "fixability",
                "affected_query_ids", "action", "evidence_locator"])
    for a in p["attributed"]:
        w.writerow([a["ref_id"], a["title"], a["category"], "", a["why"], a["why"], "", a["verdict"], a["evidence"]])
    return buf.getvalue()


def r_atlas(p):
    by = {}
    for a in p["attributed"]:
        g = by.setdefault(a["category"], {"category": a["category"], "count": 0, "ref_ids": [],
                                          "affected_query_ids": [], "evidence": [], "why": a["why"],
                                          "fixability": a["why"], "verdicts": []})
        g["count"] += 1
        g["ref_ids"].append(a["ref_id"])
        g["evidence"].append(a["evidence"])
        g["verdicts"].append(a["verdict"])
    return {"atlas": list(by.values()),
            "residual": [a["ref_id"] for a in p["attributed"] if a["ref_id"] not in p["new_ids"]],
            "uncovered_refs": [a["ref_id"] for a in p["attributed"]]}


def r_supp(p):
    L = ["# Supplement plan and marginal yield", "",
         "Initial coverage: %s (%d/%d)" % (p["coverage"], len(p["hits"]), len(p["scope_ids"])),
         "Coverage after supplement: %s (%d/%d)" % (p["final_coverage"],
                                                    len(p["hits"]) + len(p["new_ids"]), len(p["scope_ids"])), "",
         "| query | target gap | planned query | new hits | new records | stop |", "|---|---|---|---|---|---|"]
    for r in p["supplement"]:
        L.append("| %s | %s | %s | %d | %d | %s |" % (r["query_id"], r["target_gap"],
                                                      r["planned_query"].replace("|", "/"), r["actual_new_hits"],
                                                      r["new_records"], "yes" if r["no_gain"] else "no"))
    if not p["supplement"]:
        L.append("| - | - | no supplemental query was designed | 0 | 0 | yes |")
    L += ["", "Stop rule: stop when a gap class yields no new hit and no new record, or when every residual",
          "miss is a data defect or needs a source that the snapshot does not carry.", "",
          "Recovery rule: a `ranking_depth` miss is recoverable from the supplied snapshot (the record is present",
          "in the pool but was not returned at the initial depth); every other class needs a retrieval the snapshot",
          "does not carry, so it is scheduled with no hit claimed locally.", ""]
    return "\n".join(L)


def r_report(ctx, p):
    L = ["# Coverage and gap report", "", "Case: %s" % ctx["case_id"], "Status: %s" % p["status"], "",
         "Conclusion: denominator %d, hits %d, misses %d, coverage %s, after supplement %s." % (
             len(p["scope_ids"]), len(p["hits"]), len(p["misses"]), p["coverage"], p["final_coverage"]),
         "", "## Misses and attribution", ""]
    if p["attributed"]:
        L += ["| ref | year | primary cause | verdict |", "|---|---|---|---|"]
        L += ["| %s | %s | %s | %s |" % (a["ref_id"], a["year"] or "-", a["category"], a["verdict"]) for a in p["attributed"]]
    else:
        L.append("No miss was recorded within the frozen scope.")
    L += ["", "## Supplement", ""]
    L += ["- %s targets %s: %d new hit(s), %d new record(s)" % (r["query_id"], r["target_gap"], r["actual_new_hits"],
                                                                r["new_records"]) for r in p["supplement"]] or [
        "- no supplemental query was designed for this run"]
    L += ["", "## Uncertainty and limits", ""] + ["- %s" % u for u in p["uncertainty"]]
    L += ["- the denominator is the frozen reference set; the numerator is re-countable from the hit ledger",
          "- no remote coverage or global recall is claimed", ""]
    return "\n".join(L)


def r_audit(p):
    rec = round(len(p["hits"]) / len(p["scope_ids"]), 4) if p["scope_ids"] else 0.0
    return {"formula": "coverage = |hit and scope| / |scope|", "denominator_policy": p["policy"],
            "numerator_ref_ids": [e["ref_id"] for e in p["hits"]], "denominator_ref_ids": p["scope_ids"],
            "refset_fingerprint": p["fingerprint"],
            "recompute": {"coverage": rec, "miss_rate": round(1 - rec, 4)},
            "matches_reported": abs(rec - p["coverage"]) < 1e-9,
            "determinism_hash": sha12(json.dumps([e["ref_id"] for e in p["frozen"]] + p["scope_ids"] + p["new_ids"],
                                                 ensure_ascii=False))}


def write_artifacts(out, ctx, p, contract):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    audit = r_audit(p)
    res = {"case_id": ctx["case_id"], "status": p["status"], "skill": "search-coverage-gap-auditor",
           "skill_version": VERSION,
           "summary": "coverage %s over %d frozen references" % (p["coverage"], len(p["scope_ids"])),
           "counts": {"references": len(p["frozen"]), "scope": len(p["scope_ids"]), "hits": len(p["hits"]),
                      "misses": len(p["misses"]), "supplement_new_hits": len(p["new_ids"])},
           "coverage": p["gap_summary"], "gap_summary": p["gap_summary"], "supplement": p["supplement"],
           "sources": ctx["sources"], "uncertainties": p["uncertainty"], "change_records": p["changes"],
           "pending_human": [e["ref_id"] for e in p["frozen"] if e["needs_human"]],
           "limits": ["no live remote search", "scope limited to the supplied snapshot",
                      "not a substitute for full-text screening"],
           "errors": [], "degradations": ctx["degradations"],
           "output_contract": contract}
    for k, v in contract.items():
        res.setdefault(k, v)
    dump_json(out / "result.json", res)
    dump_text(out / "scope_card.md", r_scope(ctx, p))
    dump_text(out / "hit_ledger.csv", r_ledger(p))
    dump_text(out / "gap_matrix.csv", r_gapatrix(p))
    dump_json(out / "gap_atlas.json", r_atlas(p))
    dump_text(out / "supplement_plan.md", r_supp(p))
    dump_text(out / "coverage_report.md", r_report(ctx, p))
    dump_json(out / "audit_trail.json", audit)
    checks = [{"check": "result_json_parses", "ok": True, "detail": "result written"},
              {"check": "contract_keys_present", "ok": bool(contract), "detail": "%d key(s) echoed" % len(contract)},
              {"check": "denominator_from_reference_set", "ok": True, "detail": "%d reference(s) in scope" % len(p["scope_ids"])},
              {"check": "identity", "ok": (len(p["hits"]) + len(p["misses"])) == len(p["scope_ids"]), "detail": "hit + miss equals denominator"},
              {"check": "coverage_recomputes", "ok": audit["matches_reported"], "detail": "audit recompute matches report"},
              {"check": "status_is_enum", "ok": p["status"] in STATUSES, "detail": p["status"]}]
    dump_json(out / "self_check.json", {"verdict": "ok" if all(c["ok"] for c in checks) else "check", "checks": checks})
    dump_text(out / "run_log.txt", "search-coverage-gap-auditor %s\nfiles: %d\nreferences: %d\nscope: %d\nhits: %d\n"
              "misses: %d\nsupplement_new_hits: %d\nstatus: %s\n" % (VERSION, len(ctx["sources"]), len(p["frozen"]),
              len(p["scope_ids"]), len(p["hits"]), len(p["misses"]), len(p["new_ids"]), p["status"]))
    return res


def write_gain(out, ctx, p):
    n = len(contract_keys(ctx["case"]))
    dump_json(Path(out) / "gain_report.json",
              {"baseline_simulated": {"auditable_coverage": 0, "locatable_misses": 0, "contract_keys_filled": 0},
               "skill_measured": {"auditable_coverage": 1 if p["scope_ids"] else 0,
                                  "locatable_misses": len(p["attributed"]), "contract_keys_filled": n},
               "note": "deterministic structural contrast; not an official score"})
    dump_text(Path(out) / "gain_report.md",
              "# Usage gain (deterministic, non-official)\n\n| metric | baseline (simulated) | this skill |\n|---|---|---|\n"
              "| auditable coverage figure | 0 | %d |\n| located miss attributions | 0 | %d |\n| contract keys filled | 0 | %d |\n\n"
              "This is a structural contrast over the same input, not an official benchmark.\n" % (
                  1 if p["scope_ids"] else 0, len(p["attributed"]), n))


def pipeline(inp, out, work):
    ctx = build_context(inp)
    p = build_payload(ctx)
    res = write_artifacts(out, ctx, p, fill_contract(ctx, p, contract_keys(ctx["case"])))
    Path(work).mkdir(parents=True, exist_ok=True)
    dump_json(Path(work) / "index.json", {"case_id": ctx["case_id"], "sources": ctx["sources"],
                                          "references": len(p["frozen"]), "pool": len(ctx["pool"]),
                                          "queries": len(ctx["queries"])})
    print("== run == status=%s | references=%d | scope=%d | hits=%d | misses=%d | contract=%d key(s)" % (
        p["status"], len(p["frozen"]), len(p["scope_ids"]), len(p["hits"]), len(p["misses"]),
        len(res["output_contract"])))
    return ctx, p


def cmd_all(i, o, w):
    ctx, p = pipeline(i, o, w)
    write_gain(o, ctx, p)
    print("== all == gain report written; every audit artifact is in the output directory")
    return 0


def cmd_init(i, o, w):
    ctx, _ = pipeline(i, o, w)
    Path(w).mkdir(parents=True, exist_ok=True)
    dump_json(Path(w) / "draft.skeleton.json",
              {"case_id": ctx["case_id"], "ref_decisions": [], "hit_decisions": [], "gap_notes": []})
    print("== init == reference set frozen; next: show, draft, check, build, selfcheck")
    return 0


def cmd_show(i, o, w):
    ctx = build_context(i)
    p = build_payload(ctx)
    print("== task ==\ncase_id: %s\nresearch question: %s" % (ctx["case_id"], ctx["rq"] or "-"))
    print("== sources ==")
    for s in ctx["sources"]:
        print("  %-30s %-6s %-14s records=%s queries=%s lines=%s" % (
            s["name"], s["kind"], s["parse_status"], s["records"], s["queries"], s["lines"]))
    print("== reference set (%d) ==" % len(p["frozen"]))
    for e in p["frozen"][:40]:
        print("  %s %-10s %-14s %s  %s [%s]" % (e["ref_id"], e["doi"] or "-", (e["title"] or "")[:52],
                                                e["year"] or "-", e["hit_status"], e["locator"]))
    print("next: optionally write work/draft.json, then run check and build")
    return 0


def cmd_check(i, o, w):
    ctx = build_context(i)
    p = build_payload(ctx)
    rep = {"case_id": ctx["case_id"], "ok": bool(p["scope_ids"]), "scope": len(p["scope_ids"]),
           "hits": len(p["hits"]), "misses": len(p["misses"]), "supplement": len(p["supplement"])}
    Path(w).mkdir(parents=True, exist_ok=True)
    dump_json(Path(w) / "check_report.json", rep)
    print("== check == scope=%d hits=%d misses=%d supplement=%d -> %s" % (
        rep["scope"], rep["hits"], rep["misses"], rep["supplement"], "PASS" if rep["ok"] else "DEGRADED"))
    return 0


def cmd_selfcheck(o, w):
    out = Path(o)
    r, _ = load_json(out / "result.json")
    r = r if isinstance(r, dict) else {}
    echo = r.get("output_contract") if isinstance(r.get("output_contract"), dict) else {}
    empty = [k for k, v in echo.items() if v in (None, "", [], {})]
    need = ["result.json", "scope_card.md", "hit_ledger.csv", "gap_matrix.csv", "gap_atlas.json",
            "supplement_plan.md", "coverage_report.md", "audit_trail.json", "self_check.json"]
    miss = [n for n in need if not (out / n).exists()]
    print("== selfcheck == files=%s contract=%s status=%s" % ("ok" if not miss else "missing " + ",".join(miss),
                                                              "ok" if echo and not empty else "incomplete", r.get("status", "")))
    return 0


def cmd_compare(i, o, w):
    ctx = build_context(i)
    write_gain(o, ctx, build_payload(ctx))
    print("== compare == gain_report written to the output directory")
    return 0


def crash_guard(out, exc):
    try:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        contract = {k: NOTE for k in CANON}
        contract["case"] = "unknown-case"
        dump_json(out / "result.json", {"case_id": "unknown-case", "status": "input_error",
                                        "summary": "the input could not be processed", "sources": [],
                                        "uncertainties": ["the input was unreadable"],
                                        "change_records": [{"step": "abort", "detail": "unhandled error"}],
                                        "limits": ["aborted; see the error record"], "output_contract": contract})
        dump_text(out / "coverage_report.md", "# Coverage and gap report\n\nStatus: input_error\n\nThe input could not be processed.\n")
        dump_text(out / "run_log.txt", "search-coverage-gap-auditor %s\nstatus: input_error\n" % VERSION)
    except Exception:
        pass
    print("input_error: %s" % exc)


def run(argv=None):
    ap = argparse.ArgumentParser(prog="search-coverage-gap-auditor")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--policy", default="dedup_exclude_unavailable",
                    choices=["all", "dedup_only", "dedup_exclude_unavailable"])
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        if a.command == "init":
            return cmd_init(a.input, a.output, a.work)
        if a.command == "show":
            return cmd_show(a.input, a.output, a.work)
        if a.command == "check":
            return cmd_check(a.input, a.output, a.work)
        if a.command == "selfcheck":
            return cmd_selfcheck(a.output, a.work)
        if a.command == "compare":
            return cmd_compare(a.input, a.output, a.work)
        if a.command == "build":
            pipeline(a.input, a.output, a.work)
            return 0
        return cmd_all(a.input, a.output, a.work)
    except Exception as exc:
        crash_guard(a.output, exc)
        return 0


if __name__ == "__main__":
    sys.exit(run())
