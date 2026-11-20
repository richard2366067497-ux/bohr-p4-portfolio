#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py :: human-readable products (scope card, gap atlas, supplement plan, coverage report)."""
import json

import ledger as L
from audit import POLICIES, FIXTXT, fmt_wins

V = "1.0.0"


# ------------------------------------------------------------------- products
def scope_card(st, cov, variants, rows, cx):
    refs = st["refs"]
    flags = {}
    for r in refs:
        for f in (r.get("flags") or []):
            flags[f] = flags.get(f, 0) + 1
    nmiss = cov["miss_count"]
    L_ = []
    A = L_append = L_.append
    A("# 口径卡 · 检索覆盖率与遗漏分析")
    A("")
    A("- case_id: `%s`" % (st.get("case_id") or "（未提供）"))
    A("- skill: search-coverage-gap-auditor v%s（确定性产物：同一输入重复运行结果一致，不含时间戳）" % V)
    A("- 参考集冻结指纹: `%s`（sha256 前缀；指纹变化即口径不可比）" % (st.get("refset_fingerprint") or "-"))
    A("- 参考集来源文件: %s" % (", ".join(sorted({(r.get("path") or r.get("origin") or "?").split(":")[0] for r in refs}))[:400] or "（无参考集）"))
    A("")
    A("## 1. 研究问题与检索范围")
    A("")
    A(st.get("research_question") or "（工作稿未给出研究问题；以下口径按材料推断，需人工确认）")
    A("")
    A("- 时间窗（来自查询日志）: %s" % fmt_wins(cx["wins"]))
    A("- 检索字段（来自查询日志）: %s" % (", ".join(cx["fields"]) or "未声明"))
    A("- 声明来源: %s" % (", ".join(cx["sources"]) or "未声明"))
    A("- 查询式条数: %d（%s）" % (len(cx["queries"]), ", ".join(cx["qids"][:12]) or "-"))
    A("")
    A("## 2. 参考集构成")
    A("")
    A("| 项 | 值 |")
    A("|-|-|")
    A("| 参考集条目（去重后） | %d |" % len(refs))
    A("| 重复合并计数 | %d |" % sum(len(r.get("dups") or []) for r in refs))
    A("| 不可用条目 | %d |" % sum(1 for r in refs if not r["usable"]))
    A("| 标记分布 | %s |" % (", ".join("%s=%d" % kv for kv in sorted(flags.items())) or "无"))
    A("")
    A("不可用条目单列（不参与默认分母，但保留在台账中）：")
    A("")
    for r in refs:
        if not r["usable"]:
            A("- `%s` %s —— %s" % (r["ref_id"], L.clip(r.get("title"), 90), r["usability_reason"]))
    if all(r["usable"] for r in refs):
        A("- （无）")
    A("")
    A("## 3. 分母口径（三套同时给出，选定一套为准）")
    A("")
    A("| 口径 | 分母 | 命中 | 覆盖率 | 说明 |")
    A("|-|-|-|-|-|")
    for k in POLICIES:
        v = variants[k]
        A("| `%s` | %d | %d | %s | %s |" % (k, v["denominator"], v["numerator"],
                                            ("%.4f" % v["coverage"]) if v["coverage"] is not None else "n/a",
                                            {"all": "含重复与不可用条目", "dedup_only": "去重但含不可用",
                                             "dedup_exclude_unavailable": "去重且剔除 retracted/no_fulltext"}[k]))
    A("")
    A("**选定口径**: `%s` —— %s" % (cov["policy"], st.get("policy_reason") or "默认口径（剔除撤稿/无全文条目），保证分母只含'应当被检索到'的原始研究。"))
    A("")
    A("## 4. 公式")
    A("")
    A("$$\\mathrm{coverage}=\\frac{|\\mathrm{hit}\\cap S_{\\mathrm{policy}}|}{|S_{\\mathrm{policy}}|},\\qquad \\mathrm{miss\\_rate}=1-\\mathrm{coverage}$$")
    A("")
    A("分子 id 列表见 `audit_trail.json:numerator_ids`，分母见 `denominator_ids`；`hit_ledger.csv` 可独立重算。")
    A("")
    A("## 5. 命中判定规则（三级）")
    A("")
    A("| 级别 | rule | 条件 | 置信 |")
    A("|-|-|-|-|")
    A("| L1 | `id_doi` / `id_pmid` | DOI 归一后相等，或 PMID/PMCID 相等 | high |")
    A("| L2 | `bib_title_author_year` / `bib_title_year` | 题名相似度 ≥0.92 且（姓氏命中或年份差 ≤1） | high/medium |")
    A("| L3 | `bib_borderline` | 题名相似度 0.80–0.92 | low → needs_human |")
    A("| — | `none` | 低于 0.80 | 判为 miss |")
    A("")
    dist = {}
    for r in rows:
        dist[r["match_rule"] or "none"] = dist.get(r["match_rule"] or "none", 0) + 1
    A("本轮规则命中分布: %s" % (", ".join("%s=%d" % kv for kv in sorted(dist.items())) or "-"))
    A("")
    A("判定来源: agent=%d / auto=%d（auto 表示脚本按规则建议、未经人工确认）"
      % (len([r for r in rows if r["decision_source"] == "agent"]), len([r for r in rows if r["decision_source"] == "auto"])))
    A("")
    A("## 6. 必须回答的四个数")
    A("")
    A("| # | 问题 | 值 |")
    A("|-|-|-|")
    A("| 1 | 分母（应被检索到的条目） | **%d** |" % cov["denominator"])
    A("| 2 | 命中几条 | **%d** |" % cov["numerator"])
    A("| 3 | 遗漏几条 | **%d**（另有待裁决 %d、不可用条目 %d 已单列） |" % (cov["miss_count"], cov["pending_count"], len(cov["excluded"])))
    A("| 4 | 补检后仍遗漏几条 | 见 `supplement_plan.md` 与 `gap_atlas.json:residual` |")
    A("")
    A("## 7. 单位与限制")
    A("")
    A("- 计数单位：参考集条目（去重后唯一文献）；一条文献的多条检索记录只计一次命中。")
    A("- 覆盖率只衡量**记录级可见性**，不衡量全文质量、纳排正确性与偏倚。")
    A("- 补检在本地记录池上重放，不等价于远程库实时检索（本 Skill 不联网）。")
    A("- 参考集本身若有偏，覆盖率是'对给定参考集'的覆盖率，不能外推为整体召回。")
    A("")
    return "\n".join(L_) + "\n"


