#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check.py - research-01 draft normalisation and mechanical validation (FIX/WARN codes).

Discovery, parsing (pdf/docx/html/text/structured), sentence-level indexing with
validation. Standard library only, offline, independent of CWD.
"""

import re

from parse import (STATUSES, CONFIDENCE, F_TYPES, SQ_FIELDS, LAYERS, OQ_TYPES,
                   quote_locate)


# --------------------------------------------------------------------------- draft
ALIASES = {
    "brief": ["brief", "study_brief", "question_brief"],
    "sq": ["sub_questions", "subquestions", "sub_questions_list", "questions",
           "decomposition", "question_tree", "sq"],
    "search": ["search_log", "search_steps", "retrieval_log", "tool_log", "tool_calls",
               "retrieval_steps", "steps", "search_plan"],
    "findings": ["findings", "finding_cards", "cards", "key_findings", "finding_list"],
    "synthesis": ["synthesis", "synthesis_claims", "synthesis_memo", "memo",
                  "conclusions", "claims"],
    "open": ["open_questions", "gaps", "research_gaps", "open_issues",
             "open_questions_gaps", "limitations"],
}


def _first(d, keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def normalize_draft(draft):
    d = draft if isinstance(draft, dict) else {}
    brief = d.get("brief") if isinstance(d.get("brief"), dict) else {}
    out = {
        "case_id": d.get("case_id") or d.get("caseId"),
        "brief": {
            "question": brief.get("question") or (d.get("question") if isinstance(d.get("question"), str) else None),
            "scope": brief.get("scope"),
            "inclusion": brief.get("inclusion") or [],
            "exclusion": brief.get("exclusion") or [],
            "stop_rules": brief.get("stop_rules") or [],
        },
        "sub_questions": _first(brief, ALIASES["sq"]) or _first(d, ALIASES["sq"]) or [],
        "search_log": _first(d, ALIASES["search"]) or [],
        "findings": _first(d, ALIASES["findings"]) or [],
        "synthesis": _first(d, ALIASES["synthesis"]) or [],
        "open_questions": _first(d, ALIASES["open"]) or [],
        "derived": bool(d.get("_derived")),
    }
    for k in ("sub_questions", "search_log", "findings", "synthesis", "open_questions"):
        if not isinstance(out[k], list):
            out[k] = []
    out["sub_questions"] = [x for x in out["sub_questions"] if isinstance(x, dict)]
    out["findings"] = [x for x in out["findings"] if isinstance(x, dict)]
    out["synthesis"] = [x for x in out["synthesis"] if isinstance(x, dict)]
    out["open_questions"] = [x for x in out["open_questions"] if isinstance(x, dict)]
    out["search_log"] = [x for x in out["search_log"] if isinstance(x, dict)]
    return out


OVERCLAIM = re.compile(r"(证明|证实|确证|充分证明|proves|proven|confirms|demonstrates causality|"
                       r"确凿|毫无疑问|definitively)", re.I)
NEG = re.compile(r"(no significant|not significant|no association|did not|no effect|"
                 r"无显著|未发现|不相关|无效|无差异|相反)", re.I)


def _rank(status):
    return {"established": 3, "provisional": 2, "contested": 1, "undetermined": 0}.get(status or "", 1)


def check_draft(draft, idx):
    """Mechanical validation. Returns {issues, repairs, stats}."""
    issues = []
    repairs = []
    d = draft
    def add(code, sev, where, msg, hint=""):
        issues.append({"code": code, "severity": sev, "where": where,
                       "message": msg, "fix_hint": hint})

    sqs = d["sub_questions"]
    finds = d["findings"]
    sq_ids = []
    for i, sq in enumerate(sqs):
        sid = sq.get("sq_id") or "SQ%d" % (i + 1)
        sq["sq_id"] = sid
        sq_ids.append(sid)
        miss = [k for k in SQ_FIELDS if not str(sq.get(k) or "").strip()]
        if miss:
            add("C201", "FIX", sid, "子问题缺字段: %s" % ",".join(miss),
                "补齐 object/mechanism/method/time_scope/comparison/evidence_requirement")
        if sq.get("layer") not in LAYERS:
            add("C203", "WARN", sid, "layer 取值应为 %s" % "/".join(LAYERS))
    if len(sqs) < 4:
        add("C202", "WARN", "brief", "子问题仅 %d 条（<4），拆解深度不足" % len(sqs),
            "从对象/机制/方法/时间/比较五个维度补拆")
    layers = {sq.get("layer") for sq in sqs}
    miss_layers = [l for l in LAYERS if l not in layers]
    if miss_layers:
        add("C203", "WARN", "brief", "缺层次: %s" % ",".join(miss_layers),
            "覆盖 是什么/做到哪/为什么/还缺什么")

    seen = {}
    qv, qf, repaired = 0, 0, 0
    src_ids = {m["id"] for m in idx["materials"]}
    for i, f in enumerate(finds):
        fid = f.get("finding_id") or "F%03d" % (i + 1)
        f["finding_id"] = fid
        if fid in seen:
            add("C215", "FIX", fid, "finding_id 重复")
        seen[fid] = True
        if f.get("status") not in STATUSES:
            add("C217", "FIX", fid, "status 取值应为 %s" % "/".join(STATUSES))
        if f.get("confidence") not in CONFIDENCE:
            add("C217", "FIX", fid, "confidence 取值应为 %s" % "/".join(CONFIDENCE))
        if f.get("type") not in F_TYPES:
            add("C217", "FIX", fid, "type 取值应为 %s" % "/".join(F_TYPES))
        for k in ("scope", "confidence", "status", "type", "statement"):
            if not str(f.get(k) or "").strip():
                add("C212", "FIX", fid, "缺字段: %s" % k, "补 scope/confidence/status/statement")
        sqid = f.get("sub_question_id")
        if sqid and sqid not in sq_ids:
            add("C216", "FIX", fid, "sub_question_id=%s 未在简报中登记" % sqid)
        sup = f.get("support") or []
        cnt = f.get("counter") or []
        if not isinstance(sup, list):
            sup = []
            f["support"] = sup
        if not isinstance(cnt, list):
            cnt = []
            f["counter"] = cnt
        if not sup and f.get("type") != "undetermined":
            add("C210", "FIX", fid, "发现卡无 support 证据",
                "从 show 输出逐字复制至少一句，并写 locator")
        for grp, label in ((sup, "support"), (cnt, "counter")):
            for si, ev in enumerate(grp):
                if not isinstance(ev, dict):
                    grp[si] = ev = {"quote": str(ev)}
                q = (ev.get("quote") or "").strip()
                if not q:
                    add("C214", "FIX", fid, "%s[%d] 缺 quote" % (label, si))
                    continue
                if not ev.get("source_id"):
                    add("C214", "WARN", fid, "%s[%d] 缺 source_id（将按命中位置补）" % (label, si))
                if not ev.get("locator"):
                    add("C214", "WARN", fid, "%s[%d] 缺 locator（将按命中位置补）" % (label, si))
                loc = quote_locate(idx, q, ev.get("source_id"))
                if loc["ok"]:
                    qv += 1
                    ev["verified"] = True
                    ev["source_id"] = ev.get("source_id") or loc["source_id"]
                    if ev.get("source_id") not in src_ids:
                        add("C214", "WARN", fid, "%s[%d] source_id 未在材料清单" % (label, si))
                        ev["source_id"] = loc["source_id"]
                    old = ev.get("locator") or ""
                    if not old or old.split(" chars:")[0] != loc["locator"].split(" chars:")[0]:
                        ev["locator"] = loc["locator"]
                        ev["truth_source_id"] = loc["source_id"]
                        repaired += 1
                        repairs.append({"code": "R211", "where": fid,
                                        "detail": "%s[%d] locator 已按命中位置回改" % (label, si),
                                        "from": old, "to": loc["locator"]})
                else:
                    qf += 1
                    ev["verified"] = False
                    if loc.get("locator") and not ev.get("locator"):
                        ev["locator"] = loc["locator"]
                    add("C211", "FIX", fid,
                        "%s[%d] quote 非逐字命中（%s）" % (label, si, loc.get("reason")),
                        "回 show 重抄原文；可疑位置 %s" % (loc.get("locator") or "无"))
                    if f.get("status") in ("established", "contested"):
                        f["status"] = "provisional"
                        f["_status_downgraded"] = "quote_unverified"
                    f["confidence"] = "low"
        if cnt and f.get("status") == "established":
            add("C213", "FIX", fid, "有 counter 反证却标 established（隐藏冲突）",
                "改 provisional/contested，并把无法解决的冲突写进 05-open-questions")

    # synthesis
    reg = {f["finding_id"]: f for f in finds}
    cited = set()
    for i, para in enumerate(d["synthesis"]):
        txt = str(para.get("paragraph") or para.get("text") or "")
        para["paragraph"] = txt
        ids = para.get("finding_ids")
        ids = [str(x).strip("[]") for x in ids] if isinstance(ids, list) else []
        for m2 in re.findall(r"\[(F\d{1,4})\]", txt):
            if m2 not in ids:
                ids.append(m2)
        para["finding_ids"] = ids
        unknown = [x for x in ids if x not in reg]
        if unknown:
            add("C220", "FIX", "synthesis[%d]" % i, "引用未登记 finding: %s" % ",".join(unknown),
                "只能引用 03-findings 里已登记的编号")
        cited.update(x for x in ids if x in reg)
        if not ids:
            add("C224", "FIX", "synthesis[%d]" % i, "段落未引用任何发现卡",
                "在句末加 [Fxxx]，让结论经卡片回链到原文")
            continue
        note = para.get("strength_note") or "provisional"
        para["strength_note"] = note
        top = max([_rank(reg[x].get("status")) for x in ids if x in reg] or [0])
        if _rank(note) > top:
            add("C221", "FIX", "synthesis[%d]" % i,
                "段落强度(%s)高于所引卡片最高状态" % note,
                "下调措辞或补更强证据")
        if OVERCLAIM.search(txt) and top < 3:
            add("C222", "FIX", "synthesis[%d]" % i,
                "出现绝对措辞但所引卡片最高状态不足 established",
                "改为 提示/关联/尚不能确定")
    for f in finds:
        if f["finding_id"] not in cited:
            add("C223", "INFO", f["finding_id"], "该发现卡未被综合备忘录引用")

    # coverage
    per_sq = {}
    for f in finds:
        per_sq.setdefault(f.get("sub_question_id"), []).append(f)
    uncovered = [s for s in sq_ids if not per_sq.get(s)]
    for s in uncovered:
        add("C230", "WARN", s, "子问题无任何发现卡覆盖", "补卡或在 05 写 retrieval_gap")
    for s, fs in per_sq.items():
        srcs = {(e.get("source_id") or "") for f in fs
                for e in (f.get("support") or []) + (f.get("counter") or [])}
        if s and len(srcs - {""}) < 2:
            add("C231", "WARN", str(s), "该子问题仅单一来源支撑", "补第二来源或降低置信度")

    # open questions
    oq_types = []
    for i, oq in enumerate(d["open_questions"]):
        t = oq.get("type")
        oq_types.append(t)
        if t not in OQ_TYPES:
            add("C240", "FIX", oq.get("oq_id") or "open[%d]" % i,
                "type=%s 不在词表 %s" % (t, "/".join(OQ_TYPES)))
        if not str(oq.get("basis") or "").strip():
            add("C240", "WARN", oq.get("oq_id") or "open[%d]" % i, "缺口缺 basis 依据")
    if uncovered and "retrieval_gap" not in oq_types:
        add("C241", "WARN", "open_questions", "有未覆盖子问题但没有 retrieval_gap 条目",
            "把未覆盖子问题写成检索缺口")

    # search log
    log = d["search_log"]
    if not log:
        add("C250", "WARN", "search_log", "检索日志为空（可复跑路径缺失）")
    hit_ids = set()
    step_ids = []
    for i, st in enumerate(log):
        sid = st.get("step_id") or "S%d" % (i + 1)
        st["step_id"] = sid
        if sid in step_ids:
            add("C215", "WARN", sid, "step_id 重复")
        step_ids.append(sid)
        hits = st.get("hits") or []
        if isinstance(hits, str):
            hits = [hits]
        st["hits"] = hits
        hit_ids.update(str(h) for h in hits)
        if not str(st.get("action") or "").strip():
            add("C250", "WARN", sid, "缺少 action")
    used = {e.get("source_id") for f in finds for e in (f.get("support") or []) if e.get("source_id")}
    for s in sorted(used - hit_ids):
        add("C251", "WARN", s, "证据来源没出现在任何检索/读取步骤的 hits 里",
            "在 search_log 补一条 read/search 记录")

    fix = sum(1 for x in issues if x["severity"] == "FIX")
    warn = sum(1 for x in issues if x["severity"] == "WARN")
    stats = {"sub_questions": len(sqs), "findings": len(finds),
             "synthesis_paragraphs": len(d["synthesis"]), "open_questions": len(d["open_questions"]),
             "search_steps": len(log), "quotes_verified": qv, "quotes_failed": qf,
             "locators_repaired": repaired, "fix": fix, "warn": warn,
             "uncovered_sub_questions": uncovered}
    return {"issues": issues, "repairs": repairs, "stats": stats}
