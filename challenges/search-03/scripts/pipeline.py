#!/usr/bin/env python3
"""pipeline.py - judgement merge, draft validation, build and conflict wiring.

Loaded by main.py, which injects shared helpers through ``H`` (no circular import).
Exit code is always 0: every failure path still leaves a legal partial result.json.
"""

import time

import core as C
import analyze as A

H = {}


def _h(name, *args):
    fn = H.get(name)
    if fn is None:
        raise RuntimeError("helper %r not injected by main.py" % name)
    return fn(*args)


def apply_draft(rec, e, crit):
    base = A.judge(rec, crit)
    def pick(key, valid=None, default=None):
        v = e.get(key)
        if isinstance(v, str):
            v = v.strip()
        if v in (None, "", []):
            return default
        if valid and v not in valid:
            return default
        return v
    label = pick("label", A.LABELS, base["label"])
    rel = pick("relevance", A.RELEVANCE, base["relevance"])
    score = pick("score")
    try:
        score = round(max(0.0, min(1.0, float(score))), 3) if score is not None else base["score"]
    except Exception:
        score = base["score"]
    hits = [h for h in (e.get("criteria_hit") or []) if str(h) in A.RULES]
    viol = [h for h in (e.get("criteria_violated") or []) if str(h) in A.RULES]
    quote = C.flat(str(e.get("evidence_quote") or ""))[:400] or None
    ok, field = A.quote_check(rec, quote, e.get("evidence_locator"))
    flags = [str(f) for f in (e.get("flags") or [])][:8]
    if quote and not ok:
        flags.append("quote_unverified")
        label = "maybe" if label != "exclude" else label
        rel = "indirect" if rel == "direct" else rel
    if not quote:
        flags.append("no_quote")
    conf = pick("confidence", ("high", "medium", "low"), base["confidence"])
    if quote and not ok:
        conf = "low"
    if label == "keep" and rel == "none":
        rel = "indirect"
        flags.append("relevance_upgraded")
    reason = C.flat(str(e.get("rationale") or e.get("reason") or ""))[:600] or base["rationale"]
    if quote and not ok:
        score = min(score, 0.5)                      # unverifiable evidence never keeps a top score
    j = dict(base)
    j.update({"label": label, "relevance": rel, "score": score, "confidence": conf,
              "criteria_hit": hits or base["criteria_hit"], "criteria_violated": viol,
              "evidence_quote": quote or base["evidence_quote"],
              "evidence_field": field or base.get("evidence_field"),
              "rationale": reason, "flags": flags + base.get("flags", [])})
    final_q = j.get("evidence_quote")
    j["quote_verified"] = bool(final_q and A.quote_check(rec, final_q, j.get("evidence_locator"))[0])
    if j["quote_verified"] and "quote_unverified" in j["flags"]:
        j["flags"] = [f for f in j["flags"] if f != "quote_unverified"]
    if e.get("evidence_locator"):
        j["evidence_locator"] = str(e["evidence_locator"])[:300]
    diff = abs(A.LABELS.index(label) - A.LABELS.index(base["label"])) if label in A.LABELS else 0
    j["rule_label"] = base["label"]
    j["channel_agreement"] = (label == base["label"])
    if diff >= 1 and not j["quote_verified"]:
        flags.append("channel_disagreement_escalated")
        j["flags"] = flags
        if label == "keep":
            j["label"] = label = "maybe"
            j["relevance"] = rel = "indirect"
        j["rationale"] = reason + "（规则通道判 %s，引证未通过逐字校验，降为待定）" % base["label"]
    return j


