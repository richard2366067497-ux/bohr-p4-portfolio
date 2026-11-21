#!/usr/bin/env python3
"""build.py -- artifact rendering and unconditional finalize for deep-research-evidence-map.

Called by main.py as ``cmd_build(args, H)`` where H exposes the shared helpers
(paths / find_case / partial / save_partial / build_index / DEFAULT_CONTRACT).
Every path is defensive: a missing or broken draft.json, an unreadable index or any
exception inside rendering still yields a complete, contract-filled result.json plus a
minimal report, with status=partial and explicit degradations. Exit code is always 0.
"""
import csv
import json
import re
import time

import core as C
import validate as V
from core import as_md, jval, norm

GEN = C.GEN


# ------------------------------------------------------------------ build helpers
def scaffold(index, degr):
    """structural fallback used only when no usable draft exists: no invented findings."""
    q = index.get("question") or ""
    toks = [t for t in re.split(r"[\s,;/、，。？?！!()（）\[\]]+", q) if len(t) > 1][:8]
    kw = "、".join(toks[:4]) or "研究问题"
    srcs = list((index.get("docs") or {}).keys())
    sqs, plan = [], []
    slots = [("what", "材料就「%s」直接陈述了哪些事实与量化结果？" % kw, "object 与直接证据"),
             ("how_far", "「%s」在不同材料/条件下的一致程度与量级差异是什么？" % kw, "比较关系与量化差异"),
             ("why", "材料给出的机制或解释是什么，是否存在相互竞争的解释？", "机制与竞争解释"),
             ("what_missing", "材料范围内无法回答「%s」的哪一部分，缺什么类型的证据？" % kw, "检索缺口与证据类型")]
    for i, (layer, text, ev) in enumerate(slots, 1):
        sid = "SQ%d" % i
        sqs.append({"sq_id": sid, "layer": layer, "text": text, "object": kw,
                    "mechanism": "由 Agent 补齐" if layer == "why" else "",
                    "method": "", "time_scope": "", "comparison": "跨材料对照",
                    "evidence_requirement": ev, "depends_on": ["SQ1"] if i > 2 else [],
                    "search_terms": toks[:4], "origin": "fallback_scaffold"})
        plan.append({"sq_id": sid, "sources_scope": srcs, "query_terms": toks[:4], "order": i,
                     "parallel_group": "G1" if layer in ("how_far", "why") else None,
                     "stop_condition": "兜底计划：读完清单内全部来源即停止（未由 Agent 编排）",
                     "origin": "fallback_scaffold"})
    degr.append("decomposition/retrieval plan are a structural scaffold (no draft.json): sub-question wording must be authored by the Agent")
    return sqs, plan


