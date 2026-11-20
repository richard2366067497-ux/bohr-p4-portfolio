#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline.py — check / build / selfcheck 的实现（main.py 负责 CLI 与 init/show）。

分离的原因：CLI 层要尽量短（Harness 的 Agent 只读 SKILL.md 里的命令），业务流程集中
在这里便于审计。本模块只做编排：调用 audit 判定、调用 render 渲染、把失败写成
degradations，绝不因为单个环节异常而放弃 finalize。
"""
import glob
import json
import os
import sys
import time

import align
import audit
import render

VERSION = render.VERSION
PH = "〔待补:%s〕"


# ------------------------------------------------------------------ 路径与 IO

def _writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def resolve(args):
    """输入/工作/产物三个目录：显式参数 > 运行契约路径 > 当前目录回退。"""
    cwd = os.getcwd()
    inp = getattr(args, "input", None)
    if not inp:
        for cand in ("/input", os.path.join(cwd, "input")):
            if os.path.isdir(cand):
                inp = cand
                break
    inp = inp or os.path.join(cwd, "input")
    work = getattr(args, "work", None)
    if not work:
        for cand in ("/app/work", os.path.join(cwd, "work")):
            if _writable(cand):
                work = cand
                break
    work = work or os.path.join(cwd, "work")
    out = getattr(args, "output", None)
    if not out:
        for cand in ("/app/output", os.path.join(cwd, "output")):
            if _writable(cand):
                out = cand
                break
    out = out or os.path.join(cwd, "output")
    _writable(work)
    _writable(out)
    return inp, work, out


def jload(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return default


def jdump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_index(work):
    return jload(os.path.join(work, "index.json"), None)


def ensure_index(inp, work, errors):
    idx = load_index(work)
    if isinstance(idx, dict) and idx.get("segments"):
        return idx
    try:
        idx = align.build_index(inp)
    except Exception as e:
        errors.append("index_build_failed:" + type(e).__name__)
        idx = {"input_dir": inp, "sources": [], "pages": [], "segments": [],
               "warnings": [], "errors": ["index_build_failed"], "stats": {}, "terms": []}
    jdump(os.path.join(work, "index.json"), idx)
    return idx


def load_draft(work, errors):
    """合并 plan.json / draft.json / draft_part_*.json；后写覆盖前写（按 sid / term）。"""
    paths = []
    for name in ("plan.json", "draft.json"):
        p = os.path.join(work, name)
        if os.path.isfile(p):
            paths.append(p)
    paths.extend(sorted(glob.glob(os.path.join(work, "draft_part_*.json"))))
    if not paths:
        return None
    merged = {"segments": {}, "glossary": [], "uncertainties": [], "decisions": [],
              "result_fields": {}, "task_understanding": "", "_sources": []}
    for p in paths:
        data = jload(p, None)
        if not isinstance(data, dict):
            errors.append("draft_unreadable:" + os.path.basename(p))
            continue
        merged["_sources"].append(os.path.basename(p))
        segs = data.get("segments") or data.get("items") or []
        if isinstance(segs, dict):
            segs = [dict(v, sid=k) if isinstance(v, dict) else {"sid": k, "target": v}
                    for k, v in segs.items()]
        for e in segs:
            if not isinstance(e, dict):
                continue
            sid = str(e.get("sid") or e.get("id") or "").strip()
            if sid:
                merged["segments"][sid] = e
        for key in ("glossary", "terms"):
            for g in (data.get(key) or []):
                if isinstance(g, dict) and (g.get("term") or g.get("source")):
                    g.setdefault("term", g.get("source"))
                    merged["glossary"].append(g)
        for key in ("uncertainties", "decisions"):
            for u in (data.get(key) or []):
                if isinstance(u, str):
                    merged[key].append(u)
                elif isinstance(u, dict):
                    merged[key].append(u.get("note") or u.get("detail")
                                        or json.dumps(u, ensure_ascii=False))
        rf = data.get("result_fields") or data.get("output_fields") or {}
        if isinstance(rf, dict):
            merged["result_fields"].update(rf)
        tu = data.get("task_understanding") or data.get("understanding") or ""
        if isinstance(tu, str) and tu.strip():
            merged["task_understanding"] = tu.strip()
    seen = {}
    for g in merged["glossary"]:
        seen[str(g.get("term")).lower()] = g
    merged["glossary"] = [seen[k] for k in sorted(seen)]
    return merged


def target_lang(case, task_text):
    for k in ("target_language", "language", "target_lang", "output_language"):
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and v.strip():
            v = v.strip().lower()
            if v.startswith(("zh", "chi", "cn", "中")):
                return "zh"
            if v.startswith("en"):
                return "en"
            return v[:2]
    blob = " ".join([str(case.get("task_instruction") or "") if isinstance(case, dict) else "",
                     task_text or ""])
    if "中文" in blob or "Chinese" in blob or "简体" in blob:
        return "zh"
    if "英文" in blob or "English" in blob:
        return "en"
    return "zh"


def case_id_of(case, draft):
    for src in (case or {}, (draft or {}).get("result_fields") or {}):
        if isinstance(src, dict):
            for k in ("case_id", "id", "task_id", "caseId"):
                v = src.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return "unknown-case"


def prepare(args):
    inp, work, out = resolve(args)
    errors, degrad = [], []
    case, task_text, cerrs = align.read_case(inp)
    errors.extend(cerrs)
    idx = ensure_index(inp, work, errors)
    errors.extend([e for e in idx.get("errors", []) if e not in errors])
    degrad.extend(idx.get("warnings", []))
    draft = load_draft(work, errors)
    return {"inp": inp, "work": work, "out": out, "case": case, "task": task_text,
            "idx": idx, "draft": draft, "errors": errors, "degrad": degrad,
            "lang": target_lang(case, task_text), "keys": render.contract_keys(case)}


# ------------------------------------------------------------------ 核验

def glossary_out(ck):
    """给工作稿术语表补上 locked/proposed/conflict 判定与定位信息。"""
    out = []
    for g in ck.glossary:
        term = (g.get("term") or "").strip()
        tgt = (g.get("target") or g.get("locked_target") or "").strip()
        if not term:
            continue
        sid = str(g.get("sid") or g.get("evidence_sid") or "").strip()
        qv = bool(g.get("quote_verified"))
        st = "locked" if (tgt and qv) else "proposed"
        out.append({"term": term, "target": tgt, "status": st,
                    "quote": g.get("quote") or "", "sid": sid,
                    "locator": (ck.by_sid.get(sid, {}) or {}).get("locator", sid),
                    "quote_verified": qv, "quote_offset": g.get("quote_offset", -1),
                    "basis": g.get("basis") or "", "expansion": g.get("expansion") or ""})
    by = {}
    for g in out:
        by.setdefault(g["term"].lower(), set()).add(g["target"])
    for g in out:
        if len(by[g["term"].lower()]) > 1:
            g["status"] = "conflict"
    return out


def run_checks(ctx, draft=None):
    d = ctx["draft"] if draft is None else draft
    ck = audit.Checker(ctx["idx"], d or {}, ctx["keys"], ctx["lang"])
    res = ck.run(d or {})
    res["_glossary_out"] = glossary_out(ck)
    return res


def _r(v):
    return "%.3f" % v if isinstance(v, (int, float)) else "n/a"


def _size(p):
    try:
        return os.path.getsize(p)
    except Exception:
        return 0


def cmd_check(args):
    ctx = prepare(args)
    res = run_checks(ctx)
    jdump(os.path.join(ctx["work"], "check_report.json"), res)
    s = res["summary"]
    print("CHECK: segments=%d pass=%d fail=%d warn=%d skip=%d"
          % (s["segments"], s["pass"], s["fail"], s["warn"], s["skip"]))
    if s["fail_by_check"]:
        print("FAIL_BY_CHECK: " + " ".join("%s=%d" % kv for kv in s["fail_by_check"].items()))
    if s["warn_by_check"]:
        print("WARN_BY_CHECK: " + " ".join("%s=%d" % kv for kv in s["warn_by_check"].items()))
    for c in res["checks"]:
        if c["status"] == "fail":
            print("  FAIL %-18s %-5s %s" % (c["check"], c["sid"] or "-", c["detail"][:140]))
    rates = res["rates"]
    print("RATES: coverage=%s glossary=%s span=%s neg=%s hedge=%s"
          % (_r(rates.get("coverage_rate")), _r(rates.get("glossary_consistency")),
             _r(rates.get("span_retention")), _r(rates.get("negation_rate")),
             _r(rates.get("hedge_rate"))))
    if ctx["draft"] is None:
        print("NO_DRAFT: 尚未写工作稿，check 无内容可验。先 show，再写 draft.json")
    print("NEXT: 修 fail 后重跑 check；满意后 python3 scripts/main.py build")
    if getattr(args, "strict", False) and s["fail"]:
        return 1
    return 0


# ------------------------------------------------------------------ build

def cmd_build(args):
    t0 = time.time()
    ctx = prepare(args)
    idx, draft, out, work = ctx["idx"], ctx["draft"], ctx["out"], ctx["work"]
    segs = idx.get("segments", [])
    errors, degrad = list(ctx["errors"]), list(ctx["degrad"])
    changes = []
    entries = dict((draft or {}).get("segments") or {})
    if draft:
        changes.append("draft: %d segment(s) from %s"
                       % (len(entries), ",".join(draft.get("_sources", []))))
    else:
        degrad.append("draft_missing:built_from_index_only")
        changes.append("build: no draft, fallback to placeholders")

    filled_ph = 0
    for s in segs:
        e = entries.get(s["sid"])
        if not isinstance(e, dict):
            entries[s["sid"]] = {"sid": s["sid"], "target": PH % s["sid"],
                                 "notes": "not translated in this run", "uncertain": False}
            filled_ph += 1
        elif not (e.get("target") or e.get("translation") or "").strip():
            e["target"] = PH % s["sid"]
            filled_ph += 1
    if filled_ph:
        degrad.append("segments_untranslated:%d" % filled_ph)

    tmp_draft = dict(draft or {})
    tmp_draft["segments"] = [dict(v, sid=k) for k, v in sorted(entries.items())]
    res = run_checks(dict(ctx, draft=tmp_draft), tmp_draft)
    cov = res["coverage"]
    fails = res["summary"]["fail"]
    derived = audit.derive_status(cov, fails, len(segs), None)
    if not segs:
        derived = "input_error" if not idx.get("sources") else "insufficient_evidence"
    final, note = audit.enforce_status(getattr(args, "status", None), derived)
    if note:
        degrad.append("status_note:" + note)
    if fails:
        degrad.append("audit_fail:%d" % fails)

    pairs = render.build_pairs(idx, entries, res)
    gloss = render.build_glossary(res, idx)
    res["_glossary_out"] = gloss
    pending, seen = [], set()
    for c in res["checks"]:
        if c["status"] != "warn":
            continue
        key = (c["check"], c["detail"][:40])
        if key in seen:
            continue
        seen.add(key)
        pending.append({"check": c["check"], "sid": c["sid"], "item": c["detail"][:180]})
    pending = pending[:25]

    output_files = {
        "result.json": os.path.join(out, "result.json"),
        "paragraph_pairs.jsonl": os.path.join(out, "paragraph_pairs.jsonl"),
        "audit_report.json": os.path.join(out, "audit_report.json"),
        "glossary.json": os.path.join(out, "glossary.json"),
        "bilingual_review.md": os.path.join(out, "bilingual_review.md"),
    }
    extra = {
        "case_id": case_id_of(ctx["case"], draft),
        "sources": idx.get("sources", []),
        "degradations": list(degrad),
        "errors": errors,
        "pending_human": pending,
        "change_log": changes + list(getattr(args, "note", None) or []),
        "outputs": output_files,
        "target_lang": ctx["lang"],
    }
    result, cstat = render.build_result(ctx["case"], idx, tmp_draft, res, pairs, gloss,
                                        final, extra)
    if cstat["nulled"]:
        result["degradations"] = list(degrad) + [
            "contract_fields_null:%d:%s" % (len(cstat["nulled"]),
                                            ",".join(cstat["nulled"][:8]))]
    result["runtime"] = {
        "phase": "build", "elapsed_sec": round(time.time() - t0, 2),
        "python": sys.version.split()[0], "budget": "64 req / 900 s / 16384 tok",
        "target_language": ctx["lang"], "segments": len(segs),
        "translated": cov.get("translated", 0),
    }
    audit_report = {
        "case_id": result["case_id"], "status": final,
        "summary": res["summary"], "rates": res["rates"],
        "coverage": {k: cov.get(k) for k in ("total", "translated", "coverage_rate",
                                             "coverage_rate_incl_skipped")},
        "missing_sids": cov.get("missing", []),
        "skipped_sids": cov.get("skipped", []),
        "uncertain_sids": cov.get("uncertain", []),
        "glossary_stats": {"locked": len(res["glossary"]["locked"]),
                           "proposed": len(res["glossary"]["proposed"]),
                           "conflicts": len(res["glossary"]["conflicts"]),
                           "consistency_rate": res["glossary"]["consistency_rate"]},
        "checks": res["checks"], "contract": cstat,
    }
    md = render.render_markdown(ctx["case"], idx, pairs, gloss, res, final, extra)
    written = render.write_outputs(out, {
        "paragraph_pairs.jsonl": pairs,
        "audit_report.json": audit_report,
        "glossary.json": {"case_id": result["case_id"], "terms": gloss,
                          "stats": audit_report["glossary_stats"]},
        "bilingual_review.md": md,
        "result.json": result,
    })
    print("BUILD: output=%s" % out)
    print("STATUS: %s" % final)
    print("FILES: " + " ".join("%s(%dB)" % (n, _size(os.path.join(out, n))) for n in written))
    print("COVERAGE: %d/%d translated, missing=%d, skipped=%d, uncertain=%d"
          % (cov.get("translated", 0), cov.get("total", 0), len(cov.get("missing", [])),
             len(cov.get("skipped", [])), len(cov.get("uncertain", []))))
    print("GLOSSARY: locked=%d proposed=%d conflict=%d consistency=%s"
          % (len(res["glossary"]["locked"]), len(res["glossary"]["proposed"]),
             len(res["glossary"]["conflicts"]), _r(res["glossary"]["consistency_rate"])))
    print("CONTRACT: filled=%d nulled=%d total=%d"
          % (len(cstat["filled"]), len(cstat["nulled"]), len(ctx["keys"])))
    if degrad:
        print("DEGRADATIONS: " + " | ".join(degrad[:6]))
    print("NEXT: python3 scripts/main.py selfcheck")
    return 0


# ------------------------------------------------------------------ selfcheck

def _read_pairs(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def cmd_selfcheck(args):
    """重新读盘复检：不复用 build 的内存态，确保产物自身自洽。"""
    inp, work, out = resolve(args)
    case, _t, _e = align.read_case(inp)
    idx = load_index(work) or {}
    keys = render.contract_keys(case)
    problems, warns = [], []
    res = jload(os.path.join(out, "result.json"), None)
    if not isinstance(res, dict):
        problems.append("result.json 缺失或不可解析")
    else:
        for k in keys:
            if k not in res:
                problems.append("契约字段缺失: %s" % k)
        if res.get("status") not in ("answered", "partial", "insufficient_evidence", "input_error"):
            problems.append("status 非法: %r" % res.get("status"))
        if not res.get("case_id"):
            warns.append("case_id 为空")
    pp = os.path.join(out, "paragraph_pairs.jsonl")
    pairs = _read_pairs(pp)
    if not os.path.isfile(pp):
        problems.append("paragraph_pairs.jsonl 缺失")
    n_seg = len(idx.get("segments", []))
    if n_seg and len(pairs) != n_seg:
        problems.append("段落对行数 %d ≠ 索引段数 %d" % (len(pairs), n_seg))
    ar = jload(os.path.join(out, "audit_report.json"), None)
    if not isinstance(ar, dict) or not ar.get("checks"):
        problems.append("audit_report.json 缺失或无可核验项")
    gl = jload(os.path.join(out, "glossary.json"), None)
    if not isinstance(gl, dict):
        problems.append("glossary.json 缺失")
    else:
        for g in gl.get("terms", []):
            if g.get("status") == "locked" and not g.get("quote_verified"):
                problems.append("术语 `%s` 标记 locked 但 quote 未命中" % g.get("term"))
    if isinstance(res, dict) and res.get("status") == "answered":
        if isinstance(ar, dict):
            if ar.get("summary", {}).get("fail"):
                problems.append("status=answered 但存在 fail 项")
            if ar.get("missing_sids"):
                problems.append("status=answered 但仍有缺失段")
        if any("〔" in (p.get("target") or "") for p in pairs):
            problems.append("status=answered 但译文仍含占位符")
    md = os.path.join(out, "bilingual_review.md")
    if not os.path.isfile(md) or _size(md) < 50:
        warns.append("bilingual_review.md 缺失或过短")
    print("SELFCHECK: case=%s pairs=%d segments=%d contract_keys=%d"
          % ((res or {}).get("case_id", "?"), len(pairs), n_seg, len(keys)))
    for p in problems:
        print("  PROBLEM: " + p)
    for w in warns:
        print("  WARN: " + w)
    verdict = "PASS" if not problems else "FAIL"
    if not problems and warns:
        verdict = "WARN"
    print("SELFCHECK: %s (%d problem, %d warn)" % (verdict, len(problems), len(warns)))
    if getattr(args, "strict", False) and problems:
        return 1
    return 0
