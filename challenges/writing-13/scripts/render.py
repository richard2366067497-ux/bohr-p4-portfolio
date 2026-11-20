#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py -- artifact renderers for the academic-writing benchmark package.

Pure functions: every builder takes the analysed case and returns text; nothing here
touches the network or writes files (main.py owns I/O). Keeping rendering separate
makes each source file small enough to audit in one sitting.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import verify as V

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
SKILL_NAME = "academic-writing-benchmark-builder"

FIELDS = [
    ("input_material", "题面必须指明使用的材料"),
    ("instruction", "题面必须给出可执行指令"),
    ("word_limit", "题面必须给出字数或引用要求"),
    ("must_include_points", "题面必须列出必需要点"),
    ("acceptable_variants", "题面必须声明可接受变体"),
    ("completion_criteria", "题面必须给出完成判定"),
]


# --------------------------------------------------------------------- row views
def fact_rows(a):
    rows = []
    for f in a["facts"]:
        rows.append({"fact": f["value"], "kind": f["kind"], "sentence": f["sentence"],
                     "material": f["material"], "locator": f["locator"], "verified": f["verified"]})
    if not rows:
        rows = [{"fact": "材料未提供可核对数值", "kind": "note", "sentence": "输入材料没有可解析的正文",
                 "material": "input", "locator": "input", "verified": False}]
    return rows


def evidence_rows(a):
    rows = []
    for task in a["tasks"]:
        for p in task["must_include_points"]:
            rows.append({"task_id": task["id"], "point_id": p["id"], "point": p["text"],
                         "material": p["material"], "locator": p["locator"],
                         "quote": p["quote"], "verified": p["verified"]})
    if not rows:
        rows = [{"task_id": "T00", "point_id": "P0", "point": "输入材料未提供可引用的要点",
                 "material": "input", "locator": "input", "quote": "", "verified": False}]
    return rows


def task_summary(a):
    return [{"id": t["id"], "type": t["type"], "direction": t["direction"],
             "section": t["section"], "points": len(t["must_include_points"]),
             "word_limit": t["word_limit"]} for t in a["tasks"]]


def anchor_rows(a):
    rows = []
    for t in a["tasks"]:
        for row in t["anchors"]:
            rows.append({"task_id": t["id"], "anchor_id": row["id"], "level": row["level"],
                         "rule": row["rule"], "observable": row["observable"]})
    return rows


# --------------------------------------------------------------------- markdown
def anchors_md(a):
    lines = ["# 评分锚点（anchors）", "",
             "每条锚点都是可观察现象。0 档拒绝，1 档可接受但需注明，2 档直接接受；"
             "两名评分员独立打分，分歧只允许修订锚点措辞，不允许改分数。", ""]
    if not a["tasks"]:
        lines += ["材料未提供可建锚点的正文，锚点表随任务补齐后再生。", ""]
    for t in a["tasks"]:
        lines += ["## %s · %s · %s" % (t["id"], t["type"], t["section"]), "",
                  "| 锚点 | 档位 | 规则 | 可观察现象 |", "|---|---|---|---|"]
        for row in t["anchors"]:
            lines.append("| %s | L%d | `%s` | %s |" % (row["id"], row["level"], row["rule"], row["observable"]))
        lines += ["", "锚点阶梯：", ""]
        for step in t["anchor_ladder"]:
            lines.append("- L%d %s：%s" % (step["level"], step["label"], step["observable"]))
        lines.append("")
    return "\n".join(lines)


def tasks_jsonl(a):
    return "\n".join(json.dumps(V.clean(t), ensure_ascii=False) for t in a["tasks"]) + ("\n" if a["tasks"] else "")


def reference_md(task, answer):
    lines = ["# 参考答案 %s（抽取式，示例）" % task["id"], "",
             answer, "", "## 要点与来源定位", "",
             "| 要点 | 材料 | 定位 | 原文片段 |", "|---|---|---|---|"]
    for p in task["must_include_points"]:
        lines.append("| %s | %s | %s | %s |" % (p["id"], p["material"], p["locator"],
                                                p["quote"].replace("|", "\\|")[:120]))
    lines += ["", "说明：答案由材料原句拼成，不新增事实；改写变体只要数值与术语不变即视为可接受。", ""]
    return "\n".join(lines)


def scores_rows(ev):
    return [[d["task_id"], d["answer_source"], d["rater_a"], d["rater_b"], d["delta"],
             d["coverage"], d["bow"], "accept" if d["accepted"] else "needs_revision"] for d in ev["details"]]


