#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py - research-file-locator: five-command main path.

  python3 -B scripts/main.py init       # index the library, write a legal partial result.json
  python3 -B scripts/main.py show       # print a locator-bearing catalogue for the Agent to quote
  python3 -B scripts/main.py check      # machine-verify the Agent draft (/app/work/draft.json)
  python3 -B scripts/main.py build      # turn the draft into result.json + artifacts (always finalizes)
  python3 -B scripts/main.py selfcheck  # re-verify the emitted result.json

Exit code is always 0. A legal partial result.json is written before any parsing.
The script never decides what a hit means; that judgement lives in the Agent draft
(see report.py for the verification layer and rules.py for retrieval/filter/dedupe rules).
"""
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core    # noqa: E402
import rules   # noqa: E402
import report  # noqa: E402
from report import (assemble, draft_rows, global_conds, load_draft, match_row,  # noqa: E402
                    query_conds, verify_payload, verify_row)

VERSION = "1.0.0"
T0 = time.time()
QSTAT = report.QSTAT
STATUS_ALIAS = report.STATUS_ALIAS


def P(msg=""):
    print(msg)


# ---------------------------------------------------------------- environment
def resolve_dirs(args):
    def pick(explicit, primary, fallback):
        for p in ([Path(explicit)] if explicit else []) + [Path(primary), Path(fallback)]:
            try:
                p.mkdir(parents=True, exist_ok=True)
                probe = p / ".w"
                probe.write_text("x", encoding="utf-8")
                probe.unlink()
                return p
            except Exception:  # noqa: BLE001
                continue
        return Path.cwd()

    inp = Path(args.input) if args.input else Path("/input")
    if not inp.is_dir():
        inp = Path.cwd() / "input"
    out = pick(args.out, "/app/output", "output")
    work = pick(args.work, "/app/work", "work")
    return inp, out, work

def load_ctx(args, rebuild=False):
    inp, out, work = resolve_dirs(args)
    case, cpath, errs = core.find_case(inp, args.case)
    for e in errs:
        core.STATE["errors"].append(e)
    meta = core.build_meta(case, cpath)
    ipath = work / "index.json"
    index = core.jload(ipath)
    if rebuild or not isinstance(index, dict) or "docs" not in index or \
            (meta.get("case_id") and index.get("case_id") not in (None, meta.get("case_id"))):
        index = core.build_index(meta, case, inp)
        core.jdump(ipath, index)
    return {"inp": inp, "out": out, "work": work, "case": case, "cpath": cpath,
            "meta": meta, "index": index}

def write_partial(out, meta, index, queries):
    contract = (meta or {}).get("output_contract") or {}
    payload = core.blank_payload(contract, (meta or {}).get("case_id"), "partial",
                                 "部分：已建索引，待 Agent 工作稿裁决")
    docs = (index or {}).get("docs") or []
    payload["status"] = "partial"
    payload["coverage"] = {"docs_indexed": sum(1 for d in docs if d.get("status") == "ok"),
                           "docs_total": len(docs), "queries_expected": len(queries or [])}
    payload["queries"] = [{"query_id": q["query_id"], "question": q["question"], "answer": "",
                           "status": "not_found", "evidence": [],
                           "search_scope": "尚未检索（init 阶段）"} for q in (queries or [])]
    payload["result"] = {"queries": payload["queries"], "hits": [], "coverage": payload["coverage"]}
    payload["sources"] = [{"type": d.get("type"), "path": d.get("path"), "sha256_16": d.get("sha256_16")}
                          for d in docs[:60]]
    payload["degradations"] = [{"item": "draft", "reason": "agent_draft_not_written",
                                "impact": "未经 Agent 裁决，仅有索引与空答案"}]
    core.jdump(Path(out) / "result.json", payload)

# ---------------------------------------------------------------- init
def cmd_init(args):
    ctx = load_ctx(args, rebuild=True)
    work, out, index, meta, case = ctx["work"], ctx["out"], ctx["index"], ctx["meta"], ctx["case"]
    queries = core.find_queries(case)
    task_md = core.read_task_md(ctx["inp"])
    docs = index.get("docs") or []
    paras = sum(len(d.get("paragraphs") or []) for d in docs)
    secs = sum(len(d.get("sections") or []) for d in docs)
    index["scan_stats"].update({"paragraphs": paras, "sections": secs, "index_ms": None,
                                "bytes_total": sum(d.get("bytes") or 0 for d in docs)})
    core.jdump(work / "index.json", index)
    core.jdump(work / "queries.json", {"case_id": meta.get("case_id"), "queries": queries,
                                       "task_md_chars": len(task_md)})
    tmpl = {"case_id": meta.get("case_id"), "queries": [], "excluded_evidence": [],
            "filters": [], "method_notes": {"index_granularity": "", "synonym_strategy": "",
                                            "filter_order": ""}, "uncertainties": []}
    for q in queries:
        cs = query_conds(case, q)
        tmpl["queries"].append({"query_id": q["query_id"], "question": q["question"], "answer": "",
                                "status": "not_found", "filters_applied": [rules.filter_text(c) for c in cs],
                                "evidence": [{"path": "", "version": "", "section": "",
                                              "page_printed": None, "page_physical": None,
                                              "paragraph_id": "", "quote": ""}],
                                "search_scope": "", "notes": ""})
    for c in global_conds(case):
        tmpl["filters"].append({"filter": rules.filter_text(c), "kept": 0, "removed": 0,
                                "satisfiable": True})
    core.jdump(work / "draft.template.json", tmpl)
    ledger = rules.filter_ledger(global_conds(case), docs)
    core.jdump(work / "filters_ledger.json", {"global_filters": ledger})
    write_partial(out, meta, index, queries)
    P(f"[{VERSION}] init case={meta.get('case_id')} root={index.get('library_root')}")
    P(f"docs={len(docs)} indexed={index['scan_stats'].get('indexed')} sections={secs} "
      f"paragraphs={paras} queries={len(queries)} digest={index.get('index_digest')}")
    P(f"work={work} out={out}  next: python3 -B scripts/main.py show")
    for e in (core.STATE["errors"] + [])[:5]:
        P(f"  ! {e}")
    return 0

# ---------------------------------------------------------------- show
def cmd_show(args):
    ctx = load_ctx(args)
    index, case, work = ctx["index"], ctx["case"], ctx["work"]
    queries = core.find_queries(case)
    gl = global_conds(case)
    docs = index.get("docs") or []
    P(f"=== CASE {ctx['meta'].get('case_id')} digest={index.get('index_digest')} "
      f"root={index.get('library_root')} ({index.get('root_source')})")
    ti = str(ctx["meta"].get("task_instruction") or "")[:900]
    if ti:
        P("--- task_instruction (first 900 chars) ---")
        P(ti)
    if queries:
        P(f"--- queries ({len(queries)}) ---")
        for q in queries:
            cs = query_conds(case, q)
            P(f"[{q['query_id']}] {q['question']}")
            if cs:
                P("    filters: " + "; ".join(rules.filter_text(c) for c in cs))
    P(f"--- docs ({len(docs)}) ---")
    lines = []
    shown = 0
    limit = max(1, int(getattr(args, "limit", 160) or 160))
    greps = [g.lower() for g in (getattr(args, "grep", None) or [])]
    for d in docs:
        head = (f"== {d.get('doc_id')}  {d.get('path')}  type={d.get('type')} ver={d.get('version')} "
                f"pages={d.get('pages', {}).get('count')} label={d.get('pages', {}).get('label_source')}"
                f"({d.get('pages', {}).get('page_offset')}) perm={d.get('permission')} status={d.get('status')}"
                f" sha={str(d.get('sha256_16') or '')[:12]} paras={len(d.get('paragraphs') or [])}")
        if d.get("duplicate_of"):
            head += f" duplicate_of={d['duplicate_of']}"
        if d.get("older_version_of"):
            head += f" older_version_of={d['older_version_of']}"
        if getattr(args, "doc", None) and str(d.get("doc_id")) != str(args.doc):
            continue
        lines.append(head)
        if d.get("aliases"):
            lines.append("   aliases: " + " | ".join(d["aliases"]))
        if d.get("status") != "ok":
            lines.append("   !! " + (", ".join(d.get("notes") or []) or d.get("status")))
            continue
        secmap = {}
        for p in ([] if getattr(args, "open", False) else (d.get("paragraphs") or [])):
            if True:
                if greps and not any(g in (p.get("text") or "").lower() for g in greps):
                    continue
                if shown >= limit:
                    continue
            body = p.get("text") or ""
            if not getattr(args, "full", False) and len(body) > 400:
                body = body[:400] + "…"
            tag = p.get("source") if p.get("source") not in (None, "body") else ""
            lines.append(f"   {p.get('pid')} p{p.get('page_physical')}/pp{p.get('page_printed')} "
                         f"[{p.get('section_id')}] {tag} :: {body}")
            shown += 1
            secmap[p.get("section_id")] = secmap.get(p.get("section_id"), 0) + 1
        if getattr(args, "open", False):
            for s in d.get("sections") or []:
                lines.append(f"   - {s.get('section_id')} L{s.get('level')} p{s.get('page_physical')}"
                             f"/pp{s.get('page_printed')} [{len(s.get('paragraph_ids') or [])}p] {s.get('title')}")
    P("\n".join(lines))
    if index.get("failures"):
        P(f"--- failures ({len(index['failures'])}) ---")
        for f in index["failures"][:20]:
            P(f"   {f.get('doc_id') or '-'} {f.get('path') or '-'} :: {f.get('reason')} :: {f.get('impact')}")
    if index.get("excluded_evidence"):
        P(f"--- excluded evidence ({len(index['excluded_evidence'])}) ---")
        for x in index["excluded_evidence"][:20]:
            P(f"   {x.get('doc_id')} {x.get('path')} :: {x.get('reason')}")
    P(f"--- printed {shown} paragraphs (limit {limit}); work draft: {work / 'draft.json'}")
    return 0

# ---------------------------------------------------------------- check
def cmd_check(args):
    ctx = load_ctx(args)
    index, case, work = ctx["index"], ctx["case"], ctx["work"]
    queries = core.find_queries(case)
    draft, dpath, derr = load_draft(args, work)
    rows = draft_rows(draft or {})
    fixes, warns = [], []
    if draft is None:
        fixes.append(f"FIX draft: {derr}（路径 {dpath}）；先写工作稿再 check")
        rows = []
    if len(rows) != len(queries):
        fixes.append(f"FIX coverage: 工作稿 {len(rows)} 条，案例 {len(queries)} 问；每问都要有一条")
    bad_st = [r.get("status") for r in rows if str(r.get("status") or "").strip() not in QSTAT]
    if bad_st:
        fixes.append(f"FIX status: 非法状态 {bad_st[:5]}，允许 {list(QSTAT)}")
    pairs = match_row(queries, rows)
    conds_all = {q["query_id"]: query_conds(case, q) for q in queries}
    vq = vhit = 0
    for q, row in pairs:
        if row is None:
            fixes.append(f"FIX cover {q['query_id']}: 缺该问条目")
            continue
        entry = verify_row(q, row, index, conds_all[q["query_id"]])
        n_ev = len(entry["evidence"]) + len(entry["rejected_evidence"])
        vq += 1
        vhit += len(entry["evidence"])
        for rej in entry["rejected_evidence"]:
            if rej.get("reason", "").startswith("quote_"):
                sug = rej.get("suggestion") or {}
                fixes.append(f"FIX quote {q['query_id']}: {rej.get('reason')} :: {rej.get('quote', '')[:60]!r} "
                             f"-> 最接近 {sug.get('paragraph_id')} p{sug.get('page_physical')}/"
                             f"pp{sug.get('page_printed')}「{(sug.get('snippet') or '')[:60]}」")
            else:
                warns.append(f"WARN evidence {q['query_id']}: {rej.get('reason')} {rej.get('path')}")
        if entry["status"] in ("answered", "partially_answered") and not entry["evidence"]:
            _draft_st = str((row or {}).get("status") or "-")
            fixes.append(f"FIX evidence {q['query_id']}: 草稿状态 {_draft_st} 但无通过校验的引文"
                         f"（{len(entry['rejected_evidence'])} 条被拒，见 WARN）")
        if entry["status"] in ("not_found", "blocked_by_filter") and not entry.get("scope_provided"):
            fixes.append(f"FIX scope {q['query_id']}: 空结果必须写 search_scope（查了哪些文件/关键词/过滤）")
        if n_ev == 0 and entry["status"] in ("answered", "partially_answered"):
            warns.append(f"WARN {q['query_id']}: 无 evidence 条目")
    ledger = rules.filter_ledger(global_conds(case), index.get("docs") or [])
    unsat = [r["filter"] for r in ledger if not r["satisfiable"]]
    blocked_rows = [q["query_id"] for q, r in pairs if isinstance(r, dict) and
                    STATUS_ALIAS.get(str(r.get("status")), str(r.get("status"))) == "blocked_by_filter"]
    if unsat and not blocked_rows and any(isinstance(r, dict) and STATUS_ALIAS.get(
            str(r.get("status")), str(r.get("status"))) in ("answered", "partially_answered")
            for _q, r in pairs):
        fixes.append(f"FIX filter: 过滤条件不可满足 {unsat}，但仍有问题被作答（疑似静默放宽）")
    excl = index.get("excluded_evidence") or []
    bad_ex = [x["path"] for x in excl if core.doc_by_path(index, x.get("path")) is None]
    if bad_ex:
        warns.append(f"WARN excluded: {len(bad_ex)} 条排除记录路径未能回指索引")
    rate = round(vhit / float(max(1, vhit + sum(0 for _ in range(0)))) , 3) if vhit else 0.0
    report = {"case_id": ctx["meta"].get("case_id"), "draft": str(dpath), "queries": len(queries),
              "rows": len(rows), "evidence_verified": vhit, "fixes": fixes, "warnings": warns,
              "filters_ledger": ledger, "blocked_queries": blocked_rows,
              "checked_at": core.now()}
    core.jdump(work / "check_report.json", report)
    P(f"[check] queries={len(queries)} rows={len(rows)} verified_evidence={vhit} "
      f"fixes={len(fixes)} warns={len(warns)}")
    for f in fixes[:25]:
        P("  " + f)
    for w in warns[:10]:
        P("  " + w)
    if not fixes:
        P("  PASS: 契约字段、引文逐字、覆盖与过滤执行未发现问题；可以运行 build")
    P(f"  report -> {work / 'check_report.json'}")
    return 0

def write_artifacts(payload, index, out, work):
    def _dict_list(v):
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    core.jdump(out / "index.json", index)
    _res = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    core.jdump(out / "answers.json", {"case_id": payload.get("case_id"), "status": payload.get("status"),
                                      "queries": payload.get("queries"), "coverage": payload.get("coverage"),
                                      "counts": payload.get("counts")})
    core.jdump(out / "filters_log.json", {"global_filters": payload.get("filters"),
                                          "per_query": _res.get("per_query_filters")})
    core.jdump(out / "dedupe.json", {"groups": (index.get("dedupe") or {}).get("groups"),
                                     "conflicts": (index.get("dedupe") or {}).get("conflicts"),
                                     "excluded_evidence": payload.get("excluded_evidence")})
    core.jdump(out / "failures.json", {"failures": index.get("failures") or [],
                                       "degradations": payload.get("degradations") or [],
                                       "errors": payload.get("errors") or []})
    core.write_jsonl(out / "hits.jsonl", _dict_list(payload.get("hits") or []))
    core.jdump(out / "verify_report.json", payload.get("verification") or {})
    lines = [f"# {payload.get('case_id')} 检索交接报告", "",
             f"- status: **{payload.get('status')}**", f"- {payload.get('summary')}", ""]
    for en in _dict_list(payload.get("queries") or []):
        lines.append(f"## {en.get('query_id')} {en.get('question')}")
        lines.append(f"- 状态: `{en.get('status')}`")
        if en.get("filters_applied"):
            lines.append("- 过滤: " + "; ".join(str(x) for x in en["filters_applied"]))
        if en.get("answer"):
            lines.append(f"- 结论: {en['answer']}")
        for ev in _dict_list(en.get("evidence") or []):
            lines.append(f"- 证据: `{ev.get('locator')}` | {ev.get('path')} ({ev.get('version') or '版本未标注'}) "
                         f"§{ev.get('section')} p{ev.get('page_physical')}/pp{ev.get('page_printed')}")
            lines.append(f"  > {ev.get('quote')}")
        if en.get("rejected_evidence"):
            lines.append(f"- 拒收证据: {len(en['rejected_evidence'])} 条（见 result.json）")
        if en.get("search_scope"):
            lines.append(f"- 检索范围: {en['search_scope']}")
        lines.append("")
    _filters = _dict_list(payload.get("filters") or [])
    if _filters:
        lines.append("## 过滤执行台账")
        lines.append("| 条件 | 保留 | 剔除 | 可满足 |")
        lines.append("|-|-|-|-|")
        for r in _filters:
            lines.append(f"| {r.get('filter')} | {r.get('kept')} | {r.get('removed')} | {r.get('satisfiable')} |")
        lines.append("")
    _excl = _dict_list(payload.get("excluded_evidence") or [])
    if _excl:
        lines.append("## 被排除的证据（副本/旧版/无权限）")
        for x in _excl[:30]:
            lines.append(f"- `{x.get('path')}` — {x.get('reason')}")
        lines.append("")
    (Path(out) / "location_report.md").write_text("\n".join(lines), encoding="utf-8")

def cmd_build(args):
    ctx = load_ctx(args)
    out, work, meta = ctx["out"], ctx["work"], ctx["meta"]
    core.jdump(out / "result.json", core.blank_payload(meta.get("output_contract"), meta.get("case_id"), "partial",
                                                       "构建中：已写入合法部分结果"))
    draft, dpath, derr = load_draft(args, work)
    payload = assemble(ctx, draft, derr)
    index = ctx["index"]
    payload["verification"] = verify_payload(payload, index)
    if payload["verification"]["fails"]:
        core.degrade("verification", ",".join(payload["verification"]["fails"]),
                     "部分自检项未通过，详见 verification")
    uniq, seen_d = [], set()
    for d in payload.get("degradations") or []:
        k = (d.get("item"), d.get("reason"))
        if k not in seen_d:
            seen_d.add(k)
            uniq.append(d)
    payload["degradations"] = uniq
    if payload["verification"]["fails"]:
        payload["status"] = "partial"
        payload["result"]["status"] = "partial"
    core.jdump(out / "result.json", payload)
    write_artifacts(payload, index, out, work)
    v = payload["verification"]
    _cnt = payload.get("counts")
    _cnt = _cnt if isinstance(_cnt, dict) else {}
    P(f"[build {VERSION}] case={payload.get('case_id')} status={payload.get('status')} "
      f"queries={_cnt.get('queries')} evidence={_cnt.get('evidence')} "
      f"quote_hit_rate={v.get('quote_hit_rate')} fails={v.get('fails')}")
    P(f"  result -> {out / 'result.json'}  (index {out / 'index.json'})")
    return 0

# ---------------------------------------------------------------- selfcheck
def cmd_selfcheck(args):
    ctx = load_ctx(args)
    out, work, index = ctx["out"], ctx["work"], ctx["index"]
    payload = core.jload(out / "result.json")
    if not isinstance(payload, dict):
        payload = core.blank_payload(ctx["meta"].get("output_contract"), ctx["meta"].get("case_id"),
                                     "partial", "结果文件缺失或不合法")
        core.degrade("result.json", "missing_or_invalid", "自检时未找到合法结果")
    index["_contract"] = ctx["meta"].get("output_contract") or {}
    rep = verify_payload(payload, index)
    payload["verification"] = rep
    payload["errors"] = list(payload.get("errors") or []) + core.STATE["errors"]
    payload["degradations"] = list(payload.get("degradations") or []) + core.STATE["degradations"]
    if rep["fails"] and payload.get("status") in ("ok", "partial"):
        payload["status"] = "partial"
    core.jdump(out / "result.json", payload)
    core.jdump(out / "verify_report.json", rep)
    core.jdump(work / "selfcheck_report.json", rep)
    P(f"[selfcheck] status={payload.get('status')} ok={rep['ok']} fails={rep['fails']} "
      f"queries={rep['queries']} evidence={rep['evidence']} quote_hit_rate={rep['quote_hit_rate']}")
    for c in rep["checks"]:
        if not c["ok"]:
            P(f"  FAIL {c['check']}")
    if rep.get("unmatched_quotes"):
        P(f"  unmatched quotes: {len(rep['unmatched_quotes'])} (first: {rep['unmatched_quotes'][0]})")
    return 0

# ---------------------------------------------------------------- entry
def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="research-file-locator: locator-grade "
                                 "retrieval over a research file library.",
                                 epilog="exit code is always 0; partial result.json is written first.")
    ap.add_argument("command", nargs="?", default="init",
                    choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--case", default=None)
    ap.add_argument("--draft", default=None)
    ap.add_argument("--doc", default=None)
    ap.add_argument("--grep", action="append", default=None)
    ap.add_argument("--limit", type=int, default=160)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--version", action="version", version=f"research-file-locator {VERSION}")
    args = ap.parse_args(argv)
    cmds = {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
            "selfcheck": cmd_selfcheck}
    try:
        cmds[args.command](args)
    except Exception as e:  # noqa: BLE001
        core.err(f"command:{args.command}", e)
        try:
            inp, out, work = resolve_dirs(args)
            case, cpath, _e = core.find_case(inp, args.case)
            meta = core.build_meta(case, cpath)
            payload = core.blank_payload(meta.get("output_contract") or {}, meta.get("case_id"),
                                         "failed", "失败：脚本异常")
            payload["status"] = "failed"
            payload["errors"] = core.STATE["errors"]
            payload["degradations"] = core.STATE["degradations"]
            core.jdump(Path(out) / "result.json", payload)
        except Exception:  # noqa: BLE001
            pass
        print(f"[{VERSION}] error captured: {type(e).__name__}: {e} (exit 0)")
    return 0

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)
