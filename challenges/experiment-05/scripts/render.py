# -*- coding: utf-8 -*-
"""Artifact renderers for the interpretation dossier."""
import engine as EN
from extract import s, nkey

SECTION = ("趋势", "异常点", "可能原因", "复核步骤", "后续实验建议")


def _k(ctx, kind):
    return ctx.get("kinds", {}).get(kind, [])


def _inv_objects(ctx):
    from extract import pipe_tables
    out = []
    for m in ctx["materials"]:
        objs = []
        for t in pipe_tables(m):
            objs.append({"locator": t["locator"], "columns": t["header"],
                         "n_rows": len(t["rows"]), "n_cols": len(t["header"]),
                         "kind": "table"})
        out.append({"id": m["id"], "name": m["rel"], "kind": m["kind"],
                    "chars": m["chars"], "objects": objs})
    return out


def inventory_json(ctx):
    return {"case_id": ctx["case_id"], "files": _inv_objects(ctx),
            "series": [{"mat": x["mat"], "column": x["column"], "n": x["n"],
                        "locator": x["locator"]} for x in ctx["series"]],
            "unit_groups": [{"quantity": u["quantity"], "units": u["units"],
                             "locator": u["evidence"]["locator"]} for u in ctx["units"]]}


def thresholds_json(ctx):
    items = [{"name": t["name"], "value": t["value"], "unit": t["unit"],
              "role": t["role"], "locator": t["locator"], "quote": t["quote"],
              "verified": t["verified"], "conflict": t["conflict"]}
             for t in ctx["thresholds"]]
    conflicts = [i for i in items if i["conflict"]]
    return {"case_id": ctx["case_id"], "items": items, "conflicts": conflicts,
            "rule": "a conflicting constant is kept side by side, never silently reduced to one value"}


def evidence_json(ctx, res):
    items = []
    for t in ctx["thresholds"]:
        items.append({"kind": "threshold", "id": t["name"], "locator": t["locator"],
                      "quote": t["quote"], "verified": t["verified"]})
    for r in EN.rule_index(ctx):
        items.append({"kind": "rule", "id": r["id"], "locator": r["locator"],
                      "quote": r["quote"], "verified": r["verified"]})
    for u in ctx["units"]:
        items.append({"kind": "unit_group", "id": u["quantity"],
                      "locator": u["evidence"]["locator"], "quote": u["evidence"]["quote"],
                      "verified": u["evidence"]["verified"]})
    for k in ("attr_enum", "dnc", "artifacts", "status_map", "contract_map"):
        for r in _k(ctx, k):
            items.append({"kind": k, "id": (list(r["cells"].values())[0] if r["cells"] else ""),
                          "locator": r["locator"], "quote": r["quote"],
                          "verified": r["verified"]})
    for d in ctx["dossiers"]:
        items.append({"kind": "dossier", "id": d["id"], "locator": d["locator"],
                      "quote": d.get("evidence_quote") or d.get("observed") or "",
                      "verified": bool(d.get("evidence_quote"))})
    tot = len(items)
    ver = sum(1 for i in items if i.get("verified"))
    return {"case_id": ctx["case_id"], "items": items,
            "stats": {"verified": ver, "total": tot,
                      "rate": round(ver / tot, 4) if tot else 0.0}}


def recompute_json(ctx, res):
    st = EN.self_test(ctx)
    series = []
    for x in ctx["series"]:
        vals = x["values"]
        lo, hi = EN.fence(vals)
        series.append({"column": x["column"], "mat": x["mat"], "n": x["n"],
                       "locator": x["locator"], "mean": _r(EN.mean(vals)),
                       "sd": _r(EN.sd(vals)), "median": _r(EN.median(vals)),
                       "mad": _r(EN.mad(vals)), "iqr": _r(EN.iqr(vals)),
                       "fence": [_r(lo), _r(hi)]})
    cands = EN.screen_all(ctx)
    return {"case_id": ctx["case_id"],
            "fixture": EN.SELF_TEST_DATA,
            "definitions": st,
            "series": series,
            "rule_candidates": [{"rule_id": c["rule_id"], "locator": c["locator"],
                                 "value": _r(c["value"]), "severity": c["severity"],
                                 "detail": c["detail"]} for c in cands],
            "checks": EN.checks(ctx, res),
            "note": "the definitions are recomputed on the fixed fixture; a series is scored "
                    "only when a numeric column with five or more values is present"}


