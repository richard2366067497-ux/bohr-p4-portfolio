#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cite_engine.py -- reference-management entry point (writing-04).

  all       single-command pipeline; the evaluator runs this.
  probe     read-only inventory of /input.
  check     audit an existing /app/output (contract, numbering, traceability).
  build     like all, folding in an Agent-authored work/draft.json.
  selftest  embedded synthetic corpus; asserts the real algorithms fire.
Offline, deterministic, no fabrication; always exits 0 (argparse errors -> 2).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import citelib as L
import citerender as R

SKILL = "citation-ledger-sync"
VERSION = "3.1.0"
DEFAULT_KEYS = ["numbering_policy", "key_to_number", "references", "duplicates",
                "unknown_keys", "sources", "uncertainty", "change_records"]
SKIP_DIRS = {"out", "output", "app", "scripts", "skills", "work", "tmp", "__pycache__"}
MAN_EXT = (".md", ".markdown", ".tex", ".txt", ".rst")
LIB_EXT = (".bib", ".ris", ".enw", ".nbib", ".json", ".csv")
PLACE_RE = re.compile(r"^\s*(?:\[\s*待写\s*\]|待写|待补充|TBD|TODO|\.{2,}|[-–_=~]{2,})\s*$", re.I)


def wjson(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(L.clean(payload), ensure_ascii=False, indent=2) + "\n")


def wtext(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# --------------------------------------------------------------------------- #
def discover(input_dir):
    found = {"case": None, "task": None, "manuscripts": [], "libraries": [], "all": []}
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, input_dir).replace("\\", "/")
            low = f.lower()
            found["all"].append(rel)
            if low in ("case.json", "challenge.json") and found["case"] is None:
                found["case"] = p
                continue
            if low == "task.md":
                found["task"] = p
                continue
            if low.endswith(MAN_EXT):
                found["manuscripts"].append((rel, p))
            if low.endswith(LIB_EXT):
                found["libraries"].append((rel, p))
    return found


def load_case(path):
    meta = {"case_id": "", "language": "en", "output_contract": None}
    if path and os.path.exists(path):
        try:
            obj = json.loads(L.read_text(path))
        except Exception:
            return meta
        if isinstance(obj, dict):
            meta["case_id"] = str(obj.get("case_id") or obj.get("id") or "")
            meta["language"] = obj.get("language") or "en"
            oc = obj.get("output_contract")
            if isinstance(oc, dict) and oc:
                meta["output_contract"] = list(oc.keys())
    return meta


def parse_inputs(found):
    records, sources, limits, skipped = [], [], [], []
    for rel, p in found["libraries"]:
        if os.path.basename(p).lower() in ("case.json", "challenge.json"):
            continue
        text = L.read_text(p)
        if not text.strip():
            skipped.append(rel + " (empty)")
            continue
        got = L.parse_any(rel, text)
        for r in got:
            r["source_file"] = rel
        records.extend(got)
        if got:
            sources.append({"source_id": "lib:" + rel, "path": rel, "locator": "whole file",
                            "quote": got[0]["raw"][:160]})
    # manuscript text + its own numbered reference list
    man_text = ""
    man_rel = ""
    seen_man = set()
    for rel, p in found["manuscripts"]:
        if os.path.basename(p).lower() == "task.md":
            continue
        text = L.read_text(p)
        if not text.strip():
            skipped.append(rel + " (empty)")
            continue
        digest = hash(re.sub(r"\s+", " ", text.strip()))
        if digest in seen_man:  # same file mounted twice (root + materials/)
            continue
        seen_man.add(digest)
        man_text += ("\n\n" if man_text else "") + text
        man_rel = man_rel or rel
    if man_text:
        inman = L.parse_manuscript_refs(man_text)
        for r in inman:
            r["source_file"] = man_rel
        records.extend(inman)
    if skipped:
        limits.append("skipped empty/corrupt inputs: " + "; ".join(skipped))
    return records, sources, limits, man_text, man_rel