# ------------------------------------------------------------------ commands
def cmd_init(args, ctx):
    inp, out, work = ctx
    idx, specs = build_index(inp)
    C.jwrite(work / "index.json", idx)
    status = "input_error" if not idx["counts"]["candidates"] else "partial"
    res = envelope_from(idx, specs, status)
    for k in ("status", "case_id"):
        if k in res:
            res[k] = status if k == "status" else res["case_id"]
    _h("refresh_contract", res, specs)
    if not idx["counts"]["candidates"]:
        res["degradations"].append({"stage": "init", "issue": "no_candidates_found",
                                    "detail": "no record list with a title field under /input"})
    else:
        res["degradations"].append({"stage": "init", "issue": "screening_not_started",
                                    "detail": "partial placeholder written before agent reads materials"})
    _h("finalize", out, res)

    tpl = {"case_id": idx["case_id"], "research_question": "", "criteria_used": [], "records": [],
           "conflicts": [], "uncertainties": [],
           "_howto": "每条候选填 label/relevance/score/criteria_hit/evidence_quote+evidence_locator/confidence/rationale；"
                     "evidence_quote 必须逐字来自摘要或题名。schema 见 references/draft-schema.md"}
    for rec in idx["candidates"]:
        tpl["records"].append({"record_id": rec["record_id"], "label": "", "relevance": "", "score": None,
                               "criteria_hit": [], "criteria_violated": [], "evidence_quote": "",
                               "evidence_locator": A.locator_for(rec, {}), "confidence": "",
                               "rationale": "", "duplicate_of": rec.get("duplicate_of"), "flags": []})
    C.jwrite(work / "draft.template.json", tpl)

    crit = idx["criteria"]
    print("=" * 78)
    print("init: case_id=%s  status=%s" % (idx["case_id"], status))
    print("input   : %s  (case=%s)" % (inp, idx["case_file"]))
    print("contract: %d keys -> %s" % (idx["counts"]["contract_keys"],
                                       ", ".join(k["key"] for k in idx["contract"])[:400]))
    print("found   : %d candidates | %d duplicate clusters | %d same-study groups | overflow=%d"
          % (idx["counts"]["candidates"], idx["counts"]["clusters"], idx["counts"]["same_study_groups"],
             idx.get("overflow", 0)))
    print("question: %s" % (crit.get("question") or "(未明确给出)"))
    print("k       : %s | time_window=%s" % (crit.get("k"), (crit.get("facets") or {}).get("time_window")))
    f = crit.get("facets") or {}
    for name in ("topic", "object", "method", "type"):
        print("facet   : %-8s %s" % (name, ", ".join(f.get(name) or [])[:160] or "-"))
    print("materials:")
    for s in idx["sources"][:20]:
        print("  - %-46s %-18s records=%s" % (s.get("path"), s.get("kind"), s.get("records")))
    if idx.get("degradations") or idx.get("errors"):
        print("degradations/errors: %d (see index.json)" % (len(idx.get("degradations", [])) + len(idx.get("errors", []))))
    print("-" * 78)
    print("NEXT: python3 scripts/main.py show   # read criteria + candidates with locators")
    print("      then write %s from draft.template.json, then check, then build" % (work / "draft.json"))
    print("outputs: %s" % C.jwrite.__module__)
    print("=" * 78)
    return res


