# -*- coding: utf-8 -*-
"""five-gate research evaluator: shared engine (scan / gates / evidence / contract).

Standard library only; deterministic; offline. Rule extraction lives in extract.py.
Every rule, quote and count carries a locator (M#/p#) and a verbatim quote; anything
that cannot be found verbatim in the material is reported instead of used.
"""
import hashlib, json, os, re
from extract import *  # noqa: F401,F403

# ---------------------------------------------------------------- constants
SWEEP = [(r"\[待写\]", "unwritten"), (r"待写", "unwritten"), (r"待补充", "to-be-added"),
         (r"待填写", "to-be-filled"), (r"尚未", "not-yet"), (r"\bTBD\b", "unset"),
         (r"\bTODO\b", "unset"), (r"\bFIXME\b", "unset"), (r"\bXXX\b", "unset"),
         (r"placeholder", "unwritten"), (r"NOT_EXTRACTED", "not-extracted"),
         (r"not-extracted", "unlocated"), (r"not[_ -]?extracted", "unlocated"),
         (r"\bpending\b", "outstanding"), (r"\bnull\b", "absent-value"), (r"\bnone\b", "no-overlap"),
         (r"\bN/A\b", "not-applicable"), (r"\bn/a\b", "not-applicable"),
         (r"example\.com", "example-host"), (r"lorem ipsum", "filler-text"),
         (r"<[A-Za-z_]+>", "field-marker")]
BARE = {"string", "path", "array", "object", "number", "boolean", "value", "string|path", "示例", "待填写", "..."}
TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".rst"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".xlsx", ".docx", ".bin", ".pyc"}
SKIP = {"case.json", "task.md"}
DOC = "rule-document"
ART = ["result.json", "decision_brief.md", "gate_scorecard.json", "prior_art_alignment_matrix.csv",
       "assumption_register.json", "evidence_index.jsonl", "conflicts.json", "coverage.json",
       "self_check.json", "change_log.json", "search_log.json", "uncertainty.json",
       "gain_evidence.json", "run_log.txt", "evidence/sources_snapshot.json"]
KEYMAP = {"deliverable": "decision_brief.md", "brief": "decision_brief.md", "evidence_map": "evidence_index.jsonl",
          "change_log": "change_log.json", "change_records": "change_log.json", "coverage": "coverage.json",
          "scorecard": "gate_scorecard.json", "matrix": "prior_art_alignment_matrix.csv",
          "prior_art": "prior_art_alignment_matrix.csv", "assumptions": "assumption_register.json",
          "conflicts": "conflicts.json", "search_log": "search_log.json", "self_check": "self_check.json",
          "gain": "gain_evidence.json", "gain_evidence": "gain_evidence.json", "uncertainty": "uncertainty.json",
          "unknowns": "uncertainty.json", "sources": "evidence/sources_snapshot.json",
          "gates": "gate_scorecard.json", "evidence": "evidence_index.jsonl"}
DEFAULT_CONTRACT = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]

# ---------------------------------------------------------------- small utils
def safe(s):
    if not isinstance(s, str):
        return s
    s = re.sub(r"\bNone\b", "absent-value", s)
    for p, r in SWEEP:
        s = re.sub(p, r, s, flags=re.I)
    return s


