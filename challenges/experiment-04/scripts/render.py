# -*- coding: utf-8 -*-
"""Render the comparison artifacts."""
from extract import s, num

STATE_CN = {"feasible": "可行", "conditional": "有条件可行", "undetermined": "无法判定",
            "infeasible": "不可行"}


def _ev_cell(v):
    if not v:
        return ""
    if v.get("grade") or v.get("locator"):
        return " [%s %s]" % (v.get("grade") or "-", v.get("locator") or "-")
    return ""


def memo_md(ctx, M, led, fl, status, ev, metrics):
    L = []
    A = L.append
    A("# 方案比较与选择备忘录 — experiment-04")
    A("")
    A("- case_id: `%s`" % ctx["case_id"])
    A("- status: `%s`" % status)
    A("- 材料: %s" % (", ".join("`%s`(%d chars)" % (m["name"], m["chars"])
                                for m in ctx["materials"]) or "（无）"))
    A("- 候选: %d，准则: %d，胜出: `%s`" % (len(ctx["candidates"]), len(ctx["criteria"]),
                                             M.get("winner") or "—"))
    A("")
    A("## 1. 决策问题与硬门禁")
    A("")
    A("- 决策问题：在 %d 个候选之间选择可执行方案，并给出可核对的取舍理由。" % len(ctx["candidates"]))
    if ctx["constraints"]:
        for k in ctx["constraints"]:
            e = (k.get("evidence") or {})
            A("- `%s` %s %s %s（severity=%s）；源 %s：> %s"
              % (k["criterion"], k["op"], s(k["value"]), "", k["severity"],
                 e.get("locator", ""), (e.get("quote") or "")[:140].replace("\n", " ")))
    else:
        A("- 材料未声明硬约束；门禁记为\"未声明\"，绝不默认通过。")
    A("")
    A("## 2. 准则字典（权重合计校验）")
    A("")
    A("| id | 名称 | 单位 | 方向 | 权重 | locator |")
    A("|---|---|---|---|---|---|")
    for c in ctx["criteria"]:
        e = c.get("evidence") or {}
        A("| `%s` | %s | %s | %s | %s | `%s` |"
          % (c["id"], c["name"], c["unit"] or "-", c["direction"], s(c["weight"]),
             e.get("locator", "")))
    if M.get("weight_sum") is not None:
        A("")
        A("- 权重合计 = %s（判定 1.00±0.02：%s）"
          % (s(M["weight_sum"]), "通过" if M.get("weight_ok") else "不通过"))
    A("")
    A("### 权重来源逐条引用")
    A("")
    for c in ctx["criteria"]:
        e = c.get("evidence") or {}
        A("- `%s`：> %s" % (c["id"], (e.get("quote") or "")[:200].replace("\n", " ")))
    A("")
    A("## 3. 比较矩阵（min-max 归一 + 加权）")
    A("")
    if not M.get("candidates"):
        A("材料中未检索到候选工作簿；矩阵只保留准则索引，见 `criteria_matrix.json`。")
    else:
        A("| 候选 | " + " | ".join(c["id"] for c in ctx["criteria"]) + " | 得分 | 覆盖 | 状态 |")
        A("|" + "---|" * (len(ctx["criteria"]) + 4))
        for c in M["candidates"]:
            cells = []
            for cr in ctx["criteria"]:
                v = c["values"].get(cr["id"], {})
                n = v.get("number")
                cells.append(s(n) if n is not None else "未报告")
            A("| `%s` | %s | %s | %s%% | %s |"
              % (c["candidate_id"], " | ".join(cells), s(c["score"]),
                 s(round(c["coverage"] * 100, 1)), STATE_CN.get(c["state"], c["state"])))
        A("")
        A("### 归一化区间与方向")
        A("")
        for n in M["normalisation"]:
            A("- `%s`（%s，权重 %s）：lo=%s hi=%s；取值 %s → 归一 %s"
              % (n["criterion"], n["direction"], s(n["weight"]), s(n["lo"]), s(n["hi"]),
                 n["values"], n["normalised"]))
        if M["dominance"]:
            A("")
            A("### 支配关系")
            for d in M["dominance"]:
                A("- `%s` 支配 `%s`（全准则不劣且至少一项严格更优）" % (d["dominates"], d["dominated"]))
        else:
            A("")
            A("- 无支配关系（或存在缺值，缺值不判支配）。")
        A("")
        A("### 排序（可行性状态 → 得分降序）")
        A("- 排名：%s" % (", ".join("`%s`" % x for x in M["ranked"]) or "无可排名候选"))
        A("- 胜出：`%s`" % (M.get("winner") or "—"))
    A("")
    A("## 4. 成本与周期台账（逐行复算）")
    A("")
    if not led.get("items") and not led.get("duration_items"):
        A("材料未声明 cost_time 台账；公式保留，逐行复算记为未声明。")
    else:
        A("- 计价公式：`%s`；币种 %s；实验次数 runs=%s"
          % (led.get("formula", ""), led.get("currency", ""), s(led.get("runs"))))
        for it in led.get("items", []):
            A("  - [%s] `%s` expr=%s → %s（%s）%s"
              % (it["class"], it["item"], it["expr"], s(it["value"]),
                 "ok" if it["ok"] else "FAIL: " + it["detail"], it["locator"]))
        for it in led.get("duration_items", []):
            A("  - [时长] `%s` hours=%s（%s）%s"
              % (it["item"], s(it["hours"]), "ok" if it["ok"] else "FAIL: " + it["detail"],
                 it["locator"]))
        for cid, pc in led.get("per_candidate", {}).items():
            A("  - 合计 `%s`：one_time %s + per_run %s × runs %s = **%s**"
              % (cid, s(pc["one_time"]), s(pc["per_run"]), s(pc["runs"]), s(pc["total"])))
    A("")
    A("## 5. 敏感性（翻转门槛）")
    A("")
    A("- 扫描：%s" % fl.get("note", ""))
    for a in fl.get("assumptions", []):
        if isinstance(a.get("chooser"), str):
            A("- `%s`：%s" % (a["name"], a["chooser"]))
        elif a.get("flip") == "stable":
            A("- `%s`（%s 于 `%s`）：区间内选择不变 → 稳健" % (a["name"], a["range"], a["criterion"]))
        elif isinstance(a.get("flip"), dict):
            A("- `%s`（%s 于 `%s`）：门槛 %s，`%s` → `%s`"
              % (a["name"], a["range"], a["criterion"], s(a["flip"]["threshold"]),
                 a["flip"]["from"], a["flip"]["to"]))
    if fl.get("stable"):
        A("- 稳健假设：%s" % ", ".join(fl["stable"]))
    A("")
    A("## 6. 风险条目")
    A("")
    if ctx["risks"]:
        for r in ctx["risks"]:
            if isinstance(r, dict):
                A("- `%s` %s：trigger=%s；criterion=%s；magnitude=%s；mitigation=%s；fallback=%s；acceptable=%s"
                  % (s(r.get("candidate")), s(r.get("risk")), s(r.get("trigger")),
                     s(r.get("criterion")), s(r.get("consequence_magnitude")),
                     s(r.get("mitigation")), s(r.get("fallback")), s(r.get("acceptable"))))
    else:
        A("- 材料未声明风险条目；风险维度记为未声明，不默认通过。")
    A("")
    A("## 7. 待确认与不确定")
    A("")
    for d in ctx["degradations"]:
        A("- %s" % d)
    A("- 缺值按 0 分计入得分并暴露在覆盖率里，不被平均掉。")
    A("- 未声明状态不给中间分（见状态映射表 §2）。")
    A("")
    A("## 8. 指标与来源")
    A("")
    A("- 指标：%s" % _fmt(metrics))
    for m in ctx["materials"]:
        A("- `%s` %s（%d chars，%s）" % (m["id"], m["name"], m["chars"], m["kind"]))
    A("- 证据命中率：%s/%s 条带逐字 quote" % (ev["verified"], ev["total"]))
    return "\n".join(L)