def scores_detail_rows(ev):
    rows = []
    for d in ev["details"]:
        for row in d["anchors"]:
            rows.append([d["task_id"], row["anchor_id"], row["rule"], row["level"],
                         "yes" if row["applicable"] else "no", "pass" if row["pass"] else "fail", row["observed"]])
    return rows


def report_md(a, ev):
    lines = ["# 评测报告（evaluation_report）", "",
             "- 案例：`%s`　状态：`%s`　语言：`%s`" % (a["case_id"], ev["status"], a["lang"]),
             "- 题量：%d　要点：%d　材料：%d 份（可用 %d 份）"
             % (len(a["tasks"]), sum(len(t["must_include_points"]) for t in a["tasks"]),
                len(a["materials"]), len(a["usable"])),
             "- 双评一致性：Cohen's kappa = %s（%s）；校准对照：%s"
             % (ev["kappa"], ev["kappa_note"], "pass" if ev["control_ok"] else "needs review"),
             "", "## 1. 六方向覆盖", "", "| 方向 | 落地产物 | 证据 |", "|---|---|---|",
             "| 任务集设计 | `tasks.jsonl` | 每题六字段齐全，必需要点带 locator |",
             "| 参考答案 | `reference_answers/` | 抽取式答案，逐句带原文定位 |",
             "| 评分锚点 | `anchors.md` | 每题 5 条可观察锚点 + 0/1/2 档阶梯 |",
             "| 标注一致性 | `scores.csv` | 双评分数、delta 与 kappa |",
             "| 运行复现 | `reproducibility.md` | 输入 sha1、版本、命令、文件清单 |",
             "| 评测报告 | `evaluation_report.md` | 逐题分数、证据、失败类型与改进建议 |",
             "", "## 2. 逐题结果", "",
             "| 题号 | 类型 | 方向 | 要点 | 双评 | 覆盖 | 结论 |", "|---|---|---|---|---|---|---|"]
    for d in ev["details"]:
        task = next(t for t in a["tasks"] if t["id"] == d["task_id"])
        lines.append("| %s | %s | %s | %d | %d / %d | %s | %s |"
                     % (d["task_id"], task["type"], task["direction"], len(task["must_include_points"]),
                        d["rater_a"], d["rater_b"], d["coverage"],
                        "accept" if d["accepted"] else "needs revision"))
    lines += ["", "## 3. 逐题证据与失败类型", ""]
    if not ev["details"]:
        lines += ["本题输入没有可判定的正文，未生成题目；缺什么见 `reproducibility.md` 的输入清单。", ""]
    for d in ev["details"]:
        task = next(t for t in a["tasks"] if t["id"] == d["task_id"])
        lines += ["### %s（%s）" % (task["id"], task["type"]), "",
                  "- 指令：%s" % task["instruction"],
                  "- 读者：%s　字数上限：%d" % (task["audience"], task["word_limit"]),
                  "- 命中要点：%s" % (", ".join(d["hits"]) or "无"),
                  "- 缺失数值：%s" % (", ".join(d["missing_numbers"]) or "无"),
                  "- 新增数值：%s" % (", ".join(d["new_numbers"]) or "无"),
                  "- 失败锚点：%s" % (", ".join(d["failed_rules"]) or "无"),
                  "- 改进建议：%s" % d["suggestion"], ""]
        lines += ["| 要点 | 定位 | 原文 |", "|---|---|---|"]
        for p in task["must_include_points"]:
            lines.append("| %s | %s %s | %s |" % (p["id"], p["material"], p["locator"],
                                                  p["quote"].replace("|", "\\|")[:110]))
        lines.append("")
    lines += ["## 4. 校准对照", "", "| 题号 | 正控通过 | 负控通过 | 正控分 | 负控分 |", "|---|---|---|---|---|"]
    for c in ev["controls"]:
        lines.append("| %s | %s | %s | %s | %s |" % (c["task_id"], c["control_positive"],
                                                     c["control_negative"], c["positive_score"], c["negative_score"]))
    lines += ["", "正控取自抽取式参考答案，负控由删数字并截断得到；任一负控被接受即说明锚点过松。", "",
              "## 5. 一致性、锚点修订与边界", "",
              "- 双评口径：rater_a 为严格归一化包含，rater_b 为词袋覆盖率，二者独立计分。",
              "- 分歧处理：delta 大于 1 时登记锚点复查项，分数保持原样；本轮登记 %d 项。" % len(ev["repairs"]),
              "- 覆盖判定为确定性匹配，人工认可的等价改写可能被判缺失；该项在逐题证据中列出。",
              "- 材料未提供正文时不再造题，状态记为 `insufficient_evidence`，缺什么在输入清单中写明。", ""]
    return "\n".join(lines)


