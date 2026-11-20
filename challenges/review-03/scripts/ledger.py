#!/usr/bin/env python3
"""ledger.py - 台账规则层：枚举与兼容表、严重度封顶、行/发现校验、findings 派生、
覆盖统计、契约字段映射、审查单渲染。仅标准库；被 main.py 同目录 import。

  python3 -B ledger.py --selftest
"""
from __future__ import annotations

import json
import platform
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract as X

SKILL = "statistical-audit-ledger"
VERSION = "1.0.0"

FACETS = ("design_fit", "variable_definition", "statistics", "sample_size", "reporting")
FACET_LABEL = {"design_fit": "研究设计", "variable_definition": "变量定义", "statistics": "统计方法",
               "sample_size": "样本量与效能", "reporting": "结果报告"}
DIM_LABEL = {"fact": "事实核验", "citation": "引用支持", "method": "方法设计",
             "stat_report": "统计报告", "argument": "论证链", "norm": "学术规范"}
NATURES = ("method_flaw", "underreporting", "acceptable_but_should_clarify", "none")
NATURE_LABEL = {"method_flaw": "方法/判定错误", "underreporting": "报告缺失（未报告≠做错）",
                "acceptable_but_should_clarify": "可接受但需澄清", "none": "无缺陷"}
SEV = ("critical", "major", "minor", "suggestion", "none")
SEV_RANK = {"critical": 4, "major": 3, "minor": 2, "suggestion": 1, "none": 0}
NATURE_CAP = {"method_flaw": "critical", "underreporting": "major",
              "acceptable_but_should_clarify": "minor", "none": "none"}
CELL = ("ok", "gap", "na")
ASSUME = ("checked", "violated", "not_reported", "n/a")
DEFAULT_CONTRACT = ("case_id", "status", "review_report", "findings", "evidence",
                    "coverage", "uncertainty", "pending_review")

# issue_type -> (默认检查面, 默认审查维度, 允许的缺陷性质)
ISSUE_META = {
    "test_misuse": ("statistics", "method", ("method_flaw",)),
    "assumption_unchecked": ("statistics", "method", ("method_flaw", "underreporting")),
    "independence_violation": ("statistics", "method", ("method_flaw",)),
    "multiple_comparison_uncorrected": ("statistics", "method", ("method_flaw", "underreporting")),
    "sensitivity_analysis_missing": ("statistics", "method", ("underreporting", "acceptable_but_should_clarify")),
    "model_variable_mismatch": ("variable_definition", "method", ("method_flaw",)),
    "variable_definition": ("variable_definition", "method", ("underreporting", "acceptable_but_should_clarify")),
    "outcome_measure_unclear": ("variable_definition", "method", ("underreporting", "acceptable_but_should_clarify")),
    "unit_conversion_error": ("variable_definition", "fact", ("method_flaw",)),
    "terminology_ambiguity": ("variable_definition", "argument", ("acceptable_but_should_clarify",)),
    "design_mismatch": ("design_fit", "method", ("method_flaw",)),
    "confounding": ("design_fit", "method", ("method_flaw",)),
    "outcome_switching": ("design_fit", "method", ("method_flaw",)),
    "argument_gap": ("design_fit", "argument", ("method_flaw", "acceptable_but_should_clarify")),
    "registration_missing": ("design_fit", "norm", ("underreporting",)),
    "sample_size_unjustified": ("sample_size", "method", ("underreporting", "acceptable_but_should_clarify")),
    "power_claim": ("sample_size", "method", ("method_flaw", "underreporting")),
    "attrition_missing": ("sample_size", "stat_report", ("underreporting",)),
    "effect_size_missing": ("reporting", "stat_report", ("underreporting",)),
    "ci_missing": ("reporting", "stat_report", ("underreporting",)),
    "p_reporting": ("reporting", "stat_report", ("underreporting", "acceptable_but_should_clarify")),
    "internal_inconsistency": ("reporting", "fact", ("method_flaw",)),
    "factual_error": ("reporting", "fact", ("method_flaw",)),
    "reporting_gap": ("reporting", "stat_report", ("underreporting", "acceptable_but_should_clarify")),
    "citation_support_missing": ("reporting", "citation",
                                 ("underreporting", "method_flaw", "acceptable_but_should_clarify")),
    "norm_deviation": ("reporting", "norm", ("underreporting", "acceptable_but_should_clarify")),
    "data_availability_missing": ("reporting", "norm", ("underreporting",)),
    "ethics_missing": ("design_fit", "norm", ("underreporting",)),
}


