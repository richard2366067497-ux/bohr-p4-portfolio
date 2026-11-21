#!/usr/bin/env python3
"""build.py -- render the annotation ledger + result.json from work/draft.json.

Agent-first contract: extraction (work/index.json) is authoritative for geometry,
page, colour and hashes; the Agent's draft supplies semantic judgement (types,
colour meaning, note claims, link bases, query answers). When the draft is absent
or incomplete the build still finalises a legal, honest, degraded deliverable.
Exit code is always 0.
"""
import time

import extract as X
from main import ARTIFACTS, GEN, LOW_CONF, envelope, find_case, load_index, paths

FILL = [("annotation|highlight|批注", "annotations"), ("note|笔记|digest", "notes"),
        ("link|relat|关联", "links"), ("quer|search|question|检索", "queries"),
        ("index|retriev|索引入口", "index"), ("file|document|inventory|manifest|清单|文件", "files"),
        ("provenance|hash|audit|trace|哈希", "provenance"), ("coverage|stat|count|metric|quality|覆盖", "coverage"),
        ("summary|report|answer|overview|总结", "summary"), ("skip|fail|degrad|error|跳过|失败", "skipped"),
        ("version|alias|dup|版本|别名", "versions"), ("method|approach|方法", "method"),
        ("limit|uncertain|局限|不确定", "uncertainty"), ("artifact|output|产物", "artifacts"),
        ("casetitle|title|题目", "summary")]


def fill_contract(case, model):
    """Re-emit every output_contract key untouched; match semantically, then null/[]."""
    ct = case.get("output_contract")
    keys = X.contract_keys(ct) or list(model.get("_default_keys") or [])
    res, unfilled = {}, []
    for k in keys:
        kl = k.lower()
        if model.get(k) not in (None, "", [], {}):
            res[k] = model[k]
            continue
        v = next((model[x] for pat, x in FILL if __import__("re").search(pat, kl)
                  and model.get(x) not in (None, "", [], {})), None)
        if v is None:
            v = model.get(k, X.empty_like(ct.get(k) if isinstance(ct, dict) else None))
        res[k] = v
        if v in (None, "", [], {}):
            unfilled.append(k)
    return res, unfilled, keys


def stub_notes(anns, degr):
    """Honest fallback: no invented claims, only an explicit to_verify backlog note."""
    out, by_doc = [], {}
    for a in anns:
        by_doc.setdefault(a["doc_id"], []).append(a)
    for did, lst in sorted(by_doc.items()):
        sup = [{"ann_id": a["ann_id"], "quote": a["quoted_text"]} for a in lst
               if a.get("anchor_confirmed") and a.get("quoted_text")][:6]
        out.append({"note_id": "N%03d" % (len(out) + 1), "doc_id": did, "ann_ids": [a["ann_id"] for a in lst],
                    "section": "to_verify",
                    "claim": "待人工确认：本文件 %d 条批注尚未结构化归类（脚本未做任何语义判断）" % len(lst),
                    "tags": [], "quote_support": sup, "to_verify": "", "created_from": "fallback_stub"})
    if out:
        degr.append("draft.json 缺失/不完整：笔记退化为 to_verify 待办占位（未编造 claim），补写 draft 后重跑 build 可恢复")
    return out