def gap_atlas(st, cov, gaps, clusters, miss_ids):
    covered = set()
    for c in clusters:
        covered |= set(c["ref_ids"])
    uncovered = [m for m in miss_ids if m not in covered]
    return {"refset_fingerprint": st.get("refset_fingerprint"), "policy": cov["policy"],
            "denominator": cov["denominator"], "miss_count": len(miss_ids),
            "category_totals": {c["category"]: c["count"] for c in clusters},
            "cluster_total": len(clusters), "clusters": clusters,
            "residual": [{"ref_id": x, "note": "该条遗漏未归入任何类别（脚本保底），需人工补齐"} for x in uncovered],
            "uncovered_refs": uncovered,
            "coverage_note": "每类均附 evidence（locator + 逐字 quote）与 affected_query_ids；无证据的类别不得进入结论"}


def supplement_md(st, cov, sup, clusters):
    L_ = []
    A = L_.append
    A("# 补检计划与边际收益")
    A("")
    A("口径: `%s`，分母 %d，补检前覆盖率 %.4f。" % (cov["policy"], cov["denominator"],
                                                cov["coverage"] if cov["coverage"] is not None else 0.0))
    A("")
    A("## 1. 补检登记表")
    A("")
    if not sup["rows"]:
        A("_未提出补检：材料未给出可改写的查询式，或全部遗漏属于需换源/数据缺陷。_")
    else:
        A("| # | 目标遗漏类 | 新查询式 | 字段/时间窗 | 预期新增 | 实际新增 | 新记录 | 边际收益 | 累计覆盖率 | 空转 |")
        A("|-|-|-|-|-|-|-|-|-|-|")
        for i, r in enumerate(sup["rows"], 1):
            A("| %d | `%s` | `%s` | %s / %s | %s | **%d** | %d | %.2f | %s | %s |" % (
                i, r.get("target_gap") or "-", L.clip(r.get("planned_query"), 80),
                L.clip(r.get("fields"), 20) or "-", L.clip(r.get("window"), 14) or "-",
                r.get("expected_new") if r.get("expected_new") is not None else "-",
                r.get("actual_new_hits") or 0, r.get("new_records") or 0, r.get("marginal_yield") or 0.0,
                ("%.4f" % r["cumulative_coverage_after"]) if r.get("cumulative_coverage_after") is not None else "-",
                "⚠ 空转" if r.get("no_gain") else ("⚠ 无新词项" if r.get("redundant") else "否")))
        A("")
        A("实际新增命中 id: %s" % (", ".join(sorted({x for r in sup["rows"] for x in (r.get("new_ref_ids") or [])})) or "无"))
        A("")
        A("空转说明: 若 `实际新增=0 且 新记录=0`，该补检**不得**计入遗漏下降；标 ⚠无新词项 表示该查询的词项全部来自既有查询式（仅做同义/窗口调整），收益需靠窗口或字段变化解释。")
    A("")
    A("## 2. 边际收益")
    A("")
    A("| 指标 | 值 |")
    A("|-|-|")
    A("| 补检查询数 | %d |" % sup["queries"])
    A("| 新增命中条目 | %d |" % sup["total_new_hits"])
    A("| 边际收益（条/查询） | %.3f |" % sup["marginal_yield"])
    A("| 覆盖率 before → after | %s → %s |" % (
        ("%.4f" % sup["coverage_before"]) if sup["coverage_before"] is not None else "-",
        ("%.4f" % sup["coverage_after"]) if sup["coverage_after"] is not None else "-"))
    A("| 残余遗漏 | %d |" % sup["residual_count"])
    A("")
    A("## 3. 停止理由")
    A("")
    A(sup["stop_reason"])
    A("")
    A("停止阈值定义: 累计边际收益 ≤ 0.5 条/查询，或剩余遗漏全部属于 `needs_new_source`/`data_defect`。")
    A("")
    A("## 4. 残余遗漏声明")
    A("")
    if not sup["residual_ids"]:
        A("- 无残余遗漏（在该参考集与该口径下）。")
    else:
        cat = {}
        for g in (st.get("gaps") or []):
            for rid in g["ref_ids"]:
                cat.setdefault(rid, g["category"])
        for rid in sup["residual_ids"]:
            A("- `%s` —— 残余原因 `%s`：本地材料内无可用查询式或来源可覆盖。" % (rid, cat.get(rid, "未归类")))
    A("")
    return "\n".join(L_) + "\n"


