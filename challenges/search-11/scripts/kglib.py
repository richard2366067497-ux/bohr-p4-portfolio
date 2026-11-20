# -*- coding: utf-8 -*-
"""patent-search-dossier engine (v9): scan, locate, normalise numbers, status provenance, licence
gate, boundaries, evidence snapshots and artifact writing. Standard library only, offline, deterministic.
The io/render layer (token normalisation, safe writers, png figure, markdown renderers) lives in render.py."""
import json
import os
import re
import unicodedata

from render import (ARTIFACTS, BIN_EXT, SKILL, SKIP, VERSION, clean, csv_text, degenerate, dossier_status,
                    dossiers_md, gain_md, license_gate_md, rd, render_figure, rj, runlog, safe, sanitize,
                    searched, sha, wj, wt)

CONTRACT = ["case_id", "status", "deliverable", "evidence_map", "change_log", "coverage"]


# ---------------------------------------------------------------- materials
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
    """Non-empty source lines with an M#/p# locator. Only 'parsed' material is quotable, and task
    scaffolding (case.json / task.md / README) is never treated as a searchable source."""
    if m["status"] != "parsed" or os.path.basename(m["rel"]).lower() in SKIP:
        return []
    out = []
    for i, ln in enumerate(m["text"].splitlines()):
        s = ln.strip()
        if s:
            out.append({"locator": "%s/p%d" % (m["id"], i + 1), "text": s})
    return out


# ---------------------------------------------------------------- number normalisation
NUM_RE = re.compile(
    r"(?:PCT/[A-Z]{2}\d{4}/\d{6})"
    r"|(?:(?:US|WO|EP|CN|JP|KR|DE|FR|GB)\s?\d[\d\s,./-]{4,20}[A-Z]?\d?)"
    r"|(?:\b\d{1,2}/\d{3},\d{3}\b)"
    r"|(?:\b\d{1,3}(?:,\d{3}){2,}\b)")


def doc_type(country, kind, core, raw_slash):
    if country == "WO":
        return "pct_publication"
    if country == "EP":
        return "ep_publication" if (kind.startswith("A") or not kind) else "ep_grant"
    if country == "US":
        if kind.startswith("B"):
            return "us_grant"
        if kind.startswith("A"):
            return "us_publication" if len(core) == 11 else "us_grant"
        if raw_slash:
            return "us_application"
        if len(core) == 8:
            return "us_grant"
        return "us_application"
    if not kind:
        return "national_publication" if len(core) >= 7 else "national_application"
    return "national_publication" if kind.startswith("A") else "national_grant"


def normalize_number(raw):
    txt = unicodedata.normalize("NFKC", str(raw))
    raw_slash = "/" in txt
    rules = ["strip_separators"]
    s = re.sub(r"[　\s,./\-]", "", txt).upper()
    country, inferred, pstatus, kind, core = "", "", "parsed", "", ""
    if s.startswith("PCT"):
        m = re.match(r"^PCT([A-Z]{2})(\d{4})(\d+)$", s)
        if m:
            country, yr, ser = m.group(1), m.group(2), m.group(3)[-6:]
            rules += ["pct_application_to_wo", "cc:PCT->%s" % country, "kind:pct"]
            return {"raw": txt.strip(), "norm": "WO" + yr + ser, "country": country, "kindcode": "pct",
                    "year": yr, "doc_type": "pct_application", "parse_status": "parsed",
                    "inferred_country": "", "rules": rules}
    m = re.match(r"^([A-Z]{2})(.+)$", s)
    if m:
        country, rest = m.group(1), m.group(2)
        rules.append("cc:%s" % country)
    else:
        rest = s
        rules.append("cc:inferred")
    km = re.match(r"^(.*?)([A-Z]\d?)$", rest)
    if km and len(km.group(1)) >= 5:
        core, kind = km.group(1), km.group(2)
        rules.append("kind:%s" % kind)
    else:
        core = rest
        if km:
            rules.append("kind:not-stripped (core below 5)")
    if not country:
        if re.fullmatch(r"\d{8}", core):
            country, inferred, pstatus = "US", "US", "ambiguous"
            rules.append("inferred_country:US")
        else:
            pstatus = "unparsed"
            rules.append("unparsed:no-country")
    dt = doc_type(country, kind, core, raw_slash)
    rules.append("doc_type:%s" % dt)
    norm = (country + core + kind) if country else (core + kind)
    year = core[:4] if (dt in ("us_publication", "pct_publication", "national_publication") and len(core) >= 4) else ""
    return {"raw": txt.strip(), "norm": norm, "country": country, "kindcode": kind, "year": year,
            "doc_type": dt, "parse_status": pstatus, "inferred_country": inferred, "rules": rules}


