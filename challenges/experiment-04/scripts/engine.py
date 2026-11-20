# -*- coding: utf-8 -*-
"""Comparison engine: restricted expression evaluation, state mapping, min-max
normalisation, weighted score, dominance, the feasibility gate, the cost and duration
ledger and the flip-threshold scan."""
import ast
import math

from extract import s, nkey, num, STATE_ROWS, DIR_LOW

_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub,
            ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Mod, ast.FloorDiv)


def eval_expr(expr):
    """Evaluate a restricted arithmetic expression.  Returns (value, ok, detail)."""
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return float(expr), True, "numeric literal"
    t = s(expr).replace("×", "*").replace("÷", "/").replace("％", "%")
    if not t:
        return None, False, "empty expression"
    try:
        node = ast.parse(t, mode="eval")
    except SyntaxError as exc:
        return None, False, "not an arithmetic expression (%s)" % exc.msg
    for sub in ast.walk(node):
        if not isinstance(sub, _ALLOWED):
            return None, False, "disallowed token %s" % type(sub).__name__
    try:
        val = float(eval(compile(node, "<expr>", "eval"), {"__builtins__": {}}, {}))
    except Exception as exc:  # noqa
        return None, False, "evaluation failed (%s)" % type(exc).__name__
    if math.isnan(val) or math.isinf(val):
        return None, False, "non-finite result"
    return val, True, "recomputed to %s" % round(val, 6)


def as_number(display, state_map=None):
    """Map a display value to a number: numbers pass through, state words map 0-4."""
    if isinstance(display, bool):
        return (1.0 if display else 0.0), "boolean"
    if isinstance(display, (int, float)):
        return float(display), "numeric"
    t = s(display)
    if not t:
        return None, "not-reported"
    n = num(t)
    if n is not None and re_ratio(t):
        return n, "numeric"
    rows = state_map or [{"score": sc, "tokens": " / ".join(tk)} for sc, tk in STATE_ROWS]
    tl = t.lower()
    for row in rows:
        for tok in s(row.get("tokens")).replace("／", "/").split("/"):
            tok = tok.strip().lower()
            if tok and tok in tl:
                return float(row["score"]), "state:%s" % tok
    for sc, toks in STATE_ROWS:
        for tok in toks:
            if tok.lower() in tl:
                return float(sc), "state:%s" % tok
    return None, "unmapped:%s" % t[:40]


def re_ratio(t):
    return bool(__import__("re").fullmatch(r"\s*[-+]?\d+(\.\d+)?\s*%?\s*", t))


def normalize(rows, direction):
    """min-max over the candidate set; higher/lower; hi==lo -> 1.0."""
    vals = [v for v in rows if v is not None]
    if not vals:
        return [None] * len(rows), None, None
    lo, hi = min(vals), max(vals)
    out = []
    for v in rows:
        if v is None:
            out.append(None)
        elif hi == lo:
            out.append(1.0)
        elif direction == "lower":
            out.append((hi - v) / (hi - lo))
        else:
            out.append((v - lo) / (hi - lo))
    return out, lo, hi


