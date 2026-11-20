# -*- coding: utf-8 -*-
"""Arithmetic layer: enumeration, model, Pareto, search, cost, feasibility."""
import itertools, math
from extract import (convert, nkey, num, s, direction_of)

MAX_GRID = 20000
MAX_PARETO = 1200


def _dom(ctx, k):
    for d in ctx["domains"]:
        if d["key"] == k:
            return d
    return None


def axis_values(d):
    mn, mx, st = d["min"], d["max"], d["step"]
    if st <= 0:
        st = (mx - mn) / 10.0
    n = int(math.floor((mx - mn) / st + 1e-9)) + 1
    if n > 400:
        n = 400
        st = (mx - mn) / (n - 1)
    vals = [round(mn + i * st, 9) for i in range(n)]
    if vals[-1] < mx - 1e-9:
        vals.append(round(mx, 9))
    return vals


def _cmp_ok(op, lhs, rhs):
    if op == "le":
        return lhs <= rhs + 1e-9
    if op == "lt":
        return lhs < rhs - 1e-12
    if op == "ge":
        return lhs >= rhs - 1e-9
    if op == "gt":
        return lhs > rhs + 1e-12
    if op == "eq":
        return abs(lhs - rhs) <= 1e-6 * max(1.0, abs(rhs))
    if op == "ne":
        return abs(lhs - rhs) > 1e-6 * max(1.0, abs(rhs))
    return True


def check_point(ctx, p):
    viol = []
    for c in ctx["constraints"]:
        if c["type"] == "mutex" or c["key"] not in p or p[c["key"]] is None:
            continue
        d = _dom(ctx, c["key"])
        val = p[c["key"]]
        unit = (d["unit"] if d else "") or ""
        lim = c["value"]
        if c["unit"] and unit and c["unit"] != unit:
            cv = convert(lim, c["unit"], unit)
            if cv is None:
                viol.append({"id": c["id"], "param": c["param"], "op": c["op"],
                             "limit": c["value"], "unit": c["unit"], "value": val,
                             "reason": "unit mismatch, treated as unresolved"})
                continue
            lim = cv
        if not _cmp_ok(c["op"], val, lim):
            viol.append({"id": c["id"], "param": c["param"], "op": c["op"],
                         "limit": c["value"], "unit": c["unit"], "value": val,
                         "reason": "outside stated bound"})
    return {"feasible": not viol, "violations": viol}


def grid(ctx):
    ds = ctx["domains"]
    if not ds:
        return {"ok": False, "reason": "no finite parameter domain in supplied material",
                "axes": [], "points": [], "size": 0}
    axes = [axis_values(d) for d in ds]
    size = 1
    for a in axes:
        size *= len(a)
    if size > MAX_GRID:
        return {"ok": False, "reason": "grid size %d exceeds cap %d" % (size, MAX_GRID),
                "axes": axes, "points": [], "size": size}
    keys = [d["key"] for d in ds]
    pts = []
    for combo in itertools.product(*axes):
        p = dict(zip(keys, combo))
        chk = check_point(ctx, p)
        pts.append({"params": p, "violations": chk["violations"], "feasible": chk["feasible"]})
    return {"ok": True, "axes": axes, "points": pts,
            "feasible": [p for p in pts if p["feasible"]], "size": size}


def center_point(ctx, feas):
    out = {}
    for d in ctx["domains"]:
        vals = [p["params"][d["key"]] for p in feas if p["params"].get(d["key"]) is not None]
        out[d["key"]] = round(sum(vals) / len(vals), 9) if vals else round((d["min"] + d["max"]) / 2.0, 9)
    return out


def norm_dist(ctx, a, b):
    tot = 0.0
    for d in ctx["domains"]:
        av, bv = a.get(d["key"]), b.get(d["key"])
        if av is None or bv is None:
            continue
        span = (d["max"] - d["min"]) or 1.0
        tot += ((av - bv) / span) ** 2
    return math.sqrt(tot)


def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for j in range(col, n + 1):
            M[col][j] /= pv
        for r in range(n):
            if r == col:
                continue
            f = M[r][col]
            if f == 0.0:
                continue
            for j in range(col, n + 1):
                M[r][j] -= f * M[col][j]
    return [M[i][n] for i in range(n)]


