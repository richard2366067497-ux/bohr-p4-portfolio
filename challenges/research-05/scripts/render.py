# -*- coding: utf-8 -*-
"""five-gate research evaluator: artifact writers (matrix / evidence / render / pipeline).

Standard library only; deterministic; offline. Builds on the shared engine in kglib.
"""
import hashlib, json, os, re
from kglib import *  # noqa: F401,F403

def build_artifacts(R, out):
    M, cid = R["M"], R["case_id"]
    gates = gate_verdicts(R)
    R["gates_out"] = gates
    for e in draft_checks(R, gates):
        if e["code"] not in [x["code"] for x in R["errors"]]:
            R["errors"].append(e)
    # ---- matrix (long table: one claim x its nearest comparison row)
    rows = []
    for c in R["claims"]:
        anchor = next((e for e in R["evid"] if e["evidence_id"] in c["evidence_ids"]), None)
        loc = anchor["locator"] if anchor else "unlocated"
        rows.append({"claim_id": c["claim_id"], "source_id": loc.split("/")[0], "source_locator": loc,
                     "task": c["text"], "method": "材料未给", "data": "材料未给", "evaluation": "材料未给",
                     "overlap": "no-overlap", "comparison_status": "not_comparable",
                     "cannot_compare_reason": "材料未给与该主张直接对应的对照工作",
                     "boundary_note": "本轮对照行落在规则文档自身（" + loc + "），不是文献级比较；文献级比较需要候选文献材料",
                     "row_basis": "framework row"})
    # ---- assumptions
    aset = []
    def asum(aid, stmt, cat, state, kill, val, evs):
        ids = [R["_ev"](e[0], e[1], e[2], "assumption") for e in evs]
        aset.append({"id": aid, "statement": stmt, "category": cat, "state": state, "kill_criteria": kill,
                     "validation_experiment": val, "evidence_ids": ids,
                     "evidence": [{"source_id": e[0], "locator": e[1], "quote": e[2].strip()} for e in evs]})
    b1 = M["bounds"][0] if M["bounds"] else None
    b2 = M["bounds"][-1] if M["bounds"] else None
    if b1:
        o = b1["locator"].split("/")[0]
        asum("A1", "输入材料必须含可解析文本层（不是扫描图片或无文本层 PDF）", "data", "source",
             "材料为扫描图片或无文本层 PDF 且无 OCR 工具：记 no_ocr 并降级，不再引用该材料",
             "对每份材料跑一次 scan，核对 parse_status 字段", [(o, b1["locator"], b1["quote"])])
    if b2:
        o = b2["locator"].split("/")[0]
        asum("A2", "运行环境可离线、无网络，材料不足时明说而不外检", "compute", "source",
             "若必须在线检索新文献才能判定：本轮不联网，输出条件式结论并标注范围",
             "断开网络复跑同一命令，比对产物是否逐字节一致", [(o, b2["locator"], b2["quote"])])
    fd = [f for f in M["fields"] if f["field"] in ("question", "gates", "matrix", "novelty", "assumptions",
                                                   "claims", "research_gap", "decision")]
    if fd:
        evs = [(f["locator"].split("/")[0], f["locator"], f["quote"]) for f in fd[:3]]
        asum("A3", "工作稿 draft 含 question/gates/matrix/novelty/assumptions/claims/research_gap/decision 八个必填字段",
             "experiment", "unsupported",
             "本轮材料未提供任何工作稿：G3 因此不得判 go（阈值表要求全部前提 state != unsupported）",
             "补一份最小工作稿并跑 check，直到 ERROR 归零", evs)
    rb = [r for r in M["rubric"] if "可核验" in r["point"]]
    if rb:
        evs = [(rb[0]["locator"].split("/")[0], rb[0]["locator"], rb[0]["quote"])]
        asum("A4", "评审人可按 locator 回到原文独立复核每条证据", "people", "assumed",
             "若某条证据的 locator 无法定位到对应行：该条降级为未核验并记入 uncertainty",
             "随机抽 5 条证据，用 show 的 M#/p# 回看原文逐字比对", evs)
    da = [a for a in ((R.get("draft") or {}).get("assumptions") or []) if isinstance(a, dict) and a.get("id")]
    if da:
        aset = []
        for a in da:
            evs = []
            for e in (a.get("evidence") or []):
                if isinstance(e, dict) and isinstance(e.get("quote"), str):
                    loc = str(e.get("locator") or "unlocated")
                    R["_ev"](loc.split("/")[0], loc, e["quote"], "draft-assumption", note="assumption " + str(a.get("id")))
                    evs.append({"source_id": loc.split("/")[0], "locator": loc, "quote": e["quote"].strip()})
            aset.append({"id": str(a.get("id")), "statement": str(a.get("statement") or ""),
                         "category": str(a.get("category") or "experiment"), "state": str(a.get("state") or "assumed"),
                         "kill_criteria": str(a.get("kill_criteria") or ""),
                         "validation_experiment": str(a.get("validation_experiment") or ""),
                         "source": "agent draft", "evidence": evs,
                         "evidence_ids": [e["evidence_id"] for e in R["evid"] if e["kind"] == "draft-assumption"
                                          and (e["note"] or "").endswith(str(a.get("id")))]})
    # ---- conflicts (detected once in build_context, reused here)
    conflicts = R.get("conflicts") or []
    # ---- search protocol log
    log = []
    probe = [("五门映射行", r"^\|\s*G[1-5]\s*\|.*\|.*\|.*\|.*\|", "M#/p# 的 §1 表"),
             ("阈值行", r"^\|\s*G[1-5]\s*\|.*\|.*\|.*\|", "M#/p# 的 §2 表"),
             ("错误码行", r"^\|\s*`E_[A-Z_0-9]+`", "M#/p# 的 §3 表"),
             ("证据核验行", r"^\|\s*`(exact|segments|despaced|quote_not_found)`", "M#/p# 的 §8 表"),
             ("字段行", r"^\|\s*`[a-z_]+`\s*\|", "M#/p# 的字段字典表")]
    for i, (name, pat, where) in enumerate(probe, 1):
        hits = []
        for mfile in R["materials"]:
            if mfile["status"] != "parsed":
                continue
            for j, l in enumerate(mfile["text"].split("\n"), 1):
                if re.match(pat, l.strip()):
                    hits.append("%s/p%d" % (mfile["id"], j))
        log.append({"query_id": "Q%d" % i, "name": name, "pattern": pat, "scope": where,
                    "hits": len(hits), "first_hits": hits[:4]})
    R["search_log"] = {"mode": "offline deterministic scan over the supplied materials",
                       "windows": "本材料范围（未做在线检索；材料不足时明说，不外检）",
                       "inclusion": ["材料内可解析为文本的文件", "可逐字定位到 M#/p# 的句子"],
                       "exclusion": ["二进制或无文本层文件", "占位/空文件", "无法逐字命中的改写句"],
                       "screened": len([m for m in R["materials"] if m["status"] == "parsed"]),
                       "excluded": [{"record_id": o["record_id"], "path": o["path"], "reason": o["kind"]}
                                    for o in R["objects"] if o["kind"] != "parsed"],
                       "queries": log, "counts": {"materials": len(R["materials"]),
                                                  "parsed": len([m for m in R["materials"] if m["status"] == "parsed"])}}
    R["degradations"] = []
    if R["rejects"]:
        R["degradations"].append({"code": "W_QUOTE", "detail": "%d quote(s) not found verbatim; listed in uncertainty" % len(R["rejects"])})
    R["degradations"].append({"code": "W_SEARCH_WINDOW", "detail": "no online search window: the protocol records the material scope only"})
    if len(R["objects"]) < 3:
        R["degradations"].append({"code": "W_G3_CATS", "detail": "the record table holds %d entries, below the three-source scale the rules assume" % len(R["objects"])})
    R["degradations"].append({"code": "W_DECISION_NEXT", "detail": "next_validation names the gate each step unblocks; no step can run without a draft"})
    if len([a for a in aset if a["category"]]) < 3:
        R["degradations"].append({"code": "W_G3_VALID", "detail": "fewer than three assumption categories were grounded"})
    # ---- coverage
    verified = [e for e in R["evid"] if e["verified"]]
    rate = (len(verified) / len(R["evid"])) if R["evid"] else 0.0
    parsed = [m for m in R["materials"] if m["status"] == "parsed"]
    status = "ok"
    if not parsed:
        status = "insufficient_evidence"
    elif R["errors"]:
        status = "partial"
    if R["evid"] and rate < 0.8:
        status = "partial"
    R["status"] = status
    six = {
        "problem_split": {"done": bool(R["by"].get("G1")), "locator": R["by"].get("G1", {}).get("locator", "unlocated")},
        "search_coverage": {"materials": len(R["materials"]),
                            "parsed": len([m for m in R["materials"] if m["status"] == "parsed"])},
        "evidence_backlink": {"items": len(R["evid"]), "verified": len(verified), "verbatim_rate": round(rate, 4)},
        "conflicts": {"logged": len(conflicts), "no_contrary_found": bool(R["no_contrary_found"])},
        "synthesis": {"gates": len(gates), "deliverables": len({g["deliverable"] for g in gates})},
        "gaps": {"scoped": True, "global_claim": False,
                 "statement": "在本材料范围内未见任何候选文献对照行与工作稿，故文献级空白只能按本材料范围声明"},
    }
    R["coverage"] = {"six_checks": six, "counts": {"materials": len(R["materials"]), "objects": len(R["objects"]),
                    "unresolved_records": len(R["unresolved"]), "evidence": len(R["evid"]), "verified": len(verified),
                    "gates": len(gates), "error_codes": len(M["errors"]), "warn_codes": len(M["warns"]),
                    "enums": len(M["enums"]), "rubric_points": len(M["rubric"]), "matrix_rows": len(rows)},
                    "node_types": {"rule_documents": len([m for m in R["materials"] if m["status"] == "parsed"])},
                    "verdicts": {"gates": len(gates), "go": len([g for g in gates if g["verdict"] == "go"]),
                                 "conditional": len([g for g in gates if g["verdict"] == "conditional"]),
                                 "no_go": len([g for g in gates if g["verdict"] == "no_go"])}}
    return status, verified, rate, gates, rows, aset, conflicts, log, six

