#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-topic-gatekeeper：init / show / check / build / selfcheck。
纯标准库、离线、不依赖 CWD；退出码恒 0；先写合法 partial result.json，再增量改进，最后无条件 finalize。"""
import argparse, json, os, re, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gates as G        # noqa: E402
import render as R       # noqa: E402
import indexer as X      # noqa: E402

V, T0 = "1.0.0", time.time()
now, gk, scan = X.now, X.gk, X.scan

# output_contract 字段 → 业务槽位的语义映射（顺序即优先级）
MAP = ((("overall", "decision", "verdict", "go_no_go", "conclusion"), "decision"),
       (("gate", "scorecard"), "gates"),
       (("prior", "align", "compar", "matrix"), "prior_art_rows"),
       (("novel", "innovat", "original"), "novelty"),
       (("feasib", "assumption", "premise", "constraint", "risk"), "assumptions"),
       (("gap", "blank", "white_space"), "research_gap"),
       (("conflict", "contradict", "counter"), "conflicts"),
       (("search", "query", "screen", "inclusion", "retriev", "protocol"), "search_protocol"),
       (("question", "hypothes", "problem", "testable", "statement"), "question"),
       (("sources", "bibliograph", "references"), "sources"),
       (("evidence", "citation", "quote", "locator", "provenance", "backlink"), "evidence"),
       (("uncertain", "limitation", "caveat", "unknown"), "uncertainties"),
       (("coverage", "stat", "count"), "coverage"),
       (("deliver", "artifact", "output", "brief", "report", "file", "path"), "deliverable"),
       (("change", "revision", "log"), "change_log"),
       (("status",), "status"),
       (("case",), "case_id"),
       (("summary", "synthesis", "recommend", "answer"), "decision_summary"))


def fill_contract(contract, payload):
    out = {}
    for k in (contract or {}):
        lk = str(k).lower()
        val = payload.get(lk)
        if val is None:
            for kws, slot in MAP:
                if any(w in lk for w in kws):
                    val = payload.get(slot)
                    break
        out[k] = [] if val is None else val
    return out


def empty_base(case, contract, status="partial"):
    r = {"case_id": gk(case, "case_id", "id", "caseId", "challenge_id"), "status": status,
         "skill": "research-topic-gatekeeper", "skill_version": V, "note": ""}
    r.update({k: None for k in contract})
    r.update({"decision": None, "gates": [], "prior_art_rows": [], "novelty": [], "assumptions": [], "claims": [],
              "conflicts": [], "research_gap": None, "search_protocol": None, "question": None, "coverage": {},
              "sources": [], "uncertainties": [], "errors": [], "degradations": [], "change_log": [],
              "artifacts": {}, "runtime": {}})
    return r


def finalize(outdir, res, contract):
    try:
        payload = dict(res)
        filled = fill_contract(contract, payload)
        out = {k: res.get(k) for k in ("case_id", "status", "skill", "skill_version", "note")}
        for k, v in filled.items():
            out[k] = v
        for k, v in res.items():
            out.setdefault(k, v)
        out["output_contract"] = filled
        out["contract_keys"] = list(contract or {})
        out["runtime"] = dict(res.get("runtime") or {}, elapsed_s=round(time.time() - T0, 2),
                              python=sys.version.split()[0], finished_at=now(), skill_version=V)
        G.dump_json(Path(outdir) / "result.json", out)
    except Exception as e:
        try:
            G.dump_json(Path(outdir) / "result.json",
                        {"case_id": None, "status": "failed", "output_contract": {k: None for k in (contract or {})},
                         "errors": ["finalize: %s: %s" % (type(e).__name__, e)]})
        except Exception:
            pass


def rdirs(a):
    ind = Path(a.input)
    if not ind.exists() and Path("input").exists():
        ind = Path("input")
    out, work = Path(a.output), Path(a.work)
    for d in (out, work):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    if not os.access(str(out), os.W_OK):
        out = Path.cwd() / "output"
        out.mkdir(parents=True, exist_ok=True)
    if not os.access(str(work), os.W_OK):
        work = Path.cwd() / "work"
        work.mkdir(parents=True, exist_ok=True)
    return ind, out, work


def print_objects(ix, limit=30):
    c = ix["counts"]
    print("对象表：sources %d ｜ records %d（解析 %d / 未解析 %d / 重复 %d）｜ constraints %d ｜ 内联摘要 %d"
          % (c["sources"], c["records"], c["records_resolved"], c["records_unresolved"], c["duplicate_records"],
             c["constraints"], c["inline_texts"]))
    for s in ix["objects"]["sources"][:limit]:
        print("  %-5s %-38s 材料 %-4s 别名 %-18s 版本 %s"
              % (s["sid"], (s["title"] or s["doi"] or "—")[:38], s["material"] or "—",
                 "、".join(s["aliases"])[:18] or "—", s["version_flag"] or "—"))
    for r in ix["objects"]["records"][:limit]:
        st = "重复于 %s" % r["duplicate_of"] if r["duplicate_of"] else ("→ %s" % r["sid"] if r["sid"] else "未解析")
        print("  %-5s ref=%-14s %-16s %s" % (r["rid"], (r["raw_ref"] or "—")[:14], st, (r["note"] or "")[:40]))
    if ix["unresolved_records"]:
        print("  ! 未解析记录：%s（需人工确认，不得臆测归属）"
              % "、".join(x["rid"] + "=" + (x["raw_ref"] or "?") for x in ix["unresolved_records"][:6]))
    if ix["version_notes"]:
        print("  ! 版本/行政说明 %d 条（去重与覆盖判定必须考虑）：" % len(ix["version_notes"]))
        for v in ix["version_notes"][:5]:
            print("    %s %s [%s] %s" % (v["kind"], v["id"], v["flag"], (v["quote"] or "")[:80]))


def load_index(ind, work):
    ix, err = G.load_json(work / "index.json")
    if isinstance(ix, dict) and isinstance(ix.get("materials"), list):
        return ix, None
    case, cpath, _ = X.find_case(ind)
    ix = X.build_index(ind, cpath, case)
    G.dump_json(work / "index.json", ix)
    return ix, err


def cmd_init(a):
    ind, out, work = rdirs(a)
    case, cpath, cerr = X.find_case(ind)
    contract = X.contract_of(case)
    res = empty_base(case, contract, "partial")
    res["note"] = "init：索引已建，等待 Agent 写工作稿"
    if cerr:
        res["errors"].append(cerr)
        res["degradations"].append("case.json 不可用：仅按材料运行，契约字段按默认命名")
    finalize(out, res, contract)                      # ① 先落合法 partial
    ix = X.build_index(ind, cpath, case)
    G.dump_json(work / "index.json", ix)
    print("== init v%s == 输入 %s ｜ case %s ｜ task.md %s"
          % (V, ind, cpath or "缺", next((p.name for p in scan(ind) if p.name.lower() == "task.md"), "缺")))
    print("契约字段 %d 个：%s" % (len(contract), "、".join(list(contract)[:12]) or "（output_contract 缺失）"))
    ti = gk(case, "task_instruction", "instruction", "task", "question", "research_question")
    if ti:
        print("任务指令：%s" % (ti if isinstance(ti, str) else json.dumps(ti, ensure_ascii=False))[:600])
    print("材料 %d 份（可读 %d，共 %d 字符）" % (ix["counts"]["materials"], ix["counts"]["readable"], ix["total_chars"]))
    for m in ix["materials"]:
        print("  %-4s %-42s %-11s %-5s %7d字 %3d段 %s"
              % (m["id"], m["rel"][:42], m["role"], m["kind"], m["chars"], len(m["paras"]), m["extract"]))
    if ix["extract_notes"]:
        print("  解析降级：%s" % "；".join("%s(%s)" % (n["material"], n["note"]) for n in ix["extract_notes"][:5]))
    print_objects(ix)
    print("NEXT: python3 scripts/main.py show  → 读材料判读  → 写 %s/draft.json  → check  → build" % work)
    return 0


def cmd_show(a):
    ind, out, work = rdirs(a)
    ix, err = load_index(ind, work)
    if err:
        print("（索引缺失或损坏 %s，已重建）" % err)
    if a.grep:
        pat, n = re.compile(a.grep, re.I), 0
        for m in ix["materials"]:
            for pa in m["paras"]:
                if pat.search(pa["text"]):
                    print("\n[%s/%s] %s\n%s" % (m["id"], pa["loc"], m["rel"], G.norm(pa["text"])[:900]))
                    n += 1
                    if n >= a.limit:
                        return 0
        for o in ix["object_texts"]:
            if pat.search(o["text"]):
                print("\n[%s/%s] 内联文本\n%s" % (o["id"], o["locator"], G.norm(o["text"])[:900]))
                n += 1
                if n >= a.limit:
                    return 0
        print("（%d 条命中）" % n if n else "未命中 %r：换关键词；空检索只能记为“未覆盖”，不得写成“无人研究”" % a.grep)
        return 0
    if a.id:
        gid = a.id.upper()
        src = next((s for s in ix["objects"]["sources"] if s["sid"].upper() == gid), None)
        mat = next((m for m in ix["materials"] if m["id"].upper() == gid), None)
        ot = [o for o in ix["object_texts"] if o["id"].upper() == gid]
        if not (src or mat or ot):
            print("未知编号 %s。可用：%s" % (a.id, "、".join([m["id"] for m in ix["materials"]]
                                                         + [s["sid"] for s in ix["objects"]["sources"]])))
            return 0
        if src:
            print("== %s | %s | doi %s | 别名 %s | 版本标记 %s =="
                  % (src["sid"], src["title"] or "—", src["doi"] or "—", "、".join(src["aliases"]) or "—",
                     src["version_flag"] or "—"))
            if src["note"]:
                print("行政/版本说明：%s" % src["note"][:300])
            if not mat and src.get("material"):
                mat = next((m for m in ix["materials"] if m["id"] == src["material"]), None)
        for o in ot:
            print("\n[%s/%s]\n%s" % (o["id"], o["locator"], G.norm(o["text"])[:2000]))
        if mat:
            print("== %s | %s | %s | %d 字 ==" % (mat["id"], mat["rel"], mat["extract"], mat["chars"]))
            for pa in mat["paras"][:a.limit]:
                print("\n[%s/%s]\n%s" % (mat["id"], pa["loc"], G.norm(pa["text"])[:1200]))
        return 0
    print_objects(ix)
    print("\n用法：show --id M2 ｜ show --grep 关键词 ｜ 引用写 \"quote\": 逐字原文, \"locator\": \"M2/p3\"")
    return 0


def _print_rep(rep):
    c = rep["counts"]
    print("五门 %d/5 ｜ 矩阵 %d 行 ｜ 创新 %d ｜ 前提 %d ｜ 冲突 %d ｜ 证据 %d/%d 逐字命中 ｜ 六类 %d/6 ｜ ERROR %d WARN %d"
          % (c["gates_present"], c["matrix_rows"], c["novelty"], c["assumptions"], c["conflicts"],
             c["evidence_verified"], c["evidence_total"], c["six_passed"], c["errors"], c["warnings"]))
    for e in rep["errors"][:20]:
        print("ERROR %-22s %s" % (e["code"], e["msg"]))
    for w in rep["warnings"][:12]:
        print("WARN  %-22s %s" % (w["code"], w["msg"]))
    print("六类：%s" % " ｜ ".join("%s=%s" % (k, "Y" if v else "N") for k, v in rep["coverage"]["six_checks"].items()))


def cmd_check(a):
    ind, out, work = rdirs(a)
    ix, _ = load_index(ind, work)
    case, cpath, _ = X.find_case(ind)
    draft, dpath, derr = G.load_draft(work)
    if not draft:
        rep = G.check(G.fallback_draft(ix, gk(case, "case_id", "id", default=None), derr or ""), ix)
        G.dump_json(work / "check_report.json",
                    {"draft_path": dpath, "draft_error": derr, "checked": "fallback_preview", "report": rep})
        print("== check == 工作稿：%s（%s）" % (dpath or "无", derr or ""))
        print("→ 当前只校验了兜底骨架，不是答案。**脚本不会代替你阅读理解；必须先读材料、写工作稿，再运行 build。**")
        _print_rep(rep)
        return 0
    rep = G.check(draft, ix)
    G.dump_json(work / "check_report.json", {"draft_path": dpath, "draft_error": derr, "report": rep})
    print("== check == 工作稿 %s %s" % (dpath, derr or ""))
    _print_rep(rep)
    print("NEXT: 修完 ERROR 后 python3 scripts/main.py build")
    return 0


def cmd_build(a):
    ind, out, work = rdirs(a)
    case, cpath, cerr = X.find_case(ind)
    contract = X.contract_of(case)
    res = empty_base(case, contract, "partial")
    res["note"] = "build"
    finalize(out, res, contract)                      # 任何异常前先有合法 partial
    try:
        ix, _ = load_index(ind, work)
        draft, dpath, derr = G.load_draft(work)
        if cerr:
            res["errors"].append(cerr)
        cid = gk(case, "case_id", "id", default=None)
        fb = G.fallback_draft(ix, cid, derr or "")
        src = "agent"
        if not draft:
            draft, src = fb, "fallback"
            res["degradations"].append("无工作稿：使用兜底骨架（%s）" % (derr or ""))
        elif draft.get("_from_md") or draft.get("_md_sections"):
            draft, src = fb, "fallback"
            res["degradations"].append("仅发现 draft.md 叙事稿：结构化字段用兜底补齐")
        elif derr:
            res["degradations"].append("工作稿解析问题：%s" % derr)
        draft, fixed = G.merge(draft, fb)
        if fixed:
            res["degradations"].append("字段兜底补齐：%s" % "、".join(fixed[:10]))
            if src == "agent":
                src = "agent+fallback"
        G.dump_json(work / "draft.effective.json", draft)
        rep = G.check(draft, ix)
        ratio = rep["coverage"]["evidence_hit_rate"]
        if not ix.get("materials"):
            status = "failed"
            res["degradations"].append("无输入材料")
        elif not ix["counts"]["readable"]:
            status = "partial"
            res["degradations"].append("材料无可解析文本（图片/无文本层 PDF）")
        elif src != "agent" or rep["errors"] or ratio < 0.8:
            status = "partial"
        else:
            status = "ok"
        ctx = {"case_id": cid, "status": status, "draft_source": src, "now": now(),
               "n_materials": ix["counts"]["materials"], "case_title": gk(case, "title", "case_title", "name"),
               "sources": ix["objects"]["sources"], "uncertainties": []}
        for u in ([{"item": "未解析记录 %d 条" % ix["counts"]["records_unresolved"],
                    "why": "别名/编号在对象表内找不到对应来源", "effect": "这些记录未参与覆盖判定"}]
                  if ix["counts"]["records_unresolved"] else []) + \
                 ([{"item": "版本/行政说明 %d 条" % ix["counts"]["version_notes"],
                    "why": "同一工作的 v1/v2、勘误或预印本可能被当作两份文献", "effect": "去重见 duplicate_records"}]
                  if ix["counts"]["version_notes"] else []) + \
                 ([{"item": "证据逐字命中率 %.0f%%" % (ratio * 100), "why": "部分 quote 改写/跨段/编号错",
                    "effect": "仅命中条目可作证据"}] if ratio < 1 else []):
            ctx["uncertainties"].append(u)
        if status == "failed":
            draft["decision"] = {"overall": None, "conditions": [],
                                 "summary": "输入为空：未形成任何判定；仅保留索引骨架与契约字段，需补齐输入后重跑。",
                                 "next_validation": []}
        files = R.write_all(out, draft, ctx, rep)
        res.update(R.pack(draft, rep, ix, cid, status, src, files))
        res["uncertainties"] = ctx["uncertainties"]
        res["errors"] += [e["code"] + ": " + e["msg"] for e in rep["errors"]]
        res["degradations"] += [w["code"] + ": " + w["msg"] for w in rep["warnings"][:6]]
        print("== build == status=%s ｜ 来源=%s ｜ decision=%s ｜ 五门 %d/5 ｜ 矩阵 %d 行 ｜ 证据 %d/%d ｜ 六类 %d/6"
              % (status, src, res["decision"]["overall"], rep["counts"]["gates_present"], rep["counts"]["matrix_rows"],
                 rep["counts"]["evidence_verified"], rep["counts"]["evidence_total"], rep["counts"]["six_passed"]))
        for f in sorted(files):
            print("  %-32s %7d B" % (f, files[f]))
        for d in res["degradations"][:6]:
            print("DEGRADE " + str(d)[:150])
        for e in res["errors"][:6]:
            print("ERROR   " + str(e)[:150])
    except Exception as e:
        res["errors"].append("build: %s: %s" % (type(e).__name__, e))
        print("build degraded: %s" % e)
    finally:
        try:
            if not (out / "decision_brief.md").is_file():
                (out / "decision_brief.md").write_text(
                    "# 决策简报（兜底骨架）\n\n索引已建，但未能成稿；缺口见 result.json 的 errors/degradations。\n",
                    encoding="utf-8")
                res["degradations"].append("decision_brief.md 为占位骨架")
        except Exception:
            pass
        finalize(out, res, contract)
        print("result.json 已 finalize（契约 %d 字段全部回填）" % len(contract))
    return 0


def cmd_selfcheck(a):
    ind, out, work = rdirs(a)
    rj, err = G.load_json(out / "result.json")
    ix, _ = load_index(ind, work)
    contract = X.contract_of(X.find_case(ind)[0])
    need = list(contract) or ["case_id", "status"]
    fails, rj = [], rj if isinstance(rj, dict) else {}
    if not rj:
        fails.append("result.json 不可读：%s" % err)
    missing = [k for k in need if k not in rj]
    art = rj.get("artifacts") or {}
    live = {p.name: p.stat().st_size for p in out.iterdir() if p.is_file()} if out.is_dir() else {}
    evs = []
    try:
        for line in (out / "evidence_index.jsonl").read_text(encoding="utf-8").split("\n"):
            if G.norm(line):
                evs.append(json.loads(line))
    except Exception:
        pass
    hit = sum(1 for e in evs if e.get("status") == "verified")
    ratio = round(hit / len(evs), 3) if evs else 0.0
    checks = {"contract_keys_complete": not missing, "status_present": bool(G.norm(rj.get("status"))),
              "artifacts_nonempty": bool(art) and all(live.get(k, 0) > 0 for k in art),
              "gates_five": len(G.dicts(rj.get("gates"))) == 5,
              "evidence_verified_ratio": ratio,
              "status_honest": not (rj.get("status") == "ok" and (rj.get("errors") or ratio < 0.8)),
              "no_leftover_placeholder": "TODO_PLACEHOLDER" not in json.dumps(rj, ensure_ascii=False)[:4000]}
    if missing:
        fails.append("契约缺键：%s" % "、".join(missing[:8]))
    if not checks["artifacts_nonempty"]:
        fails.append("产物缺失或为空：%s" % "、".join([k for k in art if live.get(k, 0) <= 0][:6] or ["artifacts 为空"]))
    if not checks["status_honest"]:
        fails.append("status=ok 但有错误或证据命中率不足，应降为 partial")
    for k in ("contract_keys_complete", "status_present", "gates_five", "no_leftover_placeholder"):
        if not checks[k]:
            fails.append("检查未通过：%s" % k)
    sc = {"skill_version": V, "checked_at": now(), "overall_pass": not fails, "checks": checks,
          "failures": fails, "live_files": live, "evidence_rows": len(evs), "evidence_verified": hit,
          "index_counts": ix.get("counts", {})}
    G.dump_json(out / "self_check.json", sc)
    if rj:
        rj["self_check"] = {"overall_pass": sc["overall_pass"], "checks": checks, "failures": fails}
        G.dump_json(out / "result.json", rj)
    print("== selfcheck == 契约键 %d ｜ 产物 %d ｜ 证据 %d/%d ｜ 五门 %s ｜ %s"
          % (len(need), len(art), hit, len(evs), "OK" if checks["gates_five"] else "缺",
             "PASS" if sc["overall_pass"] else "FAIL"))
    for f in fails[:8]:
        print("  ! " + f)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="research-topic-gatekeeper：五门 gate 决策简报")
    sub = ap.add_subparsers(dest="cmd")
    for name, hlp in (("init", "建索引与对象表，先写合法 partial result.json"),
                      ("show", "打印带 locator 的原文 / 对象表，供逐字引用"),
                      ("check", "机械校验工作稿：五门/矩阵/证据命中/契约"),
                      ("build", "生成主产物与最终 result.json（无条件 finalize）"),
                      ("selfcheck", "复检产物与契约完整性")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("--input", default=os.environ.get("INPUT_DIR", "/input"))
        p.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "/app/output"))
        p.add_argument("--work", default=os.environ.get("WORK_DIR", "/app/work"))
        if name == "show":
            p.add_argument("--id", default=None)
            p.add_argument("--grep", default=None)
            p.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        ap.print_help()
        return 0
    return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
            "selfcheck": cmd_selfcheck}[a.cmd](a) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(limit=2)
        sys.exit(0)
