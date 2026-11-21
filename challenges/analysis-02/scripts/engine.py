import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dataio as D
import stats as S

KEYS = ["student_t", "mann_whitney_u", "kruskal_wallis", "wilcoxon_signed_rank",
        "spearman_rho", "ols_slope", "fisher_exact", "descriptive"]
KEY_TEXT = dict((k, "the %s block from this run, or the reason it did not run" % k) for k in KEYS)
SIB = {"kruskal_wallis": "one_way_anova", "wilcoxon_signed_rank": "paired_t",
       "spearman_rho": "pearson_r"}
BASIS = {"paired": ["the rows are the pairing unit"], "correlation": ["two numeric columns"],
         "regression": ["two numeric columns", "a constant residual spread"],
         "contingency": ["a 2x2 table", "independent records"],
         "descriptive": ["one measurement per row"]}
PAIRS = [("pre", "post"), ("before", "after"), ("run1", "run2"), ("baseline", "follow"),
         ("week0", "week4")]
REQ = {"student_t": "two independent groups with at least eight records each",
       "mann_whitney_u": "two independent groups with at least three records each",
       "kruskal_wallis": "three or more groups with three records each",
       "wilcoxon_signed_rank": "a declared paired structure with at least six usable pairs",
       "spearman_rho": "two numeric columns with at least four complete pairs",
       "ols_slope": "two numeric columns with a varying predictor",
       "fisher_exact": "two two-level columns forming a 2x2 table",
       "descriptive": "at least one numeric column"}

def levels_of(rows, col, limit=8):
    out = {}
    for r in rows:
        v = r.get(col)
        v = "" if v is None else str(v).strip()
        if v:
            out[v] = out.get(v, 0) + 1
    out = dict((k, v) for k, v in out.items() if v >= 3)
    return out if 1 < len(out) <= limit else {}

def questions_of(ctx):
    ds, rows = ctx["dataset"], ctx["rows"]
    cols = ds["columns"]
    nums = [c["name"] for c in cols if c["type"] == "number" and c["n_number"] >= 8]
    cats = [c["name"] for c in cols if c["type"] != "number"]
    if not nums:
        return []
    two = [c for c in cats if len(levels_of(rows, c)) == 2]
    multi = [c for c in cats if len(levels_of(rows, c)) >= 3]
    qs = [{"id": "Q1", "kind": "descriptive", "columns": nums,
           "text": "what does each numeric column look like, with its unit and spread?"}]
    if two:
        qs.append({"id": "Q2", "kind": "two_groups", "outcome": nums[0], "group": two[0],
                   "text": "do the two levels of %s differ in %s?" % (two[0], nums[0])})
    if multi:
        qs.append({"id": "Q3", "kind": "multi_groups", "outcome": nums[0], "group": multi[0],
                   "text": "do the %d levels of %s differ in %s?"
                           % (len(levels_of(rows, multi[0])), multi[0], nums[0])})
    if len(two) >= 2:
        qs.append({"id": "Q4", "kind": "contingency", "row": two[0], "col": two[1],
                   "text": "are %s and %s associated?" % (two[0], two[1])})
    if len(nums) >= 2:
        qs.append({"id": "Q5", "kind": "association", "x": nums[1], "y": nums[0],
                   "text": "how strongly do %s and %s move together, and what is the slope?"
                           % (nums[1], nums[0])})
    for a, b in PAIRS:
        ca = [c for c in nums if a in c.lower()]
        cb = [c for c in nums if b in c.lower()]
        if ca and cb:
            qs.append({"id": "Q6", "kind": "paired", "first": ca[0], "second": cb[0],
                       "text": "do the paired values in %s change at %s?" % (ca[0], cb[0])})
            break
    return qs

def unit_of(ds, col):
    for c in ds["columns"]:
        if c["name"] == col:
            return c["unit"] or "not declared"
    return "not declared"

def _slug(s):
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(s))[:24].strip("_") or "col"