# ------------------------------------------------------------------ case 读取
def case_id_of(case, inp):
    for k in ("case_id", "caseId", "id", "task_id"):
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    base = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", Path(inp).resolve().name or "case")
    if base.lower() in ("in", "input", "data", "case", ""):
        base = "case"
    return "%s-%s" % (base, X.sha1(Path(inp)) or "0000")


def case_text(case, keys=("task_instruction", "task", "instruction", "prompt", "question", "task_md")):
    for k in keys:
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def contract_fields(case):
    """识别 output_contract 字段名，返回 (fields, degradations)。键名一律保持原样。"""
    raw = None
    for k in ("output_contract", "output_spec", "outputs", "deliverables", "contract", "result_schema"):
        if isinstance(case, dict) and case.get(k) not in (None, "", [], {}):
            raw = case[k]
            break
    if raw is None:
        return list(DEFAULT_CONTRACT), ["no_output_contract: 使用内置默认字段集"]
    fields = []
    if isinstance(raw, dict):
        fields = [str(k) for k in raw.keys()]
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict):
                for kk in ("name", "field", "key", "id", "字段"):
                    if isinstance(it.get(kk), str):
                        fields.append(it[kk])
                        break
    elif isinstance(raw, str):
        fields = [s.strip() for s in re.split(r"[,\n;、]+", raw) if s.strip()]
    fields = [f for f in dict.fromkeys(fields) if f]
    if not fields:
        return list(DEFAULT_CONTRACT), ["empty_output_contract: 使用内置默认字段集"]
    return fields, []


# ------------------------------------------------------------------ 规则
def nature_ok(issue_type, nature):
    meta = ISSUE_META.get(issue_type)
    return bool(meta) and nature in meta[2]


def cap_severity(nature, severity):
    """按缺陷性质封顶；返回 (severity, changed, note)。未报告类最高 major。"""
    nature = nature if nature in NATURES else "none"
    sev = severity if severity in SEV else "none"
    if nature == "none":
        return ("none" if sev != "none" else sev), sev != "none", "nature_none_resets_severity"
    cap = NATURE_CAP[nature]
    if SEV_RANK.get(sev, 0) > SEV_RANK[cap]:
        return cap, True, "severity_capped_by_nature:%s>%s" % (sev, cap)
    return sev, False, None


def validate_ledger_row(row, index, i):
    """校验一行台账；返回 (errors, warnings)。会回写命中的 locator。"""
    e, w = [], []
    lid = row.get("ledger_id") or "L-%02d" % (i + 1)
    if not row.get("result_question"):
        w.append("%s: empty_result_question" % lid)
    ok, loc, _mid, note = X.qmatch(index, row.get("quote") or "", row.get("source_locator"))
    if not ok:
        e.append("%s: evidence_rejected(%s)" % (lid, note))
    else:
        row["source_locator"] = loc
    if str(row.get("test_appropriate", "unknown")).lower() not in ("true", "false", "unknown"):
        e.append("%s: bad_test_appropriate=%s" % (lid, row.get("test_appropriate")))
    for k in ("normality", "variance", "independence"):
        v = (row.get("assumptions") or {}).get(k, "not_reported")
        if v not in ASSUME:
            e.append("%s: bad_assumption:%s=%s" % (lid, k, v))
    if row.get("defect_nature", "none") not in NATURES:
        e.append("%s: bad_defect_nature=%s" % (lid, row.get("defect_nature")))
    for f in FACETS:
        v = (row.get("cell_status") or {}).get(f)
        if v is not None and v not in CELL:
            e.append("%s: bad_cell_status:%s=%s" % (lid, f, v))
    if row.get("defect_nature", "none") != "none":
        it = row.get("issue_type")
        if it not in ISSUE_META:
            e.append("%s: unknown_issue_type=%s" % (lid, it))
        elif not nature_ok(it, row.get("defect_nature")):
            e.append("%s: defect_nature_mismatch: %s 不允许 %s" % (lid, it, row.get("defect_nature")))
        if not row.get("severity_reason"):
            w.append("%s: missing_severity_reason" % lid)
        if not row.get("recommendation"):
            w.append("%s: missing_recommendation" % lid)
    return e, w


