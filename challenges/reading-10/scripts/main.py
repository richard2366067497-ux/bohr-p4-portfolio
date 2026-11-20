#!/usr/bin/env python3
"""main.py -- repro-metric-crosscheck CLI: init | show | check | build | selfcheck.

Five-command main path (the agent is the answerer, the script is the assistant):
  init      index /input, lock the tolerance band, write a legal partial result.json FIRST
  show      replay located text so quotes can be copied verbatim
  check     mechanical gate over /app/work/draft.json
  build     really run the candidate methods, compare under the locked band, attribute, finalize
  selfcheck read-only audit of what is already on disk

Standard library only, no network, CWD independent, exit code always 0.
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
import core as C  # noqa: E402
import engine as E  # noqa: E402
from build import do_build  # noqa: E402

T0 = time.time()
LIMIT = 760
SLOTS = ("status", "summary", "record", "comparison", "tolerance", "attributions", "runs",
         "params", "environment", "checklist", "evidence", "verdict", "uncertainty",
         "pending_human", "gaps", "plan", "claims", "report_markdown", "comparison_csv", "sources")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log(s=""):
    print(s, flush=True)


def paths(ns):
    i = Path(getattr(ns, "input", None) or os.environ.get("SCIM_INPUT") or "/input")
    if not i.is_dir():
        for cand in (Path.cwd() / "input", Path("/bohr-workspace/input"), Path.cwd().parent / "input"):
            if cand.is_dir():
                i = cand
                break
    o = Path(getattr(ns, "output", None) or os.environ.get("SCIM_OUTPUT") or "/app/output")
    w = Path(getattr(ns, "work", None) or os.environ.get("SCIM_WORK") or "/app/work")
    for d in (o, w, o / "runs"):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    if not os.access(str(o), os.W_OK):
        o = Path.cwd() / "output"
        (o / "runs").mkdir(parents=True, exist_ok=True)
    return i, o, w


def skeleton(case, cid, idx):
    """Empty-but-complete draft the agent copies to /app/work/draft.json."""
    names = [c["name"] for c in E.discover(Path(idx["root"]), case, {})]
    return {"_note": "skeleton only, not a case answer; copy to draft.json and fill what you read",
            "case_id": cid,
            "paper": {"title": None, "doi": None, "repo": None, "commit": None, "data_version": None},
            "scope": {"synthetic_trial": None, "not_original_repo": None},
            "plan": [{"step": 1, "goal": "locate materials", "command": None, "expected": None,
                      "status": "pending"}],
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "packages": {}, "seed": None},
            "params": [{"name": "", "value": None, "class": "paper", "source": "",
                        "conflict_note": None,
                        "evidence": {"source_id": "", "locator": "", "quote": ""}}],
            "paper_values": [{"metric": "", "value": None, "unit": None,
                              "evidence": {"source_id": "", "locator": "", "quote": ""}}],
            "tolerance": [{"metric": "", "abs_tol": None, "rel_tol": None, "basis": ""}],
            "claims": [{"id": "c1", "kind": "paper_result", "text": "",
                        "confidence": "direct",
                        "evidence": [{"source_id": "", "locator": "", "quote": ""}]}],
            "attributions": [{"metric": "", "cause": "", "confidence": "inferred",
                              "evidence": "", "disposition": ""}],
            "checklist": [{"id": "", "kind": "code", "status": "available", "note": ""}],
            "candidates": [{"name": n, "path": n} for n in names],
            "verdict": {"tier": "partially_reproduced", "rationale": ""}}


def dump(path, obj):
    return C.dump_json(path, obj)


# ------------------------------------------------------------------- init
def do_init(a):
    inp, out, w = paths(a)
    case, cp, cerr = E.load_case(inp)
    cid = E.case_id_of(case)
    pre = E.shell(case, cid, "partial", t0=now())
    pre["summary"] = "init: legal placeholder written before any work"
    E.emit(out, pre)
    idx = E.build_index(inp, (out, w))
    rep = E.reported_values(case)
    plan = E.tolerance_plan(case, rep)
    dump(w / "index.json", idx)
    dump(w / "tolerance_plan.json", plan)
    dump(w / "draft_skeleton.json", skeleton(case, cid, idx))
    cov = E.coverage(idx, {})
    scope = E.scope_flags(E.instruction(case, inp))
    con = E.contract_of(case)
    keys = C.contract_keys(con)
    cands = E.discover(inp, case, {})
    units = C.flat_units(idx)
    log("== init ==")
    log("input=%s\nwork=%s\noutput=%s\ncase=%s parse=%s\ncase_id=%s contract_keys=%d"
        % (inp, w, out, cp, "ok" if not cerr else cerr, cid, len(keys)))
    if keys:
        log("contract: " + ", ".join(str(k) for k in keys))
    log("\n[materials] %d  units %d" % (len(idx["materials"]), len(units)))
    for m in idx["materials"]:
        log("  %-18s %-9s %7dB units=%-4d %-10s %s"
            % (m["id"], m["kind"], m["bytes"], len(m.get("units") or []), m.get("quality"),
               C.snip(m["rel"], 60)))
    log("\n[coverage] " + "  ".join("%s=%s" % (k, v["status"]) for k, v in cov.items()))
    log("[candidates] " + (", ".join("%s<%s>" % (c["name"], (c["rel_path"] or c.get("command") or "?"))
                                     for c in cands) or "none found"))
    log("[scope] synthetic_trial=%s mentions_original_repo=%s"
        % (scope["synthetic_trial"], scope["mentions_original_repo"]))
    log("\n[tolerance] %d entries, before_any_run=%s, source=%s, plan_sha256=%s"
        % (len(plan["entries"]), plan["before_any_run"], plan["source"], plan["plan_sha256"][:16]))
    for k, e in list(plan["entries"].items())[:8]:
        log("  %-22s abs=%s rel=%s frac=%s [%s]" % (k, e.get("abs_tol"), e.get("rel_tol"),
                                                    e.get("abs_frac"), e.get("basis")))
    if rep:
        log("[reported values from case.json] " + ", ".join(
            "%s=%s(%s)" % (k, v["value"], v["ptr"]) for k, v in list(rep.items())[:10]))
    log("\n[units preview]")
    for u in units[:a.preview]:
        log("  %s | %s" % (u["locator"], C.snip(u["text"], 110)))
    res = E.shell(case, cid, "input_error" if cerr else "partial", t0=now())
    res.update(
        summary="init: %d materials / %d units; tolerance locked before any run (%d entries)"
                % (len(idx["materials"]), len(units), len(plan["entries"])),
        sources=[{k: m.get(k) for k in ("id", "rel", "kind", "bytes", "quality", "sha1")}
                 for m in idx["materials"]],
        pending_human=["read show output, write %s, then run check and build" % (w / "draft.json")],
        degradations=["partial_written_at_init"],
        changes=[{"at": now(), "change": "init indexed materials and locked the tolerance band"}])
    if cerr:
        res["errors"] = [cerr]
    if not idx["materials"]:
        res["degradations"].append("no_material_found")
    E.emit(out, res)
    log("\n[next] 1) show --id MAT --grep KEY    2) write %s\n"
        "       3) check                       4) build" % (w / "draft.json"))


# ------------------------------------------------------------------- show
def do_show(a):
    inp, out, w = paths(a)
    idx = E.index_of(inp, w, out)
    if a.case:
        case, cp, cerr = E.load_case(inp)
        log("case.json: %s (%s)" % (cp, "ok" if not cerr else cerr))
        for k, v in (case or {}).items():
            if k == "output_contract":
                log("  output_contract: %s" % json.dumps(v, ensure_ascii=False)[:900])
            else:
                log("  %-22s %s" % (k, C.snip(json.dumps(v, ensure_ascii=False) if
                                               isinstance(v, (dict, list)) else str(v), 400)))
        log("\n[task instruction]\n" + C.snip(E.instruction(case, inp), 1600))
        return
    if a.stats:
        for m in idx["materials"]:
            log("%-18s %-9s units=%-4d %s" % (m["id"], m["kind"], len(m.get("units") or []), m["rel"]))
        return
    seen, n = set(), 0
    for m in idx["materials"]:
        if a.id and a.id not in (m["id"], m["rel"]) and a.id not in Path(m["rel"]).name:
            continue
        for loc, txt in m.get("units") or []:
            if a.grep and a.grep.casefold() not in txt.casefold():
                continue
            n += 1
            if n > a.limit:
                log("... --limit=%d reached" % a.limit)
                return
            log("%s | %s" % (loc, txt[:a.chars] if a.chars else txt))
            seen.add(m["id"])
    log("\nprinted %d unit(s) from %d material(s)" % (n, len(seen)) if n else
        "no unit matched; try --stats for the inventory, or --id <material id>")


# ------------------------------------------------------------------ check
def do_check(a):
    inp, out, w = paths(a)
    case, cp, cerr = E.load_case(inp)
    cid = E.case_id_of(case)
    idx = E.index_of(inp, w, out)
    units = C.flat_units(idx)
    plan, _ = C.load_json(w / "tolerance_plan.json")
    plan = plan if isinstance(plan, dict) else {"entries": {}}
    draft, derr = C.load_json(w / "draft.json")
    d = draft if isinstance(draft, dict) else {}
    errs, warns, okn, rej, wide = [], [], 0, 0, 0
    if not d:
        errs.append("draft_missing:%s%s" % (w / "draft.json", "" if derr is None else " (%s)" % derr))
    for k in ("paper", "plan", "params", "claims", "verdict"):
        if not d.get(k):
            (warns if k in ("paper", "plan") else errs).append("draft_section_empty:" + k)
    for c in d.get("claims") or []:
        i = str(c.get("id") or "?")
        if not str(c.get("text") or "").strip():
            errs.append("claim_text_empty:" + i)
        if c.get("confidence") not in ("direct", "inferred", "undetermined"):
            errs.append("claim_confidence_invalid:" + i)
        evs = c.get("evidence") or []
        if not evs:
            errs.append("claim_without_evidence:" + i)
        for ev in evs:
            ok, hits, why = C.check_evidence(units, ev)
            okn, rej = okn + (1 if ok else 0), rej + (0 if ok else 1)
            if not ok:
                errs.append("evidence_rejected:%s:%s:%s" % (i, why, C.snip(str(ev.get("quote")), 60)))
            elif why == "locator_rebound":
                warns.append("locator_rebound:%s->%s" % (i, hits[0]["locator"]))
    for p in d.get("params") or []:
        nm = p.get("name")
        if p.get("class") not in ("paper", "code_inferred", "self_set", "chosen"):
            errs.append("param_class_invalid:%s" % nm)
        if p.get("value") in (None, ""):
            warns.append("param_value_empty:%s" % nm)
        if p.get("class") == "paper":
            ok, hits, why = C.check_evidence(units, p.get("evidence") or {})
            okn, rej = okn + (1 if ok else 0), rej + (0 if ok else 1)
            if not ok:
                errs.append("paper_param_without_verified_quote:%s:%s" % (nm, why))
    for pv in d.get("paper_values") or []:
        if not isinstance(pv.get("value"), (int, float)):
            errs.append("paper_value_not_numeric:%s" % pv.get("metric"))
        ok, hits, why = C.check_evidence(units, pv.get("evidence") or {})
        okn, rej = okn + (1 if ok else 0), rej + (0 if ok else 1)
        if not ok:
            errs.append("paper_value_quote_rejected:%s:%s" % (pv.get("metric"), why))
    entries = plan.get("entries") or {}
    for t in d.get("tolerance") or []:
        base = None
        for k, e in entries.items():
            if k != "__default__" and C.metric_match(k, t.get("metric"))[0]:
                base = e
                break
        base = base or entries.get("__default__")
        if not base:
            warns.append("tolerance_not_predeclared:%s" % t.get("metric"))
            continue
        for f in ("abs_tol", "rel_tol"):
            dv = t.get(f)
            if f == "abs_tol" and isinstance(base.get("abs_frac"), (int, float)):
                continue
            pv = base.get(f)
            if isinstance(dv, (int, float)) and isinstance(pv, (int, float)) and dv > pv * (1 + 1e-9):
                wide += 1
                errs.append("tolerance_widened_after_run:%s:%s>%s" % (t.get("metric"), dv, pv))
    cands = E.discover(inp, case, d)
    cov = E.coverage(idx, d)
    stages = [("materials", len(idx["materials"]) > 0),
              ("environment", bool(d.get("environment"))),
              ("params", bool(d.get("params"))),
              ("runs", len(cands) > 0),
              ("comparison", bool(d.get("paper_values")) or bool(E.reported_values(case))),
              ("attribution", bool(d.get("attributions"))),
              ("verdict", (d.get("verdict") or {}).get("tier") in E.TIERS)]
    gaps = [s for s, ok in stages if not ok]
    con = E.contract_of(case)
    keys = C.contract_keys(con)
    mapped = [k for k in keys if C._slot_for(k) is not None]
    cnt = dict(claims=len(d.get("claims") or []), evidence_ok=okn, evidence_rejected=rej,
               params=len(d.get("params") or []), paper_values=len(d.get("paper_values") or []),
               tolerance_entries=len(d.get("tolerance") or []), tolerance_widened=wide,
               candidates=len(cands), contract_keys=len(keys), contract_mapped=len(mapped))
    dump(w / "check_report.json", {"draft": str(w / "draft.json"), "errors": errs, "warnings": warns,
                                   "counts": cnt, "stages": dict(stages), "gaps": gaps,
                                   "coverage": cov, "pass": not errs})
    log("== check %s ==" % ("PASS" if not errs else "FAIL"))
    log("claims=%(claims)d evidence_ok=%(evidence_ok)d rejected=%(evidence_rejected)d "
        "params=%(params)d paper_values=%(paper_values)d tol=%(tolerance_entries)d "
        "widened=%(tolerance_widened)d candidates=%(candidates)d contract=%(contract_mapped)d/%(contract_keys)d"
        % cnt)
    log("stages: " + "  ".join("%s=%s" % (k, "ok" if v else "GAP") for k, v in stages))
    for e in errs[:30]:
        log("  ERROR " + e)
    for x in warns[:20]:
        log("  WARN  " + x)
    if not mapped and keys:
        log("  WARN  no output_contract key could be mapped; keys land as null with degradations")
    log("report: %s" % (w / "check_report.json"))
    if gaps:
        log("hint: fill the GAP stages in draft.json and rerun check before build")


# ------------------------------------------------------------------ build
# -------------------------------------------------------------- selfcheck
def do_selfcheck(a):
    inp, out, w = paths(a)
    case, cp, cerr = E.load_case(inp)
    con = E.contract_of(case)
    res, rerr = C.load_json(out / "result.json")
    checks, fails = [], []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            fails.append(name)

    chk("result_json_present", isinstance(res, dict), rerr or "")
    res = res if isinstance(res, dict) else {}
    keys = C.contract_keys(con)
    missing = [k for k in keys if k not in res]
    chk("contract_keys_present", not missing, ",".join(missing[:8]))
    chk("envelope_fields", all(k in res for k in E.SENTINEL),
        ",".join(k for k in E.SENTINEL if k not in res))
    chk("status_enum", res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"),
        str(res.get("status")))
    want = E.case_id_of(case)
    chk("case_id_matches", (want is None) or (res.get("case_id") == want),
        "%s != %s" % (res.get("case_id"), want))
    rows = res.get("comparison") or []
    rows_ok = (all(r.get("abs_tol") is not None or r.get("rel_tol") is not None for r in rows)
               if rows else "no_comparison_rows" in (res.get("degradations") or []))
    chk("comparison_rows_have_band", rows_ok, "%d rows" % len(rows))
    runs = res.get("runs") or []
    bad_logs = [r.get("run_id") for r in runs
                if not (r.get("argv") and r.get("exit_code") is not None and r.get("duration_ms") is not None
                        and r.get("log_path") and Path(str(r.get("log_path"))).is_file())]
    chk("runs_verifiable", not bad_logs, ",".join(map(str, bad_logs[:5])))
    plan, _ = C.load_json(w / "tolerance_plan.json")
    plan = plan if isinstance(plan, dict) else {}
    sha = C.sha256_obj(plan.get("entries") or {})
    chk("tolerance_plan_intact", plan.get("plan_sha256") == sha,
        "plan=%s recomputed=%s" % (str(plan.get("plan_sha256"))[:12], sha[:12]))
    mism = [r.get("run_id") for r in runs
            if r.get("tolerance_plan_sha256") and r.get("tolerance_plan_sha256") != sha]
    chk("band_predeclared_before_runs", not mism and plan.get("before_any_run") is True,
        ",".join(map(str, mism[:5])))
    v = res.get("verdict") or {}
    chk("verdict_coherent", v.get("tier") in E.TIERS and (
        res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error")),
        str(v.get("tier")))
    att = res.get("attributions") or []
    chk("attributions_evidenced", all(a.get("cause") and a.get("evidence") is not None for a in att),
        "%d rows" % len(att))
    arts = ["repro_report.md", "comparison.csv", "param_table.csv", "attribution.csv"]
    empty = [f for f in arts if not (out / f).is_file() or (out / f).stat().st_size < 20]
    chk("artifacts_non_empty", not empty, ",".join(empty))
    dump(out / "selfcheck.json", {"checks": checks, "pass": not fails, "fails": fails,
                                  "at": now()})
    log("== selfcheck %s (%d/%d) ==" % ("PASS" if not fails else "FAIL",
                                        len(checks) - len(fails), len(checks)))
    for c in checks:
        log("  [%s] %-28s %s" % ("ok" if c["ok"] else "!!", c["check"], c["detail"]))
    for x in fails:
        log("  FAIL " + x)
    log("report: %s" % (out / "selfcheck.json"))


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="repro-metric-crosscheck: run candidate methods for real, compare under a "
                    "tolerance band locked before the run, attribute, grade. exit code is always 0.",
        epilog="main path: init -> show -> (agent writes draft.json) -> check -> build -> selfcheck")
    sp = ap.add_subparsers(dest="cmd")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", help="input dir (default /input, env SCIM_INPUT)")
    common.add_argument("--output", help="output dir (default /app/output, env SCIM_OUTPUT)")
    common.add_argument("--work", help="work dir (default /app/work, env SCIM_WORK)")
    p = sp.add_parser("init", parents=[common], help="index, lock the band, write partial result.json")
    p.add_argument("--preview", type=int, default=12)
    p = sp.add_parser("show", parents=[common], help="print located text / case / inventory")
    p.add_argument("--id", help="material id or file name")
    p.add_argument("--grep", help="case-insensitive substring filter")
    p.add_argument("--limit", type=int, default=80)
    p.add_argument("--chars", type=int, default=700)
    p.add_argument("--case", action="store_true", help="dump case.json keys and the task instruction")
    p.add_argument("--stats", action="store_true", help="material inventory only")
    sp.add_parser("check", parents=[common], help="validate the draft: fields, quotes, band")
    p = sp.add_parser("build", parents=[common], help="run candidates, compare, attribute, finalize")
    p.add_argument("--timeout", type=int, default=120, help="per-run timeout in seconds")
    p.add_argument("--dry-run", action="store_true", help="assemble artifacts without executing")
    sp.add_parser("selfcheck", parents=[common], help="read-only audit of the artifacts")
    a = ap.parse_args()
    if not a.cmd:
        a.cmd = "init"
        a.preview = 12
    {"init": do_init, "show": do_show, "check": do_check, "build": do_build,
     "selfcheck": do_selfcheck}.get(a.cmd, do_show)(a)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        try:
            ns = argparse.Namespace()
            for kv in sys.argv[1:]:
                if kv.startswith("--") and "=" in kv:
                    k, v = kv[2:].split("=", 1)
                    setattr(ns, k.replace("-", "_"), v)
            inp, out, w = paths(ns)
            case, cp, err = E.load_case(inp)
            res = E.shell(case, E.case_id_of(case), "partial", t0=now())
            res.update(status="partial", summary="unhandled exception; partial result written",
                       errors=[C.snip(traceback.format_exc(), 1400)],
                       degradations=["unhandled_exception"])
            E.emit(out, res)
            sys.stderr.write("fatal: partial result.json written\n")
        except Exception:
            pass
    sys.exit(0)
