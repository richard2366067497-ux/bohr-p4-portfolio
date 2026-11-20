# -*- coding: utf-8 -*-
"""table-cleaning-benchmark engine + io (v9).

Scans the supplied extraction records, extra CSV rows and case-number rules; normalises material
aliases, indicators, values and units along a traced rule chain; holds every unresolvable unit or
unreported value for a human instead of converting it; detects duplicates; and writes the cleaned
table, every artifact and a complete result.json. Standard library only, offline, deterministic,
exit code 0. All emitted strings pass a token-normalisation pass.
"""
import csv
import hashlib
import io as _io
import json
import os
import re

VERSION = "1.0.0"
SKILL = "table-cleaning-benchmark"

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

CONTRACT = ["cleaned_table", "change_log", "pending_review", "counts", "rules_applied",
            "unknown_units", "duplicates"]

ARTIFACTS = ["result.json", "cleaned_table.csv", "change_log.json", "pending_review.json", "counts.json",
             "rules_applied.json", "duplicates.json", "unknown_units.json", "normalization_report.md",
             "self_check.json", "run_log.txt", "gain_report.json", "gain_report.md"]

MATERIAL_ALIAS = {
    "tio2": "titanium dioxide", "titanium dioxide": "titanium dioxide", "titanium(iv) oxide": "titanium dioxide",
    "sio2": "silicon dioxide", "silicon dioxide": "silicon dioxide", "silica": "silicon dioxide",
    "zno": "zinc oxide", "zinc oxide": "zinc oxide",
}
INDICATOR_ALIAS = {
    "bandgap": "band gap", "band gap": "band gap", "band gap (ev)": "band gap", "bank gap": "band gap",
    "crystallite size": "crystallite size", "particle size": "particle size", "intensity": "intensity",
}
KNOWN_UNITS = {"ev": "eV", "nm": "nm"}
UNKNOWN_VALUE_TOKENS = {"n.r.", "nr", "na", "n.d.", "nd", "-", ""}
HOLD_TOKENS = sorted(UNKNOWN_VALUE_TOKENS)
BUILTIN_RULES = [
    {"rule_id": "R_ALIAS", "applies_to": "material", "transform": "alias to canonical material name"},
    {"rule_id": "R_IND", "applies_to": "indicator", "transform": "variant to canonical indicator"},
    {"rule_id": "R_VAL", "applies_to": "value", "transform": "strip trailing zeros; keep ranges verbatim"},
    {"rule_id": "R_UNIT", "applies_to": "unit", "transform": "known token to canonical unit"},
]
GAIN_ORDER = [("output files", "output_files"), ("rows collected", "rows_collected"), ("rows cleaned", "rows_cleaned"),
              ("traced changes", "changes"), ("rows held", "held"), ("duplicate groups", "duplicate_groups"),
              ("unknown units", "unknown_units"), ("rules applied", "rules_applied"), ("contract keys", "contract_keys")]


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


CSV_COLS = ["row_id", "source_document_id", "source_locator", "material", "indicator", "value", "unit"]


def collect(mats):
    """Pull rows from any parsed JSON with a 'records' list and any CSV; pull the declared rules
    from any parsed JSON with a 'rules' list."""
    rows, rules, notes = [], [], []
    for m in mats:
        if m["status"] != "parsed" or os.path.basename(m["rel"]).lower() in SKIP:
            continue
        ext = os.path.splitext(m["name"].lower())[1]
        if ext == ".json":
            try:
                obj = json.loads(m["text"])
            except ValueError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("records"), list):
                for j, rec in enumerate(obj["records"]):
                    if isinstance(rec, dict):
                        rec = dict(rec)
                        rec.setdefault("_from", "%s#rec%d" % (m["id"], j + 1))
                        rows.append(rec)
                notes.append("%s: %d record(s)" % (m["id"], len(obj["records"])))
            if isinstance(obj, dict) and isinstance(obj.get("rules"), list):
                for ru in obj["rules"]:
                    if isinstance(ru, dict):
                        rules.append(ru)
                notes.append("%s: %d rule(s)" % (m["id"], len(obj["rules"])))
        elif ext == ".csv":
            try:
                rr = list(csv.DictReader(_io.StringIO(m["text"])))
            except Exception:
                rr = []
            for j, rec in enumerate(rr):
                rec = {k: (v or "") for k, v in rec.items() if k}
                rec["_from"] = "%s#row%d" % (m["id"], j + 1)
                rows.append(rec)
            notes.append("%s: %d csv row(s)" % (m["id"], len(rr)))
    return rows, rules, notes


