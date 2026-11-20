#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patent-search-dossier / main.py

五命令主路径：init / show / check / build / selfcheck。
Agent 主答：脚本只做索引、号码规范化、候选、校验、渲染与契约回填；内容判断由 Agent 写进
/app/work/draft.json。任何异常都被捕获，退出码恒 0。
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import registry as R    # noqa: E402
import dossier as D     # noqa: E402
import render as G      # noqa: E402

V = R.VERSION
T0 = time.time()
RESERVED = {"case_id", "status", "skill", "note", "deliverable", "output_contract", "runtime",
            "errors", "degradations", "assumptions", "counts", "coverage", "sources", "conflicts",
            "gaps", "artifacts", "queries", "candidates", "number_registry", "family_graph",
            "status_provenance", "claims_versions", "technical_papers", "license_gate",
            "boundary_log", "risk_register", "evidence_map", "summary"}
CONTRACT_MAP = (
    (("number", "号码", "公开号", "专利号", "registration", "registry", "patent_no"), "number_registry"),
    (("family", "族", "同族"), "family_graph"),
    (("status", "legal", "法律", "有效性"), "status_provenance"),
    (("claim", "权利", "scope"), "claims_versions"),
    (("paper", "literature", "文献", "article", "publication"), "technical_papers"),
    (("license", "permission", "许可", "授权", "compliance", "terms"), "license_gate"),
    (("boundary", "limitation", "遗漏", "uncertain", "unknown", "gap"), "boundary_log"),
    (("candidate", "result", "候选", "命中", "命中集"), "candidates"),
    (("query", "检索式", "search", "strategy"), "queries"),
    (("evidence", "source", "provenance", "locator", "引用", "依据"), "evidence_map"),
    (("coverage", "覆盖"), "coverage"),
    (("risk", "风险"), "risk_register"),
    (("conflict", "冲突"), "conflicts"),
    (("summary", "conclusion", "结论", "回答"), "summary"),
)
DEFAULT_CONTRACT = {"retrieval_results": None, "evidence_records": None, "status_note": None}


def now():
    return R.now()


def log(work, tag, msg):
    try:
        p = Path(work) / "run.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write("%s [%s] %s\n" % (now(), tag, msg))
    except Exception:
        pass


def pick(explicit, env, defaults):
    cands = [explicit] + ([os.environ.get(env)] if os.environ.get(env) else []) + defaults
    for c in cands:
        if c and Path(str(c)).exists():
            return Path(str(c))
    for c in cands:
        if c:
            return Path(str(c))
    return Path(".")


def paths(a):
    inp = pick(getattr(a, "input", None), "INPUT_DIR", ["/input", "input", "../input", "/app/input"])
    out = pick(getattr(a, "output", None), "OUTPUT_DIR", ["/app/output", "output", "../output"])
    work = pick(getattr(a, "work", None), "WORK_DIR", ["/app/work", "work", "../work"])
    return inp, out, work


# ---------------------------------------------------------------- 契约
def base_result(case, status, contract):
    cid = R.gk(case, "case_id", "id", "caseId")
    res = {"case_id": cid, "status": status,
           "skill": {"name": R.SKILL_NAME, "version": V},
           "note": "", "deliverable": {}, "output_contract": {},
           "sources": [], "queries": [], "candidates": [], "number_registry": [],
           "family_graph": {}, "status_provenance": [], "claims_versions": [],
           "technical_papers": [], "license_gate": {}, "boundary_log": {},
           "conflicts": [], "risk_register": [], "gaps": [], "evidence_map": [],
           "coverage": {}, "counts": {}, "assumptions": [], "errors": [], "degradations": [],
           "runtime": {}, "artifacts": [], "_contract": contract or {}}
    if not cid:
        res["errors"].append("case.json 未提供 case_id（保留 null）")
    return res


def contract_of(case):
    c = R.gk(case, "output_contract", "outputContract", "output_schema", default=None)
    if isinstance(c, dict) and c:
        return dict(c)
    if isinstance(c, list):
        return {str(k): None for k in c}
    # 无契约时按任务说明关键词给默认键集（并记 assumptions）
    return dict(DEFAULT_CONTRACT)


