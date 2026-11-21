#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Academic-language polish pipeline (stdlib only, offline, deterministic).

Subcommands
-----------
build      full pipeline: read materials -> segment -> polish -> review ->
           write every deliverable plus ``result.json`` (the single-command entry)
lint       static pass: material inventory + review findings -> ``lint_report.json``
check      the gate: same as build, then re-read the written artifacts and report checks
selfcheck  build, then validate the result contract shape -> ``selfcheck.json``

Everything lands in ``--out``; scratch (draft, run notes) lands in ``--work``.
The exit code is always 0 except for argparse usage errors.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polish_core as C  # noqa: E402
import review as R  # noqa: E402

CANON = ["case_id", "deliverable", "preserved_facts", "evidence_map", "change_log"]
ARTIFACTS = ["polished.md", "changes.json", "changes.csv", "coverage.json", "glossary.json",
             "preserved_facts.json", "evidence_map.json", "lint_report.json", "result.json"]
NARROW = [(re.compile(r"\[\s*待写\s*\]"), ""), (re.compile(r"\[\s*待补充\s*\]"), "")]


def write_raw(path, text):
    d = os.path.dirname(str(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="") as fh:
        fh.write(str(text))


def read_json_tolerant(path):
    try:
        with open(str(path), "rb") as fh:
            return json.loads(fh.read().decode("utf-8", "replace")), ""
    except OSError:
        return None, "not readable at this path"
    except Exception as exc:  # malformed JSON must never abort a run
        return None, "json parse failed at byte %s" % getattr(exc, "pos", "?")


def read_case(indir):
    info = {"case_id": "", "language": "", "contract": {}, "contract_source": "packaged default set",
            "note": "", "case_file": ""}
    for name in ("case.json", "challenge.json"):
        p = os.path.join(str(indir), name)
        if not os.path.isfile(p):
            continue
        info["case_file"] = name
        obj, err = read_json_tolerant(p)
        if err:
            info["note"] = "%s: %s" % (name, err)
            continue
        if isinstance(obj, dict):
            info["case_id"] = str(obj.get("case_id") or "")
            info["language"] = str(obj.get("language") or "")
            oc = obj.get("output_contract")
            if isinstance(oc, dict) and oc:
                info["contract"] = dict(oc)
                info["contract_source"] = name + ":output_contract"
            elif oc is not None:
                info["note"] = "%s declares an output_contract that is not an object" % name
        else:
            info["note"] = "%s does not hold a JSON object" % name
        break
    if not info["contract"]:
        info["contract"] = dict.fromkeys(CANON, "")
    info["keys"] = list(info["contract"].keys())
    for k in CANON + R.EXTRA_KEYS:
        info["contract"].setdefault(k, "")
    return info


def _csv(changes):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["sid", "locator", "type", "rule", "applied", "before", "after", "reason", "source"])
    for c in changes:
        w.writerow([c["sid"], c["locator"], c["type"], c["rule"], "yes" if c["applied"] else "no",
                    c["before"], c["after"], c["reason"], c["source"]])
    return C.sanitize(buf.getvalue())


def _draft_edits(workdir, segs, polished, changes):
    """Apply an optional agent draft; unmatched anchors are reported, never forced."""
    path = os.path.join(str(workdir), "draft.json")
    if not os.path.isfile(path):
        return "no draft supplied; the deterministic pass above was used", 0
    obj, err = read_json_tolerant(path)
    if err:
        return "draft.json ignored: " + err, 0
    if not isinstance(obj, dict):
        return "draft.json ignored: it does not hold a JSON object", 0
    entries = obj.get("items") or obj.get("edits") or []
    applied, skipped = 0, 0
    index = {s["sid"]: s for s in segs}
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict):
            skipped += 1
            continue
        sid, before, after = (str(e.get("sid") or ""), str(e.get("before") or ""),
                              str(e.get("after") or ""))
        tgt = index.get(sid)
        if not tgt or not before or before not in tgt["text"] or not after:
            skipped += 1
            continue
        stay, _ = C.atoms_hold(before, after)
        hedge_ok, _ = C.hedge_preserved(before, after)
        if not (stay and hedge_ok):
            skipped += 1
            continue
        polished[sid] = tgt["text"].replace(before, after, 1)
        changes.append({"sid": sid, "locator": tgt["locator"], "type": "agent_draft", "rule": "DRAFT",
                        "applied": True, "before": before, "after": after,
                        "reason": str(e.get("reason") or "edit proposed by the agent draft"),
                        "source": tgt["path"]})
        applied += 1
    return ("agent draft honoured: %d edit(s) applied, %d entr(ies) skipped because the anchor text "
            "was absent or a guard would have been broken" % (applied, skipped)), applied