def cmd_show(args, ctx):
    inp, out, work = ctx
    idx, _ = _h("load_index", work, inp)
    crit = idx["criteria"]
    entries, _meta = _h("load_drafts", work)
    cands = idx["candidates"]
    if args.criteria:
        print("=" * 78)
        print("研究问题: %s" % (crit.get("question") or "(未给出)"))
        print("目标 k  : %s   时间窗: %s" % (crit.get("k"), (crit.get("facets") or {}).get("time_window")))
        print("纳入条款:")
        for i, cl in enumerate((crit.get("clauses", {}).get("inclusion") or [])[:10], 1):
            print("  %d. %s" % (i, cl))
        print("排除条款:")
        for cl in (crit.get("exclusion_clauses") or [])[:10]:
            print("  - %s" % cl)
        print("来源定位: %s" % "; ".join("%s (%s chars)" % (b["locator"], b["chars"]) for b in crit.get("blocks", [])))
        print("规则表: R1..R12 见 references/labeling-guideline.md")
        print("=" * 78)
        return
    if args.ids:
        want = [x.strip() for x in args.ids.split(",") if x.strip()]
        sel = [c for c in cands if c["record_id"] in want]
    elif args.picks:
        sel = [c for c in cands if c["record_id"] not in entries]
    else:
        size = max(1, int(args.page_size))
        page = max(1, int(args.page))
        sel = cands[(page - 1) * size: page * size]
    print("=" * 78)
    print("case=%s  候选 %d 条，本次显示 %d 条（page=%s size=%s picks=%s）  draft=%d 条"
          % (idx["case_id"], len(cands), len(sel), args.page, args.page_size, args.picks, len(entries)))
    print("研究问题: %s" % (crit.get("question") or "-"))
    print("k=%s 时间窗=%s 主题词=%s" % (crit.get("k"), (crit.get("facets") or {}).get("time_window"),
                                    ", ".join((crit.get("facets") or {}).get("topic") or [])[:120]))
    print("-" * 78)
    for rec in sel:
        base = rec.get("locator") or {}
        tag = " [DUP->%s]" % rec["duplicate_of"] if rec.get("duplicate_of") else (
            " [cluster primary, merged %s]" % (rec.get("cluster_size", 1) - 1) if rec.get("cluster_size", 1) > 1 else "")
        fx = " [FIXTURE]" if rec.get("fixture") else ""
        print("[%s]%s%s type=%s year=%s" % (rec["record_id"], tag, fx, rec.get("record_type"), rec.get("year") or "-"))
        print("  TITLE: %s" % (rec.get("title") or "(无题名)"))
        if rec.get("authors"):
            print("  AUTH : %s" % "; ".join(rec["authors"][:4]))
        print("  META : venue=%s | doi=%s | venue_type=%s" % (rec.get("venue") or "-", rec.get("doi") or "-",
                                                            rec.get("type_raw") or "-"))
        print("  LOC  : %s#%s   abstract: %s#%s" % (base.get("file"), base.get("pointer"), base.get("file"),
                                                    (base.get("fields") or {}).get("abstract")))
        if rec.get("duplicate_of"):
            ev = rec.get("merge_evidence") or {}
            print("  MERGE: merged into %s | reasons=%s" % (rec["duplicate_of"], ",".join(ev.get("reasons") or [])))
        if rec.get("flags"):
            print("  FLAGS: %s" % ", ".join(rec["flags"][:4]))
        e = entries.get(rec["record_id"])
        if e:
            print("  DRAFT: label=%s relevance=%s score=%s" % (e.get("label"), e.get("relevance"), e.get("score")))
        ab = C.flat(rec.get("abstract") or "")
        if ab:
            show = ab if args.full else (ab[:args.chars] + (" ...[+%d chars, use --full]" % (len(ab) - args.chars)
                                                           if len(ab) > args.chars else ""))
            print("  ABSTRACT: %s" % show)
        else:
            print("  ABSTRACT: (缺失 -> R11 摘要不足，判 maybe 并在 flags 记 abstract_missing)")
        print()
    if not sel:
        print("（本页无记录；用 --page / --ids / --picks 调整）")
    print("-" * 78)
    print("逐条判断写入 %s ，然后 python3 scripts/main.py check" % (work / "draft.json"))
    print("=" * 78)


def iss(sev, rid, field, issue, detail):
    return {"severity": sev, "record_id": rid, "field": field, "issue": issue, "detail": detail}