def match_artifact(key):
    kl = str(key).lower()
    for kws, art in CONTRACT_MAP:
        if any(kw in kl for kw in kws):
            return art
    return None


def finalize(outdir, res):
    contract = res.pop("_contract", {}) or {}
    filled = {}
    for k in contract:
        if k in res and res[k] not in (None, "", [], {}):
            filled[k] = res[k]
        elif str(k).lower() in res:
            filled[k] = res[str(k).lower()]
        else:
            art = match_artifact(k)
            filled[k] = res.get(art) if art else None
    res["output_contract"] = filled
    for k, v in filled.items():
        if k not in RESERVED and k not in res:
            res[k] = v
    res["runtime"] = dict(res.get("runtime") or {}, elapsed_s=round(time.time() - T0, 2),
                          python=sys.version.split()[0], finished_at=now(), skill_version=V,
                          started_at=res.get("runtime", {}).get("started_at") or now())
    order = ["case_id", "status", "skill", "note", "deliverable", "output_contract"]
    out = {k: res[k] for k in order if k in res}
    out.update({k: v for k, v in res.items() if k not in out})
    R.dump(Path(outdir) / "result.json", out)
    return out


def load_index(work, indir, cpath):
    idx, err = R.load_json(Path(work) / "index.json")
    if isinstance(idx, dict) and isinstance(idx.get("materials"), list):
        return idx, None
    idx = R.build_index(indir, cpath)
    R.dump(Path(work) / "index.json", idx)
    return idx, err


# ---------------------------------------------------------------- init
def cmd_init(a):
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case, cpath, cerr = R.find_case(inp)
    contract = contract_of(case)
    res = base_result(case, "partial", contract)
    res["note"] = "init: 索引已建，等待 Agent 阅读材料并写工作稿"
    res["assumptions"].append("无 Agent 工作稿时按索引兜底生成最小档案（status=partial）")
    if cerr:
        res["errors"].append(cerr)
    if not contract:
        res["assumptions"].append("output_contract 未识别，使用默认键集 %s" % list(DEFAULT_CONTRACT))
    finalize(out, res)
    try:
        idx = R.build_index(inp, cpath)
        R.dump(work / "index.json", idx)
        log(work, "INIT", "materials=%d numbers=%d chars=%d" % (
            len(idx["materials"]), len(idx["number_candidates"]), idx["total_chars"]))
        print("== init v%s == case %s" % (V, cpath or "未找到"))
        print("contract %s | materials %d | numbers %d | families %d | license-rows %d | papers %d"
              % (", ".join(map(str, contract)) or "-", len(idx["materials"]),
                 len(idx["number_candidates"]), len(idx["family_candidates"]),
                 len(idx["license_candidates"]), len(idx["paper_candidates"])))
        for m in idx["materials"]:
            role = ",".join("%s(%.2f)" % (k, v) for k, v in (m.get("roles") or {}).items()) or "-"
            print("  %-3s %-36s %-6s %7d字 %3d段 %-14s %s"
                  % (m["id"], m["rel"][:36], m["kind"], m["chars"], len(m["paras"]),
                     m["extract"][:14], role[:60]))
        for n in idx.get("extract_notes", [])[:6]:
            print("  note %s: %s" % (n["material"], n["note"]))
        if cerr:
            print("WARN %s" % cerr)
        ti = R.gk(case, "task_instruction", "organizer_workorder")
        if ti:
            print("task_instruction %s" % json.dumps(ti, ensure_ascii=False)[:500])
        print("NEXT: python3 %s show  → 写 %s/draft.json → check → build" % (
            Path(__file__).name, work))
    except Exception as e:
        print("init degraded: %s: %s" % (type(e).__name__, e))
        log(work, "INIT-ERR", str(e))
    return 0


