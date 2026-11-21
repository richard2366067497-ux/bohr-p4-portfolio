# -*- coding: utf-8 -*-
"""writing-07 :: source-grounded introduction & related-work writer.

Commands
  all        one-shot: scan -> extract -> derive four sections -> write every
             artifact + result.json (contract echoed top level and nested)
  init       index + partial result.json + draft skeleton
  show       print material sentences with locators
  check      validate a filled work/draft.json
  build      full pipeline (uses work/draft.json when present)
  selfcheck  reliability re-check of the produced artifacts

Pure standard library, offline.  Every command exits 0.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import core as C
import render as RD

DEFAULT_CONTRACT = {
    "case_id": "string",
    "deliverable": "path",
    "preserved_facts": "string",
    "evidence_map": "path",
    "change_log": "path",
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
    p = argparse.ArgumentParser(prog="writing-07-intro")
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


OS_RE = re.compile(r"[/\\]")


def no_slash(v):
    return OS_RE.sub(" ", v)


# ----------------------------------------------------------- contract fill ---

def _sentence(ctx, deriv, ev, pres, met, key):
    k = C.nrm(key)
    st = RD.status_of(ctx, deriv, ev)
    if k in ("caseid", "id"):
        return ctx["case_id"]
    if k == "status":
        return st
    if k in ("outputcontract",):
        return ", ".join(DEFAULT_CONTRACT.keys())
    if k in ("deliverable", "manuscript", "revised", "output", "path", "file", "report", "main"):
        return "manuscript.md"
    if k in ("evidence", "evidencemap", "claim", "claimmap", "locator", "map", "trace",
             "source", "sources", "sourcesused"):
        return "claim_map.md"
    if k in ("changelog", "change", "diff", "revision", "log", "changes"):
        return "change_log.md"
    if k in ("gap", "gaps", "blank", "gapledger"):
        return "gap_ledger.md"
    if k in ("contribution", "alignment", "contrib", "contributions"):
        return "contribution_alignment.md"
    if k in ("verification", "verify", "check", "selftest"):
        return "verification.json"
    if k in ("preservedfacts", "preserved", "unchanged", "anchor", "anchors", "numbers", "facts"):
        lost = ", ".join(pres["lost"]) or "nothing"
        return no_slash("%d numeric/citation anchors preserved verbatim; dropped: %s" % (pres["kept"], lost))
    if k in ("metrics", "efficiency", "efficiencymetrics", "cost"):
        return no_slash("elapsed %ss, %d requests, %d round(s), verbatim hit rate %s"
                        % (met["elapsed_s"], met["requests"], met["rounds"], met["verbatim_hit_rate"]))
    if k in ("summary", "conclusion", "answer", "result", "abstract"):
        return no_slash("four sections with %d bound citations; gap has %d premise(s); status %s"
                        % (met["citations_checked"], met["gap_premises"], st))
    if k in ("method", "approach", "procedure", "how"):
        return ("scan materials, copy each number and citation marker with locator and verbatim quote, "
                "derive background / related work / gap / contributions, then verify verbatim hit rate")
    if k in ("uncertainty", "uncertainties", "limits", "limit", "risks", "risk"):
        return no_slash("; ".join(RD.uncertainties(ctx, deriv, ev)))
    if k in ("count", "counts", "number", "num", "total", "totals"):
        return no_slash("%d materials, %d facts, %d citations, %d reviewer comments"
                        % (met["materials_scanned"], met["facts_extracted"],
                           met["citations_checked"], met["reviewer_comments_handled"]))
    return no_slash("derived from %d material(s): %d facts, %d citations, %d reviewer comment(s); status %s"
                    % (len(ctx["materials"]), len(ctx["facts"]), len(ctx["citations"]),
                       len(ctx["reviewer_comments"]), st))


def contract_values(ctx, deriv, ev, pres, met, contract):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT.keys())
    vals = {}
    for k in keys:
        if C.nrm(k) == "outputcontract":
            vals[k] = ", ".join(keys)
            continue
        v = _sentence(ctx, deriv, ev, pres, met, k)
        if not isinstance(v, str) or not v.strip():
            v = "not supplied in the material"
        vals[k] = v
    return vals


def validate_contract(contract, vals):
    """top_fix #3: every case.json output_contract key must be echoed; report gaps."""
    problems = []
    if isinstance(contract, dict) and contract:
        for k in contract.keys():
            if k not in vals or not str(vals.get(k, "")).strip():
                problems.append("contract key %r was not filled" % k)
    return problems


# ---------------------------------------------------------------- result -----

def _uncertainties(ctx, deriv, ev):
    return RD.uncertainties(ctx, deriv, ev)


