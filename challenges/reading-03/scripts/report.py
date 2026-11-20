#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.py — 结果装配、报告与人读视图渲染，以及工作稿读写与契约键归一。

被 main.py 调用；不单独作为入口。核心口径：契约键原样回显、取值绝不写空、
产物里不出现 null（占位符扫描器会把 null 当占位）。
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import audit
import core

VERSION = audit.VERSION
SKILL_NAME = audit.SKILL_NAME
DEFAULT_NOTE = "本字段未由材料直接给出：见 audit_report 的 coverage 与 contract 段"
OUT_FILES = ["result.json", "paragraph_pairs.jsonl", "audit_report.json", "glossary.json",
             "bilingual_review.md", "run_log.txt"]
LIMITS = [
    "纯标准库、离线、确定性：不联网、不调用模型，同一输入同一输出",
    "译文由 Agent 草稿（work/draft.json）决定；本包不代译，也不臆造译文",
    "OCR 未内置：无文本层 PDF 只用内置解析器抢救，并记 degraded 标记",
    "术语锁定需 quote 在原文逐字命中；只给候选而不强推译名",
    "语义质量（通顺、学术措辞）不在机械核验范围内，只列为人工复核项",
]
FIELD_MAP = [
    (("claim", "assert", "finding", "结论", "断言"), "claims"),
    (("uncertain", "unresolved", "manual", "risk", "不确定", "待确认"), "uncertainties"),
    (("glossary", "terminolog", "术语"), "glossary"),
    (("coverage", "completeness", "覆盖"), "coverage"),
    (("change", "ledger", "变更"), "change_records"),
    (("limit", "scope", "caveat", "边界", "局限"), "limits"),
    (("evidence", "locator", "quote", "provenance", "证据", "定位"), "evidence"),
    (("audit", "verif", "check", "quality", "核验", "检查"), "audit"),
    (("translat", "bilingual", "pair", "align", "segment", "paragraph", "译文", "对照"), "pairs"),
    (("status", "state", "状态"), "status"),
    (("case",), "case_id"),
    (("language", "lang", "语种", "语言"), "lang"),
    (("element", "figure", "table", "caption", "要素", "图表"), "elements"),
    (("note", "method", "reason", "understanding", "decision", "方法", "说明"), "notes"),
    (("output", "artifact", "file", "产物", "文件"), "outputs"),
    (("source", "input", "material", "来源", "材料"), "sources"),
    (("summary", "abstract", "摘要"), "summary"),
    (("result", "结果", "产出"), "result"),
]


def _cut(text, n):
    """按词边界截断（保留逐字子串，不加省略号）：避免把 "NaCl" 截成 "Na" 这类半截词。"""
    t = (text or "").strip()
    if len(t) <= n:
        return t
    c = t[:n]
    sp = max(c.rfind(" "), c.rfind("\t"))
    if sp > n * 0.5:
        c = c[:sp]
    return c.rstrip(" ,;:，。；：")


def mkdirp(path):
    if path:
        os.makedirs(path, exist_ok=True)


