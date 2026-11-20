#!/usr/bin/env python3
"""pipeline.py - analysis orchestration for search-10: discovery -> candidates -> cards ->
accounting -> human-readable deliverables.

Judgement stays in the operator draft; this module only turns it (and the deterministic
candidates) into structured artifacts and reviewable prose.
"""
import json
import re

import cards as CD
import views as VW

def salvage_case(p, st):
    """Regex/brace salvage for a truncated or malformed case.json: keep case_id and contract."""
    txt = VW.read_text(p)
    obj = {}
    m = re.search(r'"case_id"\s*:\s*"([^"]{1,80})"', txt)
    if m:
        obj["case_id"] = m.group(1)
    m = re.search(r'"(output_contract|output_spec|contract)"\s*:\s*\{', txt)
    if m:
        i0, depth = m.end() - 1, 0
        for i in range(i0, len(txt)):
            if txt[i] == "{":
                depth += 1
            elif txt[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj[m.group(1)] = json.loads(txt[i0:i + 1])
                    except ValueError:
                        pass
                    break
    if obj:
        st["degradations"].append({"item": p.name, "stage": "case_parse",
                                   "action": "regex/brace salvage of case_id and contract",
                                   "impact": "task_instruction may be incomplete"})
    return obj or None


def load_case(inp, st):
    cands = [inp / n for n in ("case.json", "case_input.json", "input.json")
             if (inp / n).is_file()]
    for p in sorted(inp.glob("*.json")):
        if p in cands:
            continue
        obj = VW.read_json_any(p)
        if isinstance(obj, dict) and ({"output_contract", "task_instruction", "case_id"} & set(obj)):
            cands.append(p)
    for p in cands:
        obj = VW.read_json_any(p)
        if isinstance(obj, dict):
            return obj, p
        st["errors"].append({"stage": "case_parse", "path": str(p), "message": "not a JSON object"})
        sv = salvage_case(p, st)
        if sv:
            return sv, p
    st["degradations"].append({"item": "case.json", "stage": "input",
                               "action": "missing or unparsable",
                               "impact": "case_id/output_contract unknown"})
    return None, None


def task_text(inp):
    for n in ("task.md", "task_instruction.md", "prompt.md"):
        if (inp / n).is_file():
            return VW.read_text(inp / n)
    for p in sorted(inp.glob("*.md")):
        return VW.read_text(p)
    return ""


def contract_of(case):
    if not isinstance(case, dict):
        return {}
    for k in ("output_contract", "output_spec", "contract", "outputs"):
        if isinstance(case.get(k), dict):
            return case[k]
    return {}


def load_draft(work):
    for n in ("draft.json", "plan.json", "work.json"):
        p = work / n
        if p.is_file():
            obj = VW.read_json_any(p)
            if isinstance(obj, dict):
                return obj
    return None


def analyse(inp, st, draft=None):
    case, _ = load_case(inp, st)
    st["case_id"] = (case.get("case_id") or case.get("id")) if isinstance(case, dict) else None
    st["contract"] = contract_of(case)
    txt = task_text(inp)
    views, sources = VW.discover(inp, st)
    VW.dedup(views, st)
    if draft:
        CD.apply_view_labels(views, draft)
        for v in views:
            for c in v.get("label_conflicts") or []:
                st["uncertainties"].append({
                    "id": "U-lbl-%s-%s" % (v["view_id"], c["field"]), "type": "label_conflict",
                    "object": v["view_id"], "description": "脚本 %s=%s；工作稿 %s"
                    % (c["field"], c["script"], c["agent"]),
                    "impact": "答题卡采用工作稿标注，原始判定留在指纹台账",
                    "quote": str(c.get("basis"))})
    qs = CD.split_questions(case, txt)
    if not qs:
        st["degradations"].append({"item": "questions", "stage": "parse",
                                   "action": "case.json/task.md 里没切出 known-item 问题",
                                   "impact": "答题卡无法生成；请在 draft.json 手写 "
                                             "questions[] 与 matches[]"})
    for v in views:
        if v.get("work_id_basis") == "filename":
            st["uncertainties"].append({
                "id": "U-wid-%s" % v["view_id"], "type": "work_grouping_uncertain",
                "object": v["view_id"],
                "description": "视图既无 work_id 也无 DOI，work 归属只能由文件名推断",
                "impact": "可能把同一论文的不同语种视图算成两篇；按 DOI/标题人工确认",
                "quote": v.get("locator")})
    by_id = {v["view_id"]: v for v in views}
    ctx = {"views": views, "by_id": by_id, "questions": qs, "sources": sources, "feats": {},
           "cands": {}, "case_loaded": isinstance(case, dict)}
    for q in qs:
        f = CD.q_features(q["text"])
        ctx["feats"][q["question_id"]] = f
        ql = CD._dlang(q, draft) or VW.detect_lang(q["text"])["detected"]
        rows = CD.score_views(f, views, ql)
        ctx["cands"][q["question_id"]] = {"source_lang": ql, "rows": rows[:12],
                                          "works": CD.rank_works(rows, views, ql, [c["cid"] for c in f["concepts"]])[:5]}
    return ctx


def cards_of(ctx, st, draft, okmap):
    out = []
    for q in ctx["questions"]:
        c = ctx["cands"][q["question_id"]]
        try:
            out.append(CD.build_card(q, ctx["views"], ctx["by_id"], c["rows"], c["works"],
                                     draft, okmap))
        except Exception as e:  # noqa: BLE001 - isolate one bad card
            st["errors"].append({"stage": "card", "question_id": q["question_id"],
                                 "message": "%s: %s" % (type(e).__name__, str(e)[:160])})
            out.append({"question_id": q["question_id"], "question_text": q["text"],
                        "question_locator": q["locator"], "status": "not_found",
                        "confidence": "low", "target_view": None,
                        "misses": {"reason": "card_assembly_failed", "detail": str(e)[:200]}})
    return out


def evidence_of(cards):
    ev = []
    for c in cards:
        ch = c.get("evidence_chain") or {}
        vid = (c.get("target_view") or {}).get("view_id")
        for key in ("doi_anchor", "title_anchor", "body_quote"):
            it = ch.get(key)
            if isinstance(it, dict) and it.get("quote"):
                ev.append({"question_id": c["question_id"], "kind": key, "quote": it["quote"],
                           "locator": it.get("locator"), "verified": bool(it.get("verified")),
                           "view_id": vid})
        for p in ch.get("term_alignment") or []:
            ev.append({"question_id": c["question_id"], "kind": "term_alignment",
                       "quote": p.get("target_quote"), "locator": p.get("target_locator"),
                       "source_term": p.get("source_term"), "target_term": p.get("target_term"),
                       "concept": p.get("concept"), "verified": bool(p.get("verified")),
                       "view_id": vid})
    return ev


def routing_rows(cards):
    rows = []
    for c in cards:
        tv = c.get("target_view") or {}
        rows.append({"question_id": c["question_id"], "source_lang": c.get("source_language"),
                     "target_langs": c.get("target_languages"),
                     "glossary_concepts": sorted({cid for q in
                                                  (c.get("queries_by_lang") or {}).values()
                                                  for cid in (q.get("concept_ids") or [])}),
                     "queries_by_lang": c.get("queries_by_lang") or {},
                     "hit_view": tv.get("view_id"), "hit_language": tv.get("language"),
                     "hits_by_lang": ({tv["language"]: 1} if tv.get("language") else {}),
                     "status": c.get("status")})
    return rows


def reconcile(ctx, cards):
    cnt = VW.counts(ctx["views"])
    found = [c for c in cards if (c.get("target_view") or {}).get("view_id")]
    works = sorted({c["target_view"]["work_id"] for c in found})
    dups = sorted({d for c in found for d in (c.get("dedup") or {})
                   .get("duplicate_views_excluded", [])})
    gaps = []
    for c in cards:
        if c.get("status") != "found":
            gaps.append({"question_id": c["question_id"], "status": c.get("status"),
                         "reason": (c.get("misses") or {}).get("reason") or "见答题卡 misses"})
        for p in (c.get("false_positive_check") or {}).get("risks") or []:
            gaps.append({"question_id": c["question_id"], "status": "review",
                         "reason": "回译风险: %s / %s" % (p.get("concept"),
                                                         p.get("target_term"))})
    return {"counting_policy": "按 work_id 去重计 1 条；重复视图保留在台账但不计入命中",
            "views_total": cnt["views_total"], "distinct_works": cnt["distinct_works"],
            "views_matched": len({c["target_view"]["view_id"] for c in found}),
            "counted_hits": len(works), "works_hit": works, "duplicates_excluded": dups,
            "views_per_work": cnt["views_per_work"], "by_language": cnt["by_language"],
            "false_positive_verdicts": [{"question_id": c["question_id"],
                                         "verdict": (c.get("false_positive_check") or {})
                                         .get("verdict"),
                                         "pairs_checked": (c.get("false_positive_check") or {})
                                         .get("pairs_checked"),
                                         "risks": len((c.get("false_positive_check") or {})
                                                      .get("risks") or [])} for c in cards],
            "gaps": gaps}


def coverage_of(ctx, cards, draft, qrep):
    found = [c for c in cards if (c.get("target_view") or {}).get("view_id")]
    ev = evidence_of(cards)
    ver = [e for e in ev if e["verified"]]
    return {"questions_total": len(ctx["questions"]), "cards_total": len(cards),
            "cards_found": len(found), "cards_not_found": len(cards) - len(found),
            "views_total": len(ctx["views"]),
            "views_labeled_by_agent": len([v for v in ctx["views"]
                                           if v.get("label_source") == "agent_draft"]),
            "views_with_duplicate_flag": len([v for v in ctx["views"] if v.get("duplicate_of")]),
            "evidence_records": len(ev), "evidence_quote_verified": len(ver),
            "quote_verified_rate": round(len(ver) / float(len(ev)), 3) if ev else 0.0,
            "draft_present": bool(draft),
            "draft_quotes_verified": len([q for q in qrep if q.get("verified")]),
            "draft_quotes_total": len(qrep)}


def routing_md(rows, cards):
    L = ["# 语种路由表（lang_routing）", "",
         "每题一行：源语种 → 目标语种 → 术语表子集 → 逐语种查询式 → 该语种命中。",
         "查询式由内置术语表推导（离线、不调用翻译服务），可逐条复核。", "",
         "| 题号 | 源语种 | 目标语种 | 术语表概念 | 命中视图 | 状态 |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            r["question_id"], r.get("source_lang"), ",".join(r.get("target_langs") or []),
            ",".join(r.get("glossary_concepts") or []) or "-", r.get("hit_view") or "-",
            r.get("status")))
    L += ["", "## 逐语种查询式", ""]
    for c in cards:
        L.append("### %s（源语种 %s）" % (c["question_id"], c.get("source_language")))
        L.append("")
        for lg, q in sorted((c.get("queries_by_lang") or {}).items()):
            L.append("- `%s` → `%s`（%s）" % (lg, q.get("query"), q.get("template")))
        L.append("")
    return "\n".join(L) + "\n"