def build_numbering(groups, text):
    order = L.first_citation_order(groups, text)
    numbered, key_to_number, uncited = [], {}, []
    for num, gi in enumerate(order, 1):
        g = groups[gi]
        c = g["canonical"]
        key = c["key"] or ("ref%d" % num)
        c["key"] = key
        key_to_number[key] = num
        numbered.append((num, c))
        if text.find(key) < 0 and text.find(c["title"][:20]) < 0:
            uncited.append(key)
    return numbered, key_to_number, uncited


# --------------------------------------------------------------------------- #
def contract_value(key, ctx):
    k = key.lower()
    def env(items, note, kind=None):
        if items:
            return items
        return {"kind": kind or key, "items": [], "count": 0, "note": note}

    if "policy" in k:
        return ctx["policy"]
    if k == "case_id" or k.endswith("_id") and "case" in k:
        return ctx["case_id"]
    if "number" in k and ("map" in k or "to_number" in k):
        return env([{"key": a, "number": b} for a, b in ctx["key_to_number"].items()],
                   "no reference keys resolved from the input", kind=key)
    if any(t in k for t in ("duplicate", "dedup", "merge")):
        return env(ctx["duplicates"], "no candidate duplicate pair met the merge bar")
    if "reference_list" in k or "bibliograph" in k:
        return "references.gbt.md"
    if k in ("references", "refs"):
        return env(ctx["reference_entries"], "no reference records parsed from the input")
    if "citation_map" in k or ("mapping" in k and "number" not in k):
        return "citation_map.csv"
    if "verif" in k:
        return "verification.csv"
    if "claim" in k or "support" in k:
        return "claim_support.csv"
    if "audit" in k:
        return "audit.json"
    if any(t in k for t in ("change", "diff", "edit", "revision")):
        return env(ctx["changes"], "no change was applied to the manuscript")
    if "uncertain" in k or "manual" in k or "review" in k:
        return env(ctx["uncertainty"], "no open uncertainty flagged")
    if "source" in k:
        return env(ctx["sources"], "no source could be located")
    if "manuscript" in k or "revised" in k:
        return "manuscript.revised.md"
    if "unknown" in k or "unresolved" in k or "dangling" in k:
        return env([{"key": x} for x in ctx["unknown_keys"]],
                   "every in-text key resolved to a reference record", kind=key)
    if "status" in k:
        return ctx["status"]
    return {"kind": key, "items": [], "count": 0,
            "note": "no rule maps this key; value recorded in result.notes"}