def _fmt(d):
    return ", ".join("%s=%s" % (k, v) for k, v in sorted(d.items()))


def matrix_json(ctx, M, status, metrics):
    return {"case_id": ctx["case_id"], "status": status,
            "criteria": [{"id": c["id"], "name": c["name"], "unit": c["unit"],
                          "direction": c["direction"], "weight": c["weight"],
                          "why": c["why"], "evidence": c["evidence"]}
                         for c in ctx["criteria"]],
            "weight_sum": M.get("weight_sum"), "weight_ok": M.get("weight_ok"),
            "weight_rule": M.get("norm_rule"), "score_formula": M.get("formula"),
            "normalisation": M.get("normalisation", []),
            "candidates": M.get("candidates", []),
            "dominance": M.get("dominance", []), "ranked": M.get("ranked", []),
            "winner": M.get("winner"), "scores": M.get("scores", {}),
            "state_map": ctx["state_map"], "grades": ctx["grades"],
            "feasibility_states": ctx["feasibility_states"],
            "constraints": ctx["constraints"],
            "degradations": ctx["degradations"], "metrics": metrics}


def flip_json(ctx, fl):
    return {"case_id": ctx["case_id"], "note": fl.get("note", ""),
            "assumptions": fl.get("assumptions", []), "flips": fl.get("flips", []),
            "stable": fl.get("stable", []), "claims": ctx["flip_claims"]}