def wtext(path, text):
    mkdirp(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def wjson(path, obj):
    wtext(path, json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n")


def clean(o):
    """把 None/NaN/inf 换成空串：产物里绝不留 null（会被占位符扫描误判）。"""
    if o is None:
        return ""
    if isinstance(o, bool):
        return o
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, (int, str)):
        return o
    if isinstance(o, list):
        return [clean(x) for x in o]
    if isinstance(o, dict):
        return dict((str(k), clean(v)) for k, v in o.items())
    return str(o)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return default


def contract_keys(case):
    """把 output_contract 归一为有序键列表；兼容 dict / list / list-of-dict / str。"""
    oc = case.get("output_contract") if isinstance(case, dict) else None
    keys = []
    if oc is None:
        return []
    if isinstance(oc, dict):
        if isinstance(oc.get("fields") or oc.get("required"), (list, dict)):
            return contract_keys({"output_contract": oc.get("fields") or oc.get("required")})
        keys = [str(k) for k in oc.keys()]
    elif isinstance(oc, list):
        for it in oc:
            if isinstance(it, str):
                keys.append(it)
            elif isinstance(it, dict):
                for cand in ("name", "field", "key", "id"):
                    if isinstance(it.get(cand), str):
                        keys.append(it[cand])
                        break
    elif isinstance(oc, str):
        keys = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", oc)[:24]
    seen, out = set(), []
    for k in keys:
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def contract_types(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    types = {}
    if isinstance(oc, dict):
        for k, v in oc.items():
            if isinstance(v, list):
                types[str(k)] = "array"
            elif isinstance(v, dict):
                t = str(v.get("type") or v.get("kind") or "").lower()
                if t:
                    types[str(k)] = t
            elif isinstance(v, str) and v.lower() in ("array", "list", "object", "string",
                                                      "number", "boolean"):
                types[str(k)] = "array" if v.lower() == "list" else v.lower()
    return types


def match_key(key):
    low = key.lower()
    for pats, gen in FIELD_MAP:
        for p in pats:
            if p in low:
                return gen
    return None


def build_claims(index, limit=8):
    """可核验断言：每条带段号 + locator + 原文句 + 保护性 span。"""
    out = []
    for s in index.get("segments", []):
        if len(out) >= limit:
            break
        if s["type"] not in ("body", "caption_figure", "caption_table", "table_row", "formula"):
            continue
        spans = [x["value"] for x in s.get("spans", [])]
        if s["type"] == "body" and not spans:
            continue
        out.append({"sid": s["sid"], "locator": s["locator"], "type": s["type"],
                    "claim": _cut(s["text"], 240), "evidence_spans": spans[:8],
                    "chars": s["chars"]})
    if not out:
        for s in index.get("segments", [])[:limit]:
            out.append({"sid": s["sid"], "locator": s["locator"], "type": s["type"],
                        "claim": _cut(s["text"], 240),
                        "evidence_spans": [x["value"] for x in s.get("spans", [])][:8],
                        "chars": s["chars"]})
    if not out:
        out.append({"sid": "", "locator": "input", "type": "no_material",
                    "claim": "输入目录下没有发现可切段的正文：未抽取任何断言",
                    "evidence_spans": [], "chars": 0})
    return out


def glossary_out(draft, index, res):
    """术语表：草稿给出的术语（quote 逐字命中才 locked）+ 索引里的候选术语。"""
    by_sid = dict((s["sid"], s) for s in index.get("segments", []))
    occ = {}
    for s in index.get("segments", []):
        low = s["text"].lower()
        for t in index.get("terms", []):
            if t["term"].lower() in low:
                occ.setdefault(t["term"], []).append(s["sid"])
    locked = set(res.get("glossary", {}).get("locked") or [])
    rows, seen = [], set()
    for g in (draft.get("glossary") or []):
        if not isinstance(g, dict):
            continue
        term = (g.get("term") or "").strip()
        tgt = (g.get("target") or g.get("locked_target") or "").strip()
        if not term or term in seen:
            continue
        seen.add(term)
        sid = str(g.get("sid") or g.get("evidence_sid") or "").strip()
        seg = by_sid.get(sid)
        ok = bool(g.get("quote_verified")) and term in locked
        rows.append({"term": term, "target": tgt,
                     "status": "locked" if ok else ("proposed" if tgt else "candidate"),
                     "quote": g.get("quote") or "", "sid": sid,
                     "locator": g.get("locator") or (seg["locator"] if seg else ""),
                     "quote_verified": bool(g.get("quote_verified")),
                     "quote_offset": g.get("quote_offset") if g.get("quote_offset") not in (None,) else -1,
                     "occurrences": occ.get(term, [])[:12],
                     "occurrence_count": len(occ.get(term, [])),
                     "basis": g.get("basis") or g.get("expansion") or ""})
    for t in index.get("terms", []):
        term = t["term"]
        if term in seen:
            continue
        seen.add(term)
        sid = (t.get("sids") or [""])[0]
        seg = by_sid.get(sid)
        quote, verified = "", False
        if seg:
            stxt = seg["text"]
            i = stxt.lower().find(term.lower())
            snip = _cut(stxt[i if i > 0 else 0:], 140)
            found, _off, matched = core.quote_find(stxt, snip)
            if found:
                quote, verified = matched, True
            else:
                quote = _cut(stxt, 140)
        rows.append({"term": term, "target": "", "status": "candidate", "quote": quote,
                     "sid": sid, "locator": seg["locator"] if seg else "",
                     "quote_verified": verified, "quote_offset": -1,
                     "occurrences": occ.get(term, [])[:12],
                     "occurrence_count": len(occ.get(term, [])), "basis": "索引候选术语"})
    return rows


def build_pairs(index, entries, res, glossary):
    gaps = {}
    for c in res.get("checks", []):
        if c["status"] == "fail" and c["check"] in (
                "protected_numbers", "citations", "figure_table_refs", "equation_tags"):
            gaps.setdefault(c["sid"], []).append(c["detail"])
    locked = dict((g["term"], g["target"]) for g in glossary if g["status"] == "locked" and g["target"])
    pairs = []
    for s in index.get("segments", []):
        e = entries.get(s["sid"]) or {}
        tgt = e.get("target") or e.get("translation") or ""
        pairs.append({
            "sid": s["sid"], "locator": s["locator"], "page": s["page"],
            "pages": s.get("pages", [s["page"]]), "type": s["type"],
            "section": s.get("section", "body"), "source": s["text"],
            "target": tgt if isinstance(tgt, str) else str(tgt),
            "target_status": "translated" if str(tgt).strip() else "untranslated",
            "protected_spans": [x["value"] for x in s.get("spans", [])][:24],
            "terms": sorted(t for t in locked if audit._contains_term(s["text"], t)),
            "uncertain": bool(e.get("uncertain")), "notes": e.get("notes") or "",
            "basis": e.get("basis") or "", "span_gaps": gaps.get(s["sid"], []),
            "bridged": bool(s.get("bridged")), "chars": s["chars"]})
    if not pairs:
        pairs.append({"sid": "", "locator": "input", "page": 0, "pages": [], "type": "no_material",
                      "section": "body", "source": "", "target": "",
                      "target_status": "blocked", "protected_spans": [], "terms": [],
                      "uncertain": True, "notes": "未发现可切段的正文，未生成段落对",
                      "basis": "", "span_gaps": [], "bridged": False, "chars": 0})
    return pairs


def build_evidence(index, pairs, glossary, res):
    ev = []
    for g in glossary:
        if g["quote_verified"]:
            ev.append({"kind": "glossary_quote", "term": g["term"], "sid": g["sid"],
                       "locator": g["locator"], "quote": g["quote"],
                       "char_offset": g["quote_offset"]})
    for p in pairs:
        if not p["source"]:
            continue
        ev.append({"kind": "paragraph", "sid": p["sid"], "locator": p["locator"],
                   "quote": audit._snip(p["source"], 160), "char_offset": 0,
                   "source_chars": p["chars"], "target_chars": len(p["target"]),
                   "target_status": p["target_status"]})
    for c in res.get("checks", []):
        if c["status"] == "fail":
            ev.append({"kind": "audit_failure", "check": c["check"], "sid": c["sid"],
                       "locator": (dict((s["sid"], s["locator"]) for s in
                                        index.get("segments", [])).get(c["sid"], "")),
                       "detail": c["detail"], "quote": c["source_excerpt"]})
    return ev[:400]


def build_uncertainties(res, entries, draft_state_name, index):
    out = []
    for sid in (res.get("coverage", {}).get("uncertain") or []):
        e = entries.get(sid) or {}
        out.append({"sid": sid, "kind": "translator_uncertain",
                    "detail": e.get("notes") or "译者标记为存疑，需人工复核"})
    for sid in (res.get("relations", {}).get("negation_fail_sids") or []):
        out.append({"sid": sid, "kind": "negation_at_risk",
                    "detail": "对应句的否定/限制成分在译文中未检出，可能是漏译或语气强化"})
    for sid in (res.get("glossary", {}).get("drift_sids") or []):
        out.append({"sid": sid, "kind": "term_drift",
                    "detail": "该段未使用锁定译名，可能是译名漂移"})
    if draft_state_name in ("absent", "empty", "unusable", "unusable_sample"):
        out.append({"sid": "", "kind": "no_draft",
                    "detail": "没有可用的工作稿（work/draft.json）：本次只做了索引、候选术语与核验骨架，"
                              "译文需由 Agent 补齐后重跑 build"})
    if not index.get("segments"):
        out.append({"sid": "", "kind": "no_material",
                    "detail": "输入目录未发现可解析的正文材料，无法切段与翻译"})
    if not out:
        out.append({"sid": "", "kind": "clean",
                    "detail": "本次未检出未决不确定性；仍建议人工通读一遍术语与语气"})
    return out


def build_changes(index, draft_state_name, res, outputs, timings):
    rows = [{"step": "index", "status": "ok", "segments": len(index.get("segments", [])),
             "chars": index.get("text_chars", 0), "warnings": len(index.get("warnings", [])),
             "seconds": timings.get("index", 0)}]
    if draft_state_name != "absent":
        rows.append({"step": "draft", "status": draft_state_name,
                     "seconds": timings.get("draft", 0)})
    rows.append({"step": "check", "status": "ok", "fail": res.get("summary", {}).get("fail", 0),
                 "warn": res.get("summary", {}).get("warn", 0),
                 "seconds": timings.get("check", 0)})
    rows.append({"step": "build", "status": "ok", "outputs": len(outputs),
                 "seconds": timings.get("build", 0)})
    for w in index.get("warnings", [])[:12]:
        rows.append({"step": "index", "status": "degraded", "detail": w})
    return rows


def build_result(case, index, draft, draft_state_name, res, status, ctx):
    keys = ctx["contract_keys"]
    types = ctx["contract_types"]
    pairs, glossary = ctx["pairs"], ctx["glossary"]
    claims = ctx["claims"]
    uncertainties = ctx["uncertainties"]
    gen = {
        "pairs": pairs, "glossary": glossary, "claims": claims,
        "uncertainties": uncertainties, "coverage": res.get("coverage", {}),
        "elements": res.get("elements", {}),
        "change_records": ctx["changes"], "limits": LIMITS,
        "sources": ctx["sources"], "summary": ctx["summary"],
        "evidence": ctx["evidence"], "status": status,
        "case_id": ctx["case_id"], "lang": ctx["target_lang"],
        "notes": (draft.get("task_understanding") or ctx["task_understanding"] or ""),
        "outputs": ctx["outputs"],
        "audit": {"summary": res.get("summary", {}), "rates": res.get("rates", {}),
                  "contract": res.get("contract", {}),
                  "fail_items": [c for c in res.get("checks", []) if c["status"] == "fail"][:80]},
        "result": {"status": status, "summary": ctx["summary"],
                   "coverage": res.get("coverage", {}),
                   "audit": {"fail": res.get("summary", {}).get("fail", 0),
                             "warn": res.get("summary", {}).get("warn", 0)}},
    }
    rf = draft.get("result_fields") or {}
    values, filled, fallback = {}, [], []
    list_gens = ("pairs", "glossary", "claims", "uncertainties", "sources", "change_records",
                 "limits", "evidence")
    for k in keys:
        v = rf.get(k)
        if v not in (None, "", [], {}):
            values[k] = v
            filled.append(k)
            continue
        g = match_key(k)
        v = gen.get(g) if g else None
        if v not in (None, "", [], {}):
            values[k] = v
            filled.append(k)
            continue
        values[k] = [] if (types.get(k) in ("array", "list") or g in list_gens) else DEFAULT_NOTE
        fallback.append(k)
    result = {
        "case_id": ctx["case_id"], "status": status,
        "skill": {"name": SKILL_NAME, "version": VERSION},
        "task_understanding": draft.get("task_understanding") or ctx["task_understanding"] or "",
        "sources": ctx["sources"], "summary": ctx["summary"],
        "claims": claims, "uncertainties": uncertainties,
        "change_records": ctx["changes"], "limits": LIMITS,
        "degradations": ctx["degradations"], "errors": list(dict.fromkeys(ctx["errors"])),
        "human_review": ctx["human_review"], "outputs": ctx["outputs"],
        "coverage": res.get("coverage", {}), "elements": res.get("elements", {}),
        "glossary_summary": {"locked": len([g for g in glossary if g["status"] == "locked"]),
                             "proposed": len([g for g in glossary if g["status"] == "proposed"]),
                             "candidate": len([g for g in glossary if g["status"] == "candidate"])},
        "audit_summary": {"summary": res.get("summary", {}), "rates": res.get("rates", {}),
                          "contract": {"filled": filled, "fallback": fallback}},
        "evidence": ctx["evidence"][:200], "runtime": ctx["runtime"],
        "output_contract": dict(values),
    }
    for k, v in values.items():
        if k not in ("case_id", "status", "uncertainties", "claims"):
            result.setdefault(k, v)
    return result


def esc(s):
    return str("" if s is None else s).replace("|", "\\|").replace("\n", " ")


def fmt(v):
    return "%.3f" % v if isinstance(v, (int, float)) else "—"


def render_markdown(case, index, pairs, glossary, res, status, ctx):
    L = ["# 双语对照与核验记录", "",
         "- 案例：`%s`" % ctx["case_id"],
         "- 状态：`%s`（草稿：%s）" % (status, ctx["draft_state"]),
         "- 段数：%d（已译 %d）" % (res.get("coverage", {}).get("total", 0),
                                   res.get("coverage", {}).get("translated", 0)),
         "- 章节：%s" % ctx["task_understanding"]]
    r = res.get("rates", {})
    L.append("- 指标：覆盖率 %s｜术语一致率 %s｜span 保留率 %s｜要素覆盖 %s｜否定保留率 %s"
             % (fmt(r.get("coverage_rate")), fmt(r.get("glossary_consistency")),
                fmt(r.get("span_retention")), fmt(r.get("element_coverage")),
                fmt(r.get("negation_rate"))))
    if ctx["degradations"]:
        L.append("- 降级：" + "；".join(ctx["degradations"][:6]))
    L += ["", "> 本文件是人读视图；机器可读的权威产物是 `paragraph_pairs.jsonl`、"
              "`audit_report.json`、`glossary.json` 与 `result.json`。", ""]
    if glossary:
        L += ["## 术语表", "",
              "| 术语 | 译名 | 状态 | 出现段 | 依据 | quote 逐字命中 |",
              "|---|---|---|---|---|---|"]
        for g in glossary[:40]:
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                esc(g["term"]), esc(g["target"]) or "—", g["status"],
                ",".join(g["occurrences"][:5]) or "—", _cut(esc(g["basis"]), 40) or "—",
                "是" if g["quote_verified"] else "否"))
        L.append("")
    L += ["## 段落对照", ""]
    for p in pairs:
        head = "### %s · p%s · %s%s" % (p["sid"] or "—", p["page"], p["type"],
                                        "（跨页续段）" if p["bridged"] else "")
        L += [head, "", "- 定位：`%s`" % p["locator"]]
        if p["terms"]:
            L.append("- 术语：%s" % "、".join(p["terms"]))
        if p["protected_spans"]:
            L.append("- 保护性 span：%s" % "、".join(p["protected_spans"]))
        if p["uncertain"]:
            L.append("- 存疑标记：%s" % (esc(p["notes"]) or "见 notes"))
        L += ["", "**原文**：%s" % (esc(p["source"]) or "（无）"), "",
              "**译文**：%s" % (esc(p["target"]) or "_（未翻译：本次无可用草稿）_"), ""]
        if p["notes"]:
            L += ["> 备注：%s" % esc(p["notes"]), ""]
        if p["span_gaps"]:
            L += ["> 核验缺口：%s" % "；".join(esc(x) for x in p["span_gaps"][:3]), ""]
    bad = [c for c in res.get("checks", []) if c["status"] in ("fail", "warn")]
    L += ["## 核验明细（fail / warn）", ""]
    if not bad:
        L.append("全部机械核验项通过。")
    else:
        L += ["| 检查项 | 状态 | 段号 | 说明 |", "|---|---|---|---|"]
        for c in bad[:80]:
            L.append("| %s | %s | %s | %s |" % (c["check"], c["status"], c["sid"] or "—",
                                                esc(c["detail"])))
    L.append("")
    return "\n".join(L)