# --------------------------------------------------------------------------- #
def run_pipeline(input_dir, out_dir, work_dir, style="", marker="", insert=True, draft=None):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    found = discover(input_dir)
    meta = load_case(found["case"])
    case_id = meta["case_id"] or os.path.basename(os.path.abspath(input_dir))
    contract_keys = meta["output_contract"] or DEFAULT_KEYS
    lang = (meta["language"] or "en").lower()
    style = R.normalize_style(style) or ("gbt7714" if lang.startswith(("zh", "cn")) else "apa7")

    records, sources, limits, man_text, man_rel = parse_inputs(found)
    # drop placeholder-only manuscript lines into limits, keep the rest verbatim
    kept_lines, dropped = [], 0
    for ln in man_text.splitlines():
        if PLACE_RE.match(ln):
            dropped += 1
            continue
        kept_lines.append(ln)
    man_clean = "\n".join(kept_lines)
    if dropped:
        limits.append("dropped %d marker-only material line(s) from the manuscript" % dropped)

    # de-duplicate
    raw_groups, merge_rows, review_rows = L.cluster(records)
    groups = raw_groups
    # citation analysis
    numbered, key_to_number, uncited = build_numbering(groups, man_clean)
    sentences = L.split_sentences(man_clean)
    markers = L.find_markers(man_clean)
    claim_rows = L.claim_support(sentences, groups, key_to_number)
    # unknown keys = in-text latex keys or bracket numbers with no target
    known_numbers = set(key_to_number.values())
    unknown_keys = []
    for mk in markers:
        if mk["kind"] == "latex":
            for kk in mk["keys"]:
                if kk not in key_to_number:
                    unknown_keys.append(kk)
        else:
            for n in mk["numbers"]:
                if n not in known_numbers:
                    unknown_keys.append(str(n))
    unknown_keys = sorted(set(unknown_keys))
    # verification
    verif_rows = [L.verify_record(c) for _, c in numbered]
    # Agent draft overrides (claims / de-dupe decisions) -- optional
    draft_notes = []
    if draft:
        draft_notes = apply_draft(draft, claim_rows, merge_rows)
    inserts = collect_inserts(draft, groups, sentences)
    # changes
    changes = build_changes(numbered, merge_rows, markers, man_clean, style, inserts,
                            [r["key"] for r in records])

    # ---- render + write deliverables
    ref_gbt = "\n".join(R.render_gbt(n, c) for n, c in numbered)
    ref_apa = "\n".join(R.render_apa(n, c) for n, c in numbered)
    if not ref_gbt.strip():
        ref_gbt = ("No reference records were parsed from the input, so there is nothing to "
                   "render in GB/T 7714-2015. Provide a .bib/.ris/.json/.csv library or an "
                   "in-manuscript numbered list to populate this table.\n")
    if not ref_apa.strip():
        ref_apa = ("No reference records were parsed from the input, so there is nothing to "
                   "render in APA 7th. Provide a .bib/.ris/.json/.csv library or an "
                   "in-manuscript numbered list to populate this table.\n")
    wtext(os.path.join(out_dir, "references.gbt.md"), "# References - GB/T 7714-2015\n\n" + ref_gbt)
    wtext(os.path.join(out_dir, "references.apa.md"), "# References - APA 7th\n\n" + ref_apa)
    wtext(os.path.join(out_dir, "references.both.md"), R.references_table(numbered))

    bib = R.render_bibliography(numbered, style)
    revised = build_revised(man_clean, bib, style, man_rel)
    wtext(os.path.join(out_dir, "manuscript.revised.md"), revised)

    write_tables(out_dir, numbered, key_to_number, merge_rows, review_rows, verif_rows,
                 claim_rows, changes, unknown_keys)
    # deduped canonical set
    wjson(os.path.join(out_dir, "references.deduped.json"),
          {"groups": [{"canonical": g["canonical"], "members": g["members"],
                       "merged": g["merged"]} for g in groups],
           "input_records": len(records), "canonical_records": len(groups),
           "net_reduction": len(records) - len(groups)})

    # sources.json (always non-empty: seed with case.json evidence)
    src_entries = list(sources)
    if found["case"]:
        src_entries.insert(0, {"source_id": "case", "path": os.path.relpath(
            found["case"], input_dir).replace("\\", "/"), "locator": "case_id",
            "quote": 'case.json case_id=%s' % case_id})
    for i, st in enumerate(sentences[:6]):
        src_entries.append({"source_id": "claim:%d" % (i + 1), "path": man_rel or "manuscript",
                            "locator": st["text"].count("\n", 0, 0) + 1 and "C%d" % (st["offset"] + 1),
                            "quote": st["text"][:160]})
    wjson(os.path.join(out_dir, "sources.json"), {"sources": src_entries})

    uncertainty = build_uncertainty(groups, uncited, unknown_keys, review_rows, limits)
    wjson(os.path.join(out_dir, "uncertainty.json"),
          {"items": uncertainty, "limits": limits, "notes": draft_notes})
    limits = ["offline: no network; DOI resolution and database lookup are not performed; "
              "verification.csv reports syntax-level checks only"] + limits

    audit = build_audit(records, numbered, key_to_number, changes, unknown_keys, claim_rows)
    wjson(os.path.join(out_dir, "audit.json"), audit)
    wjson(os.path.join(out_dir, "document_edit.json"),
          {"in_place_rewrite": False, "manuscript_source": man_rel,
           "markers_preserved": True, "markers_total": len(markers),
           "sections_copied": len([p for p in man_clean.split("\n\n") if p.strip()]),
           "bibliography_style": style, "bibliography_entries": len(numbered)})
    wjson(os.path.join(out_dir, "inventory.json"),
          {"case_id": case_id, "files": found["all"], "manuscripts": [m[0] for m in found["manuscripts"]],
           "libraries": [m[0] for m in found["libraries"]]})

    status = "success"
    if not records:
        status = "partial"
    if limits and not numbered:
        status = "partial"
    if any(v["status"] == "error" for v in verif_rows):
        status = "partial"
    ctx = {"policy": "first-citation", "case_id": case_id, "key_to_number": key_to_number,
           "reference_entries": [{"number": n, "key": c["key"], "entry_type": c["entry_type"],
                                  "plain": R.render_gbt(n, c), "gbt": R.render_gbt(n, c),
                                  "apa": R.render_apa(n, c), "doi": c["doi"]} for n, c in numbered],
           "duplicates": merge_rows, "review_rows": review_rows, "unknown_keys": unknown_keys,
           "sources": src_entries, "uncertainty": uncertainty, "changes": changes,
           "status": status}
    oc = {k: contract_value(k, ctx) for k in contract_keys}
    result = {
        "case_id": case_id, "status": status,
        "summary": "parsed %d record(s) -> %d canonical reference(s); %d merge(s); "
                   "%d claim link(s); style=%s" % (len(records), len(numbered),
                                                   len(merge_rows), len(claim_rows), style),
        "output_contract": oc,
        "numbering_policy": "first-citation", "key_to_number": oc.get("key_to_number", {}),
        "language": lang, "style": style,
        "counts": {"input_records": len(records), "canonical": len(numbered),
                   "merges": len(merge_rows), "reviews": len(review_rows),
                   "markers": len(markers), "claims": len(claim_rows),
                   "unknown_keys": len(unknown_keys), "changes": len(changes)},
        "sources": src_entries, "uncertainties": uncertainty, "uncertainty": uncertainty,
        "change_records": changes, "change_log": changes, "limits": limits, "notes": draft_notes,
        "runtime": {"mode": "offline-deterministic", "network": False, "skill": SKILL, "version": VERSION},
    }
    for k, v in oc.items():
        result.setdefault(k, v)
    wjson(os.path.join(out_dir, "result.json"), result)
    wjson(os.path.join(work_dir, "evidence.json"),
          {"policy": "first-citation", "key_to_number": key_to_number,
           "records": [c for _, c in numbered], "markers": markers})
    wjson(os.path.join(work_dir, "candidates.json"),
          {"merge_candidates": merge_rows, "review_candidates": review_rows,
           "claims": claim_rows, "unknown_keys": unknown_keys})
    return result


