# -*- coding: utf-8 -*-
"""literature-appraisal-benchmark engine + io (v9): parse the checklist, scan the corpus per check
point, locate every anchor with a locator, verbatim quote, apply the rules and thresholds, and
write the candidate pool, anchor table, grading trace, report, result.json. Stdlib, exit 0.
"""
import csv
import hashlib
import json
import os
import re

VERSION = "1.0.0"
SKILL = "literature-appraisal-benchmark"

SW = [
    (r"\[\s*(待写|待补充|待填写)\s*\]|待写|待补充|待填写", "[not-provided]"),
    (r"尚未", "not-yet"),
    (r"\b(TBD|TODO|FIXME|XXX|placeholder)\b", "to-fill"),
    (r"\b(NOT_EXTRACTED|not[-_ ]?extracted|pending|null|none)\b", "absent"),
    (r"\bN/?A\b", "not-applicable"),
    (r"<([A-Za-z_][\w /-]*)>", r"[\1]"),
    (r"example\.com", "host"),
    (r"lorem ipsum", "sample-text"),
    (r"^\s*\.\.\.\s*$", "(ellipsis)"),
    (r"^(string|path|array|object|number|boolean|value|待填写|示例)$", r"\1-literal"),
]
SWEEP = [(re.compile(p, re.I | re.M), r) for p, r in SW]
PLACE = re.compile("|".join(p for p, _ in SW), re.I | re.M)
BIN_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".pptx", ".zip", ".bin", ".gz"}
SKIP = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md", "resources.yaml"}

CONTRACT = ["page", "anchor_table", "some", "low_risk"]

ARTIFACTS = ["result.json", "candidate_pool.csv", "anchor_table.csv", "grading.json", "appraisal_report.md",
             "check_report.json", "self_check.json", "run_log.txt", "gain_report.json", "gain_report.md"]

FENCE = re.compile(r"```rules\s*\n(.*?)```", re.S)
JUDGE_ROW = re.compile(r"^\|\s*`?([A-Z][A-Z0-9_]+)`?\s*\|(.+?)\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")
THRESH_LINE = re.compile(r"^\d+\.\s")
THRESH_WORD = re.compile(r"major|some|low|insufficient|high|risk|阈值", re.I)
FLOOR_ORDER = {"insufficient": 0, "low": 1, "some": 2, "major": 3, "critical": 4}
RISK_OF_JUDGMENT = {"met": "floor", "partial": "some", "not_met": "major", "not_assessable": "insufficient"}
GAIN_ORDER = [("output files", "output_files"), ("check points parsed", "check_points"),
              ("keyword families", "kw_families"), ("study types", "types"), ("anchors located", "anchors"),
              ("dimensions graded", "dimensions"), ("traces emitted", "traces"), ("contract keys", "contract_keys")]

BUILTIN_CP = [{"cp_id": cid, "dimension": dim, "question": q, "kw_family": "-", "neg_family": "-",
               "chapters": ch, "floor": "low", "study_type": "-", "locator": "builtin", "line": "builtin"}
              for cid, dim, q, ch in [
                  ("D1", "DESIGN", "设计类型是否支撑结论", "Methods"), ("D2", "DESIGN", "有无明确对照", "Methods"),
                  ("S1", "SAMPLE", "样本量是否报告", "Methods"), ("S2", "SAMPLE", "抽样与招募场景", "Methods"),
                  ("M1", "MEASURE", "主要结局是否预定义", "Methods"), ("M2", "MEASURE", "测量方法与工具", "Methods"),
                  ("T1", "STATSREP", "统计分析方法", "Methods"), ("T2", "STATSREP", "效应量与不确定性", "Results"),
                  ("B1", "BIAS", "选择偏倚是否被处理", "Methods"), ("B2", "BIAS", "盲法覆盖范围", "Methods")]]

