#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py :: coverage policy, two-axis gap attribution, supplement yield, audit trail, products."""
import hashlib
import json
import re
from pathlib import Path

import ledger as L

V = "1.0.0"
POLICIES = ("all", "dedup_only", "dedup_exclude_unavailable")
CATS = ("query_term_missing", "field_too_narrow", "time_window_cut", "source_not_indexed",
        "ref_record_anomaly", "ranking_depth")
CAT2WHY = {"query_term_missing": "fixable_by_query", "field_too_narrow": "fixable_by_query",
           "time_window_cut": "fixable_by_query", "ranking_depth": "fixable_by_query",
           "source_not_indexed": "needs_new_source", "ref_record_anomaly": "data_defect"}
WHYS = ("fixable_by_query", "needs_new_source", "data_defect", "definition_mismatch")
FIXTXT = {"fixable_by_query": "可修复：改查询式/字段/时间窗即可覆盖",
          "needs_new_source": "需换源：本地来源集合不含该记录所属库",
          "data_defect": "数据缺陷：记录自身异常，补检无法修复",
          "definition_mismatch": "口径差异：分母/纳入规则分歧导致"}
TITLEONLY = re.compile(r"^(title|ti|t|ti:title|题名|标题)$")
FIELDTAG = re.compile(r"\b(ti|ab|ts|au|kw|mh|su|py|do|ta|is)\s*=", re.I)


# ------------------------------------------------------------------ row build
def build_rows(refs, auto, draft):
    """merge automatic match hints with the agent's hit decisions -> ledger rows."""
    dec = {}
    for d in (draft.get("hit_decisions") or []):
        if isinstance(d, dict) and d.get("ref_id"):
            dec[str(d["ref_id"])] = d
    rdec = {}
    for d in (draft.get("ref_decisions") or []):
        if isinstance(d, dict) and d.get("ref_id"):
            rdec[str(d["ref_id"])] = d
    rows = []
    for r in refs:
        a = auto.get(r["ref_id"]) or {}
        d = dec.get(r["ref_id"]) or {}
        rd = rdec.get(r["ref_id"]) or {}
        st = str(d.get("status") or "").lower()
        if st not in ("hit", "miss", "pending"):
            if a.get("pool_id") and a.get("certainty") in ("high", "medium") and a.get("rule") != "bib_borderline":
                st = "hit"
            elif a.get("rule") == "bib_borderline":
                st = "pending"
            else:
                st = "miss"
        src = "agent" if str(d.get("status") or "").lower() in ("hit", "miss", "pending") else "auto"
        usable = r["usable"] if rd.get("usable") is None else bool(rd.get("usable"))
        reason = rd.get("reason") or r["usability_reason"]
        if st == "hit":
            loc = d.get("locator") or a.get("locator")
            qte = d.get("evidence") if (d.get("evidence") and d.get("locator")) else a.get("quote")
            mid = d.get("matched_id") or a.get("pool_id")
        else:
            loc = d.get("locator") or r.get("locator")
            qte = d.get("evidence") if (d.get("evidence") and d.get("locator")) else r.get("quote")
            mid = d.get("matched_id")
        cert = d.get("certainty") or a.get("certainty") or "medium"
        rows.append({
            "ref_id": r["ref_id"], "title": L.clip(r.get("title"), 150), "doi": r.get("doi") or "",
            "year": r.get("year"), "first_author": r.get("first_author") or "",
            "usable": bool(usable), "usability_reason": reason,
            "hit_status": st, "matched_id": mid or "",
            "match_rule": d.get("rule") or (a.get("rule") if st == "hit" else "") or "",
            "certainty": cert, "evidence_locator": loc or "",
            "evidence_quote": L.clip(qte, 180),
            "decision_source": src,
            "needs_human": bool(st == "pending" or cert == "low"),
            "note": d.get("note") or "", "similarity": a.get("similarity"),
        })
    return rows


