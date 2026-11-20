#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py :: five-command entry point for search-coverage-gap-auditor.

  init   -> index materials, freeze reference set, write a legal partial result.json
  show   -> print the material projection (refs / pool / queries with locators)
  check  -> mechanical validation of the agent's draft.json
  build  -> write the six products + finalize result.json (falls back when draft is missing)
  selfcheck -> re-read products, recompute from CSV, compare two runs

Stdlib only. Offline. Exit code always 0.
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit as AB          # noqa: E402
import ledger as LG         # noqa: E402
import render as RD         # noqa: E402
import verify as VF         # noqa: E402

V = "1.0.0"
NAME = "search-coverage-gap-auditor"
ENV_KEYS = {"case_id", "status", "skill", "skill_version", "output_contract_values", "counts", "coverage",
            "gap_summary", "supplement", "sources", "uncertainty", "pending_human", "errors",
            "degradations", "assumptions", "changes", "products", "payload", "runtime"}
T0 = time.time()
PRODUCTS = ("scope_card.md", "hit_ledger.csv", "gap_matrix.csv", "gap_atlas.json",
            "supplement_plan.md", "coverage_report.md", "audit_trail.json")


def ensure_dir(p, alt, notes):
    for cand in (p, Path(alt)):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_probe"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            if cand != p:
                notes["degradations"].append({"stage": "paths", "note": "目录不可写，回退到 %s" % cand})
            return cand
        except Exception as e:
            notes["degradations"].append({"stage": "paths", "target": str(cand), "error": str(e)})
    return Path(".")


def notes_new():
    return {"errors": [], "degradations": [], "assumptions": [], "uncertainty": []}  # 四个记录通道


def jdump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")


def jload(p):
    try:
        return json.loads(Path(p).read_text("utf-8", "replace"))
    except Exception:
        return None


def envelope(contract, cid):
    res = {}
    for k in (contract or {}):
        res[k] = None
    res.update(case_id=cid, status="partial", skill=NAME, skill_version=V,
               output_contract_values={k: {"kind": "null", "provenance": "pending_init",
                                           "note": "init 占位，build 回填"} for k in (contract or {})},
               counts={}, coverage={}, gap_summary={}, supplement={}, sources=[], uncertainty=[],
               pending_human=[], errors=[], degradations=[], assumptions=[], changes=[],
               products={}, payload={}, runtime={})
    return res


def load_state(work):
    st = jload(Path(work) / "state.json")
    return st if isinstance(st, dict) else None


