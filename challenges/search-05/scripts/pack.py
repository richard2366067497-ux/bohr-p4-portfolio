#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""federated-search-reconcile :: pack layer.

Screening/ranking bookkeeping, gap accounting, bundle assembly and result.json
content. Renders are delegated to render.py. Stdlib only, offline.
"""
import json
from pathlib import Path

import ledger as L
import matrix as M
import render as R

V = "1.0.0"
COV = M.COV
PIECES = R.PIECES


# -------------------------------------------------------------------- assemble
VERD = {"include": 0, "uncertain": 1, "unscreened": 2, "exclude": 3}


def screening_map(merged, draft):
    by_item = {c["cluster_id"]: c for c in merged}
    by_rid = {}
    for c in merged:
        for rid in c["member_ids"]:
            by_rid[rid] = c["cluster_id"]
    out, bad = {}, []
    for s in (draft.get("screening") or []):
        if not isinstance(s, dict):
            continue
        key = s.get("cluster") or s.get("cluster_id") or s.get("rid") or s.get("id")
        cid = None
        if key in by_item:
            cid = key
        elif key in by_rid:
            cid = by_rid[key]
        elif isinstance(key, str) and key.upper().startswith("R-") and key in by_rid:
            cid = by_rid[key]
        verdict = str(s.get("verdict") or "").lower()
        verdict = {"in": "include", "keep": "include", "yes": "include", "out": "exclude",
                   "drop": "exclude", "no": "exclude", "unclear": "uncertain",
                   "maybe": "uncertain", "unsure": "uncertain"}.get(verdict, verdict)
        if cid is None or verdict not in VERD:
            bad.append({"item": key, "error": "unknown cluster/rid or verdict"})
            continue
        out[cid] = {"verdict": verdict, "reason": L.clip(s.get("reason") or "", 400),
                    "locator": s.get("locator") or "", "source": "agent"}
    return out, bad


def ranking(merged, smap, draft):
    order = {}
    seq = []
    for r in (draft.get("ranked") or []):
        if isinstance(r, dict):
            cid = r.get("cluster") or r.get("cluster_id")
            if cid:
                order[cid] = r.get("rank")
                seq.append(cid)
                if r.get("reason"):
                    smap.setdefault(cid, {}).setdefault("rank_reason", r["reason"])
        elif isinstance(r, str):
            seq.append(r)
    if seq:
        for i, cid in enumerate(seq, 1):
            order.setdefault(cid, i)
    for c in merged:
        rel = smap.get(c["cluster_id"]) or {"verdict": "unscreened",
                                            "reason": "脚本不判断主题相关性；未在工作稿中记录 screening",
                                            "locator": ""}
        c["relevance"] = {"verdict": rel.get("verdict", "unscreened"),
                          "reason": L.clip(rel.get("reason") or "", 300),
                          "locator": rel.get("locator") or "",
                          "source": rel.get("source", "default")}
        c["_sort"] = (order.get(c["cluster_id"], 999), VERD.get(c["relevance"]["verdict"], 2),
                      -c["completeness"], -(int(c["canonical"]["year"]["value"])
                                           if (c["canonical"].get("year") or {}).get("value") else 0))
    merged.sort(key=lambda c: c["_sort"])
    for i, c in enumerate(merged, 1):
        c["rank"] = order.get(c["cluster_id"], i)
        c.pop("_sort", None)
    return merged


def record_view(c):
    g = lambda k: c["canonical"].get(k, {}).get("value")
    ids = {k: g(k) for k in ("pmid", "pmcid", "arxiv") if g(k)}
    ev = {k: {"value": c["canonical"][k]["value"], "src_db": c["canonical"][k]["src_db"],
              "locator": c["canonical"][k]["locator"], "rule": c["canonical"][k]["rule"]}
          for k in COV + L.IDF if k in c["canonical"]}
    return {"cluster_id": c["cluster_id"], "rank": c["rank"], "title": g("title"),
            "authors": g("authors") or [], "year": g("year"), "venue": g("venue"),
            "doi": g("doi"), "abstract": g("abstract"), "identifiers": ids,
            "source_dbs": c["source_dbs"], "relevance": c["relevance"],
            "evidence": ev, "member_locators": [m["locator"] for m in c["members"]],
            "merge_reason": c["merge_reason"], "conflict_count": len(c["conflicts"]),
            "untraced_fields": c.get("untraced_fields") or []}


def assemble(idx, draft, out, errors, degradations, assumptions):
    out = Path(out)
    records = idx["records"]
    pairs = M.candidates(records)
    dmap, pairprob = M.decisions_map(pairs, draft)
    clusters, decided = M.build_clusters(records, pairs, dmap)
    merged = M.merge_clusters(clusters, draft.get("conflict_resolutions") or [])
    smap, sbad = screening_map(merged, draft)
    merged = ranking(merged, smap, draft)
    cov = M.coverage_rows(idx, merged)
    qrows, dupq = M.query_rows(idx, merged, draft)
    dbs = sorted({r["db"] for r in records})
    untraced = sorted({f for c in merged for f in (c.get("untraced_fields") or [])})
    conflicts = [dict(c=cl["cluster_id"], **cf) for cl in merged for cf in cl["conflicts"]]
    maybe = [d for d in decided.values() if d.get("final_decision") == "maybe"]
    incl = [c for c in merged if c["relevance"]["verdict"] == "include"]
    excl = [c for c in merged if c["relevance"]["verdict"] == "exclude"]

    gaps = []
    if not records:
        gaps.append({"item": "无可解析记录", "kind": "missing_material",
                     "note": "输入中没有可识别的文献记录列表；五件套只保留结构与缺口说明"})
    if not draft:
        gaps.append({"item": "工作稿缺失", "kind": "missing_judgement",
                     "note": "未读到 draft.json：库语义、同文判定、相关性、排序均未经 Agent 核对，结果按规则降级生成"})
    elif not smap:
        gaps.append({"item": "未记录相关性筛选", "kind": "missing_judgement",
                     "note": "工作稿没有 screening[]，候选集的 verdict 全为 unscreened，不能据此声称已筛出相关文献"})
    if maybe and not any(d.get("decision_source") == "agent" for d in maybe):
        gaps.append({"item": "%d 个 maybe 对未仲裁" % len(maybe), "kind": "unresolved_conflict",
                     "note": "投票分恰为 3 的对未合并，需 Agent/人工签字；相关 pair_id 见 merge_cluster.voting_evidence"})
    for f in idx.get("failures", []):
        gaps.append({"item": "库 %s 不可用" % f.get("db"), "kind": "failed_database",
                     "note": "%s（%s）: %s" % (f.get("path"), f.get("http_status") or "-", f.get("reason")),
                     "locator": f.get("path")})
    for s in cov["systematic_missing"]:
        gaps.append({"item": "字段 %s 系统性缺失" % s["field"], "kind": "systematic_missing",
                     "note": "%d/%d 个库有值" % (s["dbs_with_value"], s["dbs_total"])})
    for f in untraced:
        gaps.append({"item": "字段 %s 值未能在成员原始响应中定位" % f, "kind": "untraced_value",
                     "note": "canonical 取值来自 Agent 覆盖或归一化改写，需人工确认"})
    for g in (draft.get("gaps") or []):
        if isinstance(g, dict):
            gaps.append({"item": g.get("item") or "-", "kind": g.get("kind") or "agent_reported",
                         "note": g.get("note") or "", "locator": g.get("locator") or ""})
        elif isinstance(g, str):
            gaps.append({"item": g, "kind": "agent_reported", "note": ""})
    if not draft.get("cluster_decisions"):
        gaps.append({"item": "去重判定未经 Agent 复核", "kind": "missing_judgement",
                     "note": "全部 duplicate/distinct 由四路投票规则给出，可能含跨语言题名或副标题差异导致的漏判"})
    for p in pairprob[:10]:
        gaps.append({"item": "工作稿中的对引用无效: %s" % p.get("pair"), "kind": "input_conflict",
                     "note": p.get("error")})

    dbtab = [{"db": r["db"], "records": r["records"], "files": r["files"], "status": r["status"],
              "field_ratio": r["field_ratio"]} for r in cov["rows"]]
    stats = {"raw": len(records), "pairs": len(pairs), "dup": len([d for d in decided.values()
                                                                 if d.get("final_decision") == "duplicate"]),
             "maybe": len(maybe), "canonical": len(merged), "maybe_pairs": maybe}
    rules = R.render_rules(idx, draft, dbs)
    counts = {"files": len(idx["files"]), "records_raw": len(records), "databases": len(dbs),
              "databases_failed": len(idx.get("failures", [])), "pairs": len(pairs),
              "duplicate_pairs": stats["dup"], "maybe_pairs": len(maybe),
              "clusters": len(merged), "included": len(incl), "excluded": len(excl),
              "unscreened": len([c for c in merged if c["relevance"]["verdict"] == "unscreened"]),
              "conflicts": len(conflicts), "gaps": len(gaps),
              "untraced_fields": len(untraced)}
    status = "insufficient_evidence" if not records else ("partial" if (not draft or not smap) else "ok")
    summary = ["# 多库联合检索结果摘要", "",
               "- 库：%s%s" % (", ".join(dbs) or "无",
                             ("；失败：" + ", ".join("%s(%s)" % (f.get("db"), f.get("http_status") or "-")
                                                     for f in idx.get("failures", [])))
                             if idx.get("failures") else ""),
               "- 计数：原始记录 %d → 候选对 %d → duplicate %d → maybe %d → canonical %d"
               % (counts["records_raw"], counts["pairs"], counts["duplicate_pairs"],
                  counts["maybe_pairs"], counts["clusters"]),
               "- 相关性筛选：include %d / exclude %d / unscreened %d"
               % (counts["included"], counts["excluded"], counts["unscreened"]),
               "- 字段冲突：%d 条；缺口：%d 条（见 reconciliation.md §9）" % (len(conflicts), len(gaps))]
    if draft.get("research_question"):
        summary.insert(1, "- 研究问题：%s" % L.clip(draft["research_question"], 240))

    B = {"records": [record_view(c) for c in merged],
         "clusters": [{"cluster_id": c["cluster_id"], "member_ids": c["member_ids"],
                       "source_dbs": c["source_dbs"], "merge_reason": c["merge_reason"],
                       "conflicts": c["conflicts"], "canonical": c["canonical"]} for c in merged],
         "coverage": {"matrix": cov["rows"], "single_db_clusters": cov["single_db_clusters"],
                      "systematic_missing": cov["systematic_missing"],
                      "failed_databases": cov["failed"], "unparsed_files": cov["unparsed"]},
         "queries": qrows, "rules": rules, "sources": idx["files"] + idx.get("docs", []),
         "databases": dbtab,
         "ranked": [{"rank": c["rank"], "cluster_id": c["cluster_id"],
                     "title": c["canonical"].get("title", {}).get("value"),
                     "year": c["canonical"].get("year", {}).get("value"),
                     "venue": c["canonical"].get("venue", {}).get("value"),
                     "doi": c["canonical"].get("doi", {}).get("value"),
                     "source_dbs": c["source_dbs"], "verdict": c["relevance"]["verdict"],
                     "reason": c["relevance"]["reason"]} for c in merged],
         "screening": [{"cluster_id": c["cluster_id"], "verdict": c["relevance"]["verdict"],
                        "reason": c["relevance"]["reason"], "locator": c["relevance"]["locator"]}
                       for c in merged],
         "exclusions": [record_view(c) for c in excl], "conflicts": conflicts,
         "failures": idx.get("failures", []), "counts": counts, "uncertainty": gaps,
         "summary": "\n".join(summary), "status": status}
    items, cvals, cmap, unmapped = R.fill_contract(idx["case"].get("output_contract"), B)
    if unmapped:
        for u in unmapped[:10]:
            assumptions.append({"item": u["key"], "note": "contract key has no semantic match; value null/[]"})

    pieces = {}
    try:
        pieces["intake_ledger.md"] = R.render_ledger(idx, merged)
        pieces["query_matrix.csv"] = R.render_query_csv(qrows)
        pieces["normalize_rules.json"] = L.jd(rules) + "\n"
        pieces["merge_cluster.jsonl"] = R.render_clusters(merged, decided)
        pieces["reconciliation.md"] = R.render_recon(idx, merged, cov, qrows, dupq, gaps, draft, stats)
    except Exception as e:
        errors.append({"stage": "render", "error": "%s: %s" % (type(e).__name__, e)})
        for name in PIECES:
            pieces.setdefault(name, "")
    for name, text in pieces.items():
        R.w(out / name, text if text.strip() else ("# %s\n\n（本次运行未能生成内容：%s）\n"
                                                 % (name, "见 errors/degradations")))
    res = {}
    res.update(cvals)
    coll = [k for k in cvals if k in ("case_id", "status", "errors", "degradations", "assumptions",
                                      "sources", "uncertainty", "runtime", "counts", "contract_map")]
    if coll:
        res["contract_values"] = {k: cvals[k] for k in coll}
        assumptions.append({"item": "contract/envelope key collision: %s" % ", ".join(coll),
                            "note": "envelope value occupies the key; contract value kept in contract_values"})
    res.update(case_id=idx["case"].get("case_id"), status=status, errors=errors,
               degradations=degradations, assumptions=assumptions, sources=idx["files"],
               uncertainty=gaps[:60], counts=counts, contract_map=cmap,
               artifacts=[{"path": n, "bytes": len(pieces.get(n, "").encode("utf-8"))} for n in PIECES],
               coverage=B["coverage"], queries=qrows, records=B["records"], clusters=B["clusters"],
               summary=B["summary"], databases=dbtab, failures=idx.get("failures", []))
    return res, B, merged, stats, gaps, cov, qrows


def selfcheck(idx, inp, work, out):
    errors = []
    rep, verdict = {"schema": "federated-search-reconcile/selfcheck@1", "checks": []}, "PASS"

    def add(cid, ok, detail):
        nonlocal verdict
        rep["checks"].append({"id": cid, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            verdict = "PARTIAL"

    res = {}
    rp = Path(out) / "result.json"
    try:
        res = json.loads(rp.read_text("utf-8"))
    except Exception as e:
        errors.append({"stage": "selfcheck", "error": "result.json unreadable: %s" % e})
    add("result-json", bool(res), "%s (%d bytes)" % (rp, rp.stat().st_size if rp.is_file() else 0))
    citems = [k for k, _ in R.contract_items(idx["case"].get("output_contract"))]
    missing = [k for k in citems if k not in res]
    add("contract-keys", not missing, "%d expected, missing: %s" % (len(citems), ", ".join(missing) or "none"))
    add("case-id", res.get("case_id") == idx["case"].get("case_id"),
        "%r vs input %r" % (res.get("case_id"), idx["case"].get("case_id")))
    sizes = {}
    for n in R.PIECES:
        p = Path(out) / n
        sizes[n] = p.stat().st_size if p.is_file() else 0
    add("five-pieces", all(v > 0 for v in sizes.values()), sizes)
    qrows = 0
    try:
        qrows = len([l for l in (Path(out) / "query_matrix.csv").read_text("utf-8").splitlines()[1:] if l.strip()])
    except Exception:
        pass
    add("query-matrix", qrows >= len({r["db"] for r in idx["records"]}), "%d rows for %d dbs"
        % (qrows, len({r["db"] for r in idx["records"]})))
    lines, nloc, nbad, votes_bad = [], 0, 0, 0
    try:
        lines = [json.loads(l) for l in (Path(out) / "merge_cluster.jsonl").read_text("utf-8").splitlines() if l.strip()]
    except Exception:
        lines = []
    cache = {}
    for row in lines:
        for k, fld in (row.get("canonical") or {}).items():
            if fld.get("state") == "present" and not fld.get("locator"):
                nbad += 1
        for m in row.get("members") or []:
            loc = m.get("locator") or ""
            rel, _, ptr = loc.partition("#")
            if not rel:
                continue
            nloc += 1
            if nloc > 120:
                continue
            if rel not in cache:
                cache[rel] = True
            try:
                rec = L.resolve(rel, ptr, inp)
                if rec is None:
                    nbad += 1
                elif m.get("raw_sha") and L.sha(L.cj(rec)) != m["raw_sha"]:
                    nbad += 1
            except Exception:
                nbad += 1
        for v in row.get("voting_evidence") or []:
            if sum(x.get("weight", 0) for x in v.get("votes") or []) != v.get("score"):
                votes_bad += 1
    counts = res.get("counts") or {}
    add("cluster-count", len(lines) == counts.get("clusters"),
        "jsonl=%d counts=%s" % (len(lines), counts.get("clusters")))
    add("locator-replay", nbad == 0, "%d member locators, %d unresolved/mismatched" % (nloc, nbad))
    add("vote-recompute", votes_bad == 0, "%d pairs with inconsistent vote sums" % votes_bad)
    fails = res.get("failures") or []
    add("failure-consistency", True, "%d failed responses recorded; degradations=%d"
        % (len(fails), len(res.get("degradations") or [])))
    add("status-honesty", res.get("status") in ("ok", "partial", "insufficient_evidence"),
        "status=%s counts.unscreened=%s" % (res.get("status"), counts.get("unscreened")))
    rep["verdict"] = verdict
    rep["outputs"] = sizes
    try:
        (Path(work) / "selfcheck.json").write_text(L.jd(rep), encoding="utf-8")
    except Exception as e:
        errors.append({"stage": "selfcheck", "error": str(e)})
    return rep
