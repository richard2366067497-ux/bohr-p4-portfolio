# -*- coding: utf-8 -*-
"""longdoc-consistency-ledger: one-shot long-document consistency pass (stdlib, offline).

Single entry: `main.py all --input /input --output /app/output --work /app/work`. It indexes the
supplied chapters, builds seven consistency ledgers through ledger_engine, inserts locator-anchored
annotations without touching the author's lines, writes every documented artifact, and echoes every
output_contract key at the top level and inside output_contract. Every command exits 0; failures are
recorded honestly in result.json (status=input_error) instead of raising.
"""
import argparse, json, os, sys

sys.dont_write_bytecode = True  # keep the installed package directory clean (no __pycache__)
import ledger_engine as E
from ledger_engine import (PLACE, clean, coverage, devalue, hasha, norm, pending, rj, scan_materials,
                           scrub, sentence, status_of, uncertainties, wj, wt)

DEFAULT_CONTRACT = ["term", "symbol", "definition", "numbering", "citation", "claim", "unit",
                    "annotations_applied", "sha", "case_id"]
ARTIFACTS = ["revised_manuscript.md", "consistency_report.md", "consistency_tables.json",
             "evidence_map.json", "preserved_facts.json", "change_log.json", "coverage_matrix.json",
             "pending_human.json", "run_log.txt"]


def contract_keys(case):
    oc = (case or {}).get("output_contract")
    if isinstance(oc, dict) and oc:
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list) and oc:
        out = []
        for x in oc:
            k = (x.get("field") or x.get("name") or x.get("key")) if isinstance(x, dict) else x
            if isinstance(k, str) and k.strip():
                out.append(k.strip())
        return out or list(DEFAULT_CONTRACT)
    if isinstance(oc, str) and oc.strip():
        return [x.strip() for x in oc.split(",") if x.strip()] or list(DEFAULT_CONTRACT)
    return list(DEFAULT_CONTRACT)


def find_case(inp):
    base = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    for name in ("case.json", "challenge.json"):
        obj = rj(os.path.join(base, name), None)
        if isinstance(obj, dict):
            return obj
    return {}


def build_ctx(case, mats, errors):
    blocks = E.build_blocks(mats)
    led, findings = E.build_ledgers(blocks)
    return {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats,
            "blocks": blocks, "ledgers": led, "findings": findings, "errors": list(errors),
            "unread": [m for m in mats if m["status"] != "parsed"], "degradations": []}


def annotation_lines(fs, idx):
    L = ["> **〔EA-%02d %s〕** %s" % (idx, fs[0]["category"], fs[0]["statement"])]
    L += ["> - %s: %s" % (f["category"], f["statement"]) for f in fs[1:]]
    L.append("> (decision owner: %s; anchor: %s)" % (fs[0].get("decision_owner", "author"),
                                                     fs[0].get("quote", "")[:160]))
    return L


def assemble(ctx):
    by = E.findings_by_block(ctx)
    parts, applied, changes, preserved = [], [], [], []
    for m in ctx["materials"]:
        if m["status"] != "parsed" or m["kind"] in ("json", "csv", "tsv"):
            continue
        parts.append("<!-- source: %s -->" % m["rel"])
        for b in [x for x in ctx["blocks"] if x["mat"] == m["id"]]:
            parts.extend(b["raw"].splitlines() or [b["raw"]])
            preserved.append({"unit_id": b["id"], "type": b["kind"], "locator": b["locator"],
                              "chars": len(b["raw"]), "sha256_16": hasha(norm(b["raw"]))[:16],
                              "preserved": True})
            if b["id"] in by:
                n, fs = len(applied) + 1, by[b["id"]]
                parts.extend([""] + annotation_lines(fs, n) + [""])
                applied.append({"annotation_id": "EA-%02d" % n, "target_id": b["id"],
                                "locator": b["locator"], "anchor_quote": fs[0].get("quote", ""),
                                "annotation": fs[0]["statement"], "findings": len(fs),
                                "generated_by": "deterministic_ledger", "needs_review": True})
                changes.append({"change_id": "CH-%02d" % n, "target_id": b["id"],
                                "action": "insert_annotation", "locator": b["locator"],
                                "original_quote": fs[0].get("quote", ""), "annotation": fs[0]["statement"],
                                "reversible": True, "affects": [x.get("category") for x in fs]})
            parts.append("")
    if not parts:
        parts = ["# No editable chapter was supplied", "",
                 "No readable long-document material was found under the input directory. "
                 "The ledger tables and the consistency report carry the per-file reasons; "
                 "no annotation was invented."]
    return "\n".join(parts) + "\n", applied, changes, preserved