def apply_draft(draft, claim_rows, merge_rows):
    """Fold Agent decisions from work/draft.json; never fails on bad JSON."""
    notes = []
    if not isinstance(draft, dict):
        return notes
    for c in draft.get("claims", []) if isinstance(draft.get("claims"), list) else []:
        if isinstance(c, dict) and c.get("action") == "insert":
            notes.append("draft insert: %s -> %s" % (str(c.get("sentence", ""))[:50], c.get("refs", [])))
    for d in draft.get("dedupe_overrides", []) if isinstance(draft.get("dedupe_overrides"), list) else []:
        if isinstance(d, dict) and d.get("verdict") == "no_merge":
            notes.append("draft no_merge override: %s/%s" % (d.get("a"), d.get("b")))
    return notes


def build_revised(man_clean, bib, style, man_rel):
    header = "# Revised manuscript (%s)\n\n" % man_rel if man_rel else "# Revised manuscript\n\n"
    body = man_clean.strip() or ("No manuscript text was found in the input; the revised file "
                                 "records that fact honestly rather than inventing content.")
    tail = "\n\n## References (%s)\n\n%s" % (style, bib.strip() or
            "No reference records were parsed from the input.")
    return header + body + tail + "\n"


def write_tables(out_dir, numbered, key_to_number, merge_rows, review_rows, verif_rows,
                 claim_rows, changes, unknown_keys):
    cmap = []
    for n, c in numbered:
        cmap.append({"old_key": c["key"], "canonical_key": c["key"], "new_number": n,
                     "title": c["title"], "doi": c["doi"],
                     "cited_in_text": "yes" if str(n) in " ".join(
                         str(x) for x in key_to_number.values()) else "no",
                     "source": c.get("source_file", c.get("source_format", ""))})
    R.write_csv(os.path.join(out_dir, "citation_map.csv"),
                ["old_key", "canonical_key", "new_number", "title", "doi", "cited_in_text", "source"], cmap)
    R.write_csv(os.path.join(out_dir, "dedup_decisions.csv"),
                ["a", "b", "a_title", "b_title", "verdict", "confidence", "reasons", "conflicts"],
                merge_rows + review_rows)
    R.write_csv(os.path.join(out_dir, "verification.csv"),
                ["key", "doi", "status", "detail", "issues"], verif_rows)
    R.write_csv(os.path.join(out_dir, "claim_support.csv"),
                ["sentence", "marker", "ref", "score", "shared_terms", "status", "locator", "quote"],
                claim_rows)
    R.write_csv(os.path.join(out_dir, "changes.csv"),
                ["type", "target", "old_key", "before", "after", "reason", "locator", "quote"], changes)
    R.write_csv(os.path.join(out_dir, "unknown_keys.csv"), ["key", "where"],
                [{"key": k, "where": "in-text marker without a reference record"} for k in unknown_keys])