def validate(entries, cands, crit, specs):
    issues = []
    ids = [c["record_id"] for c in cands]
    known = set(ids)
    dup = {}
    for rid in entries:
        dup[rid] = dup.get(rid, 0) + 1
    for rid in entries:
        if rid not in known:
            issues.append(iss("error", rid, "record_id", "unknown_record_id", "该 id 不在候选集中，判断会被丢弃"))
    for rid in ids:
        if rid not in entries:
            issues.append(iss("error", rid, "records", "missing_judgement", "候选未被判定，build 将用规则通道兜底"))
    by_id = {c["record_id"]: c for c in cands}
    for rid, e in entries.items():
        rec = by_id.get(rid)
        if not rec:
            continue
        lab = e.get("label")
        if lab not in A.LABELS:
            issues.append({"severity": "error", "record_id": rid, "field": "label", "issue": "bad_enum",
                           "detail": "label=%r，应为 keep|maybe|exclude" % (lab,)})
        rel = e.get("relevance")
        if rel not in A.RELEVANCE:
            issues.append({"severity": "error", "record_id": rid, "field": "relevance", "issue": "bad_enum",
                           "detail": "relevance=%r，应为 direct|indirect|none" % (rel,)})
        sc = e.get("score")
        if sc is None:
            issues.append({"severity": "warn", "record_id": rid, "field": "score", "issue": "score_missing",
                           "detail": "将用规则打分兜底"})
        else:
            try:
                fsc = float(sc)
                if not 0.0 <= fsc <= 1.0:
                    issues.append(iss("error", rid, "score", "score_out_of_range", "score=%s 不在 0..1" % sc))
            except Exception:
                issues.append({"severity": "error", "record_id": rid, "field": "score", "issue": "score_not_number",
                               "detail": "score=%r" % (sc,)})
        hits = e.get("criteria_hit") or []
        bad = [h for h in hits if str(h) not in A.RULES]
        if bad:
            issues.append({"severity": "error", "record_id": rid, "field": "criteria_hit", "issue": "bad_rule_id",
                           "detail": "未知规则 ID: %s（只允许 R1..R12）" % ",".join(map(str, bad[:4]))})
        if not hits and not (e.get("criteria_violated") or []) and not (e.get("flags") or []):
            issues.append(iss("warn", rid, "criteria_hit", "no_rule_cited", "既没写命中规则也没写违反规则，复核者无法对账"))
        q = e.get("evidence_quote")
        if not q:
            issues.append(iss("warn", rid, "evidence_quote", "quote_missing", "无逐字引证，可核验性下降（build 会补规则通道引证）"))
        else:
            ok, field = A.quote_check(rec, q, e.get("evidence_locator"))
            if not ok:
                issues.append({"severity": "error", "record_id": rid, "field": "evidence_quote",
                               "issue": "quote_not_found",
                               "detail": "引文不在题名/摘要中（%s）" % (str(q)[:60],)})
        d = e.get("duplicate_of")
        if d and d not in known:
            issues.append(iss("warn", rid, "duplicate_of", "duplicate_target_unknown", "duplicate_of=%s 不在候选集" % d))
        if lab == "keep" and e.get("score") is not None:
            try:
                if float(e["score"]) < 0.5:
                    issues.append(iss("warn", rid, "score", "keep_with_low_score", "keep 但 score<0.5，标定不一致"))
            except Exception:
                pass
        if lab == "keep" and rel == "none":
            issues.append(iss("warn", rid, "relevance", "keep_but_none", "keep 却判 none，需说明"))
    keepish = sum(1 for e in entries.values() if e.get("label") in ("keep", "maybe"))
    k = int(crit.get("k") or 0)
    if k and keepish < k and cands:
        issues.append({"severity": "warn", "record_id": "-", "field": "k", "issue": "fewer_than_k",
                       "detail": "keep+maybe=%d < k=%d，排名区可能不足 k 条（若候选确实不足请在报告说明）" % (keepish, k)})
    return issues


def cmd_check(args, ctx):
    inp, out, work = ctx
    idx, specs = _h("load_index", work, inp)
    entries, meta = _h("load_drafts", work)
    issues = validate(entries, idx["candidates"], idx["criteria"], specs)
    errs = [i for i in issues if i["severity"] == "error"]
    warns = [i for i in issues if i["severity"] == "warn"]
    C.jwrite(work / "check.json", {"draft_files": meta.get("files", []), "records": len(entries),
                                   "candidates": len(idx["candidates"]),
                                   "errors": errs, "warnings": warns, "stdout_at": time.strftime("%F %T")})
    print("=" * 78)
    print("check: draft=%d 条 / 候选=%d 条 | errors=%d warnings=%d" % (len(entries), len(idx["candidates"]),
                                                                     len(errs), len(warns)))
    if not entries:
        print("!! 没有找到工作稿（draft.json / draft-01.json ...）。")
        print("   build 会用规则通道产出降级交付（status=partial）；这不是推荐路径。")
    for i in errs[:40]:
        print("  ERROR [%s] %s: %s — %s" % (i["record_id"], i["field"], i["issue"], i["detail"]))
    for i in warns[:25]:
        print("  warn  [%s] %s: %s — %s" % (i["record_id"], i["field"], i["issue"], i["detail"]))
    if meta.get("errors"):
        for e in meta["errors"][:6]:
            print("  ERROR draft file %s: %s %s" % (e.get("file"), e.get("issue"), e.get("detail") or ""))
    print("-" * 78)
    print("PASS" if not errs else "FIX %d error(s) then re-run check" % len(errs))
    print("NEXT: python3 scripts/main.py build")
    print("=" * 78)
    return issues