def gate_block(groups):
    ns = [len(g) for g in groups]
    return {"n": {"sizes": ns, "min_group_n": min(ns)},
            "normality": [dict(S.jarque_bera(g), group=i) for i, g in enumerate(groups)],
            "variance": S.brown_forsythe(groups) if len(groups) > 1
            else {"test": "brown_forsythe", "p": "", "verdict": "not_tested"},
            "independence": "records are read as independent; no clustering column was declared"}

def _why(nok, normok, varok):
    parts = []
    if not nok:
        parts.append("a group has fewer than eight observations")
    if not normok:
        parts.append("the normality gate failed")
    if not varok:
        parts.append("the equal-variance gate failed")
    return "; ".join(parts) or "no parametric gate was met"

def _lrow(did, res, etype, groups, unit, design, sel, notes=""):
    eff = res.get("effect_size") or {}
    return {"result_id": "%s-%s" % (did, res.get("test", "step")), "decision_id": did,
            "method": res.get("test", "step"), "estimate_type": etype, "groups": groups,
            "n": res.get("n") or [], "df": res.get("df"), "statistic_name": res.get("statistic_name"),
            "statistic": res.get("statistic"), "p": res.get("p"), "p_adj": "", "family": "primary",
            "effect_size": {"type": eff.get("type") or "-", "value": eff.get("value"),
                            "ci_95": eff.get("ci_95") or [], "ci_method": eff.get("ci_method") or "-",
                            "direction": eff.get("direction") or "-"},
            "estimate_point": res.get("difference") if res.get("difference") is not None else "",
            "ci_95": res.get("ci_95") or [], "ci_method": res.get("ci_method") or "-",
            "unit": unit, "design": design, "selected": bool(sel),
            "status": "done" if res.get("ok") else "failed",
            "notes": notes or res.get("reason") or ""}

def _try(cands, ledger, ids, did, res, m, etype, groups, unit, design, pick, why, extra=None):
    if not res.get("ok"):
        cands.append({"method": m, "assumptions": BASIS.get(design, ["independent groups"])
                      + list(extra or []) + ["enough usable records"],
                      "preconditions_met": False, "reason": res.get("reason")})
        return False
    sel = m == pick
    selnote = ("selected by the gates: " + why if sel else
               "computed for comparison only; the gates did not select it")
    ledger.append(_lrow(did, res, etype, groups, unit, design, sel, notes=selnote))
    ids.append("%s-%s" % (did, m))
    cands.append({"method": m, "assumptions": BASIS.get(design, ["independent groups"])
                  + list(extra or []), "preconditions_met": bool(sel), "selected": sel,
                  "rejected_reason": "" if sel else why})
    return sel

