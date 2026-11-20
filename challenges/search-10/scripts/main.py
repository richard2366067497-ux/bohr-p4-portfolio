#!/usr/bin/env python3
"""main.py - search-10 cross-language known-item retrieval CLI.

    python3 scripts/main.py init       # discover views + fingerprint + legal partial result.json
    python3 scripts/main.py show       # questions, view ledger, candidate anchors (with locators)
    python3 scripts/main.py check      # mechanical validation of /app/work/draft.json
    python3 scripts/main.py build      # four deliverables + final result.json (fallback-safe)
    python3 scripts/main.py selfcheck   # re-verify the written deliverables

Paths default to /input, /app/work, /app/output. Exit code is always 0.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cards as CD      # noqa: E402
import pipeline as PL   # noqa: E402
import verify as VF     # noqa: E402
import views as VW      # noqa: E402

T0 = time.time()
VER = "1.0.0"
SKILL = "xling-known-item-answer-card"
CONTRACT_KEYS = ("answer_cards", "view_fingerprints", "lang_routing", "reconciliation",
                 "queries_by_lang", "evidence", "coverage", "counts")
ALIAS = [("fingerprint", "view_fingerprints"), ("view", "view_fingerprints"),
         ("card", "answer_cards"), ("answer", "answer_cards"), ("retriev", "answer_cards"),
         ("hit", "answer_cards"), ("match", "answer_cards"), ("candidate", "answer_cards"),
         ("rout", "lang_routing"), ("query", "queries_by_lang"), ("queries", "queries_by_lang"),
         ("lang", "lang_routing"), ("recon", "reconciliation"), ("dedup", "reconciliation"),
         ("distinct", "reconciliation"), ("count", "counts"), ("index", "view_fingerprints"),
         ("evidence", "evidence"), ("citation", "evidence"), ("quote", "evidence"),
         ("coverage", "coverage"), ("method", "method_notes"), ("note", "method_notes")]


def alias(k):
    for pat, tgt in ALIAS:
        if pat in VW.low(k):
            return tgt
    return None


def new_state():
    return {"case_id": None, "status": "partial", "contract": {}, "result": {},
            "claims": [], "uncertainties": [], "sources": [], "pending_human": [],
            "errors": [], "degradations": [], "changes": [], "assumptions": [],
            "coverage": {}, "counts": {},
            "runtime": {"skill": SKILL, "version": VER, "python": sys.version.split()[0]}}


def compose(st):
    r = {"case_id": st.get("case_id"), "status": st.get("status") or "partial",
         "result": st.get("result") if isinstance(st.get("result"), dict) else {}}
    for k in ("claims", "uncertainties", "sources", "pending_human", "errors", "degradations",
              "changes", "assumptions"):
        r[k] = st.get(k) or []
    r["uncertainty"] = r["uncertainties"]
    r["coverage"] = st.get("coverage") or {}
    r["counts"] = st.get("counts") or {}
    r["runtime"] = st.get("runtime") or {}
    res, echo = r["result"], {}
    con = st.get("contract") if isinstance(st.get("contract"), dict) else {}
    for k, v in con.items():
        tgt = k if k in res else alias(k)
        if tgt and tgt in res:
            r[k] = res[tgt]
            echo[k] = "result." + tgt
        elif k in r:
            echo[k] = k
        else:
            r[k] = [] if isinstance(v, list) else ({} if isinstance(v, dict) else None)
            echo[k] = "empty(%s)" % type(v).__name__
    r["output_contract_echo"] = echo
    r["contract_fields_missing"] = [k for k in con if k not in r]
    return r


def wj(p, obj):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except (OSError, ValueError, TypeError):
        return False


def wt(p, s):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s, encoding="utf-8")
        return True
    except OSError:
        return False


def pick(explicit, cands, mk=False, st=None):
    for c in ([Path(explicit).expanduser()] if explicit else []) + [Path(x) for x in cands]:
        try:
            if mk:
                c.mkdir(parents=True, exist_ok=True)
            if c.is_dir():
                return c
        except OSError:
            continue
    if st is not None:
        st["errors"].append({"stage": "paths", "message": "no usable dir in %s" % (cands,)})
    return Path.cwd()


def env_of(a):
    st = new_state()
    return {"inp": pick(a.input, ["/input", "./input", "../input",
                                  str(HERE.parent / "input")], st=st),
            "work": pick(a.work, ["/app/work", "./work", "./.work"], mk=True, st=st),
            "out": pick(a.output, ["/app/output", "./output"], mk=True, st=st), "st": st}


def save(out, st):
    if not wj(out / "result.json", compose(st)):
        st["errors"].append({"stage": "write", "message": "result.json not writable"})


def skeleton(st, out, inp=None):
    """Earliest legal partial: envelope + every contract key (empty) before any analysis."""
    if inp is not None and not st.get("contract"):
        try:
            case, _ = PL.load_case(inp, {"errors": [], "degradations": []})
            if isinstance(case, dict):
                st["case_id"] = case.get("case_id") or case.get("id")
                st["contract"] = PL.contract_of(case)
        except Exception:  # noqa: BLE001 - pre-flight must never fail
            pass
    st["result"] = {"answer_cards": [], "view_fingerprints": [], "lang_routing": [],
                    "reconciliation": {}, "queries_by_lang": {}, "evidence": [],
                    "method_notes": ["partial result written before analysis"]}
    st["status"] = "partial"
    save(out, st)


def cmd_init(a):
    env = env_of(a)
    st, inp, work, out = env["st"], env["inp"], env["work"], env["out"]
    skeleton(st, out, inp)
    ctx = PL.analyse(inp, st)
    fps = [VW.fingerprint(v) for v in ctx["views"]]
    wj(work / "index.json", {
        "case_id": st["case_id"], "input_dir": str(inp), "contract_keys": list(st["contract"]),
        "questions": ctx["questions"], "views": fps, "sources": ctx["sources"],
        "candidates": {k: {"source_lang": v["source_lang"],
                           "works": [{kk: w[kk] for kk in ("work_id", "score", "components",
                                                           "best_view", "anchor_languages",
                                                           "doi", "title")}
                                     for w in v["works"]],
                           "top_rows": [{kk: r[kk] for kk in ("view_id", "work_id", "language",
                                                              "version", "doc_type", "score",
                                                              "components")}
                                        for r in v["rows"][:6]]}
                       for k, v in ctx["cands"].items()},
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    st["result"]["view_fingerprints"] = fps
    st["result"]["reconciliation"] = {"counting_policy": "按 work_id 去重计 1 条",
                                      "views_total": len(ctx["views"]),
                                      "distinct_works": len({v["work_id"] for v in ctx["views"]})}
    st["result"]["method_notes"] = ["init：已完成视图发现与指纹，答题卡需工作稿"]
    st["sources"] = ctx["sources"]
    st["counts"] = {"views": len(ctx["views"]), "works": len({v["work_id"] for v in ctx["views"]}),
                    "questions": len(ctx["questions"]), "contract_fields": len(st["contract"])}
    save(out, st)
    print("[init] input=%s work=%s out=%s" % (inp, work, out))
    print("[init] case_id=%s contract=%s" % (st["case_id"], list(st["contract"])))
    print("[init] %s" % json.dumps(st["counts"], ensure_ascii=False))
    for v in fps:
        print("  view %-20s work=%-12s lang=%s/%s ver=%-19s %-12s dup=%s"
              % (v["view_id"], v["work_id"], v["language"], v["language_detected"],
                 str(v["version"]), v["doc_type"], v.get("duplicate_of") or "-"))
    for q in ctx["questions"]:
        print("  q    %-5s [%s] %s" % (q["question_id"], q["locator"], q["text"][:80]))
    if not ctx["questions"]:
        print("  !! 未能从 case.json/task.md 提取问题：请在 draft.json 手写 questions[]")
    print("[init] next: python3 scripts/main.py show")
    return env


def cmd_show(a):
    env = env_of(a)
    st, inp, out = env["st"], env["inp"], env["out"]
    skeleton(st, out, inp)
    ctx = PL.analyse(inp, st, PL.load_draft(env["work"]))
    all_langs = sorted({v["language"] for v in ctx["views"]})
    print("@@ 问题（题面 locator 可回指）")
    for q in ctx["questions"]:
        f = ctx["feats"][q["question_id"]]
        c = ctx["cands"][q["question_id"]]
        print("\n[%s] %s lang=%s" % (q["question_id"], q["locator"], c["source_lang"]))
        print("  text : %s" % q["text"][:320])
        print("  专名 : doi=%s years=%s quotes=%s authors=%s"
              % (f["doi"], f["years"], [x[:36] for x in f["quoted"]][:3], f["authors"][:4]))
        print("  术语 : %s" % (", ".join("%s=%s" % (x["cid"], x["surface"])
                                         for x in f["concepts"][:8]) or "-"))
        qs = CD.queries_for(f, c["source_lang"], all_langs, ctx["views"])
        for lg in sorted(qs)[:4]:
            print("  query %-3s %s" % (lg, qs[lg]["query"][:150]))
    print("\n@@ 视图台账（语种/版本/重复/定位 + 正文摘要，供逐字引用）")
    for v in ctx["views"]:
        print("\n[%s] work=%s lang=%s(decl=%s det=%s) ver=%s doc=%s%s"
              % (v["view_id"], v["work_id"], v["language"], v["language_declared"],
                 v["language_detected"], v["version"], v["doc_type"],
                 " DUP_OF=%s" % v["duplicate_of"] if v.get("duplicate_of") else ""))
        print("  loc=%s chars=%s words=%s doi=%s" % (v["locator"], v["chars"], v["words"],
                                                     v.get("doi")))
        print("  title=%s" % (v.get("title") or "")[:150])
        print("  lang_ev=%s" % json.dumps((v.get("lang_evidence") or [{}])[0].get("markers", [])[:4],
                                          ensure_ascii=False))
        if v.get("version_basis"):
            print("  ver_ev=%s" % json.dumps(v["version_basis"][:2], ensure_ascii=False)[:200])
        print("  text=%s" % VW.norm(v.get("text", ""))[:480])
        for u in VW.units(v, limit=4)[:3]:
            print("    - %s @%s" % (u["quote"][:180], u["locator"]))
    print("\n@@ 机器候选（仅供参考；draft 会覆盖）")
    for q in ctx["questions"]:
        print("\n[%s] source_lang=%s" % (q["question_id"], ctx["cands"][q["question_id"]]["source_lang"]))
        for w in ctx["cands"][q["question_id"]]["works"][:3]:
            print("  work %-12s score=%6.2f anchors=%-10s best=%-18s title=%s"
                  % (w["work_id"], w["score"], ",".join(w["anchor_languages"]), w["best_view"],
                     (w.get("title") or "")[:70]))
            print("       components=%s" % json.dumps(w["components"], ensure_ascii=False))
    print("\n%s" % ("-" * 74))
    print("下一步（必做）：读材料原文 → 写 %s → check → build。" % (env["work"] / "draft.json"))
    print("脚本不会代替你阅读理解；view_labels 与 matches 的证据必须由你判断后填写。")
    print("-" * 74)
    st["result"]["view_fingerprints"] = [VW.fingerprint(v) for v in ctx["views"]]
    save(out, st)
    return env


def cmd_check(a):
    env = env_of(a)
    st, inp, work, out = env["st"], env["inp"], env["work"], env["out"]
    skeleton(st, out, inp)
    draft = PL.load_draft(work)
    ctx = PL.analyse(inp, st, draft)
    checks = VF.draft_checks(draft, ctx["views"], ctx["by_id"], ctx["questions"])
    qrep, okmap = VF.quotes(draft, ctx["views"], ctx["questions"])
    cnt, problems = VF.dedup_checks(draft, ctx["views"])
    cards = PL.cards_of(ctx, st, draft, okmap)
    cov = PL.coverage_of(ctx, cards, draft, qrep)
    con = st["contract"]
    echo = {k: (k if k in CONTRACT_KEYS else alias(k)) or "empty" for k in con}
    checks += [{"id": "K1", "ok": True, "level": "info",
                "detail": "契约键可回填 %d/%d" % (len([k for k in con if echo[k] != "empty"]),
                                                len(con))},
               {"id": "K2", "ok": not problems, "level": "warn",
                "detail": "去重口径%s" % ("一致" if not problems else
                                          "冲突 %s" % json.dumps(problems, ensure_ascii=False))}]
    bad = [q for q in qrep if not q["verified"]]
    checks.append({"id": "K3", "ok": not bad, "level": "error",
                   "detail": "逐字引用 %d/%d%s" % (len(qrep) - len(bad), len(qrep),
                                                  "" if not bad else "；失败 %s"
                                                  % [(b["question_id"], b["quote"][:36])
                                                     for b in bad[:4]])})
    checks.append({"id": "K4", "ok": cov["cards_found"] == cov["questions_total"],
                   "level": "warn", "detail": "答题卡命中 %d/%d"
                   % (cov["cards_found"], cov["questions_total"])})
    report = {"case_id": st["case_id"], "draft_found": bool(draft), "checks": checks,
              "quote_report": qrep, "dedup": {"counts": cnt, "problems": problems},
              "contract_echo": echo, "coverage": cov,
              "summary": {"pass": len([c for c in checks if c["ok"]]),
                          "fail": len([c for c in checks if not c["ok"]])}}
    wj(work / "check_report.json", report)
    print("[check] draft=%s" % ("found" if draft else "MISSING（build 将降级为完整 partial）"))
    for c in checks:
        print("  [%s] %-3s %s" % ("PASS" if c["ok"] else "FAIL", c["id"], c["detail"]))
    print("[check] 契约键: %s" % json.dumps(echo, ensure_ascii=False))
    print("[check] 覆盖: %s" % json.dumps(cov, ensure_ascii=False))
    print("[check] 报告: %s" % (work / "check_report.json"))
    print("[check] next: python3 scripts/main.py build")
    save(out, st)
    return env


def cmd_build(a):
    env = env_of(a)
    st, inp, work, out = env["st"], env["inp"], env["work"], env["out"]
    skeleton(st, out, inp)
    draft = PL.load_draft(work)
    ctx = PL.analyse(inp, st, draft)
    if not draft:
        st["degradations"].append({"item": "draft.json", "stage": "build",
                                   "action": "回退到机器候选（confidence=low）",
                                   "impact": "答题卡存在但缺少人工判断"})
    qrep, okmap = VF.quotes(draft, ctx["views"], ctx["questions"])
    cards = PL.cards_of(ctx, st, draft, okmap)
    if not draft:
        for c in cards:
            c["agent_authored"] = False
            c["confidence"] = "low"
            c["notes"] = (c.get("notes") or []) + ["无工作稿：由确定性候选打分装配"]
    fps = [VW.fingerprint(v) for v in ctx["views"]]
    for v, fp in zip(ctx["views"], fps):
        fp["label_source"] = v.get("label_source", "script")
        if v.get("label_conflicts"):
            fp["label_conflicts"] = v["label_conflicts"]
    rows, rec = PL.routing_rows(cards), PL.reconcile(ctx, cards)
    cov, ev = PL.coverage_of(ctx, cards, draft, qrep), PL.evidence_of(cards)
    st["result"] = {"answer_cards": cards, "view_fingerprints": fps, "lang_routing": rows,
                    "reconciliation": rec,
                    "queries_by_lang": {c["question_id"]: c.get("queries_by_lang")
                                        for c in cards},
                    "evidence": ev, "coverage": cov,
                    "method_notes": ["双向锚定（源语侧 + 目标语侧）over discovered views",
                                     "术语对齐仅用内置术语表与专名锚点，不外呼翻译服务",
                                     "去重按 work 计数，重复视图保留在指纹台账"]}
    st["coverage"], st["sources"] = cov, ctx["sources"]
    st["counts"] = {"views": len(ctx["views"]), "works": rec["distinct_works"],
                    "questions": len(ctx["questions"]), "cards_found": cov["cards_found"],
                    "evidence": len(ev), "evidence_verified": cov["evidence_quote_verified"],
                    "duplicates": len(rec["duplicates_excluded"])}
    st["claims"] = PL.claims_of(cards, qrep)
    for q in qrep:
        if not q.get("verified"):
            st["pending_human"].append({"item": "quote_unverified",
                                        "why": "引用未逐字命中：%s" % q["quote"][:60],
                                        "action": "按材料原文重写该 quote"})
    for c in cards:
        if c.get("status") == "not_found":
            st["pending_human"].append({"item": "miss:%s" % c["question_id"],
                                        "why": (c.get("misses") or {}).get("reason"),
                                        "action": (c.get("misses") or {}).get("next_action")})
        if c.get("status") == "ambiguous":
            st["pending_human"].append({"item": "ambiguous:%s" % c["question_id"],
                                        "why": "两个 work 分数接近，需人工判定",
                                        "action": "读两份视图标题/摘要确认 target"})
        for p in (c.get("false_positive_check") or {}).get("risks") or []:
            st["pending_human"].append({"item": "backtranslation:%s" % c["question_id"],
                                        "why": "%s ↔ %s 回译不在同义集合"
                                               % (p.get("concept"), p.get("target_term")),
                                        "action": "人工确认术语仍指向同一概念"})
    st["assumptions"] = [
        {"id": "A1", "text": "视图语种以声明元数据优先，文本检测作交叉校验并记录冲突"},
        {"id": "A2", "text": "计数口径按 work 去重：同一论文的不同语言视图计 1 条"},
        {"id": "A3", "text": "术语对齐仅用内置术语表 + 专名锚点，不外呼翻译服务"}]
    if not ctx["views"]:
        st["status"] = "insufficient_evidence" if ctx.get("case_loaded") else "input_error"
        reason = ("材料里没有找到视图对象" if ctx.get("case_loaded")
                  else "case.json 缺失或不可解析，且无可用材料")
    elif not ctx["questions"]:
        st["status"] = "partial"
        reason = "未提取到研究问题：需在 draft.json 手写 questions[]"
    elif not draft:
        st["status"] = "partial"
        reason = "工作稿缺失，答题卡退化为机器候选"
    elif [q for q in qrep if not q.get("verified")]:
        st["status"] = "partial"
        reason = "%d 条工作稿引用未能逐字命中" % len([q for q in qrep if not q.get("verified")])
    elif any(c.get("status") == "not_found" for c in cards):
        st["status"] = "partial"
        reason = "至少一题无达标命中"
    else:
        st["status"], reason = "ok", ""
    if reason:
        st["result"]["status_reason"] = reason
    st["changes"] = [{"item": k, "action": "written", "reason": "build 主路径产物"}
                     for k in ("answer_cards.json", "view_fingerprints.jsonl", "lang_routing.md",
                               "reconciliation.md", "result.json")]
    st["runtime"] = {"skill": SKILL, "version": VER, "python": sys.version.split()[0],
                     "elapsed_s": round(time.time() - T0, 2), "input_dir": str(inp),
                     "work_dir": str(work), "output_dir": str(out), "glossary": CD.GLOSS_SRC}
    wj(out / "answer_cards.json", {"case_id": st["case_id"], "cards": cards})
    wt(out / "view_fingerprints.jsonl",
       "\n".join(json.dumps(f, ensure_ascii=False) for f in fps) + "\n")
    wt(out / "lang_routing.md", PL.routing_md(rows, cards))
    wt(out / "reconciliation.md", PL.recon_md(rec, ctx, st))
    save(out, st)
    fin = compose(st)
    print("[build] case_id=%s status=%s %s" % (st["case_id"], st["status"], reason))
    print("[build] cards=%d found=%d views=%d works=%d evidence=%d verified=%d"
          % (len(cards), cov["cards_found"], len(ctx["views"]), rec["distinct_works"], len(ev),
             cov["evidence_quote_verified"]))
    print("[build] contract=%d missing=%s" % (len(st["contract"]),
                                              fin["contract_fields_missing"]))
    for c in cards:
        tv = c.get("target_view") or {}
        print("  %-5s %-9s conf=%-6s view=%-18s lang=%s ver=%s"
              % (c["question_id"], c.get("status"), c.get("confidence"),
                 tv.get("view_id") or "-", tv.get("language") or "-", tv.get("version") or "-"))
    print("[build] wrote answer_cards.json view_fingerprints.jsonl lang_routing.md "
          "reconciliation.md result.json -> %s" % out)
    return env


def cmd_selfcheck(a):
    env = env_of(a)
    st, out = env["st"], env["out"]
    res = VW.read_json_any(out / "result.json") if (out / "result.json").is_file() else None
    issues = [] if isinstance(res, dict) else ["result.json 缺失或不是 JSON 对象"]
    if not isinstance(res, dict):        # never overwrite a real result while checking it
        skeleton(st, out)
        res = {}
    miss = res.get("contract_fields_missing")
    if miss:
        issues.append("contract_fields_missing=%s" % miss)
    arts = {}
    for n in ("answer_cards.json", "view_fingerprints.jsonl", "lang_routing.md",
              "reconciliation.md"):
        p = out / n
        arts[n] = p.stat().st_size if p.is_file() else 0
        if not arts[n]:
            issues.append("%s 缺失或为空" % n)
    cards = (res.get("result") or {}).get("answer_cards") or []
    if not cards:
        issues.append("answer_cards 为空")
    unver = [c["question_id"] for c in cards if isinstance(c, dict) and c.get("target_view")
             and not ((c.get("evidence_chain") or {}).get("body_quote") or {}).get("verified")]
    cov = res.get("coverage") or {}
    print("[selfcheck] status=%s case_id=%s" % (res.get("status"), res.get("case_id")))
    print("[selfcheck] 契约键回填=%d missing=%s"
          % (len(res.get("output_contract_echo") or {}), miss or []))
    print("[selfcheck] 产物字节=%s" % json.dumps(arts, ensure_ascii=False))
    print("[selfcheck] cards=%d found=%s quote_verified_rate=%s"
          % (len(cards), cov.get("cards_found"), cov.get("quote_verified_rate")))
    if unver:
        print("[selfcheck] 有命中但引文未验证: %s" % unver)
    print("[selfcheck] %s" % ("OK" if not issues else "ISSUES: " + " | ".join(issues)))
    return env


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="search-10 cross-language known-item retrieval: init/show/check/build/selfcheck",
        epilog="Always exits 0; a valid partial result.json is written first.")
    ap.add_argument("cmd", nargs="?", default="init",
                    choices=["init", "show", "check", "build", "selfcheck", "help"])
    ap.add_argument("--input", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--output", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "help":
        ap.print_help()
        return 0
    fn = {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
          "selfcheck": cmd_selfcheck}[a.cmd]
    try:
        fn(a)
    except Exception as e:  # noqa: BLE001 - never crash the harness
        try:
            env = env_of(a)
            st, out = env["st"], env["out"]
            st["errors"].append({"stage": "fatal:%s" % a.cmd,
                                 "message": "%s: %s" % (type(e).__name__, str(e)[:240])})
            st["status"] = "partial"
            st["result"] = st.get("result") or {"answer_cards": [], "view_fingerprints": []}
            save(out, st)
            print("[%s] recovered: %s: %s" % (a.cmd, type(e).__name__, str(e)[:160]))
        except Exception:  # noqa: BLE001
            print("[%s] fatal; could not write partial result either" % a.cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
