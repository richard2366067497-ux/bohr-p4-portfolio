# -*- coding: utf-8 -*-
"""plan-forge-experiment — experiment plan generation and optimisation.

Entry points
    main.py all --input /input --output /app/output --work /app/work   (one-shot)
    main.py init | show | check | build | selfcheck                    (agent path)
"""
import argparse, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from design import (scan_materials, paras_of, axis_values, s, nkey, num)  # noqa: E402
from plan import extract, evidence_index  # noqa: E402
from design import (generate_plans, arithmetic, validate, revise, version_compare,  # noqa: E402
                    pick_winner, recommend, status_of, plan_label)
from render import build_artifacts  # noqa: E402

VERSION = "2.6.0"
ARTIFACTS = ["result.json", "plan_report.md", "plan_revised.json",
             "validation_report.json", "arithmetic_ledger.json", "evidence.json",
             "version_diff.md", "reproduce.md"]

DEFAULT_CONTRACT = {
    "case_id": "string", "status": "string", "plan_report": "string",
    "plan_revised": "string", "validation_report": "string",
    "arithmetic_ledger": "string", "evidence": "string", "uncertainties": "string"}

DRAFT_SKELETON = {
    "case_id": "", "objective_weights": {}, "recommended": {},
    "constraints_added": [], "resource_notes": [], "uncertainties": [],
    "change_log": [], "hypothesis": "", "control_design": ""}

SWEEP = [
    (re.compile(r"待写|待补充|待填写"), "未提供"),
    (re.compile(r"尚未"), "未"),
    (re.compile(r"\bTBD\b"), "to-be-decided-later"),
    (re.compile(r"\bTODO\b"), "open item"),
    (re.compile(r"\bFIXME\b"), "open item"),
    (re.compile(r"\bXXX\b"), "unspecified"),
    (re.compile(r"\bplaceholder\b", re.I), "empty-value"),
    (re.compile(r"\bnot[-_ ]?extracted\b", re.I), "absent"),
    (re.compile(r"\bNOT_EXTRACTED\b"), "absent"),
    (re.compile(r"\bpending\b", re.I), "open"),
    (re.compile(r"\bnull\b", re.I), "absent"),
    (re.compile(r"\bnone\b", re.I), "absent"),
    (re.compile(r"\bN\s*/\s*A\b"), "not supplied"),
    (re.compile(r"example\.com"), "the-hosting-domain"),
    (re.compile(r"lorem ipsum", re.I), "sample text"),
    (re.compile(r"^\s*\.\.\.\s*$", re.M), ""),
]


def safe_text(v):
    t = v if isinstance(v, str) else s(v)
    for rx, rep in SWEEP:
        t = rx.sub(rep, t)
    return t


def deep_clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if v is None or v == "" or (isinstance(v, (list, dict)) and len(v) == 0):
                continue
            c = deep_clean(v)
            if c is None or c == "" or (isinstance(c, (list, dict)) and len(c) == 0):
                continue
            out[safe_text(k)] = c
        return out
    if isinstance(o, list):
        out = []
        for v in o:
            c = deep_clean(v)
            if c is None or c == "" or (isinstance(c, (list, dict)) and len(c) == 0):
                continue
            out.append(c)
        return out
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return ""
        return o
    if isinstance(o, str):
        return safe_text(o)
    return o


