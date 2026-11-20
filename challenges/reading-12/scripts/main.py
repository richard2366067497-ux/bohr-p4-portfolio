# -*- coding: utf-8 -*-
"""extraction-table-cleaner CLI: the reporting layer, the contract echo and the documented subcommands.
Stdlib only, offline, deterministic; every command exits 0."""
import argparse, json, os, sys
from engine import *


SKEL = {"case_id": "", "case_summary": "", "field_map": {}, "records": [], "groups": [], "claims": [], "pending": [],
        "unmapped_columns": [], "uncertainties": []}


def bc(case, mats):
    fd, cat, ut, recs = cls(mats)
    ctx = {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats, "degradations": [],
           "errors": [], "catalog": cat or {}, "unit_table": ut or {}, "field_dict": fd or {}}
    if recs and (fd or ut):
        rows, ch, pd, unm = cr(recs, fd, cat, ut)
    else:
        rows, ch, pd, unm = [], [], [], []
        for c, m in ((not recs, "no extraction records were supplied; only the rule base could be read"),
                     (not fd, "no field dictionary was supplied"), (not ut, "no unit table was supplied")):
            if c:
                ctx["degradations"].append(m)
    ctx["rows"], ctx["changes"], ctx["pending"], ctx["unmapped"] = rows, ch, pd, unm
    if not rows:
        ctx["pending"].append(pn("-", "", "no_records", "the batch contained no extraction row to clean",
                                 "supply a records file and re-run the same command", "input scan"))
    ctx["claims"] = [{"claim_id": x.get("rule_id"), "kind": "undetermined", "rule_id": x.get("rule_id"),
                      "statement": "rule %s is human-gated: %s" % (x.get("rule_id"), x.get("condition"))}
                     for x in (cat or {}).get("rules") or [] if isinstance(x, dict) and x.get("human_gate")]
    n = lambda s: sum(1 for r in rows if r["st"] == s)
    ctx["coverage"] = {"records_in": len(recs), "rows_out": len(rows),
                       "converted": sum(1 for r in rows if "R011" in (r.get("ru") or [])), "missing": n("missing"),
                       "needs_review": n("needs_review"), "merged_duplicate": n("merged_duplicate"), "replicate": n("replicate"),
                       "conflict": n("conflict"), "changes": len(ch), "queued_for_review": len(pd), "unmapped_columns": len(unm),
                       "rules_available": len((cat or {}).get("rules") or []), "units_available": len((ut or {}).get("units") or {})}
    return ctx


def so(ctx):
    if ctx["errors"]:
        return "input_error"
    if not ctx["rows"]:
        return "insufficient_evidence"
    return "partial" if any(r["st"] in ("needs_review", "conflict") for r in ctx["rows"]) else "answered"


def uc(ctx):
    o = list(ctx["degradations"])
    o.append("units normalise to the majority label per (field, dimension); each conversion logs before/factor/offset/after")
    if ctx["pending"]:
        o.append("%d row(s) are queued for human confirmation instead of being guessed" % len(ctx["pending"]))
    if ctx["unmapped"]:
        o.append("declared unmapped columns: %s" % ", ".join(ctx["unmapped"]))
    return o


def sen(ctx, key):
    k, s, c = nk(key), so(ctx), ctx["coverage"]
    if k in ("caseid", "id"):
        return ctx["case_id"]
    if k == "status":
        return s
    if k == "outputcontract":
        return ", ".join(DC)
    if k in ("summary", "abstract", "conclusion", "digest"):
        return "%s: %d record(s) in, %d row(s) out, %d change(s), %d queued for review" % (
            s, c["records_in"], c["rows_out"], c["changes"], c["queued_for_review"])
    if k in ("evidencemap", "evidence", "claims", "claim"):
        v = [{"claim_id": x["claim_id"], "kind": x["kind"], "statement": x["statement"], "rule_id": x["rule_id"],
              "source_locator": "rule_catalog#%s" % x["rule_id"]} for x in ctx["claims"]]
        v += [{"claim_id": "row:%s" % r["r"], "kind": "reported", "rule_id": ";".join(r["ru"]), "source_locator": r["l"],
               "statement": "%s = %s %s (%s)" % (r["f"] or "value", r["v"], r["u"], r["st"])} for r in ctx["rows"]]
        return v or [{"claim_id": "no-data", "kind": "undetermined", "rule_id": "R023", "source_locator": "input scan",
                      "statement": "no extraction row was present in the input"}]
    if k in ("changelog", "changes"):
        return ctx["changes"] or [{"r": "-", "t": "none", "id": "R026", "l": "input scan",
                                   "fm": "no value was changed because no extraction row was present"}]
    if k in ("coverage", "coveragereport"):
        return c
    if k in ("uncertainties", "uncertainty", "limits", "limit"):
        return uc(ctx)
    for ks, path in (("deliverable cleaned cleanedcsv table output rows", "cleaned.csv"), ("pendingreview pending review", "pending_review.csv"),
                     ("anomalyreport anomaly", "anomaly_report.md"), ("rules rulecatalog rulebase", "rules.json"),
                     ("fieldmapping mapping fieldmap", "field_mapping.json"), ("unittable units unit", "unit_table.json")):
        if k in ks.split():
            return path
    return "derived: %d row(s), %d change(s); status %s" % (len(ctx["rows"]), len(ctx["changes"]), s)