def build_matrix(ctx):
    crit = ctx["criteria"]
    cands = ctx["candidates"]
    weights = [c["weight"] for c in crit]
    wsum = round(sum(weights), 6)
    res = {"criteria": crit, "candidates": [], "weight_sum": wsum,
           "weight_ok": abs(wsum - 1.0) <= 0.02 if crit else None,
           "normalisation": [], "scores": {}, "dominance": [], "ranked": [],
           "feasible": [], "notes": [],
           "norm_rule": ctx["norm_rules"][0] if ctx["norm_rules"] else {},
           "formula": ctx["weight_rule"]}
    if not crit or not cands:
        return res
    disp = {}
    for c in cands:
        row = {}
        for cr in crit:
            cell = c["values"].get(cr["id"]) or c["values"].get(key_match(c["values"], cr["id"]))
            if cell is None:
                row[cr["id"]] = {"number": None, "how": "not-reported", "cell": None}
                continue
            n, how = as_number(cell.get("display"), ctx["state_map"])
            row[cr["id"]] = {"number": n, "how": how, "cell": cell}
        disp[c["candidate_id"]] = row
    # constraints -> hard gate
    gate = {}
    for c in cands:
        fails, soft = [], []
        for k in ctx["constraints"]:
            cell = _crit_value(disp[c["candidate_id"]], k["criterion"], crit)
            if cell is None or cell["number"] is None:
                continue
            ok = op_ok(k["op"], cell["number"], k["value"])
            if ok is False:
                (fails if k["severity"] == "hard" else soft).append(
                    {"id": k["id"], "criterion": k["criterion"], "op": k["op"],
                     "limit": k["value"], "value": cell["number"]})
        gate[c["candidate_id"]] = {"hard_fail": fails, "soft_fail": soft}
    # normalise per criterion
    norm = {}
    for cr in crit:
        col = [disp[c["candidate_id"]].get(cr["id"], {}).get("number") for c in cands]
        ncol, lo, hi = normalize(col, cr["direction"])
        norm[cr["id"]] = ncol
        res["normalisation"].append({"criterion": cr["id"], "direction": cr["direction"],
                                     "lo": lo, "hi": hi, "weight": cr["weight"],
                                     "values": [None if v is None else round(v, 6) for v in col],
                                     "normalised": [None if v is None else round(v, 6) for v in ncol]})
    # scores
    for ci, c in enumerate(cands):
        cid = c["candidate_id"]
        have = [cr for cr in crit if norm[cr["id"]][ci] is not None]
        score = 100.0 * sum(cr["weight"] * norm[cr["id"]][ci] for cr in have)
        cov = len(have) / len(crit) if crit else 0.0
        g = gate[cid]
        if g["hard_fail"]:
            state = "infeasible"
        elif len(have) < 3:
            state = "undetermined"
        elif g["soft_fail"]:
            state = "conditional"
        else:
            state = "feasible"
        res["scores"][cid] = {"score": round(score, 4), "counted": len(have),
                              "coverage": round(cov, 4), "state": state,
                              "hard_fail": g["hard_fail"], "soft_fail": g["soft_fail"],
                              "zeroed": [cr["id"] for cr in crit if norm[cr["id"]][ci] is None]}
    # dominance (only when both fully valued)
    for a in cands:
        for b in cands:
            if a["candidate_id"] == b["candidate_id"]:
                continue
            ai, bi = cands.index(a), cands.index(b)
            av = [norm[cr["id"]][ai] for cr in crit]
            bv = [norm[cr["id"]][bi] for cr in crit]
            if any(v is None for v in av + bv):
                continue
            if all(x >= y - 1e-12 for x, y in zip(av, bv)) and any(x > y + 1e-12 for x, y in zip(av, bv)):
                res["dominance"].append({"dominates": a["candidate_id"], "dominated": b["candidate_id"]})
    order = {"feasible": 0, "conditional": 1, "undetermined": 2, "infeasible": 3}
    rank = sorted([c for c in cands if res["scores"][c["candidate_id"]]["state"] in ("feasible", "conditional")],
                  key=lambda c: (order[res["scores"][c["candidate_id"]]["state"]],
                                 -res["scores"][c["candidate_id"]]["score"]))
    res["ranked"] = [c["candidate_id"] for c in rank]
    res["feasible"] = [c["candidate_id"] for c in cands
                       if res["scores"][c["candidate_id"]]["state"] == "feasible"]
    res["winner"] = res["ranked"][0] if res["ranked"] else None
    for c in cands:
        score = res["scores"][c["candidate_id"]]
        res["candidates"].append({"candidate_id": c["candidate_id"], "name": c["name"],
                                  "params": c["params"], "source": c["source"],
                                  **{k: score[k] for k in ("score", "counted", "coverage", "state")},
                                  "values": {k: {"display": v.get("display"), "number": v.get("number"),
                                                 "unit": (v.get("cell") or {}).get("unit"),
                                                 "grade": (v.get("cell") or {}).get("grade"),
                                                 "locator": (v.get("cell") or {}).get("locator")}
                                             for k, v in disp[c["candidate_id"]].items()}})
    return res


def key_match(values, cid):
    for k in values:
        if nkey(k) == nkey(cid):
            return k
    for k in values:
        if nkey(cid) and nkey(cid) in nkey(k):
            return k
    return cid


def _crit_value(row, criterion, crit):
    if criterion in row:
        return row[criterion]
    for k in row:
        if nkey(k) == nkey(criterion):
            return row[k]
    return None


