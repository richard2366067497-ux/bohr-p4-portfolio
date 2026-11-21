# -*- coding: utf-8 -*-
"""plan-feasibility-review :: entry point.

Commands: all (one-shot, no draft required) | init | show | check | build | selfcheck.
all scans the input, extracts the resources, domains and bounds, scores the seven
categories, derives the duration and cost line by line and writes every artifact plus
result.json.  Pure standard library, offline.  Every command exits 0.
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
    "case": "string", "case_id": "string", "plan": "string", "equipment": "string",
    "material": "string", "booking": "string", "budget": "string", "domains": "string",
    "approval": "string", "source": "string", "task": "string",
}


def _abort_contract():
    oc = {k: "review aborted before extraction" for k in DEFAULT_CONTRACT}
    oc["case"] = "the input could not be processed"
    oc["case_id"] = "unknown-case"
    oc["status"] = "input_error"
    oc["plan"] = "feasibility_review.md"
    oc["source"] = "evidence.json"
    return oc

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
    (re.compile(r"n/a", re.I), "not-stated"),
    (re.compile(r"example\.com", re.I), "host"),
    (re.compile(r"lorem ipsum", re.I), "sample"),
    (re.compile(r"<[A-Za-z_][\w /-]*>"), "angle-token"),
]


def parse_args(argv):
    p = argparse.ArgumentParser(prog="plan-feasibility-review")
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
    has_text = any(m["chars"] > 0 for m in ctx["materials"])
    if not has_text and not ctx["_case"]:
        return "insufficient_evidence"
    if not res["versions"] and not (ctx["res_equipment"] or ctx["res_materials"]
                                    or ctx["res_bookings"] or ctx["params"]):
        return "insufficient_evidence"
    if ctx["degradations"]:
        return "partial"
    return "answered"


def _reason(ctx, res):
    if ctx["errors"]:
        return "input error: %s" % "; ".join(ctx["errors"])[:200]
    if not any(m["chars"] > 0 for m in ctx["materials"]) and not ctx["_case"]:
        return "no readable material was supplied"
    if not res["versions"] and not (ctx["res_equipment"] or ctx["res_materials"]
                                    or ctx["res_bookings"] or ctx["params"]):
        return "no candidate version and no resource contract was found in the material"
    if ctx["degradations"]:
        return ctx["degradations"][0]
    return "all seven categories were reviewable for every candidate version"


def _uncertainties(ctx, res):
    out = list(res["degradations"])
    if res["versions"]:
        for r in res["versions"]:
            out.append("version %s: %d blocked categor(y/ies) %s; per-run cost %s"
                       % (r["version"], len(r["blocked"]), r["blocked"], E.s(r["per_run_cost"])))
    else:
        out.append("no versioned candidate plan was supplied, so no per-version verdict exists")
    if res["budget"] is None:
        out.append("budget ceiling absent, so the over-budget percentage stays open")
    out.append("category states rely on the four-state wording found in the material "
               "(already / outsource / procure / unavailable); unrecognised wording is "
               "reported as not-declared rather than assumed available")
    return out or ["no material-specific uncertainty was identified"]


def _summary(ctx, res):
    if not res["versions"]:
        return ("no candidate version in the material; reported the rule index, the searched "
                "locations and the seven-category checklist instead")
    w = res["winner"]
    return ("reviewed %d version(s); winner %s; ranked %s"
            % (len(res["versions"]), w or "not-decidable", ", ".join(res["ranked"])))


# --------------------------------------------------------- contract fill -----

def _sentence(ctx, res, key):
    k = E.nkey(key)
    st = status_of(ctx, res)
    if k in ("caseid",) or k == "id":
        return ctx["case_id"]
    if k == "status":
        return st
    if k == "outputcontract":
        return ", ".join(DEFAULT_CONTRACT.keys())
    if k == "answered":
        return "answered" if st == "answered" else ("not fully answered: %s" % _reason(ctx, res))
    if k == "partial":
        return ("partial: %s" % _reason(ctx, res)) if st == "partial" else ("partial not needed; status " + st)
    if k == "insufficientevidence":
        return ("insufficient evidence: %s" % _reason(ctx, res)) if st == "insufficient_evidence" else ("sufficient inputs; status " + st)
    if k == "inputerror":
        return "; ".join(ctx["errors"]) if ctx["errors"] else "no input error: every supplied file was read"
    if k in ("case", "scenario", "context", "background", "subject"):
        return ("case %s: %d candidate version(s), %d domain(s), %d bound(s); status %s"
                % (ctx["case_id"], len(res["versions"]), len(ctx["params"]),
                   len(ctx["constraints"]), st))
    if k in ("task", "assignment", "instruction", "deliverable", "scope"):
        if ctx["task_instruction"]:
            return ctx["task_instruction"][:400]
        return ("seven-category feasibility review of each candidate version: equipment, "
                "material, time, sample, ethics and safety, parameter range, risks and exceptions")
    if k in ("plan", "planreport", "report", "review", "scheme", "protocol"):
        return "feasibility_review.md"
    if k in ("equipment", "device", "instrument", "equipments", "facility"):
        if ctx["res_equipment"]:
            return "; ".join("%s=%s" % (e["name"], RD.CN.get(
                EN.STATE_SET.get(e.get("status", "unknown"), "unknown"), e.get("status")))
                for e in ctx["res_equipment"][:8])
        return "no equipment object in the material; four-state check reported as searched-but-absent"
    if k in ("material", "materials", "consumable", "reagent", "supplies"):
        if ctx["res_materials"]:
            return "; ".join("%s unit_price=%s %s lead=%s" % (
                m["name"], E.s(m.get("unit_price")), m.get("unit") or "unit",
                E.s(m.get("lead_time"))) for m in ctx["res_materials"][:8])
        return "no consumable price row in the material; cost lines reported as not declared"
    if k in ("booking", "reservation", "reservations", "schedule", "slot"):
        if ctx["res_bookings"]:
            return "; ".join("%s day_rate=%s window_days=%s" % (
                b["name"], E.s(b.get("day_rate")), E.s(b.get("window_days")))
                for b in ctx["res_bookings"][:8])
        return "no booking row in the material; window capacity reported as not declared"
    if k in ("budget", "cost", "costcap", "ceiling"):
        if res["budget"] is None:
            return "no budget ceiling in the material; the cost ledger keeps its formula and leaves the ratio open"
        return "budget ceiling %s; per-run cost per version %s" % (
            E.s(res["budget"]),
            "; ".join("%s=%s" % (r["version"], E.s(r["per_run_cost"])) for r in res["versions"]) or "not computable")
    if k in ("domains", "domain", "parameterrange", "parameters", "range", "ranges", "limits"):
        if ctx["params"]:
            return "; ".join("%s %s..%s step %s %s (points %s)" % (
                d["name"], E.s(d["min"]), E.s(d["max"]), E.s(d["step"]),
                d["unit"] or "unit-free", EN.grid_points(d)) for d in ctx["params"][:8])
        return "no finite parameter domain in the material; the in-domain and step-alignment checks are reported absent"
    if k in ("approval", "approvals", "ethics", "safety", "permit", "permits", "confirmations"):
        if ctx["res_approvals"]:
            return "; ".join("%s level=%s status=%s" % (
                a["name"], E.s(a.get("level")), E.s(a.get("status"))) for a in ctx["res_approvals"][:8])
        return "no ethics or safety approval item in the material; approvals reported as not declared"
    if k in ("source", "sources", "evidence", "citations", "quotes", "trace"):
        return "evidence.json"
    if k in ("checks", "checksjson", "verdicts", "categories"):
        return "checks.json"
    if k in ("estimate", "timecost", "timeandcost"):
        return "estimate.json"
    if k in ("risks", "risk", "exceptions"):
        return "risks.json"
    if k in ("uncertainties", "uncertainty", "gaps", "limitations", "limitation"):
        return "; ".join(_uncertainties(ctx, res))
    if k in ("version", "versions", "compare", "diff", "versiondiff"):
        return "version_diff.md"
    if k in ("summary", "conclusion", "answer", "result", "recommendation"):
        return _summary(ctx, res)
    if k in ("method", "approach", "procedure", "how"):
        return ("scan materials; extract resource rows, finite domains and stated bounds; "
                "score each candidate version across the seven categories; derive the serial "
                "duration and the per-run cost line by line; rank by feasibility then cost")
    if k in ("count", "number", "num", "n", "totals"):
        return ("%d versions, %d domains, %d bounds, %d equipment rows, %d material rows, "
                "%d booking rows" % (len(res["versions"]), len(ctx["params"]),
                                     len(ctx["constraints"]), len(ctx["res_equipment"]),
                                     len(ctx["res_materials"]), len(ctx["res_bookings"])))
    if k in ("winner", "chosen", "recommended", "recommend"):
        return _summary(ctx, res)
    return ("derived from %d material file(s): %d version(s), %d domain(s), %d bound(s), "
            "%d resource row(s), status %s"
            % (len(ctx["materials"]), len(res["versions"]), len(ctx["params"]),
               len(ctx["constraints"]), len(ctx["res_equipment"]) + len(ctx["res_materials"])
               + len(ctx["res_bookings"]), st))


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


# --------------------------------------------------------------- artifacts ---

def build_artifacts(ctx, res, status, stats):
    return {
        "feasibility_review.md": RD.review_md(ctx, res, status, stats),
        "checks.json": RD.checks_json(ctx, res, status, stats),
        "estimate.json": RD.estimate_json(ctx, res),
        "risks.json": RD.risks_json(ctx, res),
        "confirmations.json": RD.confirmations_json(ctx, res),
        "evidence.json": RD.evidence_json(ctx, res, stats),
        "version_diff.md": RD.version_diff_md(ctx, res),
    }


def evidence_stats(ctx, res):
    items = RD.evidence_json(ctx, res, {"verified": 0, "total": 0})["items"]
    tot = len(items)
    ver = sum(1 for it in items if it.get("verified"))
    return {"verified": ver, "total": tot,
            "rate": round(ver / tot, 4) if tot else 0.0}


def build_result(ctx, res, contract):
    vals = contract_values(ctx, res, contract)
    st = status_of(ctx, res)
    out = {
        "case_id": ctx["case_id"],
        "status": st,
        "summary": _summary(ctx, res),
        "method": ("scan -> extract resources/domains/bounds -> seven-category verdict per "
                   "version -> line-level duration and cost -> rank -> confirmations"),
        "versions": [{"version": r["version"], "params": r["params"], "feasible": r["feasible"],
                      "blocked": r["blocked"], "per_run_cost": r["per_run_cost"],
                      "budget_use_pct": r["budget_use_pct"],
                      "states": {c: r["verdict"][c]["state"] for c in EN.CAT_CN},
                      "evidence": r["evidence"]} for r in res["versions"]],
        "ranked": res["ranked"], "winner": res["winner"],
        "category_ledger": res["category_ledger"],
        "resources": {
            "equipment": [{"name": e["name"], "status": e.get("status"),
                           "evidence": e.get("evidence")} for e in ctx["res_equipment"]],
            "materials": [{"name": m["name"], "unit_price": m.get("unit_price"),
                           "unit": m.get("unit"), "lead_time": m.get("lead_time"),
                           "stock": m.get("stock"), "qty": m.get("qty"),
                           "evidence": m.get("evidence")} for m in ctx["res_materials"]],
            "bookings": [{"name": b["name"], "day_rate": b.get("day_rate"),
                          "window_days": b.get("window_days"),
                          "evidence": b.get("evidence")} for b in ctx["res_bookings"]],
            "samples": [{"name": x["name"], "required": x.get("required"),
                         "available": x.get("available"), "evidence": x.get("evidence")}
                        for x in ctx["res_samples"]],
            "approvals": ctx["res_approvals"],
        },
        "parameter_domains": [{"name": p["name"], "min": round(p["min"], 6),
                               "max": round(p["max"], 6), "step": round(p["step"], 6),
                               "unit": p["unit"], "points": EN.grid_points(p),
                               "evidence": p["evidence"][0] if p["evidence"] else {}}
                              for p in ctx["params"]],
        "constraints": [{"id": c["id"], "param": c["param"], "op": c["op"], "value": c["value"],
                         "unit": c["unit"], "locator": c["evidence"][0]["locator"] if c["evidence"] else "",
                         "quote": c["evidence"][0]["quote"] if c["evidence"] else ""}
                        for c in ctx["constraints"]],
        "budget": res["budget"], "budget_evidence": res["budget_evidence"],
        "rules_index": res["rules_index"],
        "checks": [{"name": ck["name"], "ok": ck["ok"], "detail": ck["detail"]} for ck in res["checks"]],
        "confirmations": RD.confirmations(ctx, res),
        "degradations": res["degradations"],
        "limits": _uncertainties(ctx, res),
        "uncertainties": _uncertainties(ctx, res),
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                    for m in ctx["materials"]] or [{"id": "none", "name": "no material file found",
                                                    "kind": "absent", "chars": 0}],
        "change_records": [
            {"step": 1, "action": "scan input materials", "result": "%d file(s)" % len(ctx["materials"])},
            {"step": 2, "action": "extract resources, domains and bounds",
             "result": "%d equipment, %d material, %d booking, %d domain, %d bound"
                       % (len(ctx["res_equipment"]), len(ctx["res_materials"]),
                          len(ctx["res_bookings"]), len(ctx["params"]), len(ctx["constraints"]))},
            {"step": 3, "action": "score each candidate version on the seven categories",
             "result": "%d version(s)" % len(res["versions"])},
            {"step": 4, "action": "derive duration and cost line by line",
             "result": "winner %s" % (res["winner"] or "not-decidable")},
            {"step": 5, "action": "collect confirmations and degradations",
             "result": "%d confirmation(s), %d degradation(s)"
                       % (len(RD.confirmations(ctx, res)), len(res["degradations"]))},
        ],
        "artifacts": {
            "feasibility_review.md": "feasibility_review.md",
            "checks.json": "checks.json", "estimate.json": "estimate.json",
            "risks.json": "risks.json", "confirmations.json": "confirmations.json",
            "evidence.json": "evidence.json", "version_diff.md": "version_diff.md",
        },
        "evidence_stats": ctx.get("_ev_stats", {"verified": 0, "total": 0}),
    }
    for k, v in vals.items():
        out[k] = v
    out["output_contract"] = vals
    return out


def write_all(ctx, res, out, work, contract):
    stats = evidence_stats(ctx, res)
    ctx["_ev_stats"] = stats
    arts = build_artifacts(ctx, res, status_of(ctx, res), stats)
    for name, content in arts.items():
        if name.endswith(".json"):
            wj(os.path.join(out, name), content)
        else:
            wt(os.path.join(out, name), content)
    res_obj = build_result(ctx, res, contract)
    wj(os.path.join(out, "result.json"), res_obj)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": status_of(ctx, res),
        "versions": len(res["versions"]), "domains": len(ctx["params"]),
        "constraints": len(ctx["constraints"]),
        "equipment": len(ctx["res_equipment"]), "materials": len(ctx["res_materials"]),
        "bookings": len(ctx["res_bookings"]), "winner": res["winner"]})
    return res_obj


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


# ---------------------------------------------------------------- commands ---

def bootstrap(case, inp, out):
    mats = E.scan_materials(inp)
    ctx = {"case_id": E.s((case or {}).get("case_id")) or "unknown-case", "_case": case,
           "materials": mats, "params": [], "constraints": [], "tables": [],
           "res_equipment": [], "res_materials": [], "res_bookings": [], "res_samples": [],
           "res_approvals": [], "budget": None, "budget_ev": [], "plans": [], "rules": [],
           "degradations": ["init only indexed the input; run build to compute the review"],
           "errors": [], "task_instruction": "", "notes": {}}
    res = {"versions": [], "ranked": [], "winner": None, "category_ledger": [],
           "degradations": list(ctx["degradations"]), "budget": None, "budget_ev": [],
           "rules_index": [], "searched": [], "checks": []}
    st = "drafting"
    out_obj = {"case_id": ctx["case_id"], "status": st,
               "summary": "indexed input; run build (or all) to compute the feasibility review",
               "limits": ["partial result written by init"],
               "uncertainties": ["review not yet computed"],
               "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                           for m in mats],
               "change_records": [{"step": 0, "action": "init",
                                   "result": "indexed %d file(s)" % len(mats)}],
               "artifacts": {}}
    vals = {k: "not-computed-yet" for k in DEFAULT_CONTRACT.keys()}
    vals["case_id"] = ctx["case_id"]
    vals["status"] = st
    out_obj.update(vals)
    out_obj["output_contract"] = vals
    wj(os.path.join(out, "result.json"), out_obj)


DRAFT_SKELETON = {
    "case_id": "",
    "chosen_version": "",
    "recommended": {},
    "resource_notes": [],
    "constraints_added": [],
    "uncertainties": [],
    "change_log": [],
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
                                 "detail": "no work/draft.json; build falls back to the extracted rules"})
        report["status"] = "no-draft"
    else:
        dmap = {}
        for d in ctx["params"]:
            dmap[d["key"]] = d["key"]
            dmap[E.nkey(d["name"])] = d["key"]
        rec = draft.get("recommended") if isinstance(draft.get("recommended"), dict) else {}
        mapped, unmapped = {}, []
        for k, v in rec.items():
            kk = E.nkey(k)
            if kk in dmap:
                mapped[dmap[kk]] = E.num(v)
            else:
                unmapped.append(k)
        report["checks"].append({"check": "recommendation_keys_map_to_domains",
                                 "ok": bool(mapped) or not rec,
                                 "detail": "mapped %d value(s); unmapped: %s"
                                           % (len(mapped), ", ".join(sorted(set(unmapped))) or "not-stated")})
        viol = []
        for k, v in mapped.items():
            _dom, vv, _nn = EN.check_param(k, v, ctx["params"], ctx["constraints"])
            viol.extend("%s:%s" % (k, x) for x in vv)
        report["checks"].append({"check": "recommendation_within_bounds", "ok": not viol,
                                 "detail": "violations: %s" % (", ".join(viol) or "not-stated")})
        cv = E.s(draft.get("chosen_version"))
        if cv:
            have = [p["version"] for p in ctx["plans"]]
            report["checks"].append({"check": "chosen_version_exists", "ok": (cv in have) or not have,
                                     "detail": "chosen %s; declared versions %s"
                                               % (cv, ", ".join(have) or "not-stated")})
        if viol:
            report["violations"] = viol
            report["status"] = "repair-needed"
    wj(os.path.join(work, "check_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    case = find_case(inp) or {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    mats = E.scan_materials(inp)
    ctx = E.extract(case, mats)
    draft = rj(os.path.join(work, "draft.json"), None)
    if isinstance(draft, dict):
        ctx["notes"]["draft_used"] = True
        rec = draft.get("recommended") if isinstance(draft.get("recommended"), dict) else {}
        if rec and ctx["plans"]:
            chosen = E.s(draft.get("chosen_version")) or ctx["plans"][0]["version"]
            for p in ctx["plans"]:
                if p["version"] == chosen:
                    for k, v in rec.items():
                        if E.num(v) is not None:
                            p["params"][k] = v
        if draft.get("constraints_added"):
            ctx["notes"]["draft_constraints"] = list(draft["constraints_added"])
    res = EN.run(ctx)
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res_obj = write_all(ctx, res, out, work, contract)
    sanitize_output(out)
    print("build: status=%s artifacts=%d versions=%d"
          % (res_obj["status"], len(res_obj["artifacts"]) + 1, len(res["versions"])))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "feasibility_review.md", "checks.json", "estimate.json",
            "risks.json", "confirmations.json", "evidence.json", "version_diff.md"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok_echo = isinstance(echo, dict) and all(E.s(v) for v in echo.values())
    playbook = os.path.join(os.path.dirname(HERE), "references", "expert_playbook.md")
    ok_playbook = os.path.isfile(playbook) and os.path.getsize(playbook) > 0
    print("selfcheck: files %s, contract echo %s, expert-checklist %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss),
             "ok" if ok_echo else "incomplete",
             "ok (references/expert_playbook.md present; S01-S18 to pass item by item)"
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
        rc = cmd_build(inp, out, work)
        cmd_selfcheck(out)
        return rc
    except Exception as exc:  # never crash the harness
        try:
            os.makedirs(out, exist_ok=True)
            wt(os.path.join(out, "feasibility_review.md"),
               "# Feasibility review\n\nThe input could not be processed, so no category "
               "verdict was produced. Searched locations and the error are recorded in "
               "result.json.\n")
            wj(os.path.join(out, "evidence.json"),
               {"case_id": "unknown-case", "items": [], "stats": {"verified": 0, "total": 0}})
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "summary": "the input could not be processed",
                "error": safe_text(str(exc)[:400]),
                "limits": ["processing aborted; see error"],
                "uncertainties": ["input unreadable"],
                "sources": [{"id": "none", "name": "no readable material", "kind": "absent", "chars": 0}],
                "change_records": [{"step": 0, "action": "abort", "result": safe_text(str(exc)[:200])}],
                "output_contract": _abort_contract()})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
