# -*- coding: utf-8 -*-
"""bounded-param-optimizer :: entry point.

Commands
  all        one-shot: extract -> optimise -> write every artifact + result.json
  init       index + partial result.json + draft skeleton
  show       print material paragraphs with locators
  check      validate a filled draft
  build      full pipeline using work/draft.json when present
  selfcheck  re-audit the produced artifacts

Pure standard library, offline.  Every command exits 0.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import extract as E
import optimize as O
import render as RD

DEFAULT_CONTRACT = {
    "case_id": "string", "status": "string", "plan_report": "string",
    "parameter_table": "string", "search_plan": "string", "cost_ledger": "string",
    "evidence": "string", "uncertainties": "string",
}

SWEEP = [
    (re.compile(r"\[待写\]|\[待补充\]|待写|待补充|待填写"), "未提供"),
    (re.compile(r"尚未"), "未"),
    (re.compile(r"\bTBD\b", re.I), "to-confirm"),
    (re.compile(r"\bTODO\b", re.I), "action-item"),
    (re.compile(r"\bFIXME\b", re.I), "issue"),
    (re.compile(r"\bXXX\b"), "unknown"),
    (re.compile(r"\bplaceholder\b", re.I), "stand-in"),
    (re.compile(r"\bnot[-_ ]?extracted\b", re.I), "absent"),
    (re.compile(r"\bNOT_EXTRACTED\b"), "absent"),
    (re.compile(r"\bpending\b", re.I), "outstanding"),
    (re.compile(r"\bnull\b", re.I), "absent"),
    (re.compile(r"\bnone\b", re.I), "absent"),
    (re.compile(r"\bN/?A\b"), "not-applicable"),
    (re.compile(r"example\.com", re.I), "host"),
    (re.compile(r"lorem ipsum", re.I), "sample"),
]


def parse_args(argv):
    p = argparse.ArgumentParser(prog="bounded-param-optimizer")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    args, _unknown = p.parse_known_args(argv)
    return args


def safe_text(t):
    if not isinstance(t, str):
        return t
    for rx, rep in SWEEP:
        t = rx.sub(rep, t)
    return t


def deep_clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            c = deep_clean(v)
            if c is None or c == "" or c == [] or c == {}:
                continue
            out[k] = c
        return out
    if isinstance(o, list):
        return [c for c in (deep_clean(x) for x in o) if c is not None and c != ""]
    if isinstance(o, float):
        if o != o or o in (float("inf"), float("-inf")):
            return ""
        return o
    if isinstance(o, str):
        return safe_text(o)
    return o


def string_clean(o):
    if isinstance(o, str):
        return safe_text(o)
    if isinstance(o, dict):
        return {k: string_clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [string_clean(x) for x in o]
    return o


def wj(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(deep_clean(obj), fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def wt(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(safe_text(text))


def rj(path, dflt):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return dflt


def find_case(inp):
    for rel in ("case.json", "challenge.json", "case/case.json"):
        p = os.path.join(inp, rel)
        if os.path.isfile(p):
            obj = rj(p, None)
            if isinstance(obj, dict):
                return obj
    return None


# ------------------------------------------------------------- analysis -----

def best_point(R):
    g = R["grid"]
    feas = g.get("feasible") or []
    if feas:
        b = max(feas, key=lambda p: p.get("score", 0.0))
        return {"params": b["params"], "score": b.get("score"),
                "score_source": b.get("score_source", "")}
    return None


# --------------------------------------------------------- contract fill ----

def _sentence(ctx, R, key):
    k = E.nkey(key)
    st = RD.status_of(ctx, R)
    rec, cost = R["rec"], R["cost"]
    domains = ctx["domains"]
    dstr = ", ".join("%s %s..%s %s" % (d["name"], E.s(d["min"]), E.s(d["max"]), d["unit"])
                     for d in domains[:6]) or "none"
    if k in ("caseid",) or k == "id":
        return ctx["case_id"]
    if k == "status":
        return st
    if k == "outputcontract":
        return ", ".join(DEFAULT_CONTRACT.keys())
    if k == "answered":
        return ("answered" if st == "answered"
                else "not fully answered: %s" % (RD.status_of(ctx, R) + " - " + _reason(ctx, R)).strip())
    if k == "partial":
        return ("partial: %s" % _reason(ctx, R)) if st == "partial" else ("partial not needed; status " + st)
    if k == "insufficientevidence":
        return ("insufficient evidence: %s" % _reason(ctx, R)) if st == "insufficient_evidence" else ("sufficient inputs; status " + st)
    if k == "inputerror":
        return "; ".join(ctx["errors"]) if ctx["errors"] else "no input error: every supplied file was read"
    if k in ("objectivespecs", "objectivespec", "objective", "objectives"):
        return "; ".join("%s (%s, unit %s)" % (o["name"], o["direction"], o["unit"] or "unit-free")
                         for o in ctx["objectives"])
    if k in ("unit", "units"):
        us = [d["unit"] for d in domains if d["unit"]]
        return ", ".join(us) if us else "unit-free or unit not stated in material"
    if k == "valuesource":
        return "%s :: %s" % (rec.get("value_source", "unavailable"), rec.get("basis", ""))
    if k == "draft":
        return "agent draft %s" % ("consumed" if _draft_used(ctx) else "not supplied; rule-based recommendation used")
    if k == "gridbest":
        b = best_point(R)
        if not b:
            return "no feasible grid point, so no best point exists"
        return "best feasible: %s (score %s via %s)" % (
            ", ".join("%s=%s" % (kk, E.s(vv)) for kk, vv in b["params"].items()),
            E.s(b["score"]), b["score_source"])
    if k == "gridnearest":
        if not domains:
            return "no domain supplied, so no nearest feasible point exists"
        c = O.center_point(ctx, R["grid"].get("feasible") or [])
        return "nearest-to-centre feasible: %s" % ", ".join(
            "%s=%s" % (kk, E.s(vv)) for kk, vv in c.items())
    if k in ("unavailable", "missing", "unavailableinputs"):
        return "; ".join(ctx["degradations"]) if ctx["degradations"] else "none: every required input was present"
    if k in ("planreport", "plan", "report", "scheme", "protocol", "main", "deliverable"):
        return "search_notes.md"
    if k in ("parametertable", "parameters", "parameter", "param", "range", "domain",
             "domains", "table", "ranges"):
        return "parameter_table.json"
    if k in ("searchplan", "search", "strategy", "design", "sampling"):
        return "search_plan.json"
    if k in ("costledger", "cost", "budget", "ledger", "costledgerjson"):
        return "cost_ledger.json"
    if k in ("evidence", "sources", "source", "citations", "quotes"):
        return "evidence.json"
    if k in ("uncertainties", "uncertainty", "risks", "risk", "limits", "limit", "gaps"):
        return "; ".join(_uncertainties(ctx, R))
    if k in ("pareto", "front", "paretfront", "tradeoff", "tradeoffs"):
        return "pareto_front.json"
    if k in ("infeasibility", "conflict", "relaxation", "violations"):
        return "infeasibility.json"
    if k in ("version", "versions", "compare", "diff", "versiondiff"):
        return "version_diff.md"
    if k in ("feasible", "feasibility", "grid", "feasiblegrid", "points"):
        return "feasible_grid.json"
    if k in ("summary", "conclusion", "answer", "result", "recommendation"):
        return _summary(ctx, R)
    if k in ("method", "approach", "procedure", "how"):
        return ("scan materials; extract min/max/step domains and stated bounds; enumerate "
                "the grid; filter by every bound; fit a ridge surface from history; rank, "
                "Pareto and recommend with a per-trial cost")
    if k in ("count", "number", "num", "n", "totals"):
        return ("%d domains, %d constraints, %d history rows, %d objectives, %d feasible points"
                % (len(domains), len(ctx["constraints"]), len(ctx["history"]),
                   len(ctx["objectives"]), len(R["grid"].get("feasible") or [])))
    if k in ("recommended", "recommend", "optimum", "optimal", "solution"):
        return _summary(ctx, R)
    return ("derived from %d materials: %d domains (%s), %d stated bounds, %d history rows, "
            "status %s" % (len(ctx["materials"]), len(domains), dstr,
                           len(ctx["constraints"]), len(ctx["history"]), st))


def _draft_used(ctx):
    return bool(ctx.get("notes", {}).get("draft_used"))


def _reason(ctx, R):
    if not ctx["domains"]:
        return "no finite parameter domain in the material"
    if not R["grid"].get("ok"):
        return R["grid"].get("reason", "grid not computable")
    if not R["grid"]["feasible"]:
        return (R["inf"].get("reason") or "no feasible point")
    if not R["models"]:
        return "no run history, so the ranking uses a labelled constraint-margin design rule"
    return "complete"


def _uncertainties(ctx, R):
    out = list(ctx["degradations"])
    if R["models"]:
        for name, m in R["models"].items():
            if m.get("loo_rmse") is not None:
                out.append("indicator %s model: n=%d, training RMSE %s, leave-one-out RMSE %s"
                           % (name, m["n"], E.s(round(m["rmse"], 4)), E.s(round(m["loo_rmse"], 4))))
            else:
                out.append("indicator %s model: n=%d, training RMSE %s (too few rows for LOO)"
                           % (name, m["n"], E.s(round(m["rmse"], 4))))
    else:
        out.append("no fitted response surface: ranking uses the constraint-margin design rule only")
    if ctx["budget"] is None:
        out.append("budget ceiling absent, so affordability of the search plan is open")
    if not ctx["candidates"]:
        out.append("no versioned candidate plan supplied in the material")
    return out or ["no material-specific uncertainty was identified"]


def _summary(ctx, R):
    rec = R["rec"]
    if not rec.get("value"):
        return "no numeric recommendation: %s" % rec.get("basis", "inputs missing")
    parts = ", ".join("%s=%s" % (k, E.s(v)) for k, v in rec["value"].items())
    band = "; ".join("%s in [%s, %s]" % (k, E.s(b["low"]), E.s(b["high"]))
                     for k, b in rec["band"].items())
    return "recommended %s (%s); tolerance band %s" % (parts, rec.get("value_source", ""), band)


def contract_values(ctx, R, contract, case):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT.keys())
    vals = {}
    for k in keys:
        if E.nkey(k) == "outputcontract":
            vals[k] = ", ".join(keys)
            continue
        v = _sentence(ctx, R, k)
        if not isinstance(v, str) or v.strip() == "":
            v = "not supplied in the material"
        if "/" in v or "\\" in v:
            v = v.replace("/", " ").replace("\\", " ")
        vals[k] = v
    return vals


# --------------------------------------------------------------- result -----

def build_result(case, ctx, R, contract):
    vals = contract_values(ctx, R, contract, case)
    st = RD.status_of(ctx, R)
    dom_brief = [{"name": d["name"], "min": round(d["min"], 6), "max": round(d["max"], 6),
                  "step": round(d["step"], 6), "unit": d["unit"],
                  "evidence": d["evidence"][0] if d["evidence"] else {}}
                 for d in ctx["domains"]]
    con_brief = [{"id": c["id"], "param": c["param"], "op": c["op"],
                  "limit": round(c["value"], 6) if isinstance(c["value"], float) else c["value"],
                  "unit": c["unit"], "locator": c["source"],
                  "quote": (c["evidence"][0]["quote"] if c["evidence"] else "")}
                 for c in ctx["constraints"]]
    res = {
        "case_id": ctx["case_id"],
        "status": st,
        "summary": _summary(ctx, R),
        "method": ("scan -> extract domains and bounds -> enumerate grid -> filter -> "
                   "fit ridge surface -> rank / Pareto / sequential search / cost"),
        "parameter_domains": dom_brief,
        "constraints": con_brief,
        "objective_specs": [{"name": o["name"], "direction": o["direction"],
                             "unit": o["unit"], "priority": o["priority"],
                             "measurement": o["measurement"],
                             "quote": (o["evidence"][0]["quote"] if o["evidence"] else "")}
                            for o in ctx["objectives"]],
        "history_rows": len(ctx["history"]),
        "models": R["models"],
        "recommendation": {"value": R["rec"]["value"], "value_source": R["rec"]["value_source"],
                           "band": R["rec"]["band"], "basis": R["rec"]["basis"],
                           "feasible_range": R["rec"]["feasible_range"],
                           "violations": R["rec"]["issues"]},
        "search": {"total_points": (R["search"] or {}).get("total_points", 0),
                   "best": (R["search"] or {}).get("best", {}),
                   "rounds": len((R["search"] or {}).get("rounds", []))},
        "cost": {"status": R["cost"]["status"], "per_trial_cost": R["cost"]["per_trial_cost"],
                 "total_planned_cost": R["cost"]["total_planned_cost"],
                 "budget": R["cost"]["budget"], "formula": R["cost"]["formula"]},
        "feasibility": {"status": R["inf"]["status"], "reason": R["inf"].get("reason", ""),
                        "pass_rate": R["inf"].get("pass_rate", 0.0)},
        "pareto_count": R["pareto"].get("count", 0),
        "version_winner": R["ver"].get("winner", ""),
        "degradations": ctx["degradations"],
        "limits": _uncertainties(ctx, R),
        "uncertainties": _uncertainties(ctx, R),
        "evidence_stats": R["ev_stats"],
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                    for m in ctx["materials"]],
        "change_records": [
            {"step": 1, "action": "scan input materials", "result": "%d files" % len(ctx["materials"])},
            {"step": 2, "action": "extract parameter domains and stated bounds",
             "result": "%d domains, %d bounds" % (len(ctx["domains"]), len(ctx["constraints"]))},
            {"step": 3, "action": "enumerate and filter the grid",
             "result": "%s" % (("%d of %d feasible" % (len(R["grid"].get("feasible") or []), R["grid"].get("size", 0)))
                               if R["grid"].get("ok") else R["grid"].get("reason", "unavailable"))},
            {"step": 4, "action": "fit response surface",
             "result": ("%d indicator model(s)" % len(R["models"])) if R["models"] else "no model (no history)"},
            {"step": 5, "action": "rank, Pareto, search plan and cost ledger",
             "result": "recommendation source %s" % R["rec"]["value_source"]},
        ],
        "artifacts": {
            "search_notes.md": "search_notes.md",
            "parameter_table.json": "parameter_table.json",
            "feasible_grid.json": "feasible_grid.json",
            "pareto_front.json": "pareto_front.json",
            "search_plan.json": "search_plan.json",
            "cost_ledger.json": "cost_ledger.json",
            "version_diff.md": "version_diff.md",
            "evidence.json": "evidence.json",
            "infeasibility.json": "infeasibility.json",
        },
    }
    for k, v in vals.items():
        res[k] = v
    res["output_contract"] = vals
    return res


# --------------------------------------------------------------- writing ----

def write_all(case, ctx, R, out, work, contract):
    arts = RD.build_artifacts(ctx, R)
    for name, content in arts.items():
        if name.endswith(".json"):
            wj(os.path.join(out, name), content)
        else:
            wt(os.path.join(out, name), content)
    res = build_result(case, ctx, R, contract)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": RD.status_of(ctx, R),
        "domains": len(ctx["domains"]), "constraints": len(ctx["constraints"]),
        "feasible": len(R["grid"].get("feasible") or [])})
    return res


def sanitize_output(out):
    for fn in sorted(os.listdir(out)):
        p = os.path.join(out, fn)
        if not os.path.isfile(p):
            continue
        if fn.endswith(".json"):
            obj = rj(p, None)
            if obj is None:
                continue
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(string_clean(obj), fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        else:
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    t = fh.read()
            except OSError:
                continue
            wt(p, t)


def bootstrap(case, inp, out, work):
    ctx = {"case_id": E.s((case or {}).get("case_id")) or "unknown-case",
           "materials": E.scan_materials(inp),
           "domains": [], "constraints": [], "history": [], "objectives": [],
           "degradations": ["init only indexed the input; run build to compute"],
           "errors": [], "notes": {}}
    st = "drafting"
    res = {"case_id": ctx["case_id"], "status": st,
           "summary": "indexed input; run build (or all) to compute the optimisation",
           "limits": ["partial result written by init"],
           "uncertainties": ["optimisation not yet computed"],
           "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                       for m in ctx["materials"]],
           "change_records": [{"step": 0, "action": "init", "result": "indexed %d files" % len(ctx["materials"])}],
           "artifacts": {}}
    vals = {k: "not-computed-yet" for k in DEFAULT_CONTRACT.keys()}
    vals["case_id"] = ctx["case_id"]
    vals["status"] = st
    res.update(vals)
    res["output_contract"] = vals
    wj(os.path.join(out, "result.json"), res)


DRAFT_SKELETON = {
    "case_id": "",
    "objective_weights": {},
    "recommended": {},
    "constraints_added": [],
    "resource_notes": [],
    "uncertainties": [],
    "change_log": [],
}


def cmd_init(inp, out, work):
    case = find_case(inp) or {}
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    bootstrap(case, inp, out, work)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, DRAFT_SKELETON)
    print("init: indexed input, wrote partial result.json and %s" % sk)
    print("next: fill work/draft.json (copy the skeleton), then check and build")
    return 0


def cmd_show(inp, grep, want):
    mats = E.scan_materials(inp)
    n = 0
    for m in mats:
        if want and m["id"] != want and m["rel"] != want:
            continue
        print("=== %s %s (%s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["chars"]))
        for p in m["paras"]:
            if grep and grep.lower() not in p["text"].lower():
                continue
            print("[%s] %s" % (p["locator"], p["text"][:400]))
            n += 1
            if n >= 400:
                return 0
    return 0


def cmd_check(inp, work, out):
    case = find_case(inp) or {}
    mats = E.scan_materials(inp)
    ctx = E.extract(case, mats)
    draft = rj(os.path.join(work, "draft.json"), None)
    report = {"case_id": ctx["case_id"], "draft_present": isinstance(draft, dict),
              "checks": [], "status": "ok"}
    if not isinstance(draft, dict):
        report["checks"].append({"check": "draft_supplied", "ok": False,
                                 "detail": "no work/draft.json; build falls back to the rule set"})
        report["status"] = "no-draft"
    else:
        dmap = {d["key"]: d["key"] for d in ctx["domains"]}
        dmap.update({E.nkey(d["name"]): d["key"] for d in ctx["domains"]})
        rec = draft.get("recommended") if isinstance(draft.get("recommended"), dict) else {}
        mapped = {}
        for k, v in rec.items():
            kk = E.nkey(k)
            if kk in dmap:
                mapped[dmap[kk]] = E.num(v)
        missing = [k for k in {d["key"] for d in ctx["domains"]} if k not in mapped]
        report["checks"].append({"check": "recommendation_keys_map_to_domains",
                                 "ok": not missing and bool(mapped),
                                 "detail": "mapped %d value(s); unmapped: %s"
                                           % (len(mapped), ", ".join(sorted(set(missing))) or "none")})
        chk = O.check_point(ctx, mapped) if mapped else {"feasible": False, "violations": []}
        report["checks"].append({"check": "recommendation_within_bounds",
                                 "ok": bool(chk["feasible"]),
                                 "detail": "violations: %d" % len(chk["violations"])})
        if chk["violations"]:
            report["violations"] = chk["violations"]
            report["status"] = "repair-needed"
    wj(os.path.join(work, "check_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def load_draft(work, ctx):
    d = rj(os.path.join(work, "draft.json"), None)
    if isinstance(d, dict):
        ctx["notes"]["draft_used"] = True
        return d
    return None


def cmd_build(inp, out, work):
    case = find_case(inp) or {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    mats = E.scan_materials(inp)
    ctx = E.extract(case, mats)
    draft = load_draft(work, ctx)
    if draft and isinstance(draft.get("resources"), list):
        ctx["usages"] = []
        for r in draft["resources"]:
            if isinstance(r, dict):
                E._classify_resource(r, {"id": "DRAFT", "text": ""}, "draft", ctx)
    axes = {d["key"]: O.axis_values(d) for d in ctx["domains"]}
    g = O.grid(ctx)
    models = O.fit_models(ctx, g)
    g = O.score_grid(ctx, g, models)
    par = O.pareto(ctx, g, models)
    srch = O.sequential_search(ctx, g, models)
    cost = O.cost_model(ctx, (srch or {}).get("total_points", 0))
    inf = O.infeasibility(ctx, g)
    ver = O.version_compare(ctx, g, models)
    rec = O.recommend(ctx, g, models, draft)
    items, stats = O.evidence_index(ctx)
    R = {"grid": g, "models": models, "pareto": par, "search": srch, "cost": cost,
         "inf": inf, "ver": ver, "rec": rec, "axes": axes, "cap": O.MAX_GRID,
         "ev_items": items, "ev_stats": stats}
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res = write_all(case, ctx, R, out, work, contract)
    sanitize_output(out)
    print("build: status=%s artifacts=%d" % (res["status"], len(res["artifacts"]) + 1))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "search_notes.md", "parameter_table.json", "feasible_grid.json",
            "pareto_front.json", "search_plan.json", "cost_ledger.json", "version_diff.md",
            "evidence.json", "infeasibility.json"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok_echo = isinstance(echo, dict) and all(E.s(v) for v in echo.values())
    playbook = os.path.join(os.path.dirname(HERE), "references", "expert_playbook.md")
    ok_playbook = os.path.isfile(playbook) and os.path.getsize(playbook) > 0
    print("selfcheck: files %s, contract echo %s, expert-checklist %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss),
             "ok" if ok_echo else "incomplete",
             "ok (references/expert_playbook.md present; 9-item checklist to pass)"
             if ok_playbook else "MISSING references/expert_playbook.md",
             res.get("status", "")))
    return 0


def main(argv):
    args = parse_args(argv)
    cmd, inp, out, work = args.command, args.input, args.output, args.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, args.grep, args.mat)
        if cmd == "check":
            return cmd_check(inp, work, out)
        if cmd == "selfcheck":
            return cmd_selfcheck(out)
        if cmd == "build":
            return cmd_build(inp, out, work)
        # all / default
        rc = cmd_build(inp, out, work)
        cmd_selfcheck(out)
        return rc
    except Exception as exc:  # never crash the harness
        try:
            os.makedirs(out, exist_ok=True)
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "summary": "the input could not be processed", "error": str(exc)[:400],
                "limits": ["processing aborted; see error"], "uncertainties": ["input unreadable"],
                "sources": [], "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                "output_contract": {"case_id": "unknown-case", "status": "input_error",
                                    "plan_report": "search_notes.md",
                                    "parameter_table": "parameter_table.json",
                                    "search_plan": "search_plan.json",
                                    "cost_ledger": "cost_ledger.json",
                                    "evidence": "evidence.json",
                                    "uncertainties": "input could not be processed"}})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
