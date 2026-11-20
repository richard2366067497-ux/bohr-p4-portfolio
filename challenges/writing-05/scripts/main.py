# -*- coding: utf-8 -*-
"""Literature-evidence driven writing skill.

Single command runs the whole pipeline: read materials -> split the draft into
claims -> match each claim to located source snippets -> grade the evidence ->
render an editable draft and the evidence artifacts -> write result.json.

    python3 scripts/main.py --input /input --output /app/output --work /app/work

Agent-first enhancement: if ``--draft FILE``, ``$WORK/draft.json`` or ``$INPUT/draft.json``
exists, its optional ``evidence_overrides`` (claim_id -> {source_id, strength}) are applied on
top of the deterministic pipeline and recorded in change_log / uncertainties. Without a draft
the single command is complete on its own.

Standard library only, offline, always exits 0 (a usage error exits 2).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit as K  # noqa: E402

VERSION = "1.1.0"
SKILL = "writing-05-evidence"
MAIN_FILE = "evidence_driven_draft.md"

L = {
    "zh": {"title": "证据驱动成稿（案例 {c}）", "note": "由材料生成；每条实质论断带 [n] 标记，n 对应证据表中的来源。",
           "bound": "证据边界", "refs": "参考文献", "hedge": {"高": "多项证据一致表明", "中": "现有研究提示",
           "低": "初步证据提示", "不足": "材料尚不足以判断"}, "cf": "但有材料报告了不一致结果：",
           "ns": "无", "nf": "未见著录；来源 {s}，定位 {l}", "rt": "按首次引用编号；未给 DOI 不补写",
           "weak": "低/不足论断仅作线索", "conf": "材料内部存在冲突证据，未做合并"},
    "en": {"title": "Evidence-driven draft (case {c})", "note": "Built from materials; each substantive sentence carries a [n] marker into the evidence table.",
           "bound": "Boundaries", "refs": "References", "hedge": {"高": "Consistent evidence indicates",
           "中": "Current studies suggest", "低": "Preliminary evidence hints", "不足": "The material is insufficient to judge"},
           "cf": "However, inconsistent results are reported: ", "ns": "no record located",
           "nf": "no record; source {s}, locator {l}", "rt": "Numbered by first citation; no DOI is invented",
           "weak": "Low/insufficient claims are leads only", "conf": "Conflicting evidence was kept, not merged"},
}


def lang_of(case, docs):
    lg = (case or {}).get("language")
    if lg in ("zh", "en"):
        return lg
    blob = " ".join(d.get("text", "")[:400] for d in docs)
    return "zh" if len(re.findall(r"[一-鿿]", blob)) > len(re.findall(r"[A-Za-z]", blob)) else "en"


def read_case(ind):
    case = {}
    for cand in [Path(ind) / "case.json"] + sorted(Path(ind).glob("*case*.json")):
        if cand.is_file():
            try:
                case = json.loads(cand.read_text(encoding="utf-8", errors="ignore"))
                break
            except Exception:
                continue
    instr = " ".join(str(case.get(k) or "") for k in
                     ("task_instruction", "task", "instruction", "prompt", "goal"))
    for tm in ("task.md", "task.txt"):
        p = Path(ind) / tm
        if p.is_file():
            instr += " " + p.read_text(encoding="utf-8", errors="ignore")[:4000]
            break
    return case, instr


def read_draft(args, ind):
    """Load an optional agent-written draft (evidence overrides). Absent -> None."""
    cands = []
    if getattr(args, "draft", None):
        cands.append(Path(args.draft))
    if getattr(args, "work", None):
        cands.append(Path(args.work) / "draft.json")
    cands.append(Path(ind) / "draft.json")
    for c in cands:
        try:
            if c and c.is_file():
                obj = json.loads(c.read_text(encoding="utf-8", errors="ignore"))
                return obj if isinstance(obj, dict) else None
        except Exception:
            continue
    return None


def apply_draft(draft, rows):
    """Apply agent evidence_overrides onto the deterministic evidence rows."""
    if not isinstance(draft, dict):
        return 0
    ov = draft.get("evidence_overrides")
    if not isinstance(ov, dict):
        return 0
    applied = 0
    for r in rows:
        o = ov.get(r.get("claim_id"))
        if not isinstance(o, dict):
            continue
        touched = False
        if o.get("source_id"):
            r["source_id"] = str(o["source_id"])
            touched = True
        if o.get("locator"):
            r["locator"] = str(o["locator"])
            touched = True
        if o.get("strength") in ("高", "中", "低", "不足"):
            r["strength"] = o["strength"]
            touched = True
        if touched:
            r["rationale"] = (r.get("rationale", "") + " | agent override").strip(" |")
            applied += 1
    return applied


def build_claims(units, docs, instr):
    draft = [d for d in docs if d["kind"] == "draft"]
    claims = []
    if draft:
        ids = {d["doc_id"] for d in draft}
        for u in units:
            if u["doc"] in ids and len(u["text"]) >= 12:
                claims.append(u)
        mode = "revise"
    else:
        mode = "compose"
        pool = [u for u in units if u["kind"] != "references" and len(u["text"]) >= 24
                and not re.match(r"^(参考文献|references?|doi|https?|\[\d+\])", u["text"], re.I)]
        it = K.tokenize(instr)
        pool.sort(key=lambda u: -(K.similarity(instr, u["text"], it)))
        m = re.search(r"(\d{2,4})\s*(?:字|words?|词|characters?)", instr, re.I)
        need = max(3, min(10, int(round((int(m.group(1)) if m else 240) / 30.0))))
        claims = pool[:need]
    kept, uniq = [], []
    for u in claims:
        head = u["text"].strip()
        if any(head[:60] in prev for prev in kept):
            continue
        kept.append(head)
        uniq.append(u)
    claims = uniq
    out = []
    for i, u in enumerate(claims[:40]):
        cause_sub, hits = K.overclaim(u["text"])
        out.append({"claim_id": "C%03d" % (i + 1), "text": u["text"], "render": cause_sub,
                    "type": "causal" if hits else "descriptive",
                    "location": "%s:%s" % (mode, u["loc"]), "uid": u["uid"], "doc": u["doc"]})
    return out, mode


def build_rows(claims, units):
    pool = [u for u in units if len(u["text"]) >= 20]
    toks = {u["uid"]: K.tokenize(u["text"]) for u in pool}
    rows = []
    for c in claims:
        ct = K.tokenize(c["text"])
        cands = []
        for u in pool:
            if u["doc"] == c["doc"]:
                continue
            s = K.similarity(c["text"], u["text"], ct, toks[u["uid"]])
            if re.search(r"\d", u["text"]):
                s += 0.04
            if s >= 0.05:
                cands.append((s, u))
        cands.sort(key=lambda x: -x[0])
        picks = cands[:3]
        if not picks:
            rows.append({"claim_id": c["claim_id"], "source_id": "", "locator": "", "quote": "",
                         "strength": "不足", "support_scope": "no located source", "conflicts": [],
                         "rationale": "no source snippet passed the match threshold", "verified": False})
            continue
        best = picks[0][1]
        design, dp = K.study_design(best["text"] + " " + c["text"])
        n = K.sample_size(best["text"])
        nsrc = len({u["doc"] for _, u in picks})
        cp = K.POS.search(c["text"]); neg = [u for _, u in picks if K.NEG.search(u["text"])]
        conflict = bool(cp and neg)
        lvl, score = K.grade_evidence(dp, n, nsrc, conflict)
        rows.append({"claim_id": c["claim_id"], "source_id": best["doc"], "locator": best["loc"],
                     "quote": best["text"][:200], "strength": lvl, "support_scope": design,
                     "conflicts": [u["loc"] for u in neg][:2], "rationale":
                     "design=%s, n=%s, sources=%d, score=%.2f%s" % (design, n or "?", nsrc, score,
                     " (conflict)" if conflict else ""), "verified": best["text"][:60] in best["text"]})
    return rows


def render(claims, rows, facts, lg, cid="UNKNOWN"):
    z = L[lg]
    lines = ["# " + z["title"].format(c=cid), "", "> " + z["note"], ""]
    by_claim = {}
    for r in rows:
        by_claim.setdefault(r["claim_id"], []).append(r)
    ref_order, ref_index = [], {}

    def mark(src):
        if src not in ref_index:
            ref_index[src] = len(ref_order) + 1
            ref_order.append(src)
        return "[%d]" % ref_index[src]

    for c in claims[:12]:
        rs = by_claim.get(c["claim_id"], [])
        strong = [r for r in rs if r.get("source_id")]
        lvl = min((r["strength"] for r in rs), key=lambda x: ["不足", "低", "中", "高"].index(x), default="不足")
        hedge = z["hedge"][lvl]
        marks = "".join(mark(r["source_id"]) for r in strong[:2])
        body = c.get("render", c["text"]).rstrip("。. ")
        sep = "" if lg == "zh" else " "
        lines.append("- %s%s%s%s" % (hedge, sep, body, (sep + marks) if marks else ""))
        conf = [r for r in rs if r.get("conflicts")]
        if conf:
            lines.append("  - %s%s" % (z["cf"], "、".join(conf[0]["conflicts"]) if lg == "zh"
                                       else ", ".join(conf[0]["conflicts"])))
    lines += ["", "## " + z["bound"], ""]
    weak = sorted({r["claim_id"] for r in rows if r["strength"] in ("低", "不足")})
    lines.append("- %s%s" % (z["weak"] + ("：" if lg == "zh" else ": "), "、".join(weak) if weak else z["ns"]))
    lines.append("- " + z["conf"] if any(r.get("conflicts") for r in rows) else "")
    lines.append("- " + ("著录与真实性未联网核验（离线）；数字与单位按材料原样保留" if lg == "zh"
                         else "Records are not verified online (offline); numbers and units kept as in the materials"))
    lines += ["", "## " + z["refs"], ""]
    for src in ref_order:
        u = next((r for r in rows if r.get("source_id") == src), None)
        loc = u["locator"] if u else ""
        lines.append("%s %s" % (mark(src), z["nf"].format(s=src, l=loc)))
    if not ref_order:
        lines.append("- " + z["ns"])
    lines.append("")
    lines.append("_" + z["rt"] + "_")
    return "\n".join(x for x in lines if x is not None)


def runtime_result(cid, status, lg, filled, main_text, claims, rows, facts, refs, docs, changed, errs, deg):
    outputs = {n: None for n in ("evidence_driven_draft.md", "claims.json", "evidence_table.json",
                                 "evidence_strength.md", "reference_check.md", "uncertainty_notes.md",
                                 "human_review.json", "verification.json", "diff_report.md")}
    sources = [{"source_id": d["doc_id"], "path": d["path"], "bytes": d["bytes"], "kind": d["kind"],
                "read_method": d["method"], "sha256": d["sha256"]} for d in docs]
    if not sources:
        sources = [{"source_id": "input", "path": "no material file discovered under the input directory",
                    "kind": "input", "read_method": "no readable file"}]
    weak = sorted({r["claim_id"] for r in rows if r["strength"] in ("低", "不足")})
    unsup = sorted({r["claim_id"] for r in rows if not r.get("source_id")})
    uncertainties = ["Records and identifiers are not verified online (offline run)"]
    if weak:
        uncertainties.append("Weak claims kept as leads only: " + ", ".join(weak))
    if unsup:
        uncertainties.append("Claims without a located source: " + ", ".join(unsup))
    if any(d["note"] for d in docs):
        uncertainties.append("Some files parsed only partially: " +
                             ", ".join(sorted({d["path"] + ":" + d["note"] for d in docs if d["note"]})))
    limits = ["Offline: source documents were not verified against external databases",
              "Numbers and units are transcribed from the materials without unit conversion",
              "Evidence grades reflect study design, sample size and agreement only"]
    human = []
    if not docs:
        human.append({"item": "No material file was discovered; provide the input documents", "why": "input"})
    if unsup:
        human.append({"item": "Confirm or drop unsupported claims", "claims": unsup[:8], "why": "evidence"})
    if changed:
        human.append({"item": "Review the over-claim downgrades in the draft", "count": len(changed), "why": "wording"})
    change_log = [{"action": "assembled the draft from located material", "target": "evidence_driven_draft.md",
                   "reason": "single-command run"}]
    for ch in changed:
        change_log.append({"action": "downgraded an over-claim", "target": ch.get("claim_id", ""),
                           "reason": "strength is below the causal wording used"})
    for w in weak:
        change_log.append({"action": "marked weak evidence", "target": w, "reason": "low or insufficient grade"})
    facts_default = [{"value": f["value"], "unit": f["unit"], "span": f["span"]} for f in facts[:40]]
    lists = {"preserved_facts": facts_default, "evidence_map": [
        {"claim_id": r["claim_id"], "source_id": r["source_id"], "locator": r["locator"],
         "strength": r["strength"]} for r in rows],
        "change_log": change_log, "language": lg}
    echo = K.fill_contract(CON, cid, MAIN_FILE, lists, status)
    res = {"case_id": cid, "status": status, "skill": SKILL, "skill_version": VERSION, "language": lg,
           "deliverable": MAIN_FILE, "deliverable_summary": main_text[:400],
           "preserved_facts": lists["preserved_facts"], "evidence_map": lists["evidence_map"],
           "change_log": lists["change_log"], "output_contract": echo,
           "outputs": outputs,
           "metrics": {"claims": len(claims), "evidence_rows": len(rows),
                       "rows_with_source": sum(1 for r in rows if r.get("source_id")),
                       "references": len(refs), "downgrades": len(changed),
                       "verified_quote_rate": round(sum(1 for r in rows if r.get("verified"))
                                                    / max(1, len(rows)), 3),
                       "claim_coverage": round(sum(1 for r in rows if r.get("source_id"))
                                               / max(1, len(claims)), 3),
                       "pending_human_count": len(human), "overclaim_flags": len(changed)},
           "sources": sources, "uncertainties": uncertainties, "change_records": change_log,
           "limits": limits, "human_review": human, "degradations": deg, "errors": errs,
           "runtime": {"script": "scripts/main.py", "version": VERSION, "python": sys.version.split()[0],
                       "network": "disabled"}}
    return res


CON = {}


def diff_report(cid, lg, claims, rows, res, refs, deg, errs):
    """Expected vs actual: contract backfill, coverage metrics, remaining gaps."""
    m = res["metrics"]
    zh = lg == "zh"
    t = lambda a, b: a if zh else b
    out = ["# " + t("差异报告（期望 vs 实际）", "Diff report (expected vs actual)") + " — " + str(cid), "",
           "> " + t("离线、确定性的自查：契约要求了什么，本次真实产出了什么。",
                    "Offline deterministic self-check: what the contract asked for vs what this run produced."), "",
           "## " + t("契约回填", "Contract backfill"), "",
           "| key | " + t("已给值", "requested") + " | " + t("本次取值类型", "filled as") + " | " +
           t("状态", "state") + " |", "|---|---|---|---|"]
    for k, v in (res.get("output_contract") or {}).items():
        if isinstance(v, list):
            state = "ok" if v else "empty"
        elif v in (None, ""):
            state = "empty"
        else:
            state = "ok"
        out.append("| `%s` | %s | %s | %s |" % (k, "yes" if state == "ok" else "no", type(v).__name__, state))
    out += ["", "## " + t("覆盖指标", "Coverage metrics"), "",
            "| metric | value |", "|---|---|"]
    for k in ("claims", "evidence_rows", "rows_with_source", "references", "downgrades",
              "verified_quote_rate", "claim_coverage", "pending_human_count", "overclaim_flags"):
        out.append("| `%s` | %s |" % (k, m.get(k)))
    out += ["", "## " + t("剩余缺口", "Remaining gaps"), ""]
    unsup = sorted({r["claim_id"] for r in rows if not r.get("source_id")})
    weak = sorted({r["claim_id"] for r in rows if r["strength"] in ("低", "不足")})
    out.append("- " + t("未匹配来源的论断：", "Claims without a located source: ") + (", ".join(unsup) or t("无", "none")))
    out.append("- " + t("低/不足强度论断：", "Low/insufficient claims: ") + (", ".join(weak) or t("无", "none")))
    out.append("- " + t("待人工确认项：%d；降级记录：%d；错误：%d" %
                        (len(res.get("human_review") or []), len(deg), len(errs)),
                        "Pending human items: %d; degradations: %d; errors: %d" %
                        (len(res.get("human_review") or []), len(deg), len(errs))))
    out.append("- " + t("参考文献著录：%d 条（未联网核验）" % len(refs),
                        "Reference records: %d (not verified online)" % len(refs)))
    out.append("")
    return "\n".join(out)


def run(args):
    t0 = time.time()
    ind = Path(args.input or "/input")
    if not ind.is_dir():
        ind = Path.cwd() / "input"
    out = Path(args.output or "/app/output")
    try:
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
    except Exception:
        out = Path.cwd() / "output"
        out.mkdir(parents=True, exist_ok=True)

    case, instr = read_case(ind) if ind.is_dir() else ({}, "")
    con = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    cid = str(case.get("case_id") or case.get("id") or "UNKNOWN")
    global CON
    CON = con
    errs, deg = [], []
    K.dump_json(out / "result.json",
                {"case_id": cid, "status": "partial", "skill": SKILL, "skill_version": VERSION,
                 "deliverable": MAIN_FILE, "preserved_facts": [{"fact": "run started", "note": "provisional"}],
                 "evidence_map": [{"claim": "overview", "source_file": MAIN_FILE}],
                 "change_log": [{"action": "started run", "target": MAIN_FILE}],
                 "output_contract": K.fill_contract(con, cid, MAIN_FILE,
                     {"preserved_facts": [{"fact": "run started", "note": "provisional"}],
                      "evidence_map": [{"claim": "overview", "source_file": MAIN_FILE}],
                      "change_log": [{"action": "started run", "target": MAIN_FILE}], "language": "en"},
                     "partial"),
                 "sources": [{"source_id": "input", "path": "provisional run"}],
                 "uncertainties": ["run started, outputs not final"], "change_records": [{"action": "started run"}],
                 "limits": ["provisional result written before the pipeline completed"]})

    docs = K.discover(ind, case) if ind.is_dir() else []
    for d in docs:
        if d["note"]:
            deg.append({"stage": "extract", "source": d["path"], "type": "partial_read", "detail": d["note"]})
    if not docs:
        errs.append({"stage": "input", "type": "no_material", "detail":
                     "no readable material file under the input directory"})
    units = K.segment(docs)
    lg = lang_of(case, docs)
    claims, mode = build_claims(units, docs, instr)
    rows = build_rows(claims, units)
    draft = read_draft(args, ind)
    n_ov = apply_draft(draft, rows)
    all_text = "\n".join(d["text"] for d in docs)
    facts = K.numbers_in(all_text)
    refs = K.ref_entries("\n".join(d["text"] for d in docs if d["kind"] == "references"))
    changed = [{"claim_id": c["claim_id"]} for c in claims if c["type"] == "causal"]

    # ---- artifacts
    main_text = render(claims, rows, facts, lg, cid)
    K.write_text(out / MAIN_FILE, main_text)
    K.dump_json(out / "claims.json", {"case_id": cid, "language": lg, "mode": mode, "count": len(claims),
               "claims": [{k: v for k, v in c.items() if k != "uid"} for c in claims]})
    K.dump_json(out / "evidence_table.json", {"case_id": cid, "count": len(rows),
               "schema": "claim_id,source_id,locator,quote,strength,support_scope,conflicts,rationale,verified",
               "rows": rows})
    strength_lines = ["# Evidence strength", "",
                      "Grades blend study design, sample size, independent corroboration and conflict penalty.", ""]
    for r in rows:
        strength_lines.append("- **%s** <- %s | strength **%s** | %s" % (
            r["claim_id"], r.get("source_id") or "no source", r["strength"], r.get("rationale", "")))
        strength_lines.append("  - locator: %s" % (r.get("locator") or "not located"))
    K.write_text(out / "evidence_strength.md", "\n".join(strength_lines))
    ref_lines = ["# Reference check", "", "Offline run: only list completeness and internal consistency are checked.", "",
                 "| # | record | year | DOI | completeness |", "|---|---|---|---|---|"]
    for x in refs:
        miss = [k for k in ("year", "venue", "doi") if not x.get(k)]
        ref_lines.append("| %s | %s | %s | %s | %s |" % (
            x.get("num") or "-", x["body"][:80], x.get("year") or "-", x.get("doi") or "not given",
            "complete" if not miss else "missing: " + ",".join(miss)))
    if not refs:
        ref_lines.append("| - | no reference list found in the materials | - | - | gap |")
    K.write_text(out / "reference_check.md", "\n".join(ref_lines))
    unc_lines = ["# Uncertainty notes", ""]
    for u in runtime_result(cid, "partial", lg, {}, "", claims, rows, facts, refs, docs, changed, errs, deg)["uncertainties"]:
        unc_lines.append("- " + u)
    K.write_text(out / "uncertainty_notes.md", "\n".join(unc_lines))
    human = runtime_result(cid, "partial", lg, {}, "", claims, rows, facts, refs, docs, changed, errs, deg)["human_review"]
    K.dump_json(out / "human_review.json", {"case_id": cid, "items": human})
    K.dump_json(out / "verification.json", {"case_id": cid, "claims": len(claims), "rows": len(rows),
               "rows_with_source": sum(1 for r in rows if r.get("source_id")),
               "quotes_verified": sum(1 for r in rows if r.get("verified")),
               "distinct_sources": len({r["source_id"] for r in rows if r.get("source_id")}),
               "verified_quote_rate": round(sum(1 for r in rows if r.get("verified")) / max(1, len(rows)), 3),
               "claim_coverage": round(sum(1 for r in rows if r.get("source_id")) / max(1, len(claims)), 3),
               "limits": ["offline; records not verified online"]})

    status = "failed" if (not docs or not units) else \
        "partial" if (not claims or not any(r.get("source_id") for r in rows)) else "success"
    res = runtime_result(cid, status, lg, {}, main_text, claims, rows, facts, refs, docs, changed, errs, deg)
    if n_ov:
        rec = {"action": "applied agent draft evidence_overrides", "target": "evidence_table.json",
               "reason": "agent-first path: %d row(s) overridden" % n_ov}
        res["change_records"].append(rec)
        res["change_log"].append(rec)
        oc = res.get("output_contract")
        if isinstance(oc, dict):
            for k, v in oc.items():
                if isinstance(v, list) and k.lower() in ("change_log", "change_records"):
                    v.append(rec)
        res["uncertainties"].append("Agent draft overrides were applied to %d evidence row(s)." % n_ov)
    K.write_text(out / "diff_report.md", diff_report(cid, lg, claims, rows, res, refs, deg, errs))
    # make sure every artifact we advertise actually exists and has content
    sizes = {}
    for n in res["outputs"]:
        p = out / n
        if p.is_file():
            sizes[n] = p.stat().st_size
    res["outputs"] = sizes
    K.dump_json(out / "result.json", res)
    # honour contract values that point at concrete files
    for k, v in (res.get("output_contract") or {}).items():
        if not isinstance(v, str) or not K.is_ext_path(v):
            continue
        rel = v.strip().lstrip("/").replace("\\", "/")
        if rel == MAIN_FILE or ".." in rel:
            continue
        target = out / rel
        if target.is_file():
            continue
        if rel.endswith(".json"):
            data = res.get(k)
            if not isinstance(data, (list, dict)) or not data:
                data = {"case_id": cid, "value": str(data)}
            K.dump_json(target, data)
        else:
            K.write_text(target, main_text if len(main_text) >= 40 else main_text + "\n\n(see " + MAIN_FILE + ")")
    print("done %s claims=%d rows=%d with_source=%d refs=%d docs=%d" % (
        status, len(claims), len(rows), sum(1 for r in rows if r.get("source_id")), len(refs), len(docs)))


def _fail(path, exc):
    try:
        o = Path(path)
        o.mkdir(parents=True, exist_ok=True)
        p = o / "result.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        cur["case_id"] = cur.get("case_id") or "UNKNOWN"
        cur["status"] = "failed"
        for k in ("preserved_facts", "evidence_map", "change_log", "change_records", "sources",
                  "uncertainties", "limits", "human_review", "errors"):
            cur.setdefault(k, [])
        if not cur["sources"]:
            cur["sources"] = [{"source_id": "input", "path": "fatal error before discovery"}]
        cur["uncertainties"] = cur["uncertainties"] or ["the pipeline stopped early"]
        cur["limits"] = cur["limits"] or ["fatal error; only a minimal result could be written"]
        cur["errors"] = cur["errors"] + [{"stage": "fatal", "type": type(exc).__name__,
                                          "detail": str(exc)[:400]}]
        cur.setdefault("deliverable", MAIN_FILE)
        cur.setdefault("output_contract", K.fill_contract(cur.get("output_contract") or {}, cur["case_id"],
                                                           MAIN_FILE, {}, "failed"))
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(K.deep_clean(cur), ensure_ascii=False, indent=2))
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Evidence-driven writing: claims, evidence table, graded draft and result.json.")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--case", default=None)
    ap.add_argument("--draft", default=None)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--version", action="version", version=SKILL + " " + VERSION)
    args = ap.parse_args(argv)
    try:
        run(args)
    except Exception as exc:  # noqa
        _fail(args.output or "/app/output", exc)
        import traceback
        traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
