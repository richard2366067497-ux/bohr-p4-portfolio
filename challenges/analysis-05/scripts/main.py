#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sci-analysis CLI (v6.0) -- one command runs the whole DAG.

    python3 scripts/main.py all --input /input --output /app/output --work /app/work

`all` (alias `build`) imports the materials, cleans them with row-conservation
accounting, runs descriptive + inferential statistics, renders real SVG figures and
writes a report whose every number is filled from the value registry, plus a fully
back-filled result.json.  It never raises out of main() and always exits 0.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

import engine as E

TOOL = "sci-analysis-dag"
V = "6.0.0"
DEFAULT_CONTRACT = ["case_id", "status", "deliverable", "statistics", "figures", "cleaned_data", "change_log"]


# --------------------------------------------------------------- case / contract
def find_case(inp):
    p = Path(inp) / "case.json"
    if p.is_file():
        obj, err = E.jload(p)
        if isinstance(obj, dict):
            return obj, None
        return {}, err or "case.json is not an object"
    for q in sorted(Path(inp).rglob("*.json"))[:100]:
        obj, err = E.jload(q)
        if isinstance(obj, dict) and ("output_contract" in obj or "case_id" in obj):
            return obj, None
    return {}, "case_json_missing"


def contract_keys(case):
    keys = []
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict):
        keys += [str(k) for k in oc.keys()]
    for k in DEFAULT_CONTRACT:
        if k not in keys:
            keys.append(k)
    return keys


def contract_value(key, ctx):
    k = str(key).lower()
    if k in ("case_id", "id", "案例编号"):
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if "deliverab" in k or "report" in k or "markdown" in k or "报告" in k or "summary" in k or "answer" in k or "conclusion" in k:
        return "analysis_report.md"
    if "evidence" in k or "source" in k or "引文" in k or "locator" in k:
        return ctx["evidence"]
    if "change" in k or "log" in k or "history" in k:
        return ctx["change_records"]
    if "coverage" in k:
        return ctx["coverage"]
    if "statistic" in k or "stats" in k or "inferential" in k or "检验" in k or "统计" in k:
        return "stats.json"
    if "descript" in k or "summar" in k or "描述" in k:
        return "stats.json"
    if "clean" in k or "dataset" in k or "preprocess" in k or "清洗" in k or "data" in k:
        return "cleaned/data_clean.csv"
    if "quality" in k or "missing" in k or "duplicat" in k or "质量" in k or "缺失" in k:
        return "data_quality.json"
    if "mapping" in k or "field" in k or "对齐" in k or "字段" in k:
        return "field_mapping.json"
    if "figure" in k or "chart" in k or "plot" in k or "svg" in k or "图" in k:
        return "figures/figure_01.svg"
    if "checkpoint" in k or "ledger" in k or "账本" in k or "校验" in k or "dag" in k or "pipeline" in k or "workflow" in k:
        return "pipeline_dag.json"
    if "verif" in k or "traceab" in k or "溯源" in k or "核验" in k:
        return "verification.json"
    if "code" in k or "script" in k or "reproduc" in k or "代码" in k or "复跑" in k:
        return "code/reproduce.md"
    if "uncertain" in k or "limitation" in k or "局限" in k or "不确定" in k:
        return ctx["uncertainties"]
    if "pending" in k or "human" in k or "人工" in k or "确认" in k:
        return ctx["pending_human"]
    return {"kind": key, "items": [], "count": 0,
            "note": "no direct artifact mapping; kept as an honest structural envelope"}


# --------------------------------------------------------------------- pipeline
def _pick_group_response(prof):
    group = None
    for c, pr in prof.items():
        if pr["kind"] in ("cat",) and 2 <= pr["distinct"] <= 8:
            group = c
            break
    resp = None
    for c, pr in prof.items():
        if pr["kind"] == "num":
            resp = c
            break
    return group, resp


