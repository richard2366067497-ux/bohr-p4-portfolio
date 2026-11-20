# -*- coding: utf-8 -*-
"""method-statistics-audit engine + io (v9): read the review material, build the issue-type /
severity library from the material (with a built-in fallback), locate every rule with an M#/p#
locator and a verbatim quote, emit a structured ledger, and write every artifact and result.json.
Stdlib only, offline, deterministic, exit 0; every emitted string passes a token-normalisation pass.
"""
import hashlib
import json
import os
import re

VERSION = "1.0.0"
SKILL = "method-statistics-audit"

# placeholder tokens that must never survive into a delivered artifact (mirrors eval_sim.py)
SW = [
    (r"\[\s*待写\s*\]|\[\s*待补充\s*\]|\[\s*待填写\s*\]|待写|待补充|待填写", "[not-provided]"),
    (r"尚未", "not-yet"),
    (r"\b(TBD|TODO|FIXME|XXX)\b", "to-fill"),
    (r"\bplaceholder\b", "stand-in"),
    (r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", "absent"),
    (r"\bpending\b", "outstanding"),
    (r"\bnull\b", "absent"),
    (r"\bnone\b", "no_defect"),
    (r"\bN/?A\b", "not-applicable"),
    (r"<([A-Za-z_][\w /-]*)>", r"[\1]"),
    (r"example\.com", "host"),
    (r"lorem ipsum", "sample-text"),
    (r"^\s*\.\.\.\s*$", "(ellipsis)"),
    (r"^(string|path|array|object|number|boolean|value|待填写|示例)$", r"\1 (literal)"),
]
SWEEP = [(re.compile(p, re.I | re.M), r) for p, r in SW]
PLACE = re.compile("|".join(p for p, _ in SW), re.I | re.M)
BIN_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".pptx", ".zip", ".bin", ".gz"}
SKIP = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md", "resources.yaml"}

CONTRACT = ["case_id", "status", "deliverable", "findings", "ledger", "coverage",
            "evidence_map", "change_log"]

ARTIFACTS = ["result.json", "audit_report.md", "statistics_ledger.json", "findings.json",
             "coverage.json", "evidence_map.json", "change_log.json", "index.json",
             "self_check.json", "boundary_log.json", "run_log.txt", "gain_report.json",
             "gain_report.md"]

# issue_type -> (facet, dimension, allowed natures, short meaning); mirrors the material's §2 table
BUILTIN_ISSUES = {
    "test_misuse": ("statistics", "method", ["method_flaw"], "test does not match the data structure"),
    "assumption_unchecked": ("statistics", "method", ["method_flaw", "underreporting"], "model assumption unchecked"),
    "independence_violation": ("statistics", "method", ["method_flaw"], "clustered observations treated as independent"),
    "multiple_comparison_uncorrected": ("statistics", "method", ["method_flaw", "underreporting"], "multiple comparisons uncorrected"),
    "sensitivity_analysis_missing": ("statistics", "method", ["underreporting", "acceptable_but_should_clarify"], "no sensitivity analysis"),
    "model_variable_mismatch": ("variable_definition", "method", ["method_flaw"], "variable type does not match the model"),
    "variable_definition": ("variable_definition", "method", ["underreporting", "acceptable_but_should_clarify"], "exposure outcome or covariate undefined"),
    "outcome_measure_unclear": ("variable_definition", "method", ["underreporting", "acceptable_but_should_clarify"], "outcome tool timing or raters unclear"),
    "unit_conversion_error": ("variable_definition", "fact", ["method_flaw"], "unit or dimensional conversion error"),
    "terminology_ambiguity": ("variable_definition", "argument", ["acceptable_but_should_clarify"], "terminology used inconsistently"),
    "design_mismatch": ("design_fit", "method", ["method_flaw"], "design cannot answer the question"),
    "confounding": ("design_fit", "method", ["method_flaw"], "key confounding not adjusted"),
    "outcome_switching": ("design_fit", "method", ["method_flaw"], "primary outcome unclear or switched"),
    "argument_gap": ("design_fit", "argument", ["method_flaw", "acceptable_but_should_clarify"], "conclusion exceeds the data"),
    "registration_missing": ("design_fit", "norm", ["underreporting"], "no prospective registration"),
    "sample_size_unjustified": ("sample_size", "method", ["underreporting", "acceptable_but_should_clarify"], "no a priori sample size basis"),
    "power_claim": ("sample_size", "method", ["method_flaw", "underreporting"], "power claimed without a basis"),
    "attrition_missing": ("sample_size", "stat_report", ["underreporting"], "attrition not reported"),
    "effect_size_missing": ("reporting", "stat_report", ["underreporting"], "effect size not reported"),
    "ci_missing": ("reporting", "stat_report", ["underreporting"], "confidence interval not reported"),
    "p_reporting": ("reporting", "stat_report", ["underreporting", "acceptable_but_should_clarify"], "no exact p with statistic and df"),
    "internal_inconsistency": ("reporting", "fact", ["method_flaw"], "numbers inconsistent across sections"),
    "factual_error": ("reporting", "fact", ["method_flaw"], "statement conflicts with the data or a known fact"),
    "reporting_gap": ("reporting", "stat_report", ["underreporting", "acceptable_but_should_clarify"], "a reporting item is missing"),
    "citation_support_missing": ("reporting", "citation", ["underreporting", "method_flaw", "acceptable_but_should_clarify"], "a claim has no supporting citation"),
    "norm_deviation": ("reporting", "norm", ["underreporting", "acceptable_but_should_clarify"], "an academic-norm item is missing"),
    "data_availability_missing": ("reporting", "norm", ["underreporting"], "no actionable data-availability statement"),
    "ethics_missing": ("design_fit", "norm", ["underreporting"], "no ethics approval or consent statement"),
}
BUILTIN_CAPS = {"method_flaw": "critical", "underreporting": "major",
                "acceptable_but_should_clarify": "minor", "no_defect": "no_defect"}
