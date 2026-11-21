#!/usr/bin/env python3
"""validate.py -- draft validation, scoring-gate checks and artifact rendering (stdlib only).

Owned by deep-research-evidence-map. Imported by main.py; imports the deterministic
kernel from core.py so that quote anchoring is identical in check/ and build/.
"""
import re

from core import (GEN, ENUM_GAP, ENUM_SQ_LAYER, ENUM_STANCE, ENUM_STRENGTH, ENUM_TOOL, ENUM_TYPE,
                  anchor, as_md, contract_keys, jval, norm, overlap, wants)

BOILER = ("尚待研究", "有待进一步", "有待深入", "具有重要意义", "值得关注", "further research is needed",
          "more studies are needed", "尚存争议", "存在争议")
NEG = ("无显著", "没有显著", "未发现", "无差异", "no significant", "no effect", "no difference",
       "decrease", "reduce", "lower", "下降", "降低", "减少", "负相关", "抑制", "inhibit", "阻碍", "减弱")
POS = ("显著升高", "显著增加", "升高", "增加", "提高", "上升", "increase", "higher", "positive",
       "促进", "enhance", "正相关", "改善")


def polarity(text):
    t = norm(text).lower()
    for w in NEG:
        if w in t:
            return -1
    for w in POS:
        if w in t:
            return 1
    return 0


# ------------------------------------------------------------------ validation
def _list(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, (dict, str))]
    return []


def sub_questions(d):
    out = []
    for i, s in enumerate(_list(d, "sub_questions", "subquestions", "decomposition", "question_tree")):
        if isinstance(s, str):
            s = {"text": s}
        out.append(dict(s, sq_id=str(s.get("sq_id") or s.get("id") or "SQ%d" % (i + 1))))
    return out


def has_cycle(nodes):
    """nodes: {sq_id: [dep_ids]} -> list of sq_ids in a cycle."""
    state, bad = {}, []

    def dfs(u, stack):
        state[u] = 1
        for v in nodes.get(u, []):
            if state.get(v) == 1:
                bad.extend([v] + stack[stack.index(v):] if v in stack else [v])
            elif state.get(v, 0) == 0 and v in nodes:
                dfs(v, stack + [v])
        state[u] = 2

    for n in list(nodes):
        if state.get(n, 0) == 0:
            dfs(n, [n])
    return sorted(set(bad))