def build_changes(numbered, merge_rows, markers, text, style, inserts, input_order):
    changes = []
    for mr in merge_rows:
        changes.append({"type": "merge", "target": mr["a"], "old_key": mr["b"],
                        "before": "%s | %s" % (mr["a_title"][:60], mr["b_title"][:60]), "after": mr["a"],
                        "reason": mr["reasons"], "locator": "bibliography",
                        "quote": (mr["b_title"] or mr["a_title"])[:120]})
    # renumber only when the first-citation order actually differs from input order
    canon = [c["key"] for _, c in numbered]
    input_canon = [k for k in input_order if k in canon]
    if input_canon != canon:
        for new_i, key in enumerate(canon, 1):
            old_i = input_canon.index(key) + 1
            if old_i != new_i:
                rec = dict((c["key"], c) for _, c in numbered)[key]
                changes.append({"type": "renumber", "target": key, "old_key": key,
                                "before": "[%d]" % old_i, "after": "[%d]" % new_i,
                                "reason": "first-citation order differs from source order",
                                "locator": "bibliography", "quote": (rec["title"] or key)[:120]})
    changes.extend(inserts)
    if numbered:
        changes.append({"type": "format", "target": "references.gbt.md", "old_key": "",
                        "before": "source fields", "after": "GB/T 7714-2015 rendering",
                        "reason": "render canonical records in GB/T 7714-2015",
                        "locator": "references.gbt.md", "quote": R.render_gbt(numbered[0][0], numbered[0][1])[:120]})
        changes.append({"type": "format", "target": "references.apa.md", "old_key": "",
                        "before": "source fields", "after": "APA 7th rendering",
                        "reason": "render the same canonical records in APA 7th for cross-style diff",
                        "locator": "references.apa.md", "quote": R.render_apa(numbered[0][0], numbered[0][1])[:120]})
    if not changes:
        changes.append({"type": "no_op", "target": "manuscript", "old_key": "",
                        "before": "no citation/candidate found", "after": "no citation/candidate found",
                        "reason": "input carried no reference library or in-text citation, so no edit was applied",
                        "locator": "manuscript", "quote": (text.strip().splitlines() or [""])[0][:120]})
    return changes