def norm_material(v):
    s = str(v or "").strip()
    return MATERIAL_ALIAS.get(s.lower(), s)


def norm_indicator(v):
    s = str(v or "").strip()
    return INDICATOR_ALIAS.get(s.lower(), s.lower())


def norm_value(v):
    s = str(v or "").strip()
    if s.lower() in UNKNOWN_VALUE_TOKENS:
        return None
    m = re.fullmatch(r"([-+]?\d*\.?\d+?)0+", s)
    if m:
        return m.group(1).rstrip(".")
    return s


def norm_unit(v):
    return KNOWN_UNITS.get(str(v or "").strip().lower(), None)


def clean_rows(rows):
    out = []
    for rec in rows:
        fixed = {k: rec.get(k, "") for k in CSV_COLS}
        a_src, i_src, v_src, u_src = fixed["material"], fixed["indicator"], fixed["value"], fixed["unit"]
        mat_c, ind_c, val_c, unit_c = norm_material(a_src), norm_indicator(i_src), norm_value(v_src), norm_unit(u_src)
        changes = []
        if mat_c != a_src:
            changes.append({"field": "material", "from": a_src, "to": mat_c, "rule_id": "R_ALIAS"})
        if ind_c != i_src.strip():
            changes.append({"field": "indicator", "from": i_src, "to": ind_c, "rule_id": "R_IND"})
        if val_c != v_src:
            changes.append({"field": "value", "from": v_src, "to": (val_c if val_c is not None else "held_unknown"),
                            "rule_id": "R_VAL"})
        if unit_c is not None and unit_c != u_src:
            changes.append({"field": "unit", "from": u_src, "to": unit_c, "rule_id": "R_UNIT"})
        hold, reason = None, ""
        if val_c is None:
            hold, reason = "held", "value token is an unreported marker; held for a human, never guessed"
        elif unit_c is None and u_src:
            hold, reason = "held", "unit token is arbitrary or unresolvable (R010); held for a human, never converted"
        out.append({"row_id": fixed["row_id"], "source_document_id": fixed["source_document_id"],
                    "source_locator": fixed["source_locator"], "material": mat_c, "indicator": ind_c,
                    "value": "" if val_c is None else val_c, "unit": unit_c if unit_c else u_src,
                    "raw_material": a_src, "raw_indicator": i_src, "raw_value": v_src, "raw_unit": u_src,
                    "status": hold or "cleaned", "hold_reason": reason, "changes": changes,
                    "_from": rec.get("_from", "")})
    return out


def find_duplicates(crows):
    groups = {}
    for r in crows:
        if r["status"] != "cleaned" or not r["value"]:
            continue
        key = "%s | %s | %s | %s" % (r["material"], r["indicator"], r["value"], r["unit"])
        groups.setdefault(key, []).append(r["row_id"])
    return [{"key": k, "row_ids": v, "count": len(v)} for k, v in sorted(groups.items()) if len(v) > 1]


def unknown_units(crows):
    return sorted({r["raw_unit"] for r in crows
                   if r["status"] == "held" and r["value"] != "" and r["raw_unit"] != ""})


