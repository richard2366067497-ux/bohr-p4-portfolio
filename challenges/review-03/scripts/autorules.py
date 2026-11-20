import re

import extract as X
import ledger as L

EMPTY_ROW = {"result_question": "", "comparison": "", "n": "", "test_declared": "",
             "test_appropriate": "unknown", "statistic": "", "df": "", "p": "", "effect_size": "",
             "ci": "", "multiple_comparison": "", "sample_size_basis": "", "attrition": "",
             "defect_nature": "none", "severity": "none", "severity_reason": "",
             "issue_type": "", "recommendation": ""}

# -*- coding: utf-8 -*-
"""autorules.py - 无 draft 时的确定性自动推导规则（只报原文可逐字核验的报告完整性缺口）。

所有 findings 都来自材料原文的逐字引文；不重算数值、不编造数据；标注 auto_derived/low。
"""
AUTO_COMP_RE = re.compile(r"(?:versus|vs\.?|compared\s+(?:with|to)|compared|difference|higher|lower|increase|decrease|"
                          r"improvement|significant|显著|高于|低于|相比|差异)", re.I)
AUTO_TEST_RE = re.compile(r"(two-sample\s+t[\s-]?test|paired\s+t[\s-]?test|t[\s-]?test|ANOVA|方差分析|"
                          r"chi[\s-]?square|卡方|Mann[\s-]Whitney|Wilcoxon|Kruskal[\s-]Wallis|log[\s-]rank|"
                          r"mixed[\s-]?model|regression)", re.I)
AUTO_CI_RE = re.compile(r"95\s*%\s*(?:ci|confidence\s+interval)|confidence\s+interval|置信区间", re.I)
AUTO_NORM_RE = re.compile(r"shapiro|kolmogorov|levene|normality|正态|方差齐", re.I)
AUTO_CAUSAL_RE = re.compile(r"\bproves?\b|\bcauses?\b|\bdemonstrates?\b|\bestablishes?\b|证明|导致|决定性地", re.I)


def _has(text, words):
    return any(w in text for w in words)


NEG_RE = re.compile(r"(?:no|not|none|never|without|未|没有|无|并未|未做|不适用)\s*$")


def _negated_before(text, pos, window=36):
    return bool(re.search(r"(?:no|not|none|never|without|未|没有|无|并未|未做|不适用)",
                          text[max(0, pos - window):pos], re.I))


def _actual_effsize(low):
    return bool(re.search(r"(?:cohen'?s?\s*d|hedges'?\s*g|eta\s*(?:squared|2)|η²|odds\s+ratio|hazard\s+ratio|"
                          r"risk\s+ratio|standardized\s+mean\s+difference|\bSMD\b|\bOR\b|\bHR\b|\bRR\b|效应量)"
                          r"\s*[=:]?\s*-?\d", low))


def _auto_doc_flags(st):
    text = X.material_text(st["index"])
    low = text.lower()
    design = (X.design_hints(st["index"]) or {}).get("design_words") or []

    def mentions_ok(words):
        for w in words:
            i = low.find(w)
            if i >= 0 and not _negated_before(low, i):
                return True
        return False

    ci_pos = AUTO_CI_RE.search(low)
    return {
        "text": text, "low": low,
        "ci_ok": bool(X.RE_CI.search(text)),   # 只有真正出现数值区间才算“报告了 CI”
        "eff_ok": _actual_effsize(low),
        "mc_ok": mentions_ok(X.MC_WORDS),
        "ss_ok": bool(re.search(r"sample\s*size|power\s+(?:analysis|calculation|estimate)|g\*power|"
                                 r"achieved\s+power|minimum\s+detectable|样本量|把握度|检验效能", low)),
        "att_ok": mentions_ok(X.ATT_WORDS),
        "norm_ok": bool(AUTO_NORM_RE.search(low)) and not _negated_before(low, AUTO_NORM_RE.search(low).start()),
        "test_mentioned": bool(AUTO_TEST_RE.search(low)),
        "design_words": design,
    }


def _auto_question(quote, i):
    q = re.sub(r"\s+", " ", str(quote or "")).strip()
    base = re.split(r"[（(。;；]", q)[0][:80] or ("结果项 %d" % (i + 1))
    return X.snip(base, 80)