def uncertainties_json(ctx, res):
    items = list(ctx["degradations"])
    items += ctx.get("draft_uncertainties", [])
    if not items:
        items.append("no material-specific uncertainty was identified")
    confs = ctx.get("draft_confirmations", []) or [
        "confirm with the data owner whether the workbook is the original or a summary",
        "confirm with the equipment owner which channel or channel range the readouts belong to"]
    return {"case_id": ctx["case_id"], "uncertainties": items, "confirmations": confs,
            "gaps": [x for x in ctx["searched"]] or [
                {"item": "no gap recorded", "why": "every indexed structure carried a locator"}]}


def method_notes_md(ctx, res):
    L = ["# 方法说明 (method_notes)", "",
         "## 解析", "",
         "逐文件盘点；`.md` 走 pipe 表格 + 段落切片，`.json` 只做结构识别，其余按文本读取。",
         "每个对象带 locator（`file#L<n>` 行号 1 基）与整行 quote，可逐步比对。", "",
         "## 统计", "",
         "均值/样本 SD/中位数/MAD/修正 z/IQR 栅栏/最小二乘拟合/相对偏差，定义取自材料；",
         "定义性自检在固定夹具 %s 上复算，见 recompute.json。" % EN.SELF_TEST_DATA, "",
         "## 判据", "",
         "规则 id、触发条件与默认严重度逐行索引自材料，均带 locator 与 quote；",
         "阈值常量并列保留，冲突不择一。", "",
         "## 复跑", "",
         "```", "python3 scripts/main.py all --input /input --output /app/output --work /app/work",
         "```", "", "确定性算法，同输入同输出。", ""]
    return "\n".join(L)


def dossier_md(d):
    def lst(xs):
        return "\n".join("- " + s(x) for x in xs) if xs else "- 未声明"
    L = ["# 案卷 %s · %s" % (d["id"], d["anomaly_type"]), "",
         "| 项 | 值 |", "|---|---|",
         "| 规则 | %s |" % (s(d["rule_id"]) or "未声明"),
         "| 严重度 | %s |" % s(d["severity"]),
         "| 强度 | %s |" % s(d["strength"]),
         "| 判断 | %s |" % ("已判断" if d.get("judged") else "未判断"),
         "| 归因 | %s |" % (s(d["attribution"]) or "未判断"), "",
         "## 1. 观察", "", "- locator: %s" % (s(d["locator"]) or "未声明"),
         "- target: %s" % (s(d["target"]) or "未声明"),
         "- observed: %s" % (s(d["observed"]) or "未声明"), "",
         "## 2. 判据", "", "- rule_id: %s" % (s(d["rule_id"]) or "未声明"),
         "- expected_or_rule: %s" % (s(d["expected_or_rule"]) or "未声明"), "",
         "## 3. 证据（逐字）", "", "> %s" % (s(d.get("evidence_quote")) or "未提供逐字引用"), "",
         "## 4. 判断", "", "- verdict: %s" % s(d["verdict"]),
         "- severity: %s" % s(d["severity"]), "",
         "## 5. 归因", "", "- attribution: %s" % (s(d["attribution"]) or "未判断"),
         "- attribution_basis: %s" % (s(d["attribution_basis"]) or "未判断"), "",
         "## 6. 已排除的其他解释",
         lst(d.get("excluded_alternatives")), "",
         "## 7. 不得据此结论", lst(d.get("do_not_conclude")), "",
         "## 8. 复核动作与后续实验", lst(d.get("recheck_actions")),
         "- next_experiment: %s" % (s(d["next_experiment"]) or "未声明"), ""]
    return "\n".join(L)


def dossier_index_json(ctx):
    issues = []
    for d in ctx["dossiers"]:
        if not d["locator"]:
            issues.append({"id": d["id"], "issue": "locator missing"})
        if d.get("judged") and not d.get("attribution_basis"):
            issues.append({"id": d["id"], "issue": "judged without attribution_basis"})
        if not d.get("recheck_actions"):
            issues.append({"id": d["id"], "issue": "no executable recheck action"})
    return {"case_id": ctx["case_id"],
            "dossiers": [{"id": d["id"], "anomaly_type": d["anomaly_type"],
                          "target": d["target"], "severity": d["severity"],
                          "verdict": d["verdict"], "attribution": d["attribution"],
                          "strength": d["strength"], "locator": d["locator"],
                          "file": "dossiers/anomaly-%s.md" % d["id"]} for d in ctx["dossiers"]],
            "issues": issues,
            "count": len(ctx["dossiers"])}