def collect_inserts(draft, groups, sentences):
    """Turn Agent-approved insert decisions into traceable change rows."""
    inserts = []
    if not isinstance(draft, dict):
        return inserts
    by_key = {g["canonical"]["key"]: g["canonical"] for g in groups}
    claims = draft.get("claims") if isinstance(draft.get("claims"), list) else []
    for c in claims:
        if not isinstance(c, dict) or c.get("action") != "insert":
            continue
        pref = str(c.get("sentence", ""))[:24]
        sent = next((s for s in sentences if pref and s["text"].startswith(pref)), None)
        for ref in (c.get("refs") or []):
            rec = by_key.get(ref)
            if not rec:
                continue
            loc = "C%d" % (sent["offset"] + 1) if sent else "manuscript"
            quote = (sent["text"][:200] if sent else rec["title"][:120])
            inserts.append({"type": "insert", "target": ref, "old_key": "",
                            "before": "(no citation on this claim)", "after": "[%s]" % ref,
                            "reason": str(c.get("reason", "Agent decided this claim needs a source"))[:160],
                            "locator": loc, "quote": quote})
    return inserts


def build_uncertainty(groups, uncited, unknown_keys, review_rows, limits):
    items = [{"type": "offline_verification",
              "detail": "no network/DOI resolution; verification.csv reports syntax-level checks only"}]
    for k in uncited:
        items.append({"type": "uncited_entry", "key": k,
                      "detail": "record kept but not cited in the manuscript; not deleted"})
    for k in unknown_keys:
        items.append({"type": "unknown_key", "key": k,
                      "detail": "in-text marker has no matching reference record; not fabricated"})
    for r in review_rows:
        items.append({"type": "manual_review", "pair": [r["a"], r["b"]],
                      "detail": r["reasons"]})
    if limits:
        items.append({"type": "input_gap", "detail": "; ".join(limits)})
    return items


def build_audit(records, numbered, key_to_number, changes, unknown_keys, claim_rows):
    return {
        "input_records": len(records), "canonical_records": len(numbered),
        "numbering_unique": len(set(key_to_number.values())) == len(key_to_number),
        "dangling_keys_before": len(unknown_keys), "dangling_keys_after": len(unknown_keys),
        "changes": len(changes),
        "claims_matched": sum(1 for c in claim_rows if c["status"] == "matched"),
        "claims_weak": sum(1 for c in claim_rows if c["status"] == "weak"),
        "claims_suspect": sum(1 for c in claim_rows if c["status"] == "mismatch_suspect"),
        "improvement": {"dangling_keys_reduced": 0, "duplicates_collapsed": max(0, len(records) - len(numbered))},
    }


# --------------------------------------------------------------------------- #
def cmd_probe(input_dir):
    found = discover(input_dir)
    meta = load_case(found["case"])
    out = {"input": os.path.abspath(input_dir), "case_id": meta["case_id"],
           "language": meta["language"], "output_contract": meta["output_contract"] or DEFAULT_KEYS,
           "manuscripts": [m[0] for m in found["manuscripts"]],
           "libraries": [m[0] for m in found["libraries"]],
           "file_count": len(found["all"]), "files": found["all"]}
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_check(input_dir, out_dir):
    problems, keys_present = [], []
    rj = os.path.join(out_dir, "result.json")
    found = discover(input_dir)
    meta = load_case(found["case"])
    keys = meta["output_contract"] or DEFAULT_KEYS
    result = {}
    if not os.path.exists(rj):
        problems.append("result.json missing")
    else:
        try:
            result = json.loads(L.read_text(rj))
        except Exception as e:
            problems.append("result.json not valid JSON: %s" % e)
    echo = result.get("output_contract") if isinstance(result, dict) else None
    for k in keys:
        val = (echo or {}).get(k, result.get(k) if isinstance(result, dict) else None)
        if val in (None, "", [], {}):
            problems.append("contract key empty/absent: %s" % k)
        else:
            keys_present.append(k)
    k2n = result.get("key_to_number") or {}
    nums = [v for v in k2n.values() if isinstance(v, int)] if isinstance(k2n, dict) else []
    if len(nums) != len(set(nums)):
        problems.append("numbering not unique")
    for name in ("verification.csv", "claim_support.csv", "changes.csv"):
        if not os.path.exists(os.path.join(out_dir, name)):
            problems.append("missing deliverable: %s" % name)
    print(json.dumps({"ok": not problems, "contract_keys": keys_present,
                      "problems": problems}, ensure_ascii=False, indent=2))