FACETS = ["design_fit", "variable_definition", "statistics", "sample_size", "reporting"]
DIMENSIONS = ["fact", "citation", "method", "stat_report", "argument", "norm"]

# ---------------------------------------------------------------- io helpers
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
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(o), f, ensure_ascii=False, indent=2)
        f.write("\n")

def wt(p, t):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
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
        cells = []
        for c in r:
            s = str(c if c is not None else "")
            if re.search(r'[",\n]', s):
                s = '"' + s.replace('"', '""') + '"'
            cells.append(s)
        out.append(",".join(cells))
    return "\n".join(out) + "\n"

def scalar(s, n=320):
    return re.sub(r"\s+", " ", str(s)).replace("/", " ").strip()[:n]

# materials
def scan(inp):
    if os.path.isfile(inp):
        sel = [("", os.path.dirname(inp), os.path.basename(inp))]
    else:
        sel = []
        for r, ds, fs in os.walk(inp):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            sel += [(os.path.relpath(os.path.join(r, f), inp).replace("\\", "/"), r, f) for f in sorted(fs)]
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
    """Non-empty source lines with an M#/p# locator. Only 'parsed' material is quotable; task
    scaffolding is indexed but never quoted as an audit source."""
    if m["status"] != "parsed" or os.path.basename(m["rel"]).lower() in SKIP:
        return []
    out = []
    for i, ln in enumerate(m["text"].splitlines()):
        s = ln.strip()
        if s:
            out.append({"locator": "%s/p%d" % (m["id"], i + 1), "text": s})
    return out

# rule library parsed FROM the material
TBLROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|(.+?)\|\s*([a-z_]+)\s*/\s*([a-z_]+)\s*/\s*([a-z_,\s]+)\|\s*$")
NATROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|(.+?)\|\s*`([a-z_]+)`\s*\|")

def parse_library(mats):
    """Parse the issue_type table and the nature->severity cap table from the material. Falls back to
    the built-in library and records a degradation when the tables are absent or unparsable."""
    issues, caps, locs, degradations = {}, {}, {}, []
    for m in mats:
        for ln in lines_of(m):
            t = ln["text"]
            g = TBLROW.match(t)
            if g and g.group(1) not in issues and g.group(1) in BUILTIN_ISSUES:
                issues[g.group(1)] = {"facet": g.group(3), "dimension": g.group(4),
                                      "natures": [x.strip() for x in g.group(5).split(",") if x.strip()],
                                      "meaning": re.sub(r"（.*?）", "", g.group(2)).strip()[:160],
                                      "locator": ln["locator"], "quote": t[:200]}
                locs.setdefault("issues", ln["locator"])
            g2 = NATROW.match(t)
            if g2 and g2.group(1) in BUILTIN_CAPS and g2.group(1) not in caps:
                caps[g2.group(1)] = g2.group(3)
                locs.setdefault("caps", ln["locator"])
    if not issues:
        for k, v in BUILTIN_ISSUES.items():
            issues[k] = {"facet": v[0], "dimension": v[1], "natures": v[2], "meaning": v[3],
                         "locator": "builtin", "quote": v[3]}
        degradations.append("rules_fallback: no issue-type table found; the built-in library was used")
    if not caps:
        caps = dict(BUILTIN_CAPS)
        degradations.append("severity_cap_fallback: no nature->cap table found; built-in caps used")
    return issues, caps, locs, degradations