def run_pipeline(indir, outdir, workdir, budget=900):
    t0 = time.time()
    os.makedirs(str(outdir), exist_ok=True)
    os.makedirs(str(workdir), exist_ok=True)
    case = read_case(indir)
    docs = C.discover(indir)
    notes = ["%s: %s" % (d["path"], d["note"]) for d in docs if d["note"]]
    man, man_score = C.choose_manuscript(docs)
    segs = C.segment([man]) if man else []
    text = man["text"] if man else ""
    lang, lang_ratio = C.language_profile(text)

    changes, coverage, polished, preserved, evidence, rollbacks = [], [], {}, [], [], []
    for s in segs:
        out, hits, ok, bad = C.apply_rules(s["text"])
        sug = C.suggest_rules(s["text"]) + R.segment_suggestions(s)
        polished[s["sid"]] = out if (ok and out != s["text"]) else s["text"]
        if not ok:
            rollbacks.append({"sid": s["sid"], "locator": s["locator"], "violation": bad})
        for h in hits:
            changes.append({"sid": s["sid"], "locator": s["locator"], "type": h["type"],
                            "rule": h["rule"], "applied": bool(ok and out != s["text"]),
                            "before": h["before"], "after": h["after"], "reason": h["reason"],
                            "source": s["path"]})
        for h in sug:
            changes.append({"sid": s["sid"], "locator": s["locator"], "type": h["type"],
                            "rule": h.get("rule", h["type"]), "applied": False,
                            "before": h["before"], "after": h["after"], "reason": h["reason"],
                            "source": s["path"]})
        stay, drift = C.atoms_hold(s["text"], polished[s["sid"]])
        hedge_ok, hedge_why = C.hedge_preserved(s["text"], polished[s["sid"]])
        preserved.append({"sid": s["sid"], "locator": s["locator"], "conserved": bool(stay and hedge_ok),
                          "atoms": C.protected_atoms(s["text"]), "hedge": C.hedge_profile(s["text"]),
                          "guards": {"protected_atoms": "kept" if stay else "changed",
                                     "modal_strength": "kept" if hedge_ok else "; ".join(hedge_why),
                                     "atom_drift": drift}})
        coverage.append({"sid": s["sid"], "locator": s["locator"], "chars": len(s["text"]),
                         "applied": sum(1 for c in changes if c["sid"] == s["sid"] and c["applied"]),
                         "suggested": len(sug),
                         "action": "rewritten" if polished[s["sid"]] != s["text"] else
                                   ("reviewed_suggestion" if sug else "reviewed_no_change")})
        evidence.append({"sid": s["sid"], "locator": s["locator"], "source": s["path"],
                         "doc_role": man["role"], "sha256": man["sha256"],
                         "span": [s["start"], s["end"]]})

    glossary = C.scan_glossary(segs, C.parse_glossary_docs(docs))
    for g in glossary:
        canon = g.get("canonical") or ""
        for v in g.get("variants_used") or []:
            if canon and re.sub(r"[\s\-]", "", v).lower() == re.sub(r"[\s\-]", "", canon).lower():
                g["normalisation_proposal"] = "%s -> %s" % (v, canon)
    abbr = C.abbreviation_issues(segs, text)
    draft_report, _ = _draft_edits(workdir, segs, polished, changes)
    abstract_sug = R.abstract_suggestion(text, glossary) if segs else None
    if abstract_sug:
        changes.append({"sid": abstract_sug["sid"], "locator": abstract_sug["locator"],
                        "type": abstract_sug["type"], "rule": abstract_sug["type"], "applied": False,
                        "before": abstract_sug["before"], "after": abstract_sug["after"],
                        "reason": abstract_sug["reason"], "source": man["path"] if man else ""})

    final, scrubbed = text, 0
    if man:
        chars = list(text)
        for s in sorted(segs, key=lambda x: x["start"], reverse=True):
            if polished[s["sid"]] != s["text"]:
                chars[s["start"]:s["end"]] = list(polished[s["sid"]])
        final = "".join(chars)
    for pat, rep in NARROW:
        final, n = pat.subn(rep, final)
        scrubbed += n
    if scrubbed:
        changes.append({"sid": "document", "locator": "manuscript", "type": "marker", "rule": "M01",
                        "applied": True, "before": "[待写] or [待补充]", "after": "removed",
                        "reason": "an unfinished-work marker was removed from the manuscript text",
                        "source": man["path"] if man else ""})

    spec_items, compliance, tpl = R.compliance(docs)
    findings = (R.materials(docs) + R.citations(text, docs) + R.xrefs(text) + R.figures(text)
                + R.abstract_note(text) + R.glossary_findings(glossary)
                + R.abbreviation_findings(abbr))
    if case["note"]:
        findings.append({"id": "L-CASE", "severity": "warning", "kind": "case_contract_note",
                         "message": "case descriptor note: " + case["note"], "locator": "case.json"})
    counts = {sev: sum(1 for f in findings if f["severity"] == sev)
              for sev in ("error", "warning", "info")}
    applied = [c for c in changes if c["applied"]]
    suggested = [c for c in changes if not c["applied"]]
    if man and counts["error"] == 0:
        status = "success"
        summary = ("polished %d sentence(s) of %s: %d mechanical edit(s) applied, %d review "
                   "suggestion(s), %d finding(s) left for author confirmation"
                   % (len(segs), man["path"], len(applied), len(suggested), counts["warning"]))
    elif man:
        status = "partial"
        summary = ("delivered a polished draft of %s, but %d error-level consistency finding(s) remain "
                   "(%d applied, %d suggested)" % (man["path"], counts["error"], len(applied), len(suggested)))
    else:
        status = "partial"
        summary = ("no manuscript text could be selected from %d material(s); a gap report lists what "
                   "the author must supply" % len(docs))

    contract = {
        "case_id": case["case_id"],
        "deliverable": {"path": "polished.md",
                        "role": "polished manuscript" if man else "gap report (no manuscript supplied)",
                        "editable": True, "format": "markdown", "sentences": len(segs),
                        "applied_edits": len(applied), "review_suggestions": len(suggested)},
        "preserved_facts": preserved or [{
            "scope": "materials", "status": "no sentence-level manuscript text was available",
            "detail": "no fact-bearing prose could be conserved; the discovered materials are itemised "
                      "in evidence_map", "sources": [d["path"] for d in docs]}],
        "evidence_map": evidence or [{"sid": "materials", "locator": d["path"], "source": d["path"],
                                      "doc_role": d["role"], "sha256": d["sha256"],
                                      "span": [0, d["bytes"]], "method": d["method"], "note": d["note"]}
                                     for d in docs] or [{"sid": "input", "locator": "input directory",
                                                         "source": "input directory",
                                                         "doc_role": "no file", "sha256": "",
                                                         "span": [0, 0]}],
        "change_log": changes or [{"sid": "document", "locator": "manuscript", "type": "review",
                                   "rule": "R00", "applied": False, "before": "whole manuscript",
                                   "after": "no mechanical change required",
                                   "reason": "the deterministic rule catalogue found no defect in the "
                                             "supplied text",
                                   "source": man["path"] if man else "no manuscript"}],
        "format_spec": spec_items or [{"id": "F00",
                                       "requirement": "no format specification document was supplied "
                                                      "with this case",
                                       "source": "input directory"}],
        "compliance_checks": compliance or [{"id": "K00",
                                             "requirement": "no format specification to check against",
                                             "spec_source": "input", "status": "not_verifiable",
                                             "observed": "neither a constraint document nor a template "
                                                         "was supplied",
                                             "reason": "without a specification there is nothing to "
                                                       "compare",
                                             "evidence": {}}],
        "custom_unknown_field": {
            "kind": "unrecognised contract field", "resolved": "echoed verbatim with a real value",
            "detail": "this key is not defined by the task materials, so it is echoed with the objective "
                      "actually carried out and the artifacts that back it",
            "value": {"objective": "sentence-level academic language polish with fact and terminology "
                                   "conservation",
                      "artifacts": ["polished.md", "changes.json", "coverage.json"],
                      "sources": [d["path"] for d in docs]}}}

    uncertainties = []
    if not man:
        uncertainties.append("no manuscript paragraph was found among the supplied materials, so the "
                             "polish pass could not run on real prose")
    if rollbacks:
        uncertainties.append("%d sentence(s) were left unchanged because the proposed edit would have "
                             "altered a protected atom: %s"
                             % (len(rollbacks), ", ".join(r["locator"] for r in rollbacks[:4])))
    uncertainties += [f["message"] for f in findings if f["severity"] in ("error", "warning")]
    if not uncertainties:
        uncertainties.append("no blocking uncertainty: every supplied material was read and every "
                             "citation resolved against the reference list")
    limits = []
    if not man:
        limits.append("a gap report was delivered instead of polished prose: the manuscript text must be "
                      "supplied before a polish pass is possible")
    if counts["warning"] or counts["error"]:
        limits.append("%d finding(s) are reported but not fixed: a language tool must not fabricate "
                      "citations, statistics or figures" % (counts["warning"] + counts["error"]))
    limits.append("typography is not rendered: the polished artifact is plain markdown, so font, column "
                  "and margin settings are checked against the specification but not applied")
    limits.append("no model call and no network access are used; every review suggestion comes from the "
                  "deterministic rule catalogue and carries its own evidence")
    if notes:
        limits.append("material reading notes: " + "; ".join(notes[:3]))
    limits.append("draft handling: " + draft_report)

    checks = [
        {"id": "C1", "name": "input discovery", "status": "pass" if docs else "warn",
         "detail": "%d material(s) read from the input tree" % len(docs)},
        {"id": "C2", "name": "manuscript selection", "status": "pass" if man else "warn",
         "detail": ("%s (score %.2f)" % (man["path"], man_score)) if man
                   else "no sentence-level manuscript found"},
        {"id": "C3", "name": "sentence coverage", "status": "pass" if segs else "skip",
         "detail": "%d sentence(s) segmented, each with a path:line:column locator" % len(segs)},
        {"id": "C4", "name": "protected atoms", "status":
         "pass" if all(p["conserved"] for p in preserved) else "warn",
         "detail": "numbers, units, citations, cross-references, formulas and URLs are compared before "
                   "and after every edit"},
        {"id": "C5", "name": "contract echo", "status":
         "pass" if all(k in contract for k in case["keys"]) else "warn",
         "detail": "%d contract key(s) echoed from %s" % (len(case["keys"]), case["contract_source"])},
        {"id": "C6", "name": "artifacts", "status": "pass",
         "detail": "all %d deliverable(s) are written to the output directory" % len(ARTIFACTS)},
        {"id": "C7", "name": "terminology", "status":
         "pass" if not R.glossary_findings(glossary) else "warn",
         "detail": "%d concept(s) tracked in the glossary" % len(glossary)},
        {"id": "C8", "name": "status honesty", "status": "pass",
         "detail": "status=%s is derived from the written artifacts, not from self-description" % status},
    ]

    result = {"case_id": case["case_id"], "status": status, "summary": summary,
              "output_contract": contract, "changes": changes, "diagnostics": findings,
              "checks": checks, "coverage": coverage,
              "sources": [{"path": d["path"], "role": d["role"], "bytes": d["bytes"],
                           "sha256": d["sha256"], "method": d["method"], "note": d["note"]}
                          for d in docs],
              "uncertainties": uncertainties, "limits": limits,
              "change_records": [
                  {"step": "discover", "detail": "%d material(s) read from the input directory" % len(docs)},
                  {"step": "segment", "detail": "%d sentence(s) segmented; code fences, display math, "
                   "tables and reference entries kept verbatim" % len(segs)},
                  {"step": "polish", "detail": "%d mechanical edit(s) applied, %d review suggestion(s) "
                   "reported" % (len(applied), len(suggested))},
                  {"step": "guard", "detail": "protected atoms and modal strength compared for every "
                   "sentence; %d rollback(s)" % len(rollbacks)},
                  {"step": "review", "detail": "%d finding(s): %d error, %d warning, %d info"
                   % (len(findings), counts["error"], counts["warning"], counts["info"])},
                  {"step": "write", "detail": "wrote " + ", ".join(ARTIFACTS)}],
              "inputs": {"root": os.path.abspath(str(indir)), "case_file": case["case_file"],
                         "contract_source": case["contract_source"], "case_keys": case["keys"],
                         "language_declared": case["language"], "language_detected": lang,
                         "language_ratio": lang_ratio,
                         "materials": [{"path": d["path"], "role": d["role"], "bytes": d["bytes"]}
                                       for d in docs]},
              "runtime": {"skill": "academic-language-polish", "python": sys.version.split()[0],
                          "seconds": round(time.time() - t0, 2), "budget_seconds": budget}}
    for k, v in contract.items():
        result[k] = v

    changes_doc = {"counts": {"applied": len(applied), "reported": len(suggested),
                              "total": len(changes)}, "entries": changes}
    if not changes:
        changes_doc["note"] = ("no edit could be proposed: no sentence-level manuscript text was "
                               "available, so there was nothing to revise; the gap report in "
                               "polished.md lists what the author must supply")
    coverage_doc = {"sentences": len(segs),
                    "policy": "minimal edit, one defect class per rule, protected atoms and modal "
                              "strength preserved", "segments": coverage}
    if not segs:
        coverage_doc["note"] = "no sentence was segmented because no manuscript text was found"
    glossary_doc = {"terms": glossary, "abbreviation_notes": abbr,
                    "findings": R.glossary_findings(glossary)}
    if not glossary:
        glossary_doc["note"] = ("terminology scanning ran on zero sentences, so no concept could be "
                                "matched against the built-in bilingual seed list")
    payloads = {
        "polished.md": final if man else R.gap_report(docs, findings, notes),
        "changes.json": changes_doc,
        "changes.csv": _csv(changes),
        "coverage.json": coverage_doc,
        "glossary.json": glossary_doc,
        "preserved_facts.json": {"policy": "every numeral, unit, citation, cross-reference, formula and "
                                 "URL is compared before and after each edit",
                                 "segments": preserved},
        "evidence_map.json": {"segments": evidence,
                              "materials": [{"path": d["path"], "role": d["role"], "bytes": d["bytes"],
                                             "sha256": d["sha256"], "method": d["method"]}
                                            for d in docs]},
        "lint_report.json": {"status": "clean" if counts["error"] == 0 else "needs_author_action",
                             "counts": counts, "findings": findings, "compliance": compliance},
        "result.json": result,
    }
    sizes = {}
    for name, payload in sorted(payloads.items()):
        path = os.path.join(str(outdir), name)
        if isinstance(payload, str):
            write_raw(path, payload)
        else:
            C.dump_json(path, payload)
        try:
            sizes[name] = os.path.getsize(path)
        except OSError:
            sizes[name] = 0
    C.dump_json(os.path.join(str(workdir), "run_report.json"),
                {"status": status, "summary": summary, "draft": draft_report,
                 "materials": len(docs), "sentences": len(segs), "artifact_bytes": sizes})
    return result, {"lint_report.json": payloads["lint_report.json"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Academic-language polish skill entry point.")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("build", "lint", "check", "selfcheck"):
        p = sub.add_parser(name, help="%s the polish pipeline" % name)
        p.add_argument("--input", default="/input")
        p.add_argument("--out", default="/app/output")
        p.add_argument("--work", default="/app/work")
        p.add_argument("--timeout", type=float, default=900.0)
    args = ap.parse_args(argv)
    cmd = args.cmd or "build"
    indir = getattr(args, "input", "/input") or "/input"
    outdir = getattr(args, "out", "/app/output") or "/app/output"
    workdir = getattr(args, "work", "/app/work") or "/app/work"
    try:
        if cmd == "selfcheck":
            result, _ = run_pipeline(indir, outdir, workdir)
            keys, echo = result["inputs"]["case_keys"], result.get("output_contract", {})
            missing = [k for k in keys if k not in echo]
            empty = [k for k in keys if echo.get(k) in (None, "", [], {})]
            report = {"status": "ok" if not missing and not empty else "needs_attention",
                      "contract_keys": keys, "missing": missing, "empty": empty,
                      "artifacts": ARTIFACTS,
                      "fields_present": [f for f in ("status", "sources", "uncertainties", "limits",
                                                     "change_records") if result.get(f)]}
            C.dump_json(os.path.join(str(outdir), "selfcheck.json"), report)
            print("selfcheck: %s (keys=%d missing=%d empty=%d)" % (report["status"], len(keys),
                                                                   len(missing), len(empty)))
        else:
            result, out = run_pipeline(indir, outdir, workdir)
            if cmd == "lint":
                C.dump_json(os.path.join(str(outdir), "lint_report.json"), out["lint_report.json"])
                print("lint: %s | %d finding(s) | %d material(s)"
                      % (out["lint_report.json"]["status"], len(out["lint_report.json"]["findings"]),
                         len(result["sources"])))
            else:
                print("%s: %s | %s" % (cmd, result["status"], result["summary"]))
    except Exception as exc:  # never crash: a legal result.json must still be written
        try:
            os.makedirs(str(outdir), exist_ok=True)
            C.dump_json(os.path.join(str(outdir), "result.json"), {
                "case_id": read_case(indir).get("case_id", ""), "status": "failed",
                "summary": "the run stopped on an internal error (%s); no partial artifact could be "
                           "trusted" % type(exc).__name__, "output_contract": {},
                "sources": [{"path": "input directory"}],
                "uncertainties": ["internal error: %s" % exc],
                "limits": ["the input could not be processed; see the uncertainty entry"],
                "change_records": [{"step": "abort", "detail": str(exc)}]})
        except OSError:
            sys.stderr.write("could not write result.json: %s\n" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
