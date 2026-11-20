#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py -- one command turns materials into an editable, verifiable mindmap package.

    python3 /skills/weekly-skill/scripts/main.py run   --input /input --output /app/output --work /app/work
    python3 /skills/weekly-skill/scripts/main.py init  ...   # index, work skeleton, partial result.json
    python3 /skills/weekly-skill/scripts/main.py show  --material M1 --limit 20
    python3 /skills/weekly-skill/scripts/main.py check ...    # structural audit (errors/warns)
    python3 /skills/weekly-skill/scripts/main.py build ...    # render SVG/PNG + finalise result.json

Agent-first: init writes /app/work/mindmap.json; the Agent edits that draft (theme, nodes with
verbatim quotes, edges); build renders the Agent model, or falls back to deterministic extraction
when no usable draft exists. Exit code is always 0 and a legal result.json is always left behind.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import verify as V  # noqa: E402
from render import (SKILL_NAME, content_map, coverage_md, diff_report, evidence_rows, facts_ledger,
                    golden, layout, png_clean, render_svg, self_check, structure_summary,
                    version_md)  # noqa: E402

T0 = time.time()
DEFAULT_CONTRACT = {"deliverable": "可编辑导图（SVG + JSON）",
                    "evidence_map": "节点→来源 locator 与逐字引文",
                    "preserved_facts": "事实与数字台账",
                    "change_log": "修改记录",
                    "content_map": "来源映射"}
ARTIFACTS = ["mindmap.svg", "mindmap.json", "content_map.json", "mindmap.png", "structure.md",
             "golden_standard.json", "diff_report.md", "version_history.md", "run.log",
             "self_check.json", "result.json"]