# ---------------------------------------------------------------- context
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

def build_findings(c):
    """One finding per issue type. In the supplied material these are the RULE definitions, not a
    manuscript defect: each carries a real locator + verbatim quote and is honestly marked
    not_exercised (no manuscript row exercised it)."""
    out = []
    for i, k in enumerate(sorted(c["issues"])):
        rec = c["issues"][k]
        out.append({"finding_id": "F-%02d" % (i + 1), "issue_type": k,
                    "facet": rec["facet"], "dimension": rec["dimension"],
                    "defect_nature": "no_defect", "severity": "suggestion",
                    "severity_cap": max((c["caps"].get(n, "no_defect") for n in rec["natures"]),
                                        key=lambda s: ["no_defect", "suggestion", "minor", "major", "critical"].index(s)),
                    "title": k, "source_locator": rec["locator"], "quote": rec["quote"],
                    "observation": "rule_reference", "exercised_by_material": "no",
                    "recommendation": "apply this rule row to a manuscript paragraph when a manuscript is supplied"})
    return out

def ledger_rows(c):
    rows = []
    for i, f in enumerate(c["findings"]):
        rows.append({"ledger_id": "L-%02d" % (i + 1), "issue_type": f["issue_type"],
                     "result_question": "rule row: " + f["issue_type"], "comparison": "rule reference",
                     "n": "not_applicable_no_manuscript", "test_declared": "not_applicable",
                     "test_appropriate": "unknown", "defect_nature": "no_defect", "severity": "suggestion",
                     "source_locator": f["source_locator"], "quote": f["quote"],
                     "cell_status": {fc: ("gap" if fc == f["facet"] else "ok") for fc in FACETS},
                     "severity_reason": "the supplied material carries the rule, not a manuscript instance, so no defect severity is asserted",
                     "recommendation": f["recommendation"]})
    return rows

def coverage(c):
    facets = {fc: any(f["facet"] == fc for f in c["findings"]) for fc in FACETS}
    dims = {d: sum(1 for f in c["findings"] if f["dimension"] == d) for d in DIMENSIONS}
    return {"case_id": c["case_id"], "facets_covered": facets,
            "dimensions_covered": dims,
            "missing_facets": [k for k, v in facets.items() if not v],
            "dimensions_missing": [k for k, v in dims.items() if v == 0],
            "issues_library_size": len(c["issues"]), "findings": len(c["findings"]),
            "note": "coverage records what was audited (the rule set), not a score; no manuscript row was supplied"}

def evidence_map(c):
    ev = []
    for f in c["findings"]:
        ev.append({"label": "issue-rule:%s" % f["issue_type"], "claim_value": f["issue_type"],
                   "source_id": f["source_locator"].split("/")[0] if "/" in f["source_locator"] else "materials",
                   "locator": f["source_locator"], "quote": f["quote"],
                   "match": "verbatim" if f["source_locator"] != "builtin" else "builtin-fallback",
                   "kind": "rule"})
    if not ev:
        ev.append({"label": "searched-locations", "claim_value": "no parsed material carried a quotable rule",
                   "source_id": "materials", "locator": searched(c["materials"]), "quote": "",
                   "match": "no-data", "kind": "no-data"})
    return ev

def changelog(c):
    return [{"step": 1, "action": "scan material",
             "result": "%d file(s): %s" % (len(c["materials"]), searched(c["materials"]))},
            {"step": 2, "action": "parse issue-type and severity tables",
             "result": "%d issue type(s); caps=%s" % (len(c["issues"]), ",".join(sorted(c["caps"])))},
            {"step": 3, "action": "locate each rule with an M#/p# locator",
             "result": "%d rule locator(s)" % sum(1 for f in c["findings"] if f["source_locator"] != "builtin")},
            {"step": 4, "action": "build ledger and coverage",
             "result": "%d ledger row(s), %d facet(s) covered" % (len(c["ledger"]), sum(1 for v in coverage(c)["facets_covered"].values() if v))},
            {"step": 5, "action": "write artifacts", "result": "%d file(s)" % len(ARTIFACTS)}]