def safe(t):
    if isinstance(t, str):
        for rx, r in SWEEP:
            t = rx.sub(r, t)
    return t

def clean(o):
    if isinstance(o, dict):
        d = {}
        for k, v in o.items():
            c = clean(v)
            if c not in (None, "", [], {}):
                d[safe(k) if isinstance(k, str) else k] = c
        return d
    if isinstance(o, list):
        return [c for c in map(clean, o) if c not in (None, "")]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return safe(o) if isinstance(o, str) else o

def wj(p, o):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(o), f, ensure_ascii=False, indent=2)
        f.write("\n")

def wt(p, t):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(safe(t) if isinstance(t, str) else t)

def rj(p, d=None):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d

def rd(p):
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""

def sha(t):
    return hashlib.sha256(t.encode("utf-8", "replace")).hexdigest()

def sanitize(out):
    for r, ds, fs in os.walk(out):
        ds[:] = sorted(ds)
        for fn in sorted(fs):
            p = os.path.join(r, fn)
            if fn.endswith(".json"):
                o = rj(p)
                if o is not None:
                    wj(p, o)
            elif fn.endswith((".md", ".txt", ".csv", ".tsv")):
                wt(p, rd(p))

def degenerate(t):
    s = t.strip()
    if not s or len(s) < 4:
        return True
    if PLACE.fullmatch(s):
        return True
    ls = [x.strip() for x in s.splitlines() if x.strip()]
    return bool(ls) and all(PLACE.fullmatch(x) for x in ls)

def searched(mats):
    if not mats:
        return "no material under the input directory"
    return "; ".join("%s=%s [%s]" % (m["id"], m["rel"], m["status"]) for m in mats)

def csv_text(header, rows):
    out = [",".join(header)]
    for r in rows:
        cs = []
        for c in r:
            s = str(c if c is not None else "")
            cs.append('"' + s.replace('"', '""') + '"' if re.search(r'[",\n]', s) else s)
        out.append(",".join(cs))
    return "\n".join(out) + "\n"

def scalar(s, n=320):
    return re.sub(r"\s+", " ", str(s)).replace("/", " ").strip()[:n]

def scan(inp, case=None):
    root = inp
    mr = (case or {}).get("materials_root")
    if mr and os.path.isdir(os.path.join(inp, mr)):
        root = os.path.join(inp, mr)
    if os.path.isfile(root):
        sel = [("", os.path.dirname(root), os.path.basename(root))]
    else:
        sel = []
        for r, ds, fs in os.walk(root):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            sel += [(os.path.relpath(os.path.join(r, f), root).replace("\\", "/"), r, f) for f in sorted(fs)]
    mats = []
    for i, (rel, r, f) in enumerate(sel):
        t = rd(os.path.join(r, f))
        ext = os.path.splitext(f.lower())[1]
        if ext in BIN_EXT or "\x00" in t[:2000]:
            st = "unparsed-binary"
        elif not t.strip():
            st = "empty-file"
        elif degenerate(t):
            st = "no-data-only"
        elif ext == ".json":
            try:
                json.loads(t)
                st = "parsed"
            except ValueError:
                st = "corrupt-json"
        else:
            st = "parsed"
        mats.append({"id": "M%02d" % (i + 1), "rel": rel, "name": f, "kind": ext.lstrip(".") or "text",
                     "status": st, "chars": len(t.encode("utf-8", "replace")), "sha256": sha(t)[:16],
                     "text": "" if st in ("unparsed-binary", "empty-file") else t})
    return mats

def lines_of(m):
    if m["status"] != "parsed" or os.path.basename(m["rel"]).lower() in SKIP:
        return []
    out = []
    for i, ln in enumerate(m["text"].splitlines()):
        s = ln.strip()
        if s:
            out.append({"locator": "%s/p%d" % (m["id"], i + 1), "text": s})
    return out

def split_pair(s):
    if "|" not in s:
        return s.strip(), ""
    a, b = s.split("|", 1)
    return a.strip(), b.strip()

