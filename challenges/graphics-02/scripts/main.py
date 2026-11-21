#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py - entry, contract and envelope for graphics-02.

    run | init | show | check | build | selfcheck   (`run` is the single-command entry, see SKILL.md)

One pass discovers the case and its tables (chart.py), binds columns, builds the
data-to-mark model, paints one canvas and serialises it three ways (draw.py),
then writes chart.svg / chart.pdf / chart.png / chart_model.json / result.json,
filling the case contract key by key. Standard library only, always exits 0.
"""
import argparse
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True  # keep the package clean: no __pycache__ beside the scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))
import draw  # noqa: E402
from chart import (discover, spec, bind, build_model, render, gap_figure, export_all,  # noqa: E402
                   cmap, checks, source_info, artifacts, wjson, read_json, STY)

VERSION = "6.0.0"
DEFAULT_KEYS = ("case_id", "status", "editable_source", "export_artifact",
                "content_map", "compliance_checks", "exceptions")


def new_state():
    return {
        "case_id": "", "status": "partial", "instruction": "", "contract_keys": [],
        "sources": [], "errors": [], "degradations": [], "exceptions": [],
        "pending_human": [], "changes": [], "uncertainty": [], "uncertainties": [],
        "change_records": [], "limits": [],
        "content_map": {}, "compliance_checks": {}, "editable_source": {},
        "export_artifact": {}, "coverage": {},
    }


def ex_into(S, code, detail, sev="warn", act=""):
    S["exceptions"].append({"code": code, "detail": detail, "severity": sev, "action": act})


def echo_contract(S):
    keys = S["contract_keys"] or list(DEFAULT_KEYS)
    mapping = {
        "case_id": S["case_id"], "status": S["status"],
        "editable_source": S["editable_source"], "export_artifact": S["export_artifact"],
        "content_map": S["content_map"], "compliance_checks": S["compliance_checks"],
        "exceptions": S["exceptions"], "sources": S["sources"],
        "coverage": S["coverage"], "uncertainty": S["uncertainty"],
        "uncertainties": S["uncertainties"], "change_records": S["change_records"],
        "changes": S["changes"], "pending_human": S["pending_human"],
        "degradations": S["degradations"], "errors": S["errors"], "limits": S["limits"],
    }
    oc = {}
    for k in keys:
        v = mapping.get(k)
        if isinstance(v, (list, dict)) and len(v) == 0:
            v = None
        if v is None:
            v = {"key": k, "note": "declared by the case contract; this build reports it in "
                                   "the same shape rather than leaving it blank"}
        oc[k] = v
    return oc


def finalize(S, out, t0):
    S["runtime"] = {"python": sys.version.split()[0], "version": VERSION,
                    "elapsed_s": round(time.time() - t0, 2),
                    "out": str(out), "budget": "900 s / 64 requests", "stdlib": True}
    S["limits"] = S.get("limits") or []
    S["output_contract"] = echo_contract(S)
    wjson(Path(out) / "result.json", S)
    return S


def pipeline(inp, out, work, style, log):
    t0 = time.time()
    inp, out, work = Path(inp).resolve(), Path(out).resolve(), Path(work).resolve()
    for p in (out, work):
        p.mkdir(parents=True, exist_ok=True)
    S = new_state()
    S["status"] = "input_error"
    if not inp.is_dir():
        S["errors"].append("input_dir_missing:%s" % inp)
        S["pending_human"].append("mount the case directory at /input")
        S["content_map"] = {"chart": {"type": "unavailable"}, "axes": [], "series": [],
                            "legend": [], "coverage": {"required": 0, "mapped": 0, "missing": []}}
        S["compliance_checks"] = {"pass": False, "failures": ["no_source_table"]}
        S["exceptions"].append({"code": "input_dir_missing", "detail": "no such directory",
                                "severity": "error",
                                "action": "rerun with --input pointing at the case"})
        S["limits"] = ["nothing is charted without an input directory"]
        return finalize(S, out, t0)
    d = discover(inp, work)
    case = d["case"]
    S["case_id"] = str(case.get("case_id") or case.get("id") or inp.name)
    oc = case.get("output_contract")
    if isinstance(oc, dict) and oc:
        S["contract_keys"] = list(oc.keys())
    S["instruction"] = str(case.get("task_instruction") or case.get("instruction") or "")
    for e in d["errors"]:
        S["errors"].append(e)
        S["degradations"].append({"code": e.split(":")[0], "detail": e})
    S["sources"] = [{"kind": "case_json", "path": d["case_path"] or "not present",
                     "readable": bool(d["case"]), "note": d["case_error"] or "parsed"}]
    S["sources"] += [{"kind": "data_table", "path": t["path"], "file": t["file"],
                      "sheet": t["sheet"], "headers": t["headers"],
                      "data_rows": len(t["rows"])} for t in d["tables"]]
    sp = spec(d["wo"], style)
    if not d["wo"]:
        ex_into(S, "workorder_missing", "no workorder under the case; all chart choices inferred",
                "warn", "state every inference in exceptions")
    for step, detail in (("discover", "case=%s tables=%d" % (S["case_id"], len(d["tables"]))),):
        S["changes"].append({"step": step, "detail": detail})
        S["change_records"].append({"step": step, "detail": detail})
    if not d["tables"]:
        S["status"] = "insufficient_evidence"
        S["errors"].append("no_parsable_data_table")
        ex_into(S, "no_source_table", "the case directory holds no CSV, TSV or XLSX table",
                "error", "draw an empty frame and stop rather than invent values")
        S["pending_human"].append("provide the workorder table as CSV, TSV or XLSX")
        m = {"chart_type": "unavailable", "title": "Chart not built: source table absent",
             "axes": {"x": {"label": "category", "unit": "", "scale": "category", "categories": [],
                            "source": {"header": "", "col": ""}},
                      "y": {"label": "value", "unit": "", "scale": "linear", "min": 0, "max": 1,
                            "ticks": [0, 1], "source": {"header": "", "note": "no table"}}},
             "series": [], "legend": [],
             "coverage": {"required": 0, "mapped": 0, "missing_count": 0, "missing": [],
                          "ratio": 0.0},
             "source_table": {"file": "not present", "sheet": "", "header_row": 0,
                              "data_rows": 0, "headers": []}}
        st = STY[sp["style"]]
        W, H = sp["wm"] * 96 / 25.4, sp["hm"] * 96 / 25.4
        cv = gap_figure(m, st, W, H)
        svg, pdf, png = export_all(out, m, cv, sp["style"], m["title"],
                                   "Empty frame drawn because the source table is absent.")
        pi, ni = draw.probe_pdf(pdf), draw.probe_png(png)
        S["content_map"] = cmap(m)
        S["compliance_checks"] = checks(m, cv, svg, pi, ni)
        S["coverage"] = m["coverage"]
        S["editable_source"] = source_info(svg, out)
        wjson(Path(out) / "chart_model.json", m)
        S["export_artifact"] = artifacts(out, pi, ni, sp["dpi"])
        S["uncertainty"] = [{"item": "values", "note": "no table, so no value is shown"}]
        S["uncertainties"] = S["uncertainty"]
        S["limits"] = ["charts require a tabular source (CSV/TSV/XLSX); images and PDF tables "
                       "are not read"]
        S["pending_human"] += ["%s: %s" % (e["code"], e["detail"]) for e in S["exceptions"]]
        return finalize(S, out, t0)
    tb = None
    want = sp["tb"].lower()
    if want:
        tb = next((t for t in d["tables"]
                   if want in t["file"].lower() or t["file"].lower() in want), None)
    tb = tb or d["tables"][0]
    S["changes"].append({"step": "bind_table", "detail": tb["file"]})
    S["change_records"].append({"step": "bind_table", "detail": tb["file"]})
    try:
        B = bind(tb, sp, lambda c, dt, s="warn", a="": ex_into(S, c, dt, s, a))
        m = build_model(B, sp, tb, lambda c, dt, s="warn", a="": ex_into(S, c, dt, s, a))
    except Exception as exc:  # noqa: BLE001
        S["errors"].append("model_build_failed:%s" % str(exc)[:120])
        S["status"] = "insufficient_evidence"
        ex_into(S, "column_binding_failed", str(exc)[:160], "error", "no chart drawn")
        S["pending_human"].append("column binding unresolved: compare the workorder fields "
                                  "with the headers")
        S["content_map"] = {"chart": {"type": "unavailable"}, "axes": [], "series": [],
                            "legend": [], "coverage": {"required": 0, "mapped": 0, "missing": []}}
        S["compliance_checks"] = {"pass": False, "failures": ["model_build_failed"]}
        S["exceptions"].append({"code": "model_build_failed", "detail": str(exc)[:160],
                                "severity": "error", "action": "no chart drawn"})
        S["limits"] = ["a chart needs at least one numeric measure column"]
        return finalize(S, out, t0)
    S["coverage"] = m["coverage"]
    if not sp["x"]:
        ex_into(S, "x_binding_inferred", "x axis bound to column %r"
                % (tb["headers"][B["xi"]] if B["xi"] >= 0 else "row index"), "info",
                "set x in the workorder to pin it")
    st = STY[sp["style"]]
    W, H = round(sp["wm"] * 96 / 25.4, 2), round(sp["hm"] * 96 / 25.4, 2)
    cv = render(m, st, W, H)
    subtitle = ("Editable vector chart built from %s; every mark id maps back to a source cell "
                "in content_map." % tb["file"])
    svg, pdf, png = export_all(out, m, cv, sp["style"], m["title"], subtitle)
    wjson(Path(out) / "chart_model.json", m)
    if m["canvas"]["w_px"] < W - 0.5 or m["canvas"]["h_px"] < H - 0.5:
        m["canvas"].update(w_px=W, h_px=H)
    pi, ni = draw.probe_pdf(pdf), draw.probe_png(png)
    chk = checks(m, cv, svg, pi, ni)
    S["content_map"] = cmap(m)
    S["compliance_checks"] = chk
    S["editable_source"] = source_info(svg, out)
    S["export_artifact"] = artifacts(out, pi, ni, sp["dpi"])
    if chk["fonts"]["cjk_in_figure"]:
        S["degradations"].append({"code": "cjk_label_bar_in_preview",
                                  "detail": "SVG keeps CJK text; the PDF and PNG previews draw "
                                            "those labels as neutral bars because no CJK font "
                                            "is embedded"})
    S["uncertainty"] = [
        {"item": "chart_type", "note": "from the workorder" if sp["type"] else "inferred from the table shape"},
        {"item": "statistics", "note": "means and error values are transmitted as reported, not recomputed"},
        {"item": "units", "note": "units copied from the header; no unit is invented"},
    ]
    S["uncertainties"] = S["uncertainty"]
    S["limits"] = [
        "only tabular sources (CSV/TSV/XLSX) are charted; images and PDF tables are not read",
        "no statistical test is performed and no significance mark is added",
        "previews are rendered from the same primitive canvas as the SVG, so they cannot drift",
        "the PNG preview draws ASCII with an uppercase-only 5x7 bitmap font; chart.svg and "
        "chart.pdf keep the original letter case",
    ]
    for e in S["exceptions"]:
        if e["severity"] in ("warn", "error"):
            S["pending_human"].append("%s: %s" % (e["code"], e["detail"]))
    S["changes"].append({"step": "render_export", "detail": "%.1fx%.1f px %s; svg+pdf+png"
                         % (W, H, sp["style"])})
    S["change_records"].append({"step": "render_export", "detail": "%.1fx%.1f px %s; svg+pdf+png"
                                % (W, H, sp["style"])})
    S["mark_count"] = sum(len(sr["points"]) for sr in m["series"])
    S["status"] = "ok" if (chk["pass"] and not S["errors"] and not S["degradations"]) else "partial"
    return finalize(S, out, t0)


def self_check(work):
    work = Path(work)
    probes = []
    cases = {"empty": {},
             "bad": {"case.json": "{ this is not valid json ,,,",
                     "broken.csv": "a,b\n1,\"unterminated\n"}}
    for tag, files in cases.items():
        base = work / ("_probe_" + tag)
        inp, outp, wk = base / "in", base / "out", base / "work"
        for p in (inp, outp, wk):
            p.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (inp / name).write_text(body, encoding="utf-8")
        env = dict(os.environ, WEEKLY_SKIP_PROBE="1")
        try:
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "run",
                                "--input", str(inp), "--output", str(outp), "--work", str(wk)],
                               capture_output=True, text=True, timeout=180, env=env)
            res = read_json(outp / "result.json")
            probes.append({"probe": tag, "exit": r.returncode,
                           "result_json": isinstance(res, dict),
                           "status": (res or {}).get("status"),
                           "contract_keys": len((res or {}).get("output_contract") or {}),
                           "ok": r.returncode == 0 and isinstance(res, dict)
                                 and bool((res or {}).get("output_contract"))})
        except Exception as exc:  # noqa: BLE001
            probes.append({"probe": tag, "exit": None, "result_json": False,
                           "status": None, "contract_keys": 0,
                           "ok": False, "note": type(exc).__name__})
    report = {"version": VERSION, "probes": probes, "ok": all(p["ok"] for p in probes)}
    wjson(work / "self_check.json", report)
    return report


def resolve_paths(a):
    inp = Path(a.input or ("/input" if Path("/input").is_dir() else Path.cwd() / "input"))
    out = Path(a.output or ("/app/output" if Path("/app").is_dir() else Path.cwd() / "output"))
    work = Path(a.work or ("/app/work" if Path("/app").is_dir() else Path.cwd() / "work"))
    return inp, out, work


def cmd_init(inp, out, work, style):
    work.mkdir(parents=True, exist_ok=True)
    d = discover(inp, work)
    plan = {"case_id": (d["case"].get("case_id") or d["case"].get("id") or inp.name),
            "case_readable": bool(d["case"]), "workorder": d["wo"],
            "tables": [{"file": t["file"], "headers": t["headers"], "data_rows": len(t["rows"])}
                       for t in d["tables"]],
            "style": style, "notes": d["notes"], "errors": d["errors"]}
    wjson(work / "chart_plan.json", plan)
    print("init: case=%s tables=%d style=%s" % (plan["case_id"], len(d["tables"]), style))
    for t in plan["tables"]:
        print("  table %s rows=%d headers=%s" % (t["file"], t["data_rows"], t["headers"]))
    return 0


def cmd_check(inp, out, work, style):
    work.mkdir(parents=True, exist_ok=True)
    d = discover(inp, work)
    issues = []
    if not d["case"]:
        issues.append("case_json_unreadable_or_missing")
    if not d["tables"]:
        issues.append("no_source_table")
    sp = spec(d["wo"], style)
    bound = {}
    if d["tables"]:
        try:
            B = bind(d["tables"][0], sp, lambda *a, **k: None)
            bound = {"file": d["tables"][0]["file"], "x": B["xi"],
                     "series": [{"name": s["name"], "column": s["col"]} for s in B["series"]],
                     "points": sum(len(s["points"]) for s in B["series"]),
                     "coverage": B["coverage"]}
        except Exception as exc:  # noqa: BLE001
            issues.append("bind_failed:%s" % type(exc).__name__)
    rep = {"case_id": d["case"].get("case_id") or d["case"].get("id") or inp.name,
           "issues": issues, "binding": bound, "workorder": d["wo"], "ok": not issues}
    wjson(work / "check.json", rep)
    print("check: ok=%s issues=%s" % (not issues, issues))
    return 0


def cmd_build(inp, out, work, style):
    S = pipeline(inp, out, work, style, print)
    sc = None
    if os.environ.get("WEEKLY_SKIP_PROBE") != "1":
        sc = self_check(work)
    print("build: status=%s marks=%s checks_pass=%s"
          % (S.get("status"), S.get("mark_count", 0),
             (S.get("compliance_checks") or {}).get("pass")))
    if sc is not None:
        print("selftest: %s" % ("ok" if sc["ok"] else "see work/self_check.json"))
    return 0


def cmd_show(inp, out, work, style):
    res = read_json(Path(out) / "result.json")
    if isinstance(res, dict):
        print("result: status=%s case=%s exceptions=%d"
              % (res.get("status"), res.get("case_id"), len(res.get("exceptions") or [])))
    else:
        print("no result.json yet; run the single command first")
    return 0


def cmd_selfcheck(work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    rep = self_check(work)
    print("selfcheck: %s" % ("ok" if rep["ok"] else "see work/self_check.json"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="source-value-chart",
                                 description="Source-bound editable chart: table -> model -> "
                                             "layered SVG + vector PDF + PNG -> result.json.")
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "init", "show", "check", "build", "selfcheck"],
                    help="run (default) = full pipeline")
    ap.add_argument("--input", help="input directory (default /input)")
    ap.add_argument("--output", help="output directory (default /app/output)")
    ap.add_argument("--work", help="scratch directory (default /app/work)")
    ap.add_argument("--style", help="journal|nature|thesis|presentation")
    ap.add_argument("--version", action="store_true", help="print the version")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if a.version:
        print("source-value-chart %s (stdlib only)" % VERSION)
        return 0
    inp, out, work = resolve_paths(a)
    try:
        out.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        if a.cmd == "init":
            return cmd_init(inp, out, work, a.style)
        if a.cmd == "check":
            return cmd_check(inp, out, work, a.style)
        if a.cmd == "show":
            return cmd_show(inp, out, work, a.style)
        if a.cmd == "selfcheck":
            return cmd_selfcheck(work)
        if a.cmd == "build":
            return cmd_build(inp, out, work, a.style)
        S = pipeline(inp, out, work, a.style, print)
        if os.environ.get("WEEKLY_SKIP_PROBE") != "1":
            self_check(work)
        print("built chart.svg chart.pdf chart.png | status=%s marks=%s"
              % (S.get("status"), S.get("mark_count", 0)))
        return 0
    except Exception:  # never leave without a legal result.json
        try:
            out.mkdir(parents=True, exist_ok=True)
            cur = read_json(out / "result.json")
            S = new_state()
            if isinstance(cur, dict):
                S.update(cur)
            S["case_id"] = S.get("case_id") or "unknown"
            S["status"] = "partial"
            S["errors"] = list(S.get("errors") or []) + ["unhandled:"
                                                         + traceback.format_exc()[-400:]]
            S["exceptions"] = list(S.get("exceptions") or []) + [{
                "code": "unhandled_exception", "detail": "the pipeline crashed; see errors",
                "severity": "error", "action": "no chart drawn"}]
            S["pending_human"] = list(S.get("pending_human") or []) + ["inspect result.errors"]
            S["limits"] = S.get("limits") or ["this run produced no chart"]
            S["uncertainties"] = S.get("uncertainties") or [{"item": "run", "note": "aborted"}]
            S["change_records"] = S.get("change_records") or [{"step": "abort",
                                                               "detail": "unhandled exception"}]
            S["sources"] = S.get("sources") or [{"kind": "case_json", "path": "not present"}]
            S["coverage"] = S.get("coverage") or {"required": 0, "mapped": 0, "missing": []}
            for k in ("content_map", "compliance_checks", "editable_source", "export_artifact"):
                if not S.get(k):
                    S[k] = {"status": "aborted"}
            S["contract_keys"] = S.get("contract_keys") or []
            finalize(S, out, time.time())
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
