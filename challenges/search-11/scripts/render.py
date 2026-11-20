#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patent-search-dossier / render.py

六件产物渲染：dossiers.md、number_registry.json、family_graph.json、
status_provenance.csv、license_gate.md、boundary_log.json。纯标准库、不依赖 CWD。
"""
import csv
import os
import re
from pathlib import Path

import registry as R

VERSION = R.VERSION


# ---------------------------------------------------------------- 号码登记簿
def number_registry(draft, idx, ctx):
    entries, seen = [], set()
    cand = {c["norm"]: c for c in R.al(idx.get("number_candidates"))}
    for n in R.al(draft.get("number_decisions")):
        calc = R.normalize_number(n.get("raw"))
        key = n.get("norm") or calc["norm"]
        if key in seen:
            continue
        seen.add(key)
        c = cand.get(key, {})
        entries.append({"raw": n.get("raw"), "norm": key, "country": calc["country"],
                        "kindcode": calc["kindcode"], "serial": calc["serial"], "year": calc["year"],
                        "doc_type": n.get("doc_type") or calc["doc_type"],
                        "parse_status": n.get("parse_status") or calc["parse_status"],
                        "decision": n.get("decision") or "unreviewed",
                        "rules": calc["rules"], "note": n.get("note"),
                        "located_at": (["%s/%s" % (c["source_id"], c["locator"])] if c.get("source_id") else []),
                        "context": c.get("context")})
    for c in R.al(idx.get("number_candidates")):
        if c["norm"] in seen or len(entries) >= 60:
            continue
        calc = R.normalize_number(c["raw"])
        entries.append({"raw": c["raw"], "norm": c["norm"], "country": c["country"],
                        "kindcode": c["kindcode"], "serial": calc["serial"], "year": calc["year"],
                        "doc_type": c["doc_type"], "parse_status": c["parse_status"],
                        "decision": "index_only", "rules": calc["rules"],
                        "note": "索引候选，工作稿未确认",
                        "located_at": ["%s/%s" % (c["source_id"], c["locator"])],
                        "context": c.get("context")})
        seen.add(c["norm"])
    return {"skill": R.SKILL_NAME, "version": VERSION, "case_id": ctx.get("case_id"),
            "generated_at": ctx.get("now"), "rule_version": "number-rules/1.0",
            "rules": {"strip": "去空格/逗号/点/连字符，NFKC 归一",
                      "country": "前缀二字母国别码；PCT 前缀归 WO",
                      "kindcode": "尾部 kind code（A1/B2/U…），剩余长度≥5 才剥离",
                      "us": "11 位且前 4 位为 1960–2035 年 → 公开号；含 / 且 7–8 位 → 申请号；7–8 位 → 授权号",
                      "wo": "10–11 位 → 年份 4 位 + 序号",
                      "inference": "无国别时按位数推断 US，parse_status=ambiguous"},
            "counts": {"entries": len(entries),
                       "parsed": sum(1 for e in entries if e["parse_status"] == "parsed"),
                       "ambiguous": sum(1 for e in entries if e["parse_status"] == "ambiguous"),
                       "unparsed": sum(1 for e in entries if e["parse_status"] == "unparsed")},
            "entries": entries}


# ---------------------------------------------------------------- 族图
def family_graph(draft, idx, ctx):
    objs = R.al(draft.get("patent_objects"))
    nodes = [{"id": o.get("patent_id"), "number_norm": o.get("number_norm"),
              "title": o.get("title"), "screening": o.get("screening")} for o in objs]
    edges = [{"from": e.get("from"), "to": e.get("to"), "link_type": e.get("link_type"),
              "family_scope": e.get("family_scope"), "evidence_locator": e.get("evidence_locator"),
              "quote": e.get("quote"), "claim_scope_note": e.get("claim_scope_note")}
             for e in R.al(draft.get("family_edges"))]
    parent = {n["id"]: n["id"] for n in nodes if n.get("id")}

    def find(x):
        seen = 0
        while parent.get(x, x) != x and seen < 50:
            x = parent[x]
            seen += 1
        return x

    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    groups = {}
    for n in nodes:
        key = find(n["id"]) if n.get("id") in parent else n.get("id")
        groups.setdefault(key, []).append(n.get("id"))
    works = [{"work_id": "W%d" % i, "members": sorted(v), "family_scope": "extended",
              "not_exhaustive": True,
              "claim_scope_note": "仅按材料可见链接归并；不推定各成员权利要求范围等同"}
             for i, (k, v) in enumerate(sorted(groups.items(), key=lambda kv: str(kv[0])), 1)]
    return {"skill": R.SKILL_NAME, "version": VERSION, "case_id": ctx.get("case_id"),
            "generated_at": ctx.get("now"),
            "scope_policy": {"simple": "同优先权可推定同一简单族",
                             "extended": "仅 observed 链接（续案/分案/指定国），不推定权利要求等同",
                             "not_exhaustive": "观察到的族可能不完整，一律为 true"},
            "nodes": nodes, "edges": edges, "works": works,
            "counts": {"nodes": len(nodes), "edges": len(edges), "works": len(works),
                       "not_exhaustive": True}}


# ---------------------------------------------------------------- 状态来源表
def status_rows(draft, ctx):
    rows = []
    for s in R.al(draft.get("status_entries")):
        sk = s.get("source_kind")
        conf = s.get("confidence") or ("high" if sk == "official_register" else
                                       "medium" if sk == "facsimile_ocr" else "low")
        rows.append({"patent_id": s.get("patent_id"), "status_value": s.get("value") or "unknown",
                     "as_of": s.get("as_of"), "query_date": s.get("as_of") or ctx.get("today"),
                     "source_kind": sk, "source_id": s.get("source_id"),
                     "locator": s.get("locator"), "confidence": conf,
                     "needs_official_verification": str(bool(s.get("needs_official_verification"))).lower(),
                     "note": R.norm_ws(s.get("note"))[:200]})
    return rows


def write_status_csv(path, rows):
    cols = ["patent_id", "status_value", "as_of", "query_date", "source_kind", "source_id",
            "locator", "confidence", "needs_official_verification", "note"]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in (rows or [{"patent_id": "", "status_value": "unknown",
                            "note": "无状态条目（降级）"}]):
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    os.replace(tmp, p)
    return len(rows)


# ---------------------------------------------------------------- 许可闸门
def license_gate(draft, idx, ctx):
    lic = R.al(draft.get("license_decisions"))
    tiers = {str(l.get("source_id")): l for l in lic}
    mats = [m for m in idx.get("materials", []) if "license" in (m.get("roles") or {})]
    L = ["# 许可闸门（license_gate）", "",
         "> 案件 `%s` ｜ 生成 %s ｜ 依据：材料许可表 + 工作稿判定" % (ctx.get("case_id"), ctx.get("now")),
         "",
         "分级口径：green=材料明确允许检索与展示；yellow=允许内部/有限展示，只给结论与字段名；"
         "red=需登录/受限/保密，不抓取、不展示原文，只记录已排除。", "",
         "| 来源 | 库名/版本 | 分级 | 可展示字段范围 | 降级方案 | 排除出主结果 | 依据 |",
         "|---|---|---|---|---|---|---|"]
    for l in lic:
        L.append("| %s | %s | **%s** | %s | %s | %s | %s |" % (
            l.get("source_id") or "-", R.norm_ws(l.get("source_name")) or "-",
            str(l.get("tier") or "yellow").upper(),
            R.norm_ws(l.get("display_scope")) or "按材料声明",
            R.norm_ws(l.get("degrade_plan")) or "受限则仅给定位与结论",
            "是" if l.get("excluded_from_output") else "否",
            R.norm_ws(l.get("reason"))[:160] or "-"))
    for m in mats:
        if m["id"] not in tiers:
            L.append("| %s | %s | YELLOW | 未分级（保守默认） | 仅给结论与字段名 | 是 | 工作稿未分级 |"
                     % (m["id"], m["rel"]))
    excluded = [l for l in lic if l.get("excluded_from_output") or l.get("tier") == "red"]
    L += ["", "## 被排除的数据与原因", ""]
    if excluded:
        for l in excluded:
            L.append("- `%s`（%s）：%s" % (l.get("source_id"), str(l.get("tier")).upper(),
                                          R.norm_ws(l.get("reason")) or "受限来源，未展示原文"))
    else:
        L.append("- 无（所有来源均可按声明范围展示）")
    unknown = [m["rel"] for m in mats if m["id"] not in tiers]
    L += ["", "## 未声明许可的来源", "",
          "- " + ("、".join("`%s`" % x for x in unknown) if unknown else "无"), "",
          "## 边界", "",
          "- 本闸门依据材料声明，不构成法律意见；材料未声明时按保守（yellow/red）处理并进 gaps。",
          "- 受限来源的原文、影印件片段与权利要求长段不得进入主结果，只保留来源种类与定位。"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- 边界日志
def boundary_log(draft, idx, ctx):
    bs = R.al(draft.get("boundaries"))
    by = {}
    for b in bs:
        by.setdefault(str(b.get("type")), []).append(b)
    auto = []
    for m in idx.get("materials", []):
        if m.get("ocr") == "noisy":
            auto.append({"type": "ocr_noise", "item": m["id"], "material": m["rel"],
                         "detail": "OCR 文本含噪声，逐字引文可能需容错匹配",
                         "impact": "该来源引文按 OCR 容错（≥0.90）核验，需对照原页"})
    entries = [{"index": i + 1, "type": b.get("type"), "item": b.get("item"),
                "detail": R.norm_ws(b.get("detail")), "impact": R.norm_ws(b.get("impact")),
                "source": "draft"} for i, b in enumerate(bs)]
    entries += [dict(a, source="index") for a in auto]
    return {"skill": R.SKILL_NAME, "version": VERSION, "case_id": ctx.get("case_id"),
            "generated_at": ctx.get("now"),
            "type_dictionary": ["legal_status_unknown", "family_not_exhaustive", "ocr_merged_page",
                                "claim_scope_unexplained", "patent_vs_paper_scope", "license_restricted",
                                "metadata_missing", "coverage_gap", "ocr_noise"],
            "by_type": {k: len(v) for k, v in by.items()},
            "counts": {"entries": len(entries), "types": len(by)},
            "entries": entries,
            "conflicts": R.al(draft.get("conflicts")), "gaps": R.al(draft.get("gaps")),
            "note": "边界声明用于限定结论适用范围；未列出的未知项不得当作已知。"}


# ---------------------------------------------------------------- 风险与摘要
def risk_register(draft):
    out = []
    for s in R.al(draft.get("status_entries")):
        if s.get("needs_official_verification"):
            out.append({"risk_id": "K%d" % (len(out) + 1),
                        "item": "%s 法律状态待官方核验" % s.get("patent_id"), "level": "high",
                        "why": "来源 %s 非官方登记" % s.get("source_kind"),
                        "evidence": "%s/%s" % (s.get("source_id"), s.get("locator")),
                        "action": "回官方登记库核对并记录查询日期"})
    for b in R.al(draft.get("boundaries")):
        if str(b.get("type")) in ("ocr_merged_page", "license_restricted", "family_not_exhaustive"):
            out.append({"risk_id": "K%d" % (len(out) + 1), "item": b.get("item") or b.get("type"),
                        "level": "medium", "why": R.norm_ws(b.get("detail"))[:160],
                        "evidence": b.get("type"), "action": "按边界声明限定结论适用范围"})
    for g in R.al(draft.get("gaps")):
        out.append({"risk_id": "K%d" % (len(out) + 1), "item": g.get("item"), "level": "medium",
                    "why": R.norm_ws(g.get("why"))[:160], "evidence": "-",
                    "action": "在 %s 前补齐" % (g.get("needed_by") or "交付前")})
    if not out:
        out.append({"risk_id": "K1", "item": "未登记风险", "level": "low",
                    "why": "工作稿未声明不确定性", "evidence": "-", "action": "人工复核结论范围"})
    return out


def summary_text(draft, rep, reg):
    c = rep["counts"]
    se = R.al(draft.get("status_entries"))
    unk = sum(1 for s in se if str(s.get("value")) == "unknown")
    need = sum(1 for s in se if s.get("needs_official_verification"))
    red = sum(1 for l in R.al(draft.get("license_decisions")) if l.get("tier") == "red")
    parsed = (reg.get("counts") or {}).get("parsed", 0)
    pend = (reg.get("counts") or {}).get("ambiguous", 0) + (reg.get("counts") or {}).get("unparsed", 0)
    return ("在材料范围内定位专利对象 %d 件、号码登记 %d 条（已解析 %d / 待定 %d）、"
            "同族边 %d 条（not_exhaustive）、权利要求摘录 %d 条、技术文献 %d 篇；"
            "法律状态登记 %d 条，其中 unknown %d 条、需官方复核 %d 条；受限来源 %d 个已排除出主结果。"
            "证据逐字或容错命中 %d/%d（%.0f%%）。结论仅限材料可见证据，未做侵权/FTO/价值判断。"
            % (c["patents"], c["numbers"], parsed, pend, c["edges"], c["claims"], c["papers"],
               c["status"], unk, need, red, c["evidence_verified"], c["evidence_total"],
               100 * (c["evidence_ratio"] or 0)))


# ---------------------------------------------------------------- 主产物
def render_dossiers(draft, idx, rep, ctx):
    q = draft.get("query") or {}
    c = rep["counts"]
    L = ["# 检索案件档案：%s" % (ctx.get("title") or ctx.get("case_id") or "未命名案件"), "",
         "> 案件 `%s` ｜ Skill `%s` v%s ｜ 生成 %s ｜ 状态 **%s** ｜ 检索类型 `%s` ｜ 材料 %d 件" % (
             ctx.get("case_id"), R.SKILL_NAME, VERSION, ctx.get("now"), ctx.get("status"),
             q.get("kind"), len(idx.get("materials", []))),
         "> 证据命中 %d/%d（%.0f%%）｜ 号码 %d ｜ 族边 %d ｜ 状态 %d ｜ 权利要求 %d ｜ 技术文献 %d ｜ 边界 %d" % (
             c["evidence_verified"], c["evidence_total"], 100.0 * (c["evidence_ratio"] or 0),
             c["numbers"], c["edges"], c["status"], c["claims"], c["papers"], c["boundaries"]),
         "> 工作稿来源：`%s`。本档案只陈述材料范围内可核验的内容；未知项单列，不作推断。" % ctx.get("draft_source"),
         "",
         "## 1. 检索范围与检索式", "",
         "**检索意图**：%s" % (R.norm_ws(q.get("statement")) or "（工作稿未写）"), "",
         "| 项 | 内容 |", "|---|---|",
         "| 检索类型 | `%s` |" % (q.get("kind") or "-"),
         "| 目标号码 | %s |" % ("、".join("`%s`" % t for t in R.al(q.get("targets"))) or "-"),
         "| 覆盖检索面 | %s |" % ("、".join(R.al(q.get("scope"))) or "-"),
         "| 显式排除 | %s |" % ("、".join(R.al(q.get("excluded"))) or "无"),
         "| 输入标识 | `case_id=%s` ｜ 材料指纹 `%s` |" % (
             ctx.get("case_id"), (idx.get("fingerprint") or {}).get("sha256", "-")),
         ""]

    L += ["## 2. 号码登记簿（raw → norm）", "",
          "| 原始号码 | 规范化 | 类型 | 解析状态 | 规则链 | 材料定位 |", "|---|---|---|---|---|---|"]
    for n in (ctx.get("registry") or {}).get("entries", [])[:40]:
        L.append("| `%s` | `%s` | %s | %s | %s | %s |" % (
            R.norm_ws(n.get("raw")), n.get("norm") or "-", n.get("doc_type"), n.get("parse_status"),
            " → ".join(n.get("rules") or []), "、".join(n.get("located_at") or []) or "-"))
    if not (ctx.get("registry") or {}).get("entries"):
        L.append("| _未解析到号码（降级）_ | - | - | unparsed | - | - |")
    L += ["", "解析规则：去分隔符 → 国别前缀 → 尾部 kind code → 位数判定文书类型；"
              "无国别时按位数推断并标 `ambiguous`，不当作确定号码。", ""]

    L += ["## 3. 案件档案（逐件）", ""]
    objs = R.al(draft.get("patent_objects"))
    if not objs:
        L += ["_材料中未定位到专利对象；见边界日志与 gaps。_", ""]
    for o in objs:
        pid = o.get("patent_id")
        L += ["### %s · `%s`%s" % (pid, o.get("number_norm"),
                                   (" · " + str(o.get("title"))) if o.get("title") else ""), "",
              "| 著录项 | 值 | 来源 |", "|---|---|---|"]
        ev0 = (R.al(o.get("evidence")) or [{}])[0]
        for label, key in (("申请人/权利人", "assignee"), ("申请日", "filing_date"),
                           ("优先权日", "priority_date"), ("IPC/CPC", "ipc"),
                           ("筛选决定", "screening"), ("筛选理由", "why")):
            v = o.get(key)
            if isinstance(v, list):
                v = "、".join(map(str, v))
            L.append("| %s | %s | %s |" % (label, v if v not in (None, "") else "_未提供_",
                                           "%s/%s" % (ev0.get("source_id"), ev0.get("locator"))
                                           if ev0.get("source_id") else "-"))
        for e in R.al(o.get("evidence")):
            L.append("| 证据（逐字） | `%s` | %s/%s |" % (
                R.norm_ws(e.get("quote"))[:160].replace("|", "/"),
                e.get("source_id"), e.get("locator")))
        L += [""]
        st = [s for s in R.al(draft.get("status_entries")) if s.get("patent_id") == pid]
        L += ["**法律状态**（来源分级，不把转载页当登记）", "",
              "| 状态 | as_of | 来源种类 | 来源定位 | 需官方核验 | 说明 |", "|---|---|---|---|---|---|"]
        for s in st:
            L.append("| **%s** | %s | %s | %s/%s | %s | %s |" % (
                s.get("value") or "unknown", s.get("as_of"), s.get("source_kind"),
                s.get("source_id"), s.get("locator"),
                "是" if s.get("needs_official_verification") else "否",
                R.norm_ws(s.get("note"))[:120] or "-"))
        if not st:
            L.append("| unknown | - | - | - | 是 | 未登记，按未知处理 |")
        L += [""]
        cl = [x for x in R.al(draft.get("claims_versions")) if x.get("patent_id") == pid]
        L += ["**权利要求摘录（原文，未解释范围）**", ""]
        for x in cl:
            L += ["> %s" % R.norm_ws(x.get("quote"))[:700], "",
                  "定位 `%s` ｜ 版本 `%s` ｜ OCR 边界：%s" % (
                      x.get("locator"), x.get("version"), x.get("ocr_boundary") or "未声明"), ""]
        if not cl:
            L += ["_未摘录到权利要求原文；见边界 `claim_scope_unexplained`。_", ""]
        fam = [e for e in R.al(draft.get("family_edges")) if pid in (e.get("from"), e.get("to"))]
        L += ["**同族（observed，not_exhaustive）**", ""]
        for e in fam:
            L.append("- `%s` —%s（%s）→ `%s` ｜ 证据 `%s` ｜ %s" % (
                e.get("from"), e.get("link_type"), e.get("family_scope"), e.get("to"),
                e.get("evidence_locator"),
                R.norm_ws(e.get("claim_scope_note"))[:120] or "未做等同推定"))
        if not fam:
            L.append("- 材料未给出该件的族链接；不作推定。")
        L += [""]

    L += ["## 4. 技术主题与技术文献", "",
          "| 文献 | DOI | 年份 | 相关性 | 依据 | 定位 |", "|---|---|---|---|---|---|"]
    for p in R.al(draft.get("technical_papers")):
        L.append("| %s | %s | %s | %s | %s | %s/%s |" % (
            R.norm_ws(p.get("title")) or p.get("paper_id"), p.get("doi") or "-",
            p.get("year") or "-", p.get("relevance") or "-",
            (R.norm_ws(p.get("why_relevant")) or "-")[:160].replace("|", "/"),
            p.get("source_id"), p.get("locator")))
    if not R.al(draft.get("technical_papers")):
        L.append("| _未检索到技术文献_ | - | - | - | 见边界 | - |")
    L += ["", "专利文献与技术文献口径不同：专利按号码/族/分类号定位，技术文献按 DOI/摘要主题匹配，"
              "两者不混排成同一排序（见边界 `patent_vs_paper_scope`）。", ""]

    L += ["## 5. 候选集与筛选依据", ""]
    if objs:
        L += ["| 对象 | 决定 | 理由 |", "|---|---|---|"]
        for o in objs:
            L.append("| `%s` | %s | %s |" % (o.get("number_norm"), o.get("screening") or "include",
                                             (R.norm_ws(o.get("why")) or "-")[:200].replace("|", "/")))
    else:
        L += ["_无候选对象（降级：材料未提供可解析号码）。_"]
    L += [""]

    L += ["## 6. 许可闸门摘要", "", "| 来源 | 分级 | 排除出主结果 | 说明 |", "|---|---|---|---|"]
    for l in R.al(draft.get("license_decisions")):
        L.append("| %s | %s | %s | %s |" % (l.get("source_id"), str(l.get("tier")).upper(),
                                            "是" if l.get("excluded_from_output") else "否",
                                            (R.norm_ws(l.get("reason")) or "-")[:140].replace("|", "/")))
    if not R.al(draft.get("license_decisions")):
        L.append("| _未分级_ | - | - | 全部来源按保守默认处理 |")
    L += ["", "详见 `license_gate.md`：受限来源只记录“已排除 + 原因”，不展示原文。", ""]

    L += ["## 7. 边界与遗漏", "", "| # | 类型 | 条目 | 影响 |", "|---|---|---|---|"]
    for i, b in enumerate(R.al(draft.get("boundaries")), 1):
        L.append("| %d | %s | %s | %s |" % (i, b.get("type"), (R.norm_ws(b.get("item")) or "-")[:80].replace("|", "/"),
                                            (R.norm_ws(b.get("impact")) or "-")[:160].replace("|", "/")))
    if not R.al(draft.get("boundaries")):
        L.append("| - | _未声明_ | 见 boundary_log.json | 结论不可用于决策 |")
    L += ["", "**冲突**：%s" % ("；".join(
        "%s（%s）" % (R.norm_ws(x.get("item")), "、".join(R.al(x.get("sources"))))
        for x in R.al(draft.get("conflicts"))) or "无"), "",
        "**待补**：%s" % ("；".join(
            "%s（原因：%s）" % (R.norm_ws(g.get("item")), R.norm_ws(g.get("why")))
            for g in R.al(draft.get("gaps"))) or "无"), ""]

    L += ["## 8. 复现步骤", "",
          "```bash",
          "python3 scripts/main.py init --input /input --output /app/output --work /app/work",
          "python3 scripts/main.py show",
          "# Agent 阅读材料后写 /app/work/draft.json",
          "python3 scripts/main.py check",
          "python3 scripts/main.py build",
          "python3 scripts/main.py selfcheck",
          "```", "",
          "- 输入指纹：`%s`（文件 %s 个 / %s 字节）" % (
              (idx.get("fingerprint") or {}).get("sha256"), (idx.get("fingerprint") or {}).get("files"),
              (idx.get("fingerprint") or {}).get("bytes")),
          "- 号码规则版本 `number-rules/1.0`；状态口径：非 official_register 一律需官方复核。",
          "- 复核方式：按 `source_id/locator` 回到材料原文；`show --id M2 --grep 权利要求` 可回看。", ""]
    if ctx.get("status_note"):
        L += ["## 9. 运行说明", "", R.norm_ws(ctx["status_note"]), ""]
    return "\n".join(L)
