#!/usr/bin/env python3
"""litread-bench-ledger CLI: init | show | check | build | selfcheck.

Exit code is always 0: failures land inside result.json (errors / degradations),
never in the process status. Paths derive from __file__, so the CLI does not
depend on the current working directory.
"""
import argparse
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True  # keep the installed skill directory free of __pycache__

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import core as C      # noqa: E402
import ledger as G    # noqa: E402
import litio as L     # noqa: E402


def load_draft(explicit=None):
    cands = ([Path(explicit)] if explicit else []) + [L.WORK / "draft.json",
                                                     L.WORK / "plan.json"]
    for p in cands:
        if p.is_file():
            try:
                o = L.rj(p)
                return p, (o if isinstance(o, dict) else {"items": o}), None
            except Exception as e:
                return p, None, "draft %s is not valid JSON: %s" % (p.name, e)
    return None, None, "no draft at %s" % (L.WORK / "draft.json")


def cmd_init(a):
    case, cp = L.load_case(L.INPUT)
    res, con = L.prep("init", case)
    task_txt, _ = L.read_task_md(L.INPUT)
    print("== litread-bench-ledger %s | init ==" % L.V)
    print("input : %s\noutput: %s\nwork  : %s\ncase  : %s" % (L.INPUT, L.OUTPUT, L.WORK, cp or "NOT FOUND"))
    if "_bad_json" in case:
        res["errors"].append({"stage": "case", "error": "case.json unreadable: " + case["_bad_json"]})
        print("! case.json is not valid JSON -> partial mode, materials still indexed")
    keys = L.ckeys(con)
    print("contract fields (%d): %s" % (len(keys), ", ".join(keys) or "NONE FOUND"))
    instr = L.dget(case, L.TASKK) or (L.nm(task_txt)[:400] if task_txt else None)
    print("task_instruction: %s" % (L.nm(str(instr))[:300] if instr else "(none)"))
    idx = L.scan(L.INPUT)
    L.wj(L.WORK / "index.json", idx)
    for m in idx["materials"]:
        print("  %-4s %-30s %-6s paras=%-3d chars=%-6d %s%s"
              % (m["mid"], m["name"][:30], m["kind"], len(m["paragraphs"]), m["chars"],
                 m["status"], ("  ! " + m["note"]) if m["note"] else ""))
    print("MATERIALS %d | paragraphs %d" % (len(idx["materials"]), idx["n_paragraphs"]))
    wo = L.workorder(case)
    L.wj(L.WORK / "workorder.json",
         {"schema": L.NM + "/workorder@1", "items": wo, "generated_at": L.now()})
    print("WORKORDER items: %d" % len(wo))
    for w in wo:
        print("  %-5s %-10s %s" % (w["item_id"], str(w["task_type"])[:10],
                                   L.nm(w["task"])[:90] or "(no task text)"))
    cands = L.candidates(case)
    print("CANDIDATE outputs: %d %s" % (len(cands), [x["output_id"] for x in cands] or ""))
    res.update({"errors": res["errors"] + idx["errors"], "degradations": idx["degradations"],
                "sources": L.srcs(idx),
                "benchmark": {"stage": "indexed", "materials": len(idx["materials"]),
                              "paragraphs": idx["n_paragraphs"], "n_items": 0,
                              "workorder_items": len(wo)},
                "technical_synthetic": L.checker_note(),
                "uncertainty": (["no case.json found; contract fields unknown"] if not cp else [])
                + ["material parse degraded: " + m["mid"] for m in idx["materials"] if m["note"]]
                + ["cards not authored yet; write %s" % (L.WORK / "draft.json")],
                "pending_human": ["author work/draft.json from `show` output, then check/build"]})
    L.save(res, "init")
    print("partial result.json written: %s (legal, all contract keys present)" % (L.OUTPUT / "result.json"))
    print("NEXT: main.py show%s | write work/draft.json | main.py check | main.py build"
          % ((" --material " + idx["materials"][0]["mid"]) if idx["materials"] else ""))