def cmd_build(a, H):
    t0 = time.time()
    inp, out, wk = H.paths(a)
    out.mkdir(parents=True, exist_ok=True)
    errs, degr, pend = [], [], []
    H.save_partial({}, [{"code": "build_started", "detail": "final artifacts not rendered yet"}], out, "build_boot")
    idx = {}
    try:
        idx = C.jread(wk / "index.json") if (wk / "index.json").exists() else {}
    except Exception as e:
        errs.append({"code": "index_unreadable", "detail": repr(e)})
    if not idx.get("docs") and not idx.get("question"):
        errs.append({"code": "index_rebuilt", "detail": "no usable index: init re-run inside build"})
        try:
            idx, _case, e2, d2 = H.build_index(inp, [], [])
            errs += e2
            degr += d2
            wk.mkdir(parents=True, exist_ok=True)
            C.jwrite(wk / "index.json", idx)
        except Exception as e:
            errs.append({"code": "init_failed", "detail": repr(e)})
            idx = {"docs": {}, "paras": {}, "records": [], "contract": dict((k, "array") for k in H.DEFAULT_CONTRACT),
                   "question": "", "case_id": "unknown", "tool_calls": []}
    case = {}
    try:
        case, _ = H.find_case(inp, [])
    except Exception:
        case = {}
    if not isinstance(idx.get("contract"), (dict, list)) or not C.contract_keys(idx.get("contract")):
        idx["contract"] = case.get("output_contract") if C.contract_keys(case.get("output_contract")) else \
            dict((k, "array") for k in H.DEFAULT_CONTRACT)
    paras, docs = idx.get("paras") or {}, idx.get("docs") or {}
    cid = str(idx.get("case_id") or (case or {}).get("case_id") or "unknown")

    draft, dsrc = {}, "none"
    if (wk / "draft.json").exists():
        try:
            draft = C.jread(wk / "draft.json")
            dsrc = str(wk / "draft.json")
        except Exception as e:
            errs.append({"code": "draft_unreadable", "detail": "%s: %r" % (wk / "draft.json", e)})
            degr.append("draft.json is not valid JSON: build continued with the degraded fallback")
    if not isinstance(draft, dict) or not draft:
        draft = {}
        degr.append("no usable draft.json at build time: produced a complete but degraded deliverable "
                    "(structure + source inventory only, status=partial)")
        pend.append("Agent must read the materials with `show`, author /app/work/draft.json, then re-run check and build")
    if not draft.get("research_question") and idx.get("question"):
        draft["research_question"] = idx["question"]

    sqs = V.sub_questions(draft)
    plan = [p for p in V._list(draft, "retrieval_plan", "retrieval", "search_plan") if isinstance(p, dict)]
    ev = [e for e in V._list(draft, "evidence", "evidence_rows") if isinstance(e, dict)]
    cl = [c for c in V._list(draft, "claims", "conclusions", "findings") if isinstance(c, dict)]
    cf = [c for c in V._list(draft, "conflicts", "disagreements") if isinstance(c, dict)]
    gp = [g for g in V._list(draft, "gaps", "research_gaps") if isinstance(g, dict)]
    if not sqs:
        sqs, plan2 = scaffold(idx, degr)
        plan = plan or plan2
    if not plan:
        plan = [{"sq_id": s["sq_id"], "sources_scope": list(docs), "query_terms": s.get("search_terms") or [],
                 "order": i + 1, "parallel_group": None,
                 "stop_condition": "auto: stop when every indexed source has been screened",
                 "origin": "auto"} for i, s in enumerate(sqs)]
        degr.append("retrieval_plan derived from sub-questions (draft had none)")

    # anchor every evidence row; drop rows whose quote is not verbatim in the claimed source
    kept, dropped = [], 0
    for i, e in enumerate(ev):
        eid = str(e.get("evidence_id") or "E%d" % (i + 1))
        e["evidence_id"] = eid
        sid = str(e.get("source_id") or "")
        if sid not in paras:
            dropped += 1
            degr.append("evidence %s dropped: source_id %r not indexed" % (eid, sid))
            continue
        a2 = C.anchor(paras[sid], e.get("quote") or "")
        e["anchor"] = dict(source_id=sid, loc=a2["loc"], para_index=a2["para_index"], offset=a2["offset"],
                           occurrences=a2["occurrences"], mode=a2["mode"], span_paras=a2["span_paras"])
        if not a2["found"]:
            dropped += 1
            degr.append("evidence %s dropped: quote not verbatim in %s (%r)" % (eid, sid, C.norm(e.get("quote"))[:60]))
            continue
        if a2["loc"] and C.norm(e.get("locator")) not in ("", a2["loc"]):
            degr.append("evidence %s locator %r corrected to anchored %r" % (eid, e.get("locator"), a2["loc"]))
            e["locator_given"] = e.get("locator")
        e["locator"] = a2["loc"] or e.get("locator")
        kept.append(e)
    if dropped:
        pend.append("%d evidence row(s) were dropped for unverifiable quotes: re-read the source text and quote verbatim" % dropped)
    ev = kept
    if not ev:
        pend.append("evidence matrix is empty: every conclusion needs at least one anchored quote")
    if not cl:
        cl = [{"claim_id": "C1", "sq_id": (sqs[0]["sq_id"] if sqs else None), "type": "undetermined",
               "text": "本次运行未生成证据矩阵，因此不对研究问题作任何实质性结论。",
               "evidence_ids": [], "confidence": "low",
               "boundary": "证据缺失：draft.json 中没有可回链的 quote；结论范围为空，不能外推",
               "origin": "fallback"}]
        degr.append("no claims in the draft: emitted one explicit undetermined claim instead of inventing findings")
    if not cf and not draft.get("no_conflict_observed"):
        degr.append("no conflict entry and no_conflict_observed not set: conflict assessment is missing")
    if not gp:
        gp = [{"gap_id": "G1", "description": "未完成类型化的研究空白检索（本次运行无 gap 记录）",
               "gap_type": "retrieval_gap",
               "basis": "检索范围 %s 内未登记 gap；S* 清单已读但未逐条判定缺口" % ", ".join(list(docs)[:6]),
               "searched_scope": ", ".join(list(docs)[:6]) or "none",
               "would_resolve": "补充针对性检索并逐条登记检索缺口", "origin": "fallback"}]
        degr.append("gaps section filled with one explicit retrieval_gap placeholder (nothing invented)")

    rep = V.validate_draft({"research_question": draft.get("research_question"), "sub_questions": sqs,
                            "retrieval_plan": plan, "evidence": ev, "claims": cl, "conflicts": cf,
                            "gaps": gp, "no_conflict_observed": draft.get("no_conflict_observed")}, idx)
    degr += ["check: %s (%s)" % (e["code"], e["detail"][:110]) for e in rep["errors"][:6] if e["code"] != "draft_missing"]

    calls = list(idx.get("tool_calls") or [])
    for i, t in enumerate([t for t in V._list(draft, "tool_calls", "tool_call_log") if isinstance(t, dict)]):
        t.setdefault("step_id", "A%d" % (i + 1))
        t.setdefault("origin", "agent")
        t.setdefault("retry_count", 0)
        calls.append(t)
    calls.append({"step_id": "TBD", "tool": "calc", "origin": "script",
                  "params": {"action": "anchor+validate"}, "status": "ok", "retry_count": 0,
                  "result_summary": "%d evidence anchored, %d dropped, quote_pass=%.3f" %
                                    (len(ev), dropped, rep["counts"].get("quote_pass_rate", 0)),
                  "produced_artifact": "output/evidence_matrix.jsonl"})

    for i, t in enumerate(calls, 1):  # stable step ids so any trace can be replayed in order
        t["step_id"] = "T%d" % i
    try:  # replayable trace of every material-handling step
        wpath = H.paths(a)[2] / "tool_calls.jsonl"
        with wpath.open("w", encoding="utf-8") as f:
            for t in calls:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    except Exception as e:
        errs.append({"code": "trace_write_failed", "detail": repr(e)})
    M = dict(case_id=cid, records=[{"record_id": r["record_id"], "source_id": r["source_id"]} for r in (idx.get("records") or [])], research_question=draft.get("research_question") or idx.get("question") or "",
             scope=draft.get("scope") or {}, sub_questions=sqs, retrieval_plan=plan,
             evidence=ev, claims=cl, conflicts=cf, gaps=gp,
             uncertainties=draft.get("uncertainties") or [], bounded_proposal=draft.get("bounded_proposal") or {},
             inclusion_decisions=[d for d in V._list(draft, "inclusion_decisions", "screening") if isinstance(d, dict)],
             method_notes=draft.get("method_notes") or {},
             no_conflict_observed=bool(draft.get("no_conflict_observed")),
             tool_calls=calls, counts=rep["counts"], six=rep["six"],
             sources=[dict(source_id=k, file=v["filename"], kind=v["kind"], engine=v["engine"],
                           n_paras=len(paras.get(k) or []), scheme=v.get("scheme"),
                           title=v.get("title"), declared=v.get("declared"), notes=v.get("notes"))
                      for k, v in docs.items()],
             source_inventory=[[k, v["filename"], v["kind"], len(paras.get(k) or []),
                                (v.get("quality") if v.get("quality") is not None else "-")]
                               for k, v in docs.items()],
             records_total=len(idx.get("records") or []),
             sources_expected=idx.get("sources_expected") or len(docs),
             degradations=degr, pending_human=pend)
    cov = V.coverage_of(M)
    M["coverage"] = cov
    cn = rep["counts"]
    has_body = bool(ev and any(c.get("type") != "undetermined" for c in cl))
    M["status"] = "ok" if (has_body and rep["ok"] and not degr) else ("partial" if (ev or docs) else "failed")
    if not docs:
        M["status"] = "partial"
        pend.append("no readable source material under the input directory: report contains structure only")
    scope = M["scope"] if isinstance(M["scope"], dict) else {}
    M["scope_note"] = "；".join("%s=%s" % (k, C.as_md(scope[k]).replace("\n", " ")) for k in scope if scope.get(k))[:300]
    M["report"] = render_report(M)

    tp = out / "research_plan.json"
    C.jwrite(tp, {"case_id": cid, "question_original": M["research_question"],
                  "question_source": idx.get("question_source"), "scope": M["scope"],
                  "decomposition": {"sub_questions": sqs},
                  "dependency_graph": dict((s["sq_id"], s.get("depends_on") or []) for s in sqs),
                  "retrieval_plan": plan,
                  "parallel_groups": sorted({str(p.get("parallel_group")) for p in plan if p.get("parallel_group")}),
                  "stop_conditions": dict((p.get("sq_id"), p.get("stop_condition")) for p in plan),
                  "constraints": idx.get("constraints") or {},
                  "search_protocol_excerpt": (idx.get("protocol") or "")[:4000],
                  "generator": GEN})
    with (out / "evidence_matrix.jsonl").open("w", encoding="utf-8") as f:
        for e in ev:
            f.write(json.dumps(dict(evidence_id=e.get("evidence_id"), sq_id=e.get("sq_id"),
                                    source_id=e.get("source_id"), record_id=e.get("record_id"),
                                    locator=e.get("locator"), quote=e.get("quote"),
                                    strength=e.get("strength"), stance=e.get("stance"),
                                    anchor=e.get("anchor"), notes=e.get("notes")),
                               ensure_ascii=False) + "\n")
    cols = ["evidence_id", "sq_id", "source_id", "record_id", "locator", "quote", "strength", "stance",
            "anchor_mode", "notes"]
    with (out / "evidence_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in ev:
            w.writerow([e.get("evidence_id"), e.get("sq_id"), e.get("source_id"), e.get("record_id"),
                        e.get("locator"), e.get("quote"), e.get("strength"), e.get("stance"),
                        (e.get("anchor") or {}).get("mode"), e.get("notes")])
    C.jwrite(out / "synthesis.json", {"case_id": cid, "claims": cl, "conflicts": cf, "gaps": gp,
                                      "bounded_proposal": M["bounded_proposal"],
                                      "uncertainties": M["uncertainties"],
                                      "method_notes": M["method_notes"],
                                      "counts": cn, "six_requirements": rep["six"],
                                      "check_errors": [{"code": e["code"], "where": e["where"]} for e in rep["errors"][:20]]})
    C.jwrite(out / "coverage.json", cov)
    C.twrite(out / "report.md", M["report"])

    M["artifacts"] = ["result.json", "research_plan.json", "evidence_matrix.jsonl", "evidence_matrix.csv",
                      "synthesis.json", "coverage.json", "report.md"]
    res, missing, empty_soft = C.fill_contract(idx.get("contract"), M)
    res.update(case_id=cid, status=M["status"], sources=M["sources"], errors=errs,
               degradations=degr, uncertainties=(M["uncertainties"] or
                                                 ["no explicit uncertainty recorded: read the report's gap section"]),
               changes=[{"step": "init", "detail": "materials indexed into locator paragraphs"},
                        {"step": "build", "detail": "artifacts rendered from %s" % dsrc},
                        {"step": "anchoring", "detail": "%d evidence anchored, %d dropped for unverifiable quotes" % (len(ev), dropped)},
                        {"step": "contract", "detail": "%d/%d contract fields filled" %
                                                      (len(C.contract_keys(idx.get("contract"))) - len(missing),
                                                       len(C.contract_keys(idx.get("contract"))))}],
               runtime=dict(skill=GEN, stage="final", seconds=round(time.time() - t0, 2),
                            sources=len(docs), evidence=len(ev), claims=len(cl),
                            quote_pass_rate=cn.get("quote_pass_rate"),
                            six_requirements=sum(1 for v in rep["six"].values() if v)),
               coverage=cov, six_requirements=rep["six"], counts=cn, tool_calls=calls,
               artifacts=M["artifacts"], report_path=str(out / "report.md"),
               research_question=M["research_question"], sub_questions=sqs, retrieval_plan=plan,
               evidence=ev, claims=cl, conflicts=cf, gaps=gp, report=M["report"],
               pending_human=pend)
    if rep["errors"]:
        degr.append("draft check reported %d issue(s): %s (details in synthesis.json.check_errors)" %
                    (len(rep["errors"]), ", ".join(sorted({e["code"] for e in rep["errors"]})[:6])))
    if missing and M["status"] == "ok":
        M["status"] = "partial"
        res["status"] = "partial"
    if missing:
        res["degradations"].append("output_contract keys with no matching content (kept as null/[]): %s" % ", ".join(missing))
        res.setdefault("pending_human", []).append("fill contract fields: %s" % ", ".join(missing))
    C.jwrite(out / "result.json", res)
    print("status=%s case_id=%s sources=%d records=%d evidence=%d(dropped=%d) claims=%d conflicts=%d gaps=%d"
          % (M["status"], cid, len(docs), len(idx.get("records") or []), len(ev), dropped, len(cl), len(cf), len(gp)))
    print("coverage: quote_pass=%s backlink=%s six=%d/6 sub_questions=%d"
          % (cn.get("quote_pass_rate"), cn.get("claims_backlinked_ratio"),
             sum(1 for v in rep["six"].values() if v), len(sqs)))
    print("artifacts: %s | unfilled contract: %s | empty-but-typed: %s"
          % (", ".join(M["artifacts"]), missing or "none", empty_soft or "none"))
    print("draft=%s | check_errors=%d | degradations=%d" % (dsrc, len(rep["errors"]), len(degr)))
    return 0


# ------------------------------------------------------------------ rendering
def render_report(M):
    q = M.get("research_question") or "(未从输入中恢复出研究问题)"
    L = []
    A = L.append
    A("# 深度研究报告：%s" % norm(q)[:120])
    A("")
    A("> 生成方式：`deep-research-evidence-map v1.0.0` 由 Agent 工作稿 `/app/work/draft.json` 渲染。"
      "结论句后的 `[E#]` 指向证据矩阵行，`[S# loc]` 指向来源段落；运行状态 `%s`。" % M.get("status"))
    A("")
    if M.get("scope_note"):
        A("**范围**：%s" % M["scope_note"])
        A("")
    A("## 1. 研究问题与范围")
    A("")
    A("- 原始问题：%s" % norm(q))
    sc = M.get("scope") or {}
    if isinstance(sc, dict) and sc:
        for k in ("time_range", "domain", "population", "inclusion", "exclusion"):
            if sc.get(k):
                A("- %s: %s" % (k, as_md(sc[k]).replace("\n", " ")))
    A("- 材料规模：来源 %d 个（可读 %d）、记录 %d 条、证据 %d 条、结论 %d 条、冲突 %d 组、空白 %d 条"
      % (len(M.get("sources") or []), M.get("counts", {}).get("sources_read", 0),
         M.get("records_total", 0), len(M.get("evidence") or []), len(M.get("claims") or []),
         len(M.get("conflicts") or []), len(M.get("gaps") or [])))
    A("")

    A("## 2. 问题拆解树")
    A("")
    sqs = M.get("sub_questions") or []
    if not sqs:
        A("_未提供拆解（工作稿缺失或未写 sub_questions）：本报告不代替拆解，请按 SKILL.md §6 补齐后重跑 build。_")
    else:
        roots = [s for s in sqs if not (s.get("depends_on") or [])]
        kids = {s["sq_id"]: [t["sq_id"] for t in sqs if s["sq_id"] in (t.get("depends_on") or [])] for s in sqs}
        seen = set()

        def draw(sid, depth):
            if sid in seen:
                return
            seen.add(sid)
            s = next(x for x in sqs if x["sq_id"] == sid)
            A("%s- **%s** [%s] %s" % ("  " * depth, sid, s.get("layer") or "-", norm(s.get("text"))[:220]))
            slots = [(k, norm(s.get(k))) for k in ("object", "mechanism", "method", "time_scope", "comparison", "evidence_requirement") if norm(s.get(k))]
            if slots:
                A("%s  - 槽位：%s" % ("  " * depth, "；".join("%s=%s" % (k, v[:70]) for k, v in slots)))
            if s.get("search_terms"):
                A("%s  - 检索词：%s" % ("  " * depth, ", ".join(norm(t) for t in s["search_terms"])[:200]))
            for k in kids.get(sid, []):
                draw(k, depth + 1)

        for r in roots or sqs:
            draw(r["sq_id"], 0)
        for s in sqs:
            if s["sq_id"] not in seen:
                draw(s["sq_id"], 0)
    A("")
    A("## 3. 检索规划与覆盖")
    A("")
    plan = M.get("retrieval_plan") or []
    if plan:
        A(V.table_md(["子问题", "顺序", "并行组", "来源范围", "检索词", "停止条件"],
                   [[p.get("sq_id"), p.get("order"), p.get("parallel_group") or "-",
                     ", ".join(map(str, p.get("sources_scope") or [])) or "-",
                     ", ".join(norm(t) for t in (p.get("query_terms") or []))[:120] or "-",
                     norm(p.get("stop_condition"))[:120] or "-"] for p in plan]))
    else:
        A("_无检索计划记录。_")
    A("")
    cov = M.get("coverage") or {}
    A("覆盖计数：子问题 %s（有证据 %s）｜来源 期望 %s/已读 %s/有证据 %s｜记录 期望 %s/已筛 %s/采用 %s｜"
      "证据 %s（逐字通过 %s）｜结论回链率 %s｜六类要点 %s/6"
      % (cov.get("sub_questions"), cov.get("sub_questions_with_evidence"), cov.get("sources_expected"),
         cov.get("sources_read"), cov.get("sources_with_evidence"), cov.get("records_expected"),
         cov.get("records_screened"), cov.get("records_used"), cov.get("evidence_count"),
         cov.get("quote_pass_rate"), cov.get("claims_backlinked_ratio"),
         sum(1 for v in (M.get("six") or {}).values() if v)))
    A("")
    A("## 4. 工具调用记录")
    A("")
    tc = M.get("tool_calls") or []
    if tc:
        A(V.table_md(["step", "tool", "参数摘要", "返回摘要", "状态", "重试"],
                   [[t.get("step_id"), t.get("tool"), norm(jval(t.get("params")))[:80],
                     norm(t.get("result_summary"))[:100], t.get("status"), t.get("retry_count", 0)] for t in tc]))
    else:
        A("_无工具调用记录。_")
    A("")
    A("## 5. 证据矩阵")
    A("")
    ev = M.get("evidence") or []
    if ev:
        A(V.table_md(["id", "子问题", "来源", "locator", "强度", "立场", "逐字引文"],
                   [["[%s]" % e.get("evidence_id"), e.get("sq_id") or "-", e.get("source_id"),
                     e.get("locator") or "-", e.get("strength") or "-", e.get("stance") or "-",
                     norm(e.get("quote"))[:220]] for e in ev]))
    elif M.get("source_inventory"):
        A("_证据矩阵为空：以下为本次读到的来源清单（不代表任何结论）。_")
        A("")
        A(V.table_md(["来源", "文件", "类型", "段落数", "文本质量"], M["source_inventory"]))
    else:
        A("_证据矩阵为空。_")
    A("")
    A("## 6. 综合结论")
    A("")
    cl = M.get("claims") or []
    if not cl:
        A("_无结论。_")
    for c in cl:
        refs = "".join("[%s]" % x for x in (c.get("evidence_ids") or []))
        A("- **%s**（%s%s）%s %s" % (c.get("claim_id"), c.get("type") or "material_fact",
                                     "/" + norm(c.get("confidence")) if c.get("confidence") else "",
                                     norm(c.get("text")), refs))
        if c.get("boundary"):
            A("  - 边界：%s" % norm(c["boundary"]))
        locs = ["%s %s" % (x.get("source_id"), x.get("locator")) for x in ev
                if x.get("evidence_id") in (c.get("evidence_ids") or []) and x.get("locator")]
        if locs:
            A("  - 定位：%s" % "；".join(locs[:6]))
    A("")
    A("## 7. 冲突证据")
    A("")
    cf = M.get("conflicts") or []
    if not cf:
        A("_未记录冲突；工作稿 `no_conflict_observed=%s`。_（如材料中确有相反结论，须补登并并列双方原文。）"
          % M.get("no_conflict_observed"))
    for x in cf:
        A("### %s %s" % (x.get("conflict_id"), norm(x.get("topic"))[:140]))
        for tag, key in (("A 方", "side_a"), ("B 方", "side_b")):
            s = x.get(key) or {}
            A("- %s **%s** [%s]：%s" % (tag, s.get("source_id"), s.get("locator") or s.get("anchor", {}).get("loc"),
                                        norm(s.get("quote"))[:260]))
            if s.get("position"):
                A("  - 立场：%s" % norm(s["position"])[:200])
        A("- 可能原因：%s（处置：%s）" % (norm(x.get("possible_reason")) or "-", x.get("resolution") or "unresolved"))
        if x.get("impact_on_conclusion"):
            A("- 对结论的影响：%s" % norm(x["impact_on_conclusion"])[:240])
        A("")
    A("## 8. 研究空白（类型化）")
    A("")
    gp = M.get("gaps") or []
    if not gp:
        A("_未记录研究空白。_")
    for g in gp:
        A("- **%s**（%s）%s" % (g.get("gap_id"), g.get("gap_type"), norm(g.get("description"))[:220]))
        A("  - 依据：%s" % norm(g.get("basis"))[:260])
        if g.get("searched_scope"):
            A("  - 已检索范围：%s" % norm(g["searched_scope"])[:200])
        if g.get("would_resolve"):
            A("  - 何种材料可填补：%s" % norm(g["would_resolve"])[:200])
    A("")
    A("## 9. 不确定性与结论边界")
    A("")
    un = M.get("uncertainties") or []
    if not un:
        un = ["材料范围内未记录显式不确定性；未覆盖范围见第 8 节空白。"]
    for u in un:
        A("- %s" % norm(u)[:300])
    und = [c for c in cl if norm(c.get("type")) == "undetermined"]
    if und:
        A("")
        A("**证据不足、明确不作结论的子问题项**：")
        for c in und:
            A("- %s：%s（边界：%s）" % (c.get("claim_id"), norm(c.get("text"))[:200], norm(c.get("boundary"))[:200]))
    bp = M.get("bounded_proposal") or {}
    if isinstance(bp, dict) and (bp.get("constraints") or bp.get("assumptions")):
        A("")
        A("## 9b. 有界提案 / 约束落实")
        A("")
        for k in (bp.get("constraints") or []):
            A("- %s [%s] %s%s" % (k.get("constraint_id"), k.get("status"), norm(k.get("text"))[:160],
                                  "（落实：%s）" % norm(k.get("how"))[:120] if k.get("how") else ""))
        for a in (bp.get("assumptions") or []):
            A("- 假设：%s" % norm(a)[:200])
        for a in (bp.get("excluded_options") or []):
            A("- 已排除方案：%s" % norm(a)[:200])
    A("")
    A("## 10. 复跑与核验")
    A("")
    A("```bash")
    A("python3 -B scripts/main.py init     # 重建 index.json（材料 -> locator 段落）")
    A("python3 -B scripts/main.py show     # 复核来源/记录/契约")
    A("python3 -B scripts/main.py check    # 复核 quote 命中、依赖图、覆盖率")
    A("python3 -B scripts/main.py build    # 重渲染本报告与 result.json")
    A("```")
    A("")
    A("本报告每条结论可回链：`[E#]` → `evidence_matrix.jsonl` 的 `evidence_id` → 该行 `source_id` + `locator`（段落级锚定，`anchor.mode` 标注 exact/loose/window）。")
    A("")
    if M.get("degradations"):
        A("## 11. 降级与缺口（本次运行）")
        A("")
        for d in M["degradations"]:
            A("- %s" % norm(d)[:300])
        A("")
    A("---")
    A("生成器：%s｜状态：%s｜引文通过率：%s" % (GEN, M.get("status"), (M.get("counts") or {}).get("quote_pass_rate")))
    return "\n".join(L) + "\n"
