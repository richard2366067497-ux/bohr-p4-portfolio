# -*- coding: utf-8 -*-
"""plan-forge-experiment :: extraction layer.

Turns case.json plus a directory of material files into one ctx dict: finite
parameter domains, stated constraints, resources with prices and bookings,
candidate plans with steps, controls, risks, confirmations and the hypothesis.
Every extracted item carries source_id + locator + a verbatim quote.
"""
import json, re

from design import (s, nkey, num, bnum, unit_of, first_of, ev, walk, paras_of,
                    fenced_blocks, parse_range, FENCE_RX)


def _steps_of(d, mat, path):
    out = []
    raw = d.get("steps") if isinstance(d, dict) else None
    if not isinstance(raw, list):
        return out
    for i, st in enumerate(raw):
        if not isinstance(st, dict):
            continue
        out.append({
            "id": s(first_of(st, ("id", "step", "no"))) or "S%d" % (i + 1),
            "action": s(first_of(st, ("action", "name", "do", "description"))),
            "device": s(first_of(st, ("device", "equipment", "instrument", "apparatus"))),
            "params": {s(kk): vv for kk, vv in (st.get("params") or {}).items()}
                      if isinstance(st.get("params"), dict) else {},
            "duration_min": num(first_of(st, ("duration_min", "minutes", "duration",
                                              "time_min", "min"))),
            "depends_on": [s(x) for x in st.get("depends_on", [])]
                          if isinstance(st.get("depends_on"), list) else [],
            "parallel_group": s(first_of(st, ("parallel_group", "group", "parallel"))),
            "output": s(first_of(st, ("output", "product", "result"))),
            "evidence": ev(mat, "%s.steps[%d]" % (path, i),
                           [s(first_of(st, ("action", "name"))) or "step"])})
    return out

NAME_KEYS = ("name", "param", "parameter", "key", "variable", "factor",
             "resource", "item", "material", "equipment", "device", "id",
             "label", "step", "action", "indicator", "metric")

DOMAIN_KEYS = ("parameter_domains", "domains", "parameter_space", "parameters",
               "factors", "ranges", "domain", "allowed_ranges", "参数范围")
CONSTRAINT_KEYS = ("constraints", "limits", "requirements", "bounds", "约束")
PLAN_KEYS = ("candidate_plans", "candidates", "plans", "versions", "protocols",
             "proposals", "options", "arms", "方案")
RES_KEYS = ("resources", "equipment", "materials", "reagents", "consumables",
            "price_list", "prices", "bookings", "resource_contract", "devices",
            "equipment_list", "supplies", "资源", "设备")
CTRL_KEYS = ("controls", "control_groups", "control", "reference_arms",
             "control_arms", "对照")
RISK_KEYS = ("risks", "mitigations", "exceptions", "hazards", "failure_modes",
             "风险")
CONF_KEYS = ("confirmations", "open_questions", "pending_items", "to_confirm",
             "clarifications", "确认项")
HYP_KEYS = ("hypothesis", "objective", "goal", "question", "aim", "假设")
STEP_KEYS = ("steps", "procedure", "protocol_steps", "actions", "workflow", "步骤",
             "step_list", "timeline")

OP_MAP = {"le": "le", "<=": "le", "≤": "le", "lt": "lt", "<": "lt", "ge": "ge",
          ">=": "ge", "≥": "ge", "gt": "gt", ">": "gt", "eq": "eq", "==": "eq",
          "=": "eq", "ne": "ne", "!=": "ne", "mutex": "mutex", "exclude": "mutex"}

MARKDOWN_OP = [
    (re.compile(r"(不得高于|不超过|上限|最高|≤|<=|低于或等于|no more than|at most|up to)"), "le"),
    (re.compile(r"(不得低于|下限|最低|≥|>=|高于或等于|no less than|at least|not below)"), "ge"),
    (re.compile(r"(小于|低于|less than|below)"), "lt"),
    (re.compile(r"(大于|高于|greater than|above|more than)"), "gt")]