def validate_finding(f, index, tag):
    e, w = [], []
    if f.get("issue_type") not in ISSUE_META:
        e.append("%s: unknown_issue_type=%s" % (tag, f.get("issue_type")))
    if f.get("defect_nature") not in NATURES:
        e.append("%s: bad_defect_nature=%s" % (tag, f.get("defect_nature")))
    if f.get("severity") not in SEV:
        e.append("%s: bad_severity=%s" % (tag, f.get("severity")))
    if f.get("facet") not in FACETS:
        e.append("%s: bad_facet=%s" % (tag, f.get("facet")))
    if f.get("dimension") not in DIM_LABEL:
        e.append("%s: bad_dimension=%s" % (tag, f.get("dimension")))
    if f.get("issue_type") in ISSUE_META and f.get("defect_nature") in NATURES \
            and not nature_ok(f["issue_type"], f["defect_nature"]):
        e.append("%s: defect_nature_mismatch: %s 不允许 %s" % (tag, f["issue_type"], f["defect_nature"]))
    if SEV_RANK.get(f.get("severity"), 0) >= SEV_RANK["minor"]:
        if not f.get("quote"):
            e.append("%s: missing_quote" % tag)
        else:
            ok, loc, _m, note = X.qmatch(index, f["quote"], f.get("source_locator"))
            if ok:
                f["source_locator"] = loc
            else:
                e.append("%s: evidence_rejected(%s)" % (tag, note))
        if not f.get("severity_reason"):
            w.append("%s: missing_severity_reason" % tag)
        if not f.get("recommendation"):
            w.append("%s: missing_recommendation" % tag)
    return e, w


# ------------------------------------------------------------------ 派生
def _obs(row):
    bits = []
    for label, key in (("对比", "comparison"), ("n", "n"), ("检验", "test_declared"),
                       ("统计量", "statistic"), ("df", "df"), ("p", "p"), ("效应量", "effect_size"),
                       ("CI", "ci"), ("多重比较", "multiple_comparison")):
        v = row.get(key)
        if v not in (None, "", [], "not_reported"):
            bits.append("%s=%s" % (label, v))
    if str(row.get("test_appropriate")).lower() == "false":
        bits.append("检验与数据结构不匹配")
    return "；".join(bits) or "台账要素不全，见原文引文"