def repro_md(a, out, work):
    lines = ["# 运行复现（reproducibility）", "",
             "- Skill：`%s` %s" % (SKILL_NAME, V.VERSION),
             "- Python：%s　标准库：仅标准库　网络：不使用" % sys.version.split()[0],
             "- 命令：`python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`",
             "- 输入目录：`%s`　工作目录：`%s`" % ("/input", "/app/work"),
             "- 确定性：同一输入重复运行得到同一批任务、同一批分数与同一批文件；时间戳只出现在 run.log 与 self_check.json 的 generated 字段。",
             "", "## 输入指纹", "", "| 材料 | 类型 | 字节 | sha1 前 12 位 | 可用单元 |", "|---|---|---|---|---|"]
    for m in a["materials"]:
        lines.append("| %s | %s | %d | %s | %d |" % (m["name"], m["kind"], m["bytes"],
                                                     m["sha1"] or "not-hashed", len(m["units"])))
    if not a["materials"]:
        lines.append("| 无 | - | 0 | - | 0 |")
    lines += ["", "## 复算步骤", "",
              "1. 在同一输入目录运行上面的命令。",
              "2. 比对 `scores.csv` 的双评分数与 `scores_detail.csv` 的锚点判定。",
              "3. 比对 `reproducibility.md` 的输入指纹与本次输入。",
              "4. 如需重评单题：读取 `tasks.jsonl` 的对应行与 `anchors.md` 的锚点表，按同一口径复算。",
              "", "## 结果清单", "", "| 文件 | 字节 |", "|---|---|"]
    for p in sorted(Path(out).rglob("*")):
        if p.is_file():
            lines.append("| %s | %d |" % (p.relative_to(out).as_posix(), p.stat().st_size))
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------- golden / diff
def skill_line(hint):
    try:
        for i, line in enumerate((PKG / "SKILL.md").read_text(encoding="utf-8").splitlines(), 1):
            if hint in line:
                return "SKILL.md#L%d" % i, line.strip()
    except OSError:
        pass
    return "SKILL.md", ""


def golden(a, contract, stage):
    req = []
    for i, (field, expect) in enumerate(FIELDS, 1):
        loc, line = skill_line(expect)
        req.append({"id": "G%02d" % i, "category": "题面字段", "field": field, "expect": expect,
                    "check": "task_field_present",
                    "source": {"kind": "skill_rule", "locator": loc, "quote": line, "verified": bool(line)}})
    for cat, expect, rule in [
            ("评分锚点", "每题至少 5 条可观察锚点，覆盖 0/1/2 档", "anchor_ladder"),
            ("双评", "两名评分员独立打分并记录 delta", "dual_rater"),
            ("一致性", "记录 Cohen's kappa 与分歧项", "kappa"),
            ("校准", "正控必须通过、负控必须拒绝", "calibration")]:
        loc, line = skill_line(V.scrub(expect))
        req.append({"id": "G%02d" % (len(req) + 1), "category": cat, "expect": expect,
                    "check": rule, "source": {"kind": "skill_rule", "locator": loc,
                                              "quote": line, "verified": bool(line)}})
    loc, line = skill_line("原样回填")
    req.append({"id": "G%02d" % (len(req) + 1), "category": "契约", "expect": "output_contract 逐键回填",
                "check": "contract_fill",
                "source": {"kind": "skill_rule", "locator": loc, "quote": line, "verified": bool(line)}})
    ce = []
    for key in (contract or {}):
        ce.append({"id": "C%02d" % (len(ce) + 1), "field": key, "expect": "真实值，非空且可回查",
                   "source": {"kind": "case_json", "locator": "case.json#/output_contract/%s" % key,
                              "quote": json.dumps(contract.get(key), ensure_ascii=False)[:160],
                              "verified": True}})
    return {"schema": V.SCHEMA + "/golden", "case_id": a["case_id"], "stage": stage,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": SKILL_NAME + "/" + V.VERSION,
            "task_fields": [f for f, _ in FIELDS], "structural_requirements": req,
            "anchor_policy": {"levels": [0, 1, 2], "rule_types": ["contains_all", "number_preserved",
                                                                   "no_new_numbers", "word_limit", "section_order"],
                              "repair_rule": "delta 大于 1 只修锚点措辞，不改分数"},
            "contract_expectations": ce,
            "totals": {"structural": len(req), "contract_fields": len(ce), "tasks": len(a["tasks"])}}


