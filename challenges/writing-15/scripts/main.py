#!/usr/bin/env python3
"""writing-15 | longdoc-source-ledger CLI: init | show | check | build | selfcheck.

Read the material and author work/draft.json before build; build still finalises with
labelled deterministic fallbacks when no draft exists. Exit code is always 0 - the real
outcome lives in result.json (status / errors / degradations).
"""
import argparse
import json
import os
import platform
import re
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger as L
import audit as A
import emit as E
import render as R
from audit import contract_keys, echo_contract

NAME, VERSION, T0 = "longdoc-source-ledger", "1.0.0", time.time()
ID_PAT = re.compile(r"\b([A-Za-z]{1,6}\d{0,3}[-_][A-Za-z]{0,3}\d{1,5})\b")

def log(*a):
    print(*a, flush=True)

def dump(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def lj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig")), None
    except Exception as exc:
        return None, "%s: %r" % (Path(p).name, exc)

def rt():
    return {"skill": NAME, "version": VERSION, "python": platform.python_version(),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(time.time() - T0, 2),
            "budget": "64 model requests / 900 s / 16384 tokens per case",
            "network": "unused"}

def paths(a):
    inp = Path(a.input or os.environ.get("INPUT_DIR") or "/input")
    if not inp.is_dir():
        for alt in (Path.cwd() / "input", HERE.parent / "input", Path("/app/input")):
            if alt.is_dir():
                inp = alt
                break
    out = Path(a.out or os.environ.get("OUT_DIR") or "/app/output")
    if not (a.out or os.environ.get("OUT_DIR")) and not Path("/app").is_dir():
        out = Path.cwd() / "output"
    work = Path(a.work or os.environ.get("WORK_DIR") or (out.parent / "work"))
    for d in (out, work, out / "versions", out / "revised_chapters"):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return {"input": inp, "out": out, "work": work}

from ledger import find_case, find_wo, wo_items, implicit_targets

def envelope(cid, contract, payload, status):
    payload = dict(payload)
    payload["case_id"] = cid
    payload["status"] = status
    res = echo_contract(contract, payload)
    for k, v in payload.items():
        res.setdefault(k, v)
    res["case_id"] = cid
    res["status"] = status
    res["contract_fields"] = contract_keys(contract)
    return res

def write_partial(out, cid, contract, note="", errors=None):
    payload = {"deliverable": None, "preserved_facts": [], "evidence_map": [], "change_log": [],
               "annotations": [], "workorder_execution": None, "consistency": None,
               "coverage": None, "sources": [], "uncertainty": [], "pending_human": [],
               "errors": [e for e in (errors or []) if e], "degradations": [note] if note else [],
               "changes": [], "runtime": rt()}
    res = envelope(cid, contract, payload, "partial")
    dump(Path(out) / "result.json", res)
    return res

def cmd_init(a, P):
    inp, out, work = P["input"], P["out"], P["work"]
    write_partial(out, "", {}, "init started; contract not read yet")
    case, cpath, errs = find_case(inp)
    cid = str((case or {}).get("case_id") or (case or {}).get("id") or "")
    contract = (case or {}).get("output_contract")
    ckeys = contract_keys(contract)
    write_partial(out, cid, contract, "init: contract read, material index not built yet", errs)
    ix = L.build_index(inp, errs)
    task_text = ""
    if (inp / "task.md").is_file():
        task_text, _ = L.read_text(inp / "task.md")
    instruction = str((case or {}).get("task_instruction") or (case or {}).get("instruction") or "")
    wo = find_wo(case, inp)
    index_ids = {b["id"] for b in ix["blocks"] if b["id"]}
    targets = wo_items(wo)
    if not targets:
        targets = implicit_targets(instruction + "\n" + task_text, index_ids)
        if targets:
            ix["notes"].append("no workorder; targets inferred from ids named in the instruction")
    ix.update({"case_id": cid, "case_path": str(cpath) if cpath else "",
               "contract": contract if isinstance(contract, (dict, list, str)) else {},
               "workorder": wo, "workorder_items": targets, "instruction": instruction,
               "task_md": task_text[:20000],
               "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    dump(work / "source_index.json", ix)
    dump(work / "paths.json", {k: str(v) for k, v in P.items()})
    tpl = {"case_id": cid, "reading_notes": "", "annotations": [], "findings": [],
           "plan": {"chapters": []}, "pending_human": []}
    for t in targets:
        res = L.resolve_target(ix, t["target_id"])
        b = res["block"]
        if b is None:
            tpl["annotations"].append({"target_id": t["target_id"], "locator": None, "anchor_quote": None,
                                       "annotation": None, "evidence": [], "rationale": None,
                                       "uncertainty": "target not locatable: " + res["note"]})
            continue
        tpl["annotations"].append({
            "target_id": t["target_id"], "locator": b["loc"],
            "anchor_quote": b["body"][:max(20, min(120, len(b["body"])))], "annotation": None,
            "evidence": [{"locator": b["loc"], "quote": L.norm(b["body"])[:160]}],
            "rationale": None, "uncertainty": "",
            "_context": {"resolution": res["resolution"], "note": res["note"],
                         "block_preview": b["body"][:400]}})
    dump(work / "draft_template.json", tpl)
    sources = [{"rel": m["rel"], "kind": m["kind"], "status": m["status"], "chars": m["chars"],
                "sha256_16": m["sha"], "note": m["note"]} for m in ix["materials"]]
    pend = [{"item": t["target_id"], "reason": "target id not found in the materials",
             "action": "supply the chapter file or confirm the id", "severity": "high"}
            for t in targets if L.resolve_target(ix, t["target_id"])["block"] is None]
    payload = {"deliverable": {"manuscript": None,
                               "status_note": "index built; run show, write the draft, then build"},
               "preserved_facts": [], "evidence_map": [], "change_log": [], "annotations": [],
               "workorder_execution": {"workorder_id": str((wo or {}).get("id") or ""),
                                       "targets": [{"target_id": t["target_id"], "status": "pending"} for t in targets],
                                       "requirements_met": False},
               "consistency": None, "coverage": None, "sources": sources,
               "uncertainty": list(ix["notes"]), "pending_human": pend, "errors": errs,
               "degradations": list(ix["notes"]), "changes": [], "runtime": rt()}
    status = "partial" if (targets or ix["blocks"]) else "insufficient_evidence"
    dump(out / "result.json", envelope(cid, contract, payload, status))
    st = ix["stats"]
    log("== longdoc-source-ledger %s | init ==" % VERSION)
    log("input %s | case %s (%s) | contract %d keys: %s"
        % (inp, cid or "<none>", cpath.name if cpath else "-", len(ckeys), ", ".join(ckeys) or "<none>"))
    log("materials %d | blocks %d | sections %d | chars %d | ids %d"
        % (st["materials"], st["blocks"], st["sections"], st["chars"], st["with_id"]))
    for m in ix["materials"]:
        log("  [%s] %s  %d chars  %s%s" % (m["status"], m["rel"], m["chars"], m["kind"],
                                          (" | " + m["note"]) if m["note"] else ""))
    log("workorder %s | targets %d" % (str((wo or {}).get("id") or "<none>"), len(targets)))
    for t in targets:
        res = L.resolve_target(ix, t["target_id"])
        b = res["block"]
        log("  * %s -> %s [%s]%s" % (t["target_id"], b["loc"] if b else "NOT FOUND", res["resolution"],
                                     (" " + t["requirement"][:90]) if t["requirement"] else ""))
        if b:
            log("    | %s" % b["body"][:220].replace("\n", " "))
    log("next: show --target <id>; write %s/draft.json (skeleton: draft_template.json); check; build" % work)
    log("NOTE: the script does not read for you; build alone yields a labelled fallback.")

def cmd_show(a, P):
    ix, err = lj(P["work"] / "source_index.json")
    if not isinstance(ix, dict) or not ix.get("blocks"):
        log("no usable index (%s); run: python3 scripts/main.py init" % (err or "empty"))
        return
    if a.contract:
        log(json.dumps(ix.get("contract"), ensure_ascii=False, indent=2)[:4000])
        log("contract keys: %s" % ", ".join(contract_keys(ix.get("contract"))))
        return
    if a.workorder:
        log(json.dumps(ix.get("workorder"), ensure_ascii=False, indent=2)[:6000])
        for t in ix.get("workorder_items") or []:
            log("  * %s | %s" % (t["target_id"], t.get("requirement", "")[:160]))
        return
    if a.find:
        fq = L.find_quote(ix, a.find)
        log("find %r -> ok=%s where=%s" % (a.find[:60], fq["ok"], fq["where"]))
        for c in fq["candidates"]:
            log("  hit: %s" % c)
        if not fq["ok"]:
            log("  not found; copy quotes from printed block text instead of retyping")
        return
    if a.target:
        res = L.resolve_target(ix, a.target)
        b = res["block"]
        if b is None:
            log("target %s not found: %s" % (a.target, res["note"]))
            return
        ctx = max(0, int(a.context or 1))
        log("target %s -> resolution=%s %s" % (a.target, res["resolution"], res["note"]))
        for k in range(max(0, b["bid"] - ctx), min(len(ix["blocks"]) - 1, b["bid"] + ctx) + 1):
            x = ix["blocks"][k]
            log("%s [%s] %s  (%d chars, sha %s, lines %d-%d)"
                % (">>" if k == b["bid"] else "  ", x["kind"], x["loc"], x["chars"], x["sha"],
                   x["start"] + 1, x["end"] + 1))
            log("   " + x["body"].replace("\n", "\n   "))
        log("impact candidates (blocks sharing terms/symbols):")
        for im in A.impact_map(ix, b):
            log("   ~ %s  score=%d shared=%s" % (im["locator"], im["score"],
                                                 ", ".join(im["shared_terms"][:4])))
        return
    lim = int(a.limit or 40)
    page = max(0, int(a.page or 0))
    log("index: %d blocks / %d materials / case %s"
        % (len(ix["blocks"]), len(ix["materials"]), ix.get("case_id")))
    for t in ix.get("workorder_items") or []:
        b = L.resolve_target(ix, t["target_id"])["block"]
        log("  target %s -> %s" % (t["target_id"], b["loc"] if b else "NOT FOUND"))
    log("blocks (page %d, %d per page; --list for all, --target <id> for full text):" % (page, lim))
    for b in ix["blocks"][page * lim:(page + 1) * lim]:
        log("  [%04d] %-9s %s  %s" % (b["bid"], b["kind"], b["loc"],
                                      b["body"][:110].replace("\n", " ")))
    if (page + 1) * lim < len(ix["blocks"]):
        log("  ... %d more; --page %d" % (len(ix["blocks"]) - (page + 1) * lim, page + 1))

def cmd_check(a, P):
    ix, err = lj(P["work"] / "source_index.json")
    if not isinstance(ix, dict) or not ix.get("blocks"):
        log("no usable index (%s); run init first" % (err or "empty"))
        return
    draft, derr = None, None
    for name in (a.draft, "draft.json", "plan.json"):
        if not name:
            continue
        p = Path(name) if Path(name).is_absolute() else P["work"] / name
        if p.is_file():
            draft, derr = lj(p)
            break
    if not isinstance(draft, dict):
        log("no usable draft in %s (%s); write draft.json first - check validates what you wrote"
            % (P["work"], derr or "missing"))
        return
    vr = A.validate_draft(ix, draft, ix.get("workorder_items") or [])
    led = A.scan_consistency(ix)
    s = vr["summary"]
    dump(P["work"] / "check_report.json",
         {"summary": s, "items": [{k: v for k, v in it.items() if k != "text"} for it in vr["items"]],
          "computed_finding_count": led["finding_count"], "computed_categories": led["counts"],
          "hint": "high=reject (fix or delete); warn=judgement call (record it)"})
    log("== check ==")
    log("targets covered %d/%d | missing %s" % (s["targets_covered"], s["targets_total"],
                                                ", ".join(s["targets_missing"]) or "-"))
    log("annotations accepted %d rejected %d | findings accepted %d"
        % (s["accepted"], len(vr["rejected"]), s["findings_accepted"]))
    log("categories %s | missing %s" % (", ".join(s["categories_covered"]) or "-",
                                        ", ".join(s["categories_missing"]) or "-"))
    log("computed candidates %d %s" % (led["finding_count"], json.dumps(led["counts"])))
    for it in vr["items"]:
        if it["status"] in ("reject", "warn"):
            log("  %-6s %s: %s" % (it["status"], it.get("target_id") or it.get("finding_id"),
                                   "; ".join(it["reasons"])[:400]))
    if not vr["findings"]:
        log("NOTE: findings[] empty - the report would hold computed candidates only, which the "
            "task statement says is not scientific verification.")
    log("check_report -> %s" % (P["work"] / "check_report.json"))

def cmd_build(a, P):
    out, work = P["out"], P["work"]
    ix, err = lj(work / "source_index.json")
    if not isinstance(ix, dict):
        log("no index (%s); running init first" % (err or "missing"))
        cmd_init(a, P)
        ix, _ = lj(work / "source_index.json")
        ix = ix if isinstance(ix, dict) else {}
    cid, contract = str(ix.get("case_id") or ""), ix.get("contract") or {}
    if not ix.get("blocks"):
        payload = {"deliverable": None, "preserved_facts": [], "evidence_map": [], "change_log": [],
                   "annotations": [], "workorder_execution": None, "consistency": None, "coverage": None,
                   "sources": [], "uncertainty": ["no extractable material"],
                   "pending_human": [{"item": "material", "reason": "no text could be extracted",
                                      "action": "supply readable chapters"}],
                   "errors": list(ix.get("notes") or ["empty index"]), "degradations": [],
                   "changes": [], "runtime": rt()}
        dump(out / "result.json", envelope(cid, contract, payload, "insufficient_evidence"))
        log("build: no material indexed -> insufficient_evidence result written (exit 0)")
        return
    draft, derr = None, None
    for name in (a.draft, "draft.json", "plan.json"):
        if not name:
            continue
        p = Path(name) if Path(name).is_absolute() else work / name
        if p.is_file():
            draft, derr = lj(p)
            break
    if not isinstance(draft, dict):
        draft = {}
        log("build: no usable draft (%s) -> deterministic fallbacks, status=partial"
            % (derr or "missing"))
    res = E.build_payload(ix, draft, P)
    payload, status = res["payload"], res["status"]
    try:
        html = R.html_preview(res["asm"]["text"], {"case_id": cid, "skill": NAME, "version": VERSION,
                                                   "status": status})
        (out / "preview.html").write_text(html, encoding="utf-8")
        pdf = R.pdf_preview(res["asm"]["text"].splitlines(), "case %s | %s" % (cid, NAME))
        (out / "export_preview.pdf").write_bytes(pdf)
        res["receipts"]["editable_and_preview"].update({"preview_html_bytes": len(html.encode()),
                                                        "preview_pdf_bytes": len(pdf)})
    except Exception as exc:
        payload["errors"].append("preview render failed: %r" % (exc,))
        status = "partial"
    dump(out / "revision_records.json", {"case_id": cid, "targets": res["recs"]})
    dump(out / "operation_receipts.json", res["receipts"])
    dump(out / "evidence_map.json", {"case_id": cid, "claims": res["ev_map"]})
    dump(out / "change_log.json", {"case_id": cid, "changes": res["clog"]})
    dump(out / "preserved_facts.json", {k: res["fidelity"][k] for k in
                                        ("units", "counts", "total", "not_preserved",
                                         "line_counts_before", "line_counts_after", "basis")})
    dump(out / "pending_human.json", {"case_id": cid, "items": res["pend"]})
    dump(out / "consistency_tables.json", payload["consistency"])
    dump(out / "coverage_matrix.json", payload["coverage"])
    try:
        (out / "consistency_report.md").write_text(
            R.consistency_md(payload["consistency"],
                             {"case_id": cid, "status": status, "targets": res["recs"],
                              "stats": ix.get("stats"),
                              "scope_note": "computed rows are candidates; the scientific review "
                                            "is the agent_findings block"}),
            encoding="utf-8")
    except Exception as exc:
        payload["errors"].append("consistency report render failed: %r" % (exc,))
    man = {"case_id": cid, "skill": NAME, "version": VERSION,
           "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "inputs": [{"path": m["rel"], "chars": m["chars"], "sha256_16": m["sha"]}
                      for m in ix["materials"]],
           "outputs": [],
           "determinism": "same index + same draft -> byte-identical revised_manuscript.md"}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "run_manifest.json":
            txt = p.read_text(encoding="utf-8", errors="replace") if p.suffix in (".md", ".json", ".html", ".patch") else ""
            man["outputs"].append({"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size,
                                   "sha256_16": L.sha(txt)})
    dump(out / "run_manifest.json", man)
    payload["runtime"] = rt()
    dump(out / "result.json", envelope(cid, contract, payload, status))
    log("== build ==")
    log("status %s | agent-covered %d/%d | annotations applied %d (fallback %d)"
        % (status, res["vr"]["summary"]["targets_covered"], res["vr"]["summary"]["targets_total"],
           len(res["applied"]), len(res["fallbacks"])))
    log("manuscript %d chars | blocks preserved %d/%d | rollback==v1 %s"
        % (len(res["asm"]["text"]), res["fidelity"]["total"] - res["fidelity"]["not_preserved"],
           res["fidelity"]["total"], res["vc"]["rollback_equals_v1"]))
    log("consistency %s | agent findings %d | computed candidates %d"
        % (json.dumps(res["led"]["counts"]), len(res["vr"]["findings"]), res["led"]["finding_count"]))
    log("contract keys echoed %d: %s" % (len(contract_keys(contract)), ", ".join(contract_keys(contract)) or "-"))
    if res["pend"]:
        log("pending_human %d item(s)" % len(res["pend"]))
    if res["fallbacks"]:
        log("fallback annotations %s (needs_review=true)"
            % ", ".join(f["target_id"] for f in res["fallbacks"]))
    log("outputs -> %s" % out)

def cmd_selfcheck(a, P):
    out, work = P["out"], P["work"]
    ix, _ = lj(work / "source_index.json")
    res, _ = lj(out / "result.json")
    log("== selfcheck ==")
    checks = E.selfcheck(out, work, ix if isinstance(ix, dict) else {}, res)
    for c in checks:
        log("  [%s] %-32s %s" % ("PASS" if c["pass"] else "FAIL", c["check"], c["detail"]))
    ok = all(c["pass"] for c in checks)
    hard = [c for c in checks if not c["pass"] and c.get("hard", True)]
    if hard and isinstance(res, dict):
        res.setdefault("errors", [])
        for c in hard:
            res["errors"].append("selfcheck: %s (%s)" % (c["check"], c["detail"]))
        if res.get("status") == "ok":
            res["status"] = "partial"
        dump(out / "result.json", res)
        log("  -> result.json updated: %d hard check(s) failed" % len(hard))
    log("selfcheck %d/%d passed" % (sum(1 for c in checks if c["pass"]), len(checks)))

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="longdoc-source-ledger (writing-15)")
    ap.add_argument("cmd", choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--draft", default=None)
    ap.add_argument("--target", default=None)
    ap.add_argument("--find", default=None)
    ap.add_argument("--context", type=int, default=1)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--contract", action="store_true")
    ap.add_argument("--workorder", action="store_true")
    ap.add_argument("--list", action="store_true", help="list all blocks (default view is paginated)")
    a = ap.parse_args(argv)
    if a.list:
        a.limit, a.page = 400, 0
    P = paths(a)
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check,
         "build": cmd_build, "selfcheck": cmd_selfcheck}[a.cmd](a, P)
    except SystemExit:
        raise
    except Exception as exc:
        log("ERROR in %s: %r" % (a.cmd, exc))
        log(traceback.format_exc(limit=4))
        try:
            if a.cmd != "selfcheck":
                ix, _ = lj(P["work"] / "source_index.json")
                ix = ix if isinstance(ix, dict) else {}
                cur, _ = lj(P["out"] / "result.json")
                if not isinstance(cur, dict):
                    cur = write_partial(P["out"], str(ix.get("case_id") or ""), ix.get("contract") or {})
                cur.setdefault("errors", []).append("%s: %r" % (a.cmd, exc))
                if cur.get("status") == "ok":
                    cur["status"] = "partial"
                dump(P["out"] / "result.json", cur)
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
