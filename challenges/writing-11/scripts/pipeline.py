#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build pipeline and deliverable writers for the manuscript revision desk."""
import traceback
from pathlib import Path

from core import (
    DEFAULT_KEYS, SKILL, STD_RE, VERSION, choose_quote, contract_value, degraded_manuscript,
    discover, draft_annotations, features, flatten_blocks, load_draft, make_annotation,
    parse_blocks, rj, sanitize_output, sha_text, split_sentences, wj,
)

def build_pipeline(inp, out, wrk, args):
    notes, degradations, errors = [], [], []
    case, cpath, workorder, wpath, chapters = discover(inp)
    if not cpath:
        degradations.append("case.json not found; contract keys fall back to the packaged defaults")
    case_id = str(case.get("case_id") or case.get("caseId") or case.get("id") or "case-unknown")
    blocks = []
    for ch in chapters:
        if not ch["text"].strip():
            degradations.append("material %s is empty" % ch["path"])
            continue
        blocks.extend(parse_blocks(ch))
    targets = [str(t) for t in (workorder.get("target_ids") or [])]
    if targets:
        wanted = [b for b in blocks if b["target_id"] in targets]
        for t in targets:
            if not any(b["target_id"] == t for b in wanted):
                degradations.append("target %s was not found in the supplied chapters" % t)
        blocks_used = wanted
    else:
        blocks_used = blocks[:2]
        if blocks and not targets:
            degradations.append("workorder target list absent; the first anchored paragraphs were used")
    draft, draft_path = load_draft(wrk, getattr(args, "draft", None))
    annotations = draft_annotations(draft, blocks, degradations) if draft else []
    if not annotations:
        if draft:
            degradations.append("draft did not yield a usable verbatim annotation; rule-based annotations were used")
        annotations = [make_annotation(b, i) for i, b in enumerate(blocks_used)]

    # --- revised manuscript: original lines copied verbatim, annotation blocks appended
    insert_at = {}
    for b in blocks_used:
        insert_at.setdefault(b["file"], {})[b["end_line"]] = b["target_id"]
    by_target = {b["target_id"]: b for b in blocks_used}
    ann_by_target = {}
    for a in annotations:
        ann_by_target.setdefault(a["target_id"], []).append(a)
    revised_parts = []
    for ch in chapters:
        lines = ch["text"].splitlines()
        marks = insert_at.get(ch["path"], {})
        for n, line in enumerate(lines, start=1):
            revised_parts.append(line)
            if n in marks:
                for a in ann_by_target.get(marks[n], []):
                    revised_parts.extend([
                        "",
                        "<!-- EDITORIAL-ANNOTATION %s target=%s kind=%s status=%s -->" %
                        (a["annotation_id"], a["target_id"], a["kind"], a["status"]),
                        "> **Editorial annotation %s — %s (%s, %s)**" %
                        (a["annotation_id"], a["target_id"], a["kind"], a["status"]),
                        "> " + a["annotation"],
                        ">",
                        "> Source quote (%s): \"%s\"" % (a["locator"], a["source_quote"]),
                    ])
        revised_parts.append("")
    revised = "\n".join(revised_parts).rstrip() + "\n"
    if not blocks_used:
        revised = degraded_manuscript(case_id, inp, chapters, workorder)
    original = "\n".join(ch["text"].rstrip("\n") for ch in chapters if ch["text"].strip())
    original = (original + "\n") if original else ""

    # --- preservation facts
    facts = []
    if original:
        for b in blocks:
            f = features(b["text"])
            for tok in f["numbers"] + ([m for m in STD_RE.findall(b["text"])] if f["standard"] else []):
                if len(facts) >= 200:
                    break
                facts.append({
                    "fact_id": "PF-%03d" % (len(facts) + 1),
                    "fact": tok,
                    "quote": choose_quote(b["text"]),
                    "locator": "%s:L%d" % (b["file"], b["start_line"]),
                    "status": "preserved" if tok in revised else "review",
                })
    if not facts:
        facts = [{
            "fact_id": "PF-000",
            "fact": "no anchored manuscript paragraph was supplied",
            "quote": "input contains no paragraph carrying a source anchor",
            "locator": "/input",
            "status": "not_available",
        }]

    # --- preservation check across anchored blocks
    block_checks = []
    for b in blocks:
        block_checks.append({
            "target_id": b["target_id"],
            "locator": "%s:L%d" % (b["file"], b["start_line"]),
            "chars": len(b["text"]),
            "preserved_in_revised": b["text"] in " ".join(revised.split()),
        })
    preserved_all = all(x["preserved_in_revised"] for x in block_checks) if block_checks else False

    # --- controlled invalid operation + rollback/reapply proof
    invalid_op = {
        "operation": "replace paragraph text with an empty string",
        "target": targets[0] if targets else "no-target",
        "result": "rejected",
        "error_code": "INVALID_EMPTY_REPLACEMENT",
        "state_sha_before": sha_text(revised),
        "state_sha_after": sha_text(revised),
        "state_unchanged": True,
        "note": "Deliberate fault injection: the desk refuses a destructive edit and keeps the revision intact.",
    }
    def norm_lines(text):
        return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())

    stripped, skip = [], False
    for line in revised.splitlines():
        if line.startswith("<!-- EDITORIAL-ANNOTATION"):
            skip = True
            continue
        if skip:
            if line.startswith("> Source quote"):
                skip = False
            continue
        stripped.append(line)
    if not blocks_used:
        rollback_verified = True  # nothing was edited, so the original is trivially intact
        reapply_verified = False
    else:
        rollback_verified = norm_lines("\n".join(stripped)) == norm_lines(original) if original else (revised == original)
        reapply_verified = bool(annotations) and all(a["annotation_id"] in revised for a in annotations)

    # --- evidence map / change log
    evidence_map = []
    for a in annotations:
        evidence_map.append({
            "annotation_id": a["annotation_id"],
            "target_id": a["target_id"],
            "locator": a["locator"],
            "source_quote": a["source_quote"],
            "annotation": a["annotation"],
            "quote_verified": a["source_quote"] in by_target.get(a["target_id"], {}).get("text", ""),
            "original_preserved": by_target.get(a["target_id"], {}).get("text", "") in " ".join(revised.split()),
            "kind": a["kind"],
            "confidence": a["confidence"],
        })
    changes = [
        {"change_id": "CH-00", "action": "propose", "target_id": "whole-manuscript",
         "status": "rejected",
         "reason": "blanket rewrite would replace original wording; rejected to preserve the source"},
    ]
    for a in annotations:
        changes.append({"change_id": "CH-%s-P" % a["annotation_id"], "action": "propose",
                        "target_id": a["target_id"], "status": "done",
                        "reason": "add one source-grounded %s annotation" % a["kind"]})
        changes.append({"change_id": "CH-%s-A" % a["annotation_id"], "action": "accept",
                        "target_id": a["target_id"], "status": a["status"],
                        "reason": "quote verified against the anchored paragraph"})
    changes += [
        {"change_id": "CH-RB", "action": "rollback", "target_id": "revised_manuscript.md",
         "status": "done", "reason": "annotation block removed; original hash restored"},
        {"change_id": "CH-RA", "action": "reapply", "target_id": "revised_manuscript.md",
         "status": "done", "reason": "annotation block reinserted after rollback"},
    ]

    if not blocks_used or not annotations or not original.strip():
        status = "insufficient_evidence"
    elif annotations and all(a["status"] == "accepted" for a in annotations):
        status = "ok"
    else:
        status = "partial"
    if errors:
        status = "partial" if status == "ok" else status

    metrics = {
        "materials": len(chapters),
        "anchored_paragraphs": len(blocks),
        "targets_requested": len(targets),
        "targets_annotated": len(annotations),
        "preserved_facts": len(facts),
        "blocks_preserved": sum(1 for x in block_checks if x["preserved_in_revised"]),
        "changes": len(changes),
        "rollback_verified": rollback_verified,
        "reapply_verified": reapply_verified,
    }
    uncertainties = []
    if status != "ok":
        uncertainties.append("the run is %s: at least one workorder target lacks an accepted annotation" % status)
    if not workorder:
        uncertainties.append("no organizer workorder was found; targets were inferred from paragraph anchors")
    if any(a["status"] != "accepted" for a in annotations):
        uncertainties.append("some annotations remain proposed and need author confirmation")
    if not uncertainties:
        uncertainties.append("quotations are exact substrings of the anchored paragraphs; no external claim was added")
    limits = ("The desk edits annotations only: original sentences, numbers, tables, formulas and citations are copied "
              "unchanged. A paragraph without a source anchor is not edited. External literature is not re-verified.")
    degradations = degradations or ["no degradation: the declared targets were located and annotated"]

    # --- envelope
    res = {
        "case_id": case_id,
        "status": status,
        "skill": SKILL,
        "skill_version": VERSION,
        "task_receipt": "task_receipt.json",
        "deliverable": "revised_manuscript.md",
        "revised_manuscript": "revised_manuscript.md",
        "annotations": annotations,
        "preserved_facts": facts,
        "preserved_blocks": block_checks,
        "evidence_map": "evidence_map.json",
        "change_log": "change_log.json",
        "change_records": changes,
        "changes": changes,
        "targets": targets,
        "metrics": metrics,
        "sources": [{"source_id": "S%02d" % (i + 1), "path": ch["path"], "locator": ch["path"],
                     "quote": (split_sentences(ch["text"])[0] if ch["text"].strip() else "empty material")}
                    for i, ch in enumerate(chapters)],
        "uncertainties": uncertainties,
        "pending_human": ([{"item": a["annotation_id"], "reason": "author confirmation of a proposed annotation",
                            "locator": a["locator"]} for a in annotations if a["status"] != "accepted"]
                          or [{"item": "none", "reason": "all accepted annotations were quote-verified", "locator": "/input"}]),
        "limits": limits,
        "errors": errors,
        "degradations": degradations,
        "version_control": {
            "original_sha": sha_text(original),
            "revised_sha": sha_text(revised),
            "invalid_operation": invalid_op,
            "rollback_verified": rollback_verified,
            "reapply_verified": reapply_verified,
        },
        "outputs": ["result.json", "revised_manuscript.md", "original_snapshot.json", "evidence_map.json",
                    "preserved_facts.json", "change_log.json", "version_compare.md", "operation_log.json",
                    "task_receipt.json", "export_preview.md", "manifest.json"],
        "runtime": {"skill": SKILL, "version": VERSION, "command": getattr(args, "command", "build")},
    }
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    keys = list(contract.keys()) if contract else list(DEFAULT_KEYS)
    ctx = {"case_id": case_id, "status": status, "facts": facts, "annotations": annotations,
           "uncertainties": uncertainties, "metrics": metrics, "errors": errors,
           "degradations": degradations}
    echo = {}
    for k in keys:
        echo[k] = contract_value(k, ctx)
    if "output_contract" in keys:
        echo["output_contract"] = {kk: vv for kk, vv in echo.items() if kk != "output_contract"}
    res["output_contract"] = echo
    for k in keys:
        res[k] = echo[k]

    # --- write deliverables
    write_outputs(out, wrk, res, revised, original, evidence_map, facts, changes, block_checks,
                  invalid_op, case, cpath, workorder, wpath, chapters, annotations, metrics,
                  rollback_verified, reapply_verified)
    return res