def cmd_show(a):
    case, _ = L.load_case(L.INPUT)
    res, con = L.prep("show", case)
    idx = L.get_index(res)
    wo = (L.rj(L.WORK / "workorder.json").get("items")
          if (L.WORK / "workorder.json").is_file() else L.workorder(case))
    if a.item:
        hit = [x for x in wo if x["item_id"].lower() == a.item.lower()]
        if not hit:
            print("! workorder item %s not found (have: %s)"
                  % (a.item, ", ".join(x["item_id"] for x in wo) or "none"))
            res["errors"].append({"stage": "show", "error": "item %s not found" % a.item})
        for w in hit:
            print("ITEM %s | type=%s | difficulty=%s | license=%s"
                  % (w["item_id"], w["task_type"], w["difficulty"], w["license"]))
            print("task: %s" % (w["task"] or "(empty)"))
            print("reference_answer: %s"
                  % ("MISSING (do not invent)" if w["reference_missing"]
                     else str(w["reference_answer"])[:400]))
            for r in w["source_refs"]:
                print("  source_ref: %s" % L.nm(str(r))[:200])
        L.save(res, "show")
        return
    if a.material:
        ms = {m["mid"]: m for m in idx.get("materials", [])}
        key = next((k for k in ms if k.lower() == a.material.lower()), None)
        if not key:
            print("! material %s not found. available: %s" % (a.material, ", ".join(ms) or "none"))
            res["errors"].append({"stage": "show", "error": "material %s not found" % a.material})
            for m in idx.get("materials", []):
                print("  %-4s %-30s paras=%d chars=%d"
                      % (m["mid"], m["name"][:30], len(m["paragraphs"]), m["chars"]))
        else:
            m, st = ms[key], max(1, a.start)
            end = st + max(1, a.limit)
            print("MATERIAL %s | %s | %s | %d paragraphs | %d chars"
                  % (m["mid"], m["name"], m["kind"], len(m["paragraphs"]), m["chars"]))
            for p in m["paragraphs"][st - 1:end - 1]:
                print("\n[%s%s] (%d chars)%s"
                      % (p["pid"], (" p.%d" % p["page"]) if p.get("page") else "", len(p["text"]),
                         ("  native_id=%s" % p["native_id"]) if p.get("native_id") else ""))
                print(p["text"][:1400])
            if end - 1 < len(m["paragraphs"]):
                print("\n... next: --material %s --start %d" % (m["mid"], end))
        L.save(res, "show")
        return
    print("== overview ==")
    print("contract: %s" % (", ".join(L.ckeys(con)) or "NONE"))
    for m in idx.get("materials", []):
        print("  %-4s %-32s %-6s paras=%-3d chars=%-6d %s%s"
              % (m["mid"], m["name"][:32], m["kind"], len(m["paragraphs"]), m["chars"],
                 m["status"], ("  ! " + m["note"]) if m["note"] else ""))
    print("WORKORDER (%d):" % len(wo))
    for w in wo:
        print("  %-5s %-10s %s" % (w["item_id"], str(w["task_type"])[:10],
                                   L.nm(w["task"])[:90] or "(no task text)"))
    if not wo:
        print("  (none -> author cards from the materials yourself)")
    print("read: main.py show --material M01 --start 1 --limit 20")
    L.save(res, "show")


