# -*- coding: utf-8 -*-
"""plan-forge-experiment :: engine layer — value primitives, material scanning and quote helpers, grid and arithmetic work, the six validation rules, the revision pass and versioning. Imports nothing from plan.py or render.py."""
import json, math, os, re

UNIT_ALIASES = {"c": "c", "°c": "c", "k": "k", "min": "min", "m": "min",
                "h": "h", "s": "s", "ml": "ml", "l": "l", "ul": "ul", "µl": "ul",
                "μl": "ul", "g": "g", "kg": "kg", "mg": "mg", "ug": "ug", "µg": "ug",
                "μg": "ug", "mbar": "mbar", "bar": "bar", "kpa": "kpa", "mpa": "mpa",
                "rpm": "rpm", "v": "v", "a": "a", "%": "pct", "pct": "pct",
                "usd": "usd", "$": "usd", "cny": "cny", "rmb": "cny", "¥": "cny",
                "元": "cny", "×g": "xg", "xg": "xg", "µm": "um", "um": "um",
                "nm": "nm", "cm": "cm", "mm": "mm"}

CONV = {("min", "h"): 1 / 60.0, ("h", "min"): 60.0, ("min", "s"): 60.0,
        ("s", "min"): 1 / 60.0, ("h", "s"): 3600.0, ("s", "h"): 1 / 3600.0,
        ("ml", "l"): 0.001, ("l", "ml"): 1000.0, ("ul", "ml"): 0.001,
        ("ml", "ul"): 1000.0, ("g", "kg"): 0.001, ("kg", "g"): 1000.0,
        ("g", "mg"): 1000.0, ("mg", "g"): 0.001, ("mg", "ug"): 1000.0,
        ("ug", "mg"): 0.001, ("ul", "l"): 1e-6, ("l", "ul"): 1e6,
        ("ug", "g"): 1e-6, ("g", "ug"): 1e6, ("kpa", "mpa"): 0.001,
        ("mpa", "kpa"): 1000.0, ("bar", "mbar"): 1000.0, ("mbar", "bar"): 0.001,
        ("um", "mm"): 0.001, ("mm", "um"): 1000.0, ("mm", "cm"): 0.1, ("cm", "mm"): 10.0}

UNIT_RX = ("L|mL|ml|µL|μL|uL|ul|kg|mg|µg|μg|ug|g|°C|℃|×g|rpm|V|A|%|min|h|s|"
           "mM|µM|nM|M|nm|µm|μm|um|cm|mm|m|day|d|次|例|个|支|管|孔|盒|包|瓶|板|袋|套")


def s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
            return str(int(round(v)))
        return ("%.6f" % v).rstrip("0").rstrip(".")
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def nkey(v):
    t = s(v).lower().replace("°", "").replace("℃", "c")
    return re.sub(r"[^0-9a-z一-鿿]+", "", t)


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return float(v)
    t = s(v)
    if not t:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", t.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def bnum(v):
    if isinstance(v, bool):
        return v
    t = s(v).lower()
    if t in ("yes", "true", "y", "1", "可", "是", "允许"):
        return True
    if t in ("no", "false", "n", "0", "不可", "否", "禁止"):
        return False
    return None


def unit_of(v):
    t = s(v).lower()
    m = re.search(UNIT_RX, t)
    if m:
        return UNIT_ALIASES.get(m.group(0), m.group(0))
    for tok, u in UNIT_ALIASES.items():
        if tok and tok in t:
            return u
    return ""


def convert(val, uf, ut):
    if not uf or not ut or uf == ut:
        return val
    if uf == "c" and ut == "k":
        return val + 273.15
    if uf == "k" and ut == "c":
        return val - 273.15
    f = CONV.get((uf, ut))
    return None if f is None else val * f


def first_of(d, keys):
    for k in keys:
        if isinstance(d, dict) and k in d and s(d[k]) != "":
            return d[k]
    return None


