#!/usr/bin/env python3
"""checks.py -- mechanical validation of the Agent's work/draft.json.

Every check is deterministic and points at a concrete FIX location. Nothing here
judges scientific meaning; it judges whether the draft can be re-run and audited:
verbatim quotes, anchor page, note support, link basis, query coverage, contract.
Exit code is always 0.
"""
import json
import re
from pathlib import Path

import extract as X
from main import ARTIFACTS, paths, load_index, find_case

LOW_CONF = 0.5


def load_draft(wk, a):
    p = Path(getattr(a, "draft", None) or (wk / "draft.json"))
    if not p.exists():
        return {}, ""
    try:
        d = X.jread(p)
        return (d if isinstance(d, dict) else {"_err": "draft root is not an object"}), str(p)
    except Exception as e:
        return {"_err": repr(e)}, str(p)


def d_anns(dr):
    for k in ("annotation_judgements", "annotations", "ann_judgements", "annotation_notes"):
        if isinstance(dr.get(k), list):
            return [x for x in dr[k] if isinstance(x, dict)]
    return []


def d_list(dr, *keys):
    for k in keys:
        if isinstance(dr.get(k), list):
            return [x for x in dr[k] if isinstance(x, dict)]
        if isinstance(dr.get(k), dict):
            return [dict(v, qid=v.get("qid") or kk) for kk, v in dr[k].items() if isinstance(v, dict)]
    return []


def match_ann(anns, item):
    aid = str(item.get("ann_id") or item.get("id") or "")
    by = {x["ann_id"]: x for x in anns}
    if aid and aid in by:
        return by[aid]
    q = X.norm(item.get("quoted_text") or item.get("quote") or "", True)
    if q:
        for x in anns:
            t = X.norm(x.get("quoted_text") or "", True)
            if t and (q in t or t in q):
                return x
    return None


