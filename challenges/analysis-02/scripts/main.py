import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dataio as D
import engine as E
import report as R
import stats as S

SUPPORTED = ["two_independent_groups", "multi_group", "paired", "correlation", "regression",
             "contingency", "descriptive"]
METHODS = ["student_t", "mann_whitney_u", "one_way_anova", "kruskal_wallis", "paired_t",
           "wilcoxon_signed_rank", "pearson_r", "spearman_rho", "ols_slope", "fisher_exact",
           "descriptive"]
ENTRY = ("python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output "
         "--work /app/work")

def find_case(inp):
    obj = D.rj(os.path.join(inp, "case.json"))
    return obj if isinstance(obj, dict) else {}

def contract_of(case):
    c = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(c, dict) and c:
        return [str(k) for k in c.keys()], dict((str(k), c[k]) for k in c)
    return list(E.KEYS), dict(E.KEY_TEXT)

def read_draft(work):
    p = os.path.join(work, "draft.json")
    if not os.path.isfile(p):
        return {}, "no draft was read, so the documented defaults and the input columns decide"
    try:
        with open(p, "r", encoding="utf-8-sig") as fh:
            obj = json.load(fh)
    except Exception as exc:
        return {}, "work/draft.json is not valid JSON (%s); the documented defaults were used" % str(exc)[:60]
    if not isinstance(obj, dict):
        return {}, "work/draft.json does not hold an object; the documented defaults were used"
    return obj, "work/draft.json was read"

def items_of(draft):
    for k in ("items", "decisions"):
        v = (draft or {}).get(k)
        if isinstance(v, list):
            return v
    return []

def plan_of(draft, columns=None):
    names = [c["name"] for c in (columns or [])]
    plan = {"missing": {"policy": "mark_only", "columns": []},
            "duplicates": {"policy": "drop_exact", "keys": []},
            "outliers": {"policy": "flag", "rule": "tukey_1.5iqr", "columns": []}}
    applied, rejected = [], []
    dp = (draft or {}).get("data_plan") if isinstance(draft, dict) else None
    spec = (("missing", ("listwise", "pairwise", "mark_only"), "columns"),
            ("duplicates", ("drop_exact", "keep", "flag_only"), "keys"),
            ("outliers", ("keep", "flag", "winsorize", "exclude"), "columns"))
    if isinstance(dp, dict):
        for key, allowed, lk in spec:
            src = dp.get(key)
            if not isinstance(src, dict):
                continue
            pol = src.get("policy")
            if pol in allowed:
                plan[key]["policy"] = pol
                applied.append({"field": "data_plan.%s.policy" % key, "value": pol})
            elif pol:
                rejected.append({"field": "data_plan.%s.policy" % key, "value": str(pol)[:40],
                                 "reason": "the policy is not one of " + "/".join(allowed)})
            vals = src.get(lk)
            if isinstance(vals, list) and vals:
                known = [v for v in vals if not names or v in names]
                unknown = [v for v in vals if names and v not in names]
                if known:
                    plan[key][lk] = known
                if unknown:
                    rejected.append({"field": "data_plan.%s.%s" % (key, lk),
                                     "value": ", ".join(str(v) for v in unknown[:6]),
                                     "reason": "the column is not in the loaded table"})
        rule = (dp.get("outliers") or {}).get("rule") if isinstance(dp.get("outliers"), dict) else None
        if rule in ("tukey_1.5iqr", "z3"):
            plan["outliers"]["rule"] = rule
        units = dp.get("units") if isinstance(dp.get("units"), dict) else {}
        for col, unit in units.items():
            if col in names and str(unit).strip():
                applied.append({"field": "data_plan.units.%s" % col, "value": str(unit)[:24]})
            elif names:
                rejected.append({"field": "data_plan.units.%s" % col, "value": str(unit)[:24],
                                 "reason": "the column is not in the loaded table"})
    return plan, applied, rejected