def collect_conflicts(idx, rows, disagreements, unverified):
    annot = idx.get("annotations") or {}
    opinions = []
    for op in (annot.get("opinions") or [])[:40]:
        opinions.append({"source": op.get("source"), "key": op.get("key"), "content": op.get("item"),
                         "kind": "input_fixture_conflicting_opinion",
                         "use": "evidence_only_not_label"})
    return {
        "duplicate_clusters": idx.get("clusters") or [],
        "same_study_groups": idx.get("studies") or [],
        "conflicting_opinion_fixtures": opinions,
        "agent_rule_disagreements": disagreements[:80],
        "quote_unverified": unverified[:80],
        "summary": {"duplicate_clusters": len(idx.get("clusters") or []),
                    "merged_records": sum(len(c.get("merged") or []) for c in (idx.get("clusters") or [])),
                    "same_study_groups": len(idx.get("studies") or []),
                    "opinion_fixtures": len(opinions),
                    "channel_disagreements": len(disagreements),
                    "unverified_quotes": len(unverified)},
    }


def cmd_build(args, ctx):
    inp, out, work = ctx
    idx, specs = _h("load_index", work, inp)
    res = _h("envelope_from", idx, specs, "partial")
    _h("refresh_contract", res, specs)
    _h("finalize", out, res)                       # legal partial lands before heavy work
    cands = idx["candidates"]
    crit = dict(idx["criteria"])
    no_criteria = not (crit.get("facets") or {}).get("topic")
    bridge = A.bridge_ok(cands, crit) and not no_criteria
    crit["bridge"] = "on" if bridge else "off"
    if no_criteria:
        res["degradations"].append({"stage": "judge", "issue": "no_criteria_found",
                                    "detail": "输入未给出研究问题/纳排条件；无判定依据，记录一律待定而非判不相关"})
    bridge_note = None
    if not bridge:
        bridge_note = {"stage": "judge", "issue": "language_mismatch_no_lexical_bridge",
                       "detail": "zero criteria-term hits + different scripts; structural proxy instead of asserting "
                                 "irrelevance"}
    entries, meta = _h("load_drafts", work)
    rows, fallback, disagreements, unverified = [], [], [], []
    for rec in cands:
        e = entries.get(rec["record_id"])
        try:
            if e:
                j = apply_draft(rec, e, crit)
                source = "agent_draft"
                if j.get("rule_label") and not j.get("channel_agreement") and (
                        bridge or "channel_disagreement_escalated" in (j.get("flags") or [])):
                    disagreements.append({"record_id": rec["record_id"], "agent_label": j["label"],
                                          "rule_label": j["rule_label"],
                                          "quote_verified": bool(j.get("quote_verified")),
                                          "action": "escalated_to_maybe" if "channel_disagreement_escalated"
                                                    in (j.get("flags") or []) else "documented"})
                if "quote_unverified" in (j.get("flags") or []):
                    unverified.append({"record_id": rec["record_id"], "quote": (j.get("evidence_quote") or "")[:80]})
            else:
                j = A.judge(rec, crit)
                source = "rule_fallback"
                fallback.append(rec["record_id"])
        except Exception as exc:
            j = {"label": "maybe", "relevance": "indirect", "score": 0.3, "criteria_hit": [], "criteria_violated": [],
                 "evidence_quote": None, "confidence": "low", "flags": ["judge_failed"],
                 "rationale": "判定异常，按待定处理：%s" % type(exc).__name__}
            source = "rule_fallback"
            res["errors"].append({"stage": "judge", "record_id": rec["record_id"], "issue": "judge_failed",
                                  "detail": "%s: %s" % (type(exc).__name__, str(exc)[:140])})
            fallback.append(rec["record_id"])
        if rec.get("duplicate_of"):
            j = dict(j)
            j.update({"label": "exclude", "relevance": "none",
                      "criteria_hit": sorted(set((j.get("criteria_hit") or []) + ["R9"])),
                      "score": 0.0,
                      "rationale": "合并到 %s（%s）；保留原始判定：%s" % (
                          rec["duplicate_of"], ",".join((rec.get("merge_evidence") or {}).get("reasons") or []),
                          j.get("rationale") or "")[:260],
                      "flags": sorted(set((j.get("flags") or []) + ["merged_duplicate"]))})
        rows.append(A.screening_row(rec, j, source))

    pool, ties = A.rank_rows(rows, int(crit.get("k") or 10))
    by_rank = {r["record_id"]: r for r in pool}
    rows.sort(key=lambda r: (0 if r["record_id"] in by_rank else 1,
                             by_rank.get(r["record_id"], {}).get("rank") or 10 ** 6, r["record_id"]))
    cov = A.coverage_of(rows, cands, idx.get("overflow", 0))
    cov["missing_abstract"] = sum(1 for c in cands if len(c["abstract"]) < 40)
    cov["missing_year"] = sum(1 for c in cands if not c.get("year"))
    cov["missing_doi"] = sum(1 for c in cands if not c.get("doi"))
    cov["same_study_groups"] = len(idx.get("studies") or [])
    conflicts = collect_conflicts(idx, rows, disagreements, unverified)
    k = int(crit.get("k") or 10)
    ranking = {
        "ranking_key": "score desc(4dp) -> relevance(direct>indirect>none) -> type_weight(primary1.0/review0.8/"
                       "preprint0.7/other0.3) -> year desc -> record_id asc",
        "k": k,
        "ordered": [{"rank": r["rank"], "record_id": r["record_id"], "score": r["score"],
                     "label": r["label"], "relevance": r["relevance"]} for r in pool],
        "top_k": [r for r in rows if r.get("rank") and r["rank"] <= k],
        "excluded": [{"record_id": r["record_id"], "reason": ("duplicate_of:" + r["duplicate_of"]) if r.get("duplicate_of")
                      else "label_exclude", "label": r["label"]} for r in rows if not r.get("rank")],
        "tie_groups": ties,
        "counts": {"ranked": len(pool), "excluded": sum(1 for r in rows if not r.get("rank")),
                   "top_k_returned": sum(1 for r in rows if r.get("rank") and r["rank"] <= k)},
    }
    if len(ranking["top_k"]) < k:
        res["assumptions"].append("排名区 %d 条 < k=%d（候选不足或判为待定/排除），计数见 ranking.json"
                                  % (len(ranking["top_k"]), k))
    res["result"].update({"screening": rows, "ranking": ranking, "coverage": cov, "conflicts": conflicts,
                          "criteria": {"rules": A.RULES, "question": crit.get("question"), "k": k,
                                       "facets": crit.get("facets"), "clauses": crit.get("clauses"),
                                       "source_blocks": crit.get("blocks")},
                          "method_notes": {"channels": "rule (deterministic, recomputable) + agent draft (semantic, "
                                                      "quote-verified); disagreement -> maybe + pending_human",
                                           "weights": A.W, "keep_threshold": A.KEEP_MIN,
                                           "maybe_threshold": A.MAYBE_MIN,
                                           "dedup": "same DOI | normalised title | title-sim>=0.90 | preprint-vs-"
                                                    "published; keep published > DOI > newer > complete",
                                           "recall": "snapshot only, no global recall claimed"}})
    res["result"]["method_notes"]["lexical_bridge"] = "on" if bridge else "off (structural proxy)"
    if not bridge:
        res["assumptions"].append("纳排词表与候选语种不一致：规则通道只做结构化代评分，不据此断言不相关")
    if meta.get("research_question"):
        res["result"]["criteria"]["agent_research_question"] = meta["research_question"]
    res["assumptions"] += ["纳排口径取自 case.json/task.md 显式条款；未给出的 facet 以主题代理并标 facet_unspecified",
                           "相关性判断只基于给定题名/摘要，不做全文阅读"]
    for rid in fallback[:50]:
        res["uncertainties"].append({"record_id": rid, "issue": "rule_channel_only",
                                     "action": "无 Agent 判定，仅规则通道，优先人工复核"})
    for u in unverified:
        res["pending_human"].append({"record_id": u["record_id"], "issue": "quote_unverified",
                                     "action": "引证未逐字命中，已降为待定：核对原文后改写 quote 或改判"})
    for g in (idx.get("studies") or []):
        res["pending_human"].append({"issue": "same_study_group", "group": g["group_id"],
                                     "records": g["members"],
                                     "action": "疑似同一研究多篇报道，未合并；人工确认是否不同结局指标"})
    for op in (conflicts.get("conflicting_opinion_fixtures") or [])[:10]:
        res["pending_human"].append({"issue": "conflicting_opinion_fixture", "source": op.get("source"),
                                     "action": "输入 fixture 的意见冲突：只作证据、不采纳为标签，需人工裁定"})
    res["degradations"] += idx.get("degradations", [])
    if bridge_note:
        res["degradations"].append(bridge_note) if fallback else res["warnings"].append(bridge_note)
    if not entries:
        res["degradations"].append({"stage": "build", "issue": "no_agent_draft_rule_fallback",
                                    "detail": "全部 %d 条仅用规则通道判定，未做语义复核" % len(rows)})
    elif fallback:
        res["degradations"].append({"stage": "build", "issue": "partial_agent_draft",
                                    "detail": "%d/%d 条缺 Agent 判定，用规则通道兜底" % (len(fallback), len(rows))})
    if unverified:
        res["degradations"].append({"stage": "build", "issue": "quotes_unverified",
                                    "detail": "%d 条引证未逐字命中，已降级为待定" % len(unverified)})
    for e in meta.get("errors", []):
        res["errors"].append({"stage": "draft", "issue": e.get("issue"), "detail": e.get("detail") or e.get("file")})
    if idx.get("overflow"):
        res["degradations"].append({"stage": "build", "issue": "record_cap",
                                    "detail": "%d 条超出记录上限未判定（SCREEN_MAX_RECORDS）" % idx["overflow"]})

    ratio_missing = cov["missing_abstract"] / float(len(cands)) if cands else 1.0
    if not cands:
        status = "input_error"
    elif not entries and ratio_missing >= 0.8:
        status = "insufficient_evidence"
        res["degradations"].append({"stage": "build", "issue": "insufficient_material",
                                    "detail": "摘要缺失比例过高或无 keep，判定不可靠"})
    elif fallback or unverified or res["errors"] or [d for d in res["degradations"]
                                                     if d.get("issue") != "contract_field_filled_empty"]:
        status = "partial"
    else:
        status = "answered"
    res["status"] = status
    res["result"]["report_md"] = A.render_report(res, crit, rows, ranking, conflicts)
    res["result"]["artifacts"] = {
        "result_json": "result.json", "screening": "screening.jsonl", "ranking": "ranking.json",
        "coverage": "coverage.json", "conflicts": "conflicts.json", "report": "screening_report.md"}
    res["changes"] = [{"at": time.strftime("%F %T"), "action": "build",
                       "draft_files": meta.get("files", []), "rows": len(rows),
                       "agent_rows": cov["agent_rows"], "fallback_rows": cov["rule_fallback_rows"]}]
    C.jlwrite(out / "screening.jsonl", rows)
    C.jwrite(out / "ranking.json", ranking)
    C.jwrite(out / "coverage.json", cov)
    C.jwrite(out / "conflicts.json", conflicts)
    (out / "screening_report.md").write_text(res["result"]["report_md"], encoding="utf-8")
    _h("refresh_contract", res, specs)
    _h("finalize", out, res)
    print("=" * 78)
    print("build: status=%s rows=%d agent=%d fallback=%d" % (status, len(rows), cov["agent_rows"],
                                                             cov["rule_fallback_rows"]))
    print("labels: keep=%s maybe=%s exclude=%s merged=%s quote_verified=%s" % (
        cov["labels"].get("keep"), cov["labels"].get("maybe"), cov["labels"].get("exclude"),
        cov["merged_duplicates"], cov["quote_verified"]))
    print("ranking: %d ranked top_k=%d k=%d ties=%d" % (len(pool), len(ranking["top_k"]), k, len(ties)))
    print("contract: %d keys -> %s" % (len(specs), ", ".join(k["key"] for k in idx["contract"])[:360]))
    print("outputs : screening.jsonl ranking.json coverage.json conflicts.json screening_report.md")
    print("NEXT : python3 scripts/main.py selfcheck")
    print("=" * 78)
    return res