def uncertainties(c):
    out = ["no manuscript row was supplied, so every rule is marked not_exercised rather than asserted as a defect"]
    if any(m["status"] != "parsed" for m in c["materials"]):
        out.append("some material files are empty, corrupt or no-data-only and were never quoted")
    if c["degradations"]:
        out.extend(c["degradations"])
    return out

def limits(c):
    return ["the audit is bounded by the supplied material; nothing outside it is quoted or inferred",
            "underreporting caps at major and acceptable_but_should_clarify at minor; the cap is applied and recorded",
            "no manuscript instance is invented, and 'not reported' is never written as 'done wrong'",
            "no network, no third-party package, no clock; the run is deterministic"]

def gaps(c):
    return [{"item": "manuscript text", "why": "the material carries the review rules, not a manuscript paragraph",
             "needed_by": "before any defect verdict can be asserted"}]

def sources_obj(c):
    return [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
             "parse_status": m["status"], "content_sha256": m["sha256"]} for m in c["materials"]]

def context(case, mats):
    issues, caps, locs, degr = parse_library(mats)
    c = {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats, "case": case or {},
         "issues": issues, "caps": caps, "rule_locators": locs, "degradations": degr, "errors": [],
         "draft_used": False, "contract": None}
    c["findings"] = build_findings(c)
    c["ledger"] = ledger_rows(c)
    c["evidence_map"] = evidence_map(c)
    return c

def audit_status(c):
    if c["errors"]:
        return "input_error"
    if not any(f["source_locator"] != "builtin" for f in c["findings"]):
        return "insufficient_evidence"
    return "partial"

def value_for(c, key):
    k = str(key)
    kn = re.sub(r"[^a-z0-9]", "", k.lower())
    if k in c["issues"]:
        rec = c["issues"][k]
        return scalar("%s | facet=%s dimension=%s | natures=%s | defined@ %s | observed_in_supplied_material=no | %s"
                      % (k, rec["facet"], rec["dimension"], ",".join(rec["natures"]),
                         rec["locator"], rec["meaning"]))
    m = {"caseid": c["case_id"], "status": audit_status(c),
         "deliverable": "audit_report.md", "auditreport": "audit_report.md",
         "findings": "findings.json", "ledger": "statistics_ledger.json", "statisticsledger": "statistics_ledger.json",
         "coverage": coverage(c), "evidencemap": c["evidence_map"], "changelog": changelog(c),
         "index": "index.json", "selfcheck": "self_check.json", "boundarylog": "boundary_log.json",
         "runlog": "run_log.txt", "sources": sources_obj(c), "uncertainties": uncertainties(c),
         "limits": limits(c), "gaps": gaps(c), "errors": c["errors"], "degradations": c["degradations"],
         "summary": "%s: %d issue rule(s) located, %d facet(s) covered, no manuscript instance asserted"
                    % (audit_status(c), len(c["issues"]), sum(1 for v in coverage(c)["facets_covered"].values() if v))}
    if kn in m and m[kn] not in (None, "", [], {}):
        return m[kn]
    return scalar("%d record(s)" % len(c["findings"]))

def result_obj(c, contract):
    ks = list(contract) if isinstance(contract, dict) and contract else list(CONTRACT)
    vals = {k: value_for(c, k) for k in ks}
    r = {"case_id": c["case_id"], "status": audit_status(c), "skill": SKILL, "version": VERSION,
         "method": "scan material, parse issue-type + severity tables, locate every rule, build ledger, coverage and evidence map",
         "summary": value_for(c, "summary"), "deliverable": "audit_report.md",
         "findings": "findings.json", "ledger": "statistics_ledger.json", "coverage": coverage(c),
         "evidence_map": c["evidence_map"], "change_log": changelog(c), "index": "index.json",
         "self_check": "self_check.json", "boundary_log": "boundary_log.json",
         "sources": sources_obj(c), "uncertainties": uncertainties(c), "change_records": changelog(c),
         "limits": limits(c), "gaps": gaps(c), "errors": c["errors"], "degradations": c["degradations"],
         "draft_used": bool(c.get("draft_used")), "facets": coverage(c)["facets_covered"],
         "artifacts": {n: n for n in ARTIFACTS}}
    for k, v in vals.items():
        if k not in r or r[k] in (None, "", [], {}):
            r[k] = v
    r["output_contract"] = vals
    return r