def build_ctx(inp, case, draft, errors=None):
    mats = D.scan_materials(inp)
    ds, notes = D.load_primary(mats)
    plan, applied, rejected = plan_of(draft, (ds or {}).get("columns"))
    ctx = {"inp": inp, "case": case, "case_id": (case or {}).get("case_id") or "case-unknown",
           "materials": mats, "notes": list(notes), "dataset": ds, "plan": plan, "applied": applied,
           "rejected": rejected, "errors": list(errors or []), "degradations": [], "rows": [],
           "rules": [], "removed": 0, "questions": [], "decisions": [], "ledger": [], "evidence": [],
           "charts": {}, "families": 0, "draft": draft,
           "rels": (ds or {}).get("source") or (mats[0]["rel"] if mats else "no material")}
    if ds:
        ctx["rows"], ctx["rules"], ctx["removed"] = D.clean(ds, plan)
        if not any(c["type"] == "number" for c in ds["columns"]):
            ctx["degradations"].append({"kind": "no_analyzable_data",
                                        "detail": "the loaded table carries no numeric column",
                                        "effect": "no question can be built, so the ledger stays empty"})
        else:
            ctx["questions"] = E.questions_of(ctx)
            ctx["decisions"], ctx["ledger"], ctx["evidence"], ctx["charts"] = E.run_questions(ctx)
            ctx["families"] = E.apply_correction(ctx["ledger"])
    else:
        ctx["degradations"].append({"kind": "draft_missing" if not draft else "no_decisions",
                                    "detail": "no table with numeric columns was loaded",
                                    "effect": "the ledger stays empty and every key states its reason"})
    if not ctx["questions"]:
        ctx["degradations"].append({"kind": "no_analyzable_data",
                                    "detail": "no question could be built from the loaded columns",
                                    "effect": "the ledger stays empty and the report says so"})
    for m in mats:
        if m["status"] in ("invalid-json", "unparsed-binary", "empty-file"):
            ctx["degradations"].append({"kind": "index_note", "detail": "%s is %s: %s"
                                        % (m["rel"], m["status"], m["reason"]),
                                        "effect": "the file is kept in the snapshot and never used as data"})
    ctx["status"] = status_of(ctx)
    ctx["uncertainties"] = uncertainties_of(ctx)
    return ctx

def status_of(ctx):
    led = ctx["ledger"]
    if not led:
        return "insufficient_evidence"
    if not any(r["family"] == "primary" for r in led):
        return "partial"
    return "partial" if any(d["status"] == "skipped" for d in ctx["decisions"]) else "ok"

def uncertainties_of(ctx):
    out = []
    for d in ctx["decisions"]:
        if d["status"] == "skipped":
            out.append("decision %s (%s) was skipped: %s" % (d["decision_id"], d["design"],
                                                             d.get("reason") or "; ".join(d["notes"])))
        for c in d.get("candidates") or []:
            if c.get("reason"):
                out.append("%s could not run in %s: %s" % (c["method"], d["decision_id"], c["reason"]))
    for c in (ctx["dataset"] or {}).get("columns", []):
        if c["type"] == "number" and not c["unit"]:
            out.append("column %s declares no unit, so its numbers are reported in the unit of the input"
                       % c["name"])
    out.extend(ctx["notes"])
    if not out:
        out.append("no uncertainty beyond the limits below was identified in this run: every gate "
                   "verdict and every count is printed next to the number it belongs to")
    return out[:24]

