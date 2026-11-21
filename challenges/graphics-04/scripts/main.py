#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py - entry, contract and envelope for graphics-04.

    run | init | show | check | build | selfcheck      (`run` is the single-command entry, see SKILL.md)

One pass reads the materials (sheet.py), lays the apparatus and the steps out,
paints one canvas and serialises it three ways (draw.py), then writes
figure.svg / figure.pdf / figure.png / figure_model.json / result.json, filling
the case contract key by key. Standard library only, always exits 0.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True  # keep the package clean: no __pycache__ beside the scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))
import draw  # noqa: E402
import sheet  # noqa: E402
from sheet import (discover, build_model, layout, render, gap_render, checks, cmap,  # noqa: E402
                   wjson, read_json, E)

VERSION = "6.0.0"
DEFAULT_KEYS = ("case_id", "status", "editable_source", "export_artifact",
                "content_map", "compliance_checks", "exceptions")
CANVAS_W = 1440.0
GAP_H = 560.0


def new_state():
    return {
        "case_id": "", "status": "partial", "contract_keys": [],
        "editable_source": {}, "export_artifact": {}, "content_map": {},
        "compliance_checks": {}, "exceptions": [], "sources": [], "uncertainty": [],
        "uncertainties": [], "pending_human": [], "errors": [], "degradations": [],
        "changes": [], "change_records": [], "limits": [], "coverage": {},
        "instruction": "",
    }


def echo_contract(S):
    """Fill every contract key with a real value; never leave a key empty."""
    keys = S.get("contract_keys") or list(DEFAULT_KEYS)
    mapping = {
        "case_id": S.get("case_id"), "status": S.get("status"),
        "editable_source": S.get("editable_source"), "export_artifact": S.get("export_artifact"),
        "content_map": S.get("content_map"), "compliance_checks": S.get("compliance_checks"),
        "exceptions": S.get("exceptions"), "sources": S.get("sources"),
        "uncertainty": S.get("uncertainty"), "uncertainties": S.get("uncertainties"),
        "changes": S.get("changes"), "change_records": S.get("change_records"),
        "pending_human": S.get("pending_human"), "degradations": S.get("degradations"),
        "errors": S.get("errors"), "limits": S.get("limits"),
        "coverage": S.get("coverage"), "runtime": S.get("runtime"),
    }
    oc = {}
    for k in keys:
        v = mapping.get(k)
        if isinstance(v, (list, dict)) and len(v) == 0:
            v = None
        if v is None:
            v = {"key": k, "note": "declared by the case contract; reported in this shape for "
                                   "this run rather than left blank"}
        oc[k] = v
    return oc


def finalize(S, out, t0, argv):
    S["runtime"] = {"version": VERSION, "seconds": round(time.time() - t0, 2),
                    "python": sys.version.split()[0], "argv": argv, "out": str(out),
                    "stdlib": True}
    S["output_contract"] = echo_contract(S)
    wjson(Path(out) / "result.json", S)
    return S