def _ridge(X, y, lam):
    n = len(X[0]) if X else 0
    if n == 0 or len(X) < n:
        return None
    A = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    for r, yy in zip(X, y):
        for i in range(n):
            b[i] += r[i] * yy
            for j in range(n):
                A[i][j] += r[i] * r[j]
    for i in range(n):
        A[i][i] += lam
    return _solve(A, b)


def _dot(c, r):
    return sum(a * b for a, b in zip(c, r))


def predict(models, name, params):
    m = models.get(name)
    if not m:
        return None
    v = m["coef"]["intercept"]
    for k in m["params"]:
        v += m["coef"].get(k, 0.0) * params.get(k, 0.0)
    return v


def fit_models(ctx, grid_res):
    models = {}
    if not grid_res.get("ok"):
        return models
    keys = [d["key"] for d in ctx["domains"]]
    rows = [h for h in ctx["history"]
            if h.get("bound") and all(h["bound"].get(k) is not None for k in keys)]
    for o in ctx["objectives"]:
        pairs = [(h["bound"], h["resp"][o["name"]]) for h in rows
                 if (h.get("resp") or {}).get(o["name"]) is not None]
        if len(pairs) < max(3, len(keys) + 2):
            continue
        X = [[1.0] + [b[k] for k in keys] for b, _ in pairs]
        y = [yy for _, yy in pairs]
        coef = _ridge(X, y, 1e-8)
        if coef is None:
            continue
        err = [_dot(coef, r) - yy for r, yy in zip(X, y)]
        rmse = math.sqrt(sum(e * e for e in err) / len(err))
        loo = None
        if len(pairs) <= 60:
            es = []
            for i in range(len(pairs)):
                ci = _ridge([r for j, r in enumerate(X) if j != i],
                            [v for j, v in enumerate(y) if j != i], 1e-8)
                if ci is None:
                    es = []
                    break
                es.append(_dot(ci, X[i]) - y[i])
            if es:
                loo = math.sqrt(sum(e * e for e in es) / len(es))
        models[o["name"]] = {"kind": "ridge_linear", "rmse": rmse, "loo_rmse": loo,
                             "n": len(pairs), "params": keys, "lambda": 1e-8,
                             "coef": dict({"intercept": coef[0]},
                                          **{k: coef[i + 1] for i, k in enumerate(keys)})}
    return models


def _nearest_response(ctx, hist, params, name):
    best, bd = None, None
    for h in hist:
        if not h.get("bound"):
            continue
        d = norm_dist(ctx, params, h["bound"])
        if bd is None or d < bd:
            bd, best = d, (h.get("resp") or {}).get(name)
    return best


def _margin_score(ctx, p):
    slacks = []
    for c in ctx["constraints"]:
        d = _dom(ctx, c["key"])
        if c["type"] == "mutex" or d is None or p["params"].get(c["key"]) is None:
            continue
        span = (d["max"] - d["min"]) or 1.0
        v, lim = p["params"][c["key"]], c["value"]
        if c["unit"] and d.get("unit") and c["unit"] != d["unit"]:
            cv = convert(lim, c["unit"], d["unit"])
            if cv is not None:
                lim = cv
        if c["op"] in ("le", "lt"):
            slacks.append((lim - v) / span)
        elif c["op"] in ("ge", "gt"):
            slacks.append((v - lim) / span)
    if not slacks:
        return 0.5
    return max(0.0, min(1.0, min(slacks) / 0.5))


def score_grid(ctx, grid_res, models):
    feas = grid_res.get("feasible", [])
    if not feas:
        return grid_res
    objs = ctx["objectives"]
    hist = [h for h in ctx["history"] if h.get("bound") and h.get("resp")]
    have = {o["name"]: (o["name"] in models) for o in objs}
    center = center_point(ctx, feas)
    vals = {o["name"]: [] for o in objs}
    for p in feas:
        for o in objs:
            if have[o["name"]]:
                vals[o["name"]].append(predict(models, o["name"], p["params"]))
            elif hist:
                vals[o["name"]].append(_nearest_response(ctx, hist, p["params"], o["name"]))
            else:
                vals[o["name"]].append(None)
    rng = {}
    for o in objs:
        xs = [x for x in vals[o["name"]] if x is not None]
        if xs:
            rng[o["name"]] = (min(xs), max(xs))
    for i, p in enumerate(feas):
        parts, total, wsum = {}, 0.0, 0.0
        for o in objs:
            v = vals[o["name"]][i]
            lo, hi = rng.get(o["name"], (0.0, 1.0))
            if v is None:
                parts[o["name"]] = {"value": None, "norm": None, "source": "unavailable"}
                continue
            nv = (v - lo) / ((hi - lo) or 1.0)
            if o["direction"] == "min":
                nv = 1.0 - nv
            w = 1.0 / max(1, o["priority"])
            parts[o["name"]] = {"value": round(v, 6), "norm": round(nv, 6),
                                "source": "ridge_model" if have[o["name"]] else "nearest_history"}
            total += nv * w
            wsum += w
        p["objectives"] = parts
        p["distance_to_center"] = round(norm_dist(ctx, p["params"], center), 6)
        if wsum > 0:
            p["score"] = round(total / wsum, 6)
            p["score_source"] = "objective_model"
        else:
            p["score"] = round(_margin_score(ctx, p), 6)
            p["score_source"] = "constraint_margin_design_rule"
    return grid_res