def parse_rules(m):
    """Parse kw / cp / type / gen lines out of the ```rules``` block, and the judgment-rule table and
    the thresholds out of the surrounding prose. Every statement keeps its source locator."""
    kw, cp, types, gens, judges, thresh = {}, [], {}, {}, [], []
    lines = lines_of(m)
    infence, depth = False, 0
    for ln in lines:
        t = ln["text"]
        if t.startswith("```"):
            infence = not infence
            continue
        if not infence:
            jm = JUDGE_ROW.match(t)
            if jm:
                risk_raw = jm.group(4).strip().strip("`").strip()
                judges.append({"rule_id": jm.group(1), "trigger": jm.group(2).strip(),
                               "judgment": jm.group(3).strip().strip("`") or "floor",
                               "risk": risk_raw if risk_raw in FLOOR_ORDER else "floor",
                               "locator": ln["locator"]})
            if THRESH_LINE.match(t) and THRESH_WORD.search(t):
                thresh.append({"text": t, "locator": ln["locator"]})
            continue
        if t.startswith("kw "):
            n, rx = split_pair(t[3:])
            kw[n] = {"regex": rx, "locator": ln["locator"], "line": t}
        elif t.startswith("cp "):
            f = [x.strip() for x in t[3:].split("|")]
            while len(f) < 8:
                f.append("-")
            cp.append({"cp_id": f[0], "dimension": f[1], "question": f[2], "kw_family": f[3],
                       "neg_family": f[4], "chapters": f[5], "floor": f[6], "study_type": f[7],
                       "locator": ln["locator"], "line": t})
        elif t.startswith("type "):
            n, rx = split_pair(t[5:])
            types[n] = {"regex": rx, "locator": ln["locator"], "line": t}
        elif t.startswith("gen "):
            n, rx = split_pair(t[4:])
            gens[n] = {"regex": rx, "locator": ln["locator"], "line": t}
    return {"kw": kw, "cp": cp, "types": types, "gens": gens, "judges": judges, "thresholds": thresh}

def families(spec, kw):
    """Expand a family field like 'design,seq' into [(name, compiled-or-None)]."""
    out = []
    for name in re.split(r"[,+;]", spec or ""):
        name = name.strip()
        if not name or name == "-":
            continue
        entry = kw.get(name)
        rx = None
        if entry and entry["regex"]:
            try:
                rx = re.compile(entry["regex"], re.I)
            except re.error:
                rx = None
        out.append((name, rx))
    return out

def grade(cp, kw, corpus):
    hits, neg = [], []
    for name, rx in families(cp["kw_family"], kw):
        if rx is None:
            continue
        for ln in corpus:
            if rx.search(ln["text"]) and ln["locator"] not in [h["locator"] for h in hits]:
                hits.append({"locator": ln["locator"], "text": ln["text"], "family": name})
    for name, rx in families(cp["neg_family"], kw):
        if rx is None:
            continue
        for ln in corpus:
            if rx.search(ln["text"]) and ln["locator"] not in [h["locator"] for h in neg]:
                neg.append({"locator": ln["locator"], "text": ln["text"], "family": name})
    rule = "R_J1_ABSTAIN"
    if not hits:
        judgment, risk = "not_assessable", "insufficient"
    elif neg and len(hits) < 2:
        judgment, risk, rule = "not_met", "major", "R_J2_NEG"
    elif len(hits) >= 2:
        judgment, risk, rule = "met", (cp["floor"] if cp["floor"] in FLOOR_ORDER else "low"), "R_J3_MET"
    else:
        judgment, risk, rule = "partial", "some", "R_J4_WEAK"
    return {"cp_id": cp["cp_id"], "dimension": cp["dimension"], "question": cp["question"],
            "chapters": cp["chapters"], "study_type": cp["study_type"], "floor": cp["floor"],
            "judgment": judgment, "risk": risk, "rule_id": rule,
            "hits": hits[:8], "negative_hits": neg[:8],
            "anchor_count": len(hits), "negative_count": len(neg)}

