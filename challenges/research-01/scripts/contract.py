#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract.py - research-01 output_contract mapping and result.json envelope."""
import json
import os
import re

import parse as P
from render import SL, cut
from parse import tok

# --------------------------------------------------------------------------- contract
def md_findings(data):
    out = ["### 发现卡 / Findings\n"]
    for f in data["findings"]:
        out.append("- **%s**（%s, %s）%s" % (f["finding_id"], f.get("status"), f.get("confidence"),
                                            f.get("statement") or ""))
        for it in f.get("support") or []:
            out.append("  - 证据 `%s` `%s`：%s" % (it.get("source_id"), it.get("locator"),
                                                  it.get("quote")))
        for it in f.get("counter") or []:
            out.append("  - 反证 `%s` `%s`：%s" % (it.get("source_id"), it.get("locator"),
                                                  it.get("quote")))
    return "\n".join(out) + "\n"


def md_synthesis(data):
    out = ["## 综合备忘录 / Synthesis\n"]
    for i, p in enumerate(data["synthesis"], 1):
        out.append("%d. %s（强度：%s；引用 %s）" % (
            i, p.get("paragraph"), SL.get(p.get("strength_note")), "、".join(p.get("finding_ids") or [])))
    out.append("\n## 未决与边界 / Open questions\n")
    for o in data["open_questions"]:
        out.append("- [%s] %s（依据：%s）" % (o.get("type"), o.get("description"), o.get("basis")))
    return "\n".join(out) + "\n"


def contract_values(data, status):
    sq = [{"sq_id": s.get("sq_id"), "text": s.get("text"), "object": s.get("object"),
           "mechanism": s.get("mechanism"), "method": s.get("method"),
           "time_scope": s.get("time_scope"), "comparison": s.get("comparison"),
           "evidence_requirement": s.get("evidence_requirement"),
           "depends_on": s.get("depends_on") or [], "layer": s.get("layer")}
          for s in data["sqs"]]
    return [
        ("__case_id__", data.get("case_id")),
        ("__question__", data["question"]),
        ("__sub_questions__", sq),
        ("__search__", data["search_steps"]),
        ("__evidence__", data["evidence"]),
        ("__findings__", data["findings"]),
        ("__conflicts__", data["conflicts"]),
        ("__open__", data["open_questions"]),
        ("__uncertainty__", data["uncertainties"]),
        ("__sources__", data["sources"]),
        ("__synthesis_md__", md_synthesis(data)),
        ("__findings_md__", md_findings(data)),
        ("__coverage__", data["coverage"]),
        ("__status__", status),
        ("__brief_md__", "# 研究简报\n\n问题：%s\n\n子问题：%s\n" % (
            data["question"], "；".join("%s %s" % (s.get("sq_id"), s.get("text")) for s in data["sqs"]))),
        ("__artifacts__", ["notebook/00-README.md", "notebook/01-brief.md", "notebook/02-search-log.jsonl",
                           "notebook/03-findings/finding-cards.jsonl", "notebook/04-synthesis.md",
                           "notebook/05-open-questions.md", "appendix/evidence-register.jsonl"]),
        ("__method__", "见 SKILL.md 第 7 节；复跑：init → show → draft.json → check → build → selfcheck"),
    ]


def map_key(key, vals):
    k = str(key).lower()
    v = dict(vals)
    def has(*ws):
        return any(w in k for w in ws)
    if has("case") and has("id"):
        return "__case_id__", "case_id"
    if has("research_question", "question", "topic", "title", "objective"):
        return "__question__", "research_question"
    if has("sub_question", "subquestion", "decompos", "question_tree", "breakdown", "sublist"):
        return "__sub_questions__", "sub_questions"
    if has("search", "retriev", "quer", "protocol", "plan"):
        return "__search__", "search_log"
    if has("conflict", "contradict", "disagree"):
        return "__conflicts__", "conflicts"
    if has("evidence", "matrix", "extract", "record"):
        return "__evidence__", "evidence_register"
    if has("finding", "key_result", "cards"):
        return "__findings__", "findings"
    if has("synth", "conclusion", "review", "memo", "narrative", "report", "answer", "summary"):
        return "__synthesis_md__", "synthesis_markdown"
    if has("gap", "open", "limitation", "uncertain", "caveat"):
        return "__open__", "open_questions"
    if has("source", "citation", "reference", "bibliograph"):
        return "__sources__", "sources"
    if has("coverage", "metric", "stat", "count"):
        return "__coverage__", "coverage"
    if has("artifact", "deliverable", "file", "output"):
        return "__artifacts__", "artifacts"
    if has("method", "reproduc", "runbook", "note"):
        return "__method__", "method_notes"
    if has("status",):
        return "__status__", "status"
    return None, None


