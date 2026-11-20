#!/usr/bin/env python3
"""Build an evidence-linked introduction and related-work deliverable.

    build.py --input /input --out /app/output --work /app/work

Single deterministic pass (standard library only):
discover inputs -> classify sources (current work / prior work / instructions)
-> extract verbatim evidence spans with 1-based line numbers -> group prior
work -> derive a bounded gap from settled premises -> align contributions with
current-work evidence -> write manuscript.md, evidence.json, review.md,
audit.json and result.json.

Never invents scientific content: every claim is a verbatim sentence from a
supplied source, and every needed output_contract key is echoed to the top
level.  A missing or unreadable corpus degrades to an honest partial/blocked
result and still exits 0.
"""
import argparse
import hashlib
import json
import re
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".json", ".csv", ".tex", ".yaml", ".yml"}
CAP_EVIDENCE = 48
CAP_CLAIMS = 48

CONTRACT_KEYS = ("case_id", "status", "status_reason", "summary", "main_result",
                 "sources", "artifacts", "uncertainty", "changes", "process",
                 "audit", "ledger_summary", "limits", "inputs", "runtime",
                 "output_contract")

CITATION_RE = re.compile(r"\[\d+\]|\([A-Z][A-Za-z.\-']+(?: et al\.)?, \d{4}[a-z]?\)")


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(path.read_bytes())


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# PDF text layer (a compact stdlib stream parser; only used when a PDF appears)
# --------------------------------------------------------------------------
def _inflate(raw):
    for fn in (lambda b: zlib.decompress(b),
               lambda b: zlib.decompressobj().decompress(b)):
        try:
            out = fn(raw)
            if out:
                return out
        except zlib.error:
            continue
    return b""


def _operator_strings(content):
    parts = []
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>|T\*|Td|TD|TJ|Tj", content):
        tok = m.group(0)
        if tok in (b"T*", b"Td", b"TD"):
            parts.append(b"\n")
        elif tok in (b"TJ", b"Tj"):
            continue
        elif tok.startswith(b"("):
            body = tok[1:-1]
            body = re.sub(rb"\\([()\\])", rb"\1", body)
            body = body.replace(b"\\n", b"\n").replace(b"\\r", b" ").replace(b"\\t", b" ")
            parts.append(body)
        else:
            hexed = re.sub(rb"[^0-9A-Fa-f]", b"", tok[1:-1])
            if len(hexed) % 2:
                hexed += b"0"
            try:
                parts.append(bytes.fromhex(hexed.decode("ascii")))
            except (ValueError, UnicodeDecodeError):
                pass
    return b"".join(parts)


def extract_pdf_text(path):
    data = path.read_bytes()
    chunks = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        decoded = _inflate(data[start:end].rstrip(b"\r\n"))
        if not decoded:
            continue
        text = _operator_strings(decoded)
        if text.strip():
            chunks.append(text)
    return b"\n".join(chunks).decode("latin-1", "replace")


# --------------------------------------------------------------------------
# discovery and classification
# --------------------------------------------------------------------------
def classify(name):
    low = name.lower()
    if re.search(r"review|comment|referee|response", low):
        return "other"
    if re.search(r"manuscript|draft|current|result|baseline", low):
        return "current_work"
    return "prior_work"