# ---------------------------------------------------------------- show
def cmd_show(a):
    inp, out, work = paths(a)
    idx, err = load_index(work, inp, None)
    if a.id:
        mid = a.id.upper()
        m = next((x for x in idx.get("materials", []) if x["id"] == mid), None)
        if not m:
            print("unknown material %s; have: %s" % (a.id, ", ".join(
                "%s=%s" % (x["id"], x["rel"]) for x in idx.get("materials", []))))
            return 0
        pat = __import__("re").compile(a.grep, __import__("re").I) if a.grep else None
        print("== %s | %s | %s | roles=%s | ocr=%s ==" % (
            m["id"], m["rel"], m["extract"], m.get("roles"), m.get("ocr")))
        n = 0
        for pa in m.get("paras", []):
            if pat and not pat.search(pa["text"]):
                continue
            print("\n[%s/%s]\n%s" % (m["id"], pa["loc"], pa["text"][:1500]))
            n += 1
            if n >= 200:
                print("\n... truncated (用 --grep 缩小范围)")
                break
        return 0
    if a.grep:
        pat = __import__("re").compile(a.grep, __import__("re").I)
        print("== grep %r ==" % a.grep)
        for m in idx.get("materials", []):
            for pa in m.get("paras", []):
                if pat.search(pa["text"]):
                    print("\n[%s/%s] %s" % (m["id"], pa["loc"], pa["text"][:900]))
        return 0
    case, _, _ = R.find_case(inp)
    print("== show v%s == case_id %s | materials %d | chars %d | fingerprint %s"
          % (V, R.gk(case, "case_id", "id") or "-", len(idx.get("materials", [])),
             idx.get("total_chars", 0), (idx.get("fingerprint") or {}).get("sha256")))
    print("\n-- 材料与角色（引用时用 M#/p#） --")
    for m in idx.get("materials", []):
        print("  %-3s %-38s %-6s %6d字 %3d段 ocr=%s roles=%s"
              % (m["id"], m["rel"][:38], m["kind"], m["chars"], len(m["paras"]),
                 m.get("ocr"), ",".join((m.get("roles") or {}).keys()) or "-"))
    print("\n-- 号码候选（raw → norm，含定位与解析状态） --")
    for c in R.al(idx.get("number_candidates"))[:24]:
        print("  %-24s → %-18s %-16s %-9s %s/%s w=%d"
              % (str(c["raw"])[:24], c["norm"], c["doc_type"], c["parse_status"],
                 c["source_id"], c["locator"], c.get("weight", 0)))
    print("\n-- 族链接候选（需你判定 link_type 与 family_scope） --")
    for f in R.al(idx.get("family_candidates"))[:12]:
        print("  %s | %s | guess=%s | nums=%s" % (f["locator"], f["quote"][:110],
                                                  f.get("link_type_guess"), f.get("numbers")))
    print("\n-- 法律状态相关行（不得直接当登记结论） --")
    for s in R.al(idx.get("status_candidates"))[:12]:
        print("  %s | kw=%s | dates=%s | %s" % (s["locator"], s.get("status_kw"),
                                                s.get("dates"), s["quote"][:110]))
    print("\n-- 许可相关行（供你分级 green/yellow/red） --")
    for l in R.al(idx.get("license_candidates"))[:12]:
        print("  %s | tier_guess=%s | %s" % (l["locator"], l.get("tier_guess"), l["line"][:110]))
    print("\n-- 技术文献候选 --")
    for p in R.al(idx.get("paper_candidates"))[:10]:
        print("  %s | doi=%s | %s" % (p["locator"], p.get("doi"), p["line"][:110]))
    print("\n-- 契约键（result.json 将逐键回填） --")
    print("  %s" % (list((R.gk(case, "output_contract", default={}) or {}).keys()),))
    print("\nNEXT: 读材料 → 写 %s/draft.json（schema 见 SKILL.md §4）→ check → build" % work)
    return 0


