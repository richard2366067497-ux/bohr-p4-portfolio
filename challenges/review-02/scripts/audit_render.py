"""audit_render.py - fallback content, contract fill, envelope, human-readable render.

Owns everything that turns an index plus a (possibly missing) judgement draft into
textual deliverables. No semantic decision is taken here.
"""

from __future__ import annotations

import json, sys, time

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import audit_core as A
import audit_build as B


def quotable(*vals):
    """A mechanical row may not quote schema/placeholder keywords verbatim into a delivered artifact."""
    return not any(B.SHELL_TOKENS.search(str(v or "")) for v in vals)


def fallback(idx, corpus):
    cks, fnds = [], []
    for c in (idx.get("claim_candidates") or [])[:60]:
        if not quotable(c["text"]):
            continue
        cks.append({"check_id": c["cand_id"], "claim_id": c["cand_id"], "claim_text": c["text"],
                    "claim_quote": c["text"], "claim_strength": c["claim_strength"],
                    "cited_source": {"label": ", ".join(c["markers"]) or None,
                                     "source_locator_if_available": None},
                    "source_claim_if_available": None, "verdict": "undetermined",
                    "semantics": {B.SEM[0]: None, B.SEM[1]: None, B.SEM[2]: None,
                                  "comparator": c["comparator"], "negation": c["negation"],
                                  "significance": c["significance"]},
                    "locators": {"claim_loc": c["locator"], "source_loc": None},
                    "rationale": "脚本机械抽取的候选论断，未做语义判定（无工作稿）",
                    "checked_evidence": [c["text"]],
                    "quote_verified": bool(corpus.find(c["text"])["ok"]),
                    "unresolved_reason": "agent draft.json 缺失：仅有定位与原文，没有支持度判定",
                    "human_check_needed": "阅读该段与所引文献，判定方向/数值/范围是否一致",
                    "status": "pending_review"})
    refs_n = len(idx.get("references") or [])
    for c in idx.get("citations") or []:
        if c["pairing"] == "paired" or not quotable(c["sentence"]):
            continue
        fnds.append({"finding_id": "F-%02d" % (len(fnds) + 1), "facet": "citation",
                     "location": {"section": c["section"], "locator": c["locator"],
                                  "page": c["page"], "table_or_figure": None},
                     "quote": A.squash(c["sentence"], 420), "quote_verified": True,
                     "issue_type": "compliance",
                     "severity": "major" if c["pairing"] in ("numbering_gap", "ambiguous") else "minor",
                     "severity_reason": "引文标记无法与文献表条目对应，读者无法回查来源",
                     "verdict_type": "compliance_issue",
                     "evidence": "正文标记 %s 配对状态=%s；文献表解析到 %d 条"
                                 % (c["marker"], c["pairing"], refs_n),
                     "rationale": "机械核对：编号/作者-年份匹配失败，属规范问题而非结论正确性问题",
                     "revision": "补齐文献表条目，或将正文标记改为文献表中实际存在的编号/作者-年份",
                     "claim_ref": None, "status": "pending_review"})
    for n in idx.get("numeric_candidates") or []:
        if not quotable(n["left"]["sentence"], n["right"]["sentence"]):
            continue
        fnds.append({"finding_id": "F-%02d" % (len(fnds) + 1), "facet": "statistics",
                     "location": {"section": n["left"]["sec"], "locator": n["left"]["locator"],
                                  "page": None, "table_or_figure": None},
                     "quote": A.squash(n["left"]["sentence"], 420), "quote_verified": True,
                     "issue_type": "numeric_inconsistency", "severity": "major",
                     "severity_reason": "同一数值桶在摘要与正文出现不同值，影响可复现性",
                     "verdict_type": "fact_error",
                     "evidence": "另一侧 %s 记 %s：%s" % (n["right"]["locator"], n["right"]["value"],
                                                        A.squash(n["right"]["sentence"], 240)),
                     "rationale": "机械比对（bucket=%s，共享上下文 %s）；是否为分组差异需人工确认"
                                 % (n["bucket"], ",".join(n["shared_terms"][:4])),
                     "revision": "统一摘要与正文的该数值，或在摘要写明分组/条件差异",
                     "claim_ref": None, "status": "pending_review"})
    cov = {f: {"checked": False, "items": 0, "findings": 0, "note": "未审查：无工作稿"}
           for f in B.FACETS + B.SUBS}
    return cks, fnds, cov


