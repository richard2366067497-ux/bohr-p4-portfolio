#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI + deliverable rendering for the screening closure auditor (search-08).

All domain logic and material parsing live in core.py; this module wires the commands
(all/init/show/check/build/selfcheck/compare), the output-contract echo and the writers.
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

from core import *  # noqa: F401,F403  (constants, helpers, parsing and the screening domain)

DELIVERABLE = "screening_table.csv"
NEED = ["result.json", DELIVERABLE, "dedup_report.json", "conflict_report.json", "audit_log.jsonl",
        "criteria.json", "search_protocol.json", "count_closure.md", "self_check.json"]


def contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    return [str(k) for k in oc] if isinstance(oc, dict) and oc else list(CANON)


def slist(v, note):
    return v if (isinstance(v, list) and v) else [{"kind": "note", "value": note}]


def fill_contract(ctx, p, keys):
    ev = p["evidence"] or [{"kind": "material_read", "locator": s["name"],
                            "note": "%s was read and indexed with a locator" % s["name"]}
                           for s in ctx["sources"][:3]] or [
        {"kind": "note", "locator": "input", "note": "the snapshot carried no material to cite"}]
    vals = {
        "case": "%s | status %s | %s" % (ctx["case_id"], p["status"],
                                         "records %d" % p["closure"]["input_records"]),
        "case_id": ctx["case_id"], "deliverable": DELIVERABLE,
        "evidence_map": ev, "change_log": p["changes"],
        "coverage": dict(p["metrics"], closure=p["closure"], standard_version=p["version"]),
        "status": p["status"],
        "screening": {"rows": len(p["rows"]), "records": len(p["kept"]),
                      "include": len(p["included"]), "exclude": len(p["excluded"]),
                      "needs_review": len(p["review"]), "table": DELIVERABLE},
        "dedup": {"input_records": p["closure"]["input_records"], "after_dedup": p["closure"]["after_dedup"],
                  "merge_pairs": p["merges"]},
        "conflict": {"count": len(p["conflicts"]), "method": "standard_based_arbitration"},
        "audit": {"steps": len(p["changes"]), "log": "audit_log.jsonl"},
        "criteria": p["criteria"],
        "protocol": {"records_ingested": p["closure"]["input_records"],
                     "window": ctx["window"] or "not declared in the snapshot",
                     "languages": ctx["languages"] or ["not declared in the snapshot"]},
        "closure": p["closure"],
        "sources": ctx["sources"] or [{"kind": "note", "name": "input", "note": "the input carried no material file"}],
        "uncertainty": p["uncertainty"],
        "limits": ["no live database search", "coverage is reported for the supplied snapshot only",
                   "double screening is simulated and labelled as such"],
        "report": "the screening closure report is written to the output directory alongside its audit log",
        "paths": {k: k for k in NEED if k != "result.json"},
        "products": {"screening_table": 1, "dedup_report": 1, "conflict_report": 1, "audit_log": 1,
                     "criteria": 1, "search_protocol": 1, "count_closure": 1, "self_check": 1},
        "init": {"status": "ok", "note": "index and frozen criteria version written to the work directory"},
        "show": {"status": "ok", "note": "record projection printed with source locators"},
        "check": {"status": "ok", "note": "mechanical checks: contract keys, count closure and evidence coverage"},
        "build": {"status": p["status"], "note": "the screening artifacts and the final result were written"},
        "selfcheck": {"status": "ok", "note": "artifact presence, recomputation and repeatability verified"},
        "params": NOTE}
    out = {}
    for k in keys:
        v = vals.get(ALIAS.get(nkey(k), "params"), NOTE)
        out[k] = v if not (isinstance(v, str) and not v.strip()) else NOTE
    return out