def fit(value, spec, slot):
    s = str(spec or "").lower()
    wants_str = any(w in s for w in ("string", "text", "markdown", "prose", "字符串", "文本", "叙述"))
    wants_list = any(w in s for w in ("array", "list", "列表", "数组"))
    if value is None:
        return ([] if wants_list else None)
    if wants_str and isinstance(value, (list, dict)):
        if slot in ("__findings__",):
            return "见 notebook/03-findings/finding-cards.jsonl"
        if slot == "__sub_questions__":
            return "\n".join("- %s %s" % (x.get("sq_id"), x.get("text")) for x in value)
        if slot == "__search__":
            return "\n".join("- %s %s → %s" % (x.get("step_id"), x.get("action"),
                                               x.get("result_summary")) for x in value)
        if slot == "__evidence__":
            return "\n".join("- %s `%s` `%s`：%s" % (x.get("evidence_id"), x.get("source_id"),
                                                    x.get("locator"), x.get("quote")) for x in value)
        if slot == "__sources__":
            return "\n".join("- %s `%s`（%s）" % (x.get("source_id"), x.get("path"),
                                                 x.get("read_method")) for x in value)
        if slot == "__open__":
            return "\n".join("- [%s] %s" % (x.get("type"), x.get("description")) for x in value)
        return json.dumps(value, ensure_ascii=False)
    if wants_list and not isinstance(value, list):
        return [value]
    return value


# 包内声明的默认契约键（case.json 未给 output_contract 时用它回填，见 SKILL.md §0）
_DECLARED_CONTRACT = ["case_id", "research_question", "sub_questions", "search_plan",
                      "evidence_matrix", "findings", "synthesis", "conflicts",
                      "open_questions", "sources", "status"]


def scrub(value):
    """把 JSON null 换成空串（不留空壳占位），保持结构不变。"""
    if value is None:
        return ""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(x) for x in value]
    return value


_PATHY_RE = re.compile(r"\.(md|markdown|json|jsonl|csv|tsv|txt|tex|bib|html?)$", re.IGNORECASE)

# 长文/多行类槽位在 output_contract 里改成指向已写产物的相对路径（可被下游按文件回查），
# 避免把整段 markdown 塞进契约回填而看起来像坏路径。
_ECHO_POINTER = {
    "synthesis": "notebook/04-synthesis.md",
    "synthesis_markdown": "notebook/04-synthesis.md",
    "synthesis_md": "notebook/04-synthesis.md",
    "findings_md": "notebook/03-findings/findings-index.md",
    "evidence": "appendix/evidence-register.jsonl",
    "evidence_register": "appendix/evidence-register.jsonl",
    "search": "notebook/02-search-log.jsonl",
    "search_plan": "notebook/02-search-log.jsonl",
    "brief": "notebook/01-brief.md",
}


def _echo_value(key, value, out):
    """契约回填用的值：多行/像路径的字符串改成产物指针，写不出实体的留空（绝不编造）。"""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return ""
    if "\n" in s or _PATHY_RE.search(s) or "/" in s:
        ptr = _ECHO_POINTER.get(str(key).lower())
        if ptr and out is not None and os.path.isfile(os.path.join(str(out), ptr)):
            return ptr
        return ""
    return value


def attach_output_contract(res, keys, out=None):
    """逐键显式回填 output_contract：契约声明的键 + 包内声明兜底键，全部保留、绝不删键。"""
    ks = [str(k) for k in keys]
    for d in _DECLARED_CONTRACT:
        if d not in ks:
            ks.append(d)
    oc = {}
    for k in ks:
        if k not in res:
            res[k] = ""
        oc[k] = _echo_value(k, res.get(k), out)
    res["output_contract"] = scrub(oc)
    res["case_id"] = res.get("case_id") or "unknown"
    return scrub(res)