# ---------------------------------------------------------------- check
def cmd_check(a):
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    idx, _ = load_index(work, inp, None)
    draft, dpath, derr = D.load_draft(work)
    fb_used = False
    if derr and not draft:
        fb = D.fallback_draft(idx)
        draft, degs = D.merge_draft({}, fb)
        dpath, fb_used = "fallback", True
    rep = D.check(draft, idx)
    R.dump(work / "check_report.json", {"draft_path": dpath, "draft_error": derr, "report": rep})
    c = rep["counts"]
    log(work, "CHECK", "errors=%d warnings=%d ratio=%.2f" % (
        len(rep["errors"]), len(rep["warnings"]), c["evidence_ratio"]))
    print("== check == draft %s %s" % (dpath or "none", ("(%s)" % derr) if derr else ""))
    print("号码 %d | 对象 %d | 族边 %d | 状态 %d | 权利要求 %d | 文献 %d | 许可 %d | 边界 %d"
          % (c["numbers"], c["patents"], c["edges"], c["status"], c["claims"], c["papers"],
             c["licenses"], c["boundaries"]))
    print("证据 %d/%d (%.0f%%) | 检索面 %d/%d | %s"
          % (c["evidence_verified"], c["evidence_total"], 100 * c["evidence_ratio"],
             c["facets_hit"], c["facets_total"],
             "PASS" if not rep["errors"] else "FIX %d" % len(rep["errors"])))
    for e in rep["errors"][:20]:
        print("ERROR %s" % e)
    for w in rep["warnings"][:15]:
        print("WARN  %s" % w)
    if derr:
        print("NOTE  %s" % derr)
    if fb_used:
        print("WARN  没有工作稿：本次校验基于索引兜底，不代表你已完成阅读与判断")
    print("NEXT: 修工作稿后重跑 check → build")
    return 0


