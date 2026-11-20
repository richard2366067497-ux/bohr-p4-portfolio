# -*- coding: utf-8 -*-
"""plan-forge-experiment :: rendering layer (artifacts)."""
import json, os

from design import s, nkey, num, plan_label, axis_values

SIX = [("hypothesis_and_variables", "假设与变量 / hypothesis and variables"),
       ("controls", "对照组 / controls and baseline"),
       ("equipment_materials", "设备材料 / equipment and materials"),
       ("time_and_cost", "时间成本 / time and cost"),
       ("parameter_ranges", "参数范围 / parameter ranges"),
       ("risks_and_exceptions", "风险和异常 / risks and exceptions")]


def six_elements(ctx, results):
    out = {}
    hyp = ctx["hypothesis"]
    vs = []
    for d in ctx["domains"]:
        vs.append({"name": d["name"], "role": "independent variable",
                   "range": "[%s, %s] step %s" % (s(d["min"]), s(d["max"]), s(d["step"])),
                   "unit": d["unit"], "axis_points": len(axis_values(d)),
                   "levels": axis_values(d) if len(axis_values(d)) <= 12 else
                             (axis_values(d)[:6] + ["..."] + axis_values(d)[-3:]),
                   "evidence": d["evidence"][0]})
    out["hypothesis_and_variables"] = {
        "status": "present" if hyp else "proposed",
        "hypothesis": hyp["statement"] if hyp else
                      "no hypothesis statement was declared in the supplied material",
        "falsifier": (hyp or {}).get("falsifier") or
                     "not stated; a falsifier must be agreed before the run",
        "support_metric": (hyp or {}).get("support_metric") or
                          "not stated; the readout column of the history table is used as the working support metric",
        "independent_variables": vs,
        "derived_dependent_variable": "the response column carried by the history table, if any",
        "evidence": (hyp or {}).get("evidence") or []}
    out["controls"] = {
        "status": "declared" if ctx["controls"] else "proposed",
        "items": ctx["controls"] or [
            {"id": "K1", "type": "reference",
             "design": "reference arm at the lowest level of each declared parameter"
                       + (" (%s)" % ", ".join("%s=%s" % (d["name"], s(d["min"])) for d in ctx["domains"])
                          if ctx["domains"] else ""),
             "excludes": "the manipulated parameter effect",
             "readout": "same readout as the treatment arms",
             "evidence": {"source_id": "RULE", "locator": "generated",
                          "quote": "no control arm in the material; reference arm derived from the declared domain",
                          "verified": False}}],
        "note": ("declared in the material with a source quote" if ctx["controls"]
                 else "no control arm was found in the material; the arm shown is rule-derived and listed as a confirmation item")}
    out["equipment_materials"] = {
        "status": "present" if ctx["resources"] else "absent",
        "items": [{"name": r["name"], "spec": r["spec"] or "not specified",
                   "on_hand": s(r["qty"]), "unit": r["unit"],
                   "unit_price": s(r["price"]), "lead_time": s(r["lead_time"]),
                   "booking_window": r["booking"] or "not declared",
                   "substitutable": (r["substitutable"] if r["substitutable"] is not None else "not declared"),
                   "locator": "%s/%s" % (r["material"], r["path"]),
                   "quote": r["evidence"]["quote"][:200]} for r in ctx["resources"]] or
                 ["no equipment or material list was supplied; this element is reported as absent rather than invented"],
        "count": len(ctx["resources"])}
    cheapest = min([r for r in ctx["resources"] if r.get("price") is not None],
                   key=lambda r: r["price"], default=None)
    out["time_and_cost"] = {
        "status": "present" if results else "absent",
        "per_version": [{"version": r["plan"]["version"],
                         "duration_min": r["arith"]["duration_min"],
                         "per_run_cost": r["arith"]["per_run_cost"],
                         "replicates": r["arith"]["replicates"],
                         "total_cost": r["arith"]["total_cost"]} for r in results],
        "budget": s(ctx["budget"]), "deadline_days": s(ctx["deadline_days"]),
        "unit_price_anchor": ({"name": cheapest["name"], "unit_price": cheapest["price"],
                               "locator": "%s/%s" % (cheapest["material"], cheapest["path"])}
                              if cheapest else "no priced item in the material"),
        "formula": "per_run_cost = sum(amount x unit_price); total_cost = per_run_cost x replicates; "
                   "duration_min = sum(serial step minutes) + max(minutes) per parallel group"}
    out["parameter_ranges"] = {
        "status": "present" if ctx["domains"] else "absent",
        "domains": [{"name": d["name"], "min": d["min"], "max": d["max"], "step": d["step"],
                     "unit": d["unit"], "axis_points": len(axis_values(d)),
                     "levels": axis_values(d) if len(axis_values(d)) <= 12 else
                               (axis_values(d)[:6] + ["..."] + axis_values(d)[-3:]),
                     "locator": d["evidence"][0]["locator"],
                     "quote": d["evidence"][0]["quote"][:200]} for d in ctx["domains"]],
        "constraints": [{"id": c["id"], "parameter": c["param"], "op": c["op"],
                         "value": s(c["value"]), "unit": c["unit"], "note": c["note"],
                         "source": c["source"], "locator": c["evidence"][0]["locator"],
                         "quote": c["evidence"][0]["quote"][:200]} for c in ctx["constraints"]]}
    out["risks_and_exceptions"] = {
        "status": "present" if ctx["risks"] else "open",
        "items": ctx["risks"] or [
            {"id": "R1", "mode": "resource unavailable inside the booking window",
             "trigger": "booking window not confirmed before the run",
             "criterion": "not stated", "stop_loss": "not stated",
             "fallback": "reserve the next free slot or switch to a declared substitutable item",
             "evidence": {"source_id": "RULE", "locator": "generated",
                          "quote": "no risk register in the material; this entry is derived from the booking rule",
                          "verified": False}}],
        "confirmations": ctx["confirmations"],
        "note": ("from the material's risk register" if ctx["risks"]
                 else "no risk register was supplied; the entry shown is derived from the resource rules")}
    return out