def build_result(case_id, status, data, chk, idx, degradations, errors, changes, extra, out=None):
    vals = contract_values(data, status)
    vm = dict(vals)
    res, audit = {}, []
    for f in idx["contract"]:
        key = f["key"]
        slot, semantic = map_key(key, vals)
        if slot is None:
            value = None
            audit.append({"key": key, "slot": None, "filled": False,
                          "detail": "无对应语义槽，按契约要求留空"})
        else:
            value = fit(vm.get(slot), f.get("spec"), slot)
            filled = value not in (None, [], "", {})
            audit.append({"key": key, "slot": semantic, "filled": filled,
                          "detail": "由 %s 回填" % semantic})
        res[key] = value
    res.update({
        "case_id": case_id, "status": status, "task_type": "deep_research_evidence_synthesis",
        "research_question": data["question"],
        "sub_questions": data["sqs"], "search_steps": data["search_steps"],
        "findings": data["findings"], "conflicts": data["conflicts"],
        "conflict_hints": data["conflict_hints"],
        "synthesis_claims": [{"paragraph_id": "P%d" % (i + 1), "text": p.get("paragraph"),
                              "finding_ids": p.get("finding_ids") or [],
                              "strength_note": p.get("strength_note")}
                             for i, p in enumerate(data["synthesis"])],
        "synthesis_markdown": md_synthesis(data),
        "evidence_summary": {"total": len(data["evidence"]),
                             "verified": sum(1 for e in data["evidence"] if e["verified"]),
                             "unverified": sum(1 for e in data["evidence"] if not e["verified"]),
                             "register": "appendix/evidence-register.jsonl"},
        "evidence_register": data["evidence"],
        "open_questions": data["open_questions"],
        "coverage": data["coverage"], "sources": data["sources"],
        "uncertainties": data["uncertainties"],
        "degradations": degradations, "errors": errors, "changes": changes,
        "quality": {"fix": chk["stats"]["fix"], "warn": chk["stats"]["warn"],
                    "quotes_verified": chk["stats"]["quotes_verified"],
                    "quotes_failed": chk["stats"]["quotes_failed"],
                    "locators_repaired": chk["stats"]["locators_repaired"],
                    "issues": chk["issues"][:80],
                    "uncovered_sub_questions": chk["stats"]["uncovered_sub_questions"]},
        "contract_audit": audit,
        "artifacts": vm["__artifacts__"],
        "runtime": extra,
    })
    return attach_output_contract(res, [f["key"] for f in idx["contract"]], out=out)