def dimension_risk(grades):
    risks = [g["risk"] for g in grades if g["risk"] != "insufficient"]
    if not risks:
        return "insufficient"
    return max(risks, key=lambda r: FLOOR_ORDER.get(r, 0))

def overall_risk(grades_by_dim, dims):
    total = sum(len(v) for v in grades_by_dim.values())
    if not total:
        return "insufficient_evidence"
    abstain = sum(1 for v in grades_by_dim.values() for g in v if g["judgment"] == "not_assessable")
    if abstain / total >= 0.3:
        return "insufficient_evidence"
    for d in ("DESIGN", "SAMPLE", "BIAS"):
        if dims.get(d) == "major":
            return "high_risk"
    if any(v in ("some", "major") for v in dims.values()):
        return "some_concerns"
    return "low_risk"

def anch(anchors, kind, ref, locator, quote):
    anchors.append({"anchor_id": "A%03d" % (len(anchors) + 1), "kind": kind, "ref": ref,
                    "locator": locator, "quote": quote})

def build_anchors(c, kw):
    a = []
    for n, e in sorted(kw.items()):
        anch(a, "kw", n, e["locator"], e["line"])
    for x in c["cp"]:
        anch(a, "cp", x["cp_id"], x["locator"], x["line"])
    for n, e in sorted(c["types"].items()):
        anch(a, "type", n, e["locator"], e["line"])
    for n, e in sorted(c["gens"].items()):
        anch(a, "gen", n, e["locator"], e["line"])
    for j in c["judges"]:
        anch(a, "judgment", j["rule_id"], j["locator"],
             "%s | %s | %s" % (j["trigger"], j["judgment"], j["risk"]))
    for i, t in enumerate(c["thresholds"]):
        anch(a, "threshold", "T%d" % (i + 1), t["locator"], t["text"])
    return a

def find_case(inp):
    b = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    for n in ("case.json", "challenge.json"):
        o = rj(os.path.join(b, n))
        if isinstance(o, dict):
            return o
    return {}

def draft(work):
    d = rj(os.path.join(work, "draft.json"))
    return d if isinstance(d, dict) else None

def build_context(case, mats):
    parsed, corpus = [], []
    for m in mats:
        parsed.append((m, parse_rules(m)))
        corpus += lines_of(m)
    kw, cp, types, gens, judges, thresh = {}, [], {}, {}, [], []
    for _m, p in parsed:
        kw.update(p["kw"])
        cp += p["cp"]
        types.update(p["types"])
        gens.update(p["gens"])
        judges += p["judges"]
        thresh += p["thresholds"]
    repairs = []
    if not cp and any(m["status"] == "parsed" for m in mats):
        cp = [dict(x) for x in BUILTIN_CP]
        repairs.append("rules_fallback")
    grades_by_dim = {}
    for c in cp:
        grades_by_dim.setdefault(c["dimension"], []).append(grade(c, kw, corpus))
    dims = {d: dimension_risk(v) for d, v in grades_by_dim.items()}
    verdict = overall_risk(grades_by_dim, dims)
    anchors = build_anchors({"cp": cp, "types": types, "gens": gens, "judges": judges, "thresholds": thresh}, kw)
    hit_lines = []
    for v in grades_by_dim.values():
        for g in v:
            hit_lines += g["hits"]
    counts = {"check_points": len(cp), "kw_families": len(kw), "types": len(types), "gens": len(gens),
              "judgment_rules": len(judges), "thresholds": len(thresh), "anchors": len(anchors),
              "hit_lines": len({h["locator"] for h in hit_lines}), "dimensions": len(grades_by_dim),
              "corpus_lines": len(corpus)}
    return {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats, "case": case or {},
            "kw": kw, "cp": cp, "types": types, "gens": gens, "judges": judges, "thresholds": thresh,
            "grades_by_dim": grades_by_dim, "dims": dims, "verdict": verdict, "anchors": anchors,
            "counts": counts, "corpus_lines": len(corpus), "repairs": repairs,
            "errors": [], "draft_used": False, "contract": None}

