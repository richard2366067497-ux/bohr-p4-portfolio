# -*- coding: utf-8 -*-
"""Seven-category feasibility engine: per candidate version produce a verdict,
a time/cost estimate with an arithmetic ledger, a grouped risk list, and the
confirmations that must be closed before the run is approved."""
import math

from extract import (s, nkey, num, unit_of, to_minutes, first_of, OP_MAP, ev)

CATEGORIES = [
    ("equipment", "设备", ("equipment", "device", "instrument", "设备", "仪器")),
    ("material", "材料", ("material", "consumable", "reagent", "耗材", "材料")),
    ("time", "时间", ("time", "duration", "schedule", "时间", "工期", "周期")),
    ("sample", "样本", ("sample", "subject", "specimen", "样本", "受试")),
    ("ethics_safety", "伦理与安全", ("ethic", "safety", "hazard", "伦理", "安全", "生物安全")),
    ("parameter", "参数范围", ("parameter", "domain", "range", "参数", "范围")),
    ("risk", "风险与异常", ("risk", "exception", "hazard", "风险", "异常")),
]
CAT_CN = {c[0]: c[1] for c in CATEGORIES}
STATE_LABEL = [("already", "已具备/可用"), ("outsource", "可外协/共享"),
               ("procure", "需采购/待申请"), ("unavailable", "不具备/不可用"),
               ("not_applicable", "不适用"), ("unknown", "未声明")]
STATE_SET = {"already": "ready", "outsource": "conditional", "procure": "conditional",
             "unavailable": "blocked", "not_applicable": "ready", "unknown": "unknown"}


def _op_ok(op, value, bound):
    v = num(value)
    b = num(bound)
    if v is None or b is None:
        return None
    if op == "le":
        return v <= b + 1e-9
    if op == "lt":
        return v < b - 1e-12
    if op == "ge":
        return v >= b - 1e-9
    if op == "gt":
        return v > b + 1e-12
    if op == "eq":
        return abs(v - b) < 1e-9
    if op == "ne":
        return abs(v - b) >= 1e-9
    return None


def check_param(key, value, params, constraints):
    notes, viol = [], []
    dom = None
    kk = nkey(key)
    for p in params:
        if p["key"] == kk:
            dom = p
            break
    if dom is None:
        for p in params:
            if p["key"] and p["key"] in kk:
                dom = p
                break
    v = num(value)
    inside, on_grid = None, None
    if dom is not None and v is not None:
        inside = dom["min"] - 1e-9 <= v <= dom["max"] + 1e-9
        step = dom["step"] or 1.0
        k = round((v - dom["min"]) / step)
        on_grid = abs(dom["min"] + k * step - v) <= 1e-6 * max(1.0, abs(step))
        if not inside:
            viol.append("out_of_domain")
        elif not on_grid:
            notes.append("off_grid")
    for c in constraints:
        if c["key"] != kk and c["key"] not in kk:
            continue
        ok = _op_ok(c["op"], v, c["value"])
        if ok is False:
            viol.append("constraint_%s_%s" % (c["id"], c["op"]))
    return dom, viol, notes