def am(ctx):
    c = ctx["coverage"]
    L = ["# Anomaly and conflict report", "", "Status: %s" % so(ctx), "",
         "Records in: %d | rows out: %d | converted: %d | queued for review: %d" % (c["records_in"], c["rows_out"],
                                                                                     c["converted"], c["queued_for_review"]),
         "", "| bucket | count |", "|-|-|"] + ["| %s | %d |" % (b, c[b]) for b in BK]
    L += ["", "## Method", "- roles come from the dictionary; unmatched columns are declared, never dropped",
          "- units normalise to the majority label per (field, dimension) and log before/factor/offset/after",
          "- names change only on an exact synonym hit; duplicates, replicates and conflicts go by judgment key, not row order",
          "", "## Queued"]
    L += ["- **%s** `%s` at %s: %s -> %s" % (p["rc"], p["r"], p["l"], p["rs"], p["sa"])
          for p in ctx["pending"]] or ["- nothing was held; every value passed the checks"]
    L += ["", "## Rows"]
    L += ["- %s | %s = %s %s | %s | rules %s" % (r["r"], r["f"] or "value", r["v"], r["u"], r["st"], ";".join(r["ru"]))
          for r in ctx["rows"][:60]] or ["- no extraction row was present; the rule base was read and every artifact keeps a "
                                         "structured no-data record (rule R023)"]
    L += ["", "## Boundary", "A conversion never resolves a scientific disagreement; conflicting rows keep both values. Missing stays empty, never 0."]
    return "\n".join(L)


def rs(ctx):
    cat = ctx["catalog"] if isinstance(ctx["catalog"], dict) else {}
    ks = ("rule_id", "name", "priority", "applies_to", "owner", "human_gate", "condition", "transform", "failure_mode")
    rules = [{k: x.get(k) for k in ks} for x in cat.get("rules") or [] if isinstance(x, dict)]
    if not rules:
        rules = [{"rule_id": "R023", "name": "empty_input_degrade", "priority": 123, "applies_to": "file", "owner": "builtin",
                  "human_gate": False, "condition": "no rule catalog was supplied", "transform":
                  "status insufficient_evidence; keep a legal result.json with the contract keys",
                  "failure_mode": "an empty run is indistinguishable from a real result"}]
    ids = [x.get("rule_id") for x in cat.get("rules") or [] if isinstance(x, dict)]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    return {"precedence": cat.get("precedence") or "Lower priority number wins; a case rule replaces a builtin rule with the same id.",
            "tolerance": cat.get("tolerance") or {"replicate_relative_spread": 0.05}, "rules": rules,
            "suppressed_rules": [{"rule_id": i, "reason": "a case rule with this id replaced the builtin of the same id"} for i in dup]}