def find_numbers(mats):
    found, order = {}, []
    for m in mats:
        for ln in lines_of(m):
            for raw in NUM_RE.findall(ln["text"]):
                r = normalize_number(raw)
                if not r["norm"]:
                    continue
                loc = {"source_id": m["id"], "locator": ln["locator"], "quote": safe(ln["text"])}
                if r["norm"] not in found:
                    r["located_at"] = [loc]
                    found[r["norm"]] = r
                    order.append(r["norm"])
                else:
                    found[r["norm"]]["located_at"].append(loc)
    return [found[k] for k in order]


# ---------------------------------------------------------------- evidence map
CITE_KEYS = [
    ("number-discipline", "公开号、申请号、授权号、优先权号各自登记"),
    ("number-rule-chain", "规则顺序"),
    ("status-discipline", "不得推断"),
    ("family-scope", "关键词命中"),
    ("licence-default", "材料未声明许可"),
]


def citations(mats):
    out = []
    for label, needle in CITE_KEYS:
        for m in mats:
            hit = False
            for ln in lines_of(m):
                if needle in ln["text"]:
                    out.append({"claim": label, "source_id": m["id"], "locator": ln["locator"], "quote": ln["text"],
                                "match": "verbatim" if safe(ln["text"]) == ln["text"] else "verbatim-normalised"})
                    hit = True
                    break
            if hit:
                break
    return out


def evidence_map(reg, cites, mats):
    ev = []
    for c in cites:
        ev.append({"label": c["claim"], "claim_value": c["quote"], "source_id": c["source_id"],
                   "locator": c["locator"], "quote": c["quote"], "match": c["match"], "kind": "rule"})
    for r in reg:
        a = r["located_at"][0]
        ev.append({"label": "number-specimen:%s" % r["norm"], "claim_value": r["norm"], "source_id": a["source_id"],
                   "locator": a["locator"], "quote": a["quote"],
                   "match": "verbatim" if safe(a["quote"]) == a["quote"] else "verbatim-normalised", "kind": "specimen"})
    if not ev:
        ev.append({"label": "searched-locations", "claim_value": "no parsed material carried quotable text",
                   "source_id": "materials", "locator": searched(mats), "quote": "", "match": "no-data", "kind": "no-data"})
    return ev


def selfcheck_ok(ev):
    return bool(ev) and all(e.get("match") in ("verbatim", "verbatim-normalised", "no-data") for e in ev)


# ---------------------------------------------------------------- status / licence / boundaries
def status_entries(reg, mats):
    rows = []
    for r in reg:
        a = r["located_at"][0]
        rows.append({"patent_id": r["norm"], "status_value": "unknown", "as_of": "not-recorded-no-clock",
                     "query_date": "not-recorded-no-clock", "source_kind": "not-declared",
                     "source_id": a["source_id"], "locator": a["locator"], "confidence": "low",
                     "needs_official_verification": "true",
                     "note": "no official register page was supplied; the status stays unknown and must not be read as granted or lapsed"})
    if not rows:
        rows.append({"patent_id": "no-record", "status_value": "unknown", "as_of": "not-recorded-no-clock",
                     "query_date": "not-recorded-no-clock", "source_kind": "not-declared", "source_id": "materials",
                     "locator": "materials/*", "confidence": "low", "needs_official_verification": "true",
                     "note": "no parsed material carried a locatable number; searched: " + searched(mats)})
    return rows


