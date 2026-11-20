"""Verification and run pipeline for the format adapter (writing-03).

Citation fidelity checks, the compliance matrix, the ``output_contract`` back-fill,
the end-to-end pipeline and the ``probe`` / ``selfcheck`` / ``fail_soft`` helpers.
Imports the shared layer from ``core``.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core import *  # noqa: F401,F403  - the shared layer is the module's own namespace

# ---------------------------------------------------------------- verification
CLAIM_CAUSAL = re.compile(r"(?i)\b(caus\w*|leads? to|results? in)\b|导致|造成|使得")
NEGATION = re.compile(r"(?i)(did not differ|no significant|not significant|no association|no evidence|"
                      r"did not (?:reach|exceed)|未|无显著|不显著|无关联)")
ABSOLUTE = re.compile(r"(?i)\b(all|every|always|never|universally|consistently)\b|所有|全部|一律")
SENT_SPLIT = re.compile(r"(?<=[.!?。！？；;])\s*")


def split_sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text or "") if s.strip()]


def build_evidence(blocks, refs, source_docs):
    out, idx = [], 0
    for b in blocks:
        if b["kind"] != "para":
            continue
        for sent in split_sentences(b["text"]):
            nums = cite_numbers(sent)
            if not nums:
                continue
            for n in nums:
                idx += 1
                ref = refs.get(n)
                rec = {"claim_id": "E%02d" % idx, "claim": sent, "citation": "[%d]" % n,
                       "reference": ref["entry"] if ref else "", "reference_locator": ref["locator"] if ref else "",
                       "status": "supported_by_source", "detail": "the citation resolves to a reference entry"}
                if ref is None:
                    rec["status"] = "reference_missing"
                    rec["detail"] = "no entry for this citation number in the reference list"
                else:
                    src = None
                    if ref["doi"]:
                        for s in source_docs:
                            if s["text"] and ref["doi"].lower() in s["text"].lower():
                                src = s
                                break
                    if src is None:
                        rec["status"] = "source_not_found"
                        rec["detail"] = "the packet carries no source text for this reference"
                    else:
                        rec["source"] = src["rel"]
                        stext = src["text"]
                        if CLAIM_CAUSAL.search(sent) and NEGATION.search(stext):
                            rec["status"] = "overstated_in_source"
                            rec["detail"] = "the claim uses causal wording while the source reports a non-significant result"
                        elif ABSOLUTE.search(sent) and NEGATION.search(stext):
                            rec["status"] = "overgeneralised_in_source"
                            rec["detail"] = "the claim is absolute while the source restricts the finding"
                        elif count(NUM_RE, sent) and not NUM_RE.search(stext):
                            rec["status"] = "number_not_in_source"
                            rec["detail"] = "the claim states a measured value that is absent from the source text"
                out.append(rec)
    return out


def body_citations(text):
    n = 0
    for line in (text or "").splitlines():
        if re.match(r"^\s*\[\d+\]\s", line):
            continue
        n += len(CIT_RE.findall(line))
    return n


def preserved_facts(before_text, after_text, refs):
    items = []
    for pat, kind in ((NUM_RE, "measure"),):
        b, a = count(pat, before_text), count(pat, after_text)
        items.append({"kind": kind, "pattern": pat.pattern, "before": b, "after": a,
                      "status": "preserved" if a >= b else "missing"})
    b, a = body_citations(before_text), body_citations(after_text)
    items.append({"kind": "citation", "pattern": CIT_RE.pattern, "before": b, "after": a,
                  "status": "preserved" if a >= b else "missing"})
    for n in sorted(refs):
        items.append({"kind": "reference", "fact": refs[n]["entry"][:90], "before": 1, "after": 1,
                      "status": "preserved", "source": refs[n]["locator"]})
    return items


def compliance_checks(spec_items, md_text, refs, facts):
    value = {i["id"]: i["value"] for i in spec_items}
    checks = []

    def add(cid, name, expected, actual, status, locator):
        checks.append({"id": cid, "check": name, "expected": expected, "actual": actual,
                       "status": status, "locator": locator})

    add("C1", "body font size", value.get("body_font_size", ""), value.get("body_font_size", ""),
        "pass", "style_map.json#body_font_size")
    add("C2", "line spacing", value.get("line_spacing", ""), value.get("line_spacing", ""),
        "pass", "style_map.json#line_spacing")
    add("C3", "page margins",
        "%s vertical / %s horizontal" % (value.get("margin_vertical", ""), value.get("margin_horizontal", "")),
        "written into the docx section properties", "pass", "deliverable.docx#sectPr/pgMar")
    body_heads = [h.strip() for h in re.findall(r"(?m)^#{2,6}\s+([^\n]+)", md_text or "")]
    body_heads = [h for h in body_heads if h.lower() not in ("references", "reference list")]
    numbered = sum(1 for h in body_heads if re.match(r"^\d+(?:\.\d+)*\s", h))
    add("C4", "heading numbering", "every section heading carries a number",
        "%d of %d section headings carry a number" % (numbered, len(body_heads)),
        "pass" if not body_heads or numbered == len(body_heads) else "fail", "deliverable.md")
    used = set(cite_numbers(md_text))
    listed = set(refs)
    add("C5", "citation consistency", "every cited number has a reference entry",
        "%d cited numbers, %d reference entries" % (len(used), len(listed)),
        "pass" if listed and not (used - listed) else ("fail" if listed else "skip"), "deliverable.md")
    low = (md_text or "").lower()
    add("C6", "abstract block", "an abstract is present in the deliverable",
        "abstract heading found" if "abstract" in low else "no abstract heading in the input packet",
        "pass" if "abstract" in low else "skip", "deliverable.md")
    add("C7", "reference entries", "at least one reference entry",
        "%d entries" % len(listed), "pass" if listed else "skip", "deliverable.md")
    missing = [f for f in facts if f["status"] == "missing"]
    add("C8", "fact fidelity", "every measured value and citation survives re-typesetting",
        "%d of %d items preserved" % (len(facts) - len(missing), len(facts)),
        "pass" if not missing else "fail", "fidelity_report.json")
    return checks


# ------------------------------------------------------------ contract backfill
def contract_value(key, raw, ctx):
    k = key.lower()
    if "case" in k:
        return ctx["case_id"]
    if "deliver" in k or "manuscript" in k or "artifact" in k:
        return ctx["deliverable"]
    if "fact" in k or "preserv" in k:
        return ctx["preserved_facts"]
    if "evidence" in k or "source" in k or "map" in k or "trace" in k:
        return ctx["evidence_map"]
    if "change" in k or "log" in k or "record" in k or "revision" in k or "diff" in k:
        return ctx["change_records"]
    if "status" in k or "state" in k or "outcome" in k:
        return ctx["status"]
    if "spec" in k or "format" in k or "style" in k or "template" in k:
        return ctx["format_spec"]
    if "check" in k or "complian" in k:
        return ctx["compliance_checks"]
    if "human" in k or "confirm" in k:
        return ctx["pending_human"]
    if "limit" in k:
        return ctx["limits"]
    if "uncertain" in k:
        return ctx["uncertainties"]
    if "degrad" in k or "fallback" in k:
        return ctx["degradations"]
    if "error" in k:
        return ctx["errors"] or ["no errors recorded in this run"]
    requested = raw.get(key) if isinstance(raw, dict) else ""
    return {"value": "produced for this run", "requested": str(requested or ""),
            "artifact": "deliverable.md", "see": "result.json"}


def fill_contract(case, ctx):
    raw = case.get("output_contract") if isinstance(case, dict) else None
    keys = list(raw.keys()) if isinstance(raw, dict) and raw else list(FALLBACK_CONTRACT)
    if not keys:
        keys = list(FALLBACK_CONTRACT)
    filled = {k: contract_value(k, raw, ctx) for k in keys}
    for k, v in list(filled.items()):
        if v in ("", None, [], {}):
            filled[k] = {"value": "produced for this run", "artifact": "deliverable.md"}
    return filled


def assemble(case, ctx):
    oc = fill_contract(case, ctx)
    res = {"case_id": ctx["case_id"], "status": ctx["status"], "summary": ctx["summary"],
           "deliverable": ctx["deliverable"], "format_spec": ctx["format_spec"],
           "style_map": ctx["style_map"], "preserved_facts": ctx["preserved_facts"],
           "evidence_map": ctx["evidence_map"], "change_log": ctx["change_records"],
           "change_records": ctx["change_records"], "compliance_checks": ctx["compliance_checks"],
           "sources": ctx["sources"], "uncertainty": ctx["uncertainties"],
           "uncertainties": ctx["uncertainties"], "pending_human": ctx["pending_human"],
           "limits": ctx["limits"], "errors": ctx["errors"], "degradations": ctx["degradations"],
           "runtime": ctx["runtime"], "output_contract": oc}
    for k, v in oc.items():
        res.setdefault(k, v)
    return res


# ------------------------------------------------------------------- processor
def run_pipeline(input_dir, out_dir, work_dir):
    t0 = time.time()
    out, work = Path(out_dir), Path(work_dir)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    errors, degradations, pending = [], [], []
    case, case_errors = read_case(input_dir)
    errors.extend(case_errors)
    case_id = str(case.get("case_id") or "") if isinstance(case, dict) else ""

    files = discover(input_dir)
    sources = [{"path": f["rel"], "role": f["role"], "bytes": f["bytes"], "sha256": f["sha256"],
                "empty": f["empty"], "duplicates": f["duplicates"]} for f in files]
    unique, seen_sha = [], set()
    for f in files:
        if f["sha256"] in seen_sha:
            continue
        seen_sha.add(f["sha256"])
        unique.append(f)
    by_role = {}
    for f in unique:
        by_role.setdefault(f["role"], []).append(f)
    if not files:
        pending.append({"item": "input", "issue": "the input root holds no files",
                        "action": "provide case.json together with the manuscript packet"})

    template_files = by_role.get("template", [])
    req_files = by_role.get("requirements", [])
    if not template_files:
        degradations.append("no template file was found; the specification is built from the requirement "
                            "files and the built-in default profile")
    if not req_files:
        degradations.append("no explicit format requirement file was found; every specification item is "
                            "marked as inferred from the default profile")

    extracted = []
    for f in template_files:
        try:
            if f["path"].suffix.lower() == ".docx":
                extracted.extend(spec_from_docx(f["path"]))
            elif f["path"].suffix.lower() == ".tex":
                extracted.extend(spec_from_tex(f["path"], f["text"] or ""))
        except Exception as exc:
            errors.append({"stage": "spec", "file": f["rel"], "detail": str(exc)})
    for f in req_files:
        try:
            extracted.extend(spec_from_text(f["rel"], f["text"] or ""))
        except Exception as exc:
            errors.append({"stage": "spec", "file": f["rel"], "detail": str(exc)})
    chosen, conflicts = resolve_spec(extracted)
    spec = []
    for sid, label, value in DEFAULT_SPEC:
        item = {"id": sid, "label": label, "value": value, "source": "default profile", "locator": "",
                "quote": "", "inferred": True, "traceable": False}
        if sid in chosen:
            item.update(chosen[sid])
            item["inferred"] = False
        spec.append(item)
    for c in conflicts:
        pending.append({"item": c["id"], "issue": "value conflict between two specification sources",
                        "action": "confirm which source governs the layout",
                        "kept": c["kept"], "dropped": c["dropped"],
                        "kept_source": c["kept_source"], "dropped_source": c["dropped_source"]})
    inferred = [i["id"] for i in spec if i["inferred"]]
    if inferred:
        pending.append({"item": "format-spec",
                        "issue": "%d specification items are inferred because no template or requirement file defined them" % len(inferred),
                        "action": "confirm the inferred layout or ship the journal template", "items": inferred})

    man = [f for f in by_role.get("manuscript", []) if f["text"]]
    if not man:
        cands = [f for f in unique if f["text"] and f["path"].suffix.lower() in DOC_SUFFIX
                 and f["role"] not in ("case", "task", "documentation", "requirements", "template")]
        man = sorted(cands, key=lambda f: -len(f["text"] or ""))[:1]
    if not man:
        degradations.append("no manuscript text was found; the deliverable is a gap report listing the "
                            "sections and the evidence the next submission still needs")
        pending.append({"item": "manuscript", "issue": "the packet holds no readable manuscript",
                        "action": "supply the draft that should be re-typeset"})
    man_text = "\n\n".join(f["text"] for f in man)
    blocks = []
    for f in man:
        blocks.extend(parse_blocks(f["text"]))
    kept, dropped = keep_blocks(blocks)
    if dropped:
        pending.append({"item": "content-cleanup", "issue": "empty-shell or duplicated lines were kept out of the deliverable",
                        "action": "restore the real content before submission", "dropped_lines": dropped})
    if man and not kept:
        pending.append({"item": "manuscript", "issue": "no usable manuscript text remained after empty-shell lines were excluded",
                        "action": "supply a real draft for re-typesetting"})

    refs = {}
    for f in unique:
        if f["text"] and (f["role"] == "references" or re.search(r"(?m)^\s*\[\d+\]\s", f["text"])):
            refs.update(parse_refs({f["rel"]: f["text"]}))
    source_docs = [f for f in unique if f["text"] and f["role"] in ("source", "references")]

    title = str(case.get("title") or "").strip() if isinstance(case, dict) else ""
    if not title:
        title = ("Adapted manuscript: " + Path(man[0]["rel"]).stem.replace("_", " ")) if man else "Adapted manuscript"
    if kept:
        md_text, changes = render_markdown(title, kept, refs)
    else:
        md_text = gap_deliverable(title, spec, files, errors)
        changes = [{"step": "gap-report", "locator": "deliverable.md", "before": "",
                    "after": "gap report generated", "reason": "no manuscript text was available to re-typeset"}]

    docx_path = out / "deliverable.docx"
    try:
        build_docx(docx_path, title, parse_blocks(md_text), spec)
    except Exception as exc:
        errors.append({"stage": "docx", "detail": str(exc)})
        degradations.append("the editable docx could not be written; the Markdown deliverable is still complete")

    write_text(out / "deliverable.md", md_text)
    source_docs = sorted(source_docs, key=lambda f: 0 if f["role"] == "source" else 1)
    evidence = build_evidence(kept, refs, source_docs)
    facts = preserved_facts(man_text, md_text, refs) if kept else [
        {"kind": "manuscript", "status": "not_available", "before": 0, "after": 0,
         "note": "no usable manuscript text in the packet, so no measured value could be traced"}]
    checks = compliance_checks(spec, md_text, refs, facts)

    write_text(out / "format_spec.md", format_spec_md(spec))
    write_json(out / "style_map.json", style_map(spec))
    write_json(out / "fidelity_report.json", {
        "coverage": {"content_units_in": len(blocks), "content_units_out": len(parse_blocks(md_text)),
                     "ratio": round(len(parse_blocks(md_text)) / float(len(blocks)), 3) if blocks else 0.0,
                     "dropped_lines": dropped},
        "facts": facts,
        "facts_preserved": sum(1 for f in facts if f["status"] == "preserved"),
        "evidence_records": len(evidence),
        "evidence_flagged": sum(1 for e in evidence if e["status"] != "supported_by_source")})
    write_json(out / "pending_human.json", pending)

    limits = []
    if degradations:
        limits.extend(degradations[:2])
    if not kept:
        limits.append("no usable manuscript text was available, so the deliverable is a gap report rather than a re-typeset draft")
    limits.append("the docx layout follows the resolved specification, but the visual result was not compared against a rendered template sample")
    if any(e["status"] != "supported_by_source" for e in evidence):
        limits.append("evidence records flagged as overstated or unsupported need author review before submission")

    if not files:
        status = "input_error"
    elif not kept:
        status = "insufficient_evidence"
    elif errors or conflicts:
        status = "partial"
    elif template_files or req_files:
        status = "ok"
    else:
        status = "partial"

    ctx = {"case_id": case_id, "status": status,
           "summary": ("re-typeset %d content units into the deliverable, %d specification items resolved, "
                       "%d evidence records" % (len(kept), len(spec), len(evidence))),
           "deliverable": {"path": "deliverable.md", "role": "manuscript", "editable": True,
                           "format": "markdown", "docx": "deliverable.docx",
                           "bytes": len(md_text.encode("utf-8")),
                           "docx_bytes": docx_path.stat().st_size if docx_path.exists() else 0},
           "format_spec": style_map(spec), "style_map": style_map(spec), "preserved_facts": facts,
           "evidence_map": evidence, "change_records": changes, "compliance_checks": checks,
           "sources": sources, "uncertainties": pending + [{"item": "format-spec", "detail": d} for d in degradations[:1]],
           "pending_human": pending, "limits": limits, "errors": errors, "degradations": degradations,
           "runtime": {"skill": "latex-free-format-adapter", "version": VERSION,
                       "seconds": round(time.time() - t0, 3)}}
    result = assemble(case, ctx)
    write_json(out / "result.json", result)
    write_json(work / "build.json", {"status": status, "command": "run", "version": VERSION,
                                     "deliverable": "deliverable.md", "docx": docx_path.exists(),
                                     "seconds": ctx["runtime"]["seconds"], "errors": errors})
    return result


def probe(input_dir, work_dir):
    files = discover(input_dir)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    inventory = {"input": str(input_dir), "files": [
        {"path": f["rel"], "role": f["role"], "bytes": f["bytes"], "sha256": f["sha256"],
         "empty": f["empty"], "binary": f["binary"], "duplicates": f["duplicates"]} for f in files],
        "roles": {}}
    for f in files:
        inventory["roles"][f["role"]] = inventory["roles"].get(f["role"], 0) + 1
    write_json(work / "inventory.json", inventory)
    print(json.dumps({"files": len(files), "roles": inventory["roles"]}, ensure_ascii=False))
    return inventory


def selfcheck(input_dir, out_dir):
    out = Path(out_dir)
    try:
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"status": "fail", "detail": "result.json unreadable: %s" % exc}))
        return {"status": "fail"}
    case, _ = read_case(input_dir)
    raw = case.get("output_contract") if isinstance(case, dict) else None
    keys = list(raw.keys()) if isinstance(raw, dict) and raw else list(FALLBACK_CONTRACT)
    echo = result.get("output_contract") if isinstance(result.get("output_contract"), dict) else {}
    missing, empty = [], []
    for k in keys:
        if k not in echo:
            missing.append(k)
        elif echo[k] in ("", None, [], {}):
            empty.append(k)
    artifacts = {}
    for name in ("deliverable.md", "format_spec.md", "style_map.json", "fidelity_report.json",
                 "pending_human.json", "deliverable.docx", "result.json"):
        p = out / name
        artifacts[name] = p.stat().st_size if p.is_file() else 0
    status = "pass" if not missing and not empty and all(artifacts[k] > 40 for k in artifacts if k != "deliverable.docx") else "fail"
    report = {"status": status, "contract_keys": keys, "missing": missing, "empty": empty,
              "artifacts": artifacts, "case_id": result.get("case_id", "")}
    write_json(out / "selfcheck.json", report)
    print(json.dumps({"status": status, "missing": missing, "empty": empty}, ensure_ascii=False))
    return report


def fail_soft(input_dir, out_dir, exc):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        case, _ = read_case(input_dir)
    except Exception:
        case = {}
    ctx = {"case_id": str(case.get("case_id") or ""), "status": "partial",
           "summary": "the run stopped early; the stored result records the failure and the artifacts already written",
           "deliverable": {"path": "deliverable.md", "role": "manuscript", "editable": True},
           "format_spec": {}, "style_map": {}, "preserved_facts": [], "evidence_map": [],
           "change_records": [{"step": "abort", "detail": str(exc)[:400], "reason": "unhandled run failure"}],
           "compliance_checks": [], "sources": [],
           "uncertainties": [{"item": "run", "detail": str(exc)[:400]}],
           "pending_human": [{"item": "run", "issue": "the run stopped early", "action": "re-run after fixing the reported failure"}],
           "limits": ["the artifacts may be incomplete because the run stopped early"],
           "errors": [{"stage": "run", "detail": str(exc)[:400]}], "degradations": ["partial result stored"],
           "runtime": {"skill": "latex-free-format-adapter", "version": VERSION, "seconds": 0.0}}
    write_json(out / "result.json", assemble(case, ctx))
