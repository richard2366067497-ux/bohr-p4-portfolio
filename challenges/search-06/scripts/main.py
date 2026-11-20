#!/usr/bin/env python3
"""main.py -- five-command driver for the literature watch desk (stdlib only).

init       discover input -> work/index.json + legal partial result.json (written first)
show       print window, source coverage and per-work before/after with locators
check      mechanical validation of the Agent draft (delegated to desk.py)
build      watch_brief.md + candidates.csv + decision_trail.jsonl + result.json (delegated)
selfcheck  re-verify products, contract keys and count identities

Defaults: --input /input --output /app/output --work /app/work. Exit code is always 0.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C
import desk as D
import render as R
from desk import (GEN, assemble_alerts, build_index_or_fail, case_id_of, contract_keys, counts_of,
                  fill_contract, input_fp, jread, jwrite, load_draft, load_index, merge_decisions,
                  partial, paths, sha, slim, sub_of, twrite, validate)

desc = "Literature watch desk (%s)" % GEN


def cmd_init(a):
    t0 = time.time()
    inp, out, wk = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    wk.mkdir(parents=True, exist_ok=True)
    errs = []
    case, cpath = D.find_case(inp, errs)
    cid = case_id_of(case, cpath)
    jwrite(out / "result.json", partial(case, cid, errs))      # legal partial before any real work
    idx = build_index_or_fail(a, inp, errs)
    for e in idx.get("errors") or []:
        if e not in errs:
            errs.append(e)
    jwrite(wk / "index.json", slim(idx, cid))
    win = idx.get("window") or {}
    pend = ["read the materials with `show`, author %s, then run check and build" % (wk / "draft.json")]
    if not idx.get("works"):
        pend.append("no bibliographic work recognised under %s: inspect the files and record why" % inp)
    res = partial(case, cid, errs, idx.get("degradations"))
    res.update(sources=idx.get("sources") or [], pending_human=pend,
               uncertainty=["relevance and alerting are not judged yet: run show, read the records, write draft.json"],
               counts={"records_total": len(idx.get("records") or []), "works_total": len(idx.get("works") or []),
                       "duplicate_records": len(idx.get("records") or []) - len(idx.get("works") or [])},
               fingerprints={"input": input_fp(inp), "skill": GEN},
               runtime=dict(skill=GEN, stage="init", seconds=round(time.time() - t0, 2),
                            records=len(idx.get("records") or []), works=len(idx.get("works") or []),
                            contract_keys=len(contract_keys(case.get("output_contract")))))
    jwrite(out / "result.json", res)
    print("== case == %s | %s" % (cid, idx.get("case_path") or "(no case.json found)"))
    print("== window == [%s, %s) tz=%s" % (win.get("start") or "?", win.get("end") or "?", win.get("timezone")))
    print("   basis: %s" % ("; ".join(win.get("basis") or []) or "(none: no watermark/date found, set window in draft)"))
    print("== sources == %d" % len(idx.get("sources") or []))
    for s in idx.get("sources") or []:
        print("  %s | %-30s | %-9s | %3d rec | %-9s | %s" % (s["source_id"], s["file"][:30], s["role"],
                                                             s.get("n_records", 0), s["status"], (s.get("note") or "")[:56]))
    print("== works == %d (baseline records %d | seen ids %d | notice records %d)" % (
        len(idx.get("works") or []), len(idx.get("baseline") or []), idx.get("seen_n") or 0, idx.get("retract_n") or 0))
    for w in idx.get("works") or []:
        print("  %-36s | %-13s | %-10s | %s" % (w["work_key"][:36], w["auto_op"], w["published"] or "-", (w["title"] or "")[:64]))
    print("== next == 1) show  2) write %s  3) check  4) build" % (wk / "draft.json"))
    return 0


def cmd_show(a):
    inp, out, wk = paths(a)
    errs = []
    idx = load_index(wk, a, inp, errs)
    win = idx.get("window") or {}
    print("window : [%s, %s)  tz=%s" % (win.get("start") or "?", win.get("end") or "?", win.get("timezone")))
    print("basis  : %s" % ("; ".join(win.get("basis") or []) or "(none)"))
    print("\nsource coverage:")
    for s in idx.get("sources") or []:
        print("  %s %-26s role=%-8s rec=%3d status=%-9s %s" % (s["source_id"], s["file"][:26], s["role"],
                                                               s.get("n_records", 0), s["status"], (s.get("note") or "")[:64]))
    works = idx.get("works") or []
    if a.op:
        works = [w for w in works if w.get("auto_op") == a.op]
    if a.work_key:
        works = [w for w in works if w["work_key"] == a.work_key or a.work_key in (w.get("keys") or [])]
    lim = a.limit or len(works)
    print("\n%d work(s) in scope, showing %d\n" % (len(works), min(lim, len(works))))
    for i, w in enumerate(works[:lim], 1):
        print("[%d] %s  -- mechanical op: %s" % (i, w["work_key"], w["auto_op"]))
        print("    title   : %s" % (w["title"] or "(none)"))
        print("    meta    : doi=%s arxiv=%s venue=%s" % (w["doi"] or "-", w["arxiv"] or "-", w["venue"] or "-"))
        print("    dates   : published=%s (%s) indexed=%s version=%s type=%s" % (
            w["published"] or "-", w["published_prec"] or "?", w["indexed"] or "-",
            w["version"] or "-", w["type"] or "-"))
        for m in w.get("members") or []:
            print("    rec     : %-8s doi=%-28s %s" % (m["locator"], (m["doi"] or "-")[:28], (m["venue"] or "")[:40]))
            print("      quote : \"%s\"" % (m["title"] or ""))
        if w.get("baseline"):
            b = w["baseline"]
            print("    before  : %-8s venue=%s | version=%s | published=%s | doi=%s" % (
                b.get("locator"), b.get("venue") or "-", b.get("version") or "-",
                b.get("published") or "-", b.get("doi") or "-"))
        print("    after   :          venue=%s | version=%s | published=%s | doi=%s" % (
            w["venue"] or "-", w["version"] or "-", w["published"] or "-", w["doi"] or "-"))
        if w.get("change_signals"):
            print("    signals : %s" % ", ".join(w["change_signals"]))
        print("    auto why: %s" % "; ".join(w.get("auto_reasons") or []))
        if w.get("duplicates"):
            print("    merged  : %s" % ", ".join(d["locator"] for d in w["duplicates"]))
        print("")
    print("next: read the records above and write one decision per work_key into %s" % (wk / "draft.json"))
    return 0


def cmd_build(a):
    t0 = time.time()
    inp, out, wk = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    wk.mkdir(parents=True, exist_ok=True)
    errs, pend, degr = [], [], []
    case, cpath = D.find_case(inp, errs)
    cid = case_id_of(case, cpath)
    jwrite(out / "result.json", partial(case, cid, errs))          # (1) legal partial first
    idx = load_index(wk, a, inp, errs)
    dr, dsrc, derr = load_draft(wk)
    if derr and derr != "missing":
        errs.append({"code": "draft_unreadable", "detail": "%s: %s" % (dsrc, derr)})
        degr.append("draft.json exists but cannot be parsed (%s): decisions stay mechanical" % derr)
        pend.append("fix draft.json and rerun check/build")
    if not dr:
        degr.append("no usable draft.json: mechanical ops kept, no relevance/screening judgement, status=partial")
        pend.append("read the materials with `show` and write decisions for every work_key")
    rows, gaps, extra = merge_decisions(idx, dr)
    degr += gaps
    if extra:
        degr.append("%d draft decision(s) referenced unknown work_key and were ignored: %s" % (len(extra), ", ".join(extra[:5])))
    sub = sub_of(dr, case)
    win = dict(idx.get("window") or {})
    if isinstance(dr.get("window"), dict):
        for k in ("start", "end", "timezone", "basis"):
            if dr["window"].get(k):
                win[k] = dr["window"][k]
    alerts = assemble_alerts(rows, dr, degr)
    misses = [str(x) for x in (dr.get("misses") or dr.get("gaps") or []) if str(x).strip()]
    unc = [str(x) for x in (dr.get("uncertainty") or []) if str(x).strip()]
    cov = [str(x) for x in (dr.get("coverage_notes") or []) if str(x).strip()]
    for s in idx.get("sources") or []:
        if s.get("status") in ("failed", "empty", "not_parsed"):
            misses.append("%s (%s) status=%s: %s" % (s["source_id"], s["file"], s["status"], s.get("note") or ""))
    if not dr and not misses:
        misses = ["draft absent: no gap analysis was written; inspect sources with status != ok and the "
                  "degradations list before trusting coverage"]
    an = sum(1 for r in rows if r["alert"])
    cn = counts_of(rows)
    rep = validate(idx, rows, dr, gaps, extra)
    if not unc:
        unc = ["relevance judgements are the reviewer's; unrecognised record types may hide updates"]
    degr = sorted(set(degr), key=degr.index)
    status = "ok"
    if not idx.get("works"):
        status = "insufficient_evidence" if (idx.get("sources") or idx.get("records")) else "input_error"
        pend.append("no work recognised in the input snapshot; nothing to diff against the previous window")
    elif not dr or gaps or rep["errors"]:
        status = "partial"
    dedup = dr.get("dedup_rules") if isinstance(dr.get("dedup_rules"), dict) else {
        "keys": ["doi", "arxiv", "title_fp"],
        "normalization": "DOI lowercased and prefix-stripped; arXiv version suffix stripped; title NFKC + "
                         "alphanumeric-only sha1(12); records merged when any key matches"}
    brief = R.brief_md(idx, rows, sub, win, alerts, misses, unc, cov, status, cid)
    twrite(out / "watch_brief.md", brief)
    twrite(out / "candidates.csv", R.csv_text(rows))
    twrite(out / "decision_trail.jsonl", R.jsonl_text(R.trail_rows(rows, cid)))
    compact = [{k: r[k] for k in ("work_key", "op", "title", "doi", "arxiv", "venue", "published",
                                  "indexed", "version", "relevance", "alert", "alert_group", "why")} for r in rows]
    compact = [dict(c, sources=r["sources"], evidence=r["evidence"], suppress_reason=r["suppress_reason"])
               for c, r in zip(compact, rows)]
    METHOD = ("init discovers record sources and a baseline/watermark, normalizes DOI/arXiv/title keys, merges "
              "copies into one work, then diffs against the previous snapshot on both the published and the indexed "
              "axis; the Agent reads each record and writes op + relevance + screening rationale + verbatim evidence; "
              "build renders the brief, candidate table and decision trail and reconciles the counts.")
    base = {"summary": brief, "candidates": compact, "ranking": compact,
            "screening": [{"work_key": r["work_key"], "op": r["op"], "relevance": r["relevance"],
                           "why": r["why"], "suppress_reason": r["suppress_reason"]} for r in rows],
            "evidence": R.trail_rows(rows, cid), "query": sub["query"], "window": win,
            "sources": idx.get("sources") or [], "dedup": dedup,
            "retractions": [c for c in compact if c["op"] == "retract"],
            "updates": [c for c in compact if c["op"] == "update"],
            "alerts": alerts, "misses": misses, "uncertainty": unc, "counts": cn,
            "status_note": "%s: %d/%d works reviewed; %d alerted; %d degraded item(s)" % (
                status, rep["reviewed"], len(rows), an, len(degr)),
            "method": METHOD, "artifacts": ["watch_brief.md", "candidates.csv", "decision_trail.jsonl", "result.json"],
            "changes": []}
    fp = {"input": input_fp(inp), "skill": GEN,
          "decisions": sha(json.dumps([[r["work_key"], r["op"], r["relevance"], r["why"]] for r in rows],
                                      sort_keys=True, ensure_ascii=False))[:32]}
    prev = {}
    try:
        prev = jread(wk / "build_state.json") if (wk / "build_state.json").exists() else {}
    except Exception:
        prev = {}
    changes = [{"step": "init", "window": "[%s,%s)" % (win.get("start"), win.get("end")),
                "sources": len(idx.get("sources") or []), "works": len(rows)},
               {"step": "build", "artifacts": base["artifacts"], "reviewed": rep["reviewed"],
                "mechanical_fallback": len(rows) - rep["reviewed"], "alerted": an}]
    if prev.get("input") == fp["input"] and prev.get("decisions") == fp["decisions"]:
        changes.append({"step": "rerun_same_input", "already_delivered": True,
                        "detail": "identical input fingerprint and decisions: no second push expected"})
    else:
        changes.append({"step": "rerun_same_input", "already_delivered": False,
                        "detail": "new input or changed decisions: this window would be delivered once"})
    jwrite(wk / "build_state.json", fp)
    res, miss = fill_contract(case, base)
    res.update(case_id=cid, status=status, sources=idx.get("sources") or [], uncertainty=unc,
               pending_human=pend, errors=errs + rep["errors"], degradations=degr, changes=changes,
               counts=cn, fingerprints=fp,
               runtime=dict(skill=GEN, stage="build", seconds=round(time.time() - t0, 2),
                            records=cn["records_total"], works=len(rows), alerted=an,
                            reviewed=rep["reviewed"], quote_hit_rate=rep["quote_hit_rate"],
                            contract_keys=len(contract_keys(case.get("output_contract"))),
                            unfilled_contract=miss or "none"))
    if miss:
        pend.append("output_contract keys with no matching content: %s" % ", ".join(miss))
        res["pending_human"] = pend
        res["status"] = "partial" if status == "ok" else status
    jwrite(out / "result.json", res)                                # (3) unconditional finalize
    print("status=%s records=%d works=%d new=%d update=%d retract=%d late_index=%d seen=%d out=%d alerted=%d" % (
        res["status"], cn["records_total"], cn["works_total"], cn["new"], cn["update"], cn["retract"],
        cn["late_index"], cn["seen"], cn["out_of_window"], an))
    print("reviewed=%d/%d quote_hit_rate=%s dup_records=%d contract=%d/%d artifacts=%s" % (
        rep["reviewed"], len(rows), rep["quote_hit_rate"], cn["duplicate_records"],
        len(contract_keys(case.get("output_contract"))) - len(miss),
        len(contract_keys(case.get("output_contract"))), ", ".join(base["artifacts"])))
    if degr:
        print("degraded: %s" % " | ".join(degr[:4]))
    return 0


def cmd_selfcheck(a):
    inp, out, wk = paths(a)
    res = {}
    try:
        res = jread(out / "result.json")
    except Exception as e:
        print("FAIL result.json unreadable: %r" % (e,))
    case, _ = D.find_case(inp, [])
    keys = contract_keys(case.get("output_contract"))
    missing = [k for k in keys if k not in res]
    empty = [k for k in keys if res.get(k) in (None, "", [], {})]
    cn = res.get("counts") or {}
    checks = [
        ("result.contract_keys_present", not missing, "%d/%d" % (len(keys) - len(missing), len(keys))),
        ("result.contract_keys_filled", not empty, "empty=%s" % (empty[:5] or "none")),
        ("result.envelope", all(k in res for k in ("case_id", "status", "errors", "degradations",
                                                   "changes", "counts", "fingerprints")), str(res.get("status"))),
        ("counts.records_minus_works", cn.get("identity_1") is True,
         "%s-%s=%s" % (cn.get("records_total"), cn.get("works_total"), cn.get("duplicate_records"))),
        ("counts.op_sum", cn.get("identity_2") is True, "works=%s" % cn.get("works_total")),
        ("counts.alert_bound", cn.get("identity_3") is True, "alerted=%s" % cn.get("alerted")),
    ]
    for name, p, need in (("watch_brief.md", out / "watch_brief.md", 400),
                          ("candidates.csv", out / "candidates.csv", 2),
                          ("decision_trail.jsonl", out / "decision_trail.jsonl", 1)):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            n = len(txt) if p.suffix == ".md" else len([x for x in txt.splitlines() if x.strip()])
            checks.append(("%s.present" % name, n >= need, "%d units" % n))
        except Exception as e:
            checks.append(("%s.present" % name, False, repr(e)))
    try:
        lines = [json.loads(x) for x in (out / "decision_trail.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        ver = sum(1 for x in lines if x.get("quote_verified"))
        checks.append(("trail.quotes_verified", bool(lines) and ver == len(lines), "%d/%d" % (ver, len(lines))))
        checks.append(("trail.reviewed", all(x.get("reviewed") for x in lines),
                       "%d mechanical" % sum(1 for x in lines if not x.get("reviewed"))))
        checks.append(("trail.rows_match_counts", len(lines) == (cn.get("works_total") or 0),
                       "%d vs %s" % (len(lines), cn.get("works_total"))))
    except Exception as e:
        checks.append(("trail.parse", False, repr(e)))
    for name, ok, detail in checks:
        print("%s %-30s %s" % ("PASS" if ok else "FAIL", name, detail))
    ok = all(c[1] for c in checks)
    print("selfcheck: %s (%d/%d) status=%s fp.input=%s" % (
        "PASS" if ok else "NEEDS WORK", sum(1 for c in checks if c[1]), len(checks),
        res.get("status"), (res.get("fingerprints") or {}).get("input", "-")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description=desc)
    sub = ap.add_subparsers(dest="cmd")
    helps = [("init", "discover input, build index + partial result.json"),
             ("show", "print window/coverage/per-work before-after with locators"),
             ("check", "validate the Agent draft"),
             ("build", "render products + finalize result.json"),
             ("selfcheck", "re-verify products, contract and counts")]
    for n, h in helps:
        q = sub.add_parser(n, help=h)
        for f in ("--input", "--output", "--work"):
            q.add_argument(f)
        if n == "show":
            q.add_argument("--work-key")
            q.add_argument("--op")
            q.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        {"init": cmd_init, "show": cmd_show, "check": D.cmd_check,
         "build": cmd_build, "selfcheck": cmd_selfcheck}[a.cmd](a)
    except Exception as e:
        import traceback
        try:
            inp, out, _ = paths(a)
            out.mkdir(parents=True, exist_ok=True)
            case, _ = D.find_case(inp, [])
            jwrite(out / "result.json", partial(case, case_id_of(case, None),
                                                [{"code": "unhandled_exception",
                                                  "detail": "%s: %s" % (type(e).__name__, e),
                                                  "trace": traceback.format_exc()[-700:]}]))
        except Exception:
            pass
        print("ERROR %s: %s" % (type(e).__name__, e), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