def run_questions(ctx):
    ds, rows = ctx["dataset"], ctx["rows"]
    decisions, ledger, evidence, charts = [], [], [], {}

    def add_chart(dcharts, payload, path, ctype, shows):
        charts[path] = dict(payload, type=ctype, shows=shows)
        dcharts.append({"type": ctype, "path": path, "shows": shows})

    for q in ctx["questions"]:
        did = "D-%02d" % (len(decisions) + 1)
        cands, gate, chosen, ids, notes, dcharts = [], {}, "", [], [], []
        if q["kind"] == "descriptive":
            for c in q["columns"]:
                d = S.descriptive(D.column_values(rows, c), unit_of(ds, c))
                if not d["n"]:
                    continue
                ledger.append({"result_id": "%s-%s" % (did, c), "decision_id": did,
                               "method": "descriptive", "estimate_type": "descriptive",
                               "groups": [c], "n": [d["n"]], "df": d["n"] - 1,
                               "statistic_name": "mean", "statistic": d["mean"], "p": "", "p_adj": "",
                               "family": "descriptive",
                               "effect_size": {"type": "sd", "value": d["sd"], "ci_95": [],
                                               "ci_method": "-", "direction": "spread of the values"},
                               "ci_95": d["mean_ci_95"], "ci_method": "analytic_large_sample",
                               "unit": d["unit"], "design": "descriptive", "selected": True,
                               "status": "descriptive_only",
                               "notes": "median %s, iqr %s, range %s to %s, skewness %s, excess "
                                        "kurtosis %s" % (S.fmt(d["median"]), S.fmt(d["iqr"]),
                                                         S.fmt(d["min"]), S.fmt(d["max"]),
                                                         S.fmt(d["skewness"]),
                                                         S.fmt(d["excess_kurtosis"]))})
                ids.append("%s-%s" % (did, c))
                evidence.append({"kind": "descriptive", "locator": "%s column %s" % (ds["source"], c),
                                 "quote": "n=%d, mean=%s, sd=%s, median=%s, unit=%s"
                                          % (d["n"], S.fmt(d["mean"]), S.fmt(d["sd"]),
                                             S.fmt(d["median"]), d["unit"])})
            chosen = "descriptive"
            cands = [{"method": "descriptive", "assumptions": ["one measurement per row"],
                      "preconditions_met": True, "selected": True}]
            gate = {"n": {"sizes": [len(D.column_values(rows, c)) for c in q["columns"]]},
                    "normality": [], "variance": {"verdict": "not_tested"},
                    "independence": "each row is one record"}
            add_chart(dcharts, {"kind": "hist", "column": q["columns"][0]},
                      "charts/histogram_%s.svg" % _slug(q["columns"][0]), "histogram",
                      "one bar per bin of %s, so the shape behind the mean is visible" % q["columns"][0])
        elif q["kind"] in ("two_groups", "multi_groups"):
            ocol = q["outcome"]
            groups = dict((k, v) for k, v in sorted(D.group_values(rows, q["group"], ocol).items())
                          if len(v) >= 2)
            groups = dict(list(groups.items())[:2 if q["kind"] == "two_groups" else 6])
            gate = {"levels_source": "column " + q["group"]}
            if len(groups) < 2:
                decisions.append({"decision_id": did, "question_id": q["id"], "design": q["kind"],
                                  "status": "skipped", "chosen_method": "", "text": q["text"],
                                  "reason": "fewer than two levels carry enough records",
                                  "candidates": [], "gate_results": gate, "result_ids": [],
                                  "charts": [], "levels": q["group"], "notes": notes,
                                  "multiple_comparison_family": "primary", "correction": "not needed"})
                continue
            vals, goal, unit = list(groups.values()), list(groups.keys()), unit_of(ds, ocol)
            gate.update(gate_block(vals))
            nok = gate["n"]["min_group_n"] >= 8
            normok = nok and all(x["verdict"] == "pass" for x in gate["normality"])
            varok = gate["variance"].get("verdict") == "pass"
            if q["kind"] == "two_groups":
                pair_list = ((S.student_t(vals[0], vals[1]), "student_t", "mean_difference",
                              ["normal residuals", "equal variance"]),
                             (S.mann_whitney_u(vals[0], vals[1]), "mann_whitney_u",
                              "rank_difference", []))
                pick = "student_t" if (nok and normok and varok) else "mann_whitney_u"
                why = ("both groups pass the normality and equal-variance gates with at least eight "
                       "records" if pick == "student_t" else "no parametric gate: "
                       + _why(nok, normok, varok))
                design = "two_independent_groups"
            else:
                pair_list = ((S.one_way_anova(vals), "one_way_anova", "omnibus_test",
                              ["normal residuals", "equal variance"]),
                             (S.one_way_ranks(vals), "kruskal_wallis", "omnibus_test", []))
                pick = "one_way_anova" if (nok and normok and varok) else "kruskal_wallis"
                why = ("every group passes the normality and equal-variance gates"
                       if pick == "one_way_anova" else "no parametric gate: " + _why(nok, normok, varok))
                design = "multi_group"
            for res, m, et, asum in pair_list:
                _try(cands, ledger, ids, did, res, m, et, goal, unit, design, pick, why, asum)
            chosen = pick
            for gname, gvals in groups.items():
                d = S.descriptive(gvals, unit)
                if not d["n"]:
                    continue
                evidence.append({"kind": "group_summary", "locator": "column %s level %s"
                                 % (q["group"], gname),
                                 "quote": "n=%d, median=%s, mean=%s, sd=%s"
                                          % (d["n"], S.fmt(d["median"]), S.fmt(d["mean"]),
                                             S.fmt(d["sd"]))})
            add_chart(dcharts, {"kind": "box", "groups": groups, "outcome": ocol, "unit": unit},
                      "charts/box_%s.svg" % _slug(ocol), "box_with_points",
                      "median, quartiles, fences, raw points and any point past a fence")
        elif q["kind"] == "paired":
            xs = D.column_values(rows, q["first"])
            ys = D.column_values(rows, q["second"])
            n = min(len(xs), len(ys))
            diffs = [ys[i] - xs[i] for i in range(n)]
            gate = {"n": {"sizes": [n], "min_group_n": n}, "normality": [S.jarque_bera(diffs)],
                    "variance": {"verdict": "not_tested"}, "independence": "-",
                    "levels_source": "paired rows of %s and %s" % (q["first"], q["second"])}
            nok = n >= 8 and gate["normality"][0]["verdict"] == "pass"
            pick = "paired_t" if nok else "wilcoxon_signed_rank"
            why = ("at least eight pairs with a normal difference" if nok else
                   "fewer than eight pairs or a non-normal difference")
            for res, m, et, asum in ((S.paired_t(diffs), "paired_t", "mean_difference",
                                      ["normal differences"]),
                                     (S.wilcoxon_signed_rank(diffs), "wilcoxon_signed_rank",
                                      "rank_difference", [])):
                _try(cands, ledger, ids, did, res, m, et, [q["first"], q["second"]],
                     unit_of(ds, q["first"]), "paired", pick, why, asum)
            chosen = pick
            add_chart(dcharts, {"kind": "scatter", "x": q["first"], "y": q["second"],
                                "title": "paired values: %s against %s" % (q["first"], q["second"])},
                      "charts/paired_%s.svg" % _slug(q["first"]), "paired_slope",
                      "each record as a point, with the line of equality for reference")
        elif q["kind"] == "contingency":
            lv_r = sorted(levels_of(rows, q["row"]).keys())
            lv_c = sorted(levels_of(rows, q["col"]).keys())
            table = [[0, 0], [0, 0]]
            for r in rows:
                a, b = str(r.get(q["row"], "")).strip(), str(r.get(q["col"], "")).strip()
                if a in lv_r and b in lv_c:
                    table[lv_r.index(a)][lv_c.index(b)] += 1
            fe = S.fisher_exact(table)
            gate = {"n": {"sizes": [sum(table[0]) + sum(table[1])],
                          "min_group_n": min(sum(table[0]), sum(table[1]))},
                    "normality": [], "variance": {"verdict": "not_tested"}, "independence": "-",
                    "levels_source": "columns " + " and ".join([q["row"], q["col"]])}
            ok = _try(cands, ledger, ids, did, fe, "fisher_exact", "association",
                      ["/".join(lv_r), "/".join(lv_c)], "-", "contingency", "fisher_exact",
                      "the exact test is the only 2x2 test this skill reports")
            if ok:
                chosen = "fisher_exact"
                notes.append("the smallest expected count is %s, so the exact test carries the finding"
                             % S.fmt(fe["expected_min"]))
                evidence.append({"kind": "table", "locator": "columns %s and %s" % (q["row"], q["col"]),
                                 "quote": "cells %s x %s = %s" % ("/".join(lv_r), "/".join(lv_c),
                                                                  fe["table"])})
            else:
                notes.append(fe.get("reason"))
            add_chart(dcharts, {"kind": "bars", "table": table, "row": lv_r, "col": lv_c},
                      "charts/bars_%s.svg" % _slug(q["row"]), "grouped_bar",
                      "how many records fall in each cell of the table")
        elif q["kind"] == "association":
            xs, ys = D.pair_values(rows, q["x"], q["y"])
            gate = {"n": {"sizes": [len(xs)], "min_group_n": len(xs)},
                    "normality": [S.jarque_bera(xs), S.jarque_bera(ys)],
                    "variance": {"verdict": "not_tested"}, "independence": "-",
                    "levels_source": "two numeric columns of the input"}
            okn = len(xs) >= 8 and all(g["verdict"] == "pass" for g in gate["normality"])
            pick = "pearson_r" if (okn and not S.tie_groups(xs + ys)) else "spearman_rho"
            why = ("both columns pass the normality gate and carry no ties" if pick == "pearson_r"
                   else "a normality gate failed or the values carry many ties")
            for res, m, et, asum in ((S.pearson_r(xs, ys), "pearson_r", "correlation",
                                      ["normal columns for the linear r"]),
                                     (S.spearman_rho(xs, ys), "spearman_rho", "correlation", [])):
                _try(cands, ledger, ids, did, res, m, et, [q["x"], q["y"]], "-", "correlation",
                     pick, why, asum)
            chosen = pick
            ol = S.ols_slope(xs, ys)
            if ol.get("ok"):
                _try(cands, ledger, ids, did, ol, "ols_slope", "slope", [q["x"], q["y"]],
                     unit_of(ds, q["y"]), "regression", "ols_slope", "a varying predictor")
                ledger[-1]["notes"] = ("the same pair read as a line; r squared %s"
                                       % S.fmt(ol.get("r_squared")))
                evidence.append({"kind": "fit", "locator": "columns %s and %s" % (q["x"], q["y"]),
                                 "quote": "slope %s %s per unit of %s, intercept %s, r squared %s"
                                          % (S.fmt(ol["statistic"]),
                                             unit_of(ds, q["y"]).replace("not declared", "unit"),
                                             q["x"], S.fmt(ol["intercept"]), S.fmt(ol.get("r_squared")))})
            else:
                cands.append({"method": "ols_slope", "assumptions": ["a varying predictor"],
                              "preconditions_met": False, "reason": ol.get("reason")})
            add_chart(dcharts, {"kind": "scatter", "x": q["x"], "y": q["y"],
                                "title": "%s against %s" % (q["y"], q["x"])},
                      "charts/scatter_%s.svg" % _slug(q["x"]), "scatter_fit",
                      "every pair, the fitted line and both axis ranges")
        fam = "descriptive" if q["kind"] == "descriptive" else "primary"
        decisions.append({"decision_id": did, "question_id": q["id"], "design": q["kind"],
                          "text": q["text"], "status": "done" if chosen else "skipped",
                          "gate_results": gate, "candidates": cands, "chosen_method": chosen,
                          "levels": q.get("group") or "", "multiple_comparison_family": fam,
                          "correction": ("not applied, a descriptive row carries no test" if fam == "descriptive"
                                         else "holm, inside a family with two or more inferential rows"),
                          "result_ids": ids, "charts": dcharts,
                          "chart": dcharts[0] if dcharts else {"type": "", "path": "", "shows": ""},
                          "notes": notes})
    return decisions, ledger, evidence, charts

