#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-topic-gatekeeper 渲染层：decision_brief.md / gate_scorecard.json /
prior_art_alignment_matrix.csv / assumption_register.json / evidence_index.jsonl / conflicts.json。
纯标准库；异常由调用方降级，不抛出到 CLI。"""
import csv, io, json, re
from pathlib import Path

import gates as G

norm, al, dicts, strs = G.norm, G.al, G.dicts, G.strs
V = "1.0.0"


def table(head, rows, empty="（无）"):
    rows = [[norm(c).replace("|", "\\|") or "—" for c in r] for r in rows]
    if not rows:
        return empty + "\n"
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def ev_rows(rep, ref):
    out, seen = [], set()
    for e in rep.get("evidence", []):
        if norm(e.get("ref")) != norm(ref):
            continue
        k = (norm(e.get("found_source") or e.get("source_id")), norm(e.get("found_locator") or e.get("locator")),
             norm(e.get("quote")))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def ev_line(e):
    tag = "逐字" if e.get("status") == "verified" else "未命中"
    loc = e.get("found_locator") or e.get("locator") or "?"
    sid = e.get("found_source") or e.get("source_id") or "?"
    mark = "−" if norm(e.get("polarity")) == "contradict" else "+"
    return "  - [%s] %s@%s（%s，%s）：\"%s\"" % (mark, sid, loc, tag, e.get("match") or "-", norm(e.get("quote"))[:160])


def brief(draft, ctx, rep):
    L = []
    dec, q, sp = draft.get("decision") or {}, draft.get("question") or {}, draft.get("search_protocol") or {}
    gp = draft.get("research_gap") or {}
    c = rep.get("counts", {})
    cov = rep.get("coverage", {})
    title = norm(draft.get("proposal_title")) or norm(ctx.get("case_title")) or "研究设想"
    L.append("# 决策简报：%s\n" % title)
    L.append("> v%s ｜ case_id=%s ｜ status=%s ｜ 工作稿来源=%s ｜ 材料 %d 份 ｜ 证据 %d/%d 逐字命中 ｜ %s\n"
             % (V, ctx.get("case_id") or "n/a", ctx.get("status"), ctx.get("draft_source"),
                ctx.get("n_materials", 0), c.get("evidence_verified", 0), c.get("evidence_total", 0), ctx.get("now")))
    L.append("> 本文把研究设想推进到**可决策结论**：五门各自给 go/conditional/no_go 与条件，每条判定附证据回链 [E#]；"
             "凡材料未覆盖处标为假设或无法确定，不代以推断。\n")

    # 0 速览
    L.append("## 0. 一页速览\n")
    gv = {norm(g.get("gate_id")).upper(): norm(g.get("verdict")).lower() for g in dicts(draft.get("gates"))}
    L.append(table(["项目", "结论", "依据"], [
        ["总判定", norm(dec.get("overall")) or "未给出", norm(dec.get("summary"))[:120] or "—"],
        ["G1 值得做", gv.get("G1", "缺") + "（问题可检验性）", "§3.1"],
        ["G2 别人做到哪", gv.get("G2", "缺") + "（最近工作覆盖）", "§3.2"],
        ["G3 做得出来吗", gv.get("G3", "缺") + "（前提三分）", "§3.3"],
        ["G4 不是旧方案吗", gv.get("G4", "缺") + "（创新类型判定）", "§3.4"],
        ["G5 失败会怎样", gv.get("G5", "缺") + "（kill criteria）", "§3.5"],
        ["六类覆盖", "%d/6 通过" % cov.get("six_passed", 0), "§附录 B"],
        ["证据", "%d 条，逐字命中 %d" % (c.get("evidence_total", 0), c.get("evidence_verified", 0)), "§附录 A"],
        ["反证登记", "%d 组" % len(dicts(draft.get("conflicts"))) if draft.get("conflicts")
         else norm(draft.get("no_contrary_found"))[:60] or "未登记", "§7"],
    ]))

    # 1 问题
    L.append("\n## 1. 研究问题：拆成可检验的表述\n")
    L.append((norm(q.get("problem_statement")) or "（未给出问题陈述）") + "\n")
    L.append(table(["维度", "内容"], [
        ["研究对象", norm(q.get("object")) or "未给出"],
        ["关键变量", "；".join(strs(q.get("variables"))) or "未给出"],
        ["比较基线", norm(q.get("baseline")) or "未给出"],
        ["预期结论", norm(q.get("expected")) or "未给出"],
    ]))
    fs = strs(q.get("falsification"))
    L.append("\n**可证伪条件**（出现即否定该设想）\n")
    L.append("\n".join("- F%d %s" % (i, re.sub(r"^F%d[：:.、\s]*" % i, "", f)) for i, f in enumerate(fs, 1))
             + "\n" if fs else "（未给出，见附录 B）\n")
    vr = [x for x in dicts(q.get("vague_replaced"))]
    if vr:
        L.append("\n**模糊措辞 → 可测量替换**\n")
        L.append(table(["原表述", "替换为"], [[norm(v.get("vague")), norm(v.get("measurable"))] for v in vr]))
    ut = strs(q.get("untestable"))
    if ut:
        L.append("\n**明确标为不可检验（不假装能测）**：" + "；".join(ut) + "\n")

    # 2 检索
    L.append("\n## 2. 检索、纳排与对象表（可独立复核）\n")
    L.append(table(["检索式", "时间窗", "纳入标准", "排除标准", "已筛记录"], [
        ["；".join(strs(sp.get("queries"))) or "（未给出检索式）",
         norm(sp.get("windows") or sp.get("date_window")) or "（未给出时间窗）",
         "；".join(strs(sp.get("inclusion"))) or "—", "；".join(strs(sp.get("exclusion"))) or "—",
         str(sp.get("screened") if sp.get("screened") is not None else "—")]]))
    ex = [x for x in dicts(sp.get("excluded"))]
    if ex:
        L.append("\n**纳排明细（被排除的记录与理由）**\n")
        L.append(table(["记录", "理由"], [[norm(x.get("record_id")), norm(x.get("reason"))] for x in ex]))
    L.append("\n**输入对象表（来自 case.json 与材料，脚本机械解析，未改写）**\n")
    L.append(table(["编号", "题名/标识", "别名", "版本/状态标记", "对应材料"], [
        [s.get("sid"), norm(s.get("title"))[:70] or norm(s.get("doi")) or "—",
         "、".join(strs(s.get("aliases")))[:40] or "—", norm(s.get("version_flag")) or "—",
         norm(s.get("material")) or "—"] for s in ctx.get("sources", [])[:24]]))

    # 3 五门
    L.append("\n## 3. 五门判定（每门：结论 + 条件 + 证据回链 + 残余风险 + 改法）\n")
    for i, (gid, name, qs) in enumerate(G.GATES, 1):
        g = next((x for x in dicts(draft.get("gates")) if norm(x.get("gate_id")).upper() == gid), {})
        L.append("\n### 3.%d %s %s\n" % (i, gid, name))
        L.append("**判定：%s**\n" % (norm(g.get("verdict")) or "缺"))
        L.append("问题：%s\n" % (norm(g.get("question")) or qs))
        if norm(g.get("rationale")):
            L.append("理由：%s\n" % norm(g.get("rationale")))
        cs = strs(g.get("conditions"))
        if cs:
            L.append("\n成立条件\n")
            L.append("\n".join("- %s" % x for x in cs) + "\n")
        eids = strs(g.get("evidence_ids"))
        L.append("\n证据回链（evidence_ids=%s）\n" % ("、".join(eids) or "无"))
        rows = []
        for eid in eids:
            for e in ev_rows(rep, eid):
                rows.append(ev_line(e))
        L.append("\n".join(rows) if rows else "  - （无可核验证据，见附录 B 的诊断）\n")
        rs = strs(g.get("residual_risks"))
        if rs:
            L.append("\n残余风险\n")
            L.append("\n".join("- %s" % x for x in rs) + "\n")
        if norm(g.get("pivot_if_no_go")):
            L.append("\n若该门不通过则改为：%s\n" % norm(g.get("pivot_if_no_go")))

    # 4 矩阵
    L.append("\n## 4. 已有工作对齐矩阵（逐条划界，长表见 prior_art_alignment_matrix.csv）\n")
    L.append(table(["设想主张", "最近工作", "任务", "方法", "数据", "评价", "重叠", "可比性", "边界差别", "定位"], [
        [norm(r.get("claim_id")), norm(r.get("source_id")), norm(r.get("task"))[:26], norm(r.get("method"))[:26],
         norm(r.get("data"))[:20], norm(r.get("evaluation"))[:26], norm(r.get("overlap")),
         norm(r.get("comparison_status")) + ("" if norm(r.get("comparison_status")) != "not_comparable"
                                             else "：" + norm(r.get("cannot_compare_reason"))[:40]),
         norm(r.get("boundary_note"))[:70], norm(r.get("locator"))] for r in dicts(draft.get("matrix"))]))

    # 5 创新
    L.append("\n## 5. 创新类型与覆盖判定\n")
    L.append("类型学：method（方法）/ data（数据）/ scenario_transfer（场景迁移）/ conclusion_correction（结论修正）。"
             "**“检索不到”不构成新颖性**：无对照行的只能判 undetermined。\n")
    L.append(table(["主张", "类型", "判定", "覆盖来源", "与最近工作的边界"], [
        [norm(n.get("claim_id")), norm(n.get("type")), norm(n.get("verdict")),
         "、".join(strs(n.get("covered_by"))) or "—", norm(n.get("boundary"))[:90] or "—"]
        for n in dicts(draft.get("novelty"))]))

    # 6 假设
    L.append("\n## 6. 可行性前提登记与 kill criteria（可行性=可执行计划，不是一句“可行”）\n")
    st = cov.get("assumption_states", {})
    L.append("状态三分：source（有来源）/ assumed（假设）/ unsupported（无支撑）。当前：%s\n"
             % "，".join("%s %d" % (k, v) for k, v in sorted(st.items())) if st else "")
    L.append(table(["编号", "前提", "类别", "状态", "来源定位", "kill criteria", "最小验证实验"], [
        [norm(a.get("id")), norm(a.get("statement"))[:70], norm(a.get("category")), norm(a.get("state")),
         norm(a.get("source_locator")) or "—", norm(a.get("kill_criteria"))[:60],
         norm(a.get("validation_experiment"))[:60]] for a in dicts(draft.get("assumptions"))]))

    # 7 冲突
    L.append("\n## 7. 冲突证据与取舍（不隐藏反证）\n")
    conf = dicts(draft.get("conflicts"))
    if conf:
        for i, c2 in enumerate(conf, 1):
            L.append("\n**C-%d %s**\n" % (i, norm(c2.get("topic")) or "未命名冲突"))
            for side, lab in (("support", "支持"), ("contradict", "相反")):
                for e in dicts(c2.get(side)):
                    L.append("- [%s] %s@%s：\"%s\"" % (lab, norm(e.get("source_id")),
                                                       norm(e.get("locator")) or "?", norm(e.get("quote"))[:150]))
            L.append("\n取舍：%s ｜ 对判定的影响：%s\n" % (norm(c2.get("resolution")) or "未写取舍理由",
                                                    norm(c2.get("impact_on_decision")) or "未写"))
    else:
        L.append((norm(draft.get("no_contrary_found")) or "未登记任何相反结论，也未说明检索范围——视为缺口。") + "\n")

    # 8 空白
    L.append("\n## 8. 研究空白（限定范围，不做全局断言）\n")
    L.append((norm(gp.get("statement")) or "（未给出）") + "\n")
    L.append("\n- 作用范围：%s\n- 是否宣称全局首创：%s\n" % (norm(gp.get("scope")) or "未限定",
                                                     "是（不合规）" if gp.get("global_claim") in (True, "true", 1) else "否"))
    for e in dicts(gp.get("basis")):
        L.append("- 依据 %s@%s：\"%s\"" % (norm(e.get("source_id")), norm(e.get("locator")) or "?", norm(e.get("quote"))[:140]))

    # 9 结论
    L.append("\n## 9. 结论与下一步最小验证\n")
    L.append("**总判定：%s**\n\n%s\n" % (norm(dec.get("overall")) or "未给出", norm(dec.get("summary")) or "（未给出）"))
    cs = strs(dec.get("conditions"))
    if cs:
        L.append("\n结论成立的条件\n")
        L.append("\n".join("- %s" % x for x in cs) + "\n")
    nv = dicts(dec.get("next_validation"))
    L.append("\n**下一步最小验证（把 conditional 变 go 的最短路径）**\n")
    L.append(table(["门", "动作", "需要拿到什么证据"], [
        [norm(x.get("gate")) or "—", norm(x.get("step")), norm(x.get("evidence_needed"))] for x in nv]))

    # 附录
    L.append("\n## 附录 A：证据索引（逐条定位；未命中者不可作证据）\n")
    L.append(table(["引用", "来源", "定位", "匹配", "极性", "原文"], [
        [norm(e.get("ref")) or "—", norm(e.get("found_source") or e.get("source_id")),
         norm(e.get("found_locator") or e.get("locator")) or "?", norm(e.get("match")) or e.get("status"),
         norm(e.get("polarity")) or "support", norm(e.get("quote"))[:110]] for e in rep.get("evidence", [])]))
    L.append("\n## 附录 B：覆盖与自检\n")
    six = cov.get("six_checks", {})
    L.append(table(["六类要点", "是否覆盖"], [
        ["问题拆解（problem_decomposition）", "是" if six.get("problem_decomposition") else "否"],
        ["检索覆盖（search_coverage）", "是" if six.get("search_coverage") else "否"],
        ["证据回链（evidence_backlink）", "是" if six.get("evidence_backlink") else "否"],
        ["冲突证据（conflict_evidence）", "是" if six.get("conflict_evidence") else "否"],
        ["综合结论（synthesis）", "是" if six.get("synthesis") else "否"],
        ["研究空白（research_gap）", "是" if six.get("research_gap") else "否"]]))
    diag = [["ERROR " + e["code"], e["msg"]] for e in rep.get("errors", [])] + \
           [["WARN " + w["code"], w["msg"]] for w in rep.get("warnings", [])]
    L.append("\n**诊断**\n")
    L.append(table(["级别", "说明"], diag))
    L.append("\n## 附录 C：变更记录与不确定性\n")
    L.append(table(["动作", "对象", "原因", "前", "后"], [
        [norm(x.get("action")), norm(x.get("target")), norm(x.get("reason"))[:80],
         norm(x.get("before"))[:30], norm(x.get("after"))[:40]] for x in dicts(draft.get("change_log"))]))
    unc = ctx.get("uncertainties", [])
    L.append("\n".join("- %s：%s → %s" % (norm(u.get("item")), norm(u.get("why")), norm(u.get("effect")))
                      for u in unc) if unc else "\n- （无）")
    return "\n".join(L).rstrip() + "\n"


def scorecard(draft, ctx, rep):
    gates = []
    for gid, name, qs in G.GATES:
        g = next((x for x in dicts(draft.get("gates")) if norm(x.get("gate_id")).upper() == gid), {})
        eids = strs(g.get("evidence_ids"))
        gates.append({
            "gate_id": gid, "name": name, "question": norm(g.get("question")) or qs,
            "verdict": norm(g.get("verdict")).lower() or None,
            "conditions": strs(g.get("conditions")),
            "evidence_ids": eids,
            "evidence_verified": sum(1 for eid in eids for e in ev_rows(rep, eid) if e.get("status") == "verified"),
            "residual_risks": strs(g.get("residual_risks")),
            "pivot_if_no_go": norm(g.get("pivot_if_no_go")) or None,
            "rationale": norm(g.get("rationale")) or None})
    dec = draft.get("decision") or {}
    return {"case_id": ctx.get("case_id"), "skill_version": V, "generated_at": ctx.get("now"),
            "overall": norm(dec.get("overall")).lower() or None,
            "summary": norm(dec.get("summary")),
            "conditions": strs(dec.get("conditions")),
            "next_validation": dicts(dec.get("next_validation")),
            "gates": gates,
            "verdict_counts": {v: sum(1 for g in gates if g["verdict"] == v) for v in ("go", "conditional", "no_go")},
            "coverage": rep.get("coverage", {}),
            "counts": rep.get("counts", {}),
            "status": ctx.get("status"), "draft_source": ctx.get("draft_source")}


CSV_HEAD = ["proposal_claim_id", "source_id", "task", "method", "data", "evaluation", "overlap",
            "comparison_status", "cannot_compare_reason", "boundary_note", "evidence_locator"]


def matrix_csv(draft):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_HEAD)
    for r in dicts(draft.get("matrix")):
        w.writerow([norm(r.get("claim_id")), norm(r.get("source_id")), norm(r.get("task")), norm(r.get("method")),
                    norm(r.get("data")), norm(r.get("evaluation")), norm(r.get("overlap")).lower(),
                    norm(r.get("comparison_status")).lower(), norm(r.get("cannot_compare_reason")),
                    norm(r.get("boundary_note")), norm(r.get("locator"))])
    return buf.getvalue()


def assumption_register(draft, ctx, rep):
    rows = []
    for a in dicts(draft.get("assumptions")):
        aid = norm(a.get("id"))
        evs = [{"source_id": e.get("found_source") or e.get("source_id"),
                "locator": e.get("found_locator") or e.get("locator"), "quote": e.get("quote"),
                "status": e.get("status")} for e in rep.get("evidence", []) if norm(e.get("ref")) == aid]
        rows.append({"id": aid, "statement": norm(a.get("statement")), "category": norm(a.get("category")).lower(),
                     "state": norm(a.get("state")).lower(), "source_locator": norm(a.get("source_locator")),
                     "evidence": evs, "kill_criteria": norm(a.get("kill_criteria")),
                     "validation_experiment": norm(a.get("validation_experiment")),
                     "owner_gate": "G3"})
    return {"case_id": ctx.get("case_id"), "skill_version": V, "generated_at": ctx.get("now"),
            "state_legend": {"source": "材料中有逐字来源", "assumed": "合理假设，需实验确认",
                             "unsupported": "无支撑，缺它则该门不可能 go"},
            "counts": {s: sum(1 for r in rows if r["state"] == s) for s in G.ASTATE},
            "assumptions": rows}


def evidence_jsonl(rep):
    out = []
    for e in rep.get("evidence", []):
        out.append(json.dumps({"ref": norm(e.get("ref")), "source_id": norm(e.get("found_source") or e.get("source_id")),
                               "locator": norm(e.get("found_locator") or e.get("locator")),
                               "quote": e.get("quote"), "polarity": norm(e.get("polarity")) or "support",
                               "match": e.get("match"), "status": e.get("status")}, ensure_ascii=False))
    return "\n".join(out) + ("\n" if out else "")


def conflicts_json(draft, ctx, rep):
    return {"case_id": ctx.get("case_id"), "skill_version": V,
            "no_contrary_found": norm(draft.get("no_contrary_found")) or None,
            "contradicting_evidence": [{"ref": e.get("ref"), "source_id": e.get("found_source") or e.get("source_id"),
                                        "locator": e.get("found_locator") or e.get("locator"), "quote": e.get("quote")}
                                       for e in rep.get("evidence", []) if norm(e.get("polarity")) == "contradict"],
            "conflicts": dicts(draft.get("conflicts"))}


def write_all(outdir, draft, ctx, rep):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    md = brief(draft, ctx, rep)
    (out / "decision_brief.md").write_text(md, encoding="utf-8")
    files["decision_brief.md"] = len(md.encode("utf-8"))
    G.dump_json(out / "gate_scorecard.json", scorecard(draft, ctx, rep))
    files["gate_scorecard.json"] = (out / "gate_scorecard.json").stat().st_size
    with open(str(out / "prior_art_alignment_matrix.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write(matrix_csv(draft))
    files["prior_art_alignment_matrix.csv"] = (out / "prior_art_alignment_matrix.csv").stat().st_size
    G.dump_json(out / "assumption_register.json", assumption_register(draft, ctx, rep))
    files["assumption_register.json"] = (out / "assumption_register.json").stat().st_size
    (out / "evidence_index.jsonl").write_text(evidence_jsonl(rep), encoding="utf-8")
    files["evidence_index.jsonl"] = (out / "evidence_index.jsonl").stat().st_size
    G.dump_json(out / "conflicts.json", conflicts_json(draft, ctx, rep))
    files["conflicts.json"] = (out / "conflicts.json").stat().st_size
    return files


def pack(draft, rep, ix, case_id, status, src, files):
    """把工作稿 + 校验结果装成 result.json 的业务字段（契约回填由 main.fill_contract 负责）。"""
    dec = draft.get("decision") or {}
    return {
        "case_id": case_id, "status": status,
        "note": "build：%s ｜ 五门 %d/5 ｜ 矩阵 %d 行 ｜ 证据 %d/%d 逐字命中" % (
            src, rep["counts"]["gates_present"], rep["counts"]["matrix_rows"],
            rep["counts"]["evidence_verified"], rep["counts"]["evidence_total"]),
        "decision": {"overall": norm(dec.get("overall")).lower() or None, "summary": norm(dec.get("summary")),
                     "conditions": strs(dec.get("conditions")), "next_validation": dicts(dec.get("next_validation"))},
        "decision_summary": norm(dec.get("summary")),
        "gates": [{"gate_id": g.get("gate_id"), "name": g.get("name"), "verdict": norm(g.get("verdict")).lower(),
                   "conditions": strs(g.get("conditions")), "evidence_ids": strs(g.get("evidence_ids")),
                   "residual_risks": strs(g.get("residual_risks")), "pivot_if_no_go": g.get("pivot_if_no_go")}
                  for g in dicts(draft.get("gates"))],
        "prior_art_rows": dicts(draft.get("matrix")),
        "novelty": dicts(draft.get("novelty")),
        "assumptions": dicts(draft.get("assumptions")),
        "claims": dicts(draft.get("claims")),
        "conflicts": dicts(draft.get("conflicts")),
        "research_gap": draft.get("research_gap") or None,
        "search_protocol": draft.get("search_protocol") or None,
        "question": draft.get("question") or None,
        "evidence": [{"ref": e.get("ref"), "source_id": e.get("found_source") or e.get("source_id"),
                      "locator": e.get("found_locator") or e.get("locator"), "quote": e.get("quote"),
                      "polarity": e.get("polarity"), "match": e.get("match"), "status": e.get("status")}
                     for e in rep.get("evidence", [])],
        "coverage": dict(rep.get("coverage", {}), objects=ix.get("counts", {})),
        "sources": [{"id": s["sid"], "title": s["title"], "doi": s["doi"], "aliases": s["aliases"],
                     "version_flag": s["version_flag"], "material": s["material"], "origin": s["origin"]}
                    for s in ix.get("objects", {}).get("sources", [])],
        "change_log": dicts(draft.get("change_log")) or
                      [{"action": "生成", "target": "decision_brief.md", "reason": src, "before": "—", "after": "v1"}],
        "deliverable": {"path": "decision_brief.md", "format": "markdown", "editable": True,
                        "chars": files.get("decision_brief.md", 0), "companions": sorted(files),
                        "draft_source": src},
        "artifacts": files,
    }
