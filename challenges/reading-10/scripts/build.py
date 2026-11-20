#!/usr/bin/env python3
"""build.py -- build command for repro-metric-crosscheck (split out to keep main.py small).

do_build: read the draft, resolve reported values, really execute every candidate,
compare under the pre-declared band, attribute the gaps, grade the verdict and
finalize result.json plus the human-readable / machine-readable artifacts.
Rendering (repro_report.md) also lives here. Exit code is always 0.
"""
import json
import os
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core as C  # noqa: E402
import engine as E  # noqa: E402

T0 = time.time()
LIMIT = 760


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log(s=""):
    print(s, flush=True)


def dump(path, obj):
    return C.dump_json(path, obj)


def render_md(rec):
    L = ["# Reproduction and method-verification record", "",
         "- case_id: `%s` | generated: %s | status: **%s**"
         % (rec.get("case_id"), rec.get("generated_at"), rec.get("status")),
         "- verdict: **%s** - %s" % (rec["verdict"]["tier"], rec["verdict"]["rationale"]),
         "- scope: %s" % C.snip(rec.get("scope_text"), 420), ""]

    def table(head, rows):
        L.append("| " + " | ".join(head) + " |")
        L.append("|" + "---|" * len(head))
        for row in rows:
            L.append("| " + " | ".join("" if c is None else str(c).replace("|", "/").replace("\n", " ")
                                       for c in row) + " |")
        L.append("")

    L.append("## 1. Task completion - materials, locators, coverage\n")
    table(["id", "file", "kind", "bytes", "units", "quality", "sha1"],
          [[m["id"], m["rel"], m["kind"], m["bytes"], len(m.get("units") or []), m.get("quality"),
            m.get("sha1")] for m in rec["materials"]])
    table(["object class", "status", "objects"],
          [[k, v["status"], ", ".join(v["objects"][:6]) or "-"] for k, v in rec["coverage"].items()])
    L.append("## 2. Environment snapshot\n")
    L.append("```json\n" + json.dumps(rec["environment"], ensure_ascii=False, indent=2) + "\n```\n")
    L.append("## 3. Parameter restoration (paper / code-inferred / self-set)\n")
    if rec["params"]:
        table(["param", "value", "class", "locator", "quote", "conflict"],
              [[p.get("name"), p.get("value"), p.get("class"), p.get("locator"),
                "verified" if p.get("verified") else p.get("check"), p.get("conflict_note")]
               for p in rec["params"]])
    else:
        L.append("_No parameter table in the draft: parameter restoration is an open gap._\n")
    L.append("## 4. Pre-declared tolerance band (locked before any run)\n")
    L.append("- declared_step `%s` | declared_at `%s` | before_any_run `%s` | plan_sha256 `%s`"
             % (rec["tolerance_plan"].get("declared_step"), rec["tolerance_plan"].get("declared_at"),
                rec["tolerance_plan"].get("before_any_run"),
                (rec["tolerance_plan"].get("plan_sha256") or "")[:16]))
    table(["metric", "abs_tol", "rel_tol", "abs_frac", "basis"],
          [[k, v.get("abs_tol"), v.get("rel_tol"), v.get("abs_frac"), v.get("basis")]
           for k, v in (rec["tolerance_plan"].get("entries") or {}).items()])
    L.append("## 5. Code execution - real runs\n")
    if rec["runs"]:
        table(["run", "exit", "duration_ms", "metrics", "command"],
              [[r["run_id"], r.get("exit_code"), r.get("duration_ms"), len(r.get("metrics") or {}),
                " ".join(r.get("argv") or [])] for r in rec["runs"]])
        for r in rec["runs"]:
            L.append("- `%s`: log `%s`%s" % (r["run_id"], r.get("log_path"),
                                             (" | error: " + str(r["error"])) if r.get("error") else ""))
        L.append("")
    else:
        L.append("_No candidate method was executed._\n")
    L.append("## 6. Result comparison under the locked band\n")
    if rec["comparison"]:
        table(["run", "metric", "observed", "reported", "abs_dev", "rel_dev", "call", "reported source"],
              [[r["run"], r["metric"], r["observed"], r["reported"], r["abs_dev"], r["rel_dev"],
                r["verdict"], r.get("reported_locator") or r.get("reported_source")]
               for r in rec["comparison"]])
        for r in rec["comparison"][:8]:
            if r.get("metric_evidence"):
                L.append("- `%s/%s` value traced to stdout: `%s`"
                         % (r["run"], r["metric"], r["metric_evidence"]))
        L.append("")
    else:
        L.append("_No comparable observed/reported pair exists._\n")
    L.append("## 7. Difference attribution\n")
    if rec["attributions"]:
        table(["metric", "cause", "confidence", "detail"],
              [[a.get("metric"), a.get("cause"), a.get("confidence"), C.snip(a.get("detail"), 240)]
               for a in rec["attributions"]])
    else:
        L.append("_No attribution rows._\n")
    L.append("## 8. Evidence ledger\n")
    ev = [[c.get("id"), e.get("source_id"), e.get("locator"), C.snip(e.get("quote"), 90),
           "verified" if e.get("verified") else e.get("check")]
          for c in rec["claims"] for e in (c.get("evidence") or [])][:80]
    if ev:
        table(["claim", "source", "locator", "quote", "check"], ev)
    else:
        L.append("_No quoted evidence in the draft._\n")
    L.append("## 9. Gaps, degradations, handover\n")
    for label, items in (("gap", rec["gaps"]), ("degraded", rec["degradations"]),
                         ("needs human", rec["pending_human"])):
        L.append("\n".join("- %s: %s" % (label, x) for x in (items or ["(none)"])))
        L.append("")
    L.append("## 10. Graded conclusion\n")
    L.append("- tier **%s**" % rec["verdict"]["tier"])
    L.append("- rationale: %s" % rec["verdict"]["rationale"])
    L.append("- missing objects: %s" % (", ".join(rec["verdict"]["missing_objects"]) or "none"))
    L.append("- rule: %s" % rec["verdict"]["rule"])
    if rec["verdict"].get("verdict_conflict"):
        L.append("- conflict: %s" % rec["verdict"]["verdict_conflict"])
    L.append("")
    return "\n".join(L)