def scan_materials(input_dir):
    mats = []
    if not os.path.isdir(input_dir):
        return mats
    idx = 0
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            idx += 1
            try:
                with open(full, "rb") as fh:
                    raw = fh.read(4_000_000)
            except OSError:
                raw = b""
            binary = b"\x00" in raw[:4096]
            text = "" if binary else raw.decode("utf-8", "replace")
            obj = None
            if fn.lower().endswith(".json") and text.strip():
                try:
                    obj = json.loads(text)
                except ValueError:
                    obj = None
            mats.append({"id": "M%02d" % idx, "name": fn,
                         "rel": os.path.relpath(full, input_dir).replace("\\", "/"),
                         "path": full, "text": text, "json": obj,
                         "chars": len(text), "binary": binary,
                         "kind": "json" if obj is not None else ("text" if text else "binary")})
    return mats


def paras_of(mid, text):
    out, buf, pi = [], [], 0
    for ln in (text or "").splitlines():
        if ln.strip():
            buf.append(ln.rstrip())
        elif buf:
            pi += 1
            out.append({"locator": "%s/p%d" % (mid, pi), "text": "\n".join(buf)})
            buf = []
    if buf:
        pi += 1
        out.append({"locator": "%s/p%d" % (mid, pi), "text": "\n".join(buf)})
    return out


def find_quote(text, needles, limit=300):
    if not text:
        return ""
    for n in needles:
        tok = s(n)
        if not tok:
            continue
        i = text.find(tok)
        if i < 0:
            i = text.lower().find(tok.lower())
            if i < 0:
                continue
        start = text.rfind("\n", 0, i)
        start = 0 if start < 0 else start + 1
        end = min(len(text), start + limit)
        if end < i + len(tok):
            end = min(len(text), i + len(tok) + 40)
        return text[start:end].strip()[:limit]
    return ""


def ev(mat, path, needles):
    text = mat.get("text", "")
    q = find_quote(text, needles)
    loc = ("%s/%s" % (mat["id"], path)) if path else mat["id"]
    ok = bool(q) and q[:120] in text
    if not q:
        q = "value at %s (no quotable line)" % loc
    return {"source_id": mat["id"], "locator": loc, "quote": q, "verified": ok}


def walk(o, path, out, depth=0):
    if depth > 8:
        return
    if isinstance(o, dict):
        out.append((path, o))
        for k in sorted(o.keys()):
            walk(o[k], "%s.%s" % (path, k), out, depth + 1)
    elif isinstance(o, list):
        for i, v in enumerate(o[:400]):
            walk(v, "%s[%d]" % (path, i), out, depth + 1)


FENCE_RX = re.compile(r"```[A-Za-z]*[ \t]*\r?\n(.*?)```", re.S)
RANGE_RX = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:–|—|~|至|to|-)\s*(-?\d+(?:\.\d+)?)\s*(" + UNIT_RX + r")")


def fenced_blocks(text):
    """Parse fenced code blocks that happen to be valid JSON data sources."""
    out = []
    if not text:
        return out
    for i, m in enumerate(FENCE_RX.finditer(text)):
        body = m.group(1).strip()
        if not body or not body.startswith(("{", "[")):
            continue
        try:
            obj = json.loads(body)
        except ValueError:
            continue
        line = text[:m.start(1)].count("\n") + 1
        out.append({"obj": obj, "path": "$fence[%d]@L%d" % (i, line)})
    return out


def parse_range(txt):
    """Pull (min, max, unit, step) out of a stated allowed range."""
    m = RANGE_RX.search(s(txt))
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    if hi <= lo:
        return None
    st = None
    sm = re.search(r"step\s*[:=]?\s*([\d.]+)", s(txt), re.I)
    if sm:
        st = num(sm.group(1))
    return lo, hi, UNIT_ALIASES.get(m.group(3).lower(), m.group(3).lower()), st


