#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py — sci-lit-bilingual-audit 命令行入口（五命令主路径）。

    python3 scripts/main.py init       # 建索引 + 先写合法 partial result.json
    python3 scripts/main.py show       # 打印带 locator 的段号/原文/span/术语候选
    python3 scripts/main.py check      # 机械核验工作稿
    python3 scripts/main.py build      # 由工作稿生成产物 + 无条件 finalize result.json
    python3 scripts/main.py selfcheck  # 复检产物自洽性

工程约定：
  * 退出码恒为 0——Harness 靠 stdout 的 STATUS/CHECK/BUILD/SELFCHECK 行判断结果；
  * 任何异常都写一份合法 result.json（契约字段齐、状态诚实），不留空目录；
  * 路径由 __file__ 推导，不依赖 CWD；可用 --input/--work/--output 覆盖；
  * 纯标准库、不联网、无第三方依赖。
"""
import argparse
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import align      # noqa: E402
import pipeline   # noqa: E402
import render     # noqa: E402

VERSION = render.VERSION
_resolve, _jdump, _writable = pipeline.resolve, pipeline.jdump, pipeline._writable


def empty_result(case, status, extra):
    """合法的最小 result.json：output_contract 的每个键都在（无值给 null / []）。"""
    keys = render.contract_keys(case)
    types = render.contract_field_types(case)
    res = {
        "case_id": extra.get("case_id", ""),
        "status": status,
        "skill": {"name": render.SKILL_NAME, "version": VERSION},
        "task_understanding": extra.get("task_understanding", ""),
        "sources": extra.get("sources", []),
        "summary": extra.get("summary", {}),
        "glossary": [],
        "audit_summary": {"summary": {}, "rates": {}},
        "coverage": extra.get("coverage", {}),
        "evidence": [],
        "uncertainties": extra.get("uncertainties", []),
        "pending_human": extra.get("pending_human", []),
        "degradations": extra.get("degradations", []),
        "errors": extra.get("errors", []),
        "change_log": extra.get("change_log", []),
        "outputs": extra.get("outputs", {}),
        "runtime": extra.get("runtime", {}),
    }
    for k in keys:
        res[k] = status if k == "status" else (
            [] if types.get(k) in ("array", "list") else None)
    return res


def _pages(inp):
    """init 需要文本质量指标时重读材料；任何失败都退回空列表，不阻断 init。"""
    try:
        mats, _sk, _w = align.discover(inp)
        pages = []
        for p in mats[:3]:
            pg, _k, _h, _w = align._load_material(p)
            pages.extend({"text": t} for t in pg)
        return pages
    except Exception:
        return []


def cmd_init(args):
    t0 = time.time()
    inp, work, out = _resolve(args)
    errors, degrad, changes = [], [], []
    case, task_text, cerrs = align.read_case(inp)
    errors.extend(cerrs)
    idx = pipeline.ensure_index(inp, work, errors)
    errors.extend([e for e in idx.get("errors", []) if e not in errors])
    degrad.extend(idx.get("warnings", []))
    q = align.text_quality([p.get("text", "") for p in _pages(inp)])
    st = idx.get("stats", {})
    if not idx.get("segments"):
        status = "input_error" if not idx.get("sources") else "insufficient_evidence"
        degrad.append("no_translatable_segments")
    elif q["status"] == "empty":
        status = "insufficient_evidence"
        degrad.append("no_text_layer_or_empty")
    else:
        status = "partial"
        if q["status"] == "low_quality":
            degrad.append("low_text_quality:" + ",".join(q["flags"]))
    if not os.path.isdir(inp):
        errors.append("input_dir_missing")
    if st.get("segments"):
        changes.append("init: indexed %d segments from %d source(s)"
                       % (st["segments"], len(idx.get("sources", []))))
    extra = {
        "case_id": pipeline.case_id_of(case, None),
        "sources": idx.get("sources", []),
        "summary": {"paragraphs": st.get("segments", 0), "translated": 0},
        "coverage": {"total": st.get("segments", 0), "translated": 0,
                     "missing": [s["sid"] for s in idx.get("segments", [])],
                     "coverage_rate": 0.0},
        "degradations": degrad + ["draft_not_provided_yet"],
        "errors": errors,
        "change_log": changes,
        "outputs": {"result": os.path.join(out, "result.json")},
        "runtime": {"phase": "init", "elapsed_sec": round(time.time() - t0, 2),
                    "python": sys.version.split()[0],
                    "budget": "64 req / 900 s / 16384 tok",
                    "text_quality": q},
    }
    _jdump(os.path.join(out, "result.json"), empty_result(case, status, extra))
    print("INIT: input=%s work=%s output=%s" % (inp, work, out))
    print("STATUS: %s" % status)
    print("INDEX: segments=%s words=%s bridged=%s spans=%s sources=%d terms=%d quality=%s"
          % (st.get("segments", 0), st.get("words", 0), st.get("bridged", 0),
             st.get("spans", 0), len(idx.get("sources", [])), len(idx.get("terms", [])),
             q["status"]))
    if st.get("by_type"):
        print("TYPES: " + " ".join("%s=%d" % kv for kv in st["by_type"].items()))
    for w in idx.get("warnings", [])[:8]:
        print("WARN: " + w)
    for e in errors[:6]:
        print("ERR: " + e)
    print("PARTIAL written: %s" % os.path.join(out, "result.json"))
    print("NEXT: python3 scripts/main.py show  → 读材料 → 写 %s/draft.json" % work)
    return 0


def cmd_show(args):
    inp, work, out = _resolve(args)
    errors = []
    idx = pipeline.ensure_index(inp, work, errors)
    if args.terms:
        terms = idx.get("terms", [])
        print("TERMS: %d candidates (term | count | sids | expansion)" % len(terms))
        for t in terms[: args.limit or 40]:
            print("  %-30s n=%-3d %s %s" % (t["term"][:30], t["count"], ",".join(t["sids"][:5]),
                                            ("= " + t["expansion"]) if t.get("expansion") else ""))
            if t.get("context"):
                print("      ctx: %s" % t["context"][:150])
        return 0
    segs = idx.get("segments", [])
    if not segs:
        print("SHOW: no segments (input=%s)" % inp)
        for w in idx.get("warnings", [])[:6]:
            print("WARN: " + w)
        return 0
    lo = max(1, args.start or 1)
    hi = min(len(segs), args.end or len(segs))
    print("SHOW: segments %d-%d of %d" % (lo, hi, len(segs)))
    print("COLS: sid | page | type | words   —— SRC 是唯一合法引文来源，逐字复制")
    for s in segs[lo - 1:hi]:
        flag = ""
        if s.get("bridged"):
            flag = " bridged=%s" % "-".join(str(p) for p in s["pages"])
        print("%s @p%s [%s]%s words=%d" % (s["sid"], s["page"], s["type"], flag, s["words"]))
        body = s["text"]
        cap = args.chars or 1200
        print("  SRC  : " + (body if len(body) <= cap
                             else body[:cap] + " …[+%d chars]" % (len(body) - cap)))
        if s.get("spans"):
            print("  SPANS: " + " | ".join("%s=%s" % (x["kind"], x["value"])
                                           for x in s["spans"][:14]))
        if s["type"] in ("reference", "formula"):
            print("  HINT : 可保留原文（target=原文），notes 注明 kept verbatim")
    if hi < len(segs):
        print("NEXT: python3 scripts/main.py show --from %d --to %d"
              % (hi + 1, min(len(segs), hi + 8)))
    print("REMINDER: 逐段翻译写入 %s/draft.json（每 6-10 段落盘），再跑 check" % work)
    return 0


def emergency(out, inp, exc):
    """顶层异常兜底：尽力写合法 result.json，保证不出现空产物目录。"""
    try:
        case, _t, _e = align.read_case(inp)
    except Exception:
        case = {}
    try:
        _jdump(os.path.join(out, "result.json"), empty_result(case, "input_error", {
            "degradations": ["unhandled_exception"],
            "errors": ["%s: %s" % (type(exc).__name__, str(exc)[:200])],
            "outputs": {"result": os.path.join(out, "result.json")},
            "runtime": {"phase": "emergency"}}))
    except Exception:
        pass


def build_parser():
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="科研文献双语对照 + 译后核验审计：init → show → (写 draft.json) → "
                    "check → build → selfcheck",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码恒 0；以 stdout 的 STATUS/CHECK/BUILD/SELFCHECK 行为准。")
    ap.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    sub = ap.add_subparsers(dest="cmd")
    helps = (("init", "建索引并写出合法 partial result.json"),
             ("show", "打印带 locator 的段号/原文/span/术语候选"),
             ("check", "机械核验工作稿"),
             ("build", "生成全部产物与最终 result.json"),
             ("selfcheck", "复检产物自洽性"))
    for name, helptext in helps:
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--input", help="输入目录（默认 /input，回退 ./input）")
        p.add_argument("--work", help="工作目录（默认 /app/work，回退 ./work）")
        p.add_argument("--output", help="产物目录（默认 /app/output，回退 ./output）")
        p.add_argument("--strict", action="store_true", help="有问题时退出码 1（仅本地调试）")
        if name == "show":
            p.add_argument("--from", dest="start", type=int, help="起始段号（1 基）")
            p.add_argument("--to", dest="end", type=int, help="结束段号（含）")
            p.add_argument("--chars", type=int, default=1200, help="每段原文最多打印字符数")
            p.add_argument("--terms", action="store_true", help="只打术语候选")
            p.add_argument("--limit", type=int, default=40, help="术语候选条数")
        if name == "build":
            p.add_argument("--status", choices=["answered", "partial", "insufficient_evidence",
                                                "input_error"],
                           help="只能向更保守方向覆盖 status")
            p.add_argument("--note", action="append", help="追加 change_log 记录")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    try:
        if args.cmd == "init":
            return cmd_init(args)
        if args.cmd == "show":
            return cmd_show(args)
        fn = {"check": pipeline.cmd_check, "build": pipeline.cmd_build,
              "selfcheck": pipeline.cmd_selfcheck}[args.cmd]
        return fn(args) or 0
    except SystemExit:
        return 0
    except Exception as e:
        traceback.print_exc()
        try:
            inp, _w, out = _resolve(args)
        except Exception:
            inp, out = os.getcwd(), os.path.join(os.getcwd(), "output")
            _writable(out)
        emergency(out, inp, e)
        print("STATUS: input_error (unhandled %s; emergency result.json written)"
              % type(e).__name__)
        return 0


if __name__ == "__main__":
    sys.exit(main())