# ---------------------------------------------------------------- build
def cmd_build(a):
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case, cpath, cerr = R.find_case(inp)
    contract = contract_of(case)
    res = base_result(case, "partial", contract)
    res["note"] = "build: 开始"
    finalize(out, dict(res))                      # 先落一份合法 partial
    draft, dpath, derr = {}, None, None
    try:
        idx, _ = load_index(work, inp, cpath)
        if cerr:
            res["errors"].append(cerr)
        draft, dpath, derr = D.load_draft(work)
        fb = D.fallback_draft(idx)
        src = "agent" if (draft and not derr) else "fallback"
        if derr:
            res["degradations"].append(derr)
        merged, degs = D.merge_draft(draft, fb)
        res["degradations"] += degs
        if degs and src == "agent":
            src = "agent+index"
        if not merged.get("number_decisions") and not merged.get("patent_objects"):
            res["degradations"].append("材料未解析出任何号码：档案降级为结构骨架")
        if not idx.get("materials"):
            res["degradations"].append("未发现输入材料（/input 为空或无 materials）：仅交付契约骨架")
        draft = merged
        R.dump(work / "draft.effective.json", draft)
        rep = D.check(draft, idx)
        c = rep["counts"]
        status = "ok"
        if not idx.get("materials"):
            status = "input_error" if cerr and not case else "partial"
        elif src != "agent" or rep["errors"] or c["evidence_ratio"] < 0.9 or c["facets_hit"] < 6:
            status = "partial"
        ctx = {"case_id": R.gk(case, "case_id", "id"), "now": now(), "status": status,
               "draft_source": src, "today": now()[:10],
               "title": R.norm_ws(R.gk(case, "title", "case_title", default="")) or None,
               "status_note": draft.get("status_note")}
        reg = G.number_registry(draft, idx, ctx)
        ctx["registry"] = reg
        fam = G.family_graph(draft, idx, ctx)
        rows = G.status_rows(draft, ctx)
        lic_md = G.license_gate(draft, idx, ctx)
        bnd = G.boundary_log(draft, idx, ctx)
        dossier_md = G.render_dossiers(draft, idx, rep, ctx)
        (out / "dossiers.md").write_text(dossier_md, encoding="utf-8")
        R.dump(out / "number_registry.json", reg)
        R.dump(out / "family_graph.json", fam)
        G.write_status_csv(out / "status_provenance.csv", rows)
        (out / "license_gate.md").write_text(lic_md, encoding="utf-8")
        R.dump(out / "boundary_log.json", bnd)
        ev_map = [{"ref": e["ref"], "kind": e["kind"], "source_id": e["source_id"],
                   "locator": e.get("found_locator") or e["locator"], "claimed_locator": e["locator"],
                   "quote": e["quote"], "match": e["match"], "ratio": e["ratio"],
                   "status": "verified" if e["hit"] else "unverified"} for e in rep["evidence"]]
        cands = []
        for o in R.al(draft.get("patent_objects")):
            cands.append({"candidate_id": o.get("patent_id"), "type": "patent",
                          "number_norm": o.get("number_norm"), "decision": o.get("screening") or "include",
                          "reason": R.norm_ws(o.get("why")), "evidence_locator":
                          ((R.al(o.get("evidence")) or [{}])[0].get("source_id") and
                           "%s/%s" % ((R.al(o.get("evidence")) or [{}])[0].get("source_id"),
                                      (R.al(o.get("evidence")) or [{}])[0].get("locator")))})
        for p in R.al(draft.get("technical_papers")):
            cands.append({"candidate_id": p.get("paper_id"), "type": "paper", "doi": p.get("doi"),
                          "decision": "include", "reason": R.norm_ws(p.get("why_relevant")),
                          "evidence_locator": "%s/%s" % (p.get("source_id"), p.get("locator"))})
        q = draft.get("query") or {}
        res.update({
            "status": status, "note": "build: %s | 证据 %d/%d | 检索面 %d/%d" % (
                src, c["evidence_verified"], c["evidence_total"], c["facets_hit"], c["facets_total"]),
            "deliverable": {"path": "dossiers.md", "format": "markdown",
                            "chars": len(dossier_md), "draft_source": src,
                            "artifacts": ["dossiers.md", "number_registry.json", "family_graph.json",
                                          "status_provenance.csv", "license_gate.md",
                                          "boundary_log.json"]},
            "queries": [{"query_id": "Q1", "kind": q.get("kind"), "statement": R.norm_ws(q.get("statement")),
                         "targets": R.al(q.get("targets")), "scope": R.al(q.get("scope")),
                         "excluded": R.al(q.get("excluded"))}],
            "candidates": cands, "number_registry": reg["entries"], "family_graph": fam,
            "status_provenance": rows, "claims_versions": R.al(draft.get("claims_versions")),
            "technical_papers": R.al(draft.get("technical_papers")),
            "license_gate": {"decisions": R.al(draft.get("license_decisions")),
                             "red_sources": [l.get("source_id") for l in
                                             R.al(draft.get("license_decisions")) if l.get("tier") == "red"],
                             "policy": "red 来源不抓取、不展示原文，仅记录已排除与原因"},
            "boundary_log": bnd, "conflicts": R.al(draft.get("conflicts")),
            "gaps": R.al(draft.get("gaps")), "evidence_map": ev_map,
            "coverage": rep["coverage"], "counts": c, "sources": R.source_rows(idx),
            "risk_register": G.risk_register(draft), "summary": G.summary_text(draft, rep, reg),
            "artifacts": ["result.json", "dossiers.md", "number_registry.json", "family_graph.json",
                          "status_provenance.csv", "license_gate.md", "boundary_log.json"],
            "errors": res["errors"] + rep["errors"],
            "assumptions": res["assumptions"] + [
                "号码规范化由脚本确定性执行，工作稿的 norm 必须与之一致（R2）",
                "法律状态非 official_register 来源一律 needs_official_verification=true"],
            "runtime": {"input_fingerprint": idx.get("fingerprint"), "materials": len(idx.get("materials", [])),
                        "draft_path": dpath or "fallback"}})
        if not contract:
            res["assumptions"].append("output_contract 未识别，已用默认键集 %s" % list(DEFAULT_CONTRACT))
        log(work, "BUILD", "status=%s src=%s evidence=%d/%d" % (
            status, src, c["evidence_verified"], c["evidence_total"]))
        print("== build == %s | %s | dossiers.md %.1f KB | 号码 %d | 族边 %d | 状态 %d | 文献 %d | 边界 %d | 契约 %d/%d"
              % (status, src, len(dossier_md) / 1024.0, c["numbers"], c["edges"], c["status"],
                 c["papers"], c["boundaries"], len(contract), len(contract)))
        print("证据 %d/%d (%.0f%%) | 检索面 %d/%d" % (
            c["evidence_verified"], c["evidence_total"], 100 * c["evidence_ratio"],
            c["facets_hit"], c["facets_total"]))
        for d in res["degradations"][:8]:
            print("DEGRADE %s" % d)
        for e in res["errors"][:8]:
            print("ERROR %s" % e)
    except Exception as e:
        res["errors"].append("build: %s: %s" % (type(e).__name__, e))
        print("build degraded: %s" % e)
        traceback.print_exc(limit=2)
    finally:
        try:
            if not (out / "dossiers.md").is_file():
                (out / "dossiers.md").write_text(
                    "# 检索案件档案（降级骨架）\n\n案件 `%s`：输入不足，未生成完整档案。"
                    "见 result.json 的 errors/degradations。\n" % (R.gk(case, "case_id") or "-"),
                    encoding="utf-8")
                res["degradations"].append("dossiers.md 为占位骨架")
            for name, dflt in (("number_registry.json", {"entries": []}),
                               ("family_graph.json", {"nodes": [], "edges": []}),
                               ("boundary_log.json", {"entries": [], "counts": {"entries": 0}})):
                if not (out / name).is_file():
                    R.dump(out / name, dflt)
                    res["degradations"].append("%s 为占位空结构" % name)
            if not (out / "status_provenance.csv").is_file():
                G.write_status_csv(out / "status_provenance.csv", [])
            if not (out / "license_gate.md").is_file():
                (out / "license_gate.md").write_text("# 许可闸门\n\n无可用许可信息（降级）。\n",
                                                     encoding="utf-8")
            if not contract:
                res["_contract"] = contract_of(case)
            res["_contract"] = contract
            finalize(out, res)
        except Exception as e:
            try:
                R.dump(out / "result.json", {"case_id": R.gk(case, "case_id"), "status": "partial",
                                             "errors": ["finalize: %s" % e]})
            except Exception:
                pass
    return 0