def fallback_queries(case_q, notes, degr):
    """Symbolic retrieval over tags/terms when the Agent did not answer."""
    df = {}
    for n in notes:
        for t in X.tokens((n.get("claim") or "") + " " + " ".join(n.get("tags") or [])):
            df[t] = df.get(t, 0) + 1
    out = []
    for q in case_q:
        ts = X.tokens(q["question"])
        scored = []
        for n in notes:
            body = X.tokens((n.get("claim") or "") + " " + " ".join(n.get("tags") or []) + " "
                            + " ".join(s.get("quote") or "" for s in (n.get("quote_support") or [])))
            sc = sum(1.0 / (1 + df.get(t, 1)) for t in ts if t in body)
            if sc > 0:
                scored.append((round(sc, 2), n))
        scored.sort(key=lambda x: -x[0])
        hits = [{"note_id": n["note_id"], "locator": (n.get("quote_support") or [{}])[0].get("ann_id") or "",
                 "why": "术语/标签重合 score=%.2f" % sc, "score": sc} for sc, n in scored[:5]]
        out.append({"qid": q["qid"], "question": q["question"], "answered": bool(hits), "hits": hits,
                    "answered_by": "script_fallback",
                    "recall_note": "脚本按标签/术语倒排兜底，未做语义判断；同义术语召回可能不足" if hits
                                   else "无术语命中：需人工确认该问题是否超出本库批注范围"})
    if case_q:
        degr.append("%d 个检索问题由脚本兜底（answered_by=script_fallback），语义相关性未由 Agent 确认" % len(case_q))
    return out


def build_inverted(notes, anns):
    inv = {"tags": {}, "topics": {}, "sources": {}, "pages": {}}
    for n in notes:
        for t in (n.get("tags") or []):
            inv["tags"].setdefault(str(t), []).append(n["note_id"])
        for t in sorted(X.tokens(n.get("claim") or ""))[:40]:
            inv["topics"].setdefault(t, []).append(n["note_id"])
        for s in (n.get("quote_support") or []):
            a = next((x for x in anns if x["ann_id"] == s.get("ann_id")), None)
            if a:
                inv["pages"].setdefault("%s@p%s" % (a["doc_id"], a.get("page")), []).append(n["note_id"])
                inv["sources"].setdefault(a["doc_id"], []).append(n["note_id"])
    out = {}
    for k, v in inv.items():
        out[k] = {kk: sorted(set(vv)) for kk, vv in v.items()}
        out[k + "_doc_freq"] = {kk: len(set(vv)) for kk, vv in v.items()}
    out["entry_points"] = {"by_tag": sorted(out["tags"])[:24], "by_source": sorted(out["sources"]),
                           "by_page": sorted(out["pages"])[:30],
                           "how_to": "按 tag / 来源 doc_id / 页码 locator 精确召回；doc_freq 高的泛词不作过滤条件，避免误召回"}
    return out


def cell(v):
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")[:220]