# ------------------------------------------------------------------- coverage
def fmt_wins(wins):
    out = []
    for a, b in wins:
        out.append("%s-%s" % (a if a else "…", b if b else "…"))
    return ", ".join(out) or "未声明"


def window_ok(year, wins):
    if not year or not wins:
        return True
    for a, b in wins:
        if (a or 0) <= year <= (b or 9999):
            return True
    return False


def coverage(refs, rows, policy):
    rb = {r["ref_id"]: r for r in rows}
    dup_total = sum(len(r.get("dups") or []) for r in refs)
    hit_ids = [i for i, r in rb.items() if r["hit_status"] == "hit"]
    pend_ids = [i for i, r in rb.items() if r["hit_status"] == "pending"]
    hit_dups = sum(len(r.get("dups") or []) for r in refs if rb.get(r["ref_id"], {}).get("hit_status") == "hit")
    if policy == "all":
        den_ids = [r["ref_id"] for r in refs]
        n_den, n_hit = len(refs) + dup_total, len(hit_ids) + hit_dups
    elif policy == "dedup_only":
        den_ids = [r["ref_id"] for r in refs]
        n_den, n_hit = len(refs), len(hit_ids)
    else:
        den_ids = [r["ref_id"] for r in refs if r["usable"]]
        n_den, n_hit = len(den_ids), len([i for i in hit_ids if rb[i]["usable"]])
    miss_ids = [i for i in den_ids if rb[i]["hit_status"] == "miss"]
    pend = [i for i in pend_ids if i in den_ids]
    cov = (n_hit / n_den) if n_den else None
    return {"policy": policy, "denominator": n_den, "numerator": n_hit,
            "coverage": round(cov, 6) if cov is not None else None,
            "miss_rate": round(1 - cov, 6) if cov is not None else None,
            "miss_count": len(miss_ids), "pending_count": len(pend),
            "denominator_ids": den_ids, "numerator_ids": [i for i in den_ids if rb[i]["hit_status"] == "hit"],
            "missed_ids": miss_ids, "pending_ids": pend,
            "duplicates_merged": dup_total,
            "excluded": [{"ref_id": r["ref_id"], "reason": r["usability_reason"]} for r in refs if not r["usable"]],
            "pending_human": pend}


def coverage_variants(refs, rows):
    return {p: coverage(refs, rows, p) for p in POLICIES}


def coverage_by_source(rows, pool):
    pc = {p["pool_id"]: p for p in pool}
    out = {}
    for r in rows:
        if r["hit_status"] != "hit" or not r["matched_id"]:
            continue
        c = (pc.get(r["matched_id"]) or {}).get("container") or "unknown"
        out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- attribution
def qctx(queries):
    blob = " ".join(((q.get("query") or "") + " " + (q.get("fields") or "") + " " + (q.get("source") or ""))
                    for q in queries).lower()
    qtoks = set(re.findall(r"[a-z0-9\u4e00-\u9fff\-]{3,}", blob))
    wins = [(q.get("year_from"), q.get("year_to")) for q in queries
            if q.get("year_from") or q.get("year_to")]
    fields = sorted({(q.get("fields") or "").lower() for q in queries if q.get("fields")})
    sources = sorted({(q.get("source") or "").lower() for q in queries if q.get("source")})
    return {"qtext": blob, "qtoks": qtoks, "wins": wins, "fields": fields,
            "sources": sources, "qids": [q["q_id"] for q in queries], "queries": queries}


def missing_terms(title, cx):
    out = []
    for t in sorted(L.toks(title)):
        if len(t) < 4 or t in cx["qtoks"]:
            continue
        if any((t in x or x.startswith(t[:5]) or t.startswith(x[:5])) for x in cx["qtoks"] if len(x) >= 4):
            continue
        out.append(t)
    return out


def narrow_fields(fields):
    parts = [p.strip() for f in fields for p in re.split(r"[,/;+|&]", f) if p.strip()]
    return bool(parts) and all(TITLEONLY.match(p) for p in parts)