def cmd_check(a):
    case, _ = L.load_case(L.INPUT)
    res, con = L.prep("check", case)
    idx = L.get_index(res)
    c = L.cache(idx)
    wo = (L.rj(L.WORK / "workorder.json").get("items")
          if (L.WORK / "workorder.json").is_file() else [])
    path, draft, err = load_draft(a.draft)
    print("== check ==")
    if err:
        print("! %s\n  -> authoring required; build would fall back to minimal cards" % err)
        L.wj(L.WORK / "check_report.json",
             {"ok": False, "n_items": 0, "issues": [{"level": "error", "msg": err}],
              "warnings": [], "rejected": []})
        res.update({"errors": [{"stage": "check", "error": err}],
                    "pending_human": ["write work/draft.json (see references/item-card-schema.md)"]})
        L.save(res, "check")
        print("RESULT: FAIL (no draft)")
        return
    rep = C.validate(draft, c, wo, (draft.get("set_meta") or {}).get("uncovered"))
    rep.update({"draft": str(path), "checked_at": L.now()})
    L.wj(L.WORK / "check_report.json", rep)
    print("draft: %s | raw=%d accepted=%d rejected=%d"
          % (path.name, rep["n_raw"], len(rep["items"]), len(rep["rejected"])))
    nrefs = sum(len(i["source_refs"]) for i in rep["items"])
    nver = sum(1 for i in rep["items"] for r in i["source_refs"] if (r.get("_v") or {}).get("verified"))
    print("quotes verified: %d/%d refs on accepted cards" % (nver, nrefs))
    for x in rep["issues"]:
        print("  ERROR %-5s %s" % (x.get("item", "-"), x["msg"]))
    for w in rep["warnings"][:25]:
        print("  WARN  %-5s %s" % (w.get("item", "-"), w["msg"]))
    if rep["warnings"][25:]:
        print("  ... %d more warnings in work/check_report.json" % len(rep["warnings"][25:]))
    keys = L.ckeys(con)
    print("contract: %d fields -> %s" % (len(keys), ", ".join(keys) or "NONE"))
    res.update({"errors": [{"stage": "check", "item": x.get("item"), "error": x["msg"]}
                           for x in rep["issues"]][:20],
                "degradations": ([{"item": "check", "issue": "%d card(s) rejected" % len(rep["rejected"]),
                                   "action": "excluded from scoring, kept in failures.md"}]
                                 if rep["rejected"] else []),
                "pending_human": (["fix %d check error(s) before build" % len(rep["issues"])]
                                  if rep["issues"] else []),
                "benchmark": {"stage": "checked", "n_items": len(rep["items"]),
                              "n_rejected": len(rep["rejected"]), "n_refs": nrefs,
                              "n_refs_verified": nver}})
    L.save(res, "check")
    print("RESULT: %s" % ("PASS" if not rep["issues"] else
                          "FAIL (build keeps only valid cards and adds fallback)"))