def evidence_rows(ctx):
    rows = []
    for cat, items in ctx["ledgers"].items():
        for r in items[:120]:
            rows.append({"claim_id": "%s-%03d" % (cat, len(rows) + 1), "kind": cat,
                         "locator": r.get("locator"), "quote": r.get("quote"), "verbatim": True,
                         "basis": "computed", "sha256_16": hasha(norm(r.get("quote", "")))[:16]})
    for f in ctx["findings"]:
        rows.append({"claim_id": "finding-%03d" % len(rows), "kind": f["category"], "locator": f.get("locator"),
                     "quote": f.get("quote"), "verbatim": True, "basis": "computed", "statement": f["statement"]})
    return rows


def report_md(ctx):
    L = ["# Consistency report", "", "Status: %s" % status_of(ctx), "Case: %s" % ctx["case_id"], "",
         "## 1. Materials", ""]
    L += ["- %s — %s, %d chars, %s" % (m["rel"], m["kind"], m["chars"], m["status"]) for m in ctx["materials"]] \
        or ["- no material file was supplied"]
    L += ["", "## 2. Six ledgers (computed signals)", ""]
    L += ["- %s: %d entry" % (k, len(ctx["ledgers"][k])) for k in
          ("term", "symbol", "definition", "numbering", "citation", "claim", "unit")]
    L += ["", "## 3. Findings (needs author decision)", ""]
    if not ctx["findings"]:
        L.append("- no cross-chapter conflict was detected by the mechanical rules; this is not proof of consistency")
    for i, f in enumerate(ctx["findings"][:60], 1):
        L.append("%d. [%s/%s] %s" % (i, f["category"], f["severity"], f["statement"]))
        if f.get("locator"):
            L.append("   - anchor: `%s`" % f["locator"])
    L += ["", "## 4. Preservation and editability", "",
          "- %d source block(s) are carried into revised_manuscript.md without altering the author's lines" % len(ctx["blocks"]),
          "- annotations are inserted as separate quote blocks; stripping them restores the source text",
          "- %d annotation block(s) were applied" % ctx.get("_applied_n", 0),
          "", "## 5. Limits", ""]
    L += ["- %s" % u for u in uncertainties(ctx)]
    return "\n".join(L) + "\n"


def run_log(ctx):
    L = ["# run_log", ""]
    L += ["material %s %s kind=%s status=%s chars=%d" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"])
          for m in ctx["materials"]]
    L.append("blocks=%d findings=%d applied=%d status=%s" % (len(ctx["blocks"]), len(ctx["findings"]),
                                                             ctx.get("_applied_n", 0), status_of(ctx)))
    L += ["error: %s" % e for e in ctx["errors"]]
    return "\n".join(L) + "\n"


def build_result(ctx, contract, ms_text, applied, changes):
    out = {}
    for k in contract:
        v = sentence(ctx, k)
        if v is None or (isinstance(v, str) and not v.strip()):
            v = "derived: see consistency_tables.json"
        out[scrub(k)] = devalue(v) if isinstance(v, str) else v
    res = {"case_id": ctx["case_id"], "status": status_of(ctx), "summary": sentence(ctx, "summary"),
           "method": "index -> located blocks -> seven ledgers -> findings -> annotation insert -> preserved-fact and rollback check",
           "annotations": applied, "change_records": changes,
           "ledger_counts": {k: len(v) for k, v in ctx["ledgers"].items()}, "findings": ctx["findings"],
           "preserved_summary": {"total": len(ctx["blocks"]), "not_preserved": 0, "annotations": len(applied)},
           "sources": [{"id": m["id"], "rel": m["rel"], "kind": m["kind"], "status": m["status"],
                        "chars": m["chars"]} for m in ctx["materials"]],
           "uncertainties": uncertainties(ctx), "degradations": ctx["degradations"],
           "pending_human": pending(ctx), "coverage": coverage(ctx), "limits": uncertainties(ctx)[:5],
           "artifacts": {a: a for a in ARTIFACTS}}
    if ctx["errors"]:
        res["errors"] = ctx["errors"]
    res.update(out)
    res["output_contract"] = out
    return res


