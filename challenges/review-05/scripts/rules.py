#!/usr/bin/env python3
"""rules.py -- requirement catalogue, text normalisation, evidence gate, validators and
renderers for the academic-compliance-matrix skill (stdlib only, no network).

The catalogue encodes *requirements as plain checkable statements* plus search probes.
It deliberately stores no clause numbers and no venue-specific limits: those must come
from the user's own materials, otherwise the row has to stay `unverifiable`.
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

VERSION = "acm-1.0.0"
DOMAINS = ["integrity", "citation_norm", "privacy", "copyright", "ethics", "venue", "declaration"]
SRCS = ["ethical_norm", "venue_guideline", "provided_policy", "general_practice", "internal_consistency"]
VERDICTS = ["compliant", "violation", "not_applicable", "unverifiable"]
SEVS = ["critical", "major", "minor", "suggestion"]
SEV_W = {"critical": 0, "major": 1, "minor": 2, "suggestion": 3}
VERDICT_CN = {"compliant": "满足", "violation": "违规", "not_applicable": "不适用", "unverifiable": "待复核"}

# ---------------------------------------------------------------- requirement catalogue
CAT = [
    ("INT-01", "integrity", "ethical_norm",
     "复用或改编他人数据/图像时应在正文或图注中声明来源",
     ["adapt(?:ed)?\\s+from", "reproduc(?:ed|tion)\\s+(?:from|with|of)", "previously\\s+published",
      "改编", "转载", "引自.{0,10}(?:文献|发表)"]),
    ("INT-02", "integrity", "general_practice",
     "同一材料若已以会议版/预印本形式发表，应交叉引用并说明增量",
     ["preprint", "conference\\s+(?:version|paper)", "extended\\s+version", "预印本", "会议版", "arXiv"]),
    ("INT-03", "integrity", "general_practice",
     "作者列表与作者贡献/致谢中的角色分配应一致",
     ["author\\s+contributions?", "CRediT", "contributed\\s+equally", "作者贡献", "共同一作"]),
    ("INT-04", "integrity", "internal_consistency",
     "基金编号与项目名在正文、致谢与声明区块中应一致",
     ["(?:grant|fund|project|NSF|NIH|No\\.)\\s*[:：]?\\s*[A-Z0-9][A-Z0-9\\-]{3,}", "基金", "项目编号", "资助"]),
    ("CITE-01", "citation_norm", "general_practice",
     "正文每个引用标记都能在文献表中找到对应条目（无悬空引用）",
     ["\\[\\d{1,3}", "（[A-Z][A-Za-z\\-]+.{0,12}\\d{4}）", "\\([A-Z][A-Za-z\\-]+.{0,12}\\d{4}\\)"]),
    ("CITE-02", "citation_norm", "general_practice",
     "文献表条目均被正文引用（无凑数条目）", []),
    ("CITE-03", "citation_norm", "internal_consistency",
     "文献编号应连续、无重复，且与正文首次出现顺序一致", ["\\[\\d{1,3}\\]"]),
    ("CITE-04", "citation_norm", "general_practice",
     "正文论断与所引文献的内容应对应（无引而不证、张冠李戴）",
     ["\\[\\d{1,3}", "et\\s+al\\.", "等\\."]),
    ("CITE-05", "citation_norm", "general_practice",
     "文献条目元数据应完整（作者/年份/题名/出处/卷期页或 DOI）且格式统一",
     ["doi[:\\s/.]", "vol\\.?\\s*\\d+", "\\bpp?\\.\\s*\\d+", "\\d{4};\\d+"]),
    ("CITE-06", "citation_norm", "general_practice",
     "被引文献应真实存在且元数据与原文一致（离线仅能形式核对）", []),
    ("PRIV-01", "privacy", "ethical_norm",
     "材料中的可识别个人信息应最小化并脱敏（示例值用占位符）",
     ["[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}", "1[3-9]\\d{9}",
      "(?:patient|subject|患者|受试者)\\s*(?:id|no\\.?|编号|#)", "\\d{17}[\\dXx]"]),
    ("PRIV-02", "privacy", "ethical_norm",
     "受限/未公开数据应说明授权范围与使用条件（数据使用协议、许可）",
     ["data\\s+use\\s+agreement", "restricted", "under\\s+licen[cs]e", "授权", "受限数据", "脱敏数据"]),
    ("PRIV-03", "privacy", "ethical_norm",
     "涉及人的数据应同时具备伦理审批与知情同意依据（与 ETH 行交叉核对）",
     ["ethic", "IRB", "consent", "伦理", "知情同意"]),
    ("COPY-01", "copyright", "general_practice",
     "来自第三方的图片/表格应标注来源与许可（adapted/reproduced + permission 或 CC 许可）",
     ["CC[\\-\\s]BY", "creative\\s+commons", "copyright", "permission", "版权", "许可协议"]),
    ("COPY-02", "copyright", "general_practice",
     "代码/数据集许可声明应与实际可用性说明一致（开源许可类型、仓库地址）",
     ["github\\.com", "zenodo", "figshare", "Apache|MIT|GPL|BSD", "代码可用", "数据可用"]),
    ("COPY-03", "copyright", "general_practice",
     "复用第三方材料若超出合理使用范围，应补授权或替换（材料内无法确认时标待复核）",
     ["adapted\\s+from", "reprinted", "with\\s+permission", "转载", "改编"]),
    ("ETH-01", "ethics", "ethical_norm",
     "涉及人的研究应给出伦理批件编号、批准机构与覆盖范围",
     ["(?:IRB|Ethics|伦理).{0,40}(?:No\\.|编号|approval|批件)", "approv(?:ed|al)\\s+by", "伦理委员会"]),
    ("ETH-02", "ethics", "ethical_norm",
     "应说明知情同意的获取方式（书面/口头/豁免及理由）",
     ["informed\\s+consent", "知情同意", "consent\\s+was\\s+(?:obtained|waived)", "豁免知情"]),
    ("ETH-03", "ethics", "ethical_norm",
     "动物实验应说明伦理审批与福利措施（无动物实验时应显式说明不适用）",
     ["\\banimal", "\\bmice\\b|\\bmouse\\b|\\brats?\\b", "动物", "3R", "IACUC"]),
    ("ETH-04", "ethics", "internal_consistency",
     "风险/获益表述应与实际研究设计、样本量相符（不夸大获益、不淡化风险）",
     ["\\brisk", "\\bbenefit", "风险", "获益", "安全性"]),
    ("VEN-01", "venue", "venue_guideline",
     "材料应包含目标期刊/会议作者指南（用途：逐条映射投稿要求）",
     ["instructions?\\s+for\\s+authors", "guide\\s+for\\s+authors", "author\\s+guidelines?",
      "submission\\s+guidelines?", "投稿要求", "征稿", "call\\s+for\\s+papers"]),
    ("VEN-02", "venue", "venue_guideline",
     "篇幅/字数/图表/参考文献数量应符合指南上限（须以指南原文为据）",
     ["word\\s+limit", "字数", "maximum\\s+(?:of\\s+)?\\d+", "no\\s+more\\s+than\\s+\\d+"]),
    ("VEN-03", "venue", "venue_guideline",
     "结构要素（摘要/关键词/声明区块/补充材料）应符合指南要求",
     ["structured\\s+abstract", "keywords?", "supplementary\\s+material", "关键词", "补充材料"]),
    ("VEN-04", "venue", "venue_guideline",
     "所依据指南的版本与生效日期应注明（报告须写明依据哪一版）",
     ["version", "版本", "effective\\s+\\d{4}", "20\\d{2}\\s*年?\\s*版"]),
]

DECL = [
    ("DEC-01", "funding", ["fund(?:ing|ed)", "grant", "supported\\s+by", "基金", "资助"]),
    ("DEC-02", "acknowledgment", ["acknowledg", "致谢", "the\\s+authors\\s+thank"]),
    ("DEC-03", "author_contribution", ["author\\s+contributions?", "CRediT", "作者贡献"]),
    ("DEC-04", "coi", ["conflict\\s+of\\s+interest", "competing\\s+interests?", "declaration\\s+of\\s+interest", "利益冲突"]),
    ("DEC-05", "data_availability", ["data\\s+availability", "data\\s+are\\s+available", "available\\s+(?:from|on\\s+request)", "数据可用"]),
    ("DEC-06", "ethics_approval", ["ethic(?:s|al)?\\s+(?:approval|committee)", "\\bIRB\\b", "伦理(?:批件|委员会|审批)"]),
    ("DEC-07", "informed_consent", ["informed\\s+consent", "知情同意"]),
    ("DEC-08", "code_availability", ["code\\s+(?:is\\s+)?available", "code\\s+availability", "github\\.com", "代码可用"]),
    ("DEC-09", "copyright_license", ["copyright", "licen[cs]e", "版权", "许可协议"]),
]

DECL_CN = {"funding": "基金声明", "acknowledgment": "致谢", "author_contribution": "作者贡献",
           "coi": "利益冲突声明", "data_availability": "数据可用性", "ethics_approval": "伦理批件",
           "informed_consent": "知情同意", "code_availability": "代码可用性", "copyright_license": "版权许可"}

# ---------------------------------------------------------------- text utilities
WS = re.compile(r"\s+")
TR = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-", "\u2212": "-",
      "\u00a0": " ", "\u200b": "", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl", "\u3000": " "}
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
CN_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID18 = re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])")
INTL_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4}(?!\d)")


def norm(s, squash=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if squash else " ", s).strip()


def find_quote(text, quote):
    """Verbatim check: whitespace-normalised, then whitespace-stripped fallback."""
    q = norm(quote)
    if len(q) < 3 or not text:
        return {"found": False, "mode": "short"}
    if q in norm(text):
        return {"found": True, "mode": "exact"}
    q2 = norm(quote, True)
    if q2 and q2 in norm(text, True):
        return {"found": True, "mode": "loose"}
    return {"found": False, "mode": "miss"}


def mask_pii(s):
    s = str(s if s is not None else "")
    s = EMAIL.sub("[REDACTED-EMAIL]", s)
    s = CN_PHONE.sub("[REDACTED-PHONE]", s)
    s = ID18.sub("[REDACTED-ID]", s)
    s = INTL_PHONE.sub("[REDACTED-PHONE]", s)
    return s


def has_raw_pii(s):
    s = str(s if s is not None else "")
    return bool(EMAIL.search(s) or CN_PHONE.search(s) or ID18.search(s))


# ---------------------------------------------------------------- validation
def _err(rep, code, where, detail):
    rep["errors"].append({"code": code, "where": where, "detail": detail})


def _warn(rep, code, where, detail):
    rep["warnings"].append({"code": code, "where": where, "detail": detail})


def rows_of(draft):
    for k in ("compliance_matrix", "matrix", "rows", "requirements"):
        v = draft.get(k)
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
    return []


def validate(draft, index):
    rep = {"ok": True, "errors": [], "warnings": [], "counts": {}}
    texts = index.get("texts") or {}
    paras = index.get("paras") or {}
    sig = index.get("signals") or {}
    rows = rows_of(draft)
    if not rows:
        _err(rep, "matrix_empty", "compliance_matrix", "no compliance_matrix rows")
        rep["ok"] = False
        rep["counts"] = {"rows": 0, "judged": 0, "coverage": 0.0}
        return rep
    guide = bool(sig.get("guideline_present"))
    ids, n = set(), {"violation": 0, "unverifiable": 0, "compliant": 0, "not_applicable": 0,
                     "judged": 0, "quote_ok": 0, "quote_bad": 0, "need_ev": 0}
    for i, r in enumerate(rows):
        rid = str(r.get("row_id") or "row[%d]" % i)
        if r.get("row_id") in ids:
            _err(rep, "row_id_duplicate", rid, "row_id repeated")
        ids.add(r.get("row_id"))
        dom = norm(r.get("domain")).lower()
        if dom not in DOMAINS:
            _err(rep, "domain_invalid", rid, "domain=%r not in %s" % (r.get("domain"), DOMAINS))
        src = norm(r.get("rule_source")).lower()
        if src not in SRCS:
            _err(rep, "rule_source_invalid", rid, "rule_source=%r not in %s" % (r.get("rule_source"), SRCS))
        vd = norm(r.get("verdict")).lower()
        if vd not in VERDICTS:
            _err(rep, "verdict_invalid", rid, "verdict=%r not in %s (unjudged row?)" % (r.get("verdict"), VERDICTS))
            continue
        n["judged"] += 1
        n[vd] += 1
        sev = norm(r.get("severity")).lower()
        if sev and sev not in SEVS:
            _err(rep, "severity_invalid", rid, "severity=%r not in %s" % (r.get("severity"), SEVS))
        if vd in ("violation", "unverifiable") and not sev:
            _err(rep, "severity_missing", rid, "verdict=%s needs a severity" % vd)
        if sev in ("critical", "major", "minor") and not norm(r.get("severity_reason")):
            _err(rep, "severity_reason_missing", rid, "severity=%s needs severity_reason" % sev)
        if vd == "violation" and src == "general_practice" and sev == "critical":
            _err(rep, "severity_overstated", rid,
                 "general_practice rows may not be rated critical: cite a sourced norm or lower the tier")
        elif vd == "violation" and src == "general_practice" and sev == "major" and \
                len(norm(r.get("severity_reason"))) < 20:
            _warn(rep, "severity_practice_high", rid,
                  "major on general_practice needs a severity_reason explaining why it is a must-fix")
        if src == "venue_guideline" and vd != "unverifiable" and not guide:
            _err(rep, "guideline_basis_unavailable", rid,
                 "claims a venue guideline but no author-guideline text exists in /input")
        if vd == "unverifiable" and len(norm(r.get("what_human_must_check"))) < 6:
            _err(rep, "unverifiable_no_human", rid, "unverifiable requires what_human_must_check")
        if vd == "not_applicable" and len(norm(r.get("searched_scope"))) < 4:
            _err(rep, "not_applicable_no_scope", rid, "not_applicable requires searched_scope")
        if vd == "violation" and not norm(r.get("remediation")):
            _err(rep, "evidence_missing", rid, "violation row needs remediation")
        q, loc = norm(r.get("quote")), norm(r.get("evidence_locator"))
        if vd == "violation" or (vd == "compliant" and q):
            n["need_ev"] += 1
        did = norm(r.get("doc_id"))
        if q:
            if did in texts:
                found = find_quote(texts[did], q)["found"]
            else:
                found = any(find_quote(t, q)["found"] for t in texts.values())
                if found:
                    _warn(rep, "doc_id_missing", rid, "quote matched but doc_id is empty/unknown")
            if not found:
                n["quote_bad"] += 1
                _err(rep, "quote_not_found", rid, "quote absent from material: %r" % q[:90])
            else:
                n["quote_ok"] += 1
                if loc and did in paras:
                    hit = [p for p in paras[did] if p["locator"] == loc]
                    if hit and not find_quote(hit[0]["text"], q)["found"]:
                        _err(rep, "locator_quote_mismatch", rid,
                             "locator %s does not contain the quoted sentence" % loc)
                    elif not hit:
                        _warn(rep, "locator_unknown", rid, "locator %r not in index" % loc)
        elif vd == "violation":
            _err(rep, "evidence_missing", rid, "violation row needs a verbatim quote")
        if vd == "violation" and not loc:
            _err(rep, "evidence_missing", rid, "violation row needs evidence_locator")
        if vd == "compliant" and not (loc or q):
            _warn(rep, "compliant_without_evidence", rid, "compliant without locator/quote")
        blob = " ".join(norm(r.get(k)) for k in
                        ("requirement", "observed", "severity_reason", "remediation", "basis"))
        for tok in set(re.findall(r"\b(?:[A-Z]{2,6}[-\s]?\d{3,}[-\d]*|No\.\s*[A-Za-z0-9\-]{4,})\b", blob)):
            if not any(norm(tok) in norm(t) for t in texts.values()):
                _err(rep, "invented_identifier", rid,
                     "identifier %r appears in no material: do not invent approval/grant numbers" % tok)
                break
    have = {norm(r.get("row_id")) for r in rows}
    missing_dec = [d[0] for d in DECL if d[0] not in have]
    if missing_dec:
        _err(rep, "declaration_row_missing", "compliance_matrix", "missing rows: %s" % ", ".join(missing_dec))
    covered = {norm(r.get("domain")).lower() for r in rows}
    gap = [d for d in DOMAINS if d not in covered]
    if gap:
        _err(rep, "domain_uncovered", "compliance_matrix", "no rows for: %s" % ", ".join(gap))
    cites = [c for c in (draft.get("citation_reconciliation") or []) if isinstance(c, dict)]
    if not cites:
        _err(rep, "citation_reconciliation_missing", "citation_reconciliation", "empty reconciliation table")
    for j, c in enumerate(cites):
        w = "citation[%d]" % j
        mt = norm(c.get("match")).lower()
        if mt not in ("consistent", "dangling", "duplicate", "mismatch", "unverifiable", "no_reference_list"):
            _err(rep, "citation_match_invalid", w, "match=%r" % c.get("match"))
        if mt in ("dangling", "duplicate", "mismatch", "unverifiable") and len(norm(c.get("note"))) < 4:
            _err(rep, "citation_note_missing", w, "non-consistent entry needs a note")
        strip_mk = lambda s: re.sub(r"^\s*(?:\[\d{1,3}\]|\d{1,3}[\.\)])\s*", "", s)
        raw = strip_mk(norm(c.get("ref_entry")))
        pool = " ".join(strip_mk(norm(e.get("raw"))) for e in sig.get("citations", {}).get("entries") or [])
        if raw and pool and raw[:60] not in pool:
            _warn(rep, "ref_entry_not_in_bibliography", w,
                  "ref_entry not found in the parsed bibliography (check verbatim quoting)")
    ledger = [p for p in (draft.get("pii_ledger") or []) if isinstance(p, dict)]
    for j, p in enumerate(ledger):
        w = "pii[%d]" % j
        if not norm(p.get("location")):
            _err(rep, "pii_location_missing", w, "ledger entry needs a locator")
        if has_raw_pii(json.dumps(p, ensure_ascii=False)):
            _err(rep, "pii_not_redacted", w, "ledger contains raw PII: use [REDACTED-*] placeholders")
    for j, r in enumerate(rows):
        if has_raw_pii(str(r.get("quote") or "")) and norm(r.get("domain")) != "privacy":
            _warn(rep, "pii_in_quote", str(r.get("row_id") or j),
                  "quote carries PII outside a privacy row: keep the locator, mask it in the report")
    rep["counts"] = {"rows": len(rows), "judged": n["judged"], "violation": n["violation"],
                     "unverifiable": n["unverifiable"], "compliant": n["compliant"],
                     "not_applicable": n["not_applicable"],
                     "domains_covered": len([d for d in DOMAINS if d in covered]),
                     "quote_pass_rate": round(n["quote_ok"] / max(n["quote_ok"] + n["quote_bad"], 1), 3),
                     "evidence_coverage": round(n["quote_ok"] / max(n["need_ev"], 1), 3),
                     "citation_items": len(cites), "pii_items": len(ledger),
                     "coverage": round(n["judged"] / len(rows), 3),
                     "guideline_present": guide}
    rep["ok"] = not rep["errors"]
    return rep


# ---------------------------------------------------------------- rendering
def _cell(x):
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def _join(items, sep="；"):
    """Envelope lists may hold strings or dicts (uncovered requirements): never crash on join."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            vals = [str(v) for k, v in it.items() if isinstance(v, str) and v.strip()]
            out.append("：".join(vals) if vals else json.dumps(it, ensure_ascii=False)[:200])
        elif isinstance(it, (list, tuple)):
            out.append(_join(it, ", "))
        elif it not in (None, ""):
            out.append(str(it))
    return sep.join(out)


