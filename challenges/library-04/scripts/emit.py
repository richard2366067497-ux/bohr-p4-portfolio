#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emit.py — draft validation, result assembly and contract backfill.

The Agent's judgements (which file is which version, whether the library really
supports a claim, what must be answered "no") arrive in /app/work/draft.json.
Each quote is re-located in the indexed text, each locator recomputed, and every
unresolved reference becomes a recorded degradation rather than a silent pass.
"""
from __future__ import annotations

import json
import re
import sys
import time
import kb
import parse as P
from kb import akey, draft_answers, evs_of, load_draft, match_answer, sides_of
from parse import norm_q

VERSION = kb.VERSION
CLAIM_STATUS, LEVELS = kb.CLAIM_STATUS, kb.LEVELS
CONTRACT_RULES = (
    ("case_id", ("case_id", "caseid")), ("status", ("status", "run_status")),
    ("summary", ("summary", "overview", "结论", "综述", "摘要")),
    ("answers", ("answer", "qa", "问答", "回答")), ("questions", ("question", "query", "问题")),
    ("evidence", ("evidence", "citation", "quote", "引文", "证据", "回链", "trace")),
    ("documents", ("document", "file", "catalog", "inventory", "清单", "文件", "目录", "资料")),
    ("metadata", ("metadata", "元数据", "字段")), ("versions", ("version", "版本", "edition")),
    ("duplicates", ("duplicate", "dedup", "重复", "副本")),
    ("conflicts", ("conflict", "矛盾", "冲突")),
    ("not_found", ("not_found", "missing", "gap", "insufficient", "缺证", "无依据", "未找到")),
    ("operations", ("operation", "action", "log", "repair", "change", "操作", "整理", "处置")),
    ("coverage", ("coverage", "stat", "count", "覆盖", "统计")),
    ("uncertainties", ("uncertain", "risk", "不确定性")),
    ("degradations", ("degrad", "limitation", "缺口")),
    ("errors", ("error", "failure", "失败", "异常")),
    ("sources", ("source", "provenance", "来源")),
)


def edition_spread(docs, items, verified=False):
    """How many cited records share one document family (>=2 means cross-edition evidence)."""
    fam_of = {d["doc_id"]: d.get("family") for d in docs}
    counts = {}
    for e in items or []:
        if not isinstance(e, dict) or (verified and not e.get("quote_verified")):
            continue
        doc = kb.doc_lookup(docs, e.get("doc_id") or e.get("path") or e.get("file"))
        f = fam_of.get(doc["doc_id"]) if doc else None
        if f:
            counts[f] = counts.get(f, 0) + 1
    return max(counts.values()) if counts else 0


def verify_draft(state, draft):
    """Mechanical validation of the Agent worksheet. Never raises."""
    items, docs, chunks = [], state["docs"], state["chunks"]
    st = {"claims": 0, "evidence": 0, "quote_ok": 0, "quote_miss": 0,
          "questions_expected": len(state["questions"]), "answered": 0, "not_in_kb": 0, "conflicts": 0}
    dmap = kb.doc_text_map(docs, chunks)

    def add(level, item, msg, hint=None):
        rec = {"level": level, "item": item, "message": msg}
        if hint:
            rec["hint"] = hint
        items.append(rec)

    if draft is None:
        add("FIX", "draft.json", "工作稿缺失：build 会走兜底（清单齐全、答案标缺证、status=partial）",
            "先 init/show 读材料，写 /app/work/draft.json 再 check")
        return items, st
    answers = next((draft[k] for k in ("answers", "qa", "responses", "问答")
                     if isinstance(draft.get(k), list)), [])
    if not answers:
        add("FIX", "answers", "draft.json 没有 answers 数组", "按 references/contract.md §5 写 answers[]")
    covered = set()
    for idx, a in enumerate(answers, 1):
        if not isinstance(a, dict):
            add("FIX", f"answers[{idx}]", "条目不是对象")
            continue
        key = akey(a, idx)
        matched = next((q for q in state["questions"] if match_answer(a, q)), None)
        if matched:
            covered.add(str(matched.get("question_id")))
        elif state["questions"]:
            add("WARN", f"answers[{idx}]", f"答案 '{key}' 对不上 case.json 的任何问题")
        if not str(a.get("answer") or a.get("a") or a.get("text") or "").strip():
            add("FIX", key, "answer 为空")
        claims = [c for c in (a.get("claims") or []) if isinstance(c, dict)]
        statuses = []
        for ci, c in enumerate(claims, 1):
            st["claims"] += 1
            cst = str(c.get("status") or "").strip()
            statuses.append(cst)
            tag = f"{key}.claim{ci}"
            if cst not in CLAIM_STATUS:
                add("FIX", tag, f"status='{cst}' 不在 {sorted(CLAIM_STATUS)}")
            if not str(c.get("claim") or "").strip():
                add("FIX", tag, "claim 文本为空")
            evs = evs_of(c)
            if cst in ("supported", "conflicting") and not evs:
                add("FIX", tag, f"status={cst} 却没有 evidence")
            quotes, cited = [], set()
            for ei, e in enumerate(evs, 1):
                st["evidence"] += 1
                quote = str(e.get("quote") or "")
                doc = kb.doc_lookup(docs, e.get("doc_id") or e.get("path") or e.get("file"))
                if doc is None:
                    add("FIX", f"{tag}.ev{ei}", f"引用文件 '{e.get('path') or e.get('doc_id')}' 不在索引中")
                    continue
                cited.add(doc["doc_id"])
                if len(norm_q(quote)) < 12:
                    add("WARN", f"{tag}.ev{ei}", "quote 短于 12 字符，证据力不足")
                hit = kb.locate_quote(dmap, doc["doc_id"], quote) if quote else None
                if hit is None:
                    st["quote_miss"] += 1
                    add("FIX", f"{tag}.ev{ei}", f"quote 在 {doc['doc_id']} 中找不到逐字原文：\"{quote[:46]}\"",
                        f"用 show --doc {doc['doc_id']} 复制原句，不要改写/翻译/拼接")
                    continue
                st["quote_ok"] += 1
                quotes.append(quote)
                if e.get("page") not in (None, "") and hit["page"] is not None:
                    try:
                        if int(re.findall(r"\d+", str(e["page"]))[0]) != int(hit["page"]):
                            add("WARN", f"{tag}.ev{ei}", f"页码写 {e['page']}，实际在 p{hit['page']}（build 会纠正）")
                    except Exception:
                        pass
                elif hit["page"] is not None:
                    add("INFO", f"{tag}.ev{ei}", f"缺页码，已定位 p{hit['page']}（build 回填）")
                dver = str(doc.get("version") or "")
                if e.get("version") and dver and str(e["version"]).strip() != dver:
                    add("WARN", f"{tag}.ev{ei}", f"引用版本 '{e['version']}' ≠ 索引版本 '{dver}'")
                elif not e.get("version"):
                    add("INFO", f"{tag}.ev{ei}", f"缺版本号，按索引回填 {dver}")
            stray = [n for n in set(kb.NUM.findall(str(c.get("claim") or "")))
                     if n.lower() not in norm_q(" ".join(quotes))]
            if stray and quotes:
                add("WARN", tag, f"claim 中数值 {stray[:4]} 未出现在所引原句（疑似推断或写错）",
                    "确属推断请改 status=insufficient/not_in_kb，或补含该数值的原句")
            if cst == "conflicting" and len(cited) < 2:
                add("WARN", tag, "conflicting 论断应引用两个不同文件的原文")
        if any(s in ("not_in_kb", "insufficient") for s in statuses):
            st["not_in_kb"] += 1
            if not str(a.get("missing_evidence") or "").strip():
                add("FIX", key, "有缺证论断，但 missing_evidence 为空（必须说明缺什么）")
            if not a.get("searched_scope") and not draft.get("not_found"):
                add("WARN", key, "缺证问题缺 searched_scope（build 会从检索记录补）")
        lvl = str(a.get("uncertainty_level") or "").strip()
        if lvl not in LEVELS:
            add("FIX", key, f"uncertainty_level='{lvl}' 不在 {sorted(LEVELS)}")
        else:
            want, why = kb.uncertainty_grade(claims, editions=edition_spread(docs, [e for c in claims for e in evs_of(c)]))
            if want != lvl:
                add("WARN", key, f"uncertainty_level 按规则应为 {want}（{why}），你写 {lvl}",
                    "规则见 references/rules.md §4；build 采用规则值并记 changes")
        st["answered"] += 1
    for q in state["questions"]:
        if str(q.get("question_id")) not in covered:
            add("FIX", str(q.get("question_id")), f"问题未被作答：{str(q.get('question'))[:56]}")
    conflicts = [c for c in (draft.get("conflicts") or []) if isinstance(c, dict)]
    for ci, cf in enumerate(conflicts, 1):
        st["conflicts"] += 1
        sides = sides_of(cf)
        if len(sides) < 2:
            add("FIX", f"conflicts[{ci}]", "冲突需要 side_a 与 side_b 两侧原话")
        for si, s in enumerate(sides, 1):
            doc = kb.doc_lookup(docs, s.get("doc_id") or s.get("path") or s.get("file"))
            if doc is None:
                add("FIX", f"conflicts[{ci}].side{si}", f"冲突一侧文件 '{s.get('path')}' 不在索引中")
            elif kb.locate_quote(dmap, doc["doc_id"], str(s.get("quote") or "")) is None:
                add("FIX", f"conflicts[{ci}].side{si}", f"冲突一侧 quote 非逐字：\"{str(s.get('quote'))[:40]}\"")
    for ni, nf in enumerate([n for n in (draft.get("not_found") or []) if isinstance(n, dict)], 1):
        if not str(nf.get("missing_evidence") or "").strip():
            add("FIX", f"not_found[{ni}]", "缺证记录没有 missing_evidence")
        if not nf.get("searched_scope"):
            add("WARN", f"not_found[{ni}]", "缺证记录没有 searched_scope")
    add("INFO", "output_contract", f"{len(state.get('contract') or {})} 个契约键将在 build 时原样回填")
    return items, st


# ---------------------------------------------------------------------- assemble
def _claims(state, claims, key, dmap, degradations, changes):
    docs, out = state["docs"], []
    for ci, c in enumerate(claims or [], 1):
        if not isinstance(c, dict):
            continue
        cst = str(c.get("status") or "").strip()
        if cst not in CLAIM_STATUS:
            cst = "insufficient"
        ev_out = []
        for e in evs_of(c):
            quote = str(e.get("quote") or "")
            doc = kb.doc_lookup(docs, e.get("doc_id") or e.get("path") or e.get("file"))
            if doc is None:
                degradations.append({"stage": "build", "item": f"{key}.claim{ci}",
                                     "detail": f"evidence reference '{e.get('path') or e.get('doc_id')}' unresolved",
                                     "impact": "evidence dropped"})
                continue
            hit = kb.locate_quote(dmap, doc["doc_id"], quote) if quote else None
            page = hit["page"] if hit and hit["page"] is not None else e.get("page")
            if hit and e.get("page") not in (None, "") and str(e["page"]) != str(page):
                changes.append({"item": f"{key}.claim{ci}", "field": "page", "from": e.get("page"),
                                "to": page, "reason": "verbatim locator wins"})
            rec = {"doc_id": doc["doc_id"], "path": doc["path"],
                   "version": str(e.get("version") or doc.get("version") or ""),
                   "page": page, "section": hit["section"] if hit else e.get("section"),
                   "chunk_id": hit["chunk_id"] if hit else None, "char_offset": hit["offset"] if hit else None,
                   "quote": quote, "quote_verified": bool(hit),
                   "match_type": hit["match"] if hit else "unverified",
                   "sha256_16": (doc.get("sha256") or "")[:16],
                   "locator": f"[{doc['doc_id']} {doc['path']} {doc.get('version') or 'v?'} "
                              f"p{page if page is not None else '-'} §{hit['section'] if hit else e.get('section')}]"}
            if not hit:
                degradations.append({"stage": "build", "item": f"{key}.claim{ci}",
                                     "detail": f"quote not verbatim in {doc['doc_id']}: {quote[:56]}",
                                     "impact": "kept with quote_verified=false; not usable as evidence"})
            ev_out.append(rec)
        good = [e for e in ev_out if e["quote_verified"]]
        if cst in ("supported", "conflicting") and not good:
            cst = "insufficient"
            changes.append({"item": f"{key}.claim{ci}", "field": "status", "to": "insufficient",
                            "reason": "no verbatim-verified evidence"})
        out.append({"claim_id": f"{key}.C{ci}", "claim": str(c.get("claim") or ""),
                    "status": cst, "evidence": ev_out, "evidence_count": len(good)})
    return out


def assemble(state, draft):
    t0 = time.time()
    docs, chunks = state["docs"], state["chunks"]
    dmap = kb.doc_text_map(docs, chunks)
    degradations, changes = list(state.get("degradations") or []), []
    errors = list(state.get("errors") or [])
    draft_ok = isinstance(draft, dict)
    das = draft_answers(draft) if draft_ok else []
    answers, evidence, conflicts, not_found, operations = [], [], [], [], []

    for q in state["questions"]:
        qid = str(q.get("question_id"))
        hits = kb.search(chunks, q.get("question") or "", topk=5, dup_ids={d["doc_id"] for d in docs if d.get("dup_of")})
        scope = sorted({h["doc_id"] for h in hits}) or [d["doc_id"] for d in docs if d["readable"]][:9]
        match = next((a for a in das if isinstance(a, dict) and match_answer(a, q)), None)
        if match is None:
            ans = {"question_id": qid, "question": q.get("question"),
                   "answer": "（尚未作答）已建索引并给出检索候选，但工作稿缺少对该题的人工判断，"
                             "因此不给结论，避免编造依据。",
                   "claims": [{"claim_id": f"{qid}.C1", "status": "insufficient", "evidence_count": 0,
                               "evidence": [], "claim": "未生成工作稿：仅完成机械索引与候选检索"}],
                   "uncertainty_level": "high", "searched_scope": scope, "from_draft": False,
                   "missing_evidence": "缺少工作稿：需阅读材料后写明依据与逐字引文", "status": "partial"}
            not_found.append({"question_id": qid, "question": q.get("question"), "searched_scope": scope,
                              "missing_evidence": "工作稿未覆盖该问题；索引已建立但未指认任何逐字证据"})
            degradations.append({"stage": "build", "item": qid, "detail": "no draft answer",
                                 "impact": "answer is a placeholder, NOT a knowledge-base negative"})
        else:
            claims = _claims(state, match.get("claims"), qid, dmap, degradations, changes)
            statuses = [c["status"] for c in claims]
            lvl = str(match.get("uncertainty_level") or "").strip()
            graded, why = kb.uncertainty_grade(claims, editions=edition_spread(docs, [e for c in claims for e in c["evidence"]], verified=True))
            if lvl not in LEVELS:
                lvl = graded
            elif lvl != graded:
                changes.append({"item": qid, "field": "uncertainty_level", "from": lvl, "to": graded,
                                "reason": f"rule-based grade ({why})"})
                lvl = graded
            miss = match.get("missing_evidence")
            if not miss and any(s in ("not_in_kb", "insufficient") for s in statuses):
                miss = "检索范围内无逐字依据；需补充对应原始材料"
                changes.append({"item": qid, "field": "missing_evidence", "to": miss,
                                "reason": "filled from claim status"})
            if statuses and all(s == "supported" for s in statuses):
                astat = "answered"
            elif statuses and all(s in ("not_in_kb", "insufficient") for s in statuses):
                astat = "insufficient"
            else:
                astat = "partial"
            ans = {"question_id": qid, "question": q.get("question") or match.get("question"),
                   "answer": str(match.get("answer") or match.get("a") or match.get("text") or ""),
                   "claims": claims, "uncertainty_level": lvl, "missing_evidence": miss,
                   "searched_scope": match.get("searched_scope") or scope,
                   "status": astat, "from_draft": True}
        answers.append(ans)
        for c in ans["claims"]:
            for e in c["evidence"]:
                evidence.append(dict(e, claim_id=c["claim_id"], question_id=qid))

    for cf in ([c for c in (draft.get("conflicts") or []) if isinstance(c, dict)] if draft_ok else []):
        entry = {"topic": cf.get("topic") or cf.get("title") or "conflict",
                 "reason": cf.get("reason"), "sides": []}
        for s in sides_of(cf):
            doc = kb.doc_lookup(docs, s.get("doc_id") or s.get("path") or s.get("file"))
            quote = str(s.get("quote") or "")
            hit = kb.locate_quote(dmap, doc["doc_id"], quote) if doc and quote else None
            entry["sides"].append({"doc_id": doc["doc_id"] if doc else None,
                                   "path": doc["path"] if doc else s.get("path"),
                                   "version": doc.get("version") if doc else s.get("version"),
                                   "page": hit["page"] if hit else s.get("page"),
                                   "section": hit["section"] if hit else s.get("section"),
                                   "quote": quote, "quote_verified": bool(hit)})
            if not hit:
                degradations.append({"stage": "build", "item": entry["topic"],
                                     "detail": f"conflict quote unverified: {quote[:48]}",
                                     "impact": "conflict kept but one side is not verbatim"})
        conflicts.append(entry)

    for nf in ([n for n in (draft.get("not_found") or []) if isinstance(n, dict)] if draft_ok else []):
        ref = str(nf.get("question_id") or nf.get("question") or "")
        ans = next((a for a in answers if str(a["question_id"]) == ref
                    or norm_q(a.get("question") or "") == norm_q(nf.get("question") or "")), None) or {}
        not_found.append({"question_id": ans.get("question_id") or ref, "question": ans.get("question") or nf.get("question"),
                          "searched_scope": nf.get("searched_scope") or ans.get("searched_scope") or [],
                          "missing_evidence": nf.get("missing_evidence") or "未说明"})
    for op in ([o for o in (draft.get("operations") or []) if isinstance(o, dict)] if draft_ok else []):
        operations.append({"op": op.get("op") or op.get("operation") or "note",
                           "target": op.get("target") or op.get("doc_id") or op.get("path"),
                           "detail": op.get("detail") or op.get("note"), "evidence": op.get("evidence") or []})

    by_type, by_dir, meta_fields = {}, {}, set()
    for d in docs:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
        by_dir[d.get("dir") or "."] = by_dir.get(d.get("dir") or ".", 0) + 1
        meta_fields |= set(d.get("metadata") or {})
        if d.get("aliases"):
            meta_fields.add("aliases")
    duplicates = [{"doc_id": d["doc_id"], "path": d["path"], "dup_of": d["dup_of"],
                   "sha256_16": (d.get("sha256") or "")[:16], "size": d["size"],
                   "action": "kept both, marked byte-identical"} for d in docs if d.get("dup_of")]
    families = [{"family": r["family"], "current": r["current"],
                 "chain": [{"doc_id": v["doc_id"], "version": v["version"], "path": v["path"],
                            "sha256_16": v["sha256_16"]} for v in r["versions"]]}
                for r in state["relations"]]
    operations.append({"op": "index_build", "target": state["input"],
                       "detail": f"{len(docs)} files -> {len(chunks)} chunks; roots={state['roots']}",
                       "evidence": [f"{d['doc_id']}:{str(d.get('sha256'))[:16]}" for d in docs][:20]})
    for d in duplicates:
        operations.append({"op": "dedupe", "target": d["path"],
                           "detail": f"byte-identical to {d['dup_of']} ({d['sha256_16']})", "evidence": [d["doc_id"]]})
    for r in families:
        operations.append({"op": "version_group", "target": r["family"],
                           "detail": " -> ".join(f"{c['doc_id']}({c['version']})" for c in r["chain"])
                                     + f"; current={r['current']}",
                           "evidence": [c["path"] for c in r["chain"]]})
    for d in docs:
        if not d["readable"]:
            operations.append({"op": "skip_index", "target": d["path"],
                               "detail": d.get("note") or "no text layer",
                               "evidence": [f"permission={d['permission']}"]})

    verified = [e for e in evidence if e["quote_verified"]]
    coverage = {"questions_expected": len(state["questions"]), "answered_from_draft": len([a for a in answers if a.get("from_draft")]),
                "not_found": len(not_found), "docs_indexed": len(docs),
                "docs_readable": len([d for d in docs if d["readable"]]),
                "docs_unreadable": len([d for d in docs if not d["readable"]]),
                "docs_no_text_layer": len([d for d in docs if d.get("no_text_layer")]),
                "duplicates": len(duplicates), "version_families": len(families),
                "evidence_total": len(evidence), "evidence_verified": len(verified),
                "quote_hit_rate": round(len(verified) / len(evidence), 4) if evidence else 0.0,
                "questions_without_evidence": [a["question_id"] for a in answers
                                               if not any(c["evidence_count"] for c in a["claims"])]}
    six = {"file_types": by_type, "metadata_fields": sorted(meta_fields), "directories": by_dir,
           "duplicates": len(duplicates), "version_families": len(families),
           "permissions": {p: len([d for d in docs if d["permission"] == p])
                           for p in {d["permission"] for d in docs}} if docs else {}}
    if not draft_ok:
        degradations.append({"stage": "build", "item": "draft.json",
                             "detail": "工作稿缺失或不可解析：走兜底交付",
                             "impact": "answers 为结构占位并标缺证；清单/版本/重复仍完整"})
    elif coverage["answered_from_draft"] < coverage["questions_expected"]:
        degradations.append({"stage": "build", "item": "coverage",
                             "detail": f"{coverage['questions_expected'] - coverage['answered_from_draft']} 个问题无工作稿答案",
                             "impact": "these answers are placeholders, not negative findings"})
    status = "ok"
    if not draft_ok:
        status = "partial" if docs or answers else "failed"
    elif coverage["answered_from_draft"] < coverage["questions_expected"] or coverage["quote_hit_rate"] < 1.0 \
            or coverage["docs_unreadable"] or not_found or conflicts:
        status = "partial"
    payload = {
        "case_id": state.get("case_id"), "task_instruction": state.get("task_instruction"),
        "status": status,
        "summary": {"documents": len(docs), "readable": coverage["docs_readable"],
                    "unreadable": coverage["docs_unreadable"], "version_families": len(families),
                    "duplicates": len(duplicates), "questions": coverage["questions_expected"],
                    "answered_from_draft": coverage["answered_from_draft"],
                    "evidence_verified": len(verified), "quote_hit_rate": coverage["quote_hit_rate"],
                    "conflicts": len(conflicts), "not_found": len(not_found),
                    "text": f"索引 {len(docs)} 文件（可读 {coverage['docs_readable']}）、{len(families)} 版本族、"
                            f"{len(duplicates)} 副本；{coverage['answered_from_draft']}/{coverage['questions_expected']} 题有工作稿答案；"
                            f"引文逐字通过 {len(verified)}/{len(evidence)}；冲突 {len(conflicts)}、缺证 {len(not_found)}。"},
        "result": {"library": {"roots": state["roots"], "six_dimensions": six, "documents": docs,
                               "version_relations": families, "duplicates": duplicates},
                   "answers": answers, "evidence": evidence, "conflicts": conflicts,
                   "not_found": not_found, "operations": operations, "coverage": coverage},
        "documents": docs, "version_relations": families, "duplicates": duplicates,
        "metadata": {"fields": sorted(meta_fields),
                     "by_document": {d["doc_id"]: d.get("metadata") or {} for d in docs if d.get("metadata")}},
        "questions": state["questions"], "answers": answers, "evidence": evidence,
        "conflicts": conflicts, "not_found": not_found, "operations": operations, "coverage": coverage,
        "sources": state.get("sources") or [],
        "uncertainties": [{"question_id": a["question_id"], "level": a["uncertainty_level"],
                           "missing_evidence": a.get("missing_evidence")}
                          for a in answers if a["uncertainty_level"] != "none"],
        "errors": errors, "degradations": degradations, "changes": changes,
        "counts": {"documents": len(docs), "chunks": len(chunks),
                   "claims": sum(len(a["claims"]) for a in answers), "evidence": len(evidence),
                   "quote_verified": len(verified), "quote_hit_rate": coverage["quote_hit_rate"],
                   "conflicts": len(conflicts), "not_found": len(not_found), "operations": len(operations)},
        "method_notes": {
            "index": "逐文件解析（PDF: pdftotext 或 zlib 流解码；Office: zipfile+XML；文本: 编码回退），按页/节切块留 locator。",
            "versions": "版本记号 → 内嵌日期 → mtime 排族；sha256 相同判副本，保留并标注。",
            "evidence": "引文须逐字命中（空白/引号归一），页码章节以命中位置为准，未命中标 quote_verified=false。",
            "absence": "无逐字依据写 not_in_kb/insufficient + searched_scope + missing_evidence，不用常识补写。",
            "compare": "同输入下基础 Agent 多为整段转述；本包逐条定位与命中率可逐条对照。"},
        "verification": {},
        "runtime": {"version": VERSION, "python": sys.version.split()[0],
                    "seconds": round(time.time() - t0, 2),
                    "budget": {"script_calls": "init/show/check/build/selfcheck", "model_calls_in_script": 0,
                               "wall_clock_target_s": 900}},
        "contract_keys": sorted((state.get("contract") or {}).keys()),
        "question_ids": [q.get("question_id") for q in state["questions"]],
    }
    payload.update(backfill(state.get("contract") or {}, payload)[0])
    payload["contract_map"] = backfill(state.get("contract") or {}, payload)[1]
    payload["verification"] = verify_payload(payload)
    return payload


def verify_payload(payload):
    keys = payload.get("contract_keys") or []
    ev = payload.get("evidence") or []
    answers = payload.get("answers") or []
    checks = {"contract_keys_present": all(k in payload for k in keys), "contract_keys": len(keys),
              "answers_count": len(answers), "questions_count": len(payload.get("question_ids") or []),
              "evidence_total": len(ev),
              "quote_hit_rate": round(len([e for e in ev if e.get("quote_verified")]) / len(ev), 4) if ev else 0.0,
              "every_answer_has_locator": all(
                  any(c.get("evidence") for c in (a.get("claims") or []))
                  or (a.get("claims") and all(c.get("status") in ("not_in_kb", "insufficient")
                                              for c in a["claims"]) and bool(a.get("missing_evidence")))
                  for a in answers),
              "no_anonymous_source": all(e.get("doc_id") for e in ev),
              "status": payload.get("status")}
    checks["pass"] = bool(checks["contract_keys_present"] and checks["every_answer_has_locator"])
    return checks


# --------------------------------------------------------------------- rendering
def backfill(contract, payload):
    filled, mapping = {}, {}
    for key, hint in (contract or {}).items():
        low, val, hit = str(key).lower(), None, None
        for target, needles in CONTRACT_RULES:
            if any(nd in low for nd in needles):
                val, hit = payload.get(target), target
                break
        if val is None and isinstance(hint, list):
            val = []
        if val is not None:
            if isinstance(hint, list) and not isinstance(val, list):
                val = [val]
            if isinstance(hint, dict) and not isinstance(val, dict):
                val = {"value": val}
            if isinstance(hint, str) and isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)[:6000]
        filled[key] = val
        mapping[key] = hit or "null"
    return filled, mapping
