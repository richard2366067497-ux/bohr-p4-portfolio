#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patent-search-dossier / dossier.py

工作稿装载与兜底（fallback_draft / merge_draft）、R1–R13 机械校验（check）、
selfcheck 复检。渲染在 render.py。纯标准库、不联网、不依赖 CWD。
"""
import json
import re
from pathlib import Path

import registry as R

VERSION = R.VERSION
STATUS_VALUES = ("unknown", "granted", "pending", "expired", "abandoned", "withdrawn",
                 "rejected", "not_in_force", "revoked")
SOURCE_KINDS = ("official_register", "facsimile_ocr", "observed_link", "aggregator")
LINK_TYPES = ("observed", "shared_priority", "continuation", "divisional", "pct_national_phase")
BOUNDARY_TYPES = ("legal_status_unknown", "family_not_exhaustive", "ocr_merged_page",
                  "claim_scope_unexplained", "patent_vs_paper_scope", "license_restricted",
                  "metadata_missing", "coverage_gap")
DRAFT_KEYS = ("query", "number_decisions", "patent_objects", "field_extraction", "family_edges",
              "status_entries", "claims_versions", "technical_papers", "license_decisions",
              "boundaries", "conflicts", "gaps", "status_note")


def load_draft(work):
    work = Path(work)
    for name in ("draft.json", "plan.json"):
        p = work / name
        if p.is_file():
            obj, err = R.load_json(p)
            if isinstance(obj, dict):
                return obj, str(p), None
            return {}, str(p), "工作稿解析失败 %s: %s" % (name, err)
    return {}, None, "未找到工作稿（%s/draft.json）" % work


def _ev(source_id, locator, quote):
    return [{"source_id": source_id, "locator": locator, "quote": quote}] if (source_id and quote) else []


def _pid(objs, norm):
    for o in objs:
        if o.get("number_norm") == norm:
            return o.get("patent_id")
    return None


def _first_norm(text):
    for c in R.extract_candidates([{"loc": "p1", "text": text}]):
        return c["norm"]
    return None


def fallback_draft(idx):
    """无工作稿时：只用索引里的机械候选拼出完整最小档案，不推断任何法律状态。"""
    today = R.now()[:10]
    cands = R.al(idx.get("number_candidates"))[:12]
    objs, nds = [], []
    for i, c in enumerate(cands, 1):
        objs.append({"patent_id": "P%d" % i, "number_norm": c["norm"], "title": None, "assignee": None,
                     "filing_date": None, "priority_date": None, "ipc": [],
                     "screening": "include", "why": "索引在材料中定位到的专利号码（未经 Agent 复核）",
                     "evidence": _ev(c["source_id"], c["locator"], c["context"])})
        nds.append({"raw": c["raw"], "norm": c["norm"], "doc_type": c["doc_type"],
                    "parse_status": c["parse_status"], "decision": "unreviewed",
                    "note": "脚本解析，未经 Agent 确认"})
    by_norm = {c["norm"]: c for c in cands}
    edges, edge_seen = [], set()
    for f in R.al(idx.get("family_candidates")):
        nums = [n for n in f.get("numbers", []) if n in by_norm]
        for a in range(len(nums) - 1):
            key = (nums[a], nums[a + 1])
            if key in edge_seen:
                continue
            edge_seen.add(key)
            edges.append({"from": _pid(objs, nums[a]), "to": _pid(objs, nums[a + 1]),
                          "link_type": f.get("link_type_guess") or "observed",
                          "family_scope": "extended", "evidence_locator": f.get("locator"),
                          "quote": f.get("quote"), "claim_scope_note": "仅陈述材料可见链接，未做等同推定"})
    status = []
    for o in objs:
        src = (o.get("evidence") or [{}])[0]
        status.append({"patent_id": o["patent_id"], "value": "unknown", "as_of": today,
                       "source_kind": "observed_link", "source_id": src.get("source_id"),
                       "locator": src.get("locator"), "needs_official_verification": True,
                       "note": "材料未提供官方登记，状态未核实"})
    claims = []
    for m in idx.get("materials", []):
        if not (set((m.get("roles") or {})) & {"facsimile_ocr", "patent_record"}):
            continue
        for pa in m.get("paras", []):
            low = pa["text"].lower()
            if ("claim" in low or "权利要求" in low) and len(R.norm_ws(pa["text"])) > 40:
                claims.append({"patent_id": _pid(objs, _first_norm(pa["text"])) or "P1",
                               "version": "v1", "quote": R.norm_ws(pa["text"])[:300],
                               "locator": "%s/%s" % (m["id"], pa["loc"]),
                               "ocr_boundary": "material OCR quality=%s；摘录可能跨页或被截断" % m.get("ocr"),
                               "scope_explained": False})
                break
    papers = []
    for i, p in enumerate(R.al(idx.get("paper_candidates"))[:10], 1):
        papers.append({"paper_id": "T%d" % i, "title": None, "doi": p.get("doi"), "year": None,
                       "relevance": "medium",
                       "why_relevant": "索引按 DOI/摘要特征识别，相关性待 Agent 复核",
                       "source_id": p.get("source_id"), "locator": p.get("locator"),
                       "quote": p.get("line")})
    lic, covered = [], set()
    for c in R.al(idx.get("license_candidates")):
        if c["source_id"] in covered:
            continue
        covered.add(c["source_id"])
        tier = c.get("tier_guess") or "yellow"
        lic.append({"source_id": c["source_id"], "source_name": c["source_id"], "tier": tier,
                    "display_scope": "按材料声明；未声明时仅结论与字段名",
                    "degrade_plan": "受限则不展示原文，仅给定位与结论",
                    "excluded_from_output": tier == "red",
                    "reason": "脚本按关键词初判（未经 Agent 复核）：%s" % R.norm_ws(c.get("line"))[:120]})
    boundaries = [
        {"type": "legal_status_unknown", "item": "全部专利法律状态",
         "detail": "材料未提供官方登记页，状态值统一 unknown", "impact": "不得用于有效性判断"},
        {"type": "family_not_exhaustive", "item": "同族范围",
         "detail": "仅按材料可见链接归并，族可能不完整", "impact": "族结论限定为 observed 范围"},
    ]
    if any("facsimile_ocr" in (m.get("roles") or {}) for m in idx.get("materials", [])):
        boundaries.append({"type": "ocr_merged_page", "item": "影印件 OCR",
                           "detail": "影印件为 OCR 文本，可能存在合并页/截断",
                           "impact": "权利要求摘录以 OCR 文本为准，需对照官方式样"})
    if lic:
        boundaries.append({"type": "license_restricted", "item": "来源许可",
                           "detail": "存在受限或未声明许可的来源", "impact": "受限原文不进主结果"})
    boundaries.append({"type": "claim_scope_unexplained", "item": "权利要求范围",
                       "detail": ("仅摘录原文，未做范围解释" if claims else "未定位到可摘录的权利要求段"),
                       "impact": "保护范围不作判断，不构成侵权/FTO 意见"})
    if papers and objs:
        boundaries.append({"type": "patent_vs_paper_scope", "item": "专利与技术文献口径",
                           "detail": "专利按号码/族定位，技术文献按 DOI/摘要匹配，未混排同一排序",
                           "impact": "两类结果分别核验"})
    gaps = [{"item": "官方法律状态", "why": "材料未提供官方登记", "needed_by": "对外交付前"},
            {"item": "同族完整性", "why": "材料未提供完整族表", "needed_by": "对外交付前"}]
    if not objs:
        gaps.append({"item": "专利对象", "why": "材料中未定位到专利号码", "needed_by": "立即"})
    return {"query": {"kind": "number" if objs else "topic",
                      "statement": "由索引候选自动归纳（未经 Agent 复核）",
                      "targets": [o["number_norm"] for o in objs[:3]],
                      "scope": ["目标专利", "同族", "法律状态", "权利要求", "技术文献", "授权边界"],
                      "excluded": []},
            "number_decisions": nds, "patent_objects": objs, "field_extraction": [],
            "family_edges": edges, "status_entries": status, "claims_versions": claims,
            "technical_papers": papers, "license_decisions": lic, "boundaries": boundaries,
            "conflicts": [], "gaps": gaps,
            "status_note": "兜底生成：结构完整但未经 Agent 阅读判断，证据仅为索引定位。"}


def merge_draft(draft, fb):
    """以 Agent 工作稿为准，缺失键用兜底补；返回 (merged, degradations)。"""
    d, deg = dict(draft or {}), []
    for k in DRAFT_KEYS:
        if not isinstance(d.get(k), (list, dict)) or not d.get(k):
            v = fb.get(k)
            if isinstance(v, (list, dict)) and v:
                d[k] = v
                deg.append("工作稿缺 %s，用索引兜底补齐（%d 条）" % (k, len(v)))
            else:
                d.setdefault(k, [] if not isinstance(v, dict) else v)
    if not isinstance(d.get("query"), dict) or not d.get("query"):
        d["query"] = fb["query"]
        deg.append("工作稿缺 query，用兜底检索意图")
    return d, deg


# ---------------------------------------------------------------- 证据
def _collect(draft, idx):
    items = []

    def add(ref, kind, source_id, locator, quote):
        hit = R.find_quote(idx, quote, source_id, locator) if R.norm_ws(quote) else \
            {"ok": False, "match": "empty", "claimed": locator}
        items.append({"ref": ref, "kind": kind, "source_id": source_id, "locator": locator,
                      "quote": R.norm_ws(quote)[:400], "hit": bool(hit.get("ok")),
                      "match": hit.get("match"), "ratio": hit.get("ratio"),
                      "found_locator": hit.get("locator"), "locator_ok": hit.get("locator_ok", False)})

    for o in R.al(draft.get("patent_objects")):
        for e in R.al(o.get("evidence")):
            add("%s/record" % o.get("patent_id"), "record", e.get("source_id"),
                e.get("locator"), e.get("quote"))
    for f in R.al(draft.get("field_extraction")):
        add("%s/%s" % (f.get("patent_id"), f.get("field")), "field", f.get("source_id"),
            f.get("locator"), f.get("quote"))
    for e in R.al(draft.get("family_edges")):
        m = re.match(r"(M\d+)/(p\d+)", str(e.get("evidence_locator") or ""))
        add("%s->%s" % (e.get("from"), e.get("to")), "family", m.group(1) if m else None,
            m.group(2) if m else None, e.get("quote"))
    for s in R.al(draft.get("status_entries")):
        if R.norm_ws(s.get("quote")):
            add("%s/status" % s.get("patent_id"), "status", s.get("source_id"),
                s.get("locator"), s.get("quote"))
    for c in R.al(draft.get("claims_versions")):
        m = re.match(r"(M\d+)/(p\d+)", str(c.get("locator") or ""))
        add("%s/%s" % (c.get("patent_id"), c.get("version")), "claims",
            m.group(1) if m else None, m.group(2) if m else None, c.get("quote"))
    for p in R.al(draft.get("technical_papers")):
        m = re.match(r"(M\d+)/(p\d+)", str(p.get("locator") or ""))
        add("%s/paper" % p.get("paper_id"), "paper", p.get("source_id") or (m.group(1) if m else None),
            m.group(2) if m else None, p.get("quote"))
    return items


def loc_exists(idx, loc, source_id=None):
    s = str(loc or "")
    m = re.match(r"(M\d+)/(p\d+)", s)
    if not m and re.match(r"^p\d+$", s) and source_id:
        s = "%s/%s" % (source_id, s)
        m = re.match(r"(M\d+)/(p\d+)", s)
    if not m:
        return any(x["id"] == s for x in idx.get("materials", []))
    mid, pl = m.groups()
    mat = next((x for x in idx.get("materials", []) if x["id"] == mid), None)
    return bool(mat and any(p["loc"] == pl for p in mat.get("paras", [])))


def _norms_in_materials(idx):
    out = set()
    for m in idx.get("materials", []):
        for c in R.extract_candidates(m.get("paras", [])):
            out.add(c["norm"])
    for c in R.al(idx.get("number_candidates")):
        out.add(c["norm"])
    return out


def _serial_present(idx, norm):
    digits = re.sub(r"[^0-9]", "", str(norm or ""))
    if len(digits) < 6:
        return False
    for m in idx.get("materials", []):
        if digits in re.sub(r"[^0-9]", "", m.get("blob") or ""):
            return True
    return False


# ---------------------------------------------------------------- 校验
def check(draft, idx):
    E, W = [], []
    draft = draft if isinstance(draft, dict) else {}
    ev = _collect(draft, idx)
    ok = sum(1 for e in ev if e["hit"])

    q = draft.get("query") if isinstance(draft.get("query"), dict) else {}
    kind = str(q.get("kind") or "").lower()
    targets = R.al(q.get("targets"))
    if not q:
        E.append("R1 缺 query：未写检索意图（kind/statement/targets）")
    else:
        if kind not in ("number", "topic", "both"):
            E.append("R1 query.kind 必须是 number|topic|both，实际 %r" % q.get("kind"))
        if kind in ("number", "both") and not targets:
            E.append("R1 number 检索缺 targets")
        for t in targets:
            if R.normalize_number(t)["parse_status"] == "unparsed":
                E.append("R1 target 无法规范化：%r" % t)
        if kind in ("topic", "both") and not R.norm_ws(q.get("statement")):
            E.append("R1 topic 检索缺 statement（检索式/关键词/分类号）")

    nds = R.al(draft.get("number_decisions"))
    if not nds:
        E.append("R2 缺 number_decisions：至少登记 1 个号码的解析结果")
    for n in nds:
        raw = n.get("raw")
        calc = R.normalize_number(raw)
        got = str(n.get("norm") or "").strip()
        if calc["parse_status"] != "unparsed" and got != calc["norm"]:
            E.append("R2 号码规范化不一致：raw=%r 工作稿=%r 脚本=%r" % (raw, got, calc["norm"]))
        if calc["parse_status"] == "unparsed" and str(n.get("parse_status")) == "parsed":
            E.append("R2 脚本判为 unparsed 但工作稿称 parsed：%r" % raw)
        if n.get("parse_status") not in (None, "parsed", "ambiguous", "unparsed"):
            E.append("R2 parse_status 非法：%r" % n.get("parse_status"))

    known = _norms_in_materials(idx)
    for o in R.al(draft.get("patent_objects")):
        norm = str(o.get("number_norm") or "")
        if not norm:
            E.append("R3 %s 缺 number_norm" % o.get("patent_id"))
        elif norm not in known and not _serial_present(idx, norm):
            E.append("R3 %s 的号码 %r 在材料中找不到（疑似编造）" % (o.get("patent_id"), norm))

    for e in ev:
        if not e["hit"]:
            W.append("R4 引文未命中：%s (%s) ratio=%.2f" % (e["ref"], e["kind"], e.get("ratio") or 0))
        elif e["match"] == "ocr_tolerant":
            W.append("R4 OCR 容错命中 %.2f：%s" % (e.get("ratio") or 0, e["ref"]))
        elif not e.get("locator_ok"):
            W.append("R4 locator 与命中段不一致：%s 声称 %s 实为 %s"
                     % (e["ref"], e["locator"], e.get("found_locator")))
    miss = [e for e in ev if not e["hit"]]
    if len(miss) > max(1, int(0.15 * max(1, len(ev)))):
        E.append("R4 引文未命中 %d/%d 条，超过容差" % (len(miss), len(ev)))

    se = R.al(draft.get("status_entries"))
    if not se:
        E.append("R5 缺 status_entries：法律状态必须显式登记（可 unknown）")
    for s in se:
        pid = s.get("patent_id")
        for f in ("as_of", "source_kind", "needs_official_verification"):
            if s.get(f) in (None, ""):
                E.append("R5 %s 缺状态纪律字段 %s" % (pid, f))
        sk = str(s.get("source_kind") or "")
        if sk and sk not in SOURCE_KINDS:
            E.append("R5 %s source_kind 非法：%r（允许 %s）" % (pid, sk, ",".join(SOURCE_KINDS)))
        if s.get("as_of") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(s.get("as_of"))):
            W.append("R5 %s as_of 建议 ISO 日期（YYYY-MM-DD），实际 %r" % (pid, s.get("as_of")))
        if sk and sk != "official_register" and s.get("needs_official_verification") is not True:
            E.append("R6 %s 来源为 %s，needs_official_verification 必须为 true" % (pid, sk))
        v = str(s.get("value") or "")
        if v and v not in STATUS_VALUES:
            E.append("R6 %s 状态值非法：%r（允许 unknown 或 %s）" % (pid, v, "/".join(STATUS_VALUES[1:])))
        if sk in ("aggregator", "observed_link") and v not in ("unknown", ""):
            W.append("R6 %s 用 %s 给出确定状态 %r：属线索而非登记，已按风险记录" % (pid, sk, v))
        if s.get("locator") and not loc_exists(idx, s.get("locator"), s.get("source_id")):
            W.append("R6 %s locator 无法解析：%r" % (pid, s.get("locator")))

    fe = R.al(draft.get("family_edges"))
    for e in fe:
        if e.get("link_type") not in LINK_TYPES:
            E.append("R7 族边 link_type 非法：%r（允许 %s）" % (e.get("link_type"), ",".join(LINK_TYPES)))
        if e.get("family_scope") not in ("simple", "extended"):
            E.append("R7 族边 %s->%s 缺 family_scope(simple|extended)" % (e.get("from"), e.get("to")))
        loc = e.get("evidence_locator")
        if not loc:
            E.append("R7 族边 %s->%s 缺 evidence_locator" % (e.get("from"), e.get("to")))
        elif not loc_exists(idx, loc):
            E.append("R7 族边 %s->%s 的 evidence_locator 不存在：%r" % (e.get("from"), e.get("to"), loc))
        if not R.norm_ws(e.get("quote")):
            W.append("R7 族边 %s->%s 缺逐字 quote，族关系不可核验" % (e.get("from"), e.get("to")))

    cv = R.al(draft.get("claims_versions"))
    for c in cv:
        if "ocr_boundary" not in c:
            W.append("R8 %s/%s 未声明 ocr_boundary（无边界请写 none）" % (c.get("patent_id"), c.get("version")))
        if c.get("scope_explained") is True and not R.norm_ws(c.get("quote")):
            W.append("R8 %s 声称已解释范围但无摘录证据" % c.get("patent_id"))

    has_paper = any("paper" in (m.get("roles") or {}) for m in idx.get("materials", []))
    if has_paper and not R.al(draft.get("technical_papers")):
        E.append("R9 材料含技术文献角色，但 technical_papers 为空")

    lic = R.al(draft.get("license_decisions"))
    lic_role_ids = [m["id"] for m in idx.get("materials", []) if "license" in (m.get("roles") or {})]
    if lic_role_ids and not lic:
        E.append("R10 材料含许可表，但 license_decisions 为空")
    tiers = {}
    for l in lic:
        t = str(l.get("tier") or "")
        if t not in ("green", "yellow", "red"):
            E.append("R10 许可分级非法：%r（green|yellow|red）" % t)
        tiers[str(l.get("source_id"))] = t
        if t in ("yellow", "red") and not R.norm_ws(l.get("degrade_plan")):
            W.append("R10 %s 为 %s 但未写降级方案" % (l.get("source_id"), t))
        if t == "red" and l.get("excluded_from_output") is not True:
            E.append("R10 red 来源 %s 必须 excluded_from_output=true" % l.get("source_id"))
    for sid in lic_role_ids:
        if sid not in tiers:
            W.append("R10 许可类材料 %s 未在 license_decisions 中分级（按 yellow 处理）" % sid)
    red = {k for k, v in tiers.items() if v == "red"}
    if red:
        for e in ev:
            if e["source_id"] in red and e["kind"] in ("record", "claims", "field", "paper", "family"):
                E.append("R10 red 来源 %s 的原文进入了主结果（%s）" % (e["source_id"], e["ref"]))
                break

    bs = R.al(draft.get("boundaries"))
    types = {str(b.get("type")) for b in bs}
    for b in bs:
        if str(b.get("type")) not in BOUNDARY_TYPES:
            W.append("R11 边界类型未登记在字典中：%r" % b.get("type"))
    need = set()
    if any(str(s.get("value")) == "unknown" for s in se):
        need.add("legal_status_unknown")
    if fe:
        need.add("family_not_exhaustive")
    if any("facsimile_ocr" in (m.get("roles") or {}) for m in idx.get("materials", [])):
        need.add("ocr_merged_page")
    if cv and not all(c.get("scope_explained") is True for c in cv):
        need.add("claim_scope_unexplained")
    if R.al(draft.get("technical_papers")) and R.al(draft.get("patent_objects")):
        need.add("patent_vs_paper_scope")
    if any(v in ("yellow", "red") for v in tiers.values()):
        need.add("license_restricted")
    for t in sorted(need - types):
        E.append("R11 缺边界声明：%s" % t)
    if not bs:
        E.append("R11 boundaries 为空：必须显式声明未知项与结论边界")

    vals = {}
    for s in se:
        vals.setdefault(str(s.get("patent_id")), set()).add(str(s.get("value")))
    declared = " ".join(json.dumps(c, ensure_ascii=False) for c in R.al(draft.get("conflicts")))
    for pid, vs in vals.items():
        vs = {v for v in vs if v and v != "unknown"}
        if len(vs) > 1 and pid not in declared:
            E.append("R13 %s 状态值冲突 %s，未登记 conflicts" % (pid, sorted(vs)))

    cov = R.compute_facets(draft, idx, {"ok": ok, "total": len(ev)})
    if cov["_summary"]["facets_hit"] < 5:
        W.append("R12 检索面覆盖 %d/%d，低于 5" % (cov["_summary"]["facets_hit"],
                                                   cov["_summary"]["facets_total"]))
    counts = {"numbers": len(nds), "patents": len(R.al(draft.get("patent_objects"))),
              "edges": len(fe), "status": len(se), "claims": len(cv),
              "papers": len(R.al(draft.get("technical_papers"))), "licenses": len(lic),
              "red_sources": len(red), "boundaries": len(bs),
              "evidence_total": len(ev), "evidence_verified": ok,
              "evidence_ratio": round(ok / len(ev), 3) if ev else 0.0,
              "facets_hit": cov["_summary"]["facets_hit"],
              "facets_total": cov["_summary"]["facets_total"]}
    return {"counts": counts, "errors": E, "warnings": W, "coverage": cov, "evidence": ev}


# ---------------------------------------------------------------- 复检
def selfcheck(outdir, work, result, idx, input_dir):
    out = Path(outdir)
    arts = ["result.json", "dossiers.md", "number_registry.json", "family_graph.json",
            "status_provenance.csv", "license_gate.md", "boundary_log.json"]
    files, missing, empty = [], [], []
    for a in arts:
        p = out / a
        if not p.is_file():
            missing.append(a)
            continue
        n = p.stat().st_size
        files.append({"file": a, "bytes": n})
        if n == 0:
            empty.append(a)
    contract = result.get("output_contract") or {}
    cov = result.get("coverage") or {}
    ratio = (result.get("counts") or {}).get("evidence_ratio", 0)
    fp_now = R.fingerprint(input_dir)
    stable = fp_now.get("sha256") == (idx.get("fingerprint") or {}).get("sha256")
    checks = {
        "artifacts_present": not missing,
        "artifacts_nonempty": not empty,
        "contract_keys_complete": bool(contract) and all(k in contract for k in contract),
        "evidence_ratio_ge_0_9": bool(ratio >= 0.9),
        "facets_ge_5": bool((cov.get("_summary") or {}).get("facets_hit", 0) >= 5),
        "status_note_present": bool(R.norm_ws(result.get("note"))),
        "input_fingerprint_stable": bool(stable),
        "boundary_log_nonempty": bool(((result.get("boundary_log") or {}).get("counts") or {}).get("entries")),
    }
    report = {"skill": R.SKILL_NAME, "version": VERSION, "checked_at": R.now(),
              "overall_pass": all(checks.values()), "checks": checks, "artifacts": files,
              "missing": missing, "empty": empty, "contract_keys": list(contract),
              "evidence_ratio": ratio, "facets": cov.get("_summary"),
              "fingerprint": fp_now, "notes": [k for k, v in checks.items() if not v]}
    R.dump(Path(work) / "self_check.json", report)
    R.dump(out / "self_check.json", report)
    return report
