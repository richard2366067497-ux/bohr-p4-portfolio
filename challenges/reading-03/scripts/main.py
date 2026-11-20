#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py — 单命令入口（all）与增强子命令（init / show / check / build / selfcheck / compare）。

  all        一次跑完：索引 → 草稿 → 核验 → 产物（无草稿也产出完整契约与全部产物，退出码 0）
  init       写 work/index.json 与 work/draft.json 骨架（已有草稿不覆盖）
  show       打印索引/草稿/核验摘要
  check      只核验，写 work/check_report.json（恒退出 0，失败项在 JSON 里）
  build      按现有索引与草稿写产物（等价于 all 的重跑）
  selfcheck  在 work/_selfcheck 里空跑一遍并逐项自检，写 work/selfcheck_report.json
  compare    基线搬运 vs 本 Skill 的可核验差异，写 work/compare_report.json

产物目录（--output）：result.json / paragraph_pairs.jsonl / audit_report.json / glossary.json /
bilingual_review.md / run_log.txt。工作目录（--work）：index.json / draft.json / check_report.json。
"""
import argparse
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import audit
import core
from report import (OUT_FILES, SKILL_NAME, VERSION, audit_report, build_claims, build_changes,
                    build_evidence, build_pairs, build_result, build_uncertainties, check_report,
                    clean, contract_keys, contract_types, glossary_doc, glossary_out, match_key,
                    mkdirp, read_json, render_markdown, wjson, write_outputs, wtext)

COMMANDS = ("all", "init", "show", "check", "build", "selfcheck", "compare")
DEFAULT_KEYS = ["case_id", "status", "result", "claims", "uncertainties"]
SWEEP = re.compile(
    r"\[\s*待写\s*\]|待写|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b|"
    r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|\bnull\b|\bNone\b|\bN/?A\b|"
    r"^\s*\.\.\.\s*$|<[A-Za-z_][\w /-]*>|example\.com|lorem ipsum|"
    r"^(string|path|array|object|number|boolean|value|示例)$", re.I | re.M)


# ------------------------------------------------------------------ 基础工具


def rel(path, base):
    try:
        return os.path.relpath(path, base).replace("\\", "/")
    except ValueError:
        return path


def sec(t0):
    return round(time.perf_counter() - t0, 4)


# ------------------------------------------------------------------ 契约


# ------------------------------------------------------------------ 草稿


def draft_entries(draft):
    segs = (draft or {}).get("segments") or (draft or {}).get("items") or []
    out = {}
    if isinstance(segs, dict):
        for k, v in segs.items():
            out[str(k)] = dict(v) if isinstance(v, dict) else {"sid": str(k), "target": str(v or "")}
    elif isinstance(segs, list):
        for e in segs:
            if isinstance(e, dict):
                sid = str(e.get("sid") or e.get("id") or "").strip()
                if sid:
                    out[sid] = e
    return out


def load_draft(work, src=None):
    """草稿查找顺序：work/draft.json → 输入目录/draft.json → 输入目录/draft.sample.json。

    Agent 路径把草稿写进 work；随手试跑示例时草稿就放在用例目录里，两种都能命中。
    """
    cands = [os.path.join(work, "draft.json")]
    if src:
        cands += [os.path.join(src, "draft.json"), os.path.join(src, "draft.sample.json")]
    path = ""
    for c in cands:
        if os.path.isfile(c):
            path = c
            break
    if not path:
        return {}, "absent"
    draft = read_json(path)
    if not isinstance(draft, dict):
        return {}, "unusable"
    if not draft:
        return {}, "empty"
    return draft, "loaded"


def draft_state(draft, state, index):
    entries = draft_entries(draft)
    sids = set(s["sid"] for s in index.get("segments", []))
    hit = len(sids & set(entries.keys()))
    if state != "loaded":
        return state, entries, hit
    if not sids:
        return "loaded_no_segments", entries, 0
    if hit == 0:
        return "unusable_sample", entries, 0
    return "usable", entries, hit


def draft_skeleton(case, index):
    """给 Agent 的工作稿骨架：每段带原文/定位/类型/候选术语，target 留空待填。"""
    terms = index.get("terms", [])
    locked_terms = []
    skel = {"case_id": str(case.get("case_id") or ""), "segments": [], "glossary": [],
            "result_fields": {}, "uncertainties": [], "task_understanding": ""}
    for s in index.get("segments", []):
        mine = [t["term"] for t in terms if s["sid"] in t.get("sids", [])][:6]
        skel["segments"].append({
            "sid": s["sid"], "locator": s["locator"], "type": s["type"],
            "section": s.get("section", "body"), "quote": s["text"], "source": s["text"],
            "target": "", "terms": mine, "uncertain": False, "notes": "", "basis": ""})
    for t in terms[:24]:
        sid = (t.get("sids") or [""])[0]
        seg = next((x for x in index.get("segments", []) if x["sid"] == sid), None)
        quote = ""
        if seg:
            ctx = t.get("context") or ""
            found, _off, matched = core.quote_find(seg["text"], ctx)
            quote = matched if found else seg["text"][:120]
        if t["term"] not in locked_terms:
            locked_terms.append(t["term"])
            skel["glossary"].append({"term": t["term"], "target": "", "quote": quote,
                                     "sid": sid, "expansion": t.get("expansion", ""),
                                     "basis": "候选（出现 %d 次）" % t.get("count", 1)})
    return skel


# ------------------------------------------------------------------ 派生内容


# ------------------------------------------------------------------ 渲染


# ------------------------------------------------------------------ 主流程


def run_pipeline(inp, out, work, t0, save_work=True):
    timings = {}
    ctx = {"errors": [], "degradations": [], "warnings": []}
    t = time.perf_counter()
    index = core.build_index(inp)
    timings["index"] = sec(t)
    case, task_text, cerrs = core.read_case(inp)
    ctx["errors"].extend(cerrs)
    ctx["errors"].extend(index.get("errors", []))
    case_id = str(case.get("case_id") or "").strip()
    if not case_id:
        case_id = os.path.basename(os.path.abspath(inp)) or "case_input"
        ctx["warnings"].append("case_id_missing:使用输入目录名兜底")
    keys = contract_keys(case)
    if not keys:
        keys = list(DEFAULT_KEYS)
        ctx["warnings"].append("output_contract_missing:使用 SKILL.md 默认契约键")
    src_lang = str(case.get("language") or "").strip() or "en"
    tgt_lang = str(case.get("target_language") or "").strip() or "zh"
    ctx.update({"case_id": case_id, "contract_keys": keys,
                "contract_types": contract_types(case), "target_lang": tgt_lang,
                "source_lang": src_lang})
    if task_text.strip():
        first = core.norm_ws(task_text)[:160]
        ctx["task_understanding"] = "输入任务说明：" + first
    else:
        ctx["task_understanding"] = "把材料按语义切段并做双语对照，产出可核验的段落对与核验记录"
    if save_work:
        wjson(os.path.join(work, "index.json"), index)

    t = time.perf_counter()
    draft, dstate = load_draft(work, inp)
    dstate, entries, hit = draft_state(draft, dstate, index)
    timings["draft"] = sec(t)
    if dstate in ("absent", "empty", "unusable", "unusable_sample"):
        ctx["degradations"].append("draft_" + dstate)
    if dstate == "unusable_sample":
        ctx["degradations"].append("draft_sids_match_zero_segments:按无草稿处理，不臆造译文")
        entries = {}
    if index.get("warnings"):
        for w in index["warnings"]:
            ctx["degradations"].append(w)
    if index.get("skipped"):
        ctx["degradations"].append("skipped_non_material_files:%d" % len(index["skipped"]))
    for s in index.get("sources", []):
        if s.get("extractor", "").startswith("builtin"):
            ctx["degradations"].append("pdf_builtin_extractor:%s" % s.get("path", ""))

    t = time.perf_counter()
    checker = audit.Checker(index, draft if dstate == "usable" else {}, keys, tgt_lang,
                            derivable=[k for k in keys if match_key(k)])
    res = checker.run(draft if dstate == "usable" else {})
    derived = audit.derive_status(res["coverage"], res["summary"]["fail"],
                                  len(index.get("segments", [])),
                                  empty_text=not index.get("segments"))
    requested = str(draft.get("status") or "").strip() if dstate == "usable" else ""
    status, note = audit.enforce_status(requested, derived)
    if note:
        ctx["degradations"].append(note)
    timings["check"] = sec(t)

    t = time.perf_counter()
    glossary = glossary_out(draft if dstate == "usable" else {}, index, res)
    pairs = build_pairs(index, entries if dstate == "usable" else {}, res, glossary)
    claims = build_claims(index)
    uncertainties = build_uncertainties(res, entries if dstate == "usable" else {}, dstate, index)
    evidence = build_evidence(index, pairs, glossary, res)
    sources = index.get("sources") or [{"path": "(未发现材料)", "kind": "empty_input",
                                        "extractor": "absent", "pages": 0, "chars": 0}]
    if not index.get("sources"):
        ctx["degradations"].append("no_material_files_found")
    summary = {"segments": len(index.get("segments", [])),
               "translated": res.get("coverage", {}).get("translated", 0),
               "glossary_locked": len([g for g in glossary if g["status"] == "locked"]),
               "glossary_candidate": len([g for g in glossary if g["status"] == "candidate"]),
               "audit_pass": res["summary"]["pass"], "audit_fail": res["summary"]["fail"],
               "audit_warn": res["summary"]["warn"],
               "spans_protected": index.get("stats", {}).get("spans", 0),
               "bridged_segments": index.get("stats", {}).get("bridged", 0)}
    human = []
    for c in res.get("checks", []):
        if c["status"] == "fail" and len(human) < 40:
            human.append({"check": c["check"], "sid": c["sid"], "detail": c["detail"],
                          "action": "对照原文修正该段译文后重跑 build"})
    outputs = {}
    ctx.update({"pairs": pairs, "glossary": glossary, "claims": claims,
                "uncertainties": uncertainties, "evidence": evidence, "sources": sources,
                "summary": summary, "human_review": human, "draft_state": dstate,
                "draft_hits": hit, "task_text": task_text})
    ctx["changes"] = build_changes(index, dstate, res, OUT_FILES, timings)
    timings["build"] = sec(t)
    return index, case, res, status, ctx, timings, draft


def do_build(inp, out, work, t0, save_work=True):
    index, case, res, status, ctx, timings, draft = run_pipeline(inp, out, work, t0, save_work)
    total = sec(t0)
    ctx["outputs"] = dict((n, n) for n in OUT_FILES)
    segs = len(index.get("segments", []))
    pairs_n = len(ctx.get("pairs", []))
    translate_s = round(timings.get("index", 0) + timings.get("draft", 0)
                        + timings.get("check", 0) + timings.get("build", 0), 4)
    ctx["runtime"] = {
        "total_seconds": total, "timings": timings,
        "efficiency": {
            "segments": segs, "pairs": pairs_n,
            "seconds_per_segment": round(translate_s / segs, 5) if segs else 0,
            "seconds_per_pair": round(translate_s / pairs_n, 5) if pairs_n else 0,
            "manual_baseline_minutes_per_segment": 3.0,
            "automated_minutes_estimate": round(translate_s / 60.0, 3),
            "note": "耗时取真实运行计时；人工基线按每段 3 分钟（切段+查术语+对照+校对）折算，仅作效率对照口径",
        },
        "python": sys.version.split()[0], "stdlib_only": True,
        "network": False, "deterministic": True}
    result = build_result(case, index, draft, ctx["draft_state"], res, status, ctx)
    review = render_markdown(case, index, ctx["pairs"], ctx["glossary"], res, status, ctx)
    log = ("skill=%s version=%s\ncommand=build\ncase=%s\ndraft=%s segments=%d translated=%d\n"
           "index_seconds=%s draft_seconds=%s check_seconds=%s build_seconds=%s total_seconds=%s\n"
           "status=%s audit_fail=%d audit_warn=%d\n"
           % (SKILL_NAME, VERSION, ctx["case_id"], ctx["draft_state"],
              len(index.get("segments", [])), ctx["summary"]["translated"],
              timings.get("index"), timings.get("draft"), timings.get("check"),
              timings.get("build"), total, status, res["summary"]["fail"], res["summary"]["warn"]))
    payload = {"result.json": result, "paragraph_pairs.jsonl": ctx["pairs"],
               "audit_report.json": audit_report(ctx["case_id"], index, res, status, ctx),
               "glossary.json": glossary_doc(ctx, index), "bilingual_review.md": review,
               "run_log.txt": log}
    written = write_outputs(out, payload)
    wjson(os.path.join(work, "check_report.json"), check_report(ctx["case_id"], index, res,
                                                                status, ctx))
    if save_work:
        wjson(os.path.join(work, "index.json"), index)
    return {"written": written, "status": status, "result": result, "index": index,
            "res": res, "runtime": ctx["runtime"], "ctx": ctx}


# ------------------------------------------------------------------ 子命令


def cmd_all(a, t0):
    mkdirp(a.work)
    mkdirp(a.output)
    out = do_build(a.input, a.output, a.work, t0)
    print("status=%s outputs=%d segments=%d translated=%d audit_fail=%d"
          % (out["status"], len(out["written"]), out["index"].get("stats", {}).get("segments", 0),
             out["ctx"]["summary"]["translated"], out["res"]["summary"]["fail"]))
    print("wrote: " + ", ".join(out["written"]))
    return 0


def cmd_init(a, t0):
    mkdirp(a.work)
    index = core.build_index(a.input)
    case, task_text, cerrs = core.read_case(a.input)
    wjson(os.path.join(a.work, "index.json"), index)
    path = os.path.join(a.work, "draft.json")
    if os.path.isfile(path):
        print("draft.json 已存在，保留不覆盖（如需重建请先删除）")
    else:
        skel = draft_skeleton(case, index)
        wjson(path, skel)
        print("wrote draft.json skeleton (segments=%d, glossary=%d)"
              % (len(skel["segments"]), len(skel["glossary"])))
    print("index.json: segments=%d chars=%d warnings=%d"
          % (len(index.get("segments", [])), index.get("text_chars", 0),
             len(index.get("warnings", []))))
    if cerrs:
        print("case.json: " + ", ".join(cerrs))
    return 0


def sid_set(spec):
    """解析 --sids：支持 S001,S003 与 S001-S008 区间（长文按批推进时只看当前批）。"""
    out = set()
    for part in str(spec or "").replace(" ", "").split(","):
        if not part:
            continue
        m = re.match(r"^([A-Za-z]*)(\d+)-([A-Za-z]*)(\d+)$", part)
        if m:
            pre, a, _pre2, b = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            for i in range(a, b + 1):
                out.add("%s%03d" % (pre or "S", i))
        else:
            out.add(part)
    return out


def cmd_show(a, t0):
    index = read_json(os.path.join(a.work, "index.json")) or core.build_index(a.input)
    draft, dstate = load_draft(a.work, a.input)
    dstate, entries, hit = draft_state(draft, dstate, index)
    print("segments=%d by_type=%s chars=%d"
          % (len(index.get("segments", [])), json.dumps(index.get("stats", {}).get("by_type", {}),
                                                        ensure_ascii=False),
             index.get("text_chars", 0)))
    print("draft=%s entries=%d matched=%d" % (dstate, len(entries), hit))
    print("terms=%d" % len(index.get("terms", [])))
    for t in index.get("terms", [])[:10]:
        print("  - %s (n=%d, sids=%s)" % (t["term"], t.get("count", 0),
                                          ",".join(t.get("sids", [])[:4])))
    cr = read_json(os.path.join(a.work, "check_report.json"))
    if isinstance(cr, dict):
        print("last_check: status=%s fail=%s warn=%s"
              % (cr.get("status"), json.dumps(cr.get("fail_items", {}), ensure_ascii=False),
                 json.dumps(cr.get("warn_items", {}), ensure_ascii=False)))
    w = sid_set(a.sids)
    if w:
        print("batch: sids=%s" % ",".join(sorted(w)))
        for s in index.get("segments", []):
            if s["sid"] in w:
                e = entries.get(s["sid"]) or {}
                print("  %s %s %s target=%s" % (s["sid"], s["locator"], s["type"],
                                                "有" if str(e.get("target") or "").strip() else "缺"))
    return 0


def cmd_check(a, t0):
    mkdirp(a.work)
    index = core.build_index(a.input)
    case, _task, cerrs = core.read_case(a.input)
    keys = contract_keys(case) or list(DEFAULT_KEYS)
    draft, dstate = load_draft(a.work, a.input)
    dstate, entries, hit = draft_state(draft, dstate, index)
    checker = audit.Checker(index, draft if dstate == "usable" else {}, keys,
                            str(case.get("target_language") or "zh"),
                            derivable=[k for k in keys if match_key(k)])
    res = checker.run(draft if dstate == "usable" else {})
    status = audit.derive_status(res["coverage"], res["summary"]["fail"],
                                 len(index.get("segments", [])),
                                 empty_text=not index.get("segments"))
    ctx = {"draft_state": dstate, "case_id": str(case.get("case_id") or "")}
    rep = check_report(ctx["case_id"], index, res, status, ctx)
    wjson(os.path.join(a.work, "check_report.json"), rep)
    wjson(os.path.join(a.work, "index.json"), index)
    print("status=%s fail=%d warn=%d pass=%d"
          % (status, res["summary"]["fail"], res["summary"]["warn"], res["summary"]["pass"]))
    for k, v in sorted(res["summary"]["fail_by_check"].items()):
        print("  FAIL %s x%d" % (k, v))
    for k, v in sorted(res["summary"]["warn_by_check"].items()):
        print("  WARN %s x%d" % (k, v))
    print("wrote work/check_report.json")
    return 0


def cmd_build(a, t0):
    mkdirp(a.work)
    mkdirp(a.output)
    return cmd_all(a, t0)


def cmd_compare(a, t0):
    mkdirp(a.work)
    out = do_build(a.input, a.output, a.work, t0)
    ctx, res, index = out["ctx"], out["res"], out["index"]
    segs = len(index.get("segments", []))
    base = {"paragraphs_aligned": 0, "locators": 0, "span_checks": 0, "glossary_locked": 0,
            "audit_checks": 0, "checked_fields": 0, "deliverables": 1,
            "note": "基线＝把每页原文整段贴进一个 markdown，不切段、不抽 span、不核验、不给定位"}
    mine = {"paragraphs_aligned": len(ctx["pairs"]), "locators": len(ctx["pairs"]),
            "span_checks": sum(1 for c in res.get("checks", [])
                               if c["check"] in ("protected_numbers", "citations",
                                                 "figure_table_refs", "equation_tags")),
            "glossary_locked": len([g for g in ctx["glossary"] if g["status"] == "locked"]),
            "audit_checks": len(res.get("checks", [])), "checked_fields": 6,
            "deliverables": len(OUT_FILES), "segments": segs,
            "translated": ctx["summary"]["translated"],
            "fail": res["summary"]["fail"], "warn": res["summary"]["warn"]}
    rep = {"case_id": ctx["case_id"], "baseline": base, "with_skill": mine,
           "gaps": [{"metric": k, "baseline": base[k], "with_skill": mine[k]}
                    for k in ("paragraphs_aligned", "locators", "span_checks",
                              "glossary_locked", "audit_checks", "deliverables")],
           "method": "同一输入、同一产物口径；基线为随包确定性模拟，非官方对照",
           "disclosure": "本文件不宣称官方 A/B 数据；仅用于说明缺口类别与可核验性差异"}
    wjson(os.path.join(a.work, "compare_report.json"), rep)
    print(json.dumps(rep["gaps"], ensure_ascii=False))
    print("wrote work/compare_report.json / output/%d files" % len(out["written"]))
    return 0


def degrade_case(base, t0):
    """异常场景自检：空文件 + 坏 json + 只有占位符的 txt，验证降级路径仍产出完整契约。

    返回 (ok, detail)，供 selfcheck 的 degrade_graceful 项使用；只写 work/_selfcheck 下。
    """
    inp = os.path.join(base, "case")
    so, sw = os.path.join(base, "output"), os.path.join(base, "work")
    mkdirp(os.path.join(inp, "materials"))
    mkdirp(so)
    mkdirp(sw)
    try:
        wjson(os.path.join(inp, "case.json"), {"case_id": "selfcheck-degrade", "language": "en",
                                               "output_contract": None})
        with open(os.path.join(inp, "materials", "empty.md"), "wb") as f:
            f.write(b"")
        wtext(os.path.join(inp, "materials", "broken.json"), "{not json,,}")
        wtext(os.path.join(inp, "materials", "notes.txt"), "[待写]\n")
        out = do_build(inp, so, sw, t0)
        keys = contract_keys(read_json(os.path.join(inp, "case.json"), {}) or {}) or DEFAULT_KEYS
        echo = out["result"].get("output_contract") or {}
        miss = [k for k in keys if k not in echo]
        empty = [k for k in keys if echo.get(k) in (None, "", [], {})]
        bad = []
        for n in OUT_FILES:
            p = os.path.join(so, n)
            if not os.path.isfile(p) or os.path.getsize(p) < 40:
                bad.append(n)
            else:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    if SWEEP.search(f.read()):
                        bad.append(n + "(占位符)")
        ok = not (miss or empty or bad)
        return ok, ("降级路径 status=%s；缺失键=%s 空值=%s 产物问题=%s"
                    % (out["status"], miss or "无", empty or "无", bad or "无"))
    except Exception as e:  # noqa
        return False, "降级路径异常: %s: %s" % (type(e).__name__, e)


def cmd_selfcheck(a, t0):
    """空跑一遍并逐项自检；只写 work/_selfcheck，不碰已交付的 output。"""
    base = os.path.join(a.work, "_selfcheck")
    sw, so = os.path.join(base, "work"), os.path.join(base, "output")
    mkdirp(sw)
    mkdirp(so)
    out = do_build(a.input, so, sw, t0)
    result = out["result"]
    keys = contract_keys(read_json(os.path.join(a.input, "case.json"), {}) or {}) or DEFAULT_KEYS
    echo = result.get("output_contract") if isinstance(result.get("output_contract"), dict) else {}
    checks = []

    def ck(name, ok, detail):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    ck("exit_code", True, "build 正常返回（selfcheck 恒退出 0）")
    ck("result_json", isinstance(result, dict), "result.json 可解析")
    ck("contract_echo", all(k in echo for k in keys),
       "契约键 %d/%d 已回显" % (len([k for k in keys if k in echo]), len(keys)))
    empties = [k for k in keys if echo.get(k) in (None, "", [], {})]
    ck("contract_values", not empties, "空值键: %s" % (empties or "无"))
    missing = [n for n in OUT_FILES if not os.path.isfile(os.path.join(so, n))]
    ck("deliverables", not missing, "缺失产物: %s" % (missing or "无"))
    small = [n for n in OUT_FILES if os.path.isfile(os.path.join(so, n))
             and os.path.getsize(os.path.join(so, n)) < 40]
    ck("substantive", not small, "小于 40 字节的产物: %s" % (small or "无"))
    hits = {}
    for n in OUT_FILES:
        p = os.path.join(so, n)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                found = sorted(set(m.group(0) for m in SWEEP.finditer(f.read())))
            if found:
                hits[n] = found[:6]
    ck("placeholder_sweep", not hits, "占位符命中: %s" % (json.dumps(hits, ensure_ascii=False)
                                                        if hits else "无"))
    ck("status_field", bool(result.get("status")), "status=%s" % result.get("status"))
    ck("case_id", bool(result.get("case_id")), "case_id=%s" % result.get("case_id"))
    for f in ("sources", "uncertainties", "change_records", "limits"):
        ck("field:" + f, bool(result.get(f)), "%s 非空" % f)
    pairs = [ln for ln in (open(os.path.join(so, "paragraph_pairs.jsonl"), "r",
                                encoding="utf-8") if os.path.isfile(
        os.path.join(so, "paragraph_pairs.jsonl")) else []) if ln.strip()]
    ck("pairs_rows", len(pairs) >= 1, "段落对 %d 行" % len(pairs))
    ck("degrade_graceful", *degrade_case(os.path.join(base, "degrade"), t0))
    ok = all(c["status"] == "PASS" for c in checks)
    rep = {"case_id": result.get("case_id"), "ok": ok, "checks": checks,
           "segments": len(out["index"].get("segments", [])),
           "outputs": out["written"], "runtime": out["runtime"],
           "selfcheck_dir": rel(base, a.work)}
    wjson(os.path.join(a.work, "selfcheck_report.json"), rep)
    for c in checks:
        print("%s %s — %s" % (c["status"], c["check"], c["detail"]))
    print("selfcheck: %s" % ("PASS" if ok else "FAIL"))
    return 0


def emergency(a, exc, t0):
    """任何未预期异常：仍写出完整契约与占位产物，退出 0（诚实记录异常）。"""
    ctx = {"case_id": "case_input", "contract_keys": list(DEFAULT_KEYS),
           "contract_types": {}, "target_lang": "zh", "source_lang": "en",
           "errors": ["unhandled_exception:" + type(exc).__name__ + ":" + str(exc)[:200]],
           "degradations": ["pipeline_aborted"], "warnings": [], "glossary": [], "pairs": [],
           "claims": build_claims({"segments": []}), "uncertainties": [],
           "evidence": [], "human_review": [], "sources": [], "summary": {},
           "draft_state": "absent", "task_understanding": "运行异常中止，未生成正文派生产物",
           "changes": [{"step": "pipeline", "status": "aborted",
                        "detail": type(exc).__name__}],
           "runtime": {"total_seconds": sec(t0)}}
    ctx["uncertainties"] = build_uncertainties({"coverage": {}, "relations": {}, "glossary": {}},
                                               {}, "absent", {"segments": []})
    empty_index = {"segments": [], "terms": [], "stats": {}, "sources": []}
    ctx["pairs"] = build_pairs(empty_index, {}, {}, [])
    ctx["outputs"] = dict((n, n) for n in OUT_FILES)
    res = {"checks": [], "summary": {"pass": 0, "fail": 0, "warn": 0, "fail_by_check": {},
                                     "warn_by_check": {}}, "rates": {}, "coverage": {},
           "elements": {}, "glossary": {}, "spans": {}, "relations": {}, "contract": {}}
    status = "input_error"
    result = build_result({}, empty_index, {}, "absent", res, status, ctx)
    mkdirp(a.output)
    write_outputs(a.output, {
        "result.json": result, "paragraph_pairs.jsonl": ctx["pairs"],
        "audit_report.json": audit_report("case_input", empty_index, res, status, ctx),
        "glossary.json": glossary_doc(ctx, empty_index),
        "bilingual_review.md": "# 运行异常\n\n本次运行在流水线内部异常中止，未产出正文派生产物；"
                               "异常已记录在 result.json 的 errors 字段。\n",
        "run_log.txt": "skill=%s version=%s\ncommand=aborted\ntotal_seconds=%s\nerror=%s\n"
                       % (SKILL_NAME, VERSION, sec(t0), type(exc).__name__)})
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="sci-lit-bilingual-audit: index, bilingual pair, glossary and mechanical audit")
    ap.add_argument("command", nargs="?", default="all", choices=list(COMMANDS),
                    help="all | init | show | check | build | selfcheck | compare")
    ap.add_argument("--input", default="/input", help="材料目录（默认 /input）")
    ap.add_argument("--output", default="/app/output", help="产物目录（默认 /app/output）")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--sids", default="", help="show 只看这些段：S001,S003 或 S001-S008（长文分批）")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    fn = {"all": cmd_all, "init": cmd_init, "show": cmd_show, "check": cmd_check,
          "build": cmd_build, "selfcheck": cmd_selfcheck, "compare": cmd_compare}[a.command]
    try:
        return fn(a, t0)
    except SystemExit:
        raise
    except Exception as exc:  # 绝不非零退出：异常也写合法结果
        print("warning: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        try:
            return emergency(a, exc, t0)
        except Exception:
            return 0


if __name__ == "__main__":
    sys.exit(main())