def pipeline(inp, out, work):
    t0 = time.time()
    inp, out, work = Path(inp).resolve(), Path(out).resolve(), Path(work).resolve()
    for p in (out, work):
        p.mkdir(parents=True, exist_ok=True)
    S = new_state()
    S["status"] = "input_error"
    if not inp.is_dir():
        S["errors"].append("input_dir_missing:%s" % inp)
        S["exceptions"].append({"code": "input_dir_missing", "message": "no such directory",
                                "severity": "blocking", "action": "rerun with --input"})
        S["pending_human"].append("mount the case directory at /input")
        S["content_map"] = {"parts": [], "connections": [], "steps": [], "stages": [],
                            "legend": [], "panels": [], "coverage": {}}
        S["compliance_checks"] = {"pass": False, "failures": ["no_drawable_entities"]}
        S["limits"] = ["nothing is drawn without an input directory"]
        return finalize(S, out, t0, sys.argv[1:])
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
    S["sources"] = [{"id": x["id"], "path": x["path"], "name": x["name"], "kind": x["kind"],
                     "chars": len(x["text"]), "lines": len(x["text"].splitlines())}
                    for x in d["docs"]]
    m = build_model(d, S["exceptions"])
    S["changes"].append({"target": "figure.svg", "original": "",
                         "revised": "rebuilt from the source materials",
                         "locator": "not applicable",
                         "reason": "rebuild task: the material carries no existing figure"})
    S["change_records"].append({"step": "ingest",
                                "detail": "%d documents, %d parts, %d connections, %d steps"
                                % (len(d["docs"]), len(m["parts"]), len(m["conns"]), len(m["steps"]))})
    W = CANVAS_W
    svg2 = None
    foot = ("Sources: %s | every element carries a locator and a verbatim quote in content_map | v%s"
            % ("、".join("%s(%s)" % (x["id"], x["name"]) for x in d["docs"][:4]) or "no material",
               VERSION))
    if not m["parts"] and not m["steps"]:
        S["status"] = "insufficient_evidence"
        S["exceptions"].append({"code": "no_drawable_entities",
                                "message": "the materials hold no apparatus list and no numbered steps",
                                "severity": "blocking",
                                "action": "draw an empty frame and stop rather than invent a process"})
        S["pending_human"].append("provide the parts list / connections / steps")
        H = GAP_H
        cv = gap_render(m, W, H, foot)
        svg = draw.export_svg(cv, W, H, m["title"], "Empty frame: the materials are silent.")
        panels, cov = [], {"parts": 0, "connections": 0, "steps": 0, "stages": 0,
                           "panels": [], "verified_rate": 0.0}
    else:
        geo = layout(m, W)
        H = geo["H"]
        cv = render(m, W, H, geo, foot)
        sub = "Editable apparatus/process sheet; every id maps to content_map."
        svg = draw.export_svg(cv, W, H, m["title"], sub)
        svg2 = draw.export_svg(cv, W, H, m["title"], sub)
        panels = [{"panel": 1, "kind": "apparatus", "svg_layer": "layer-apparatus"}]
        if m["steps"]:
            panels.append({"panel": 2, "kind": "process", "svg_layer": "layer-steps"})
        items = m["parts"] + m["conns"] + m["steps"]
        ver = len([x for x in items if x.get("source_verified")])
        cov = {"parts": len(m["parts"]), "connections": len(m["conns"]),
               "steps": len(m["steps"]), "stages": len(m["stages"]),
               "panels": [p["kind"] for p in panels],
               "verified_rate": round(ver / float(len(items)), 3) if items else 0.0}
    pdf = draw.export_pdf(cv, W, H)
    png = draw.export_png(cv, W, H)
    pi, ni = draw.inspect_pdf(pdf), draw.inspect_png(png)
    chk = checks(m, cv, svg, pi, ni, W, H)
    if m["parts"] or m["steps"]:
        S["status"] = "ok" if (chk["pass"] and not S["errors"]) else "partial"
    if svg2 is not None:
        chk["determinism"]["rerender_identical"] = (svg == svg2)
        S["change_records"].append({"step": "render_export",
                                    "detail": "one canvas -> svg/pdf/png; %d layers, %d ids"
                                    % (len(re.findall(r'<g id="layer-', svg)), svg.count(' id="'))})
    (out / "figure.svg").write_bytes(svg.encode("utf-8"))
    (out / "figure.pdf").write_bytes(pdf)
    (out / "figure.png").write_bytes(png)
    for x in m["parts"] + m["steps"]:
        for k in ("_x", "_y", "_w", "_h"):
            x.pop(k, None)
    wjson(out / "figure_model.json",
          {"kind": m["kind"], "title": m["title"], "canvas": {"w_px": W, "h_px": round(H, 2)},
           "parts": m["parts"], "connections": m["conns"], "steps": m["steps"],
           "stages": m["stages"], "legend": m["legend"], "panels": panels})
    model_bytes = (out / "figure_model.json").stat().st_size
    S["content_map"] = cmap(m, panels, cov)
    S["coverage"] = cov
    S["compliance_checks"] = chk
    layers = re.findall(r'<g id="(layer-[^"]+)"', svg)
    S["editable_source"] = {
        "path": "figure.svg", "format": "svg", "editable": True, "text_selectable": True,
        "layers": layers, "layer_count": len(layers), "viewBox": [W, round(H, 2)],
        "text_count": svg.count("<text"), "bytes": len(svg.encode("utf-8")),
        "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        "model": "figure_model.json", "font_stack": draw.FONT_STACK}
    S["export_artifact"] = {
        "svg": {"path": "figure.svg", "role": "editable vector master",
                "bytes": len(svg.encode("utf-8"))},
        "pdf": {"path": "figure.pdf", "engine": "builtin-vector-pdf", "vector": pi.get("vector"),
                "pages": pi.get("pages"), "mediabox_pt": pi.get("mediabox_pt"),
                "bytes": pi.get("bytes")},
        "png": {"path": "figure.png", "engine": "builtin-raster", "width": ni.get("width"),
                "height": ni.get("height"), "dpi": 96, "color_type": ni.get("color_type"),
                "unique_colors": ni.get("unique_colors"), "bytes": ni.get("bytes")},
        "model": {"path": "figure_model.json", "role": "layout model with source locators",
                  "bytes": model_bytes},
    }
    S["limits"] = [
        "a connection is drawn only when both ends resolve to a listed part; a half arrow is never drawn",
        "quantities and media are transmitted as written; no value is completed or rounded up",
        "the PDF and PNG previews draw non-Latin-1 text as neutral bars (no CJK face is embedded); "
        "figure.svg keeps every label as live text",
        "no 3D likeness of the apparatus is attempted: the sheet is a labelled block-and-arrow schematic",
    ]
    S["uncertainty"] = [
        {"item": "figure_kind", "note": "from the workorder" if d["wo"] else "inferred from the material"},
        {"item": "layout", "note": "longest-path layering of the connection graph, material order for ties"},
        {"item": "media", "note": "the medium word is copied from the source line, then classified"},
    ]
    if not d["wo"]:
        S["pending_human"].append("workorder_missing: confirm figure kind and required parts")
    if any(p.get("qty") is None for p in m["parts"]):
        S["pending_human"].append("confirm quantities: " +
                                  "、".join(p["name"] for p in m["parts"] if p.get("qty") is None))
    S["pending_human"] += ["confirm connection without both ends: %s -> %s" % (c["from"], c["to"])
                           for c in m["conns"] if not c.get("drawable")]
    unverified = [x for x in m["parts"] + m["conns"] + m["steps"] if not x.get("source_verified")]
    if unverified:
        S["pending_human"].append("confirm elements without a verbatim source: " + "、".join(
            str(x.get("name") or x.get("title") or x.get("id")) for x in unverified))
    for e in S["exceptions"]:
        if e["severity"] in ("major", "blocking"):
            S["uncertainty"].append("%s: %s" % (e["code"], e["message"]))
    S["uncertainties"] = S["uncertainty"]
    return finalize(S, out, t0, sys.argv[1:])


def self_check(work):
    work = Path(work)
    probes = []
    cases = {"empty": {},
             "bad": {"case.json": "{ this is not valid json ,,,",
                     "notes.txt": "[待写]\n", "broken.md": ""}}
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
            probes.append({"probe": tag, "exit": None, "result_json": False, "status": None,
                           "contract_keys": 0, "ok": False, "note": type(exc).__name__})
    rep = {"version": VERSION, "probes": probes, "ok": all(p["ok"] for p in probes)}
    wjson(work / "self_check.json", rep)
    return rep


def resolve_paths(a):
    inp = Path(a.input or ("/input" if Path("/input").is_dir() else Path.cwd() / "input"))
    out = Path(a.output or ("/app/output" if Path("/app").is_dir() else Path.cwd() / "output"))
    work = Path(a.work or ("/app/work" if Path("/app").is_dir() else Path.cwd() / "work"))
    return inp, out, work


def cmd_init(inp, out, work):
    work.mkdir(parents=True, exist_ok=True)
    d = discover(inp, work)
    plan = {"case_id": (d["case"].get("case_id") or d["case"].get("id") or inp.name),
            "case_readable": bool(d["case"]), "workorder": d["wo"], "notes": d["errors"],
            "documents": [{"id": x["id"], "name": x["name"], "kind": x["kind"],
                           "chars": len(x["text"])} for x in d["docs"]]}
    wjson(work / "figure_plan.json", plan)
    print("init: case=%s documents=%d" % (plan["case_id"], len(plan["documents"])))
    for doc in plan["documents"]:
        print("  %s %s kind=%s chars=%d" % (doc["id"], doc["name"], doc["kind"], doc["chars"]))
    return 0


def cmd_check(inp, out, work):
    work.mkdir(parents=True, exist_ok=True)
    d = discover(inp, work)
    exc = []
    m = build_model(d, exc)
    rep = {"case_id": d["case"].get("case_id") or d["case"].get("id") or inp.name,
           "parts": [{"id": p["id"], "name": p["name"], "qty": p["qty"],
                      "verified": p["source_verified"]} for p in m["parts"]],
           "connections": [{"id": c["id"], "from": c["from"], "to": c["to"],
                            "drawable": bool(c.get("drawable"))} for c in m["conns"]],
           "steps": [{"no": s["no"], "title": s["title"]} for s in m["steps"]],
           "exceptions": exc,
           "ok": bool(m["parts"] or m["steps"]) and not any(e["severity"] == "blocking"
                                                            for e in exc)}
    wjson(work / "check.json", rep)
    print("check: ok=%s parts=%d connections=%d steps=%d"
          % (rep["ok"], len(m["parts"]), len(m["conns"]), len(m["steps"])))
    return 0


def cmd_show(out):
    res = read_json(Path(out) / "result.json")
    if isinstance(res, dict):
        cm = res.get("content_map") or {}
        print("result: status=%s case=%s parts=%d connections=%d steps=%d"
              % (res.get("status"), res.get("case_id"), len(cm.get("parts") or []),
                 len(cm.get("connections") or []), len(cm.get("steps") or [])))
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
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Apparatus / technical-route material -> editable "
                                             "layered SVG + vector PDF + PNG -> result.json.")
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "init", "show", "check", "build", "selfcheck"],
                    help="run (default) = the full single-command pipeline")
    ap.add_argument("--input", help="input directory (default /input)")
    ap.add_argument("--output", help="output directory (default /app/output)")
    ap.add_argument("--work", help="scratch directory (default /app/work)")
    ap.add_argument("--style", help="reserved; ignored by this figure type")
    ap.add_argument("--version", action="store_true", help="print the version")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if a.version:
        print("apparatus-and-route-sheet %s (stdlib only)" % VERSION)
        return 0
    inp, out, work = resolve_paths(a)
    try:
        out.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        if a.cmd == "init":
            return cmd_init(inp, out, work)
        if a.cmd == "check":
            return cmd_check(inp, out, work)
        if a.cmd == "show":
            return cmd_show(out)
        if a.cmd == "selfcheck":
            return cmd_selfcheck(work)
        S = pipeline(inp, out, work)
        if os.environ.get("WEEKLY_SKIP_PROBE") != "1":
            self_check(work)
        print("built figure.svg figure.pdf figure.png | status=%s parts=%s steps=%s"
              % (S.get("status"), len((S.get("content_map") or {}).get("parts") or []),
                 len((S.get("content_map") or {}).get("steps") or [])))
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
            S["errors"] = list(S.get("errors") or []) + ["unhandled:" + traceback.format_exc()[-400:]]
            S["exceptions"] = list(S.get("exceptions") or []) + [{
                "code": "unhandled_exception", "message": "the pipeline crashed; see errors",
                "severity": "blocking", "action": "no figure drawn"}]
            S["pending_human"] = list(S.get("pending_human") or []) + ["inspect result.errors"]
            S["limits"] = S.get("limits") or ["this run produced no figure"]
            S["uncertainties"] = S.get("uncertainties") or [{"item": "run", "note": "aborted"}]
            S["change_records"] = S.get("change_records") or [{"step": "abort",
                                                               "detail": "unhandled exception"}]
            S["sources"] = S.get("sources") or [{"id": "S0", "path": "not present"}]
            for k in ("content_map", "compliance_checks", "editable_source", "export_artifact"):
                if not S.get(k):
                    S[k] = {"status": "aborted"}
            S["coverage"] = S.get("coverage") or {"parts": 0, "connections": 0, "steps": 0}
            finalize(S, out, time.time(), sys.argv[1:])
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