def apply_correction(ledger):
    idx = [i for i, r in enumerate(ledger) if r["p"] not in ("", None) and r["family"] == "primary"]
    if len(idx) < 2:
        return 0
    for i, a in zip(idx, S.holm([float(ledger[i]["p"]) for i in idx])):
        ledger[i]["p_adj"] = a
    return len(idx)

def blk(row, ctx, note=""):
    d = dict((x["decision_id"], x) for x in ctx["decisions"]).get(row["decision_id"], {})
    return {"method": row["method"], "result_id": row["result_id"], "decision_id": row["decision_id"],
            "selected_by_gates": bool(row["selected"]), "design": row["design"],
            "estimate_type": row["estimate_type"], "groups": row["groups"], "n": row["n"],
            "df": row["df"], "statistic_name": row["statistic_name"], "statistic": row["statistic"],
            "p": row["p"], "p_adj": row["p_adj"], "ci_95": row["ci_95"],
            "ci_method": row["ci_method"], "effect_size": row["effect_size"], "unit": row["unit"],
            "status": row["status"], "gate_results": d.get("gate_results") or {},
            "candidates": d.get("candidates") or [], "note": note or row["notes"]}

def contract_values(ctx, ckeys):
    led = ctx["ledger"]
    out = {}
    for k in ckeys:
        if k == "descriptive":
            items = [{"column": r["groups"][0], "n": r["n"][0], "mean": r["statistic"],
                      "ci_95": r["ci_95"], "unit": r["unit"], "summary": r["notes"]}
                     for r in led if r["method"] == "descriptive"]
            out[k] = ({"method": "descriptive", "columns": len(items), "items": items,
                       "note": "one profile per numeric column; the spread is the sample standard "
                               "deviation and the interval is the 95% interval of the mean"}
                      if items else _none(k, "no numeric column with enough complete values was loaded",
                                          ctx))
            continue
        rows = [r for r in led if r["method"] == k] or \
            [r for r in led if r["method"] == SIB.get(k)]
        if rows:
            pick = [r for r in rows if r["selected"]] or rows
            out[k] = blk(pick[0], ctx,
                         ("%s is the method the gates selected for this question" % pick[0]["method"])
                         if pick[0]["selected"] else
                         ("%s was computed under the %s heading instead: the gates did not select it"
                          % (k, pick[0]["method"])))
        else:
            out[k] = _none(k, "the loaded table carries no question of this design" if ctx["dataset"]
                           else "no table with numeric columns was loaded from the input", ctx)
    return out