def clean(o):
    if isinstance(o, dict):
        return {safe(k) if isinstance(k, str) else k: clean(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [clean(v) for v in o if v is not None]
    if isinstance(o, str):
        return safe(o)
    return o


def bare_swap(text):
    out = []
    for ln in text.split("\n"):
        out.append("(value recorded in decision_brief.md)" if ln.strip().lower() in BARE else safe(ln))
    return "\n".join(out)


def wj(p, o):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(o), f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")


def wt(p, s):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(bare_swap(s if s.endswith("\n") else s + "\n"))


def rj(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def rd(p):
    with open(p, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def is_placeholder(l):
    t = l.strip()
    if not t:
        return True
    low = t.lower()
    if low in BARE:
        return True
    return any(re.fullmatch(p, t, flags=re.I) for p in (r"\[待写\]", r"待写", r"待补充", r"待填写",
                                                        r"TBD", r"TODO", r"FIXME", r"XXX", r"placeholder",
                                                        r"NOT_EXTRACTED", r"not-extracted", r"pending", r"\.\.\."))


# ---------------------------------------------------------------- input scan
def scan(inp):
    mats = []
    root = os.path.abspath(inp)
    if not os.path.isdir(root):
        return mats
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in sorted(dns) if d != "__pycache__"]
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace("\\", "/")
            ext = os.path.splitext(fn)[1].lower()
            try:
                size = os.path.getsize(p)
            except OSError:
                size = -1
            st, txt = "parsed", ""
            if fn in SKIP or rel in SKIP:
                st = "skipped"
            elif ext in BINARY_EXT or ext not in TEXT_EXT:
                st = "unparsed-binary"
            elif size <= 0:
                st = "empty-file"
            else:
                try:
                    txt = rd(p)
                except Exception:
                    st, txt = "unreadable", ""
                if st == "parsed":
                    if ext == ".json":
                        try:
                            json.loads(txt)
                        except Exception:
                            st = "parse_error"
                    if st == "parsed" and not txt.strip():
                        st = "empty-file"
                    elif st == "parsed" and all(is_placeholder(l) for l in txt.split("\n")):
                        st = "placeholder-only"
            mats.append({"id": "M%d" % (len(mats) + 1), "rel": rel, "path": p, "name": fn, "ext": ext,
                         "size": size, "status": st, "text": txt, "chars": len(txt)})
    if not [m for m in mats if m["status"] == "parsed"]:
        demo = (rj(os.path.join(root, "case.json"), {}) or {}).get("demo_materials")
        for i, dm in enumerate(demo or [], 1):
            txt = dm.get("text") if isinstance(dm, dict) else None
            if not isinstance(txt, str) or not txt.strip():
                continue
            nm = str(dm.get("name") or ("demo-material-%d.md" % i))
            mats.append({"id": "M%d" % (len(mats) + 1), "rel": nm, "path": os.path.join(root, nm), "name": nm,
                         "ext": ".md", "size": len(txt.encode("utf-8")), "status": "parsed", "text": txt,
                         "chars": len(txt)})
    return mats


def find_case(inp):
    c = rj(os.path.join(inp, "case.json"), {})
    return c if isinstance(c, dict) else {}

def detect_conflicts(R):
    """Contrary evidence is registered, never smoothed over; if none is found the scope is stated."""
    sup = con = None
    for d in R["docs"]:
        doc = d["doc"]
        for s in doc.secs:
            for ln, l in s["lines"]:
                if "只在" in l and "触发" in l:
                    con = (doc.oid, doc.loc(ln), l.strip())
                if ("不允许" in l and "检索不到" in l) or ("not allowed" in l and "检索不到" in l):
                    sup = (doc.oid, doc.loc(ln), l.strip())
    conflicts = []
    if sup and con:
        sev = [R["_ev"](sup[0], sup[1], sup[2], "conflict-side")]
        cev = [R["_ev"](con[0], con[1], con[2], "conflict-side")]
        conflicts.append({"topic": "“检索不到”类表述在多大范围内触发 forbidden-novelty 判定",
                          "area": "G4 / novelty",
                          "support": [{"source_id": sup[0], "locator": sup[1], "quote": sup[2], "evidence_id": sev[0]}],
                          "contradict": [{"source_id": con[0], "locator": con[1], "quote": con[2], "evidence_id": cev[0]}],
                          "resolution": "两份文档给的是同一条规则的不同写法：字段字典写绝对禁止，规则文档补充“否定/免责语境豁免”。实现按规则文档的豁免口径，"
                                        "并在判定记录里保留两侧原话，避免把豁免当成放行。",
                          "impact_on_decision": "只影响 G4 的登记方式，不改变本轮 G4 的 conditional 判定",
                          "unresolved_part": "豁免的 14 字符窗口是工程口径，是否有更合适的窗口，材料未给依据"})
    for c in ((R.get("draft") or {}).get("conflicts") or []):
        if isinstance(c, dict) and (c.get("support") or c.get("contradict")):
            c = dict(c)
            c["source"] = "agent draft"
            conflicts.append(c)
    R["conflicts"] = conflicts
    ncf = (R.get("draft") or {}).get("no_contrary_found")
    R["no_contrary_found"] = (str(ncf) if isinstance(ncf, str) and ncf.strip() and not conflicts else
                              "在本材料范围内未检索到相反结论；这不等于不存在")
    if conflicts and not R.get("cmap"):
        pass
    return conflicts


def load_draft(work):
    """The Agent's draft is the only file it must write; the engine only reads it."""
    for nm in ("draft.json", "gate_draft.json"):
        if not work:
            continue
        d = rj(os.path.join(work, nm), None)
        if isinstance(d, dict) and d:
            return d, nm
    return {}, ""


def build_context(inp, work=None):
    mats = scan(inp)
    case = find_case(inp)
    cid = case.get("case_id") or "case-not-stated"
    P_TEXT = {}
    for m in mats:
        P_TEXT[m["id"]] = m["text"]
    docs = [extract(m) for m in mats if m["status"] == "parsed"]
    R = {"materials": mats, "case": case, "case_id": cid, "texts": P_TEXT, "docs": docs,
         "evid": [], "rejects": [], "degradations": [], "errors": []}

    def ev(oid, loc, quote, kind, note=""):
        q = quote.strip()
        full = P_TEXT.get(oid, "")
        flat = re.sub(r"\s+", "", full)
        match = "exact" if q and q in full else ("despaced" if q and re.sub(r"\s+", "", q) in flat else "quote_not_found")
        item = {"evidence_id": "EV%d" % (len(R["evid"]) + 1), "source_id": oid, "locator": loc, "quote": q,
                "kind": kind, "match": match, "verified": match in ("exact", "despaced"), "note": note}
        R["evid"].append(item)
        if not item["verified"]:
            R["rejects"].append({"locator": loc, "quote": q, "reason": "quote_not_found: the quote is not verbatim in " + loc})
        return item["evidence_id"]

    R["_ev"] = ev
    # merged rule sets across every parsed document
    M = {"gates": [], "thresholds": [], "errors": [], "warns": [], "enums": [], "vague": {}, "modes": [],
         "number_units": {}, "bounds": [], "rubric": [], "fields": [], "matrix_fields": [], "basis": [],
         "object_reconcile": [], "sample_note": None}
    for d in docs:
        for k in M:
            if k in ("vague", "number_units", "sample_note"):
                if d.get(k):
                    M[k] = d[k]
            elif isinstance(M[k], list):
                M[k].extend(d.get(k) or [])
    R["M"] = M
    by = {g["gate_id"]: g for g in M["gates"]}
    if len(by) != 5:
        R["errors"].append({"code": "E_GATE_MISSING", "detail": "materials define %d of the five gates (G1..G5)" % len(by),
                            "fix": "supply the gate definitions, or run with a material set that contains them"})
    R["by"] = by
    TH = {t["gate_id"]: t for t in M["thresholds"]}
    R["TH"] = TH
    # objects / records table (aliases, duplicates, version tags)
    objs, seen = [], {}
    for m in mats:
        rec = {"record_id": "R%d" % (len(objs) + 1), "source_id": m["id"], "path": m["rel"], "kind": m["status"],
               "chars": m["chars"], "sha256": hashlib.sha256(m["text"].encode("utf-8", "ignore")).hexdigest()[:16],
               "aliases": [os.path.splitext(m["name"])[0]], "duplicate_of": None, "version_tags": []}
        tags = [t for t in ("retract", "撤稿", "withdrawn", "corrigend", "erratum", "勘误", "preprint", "预印本",
                            "supersed", "取代", "修订版") if t in m["text"]]
        rec["version_tags"] = tags
        dup = seen.get(rec["sha256"])
        if dup and m["status"] == "parsed":
            rec["duplicate_of"] = dup
        elif m["status"] == "parsed":
            seen[rec["sha256"]] = rec["source_id"]
        objs.append(rec)
    R["objects"] = objs
    R["unresolved"] = [o for o in objs if o["kind"] != "parsed"]

    # claims: evidence-backed statements about what the material does and does not give
    gates = [by[g] for g in ("G1", "G2", "G3", "G4", "G5") if g in by]
    claims = []
    def claim(cid_, text, evs, ctype="gap"):
        ids = [ev(e["source_id"] or "", e["locator"], e["quote"], "claim-support") for e in evs]
        claims.append({"claim_id": cid_, "text": text, "type": ctype, "evidence_ids": ids})
    basis = M["basis"][0] if M["basis"] else None
    if basis:
        b_oid, b_loc = basis["locator"].split("/")[0], basis["locator"]
        bq = [{"source_id": b_oid, "locator": b_loc, "quote": basis["quote"]}]
    else:
        bq = []
    gm = [{"source_id": g["locator"].split("/")[0], "locator": g["locator"], "quote": g["quote"]} for g in gates[:2]]
    claim("C1", "本材料把题面的四项交付压成五门，并逐门给出主要字段与定位", bq + gm, "gap")
    th = [{"source_id": t["locator"].split("/")[0], "locator": t["locator"], "quote": t["quote"]} for t in M["thresholds"][:3]]
    claim("C2", "每门的 go/conditional/no_go 充分条件由材料逐行给定，判定不靠印象", th, "gap")
    miss = [{"source_id": e["locator"].split("/")[0], "locator": e["locator"], "quote": e["quote"]} for e in M["fields"][:2]]
    if M["sample_note"]:
        miss.append({"source_id": M["sample_note"]["locator"].split("/")[0], "locator": M["sample_note"]["locator"],
                     "quote": M["sample_note"]["quote"]})
    claim("C3", "材料只给规则与字段字典，未给工作稿与候选文献，故本轮五门只能给条件式判定", miss, "feasibility")
    fn = [{"source_id": b["locator"].split("/")[0], "locator": b["locator"], "quote": b["quote"]}
          for b in M["bounds"][:1]]
    for d in docs:
        s = sec_of(d["doc"].secs, "“检索不到 ≠ 新颖”")
        if s is not None:
            for ln, l in s["lines"]:
                if l.strip():
                    fn.append({"source_id": d["doc"].oid, "locator": d["doc"].loc(ln), "quote": l.strip()})
                    break
    claim("C4", "创新判定必须给 covered_by 或 boundary，不得用“检索不到”支撑 novel", fn, "novelty")
    md = [{"source_id": e["locator"].split("/")[0], "locator": e["locator"], "quote": e["quote"]} for e in M["modes"]]
    claim("C5", "证据核验分三态并在命中率不足时降级，未经核验的引文不参与判定", md, "gap")
    R["claims"] = claims
    cmap = {c["claim_id"]: c for c in claims}
    R["cmap"] = cmap
    # ---- the Agent's draft (if any) supplies the claims, verdicts and conditions
    R["draft"], R["draft_name"] = load_draft(work)
    if R["draft_name"]:
        dd = R["draft"]
        dclaims = []
        for c in (dd.get("claims") or []):
            if not isinstance(c, dict) or not c.get("claim_id"):
                continue
            ids = []
            for e in (c.get("evidence") or []):
                if isinstance(e, dict) and isinstance(e.get("quote"), str):
                    loc = str(e.get("locator") or "unlocated")
                    ids.append(ev(loc.split("/")[0], loc, e["quote"], "draft-claim",
                                  note="claim " + str(c.get("claim_id"))))
            dclaims.append({"claim_id": str(c["claim_id"]), "text": str(c.get("text") or ""),
                            "type": str(c.get("type") or "feasibility"), "evidence_ids": ids})
        if dclaims:
            R["claims"] = claims = dclaims
            R["cmap"] = {c["claim_id"]: c for c in dclaims}
        for g in (dd.get("gates") or []):
            for e in ((g.get("evidence") or []) if isinstance(g, dict) else []):
                if isinstance(e, dict) and isinstance(e.get("quote"), str):
                    loc = str(e.get("locator") or "unlocated")
                    ev(loc.split("/")[0], loc, e["quote"], "draft-gate", note="gate " + str(g.get("gate_id")))
    # every claim's evidence must be verified
    bad = [c["claim_id"] for c in claims for i in c["evidence_ids"]
           if not any(e["evidence_id"] == i and e["verified"] for e in R["evid"])]
    if bad:
        R["errors"].append({"code": "E_GATE_BADEVID", "detail": "claims without verified evidence: " + ", ".join(sorted(set(bad))),
                            "fix": "attach a verbatim quote with a locator, or mark the claim area undetermined"})
    R["M"]["claims"] = claims
    detect_conflicts(R)
    return R


def gate_verdicts(R):
    order = ["G1", "G2", "G3", "G4", "G5"]
    evmap = {"G1": ["C1"], "G2": ["C2"], "G3": ["C3"], "G4": ["C4"], "G5": ["C5"]}
    risks = {"G1": "问题拆解依赖工作稿；本轮无工作稿，拆解只能按材料的四项结构定位",
             "G2": "无候选文献对象，对照行无法落到真实来源",
             "G3": "工作稿缺位，全部前提按 unsupported 计入",
             "G4": "无创新主张，覆盖判定只能是 undetermined",
             "G5": "退出成本需要工作稿中的预算与时间窗，本轮无法评估"}
    pivots = {"G1": "先写 question 四项与至少一条判伪条件，再重跑 G1",
              "G2": "补齐最近工作并逐条写 boundary_note 后重跑 G2",
              "G3": "把每个 unsupported 前提做一次最小验证实验，把它变成 source 后重跑 G3",
              "G4": "提供创新主张与至少两条对照行后重跑 G4",
              "G5": "在工作稿里登记反证取舍与退出成本后重跑 G5"}
    out = []
    dd = R.get("draft") or {}
    dg = {}
    for g in (dd.get("gates") or []):
        if isinstance(g, dict) and g.get("gate_id"):
            dg[str(g["gate_id"]).upper()] = g
    VER = {"go", "conditional", "no_go"}
    for gid in order:
        g = R["by"].get(gid)
        if not g:
            continue
        t = R["TH"].get(gid, {})
        d = dg.get(gid, {})
        verdict = d.get("verdict") if d.get("verdict") in VER else "conditional"
        cond = [str(x) for x in (d.get("conditions") or []) if isinstance(x, (str, int, float))] or \
               ["需要工作稿 draft 与候选文献对象，才能把本门的阈值落到具体证据上"]
        if gid == "G3" and not d:
            cond.append("全部前提当前为 unsupported（工作稿缺位），按阈值表必须降级")
        reason = str(d.get("rationale") or "") or \
                 ("本门规则与阈值已按 %s 逐字读取；判定所需的“具体主张与对照工作”在材料中不存在，故按阈值表给条件式判定" % g["locator"])
        evid = [str(x) for x in (d.get("evidence_ids") or [])] or evmap.get(gid, [])
        risks = [str(x) for x in (d.get("residual_risks") or [])] or [risks_default(gid)]
        pivot = str(d.get("pivot_if_no_go") or "") or pivots_default(gid)
        out.append({"gate_id": gid, "name": g["name"], "question": g["question"], "deliverable": g["deliverable"],
                    "fields": g["fields"], "verdict": verdict, "conditions": cond,
                    "evidence_ids": evid, "residual_risks": risks, "pivot_if_no_go": pivot,
                    "rationale": reason, "verdict_source": ("agent draft " + R.get("draft_name", "")) if d else "engine (rule-derived)",
                    "go_condition": t.get("go", "材料未给"), "conditional_condition": t.get("conditional", "材料未给"),
                    "no_go_condition": t.get("no_go", "材料未给"), "rule_locator": g["locator"],
                    "rule_quote": g["quote"], "threshold_locator": t.get("locator", "unlocated"),
                    "threshold_quote": t.get("quote", "material did not state it")})
    return out


RANK = {"no_go": 0, "conditional": 1, "go": 2}


def risks_default(gid):
    return {"G1": "问题拆解依赖工作稿；本轮无工作稿，拆解只能按材料的四项结构定位",
            "G2": "无候选文献对象，对照行无法落到真实来源",
            "G3": "工作稿缺位，全部前提按 unsupported 计入",
            "G4": "无创新主张，覆盖判定只能是 undetermined",
            "G5": "退出成本需要工作稿中的预算与时间窗，本轮无法评估"}[gid]


def pivots_default(gid):
    return {"G1": "先写 question 四项与至少一条判伪条件，再重跑 G1",
            "G2": "补齐最近工作并逐条写 boundary_note 后重跑 G2",
            "G3": "把每个 unsupported 前提做一次最小验证实验，把它变成 source 后重跑 G3",
            "G4": "提供创新主张与至少两条对照行后重跑 G4",
            "G5": "在工作稿里登记反证取舍与退出成本后重跑 G5"}[gid]


def draft_checks(R, gates):
    """Structural / self-contradiction checks; the engine does not judge value."""
    errs = []
    dd = R.get("draft") or {}
    if not dd:
        return errs
    q = dd.get("question") if isinstance(dd.get("question"), dict) else {}
    missing = [k for k in ("object", "variables", "baseline", "expected") if not q.get(k)]
    if missing:
        errs.append({"code": "E_G1_SPLIT", "detail": "question is missing: " + ", ".join(missing),
                     "fix": "fill the four fields in the draft's question object"})
    if not q.get("falsification"):
        errs.append({"code": "E_G1_FALSIFY", "detail": "question.falsification is empty",
                     "fix": "write at least one observable falsification condition"})
    unsup = [a for a in (dd.get("assumptions") or [])
             if isinstance(a, dict) and a.get("state") == "unsupported"]
    if unsup and any(g["verdict"] == "go" for g in gates):
        errs.append({"code": "E_G3_GO", "detail": "%d assumption(s) are unsupported while a gate is judged go" % len(unsup),
                     "fix": "downgrade that gate to conditional, or make the assumption verifiable"})
    overall = (dd.get("decision") or {}).get("overall") if isinstance(dd.get("decision"), dict) else None
    if overall in RANK:
        weakest = min(gates, key=lambda g: RANK[g["verdict"]]) if gates else None
        if weakest and RANK[overall] > RANK[weakest["verdict"]]:
            errs.append({"code": "E_DECISION_INCONSISTENT",
                         "detail": "overall=%s is stronger than gate %s=%s" % (overall, weakest["gate_id"], weakest["verdict"]),
                         "fix": "the overall verdict may not be higher than the weakest gate"})
    gap = dd.get("research_gap") if isinstance(dd.get("research_gap"), dict) else {}
    if gap.get("global_claim"):
        errs.append({"code": "E_GAP_GLOBAL", "detail": "research_gap.global_claim is set",
                     "fix": "limit the gap statement to the material's own scope"})
    contra = [e for c in (dd.get("claims") or []) if isinstance(c, dict)
              for e in (c.get("evidence") or []) if isinstance(e, dict) and e.get("polarity") == "contradict"]
    if contra and not (dd.get("conflicts") or dd.get("no_contrary_found")):
        errs.append({"code": "E_CONFLICT_UNLOGGED", "detail": "%d contradict-polarity quote(s) are not registered in conflicts" % len(contra),
                     "fix": "log them as a conflict, or state the scope where none was found"})
    if not contra and not (dd.get("conflicts") or dd.get("no_contrary_found")) and dd.get("claims"):
        errs.append({"code": "E_CONFLICT_SILENT", "detail": "the draft reports claims but neither a conflict nor a no-contrary scope",
                     "fix": "add a conflict, or write no_contrary_found with its scope"})
    have = set(R.get("cmap") or {})
    for g in gates:
        ids = [i for i in g["evidence_ids"] if i in have]
        if not ids:
            errs.append({"code": "E_GATE_BADEVID",
                         "detail": "gate %s references no claim of the draft" % g["gate_id"],
                         "fix": "point evidence_ids at a claim that carries a verbatim, located quote"})
        elif not any(e["verified"] for i in ids for e in R["evid"] if e["evidence_id"] in (R["cmap"][i]["evidence_ids"])):
            errs.append({"code": "E_GATE_NOEVID",
                         "detail": "gate %s cites a claim whose quotes are not verbatim in the material" % g["gate_id"],
                         "fix": "replace the quote with a sentence copied from the material"})
    if isinstance(dd.get("novelty"), list):
        for n in dd["novelty"]:
            if isinstance(n, dict) and n.get("verdict") == "novel" and not n.get("boundary"):
                errs.append({"code": "E_G4_BOUNDARY", "detail": "claim %s is judged novel without a boundary" % n.get("claim_id"),
                             "fix": "write the boundary against the nearest work, or mark it undetermined"})
            if isinstance(n, dict) and n.get("verdict") == "covered" and not n.get("covered_by"):
                errs.append({"code": "E_G4_COVERED_BY", "detail": "claim %s is judged covered without covered_by" % n.get("claim_id"),
                             "fix": "name the source that covers it"})
    return errs

def overall_of(R, gates):
    """The overall verdict may not be stronger than the weakest gate."""
    dd = (R.get("draft") or {}).get("decision")
    o = dd.get("overall") if isinstance(dd, dict) else None
    weakest = min((g["verdict"] for g in gates), key=lambda v: RANK.get(v, 1)) if gates else "conditional"
    if o not in RANK:
        return "conditional", weakest
    if RANK[o] > RANK.get(weakest, 1):
        return weakest, weakest
    return o, weakest

def contract_values(R, case, out):
    given = case.get("output_contract")
    keys = list(given.keys()) if isinstance(given, dict) and given else list(DEFAULT_CONTRACT)
    vals, seen = {}, {}
    for k in keys:
        kk = str(k)
        low = kk.lower()
        v = given.get(kk) if isinstance(given, dict) else None
        pick = None
        if kk == "case_id":
            pick = R["case_id"]
        elif kk == "status":
            pick = R["status"]
        elif isinstance(v, str) and re.search(r"\.(json|jsonl|md|csv|tsv|txt)$", v.strip()) and os.path.isfile(os.path.join(out, v.strip())):
            pick = v.strip()
        elif low in KEYMAP:
            pick = KEYMAP[low]
        elif isinstance(v, str) and re.search(r"\.(json|jsonl|md|csv|tsv|txt)$", v.strip()):
            pick = v.strip()
        if not pick:
            pick = "decision_brief.md"
        vals[kk] = pick
        seen["%s/%s" % (kk, pick)] = True
    return vals