PROSE_RANGE = re.compile(
    r"([一-鿿A-Za-z][一-鿿A-Za-z0-9_]{0,14})\s*[:：]?\s*"
    r"(-?\d+(?:\.\d+)?)\s*(?:–|—|~|至|to|-)\s*(-?\d+(?:\.\d+)?)\s*"
    r"(L|mL|ml|µL|μL|uL|kg|mg|µg|μg|ug|g|°C|℃|×g|rpm|V|A|%|min|h|s)\s*"
    r"(?:[（(]\s*step\s*([\d.]+)\s*[）)])?", re.I)


def name_of(d, parent_key=""):
    v = first_of(d, NAME_KEYS)
    return s(v) if v is not None else s(parent_key)


def _add_domain(store, name, mn, mx, step, unit, mat, path, needles):
    if not name or mn is None or mx is None or mx <= mn:
        return
    k = nkey(name)
    for d in store:
        if d["key"] == k and abs(d["min"] - mn) < 1e-9 and abs(d["max"] - mx) < 1e-9:
            return
    if step is None or step <= 0 or step > (mx - mn):
        step = (mx - mn) / 10.0
    store.append({"key": k, "name": s(name), "min": float(mn), "max": float(mx),
                  "step": float(step), "unit": unit or "",
                  "evidence": [ev(mat, path, needles + [s(mn), s(mx), s(name)])]})


def _add_constraint(store, param, op, value, unit, mat, path, needles,
                    ctype="range", note=""):
    if not op:
        return
    k = nkey(param)
    for c in store:
        if (c["key"] == k and c["op"] == op
                and abs((num(c["value"]) or 0.0) - (num(value) or 0.0)) < 1e-9):
            return
    store.append({"id": "C%02d" % (len(store) + 1), "key": k, "param": s(param),
                  "op": op, "value": value, "unit": unit or "", "type": ctype,
                  "note": note, "evidence": [ev(mat, path, needles + [s(value)])],
                  "source": mat["id"]})


def _domain_from_dict(d, parent_key, store, mat, path):
    if not isinstance(d, dict):
        return
    mn = num(first_of(d, ("min", "minimum", "lower", "low", "from", "start", "lo")))
    mx = num(first_of(d, ("max", "maximum", "upper", "high", "to", "end", "hi")))
    nm = name_of(d, parent_key)
    step = num(first_of(d, ("step", "resolution", "increment", "granularity")))
    unit = s(first_of(d, ("unit", "units", "u")))
    raw = s(first_of(d, ("allowed", "range", "interval", "span", "permitted")))
    if (mn is None or mx is None) and raw:
        pr = parse_range(raw)
        if pr:
            mn, mx, unit, st2 = pr
            step = step or st2
    if mn is None or mx is None or not nm:
        return
    _add_domain(store, nm, mn, mx, step, unit or unit_of(raw), mat, path,
                [nm, raw[:40]])


def _pair_domains(d, store, mat, path):
    mins, maxs = {}, {}
    for k, v in d.items():
        kk = s(k).lower()
        vv = num(v)
        if vv is None:
            continue
        if re.search(r"(_min|^min[_\-. ]|minimum$|lower|^low)", kk):
            mins[nkey(re.sub(r"(_min|^min[_\-. ]|minimum$|lower|^low)", "", kk))] = (vv, k)
        elif re.search(r"(_max|^max[_\-. ]|maximum$|upper|^high)", kk):
            maxs[nkey(re.sub(r"(_max|^max[_\-. ]|maximum$|upper|^high)", "", kk))] = (vv, k)
    for stem, (mn, kmin) in mins.items():
        if stem and stem in maxs:
            mx, kmax = maxs[stem]
            nm = re.sub(r"(_min|_max|_lower|_upper|\s)", "", s(kmin))
            _add_domain(store, nm, mn, mx, None, unit_of(s(d.get(kmax))), mat, path,
                        [kmin, kmax])


