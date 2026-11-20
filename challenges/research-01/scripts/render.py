#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py - research-01 notebook chapter rendering (deterministic, no timestamps)."""
import json
import re

import parse as P
import check as C
from parse import tok

# --------------------------------------------------------------------------- render

def cut(s, n):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


SL = {"established": "已被证明 / established", "provisional": "有提示性证据 / provisional",
      "contested": "仍有争议 / contested", "undetermined": "无法确定 / undetermined"}


def render_all(draft, idx, data, chk):
    files = {}
    cid = data.get("case_id") or (idx["case"] or {}).get("case_id") or "unknown"
    cov = data["coverage"]
    brief = data["brief"]
    L = []
    L.append("# 第 1 章 研究简报与子问题拆解 / Brief & decomposition\n")
    L.append("## 1.1 研究问题 / Research question\n\n%s\n" % (brief.get("question") or data["question"]))
    L.append("## 1.2 范围与纳排 / Scope, inclusion, exclusion\n")
    L.append("| 项 | 内容 |\n|---|---|")
    L.append("| 范围 | %s |" % (brief.get("scope") or "未声明（材料范围即边界）"))
    for k, lab in (("inclusion", "纳入"), ("exclusion", "排除")):
        v = brief.get(k) or []
        L.append("| %s | %s |" % (lab, "；".join(str(x) for x in v) if v else "未声明"))
    L.append("| 停止条件 | %s |" % ("；".join(str(x) for x in (brief.get("stop_rules") or [])) or "材料遍历完毕"))
    L.append("\n## 1.3 子问题拆解表 / Decomposition\n")
    L.append("| 子问题 | 内容 | 对象 | 机制 | 方法 | 时间范围 | 比较 | 证据要求 | 层次 | 依赖 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for s in data["sqs"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            s.get("sq_id"), cut(s.get("text"), 90), cut(s.get("object"), 40),
            cut(s.get("mechanism"), 40), cut(s.get("method"), 40), cut(s.get("time_scope"), 30),
            cut(s.get("comparison"), 30), cut(s.get("evidence_requirement"), 60),
            s.get("layer"), ",".join(s.get("depends_on") or []) or "-"))
    L.append("\n## 1.4 检索顺序 / Retrieval order\n")
    done = set()
    order = []
    pend = list(data["sqs"])
    while pend and len(order) < 40:
        for s in list(pend):
            if all((x in done) or x not in {p.get("sq_id") for p in pend}
                   for x in (s.get("depends_on") or [])):
                order.append((s.get("sq_id"), "前置" if not s.get("depends_on") else "依赖后置"))
                done.add(s.get("sq_id"))
                pend.remove(s)
        if pend and all(p.get("sq_id") in done for p in pend):
            break
    for i, (sid, kind) in enumerate(order, 1):
        L.append("%d. %s（%s）" % (i, sid, kind))
    L.append("\n依赖项完成后即可并行执行剩余检索；同一材料不重复读取。")
    L.append("\n## 1.5 材料内覆盖估计 / In-material coverage estimate\n")
    L.append("| 子问题 | 命中句数 | 可用来源 |")
    L.append("|---|---|---|")
    for st in data["sq_stats"]:
        L.append("| %s | %d | %s |" % (st["sq_id"], st["hit_sentences"],
                                       ", ".join(st["sources"]) or "无"))
    L.append("\n> 覆盖估计由脚本按子问题关键词逐句匹配得出，只反映**材料内**命中，不代表领域文献覆盖。\n")
    files["notebook/01-brief.md"] = "\n".join(L)

    rows = []
    for st in data["search_steps"]:
        rows.append({"step_id": st.get("step_id"), "action": st.get("action"),
                     "target": st.get("target"), "params": st.get("params"),
                     "result_summary": st.get("result_summary"), "hits": st.get("hits") or [],
                     "status": st.get("status"), "retry_count": st.get("retry_count", 0)})
    files["notebook/02-search-log.jsonl"] = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else "")
    M = ["# 第 2 章 检索与工具调用日志 / Search & tool log\n",
         "可复跑依据：按 `step_id` 顺序重放 `action + target + params`，比对 `hits` 与 `status`。失败步保留不删。\n",
         "| 步 | 动作 | 目标 | 参数 | 结果 | 命中 | 状态 | 重试 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        M.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["step_id"], r["action"], cut(r["target"], 40), cut(r["params"], 60),
            cut(r["result_summary"], 80), ",".join(str(h) for h in r["hits"]) or "-",
            r["status"], r["retry_count"]))
    files["notebook/02-search-log.md"] = "\n".join(M) + "\n"

    cards = [{"finding_id": f["finding_id"], "statement": f.get("statement"),
              "type": f.get("type"), "confidence": f.get("confidence"),
              "sub_question_id": f.get("sub_question_id"), "scope": f.get("scope"),
              "status": f.get("status"), "support": f.get("support") or [],
              "counter": f.get("counter") or []} for f in data["findings"]]
    files["notebook/03-findings/finding-cards.jsonl"] = "\n".join(json.dumps(c, ensure_ascii=False) for c in cards) + ("\n" if cards else "")
    F = ["# 第 3 章 发现卡 / Finding cards\n",
         "每张卡自带支持证据、反证、适用范围与状态；正文只能经卡片引用原文。\n",
         "| 状态 | 张数 |", "|---|---|"]
    for st in P.STATUSES:
        F.append("| %s | %d |" % (st, sum(1 for f in data["findings"] if f.get("status") == st)))
    F.append("")
    if not cards:
        F.append("_（本次运行没有可登记的发现卡：材料为空或工作稿缺失。见 05 与 result.json 的 degradations。）_\n")
    for f in data["findings"]:
        F.append("### %s · %s · %s" % (f["finding_id"], f.get("status"), f.get("confidence")))
        F.append("\n**陈述**：%s\n" % (f.get("statement") or ""))
        F.append("- 类型：%s｜子问题：%s｜适用：%s" % (f.get("type"), f.get("sub_question_id") or "-",
                                                f.get("scope") or "未声明"))
        for role, lab in (("support", "支持"), ("counter", "反证")):
            items = f.get(role) or []
            if not items:
                F.append("- %s：无" % lab)
            for i, it in enumerate(items, 1):
                mark = "✓逐字命中" if it.get("verified") else "✗未逐字命中"
                F.append("- %s %d：`%s` `%s` %s\n  > %s" % (lab, i, it.get("source_id"),
                                                            it.get("locator"), mark,
                                                            it.get("quote")))
        F.append("")
    files["notebook/03-findings/findings-index.md"] = "\n".join(F) + "\n"

    S = ["# 第 4 章 综合备忘录 / Synthesis memo\n",
         "引用规则：只能引用已登记的 `[Fxxx]` 发现卡；强度标注不得高于所引卡片的最高状态。\n"]
    reg = {f["finding_id"]: f for f in data["findings"]}
    if not data["synthesis"]:
        S.append("_（无可合成的段落：工作稿缺失或材料不足。）_\n")
    for i, para in enumerate(data["synthesis"], 1):
        ids = para.get("finding_ids") or []
        S.append("### 4.%d\n\n%s\n" % (i, para.get("paragraph") or ""))
        S.append("> 强度：%s｜引用：%s\n" % (SL.get(para.get("strength_note"), para.get("strength_note")),
                                         "、".join("[%s]" % x for x in ids) or "无"))
    S.append("\n## 回链表 / Traceability\n")
    S.append("| 段落 | 引用卡 | 卡片状态 | 段落强度 | 一致 |")
    S.append("|---|---|---|---|---|")
    rank = {"established": 3, "provisional": 2, "contested": 1, "undetermined": 0}
    for i, para in enumerate(data["synthesis"], 1):
        ids = para.get("finding_ids") or []
        top = max([rank.get(reg[x].get("status"), 1) for x in ids if x in reg] or [0])
        ok = rank.get(para.get("strength_note"), 1) <= top
        S.append("| 4.%d | %s | %s | %s | %s |" % (
            i, "、".join(ids) or "无",
            SL.get(max([reg[x].get("status") for x in ids if x in reg] or ["undetermined"],
                       key=lambda s: rank.get(s, 1))),
            SL.get(para.get("strength_note")), "✓" if ok else "✗ 越级"))
    files["notebook/04-synthesis.md"] = "\n".join(S) + "\n"

    O = ["# 第 5 章 未决问题与研究空白 / Open questions\n",
         "四型：`retrieval_gap`（检索/材料缺口）、`unresolved_conflict`（无法在卡内解决的冲突）、"
         "`method_limitation`（方法或可读性限制）、`scope_limit`（结论范围限制）。每条给依据。\n"]
    for t in P.OQ_TYPES:
        items = [o for o in data["open_questions"] if o.get("type") == t]
        O.append("## %s（%d）\n" % (t, len(items)))
        if not items:
            O.append("- 无\n")
        for o in items:
            O.append("- **%s**：%s\n  - 依据：%s" % (o.get("oq_id") or "-", o.get("description") or "",
                                                o.get("basis") or "未给依据"))
    other = [o for o in data["open_questions"] if o.get("type") not in P.OQ_TYPES]
    if other:
        O.append("\n## 待归类（类型不在词表，需修）\n")
        for o in other:
            O.append("- %s：%s（type=%s）" % (o.get("oq_id"), o.get("description"), o.get("type")))
    if data["conflict_hints"]:
        O.append("\n## 脚本机械提示（待人工/Agent 判定，非结论）\n")
        for h in data["conflict_hints"]:
            O.append("- %s：%s（来源 %s）" % (h["sub_question_id"], h["note"], ", ".join(h["sources"])))
    files["notebook/05-open-questions.md"] = "\n".join(O) + "\n"

    files["appendix/evidence-register.jsonl"] = "\n".join(
        json.dumps(e, ensure_ascii=False) for e in data["evidence"]) + ("\n" if data["evidence"] else "")

    R = ["# 调查笔记本 · 导航 / Notebook index\n",
         "| 项 | 值 |", "|---|---|",
         "| case_id | `%s` |" % cid,
         "| 材料 / 可读 | %d / %d |" % (cov["materials"], cov["materials_read"]),
         "| 记录行 | %d |" % cov["records"],
         "| 子问题 / 已覆盖 | %d / %d |" % (cov["sub_questions"], cov["sub_questions_covered"]),
         "| 发现卡 | %d |" % cov["findings"],
         "| 证据条 / 逐字命中率 | %d / %.0f%% |" % (cov["evidence"], 100 * cov["quote_hit_rate"]),
         "| 检索步骤 | %d |" % cov["search_steps"],
         "| 未决问题 | %d |" % cov["open_questions"],
         "| FIX / WARN | %d / %d |" % (chk["stats"]["fix"], chk["stats"]["warn"]),
         "", "| 章节 | 文件 |", "|---|---|",
         "| 1 研究简报与拆解 | `notebook/01-brief.md` |",
         "| 2 检索与工具日志 | `notebook/02-search-log.jsonl`（阅读版 `.md`）|",
         "| 3 发现卡 | `notebook/03-findings/finding-cards.jsonl`（阅读版 `findings-index.md`）|",
         "| 4 综合备忘录 | `notebook/04-synthesis.md` |",
         "| 5 未决问题 | `notebook/05-open-questions.md` |",
         "| 证据登记 | `appendix/evidence-register.jsonl` |",
         "| 机器结果 | `result.json` |", ""]
    files["notebook/00-README.md"] = "\n".join(R) + "\n"
    return files