# --------------------------------------------------------------------- plumbing
def ensure(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def wtext(path, text, binary=False):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            p.write_bytes(text)
        else:
            p.write_bytes(V.scrub(text).encode("utf-8"))
        return True
    except OSError:
        return False


def log(work, msg):
    line = "%-19s %+6.2fs %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), time.time() - T0, msg)
    try:
        ensure(work)
        with (Path(work) / "run.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    return line


def load_case(input_dir):
    for name in ("case.json", "challenge.json"):
        obj = V.loadj(Path(input_dir) / name)
        if isinstance(obj, dict):
            return obj, str(Path(input_dir) / name)
    return {}, ""


def case_id_of(case, input_dir):
    for key in ("case_id", "id", "challenge_id"):
        val = str(case.get(key) or "").strip()
        if val:
            return val
    return Path(input_dir).resolve().name or "case"


def contract_of(case):
    for key in ("output_contract", "contract", "output_schema"):
        val = case.get(key)
        if isinstance(val, dict) and val:
            return val
    return dict(DEFAULT_CONTRACT)


def analyze(input_dir, work):
    case, cpath = load_case(input_dir)
    disc = V.discover(input_dir, case)
    materials = disc["materials"]
    draft = None
    for name in ("mindmap.json", "draft.json"):
        obj = V.loadj(Path(work) / name)
        if isinstance(obj, dict) and (obj.get("nodes") or obj.get("theme")):
            draft = obj
            break
    if draft is not None:
        model = V.normalize_model(draft, materials)
        if not model["nodes"]:
            draft, model = None, None
    if draft is None:
        model = V.normalize_model(V.fallback_model(materials), materials)
        model["source"] = "deterministic_extraction"
        if materials:
            disc["degraded"].append("work draft missing or empty: deterministic extraction used")
    validation = V.validate(model)
    lay = layout(model) if model["nodes"] else {"pos": {}, "width": 1000, "height": 200,
                                                  "box_h": 34, "col_w": 200, "margin": 40}
    return {"case": case, "case_path": cpath, "case_id": case_id_of(case, input_dir),
            "materials": materials, "model": model, "validation": validation, "layout": lay,
            "degraded": disc["degraded"], "notes": disc["notes"]}


def status_of(a):
    model, val = a["model"], a["validation"]
    if not a["materials"] or not any(m["text_available"] for m in a["materials"]):
        return "insufficient_evidence"
    if not model["nodes"]:
        return "insufficient_evidence"
    ev = [e for n in model["nodes"] for e in n["evidence"]]
    if val["ok"] and ev and all(e["verified"] for e in ev) and 3 <= len(model["nodes"]) <= 60:
        return "ok"
    return "partial"


# --------------------------------------------------------------------- probes
def probe(name, files, timeout=90):
    root = Path(tempfile.mkdtemp(prefix="mm-%s-" % name))
    rec = {"name": name, "exit_code": None, "result_valid": False, "files": 0, "status": ""}
    try:
        inp, work, out = root / "input", root / "work", root / "output"
        for d in (inp, work, out):
            ensure(d)
        for rel, content in (files or {}).items():
            p = inp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        env = dict(os.environ, PYTHONUTF8="1", BOHR_PROBE="1")
        cp = subprocess.run([sys.executable, "-B", str(HERE / "main.py"), "build",
                             "--input", str(inp), "--output", str(out), "--work", str(work)],
                            cwd=str(root), env=env, capture_output=True, timeout=timeout)
        rec["exit_code"] = cp.returncode
        res = V.loadj(out / "result.json")
        rec["result_valid"] = isinstance(res, dict)
        rec["status"] = (res or {}).get("status") or ""
        rec["files"] = len([p for p in out.rglob("*") if p.is_file()])
        rec["pass"] = bool(cp.returncode == 0 and rec["result_valid"] and rec["files"] >= 5)
    except Exception as exc:
        rec["error"] = str(exc)[:160]
        rec["pass"] = False
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return rec


# --------------------------------------------------------------------- pipeline
def run_pipeline(args):
    inp, out, work = Path(args.input), Path(args.output), Path(args.work)
    ensure(out)
    ensure(work)
    if args.cmd == "show":
        a = analyze(str(inp), str(work))
        mid = args.material or (a["materials"][0]["id"] if a["materials"] else "")
        mat = next((m for m in a["materials"] if m["id"] == mid), None)
        if mat is None:
            print("== show | material %s not found (materials: %s)"
                  % (mid or "-", ", ".join(m["id"] for m in a["materials"]) or "（无）"))
            return _finalize(a, args, "partial", ["show 请求的材料不存在"])
        start = max(1, int(args.start))
        limit = max(1, int(args.limit))
        print("== show | %s (%s) units %d-%d" % (mat["id"], mat["name"], start, start + limit - 1))
        for u in mat["units"][start - 1:start - 1 + limit]:
            print("  [%s] %s" % (u["locator"], u["text"][:160]))
        return _finalize(a, args, status_of(a), [])
    a = analyze(str(inp), str(work))
    contract = contract_of(a["case"])
    a["contract"] = contract
    a["model"]["case_id"] = a["case_id"]
    log(work, "stage=%s case=%s materials=%d nodes=%d edges=%d"
        % (args.cmd, a["case_id"], len(a["materials"]), len(a["model"]["nodes"]),
           len(a["model"]["edges"])))
    if args.cmd == "init":
        log(work, "init wrote work draft /app/work/mindmap.json")
    return _finalize(a, args, status_of(a), [])


def _finalize(a, args, status, extra_limits):
    inp, out, work = Path(args.input), Path(args.output), Path(args.work)
    model, val = a["model"], a["validation"]
    cmap = content_map(a["materials"], model)
    contract = a.get("contract") or contract_of(a["case"])
    # ---- work draft skeleton so the Agent can edit before build
    try:
        draft_path = work / "mindmap.json"
        if not draft_path.is_file():
            V.dumpj(draft_path, {"theme": model["theme"], "nodes": model["nodes"],
                                 "edges": model["edges"], "hint": "编辑本文件后重跑 build"})
        V.dumpj(work / "index.json", {"case_id": a["case_id"], "materials": V.index_view(a["materials"]),
                                      "contract_keys": list(contract.keys())})
        V.dumpj(work / "check.json", {"stage": args.cmd, "errors": val["errors"], "warns": val["warns"]})
    except OSError:
        pass
    # ---- artifacts
    wtext(out / "mindmap.svg", render_svg(model, a["layout"]) if model["nodes"] else
          "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1000\" height=\"120\"><text x=\"20\" y=\"60\">"
          "没有可建图的材料内容</text></svg>\n")
    V.dumpj(out / "mindmap.json", {"case_id": a["case_id"], "theme": model["theme"],
                                   "nodes": model["nodes"], "edges": model["edges"],
                                   "source": model["source"], "dropped": model["dropped"],
                                   "edge_drop": model["edge_drop"]})
    V.dumpj(out / "content_map.json", cmap)
    png, knob, png_note = png_clean(model, a["layout"])
    ok_png = wtext(out / "mindmap.png", png, binary=True)
    if png_note or not ok_png:
        a["degraded"].append(png_note or "png preview could not be written")
    wtext(out / "structure.md", coverage_md(model, cmap, val))
    gdoc = golden(model, val, contract, cmap, args.cmd)
    V.dumpj(out / "golden_standard.json", gdoc)
    dtext, counts, _items = diff_report(model, val, cmap, gdoc, contract, args.cmd)
    wtext(out / "diff_report.md", dtext)
    entry = {"version": "v0" if args.cmd == "init" else "v1", "stage": args.cmd,
             "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "nodes": len(model["nodes"]),
             "edges": len(model["edges"]), "depth": val["depth"],
             "change": "节点 %d 个，模型来源 %s" % (len(model["nodes"]), model["source"])}
    wtext(out / "version_history.md", version_md(work, [entry], args.cmd))
    probes = []
    if not args.no_probe and args.cmd != "show" and os.environ.get("BOHR_PROBE") != "1":
        probes.append(probe("empty_input", {}))
        probes.append(probe("bad_json", {"case.json": "{ not valid json", "broken.json": "[1, 2,",
                                         "paper.md": "# 方法\n\n样本 30 份，温度 80 摄氏度。\n"}))
    sc = self_check(model, val, contract, cmap, probes, args.cmd)
    V.dumpj(out / "self_check.json", sc)
    try:
        src = work / "run.log"
        if src.is_file():
            shutil.copy2(src, out / "run.log")
    except OSError:
        wtext(out / "run.log", "run log unavailable\n")
    # ---- result.json
    sizes = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size}
             for p in sorted(out.rglob("*")) if p.is_file()]
    wrap = sorted(n["id"] for n in model["nodes"] if not all(e["verified"] for e in n["evidence"]))
    uncertainty = wrap + cmap["coverage"]["unmapped"][:6]
    if not uncertainty:
        uncertainty = (["本次没有产出可核验节点：材料文本不可用或结构为空，证据覆盖为空，缺口见 degradations。"]
                       if not model["nodes"] else
                       ["证据侧无未命中项：全部节点 quote 均逐字命中材料，未覆盖单元为 0。"])
    pending = ["未逐字命中的节点：%s" % "、".join(wrap)] if wrap else []
    pending += ["未引用单元：%s" % "、".join(cmap["coverage"]["unmapped"][:6])] \
        if cmap["coverage"]["unmapped"] else []
    limits = list(extra_limits) + list(a["degraded"]) + [
        "PNG 预览由标准库绘制几何形状，标签文字在 SVG/JSON 中；如需带字预览请用 rsvg-convert/inkscape。",
        "节点匹配为确定性规则：等价改写的人工版本可能被判未命中，逐条证据已列出命中情况。"]
    changes = [{"action": args.cmd, "detail": "节点 %d 个，关系 %d 条，模型来源 %s"
                % (len(model["nodes"]), len(model["edges"]), model["source"])}]
    ctx = {"case_id": a["case_id"], "files": [x["path"] for x in sizes][:12],
           "note": "导图包已生成：" + "、".join(ARTIFACTS[:4]),
           "deliverable": {"summary": "%d 节点 / %d 关系 / 深度 %d / 模型来源 %s"
                                      % (len(model["nodes"]), len(model["edges"]), val["depth"],
                                         model["source"]),
                           "primary": "mindmap.svg", "structure": "mindmap.json",
                           "content_map": "content_map.json", "preview": "mindmap.png",
                           "editable": True, "nodes": len(model["nodes"])},
           "evidence_map": evidence_rows(model), "preserved_facts": facts_ledger(model),
           "change_log": changes, "content_map": cmap,
           "mindmap": structure_summary(model, val),
           "edges": [{"from": e["from"], "to": e["to"], "type": e["type"],
                      "locator": (e["evidence"][0]["locator"] if e["evidence"] else "")}
                     for e in model["edges"]]}
    res = {"case_id": a["case_id"], "status": status,
           "summary": "%d 节点 / %d 关系 / 状态 %s / 模型来源 %s"
                      % (len(model["nodes"]), len(model["edges"]), status, model["source"]),
           "sources": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "path": m["path"],
                        "bytes": m["bytes"], "sha1": m["sha1"], "units": len(m["units"]),
                        "text_available": m["text_available"]} for m in a["materials"]],
           "uncertainty": uncertainty, "uncertainties": uncertainty,
           "pending_human": pending, "errors": a["notes"], "degradations": a["degraded"],
           "limits": limits, "changes": changes, "change_records": changes,
           "runtime": {"skill": SKILL_NAME + "/" + V.VERSION, "python": sys.version.split()[0],
                       "seconds": round(time.time() - T0, 2)},
           "artifacts": sizes, "coverage": {"materials": len(a["materials"]),
                                            "units": cmap["coverage"]["units"],
                                            "mapped": cmap["coverage"]["mapped"],
                                            "nodes": len(model["nodes"]),
                                            "edges": len(model["edges"]),
                                            "verified_evidence": sum(1 for n in model["nodes"]
                                                                     for e in n["evidence"] if e["verified"])},
           "structure": {"theme": model["theme"]["label"], "depth": val["depth"],
                         "branches": val["branches"]},
           "checks": [{"id": c["id"], "status": "PASS" if c["pass"] else "FAIL",
                       "detail": c["observed"]} for c in sc["checks"]],
           "diff_report": {"path": "diff_report.md", "verdict_counts": counts},
           "golden_standard": {"path": "golden_standard.json", "requirements": len(gdoc["structural_requirements"])},
           "version_history": {"path": "version_history.md", "versions": 2},
           "self_check": {"path": "self_check.json", "pass": sc["summary"]["pass"],
                          "checks": sc["summary"]["checks"], "failed": sc["summary"]["failed"]}}
    V.finalize(res, contract, ctx, out / "result.json")
    log(work, "done status=%s nodes=%d out_files=%d" % (status, len(model["nodes"]), len(sizes)))
    print("== %s | status=%s | nodes=%d | edges=%d | depth=%d | self_check=%s"
          % (args.cmd, status, len(model["nodes"]), len(model["edges"]), val["depth"],
             "pass" if sc["summary"]["pass"] else "review"))
    for b in [n for n in model["nodes"] if n["level"] == 1]:
        print("   %s %-10s children=%d" % (b["id"], b["role"], len(b["children"])))
    if val["errors"]:
        print("   errors=%d: %s" % (len(val["errors"]), val["errors"][0]["code"]))
    print("== output %s" % out)
    return 0