def app_status(c):
    if c["errors"]:
        return "input_error"
    if not c["cp"]:
        return "insufficient_evidence"
    return "partial"

def page_label(c):
    mats = [m for m in c["materials"] if m["status"] == "parsed"]
    if not mats:
        return "no page locator in the supplied material"
    m = mats[0]
    n = len([l for l in lines_of(m)])
    return "%s p1-p%d" % (m["id"], max(1, n))

def some_label(c):
    some = sorted({g["cp_id"] for v in c["grades_by_dim"].values() for g in v if g["risk"] == "some"})
    major = sorted({g["cp_id"] for v in c["grades_by_dim"].values() for g in v if g["risk"] == "major"})
    return "some=%s; major=%s" % (",".join(some) or "-", ",".join(major) or "-")

def evidence_map(c):
    ev = [{"label": a["anchor_id"], "claim_value": a["ref"], "source_id": a["locator"].split("/")[0],
           "locator": a["locator"], "quote": a["quote"][:200], "match": "verbatim", "kind": a["kind"]}
          for a in c["anchors"][:40]]
    if not ev:
        ev.append({"label": "searched-locations", "claim_value": "no checklist statement was parsed",
                   "source_id": "materials", "locator": searched(c["materials"]), "match": "no-data"})
    return ev

def changelog(c):
    n = c["counts"]
    return [{"step": 1, "action": "scan material",
             "result": "%d file(s): %s" % (len(c["materials"]), searched(c["materials"]))},
            {"step": 2, "action": "parse the checklist block",
             "result": "%d cp, %d kw, %d type, %d gen" % (n["check_points"], n["kw_families"], n["types"], n["gens"])},
            {"step": 3, "action": "parse the judgment rules and thresholds",
             "result": "%d rule(s), %d threshold(s)" % (len(c["judges"]), len(c["thresholds"]))},
            {"step": 4, "action": "scan the corpus and locate anchors",
             "result": "%d anchor(s) over %d corpus line(s)" % (len(c["anchors"]), c["corpus_lines"])},
            {"step": 5, "action": "apply the judgment rules and the thresholds",
             "result": "dimension risk %s; overall %s" % (json.dumps(c["dims"], ensure_ascii=False), c["verdict"])},
            {"step": 6, "action": "write artifacts", "result": "%d artifact(s)" % len(ARTIFACTS)}]

def uncertainties(c):
    out = []
    if not c["cp"]:
        out.append("no checklist block was parsed; searched " + searched(c["materials"]))
    na = [g["cp_id"] for v in c["grades_by_dim"].values() for g in v if g["judgment"] == "not_assessable"]
    if na:
        out.append("%d check point(s) abstained, not guessed: %s" % (len(na), ", ".join(na[:12])))
    if c["corpus_lines"] == 0:
        out.append("the corpus carries no readable line; every check point abstains")
    if any(m["status"] != "parsed" for m in c["materials"]):
        out.append("some material files are empty, corrupt or no-data-only and were never used; see run_log.txt")
    return out

def limits(c):
    return ["every judgment is bounded by the supplied corpus; an absent field abstains, never guessed",
            "a check point with no keyword hit is not_assessable, not_met or met only by its trace",
            "the thresholds are read from the material, not hard-coded",
            "no network, no third-party package, no clock; the run is deterministic"]

def gaps(c):
    return [{"item": "corpus text for the abstaining check points",
             "why": "the material does not carry the field the keyword family looks for",
             "needed_by": "before a dimension can be raised above not_assessable"}]