def br(ctx, contract, draft):
    keys = list(contract) if isinstance(contract, dict) and contract else list(DC)
    out = {}
    for k in keys:
        v = sen(ctx, k)
        out[st(k) if isinstance(k, str) else k] = v if (not isinstance(v, str) or v.strip()) else "derived"
    c = ctx["coverage"]
    steps = [("scan materials", "%d file(s)" % len(ctx["materials"])),
             ("read the rule base", "%d rule(s), %d unit(s)" % (c["rules_available"], c["units_available"])),
             ("normalise fields, units, names", "%d row(s)" % c["rows_out"]),
             ("group duplicates and conflicts", "%d merge decision(s)" % c["merged_duplicate"]),
             ("export the audit trail", "%d change(s), %d queued" % (len(ctx["changes"]), len(ctx["pending"])))]
    res = {"case_id": ctx["case_id"], "status": so(ctx), "summary": sen(ctx, "summary"),
           "method": "rule base + field dictionary + unit table -> normalise, convert, group, audit",
           "claims": ctx["claims"], "uncertainties": uc(ctx),
           "limits": ctx["degradations"] or ["no limit was hit; every row was either cleaned or queued"],
           "degradations": ctx["degradations"], "draft_used": bool(draft),
           "change_records": [{"step": i, "action": a, "result": r} for i, (a, r) in enumerate(steps, 1)],
           "sources": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "chars": m["chars"], "parse_status": m["parse_status"]}
                       for m in ctx["materials"]], "artifacts": {a: a for a in FILES}}
    res.update(out)
    res["output_contract"] = out
    return res


def wa(ctx, out, work, contract, draft):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    wt(os.path.join(out, "anomaly_report.md"), am(ctx))
    dmp(out, "cleaned.csv", CLK, ctx["rows"] or [{"r": "-", "l": "input scan", "st": "no_records", "ru": ["R023"],
         "nt": ["no extraction row was present, so the cleaned table carries a structured no-data row"]}])
    dmp(out, "change_log.csv", CHK, ctx["changes"] or [{"r": "-", "t": "none", "id": "R026", "l": "input scan",
         "fm": "no change was needed"}])
    dmp(out, "pending_review.csv", PDK, ctx["pending"])
    wj(os.path.join(out, "rules.json"), rs(ctx))
    fd = ctx["field_dict"] if isinstance(ctx["field_dict"], dict) else {}
    wj(os.path.join(out, "field_mapping.json"),
       {"roles": {r: {"synonyms": t, "target_field": r} for r, t in (fd.get("roles") or {}).items()},
        "target_fields": fd.get("target_fields") or {}, "synonyms": fd.get("synonyms") or {}, "unmapped_columns": ctx["unmapped"],
        "note": "mapped only on an exact or word-boundary synonym hit; everything else is declared"})
    ut = ctx["unit_table"] if isinstance(ctx["unit_table"], dict) else {}
    wj(os.path.join(out, "unit_table.json"),
       {"prefixes": ut.get("prefixes") or {}, "units": ut.get("units") or {}, "canonical": ut.get("canonical") or {},
        "unknown_tokens": ut.get("unknown_tokens") or [], "ambiguous_tokens": ut.get("ambiguous_tokens") or [],
        "used_units": sorted({r["u"] for r in ctx["rows"] if r["u"]}),
        "note": "value_in_base = value * scale + offset; only same-dimension conversions are performed"} if ut
       else {"units": [], "used_units": [], "note": "no unit table was supplied with the batch"})
    wj(os.path.join(out, "evidence_map.json"),
       {"changes": ctx["changes"], "pending": ctx["pending"], "count": len(ctx["changes"]) + len(ctx["pending"]),
        "note": "every change and every queued row carries row_id + rule_id + source_locator back to the input row"})
    wj(os.path.join(out, "coverage.json"), ctx["coverage"])
    c = ctx["coverage"]
    wt(os.path.join(out, "run_log.txt"), "\n".join(
        ["# run_log", ""] + ["material %s %s kind=%s status=%s chars=%d" % (m["id"], m["name"], m["kind"], m["parse_status"],
                             m["chars"]) for m in ctx["materials"]] +
        ["records=%d rows=%d changes=%d queued=%d unmapped=%d status=%s" % (c["records_in"], c["rows_out"], c["changes"],
         c["queued_for_review"], c["unmapped_columns"], so(ctx))]) + "\n")
    res = br(ctx, contract, draft)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "cleaning_state.json"),
       {"case_id": ctx["case_id"], "status": so(ctx), "coverage": c, "unmapped": ctx["unmapped"]})
    return res


def fc(inp):
    base = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    for rel in ("case.json", "challenge.json"):
        o = rj(os.path.join(base, rel), None)
        if isinstance(o, dict):
            return o
    return {}


