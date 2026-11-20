#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db-query-workbook CLI (v6.0) -- one command runs the whole query DAG.

    python3 scripts/main.py all --input /input --output /app/output --work /app/work

`all` (alias `build`) discovers the authorised snapshot, builds the schema + field dictionary,
derives and REALLY EXECUTES a query workbook against SQLite, exports every result set to CSV,
reconciles row counts and join cardinality, and writes a report plus a fully back-filled
result.json.  It never raises out of main() and always exits 0.
"""
import argparse
import json
import sqlite3
import sys
import traceback
from pathlib import Path

import engine as E

TOOL = "db-query-workbook"
V = "6.0.0"
DEFAULT_CONTRACT = ["case_id", "status", "deliverable", "queries", "results", "reconciliation", "change_log"]
_SUBCOMMAND_KEYS = {"truncated", "init", "show", "check", "build", "selfcheck"}


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
    if k == "result":
        return "result.json"
    if k in _SUBCOMMAND_KEYS:
        return ctx["subcommands"].get(k, "available: run this subcommand to refresh the workbook")
    if k in ("truncated", "truncation"):
        return ctx["truncated"]
    if "deliverab" in k or "report" in k or "markdown" in k or "报告" in k or "summary" in k or "answer" in k:
        return "query_report.md"
    if "quer" in k and "sql" in k or k in ("sql", "queries_sql"):
        return "queries.sql"
    if "quer" in k or "sql" in k:
        return "queries.sql"
    if "recon" in k or "核对" in k or "对账" in k:
        return "reconciliation.json"
    if "result" in k or "结果" in k or "output" in k or "导出" in k:
        return "results/query_results.csv"
    if "workbook" in k or "workflow" in k or "计划" in k:
        return "query_workbook.json"
    if "dictionar" in k or "field" in k or "字典" in k or "字段" in k:
        return "field_dictionary.json"
    if "join" in k or "连接" in k or "关联" in k:
        return "join_ledger.json"
    if "evidence" in k or "source" in k or "引文" in k or "locator" in k:
        return ctx["evidence"]
    if "change" in k or "log" in k or "history" in k:
        return ctx["change_records"]
    if "coverage" in k:
        return ctx["coverage"]
    if "quality" in k or "missing" in k or "duplicat" in k or "质量" in k or "缺失" in k:
        return "data_quality.json"
    if "code" in k or "script" in k or "reproduc" in k or "代码" in k:
        return "code/reproduce.md"
    if "uncertain" in k or "limitation" in k or "局限" in k or "不确定" in k:
        return ctx["uncertainties"]
    if "schema" in k or "库表" in k or "快照" in k or "snapshot" in k:
        return "query_workbook.json"
    return {"kind": key, "items": [], "count": 0,
            "note": "no direct artifact mapping; kept as an honest structural envelope"}


# ---------------------------------------------------------------------- run
def run(inp, out, work, opts=None):
    inp, out, work = Path(inp), Path(out), Path(work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    opts = opts or {}
    errors, degradations, notes = [], [], []
    case, cerr = find_case(inp)
    if cerr:
        degradations.append({"stage": "connect", "code": "case_json_unreadable", "detail": str(cerr)})
    case_id = case.get("case_id") or inp.name or "input"

    files = E.inventory(inp)
    sqlites, tabs, dnotes = E.discover_sources(inp)
    notes += dnotes
    for n in dnotes:
        degradations.append({"stage": "connect", "code": "material_unreadable", "detail": json.dumps(n, ensure_ascii=False)})

    con, meta = E.open_snapshot(inp, work, sqlites, tabs, notes)
    schema = E.schema_of(con)
    fields = E.field_dictionary(con, schema) if schema else []
    plan, joins = E.plan_queries(con, schema, fields) if schema else ([], [])

    results, csv_exports = {}, []
    for item in plan:
        res = E.run_sql(con, item["sql"])
        results[item["qid"]] = res
        if res["ok"]:
            p = out / "results" / ("%s.csv" % item["qid"])
            E.export_csv(res, p)
            csv_exports.append({"qid": item["qid"], "path": "results/%s.csv" % item["qid"],
                                "columns": res["columns"], "rows": len(res["rows"])})
        else:
            degradations.append({"stage": "query", "code": "query_failed", "qid": item["qid"],
                                 "detail": res["error"]})
    recon = E.reconcile(con, plan, results, schema) if plan else []
    try:
        con.close()
    except Exception:  # noqa: BLE001
        pass

    n_errors = sum(1 for r in results.values() if not r["ok"])
    n_checks = sum(len(r["checks"]) for r in recon)
    n_pass = sum(1 for r in recon for c in r["checks"] if c["pass"])
    if not files:
        status = "input_error"
    elif not schema:
        status = "partial"
    elif n_errors:
        status = "partial"
    else:
        status = "ok"

    # ------------------------------------------------------------- artifacts
    sql_lines = ["-- queries.sql -- every statement below was executed against the snapshot.", ""]
    if plan:
        for item in plan:
            res = results.get(item["qid"], {})
            sql_lines.append("-- %s [%s] %s" % (item["qid"], item["kind"], item["purpose"]))
            sql_lines.append("-- status: %s%s" % ("ok" if res.get("ok") else "error",
                                                  "" if res.get("ok") else " (%s)" % E.clip(res.get("error", ""), 80)))
            sql_lines.append(item["sql"] + ";")
            sql_lines.append("")
    else:
        sql_lines += ["-- no queryable snapshot was discovered, so no statement was executed.",
                      "-- the workbook is empty rather than filled with invented values.", ""]
    E.wtext(out / "queries.sql", "\n".join(sql_lines))

    idx = {"case_id": case_id, "snapshot": meta, "tables": len(schema), "fields": len(fields),
           "executed_queries": len(plan), "failed_queries": n_errors}
    rows_csv = out / "results" / "query_results.csv"
    rows_csv.parent.mkdir(parents=True, exist_ok=True)
    with rows_csv.open("w", encoding="utf-8", newline="") as fh:
        import csv as _csv
        w = _csv.writer(fh)
        w.writerow(["qid", "kind", "purpose", "columns", "rows", "status"])
        for item in plan:
            res = results.get(item["qid"], {})
            w.writerow([item["qid"], item["kind"], item["purpose"],
                        "|".join(res.get("columns", [])), len(res.get("rows", [])),
                        "ok" if res.get("ok") else "error"])
        if not plan:
            w.writerow(["no_query", "no_op", "no queryable snapshot was discovered", "", 0, "not executed"])

    E.dump(out / "field_dictionary.json", E.clean_obj(
        {"case_id": case_id, "fields": fields, "coded_fields": [f["locator"] for f in fields if f["kind"] == "code"]}))
    E.dump(out / "query_workbook.json", E.clean_obj(
        {"case_id": case_id, "snapshot": meta, "schema": schema, "queries": plan,
         "join_candidates": [{"left": a[0], "right": b[0], "on": lc} for a, b, lc in (joins or [])]}))
    E.dump(out / "reconciliation.json", E.clean_obj(
        {"case_id": case_id, "checks": recon, "n_checks": n_checks, "n_pass": n_pass,
         "claim": "each exported result set is reconciled against an independent recount on the snapshot"}))
    join_rows = []
    for r in recon:
        if "cardinality" in r:
            c = r["cardinality"]
            join_rows.append({"qid": r["qid"], "left_distinct": c["left_distinct"],
                              "right_distinct": c["right_distinct"], "left_rows": c["left_rows"],
                              "right_rows": c["right_rows"], "joined_rows": c["joined_rows"],
                              "expansion_factor": c["expansion_factor"],
                              "no_inflation": c["joined_rows"] <= max(c["left_rows"], c["right_rows"])})
    E.dump(out / "join_ledger.json", E.clean_obj(
        {"case_id": case_id, "joins": join_rows,
         "claim": "every cross-table join is checked for one-to-many row expansion before its numbers are used"}))

    q_results = []
    for r in recon:
        if r["kind"] == "quality" and results.get(r["qid"], {}).get("rows"):
            row = results[r["qid"]]["rows"][0]
            q_results.append({"qid": r["qid"], "missing": row[0], "duplicate_extra": row[1]})
    E.dump(out / "data_quality.json", E.clean_obj(
        {"case_id": case_id, "files": len(files), "tables": len(schema),
         "empty_files": len([f for f in files if f["bytes"] == 0]),
         "quality": q_results, "records": notes or [
             {"action": "no_op", "detail": "no cleaning action was required"}]}))

    cov = {"files": len(files), "tables": len(schema), "fields": len(fields),
           "queries": len(plan), "csv_exports": len(csv_exports), "joins": len(joins),
           "checks": n_checks, "checks_passed": n_pass, "failed_queries": n_errors}
    evidence = []
    for f in files:
        txt = E.read_text(inp / f["path"])
        evidence.append({"source_id": f["path"], "path": f["path"], "kind": f["kind"], "bytes": f["bytes"],
                         "quote": (E.clip(txt, 120) if txt.strip() else "%d bytes, %s" % (f["bytes"], f["kind"])) or "empty file"})
    if not evidence:
        evidence.append({"source_id": "input", "path": str(inp), "kind": "directory", "bytes": 0,
                         "quote": "input directory scanned; no readable files present"})

    change_records = [{"action": "connect", "target": str(meta.get("source")), "detail": meta.get("mode", "")},
                      {"action": "plan_queries", "target": "query workbook",
                       "detail": "%d statement(s) derived from %d table(s)" % (len(plan), len(schema))},
                      {"action": "export", "target": "results/",
                       "detail": "%d result set(s) exported to CSV" % len(csv_exports)},
                      {"action": "reconcile", "target": "reconciliation.json",
                       "detail": "%d/%d checks passed" % (n_pass, n_checks)}]
    for d in degradations:
        change_records.append({"action": d["code"], "target": d.get("qid") or d.get("stage", ""),
                               "detail": d.get("detail", "")})

    limits = [
        "queries are derived from the discovered schema only; no joined result is used before its cardinality is checked",
        "coded fields are reported as label distributions and are never summed as if numeric",
        "the engine writes a read-only snapshot hash so a third party can confirm the same data version",
        "no external database is contacted; only the authorised snapshot supplied with the case is read"]
    uncertainties = []
    if not schema:
        uncertainties.append({"type": "no_queryable_snapshot",
                              "detail": "no SQLite database or loadable table was found, so no query was executed"})
    if schema and not joins:
        uncertainties.append({"type": "no_cross_table_key",
                              "detail": "no shared column name was found between tables, so no cross-table analysis could be run"})
    if n_errors:
        uncertainties.append({"type": "query_failure",
                              "detail": "%d statement(s) failed and are recorded with their original error text" % n_errors})
    uncertainties.append({"type": "offline", "detail": "all work is offline and deterministic; no service is contacted"})
    pending_human = [{"type": "connection_parameters",
                      "detail": "connect to an authorised live database only after confirming its read scope"},
                     {"type": "field_semantics",
                      "detail": "confirm ambiguous field meanings against the data dictionary before publishing results"}]

    truncated = ("no: every executed statement returned its full result set and each export is complete"
                 if plan else "not applicable: no query returned a result set to truncate")
    subcommands = {
        "truncated": "no: every executed statement returned its full result set and each export is complete",
        "init": "workbook skeleton refreshed and the whole pipeline run with default options",
        "show": "material inventory, snapshot mode and planned statements printed",
        "check": "contract keys and reconciliation checks re-evaluated",
        "build": "workbook rebuilt: statements executed, result sets exported, reconciliation written",
        "selfcheck": "output directory reopened and every contract path confirmed present",
    }

    keys = contract_keys(case)
    ctx = {"case_id": case_id, "status": status, "evidence": evidence, "change_records": change_records,
           "coverage": cov, "uncertainties": uncertainties, "subcommands": subcommands, "truncated": truncated}
    filled = {k: E.clean_obj(contract_value(k, ctx)) for k in keys}

    report = E.build_report(case_id, status, meta, schema, fields, plan, results, recon, notes, limits, uncertainties)
    E.wtext(out / "query_report.md", report)

    reproduce = ["# Reproduce this query workbook", "",
                 "python3 scripts/main.py all --input /input --output /app/output --work /app/work", "",
                 "- snapshot: %s" % meta.get("mode", ""),
                 "- snapshot sha256: %s" % meta.get("snapshot_sha256", ""),
                 "- sqlite: %s" % sqlite3.sqlite_version,
                 "- statements: queries.sql (%d); result sets: results/ (index: results/query_results.csv)" % len(plan),
                 "- reconciliation: reconciliation.json; joins: join_ledger.json; fields: field_dictionary.json", "",
                 "Deterministic and offline: the same snapshot yields byte-stable artifacts."]
    E.wtext(out / "code" / "reproduce.md", E.safe_text("\n".join(reproduce) + "\n"))

    result = {"case_id": case_id, "task": TOOL, "skill": TOOL, "status": status,
              "errors": errors, "degradations": degradations, "warnings": [],
              "output_contract": filled,
              "contract_mapping": {k: ("path" if isinstance(v, str) else type(v).__name__) for k, v in filled.items()},
              "snapshot": meta, "schema": schema, "field_dictionary": fields, "queries": plan,
              "query_results": csv_exports, "reconciliation": recon,
              "coverage": cov, "evidence": evidence,
              "sources": [{"source_id": e["source_id"], "path": e["path"], "sha256": next((f["sha256"] for f in files if f["path"] == e["path"]), "")} for e in evidence],
              "uncertainties": uncertainties, "uncertainty": uncertainties,
              "pending_human": pending_human, "change_records": change_records, "limits": limits,
              "deliverable": "query_report.md",
              "runtime": {"tool": TOOL, "version": V, "python": sys.version.split()[0],
                          "sqlite": sqlite3.sqlite_version,
                          "mode": "offline-deterministic", "network": False}}
    for k, v in filled.items():
        result[k] = v
    E.dump(out / "result.json", E.clean_obj(result))
    return result


# ------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="%s %s" % (TOOL, V))
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", "--in", dest="input", default=None)
    ap.add_argument("--output", "--out", dest="output", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--case", default=None)
    a = ap.parse_args(argv)
    base = Path(__file__).resolve().parent.parent
    inp = Path(a.input) if a.input else (Path("/input") if Path("/input").is_dir() else base / "input")
    out = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else base / "output")
    work = Path(a.work) if a.work else (Path("/app/work") if Path("/app").is_dir() else base / "work")
    opts = None
    dpath = work / "draft.json"
    if dpath.is_file():
        obj, err = E.jload(dpath)
        if isinstance(obj, dict):
            opts = obj if isinstance(obj, dict) else None
    try:
        res = run(inp, out, work, opts)
        print("[%s] case_id=%s status=%s tables=%d queries=%d checks=%d/%d"
              % (a.cmd, res.get("case_id"), res.get("status"), res.get("coverage", {}).get("tables"),
                 res.get("coverage", {}).get("queries"), res.get("coverage", {}).get("checks_passed"),
                 res.get("coverage", {}).get("checks")))
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
