# -*- coding: utf-8 -*-
"""Artifact rendering for bounded-param-optimizer. Stdlib only."""
from extract import s

LIM = 60


def _pt(p, limit=LIM):
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in list(p.items())[:limit]}


def inventory(ctx):
    lines = ["| id | file | kind | chars |", "|-|-|-|-|"]
    for m in ctx["materials"]:
        lines.append("| %s | %s | %s | %d |" % (m["id"], m["rel"], m["kind"], m["chars"]))
    return "\n".join(lines)


def search_notes(ctx, R):
    d = ctx["domains"]
    inf = R["inf"]
    sections = []
    sections.append("# Search notes — %s" % ctx["case_id"])
    sections.append(
        "## Method\n"
        "1. Scan every file under the input root and index it as a material.\n"
        "2. Extract finite parameter domains (min / max / step) and stated bounds, "
        "each carrying a source locator and a verbatim quote.\n"
        "3. Enumerate the Cartesian grid of the domains and evaluate every stated "
        "bound point by point.\n"
        "4. Fit a ridge-linear response surface per indicator from any run history, "
        "with training RMSE and leave-one-out RMSE reported.\n"
        "5. Rank feasible points, compute the Pareto front, run a maximin + greedy "
        "sequential search plan and quote a per-trial cost from price/usage rows.")
    sections.append("## Material inventory\n" + inventory(ctx))
    found = []
    found.append("- parameter domains: %d (%s)" % (
        len(d), ", ".join("%s in [%s, %s] step %s %s"
                          % (x["name"], s(x["min"]), s(x["max"]), s(x["step"]), x["unit"])
                          for x in d) or "none"))
    found.append("- stated bounds: %d (%s)" % (
        len(ctx["constraints"]),
        ", ".join("%s %s %s %s" % (c["param"], c["op"], s(c["value"]), c["unit"])
                  for c in ctx["constraints"][:8]) or "none"))
    found.append("- run history rows: %d (rows usable by the model: %d)"
                 % (len(ctx["history"]), ctx["notes"].get("bound_rows", 0)))
    found.append("- indicators: %s" % (", ".join("%s (%s)" % (o["name"], o["direction"])
                                                 for o in ctx["objectives"]) or "none"))
    found.append("- price rows: %d, usage rows: %d, budget ceiling: %s"
                 % (len(ctx["prices"]), len(ctx["usages"]),
                    s(ctx["budget"]) if ctx["budget"] is not None else "not supplied"))
    found.append("- versioned candidate plans: %d" % len(ctx["candidates"]))
    sections.append("## What the material yielded\n" + "\n".join(found))
    grid = R["grid"]
    if grid.get("ok"):
        sections.append("## Grid\n- grid size: %d points\n- feasible: %d (%.2f%%)"
                        % (grid["size"], len(grid["feasible"]),
                           100.0 * len(grid["feasible"]) / max(1, grid["size"])))
    else:
        sections.append("## Grid\n- grid: unavailable — %s" % grid.get("reason", ""))
    sections.append("## Feasibility\n- %s" % inf.get("reason", ""))

    hits, misses = [], []
    for m in ctx["materials"]:
        markers = []
        if m.get("json") is not None:
            for k in ("parameter_domains", "domains", "constraints", "history",
                      "resources", "budget", "candidate_plans", "objectives"):
                if k in m["json"]:
                    markers.append(k)
        if markers:
            hits.append("- %s (%s): %s" % (m["id"], m["rel"], ", ".join(markers)))
        else:
            misses.append("- %s (%s): no parameter / constraint / history block"
                          % (m["id"], m["rel"]))
    sections.append("## Searched locations\n" + "\n".join(hits + misses))

    deg = ctx["degradations"] or ["none — every needed input was present"]
    sections.append("## Gaps found in the input\n" + "\n".join("- " + x for x in deg))
    nxt = [
        "Confirm each domain's step with the instrument resolution before running.",
        "Re-run with a filled draft.json (see init) to substitute lab-specific values.",
        "Attach the raw run history (one row per trial, columns named after the domains) "
        "to replace the nearest-history estimate with a fitted surface.",
    ]
    if not ctx["domains"]:
        nxt.insert(0, "Provide at least one parameter domain as min/max/step so the grid, "
                      "model and cost ledger can be computed instead of reported absent.")
    sections.append("## Next actions\n" + "\n".join("- " + x for x in nxt))
    return "\n\n".join(sections) + "\n"