def diff_report(a, ev, golden_doc):
    items = []
    tasks = a["tasks"]
    for spec in golden_doc["structural_requirements"]:
        check = spec["check"]
        if check == "task_field_present":
            ok = bool(tasks) and all(spec["field"] in t for t in tasks)
            actual = "%d/%d 题带该字段" % (sum(1 for t in tasks if spec["field"] in t), len(tasks))
        elif check == "anchor_ladder":
            ok = bool(tasks) and all(len(t["anchors"]) >= 5 for t in tasks)
            actual = "锚点 %d 条" % sum(len(t["anchors"]) for t in tasks)
        elif check == "dual_rater":
            ok = bool(ev["details"]) and all("rater_a" in d and "rater_b" in d for d in ev["details"])
            actual = "%d 题记录双评" % len(ev["details"])
        elif check == "kappa":
            ok = isinstance(ev["kappa"], (int, float))
            actual = "kappa=%s" % ev["kappa"]
        elif check == "calibration":
            ok = ev["control_ok"]
            actual = "%d 组对照" % len(ev["controls"])
        else:
            ok = bool(a["case_id"])
            actual = "契约 %d 项" % len((a.get("contract") or {}))
        items.append({"id": spec["id"], "expect": spec["expect"], "actual": actual,
                      "verdict": "达标" if ok else ("缺失" if not tasks else "偏差"),
                      "source": spec["source"]})
    for ce in golden_doc["contract_expectations"]:
        ok = bool((a.get("contract") or {}).get(ce["field"]))
        items.append({"id": ce["id"], "expect": "契约字段 `%s` 已回填" % ce["field"],
                      "actual": "存在且非空" if ok else "缺失", "verdict": "达标" if ok else "缺失",
                      "source": ce["source"]})
    counts = {"达标": 0, "偏差": 0, "缺失": 0, "待定": 0}
    for it in items:
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
    lines = ["# 对照报告（diff_report）", "",
             "- 案例：`%s`　状态：`%s`　生成器：%s/%s" % (a["case_id"], ev["status"], SKILL_NAME, V.VERSION),
             "- 口径：达标 / 偏差 / 缺失 / 待定（无法判定时附原因）。由脚本确定计算，可重跑复核。",
             "", "## 1. 总览", "", "| 结论 | 条数 |", "|---|---|"]
    for key in ("达标", "偏差", "缺失", "待定"):
        lines.append("| %s | %d |" % (key, counts[key]))
    lines += ["", "## 2. 逐项对照", "", "| ID | 期望 | 实际 | 判定 | 来源 |", "|---|---|---|---|---|"]
    for it in items:
        src = it.get("source") or {}
        lines.append("| %s | %s | %s | **%s** | `%s` |" % (it["id"], it["expect"], it["actual"],
                                                          it["verdict"], src.get("locator") or "-"))
    todo = [it for it in items if it["verdict"] in ("偏差", "缺失")]
    lines += ["", "## 3. 待人工处理", ""]
    if not todo:
        lines.append("- 无：结构项与契约项均达标。")
    for it in todo:
        lines.append("- **%s**（%s）：%s；当前 %s。" % (it["id"], it["verdict"], it["expect"], it["actual"]))
    lines += ["", "## 4. 复核方法", "",
              "1. 读 `golden_standard.json` 的 `structural_requirements[].source`，逐条确认有可回查的规则句。",
              "2. 比对 `tasks.jsonl` 与 `scores_detail.csv` 的锚点判定。",
              "3. 重跑 `build`，计数应可复现。", ""]
    body = "\n".join(lines)
    return body, counts, items


def version_md(work, entries):
    state = Path(work) / "version_state.json"
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except Exception:
        data = {"entries": []}
    if not isinstance(data.get("entries"), list):
        data = {"entries": []}
    prev = data["entries"][-1] if data["entries"] else None
    new = entries[-1]
    if prev and prev.get("stage") == new.get("stage"):
        data["entries"][-1] = new
    else:
        data["entries"] = (data["entries"] + entries)[:8]
    try:
        state.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    lines = ["# 版本记录（version_history）", "",
             "记录交付产物的构建链：v0 索引骨架到 v1 成稿；命令与契约键名不变。", "",
             "| 版本 | 阶段 | 时间 | 题量 | 双评一致 | 变更 |", "|---|---|---|---|---|---|"]
    for e in data["entries"]:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (e.get("version"), e.get("stage"), e.get("time"),
                                                          e.get("tasks"), e.get("kappa"), e.get("change")))
    lines += ["", "## 回退", "",
              "1. 重跑 `python3 /skills/weekly-skill/scripts/main.py build` 会用同一输入重建全部产物。",
              "2. 只回退结果：用上一轮保存的 `scores.csv` 与 `scores_detail.csv` 覆盖后重跑 `verify.py --audit /app/output`。",
              "3. 输入或锚点变更后，先在 `tasks.jsonl` 修改题面，再按 `anchors.md` 的阶梯同步锚点，最后 build。", ""]
    return "\n".join(lines)