def draft_check(ctx, dnote):
    cols = [c["name"] for c in (ctx["dataset"] or {}).get("columns", [])]
    draft = ctx.get("draft") or {}
    accepted, rejected = list(ctx["applied"]), list(ctx["rejected"])
    for it in items_of(draft):
        if not isinstance(it, dict):
            rejected.append({"field": "items[]", "value": str(it)[:40],
                             "reason": "the item is not an object"})
            continue
        did = str(it.get("decision_id") or "D-??")
        bad = 0
        if it.get("design") and it["design"] not in SUPPORTED:
            rejected.append({"field": "%s.design" % did, "value": str(it["design"])[:40],
                             "reason": "the design is not one of " + "/".join(SUPPORTED)})
            bad += 1
        if it.get("chosen_method") and it["chosen_method"] not in METHODS:
            rejected.append({"field": "%s.chosen_method" % did, "value": str(it["chosen_method"])[:40],
                             "reason": "the method is not in this skill's set"})
            bad += 1
        for k, v in (it.get("variables") or {}).items():
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, str) and x and cols and x not in cols:
                    rejected.append({"field": "%s.variables.%s" % (did, k), "value": x,
                                     "reason": "the column is not in the loaded table"})
                    bad += 1
        if it.get("question_id") and it["question_id"] not in [q["id"] for q in ctx["questions"]]:
            rejected.append({"field": "%s.question_id" % did, "value": str(it["question_id"])[:20],
                             "reason": "the question id is not in the question list of this input"})
            bad += 1
        if not bad:
            accepted.append({"field": "%s.decision" % did, "value": did,
                             "reason": "the design, the method and the columns are usable here"})
    return {"schema": "draft-check/1", "case_id": ctx["case_id"], "draft": dnote,
            "columns_in_table": cols, "accepted": accepted, "rejected": rejected,
            "questions": [q["id"] for q in ctx["questions"]], "plan": ctx["plan"],
            "verdict": "the draft was applied where its columns and methods exist; every rejected "
                       "field is listed with its reason",
            "note": "the input always wins over the draft: a rejected field is reported, never used"}