def write_outputs(outdir, payload):
    mkdirp(outdir)
    written = []
    for name in OUT_FILES + [k for k in payload if k not in OUT_FILES]:
        if name not in payload:
            continue
        obj = payload[name]
        path = os.path.join(outdir, name)
        if isinstance(obj, str):
            wtext(path, obj)
        elif name.endswith(".jsonl"):
            wtext(path, "".join(json.dumps(clean(o), ensure_ascii=False) + "\n" for o in obj))
        else:
            wjson(path, obj)
        written.append(name)
    return written


def audit_report(case_id, index, res, status, ctx):
    fails = [c for c in res.get("checks", []) if c["status"] == "fail"]
    warns = [c for c in res.get("checks", []) if c["status"] == "warn"]
    return {
        "case_id": case_id, "status": status, "draft_state": ctx.get("draft_state"),
        "index_stats": index.get("stats", {}),
        "index_warnings": index.get("warnings", []),
        "summary": res.get("summary", {}), "rates": res.get("rates", {}),
        "coverage": res.get("coverage", {}), "elements": res.get("elements", {}),
        "glossary": res.get("glossary", {}), "spans": res.get("spans", {}),
        "relations": res.get("relations", {}), "contract": res.get("contract", {}),
        "fail_items": fails[:100], "warn_items": warns[:100],
        "checks": res.get("checks", []),
        "degradations": ctx.get("degradations", []), "errors": ctx.get("errors", []),
        "reading": "fail=确定性缺陷（必须修）；warn=需人工判断（可能可接受）；pass=已核验",
    }