# --------------------------------------------------------------------- bootstrap
def bootstrap(a, args):
    notes = notes_new()
    inp = Path(a.input).expanduser()
    work = ensure_dir(Path(a.work).expanduser(), "./work", notes)
    out = ensure_dir(Path(a.output).expanduser(), "./output", notes)
    cpath, case = LG.find_case(inp, notes["errors"])
    contract = {}
    cid = None
    if isinstance(case, dict):
        contract = case.get("output_contract") if isinstance(case.get("output_contract"), list) else case.get("output_contract")
        if isinstance(contract, dict):
            contract = {str(k): contract[k] for k in contract}
        elif isinstance(contract, list):
            contract = {str(k): None for k in contract}
        else:
            contract = {}
            notes["assumptions"].append({"item": "output_contract", "note": "case.json 未提供 output_contract，产物按本 Skill 固定契约输出"})
        cid = case.get("case_id") or case.get("caseId") or case.get("id")
    # first artefact: a legal partial result.json
    res = envelope(contract, cid)
    jdump(out / "result.json", res)
    st = {"case_id": cid, "contract": contract, "notes": notes,
          "paths": {"input": str(inp), "work": str(work), "output": str(out)},
          "docs_meta": [], "refs": [], "pool": [], "queries": [], "imports": [],
          "auto": {}, "refset_fingerprint": None, "started": T0}
    try:
        docs = LG.discover(inp, notes["errors"])
        st["docs_meta"] = [{"doc_id": d["doc_id"], "path": d["path"], "sha256": d["sha256"],
                            "chars": d["chars"]} for d in docs]
        pool, refrecs = LG.split_records(docs, notes["degradations"])
        refs = LG.collect_refs(refrecs, case, notes["degradations"])
        queries = LG.collect_queries(docs, notes["degradations"])
        imports = LG.collect_imports(docs, notes["degradations"])
        st.update(pool=[{k: p.get(k) for k in ("pool_id", "title", "ntitle", "doi", "pmid", "year",
                                             "first_author", "venue", "container", "doc_id", "locator",
                                             "quote", "also_in", "flags")} for p in pool],
                  refs=refs, queries=queries, imports=imports,
                  refset_fingerprint=LG.fingerprint(refs))
        inv, hot = LG.token_index(pool)
        st["auto"] = {r["ref_id"]: LG.match_ref(r, pool, inv, hot) for r in refs}
        if not docs:
            notes["errors"].append({"stage": "discover", "error": "输入目录下未发现可读材料"})
        if not refs:
            notes["uncertainty"].append("未识别到参考集：覆盖率分母未定义，不以检索结果反推分母")
        if not queries:
            notes["degradations"].append({"stage": "queries", "note": "未识别查询日志：漏检归因无法定位到具体查询式"})
    except Exception as e:
        notes["errors"].append({"stage": "init", "error": "%s: %s" % (type(e).__name__, e),
                                "trace": traceback.format_exc(limit=2)})
    jdump(Path(work) / "state.json", st)
    return st, out, work, inp


def need_state(a):
    st = load_state(a.work)
    if st:
        return st, Path(st["paths"]["output"]), Path(st["paths"]["input"])
    st, out, work, inp = bootstrap(a, None)
    return st, out, inp


def cmd_init(a):
    st, out, work, inp = bootstrap(a, None)
    n = st["notes"]
    cov = AB.coverage(st["refs"], AB.build_rows(st["refs"], st.get("auto") or {}, {}), "all") if st["refs"] else None
    print("[init] input=%s work=%s output=%s" % (inp, work, out))
    print("[init] case_id=%s contract_keys=%d docs=%d refs=%d pool=%d queries=%d imports=%d fingerprint=%s"
          % (st["case_id"], len(st["contract"]), len(st["docs_meta"]), len(st["refs"]),
             len(st["pool"]), len(st["queries"]), len(st["imports"]), st.get("refset_fingerprint")))
    if not st["refs"]:
        print("[init] WARN 未识别参考集：覆盖率分母未定义（不虚构分母）")
    print("[init] 合法 partial result.json 已写入 %s/result.json（%d 契约键）"
          % (out, len(st["contract"])))
    print("[init] 下一步: show → 读材料 → 写 %s/draft.json → check → build" % work)
    return 0