def build(inp, out, work, quiet=False):
    for d in (out, work, os.path.join(out, "charts"), os.path.join(out, "raw_snapshot"),
              os.path.join(out, "logs")):
        os.makedirs(d, exist_ok=True)
    case = find_case(inp)
    draft, dnote = read_draft(work)
    ctx = build_ctx(inp, case, draft)
    ckeys, ctext = contract_of(case)
    contract = E.contract_values(ctx, ckeys)
    D.snapshot(ctx["materials"], out)
    charts = R.draw_charts(ctx, out)
    R.write_cleaned(ctx, out)
    R.write_stats(ctx, out)
    ev = R.evidence_rows(ctx)
    summary = {"materials": len(ctx["materials"]), "tables_loaded": 1 if ctx["dataset"] else 0,
               "rows_read": ctx["dataset"]["n_rows"] if ctx["dataset"] else 0,
               "rows_after_cleaning": len(ctx["rows"]), "rows_removed": ctx["removed"],
               "numeric_columns": sum(1 for c in (ctx["dataset"] or {}).get("columns", [])
                                      if c["type"] == "number"),
               "questions": len(ctx["questions"]), "decisions": len(ctx["decisions"]),
               "decisions_skipped": sum(1 for d in ctx["decisions"] if d["status"] == "skipped"),
               "ledger_rows": len(ctx["ledger"]),
               "inferential_rows": sum(1 for r in ctx["ledger"] if r["family"] == "primary"),
               "descriptive_rows": sum(1 for r in ctx["ledger"] if r["family"] == "descriptive"),
               "corrected_rows": ctx["families"], "evidence_rows": len(ev),
               "figures": len(charts)}
    wj = R.wj
    wj(os.path.join(out, "evidence.json"),
       {"schema": "evidence/1", "case_id": ctx["case_id"], "source": ctx["rels"], "rows": ev,
        "count": len(ev),
        "note": "every row names the column or the decision it came from and carries the first 16 hex "
                "digits of the SHA-256 of its own quote, so a reviewer can re-hash it"})
    prim = [r["result_id"] for r in ctx["ledger"] if r["family"] == "primary"]
    desc = [r["result_id"] for r in ctx["ledger"] if r["family"] == "descriptive"]
    wj(os.path.join(out, "results_ledger.json"),
       {"schema": "results-ledger/1", "case_id": ctx["case_id"], "seed": S.SEED,
        "families": {"primary": {"size": len(prim), "correction": "holm", "source": "auto",
                                 "members": prim},
                     "descriptive": {"size": len(desc), "correction": "not_applied", "source": "auto",
                                     "members": desc}},
        "rows": ctx["ledger"],
        "note": "selected marks the one row the gates chose for a question; the other rows of that "
                "question were computed so the decision log can show they were considered"})
    wj(os.path.join(out, "decision_log.json"),
       {"schema": "decision-log/1", "case_id": ctx["case_id"], "seed": S.SEED, "draft": dnote,
        "plan": ctx["plan"], "plan_applied": ctx["applied"], "plan_rejected": ctx["rejected"],
        "questions": ctx["questions"], "decisions": ctx["decisions"],
        "note": "gate order: sample size, normality, equal variance, independence, multiplicity family"})
    lines = R.report_lines(ctx, summary, charts)
    R.txt(os.path.join(out, "report.md"), "\n".join(lines) + "\n")
    R.write_pdf(os.path.join(out, "report.pdf"), lines)
    R.txt(os.path.join(out, "logs", "run.log"),
          "\n".join(["analysis-02 run log", "case_id=%s" % ctx["case_id"], "source=%s" % ctx["rels"],
                     "materials_scanned=%d" % len(ctx["materials"]),
                     "records_read=%d records_after_cleaning=%d removed=%d"
                     % (summary["rows_read"], summary["rows_after_cleaning"], summary["rows_removed"]),
                     "cleaning_steps=%d" % len(ctx["rules"]), "questions=%d" % len(ctx["questions"]),
                     "ledger_rows=%d evidence_rows=%d figures=%d"
                     % (len(ctx["ledger"]), len(ev), len(charts)),
                     "degradations=%s" % "; ".join(d["kind"] for d in ctx["degradations"]),
                     "draft=%s" % dnote, ""]) + "\n")
    wj(os.path.join(out, "reproducibility.json"), R.write_repro(ctx, out))
    unk = [k for k, v in contract.items() if isinstance(v, dict) and v.get("computed") is False]
    result = {"case_id": ctx["case_id"], "status": ctx["status"], "output_contract": contract,
              "contract": {"keys": ckeys, "declared_in": "case.json output_contract", "text": ctext,
                           "note": "every key carries either the block the gates selected or the "
                                   "reason it could not run"},
              "summary": summary,
              "sources": [{"rel": m["rel"], "kind": m["kind"], "status": m["status"],
                           "bytes": m["bytes"], "sha256_16": m["sha256_16"],
                           "used_as_data": bool(ctx["dataset"] and m["rel"] == ctx["dataset"]["source"]),
                           "reason": m["reason"] or "-"} for m in ctx["materials"]],
              "degradations": ctx["degradations"], "uncertainties": ctx["uncertainties"],
              "limits": R.LIMITS, "lint": {"banned_expressions": R.BANNED,
                                           "hits": R.banned_hits("\n".join(lines)),
                                           "verdict": R.lint_note("\n".join(lines))},
              "change_records": [{"change": dnote, "kind": "draft_read",
                                  "effect": "policies and columns from the draft were applied where the "
                                            "column exists in the loaded table"}] +
                                 [{"change": "draft field rejected", "kind": "field_rejected",
                                   "field": r["field"], "value": r["value"], "reason": r["reason"]}
                                  for r in ctx["rejected"]] +
                                 [{"change": "draft field applied", "kind": "field_applied",
                                   "field": a["field"], "value": a["value"],
                                   "reason": "the column exists in the loaded table"} for a in ctx["applied"]] +
                                 [{"change": "cleaning step counted", "kind": "cleaning",
                                   "field": r["step"], "value": r.get("column") or r.get("keys"),
                                   "reason": r.get("action", "")} for r in ctx["rules"]] +
                                 [{"change": "material not used as data", "kind": "index_note",
                                   "field": m["rel"], "value": m["status"], "reason": m["reason"]}
                                  for m in ctx["materials"] if m["status"] != "loaded"] +
                                 [{"change": "contract key has no question in this input",
                                   "kind": "key_reason", "field": k, "value": "computed: false",
                                   "reason": v.get("reason", "")} for k, v in contract.items()
                                  if k in unk],
              "artifacts": R.declared_pairs(out),
              "reproducibility": {"seed": S.SEED, "python": sys.version.split()[0],
                                  "deterministic": True, "entry": ENTRY},
              "engine": {"entry": "scripts/main.py",
                         "modules": ["scripts/main.py", "scripts/engine.py", "scripts/stats.py",
                                     "scripts/dataio.py", "scripts/report.py"],
                         "gate_order": ["sample size", "normality", "equal variance", "independence",
                                        "multiplicity family"],
                         "no_external_package": True},
              "draft": {"read": bool(draft), "note": dnote, "items": len(items_of(draft)),
                        "rejected_fields": ctx["rejected"]}}
    wj(os.path.join(out, "result.json"), result)
    sc = R.selfcheck(ctx, out, contract)
    wj(os.path.join(out, "self_check.json"), sc)
    wj(os.path.join(work, "check_report.json"), draft_check(ctx, dnote))
    if not quiet:
        print("analysis-02 %s: status=%s ledger=%d evidence=%d figures=%d selfcheck=%s"
              % (ctx["case_id"], ctx["status"], len(ctx["ledger"]), len(ev), len(charts), sc["status"]))
        for c in sc["checks"]:
            if c["status"] != "PASS":
                print("  [%s] %s: %s" % (c["status"], c["id"], c["detail"]))
    return ctx, result, sc

