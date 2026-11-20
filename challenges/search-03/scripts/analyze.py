#!/usr/bin/env python3
"""analyze.py - judging, ranking, artefact rendering and contract back-fill.

Second module of the pack (core.py stays the I/O/discovery layer). Stdlib only.
Deterministic: no randomness, no clock-dependent ordering.
"""

from core import *  # noqa: F401,F403  (text utils, constants, io helpers)
import core as C  # noqa: F401

VERSION = C.VERSION
LABELS = C.LABELS
RELEVANCE = C.RELEVANCE
RULES = C.RULES
TYPE_WEIGHT = C.TYPE_WEIGHT
REL_ORDER = C.REL_ORDER
W = C.W
KEEP_MIN, MAYBE_MIN = C.KEEP_MIN, C.MAYBE_MIN
STATUS_SET = ("answered", "partial", "insufficient_evidence", "input_error")


# ---------------------------------------------------------------- clustering
def cluster(cands):
    par = list(range(len(cands)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            par[max(a, b)] = min(a, b)

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            if a["doi"] and b["doi"] and a["doi"] == b["doi"]:
                union(i, j)
                continue
            ta, tb = title_key(a["title"]), title_key(b["title"])
            if ta and ta == tb:
                union(i, j)
                continue
            if not ta or not tb:
                continue
            sm = sim(a["title"], b["title"])
            if sm >= 0.90:
                union(i, j)
            elif sm >= 0.75 and (a["record_type"] == "preprint") != (b["record_type"] == "preprint"):
                union(i, j)
    groups = {}
    for i in range(len(cands)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for gid, idxs in enumerate(sorted(groups.values(), key=lambda v: min(v)), 1):
        members = [cands[i] for i in idxs]

        def pref(r):
            return (1 if r["record_type"] != "preprint" else 0, 1 if r["doi"] else 0,
                    r["year"] or 0, len(r["abstract"]), -r["order"])
        members.sort(key=pref, reverse=True)
        primary = members[0]
        ev = []
        for m in members[1:]:
            why = []
            if m["doi"] and primary["doi"] and m["doi"] == primary["doi"]:
                why.append("same_doi")
            if title_key(m["title"]) and title_key(m["title"]) == title_key(primary["title"]):
                why.append("same_title")
            elif sim(m["title"], primary["title"]) >= 0.9:
                why.append("title_similarity>=0.90")
            if (m["record_type"] == "preprint") != (primary["record_type"] == "preprint"):
                why.append("preprint_vs_published")
            if m["fixture"] or primary["fixture"]:
                why.append("input_fixture")
            m["duplicate_of"] = primary["record_id"]
            m["cluster_id"] = "g%02d" % gid
            m["merge_evidence"] = {"reasons": why or ["normalised_title_match"],
                                   "kept": primary["record_id"],
                                   "kept_locator": primary["locator"],
                                   "merged_locator": m["locator"],
                                   "kept_doi": primary["doi"], "merged_doi": m["doi"]}
            ev.append({"merged": m["record_id"], "into": primary["record_id"],
                       "reasons": m["merge_evidence"]["reasons"]})
        primary["cluster_id"] = "g%02d" % gid
        primary["cluster_size"] = len(members)
        if len(members) > 1:
            out.append({"cluster_id": "g%02d" % gid, "kept": primary["record_id"],
                        "merged": [m["record_id"] for m in members[1:]],
                        "reason": "version_or_duplicate", "evidence": ev,
                        "kept_locator": primary["locator"],
                        "merged_locators": [m["locator"] for m in members[1:]]})
    # same-study families (NOT merged)
    fams = []
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            if a.get("duplicate_of") or b.get("duplicate_of"):
                continue
            if not a["authors"] or not b["authors"]:
                continue
            if a["authors"][0].split()[-1:].__str__() == "''":
                continue
            la = (a["authors"][0].split()[-1] if a["authors"][0].split() else "").lower()
            lb = (b["authors"][0].split()[-1] if b["authors"][0].split() else "").lower()
            if not la or la != lb:
                continue
            if a["year"] and b["year"] and abs(a["year"] - b["year"]) > 2:
                continue
            if sim(a["title"], b["title"]) >= 0.72:
                g = "s%02d" % (len(fams) + 1)
                fams.append({"group_id": g, "members": [a["record_id"], b["record_id"]],
                             "kind": "same_study_possible",
                             "evidence": {"first_author": la, "title_similarity": round(sim(a["title"], b["title"]), 3),
                                          "years": [a["year"], b["year"]]},
                             "action": "pending_human"})
                for r in (a, b):
                    r.setdefault("flags", []).append("same_study_group:%s" % g)
    return out, fams


# ---------------------------------------------------------------- rule channel
def field_hits(rec, ts):
    """Weighted term coverage over title(2x) / keywords(1.5x) / abstract(1x)."""
    title = s(rec["title"]).lower()
    kws = s(rec["keywords"]).lower()
    abs_ = s(rec["abstract"]).lower()
    got = []
    for t in ts:
        w = 0.0
        hit = False
        if t and t in title:
            w += 2.0
            hit = True
        if t and t in kws:
            w += 1.5
            hit = True
        if t and t in abs_:
            w += 1.0
            hit = True
        if hit:
            got.append((t, w))
    return got


def facet_score(rec, ts, neutral=None):
    if not ts:
        return (None, [])
    got = field_hits(rec, ts[:8])
    ratio = sum(min(2.0, w) for _, w in got) / (2.0 * len(ts[:8]))
    return (min(1.0, ratio), [t for t, _ in got])


def bridge_ok(cands, crit):
    """Can the criteria vocabulary actually match the candidate pool?

    Zero topic hits combined with a language split (CJK question vs latin pool,
    or the reverse) means no lexical bridge exists; scoring then degrades to a
    structural proxy instead of pretending the papers are irrelevant.
    """
    topic = (crit.get("facets") or {}).get("topic") or []
    q = crit.get("question") or ""
    if not cands or not topic:
        return True
    hits = 0
    for c in cands:
        hay = (CJK_STR(c.get("title")) + " " + CJK_STR(c.get("abstract"))).lower()
        hits += sum(1 for t in topic if t and t in hay)
    if hits:
        return True
    q_cjk = bool(re.search(r"[\u4e00-\u9fff]", q))
    cjk_docs = sum(1 for c in cands
                   if len(re.findall(r"[\u4e00-\u9fff]", CJK_STR(c.get("title")) + CJK_STR(c.get("abstract")))) >= 5)
    lat_docs = sum(1 for c in cands
                   if len(LAT.findall(CJK_STR(c.get("title")) + " " + CJK_STR(c.get("abstract")))) >= 5)
    return not ((q_cjk and lat_docs > cjk_docs) or ((not q_cjk) and cjk_docs > lat_docs))


def CJK_STR(v):
    return v if isinstance(v, str) else ""


def type_tags(rec):
    """Canonical literature-type tags used by R5 / type exclusions."""
    txt = ((rec.get("type_raw") or "") + " " + (rec.get("venue") or "")).lower()
    tags = set()
    if rec.get("record_type") == "preprint" or PREPRINT.search(txt):
        tags.add("preprint")
    if rec.get("record_type") == "review" or re.search(r"review|survey|meta[- ]?analys", txt):
        tags.add("review")
    if rec.get("record_type") == "primary":
        tags.add("primary")
    for tg, pat in (("rct", r"randomi|\brct\b"), ("cohort", r"cohort|case[- ]control")):
        if re.search(pat, txt):
            tags.add(tg)
    return tags


def judge(rec, crit):
    f = crit["facets"]
    structural = crit.get("bridge") == "off"
    topic, thits = facet_score(rec, f["topic"])
    obj, ohits = facet_score(rec, f["object"])
    meth, mhits = facet_score(rec, f["method"])
    topic = 0.0 if topic is None else topic
    obj = topic * 0.9 if obj is None else obj
    meth = topic * 0.9 if meth is None else meth
    flags = []
    if not f["object"]:
        flags.append("facet_unspecified:object")
    if not f["method"]:
        flags.append("facet_unspecified:method")
    abs_ = s(rec["abstract"])
    has_abs = len(abs_) >= 40
    evidence = 1.0 if (has_abs and RESULT_CUE.search(abs_)) else (0.6 if has_abs else 0.1)
    win = f.get("time_window")
    yr = rec["year"]
    if win:
        if yr and win[0] <= yr <= win[1]:
            recency, r4 = 1.0, True
        elif yr and (win[0] - 2) <= yr <= (win[1] + 2):
            recency, r4 = 0.6, False
        else:
            recency, r4 = 0.05, False
    else:
        now = 2026
        recency = 1.0 if (yr and yr >= now - 5) else (0.7 if (yr and yr >= now - 10) else (0.45 if yr else 0.4))
        r4 = bool(yr)
    completeness = sum(1 for x in (rec["title"], rec["abstract"], rec["year"], rec["doi"], rec["authors"]) if x) / 5.0
    if structural:
        score = 0.35 * evidence + 0.25 * recency + 0.20 * completeness + 0.20 * (0.2 if rec["record_type"] == "other" else 1.0)
        flags.append("language_mismatch_no_lexical_bridge")
    else:
        score = (W["topic"] * topic + W["object"] * obj + W["method"] * meth + W["evidence"] * evidence +
                 W["recency"] * recency + W["completeness"] * completeness)
    hard = []
    tl = (rec["title"] + " " + rec["venue"] + " " + rec["type_raw"])
    if BAD_TYPE.search(tl):
        hard.append("retraction_or_editorial")
    ex_hits = [t for t in f.get("exclusions", [])[:10] if t and t in (rec["title"] + " " + abs_).lower()]
    if len(ex_hits) >= max(2, len(f.get("exclusions", [])[:10]) // 2):
        hard.append("exclusion_clause_hit:%s" % ",".join(ex_hits[:3]))
    tags = type_tags(rec)
    t_ex = [x for x in (f.get("type_exclude") or []) if x in tags]
    t_in = f.get("type_include") or []
    if t_ex:
        hard.append("excluded_type:" + ",".join(sorted(t_ex)))
    type_ok = (not t_in) or bool(set(t_in) & tags)
    if hard:
        score = min(score, 0.12)
    score = round(max(0.0, min(1.0, score)), 3)
    label, rel = "exclude", "none"
    if hard:
        pass
    elif structural:
        label, rel = "maybe", "indirect"
    elif not has_abs:
        label = "maybe"
        rel = "indirect" if topic >= 0.35 else "none"
        flags.append("abstract_missing")
    elif score >= KEEP_MIN and topic >= 0.35:
        label = "keep"
    elif score >= MAYBE_MIN or topic >= 0.2:
        label = "maybe"
    if label != "exclude":
        if topic >= 0.5 and obj >= 0.4 and meth >= 0.35:
            rel = "direct"
        elif topic >= 0.25 or obj >= 0.4:
            rel = "indirect"
        else:
            rel = "none"
    hit = []
    if topic >= 0.30:
        hit.append("R1")
    if obj >= 0.50:
        hit.append("R2")
    if meth >= 0.50:
        hit.append("R3")
    if r4:
        hit.append("R4")
    if type_ok and (tags or rec["record_type"] in ("primary", "review")):
        hit.append("R5")
    if evidence >= 0.85:
        hit.append("R6")
    if completeness >= 0.8:
        hit.append("R7")
    viol = []
    if hard:
        viol.append("R8")
    if not has_abs:
        viol.append("R11")
    if win and not r4:
        viol.append("R4")
    if topic < 0.15:
        viol.append("R1")
    quote, qfield = pick_quote(rec, [t for t in (thits + ohits + mhits)][:8])
    conf = "high" if (has_abs and len(hit) >= 4) else ("medium" if (has_abs and len(hit) >= 2) else "low")
    parts = "主题%.2f/对象%.2f/方法%.2f/证据%.2f/时效%.2f/元数据%.2f" % (topic, obj, meth, evidence, recency, completeness)
    why = "规则通道：%s；命中 %s%s" % (parts, "/".join(hit) if hit else "无",
                                     ("；违反 " + "/".join(viol)) if viol else "")
    if hard:
        why += "；硬排除(" + ",".join(hard) + ")"
    return {"label": label, "relevance": rel, "score": score, "criteria_hit": hit,
            "criteria_violated": viol, "evidence_quote": quote, "evidence_field": qfield,
            "confidence": conf, "rationale": why, "flags": flags,
            "components": {"topic": round(topic, 3), "object": round(obj, 3), "method": round(meth, 3),
                           "evidence": round(evidence, 3), "recency": round(recency, 3),
                           "completeness": round(completeness, 3)},
            "matched_terms": {"topic": thits[:6], "object": ohits[:6], "method": mhits[:6]}}


def sentences(text):
    out = [x.strip() for x in SENT.split(flat(text)) if x and x.strip()]
    return out or ([flat(text)] if flat(text) else [])


def pick_quote(rec, ts, maxlen=200):
    for field in ("abstract", "title"):
        src = s(rec.get(field))
        if not src:
            continue
        best, bs = None, -1.0
        for sent in sentences(src):
            low = sent.lower()
            sc = sum(2.0 if t in s(rec["title"]).lower() else 1.0 for t in ts if t and t in low)
            if sc > bs or (sc == bs and best and len(sent) < len(best)):
                best, bs = sent, sc
            if sc >= max(2.0, len(ts) * 0.6):
                break
        if best:
            if len(best) > maxlen:
                cut = best[:maxlen]
                sp = cut.rfind(" ")
                best = cut[:sp] if sp > 120 else cut
            best = flat(best)
            if best and best in flat(src):
                return best, field
    return None, None


def quote_check(rec, quote, locator=None):
    if not quote:
        return False, None
    q = flat(quote)
    fields = {"title": flat(rec["title"]), "abstract": flat(rec["abstract"]), "keywords": flat(rec["keywords"])}
    order = ["abstract", "title", "keywords"]
    if isinstance(locator, str):
        low = locator.lower()
        order = [f for f in ("abstract", "title", "keywords") if f in low] + [f for f in order if f not in low]
    for f in order:
        if fields[f] and q and q in fields[f]:
            return True, f
    return False, None


# ---------------------------------------------------------------- ranking
def rank_rows(rows, k):
    pool = [r for r in rows if r["label"] != "exclude" and not r.get("duplicate_of")]
    pool.sort(key=lambda r: (-round(float(r.get("score") or 0.0), 4), REL_ORDER.get(r.get("relevance"), 3),
                             -TYPE_WEIGHT.get(r.get("record_type"), 0.3), -(r.get("year") or 0),
                             str(r.get("record_id"))))
    for i, r in enumerate(pool, 1):
        r["rank"] = i
    groups = []
    for r in pool:
        sc = round(float(r.get("score") or 0.0), 4)
        if groups and groups[-1]["score"] == sc:
            groups[-1]["record_ids"].append(r["record_id"])
        else:
            groups.append({"score": sc, "record_ids": [r["record_id"]]})
    tie = [{"score": g["score"], "record_ids": g["record_ids"],
            "tie_break": "relevance(direct>indirect>none) -> record_type_weight(primary>review>preprint>other) "
                         "-> year desc -> record_id asc"}
           for g in groups if len(g["record_ids"]) > 1]
    return pool, tie


# ---------------------------------------------------------------- envelope + contract
STATUS_SET = ("answered", "partial", "insufficient_evidence", "input_error")


def envelope(case_id, status, specs):
    res = {
        "case_id": case_id or "unknown", "status": status if status in STATUS_SET else "partial",
        "task": "literature_screening_and_ranking", "skill_version": VERSION,
        "errors": [], "degradations": [], "assumptions": [], "warnings": [],
        "sources": [], "uncertainties": [], "pending_human": [], "changes": [],
        "queries": [], "runtime": {"version": VERSION, "python": None, "elapsed_sec": 0.0, "finished": False},
        "result": {"screening": [], "ranking": {}, "coverage": {}, "conflicts": {},
                   "criteria": {}, "method_notes": {}, "artifacts": {}},
    }
    fill_contract(res, specs)
    return res


def contract_value(key, res):
    """Semantic mapping from an arbitrary output_contract key to our artefacts."""
    low = str(key).lower()
    r = res.get("result", {})
    screening = r.get("screening") or []
    if low in ("case_id", "case", "id"):
        return res.get("case_id")
    if low == "status":
        return res.get("status")
    groups = (
        (("rank", "order", "priorit", "sorted", "top"), lambda: r.get("ranking", {}).get("ordered") or screening),
        (("screen", "result", "candidate", "paper", "record", "item", "literature", "hit"), lambda: screening),
        (("cover", "count", "stat", "census"), lambda: r.get("coverage") or {}),
        (("conflict", "dup", "merge", "version", "dedup"), lambda: r.get("conflicts") or {}),
        (("criteria", "guideline", "label", "protocol", "rule"), lambda: r.get("criteria") or {}),
        (("evidence", "quote", "citation", "locator", "source"), lambda: evidence_rows(screening)),
        (("report", "markdown", "text", "narrative", "readme", "explain", "rationale"),
         lambda: r.get("report_md") or ""),
        (("quer", "search"), lambda: res.get("queries") or []),
        (("uncertain", "gap", "limitation", "risk", "degrad"), lambda: res.get("uncertainties") or []),
        (("error",), lambda: res.get("errors") or []),
        (("runtime", "meta", "provenance"), lambda: res.get("runtime") or {}),
    )
    for needles, build in groups:
        if any(n in low for n in needles):
            return build()
    return None


def evidence_rows(screening):
    return [{"record_id": x["record_id"], "quote": (x.get("reason") or {}).get("evidence_quote"),
             "locator": (x.get("reason") or {}).get("evidence_locator"),
             "criteria_hit": (x.get("reason") or {}).get("criteria_hit")} for x in screening]


def fill_contract(res, specs):
    for key, kind, _spec in specs:
        if key == "__implicit__":
            continue
        if key in res:
            continue
        val = contract_value(key, res)
        empty = val in (None, [], {}, "")
        if empty:
            val = [] if kind == "list" else ({} if kind == "dict" else ("" if kind == "string" else None))
            res["degradations"].append({"stage": "contract", "issue": "contract_field_filled_empty",
                                        "field": key, "declared_type": kind})
        res[key] = val
    return res


# ---------------------------------------------------------------- artifacts
def screening_row(rec, j, source):
    quote = j.get("evidence_quote")
    qv = j.get("quote_verified")
    if qv is None:
        qv = bool(quote and quote_check(rec, quote)[0])
    reason = {"criteria_hit": j.get("criteria_hit") or [], "criteria_violated": j.get("criteria_violated") or [],
              "evidence_quote": quote, "evidence_locator": locator_for(rec, j),
              "quote_verified": bool(qv),
              "confidence": j.get("confidence") or "low", "rationale": j.get("rationale") or ""}
    return {
        "record_id": rec["record_id"], "title": rec["title"], "authors": rec.get("authors") or [],
        "year": rec.get("year"), "doi": rec.get("doi"), "venue": rec.get("venue"),
        "record_type": rec.get("record_type"), "locator": rec.get("locator"),
        "label": j.get("label"), "relevance": j.get("relevance"), "score": j.get("score"),
        "rank": None, "reason": reason,
        "duplicate_of": rec.get("duplicate_of"), "merge_evidence": rec.get("merge_evidence"),
        "cluster_id": rec.get("cluster_id"), "flags": list(dict.fromkeys((j.get("flags") or []) + (rec.get("flags") or []))),
        "fixture": bool(rec.get("fixture")), "source": source,
        "components": j.get("components"), "matched_terms": j.get("matched_terms"),
    }


def locator_for(rec, j):
    base = rec.get("locator") or {}
    field = j.get("evidence_field") or ("abstract" if "abstract" in s(j.get("evidence_locator")).lower() else None)
    if isinstance(j.get("evidence_locator"), str) and j.get("evidence_locator"):
        return j["evidence_locator"]
    fields = base.get("fields") or {}
    ptr = fields.get(field or "abstract") or base.get("pointer")
    return "%s#%s" % (base.get("file", "?"), ptr)


def coverage_of(rows, cands, overflow=0):
    total = len(cands)
    labels = {k: sum(1 for r in rows if r["label"] == k) for k in LABELS}
    rel = {k: sum(1 for r in rows if r["relevance"] == k) for k in RELEVANCE}
    merged = sum(1 for r in rows if r.get("duplicate_of"))
    return {
        "total_candidates": total, "screened": len(rows), "coverage_ratio": round(len(rows) / total, 4) if total else 0.0,
        "labels": labels, "relevance": rel,
        "kept_in_ranking": sum(1 for r in rows if r.get("rank")),
        "merged_duplicates": merged, "unique_after_merge": total - merged,
        "same_study_groups": len({f for r in rows for f in (r.get("flags") or []) if str(f).startswith("same_study_group")}),
        "missing_abstract": sum(1 for r in rows if not s(r.get("title")) or
                                len(s((r.get("reason") or {}).get("evidence_quote"))) == 0),
        "missing_year": sum(1 for r in rows if r.get("year") is None),
        "missing_doi": sum(1 for r in rows if not r.get("doi")),
        "maybe_zone": labels.get("maybe", 0),
        "rule_fallback_rows": sum(1 for r in rows if r.get("source") == "rule_fallback"),
        "agent_rows": sum(1 for r in rows if r.get("source") == "agent_draft"),
        "quote_verified": sum(1 for r in rows if (r.get("reason") or {}).get("quote_verified")),
        "not_processed_cap": overflow,
        "recall_note": "Only the supplied candidate snapshot is screened; no global recall, no live database "
                       "query is claimed.",
    }


def render_report(res, crit, rows, ranking, conflicts):
    r = res["result"]
    cov = r.get("coverage", {})
    o = ["# 候选文献筛选与排序报告", ""]
    o += ["- case_id: `%s`" % res.get("case_id"), "- status: `%s`" % res.get("status"),
          "- 候选总数: %s；已逐条判定: %s；覆盖率: %s" % (cov.get("total_candidates"), cov.get("screened"),
                                                 cov.get("coverage_ratio")), ""]
    o += ["## 1. 研究问题与判定口径", "", "**问题**：%s" % (crit.get("question") or "（输入未明确给出，按材料推断）"), ""]
    o += ["**纳排条件摘录**（逐条来自输入，未补造）：", ""]
    for i, cl in enumerate((crit.get("clauses", {}).get("inclusion") or [])[:8], 1):
        o.append("%d. [纳入] %s" % (i, cl))
    for cl in (crit.get("exclusion_clauses") or [])[:6]:
        o.append("- [排除] %s" % cl)
    if not (crit.get("clauses", {}).get("inclusion") or crit.get("exclusion_clauses")):
        o.append("- 输入未给出显式纳排条款；按研究问题主题/对象/方法/时间 facet 推断，见 assumptions。")
    o += ["", "**标签定义**：keep=直接支撑研究问题；maybe=信息不足或间接相关，需人工看一眼；"
          "exclude=不相关/硬排除/重复版本。详见 `references/labeling-guideline.md`。", ""]
    o += ["## 2. 排序结果（top_k）", "", "| rank | record_id | label | 年份 | 类型 | score | 依据 |", "|---|---|---|---|---|---|---|"]
    for row in ranking.get("top_k", [])[:30]:
        o.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row.get("rank"), row.get("record_id"), row.get("label"), row.get("year") or "-",
            row.get("record_type"), row.get("score"),
            (row.get("reason", {}).get("rationale") or "")[:80].replace("|", "/")))
    o += ["", "排序键：score↓ → relevance(direct>indirect>none) → 类型权重(原始1.0/综述0.8/预印本0.7/其他0.3) "
          "→ 年份↓ → record_id↑；同分档见 `ranking.json.tie_groups`。", ""]
    o += ["## 3. 待定区与排除原因", ""]
    maybe = [x for x in rows if x["label"] == "maybe"]
    o.append("- 待定 %d 条：%s" % (len(maybe), ", ".join(x["record_id"] for x in maybe[:20]) or "无"))
    excl = [x for x in rows if x["label"] == "exclude"]
    o.append("- 排除 %d 条，理由分布：" % len(excl))
    dist = {}
    for x in excl:
        key = "duplicate/version" if x.get("duplicate_of") else (
            "hard_exclusion" if "R8" in (x["reason"].get("criteria_violated") or []) else
            "abstract_missing" if "R11" in (x["reason"].get("criteria_violated") or []) else "low_relevance")
        dist[key] = dist.get(key, 0) + 1
    for k2, v2 in sorted(dist.items()):
        o.append("  - %s: %d" % (k2, v2))
    o += ["", "## 4. 重复与版本合并", ""]
    cl = conflicts.get("duplicate_clusters") or []
    if cl:
        for c in cl:
            o.append("- `%s`：保留 %s，合并 %s（%s）" % (c["cluster_id"], c["kept"], ", ".join(c["merged"]),
                                                   ", ".join(sum([e.get("reasons", []) for e in c.get("evidence", [])], []))[:60]))
    else:
        o.append("- 未发现 DOI/题名/预印本层面的重复或版本变体。")
    o += ["", "## 5. 冲突与人工复核", ""]
    pend = res.get("pending_human") or []
    o += ["- 升级人工共 %d 项" % len(pend)] + ["  - %s" % (p.get("action") or p.get("issue")) for p in pend[:12]]
    o += ["", "## 6. 覆盖、限制与自查", "",
          "- 有限快照：只对给定候选集判定，不声称全局召回。",
          "- 判定双通道：规则通道（可复算）+ Agent 工作稿通道；不一致处已升级为待定并记录。",
          "- 覆盖统计见 `coverage.json`；校验结果见 `selfcheck.json`。"]
    return "\n".join(o) + "\n"