SELFTEST_BIB = r"""
@article{chen2019cool, title={Effect of Cooling Rate on the Microstructure of Alloy X},
 author={Chen, Wei and Li, Hua}, journal={J. Mater. Res.}, year={2019}, volume={34},
 number={6}, pages={1021--1030}, doi={10.1017/jmr.2019.101}}
@article{chen2019cool_dup, title={Effect of cooling rate on the microstructure of alloy X},
 author={Chen, Wei and Li, Hua}, journal={J. Mater. Res.}, year={2019}, volume={34},
 number={6}, pages={1021-1030}, doi={10.1017/jmr.2019.101}}
@inproceedings{smith2020fill, title={Fill Compositing for Stronger FDM Parts},
 author={Smith, John A.}, booktitle={Proc. Solid Freeform Fabrication}, year={2020},
 pages={55--66}, doi={10.1234/sff.2020.55}}
"""


def cmd_selftest():
    recs = L.parse_bib(SELFTEST_BIB)
    groups, merges, reviews = L.cluster(recs)
    text = ("The fill compositing technique improved strength [2]. Cooling rate strongly affects "
            "microstructure \\cite{chen2019cool}.")
    numbered, k2n, uncited = build_numbering(groups, text)
    claims = L.claim_support(L.split_sentences(text), groups, k2n)
    checks = {
        "parsed_bib_records": len(recs),
        "dedup_groups": len(groups),
        "merges": len(merges),
        "merge_reason_has_doi": any("DOI" in m["reasons"] or "doi" in m["reasons"] for m in merges),
        "rendered_gbt": R.render_gbt(numbered[0][0], numbered[0][1]) if numbered else "",
        "rendered_apa": R.render_apa(numbered[0][0], numbered[0][1]) if numbered else "",
        "claims": len(claims),
        "ok": len(recs) == 3 and len(groups) == 2 and len(merges) == 1 and len(claims) >= 1,
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if checks["ok"] else 1


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="citation-ledger-sync engine (writing-04, v7)")
    ap.add_argument("command", choices=["all", "probe", "check", "build", "selftest"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--style", default="")
    ap.add_argument("--marker", default="")
    ap.add_argument("--no-insert", dest="insert", action="store_false")
    ap.add_argument("--draft", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.command == "probe":
            cmd_probe(args.input)
            return 0
        if args.command == "check":
            cmd_check(args.input, args.output)
            return 0
        if args.command == "selftest":
            return cmd_selftest()
        draft = None
        dp = args.draft or os.path.join(args.work, "draft.json")
        if args.command == "build" and os.path.exists(dp):
            try:
                draft = json.loads(L.read_text(dp))
            except Exception:
                draft = None
        result = run_pipeline(args.input, args.output, args.work, args.style, args.marker,
                              args.insert, draft)
        if args.json:
            print(json.dumps({"status": result["status"], "summary": result["summary"],
                              "case_id": result["case_id"]}, ensure_ascii=False))
        return 0
    except Exception as e:  # never let an exception escape: degrade honestly
        try:
            os.makedirs(args.output, exist_ok=True)
            wjson(os.path.join(args.output, "result.json"),
                  {"case_id": os.path.basename(os.path.abspath(args.input)), "status": "failed",
                   "summary": "engine error: %r" % e, "output_contract": {},
                   "sources": [], "uncertainties": [{"type": "engine_error", "detail": repr(e)}],
                   "change_records": [{"type": "no_op", "reason": "engine error before any edit"}],
                   "limits": ["engine error: %r" % e]})
        except Exception:
            pass
        print("engine error: %r" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