def tok(s):
    s = str(s).lower()
    out = set(re.findall(r"[a-z][a-z\-]{3,}", s))
    for w in re.findall(r"[\u4e00-\u9fff]{2,}", s):
        out.update(w[i:i + 2] for i in range(max(1, len(w) - 1)))
    return out


def sq_stats(idx, sqs):
    out = []
    for sq in sqs:
        toks = tok(str(sq.get("text", "")) + " " + str(sq.get("object", "")))
        hits = []
        for m in idx["materials"]:
            for b in m.get("blocks") or []:
                for s in b["sents"]:
                    if len(s["text"]) < 12:
                        continue
                    sc = len(toks & tok(s["text"]))
                    if sc >= 2:
                        hits.append((sc, m["id"], s["text"], bool(C.NEG.search(s["text"]))))
        hits.sort(key=lambda x: -x[0])
        out.append({"sq_id": sq.get("sq_id"), "hit_sentences": len(hits),
                    "sources": sorted({h[1] for h in hits}),
                    "top_hits": [{"source_id": h[1], "text": cut(h[2], 200)} for h in hits[:2]]})
    return out


def conflict_hints(stats):
    hints = []
    for st in stats:
        neg = [h for h in st["top_hits"] if C.NEG.search(h["text"])]
        pos = [h for h in st["top_hits"] if not C.NEG.search(h["text"])]
        if neg and pos and {h["source_id"] for h in neg} != {h["source_id"] for h in pos}:
            hints.append({"sub_question_id": st["sq_id"],
                          "note": "同一子问题下不同来源出现方向相反的陈述，请判定是否构成冲突",
                          "sources": sorted({h["source_id"] for h in st["top_hits"]})})
    return hints


