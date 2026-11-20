# -*- coding: utf-8 -*-
"""Render the artifacts: the review markdown, checks, estimate, risks, confirmations,
evidence and the version diff."""
from extract import s, num, nkey

CAT_CN = {"equipment": "设备", "material": "材料", "time": "时间", "sample": "样本",
          "ethics_safety": "伦理与安全", "parameter": "参数范围", "risk": "风险与异常"}
ORDER = ["equipment", "material", "time", "sample", "ethics_safety", "parameter", "risk"]
CN = {"ready": "可行", "conditional": "有条件可行", "blocked": "不可行",
      "unknown": "未声明"}


def review_md(ctx, res, status, stats):
    L = []
    A = L.append
    A("# 可行性复核报告 — experiment-02")
    A("")
    A("- case_id: `%s`" % ctx["case_id"])
    A("- status: `%s`" % status)
    A("- 材料: %s" % (", ".join("`%s`(%d chars)" % (m["name"], m["chars"])
                                for m in ctx["materials"]) or "（无）"))
    A("- 版本数: %d，胜出: `%s`" % (len(res["versions"]), res["winner"] or "—"))
    A("")
    A("## 1. 七大项复核（逐版本 × 逐项）")
    A("")
    A("| 版本 | " + " | ".join(CAT_CN[c] for c in ORDER) + " | 可行 | 单次成本 |")
    A("|" + "---|" * (len(ORDER) + 3))
    for r in res["versions"]:
        cells = [CN.get(r["verdict"][c]["state"], "—") for c in ORDER]
        cost = "—" if r["per_run_cost"] in (None, 0) else s(r["per_run_cost"])
        A("| %s | %s | %s | %s |" % (r["version"], " | ".join(cells),
                                     "是" if r["feasible"] else "否", cost))
    A("")
    A("### 逐项依据")
    A("")
    for r in res["versions"]:
        A("**版本 %s**（`%s`）" % (r["version"], r["evidence"]["locator"]))
        for c in ORDER:
            v = r["verdict"][c]
            why = v.get("why") or v.get("detail") or ""
            A("- %s：%s — %s" % (CAT_CN[c], CN.get(v["state"], "—"), why))
        A("")
    A("## 2. 时间与成本（逐版本，线级）")
    A("")
    for r in res["versions"]:
        est = r["verdict"]["time"].get("estimate") or {}
        A("### %s" % r["version"])
        if not est.get("available"):
            A("- 未提供步骤表：%s" % est.get("reason", ""))
            A("")
            continue
        A("- 步骤行（串行分钟 + 并行组取最大）：")
        for ln in est["lines"]:
            A("  - `%s` 持续 %s min，组 `%s`，人力 %s，等待 %s d"
              % (ln["step"], ln["duration_min"], ln["group"], ln["labor_people"],
                 ln["wait_days"]))
        A("- 单次时长 = %s min" % est["duration_min"])
        if est.get("cost_lines"):
            A("- 成本行：")
            for cl in est["cost_lines"]:
                A("  - %s × %s %s = %s" % (cl["amount"], cl["unit_price"],
                                           cl["unit"], cl["line_total"]))
        A("- 单次成本 = %s；占预算 %s%%（预算 %s）"
          % (s(est.get("per_run_cost")), s(r["budget_use_pct"]), s(res["budget"])))
        for ck in est.get("checks", []):
            A("- 自检 `%s`：%s（%s）" % (ck["name"], "ok" if ck["ok"] else "FAIL", ck["detail"]))
        A("")
    A("## 3. 参数范围与约束（逐项，带 locator 与 quote）")
    A("")
    if not res["searched"]:
        A("材料中未检索到有限参数域或数值约束；已检索位置见 `checks.json`。")
    for it in res["searched"]:
        e = (it.get("evidence") or [{}])[0]
        if it["kind"] == "parameter_domain":
            A("- 域 `%s`：%s–%s step %s %s（轴点 %s）；源 %s：> %s"
              % (it["key"], it["min"], it["max"], it["step"], it["unit"], it["points"],
                 e.get("locator", ""), e.get("quote", "")[:160].replace("\n", " ")))
        else:
            A("- 约束 `%s` %s %s %s；源 %s：> %s"
              % (it["param"], it["op"], it["value"], it["unit"], e.get("locator", ""),
                 e.get("quote", "")[:160].replace("\n", " ")))
    A("")
    A("## 4. 风险与异常")
    A("")
    for r in res["versions"]:
        A("### %s" % r["version"])
        for it in r["verdict"]["risk"]["items"]:
            A("- %s：%s" % (it["name"], it["detail"]))
        A("- 未声明项按“不可断言”处理，不视为已满足。")
        A("")
    A("## 5. 待确认清单（批准前必须关闭）")
    A("")
    for line in confirmations(ctx, res):
        A("- %s" % line)
    A("")
    A("## 6. 算术台账")
    A("")
    for ck in res["checks"]:
        A("- `%s`：%s — %s" % (ck["name"], "ok" if ck["ok"] else "FAIL", ck["detail"]))
    for r in res["versions"]:
        est = r["verdict"]["time"].get("estimate") or {}
        for ck in est.get("checks", []):
            A("- [`%s`] `%s`：%s — %s" % (r["version"], ck["name"],
                                           "ok" if ck["ok"] else "FAIL", ck["detail"]))
    A("")
    A("## 7. 局限与降级")
    A("")
    for d in res["degradations"]:
        A("- %s" % d)
    A("- 本复核不做显著性检验；样本不足时只报可核验的算术量。")
    A("")
    A("## 8. 来源与命中率")
    A("")
    for m in ctx["materials"]:
        A("- `%s` %s（%d chars，%s）" % (m["id"], m["name"], m["chars"], m["kind"]))
    A("- 抽取命中率：%s/%s 条带逐字 quote" % (stats["verified"], stats["total"]))
    return "\n".join(L)