def licence_entries(mats):
    rows = []
    lic = [(c["source_id"], c["locator"], c["quote"]) for c in citations(mats) if c["claim"] == "licence-default"]
    note = lic[0][2] if lic else "no licence statement was supplied for any source"
    for m in mats:
        rows.append({"source_id": m["id"], "source_name": m["rel"], "tier": "yellow",
                     "display_scope": "conclusions, field names and locators only; no long verbatim excerpt",
                     "degrade_plan": "quote only the conclusion plus source_id/locator, never a long run of source text",
                     "excluded_from_output": "false", "reason": note})
    return rows


def boundaries(reg, edges, mats, lics):
    src = searched(mats)
    b = [{"type": "legal_status_unknown", "item": "legal status of every registered number",
          "detail": "no official register page was supplied, so every status stays unknown",
          "impact": "the dossier cannot be used for validity, freedom-to-operate or infringement purposes", "source": src}]
    if not reg:
        b.append({"type": "coverage_gap", "item": "no locatable patent number",
                  "detail": "no parsed material carried a patent number, so the number and family lanes are empty",
                  "impact": "identification and family conclusions are limited to what the material stated", "source": src})
    else:
        b.append({"type": "coverage_gap", "item": "no located patent record",
                  "detail": "%d number(s) were normalised, but the material states a rule table rather than a located patent record" % len(reg),
                  "impact": "no title, assignee, filing date or claim text can be read for a real document", "source": src})
    b.append({"type": "metadata_missing", "item": "query date and as-of date",
              "detail": "the runtime provides no clock, so as_of is not-recorded-no-clock",
              "impact": "any future status check must re-query and record the date at that time", "source": "runtime: clock disabled"})
    if not edges:
        b.append({"type": "coverage_gap", "item": "observed family links",
                  "detail": "no family link was observed in the material, so the graph carries isolated nodes only",
                  "impact": "the family is not shown to be exhaustive and no equivalence of claim scope is implied", "source": src})
    else:
        b.append({"type": "family_not_exhaustive", "item": "observed family links",
                  "detail": "%d observed link(s) were recorded; the family may still be incomplete" % len(edges),
                  "impact": "family conclusions are limited to the observed links", "source": src})
    b.append({"type": "license_restricted", "item": "licence of %d source(s)" % len(lics),
              "detail": "no licence was declared, so every source is handled as the yellow tier",
              "impact": "only conclusions, field names and locators leave the dossier; no long excerpt is shown",
              "source": "field-dictionary section 5"})
    b.append({"type": "claim_scope_unexplained", "item": "claim scope",
              "detail": "claim text was not supplied, so no scope or equivalence judgement is made",
              "impact": "claim wording must be read from the official register before any scope use", "source": src})
    b.append({"type": "patent_vs_paper_scope", "item": "patent and technical literature lanes",
              "detail": "patents are located by number and literature by topic; the two lanes are never merged into one ranking",
              "impact": "a topic lane with no hit stays empty rather than borrowing a patent hit", "source": src})
    return b


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


def context(case, mats):
    reg = find_numbers(mats)
    cites = citations(mats)
    lics = licence_entries(mats)
    sts = status_entries(reg, mats)
    bnd = boundaries(reg, [], mats, lics)
    ev = evidence_map(reg, cites, mats)
    fam_nodes = [{"id": "N%d" % (i + 1), "number_norm": r["norm"], "title": "", "doc_type": r["doc_type"]}
                 for i, r in enumerate(reg)]
    return {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats, "case": case or {},
            "registry": reg, "cites": cites, "licences": lics, "status": sts, "boundaries": bnd,
            "evidence_map": ev, "family_nodes": fam_nodes, "family_edges": [], "draft_used": False,
            "contract": None, "errors": []}


