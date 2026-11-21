#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py — kb-version-qa command line (library-04 knowledge-base repair + cited QA).

  python3 -B scripts/main.py init       # index the library, write a legal partial result.json
  python3 -B scripts/main.py show       # locator-annotated inventory + retrieval candidates
  python3 -B scripts/main.py check      # mechanical validation of /app/work/draft.json
  python3 -B scripts/main.py build      # finalise result.json + artifacts (always exits 0)
  python3 -B scripts/main.py selfcheck  # re-verify the delivered result.json

Exit code is always 0: a broken draft degrades the delivery, it never kills the run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kb  # noqa: E402
import emit  # noqa: E402
import parse as P  # noqa: E402
from parse import human, jdump, jload  # noqa: E402

VERSION = kb.VERSION
LEVELS = kb.LEVELS


# ------------------------------------------------------------------------ paths
def writable(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        probe = Path(path) / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def resolve(args):
    inp = Path(args.input or os.environ.get("KB_INPUT") or "/input")
    if not inp.is_dir():
        inp = Path.cwd() / "input"
    work = Path(args.work or os.environ.get("KB_WORK") or "/app/work")
    out = Path(args.out or os.environ.get("KB_OUT") or "/app/output")
    for cand in (work, Path.cwd() / "work", Path(tempfile.gettempdir()) / "kb_work"):
        if writable(cand):
            work = Path(cand)
            break
    for cand in (out, Path.cwd() / "output", Path(tempfile.gettempdir()) / "kb_out"):
        if writable(cand):
            out = Path(cand)
            break
    return inp, work, out


def state_path(work):
    return Path(work) / "index.json"


def fingerprint(inp, case_path):
    """Cheap freshness check so a new/changed input never gets answered from a stale index."""
    n, newest = 0, 0.0
    try:
        for p in Path(inp).rglob("*"):
            if p.is_file():
                n += 1
                newest = max(newest, p.stat().st_mtime)
    except Exception:
        pass
    try:
        newest = max(newest, Path(case_path).stat().st_mtime if case_path else 0)
    except Exception:
        pass
    return {"files": n, "newest_mtime": round(newest, 1)}


# -------------------------------------------------------------------- init stage
def do_init(args, quiet=False):
    inp, work, out = resolve(args)
    degr = []
    case_path, case_note = kb.find_case(inp, args.case)
    case = jload(case_path) if case_path else None
    if not isinstance(case, dict):
        case = {}
        degr.append({"stage": "case", "item": "case.json",
                     "detail": case_note or "case.json missing or not a JSON object",
                     "impact": "contract/questions/library hints unknown; index still built from the input tree"})
    roots, root_notes = kb.find_roots(inp, case)
    raw_q, qkey = kb.find_questions(case)
    questions = kb.normalise_questions(raw_q)
    if not questions:
        degr.append({"stage": "questions", "item": "questions",
                     "detail": "no question list recovered from case.json (tried questions/queries/tasks/...)",
                     "impact": "answers[] stays empty until a question list or draft supplies one"})
    docs, chunks, relations, errors, skipped, aux = kb.build_index(
        inp, case_path, case, roots, {"degradations": degr})
    diffs = []
    try:
        diffs = kb.version_diffs(docs, chunks, relations)
    except Exception as exc:
        degr.append({"stage": "version_diff", "item": "diff", "detail": f"{type(exc).__name__}: {exc}",
                     "impact": "no cross-version diff hints"})
    for d in docs:
        if not d["readable"]:
            degr.append({"stage": "parse", "item": d["doc_id"], "doc_id": d["doc_id"], "path": d["path"],
                         "detail": d.get("note") or "no extractable text",
                         "impact": "content not searchable; treat as missing evidence, never invent content"})
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    if not contract:
        for k in ("contract", "output_schema", "deliverable"):
            if isinstance(case.get(k), dict):
                contract = case[k]
                degr.append({"stage": "contract", "item": k,
                             "detail": f"output_contract absent; using case.json['{k}']",
                             "impact": "contract fields filled from an equivalent key"})
                break
    task_md = inp / "task.md"
    state = {
        "version": VERSION, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "input": str(inp), "work": str(work), "out": str(out),
        "case_path": str(case_path) if case_path else None,
        "case_id": case.get("case_id") or case.get("id") or case.get("caseId"),
        "task_instruction": str(case.get("task_instruction") or case.get("instruction")
                                or case.get("task") or "")[:4000],
        "task_md": (P.read_text(task_md) or "")[:3000] if task_md.is_file() else "",
        "contract": contract, "roots": [str(r) for r in roots], "root_notes": root_notes,
        "questions": questions, "question_key": qkey,
        "docs": docs, "chunks": chunks, "relations": relations, "diffs": diffs,
        "errors": errors, "skipped": skipped,
        "aux": [{"source": a.get("source"), "key": a.get("key"),
                 "records": len(a.get("records") or []), "text": (a.get("text") or "")[:1500]} for a in aux],
        "fingerprint": fingerprint(inp, case_path),
        "degradations": degr,
        "sources": [{"doc_id": d["doc_id"], "path": d["path"], "sha256": d["sha256"],
                     "type": d["type"], "size": d["size"], "permission": d["permission"]} for d in docs],
    }
    jdump(state_path(work), state)
    payload = emit.assemble(state, None)
    jdump(Path(out) / "result.json", payload)
    jdump(Path(out) / "kb_index.json", index_view(state))
    write_inventory(out, state)
    if not quiet:
        print(f"[kb-version-qa {VERSION}] init: input={inp} work={work} out={out}")
        print(f"  case={state['case_id']} docs={len(docs)} chunks={len(chunks)} questions={len(questions)} "
              f"families={len(relations)} contract_keys={len(contract)}")
        unread = [d["doc_id"] for d in docs if not d["readable"]]
        print(f"  unreadable={unread or 'none'} duplicates={len([d for d in docs if d['dup_of']])} "
              f"degradations={len(degr)}")
        print("  next: python3 -B scripts/main.py show   then write /app/work/draft.json")
    return state


def index_view(state):
    return {"generated_at": state["generated_at"], "case_id": state["case_id"], "roots": state["roots"],
            "documents": state["docs"], "version_relations": state["relations"],
            "version_diff_candidates": state["diffs"], "questions": state["questions"],
            "sidecars": state["aux"], "duplicates": [d["doc_id"] for d in state["docs"] if d["dup_of"]],
            "unreadable": [d["doc_id"] for d in state["docs"] if not d["readable"]],
            "counts": {"documents": len(state["docs"]), "chunks": len(state["chunks"]),
                       "families": len(state["relations"]), "questions": len(state["questions"])}}


def write_inventory(out, state):
    try:
        path = Path(out) / "inventory.csv"
        cols = ["doc_id", "path", "dir", "type", "ext", "size", "sha256", "permission", "readable",
                "no_text_layer", "pages", "chunks", "chars", "family", "version", "dup_of", "note"]
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for d in state["docs"]:
                w.writerow({c: d.get(c) for c in cols})
        return path
    except Exception:
        return None


def load_state(args):
    inp, work, out = resolve(args)
    p = state_path(work)
    state = jload(p) if p.is_file() else None
    if isinstance(state, dict):
        fp = fingerprint(inp, state.get("case_path"))
        if state.get("fingerprint") == fp:
            return state, work, out, False
        print("(input changed since last init: re-indexing)")
    return do_init(args, quiet=True), work, out, True


# -------------------------------------------------------------------- show stage
def cmd_show(args):
    state, work, out, built = load_state(args)
    if built:
        print("(index was missing: init ran first)")
    docs, chunks = state["docs"], state["chunks"]
    print(f"== LIBRARY: {len(docs)} documents, {len(state['relations'])} version families, {len(chunks)} chunks ==")
    print("doc_id  type   perm      p  version  family                 size      sha16             path")
    for d in docs:
        print(f"{d['doc_id']:<7} {d['type']:<6} {d['permission']:<9} {str(d['pages'] or '-'):<2} "
              f"{str(d['version'] or '-'):<8} {str(d['family'])[:22]:<22} {human(d['size']):>9} "
              f"{str(d['sha256'] or '')[:16]:<17} {d['path']}")
        if d.get("aliases") or d.get("metadata"):
            extra = dict(d.get("metadata") or {})
            if d.get("aliases"):
                extra["aliases"] = d["aliases"]
            print(f"        metadata: {json.dumps(extra, ensure_ascii=False)[:300]}")
        if not d["readable"]:
            print(f"        !! not searchable: {d.get('note')}")
    if state["relations"]:
        print("\n== VERSION FAMILIES (ordered old -> new; last = current) ==")
        for r in state["relations"]:
            print(f"{r['family']}: " + " -> ".join(f"{v['doc_id']}({v['version']})" for v in r["versions"]))
    if state["diffs"]:
        print("\n== CROSS-VERSION NUMERIC DIFF CANDIDATES (quote both sides before use) ==")
        for d in state["diffs"]:
            print(f"{d['family']} {d['older']}->{d['newer']}: only_older={d['numbers_only_older']} "
                  f"only_newer={d['numbers_only_newer']}")
    if state["aux"]:
        print("\n== METADATA / ALIAS SIDECARS ==")
        for a in state["aux"]:
            print(f"- {a['source']} ({a['key']}, {a['records']} records) {a['text'][:200]}")
    if args.doc:
        for ch in chunks:
            if ch["doc_id"].upper() == args.doc.upper():
                print(f"\n[{ch['chunk_id']} page={ch['page']} section={ch['section']}]\n{ch['text']}")
        return 0
    print("\n== QUESTION CANDIDATES (locator + verbatim excerpt; read before answering) ==")
    qs = state["questions"]
    if args.question:
        qs = [q for q in qs if str(q.get("question_id")).upper() == args.question.upper()]
    if not qs:
        print("(no questions recovered: answer what task_instruction asks and record it in draft.json)")
    for q in qs:
        print(f"\n{q.get('question_id')}: {q.get('question')}")
        for hit in kb.search(chunks, q.get("question") or "", topk=args.topk,
                             dup_ids={d["doc_id"] for d in docs if d.get("dup_of")}):
            sec = f" §{hit['section']}" if hit.get("section") else ""
            pg = hit["page"] if hit["page"] is not None else "-"
            print(f"  [{hit['doc_id']} p{pg}{sec} {hit['chunk_id']} score={hit['score']}]")
            print(f"    {hit['excerpt'][:args.width]}")
    if args.full:
        budget = args.budget
        print("\n== FULL TEXT (chunk by chunk) ==")
        for d in docs:
            if not d["readable"]:
                continue
            print(f"\n----- {d['doc_id']} {d['path']} (v{d['version']}) -----")
            for ch in chunks:
                if ch["doc_id"] != d["doc_id"]:
                    continue
                if budget <= 0:
                    print("(budget exhausted; use --doc D0x for the rest)")
                    return 0
                print(f"[{ch['chunk_id']} p{ch['page'] if ch['page'] is not None else '-'} §{ch['section']}] {ch['text']}")
                budget -= len(ch["text"])
    return 0


# ------------------------------------------------------------------- check stage
def cmd_check(args):
    state, work, out, built = load_state(args)
    if built:
        print("(index was missing: init ran first)")
    draft, dpath, err = emit.load_draft(work)
    items, st = emit.verify_draft(state, draft)
    counts = {lv: len([i for i in items if i["level"] == lv]) for lv in ("FIX", "WARN", "INFO")}
    jdump(Path(work) / "check_report.json",
          {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "draft": str(dpath), "draft_error": err,
           "stats": st, "counts": counts, "items": items})
    print(f"== CHECK {dpath} ==")
    if err:
        print(f"  [FIX] {err}")
    for it in items[:args.max_items]:
        print(f"  [{it['level']}] {it.get('item')}: {it['message']}")
        if it.get("hint"):
            print(f"        -> {it['hint']}")
    if len(items) > args.max_items:
        print(f"  ... {len(items) - args.max_items} more in {Path(work) / 'check_report.json'}")
    print(f"  claims={st['claims']} evidence={st['evidence']} quote_ok={st['quote_ok']} "
          f"quote_miss={st['quote_miss']} answered={st['answered']}/{st['questions_expected']}")
    print(f"  RESULT: {'PASS' if counts['FIX'] == 0 else 'NEEDS_FIX'}  "
          f"(FIX={counts['FIX']} WARN={counts['WARN']} INFO={counts['INFO']})")
    if counts["FIX"]:
        print("  修完再 build；build 不会因 FIX 项崩溃，但会把这些缺口写进 degradations。")
    return 0


# ------------------------------------------------------------------- build stage
def cmd_build(args):
    state, work, out, built = load_state(args)
    draft, dpath, err = emit.load_draft(work)
    payload = emit.assemble(state, draft)
    written = write_artifacts(payload, state, out)
    if write_inventory(out, state):
        written.append("inventory.csv")
    jdump(Path(out) / "kb_index.json", index_view(state))
    if "LIBRARY_REPORT.md" not in written:
        written.append("LIBRARY_REPORT.md")
    print(f"[kb-version-qa {VERSION}] build: status={payload['status']} docs={payload['counts']['documents']} "
          f"answers={len(payload['answers'])} claims={payload['counts']['claims']} "
          f"evidence={payload['counts']['evidence']} quote_hit={payload['counts']['quote_hit_rate']} "
          f"conflicts={payload['counts']['conflicts']} not_found={payload['counts']['not_found']}")
    if err:
        print(f"  (fallback) {err}: 已输出完整最小交付，缺口见 degradations")
    print(f"  wrote {len(written)} artifacts in {out}: {', '.join(written)}")
    if payload["degradations"]:
        print(f"  degradations={len(payload['degradations'])} (see result.json)")
    return 0


def cmd_selfcheck(args):
    inp, work, out = resolve(args)
    res = Path(out) / "result.json"
    payload = jload(res)
    print(f"== SELFCHECK {res} ==")
    if not isinstance(payload, dict):
        print("  [FIX] result.json 缺失或非法 JSON —— 运行 build 重新生成")
        return 0
    checks = emit.verify_payload(payload)
    for k, v in checks.items():
        print(f"  {k}: {v}")
    keys = payload.get("contract_keys") or []
    missing = [k for k in keys if k not in payload]
    print(f"  contract: {len(keys)} keys, missing={missing or 'none'}")
    bad = [e for e in (payload.get("evidence") or []) if not e.get("quote_verified")]
    if bad:
        print(f"  [FIX] {len(bad)} 条引文未通过逐字校验：{[e.get('claim_id') for e in bad][:5]}")
    cov = payload.get("coverage") or {}
    print(f"  coverage: questions {cov.get('answered_from_draft')}/{cov.get('questions_expected')} "
          f"docs {cov.get('docs_readable')}/{cov.get('docs_indexed')} quote_hit={cov.get('quote_hit_rate')}")
    print(f"  VERDICT: {'PASS' if checks.get('pass') and not bad else 'PARTIAL'}"
          + (f" (degraded: {len(payload.get('degradations') or [])})" if payload.get("degradations") else ""))
    return 0


def write_artifacts(payload, state, out):
    out = Path(out)
    written = []
    for name, obj in (("result.json", payload), ("answers.json", {"case_id": payload.get("case_id"),
                                                                 "answers": payload["answers"]}),
                      ("conflicts.json", {"conflicts": payload["conflicts"]}),
                      ("not_found.json", {"not_found": payload["not_found"]}),
                      ("operations.json", {"operations": payload["operations"]}),
                      ("kb_stats.json", payload["coverage"])):
        if P.jdump(out / name, obj):
            written.append(name)
    try:
        with open(out / "evidence.jsonl", "w", encoding="utf-8") as fh:
            for e in payload["evidence"]:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        written.append("evidence.jsonl")
    except Exception:
        pass
    try:
        (out / "LIBRARY_REPORT.md").write_text(render_report(payload, state), encoding="utf-8")
        written.append("LIBRARY_REPORT.md")
    except Exception:
        pass
    return written


def render_report(payload, state):
    L = [f"# 科研资料清单与带证问答报告（{payload.get('case_id')}）", "",
         f"- 状态：`{payload.get('status')}`　运行：kb-version-qa {VERSION}",
         f"- 输入根：{', '.join(state['roots'])}", f"- 摘要：{payload['summary']['text']}", "",
         "## 1. 文件清单（真实解析）", "",
         "| doc_id | 路径 | 类型 | 大小 | 权限 | 可检索 | 页 | 版本 | 族 | sha256(16) |",
         "|-|-|-|-|-|-|-|-|-|-|"]
    for d in payload["documents"]:
        L.append(f"| {d['doc_id']} | {d['path']} | {d['type']} | {human(d['size'])} | {d['permission']} | "
                 f"{'是' if d['readable'] else '否'} | {d.get('pages') or '-'} | {d.get('version') or '-'} | "
                 f"{d.get('family') or '-'} | {str(d.get('sha256') or '')[:16]} |")
    L += ["", "## 2. 六维度自检（文件类型/元数据/目录/重复/版本/权限）", "", "```json",
          json.dumps(payload["result"]["library"]["six_dimensions"], ensure_ascii=False, indent=1), "```", ""]
    if payload["version_relations"]:
        L += ["## 3. 版本关系", ""]
        for r in payload["version_relations"]:
            L.append(f"- **{r['family']}**：" + " → ".join(f"{c['doc_id']}({c['version']})" for c in r["chain"])
                     + f"　当前版 = `{r['current']}`")
        L.append("")
    if payload["duplicates"]:
        L += ["## 4. 重复副本", ""]
        for d in payload["duplicates"]:
            L.append(f"- `{d['path']}` 与 `{d['dup_of']}` 字节相同（{d['sha256_16']}）：保留两者并标注，不删原文件")
        L.append("")
    L += ["## 5. 问答与证据回链", ""]
    for a in payload["answers"]:
        L += [f"### {a['question_id']}　{a.get('question') or ''}", "", a["answer"] or "（无答案文本）", ""]
        for c in a["claims"]:
            L.append(f"- **{c['status']}** {c['claim']}")
            for e in c["evidence"]:
                L.append(f"    - {e['locator']} \"{e['quote'][:180]}\" verified={e['quote_verified']}")
        L.append(f"- 不确定性：`{a['uncertainty_level']}`"
                 + (f"；缺证说明：{a['missing_evidence']}" if a.get("missing_evidence") else ""))
        L.append("")
    for title, key, fmt in (("## 6. 证据冲突（双方原话，不取平均）", "conflicts", None),
                            ("## 7. 知识库无依据的问题", "not_found", None)):
        if payload[key]:
            L += [title, ""]
            for cf in payload[key]:
                if key == "conflicts":
                    L.append(f"- **{cf['topic']}**（{cf.get('reason') or '未说明原因'}）")
                    for sd in cf["sides"]:
                        L.append(f"    - {sd['doc_id']} v{sd.get('version')} p{sd.get('page')} "
                                 f"§{sd.get('section')}：\"{sd['quote'][:150]}\"")
                else:
                    L.append(f"- {cf['question_id']}：检索范围 {cf.get('searched_scope')}；"
                             f"缺 {cf.get('missing_evidence')}")
            L.append("")
    L += ["## 8. 操作记录（可复跑）", ""]
    for op in payload["operations"][:60]:
        L.append(f"- `{op['op']}` {op.get('target')}：{op.get('detail')}")
    L += ["", "## 9. 降级与限制", ""]
    if payload["degradations"]:
        for d in payload["degradations"]:
            L.append(f"- [{d.get('stage')}] {d.get('item')}：{d.get('detail')} → 影响：{d.get('impact')}")
    else:
        L.append("- 无")
    L += ["", "## 10. 复跑方式", "", "```bash",
          "python3 -B scripts/main.py init && python3 -B scripts/main.py show",
          "# 写完 /app/work/draft.json 后：",
          "python3 -B scripts/main.py check && python3 -B scripts/main.py build "
          "&& python3 -B scripts/main.py selfcheck", "```", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="kb-version-qa: research knowledge-base inventory + cited QA")
    ap.add_argument("command", nargs="?", default="init",
                    choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", help="input directory (default /input)")
    ap.add_argument("--work", help="working directory (default /app/work)")
    ap.add_argument("--out", help="output directory (default /app/output)")
    ap.add_argument("--case", help="explicit case.json path")
    ap.add_argument("--doc", help="show: dump one doc_id fully")
    ap.add_argument("--question", help="show: only this question_id")
    ap.add_argument("--topk", type=int, default=6)
    ap.add_argument("--width", type=int, default=400)
    ap.add_argument("--full", action="store_true", help="show: also dump readable full text")
    ap.add_argument("--budget", type=int, default=60000, help="show --full character budget")
    ap.add_argument("--max-items", type=int, default=40)
    ap.add_argument("--version", action="version", version=f"kb-version-qa {VERSION}")
    args = ap.parse_args(argv)
    handlers = {"init": lambda: do_init(args), "show": lambda: cmd_show(args),
                "check": lambda: cmd_check(args), "build": lambda: cmd_build(args),
                "selfcheck": lambda: cmd_selfcheck(args)}
    try:
        handlers[args.command]()
    except Exception as exc:  # never fail the harness
        print(f"[kb-version-qa {VERSION}] {args.command} degraded: {type(exc).__name__}: {exc}")
        try:
            _, work, out = resolve(args)
            p = Path(out) / "result.json"
            if not p.is_file():
                jdump(p, {"case_id": None, "status": "failed", "answers": [], "documents": [],
                          "errors": [{"stage": args.command, "error": f"{type(exc).__name__}: {exc}"}],
                          "degradations": [{"stage": args.command, "item": "runtime", "detail": str(exc),
                                            "impact": "minimal envelope only"}],
                          "coverage": {}, "runtime": {"version": VERSION}})
        except Exception:
            pass

    try:
        import finalize
        finalize.run(resolve(args)[2])
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