OPS = {"le": lambda a, b: a <= b + 1e-9, "lt": lambda a, b: a < b - 1e-12,
       "ge": lambda a, b: a >= b - 1e-9, "gt": lambda a, b: a > b + 1e-12,
       "eq": lambda a, b: abs(a - b) <= 1e-9, "ne": lambda a, b: abs(a - b) > 1e-9}


def axis_values(d, cap=400):
    lo, hi, st = d["min"], d["max"], d["step"]
    if st <= 0:
        st = (hi - lo) / 10.0
    n = int(math.floor((hi - lo) / st + 1e-9)) + 1
    vals, k, g = [], 0, 0
    while k < n and g < cap:
        v = lo + k * st
        if v > hi + 1e-9:
            break
        vals.append(round(v, 10))
        k += 1
        g += 1
    if not vals:
        vals = [lo, hi]
    return vals


def domain_map(ctx):
    return {d["key"]: d for d in ctx["domains"]}


def in_domain(d, v):
    return d["min"] - 1e-9 <= v <= d["max"] + 1e-9


def on_step(d, v, tol=1e-6):
    if d["step"] <= 0:
        return True
    k = (v - d["min"]) / d["step"]
    return abs(k - round(k)) <= tol


def resolve_param(domains, key):
    kk = nkey(key)
    if kk in domains:
        return domains[kk]
    hits = {v for k, v in domains.items() if len(k) >= 3 and (k in kk or kk in k)}
    return hits.pop() if len(hits) == 1 else None


def planned_value(plan, d):
    """Value the plan assigns to domain d, or None."""
    for k, v in plan["params"].items():
        if resolve_param({d["key"]: d}, k):
            x = num(v)
            if x is not None:
                return x
    for st in plan["steps"]:
        for k, v in st["params"].items():
            if resolve_param({d["key"]: d}, k):
                x = num(v)
                if x is not None:
                    return x
    return None


def generate_plans(ctx):
    """Three versioned candidates derived by rule from the declared domains."""
    ds = ctx["domains"]
    modes = [("v1", 1.0 / 3.0, "conservative: lower third of every declared range"),
             ("v2", 0.5, "balanced: midpoint of every declared range"),
             ("v3", 2.0 / 3.0, "aggressive: upper third of every declared range")]
    plans = []
    for ver, frac, why in modes:
        params = {}
        for d in ds:
            raw = d["min"] + frac * (d["max"] - d["min"])
            vals = axis_values(d)
            near = min(vals, key=lambda v: abs(v - raw))
            params[d["name"]] = near
        plans.append({"version": ver, "params": params,
                      "steps": [dict(st) for st in ctx.get("step_template") or []],
                      "usages": {}, "samples": None, "reported_cost": None,
                      "reported_duration": None, "material": "RULE", "path": "generated",
                      "evidence": {"source_id": "RULE", "locator": "generated",
                                   "quote": why, "verified": False},
                      "source": "generated", "basis": why})
    return plans


def usage_amount(plan, res):
    """Amount of a resource a plan consumes."""
    for k, v in plan["usages"].items():
        if nkey(k) == res["key"] or (len(res["key"]) >= 3 and (res["key"] in nkey(k) or nkey(k) in res["key"])):
            x = num(v)
            if x is not None:
                return x, "plan usage for %s" % k
    if res.get("qty") is not None:
        return res["qty"], "declared per-run quantity of %s" % res["name"]
    return None, ""


def step_duration(plan):
    """Serial duration = sum of step minutes; parallel groups counted once (max)."""
    groups, total, lines = {}, 0.0, []
    for st in plan["steps"]:
        m = st.get("duration_min")
        if m is None:
            continue
        g = st.get("parallel_group")
        if g:
            groups[g] = max(groups.get(g, 0.0), float(m))
            lines.append("%s (%s) %s min, parallel group %s" % (st["id"], st["action"][:24], s(m), g))
        else:
            total += float(m)
            lines.append("%s (%s) %s min, serial" % (st["id"], st["action"][:24], s(m)))
    for g, mx in sorted(groups.items()):
        total += mx
    return round(total, 6), lines