def auto_gap(ref, row, cx):
    """one deterministic, evidence-carrying attribution hypothesis for a missed reference."""
    rid = ref["ref_id"]
    qs = cx["queries"]
    rev = {"doc_id": ref.get("doc_id"), "locator": ref.get("locator"), "quote": ref.get("quote")}
    cof = []
    if ref.get("flags") and "meta_incomplete" in ref["flags"]:
        cof.append("ref_record_anomaly")
    if ref.get("dups"):
        cof.append("definition_mismatch")
    yr = ref.get("year")
    if yr and cx["wins"] and not window_ok(yr, cx["wins"]):
        ev = [{"doc_id": q["doc_id"], "locator": q["locator"], "quote": q["quote"]}
              for q in qs if q.get("year_from") or q.get("year_to")][:3]
        return dict(category="time_window_cut", why="fixable_by_query", ref_ids=[rid],
                    affected_query_ids=[q["q_id"] for q in qs if q.get("year_from") or q.get("year_to")][:5],
                    evidence=ev + [rev], certainty="high", co_factors=cof, auto=True,
                    verdict="该条年份 %s 落在查询声明的时间窗（%s）之外，按当前时间窗不可能被返回"
                            % (yr, fmt_wins(cx["wins"])))
    mt = missing_terms(ref.get("title") or "", cx)
    if mt:
        return dict(category="query_term_missing", why="fixable_by_query", ref_ids=[rid],
                    affected_query_ids=cx["qids"][:5],
                    evidence=[{"doc_id": q["doc_id"], "locator": q["locator"], "quote": q["quote"]} for q in qs[:3]] + [rev],
                    certainty="high" if len(mt) >= 2 else "medium", co_factors=cof, auto=True,
                    verdict="题名中的判别词 %s 未出现在任何查询式中（词项缺口）" % ("、".join(mt[:5])))
    if cx["sources"] and ref.get("venue"):
        vn = L.ntitle(ref.get("venue"))
        if vn and not any(s.split()[0] in vn or vn in s for s in cx["sources"]):
            return dict(category="source_not_indexed", why="needs_new_source", ref_ids=[rid],
                        affected_query_ids=cx["qids"][:3],
                        evidence=[{"doc_id": q["doc_id"], "locator": q["locator"], "quote": q["quote"]}
                                  for q in qs if q.get("source")][:2] + [rev],
                        certainty="low", co_factors=cof, auto=True,
                        verdict="声明来源为 %s，未见该刊/库；需换源验证" % (", ".join(cx["sources"])[:80]))
    if narrow_fields(cx["fields"]):
        return dict(category="field_too_narrow", why="fixable_by_query", ref_ids=[rid],
                    affected_query_ids=cx["qids"][:5],
                    evidence=[{"doc_id": q["doc_id"], "locator": q["locator"], "quote": q["quote"]}
                              for q in qs if q.get("fields")][:2] + [rev],
                    certainty="medium", co_factors=cof, auto=True,
                    verdict="查询字段被限制为 %s；词项已覆盖但字段过窄，扩展字段可覆盖" % (", ".join(cx["fields"])[:60]))
    if cof:
        return dict(category="ref_record_anomaly", why="data_defect", ref_ids=[rid], affected_query_ids=[],
                    evidence=[rev], certainty="low", co_factors=[], auto=True,
                    verdict="参考集条目元数据异常（%s），无法确定是检索缺口还是记录缺陷"
                            % (", ".join(ref.get("flags") or ["缺失字段"])))
    return dict(category="ranking_depth", why="fixable_by_query", ref_ids=[rid], affected_query_ids=cx["qids"][:5],
                evidence=[rev], certainty="low", co_factors=[], auto=True,
                verdict="词项与字段均已覆盖但记录未出现在返回集合内：疑似返回条数上限或排序截断，需提高 limit 或降级排序验证")