def _auto_row(st, seed, flags, i):
    tok = seed.get("observed_tokens") or {}
    quote = seed.get("quote") or ""
    p_tokens = tok.get("p") or []
    n_tokens = tok.get("n") or []
    stat_tokens = tok.get("statistic") or []
    comparison = ""
    m = re.search(r"([A-Za-z0-9\u4e00-\u9fff\-]{2,24})\s*(?:versus|vs\.?|compared\s+(?:with|to)|与|比)\s*"
                  r"([A-Za-z0-9\u4e00-\u9fff\-]{2,24})", quote, re.I)
    if m:
        comparison = "%s vs %s" % (m.group(1), m.group(2))
    row = dict(EMPTY_ROW,
               ledger_id=seed.get("seed_id"), source_locator=seed.get("source_locator"), quote=quote,
               result_question=_auto_question(quote, i), comparison=comparison,
               n=(n_tokens[0] if n_tokens else "not_reported"),
               test_declared=(AUTO_TEST_RE.search(quote).group(1) if AUTO_TEST_RE.search(quote) else "not_reported"),
               statistic=(", ".join(stat_tokens) if stat_tokens else "not_reported"),
               p=(", ".join(p_tokens) if p_tokens else "not_reported"),
               effect_size=("reported_elsewhere" if flags["eff_ok"] else "not_reported"),
               ci=("reported_elsewhere" if flags["ci_ok"] else "not_reported"),
               multiple_comparison=("corrected_elsewhere" if flags["mc_ok"] else "not_reported"),
               sample_size_basis=("reported_elsewhere" if flags["ss_ok"] else "not_reported"),
               attrition=("reported_elsewhere" if flags["att_ok"] else "not_reported"),
               assumptions={"normality": ("checked_elsewhere" if flags["norm_ok"] else "not_reported"),
                            "variance": ("checked_elsewhere" if flags["norm_ok"] else "not_reported"),
                            "independence": "not_reported"},
               seed_tokens=tok, seed_flags=seed.get("flags"), judged=True, auto_derived=True,
               cell_status={f: ("na" if f in ("variable_definition", "design_fit") else "ok") for f in L.FACETS})
    # 机械可核验的格子状态：报告完整性逐项检查（只报原文确实没写的）
    if p_tokens:
        row["cell_status"]["reporting"] = "ok" if (flags["ci_ok"] and flags["eff_ok"]) else "gap"
    row["cell_status"]["statistics"] = ("ok" if (row["test_declared"] != "not_reported"
                                                   and row["statistic"] != "not_reported") else
                                        ("gap" if p_tokens else "na"))
    row["cell_status"]["sample_size"] = ("ok" if n_tokens else ("gap" if p_tokens else "na"))
    if flags["design_words"]:
        row["cell_status"]["design_fit"] = "ok" if flags["att_ok"] else "gap"
    exact_p = any("=" in t for t in p_tokens)
    ineq_p = any(("<" in t or ">" in t) for t in p_tokens)
    is_comp = bool(AUTO_COMP_RE.search(quote))
    rule = None
    if exact_p and is_comp and not flags["ci_ok"]:
        rule = ("ci_missing", "underreporting", "major",
                "原文报告了精确 p 值与组间比较，但全文未出现置信区间（CI）；区间是判断差异强度的必需报告项（未报告≠做错）。",
                "在该结果处补报 95% CI（并说明效应量口径，如均值差及其 CI）。")
    elif exact_p and is_comp and not flags["eff_ok"]:
        rule = ("effect_size_missing", "underreporting", "major",
                "原文仅报告 p 值与方向，未给出效应量；读者无法判断差异的实际大小（未报告≠做错）。",
                "补报与设计匹配的效应量（如 Cohen's d / Hedges' g / η² 及其 CI）。")
    elif ineq_p and not re.search(r"(?:significance|alpha|显著性水平|检验水准|threshold)\s*(?:was\s*)?(?:set|设定|设为)|alpha\s*=|α\s*=", quote, re.I):
        rule = ("p_reporting", "underreporting", "minor",
                "原文以不等式（如 p < 0.05）报告显著性，未给出精确 p 值、检验统计量与自由度。",
                "报告精确 p 值、检验统计量与自由度；若只能给阈值，需说明原因。")
    elif AUTO_CAUSAL_RE.search(quote) and not flags["design_words"]:
        rule = ("argument_gap", "acceptable_but_should_clarify", "minor",
                "原文使用因果/证明式表述，但材料中未见随机化或因果识别设计；表述强度超出可支持范围。",
                "改为相关性/关联性表述，或补充能支持因果推断的设计与证据。")
    if rule:
        row.update(issue_type=rule[0], defect_nature=rule[1], severity=rule[2],
                   severity_reason=rule[3], recommendation=rule[4], auto_rule=rule[0])
        row["cell_status"]["reporting"] = "gap"
    return row