def derive_findings(ledger, extra):
    """由台账非 ok 格 + 台账外发现派生 findings（含严重度封顶与 changes）。"""
    out, changes = [], []

    def add(f, tag):
        sev, changed, note = cap_severity(f.get("defect_nature"), f.get("severity"))
        if changed:
            changes.append({"id": tag, "rule": note, "from": f.get("severity"), "to": sev})
            f["severity"] = sev
        elif SEV_RANK.get(sev, 0) < SEV_RANK.get(f.get("severity"), 0):
            f["severity"] = sev
        out.append(f)

    for i, row in enumerate(ledger or []):
        if row.get("defect_nature", "none") == "none" or row.get("severity", "none") == "none":
            continue
        it = row.get("issue_type") or "reporting_gap"
        meta = ISSUE_META.get(it, ("reporting", "stat_report", ("underreporting",)))
        facet = row.get("facet") if row.get("facet") in FACETS else meta[0]
        cells = row.get("cell_status") or {}
        if it in ("reporting_gap", "effect_size_missing", "ci_missing", "p_reporting") and cells.get("reporting") == "gap":
            facet = "reporting"
        tag = row.get("ledger_id") or "L-%02d" % (i + 1)
        add({"source": "ledger", "ledger_id": tag,
             "title": X.snip(row.get("result_question") or "未命名结果项", 90),
             "facet": facet, "dimension": meta[1], "issue_type": it,
             "defect_nature": row.get("defect_nature"), "severity": row.get("severity"),
             "severity_reason": row.get("severity_reason"), "source_locator": row.get("source_locator"),
             "quote": row.get("quote"), "observation": _obs(row),
             "recommendation": row.get("recommendation")}, tag)
    for j, f0 in enumerate(extra or []):
        if not isinstance(f0, dict):
            continue
        f = {k: v for k, v in f0.items() if k != "finding_id"}
        f["source"] = "extra"
        f["title"] = X.snip(f.get("title") or f.get("observation") or "台账外问题", 90)
        f["facet"] = f.get("facet") if f.get("facet") in FACETS else "reporting"
        f["dimension"] = f.get("dimension") if f.get("dimension") in DIM_LABEL else "method"
        if not f.get("observation") and f.get("quote"):
            f["observation"] = X.snip(f.get("quote"), 160)
        add(f, "X-%02d" % (j + 1))
    out.sort(key=lambda f: (-SEV_RANK.get(f.get("severity"), 0),
                            NATURES.index(f.get("defect_nature")) if f.get("defect_nature") in NATURES else 9,
                            str(f.get("source_locator") or "")))
    for n, f in enumerate(out, 1):
        f["finding_id"] = "F-%02d" % n
    return out, changes


def coverage(ledger, findings):
    facets = {f: {"label": FACET_LABEL[f], "judged": 0, "ok": 0, "gap": 0, "findings": 0} for f in FACETS}
    dims = {d: 0 for d in DIM_LABEL}
    for row in ledger or []:
        cs = row.get("cell_status") or {}
        for f in FACETS:
            if cs.get(f) in ("ok", "gap"):
                facets[f]["judged"] += 1
                facets[f][cs[f]] += 1
    for fd in findings or []:
        if fd.get("facet") in facets:
            facets[fd["facet"]]["findings"] += 1
        if fd.get("dimension") in dims:
            dims[fd["dimension"]] += 1
    covered = [f for f in FACETS if facets[f]["judged"] or facets[f]["findings"]]
    return {"facets": facets,
            "dimensions": {d: {"label": DIM_LABEL[d], "count": dims[d]} for d in DIM_LABEL},
            "facets_covered": len(covered), "facets_total": len(FACETS),
            "missing_facets": [f for f in FACETS if f not in covered],
            "dimensions_covered": [d for d in DIM_LABEL if dims[d]],
            "dimensions_missing": [d for d in DIM_LABEL if not dims[d]],
            "ledger_rows": len(ledger or []), "findings": len(findings or []),
            "severity_counts": {s: sum(1 for f in (findings or []) if f.get("severity") == s) for s in SEV[:-1]},
            "nature_counts": {n: sum(1 for f in (findings or []) if f.get("defect_nature") == n)
                              for n in NATURES[:-1]}}