def default_for(spec):
    if isinstance(spec, dict):
        t = str(spec.get("type") or spec.get("kind") or "").lower()
        if "list" in t or "array" in t or t.endswith("[]"):
            return []
        if "obj" in t or "dict" in t or "map" in t:
            return {}
        return spec.get("default")
    if isinstance(spec, list):
        return []
    if isinstance(spec, str):
        low = spec.lower()
        return [] if ("list" in low or "array" in low or "[]" in spec) else {} if "object" in low else None
    return None


def contract_value(k, core):
    """One value per declared contract key: produced file names, canonical core field, else None."""
    nk = B.norm_key(k)
    if k in A.PRODUCED_FILES:
        return k
    v = core.get(k)
    if v is None:
        c = B.canon_of(k) or nk
        v = core.get(c)
        if v is None and c == "deliverable":
            v = "citation_report.md"
    return v


def fill_contract(core, keys, spec):
    out, filled, empty = {}, [], []
    for k in keys:
        v = contract_value(k, core)
        if v is None or v == "" or v == [] or v == {}:
            out[k] = default_for(spec.get(k))
            empty.append(k)
        else:
            out[k] = v
            filled.append(k)
    return out, filled, empty


def envelope(idx, version):
    core = {"findings": [], "citation_checks": [], "coverage": {}, "summary": "",
            "uncertainties": [], "unchecked_items": [], "sources": [], "status": "partial",
            "claims": [], "metrics": {}, "severity_summary": {}, "revisions": [],
            "numeric_checks": [], "compliance_checks": [], "result": {},
            "method_notes": {"rules_version": B.RULES_VERSION}}
    contract, filled, empty = fill_contract(core, idx.get("contract_keys") or [],
                                            idx.get("contract_spec") or {})
    res = dict(contract)
    for k, v in core.items():
        res.setdefault(k, v)
    res.update({
        "case_id": idx.get("case_id"), "status": "partial", "skill": "citation-fact-audit",
        "skill_version": version, "rules_version": B.RULES_VERSION,
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("gaps") or []) + [
            {"code": "initial_partial", "detail": "init 写出的初级 partial；build 将以工作稿 finalize"}],
        "changes": [], "plan": [],
        "run_summary": {"draft_used": False, "stage": "init"},
        "runtime": {"skill_version": version, "rules_version": B.RULES_VERSION,
                    "index_schema": A.INDEX_SCHEMA, "wall_seconds": None,
                    "finished_at": None, "deterministic": True},
        "contract_fields": {"declared": list(idx.get("contract_keys") or []),
                            "filled_empty": empty, "from": idx.get("contract_from")}})
    defaults = {"case_id": idx.get("case_id"), "deliverable": "citation_report.md",
                "evidence_map": [{"kind": "initial_index_only",
                                  "detail": "init 阶段只建索引，语义判定由工作稿提供"}],
                "change_log": [{"rule": "init", "detail": "索引建立，未做语义判定"}],
                "coverage": {f: {"checked": False, "items": 0, "findings": 0} for f in B.FACETS},
                "status": "partial"}
    for k in idx.get("contract_keys") or []:
        if res.get(k) in (None, "", [], {}):
            v = defaults.get(k)
            if v is None:
                v = defaults.get(B.canon_of(k))
            if v is not None:
                res[k] = v
    res["output_contract"] = {k: res.get(k) for k in (idx.get("contract_keys") or [])}
    res.setdefault("change_records", res.get("changes") or [])
    res.setdefault("limits", {"full_text_access": False, "external_verification": False})
    return res


