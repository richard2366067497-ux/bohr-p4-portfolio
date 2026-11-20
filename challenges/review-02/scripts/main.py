#!/usr/bin/env python3
"""main.py - citation-fact-audit driver: init / show / check / build / selfcheck.

Agent-first: the script indexes the real input, prints locatable material, checks
the agent's draft against it, and assembles the final deliverables. Judgement lives
in /app/work/draft.json. Exit code is always 0; failures degrade, never crash.
"""

import argparse, json, os, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import audit_core as A      # noqa: E402
import audit_build as B     # noqa: E402
import audit_render as R    # noqa: E402

VERSION = "1.0.0"
T0 = time.time()


# ------------------------------------------------------------------ paths
def resolve_dirs(args):
    def pick(val, env, primary, alt):
        cand = [val, os.environ.get(env), primary, str(Path.cwd() / alt), str(HERE.parent / alt)]
        for c in cand:
            if c and Path(c).exists():
                return Path(c)
        return Path(val or os.environ.get(env) or primary)
    inp = pick(args.input, "AUDIT_INPUT", "/input", "input")
    work = Path(args.work or os.environ.get("AUDIT_WORK") or "/app/work")
    out = Path(args.output or os.environ.get("AUDIT_OUTPUT") or "/app/output")
    notes = []
    for target, name in ((work, "work"), (out, "output")):
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / ".write_probe"
            probe.write_text("ok", "utf-8")
            probe.unlink()
        except Exception as e:
            alt = Path.cwd() / name
            notes.append({"code": "output_dir_fallback", "scope": str(target),
                          "detail": "%s 不可写（%s），退回 %s" % (target, type(e).__name__, alt)})
            try:
                alt.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if name == "work":
                work = alt
            else:
                out = alt
    return inp, work, out, notes


def ensure_index(inp, work, force=False):
    p = Path(work) / "index.json"
    if p.exists() and not force:
        idx, err = A.load_json(p)
        if isinstance(idx, dict) and idx.get("schema") == A.INDEX_SCHEMA:
            return idx, None
    idx = A.build_index(inp)
    B.attach_candidates(idx)
    try:
        A.dump_json(p, idx)
    except Exception:
        pass
    return idx, None


def dump_any(path, obj):
    try:
        A.dump_json(path, obj)
        return True
    except Exception:
        try:
            A.dump_json(Path.cwd() / Path(path).name, obj)
        except Exception:
            pass
        return False