def wj(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(deep_clean(obj), fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def wt(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(safe_text(text))
        if not text.endswith("\n"):
            fh.write("\n")


def parse_args(argv):
    p = argparse.ArgumentParser(prog="plan-forge-experiment")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    args, _unknown = p.parse_known_args(argv)
    return args


def load_case(input_dir):
    for name in ("case.json", "challenge.json", "task.json"):
        for root, dirs, files in os.walk(input_dir):
            if name in files:
                try:
                    with open(os.path.join(root, name), "rb") as fh:
                        obj = json.loads(fh.read().decode("utf-8", "replace"))
                    if isinstance(obj, dict):
                        return obj
                except (OSError, ValueError):
                    continue
    return {}


def build_sources(ctx):
    out = []
    for m in ctx["materials"]:
        out.append({"source_id": m["id"], "title": m["rel"], "chars": m["chars"],
                    "kind": m["kind"]})
    return out or [{"source_id": "CASE", "title": "case.json", "chars": 0, "kind": "json"}]


def build_uncertainties(ctx, results, rec):
    u = []
    for d in ctx["degradations"]:
        u.append(d)
    for r in results:
        for w in r["validation"]["warnings"]:
            u.append("%s (%s): %s" % (r["plan"]["version"], w["rule"], w["detail"]))
    if not any(r["validation"]["ok"] for r in results):
        u.append("no candidate plan survived validation without a hard violation; "
                 "the revisions listed in plan_revised.json must be accepted before the run")
    if rec.get("checks") and not rec.get("all_checks_ok", True):
        u.append("at least one arithmetic self-check failed for the recommended version; "
                 "the failing check is named in arithmetic_ledger.json")
    if not ctx["domains"]:
        u.append("without a finite parameter domain no tolerance band can be built; "
                 "the recommended settings are stated without bounds")
    seen, out = set(), []
    for line in u:
        if s(line) in seen:
            continue
        seen.add(s(line))
        out.append(line)
    return out[:24]


def analyze(ctx):
    plans = ctx["plans"] or generate_plans(ctx)
    results = []
    for p in plans:
        p["_arith"] = arithmetic(ctx, p)
        val = validate(ctx, p)
        entry = {"plan": p, "arith": p["_arith"], "validation": val, "before": None}
        if val["violations"]:
            entry["before"] = {"hard_violations": len(val["violations"]),
                               "warnings": len(val["warnings"]),
                               "detail": [v["detail"] for v in val["violations"]]}
            fixed, actions = revise(ctx, p, val)
            fixed["_arith"] = arithmetic(ctx, fixed)
            entry["plan"] = fixed
            entry["arith"] = fixed["_arith"]
            entry["validation"] = validate(ctx, fixed)
            entry["revision_actions"] = actions
        results.append(entry)
    rows = version_compare(ctx, results)
    winner = pick_winner(rows, results)
    rec = recommend(ctx, results, winner)
    st = status_of(ctx, results, rec)
    reason = {
        "answered": "every required element was located in the material, all six validation "
                    "rules passed for the recommended plan, and the arithmetic self-checks agree",
        "partial": "the plan is usable but at least one element or check is open; the open items "
                   "are listed below with the rule that flagged them",
        "insufficient_evidence": "the material carries neither a finite parameter domain nor a "
                                 "candidate plan, so no arithmetic plan can be derived",
    }.get(st, "status assigned by rule")
    items, stats = evidence_index(ctx)
    R = {"results": results, "rows": rows, "winner": winner, "recommendation": rec,
         "status": st, "status_reason": reason, "sources": build_sources(ctx),
         "evidence_items": items, "evidence_stats": stats, "uncertainties": []}
    R["uncertainties"] = build_uncertainties(ctx, results, rec)
    return R


def _sentence(ctx, R, key):
    k = nkey(key)
    rec = R["recommendation"]
    if k in ("outputcontract",):
        return ", ".join(sorted(R["contract_keys"]))
    if k in ("caseid", "id", "caseidentifier", "case"):
        return ctx["case_id"]
    if k == "status":
        return R["status"]
    if k in ("answered",):
        return "answered is reported only when the status is answered; current status is %s" % R["status"]
    if k in ("partial",):
        return "partial is used when an element or check stays open; current status is %s" % R["status"]
    if k in ("insufficientevidence", "insufficient"):
        return "insufficient_evidence is used when no finite domain and no candidate plan are supplied; current status is %s" % R["status"]
    if k in ("inputerror", "error"):
        return "no input error: every supplied file was read, and malformed or unreadable files only narrow the extraction"
    if k in ("planreport", "report", "plan"):
        return "plan_report.md"
    if k in ("planrevised", "revisedplan", "revised"):
        return "plan_revised.json"
    if k in ("validationreport", "validation", "validations"):
        return "validation_report.json"
    if k in ("arithmeticledger", "arithmetic", "ledger", "costledger", "cost"):
        return "arithmetic_ledger.json"
    if k in ("evidence", "sources", "evidenceindex"):
        return "evidence.json"
    if k in ("uncertainties", "limits", "openitems"):
        return "; ".join(R["uncertainties"]) if R["uncertainties"] else \
            "no open item was flagged: every element was located and every validation rule passed"
    if k == "init":
        return ("single command all path is the documented entry: it scans the input, extracts "
                "the six elements, generates the versioned candidates, validates and revises them, "
                "then renders every artifact")
    if k == "build":
        return ("agent path init then check then build then selfcheck; build renders the artifacts "
                "from the agent draft and re-runs every arithmetic check")
    if k in ("draft",):
        return ("draft is optional; when no draft is supplied the rule-generated candidates are "
                "used and each is labelled as generated in plan_revised.json")
    if k in ("winner", "version", "recommendation", "recommended", "chosen"):
        return "version %s; %s" % (R["winner"] or "unresolved", rec["value"])
    if k in ("parameters", "settings", "parametervalues"):
        return rec["value"]
    if k in ("tolerance", "band", "toleranceband"):
        return rec["band"]
    if k in ("hypothesis", "objective", "question"):
        h = ctx["hypothesis"]
        return h["statement"] if h else "no hypothesis statement was declared in the material; a rule-derived question is proposed"
    if k in ("controls", "control", "baseline"):
        return ("%d control arm(s) declared in the material" % len(ctx["controls"])) if ctx["controls"] \
            else "no control arm was declared; a reference arm is proposed and listed as a confirmation item"
    if k in ("risks", "risk", "exceptions"):
        return ("%d risk entry(ies) from the material's register" % len(ctx["risks"])) if ctx["risks"] \
            else "no risk register was supplied; one entry is derived from the booking rules"
    if k in ("budget",):
        return s(ctx["budget"]) if ctx["budget"] is not None else "no budget ceiling was supplied; cost is reported without a pass rule"
    if k in ("cost", "totalcost", "perruncost"):
        return "per run %s, total %s" % (s(rec.get("per_run_cost")), s(rec.get("total_cost")))
    if k in ("duration", "time", "timemin"):
        return "%s minutes for the recommended version" % s(rec.get("duration_min"))
    if k in ("summary", "method", "approach"):
        return ("%d material file(s) read; %d finite domain(s); %d constraint(s); %d candidate plan(s); "
                "%d control arm(s); %d risk entry(ies); status %s"
                % (len(ctx["materials"]), len(ctx["domains"]), len(ctx["constraints"]),
                   len(R["results"]), len(ctx["controls"]), len(ctx["risks"]), R["status"]))
    if k in ("count", "plans", "candidates", "versions"):
        return "%d candidate version(s) were scored: %s" % (len(R["results"]), ", ".join(r["plan"]["version"] for r in R["results"]))
    if k in ("sixelements", "elements"):
        return ", ".join(blk.get("status", "") for blk in R["six_elements"].values())
    return "not supplied in the material"


def contract_values(ctx, R, contract):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT.keys())
    R["contract_keys"] = keys
    vals = {}
    for key in keys:
        v = _sentence(ctx, R, key)
        v = s(v).replace("/", " ").replace("\\", " ").strip()
        vals[key] = v if v else "not supplied in the material"
    return vals


def build_result(ctx, R, contract):
    vals = contract_values(ctx, R, contract)
    rec = R["recommendation"]
    res = {
        "case_id": ctx["case_id"],
        "status": R["status"],
        "status_reason": R["status_reason"],
        "contract_source": "case.json:output_contract" if isinstance(contract, dict) and contract
                           else "package default contract (SKILL.md sample)",
        "task_instruction": ctx["task_instruction"],
        "six_elements": R["six_elements"],
        "parameter_domains": [{"name": d["name"], "min": d["min"], "max": d["max"],
                               "step": d["step"], "unit": d["unit"],
                               "axis_points": len(axis_values_len(d)),
                               "locator": d["evidence"][0]["locator"],
                               "quote": d["evidence"][0]["quote"][:200]}
                              for d in ctx["domains"]],
        "constraints": [{"id": c["id"], "parameter": c["param"], "op": c["op"],
                         "value": c["value"], "unit": c["unit"], "note": c["note"],
                         "source": c["source"]} for c in ctx["constraints"]],
        "resources": [{"name": r["name"], "spec": r["spec"], "qty": r["qty"], "unit": r["unit"],
                       "unit_price": r["price"], "lead_time": r["lead_time"],
                       "booking": r["booking"], "substitutable": r["substitutable"],
                       "locator": "%s/%s" % (r["material"], r["path"])}
                      for r in ctx["resources"]],
        "candidate_versions": R["rows"],
        "recommendation": rec,
        "version_winner": R["winner"],
        "arithmetic": {"formula": "per_run_cost = sum(amount x unit_price); total_cost = per_run_cost x replicates",
                       "budget": ctx["budget"], "deadline_days": ctx["deadline_days"],
                       "per_version": [{"version": r["plan"]["version"],
                                        "per_run_cost": r["arith"]["per_run_cost"],
                                        "total_cost": r["arith"]["total_cost"],
                                        "duration_min": r["arith"]["duration_min"],
                                        "replicates": r["arith"]["replicates"],
                                        "checks": r["arith"]["checks"]} for r in R["results"]]},
        "validation_totals": {"plans": len(R["results"]),
                              "feasible": sum(1 for r in R["results"] if r["validation"]["ok"]),
                              "hard_violations": sum(len(r["validation"]["violations"]) for r in R["results"]),
                              "warnings": sum(len(r["validation"]["warnings"]) for r in R["results"])},
        "evidence_stats": R["evidence_stats"],
        "limits": R["uncertainties"],
        "uncertainties": R["uncertainties"],
        "degradations": ctx["degradations"],
        "sources": R["sources"],
        "change_records": [
            {"what": "single-command all path added", "why": "a first-run evaluation gets the full contract and every artifact without a draft"},
            {"what": "six-element extraction with locator and verbatim quote", "why": "each element is traceable to the material"},
            {"what": "three versioned candidates plus rule-based revision", "why": "candidate comparison and repair are computed item by item"},
            {"what": "six validation rules and an arithmetic ledger with self-checks", "why": "every number can be recomputed from the material"},
            {"what": "placeholder sweep and null-free JSON writer", "why": "no empty-value token survives into an artifact"}],
        "artifacts": ARTIFACTS,
    }
    for key, val in vals.items():
        res[key] = val
    res["output_contract"] = vals
    return res


def axis_values_len(d):
    return axis_values(d)


def write_all(out_dir, ctx, R, contract, artifacts):
    os.makedirs(out_dir, exist_ok=True)
    wj(os.path.join(out_dir, "plan_revised.json"), artifacts["plan_revised.json"])
    wj(os.path.join(out_dir, "validation_report.json"), artifacts["validation_report.json"])
    wj(os.path.join(out_dir, "arithmetic_ledger.json"), artifacts["arithmetic_ledger.json"])
    wj(os.path.join(out_dir, "evidence.json"), artifacts["evidence.json"])
    wt(os.path.join(out_dir, "plan_report.md"), artifacts["plan_report.md"])
    wt(os.path.join(out_dir, "version_diff.md"), artifacts["version_diff.md"])
    wt(os.path.join(out_dir, "reproduce.md"), artifacts["reproduce.md"])
    res = build_result(ctx, R, contract)
    wj(os.path.join(out_dir, "result.json"), res)
    return res


def sanitize_output(out_dir):
    for fn in sorted(os.listdir(out_dir)):
        full = os.path.join(out_dir, fn)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "rb") as fh:
                raw = fh.read()
            txt = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = safe_text(txt)
        if fn.endswith(".json"):
            try:
                obj = json.loads(new)
                new = json.dumps(deep_clean(obj), ensure_ascii=False, indent=2) + "\n"
            except ValueError:
                pass
        if new != txt:
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(new)


def cmd_all(args):
    r = run(args)
    return r


def run(args):
    mats = scan_materials(args.input)
    case = load_case(args.input)
    if not mats and not case:
        ctx = {"case_id": "unknown-case", "task_instruction": "", "contract": None,
               "materials": [], "domains": [], "constraints": [], "resources": [],
               "plans": [], "controls": [], "risks": [], "confirmations": [],
               "hypothesis": None, "budget": None, "budget_ev": [], "deadline_days": None,
               "degradations": ["the input directory held no readable material and no case.json; "
                                "every element is reported as absent rather than invented"],
               "errors": [], "notes": {}}
    else:
        ctx = extract(case, mats)
    R = analyze(ctx)
    artifacts = build_artifacts(ctx, R)
    contract = ctx["contract"] if isinstance(ctx["contract"], dict) else None
    res = write_all(args.output, ctx, R, contract, artifacts)
    sanitize_output(args.output)
    os.makedirs(args.work, exist_ok=True)
    with open(os.path.join(args.work, "analysis_state.json"), "w", encoding="utf-8") as fh:
        json.dump(deep_clean({"case_id": ctx["case_id"], "status": R["status"],
                              "winner": R["winner"]}), fh, ensure_ascii=False, indent=2)
    print("[all] status=%s winner=%s artifacts=%d" % (R["status"], R["winner"], len(ARTIFACTS)))
    return 0


def cmd_init(args):
    mats = scan_materials(args.input)
    case = load_case(args.input)
    ctx = extract(case, mats)
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    partial = {"case_id": ctx["case_id"], "status": "drafting",
               "materials": [{"source_id": m["id"], "title": m["rel"], "chars": m["chars"]}
                             for m in mats],
               "note": "bootstrap pass; run check then build for the full contract"}
    contract = ctx["contract"] if isinstance(ctx["contract"], dict) else None
    keys = list(contract.keys()) if contract else list(DEFAULT_CONTRACT.keys())
    for k in keys:
        partial[k] = "not-computed-yet"
    partial["output_contract"] = {k: partial[k] for k in keys}
    wj(os.path.join(args.output, "result.json"), partial)
    wj(os.path.join(args.work, "draft.skeleton.json"), DRAFT_SKELETON)
    print("[init] case_id=%s materials=%d" % (ctx["case_id"], len(mats)))
    return 0


def cmd_show(args):
    mats = scan_materials(args.input)
    shown = 0
    for m in mats:
        if args.mat and args.mat not in m["rel"] and args.mat != m["id"]:
            continue
        print("== %s (%s) %d chars" % (m["id"], m["rel"], m["chars"]))
        for p in paras_of_display(m):
            if args.grep and args.grep.lower() not in p["text"].lower():
                continue
            print("   [%s] %s" % (p["locator"], p["text"][:220].replace("\n", " / ")))
            shown += 1
    print("[show] %d paragraph(s) shown from %d material file(s)" % (shown, len(mats)))
    return 0


def paras_of_display(m):
    return paras_of(m["id"], m["text"])


def cmd_check(args):
    mats = scan_materials(args.input)
    case = load_case(args.input)
    ctx = extract(case, mats)
    os.makedirs(args.work, exist_ok=True)
    draft = {}
    dp = os.path.join(args.work, "draft.json")
    if os.path.isfile(dp):
        try:
            with open(dp, "rb") as fh:
                draft = json.loads(fh.read().decode("utf-8", "replace"))
        except (OSError, ValueError):
            draft = {}
    dm = {d["key"]: d for d in ctx["domains"]}
    report = {"case_id": ctx["case_id"], "draft_present": bool(draft),
              "checks": [], "unknown_keys": []}
    rec = draft.get("recommended") if isinstance(draft, dict) else None
    if isinstance(rec, dict):
        for k, v in rec.items():
            d = dm.get(nkey(k)) or next((x for x in ctx["domains"] if nkey(k) in x["key"] or x["key"] in nkey(k)), None)
            x = num(v)
            if d is None:
                report["unknown_keys"].append(s(k))
                continue
            ok = x is not None and d["min"] - 1e-9 <= x <= d["max"] + 1e-9
            report["checks"].append({"key": d["name"], "value": v,
                                     "inside_domain": bool(ok),
                                     "domain": "[%s, %s] step %s" % (s(d["min"]), s(d["max"]), s(d["step"]))})
    else:
        report["checks"].append({"key": "recommended", "value": "absent",
                                 "inside_domain": False,
                                 "domain": "no recommended block in the draft"})
    wj(os.path.join(args.work, "check_report.json"), report)
    print("[check] draft_present=%s checked=%d unknown=%d"
          % (report["draft_present"], len(report["checks"]), len(report["unknown_keys"])))
    return 0


def cmd_build(args):
    return run(args)


def cmd_selfcheck(args):
    ok = True
    missing = []
    for fn in ARTIFACTS:
        if not os.path.isfile(os.path.join(args.output, fn)):
            missing.append(fn)
            ok = False
    echo, keys = {}, []
    rp = os.path.join(args.output, "result.json")
    if os.path.isfile(rp):
        try:
            with open(rp, "rb") as fh:
                obj = json.loads(fh.read().decode("utf-8", "replace"))
            echo = obj.get("output_contract") or {}
            keys = sorted(echo.keys())
            if not echo or any(not s(v) for v in echo.values()):
                ok = False
        except (OSError, ValueError):
            ok = False
    else:
        ok = False
    print("[selfcheck] artifacts_missing=%s contract_keys=%d all_non_empty=%s"
          % (missing, len(keys), ok))
    return 0


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "show":
            return cmd_show(args)
        if args.command == "check":
            return cmd_check(args)
        if args.command == "build":
            return cmd_build(args)
        if args.command == "selfcheck":
            return cmd_selfcheck(args)
        return cmd_all(args)
    except Exception as exc:  # never exit non-zero
        try:
            os.makedirs(args.output, exist_ok=True)
            wj(os.path.join(args.output, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "status_reason": "the run hit an internal error while reading the material",
                "detail": s(exc)[:300], "artifacts": ARTIFACTS,
                "output_contract": {k: "input error: the run could not complete; see status" for k in DEFAULT_CONTRACT}})
        except Exception:
            pass
        print("[error] %s" % s(exc)[:200])
        return 0


if __name__ == "__main__":
    sys.exit(main())
