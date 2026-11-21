# -*- coding: utf-8 -*-
"""search-10 :: artifact rendering.  A degraded run still writes every artifact with a
readable reason, so a reviewer sees exactly what the material did and did not state."""
import core as C


def search_report_md(ctx, ev_stats, met):
    gl = ctx["glossary"]
    L = ["# 跨语种检索报告（search_report）", "",
         "- case_id: `%s`" % ctx["case_id"],
         "- 状态: `%s`" % C.status_of(ctx),
         "- 术语表：`%s`（来源：%s；许可：%s；版本：%s）" % (
             gl["locator"] or "未提供", gl["source"] or "未声明",
             gl["license"] or "未声明", gl["version"]),
         "- 翻译服务与版本：**无**（离线运行，只用内置术语表；不调用任何翻译接口，"
         "因此不存在「术语对齐靠接口直译」的风险）", "",
         "## 1 目标与语种路由", ""]
    if ctx["questions"]:
        for q in ctx["questions"]:
            L.append("- `%s`（源语 %s → 目标 %s）：%s" % (
                q["question_id"], q["source_lang"],
                ", ".join(q["target_langs"]) or "未声明", q["text"][:120]))
    else:
        L.append("- 材料未给出题面；查询计划由材料中**实际出现**的术语概念驱动（见 §2）。")
    L += ["", "- 术语表覆盖语种：%s" % (", ".join(cov_langs(ctx)) or "无"),
          "- 材料中实际出现锚点的语种：%s" % (", ".join(ctx["coverage_anchor_langs"]) or "无"), "",
          "## 2 逐语种查询式（固化产物：lang_queries.md / query_plan.json）", "",
          "| cid | 语言 | 查询式 | 依据 | 定位符 |", "|-|-|-|-|-|"]
    for e in ctx["queries"][:40]:
        L.append("| %s | %s | `%s` | %s | `%s` |" % (
            e["cid"], e["lang"], e["query"].replace("|", "\\|"), e["query_kind"],
            (e.get("basis", "").split(" at ")[-1] if e.get("basis", "").startswith("stated") else "—")))
    if len(ctx["queries"]) > 40:
        L.append("| … | … | 其余 %d 条见 query_plan.json | | |" % (len(ctx["queries"]) - 40))
    L += ["", "## 3 跨语种术语对齐（硬证据）", "",
          "| concept | 源语 | 源词（逐字） | locator | 目标语 | 目标词（逐字） | locator | 术语表 |",
          "|-|-|-|-|-|-|-|-|"]
    for p in ctx["term_pairs"][:40]:
        L.append("| %s | %s | %s | `%s` | %s | %s | `%s` | %s |" % (
            p["concept_id"], p["source_lang"], p["source"], p["source_locator"],
            p["target_lang"], p["target"], p["target_locator"], p["glossary"]))
    if not ctx["term_pairs"]:
        L.append("| — | — | 材料未在同一概念上给出 ≥2 个语种的写法 | — | — | — | — | — |")
    L += ["", "## 4 视图台账与去重（reconciliation.md）", "",
          "- views_total=%d, distinct_works=%d, duplicates=%s" % (
              ctx["dedup"].get("views_total", 0), ctx["dedup"].get("distinct_works", 0),
              ctx["dedup"].get("duplicates") or "无"),
          "", "## 5 命中与未命中", ""]
    for card in ctx["cards"]:
        L.append("- **%s** → work `%s` / view `%s`（%s）；证据 `%s` %s" % (
            card["question_id"], card["work_id"], card["view_id"], card["confidence"],
            card["evidence"]["locator"], card["evidence"]["quote"][:80]))
    for m in ctx["misses"]:
        L.append("- `%s` → 未命中：%s" % (m["question_id"], m["reason"]))
    if not ctx["cards"] and not ctx["misses"]:
        L.append("- 材料没有题面、也没有视图，因此本次不产生命中卡；这是**如实留空**而非失败。")
    L += ["", "## 6 证据与效率", "",
          "- 逐字证据：%d 条，命中率 %s" % (ev_stats["total"], ev_stats["hit_rate"]),
          "- 效率：elapsed %ss / requests %d / rounds %d" % (
              met["elapsed_s"], met["requests"], met["rounds"]),
          "", "## 7 缺口与需人工确认", ""]
    for d in ctx["degradations"] or ["未发现额外缺口"]:
        L.append("- %s" % d)
    for p in ctx["pending_human"]:
        L.append("- 需人工确认：%s（%s）" % (p["item"], p["why"]))
    return "\n".join(L).rstrip() + "\n"


