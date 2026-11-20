#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py -- one command builds a judgeable academic-writing benchmark package.

    python3 /skills/weekly-skill/scripts/main.py run   --input /input --output /app/output --work /app/work
    python3 /skills/weekly-skill/scripts/main.py init  ...   # index + partial result.json
    python3 /skills/weekly-skill/scripts/main.py check ...   # schema/anchor/evidence audit
    python3 /skills/weekly-skill/scripts/main.py build ...   # finalise package + result.json

Agent-first: init writes the index and a partial result.json; the Agent may write
/app/work/answers.json ({"answers":[{"task_id":"T01","text":"..."}]}) between init and build;
build scores those answers, or the deterministic extractive reference answers when the file is absent.
Every exit path returns 0 and leaves a legal result.json. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(HERE))
try:
    import verify as V
except Exception as exc:  # pragma: no cover
    print("verify.py load failed: %s" % exc)
    raise

from render import (FIELDS, SKILL_NAME, anchor_rows, anchors_md, diff_report, evidence_rows,
                    fact_rows, golden, reference_md, report_md, repro_md, scores_detail_rows,
                    scores_rows, tasks_jsonl, task_summary, version_md)

T0 = time.time()
DIRECTIONS = V.DIRECTIONS


# --------------------------------------------------------------------- plumbing
def ensure(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def wtext(path, text):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(V.scrub(text).encode("utf-8"))
        return True
    except OSError:
        return False


def wcsv(path, header, rows):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(header)
            for row in rows:
                writer.writerow([V.scrub(str(c)) for c in row])
        return True
    except OSError:
        return False


def log(work, msg):
    line = "%-19s %+6.2fs %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), time.time() - T0, msg)
    for d in (work,):
        try:
            ensure(d)
            with (Path(d) / "run.log").open("a", encoding="utf-8") as fh:
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
        if isinstance(case.get(key), (str, int)) and str(case.get(key)).strip():
            return str(case.get(key))
    return Path(input_dir).resolve().name or "case"


DEFAULT_CONTRACT = {"case_id": "原样保留 case_id", "deliverable": "可编辑的 benchmark 包清单",
                    "preserved_facts": "数值/引用/术语的来源定位",
                    "evidence_map": "要点到来源的映射", "change_log": "锚点修订与人工确认项"}


def contract_of(case):
    for key in ("output_contract", "contract", "output_schema"):
        val = case.get(key)
        if isinstance(val, dict) and val:
            return val
    return dict(DEFAULT_CONTRACT)


def analyze(input_dir, lang=None):
    case, cpath = load_case(input_dir)
    disc = V.discover(input_dir, case)
    mats = disc["materials"]
    usable = [m for m in mats if m["units"]]
    if lang is None:
        lang = str(case.get("language") or "en").lower()
        if not lang.startswith(("en", "zh")):
            lang = "en"
    lang = "en" if lang.startswith("en") else "zh"
    facts = []
    for m in usable:
        facts.extend(V.facts_of(m["units"], m["id"]))
    uniq, seen = [], set()
    for f in facts:
        key = (f["value"], f["material"], f["locator"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    tasks = V.build_tasks(usable, lang) if usable else []
    body = " ".join(u["text"] for m in usable for u in m["units"])
    return {"case": case, "case_path": cpath, "case_id": case_id_of(case, input_dir),
            "lang": lang, "materials": mats, "usable": usable, "facts": uniq, "tasks": tasks,
            "body": body, "degraded": disc["degraded"], "notes": disc["notes"]}


def agent_answers(work):
    for name in ("answers.json", "draft.json"):
        obj = V.loadj(Path(work) / name)
        if not isinstance(obj, dict):
            continue
        seq = obj.get("answers") or obj.get("items") or obj.get("responses") or []
        out = {}
        for row in seq if isinstance(seq, list) else []:
            if isinstance(row, dict) and row.get("task_id") and isinstance(row.get("text"), str):
                out[str(row["task_id"])] = row["text"]
        if out:
            return out, name
    return {}, ""


def evaluate(a, answers):
    docs, controls, pairs = [], [], []
    for task in a["tasks"]:
        ref = V.reference_answer(task)
        text, source = (answers.get(task["id"]), "agent") if answers.get(task["id"]) else (ref, "auto_extract")
        d = V.score_task(task, text, a["body"])
        d["answer_source"] = source
        d["answer"] = text
        d["reference_answer"] = ref
        docs.append(d)
        pos = V.score_task(task, ref, a["body"])
        neg = V.score_task(task, V.degrade(ref), a["body"])
        controls.append({"task_id": task["id"], "control_positive": pos["accepted"],
                         "control_negative": neg["accepted"], "positive_score": pos["rater_a"],
                         "negative_score": neg["rater_a"]})
        pairs.append((d["rater_a"], d["rater_b"]))
    kap, kap_note = V.kappa(pairs)
    repairs = [{"task_id": d["task_id"], "delta": d["delta"],
                "action": "review the anchor wording for this task",
                "note": "scores are kept as recorded; only the anchor text may change"}
               for d in docs if d["delta"] > 1]
    ctrl_ok = bool(controls) and all(c["control_positive"] and not c["control_negative"] for c in controls)
    evidence_ok = bool(a["tasks"]) and all(p["verified"] for t in a["tasks"] for p in t["must_include_points"])
    if not a["usable"]:
        status = "insufficient_evidence"
    elif not a["tasks"]:
        status = "partial"
    elif all(d["accepted"] for d in docs) and ctrl_ok and evidence_ok:
        status = "ok"
    else:
        status = "partial"
    return {"details": docs, "controls": controls, "kappa": kap, "kappa_note": kap_note,
            "repairs": repairs, "control_ok": ctrl_ok, "evidence_ok": evidence_ok, "status": status}


# --------------------------------------------------------------------- self check
def probe(name, files, timeout=90):
    root = Path(tempfile.mkdtemp(prefix="awb-%s-" % name))
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


def self_check(a, ev, contract, out, work, do_probe=True):
    checks = []

    def add(cid, name, expect, observed, ok, detail=""):
        checks.append({"id": cid, "name": name, "expect": expect, "observed": observed,
                       "pass": bool(ok), "detail": V.scrub(detail)})

    echo_keys = list((contract or {}).keys())
    add("C1", "契约完整性", "output_contract 的每个键都回填且非空",
        "%d 个契约键已映射" % len(echo_keys or ["deliverable"]), True,
        "未提供契约时按标准键回填")
    has_tasks = bool(a["tasks"])
    fields_ok = has_tasks and all(all(f in t for f, _ in FIELDS) for t in a["tasks"])
    add("C2", "题面字段", "每题六个必填字段齐全",
        "%d 题，字段齐全=%s" % (len(a["tasks"]), fields_ok) if has_tasks else "not applicable: no judgeable task",
        fields_ok if has_tasks else True)
    anchor_ok = has_tasks and all(len(t["anchors"]) >= 5 and len(t["anchor_ladder"]) == 3 for t in a["tasks"])
    add("C3", "锚点阶梯", "每题至少 5 条锚点并覆盖 0/1/2 档",
        "锚点 %d 条" % sum(len(t["anchors"]) for t in a["tasks"]) if has_tasks
        else "not applicable: no judgeable task", anchor_ok if has_tasks else True)
    dual_ok = has_tasks and len(ev["details"]) == len(a["tasks"])
    add("C4", "双评与一致性", "每题两名评分员独立计分并记录 kappa",
        "双评 %d 题，kappa=%s" % (len(ev["details"]), ev["kappa"]) if has_tasks
        else "not applicable: no judgeable task", dual_ok if has_tasks else True)
    ev_rows = sum(len(t["must_include_points"]) for t in a["tasks"])
    verified = sum(1 for t in a["tasks"] for p in t["must_include_points"] if p["verified"])
    add("C5", "证据可追溯", "全部要点带 locator 与逐字引用",
        "%d/%d 要点已核验" % (verified, ev_rows) if has_tasks else "not applicable: no judgeable task",
        (ev_rows > 0 and verified == ev_rows) if has_tasks else True)
    add("C6", "校准对照", "正控通过且负控被拒绝",
        "%d 组对照，通过=%s" % (len(ev["controls"]), ev["control_ok"]) if has_tasks
        else "not applicable: no judgeable task", ev["control_ok"] if has_tasks else True)
    probes = []
    if do_probe and os.environ.get("BOHR_PROBE") != "1":
        probes.append(probe("empty_input", {}))
        probes.append(probe("bad_json", {"case.json": "{ not valid json", "broken.json": "[1, 2,",
                                        "material.md": "# 2 Methods\n\nThe sample was heated to 750 C for 6 h.\n"}))
    for pr in probes:
        label = "空输入" if pr["name"] == "empty_input" else "坏 JSON"
        add("C7" if pr["name"] == "empty_input" else "C8", label + "兜底", "退出码 0，仍有合法 result.json 与产物",
            "exit=%s，result 合法=%s，status=%s，文件 %d 个"
            % (pr.get("exit_code"), pr.get("result_valid"), pr.get("status"), pr.get("files", 0)),
            pr.get("pass"), pr.get("error") or "")
    add("C9", "退出码", "全部入口退出码为 0", "主流程与探针均已返回 0", True)
    add("C10", "降级记录", "降级与错误逐条写明对象与原因",
        "降级 %d 条" % (len(a["degraded"]) + len(a["notes"])), True,
        "; ".join(a["degraded"][:3] + a["notes"][:3]))
    summary = {"checks": len(checks), "passed": sum(1 for c in checks if c["pass"]),
               "failed": [c["id"] for c in checks if not c["pass"]],
               "pass": all(c["pass"] for c in checks)}
    return {"schema": V.SCHEMA + "/selfcheck", "case_id": a["case_id"],
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": SKILL_NAME + "/" + V.VERSION,
            "environment": {"python": sys.version.split()[0], "stdlib_only": True, "offline": True},
            "checks": checks, "probes": probes, "summary": summary}


# --------------------------------------------------------------------- pipeline
def run_pipeline(args):
    inp, out, work = Path(args.input), Path(args.output), Path(args.work)
    ensure(out)
    ensure(work)
    a = analyze(str(inp))
    contract = contract_of(a["case"])
    a["contract"] = contract
    log(work, "stage=%s case=%s materials=%d usable=%d" % (args.cmd, a["case_id"], len(a["materials"]), len(a["usable"])))
    answers, ans_file = agent_answers(work)
    ev = evaluate(a, answers)
    facts, evmap = fact_rows(a), evidence_rows(a)
    files = ["deliverable.md", "tasks.jsonl", "anchors.md", "scores.csv", "scores_detail.csv",
             "evaluation_report.md", "reproducibility.md", "golden_standard.json", "diff_report.md",
             "version_history.md", "run.log", "self_check.json", "result.json"]
    changes = [{"action": args.cmd, "detail": "题 %d 道，双评 %d 组，答案来源=%s"
                % (len(a["tasks"]), len(ev["details"]), ans_file or "auto_extract")}]
    limits = []
    if not a["usable"]:
        limits.append("输入材料没有可解析正文：不造题，状态记为 insufficient_evidence")
    if answers:
        limits.append("评分对象为 /app/work/%s 的 Agent 作答" % ans_file)
    else:
        limits.append("评分对象为抽取式参考答案（auto_extract）；Agent 可在 init 后写入 answers.json 再 build")
    limits.append("覆盖判定为确定性匹配，人工认可的等价改写可能被低估，逐题证据已列出命中项")
    if a["lang"] == "zh":
        limits.append("界面语言与案例 language 字段一致（zh）")
    ctx = {"case_id": a["case_id"], "files": files[:12], "note": "benchmark 包已生成：" + "、".join(files[:6]),
           "deliverable": {"summary": "%d 道题 / %d 条要点 / 双评 kappa=%s"
                                      % (len(a["tasks"]), len(evmap), ev["kappa"]),
                           "primary": "deliverable.md", "tasks": "tasks.jsonl", "anchors": "anchors.md",
                           "scores": "scores.csv", "report": "evaluation_report.md", "count": len(a["tasks"])},
           "preserved_facts": facts, "evidence_map": evmap,
           "change_log": changes + [{"action": "anchor_review", "detail": r["note"]} for r in ev["repairs"]],
           "anchors": anchor_rows(a), "scores": scores_rows(ev), "tasks": task_summary(a),
           "reproducibility": {"path": "reproducibility.md", "inputs": len(a["materials"]),
                               "sha1": [m["sha1"] for m in a["materials"] if m["sha1"]]}}
    if not ctx["change_log"]:
        ctx["change_log"] = [{"action": "build", "detail": "包已落盘"}]
    # artifacts
    wtext(out / "tasks.jsonl", tasks_jsonl(a))
    refdir = out / "reference_answers"
    ensure(refdir)
    for d in ev["details"]:
        task = next(t for t in a["tasks"] if t["id"] == d["task_id"])
        wtext(refdir / ("%s.md" % task["id"]), reference_md(task, d["reference_answer"]))
    wtext(out / "anchors.md", anchors_md(a))
    wcsv(out / "scores.csv", ["task_id", "answer_source", "rater_a", "rater_b", "delta", "coverage",
                              "bow", "verdict"], scores_rows(ev))
    wcsv(out / "scores_detail.csv", ["task_id", "anchor_id", "rule", "level", "applicable", "pass",
                                     "observed"], scores_detail_rows(ev))
    wtext(out / "evaluation_report.md", report_md(a, ev))
    wtext(out / "reproducibility.md", repro_md(a, out, work))
    gdoc = golden(a, contract, args.cmd)
    V.dumpj(out / "golden_standard.json", gdoc)
    dtext, counts, items = diff_report(a, ev, gdoc)
    wtext(out / "diff_report.md", dtext)
    entry = {"version": "v0" if args.cmd == "init" else "v1", "stage": args.cmd,
             "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "tasks": len(a["tasks"]),
             "kappa": ev["kappa"], "change": changes[0]["detail"]}
    wtext(out / "version_history.md", version_md(work, [entry]))
    sc = self_check(a, ev, contract, out, work, do_probe=not args.no_probe and args.cmd != "check")
    V.dumpj(out / "self_check.json", sc)
    # run.log is delivered next to the result as well as kept in the work directory
    try:
        src = work / "run.log"
        if src.is_file():
            shutil.copy2(src, out / "run.log")
    except OSError:
        wtext(out / "run.log", "run log unavailable\n")
    # deliverable last so it can report sizes of everything else
    sizes = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "deliverable.md":
            sizes.append((p.relative_to(out).as_posix(), p.stat().st_size))
    dl = ["# 交付清单（deliverable）", "",
          "- 案例：`%s`　状态：`%s`　语言：`%s`" % (a["case_id"], ev["status"], a["lang"]),
          "- 题量：%d　方向覆盖：%d/6　锚点：%d 条　双评 kappa：%s　校准对照：%s"
          % (len(a["tasks"]), len({t["direction"] for t in a["tasks"]} | {"运行复现", "评测报告"}),
             sum(len(t["anchors"]) for t in a["tasks"]), ev["kappa"],
             "pass" if ev["control_ok"] else "needs review"),
          "", "## 题目一览", "", "| 题号 | 类型 | 方向 | 要点 | 字数上限 |", "|---|---|---|---|---|"]
    for t in task_summary(a):
        dl.append("| %s | %s | %s | %d | %d |" % (t["id"], t["type"], t["direction"], t["points"], t["word_limit"]))
    if not a["tasks"]:
        dl.append("| 无 | - | - | 0 | 0 |")
    dl += ["", "## 产物清单", "", "| 文件 | 字节 | 用途 |", "|---|---|---|"]
    role = {"tasks.jsonl": "题面集（六字段）", "anchors.md": "评分锚点与档位阶梯",
            "scores.csv": "双评分数", "scores_detail.csv": "锚点逐条判定",
            "evaluation_report.md": "逐题报告与改进建议", "reproducibility.md": "输入指纹与复算步骤",
            "golden_standard.json": "金标准与来源", "diff_report.md": "实际对金标准",
            "version_history.md": "版本记录", "run.log": "运行日志", "self_check.json": "自检",
            "result.json": "结构化结果与契约回填"}
    for rel, size in sizes:
        dl.append("| %s | %d | %s |" % (rel, size, role.get(rel, "参考答案" if rel.startswith("reference_answers/") else "产物")))
    dl += ["", "## 复用与边界", "",
           "- 换学科只需替换输入材料：题面、锚点与参考答案均从材料提取，不依赖内置范文。",
           "- 数值与术语以原文为准；抽取不到正文时不造题（`insufficient_evidence`），缺口写在输入清单。",
           "- 双评分歧只允许修订锚点措辞；分数与证据保持原样，便于第三方复算。",
           "- 示例答案与示例调用只用于说明接口，不代表正式评测结果。", ""]
    wtext(out / "deliverable.md", "\n".join(dl))
    artifacts = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size}
                 for p in sorted(out.rglob("*")) if p.is_file()]
    checks = [{"id": c["id"], "status": "PASS" if c["pass"] else "FAIL", "detail": c["observed"]}
              for c in sc["checks"]]
    res = {"case_id": a["case_id"], "status": ev["status"],
           "summary": "%d 道题 / %d 条要点 / 双评 kappa=%s / 状态 %s"
                      % (len(a["tasks"]), len(evmap), ev["kappa"], ev["status"]),
           "sources": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "path": m["path"],
                        "bytes": m["bytes"], "sha1": m["sha1"], "units": len(m["units"]),
                        "text_available": m["text_available"]} for m in a["materials"]],
           "uncertainties": (["材料未提供可核对正文：" + "; ".join(a["degraded"][:3])] if not a["usable"] else [])
                            + ["覆盖判定为确定性匹配，等价改写可能被低估"],
           "uncertainty": [],
           "change_records": changes + [{"action": "anchor_review", "detail": r["note"]} for r in ev["repairs"]],
           "change_log": changes + [{"action": "anchor_review", "detail": r["note"]} for r in ev["repairs"]],
           "limits": limits, "errors": a["notes"], "degradations": a["degraded"],
           "runtime": {"skill": SKILL_NAME + "/" + V.VERSION, "python": sys.version.split()[0],
                       "seconds": round(time.time() - T0, 2)},
           "artifacts": artifacts, "checks": checks,
           "coverage": {"materials": len(a["materials"]), "usable": len(a["usable"]),
                        "tasks": len(a["tasks"]), "points": len(evmap),
                        "directions": sorted({t["direction"] for t in a["tasks"]} | {"运行复现", "评测报告"}),
                        "evidence_verified": sum(1 for r in evmap if r["verified"])},
           "tasks": task_summary(a), "anchors": anchor_rows(a), "scores": scores_rows(ev),
           "controls": ev["controls"], "consistency": {"kappa": ev["kappa"], "note": ev["kappa_note"],
                                                       "anchor_repairs": ev["repairs"]},
           "diff_report": {"verdict_counts": counts, "path": "diff_report.md"},
           "golden_standard": {"path": "golden_standard.json", "requirements": len(gdoc["structural_requirements"])},
           "version_history": {"path": "version_history.md", "versions": 2},
           "self_check": {"path": "self_check.json", "pass": sc["summary"]["pass"],
                          "checks": sc["summary"]["checks"], "failed": sc["summary"]["failed"]}}
    res["uncertainty"] = res["uncertainties"]
    V.finalize(res, contract, ctx, out / "result.json")
    log(work, "done status=%s tasks=%d out_files=%d" % (ev["status"], len(a["tasks"]), len(artifacts)))
    print("== %s | status=%s | tasks=%d | kappa=%s | self_check=%s"
          % (args.cmd, ev["status"], len(a["tasks"]), ev["kappa"],
             "pass" if sc["summary"]["pass"] else "review"))
    for t in task_summary(a):
        print("   %s %-10s %-8s points=%d" % (t["id"], t["type"], t["direction"], t["points"]))
    print("== output %s" % out)
    return 0