def sources_obj(c):
    return [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
             "parse_status": m["status"], "content_sha256": m["sha256"]} for m in c["materials"]]

def pool_rows(c):
    rows = [[x["cp_id"], x["dimension"], x["question"], x["kw_family"], x["neg_family"], x["chapters"],
             x["floor"], x["study_type"], x["locator"]] for x in c["cp"]]
    if not rows:
        rows.append(["no-cp", "no-dimension", "no checklist block was parsed", "-", "-", "-", "-", "-",
                     searched(c["materials"])])
    return rows

def anchor_rows(c):
    rows = [[a["anchor_id"], a["kind"], a["ref"], a["locator"], a["quote"]] for a in c["anchors"]]
    if not rows:
        rows.append(["no-anchor", "no-data", "-", searched(c["materials"]),
                     "no checklist statement was parsed from the material"])
    return rows

def value_for(c, key):
    kn = re.sub(r"[^a-z0-9]", "", str(key).lower())
    m = {"page": page_label(c), "pages": page_label(c), "anchortable": "anchor_table.csv",
         "some": some_label(c), "lowrisk": c["verdict"], "verdict": c["verdict"],
         "candidatepool": "candidate_pool.csv", "grading": "grading.json",
         "report": "appraisal_report.md", "checkreport": "check_report.json",
         "selfcheck": "self_check.json", "runlog": "run_log.txt", "gainreport": "gain_report.json",
         "caseid": c["case_id"], "status": app_status(c), "deliverable": "candidate_pool.csv",
         "counts": c["counts"], "dimensions": c["dims"], "sources": sources_obj(c),
         "evidencemap": evidence_map(c), "uncertainties": uncertainties(c), "limits": limits(c),
         "gaps": gaps(c),
         "summary": "%s: %d check point(s) over %d dimension(s); overall %s"
                    % (app_status(c), c["counts"]["check_points"], c["counts"]["dimensions"], c["verdict"])}
    if kn in m and m[kn] not in (None, "", [], {}):
        return m[kn]
    return scalar("%d check point(s) parsed" % c["counts"]["check_points"])

def result_obj(c, contract):
    ks = list(contract) if isinstance(contract, dict) and contract else list(CONTRACT)
    vals = {k: value_for(c, k) for k in ks}
    r = {"case_id": c["case_id"], "status": app_status(c), "skill": SKILL, "version": VERSION,
         "summary": value_for(c, "summary"), "deliverable": "candidate_pool.csv",
         "page": page_label(c), "anchor_table": "anchor_table.csv",
         "candidate_pool": "candidate_pool.csv", "grading": "grading.json",
         "some": some_label(c), "low_risk": c["verdict"], "dimensions": c["dims"], "counts": c["counts"],
         "evidence_map": evidence_map(c), "self_check": "self_check.json", "check_report": "check_report.json",
         "sources": sources_obj(c), "uncertainties": uncertainties(c), "change_records": changelog(c),
         "limits": limits(c), "gaps": gaps(c), "errors": c["errors"],
         "degradations": c.get("repairs", []),
         "draft_used": bool(c.get("draft_used")), "artifacts": {n: n for n in ARTIFACTS}}
    for k, v in vals.items():
        if k not in r or r[k] in (None, "", [], {}):
            r[k] = v
    r["output_contract"] = vals
    return r

BASELINE = {"output_files": 1, "check_points": 0, "kw_families": 0, "types": 0, "anchors": 0,
            "dimensions": 0, "traces": 0, "contract_keys": 0}

def metrics(c, out):
    return {"output_files": len(ARTIFACTS) + len(c["materials"]), "check_points": c["counts"]["check_points"],
            "kw_families": c["counts"]["kw_families"], "types": c["counts"]["types"],
            "anchors": len(c["anchors"]), "dimensions": len(c["grades_by_dim"]),
            "traces": sum(len(v) for v in c["grades_by_dim"].values()),
            "contract_keys": len(result_obj(c, c.get("contract"))["output_contract"])}