# ------------------------------------------------------------------ rendering
def _cell(s, n=140):
    return A.squash(str(s or "").replace("|", "/").replace("\n", " "), n)


def render_report(result):
    cks = result.get("citation_checks") or []
    fnds = result.get("findings") or []
    cov = result.get("coverage") or {}
    L = ["# 引用与事实核验报告", "",
         "| 项 | 值 |", "|---|---|",
         "| 案例 | %s |" % (result.get("case_id") or "未提供"),
         "| 技能 / 版本 | citation-fact-audit %s（规则 %s） |" % (result.get("skill_version"),
                                                        result.get("rules_version")),
         "| 结果状态 | %s |" % result.get("status"),
         "| 核验矩阵 | %d 行 |" % len(cks),
         "| 问题清单 | %d 条（confirmed %d / pending_review %d） |"
         % (len(fnds), sum(1 for f in fnds if f.get("status") == "confirmed"),
            sum(1 for f in fnds if f.get("status") == "pending_review")),
         "| 判定分布 | %s |" % _cell(result.get("metrics", {}).get("verdicts"), 200),
         "| 严重度分布 | %s |" % _cell(result.get("metrics", {}).get("severities"), 200),
         "", "## 1 结论摘要", "", result.get("summary") or "（工作稿未提供摘要）", ""]
    L += ["## 2 引文支持核验矩阵", "",
          "| # | 判定 | 本文位置 | 被引论断 | 方向/数值/范围 | 依据 |", "|---|---|---|---|---|---|"]
    for c in cks:
        s = c.get("semantics") or {}
        tri = "/".join({True: "T", False: "F", None: "?"}.get(s.get(k), "?") for k in B.SEM)
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            _cell(c.get("check_id"), 20), c.get("verdict"), _cell((c.get("locators") or {}).get("claim_loc"), 60),
            _cell(c.get("claim_quote"), 120), tri, _cell(c.get("rationale"), 160)))
    if not cks:
        L.append("| - | - | - | 无核验行 | - | - |")
    order = {s: i for i, s in enumerate(B.SEVERITIES)}
    L += ["", "## 3 问题清单（按严重度）", ""]
    for sev in B.SEVERITIES:
        group = [f for f in fnds if f.get("severity") == sev]
        if not group:
            continue
        L += ["### %s（%d 条）" % (sev, len(group)), ""]
        for f in group:
            loc = f.get("location") or {}
            L += ["**%s · %s · %s · %s**" % (f.get("finding_id"), f.get("facet"),
                                             f.get("issue_type"), f.get("status")),
                  "",
                  "- 位置：`%s`%s" % (loc.get("locator"), "（%s）" % loc.get("section") if loc.get("section") else ""),
                  "- 原文：> %s" % _cell(f.get("quote"), 300),
                  "- 类别：%s（%s）｜严重度理由：%s" % (f.get("verdict_type"), f.get("severity"),
                                                _cell(f.get("severity_reason"), 200)),
                  "- 依据：%s" % _cell(f.get("evidence"), 400),
                  "- 判定理由：%s" % _cell(f.get("rationale"), 300),
                  "- 修改建议：%s" % _cell(f.get("revision"), 300),
                  "- 原文逐字校验：%s" % ("通过" if f.get("quote_verified") else "未命中（待复核）"),
                  ""]
    if not fnds:
        L += ["（工作稿未提供问题条目；见第 5 节未检查项与 degradations）", ""]
    L += ["## 4 数值与统计一致性", ""]
    nums = result.get("numeric_checks") or [f for f in fnds if f.get("facet") == "statistics"]
    if nums:
        L += ["| # | 位置 | 冲突描述 | 建议 |", "|---|---|---|---|"]
        for f in nums:
            L.append("| %s | %s | %s | %s |" % (_cell(f.get("finding_id"), 20),
                                               _cell((f.get("location") or {}).get("locator"), 60),
                                               _cell(f.get("evidence"), 200), _cell(f.get("revision"), 160)))
    else:
        L.append("本次未记录数值/统计一致性问题（或未检查，见下节）。")
    L += ["", "## 5 覆盖情况", "", "| 检查项 | 是否已检查 | 条目数 | 问题数 | 说明 |", "|---|---|---|---|---|"]
    for k in list(B.FACETS) + list(B.SUBS):
        row = cov.get(k) or {}
        L.append("| %s | %s | %s | %s | %s |" % (k, "是" if row.get("checked") else "否",
                                                row.get("items", "-"), row.get("findings", "-"),
                                                _cell(row.get("note"), 120)))
    for k, row in cov.items():
        if k not in B.FACETS and k not in B.SUBS and isinstance(row, dict):
            L.append("| %s | %s | %s | %s | %s |" % (k, "是" if row.get("checked") else "否",
                                                    row.get("items", "-"), row.get("findings", "-"),
                                                    _cell(row.get("note"), 120)))
    L += ["", "## 6 未检查项与不确定性", ""]
    for u in result.get("unchecked_items") or []:
        L.append("- 未检查：%s —— %s" % (_cell(u.get("item"), 120), _cell(u.get("reason"), 200)))
    for u in result.get("uncertainties") or []:
        L.append("- 不确定：%s —— %s（人工下一步：%s）" % (_cell(u.get("topic"), 80),
                                                  _cell(u.get("detail"), 240),
                                                  _cell(u.get("human_check_needed"), 160)))
    if not (result.get("unchecked_items") or result.get("uncertainties")):
        L.append("（未登记）")
    L += ["", "## 7 复核步骤（他人如何得到同一批结论）", "",
          "1. 用 `python3 scripts/main.py init` 重建索引，核对 `sources[].sha256_12` 与本次一致。",
          "2. 用 `python3 scripts/main.py show --part units --offset N --limit M` 打开每条结论的 locator，逐字比对 quote。",
          "3. 对每条 `citation_checks`：按 direction/numeric/scope 三要素复核 verdict，依据见第 2 节。",
          "4. 对每条 `pending_review`：按 `human_check_needed` 补外部核验（原文/发表状态/版本）。",
          "5. 重跑 `build` 与 `selfcheck`，比较 `result.json` 是否字节一致（确定性）。", "",
          "## 8 运行记录与降级", "",
          "- 规则版本：%s；索引 schema：%s" % (result.get("rules_version"), A.INDEX_SCHEMA),
          "- 运行摘要：%s" % _cell(result.get("run_summary"), 300)]
    for d in result.get("degradations") or []:
        L.append("- 降级：`%s` %s" % (d.get("code"), _cell(d.get("detail"), 240)))
    for c in result.get("changes") or []:
        L.append("- 修正记录：%s.%s %s → %s（%s）" % (c.get("scope"), c.get("field"),
                                                c.get("from"), c.get("to"), c.get("rule")))
    for e in result.get("errors") or []:
        L.append("- 错误：%s" % _cell(e, 240))
    if not result.get("degradations") and not result.get("errors"):
        L.append("- 无降级、无错误。")
    return "\n".join(L) + "\n"