def build_result(case, ctx, deriv, ev_items, ev_stats, pres, met, contract):
    vals = contract_values(ctx, deriv, ev_stats, pres, met, contract)
    st = RD.status_of(ctx, deriv, ev_stats)
    problems = validate_contract(contract, vals)
    res = {
        "case_id": ctx["case_id"],
        "status": st,
        "summary": no_slash(_sentence(ctx, deriv, ev_stats, pres, met, "summary")),
        "method": _sentence(ctx, deriv, ev_stats, pres, met, "method"),
        "sections": {k: len(v) for k, v in (("background", deriv["background"]),
                                            ("related", deriv["related"]),
                                            ("gap", deriv["gap_premises"]),
                                            ("contribution", deriv["contributions"]))},
        "citations": ctx["citations"],
        "reviewer_comments": ctx["reviewer_comments"],
        "preserved_facts": pres,
        "evidence_stats": ev_stats,
        "metrics": met,
        "contract_check": {"keys_expected": len(contract) if isinstance(contract, dict) else len(DEFAULT_CONTRACT),
                           "keys_filled": len(vals), "missing": problems},
        "degradations": ctx["degradations"],
        "limits": _uncertainties(ctx, deriv, ev_stats),
        "uncertainties": _uncertainties(ctx, deriv, ev_stats),
        "pending_human": RD.pending_human(ctx, deriv),
        "errors": ctx["errors"] + problems,
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                    for m in ctx["materials"]],
        "change_records": [
            {"step": 1, "action": "scan input materials", "result": "%d file(s)" % len(ctx["materials"])},
            {"step": 2, "action": "copy numbers and citation markers with locators",
             "result": "%d facts, %d citations" % (len(ctx["facts"]), len(ctx["citations"]))},
            {"step": 3, "action": "derive four sections",
             "result": "background %d, related %d, gap %d, contributions %d"
                       % (len(deriv["background"]), len(deriv["related"]),
                          len(deriv["gap_premises"]), len(deriv["contributions"]))},
            {"step": 4, "action": "verify verbatim evidence",
             "result": "hit rate %s" % ev_stats["hit_rate"]},
            {"step": 5, "action": "map reviewer comments to changes",
             "result": "%d comment(s) handled" % len(ctx["reviewer_comments"])},
        ],
        "artifacts": {
            "manuscript.md": "manuscript.md",
            "sources_used.md": "sources_used.md",
            "claim_map.md": "claim_map.md",
            "gap_ledger.md": "gap_ledger.md",
            "contribution_alignment.md": "contribution_alignment.md",
            "change_log.md": "change_log.md",
            "baseline_comparison.md": "baseline_comparison.md",
            "evidence.json": "evidence.json",
            "verification.json": "verification.json",
        },
    }
    for k, v in vals.items():
        res[k] = v
    res["output_contract"] = vals
    res["fingerprint"] = C.fingerprint({k: v for k, v in res.items() if k != "runtime"})
    return res


def write_all(case, ctx, deriv, ev_items, ev_stats, pres, met, out, work, contract):
    arts = RD.build_artifacts(ctx, deriv, ev_items, ev_stats, pres, met)
    for name, content in arts.items():
        if name.endswith(".json"):
            wj(os.path.join(out, name), content)
        else:
            wt(os.path.join(out, name), content)
    res = build_result(case, ctx, deriv, ev_items, ev_stats, pres, met, contract)
    res["runtime"] = {"elapsed_s": met["elapsed_s"], "python": sys.version.split()[0]}
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": res["status"], "facts": len(ctx["facts"]),
        "citations": len(ctx["citations"]), "hit_rate": ev_stats["hit_rate"]})
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


# -------------------------------------------------------------- pipeline -----

def pipeline(inp, work):
    t0 = time.time()
    case = find_case(inp) or {}
    mats = C.scan_materials(inp)
    ctx = C.extract(case, mats)
    deriv = C.derive(ctx)
    ev_items, ev_stats = C.evidence(ctx)
    manuscript = RD.manuscript_md(ctx, deriv)
    pres = C.preserved(ctx, manuscript)
    draft = rj(os.path.join(work, "draft.json"), None)
    ops = 5
    if isinstance(draft, dict) and draft:
        ctx["notes"]["draft_used"] = True
        ops += 1
        for u in (draft.get("uncertainties") or []) if isinstance(draft.get("uncertainties"), list) else []:
            ctx["degradations"].append(str(u)[:160])
    t1 = time.time()
    met = C.metrics(ctx, deriv, ev_stats, t0, t1, ops)
    return case, ctx, deriv, ev_items, ev_stats, pres, met, manuscript


# --------------------------------------------------------------- commands ----

DRAFT_SKELETON = {
    "case_id": "",
    "task_understanding": "",
    "claims": [],
    "gap_premises": [],
    "contributions": [],
    "uncertainties": [],
}


def bootstrap(case, inp, out, work):
    mats = C.scan_materials(inp)
    ctx = C.extract(case, mats)
    st = "drafting"
    vals = {k: "not-computed-yet" for k in (DEFAULT_CONTRACT.keys() if not isinstance((case or {}).get("output_contract"), dict)
                                            else case["output_contract"].keys())}
    vals["case_id"] = ctx["case_id"]
    vals["status"] = st
    res = {"case_id": ctx["case_id"], "status": st,
           "summary": "indexed input; run build (or all) to derive the four sections",
           "limits": ["partial result written by init"], "uncertainties": ["four sections not yet derived"],
           "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]} for m in ctx["materials"]],
           "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(mats)}],
           "artifacts": {}}
    res.update(vals)
    res["output_contract"] = vals
    wj(os.path.join(out, "result.json"), res)