def _none(k, why, ctx):
    out = {"computed": False, "method": k, "reason": why, "requirement": REQ.get(k, "a design in the input"),
           "input": ctx["rels"]}
    if ctx["degradations"]:
        out["degradations"] = [d["kind"] for d in ctx["degradations"]]
    if ctx["dataset"]:
        out["columns_seen"] = [c["name"] for c in ctx["dataset"]["columns"]][:12]
    return out

def n4(x):
    return S.fmt(x, 4) if not isinstance(x, str) else (x or "-")

def ci4(ci):
    return "[%s, %s]" % (n4(ci[0]), n4(ci[1])) if ci and len(ci) == 2 else "-"

EST_LABEL = {"mean_difference": "the mean difference", "rank_difference": "the median difference",
             "slope": "the slope", "correlation": "the correlation coefficient",
             "association": "the odds ratio"}
DESIGN_PHRASE = {"two_independent_groups": "the two levels are distinguishable",
                 "multi_group": "the group levels are distinguishable",
                 "paired": "the paired values moved between the two readings",
                 "correlation": "the two columns move together", "regression": "the slope differs from a flat line",
                 "contingency": "the two columns are associated"}

def interpret(row, dec):
    p = row["p"]
    if row["status"] != "done" or p in ("", None):
        return {"statistical": "this row carries no test: %s" % (row["notes"] or "the step did not run"),
                "practical": "nothing is read from a row that did not run",
                "caveats": ["the estimate is missing, so the finding is missing with it"],
                "auto_generated": True}
    p, eff, ci = float(p), row["effect_size"], row["ci_95"]
    lab = EST_LABEL.get(row["estimate_type"], "")
    pt = row.get("estimate_point")
    has_ci = len(ci) == 2 and bool(lab)
    nref = "1, the no-association value" if row["estimate_type"] == "association" else "0"
    adj = " (holm adjusted p = %s)" % n4(row["p_adj"]) if row["p_adj"] not in ("", None) else ""
    if has_ci and pt not in ("", None):
        est = "%s is %s with a 95%% interval %s" % (lab, n4(pt), ci4(ci))
    elif has_ci:
        est = "the 95%% interval for %s is %s" % (lab, ci4(ci))
    elif lab:
        est = "no interval was computed for %s on this row" % lab
    else:
        est = "this is an omnibus row, so no single estimate interval is attached to it"
    ect = []
    if eff["type"] != row["statistic_name"]:
        ect.append("the effect size %s = %s" % (eff["type"], n4(eff["value"])))
        if len(eff.get("ci_95") or []) == 2 and (not lab or eff.get("ci_95") != row["ci_95"]):
            ect[-1] += " with a 95%% interval %s" % ci4(eff["ci_95"])
    if eff.get("hedges_g") not in ("", None):
        ect.append("the small-sample corrected hedges_g = %s" % n4(eff["hedges_g"]))
    dfp = "" if row["df"] in ("", None, []) else " with df = %s" % (row["df"],)
    stat = ("%s = %s%s, p = %s%s; %s%s"
            % (row["statistic_name"], n4(row["statistic"]), dfp, n4(p), adj, est,
               ("; " + "; ".join(ect)) if ect else ""))
    head = DESIGN_PHRASE.get(row["design"], "the estimate differs from its reference value")
    if p < 0.05:
        st = ("in this sample %s: %s. %s" % (head, stat, "That interval stays clear of %s, and the "
              "direction is %s." % (nref, eff["direction"]) if has_ci else
              "The direction is %s." % eff["direction"]))
        pr = ("the finding is stated with its p value, with the interval of the estimate where one exists "
              "and with its effect size rather than as a bare p value; whether a size of %s matters is a "
              "judgement for the researcher." % n4(eff["value"]))
        if has_ci:
            pr += " With n = %s the 95%% interval for %s is %s wide." % (row["n"], lab, n4(ci[1] - ci[0]))
    else:
        st = ("this sample does not support a difference at the 0.05 level: %s. %s" % (stat, (
            "That interval %s covers %s, so an absence of a difference cannot be ruled out either."
            % (ci4(ci), nref)) if has_ci else
            "Only the test result is available here, so the absence rests on the p value alone."))
        pr = ("with n = %s this sample cannot separate %s%s from %s, and the width of that interval, not "
              "the p value, is what says how much the data support. A larger sample would be needed "
              "before a difference of this size could be claimed."
              % (row["n"], lab, "" if pt in ("", None) else " = " + n4(pt), nref)) if has_ci else \
             ("the omnibus statistic is %s; with n = %s this sample does not separate the levels, so a "
              "larger sample or a narrower design would be needed before a difference could be claimed."
              % (n4(row["statistic"]), row["n"]))
    cav = ["the design is %s and the data are observational, so an association is reported as an "
           "association and not as a cause" % row["design"]]
    if row["method"] in ("mann_whitney_u", "kruskal_wallis", "wilcoxon_signed_rank", "spearman_rho"):
        cav.append("a rank method was selected, so the estimand is a shift in distribution or a rank "
                   "association rather than a difference of means")
    for c in dec.get("candidates") or []:
        if c.get("rejected_reason") and c.get("method") != row["method"]:
            cav.append("%s was not used: %s" % (c["method"], c["rejected_reason"]))
    return {"statistical": st, "practical": pr, "caveats": cav, "auto_generated": True}

def n_gate_text(dec, g):
    n = g.get("n") or {}
    sizes = n.get("sizes") or []
    d = dec.get("design")
    if d == "contingency":
        return "table n=%s, smallest row total %s" % (sizes[0] if sizes else "-", n.get("min_group_n", "-"))
    if d in ("association", "regression"):
        return "complete pairs=%s" % (sizes[0] if sizes else "-")
    if d == "paired":
        return "pairs=%s" % (sizes[0] if sizes else "-")
    return "min group n=%s" % (n.get("min_group_n", "-") or "-")

def gate_labels(dec):
    k = len((dec.get("gate_results") or {}).get("normality") or [])
    d = dec.get("design")
    if d == "association":
        return ["x column", "y column"][:k] or ["value"]
    if d == "paired":
        return ["paired differences"][:k] or ["value"]
    return ["group %d" % i for i in range(k)] or ["value"]