def serial_minutes(plan):
    return step_duration(plan)[0]


def arithmetic(ctx, plan):
    cost, cost_lines, cost_inputs = 0.0, [], []
    known = False
    for res in ctx["resources"]:
        amt, why = usage_amount(plan, res)
        price = res.get("price")
        if amt is None or price is None:
            if res.get("price") is None:
                cost_inputs.append({"name": res["name"], "amount": s(amt),
                                    "unit_price": "absent",
                                    "note": "no unit price found for this item; cost left out of the total",
                                    "locator": "%s/%s" % (res["material"], res["path"])})
            continue
        per_sample = amt * price
        cost += per_sample
        known = True
        cost_lines.append("%s: %s %s x %s = %s" % (res["name"], s(amt), res["unit"] or "unit",
                                                   s(price), s(round(per_sample, 6))))
        cost_inputs.append({"name": res["name"], "amount": amt, "unit": res["unit"],
                            "unit_price": price, "line_total": round(per_sample, 6),
                            "basis": why,
                            "locator": "%s/%s" % (res["material"], res["path"])})
    duration, dur_lines = step_duration(plan)
    if duration <= 0 and plan.get("reported_duration") is not None:
        duration = float(plan["reported_duration"])
        dur_lines = ["reported total duration %s min (no per-step minutes supplied)"
                     % s(duration)]
    per_run = round(cost, 6) if known else None
    total = None
    if per_run is not None:
        reps = plan.get("samples") or 1
        total = round(per_run * reps, 6)
        cost_lines.append("total = %s per run x %s run(s) = %s" % (s(per_run), s(reps), s(total)))
    checks = []
    recon = round(sum(i["line_total"] for i in cost_inputs if i.get("line_total") is not None), 6)
    checks.append({"name": "cost_reconciliation", "evaluated": per_run is not None,
                   "ok": (per_run is None) or abs(recon - per_run) < 1e-6,
                   "detail": ("no priced item matched this plan, so the cost identity could not be evaluated"
                              if per_run is None else
                              "sum of line totals %s equals the per-run cost %s" % (s(recon), s(per_run)))})
    if ctx["budget"] is not None and total is not None:
        checks.append({"name": "budget_ceiling", "evaluated": True, "ok": total <= ctx["budget"] + 1e-9,
                       "detail": "total %s vs budget %s" % (s(total), s(ctx["budget"]))})
    checks.append({"name": "duration_reconciliation", "evaluated": duration > 0,
                   "ok": abs(duration - serial_minutes(plan)) < 1e-6,
                   "detail": ("no step carried a duration, so the time identity could not be evaluated"
                              if duration <= 0 else
                              "serial step minutes plus one maximum per parallel group = %s min"
                              % s(duration))})
    if ctx["deadline_days"] is not None and duration > 0:
        days = duration / 480.0
        checks.append({"name": "calendar_fit", "evaluated": True, "ok": days <= ctx["deadline_days"] + 1e-9,
                       "detail": "%s min = %.2f working days (8 h) vs available %s day(s)"
                                 % (s(duration), days, s(ctx["deadline_days"]))})
    return {"per_run_cost": per_run, "total_cost": total, "replicates": plan.get("samples") or 1,
            "duration_min": duration, "cost_formula":
                "line_total = amount x unit_price ; total = per_run_cost x replicates",
            "cost_lines": cost_lines, "duration_lines": dur_lines,
            "cost_inputs": cost_inputs, "checks": checks}


def check_point(ctx, params):
    out = []
    dm = domain_map(ctx)
    for name, val in params.items():
        d = resolve_param(dm, name)
        x = num(val)
        if d is None or x is None:
            out.append({"rule": "param_domain", "ok": False,
                        "detail": "parameter '%s' does not map to any declared finite domain" % s(name)})
            continue
        ok = in_domain(d, x) and on_step(d, x)
        out.append({"rule": "param_domain", "ok": ok,
                    "detail": "%s=%s %s %s domain [%s, %s] step %s"
                              % (d["name"], s(x), d["unit"], "inside" if ok else "outside",
                                 s(d["min"]), s(d["max"]), s(d["step"]))})
    return out