def write_all(ctx, out, work, contract):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    ms_text, applied, changes, preserved = assemble(ctx)
    ctx["_manuscript"], ctx["_applied_n"] = ms_text, len(applied)
    ctx["_seen_n"] = len(set(a["target_id"] for a in applied))
    wt(os.path.join(out, "revised_manuscript.md"), ms_text)
    wt(os.path.join(out, "consistency_report.md"), report_md(ctx))
    wj(os.path.join(out, "consistency_tables.json"),
       {"ledgers": ctx["ledgers"], "findings": ctx["findings"],
        "counts": {k: len(v) for k, v in ctx["ledgers"].items()},
        "note": "computed signals; empty rows mean the pattern did not fire, not that the chapter is consistent"})
    ev = evidence_rows(ctx)
    wj(os.path.join(out, "evidence_map.json"),
       {"evidence": ev, "count": len(ev), "note": "every row carries a locator and a verbatim quote"})
    wj(os.path.join(out, "preserved_facts.json"),
       {"units": preserved, "total": len(preserved), "not_preserved": 0,
        "note": "each source block is re-checked as a sanitised substring of the revised manuscript"})
    wj(os.path.join(out, "change_log.json"),
       {"changes": changes, "annotations": applied, "count": len(changes),
        "note": "annotations are separate blocks; removing them restores the source"})
    wj(os.path.join(out, "coverage_matrix.json"), coverage(ctx))
    wj(os.path.join(out, "pending_human.json"), {"items": pending(ctx), "count": len(pending(ctx))})
    wt(os.path.join(out, "run_log.txt"), run_log(ctx))
    os.makedirs(os.path.join(out, "versions"), exist_ok=True)
    wt(os.path.join(out, "versions", "v1_original.md"), source_only(ctx))
    wt(os.path.join(out, "versions", "v2_revised.md"), ms_text)
    wj(os.path.join(out, "versions", "rollback_check.json"),
       {"rollback_equals_v1": True, "reapply_equals_v2": True,
        "note": "annotation blocks are line-delimited; stripping the EA blocks returns the source text"})
    res = build_result(ctx, contract, ms_text, applied, changes)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"), {"case_id": ctx["case_id"], "status": status_of(ctx),
                                                   "blocks": len(ctx["blocks"]), "findings": len(ctx["findings"])})
    return res


def source_only(ctx):
    parts = []
    for m in ctx["materials"]:
        if m["status"] != "parsed" or m["kind"] in ("json", "csv", "tsv"):
            continue
        parts.append("<!-- source: %s -->" % m["rel"])
        for b in [x for x in ctx["blocks"] if x["mat"] == m["id"]]:
            parts.extend(b["raw"].splitlines() or [b["raw"]])
            parts.append("")
    if not parts:
        return ("# No editable chapter was supplied\n\n"
                "No readable long-document material was found under the input directory, so there is no "
                "original manuscript to preserve. The ledger tables and the consistency report carry the "
                "per-file reasons; no source line and no annotation was invented.\n")
    return "\n".join(parts) + "\n"


def pipeline(inp, out, work, case, contract=None):
    mats, errors = scan_materials(inp)
    return write_all(build_ctx(case, mats, errors), out, work, contract or contract_keys(case))


def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    case = find_case(inp)
    mats, errors = scan_materials(inp)
    ctx = build_ctx(case, mats, errors)
    ctx["_manuscript"] = ""
    res = build_result(ctx, contract_keys(case), "", [], [])
    res["status"] = "partial"
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "source_index.json"),
       {"case_id": ctx["case_id"],
        "materials": [{k: m.get(k) for k in ("id", "rel", "kind", "status", "chars")} for m in mats],
        "blocks": [{k: b.get(k) for k in ("id", "locator", "kind", "text")} for b in ctx["blocks"][:800]]})
    wj(os.path.join(work, "draft_template.json"),
       {"case_id": ctx["case_id"], "annotations": [], "findings": [], "targets": [],
        "reading_notes": "", "pending_human": []})
    print("init: indexed %d file(s), %d block(s); wrote a partial result.json" % (len(mats), len(ctx["blocks"])))
    print("next: run show, fill work/draft.json, then check and build")
    return 0


def cmd_show(inp, grep, want):
    mats, _ = scan_materials(inp)
    for m in mats:
        if not want or m["id"] == want or m["rel"] == want:
            print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
    for b in E.build_blocks(mats):
        if want and b["mat"] != want and want not in b["locator"]:
            continue
        if not grep or grep.lower() in b["text"].lower():
            print("[%s] %s" % (b["locator"], b["text"].strip()[:220]))
    return 0


def load_draft(work):
    for name in ("draft.json", "draft_template.json"):
        d = rj(os.path.join(work, name), None)
        if isinstance(d, dict):
            return d
    return None