def validate(dr, idx):
    docs, anns = idx.get("docs") or {}, idx.get("annotations") or []
    by = {x["ann_id"]: x for x in anns}
    pmap = {k: {pg["page"]: (pg.get("text") or "") for pg in v} for k, v in (idx.get("pages") or {}).items()}
    rep = {"errors": [], "warnings": [], "counts": {}}

    def err(c, d, w=""):
        rep["errors"].append({"code": c, "detail": d, "where": w})

    def warn(c, d, w=""):
        rep["warnings"].append({"code": c, "detail": d, "where": w})

    if dr.get("_err"):
        err("draft_unreadable", str(dr["_err"]), "draft")
    elif not dr:
        err("draft_missing", "work/draft.json absent: build will fall back to a degraded partial", "draft")
    judge = d_anns(dr)
    notes = d_list(dr, "notes")
    links = d_list(dr, "links")
    qs = d_list(dr, "queries", "query_answers", "retrieval")
    if dr and not dr.get("_err"):
        if not judge:
            warn("no_annotation_judgements", "没有批注判断：类型/颜色/引文判断需逐条写", "annotation_judgements")
        if not notes:
            warn("no_notes", "没有结构化笔记：section/claim/quote_support 至少一条", "notes")
        if not qs and (idx.get("queries") or []):
            warn("no_query_answers", "案例给出的检索问题未回答", "queries")
    confirmed = {x["ann_id"] for x in anns if x.get("anchor_confirmed")}
    for i, j in enumerate(judge):
        w = "ann[%d]" % i
        a = match_ann(anns, j)
        if not a:
            err("ann_unknown", "判断里的 ann_id 不在索引中: %r（先运行 show --ann）" % (j.get("ann_id"),), w)
            continue
        q = X.norm(j.get("quoted_text") or j.get("quote") or "")
        pages = pmap.get(a["doc_id"], {})
        if q:
            if not X.fq(pages.get(a["page"], ""), q)["found"]:
                hit = sorted(p for p, txt in pages.items() if X.fq(txt, q)["found"])
                if hit:
                    err("anchor_page_mismatch", "%s: 引文在 p%s 命中，但 draft 写 p%s（锚点错位）"
                        % (a["ann_id"], hit[0], a["page"]), w)
                elif not (pages.get(a["page"]) or "").strip():
                    warn("page_no_text", "%s: 该页无文本层，引文无法校验；请标低置信度" % a["ann_id"], w)
                else:
                    err("quote_not_found", "%s: 引文不在 p%s 文本中（逐字复制 show 输出，勿改写/拼接）"
                        % (a["ann_id"], a["page"]), w)
        elif a["ann_id"] in confirmed and a.get("type") not in ("margin_note", "handwritten", "region_mark"):
            warn("judgement_without_quote", "%s 有可锚定原文，但 draft 未给 quoted_text" % a["ann_id"], w)
        tc = X.norm(j.get("type_confirm") or j.get("type") or "")
        if tc and tc not in X.TYPES:
            err("bad_type", "type_confirm %r 不在枚举内" % tc, w)
        if tc and tc != a.get("type"):
            warn("type_relabelled", "%s: 抽取器判为 %s，Agent 改判为 %s（需有依据，如 legend/说明）"
                 % (a["ann_id"], a.get("type"), tc), w)
        c = j.get("anchor_confidence")
        if c is not None:
            try:
                if not (0 <= float(c) <= 1):
                    err("bad_confidence", "anchor_confidence 必须在 0..1", w)
            except Exception:
                err("bad_confidence", "anchor_confidence 不是数字", w)
    note_ids, edges, deg = set(), set(), {}
    for i, n in enumerate(notes):
        w, nid = "note[%d]" % i, str(n.get("note_id") or "N%d" % (i + 1))
        if nid in note_ids:
            err("duplicate_note_id", "note_id 重复: %s" % nid, w)
        note_ids.add(nid)
        if n.get("section") not in X.SECTIONS:
            err("bad_section", "%s: section %r 不在 %s" % (nid, n.get("section"), "|".join(X.SECTIONS)), w)
        if not X.norm(n.get("claim")):
            err("note_without_claim", "%s: claim 为空" % nid, w)
        sup = [s for s in (n.get("quote_support") or []) if isinstance(s, dict)]
        if not sup:
            err("note_without_support", "%s: 没有 quote_support——论断必须指到原文片段" % nid, w)
        for s in sup:
            a = by.get(str(s.get("ann_id") or ""))
            q = X.norm(s.get("quote") or s.get("quoted_text") or "")
            if not a:
                err("support_ann_unknown", "%s: 支撑引用未知批注 %r" % (nid, s.get("ann_id")), w)
                continue
            if not q:
                err("support_without_quote", "%s: 对 %s 的支撑没有引文" % (nid, a["ann_id"]), w)
                continue
            if not X.fq((pmap.get(a["doc_id"]) or {}).get(a["page"], ""), q)["found"] and \
                    not X.fq((idx.get("texts") or {}).get(a["doc_id"], ""), q)["found"]:
                err("support_quote_not_found", "%s: 支撑引文不在 %s 中" % (nid, a["doc_id"]), w)
            elif a.get("type") not in ("margin_note", "handwritten", "region_mark"):
                span = X.norm(a.get("quoted_text") or "", True)
                if span and X.norm(q, True) not in span:
                    warn("support_outside_annotation",
                         "%s: 引文在本页命中，但超出 %s 实际覆盖的原文（%s）——核对是否张冠李戴"
                         % (nid, a["ann_id"], span[:60]), w)
        for aid in (n.get("ann_ids") or []):
            if str(aid) not in by:
                err("note_ann_unknown", "%s: ann_ids 引用 %r 不在索引中" % (nid, aid), w)
    nodes = note_ids | set(by) | set(docs)
    for i, l in enumerate(links):
        w = "link[%d]" % i
        f, t = str(l.get("from") or ""), str(l.get("to") or "")
        rel = X.norm(l.get("relation") or l.get("type") or "")
        if f not in nodes or t not in nodes:
            err("link_unknown_node", "%s->%s: 端点必须是笔记/批注/doc_id" % (f, t), w)
        if f == t:
            err("link_self", "自环 %s" % f, w)
        if (f, t, rel) in edges:
            err("link_duplicate", "重复边 %s->%s[%s]" % (f, t, rel), w)
        edges.add((f, t, rel))
        if rel and rel not in X.RELS:
            err("bad_relation", "relation %r 不在枚举内" % rel, w)
        basis = X.norm(l.get("basis") or l.get("reason") or "")
        if len(basis) < 12:
            err("link_basis_thin", "%s->%s: basis 过短，必须说明为什么连（不能只写共享术语）" % (f, t), w)
        elif len(re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", basis)) < 8:
            err("link_basis_thin", "%s->%s: basis 无可核验内容" % (f, t), w)
        if f.startswith("N"):
            deg[f] = deg.get(f, 0) + 1
    for nid, c in deg.items():
        if c > 3:
            warn("over_connected", "%s 有 %d 条语义出边（上限 3）：控制过度连接" % (nid, c), nid)
    case_q = idx.get("queries") or []
    qids = {q["qid"] for q in case_q}
    answered = 0
    for i, q in enumerate(qs):
        w = "query[%d]" % i
        qid = str(q.get("qid") or q.get("id") or "")
        if qids and qid not in qids:
            warn("query_unknown_qid", "qid %r 不在案例问题 %s 中" % (qid, sorted(qids)), w)
        hits = [h for h in (q.get("hits") or []) if isinstance(h, dict)]
        bad = [h.get("note_id") for h in hits if str(h.get("note_id") or "") not in note_ids]
        if bad:
            err("query_hit_unknown", "%s: 命中了不存在的笔记 %s" % (qid, bad), w)
        if not hits and not X.norm(q.get("recall_note") or q.get("note") or ""):
            warn("query_no_hit_no_reason", "%s: 无命中且未写 recall_note" % qid, w)
        answered += 1 if hits else 0
    missing_q = sorted(qids - {str(q.get("qid") or "") for q in qs})
    if missing_q and notes:
        err("query_unanswered", "案例检索问题未回答: %s" % ", ".join(missing_q), "queries")
    covered = {x["ann_id"] for x in (match_ann(anns, j) for j in judge) if x}
    cn = rep["counts"]
    cn.update(annotations_indexed=len(anns), annotations_judged=len(covered), annotations_confirmed=len(confirmed),
              judge_coverage=round(len(covered) / max(len(anns), 1), 3), notes=len(notes),
              notes_with_support=len([n for n in notes if n.get("quote_support")]), links=len(links),
              queries_case=len(case_q), queries_answered=answered,
              quote_checked=len([j for j in judge if X.norm(j.get("quoted_text") or "")]),
              low_confidence_annotations=len([x for x in anns if not x.get("anchor_confirmed")]))
    bad_q = len([e for e in rep["errors"] if e["code"] in ("quote_not_found", "anchor_page_mismatch",
                                                           "support_quote_not_found")])
    cn["quote_pass_rate"] = round((cn["quote_checked"] - len(
        [e for e in rep["errors"] if e["code"] in ("quote_not_found", "anchor_page_mismatch")])) / max(cn["quote_checked"], 1), 3)
    cn["quote_errors"] = bad_q
    if cn["judge_coverage"] < 0.8 and anns:
        rep["warnings"].append({"code": "low_judge_coverage", "where": "annotation_judgements",
                                "detail": "只判断了 %.0f%% 的批注；覆盖不足会拉低完整性与可核验性"
                                          % (100 * cn["judge_coverage"])})
    rep["ok"] = not rep["errors"]
    return rep


def selfcheck(a):
    inp, outp, wk = paths(a)
    rep = {"ok": True, "checks": {}, "errors": []}

    def fail(code, detail):
        rep["ok"] = False
        rep["errors"].append({"code": code, "detail": detail})

    try:
        res = X.jread(outp / "result.json")
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [{"code": "result_unreadable", "detail": repr(e)}]},
                         ensure_ascii=False, indent=1))
        return 0
    idx = load_index(wk)
    case, _ = find_case(inp, []) if inp.exists() else ({}, None)
    keys = X.contract_keys(case.get("output_contract"))
    missing = [k for k in keys if k not in res]
    rep["checks"].update(contract_keys=len(keys), contract_missing=missing)
    if missing:
        fail("contract_missing", missing)
    anns, notes = [], []
    for f, tgt in (("annotations.jsonl", anns), ("notes.jsonl", notes)):
        try:
            tgt += [json.loads(x) for x in (outp / f).read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception as e:
            fail(f.replace(".", "_") + "_unreadable", repr(e))
    pmap = {k: {pg["page"]: (pg.get("text") or "") for pg in v} for k, v in (idx.get("pages") or {}).items()}
    okq, bad = 0, []
    for x in anns:
        q = x.get("quoted_text") or ""
        if not q:
            continue
        page_t = (pmap.get(x.get("doc_id")) or {}).get(x.get("page"), "")
        if X.fq(page_t, q)["found"] or X.fq((idx.get("texts") or {}).get(x.get("doc_id"), ""), q)["found"]:
            okq += 1
        else:
            bad.append(x.get("ann_id"))
    rep["checks"].update(
        annotations=len(anns), quotes_checked=len([x for x in anns if x.get("quoted_text")]),
        quote_hit_rate=round(okq / max(len([x for x in anns if x.get("quoted_text")]), 1), 3),
        quote_miss=bad[:10], low_confidence=len([x for x in anns if x.get("low_confidence")]),
        notes=len(notes), notes_without_support=[n.get("note_id") for n in notes if not n.get("quote_support")],
        status=res.get("status"))
    links = (X.jread(outp / "links.json") or {}).get("links") if (outp / "links.json").exists() else []
    qs = (X.jread(outp / "queries.json") or {}).get("queries") if (outp / "queries.json").exists() else []
    rep["checks"].update(links=len(links or []),
                         links_without_basis=[l.get("link_id") for l in (links or []) if len(X.norm(l.get("basis"))) < 12],
                         queries=len(qs or []), queries_answered=len([q for q in (qs or []) if q.get("hits")]))
    arts = {f: ((outp / f).exists() and (outp / f).stat().st_size > 0) for f in ARTIFACTS}
    rep["checks"]["artifacts"] = arts
    if not all(arts.values()):
        fail("artifact_empty", [k for k, v in arts.items() if not v])
    if bad:
        fail("quote_miss", bad[:10])
    if res.get("status") not in ("ok", "partial", "insufficient_evidence", "input_error"):
        fail("bad_status", res.get("status"))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


def run(a):
    from main import paths, load_index, GEN
    _, _, wk = paths(a)
    dr, src = load_draft(wk, a)
    idx = load_index(wk)
    if not idx:
        print(json.dumps({"ok": False, "errors": [{"code": "no_index", "detail": "run init first"}]},
                         ensure_ascii=False, indent=1))
        return
    rep = validate(dr, idx)
    rep["counts"]["draft"] = src or "(absent)"
    rep["counts"]["skill"] = GEN
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    for e in rep["errors"][:16]:
        print("FIX [%s] %s :: %s" % (e["code"], e["where"], e["detail"]))
    for w in rep["warnings"][:8]:
        print("WARN [%s] %s :: %s" % (w["code"], w["where"], w["detail"]))
    cn = rep["counts"]
    print("judge_coverage=%s quote_pass=%s errors=%d warnings=%d notes=%s support=%s links=%s queries=%s/%s" % (
        cn["judge_coverage"], cn["quote_pass_rate"], len(rep["errors"]), len(rep["warnings"]),
        cn["notes"], cn["notes_with_support"], cn["links"], cn["queries_answered"], cn["queries_case"]))
    if rep["errors"]:
        print("-- 修改 %s 后重跑 check；build 仍会执行，但会把这些缺口写进 degradations" % (src or "draft.json"))