# ------------------------------------------------------------------ 契约映射
def map_contract_value(field, art):
    """按语义把产物映射到契约字段；识别不到返回 (None, 'unmapped')。"""
    k = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(field).lower())
    has = lambda *ws: any(w in k for w in ws)
    if has("ledger", "audittable", "statisticstable", "台账"):
        return art.get("ledger"), None
    if has("finding", "issue", "defect", "problem", "缺陷", "问题", "意见"):
        return art.get("findings"), None
    if has("未覆盖", "uncovered", "missing", "gap"):
        return art.get("unchecked_items"), None
    if has("coverage", "checklist", "matrix", "facet", "覆盖", "检查面"):
        return art.get("coverage"), None
    if has("evidence", "source", "citation", "locator", "quote", "证据", "来源", "引用"):
        return art.get("evidence_index") or art.get("sources"), None
    if has("pending", "todo", "待复核", "recheck"):
        return art.get("pending_review"), None
    if has("uncertain", "limitation", "risk", "不确定", "局限"):
        return art.get("uncertainty"), None
    if has("degrad", "error", "failure", "降级", "错误"):
        return art.get("errors") or art.get("degradations"), None
    if has("summary", "conclusion", "abstract", "摘要", "结论", "总结", "verdict"):
        return art.get("summary"), None
    if has("report", "audit", "reviewdoc", "markdown", "报告", "审查单", "review"):
        return art.get("report_md"), None
    if has("manifest", "runinfo", "meta", "runtime", "运行", "记录"):
        return art.get("run_manifest_lite"), None
    if has("score", "metric", "count", "统计数"):
        return (art.get("coverage") or {}).get("severity_counts"), None
    if has("status", "state", "状态"):
        return art.get("status"), None
    if has("caseid") or k in ("id", "case"):
        return art.get("case_id"), None
    return None, "unmapped"


def fill_contract(fields, art):
    """回填全部契约字段：键名不变；缺值 null（列表字段给 []）；未映射记 degradations。"""
    out, deg = {}, []
    for f in fields:
        v, note = map_contract_value(f, art)
        lk = re.sub(r"[^a-z\u4e00-\u9fff]", "", str(f).lower())
        if note and hasattr(v, "__len__") and not isinstance(v, str):
            v = []
        elif note and any(t in lk for t in ("list", "finding", "issue", "evidence", "问题")):
            v = []
        out[f] = v
        if note:
            deg.append("contract_field_unmapped:%s" % f)
    return out, deg


# ------------------------------------------------------------------ 渲染
def _cell(v):
    if v is None or v == "":
        return "—"
    if isinstance(v, (list, tuple)):
        return "、".join(_cell(x) for x in v) or "—"
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)[:120]
    s = str(v).replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 120 else s[:120] + "…"


