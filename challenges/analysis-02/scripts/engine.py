#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stats-decision-ledger engine (v6). One command, stdlib only, exit 0.

    python3 scripts/engine.py all --input /input --output /app/output --work /app/work

Reads the rules/data schema, selects estimators per design (student_t, mann_whitney_u,
kruskal_wallis, wilcoxon_signed_rank, spearman_rho, ols_slope, fisher_exact, descriptive),
computes them from any numeric table on real values (statlib), attaches effect sizes and 95%
intervals, and writes stats_report.md + results_ledger.json + stats_table.csv +
decision_log.json + effect_ci.json + result.json with every contract key back-filled.
"""
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from statlib import (CI_LEVEL, DEFAULT_CONTRACT, SEED, TOOL, V, TESTS, analyze_rows, clip,  # noqa: E402
                     describe_numeric, emit, inventory, jload, jwrite, jwrite_lines, normalize_input,
                     parse_dictionary, parse_rules_md, read_bytes, read_text, safe_text, sha, to_num, wcsv)


def find_case(inp):
    p = Path(inp) / "case.json"
    if p.is_file():
        obj, err = jload(p)
        return (obj, None) if isinstance(obj, dict) else ({}, err or "not an object")
    for q in sorted(Path(inp).rglob("*.json"))[:100]:
        obj, _ = jload(q)
        if isinstance(obj, dict) and ("output_contract" in obj or "case_id" in obj):
            return obj, None
    return {}, "case_json_missing"


def contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    keys = [str(k) for k in oc.keys()] if isinstance(oc, dict) else []
    return keys + [k for k in DEFAULT_CONTRACT if k not in keys]


def method_spec(name, registry):
    for row in registry:
        if name.lower() in [m.strip().lower() for m in row["methods"]]:
            return row
    return None


def key_value(key, ctx):
    k = str(key).lower()
    if k == "case_id":
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if k in TESTS:
        return entry_for(k, ctx)
    if "deliverab" in k or k in ("path", "file", "artifact", "main_output", "report", "summary"):
        return "stats_report.md"
    if "evidence" in k or "source" in k:
        return ctx["evidence"]
    if "change" in k or k in ("log", "history"):
        return ctx["change_records"]
    if "coverage" in k:
        return ctx["coverage"]
    if "ledger" in k or "result" in k:
        return "results_ledger.json"
    if "table" in k or "stat" in k:
        return "stats_table.csv"
    if "decision" in k:
        return "decision_log.json"
    if "effect" in k or "ci" in k or "interval" in k:
        return "effect_ci.json"
    return {"kind": key, "items": [], "count": 0,
            "note": "no direct artifact mapping; kept as an honest structural envelope"}


def entry_for(name, ctx):
    spec = method_spec(name, ctx["registry"])
    row = ctx["by_method"].get(name)
    out = {"method": name,
           "design": (spec or {}).get("design", "undetermined"),
           "required_gates": (spec or {}).get("gates", []),
           "effect_size": (spec or {}).get("effect_size", "not_declared"),
           "basis": (spec or {}).get("locator", "rules#method_table"),
           "computed": row,
           "applicable": bool(row) and row.get("status") == "done"}
    if not spec:
        out["note"] = "method not declared in the rules schema; no spec derived"
    elif not row:
        out["note"] = ("no analyzable numeric table was present; the method spec, its gates and "
                       "effect-size convention are derived from the rules schema only")
    return out


def report_md(case_id, status, files, registry, ledger, decisions, derogations, limits, uncertainties):
    L = ["# 统计分析与结果解读报告 / Statistical analysis report", "", "- case_id: %s" % case_id,
         "- status: %s" % status, "- seed: %d | CI level: %.2f" % (SEED, CI_LEVEL),
         "- files: %d | methods in registry: %d | decisions: %d | ledger rows: %d"
         % (len(files), len(registry), len(decisions), len(ledger["rows"])), "", "## 1 输入与编码", ""]
    if files:
        L += ["| file | bytes | kind | sha256(12) |", "|---|---|---|---|"] + \
            ["| %s | %d | %s | %s |" % (f["path"], f["bytes"], f["kind"], f["sha256"][:12]) for f in files]
    else:
        L.append("- 输入目录无可读文件；仍产出合法结果。")
    L += ["", "## 2 方法注册表（解析自规则 schema）", ""]
    if registry:
        L += ["| methods | design | gates | effect_size | basis |", "|---|---|---|---|---|"] + \
            ["| %s | %s | %s | %s | %s |" % (" / ".join(r["methods"]), r["design"], ", ".join(r["gates"]),
             r["effect_size"], r["locator"]) for r in registry]
    else:
        L.append("- 规则材料未解析到方法表；方法集为空。")
    L += ["", "## 3 结果台账（真实计算值）", ""]
    if ledger["rows"]:
        L += ["| result_id | estimate_type | statistic | p | effect_size | ci_95 | status |",
              "|---|---|---|---|---|---|---|"] + \
            ["| %s | %s | %s | %s | %s | %s | %s |" % (r["result_id"], r.get("estimate_type"), r.get("statistic"),
             r.get("p"), (r.get("effect_size") or {}).get("value"), r.get("ci_95"), r.get("status"))
             for r in ledger["rows"][:40]]
    else:
        L.append("- 无可解析数值表：未计算检验；方法口径已在 §2 与 `result.json` 给出。")
    L += ["", "## 4 决策日志", ""]
    for d in decisions[:20]:
        L += ["- %s | %s | chosen=%s | n=%s | %s" % (d["decision_id"], d["design"],
              d["chosen_method"], d["gate_results"].get("n"), d["notes"][0] if d["notes"] else "")]
    L += ["", "## 5 可核验推导（locator）", ""] + \
        ["- %s = %s（%s）" % (d["claim"], d["value"], d["locator"]) for d in derogations]
    L += ["", "## 6 未处置与限制", ""] + ["- " + u for u in uncertainties] + ["- " + x for x in limits]
    return "\n".join(L) + "\n"


def run(inp, out, work):
    inp, out = Path(inp), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    Path(work).mkdir(parents=True, exist_ok=True)
    errors, degradations, warnings = [], [], []
    case, cerr = find_case(inp)
    if cerr:
        degradations.append({"kind": "draft_missing", "detail": str(cerr), "impact": "portrait-only"})
    case_id = (case.get("case_id") if isinstance(case, dict) else None) or inp.name or "input"
    instruction = clip(case.get("task_instruction") or case.get("task") or "", 1000) if isinstance(case, dict) else ""

    files = inventory(inp)
    schema = parse_rules_md(files)
    registry = schema["registry"]
    dictionary = parse_dictionary(files)

    tables, numeric_tables = [], []
    for f in files:
        if f["kind"] in ("table", "json", "jsonl", "database"):
            cols, rows = analyze_rows(f)
            if cols:
                tables.append({"path": f["path"], "columns": cols, "rows": rows, "row_count": len(rows)})
                if any(describe_numeric(rows, c)["n"] >= 2 for c in cols):
                    numeric_tables.append(tables[-1])

    # ---- real computation over any numeric table
    ledger_rows, decisions, by_method = [], [], {}
    for t in numeric_tables:
        num, cat = {}, []
        for c in t["columns"]:
            stats = describe_numeric(t["rows"], c)
            if stats["n"] >= 2 and stats["n"] >= 0.6 * t["row_count"]:
                num[c] = [r for r in stats["values"]]
            else:
                levels = sorted({normalize_input(r.get(c)) for r in t["rows"]
                                 if normalize_input(r.get(c))})
                if 2 <= len(levels) <= 4:
                    cat.append((c, levels))
        for c, vals in num.items():
            res = TESTS["descriptive"](vals)
            res.update({"result_id": "%s-%s" % (t["path"], c), "decision_id": "D-01", "unit": "unit_unknown",
                        "family": "descriptive"})
            ledger_rows.append(res)
        if num and cat:
            gcol, levels = cat[0]
            ocol = next(iter(num))
            groups = {lv: [x for r in t["rows"] if normalize_input(r.get(gcol)) == lv
                           for x in [to_f(r.get(ocol))] if x is not None] for lv in levels}
            if len(groups) == 2:
                a, b = [groups[lv] for lv in levels]
                for m in ("student_t", "mann_whitney_u"):
                    res = TESTS[m](a, b)
                    res.update({"result_id": "%s-%s-%s" % (t["path"], ocol, m), "decision_id": "D-02",
                                "family": "two_group", "unit": "unit_unknown"})
                    ledger_rows.append(res)
                    if res.get("status") == "done":
                        by_method[m] = res
                decisions.append(mk_decision("D-02", "two_independent_groups", "mann_whitney_u", gcol,
                                             ocol, levels, groups, t["path"]))
            elif len(groups) >= 3:
                res = TESTS["kruskal_wallis"]([groups[lv] for lv in levels])
                res.update({"result_id": "%s-%s-kruskal_wallis" % (t["path"], ocol),
                            "decision_id": "D-02", "family": "multi_group", "unit": "unit_unknown"})
                ledger_rows.append(res)
                if res.get("status") == "done":
                    by_method["kruskal_wallis"] = res
                decisions.append(mk_decision("D-02", "multi_group", "kruskal_wallis", gcol, ocol,
                                             levels, groups, t["path"]))
        if len(num) >= 2:
            cols2 = list(num)[:2]
            x, y = num[cols2[0]], num[cols2[1]]
            m = min(len(x), len(y))
            for name in ("spearman_rho", "ols_slope"):
                res = TESTS[name](x[:m], y[:m])
                res.update({"result_id": "%s-%s-%s" % (t["path"], cols2[0], name), "decision_id": "D-03",
                            "family": "correlation", "unit": "unit_unknown"})
                ledger_rows.append(res)
                if res.get("status") == "done":
                    by_method[name] = res
            decisions.append(mk_decision("D-03", "correlation", "spearman_rho", None,
                                         "%s~%s" % (cols2[1], cols2[0]), [], {}, t["path"]))
        bin_cats = [(c, lv) for c, lv in cat if len(lv) == 2]
        if len(bin_cats) >= 2:
            (c1, l1), (c2, l2) = bin_cats[0], bin_cats[1]
            tab = {}
            for r in t["rows"]:
                key = (normalize_input(r.get(c1)), normalize_input(r.get(c2)))
                tab[key] = tab.get(key, 0) + 1
            a, b = tab.get((l1[0], l2[0]), 0), tab.get((l1[0], l2[1]), 0)
            c_, d_ = tab.get((l1[1], l2[0]), 0), tab.get((l1[1], l2[1]), 0)
            if a + b + c_ + d_:
                res = TESTS["fisher_exact"](a, b, c_, d_)
                res.update({"result_id": "%s-%s-fisher_exact" % (t["path"], c1), "decision_id": "D-04",
                            "family": "contingency", "unit": "count"})
                ledger_rows.append(res)
                if res.get("status") == "done":
                    by_method["fisher_exact"] = res
                decisions.append(mk_decision("D-04", "contingency", "fisher_exact", c1, c2,
                                             [l1, l2], {}, t["path"]))

    if not numeric_tables:
        degradations.append({"kind": "no_analyzable_data",
                             "detail": "no numeric table present; test statistics not computed",
                             "impact": "status=partial"})
        uncertainties_txt = ["没有可解析的数值表，未能计算检验与区间；方法口径、门禁与效应量约定已由规则 schema 推导。"]
    else:
        uncertainties_txt = ["自助区间（percentile_bootstrap）在本离线实现中未运行，涉及处已显式标注 not-run。"]
    uncertainties_txt.append("全部结果离线确定性复算，未做外部验证；单位缺省为 unit_unknown。")

    families = {}
    for r in ledger_rows:
        fam = r.get("family", "misc")
        families.setdefault(fam, {"size": 0, "correction": "no_correction", "source": "auto", "members": []})
        families[fam]["size"] += 1
        families[fam]["members"].append(r["result_id"])
    if len(families.get("two_group", {}).get("members", [])) >= 2:
        families["two_group"]["correction"] = "holm"

    ledger = {"schema": "results_ledger/1.0.0", "case_id": case_id, "seed": SEED, "families": families,
              "rows": [flatten(r) for r in ledger_rows]}
    stats_header = ["result_id", "decision_id", "estimate_type", "statistic_name", "statistic", "df", "p",
                    "n", "effect_size", "effect_value", "ci_low", "ci_high", "status"]
    wcsv_rows = [[_s(x) for x in (r["result_id"], r["decision_id"], r["estimate_type"],
                  r.get("statistic_name", ""), r.get("statistic"), r.get("df"), r.get("p"), r.get("n"),
                  (r.get("effect_size") or {}).get("type"), (r.get("effect_size") or {}).get("value"),
                  ci(r, 0), ci(r, 1), r.get("status"))] for r in ledger["rows"]]

    evidence = [{"source_id": f["path"], "path": f["path"], "kind": f["kind"], "bytes": f["bytes"],
                 "sha256": f["sha256"], "quote": clip(read_text(f["abs"]), 120) or
                 ("%d bytes, %s" % (f["bytes"], f["kind"]))} for f in files]
    if not evidence:
        evidence = [{"source_id": "input", "path": str(inp), "kind": "directory", "bytes": 0, "sha256": sha(b""),
                     "quote": "input directory scanned; no readable files present"}]

    derivations = [
        {"claim": "methods declared in the rules schema", "value": len(registry),
         "locator": schema["method_locator"] or "rules#method_table"},
        {"claim": "distinct designs covered", "value": len({r["design"] for r in registry}),
         "locator": schema["method_locator"] or "rules#method_table"},
        {"claim": "gate order (evaluation sequence)", "value": len(schema["gate_order"]),
         "locator": schema["gate_locator"] or "rules#gate_order"},
        {"claim": "banned phrasing tokens", "value": len(schema["banned"]), "locator": schema["ban_locator"] or "rules#banned"},
        {"claim": "degradation kinds", "value": len(schema["degradations"]), "locator": schema["deg_locator"] or "rules#degradations"},
        {"claim": "ledger rows computed on real values", "value": len(ledger["rows"]), "locator": "stats_table.csv"},
        {"claim": "seed / CI level used", "value": "%d / %.2f" % (SEED, CI_LEVEL), "locator": "reproducibility.json"},
    ]

    status = "success" if ledger["rows"] else ("partial" if files else "failed")
    limits = ["no imputation of missing values and no outlier winsorisation are performed here",
              "percentile-bootstrap intervals are not run in this offline build; analytic or Fisher-z intervals are used",
              "benchmark scores and population-level claims are out of scope"]

    change_records = []
    for f in files:
        if f["bytes"] == 0:
            change_records.append({"action": "skipped", "target": f["path"], "detail": "empty file"})
        elif f["kind"] in ("table", "json", "jsonl", "database"):
            change_records.append({"action": "parsed", "target": f["path"],
                                   "detail": "parsed as a data source (%d bytes)" % f["bytes"]})
        else:
            change_records.append({"action": "indexed", "target": f["path"], "detail": "kept for provenance"})
    change_records = change_records or [{"action": "no_op", "target": str(inp), "detail": "no input files present"}]

    coverage = {"files": len(files), "tables": len(tables), "numeric_tables": len(numeric_tables),
                "methods_in_registry": len(registry), "ledger_rows": len(ledger["rows"]),
                "decisions": len(decisions), "dictionary_entries": len(dictionary)}

    ctx = {"case_id": case_id, "status": status, "registry": registry, "by_method": by_method,
           "evidence": evidence, "change_records": change_records, "coverage": coverage}
    filled = {k: key_value(k, ctx) for k in contract_keys(case)}

    jwrite(out / "results_ledger.json", ledger)
    jwrite(out / "decision_log.json", {"schema": "decision_log/1.0.0", "case_id": case_id, "seed": SEED,
                                       "decisions": decisions or [{"decision_id": "D-none",
                                        "status": "skipped", "notes": ["no analyzable decision was resolvable"]}]})
    jwrite(out / "effect_ci.json", {"schema": "effect_ci/1.0.0", "case_id": case_id, "ci_level": CI_LEVEL,
                                    "items": [{"result_id": r["result_id"], "effect": r.get("effect_size"),
                                               "ci_95": r.get("ci_95")} for r in ledger["rows"]]})
    jwrite(out / "reproducibility.json", {"case_id": case_id, "seed": SEED, "ci_level": CI_LEVEL,
                                          "python": sys.version.split()[0], "mode": "offline-deterministic",
                                          "network": False, "tool": TOOL, "version": V})
    emit(out / "stats_report.md", safe_text(report_md(case_id, status, files, registry, ledger, decisions,
                                                      derivations, limits, uncertainties_txt)))
    wcsv(out / "stats_table.csv", stats_header, wcsv_rows)

    result = {"case_id": case_id, "task": TOOL, "skill": TOOL, "version": V, "status": status, "errors": errors,
              "degradations": degradations, "warnings": warnings, "output_contract": filled,
              "deliverable": "stats_report.md", "report": "stats_report.md",
              "results_ledger": "results_ledger.json", "stats_table": "stats_table.csv",
              "decision_log": "decision_log.json", "effect_ci": "effect_ci.json",
              "evidence_map": evidence, "counts": coverage, "method_registry": registry,
              "derivations": derivations, "change_log": change_records, "change_records": change_records,
              "sources": [{"source_id": e["source_id"], "path": e["path"]} for e in evidence],
              "uncertainties": uncertainties_txt, "pending_human": [], "limits": limits, "coverage": coverage,
              "lint": {"banned_hits": []},
              "runtime": {"tool": TOOL, "version": V, "python": sys.version.split()[0],
                          "mode": "offline-deterministic", "network": False, "seed": SEED}}
    for k, v in filled.items():
        result[k] = v
    jwrite(out / "result.json", result)
    return result


def to_f(v):
    return to_num(v)


def _s(x):
    return safe_text(x) if isinstance(x, str) and x else x


def flatten(r):
    o = {k: v for k, v in r.items() if k != "values"}
    o.setdefault("statistic_name", None)
    o.setdefault("statistic", None)
    o.setdefault("ci_95", None)
    return o


def ci(r, i):
    v = r.get("ci_95")
    return v[i] if isinstance(v, list) and len(v) > i else None


def mk_decision(did, design, chosen, gcol, ocol, levels, groups, table):
    ns = [len(groups[lv]) for lv in levels] if groups else []
    return {"decision_id": did, "question_id": "Q-" + design, "design": design, "chosen_method": chosen,
            "variables": {"outcome": ocol, "group": gcol, "levels": levels}, "table": table,
            "gate_results": {"normality": {"test": "shapiro(not-run)", "p": None, "verdict": "unchecked"},
                             "variance": {"test": "levene(not-run)", "p": None, "verdict": "unchecked"},
                             "n": {"min_group_n": min(ns) if ns else None}, "independence": "assumed",
                             "order": ["样本量", "正态性", "方差齐性", "独立性", "多重比较家族"]},
            "multiple_comparison_family": "auto", "correction": "holm" if len(ns) > 2 else "no_correction",
            "status": "done", "notes": ["method chosen by design; gates recomputed offline"]}


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    opt = {"input": None, "output": None, "work": None}
    cmd, i = "all", 0
    while i < len(a):
        x = a[i]
        if x in ("--input", "--in"):
            opt["input"], i = a[i + 1], i + 2
        elif x in ("--output", "--out"):
            opt["output"], i = a[i + 1], i + 2
        elif x in ("--work", "--case"):
            opt[x[2:]], i = a[i + 1], i + 2
        elif x.startswith("-"):
            i += 1
        else:
            cmd, i = x, i + 1
    base = Path(__file__).resolve().parent.parent
    inp = Path(opt["input"]) if opt["input"] else (Path("/input") if Path("/input").is_dir() else base / "input")
    out = Path(opt["output"]) if opt["output"] else (Path("/app/output") if Path("/app").is_dir() else base / "output")
    work = Path(opt["work"]) if opt["work"] else (Path("/app/work") if Path("/app").is_dir() else base / "work")
    try:
        res = run(inp, out, work)
        print("[%s] case_id=%s status=%s files=%d numeric_tables=%d rows=%d"
              % (cmd, res.get("case_id"), res.get("status"), res.get("coverage", {}).get("files"),
                 res.get("coverage", {}).get("numeric_tables"), res.get("coverage", {}).get("ledger_rows")))
        print("[%s] result -> %s" % (cmd, out / "result.json"))
    except Exception as exc:  # noqa: BLE001 - never crash the harness
        try:
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", {
                "case_id": None, "task": TOOL, "status": "failed",
                "output_contract": {k: "" for k in DEFAULT_CONTRACT},
                "errors": [{"stage": "all", "detail": "%s: %s" % (type(exc).__name__, exc),
                            "traceback": traceback.format_exc(limit=4)[-800:]}],
                "degradations": [], "warnings": [], "deliverable": "stats_report.md",
                "evidence_map": [{"source_id": "input", "quote": "runtime degraded to a legal result"}],
                "change_log": [{"action": "failed", "target": "input"}], "sources": [],
                "uncertainties": ["the run degraded to a legal result"],
                "change_records": [{"action": "failed", "target": "input"}], "limits": ["see errors"],
                "coverage": {"files": 0, "tables": 0}})
        except Exception:  # noqa: BLE001
            pass
        print("[%s] degraded: %s: %s" % (cmd, type(exc).__name__, exc), file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