def naive(inp):
    mats = D.scan_materials(inp)
    ds, _ = D.load_primary(mats)
    m = {"records_analysed": ds["n_rows"] if ds else 0, "cleaning_steps": 0, "tests_run": 0,
         "gate_checks": 0, "effect_sizes": 0, "confidence_intervals": 0, "corrections": 0,
         "evidence_rows": 0, "figures": 0, "artifacts": 1, "degradations_declared": 0}
    if not ds:
        return m
    cats = [c["name"] for c in ds["columns"]
            if c["type"] != "number" and 2 <= c.get("distinct", 0) <= 5]
    if not cats:
        cats = [c["name"] for c in ds["columns"] if c["type"] != "number"]
    nums = [c["name"] for c in ds["columns"] if c["type"] == "number" and c["n_number"] >= 8]
    if cats and nums:
        g = D.group_values(ds["rows"], cats[0], nums[0])
        lv = sorted(g)
        if len(lv) >= 2 and S.student_t(g[lv[0]], g[lv[1]]).get("ok"):
            m["tests_run"], m["confidence_intervals"] = 1, 1
    return m

def cmd_compare(inp, out, work):
    ctx, result, _ = build(inp, out, work, quiet=True)
    b = naive(inp)
    s = {"records_analysed": result["summary"]["rows_read"], "cleaning_steps": len(ctx["rules"]),
         "tests_run": result["summary"]["inferential_rows"],
         "gate_checks": sum(len(d.get("gate_results") or {}) for d in ctx["decisions"]),
         "effect_sizes": len([r for r in ctx["ledger"] if r["effect_size"]["value"] not in ("", None)]),
         "confidence_intervals": len([r for r in ctx["ledger"] if len(r["ci_95"]) == 2]),
         "corrections": result["summary"]["corrected_rows"],
         "evidence_rows": result["summary"]["evidence_rows"], "figures": result["summary"]["figures"],
         "artifacts": len(R.ARTIFACTS), "degradations_declared": len(ctx["degradations"])}
    rep = {"schema": "compare/1", "case_id": result["case_id"], "source": ctx["rels"],
           "baseline": {"what": "load the table at face value, print a mean per column and run one "
                                "t test on the first two levels: no plan, no gate, no interval and no "
                                "locator", "measures": b},
           "skill": {"what": "this package on the same input in the same run", "measures": s},
           "delta": dict((k, s[k] - b[k]) for k in b),
           "note": "both columns are measured on the same input in this run, so the GAIN_EVIDENCE "
                   "table can be re-derived instead of believed"}
    R.wj(os.path.join(work, "compare_report.json"), rep)
    print("compare on %s: baseline %s | skill %s" % (ctx["rels"], b, s))
    return rep