# ---------------------------------------------------------------- selfcheck
def cmd_selfcheck(a):
    inp, out, work = paths(a)
    idx, _ = load_index(work, inp, None)
    res, err = R.load_json(out / "result.json")
    if not isinstance(res, dict):
        print("== selfcheck == 无 result.json（%s）；先运行 build" % err)
        return 0
    rep = D.selfcheck(out, work, res, idx, inp)
    print("== selfcheck == %s | 契约 %d | 产物 %d/%d | 证据 %.0f%% | 检索面 %s"
          % ("PASS" if rep["overall_pass"] else "CHECK",
             len(rep["contract_keys"]), len(rep["artifacts"]),
             len(rep["artifacts"]) + len(rep["missing"]), 100 * (rep["evidence_ratio"] or 0),
             (rep.get("facets") or {}).get("facets_hit")))
    for n in rep["notes"]:
        print("NOTE  %s 未通过" % n)
    if rep["missing"]:
        print("MISSING %s" % rep["missing"])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="patent-search-dossier v%s：init/show/check/build/selfcheck" % V)
    sub = ap.add_subparsers(dest="cmd")
    for name, hlp in (("init", "建索引与候选并写合法 partial result.json"),
                      ("show", "打印带 locator 的材料原文与对象清单"),
                      ("check", "机械校验工作稿（R1–R13）"),
                      ("build", "生成六件产物与最终 result.json（缺稿兜底）"),
                      ("selfcheck", "复检产物、契约与确定性指纹")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("--input", default=None)
        p.add_argument("--output", default=None)
        p.add_argument("--work", default=None)
        if name == "show":
            p.add_argument("--id", default=None, help="材料编号，如 M2")
            p.add_argument("--grep", default=None, help="按正则过滤段落/全文")
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