def cmd_build(a):
    case, _ = L.load_case(L.INPUT)
    res, con = L.prep("build", case)
    cid = L.dget(case, L.IDK)
    cid = str(cid) if cid else None
    idx = L.get_index(res)
    c = L.cache(idx)
    wo = (L.rj(L.WORK / "workorder.json").get("items")
          if (L.WORK / "workorder.json").is_file() else L.workorder(case))
    if "_bad_json" in case:
        res["errors"].append({"stage": "case", "error": "case.json unreadable: " + case["_bad_json"]})
    path, draft, err = load_draft(a.draft)
    set_meta = (draft or {}).get("set_meta") or {}
    items, rejected, issues, warns, wc = [], [], [], [], []
    mode = "agent_authored"
    if err:
        print("! %s" % err)
        res["degradations"].append({"item": "draft", "issue": err,
                                    "action": "deterministic fallback cards from real paragraphs"})
    else:
        rep = C.validate(draft, c, wo, set_meta.get("uncovered"))
        items, rejected, issues, warns, wc = (rep["items"], rep["rejected"], rep["issues"],
                                             rep["warnings"], rep["workorder_coverage"])
        print("draft %s | accepted=%d rejected=%d errors=%d"
              % (path.name, len(items), len(rejected), len(issues)))
    if not items:
        mode = "fallback_minimal"
        for n, raw in enumerate(C.fallback_items(idx, 6), 1):
            it = C.norm_item(raw, n)
            for ref in it["source_refs"]:
                v = L.verify(c, ref["material"], ref["quote"])
                ref["_v"] = v
                if v.get("verified"):
                    ref["locator"] = v.get("pid") or ref["locator"]
            it["_anchors_ok"] = any((r.get("_v") or {}).get("verified") for r in it["source_refs"])
            if it["_anchors_ok"]:
                items.append(it)
        res["degradations"].append({"item": "benchmark",
                                    "issue": "no usable agent draft" if err else "all cards rejected",
                                    "action": "generated %d minimal extractive cards" % len(items)})
    elif rejected:
        mode = "agent_authored_with_fallback"
    A = G.build_set(case, cid, idx, c, items, rejected, issues, warns, wc, set_meta, mode)
    dep = list(res.get("degradations") or []) + list(idx.get("degradations") or [])
    status = ("input_error" if not idx["materials"] else
              "insufficient_evidence" if not idx["n_paragraphs"] else
              "ok" if (mode == "agent_authored" and not issues and not rejected
                       and A["cm"]["verdict"] == "ok" and A["cal"]["n_disagree"] == 0)
              else "partial")
    claims = [{"claim": "statement appears verbatim at %s / %s" % (x["material"], x["locator"]),
               "item_id": x["item_id"], "locator": x["locator"], "quote": x["quote"],
               "verified": x["verified"]} for x in A["anchors"]][:40]
    score_map = {r["item_id"]: r["score"] for r in A["rows"]
                 if r["agent"] == "calibration_probe" and r["score"] is not None}
    ctx = {"case_id": cid, "status": status, "sources": L.srcs(idx),
           "result": {"set_id": A["cards"]["set_id"], "set_version": A["cards"]["set_version"],
                      "mode": mode, "n_items": len(items),
                      "items": [{"item_id": i["item_id"], "task_type": i["task_type"],
                                 "question": i["question"],
                                 "reference_answer": i["reference_answer"],
                                 "reference_missing": i["reference_missing"],
                                 "scoring_rule": i["scoring_rule"]} for i in items],
                      "scores": score_map,
                      "aggregate": {k: A["agg"][k] for k in ("n_rows", "n_scored", "mean",
                                                             "distribution", "judgeable_rate")},
                      "panel": "benchmark/panel.md", "failures": "benchmark/failures.md"},
           "claims": claims, "uncertainty": A["unc"],
           "anchors": {"n": A["n_anchors"], "n_verified": A["n_verified"],
                       "anchors": A["anchors"][:60]},
           "scoring": A["agg"], "failures": A["fails"], "version_record": A["ver"],
           "benchmark": {"set_id": A["cards"]["set_id"], "set_version": A["cards"]["set_version"],
                         "n_items": len(items), "items": A["cards"]["items"]},
           "coverage_matrix": A["cm"], "outputs": A["outs"],
           "technical_synthetic": L.checker_note()}
    filled, diag = L.fill_contract(con, ctx)
    res.update(filled)
    res["contract_fill"] = diag
    res["contract_fields_present"] = L.ckeys(con)
    res.update({"status": status, "outputs": A["outs"],
                "benchmark": {"mode": mode, "n_items": len(items),
                              "set_id": A["cards"]["set_id"],
                              "set_version": A["cards"]["set_version"],
                              "n_rejected": len(rejected), "scores": score_map},
                "anchors": {"n": A["n_anchors"], "verified": A["n_verified"]},
                "scoring": {"aggregate": A["agg"], "closure": A["closure"]},
                "coverage_matrix": A["cm"], "calibration": A["cal"],
                "version_record": A["ver"], "failures": A["fails"], "sources": L.srcs(idx),
                "technical_synthetic": L.checker_note(),
                "errors": (res.get("errors") or []) + issues[:20],
                "degradations": dep, "pending_human": A["unc"][:12], "uncertainty": A["unc"],
                "changes": [{"what": "benchmark set snapshot built from live input", "mode": mode,
                             "why": "agent-authored cards preferred; deterministic fallback keeps "
                                    "the deliverable complete when the draft is missing"},
                            {"what": "scores limited to calibration probes + attributable "
                                     "candidate outputs",
                             "why": "no fabricated model or DSH scores; checker logs registered only"},
                            {"what": "three-pointer closure computed for every score row",
                             "why": "each score must resolve to a raw output, a run config and a "
                                    "scoring record"}]})
    res["runtime"].update({"materials": len(idx["materials"]), "paragraphs": idx["n_paragraphs"],
                           "n_items": len(items), "mode": mode, "n_rows": len(A["rows"]),
                           "closure_rate": A["closure"]["closure_rate"],
                           "self_audit": {"ok": A["closure"]["n_resolved"] == len(A["rows"]) and
                                          sum(A["agg"]["distribution"].values()) == A["agg"]["n_scored"],
                                          "checks": "closure of 3 pointers; 2+1+0 == n_scored"}})
    L.save(res, "build")
    print("mode=%s items=%d anchors=%d/%d verified rows=%d status=%s"
          % (mode, len(items), A["n_verified"], A["n_anchors"], len(A["rows"]), status))
    print("closure=%s calibration=%s coverage=%s"
          % (A["closure"]["closure_rate"], A["cal"]["agreement"], A["cm"]["verdict"]))
    print("wrote: " + " ".join("%s(%dB)" % (Path(v).name, (L.OUTPUT / v).stat().st_size)
                               for v in A["outs"].values() if (L.OUTPUT / v).is_file()))