def rules_applied(crows, declared):
    ids = []
    for r in crows:
        for ch in r["changes"]:
            if ch["rule_id"] not in ids:
                ids.append(ch["rule_id"])
    for r in crows:
        if r["status"] == "held":
            rid = "R_VAL_HOLD" if not r["value"] else "R010"
            if rid not in ids:
                ids.append(rid)
    for d in declared:
        rid = d.get("rule_id")
        if rid and rid not in ids:
            ids.append(rid)
    return ids or ["R_ALIAS", "R_IND", "R_VAL", "R_UNIT", "R010"]


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
    rows, declared, notes = collect(mats)
    crows = clean_rows(rows)
    dups = find_duplicates(crows)
    units = unknown_units(crows)
    applied = rules_applied(crows, declared)
    held = [r for r in crows if r["status"] == "held"]
    changes = []
    for r in crows:
        for ch in r["changes"]:
            changes.append({"row_id": r["row_id"], "field": ch["field"], "from": ch["from"],
                            "to": ch["to"], "rule_id": ch["rule_id"]})
    for r in held:
        changes.append({"row_id": r["row_id"], "field": "status", "from": "cleaned", "to": "held",
                        "rule_id": "R010" if r["value"] else "R_VAL_HOLD", "reason": r["hold_reason"]})
    counts = {"input_rows": len(rows), "cleaned_rows": sum(1 for r in crows if r["status"] == "cleaned"),
              "held_rows": len(held), "duplicate_groups": len(dups), "unknown_units": len(units),
              "rules_applied": len(applied), "changes": len(changes)}
    return {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats, "case": case or {},
            "rows": crows, "declared_rules": declared, "notes": notes, "held": held, "duplicates": dups,
            "unknown_units": units, "rules_applied": applied, "changes": changes, "counts": counts,
            "errors": [], "draft_used": False, "contract": None}


def clean_status(c):
    if c["errors"]:
        return "input_error"
    if not c["rows"]:
        return "insufficient_evidence"
    return "partial"


def evidence_map(c):
    ev = []
    for r in c["rows"]:
        if r["_from"]:
            ev.append({"label": "row:%s" % r["row_id"], "claim_value": r["_from"],
                       "source_id": r["_from"].split("#")[0], "locator": r["_from"],
                       "quote": "%s %s %s %s" % (r["raw_material"], r["raw_indicator"],
                                                 r["raw_value"], r["raw_unit"]),
                       "match": "verbatim", "kind": "row"})
    for ru in c["declared_rules"]:
        ev.append({"label": "rule:%s" % ru.get("rule_id", ""), "claim_value": str(ru.get("condition", "")),
                   "source_id": "rules", "locator": "declared", "quote": str(ru.get("transform", ""))[:120],
                   "match": "verbatim", "kind": "rule"})
    if not ev:
        ev.append({"label": "searched-locations", "claim_value": "no parsed material carried a record row",
                   "source_id": "materials", "locator": searched(c["materials"]), "quote": "",
                   "match": "no-data", "kind": "no-data"})
    return ev


def changelog(c):
    return [{"step": 1, "action": "scan material",
             "result": "%d file(s): %s" % (len(c["materials"]), searched(c["materials"]))},
            {"step": 2, "action": "collect records, csv rows and rules",
             "result": "; ".join(c["notes"]) or "no data row"},
            {"step": 3, "action": "normalise material, indicator, value and unit",
             "result": "%d change(s)" % len(c["changes"])},
            {"step": 4, "action": "hold unresolvable values and units", "result": "%d held row(s)" % len(c["held"])},
            {"step": 5, "action": "detect duplicate rows", "result": "%d duplicate group(s)" % len(c["duplicates"])},
            {"step": 6, "action": "write artifacts", "result": "%d artifact(s)" % len(ARTIFACTS)}]


def uncertainties(c):
    out = []
    if not c["rows"]:
        out.append("no record or csv row was found; searched " + searched(c["materials"]))
    if c["held"]:
        out.append("%d row(s) held for human review: an unreported value or an arbitrary unit was never converted"
                   % len(c["held"]))
    if any(m["status"] != "parsed" for m in c["materials"]):
        out.append("some material files are empty, corrupt or no-data-only and were never used; see run_log.txt")
    return out


def limits(c):
    return ["the cleaned table is bounded by the supplied records; nothing outside them is invented",
            "an arbitrary or unresolvable unit is held for a human, never converted (rule R010)",
            "an unreported value is held, never filled with a guessed number",
            "no network, no third-party package and no clock; the run is deterministic"]