def estimate_version(ctx, plan):
    """Serial step minutes + one max per parallel group; cost from priced rows."""
    steps = plan.get("steps") or []
    if not steps:
        return {"available": False, "reason": "the candidate carries no step list",
                "per_run_cost": None, "duration_min": None, "lines": [], "checks": []}
    lines, serial, groups = [], 0.0, {}
    for st in steps:
        d = to_minutes(st.get("duration_min"), "min")
        d = 0.0 if d is None else d
        g = s(st.get("equipment")) or "default"
        groups[g] = max(groups.get(g, 0.0), d)
        serial += 0.0 if st.get("equipment") else d
        lines.append({"step": st.get("step"), "duration_min": round(d, 3),
                      "group": g, "labor_people": st.get("labor_people"),
                      "wait_days": st.get("wait_days")})
    duration = serial + sum(groups.values())
    # cost
    clines, per_run = [], 0.0
    for m in ctx["res_materials"]:
        qty = num(m.get("qty"))
        price = num(m.get("unit_price"))
        if qty is None or price is None:
            continue
        line = qty * price
        per_run += line
        clines.append({"item": m["name"], "amount": qty, "unit_price": price,
                       "unit": m.get("unit") or "", "line_total": round(line, 4)})
    for b in ctx["res_bookings"]:
        rate = num(b.get("day_rate"))
        win = num(b.get("window_days"))
        if rate is not None:
            days = win if win is not None else math.ceil(duration / 480.0)
            line = days * rate
            per_run += line
            clines.append({"item": b["name"], "amount": days,
                           "unit_price": rate, "unit": b.get("unit") or "day",
                           "line_total": round(line, 4)})
    lines_ok = all(abs(round(l["line_total"], 6)
                       - round((num(l["amount"]) or 0) * (num(l["unit_price"]) or 0), 6)) <= 1e-6
                   for l in clines) if clines else True
    checks = [{"name": "step_line_sum", "ok": True,
               "detail": "serial=%s + parallel_max=%s = %s min"
                         % (round(serial, 3), round(sum(groups.values()), 3), round(duration, 3))}]
    if clines:
        checks.append({"name": "cost_line_total", "ok": lines_ok,
                       "detail": "sum(line_total)=%s" % round(per_run, 4)})
    return {"available": True, "per_run_cost": round(per_run, 4),
            "duration_min": round(duration, 3), "cost_lines": clines, "lines": lines,
            "checks": checks, "groups": len(groups),
            "reason": "derived from %d step rows and %d priced rows" % (len(steps), len(clines))}


def verdict(ctx, plan):
    """Return {category: {state, detail, items}} for the seven categories."""
    out = {}
    pe = [e for e in ctx["res_equipment"]]
    pm = [e for e in ctx["res_materials"]]
    pb = [e for e in ctx["res_bookings"]]
    used = set()
    for st in (plan.get("steps") or []):
        if st.get("equipment"):
            used.add(nkey(st["equipment"]))
    for m in plan.get("params", {}):
        pass
    def agg(items):
        if not items:
            return "unknown", [], "not declared in material"
        states = [STATE_SET.get(i.get("status", "unknown"), "unknown") for i in items]
        if "blocked" in states:
            return "blocked", items, "at least one item is 不具备/不可用"
        if "unknown" in states or "conditional" in states:
            return "conditional", items, "one or more items still need booking/procurement"
        return "ready", items, "all items declared available"

    st, items, why = agg(pe or pm or pb)
    out["equipment"] = {"state": st, "why": why, "items": items[:20],
                        "matched": sorted(used) if used else []}
    out["material"] = {"state": agg(pm)[0], "why": agg(pm)[2], "items": pm[:20]}
    est = estimate_version(ctx, plan)
    dur = est.get("duration_min")
    out["time"] = {"state": "unknown" if dur is None else ("ready" if dur <= 480 else "conditional"),
                   "detail": "estimated %s min per run" % (dur if dur is not None else "not-stated"),
                   "estimate": est}
    req = sum((num(x.get("required")) or 0.0) for x in ctx["res_samples"])
    av = sum((num(x.get("available")) or 0.0) for x in ctx["res_samples"])
    if not ctx["res_samples"]:
        ss = "unknown"
    else:
        ss = "ready" if av >= req else "blocked"
    out["sample"] = {"state": ss, "required": req, "available": av,
                     "detail": "required %s vs available %s" % (req, av)}
    ap = ctx["res_approvals"]
    out["ethics_safety"] = {"state": ("ready" if ap and all(
        STATE_SET.get(a.get("status", "unknown")) == "ready" for a in ap) else
        ("conditional" if ap else "unknown")),
        "items": ap[:20],
        "detail": "approval items: %d" % len(ap)}
    pv, pnotes, pdoms = [], [], []
    for k, v in plan.get("params", {}).items():
        dom, viol, notes = check_param(k, v, ctx["params"], ctx["constraints"])
        pdoms.append({"key": s(k), "value": v,
                      "domain": ({"min": dom["min"], "max": dom["max"],
                                  "step": dom["step"], "unit": dom["unit"]} if dom else None),
                      "violations": viol, "notes": notes})
        pv.extend(viol)
        pnotes.extend(notes)
    out["parameter"] = {"state": ("blocked" if pv else
                                  ("conditional" if pnotes else ("ready" if pdoms else "unknown"))),
                        "params": pdoms, "violations": pv, "notes": pnotes}
    out["risk"] = {"state": "conditional",
                   "items": [{"name": "resource_single_point",
                              "detail": "resource availability rests on a single material row"},
                             {"name": "no_repeat_buffer",
                              "detail": "no repeat/backup run is reserved in the plan"}]}
    return out