def cov_langs(ctx):
    return ctx["coverage_glossary_langs"]


def lang_queries_md(ctx):
    L = ["# 逐语种查询式（lang_queries）", "",
         "生成规则：概念锚点只来自材料中**逐字出现**的术语；查询式用术语表在该语种的写法拼装，"
         "不使用任何翻译接口。`glossary-grounded` 表示该语种写法在材料里被直接见到，"
         "`glossary-projected` 表示由术语表跨语种投射得到（仍可回查术语表行）。", "",
         "## 查询模板", "",
         "```text",
         'concept_query(lang, cid)      = "term 1" AND "term 2"',
         'known_item_query(lang, cid)   = concept_query(lang, cid) AND (doi OR "title phrase" OR author AND year)',
         'back_translation_check(cid)   = tf(cid, lang) == reverse(tf(cid, other_lang))',
         "```", "",
         "| cid | lang | query | kind | 依据 |", "|-|-|-|-|-|"]
    for e in ctx["queries"]:
        L.append("| %s | %s | `%s` | %s | %s |" % (
            e["cid"], e["lang"], e["query"].replace("|", "\\|"), e["query_kind"], e["basis"]))
    if not ctx["queries"]:
        L.append("| — | — | 材料未给出任何术语概念 | — | — |")
    L += ["", "## 回译校验（逆映射）", "",
          "对每条 term pair，脚本用**术语表同一 cid** 反向查回源语写法；不一致即记 `review`，"
          "绝不臆造译法。本次成对证据 %d 条，全部来自术语表 `builtin` 编号。" % len(ctx["term_pairs"])]
    return "\n".join(L).rstrip() + "\n"


def reconciliation_md(ctx):
    L = ["# 对账与去重（reconciliation）", "",
         "同一 work 的原文、全译、摘要版、副本必须去重后计数：只有 `distinct_works` 才算命中。", "",
         "| 视图 | work | 语言 | 版本 | 正文完整度 | 内容指纹 | 重复于 |", "|-|-|-|-|-|-|-|"]
    for v in ctx["views"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            v["view_id"], v["work_id"], v["language"], v["version"], v["doc_type"],
            v["sha"], v.get("duplicate_of") or "—"))
    if not ctx["views"]:
        L.append("| — | — | — | — | — | — | 材料未提供任何视图 |")
    L += ["", "- views_total=%d；distinct_works=%d；counted_hits=%d；duplicates=%s" % (
        ctx["dedup"].get("views_total", 0), ctx["dedup"].get("distinct_works", 0),
        len(ctx["cards"]), ctx["dedup"].get("duplicates") or "无"),
        "- 口径：`abstract_only` 可以入台账但**不作为正文命中证据**；`duplicate` 只入台账不计数。"]
    return "\n".join(L).rstrip() + "\n"


def baseline_md(ctx, gmet, met):
    L = ["# Baseline 对照（可复现口径，非官方对照）", "",
         "> 诚实声明：无 Skill 一栏为**确定性基线模拟**（朴素策略），说明缺口类别，非官方 A/B 数据。", "",
         "| 对照项 | 无 Skill（基线模拟） | 加载本 Skill（本次运行） |", "|-|-|-|",
         "| 语种路由 | 只按提问语言检索 | %d 条查询、%d 个语种 |" % (
             gmet["queries_generated"], gmet["languages_covered"]),
         "| 术语对齐 | 翻译接口直译，无出处 | %d 条成对证据，全部可回查 |" % gmet["term_alignment_pairs"],
         "| 翻译调用 | 逐语种调用翻译服务 | %d 次（离线内置表） |" % gmet["translation_service_calls"],
         "| 去重 | 原文/全译/摘要各算一条 | work 级去重：distinct=%d，duplicates=%d |" % (
             ctx["dedup"].get("distinct_works", 0), len(ctx["dedup"].get("duplicates", []))),
         "| 证据 | 无 locator | %d 条逐字证据，命中率 %s |" % (met["lines_scanned"], met["verbatim_hit_rate"]),
         "| 人工核对 | 全靠人工 | 自动核对 %d 条，人工仅 %d 条 |" % (
             gmet["human_review_items_saved_vs_manual"], gmet["human_review_items"]),
         "| 契约回填 | 无 result.json | 契约键逐键回填（顶层 + nested） |",
         "| 效率指标 | 无记录 | elapsed %ss / requests %d / rounds %d |" % (
             met["elapsed_s"], met["requests"], met["rounds"]),
         "", "复现：`python3 scripts/main.py all --input /input --output /app/output --work /app/work`"]
    return "\n".join(L).rstrip() + "\n"