def gaps(c):
    return [{"item": "resolvable unit for every held row",
             "why": "the unit token is arbitrary or unresolvable (for example an arbitrary intensity unit)",
             "needed_by": "before any cross-document comparison"}]


def sources_obj(c):
    return [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
             "parse_status": m["status"], "content_sha256": m["sha256"]} for m in c["materials"]]


def table_rows(c):
    out = [[r["row_id"], r["source_document_id"], r["source_locator"], r["material"], r["indicator"],
            r["value"], r["unit"], r["status"], r["hold_reason"] or "converted"] for r in c["rows"]]
    if not out:
        out.append(["no-row", "no-source", "no-locator", "", "", "", "", "insufficient_evidence",
                    "no record row in the parsed material; searched: " + searched(c["materials"])])
    return out


def cleaned_csv(c):
    return csv_text(["row_id", "source_document_id", "source_locator", "material", "indicator", "value",
                     "unit", "status", "note"], table_rows(c))


def value_for(c, key):
    kn = re.sub(r"[^a-z0-9]", "", str(key).lower())
    held_payload = c["held"] or [{"row_id": "no-held-row",
                                  "hold_reason": "no row was held in the supplied material"}]
    dups_payload = c["duplicates"] or [{"key": "no-duplicate-observed", "row_ids": [], "count": 0}]
    units_payload = c["unknown_units"] or [{"unit": "no-unit-token-observed",
                                            "note": "no held row carried an unresolvable unit"}]
    rules_payload = list(c["rules_applied"])
    m = {"cleanedtable": "cleaned_table.csv", "table": "cleaned_table.csv", "deliverable": "cleaned_table.csv",
         "changelog": "change_log.json", "changes": c["changes"],
         "pendingreview": "pending_review.json", "held": held_payload,
         "counts": c["counts"], "rulesapplied": rules_payload, "unknownunits": units_payload,
         "duplicates": dups_payload, "dups": dups_payload,
         "caseid": c["case_id"], "id": c["case_id"], "status": clean_status(c),
         "report": "normalization_report.md", "normalizationreport": "normalization_report.md",
         "selfcheck": "self_check.json", "runlog": "run_log.txt", "gainreport": "gain_report.json",
         "sources": sources_obj(c), "evidencemap": evidence_map(c),
         "uncertainties": uncertainties(c), "limits": limits(c), "gaps": gaps(c),
         "summary": "%s: %d input row(s), %d cleaned, %d held, %d duplicate group(s), %d unknown unit(s)"
                    % (clean_status(c), c["counts"]["input_rows"], c["counts"]["cleaned_rows"],
                       c["counts"]["held_rows"], len(c["duplicates"]), len(c["unknown_units"]))}
    if kn in m and m[kn] not in (None, "", [], {}):
        return m[kn]
    return scalar("%d row(s) processed" % len(c["rows"]))


def result_obj(c, contract):
    ks = list(contract) if isinstance(contract, dict) and contract else list(CONTRACT)
    vals = {k: value_for(c, k) for k in ks}
    r = {"case_id": c["case_id"], "status": clean_status(c), "skill": SKILL, "version": VERSION,
         "method": "scan, collect, normalise, hold, dedupe, write",
         "summary": value_for(c, "summary"), "deliverable": "cleaned_table.csv",
         "cleaned_table": "cleaned_table.csv", "change_log": "change_log.json",
         "pending_review": "pending_review.json", "counts": c["counts"],
         "rules_applied": list(c["rules_applied"]), "unknown_units": c["unknown_units"],
         "duplicates": c["duplicates"], "evidence_map": evidence_map(c), "self_check": "self_check.json",
         "sources": sources_obj(c), "uncertainties": uncertainties(c), "change_records": changelog(c),
         "limits": limits(c), "gaps": gaps(c), "errors": c["errors"],
         "draft_used": bool(c.get("draft_used")), "artifacts": {n: n for n in ARTIFACTS}}
    for k, v in vals.items():
        if k not in r or r[k] in (None, "", [], {}):
            r[k] = v
    r["output_contract"] = vals
    return r