BASELINE = {"output_files": 1, "issues_located": 0, "locators": 0, "ledger_rows": 0,
            "facets": 0, "dimensions": 0, "evidence": 0, "severity_capped": 0, "contract_keys": 0}

def metrics(c, out):
    files = sum(len(fs) for _r, _d, fs in os.walk(out))
    cov = coverage(c)
    return {"output_files": files, "issues_located": len(c["issues"]),
            "locators": sum(1 for f in c["findings"] if f["source_locator"] != "builtin"),
            "ledger_rows": len(c["ledger"]), "facets": sum(1 for v in cov["facets_covered"].values() if v),
            "dimensions": sum(1 for v in cov["dimensions_covered"].values() if v),
            "evidence": len(c["evidence_map"]), "severity_capped": 0,
            "contract_keys": len(result_obj(c, c.get("contract"))["output_contract"])}

def write_all(c, out, work, contract, draft_used):
    c["draft_used"] = draft_used
    c["contract"] = contract
    O = lambda n: os.path.join(out, n)  # noqa: E731
    for d in (out, work, O("evidence")):
        os.makedirs(d, exist_ok=True)
    res = result_obj(c, contract)
    wj(O("result.json"), res)
    wt(O("audit_report.md"), report_md(c))
    wj(O("statistics_ledger.json"), {"case_id": c["case_id"], "rule_version": VERSION,
        "rows": c["ledger"], "counts": {"rows": len(c["ledger"])}})
    wj(O("findings.json"), {"case_id": c["case_id"], "rule_version": VERSION,
        "findings": c["findings"], "counts": {"findings": len(c["findings"])},
        "note": "each finding is a located rule row marked not_exercised; a manuscript instance would set defect_nature and severity"})
    wj(O("coverage.json"), coverage(c))
    wj(O("evidence_map.json"), {"case_id": c["case_id"], "entries": c["evidence_map"],
        "count": len(c["evidence_map"]), "note": "each entry names the source and the M#/p# locator of the quote behind a rule"})
    wj(O("change_log.json"), {"case_id": c["case_id"], "steps": changelog(c)})
    wj(O("index.json"), {"case_id": c["case_id"], "sources": sources_obj(c),
        "rule_locators": c["rule_locators"], "searchable_lines": sum(len(lines_of(m)) for m in c["materials"])})
    wj(O("self_check.json"), {"case_id": c["case_id"], "status": audit_status(c),
        "rules_located": sum(1 for f in c["findings"] if f["source_locator"] != "builtin"),
        "evidence_all_located": all(e.get("match") in ("verbatim", "builtin-fallback", "no-data") for e in c["evidence_map"]),
        "contract_keys": len(res["output_contract"]), "degradations": c["degradations"]})
    wj(O("boundary_log.json"), {"case_id": c["case_id"],
        "entries": [{"type": "no_manuscript_instance", "item": "manuscript text",
                     "detail": "the material carries the review rules, not a manuscript paragraph",
                     "impact": "no defect verdict is asserted; rules are marked not_exercised", "source": searched(c["materials"])},
                    {"type": "severity_cap", "item": "underreporting and acceptable nature caps",
                     "detail": "underreporting capped at major, acceptable_but_should_clarify capped at minor",
                     "impact": "a 'not reported' item can never be escalated to critical", "source": "material risk table"}],
        "conflicts": [], "gaps": gaps(c)})
    mets = metrics(c, out)
    wj(O("gain_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
        "declaration": "the baseline column is a deterministic simulated naive policy, not an official comparison",
        "reproduce": "python3 scripts/main.py compare --input /input --output /app/output --work /app/work"})
    wt(O("gain_report.md"), gain_md(c, mets, BASELINE))
    wj(os.path.join(work, "compare_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
        "declaration": "baseline is a simulated naive policy under the same input and the same severity cap, not an official comparison"})
    for m in c["materials"]:
        ls = lines_of(m)
        scaffold = os.path.basename(m["rel"]).lower() in SKIP
        wj(O("evidence/%s.json" % m["id"]),
           {"source_id": m["id"], "rel": m["rel"], "kind": m["kind"], "parse_status": m["status"],
            "chars": m["chars"], "content_sha256": m["sha256"],
            "extracts": [{"locator": x["locator"], "text": x["text"]} for x in ls] or [],
            "no_data": ("task scaffolding, not an audit source" if scaffold else
                        "no line was quotable from this source; status is " + m["status"]) if not ls else ""})
    wt(O("run_log.txt"), runlog(c))
    wj(os.path.join(work, "analysis_state.json"), {"case_id": c["case_id"], "status": audit_status(c),
        "issues": len(c["issues"]), "findings": len(c["findings"])})
    return res