def do_build(a):
    inp, out, w = paths(a)
    case, cp, cerr = E.load_case(inp)
    cid = E.case_id_of(case)
    pre = E.shell(case, cid, "partial", t0=now())
    pre["summary"] = "build started; a legal partial result.json already exists"
    E.emit(out, pre)
    idx = E.index_of(inp, w, out)
    units = C.flat_units(idx)
    errs = [cerr] if cerr else []
    deg, pend, unc = [], [], []
    plan, perr = C.load_json(w / "tolerance_plan.json")
    rep = E.reported_values(case)
    plan = plan if isinstance(plan, dict) and plan.get("entries") else E.tolerance_plan(case, rep)
    raw, derr = C.load_json(w / "draft.json")
    d = raw if isinstance(raw, dict) else {}
    no_draft = not d
    if no_draft:
        deg += ["no_draft:deterministic_minimal_delivery"]
        pend.append("draft missing: parameter provenance, metric semantics and attribution wording are "
                    "script-minimal; write draft.json and rerun build")
    if derr and (w / "draft.json").exists():
        errs.append("draft_unreadable:%s" % derr)
    # reported values: draft (verified) > auto extraction
    for pv in d.get("paper_values") or []:
        if pv.get("metric") and isinstance(pv.get("value"), (int, float)):
            ok, hits, why = C.check_evidence(units, pv.get("evidence") or {})
            loc = (hits[0]["locator"] if hits else (pv.get("evidence") or {}).get("locator"))
            rep[str(pv["metric"])] = {"value": float(pv["value"]), "source": "draft.paper_values",
                                      "locator": loc, "quote": (pv.get("evidence") or {}).get("quote"),
                                      "basis": "draft_verified" if ok else "draft_quote_unverified",
                                      "verified": ok, "check": why}
            if not ok:
                deg.append("reported_value_quote_unverified:%s" % pv.get("metric"))
                unc.append("reported value for %s was not backed by a verified quote (%s); treated as "
                           "the baseline but flagged" % (pv.get("metric"), why))
    plan, materialized = lock_band(plan, list(rep.keys()), w)
    if materialized:
        log("[band] materialized %d metric entry(ies) before any run: %s"
            % (len(materialized), ", ".join(materialized[:8])))
    # candidates and execution
    cands = E.discover(inp, case, d)
    seed = None
    for src in (d, case):
        for k in ("seed", "random_seed", "SEED"):
            if isinstance(src, dict) and isinstance(src.get(k), (int, str)):
                seed = src[k]
                break
        if seed is not None:
            break
    envx = E.env_for(d, seed)
    runs = []
    if not cands:
        deg.append("no_candidate_found")
        pend.append("no candidate implementation located; run it by hand and fill runs[]")
    elif a.dry_run:
        deg.append("dry_run:no_execution")
        pend.append("build ran with --dry-run; no candidate was executed")
    else:
        for it in cands:
            remain = LIMIT - (time.time() - T0)
            if remain < 50:
                deg.append("run_skipped_deadline:" + it["name"])
                pend.append("candidate %s skipped: %ds left" % (it["name"], int(remain)))
                continue
            rec = E.run_one(it, inp, out, w, envx, min(a.timeout, max(20, int(remain - 40))), plan)
            runs.append(rec)
            if rec.get("error"):
                deg.append("run_error:%s:%s" % (rec["run_id"], str(rec["error"])[:60]))
                pend.append("candidate %s: %s (see %s)" % (rec["run_id"], rec.get("error"),
                                                           rec.get("log_path") or "work/runs"))
            elif not rec.get("metrics"):
                unc.append("candidate %s produced no parseable metric on stdout" % rec["run_id"])
    names = []
    for r in runs:
        for k in (r.get("metrics") or {}):
            if k not in names:
                names.append(k)
    for pv in d.get("paper_values") or []:
        if pv.get("metric") and str(pv["metric"]) not in names:
            names.append(str(pv["metric"]))
    if not rep and names:
        auto = E.auto_reported(names, idx)
        if auto:
            rep.update(auto)
            deg.append("reported_values_auto_extracted:%d" % len(auto))
            unc.append("reported values for %s were auto-extracted from materials, not confirmed by a "
                       "verified draft quote" % ", ".join(sorted(auto)))
    if not names:
        names = list(rep.keys())
    rows = E.compare(runs, rep, plan, names) if names else []
    if not rows:
        deg.append("no_comparison_rows")
    # draft params / claims
    params, claims, evid = [], [], []
    for p in d.get("params") or []:
        ok, hits, why = C.check_evidence(units, p.get("evidence") or {})
        params.append({"name": p.get("name"), "value": p.get("value"),
                       "class": p.get("class"), "source": p.get("source"),
                       "locator": hits[0]["locator"] if hits else (p.get("evidence") or {}).get("locator"),
                       "quote": C.snip((p.get("evidence") or {}).get("quote"), 200),
                       "conflict_note": p.get("conflict_note"),
                       "verified": ok, "check": why})
        if not ok and p.get("class") == "paper":
            unc.append("parameter %s is claimed paper-stated but its quote is not in the materials (%s)"
                       % (p.get("name"), why))
    for c in d.get("claims") or []:
        evs = []
        for ev in c.get("evidence") or []:
            ok, hits, why = C.check_evidence(units, ev)
            evs.append({"source_id": hits[0]["source_id"] if hits else ev.get("source_id"),
                        "locator": hits[0]["locator"] if hits else ev.get("locator"),
                        "quote": C.snip(ev.get("quote"), 240), "verified": ok, "check": why})
        claims.append({"id": c.get("id"), "kind": c.get("kind"), "text": c.get("text"),
                       "confidence": c.get("confidence"), "evidence": evs})
        evid += [dict(e, claim=c.get("id")) for e in evs if e["verified"]]
    cov = E.coverage(idx, d)
    scope = E.scope_flags(E.instruction(case, inp))
    if isinstance(d.get("scope"), dict):
        for k in ("synthetic_trial", "mentions_original_repo"):
            if isinstance(d["scope"].get(k), bool):
                scope[k] = d["scope"][k]
    verdict = E.verdict_for(rows, runs, cov, scope, d)
    attribs = E.attribute(rows, params, cov, runs)
    seen_cause = {(a.get("metric"), a.get("cause")) for a in attribs}
    for extra in d.get("attributions") or []:
        if isinstance(extra, dict) and (extra.get("cause") or extra.get("detail")):
            if (extra.get("metric"), extra.get("cause")) in seen_cause:
                continue
            attribs.append(dict(extra, source="draft"))
    if verdict.get("verdict_conflict"):
        deg.append("verdict_conflict:" + verdict["verdict_conflict"])
        unc.append(verdict["verdict_conflict"])
    for m in idx["materials"]:
        if m.get("quality") not in (None, "ok"):
            deg.append("material_quality:%s:%s" % (m["id"], m["quality"]))
        if m.get("kind") in ("image", "skipped", "zip", "pptx"):
            pend.append("material %s (%s) not content-parsed" % (m["id"], m["kind"]))
    checklist = [{"item": m["rel"], "kind": m["kind"], "status": m.get("quality"),
                  "locator": (m.get("units") or [[None]])[0][0] if m.get("units") else None,
                  "sha1": m.get("sha1")} for m in idx["materials"]]
    for item in d.get("checklist") or []:
        if isinstance(item, dict):
            checklist.append({"item": item.get("id") or item.get("item"),
                              "kind": item.get("kind"), "status": item.get("status"),
                              "locator": item.get("locator"), "note": item.get("note")})
    for cls, st in cov.items():
        if st["status"] == "missing":
            pend.append("required object class '%s' not located in the input" % cls)
        elif st["status"] == "needs_request":
            pend.append("required object class '%s' is not available: needs request (see checklist)"
                        % cls)
    env = d.get("environment") if isinstance(d.get("environment"), dict) else {}
    environment = {"python": env.get("python") or platform.python_version(),
                   "platform": env.get("platform") or platform.platform(),
                   "packages": env.get("packages") or {},
                   "seed": seed if seed is not None else env.get("seed"),
                   "hardware_note": env.get("hardware_note"),
                   "source": "draft+host" if env else "host_only"}
    if not env:
        deg.append("environment_from_host_only")
        unc.append("environment snapshot comes from the host; it is not matched against any paper claim")
    status = "ok"
    if cerr:
        status = "input_error"
    elif not runs:
        status = "insufficient_evidence"
    if status == "ok" and (deg or pend):
        status = "partial"
    tol_rows = [dict(v, metric=k) for k, v in (plan.get("entries") or {}).items()]
    counts = {"materials": len(idx["materials"]), "runs": len(runs),
              "runs_ok": sum(1 for r in runs if r.get("exit_code") == 0),
              "comparison_rows": len(rows),
              "in_tolerance": sum(1 for r in rows if r["within_tolerance"] is True),
              "out_of_tolerance": sum(1 for r in rows if r["within_tolerance"] is False),
              "no_reported_value": sum(1 for r in rows if r["within_tolerance"] is None),
              "evidence_verified": sum(1 for c in claims for e in c["evidence"] if e["verified"]),
              "params": len(params), "attributions": len(attribs)}
    md = render_md({"case_id": cid, "generated_at": now(), "status": status,
                    "verdict": verdict, "scope_text": E.instruction(case, inp),
                    "materials": idx["materials"], "coverage": cov, "params": params,
                    "tolerance_plan": plan, "runs": runs, "comparison": rows,
                    "attributions": attribs, "claims": claims, "gaps": pend, "degradations": deg,
                    "pending_human": pend, "environment": environment})
    C.write_text(out / "repro_report.md", md)
    C.write_csv(out / "comparison.csv",
                ["run", "metric", "observed", "reported", "abs_dev", "rel_dev", "call",
                 "abs_tol", "rel_tol", "tolerance_basis", "reported_locator", "run_log"],
                [[r["run"], r["metric"], r["observed"], r["reported"], r["abs_dev"], r["rel_dev"],
                  r["verdict"], r["abs_tol"], r["rel_tol"], r["tolerance_basis"],
                  r.get("reported_locator"), r.get("run_log")] for r in rows])
    C.write_csv(out / "param_table.csv",
                ["param", "value", "class", "locator", "verified", "conflict_note"],
                [[p["name"], p["value"], p["class"], p["locator"], p["verified"],
                  p["conflict_note"]] for p in params])
    C.write_csv(out / "attribution.csv", ["metric", "cause", "confidence", "detail"],
                [[a.get("metric"), a.get("cause"), a.get("confidence"), a.get("detail")]
                 for a in attribs])
    dump(out / "tolerance.json", plan)
    sources = [{k: m.get(k) for k in ("id", "rel", "kind", "bytes", "sha1")} for m in idx["materials"]]
    runtime = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(T0)),
               "finished_at": now(), "elapsed_s": round(time.time() - T0, 2),
               "budget_s": LIMIT, "deadline_hit": time.time() - T0 > LIMIT}
    rec = {"case_id": cid, "status": status,
           "summary": "verdict %s; %d run(s), %d comparison row(s) (in %d / out %d / n.a. %d)"
                      % (verdict["tier"], len(runs), len(rows), counts["in_tolerance"],
                         counts["out_of_tolerance"], counts["no_reported_value"]),
           "generated_at": now(), "scope_text": C.snip(E.instruction(case, inp), 700),
           "scope": scope, "paper": d.get("paper") or {}, "materials": idx["materials"],
           "coverage": cov, "environment": environment, "tolerance_plan": plan, "tolerance": tol_rows,
           "params": params, "plan": d.get("plan") or [], "runs": runs, "comparison": rows,
           "attributions": attribs, "claims": claims, "evidence": evid, "verdict": verdict,
           "checklist": checklist, "sources": sources, "gaps": sorted(set(pend)),
           "degradations": sorted(set(deg)), "errors": errs, "uncertainty": sorted(set(unc)),
           "pending_human": sorted(set(pend)), "counts": counts,
           "artifacts": {"result_json": str(out / "result.json"),
                         "report": str(out / "repro_report.md"),
                         "comparison_csv": str(out / "comparison.csv"),
                         "param_table_csv": str(out / "param_table.csv"),
                         "attribution_csv": str(out / "attribution.csv"),
                         "tolerance_json": str(out / "tolerance.json"),
                         "runs_dir": str(out / "runs"), "work_dir": str(w)},
           "changes": [{"at": plan.get("declared_at"),
                        "change": "init locked %d tolerance entries" % len(tol_rows)},
                       {"at": plan.get("materialized_at"),
                        "change": "band materialized for %s before any run"
                                  % (", ".join(plan.get("materialized") or []) or "-")},
                       {"at": now(), "change": "build executed %d candidate(s) and finalized the record"
                                               % len(runs)}],
           "runtime": runtime}
    dump(out / "repro_record.json", rec)
    con = E.contract_of(case)
    un = []
    stacked = dict(rec, record=rec, report_markdown=md, comparison_csv=str(out / "comparison.csv"),
                   tolerance=tol_rows, attributions=attribs, checklist=checklist, gaps=rec["gaps"],
                   summary=rec["summary"], verdict=verdict, status=status)
    res = dict(rec)
    if con:
        filled = C.echo_contract(con, stacked, un)
        if isinstance(filled, dict):
            res.update(filled)
        else:
            res["_contract_shape"] = filled
    if un:
        res["degradations"] = sorted(set(res["degradations"]) |
                                     {"contract_field_unmapped:" + ",".join(sorted(set(un)))})
    E.emit(out, res)
    log("== build ==")
    log("runs %d (ok %d) | rows %d (in %d / out %d / n.a. %d)"
        % (len(runs), counts["runs_ok"], len(rows), counts["in_tolerance"],
           counts["out_of_tolerance"], counts["no_reported_value"]))
    for r in runs:
        log("  %-20s exit=%s %5sms metrics=%d %s" % (r["run_id"], r.get("exit_code"),
                                                     r.get("duration_ms"),
                                                     len(r.get("metrics") or {}),
                                                     r.get("error") or ""))
    for r in rows[:24]:
        log("  %-16s %-18s obs=%-12s rep=%-10s rel=%-9s %s"
            % (r["run"], r["metric"], r["observed"], r["reported"], r["rel_dev"], r["verdict"]))
    log("verdict %s | status %s | contract %d/%d mapped"
        % (verdict["tier"], status, len(C.contract_keys(con)) - len(set(un)),
           len(C.contract_keys(con))))
    log("result.json -> %s\nreport -> %s" % (out / "result.json", out / "repro_report.md"))




def lock_band(plan, names, wrk):
    """Materialise one band entry per metric BEFORE any subprocess starts.
    Entries inherit the wildcard prior (or a case-declared band) and are stamped,
    then the plan hash is recomputed and persisted so every run can record it."""
    ent = plan.setdefault("entries", {})
    dflt = ent.get("__default__") or C.prior_entry(None)
    added = []
    for n in names:
        if any(k != "__default__" and C.metric_match(k, n)[0] for k in ent):
            continue
        e = {k: v for k, v in dflt.items() if k not in ("basis",)}
        e["basis"] = (dflt.get("basis") or "prior_default")
        e["declared_step"] = "build:pre_run"
        ent[n] = e
        added.append(n)
    if added:
        plan["plan_sha256"] = C.sha256_obj(ent)
        plan["materialized"] = sorted(set(plan.get("materialized") or []) | set(added))
        plan["materialized_at"] = now()
        dump(wrk / "tolerance_plan.json", plan)
    return plan, added


def paths(ns):
    """Import the path resolver from main so both entry points agree exactly."""
    import main as M
    return M.paths(ns)