def validate(ctx, plan):
    viol, warnings, notes = [], [], []
    dm = domain_map(ctx)
    # rule 1: parameter domain
    seen_param = set()
    for name, val in plan["params"].items():
        d = resolve_param(dm, name)
        x = num(val)
        if d is None:
            if len(dm):
                warnings.append({"rule": "param_domain",
                                 "detail": "value '%s=%s' has no matching finite domain" % (name, s(val))})
            continue
        seen_param.add(d["key"])
        if x is None:
            viol.append({"rule": "param_domain",
                         "detail": "%s has a non-numeric value '%s'" % (d["name"], s(val))})
        elif not in_domain(d, x):
            viol.append({"rule": "param_domain",
                         "detail": "%s=%s %s outside domain [%s, %s]"
                                   % (d["name"], s(x), d["unit"], s(d["min"]), s(d["max"]))})
        elif not on_step(d, x):
            warnings.append({"rule": "param_domain",
                             "detail": "%s=%s is inside the range but off the %s step grid"
                                       % (d["name"], s(x), s(d["step"]))})
    for d in ctx["domains"]:
        if d["key"] not in seen_param and (plan["params"] or plan["steps"]):
            warnings.append({"rule": "param_domain",
                             "detail": "domain %s is never set by this plan" % d["name"]})
    # rule 2: constraints
    for c in ctx["constraints"]:
        if c["op"] == "mutex":
            continue
        d = resolve_param(dm, c["param"])
        if d is None:
            continue
        x = planned_value(plan, d)
        if x is None:
            continue
        if c["value"] is not None and not OPS[c["op"]](x, float(c["value"])):
            viol.append({"rule": "constraint_%s" % c["op"],
                         "detail": "%s: %s=%s %s %s %s (source %s)"
                                   % (c["id"], d["name"], s(x), c["op"], s(c["value"]),
                                      c["note"] or "stated constraint", c["source"])})
    # rule 3: booking window
    bk = [r for r in ctx["resources"] if r["booking"]]
    if not bk:
        notes.append({"rule": "booking",
                      "detail": "no booking window was declared for any facility; the rule is reported as open"})
    for r in bk:
        notes.append({"rule": "booking",
                      "detail": "%s booking '%s' must be reserved before the run" % (r["name"], r["booking"])})
    # rule 4: budget
    ar = plan.get("_arith") or arithmetic(ctx, plan)
    if ctx["budget"] is None:
        notes.append({"rule": "budget", "detail": "no budget ceiling declared; cost is reported without a pass/fail"})
    elif ar["total_cost"] is None:
        notes.append({"rule": "budget",
                      "detail": "no priced item matched this plan, so the budget check could not be evaluated"})
    elif ar["total_cost"] > ctx["budget"] + 1e-9:
        viol.append({"rule": "budget",
                     "detail": "total %s exceeds budget %s" % (s(ar["total_cost"]), s(ctx["budget"]))})
    # rule 5: quantity
    for r in ctx["resources"]:
        amt, _ = usage_amount(plan, r)
        if amt is not None and r.get("qty") is not None and amt > r["qty"] + 1e-9:
            viol.append({"rule": "quantity",
                         "detail": "%s needs %s %s but only %s %s are on hand"
                                   % (r["name"], s(amt), r["unit"], s(r["qty"]), r["unit"])})
    # rule 6: control
    if not ctx["controls"]:
        viol.append({"rule": "control",
                     "detail": "no control arm is defined for the plan's readout"})
    # rule 7: unit
    for r in ctx["resources"]:
        if r.get("price") is not None and not r.get("unit"):
            warnings.append({"rule": "unit",
                             "detail": "no unit declared for priced item %s" % r["name"]})
    for d in ctx["domains"]:
        if not d.get("unit"):
            warnings.append({"rule": "unit", "detail": "no unit declared for parameter %s" % d["name"]})
    return {"violations": viol, "warnings": warnings, "notes": notes,
            "ok": not viol,
            "summary": ("%d hard violation(s), %d warning(s), %d open note(s)"
                        % (len(viol), len(warnings), len(notes)))}