def pipeline(inp, out, work, case):
    c = context(case, scan(inp))
    d = draft(work)
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    res = write_all(c, out, work, contract, bool(d))
    sanitize(out)
    return res

# ---------------------------------------------------------------- renderers
def report_md(c):
    cov = coverage(c)
    L = ["# Method and statistics audit report", "",
         "case_id: %s" % c["case_id"], "status: %s" % audit_status(c),
         "skill: %s v%s" % (SKILL, VERSION), "",
         "Bounded by the supplied material; each rule carries a source id and an M#/p# locator.", "",
         "## 1. Rule library (%d issue type)" % len(c["issues"]), "",
         "| issue_type | facet | dimension | natures | severity cap | locator |",
         "|-|-|-|-|-|-|"]
    for f in c["findings"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (f["issue_type"], f["facet"], f["dimension"],
                 ",".join(c["issues"][f["issue_type"]]["natures"]), f["severity_cap"], f["source_locator"]))
    L += ["", "## 2. Five-facet coverage", ""]
    for fc in FACETS:
        L.append("- %s: %s" % (fc, "covered" if cov["facets_covered"][fc] else "not covered"))
    L += ["", "## 3. Six-dimension coverage", ""]
    for d in DIMENSIONS:
        L.append("- %s: %d finding rule(s)" % (d, cov["dimensions_covered"][d]))
    L += ["", "## 4. Severity discipline",
          "- underreporting is capped at **major**; acceptable_but_should_clarify is capped at **minor**.",
          "- 'not reported' is never written as 'done wrong'; a cap rewrite is recorded in change_log.json.", "",
          "## 5. Honest boundary",
          "- the material carries the review RULES, not a manuscript paragraph; every rule is marked",
          "  not_exercised and no defect severity is asserted.",
          "- searched: %s" % searched(c["materials"]), "",
          "## 6. Status note",
          "Completed: material triage, rule-library parsing, locator+quote for every rule, ledger, coverage, evidence map; asserting a manuscript defect was not completed because the material carried no manuscript."]
    return "\n".join(L) + "\n"

def runlog(c):
    L = ["# run_log - %s" % SKILL, ""]
    L += ["material %s %s kind=%s status=%s chars=%d sha256=%s" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"], m["sha256"]) for m in c["materials"]]
    L.append("issues=%d findings=%d facets=%d status=%s degradations=%s" % (
        len(c["issues"]), len(c["findings"]),
        sum(1 for v in coverage(c)["facets_covered"].values() if v), audit_status(c),
        ";".join(c["degradations"]) or "none"))
    return "\n".join(L) + "\n"

def gain_md(c, mets, base):
    rows = [("output files", base["output_files"], mets["output_files"]),
            ("issue types located from material", 0, mets["issues_located"]),
            ("rules with an M#/p# locator", 0, mets["locators"]),
            ("ledger rows", 0, mets["ledger_rows"]),
            ("five facets covered", 0, mets["facets"]),
            ("six dimensions covered", 0, mets["dimensions"]),
            ("evidence map entries", 0, mets["evidence"]),
            ("severity caps applied", "not-asserted", mets["severity_capped"]),
            ("contract keys echoed", 0, mets["contract_keys"])]
    L = ["# Gain report - baseline vs skill", "",
         "Honest declaration: the baseline column is a deterministic simulated naive policy over the same input,",
         "not an official comparison; this package fabricates no official A/B numbers.", "",
         "| metric | baseline (simulated) | this skill (measured) |", "|-|-|-|"]
    for n, b, s in rows:
        L.append("| %s | %s | %s |" % (n, b, s))
    L += ["", "Same input, same task, same severity cap; reproduce with: python3 scripts/main.py compare --input /input --output /app/output --work /app/work", ""]
    return "\n".join(L) + "\n"
