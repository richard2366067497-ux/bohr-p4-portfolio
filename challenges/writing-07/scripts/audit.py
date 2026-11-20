#!/usr/bin/env python3
"""Structural audit for the evidence ledger (standard library only).

    audit.py --ledger evidence.json --draft manuscript.md --report audit.json

Checks that the ledger is internally consistent: unique IDs, resolvable links,
verbatim quotes that really sit inside their declared 1-based line range, citation
tokens that occur in the claims and draft, gap premises that are settled, and
contributions whose own evidence comes from current work rather than prior papers.

Exit 0 = no structural errors (warnings allowed); 1 = errors; 2 = unusable input.
This is a traceability check, NOT a truth / entailment / novelty judgement.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

SOURCE_KINDS = {"prior_work", "current_work", "experimental_record", "other"}
ASSESSMENTS = {"supported", "inference", "needs_confirmation"}
ROLES = {"background", "related_work", "gap", "contribution", "other"}
COLLECTIONS = ("sources", "evidence", "references", "claims", "groups", "gaps", "contributions")


class LedgerShape(Exception):
    """Raised when the ledger is structurally unusable (not merely wrong)."""


def flat(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index(rows, name, errors):
    if not isinstance(rows, list):
        raise LedgerShape("%s must be an array" % name)
    table = {}
    for row in rows:
        if not isinstance(row, dict):
            raise LedgerShape("%s entries must be objects" % name)
        rid = row.get("id")
        if not isinstance(rid, str) or not rid:
            raise LedgerShape("%s entries need a non-empty string id" % name)
        if rid in table:
            errors.append("%s: duplicate id %s" % (name, rid))
        table[rid] = row
    return table


def _string(row, field, errors, required=True):
    val = row.get(field, "")
    if not isinstance(val, str):
        raise LedgerShape("%s.%s must be a string" % (row.get("id"), field))
    if required and not val.strip():
        errors.append("%s: empty %s" % (row.get("id"), field))
    return val


def audit(ledger, draft_text, base_dir):
    errors, warnings = [], []
    if not isinstance(ledger, dict):
        raise LedgerShape("ledger root must be an object")
    if ledger.get("schema_version") != "1.0":
        errors.append("schema_version must equal 1.0")
    if not isinstance(ledger.get("case_id"), str) or not ledger["case_id"].strip():
        errors.append("case_id must be a non-empty string")

    tab = {name: _index(ledger.get(name, []), name, errors) for name in COLLECTIONS}

    def refs(row, field, target, need=False):
        ids = row.get(field, [])
        if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
            raise LedgerShape("%s.%s must be an array of string ids" % (row.get("id"), field))
        if need and not ids:
            errors.append("%s: missing %s" % (row.get("id"), field))
        good = []
        for x in ids:
            if x in tab[target]:
                good.append(x)
            else:
                errors.append("%s: unknown %s id %s" % (row.get("id"), target, x))
        return good

    def one(row, field, target):
        val = row.get(field)
        if not isinstance(val, str) or val not in tab[target]:
            errors.append("%s: unknown %s %r" % (row.get("id"), field, val))
            return None
        return val

    # sources -> readable extracts
    extracts = {}
    for sid, src in tab["sources"].items():
        _string(src, "input_path", errors)
        if src.get("kind") not in SOURCE_KINDS:
            errors.append("%s: invalid source kind %r" % (sid, src.get("kind")))
        if src.get("availability") in ("missing", "unreadable", "metadata_only"):
            warnings.append("%s: limited access: %s" % (sid, src.get("availability")))
        ep = src.get("extracted_path")
        if isinstance(ep, str) and ep:
            p = Path(ep)
            if not p.is_absolute():
                p = base_dir / p
            try:
                extracts[sid] = p.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError) as exc:
                errors.append("%s: extract not readable: %s" % (sid, exc))
        else:
            warnings.append("%s: no inspectable extract" % sid)

    # evidence quotes inside their declared line window
    for eid, ev in tab["evidence"].items():
        sid = one(ev, "source_id", "sources")
        quote = _string(ev, "quote", errors)
        _string(ev, "locator", errors)
        start, end = ev.get("line_start"), ev.get("line_end")
        if not (isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int)
                and not isinstance(end, bool) and start >= 1 and end >= start):
            errors.append("%s: line_start/line_end must be inclusive 1-based integers" % eid)
            continue
        if sid not in extracts:
            errors.append("%s: source %s has no readable extract" % (eid, sid))
            continue
        lines = extracts[sid]
        if end > len(lines):
            errors.append("%s: line range beyond extract (%d lines)" % (eid, len(lines)))
        elif quote.strip() and flat(quote) not in flat("\n".join(lines[start - 1:end])):
            errors.append("%s: quote is absent from lines %d-%d" % (eid, start, end))
        if tab["sources"][sid].get("availability") in ("metadata_only", "missing", "unreadable"):
            errors.append("%s: limited source cannot substantiate content" % eid)

    draft = flat(draft_text)

    for rid, rf in tab["references"].items():
        one(rf, "source_id", "sources")
        token = _string(rf, "citation", errors)
        if token and flat(token) not in draft:
            warnings.append("%s: citation token not found in draft" % rid)
        if rf.get("metadata_status") != "verified_from_input":
            warnings.append("%s: metadata not verified against input" % rid)

    for cid, cl in tab["claims"].items():
        text = _string(cl, "text", errors)
        if cl.get("assessment") not in ASSESSMENTS:
            errors.append("%s: invalid assessment %r" % (cid, cl.get("assessment")))
        if cl.get("role") not in ROLES:
            errors.append("%s: invalid role %r" % (cid, cl.get("role")))
        ev_ids = refs(cl, "evidence_ids", "evidence",
                      need=cl.get("assessment") in ("supported", "inference"))
        cite_ids = refs(cl, "citation_ids", "references")
        if text and flat(text) not in draft:
            if cl.get("assessment") == "needs_confirmation":
                warnings.append("%s: unresolved claim omitted from draft" % cid)
            else:
                errors.append("%s: claim text absent from draft" % cid)
        if cl.get("assessment") == "inference":
            _string(cl, "rationale", errors)
        if cl.get("assessment") == "needs_confirmation":
            warnings.append("%s: needs a qualification / omission record" % cid)
        ev_sources = {tab["evidence"][e].get("source_id") for e in ev_ids if e in tab["evidence"]}
        for rid in cite_ids:
            rf = tab["references"].get(rid)
            if not rf:
                continue
            tok = _string(rf, "citation", errors, required=False)
            if tok and flat(tok) not in flat(text):
                errors.append("%s: linked citation %s not inside the claim" % (cid, rid))
            if rf.get("source_id") not in ev_sources:
                errors.append("%s: citation %s lacks matching content evidence" % (cid, rid))
        if cl.get("role") == "related_work" and not cite_ids:
            warnings.append("%s: related-work claim has no citation mapping" % cid)

    for gid, grp in tab["groups"].items():
        _string(grp, "label", errors)
        _string(grp, "axis", errors)
        refs(grp, "source_ids", "sources", need=True)
        refs(grp, "claim_ids", "claims", need=True)

    for hid, gap in tab["gaps"].items():
        cid = one(gap, "claim_id", "claims")
        premises = refs(gap, "premise_claim_ids", "claims", need=True)
        _string(gap, "derivation", errors)
        _string(gap, "scope", errors)
        if cid and tab["claims"][cid].get("role") != "gap":
            errors.append("%s: linked claim is not a gap" % hid)
        if cid and cid in premises:
            errors.append("%s: gap quotes itself as a premise" % hid)
        for pid in premises:
            if tab["claims"][pid].get("assessment") == "needs_confirmation":
                errors.append("%s: unsettled premise %s" % (hid, pid))

    for kid, con in tab["contributions"].items():
        cid = one(con, "claim_id", "claims")
        own = refs(con, "own_evidence_ids", "evidence", need=True)
        refs(con, "addresses_gap_ids", "gaps")
        _string(con, "limits", errors)
        if cid and tab["claims"][cid].get("role") != "contribution":
            errors.append("%s: linked claim is not a contribution" % kid)
        for eid in own:
            ev = tab["evidence"].get(eid, {})
            sid = ev.get("source_id")
            if sid in tab["sources"] and tab["sources"][sid].get("kind") not in (
                    "current_work", "experimental_record"):
                errors.append("%s: own evidence %s comes from prior/other work" % (kid, eid))
            if cid and eid not in tab["claims"][cid].get("evidence_ids", []):
                errors.append("%s: own evidence %s is not on its claim" % (kid, eid))

    for role, coll in (("gap", "gaps"), ("contribution", "contributions")):
        mapped = {row.get("claim_id") for row in tab[coll].values()}
        for cid, cl in tab["claims"].items():
            if cl.get("role") == role and cid not in mapped:
                errors.append("%s: missing %s derivation record" % (cid, role))

    if not tab["claims"]:
        warnings.append("no claims mapped; manuscript coverage not established")

    return {
        "status": "errors" if errors else "no_structural_errors",
        "errors": errors,
        "warnings": warnings,
        "counts": {name: len(rows) for name, rows in tab.items()},
        "limits": "Does not establish entailment, coverage, novelty, truth or journal compliance.",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.report.resolve() in (args.ledger.resolve(), args.draft.resolve()):
            raise LedgerShape("report path must not overwrite an input")
        ledger = json.loads(args.ledger.read_text(encoding="utf-8-sig"))
        draft = args.draft.read_text(encoding="utf-8-sig")
        report = audit(ledger, draft, args.ledger.resolve().parent)
        report["hashes"] = {"ledger_sha256": file_hash(args.ledger),
                            "draft_sha256": file_hash(args.draft)}
        code = 1 if report["errors"] else 0
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        report = {"status": "input_error", "errors": [str(exc)], "warnings": []}
        code = 2
    if args.report.resolve() not in (args.ledger.resolve(), args.draft.resolve()):
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