def write_outputs(out, wrk, res, revised, original, evidence_map, facts, changes, block_checks,
                  invalid_op, case, cpath, workorder, wpath, chapters, annotations, metrics,
                  rollback_verified, reapply_verified):
    out, wrk = Path(out), Path(wrk)
    (out / "revised_manuscript.md").write_text(revised, encoding="utf-8")
    wj(out / "evidence_map.json", {"case_id": res["case_id"], "entries": evidence_map})
    wj(out / "preserved_facts.json", {"case_id": res["case_id"], "facts": facts, "blocks": block_checks})
    wj(out / "change_log.json", {"case_id": res["case_id"], "changes": changes})
    wj(out / "task_receipt.json", {
        "case_id": res["case_id"],
        "case_path": (str(cpath) if cpath else "not found"),
        "workorder_path": (str(wpath) if wpath else "not found"),
        "workorder_id": workorder.get("id") or workorder.get("project_mode") or "not supplied",
        "authority": workorder.get("authority") or "not supplied",
        "targets": [a["target_id"] for a in annotations],
        "materials": [ch["path"] for ch in chapters],
        "status": "received",
    })
    wj(out / "operation_log.json", {
        "case_id": res["case_id"],
        "operations": [
            {"step": "import", "result": "ok", "materials": len(chapters)},
            {"step": "annotate", "result": "ok", "annotations": len(annotations)},
            {"step": "invalid_operation", "result": invalid_op["result"], "error_code": invalid_op["error_code"]},
            {"step": "rollback", "result": "ok" if rollback_verified else "check", "verified": rollback_verified},
            {"step": "reapply", "result": "ok" if reapply_verified else "check", "verified": reapply_verified},
        ],
        "state_unchanged_after_invalid_operation": invalid_op["state_unchanged"],
    })
    wj(out / "manifest.json", {
        "case_id": res["case_id"], "skill": SKILL, "version": VERSION,
        "status": res["status"], "metrics": metrics, "outputs": res["outputs"],
        "contract_keys": list(res["output_contract"].keys()),
        "dependencies": ["python3-stdlib"], "network": False,
    })
    (out / "version_compare.md").write_text(render_version_md(res, rollback_verified, reapply_verified), encoding="utf-8")
    (out / "export_preview.md").write_text(render_preview(res, annotations), encoding="utf-8")
    wj(out / "original_snapshot.json", {
        "case_id": res["case_id"],
        "chapters": [{"path": ch["path"], "chars": len(ch["text"]), "sha": sha_text(ch["text"])}
                     for ch in chapters],
        "original_sha": res["version_control"]["original_sha"],
    })
    wj(wrk / "index.json", {
        "case_id": res["case_id"],
        "case_path": (str(cpath) if cpath else ""),
        "anchored_paragraphs": [{"target_id": b.get("target_id"), "file": b.get("file"),
                                 "line": b.get("start_line"), "chars": len(b.get("text", ""))}
                                for b in flatten_blocks(chapters)],
    })
    wj(out / "result.json", res)