def ledger_json(ctx, led):
    return {"case_id": ctx["case_id"], **led}


def evidence_json(ctx, matrix, stats):
    items = []
    for m in ctx["materials"]:
        items.append({"source_id": m["id"], "locator": m["id"], "quote": m["name"],
                      "verified": True, "kind": "material_index"})
    for c in ctx["criteria"]:
        e = c.get("evidence") or {}
        items.append({**e, "kind": "criterion", "key": c["id"]})
    for t in ctx["tables"]:
        items.append({"source_id": t["mat"]["id"], "locator": t["locator"],
                      "quote": " | ".join(t["header"])[:200],
                      "verified": True, "kind": "table_index"})
    for k in ctx["constraints"]:
        e = k.get("evidence") or {}
        items.append({**e, "kind": "constraint", "key": k["criterion"]})
    for c in ctx["candidates"]:
        items.append({**c.get("evidence", {}), "kind": "candidate", "key": c["candidate_id"]})
        for cid, v in c["values"].items():
            if v.get("locator"):
                items.append({"source_id": c["source"], "locator": v["locator"],
                              "quote": v.get("quote") or "value cell for %s" % cid,
                              "verified": bool(v.get("quote")),
                              "kind": "value", "key": "%s.%s" % (c["candidate_id"], cid)})
    for lst, kind in (("assumptions", "assumption"), ("risks", "risk")):
        for it in ctx.get(lst, []):
            if isinstance(it, dict):
                items.append({"source_id": (ctx.get(lst + "_src") or {}).get("source_id", ""),
                              "locator": (ctx.get(lst + "_src") or {}).get("locator", ""),
                              "quote": s(it.get("name") or it.get("risk"))[:120],
                              "verified": False, "kind": kind,
                              "key": s(it.get("name") or it.get("risk"))})
    return {"case_id": ctx["case_id"], "items": items, "stats": stats}


def version_diff_md(ctx, M):
    L = ["# 候选对比 — experiment-04", "",
         "| 候选 | 得分 | 覆盖 | 状态 | 命中准则 | 缺值准则 | 来源 |",
         "|---|---|---|---|---|---|---|"]
    for c in M.get("candidates", []):
        L.append("| `%s` | %s%% | %s | %s | %s | %s | `%s` |"
                 % (c["candidate_id"], s(c["score"]), s(c["coverage"]),
                    STATE_CN.get(c["state"], c["state"]),
                    ", ".join(k for k, v in c["values"].items() if v.get("number") is not None),
                    ", ".join(k for k, v in c["values"].items() if v.get("number") is None) or "-",
                    c.get("source", "")))
    L += ["", "胜出：`%s`（排序键：可行性状态 → 得分降序）" % (M.get("winner") or "—"),
          "", "准则权重合计：%s（判定 1.00±0.02：%s）"
          % (s(M.get("weight_sum")), "通过" if M.get("weight_ok") else "不通过"), ""]
    return "\n".join(L)


def confirmations(ctx, M, led):
    out = []
    if not ctx["candidates"]:
        out.append("材料未给出候选工作簿：需人工补录 candidates 与其 values。")
    if not ctx["constraints"]:
        out.append("未声明硬约束：需确认是否存在预算上限或截止期门禁。")
    if not ctx["assumptions"]:
        out.append("未声明假设：需补录 assumptions（range + effect）以做敏感性。")
    if not ctx["cost_time"]:
        out.append("未声明 cost_time 台账：需补录一次性/按次项与 expr。")
    if not ctx["risks"]:
        out.append("未声明风险条目：需补录 5 个必填字段。")
    for c in M.get("candidates", []):
        for k, v in c["values"].items():
            if v.get("number") is None:
                out.append("候选 `%s` 的 `%s` 未报告：按 0 分处理，需补证据。"
                           % (c["candidate_id"], k))
    if not out:
        out.append("所有声明项均已覆盖；仍建议对翻转门槛做一次人工复核。")
    return out