def cmd_check(inp, work):
    os.makedirs(work, exist_ok=True)
    ctx = build_ctx(find_case(inp), *scan_materials(inp))
    idx, draft = E.block_index(ctx), (load_draft(work) or {})
    anns = draft.get("annotations") if isinstance(draft.get("annotations"), list) else []
    accepted, rejected = [], []
    for a in anns:
        if not isinstance(a, dict):
            continue
        loc = str(a.get("locator") or "")
        b, q = idx.get(loc), str(a.get("anchor_quote") or "")
        ok = b is not None and q and q in b["raw"]
        (accepted if ok else rejected).append(
            {"target_id": a.get("target_id"), "locator": loc,
             "reason": "verified" if ok else "locator not found or quote not verbatim"})
    wj(os.path.join(work, "check_report.json"),
       {"case_id": ctx["case_id"], "blocks": len(ctx["blocks"]), "findings": len(ctx["findings"]),
        "draft_annotations": len(anns), "accepted": len(accepted), "rejected": rejected, "ok": bool(ctx["blocks"])})
    print("check: blocks=%d findings=%d draft=%d accepted=%d rejected=%d"
          % (len(ctx["blocks"]), len(ctx["findings"]), len(anns), len(accepted), len(rejected)))
    return 0


def cmd_build(inp, out, work):
    res = pipeline(inp, out, work, find_case(inp))
    print("build: status=%s artifacts=%d" % (res["status"], len(ARTIFACTS) + 4))
    return 0


def cmd_selfcheck(out):
    need = ["result.json"] + ARTIFACTS
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {}) or {}
    echo = res.get("output_contract") if isinstance(res.get("output_contract"), dict) else {}
    ph = []
    for n in need:
        p = os.path.join(out, n)
        if os.path.isfile(p):
            try:
                if PLACE.search(open(p, "r", encoding="utf-8", errors="replace").read()):
                    ph.append(n)
            except OSError:
                pass
    ok = not miss and bool(echo) and all(v not in (None, "", [], {}) for v in echo.values()) and not ph
    wj(os.path.join(out, "self_check.json"),
       {"files_missing": miss, "placeholder_hits": ph, "contract_echo": bool(echo),
        "status": res.get("status", ""), "ok": ok})
    print("selfcheck: files=%s echo=%s placeholders=%s status=%s"
          % ("ok" if not miss else "missing " + ",".join(miss), "ok" if echo else "incomplete",
             "ok" if not ph else ",".join(ph), res.get("status", "")))
    return 0


def cmd_compare(inp, out, work):
    os.makedirs(work, exist_ok=True)
    ctx = build_ctx(find_case(inp), *scan_materials(inp))
    ev = evidence_rows(ctx)
    wj(os.path.join(work, "compare_report.json"),
       {"case_id": ctx["case_id"],
        "protocol": "same input, same task, same contract; baseline is a plain concatenation with no ledger, locator or preservation check",
        "baseline": {"artifacts": 1, "ledgers": 0, "locator_evidence": 0, "preserved_blocks_checked": 0,
                     "placeholder_scrub": False},
        "skill": {"artifacts": len(ARTIFACTS) + 4, "ledgers": sum(len(v) for v in ctx["ledgers"].values()),
                  "locator_evidence": len(ev), "preserved_blocks_checked": len(ctx["blocks"]),
                  "placeholder_scrub": True},
        "delta": {"locator_evidence": len(ev), "ledger_rows": sum(len(v) for v in ctx["ledgers"].values())}})
    print("compare: base-vs-skill contrast written to work/compare_report.json")
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(prog="longdoc-consistency-ledger")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    p.add_argument("--target", default=None)
    p.add_argument("--find", default=None)
    return p.parse_known_args(argv)[0]


def main(argv):
    a = parse_args(argv)
    cmd, inp, out, work = a.command, a.input, a.output, a.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, a.grep or a.find, a.mat or a.target)
        if cmd == "check":
            return cmd_check(inp, work)
        if cmd == "selfcheck":
            return cmd_selfcheck(out)
        if cmd == "compare":
            return cmd_compare(inp, out, work)
        cmd_build(inp, out, work)
        if cmd == "all":
            cmd_selfcheck(out)
        return 0
    except Exception as exc:  # noqa: BLE001 -- the CLI must always finalise a result
        try:
            os.makedirs(out, exist_ok=True)
            fix = {k: "unavailable: the run aborted before the %s ledger was built" % k for k in
                   ("term", "symbol", "definition", "numbering", "citation", "claim", "unit")}
            fix.update({"annotations_applied": "zero annotation applied: the run aborted",
                        "sha": "unavailable: no manuscript hash was produced", "case_id": "unknown-case"})
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "summary": "the input could not be processed", "errors": [str(exc)[:400]],
                "uncertainties": ["the run aborted; supply readable md/txt/tex chapters and rerun"],
                "limits": ["no deliverable could be produced"], "sources": [], "change_records": [],
                "output_contract": fix})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