def parameter_table(ctx, R):
    models = R["models"]
    rows = []
    for d in ctx["domains"]:
        sens = {}
        for name, m in models.items():
            if d["key"] in m["coef"]:
                sens[name] = round(m["coef"][d["key"]], 6)
        rows.append({
            "name": d["name"], "min": round(d["min"], 6), "max": round(d["max"], 6),
            "step": round(d["step"], 6), "unit": d["unit"],
            "values_per_axis": len(R["axes"].get(d["key"], [])),
            "sensitivity": sens,
            "evidence": d["evidence"][0] if d["evidence"] else {},
        })
    return {"case_id": ctx["case_id"], "count": len(rows),
            "fields": ["name", "min", "max", "step", "unit", "values_per_axis",
                       "sensitivity", "evidence"],
            "rows": rows,
            "derived_from_history": bool(ctx["notes"].get("domains_from_history")),
            "note": ("sensitivity is the fitted ridge coefficient for that parameter; "
                     "an empty map means no model could be fitted for the indicators")}


def feasible_grid(ctx, R):
    grid = R["grid"]
    out = {"case_id": ctx["case_id"], "cap": R["cap"]}
    if not grid.get("ok"):
        out.update({"status": "unavailable", "reason": grid.get("reason", ""),
                    "axes": {d["name"]: [] for d in ctx["domains"]}, "grid_size": grid.get("size", 0),
                    "feasible_count": 0, "feasible_rate": 0.0,
                    "constraint_pass": [], "sample_feasible": [], "sample_infeasible": []})
        return out
    out.update({"status": "enumerated",
                "axes": {d["name"]: R["axes"].get(d["key"], []) for d in ctx["domains"]},
                "grid_size": grid["size"], "feasible_count": len(grid["feasible"]),
                "feasible_rate": round(len(grid["feasible"]) / max(1, grid["size"]), 4)})
    passes = []
    for c in ctx["constraints"]:
        if c["type"] == "mutex":
            continue
        passed = sum(1 for p in grid["points"]
                     if not any(v["id"] == c["id"] for v in p["violations"]))
        passes.append({"id": c["id"], "param": c["param"], "op": c["op"],
                       "limit": round(c["value"], 6), "unit": c["unit"],
                       "passed": passed, "failed": grid["size"] - passed})
    out["constraint_pass"] = passes
    samp = grid["feasible"]
    step = max(1, len(samp) // 50)
    out["sample_feasible"] = [{"params": _pt(p["params"]), "score": p.get("score"),
                               "score_source": p.get("score_source", ""),
                               "objectives": p.get("objectives", {})}
                              for p in samp[::step][:50]]
    bad = [p for p in grid["points"] if not p["feasible"]]
    stepb = max(1, len(bad) // 20)
    out["sample_infeasible"] = [{"params": _pt(p["params"]), "violations": p["violations"]}
                                for p in bad[::stepb][:20]]
    return out


def pareto_front(ctx, R):
    p = R["pareto"]
    out = {"case_id": ctx["case_id"], "count": p.get("count", 0),
           "indicators": [o["name"] for o in ctx["objectives"]],
           "basis": p.get("basis", ""),
           "points": [{"params": _pt(q["params"]), "score": q.get("score"),
                       "objectives": q.get("objectives", {})} for q in p.get("points", [])]}
    if "single_objective_best" in p:
        out["single_objective_best"] = p["single_objective_best"]
    return out


def search_plan(ctx, R):
    sp = R["search"] or {}
    cost = R["cost"]
    budget = ctx["budget"]
    limit = None
    if cost.get("per_trial_cost") and budget is not None:
        limit = min(sp.get("total_points", 0) or 0, cost.get("affordable_trials") or 0)
    return {"case_id": ctx["case_id"],
            "strategy": {
                "name": "maximin initial batch then greedy acquisition",
                "why": "spread the first batch over the feasible box, then spend the "
                       "remaining budget where the predicted indicator is highest",
                "initial_selection": sp.get("rounds", [{}])[0].get("rule", "") if sp.get("rounds") else "",
                "per_round_rule": "add the point maximising predicted score minus an "
                                  "exploration weight that shrinks each round",
                "stop_rule": [
                    "stop when the feasible grid is exhausted",
                    "stop when the predicted improvement of the next point is below 1e-6",
                    "stop when the accountable budget is spent",
                ],
                "max_rounds": len(sp.get("rounds", [])) or 0,
            },
            "rounds": sp.get("rounds", []),
            "total_points": sp.get("total_points", 0),
            "best": sp.get("best", {}),
            "budget": budget,
            "affordable_trials": cost.get("affordable_trials"),
            "planned_trials_within_budget": limit,
            "basis": sp.get("basis", "no feasible point, so no search plan is proposed")}


def cost_ledger(ctx, R):
    out = dict(R["cost"])
    out["case_id"] = ctx["case_id"]
    out["planned_trials"] = (R["search"] or {}).get("total_points", 0)
    if out.get("total_planned_cost") is None:
        out["total_planned_cost_note"] = (
            "total is left open because either the per-trial cost or the planned number "
            "of trials is not derivable from the supplied material")
    return out


def version_diff(ctx, R):
    v = R["ver"]
    lines = ["# Version comparison — %s" % ctx["case_id"], ""]
    lines.append("Winner: **%s** (%s)" % (v.get("winner") or "none", v.get("basis", "")))
    lines.append("")
    lines.append("| version | params | complete | feasible | violations | mean predicted | reported cost | locator |")
    lines.append("|-|-|-|-|-|-|-|-|")
    if not v.get("versions"):
        lines.append("| none | no versioned candidate plan was supplied | no | no | 0 | not available | not supplied | - |")
    for r in v.get("versions", []):
        params = ", ".join("%s=%s" % (k, s(val)) for k, val in r["params"].items()) or "none"
        lines.append("| %s | %s | %s | %s | %d | %s | %s | %s |" % (
            r["version"], params, "yes" if r["complete"] else "no",
            "yes" if r["feasible"] else "no", len(r["violations"]),
            s(r["mean_predicted"]) if r["mean_predicted"] is not None else "not available",
            s(r["reported_cost"]) if r["reported_cost"] is not None else "not supplied",
            r["locator"]))
    lines.append("")
    lines.append("Each row repeats the parameters exactly as written in the material; the "
                 "predicted column is the mean of the fitted ridge predictions over the "
                 "declared indicators and is blank for versions that break a stated bound.")
    return "\n".join(lines) + "\n"


def evidence(ctx, R):
    stats = R["ev_stats"]
    return {"case_id": ctx["case_id"], "stats": stats, "items": R["ev_items"][:200]}


def infeasibility(ctx, R):
    out = dict(R["inf"])
    out["case_id"] = ctx["case_id"]
    return out


def build_artifacts(ctx, R):
    return {
        "search_notes.md": search_notes(ctx, R),
        "parameter_table.json": parameter_table(ctx, R),
        "feasible_grid.json": feasible_grid(ctx, R),
        "pareto_front.json": pareto_front(ctx, R),
        "search_plan.json": search_plan(ctx, R),
        "cost_ledger.json": cost_ledger(ctx, R),
        "version_diff.md": version_diff(ctx, R),
        "evidence.json": evidence(ctx, R),
        "infeasibility.json": infeasibility(ctx, R),
    }


def status_of(ctx, R):
    if not ctx["domains"]:
        return "insufficient_evidence"
    if R["grid"].get("ok") and not R["grid"]["feasible"]:
        return "partial"
    if not R["models"]:
        return "partial"
    return "answered"