# ------------------------------------------------------------------ contract / envelope
def assemble(idx, draft, draft_error, version, stamp=False):
    corpus = B.Corpus(idx)
    gaps = [dict(g) for g in (idx.get("gaps") or [])]
    errors = list(idx.get("errors") or [])
    changes, rep = [], None
    if draft_error:
        gaps.append({"code": "draft_unavailable", "detail": draft_error})
        errors.append("draft: %s" % draft_error)
    if isinstance(draft, dict):
        rep, cks, fnds, coverage, changes = B.process_draft(draft, idx, corpus)
        unc = draft.get("uncertainties") if isinstance(draft.get("uncertainties"), list) else []
        unchecked = draft.get("unchecked_items") if isinstance(draft.get("unchecked_items"), list) else []
        summary = A.squash(draft.get("summary"), 2000)
        if not rep["ok"]:
            gaps.append({"code": "draft_incomplete", "detail": "; ".join(rep["errors"][:8])})
    else:
        cks, fnds, coverage = R.fallback(idx, corpus)
        unc = [{"topic": "semantic verdicts",
                "detail": "无工作稿：核验矩阵全部为 undetermined 机械候选，未做支持度判定",
                "human_check_needed": "阅读 citation_checks 的 claim_quote 所在段落与所引文献"}]
        unchecked = [{"item": f, "reason": "无工作稿，未逐项审查"} for f in B.FACETS]
        summary = ("缺少 Agent 工作稿，本结果由脚本机械生成：给出 %d 条候选论断的定位与原文、%d 条可机械"
                   "证明的问题（引文配对失败/数值不一致）。语义支持度判定缺失，见 degradations。"
                   % (len(cks), len(fnds)))
    unverified = [c["check_id"] for c in cks if not c["quote_verified"]]
    if unverified:
        gaps.append({"code": "quote_unverified", "count": len(unverified),
                     "detail": "%d 条 quote 未逐字命中，已降级 pending_review" % len(unverified)})
    status = "input_error" if not idx.get("units") else (
        "completed" if isinstance(draft, dict) and
        (any(c["verdict"] != "undetermined" for c in cks) or
         any(f["status"] == "confirmed" for f in fnds)) else "partial")
    sev = B._count([f["severity"] for f in fnds])
    metrics = {"citation_checks": len(cks), "findings": len(fnds),
               "confirmed_findings": sum(1 for f in fnds if f["status"] == "confirmed"),
               "pending_findings": sum(1 for f in fnds if f["status"] == "pending_review"),
               "verdicts": B._count([c["verdict"] for c in cks]), "severities": sev,
               "facets": B._count([f["facet"] for f in fnds]), "quote_unverified": len(unverified),
               "references_parsed": len(idx.get("references") or []),
               "citations_detected": len(idx.get("citations") or []),
               "units": len(idx.get("units") or [])}
    core = {
        "case_id": idx.get("case_id"), "status": status, "summary": summary,
        "findings": fnds, "citation_checks": cks, "coverage": coverage,
        "unchecked_items": unchecked, "uncertainties": unc,
        "sources": [{k: s.get(k) for k in ("source_id", "path", "rel", "kind", "format", "parser",
                                           "bytes", "units", "text_chars", "quality", "sha256_12")}
                    for s in idx.get("sources") or []],
        "claims": [{"claim_id": c["check_id"], "claim_text": c["claim_text"], "verdict": c["verdict"]}
                   for c in cks],
        "numeric_checks": [f for f in fnds if f["facet"] == "statistics"],
        "compliance_checks": [f for f in fnds if f["facet"] == "compliance"],
        "severity_summary": sev,
        "revisions": [{"finding_id": f["finding_id"], "revision": f["revision"]} for f in fnds],
        "metrics": metrics, "report": "citation_report.md",
        "artifacts": ["citation_report.md", "evidence.jsonl", "run_manifest.json"],
        "method_notes": {"rules_version": B.RULES_VERSION, "verdict_levels": list(B.VERDICTS),
                         "three_elements": list(B.SEM),
                         "fallback": "无工作稿时全部判定为 undetermined 并标 pending_review",
                         "quote_check": "NFKC + 去空白后子串匹配，须落在单个段落单元内"},
        "result": {"summary": summary, "status": status, "metrics": metrics,
                   "top_findings": [{"finding_id": f["finding_id"], "facet": f["facet"],
                                     "severity": f["severity"], "issue_type": f["issue_type"],
                                     "locator": f["location"]["locator"], "revision": f["revision"]}
                                    for f in sorted(fnds, key=lambda x: B.SEVERITIES.index(x["severity"]))[:10]],
                   "verdicts": B._count([c["verdict"] for c in cks])}}
    keys = list(idx.get("contract_keys") or [])
    contract, filled, empty = R.fill_contract(core, keys, idx.get("contract_spec") or {})
    if empty:
        gaps.append({"code": "contract_field_filled_empty", "fields": empty,
                     "detail": "契约字段无法自然映射，已按类型填空值"})
    result = dict(contract)
    for k, v in core.items():
        result.setdefault(k, v)
    result.update({
        "status": status, "case_id": idx.get("case_id"), "skill": "citation-fact-audit",
        "skill_version": version, "rules_version": B.RULES_VERSION,
        "errors": errors, "degradations": gaps,
        "changes": changes + ([{"scope": "result", "field": "contract_fields", "filled": filled,
                                "empty": empty}] if empty else []),
        "run_summary": {"draft_used": isinstance(draft, dict),
                        "validation_errors": len(rep["errors"]) if rep else None,
                        "validation_warnings": len(rep["warnings"]) if rep else None,
                        "blocking_gaps": sorted({g.get("code") for g in gaps
                                                 if g.get("code") in B.BLOCKING})},
        "runtime": {"skill_version": version, "rules_version": B.RULES_VERSION,
                    "index_schema": A.INDEX_SCHEMA, "wall_seconds": None,
                    "finished_at": None, "deterministic": True}})
    if stamp:
        result["runtime"]["wall_seconds"] = round(time.time() - T0, 3)
        result["runtime"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return result, rep


# ------------------------------------------------------------------ commands
def cmd_init(args):
    inp, work, out, notes = resolve_dirs(args)
    idx, _ = ensure_index(inp, work, force=not args.reuse)
    idx.setdefault("gaps", []).extend(notes)
    res = R.envelope(idx, VERSION)
    ok = dump_any(out / "result.json", res)
    tpl = B.draft_template(idx)
    dump_any(work / "draft.template.json", tpl)
    st = idx.get("stats") or {}
    print("INIT case=%s input=%s" % (idx.get("case_id"), inp))
    print("  materials: %d files, %d units, %s chars" % (st.get("files", 0), st.get("units", 0),
                                                         st.get("text_chars", 0)))
    print("  references: %d entries | citations: %d | claim candidates: %d | numeric candidates: %d"
          % (st.get("references", 0), st.get("citations", 0), st.get("claim_candidates", 0),
             st.get("numeric_candidates", 0)))
    print("  contract: %s" % (idx.get("contract_keys") or "(none -> standard envelope)"))
    for s in idx.get("sources") or []:
        print("  - %-28s %-10s %-14s units=%-4d quality=%s" % (s.get("rel"), s.get("kind"),
                                                               s.get("parser"), s.get("units", 0),
                                                               s.get("quality")))
    for g in idx.get("gaps") or []:
        print("  ! %s: %s" % (g.get("code"), A.squash(g.get("detail"), 160)))
    print("  partial result.json written: %s" % ok)
    print("NEXT: python3 scripts/main.py show")


def cmd_show(args):
    inp, work, out, _ = resolve_dirs(args)
    idx, _ = ensure_index(inp, work)
    part = args.part or "auto"
    buf = []
    budget = int(args.max_chars or 14000)

    def push(s):
        if sum(len(x) for x in buf) < budget:
            buf.append(s)

    if part in ("auto", "overview"):
        st = idx.get("stats") or {}
        push("== 案例 %s | %s ==" % (idx.get("case_id"), idx.get("input_dir")))
        push("files=%d units=%d refs=%d citations=%d claims=%d numeric=%d chars=%d"
             % (st.get("files", 0), st.get("units", 0), st.get("references", 0),
                st.get("citations", 0), st.get("claim_candidates", 0),
                st.get("numeric_candidates", 0), st.get("text_chars", 0)))
        push("contract keys: %s" % ", ".join(idx.get("contract_keys") or []) or "contract keys: (none)")
        if idx.get("case_meta"):
            push("task: %s" % A.squash(list(idx["case_meta"].values())[0], 600))
        for g in idx.get("gaps") or []:
            push("! %s: %s" % (g.get("code"), A.squash(g.get("detail"), 200)))
    if part in ("auto", "claims"):
        push("\n-- 可核验论断候选（claim_candidates，逐字原文 + locator）--")
        for c in idx.get("claim_candidates") or []:
            push("[%s] %s\n    %s\n    markers=%s nums=%s dir=%s neg=%s sig=%s scope=%s causal=%s"
                 % (c["cand_id"], c["locator"], c["text"], c["markers"][:4], c["numbers"][:4],
                    c["direction"], c["negation"], c["significance"], c["scope_cue"], c["causal_cue"]))
    if part in ("auto", "refs"):
        push("\n-- 参考文献表（%d 条）--" % len(idx.get("references") or []))
        for r in idx.get("references") or []:
            push("[%s] label=%s year=%s status=%s doi=%s\n    %s\n    locator=%s"
                 % (r["ref_id"], r["label"], r["year"], r["status_flag"], r["doi"],
                    A.squash(r["raw"], 260), r["locator"]))
        push("\n-- 引文标记配对（%d 处）--" % len(idx.get("citations") or []))
        for c in idx.get("citations") or []:
            push("%s %-16s %-12s -> %s [%s] %s" % (c["cite_id"], c["marker"], c["pairing"],
                                                   c["ref_ids"], c["locator"], A.squash(c["sentence"], 100)))
    if part in ("auto", "numbers"):
        push("\n-- 数值一致性候选（%d）--" % len(idx.get("numeric_candidates") or []))
        for n in idx.get("numeric_candidates") or []:
            push("%s bucket=%s\n    A %s: %s\n    B %s: %s" % (n["num_id"], n["bucket"], n["left"]["locator"],
                                                              n["left"]["sentence"], n["right"]["locator"],
                                                              n["right"]["sentence"]))
        if idx.get("numeric_index"):
            push("numeric index: %s" % A.squash(idx["numeric_index"], 600))
    if part in ("units", "all"):
        units = idx.get("units") or []
        off = max(0, int(args.offset or 0))
        lim = max(1, int(args.limit or 25))
        push("\n-- 段落单元 %d-%d / %d（quote 必须逐字取自此处）--"
             % (off, min(off + lim, len(units)), len(units)))
        for u in units[off:off + lim]:
            push("[%s] %s\n    %s" % (u["uid"], u["locator"], u["text"]))
        if off + lim < len(units):
            push("... 继续: --part units --offset %d --limit %d" % (off + lim, lim))
    print("\n".join(buf))


def cmd_check(args):
    inp, work, out, _ = resolve_dirs(args)
    idx, _ = ensure_index(inp, work)
    draft_path = Path(args.draft) if args.draft else work / "draft.json"
    draft, err = A.load_json(draft_path)
    if draft is None:
        rep = {"ok": False, "errors": ["draft 不可用: %s" % err], "warnings": [], "items": [],
               "stats": {}}
    else:
        rep, _, _, _, _ = B.process_draft(draft, idx, B.Corpus(idx))
    dump_any(work / "check_report.json", rep)
    ok = sum(1 for i in rep["items"] if i["ok"])
    bad = [i for i in rep["items"] if not i["ok"]]
    print("CHECK %s draft=%s" % (idx.get("case_id"), draft_path))
    print("  %d pass / %d fail / %d warn" % (ok, len(bad), len(rep["warnings"])))
    for i in bad[:40]:
        print("  FAIL %s/%s: %s" % (i["scope"], i["check"], i["detail"]))
    for w in rep["warnings"][:15]:
        print("  WARN %s" % w)
    if draft is None:
        print("  没有工作稿：请先 show 读材料、写 draft.json（模板在 %s）" % (work / "draft.template.json"))
    print("NEXT: python3 scripts/main.py build   (build 会无条件 finalize，兜底 partial)")
    return 0


def cmd_build(args):
    inp, work, out, notes = resolve_dirs(args)
    idx, _ = ensure_index(inp, work)
    idx.setdefault("gaps", []).extend(notes)
    draft_path = Path(args.draft) if args.draft else work / "draft.json"
    draft, err = A.load_json(draft_path)
    result, rep = assemble(idx, draft, err, VERSION, stamp=args.stamp)
    ok = dump_any(out / "result.json", result)
    written = ["result.json" if ok else "result.json(failed)"]
    try:
        (out / "citation_report.md").write_text(R.render_report(result), "utf-8")
        written.append("citation_report.md")
    except Exception:
        pass
    try:
        (out / "evidence.jsonl").write_text(R.evidence_lines(result), "utf-8")
        written.append("evidence.jsonl")
    except Exception:
        pass
    try:
        A.dump_json(out / "run_manifest.json", R.manifest(idx, result, "build", time.time() - T0, VERSION))
        written.append("run_manifest.json")
    except Exception:
        pass
    m = result.get("metrics") or {}
    print("BUILD case=%s status=%s draft_used=%s" % (result.get("case_id"), result.get("status"),
                                                     (result.get("run_summary") or {}).get("draft_used")))
    print("  citation_checks=%d findings=%d confirmed=%d pending=%d unverified_quotes=%d"
          % (m.get("citation_checks", 0), m.get("findings", 0), m.get("confirmed_findings", 0),
             m.get("pending_findings", 0), m.get("quote_unverified", 0)))
    print("  verdicts=%s severities=%s" % (A.squash(m.get("verdicts"), 160), A.squash(m.get("severities"), 160)))
    print("  wrote: %s -> %s" % (", ".join(written), out))
    for g in (result.get("degradations") or [])[:10]:
        print("  ! %s: %s" % (g.get("code"), A.squash(g.get("detail"), 160)))
    print("NEXT: python3 scripts/main.py selfcheck")
    return 0


def cmd_selfcheck(args):
    inp, work, out, _ = resolve_dirs(args)
    idx, _ = ensure_index(inp, work)
    res, err = A.load_json(out / "result.json")
    if res is None:
        print("SELFCHECK: result.json 不可用 (%s)" % err)
        dump_any(work / "selfcheck.json", {"ok": False, "failed": ["result.json"], "checks": []})
        return 0
    sc = B.selfcheck(res, idx)
    dump_any(work / "selfcheck.json", sc)
    print("SELFCHECK %s: %s (%d checks, %d failed)"
          % (res.get("case_id"), "PASS" if sc["ok"] else "FAIL", len(sc["checks"]), len(sc["failed"])))
    for c in sc["checks"]:
        print("  [%s] %s %s" % ("ok" if c["ok"] else "!!", c["check"], c["detail"][:160]))
    return 0


def last_resort(args, exc):
    try:
        inp, work, out, notes = resolve_dirs(args)
        idx = A.new_index()
        idx["input_dir"] = str(inp)
        idx["gaps"] = notes + [{"code": "internal_error", "detail": "%s: %s" % (type(exc).__name__, exc)}]
        idx["errors"] = [str(exc)]
        dump_any(out / "result.json", R.envelope(idx, VERSION))
        print("FALLBACK: 已写出最小合法 result.json（%s）" % exc)
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="citation-fact-audit (review-02)")
    ap.add_argument("command", choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", help="input dir (default /input)")
    ap.add_argument("--work", help="work dir (default /app/work)")
    ap.add_argument("--output", help="output dir (default /app/output)")
    ap.add_argument("--draft", help="explicit draft.json path (default <work>/draft.json)")
    ap.add_argument("--part", default="auto", choices=["auto", "overview", "units", "claims", "refs", "numbers", "all"])
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=25, help="units per page for --part units")
    ap.add_argument("--max-chars", dest="max_chars", type=int, default=14000)
    ap.add_argument("--reuse", action="store_true", help="init: reuse existing index.json")
    ap.add_argument("--stamp", action="store_true", help="record wall clock in result.runtime")
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        ap.print_help()
        return 0
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        print("usage: main.py {init|show|check|build|selfcheck} [--input DIR] [--work DIR] [--output DIR]")
        return 0
    try:
        return {"init": cmd_init, "show": cmd_show, "check": cmd_check,
                "build": cmd_build, "selfcheck": cmd_selfcheck}[args.command](args)
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        last_resort(args, e)
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