def build_gaps(refs, rows, cx, draft, degr, cov=None):
    """attribute every reference that the chosen denominator counts as missed."""
    byid = {r["ref_id"]: r for r in refs}
    rb = {r["ref_id"]: r for r in rows}
    miss = list((cov or {}).get("missed_ids") or [i for i, r in rb.items() if r["hit_status"] == "miss"])
    gaps, covered = [], set()
    for g in (draft.get("gap_notes") or []):
        if not isinstance(g, dict):
            continue
        cat = str(g.get("category") or "")
        if cat not in CATS:
            degr.append({"stage": "gap", "note": "category %r 不在受控词表，已按 ranking_depth 记录并标记" % cat})
            cat = cat if cat else "ranking_depth"
        why = str(g.get("why") or CAT2WHY.get(cat, "fixable_by_query"))
        if why not in WHYS:
            why = CAT2WHY.get(cat, "fixable_by_query")
        ids = [str(x) for x in (g.get("ref_ids") or []) if str(x) in byid]
        if not ids:
            degr.append({"stage": "gap", "note": "一条 gap_notes 未给出有效 ref_ids，已忽略"})
            continue
        ev = []
        for e in (g.get("evidence") or []):
            if isinstance(e, dict) and e.get("quote"):
                ev.append({"doc_id": e.get("doc_id") or (e.get("locator") or "").split(":")[0],
                           "locator": e.get("locator") or "", "quote": L.clip(e.get("quote"), 200)})
            elif isinstance(e, str) and e.strip():
                ev.append({"doc_id": None, "locator": "", "quote": L.clip(e, 200)})
        if not ev:
            for rid in ids[:1]:
                ev.append({"doc_id": byid[rid].get("doc_id"), "locator": byid[rid].get("locator"),
                           "quote": byid[rid].get("quote")})
        gaps.append(dict(category=cat, why=why, ref_ids=ids,
                         affected_query_ids=[str(x) for x in (g.get("affected_query_ids") or [])],
                         evidence=ev, verdict=str(g.get("verdict") or ""),
                         certainty=str(g.get("certainty") or "medium"), auto=False, co_factors=[]))
        covered |= set(ids)
    for rid in miss:
        if rid in covered:
            continue
        gaps.append(auto_gap(byid[rid], rb[rid], cx))
        covered.add(rid)
    # a gap entry must never claim a reference that is not actually missed
    miss_set = set(miss)
    for g in gaps:
        g["ref_ids"] = [x for x in g["ref_ids"] if x in miss_set or x in miss]
    gaps = [g for g in gaps if g["ref_ids"]]
    return gaps, miss


def cluster(gaps):
    cl = {}
    for g in gaps:
        c = cl.setdefault(g["category"], dict(category=g["category"], why=g["why"], ref_ids=[], affected=[],
                                              evidence=[], verdicts=[], certainty=[], auto=0, agent=0))
        c["ref_ids"] += [x for x in g["ref_ids"] if x not in c["ref_ids"]]
        c["affected"] += [x for x in g["affected_query_ids"] if x not in c["affected"]]
        for e in g["evidence"]:
            if len(c["evidence"]) < 8 and all(e["quote"] != x["quote"] for x in c["evidence"]):
                c["evidence"].append(e)
        if g["verdict"]:
            c["verdicts"].append(g["verdict"])
        c["certainty"].append(g["certainty"])
        c["auto" if g.get("auto") else "agent"] += 1
    out = []
    for cat in list(CATS) + [k for k in cl if k not in CATS]:
        if cat not in cl:
            continue
        c = cl[cat]
        c["count"] = len(c["ref_ids"])
        c["fixability"] = FIXTXT.get(c["why"], c["why"])
        c["affected_query_ids"] = c["affected"]
        c["verdict"] = "；".join(c["verdicts"][:3]) or "（未给出判定说明）"
        c["certainty_mix"] = {k: c["certainty"].count(k) for k in sorted(set(c["certainty"]))}
        c.pop("verdicts", None)
        c.pop("certainty", None)
        c.pop("auto_refs", None)
        out.append(c)
    return out