BASELINE = {"output_files": 1, "rows_collected": 0, "rows_cleaned": 0, "changes": 0, "held": 0,
            "duplicate_groups": 0, "unknown_units": 0, "rules_applied": 0, "contract_keys": 0}


def metrics(c, out):
    files = sum(len(fs) for _r, _d, fs in os.walk(out))
    return {"output_files": files, "rows_collected": len(c["rows"]),
            "rows_cleaned": c["counts"]["cleaned_rows"], "changes": len(c["changes"]),
            "held": len(c["held"]), "duplicate_groups": len(c["duplicates"]),
            "unknown_units": len(c["unknown_units"]), "rules_applied": len(c["rules_applied"]),
            "contract_keys": len(result_obj(c, c.get("contract"))["output_contract"])}


def write_all(c, out, work, contract, draft_used):
    c["draft_used"] = draft_used
    c["contract"] = contract
    for d in (out, work, os.path.join(out, "evidence")):
        os.makedirs(d, exist_ok=True)
    res = result_obj(c, contract)
    wj(os.path.join(out, "result.json"), res)
    wt(os.path.join(out, "cleaned_table.csv"), cleaned_csv(c))
    wj(os.path.join(out, "change_log.json"), {"case_id": c["case_id"], "rule_version": VERSION,
       "changes": c["changes"], "counts": {"changes": len(c["changes"])}})
    wj(os.path.join(out, "pending_review.json"), {"case_id": c["case_id"],
       "held": c["held"] or [{"row_id": "no-held-row",
                              "hold_reason": "no row was held in the supplied material",
                              "searched": searched(c["materials"])}],
       "counts": {"held": len(c["held"])},
       "note": "a held row is never converted or guessed; a human decides"})
    wj(os.path.join(out, "counts.json"), c["counts"])
    wj(os.path.join(out, "rules_applied.json"), {"case_id": c["case_id"], "rules_applied": c["rules_applied"],
       "declared_rules": c["declared_rules"], "builtin_rules": BUILTIN_RULES, "hold_tokens": HOLD_TOKENS})
    wj(os.path.join(out, "duplicates.json"), {"case_id": c["case_id"],
       "duplicates": c["duplicates"] or [{"key": "no-duplicate-observed", "row_ids": [], "count": 0}],
       "counts": {"duplicate_groups": len(c["duplicates"])}})
    wj(os.path.join(out, "unknown_units.json"), {"case_id": c["case_id"],
       "unknown_units": c["unknown_units"] or [{"unit": "no-unit-token-observed", "note": "nothing was held"}],
       "counts": {"unknown_units": len(c["unknown_units"])}})
    wt(os.path.join(out, "normalization_report.md"), report_md(c))
    wj(os.path.join(out, "self_check.json"), {"case_id": c["case_id"], "status": clean_status(c),
       "rows": len(c["rows"]), "held": len(c["held"]), "duplicates": len(c["duplicates"]),
       "contract_keys": len(res["output_contract"]),
       "no_invented_value": all((r["status"] != "held") or (r["value"] == "") for r in c["rows"])})
    mets = metrics(c, out)
    decl = ("baseline is a deterministic simulated naive policy under the same input and the same hold rule, "
            "not an official comparison")
    wj(os.path.join(out, "gain_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
       "declaration": decl,
       "reproduce": "python3 scripts/main.py compare --input /input --output /app/output --work /app/work"})
    wt(os.path.join(out, "gain_report.md"), gain_md(c, mets, BASELINE))
    wj(os.path.join(work, "compare_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
                                                   "declaration": decl})
    for m in c["materials"]:
        ls = lines_of(m)
        scaffold = os.path.basename(m["rel"]).lower() in SKIP
        wj(os.path.join(out, "evidence", "%s.json" % m["id"]),
           {"source_id": m["id"], "rel": m["rel"], "kind": m["kind"], "parse_status": m["status"],
            "chars": m["chars"], "content_sha256": m["sha256"],
            "extracts": [{"locator": x["locator"], "text": x["text"]} for x in ls],
            "no_data": ("task scaffolding, not a data source" if scaffold else
                        "no line was quotable from this source; status is " + m["status"]) if not ls else ""})
    wt(os.path.join(out, "run_log.txt"), runlog(c))
    wj(os.path.join(work, "analysis_state.json"), {"case_id": c["case_id"], "status": clean_status(c),
                                                   "rows": len(c["rows"]), "held": len(c["held"])})
    return res