def build_artifacts(ctx, R):
    art = {}
    six = six_elements(ctx, R["results"])
    R["six_elements"] = six
    winner = R["winner"]
    rec = R["recommendation"]

    L = []
    L.append("# Plan report — %s" % ctx["case_id"])
    L.append("")
    L.append("Status: **%s**. %s" % (R["status"], R["status_reason"]))
    L.append("")
    if R["status"] == "insufficient_evidence":
        L.append("## Why this is not answered")
        L.append("")
        for d in ctx["degradations"]:
            L.append("- %s" % d)
        L.append("")
    L.append("## Six required elements, each with its basis")
    L.append("")
    for key, title in SIX:
        blk = six[key]
        L.append("### %s" % title)
        L.append("")
        L.append("- status: %s" % blk.get("status"))
        if key == "hypothesis_and_variables":
            L.append("- hypothesis: %s" % blk["hypothesis"])
            L.append("- falsifier: %s" % blk["falsifier"])
            L.append("- support metric: %s" % blk["support_metric"])
            for v in blk["independent_variables"]:
                L.append("  - %s (%s) range %s %s, %d axis points, locator %s"
                         % (v["name"], v["role"], v["range"], v["unit"], v["axis_points"],
                            v["evidence"]["locator"]))
        elif key == "controls":
            for c in blk["items"]:
                L.append("  - %s [%s] %s | readout: %s | locator %s"
                         % (c["id"], c["type"], c["design"][:140], c["readout"] or "n a",
                            c["evidence"]["locator"]))
            L.append("- note: %s" % blk["note"])
        elif key == "equipment_materials":
            for r in blk["items"]:
                if isinstance(r, str):
                    L.append("  - %s" % r)
                else:
                    L.append("  - %s | spec %s | on hand %s %s | unit price %s | lead %s | booking %s | locator %s"
                             % (r["name"], r["spec"], r["on_hand"], r["unit"], r["unit_price"],
                                r["lead_time"], r["booking_window"], r["locator"]))
        elif key == "time_and_cost":
            for t in blk["per_version"]:
                if t["total_cost"] is None:
                    L.append("  - %s: %s min per run; cost unpriced (no unit price on any matched item)"
                             % (t["version"], s(t["duration_min"])))
                else:
                    L.append("  - %s: %s min, %s per run x %s = %s total"
                             % (t["version"], s(t["duration_min"]), s(t["per_run_cost"]),
                                s(t["replicates"]), s(t["total_cost"])))
            L.append("- budget: %s | deadline: %s | anchor: %s"
                     % (blk["budget"] or "not supplied",
                        (blk["deadline_days"] + " day(s)") if blk["deadline_days"] else "not supplied",
                        blk["unit_price_anchor"] if isinstance(blk["unit_price_anchor"], str)
                        else "%s at %s per unit (%s)" % (blk["unit_price_anchor"]["name"],
                                                         s(blk["unit_price_anchor"]["unit_price"]),
                                                         blk["unit_price_anchor"]["locator"])))
            L.append("- formula: %s" % blk["formula"])
        elif key == "parameter_ranges":
            for d in blk["domains"]:
                L.append("  - %s: [%s, %s] step %s %s, %d axis points, locator %s"
                         % (d["name"], s(d["min"]), s(d["max"]), s(d["step"]), d["unit"],
                            d["axis_points"], d["locator"]))
            for c in blk["constraints"]:
                L.append("  - %s: %s %s %s %s (%s, source %s, locator %s)"
                         % (c["id"], c["parameter"], c["op"], c["value"], c["unit"],
                            c["note"] or "stated constraint", c["source"], c["locator"]))
        else:
            for r in blk["items"]:
                L.append("  - %s: %s | trigger %s | criterion %s | stop %s | fallback %s | locator %s"
                         % (r["id"], r["mode"][:120], r["trigger"] or "n a",
                            r["criterion"] or "n a", r["stop_loss"] or "n a",
                            r["fallback"] or "n a", r["evidence"]["locator"]))
            for c in blk["confirmations"]:
                L.append("  - confirm: %s (why: %s) | locator %s"
                         % (c["item"][:120], c["why"][:120] or "n a", c["evidence"]["locator"]))
            L.append("- note: %s" % blk["note"])
        L.append("")
    L.append("## Recommendation")
    L.append("")
    L.append("- version: %s (%s)" % (winner or "none", rec.get("source") or "n a"))
    L.append("- settings: %s" % rec["value"])
    L.append("- tolerance band: %s" % rec["band"])
    L.append("- basis: %s" % rec["basis"])
    if rec.get("total_cost") is None:
        L.append("- cost: unpriced (no unit price was found for any item this plan consumes); "
                 "duration %s min; replicates %s" % (s(rec.get("duration_min")), s(rec.get("replicates"))))
    else:
        L.append("- per-run cost %s, total %s, duration %s min, replicates %s"
                 % (s(rec.get("per_run_cost")), s(rec.get("total_cost")),
                    s(rec.get("duration_min")), s(rec.get("replicates"))))
    for c in rec.get("checks") or []:
        L.append("- arithmetic check `%s`: %s — %s"
                 % (c["name"], ("not evaluable" if not c.get("evaluated", True)
                                else ("ok" if c["ok"] else "failed")), c["detail"]))
    L.append("")
    L.append("## Limits and open items")
    L.append("")
    for d in R["uncertainties"]:
        L.append("- %s" % d)
    if not R["uncertainties"]:
        L.append("- nothing remained open: every element was located and every validation rule passed")
    L.append("")
    L.append("## Sources")
    L.append("")
    for src in R["sources"]:
        L.append("- %s: %s (%s chars)" % (src["source_id"], src["title"], src["chars"]))
    L.append("")
    art["plan_report.md"] = "\n".join(L)

    rev = {"case_id": ctx["case_id"], "winner": winner,
           "status": R["status"],
           "recommended": {"version": winner, "settings": rec["value"],
                           "tolerance_band": rec["band"], "basis": rec["basis"]},
           "plans": [{"version": r["plan"]["version"], "source": r["plan"].get("source"),
                      "settings": plan_label(r["plan"]),
                      "revisions": r.get("revision_actions", []),
                      "hard_violations_after_revision": len(r["validation"]["violations"]),
                      "per_run_cost": r["arith"]["per_run_cost"],
                      "total_cost": r["arith"]["total_cost"],
                      "duration_min": r["arith"]["duration_min"],
                      "replicates": r["arith"]["replicates"],
                      "feasible": r["validation"]["ok"],
                      "locator": "%s/%s" % (r["plan"].get("material", ""), r["plan"].get("path", ""))}
                     for r in R["results"]],
           "revision_rules": [
               "out-of-domain or off-grid value -> nearest legal grid point inside the finite domain",
               "constraint violation -> nearest grid point that satisfies the stated bound",
               "usage above stock -> trimmed to the quantity on hand",
               "over-budget total -> replicates cut to floor(budget / per_run_cost), never below 1",
               "missing control -> a reference arm is added and flagged as a confirmation item",
               "every action above is listed per plan with from -> with to and the reason"],
           "unresolved": [u for u in R["uncertainties"] for _ in [0]][:12]}
    art["plan_revised.json"] = rev

    art["validation_report.json"] = {
        "case_id": ctx["case_id"],
        "rules": [
            {"rule": "param_domain", "meaning": "every set value lies inside its declared finite domain and on the step grid"},
            {"rule": "constraint_*", "meaning": "stated le/ge/lt/gt/eq/ne bounds and mutex pairs are respected"},
            {"rule": "booking", "meaning": "facilities with a booking window are reserved inside that window"},
            {"rule": "budget", "meaning": "total cost of the plan does not exceed the declared ceiling"},
            {"rule": "quantity", "meaning": "consumption of each item does not exceed the quantity on hand"},
            {"rule": "control", "meaning": "a control or baseline arm exists for the plan's readout"},
            {"rule": "unit", "meaning": "each parameter and priced item carries a unit"}],
        "per_plan": [{"version": r["plan"]["version"],
                      "hard_violations": r["validation"]["violations"],
                      "warnings": r["validation"]["warnings"],
                      "notes": r["validation"]["notes"],
                      "summary": r["validation"]["summary"],
                      "feasible": r["validation"]["ok"],
                      "before_revision": r.get("before")}
                     for r in R["results"]],
        "totals": {"plans": len(R["results"]),
                   "feasible": sum(1 for r in R["results"] if r["validation"]["ok"]),
                   "hard_violations": sum(len(r["validation"]["violations"]) for r in R["results"]),
                   "warnings": sum(len(r["validation"]["warnings"]) for r in R["results"])}}
    art["validation_report.json"] = art["validation_report.json"]

    art["arithmetic_ledger.json"] = {
        "case_id": ctx["case_id"],
        "formula": rec.get("basis") and
                   "per_run_cost = sum(amount x unit_price); total_cost = per_run_cost x replicates",
        "budget": ctx["budget"], "deadline_days": ctx["deadline_days"],
        "per_plan": [{"version": r["plan"]["version"],
                      "replicates": r["arith"]["replicates"],
                      "per_run_cost": r["arith"]["per_run_cost"],
                      "total_cost": r["arith"]["total_cost"],
                      "duration_min": r["arith"]["duration_min"],
                      "cost_lines": r["arith"]["cost_lines"],
                      "duration_lines": r["arith"]["duration_lines"],
                      "inputs": r["arith"]["cost_inputs"],
                      "checks": r["arith"]["checks"],
                      "inputs_complete": all(c["ok"] for c in r["arith"]["checks"])}
                     for r in R["results"]]}
    art["evidence.json"] = {"case_id": ctx["case_id"], "stats": R["evidence_stats"],
                            "items": R["evidence_items"]}

    L = ["# Version diff — %s" % ctx["case_id"], "",
         "| version | source | settings | per-run | total | duration min | reps | hard viol. | feasible | revised |",
         "|-|-|-|-|-|-|-|-|-|-|"]
    for row in R["rows"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %d | %s | %s |"
                 % (row["version"], row["source"], row["params"], s(row["per_run_cost"]),
                    s(row["total_cost"]), s(row["duration_min"]), s(row["replicates"]),
                    row["hard_violations"], "yes" if row["feasible"] else "no",
                    "yes" if row["revised"] else "no"))
    L.append("")
    L.append("Winner by rule (feasible first, then fewest hard violations, then lowest total cost, then shortest duration): **%s**." % (winner or "none"))
    L.append("")
    L.append("Per-version locators:")
    for row in R["rows"]:
        L.append("- %s: %s" % (row["version"], row["locator"]))
    art["version_diff.md"] = "\n".join(L)

    L = ["# Reproduce — %s" % ctx["case_id"], "",
         "## Entry point", "",
         "```bash", "python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work", "```", "",
         "## Materials read", ""]
    for src in R["sources"]:
        L.append("- %s: %s (%s chars, kind %s)" % (src["source_id"], src["title"], src["chars"], src["kind"]))
    L.append("")
    L.append("## Recommended settings")
    L.append("")
    L.append("- %s" % rec["value"])
    L.append("- tolerance band: %s" % rec["band"])
    for c in rec.get("checks") or []:
        L.append("- check `%s`: %s (%s)"
                 % (c["name"], ("not evaluable" if not c.get("evaluated", True)
                                else ("ok" if c["ok"] else "failed")), c["detail"]))
    L.append("")
    L.append("## Step-by-step")
    L.append("")
    for i, r in enumerate(R["results"]):
        L.append("%d. Run version %s: %s" % (i + 1, r["plan"]["version"], plan_label(r["plan"])))
    L.append("%d. Confirm the control arm and each open confirmation item listed in the plan report." % (len(R["results"]) + 1))
    L.append("%d. Reserve the booking windows, then execute the serial steps in order; parallel groups may overlap." % (len(R["results"]) + 2))
    L.append("")
    L.append("## Decision rules")
    L.append("")
    for line in art["plan_revised.json"]["revision_rules"]:
        L.append("- %s" % line)
    art["reproduce.md"] = "\n".join(L)
    return art