def audit(out_dir):
    out = Path(out_dir)
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()) if out.is_dir() else []
    res = V.loadj(out / "result.json", {}) or {}
    checks = []

    def chk(cid, ok, detail):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})

    chk("result_json", bool(res), "result.json parsed" if res else "result.json missing or invalid")
    echo = res.get("output_contract") if isinstance(res, dict) else None
    chk("contract_echo", isinstance(echo, dict) and bool(echo), "%d contract keys echoed" % len(echo or {}))
    chk("case_id", bool(res.get("case_id")), "case_id=%r" % (res.get("case_id"),))
    chk("deliverables", len(files) >= 5, "%d output files" % len(files))
    flagged = []
    for rel in files:
        if Path(rel).suffix.lower() in (".md", ".json", ".csv", ".svg", ".png", ".txt"):
            hits = V.PLACEHOLDER_RE.findall(V.read_text(out / rel))
            if hits:
                flagged.append(rel)
    chk("placeholder_sweep", not flagged, "flagged files: %s" % (flagged[:5] or "no placeholder token"))
    ok = all(c["status"] == "PASS" for c in checks)
    print(json.dumps({"status": "PASS" if ok else "FAIL", "checks": checks}, ensure_ascii=False, indent=2))
    return 0


def crash_safe(args, exc):
    try:
        out, work = Path(args.output), Path(args.work)
        ensure(out)
        ensure(work)
        case, _ = load_case(args.input)
        cid = case_id_of(case, args.input)
        changes = [{"action": "crash", "detail": str(exc)[:160]}]
        ctx = {"case_id": cid, "files": [], "note": "运行时异常，已写最小合法 result.json",
               "deliverable": {"summary": "已落盘最小结果", "artifacts": []},
               "evidence_map": [], "preserved_facts": [], "change_log": changes, "content_map": {}}
        res = {"case_id": cid, "status": "input_error", "summary": "运行时异常，已最小落盘",
               "sources": [], "uncertainty": [str(exc)[:160]], "uncertainties": [str(exc)[:160]],
               "pending_human": [], "errors": [str(exc)[:200]],
               "degradations": ["已写最小 result.json，退出码仍为 0"], "limits": ["主流程异常，结果不完整"],
               "changes": changes, "change_records": changes,
               "runtime": {"skill": SKILL_NAME + "/" + V.VERSION, "seconds": round(time.time() - T0, 2)},
               "artifacts": [], "checks": []}
        V.finalize(res, contract_of(case), ctx, out / "result.json")
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Material-to-mindmap builder: editable SVG/JSON map, "
                                             "source map, five verifiable assets, result.json.")
    ap.add_argument("cmd", nargs="?", default="run", choices=["init", "show", "check", "build", "run"],
                    help="pipeline stage (default: run)")
    ap.add_argument("--input", default=os.environ.get("BOHR_INPUT_DIR") or "/input", help="input directory")
    ap.add_argument("--output", default=os.environ.get("BOHR_OUTPUT_DIR") or "/app/output", help="output directory")
    ap.add_argument("--work", default=os.environ.get("BOHR_WORK_DIR") or "/app/work", help="working directory")
    ap.add_argument("--material", default="", help="material id for show (e.g. M1)")
    ap.add_argument("--start", type=int, default=1, help="first unit index for show")
    ap.add_argument("--limit", type=int, default=20, help="number of units for show")
    ap.add_argument("--no-probe", dest="no_probe", action="store_true",
                    help="skip the empty-input and bad-json subprocess probes")
    ap.add_argument("--audit", metavar="OUT", help="audit a produced output directory")
    args = ap.parse_args(argv)
    if args.audit:
        return audit(args.audit)
    return run_pipeline(args)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        main(sys.argv[1:])
    except SystemExit:
        pass
    except Exception as exc:  # pragma: no cover
        print("main.py internal exception (exit code stays 0): %s" % exc)
        class _A:
            input = "/input"
            output = "/app/output"
            work = "/app/work"
        crash_safe(_A(), exc)
    sys.exit(0)