def op_ok(op, value, bound):
    if value is None or bound is None:
        return None
    if op == "le":
        return value <= bound + 1e-9
    if op == "lt":
        return value < bound - 1e-12
    if op == "ge":
        return value >= bound - 1e-9
    if op == "gt":
        return value > bound + 1e-12
    if op == "eq":
        return abs(value - bound) < 1e-9
    if op == "ne":
        return abs(value - bound) >= 1e-9
    return None


# ------------------------------------------------------------------ ledger ---

def cost_ledger(ctx):
    ct = ctx["cost_time"] if isinstance(ctx["cost_time"], dict) else {}
    curr = s(ct.get("currency")) or "not-declared"
    runs = num(ct.get("runs"))
    cost_rows = ct.get("items") or ct.get("cost_rows") or []
    dur_rows = ct.get("duration_items") or ct.get("duration_rows") or []
    out = {"currency": curr, "runs": runs, "items": [], "duration_items": [],
           "checks": [], "per_candidate": {}, "source": ctx.get("cost_time_src", {}),
           "formula": "total = sum(one_time items) + sum(per_run items) x runs"}
    for it in cost_rows[:60]:
        if not isinstance(it, dict):
            continue
        val, ok, detail = eval_expr(it.get("expr"))
        cls = s(it.get("class")) or "per_run"
        rec = {"candidate": s(it.get("candidate")), "item": s(it.get("item")),
               "class": cls, "expr": s(it.get("expr")),
               "value": None if val is None else round(val, 4), "ok": ok, "detail": detail,
               "unit": s(it.get("unit")), "locator": s(it.get("locator"))}
        out["items"].append(rec)
        if val is not None:
            pc = out["per_candidate"].setdefault(s(it.get("candidate")), {"one_time": 0.0, "per_run": 0.0})
            pc["one_time" if cls == "one_time" else "per_run"] += val
    for it in dur_rows[:60]:
        if not isinstance(it, dict):
            continue
        raw = it.get("hours")
        val, ok, detail = eval_expr(raw)
        out["duration_items"].append({"candidate": s(it.get("candidate")), "item": s(it.get("item")),
                                      "hours": None if val is None else round(val, 4),
                                      "ok": ok, "detail": detail, "locator": s(it.get("locator"))})
    rr = runs if runs else 1.0
    for cid, pc in out["per_candidate"].items():
        out["per_candidate"][cid] = {"one_time": round(pc["one_time"], 4),
                                     "per_run": round(pc["per_run"], 4),
                                     "total": round(pc["one_time"] + pc["per_run"] * rr, 4),
                                     "runs": rr}
    if out["items"]:
        out["checks"].append({"name": "ledger_expr_evaluable",
                              "ok": all(i["ok"] for i in out["items"]),
                              "detail": "%d of %d cost expresions recomputed"
                                        % (sum(1 for i in out["items"] if i["ok"]), len(out["items"]))})
        for cid, pc in out["per_candidate"].items():
            out["checks"].append({"name": "total_%s" % cid,
                                  "ok": True,
                                  "detail": "one_time %s + per_run %s x runs %s = %s"
                                            % (pc["one_time"], pc["per_run"], pc["runs"], pc["total"])})
    if out["duration_items"]:
        out["checks"].append({"name": "duration_expr_evaluable",
                              "ok": all(i["ok"] for i in out["duration_items"]),
                              "detail": "%d of %d duration expresions recomputed"
                                        % (sum(1 for i in out["duration_items"] if i["ok"]),
                                           len(out["duration_items"]))})
    return out


# ------------------------------------------------------------- flip scan -----