def coverage(c):
    facets = {"number_lane": bool(c["registry"]), "family": bool(c["family_edges"]),
              "legal_status": bool(c["status"]), "claims": bool(c["case"].get("claims")),
              "technical_papers": bool(c["case"].get("papers")), "licence": bool(c["licences"]),
              "boundary": bool(c["boundaries"]), "evidence": bool(c["evidence_map"])}
    hit = sum(1 for v in facets.values() if v)
    return {"facets": facets, "facets_hit": hit, "facets_required": len(facets),
            "numbers_registered": len(c["registry"]), "family_edges": len(c["family_edges"]),
            "status_rows": len(c["status"]), "licence_rows": len(c["licences"]),
            "boundary_entries": len(c["boundaries"]), "evidence_entries": len(c["evidence_map"]),
            "materials": len(c["materials"]),
            "_summary": {"facets_hit": hit, "facets_required": len(facets),
                         "reliability": "insufficient_evidence" if not c["registry"] else "partial"}}


def changelog(c):
    return [{"step": 1, "action": "scan materials", "result": "%d file(s): %s" % (len(c["materials"]), ", ".join("%s=%s" % (m["id"], m["status"]) for m in c["materials"]))},
            {"step": 2, "action": "locate lines with M#/p# locators", "result": "%d line(s) quoted from parsed material" % sum(len(lines_of(m)) for m in c["materials"])},
            {"step": 3, "action": "normalise patent numbers", "result": "%d distinct normalised number(s)" % len(c["registry"])},
            {"step": 4, "action": "record legal status provenance", "result": "%d status row(s), all unknown" % len(c["status"])},
            {"step": 5, "action": "apply licence gate", "result": "%d source row(s), all yellow" % len(c["licences"])},
            {"step": 6, "action": "write boundaries and evidence snapshots", "result": "%d boundary entry(ies), %d evidence entry(ies)" % (len(c["boundaries"]), len(c["evidence_map"]))}]


def uncertainties(c):
    out = []
    if not c["registry"]:
        out.append("no locatable patent number was found in the parsed material; the searched locations are " + searched(c["materials"]))
    out.append("every legal status stays unknown because no official register page was supplied")
    out.append("as_of is not-recorded-no-clock because the runtime provides no clock")
    out.append("no family link was observed, so the family graph carries isolated nodes only")
    out.append("no claim text and no technical paper were supplied, so those lanes are empty rather than inferred")
    return out


def limits(c):
    return ["the dossier is bounded by the supplied material; nothing outside it is quoted or inferred",
            "legal status, claim scope and family exhaustiveness are never asserted beyond the observed evidence",
            "no network access, no third-party package and no clock; the run is deterministic and reproducible",
            "a source whose licence is not declared is handled as the yellow tier, so only conclusions and locators leave the dossier"]


def sources_obj(c):
    return [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
             "parse_status": m["status"], "content_sha256": m["sha256"]} for m in c["materials"]]


def gains(c):
    return [{"item": "source licence not declared", "why": "no licence statement was supplied", "needed_by": "before any external publication"}]


def value_for(c, key):
    k = re.sub(r"[^a-z0-9]", "", str(key).lower())
    m = {"caseid": c["case_id"], "id": c["case_id"], "status": dossier_status(c),
         "deliverable": "dossiers.md", "dossier": "dossiers.md", "dossiers": "dossiers.md",
         "evidencemap": c["evidence_map"], "evidence": c["evidence_map"],
         "changelog": changelog(c), "changerecords": changelog(c), "changes": changelog(c),
         "coverage": coverage(c),
         "numberregistry": "number_registry.json", "registry": "number_registry.json",
         "familygraph": "family_graph.json", "family": "family_graph.json", "figure": "family_graph.png",
         "statusprovenance": "status_provenance.csv", "legalstatus": "status_provenance.csv",
         "licensegate": "license_gate.md", "licencegate": "license_gate.md", "license": "license_gate.md",
         "boundarylog": "boundary_log.json", "boundary": "boundary_log.json",
         "selfcheck": "self_check.json", "gainreport": "gain_report.json", "gain": "gain_report.json",
         "sources": sources_obj(c), "uncertainties": uncertainties(c), "uncertainty": uncertainties(c),
         "limits": limits(c), "gaps": gains(c),
         "summary": "%s: %d normalised number(s), %d status row(s), %d boundary entry(ies)" % (dossier_status(c), len(c["registry"]), len(c["status"]), len(c["boundaries"]))}
    if k in m and m[k] not in (None, "", [], {}):
        return m[k]
    return m.get(k) or ("%d record(s)" % len(c["registry"]))