def validate_draft(draft, index):
    rep = {"ok": False, "errors": [], "warnings": [], "counts": {}, "six": {}, "fixes": []}

    def err(code, where, detail):
        rep["errors"].append({"code": code, "where": where, "detail": norm(detail)[:400]})

    def warn(code, where, detail):
        rep["warnings"].append({"code": code, "where": where, "detail": norm(detail)[:300]})

    paras = index.get("paras") or {}
    docs = index.get("docs") or {}
    if not isinstance(draft, dict) or not draft:
        err("draft_missing", "draft.json", "no readable draft: run init, read materials with show, write /app/work/draft.json")
        rep["counts"] = {"sub_questions": 0, "evidence": 0, "claims": 0, "conflicts": 0, "gaps": 0}
        rep["fixes"] = ["write /app/work/draft.json then rerun check"]
        return rep

    q = norm(draft.get("research_question") or index.get("question") or "")
    sqs = sub_questions(draft)
    plan = [p for p in _list(draft, "retrieval_plan", "retrieval", "search_plan") if isinstance(p, dict)]
    ev = [e for e in _list(draft, "evidence", "evidence_rows", "evidence_matrix") if isinstance(e, dict)]
    cl = [c for c in _list(draft, "claims", "conclusions", "findings") if isinstance(c, dict)]
    cf = [c for c in _list(draft, "conflicts", "disagreements") if isinstance(c, dict)]
    gp = [g for g in _list(draft, "gaps", "research_gaps") if isinstance(g, dict)]
    ids = {s["sq_id"]: s for s in sqs}
    src_ids = set(paras.keys())

    # ---- decomposition
    if len(sqs) < 3:
        err("too_few_sub_questions", "sub_questions", "%d found; need >=3 independently searchable sub-questions" % len(sqs))
    layers = {norm(s.get("layer")) for s in sqs}
    missing_layers = [l for l in ENUM_SQ_LAYER if l not in layers]
    if sqs and missing_layers:
        warn("layer_gap", "sub_questions", "layers not covered: %s (what/how_far/why/what_missing)" % ",".join(missing_layers))
    nodes = {}
    for s in sqs:
        sid = s["sq_id"]
        text = norm(s.get("text"))
        if len(text) < 12:
            err("sq_text_too_short", sid, "sub-question text is empty or a bare keyword: %r" % text[:60])
        if q and overlap(text, q) > 0.85 and len(text) < len(q) * 1.6:
            err("keyword_rewrite", sid, "sub-question is a rephrasing of the original question (overlap %.2f): make it independently searchable" % overlap(text, q))
        slots = [k for k in ("object", "mechanism", "method", "time_scope", "comparison", "evidence_requirement")
                 if norm(s.get(k))]
        if len(slots) < 3:
            err("sq_slots_thin", sid, "only %d/6 structured slots filled (%s): name object, mechanism/method, time scope, comparison, evidence requirement" % (len(slots), ",".join(slots) or "none"))
        deps = s.get("depends_on") or []
        deps = [str(x) for x in deps] if isinstance(deps, list) else []
        for d in deps:
            if d not in ids:
                err("dep_unknown", sid, "depends_on references unknown sq_id %r" % d)
            if d == sid:
                err("dep_self", sid, "sub-question depends on itself")
        nodes[sid] = deps
        if s.get("layer") and norm(s.get("layer")) not in ENUM_SQ_LAYER:
            warn("layer_enum", sid, "layer %r not in %s" % (s.get("layer"), "/".join(ENUM_SQ_LAYER)))
    cyc = has_cycle(nodes)
    if cyc:
        err("dep_cycle", "sub_questions", "dependency cycle among %s" % ",".join(cyc))

    # ---- retrieval plan
    planned = {str(p.get("sq_id")) for p in plan if p.get("sq_id")}
    for sid in ids:
        if sid not in planned:
            err("plan_missing_sq", sid, "no retrieval_plan entry for this sub-question (retrieval coverage incomplete)")
    for p in plan:
        sid = str(p.get("sq_id") or "?")
        if sid not in ids and sid != "?":
            warn("plan_unknown_sq", sid, "retrieval_plan references a sub-question that does not exist")
        if not norm(p.get("stop_condition")):
            err("stop_condition_missing", sid, "retrieval_plan needs a stop_condition (when to stop searching)")
        if not (p.get("sources_scope") or p.get("sources") or p.get("scope")):
            err("scope_missing", sid, "retrieval_plan needs sources_scope (which sources to search)")
        terms = p.get("query_terms") or p.get("queries") or p.get("terms")
        if not terms or (isinstance(terms, list) and not any(norm(t) for t in terms)):
            err("query_terms_missing", sid, "retrieval_plan needs concrete query_terms")
        sc = p.get("sources_scope") or []
        for s in (sc if isinstance(sc, list) else [sc]):
            if str(s) in src_ids or str(s).startswith("all") or str(s).upper() in ("ALL", "*"):
                continue
            warn("scope_unknown_source", sid, "sources_scope names %r which is not an indexed source" % s)

    # ---- evidence
    evmap, verified, anchored = {}, 0, 0
    for i, e in enumerate(ev):
        eid = str(e.get("evidence_id") or e.get("id") or "E%d" % (i + 1))
        e["evidence_id"] = eid
        sid = str(e.get("source_id") or e.get("doc_id") or e.get("paper_id") or "")
        quote = e.get("quote") or e.get("excerpt") or ""
        if sid not in src_ids:
            err("evidence_unknown_source", eid, "source_id %r is not an indexed source (%s)" % (sid, ",".join(sorted(src_ids)[:8])))
            evmap[eid] = e
            continue
        if str(e.get("sq_id")) not in ids:
            err("evidence_unknown_sq", eid, "sq_id %r does not exist" % e.get("sq_id"))
        if len(norm(quote)) < 8:
            err("quote_too_short", eid, "quote shorter than 8 chars: %r" % norm(quote)[:40])
        a = anchor(paras[sid], quote)
        e["anchor"] = dict(source_id=sid, loc=a["loc"], para_index=a["para_index"], offset=a["offset"],
                           occurrences=a["occurrences"], mode=a["mode"], span_paras=a["span_paras"])
        if not a["found"]:
            err("quote_not_found", eid, "quote not found verbatim in %s: %r" % (sid, norm(quote)[:90]))
        else:
            verified += 1
            if a["loc"]:
                anchored += 1
                given = norm(e.get("locator"))
                if given and given != a["loc"]:
                    warn("locator_corrected", eid, "given %r -> anchored %r (paragraph anchor wins)" % (given, a["loc"]))
                e["locator"] = a["loc"]
                e.setdefault("locator_given", given or None)
        if norm(e.get("strength")) not in ENUM_STRENGTH:
            warn("strength_enum", eid, "strength %r not in strong/moderate/weak" % e.get("strength"))
        if e.get("stance") and norm(e.get("stance")) not in ENUM_STANCE:
            warn("stance_enum", eid, "stance %r not in supports/refutes/neutral" % e.get("stance"))
        if e.get("locator") in (None, ""):
            warn("locator_missing", eid, "no locator; anchored locator unavailable")
        evmap[eid] = e
    seen = {}
    for e in ev:
        k = (str(e.get("source_id")), norm(e.get("quote"), True)[:120])
        if k in seen:
            warn("evidence_duplicate", e.get("evidence_id"), "same quote already used by %s" % seen[k])
        seen[k] = e.get("evidence_id")

    # ---- claims
    backlinked = 0
    claim_pol = {}
    for i, c in enumerate(cl):
        cid = str(c.get("claim_id") or c.get("id") or "C%d" % (i + 1))
        c["claim_id"] = cid
        eids = c.get("evidence_ids") or c.get("evidence") or []
        eids = [str(x) for x in eids] if isinstance(eids, list) else [str(eids)]
        typ = norm(c.get("type") or "material_fact")
        if typ not in ENUM_TYPE:
            warn("claim_type_enum", cid, "type %r not in material_fact/inference/undetermined" % typ)
        if typ == "undetermined":
            if eids:
                err("undetermined_with_evidence", cid, "type=undetermined must not claim evidence; use inference+weak evidence instead")
            if not norm(c.get("boundary")):
                err("undetermined_no_boundary", cid, "undetermined claim needs boundary = what was searched and why it is undetermined")
        else:
            if not eids:
                err("claim_no_evidence", cid, "claim has no evidence_ids: every conclusion must back-link to a source paragraph")
            for x in eids:
                if x not in evmap:
                    err("claim_unknown_evidence", cid, "evidence_id %r not in the evidence table" % x)
                elif not evmap[x].get("anchor", {}).get("mode") in ("miss", "too_short", None):
                    backlinked += 1
                    break
            if typ in ("inference",) and not norm(c.get("boundary")):
                err("inference_no_boundary", cid, "inference claim needs boundary (conditions / no-extrapolation range)")
        if not norm(c.get("text")):
            err("claim_text_empty", cid, "claim text is empty")
        if str(c.get("sq_id")) not in ids and c.get("sq_id"):
            warn("claim_unknown_sq", cid, "sq_id %r does not exist" % c.get("sq_id"))
        claim_pol.setdefault(str(c.get("sq_id")), []).append((cid, polarity(c.get("text"))))

    used_eids = {x for c in cl for x in (c.get("evidence_ids") or []) if isinstance(x, str)}
    und_sq = {str(c.get("sq_id")) for c in cl if norm(c.get("type")) == "undetermined"}
    for e in ev:  # evidence that documents "no data" inside an undetermined sub-question is not orphan
        if str(e.get("sq_id")) in und_sq:
            used_eids.add(str(e.get("evidence_id")))
    for eid in [e.get("evidence_id") for e in ev]:
        if eid and eid not in used_eids:
            warn("evidence_orphan", eid, "evidence row is never cited by a claim: cite it or drop it (unused evidence weakens back-linking)")

    # ---- conflicts
    for i, x in enumerate(cf):
        xid = str(x.get("conflict_id") or x.get("id") or "X%d" % (i + 1))
        x["conflict_id"] = xid
        sides = [x.get("side_a") or x.get("a") or {}, x.get("side_b") or x.get("b") or {}]
        srcs = []
        for tag, s in zip(("side_a", "side_b"), sides):
            sid = str(s.get("source_id") or "")
            if sid not in src_ids:
                err("conflict_side_source", xid, "%s source_id %r not indexed" % (tag, sid))
                continue
            srcs.append(sid)
            a = anchor(paras[sid], s.get("quote") or "")
            s["anchor"] = dict(source_id=sid, loc=a["loc"], mode=a["mode"], occurrences=a["occurrences"])
            if not a["found"]:
                err("conflict_quote_not_found", xid, "%s quote not verbatim in %s: %r" % (tag, sid, norm(s.get("quote"))[:70]))
            elif a["loc"]:
                s["locator"] = a["loc"]
            if not norm(s.get("position")):
                warn("conflict_position_missing", xid, "%s has no position summary" % tag)
        if len(set(srcs)) == 2 and len(srcs) == 2 and srcs[0] == srcs[1]:
            err("conflict_same_source", xid, "both sides cite the same source: a conflict needs two independent sources")
        elif len(set(srcs)) < 2 and srcs:
            err("conflict_one_side", xid, "only one side resolved to an indexed source")
        if len(norm(x.get("possible_reason"))) < 10:
            err("conflict_reason_thin", xid, "possible_reason too thin: name sample/method/condition/metric/era difference")
        if not norm(x.get("impact_on_conclusion")):
            warn("conflict_no_impact", xid, "state how this unresolved difference affects the conclusion")
        if not norm(x.get("sq_id")):
            warn("conflict_no_sq", xid, "link the conflict to a sub-question")

    # ---- gaps
    for i, g in enumerate(gp):
        gid = str(g.get("gap_id") or g.get("id") or "G%d" % (i + 1))
        g["gap_id"] = gid
        gt = norm(g.get("gap_type"))
        if gt not in ENUM_GAP:
            err("gap_type_enum", gid, "gap_type %r not in %s" % (gt, "/".join(ENUM_GAP)))
        basis = norm(g.get("basis") or g.get("evidence_of_gap"))
        if len(basis) < 15:
            err("gap_basis_thin", gid, "basis too short: say which search/source is missing and what was consulted")
        elif not re.search(r"\b(E\d+|S\d+|R\d+|X\d+|SQ\d+)\b", basis) and not re.search(r"检索|搜索|search|query|未命中|查不到|no source", basis, re.I):
            err("gap_basis_unlinked", gid, "basis must trace to E#/S#/R# or a concrete search term/range")
        if any(b in basis for b in BOILER) and len(basis) < 40:
            err("gap_boilerplate", gid, "boilerplate gap statement (%r) without retrieval evidence" % basis[:40])
        if not norm(g.get("description")):
            err("gap_no_description", gid, "gap has no description")

    # ---- undeclared conflict detection (this skill's own guard)
    declared = {norm(c.get("topic")) for c in cf}
    for sid, lst in claim_pol.items():
        neg = [cid for cid, p in lst if p < 0]
        pos = [cid for cid, p in lst if p > 0]
        if neg and pos:
            tag = "SQ:%s" % sid
            if not any(tag.lower() in d.lower() or sid in d for d in declared) and not draft.get("no_conflict_observed"):
                err("conflict_undeclared", tag, "claims %s vs %s point in opposite directions but no conflict entry declares it: present both sides" % (",".join(pos[:2]), ",".join(neg[:2])))

    if cf and all(norm(x.get("resolution")) == "unresolved" for x in cf) and len(cf) > 0:
        warn("all_conflicts_unresolved", "conflicts", "every conflict is unresolved: attribute at least the ones you can (sample/method/condition)")
    if not cf and not draft.get("no_conflict_observed"):
        err("conflicts_not_assessed", "conflicts", "no conflict assessed: either list conflicting findings or set no_conflict_observed=true with the searched scope")
    if not gp:
        err("gaps_missing", "gaps", "no research gap recorded: type it (retrieval_gap/unresolved_conflict/method_limitation/scope_limit) with retrieval evidence")

    # ---- count / six requirements
    ok_backlink = (backlinked / float(max(len([c for c in cl if norm(c.get("type") or "material_fact") != "undetermined"]), 1)))
    counts = dict(sub_questions=len(sqs), layers=len(layers & set(ENUM_SQ_LAYER)), retrieval_plan=len(plan),
                  evidence=len(ev), evidence_verified=verified, evidence_anchored=anchored,
                  quote_pass_rate=round(verified / float(max(len(ev), 1)), 3),
                  claims=len(cl), claims_backlinked=backlinked, claims_backlinked_ratio=round(min(ok_backlink, 1.0), 3),
                  undetermined=sum(1 for c in cl if norm(c.get("type")) == "undetermined"),
                  conflicts=len(cf), gaps=len(gp),
                  sources_read=sum(1 for k in paras if paras.get(k)),
                  sources_with_evidence=len({str(e.get("source_id")) for e in ev}),
                  gaps_typed=len({norm(g.get("gap_type")) for g in gp}))
    six = {
        "problem_decomposition": bool(len(sqs) >= 3 and len(layers & set(ENUM_SQ_LAYER)) >= 3 and not cyc),
        "retrieval_coverage": bool(plan and all(s["sq_id"] in planned for s in sqs) and all(norm(p.get("stop_condition")) for p in plan)),
        "evidence_backlink": bool(ev and counts["quote_pass_rate"] >= 0.99 and counts["claims_backlinked_ratio"] >= 0.95),
        "conflict_evidence": bool(cf or draft.get("no_conflict_observed")),
        "synthesis_conclusion": bool(cl and any(norm(c.get("type")) != "undetermined" for c in cl)),
        "research_gap": bool(gp and all(norm(g.get("gap_type")) in ENUM_GAP for g in gp)),
    }
    rep["counts"], rep["six"] = counts, six
    rep["ok"] = not rep["errors"]
    rep["fixes"] = ["FIX [%s] %s :: %s" % (e["code"], e["where"], e["detail"]) for e in rep["errors"][:12]]
    return rep


