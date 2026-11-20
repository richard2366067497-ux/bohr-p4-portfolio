#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py — 把索引 + 工作稿 + 核验结果渲染成最终产物。

产物（/app/output 下）：
  result.json            主产物，原样回填 output_contract 全部字段 + 信封字段
  paragraph_pairs.jsonl  每行一段：段号/定位/原文/译文/术语命中/span 缺口/备注/存疑
  audit_report.json      每条核验项的 pass|fail|warn|skip + 定位 + 指标率
  glossary.json          术语表（含 quote_verified 与全篇出现位置）
  bilingual_review.md    人读视图（派生，便于评审逐段核对）

契约回填策略（不猜业务字段名就回 null，绝不改名、不漏键）：
  1) 工作稿 result_fields 里有该键且非空 → 直接采用（Agent 的决定优先）；
  2) 否则按字段名语义映射到本 Skill 的产物（translation→段落对、glossary→术语表、
     coverage/summary→覆盖账本、audit/verification→核验摘要、evidence/locator→证据表…）；
  3) 都不匹配 → null；若契约显式声明为 array 则给 []。
"""
import json
import os
import re

VERSION = "1.0.0"
SKILL_NAME = "sci-lit-bilingual-audit"

# 语义 → 生成器名
FIELD_MAP = [
    (("glossary", "terminolog", "术语"), "glossary"),
    (("coverage", "completeness", "coverage_report", "覆盖"), "coverage"),
    (("audit", "verif", "check", "quality", "核验", "检查"), "audit"),
    (("evidence", "citation_locator", "locator", "quote", "provenance", "证据", "定位"), "evidence"),
    (("uncertain", "unresolved", "pending", "manual", "risk", "不确定", "待确认"), "uncertainties"),
    (("translat", "bilingual", "target_text", "pair", "align", "segment", "paragraph",
      "译文", "翻译", "对照"), "pairs"),
    (("status", "state", "状态"), "status"),
    (("case",), "case_id"),
    (("language", "lang", "语种", "语言"), "lang"),
    (("note", "method", "reason", "understanding", "approach", "decision", "方法", "说明"), "notes"),
    (("output", "artifact", "file", "path", "产物", "文件"), "outputs"),
    (("source", "input", "material", "来源", "材料"), "sources"),
    (("summary", "abstract", "abstract_zh", "摘要"), "summary"),
]


def contract_keys(case):
    """把 output_contract 归一为有序键列表；兼容 dict / list / list-of-dict / str。"""
    oc = case.get("output_contract") if isinstance(case, dict) else None
    keys = []
    if oc is None:
        return keys
    if isinstance(oc, dict):
        if set(oc.keys()) <= {"fields", "required", "schema"} and isinstance(
                oc.get("fields") or oc.get("required"), (list, dict)):
            inner = oc.get("fields") or oc.get("required")
            return contract_keys({"output_contract": inner})
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
        keys = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", oc)
        if not keys:
            keys = re.findall(r"\b([a-z_][a-z0-9_]{2,})\b", oc)[:24]
    seen, out = set(), []
    for k in keys:
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def contract_field_types(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    types = {}
    if isinstance(oc, dict):
        for k, v in oc.items():
            t = None
            if isinstance(v, dict):
                t = str(v.get("type") or v.get("kind") or "").lower()
            elif isinstance(v, list):
                t = "array"
            elif isinstance(v, str) and v.lower() in ("array", "list", "object", "string", "number", "boolean"):
                t = v.lower()
            if t:
                types[str(k)] = t
    return types


def _match(key):
    low = key.lower()
    for pats, gen in FIELD_MAP:
        for p in pats:
            if p in low:
                return gen
    return None


def build_pairs(index, draft_entries, audit_res):
    """段落对：source 一律取索引原文（保证 quote 可核验），译文取工作稿。"""
    span_gap = {}
    for item in audit_res.get("checks", []):
        if item["check"] in ("protected_numbers", "citations", "figure_table_refs", "equation_tags") \
                and item["status"] == "fail":
            span_gap.setdefault(item["sid"], []).append(item["detail"])
    locked = {g.get("term"): g.get("target") for g in audit_res.get("_glossary_out", [])
              if g.get("status") == "locked"}
    pairs = []
    for s in index.get("segments", []):
        e = draft_entries.get(s["sid"]) or {}
        tgt = (e.get("target") or e.get("translation") or "")
        terms = [t for t in locked if t and _term_in(s["text"], t)]
        pairs.append({
            "sid": s["sid"],
            "locator": s["locator"],
            "page": s["page"],
            "type": s["type"],
            "section": s.get("section", "body"),
            "source": s["text"],
            "target": tgt,
            "terms": sorted(terms),
            "uncertain": bool(e.get("uncertain")),
            "notes": e.get("notes") or "",
            "translation_basis": e.get("basis") or e.get("translation_basis") or "",
            "span_gaps": span_gap.get(s["sid"], []),
            "bridged": bool(s.get("bridged")),
        })
    return pairs


def _term_in(hay, term):
    if re.search(r"[\u4e00-\u9fff]", term or ""):
        return term in hay
    try:
        return re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", hay, re.I) is not None
    except re.error:
        return False


def build_glossary(audit_res, index):
    by_term = {}
    for s in index.get("segments", []):
        for t in (g.get("term") for g in audit_res.get("_glossary_out", [])):
            if t and _term_in(s["text"], t):
                by_term.setdefault(t, []).append(s["sid"])
    out = []
    for g in sorted(audit_res.get("_glossary_out", []), key=lambda x: (x.get("term") or "")):
        term = g.get("term") or ""
        g = dict(g)
        g["occurrences"] = by_term.get(term, [])
        g["occurrence_count"] = len(g["occurrences"])
        out.append(g)
    return out


def build_evidence(audit_res, pairs):
    """证据表：每条 = 一个可复核的定位（术语引文 / 段落 quote / 核验 fail）。"""
    ev = []
    for g in audit_res.get("_glossary_out", []):
        if g.get("quote_verified"):
            ev.append({"kind": "glossary_quote", "term": g.get("term"),
                       "locator": g.get("locator") or g.get("sid"),
                       "sid": g.get("sid"), "quote": g.get("quote"),
                       "char_offset": g.get("quote_offset")})
    for p in pairs:
        if p["target"]:
            ev.append({"kind": "paragraph", "locator": p["locator"], "sid": p["sid"],
                       "quote": p["source"][:160], "char_offset": 0,
                       "source_chars": len(p["source"]), "target_chars": len(p["target"])})
    for c in audit_res.get("checks", []):
        if c["status"] == "fail":
            ev.append({"kind": "audit_failure", "check": c["check"], "sid": c["sid"],
                       "detail": c["detail"], "quote": c["source_excerpt"]})
    return ev


def build_result(case, index, draft, audit_res, pairs, glossary, status, extra):
    """组装 result.json：信封 + 契约字段回填。"""
    keys = contract_keys(case)
    types = contract_field_types(case)
    rf = (draft or {}).get("result_fields") or {}
    have = set(rf.keys())
    generated = {
        "pairs": pairs,
        "glossary": glossary,
        "coverage": audit_res.get("coverage", {}),
        "audit": {"summary": audit_res.get("summary", {}), "rates": audit_res.get("rates", {}),
                  "fail_items": [c for c in audit_res.get("checks", []) if c["status"] == "fail"][:60]},
        "evidence": build_evidence(audit_res, pairs),
        "uncertainties": (draft or {}).get("uncertainties") or [],
        "status": status,
        "case_id": extra.get("case_id"),
        "lang": extra.get("target_lang"),
        "notes": (draft or {}).get("task_understanding") or extra.get("task_understanding") or "",
        "outputs": extra.get("outputs", {}),
        "sources": extra.get("sources", []),
        "summary": {
            "paragraphs": audit_res.get("coverage", {}).get("total", 0),
            "translated": audit_res.get("coverage", {}).get("translated", 0),
            "glossary_locked": sum(1 for g in glossary if g.get("status") == "locked"),
            "audit_pass": audit_res.get("summary", {}).get("pass", 0),
            "audit_fail": audit_res.get("summary", {}).get("fail", 0),
        },
    }
    filled, nulled = [], []
    contract_values = {}
    list_gens = {"pairs", "glossary", "evidence", "uncertainties", "sources"}
    for k in keys:
        if k in have and rf.get(k) not in (None, "", [], {}):
            contract_values[k] = rf[k]
            filled.append(k)
            continue
        gen = _match(k)
        val = generated.get(gen) if gen else None
        if gen in list_gens and val == []:
            contract_values[k] = []      # 空列表也是合法值，不算缺值
            filled.append(k)
            continue
        if gen and val not in (None, "", [], {}):
            contract_values[k] = val
            filled.append(k)
            continue
        contract_values[k] = [] if (types.get(k) in ("array", "list") or gen in list_gens) else None
        nulled.append(k)

    result = {
        "case_id": extra.get("case_id") or "",
        "status": status,
        "skill": {"name": SKILL_NAME, "version": VERSION},
        "task_understanding": (draft or {}).get("task_understanding") or "",
        "sources": extra.get("sources", []),
        "summary": generated["summary"],
        "glossary": glossary,
        "audit_summary": {
            "summary": audit_res.get("summary", {}),
            "rates": audit_res.get("rates", {}),
            "contract": {"filled": filled, "nulled": nulled},
        },
        "coverage": audit_res.get("coverage", {}),
        "evidence": generated["evidence"][:400],
        "uncertainties": generated["uncertainties"],
        "pending_human": extra.get("pending_human", []),
        "degradations": extra.get("degradations", []),
        "errors": extra.get("errors", []),
        "change_log": extra.get("change_log", []),
        "outputs": extra.get("outputs", {}),
        "runtime": extra.get("runtime", {}),
        "example": "",
    }
    # 契约字段放在顶层（不改名、不漏键）；与信封同名键以契约值为准但状态保持推导值
    for k, v in contract_values.items():
        if k in ("status",) and status:
            result[k] = status
            continue
        result[k] = v
    result.pop("example", None)
    return result, {"filled": filled, "nulled": nulled}


def render_markdown(case, index, pairs, glossary, audit_res, status, extra):
    lines = []
    lines.append("# 双语对照与核验记录")
    lines.append("")
    lines.append("- 案例：`%s`" % (extra.get("case_id") or ""))
    lines.append("- 状态：`%s`" % status)
    lines.append("- 段数：%d（已译 %d）" % (audit_res.get("coverage", {}).get("total", 0),
                                          audit_res.get("coverage", {}).get("translated", 0)))
    rates = audit_res.get("rates", {})
    lines.append("- 指标：覆盖率 %s｜术语一致率 %s｜span 保留率 %s｜否定保留率 %s"
                 % (_fmt(rates.get("coverage_rate")), _fmt(rates.get("glossary_consistency")),
                    _fmt(rates.get("span_retention")), _fmt(rates.get("negation_rate"))))
    if extra.get("degradations"):
        lines.append("- 降级：" + "；".join(extra["degradations"][:6]))
    lines.append("")
    lines.append("> 本文件为派生的人读视图；机器可读的权威产物是 `paragraph_pairs.jsonl`、"
                 "`audit_report.json`、`glossary.json` 与 `result.json`。")
    lines.append("")
    if glossary:
        lines.append("## 术语表（locked = quote 逐字命中且全篇回扫一致）")
        lines.append("")
        lines.append("| 术语 | 译名 | 状态 | 出现段 | 依据 |")
        lines.append("|---|---|---|---|---|")
        for g in glossary:
            lines.append("| %s | %s | %s | %s | %s |" % (
                _esc(g.get("term")), _esc(g.get("target")), g.get("status"),
                ",".join(g.get("occurrences", [])[:6]) or "-", _esc(g.get("basis"))))
        lines.append("")
    lines.append("## 段落对照")
    lines.append("")
    for p in pairs:
        lines.append("### %s · p%s · %s%s" % (p["sid"], p["page"], p["type"],
                                              "（跨页续段）" if p["bridged"] else ""))
        lines.append("")
        lines.append("- 定位：`%s`" % p["locator"])
        if p["terms"]:
            lines.append("- 术语：%s" % "、".join(p["terms"]))
        if p["uncertain"]:
            lines.append("- ⚠ 存疑：%s" % (_esc(p["notes"]) or "见 notes"))
        lines.append("")
        lines.append("**原文**：%s" % _esc(p["source"]))
        lines.append("")
        lines.append("**译文**：%s" % (_esc(p["target"]) if p["target"] else "_（未翻译）_"))
        lines.append("")
        if p["notes"]:
            lines.append("> 备注：%s" % _esc(p["notes"]))
            lines.append("")
        if p["span_gaps"]:
            lines.append("> ⚠ 核验缺口：%s" % "；".join(_esc(x) for x in p["span_gaps"][:3]))
            lines.append("")
    lines.append("## 核验明细（fail / warn）")
    lines.append("")
    bad = [c for c in audit_res.get("checks", []) if c["status"] in ("fail", "warn")]
    if not bad:
        lines.append("全部核验项通过。")
    else:
        lines.append("| 检查项 | 状态 | 段号 | 说明 |")
        lines.append("|---|---|---|---|")
        for c in bad[:80]:
            lines.append("| %s | %s | %s | %s |" % (c["check"], c["status"], c["sid"] or "-",
                                                    _esc(c["detail"])))
    lines.append("")
    return "\n".join(lines)


def _fmt(v):
    return "%.3f" % v if isinstance(v, (int, float)) else "n/a"


def _esc(s):
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def write_outputs(outdir, payload):
    """payload: {filename: obj_or_str}；返回写入的文件名列表。"""
    os.makedirs(outdir, exist_ok=True)
    written = []
    for name, obj in payload.items():
        path = os.path.join(outdir, name)
        if isinstance(obj, str):
            text = obj
        elif name.endswith(".jsonl"):
            text = "".join(json.dumps(o, ensure_ascii=False, sort_keys=False) + "\n" for o in obj)
        else:
            text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        written.append(name)
    return written