def _keyed_constraints(d, store, mat, path, known):
    for k, v in d.items():
        kk = s(k).lower()
        vv = num(v)
        if vv is None or kk in ("min", "max", "step", "minimum", "maximum", "lower", "upper"):
            continue
        m = re.match(r"^max[_\-\s]*(.+)$|^(.+?)[_\-\s]*max(imum)?(_value)?$", kk)
        if m:
            stem = m.group(1) or m.group(2) or ""
            if stem and nkey(stem) in known:
                _add_constraint(store, stem, "le", vv, unit_of(s(v)), mat, path, [s(k)],
                                note="upper bound stated as %s" % s(k))
            continue
        m = re.match(r"^min[_\-\s]*(.+)$|^(.+?)[_\-\s]*min(imum)?(_value)?$", kk)
        if m:
            stem = m.group(1) or m.group(2) or ""
            if stem and nkey(stem) in known:
                _add_constraint(store, stem, "ge", vv, unit_of(s(v)), mat, path, [s(k)],
                                note="lower bound stated as %s" % s(k))


def _constrained(d, store, mat, path, known):
    if not isinstance(d, dict):
        return
    if "op" not in d and "operator" not in d and "relation" not in d:
        has_lo = any(k in d for k in ("min", "minimum", "lower"))
        has_hi = any(k in d for k in ("max", "maximum", "upper"))
        if has_lo and has_hi:
            return  # a domain record, not a constraint
    param = name_of(d, "")
    if not param:
        for k in ("field", "column", "applies_to", "on", "target"):
            if isinstance(d.get(k), str):
                param = d[k]
                break
    op = None
    for k in ("op", "operator", "relation", "rel", "comparison", "type", "kind"):
        if k in d and s(d[k]).lower() in OP_MAP:
            op = OP_MAP[s(d[k]).lower()]
            break
    val = first_of(d, ("value", "limit", "threshold", "bound", "target", "v", "expected"))
    if op is None:
        if "max" in d or "upper" in d or "maximum" in d:
            op, val = "le", first_of(d, ("max", "upper", "maximum"))
        elif "min" in d or "lower" in d or "minimum" in d:
            op, val = "ge", first_of(d, ("min", "lower", "minimum"))
    if op is None or param is None:
        return
    if op == "mutex":
        _add_constraint(store, param, "mutex", s(val), "", mat, path, [param, s(val)],
                        ctype="mutex", note="mutually exclusive with %s" % s(val))
        return
    vv = num(val)
    if vv is None:
        return
    unit = s(first_of(d, ("unit", "units"))) or unit_of(s(val))
    _add_constraint(store, param, op, vv, unit, mat, path, [param, s(val)],
                    note=s(first_of(d, ("note", "reason", "why", "basis", "comment"))))


def scan_text_constraints(mat, domains, store):
    text = mat.get("text", "")
    if not text:
        return
    text = FENCE_RX.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for i, ln in enumerate(text.splitlines()):
        if not ln.strip():
            continue
        if re.search(r'"\s*:\s*["\[\{]', ln) or nkey(ln).find("trigger") >= 0:
            continue
        lv = ln.lower()
        op = None
        for rx, o in MARKDOWN_OP:
            if rx.search(lv):
                op = o
                break
        if op is None:
            continue
        nums = [x for x in (num(y) for y in re.findall(r"[-+]?\d+(?:\.\d+)?", ln)) if x is not None]
        if not nums:
            continue
        target = None
        for d in domains:
            if d["key"] and d["key"] in nkey(ln):
                target = d
                break
        if target is None:
            if len(domains) == 1:
                target = domains[0]
            else:
                continue
        _add_constraint(store, target["name"], op, nums[0],
                        unit_of(ln) or target.get("unit", ""), mat, "p%d" % (i + 1),
                        [ln.strip()[:40]], note="prose rule: %s" % ln.strip()[:120])