def evidence_lines(result):
    out = []
    for c in result.get("citation_checks") or []:
        out.append(json.dumps({"kind": "citation_check", "id": c.get("check_id"),
                               "verdict": c.get("verdict"), "status": c.get("status"),
                               "locator": (c.get("locators") or {}).get("claim_loc"),
                               "quote": c.get("claim_quote"),
                               "source_locator": (c.get("locators") or {}).get("source_loc"),
                               "semantics": c.get("semantics"), "rationale": c.get("rationale"),
                               "unresolved_reason": c.get("unresolved_reason")}, ensure_ascii=False))
    for f in result.get("findings") or []:
        out.append(json.dumps({"kind": "finding", "id": f.get("finding_id"), "facet": f.get("facet"),
                               "issue_type": f.get("issue_type"), "severity": f.get("severity"),
                               "verdict_type": f.get("verdict_type"), "status": f.get("status"),
                               "locator": (f.get("location") or {}).get("locator"),
                               "quote": f.get("quote"), "evidence": f.get("evidence"),
                               "revision": f.get("revision")}, ensure_ascii=False))
    return "\n".join(out) + ("\n" if out else "")


def index_snapshot(idx):
    """A self-contained, null-free snapshot of what the run actually read and decided."""
    return {"schema": idx.get("schema"), "case_id": idx.get("case_id"), "input_dir": idx.get("input_dir"),
            "contract": {"keys": idx.get("contract_keys"), "from": idx.get("contract_from"),
                         "spec": idx.get("contract_spec")},
            "stats": idx.get("stats"),
            "sources": [{k: s.get(k) for k in ("source_id", "rel", "kind", "format", "parser", "bytes",
                                               "units", "text_chars", "quality", "sha256_12")}
                        for s in idx.get("sources") or []],
            "gaps": [{"code": g.get("code"), "scope": g.get("scope"),
                      "detail": A.squash(g.get("detail"), 240)} for g in idx.get("gaps") or []],
            "errors": list(idx.get("errors") or [])}