def render_ledger(cid, status, files, anns, notes, links, queries, cov, idx, degr, sem):
    L = ["# 阅读批注账本 · %s" % cid, "",
         "> status **%s** ｜ 文件 %d ｜ 批注 %d（锚定 %d / 低置信 %d）｜ 笔记 %d ｜ 关联 %d（语义 %d）｜ 检索 %d/%d" % (
             status, len(files), len(anns), cov["annotations_anchored"], cov["annotations_low_confidence"],
             len(notes), len(links), sem, cov["queries_answered"], cov["queries_total"]),
         "", "## 1. 文件账本（哈希 / 版本 / 别名 / 重复）", "",
         "| doc_id | 文件 | 类型 | 页 | 文本层 | sha256 | 版本 | 别名组 | 重复 |", "|---|---|---|---|---|---|---|---|---|"]
    for f in files:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            f["doc_id"], cell(f["file"]), f["kind"], f["pages"], f["has_text_layer"], (f["sha256"] or "")[:12],
            f["version"] or "-", f["alias_group"] or "-", f["duplicate_of"] or "-"))
    if idx.get("aliases"):
        L += ["", "版本/别名候选（脚本按文件名归一+版本号判定；是否同一文献由 Agent 在 `version_judgements` 确认）："]
        for g in idx["aliases"]:
            L.append("- **%s** %s → canonical `%s` ｜ chain: %s" % (
                g["group"], ", ".join(g["docs"]), g["canonical"],
                " → ".join("%s(v%s)" % (c["doc_id"], c["version"] or "?") for c in g["chain"])))
    if idx.get("version_notes"):
        L += ["", "行政版本说明（原文行，供复核）："]
        L += ["- [%s] %s" % (n.get("source") or n.get("locator"), n["note"][:220]) for n in idx["version_notes"][:12]]
    L += ["", "## 2. 批注账本（逐条可回到页与位置）", "",
          "| ann_id | doc | 页 | 类型 | 颜色 | 锚定方法 | 置信 | 原文 / 候选 |", "|---|---|---|---|---|---|---|---|"]
    for a in anns:
        L.append("| %s | %s | p%s | %s | %s | %s | %.2f%s | %s |" % (
            a["ann_id"], a["doc_id"], a.get("page"), a.get("type"), a.get("color") or "-", a.get("anchor_method"),
            float(a.get("anchor_confidence") or 0), "" if a.get("anchor_confirmed") else " ⚠",
            cell(a.get("quoted_text") or a.get("candidate_quote") or "(无文字，仅几何)")))
    L += ["", "> 颜色语义仅在输入给出 legend/说明时填写（`color_meaning`），否则留空，不臆断；⚠ = 低置信锚点，需人工核对。",
          "", "## 3. 结构化笔记（论断 + 原文支撑）", ""]
    if notes:
        L += ["| note_id | doc | 类 | 论断 | 支撑批注与原文 |", "|---|---|---|---|---|"]
        for n in notes:
            sup = "; ".join("%s: %s" % (s.get("ann_id"), cell(s.get("quote") or "")[:70])
                            for s in (n.get("quote_support") or []))
            L.append("| %s | %s | %s | %s | %s |" % (n["note_id"], n.get("doc_id"), n.get("section"),
                                                     cell(n.get("claim")), cell(sup) or "(无)"))
    else:
        L.append("(无笔记：未写工作稿)")
    L += ["", "## 4. 知识关联（每条带依据）", ""]
    for l in links[:60]:
        L.append("- `%s` **%s** → `%s` ｜ %s ｜ conf=%.2f ｜ basis: %s" % (
            l["from"], l["relation"], l["to"], l["kind"], float(l.get("confidence") or 0), cell(l.get("basis"))))
    if len(links) > 60:
        L.append("- …（省略 %d 条结构回链，完整见 links.json）" % (len(links) - 60))
    L += ["", "## 5. 检索入口与命中", ""]
    for q in queries:
        L.append("### %s %s" % (q["qid"], q.get("question")))
        if q.get("hits"):
            for h in q["hits"][:6]:
                L.append("- → `%s` @ %s ｜ %s" % (h.get("note_id"), h.get("locator") or "-", h.get("why") or ""))
        else:
            L.append("- 无命中：%s" % (q.get("recall_note") or "未说明"))
        L.append("")
    L += ["## 6. 覆盖、降级与复跑", "",
          "- 覆盖：文件 %s/%s 有文本层；批注锚定 %s/%s；笔记支撑率 %s；检索命中 %s/%s" % (
              cov["docs_processed"], cov["docs_expected"], cov["annotations_anchored"], cov["annotations_extracted"],
              cov["note_support_rate"], cov["queries_answered"], cov["queries_total"]),
          "- 批注类型分布：%s" % (", ".join("%s=%d" % kv for kv in cov["annotations_by_type"].items()) or "无"),
          "- 降级：%s" % ("; ".join(degr) or "无"),
          "- 跳过年限：见 `skipped.json`（加密/损坏/无文本层/低置信/重复/版本差异逐条记录原因与处置）",
          "- 复跑：`init → show → 写 work/draft.json → check → build → selfcheck`；输入哈希与抽取器版本见 `provenance.json`", ""]
    return "\n".join(L)