# ------------------------------------------------------------------------- show
def cmd_show(a):
    st, out, inp = need_state(a)
    lim = max(1, int(a.limit or 12))
    sec = a.section or "all"
    auto = st.get("auto") or {}
    if sec in ("all", "materials"):
        print("== materials (%d) ==" % len(st["docs_meta"]))
        for m in st["docs_meta"]:
            print("  %s  %-38s %7dB  sha=%s" % (m["doc_id"], m["path"], m["chars"], (m["sha256"] or "")[:12]))
        if not st["docs_meta"]:
            print("  (none)")
        print()
    if sec in ("all", "refs"):
        print("== reference set (%d)  fingerprint=%s ==" % (len(st["refs"]), st.get("refset_fingerprint")))
        print("  列: ref_id 年份 [可用性] 题名 | doi | locator")
        shown = [x for x in st["refs"] if a.ref is None or x["ref_id"].lower() == str(a.ref).lower()]
        for r in (shown if a.ref is not None else shown[:lim]):
            print("  %s %s [%s] %s" % (r["ref_id"], r.get("year") or "----",
                                       r["usability_reason"], LG.clip(r.get("title"), 110)))
            print("        doi=%s  loc=%s" % (r.get("doi") or "-", r.get("locator") or "-"))
            h = auto.get(r["ref_id"]) or {}
            print("        auto-match: %s rule=%s cert=%s sim=%s" % (h.get("pool_id") or "none", h.get("rule"),
                                                                     h.get("certainty"), h.get("similarity")))
            if r.get("dups"):
                print("        duplicates: %d" % len(r["dups"]))
        if len(shown) > lim and a.ref is None:
            print("  ... 仅显示前 %d 条（--limit N 调整）" % lim)
        print()
    if sec in ("all", "pool"):
        print("== retrieved record pool (%d, 去重后) ==" % len(st["pool"]))
        for p in st["pool"][:lim]:
            print("  %s %-10s %s %s | %s" % (p["pool_id"], p.get("container"), p.get("year") or "----",
                                             LG.clip(p.get("title"), 90), p.get("locator")))
        if len(st["pool"]) > lim:
            print("  ... 共 %d 条，仅显示前 %d（--limit N）" % (len(st["pool"]), lim))
        print()
    if sec in ("all", "queries"):
        print("== query log (%d) ==" % len(st["queries"]))
        for q in st["queries"][:lim]:
            print("  %s fields=%s source=%s window=%s-%s iter=%s  %s" % (
                q["q_id"], q.get("fields") or "-", q.get("source") or "-", q.get("year_from") or "…",
                q.get("year_to") or "…", q.get("iteration") or "-", q.get("locator")))
            print('        "%s"' % LG.clip(q.get("query"), 160))
        if len(st["queries"]) > lim:
            print("  ... 共 %d 条（--limit N）" % len(st["queries"]))
        print()
    if sec in ("all", "sources"):
        print("== import state / incremental (%d) ==" % len(st["imports"]))
        for i in st["imports"][:lim]:
            print("  %s %s %s" % (i.get("source"), i.get("ptr"), i.get("values")))
        print()
    if sec == "all":
        print("== 未命中条目的脚本候选归因（你需要在 draft.gap_notes 里确认或改判） ==")
        rows = AB.build_rows(st["refs"], auto, {})
        cx = AB.qctx(st["queries"])
        k = 0
        for r in rows:
            if r["hit_status"] != "miss":
                continue
            ref = [x for x in st["refs"] if x["ref_id"] == r["ref_id"]][0]
            g = AB.auto_gap(ref, r, cx)
            print("  %s → %s (%s)  %s" % (r["ref_id"], g["category"], g["why"], LG.clip(g["verdict"], 110)))
            k += 1
            if k >= lim:
                break
        if not k:
            print("  (无未命中条目，或参考集为空)")
        print()
        print("== 下一步 ==")
        print("  1) 逐条核对上面的自动匹配（尤其 certainty=low / rule=bib_borderline）")
        print("  2) 写 %s/draft.json（schema: SKILL.md §6, 字段字典: references/draft-and-fields.md）" % st["paths"]["work"])
        print("  3) python3 scripts/main.py check → 按 FAIL 修 → python3 scripts/main.py build")
    return 0