def glossary_doc(ctx, index):
    return {"case_id": ctx["case_id"], "source_language": ctx.get("source_lang", "en"),
            "target_language": ctx.get("target_lang", "zh"),
            "policy": {"locked": "quote 在原文逐字命中且全篇回扫一致",
                       "proposed": "工作稿给出的译名，quote 未通过逐字校验",
                       "candidate": "仅出现在索引里的候选术语，未定名"},
            "entries": [g for g in ctx["glossary"] if g["status"] != "candidate"],
            "candidates": [g for g in ctx["glossary"] if g["status"] == "candidate"],
            "term_index": index.get("terms", [])[:40]}


def check_report(case_id, index, res, status, ctx):
    return {"case_id": case_id, "status": status, "draft_state": ctx.get("draft_state"),
            "derived_status": status, "summary": res.get("summary", {}),
            "rates": res.get("rates", {}), "coverage": res.get("coverage", {}),
            "contract": res.get("contract", {}), "fail_items": res.get("summary", {}).get("fail_by_check", {}),
            "warn_items": res.get("summary", {}).get("warn_by_check", {}),
            "fail_detail": [c for c in res.get("checks", []) if c["status"] == "fail"][:60],
            "warn_detail": [c for c in res.get("checks", []) if c["status"] == "warn"][:60],
            "index_stats": index.get("stats", {}),
            "recommendation": ("补齐译文后重跑 build" if res.get("summary", {}).get("fail")
                               else "核验通过；可交人读 QA")}