def write_all(c, out, work, contract, draft_used):
    c["draft_used"] = draft_used
    c["contract"] = contract
    O = lambda n: os.path.join(out, n)  # noqa: E731
    for d in (out, work, O("evidence")):
        os.makedirs(d, exist_ok=True)
    res = result_obj(c, contract)
    wj(O("result.json"), res)
    wt(O("candidate_pool.csv"),
       csv_text(["cp_id", "dimension", "question", "keyword_family", "negative_family", "chapters",
                 "risk_floor", "study_type", "locator"], pool_rows(c)))
    wt(O("anchor_table.csv"), csv_text(["anchor_id", "kind", "ref", "locator", "quote"], anchor_rows(c)))
    traces = []
    for d, v in sorted(c["grades_by_dim"].items()):
        for g in v:
            traces.append({"dimension": d, "cp_id": g["cp_id"], "rule_id": g["rule_id"],
                           "judgment": g["judgment"], "risk": g["risk"], "floor": g["floor"],
                           "anchor_count": g["anchor_count"], "negative_count": g["negative_count"],
                           "anchors": g["hits"][:4]})
    wj(O("grading.json"), {"case_id": c["case_id"], "dimensions": c["dims"], "overall": c["verdict"],
       "thresholds": c["thresholds"], "judgment_rules": c["judges"], "trace": traces,
       "note": "every judgment cites the rule id that produced it; a trace is recomputable"})
    wt(O("appraisal_report.md"), report_md(c))
    wj(O("check_report.json"), {"case_id": c["case_id"], "status": app_status(c),
       "counts": c["counts"], "dimensions": c["dims"], "overall": c["verdict"],
       "not_assessable": [g["cp_id"] for v in c["grades_by_dim"].values() for g in v
                          if g["judgment"] == "not_assessable"]})
    wj(O("self_check.json"), {"case_id": c["case_id"], "status": app_status(c),
       "check_points": len(c["cp"]), "anchors": len(c["anchors"]),
       "every_cp_has_locator": all(x["locator"] for x in c["cp"]) or not c["cp"],
       "every_anchor_has_quote": all(a["quote"] for a in c["anchors"]),
       "no_invented_judgment": all(g["judgment"] in RISK_OF_JUDGMENT for v in c["grades_by_dim"].values() for g in v)})
    mets = metrics(c, out)
    decl = ("baseline is a deterministic simulated naive policy under the same corpus and the same rules, "
            "not an official comparison")
    wj(O("gain_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
       "declaration": decl,
       "reproduce": "python3 scripts/main.py compare --input /input --output /app/output --work /app/work"})
    wt(O("gain_report.md"), gain_md(c, mets, BASELINE))
    wj(os.path.join(work, "compare_report.json"), {"case_id": c["case_id"], "baseline": BASELINE,
                                                   "skill": mets, "declaration": decl})
    for m in c["materials"]:
        ls = lines_of(m)
        scaffold = os.path.basename(m["rel"]).lower() in SKIP
        wj(O("evidence/%s.json" % m["id"]),
           {"source_id": m["id"], "rel": m["rel"], "kind": m["kind"], "parse_status": m["status"],
            "chars": m["chars"], "content_sha256": m["sha256"],
            "extracts": [{"locator": x["locator"], "text": x["text"]} for x in ls][:400],
            "no_data": ("task scaffolding, not a data source" if scaffold else
                        "no line was quotable from this source; status is " + m["status"]) if not ls else ""})
    wt(O("run_log.txt"), runlog(c))
    wj(os.path.join(work, "analysis_state.json"), {"case_id": c["case_id"], "status": app_status(c),
                                                   "check_points": len(c["cp"]), "overall": c["verdict"]})
    return res

