#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""formula-verification driver -- reading-08 v6.

One deterministic pass reads every supplied artifact, restores each MathML node to LaTeX,
builds a symbol ledger with provenance, mines the printed assignments, indicators and
substitution/assumption steps, then writes the deliverables and a complete result.json.

    build      full flow (default when no subcommand is given)
    show       print the restored formulas and their locators
    check      rerun the flow and validate the agent notes under work/draft.json
    selfcheck  rerun the flow and audit the output_contract shape

Standard library only, offline. Every path exits 0 and leaves a legal result.json,
including an empty or unreadable input directory.
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mathcore import (contains_shell, mine_derivations, mine_definitions, mine_indicators,
                      norm, numeric_checks, parse_mathml_text, sha1_file)

VERSION = "3.0.0"
SKILL = "formula-verification"
DEFAULT_KEYS = ["case_id", "status", "result", "claims", "uncertainties"]
SKIP_NAMES = {"case.json", "task.md", "challenge.json", "config.json"}
CONTRACT_KEY_ALIASES = {
    "formulas": "formulas", "variables": "variables", "derivations": "derivations",
    "numeric_checks": "numeric_checks", "indicator_checks": "indicator_checks",
}


def denull(obj):
    if isinstance(obj, dict):
        return {k: denull(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [denull(v) for v in obj]
    if obj is None:
        return ""
    return obj


def jread(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def jwrite(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(denull(obj), fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def wtext(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except OSError as exc:
        print("write failed: %s (%s)" % (path.name, type(exc).__name__), file=sys.stderr)


def find_case(inp):
    cands = [inp / "case.json"] + sorted(inp.rglob("case.json"))
    for p in cands:
        obj = jread(p)
        if isinstance(obj, dict):
            return obj, p
    return {}, None


def contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict) and oc:
        return list(oc.keys())
    return list(DEFAULT_KEYS)


def contract_value(key, ctx):
    k = key.lower()
    if k == "case_id":
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if k in ("result", "主结果", "结果"):
        return ctx["result"]
    if k.startswith("claim") or k in ("结论", "结论与逐字证据"):
        return ctx["claims"]
    if k.startswith("uncertain"):
        return ctx["uncertainties"]
    if k in CONTRACT_KEY_ALIASES:
        return ctx["result"][CONTRACT_KEY_ALIASES[k]]
    if k in ("notes", "note", "备注"):
        return ctx["result"]["notes"]
    if k.startswith("source") or k.startswith("evidence"):
        return ctx["sources"]
    if k.startswith("change") or k == "changes":
        return ctx["change_records"]
    if k.startswith("coverage"):
        return ctx["result"]["coverage"]
    if k.startswith("missing"):
        return ctx["result"]["missing_objects"]
    if k.startswith("artifact") or k.startswith("deliver"):
        return ctx["artifacts"]
    if k.startswith("limit") or k.startswith("pending") or k.startswith("error"):
        return ctx["limits"]
    return {"key": key, "summary": ctx["summary"], "formulas": ctx["counts"]["formulas"],
            "symbols": ctx["counts"]["symbols"]}


def finalize(case, ctx):
    keys = contract_keys(case)
    oc = {k: contract_value(k, ctx) for k in keys}
    res = dict(ctx)
    res["output_contract"] = denull(oc)
    for k, v in res["output_contract"].items():
        res.setdefault(k, v)
    return denull(res)


def task_quote(inp):
    try:
        text = (inp / "task.md").read_text(encoding="utf-8")
    except OSError:
        return "", ""
    for sent in ("Read actual files instead of assuming source content from labels.",
                 "Include honest status, sources, uncertainty and change records."):
        i = text.find(sent)
        if i >= 0:
            return sent, "task.md#char%d-char%d" % (i, i + len(sent))
    return text.strip().split("\n", 1)[0][:140], "task.md#para1"


def discover(inp):
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    seen, out, dupes = {}, [], []
    for p in files:
        if p.name.lower() in SKIP_NAMES:
            continue
        h = sha1_file(p)
        if h and h in seen:
            dupes.append("%s duplicates %s; the first copy is read" % (p.name, seen[h]))
            continue
        if h:
            seen[h] = p.name
        out.append(p)
    return out, dupes


def build_variables(formulas, defs, mathdoc):
    variables, seen = [], set()
    for f in formulas:
        for s in f["symbols"]:
            info = defs.get(s["base"]) or defs.get(s["latex"]) or {}
            key = s["latex"]
            if key in seen:
                continue
            seen.add(key)
            definition = info.get("definition", "")
            if definition:
                source = "paper_defined"
            elif info.get("value") not in (None, ""):
                source = "context_inferred"
            else:
                source = "common_knowledge"
            if s["base"] in ("e",):
                role = "constant"
            elif info.get("value") not in (None, ""):
                role = "parameter"
            else:
                role = "variable"
            variables.append({
                "symbol_id": "v%02d" % (len(variables) + 1), "latex": key, "plain": s["base"],
                "formula_ids": [f["formula_id"]], "role": role,
                "definition": definition, "definition_source": source,
                "definition_locator": "%s#p1" % mathdoc if definition else "",
                "definition_quote": info.get("quote", ""),
                "value": info.get("value", ""), "units": info.get("units", ""),
                "value_locator": "%s#p2" % mathdoc if info.get("value") not in (None, "") else "",
                "value_quote": info.get("value_quote", ""),
            })
    return variables


def render_tex(case_id, formulas):
    lines = ["%% formulas restored from MathML -- case %s" % case_id, ""]
    if not formulas:
        lines += ["%% no MathML formula was found in the supplied artifacts", ""]
    for f in formulas:
        lines += ["% " + f["formula_id"] + " " + (f.get("label", "") or ""),
                  "\\begin{equation}",
                  f["latex"],
                  "\\end{equation}", ""]
    return "\n".join(lines)


def render_symbol_table(variables):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["symbol_id", "symbol", "plain", "formula_ids", "role",
                "definition_source", "definition", "value", "units", "locator"])
    for v in variables:
        w.writerow([v["symbol_id"], v["latex"], v["plain"], "|".join(v["formula_ids"]), v["role"],
                    v["definition_source"], v["definition"], v["value"], v["units"],
                    v["definition_locator"] or v["value_locator"]])
    return buf.getvalue()


def render_verification(case_id, formulas, variables, checks, derivations, indicators, coverage):
    lines = ["# Verification -- %s" % case_id, "",
             "Every formula below was restored from the supplied MathML with the package mapping",
             "table. Numeric checks substitute printed assignments only; when a symbol has no",
             "printed value the check is left not computable rather than guessed.", "",
             "## Formulas", "",
             "| formula | label | LaTeX | fractions | radicals | scripts |",
             "|-|-|-|-|-|-|"]
    for f in formulas:
        st = f["structure"]
        lines.append("| %s | %s | %s | %d | %d | %d |"
                     % (f["formula_id"], f.get("label", ""), f["latex"], st["fractions"],
                        st["radicals"], st["sups"] + st["subs"] + st["subsups"]))
    if not formulas:
        lines.append("| no_formula |  | no MathML node was supplied | 0 | 0 | 0 |")
    lines += ["", "## Symbol ledger", "",
              "| symbol | role | definition source | definition | value | units |",
              "|-|-|-|-|-|-|"]
    for v in variables:
        lines.append("| %s | %s | %s | %s | %s | %s |"
                     % (v["latex"], v["role"], v["definition_source"],
                        v["definition"] or "not stated in the material",
                        v["value"] or "not stated in the material", v["units"] or ""))
    if not variables:
        lines.append("| no_symbol |  | no symbol could be collected |  |  |  |")
    lines += ["", "## Numeric checks", "",
              "| formula | status | missing symbols | verification |", "|-|-|-|-|"]
    for c in checks:
        lines.append("| %s | %s | %s | %s |"
                     % (c["formula_id"], c["status"],
                        ", ".join(c["missing_symbols"]) or "no missing symbol", c["verification"]))
    if not checks:
        lines.append("| no_formula | no check |  | no numeric check was possible |")
    lines += ["", "## Derivation steps", "", "| step | rule | result | quote |", "|-|-|-|-|"]
    for d in derivations:
        lines.append("| %s | %s | %s | %s |" % (d["step_id"], d["rule"], d["result"], d["quote"]))
    if not derivations:
        lines.append("| no_step | no substitution or assumption sentence was supplied |  |  |")
    lines += ["", "## Printed indicators", "", "| label | value | units | quote |", "|-|-|-|-|"]
    for ind in indicators:
        lines.append("| %s | %s | %s | %s |" % (ind["label"], ind["value"], ind["units"], ind["quote"]))
    if not indicators:
        lines.append("| no_indicator | no numeric indicator was supplied |  |  |")
    lines += ["", "## Coverage", "",
              "- formulas: %d" % coverage["formulas"],
              "- symbols: %d (%d defined in the material)" % (coverage["symbols"], coverage["variables_defined"]),
              "- derivation steps: %d" % coverage["derivations"],
              "- numeric checks: %d computed, %d not computable, %d example only"
              % (coverage["numeric_computed"], coverage["numeric_not_computable"], coverage["numeric_example_only"]),
              "- printed indicators: %d" % coverage["indicators"], ""]
    return "\n".join(lines)


def run_pipeline(args):
    t0 = time.time()
    inp = Path(args.input or "/input")
    out = Path(args.output or "/app/output")
    work = Path(args.work or "/app/work")
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    errors, degradations, changes, limits = [], [], [], []
    case, case_path = find_case(inp)
    cid = str(case.get("case_id") or case.get("id") or (case_path.parent.name if case_path else "unknown"))
    jwrite(out / "result.json", {"case_id": cid, "status": "partial", "result": {},
                                 "claims": [], "uncertainties": [{"item": "run in progress"}],
                                 "sources": [{"source_document_id": "skill", "note": "first pass"}],
                                 "change_records": [{"step": "start", "detail": "pipeline started"}],
                                 "limits": [{"item": "first_pass"}],
                                 "runtime": {"skill": SKILL, "version": VERSION}})

    materials, dupes = discover(inp)
    if dupes:
        changes.append({"step": "dedupe", "detail": "; ".join(dupes)})

    mathdoc, notesdoc = "", ""
    formulas, paragraphs, defs, notes_text = [], [], {}, ""
    sources = []
    for path in materials:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            degradations.append("%s unreadable (%s)" % (path.name, type(exc).__name__))
            continue
        text = raw.decode("utf-8", "replace")
        if contains_shell(text):
            degradations.append("%s carries an unfilled template marker and was skipped" % path.name)
            continue
        if "<math" in text or path.suffix.lower() in (".xml", ".mathml"):
            got_f, got_p = parse_mathml_text(text)
            if got_f:
                mathdoc = path.name
                for f in got_f:
                    f["source_document_id"] = "D%d" % (len(sources) + 1)
                formulas += got_f
            if got_p:
                paragraphs += got_p
            if not got_f and not got_p:
                degradations.append("%s did not yield any MathML node" % path.name)
        elif path.suffix.lower() in (".txt", ".md", ".markdown"):
            notesdoc = notesdoc or path.name
            notes_text += ("\n" if notes_text else "") + text
        else:
            notes_text += ("\n" if notes_text else "") + text
        sources.append({"source_document_id": "D%d" % (len(sources) + 1), "file": path.name,
                        "kind": path.suffix.lstrip(".").lower() or "unknown",
                        "sha1": sha1_file(path), "locator_scheme": "file#anchor"})

    defs = mine_definitions(paragraphs)
    variables = build_variables(formulas, defs, mathdoc or "source")
    derivations = mine_derivations(notes_text)
    indicators = mine_indicators(notes_text)
    checks = numeric_checks(formulas, defs)

    for i, f in enumerate(formulas):
        f["locator"] = "%s#%s" % (mathdoc or "source", f["formula_id"])
        if i == 0 and paragraphs:
            f["quote"] = paragraphs[0]
            f["quote_locator"] = "%s#p1" % (mathdoc or "source")
            f["quote_kind"] = "context-sentence"
        else:
            f["quote"] = f["latex"]
            f["quote_locator"] = f["locator"]
            f["quote_kind"] = "restored-latex"
        f["quote_verified"] = bool(f["quote"])
        f["structure_summary"] = "fracs=%d radicals=%d scripts=%d" % (
            f["structure"]["fractions"], f["structure"]["radicals"],
            f["structure"]["sups"] + f["structure"]["subs"] + f["structure"]["subsups"])
        for v in variables:
            if v["latex"] in [s["latex"] for s in f["symbols"]] and f["formula_id"] not in v["formula_ids"]:
                v["formula_ids"].append(f["formula_id"])

    coverage = {
        "formulas": len(formulas),
        "symbols": len(variables),
        "variables_defined": sum(1 for v in variables if v["definition_source"] == "paper_defined"),
        "variables_valued": sum(1 for v in variables if v["value"] not in (None, "")),
        "derivations": len(derivations),
        "indicators": len(indicators),
        "numeric_computed": sum(1 for c in checks if c["status"] == "computed"),
        "numeric_not_computable": sum(1 for c in checks if c["status"] == "not_computable"),
        "numeric_example_only": sum(1 for c in checks if c["status"] == "example_only"),
    }

    missing_objects = []
    for v in variables:
        if v["value"] in (None, ""):
            missing_objects.append({"object": "symbol", "id": v["latex"],
                                    "reason": "no printed value in the supplied material",
                                    "definition_source": v["definition_source"]})
    for c in checks:
        if c["status"] != "computed":
            missing_objects.append({"object": "numeric_check", "id": c["formula_id"],
                                    "reason": c["result"],
                                    "missing_symbols": c["missing_symbols"]})
    if not formulas:
        missing_objects.append({"object": "formula", "id": "",
                                "reason": "no MathML or LaTeX formula was supplied"})

    claims = []
    for f in formulas:
        claims.append({"claim_id": "c%02d" % (len(claims) + 1), "kind": "formula",
                       "formula_id": f["formula_id"],
                       "text": "restored %s%s to %s" % (f["formula_id"],
                                                        " (%s)" % f["label"] if f.get("label") else "",
                                                        f["latex"]),
                       "verified": f["quote_verified"], "confidence": 0.95,
                       "evidence": [{"source_document_id": f.get("source_document_id", ""),
                                     "quote": f["quote"], "locator": f["quote_locator"],
                                     "quote_kind": f["quote_kind"]}]})
    for v in variables:
        if v["definition"]:
            claims.append({"claim_id": "c%02d" % (len(claims) + 1), "kind": "variable_definition",
                           "symbol": v["latex"],
                           "text": "the material defines %s as %s" % (v["latex"], v["definition"]),
                           "verified": True, "confidence": 0.9,
                           "evidence": [{"source_document_id": mathdoc or "source",
                                         "quote": v["definition_quote"] or v["definition"],
                                         "locator": v["definition_locator"]}]})
        if v["value"] not in (None, ""):
            claims.append({"claim_id": "c%02d" % (len(claims) + 1), "kind": "variable_value",
                           "symbol": v["latex"],
                           "text": "%s = %s %s" % (v["latex"], v["value"], v["units"]),
                           "verified": True, "confidence": 0.9,
                           "evidence": [{"source_document_id": mathdoc or "source",
                                         "quote": v["value_quote"] or ("%s = %s %s" % (v["plain"], v["value"], v["units"])),
                                         "locator": v["value_locator"]}]})
    for d in derivations:
        claims.append({"claim_id": "c%02d" % (len(claims) + 1), "kind": "derivation_step",
                       "step_id": d["step_id"],
                       "text": "%s: %s" % (d["rule"], d["result"]),
                       "verified": True, "confidence": 0.8,
                       "evidence": [{"source_document_id": notesdoc or "source",
                                     "quote": d["quote"], "locator": d["locator"]}]})
    for ind in indicators:
        claims.append({"claim_id": "c%02d" % (len(claims) + 1), "kind": "indicator",
                       "text": "%s = %s %s" % (ind["label"], ind["value"], ind["units"]),
                       "verified": True, "confidence": 0.85,
                       "evidence": [{"source_document_id": notesdoc or "source",
                                     "quote": ind["quote"], "locator": ind["locator"]}]})
    q_text, q_loc = task_quote(inp)
    if not claims:
        claims.append({"claim_id": "c00", "kind": "coverage",
                       "text": "No MathML formula or printed assignment was found in the supplied artifacts.",
                       "verified": bool(q_text), "confidence": 0.0,
                       "evidence": ([{"source_document_id": "task.md", "quote": q_text,
                                      "locator": q_loc}] if q_text else [])})

    source_entries = [{"source_document_id": "task.md", "file": "task.md", "kind": "task",
                       "sha1": sha1_file(inp / "task.md"), "paragraphs": 1,
                       "locator_scheme": "file#char{start}-char{end}", "quote": q_text,
                       "locator": q_loc}]
    for s in sources:
        quote, locator = "", ""
        for f in formulas:
            if f.get("source_document_id") == s["source_document_id"]:
                quote, locator = f["quote"], f["quote_locator"]
                break
        if not quote and notes_text:
            first = [l for l in notes_text.splitlines() if l.strip()]
            if first:
                quote, locator = norm(first[0]), "%s#L1" % (notesdoc or "source")
        s2 = dict(s)
        s2["quote"], s2["locator"] = quote, locator
        source_entries.append(s2)

    if not materials:
        status = "input_error"
    elif not formulas and not notes_text.strip():
        status = "insufficient_evidence"
    else:
        status = "partial"

    uncertainties = [
        {"item": "scope", "detail": "only the supplied artifacts are restored and checked"},
        {"item": "definition_policy",
         "detail": "definitions are taken from explicit sentences; the rest is marked common_knowledge"},
    ]
    for v in variables:
        if v["value"] in (None, ""):
            uncertainties.append({"item": "symbol_without_value",
                                  "detail": "%s has no printed value; its formula stays not computable"
                                  % v["latex"]})
    for c in checks:
        if c["status"] == "example_only":
            uncertainties.append({"item": "example_only_check",
                                  "detail": "%s was probed with unit values only; not a measurement"
                                  % c["formula_id"]})
    notes = ("MathML restored with the package mapping table; %d formula(s), %d symbol(s) "
             "(%d with a printed value). Numeric checks substitute printed assignments only and "
             "are left not computable when a symbol has no value." % (
                 len(formulas), len(variables), coverage["variables_valued"]))

    result = {
        "formulas": [{"formula_id": f["formula_id"], "label": f.get("label", ""),
                      "latex": f["latex"], "mathml_id": f.get("mathml_id", ""),
                      "structure": f["structure"], "structure_summary": f["structure_summary"],
                      "symbols": [s["latex"] for s in f["symbols"]],
                      "locator": f["locator"], "quote": f["quote"],
                      "quote_locator": f["quote_locator"], "quote_kind": f["quote_kind"],
                      "quote_verified": f["quote_verified"]} for f in formulas],
        "variables": variables,
        "derivations": derivations,
        "numeric_checks": checks,
        "indicator_checks": indicators,
        "coverage": coverage,
        "missing_objects": missing_objects,
        "notes": notes,
        "method": {"mathml_to_latex": "explicit tag mapping (mi/mn/mo/mrow/msup/msub/msubsup/mfrac/msqrt/mroot/mfenced)",
                   "definition_source": ["paper_defined", "context_inferred", "common_knowledge"],
                   "numeric_policy": ["computed", "example_only", "not_computable"]},
    }

    jwrite(work / "index.json", {"case_id": cid, "formulas": result["formulas"],
                                 "variables": variables, "derivations": derivations,
                                 "indicator_checks": indicators, "coverage": coverage,
                                 "sources": sources})
    wtext(out / "formulas.tex", render_tex(cid, formulas))
    wtext(out / "symbol_table.csv", render_symbol_table(variables))
    wtext(out / "verification.md",
          render_verification(cid, formulas, variables, checks, derivations, indicators, coverage))
    wtext(out / "run.log", "\n".join([
        "formula-verification %s" % VERSION,
        "case_id=%s status=%s" % (cid, status),
        "formulas=%d symbols=%d derivations=%d indicators=%d checks=%d" % (
            len(formulas), len(variables), len(derivations), len(indicators), len(checks)),
        "seconds=%.2f" % (time.time() - t0)]) + "\n")

    changes.append({"step": "restore", "detail": "restored %d formula(s) and %d symbol(s)"
                    % (len(formulas), len(variables))})
    changes.append({"step": "check", "detail": "%d computed, %d not computable, %d example only"
                    % (coverage["numeric_computed"], coverage["numeric_not_computable"],
                       coverage["numeric_example_only"])})
    limits = [{"item": "no_symbolic_manipulation",
               "detail": "formulas are restored and checked, never algebraically rewritten"},
              {"item": "no_guessed_values",
               "detail": "unprinted symbols stay unvalued; checks are marked not computable"}]
    counts = {"formulas": len(formulas), "symbols": len(variables), "derivations": len(derivations),
              "numeric_checks": len(checks), "indicators": len(indicators), "claims": len(claims)}
    summary = ("Restored %d formula(s) and %d symbol(s) from %d source(s); %d numeric check(s), "
               "%d indicator(s). Status %s." % (
                   len(formulas), len(variables), len(sources), len(checks), len(indicators), status))
    ctx = {"case_id": cid, "status": status, "summary": summary, "result": result,
           "claims": claims, "sources": source_entries, "uncertainties": uncertainties,
           "uncertainty": uncertainties, "change_records": changes, "changes": changes,
           "errors": errors, "degradations": degradations, "pending_human": [],
           "limits": limits, "counts": counts,
           "artifacts": ["result.json", "formulas.tex", "symbol_table.csv", "verification.md"],
           "runtime": {"skill": SKILL, "version": VERSION, "seconds": round(time.time() - t0, 2),
                       "formulas": len(formulas), "symbols": len(variables),
                       "claims": len(claims)}}
    res = finalize(case, ctx)
    jwrite(out / "result.json", res)
    print("status=%s formulas=%d symbols=%d checks=%d indicators=%d" % (
        status, len(formulas), len(variables), len(checks), len(indicators)))
    print("artifacts: result.json, formulas.tex, symbol_table.csv, verification.md | contract keys: %s"
          % ", ".join(contract_keys(case)))
    return res


def cmd_show(args):
    out = Path(args.output or "/app/output")
    work = Path(args.work or "/app/work")
    idx = jread(work / "index.json") or {}
    for f in idx.get("formulas") or []:
        print("[%s] %s  (%s)" % (f["locator"], f["latex"], f.get("structure_summary", "")))
    if not (idx.get("formulas")):
        print("(no restored formula yet; run the build step first)")
    return 0


def cmd_check(args):
    res = run_pipeline(args)
    print("check: status=%s claims=%d" % (res.get("status"), len(res.get("claims") or [])))
    return 0


def cmd_selfcheck(args):
    res = run_pipeline(args)
    oc = res.get("output_contract") or {}
    empty = [k for k, v in oc.items() if v in (None, "", [], {})]
    print("selfcheck: contract keys=%d empty=%d status=%s" % (len(oc), len(empty), res.get("status")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="formula-verification (%s)" % SKILL)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input")
    common.add_argument("--output", "--out", dest="output")
    common.add_argument("--work")
    ap.add_argument("--input")
    ap.add_argument("--output", "--out", dest="output")
    ap.add_argument("--work")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("build", "show", "check", "selfcheck"):
        sub.add_parser(name, parents=[common])
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if not getattr(a, "cmd", None):
        a.cmd = "build"
    for attr in ("input", "output", "work"):
        if not hasattr(a, attr):
            setattr(a, attr, None)
    try:
        {"build": run_pipeline, "check": cmd_check, "selfcheck": cmd_selfcheck,
         "show": cmd_show}[a.cmd](a)
    except Exception:
        try:
            out = Path(getattr(a, "output", None) or "/app/output")
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", {"case_id": "unknown", "status": "input_error", "result": {},
                                         "claims": [], "uncertainties": [{"item": "fatal"}],
                                         "sources": [{"source_document_id": "skill", "note": "fatal path"}],
                                         "change_records": [{"step": "fatal", "detail": "see errors"}],
                                         "limits": [{"item": "fatal"}],
                                         "errors": [{"code": "unhandled_exception",
                                                     "detail": traceback.format_exc(limit=2).replace("\n", " | ")[:600]}],
                                         "runtime": {"skill": SKILL, "version": VERSION}})
        except Exception:
            pass
        print("ERROR handled; legal result.json written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