def recon_md(rec, ctx, st):
    L = ["# 去重与复核（reconciliation）", "", "## 1. 计数口径", "", "- " + rec["counting_policy"],
         "", "| 指标 | 值 |", "|---|---|",
         "| views_total | %s |" % rec["views_total"],
         "| distinct_works | %s |" % rec["distinct_works"],
         "| views_matched | %s |" % rec["views_matched"],
         "| counted_hits | %s |" % rec["counted_hits"],
         "| duplicates_excluded | %s |" % (",".join(rec["duplicates_excluded"]) or "-"),
         "", "## 2. 视图指纹台账", "",
         "| view_id | work | lang | version | doc_type | dup_of | locator |",
         "|---|---|---|---|---|---|---|"]
    for v in ctx["views"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |"
                 % (v["view_id"], v["work_id"], v["language"], v["version"], v["doc_type"],
                    v.get("duplicate_of") or "-", v.get("locator")))
    L += ["", "## 3. 误译/假阳性抽检", "", "| 题号 | 判定 | 检查对数 | 风险数 |", "|---|---|---|---|"]
    for f in rec["false_positive_verdicts"]:
        L.append("| %s | %s | %s | %s |" % (f["question_id"], f["verdict"], f["pairs_checked"],
                                            f["risks"]))
    L += ["", "## 4. 缺口与未完成", ""]
    L += ["- `%s`：%s（%s）" % (g["question_id"], g["status"], g["reason"]) for g in rec["gaps"]] \
        or ["- 无：全部问题都有可复核命中，术语回译未发现风险。"]
    L += ["", "## 5. 运行痕迹", "",
          "- errors %d ｜ degradations %d ｜ uncertainties %d"
          % (len(st["errors"]), len(st["degradations"]), len(st["uncertainties"])),
          "- 复算：`python3 scripts/main.py build` 重跑，除 runtime 外结果一致。", ""]
    return "\n".join(L)


def claims_of(cards, qrep):
    out = []
    for c in cards:
        tv = c.get("target_view") or {}
        bq = (c.get("evidence_chain") or {}).get("body_quote") or {}
        out.append({"claim_id": "C-%s" % c["question_id"], "kind": "reported",
                    "statement": "%s -> %s" % (c["question_id"], ("%s/%s (%s,%s)" % (
                        tv.get("work_id"), tv.get("view_id"), tv.get("language"),
                        tv.get("version"))) if tv else "未找到达标命中(%s)" % c.get("status")),
                    "source_id": tv.get("view_id"), "location": tv.get("locator"),
                    "quote": bq.get("quote"), "quote_verified": bool(bq.get("verified")),
                    "confidence": c.get("confidence"), "status": c.get("status")})
    for q in qrep:
        if not q.get("verified"):
            out.append({"claim_id": "C-Q-%s" % q.get("question_id"), "kind": "inferred",
                        "statement": "工作稿引用未逐字命中材料", "source_id": q.get("view_id"),
                        "location": q.get("locator"), "quote": q.get("quote"),
                        "quote_verified": False, "confidence": "low", "status": "needs_human"})
    return out
