#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""outline-slot-review 规则层：工作稿模型化 / 校验 / 修补 / 渲染 / 契约回填。
kit 管"怎么读"，本文件管"读出来怎么判"，main 只管命令行与落盘；一切修补都写进 changes。"""
import re

import kit
from kit import GAP_TYPES, ORDER, V

# output_contract 字段 -> 产物（先专有后通用，避免 screening_criteria 被误判为 criteria）
FIELDS = [(r"^(case_?id|案例)$", "case_id"),
          (r"(status|状态)", "status"),
          (r"(criteri|标准)", "criteria"),
          (r"(screen|筛|纳排|prisma|inclusion)", "screening"),
          (r"(outline|提纲|结构|section)", "outline"),
          (r"(slot|evidence|matrix|证据|回链)", "evidence_slots"),
          (r"(gap|blank|空白|缺口)", "gaps"),
          (r"(coverage|metrics?|stats?|statistic|覆盖|计数)", "coverage"),
          (r"(draft|review|manuscript|narrative|综述|草稿|正文|成稿)", "draft"),
          (r"(source|reference|bibliograph|文献|书目|参考)", "sources"),
          (r"(uncertain|conflict|limitation|不确定|冲突|限制)", "uncertainty"),
          (r"(change|revision|版本|变更)", "changes")]


# ------------------------------------------------------------------ 模型化
def s_norm(x):
    x = str(x or "").lower()
    if x in ("strong", "高", "强", "high"):
        return "strong"
    if x in ("moderate", "中", "中等", "medium"):
        return "moderate"
    return "weak"


def pol_norm(x):
    x = str(x or "").lower()
    return "counter" if any(k in x for k in ("counter", "反", "oppos", "against", "对立")) else "supports"


def base(ctx):
    return {"case_id": ctx["cid"], "rq": ctx["rq"], "protocol": {}, "criteria": [], "screening": [],
            "outline": [], "slots": {}, "notes": {}, "outline_basis": "", "lg": ctx["lg"], "authored": False}


def norm(raw, ctx):
    m = base(ctx)
    raw = raw or {}
    m["authored"] = bool(raw) and bool(raw.get("criteria") or raw.get("outline") or raw.get("slots"))
    m["rq"] = str(raw.get("research_question") or raw.get("rq") or m["rq"])[:400]
    m["protocol"] = raw.get("protocol") if isinstance(raw.get("protocol"), dict) else {}
    m["notes"] = raw.get("method_notes") if isinstance(raw.get("method_notes"), dict) else {}
    m["outline_basis"] = str(raw.get("outline_basis") or "")[:600]
    for i, c in enumerate(raw.get("criteria") or [], 1):
        if not isinstance(c, dict):
            continue
        t = str(c.get("type") or "").lower()
        m["criteria"].append({
            "criterion_id": str(c.get("criterion_id") or c.get("id") or "C%d" % i),
            "type": "exclude" if (t.startswith("excl") or "排除" in t) else "include",
            "statement": str(c.get("statement") or c.get("text") or "")[:500],
            "judge_rule": str(c.get("judge_rule") or c.get("rule") or "")[:500],
            "priority": c.get("priority") or i,
            "stage": c.get("stage") if c.get("stage") in kit.STAGE else "title_abstract"})
    seen = set()
    for i, r in enumerate(raw.get("screening") or [], 1):
        if not isinstance(r, dict):
            continue
        rid = str(r.get("record_id") or r.get("id") or "R%02d" % i)
        if rid in seen:
            rid = "%s#%d" % (rid, i)
        seen.add(rid)
        dec = str(r.get("decision") or "").lower()
        dec = ("include" if (dec.startswith("incl") or "纳入" in dec) else
               "exclude" if (dec.startswith("excl") or "排除" in dec) else "pending")
        cc = r.get("criterion_ids") or r.get("criteria") or []
        m["screening"].append({
            "record_id": rid, "source_id": r.get("source_id") or None,
            "stage": r.get("stage") if r.get("stage") in kit.STAGE else "title_abstract",
            "decision": dec, "criterion_ids": [str(x) for x in cc] if isinstance(cc, list) else [],
            "reason": str(r.get("reason") or "")[:600], "locator": str(r.get("locator") or "")})
    used, idmap, seq = set(), {}, [0]

    def newid():
        seq[0] += 1
        return "SL%d" % seq[0]

    for i, sec in enumerate(raw.get("outline") or [], 1):
        if not isinstance(sec, dict):
            continue
        slots = []
        for sl in (sec.get("slots") or []):
            sl = {"claim_prompt": sl} if isinstance(sl, str) else (sl if isinstance(sl, dict) else None)
            if not sl:
                continue
            old = str(sl.get("slot_id") or "")
            nid = old if (old and old not in used) else newid()
            if old and nid != old:
                idmap.setdefault(old, nid)
            used.add(nid)
            slots.append({"slot_id": nid,
                          "claim_prompt": str(sl.get("claim_prompt") or sl.get("prompt") or "")[:400],
                          "required_evidence": str(sl.get("required_evidence") or sl.get("evidence") or "")[:300],
                          "section_label": str(sl.get("section_label") or sec.get("section_label") or "")[:120]})
        m["outline"].append({
            "sec_id": str(sec.get("sec_id") or sec.get("id") or "SEC%d" % i),
            "heading": str(sec.get("heading") or sec.get("title") or "未命名章节")[:200],
            "purpose": str(sec.get("purpose") or "")[:400], "section_label": str(sec.get("section_label") or "")[:120],
            "lead": str(sec.get("lead") or "")[:600],
            "lead_slot_ids": [idmap.get(str(x), str(x)) for x in (sec.get("lead_slot_ids") or []) if str(x)],
            "slots": slots, "slot_ids": [s["slot_id"] for s in slots]})
    declared = {s["slot_id"] for sec in m["outline"] for s in sec["slots"]}
    for i, s in enumerate(raw.get("slots") or [], 1):
        if not isinstance(s, dict):
            continue
        sid = idmap.get(str(s.get("slot_id") or ""), str(s.get("slot_id") or "SL%d" % i))
        refs = []
        for r in (s.get("evidence_refs") or s.get("evidence") or []):
            r = {"quote": r} if isinstance(r, str) else r
            if not isinstance(r, dict):
                continue
            refs.append({"source_id": (str(r.get("source_id")) if r.get("source_id") else None),
                         "locator": str(r.get("locator") or ""), "quote": str(r.get("quote") or "")})
        claim = str(s.get("claim") or "")
        st = str(s.get("state") or "").lower()
        state = "filled" if (st.startswith("fill") or (not st and (claim or refs))) else \
                "gap" if st.startswith("gap") else ("filled" if (claim or refs) else "gap")
        cw = s.get("conflicts_with") or []
        m["slots"][sid] = {
            "slot_id": sid, "state": state, "claim": claim[:1500], "evidence_refs": refs,
            "strength": s_norm(s.get("strength")), "polarity": pol_norm(s.get("polarity")),
            "conflicts_with": [idmap.get(str(x), str(x)) for x in cw] if isinstance(cw, list) else [],
            "gap_reason": str(s.get("gap_reason") or "")[:500], "search_scope": str(s.get("search_scope") or "")[:500],
            "missing_evidence": str(s.get("missing_evidence") or "")[:500],
            "gap_type": str(s.get("gap_type") or ""), "declared": sid in declared}
    for sec in m["outline"]:
        for s in sec["slots"]:
            if s["slot_id"] not in m["slots"]:
                m["slots"][s["slot_id"]] = {
                    "slot_id": s["slot_id"], "state": "gap", "claim": "", "evidence_refs": [],
                    "strength": "weak", "polarity": "supports", "conflicts_with": [],
                    "gap_reason": "工作稿未填写该槽位", "search_scope": "",
                    "missing_evidence": s.get("required_evidence") or "该槽位所需证据",
                    "gap_type": "retrieval_gap", "declared": True}
    return m


def fallback(ctx, why):
    m = base(ctx)
    m["authored"], m["fallback_reason"] = False, why
    srcs = [d for d in ctx["docs"] if d["kind"] == "source"]
    rows = ctx["records"] or [{"record_id": "R%02d" % i, "source_id": d["sid"], "note": d["path"]}
                              for i, d in enumerate(srcs, 1)]
    m["screening"] = [{"record_id": r["record_id"], "source_id": r.get("source_id"), "stage": "title_abstract",
                       "decision": "pending", "criterion_ids": [], "reason": "未执行筛选：" + why,
                       "locator": r.get("note") or ""} for r in rows]
    plan = [("SEC1", "研究问题与纳排范围", "说明本批文献的检索与筛选边界", "scope",
             "纳入/排除条款与逐篇判定", "scope_limit", "未写纳排标准", "未执行（需先写工作稿）"),
            ("SEC2", "文献清单（材料转录）", "给出可回查的元数据与定位，不做论断", "inventory",
             "每篇文献的主要结论与定位", "retrieval_gap", "未提取逐篇结论句", "材料全文逐篇阅读")]
    m["outline"], m["slots"] = [], {}
    for i, (sec, head, pur, lab, miss, gt, gr, scope) in enumerate(plan, 1):
        sl = "SL%d" % i
        m["outline"].append({"sec_id": sec, "heading": head, "purpose": pur, "section_label": lab,
                             "lead": "", "lead_slot_ids": [], "slot_ids": [sl],
                             "slots": [{"slot_id": sl, "claim_prompt": miss, "required_evidence": miss,
                                        "section_label": lab}]})
        m["slots"][sl] = {"slot_id": sl, "state": "gap", "claim": "", "evidence_refs": [], "strength": "weak",
                          "polarity": "supports", "conflicts_with": [], "gap_reason": why + "；" + gr,
                          "search_scope": scope, "missing_evidence": miss, "gap_type": gt, "declared": True}
    return m


# ------------------------------------------------------------------ 校验
def validate(m, ctx):
    I = []

    def add(c, target, msg=None, hint=None):
        meta = kit.CODES.get(c, (c, "WARN", "", ""))
        I.append({"code": c, "level": meta[1], "name": meta[0], "target": target,
                  "message": msg or meta[3], "hint": hint or meta[2]})

    cids = {c["criterion_id"] for c in m["criteria"]}
    if not m["criteria"]:
        add("S101", "criteria")
    elif not any(c["type"] == "include" for c in m["criteria"]):
        add("S101", "criteria", "无 include 条款：标准必须先于筛选写定")
    if not m["screening"]:
        add("S102", "screening")
    for r in m["screening"]:
        for cid in r["criterion_ids"]:
            if cid not in cids:
                add("S103", r["record_id"], "引用未知条款 %s" % cid)
        if r["decision"] in ("exclude", "pending") and not r["criterion_ids"]:
            add("S104", r["record_id"], "决策=%s 但未挂条款" % r["decision"])
        if r["decision"] == "exclude" and not r["reason"]:
            add("S104", r["record_id"], "排除未给 reason")
    have = {r["record_id"] for r in m["screening"]}
    if ctx["records"]:
        miss = [r["record_id"] for r in ctx["records"] if r["record_id"] not in have]
        if miss:
            add("S105", ",".join(miss[:8]), "%d 条记录未出现在筛选记录" % len(miss))
        for r in ctx["records"]:
            if r["duplicate_of"] and r["record_id"] in have and not any(
                    s["record_id"] == r["record_id"] and s["decision"] == "exclude" for s in m["screening"]):
                add("S106", r["record_id"], "重复记录（同源 %s）未排除" % r["duplicate_of"])
        full = {r["record_id"] for r in m["screening"] if r["stage"] == "full_text"}
        ta = {r["record_id"] for r in m["screening"] if r["stage"] == "title_abstract"}
        if full - ta:
            add("S107", ",".join(sorted(full - ta)[:6]), "全文阶段行缺少题录阶段行")
    declared = {s["slot_id"] for sec in m["outline"] for s in sec["slots"]}
    if len(m["outline"]) < 2 or not declared:
        add("O101", "outline", "章节 %d / 槽位 %d" % (len(m["outline"]), len(declared)))
    for sec in m["outline"]:
        if not sec["heading"].strip() or not sec["purpose"].strip():
            add("O102", sec["sec_id"])
        if sec["lead"] and not sec["lead_slot_ids"]:
            add("D101", sec["sec_id"])
    heads = " ".join(s["heading"].lower() for s in m["outline"])
    generic = sum(1 for k in ("背景", "introduction", "method", "方法", "挑战", "challenge", "展望", "future") if k in heads)
    if generic >= 2 and not m["outline_basis"]:
        add("O105", "outline", "标题含 %d 个通用框架词" % generic, "补 outline_basis 说明来自文献分布")
    for sid, s in m["slots"].items():
        if sid not in declared:
            add("O103", sid, "槽位未在 outline 声明")
        if s["state"] == "filled":
            if not s["evidence_refs"] or not s["claim"].strip():
                add("Q101", sid, "filled 但缺 claim 或 evidence_refs")
            for r in s["evidence_refs"]:
                d = ctx["dmap"].get(r["source_id"] or "")
                if not d:
                    add("Q102", sid, "未知来源 %s" % r["source_id"])
                    continue
                st, u = kit.find_quote(r["quote"], d)
                if st == "exact":
                    continue
                if st == "normalized" and u:
                    add("Q103", sid, "仅差异于空白/标点；建议改用：%s" % u["text"][:80])
                elif st == "fuzzy" and u:
                    add("Q104", sid, "未命中；最近句：%s" % u["text"][:80])
                else:
                    add("Q104", sid, "引文在 %s 中找不到" % r["source_id"])
                rows = [x["decision"] for x in m["screening"] if x["source_id"] == r["source_id"]]
                dec = sorted(rows, key=lambda d: {"exclude": 0, "pending": 1, "include": 2}[d])[-1] if rows else None
                if dec in ("exclude", "pending"):
                    add("Q105", sid, "引用了 %s 结论=%s 的文献" % (r["source_id"], dec))
            hint, hb = kit.strength_hint(s["evidence_refs"], ctx["docs"], bool(s["conflicts_with"]))
            if ORDER[s["strength"]] > ORDER[hint]:
                add("Q107", sid, "自评 %s > 判据 %s (score %s)" % (s["strength"], hint, hb["score"]))
            if hb.get("abstract_only") and s["strength"] == "strong":
                add("Q106", sid, "仅摘要文献支撑 strong")
        else:
            miss_f = [k for k in ("gap_reason", "search_scope", "missing_evidence") if not s.get(k)]
            if miss_f:
                add("G101", sid, "缺 %s" % ",".join(miss_f))
            if s["gap_type"] not in GAP_TYPES:
                add("G102", sid, "非法 gap_type=%r" % s["gap_type"], "用 %s" % "/".join(GAP_TYPES))
            for w in kit.cliche_hits(s.get("missing_evidence", "") + s.get("gap_reason", "")):
                add("G103", sid, "套话“%s”" % w)
        for x in s["conflicts_with"]:
            if x not in m["slots"]:
                add("X101", sid, "冲突指向不存在的 %s" % x)
    for sid, s in m["slots"].items():
        for x in s["conflicts_with"]:
            if x in m["slots"] and sid not in m["slots"][x]["conflicts_with"]:
                add("X102", "%s<->%s" % (sid, x), "冲突关系单向")
    pool = "\n".join(d["text"] or "" for d in ctx["docs"]).lower()
    dois = set()
    for s in m["slots"].values():
        dois |= {x.lower() for x in kit.DOI.findall(s["claim"] + s["gap_reason"] + s["missing_evidence"])}
    for sec in m["outline"]:
        dois |= {x.lower() for x in kit.DOI.findall(sec["lead"] + sec["purpose"])}
    bad = sorted(d for d in dois if d not in pool)
    if bad:
        add("Q108", ",".join(bad[:4]), "材料中不存在这些 DOI")
    return I


# ------------------------------------------------------------------ 修补（build 自动处置，全部留痕）
def repair(m, ctx, changes, degs):
    fixed = {"quote": 0, "dropped": 0, "strength": 0, "gap": 0, "sym": 0}
    for sid, s in m["slots"].items():
        if s["state"] != "filled":
            continue
        keep = []
        for r in s["evidence_refs"]:
            d = ctx["dmap"].get(r["source_id"] or "")
            if not d:
                degs.append({"stage": "build", "source_id": r.get("source_id"), "type": "unknown_source",
                             "detail": "%s 引用了不存在的来源" % sid})
                fixed["dropped"] += 1
                continue
            st, u = kit.find_quote(r["quote"], d)
            if st == "exact":
                if not r["locator"] and u:
                    r["locator"] = u["loc"]
                keep.append(r)
            elif st in ("normalized", "fuzzy") and u:
                changes.append({"target": sid, "action": "quote_replaced", "before": r["quote"][:120],
                                "after": u["text"][:200], "locator": u["loc"], "source_id": r["source_id"],
                                "reason": "引文与材料仅差异于空白/标点或高度相似，改用逐字原句",
                                "human_confirm": st == "fuzzy"})
                r["quote"], r["locator"] = u["text"], u["loc"]
                keep.append(r)
                fixed["quote"] += 1
            else:
                degs.append({"stage": "build", "source_id": r.get("source_id"), "type": "quote_dropped",
                             "detail": "%s 引文无法在 %s 中定位，已丢弃" % (sid, r["source_id"])})
                fixed["dropped"] += 1
        s["evidence_refs"] = keep
        if not keep:
            s.update({"state": "gap",
                      "gap_reason": (s["gap_reason"] + "；" if s["gap_reason"] else "") + "引文无法逐字命中，按纪律不硬写",
                      "gap_type": s["gap_type"] if s["gap_type"] in GAP_TYPES else "retrieval_gap",
                      "search_scope": s["search_scope"] or "材料全文内检索该论断的支撑句",
                      "missing_evidence": s["missing_evidence"] or "可逐字引用的支撑句"})
            fixed["gap"] += 1
            changes.append({"target": sid, "action": "slot_to_gap", "before": "filled", "after": "gap",
                            "reason": "无可验证引文：宁报缺口不假写"})
    for sid, s in m["slots"].items():
        if s["state"] != "filled":
            continue
        hint, hb = kit.strength_hint(s["evidence_refs"], ctx["docs"], bool(s["conflicts_with"]))
        if ORDER[s["strength"]] > ORDER[hint]:
            changes.append({"target": sid, "action": "strength_downgraded", "before": s["strength"], "after": hint,
                            "reason": "判据 score=%s（设计=%s，独立来源=%d，仅摘要=%s）"
                                      % (hb["score"], hb["design"], hb["distinct_sources"], hb["abstract_only"])})
            s["strength"] = hint
            fixed["strength"] += 1
    for sid, s in m["slots"].items():
        for x in list(s["conflicts_with"]):
            if x in m["slots"] and sid not in m["slots"][x]["conflicts_with"]:
                m["slots"][x]["conflicts_with"].append(sid)
                fixed["sym"] += 1
    for r in m["screening"]:
        if not r["source_id"]:
            rec = next((x for x in ctx["records"] if x["record_id"] == r["record_id"]), None)
            r["source_id"] = rec["source_id"] if rec else None
    return fixed


# ------------------------------------------------------------------ 统计
def coverage(m, ctx):
    srcs = [d for d in ctx["docs"] if d["kind"] == "source"]
    rank = {"exclude": 0, "pending": 1, "include": 2}
    dec = {}
    for r in m["screening"]:
        sid = r.get("source_id")
        if sid and rank[r["decision"]] >= rank.get(dec.get(sid, "exclude"), 0):
            dec[sid] = r["decision"]
    filled = [s for s in m["slots"].values() if s["state"] == "filled"]
    gaps = [s for s in m["slots"].values() if s["state"] == "gap"]
    cited = sorted({r["source_id"] for s in filled for r in s["evidence_refs"] if r["source_id"]})
    ev = [r for s in filled for r in s["evidence_refs"]]
    return {
        "sources_total": len(srcs), "records_total": len(ctx["records"]),
        "duplicates": sum(1 for r in ctx["records"] if r["duplicate_of"]),
        "screened": sum(1 for d in srcs if dec.get(d["sid"])),
        "included": sum(1 for v in dec.values() if v == "include"),
        "excluded": sum(1 for v in dec.values() if v == "exclude"),
        "pending": sum(1 for v in dec.values() if v == "pending"),
        "criteria": len(m["criteria"]), "screening_rows": len(m["screening"]),
        "sections": len(m["outline"]), "slots_total": len(m["slots"]),
        "filled": len(filled), "gaps": len(gaps),
        "filled_ratio": round(len(filled) / len(m["slots"]), 3) if m["slots"] else 0.0,
        "evidence_refs": len(ev), "distinct_sources_cited": len(cited), "cited": cited,
        "conflict_pairs": len({tuple(sorted([s["slot_id"], x])) for s in m["slots"].values() for x in s["conflicts_with"]}),
        "strength_counts": {k: sum(1 for s in filled if s["strength"] == k) for k in ("strong", "moderate", "weak")},
        "abstract_only_sources": [d["sid"] for d in srcs if d["abstract_only"]],
        "included_ids": [d["sid"] for d in srcs if dec.get(d["sid"]) == "include"],
        "excluded_ids": [d["sid"] for d in srcs if dec.get(d["sid"]) == "exclude"],
        "pending_ids": [d["sid"] for d in srcs if dec.get(d["sid"]) == "pending"]}


def uncertainty(m, ctx, cov):
    u = ["本 Skill 离线运行：文献真实性、DOI 与著录未联网核验，只做材料内一致性校验"]
    if cov["abstract_only_sources"]:
        u.append("仅摘要可核的文献 %d 篇（%s）：其支撑的断言强度封顶 moderate"
                 % (len(cov["abstract_only_sources"]), ", ".join(cov["abstract_only_sources"][:6])))
    conf = sorted({s["slot_id"] for s in m["slots"].values() if s["conflicts_with"]})
    if conf:
        u.append("存在结论冲突：%s，已并列呈现并标注对立槽位" % ", ".join(conf[:8]))
    if cov["gaps"]:
        u.append("未填充槽位 %d/%d（覆盖率 %.0f%%），逐条见 gap_report.json"
                 % (cov["gaps"], cov["slots_total"], 100 * cov["filled_ratio"]))
    if cov["pending"]:
        u.append("待定文献 %d 篇：其结论不应视作已纳入证据" % cov["pending"])
    if ctx["degs"]:
        u.append("材料抽取/建库降级 %d 条，见 degradations" % len(ctx["degs"]))
    return u


# ------------------------------------------------------------------ 渲染
def render_draft(m, ctx, cov):
    zh = m["lg"] == "zh"
    SEP = "" if zh else " "
    rq = m["rq"] or ("（输入未给研究问题）" if zh else "(no research question in input)")
    L = ["# " + ("文献综述（提纲驱动）：%s" % rq if zh else "Outline-driven review: %s" % rq), "",
         ("> 研究问题：%s" % rq if zh else "> Research question: %s" % rq), "",
         ("> 生成：outline-slot-review v%s；段末 `[SLx]` 是该段来源槽位，`[Sxx]` 是引文来源；"
          "本稿只由已填槽位渲染，未填槽位不写成正文。" % V) if zh else
         ("> Generated by outline-slot-review v%s; `[SLx]` = source slots, `[Sxx]` = cited sources; "
          "only filled slots become prose." % V), ""]
    if not m["authored"]:
        L += ["## " + ("文献清单（材料转录，非论断）" if zh else "Source inventory (transcribed)"), "",
              "| 来源 | 标题（材料转录） | 年 | 仅摘要 | 首条定位 |", "|---|---|---|---|---|"]
        for d in ctx["docs"]:
            if d["kind"] != "source":
                continue
            u = d["units"][0] if d["units"] else None
            L.append("| %s | %s | %s | %s | `%s` |" % (
                d["sid"], (d["meta"].get("title") or "—").replace("|", "/")[:80], d["meta"].get("year") or "—",
                "是" if d["abstract_only"] else "否", u["loc"] if u else "—"))
        L += ["", "> 上表仅为材料元数据与定位转录，未做解释；缺工作稿时本 Skill 不生成论断。", ""]
    for sec in m["outline"]:
        L += ["## " + sec["heading"], ""]
        if sec["purpose"]:
            L += [("*本节目：%s*" % sec["purpose"] if zh else "*Purpose: %s*" % sec["purpose"]), ""]
        if sec["lead"]:
            L += [sec["lead"].strip() + " [%s]" % ",".join(sec["lead_slot_ids"]), ""]
        body, pid, last = [], [], [None]
        for sid in sec["slot_ids"]:
            s = m["slots"].get(sid)
            if not s or s["state"] != "filled":
                continue
            sids = [r["source_id"] for r in s["evidence_refs"] if r["source_id"]]
            fresh = (not body) or s["strength"] != last[0]
            sent = kit.render_claim(s["claim"], s["strength"], sids, m["lg"], s["polarity"], hedge=fresh)
            last[0] = s["strength"]
            if not sent:
                continue
            if s["polarity"] == "counter" and body:
                L += [SEP.join(body) + " [%s]" % ",".join(pid), ""]
                body, pid, last = [], [], [None]
            body.append(sent)
            pid.append(sid)
            if len(body) >= 3:
                L += [SEP.join(body) + " [%s]" % ",".join(pid), ""]
                body, pid, last = [], [], [None]
        if body:
            L += [SEP.join(body) + " [%s]" % ",".join(pid), ""]
        elif m["authored"]:
            L += ["> 本节暂无已逐字核验的证据，不写正文；缺口见下一节。" if zh
                  else "> No verified evidence for this section; see gaps.", ""]
    gaps = [m["slots"][k] for k in sorted(m["slots"], key=lambda x: (len(x), x)) if m["slots"][k]["state"] == "gap"]
    if gaps:
        L += ["## " + ("证据缺口（未填充槽位）" if zh else "Evidence gaps"), ""]
        for s in gaps:
            L.append("- `%s`｜类型 %s｜缺什么：%s｜检索范围：%s｜原因：%s"
                     % (s["slot_id"], s["gap_type"] or "未标注", s["missing_evidence"] or "未填",
                        s["search_scope"] or "未填", s["gap_reason"] or "未填"))
        L.append("")
    L += ["## " + ("边界与不确定性" if zh else "Boundaries and uncertainty"), ""]
    L += ["- " + x for x in uncertainty(m, ctx, cov)]
    L += ["", "## " + ("参考文献（材料转录，未联网核验）" if zh else "References (transcribed, not verified online)"), ""]
    seen = []
    for d in ctx["docs"]:
        if d["kind"] != "source":
            continue
        if d["sid"] in cov["cited"]:
            seen.append("[%s] %s" % (d["sid"], kit.source_line(d)))
        elif d["sid"] in cov.get("included_ids", []):
            seen.append("[%s] %s（纳入但草稿未引用）" % (d["sid"], kit.source_line(d)))
    if cov.get("excluded_ids"):
        seen.append("- 已排除未列入：%s" % ", ".join(cov["excluded_ids"]))
    L += seen or ["- （材料中无可引用文献）"]
    return "\n".join(L).rstrip() + "\n"


def gap_report(m, ctx, cov):
    gaps = [m["slots"][k] for k in sorted(m["slots"], key=lambda x: (len(x), x)) if m["slots"][k]["state"] == "gap"]
    by_type, by_sec, label = {}, {}, {}
    for sec in m["outline"]:
        for s in sec["slots"]:
            label[s["slot_id"]] = sec["heading"]
    for g in gaps:
        by_type[g["gap_type"] or "unlabelled"] = by_type.get(g["gap_type"] or "unlabelled", 0) + 1
        h = label.get(g["slot_id"], "未分组")
        by_sec[h] = by_sec.get(h, 0) + 1
    rgs = []
    for i, g in enumerate(gaps, 1):
        h = label.get(g["slot_id"], "")
        stmt = ("在「%s」上，材料尚缺：%s；要推进该问题，需在「%s」范围内补证（缺口类型：%s）。"
                % (h or "未分组", g["missing_evidence"] or "未说明", g["search_scope"] or "未限定",
                   g["gap_type"] or "未标注"))
        hits = kit.cliche_hits(g["missing_evidence"] + g["gap_reason"] + g["search_scope"])
        rgs.append({"gap_id": "RG%02d" % i, "slot_id": g["slot_id"], "statement": stmt,
                    "grounded_in": [g["slot_id"]], "gap_type": g["gap_type"] or None, "cliche_hits": hits})
    return {"case_id": m["case_id"], "gap_count": len(gaps), "by_type": by_type, "by_section": by_sec,
            "by_slot": [{"slot_id": g["slot_id"], "section": label.get(g["slot_id"], ""),
                         "gap_type": g["gap_type"] or None, "gap_reason": g["gap_reason"],
                         "search_scope": g["search_scope"], "missing_evidence": g["missing_evidence"]} for g in gaps],
            "research_gaps": rgs, "cliche_flagged": [r["gap_id"] for r in rgs if r["cliche_hits"]],
            "rule": "研究空白由已写缺口字段推导（槽位→缺什么→检索范围），不用套话结尾"}


def value_for(k, prods, m, ctx):
    t = next((v for pat, v in FIELDS if re.search(pat, k, re.I)), None)
    if not t:
        return None, None
    if t == "draft":
        return prods["draft_text"], "draft.md"
    if t == "criteria":
        return m["criteria"], "screening/criteria.json"
    if t == "screening":
        return m["screening"], "screening/screening_log.jsonl"
    if t == "outline":
        return [{"sec_id": s["sec_id"], "heading": s["heading"], "purpose": s["purpose"],
                 "slot_ids": s["slot_ids"]} for s in m["outline"]], "outline/skeleton.json"
    if t == "evidence_slots":
        return prods["slot_rows"], "slots/filled.jsonl"
    if t == "gaps":
        return prods["gap_rows"], "slots/gaps.jsonl"
    if t == "coverage":
        return prods["coverage"], "coverage.json"
    if t == "sources":
        return ctx["sources"], "result.json#sources"
    if t == "uncertainty":
        return prods["uncertainty"], "result.json#uncertainty"
    if t == "changes":
        return prods["changes"], "changes.json"
    if t == "status":
        return prods["status"], "result.json#status"
    return m["case_id"], "result.json#case_id"