def cmd_selfcheck(a):
    print("== selfcheck ==")
    ok, checks, lines = G.selfcheck()
    for line in lines:
        print(line)
    if not checks:
        print("! nothing to check yet")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Agent-led literature-reading benchmark ledger.")
    def roots(p):
        p.add_argument("--input", default=argparse.SUPPRESS, help="input root (default /input)")
        p.add_argument("--output", default=argparse.SUPPRESS, help="output root (default /app/output)")
        p.add_argument("--work", default=argparse.SUPPRESS, help="work root (default /app/work)")
        return p

    roots(ap)
    sub = ap.add_subparsers(dest="cmd")
    roots(sub.add_parser("init", help="index input, read contract, write partial result.json"))
    p = roots(sub.add_parser("show", help="print materials / workorder with locators"))
    p.add_argument("--material")
    p.add_argument("--item")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--limit", type=int, default=10)
    roots(sub.add_parser("check", help="validate work/draft.json")).add_argument("--draft")
    roots(sub.add_parser("build", help="write artifacts and finalise result.json")).add_argument("--draft")
    roots(sub.add_parser("selfcheck", help="reconcile closure, counts and contract"))
    a, _ = ap.parse_known_args(argv)
    roots_given = {k: getattr(a, k, None) for k in ("input", "output", "work")}
    if any(roots_given.values()):
        L.set_roots(roots_given["input"], roots_given["output"], roots_given["work"])
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
         "selfcheck": cmd_selfcheck}[a.cmd](a)
    except Exception as e:
        print("! recoverable failure in %s: %s" % (a.cmd, e))
        print(traceback.format_exc(limit=4))
        try:
            res, _ = L.prep(a.cmd + "/error", L.load_case(L.INPUT)[0])
            res["errors"].append({"stage": a.cmd, "error": str(e),
                                  "traceback": traceback.format_exc(limit=4)[-900:]})
            res["status"] = "partial"
            res["degradations"] = [{"item": "run", "issue": str(e),
                                    "action": "wrote legal partial result.json, exit 0"}]
            L.save(res, a.cmd + "/error")
            print("WROTE partial result.json -> %s" % (L.OUTPUT / "result.json"))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)
    except Exception:
        try:  # never die silently: report, keep exit code 0, keep any partial result.json
            import traceback
            sys.stderr.write("! fatal: %s\n%s\n"
                             % (sys.exc_info()[1], traceback.format_exc(limit=4)))
        except Exception:
            pass
        sys.exit(0)
