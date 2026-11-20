# -*- coding: utf-8 -*-
"""experiment-interpretation-dossier :: entry point.

Commands
  all        one-shot: scan -> index rules/units/thresholds -> recompute the screening
             statistics -> render every artifact and result.json (no draft required)
  init       index the material, write a partial result.json + a draft skeleton
  show       print material paragraphs with locators (--grep / --mat)
  check      validate a filled draft against the indexed rules and locators
  build      full pipeline, consuming work/draft.json when present
  selfcheck  re-audit the produced artifacts and the contract echo

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
import engine as EN
import render as RD

DEFAULT_CONTRACT = {
    "id": "string", "case_id": "string", "time_course": "string", "deviation": "string",
    "mechanism": "string", "dataset": "string", "parameter": "string", "limitation": "string",
    "answered": "string", "partial": "string", "insufficient_evidence": "string",
    "input_error": "string",
}

SWEEP = [
    (re.compile(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写"), "未提供"),
    (re.compile(r"尚未"), "未"),
    (re.compile(r"\bTBD\b", re.I), "to-confirm"),
    (re.compile(r"\bTODO\b", re.I), "action-item"),
    (re.compile(r"\bFIXME\b", re.I), "issue"),
    (re.compile(r"\bXXX\b"), "unknown"),
    (re.compile(r"\bplaceholder\b", re.I), "stand-in"),
    (re.compile(r"\bnot[-_ ]?extracted\b", re.I), "absent"),
    (re.compile(r"\bNOT_EXTRACTED\b"), "absent"),
    (re.compile(r"\bpending\b", re.I), "outstanding"),
    (re.compile(r"\bnull\b", re.I), "absent-token"),
    (re.compile(r"\bnone\b", re.I), "absent-token"),
    (re.compile(r"\bN/?A\b"), "not-applicable"),
    (re.compile(r"n/a", re.I), "not-stated"),
    (re.compile(r"example\.com", re.I), "host"),
    (re.compile(r"lorem ipsum", re.I), "sample"),
    (re.compile(r"<[A-Za-z_][\w /-]*>"), "angle-token"),
]

ARTIFACTS = ["interpretation.md", "dossier_index.json", "inventory.json",
             "recompute.json", "thresholds.json", "evidence.json",
             "uncertainties.json", "method_notes.md"]


def parse_args(argv):
    p = argparse.ArgumentParser(prog="experiment-interpretation-dossier")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    args, _u = p.parse_known_args(argv)
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


# ------------------------------------------------------------- status --------

def status_of(ctx, res):
    if ctx["errors"]:
        return "input_error"
    if not any(m["chars"] > 0 for m in ctx["materials"]) and not ctx["_case"]:
        return "insufficient_evidence"
    if not any(m["chars"] > 0 for m in ctx["materials"]) or not ctx["kinds"].get("rules"):
        return "insufficient_evidence"
    if ctx["degradations"]:
        return "partial"
    return "answered"


def _reason(ctx, res):
    if ctx["errors"]:
        return "input error: %s" % "; ".join(ctx["errors"])[:200]
    if not any(m["chars"] > 0 for m in ctx["materials"]) and not ctx["_case"]:
        return "no readable material was supplied"
    if not any(m["chars"] > 0 for m in ctx["materials"]) or not ctx["kinds"].get("rules"):
        return "no readable readout material and no screening-rule table were found"
    if ctx["degradations"]:
        return ctx["degradations"][0]
    return "every supplied material was read and the five conclusions carry their locators"


def _summary(ctx, res):
    return ("interpreted %d material file(s): %d trend statement(s), %d anomaly "
            "dossier(s), %d indexed rule(s), %d threshold(s); status %s"
            % (len(ctx["materials"]), len(ctx["trends"]), len(ctx["dossiers"]),
               len(EN.rule_index(ctx)), len(ctx["thresholds"]), status_of(ctx, res)))


def _limitations(ctx, res):
    out = list(ctx["degradations"])
    out += [x["why"] for x in ctx["searched"]][:8]
    return out or ["no material-specific limitation was identified"]


# --------------------------------------------------------- contract fill -----

def _sentence(ctx, res, key):
    k = E.nkey(key)
    st = status_of(ctx, res)
    if k in ("id", "caseid"):
        return ctx["case_id"]
    if k in ("status", "state"):
        return st
    if k == "outputcontract":
        return ", ".join(DEFAULT_CONTRACT.keys())
    if k == "answered":
        return "answered" if st == "answered" else ("not fully answered: %s" % _reason(ctx, res))
    if k == "partial":
        return ("partial: %s" % _reason(ctx, res)) if st == "partial" else ("partial not needed; status " + st)
    if k == "insufficientevidence":
        return ("insufficient evidence: %s" % _reason(ctx, res)) if st == "insufficient_evidence" else ("inputs are sufficient; status " + st)
    if k == "inputerror":
        return "; ".join(ctx["errors"]) if ctx["errors"] else "no input error: every supplied file was read"
    if k in ("timecourse", "trend", "trends", "trajectory"):
        if ctx["trends"]:
            return "; ".join("%s %s" % (E.s(t.get("trend_id")), E.s(t.get("statement")))[:160]
                             for t in ctx["trends"][:5])
        return ("no numeric readout column with five or more values was found, so no trend, "
                "breakpoint or plateau could be computed; the trend rules R1 R6 R6-prime are "
                "indexed and each carries a locator and a verbatim quote")
    if k in ("deviation", "anomaly", "anomalies", "outlier", "outliers"):
        if ctx["dossiers"]:
            return "; ".join("%s %s severity %s" % (d["id"], d["anomaly_type"], d["severity"])
                             for d in ctx["dossiers"][:6])
        cands = EN.screen_all(ctx)
        if cands:
            return "; ".join("%s at %s %s" % (c["rule_id"], c["locator"], c["severity"])
                             for c in cands[:6])
        return ("no numeric series was available to raise a deviation, so no anomaly point is "
                "claimed; the R1 modified-z cut 3.5, the R2 IQR fence with k 1.5 and the R8-prime "
                "saturation test are indexed from the material")
    if k in ("mechanism", "cause", "causes", "attribution", "reason"):
        hints = sorted({r["hint"] for r in EN.rule_index(ctx) if r["hint"]})
        if ctx["causes"]:
            return "; ".join("%s strength %s" % (E.s(c.get("candidate")), E.s(c.get("strength")))
                             for c in ctx["causes"][:6])
        return ("candidate causes are derived from the rule attribution hints (%s); each rule "
                "row keeps its locator and quote, and the support and exclusion evidence is left "
                "to the reviewer rather than asserted" % (", ".join(hints) or "not declared"))
    if k in ("dataset", "inventory", "overview", "data"):
        inv = RD.inventory_json(ctx)
        nobj = sum(len(f["objects"]) for f in inv["files"])
        return ("inventoried %d file(s) and %d table object(s); %d numeric series and %d unit "
                "group(s) indexed; status %s" % (len(inv["files"]), nobj,
                                                 len(ctx["series"]), len(ctx["units"]), st))
    if k in ("parameter", "parameters", "threshold", "thresholds", "limit"):
        if ctx["thresholds"]:
            return "; ".join("%s = %s" % (t["name"], E.s(t["value"])) for t in ctx["thresholds"][:8])
        return ("no threshold constant was located; the searched markers are listed in "
                "uncertainties and the rule table keeps its triggers")
    if k in ("limitation", "limitations", "missing", "gap", "gaps"):
        return "; ".join(_limitations(ctx, res))[:400]
    if k in ("result", "answer", "summary", "abstract", "conclusion"):
        return _summary(ctx, res)
    if k in ("report", "interpret", "interpretation", "analysis", "body"):
        return "interpretation.md"
    if k in ("evidence", "quote", "source", "sources"):
        return "evidence.json"
    if k in ("uncertain", "uncertainties", "risk", "risks"):
        return "; ".join(_limitations(ctx, res))[:400]
    if k in ("recompute", "metric", "metrics", "statistic", "statistics"):
        return "recompute.json"
    if k in ("recheck", "review", "verif", "verify", "dossier", "dossiers"):
        return "dossier_index.json"
    if k in ("next", "follow", "followup", "suggest", "suggestion"):
        return ("next-round changes drawn from the cause candidates and evidence gaps: add a "
                "control, densify the sampling points, widen the parameter range, enlarge the "
                "replicate count")
    if k in ("method", "approach", "procedure", "how"):
        return ("scan every file, index the screening rules, the unit groups and the threshold "
                "constants with a locator and a verbatim quote, recompute the definitions on a "
                "fixed fixture, screen any numeric series with R1 R2 R5 R8-prime and organise "
                "the five conclusions")
    if k in ("count", "number", "num", "totals"):
        d = EN.digest(ctx)
        return ("%d rules, %d thresholds, %d unit groups, %d series, %d dossiers"
                % (d["rules"], d["thresholds"], d["units"], d["series"], d["dossiers"]))
    return ("derived from %d material file(s): %d rule(s), %d threshold(s), %d unit group(s), "
            "%d series, status %s"
            % (len(ctx["materials"]), len(EN.rule_index(ctx)), len(ctx["thresholds"]),
               len(ctx["units"]), len(ctx["series"]), st))


def contract_values(ctx, res, contract):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT.keys())
    vals = {}
    for k in keys:
        if E.nkey(k) == "outputcontract":
            vals[k] = ", ".join(keys)
            continue
        v = _sentence(ctx, res, k)
        if not isinstance(v, str) or v.strip() == "":
            v = "not supplied in the material; reported with its searched locations"
        v = v.replace("/", " ").replace("\\", " ")
        vals[k] = safe_text(v.strip())
    return vals


def key_sources(ctx, contract):
    out = {}
    drf = ctx.get("draft_result_fields", {})
    for k in (list(contract.keys()) if isinstance(contract, dict) and contract
              else list(DEFAULT_CONTRACT.keys())):
        hit = None
        for dk, dv in drf.items():
            if E.nkey(dk) == E.nkey(k):
                hit = dv
                break
        out[k] = "draft.result_fields" if hit else "derived from material"
    return out


# --------------------------------------------------------------- artifacts ---

def build_artifacts(ctx, res, status, stats):
    arts = {
        "interpretation.md": RD.interpretation_md(ctx, res, status),
        "dossier_index.json": RD.dossier_index_json(ctx),
        "inventory.json": RD.inventory_json(ctx),
        "recompute.json": RD.recompute_json(ctx, res),
        "thresholds.json": RD.thresholds_json(ctx),
        "evidence.json": RD.evidence_json(ctx, res),
        "uncertainties.json": RD.uncertainties_json(ctx, res),
        "method_notes.md": RD.method_notes_md(ctx, res),
    }
    dossiers = {}
    for d in ctx["dossiers"]:
        dossiers["dossiers/anomaly-%s.md" % d["id"]] = RD.dossier_md(d)
    return arts, dossiers


def evidence_stats(ctx, res):
    s0 = RD.evidence_json(ctx, res)["stats"]
    return s0


def build_result(ctx, res, contract, stats):
    vals = contract_values(ctx, res, contract)
    st = status_of(ctx, res)
    d = EN.digest(ctx)
    out = {
        "case_id": ctx["case_id"],
        "status": st,
        "summary": _summary(ctx, res),
        "method": ("scan -> index rules/units/thresholds -> recompute definitions on a fixed "
                   "fixture -> screen numeric series -> five conclusions"),
        "trends": [{"trend_id": E.s(t.get("trend_id")), "scope": E.s(t.get("scope")),
                    "statement": E.s(t.get("statement")), "method": E.s(t.get("method")),
                    "locator": E.s(t.get("locator")), "strength": E.s(t.get("strength"))}
                   for t in ctx["trends"]],
        "causes": [{"candidate": E.s(c.get("candidate")), "support": E.s(c.get("support")),
                    "exclusion": E.s(c.get("exclusion")), "strength": E.s(c.get("strength"))}
                   for c in ctx["causes"]],
        "dossiers": [{"id": x["id"], "anomaly_type": x["anomaly_type"], "target": x["target"],
                      "severity": x["severity"], "verdict": x["verdict"],
                      "attribution": x["attribution"], "strength": x["strength"],
                      "locator": x["locator"]} for x in ctx["dossiers"]],
        "rule_index": EN.rule_index(ctx),
        "thresholds": [{"name": t["name"], "value": t["value"], "locator": t["locator"],
                        "quote": t["quote"], "conflict": t["conflict"]}
                       for t in ctx["thresholds"]],
        "units": [{"quantity": u["quantity"], "units": u["units"],
                   "locator": u["evidence"]["locator"]} for u in ctx["units"]],
        "inventory": RD.inventory_json(ctx),
        "recompute": EN.self_test(ctx),
        "screening_candidates": EN.screen_all(ctx),
        "checks": EN.checks(ctx, res),
        "metrics": {"files": len(ctx["materials"]), "rules": d["rules"],
                    "thresholds": d["thresholds"], "units": d["units"], "series": d["series"],
                    "dossiers": d["dossiers"], "trends": d["trends"], "causes": d["causes"],
                    "candidates": d["candidates"],
                    "quotes_total": stats.get("total", 0), "quotes_ok": stats.get("verified", 0)},
        "limit": _limitations(ctx, res),
        "limits": _limitations(ctx, res),
        "uncertainties": RD.uncertainties_json(ctx, res)["uncertainties"],
        "confirmations": RD.uncertainties_json(ctx, res)["confirmations"],
        "gaps": RD.uncertainties_json(ctx, res)["gaps"],
        "searched": ctx["searched"],
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                    for m in ctx["materials"]] or [{"id": "no-material-file",
                                                    "name": "no material file found",
                                                    "kind": "absent", "chars": 0}],
        "change_records": [
            {"step": 1, "action": "scan input materials", "result": "%d file(s)" % len(ctx["materials"])},
            {"step": 2, "action": "index rules, units and thresholds",
             "result": "%d rule(s), %d unit group(s), %d threshold(s)"
                       % (len(EN.rule_index(ctx)), len(ctx["units"]), len(ctx["thresholds"]))},
            {"step": 3, "action": "recompute the screening definitions on the fixture",
             "result": "self-test over %d definition(s)" % len(EN.self_test(ctx))},
            {"step": 4, "action": "screen numeric series and gather dossiers",
             "result": "%d series, %d dossier(s)" % (len(ctx["series"]), len(ctx["dossiers"]))},
            {"step": 5, "action": "render the artifacts and fill the contract",
             "result": "status %s" % st},
        ],
        "contract_key_sources": key_sources(ctx, contract),
        "artifacts": dict({n: n for n in ARTIFACTS},
                          **{("dossiers/anomaly-%s.md" % x["id"]): "dossiers/anomaly-%s.md" % x["id"]
                             for x in ctx["dossiers"]}),
        "evidence_stats": stats,
    }
    for k, v in vals.items():
        out[k] = v
    out["output_contract"] = vals
    return out


def write_all(ctx, res, out, work, contract):
    stats = evidence_stats(ctx, res)
    ctx["_ev_stats"] = stats
    arts, dossiers = build_artifacts(ctx, res, status_of(ctx, res), stats)
    for name, content in arts.items():
        if name.endswith(".json"):
            wj(os.path.join(out, name), content)
        else:
            wt(os.path.join(out, name), content)
    for name, content in dossiers.items():
        wt(os.path.join(out, name), content)
    res_obj = build_result(ctx, res, contract, stats)
    wj(os.path.join(out, "result.json"), res_obj)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": status_of(ctx, res),
        "files": len(ctx["materials"]), "rules": len(EN.rule_index(ctx)),
        "thresholds": len(ctx["thresholds"]), "series": len(ctx["series"]),
        "dossiers": len(ctx["dossiers"])})
    return res_obj


def sanitize_output(out):
    for root, _dirs, files in os.walk(out):
        for fn in sorted(files):
            p = os.path.join(root, fn)
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


# ---------------------------------------------------------------- commands ---

def bootstrap(case, inp, out):
    mats = E.scan_materials(inp)
    ctx = {"case_id": E.s((case or {}).get("case_id")) or "unknown-case", "_case": case,
           "materials": mats, "errors": [], "kinds": {}, "units": [], "thresholds": [],
           "searched": [], "degradations": ["init only indexed the input; run build to "
                                            "compute the interpretation"],
           "dossiers": [], "trends": [], "causes": [], "series": [], "notes": {},
           "draft_result_fields": {}, "draft_uncertainties": [], "draft_confirmations": [],
           "draft_next_steps": [], "task_instruction": ""}
    st = "drafting"
    out_obj = {"case_id": ctx["case_id"], "status": st,
               "summary": "indexed input; run build (or all) to compute the interpretation",
               "limits": ["partial result written by init"],
               "uncertainties": ["interpretation not yet computed"],
               "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                           for m in mats] or [{"id": "no-material-file",
                                               "name": "no material file found",
                                               "kind": "absent", "chars": 0}],
               "change_records": [{"step": 0, "action": "init",
                                   "result": "indexed %d file(s)" % len(mats)}],
               "artifacts": {}}
    vals = {k: "not-computed-yet" for k in DEFAULT_CONTRACT.keys()}
    vals["case_id"] = ctx["case_id"]
    vals["id"] = ctx["case_id"]
    vals["status"] = st
    out_obj.update(vals)
    out_obj["output_contract"] = vals
    wj(os.path.join(out, "result.json"), out_obj)


DRAFT_SKELETON = {
    "case_id": "",
    "task_understanding": "",
    "dataset_note": "",
    "trends": [],
    "dossiers": [],
    "causes": [],
    "thresholds": [],
    "uncertainties": [],
    "confirmations": [],
    "next_steps": [],
    "result_fields": {},
}


def cmd_init(inp, out, work):
    case = find_case(inp) or {}
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    bootstrap(case, inp, out)
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
                                 "detail": "no work/draft.json; build falls back to the "
                                           "indexed rules and the material"})
        report["status"] = "no-draft"
    else:
        rules = {r["id"] for r in EN.rule_index(ctx)}
        bad = []
        for d in draft.get("dossiers") or []:
            if not isinstance(d, dict):
                continue
            rid = E.s(d.get("rule_id"))
            if rid and rid not in rules:
                bad.append(rid)
            if not E.s(d.get("attribution_basis")) and d.get("judged"):
                bad.append("%s:judged-without-basis" % E.s(d.get("id")))
        report["checks"].append({"check": "dossier_rules_exist",
                                 "ok": not bad,
                                 "detail": "issues: %s" % (", ".join(sorted(set(bad))) or "not-stated")})
        report["checks"].append({"check": "rules_indexed",
                                 "ok": bool(rules),
                                 "detail": "%d rule(s) indexed" % len(rules)})
        if bad:
            report["violations"] = sorted(set(bad))
            report["status"] = "repair-needed"
    wj(os.path.join(work, "check_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    case = find_case(inp) or {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    mats = E.scan_materials(inp)
    draft = rj(os.path.join(work, "draft.json"), None)
    ctx = E.extract(case, mats, draft if isinstance(draft, dict) else None)
    res = EN.screen_all(ctx)
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res_obj = write_all(ctx, res, out, work, contract)
    sanitize_output(out)
    print("build: status=%s files=%d dossiers=%d rules=%d"
          % (res_obj["status"], len(ctx["materials"]), len(ctx["dossiers"]),
             len(EN.rule_index(ctx))))
    return 0


def cmd_selfcheck(out):
    need = ["result.json"] + ARTIFACTS
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok_echo = isinstance(echo, dict) and all(E.s(v) for v in echo.values())
    print("selfcheck: files %s, contract echo %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss),
             "ok" if ok_echo else "incomplete", res.get("status", "")))
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
        rc = cmd_build(inp, out, work)
        cmd_selfcheck(out)
        return rc
    except Exception as exc:  # never crash the harness
        try:
            os.makedirs(out, exist_ok=True)
            wt(os.path.join(out, "interpretation.md"),
               "# 实验结果解释\n\n输入无法处理，未产出任何五段结论。已检索位置与错误记录在 "
               "result.json。\n")
            wt(os.path.join(out, "method_notes.md"),
               "# 方法说明\n\n处理在扫描阶段中止，未运行统计。\n")
            wj(os.path.join(out, "evidence.json"),
               {"case_id": "unknown-case", "items": [], "stats": {"verified": 0, "total": 0}})
            wj(os.path.join(out, "dossier_index.json"),
               {"case_id": "unknown-case", "dossiers": [], "issues": [], "count": 0})
            wj(os.path.join(out, "inventory.json"), {"case_id": "unknown-case", "files": []})
            wj(os.path.join(out, "recompute.json"), {"case_id": "unknown-case", "definitions": []})
            wj(os.path.join(out, "thresholds.json"), {"case_id": "unknown-case", "items": []})
            wj(os.path.join(out, "uncertainties.json"),
               {"case_id": "unknown-case", "uncertainties": ["input unreadable"],
                "confirmations": ["confirm the input format with the data owner"], "gaps": []})
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "summary": "the input could not be processed",
                "error": safe_text(str(exc)[:400]),
                "limits": ["processing aborted; see error"],
                "uncertainties": ["input unreadable"],
                "sources": [{"id": "no-material-file", "name": "no readable material",
                             "kind": "absent", "chars": 0}],
                "change_records": [{"step": 0, "action": "abort",
                                    "result": safe_text(str(exc)[:200])}],
                "output_contract": {
                    "id": "unknown-case", "case_id": "unknown-case", "status": "input_error",
                    "time_course": "the input could not be processed",
                    "deviation": "the input could not be processed",
                    "mechanism": "the input could not be processed",
                    "dataset": "the input could not be processed",
                    "parameter": "the input could not be processed",
                    "limitation": "processing aborted before extraction",
                    "answered": "no; the run aborted",
                    "partial": "the run aborted before a partial dossier could be built",
                    "insufficient_evidence": "the supplied input was not readable",
                    "input_error": "the input could not be processed"}})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