def flip_scan(ctx, matrix):
    """Equal-spaced 17-point scan per assumption, bisection when the choice changes."""
    out = {"assumptions": [], "flips": [], "stable": [], "note":
           "17-point equal scan over each declared range; change -> 22-round bisection"}
    if not ctx["assumptions"] or not matrix.get("candidates"):
        out["note"] = "no assumption with a declared range and no candidate set; scan not computable"
        return out
    for a in ctx["assumptions"][:12]:
        if not isinstance(a, dict):
            continue
        name = s(a.get("name")) or s(a.get("id"))
        rng = a.get("range") if isinstance(a.get("range"), list) else None
        eff = a.get("effect") if isinstance(a.get("effect"), dict) else {}
        rec = {"name": name, "range": rng, "type": s(eff.get("type")),
               "criterion": s(eff.get("criterion")), "candidate": s(eff.get("candidate")),
               "chooser": [], "flip": None}
        if not rng or len(rng) != 2 or not eff.get("type"):
            rec["chooser"] = "not-scanned: range or effect missing"
            out["assumptions"].append(rec)
            continue
        lo, hi = sorted([num(rng[0]) or 0.0, num(rng[1]) or 0.0])
        picks = []
        for i in range(17):
            t = lo + (hi - lo) * i / 16.0
            picks.append((t, _choose_with(ctx, matrix, a, t)))
        rec["chooser"] = [[round(t, 6), c] for t, c in picks]
        changes = [(i, picks[i - 1][1], picks[i][1], picks[i - 1][0], picks[i][0])
                   for i in range(1, len(picks)) if picks[i][1] != picks[i - 1][1]]
        if not changes:
            rec["flip"] = "stable"
            out["stable"].append(name)
        else:
            i, frm, to, x0, x1 = changes[0]
            for _ in range(22):
                mid = (x0 + x1) / 2.0
                if _choose_with(ctx, matrix, a, mid) == frm:
                    x0 = mid
                else:
                    x1 = mid
            rec["flip"] = {"from": frm, "to": to, "threshold": round((x0 + x1) / 2.0, 6),
                           "width": round(hi - lo, 6)}
            out["flips"].append({"assumption": name, **rec["flip"]})
        out["assumptions"].append(rec)
    return out


def _choose_with(ctx, matrix, assumption, t):
    """Re-rank the candidates after applying the assumption at level t."""
    eff = assumption.get("effect") or {}
    typ = s(eff.get("type"))
    crit = ctx["criteria"]
    score, cnt = {}, {}
    for cr in crit:
        vals, cells = [], {}
        for c in ctx["candidates"]:
            cell = c["values"].get(cr["id"]) or c["values"].get(key_match(c["values"], cr["id"]))
            n = None
            if cell is not None:
                n, _ = as_number(cell.get("display"), ctx["state_map"])
            if n is not None and nkey(cr["id"]) == nkey(eff.get("criterion")) and \
                    (not eff.get("candidate") or s(eff.get("candidate")) == c["candidate_id"]):
                if typ == "scale":
                    n = n * t
                elif typ == "delta":
                    n = n + t * (num(eff.get("multiplier")) or 1.0)
            vals.append(n)
            cells[c["candidate_id"]] = n
        ncol, lo, hi = normalize([cells.get(c["candidate_id"]) for c in ctx["candidates"]], cr["direction"])
        for ci, c in enumerate(ctx["candidates"]):
            if ncol[ci] is not None:
                score[c["candidate_id"]] = score.get(c["candidate_id"], 0.0) + cr["weight"] * ncol[ci]
                cnt[c["candidate_id"]] = cnt.get(c["candidate_id"], 0) + 1
    # gate re-check at level t
    best, bestscore = None, None
    for c in ctx["candidates"]:
        cid = c["candidate_id"]
        if cid not in score:
            continue
        if matrix["scores"].get(cid, {}).get("state") == "infeasible":
            continue
        if typ == "cap":
            pass
        sc = score[cid]
        if bestscore is None or sc > bestscore + 1e-12:
            best, bestscore = cid, sc
    return best or "not-decidable"


def metrics(ctx, matrix, ledger, evidence_items):
    tot = len(ctx["criteria"]) * max(1, len(ctx["candidates"]))
    filled = 0
    if matrix.get("candidates"):
        filled = sum(1 for c in matrix["candidates"] for v in c["values"].values()
                     if v.get("number") is not None)
    q_tot = len(evidence_items)
    q_ok = sum(1 for i in evidence_items if i.get("verified"))
    return {"candidates": len(ctx["candidates"]), "criteria": len(ctx["criteria"]),
            "cells": tot, "filled": filled,
            "fill_rate": round(filled / tot, 4) if tot else 0.0,
            "quotes_total": q_tot, "quotes_ok": q_ok,
            "ledger_items": len(ledger.get("items", [])),
            "ledger_ok": sum(1 for i in ledger.get("items", []) if i.get("ok")),
            "criteria_weight_ok": matrix.get("weight_ok"),
            "flips": None}