def revise(ctx, plan, vres):
    """Repair a plan: pull out-of-domain values back to the nearest legal grid point,
    trim over-quantity usage to stock, and cut replicates until the cost fits the budget."""
    actions, fixed = [], dict(plan)
    fixed.pop("_arith", None)
    fixed["params"] = dict(plan["params"])
    fixed["usages"] = dict(plan["usages"])
    dm = domain_map(ctx)
    for v in vres["violations"]:
        if v["rule"] == "param_domain":
            for name in list(fixed["params"].keys()):
                d = resolve_param(dm, name)
                x = num(fixed["params"][name])
                if d is None or x is None:
                    continue
                if not in_domain(d, x) or not on_step(d, x):
                    vals = axis_values(d)
                    near = min(vals, key=lambda q: (abs(q - x), q))
                    if abs(near - x) > 1e-9:
                        actions.append({"kind": "clamp_parameter", "target": d["name"],
                                        "from": x, "to": near, "unit": d["unit"],
                                        "why": "%s violated its finite domain; moved to the nearest legal grid point"
                                               % d["name"]})
                        fixed["params"][name] = near
        elif v["rule"] == "constraint_le" or v["rule"] == "constraint_ge" or \
                v["rule"] == "constraint_lt" or v["rule"] == "constraint_gt":
            rid = v["detail"].split(":")[0]
            c = next((c for c in ctx["constraints"] if c["id"] == rid), None)
            if c is None:
                continue
            d = resolve_param(dm, c["param"])
            if d is None:
                continue
            for name in list(fixed["params"].keys()):
                if not resolve_param({d["key"]: d}, name):
                    continue
                vals = [q for q in axis_values(d) if OPS[c["op"]](q, float(c["value"]))]
                if not vals:
                    continue
                cur = num(fixed["params"][name])
                near = min(vals, key=lambda q: (abs(q - cur), q))
                if abs(near - cur) > 1e-9:
                    actions.append({"kind": "satisfy_constraint", "target": d["name"],
                                    "from": cur, "to": near, "unit": d["unit"],
                                    "why": "pull %s inside constraint %s %s %s"
                                           % (d["name"], c["op"], s(c["value"]), c["unit"]),
                                    "constraint": c["id"]})
                    fixed["params"][name] = near
        elif v["rule"] == "quantity":
            for r in ctx["resources"]:
                if r["name"] in v["detail"] and r.get("qty") is not None:
                    for k in list(fixed["usages"].keys()):
                        if nkey(k) == r["key"]:
                            actions.append({"kind": "trim_usage", "target": r["name"],
                                            "from": num(fixed["usages"][k]), "to": r["qty"],
                                            "unit": r["unit"],
                                            "why": "usage exceeds stock; trimmed to the %s %s on hand"
                                                   % (s(r["qty"]), r["unit"])})
                            fixed["usages"][k] = r["qty"]
        elif v["rule"] == "budget":
            ar = arithmetic(ctx, fixed)
            if ar["per_run_cost"] and ar["total_cost"] and ctx["budget"]:
                reps = int(math.floor(ctx["budget"] / ar["per_run_cost"] + 1e-9))
                reps = max(1, reps)
                if reps < (fixed.get("samples") or 1):
                    actions.append({"kind": "reduce_replicates", "target": "replicates",
                                    "from": fixed.get("samples") or 1, "to": reps,
                                    "unit": "run",
                                    "why": "cut replicates to %d so total %s x %d <= budget %s"
                                           % (reps, s(ar["per_run_cost"]), reps, s(ctx["budget"]))})
                    fixed["samples"] = reps
        elif v["rule"] == "control":
            actions.append({"kind": "add_control", "target": "control arm",
                            "from": "absent", "to": "rule-derived reference arm",
                            "unit": "",
                            "why": "no control was declared; a reference arm is added and flagged for confirmation"})
    fixed["source"] = "material+revised" if plan.get("source") == "material" else "generated+revised"
    fixed["revision_actions"] = actions
    return fixed, actions