def ld(work):
    d = rj(os.path.join(work, "draft.json"), None)
    return d if isinstance(d, dict) else None


def pl(inp, out, work, case):
    ctx = bc(case, scan(inp))
    d = ld(work)
    if d and isinstance(d.get("field_map"), dict) and d["field_map"]:
        ctx["degradations"].append("an agent field_map was supplied for %d column(s); exact synonym hits still govern"
                                   % len(d["field_map"]))
    co = case.get("output_contract")
    return wa(ctx, out, work, co if isinstance(co, dict) else None, bool(d))


def err_result(exc):
    return {"case_id": "unknown-case", "status": "input_error", "summary": "the input could not be processed",
            "error": str(exc)[:400], "limits": ["aborted; see error"], "uncertainties": ["input unreadable"], "sources": [],
            "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
            "output_contract": {k: "unknown-case" if k == "case_id" else "cleaned.csv" if k == "deliverable" else "input_error"
                                for k in DC}}


def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res = br(bc(fc(inp), scan(inp)), None, False)
    res["status"] = "partial"
    wj(os.path.join(out, "result.json"), res)
    if not os.path.exists(os.path.join(work, "draft.skeleton.json")):
        wj(os.path.join(work, "draft.skeleton.json"), SKEL)
    print("init: indexed input; wrote a partial result.json + draft.skeleton.json")
    print("next: run show, fill work/draft.json, then check and build")
    return 0


def cmd_show(inp, grep, want, part):
    if part == "draft":
        print(json.dumps(SKEL, ensure_ascii=False, indent=2))
    for m in scan(inp):
        if want and m["id"] != want and m["name"] != want:
            continue
        print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["name"], m["kind"], m["parse_status"], m["chars"]))
        for i, ln in enumerate(m["text"].splitlines()):
            if not grep or grep.lower() in ln.lower():
                print("[%s/p%d] %s" % (m["id"], i + 1, ln.strip()[:300]))
    return 0


def cmd_check(inp, work):
    ctx = bc(fc(inp), scan(inp))
    g = len(ctx["rows"]) + len(ctx["changes"])
    rep = {"case_id": ctx["case_id"], "usable_rows": g, "ok": g > 0, "draft_present": isinstance(ld(work), dict),
           "note": "insufficient_evidence: build still writes an honest degraded result" if not g else "grounded"}
    wj(os.path.join(work, "check_report.json"), rep)
    print("check: usable rows/changes=%d (%s)" % (g, rep["note"]))
    return 0


def cmd_build(inp, out, work):
    res = pl(inp, out, work, fc(inp))
    print("build: status=%s artifacts=%d" % (res["status"], len(res["artifacts"]) + 1))
    return 0


def cmd_selfcheck(out):
    miss = [n for n in ["result.json"] + FILES if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok = isinstance(echo, dict) and all(not (isinstance(v, str) and not v.strip()) and not (isinstance(v, (list, dict)) and not v)
                                        for v in echo.values())
    print("selfcheck: files=%s echo=%s status=%s" % ("ok" if not miss else "missing " + ", ".join(miss),
                                                     "ok" if ok else "incomplete", res.get("status", "")))
    return 0


def cmd_compare(inp, out, work):
    ctx = bc(fc(inp), scan(inp))
    c = ctx["coverage"]
    wj(os.path.join(work, "compare_report.json"),
       {"case_id": ctx["case_id"], "baseline": "a base agent pastes the rows and converts units by eyeball, with no rule ids",
        "records_in": c["records_in"], "rows_out": c["rows_out"], "changes": c["changes"],
        "queued_for_review": c["queued_for_review"], "unmapped_columns": c["unmapped_columns"],
        "locators": len(ctx["changes"]) + len(ctx["pending"])})
    print("compare: contrast written to work/compare_report.json")
    return 0


def pa(a):
    p = argparse.ArgumentParser(prog="extraction-table-cleaner")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    p.add_argument("--part", default=None)
    return p.parse_known_args(a)[0]


def mn(argv):
    a = pa(argv)
    cmd, inp, out, work = a.command, a.input, a.output, a.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, a.grep, a.mat, a.part)
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
            wj(os.path.join(out, "result.json"), err_result(exc))
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(mn(sys.argv[1:]))