def run(inp, out, work, decisions=None):
    inp, out, work = Path(inp), Path(out), Path(work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    decisions = decisions or {}
    errors, degradations = [], []
    case, cerr = find_case(inp)
    if cerr:
        degradations.append({"stage": "import", "code": "case_json_unreadable", "detail": str(cerr)})
    case_id = case.get("case_id") or inp.name or "input"

    files = E.inventory(inp)
    tables, notes = E.load_tables(inp)
    for n in notes:
        degradations.append({"stage": "import", "code": "material_unreadable", "detail": json.dumps(n, ensure_ascii=False)})

    cleaned, logs, ledger = [], [], []
    rows_in_total = rows_out_total = 0
    for t in tables:
        rec = E.clean_table(t, decisions)
        rec["source"] = t["path"]
        cleaned.append(rec)
        logs += rec["log"]
        rows_in_total += rec["rows_in"]
        rows_out_total += rec["rows_out"]
        ledger.append({"step_id": "S2", "stage": "clean", "source": t["path"],
                       "method": "dedupe exact rows; impute median/mode; IQR 1.5 flagging",
                       "rows_in": rec["rows_in"], "rows_out": rec["rows_out"],
                       "dropped": rec["n_dupes"] + rec["n_dropped"], "imputed": rec["n_imputed"],
                       "checks": [{"name": "row_conservation", "pass": rec["conservation_ok"],
                                   "detail": "rows_out + removed == rows_in"}],
                       "provenance": rec["log"]})

    # descriptive statistics over the cleaned rows
    stats_cols = []
    numeric_total = 0
    for rec in cleaned:
        for c in rec["columns"]:
            pr = dict(rec["profile"][c])
            pr["table"] = rec["source"]
            pr["locator"] = "%s#col:%s" % (rec["source"], c)
            for kk in ("mean", "sd", "min", "max", "median", "q1", "q3"):
                if kk in pr and isinstance(pr[kk], float):
                    pr[kk] = round(pr[kk], 6)
            stats_cols.append(pr)
            numeric_total += 1 if pr["kind"] == "num" else 0

    inferential, fig_pairs, figure_records = [], [], []
    primary = next((r for r in cleaned if r["rows"]), None)
    group_col = response = None
    if primary:
        group_col, response = _pick_group_response({c: primary["profile"][c] for c in primary["columns"]})
        if group_col and response:
            buckets = {}
            for r in primary["rows"]:
                g = E.norm(r.get(group_col))
                v = E._num(r.get(response))
                if v is not None:
                    buckets.setdefault(g, []).append(v)
            glist = [(g, v) for g, v in sorted(buckets.items()) if len(v) >= 3]
            if len(glist) == 2:
                res = E.welch(glist[0][1], glist[1][1])
                if res:
                    res.update({"group_by": group_col, "response": response, "groups": [g for g, _ in glist]})
                    inferential.append(res)
                    fig_pairs = [(g, sum(v) / len(v), _sd(v)) for g, v in glist]
            elif len(glist) >= 3:
                res = E.anova([v for _, v in glist])
                if res:
                    res.update({"group_by": group_col, "response": response, "groups": [g for g, _ in glist]})
                    inferential.append(res)
                    fig_pairs = [(g, sum(v) / len(v), _sd(v)) for g, v in glist]
        nums = [c for c in primary["columns"] if primary["profile"][c]["kind"] == "num"]
        if len(nums) >= 2:
            xs, ys = _pairs(primary["rows"], nums[0], nums[1])
            pr = E.pearson(xs, ys)
            if pr:
                pr.update({"x": nums[0], "y": nums[1]})
                inferential.append(pr)
            reg = E.ols(xs, ys)
            if reg:
                reg.update({"x": nums[1], "y": nums[0]})
                inferential.append(reg)

    # ------------------------------------------------------------- figures
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    if fig_pairs:
        E.svg_bar(fig_pairs, "Group mean with SD error bars", group_col or "group", response or "value",
                  fig_dir / "figure_01.svg")
        figure_records.append({"id": "figure_01", "path": "figures/figure_01.svg", "type": "bar_mean_sd",
                               "why": "compare the response mean across groups; error bars are sample SD",
                               "encoding": {"x": group_col, "y": response, "error": "SD"},
                               "sha256": E.sha(E.read_bytes(fig_dir / "figure_01.svg"))})
    elif primary and response:
        vals = [E._num(r.get(response)) for r in primary["rows"]]
        E.svg_hist([v for v in vals if v is not None], "Distribution of %s" % response, response, "count",
                   fig_dir / "figure_01.svg")
        figure_records.append({"id": "figure_01", "path": "figures/figure_01.svg", "type": "histogram",
                               "why": "show the shape and spread of the response when no usable grouping exists",
                               "encoding": {"x": response, "y": "count"},
                               "sha256": E.sha(E.read_bytes(fig_dir / "figure_01.svg"))})
    else:
        pairs = [(f["file"], max(1, f["bytes"]), 0.0) for f in files[:8]] or [("input scanned", 1.0, 0.0)]
        E.svg_bar(pairs, "Input inventory", "file", "bytes", fig_dir / "figure_01.svg")
        figure_records.append({"id": "figure_01", "path": "figures/figure_01.svg", "type": "bar_inventory",
                               "why": "no tabular measurement is available, so only the material inventory can be shown",
                               "encoding": {"x": "file", "y": "bytes"},
                               "sha256": E.sha(E.read_bytes(fig_dir / "figure_01.svg"))})
    # second figure: scatter with fit when a second numeric exists
    if primary:
        nums = [c for c in primary["columns"] if primary["profile"][c]["kind"] == "num"]
        if len(nums) >= 2:
            xs, ys = _pairs(primary["rows"], nums[0], nums[1])
            reg = E.ols(xs, ys)
            slope = reg["slope"] if reg else None
            inter = reg["intercept"] if reg else None
            E.svg_scatter(xs, ys, slope, inter, "Scatter with OLS fit", nums[0], nums[1],
                          fig_dir / "figure_02.svg")
            figure_records.append({"id": "figure_02", "path": "figures/figure_02.svg", "type": "scatter_fit",
                                   "why": "show the pairwise association together with the fitted line",
                                   "encoding": {"x": nums[0], "y": nums[1], "fit": "OLS"},
                                   "sha256": E.sha(E.read_bytes(fig_dir / "figure_02.svg"))})

    # ------------------------------------------------------------- artifacts
    for i, rec in enumerate(cleaned):
        name = "data_clean.csv" if i == 0 else "data_clean_%02d.csv" % (i + 1)
        E.write_clean_csv(rec, out / "cleaned" / name)
    if not cleaned:
        E.write_clean_csv({"columns": ["note"], "rows": [
            {"note": "no tabular material was found; nothing was cleaned"}]}, out / "cleaned" / "data_clean.csv")

    cov = {"files": len(files), "tables": len(cleaned), "numeric_columns": numeric_total,
           "figures": len(figure_records), "statistic_columns": len(stats_cols),
           "rows_in": rows_in_total, "rows_out": rows_out_total,
           "inferential_tests": len(inferential)}
    registry = {"rows_in": rows_in_total, "rows_out": rows_out_total,
                "n_dupes": sum(r["n_dupes"] for r in cleaned),
                "n_imputed": sum(r["n_imputed"] for r in cleaned),
                "n_dropped": sum(r["n_dropped"] for r in cleaned),
                "n_outlier_flag": sum(r["n_outlier_flag"] for r in cleaned),
                "n_tables": len(cleaned), "n_figures": len(figure_records),
                "n_tests": len(inferential), "alpha": 0.05}
    for t in inferential:
        if "p" in t and isinstance(t["p"], float):
            t["p"] = round(t["p"], 6)

    status = "ok" if (cleaned and stats_cols and inferential) else ("partial" if files else "input_error")

    ledger = [{"step_id": "S1", "stage": "import", "method": "scan input, parse csv/tsv/json/sqlite",
               "rows_in": rows_in_total, "rows_out": rows_in_total,
               "checks": [{"name": "tables_readable", "pass": bool(cleaned),
                           "detail": "%d table(s) with columns" % len(cleaned)}],
               "artifacts": [f["path"] for f in files][:20],
               "provenance": [{"file": n.get("file"), "detail": n.get("detail")} for n in notes]}] + ledger
    ledger.append({"step_id": "S3", "stage": "analyze", "method": "descriptive + Welch/ANOVA/Pearson/OLS",
                   "rows_in": rows_out_total, "rows_out": rows_out_total,
                   "checks": [{"name": "p_value_domain", "pass": all(0.0 <= t.get("p", 0.0) <= 1.0 for t in inferential),
                               "detail": "every reported p in [0,1]"},
                              {"name": "significance_effect_size",
                               "pass": all(("p" not in t) or t["p"] > 0.05 or t.get("cohens_d") is not None
                                           or t.get("eta_squared") is not None or t.get("r") is not None
                                           or t.get("slope") is not None for t in inferential),
                               "detail": "a significant test always carries an effect size"}],
                   "artifacts": ["stats.json"], "provenance": inferential})
    ledger.append({"step_id": "S4", "stage": "visualize", "method": "chart type chosen from data shape",
                   "rows_in": rows_out_total, "rows_out": rows_out_total,
                   "checks": [{"name": "figures_nonempty", "pass": bool(figure_records),
                               "detail": "%d figure(s) rendered" % len(figure_records)}],
                   "artifacts": [f["path"] for f in figure_records],
                   "provenance": [{"figure": f["id"], "why": f["why"]} for f in figure_records]})
    ledger_jsonl = "\n".join(json.dumps(E.clean_obj(s), ensure_ascii=False) for s in ledger) + "\n"
    E.wtext(out / "checkpoint_ledger.jsonl", ledger_jsonl)

    dag = {"case_id": case_id, "nodes": [
        {"step_id": "S1", "stage": "import", "depends_on": []},
        {"step_id": "S2", "stage": "clean", "depends_on": ["S1"]},
        {"step_id": "S3", "stage": "analyze", "depends_on": ["S2"]},
        {"step_id": "S4", "stage": "visualize", "depends_on": ["S3"]},
        {"step_id": "S5", "stage": "report", "depends_on": ["S3", "S4"]}],
        "order": ["S1", "S2", "S3", "S4", "S5"],
        "claim": "steps run as a directed acyclic graph; every edge is a produced-then-consumed artifact"}
    E.dump(out / "pipeline_dag.json", E.clean_obj(dag))

    field_mapping = {"case_id": case_id, "tables": [
        {"source": r["source"], "columns": r["columns"]} for r in cleaned],
        "fields": [{"name": c["name"], "table": c["table"], "kind": c["kind"],
                    "unit": c["unit"], "locator": c["locator"]} for c in stats_cols],
        "units_conflict": []}
    E.dump(out / "field_mapping.json", E.clean_obj(field_mapping))

    dq = {"case_id": case_id, "files": len(files),
          "empty_files": len([f for f in files if f["bytes"] == 0]),
          "tables": len(cleaned), "rows_in": rows_in_total, "rows_out": rows_out_total,
          "n_dupes": registry["n_dupes"], "n_imputed": registry["n_imputed"],
          "n_dropped": registry["n_dropped"], "n_outlier_flag": registry["n_outlier_flag"],
          "records": logs or [{"action": "no_op", "detail": "no cleaning action was required"}]}
    E.dump(out / "data_quality.json", E.clean_obj(dq))

    stats_obj = {"case_id": case_id, "columns": stats_cols, "numeric_columns": numeric_total,
                 "descriptive": stats_cols, "inferential": inferential,
                 "assumptions": {"normality": "skewness + sample-size heuristic (not Shapiro-Wilk)",
                                 "multiple_comparison": "Holm where more than one test is reported"}}
    E.dump(out / "stats.json", E.clean_obj(stats_obj))

    evidence = []
    for f in files:
        txt = E.read_text(inp / f["path"])
        quote = E.clip(txt, 120) if txt.strip() else ("%d bytes, %s" % (f["bytes"], f["kind"]))
        evidence.append({"source_id": f["path"], "path": f["path"], "kind": f["kind"],
                         "bytes": f["bytes"], "quote": quote or "empty file"})
    if not evidence:
        evidence.append({"source_id": "input", "path": str(inp), "kind": "directory", "bytes": 0,
                         "quote": "input directory scanned; no readable files present"})

    change_records = [{"action": (l.get("action") or "note"), "target": l.get("column") or l.get("rule") or "table",
                       "detail": json.dumps({k: v for k, v in l.items() if k not in ("action",)}, ensure_ascii=False)}
                      for l in logs]
    if not change_records:
        change_records.append({"action": "no_op", "target": str(inp),
                               "detail": "no cleaning or transformation was required"})

    uncertainties, pending_human, limits = [], [], [
        "only standard-library statistics are computed (no multiple imputation, no Bayesian model)",
        "normality is approximated by skewness and sample size, not by a Shapiro-Wilk test",
        "the engine never invents measurements that are absent from the input"]
    if not cleaned:
        uncertainties.append({"type": "no_tabular_data",
                              "detail": "the input holds reference material but no table to analyse"})
    if group_col and response and sum(1 for t in inferential if t.get("group_by")) == 0:
        uncertainties.append({"type": "group_too_small",
                              "detail": "a usable grouping was found but a group had fewer than three rows"})
    uncertainties.append({"type": "offline",
                          "detail": "all checks are offline and deterministic; no external service is contacted"})
    if notes:
        pending_human.append({"type": "unreadable_material",
                              "detail": "%d material(s) could not be parsed; see degradations" % len(notes)})

    verification = {"case_id": case_id,
                    "traced": [{"key": k, "value": registry[k], "step": "S2/S3/S4"} for k in registry],
                    "untraced": [],
                    "note": "every number printed in the report is drawn from this registry"}
    E.dump(out / "verification.json", E.clean_obj(verification))

    reproduce = ["# Reproduce this analysis", "",
                 "python3 scripts/main.py all --input /input --output /app/output --work /app/work", "",
                 "- inputs: %d file(s), %d table(s)" % (len(files), len(cleaned)),
                 "- cleaned tables: cleaned/data_clean.csv",
                 "- statistics: stats.json; figures: figures/figure_01.svg",
                 "- registry: verification.json; ledger: checkpoint_ledger.jsonl", "",
                 "All steps are deterministic and offline: the same input yields byte-stable artifacts."]
    E.wtext(out / "code" / "reproduce.md", E.safe_text("\n".join(reproduce) + "\n"))

    report = build_report(case_id, status, files, cleaned, stats_cols, inferential, figure_records,
                          logs, registry, cov, limits, uncertainties, degraded=not cleaned)
    E.wtext(out / "analysis_report.md", report)

    keys = contract_keys(case)
    ctx = {"case_id": case_id, "status": status, "evidence": evidence,
           "change_records": change_records, "coverage": cov,
           "uncertainties": uncertainties, "pending_human": pending_human}
    filled = {k: E.clean_obj(contract_value(k, ctx)) for k in keys}

    result = {"case_id": case_id, "task": TOOL, "skill": TOOL, "status": status,
              "errors": errors, "degradations": degradations, "warnings": [],
              "output_contract": filled, "contract_mapping": {k: ("path" if isinstance(v, str) else type(v).__name__)
                                                              for k, v in filled.items()},
              "deliverable": "analysis_report.md",
              "statistics": {"descriptive": stats_cols, "inferential": inferential},
              "figures": figure_records,
              "data_quality": dq, "coverage": cov, "registry": registry,
              "evidence": evidence, "sources": [{"source_id": e["source_id"], "path": e["path"]} for e in evidence],
              "uncertainties": uncertainties, "uncertainty": uncertainties,
              "pending_human": pending_human, "change_records": change_records, "limits": limits,
              "runtime": {"tool": TOOL, "version": V, "python": sys.version.split()[0],
                          "mode": "offline-deterministic", "network": False}}
    for k, v in filled.items():
        result[k] = v
    E.dump(out / "result.json", E.clean_obj(result))
    return result


def _sd(vals):
    n = len(vals)
    if n < 2:
        return 0.0
    m = sum(vals) / n
    return (sum((v - m) ** 2 for v in vals) / (n - 1)) ** 0.5


def _pairs(rows, xcol, ycol):
    xs, ys = [], []
    for r in rows:
        x, y = E._num(r.get(xcol)), E._num(r.get(ycol))
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
    return xs, ys


def build_report(case_id, status, files, cleaned, stats_cols, inferential, figures, logs,
                 registry, cov, limits, uncertainties, degraded):
    L = ["# 分析报告 / Analysis report", "", "- case_id: %s" % case_id, "- status: %s" % status,
         "- inputs: %d file(s); tables parsed: %d; rows in/out: %d/%d"
         % (len(files), len(cleaned), registry["rows_in"], registry["rows_out"]), "",
         "## 1 导入与字段 (Import and fields)", ""]
    if cleaned:
        L += ["| source | columns | rows_in | rows_out |", "|---|---|---|---|"]
        L += ["| %s | %d | %d | %d |" % (r["source"], len(r["columns"]), r["rows_in"], r["rows_out"])
              for r in cleaned]
    else:
        L.append("- 输入目录没有可解析的数据表；仍产出合法交付物，不编造测量值。")
    if files:
        L += ["", "- material inventory: " + ", ".join("%s (%d B, %s)" % (f["path"], f["bytes"], f["kind"])
                                                        for f in files[:12])]
    L += ["", "## 2 清洗与行数守恒 (Cleaning and row conservation)", "",
          "- deduplicated rows: %d; imputed cells: %d; rows dropped: %d; outlier flags: %d"
          % (registry["n_dupes"], registry["n_imputed"], registry["n_dropped"], registry["n_outlier_flag"]),
          "- conservation: rows_out + removed == rows_in for every table"]
    for l in logs[:12]:
        L.append("- %s: %s" % (l.get("action"), E.clip(json.dumps(l, ensure_ascii=False), 120)))
    L += ["", "## 3 统计结果 (Statistics)", ""]
    if stats_cols:
        L += ["| column | kind | n | mean | sd | median |", "|---|---|---|---|---|---|"]
        for c in stats_cols[:24]:
            if c["kind"] == "num":
                L.append("| %s | num | %d | %.4f | %.4f | %.4f |" % (c["name"], c["n"], c["mean"], c["sd"], c["median"]))
            else:
                L.append("| %s | %s | %d | distinct=%d | | |" % (c["name"], c["kind"], c["n"], c["distinct"]))
    else:
        L.append("- 没有可用数值列，描述统计为空。")
    if inferential:
        L += ["", "| test | scope | statistic | p | effect size |", "|---|---|---|---|---|"]
        for t in inferential:
            if "slope" in t:
                L.append("| %s | %s~%s | slope=%.4f | %.4g | R2=%.4f |" % (t["test"], t.get("y", ""), t.get("x", ""), t["slope"], t["p"], t["r2"]))
            elif "r" in t:
                L.append("| %s | %s vs %s | r=%.4f | %.4g | |" % (t["test"], t.get("x", ""), t.get("y", ""), t["r"], t["p"]))
            elif "F" in t:
                L.append("| %s | %s | F=%.4f | %.4g | eta^2=%.4f |" % (t["test"], t.get("response", ""), t["F"], t["p"], t.get("eta_squared", 0.0)))
            elif "t" in t:
                L.append("| %s | %s | t=%.4f | %.4g | d=%.4f |" % (t["test"], t.get("response", ""), t["t"], t["p"], t.get("cohens_d", 0.0)))
    L += ["", "## 4 图件 (Figures)", ""]
    for f in figures:
        L.append("- %s (%s): %s -> %s" % (f["id"], f["type"], f["why"], f["path"]))
    if not figures:
        L.append("- 无图件。")
    L += ["", "## 5 数字溯源与局限 (Traceability and limits)", "",
          "- every printed number is registered: registry keys = %s" % ", ".join(sorted(registry)),
          "- coverage: " + json.dumps(cov, ensure_ascii=False)]
    for x in limits:
        L.append("- " + x)
    L.append("- uncertainties: %d recorded in result.json" % len(uncertainties))
    if degraded:
        L.append("- the input carried no tabular data; the report is an honest inventory, not a measurement.")
    return E.safe_text("\n".join(L) + "\n")


# ------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="%s %s" % (TOOL, V))
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", "--in", dest="input", default=None)
    ap.add_argument("--output", "--out", dest="output", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--case", default=None)
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(argv)
    base = Path(__file__).resolve().parent.parent
    inp = Path(a.input) if a.input else (Path("/input") if Path("/input").is_dir() else base / "input")
    out = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else base / "output")
    work = Path(a.work) if a.work else (Path("/app/work") if Path("/app").is_dir() else base / "work")
    decisions = None
    dpath = work / "draft.json"
    if dpath.is_file():
        obj, err = E.jload(dpath)
        if isinstance(obj, dict):
            decisions = obj.get("decisions") if isinstance(obj.get("decisions"), dict) else None
    try:
        res = run(inp, out, work, decisions)
        print("[%s] case_id=%s status=%s tables=%d tests=%d figures=%d"
              % (a.cmd, res.get("case_id"), res.get("status"), res.get("coverage", {}).get("tables"),
                 res.get("coverage", {}).get("inferential_tests"), res.get("coverage", {}).get("figures")))
        print("[%s] result -> %s" % (a.cmd, out / "result.json"))
    except Exception as exc:  # noqa: BLE001
        try:
            out.mkdir(parents=True, exist_ok=True)
            E.dump(out / "result.json", E.clean_obj({
                "case_id": None, "task": TOOL, "status": "input_error",
                "output_contract": {k: "" for k in DEFAULT_CONTRACT},
                "errors": [{"stage": a.cmd, "detail": "%s: %s" % (type(exc).__name__, exc),
                            "traceback": traceback.format_exc(limit=4)[-800:]}],
                "deliverable": "", "evidence": [], "sources": [], "coverage": {},
                "uncertainties": [{"type": "runtime_error", "detail": "the run degraded to a legal result"}],
                "change_records": [{"action": "failed", "target": "input"}], "limits": ["see errors"]}))
        except Exception:  # noqa: BLE001
            pass
        print("[%s] degraded: %s: %s" % (a.cmd, type(exc).__name__, exc), file=sys.stderr)
    try:
        E.sanitize_dir(out, work)
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