# ------------------------------------------------------------------------ check
def cmd_build(a):
    st, out, inp = need_state(a)
    work = Path(st["paths"]["work"])
    notes = st["notes"]
    draft = {} if a.no_draft else (jload(work / "draft.json") or {})
    have_draft = isinstance(draft, dict) and bool(draft)
    if not have_draft:
        notes["degradations"].append({"stage": "draft", "note": "工作稿缺失：全部判断按脚本规则自动填补，"
                                                                  "ledger 中 decision_source=auto，status 降为 partial"})
    policy = VF.policy_of(st, draft, a.policy)
    c = VF.compute(st, draft, policy)
    cov, rows, gaps, clusters, sup = c["cov"], c["rows"], c["gaps"], c["clusters"], c["sup"]
    qs = VF.quote_stats(st, inp, c)
    st["policy_reason"] = ((draft.get("scope") or {}).get("notes") if isinstance(draft.get("scope"), dict) else "") or ""
    st["research_question"] = draft.get("research_question") or ""
    st["gaps"] = gaps
    st["out_dir"] = str(out)
    st["uncertainty"] = list(notes["uncertainty"])
    for x in (draft.get("conflicts") or []):
        if isinstance(x, dict):
            notes["uncertainty"].append("冲突: %s %s" % (x.get("item"), x.get("detail")))
    if st.get("imports"):
        notes["assumptions"].append({"item": "import_state", "note": "材料含增量导入状态 %d 条，仅作来源完整性线索，未用于覆盖率分母"
                                     % len(st["imports"])})

    # ---- products
    try:
        (out / "scope_card.md").write_text(RD.scope_card(st, cov, c["variants"], rows, c["cx"]), encoding="utf-8")
        (out / "hit_ledger.csv") and LG.wcsv(out / "hit_ledger.csv", rows, LG.LEDGER_COLS)
        mx = []
        for g in gaps:
            for rid in g["ref_ids"]:
                mx.append({"ref_id": rid, "title": LG.clip(next((x.get("title") for x in st["refs"] if x["ref_id"] == rid), ""), 120), "primary_category": g["category"],
                           "co_factors": ";".join(g.get("co_factors") or []), "why": g["why"],
                           "fixability": AB.FIXTXT.get(g["why"], g["why"]),
                           "affected_query_ids": ";".join(g["affected_query_ids"]),
                           "action": LG.clip(g.get("verdict"), 160),
                           "evidence_locator": (g["evidence"][0]["locator"] if g["evidence"] else "")})
        LG.wcsv(out / "gap_matrix.csv", mx, LG.MATRIX_COLS)
        jdump(out / "gap_atlas.json", RD.gap_atlas(st, cov, gaps, clusters, cov["missed_ids"]))
        (out / "supplement_plan.md").write_text(RD.supplement_md(st, cov, sup, clusters), encoding="utf-8")
        (out / "coverage_report.md").write_text(RD.report_md(st, cov, c["variants"], rows, gaps, clusters, sup), encoding="utf-8")
        jdump(out / "audit_trail.json", AB.audit_trail(st, cov, c["variants"], gaps, clusters, sup, rows, draft, qs))
    except Exception as e:
        notes["errors"].append({"stage": "products", "error": "%s: %s" % (type(e).__name__, e),
                                "trace": traceback.format_exc(limit=3)})
        for n in PRODUCTS:
            if not (out / n).exists():
                try:
                    (out / n).write_text(json.dumps({"error": "product failed", "detail": str(e)}, ensure_ascii=False) if n.endswith(".json") else "# 产物生成失败: %s\n" % e, encoding="utf-8")
                except Exception:
                    pass

    if qs["missing"]:
        notes["degradations"].append({"stage": "quote", "note": "%d 条证据 quote 未能在源文件中逐字命中，已标记待核" % qs["missing"]})
    prods = {}
    for n in PRODUCTS:
        p = out / n
        if p.exists():
            b = p.read_bytes()
            prods[n] = {"path": n, "bytes": len(b), "sha256": LG.sha(b.decode("utf-8", "replace"))[:16]}
    if not st["refs"]:
        status = "insufficient_evidence"
    elif not st["docs_meta"]:
        status = "input_error"
    else:
        agent_cov = (len([r for r in rows if r["decision_source"] == "agent"]) / max(1, len(rows)))
        status = "ok" if (have_draft and agent_cov >= 0.8 and not qs["missing"] and cov["denominator"]) else "partial"

    pending = [{"item": r["ref_id"], "note": "命中判定待人工裁决（certainty=%s, rule=%s）" % (r["certainty"], r["match_rule"])}
               for r in rows if r["needs_human"]][:20]
    if qs["missing"]:
        pending.append({"item": "evidence_quote", "note": "%d 条证据 quote 未逐字命中，需核对 locator" % qs["missing"]})
    if not st["refs"]:
        pending.append({"item": "reference_set", "note": "未识别参考集：请提供参考集/专家清单文件后重跑 init"})
    if not have_draft:
        pending.append({"item": "draft", "note": "工作稿缺失：请按 SKILL.md §6 写 draft.json 后重跑 check/build 提升档位"})

    ctx = {"cov": cov, "clusters": clusters, "sup": sup, "refs": st["refs"]}
    cvals, cmeta = AB.contract_values(st.get("contract") or {}, ctx)
    unmapped = [k for k, v in cvals.items() if v is None]
    if unmapped:
        notes["assumptions"].append({"item": "output_contract", "note": "以下契约键无法映射到本 Skill 产物，保留 null：%s" % unmapped})

    res = envelope(st.get("contract") or {}, st.get("case_id"))
    res.update(status=status,
               output_contract_values={k: dict(v, value=cvals.get(k)) for k, v in cmeta.items()},
               counts={"refs": len(st["refs"]), "refs_unusable": sum(1 for r in st["refs"] if not r["usable"]),
                       "duplicates_merged": cov["duplicates_merged"], "pool_records": len(st["pool"]),
                       "queries": len(st["queries"]), "documents": len(st["docs_meta"]),
                       "denominator": cov["denominator"], "hit": cov["numerator"], "miss": cov["miss_count"],
                       "pending": cov["pending_count"], "gap_clusters": len(clusters),
                       "decisions_agent": len([r for r in rows if r["decision_source"] == "agent"]),
                       "decisions_auto": len([r for r in rows if r["decision_source"] == "auto"])},
               coverage={"policy": cov["policy"], "coverage": cov["coverage"], "miss_rate": cov["miss_rate"],
                         "denominator": cov["denominator"], "numerator": cov["numerator"],
                         "denominator_ids": cov["denominator_ids"], "numerator_ids": cov["numerator_ids"],
                         "missed_ids": cov["missed_ids"], "excluded": cov["excluded"],
                         "variants": {k: {"denominator": v["denominator"], "numerator": v["numerator"],
                                          "coverage": v["coverage"]} for k, v in c["variants"].items()},
                         "by_source": AB.coverage_by_source(rows, st["pool"]),
                         "refset_fingerprint": st.get("refset_fingerprint")},
               gap_summary={"miss_count": cov["miss_count"],
                            "categories": {x["category"]: x["count"] for x in clusters},
                            "residual": sup["residual_count"], "uncovered": [x for x in cov["missed_ids"]
                                                                             if x not in {y for g in gaps for y in g["ref_ids"]}]},
               supplement={"queries": sup["queries"], "new_hits": sup["total_new_hits"],
                           "marginal_yield": sup["marginal_yield"], "coverage_before": sup["coverage_before"],
                           "coverage_after": sup["coverage_after"], "residual": sup["residual_count"],
                           "stop_reason": sup["stop_reason"], "no_gain_queries": sup["no_gain_queries"],
                           "redundant_queries": sup["redundant_queries"]},
               sources=[{"doc_id": m["doc_id"], "path": m["path"], "sha256": m["sha256"], "chars": m["chars"]}
                        for m in st["docs_meta"]],
               uncertainty=notes["uncertainty"][:30],
               pending_human=pending,
               errors=notes["errors"], degradations=notes["degradations"], assumptions=notes["assumptions"],
               changes=[{"target": "products", "action": "generated", "detail": "%d 件套由 build 生成" % len(prods)}],
               products=prods,
               payload={"reference_set": [{"ref_id": r["ref_id"], "title": r.get("title"), "doi": r.get("doi"),
                                           "year": r.get("year"), "usable": bool(r["usable"]),
                                           "flags": r.get("flags")} for r in st["refs"]][:300],
                        "ledger": rows[:300], "gap_clusters": clusters,
                        "supplement_rows": sup["rows"], "quote_verbatim": qs,
                        "logic": {"hit_rules": ["id_doi", "id_pmid", "bib_title_author_year", "bib_title_year",
                                                "bib_borderline", "none"],
                                  "categories": list(AB.CATS), "whys": list(AB.WHYS),
                                  "stop_rule": "marginal_yield <= 0.5 条/查询 或 剩余遗漏全为 needs_new_source/data_defect"}},
               runtime={"elapsed_s": round(time.time() - T0, 2), "python": sys.version.split()[0],
                        "skill_version": V, "llm_requests": 0, "deterministic": True,
                        "budget_note": "确定性计算；模型预算用于阅读材料与撰写 draft.json"})
    for k in (st.get("contract") or {}):
        if k in ENV_KEYS:
            continue        # envelope keeps its own meaning; the contract value stays in output_contract_values
        res[k] = cvals.get(k)
    res["case_id"] = st.get("case_id")
    jdump(out / "result.json", res)
    print("[build] status=%s policy=%s 分母=%d 命中=%d 遗漏=%d 覆盖率=%s 补检=%d(+%d) 残余=%d"
          % (status, cov["policy"], cov["denominator"], cov["numerator"], cov["miss_count"], cov["coverage"],
             sup["queries"], sup["total_new_hits"], sup["residual_count"]))
    print("[build] 类别: %s" % ({x["category"]: x["count"] for x in clusters} or "无"))
    print("[build] 决策来源: agent=%d auto=%d  证据逐字命中 %d/%d"
          % (len([r for r in rows if r["decision_source"] == "agent"]),
             len([r for r in rows if r["decision_source"] == "auto"]), qs["found"], qs["checked"]))
    print("[build] 产物 %d/%d: %s" % (len(prods), len(PRODUCTS), ", ".join(sorted(prods))))
    if status != "ok":
        print("[build] 提示: %s —— 见 degradations/pending_human" % status)
    return 0


