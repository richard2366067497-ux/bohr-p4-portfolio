"""clean_report.py - verification and rendering layer for extraction-table-auditor.

Runtime path/resource helpers, mechanical validation of the agent workbook,
artifact rendering, post-run recomputation, the two-run determinism check and
the internal gain contrast. Kept separate from main.py so that both stay small
and each concern can be read on its own.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

from clean_engine import (CANON, CHG, PEND, Units, artifact_names, clip, dump_json,  # noqa: F401
                          exec_formula, iter_files, load_json, verify_quote, write_csv)
from clean_flow import discover  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
REF = BASE / "references"

V = "1.0.0"

ALLOWED = ("", "accept", "convert", "hold", "missing", "review", "pending")

def paths(a):
    def first(cs):
        return next((Path(c) for c in cs if Path(c).exists()), Path(cs[0]))
    inp = Path(a.inp).resolve() if a.inp else first(["/input", str(BASE / "input"), str(BASE.parent / "input")])
    has_app = Path("/app").exists()
    out = Path(a.out).resolve() if a.out else (Path("/app/output") if has_app else BASE.parent / "output")
    work = Path(a.work).resolve() if a.work else (Path("/app/work") if has_app else BASE.parent / "work")
    return inp, out, work, (Path(a.draft).resolve() if a.draft else work / "draft.json")

def refs(inp=None):
    """Field dictionary / unit table are case-scoped: prefer the input's own copies,
    fall back to the packaged references, and degrade to builtins when neither exists."""
    errs = []
    pool = iter_files(inp) if inp is not None and Path(inp).exists() else []

    def pick(name):
        for cand in pool:
            if cand.name == name:
                return cand
        return REF / name

    fp = pick("field_dictionary.json")
    up = pick("unit_table.json")
    rp = REF / "rule_catalog.json"
    fdict, e1 = load_json(fp)
    utab, e2 = load_json(up)
    rcat, e3 = load_json(rp)
    for path, err in ((fp, e1), (up, e2), (rp, e3)):
        if err:
            errs.append({"stage": "references", "file": path.name, "error": err})
    fdict = fdict if isinstance(fdict, dict) else {}
    if not isinstance(utab, dict) or not utab.get("units"):
        utab = {"version": "fallback", "units": {"1": {"dim": {}, "scale": 1.0}}}
        errs.append({"stage": "references", "error": "unit_table unusable; fallback table"})
    rules = (rcat or {}).get("rules") if isinstance(rcat, dict) else rcat
    return fdict, utab, (rules if isinstance(rules, list) else []), errs

def index(inp, work, fdict, utab, rules):
    idx, _ = load_json(work / "index.json")
    if isinstance(idx, dict) and idx.get("version") and idx.get("input_root") == str(inp):
        return idx
    return discover(inp, fdict, rules, Units(utab))

def env(case_id=None):
    return {"case_id": case_id, "status": "partial", "result": {}, "claims": [], "uncertainties": [],
            "uncertainty": [], "sources": [], "pending_human": [], "errors": [], "degradations": [],
            "changes": [], "contract_mapping": {},
            "runtime": {"tool": "extraction-table-auditor", "version": V, "python": sys.version.split()[0],
                        "offline": True, "stdlib_only": True}}

def cpaths(tpl, path="", acc=None):
    acc = [] if acc is None else acc
    if isinstance(tpl, dict):
        for k, v in tpl.items():
            cpaths(v, (path + "." if path else "") + str(k), acc)
    elif isinstance(tpl, list):
        for i, v in enumerate(tpl):
            cpaths(v, "%s[%d]" % (path, i), acc)
    else:
        acc.append(path)
    return acc

def getp(res, path):
    node = res
    for part in path.replace("]", "").replace("[", ".").split("."):
        if part == "":
            continue
        if isinstance(node, dict):
            node = node.get(part, "__missing__")
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return "__missing__"
    return node

def coverage(tpl, res):
    ps = cpaths(tpl or {})
    if not ps:
        return {"paths": 0, "filled": 0, "pct": 100.0, "missing": []}
    miss = [p for p in ps if getp(res, p) == "__missing__"]
    return {"paths": len(ps), "filled": len(ps) - len(miss),
            "pct": round(100.0 * (len(ps) - len(miss)) / len(ps), 2), "missing": miss[:20]}

def validate(idx, draft, units):
    out = []

    def add(n, ok, d, h=""):
        out.append({"name": n, "pass": bool(ok), "detail": clip(d, 260), "hint": h})

    if draft is None:
        add("draft_present", False, "no readable draft.json",
            "python3 scripts/main.py show --part draft > <work>/draft.json")
        return out, ["draft_present"]
    objs = {o["row_id"]: o for o in idx["objects"]}
    locs = {o["locator"]: o for o in idx["objects"]}
    decs = {}
    rows = draft.get("rows") or []
    if isinstance(rows, dict):
        decs = {str(k): v for k, v in rows.items() if isinstance(v, dict)}
    else:
        for d in (rows if isinstance(rows, list) else []):
            if isinstance(d, dict) and (d.get("row_id") or d.get("locator")):
                decs[str(d.get("row_id") or d.get("locator"))] = d
    add("draft_present", True, "%d row decisions" % len(decs))
    add("case_id_match", not idx.get("case_id") or str(draft.get("case_id") or "") == str(idx.get("case_id")),
        "draft=%r index=%r" % (draft.get("case_id"), idx.get("case_id")), "copy case_id from show")
    bad = sorted(k for k, v in decs.items() if str(v.get("decision") or v.get("action") or "").lower() not in ALLOWED)
    add("decisions_valid", not bad, "invalid: %s" % (", ".join(bad[:8]) or "none"), "accept|convert|hold|missing")
    miss = sorted(set(objs) - set(decs) - set(k for k in decs if k in locs))
    add("row_coverage", not miss, "%d/%d rows decided; missing: %s" % (len(decs), len(objs), ", ".join(miss[:8]) or "none"),
        "every input row needs a decision or a group entry")
    ghosts = sorted(k for k in decs if k not in objs and k not in locs)
    add("locators_resolve", not ghosts, "unknown ids: %s" % (", ".join(ghosts[:8]) or "none"), "row_id must exist in show")
    gdec = {tuple(sorted(str(i) for i in (g.get("row_ids") or []))): g
            for g in draft.get("groups") or [] if isinstance(g, dict)}
    open_ = [g["group_id"] for g in idx["groups"] if not str((gdec.get(tuple(sorted(g["row_ids"]))) or {}).get("action")
                                                             or (gdec.get(tuple(sorted(g["row_ids"]))) or {}).get("decision") or "")]
    add("groups_decided", not open_, "%d/%d decided; open: %s" % (len(idx["groups"]) - len(open_), len(idx["groups"]),
                                                                 ", ".join(open_[:8]) or "none"), "merge|replicate|conflict|keep_separate")
    noreason = [g for g in gdec.values() if (g.get("action") or g.get("decision")) and not str(g.get("reason") or "").strip()]
    add("group_reasons", not noreason, "%d decided groups without a reason" % len(noreason),
        "the reason is what a reviewer reads")
    claims = [c for c in draft.get("claims") or [] if isinstance(c, dict)]
    unver, incomplete = [], []
    for c in claims:
        ev = c.get("evidence") or {}
        q = str(ev.get("quote") or c.get("quote") or "")
        loc = str(ev.get("locator") or c.get("locator") or "")
        rid = str(c.get("row_id") or (loc.split("#", 1)[1] if "#" in loc else ""))
        o = objs.get(rid) or locs.get(loc)
        if not c.get("statement") or not q or not (loc or rid):
            incomplete.append(clip(str(c.get("claim_id") or "?"), 24))
        elif not (o and verify_quote(o["blob"], q)[0]):
            unver.append(clip("%s:%s" % (c.get("claim_id", "?"), q), 56))
    add("claims_complete", not incomplete, "missing statement/quote/locator: %s" % (", ".join(incomplete[:6]) or "none"),
        "each claim needs statement + verbatim quote + locator")
    add("quote_verified", not unver, "%d/%d verbatim; bad: %s" % (len(claims) - len(unver), len(claims),
                                                                 "; ".join(unver[:3]) or "none"),
        "copy the quote character-for-character from the object line")
    conv_bad = []
    for rid, d in decs.items():
        if str(d.get("decision") or "").lower() != "convert":
            continue
        o = objs.get(rid) or locs.get(rid)
        tgt = str(d.get("unit_target") or "")
        if not o:
            continue
        if not tgt:
            conv_bad.append("%s:no-unit_target" % rid)
            continue
        r = units.convert((o["cells"].get("unit") or "").strip(), tgt)
        if not r.get("ok"):
            conv_bad.append("%s:%s" % (rid, r.get("reason")))
    add("conversions_recomputable", not conv_bad, "problems: %s" % (", ".join(conv_bad[:6]) or "none"),
        "unit_target must be dimensionally compatible")
    held = {k for k, v in decs.items() if str(v.get("decision") or "").lower() in ("hold", "review", "pending")}
    pend = {str(p.get("row_id") or "") for p in draft.get("pending") or [] if isinstance(p, dict)}
    add("pending_complete", held <= pend, "held rows without pending entry: %s"
        % (", ".join(sorted(held - pend)[:6]) or "none"), "declare reason_code + suggested_action")
    leak = sorted(k for k, v in decs.items() if str(v.get("decision") or "").lower() in ("hold", "missing")
                  and isinstance(v.get("value"), (int, float)))
    add("no_value_leak", not leak, "held rows with a numeric value: %s" % (", ".join(leak[:6]) or "none"),
        "unconfirmed values stay empty")
    add("field_map_declared", ("field_map" in draft) or bool(draft.get("unmapped_columns"))
        or not (idx.get("columns") or {}).get("unmapped"),
        "field_map=%d unmapped=%d" % (len(draft.get("field_map") or {}), len(draft.get("unmapped_columns") or [])),
        "list every unmapped column instead of dropping it")
    add("findings_present", bool(draft.get("findings")), "%d findings" % len(draft.get("findings") or []),
        "one conclusion per indicator family, each with locators")
    return out, [c["name"] for c in out if not c["pass"]]

def load_draft(p):
    if not Path(p).exists():
        return None, "draft not found: %s" % p
    o, err = load_json(p)
    if err or not isinstance(o, dict):
        return None, err or "draft is not a JSON object"
    return o, None

def cmd_check(a):
    inp, out, work, dp = paths(a)
    fdict, utab, rules, _ = refs(inp)
    idx = index(inp, work, fdict, utab, rules)
    draft, _ = load_draft(dp)
    checks, blocking = validate(idx, draft, Units(utab))
    rep = {"draft": str(dp), "checks": checks, "pass": len(checks) - len(blocking), "total": len(checks),
           "blocking": blocking, "pass_rate": round(100.0 * (len(checks) - len(blocking)) / len(checks), 2)}
    work.mkdir(parents=True, exist_ok=True)
    dump_json(work / "check_report.json", rep)
    for c in checks:
        print("[%s] %-24s %s" % ("PASS" if c["pass"] else "FAIL", c["name"], c["detail"]))
        if not c["pass"] and c.get("hint"):
            print("        hint: %s" % c["hint"])
    print("[check] %d/%d pass (%.0f%%); blocking=%s" % (rep["pass"], rep["total"], rep["pass_rate"],
                                                        ", ".join(blocking) or "none"))
    print("[check] report -> %s ; next: fix FAIL lines then build" % (work / "check_report.json"))
    return 0


# ----------------------------------------------------------------------- build

def render(out, idx, comp, names, utab):
    write_csv(out / names["cleaned.csv"], comp["rows"], CANON)
    write_csv(out / names["change_log.csv"], comp["changes"], CHG)
    write_csv(out / names["pending_review.csv"], comp["pending"], PEND)
    applied = {}
    for rec in comp["changes"] + comp["pending"]:
        key = rec.get("rule_id") or "pending:" + rec.get("reason_code", "")
        applied[key] = applied.get(key, 0) + 1
    dump_json(out / names["rules.json"], {
        "version": idx.get("version", V), "rules": idx["rules"],
        "suppressed_rules": idx["suppressed_rules"], "applied_counts": applied,
        "precedence": "lower priority number wins; case rules default to 5, builtin 100+; rules with "
                      "owner=agent require a human/agent decision instead of a mechanical transform"})
    dump_json(out / names["field_mapping.json"], {
        "schema_source": (idx.get("schema") or {}).get("source", "builtin"),
        "columns": [{"original": k, "role": v} for k, v in sorted((idx.get("columns") or {}).get("roles", {}).items())],
        "condition_columns": (idx.get("columns") or {}).get("conditions", []),
        "indicator_to_field": [{"indicator": k, "field": v} for k, v in sorted(comp["indicator_map"].items())],
        "material_to_label": [{"material": k, "label": v} for k, v in sorted(comp["material_map"].items())],
        "unmapped": (idx.get("columns") or {}).get("unmapped", []),
        "note": "a column is either mapped to a role/target field or listed in unmapped; nothing is dropped "
                "silently and no mapping is guessed"})
    table = dict(utab)
    seen = {}
    for rec in comp["changes"]:
        if rec.get("factor") in ("", None):
            continue
        key = "%s -> %s" % (rec["unit_before"], rec["unit_after"])
        e = seen.setdefault(key, {"from": rec["unit_before"], "to": rec["unit_after"],
                                  "factor": rec["factor"], "offset": rec["offset"], "count": 0})
        e["count"] += 1
    table["observed_conversions"] = [seen[k] for k in sorted(seen)]
    table["unresolved_units"] = sorted({p["original_unit"] for p in comp["pending"]
                                        if p["reason_code"] in ("unknown_unit", "ambiguous_unit")})
    dump_json(out / names["unit_table.json"], table)
    (out / names["anomaly_report.md"]).write_text(report_md(idx, comp), encoding="utf-8")

def report_md(idx, comp):
    c, reasons = comp["counts"], {}
    for p in comp["pending"]:
        reasons[p["reason_code"]] = reasons.get(p["reason_code"], 0) + 1
    un = (idx.get("columns") or {}).get("unmapped") or []
    L = ["# 清洗与标准化报告 / cleaning report", "", "- case_id: %s" % idx.get("case_id"),
         "- rows: %d in / %d table / %d analytic" % (c["input_rows"], c["cleaned_rows"], c["analytic_rows"]),
         "- changed values %d | pending %d | merged duplicates %d | conflicts %d"
         % (c["changed_values"], c["pending_review"], c["merged_duplicates"], c["conflicts"]),
         "", "## 1 字段规范 (field standardisation)",
         "- mapped columns %d; unmapped kept and reported: %s"
         % (len((idx.get("columns") or {}).get("roles") or {}), ", ".join(un[:12]) or "none"),
         "- indicator→field: %s" % (", ".join("%s→%s" % kv for kv in sorted(comp["indicator_map"].items())[:10]) or "none"),
         "", "## 2 单位换算 (unit conversion)",
         "- converted values %d; each change_log row carries before/factor/offset/formula/precision"
         % len([x for x in comp["changes"] if x["field"] in ("value", "value_low", "value_high", "value_err")]),
         "- unresolved units stay empty and are queued: %s" % (", ".join(sorted(reasons)) or "none"),
         "", "## 3 同义归一 (synonym normalisation)",
         "- material labels: %s" % (", ".join("%s→%s" % kv for kv in sorted(comp["material_map"].items())[:10]) or "none"),
         "", "## 4 缺失与异常 (missing / anomalous)",
         "- missing %d | needs_review %d | range bounds kept %d | ± error kept %d"
         % (c["missing_values"], c["needs_review"], c["range_values"], c["error_term_values"]),
         "", "## 5 重复与冲突 (duplicates / conflicts)",
         "- candidate groups %d, decided %d" % (c["groups"], c["groups_decided"])]
    L += ["- %s signal=%s rows=%s unit_variants=%s why=%s" % (g["group_id"], g["signal"], ",".join(g["row_ids"]),
                                                             g["unit_variants"], g["reason"]) for g in comp["groups"]]
    L += ["", "## 6 来源与变更记录 (sources / change records)",
          "- every row carries row_id + source_document_id + rule_ids + judgment_key",
          "- every claim carries a locator and a verbatim quote from the source cell",
          "", "## 7 待确认 (pending human decisions)"]
    L += ["- %s `%s` %s → %s" % (p["row_id"], p["reason_code"], p["reason"], p["suggested_action"])
          for p in comp["pending"][:40]] or ["- none"]
    L += ["", "## 8 边界 (limits)",
          "- never guesses a unit, never writes 0 for a missing value, never merges rows whose source or "
          "conditions differ",
          "- condition columns are kept verbatim and never unit-converted",
          "- values needing adjudication are excluded from the analytic table and listed above"]
    return "\n".join(L) + "\n"

def read_csv(p):
    if not Path(p).exists():
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))

def recompute_ok(rec):
    after = exec_formula(rec.get("before"), rec.get("factor") or 0, rec.get("offset") or 0)
    try:
        target = float(rec.get("after"))
    except (TypeError, ValueError):
        return True
    return after is None or abs(after - target) <= 1e-6 * max(1.0, abs(target))

def determinism(inp, work, dp):
    dirs = [work / "_det1", work / "_det2"]
    blobs = []
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parent / "main.py"), "build",
                        "--in", str(inp),
                        "--out", str(d), "--work", str(d), "--draft", str(dp)], capture_output=True, timeout=600)
        blobs.append({p.name: p.read_bytes() for p in sorted(d.iterdir()) if p.is_file()})
    names = sorted(set(blobs[0]) | set(blobs[1]))
    diff = [n for n in names if blobs[0].get(n) != blobs[1].get(n)]
    for d in dirs:
        for p in sorted(d.iterdir()):
            p.unlink()
        d.rmdir()
    return {"checked": True, "identical": bool(names) and not diff, "files": names, "diff": diff}

def gain(idx, res, rate, cl, pend, chg):
    r = res.get("result") or {}
    c, cov = r.get("counts") or {}, r.get("coverage") or {}
    return [{"id": "field_normalisation", "baseline": "0% (raw header passthrough)",
             "definition": "source columns mapped to a role or explicitly declared unmapped",
             "delivered": "%s mapped + %d declared unmapped" % (cov.get("columns_mapped", 0), len(cov.get("columns_unmapped") or []))},
            {"id": "conversion_recomputable", "baseline": "no change log at all",
             "definition": "change-log rows reproducible from before/factor/offset",
             "delivered": "%.1f%% of %d rows" % (rate, chg)},
            {"id": "source_traceability", "baseline": "0 rows (no rule ids in raw input)",
             "definition": "rows carrying row_id + source + rule_ids",
             "delivered": "%s of %s rows" % (cov.get("rows_with_rule_ids", 0), c.get("cleaned_rows", cl))},
            {"id": "uncertainty_isolation", "baseline": "0 (raw text stays in the table)",
             "definition": "unconfirmed values kept out of the analytic table",
             "delivered": "%d pending items isolated" % pend},
            {"id": "duplicate_decisions", "baseline": "0 of %s" % c.get("groups", 0),
             "definition": "candidate groups with an explicit reasoned decision",
             "delivered": "%s of %s" % (c.get("groups_decided", 0), c.get("groups", 0))}]

def cmd_selfcheck(a):
    inp, out, work, dp = paths(a)
    fdict, utab, rules, _ = refs(inp)
    idx = index(inp, work, fdict, utab, rules)
    res, _ = load_json(out / "result.json")
    res = res if isinstance(res, dict) else env()
    names = idx.get("artifact_names") or artifact_names({})
    cl = read_csv(out / names["change_log.csv"])
    cleaned = read_csv(out / names["cleaned.csv"])
    pend = read_csv(out / names["pending_review.csv"])
    ok = sum(1 for r in cl if recompute_ok(r))
    rate = 100.0 * ok / len(cl) if cl else 100.0
    counts = (res.get("result") or {}).get("counts") or {}
    checks = [{"name": "change_log_recomputes", "pass": ok == len(cl),
               "detail": "%d/%d rows satisfy after = before*factor + offset" % (ok, len(cl))},
              {"name": "counts_match_artifacts",
               "pass": all(counts.get(k) == v for k, v in (("cleaned_rows", len(cleaned)),
                                                           ("change_log_rows", len(cl)), ("pending_review", len(pend))) if k in counts),
               "detail": "cleaned=%d change=%d pending=%d" % (len(cleaned), len(cl), len(pend))}]
    ids = [r.get("row_id") for r in cleaned]
    checks.append({"name": "row_ids_unique", "pass": len(ids) == len(set(ids)),
                   "detail": "%d ids / %d unique" % (len(ids), len(set(ids)))})
    known = {str(r.get("rule_id")) for r in idx["rules"]}
    used = {r.get("rule_id") for r in cl} | {r.get("rule_id") for r in cleaned if r.get("rule_id")}
    checks.append({"name": "rule_ids_resolve", "pass": not (used - known),
                   "detail": "unresolved: %s" % (", ".join(sorted(x for x in used - known if x)[:8]) or "none")})
    by_id = {o["row_id"]: o for o in idx["objects"]}
    bad = [c.get("claim_id") for c in res.get("claims") or []
           if not (by_id.get(str(c.get("row_id"))) and verify_quote(by_id[str(c.get("row_id"))]["blob"],
                                                                    (c.get("evidence") or {}).get("quote", ""))[0])]
    checks.append({"name": "claims_quote_verified", "pass": not bad,
                   "detail": "%d claims, %d unverified" % (len(res.get("claims") or []), len(bad))})
    cov = coverage(idx.get("contract") or idx.get("output_contract") or {}, res)
    checks.append({"name": "contract_complete", "pass": not cov["missing"],
                   "detail": "%d/%d contract paths present" % (cov["filled"], cov["paths"])})
    det = {"checked": False, "identical": None, "files": []}
    if not a.no_rerun:
        det = determinism(inp, work, dp)
        checks.append({"name": "deterministic_rerun", "pass": det["identical"] is not False,
                       "detail": "%d files compared" % len(det["files"])})
    rep = {"checks": checks, "pass": len([c for c in checks if c["pass"]]), "total": len(checks),
           "formula_consistency_pct": round(rate, 2), "determinism": det, "contract_coverage": cov,
           "gain": gain(idx, res, rate, len(cleaned), len(pend), len(cl)),
           "gain_note": "internal contrast against a raw passthrough of the same input; it is a "
                        "reproducibility check, not a platform score"}
    dump_json(out / "selfcheck.json", rep)
    for c in checks:
        print("[%s] %-24s %s" % ("PASS" if c["pass"] else "FAIL", c["name"], c["detail"]))
    print("[selfcheck] gain versus raw passthrough (same input):")
    for g in rep["gain"]:
        print("  %-24s baseline=%-32s delivered=%s" % (g["id"], g["baseline"], g["delivered"]))
    print("[selfcheck] %d/%d pass; report -> %s" % (rep["pass"], rep["total"], out / "selfcheck.json"))
    return 0