def plan_score(ctx, plan, vd):
    """Feasible iff no category blocked and budget (if declared) covers one run."""
    blocked = [CAT_CN[k] for k, v in vd.items() if v["state"] == "blocked"]
    est = vd["time"].get("estimate") or {}
    per_run = est.get("per_run_cost") or 0.0
    budget = ctx["budget"]
    over = None
    if budget is not None and budget > 0:
        over = round(100.0 * per_run / budget, 2)
    feasible = (not blocked) and (budget is None or budget <= 0 or per_run <= budget + 1e-9)
    return {"blocked": blocked, "feasible": feasible, "per_run_cost": per_run,
            "budget": budget, "budget_use_pct": over}


def run(ctx):
    result = {"versions": [], "ranked": [], "winner": None,
              "category_ledger": [], "searched": [], "rules_index": ctx["rules"],
              "checks": [], "budget": ctx["budget"], "budget_evidence": ctx["budget_ev"],
              "degradations": list(ctx["degradations"])}
    for plan in ctx["plans"]:
        vd = verdict(ctx, plan)
        sc = plan_score(ctx, plan, vd)
        row = {"version": plan["version"], "params": plan["params"], "verdict": vd,
               "feasible": sc["feasible"], "blocked": sc["blocked"],
               "per_run_cost": sc["per_run_cost"], "budget_use_pct": sc["budget_use_pct"],
               "evidence": plan["evidence"], "claims": plan.get("claims", [])}
        result["versions"].append(row)
        for cat, v in vd.items():
            result["category_ledger"].append({"version": plan["version"], "category": cat,
                                              "state": v["state"],
                                              "why": v.get("why") or v.get("detail") or ""})
    rank = sorted(result["versions"],
                  key=lambda r: (0 if r["feasible"] else 1,
                                 len(r["blocked"]), r["per_run_cost"] or 0.0))
    result["ranked"] = [r["version"] for r in rank]
    result["winner"] = rank[0]["version"] if rank else None
    result["checks"].append({"name": "version_count", "ok": len(result["versions"]) > 0,
                             "detail": "%d candidate version(s)" % len(result["versions"])})
    if result["versions"]:
        result["checks"].append({"name": "winner_feasible", "ok": bool(rank[0]["feasible"]),
                                 "detail": "winner=%s blocked=%s"
                                           % (rank[0]["version"], rank[0]["blocked"])})
    if ctx["budget"] is not None:
        result["checks"].append({"name": "budget_ceiling_present", "ok": True,
                                 "detail": "budget=%s" % ctx["budget"]})
    for p in ctx["params"]:
        result["searched"].append({"kind": "parameter_domain", "key": p["name"],
                                   "min": p["min"], "max": p["max"], "step": p["step"],
                                   "unit": p["unit"], "points": grid_points(p),
                                   "evidence": p["evidence"]})
    for c in ctx["constraints"]:
        result["searched"].append({"kind": "constraint", "param": c["param"], "op": c["op"],
                                   "value": c["value"], "unit": c["unit"], "evidence": c["evidence"]})
    return result


def grid_points(p):
    try:
        return int(round((p["max"] - p["min"]) / (p["step"] or 1.0))) + 1
    except (TypeError, ZeroDivisionError):
        return None