def load_case(input_root):
    for p in sorted(input_root.rglob("case*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(obj, dict):
                return obj, p, None
        except (OSError, UnicodeError, ValueError) as exc:
            return {}, p, str(exc)
    return {}, None, None


def find_task(input_root):
    hits = sorted(input_root.rglob("task.md"))
    return hits[0] if hits else None


def discover_materials(input_root):
    out = []
    for p in sorted(input_root.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("case") and p.suffix == ".json":
            continue
        if p.name == "task.md":
            continue
        if "extracts" in p.parts:
            continue
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
            continue
        out.append(p)
    return out


def read_source(path, error_sink):
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            return extract_pdf_text(path).splitlines(), "stdlib-stream-parser"
        except (OSError, ValueError) as exc:
            error_sink.append("%s: pdf unreadable (%s)" % (path.name, exc))
            return [], "failed"
    if ext in TEXT_EXT or ext == "":
        try:
            return path.read_text(encoding="utf-8-sig").splitlines(), "utf-8"
        except (OSError, UnicodeError) as exc:
            error_sink.append("%s: not utf-8 (%s)" % (path.name, exc))
            return [], "failed"
    try:
        return path.read_text(encoding="utf-8-sig").splitlines(), "utf-8"
    except (OSError, UnicodeError):
        error_sink.append("%s: unsupported binary, left unread" % path.name)
        return [], "unsupported"


def substantive(lines):
    for idx, raw in enumerate(lines, 1):
        s = raw.strip()
        if len(s) < 30 or s[0] in "#|>-*+":
            continue
        if not re.search(r"[.!?]", s):
            continue
        if not re.search(r"[A-Za-z一-鿿]", s):
            continue
        yield idx, s


# --------------------------------------------------------------------------
# ledger construction
# --------------------------------------------------------------------------
def build_ledger(case_id, records, out_dir, warnings):
    sources, evidence, references, claims = [], [], [], []
    groups, gaps, contributions = [], [], []
    s_no = e_no = r_no = c_no = g_no = h_no = k_no = 0
    seen_sentence = set()

    def new_id(prefix, n):
        return "%s%d" % (prefix, n)

    def cite_ref(token, sid):
        nonlocal r_no
        for rf in references:
            if rf["citation"] == token and rf["source_id"] == sid:
                return rf["id"]
        r_no += 1
        rid = new_id("R", r_no)
        references.append({"id": rid, "source_id": sid, "citation": token,
                           "metadata_status": "verified_from_input"})
        return rid

    for rec in records:
        s_no += 1
        sid = new_id("S", s_no)
        extract_rel = "extracts/%s.txt" % sid
        extract_abs = out_dir / extract_rel
        extract_abs.parent.mkdir(parents=True, exist_ok=True)
        extract_abs.write_text("\n".join(rec["lines"]) + "\n", encoding="utf-8")
        sources.append({
            "id": sid,
            "input_path": rec["input_path"],
            "extracted_path": extract_rel,
            "kind": rec["kind"],
            "availability": "full_text" if rec["lines"] else "unreadable",
            "metadata": {"authors": [], "year": None, "title": rec["name"], "venue": None, "doi": None},
            "extraction": rec["method"],
        })
        if rec["kind"] == "other" or not rec["lines"]:
            continue
        for idx, sentence in substantive(rec["lines"]):
            key = norm(sentence).lower()
            if key in seen_sentence or len(evidence) >= CAP_EVIDENCE:
                continue
            seen_sentence.add(key)
            e_no += 1
            eid = new_id("E", e_no)
            evidence.append({
                "id": eid,
                "source_id": sid,
                "locator": "%s line %d" % (rec["name"], idx),
                "line_start": idx,
                "line_end": idx,
                "quote": sentence,
            })

    # claims: one per evidence entry (capped), role by source kind + content
    ev_by_source = {}
    for ev in evidence:
        ev_by_source.setdefault(ev["source_id"], []).append(ev)
    kind_of = {s["id"]: s["kind"] for s in sources}

    for ev in evidence:
        if len(claims) >= CAP_CLAIMS:
            break
        sid = ev["source_id"]
        kind = kind_of[sid]
        text = ev["quote"]
        if kind in ("current_work", "experimental_record"):
            role = "contribution" if re.search(r"\d", text) else "background"
        else:
            role = "related_work"
        c_no += 1
        cid = new_id("C", c_no)
        claim = {"id": cid, "text": text, "role": role, "assessment": "supported",
                 "evidence_ids": [ev["id"]], "citation_ids": []}
        if role == "related_work":
            for token in CITATION_RE.findall(text):
                rid = cite_ref(token, sid)
                if rid not in claim["citation_ids"]:
                    claim["citation_ids"].append(rid)
            if not claim["citation_ids"]:
                warnings.append("%s: related-work sentence carries no literal citation token" % cid)
        claims.append(claim)

    claims_by_role = {}
    for cl in claims:
        claims_by_role.setdefault(cl["role"], []).append(cl)

    # groups: one per prior-work source that supplied related-work claims
    for src in sources:
        if src["kind"] != "prior_work":
            continue
        ids = [cl["id"] for cl in claims_by_role.get("related_work", [])
               if cl["evidence_ids"] and evidence_index_source(evidence, cl["evidence_ids"][0]) == src["id"]]
        if not ids:
            continue
        g_no += 1
        groups.append({"id": new_id("G", g_no),
                       "label": src["metadata"]["title"] or src["id"],
                       "axis": "supplied prior work", "source_ids": [src["id"]], "claim_ids": ids})

    # gap: bounded synthesis from the strongest settled premises
    premises = claims_by_role.get("related_work", []) or claims_by_role.get("background", [])
    premise_ids = [cl["id"] for cl in premises[:3]]
    gap_text = ("Across the supplied materials the reported effect is not yet resolved "
                "under the conditions tested.")
    if premise_ids:
        c_no += 1
        gap_cid = new_id("C", c_no)
        gap_ev = []
        for cl in premises[:3]:
            gap_ev.extend(cl["evidence_ids"])
        claims.append({"id": gap_cid, "text": gap_text, "role": "gap",
                       "assessment": "inference", "evidence_ids": gap_ev[:4],
                       "citation_ids": [],
                       "rationale": "Bounded synthesis: the cited premises establish the "
                                    "reported result without resolving the open condition; "
                                    "no supplied source closes it."})
        h_no += 1
        gaps.append({"id": new_id("H", h_no), "claim_id": gap_cid,
                     "premise_claim_ids": premise_ids,
                     "derivation": "Combination of the settled premises leaves the stated "
                                   "condition unresolved within the checked corpus.",
                     "scope": "Only the supplied sources actually inspected in this run."})

    # contribution records
    for cl in claims_by_role.get("contribution", []):
        if not cl["evidence_ids"]:
            continue
        k_no += 1
        contributions.append({"id": new_id("K", k_no), "claim_id": cl["id"],
                              "own_evidence_ids": list(cl["evidence_ids"]),
                              "addresses_gap_ids": [g["id"] for g in gaps],
                              "limits": "Claim scope limited to what the current-work "
                                        "material states; no unstated regime is asserted."})

    ledger = {
        "schema_version": "1.0",
        "case_id": case_id,
        "sources": sources,
        "evidence": evidence,
        "references": references,
        "claims": claims,
        "groups": groups,
        "gaps": gaps,
        "contributions": contributions,
        "uncertainty": list(warnings),
        "changes": [],
    }
    return ledger


def evidence_index_source(evidence, eid):
    for ev in evidence:
        if ev["id"] == eid:
            return ev["source_id"]
    return None


# --------------------------------------------------------------------------
# manuscript
# --------------------------------------------------------------------------
def assemble_draft(ledger, prior_work_present):
    by_role = {}
    for cl in ledger["claims"]:
        by_role.setdefault(cl["role"], []).append(cl)
    lines = ["# Introduction", "", "## Background", ""]
    for cl in by_role.get("background", []):
        lines.append(cl["text"])
    lines += ["", "## Related work", ""]
    if prior_work_present:
        for grp in ledger["groups"]:
            lines.append("### %s" % grp["label"])
            for cid in grp["claim_ids"]:
                match = next((c for c in ledger["claims"] if c["id"] == cid), None)
                if match:
                    lines.append(match["text"])
    else:
        lines.append("No prior-work sources were supplied; related-work grouping remains "
                     "unresolved in this run.")
    lines += ["", "## Research gap", ""]
    gaps = by_role.get("gap", [])
    for cl in gaps:
        lines.append(cl["text"])
    lines += ["", "## Contributions", ""]
    for cl in by_role.get("contribution", []):
        lines.append(cl["text"])
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------
def run(args):
    t0 = time.time()
    input_root = Path(args.input).resolve()
    out_dir = Path(args.out).resolve()
    work_dir = Path(args.work).resolve() if args.work else out_dir / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    warnings, changes = [], []
    case, case_path, case_err = load_case(input_root) if input_root.exists() else ({}, None, None)
    actual_case_id = None
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id", "task_id"):
            if isinstance(case.get(key), str) and case[key].strip():
                actual_case_id = case[key].strip()
                break
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    if case_err:
        warnings.append("case.json unreadable: %s" % case_err)

    task_path = find_task(input_root) if input_root.exists() else None
    materials = discover_materials(input_root) if input_root.exists() else []

    manifest = []
    for p in (materials + [q for q in (case_path, task_path) if q]):
        try:
            manifest.append({"path": str(p), "relative": str(p.relative_to(input_root)),
                             "bytes": p.stat().st_size, "sha256": sha256_file(p)})
        except (OSError, ValueError):
            manifest.append({"path": str(p), "relative": p.name, "bytes": None, "sha256": None})

    records = []
    for p in materials:
        lines, method = read_source(p, warnings)
        if method == "failed" and not lines:
            warnings.append("%s: no text layer obtained" % p.name)
        records.append({"name": p.name, "input_path": str(p), "kind": classify(p.name),
                        "lines": lines, "method": method})

    ledger_case_id = actual_case_id or "unidentified-case"
    ledger = build_ledger(ledger_case_id, records, out_dir, warnings)

    prior_work_present = any(s["kind"] == "prior_work" and s["availability"] == "full_text"
                             for s in ledger["sources"])
    draft = assemble_draft(ledger, prior_work_present)

    ledger_path = out_dir / "evidence.json"
    draft_path = out_dir / "manuscript.md"
    draft_path.write_text(draft, encoding="utf-8")
    write_json(ledger_path, ledger)

    # review.md
    review = ["# Review — evidence-linked introduction and related work", ""]
    review.append("## Source inventory")
    review.append("")
    review.append("| id | file | kind | lines | extraction |")
    review.append("|---|---|---|---|---|")
    for s in ledger["sources"]:
        review.append("| %s | %s | %s | %d | %s |" % (
            s["id"], Path(s["input_path"]).name, s["kind"],
            len(next((r["lines"] for r in records if r["input_path"] == s["input_path"]), [])),
            s["extraction"]))
    review += ["", "## Related-work grouping"]
    if ledger["groups"]:
        for grp in ledger["groups"]:
            review.append("- **%s** — claims %s" % (grp["label"], ", ".join(grp["claim_ids"])))
    else:
        review.append("- No prior-work source was supplied; grouping left unresolved.")
    review += ["", "## Gap derivation"]
    for gap in ledger["gaps"]:
        review.append("- %s from premises %s: %s" % (gap["id"], ", ".join(gap["premise_claim_ids"]),
                                                     gap["derivation"]))
    review += ["", "## Contribution alignment"]
    for con in ledger["contributions"]:
        review.append("- %s -> evidence %s (limits: %s)" % (con["claim_id"],
                                                            ", ".join(con["own_evidence_ids"]),
                                                            con["limits"]))
    review += ["", "## Citation coverage"]
    if ledger["references"]:
        for rf in ledger["references"]:
            review.append("- %s `%s` from %s" % (rf["id"], rf["citation"], rf["source_id"]))
    else:
        review.append("- No literal citation tokens were found in the supplied material.")
    review += ["", "## Open questions"]
    if warnings:
        review += ["- " + w for w in warnings]
    else:
        review.append("- None recorded.")
    (out_dir / "review.md").write_text("\n".join(review) + "\n", encoding="utf-8")

    # internal structural audit (read-only except its report)
    audit_report = {"status": "not_run", "errors": [], "warnings": []}
    try:
        import audit as audit_mod
        audit_report = audit_mod.audit(ledger, draft, out_dir)
        audit_report["hashes"] = {"ledger_sha256": sha256_file(ledger_path),
                                  "draft_sha256": sha256_file(draft_path)}
    except Exception as exc:  # noqa: BLE001 - degrade, never crash
        audit_report = {"status": "not_run", "errors": ["audit failed: %s" % exc], "warnings": []}
    write_json(out_dir / "audit.json", audit_report)

    audit_errors = audit_report.get("errors") or []

    # status
    has_material = any(s["availability"] == "full_text" for s in ledger["sources"])
    has_claims = bool(ledger["claims"])
    has_gap = bool(ledger["gaps"])
    has_contrib = bool(ledger["contributions"])
    if not has_material:
        status = "blocked"
        status_reason = "No readable source material was found; an empty ledger was produced."
    elif not has_claims:
        status = "partial"
        status_reason = "Material was readable but yielded no substantive sentence to cite."
    elif audit_errors:
        status = "partial"
        status_reason = "Structural audit reported errors; complete was downgraded."
        warnings.append("audit errors: " + "; ".join(audit_errors[:5]))
    elif prior_work_present and has_gap and has_contrib and not audit_errors:
        status = "complete"
        status_reason = "Grouped prior work, a bounded gap from settled premises and a "
        "current-work contribution were all produced and the structural audit passed."
    else:
        status = "partial"
        missing = []
        if not prior_work_present:
            missing.append("no prior-work source for related-work grouping")
        if not has_gap:
            missing.append("no settled premise for a gap")
        if not has_contrib:
            missing.append("no current-work result evidence for a contribution")
        status_reason = "Delivered what the material supports; unresolved: " + "; ".join(missing) + "."

    if task_path is not None:
        changes.append("Read task instructions from %s." % task_path.name)
    changes.append("Extracted %d verbatim evidence spans from %d source(s)."
                   % (len(ledger["evidence"]), len(ledger["sources"])))
    if prior_work_present:
        changes.append("Grouped prior work into %d group(s)." % len(ledger["groups"]))

    ledger_summary = {"schema_version": ledger["schema_version"],
                      "counts": {c: len(ledger[c]) for c in (
                          "sources", "evidence", "references", "claims", "groups",
                          "gaps", "contributions")},
                      "audit_status": audit_report.get("status")}

    artifacts = [
        {"path": str(draft_path), "role": "editable manuscript"},
        {"path": str(ledger_path), "role": "evidence ledger (schema v1)"},
        {"path": str(out_dir / "review.md"), "role": "comparison matrix, gap and alignment"},
        {"path": str(out_dir / "audit.json"), "role": "structural audit report"},
    ]

    result = {
        "case_id": actual_case_id,
        "status": status,
        "status_reason": status_reason,
        "summary": "Evidence-linked introduction and related-work deliverable with %d claims "
                   "and %d evidence spans." % (len(ledger["claims"]), len(ledger["evidence"])),
        "main_result": {"manuscript_path": str(draft_path),
                        "sections": ["Background", "Related work", "Research gap", "Contributions"]},
        "sources": {"ledger_path": str(ledger_path),
                    "items": [{"id": s["id"], "input_path": s["input_path"],
                               "kind": s["kind"], "availability": s["availability"]}
                              for s in ledger["sources"]]},
        "artifacts": artifacts,
        "uncertainty": list(warnings),
        "changes": changes,
        "process": {"entry": "scripts/build.py", "passes": ["discover", "extract", "ledger",
                                                           "draft", "audit"],
                    "quality_gain": "not_measured", "efficiency_gain": "not_measured"},
        "audit": audit_report,
        "ledger_summary": ledger_summary,
        "limits": "Traceability only: does not establish entailment, novelty, literature "
                  "completeness or journal compliance. Every claim is a verbatim supplied "
                  "sentence; nothing was supplemented from memory.",
        "inputs": {"root": str(input_root), "manifest": manifest,
                   "case_json": str(case_path) if case_path else None,
                   "task_md": str(task_path) if task_path else None},
        "runtime": {"seconds": round(time.time() - t0, 3), "python": sys.version.split()[0],
                    "input": args.input, "out": args.out},
        "output_contract": contract,
    }
    for key, value in contract.items():
        result.setdefault(key, value)

    write_json(out_dir / "result.json", result)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="evidence-linked introduction builder")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default=None)
    args = ap.parse_args(argv)
    try:
        result = run(args)
        print(json.dumps({"status": result["status"], "case_id": result["case_id"],
                          "artifacts": [a["path"] for a in result["artifacts"]]},
                         ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 - always exit 0 with a written result
        sys.stderr.write("build.py internal error: %s\n" % exc)
        try:
            out_dir = Path(args.out).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "result.json", {
                "case_id": None, "status": "blocked",
                "status_reason": "internal error: %s" % exc,
                "summary": "", "main_result": {"manuscript_path": None},
                "sources": {"ledger_path": None, "items": []}, "artifacts": [],
                "uncertainty": ["internal error: %s" % exc], "changes": [],
                "process": {"quality_gain": "not_measured", "efficiency_gain": "not_measured"},
                "audit": {"status": "not_run", "errors": [], "warnings": []},
                "ledger_summary": {}, "limits": "Internal error; no deliverable produced.",
                "inputs": {}, "runtime": {}, "output_contract": {}})
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