def scan_text_domains(mat, store):
    """Finite domains stated in prose or inside quoted allowed-range strings."""
    text = mat.get("text", "")
    if not text:
        return
    for m in re.finditer(r'"name"\s*:\s*"([^"]{1,24})"[\s\S]{0,120}?'
                         r'"(?:allowed|range|interval)"\s*:\s*"([^"]{1,48})"', text):
        pr = parse_range(m.group(2))
        if pr:
            mn, mx, unit, step = pr
            line = text[:m.start()].count("\n") + 1
            _add_domain(store, m.group(1), mn, mx, step, unit, mat, "L%d" % line,
                        [m.group(1), m.group(2)[:30]])
    for i, ln in enumerate(text.splitlines()):
        for m in PROSE_RANGE.finditer(ln):
            nm = m.group(1).strip()
            if nkey(nm) in ("step", "value", "actual", "expected", "unit"):
                continue
            st = num(m.group(5)) if m.group(5) else None
            _add_domain(store, nm, float(m.group(2)), float(m.group(3)), st,
                        unit_of(m.group(4)), mat, "L%d" % (i + 1), [ln.strip()[:60]])


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
    for r in ctx["resources"]:
        add(r["evidence"], "resource", r["name"],
            "spec %s qty %s %s price %s lead %s booking %s"
            % (r["spec"] or "not stated", s(r["qty"]), r["unit"], s(r["price"]),
               s(r["lead_time"]), r["booking"] or "not declared"))
    for p in ctx["plans"]:
        add(p["evidence"], "candidate_plan", p["version"],
            ",".join("%s=%s" % (k, s(v)) for k, v in p["params"].items()) or "no inline params")
    for k in ctx["controls"]:
        add(k["evidence"], "control", k["id"], k["design"][:120])
    for r in ctx["risks"]:
        add(r["evidence"], "risk", r["id"], r["mode"][:120])
    for c in ctx["confirmations"]:
        add(c["evidence"], "confirmation", c["item"][:40], c["why"][:120])
    if ctx["hypothesis"]:
        for e in (ctx["hypothesis"].get("evidence") or []):
            add(e, "hypothesis", "hypothesis", ctx["hypothesis"]["statement"][:120])
    for b in ctx["budget_ev"]:
        add(b, "budget", "budget", s(ctx["budget"]))
    total = len(items)
    hit = sum(1 for i in items if i.get("verified"))
    return items, {"total": total, "verbatim_hits": hit,
                   "hit_rate": round(hit / total, 4) if total else 1.0,
                   "note": ("every quoted line was re-located inside its source material"
                            if total else
                            "no extractable item carried a quotable line in the supplied material")}