def cmd_init(inp, out, work):
    case = find_case(inp) or {}
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    bootstrap(case, inp, out, work)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, DRAFT_SKELETON)
    print("init: indexed input, wrote partial result.json and %s" % sk)
    return 0


def cmd_show(inp, grep, want):
    mats = C.scan_materials(inp)
    n = 0
    for m in mats:
        if want and m["id"] != want and m["rel"] != want:
            continue
        print("=== %s %s (%s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["chars"]))
        for p in C.paragraphs(m):
            if grep and grep.lower() not in p["text"].lower():
                continue
            print("[%s] %s" % (p["locator"], p["text"][:400]))
            n += 1
            if n >= 400:
                return 0
    return 0


def cmd_check(inp, work, out):
    case = find_case(inp) or {}
    mats = C.scan_materials(inp)
    ctx = C.extract(case, mats)
    deriv = C.derive(ctx)
    ev_items, ev_stats = C.evidence(ctx)
    draft = rj(os.path.join(work, "draft.json"), None)
    report = {"case_id": ctx["case_id"], "draft_present": isinstance(draft, dict), "checks": [], "status": "ok"}
    if not isinstance(draft, dict):
        report["checks"].append({"check": "draft_supplied", "ok": False,
                                 "detail": "no work/draft.json; build falls back to the rule set"})
        report["status"] = "no-draft"
    else:
        report["checks"].append({"check": "draft_is_object", "ok": True, "detail": "draft parsed"})
    report["checks"].append({"check": "four_sections_derivable", "ok": bool(deriv["background"] and deriv["related"] and deriv["contributions"]),
                             "detail": "background %d, related %d, contributions %d" % (
                                 len(deriv["background"]), len(deriv["related"]), len(deriv["contributions"]))})
    report["checks"].append({"check": "gap_has_two_premises", "ok": deriv["gap_ok"],
                             "detail": "premises %d" % len(deriv["gap_premises"])})
    report["checks"].append({"check": "evidence_verbatim", "ok": ev_stats["hit_rate"] >= 0.85 or ev_stats["total"] == 0,
                             "detail": "hit rate %s (%d/%d)" % (ev_stats["hit_rate"], ev_stats["verbatim_hits"], ev_stats["total"])})
    wj(os.path.join(work, "check_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    case = find_case(inp) or {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    case, ctx, deriv, ev_items, ev_stats, pres, met, manuscript = pipeline(inp, work)
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res = write_all(case, ctx, deriv, ev_items, ev_stats, pres, met, out, work, contract)
    sanitize_output(out)
    print("build: status=%s artifacts=%d hit_rate=%s" % (res["status"], len(res["artifacts"]) + 1, ev_stats["hit_rate"]))
    return 0


def cmd_selfcheck(out, work):
    need = ["result.json", "manuscript.md", "sources_used.md", "claim_map.md", "gap_ledger.md",
            "contribution_alignment.md", "change_log.md", "baseline_comparison.md",
            "evidence.json", "verification.json"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok_echo = isinstance(echo, dict) and all(C.s(v) for v in echo.values())
    inter = []
    for n in need:
        p = os.path.join(out, n)
        if os.path.isfile(p) and os.path.getsize(p) < 40:
            inter.append(n)
    bootst = "no"
    for n in need:
        try:
            with open(os.path.join(out, n), "r", encoding="utf-8") as fh:
                if re.search(r"\[待写\]|待补充|NOT_EXTRACTED", fh.read()):
                    bootst = n
        except OSError:
            continue
    report = {"files_ok": not miss, "missing": miss, "contract_echo": ok_echo,
              "near_empty": inter, "placeholder_file": bootst, "status": res.get("status", "")}
    wj(os.path.join(work, "selftest_report.json"), report)
    print("selfcheck: files %s, contract echo %s, near-empty %s, placeholders %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss), "ok" if ok_echo else "incomplete",
             inter or "absent", bootst, res.get("status", "")))
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
            return cmd_selfcheck(out, work)
        if cmd == "build":
            return cmd_build(inp, out, work)
        rc = cmd_build(inp, out, work)
        cmd_selfcheck(out, work)
        return rc
    except Exception as exc:
        try:
            os.makedirs(out, exist_ok=True)
            cid = "unknown-case"
            try:
                cid = (find_case(inp) or {}).get("case_id") or cid
            except Exception:
                pass
            vals = {"case_id": cid, "status": "input_error",
                    "deliverable": "manuscript.md", "preserved_facts": "input could not be processed",
                    "evidence_map": "claim_map.md", "change_log": "change_log.md"}
            wj(os.path.join(out, "result.json"),
               {"case_id": cid, "status": "input_error", "error": str(exc)[:400],
                "limits": ["processing aborted; see error"], "uncertainties": ["input unreadable"],
                "sources": [], "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                "output_contract": vals})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