def cmd_show(inp, out, work):
    ctx = build_ctx(inp, find_case(inp), read_draft(work)[0])
    print("case_id: %s · source table: %s" % (ctx["case_id"], ctx["rels"]))
    for m in ctx["materials"]:
        print("  %s %-30s %-14s %8d B  %s" % (m["id"], m["rel"], m["status"], m["bytes"],
                                              m["reason"] or "-"))
    for c in (ctx["dataset"] or {}).get("columns", []):
        print("  column %-22s %-8s n=%d missing=%d distinct=%d unit=%s"
              % (c["name"], c["type"], c["n_number"], c["missing"], c["distinct"],
                 c["unit"] or "not declared"))
    for q in ctx["questions"]:
        print("  %s %-16s %s" % (q["id"], q["kind"], q["text"]))
    print("cleaning plan: %s" % json.dumps(ctx["plan"], ensure_ascii=False))
    return ctx

def cmd_init(inp, out, work):
    ctx = build_ctx(inp, find_case(inp), read_draft(work)[0])
    os.makedirs(work, exist_ok=True)
    items = []
    for q in ctx["questions"]:
        v = {}
        for k in ("group", "outcome", "x", "y", "row", "col", "first", "second"):
            if q.get(k):
                v["x" if k in ("row", "first") else "y" if k in ("col", "second") else k] = q[k]
        items.append({"decision_id": "D-%02d" % (len(items) + 1), "question_id": q["id"],
                      "field": "decision", "design": q["kind"], "variables": v, "chosen_method": "",
                      "locator": "", "why": "",
                      "note": "fill chosen_method with a method from the skill set, or leave it empty "
                              "and let the gates choose"})
    R.wj(os.path.join(work, "draft_candidates.json"),
         {"schema": "draft-candidates/1", "case_id": ctx["case_id"], "items": items,
          "data_plan": ctx["plan"],
          "columns": [c["name"] for c in (ctx["dataset"] or {}).get("columns", [])],
          "note": "this file lists what an agent may fill in; it is never read back as a decision. "
                  "Copy the parts you agree with into draft.json and run the check entry point."})
    print("init: wrote draft_candidates.json with %d candidate decision(s); the skill never reads it "
          "back" % len(items))
    return items

def cmd_check(inp, out, work):
    draft, dnote = read_draft(work)
    ctx = build_ctx(inp, find_case(inp), draft)
    chk = draft_check(ctx, dnote)
    R.wj(os.path.join(work, "check_report.json"), chk)
    print("check: %s · accepted=%d rejected=%d" % (dnote, len(chk["accepted"]), len(chk["rejected"])))
    for r in chk["rejected"]:
        print("  rejected %s = %r: %s" % (r["field"], r["value"], r["reason"]))
    return chk

def main(argv=None):
    ap = argparse.ArgumentParser(description="analysis-02: research data to a checked report")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "build", "selfcheck", "init", "show", "check", "compare"])
    ap.add_argument("--input", default=os.environ.get("INPUT", "/input"))
    ap.add_argument("--output", default=os.environ.get("OUTPUT", "/app/output"))
    ap.add_argument("--work", default=os.environ.get("WORK", "/app/work"))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "show":
            cmd_show(a.input, a.output, a.work)
        elif a.cmd == "init":
            cmd_init(a.input, a.output, a.work)
        elif a.cmd == "check":
            cmd_check(a.input, a.output, a.work)
        elif a.cmd == "compare":
            cmd_compare(a.input, a.output, a.work)
        else:
            build(a.input, a.output, a.work)
    except Exception as exc:
        try:
            os.makedirs(a.output, exist_ok=True)
            R.wj(os.path.join(a.output, "result.json"),
                 {"case_id": "unknown", "status": "input_error", "output_contract": {},
                  "error": {"type": type(exc).__name__, "message": str(exc)[:400]},
                  "sources": [{"rel": a.input, "status": "read_failed"}],
                  "uncertainties": ["the run stopped early: %s" % str(exc)[:200]],
                  "change_records": [{"change": "run stopped before the artifacts were complete",
                                      "kind": "input_error", "reason": str(exc)[:200]}],
                  "limits": R.LIMITS,
                  "note": "a partial result is saved so the failure can be located instead of hidden"})
        except Exception:
            pass
        print("analysis-02 stopped early: %s: %s" % (type(exc).__name__, str(exc)[:200]))
    return 0

if __name__ == "__main__":
    sys.exit(main())