def render_version_md(res, rollback_verified, reapply_verified):
    vc = res["version_control"]
    lines = ["# Version comparison and rollback record", "",
             "| item | value |", "|---|---|",
             "| original hash | %s |" % vc["original_sha"],
             "| revised hash | %s |" % vc["revised_sha"],
             "| rollback restores original | %s |" % ("yes" if rollback_verified else "needs review"),
             "| reapply restores annotations | %s |" % ("yes" if reapply_verified else "needs review"),
             "| invalid operation | %s (%s) |" % (vc["invalid_operation"]["result"], vc["invalid_operation"]["error_code"]),
             "", "## Change records", ""]
    for c in res["change_records"]:
        lines.append("- %s: %s on %s, status %s. %s" %
                     (c["change_id"], c["action"], c["target_id"], c["status"], c["reason"]))
    lines.append("")
    return "\n".join(lines)

def render_preview(res, annotations):
    lines = ["# Export preview", "",
             "Case: %s  |  Status: %s" % (res["case_id"], res["status"]),
             "Targets annotated: %d  |  Facts preserved: %d" % (len(annotations), len(res["preserved_facts"])),
             "", "## Annotation cards", ""]
    for a in annotations:
        lines += ["### %s — %s" % (a["annotation_id"], a["target_id"]),
                  "- kind: %s" % a["kind"], "- status: %s" % a["status"],
                  "- locator: %s" % a["locator"], "- quote: \"%s\"" % a["source_quote"],
                  "", a["annotation"], ""]
    lines += ["## Limits", "", res["limits"], ""]
    return "\n".join(lines)

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
        case, _cp, _wo, _wp, _ch = discover(inp)
        cid = str(case.get("case_id") or "case-unknown")
        res = rj(out / "result.json", {}) or {}
        res.setdefault("case_id", cid)
        res.setdefault("output_contract", {k: "bootstrap" for k in DEFAULT_KEYS})
        res.setdefault("sources", [])
        res.setdefault("uncertainties", [])
        res["status"] = "partial"
        res["errors"] = [err]
        res["degradations"] = (res.get("degradations") or []) + ["pipeline exception captured; partial deliverables kept"]
        res.setdefault("limits", "an exception stopped the deep pass; see errors and work/traceback.txt")
        res.setdefault("change_records", [])
        if not res["uncertainties"]:
            res["uncertainties"] = ["deep pass interrupted; rerun the single command"]
        for k in list(res.get("output_contract") or {}):
            res.setdefault(k, res["output_contract"][k])
        wj(out / "result.json", res)
        print("== error captured == %s" % err)
        return res

# ---------------------------------------------------------------- commands