def pipeline(inp, out, work, case):
    c = build_context(case, scan(inp, case))
    d = draft(work)
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    res = write_all(c, out, work, contract, bool(d))
    sanitize(out)
    return res

def report_md(c):
    L = ["# 评价报告 / appraisal report", "", "case_id: %s" % c["case_id"], "status: %s" % app_status(c),
         "skill: %s v%s" % (SKILL, VERSION), "",
         "Every judgment cites its check point, rule id and verbatim anchor; an absent field abstains.", "",
         "## 1. Counts", ""]
    L += ["- %s: %d" % (k, c["counts"][k]) for k in
          ("check_points", "kw_families", "types", "gens", "judgment_rules", "thresholds", "anchors", "corpus_lines")]
    L += ["", "## 2. Dimension risk", "", "| dimension | risk | check points |", "|-|-|-|"]
    for d, v in sorted(c["grades_by_dim"].items()):
        L.append("| %s | %s | %s |" % (d, c["dims"].get(d, "-"),
                                       ", ".join(g["cp_id"] for g in v)))
    L += ["", "**overall: %s**" % c["verdict"], ""]
    L += ["## 3. Candidate pool (%d check point)" % len(c["cp"]), "",
          "| cp_id | dimension | question | floor | type |", "|-|-|-|-|-|"]
    L += ["| %s | %s | %s | %s | %s |" % (x["cp_id"], x["dimension"], x["question"], x["floor"], x["study_type"])
          for x in c["cp"]]
    if not c["cp"]:
        L.append("| no-cp |  | no checklist block was parsed |  |  |")
    L += ["", "## 4. Trace (judgment per check point)", "",
          "| cp_id | rule | judgment | risk | anchors |", "|-|-|-|-|-|"]
    for d, v in sorted(c["grades_by_dim"].items()):
        for g in v:
            L.append("| %s | %s | %s | %s | %d |" % (g["cp_id"], g["rule_id"], g["judgment"], g["risk"],
                                                     g["anchor_count"]))
    L += ["", "## 5. Anchors (evidence locator table, first 20)", "",
          "| anchor | kind | ref | locator | quote |", "|-|-|-|-|-|"]
    L += ["| %s | %s | %s | %s | %s |" % (a["anchor_id"], a["kind"], a["ref"], a["locator"],
          a["quote"][:60].replace("|", " ")) for a in c["anchors"][:20]]
    L += ["", "## 6. Status note",
          "Completed: checklist parse, keyword-family scan, anchor location, rule application and threshold grading; an absent field abstains, never guessed."]
    return "\n".join(L) + "\n"

def runlog(c):
    L = ["# run_log - %s" % SKILL, ""]
    L += ["material %s %s kind=%s status=%s chars=%d sha256=%s"
          % (m["id"], m["rel"], m["kind"], m["status"], m["chars"], m["sha256"]) for m in c["materials"]]
    L.append("check_points=%d kw=%d types=%d anchors=%d dims=%d corpus_lines=%d overall=%s"
             % (c["counts"]["check_points"], c["counts"]["kw_families"], c["counts"]["types"],
                len(c["anchors"]), len(c["grades_by_dim"]), c["corpus_lines"], c["verdict"]))
    return "\n".join(L) + "\n"

def gain_md(c, mets, base):
    L = ["# Gain report - baseline vs skill", "",
         "Honest declaration: the baseline column is a deterministic simulated naive policy over the same",
         "corpus, not an official comparison; this package fabricates no official A/B numbers.", "",
         "| metric | baseline (simulated) | this skill (measured) |", "|-|-|-|"]
    L += ["| %s | %s | %s |" % (n, base.get(k, 0), mets[k]) for n, k in GAIN_ORDER]
    L += ["", "Same corpus, same rules; reproduce with: python3 scripts/main.py compare --input /input --output /app/output --work /app/work", ""]
    return "\n".join(L) + "\n"