def run(a):
    t0 = time.time()
    inp, outp, wk = paths(a)
    errs, degr, pend = [], [], []
    case, cid = {}, "unknown"
    try:
        case, cp = find_case(inp, errs)
        cid = str(case.get("case_id") or case.get("id") or (cp.parent.name if cp else "unknown"))
    except Exception as e:
        errs.append({"code": "case_probe_failed", "detail": repr(e)})
    X.jw(outp / "result.json", envelope(case, cid, errs))       # legal partial first, unconditionally
    idx = load_index(wk, errs)
    if not (idx.get("docs") or idx.get("annotations")):
        try:
            from main import build_index
            idx, case, cid = build_index(inp, errs, degr)
            X.jw(wk / "index.json", idx)
            degr.append("index 在 build 内重建（init 未完成或未运行）")
        except Exception as e:
            errs.append({"code": "index_failed", "detail": "%s: %s" % (type(e).__name__, e)})
    docs, anns = idx.get("docs") or {}, list(idx.get("annotations") or [])
    pmap = {k: {pg["page"]: (pg.get("text") or "") for pg in v} for k, v in (idx.get("pages") or {}).items()}
    from checks import d_anns, d_list, load_draft, match_ann
    dr, dsrc = load_draft(wk, a)
    if dr.get("_err"):
        errs.append({"code": "draft_unreadable", "detail": dr["_err"]})
        dr = {}
    if not dr:
        degr.append("draft.json 缺失：build 只用抽取结果生成账本，语义笔记/关联/检索未由 Agent 撰写")
        pend.append("写 %s 后重跑 check → build，获得完整笔记与语义关联" % (wk / "draft.json"))
    used = set()
    for j in d_anns(dr):
        a0 = match_ann(anns, j)
        if not a0:
            q = X.norm(j.get("quoted_text") or "")
            did = next((k for k, t in (idx.get("texts") or {}).items() if q and X.fq(t, q)["found"]), None)
            if not did:
                degr.append("draft 批注判断无法匹配索引批注且引文不在任何文本中，已跳过: %r" % (j.get("ann_id"),))
                continue
            a0 = {"ann_id": str(j.get("ann_id") or "U%03d" % (len(anns) + 1)), "doc_id": did,
                  "page": int(j.get("page") or 1), "type": X.type_alias(j.get("type_confirm") or "unknown"),
                  "quoted_text": q, "candidate_quote": q, "comment": X.norm(j.get("comment") or ""),
                  "color": j.get("color"), "anchor_method": "draft_text_match",
                  "anchor_confidence": float(j.get("anchor_confidence") or 0.6), "anchor_confirmed": True,
                  "source": "draft", "source_version": "", "locator": "p%s#draft" % int(j.get("page") or 1)}
            anns.append(a0)
        used.add(a0["ann_id"])
        if j.get("quoted_text"):
            a0["quoted_text"] = X.norm(j["quoted_text"])
            a0["anchor_confirmed"] = bool(X.fq((pmap.get(a0["doc_id"]) or {}).get(a0["page"], ""), a0["quoted_text"])["found"]
                                          or X.fq((idx.get("texts") or {}).get(a0["doc_id"], ""), a0["quoted_text"])["found"])
        if j.get("type_confirm") in X.TYPES:
            a0["type"] = j["type_confirm"]
        for k in ("color_meaning", "comment", "to_verify"):
            if j.get(k):
                a0[k] = X.norm(j[k])
        if j.get("anchor_confidence") is not None:
            try:
                a0["anchor_confidence"] = round(min(1.0, max(0.0, float(j["anchor_confidence"]))), 2)
            except Exception:
                pass
    for a0 in anns:
        a0["low_confidence"] = bool(float(a0.get("anchor_confidence") or 0) < LOW_CONF or not a0.get("anchor_confirmed"))
        a0.setdefault("color_meaning", None)
        a0["type"] = a0["type"] if a0["type"] in X.TYPES else "unknown"
    low = [x["ann_id"] for x in anns if x["low_confidence"]]
    if low:
        degr.append("%d 条批注锚点低置信度（无文本层/几何推断/引文未逐字命中）：%s" % (len(low), ", ".join(low[:10])))
    notes = []
    for i, n in enumerate(d_list(dr, "notes")):
        nid = str(n.get("note_id") or "N%03d" % (i + 1))
        sup = [{"ann_id": str(s.get("ann_id")), "quote": X.norm(s.get("quote") or s.get("quoted_text") or "")}
               for s in (n.get("quote_support") or []) if isinstance(s, dict)]
        aids = [str(x) for x in (n.get("ann_ids") or []) if str(x)] or [s["ann_id"] for s in sup]
        did = str(n.get("doc_id") or next((y["doc_id"] for x in aids for y in anns if y["ann_id"] == x), ""))
        notes.append({"note_id": nid, "doc_id": did, "ann_ids": aids,
                      "section": n.get("section") if n.get("section") in X.SECTIONS else "to_verify",
                      "claim": X.norm(n.get("claim")), "tags": [X.norm(t) for t in (n.get("tags") or []) if X.norm(t)],
                      "quote_support": [s for s in sup if s["quote"] or s["ann_id"]],
                      "to_verify": X.norm(n.get("to_verify") or ""), "created_from": "draft"})
    if not notes:
        notes = stub_notes(anns, degr)
    links, seen, sem = [], set(), 0
    for n in notes:
        for aid in n["ann_ids"][:6]:
            a0 = next((x for x in anns if x["ann_id"] == aid), None)
            if not a0 or (n["note_id"], aid) in seen:
                continue
            seen.add((n["note_id"], aid))
            links.append({"link_id": "L%03d" % (len(links) + 1), "from": n["note_id"], "to": aid,
                          "relation": "annotates",
                          "basis": "笔记 ann_ids 显式回链：%s 的论断由 %s@p%s 批注支撑"
                                   % (n["note_id"], aid, a0.get("page")),
                          "confidence": 1.0, "kind": "structural"})
    for l in d_list(dr, "links"):
        f, t = str(l.get("from") or ""), str(l.get("to") or "")
        rel = X.norm(l.get("relation") or "same_topic")
        if not f or not t or f == t or rel not in X.RELS:
            continue
        if any(x["from"] == f and x["to"] == t and x["relation"] == rel for x in links):
            continue
        links.append({"link_id": "L%03d" % (len(links) + 1), "from": f, "to": t, "relation": rel,
                      "basis": X.norm(l.get("basis") or l.get("reason")), "confidence": float(l.get("confidence") or 0.6),
                      "kind": "semantic"})
        sem += 1
    if not sem:
        degr.append("没有 Agent 撰写的语义关联（links 仅含 ann→note 结构回链）；语义关联需在 draft.links 给 basis")
    case_q, dq = idx.get("queries") or [], d_list(dr, "queries", "query_answers", "retrieval")
    queries = []
    if dq:
        for q in dq:
            qid = str(q.get("qid") or "Q%d" % (len(queries) + 1))
            base = next((x for x in case_q if x["qid"] == qid), {})
            hits = [{"note_id": str(h.get("note_id") or ""), "locator": h.get("locator") or "",
                     "why": X.norm(h.get("why") or h.get("reason"))} for h in (q.get("hits") or []) if isinstance(h, dict)]
            queries.append({"qid": qid, "question": X.norm(q.get("question") or base.get("question") or ""),
                            "answered": bool(hits), "hits": hits, "answered_by": "agent",
                            "recall_note": X.norm(q.get("recall_note") or q.get("note"))})
        miss = [x for x in case_q if x["qid"] not in {q["qid"] for q in queries}]
        if miss:
            queries += fallback_queries(miss, notes, degr)
    else:
        queries = fallback_queries(case_q, notes, degr)
    if case_q and not any(q.get("answered") for q in queries):
        pend.append("检索问题全部无命中：检查笔记标签/术语是否覆盖问题用词，或在 recall_note 说明超出范围")
    n_sup = len([n for n in notes if n.get("quote_support")])
    types = sorted({x["type"] for x in anns})
    coverage = {"docs_expected": len(docs), "docs_processed": len([d for d in docs.values() if d.get("has_text_layer")]),
                "docs_with_annotations": len({x["doc_id"] for x in anns}),
                "annotations_extracted": len(anns), "annotations_judged": len(used),
                "annotations_anchored": len([x for x in anns if x.get("anchor_confirmed")]),
                "annotations_low_confidence": len(low), "annotation_types": types,
                "annotations_by_type": {t: len([x for x in anns if x["type"] == t]) for t in types},
                "notes_created": len(notes), "notes_with_support": n_sup,
                "notes_by_section": {s: len([n for n in notes if n["section"] == s])
                                     for s in X.SECTIONS if any(n["section"] == s for n in notes)},
                "links_total": len(links), "links_semantic": sem,
                "queries_total": len(case_q), "queries_answered": len([q for q in queries if q.get("answered")]),
                "skipped": len(idx.get("skipped") or []),
                "quote_hit_rate": round(len([x for x in anns if x.get("anchor_confirmed")]) / max(len(anns), 1), 3),
                "note_support_rate": round(n_sup / max(len(notes), 1), 3)}
    files = [{"doc_id": k, "file": d.get("filename"), "path": d.get("path"), "kind": d.get("kind"),
              "sha256": d.get("sha256"), "bytes": d.get("size"), "pages": d.get("n_pages"),
              "has_text_layer": d.get("has_text_layer"), "text_quality": d.get("quality"),
              "version": d.get("version") or "", "alias_group": d.get("alias_group") or "",
              "duplicate_of": d.get("duplicate_of") or "", "version_chain": d.get("version_chain") or [],
              "source_url": (d.get("src") or {}).get("url") if isinstance(d.get("src"), dict) else None,
              "readable": bool(d.get("has_text_layer")) or d.get("kind") in ("pdf", "docx", "html", "text")}
             for k, d in docs.items()]
    status = "ok"
    if not docs and not anns:
        status = "input_error"
        pend.append("输入目录没有可处理的材料文件")
    elif not notes or not anns or len(low) > max(1, len(anns) // 2) or not dsrc \
            or any(e["code"] in ("case_json_invalid", "index_failed", "draft_unreadable") for e in errs):
        status = "partial"
    if not anns and docs:
        status = "insufficient_evidence"
    provenance = {"skill": GEN, "case_id": cid, "case_path": idx.get("case_path"), "generated": time.strftime("%FT%T"),
                  "python": __import__("sys").version.split()[0],
                  "argv": {"input": str(inp), "output": str(outp), "work": str(wk)},
                  "inputs": [{"doc_id": f["doc_id"], "file": f["file"], "sha256": f["sha256"], "bytes": f["bytes"],
                              "kind": f["kind"], "pages": f["pages"]} for f in files],
                  "draft": {"path": dsrc, "sha256": X.sha(dsrc) if dsrc else "", "present": bool(dsrc)},
                  "extractors": {"pdf": "builtin-pdf (zlib + page tree + /Annots + content-stream blocks)",
                                 "docx": "docx-xml (document.xml + comments.xml)", "html": "html-regex",
                                 "overlay": "annotations*.json"},
                  "counts": coverage, "artifacts": [],
                  "human_changes": [{"what": "Agent draft.json",
                                     "diff": "draft overrides annotation type/colour meaning/quotes and supplies note claims, link bases, query answers"}
                                    if dsrc else {"what": "none", "diff": "no draft: extraction-only output"}]}
    X.jw(outp / "files.json", {"case_id": cid, "documents": files, "duplicates": idx.get("duplicates") or [],
                               "aliases": idx.get("aliases") or [], "version_notes": idx.get("version_notes") or []})
    X.jl(outp / "annotations.jsonl", [{k: x.get(k) for k in (
        "ann_id", "doc_id", "type", "page", "locator", "rect", "color", "color_meaning", "quoted_text", "comment",
        "anchor_method", "anchor_confidence", "anchor_confirmed", "low_confidence", "source", "source_version",
        "author", "created")} for x in anns])
    X.jl(outp / "notes.jsonl", notes)
    X.jw(outp / "links.json", {"case_id": cid, "links": links,
                               "rules": "semantic edges need a basis; one shared term is not enough; annotates = structural back-link"})
    inv = build_inverted(notes, anns)
    X.jw(outp / "index.json", {"case_id": cid, "built_from": "notes.jsonl", **inv})
    X.jw(outp / "queries.json", {"case_id": cid, "queries": queries})
    skipped = [dict(s, action=s.get("action") or "记录并降级，不假装完成") for s in (idx.get("skipped") or [])]
    X.jw(outp / "skipped.json", {"case_id": cid, "skipped": skipped,
                                 "low_confidence_annotations": low})
    (outp / "ledger.md").write_text(render_ledger(cid, status, files, anns, notes, links, queries, coverage,
                                                 idx, degr, sem), encoding="utf-8")
    provenance["artifacts"] = [{"file": f, "bytes": (outp / f).stat().st_size if (outp / f).exists() else 0,
                                "sha256": X.sha(outp / f)[:32]} for f in ARTIFACTS if f != "result.json"]
    X.jw(outp / "provenance.json", provenance)
    ledger = (outp / "ledger.md").read_text(encoding="utf-8")
    model = {"annotations": anns, "notes": notes, "links": links, "queries": queries, "index": inv, "files": files,
             "provenance": provenance, "coverage": coverage, "summary": ledger,
             "method": "extraction is deterministic (page tree, /Annots, content-block rect overlay, sha256 dedup, "
                       "alias/version grouping); the Agent authors note claims, link bases and query answers in "
                       "work/draft.json; check validates every quote verbatim before build.",
             "skipped": skipped,
             "versions": {"duplicates": idx.get("duplicates") or [], "aliases": idx.get("aliases") or [],
                          "version_notes": idx.get("version_notes") or []},
             "uncertainty": dr.get("uncertainty") or (["锚点为几何推断，低置信度条目已逐条标注"] if low else []),
             "artifacts": ARTIFACTS, "annotations_by_type": coverage["annotations_by_type"],
             "_default_keys": ["annotations", "notes", "links", "queries", "index", "files", "coverage", "summary"]}
    res, unfilled, keys = fill_contract(case, model)
    res.update(case_id=cid, status=status,
               sources=[{"doc_id": f["doc_id"], "file": f["file"], "kind": f["kind"],
                         "sha256": (f["sha256"] or "")[:16], "pages": f["pages"],
                         "has_text_layer": f["has_text_layer"]} for f in files],
               errors=errs, degradations=degr, uncertainty=model["uncertainty"],
               pending_human=pend + (["output_contract 无内容匹配的键: %s" % ", ".join(unfilled)] if unfilled else []),
               changes=[{"step": "init", "source": idx.get("case_path"), "to": [str(wk / "index.json")]},
                        {"step": "build", "source": dsrc or "(no draft)", "to": ARTIFACTS},
                        {"step": "contract", "resolved": len(keys) - len(unfilled), "keys": keys}],
               runtime={"skill": GEN, "stage": "build", "seconds": round(time.time() - t0, 2), "docs": len(files),
                        "annotations": len(anns), "notes": len(notes), "links": len(links), "queries": len(queries),
                        "draft": bool(dsrc), "contract_keys": len(keys), "unfilled": len(unfilled)})
    X.jw(outp / "result.json", res)
    print("status=%s docs=%d annotations=%d anchored=%d low_conf=%d notes=%d support=%d links=%d(sem=%d) queries=%s/%s" % (
        status, len(files), len(anns), coverage["annotations_anchored"], len(low), len(notes), n_sup,
        len(links), sem, coverage["queries_answered"], len(case_q)))
    print("artifacts:", ", ".join(ARTIFACTS))
    print("unfilled contract:", unfilled or "none", "| draft:", dsrc or "(absent -> degraded)")
    if degr:
        print("degradations:", " | ".join(degr[:4]))