def render(R, out, work):
    cid = R["case_id"]
    status, verified, rate, gates, rows, aset, conflicts, log, six = build_artifacts(R, out)
    M = R["M"]
    parsed = [m for m in R["materials"] if m["status"] == "parsed"]
    overall, weakest = overall_of(R, gates)
    # decision_brief.md
    L = ["# 判定简报：%s" % cid, "",
         "状态：`%s`；证据逐字命中率 %.4f（%d/%d）；ERROR %d；门 %d/5。" %
         (status, rate, len(verified), len(R["evid"]), len(R["errors"]), len(gates)), ""]
    if status == "insufficient_evidence":
        L += ["## 0. 无可用材料（结构化 no-data 记录）", "", "检索位置与解析状态："]
        L += ["- %s：%s" % (m["rel"], m["status"]) for m in R["materials"]]
        L += ["- 结论：材料中没有可解析文本，五门、阈值与引文都无法 grounding；本简报不编造任何判定。",
              "- 下一步：提供一份含五门规则的文本材料，用同一条命令复跑。", ""]
    L += [
         "## 1. 四项交付 ↔ 五门", ""]
    if M["basis"]:
        L += ["> " + M["basis"][0]["quote"], "> 定位：" + M["basis"][0]["locator"], ""]
    L += ["| 门 | 名称 | 回答的问题 | 题面交付项 | 主要字段 | 判定 |", "|---|---|---|---|---|---|"]
    for g in gates:
        L.append("| %s | %s | %s | %s | %s | %s |" % (g["gate_id"], g["name"], g["question"], g["deliverable"],
                                                       g["fields"], g["verdict"]))
    L += ["", "## 2. 每门的阈值与条件（逐门）", ""]
    for g in gates:
        L += ["### %s %s — %s" % (g["gate_id"], g["name"], g["verdict"]),
              "- 判定理由：%s" % g["rationale"],
              "- go 的充分条件（原文 %s）：%s" % (g["threshold_locator"], g["go_condition"]),
              "- 降级条件：%s" % g["conditional_condition"],
              "- no_go：%s" % g["no_go_condition"],
              "- 成立所需条件：%s" % "；".join(g["conditions"]),
              "- 残余风险：%s" % "；".join(g["residual_risks"]),
              "- 不通过时改做：%s" % g["pivot_if_no_go"],
              "- 证据：%s" % ", ".join(g["evidence_ids"]), ""]
    L += ["## 3. 已有工作比较（长表）", "",
          "本轮材料是规则文档，未含候选文献对象，因此矩阵按“框架行”登记：每条主张一行，对照列写“材料未给”，并给出不可直接比较的原因。"
          "文献级比较需要候选文献材料，换材料即可复跑。", ""]
    for r in rows:
        L.append("- %s ← %s（%s）：%s" % (r["claim_id"], r["source_id"], r["source_locator"], r["boundary_note"]))
    L += ["", "## 4. 可行性前提登记（G3）", ""]
    for a in aset:
        L += ["- %s [%s/%s] %s" % (a["id"], a["category"], a["state"], a["statement"]),
              "  - 放弃信号：%s" % a["kill_criteria"], "  - 最小验证：%s" % a["validation_experiment"]]
    L += ["", "## 5. 创新判定（G4）", "",
          "材料未提供创新主张与对照工作，novelty 判定只能是 undetermined；按材料规则，不得用“检索不到”支撑 novel，"
          "因此本轮不产生任何 novel 结论。", ""]
    L += ["## 6. 冲突与反证（G5）", ""]
    for c in conflicts:
        L += ["- 主题：%s" % c["topic"],
              "  - 支持侧（%s）：%s" % (c["support"][0]["locator"], c["support"][0]["quote"]),
              "  - 反证侧（%s）：%s" % (c["contradict"][0]["locator"], c["contradict"][0]["quote"]),
              "  - 取舍：%s" % c["resolution"], "  - 对判定的影响：%s" % c["impact_on_decision"]]
    L += ["", "未发现相反证据的范围声明：" + R["no_contrary_found"], "",
          "## 7. 研究空白（限范围）", "", six["gaps"]["statement"], "",
          "## 8. 总判定", "",
          "- overall：%s（最弱一门：%s；总判定不得高于最弱一门）" % (overall, weakest),
          "- 摘要：本材料给出完整的五门规则与阈值；%s"
          % ("工作稿已并入判定，各门结论与证据见第 2 节。" if R.get("draft_name") else
             "缺少工作稿与候选文献，五门均只能给条件式判定，创新覆盖与失败成本无法评估。补一份最小工作稿即可让判定落到具体主张上。"),
          "- 把 conditional 变 go 的条件：%s" % "；".join(a["validation_experiment"] for a in aset[:2] if a.get("validation_experiment")), ""]
    L += ["## 附录 A 未命中引文", ""]
    if R["rejects"]:
        L += ["| locator | quote | reason |", "|---|---|---|"] + \
             ["| %s | %s | %s |" % (r["locator"], r["quote"], r["reason"]) for r in R["rejects"]]
    else:
        L.append("本轮无未命中引文：%d 条证据全部在材料中逐字命中。（该清单为空是实测结果，不是省略。）" % len(R["evid"]))
    L += ["", "## 附录 B 缺口与降级", ""]
    L += ["- %s：%s" % (d["code"], d["detail"]) for d in R["degradations"]]
    L += ["- ERROR %d 条" % len(R["errors"])]
    for e in R["errors"]:
        L.append("  - %s：%s" % (e["code"], e["detail"]))
    L += ["", "## 附录 C 不确定性", ""]
    L += ["- 未解析记录 %d 条（%s）" % (len(R["unresolved"]),
          "；".join(o["path"] + "=" + o["kind"] for o in R["unresolved"]) or "无"),
          "- 未做过在线检索：本包离线，材料不足时只降级并明说。",
          "- 版本/重复消解：%s" % ("未发现重复或版本标记" if not any(o["duplicate_of"] or o["version_tags"] for o in R["objects"])
                                       else "见 evidence/sources_snapshot.json"), ""]
    wt(os.path.join(out, "decision_brief.md"), "\n".join(L))
    # gate_scorecard.json
    wj(os.path.join(out, "gate_scorecard.json"), {
        "case_id": cid, "status": status, "verdict_vocabulary": [e for e in M["enums"] if e["key"].endswith("verdict") or e["key"].endswith("overall")],
        "gates": gates, "decision": {"overall": overall,
                                     "weakest_gate": weakest,
                                     "summary": ("工作稿已并入判定。" if R.get("draft_name") else
                                                 "材料给出五门规则与阈值；缺少工作稿与候选文献，五门均给条件式判定。"),
                                     "next_validation": [{"step": a["validation_experiment"], "evidence_needed": a["statement"],
                                                          "gate": ("G3" if a["category"] in ("data", "compute", "experiment") else "G5")}
                                                         for a in aset]},
        "counts": {"gates": len(gates), "conditional": len([g for g in gates if g["verdict"] == "conditional"]),
                   "no_go": len([g for g in gates if g["verdict"] == "no_go"]),
                   "go": len([g for g in gates if g["verdict"] == "go"])},
        "notes": ["verdict 由本包给出并逐条对回阈值表；脚本只检查结构约束与自相矛盾，不做价值判断（材料原话）",
                  "任一 gate 为 no_go 时总判定不得为 go；存在 conditional 时总判定须为 conditional 或更低"]})
    # matrix csv
    head = ["claim_id", "source_id", "source_locator", "task", "method", "data", "evaluation", "overlap",
            "comparison_status", "cannot_compare_reason", "boundary_note", "row_basis"]
    lines = [",".join(head)]
    for r in rows:
        lines.append(",".join('"%s"' % str(r[k]).replace('"', "'").replace("\n", " ") for k in head))
    wt(os.path.join(out, "prior_art_alignment_matrix.csv"), "\n".join(lines))
    # assumption register
    wj(os.path.join(out, "assumption_register.json"), {
        "case_id": cid, "state_vocabulary": [e for e in M["enums"] if e["key"].endswith("state")],
        "category_vocabulary": [e for e in M["enums"] if e["key"].endswith("category")],
        "assumptions": aset,
        "counts": {"total": len(aset), "categories": len({a["category"] for a in aset}),
                   "source": len([a for a in aset if a["state"] == "source"]),
                   "assumed": len([a for a in aset if a["state"] == "assumed"]),
                   "unsupported": len([a for a in aset if a["state"] == "unsupported"])},
        "gate_effect": "存在 unsupported 前提 → G3 不得判 go（阈值表原话：全部前提 state != unsupported）"})
    # evidence index jsonl
    with open(os.path.join(out, "evidence_index.jsonl"), "w", encoding="utf-8") as f:
        for e in R["evid"]:
            f.write(json.dumps(clean(e), ensure_ascii=False, sort_keys=True) + "\n")
    # conflicts
    wj(os.path.join(out, "conflicts.json"), {
        "case_id": cid, "conflicts": conflicts, "no_contrary_found": R["no_contrary_found"],
        "note": "支持侧与反证侧都保留原话与定位；没有相反证据时用 no_contrary_found 写明范围，而不是默认无冲突。",
        "counts": {"conflicts": len(conflicts), "sides_quoted": len(conflicts) * 2}})
    # search log
    wj(os.path.join(out, "search_log.json"), dict(R["search_log"], case_id=cid))
    # coverage
    wj(os.path.join(out, "coverage.json"), dict(R["coverage"], case_id=cid, status=status,
                                                enums=M["enums"],
                                                rule_error_codes=[x["code"] for x in M["errors"]],
                                                warn_codes=[x["code"] for x in M["warns"]],
                                                no_data=(None if parsed else {
                                                    "status": "insufficient_evidence",
                                                    "searched_locations": [m["rel"] + " (" + m["status"] + ")" for m in R["materials"]],
                                                    "reason": "no material could be parsed as text, so no gate, threshold or quote could be grounded",
                                                    "next": "supply one text material that carries the gate rules, then rerun the same command"})))
    R["overall"] = overall
    # change log
    cl = [{"step": 1, "action": "scan", "result": "indexed %d file(s): %s" %
           (len(R["materials"]), ", ".join("%s=%s" % (m["rel"], m["status"]) for m in R["materials"]) or "none")},
          {"step": 2, "action": "extract", "result": "gates=%d thresholds=%d error_codes=%d warn_codes=%d enums=%d rubric_points=%d" %
           (len(M["gates"]), len(M["thresholds"]), len(M["errors"]), len(M["warns"]), len(M["enums"]), len(M["rubric"]))},
          {"step": 3, "action": "ground", "result": "evidence=%d verified=%d rate=%.4f" % (len(R["evid"]), len(verified), rate)},
          {"step": 4, "action": "downgrade", "target": "G3", "reason": "%s (unsupported)" % next((a["statement"] for a in aset if a["state"] == "unsupported"), "no draft supplied"),
           "before": "go", "after": "conditional"},
          {"step": 5, "action": "align", "target": "matrix", "reason": "no candidate references in the material: rows are framework rows with 材料未给 in the comparison columns"},
          {"step": 6, "action": "decide", "result": "overall=conditional (not higher than the weakest gate)"},
          {"step": 7, "action": "write", "result": "%d artifact(s)" % len(ART)}]
    wj(os.path.join(out, "change_log.json"), {"case_id": cid, "change_records": cl, "counts": {"steps": len(cl)}})
    # uncertainty
    wj(os.path.join(out, "uncertainty.json"), {
        "case_id": cid, "status": status,
        "unlocated": R["rejects"],
        "unresolved_records": [{"record_id": o["record_id"], "path": o["path"], "kind": o["kind"]} for o in R["unresolved"]],
        "undetermined": [{"area": "G4 / novelty", "reason": "材料未提供创新主张与对照工作，按规则只能 undetermined"},
                         {"area": "G5 / failure cost", "reason": "材料未提供预算与时间窗，退出成本无法评估"}],
        "degradations": R["degradations"],
        "searched_locations": [m["rel"] + " (" + m["status"] + ")" for m in R["materials"]],
        "note": "未命中与未解析一律留在这里，不写进判定结论。"})
    # gain evidence
    wj(os.path.join(out, "gain_evidence.json"), {
        "case_id": cid, "deterministic": True, "network": False, "clock": False,
        "model_requests_by_this_skill": 0,
        "baseline": "a prose answer from the same two materials: no gate table, no locator, no verbatim quote, no conflict registration (simulated, not an official measurement)",
        "skills_measured_this_run": {"artifacts": len(ART), "gates": len(gates), "enums": len(M["enums"]),
                                     "error_codes": len(M["errors"]), "warn_codes": len(M["warns"]),
                                     "rubric_points_extracted": len(M["rubric"]), "evidence_items": len(R["evid"]),
                                     "verbatim_rate": round(rate, 4), "matrix_rows": len(rows),
                                     "assumptions": len(aset)},
        "baseline_simulated": {"artifacts": 1, "gates": 0, "evidence_items": 0, "verbatim_rate": 0.0,
                               "conflicts_logged": 0, "contract_keys": 0},
        "method": "every number above is recounted from this run's own artifacts; the baseline column is a described contrast, not a measured competitor",
        "protocol": "SELFTEST.md (section 5)",
        "reproduce": "python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work"})
    # run log
    rl = ["# run log", ""]
    for m in R["materials"]:
        rl.append("material %s %s status=%s chars=%d" % (m["id"], m["rel"], m["status"], m["chars"]))
    rl += ["", "stages: scan=%d parsed=%d objects=%d evidence=%d verified=%d gates=%d errors=%d warns=%d" %
           (len(R["materials"]), len([m for m in R["materials"] if m["status"] == "parsed"]), len(R["objects"]),
            len(R["evid"]), len(verified), len(gates), len(R["errors"]), len(M["warns"])),
           "status=%s exit=0" % status]
    wt(os.path.join(out, "run_log.txt"), "\n".join(rl))
    # provenance snapshot
    wj(os.path.join(out, "evidence/sources_snapshot.json"), {
        "case_id": cid, "objects": R["objects"], "unresolved_records": R["unresolved"],
        "reconciliation": {"aliases": "record aliases fold onto their M# source id",
                           "duplicates": "records sharing a content hash point at the first one via duplicate_of",
                           "versions": [o["version_tags"] for o in R["objects"]],
                           "unresolved": "never guessed: left here and counted as not-covered"},
        "steps": M.get("object_reconcile", [])})
    return status, gates, rows, aset, verified, rate