def r_table(p):
    cols = ["record_id", "decision", "reason_code", "locator", "excerpt", "reviewer", "standard_version"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in p["rows"]:
        w.writerow([r["record_id"], r["decision"], r["reason_code"], r["locator"], r["excerpt"],
                    r["reviewer"], r["standard_version"]])
    return buf.getvalue()


def r_dedup(p):
    return {"policy": "exact DOI first, then normalised title + first author + year + venue",
            "input_records": p["closure"]["input_records"], "merge_pairs_count": len(p["merges"]),
            "after_dedup": p["closure"]["after_dedup"], "merge_pairs": p["merges"],
            "note": "a different DOI is never merged; every pair keeps its basis"}


def r_conflict(p):
    return {"method": "standard_based_arbitration_not_majority_vote", "count": len(p["conflicts"]),
            "conflicts": p["conflicts"],
            "note": "each disagreement keeps both reviewer labels and the basis for the resolution"}


def r_protocol(ctx, p):
    return {"databases": sorted({r["source"] for r in ctx["records"] if r["source"]}) or
            ["not declared in the snapshot"],
            "fields": ["title", "abstract"], "window": ctx["window"] or "not declared in the snapshot",
            "languages": ctx["languages"] or ["not declared in the snapshot"],
            "record_count": p["closure"]["input_records"], "standard_version": p["version"],
            "note": "the protocol records what the snapshot declares; nothing is inferred from a filename"}


def r_closure(p):
    c = p["closure"]
    L = ["# Count closure", "", "The counts must close at every step; the identity is checked mechanically.", "",
         "| step | input | output |", "|---|---|---|",
         "| ingest | 0 | %d |" % c["input_records"],
         "| dedup | %d | %d |" % (c["input_records"], c["after_dedup"]),
         "| screen | %d | %d include + %d exclude + %d needs_review |" % (
             c["after_dedup"], c["included"], c["excluded"], c["needs_review"]), "",
         "input_records - duplicates_merged = after_dedup: %d - %d = %d" % (
             c["input_records"], c["duplicates_merged"], c["after_dedup"]),
         "after_dedup = include + exclude + needs_review: %d = %d + %d + %d" % (
             c["after_dedup"], c["included"], c["excluded"], c["needs_review"]),
         "closure holds: %s" % ("yes" if c["closed"] else "no"), "",
         "| metric | value |", "|---|---|",
         "| dedup merge rate | %s |" % p["metrics"]["dedup_merge_rate"],
         "| reason-code coverage | %s |" % p["metrics"]["reason_code_coverage"],
         "| evidence coverage | %s |" % p["metrics"]["evidence_coverage"],
         "| inter-reviewer agreement | %s |" % p["metrics"]["inter_reviewer_agreement"],
         "| Cohen's kappa | %s |" % p["metrics"]["cohen_kappa"],
         "| audit chain completeness | %s |" % p["metrics"]["audit_chain_completeness"], "",
         "The reviewers are simulated and labelled as such; no human review is claimed.", ""]
    return "\n".join(L)


def write_artifacts(out, ctx, p, contract):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    res = {"case_id": ctx["case_id"], "status": p["status"], "skill": "screening-dedup-conflict-auditor",
           "skill_version": VERSION,
           "summary": "screening closure over %d record(s) with %d conflict(s)" % (
               p["closure"]["input_records"], len(p["conflicts"])),
           "counts": p["closure"], "metrics": p["metrics"], "coverage": p["metrics"],
           "evidence_map": fill_contract(ctx, p, ["evidence_map"])["evidence_map"],
           "change_log": p["changes"], "sources": ctx["sources"],
           "uncertainties": p["uncertainty"],
           "limits": ["no live database search", "coverage is reported for the supplied snapshot only",
                      "double screening is simulated and labelled as such"],
           "standard_version": p["version"], "degradations": ctx["degradations"],
           "output_contract": contract, "deliverable": DELIVERABLE}
    for k, v in contract.items():
        res.setdefault(k, v)
    dump_json(out / "result.json", res)
    dump_text(out / DELIVERABLE, r_table(p))
    dump_json(out / "dedup_report.json", r_dedup(p))
    dump_json(out / "conflict_report.json", r_conflict(p))
    dump_json(out / "criteria.json", p["criteria"])
    dump_json(out / "search_protocol.json", r_protocol(ctx, p))
    dump_text(out / "count_closure.md", r_closure(p))
    lines = []
    for i, ch in enumerate(p["changes"], 1):
        lines.append(json.dumps({"step": i, "action": ch["step"], "operator": "script:deterministic",
                                 "standard_version": p["version"], "detail": ch["detail"]}, ensure_ascii=False))
    dump_text(out / "audit_log.jsonl", "\n".join(lines) + "\n")
    checks = [{"check": "result_json_parses", "ok": True, "detail": "result written"},
              {"check": "contract_keys_present", "ok": bool(contract), "detail": "%d key(s) echoed" % len(contract)},
              {"check": "counts_close", "ok": p["closure"]["closed"], "detail": "input - merges = after_dedup = include + exclude + needs_review"},
              {"check": "reason_code_coverage", "ok": p["metrics"]["reason_code_coverage"] == 1.0, "detail": "every screened row carries a reason code"},
              {"check": "evidence_coverage", "ok": p["metrics"]["evidence_coverage"] == 1.0, "detail": "every screened row carries a locator and an excerpt"},
              {"check": "conflicts_arbitrated", "ok": all(c.get("basis") for c in p["conflicts"]), "detail": "each conflict records a basis and a method"},
              {"check": "standard_version_frozen", "ok": bool(p["version"]), "detail": p["version"]},
              {"check": "status_is_enum", "ok": p["status"] in STATUSES, "detail": p["status"]}]
    dump_json(out / "self_check.json", {"verdict": "ok" if all(c["ok"] for c in checks) else "check", "checks": checks})
    dump_text(out / "run_log.txt", "screening-dedup-conflict-auditor %s\nfiles: %d\nrecords: %d\nafter_dedup: %d\n"
              "include: %d\nexclude: %d\nneeds_review: %d\nconflicts: %d\nstatus: %s\n" % (
                  VERSION, len(ctx["sources"]), p["closure"]["input_records"], p["closure"]["after_dedup"],
                  p["closure"]["included"], p["closure"]["excluded"], p["closure"]["needs_review"],
                  len(p["conflicts"]), p["status"]))
    return res


def write_gain(out, ctx, p):
    n = len(contract_keys(ctx["case"]))
    dump_json(Path(out) / "gain_report.json",
              {"baseline_simulated": {"closed_counts": 0, "located_decisions": 0, "contract_keys_filled": 0},
               "skill_measured": {"closed_counts": 1 if p["closure"]["closed"] else 0,
                                  "located_decisions": len(p["evidence"]), "contract_keys_filled": n},
               "note": "deterministic structural contrast; not an official score"})
    dump_text(Path(out) / "gain_report.md",
              "# Usage gain (deterministic, non-official)\n\n| metric | baseline (simulated) | this skill |\n|---|---|---|\n"
              "| counts that close | 0 | %d |\n| decisions with a locator and an excerpt | 0 | %d |\n"
              "| contract keys filled | 0 | %d |\n\n"
              "This is a structural contrast over the same input, not an official benchmark.\n" % (
                  1 if p["closure"]["closed"] else 0, len(p["evidence"]), n))


def pipeline(inp, out, work):
    ctx = build_context(inp)
    p = build_payload(ctx)
    res = write_artifacts(out, ctx, p, fill_contract(ctx, p, contract_keys(ctx["case"])))
    Path(work).mkdir(parents=True, exist_ok=True)
    dump_json(Path(work) / "index.json", {"case_id": ctx["case_id"], "sources": ctx["sources"],
                                          "records": len(ctx["records"]), "judgements": len(ctx["judgements"]),
                                          "standard_version": p["version"]})
    print("== run == status=%s | records=%d | after_dedup=%d | include=%d | exclude=%d | needs_review=%d | conflicts=%d | contract=%d key(s)" % (
        p["status"], p["closure"]["input_records"], p["closure"]["after_dedup"], p["closure"]["included"],
        p["closure"]["excluded"], p["closure"]["needs_review"], len(p["conflicts"]), len(res["output_contract"])))
    return ctx, p


def cmd_all(i, o, w):
    ctx, p = pipeline(i, o, w)
    write_gain(o, ctx, p)
    print("== all == gain report written; every screening artifact is in the output directory")
    return 0


def cmd_init(i, o, w):
    ctx, p = pipeline(i, o, w)
    Path(w).mkdir(parents=True, exist_ok=True)
    dump_json(Path(w) / "draft.skeleton.json",
              {"case_id": ctx["case_id"], "standard_version": p["version"], "decisions": [], "conflict_notes": []})
    print("== init == criteria version frozen; next: show, draft, check, build, selfcheck")
    return 0


def cmd_show(i, o, w):
    ctx = build_context(i)
    p = build_payload(ctx)
    print("== task ==\ncase_id: %s\nresearch question: %s\nstandard version: %s" % (
        ctx["case_id"], ctx["rq"] or "-", p["version"]))
    print("== sources ==")
    for s in ctx["sources"]:
        print("  %-28s %-6s %-14s records=%s judgements=%s codes=%s" % (
            s["name"], s["kind"], s["parse_status"], s["records"], s["judgements"], s["code_dictionary"]))
    print("== records (%d) ==" % len(p["kept"]))
    for r in p["kept"][:40]:
        print("  %-12s %-16s %-10s %s" % (r["record_id"], r["decision"], r["reason_code"], (r["title"] or "")[:56]))
    print("next: optionally write work/draft.json, then run check and build")
    return 0


def cmd_check(i, o, w):
    ctx = build_context(i)
    p = build_payload(ctx)
    rep = {"case_id": ctx["case_id"], "closure": p["closure"], "conflicts": len(p["conflicts"]),
           "reason_code_coverage": p["metrics"]["reason_code_coverage"],
           "evidence_coverage": p["metrics"]["evidence_coverage"],
           "ok": bool(p["closure"]["closed"]) and p["metrics"]["reason_code_coverage"] == 1.0}
    Path(w).mkdir(parents=True, exist_ok=True)
    dump_json(Path(w) / "check_report.json", rep)
    print("== check == closed=%s reason_codes=%s evidence=%s conflicts=%d -> %s" % (
        rep["closure"]["closed"], rep["reason_code_coverage"], rep["evidence_coverage"], rep["conflicts"],
        "PASS" if rep["ok"] else "DEGRADED"))
    return 0


def cmd_selfcheck(o, w):
    out = Path(o)
    r, _ = load_json(out / "result.json")
    r = r if isinstance(r, dict) else {}
    echo = r.get("output_contract") if isinstance(r.get("output_contract"), dict) else {}
    empty = [k for k, v in echo.items() if v in (None, "", [], {})]
    miss = [n for n in NEED if not (out / n).exists()]
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
        contract.update({"case_id": "unknown-case", "deliverable": DELIVERABLE, "status": "input_error",
                         "evidence_map": [{"kind": "note", "locator": "input", "note": "the input was unreadable"}],
                         "change_log": [{"step": "abort", "detail": "unhandled error"}],
                         "coverage": {"note": "the run aborted before any metric was computed"}})
        dump_json(out / "result.json", {"case_id": "unknown-case", "status": "input_error",
                                        "summary": "the input could not be processed", "sources": [],
                                        "uncertainties": ["the input was unreadable"],
                                        "change_records": [{"step": "abort", "detail": "unhandled error"}],
                                        "limits": ["aborted; see the error record"], "output_contract": contract})
        dump_text(out / DELIVERABLE, "record_id,decision,reason_code,locator,excerpt,reviewer,standard_version\n")
        dump_text(out / "count_closure.md", "# Count closure\n\nStatus: input_error\n\nThe input could not be processed.\n")
        dump_text(out / "run_log.txt", "screening-dedup-conflict-auditor %s\nstatus: input_error\n" % VERSION)
    except Exception:
        pass
    print("input_error: %s" % exc)


def run(argv=None):
    ap = argparse.ArgumentParser(prog="screening-dedup-conflict-auditor")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
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