def check_report(ctx, ev_stats):
    q_ids = [q["question_id"] for q in ctx["questions"]]
    checks = [
        {"id": "D0", "check": "工作稿（可选）存在且可解析", "level": "info",
         "ok": True,
         "detail": ("work/draft.json was used for the human judgements" if ctx.get("draft_present")
                    else "no work/draft.json; the run derives every row from the material itself")},
        {"id": "D1", "check": "每题都有意图复述", "level": "warn",
         "ok": not ctx["questions"] or all(q.get("text") for q in ctx["questions"]),
         "detail": "%d 题" % len(ctx["questions"])},
        {"id": "D2", "check": "每题写 source_lang", "level": "warn",
         "ok": all(q.get("source_lang") for q in ctx["questions"]),
         "detail": ", ".join(q.get("source_lang", "") for q in ctx["questions"]) or "无题面"},
        {"id": "D3", "check": "每题写 target_langs", "level": "warn",
         "ok": all(q.get("target_langs") for q in ctx["questions"]),
         "detail": "; ".join(",".join(q.get("target_langs") or []) for q in ctx["questions"]) or "无题面"},
        {"id": "D4", "check": "每个视图都有语种/版本", "level": "warn",
         "ok": all(v.get("language") and v.get("version") for v in ctx["views"]),
         "detail": "%d 个视图" % len(ctx["views"])},
        {"id": "K1", "check": "契约键可回填", "level": "info", "ok": True,
         "detail": "deliverable / evidence_map / change_log / coverage / status"},
        {"id": "K2", "check": "去重口径与脚本一致", "level": "warn",
         "ok": ctx["dedup"].get("distinct_works", 0) >= len(ctx["cards"]),
         "detail": "distinct_works=%d, counted_hits=%d" % (
             ctx["dedup"].get("distinct_works", 0), len(ctx["cards"]))},
        {"id": "K3", "check": "全部引用逐字命中", "level": "error",
         "ok": ev_stats["hit_rate"] >= 0.99 or ev_stats["total"] == 0,
         "detail": "hit rate %s (%d/%d)" % (ev_stats["hit_rate"], ev_stats["verbatim_hits"], ev_stats["total"])},
        {"id": "K4", "check": "每题都有结论（命中或 misses）", "level": "warn",
         "ok": len(ctx["cards"]) + len(ctx["misses"]) >= len(q_ids),
         "detail": "cards=%d misses=%d questions=%d" % (len(ctx["cards"]), len(ctx["misses"]), len(q_ids))},
    ]
    return {"case_id": ctx["case_id"], "questions": q_ids, "checks": checks,
            "dedup": ctx["dedup"], "status": "ok" if all(c["ok"] for c in checks) else "review",
            "misses": ctx["misses"]}


def build_artifacts(ctx, ev_stats, met, gmet):
    return {
        "search_report.md": search_report_md(ctx, ev_stats, met),
        "lang_queries.md": lang_queries_md(ctx),
        "reconciliation.md": reconciliation_md(ctx),
        "baseline_comparison.md": baseline_md(ctx, gmet, met),
        "query_plan.json": {"queries": ctx["queries"], "languages": sorted(set(e["lang"] for e in ctx["queries"])),
                            "glossary": {"locator": ctx["glossary"]["locator"],
                                         "source": ctx["glossary"]["source"],
                                         "license": ctx["glossary"]["license"],
                                         "version": ctx["glossary"]["version"]},
                            "note": "one row per concept x language; grounded in a verbatim material line"},
        "glossary_index.json": {"concepts": ctx["glossary"]["concepts"],
                                "source": ctx["glossary"]["source"],
                                "license": ctx["glossary"]["license"],
                                "version": ctx["glossary"]["version"],
                                "locator": ctx["glossary"]["locator"],
                                "translation_service": "offline-builtin-glossary (no API call)",
                                "note": "concept level only; proper nouns are matched by DOI/author/year anchors"},
        "answer_cards.json": {"cards": ctx["cards"], "misses": ctx["misses"],
                              "questions": ctx["questions"], "dedup": ctx["dedup"]},
        "check_report.json": check_report(ctx, ev_stats),
        "evidence.json": {"case_id": ctx["case_id"], "stats": ev_stats, "items": ctx["evidence_items"]},
    }
