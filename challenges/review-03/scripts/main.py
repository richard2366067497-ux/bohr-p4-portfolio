#!/usr/bin/env python3
"""main.py - 研究方法与统计审查（统计审计台账）: all | init | show | check | build | selfcheck

init  : 索引 /input、抽候选台账行、先写合法 partial result.json
show  : 打印带 locator 的材料与候选行，供逐字引用与判定
check : 校验 draft.json 的枚举、逐字引文、缺陷性质兼容性、严重度上限、覆盖计数
build : 台账 -> audit_report.md / statistics_ledger.json / findings.json / coverage.json / result.json
        无条件 finalize；工作稿缺失时输出完整的最小降级交付
仅标准库、不联网、不依赖 CWD；退出码恒 0。
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract as X
import ledger as L
import autorules as AR

T0 = time.time()
IN, OUT, WRK = X.paths()
IDX, SEED = WRK / "index.json", WRK / "ledger_seed.json"
DRAFT, SKEL, CHK = WRK / "draft.json", WRK / "draft_skeleton.json", WRK / "check_report.json"
RES, REP = OUT / "result.json", OUT / "audit_report.md"
LED, FIND, COV, MAN = (OUT / n for n in ("statistics_ledger.json", "findings.json", "coverage.json", "run_manifest.json"))
now = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
say = lambda s="": print(s, flush=True)
EMPTY_ROW = {"result_question": "", "comparison": "", "n": "", "test_declared": "",
             "test_appropriate": "unknown", "statistic": "", "df": "", "p": "", "effect_size": "",
             "ci": "", "multiple_comparison": "", "sample_size_basis": "", "attrition": "",
             "defect_nature": "none", "severity": "none", "severity_reason": "",
             "issue_type": "", "recommendation": ""}


def find_case():
    paths = [IN / "case.json"] + sorted(IN.rglob("case*.json")) if IN.is_dir() else []
    for p in paths:
        if p.is_file():
            obj, err = X.load_json(p)
            return (obj, p, None) if isinstance(obj, dict) else ({}, p, "bad_case_json:%s" % err)
    return {}, None, "case_json_missing"


def state():
    st = {"errors": [], "degradations": []}
    case, cpath, cerr = find_case()
    st.update(case=case, case_path=cpath)
    if cerr:
        st["errors"].append(cerr)
    st["case_id"] = L.case_id_of(case, IN)
    st["fields"], deg = L.contract_fields(case)
    st["degradations"] += deg
    tm = IN / "task.md"
    if tm.is_file():
        st["task_md"] = tm.read_text(encoding="utf-8", errors="replace")
    else:
        st["degradations"].append("task_md_missing")
        st["task_md"] = ""
    idx, err = X.load_json(IDX) if IDX.is_file() else (None, "no_index")
    if not isinstance(idx, dict):
        idx = X.index_input(IN)
        X.dump_json(IDX, idx)
    seeds, serr = X.load_json(SEED) if SEED.is_file() else (None, "no_seed")
    if not isinstance(seeds, list):
        seeds = X.extract_candidates(idx)
        X.dump_json(SEED, seeds)
    st.update(index=idx, seeds=seeds, hints=X.design_hints(idx), materials=idx.get("materials", []))
    for m in st["materials"]:
        if m.get("quality") not in (None, "ok"):
            st["degradations"].append("material_%s:%s" % (m.get("id"), m.get("quality")))
    return st


def sources_of(st):
    return [{"material_id": m.get("id"), "rel": m.get("rel"), "kind": m.get("kind"),
             "quality": m.get("quality"), "chars": m.get("chars", 0), "sha1": m.get("sha1"),
             "units": len(m.get("units") or []), "notes": m.get("notes", [])}
            for m in st.get("materials", [])]


def envelope(st, status, payload):
    """拼 result.json：信封字段 + 契约字段原样回填（附 output_contract 子对象回显）。"""
    art = dict(payload, case_id=st["case_id"], status=status,
               sources=payload.get("sources", sources_of(st)), errors=st.get("errors", []),
               uncertainty=payload.get("uncertainty", []), pending_review=payload.get("pending_review", []),
               summary=payload.get("summary", ""), coverage=payload.get("coverage", {}),
               unchecked_items=payload.get("unchecked_items", []),
               degradations=list(dict.fromkeys(st.get("degradations", []) + payload.get("degradations", []))))
    filled, fdeg = L.fill_contract(st["fields"], art)
    degs = list(dict.fromkeys(art["degradations"] + fdeg))
    res = {"case_id": st["case_id"], "status": status, "sources": art["sources"],
           "findings": payload.get("findings", []), "statistics_ledger": payload.get("ledger", []),
           "coverage": art["coverage"], "summary": art["summary"], "uncertainty": art["uncertainty"],
           "pending_review": art["pending_review"], "errors": art["errors"], "degradations": degs,
           "changes": payload.get("changes", []),
           "runtime": L.runtime_block(IN, OUT, WRK, payload.get("mode", "run"))}
    res.update(filled)
    res["output_contract"] = dict(filled)
    res["contract_fields"] = list(st["fields"])
    return res, degs


def write_result(res):
    return X.dump_json(RES, res)


def cmd_init(args):
    st = state()
    write_result(envelope(st, "partial", {"mode": "init", "summary": "",
                                          "degradations": ["init_only:尚未进行人工审查"]})[0])
    rows = []
    for s in st["seeds"]:
        r = dict(EMPTY_ROW, ledger_id=s["seed_id"], source_locator=s["source_locator"], quote=s["quote"],
                 assumptions={"normality": "not_reported", "variance": "not_reported",
                              "independence": "not_reported"},
                 cell_status={f: "" for f in L.FACETS},
                 seed_tokens=s.get("observed_tokens"), seed_flags=s.get("flags"))
        rows.append(r)
    X.dump_json(SKEL, {"case_id": st["case_id"],
                       "manuscript_meta": {k: None for k in ("title", "design_type", "field",
                                                             "target_guideline", "n_reported")},
                       "statistics_ledger": rows, "extra_findings": [], "unchecked_items": [],
                       "uncertainties": [], "summary": "",
                       "_howto": "逐行填判定；defect_nature != none 的行会派生 finding。"
                                 "抽不到的台账行自行补行并顺延 ledger_id。"})
    say("INIT  case_id=%s | materials=%d | chars=%d | seed_rows=%d | contract_fields=%d"
        % (st["case_id"], len(st["materials"]), st["index"].get("stats", {}).get("chars", 0),
           len(rows), len(st["fields"])))
    for m in st["materials"]:
        say("  - %-20s %-9s quality=%-13s units=%-3d chars=%6d %s"
            % (m.get("id"), m.get("kind"), m.get("quality"), len(m.get("units") or []), m.get("chars", 0),
               ("| " + ";".join(m.get("notes", []))) if m.get("notes") else ""))
    if st["hints"].get("design_words"):
        say("  design_words: %s" % ", ".join(st["hints"]["design_words"]))
    if st["hints"].get("guidelines"):
        say("  guideline_mentions: %s" % ", ".join(st["hints"]["guidelines"]))
    say("  contract: %s" % ", ".join(st["fields"]))
    for e in st["errors"]:
        say("  ERROR %s" % e)
    say("NEXT  python3 -B main.py show  →  读材料、写 %s  →  check  →  build" % DRAFT)
    return 0


def cmd_show(args):
    st = state()
    say("SHOW  case_id=%s | materials=%d | seed_rows=%d" % (st["case_id"], len(st["materials"]), len(st["seeds"])))
    say("contract_fields: %s" % ", ".join(st["fields"]))
    if args.id:
        for m in st["materials"]:
            if m.get("id") != args.id:
                continue
            say("\n== %s (%s, %s chars, quality=%s)" % (m.get("id"), m.get("rel"), m.get("chars"), m.get("quality")))
            for u in m.get("units") or []:
                if args.grep and args.grep.lower() not in u["text"].lower():
                    continue
                body = u["text"] if (args.full or len(u["text"]) <= args.limit) else u["text"][:args.limit] + " …"
                say("[%s]\n%s\n" % (u.get("locator"), body))
        return 0
    say("\n材料（locator 前缀 = 材料 id）:")
    for m in st["materials"]:
        say("  %-20s %-9s %-13s units=%-3d chars=%-6d %s"
            % (m.get("id"), m.get("kind"), m.get("quality"), len(m.get("units") or []), m.get("chars", 0),
               ("| " + ";".join(m.get("notes", []))) if m.get("notes") else ""))
    if st["hints"].get("design_words"):
        say("设计线索词: %s" % ", ".join(st["hints"]["design_words"]))
    say("\n候选台账行（机械抽取，需你逐条判定；quote 可直接用作逐字引文）:")
    show = [s for s in st["seeds"] if not args.grep or args.grep.lower() in (s.get("quote") or "").lower()]
    for s in show[: max(1, args.rows)]:
        tk = s.get("observed_tokens") or {}
        say("  %s [%s] %s" % (s["seed_id"], s.get("source_locator"), ",".join(s.get("flags") or [])))
        say("     p=%s stat=%s ci=%s n=%s" % (tk.get("p") or "-", tk.get("statistic") or "-",
                                             tk.get("ci") or "-", tk.get("n") or "-"))
        q = (s.get("quote") or "").replace("\n", " ")
        say("     “%s”" % (q if len(q) <= 220 else q[:220] + "…"))
    say("\n下一步：读上面原文（必要时 show --id <材料> --grep <关键词>），把判定写进 %s，再 check / build。" % DRAFT)
    say("骨架：%s" % SKEL)
    return 0


def load_draft():
    obj, err = X.load_json(DRAFT) if DRAFT.is_file() else (None, "draft_missing")
    if isinstance(obj, list):
        obj = {"statistics_ledger": obj}
    return (obj, None) if isinstance(obj, dict) else ({}, "draft_unusable:%s" % (err or "not_a_dict"))


def cmd_check(args):
    st = state()
    draft, derr = load_draft()
    rep = {"case_id": st["case_id"], "errors": [], "warnings": [], "caps": [], "coverage": {}, "status": "PASS"}
    rows = [r for r in (draft.get("statistics_ledger") or draft.get("ledger") or []) if isinstance(r, dict)]
    extra = [f for f in (draft.get("extra_findings") or []) if isinstance(f, dict)]
    if derr:
        rep["errors"].append("%s（build 将输出最小降级交付）" % derr)
    if draft.get("findings"):
        rep["warnings"].append("draft.findings_ignored: 问题一律由台账派生，台账外问题请写 extra_findings")
    for i, r in enumerate(rows):
        r.setdefault("ledger_id", "L-%02d" % (i + 1))
        e, w = L.validate_ledger_row(r, st["index"], i)
        rep["errors"] += e
        rep["warnings"] += w
        sev, changed, note = L.cap_severity(r.get("defect_nature"), r.get("severity"))
        if changed:
            rep["caps"].append({"ledger_id": r.get("ledger_id"), "rule": note, "to": sev})
    for j, f in enumerate(extra):
        e, w = L.validate_finding(f, st["index"], "X-%02d" % (j + 1))
        rep["errors"] += e
        rep["warnings"] += w
    fins, _ch = L.derive_findings(rows, extra)
    cov = L.coverage(rows, fins)
    if cov["missing_facets"]:
        rep["warnings"].append("coverage_gap: 未覆盖检查面 %s（补行或写 unchecked_items 说明）"
                               % ",".join(cov["missing_facets"]))
    if not rows:
        rep["warnings"].append("empty_ledger: 尚无台账行")
    rep["coverage"] = {k: cov[k] for k in ("facets_covered", "missing_facets", "dimensions_covered",
                                           "findings", "severity_counts", "nature_counts")}
    rep["status"] = "PASS" if not rep["errors"] else "FAIL"
    X.dump_json(CHK, rep)
    say("CHECK  case_id=%s | rows=%d | extra=%d | findings(derived)=%d" % (st["case_id"], len(rows), len(extra), len(fins)))
    for e in rep["errors"]:
        say("  ERROR %s" % e)
    for w in rep["warnings"]:
        say("  WARN  %s" % w)
    for c in rep["caps"]:
        say("  CAP   %s %s → %s" % (c["ledger_id"], c["rule"], c["to"]))
    say("  coverage: facets %d/5%s | dims %d/6 | severity %s"
        % (cov["facets_covered"], (" (missing %s)" % ",".join(cov["missing_facets"])) if cov["missing_facets"] else "",
           len(cov["dimensions_covered"]), json.dumps(cov["severity_counts"], ensure_ascii=False)))
    say("  contract: %d fields, build 时全量回填" % len(st["fields"]))
    say("  RESULT: %s (errors=%d warnings=%d) → %s" % (rep["status"], len(rep["errors"]), len(rep["warnings"]), CHK))
    return 0


def _norm_rows(rows):
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        r = dict(EMPTY_ROW, **r)
        r["ledger_id"] = str(r.get("ledger_id") or "L-%02d" % (i + 1))
        r["assumptions"] = r["assumptions"] if isinstance(r.get("assumptions"), dict) else {}
        r["cell_status"] = r["cell_status"] if isinstance(r.get("cell_status"), dict) else {}
        out.append(r)
    return out




def cmd_all(args):
    """单命令入口：init -> 确定性自动推导 -> build；无 draft 也产出完整可核验交付。"""
    cmd_init(args)
    return cmd_build(args)


def cmd_build(args):
    st = state()
    write_result(envelope(st, "partial", {"mode": "build", "summary": "",
                                          "degradations": ["build_in_progress"]})[0])  # ① 先写合法 partial
    draft, derr = load_draft()
    degraded = [derr] if derr else []
    rows = _norm_rows(draft.get("statistics_ledger") or draft.get("ledger") or [])
    extra = [f for f in (draft.get("extra_findings") or []) if isinstance(f, dict)]
    if not rows:
        auto = AR.auto_derive(st)
        rows = _norm_rows(auto["rows"])
        extra = auto["extra"] + extra
        degraded += auto["degradations"]
        draft = dict(draft or {})
        draft["auto_derived"] = True
        draft["uncertainties"] = list(draft.get("uncertainties") or []) + auto["uncertainties"]
    if not rows:
        degraded.append("no_ledger_rows: 输出 init 候选行骨架（未判定），真问题需 Agent 判定")
        rows = _norm_rows([dict(EMPTY_ROW, ledger_id=s["seed_id"], source_locator=s["source_locator"],
                                quote=s["quote"], cell_status={}, seed_tokens=s.get("observed_tokens"),
                                judged=False) for s in st["seeds"]])
    pend_unjudged = [{"kind": "unjudged_row", "ledger_id": r["ledger_id"], "source_locator": r.get("source_locator")}
                     for r in rows if r.get("judged") is False]
    errs, pend = [], []
    for i, r in enumerate(rows):
        for x in L.validate_ledger_row(r, st["index"], i)[0]:
            errs.append("ledger:%s" % x)
            if "evidence_rejected" in x:
                pend.append({"kind": "evidence_rejected", "ledger_id": r["ledger_id"],
                             "quote": X.snip(r.get("quote"), 160)})
                r["defect_nature"], r["severity"] = "none", "none"
    for j, f in enumerate(extra):
        for x in L.validate_finding(f, st["index"], "X-%02d" % (j + 1))[0]:
            errs.append("extra:%s" % x)
            if "evidence_rejected" in x:
                pend.append({"kind": "evidence_rejected", "finding": "X-%02d" % (j + 1),
                             "quote": X.snip(f.get("quote"), 160)})
    pend += pend_unjudged
    if pend:
        degraded.append("evidence_or_table_pending:%d 项已进 pending_review，不计入 findings" % len(pend))
    if pend_unjudged:
        degraded.append("unjudged_rows:%d 行台账未被 Agent 判定，已进 pending_review" % len(pend_unjudged))
    findings, changes = L.derive_findings(rows, extra)
    by_id = {r["ledger_id"]: r for r in rows}
    for c in changes:  # 让台账/报告与派生结果一致：封顶结果回写行，并保留原判
        r = by_id.get(str(c.get("id")))
        if r is not None and r.get("severity") == c.get("from"):
            r["severity_original"] = c.get("from")
            r["severity"] = c.get("to")
            r["severity_note"] = c.get("rule")
    cov = L.coverage(rows, findings)
    meta = draft.get("manuscript_meta") if isinstance(draft.get("manuscript_meta"), dict) else {}
    unc = [str(x) for x in (draft.get("uncertainties") or draft.get("uncertainty") or [])]
    unch = [u for u in (draft.get("unchecked_items") or []) if isinstance(u, dict)]
    for m in st["materials"]:
        if m.get("quality") not in (None, "ok", "empty"):
            unch.append({"item": m.get("rel"), "reason": "material_quality=%s（%s）"
                         % (m.get("quality"), ";".join(m.get("notes", [])) or "无法解析")})
    if cov["missing_facets"]:
        unch.append({"item": "facet:" + ",".join(cov["missing_facets"]),
                     "reason": "该检查面无已判定台账行与关联问题，记为未检查（不等于无缺陷）"})
    sc = cov["severity_counts"]
    summary = str(draft.get("summary") or "").strip() or (
        "共建立 %d 行统计台账，派生 %d 条问题（critical %d、major %d、minor %d、suggestion %d）；"
        "五检查面覆盖 %d/5，六类审查面覆盖 %d/6。"
        % (len(rows), len(findings), sc.get("critical", 0), sc.get("major", 0), sc.get("minor", 0),
           sc.get("suggestion", 0), cov["facets_covered"], len(cov["dimensions_covered"])))
    status = "ok"
    if not st["materials"]:
        status = "input_error"
        degraded.append("no_input_materials")
    if st["errors"] or degraded or errs or pend or cov["missing_facets"]:
        status = status if status == "input_error" else "partial"
    ctx = {"status": status, "meta": dict(meta, case_id=st["case_id"]), "ledger": rows, "findings": findings,
           "coverage": cov, "pending_review": pend, "unchecked_items": unch, "degradations": degraded,
           "uncertainty": unc}
    report = L.render_report(ctx)
    X.write_text(REP, report)
    X.dump_json(LED, {"case_id": st["case_id"], "rows": rows, "schema_version": "ledger-1.0",
                      "facets": list(L.FACETS)})
    X.dump_json(FIND, {"case_id": st["case_id"], "findings": findings, "changes": changes,
                       "nature_labels": L.NATURE_LABEL, "facet_labels": L.FACET_LABEL})
    X.dump_json(COV, dict(cov, case_id=st["case_id"]))
    if draft.get("auto_derived"):
        summary = "【单命令自动模式】" + summary + "（脚本按原文可核验的报告完整性规则派生，confidence=low；非人工判定）"
    payload = {"mode": "build", "ledger": rows, "findings": findings, "coverage": cov, "summary": summary,
               "auto_derived": bool(draft.get("auto_derived")),
               "report_md": report, "changes": changes, "pending_review": pend,
               "unchecked_items": unch, "uncertainty": unc, "sources": sources_of(st),
               "evidence_index": [{"finding_id": f.get("finding_id"), "ref": f.get("ledger_id"),
                                   "source_locator": f.get("source_locator"), "quote": f.get("quote")}
                                  for f in findings if f.get("quote")],
               "degradations": degraded}
    res, degs = envelope(st, status, payload)
    if draft.get("auto_derived"):
        res["auto_derived"] = {"mode": "no_draft_rules", "confidence": "low",
                               "note": "无工作稿时按原文可逐字核验的报告完整性规则派生；写 draft.json 可进入高质量人工判定路径"}
    res["unchecked_items"] = unch
    res["artifacts"] = {"audit_report": str(REP), "statistics_ledger": str(LED),
                        "findings": str(FIND), "coverage": str(COV)}
    write_result(res)
    X.dump_json(MAN, {"case_id": st["case_id"], "generated_at": now(), "elapsed_s": round(time.time() - T0, 2),
                      "skill": {"name": L.SKILL, "version": L.VERSION},
                      "inputs": {"case_json": str(st.get("case_path")), "input_root": str(IN),
                                 "materials": [{k: m.get(k) for k in ("id", "rel", "sha1", "quality", "chars")}
                                               for m in st["materials"]]},
                      "outputs": {p.name: X.sha1(p) for p in (RES, REP, LED, FIND, COV)},
                      "degradations": degs, "errors": st["errors"] + errs, "changes": changes,
                      "budget": {"seconds": 900, "requests": 64, "tokens_per_response": 16384}})
    say("BUILD  case_id=%s status=%s | ledger_rows=%d findings=%d | facets=%d/5 dims=%d/6"
        % (st["case_id"], status, len(rows), len(findings), cov["facets_covered"], len(cov["dimensions_covered"])))
    say("  severity: %s" % json.dumps(sc, ensure_ascii=False))
    say("  nature:   %s" % json.dumps(cov["nature_counts"], ensure_ascii=False))
    for d in degs:
        say("  DEGRADE %s" % d)
    for e in (st["errors"] + errs)[:6]:
        say("  ERROR %s" % e)
    say("  → %s | %s | %s | %s" % (RES, REP, LED, FIND))
    return 0


def cmd_selfcheck(args):
    fails, st = [], state()
    res, err = X.load_json(RES) if RES.is_file() else (None, "missing")
    if not isinstance(res, dict):
        fails.append("result.json 不可读: %s" % err)
        res = {}
    fails += ["result.json 缺契约字段: %s" % f for f in st["fields"] if f not in res]
    fails += ["result.json 缺信封字段: %s" % k for k in ("case_id", "status", "sources", "uncertainty",
                                                         "pending_review", "errors", "degradations",
                                                         "changes", "runtime") if k not in res]
    if res.get("case_id") != st["case_id"]:
        fails.append("case_id 不一致: %r != %r" % (res.get("case_id"), st["case_id"]))
    qok = sum(1 for f in res.get("findings") or []
              if f.get("quote") and X.qmatch(st["index"], f["quote"], f.get("source_locator"))[0])
    qbad = sum(1 for f in res.get("findings") or []
               if f.get("quote") and not X.qmatch(st["index"], f["quote"], f.get("source_locator"))[0])
    if qbad:
        fails.append("有 %d 条 finding 的 quote 无法逐字命中材料" % qbad)
    ids = [r.get("ledger_id") for r in (res.get("statistics_ledger") or [])]
    if len(ids) != len(set(ids)):
        fails.append("ledger_id 不唯一")
    if (res.get("coverage") or {}).get("findings") != L.coverage(res.get("statistics_ledger") or [],
                                                                res.get("findings") or [])["findings"]:
        fails.append("coverage.findings 与重算不一致")
    txt = REP.read_text(encoding="utf-8", errors="replace") if REP.is_file() else ""
    if len(txt) < 400:
        fails.append("audit_report.md 缺失或过小")
    fails += ["audit_report.md 缺章节: %s" % s for s in ("一、", "二、", "三、", "四、", "五、", "六、", "七、")
              if "## " + s not in txt]
    if not res.get("findings") and res.get("status") == "ok":
        fails.append("status=ok 但零问题：若确无缺陷请在 summary 写明并保留覆盖证据")
    say("SELFCHECK case_id=%s status=%s | quotes_ok=%d quotes_bad=%d | ledger=%d findings=%d"
        % (st["case_id"], res.get("status"), qok, qbad, len(res.get("statistics_ledger") or []),
           len(res.get("findings") or [])))
    for f in fails:
        say("  FAIL %s" % f)
    say("  RESULT: %s" % ("PASS" if not fails else "FAIL(%d)" % len(fails)))
    return 0


def apply_cli_paths(argv):
    """允许 --input/--output/--work 出现在任意位置：抽取后写入 SCIM_* 环境变量并重算路径全局。"""
    global IN, OUT, WRK, IDX, SEED, DRAFT, SKEL, CHK, RES, REP, LED, FIND, COV, MAN
    flags = {"--input": "SCIM_INPUT", "--output": "SCIM_OUTPUT", "--work": "SCIM_WORK",
             "--out": "SCIM_OUTPUT"}
    kept, changed, i = [], False, 0
    while i < len(argv):
        a = argv[i]
        hit = None
        if a in flags and i + 1 < len(argv):
            hit = (flags[a], argv[i + 1])
            i += 2
        else:
            for k, env in flags.items():
                if a.startswith(k + "="):
                    hit = (env, a.split("=", 1)[1])
                    i += 1
                    break
        if hit:
            os.environ[hit[0]] = hit[1]
            changed = True
            continue
        kept.append(a)
        i += 1
    if changed:
        IN, OUT, WRK = X.paths()
        IDX, SEED = WRK / "index.json", WRK / "ledger_seed.json"
        DRAFT, SKEL, CHK = WRK / "draft.json", WRK / "draft_skeleton.json", WRK / "check_report.json"
        RES, REP = OUT / "result.json", OUT / "audit_report.md"
        LED, FIND, COV, MAN = (OUT / n for n in ("statistics_ledger.json", "findings.json",
                                                 "coverage.json", "run_manifest.json"))
        try:
            OUT.mkdir(parents=True, exist_ok=True)
            WRK.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return kept


def run(argv):
    argv = apply_cli_paths(argv)
    ap = argparse.ArgumentParser(prog="main.py", description="statistical-audit-ledger")
    sub = ap.add_subparsers(dest="cmd")
    for c in ("init", "check", "build", "selfcheck", "all"):
        sub.add_parser(c)
    sp = sub.add_parser("show")
    sp.add_argument("--id", default=None, help="材料 id")
    sp.add_argument("--grep", default=None)
    sp.add_argument("--limit", type=int, default=1600)
    sp.add_argument("--rows", type=int, default=40)
    sp.add_argument("--full", action="store_true")
    a = ap.parse_args(argv)
    return {"init": cmd_init, "show": cmd_show, "check": cmd_check,
            "build": cmd_build, "selfcheck": cmd_selfcheck,
            "all": cmd_all}[a.cmd or "show"](a)


def _bail(where):
    """兜底：任何异常都写一份合法 partial result.json。"""
    try:
        try:
            OUT.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        st = {"errors": ["exception_in_%s:%s" % (where, traceback.format_exc().splitlines()[-1][:180])],
              "degradations": ["unhandled_exception"], "case_id": "unknown",
              "fields": list(L.DEFAULT_CONTRACT), "materials": [], "index": {"materials": []}}
        write_result(envelope(st, "partial", {"mode": where, "summary": "运行异常，已输出最小合法结果。"})[0])
        say("FALLBACK 已写合法 partial result.json (%s)" % st["errors"][0])
    except Exception:
        X.dump_json(RES, {"case_id": "unknown", "status": "partial", "errors": ["fatal"],
                          "degradations": ["fatal"], "sources": [], "uncertainty": [],
                          "pending_review": [], "changes": [], "runtime": {}})


if __name__ == "__main__":
    where = sys.argv[1] if len(sys.argv) > 1 else "cli"
    try:
        run(sys.argv[1:])
    except SystemExit:
        if not any(x in ("-h", "--help") for x in sys.argv[1:]):
            _bail(where)
    except Exception:
        _bail(where)
    sys.exit(0)
