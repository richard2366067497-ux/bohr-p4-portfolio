"""audit_leads.py - deterministic lead scanners for the manuscript audit skill.

Every scanner returns located *candidates*, not verdicts: each carries a verbatim
quote, a locator, a rule id and the question the reviewing agent has to answer.
Stdlib only, no network, CWD-independent.
"""

from __future__ import annotations

import re

from audit_core import (FACETS, norm, squeeze, numbers_in, _ref_entries, best_sentence)

# ---------------------------------------------------------------- lead scanning
def _cand(rule, facet, severity, issue_type, seg, why, ask, quote=None, extra=None, cue=None):
    if quote is not None:
        q = norm(quote)
    else:
        q = norm(best_sentence(seg, cue))
    if len(q) > 300:
        cut = q.rfind(" ", 0, 300)
        q = q[:cut] if cut > 200 else q[:300]
    c = {"rule": rule, "facet": facet, "severity": severity, "issue_type": issue_type,
         "uid": seg["uid"], "locator": seg["locator"], "quote": q,
         "why": why, "ask": ask, "confidence": "medium"}
    if extra:
        c.update(extra)
    return c


def _seg_by(index, uid):
    for s in index["segments"]:
        if s["uid"] == uid:
            return s
    return None


def _first(index, canon, doc_id=None):
    for s in index["segments"]:
        if s["canon"] == canon and (doc_id is None or s["doc_id"] == doc_id):
            return s
    return None


def _manuscript_ids(index):
    ids = [d["doc_id"] for d in index["documents"] if d["role"] == "manuscript"]
    return ids or [d["doc_id"] for d in index["documents"]]


def scan_structure(index):
    out = []
    mdocs = _manuscript_ids(index)
    if not mdocs or not index["segments"]:
        return out
    aggs = index["aggs"]
    present = {}
    for s in aggs["sections"]:
        if s["doc_id"] in mdocs:
            present.setdefault(s["canon"], s)
    required = [("abstract", "major", "摘要缺失：读者无法据此判断问题、方法与结论口径"),
                ("introduction", "major", "引言缺失：研究问题与动机无交代"),
                ("methods", "major", "方法章节缺失：结果不可复现、不可评估"),
                ("results", "critical", "结果章节缺失：正文没有可核对的数据呈现"),
                ("conclusion", "minor", "结论缺失：摘要/结果中的主张没有收束段落"),
                ("references", "critical", "参考文献表缺失：引用无法核对")]
    segs = index["segments"]
    for canon, sev, why in required:
        if canon in present:
            continue
        anchor = None
        for s in segs:
            if s["doc_id"] in mdocs and s["canon"] and s["canon"] != canon:
                anchor = s
                break
        if anchor is None:
            anchor = next((s for s in segs if s["doc_id"] in mdocs), None)
        if anchor is None:
            continue
        out.append(_cand("ST-01", "struct", sev, "reporting_gap", anchor,
                         "未检出 `%s` 章节或等价标题（脚本按标题词表与编号标题判定）" % canon,
                         "回原文确认该章节是否确实缺失；若以其它标题存在（如“Experimental”），"
                         "请在 draft 中 reject 并说明，不要照抄此候选"))
    order = {}
    for s in aggs["sections"]:
        if s["doc_id"] in mdocs and s["canon"] not in order:
            order[s["canon"]] = s["first_index"]
    if "results" in order and "methods" in order and order["results"] < order["methods"]:
        seg = _first(index, "results", mdocs[0])
        out.append(_cand("ST-02", "struct", "minor", "improvement", seg,
                         "结果出现在方法之前，证据链顺序倒置",
                         "确认是否为排版/预印本格式差异，是则 reject 并说明"))
    abs_seg = _first(index, "abstract", mdocs[0] if mdocs else None)
    if abs_seg:
        body_nums = set()
        for s in segs:
            if s["doc_id"] in mdocs and s["canon"] != "abstract":
                body_nums.update(numbers_in(s["text"]))
        only_abs = [n for n in numbers_in(abs_seg["text"]) if n not in body_nums]
        only_abs = [n for n in only_abs if not re.match(r"^\d{1,2}$", n)]
        if only_abs:
            out.append(_cand("ST-03", "struct", "major", "insufficient_evidence", abs_seg,
                             "摘要数值未在正文/表格中出现：%s" % ", ".join(only_abs[:8]),
                             "逐个回查是否为正文以其它形式（图表、百分比、单位换算）报告；"
                             "只有确实找不到才对摘要条目立案"))
    return out