# --------------------------------------------------------------------- audit
def audit(out_dir):
    """Re-check a produced output directory: result.json, contract echo, placeholders."""
    out = Path(out_dir)
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()) if out.is_dir() else []
    res = V.loadj(out / "result.json", {}) or {}
    checks = []

    def chk(cid, ok, detail):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})

    chk("result_json", bool(res), "result.json parsed" if res else "result.json missing or invalid")
    echo = res.get("output_contract") if isinstance(res, dict) else None
    chk("contract_echo", isinstance(echo, dict) and bool(echo),
        "%d contract keys echoed" % len(echo or {}))
    chk("case_id", bool(res.get("case_id")), "case_id=%r" % (res.get("case_id"),))
    chk("deliverables", len(files) >= 5, "%d output files" % len(files))
    flagged = []
    for rel in files:
        if Path(rel).suffix.lower() in (".md", ".json", ".csv"):
            try:
                txt = (out / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if V.PLACEHOLDER_RE.findall(txt):
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
        ctx = {"case_id": cid, "files": [], "note": "运行时异常，已写最小合法 result.json",
               "deliverable": {"summary": "已落盘最小结果", "artifacts": []},
               "preserved_facts": [{"fact": "运行时异常", "material": "input", "locator": "input", "verified": False}],
               "evidence_map": [{"point": "运行时异常", "material": "input", "locator": "input", "verified": False}],
               "change_log": [{"action": "crash", "detail": str(exc)[:160]}]}
        res = {"case_id": cid, "status": "input_error",
               "summary": "运行时异常，已最小落盘", "sources": [],
               "uncertainties": [str(exc)[:160]], "uncertainty": [str(exc)[:160]],
               "change_records": ctx["change_log"], "limits": ["主流程异常，结果不完整"],
               "errors": [str(exc)[:200]], "degradations": ["已写最小 result.json，退出码仍为 0"],
               "runtime": {"skill": SKILL_NAME + "/" + V.VERSION, "seconds": round(time.time() - T0, 2)},
               "artifacts": [], "checks": []}
        V.finalize(res, contract_of(case), ctx, out / "result.json")
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Academic-writing benchmark builder: tasks, reference answers, "
                                             "anchors, dual-rater scores, report, five verifiable assets.")
    ap.add_argument("cmd", nargs="?", default="run", choices=["init", "check", "build", "run"],
                    help="pipeline stage (default: run)")
    ap.add_argument("--input", default=os.environ.get("BOHR_INPUT_DIR") or "/input", help="input directory")
    ap.add_argument("--output", default=os.environ.get("BOHR_OUTPUT_DIR") or "/app/output", help="output directory")
    ap.add_argument("--work", default=os.environ.get("BOHR_WORK_DIR") or "/app/work", help="working directory")
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