def _best(feas):
    if not feas:
        return {"params": {}, "score": 0.0, "score_source": ""}
    b = max(feas, key=lambda p: p.get("score", 0.0))
    return {"params": b["params"], "score": b.get("score", 0.0),
            "score_source": b.get("score_source", "")}


def pareto(ctx, grid_res, models):
    feas = grid_res.get("feasible", [])
    if not feas or "score" not in feas[0]:
        return {"points": [], "count": 0, "basis": "no scored feasible point"}
    objs = [o for o in ctx["objectives"]
            if any((p.get("objectives") or {}).get(o["name"], {}).get("value") is not None
                   for p in feas)]
    if len(objs) < 2:
        return {"points": [], "count": 0,
                "basis": "one indicator only; a Pareto front needs at least two "
                         "independent indicators, so none is claimed",
                "single_objective_best": _best(feas)}
    sample = feas if len(feas) <= MAX_PARETO else feas[::max(1, len(feas) // MAX_PARETO)]
    front = []
    for a in sample:
        dom = False
        for b in sample:
            if a is b:
                continue
            ge, gt = True, False
            for o in objs:
                av, bv = a["objectives"][o["name"]]["value"], b["objectives"][o["name"]]["value"]
                if av is None or bv is None:
                    ge = False
                    break
                if o["direction"] == "min":
                    if bv > av + 1e-12:
                        ge = False
                        break
                    if bv < av - 1e-12:
                        gt = True
                else:
                    if bv < av - 1e-12:
                        ge = False
                        break
                    if bv > av + 1e-12:
                        gt = True
            if ge and gt:
                dom = True
                break
        if not dom:
            front.append(a)
    front.sort(key=lambda p: -p.get("score", 0.0))
    return {"points": front[:40], "count": len(front),
            "basis": "non-dominated over %s using %s" % (
                ", ".join(o["name"] for o in objs),
                "fitted ridge model" if all(o["name"] in models for o in objs)
                else "nearest-history estimate")}


def sequential_search(ctx, grid_res, models, max_rounds=3):
    feas = grid_res.get("feasible", [])
    if not feas:
        return None
    k0 = min(len(feas), max(4, int(math.ceil(math.sqrt(len(feas))))))
    center = center_point(ctx, feas)
    far = max(feas, key=lambda p: norm_dist(ctx, p["params"], center))
    chosen = [far]
    while len(chosen) < k0:
        nxt = max((p for p in feas if p not in chosen),
                  key=lambda p: min(norm_dist(ctx, p["params"], q["params"]) for q in chosen))
        chosen.append(nxt)
    rounds = [{"round": 1, "kind": "initial_design",
               "rule": "maximin spreading seeded at the feasible centroid",
               "points": [c["params"] for c in chosen[:k0]],
               "predicted_best": round(max(c.get("score", 0.0) for c in chosen[:k0]), 6),
               "cumulative_points": k0}]
    acq = lambda p, lam: p.get("score", 0.0) - lam * p.get("distance_to_center", 0.0)
    best = max(chosen, key=lambda p: acq(p, 2.0))
    for r in range(2, (max_rounds or 3) + 1):
        cand = [p for p in feas if p not in chosen]
        if not cand:
            break
        nxt = max(cand, key=lambda p: acq(p, 1.0 / r))
        chosen.append(nxt)
        imp = max(0.0, nxt.get("score", 0.0) - best.get("score", 0.0))
        if nxt.get("score", 0.0) > best.get("score", 0.0):
            best = nxt
        rounds.append({"round": r, "kind": "refinement",
                       "rule": "greedy max of predicted score minus an exploration weight",
                       "add": nxt["params"], "predicted_best": round(best.get("score", 0.0), 6),
                       "predicted_improvement": round(imp, 6),
                       "cumulative_points": len(chosen)})
    return {"initial_batch": k0, "rounds": rounds, "total_points": len(chosen),
            "best": _best([best]),
            "basis": "scores are model-based when a fitted model exists, otherwise the "
                     "labelled constraint-margin design rule"}


def cost_model(ctx, total_points=None):
    per, formula, inputs = None, [], []
    for u in ctx["usages"]:
        for p in ctx["prices"]:
            if p["key"] == u["key"] or p["key"] in u["key"] or u["key"] in p["key"]:
                c = u["qty"] * p["price"]
                per = (per or 0.0) + c
                formula.append("%s: %s x %s = %s" % (p["name"], s(u["qty"]), s(p["price"]),
                                                     s(round(c, 6))))
                inputs.append({"name": p["name"], "qty": u["qty"], "qty_unit": u["unit"],
                               "unit_price": p["price"], "price_unit": p["unit"],
                               "line_total": round(c, 6),
                               "price_locator": p["evidence"]["locator"],
                               "usage_locator": u["evidence"]["locator"]})
    if per is None and ctx["history"]:
        cols = {k for h in ctx["history"] for k in h["row"]}
        for k in sorted(cols):
            nk = nkey(k)
            if not any(t in nk for t in ("cost", "price", "budget", "expense", "spend")):
                continue
            vals = [num(h["row"].get(k)) for h in ctx["history"]]
            vals = [x for x in vals if x is not None]
            if len(vals) >= 2:
                per = round(sum(vals) / len(vals), 6)
                formula.append("mean of the '%s' column over %d recorded runs = %s"
                               % (k, len(vals), s(per)))
                inputs.append({"name": k, "line_total": per, "samples": len(vals),
                               "locator": "%s/%s" % (ctx["history"][0]["mat"],
                                                     ctx["history"][0]["loc"])})
                break
    if per is None:
        for c in ctx["candidates"]:
            if c.get("cost") is not None:
                per = c["cost"]
                formula.append("%s: reported plan cost %s" % (c["version"], s(c["cost"])))
                inputs.append({"name": c["version"], "line_total": c["cost"],
                               "locator": c["evidence"]["locator"]})
                break
    total = per * total_points if (per is not None and total_points) else None
    afford = (int(math.floor(ctx["budget"] / per))
              if (per and per > 0 and ctx["budget"] is not None) else None)
    checks = [{"check": "per_trial_cost_is_numeric", "ok": per is not None,
               "detail": ("value %s" % s(round(per, 6))) if per is not None
               else "no price/usage pair in material"}]
    if per is not None and total is not None and total_points:
        checks.append({"check": "total_equals_per_trial_x_points",
                       "ok": abs(total - per * total_points) < 1e-6,
                       "detail": "total %s = per_trial %s x %d points"
                                 % (s(round(total, 6)), s(round(per, 6)), total_points)})
    if ctx["budget"] is not None:
        checks.append({"check": "budget_ceiling_present", "ok": True,
                       "detail": "budget %s" % s(ctx["budget"])})
    return {"status": "computed_from_sources" if per is not None else "unavailable",
            "per_trial_cost": round(per, 6) if per is not None else None,
            "total_planned_cost": round(total, 6) if total is not None else None,
            "budget": ctx["budget"], "budget_evidence": ctx.get("budget_ev", []),
            "affordable_trials": afford,
            "formula": " ; ".join(formula) if formula else
                       "no unit price and usage pair was found in the supplied material, "
                       "so no per-trial cost is claimed",
            "inputs": inputs, "checks": checks}


def _any_ok(pts, ids):
    return any(not any(v["id"] in ids for v in p["violations"]) for p in pts)


def infeasibility(ctx, grid_res):
    if not ctx["domains"]:
        return {"status": "not_applicable",
                "reason": "no finite parameter domain supplied, so feasibility is undefined"}
    if not grid_res.get("ok"):
        return {"status": "not_computable", "reason": grid_res.get("reason", "")}
    pts = grid_res["points"]
    if grid_res["feasible"]:
        return {"status": "feasible",
                "reason": "%d of %d grid points satisfy every stated bound"
                          % (len(grid_res["feasible"]), len(pts)),
                "pass_rate": round(len(grid_res["feasible"]) / max(1, len(pts)), 4)}
    def counts(kids):
        out = {}
        for p in pts:
            for v in p["violations"]:
                if v["id"] not in kids:
                    continue
                c = out.setdefault(v["id"], {"id": v["id"], "param": v["param"], "op": v["op"],
                                             "limit": v["limit"], "unit": v["unit"], "n": 0})
                c["n"] += 1
        return sorted(out.values(), key=lambda x: -x["n"])
    kept, removed = list(ctx["constraints"]), []
    kids = {c["id"] for c in kept}
    ranked = counts(kids)
    while kept and ranked:
        if _any_ok(pts, {c["id"] for c in kept}):
            break
        victim = ranked[0]
        c = next((x for x in kept if x["id"] == victim["id"]), None)
        if c is None:
            break
        removed.append(c)
        kept = [k for k in kept if k["id"] != c["id"]]
        ranked = counts({k["id"] for k in kept})
    least = min(pts, key=lambda p: len(p["violations"]))
    return {"status": "infeasible",
            "reason": "every point of the %d-point grid breaks at least one bound" % len(pts),
            "violation_counts": counts({c["id"] for c in ctx["constraints"]}),
            "minimal_conflict_set": [{"id": c["id"], "param": c["param"], "op": c["op"],
                                      "limit": c["value"], "unit": c["unit"],
                                      "locator": c["source"],
                                      "quote": (c["evidence"][0]["quote"] if c["evidence"] else "")}
                                     for c in removed],
            "relaxation_options": _relax(ctx, removed),
            "least_violating_point": {"params": least["params"], "violations": least["violations"]},
            "pass_rate": 0.0}


def _relax(ctx, removed):
    opts = []
    for c in removed:
        d = _dom(ctx, c["key"])
        if not d:
            continue
        if c["op"] in ("le", "lt"):
            opts.append({"constraint": c["id"], "param": c["param"], "current_limit": c["value"],
                         "unit": c["unit"], "suggested_limit": d["max"],
                         "delta": round(d["max"] - c["value"], 6),
                         "reason": "relaxing the stated upper bound to the domain maximum "
                                   "makes %s reachable" % c["param"]})
        elif c["op"] in ("ge", "gt"):
            opts.append({"constraint": c["id"], "param": c["param"], "current_limit": c["value"],
                         "unit": c["unit"], "suggested_limit": d["min"],
                         "delta": round(d["min"] - c["value"], 6),
                         "reason": "relaxing the stated lower bound to the domain minimum "
                                   "makes %s reachable" % c["param"]})
    return opts


def version_compare(ctx, grid_res, models):
    rows = []
    ids = [d["key"] for d in ctx["domains"]]
    for c in ctx["candidates"]:
        pmap = {}
        for k, v in (c.get("params") or {}).items():
            kk = nkey(k)
            for d in ctx["domains"]:
                if kk == d["key"] or kk == nkey(d["name"]):
                    pmap[d["key"]] = num(v)
        complete = all(pmap.get(k) is not None for k in ids) if ids else False
        chk = check_point(ctx, pmap) if complete else {"feasible": False, "violations": []}
        preds, score = {}, None
        if complete and chk["feasible"]:
            for o in ctx["objectives"]:
                v = predict(models, o["name"], pmap)
                if v is not None:
                    preds[o["name"]] = round(v, 6)
            if preds:
                score = round(sum(preds.values()) / len(preds), 6)
        rows.append({"version": c["version"], "params": pmap, "complete": complete,
                     "feasible": chk["feasible"], "violations": chk["violations"],
                     "predicted": preds, "mean_predicted": score,
                     "reported_cost": c.get("cost"), "locator": c["evidence"]["locator"],
                     "quote": c["evidence"]["quote"]})
    feasrows = [r for r in rows if r["feasible"] and r["mean_predicted"] is not None]
    if feasrows:
        best = max(feasrows, key=lambda r: r["mean_predicted"])["version"]
        basis = "highest mean predicted indicator among feasible candidates"
    elif rows:
        best = min(rows, key=lambda r: len(r["violations"]))["version"]
        basis = "fewest bound violations; no feasible candidate with a predicted score"
    else:
        best, basis = "", "no versioned candidate plan was supplied in the material"
    return {"versions": rows, "winner": best, "basis": basis}


def recommend(ctx, grid_res, models, draft):
    out = {"value": {}, "value_source": "unavailable", "band": {}, "issues": [],
           "checked_against": [], "feasible_range": {}, "basis": ""}
    if not ctx["domains"]:
        out["basis"] = ("no finite parameter domain supplied, so no numeric recommendation "
                        "can be derived from the material")
        out["issues"].append("parameter domain missing from supplied material")
        return out
    feas = grid_res.get("feasible", [])
    for d in ctx["domains"]:
        vals = [p["params"][d["key"]] for p in feas if p["params"].get(d["key"]) is not None]
        out["feasible_range"][d["key"]] = {"min": min(vals) if vals else round(d["min"], 6),
                                           "max": max(vals) if vals else round(d["max"], 6),
                                           "unit": d["unit"]}
    rec = {}
    if isinstance(draft, dict) and isinstance(draft.get("recommended"), dict):
        for k, v in draft["recommended"].items():
            for d in ctx["domains"]:
                if nkey(k) == d["key"] or nkey(k) == nkey(d["name"]):
                    rec[d["key"]] = num(v)
    if rec and all(rec.get(d["key"]) is not None for d in ctx["domains"]):
        out["value_source"] = "draft_checked"
        chk = check_point(ctx, rec)
        out["checked_against"] = chk["violations"]
        if chk["feasible"]:
            out["value"] = rec
            out["basis"] = "draft recommendation satisfies every stated bound"
        else:
            nearest = min(feas, key=lambda p: norm_dist(ctx, p["params"], rec)) if feas else None
            out["issues"] = chk["violations"]
            if nearest:
                out["value"] = dict(nearest["params"])
                out["value_source"] = "draft_repaired_to_nearest_feasible"
                out["basis"] = ("draft recommendation breaks a bound; replaced by the nearest "
                                "feasible grid point")
    elif feas:
        best = max(feas, key=lambda p: p.get("score", 0.0))
        out["value"] = dict(best["params"])
        out["value_source"] = "grid_search"
        out["basis"] = "highest %s over the enumerated feasible grid" % best.get("score_source", "score")
    else:
        inf = infeasibility(ctx, grid_res)
        least = (inf.get("least_violating_point") or {}).get("params")
        if least:
            out["value"] = dict(least)
            out["value_source"] = "least_violating_point"
            out["basis"] = "grid is infeasible; the least-violating point is reported"
            out["issues"] = [{"reason": "no feasible point on the enumerated grid"}]
    for d in ctx["domains"]:
        v = out["value"].get(d["key"])
        if v is None:
            continue
        out["band"][d["key"]] = {"low": round(max(d["min"], v - d["step"]), 6),
                                 "high": round(min(d["max"], v + d["step"]), 6),
                                 "unit": d["unit"],
                                 "rule": "one domain step of %s around the recommended value" % s(d["step"])}
    return out


def evidence_index(ctx):
    items = []
    add = lambda e, kind, name, value: items.append(dict(e, kind=kind, name=name, value=value))
    for d in ctx["domains"]:
        for e in d["evidence"]:
            add(e, "parameter_domain", d["name"],
                "[%s, %s] step %s %s" % (s(d["min"]), s(d["max"]), s(d["step"]), d["unit"]))
    for c in ctx["constraints"]:
        for e in c["evidence"]:
            add(e, "constraint", c["param"], "%s %s %s" % (c["op"], s(c["value"]), c["unit"]))
    for o in ctx["objectives"]:
        for e in o["evidence"]:
            add(e, "objective", o["name"], "direction %s" % o["direction"])
    for p in ctx["prices"]:
        add(p["evidence"], "price", p["name"], s(p["price"]))
    for u in ctx["usages"]:
        add(u["evidence"], "usage", u["name"], s(u["qty"]))
    for b in ctx["budget_ev"]:
        add(b, "budget", "budget", s(ctx["budget"]))
    for c in ctx["candidates"]:
        add(c["evidence"], "candidate_plan", c["version"],
            ",".join("%s=%s" % (k, s(v)) for k, v in c["params"].items()))
    total = len(items)
    hit = sum(1 for i in items if i.get("verified"))
    return items, {"total": total, "verbatim_hits": hit,
                   "hit_rate": round(hit / total, 4) if total else 1.0,
                   "note": ("every quoted line was re-located inside its source material"
                            if total else
                            "no extractable item carried a quotable line in the supplied material")}