def plan_label(plan):
    if not plan["params"]:
        return "no inline parameter values"
    return ", ".join("%s=%s" % (k, s(v)) for k, v in sorted(plan["params"].items()))


def version_compare(ctx, results):
    rows = []
    for r in results:
        rows.append({
            "version": r["plan"]["version"],
            "source": r["plan"].get("source", "material"),
            "params": plan_label(r["plan"]),
            "per_run_cost": r["arith"]["per_run_cost"],
            "total_cost": r["arith"]["total_cost"],
            "duration_min": r["arith"]["duration_min"],
            "replicates": r["arith"]["replicates"],
            "hard_violations": len(r["validation"]["violations"]),
            "warnings": len(r["validation"]["warnings"]),
            "feasible": r["validation"]["ok"],
            "revised": bool(r.get("revision_actions")),
            "revision_count": len(r.get("revision_actions") or []),
            "locator": "%s/%s" % (r["plan"].get("material", ""), r["plan"].get("path", ""))})
    return rows


def pick_winner(rows, results):
    def key(row):
        r = next(x for x in results if x["plan"]["version"] == row["version"])
        cost = r["arith"]["total_cost"]
        cost = cost if cost is not None else float("inf")
        dur = r["arith"]["duration_min"] or float("inf")
        return (0 if row["feasible"] else 1, row["hard_violations"],
                row["revision_count"], cost, dur)
    if not rows:
        return None
    best = sorted(rows, key=key)[0]
    return best["version"]


def recommend(ctx, results, winner):
    r = next((x for x in results if x["plan"]["version"] == winner), None)
    if r is None:
        return {"status": "insufficient_evidence", "value": "no candidate plan could be scored",
                "basis": "no plan and no finite domain were supplied", "band": "n a",
                "source": "rule", "checks": []}
    dm = domain_map(ctx)
    band = []
    for k, v in r["plan"]["params"].items():
        d = resolve_param(dm, k)
        x = num(v)
        if d is None or x is None:
            continue
        band.append("%s %s +/-1 step (%s to %s)" % (d["name"], s(x),
                                                    s(max(d["min"], round(x - d["step"], 10))),
                                                    s(min(d["max"], round(x + d["step"], 10)))))
    ar = r["arith"]
    checks = ar["checks"]
    feasible = r["validation"]["ok"]
    basis = ("lowest per-run cost among feasible candidates"
             if feasible and ar["total_cost"] is not None else
             "fewest hard violations and shortest duration among feasible candidates"
             if feasible else
             "fewest hard violations; still needs the listed revisions before it can run")
    if r["plan"].get("source") == "generated":
        basis += "; values generated by rule from the declared finite domains"
    return {"status": "ok" if feasible else "needs_revision",
            "value": plan_label(r["plan"]) or "no inline parameter values",
            "version": winner, "source": r["plan"].get("source"),
            "basis": basis, "band": "; ".join(band) or "no finite domain to build a tolerance band from",
            "per_run_cost": ar["per_run_cost"], "total_cost": ar["total_cost"],
            "duration_min": ar["duration_min"], "replicates": ar["replicates"],
            "checks": checks,
            "all_checks_ok": all(c["ok"] and c.get("evaluated", True) for c in checks) if checks else False}


def status_of(ctx, results, winner_rec):
    if not ctx["domains"] and not ctx["plans"]:
        return "insufficient_evidence"
    if not any(r["validation"]["ok"] for r in results):
        return "partial"
    if ctx["degradations"] or (winner_rec and not winner_rec.get("all_checks_ok", True)):
        return "partial"
    return "answered"
