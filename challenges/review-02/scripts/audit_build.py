"""audit_build.py - candidate scan, draft processing, contract fill, assembly, selfcheck.

The judgement always comes from /app/work/draft.json. This module checks and
normalises it; it never invents it. Fallback rows are marked pending_review.
"""

from __future__ import annotations

import json, re, time
from itertools import combinations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import audit_core as A

RULES_VERSION = "rules/1"
SEM = ("direction_match", "numeric_match", "scope_match")
FACETS = ("citation", "fact", "statistics", "logic", "method", "compliance")
SUBS = ("support_verdict", "source_reliability", "evidence_locator",
        "numeric_consistency", "argument_chain")
ISSUE_TYPES = ("citation_unsupported", "citation_partially_supported", "overclaim",
               "fact_mismatch", "source_unreliable", "numeric_inconsistency",
               "logic_gap", "compliance", "improvement")
SEVERITIES = ("critical", "major", "minor", "suggestion")
VERDICTS = ("full_support", "partial_support", "no_support", "undetermined")
VERDICT_TYPES = ("fact_error", "insufficient_evidence", "compliance_issue", "suggestion")
# Schema/placeholder keywords: a verbatim quote carrying them would turn a delivered artifact into a shell.
SHELL_TOKENS = re.compile(r"\bnull\b|\bNone\b|\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b|\bplaceholder\b|"
                          r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|\bN/?A\b|待写|待补充|待填写|"
                          r"尚未|example\.com|lorem ipsum|<[A-Za-z_][\w /-]*>", re.I)
BLOCKING = {"contract_missing", "unreadable_material", "no_reference_list", "units_truncated",
            "draft_unavailable", "draft_invalid", "draft_incomplete", "quote_unverified",
            "no_input_files"}
FACET_ALIAS = {"citation": "citation", "citations": "citation", "reference": "citation",
               "引用": "citation", "引文": "citation", "cite": "citation", "fact": "fact",
               "facts": "fact", "factual": "fact", "事实": "fact", "statistics": "statistics",
               "statistic": "statistics", "stats": "statistics", "stat": "statistics",
               "numeric": "statistics", "numbers": "statistics", "统计": "statistics",
               "logic": "logic", "logical": "logic", "reasoning": "logic", "argument": "logic",
               "逻辑": "logic", "论证": "logic", "method": "method", "methods": "method",
               "methodology": "method", "design": "method", "方法": "method",
               "compliance": "compliance", "ethics": "compliance", "norm": "compliance",
               "norms": "compliance", "规范": "compliance", "学术规范": "compliance"}