def auto_derive(st):
    """无 draft 时的确定性回退：只产出"原文自身可核验"的报告完整性问题。

    每条 finding 的 quote 都取自原文并带 locator，标注 auto_derived/low confidence；
    不做数值重算、不做结论性判断、不编造数据。"""
    flags = _auto_doc_flags(st)
    rows = [_auto_row(st, seed, flags, i) for i, seed in enumerate(st["seeds"])]
    comp_seeds = [s for s in st["seeds"]
                  if (s.get("observed_tokens") or {}).get("p") and AUTO_COMP_RE.search(s.get("quote") or "")]
    p_seeds = [s for s in st["seeds"] if (s.get("observed_tokens") or {}).get("p")]

    def extra(issue, nature, sev, reason, rec, seed, facet, dimension):
        return {"source": "auto", "auto_derived": True, "issue_type": issue, "defect_nature": nature,
                "severity": sev, "severity_reason": reason, "recommendation": rec,
                "facet": facet, "dimension": dimension,
                "title": X.snip(reason, 90), "observation": X.snip(reason, 200),
                "quote": seed.get("quote"), "source_locator": seed.get("source_locator"),
                "confidence": "low", "status": "auto_derived"}

    extras = []
    rep = (comp_seeds or p_seeds or st["seeds"] or [None])[0]
    if rep is not None and p_seeds and not flags["ss_ok"]:
        extras.append(extra("sample_size_unjustified", "underreporting", "minor",
                            "全文报告了显著性结果，但未给出样本量估算依据（效应量来源/把握度/显著性水平）。",
                            "补报样本量估算方法与依据，或说明为何未做估算。",
                            rep, "sample_size", "method"))
    if rep is not None and len(comp_seeds) >= 3 and not flags["mc_ok"]:
        extras.append(extra("multiple_comparison_uncorrected", "underreporting", "major",
                            "材料报告了 %d 组以上两两比较的 p 值，但未说明多重比较校正方法。" % len(comp_seeds),
                            "说明比较族与校正方法（如 Holm/Bonferroni/FDR），并报告校正后 p 值。",
                            comp_seeds[0], "statistics", "method"))
    if rep is not None and flags["test_mentioned"] and not flags["norm_ok"]:
        mseed = next((s for s in st["seeds"] if AUTO_TEST_RE.search(s.get("quote") or "")), rep)
        extras.append(extra("assumption_unchecked", "underreporting", "major",
                            "材料使用参数检验（t/ANOVA 等），但未报告正态性/方差齐性等前提检验。",
                            "补报前提检验方法与结果，或说明改用非参数/稳健方法的理由。",
                            mseed, "statistics", "method"))
    if flags["design_words"] and not flags["att_ok"] and p_seeds:
        extras.append(extra("attrition_missing", "underreporting", "minor",
                            "材料出现设计线索（%s），但未报告失访/剔除/缺失数据处理。"
                            % ",".join(flags["design_words"][:3]),
                            "补报入组、失访、剔除人数与处理方式（流程图/表格）。",
                            rep, "sample_size", "stat_report"))
    degr = ["auto_derived_no_draft: 未写工作稿，按内置确定性规则从原文可核验事实派生问题"
            "（%d 行台账 / %d 条问题，confidence=low）；写 draft.json 可获得高质量人工判定路径" % (
                len(rows), sum(1 for r in rows if r.get("defect_nature", "none") != "none") + len(extras))]
    unc = ["auto_derived：以下问题由脚本按原文可核验的报告完整性规则派生（未做人工判定）："
           "缺 CI/效应量、p 值报告方式、样本量依据、多重比较、前提检验；"
           "每条均带原文逐字引文与 locator，可逐条复核；如需「方法是否做错」的判断请写 draft.json 后重跑。"]
    return {"rows": rows, "extra": extras, "degradations": degr, "uncertainties": unc}
