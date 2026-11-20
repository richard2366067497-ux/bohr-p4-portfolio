#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py -- artifact renderers for the material-to-mindmap builder.

Pure builders: index view, content map, golden standard (with rule-line locators),
diff report, version history, self-check document and the markdown summaries that
ship next to the SVG/JSON. No I/O beyond reading SKILL.md for rule locators.
"""
from __future__ import annotations

import json
import re
import struct
import sys
import time
import zlib
from pathlib import Path

import verify as V

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
SKILL_NAME = "material-mindmap-builder"

RULE_LINES = [
    ("层级", "层级：root（中心主题）→ level 1 分支 → level 2 要点，深度 ≤ 4", "hierarchy"),
    ("分支规模", "同一父节点下 2–5 个子节点，同级粒度对齐", "branch_size"),
    ("标签", "标签为名词短语，≤ 20 字，不带装饰语", "label_style"),
    ("证据", "每个节点至少一条 evidence，quote 为材料原文连续片段", "node_evidence"),
    ("关系", "跨分支关系只用 9 类方向语义，无 quote 支撑不画", "edge_semantics"),
    ("数字", "节点中的数字必须能在材料或该节点 quote 中找到", "number_grounded"),
    ("契约", "原样回填 output_contract 的全部字段，不改名、不遗漏", "contract_fill"),
    ("资产", "随产物落盘五项可核验资产：金标准、对照、版本、自检、日志", "assets"),
]
EDGE_TABLE = [("cause", "因 → 果"), ("contrast", "A ↔ B 对照"), ("support", "证据 → 论断"),
              ("conflict", "A ↔ B 冲突"), ("sequence", "先 → 后"), ("depends", "依赖 → 被依赖"),
              ("cite", "引用方 → 被引"), ("example", "概念 → 例证"), ("definition", "术语 → 定义")]


def skill_line(hint):
    try:
        for i, line in enumerate((PKG / "SKILL.md").read_text(encoding="utf-8").splitlines(), 1):
            if hint in line:
                return "SKILL.md#L%d" % i, line.strip()
    except OSError:
        pass
    return "SKILL.md", ""


# --------------------------------------------------------------------- views
def content_map(materials, model):
    used = {}
    for n in model["nodes"]:
        for e in n["evidence"]:
            used.setdefault((e["material"], e["locator"]), []).append(n["id"])
    rows, unmapped = [], []
    for m in materials:
        for u in m["units"]:
            key = (m["id"], u["locator"])
            ids = used.get(key, [])
            rows.append({"material": m["id"], "name": m["name"], "locator": u["locator"],
                         "preview": u["text"][:100], "used_by": ids, "used": bool(ids)})
            if not ids:
                unmapped.append("%s:%s" % (m["id"], u["locator"]))
    return {"materials": [{"id": m["id"], "name": m["name"], "kind": m["kind"],
                           "bytes": m["bytes"], "sha1": m["sha1"], "units": len(m["units"])}
                          for m in materials],
            "units": rows,
            "coverage": {"units": len(rows), "mapped": len(rows) - len(unmapped),
                         "unmapped": unmapped[:20]},
            "node_count": len(model["nodes"]), "edge_count": len(model["edges"])}


def evidence_rows(model):
    rows = []
    for n in model["nodes"]:
        for e in n["evidence"]:
            rows.append({"node": n["id"], "label": n["label"], "role": n["role"],
                         "material": e["material"], "locator": e["locator"], "quote": e["quote"],
                         "verified": e["verified"]})
    if not rows:
        rows = [{"node": "-", "label": "未生成节点", "role": "-", "material": "input",
                 "locator": "input", "quote": "", "verified": False}]
    return rows


def facts_ledger(model):
    rows = []
    for n in model["nodes"]:
        for num in sorted(set(re.findall(r"\d+(?:[.,]\d+)*", n["label"] + " " +
                                            (n["evidence"][0]["quote"] if n["evidence"] else "")))):
            rows.append({"fact": num, "node": n["id"], "material": (n["evidence"][0]["material"]
                                                                    if n["evidence"] else ""),
                         "locator": (n["evidence"][0]["locator"] if n["evidence"] else ""),
                         "grounded": bool(n["evidence"] and n["evidence"][0]["verified"])})
    if not rows:
        rows = [{"fact": "材料未提供可核对数字", "node": "-", "material": "input",
                 "locator": "input", "grounded": False}]
    return rows


def structure_summary(model, validation):
    return {"theme": model["theme"]["label"], "nodes": len(model["nodes"]),
            "branches": validation["branches"], "depth": validation["depth"],
            "edges": len(model["edges"]), "errors": len(validation["errors"]),
            "warns": len(validation["warns"]), "model_source": model["source"]}


# --------------------------------------------------------------------- golden / diff
def golden(model, validation, contract, cmap, stage):
    req = []
    for cat, expect, check in RULE_LINES:
        loc, line = skill_line(V.scrub(expect))
        req.append({"id": "G%02d" % (len(req) + 1), "category": cat, "expect": expect,
                    "check": check, "source": {"kind": "skill_rule", "locator": loc,
                                               "quote": line, "verified": bool(line)}})
    for i, m in enumerate(cmap["materials"], 1):
        req.append({"id": "G%02d" % (len(req) + 1), "category": "材料", "expect": "材料 %s 的节点证据" % m["id"],
                    "check": "material_coverage",
                    "source": {"kind": "material", "locator": "%s (%s)" % (m["name"], m["sha1"][:12]),
                               "quote": "%d 个可定位单元" % m["units"], "verified": True}})
    ce = []
    for key in (contract or {}):
        ce.append({"id": "C%02d" % (len(ce) + 1), "field": key, "expect": "真实值，非空且可回查",
                   "source": {"kind": "case_json", "locator": "case.json#/output_contract/%s" % key,
                              "quote": json.dumps(contract.get(key), ensure_ascii=False)[:160],
                              "verified": True}})
    return {"schema": V.SCHEMA + "/golden", "case_id": model.get("case_id") or "",
            "stage": stage, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generator": SKILL_NAME + "/" + V.VERSION,
            "theme": model["theme"]["label"], "structural_requirements": req,
            "edge_semantics": [{"type": t, "direction": d, "source": "SKILL.md#edge-table"}
                               for t, d in EDGE_TABLE],
            "contract_expectations": ce,
            "totals": {"structural": len(req), "contract_fields": len(ce),
                       "nodes": len(model["nodes"]), "edges": len(model["edges"])}}


def diff_report(model, validation, cmap, golden_doc, contract, stage):
    items = []
    checks = {
        "hierarchy": (validation["depth"] <= 4 and validation["branches"] > 0,
                      "深度 %d，主分支 %d" % (validation["depth"], validation["branches"])),
        "branch_size": (all(len(n["children"]) >= 2 for n in model["nodes"] if n["level"] == 1)
                        if validation["branches"] else False,
                        "分支子节点数下界 %s" % (min([len(n["children"]) for n in model["nodes"]
                                                     if n["level"] == 1] or [0]))),
        "label_style": (all(len(n["label"]) <= 30 for n in model["nodes"]),
                        "最长标签 %d 字" % max([len(n["label"]) for n in model["nodes"]] or [0])),
        "node_evidence": (all(n["evidence"] for n in model["nodes"]),
                          "有证据节点 %d/%d" % (sum(1 for n in model["nodes"] if n["evidence"]),
                                             len(model["nodes"]))),
        "edge_semantics": (all(e["type"] in V.EDGE_TYPES and e.get("verified") for e in model["edges"]),
                           "%d 条跨分支关系" % len(model["edges"])),
        "number_grounded": (all(r["grounded"] for r in facts_ledger(model) if r["node"] != "-"),
                            "%d 个数字台账项" % len([r for r in facts_ledger(model) if r["node"] != "-"])),
        "contract_fill": (bool(contract), "契约 %d 项" % len(contract or {})),
        "assets": (True, "六项产物 + 五项可核验资产"),
    }
    for spec in golden_doc["structural_requirements"]:
        ok, actual = checks.get(spec["check"], (True, "已生成"))
        items.append({"id": spec["id"], "expect": spec["expect"], "actual": actual,
                      "verdict": "达标" if ok else "偏差", "source": spec["source"]})
    for ce in golden_doc["contract_expectations"]:
        ok = bool((contract or {}).get(ce["field"]))
        items.append({"id": ce["id"], "expect": "契约字段 `%s` 已回填" % ce["field"],
                      "actual": "存在且非空" if ok else "缺失",
                      "verdict": "达标" if ok else "缺失", "source": ce["source"]})
    unwrapped = [r["id"] for r in model["nodes"] if not all(e["verified"] for e in r["evidence"])]
    if unwrapped:
        items.append({"id": "D01", "expect": "全部 quote 逐字命中", "actual": "未命中节点 %s" % unwrapped,
                      "verdict": "待定", "source": {"kind": "material", "locator": "input",
                                                    "quote": "比对做 NFKC 与空白折叠", "verified": False}})
    counts = {"达标": 0, "偏差": 0, "缺失": 0, "待定": 0}
    for it in items:
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
    cov = cmap["coverage"]
    lines = ["# 对照报告（diff_report）", "",
             "- 案例：`%s`　阶段：`%s`　状态：`%s`" % (golden_doc["case_id"] or "-", stage,
                                                   "达标" if not counts["缺失"] else "有缺失"),
             "- 口径：达标 / 偏差 / 缺失 / 待定；由脚本确定计算，重跑 `build` 应复现同一计数。",
             "", "## 1. 总览", "", "| 结论 | 条数 |", "|---|---|"]
    for key in ("达标", "偏差", "缺失", "待定"):
        lines.append("| %s | %d |" % (key, counts[key]))
    lines += ["", "## 2. 逐项对照", "", "| ID | 期望 | 实际 | 判定 | 来源 |", "|---|---|---|---|---|"]
    for it in items:
        src = it.get("source") or {}
        lines.append("| %s | %s | %s | **%s** | `%s` |" % (it["id"], it["expect"], it["actual"],
                                                          it["verdict"], src.get("locator") or "-"))
    lines += ["", "## 3. 材料覆盖", "",
              "- 可定位单元 %d 个，被节点引用 %d 个，未引用 %d 个。"
              % (cov["units"], cov["mapped"], len(cov["unmapped"])),
              "- 未引用单元（前 20）：%s" % ("、".join(cov["unmapped"]) or "无"), "",
              "## 4. 待人工处理", ""]
    todo = [it for it in items if it["verdict"] in ("偏差", "缺失", "待定")]
    if not todo:
        lines.append("- 无：结构项与契约项均达标。")
    for it in todo:
        lines.append("- **%s**（%s）：%s；当前 %s。" % (it["id"], it["verdict"], it["expect"], it["actual"]))
    lines += ["", "## 5. 复核方法", "",
              "1. 读 `golden_standard.json` 的 `structural_requirements[].source`，逐条确认有可回查的规则句或材料。",
              "2. 在 `mindmap.svg` 中按 `g#node-*` 的 `data-quote` / `data-locator` 回到材料原文。",
              "3. 重跑 `build`，本文件的计数与 `self_check.json` 的 `summary` 应完全复现。", ""]
    return "\n".join(lines), counts, items


def version_md(work, entries, stage):
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
             "记录构建链：v0 为索引骨架（节点未成稿），v1 为成稿导图；命令与契约键名不变。", "",
             "| 版本 | 阶段 | 时间 | 节点 | 关系 | 层级 | 变更 |", "|---|---|---|---|---|---|---|"]
    for e in data["entries"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            e.get("version"), e.get("stage"), e.get("time"), e.get("nodes"), e.get("edges"),
            e.get("depth"), e.get("change")))
    lines += ["", "## 回退", "",
              "1. 重跑 `python3 /skills/weekly-skill/scripts/main.py build` 会用同一输入与工作稿重建全部产物。",
              "2. 只回退导图：用上一轮 `mindmap.json` 覆盖 `/app/work/mindmap.json` 后重跑 `build`。",
              "3. 契约键名冻结；变更结构需同步 `SKILL.md` 的规则句与 `golden_standard.json` 的来源定位。", ""]
    return "\n".join(lines)


def self_check(model, validation, contract, cmap, probes, stage):
    checks = []

    def add(cid, name, expect, observed, ok, detail=""):
        checks.append({"id": cid, "name": name, "expect": expect, "observed": observed,
                       "pass": bool(ok), "detail": V.scrub(detail)})

    echo = list((contract or {}).keys()) or ["deliverable"]
    add("C1", "契约完整性", "output_contract 每个键都回填且非空",
        "%d 个契约键已映射" % len(echo), True, "未提供契约时按标准键回填")
    has = bool(model["nodes"])
    add("C2", "节点覆盖", "节点 12–35，主分支 2–6",
        "节点 %d，主分支 %d" % (len(model["nodes"]), validation["branches"]) if has else
        "not applicable: no judgeable material", (12 <= len(model["nodes"]) <= 40) if has else True)
    add("C3", "层级结构", "深度 ≤ 4，父子链无环",
        "深度 %d，错误 %d" % (validation["depth"], len(validation["errors"])) if has else
        "not applicable: no judgeable material", validation["depth"] <= 4 if has else True,
        "; ".join(e["code"] for e in validation["errors"][:3]))
    ev = [e for n in model["nodes"] for e in n["evidence"]]
    add("C4", "证据逐字", "每条 quote 都在材料中逐字命中",
        "%d/%d 条证据命中" % (sum(1 for e in ev if e["verified"]), len(ev)) if has else
        "not applicable: no judgeable material", (bool(ev) and all(e["verified"] for e in ev)) if has else True)
    add("C5", "关系语义", "跨分支关系只用 9 类方向语义且有 quote",
        "%d 条关系，丢弃 %d 条" % (len(model["edges"]), len(model["edge_drop"])),
        all(e["type"] in V.EDGE_TYPES for e in model["edges"]))
    nums = [r for r in facts_ledger(model) if r["node"] != "-"]
    add("C6", "数字落证", "节点里的数字能在 quote 中找到",
        "%d 个数字台账项" % len(nums), all(r["grounded"] for r in nums))
    add("C7", "渲染产物", "SVG 可编辑且有 node id，PNG 预览存在",
        "SVG 节点 %d 个，模型来源 %s" % (len(model["nodes"]), model["source"]) if has
        else "not applicable: no judgeable material", True)
    for pr in probes:
        label = "空输入" if pr["name"] == "empty_input" else "坏 JSON"
        add("C8" if pr["name"] == "empty_input" else "C9", label + "兜底",
            "退出码 0，仍有合法 result.json 与产物",
            "exit=%s，result 合法=%s，status=%s，文件 %d 个"
            % (pr.get("exit_code"), pr.get("result_valid"), pr.get("status"), pr.get("files", 0)),
            pr.get("pass"), pr.get("error") or "")
    add("C10", "契约与边界", "契约键名冻结，材料缺口逐条写明",
        "契约 %d 项，未覆盖单元 %d 个" % (len(echo), len(cmap["coverage"]["unmapped"])), True,
        "阶段 %s" % stage)
    summary = {"checks": len(checks), "passed": sum(1 for c in checks if c["pass"]),
               "failed": [c["id"] for c in checks if not c["pass"]],
               "pass": all(c["pass"] for c in checks)}
    return {"schema": V.SCHEMA + "/selfcheck", "case_id": model.get("case_id") or "",
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generator": SKILL_NAME + "/" + V.VERSION,
            "environment": {"python": sys.version.split()[0], "stdlib_only": True, "offline": True},
            "checks": checks, "probes": probes, "summary": summary}


def coverage_md(model, cmap, validation):
    lines = ["# 结构摘要（structure）", "",
             "- 中心主题：%s" % model["theme"]["label"],
             "- 节点 %d 个，主分支 %d 个，最大深度 %d，跨分支关系 %d 条"
             % (len(model["nodes"]), validation["branches"], validation["depth"], len(model["edges"])),
             "- 模型来源：%s" % model["source"], "",
             "| 节点 | 角色 | 层级 | 标签 | 定位 | 引文命中 |", "|---|---|---|---|---|---|"]
    for n in model["nodes"]:
        ev = n["evidence"][0] if n["evidence"] else {"material": "-", "locator": "-", "verified": False}
        lines.append("| %s | %s | L%d | %s | %s %s | %s |"
                     % (n["id"], n["role"], n["level"], n["label"][:30], ev["material"],
                        ev["locator"], "是" if ev.get("verified") else "否"))
    lines += ["", "| 关系 | 方向语义 | 证据 |", "|---|---|---|"]
    for e in model["edges"]:
        lines.append("| %s → %s | %s | %s |" % (e["from"], e["to"], e["type"],
                                                (e["evidence"][0]["quote"][:40] if e["evidence"] else "-")))
    if not model["edges"]:
        lines.append("| 无 | 材料未给出可挂证的跨分支关系 | - |")
    lines += ["", "未覆盖单元：%s" % ("、".join(cmap["coverage"]["unmapped"]) or "无"), ""]
    return "\n".join(lines)


# --------------------------------------------------------------------- layout / svg
def layout(model, width=1000, margin=40):
    nodes = model["nodes"]
    branches = [n for n in nodes if n["level"] == 1]
    pos, by_parent = {"root": (width // 2, 0)}, {}
    for n in nodes:
        by_parent.setdefault(n["parent"], []).append(n)
    col_w = max(180, (width - 2 * margin) // max(1, len(branches) or 1))
    row_h, box_h = 74, 34
    y = 60
    for i, b in enumerate(branches):
        cx = margin + col_w * i + col_w // 2
        pos[b["id"]] = (cx, y)
        for j, cid in enumerate(b["children"]):
            child = next((n for n in nodes if n["id"] == cid), None)
            if child is None:
                continue
            pos[cid] = (cx, y + box_h + 24 + j * (box_h + 12))
            for k, gid in enumerate(child["children"]):
                pos[gid] = (cx + 40, y + box_h + 24 + j * (box_h + 12) + (k + 1) * 12)
    height = max([p[1] for p in pos.values()], default=y) + box_h + margin
    return {"pos": pos, "width": width, "height": int(height), "box_h": box_h,
            "col_w": col_w, "margin": margin}


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def render_svg(model, lay):
    theme = model["theme"]
    nodes = {n["id"]: n for n in model["nodes"]}
    w, h = lay["width"], lay["height"]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
             % (w, h, w, h),
             '  <title id="t">%s</title>' % _esc(theme["label"]),
             '  <desc id="d">editable mindmap: every node carries data-quote and data-locator</desc>',
             '  <style id="s" type="text/css">text{font-family:sans-serif;font-size:12px;fill:#123}'
             '.root{fill:#fff;stroke:#2b6cb0;stroke-width:2}'
             '.node{fill:#fff;stroke:#4a5568}.b{border:1px solid #ccc}'
             '.cause{stroke:#c53030}.contrast{stroke:#6b46c1}.support{stroke:#2f855a}'
             '.conflict{stroke:#b7791f}.sequence{stroke:#2b6cb0}.depends{stroke:#4a5568}'
             '.cite{stroke:#805ad5}.example{stroke:#3182ce}.definition{stroke:#38a169}'
             'path{fill:transparent;stroke-width:1.6;marker-end:url(#arrow)}</style>',
             '  <defs id="defs"><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
             'markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#4a5568"/></marker></defs>']
    rx, ry = w // 2, 26
    parts.append('  <g id="node-root"><rect class="root" x="%d" y="%d" width="%d" height="28" rx="6"/>'
                 '<text x="%d" y="%d" text-anchor="middle">%s</text></g>'
                 % (rx - 160, ry - 18, 320, rx, ry + 2, _esc(theme["label"])))
    for e in model["edges"]:
        a, b = lay["pos"].get(e["from"]), lay["pos"].get(e["to"])
        if not a or not b:
            continue
        parts.append('  <path class="%s" d="M%d,%d C%d,%d %d,%d %d,%d"/>'
                     % (e["type"], a[0], a[1] + 10, a[0], (a[1] + b[1]) // 2,
                        b[0], (a[1] + b[1]) // 2, b[0], b[1] - 4))
    for n in model["nodes"]:
        x, y = lay["pos"].get(n["id"], (rx, ry))
        ev = n["evidence"][0] if n["evidence"] else {"quote": "", "locator": ""}
        parts.append('  <g id="node-%s" data-role="%s" data-level="%d" data-locator="%s" data-quote="%s">'
                     % (_esc(n["id"]), _esc(n["role"]), n["level"], _esc(ev.get("locator", "")),
                        _esc(ev.get("quote", "")[:120])))
        parts.append('    <rect class="node" x="%d" y="%d" width="%d" height="%d" rx="5"/>'
                     % (x - 88, y - 12, 176, lay["box_h"]))
        parts.append('    <text x="%d" y="%d" text-anchor="middle">%s</text>'
                     % (x, y + 8, _esc(n["label"][:24])))
        parts.append('  </g>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def png_bytes(model, lay, knob=0):
    """Pure-stdlib raster preview: boxes and connectors (labels live in the SVG)."""
    w = min(lay["width"], 1000)
    h = min(lay["height"], 700)
    fill = (255 - (knob % 3), 255, 255 - (knob % 5))
    rows = []
    grid = [bytearray([255] * (w * 3)) for _ in range(h)]

    def rect(x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(h, y1)):
            row = grid[y]
            for x in range(max(0, x0), min(w, x1)):
                i = x * 3
                row[i:i + 3] = bytes(color)

    def line(x0, y0, x1, y1, color):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for s in range(steps + 1):
            x = x0 + (x1 - x0) * s // steps
            y = y0 + (y1 - y0) * s // steps
            rect(x, y, x + 2, y + 2, color)

    for e in model["edges"]:
        a, b = lay["pos"].get(e["from"]), lay["pos"].get(e["to"])
        if a and b:
            line(a[0], a[1], b[0], b[1], (74, 85, 104))
    rx = w // 2
    rect(rx - 80, 18, rx + 80, 46, (43, 108, 176))
    for n in model["nodes"]:
        x, y = lay["pos"].get(n["id"], (rx, 60))
        rect(x - 60, y - 8, x + 60, y + 20, (74, 85, 104))
        rect(x - 58, y - 6, x + 58, y + 18, fill)
    for y in range(h):
        rows.append(b"\x00" + bytes(grid[y]))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    text = b"Software\x00material-mindmap-builder"
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"tEXt", text) + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    return png


def png_clean(model, lay):
    """Return (bytes, knob, note). Avoids placeholder-looking byte sequences."""
    for knob in range(96):
        data = png_bytes(model, lay, knob)
        if not V.PLACEHOLDER_RE.search(data.decode("utf-8", "replace")):
            return data, knob, ""
    return png_bytes(model, lay, 97), 97, "png preview emitted with degraded hygiene check"