# -------------------------------------------------------------------- selfcheck
# ------------------------------------------------------------------------- main
def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="检索覆盖率与遗漏分析审计器（五命令）")
    ap.add_argument("cmd", nargs="?", default="init",
                    choices=["init", "show", "check", "build", "selfcheck", "help"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--section", default="all", choices=["all", "materials", "refs", "pool", "queries", "sources"])
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--ref", default=None)
    ap.add_argument("--policy", default=None, choices=list(AB.POLICIES))
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-draft", action="store_true")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "help":
        build_parser().print_help()
        return 0
    try:
        if a.cmd in ("check", "selfcheck"):
            st, out, inp = need_state(a)
            return VF.cmd_check(a, st, out, inp) if a.cmd == "check" else VF.cmd_selfcheck(a, st, out, inp)
        return {"init": cmd_init, "show": cmd_show, "build": cmd_build}[a.cmd](a)
    except Exception as e:
        print("[error] %s: %s" % (type(e).__name__, e))
        traceback.print_exc(limit=3)
        try:
            out = Path(a.output)
            out.mkdir(parents=True, exist_ok=True)
            res = jload(out / "result.json") or envelope({}, None)
            res.update(status="partial", errors=(res.get("errors") or []) + [
                {"stage": a.cmd, "error": "%s: %s" % (type(e).__name__, e)}])
            res["runtime"] = dict(res.get("runtime") or {}, elapsed_s=round(time.time() - T0, 2), python=sys.version.split()[0])
            jdump(out / "result.json", res)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:                     # never crash the harness
        try:
            o = Path("/app/output")
            o.mkdir(parents=True, exist_ok=True)
            jdump(o / "result.json", {"case_id": None, "status": "partial", "skill": NAME, "skill_version": V,
                                      "errors": [{"stage": "fatal", "error": str(e)}],
                                      "degradations": [{"stage": "fatal", "note": "顶层异常兜底"}],
                                      "products": {}, "runtime": {"elapsed_s": round(time.time() - T0, 2)}})
        except Exception:
            pass
        sys.exit(0)