def interpretation_md(ctx, res, status):
    dossiers = ctx["dossiers"]
    cands = EN.screen_all(ctx)
    L = ["# 实验结果解释与异常分析", "",
         "case_id: %s" % ctx["case_id"],
         "status: %s" % status, ""]
    if not dossiers and not ctx["trends"]:
        L += ["筛查事实，未经判断：未找到可复核的数值序列，也没有工作稿；",
              "下列五段结论各保留其证据缺口，不臆造趋势、异常或因果。", ""]
    L += ["## 1. 数据盘点", ""]
    for f in _inv_objects(ctx):
        L.append("- %s (%s, %d chars, %d object(s)): %s"
                 % (f["name"], f["kind"], f["chars"], len(f["objects"]),
                    ", ".join(o["locator"] for o in f["objects"][:4]) or "no table object"))
    L += ["", "## 2. 趋势", ""]
    if ctx["trends"]:
        for t in ctx["trends"]:
            L.append("- %s [%s] %s (method: %s; locator %s)"
                     % (s(t.get("trend_id")), s(t.get("scope")), s(t.get("statement")),
                        s(t.get("method")), s(t.get("locator"))))
    elif ctx["series"]:
        for x in ctx["series"][:8]:
            L.append("- column %s of %s: n=%d, mean %s, median %s, fence %s (locator %s)"
                     % (x["column"], x["mat"], x["n"], _r(EN.mean(x["values"])),
                        _r(EN.median(x["values"])), _fence(x["values"]), x["locator"]))
    else:
        L.append("- 证据缺口：材料中未找到 >=5 个数值的读数列，无法给出走势、拐点或平台期；")
        L.append("  已检索位置见 inventory.json，趋势判据（R1/R6/R6′）见 recompute.json。")
    L += ["", "## 3. 异常点", ""]
    if dossiers:
        for d in dossiers:
            L.append("- %s · %s · target %s · %s (locator %s; file dossiers/anomaly-%s.md)"
                     % (d["id"], d["anomaly_type"], s(d["target"]) or "未声明",
                        d["severity"], s(d["locator"]) or "未声明", d["id"]))
    elif cands:
        for c in cands[:12]:
            L.append("- %s at %s: %s (%s)" % (c["rule_id"], c["locator"], c["detail"], c["severity"]))
    else:
        L.append("- 证据缺口：没有数值序列可用于分布筛查，未提出异常点；")
        L.append("  判据 R1（修正 z > 3.5）、R2（IQR 栅栏）、R8′（饱和平台）已按材料索引。")
    L += ["", "## 4. 可能原因", ""]
    if ctx["causes"]:
        for c in ctx["causes"]:
            L.append("- %s | support: %s | exclusion: %s | strength %s"
                     % (s(c.get("candidate")), s(c.get("support")),
                        s(c.get("exclusion")), s(c.get("strength"))))
    else:
        hints = sorted({r["hint"] for r in EN.rule_index(ctx) if r["hint"]})
        L.append("- 由规则归因提示派生候选方向（按证据强度排序，不据此定因果）：%s"
                 % (", ".join(hints) or "材料未给出归因提示"))
        L.append("- 规则只发现\"与自身分布或其它源不一致\"，归因与排除须由判断者补齐。")
    L += ["", "## 5. 复核步骤", ""]
    rechecks = [x for d in dossiers for x in d.get("recheck_actions", [])]
    good = [r["quote"] for r in _k(ctx, "table") if "回查" in r["quote"]]
    for x in (rechecks or good)[:8]:
        L.append("- %s" % s(x))
    if not (rechecks or good):
        L.append("- 材料给出的可执行复核式样：指定对象 + 动作 + 判定条件；")
        L.append("  例：回查具体数据文件与字段、核对批次与设备日志、加做平行重复。")
    L += ["", "## 6. 后续实验建议", ""]
    nxt = ctx.get("draft_next_steps", []) + [d["next_experiment"] for d in dossiers
                                             if d.get("next_experiment")]
    for x in (nxt or ["补对照、加密采样点、调整参数范围、扩大重复数"]):
        L.append("- %s" % s(x))
    L += ["", "## 7. 不确定性与局限", ""]
    for x in ctx["degradations"][:12]:
        L.append("- %s" % s(x))
    L += ["", "## 8. 方法", "",
          "逐文件盘点 → 索引规则/单位/阈值 → 按定义复算统计（固定夹具自检）→ "
          "筛出候选并按归因四枚举组织 → 输出五段结论。复跑命令见 method_notes.md。", ""]
    return "\n".join(L)


def _r(v):
    return None if v is None else round(v, 6)


def _fence(vals):
    lo, hi = EN.fence(vals)
    return [_r(lo), _r(hi)]
