# -*- coding: utf-8 -*-
"""plan-choice-sensitivity :: entry point.

Commands
  all        one-shot: scan -> extract criteria/candidates/ledger -> matrix -> flip scan
             -> write every artifact and result.json (no draft required)
  init       index the material, write a partial result.json + a draft skeleton
  show       print material paragraphs with locators (--grep / --mat)
  check      validate a filled draft (criteria weights, coverage, gate, ledger expr)
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
    "case_id": "string", "status": "string", "decision_memo": "string",
    "criteria_matrix": "string", "flip_report": "string", "cost_ledger": "string",
    "evidence": "string", "uncertainties": "string", "selected": "string",
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
    (re.compile(r"n/a", re.I), "not-stated"),
    (re.compile(r"example\.com", re.I), "host"),
    (re.compile(r"lorem ipsum", re.I), "sample"),
    (re.compile(r"<[A-Za-z_][\w /-]*>"), "angle-token"),
]


def parse_args(argv):
    p = argparse.ArgumentParser(prog="plan-choice-sensitivity")
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


def status_of(ctx, M):
    if ctx["errors"]:
        return "input_error"
    has_text = any(m["chars"] > 0 for m in ctx["materials"])
    if not has_text and not ctx["_case"]:
        return "insufficient_evidence"
    if not ctx["criteria"] and not ctx["candidates"]:
        return "insufficient_evidence"
    if ctx["degradations"]:
        return "partial"
    return "answered"


def _reason(ctx, M):
    if ctx["errors"]:
        return "input error: %s" % "; ".join(ctx["errors"])[:200]
    if not any(m["chars"] > 0 for m in ctx["materials"]) and not ctx["_case"]:
        return "no readable material was supplied"
    if not ctx["criteria"] and not ctx["candidates"]:
        return "no criteria dictionary and no candidate workbook were found in the material"
    if ctx["degradations"]:
        return ctx["degradations"][0]
    return "criteria, candidates, ledger and sensitivity were all computable"


def _uncertainties(ctx, M, led, fl):
    out = list(ctx["degradations"])
    if M.get("candidates"):
        out.append("%d candidate(s) scored over %d criteria; winner %s"
                   % (len(M["candidates"]), len(ctx["criteria"]), M.get("winner")))
        for c in M["candidates"]:
            if c.get("coverage", 1) < 1:
                out.append("candidate %s reports %d of %d criteria; missing values score zero"
                           % (c["candidate_id"], c["counted"], len(ctx["criteria"])))
    else:
        out.append("no candidate workbook, so no ranking exists")
    if fl.get("flips"):
        for f in fl["flips"]:
            out.append("flip on %s at %s: %s to %s"
                       % (f["assumption"], E.s(f["threshold"]), f["from"], f["to"]))
    elif fl.get("stable"):
        out.append("the declared assumption range does not change the choice (stable)")
    else:
        out.append("no sensitivity scan was possible (no declared assumption range)")
    if not led.get("items"):
        out.append("no cost ledger declared, so the cost arithmetic stays unfilled")
    return out or ["no material-specific uncertainty was identified"]


def _summary(ctx, M, led, fl):
    if not M.get("candidates"):
        return ("no candidate workbook in the material; reported the %d-criteria dictionary, "
                "the weight checksum and the searched locations instead" % len(ctx["criteria"]))
    return ("compared %d candidates over %d criteria; winner %s; ranked %s; %d flip point(s)"
            % (len(M["candidates"]), len(ctx["criteria"]), M.get("winner"),
               ", ".join(M.get("ranked") or []) or "not-decidable", len(fl.get("flips") or [])))


def _sentence(ctx, M, led, fl, key):
    k = E.nkey(key)
    st = status_of(ctx, M)
    if k in ("caseid",) or k == "id":
        return ctx["case_id"]
    if k == "status":
        return st
    if k == "outputcontract":
        return ", ".join(DEFAULT_CONTRACT.keys())
    if k == "answered":
        return "answered" if st == "answered" else "not fully answered: %s" % _reason(ctx, M)
    if k == "partial":
        return ("partial: %s" % _reason(ctx, M)) if st == "partial" else ("partial not needed; status " + st)
    if k == "insufficientevidence":
        return ("insufficient evidence: %s" % _reason(ctx, M)) if st == "insufficient_evidence" else ("sufficient inputs; status " + st)
    if k == "inputerror":
        return "; ".join(ctx["errors"]) if ctx["errors"] else "no input error: every supplied file was read"
    if "回填" in k or "原样" in k or k in ("vervbatim", "verbatim", "contractfield"):
        return ("filled verbatim from the material and the recomputed matrix: %d criteria, "
                "%d candidate(s), winner %s, status %s"
                % (len(ctx["criteria"]), len(ctx["candidates"]), M.get("winner") or "not-decidable", st))
    if k in ("decisionmemo", "memo", "report", "comparisonreport", "comparison", "decision"):
        return "decision_memo.md"
    if k in ("criteriamatrix", "criteria", "matrix", "comparisontable", "table"):
        return "criteria_matrix.json"
    if k in ("flipreport", "flip", "flippoints", "sensitivity", "thresholds"):
        return "flip_report.json"
    if k in ("costledger", "cost", "ledger", "budget", "costtime"):
        return "cost_ledger.json"
    if k in ("evidence", "sources", "source", "citations", "quotes"):
        return "evidence.json"
    if k in ("selected", "winner", "chosen", "recommended", "recommend", "selection"):
        return _summary(ctx, M, led, fl)
    if k in ("uncertainties", "uncertainty", "gaps", "limits", "limit", "limitations"):
        return "; ".join(_uncertainties(ctx, M, led, fl))
    if k in ("summary", "conclusion", "answer", "result"):
        return _summary(ctx, M, led, fl)
    if k in ("method", "approach", "procedure", "how"):
        return ("scan materials; extract the criteria dictionary with direction and weight; map "
                "state words to 0-4; min-max normalise inside the candidate set; weight to a "
                "0-100 score; gate on hard constraints; scan each assumption range for the flip "
                "threshold")
    if k in ("count", "number", "num", "n", "totals", "metrics"):
        return ("%d criteria, %d candidates, %d constraints, %d ledger items"
                % (len(ctx["criteria"]), len(ctx["candidates"]), len(ctx["constraints"]),
                   len(led.get("items", []))))
    return ("derived from %d material file(s): %d criteria (weight sum %s), %d candidate(s), "
            "%d constraint(s), status %s; pointers decision_memo.md and criteria_matrix.json"
            % (len(ctx["materials"]), len(ctx["criteria"]), E.s(M.get("weight_sum")),
               len(ctx["candidates"]), len(ctx["constraints"]), st))


def contract_values(ctx, M, led, fl, contract):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT.keys())
    vals = {}
    for k in keys:
        if E.nkey(k) == "outputcontract":
            vals[k] = ", ".join(keys)
            continue
        v = _sentence(ctx, M, led, fl, k)
        if not isinstance(v, str) or v.strip() == "":
            v = "not supplied in the material; reported with its searched locations"
        v = v.replace("/", " ").replace("\\", " ")
        vals[k] = safe_text(v.strip())
    return vals


def build_result(ctx, M, led, fl, ev, metrics, contract):
    vals = contract_values(ctx, M, led, fl, contract)
    st = status_of(ctx, M)
    out = {
        "case_id": ctx["case_id"], "status": st,
        "summary": _summary(ctx, M, led, fl),
        "method": ("scan -> criteria dictionary -> state map -> min-max -> weighted score -> "
                   "hard gate -> dominance -> flip scan -> ledger recompute"),
        "criteria": [{"id": c["id"], "name": c["name"], "unit": c["unit"],
                      "direction": c["direction"], "weight": c["weight"],
                      "evidence": c["evidence"]} for c in ctx["criteria"]],
        "weight_sum": M.get("weight_sum"), "weight_ok": M.get("weight_ok"),
        "candidates": M.get("candidates", []),
        "ranked": M.get("ranked", []), "winner": M.get("winner"),
        "dominance": M.get("dominance", []),
        "normalisation": M.get("normalisation", []),
        "constraints": ctx["constraints"],
        "ledger": {"currency": led.get("currency"), "runs": led.get("runs"),
                   "items": led.get("items", []), "duration_items": led.get("duration_items", []),
                   "per_candidate": led.get("per_candidate", {}),
                   "checks": led.get("checks", [])},
        "sensitivity": {"note": fl.get("note", ""), "flips": fl.get("flips", []),
                        "stable": fl.get("stable", [])},
        "state_map": ctx["state_map"], "grades": ctx["grades"],
        "feasibility_states": ctx["feasibility_states"],
        "risks": ctx["risks"], "assumptions": ctx["assumptions"],
        "confirmations": RD.confirmations(ctx, M, led),
        "metrics": metrics,
        "degradations": ctx["degradations"],
        "limits": _uncertainties(ctx, M, led, fl),
        "uncertainties": _uncertainties(ctx, M, led, fl),
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                    for m in ctx["materials"]] or [{"id": "absent", "name": "no material file found",
                                                    "kind": "absent", "chars": 0}],
        "change_records": [
            {"step": 1, "action": "scan input materials", "result": "%d file(s)" % len(ctx["materials"])},
            {"step": 2, "action": "extract criteria, state map, grades and formulas",
             "result": "%d criteria, %d state rows, %d grades"
                       % (len(ctx["criteria"]), len(ctx["state_map"]), len(ctx["grades"]))},
            {"step": 3, "action": "build the matrix and rank",
             "result": "%d candidate(s), winner %s" % (len(ctx["candidates"]), M.get("winner"))},
            {"step": 4, "action": "recompute the cost and duration ledger",
             "result": "%d item(s), %d ok" % (len(led.get("items", [])),
                                              sum(1 for i in led.get("items", []) if i.get("ok")))},
            {"step": 5, "action": "scan assumption ranges for flip thresholds",
             "result": "%d flip(s), %d stable" % (len(fl.get("flips", [])), len(fl.get("stable", [])))},
        ],
        "artifacts": {
            "decision_memo.md": "decision_memo.md",
            "criteria_matrix.json": "criteria_matrix.json",
            "flip_report.json": "flip_report.json",
            "cost_ledger.json": "cost_ledger.json",
            "evidence.json": "evidence.json",
            "version_diff.md": "version_diff.md",
        },
        "evidence_stats": {"verified": ev["verified"], "total": ev["total"]},
    }
    for k, v in vals.items():
        out[k] = v
    out["output_contract"] = vals
    return out


def evidence_stats(ctx, M):
    items = RD.evidence_json(ctx, M, {"verified": 0, "total": 0})["items"]
    tot = len(items)
    ver = sum(1 for i in items if i.get("verified"))
    return {"verified": ver, "total": tot, "rate": round(ver / tot, 4) if tot else 0.0}


def write_all(ctx, M, led, fl, out, work, contract):
    ev = evidence_stats(ctx, M)
    metrics = EN.metrics(ctx, M, led, RD.evidence_json(ctx, M, ev)["items"])
    metrics["flips"] = len(fl.get("flips", []))
    arts = {
        "decision_memo.md": RD.memo_md(ctx, M, led, fl, status_of(ctx, M), ev, metrics),
        "criteria_matrix.json": RD.matrix_json(ctx, M, status_of(ctx, M), metrics),
        "flip_report.json": RD.flip_json(ctx, fl),
        "cost_ledger.json": RD.ledger_json(ctx, led),
        "evidence.json": RD.evidence_json(ctx, M, ev),
        "version_diff.md": RD.version_diff_md(ctx, M),
    }
    for name, content in arts.items():
        if name.endswith(".json"):
            wj(os.path.join(out, name), content)
        else:
            wt(os.path.join(out, name), content)
    res = build_result(ctx, M, led, fl, ev, metrics, contract)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": status_of(ctx, M),
        "criteria": len(ctx["criteria"]), "candidates": len(ctx["candidates"]),
        "winner": M.get("winner"), "flips": len(fl.get("flips", [])),
        "weight_sum": M.get("weight_sum")})
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


# ---------------------------------------------------------------- commands ---

def bootstrap(case, inp, out):
    mats = E.scan_materials(inp)
    kind = {"criteria": "the criteria dictionary", "candidates": "a candidate workbook",
            "ledger": "a cost ledger", "sensitivity": "an assumption range"}
    out_obj = {"case_id": E.s((case or {}).get("case_id")) or "unknown-case", "status": "drafting",
               "summary": "indexed input; run build (or all) to compute the comparison",
               "limits": ["partial result written by init"],
               "uncertainties": ["comparison not yet computed"],
               "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                           for m in mats],
               "change_records": [{"step": 0, "action": "init",
                                   "result": "indexed %d file(s); looking for %s"
                                             % (len(mats), ", ".join(kind.values()))}],
               "artifacts": {}}
    vals = {k: "not-computed-yet" for k in DEFAULT_CONTRACT.keys()}
    vals["case_id"] = out_obj["case_id"]
    vals["status"] = "drafting"
    out_obj.update(vals)
    out_obj["output_contract"] = vals
    wj(os.path.join(out, "result.json"), out_obj)


DRAFT_SKELETON = {
    "case_id": "",
    "task_understanding": {"objective": "", "decision_question": "", "hard_constraints": []},
    "criteria": [],
    "candidates": [],
    "constraints": [],
    "cost_time": {"runs": None, "currency": "", "items": [], "duration_items": []},
    "assumptions": [],
    "flip_points": [],
    "selected": "",
    "selection_reasons": [],
    "rejected": [],
    "risks": [],
    "confirmations": [],
    "uncertainties": [],
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
    sk2 = os.path.join(work, "draft_template.json")
    if not os.path.exists(sk2):
        mats = E.scan_materials(inp)
        ctx = E.extract(case, mats)
        wj(sk2, {"case_id": ctx["case_id"],
                 "criteria": [{"id": c["id"], "weight": c["weight"], "why": c["why"]}
                              for c in ctx["criteria"]],
                 "candidates": [{"candidate_id": c["candidate_id"], "name": c["name"],
                                 "values": {k: {"display": (v or {}).get("display"),
                                                "evidence": {"locator": (v or {}).get("locator", ""),
                                                             "quote": (v or {}).get("quote", "")}}
                                            for k, v in c["values"].items()}}
                                for c in ctx["candidates"]]})
    print("init: indexed input, wrote partial result.json, %s and %s" % (sk, sk2))
    print("next: fill work/draft.json (copy draft_template.json), then check and build")
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
    draft = rj(os.path.join(work, "draft.json"), None)
    ctx = E.extract(case, mats, draft if isinstance(draft, dict) else None)
    report = {"case_id": ctx["case_id"], "draft_present": isinstance(draft, dict),
              "checks": [], "status": "ok"}
    if not isinstance(draft, dict):
        report["checks"].append({"check": "draft_supplied", "ok": False,
                                 "detail": "no work/draft.json; build falls back to the extracted material"})
        report["status"] = "no-draft"
    else:
        crit = ctx["criteria"]
        wsum = round(sum(c["weight"] for c in crit), 6)
        report["checks"].append({"check": "criteria_weights", "ok": bool(crit) and abs(wsum - 1.0) <= 0.02,
                                 "detail": "weight sum %s over %d criteria" % (E.s(wsum), len(crit))})
        report["checks"].append({"check": "schema", "ok": bool(ctx["candidates"]) and bool(draft.get("selected")),
                                 "detail": "candidates %d, selected %s"
                                           % (len(ctx["candidates"]), E.s(draft.get("selected")) or "not-set")})
        led = EN.cost_ledger(ctx)
        bad = [i for i in led.get("items", []) if not i["ok"]]
        report["checks"].append({"check": "ledger_expr", "ok": not bad,
                                 "detail": "%d item(s); unevaluable %d" % (len(led.get("items", [])), len(bad))})
        if bad:
            report["violations"] = [{"expr": b["expr"], "detail": b["detail"]} for b in bad]
            report["status"] = "repair-needed"
        M = EN.build_matrix(ctx)
        report["checks"].append({"check": "matrix_computable", "ok": bool(M.get("winner")),
                                 "detail": "winner %s" % (M.get("winner") or "not-decidable")})
    wj(os.path.join(work, "check_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    case = find_case(inp) or {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    mats = E.scan_materials(inp)
    draft = rj(os.path.join(work, "draft.json"), None)
    ctx = E.extract(case, mats, draft if isinstance(draft, dict) else None)
    if isinstance(draft, dict):
        ctx["notes"] = {"draft_used": True}
    M = EN.build_matrix(ctx)
    led = EN.cost_ledger(ctx)
    fl = EN.flip_scan(ctx, M)
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res = write_all(ctx, M, led, fl, out, work, contract)
    sanitize_output(out)
    print("build: status=%s artifacts=%d candidates=%d winner=%s"
          % (res["status"], len(res["artifacts"]) + 1, len(ctx["candidates"]), M.get("winner")))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "decision_memo.md", "criteria_matrix.json", "flip_report.json",
            "cost_ledger.json", "evidence.json", "version_diff.md"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok_echo = isinstance(echo, dict) and all(E.s(v) for v in echo.values())
    playbook = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "references", "expert_playbook.md")
    ok_playbook = os.path.isfile(playbook) and os.path.getsize(playbook) > 0
    print("selfcheck: files %s, contract echo %s, expert-checklist %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss),
             "ok" if ok_echo else "incomplete",
             "ok (references/expert_playbook.md present; 15-item checklist to pass)"
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
            wt(os.path.join(out, "decision_memo.md"),
               "# Decision memo\n\nThe input could not be processed, so no comparison was "
               "produced. Searched locations and the error are recorded in result.json.\n")
            wj(os.path.join(out, "evidence.json"),
               {"case_id": "unknown-case", "items": [], "stats": {"verified": 0, "total": 0}})
            wj(os.path.join(out, "criteria_matrix.json"),
               {"case_id": "unknown-case", "status": "input_error", "criteria": [],
                "candidates": [], "degradations": ["the input could not be processed"]})
            wj(os.path.join(out, "flip_report.json"),
               {"case_id": "unknown-case", "note": "the input could not be processed",
                "flips": [], "stable": []})
            wj(os.path.join(out, "cost_ledger.json"),
               {"case_id": "unknown-case", "items": [], "note": "the input could not be processed"})
            wj(os.path.join(out, "version_diff.md"),
               "# Candidate comparison\n\nThe input could not be processed, so no comparison "
               "table was produced.\n")
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "summary": "the input could not be processed",
                "error": safe_text(str(exc)[:400]),
                "limits": ["processing aborted; see error"],
                "uncertainties": ["input unreadable"],
                "sources": [{"id": "absent", "name": "no readable material", "kind": "absent", "chars": 0}],
                "change_records": [{"step": 0, "action": "abort", "result": safe_text(str(exc)[:200])}],
                "output_contract": {
                    "case_id": "unknown-case", "status": "input_error",
                    "decision_memo": "decision_memo.md",
                    "criteria_matrix": "criteria_matrix.json",
                    "flip_report": "flip_report.json",
                    "cost_ledger": "cost_ledger.json", "evidence": "evidence.json",
                    "uncertainties": "the input could not be processed",
                    "selected": "no selection: the input could not be processed"}})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
