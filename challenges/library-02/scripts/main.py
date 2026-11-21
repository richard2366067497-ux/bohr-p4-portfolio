"""main.py - research-file-locator CLI: all / init / show / check / build / selfcheck / fixtures."""
import argparse
import sys
import time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core    # noqa: E402
import rules   # noqa: E402
import report  # noqa: E402
import extract  # noqa: E402
from report import (assemble, draft_rows, extra_syn, global_conds, load_draft,  # noqa: E402
                    match_row, query_conds, verify_payload, verify_row)
VERSION = "1.1.0"
T0 = time.time()
QSTAT = report.QSTAT
STATUS_ALIAS = report.STATUS_ALIAS
def P(msg=""):
    print(msg)
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
    docs = (index or {}).get("docs") or []
    rows = [{"query_id": q["query_id"], "question": q["question"], "answer": "",
             "status": "not_found", "evidence": [], "search_scope": "未检索（init 阶段）"}
            for q in (queries or [])]
    cov = {"docs_indexed": sum(1 for d in docs if d.get("status") == "ok"),
           "docs_total": len(docs), "queries_expected": len(rows)}
    payload = core.blank_payload((meta or {}).get("output_contract") or {}, (meta or {}).get("case_id"),
                                 "partial", "部分：已建索引，待 Agent 工作稿裁决")
    payload.update({"status": "partial", "coverage": cov, "queries": rows,
                    "result": {"queries": rows, "hits": [], "coverage": cov},
                    "sources": [{"type": d.get("type"), "path": d.get("path"),
                                 "sha256_16": d.get("sha256_16")} for d in docs[:60]],
                    "degradations": [{"item": "draft", "reason": "agent_draft_not_written",
                                      "impact": "未经 Agent 裁决，仅有索引与空答案"}]})
    core.jdump(Path(out) / "result.json", payload)
def write_candidates(work, case, index, queries):
    extra = extra_syn(case)
    rows = []
    for q in queries:
        conds = query_conds(case, q)
        hits, blocked, satisfiable = rules.search(index, q["question"], conds, extra)
        n_par = sum(len(d.get("paragraphs") or []) for d in (index.get("docs") or []))
        best, para = report.best_hit(index, hits)
        rows.append({
            "query_id": q["query_id"], "question": q["question"], "answer": "",
            "status": "partially_answered" if para is not None else "not_found",
            "filters_applied": [rules.filter_text(c) for c in conds],
            "search_scope": ("脚本候选检索：%d 个文档、%d 段，命中 %d，过滤可满足=%s；"
                             "取最高分段落作为待核引文"
                             % (len(index.get("docs") or []), n_par, len(hits), satisfiable)),
            "evidence": ([{"path": best.get("path"), "section": best.get("section"),
                           "paragraph_id": best.get("paragraph_id"),
                           "page_physical": best.get("page_physical"),
                           "page_printed": best.get("page_printed"),
                           "quote": para.get("text")}] if para is not None else []),
            "candidates": [{k: h.get(k) for k in ("doc_id", "path", "section", "paragraph_id",
                                                  "page_physical", "page_printed", "score")}
                           for h in hits[:3]],
            "notes": "脚本预填：引文逐字、locator 待 check 复核；answer 与 status 由 Agent 裁决"})
    payload = {"case_id": (index or {}).get("case_id"), "queries": rows,
               "excluded_evidence": list(index.get("excluded_evidence") or []),
               "filters": [dict(r) for r in rules.filter_ledger(global_conds(case),
                                                                index.get("docs") or [])],
               "method_notes": {"index_granularity": "section+paragraph",
                                "synonym_strategy": "builtin SYN + case synonyms",
                                "filter_order": "hard filters -> retrieve -> quote verify"},
               "uncertainties": [{"item": "adjudication",
                                  "detail": "预填候选来自脚本打分，未做语义裁决"}]}
    core.jdump(Path(work) / "draft.candidates.json", payload)
    core.jdump(Path(work) / "draft.template.json", payload)
    return payload