def render_manuscript(result):
    """The reviewed manuscript, annotated claim by claim - the reader's view of the audit."""
    L = ["# 被审稿件逐条标注（manuscript annotations）", "",
         "- 案例：%s" % (result.get("case_id") or "未提供"),
         "- 状态：%s ｜ 规则 %s ｜ 技能版本 %s" % (result.get("status"), result.get("rules_version"),
                                              result.get("skill_version")),
         "", "## 论断核验（逐条）", ""]
    for c in result.get("citation_checks") or []:
        L += ["### %s ｜ 判定 %s ｜ 状态 %s" % (c.get("check_id"), c.get("verdict"), c.get("status")),
              "", "- 位置：`%s`" % ((c.get("locators") or {}).get("claim_loc") or ""),
              "- 论断：> %s" % _cell(c.get("claim_quote"), 400),
              "- 依据：%s" % _cell(c.get("rationale"), 400)]
        src = (c.get("locators") or {}).get("source_loc")
        if src:
            L.append("- 来源位置：`%s`" % src)
        L.append("")
    if not result.get("citation_checks"):
        L += ["（无可核验论断：材料不足或未提供工作稿，见报告第 6 节）", ""]
    L += ["## 问题条目（逐条标注）", ""]
    for f in result.get("findings") or []:
        L.append("- **%s**（%s / %s / %s）：`%s` → %s" % (
            f.get("finding_id"), f.get("facet"), f.get("severity"), f.get("status"),
            (f.get("location") or {}).get("locator"), _cell(f.get("revision"), 220)))
    if not result.get("findings"):
        L.append("（未登记问题条目；未检查项与不确定性见报告第 6 节）")
    L += ["", "## 复核路径", "",
          "1. `python3 scripts/main.py show --part units --offset N --limit M` 打开每条 locator，" +
          "逐字比对该段原文。",
          "2. 对每条待复核条目按 `human_check_needed` 补外部核验（原文/发表状态/版本）。",
          "3. 重跑 `python3 scripts/main.py build` 与 `selfcheck`，比较 result.json 是否字节一致。", ""]
    return "\n".join(L) + "\n"


def manifest(idx, result, command, seconds, version):
    return {"skill": "citation-fact-audit", "skill_version": version,
            "rules_version": B.RULES_VERSION, "index_schema": A.INDEX_SCHEMA,
            "command": command, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "wall_seconds": round(seconds, 3), "python": sys.version.split()[0],
            "case_id": idx.get("case_id"), "input_dir": idx.get("input_dir"),
            "inputs": [{"rel": s.get("rel"), "bytes": s.get("bytes"), "sha256_12": s.get("sha256_12"),
                        "parser": s.get("parser"), "units": s.get("units"), "quality": s.get("quality")}
                       for s in idx.get("sources") or []],
            "counts": idx.get("stats"), "result_status": result.get("status"),
            "deterministic": "result.json 不含墙钟时间，同输入两次 build 应字节一致",
            "budget": {"model_requests": 64, "seconds": 900, "tokens_per_response": 16384}}