def scan_consistency(index):
    out = []
    mdocs = _manuscript_ids(index)
    segs = [s for s in index["segments"] if s["doc_id"] in mdocs]
    abs_segs = [s for s in segs if s["canon"] == "abstract"]
    counts = {}
    for s in segs:
        for m in re.finditer(r"(?:\bn\s*=\s*|\bN\s*=\s*|样本量[为是：:]?\s*|共\s*|total\s+of\s+)"
                             r"(\d{1,5})", s["text"], re.I):
            counts.setdefault(m.group(1), []).append(s)
        for m in re.finditer(r"(\d{1,5})\s*(?:名|例|位|人|只|份)?\s*(?:participants?|patients?|"
                             r"specimens?|samples?|subjects?|mice|rats|"
                             r"受试者|患者|参与者|样本|志愿者|对象|小鼠|大鼠)", s["text"], re.I):
            counts.setdefault(m.group(1), []).append(s)
    if len(counts) > 1:
        keys = sorted(counts, key=lambda k: (-len(counts[k]), k))
        anchor = counts[keys[0]][0]
        out.append(_cand("CO-01", "consistency", "critical", "fact_error", anchor,
                         "文中出现多个样本量口径：%s" % ", ".join("%s×%d" % (k, len(counts[k]))
                                                                  for k in keys[:5]),
                         "核对是否为不同子实验（各自样本量合法）还是同一队列前后矛盾；"
                         "同一队列不同数值才算 fact_error"))
    fig_refs, cap_refs = {}, {}
    for s in segs:
        for m in re.finditer(r"(?:图|表|Fig(?:ure)?\.?|Table|Tab\.)\s*([0-9]{1,2})", s["text"], re.I):
            kind = "fig" if re.match(r"图|fig", m.group(0), re.I) else "table"
            n = m.group(1)
            tgt = fig_refs if kind == "fig" else cap_refs
            tgt.setdefault(n, []).append(s)
    for kind, refs, other in (("图", fig_refs, cap_refs), ("表", cap_refs, fig_refs)):
        for n, seglist in sorted(refs.items()):
            if n not in other:
                out.append(_cand("CO-02", "consistency", "major", "reporting_gap", seglist[0],
                                 "正文引用%s%s，但材料中未检出对应%s题注" % (kind, n, kind),
                                 "确认是否为题注未抽取（扫描件/图片）→ 记 pending_review，"
                                 "不要直接判缺失"))
    return out


def _ref_items(index):
    """[(entry_text, segment, entry_number_or_None)] for precise reference quoting."""
    items = []
    for seg in _ref_entries(index):
        txt = seg["text"]
        marks = list(re.finditer(r"\[\s*(\d{1,3})\s*\]", txt))
        if not marks:
            items.append((txt[:300], seg, None))
            continue
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(txt)
            items.append((txt[m.start():end].strip()[:300], seg, int(m.group(1))))
    return items