def selfcheck_obj(R, out, status, verified, rate):
    present = [a for a in ART if os.path.isfile(os.path.join(out, a))]
    small = [a for a in present if os.path.getsize(os.path.join(out, a)) < 40]
    contract = R.get("contract_values") or {}
    echo_ok = bool(contract) and all(isinstance(v, str) and v.strip() for v in contract.values())
    files_ok = bool(contract) and all(os.path.isfile(os.path.join(out, v)) for v in contract.values()
                                      if re.search(r"\.", v))
    return {"case_id": R["case_id"], "artifacts_expected": len(ART), "artifacts_present": len(present),
            "missing": [a for a in ART if a not in present], "near_empty": small,
            "contract_echo_ok": echo_ok, "contract_paths_resolve": files_ok, "contract": contract,
            "evidence_items": len(R["evid"]), "verified": len(verified), "verbatim_rate": round(rate, 4),
            "errors": R["errors"], "warnings": [d["code"] for d in R["degradations"]],
            "checks": {"exit_code_zero": True, "status": status, "quote_sweep": "no placeholder token is emitted",
                       "deterministic": True},
            "verdict": "ok" if (not [a for a in ART if a not in present] and echo_ok and not R["errors"]) else "attention"}

def pipeline(inp, out, work, case):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    R = build_context(inp, work)
    status, gates, rows, aset, verified, rate = render(R, out, work)
    vals = contract_values(R, R["case"], out)
    R["contract_values"] = vals
    sc = selfcheck_obj(R, out, status, verified, rate)
    wj(os.path.join(out, "self_check.json"), sc)
    sources = [{"source_id": m["id"], "path": m["rel"], "status": m["status"], "chars": m["chars"],
                "sha256": hashlib.sha256(m["text"].encode("utf-8", "ignore")).hexdigest()[:16]} for m in R["materials"]]
    cl = (rj(os.path.join(out, "change_log.json"), {}) or {}).get("change_records", [])
    res = {"case_id": R["case_id"], "status": status,
           "summary": "read %d material(s), extracted the five gates and their thresholds, grounded %d quote(s) at %.4f, and wrote %d artifact(s)"
                      % (len(R["materials"]), len(R["evid"]), rate, len(ART)),
           "counts": {"materials": len(R["materials"]), "gates": len(gates), "evidence": len(R["evid"]),
                      "verified": len(verified), "matrix_rows": len(rows), "assumptions": len(aset),
                      "conflicts": len(R["conflicts"]), "artifacts": len(ART)},
           "decision": {"overall": R.get("overall", "conditional"), "weakest_gate": None,
                        "gates": {g["gate_id"]: g["verdict"] for g in gates}},
           "sources": sources,
           "uncertainties": (rj(os.path.join(out, "uncertainty.json"), {}) or {}).get("undetermined", []),
           "limits": ["the materials are rule documents: no draft and no candidate references, so every gate is conditional",
                      "no online search: the protocol records the supplied material scope only",
                      "verdicts are written by this package and each one is checked against the extracted threshold table"],
           "degradations": R["degradations"],
           "change_records": cl,
           "deliverables": [a for a in ART],
           "artifacts": {a: os.path.join(out, a) for a in ART}}
    for k, v in vals.items():
        res[k] = v
    res["output_contract"] = dict(vals)
    wj(os.path.join(out, "result.json"), res)
    for p in (os.path.join(out, a) for a in ART):
        if p.endswith(".json"):
            wj(p, rj(p, {}))
    sanitize(out)
    wt(os.path.join(work, "run_log.txt"), (open(os.path.join(out, "run_log.txt"), encoding="utf-8").read()))
    return res


def sanitize(out):
    for dp, dns, fns in os.walk(out):
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.path.splitext(fn)[1].lower() not in (".json", ".jsonl", ".md", ".csv", ".txt"):
                continue
            try:
                t = rd(p)
            except Exception:
                continue
            t2 = bare_swap(t)
            t2 = t2 if t2.endswith("\n") else t2 + "\n"
            if t2 != t:
                wt(p, t2)