def render_report(ctx):
    meta, cov, led, fins = ctx.get("meta") or {}, ctx.get("coverage") or {}, ctx.get("ledger") or [], \
        ctx.get("findings") or []
    L = ["# 研究方法与统计审查单（统计审计台账派生理）\n",
         "> Skill `%s` v%s；状态 `%s`。每条问题可按 `source_locator` 回到原文，按 `ledger_id` 回到台账行。\n"
         % (SKILL, VERSION, ctx.get("status")),
         "## 一、审查概要\n", "| 项 | 值 |", "|---|---|"]
    for label, key in (("case_id", "case_id"), ("稿件", "title"), ("研究设计", "design_type"),
                       ("学科", "field"), ("对照报告规范", "target_guideline"), ("报告样本量", "n_reported")):
        L.append("| %s | %s |" % (label, _cell(meta.get(key))))
    sc = cov.get("severity_counts", {})
    L.append("| 台账行数 / 问题数 | %d / %d（critical %d·major %d·minor %d·suggestion %d） |"
             % (len(led), len(fins), sc.get("critical", 0), sc.get("major", 0), sc.get("minor", 0),
                sc.get("suggestion", 0)))
    L.append("| 五面覆盖 / 六维覆盖 | %d/%d / %d/6 |" % (cov.get("facets_covered", 0),
                                                   cov.get("facets_total", 5), len(cov.get("dimensions_covered", []))))
    if meta.get("design_type") or meta.get("target_guideline"):
        L.append("\n**审查口径**：以 `%s` 设计类型应具备的方法学要素为锚点，对照 `%s` 逐项核对；"
                 "「未报告」与「做错了」分列不同缺陷性质，严重度按性质封顶。\n"
                 % (_cell(meta.get("design_type")), _cell(meta.get("target_guideline"))))
    L += ["## 二、台账总表（每个被报告的结果一行）\n"]
    if led:
        L += ["| # | 结果问题 | 对比 | n | 声明检验 | 统计量/df | p | 效应量 | 95%CI | 缺陷性质 | 严重度 | 位置 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in led:
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | `%s` |" % (
                r.get("ledger_id"), _cell(X.snip(r.get("result_question"), 44)), _cell(X.snip(r.get("comparison"), 18)),
                _cell(r.get("n")), _cell(X.snip(r.get("test_declared"), 24)),
                _cell("%s %s" % (_cell(r.get("statistic")), _cell(r.get("df")))),
                _cell(r.get("p")), _cell(r.get("effect_size")), _cell(r.get("ci")),
                r.get("defect_nature", "none"), r.get("severity", "none"), _cell(r.get("source_locator"))))
    else:
        L.append("_台账为空：见第六节未检查项与降级说明。_")
    L += ["\n## 三、按检查面的缺口统计\n", "| 检查面 | 已判定行 | ok | gap | 关联问题 |", "|---|---|---|---|---|"]
    for f in FACETS:
        c = (cov.get("facets") or {}).get(f, {})
        L.append("| %s（`%s`） | %d | %d | %d | %d |" % (FACET_LABEL[f], f, c.get("judged", 0), c.get("ok", 0),
                                                     c.get("gap", 0), c.get("findings", 0)))
    if cov.get("missing_facets"):
        L.append("\n**未覆盖检查面**：%s —— 记为未检查，不写成「无问题」。"
                 % "、".join(FACET_LABEL[f] for f in cov["missing_facets"]))
    L += ["\n## 四、六类审查面覆盖\n", "| 审查面 | 命中问题数 |", "|---|---|"]
    for d, v in (cov.get("dimensions") or {}).items():
        L.append("| %s（`%s`） | %d |" % (DIM_LABEL.get(d, d), d, v.get("count", 0)))
    L.append("\n## 五、逐条问题（由台账派生，可逐条回复）\n")
    if not fins:
        L.append("_无已确认问题：可能方法报告完备，也可能材料不可读；请结合第六节判断，不要据此写「无缺陷」。_")
    for f in fins:
        L.append("### %s %s" % (f.get("finding_id"), f.get("title")))
        L.append("- **检查面 / 审查面**：%s（`%s`）/ %s（`%s`）" % (
            FACET_LABEL.get(f.get("facet"), f.get("facet")), f.get("facet"),
            DIM_LABEL.get(f.get("dimension"), f.get("dimension")), f.get("dimension")))
        L.append("- **缺陷性质 / 严重度**：%s（`%s`）/ `%s`" % (
            NATURE_LABEL.get(f.get("defect_nature"), f.get("defect_nature")), f.get("defect_nature"), f.get("severity")))
        if f.get("source") == "ledger":
            L.append("- **台账来源**：`%s`" % f.get("ledger_id"))
        if f.get("observation"):
            L.append("- **观察**：%s" % f.get("observation"))
        if f.get("quote"):
            L.append("- **原文**（`%s`）：“%s”" % (f.get("source_locator"), f.get("quote")))
        if f.get("severity_reason"):
            L.append("- **判断依据**：%s" % f.get("severity_reason"))
        if f.get("recommendation"):
            L.append("- **修改建议**：%s" % f.get("recommendation"))
        L.append("")
    pend = ctx.get("pending_review") or []
    unch = ctx.get("unchecked_items") or []
    L += ["## 六、待复核、未检查与降级\n",
          "**待复核**：%s" % ("；".join(str(x) for x in pend) if pend else "无"),
          "", "**未检查项**：%s" % ("；".join("%s（%s）" % (u.get("item"), u.get("reason")) for u in unch
                                         if isinstance(u, dict)) if unch else "无"),
          "", "**降级**：%s" % ("；".join(str(x) for x in (ctx.get("degradations") or [])) or "无"),
          "", "**不确定性**：%s" % ("；".join(str(x) for x in (ctx.get("uncertainty") or [])) or "无"),
          "", "## 七、复核方法与本版局限\n",
          "1. 在 `/app/work` 重跑 `main.py init → show → check → build`；`result.json`、`findings.json` 内容应稳定一致（时间戳只进 `run_manifest.json`）。",
          "2. 任取一条 finding，按 `source_locator` 打开材料，`quote` 应与原文逐字一致（匹配仅做 NFKC 与空白折叠）。",
          "3. 按 `ledger_id` 回查 `statistics_ledger.json`，核对判定格、缺陷性质与严重度是否自洽。",
          "4. 局限：不重算统计量、不做图像取证、不做文献检索；只审已提供文本，未读到的写第六节。"]
    return "\n".join(L) + "\n"