# ----------------------------------------------------------------- supplement
def terms_of(q):
    s = str(q or "")
    s = FIELDTAG.sub(" ", s)
    s = re.sub(r"\b(AND|OR|NOT|NEAR|ADJ|SAME)\b", " ", s, flags=re.I)
    s = re.sub(r"[()\[\]{}:^~*\"'?]", " ", s)
    return [t.lower() for t in re.findall(r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff\-]{2,}", s)]


def cov_terms(terms, title):
    if not terms:
        return 0.0
    tt = L.toks(title)
    if not tt:
        return 0.0
    hit = 0
    for t in terms:
        if t in tt or any((t in w or w.startswith(t[:5]) or t.startswith(w[:5])) for w in tt if len(w) >= 4):
            hit += 1
    return hit / len(terms)


def eval_supplement(plan, refs, rows, pool, cov0, cx):
    byid = {r["ref_id"]: r for r in refs}
    rb = {r["ref_id"]: r for r in rows}
    base_hit = set(cov0["numerator_ids"])
    denom_ids = [i for i in cov0["denominator_ids"]]
    remaining = [i for i in denom_ids if rb[i]["hit_status"] != "hit"]
    used = {r["matched_id"] for r in rows if r["matched_id"]}
    qterms = set()
    for q in cx["queries"]:
        qterms |= set(terms_of(q.get("query")))
    out, cum, cum_new_rec = [], set(), 0
    for p in plan:
        if not isinstance(p, dict):
            continue
        pq = str(p.get("planned_query") or "")
        terms = terms_of(pq)
        if not terms:
            out.append({"target_gap": p.get("target_gap"), "planned_query": pq, "status": "invalid",
                        "note": "查询式无可解析词项，未计入收益", "actual_new_hits": 0, "new_records": 0,
                        "marginal_yield": 0.0, "no_gain": True, "redundant": False,
                        "cumulative_coverage_after": round((len(base_hit) + len(cum)) / len(denom_ids), 6) if denom_ids else None})
            continue
        redundant = set(terms) <= qterms
        new = [rid for rid in remaining if rid not in cum and cov_terms(terms, byid[rid].get("title") or "") >= 0.5]
        cum |= set(new)
        pool_hits = [x["pool_id"] for x in pool if cov_terms(terms, x.get("title") or "") >= 0.5]
        new_records = [x for x in pool_hits if x not in used]
        cum_new_rec += len(new_records)
        out.append({"target_gap": p.get("target_gap"),
                    "planned_query": pq,
                    "fields": p.get("fields") or "", "window": p.get("window") or "",
                    "rationale": p.get("rationale") or "",
                    "terms": terms[:12],
                    "redundant": bool(redundant),
                    "redundant_note": "词项均为既有查询式子集：本查询只做同义/重排或窗口调整，无新增词项，需靠窗口/字段变化解释收益" if redundant else "",
                    "expected_new": p.get("expected_new"),
                    "actual_new_hits": len(new), "new_ref_ids": new[:20],
                    "new_records": len(new_records),
                    "no_gain": bool(not new and not new_records),
                    "marginal_yield": round(len(new) / 1.0, 3),
                    "cumulative_coverage_after": round((len(base_hit) + len(cum)) / len(denom_ids), 6) if denom_ids else None})
    total_new = len(cum)
    yield_all = (total_new / len(out)) if out else 0.0
    residual = [i for i in remaining if i not in cum]
    cat_of = {}
    for g in (cx.get("gaps") or []):
        for rid in g["ref_ids"]:
            cat_of.setdefault(rid, g["category"])
    stop = ""
    if not out:
        stop = "未提出补检：所有遗漏类均不可由本地检索修复或材料未给出可改查询式"
    elif yield_all <= 0.5:
        stop = "触发停止规则：累计边际收益 %.2f 条/查询 ≤ 阈值 0.5，继续加同义词收益不足" % yield_all
    elif residual and all(cat_of.get(i) in ("source_not_indexed", "ref_record_anomaly") for i in residual):
        stop = "触发停止规则：剩余遗漏全部属于需换源/数据缺陷，本地补检无法修复"
    else:
        stop = "未触发停止规则：累计边际收益 %.2f 条/查询 > 0.5，尚有可试词项（受本轮预算限制未继续）" % yield_all
    return {"rows": out, "total_new_hits": total_new, "queries": len(out),
            "marginal_yield": round(yield_all, 3), "new_records": cum_new_rec,
            "coverage_before": round((len(base_hit)) / len(denom_ids), 6) if denom_ids else None,
            "coverage_after": round((len(base_hit) + total_new) / len(denom_ids), 6) if denom_ids else None,
            "residual_ids": residual, "residual_count": len(residual), "stop_reason": stop,
            "no_gain_queries": sum(1 for x in out if x.get("no_gain")),
            "redundant_queries": sum(1 for x in out if x.get("redundant"))}


# ---------------------------------------------------------------- audit trail
def audit_trail(st, cov, variants, gaps, clusters, sup, rows, drafts, quote_stats):
    formula = ("coverage = |hit ∩ S_policy| / |S_policy| ;  S_policy: all=参考集全部条目(含重复)"
               " ; dedup_only=去重后 ; dedup_exclude_unavailable=去重且剔除 retracted/no_fulltext")
    recompute = {}
    try:
        import csv as _csv
        p = Path(st["out_dir"]) / "hit_ledger.csv"
        with open(p, "r", encoding="utf-8", newline="") as f:
            led = list(_csv.DictReader(f))
        den = [r["ref_id"] for r in led if r["usable"] in ("True", "true", "1")]
        if cov["policy"] == "dedup_only":
            den = [r["ref_id"] for r in led]
        hit = [r["ref_id"] for r in led if r["hit_status"] == "hit" and r["ref_id"] in den]
        recompute = {"source": "hit_ledger.csv", "denominator": len(den), "numerator": len(hit),
                     "coverage": round(len(hit) / len(den), 6) if den else None}
    except Exception as e:
        recompute = {"source": "hit_ledger.csv", "error": "%s: %s" % (type(e).__name__, e)}
    match = (recompute.get("coverage") == cov["coverage"] and recompute.get("denominator") == cov["denominator"])
    det = hashlib.sha256(json.dumps([cov["denominator"], cov["numerator"], len(gaps), len(clusters),
                                     sup.get("total_new_hits"), sup.get("queries")],
                                    sort_keys=True).encode()).hexdigest()[:16]
    low = [r for r in rows if r["certainty"] == "low" or r["hit_status"] == "pending"]
    sc = []
    for x in (drafts.get("spot_check") or []):
        if isinstance(x, dict) and x.get("ref_id"):
            sc.append({"ref_id": x["ref_id"], "agree": bool(x.get("agree")), "note": L.clip(x.get("note"), 120)})
    agree = (sum(1 for x in sc if x["agree"]) / len(sc)) if sc else None
    return {"formula": formula,
            "policy": cov["policy"],
            "refset_fingerprint": st.get("refset_fingerprint"),
            "denominator_ids": cov["denominator_ids"],
            "numerator_ids": cov["numerator_ids"],
            "missed_ids": cov["missed_ids"],
            "excluded_ids": [x["ref_id"] for x in cov["excluded"]],
            "variants": {k: {"denominator": v["denominator"], "numerator": v["numerator"],
                             "coverage": v["coverage"]} for k, v in variants.items()},
            "inputs": st.get("docs_meta") or [],
            "recompute": dict(recompute, matches_report=bool(match)),
            "quote_verbatim": quote_stats,
            "spot_check": {"sample_size": len(sc), "agreement": round(agree, 4) if agree is not None else None,
                           "records": sc,
                           "low_certainty_ids": [r["ref_id"] for r in low][:20],
                           "note": ("未提供人工抽检记录；低置信/待裁决行已单列，其一致性为 null 而非猜测值"
                                    if not sc else "抽检记录来自 draft.spot_check")},
            "determinism_hash": det,
            "determinism_note": "同一输入重复运行时本哈希必须一致（依赖覆盖率/漏检数/补检数，不含时间戳）",
            "skill_version": V, "ledger_rows": len(rows)}


# ----------------------------------------------------------- contract mapping
def resolve_contract(key, ctx):
    """map an output_contract key to a real product value; unmapped keys stay null (never invented)."""
    k = str(key).lower()
    c, cov, sup, refs = ctx["cov"], ctx["cov"], ctx["sup"], ctx["refs"]
    files = ((r"audit|trail|审计", "audit_trail.json"),
             (r"scope|口径", "scope_card.md"),
             (r"ledger|台账|hit_?list|命中矩阵|hit_?matrix", "hit_ledger.csv"),
             (r"matrix|矩阵|classif|分类表", "gap_matrix.csv"),
             (r"atlas|图谱|gap_?json", "gap_atlas.json"),
             (r"supplement_?plan|补检计划|补检表|supplement_?(md|doc)", "supplement_plan.md"),
             (r"report|报告|文档|document|readme|说明", "coverage_report.md"))
    for pat, fn in files:
        if re.search(pat, k):
            return fn
    if re.search(r"coverage|覆盖|recall|召回|rate|率", k):
        return {"coverage": cov["coverage"], "denominator": cov["denominator"], "numerator": cov["numerator"],
                "miss_rate": cov["miss_rate"], "policy": cov["policy"],
                "variants": {p: (ctx.get("variants") or {}).get(p, {}).get("coverage") for p in POLICIES}}
    if re.search(r"miss|gap|漏|遗漏", k):
        return {"miss_count": cov["miss_count"],
                "categories": {x["category"]: x["count"] for x in ctx["clusters"]},
                "residual": sup["residual_count"], "missed_ids": cov["missed_ids"]}
    if re.search(r"supplement|补检|补漏|增量", k):
        return {"queries": sup["queries"], "new_hits": sup["total_new_hits"],
                "marginal_yield": sup["marginal_yield"], "coverage_before": sup["coverage_before"],
                "coverage_after": sup["coverage_after"], "stop_reason": sup["stop_reason"],
                "residual": sup["residual_count"]}
    if re.search(r"reference|refs|参考集|known|denominator|分母", k):
        return [{"ref_id": r["ref_id"], "title": L.clip(r.get("title"), 120), "doi": r.get("doi") or None,
                 "year": r.get("year"), "usable": bool(r["usable"])} for r in refs]
    if re.search(r"count|number|num|total|统计|数量|条数", k):
        return cov["denominator"]
    if re.search(r"summary|conclusion|结论|摘要|status|状态|note|说明|text", k):
        return ("对给定参考集完成覆盖—漏检—补检闭环：分母 %d，命中 %d，遗漏 %d，覆盖率 %s；"
                "补检 %d 条新增命中 %d，残余遗漏 %d。详见 coverage_report.md。"
                % (cov["denominator"], cov["numerator"], cov["miss_count"],
                   ("%.4f" % cov["coverage"]) if cov["coverage"] is not None else "未定义",
                   sup["queries"], sup["total_new_hits"], sup["residual_count"]))
    return None


def contract_values(contract, ctx):
    out, meta = {}, {}
    for k in (contract or {}):
        try:
            v = resolve_contract(k, ctx)
        except Exception as e:
            v = None
            meta[k] = {"kind": "error", "note": "%s: %s" % (type(e).__name__, e)}
            continue
        out[k] = v
        if k not in meta:
            meta[k] = {"kind": type(v).__name__ if v is not None else "null",
                       "provenance": "audit.resolve_contract" if v is not None else "unmapped",
                       "note": "" if v is not None else "该键无法映射到本 Skill 产物，按契约要求保留 null 而未臆造值"}
    return out, meta