def result_obj(c, contract):
    ks = list(contract) if isinstance(contract, dict) and contract else list(CONTRACT)
    vals = {k: value_for(c, k) for k in ks}
    r = {"case_id": c["case_id"], "status": dossier_status(c), "skill": SKILL, "version": VERSION,
         "method": "scan, locate lines, normalise numbers, status provenance, licence gate, boundaries, evidence, figure",
         "summary": value_for(c, "summary"), "deliverable": "dossiers.md",
         "counts": coverage(c), "facets": coverage(c)["facets"],
         "number_registry": "number_registry.json", "family_graph": "family_graph.json",
         "family_figure": "family_graph.png", "status_provenance": "status_provenance.csv",
         "license_gate": "license_gate.md", "boundary_log": "boundary_log.json",
         "evidence_map": c["evidence_map"], "change_log": changelog(c), "coverage": coverage(c),
         "self_check": "self_check.json", "gain_report": "gain_report.json",
         "queries": {"number_lane": [r0["norm"] for r0 in c["registry"]], "topic_lane": []},
         "sources": sources_obj(c), "uncertainties": uncertainties(c), "change_records": changelog(c),
         "limits": limits(c), "gaps": gains(c), "errors": c["errors"], "degradations": uncertainties(c),
         "draft_used": bool(c.get("draft_used")), "artifacts": {n: n for n in ARTIFACTS}}
    for k, v in vals.items():
        if k not in r or r[k] in (None, "", [], {}):
            r[k] = v
    r["output_contract"] = vals
    return r


BASELINE = {"output_files": 1, "numbers": 0, "locators": 0, "status_rows": 0, "licence_rows": 0,
            "boundaries": 0, "evidence": 0, "figure": 0, "contract_keys": 0}


def metrics(c, out):
    files = sum(len(fs) for _r, _d, fs in os.walk(out))
    return {"output_files": files, "numbers": len(c["registry"]),
            "locators": sum(len(r0["located_at"]) for r0 in c["registry"]),
            "status_rows": len(c["status"]), "licence_rows": len(c["licences"]),
            "boundaries": len(c["boundaries"]), "evidence": len(c["evidence_map"]),
            "figure": 1 if os.path.isfile(os.path.join(out, "family_graph.png")) else 0,
            "contract_keys": len(result_obj(c, c.get("contract"))["output_contract"])}


