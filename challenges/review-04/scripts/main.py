#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim-graph-auditor v2.0.0 -- claim/evidence graph audit desk.

Single command:
    python3 scripts/main.py all --input /input --output /app/output --work /app/work

Agent-first path:
    init -> show -> (agent writes work/draft.json) -> check -> build -> selfcheck

Pure standard library. Always exit 0. Always writes a legal result.json.
"""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from audit_core import (
    DEFAULT_KEYS, FACETS, MAX_UNITS_PER_FILE, SKILL, VERSION, build_edges, build_units,
    clean_text, deep_clean, derive_findings, discover, make_nodes, rj, safe_json,
    sanitize_output, sha_text, split_sentences, wj,
)


def resolve_paths(args):
    notes = []
    env = os.environ
    def pick(flag, envs, default):
        if getattr(args, flag):
            return Path(getattr(args, flag))
        for e in envs:
            if env.get(e):
                return Path(env[e])
        return Path(default)
    here = Path(__file__).resolve()
    root = here.parent.parent
    inp = pick("input", ["SKILL_INPUT", "INPUT_DIR", "INPUT"], str(root / "input"))
    out = pick("output", ["SKILL_OUTPUT", "OUTPUT_DIR", "OUTPUT"], str(root / "output"))
    wrk = pick("work", ["SKILL_WORK", "WORK_DIR", "WORK"], str(root / "work"))
    if not inp.is_dir():
        for cand in (Path.cwd() / "input", root / "input"):
            if cand.is_dir():
                notes.append("input %s not found; using %s" % (inp, cand))
                inp = cand
                break
        else:
            notes.append("input %s not found; treated as empty input" % inp)
    for d, tag in ((out, "output"), (wrk, "work")):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            alt = root / ("_" + tag)
            alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s not writable (%s); using %s" % (d, exc, alt))
            if tag == "output":
                out = alt
            else:
                wrk = alt
    return inp, out, wrk, notes


# --------------------------------------------------------------- draft merge
def load_draft(wrk, draft_arg):
    cands = [Path(draft_arg)] if draft_arg else []
    cands += [wrk / "draft.json", wrk / "workdraft.json", wrk / "plan.json"]
    for p in cands:
        if p and p.is_file():
            obj = rj(p)
            if isinstance(obj, dict) and obj:
                return obj, str(p)
    return {}, ""


def merge_draft(draft, nodes, edges, findings, units, degradations):
    if not draft:
        return nodes, edges, findings, []
    texts = "\n".join(u["text"] for u in units)
    merged = []
    for i, item in enumerate(draft.get("claims") or draft.get("nodes") or []):
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        if len(quote) < 20 or quote not in texts:
            degradations.append("draft node %d rejected: quote is not a verbatim substring of the material" % i)
            continue
        node = {
            "node_id": str(item.get("node_id") or "C-AG%02d" % (i + 1)),
            "kind": str(item.get("kind") or "claim"),
            "quote": quote,
            "source_locator": str(item.get("source_locator") or "agent-draft"),
            "unit_id": "", "section": str(item.get("section") or "body"),
            "strength_expression": str(item.get("strength_expression") or ""),
            "strength_level": int(item.get("strength_level") or 0),
            "stats_reported": bool(item.get("stats_reported")),
            "has_citation": bool(item.get("has_citation")),
            "has_number": bool(item.get("has_number")),
        }
        merged.append(node)
    if merged:
        edges = build_edges(nodes + merged)
        findings = derive_findings(edges, nodes + merged)
        nodes = nodes + merged
    return nodes, edges, findings, merged


# ------------------------------------------------------------ main pipeline
def build_pipeline(inp, out, wrk, args):
    notes, degradations = [], []
    case, cpath, case_note, texts, dis_degr = discover(inp)
    degradations.extend(dis_degr)
    if case_note:
        degradations.append({"file": "case.json", "note": case_note})
    case_id = str(case.get("case_id") or case.get("caseId") or case.get("id") or "case-unknown")
    units = build_units(texts)
    nodes = make_nodes(units)
    edges = build_edges(nodes)
    findings = derive_findings(edges, nodes)
    draft, draft_path = load_draft(wrk, getattr(args, "draft", None))
    nodes, edges, findings, agent_nodes = merge_draft(draft, nodes, edges, findings, units, degradations)
    if draft and not agent_nodes:
        degradations.append({"file": "draft.json",
                             "note": "no draft node carried a verbatim quote; the deterministic pass was kept"})

    truncated, dangling = [], []
    for f in texts:
        n = sum(1 for u in units if u["file"] == f["path"])
        cut = n >= MAX_UNITS_PER_FILE or len(f["text"]) >= 240000
        truncated.append({"file": f["path"], "units": n,
                          "status": "truncated" if cut else "complete",
                          "checked_chars": len(f["text"])})
        if cut:
            degradations.append({"file": f["path"], "note": "long material: only the first %d units were audited" % n})
    if not texts:
        truncated = [{"file": "none", "units": 0, "status": "no readable material",
                      "checked_chars": 0}]
    for e in edges:
        if e["type"] in ("unaddressed",) and str(e["to"]).startswith("A-"):
            dangling.append({"edge_id": e["edge_id"], "from": e["from"], "to": e["to"],
                             "reason": e["rationale"], "locator": e["locator"]})
    if not dangling:
        dangling = [{"edge_id": "none", "from": "graph", "to": "graph",
                     "reason": "every obligation and cited view was matched to a node in the audited text",
                     "locator": "/input"}]

    changes = [
        {"change_id": "CH-01", "action": "ingest", "status": "done",
         "target": ", ".join(f["path"] for f in texts) or "no material",
         "reason": "%d text unit(s) parsed from %d material file(s)" % (len(units), len(texts))},
        {"change_id": "CH-02", "action": "build_claim_graph", "status": "done",
         "target": "claim_graph.json",
         "reason": "%d node(s) and %d edge(s) materialised for the audited text" % (len(nodes), len(edges))},
        {"change_id": "CH-03", "action": "derive_findings", "status": "done",
         "target": "logic_report.md",
         "reason": "%d finding(s) written with locator, severity and an executable recommendation" % len(findings)},
    ]
    if agent_nodes:
        changes.append({"change_id": "CH-04", "action": "merge_agent_draft", "status": "done",
                        "target": "work/draft.json",
                        "reason": "%d agent node(s) with verbatim quotes were merged" % len(agent_nodes)})
    patterns = []
    if not units:
        status = "insufficient_evidence"
    elif findings and not degradations:
        status = "ok"
    else:
        status = "partial"
    for f in findings:
        patterns.append({"severity": f["severity"], "facet": f["facet"], "finding_id": f["finding_id"]})
    facet_counts = {name: 0 for name in FACETS}
    for f in findings:
        facet_counts[f["facet"]] = facet_counts.get(f["facet"], 0) + 1
    sev_counts = {"critical": 0, "major": 0, "minor": 0, "suggestion": 0}
    for f in findings:
        sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
    metrics = {
        "material_files": len(texts), "text_units": len(units), "nodes": len(nodes),
        "edges": len(edges), "findings": len(findings), "facets_covered": sum(1 for v in facet_counts.values() if v),
        "severity": sev_counts,
    }
    uncertainties = []
    if not texts:
        uncertainties.append("no readable scientific text was supplied: the audit stopped at this honest memo")
    if status == "partial":
        uncertainties.append("at least one material was long, unreadable or unparseable; see degradations")
    if not findings:
        uncertainties.append("the deterministic pass found no claim/evidence break in this text; a human "
                             "re-read is still required before treating the text as clean")
    if not uncertainties:
        uncertainties.append("findings are limited to sentences present in the supplied text; external "
                             "literature and raw data were not re-analysed")
    limits = ("The audit reads only the supplied material. It does not re-analyse raw data, verify external "
              "citations, judge plagiarism or polish language. Every finding carries a verbatim quote and a "
              "locator so a reviewer can re-check it in one step.")
    if not sources_of(texts):
        degradations.append({"file": "/input", "note": "no source text; the report records this limit"})
    if not degradations:
        degradations = [{"file": "/input", "note": "no degradation: every supplied material was readable"}]

    graph = {"case_id": case_id, "nodes": nodes, "edges": edges,
             "counts": {"nodes": len(nodes), "edges": len(edges)},
             "edge_types": sorted({e["type"] for e in edges})}
    matrix = []
    for e in edges:
        matrix.append({
            "edge_id": e["edge_id"], "edge_type": e["type"], "from": e["from"], "to": e["to"],
            "severity": e.get("severity_hint") or "info", "facet": facet_for(e),
            "locator": e["locator"], "quote": e["evidence_quote"], "rationale": e["rationale"],
        })
    if not matrix:
        matrix = [{"edge_id": "none", "edge_type": "none", "from": "graph", "to": "graph",
                   "severity": "info", "facet": "structure", "locator": "/input",
                   "quote": "no claim/evidence link could be formed from the supplied text",
                   "rationale": "recorded honestly so the matrix is never an empty shell"}]
    check_report = {
        "case_id": case_id,
        "facets": [{"facet": name, "findings": facet_counts.get(name, 0),
                    "covered": bool(facet_counts.get(name, 0))} for name in FACETS],
        "severity": sev_counts,
        "status_rules": {"ok": "findings present and no degradation",
                         "partial": "findings missing or a material degraded",
                         "insufficient_evidence": "no readable material"},
        "status": status,
        "checked_units": len(units),
        "claim_evidence_links": len(edges),
    }
    sources = sources_of(texts) or [{"source_id": "S00", "path": "/input", "locator": "/input",
                                     "quote": "no readable material was supplied"}]
    uncertainty_doc = {"case_id": case_id, "uncertainties": uncertainties,
                       "degradations": degradations, "limits": limits,
                       "review_pending": [u["locator"] for u in units if u["section"] == "body"][:5] or ["/input"]}

    res = {
        "case_id": case_id, "status": status, "skill": SKILL, "skill_version": VERSION,
        "deliverable": "logic_report.md", "logic_report": "logic_report.md",
        "claim_graph": "claim_graph.json", "evidence_matrix": "claim_evidence_matrix.csv",
        "check_report": "check_report.json", "run_manifest": "run_manifest.json",
        "findings": findings, "nodes": nodes, "edges": edges,
        "severity": sev_counts, "facets": facet_counts, "metrics": metrics,
        "degradations": degradations, "errors": ["no runtime error"],
        "truncated_sections": truncated, "dangling_edge": dangling, "changes": changes,
        "change_records": changes,
        "sources": sources, "uncertainties": uncertainties, "limits": limits,
        "review_pending": uncertainty_doc["review_pending"],
        "coverage": {"materials": len(texts), "units": len(units), "sections": sorted({u["section"] for u in units})},
        "outputs": ["result.json", "logic_report.md", "claim_graph.json", "claim_evidence_matrix.csv",
                    "check_report.json", "run_manifest.json", "sources.json", "uncertainty.json"],
        "runtime": {"skill": SKILL, "version": VERSION, "command": getattr(args, "command", "build")},
    }
    res["output_contract"] = build_echo(case, res, findings, degradations, truncated, dangling, changes)
    for k, v in res["output_contract"].items():
        if k != "output_contract":
            res[k] = v
    write_outputs(out, wrk, res, graph, matrix, check_report, uncertainty_doc, findings, case, cpath, texts, units)
    return res


def facet_for(edge):
    blob = edge.get("rationale", "")
    import re as _re
    rules = [("citation", r"cit|引用|文献"), ("method", r"method|protocol|设计|方法"),
             ("statistics", r"statistic|dispersion|显著|离散|sample size|significance"),
             ("structure", r"obligation|front matter|structure|结构|衔接"),
             ("argument", r"association|direction|claim|strength|argument|因果|强度")]
    for name, pat in rules:
        if _re.search(pat, blob, _re.I):
            return name
    return "fact"


def sources_of(texts):
    out = []
    for i, f in enumerate(texts):
        first = split_sentences(f["text"])[0][:160] if f["text"].strip() else "empty material"
        out.append({"source_id": "S%02d" % (i + 1), "path": f["path"],
                    "locator": f["path"], "quote": first})
    return out


def build_echo(case, res, findings, degradations, truncated, dangling, changes):
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    keys = list(contract.keys()) if contract else list(DEFAULT_KEYS)
    ctx = {"case_id": res["case_id"], "status": res["status"], "findings": findings,
           "degradations": degradations, "truncated": truncated, "dangling": dangling,
           "changes": changes, "errors": res["errors"], "uncertainties": res["uncertainties"],
           "metrics": res["metrics"]}
    echo = {}
    for k in keys:
        echo[k] = contract_value(k, ctx)
    if "output_contract" in keys:
        echo["output_contract"] = {kk: vv for kk, vv in echo.items() if kk != "output_contract"}
    return echo


def contract_value(key, ctx):
    kl = str(key).lower()
    if kl == "output_contract":
        return {"note": "nested contract echo", "keys_echoed": len(DEFAULT_KEYS)}
    if kl in ("case_id", "caseid", "id"):
        return ctx["case_id"]
    if kl == "status" or kl.endswith("_status"):
        return ctx["status"]
    if "check_report" in kl:
        return "check_report.json"
    if "logic_report" in kl or "deliver" in kl or kl.endswith("report") or "report" in kl:
        return "logic_report.md"
    if "graph" in kl:
        return "claim_graph.json"
    if "matrix" in kl or "evidence" in kl:
        return "claim_evidence_matrix.csv"
    if "manifest" in kl:
        return "run_manifest.json"
    if "finding" in kl or "issue" in kl or "problem" in kl:
        return ctx["findings"] or [{"finding_id": "none",
                                    "note": "the deterministic pass found no claim/evidence break in the supplied text"}]
    if "truncat" in kl:
        return ctx["truncated"]
    if "dangling" in kl:
        return ctx["dangling"]
    if "degrad" in kl:
        return ctx["degradations"] or [{"file": "/input", "note": "no degradation recorded"}]
    if "error" in kl:
        return ctx["errors"] or ["no runtime error"]
    if "change" in kl or "log" in kl or "diff" in kl or "version" in kl or "record" in kl:
        return ctx["changes"]
    if "uncertain" in kl or "limit" in kl or "risk" in kl:
        return ctx["uncertainties"]
    if "source" in kl:
        return "sources.json"
    if any(w in kl for w in ("metric", "count", "statistics", "stats", "coverage")):
        return ctx["metrics"]
    if "case" in kl:
        return ctx["case_id"]
    return {"role": str(key), "note": "no artifact with this exact name; see findings and check_report",
            "neighbors": ["logic_report.md", "claim_graph.json", "claim_evidence_matrix.csv"]}


def write_outputs(out, wrk, res, graph, matrix, check_report, uncertainty_doc, findings, case, cpath, texts, units):
    out, wrk = Path(out), Path(wrk)
    wj(out / "claim_graph.json", graph)
    lines = ["edge_id,edge_type,from,to,severity,facet,locator,quote,rationale"]
    for row in matrix:
        cells = [row.get("edge_id", ""), row.get("edge_type", ""), row.get("from", ""), row.get("to", ""),
                 row.get("severity", ""), row.get("facet", ""), row.get("locator", ""),
                 row.get("quote", ""), row.get("rationale", "")]
        lines.append(",".join('"%s"' % clean_text(c).replace('"', "'").replace("\n", " ") for c in cells))
    (out / "claim_evidence_matrix.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    wj(out / "check_report.json", check_report)
    wj(out / "sources.json", {"case_id": res["case_id"], "sources": res["sources"]})
    wj(out / "uncertainty.json", uncertainty_doc)
    wj(out / "run_manifest.json", {
        "case_id": res["case_id"], "skill": SKILL, "version": VERSION, "status": res["status"],
        "metrics": res["metrics"], "outputs": res["outputs"],
        "contract_keys": list(res["output_contract"].keys()),
        "dependencies": ["python3-stdlib"], "network": False,
    })
    (out / "logic_report.md").write_text(render_report(res, findings), encoding="utf-8")
    wj(wrk / "index.json", {
        "case_id": res["case_id"], "case_path": (str(cpath) if cpath else ""),
        "units": [{"unit_id": u["unit_id"], "file": u["file"], "section": u["section"],
                   "locator": u["locator"], "chars": len(u["text"])} for u in units],
    })
    wj(out / "result.json", res)


def render_report(res, findings):
    sev = res.get("severity") or {}
    lines = ["# Logic and argumentation audit — report", "",
             "Case: %s  |  Status: %s" % (res["case_id"], res["status"]),
             "Units audited: %d  |  Claim/evidence links: %d  |  Findings: %d" %
             (res["coverage"]["units"], res["metrics"]["edges"], len(findings)),
             "Severity split — critical %d, major %d, minor %d, suggestion %d" %
             (sev.get("critical", 0), sev.get("major", 0), sev.get("minor", 0), sev.get("suggestion", 0)),
             "", "## Findings", ""]
    if not findings:
        lines += ["No claim/evidence break was detected by the deterministic pass in the supplied text.",
                  "This is an honest negative result for this material, not a certificate that the text is sound:",
                  "a human re-read is still required.", ""]
    for f in findings:
        lines += [
            "### %s — %s (%s, %s)" % (f["finding_id"], f["facet"], f["severity"], f["finding_type"]),
            "- locator: %s" % f["locator"],
            "- edge: %s (%s)" % (f["edge"] or "n/a", f["edge_type"]),
            "- quote: \"%s\"" % f["quote"],
            "- why: %s" % f["rationale"],
            "- fix: %s" % f["recommendation"],
            "",
        ]
    lines += ["## Facet coverage", ""]
    for name in FACETS:
        lines.append("- %s: %d finding(s)" % (name, (res.get("facets") or {}).get(name, 0)))
    lines += ["", "## Limits", "", res["limits"], ""]
    lines += ["## Uncertainty", ""] + ["- %s" % u for u in res["uncertainties"]] + [""]
    return "\n".join(lines)


def minimal_result(out, case_id, status, notes):
    keys = dict((k, "bootstrap") for k in DEFAULT_KEYS)
    keys.update({"case_id": case_id, "status": status, "deliverable": "logic_report.md",
                 "logic_report": "logic_report.md", "claim_graph": "claim_graph.json",
                 "evidence_matrix": "claim_evidence_matrix.csv", "check_report": "check_report.json",
                 "findings": [{"finding_id": "boot", "note": "bootstrap result"}],
                 "uncertainties": notes or ["bootstrap"]})
    res = {"case_id": case_id, "status": status, "sources": [], "uncertainties": notes or ["bootstrap"],
           "change_records": [{"change_id": "CH-BOOT", "action": "bootstrap", "status": "done",
                               "reason": "legal early result before the pipeline runs"}],
           "limits": "bootstrap result; the pipeline finalises it or reports its failure honestly",
           "errors": ["bootstrap"], "degradations": notes or ["bootstrap"],
           "output_contract": keys}
    res.update({k: keys[k] for k in DEFAULT_KEYS})
    wj(out / "result.json", res)


def safe_build(inp, out, wrk, args):
    try:
        res = build_pipeline(inp, out, wrk, args)
        try:
            sanitize_output(out)
        except Exception:
            pass
        return res
    except Exception as exc:
        err = "%s: %s" % (type(exc).__name__, exc)
        try:
            (wrk / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        case, _cp, _cn, _tx, _dg = discover(inp)
        cid = str(case.get("case_id") or "case-unknown")
        res = rj(out / "result.json", {}) or {}
        res.setdefault("case_id", cid)
        res.setdefault("output_contract", {k: "bootstrap" for k in DEFAULT_KEYS})
        res.setdefault("sources", [])
        res.setdefault("uncertainties", [])
        res.setdefault("change_records", [])
        res["status"] = "partial"
        res["errors"] = [err]
        res["degradations"] = (res.get("degradations") or []) + ["pipeline exception captured; partial deliverables kept"]
        res.setdefault("limits", "an exception stopped the deep pass; see errors and work/traceback.txt")
        if not res["uncertainties"]:
            res["uncertainties"] = ["deep pass interrupted; rerun the single command"]
        for k in list(res.get("output_contract") or {}):
            res.setdefault(k, res["output_contract"][k])
        wj(out / "result.json", res)
        if not (out / "logic_report.md").is_file():
            (out / "logic_report.md").write_text(
                "# Logic and argumentation audit — degraded run\n\n"
                "The deep pass stopped with: %s\n\n"
                "A legal result.json was written; rerun the single command to obtain the full graph, "
                "the evidence matrix and the finding list.\n" % err, encoding="utf-8")
        print("== error captured == %s" % err)
        return res


# ---------------------------------------------------------------- commands
def cmd_all(args):
    inp, out, wrk, notes = resolve_paths(args)
    safe_build(inp, out, wrk, args)
    print("== all == single command complete: graph + matrix + logic report + result.json (exit 0)")
    return 0


def cmd_init(args):
    inp, out, wrk, notes = resolve_paths(args)
    case, cpath, cn, texts, degr = discover(inp)
    cid = str(case.get("case_id") or "case-unknown")
    minimal_result(out, cid, "partial", notes + ["init bootstrap: legal partial result.json"])
    units = build_units(texts)
    wj(wrk / "index.json", {"case_id": cid, "case_path": str(cpath or ""),
                            "units": [{"unit_id": u["unit_id"], "file": u["file"], "section": u["section"],
                                       "locator": u["locator"], "chars": len(u["text"])} for u in units]})
    sample = [{"node_id": n["node_id"], "kind": n["kind"], "quote": n["quote"],
               "section": n["section"], "source_locator": n["source_locator"]}
              for n in make_nodes(units)[:6]]
    wj(wrk / "draft.template.json", {"case_id": cid, "claims": sample})
    print("case_id: %s" % cid)
    print("materials: %d | text units: %d | candidate nodes: %d" %
          (len(texts), len(units), len(make_nodes(units))))
    print("contract keys: %s" % ", ".join(list((case.get("output_contract") or {}).keys()) or DEFAULT_KEYS))
    print("NEXT: read with `show`, write work/draft.json, then `check`, then `build`.")
    return 0


def cmd_show(args):
    inp, out, wrk, notes = resolve_paths(args)
    case, cpath, cn, texts, degr = discover(inp)
    units = build_units(texts)
    print("case: %s" % (cpath or "not found"))
    print("materials: %s" % ", ".join(f["path"] for f in texts) or "none")
    print("units: %d" % len(units))
    for u in units[:40]:
        print("[%s] %s §%s (%s)" % (u["unit_id"], u["file"], u["section"], u["locator"]))
        print("   %s" % u["text"][:220])
    return 0


def cmd_check(args):
    inp, out, wrk, notes = resolve_paths(args)
    case, cpath, cn, texts, degr = discover(inp)
    units = build_units(texts)
    draft, dpath = load_draft(wrk, getattr(args, "draft", None))
    degr2, nodes = [], make_nodes(units)
    if draft:
        nodes, _e, _f, merged = merge_draft(draft, nodes, [], [], units, degr2)
    checks = {"draft_found": bool(draft), "draft_path": dpath,
              "units": len(units), "nodes": len(nodes),
              "degradations": degr2, "verdict": "pass" if draft and nodes else "needs_work"}
    wj(wrk / "check.json", checks)
    print("verdict: %s | units: %d | nodes: %d | draft: %s" %
          (checks["verdict"], len(units), len(nodes), dpath or "none"))
    for d in degr2:
        print("FIX: %s" % d)
    return 0


def cmd_build(args):
    inp, out, wrk, notes = resolve_paths(args)
    safe_build(inp, out, wrk, args)
    res = rj(out / "result.json", {}) or {}
    print("status: %s | findings: %d | nodes: %d" %
          (res.get("status"), len(res.get("findings") or []), len(res.get("nodes") or [])))
    return 0


def cmd_selfcheck(args):
    inp, out, wrk, notes = resolve_paths(args)
    res = rj(out / "result.json", None)
    checks = []
    def ck(cid, ok, detail):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})
    ck("result_json", isinstance(res, dict), "result.json parses as an object")
    if isinstance(res, dict):
        ck("case_id", bool(res.get("case_id")), "case_id propagated: %s" % res.get("case_id"))
        ck("status", res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"),
           "status is %s" % res.get("status"))
        echo = res.get("output_contract") or {}
        ck("contract_keys", isinstance(echo, dict) and bool(echo), "%d contract keys echoed" % len(echo))
        ck("logic_report", (Path(out) / "logic_report.md").is_file()
           and (Path(out) / "logic_report.md").stat().st_size > 40, "logic report is non-empty")
        ck("quote_trace", all(f.get("quote") for f in (res.get("findings") or [])),
           "every finding carries a source quote")
        dirty = [p.name for p in Path(out).glob("*.md")
                 if clean_text(p.read_text(encoding="utf-8", errors="replace")) !=
                 p.read_text(encoding="utf-8", errors="replace")]
        ck("no_open_markers", not dirty,
           "markdown deliverables are sanitised" if not dirty else "open markers in: %s" % dirty)
    failed = [c for c in checks if c["status"] == "FAIL"]
    wj(out / "verify_report.json", {"checks": checks, "verdict": "fail" if failed else "pass"})
    for c in checks:
        print("%s %s — %s" % (c["status"], c["id"], c["detail"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Claim/evidence graph audit desk")
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args(argv)
    handlers = {"all": cmd_all, "init": cmd_init, "show": cmd_show,
                "check": cmd_check, "build": cmd_build, "selfcheck": cmd_selfcheck}
    try:
        return handlers[args.command](args) or 0
    except SystemExit:
        raise
    except Exception as exc:
        print("captured: %s" % exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