def assemble(draft, idx, chk):
    sqs = draft["sub_questions"]
    sq_text = {s.get("sq_id"): s.get("text") for s in sqs}
    ev, seen = [], set()
    for f in draft["findings"]:
        f.setdefault("support", [])
        f.setdefault("counter", [])
        f["sub_question_text"] = sq_text.get(f.get("sub_question_id"))
        for role in ("support", "counter"):
            for it in f[role]:
                key = (role, it.get("source_id"), it.get("locator"), it.get("quote"))
                if key in seen:
                    continue
                seen.add(key)
                ev.append({"evidence_id": "E%03d" % (len(ev) + 1), "finding_id": f["finding_id"],
                           "role": role, "source_id": it.get("source_id"),
                           "locator": it.get("locator"), "quote": it.get("quote"),
                           "verified": bool(it.get("verified")),
                           "used_by_findings": [f["finding_id"]]})
    for e in ev:
        for f in draft["findings"]:
            if f["finding_id"] == e["finding_id"]:
                continue
            for it in (f.get("support") or []) + (f.get("counter") or []):
                if it.get("quote") == e["quote"] and it.get("source_id") == e["source_id"]:
                    e["used_by_findings"].append(f["finding_id"])
    conflicts = []
    for f in draft["findings"]:
        if f.get("counter"):
            conflicts.append({"finding_id": f["finding_id"], "statement": f.get("statement"),
                              "support": [x.get("quote") for x in f.get("support") or []],
                              "counter": [x.get("quote") for x in f.get("counter") or []],
                              "resolution": f.get("status"),
                              "note": "卡内已登记反证；状态须为 contested/provisional"})
    stats = sq_stats(idx, sqs)
    covered = {f.get("sub_question_id") for f in draft["findings"]}
    src_used = {}
    for f in draft["findings"]:
        for it in (f.get("support") or []) + (f.get("counter") or []):
            src_used.setdefault(it.get("source_id"), set()).add(f["finding_id"])
    sources = [{"source_id": m["id"], "path": m["rel"], "kind": m["kind"],
                "read_method": m["read_method"], "chars": m["chars"],
                "blocks": len(m.get("blocks") or []),
                "sentences": sum(len(b["sents"]) for b in m.get("blocks") or []),
                "used_by_findings": sorted(src_used.get(m["id"], []))}
               for m in idx["materials"]]
    qst = chk["stats"]
    coverage = {
        "sub_questions": len(sqs),
        "sub_questions_covered": len([s for s in sqs if s.get("sq_id") in covered]),
        "materials": len(idx["materials"]),
        "materials_read": sum(1 for m in idx["materials"] if m["text"].strip()),
        "records": len(idx["records"]),
        "findings": len(draft["findings"]),
        "evidence": len(ev),
        "quotes_verified": qst["quotes_verified"],
        "quotes_failed": qst["quotes_failed"],
        "quote_hit_rate": round(qst["quotes_verified"] / max(1, qst["quotes_verified"] + qst["quotes_failed"]), 4),
        "locators_repaired": qst["locators_repaired"],
        "open_questions": len(draft["open_questions"]),
        "search_steps": len(draft["search_log"]),
    }
    unc = []
    for f in draft["findings"]:
        if f.get("confidence") == "low":
            unc.append({"kind": "low_confidence_finding", "ref": f["finding_id"],
                        "detail": "证据强度低，结论只能作线索"})
        for it in f.get("support") or []:
            if it.get("verified") is False:
                unc.append({"kind": "unverified_quote", "ref": f["finding_id"],
                            "detail": "引文未逐字命中，已降级"})
    for s in stats:
        if s["hit_sentences"] == 0:
            unc.append({"kind": "uncovered_sub_question", "ref": s["sq_id"],
                        "detail": "材料内无命中句"})
        elif len(s["sources"]) == 1:
            unc.append({"kind": "single_source", "ref": s["sq_id"],
                        "detail": "仅 %s 支撑" % s["sources"][0]})
    for m in idx["materials"]:
        if m["read_method"] in ("none", "unsupported"):
            unc.append({"kind": "material_not_readable", "ref": m["id"],
                        "detail": "%s read_method=%s" % (m["rel"], m["read_method"])})
    return {"sqs": sqs, "findings": draft["findings"], "evidence": ev, "conflicts": conflicts,
            "search_steps": draft["search_log"], "open_questions": draft["open_questions"],
            "synthesis": draft["synthesis"], "coverage": coverage, "sources": sources,
            "uncertainties": unc, "sq_stats": stats, "conflict_hints": conflict_hints(stats),
            "brief": draft["brief"], "question": draft["brief"].get("question") or P.question_of(idx)}


# --------------------------------------------------------------------------- commands