def scan_citation(index):
    out = []
    mdocs = _manuscript_ids(index)
    aggs = index["aggs"]
    refs = _ref_entries(index)
    n_refs = aggs["reference_count"]
    numeric = [c for c in aggs["citations"] if c["style"] == "numeric"]
    max_idx = 0
    for c in numeric:
        for n in re.findall(r"\d{1,3}", c["raw"]):
            max_idx = max(max_idx, int(n))
    if n_refs == 0:
        if numeric:
            seg = _seg_by(index, numeric[0]["uid"])
            out.append(_cand("CI-01", "citation", "critical", "citation_unsupported", seg,
                             "正文有 %d 处数字型引文标记，但未检出参考文献表" % len(numeric),
                             "确认参考文献是否在另一文件（.bib / 单独 refs 文件）中；"
                             "若确无，可判 citation_unsupported"))
    elif max_idx > n_refs:
        anchor = None
        for c in numeric:
            if any(int(n) > n_refs for n in re.findall(r"\d{1,3}", c["raw"])):
                anchor = _seg_by(index, c["uid"])
                if anchor:
                    out.append(_cand("CI-02", "citation", "major", "citation_unsupported", anchor,
                                     "引文编号 %s 超出参考文献表条目数（%d）" % (c["raw"], n_refs),
                                     "核对编号风格（是否从 [0] 起、是否多篇合并）；确认后立案"))
                    break
        if anchor is None:
            seg = _seg_by(index, numeric[0]["uid"])
            out.append(_cand("CI-02", "citation", "major", "citation_unsupported", seg,
                             "最大引文编号 %d 超出参考文献表条目数 %d" % (max_idx, n_refs),
                             "核对编号风格后确认或 reject"))
    if numeric and refs:
        cited = set()
        for c in numeric:
            for n in re.findall(r"\d{1,3}", c["raw"]):
                cited.add(int(n))
        uncited = [n for n in range(1, n_refs + 1) if n not in cited]
        if uncited and len(uncited) <= max(3, n_refs // 3):
            items = _ref_items(index)
            hit = next((it for it in items if it[2] == uncited[0]), None)
            seg, quote = (hit[1], hit[0]) if hit else (refs[0], None)
            out.append(_cand("CI-03", "citation", "minor", "citation_unsupported", seg,
                             "参考文献编号未被正文引用：%s" % ", ".join(str(n) for n in uncited[:8]),
                             "确认是否为“进一步阅读”列表（可 reject）或纯格式问题；"
                             "否则属引用表冗余条目", quote=quote))
    ay = [c for c in aggs["citations"] if c["style"] == "author-year"]
    if numeric and ay:
        seg = _seg_by(index, ay[0]["uid"])
        out.append(_cand("CI-04", "compliance", "minor", "compliance", seg,
                         "正文同时出现数字型与作者-年份型两种引文格式",
                         "确认是否为目标期刊允许的混合格式；否则属格式不一致"))
    if refs:
        miss = [it for it in _ref_items(index) if not re.search(r"(?:19|20)\d{2}", it[0])]
        if miss:
            out.append(_cand("CI-05", "citation", "minor", "reporting_gap", miss[0][1],
                             "参考文献条目缺少年份，无法核对其与正文论断的对应关系",
                             "抽查该条是否确为残缺条目；确认后立案", quote=miss[0][0]))
    return out


def _has(segs, pat):
    rx = re.compile(pat, re.I)
    for s in segs:
        if rx.search(s["text"]):
            return s
    return None


def scan_method_stats(index):
    out = []
    mdocs = _manuscript_ids(index)
    segs = [s for s in index["segments"] if s["doc_id"] in mdocs]
    method_segs = [s for s in segs if s["canon"] in ("methods",)]
    scope = method_segs or segs
    checks = [
        ("ME-01", "method", "major", "reporting_gap",
         r"\bn\s*=|\bN\s*=|样本量|受试者|参与者|例数|只数|共\s*\d+\s*(?:例|名|只|份|人)|"
         r"\d{1,5}\s*(?:名|例|位|只|份)\s*(?:受试者|患者|参与者|样本|志愿者|对象|小鼠|大鼠)|"
         r"total\s+of\s+\d+|\d+\s+(?:specimens|samples|participants|patients|mice|rats)",
         "方法/结果中未检出样本量说明（n= 或样本量描述）",
         "确认样本量是否以其它形式给出（表格、图注、试验注册号）；缺则判 reporting_gap"),
        ("ME-02", "method", "major", "reporting_gap",
         r"对照|control\b|对照组|比较组|sham|placebo|基线|baseline|vehicle|"
         r"compared|versus|\bvs\b|whereas|相比|组间",
         "未检出对照/比较组说明",
         "先判断研究类型（描述性研究可无对照）；仅在确需对照时立案"),
        ("ME-03", "method", "major", "reporting_gap",
         r"随机|randomi[sz]|盲法|blinded|blinding|分层|stratified",
         "未检出随机化/盲法说明",
         "确认是否为观察性/计算类研究（可 reject）；干预类研究缺此项为重大报告缺口"),
        ("ME-04", "method", "minor", "reporting_gap",
         r"重复|repeat|重复测量|三次|triplicate|独立实验|批次|batch",
         "未检出重复/批次信息",
         "确认是否有必要（单次观测的描述性工作可 reject）"),
        ("ST-11", "statistics", "major", "statistical_misreport",
         r"t\s*检验|t-test|ANOVA|方差分析|卡方|chi-?square|Mann-Whitney|Kruskal|回归|regression|"
         r"混合模型|mixed\s+model|bootstrap|Wilcoxon",
         "未检出统计检验方法名称",
         "若全文无推断统计则属“不适用”，reject 并说明；若报告了 p 值却无检验名则立案"),
        ("ST-12", "statistics", "major", "statistical_misreport",
         r"p\s*[<=>]\s*0?\.\d+|p\s*值|显著性|significant",
         "未检出显著性/p 值报告",
         "确认结论是否依赖显著性主张；不依赖则 reject"),
        ("ST-13", "statistics", "minor", "reporting_gap",
         r"95%\s*(?:CI|置信区间)|置信区间|confidence\s+interval|标准误|SEM|SD\b|标准差|effect\s+size|效应量",
         "未检出误差/不确定性度量（SD/SEM/CI/效应量）",
         "确认是否有均值±离散度报告；有均值无离散度属报告缺口"),
        ("ST-14", "statistics", "minor", "reporting_gap",
         r"±",
         "出现“±”但未说明其为 SD、SEM 还是 CI，也未给出 n",
         "确认文内是否另有定义（图注/表注）；缺定义则为报告缺口"),
    ]
    for rule, facet, sev, itype, pat, why, ask in checks:
        if rule == "ST-14":
            hit = _has(scope, pat)
            if not hit:
                continue
            defined = _has(segs, r"±\s*(?:SD|SEM|standard\s+deviation|standard\s+error|标准差|标准误)")
            if defined:
                continue
            out.append(_cand(rule, facet, sev, itype, hit, why, ask))
            continue
        if _has(segs, pat):
            continue
        anchor = scope[0] if scope else (segs[0] if segs else None)
        if anchor is None:
            continue
        scope_note = "（存在性全文核对；锚点取自方法章节）" if method_segs else "（存在性全文核对）"
        out.append(_cand(rule, facet, sev, itype, anchor, why + scope_note, ask,
                         quote=anchor["text"][:200]))
    # p value without test name
    if _has(segs, r"p\s*[<=]\s*0?\.\d+") and not _has(segs, r"t\s*检验|t-test|ANOVA|方差分析|卡方|"
                                                          r"chi-?square|Mann-Whitney|Kruskal|回归|"
                                                          r"regression|Wilcoxon|bootstrap"):
        seg = _has(segs, r"p\s*[<=]\s*0?\.\d+")
        out.append(_cand("ST-15", "statistics", "major", "statistical_misreport", seg,
                         "报告了 p 值但全文未指明所用检验",
                         "确认检验是否在表注/图注给出；缺则属统计报告不完整",
                         cue=r"p\s*[<=]\s*0?\.\d+"))
    # percentages without denominator
    pct = _has(segs, r"\d+(?:\.\d+)?\s*%")
    if pct and not _has(segs, r"\bn\s*=|N\s*=|共\s*\d+|样本量|total\s+of\s+\d+|"
                              r"\d+\s*(?:participants?|patients?|specimens?|samples?|例|名|只)"):
        out.append(_cand("ST-16", "statistics", "minor", "reporting_gap", pct,
                         "报告百分比但未给出分母/样本量", "确认分母是否可从表格推出；否则立案"))
    return out


def scan_logic(index):
    out = []
    mdocs = _manuscript_ids(index)
    segs = [s for s in index["segments"] if s["doc_id"] in mdocs and s["canon"] != "references"]
    HEDGE = r"可能|或许|提示|表明|暗示|倾向于|在一定|尚需|有待|suggest|may\b|might|could|likely|" \
            r"potentially|appear|indicate|consistent\s+with|we\s+speculate"
    STRONG = r"首次|证明|证实|充分说明|决定性|完全|无一例外|必然|所有|均能|普遍适用|prove[sd]?\b|" \
             r"demonstrat\w+\s+conclusively|unprecedented|invariably|always|definitely|certainly|" \
             r"undoubtedly|all\s+of\s+the"
    CAUSAL = r"导致|引起|造成|使得|归因于|驱动|决定|caus\w+|lead(?:s|ing)?\s+to|result(?:s|ed)?\s+in|" \
             r"due\s+to|driven\s+by|attribut\w+|responsible\s+for"
    OBS = r"问卷|横断面|cross-sectional|观察性|observational|相关性|correlat|association|survey|" \
          r"队列|cohort|回顾性|retrospective"
    EXP = r"随机|randomi[sz]|对照试验|controlled\s+trial|干预|intervention|实验组|处理组|" \
          r"in\s+vivo|in\s+vitro|处理条件"
    for s in segs:
        t = s["text"]
        if re.search(STRONG, t, re.I) and not re.search(HEDGE, t, re.I) and s["canon"] in \
                ("abstract", "discussion", "conclusion", "results", "other", ""):
            out.append(_cand("LO-01", "logic", "major", "logic_gap", s,
                             "强断言（首次/证明/所有/必然）缺少限定词与证据边界说明",
                             "判断该句是否超出本研究的设计与样本范围；超范围则立案并给出改写"))
        if re.search(CAUSAL, t, re.I) and re.search(OBS, t, re.I) and not re.search(EXP, t, re.I):
            out.append(_cand("LO-02", "logic", "major", "logic_gap", s,
                             "观察性/相关性设计使用了因果动词",
                             "确认设计是否支持因果；不支持则按“相关≠因果”立案"))
    # conclusion beyond data: conclusion numbers absent from results
    concl = [s for s in segs if s["canon"] == "conclusion"]
    results = [s for s in segs if s["canon"] == "results"]
    if concl and results:
        rn = set()
        for s in results:
            rn.update(numbers_in(s["text"]))
        for s in concl:
            extra = [n for n in numbers_in(s["text"]) if n not in rn and not re.match(r"^\d{1,2}$", n)]
            if extra:
                out.append(_cand("LO-03", "logic", "major", "insufficient_evidence", s,
                                 "结论中出现结果章节未报告的新数值：%s" % ", ".join(extra[:6]),
                                 "回查结果表/图是否以别的单位或形式给出；确无则属结论超出数据"))
                break
    return out


def scan_compliance(index):
    out = []
    mdocs = _manuscript_ids(index)
    segs = [s for s in index["segments"] if s["doc_id"] in mdocs]
    body = [s for s in segs if s["canon"] not in ("references", "ack", "appendix")]
    tail = (body or segs)[-1] if segs else None
    human = _has(segs, r"患者|受试者|志愿者|伦理|知情同意|informed\s+consent|IRB|ethics|动物|小鼠|大鼠|"
                       r"mice|rats|patients|participants")
    items = [
        ("CP-01", "compliance", "minor", r"数据可用性|data\s+availability|数据可获取|可用性声明|"
                                        r"补充材料|supplementary\s+data",
         "未检出数据可用性声明"),
        ("CP-02", "compliance", "minor", r"利益冲突|conflict\s+of\s+interest|competing\s+interest|"
                                        r"无利益冲突|作者声明",
         "未检出利益冲突声明"),
        ("CP-03", "compliance", "minor", r"基金|资助|funding|grant|项目编号|supported\s+by",
         "未检出资助/基金声明"),
    ]
    for rule, facet, sev, pat, why in items:
        if _has(segs, pat):
            continue
        if tail is None:
            continue
        out.append(_cand(rule, facet, sev, "compliance", tail, why,
                         "确认目标期刊是否强制要求该声明；材料可能未含投稿附件（可 reject 并说明）",
                         quote=tail["text"][:200]))
    if human and not _has(segs, r"伦理|ethics|IRB|知情同意|informed\s+consent|批准号|approval"):
        out.append(_cand("CP-04", "compliance", "major", "compliance", human,
                         "涉及人/动物研究对象但未检出伦理审批或知情同意说明",
                         "确认是否属二次分析/公开数据（可豁免）；否则属重大规范缺口"))
    # abbreviation used before definition
    defined = set()
    for s in segs:
        for m in re.finditer(r"\(([A-Z][A-Za-z]{1,7})\)", s["text"]):
            defined.add(m.group(1))
    joined = "\n".join(x["text"] for x in segs)
    seen_tok = set()
    for s in segs[:120]:
        for m in re.finditer(r"(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9])", s["text"]):
            tok = m.group(1)
            if tok in defined or tok in seen_tok:
                continue
            if tok in ("DNA", "RNA", "USA", "UK", "PDF", "AI", "SD", "CI", "SEM", "ANOVA", "IRB",
                       "HV", "HRC", "HB", "XRD", "TEM", "EDS", "FTIR", "NMR", "FIB", "GPa", "MPa",
                       "BCS", "SQUID", "PL", "IV", "CO", "CO2", "EDX", "XPS", "DSC", "TGA", "CNT"):
                continue
            if len(re.findall(r"(?<![A-Za-z0-9])" + tok + r"(?![A-Za-z0-9])", joined)) >= 2:
                seen_tok.add(tok)
                out.append(_cand("AX-01", "compliance", "minor", "compliance", s,
                                 "缩写 %s 多次出现但未检出首次定义" % tok,
                                 "确认首次出现处是否以“全称(缩写)”定义；缺则立案", cue=tok))
                break
        if len(out) > 30:
            break
    # unit / symbol variants
    joined = "\n".join(s["text"] for s in segs)
    variants = [("℃", "°C"), ("CO2", "CO₂"), ("ug", "μg"), ("ml", "mL")]
    for a, b in variants:
        if a in joined and b in joined:
            for s in segs:
                if a in s["text"] and b in s["text"]:
                    out.append(_cand("AX-02", "compliance", "suggestion", "compliance", s,
                                     "同一单位/符号存在两种写法（%s / %s）" % (a, b),
                                     "确认期刊格式要求；仅属排版偏好时可 reject"))
                    break
    return out


def scan(index):
    """Run all lead scanners, assign stable candidate ids."""
    raw = []
    for fn in (scan_structure, scan_consistency, scan_citation, scan_method_stats,
               scan_logic, scan_compliance):
        try:
            raw.extend(fn(index))
        except Exception as exc:  # noqa: BLE001
            index["notes"].append("scanner_failed:%s:%s" % (fn.__name__, exc))
    seen, uniq = set(), []
    for c in raw:
        key = (c["rule"], squeeze(c["quote"])[:120])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    uniq.sort(key=lambda c: (FACETS.index(c["facet"]) if c["facet"] in FACETS else 9,
                             c["rule"], c["uid"]))
    for i, c in enumerate(uniq[:150], 1):
        c["candidate_id"] = "C-%03d" % i
    return uniq[:150]