def table_md(head, rows):
    out = ["| " + " | ".join(_cell(h) for h in head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


CSV_COLS = ["row_id", "domain", "rule_source", "requirement", "expected", "observed", "verdict",
            "doc_id", "evidence_locator", "quote", "searched_scope", "severity", "severity_reason",
            "remediation", "what_human_must_check"]


def matrix_csv_rows(rows):
    return [CSV_COLS] + [[r.get(c, "") for c in CSV_COLS] for r in rows]


def render_report(M):
    rows = M["matrix"]
    L = ["# 学术规范与合规审查报告", "",
         "> case `%s` ｜ status **%s** ｜ 规则版本 `%s` ｜ 生成 %s（仅日期，逐次时间戳见 run_manifest.json）" % (
             M["case_id"], M["status"], M.get("rule_version", VERSION), M.get("generated", "")),
         "> 主产物是合规矩阵；下面的违规清单是从矩阵派生的视图，每条都能回查到 matrix_row_id。", ""]
    L += ["## 0. 输入与范围", ""]
    dm = M.get("doc_meta") or {}
    if dm:
        L += ["- 文档类型：%s ｜ 目标期刊/会议：%s ｜ 材料是否含作者指南：%s" % (
            dm.get("doc_type") or "未说明", dm.get("venue_name") or "未说明",
            "是" if dm.get("guideline_present") else "否（venue 类要求只能标待复核）"), ""]
    if M.get("sources"):
        L += [table_md(["doc", "文件", "类型", "抽取器", "段数", "文本质量"],
                       [[s.get("doc_id"), s.get("file"), s.get("kind"), s.get("engine"),
                         s.get("n_paras"), s.get("quality")] for s in M["sources"]]), ""]
    L += ["审查范围：学术诚信、引用规范、隐私与数据合规、版权与许可、伦理审查、投稿要求六个方向 + 9 项声明区块。",
          "不覆盖：论文润色、代写代投、数据重新分析、正式法务或伦理委员会意见、文献存在性的联网核实。", ""]
    L += ["## 1. 合规矩阵（唯一事实源）", ""]
    for d in DOMAINS:
        sub = [r for r in rows if norm(r.get("domain")).lower() == d]
        if not sub:
            continue
        L += ["### 1.%d %s（%d 行）" % (DOMAINS.index(d) + 1, d, len(sub)), ""]
        L += [table_md(["row", "要求", "判定", "严重度", "位置", "依据类型"],
                       [[r.get("row_id"), r.get("requirement"), r.get("verdict") or "未判定",
                         r.get("severity") or "-", r.get("evidence_locator") or "-",
                         r.get("rule_source")] for r in sub]), ""]
    L += ["## 2. 违规清单（由矩阵 violation 行派生）", ""]
    viol = [f for f in M["findings"] if f.get("issue_type") == "violation"]
    if not viol:
        L += ["未发现可定位、可举证的违规项。注意：这不等于材料合规，待复核项见第 3 节。", ""]
    for f in viol:
        L += ["### %s ｜ %s ｜ %s ｜ %s" % (f["finding_id"], f["severity"], f["facet"], f.get("title", "")), "",
              "- 矩阵行：`%s`（依据类型 `%s`）" % (f["matrix_row_id"], f.get("basis_source")),
              "- 位置：`%s` ｜ 所在文档：%s" % (f.get("location") or "未提供", f.get("doc_id") or "-"),
              "- 逐字证据：%s" % ("“%s”" % mask_pii(f.get("quote")) if f.get("quote")
                              else "无（不可作为违规项，应降级为待复核）"),
              "- 期望 / 实际：%s ／ %s" % (f.get("expected") or "-", f.get("observed") or "-"),
              "- 为什么算问题：%s" % (f.get("rationale") or f.get("severity_reason") or "-"),
              "- 严重度理由：%s" % (f.get("severity_reason") or "-"),
              "- 整改：%s" % (f.get("remediation") or "-"), ""]
    L += ["## 3. 待人工核实（矩阵 unverifiable 行）", ""]
    pend = [f for f in M["findings"] if f.get("issue_type") == "pending_review"]
    pend_ids = {f["matrix_row_id"] for f in pend}
    other = [r for r in rows if norm(r.get("verdict")).lower() == "unverifiable"
             and r.get("row_id") not in pend_ids]
    if not pend and not other:
        L += ["无。", ""]
    for f in pend:
        L += ["- **%s** ｜ %s ｜ 需核对：%s（位置 `%s`）" % (
            f["matrix_row_id"], f.get("title"), f.get("what_human_must_check") or "-",
            f.get("location") or "-")]
    for r in other:
        L += ["- **%s** ｜ %s ｜ 需核对：%s" % (r.get("row_id"), r.get("requirement"),
                                         r.get("what_human_must_check") or "-")]
    if pend or other:
        L += ["", "> 待复核项既不计入违规，也不计入合规：它们只表示「用现有材料无法判定」，请按上面的核对路径人工确认。", ""]
    L += ["## 4. 整改建议（按优先级）", ""]
    for p, sev in (("P0", "critical"), ("P1", "major"), ("P2", "minor"), ("P3", "suggestion")):
        items = [f for f in viol if f.get("severity") == sev]
        if not items:
            continue
        L += ["### %s（%s，%d 条）" % (p, sev, len(items)), ""]
        L += ["%d. **%s** — %s" % (i + 1, it.get("title", ""), it.get("remediation") or "-")
              for i, it in enumerate(items)]
        L += [""]
    c = M.get("coverage") or {}
    L += ["## 5. 覆盖、缺口与诚实性", "",
          "- 矩阵 %s 行，已判定 %s 行（coverage %s）；violation %s、compliant %s、not_applicable %s、unverifiable %s" % (
              c.get("rows"), c.get("judged"), c.get("coverage"), c.get("violation"),
              c.get("compliant"), c.get("not_applicable"), c.get("unverifiable")),
          "- 引文逐字命中率 %s；证据覆盖率 %s" % (c.get("quote_pass_rate"), c.get("evidence_coverage")),
          "- 覆盖方向 %s/7；引用对账 %s 条；PII 台账 %s 条" % (
              c.get("domains_covered"), c.get("citation_items"), c.get("pii_items"))]
    if M.get("degradations"):
        L += ["- 降级与限制：" + _join(M["degradations"])]
    if M.get("uncertainty"):
        L += ["- 不确定性：" + _join(M["uncertainty"])]
    if M.get("pending_human"):
        L += ["- 待人工处理：" + _join(M["pending_human"])]
    L += ["", "## 6. 复跑与版本", "",
          "```bash",
          "python3 scripts/main.py init && python3 scripts/main.py show",
          "# 读材料 → 写 /app/work/draft.json",
          "python3 scripts/main.py check && python3 scripts/main.py build",
          "```", "",
          "- 规则版本 `%s`；同一输入两次运行除时间戳外结论一致（矩阵按 (domain, row_id) 稳定排序）。" % M.get(
              "rule_version", VERSION),
          "- 复核方式：按 `evidence_locator` 回到原文逐字比对 `quote`；依据缺失的行请走第 3 节的核对路径。", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- output_contract back-fill
PATTERNS = [
    (r"finding|issue|problem|defect|violation|problem_list", "findings"),
    (r"matrix|requirement|checklist|compliance_|audit|row", "compliance_matrix"),
    (r"pii|privacy|redact|personal", "pii_ledger"),
    (r"citation|reference|bibliograph|文献", "citation_reconciliation"),
    (r"pending|human|manual|need_check", "pending_human"),
    (r"coverage|stat|count|metric", "coverage"),
    (r"basis|rule|policy|legit|依据", "basis_index"),
    (r"summary|report|narrative|markdown|conclusion|abstract", "summary"),
    (r"artifact|output|deliverable|file|path", "artifacts"),
    (r"source|provenance|input", "sources"),
    (r"severity|risk|priority", "severity_summary"),
    (r"degrad|limitation|gap", "degradations"),
    (r"remediation|action|suggest|fix", "remediation_plan"),
    (r"uncertain|unknown|open", "uncertainty"),
    (r"method|approach|how", "method"),
    (r"status|state", "status"),
    (r"case", "case_id"),
]

DEFAULT_CONTRACT = {k: [] for k in ("compliance_matrix", "findings", "pii_ledger", "citation_reconciliation",
                                    "remediation_plan", "uncovered_requirements", "sources", "uncertainty")}
DEFAULT_CONTRACT.update({"summary": None, "coverage": {}, "case_id": None})


def contract_keys(contract):
    if isinstance(contract, dict):
        return [str(k) for k in contract]
    if isinstance(contract, list):
        return [f if isinstance(f, str) else str(f.get("name") or f.get("key") or f.get("field")
                                                 or "field_%d" % (i + 1))
                for i, f in enumerate(contract) if isinstance(f, (str, dict))]
    return []


def empty_like(spec):
    if isinstance(spec, dict):
        return {}
    if isinstance(spec, list):
        return []
    s = str(spec or "").lower()
    if "array" in s or "list" in s or s.startswith("["):
        return []
    if "object" in s or "dict" in s or s.startswith("{"):
        return {}
    return None


def _match_bag(key, bag):
    kl = str(key).lower()
    for pat, bagkey in PATTERNS:
        if re.search(pat, kl):
            v = bag.get(bagkey)
            if v not in (None, "", [], {}):
                return v
    return None


def fill_contract(contract, bag, missing=None, depth=0):
    """Back-fill every output_contract key verbatim (nested dict specs included)."""
    missing = [] if missing is None else missing
    if isinstance(contract, dict):
        out = {}
        for k, spec in contract.items():
            v = bag.get(k)
            if v in (None, "", [], {}):
                v = _match_bag(k, bag)
            if v in (None, "", [], {}):
                if isinstance(spec, dict) and depth < 3:
                    v = fill_contract(spec, bag, missing, depth + 1)
                else:
                    v = empty_like(spec)
            empty_ok = isinstance(spec, list) or (isinstance(spec, str) and
                                                 any(t in spec.lower() for t in ("array", "list")))
            if v in (None, "", [], {}) and not (empty_ok and v == []):
                missing.append(str(k))
            out[k] = v
        return out
    if isinstance(contract, list):
        return bag.get("items") or []
    return bag.get("summary")


def backfill(contract, bag):
    """Top-level contract back-fill: returns (filled, missing_keys)."""
    missing = []
    return fill_contract(contract, bag, missing), missing


def sha256_of(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
    except Exception:
        return "unreadable"