def derive_draft(idx):
    """Deterministic fallback draft: instruction clauses -> sub-questions, material
    sentences -> provisional finding cards.  Clearly marked as unreviewed."""
    q = P.question_of(idx)
    case = idx["case"] or {}
    base = " ".join(str(case.get(k) or "") for k in
                    ("task_instruction", "research_question", "question", "instruction", "brief"))
    base = base.strip() or (idx.get("task_md") or "")[:2500] or q
    clauses = [c.strip(" -•\t") for c in re.split(r"[。；;\n]|(?<=\.)\s+", base)]
    clauses = [c for c in clauses if len(c) >= 10]
    seen, sqs = set(), []
    for c in clauses:
        key = c[:24]
        if key in seen:
            continue
        seen.add(key)
        n = len(sqs)
        sqs.append({
            "sq_id": "SQ%d" % (n + 1), "text": cut(c, 120),
            "object": cut(c, 60), "mechanism": "未从材料解析（兜底拆解，待复核）",
            "method": "未从材料解析（兜底拆解，待复核）", "time_scope": "材料覆盖时间范围",
            "comparison": "无" if not re.search(r"(vs|相比|对比|versus)", c, re.I) else "见子问题原文",
            "evidence_requirement": "材料中直接陈述该子问题的句子",
            "depends_on": [] if n == 0 else [],
            "layer": P.LAYERS[n % 4],
        })
        if len(sqs) >= 6:
            break
    if not sqs:
        sqs = [{"sq_id": "SQ1", "text": cut(q, 120), "object": cut(q, 60),
                "mechanism": "未从材料解析", "method": "未从材料解析", "time_scope": "未限定",
                "comparison": "无", "evidence_requirement": "材料中直接陈述该问题的句子",
                "depends_on": [], "layer": "what"}]

    log, findings = [], []
    byid = {}
    for m in idx["materials"]:
        byid[m["id"]] = m
        ok = bool(m["text"].strip())
        log.append({"step_id": "S%d" % (len(log) + 1), "action": "read", "target": m["id"],
                    "params": "path=%s read_method=%s" % (m["rel"], m["read_method"]),
                    "result_summary": "%d chars / %d blocks" % (m["chars"], len(m.get("blocks") or [])),
                    "hits": [m["id"]] if ok else [], "status": "ok" if ok else "failed",
                    "retry_count": 0})
    used = set()
    for sq in sqs:
        toks = tok(sq["text"] + " " + sq.get("object", ""))
        cand = []
        for m in idx["materials"]:
            for b in m.get("blocks") or []:
                for s in b["sents"]:
                    if len(s["text"]) < 12:
                        continue
                    sc = len(toks & tok(s["text"]))
                    if sc >= 2:
                        cand.append((sc, m, b, s))
        cand.sort(key=lambda x: -x[0])
        picked = 0
        for sc, m, b, s in cand:
            if picked >= 2 or len(findings) >= 12:
                break
            key = (m["id"], s["start"])
            if key in used:
                continue
            used.add(key)
            picked += 1
            findings.append({
                "finding_id": "F%03d" % (len(findings) + 1),
                "statement": "材料陈述：" + cut(s["text"], 160),
                "type": "material_fact", "confidence": "low",
                "support": [{"source_id": m["id"],
                             "locator": P.locator_for(m, s["start"], s["end"]),
                             "quote": s["text"]}],
                "counter": [], "scope": "限于 %s（%s）" % (m["rel"], m["kind"]),
                "sub_question_id": sq["sq_id"], "status": "provisional",
                "auto_extracted": True})
    if not findings:
        seenm = set()
        for m in idx["materials"]:
            if m["id"] in seenm or not m["text"].strip():
                continue
            for b in m.get("blocks") or []:
                got = False
                for sen in b["sents"]:
                    if len(sen["text"]) < 24:
                        continue
                    findings.append({
                        "finding_id": "F%03d" % (len(findings) + 1),
                        "statement": "材料陈述：" + cut(sen["text"], 160),
                        "type": "material_fact", "confidence": "low",
                        "support": [{"source_id": m["id"],
                                     "locator": P.locator_for(m, sen["start"], sen["end"]),
                                     "quote": sen["text"]}],
                        "counter": [], "scope": "限于 %s（兜底抽取）" % m["rel"],
                        "sub_question_id": sqs[0]["sq_id"], "status": "provisional",
                        "auto_extracted": True})
                    got = True
                    break
                if got:
                    seenm.add(m["id"])
                    break
            if len(findings) >= 3:
                break
    syn = []
    for sq in sqs:
        ids = [f["finding_id"] for f in findings if f.get("sub_question_id") == sq["sq_id"]]
        if ids:
            syn.append({"paragraph": "就「%s」，材料内可定位的陈述见 %s；这些语句直接来自材料，"
                                     "未经过阈值以上的综合判断，只作为线索。" %
                                     (cut(sq["text"], 60), "、".join("[%s]" % i for i in ids)),
                        "finding_ids": ids, "strength_note": "provisional"})
    covered = {f.get("sub_question_id") for f in findings}
    oqs = []
    for sq in sqs:
        if sq["sq_id"] not in covered:
            oqs.append({"oq_id": "OQ%d" % (len(oqs) + 1),
                        "description": "子问题「%s」在现有材料中无命中句" % cut(sq["text"], 60),
                        "type": "retrieval_gap",
                        "basis": "脚本按关键词对 %d 份材料逐句匹配，0 句达标" % len(idx["materials"])})
    oqs.append({"oq_id": "OQ%d" % (len(oqs) + 1),
                "description": "未检索外部数据库，材料覆盖面可能不足",
                "type": "scope_limit",
                "basis": "本 Skill 离线运行，只用 /input 下 %d 份材料" % len(idx["materials"])})
    if any(m["read_method"] in ("none", "unsupported") for m in idx["materials"]):
        oqs.append({"oq_id": "OQ%d" % (len(oqs) + 1),
                    "description": "部分材料无文本层或格式不支持，未纳入证据",
                    "type": "method_limitation",
                    "basis": "read_method ∈ {none, unsupported} 的材料清单见 degradations"})
    return {"case_id": (idx["case"] or {}).get("case_id"), "_derived": True,
            "brief": {"question": q, "scope": "仅 /input 提供的材料",
                      "inclusion": ["材料内直接陈述的句子"],
                      "exclusion": ["无文本层材料", "材料未涉及的对象"],
                      "stop_rules": ["各子问题至少一条命中句", "材料遍历完毕"]},
            "sub_questions": sqs, "search_log": log, "findings": findings,
            "synthesis": syn, "open_questions": oqs}


# --------------------------------------------------------------------------- assemble