def runtime_block(inp, out, wrk, mode):
    return {"skill": SKILL, "version": VERSION, "mode": mode,
            "python": platform.python_version(), "input_root": str(inp),
            "output_root": str(out), "work_root": str(wrk),
            "budget": {"model_requests": 64, "seconds": 900, "tokens_per_response": 16384}}


def _selftest():
    ok = True

    def chk(c, msg):
        nonlocal ok
        print(("PASS  " if c else "FAIL  ") + msg)
        ok = ok and bool(c)

    idx = {"materials": [{"id": "ms", "units": [
        {"locator": "ms:§Results/L10", "text": "Groups differed (F(2,45)=3.21, p = 0.049)."},
        {"locator": "ms:§Methods/L3", "text": "We randomized 120 patients into three arms."}]}]}
    chk(cap_severity("underreporting", "critical")[0] == "major", "未报告类封顶 major")
    chk(cap_severity("acceptable_but_should_clarify", "major")[0] == "minor", "可接受类封顶 minor")
    chk(cap_severity("method_flaw", "critical")[:2] == ("critical", False), "方法错误可保留 critical")
    chk(nature_ok("test_misuse", "method_flaw") and not nature_ok("test_misuse", "underreporting"),
        "issue_type↔nature 兼容表")
    f, ch = derive_findings([{"ledger_id": "L-01", "result_question": "主效应", "defect_nature": "underreporting",
                              "severity": "critical", "issue_type": "ci_missing", "quote": "p = 0.049", "n": 120}], [])
    chk(f and f[0]["severity"] == "major" and ch and ch[0]["to"] == "major", "派生时执行封顶并记 changes")
    e, _w = validate_ledger_row({"ledger_id": "L-00", "quote": "totally absent sentence", "defect_nature": "none"},
                                idx, 0)
    chk(any("evidence_rejected" in x for x in e), "伪造引文在行校验中被拒")
    fs, deg = contract_fields({"output_contract": {"review_report": None, "findings": [], "排版审美": None}})
    chk(fs == ["review_report", "findings", "排版审美"] and not deg, "契约字段原名提取")
    art = {"case_id": "c1", "status": "ok", "findings": [1], "ledger": [2], "sources": [], "coverage": {},
           "pending_review": [], "uncertainty": [], "summary": "s", "report_md": "# r", "errors": [],
           "degradations": [], "run_manifest_lite": {}}
    filled, d2 = fill_contract(fs, art)
    chk(filled["review_report"] == "# r" and filled["findings"] == [1], "契约语义映射：报告/问题")
    chk(filled["排版审美"] is None and "contract_field_unmapped:排版审美" in d2, "未知字段置 null 并记降级")
    cov = coverage([{"cell_status": {"design_fit": "ok", "statistics": "gap"}}],
                   [{"facet": "statistics", "dimension": "method", "severity": "major"}])
    chk(cov["facets_covered"] == 2 and cov["severity_counts"]["major"] == 1, "覆盖计数")
    chk("五、" in render_report({"status": "partial", "coverage": cov, "ledger": [], "findings": [],
                                 "meta": {}, "degradations": ["x"]}), "报告渲染七节")
    print("\nSELFTEST(ledger) %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