ALIASES = {
    "findings": ("findings", "finding", "issues", "issuelist", "problems", "problemlist",
                 "auditfindings", "reviewfindings", "defects", "问题", "问题清单"),
    "citation_checks": ("citationchecks", "citationcheck", "citationmatrix", "citationsupport",
                        "citations", "citationaudit", "referencechecks", "claimchecks",
                        "claims", "引文核验", "核验矩阵"),
    "coverage": ("coverage", "facetcoverage", "checklist", "checks", "checkitems", "检查项", "覆盖"),
    "summary": ("summary", "overview", "executivesummary", "conclusion", "conclusions",
                "abstractreview", "overall", "综述", "结论"),
    "report": ("report", "reviewreport", "auditreport", "markdown", "reportmd", "narrative"),
    "uncertainties": ("uncertainties", "uncertainty", "unresolved", "pending", "pendingreview",
                      "limitations", "openquestions", "待复核"),
    "sources": ("sources", "source", "evidence", "evidencelist", "materials", "referencesused"),
    "numeric_checks": ("numericchecks", "numbers", "numeric", "statisticschecks", "valuechecks"),
    "compliance_checks": ("compliance", "compliancechecks", "norms", "ethics", "standards"),
    "claims": ("claims", "claimlist", "claimsreviewed"),
    "metrics": ("metrics", "counts", "statistics", "stats"),
    "status": ("status", "resultstatus", "runstatus"),
    "case_id": ("caseid", "case", "id", "taskid"),
    "artifacts": ("artifacts", "files", "outputs", "deliverables"),
    "severity_summary": ("severitysummary", "severitycounts", "severitydistribution"),
    "revisions": ("revisions", "suggestions", "recommendations", "fixes", "修改建议"),
    "method_notes": ("methodnotes", "methodology", "methoddetails", "rulesversion"),
    "unchecked_items": ("uncheckeditems", "unchecked", "skipped", "未检查"),
    "result": ("result", "results", "outcome", "main"),
}
ALIAS_LOOKUP = {a: canon for canon, names in ALIASES.items() for a in names}
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*(?:\s?(?:%|‰|mg|kg|μg|ng|ml|μl|mm|cm|nm|μm|µm|°c|℃|kpa|mpa|"
                    r"gpa|hz|khz|ghz|ev|mol|mmol|min|hours?|days?|weeks?|months?|years?|倍|例|名|份))?", re.I)
BUCKETS = (
    ("sample_size", re.compile(r"\bn\s*=\s*(\d{1,6})|(\d{1,6})\s*(?:名|例|位|人|只|株|份|受试者|患者|参与者|样本|"
                               r"subjects?|participants?|patients?|samples?|specimens?|mice|rats|animals?)", re.I)),
    ("p_value", re.compile(r"\bp\s*([=<>≤≥])\s*(0?\.\d+(?:e-?\d+)?)", re.I)),
    ("percent", re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")),
    ("ci", re.compile(r"95%\s*(?:CI|置信区间)[^0-9]{0,8}([\d.]+)\s*[-–,~]+\s*([\d.]+)", re.I)))


def norm_key(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(s or "").lower())


def canon_of(key):
    k = norm_key(key)
    return ALIAS_LOOKUP.get(k) or next((c for c in ALIASES if k and len(k) > 4 and k.startswith(c)), None)


def facet_of(v):
    k = norm_key(v)
    if k in FACET_ALIAS:
        return FACET_ALIAS[k]
    for probe, canon in (("cit", "citation"), ("fact", "fact"), ("stat", "statistics"),
                         ("num", "statistics"), ("log", "logic"), ("meth", "method"),
                         ("comp", "compliance"), ("norm", "compliance")):
        if probe in k:
            return canon
    return None


SUBKEY = {norm_key(x): x for x in SUBS}


def covkey(k):
    nk = norm_key(k)
    return SUBKEY.get(nk) or facet_of(k) or nk


def _count(vals):
    out = {}
    for v in vals:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


# ------------------------------------------------------------------ corpus
class Corpus:
    def __init__(self, idx):
        self.units = idx.get("units") or []
        self.unit_flat, self.loc = {}, {}
        for u in self.units:
            self.unit_flat[u["uid"]] = A.flatmatch(u.get("text"))
            self.loc[u["uid"]] = u.get("locator")
        self.src_join = {}
        for u in self.units:
            self.src_join.setdefault(u.get("source_id"), []).append(A.flatmatch(u.get("text")))
        self.src_join = {k: "\n".join(v) for k, v in self.src_join.items()}
        self.all = "\n".join(self.unit_flat.values())

    def find(self, quote, min_len=10):
        q = A.flatmatch(quote)
        if len(q) < min_len:
            return {"ok": False, "reason": "quote_too_short", "uid": None, "locator": None}
        for uid, f in self.unit_flat.items():
            if q in f:
                return {"ok": True, "reason": "unit_hit", "uid": uid, "locator": self.loc.get(uid)}
        for sid, f in self.src_join.items():
            if q in f:
                return {"ok": True, "reason": "source_hit", "uid": None, "source_id": sid, "locator": None}
        return {"ok": True, "reason": "corpus_hit", "uid": None, "locator": None} if q in self.all else \
               {"ok": False, "reason": "not_found", "uid": None, "locator": None}


# ------------------------------------------------------------------ candidates
def claim_candidates(units, limit=150):
    out = []
    for u in units:
        if u["section_key"] in ("references", "back") or len(u["text"]) < 20:
            continue
        for sent in A.split_sentences(u["text"]):
            marks = [m.group(0) for m in A.NUM_MARK.finditer(sent)]
            marks += [m.group(0) for m in A.AUTH_MARK.finditer(sent)]
            marks += [m.group(0) for m in A.CITE_TEX.finditer(sent)]
            nums = NUM_RE.findall(re.sub(r"\[[^\]]{1,40}\]", " ", sent))
            causal, scope = A.cue("causal", sent), A.cue("scope", sent)
            claimish = re.search(r"有效|优于|降低|提高|增加|显著|导致|effective|demonstrat|reduc|"
                                 r"improv|increas|associat|remain", sent, re.I)
            if not marks and not (nums and (causal or A.cue("compar", sent))) \
                    and not (causal and scope) and not (scope and claimish):
                continue
            out.append({"cand_id": "CC-%02d" % (len(out) + 1), "uid": u["uid"],
                        "locator": u["locator"], "section": u["section"], "page": u["page"],
                        "text": A.squash(sent, 420), "markers": marks, "numbers": nums[:8],
                        "direction": A.direction(sent), "negation": A.cue("neg", sent),
                        "significance": A.cue("sig", sent), "scope_cue": scope,
                        "causal_cue": causal, "comparator": A.cue("compar", sent),
                        "claim_strength": "hedged" if A.cue("hedge", sent) else
                        ("strong" if scope or re.search(r"证明|证实|demonstrat|confirm|因此|从而", sent)
                         else "moderate"),
                        "why": [k for k, v in (("has_marker", marks), ("has_number", nums),
                                               ("causal_cue", causal), ("scope_cue", scope)) if v]})
            if len(out) >= limit:
                return out
    return out


def numeric_candidates(units, limit=40):
    occ = []
    for u in units:
        if u["section_key"] == "references":
            continue
        for sent in A.split_sentences(u["text"]):
            for bucket, rx in BUCKETS:
                for m in rx.finditer(A.nfkc(sent)):
                    val = next((g for g in m.groups() if g), None)
                    if val:
                        occ.append({"bucket": bucket, "value": val, "sec": u["section_key"],
                                    "locator": u["locator"], "sentence": A.squash(sent, 300)})
    cands, seen = [], set()
    for a, b in combinations(occ, 2):
        if a["bucket"] != b["bucket"] or a["value"] == b["value"]:
            continue
        if a["sec"] != "abstract" and b["sec"] != "abstract":
            continue
        ov = A.terms(a["sentence"]) & A.terms(b["sentence"])
        key = tuple(sorted([a["locator"] + a["value"], b["locator"] + b["value"]]))
        if len(ov) < 2 or key in seen:
            continue
        seen.add(key)
        cands.append({"num_id": "NC-%02d" % (len(cands) + 1), "bucket": a["bucket"],
                      "left": {k: a[k] for k in ("value", "locator", "sentence", "sec")},
                      "right": {k: b[k] for k in ("value", "locator", "sentence", "sec")},
                      "shared_terms": sorted(ov)[:6],
                      "note": "abstract/body value differs for the same bucket"})
        if len(cands) >= limit:
            break
    return cands


def numeric_index(units):
    idx = {}
    for u in units:
        if u["section_key"] == "references":
            continue
        for sent in A.split_sentences(u["text"]):
            for bucket, rx in BUCKETS:
                for m in rx.finditer(A.nfkc(sent)):
                    val = next((g for g in m.groups() if g), None)
                    if val:
                        idx.setdefault("%s:%s" % (bucket, val), []).append(u["locator"])
    return idx


def attach_candidates(idx):
    units = idx.get("units") or []
    idx["claim_candidates"] = claim_candidates(units)
    idx["numeric_candidates"] = numeric_candidates(units)
    idx["numeric_index"] = numeric_index(units)
    gaps = idx.setdefault("gaps", [])
    codes = {g.get("code") for g in gaps}
    if idx["numeric_candidates"] and "numeric_conflict_candidates" not in codes:
        gaps.append({"code": "numeric_conflict_candidates", "count": len(idx["numeric_candidates"]),
                     "detail": "摘要/正文同桶数值不一致候选，需人工确认是否为分组差异"})
    if not idx["claim_candidates"] and "no_claim_candidates" not in codes:
        gaps.append({"code": "no_claim_candidates",
                     "detail": "未筛出含引文标记/数值/因果线索的句子；请通读 units 指定审查对象"})
    st = idx.setdefault("stats", {})
    st["claim_candidates"] = len(idx["claim_candidates"])
    st["numeric_candidates"] = len(idx["numeric_candidates"])
    return idx


def draft_template(idx):
    rows = [{"claim_id": c["cand_id"], "claim_text": c["text"], "claim_quote": c["text"],
             "claim_locator": c["locator"], "claim_strength": c["claim_strength"],
             "cited_source": {"label": ", ".join(c["markers"]) or None,
                              "source_locator_if_available": None},
             "source_claim_if_available": None, "verdict": "undetermined",
             "semantics": {SEM[0]: None, SEM[1]: None, SEM[2]: None,
                           "comparator": c["comparator"], "negation": c["negation"],
                           "significance": c["significance"]},
             "source_quote": None, "rationale": None,
             "unresolved_reason": "TODO: 读原文后填；无法核实写清缺什么",
             "human_check_needed": "TODO: 人工下一步核对什么"}
            for c in (idx.get("claim_candidates") or [])[:40]]
    return {"_howto": ("逐行读 claim_locator 指向的原文，把 claim_quote 改成逐字命中片段，填 "
                       "verdict/semantics/rationale；undetermined 必填 unresolved_reason 与 "
                       "human_check_needed。再写 findings/coverage/summary/uncertainties。"
                       "完成后跑 python3 scripts/main.py check。"),
            "case_id": idx.get("case_id"), "summary": "", "citation_checks": rows,
            "findings": [], "coverage": {}, "unchecked_items": [], "uncertainties": []}


# ------------------------------------------------------------------ draft processing
def process_draft(draft, idx, corpus):
    """Validate and normalise the draft in one pass."""
    rep = {"ok": False, "errors": [], "warnings": [], "items": [], "stats": {}}
    cks, fnds, changes = [], [], []
    if not isinstance(draft, dict):
        rep["errors"].append("draft.json 不是 JSON 对象")
        return rep, cks, fnds, {}, changes
    E, W, IT = rep["errors"], rep["warnings"], rep["items"]

    def chk(scope, name, ok, detail=""):
        ok = bool(ok)
        IT.append({"scope": scope, "check": name, "ok": ok, "detail": detail})
        if not ok:
            (E if scope in ("draft", "finding", "coverage", "case_id") else W).append(
                "%s/%s: %s" % (scope, name, detail))

    if idx.get("case_id"):
        chk("case_id", "matches case.json", str(draft.get("case_id") or "") == str(idx["case_id"]),
            "draft=%r input=%r" % (draft.get("case_id"), idx["case_id"]))
    raw_cks = draft.get("citation_checks") if isinstance(draft.get("citation_checks"), list) else []
    raw_fnds = draft.get("findings") if isinstance(draft.get("findings"), list) else []
    if not raw_cks:
        E.append("citation_checks 缺失或为空：至少需要一条被引论断的核验行")
    if not raw_fnds:
        W.append("findings 为空：没有任何问题条目")
    for i, row in enumerate(raw_cks):
        if not isinstance(row, dict):
            E.append("citation_checks[%d] 不是对象" % i)
            continue
        tag = str(row.get("claim_id") or "row#%d" % (i + 1))
        q = row.get("claim_quote") or row.get("quote") or row.get("claim_text")
        hit = corpus.find(q) if q else {"ok": False, "reason": "missing"}
        chk("draft", "%s quote" % tag, q and hit["ok"], hit.get("reason") or "缺少逐字原文")
        chk("draft", "%s locator" % tag, bool(row.get("claim_locator")), "缺少 locator")
        v = row.get("verdict") if row.get("verdict") in VERDICTS else "undetermined"
        chk("draft", "%s verdict" % tag, row.get("verdict") in VERDICTS, "非法取值 %r" % row.get("verdict"))
        sem_raw = row.get("semantics") if isinstance(row.get("semantics"), dict) else {}
        miss = [k for k in SEM if k not in sem_raw]
        chk("draft", "%s semantics" % tag, not miss, "缺少 %s" % ",".join(miss) if miss else "")
        if v == "undetermined":
            chk("draft", "%s undetermined_docs" % tag,
                row.get("unresolved_reason") and row.get("human_check_needed"),
                "undetermined 必须写 unresolved_reason 与 human_check_needed")
        if not str(row.get("rationale") or "").strip():
            W.append("%s: rationale 为空，判定不可复核" % tag)
        if v == "full_support" and any(sem_raw.get(k) is False for k in SEM):
            nv = "no_support" if sem_raw.get(SEM[0]) is False else "partial_support"
            changes.append({"scope": tag, "field": "verdict", "from": v, "to": nv,
                            "rule": "full_support 要求 direction/numeric/scope 三要素全为 true",
                            "basis": {k: sem_raw.get(k) for k in SEM}})
            v = nv
        status = "confirmed"
        if not hit["ok"]:
            status = "pending_review"
            changes.append({"scope": tag, "field": "status", "from": "confirmed",
                            "to": "pending_review", "rule": "quote 未在原文逐字命中",
                            "detail": hit.get("reason")})
        elif v == "undetermined":
            status = "pending_review"
        elif not str(row.get("rationale") or "").strip():
            status = "pending_review"
            changes.append({"scope": tag, "field": "status", "from": "confirmed",
                            "to": "pending_review", "rule": "缺 rationale，判定不可复核"})
        cs = row.get("cited_source") if isinstance(row.get("cited_source"), dict) else {
            "label": row.get("cited_source"), "source_locator_if_available": None}
        cks.append({"check_id": tag, "claim_id": tag,
                    "claim_text": A.squash(row.get("claim_text") or q, 420),
                    "claim_quote": A.squash(q, 420), "claim_strength": row.get("claim_strength"),
                    "cited_source": cs, "source_claim_if_available": row.get("source_claim_if_available"),
                    "verdict": v,
                    "semantics": {k: sem_raw.get(k) for k in SEM} |
                                 {k: sem_raw.get(k) for k in ("comparator", "negation", "significance")},
                    "locators": {"claim_loc": row.get("claim_locator"),
                                 "source_loc": cs.get("source_locator_if_available")
                                 or row.get("source_locator")},
                    "rationale": A.squash(row.get("rationale"), 900),
                    "checked_evidence": [x for x in (row.get("claim_quote"), row.get("source_quote")) if x],
                    "quote_verified": bool(hit["ok"]),
                    "unresolved_reason": row.get("unresolved_reason"),
                    "human_check_needed": row.get("human_check_needed"), "status": status})
    for i, f in enumerate(raw_fnds):
        if not isinstance(f, dict):
            E.append("findings[%d] 不是对象" % i)
            continue
        tag = str(f.get("finding_id") or "F-%02d" % (i + 1))
        fa = facet_of(f.get("facet"))
        chk("finding", "%s facet" % tag, fa is not None, "非法 facet %r" % f.get("facet"))
        hit = corpus.find(f.get("quote")) if f.get("quote") else {"ok": False, "reason": "missing"}
        chk("finding", "%s quote" % tag, f.get("quote") and hit["ok"], hit.get("reason") or "缺少原文")
        chk("finding", "%s severity" % tag, f.get("severity") in SEVERITIES,
            "非法 severity %r" % f.get("severity"))
        chk("finding", "%s severity_reason" % tag, bool(f.get("severity_reason")), "缺少严重度理由")
        chk("finding", "%s issue_type" % tag, f.get("issue_type") in ISSUE_TYPES,
            "非法 issue_type %r" % f.get("issue_type"))
        loc = f.get("location")
        chk("finding", "%s location" % tag,
            (isinstance(loc, dict) and loc.get("locator")) or (isinstance(loc, str) and loc),
            "缺少 location.locator")
        chk("finding", "%s evidence" % tag, bool(f.get("evidence")), "缺少判定依据")
        chk("finding", "%s revision" % tag, len(str(f.get("revision") or "")) >= 6,
            "修改建议缺失或过短（需可执行）")
        if f.get("verdict_type") not in (None,) + VERDICT_TYPES:
            W.append("%s: verdict_type 非法 %r" % (tag, f.get("verdict_type")))
        vt = f.get("verdict_type") if f.get("verdict_type") in VERDICT_TYPES else \
            "compliance_issue" if fa == "compliance" else \
            "insufficient_evidence" if f.get("issue_type") in ("citation_partially_supported",
                                                               "citation_unsupported") else "fact_error"
        status = "confirmed"
        if not hit["ok"]:
            status = "pending_review"
            changes.append({"scope": tag, "field": "status", "from": "confirmed",
                            "to": "pending_review", "rule": "quote 未在原文逐字命中",
                            "detail": hit.get("reason")})
        fnds.append({"finding_id": tag, "facet": fa or "citation",
                     "location": _loc_of(loc),
                     "quote": A.squash(f.get("quote"), 420), "quote_verified": bool(hit["ok"]),
                     "issue_type": f.get("issue_type") if f.get("issue_type") in ISSUE_TYPES else "improvement",
                     "severity": f.get("severity") if f.get("severity") in SEVERITIES else "minor",
                     "severity_reason": A.squash(f.get("severity_reason"), 400),
                     "verdict_type": vt, "evidence": A.squash(f.get("evidence"), 700),
                     "rationale": A.squash(f.get("rationale"), 700),
                     "revision": A.squash(f.get("revision"), 500),
                     "claim_ref": f.get("claim_ref"), "status": status})
    coverage = _coverage(draft.get("coverage"), fnds, chk, W)
    rep["stats"] = {"citation_checks": len(cks), "findings": len(fnds),
                    "verdicts": _count([c["verdict"] for c in cks]),
                    "severities": _count([f["severity"] for f in fnds]),
                    "quote_failures": sum(1 for it in IT if not it["ok"] and it["check"].endswith("quote"))}
    rep["ok"] = not E
    return rep, cks, fnds, coverage, changes


def _loc_of(v):
    if isinstance(v, dict):
        return {"section": v.get("section"), "locator": v.get("locator") or v.get("loc"),
                "page": v.get("page"),
                "table_or_figure": v.get("table_or_figure") or v.get("table") or v.get("figure")}
    if isinstance(v, str):
        return {"section": None, "locator": v, "page": None, "table_or_figure": None}
    return {"section": None, "locator": None, "page": None, "table_or_figure": None}


def _coverage(cov, fnds, chk, W):
    out = {}
    if isinstance(cov, dict):
        for k, v in cov.items():
            ck = covkey(k)
            row = dict(v) if isinstance(v, dict) else ({"checked": v} if isinstance(v, bool)
                                                      else {"checked": True, "note": str(v)[:200]})
            row.setdefault("checked", True)
            row.setdefault("items", None)
            row.setdefault("findings", None)
            out[ck] = row
        missing = [f for f in FACETS if f not in out]
        chk("coverage", "six_facets", not missing, "缺少 %s" % ",".join(missing) if missing else "")
        lack = [x for x in SUBS if x not in out]
        if lack:
            W.append("coverage 缺专项子检查：%s" % ",".join(lack))
    else:
        chk("coverage", "present", False, "coverage 缺失或不是对象")
    for f in FACETS + SUBS:
        out.setdefault(f, {"checked": False, "items": 0, "findings": 0, "note": "未在工作稿 coverage 中声明"})
    for k, row in out.items():
        fa = facet_of(k)
        if row.get("findings") is None:
            row["findings"] = sum(1 for f in fnds if f["facet"] == fa) if fa else 0
    return out


# ------------------------------------------------------------------ selfcheck
def selfcheck(result, idx):
    checks = []

    def ck(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})

    ck("result_is_object", isinstance(result, dict))
    if not isinstance(result, dict):
        return {"ok": False, "checks": checks, "failed": ["result_is_object"]}
    missing = [k for k in (idx.get("contract_keys") or []) if k not in result]
    ck("contract_keys_present", not missing, "missing=%s" % missing)
    ck("case_id_matches", str(result.get("case_id")) == str(idx.get("case_id")),
       "%r vs %r" % (result.get("case_id"), idx.get("case_id")))
    ck("status_legal", result.get("status") in ("completed", "partial", "input_error"), result.get("status"))
    corpus = Corpus(idx)
    cks, fnds = result.get("citation_checks") or [], result.get("findings") or []
    ck("verdicts_legal", not [c for c in cks if c.get("verdict") not in VERDICTS])
    ck("severities_legal", not [f for f in fnds if f.get("severity") not in SEVERITIES])
    ck("facets_legal", not [f for f in fnds if f.get("facet") not in FACETS])
    ck("citation_quotes_verbatim", not [c for c in cks if not corpus.find(c.get("claim_quote"))["ok"]])
    ck("finding_quotes_verbatim", not [f for f in fnds if not corpus.find(f.get("quote"))["ok"]])
    und = [c for c in cks if c.get("verdict") == "undetermined"]
    ck("undetermined_documented",
       all(c.get("unresolved_reason") and c.get("human_check_needed") for c in und), "%d und" % len(und))
    conf = [f for f in fnds if f.get("status") == "confirmed"]
    ck("confirmed_have_evidence",
       all(f.get("quote_verified") and f.get("revision") and f.get("evidence") for f in conf),
       "%d confirmed" % len(conf))
    cov = result.get("coverage") or {}
    ck("coverage_six_facets", all(f in cov for f in FACETS), [f for f in FACETS if f not in cov])
    ck("no_fabricated_verdicts",
       not [c for c in cks if c.get("status") == "confirmed" and not c.get("quote_verified")])
    ck("envelope_fields",
       all(k in result for k in ("errors", "degradations", "changes", "runtime", "sources")))
    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "failed": [c["check"] for c in checks if not c["ok"]]}