_PDF_PAGE = (b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
             b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
             b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n")
_PDF_SCAN_BODY = (_PDF_PAGE + b"4 0 obj\n<< /Length 24 >>\n"
                  b"stream\nq 612 0 0 792 0 0 cm Q\nendstream\nendobj\n")
def _pdf(body, enc=False):
    trailer = b"/Encrypt << /Filter /Standard >>" if enc else b"/Root 1 0 R"
    return b"%PDF-1.4\n" + body + b"trailer\n<< " + trailer + b" >>\n%%EOF\n"
FIXTURES = {
    "encrypted.pdf": _pdf(_PDF_PAGE, enc=True),
    "scan_only.pdf": _pdf(_PDF_SCAN_BODY),
    "legacy.doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 96,
    "broken.docx": b"PK\x03\x04" + b"this is not a zip container" * 3,
    "empty.md": b"",
    "dup_a/run-notes.md": b"# Run notes\nBatch B-17 ELISA readout; see plate sheet.\n",
    "dup_b/run-notes.md": b"# Run notes\nBatch B-17 ELISA readout; see plate sheet.\n",
    "denied/private.md": b"# Private\nRestricted protocol; index presence only.\n",
}
FIXTURE_EXPECT = {
    "encrypted.pdf": "encrypted", "scan_only.pdf": "no_text_layer", "legacy.doc": "unsupported_legacy",
    "broken.docx": "corrupt", "empty.md": "empty_file", "dup_a/run-notes.md": "ok",
    "dup_b/run-notes.md": "ok", "denied/private.md": "permission_denied",
}
def fixtures_run(work):
    base = Path(work) / "fixtures"
    for rel, data in FIXTURES.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    rows, ok_all = [], True
    for rel, want in FIXTURE_EXPECT.items():
        p = base / rel
        decl = {"permission": "denied"} if rel.startswith("denied/") else None
        try:
            rec = core.index_doc(p, rel, "FX-" + rel.split("/")[-1], decl, base, base)
            got = rec.get("status")
        except Exception as e:  # noqa: BLE001
            got = "exception:" + type(e).__name__
        ok = got == want
        ok_all = ok_all and ok
        rows.append({"fixture": rel, "bytes": p.stat().st_size, "expected": want, "got": got, "ok": ok})
    dup = [core.index_doc(base / r, r, "FX-" + r.split("/")[-1], None, base, base)
           for r in ("dup_a/run-notes.md", "dup_b/run-notes.md")]
    groups, excluded, conflicts = rules.dedupe(dup)
    kinds = [g.get("kind") for g in groups]
    dup_ok = "identical_copy" in kinds and bool(excluded)
    rep = {"fixtures": rows, "all_expected": ok_all, "duplicate_group_kind": kinds,
           "duplicate_excluded": len(excluded), "duplicate_ok": dup_ok,
           "ok": bool(ok_all and dup_ok), "checked_at": core.now()}
    core.jdump(Path(work) / "fixtures_report.json", rep)
    return rep
def cmd_fixtures(args):
    ctx = load_ctx(args)
    rep = fixtures_run(ctx["work"])
    core.log_line(ctx["work"], "fixtures", "ok=%s" % rep["ok"])
    P(f"[fixtures] expected-status={rep['all_expected']} duplicate={rep['duplicate_ok']} "
      f"({rep['duplicate_excluded']} excluded) ok={rep['ok']}")
    for r in rep["fixtures"]:
        P(f"  {'ok ' if r['ok'] else 'BAD'} {r['fixture']}: expected {r['expected']} got {r['got']}")
    return 0
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
    cand = write_candidates(work, case, index, queries)
    ledger = rules.filter_ledger(global_conds(case), docs)
    core.jdump(work / "filters_ledger.json", {"global_filters": ledger})
    write_partial(out, meta, index, queries)
    core.log_line(work, "init", "docs=%d queries=%d digest=%s"
                  % (len(docs), len(queries), index.get("index_digest")))
    P(f"[{VERSION}] init case={meta.get('case_id')} root={index.get('library_root')}")
    P(f"docs={len(docs)} indexed={index['scan_stats'].get('indexed')} sections={secs} "
      f"paragraphs={paras} queries={len(queries)} digest={index.get('index_digest')}")
    P(f"work={work} out={out}  候选工作稿: {work / 'draft.candidates.json'} "
      f"({len(cand.get('queries') or [])} 条已预填引文)")
    P("  next: python3 -B scripts/main.py show   (候选工作稿可由 Agent 直接复核后另存为 draft.json)")
    for e in (core.STATE["errors"] + [])[:5]:
        P(f"  ! {e}")
    return 0
def cmd_show(args):
    ctx = load_ctx(args)
    index, case = ctx["index"], ctx["case"]
    docs = index.get("docs") or []
    A = args
    P(f"=== CASE {ctx['meta'].get('case_id')} digest={index.get('index_digest')} "
      f"root={index.get('library_root')} ({index.get('root_source')})")
    ti = str(ctx["meta"].get("task_instruction") or "")[:800]
    if ti:
        P("--- task_instruction ---")
        P(ti)
    for q in core.find_queries(case):
        cs = [rules.filter_text(c) for c in query_conds(case, q)]
        P(f"[{q['query_id']}] {q['question']}" + ("    filters: " + "; ".join(cs) if cs else ""))
    P("--- docs (%d) 过滤台账: " % len(docs) + "; ".join(
        "%s=%s/%s" % (r["filter"], r["kept"], r["kept"] + r["removed"])
        for r in rules.filter_ledger(global_conds(case), docs)))
    lines, shown = [], 0
    limit = max(1, int(A.limit or 160))
    greps = [g.lower() for g in (A.grep or [])]
    for d in docs:
        pg = d.get("pages") or {}
        head = ("== %s  %s  type=%s ver=%s pages=%s label=%s(%s) perm=%s status=%s sha=%s paras=%d"
                % (d.get("doc_id"), d.get("path"), d.get("type"), d.get("version"), pg.get("count"),
                   pg.get("label_source"), pg.get("page_offset"), d.get("permission"), d.get("status"),
                   str(d.get("sha256_16") or "")[:12], len(d.get("paragraphs") or [])))
        for k in ("duplicate_of", "older_version_of"):
            if d.get(k):
                head += " %s=%s" % (k, d[k])
        if A.doc and str(d.get("doc_id")) != str(A.doc):
            continue
        lines.append(head)
        if d.get("aliases"):
            lines.append("   aliases: " + " | ".join(d["aliases"]))
        if d.get("status") != "ok":
            lines.append("   !! " + (", ".join(d.get("notes") or []) or d.get("status")))
            continue
        if A.open:
            for s in d.get("sections") or []:
                lines.append("   - %s L%s p%s/pp%s [%dp] %s"
                             % (s.get("section_id"), s.get("level"), s.get("page_physical"),
                                s.get("page_printed"), len(s.get("paragraph_ids") or []),
                                s.get("title")))
            continue
        for p in d.get("paragraphs") or []:
            if greps and not any(g in (p.get("text") or "").lower() for g in greps):
                continue
            if shown >= limit:
                continue
            body = p.get("text") or ""
            if not A.full and len(body) > 400:
                body = body[:400] + "…"
            tag = p.get("source") if p.get("source") not in (None, "body") else ""
            lines.append("   %s p%s/pp%s [%s] %s :: %s"
                         % (p.get("pid"), p.get("page_physical"), p.get("page_printed"),
                            p.get("section_id"), tag, body))
            shown += 1
    P("\n".join(lines))
    for f in (index.get("failures") or [])[:20]:
        P(f"-- failure {f.get('doc_id') or '-'} {f.get('path') or '-'} :: {f.get('reason')} :: {f.get('impact')}")
    for x in (index.get("excluded_evidence") or [])[:20]:
        P(f"-- excluded {x.get('doc_id')} {x.get('path')} :: {x.get('reason')}")
    P(f"--- printed {shown} paragraphs (limit {limit}); work draft: {ctx['work'] / 'draft.json'}")
    return 0
def cmd_check(args):
    ctx = load_ctx(args)
    index, case, work = ctx["index"], ctx["case"], ctx["work"]
    queries = core.find_queries(case)
    draft, dpath, derr = load_draft(args, work)
    rows = draft_rows(draft or {})
    fixes, warns = [], []
    if draft is None:
        fixes.append("FIX draft: %s（%s）；先写工作稿再 check" % (derr, dpath))
        rows = []
    if len(rows) != len(queries):
        fixes.append("FIX coverage: 工作稿 %d 条 / 案例 %d 问；每问一条" % (len(rows), len(queries)))
    bad_st = [r.get("status") for r in rows if str(r.get("status") or "").strip() not in QSTAT]
    if bad_st:
        fixes.append("FIX status: 非法 %s；允许 %s" % (bad_st[:5], list(QSTAT)))
    pairs = match_row(queries, rows)
    conds_all = {q["query_id"]: query_conds(case, q) for q in queries}
    vhit = 0
    for q, row in pairs:
        qid = q["query_id"]
        if row is None:
            fixes.append("FIX cover %s: 缺该问条目" % qid)
            continue
        entry = verify_row(q, row, index, conds_all[qid])
        vhit += len(entry["evidence"])
        for rej in entry["rejected_evidence"]:
            if rej.get("reason", "").startswith("quote_"):
                sug = rej.get("suggestion") or {}
                fixes.append("FIX quote %s: %s :: %r -> 最接近 %s p%s/pp%s「%s」"
                             % (qid, rej.get("reason"), rej.get("quote", "")[:60],
                                sug.get("paragraph_id"), sug.get("page_physical"),
                                sug.get("page_printed"), (sug.get("snippet") or "")[:60]))
            else:
                warns.append("WARN evidence %s: %s %s" % (qid, rej.get("reason"), rej.get("path")))
        if entry["status"] in ("answered", "partially_answered") and not entry["evidence"]:
            fixes.append("FIX evidence %s: 草稿状态 %s 但无通过校验的引文（%d 条被拒，见 WARN）"
                         % (qid, str((row or {}).get("status") or "-"),
                            len(entry["rejected_evidence"])))
        if entry["status"] in ("not_found", "blocked_by_filter") and not entry.get("scope_provided"):
            fixes.append("FIX scope %s: 空结果必须写 search_scope" % qid)
    ledger = rules.filter_ledger(global_conds(case), index.get("docs") or [])
    unsat = [r["filter"] for r in ledger if not r["satisfiable"]]
    st_of = [STATUS_ALIAS.get(str((r or {}).get("status")), str((r or {}).get("status"))) for _q, r in pairs]
    if unsat and "blocked_by_filter" not in st_of and \
            any(s in ("answered", "partially_answered") for s in st_of):
        fixes.append("FIX filter: 过滤条件不可满足 %s，但仍有问题被作答（疑似静默放宽）" % unsat)
    bad_ex = [x.get("path") for x in (index.get("excluded_evidence") or [])
              if core.doc_by_path(index, x.get("path")) is None]
    if bad_ex:
        warns.append("WARN excluded: %d 条排除记录未能回指索引" % len(bad_ex))
    core.jdump(work / "check_report.json",
               {"case_id": ctx["meta"].get("case_id"), "draft": str(dpath), "queries": len(queries),
                "rows": len(rows), "evidence_verified": vhit, "fixes": fixes, "warnings": warns,
                "filters_ledger": ledger,
                "blocked_queries": [q["query_id"] for q, s in zip([p[0] for p in pairs], st_of)
                                    if s == "blocked_by_filter"], "checked_at": core.now()})
    core.log_line(work, "check", "fixes=%d warns=%d evidence=%d" % (len(fixes), len(warns), vhit))
    P("[check] queries=%d rows=%d verified_evidence=%d fixes=%d warns=%d"
      % (len(queries), len(rows), vhit, len(fixes), len(warns)))
    for f in fixes[:25]:
        P("  " + f)
    for w in warns[:10]:
        P("  " + w)
    if not fixes:
        P("  PASS: 契约字段、引文逐字、覆盖与过滤执行未发现问题；可以运行 build")
    P(f"  report -> {work / 'check_report.json'}")
    return 0
def write_artifacts(payload, index, out, work):
    core.jdump(out / "index.json", index)
    core.jdump(out / "answers.json", {"case_id": payload.get("case_id"), "status": payload.get("status"),
                                      "queries": payload.get("queries"), "coverage": payload.get("coverage"),
                                      "counts": payload.get("counts")})
    core.jdump(out / "filters_log.json", {"global_filters": payload.get("filters"),
                                          "per_query": (payload.get("result") or {}).get("per_query_filters")})
    core.jdump(out / "dedupe.json", {"groups": (index.get("dedupe") or {}).get("groups"),
                                     "conflicts": (index.get("dedupe") or {}).get("conflicts"),
                                     "excluded_evidence": payload.get("excluded_evidence")})
    core.jdump(out / "failures.json", {"failures": index.get("failures") or [],
                                       "degradations": payload.get("degradations") or [],
                                       "errors": payload.get("errors") or []})
    core.write_jsonl(out / "hits.jsonl", payload.get("hits") or [])
    core.jdump(out / "verify_report.json", payload.get("verification") or {})
    lines = [f"# {payload.get('case_id')} 检索交接报告", "",
             f"- status: **{payload.get('status')}**", f"- {payload.get('summary')}", ""]
    for en in payload.get("queries") or []:
        lines.append(f"## {en.get('query_id')} {en.get('question')}")
        lines.append(f"- 状态: `{en.get('status')}`")
        for k, t in (("filters_applied", "过滤"), ("answer", "结论"), ("search_scope", "检索范围")):
            if en.get(k):
                v = en[k] if isinstance(en[k], str) else "; ".join(en[k])
                lines.append(f"- {t}: {v}")
        for ev in en.get("evidence") or []:
            lines.append(f"- 证据: `{ev.get('locator')}` | {ev.get('path')} "
                         f"({ev.get('version') or '版本未标注'}) §{ev.get('section')} "
                         f"p{ev.get('page_physical')}/pp{ev.get('page_printed')}")
            lines.append(f"  > {ev.get('quote')}")
        if en.get("rejected_evidence"):
            lines.append(f"- 拒收证据: {len(en['rejected_evidence'])} 条（见 result.json）")
        lines.append("")
    if payload.get("filters"):
        lines += ["## 过滤执行台账", "| 条件 | 保留 | 剔除 | 可满足 |", "|-|-|-|-|"]
        lines += [f"| {r.get('filter')} | {r.get('kept')} | {r.get('removed')} | {r.get('satisfiable')} |"
                  for r in payload["filters"]]
        lines.append("")
    if payload.get("excluded_evidence"):
        lines.append("## 被排除的证据（副本/旧版/无权限）")
        lines += [f"- `{x.get('path')}` — {x.get('reason')}" for x in payload["excluded_evidence"][:30]]
        lines.append("")
    core.wtext(Path(out) / "location_report.md", "\n".join(lines))
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
    core.log_line(work, "build", "status=%s evidence=%s fails=%s"
                  % (payload.get("status"), (payload.get("counts") or {}).get("evidence"),
                     ",".join(v.get("fails") or []) or "-"))
    P(f"[build {VERSION}] case={payload.get('case_id')} status={payload.get('status')} "
      f"queries={(payload.get('counts') or {}).get('queries')} evidence={(payload.get('counts') or {}).get('evidence')} "
      f"quote_hit_rate={v.get('quote_hit_rate')} fails={v.get('fails')}")
    P(f"  result -> {out / 'result.json'}  (index {out / 'index.json'})")
    return 0
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
    fix = fixtures_run(work)
    rep["fixtures_ok"] = fix["ok"]
    rep["fixtures"] = [{"fixture": r["fixture"], "expected": r["expected"], "got": r["got"], "ok": r["ok"]}
                       for r in fix["fixtures"]]
    payload["verification"] = rep
    payload["errors"] = list(payload.get("errors") or []) + core.STATE["errors"]
    payload["degradations"] = list(payload.get("degradations") or []) + core.STATE["degradations"]
    if rep["fails"] and payload.get("status") in ("ok", "partial"):
        payload["status"] = "partial"
    core.jdump(out / "result.json", payload)
    core.jdump(out / "verify_report.json", rep)
    core.jdump(work / "selfcheck_report.json", rep)
    core.log_line(work, "selfcheck", "ok=%s fails=%s fixtures=%s"
                  % (rep["ok"], ",".join(rep["fails"]) or "-", rep.get("fixtures_ok")))
    P(f"[selfcheck] status={payload.get('status')} ok={rep['ok']} fails={rep['fails']} "
      f"queries={rep['queries']} evidence={rep['evidence']} quote_hit_rate={rep['quote_hit_rate']} "
      f"fixtures={rep.get('fixtures_ok')}")
    for c in rep["checks"]:
        if not c["ok"]:
            P(f"  FAIL {c['check']}")
    if rep.get("unmatched_quotes"):
        P(f"  unmatched quotes: {len(rep['unmatched_quotes'])} (first: {rep['unmatched_quotes'][0]})")
    return 0
def cmd_all(args):
    ctx = load_ctx(args, rebuild=True)
    work = ctx["work"]
    P("== stage 1/3 init")
    cmd_init(args)
    P("== stage 2/3 build")
    cmd_build(args)
    P("== stage 3/3 selfcheck")
    cmd_selfcheck(args)
    core.log_line(work, "all", "done")
    P(f"[all {VERSION}] 完成：{ctx['out']}/result.json + 交付物；候选工作稿 {work}/draft.candidates.json；"
      f"日志 {work}/run.log")
    return 0
def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="research-file-locator: locator-grade "
                                 "retrieval over a research file library.",
                                 epilog="exit code is always 0; partial result.json is written first.")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck", "fixtures"])
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
    cmds = {"all": cmd_all, "init": cmd_init, "show": cmd_show, "check": cmd_check,
            "build": cmd_build, "selfcheck": cmd_selfcheck, "fixtures": cmd_fixtures}
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