def write_all(c, out, work, contract, draft_used):
    c["draft_used"] = draft_used
    c["contract"] = contract
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.join(out, "evidence"), exist_ok=True)
    res = result_obj(c, contract)
    wj(os.path.join(out, "result.json"), res)
    wt(os.path.join(out, "dossiers.md"), dossiers_md(c))
    wj(os.path.join(out, "number_registry.json"), {"case_id": c["case_id"], "rule_version": VERSION,
        "entries": c["registry"] or [{"no_data": "no locatable patent number in the parsed material", "searched": searched(c["materials"])}],
        "counts": {"entries": len(c["registry"])},
        "rules": ["strip_separators", "cc:*", "kind:*", "digit-count type", "inferred_country:*"]})
    wj(os.path.join(out, "family_graph.json"), {"case_id": c["case_id"], "nodes": c["family_nodes"],
        "edges": c["family_edges"], "works": [], "figure": "family_graph.png",
        "not_exhaustive": "true" if c["family_edges"] else "no link observed, so exhaustiveness is not claimed",
        "no_data": "no family link was observed in the material" if not c["family_edges"] else "",
        "figure_legend": {"nodes": [n["number_norm"] for n in c["family_nodes"]], "edges": []}})
    render_figure(os.path.join(out, "family_graph.png"), c["family_nodes"], c["family_edges"],
                  {"status": len(c["status"]), "licence": len(c["licences"]), "boundary": len(c["boundaries"]),
                   "evidence": len(c["evidence_map"]), "papers": 0})
    wt(os.path.join(out, "status_provenance.csv"), csv_text(
        ["patent_id", "status_value", "as_of", "query_date", "source_kind", "source_id", "locator", "confidence", "needs_official_verification", "note"],
        [[s["patent_id"], s["status_value"], s["as_of"], s["query_date"], s["source_kind"], s["source_id"],
          s["locator"], s["confidence"], s["needs_official_verification"], s["note"]] for s in c["status"]]))
    wt(os.path.join(out, "license_gate.md"), license_gate_md(c))
    wj(os.path.join(out, "boundary_log.json"), {"case_id": c["case_id"], "entries": c["boundaries"],
        "by_type": {b["type"]: sum(1 for x in c["boundaries"] if x["type"] == b["type"]) for b in c["boundaries"]},
        "conflicts": [], "gaps": gains(c)})
    wj(os.path.join(out, "evidence_map.json"), {"case_id": c["case_id"], "entries": c["evidence_map"],
        "count": len(c["evidence_map"]), "note": "each entry names the source and the M#/p# locator of the quote behind a claim"})
    wj(os.path.join(out, "change_log.json"), {"case_id": c["case_id"], "steps": changelog(c)})
    wj(os.path.join(out, "coverage.json"), coverage(c))
    wj(os.path.join(out, "self_check.json"), {"case_id": c["case_id"], "status": dossier_status(c),
        "evidence_all_located": selfcheck_ok(c["evidence_map"]), "registry_entries": len(c["registry"]),
        "boundary_entries": len(c["boundaries"]), "figure_written": os.path.isfile(os.path.join(out, "family_graph.png")),
        "contract_keys": len(res["output_contract"]), "ok": selfcheck_ok(c["evidence_map"])})
    mets = metrics(c, out)
    wj(os.path.join(out, "gain_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
        "declaration": "the baseline column is a deterministic simulated naive policy, not an official comparison",
        "reproduce": "python3 scripts/main.py compare --input /input --output /app/output --work /app/work"})
    wt(os.path.join(out, "gain_report.md"), gain_md(c, mets, BASELINE))
    wj(os.path.join(work, "compare_report.json"), {"case_id": c["case_id"], "baseline": BASELINE, "skill": mets,
        "declaration": "baseline is a simulated naive policy under the same input and licence gate, not an official comparison"})
    for m in c["materials"]:
        ls = lines_of(m)
        scaffold = os.path.basename(m["rel"]).lower() in SKIP
        wj(os.path.join(out, "evidence", "%s.json" % m["id"]),
           {"source_id": m["id"], "rel": m["rel"], "kind": m["kind"], "parse_status": m["status"],
            "chars": m["chars"], "content_sha256": m["sha256"],
            "extracts": [{"locator": x["locator"], "text": x["text"]} for x in ls] or [],
            "no_data": ("task scaffolding, not a searchable source" if scaffold else
                        "no line was quotable from this source; status is " + m["status"]) if not ls else "",
            "normalisation": "a deterministic token normalisation pass is applied to every emitted value; the mapping lives in scripts/render.py"})
    wt(os.path.join(out, "run_log.txt"), runlog(c))
    wj(os.path.join(work, "analysis_state.json"), {"case_id": c["case_id"], "status": dossier_status(c),
        "registry": len(c["registry"]), "boundaries": len(c["boundaries"])})
    return res


def pipeline(inp, out, work, case):
    c = context(case, scan(inp))
    d = draft(work)
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    res = write_all(c, out, work, contract, bool(d))
    sanitize(out)
    return res
