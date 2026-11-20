#!/usr/bin/env python3
"""verify.py - mechanical validation of the operator draft and of assembled deliverables.

Nothing here judges relevance; it only proves that what the draft claims can be re-checked
against the actual materials: quote hit, locator resolvable, coverage, dedup arithmetic.
"""
import re

import views as VW

def draft_checks(draft, views, views_by_id, questions):
    checks = []

    def add(cid, ok, detail, level="warn"):
        checks.append({"id": cid, "ok": bool(ok), "detail": detail,
                       "level": "info" if ok else level})

    if not isinstance(draft, dict) or not draft:
        add("D0", False, "工作稿缺失或不是 JSON 对象（/app/work/draft.json 未写）")
        return checks
    qids = [q["question_id"] for q in questions]
    dq = {}
    for it in draft.get("questions") or []:
        if isinstance(it, dict):
            qid = VW.first_str(it, ("question_id", "id", "qid"))
            if qid:
                dq[qid] = it
    miss = [q for q in qids if q not in dq]
    add("D1", not miss, "问题条目覆盖 %d/%d%s" % (len(qids) - len(miss), len(qids),
                                                "；缺 %s" % miss if miss else ""))
    no_lang = [k for k, v in dq.items() if not VW.first_str(v, ("source_lang", "source_language"))]
    add("D2", not no_lang, "每题写 source_lang%s" % ("；缺 %s" % no_lang if no_lang else ""))
    no_tgt = [k for k, v in dq.items()
              if not isinstance(v.get("target_langs") or v.get("target_languages"), list)]
    add("D3", not no_tgt, "每题写 target_langs 列表%s" % ("；缺 %s" % no_tgt if no_tgt else ""))
    labeled = {}
    for it in draft.get("view_labels") or []:
        if isinstance(it, dict):
            vid = VW.first_str(it, ("view_id", "id"))
            if vid:
                labeled[vid] = it
    unl = [v["view_id"] for v in views if v["view_id"] not in labeled]
    add("D4", not unl, "视图标注覆盖 %d/%d%s" % (len(views) - len(unl), len(views),
                                                "；未标注 %s" % unl[:6] if unl else ""))
    unknown = [k for k in labeled if k not in views_by_id]
    add("D5", not unknown, "view_labels 的 view_id 都可解析%s"
        % ("；未知 %s" % unknown[:6] if unknown else ""))
    matched = [m for m in draft.get("matches") or [] if isinstance(m, dict)]
    oob = [m.get("question_id") for m in matched if m.get("question_id") not in qids]
    add("D6", not oob, "matches 的 question_id 都在题面内%s" % ("；越界 %s" % oob[:4] if oob else ""))
    badv = [m.get("view_id") for m in matched
            if m.get("view_id") and m.get("view_id") not in views_by_id]
    add("D7", not badv, "matches 的 view_id 可解析%s" % ("；未知 %s" % badv[:4] if badv else ""),
        "error")
    no_q = [m.get("question_id") for m in matched
            if not (isinstance(m.get("evidence"), dict) and m["evidence"].get("quote"))]
    add("D8", not no_q, "每条 match 都有逐字 quote%s" % ("；缺 %s" % no_q[:4] if no_q else ""))
    return checks


def quotes(draft, views, questions=None):
    """Every draft quote is looked up verbatim. Target-side quotes must come from materials;
    a source-side term may legitimately be taken from the question text itself."""
    quotes = []
    for m in (draft or {}).get("matches") or []:
        if not isinstance(m, dict):
            continue
        ev = m.get("evidence") if isinstance(m.get("evidence"), dict) else {}
        if isinstance(ev.get("quote"), str):
            quotes.append((m.get("question_id"), "evidence.quote", ev["quote"]))
        for p in ev.get("term_pairs") or []:
            if isinstance(p, dict):
                for k in ("target_quote", "quote", "source_quote"):
                    if isinstance(p.get(k), str):
                        quotes.append((m.get("question_id"), "term_pair." + k, p[k]))
    for f in (draft or {}).get("false_positive_checks") or []:
        if isinstance(f, dict) and isinstance(f.get("quote"), str):
            quotes.append((f.get("question_id"), "fp.quote", f["quote"]))
    qtext = {q["question_id"]: q["text"] for q in (questions or [])}
    res, okmap = [], {}
    for qid, where, q in quotes:
        hits = VW.find_quote(views, q)
        if not hits and where.endswith("source_quote"):
            src = qtext.get(qid) or ""
            if VW.norm(VW.low(q)) and VW.norm(VW.low(q)) in VW.norm(VW.low(src)):
                hits = [{"view_id": "question:%s" % qid, "work_id": None,
                         "locator": "case.json#task_instruction",
                         "language": None, "version": None}]
        okmap[VW.norm(q)] = bool(hits)
        res.append({"question_id": qid, "field": where, "quote": VW.norm(q)[:160],
                    "verified": bool(hits), "locator": hits[0]["locator"] if hits else None,
                    "view_id": hits[0]["view_id"] if hits else None})
    return res, okmap


def dedup_checks(draft, views):
    cnt = VW.counts(views)
    note = (draft or {}).get("dedup_note")
    note = note if isinstance(note, dict) else {}
    problems = []
    dw = note.get("distinct_works")
    if isinstance(dw, int) and dw != cnt["distinct_works"]:
        problems.append({"field": "distinct_works", "draft": dw, "script": cnt["distinct_works"]})
    ch = note.get("counted_hits")
    if isinstance(ch, int):
        found = len([m for m in (draft or {}).get("matches") or []
                     if isinstance(m, dict) and m.get("view_id")])
        if ch > cnt["distinct_works"]:
            problems.append({"field": "counted_hits_exceeds_distinct_works", "draft": ch,
                             "script": cnt["distinct_works"]})
        elif found and ch != found:
            problems.append({"field": "counted_hits_vs_matches", "draft": ch, "script": found})
    return cnt, problems


def backtranslate(pairs, gloss=None):
    """Glossary inverse back-translation: does the target term map back to the source term?"""
    risks, passed = [], 0
    for p in pairs:
        cid = p.get("concept_id")
        cands = set()
        if gloss and cid in gloss:
            cands |= {VW.norm(VW.low(s)) for s in gloss[cid]["forms"].get(p.get("source_lang"), [])}
            cands.add(VW.norm(VW.low(p.get("target_term") or "")))
        back = VW.norm(VW.low(p.get("source_term") or ""))
        if cands and back in cands:
            passed += 1
        else:
            risks.append({"concept": p.get("concept"), "target_term": p.get("target_term"),
                          "back_translation_candidates": sorted(cands)[:4], "verdict": "review",
                          "reason": "术语表逆映射未覆盖该写法，可能词面对应而语义不同"})
    return {"method": "glossary_inverse_backtranslation(offline)",
            "service": "none (deterministic built-in glossary, no MT call)",
            "pairs_checked": len(pairs), "passed": passed, "risks": risks,
            "verdict": "pass" if pairs and not risks else ("review" if risks else "not_applicable")}
