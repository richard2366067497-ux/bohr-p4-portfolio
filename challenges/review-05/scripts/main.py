#!/usr/bin/env python3
"""main.py -- CLI (init|show|check|build|selfcheck) for academic-compliance-matrix. stdlib only.

Exit code is always 0; failures are reported inside result.json.
"""
import argparse
import csv
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C            # noqa: E402
import rules as R           # noqa: E402

SKILL = "academic-compliance-matrix"


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))


def jwrite(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def twrite(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


def paths(a):
    degr = []
    inp = Path(a.input or os.environ.get("SKILL_INPUT") or "/input")
    out = Path(a.output or os.environ.get("SKILL_OUTPUT") or "/app/output")
    work = Path(a.work or os.environ.get("SKILL_WORK") or "/app/work")
    if not inp.exists() and not (a.input or os.environ.get("SKILL_INPUT")) and (Path.cwd() / "input").exists():
        inp = Path.cwd() / "input"
        degr.append("default /input absent; fell back to %s" % inp)
    for name, tgt in (("output", out), ("work", work)):
        try:
            tgt.mkdir(parents=True, exist_ok=True)
        except Exception:
            fb = Path.cwd() / name
            fb.mkdir(parents=True, exist_ok=True)
            degr.append("cannot use %s; fell back to %s" % (tgt, fb))
            if name == "output":
                out = fb
            else:
                work = fb
    return inp, out, work, degr


def walk(o, depth=0):
    if depth > 6:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k), v
            yield from walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o[:40]:
            yield from walk(v, depth + 1)


def find_case(inp, errs):
    if not inp.exists():
        errs.append({"code": "input_missing", "detail": "input dir not found: %s" % inp})
        return {}, None
    for p in sorted(inp.rglob("case.json")) or sorted(inp.rglob("*.json")):
        try:
            obj = jread(p)
            if isinstance(obj, dict):
                return obj, p
        except Exception as e:
            errs.append({"code": "case_json_invalid", "detail": "%s: %r" % (p.name, e)})
    return {}, None


def contract_of(case):
    for k in ("output_contract", "outputContract", "result_contract", "contract"):
        if isinstance(case.get(k), (dict, list)):
            return case[k]
    for k, v in walk(case):
        if "contract" in k.lower() and isinstance(v, (dict, list)):
            return v
    return None


def materials(inp):
    out = []
    if not inp.exists():
        return out
    for p in sorted(inp.rglob("*")):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low in ("case.json", "task.md") or low.startswith("case-") or low.endswith(".pyc"):
            continue
        if p.suffix.lower() in (".yaml", ".yml") and "environment" in str(p).lower():
            continue
        out.append(p)
    return out


def cid_of(case, cp):
    for k in ("case_id", "caseId", "id", "case"):
        if isinstance(case.get(k), str) and case[k].strip():
            return case[k].strip()
    return cp.parent.name if cp else "unknown"


def empty_result(case, cid, errs, degr=None):
    degr = list(degr or [])
    ct = contract_of(case)
    if isinstance(ct, dict):
        res = R.fill_contract(ct, {})
    elif isinstance(ct, list):
        res = {k: [] for k in R.contract_keys(ct)}
    else:
        res = dict(R.DEFAULT_CONTRACT)
        degr.append("output_contract missing in case.json; default 9-key contract used")
    for k, dv in (("case_id", cid), ("status", "partial"), ("sources", []), ("uncertainty", []),
                  ("pending_human", []), ("errors", errs), ("degradations", degr), ("changes", []),
                  ("runtime", {}), ("method", ""), ("coverage", {}), ("artifacts", []),
                  ("rule_version", R.VERSION)):
        res.setdefault(k, dv)
    res["case_id"], res["status"], res["errors"], res["degradations"] = cid, "partial", errs, degr
    return res


# --- init
def do_index(inp, work, errs, degr):
    case, cp = find_case(inp, errs)
    cid = cid_of(case, cp)
    docs = {}
    for i, p in enumerate(materials(inp)):
        try:
            d = C.extract_doc(p)
        except Exception as e:
            errs.append({"code": "extract_failed", "detail": "%s: %r" % (p.name, e)})
            d = {"kind": "unreadable", "engine": "failed", "quality": 0.0, "n_pages": 0, "text": "",
                 "paras": [{"locator": "p1#para1", "page": "p1", "text": ""}], "notes": ["extraction failed"]}
        d.update(filename=p.name, path=str(p), n_paras=len(d["paras"]))
        docs["D%d" % (i + 1)] = d
        degr += ["%s: %s" % (p.name, n) for n in d.get("notes") or []]
    sig = C.detect(docs)
    tpath = inp / "task.md"
    try:
        task = tpath.read_text(encoding="utf-8", errors="replace")[:1500] if tpath.exists() else ""
    except Exception:
        task = ""
    idx = {"case_id": cid, "case_path": str(cp or ""), "input_root": str(inp),
           "generated": time.strftime("%Y-%m-%d"), "rule_version": R.VERSION,
           "contract": contract_of(case) or {}, "task_excerpt": task,
           "docs": {k: {x: d.get(x) for x in ("filename", "kind", "engine", "n_pages", "quality",
                                              "n_paras", "path", "notes")} for k, d in docs.items()},
           "paras": {k: d["paras"] for k, d in docs.items()}, "texts": {k: d["text"] for k, d in docs.items()},
           "signals": sig, "seed_rows": C.seed_skeleton(sig)}
    jwrite(work / "index.json", idx)
    return case, cp, cid, docs, sig, idx


def template(idx):
    sig = idx["signals"]
    cites = []
    for num in sig["citations"]["dangling"]:
        m = next((x for x in sig["citations"]["markers"] if x.get("num") == num), {})
        cites.append({"marker": "[%d]" % num, "claim_locator": m.get("locator", ""), "claim_quote": "",
                      "ref_entry": "", "match": "", "note": "正文有标记，文献表未见该编号"})
    for num in sig["citations"]["orphan"]:
        e = next((x for x in sig["citations"]["entries"] if x.get("num") == num), {})
        cites.append({"marker": "[%d]" % num, "claim_locator": "", "claim_quote": "",
                      "ref_entry": e.get("raw", ""), "match": "", "note": "文献表有条目，正文未见引用"})
    for num in sig["citations"]["duplicates"]:
        cites.append({"marker": "[%d]" % num, "claim_locator": "", "claim_quote": "",
                      "ref_entry": "", "match": "", "note": "同一编号出现多个条目"})
    return {"_readme": [
        "复制为 draft.json 后逐行填判断，不要改 row_id。",
        "violation 必须给 doc_id + evidence_locator + quote（逐字取自 show）；判不出写 unverifiable + what_human_must_check。",
        "not_applicable 必须写 searched_scope；写完依次运行 check 与 build，未填的行会导出为 unverifiable。"],
        "case_id": idx["case_id"],
        "doc_meta": {"title": "", "doc_type": "manuscript", "venue_name": "",
                     "guideline_present": bool(sig["guideline_present"]),
                     "guideline_note": "" if sig["guideline_present"] else "材料未检出作者指南：venue 行只能 unverifiable"},
        "compliance_matrix": C.seed_skeleton(sig),
        "citation_reconciliation": cites,
        "pii_ledger": [{"ledger_id": "PII-%02d" % (i + 1), "pii_type": p["pii_type"],
                        "location": p["locator"], "redaction": "[REDACTED-%s]" % p["pii_type"].upper(),
                        "rationale": ""} for i, p in enumerate(sig["pii"])],
        "uncovered_requirements": [], "summary": "", "uncertainties": []}


def cmd_init(a):
    t0 = time.time()
    inp, out, work, degr = paths(a)
    errs = []
    case, cp = find_case(inp, errs)
    cid = cid_of(case, cp)
    jwrite(out / "result.json", empty_result(case, cid, errs, degr))
    case, cp, cid, docs, sig, idx = do_index(inp, work, errs, degr)
    jwrite(work / "draft.template.json", template(idx))
    res = empty_result(case, cid, errs, degr)
    res.update(status="partial",
               sources=[{"doc_id": k, "file": d["filename"], "kind": d["kind"], "engine": d["engine"],
                         "n_paras": d["n_paras"], "quality": d["quality"],
                         "sha256_16": R.sha256_of(d["path"])} for k, d in docs.items()],
               pending_human=["read the materials, fill %s, then run check and build" % (work / "draft.json")],
               coverage={"rows": len(idx["seed_rows"]), "judged": 0, "coverage": 0.0},
               method="index built; no verdicts yet (judgement belongs to the Agent draft)",
               runtime={"skill": SKILL, "version": R.VERSION, "stage": "init",
                        "seconds": round(time.time() - t0, 2), "docs": len(docs)})
    jwrite(out / "result.json", res)
    print("== materials ==  (under %s)" % inp)
    for k, d in docs.items():
        print("%s | %s | %s | %s paras | quality %.2f | %s" % (k, d["filename"], d["kind"], d["n_paras"],
                                                               d["quality"], d["engine"]))
    c = sig["citations"]
    print("== seeds == %d rows, domains %s" % (len(idx["seed_rows"]),
                                               ",".join(sorted({r["domain"] for r in idx["seed_rows"]}))))
    print("== citations == markers=%d entries=%d dangling=%s orphan=%s duplicate=%s gaps=%s" % (
        c["n_markers"], c["n_entries"], c["dangling"][:12], c["orphan"][:12],
        c["duplicates"][:12], c["gaps"][:12]))
    print("== declarations == found %d/%d: %s" % (
        len([1 for v in sig["declarations"].values() if v.get("found")]), len(R.DECL),
        ",".join(sorted(sig["declarations"]))))
    print("== pii == %d candidate(s) | guideline == %s" % (
        len(sig["pii"]), "present in %s" % sig["guideline_docs"] if sig["guideline_present"]
        else "absent (venue rows must stay unverifiable)"))
    print("== next == 1) show  2) write %s  3) check  4) build" % (work / "draft.json"))
    return 0


# --- show
def cmd_show(a):
    _, _, work, _ = paths(a)
    if not (work / "index.json").exists():
        print("index missing: run `python3 scripts/main.py init` first")
        return 0
    C.show_index(jread(work / "index.json"), a.domain, a.doc, a.paras, a.grep)
    return 0


# --- check
def cmd_check(a):
    _, _, work, _ = paths(a)
    idx = {}
    if (work / "index.json").exists():
        idx = jread(work / "index.json")
    if not idx:
        print(json.dumps({"ok": False, "errors": [{"code": "index_missing", "detail": "run init first"}]},
                         ensure_ascii=False))
        return 0
    p = work / "draft.json"
    if not p.exists():
        print(json.dumps({"ok": False, "counts": {}, "warnings": [],
                          "errors": [{"code": "draft_missing", "detail": "copy %s/draft.template.json to draft.json"
                                      % work}]}, ensure_ascii=False))
        return 0
    try:
        draft = jread(p)
    except Exception as e:
        print(json.dumps({"ok": False, "counts": {}, "warnings": [],
                          "errors": [{"code": "draft_unreadable", "detail": repr(e)}]}, ensure_ascii=False))
        return 0
    rep = R.validate(draft, idx)
    print(json.dumps({"ok": rep["ok"], "counts": rep["counts"], "errors": rep["errors"],
                      "warnings": rep["warnings"]}, ensure_ascii=False, indent=1))
    for e in rep["errors"][:15]:
        print("FIX [%s] %s :: %s" % (e["code"], e["where"], e["detail"]))
    cn = rep["counts"]
    print("rows=%s judged=%s coverage=%s violations=%s unverifiable=%s quote_pass=%s errors=%d warnings=%d" % (
        cn.get("rows"), cn.get("judged"), cn.get("coverage"), cn.get("violation"), cn.get("unverifiable"),
        cn.get("quote_pass_rate"), len(rep["errors"]), len(rep["warnings"])))
    return 0


# --- build
def merge_rows(seed, draft_rows, degr):
    by_id = {r["row_id"]: dict(r) for r in seed}
    extra = 0
    for r in draft_rows:
        rid = str(r.get("row_id") or "")
        if rid in by_id:
            merged = dict(by_id[rid])
            merged.update({k: v for k, v in r.items() if v not in (None, "", [], {})})
            by_id[rid] = merged
        else:
            by_id[rid or "X%d" % extra] = dict(r)
            extra += 1
    if extra:
        degr.append("%d draft row(s) had no catalogue seed and were appended as-is" % extra)
    unjudged = [rid for rid, r in by_id.items() if not r.get("verdict")]
    for rid in unjudged:
        r = by_id[rid]
        r["verdict"] = "unverifiable"
        r["severity"] = r.get("severity") or "major"
        r["severity_reason"] = r.get("severity_reason") or "该行未获判定，风险未知，按 major 计入待复核"
        r["observed"] = r.get("observed") or "未审查（目录种子行）"
        r["_unexamined"] = True
        r["what_human_must_check"] = r.get("what_human_must_check") or \
            "该行由目录种子生成且未经阅读判定：请按 requirement 逐条核对原文后给出 verdict"
    if unjudged:
        degr.append("%d matrix row(s) had no verdict and were exported as unverifiable" % len(unjudged))
    return C.sort_rows(list(by_id.values()))


def findings_of(rows):
    pick = [r for r in rows if not r.get("_unexamined")
            and (R.norm(r.get("verdict")).lower() == "violation"
                or (R.norm(r.get("verdict")).lower() == "unverifiable"
                    and R.norm(r.get("severity")).lower() in ("critical", "major")))]
    pick.sort(key=lambda r: (R.SEV_W.get(R.norm(r.get("severity")).lower(), 9), str(r.get("row_id"))))
    out = []
    for i, r in enumerate(pick):
        vd, q, loc = R.norm(r.get("verdict")).lower(), R.norm(r.get("quote")), R.norm(r.get("evidence_locator"))
        out.append({"finding_id": "F-%02d" % (i + 1), "facet": r.get("domain"),
                    "matrix_row_id": r.get("row_id"), "title": r.get("requirement"),
                    "issue_type": "violation" if vd == "violation" else "pending_review",
                    "severity": R.norm(r.get("severity")).lower(),
                    "severity_reason": r.get("severity_reason") or "", "doc_id": r.get("doc_id") or "",
                    "location": loc, "quote": q, "basis_source": r.get("rule_source"),
                    "expected": r.get("expected") or "", "observed": r.get("observed") or "",
                    "rationale": r.get("observed") or r.get("severity_reason") or "",
                    "remediation": r.get("remediation") or "",
                    "what_human_must_check": r.get("what_human_must_check") or "",
                    "verifiability": ("verbatim_quote+locator" if q and loc else
                                      "locator_only" if loc else "none")})
    return out


def cmd_build(a):
    t0 = time.time()
    inp, out, work, degr = paths(a)
    errs, pend = [], []
    case, cp = find_case(inp, errs)
    cid = cid_of(case, cp)
    jwrite(out / "result.json", empty_result(case, cid, errs, degr))
    idx = {}
    if (work / "index.json").exists():
        try:
            idx = jread(work / "index.json")
        except Exception as e:
            errs.append({"code": "index_unreadable", "detail": repr(e)})
    if not idx:
        try:
            case, cp, cid, docs, sig, idx = do_index(inp, work, errs, degr)
        except Exception as e:
            errs.append({"code": "init_failed", "detail": repr(e)})
            idx = {}
    docs, sig, seed = idx.get("docs") or {}, idx.get("signals") or {}, idx.get("seed_rows") or []
    cid = idx.get("case_id") or cid
    draft, dsrc, p = {}, "", work / "draft.json"
    if p.exists():
        dsrc = str(p)
        try:
            draft = jread(p)
        except Exception as e:
            errs.append({"code": "draft_unreadable", "detail": repr(e)})
    if not docs:
        errs.append({"code": "no_material", "detail": "no readable material file under %s" % inp})
    if not draft:
        degr.append("no usable draft.json: matrix exported as catalogue seeds with verdict=unverifiable")
        pend.append("read the materials and fill %s, then re-run check and build" % p)
    rows = merge_rows(seed, R.rows_of(draft), degr)
    findings = findings_of(rows)
    rep = R.validate({"compliance_matrix": rows,
                      "citation_reconciliation": draft.get("citation_reconciliation")
                      or [{"marker": "", "match": "unverifiable", "note": "no reconciliation produced"}],
                      "pii_ledger": draft.get("pii_ledger") or []}, idx)
    cn, judged = rep["counts"], rep["counts"].get("judged", 0)
    status = ("input_error" if not docs else "insufficient_evidence" if judged == 0
              else "partial" if (rep["errors"] or degr) else "ok")
    ledger = [dict({"ledger_id": "PII-%02d" % (i + 1)},
                   **{k: (R.mask_pii(v) if k == "rationale" else v) for k, v in e.items()})
              for i, e in enumerate([x for x in (draft.get("pii_ledger") or []) if isinstance(x, dict)])]
    srcs = [{"doc_id": k, "file": d.get("filename"), "kind": d.get("kind"), "engine": d.get("engine"),
             "n_paras": d.get("n_paras"), "quality": d.get("quality"),
             "sha256_16": R.sha256_of(d.get("path") or "")} for k, d in docs.items()]
    M = {"case_id": cid, "status": status, "rule_version": R.VERSION,
         "generated": time.strftime("%Y-%m-%d"),
         "doc_meta": dict({"title": "", "doc_type": "manuscript", "venue_name": "",
                           "guideline_present": bool(sig.get("guideline_present"))},
                          **(draft.get("doc_meta") or {})),
         "matrix": rows, "compliance_matrix": rows, "findings": findings, "items": findings,
         "sources": srcs, "pii_ledger": ledger,
         "citation_reconciliation": [x for x in (draft.get("citation_reconciliation") or [])
                                     if isinstance(x, dict)],
         "coverage": cn,
         "basis_index": [{"rule_source": s, "count": len([r for r in rows if R.norm(r.get("rule_source")).lower() == s]),
                          "available_in_input": True if s != "venue_guideline" else bool(sig.get("guideline_present"))}
                         for s in R.SRCS],
         "severity_summary": {s: len([f for f in findings if f["severity"] == s]) for s in R.SEVS},
         "degradations": degr,
         "uncertainty": [u for u in (draft.get("uncertainties") or []) if isinstance(u, str)][:12],
         "pending_human": pend + [x for x in (draft.get("uncovered_requirements") or [])
                                  if isinstance(x, dict)][:12],
         "remediation_plan": [{"priority": pr, "severity": sv,
                               "items": [{"row_id": f["matrix_row_id"], "title": f["title"],
                                          "action": f["remediation"]} for f in findings
                                         if f["severity"] == sv and f["issue_type"] == "violation"]}
                              for pr, sv in (("P0", "critical"), ("P1", "major"), ("P2", "minor"),
                                             ("P3", "suggestion"))],
         "artifacts": ["result.json", "compliance_matrix.csv", "compliance_report.md",
                       "pii_ledger.json", "run_manifest.json"],
         "method": "matrix-first: catalogue seeds + Agent verdicts -> compliance matrix -> derived findings "
                   "-> report; every violation needs a verbatim quote plus a locator"}
    report = R.render_report(M)
    if draft.get("summary"):
        report = report.replace("## 1. 合规矩阵", "**结论摘要**：%s\n\n## 1. 合规矩阵" % draft["summary"], 1)
    M["summary"] = report
    twrite(out / "compliance_report.md", report)
    with (out / "compliance_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(R.matrix_csv_rows(rows))
    jwrite(out / "pii_ledger.json", {"case_id": cid, "counts": len(ledger), "entries": ledger,
                                     "policy": "只记录类型、位置与脱敏形式；示例值用 [REDACTED-*] 占位"})
    try:
        prev = (jread(out / "run_manifest.json") or {}).get("counts") or {}
    except Exception:
        prev = {}
    jwrite(out / "run_manifest.json", {
        "skill": SKILL, "version": R.VERSION, "rule_version": R.VERSION, "generated": M["generated"],
        "case_id": cid, "input_root": str(inp), "case_path": idx.get("case_path", ""),
        "inputs": {s["doc_id"]: s["sha256_16"] for s in srcs},
        "counts": {k: cn.get(k) for k in ("rows", "judged", "violation", "compliant", "not_applicable",
                                          "unverifiable", "quote_pass_rate", "evidence_coverage",
                                          "domains_covered")},
        "previous_counts": prev, "deterministic_sort": "(domain, row_id)", "findings": len(findings),
        "degradations": degr, "commands": ["init", "show", "check", "build"]})
    res, miss = R.backfill(contract_of(case) or R.DEFAULT_CONTRACT, M)
    for k in ("compliance_matrix", "findings", "pii_ledger", "citation_reconciliation", "coverage", "summary",
              "sources", "degradations", "remediation_plan", "uncertainty", "artifacts", "basis_index",
              "severity_summary", "method"):
        res.setdefault(k, M.get(k))
    res.update(case_id=cid, status=status, sources=srcs,
               uncertainty=M["uncertainty"] or ["rows marked unverifiable need a human check before use"],
               pending_human=pend, errors=errs + rep["errors"], degradations=degr,
               changes=[{"step": "build", "draft": dsrc or "(none)", "rows": len(rows), "judged": judged,
                         "findings": len(findings), "contract_unfilled": miss},
                        {"step": "render", "artifacts": M["artifacts"]}],
               runtime={"skill": SKILL, "version": R.VERSION, "stage": "build",
                        "seconds": round(time.time() - t0, 2), "docs": len(docs), "rows": len(rows),
                        "judged": judged, "findings": len(findings)},
               artifacts=M["artifacts"], coverage=cn, method=M["method"], rule_version=R.VERSION)
    if miss:
        res["pending_human"] = list(res.get("pending_human") or []) + [
            "output_contract keys with no matching content: %s" % ", ".join(miss)]
    jwrite(out / "result.json", res)
    print("status=%s rows=%d judged=%d violations=%d unverifiable=%d compliant=%d quote_pass=%s coverage=%s" % (
        status, len(rows), judged, cn.get("violation"), cn.get("unverifiable"), cn.get("compliant"),
        cn.get("quote_pass_rate"), cn.get("coverage")))
    print("findings=%d (%s)" % (len(findings), ", ".join("%s:%s" % (k, v) for k, v in
                                                         M["severity_summary"].items() if v) or "none"))
    print("artifacts:", ", ".join(M["artifacts"]), "| unfilled contract:", miss or "none")
    if rep["errors"]:
        print("check errors carried into result.json.errors:", ", ".join(sorted({e["code"] for e in rep["errors"]})))
    return 0


# --- selfcheck
def cmd_selfcheck(a):
    inp, out, _w, _d = paths(a)
    C.selfcheck(out, R.contract_keys(contract_of(find_case(inp, [])[0])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="%s v%s" % (SKILL, R.VERSION))
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (("init", "index /input and write a partial result.json"),
                           ("show", "print locator-bearing candidate lists"),
                           ("check", "machine-gate the Agent draft"),
                           ("build", "render artifacts and finalize result.json"),
                           ("selfcheck", "re-verify produced artifacts")):
        q = sub.add_parser(name, help=helptext)
        for f in ("--input", "--output", "--work"):
            q.add_argument(f)
        if name == "show":
            for f in ("--doc", "--paras", "--domain", "--grep"):
                q.add_argument(f)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
         "selfcheck": cmd_selfcheck}[a.cmd](a)
    except Exception as e:
        try:
            inp, out, _w, _d = paths(a)
            _case, _cp = find_case(inp, [])
            jwrite(out / "result.json", empty_result(
                _case, cid_of(_case, _cp),
                [{"code": "unhandled_exception", "detail": "%s: %s" % (type(e).__name__, e),
                  "trace": traceback.format_exc()[-800:]}]))
        except Exception:
            pass
        print("ERROR %s: %s" % (type(e).__name__, e), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