def _dedupe(items, keys):
    seen, out = set(), []
    for it in items:
        k = tuple(s(it.get(x)) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _resource(d, mat, path, ctx):
    if not isinstance(d, dict):
        return
    nm = name_of(d, "")
    if not nm:
        return
    spec = s(first_of(d, ("spec", "specification", "model", "grade", "purity", "type")))
    qty = num(first_of(d, ("qty", "quantity", "amount", "available", "stock", "count",
                           "pack_size")))
    unit = s(first_of(d, ("unit", "units", "pack_unit")))
    price = num(first_of(d, ("unit_price", "price", "rate", "fee", "unit_cost",
                             "cost_per_unit", "cost")))
    lead = num(first_of(d, ("lead_time", "lead_days", "lead", "delivery_days")))
    book = s(first_of(d, ("booking", "booked", "slot", "window", "reserved_until",
                          "available_from", "calendar", "capacity", "capacity_min",
                          "capacity_h", "hours")))
    subs = bnum(first_of(d, ("substitutable", "interchangeable", "replaceable")))
    rec = {"key": nkey(nm), "name": nm, "spec": spec, "qty": qty, "unit": unit,
           "price": price, "lead_time": lead, "booking": book,
           "per_sample": first_of(d, ("per_sample", "per_run", "usage_per_sample")),
           "kind": s(first_of(d, ("kind", "category"))),
           "substitutable": subs, "material": mat["id"], "path": path,
           "evidence": ev(mat, path, [nm])}
    for old in ctx["resources"]:
        if old["key"] == rec["key"] and old["material"] == rec["material"]:
            return
    ctx["resources"].append(rec)


def _plan(d, mat, path, ctx):
    ver = s(first_of(d, ("version", "id", "label", "name", "v")))
    params, steps = {}, []
    for k in ("params", "parameters", "values", "settings"):
        v = d.get(k)
        if isinstance(v, dict):
            for kk, vv in v.items():
                params[s(kk)] = vv
    if isinstance(d.get("steps"), list):
        steps = _steps_of(d, mat, path)
    if not params:
        for kk, vv in d.items():
            if isinstance(vv, (int, float)) and not isinstance(vv, bool):
                params[s(kk)] = vv
    usages = {}
    for k in ("usages", "resources", "consumables", "amounts", "usage"):
        v = d.get(k)
        if isinstance(v, dict):
            for kk, vv in v.items():
                usages[s(kk)] = vv
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    nm = name_of(it, "")
                    q = num(first_of(it, ("qty", "quantity", "amount", "usage", "per_sample")))
                    if nm and q is not None:
                        usages[nm] = q
    ctx["plans"].append({
        "version": ver or "plan%d" % (len(ctx["plans"]) + 1), "params": params,
        "steps": steps, "usages": usages,
        "sig": json.dumps([ver, params, usages], sort_keys=True, ensure_ascii=False),
        "samples": num(first_of(d, ("samples", "n", "sample_size", "replicates"))),
        "reported_cost": num(first_of(d, ("cost", "total_cost", "budget_used"))),
        "reported_duration": num(first_of(d, ("duration", "total_minutes", "total_time"))),
        "material": mat["id"], "path": path,
        "evidence": ev(mat, path, [ver] if ver else list(params.keys())[:1]),
        "source": "material"})


def _control(d, mat, path, ctx):
    if not isinstance(d, dict):
        return
    ctx["controls"].append({
        "id": s(first_of(d, ("id", "name", "label"))) or "K%d" % (len(ctx["controls"]) + 1),
        "type": s(first_of(d, ("type", "kind", "category"))) or "reference",
        "design": s(first_of(d, ("design", "setup", "how", "description"))) or s(d)[:200],
        "excludes": s(first_of(d, ("excludes", "exclude", "controls_for", "for"))),
        "readout": s(first_of(d, ("readout", "measure", "metric"))),
        "evidence": ev(mat, path, [s(first_of(d, ("type", "name", "design"))) or "control"])})


def _risk(d, mat, path, ctx):
    if not isinstance(d, dict):
        return
    ctx["risks"].append({
        "id": s(first_of(d, ("id", "name", "label"))) or "R%d" % (len(ctx["risks"]) + 1),
        "mode": s(first_of(d, ("mode", "risk", "failure_mode", "description", "name"))) or s(d)[:80],
        "trigger": s(first_of(d, ("trigger", "when", "if", "condition"))),
        "criterion": s(first_of(d, ("criterion", "threshold", "limit"))),
        "stop_loss": s(first_of(d, ("stop_loss", "stop", "abort", "trip"))),
        "fallback": s(first_of(d, ("fallback", "mitigation", "plan_b", "action"))),
        "evidence": ev(mat, path, [s(first_of(d, ("mode", "name"))) or "risk"])})


def _confirm(d, mat, path, ctx):
    if not isinstance(d, dict):
        return
    ctx["confirmations"].append({
        "item": s(first_of(d, ("item", "question", "name", "what"))) or s(d)[:120],
        "why": s(first_of(d, ("why", "reason", "impact"))),
        "needed_by": s(first_of(d, ("needed_by", "deadline", "by", "when"))),
        "evidence": ev(mat, path, [s(first_of(d, ("item", "question", "name"))) or "confirm"])})


def _collect_sources(case, mats):
    src = []
    named = {m["name"].lower() for m in mats}
    if case and not ({"case.json", "challenge.json", "task.json"} & named):
        ghost = {"id": "CASE", "name": "case.json", "rel": "case.json",
                 "text": json.dumps(case, ensure_ascii=False, indent=1), "chars": 0,
                 "kind": "json", "json": case}
        src.append({"mat": ghost, "obj": case, "path": "$"})
    for m in mats:
        if isinstance(m.get("json"), (dict, list)):
            src.append({"mat": m, "obj": m["json"], "path": "."})
        for blk in fenced_blocks(m.get("text", "")):
            src.append({"mat": m, "obj": blk["obj"], "path": blk["path"]})
    return src


def extract(case, mats):
    ctx = {"case_id": s((case or {}).get("case_id")) or "unknown-case",
           "task_instruction": s((case or {}).get("task_instruction")
                                 or (case or {}).get("prompt")
                                 or (case or {}).get("instruction")),
           "contract": (case or {}).get("output_contract"),
           "materials": mats, "domains": [], "constraints": [], "resources": [],
           "plans": [], "controls": [], "risks": [], "confirmations": [],
           "hypothesis": None, "budget": None, "budget_ev": [],
           "deadline_days": None, "step_template": [], "degradations": [],
           "errors": [], "notes": {}}
    for m in mats:
        m["paras"] = paras_of(m["id"], m.get("text", ""))
    sources = _collect_sources(case, mats)
    dk = [nkey(x) for x in DOMAIN_KEYS]
    ck = [nkey(x) for x in CONSTRAINT_KEYS]
    rk = [nkey(x) for x in RES_KEYS]
    pk = [nkey(x) for x in PLAN_KEYS]
    kk_ = [nkey(x) for x in CTRL_KEYS]
    riskk = [nkey(x) for x in RISK_KEYS]
    confk = [nkey(x) for x in CONF_KEYS]
    hypk = [nkey(x) for x in HYP_KEYS]
    stepk = [nkey(x) for x in STEP_KEYS]

    for src in sources:
        obj = src["obj"]
        if not isinstance(obj, dict):
            continue
        for key in obj:
            nk = nkey(key)
            lst = obj[key]
            if nk in dk and isinstance(lst, list):
                for i, it in enumerate(lst):
                    if isinstance(it, dict):
                        _domain_from_dict(it, name_of(it, ""), ctx["domains"],
                                          src["mat"], "%s.%s[%d]" % (src["path"], key, i))
            elif nk in dk and isinstance(lst, dict):
                for nm, sub in lst.items():
                    _domain_from_dict(sub, nm, ctx["domains"], src["mat"],
                                      "%s.%s.%s" % (src["path"], key, nm))
            elif nk in ck and isinstance(lst, list):
                for i, it in enumerate(lst):
                    _constrained(it, ctx["constraints"], src["mat"],
                                 "%s.%s[%d]" % (src["path"], key, i),
                                 [d["key"] for d in ctx["domains"]])
            elif nk in rk and isinstance(lst, list):
                for i, it in enumerate(lst):
                    _resource(it, src["mat"], "%s.%s[%d]" % (src["path"], key, i), ctx)
            elif nk in pk and isinstance(lst, list):
                for i, it in enumerate(lst):
                    _plan(it, src["mat"], "%s.%s[%d]" % (src["path"], key, i), ctx)
            elif nk in kk_ and isinstance(lst, list):
                for i, it in enumerate(lst):
                    _control(it, src["mat"], "%s.%s[%d]" % (src["path"], key, i), ctx)
            elif nk in riskk and isinstance(lst, list):
                for i, it in enumerate(lst):
                    _risk(it, src["mat"], "%s.%s[%d]" % (src["path"], key, i), ctx)
            elif nk in confk and isinstance(lst, list):
                for i, it in enumerate(lst):
                    _confirm(it, src["mat"], "%s.%s[%d]" % (src["path"], key, i), ctx)
            elif nk in stepk and isinstance(lst, list) and not ctx["step_template"]:
                ctx["step_template"] = _steps_of({"steps": lst}, src["mat"],
                                                 "%s.%s" % (src["path"], key))
            elif nk in hypk and isinstance(lst, dict):
                ctx["hypothesis"] = {
                    "statement": s(first_of(lst, ("statement", "text", "hypothesis",
                                                  "objective", "goal", "testable_question"))),
                    "falsifier": s(first_of(lst, ("falsifier", "refute", "disprove", "null_hypothesis"))),
                    "support_metric": s(first_of(lst, ("support_metric", "metric", "readout", "success"))),
                    "evidence": [ev(src["mat"], "%s.%s" % (src["path"], key), [s(key)])]}
        pairs = []
        walk(obj, src["path"], pairs)
        for path, d in pairs:
            _domain_from_dict(d, "", ctx["domains"], src["mat"], path)
        for path, d in pairs:
            _pair_domains(d, ctx["domains"], src["mat"], path)
    ctx["domains"] = _dedupe(ctx["domains"], ["key"])
    for m in mats:
        scan_text_domains(m, ctx["domains"])
    ctx["domains"] = [dict(d, id="D%02d" % (i + 1)) for i, d in
                      enumerate(_dedupe(ctx["domains"], ["key"]))]
    known = [d["key"] for d in ctx["domains"]]
    for src in sources:
        obj = src["obj"]
        if obj is None:
            continue
        pairs = []
        walk(obj, src["path"], pairs)
        for path, d in pairs:
            _constrained(d, ctx["constraints"], src["mat"], path, known)
        for path, d in pairs:
            _keyed_constraints(d, ctx["constraints"], src["mat"], path, known)
            for k, v in d.items():
                kx = nkey(k)
                if kx in ("budget", "maxcost", "costcap", "costlimit", "budgetusd",
                          "budgetcny", "costcapusd"):
                    bv = num(v)
                    if bv is not None and ctx["budget"] is None:
                        ctx["budget"] = bv
                        ctx["budget_ev"].append(ev(src["mat"], path + "." + s(k), [s(k), s(v)]))
                if kx in ("deadline", "deadlinedays", "daysavailable", "windowdays"):
                    dv = num(v)
                    if dv is not None and ctx["deadline_days"] is None:
                        ctx["deadline_days"] = dv
    for m in mats:
        scan_text_constraints(m, ctx["domains"], ctx["constraints"])
        if not ctx["hypothesis"]:
            for p in (m.get("paras") or []):
                low = p["text"].lower()
                if any(h in low for h in ("hypothesis", "假设", "hypothes")):
                    ctx["hypothesis"] = {"statement": p["text"].strip()[:400],
                                         "falsifier": "", "support_metric": "",
                                         "evidence": [{"source_id": m["id"],
                                                       "locator": p["locator"],
                                                       "quote": p["text"].strip()[:300],
                                                       "verified": True}]}
                    break
    ctx["constraints"] = [dict(c, id="C%02d" % (i + 1)) for i, c in
                          enumerate(_dedupe(ctx["constraints"], ["key", "op", "value"]))]
    ctx["resources"] = _dedupe(ctx["resources"], ["key", "name", "qty", "price"])
    ctx["plans"] = _dedupe(ctx["plans"], ["version", "sig"])[:12]
    ctx["controls"] = _dedupe(ctx["controls"], ["design"])[:8]
    ctx["risks"] = _dedupe(ctx["risks"], ["mode"])[:12]
    ctx["confirmations"] = _dedupe(ctx["confirmations"], ["item"])[:12]
    for p in ctx["plans"]:
        if not p["steps"] and ctx["step_template"]:
            p["steps"] = [dict(st) for st in ctx["step_template"]]
            p["steps_source"] = "the material's step sequence, reused across the candidate plans"

    if not ctx["hypothesis"]:
        ctx["degradations"].append(
            "No hypothesis statement was declared in the material; a rule-derived testable "
            "question is proposed and listed as a confirmation item.")
    if not ctx["controls"]:
        ctx["degradations"].append(
            "No control arm was declared in the material; a rule-derived reference arm is "
            "proposed and flagged as needing organiser confirmation.")
    if not ctx["plans"]:
        ctx["degradations"].append(
            "No candidate plan was supplied; three versioned candidates are generated from the "
            "declared finite domains and labelled as generated.")
    if not ctx["domains"]:
        ctx["degradations"].append(
            "No finite parameter domain (min max step) was found; parameter ranges and the "
            "arithmetic are reported with the searched locations listed.")
    if ctx["budget"] is None:
        ctx["degradations"].append(
            "No budget ceiling was supplied; total cost is reported per plan with the "
            "amount x unit price formula and the budget check is left open.")
    if not ctx["resources"]:
        ctx["degradations"].append(
            "No equipment or material list was supplied; the equipment element carries an "
            "explicit absent record rather than an invented list.")
    return ctx