def confirmations(ctx, res):
    out = []
    if not (ctx["res_equipment"] or ctx["res_materials"] or ctx["res_bookings"]):
        out.append("材料未给出设备/耗材/机时对象：需人工补录四项状态（现有/可外协/需采购/不可用）。")
    for b in ctx["res_bookings"]:
        if b.get("window_days") is None:
            out.append("机时 `%s` 未声明窗口天数：需确认档期窗口。" % b["name"])
    for m in ctx["res_materials"]:
        if num(m.get("lead_time")) is None:
            out.append("耗材 `%s` 未声明货期：需确认到货时间。" % m["name"])
    if not ctx["res_samples"]:
        out.append("未声明样本量（所需 vs 可用）：需补录或标注不涉及人类/动物受试。")
    if not ctx["res_approvals"]:
        out.append("未声明伦理/安全审批：需确认是否涉及受试者、生物或危化品。")
    if ctx["budget"] is None:
        out.append("未声明预算上限：需补录以计算超预算百分比。")
    if not out:
        out.append("所有声明项均已覆盖；仍建议对窗口与货期做一次人工复核。")
    return out


def checks_json(ctx, res, status, stats):
    return {"case_id": ctx["case_id"], "status": status,
            "categories": [{"key": k, "cn": CAT_CN[k]} for k in ORDER],
            "category_ledger": res["category_ledger"],
            "per_version": [{"version": r["version"], "feasible": r["feasible"],
                             "blocked": r["blocked"],
                             "states": {c: r["verdict"][c]["state"] for c in ORDER}}
                            for r in res["versions"]],
            "ranked": res["ranked"], "winner": res["winner"],
            "parameter_domains": res["searched"],
            "rules_index": res["rules_index"],
            "degradations": res["degradations"],
            "evidence_stats": stats}


def estimate_json(ctx, res):
    return {"case_id": ctx["case_id"], "budget": res["budget"],
            "budget_evidence": res["budget_evidence"],
            "formula_duration": "serial step minutes + one max per parallel group",
            "formula_cost": "sum(amount x unit_price) per priced item (consumables + booking days)",
            "per_version": [{"version": r["version"], "per_run_cost": r["per_run_cost"],
                             "budget_use_pct": r["budget_use_pct"],
                             "estimate": r["verdict"]["time"].get("estimate")}
                            for r in res["versions"]],
            "checks": res["checks"] +
                      [{"version": r["version"], **ck} for r in res["versions"]
                       for ck in (r["verdict"]["time"].get("estimate") or {}).get("checks", [])]}


def risks_json(ctx, res):
    items = []
    for r in res["versions"]:
        for it in r["verdict"]["risk"]["items"]:
            items.append({"version": r["version"], "name": it["name"], "detail": it["detail"]})
    for c in ctx["constraints"]:
        items.append({"version": "*", "name": "constraint_%s" % c["id"],
                      "detail": "%s %s %s %s" % (c["param"], c["op"], c["value"], c["unit"]),
                      "evidence": c["evidence"]})
    return {"case_id": ctx["case_id"], "items": items,
            "unavailable": [{"name": e["name"], "evidence": e["evidence"]}
                            for e in ctx["res_equipment"] if e.get("status") == "unavailable"],
            "searched_but_absent": res["degradations"]}


def confirmations_json(ctx, res):
    return {"case_id": ctx["case_id"], "items": confirmations(ctx, res),
            "approvals": ctx["res_approvals"], "budget": res["budget"]}


def evidence_json(ctx, res, stats):
    items = []
    for m in ctx["materials"]:
        items.append({"source_id": m["id"], "locator": m["id"], "quote": m["name"],
                      "verified": True, "kind": "material_index"})
    for p in ctx["params"]:
        for e in p["evidence"]:
            items.append({**e, "kind": "parameter_domain", "key": p["name"]})
    for c in ctx["constraints"]:
        for e in c["evidence"]:
            items.append({**e, "kind": "constraint", "key": c["param"]})
    for lst, kind in (("res_equipment", "equipment"), ("res_materials", "material"),
                      ("res_bookings", "booking"), ("res_samples", "sample"),
                      ("res_approvals", "approval")):
        for it in ctx[lst]:
            e = it.get("evidence") or {}
            items.append({"source_id": e.get("source_id", ""), "locator": e.get("locator", ""),
                          "quote": e.get("quote", ""), "verified": e.get("verified", False),
                          "kind": kind, "key": it.get("name", "")})
    for r in res["versions"]:
        e = r.get("evidence") or {}
        items.append({**e, "kind": "plan_version", "key": r["version"]})
    return {"case_id": ctx["case_id"], "items": items, "stats": stats}


def version_diff_md(ctx, res):
    L = ["# 版本对比 — experiment-02", "",
         "| 版本 | 参数 | 七大项不可行数 | 单次成本 | 占预算 | 可行 | locator |",
         "|---|---|---|---|---|---|---|"]
    for r in res["versions"]:
        params = ", ".join("%s=%s" % (k, s(v)) for k, v in r["params"].items())
        L.append("| %s | %s | %s | %s | %s%% | %s | `%s` |"
                 % (r["version"], params, len(r["blocked"]), s(r["per_run_cost"]),
                    s(r["budget_use_pct"]), "是" if r["feasible"] else "否",
                    r["evidence"]["locator"]))
    L += ["", "胜出：`%s`（排序键：可行 → 不可行项数 → 单次成本）" % (res["winner"] or "—"), ""]
    return "\n".join(L)