def table_md(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(norm(str(c)).replace("|", "\\|") or "-" for c in r) + " |")
    return "\n".join(out)


def coverage_of(M):
    sqs = M.get("sub_questions") or []
    ev = M.get("evidence") or []
    used = {str(e.get("record_id")) for e in ev if e.get("record_id")}
    if not used:  # fall back to source-level linkage when evidence rows carry no record_id
        linked = {str(e.get("source_id")) for e in ev}
        used = {str(r.get("record_id")) for r in (M.get("records") or [])
                if str(r.get("source_id")) in linked}
    records_used = len(used)
    with_ev = {str(e.get("sq_id")) for e in ev if str(e.get("sq_id"))}
    counts = M.get("counts") or {}
    return {
        "sub_questions": len(sqs),
        "sub_questions_with_evidence": len(with_ev),
        "sub_questions_without_evidence": [s.get("sq_id") for s in sqs if s.get("sq_id") not in with_ev],
        "sources_expected": M.get("sources_expected", len(M.get("sources") or [])),
        "sources_read": counts.get("sources_read", 0),
        "sources_with_evidence": counts.get("sources_with_evidence", 0),
        "records_expected": M.get("records_total", 0),
        "records_screened": len(M.get("inclusion_decisions") or []),
        "records_used": records_used,
        "evidence_count": len(ev),
        "evidence_quote_verified": counts.get("evidence_verified", 0),
        "quote_pass_rate": counts.get("quote_pass_rate", 0.0),
        "claims": len(M.get("claims") or []),
        "claims_backlinked": counts.get("claims_backlinked", 0),
        "claims_backlinked_ratio": counts.get("claims_backlinked_ratio", 0.0),
        "undetermined_claims": counts.get("undetermined", 0),
        "conflicts": len(M.get("conflicts") or []),
        "gaps": len(M.get("gaps") or []),
        "gaps_typed": counts.get("gaps_typed", 0),
        "six_requirements": M.get("six") or {},
        "six_requirements_met": sum(1 for v in (M.get("six") or {}).values() if v),
    }