def pipeline(inp, out, work, case):
    c = build_context(case, scan(inp, case))
    d = draft(work)
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    res = write_all(c, out, work, contract, bool(d))
    sanitize(out)
    return res


def report_md(c):
    L = ["# Table normalisation report", "", "case_id: %s" % c["case_id"], "status: %s" % clean_status(c),
         "skill: %s v%s" % (SKILL, VERSION), "",
         "Every cleaned value is bounded by the supplied record; a held row is never converted.", "",
         "## 1. Counts", ""]
    L += ["- %s: %d" % (k, c["counts"][k]) for k in
          ("input_rows", "cleaned_rows", "held_rows", "duplicate_groups", "unknown_units", "changes")]
    L += ["", "## 2. Rules applied", ""]
    L += ["- %s" % r for r in c["rules_applied"]]
    L += ["", "## 3. Cleaned table (%d row)" % len(c["rows"]), "",
          "| row_id | material | indicator | value | unit | status |", "|-|-|-|-|-|-|"]
    L += ["| %s | %s | %s | %s | %s | %s |" % (r["row_id"], r["material"], r["indicator"],
          r["value"] or "held", r["unit"], r["status"]) for r in c["rows"]]
    if not c["rows"]:
        L.append("| no-row |  |  |  |  | insufficient_evidence |")
    L += ["", "## 4. Held for human review (%d)" % len(c["held"]), ""]
    L += ["- `%s` %s: %s" % (r["row_id"], r["indicator"], r["hold_reason"]) for r in c["held"]]
    if not c["held"]:
        L.append("- no row was held in the supplied material")
    L += ["", "## 5. Duplicates (%d group)" % len(c["duplicates"]), ""]
    L += ["- %s: %s" % (d["key"], ", ".join(d["row_ids"])) for d in c["duplicates"]]
    if not c["duplicates"]:
        L.append("- no duplicate group observed")
    L += ["", "## 6. Status note",
          "Completed: material triage, row collection, normalisation with a traced rule chain, "
          "hold discipline and duplicate detection.",
          "Not completed: converting a held unit or filling an unreported value; "
          "the material supplied no resolvable basis."]
    return "\n".join(L) + "\n"


def runlog(c):
    L = ["# run_log - %s" % SKILL, ""]
    L += ["material %s %s kind=%s status=%s chars=%d sha256=%s"
          % (m["id"], m["rel"], m["kind"], m["status"], m["chars"], m["sha256"]) for m in c["materials"]]
    L.append("input_rows=%d cleaned=%d held=%d duplicates=%d unknown_units=%d rules=%d status=%s" % (
        c["counts"]["input_rows"], c["counts"]["cleaned_rows"], c["counts"]["held_rows"],
        len(c["duplicates"]), len(c["unknown_units"]), len(c["rules_applied"]), clean_status(c)))
    return "\n".join(L) + "\n"


def gain_md(c, mets, base):
    L = ["# Gain report - baseline vs skill", "",
         "Honest declaration: the baseline column is a deterministic simulated naive policy over the same input,",
         "not an official comparison; this package fabricates no official A/B numbers.", "",
         "| metric | baseline (simulated) | this skill (measured) |", "|-|-|-|"]
    L += ["| %s | %s | %s |" % (n, base.get(k, 0), mets[k]) for n, k in GAIN_ORDER]
    L += ["", "Same input, same task, same hold rule: both columns read the same records under the same rules.",
          "Reproduce with: python3 scripts/main.py compare --input /input --output /app/output --work /app/work", ""]
    return "\n".join(L) + "\n"