def report_md(st, cov, variants, rows, gaps, clusters, sup):
    refs = st["refs"]
    L_ = []
    A = L_.append
    A("# 检索覆盖率与遗漏分析报告")
    A("")
    A("case_id: `%s` ｜ 参考集指纹: `%s` ｜ 口径: `%s`" % (st.get("case_id") or "（未提供）",
                                                    st.get("refset_fingerprint") or "-", cov["policy"]))
    A("")
    A("## 1. 结论摘要")
    A("")
    if cov["denominator"]:
        A("- 分母 **%d** 条（冻结参考集，去重后%s），命中 **%d**，遗漏 **%d**。"
          % (cov["denominator"], "剔除不可用条目" if cov["policy"] == "dedup_exclude_unavailable" else "",
             cov["numerator"], cov["miss_count"]))
        A("- 覆盖率 **%.2f%%**，遗漏率 **%.2f%%**；分子/分母 id 列表见 `audit_trail.json`。"
          % (100 * (cov["coverage"] or 0), 100 * (cov["miss_rate"] or 0)))
    else:
        A("- 分母为 0：**未提供可用参考集，覆盖率未定义**（不以检索结果反推分母）。")
    A("- 遗漏集中在 %d 类：%s。" % (len(clusters),
                                 "、".join("`%s`(%d)" % (c["category"], c["count"]) for c in clusters) or "无"))
    if sup["queries"]:
        A("- 补检 %d 条，新增命中 %d，覆盖率 %s → %s，边际收益 %.2f 条/查询；残余遗漏 %d。"
          % (sup["queries"], sup["total_new_hits"],
             ("%.4f" % sup["coverage_before"]) if sup["coverage_before"] is not None else "-",
             ("%.4f" % sup["coverage_after"]) if sup["coverage_after"] is not None else "-",
             sup["marginal_yield"], sup["residual_count"]))
    else:
        A("- 未提出补检，残余遗漏 %d 条（见 §5）。" % sup["residual_count"])
    A("")
    A("## 2. 口径与可复算入口")
    A("")
    A("| 项 | 值 |")
    A("|-|-|")
    for k in POLICIES:
        v = variants[k]
        A("| `%s` | 分母 %d / 命中 %d / 覆盖率 %s |" % (k, v["denominator"], v["numerator"],
                                                     ("%.4f" % v["coverage"]) if v["coverage"] is not None else "n/a"))
    A("")
    A("复算路径：`hit_ledger.csv` 中 `usable=True` 且 `hit_status=hit` 的行数 = 分子；同口径行数 = 分母；"
      "`audit_trail.json:recompute` 给出脚本独立重算值与是否一致。完整规则见 `scope_card.md`。")
    A("")
    A("## 3. 命中台账摘要")
    A("")
    A("| ref_id | 年份 | 命中状态 | 规则 | 置信 | 证据 locator |")
    A("|-|-|-|-|-|-|")
    for r in rows[:60]:
        A("| `%s` | %s | %s | %s | %s | `%s` |" % (r["ref_id"], r["year"] or "-", r["hit_status"],
                                                 r["match_rule"] or "-", r["certainty"], r["evidence_locator"] or "-"))
    if len(rows) > 60:
        A("")
        A("_（其余 %d 行见 `hit_ledger.csv`）_" % (len(rows) - 60))
    A("")
    A("## 4. 遗漏图谱")
    A("")
    if not clusters:
        A("_无遗漏条目。_")
    else:
        A("| 类别 | 条数 | 可修复性 | 受影响查询 | 判定依据（摘） |")
        A("|-|-|-|-|-|")
        for c in clusters:
            A("| `%s` | %d | %s | %s | %s |" % (c["category"], c["count"], c["fixability"],
                                               ", ".join(c["affected_query_ids"][:4]) or "-",
                                               L.clip(c["verdict"], 120)))
        A("")
        A("逐条证据（locator + 逐字 quote）见 `gap_atlas.json:clusters[].evidence`；逐条分类见 `gap_matrix.csv`。")
    A("")
    A("## 5. 逐条遗漏")
    A("")
    if not gaps:
        A("_无。_")
    else:
        A("| ref_id | 主因 | why | 证据 locator |")
        A("|-|-|-|-|")
        for g in gaps:
            for rid in g["ref_ids"]:
                A("| `%s` | `%s` | %s | `%s` |" % (rid, g["category"], g["why"],
                                                   (g["evidence"][0]["locator"] if g["evidence"] else "-")))
    A("")
    A("## 6. 补检与边际收益")
    A("")
    if not sup["rows"]:
        A("_未提出补检。_")
    else:
        A("| 目标类 | 新查询式 | 实际新增 | 边际收益 | 累计覆盖率 |")
        A("|-|-|-|-|-|")
        for r in sup["rows"]:
            A("| `%s` | `%s` | %d | %.2f | %s |" % (r.get("target_gap"), L.clip(r.get("planned_query"), 70),
                                                   r.get("actual_new_hits") or 0, r.get("marginal_yield") or 0.0,
                                                   ("%.4f" % r["cumulative_coverage_after"]) if r.get("cumulative_coverage_after") is not None else "-"))
        A("")
        A("停止理由: %s" % sup["stop_reason"])
    A("")
    A("## 7. 不确定性与限制")
    A("")
    for x in (st.get("uncertainty") or [])[:12]:
        A("- %s" % (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)))
    if not st.get("uncertainty"):
        A("- 未记录额外不确定性；低置信命中与待裁决行见台账 `needs_human` 列。")
    A("- 覆盖率针对**给定参考集**，不构成对整体文献世界的召回率。")
    A("- 补检为本地记录池重放，非远程实时检索。")
    A("")
    return "\n".join(L_) + "\n"


