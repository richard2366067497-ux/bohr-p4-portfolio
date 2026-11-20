import csv, io, json, math, os, re

UNIT_ALIASES = {"c": "c", "celsius": "c", "°c": "c",
                "k": "k", "kelvin": "k", "min": "min", "m": "min",
                "h": "h", "hr": "h", "s": "s", "sec": "s", "ml": "ml",
                "l": "l", "g": "g", "kg": "kg", "mg": "mg",
                "mbar": "mbar", "bar": "bar", "kpa": "kpa", "mpa": "mpa",
                "rpm": "rpm", "v": "v", "a": "a", "%": "pct", "pct": "pct",
                "usd": "usd", "$": "usd", "cny": "cny", "rmb": "cny"}

CONV = {("min", "h"): 1 / 60.0, ("h", "min"): 60.0, ("min", "s"): 60.0,
        ("s", "min"): 1 / 60.0, ("h", "s"): 3600.0, ("s", "h"): 1 / 3600.0,
        ("ml", "l"): 0.001, ("l", "ml"): 1000.0, ("g", "kg"): 0.001,
        ("kg", "g"): 1000.0, ("g", "mg"): 1000.0, ("mg", "g"): 0.001,
        ("kpa", "mpa"): 0.001, ("mpa", "kpa"): 1000.0, ("bar", "mbar"): 1000.0,
        ("mbar", "bar"): 0.001}

PARAM_HINTS = ("temp", "温度", "time", "时间", "duration", "conc", "浓度",
               "ph", "ratio", "配比", "flow", "流量", "pressure", "压力",
               "voltage", "电压", "current", "电流", "power", "功率", "speed",
               "rpm", "转速", "dosage", "用量", "loading", "载量", "catalyst",
               "催化剂", "volume", "体积", "mass", "质量", "rate", "速率")

MAX_HINTS = ("yield", "产率", "purity", "纯度", "conversion", "转化率",
             "selectivity", "选择性", "recovery", "回收率", "activity", "活性",
             "score", "得分", "strength", "强度")

MIN_HINTS = ("cost", "成本", "price", "价格", "time", "耗时", "error", "误差",
             "impurity", "杂质", "waste", "浪费", "residual", "残留",
             "variance", "方差", "loss", "损耗", "risk", "风险")

NAME_KEYS = ("param", "parameter", "name", "key", "variable", "factor",
             "quantity", "indicator", "metric", "objective", "target", "item",
             "resource")


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


def unit_of(v):
    t = s(v).lower()
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


def name_of(d, parent_key):
    v = first_of(d, NAME_KEYS)
    return s(v) if v is not None else s(parent_key)


def direction_of(nm):
    t = nkey(nm)
    for h in MIN_HINTS:
        if nkey(h) and nkey(h) in t:
            return "min"
    return "max"


def looks_like_param(nm):
    t = nkey(nm)
    return any(nkey(h) in t for h in PARAM_HINTS)


def is_response(nm):
    t = nkey(nm)
    bad = ("cost", "成本", "price", "价格", "time", "时间", "duration", "耗时",
           "id", "version", "index", "run", "batch", "date", "year", "temp", "温度")
    return not any(nkey(b) in t for b in bad)


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
            mid = "M%02d" % idx
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
            paras = _paras(mid, text)
            mats.append({"id": mid, "name": fn,
                         "rel": os.path.relpath(full, input_dir).replace("\\", "/"),
                         "path": full, "text": text, "json": obj, "paras": paras,
                         "chars": len(text), "binary": binary,
                         "kind": "json" if obj is not None else ("text" if text else "binary")})
    return mats


def _paras(mid, text):
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
        for i, v in enumerate(o[:500]):
            walk(v, "%s[%d]" % (path, i), out, depth + 1)


HIST_KEYS = ("history", "records", "runs", "experiments", "trials", "data",
             "observations", "measurements", "dataset", "table", "past_runs",
             "历史", "数据")
DOMAIN_KEYS = ("parameter_domains", "domains", "parameter_space", "search_space",
               "parameters", "factors", "ranges", "domain", "参数范围")
CONSTRAINT_KEYS = ("constraints", "limits", "restrictions", "requirements",
                   "constraint", "bounds", "约束")
PLAN_KEYS = ("candidate_plans", "candidates", "plans", "versions", "proposals",
             "options", "方案")
RESOURCE_KEYS = ("resources", "prices", "price_list", "costs", "bookings",
                 "budget", "resource_contract", "contract", "资源")
OBJ_KEYS = ("objectives", "objective_specs", "goals", "targets", "indicators",
            "responses", "metrics")
NK = {k: nkey(k) for k in HIST_KEYS + DOMAIN_KEYS + CONSTRAINT_KEYS + PLAN_KEYS
      + RESOURCE_KEYS + OBJ_KEYS}


def _nk(k):
    return NK.get(k, nkey(k))


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
    if mn is None or mx is None or not nm:
        return
    step = num(first_of(d, ("step", "resolution", "increment", "granularity")))
    unit = s(first_of(d, ("unit", "units", "u"))) or unit_of(s(first_of(d, ("min", "max"))))
    _add_domain(store, nm, mn, mx, step, unit, mat, path, [nm])


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
            _add_domain(store, nm, mn, mx, None, unit_of(s(d.get(kmax))), mat, path, [kmin, kmax])


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


OP_MAP = {"le": "le", "<=": "le", "≤": "le", "lt": "lt", "<": "lt", "ge": "ge",
          ">=": "ge", "≥": "ge", "gt": "gt", ">": "gt", "eq": "eq", "==": "eq",
          "=": "eq", "ne": "ne", "!=": "ne", "mutex": "mutex", "exclude": "mutex"}


def _constrained(d, store, mat, path, known):
    if not isinstance(d, dict):
        return
    param = name_of(d, "")
    if not param:
        for k in ("field", "column", "applies_to", "on"):
            if isinstance(d.get(k), str):
                param = d[k]
                break
    op = None
    for k in ("op", "operator", "relation", "rel", "comparison", "type", "kind"):
        if k in d and s(d[k]).lower() in OP_MAP:
            op = OP_MAP[s(d[k]).lower()]
            break
    val = first_of(d, ("value", "limit", "threshold", "bound", "target", "v"))
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


MARKDOWN_OP = [
    (re.compile(r"(不得高于|不超过|上限|最高|≤|<=|低于或等于|no more than|at most|up to)"), "le"),
    (re.compile(r"(不得低于|下限|最低|≥|>=|高于或等于|no less than|at least|not below)"), "ge"),
    (re.compile(r"(小于|低于|less than|below)"), "lt"),
    (re.compile(r"(大于|高于|greater than|above|more than)"), "gt")]


def scan_text_constraints(mat, domains, store):
    text = mat.get("text", "")
    if not text:
        return
    for i, ln in enumerate(text.splitlines()):
        if not ln.strip():
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
        _add_constraint(store, target["name"], op, nums[0], unit_of(ln) or target.get("unit", ""),
                        mat, "p%d" % (i + 1), [ln.strip()[:40]],
                        note="prose rule: %s" % ln.strip()[:120])


def _collect_history(mat, obj, out):
    rows = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _nk(k) in [nkey(x) for x in HIST_KEYS] and isinstance(v, list):
                for i, r in enumerate(v):
                    if isinstance(r, dict):
                        rows.append((r, "$.%s[%d]" % (k, i)))
                    elif isinstance(r, list) and len(r) > 1:
                        rows.append(({("col%d" % j): c for j, c in enumerate(r)},
                                     "$.%s[%d]" % (k, i)))
    elif isinstance(obj, list):
        for i, r in enumerate(obj):
            if isinstance(r, dict):
                rows.append((r, "$[%d]" % i))
    if not rows:
        txt = mat.get("text", "")
        if txt and any(c in txt for c in (",", ";", "\t")):
            try:
                d = csv.Sniffer().sniff(txt[:2000]) if len(txt) > 40 else csv.excel
            except csv.Error:
                d = csv.excel
            try:
                rd = list(csv.reader(io.StringIO(txt), d))
            except (csv.Error, ValueError, TypeError):
                rd = []
            if len(rd) >= 2:
                head = [s(c) for c in rd[0]]
                for i, r in enumerate(rd[1:]):
                    if len(r) == len(head):
                        rows.append((dict(zip(head, r)), "row%d" % (i + 2)))
    for r, loc in rows:
        clean = {s(k): v for k, v in r.items()}
        out.append({"row": clean, "loc": loc, "mat": mat["id"], "bound": None})


def _dedupe(items, keys):
    seen, out = set(), []
    for it in items:
        k = tuple(s(it.get(x)) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _classify_resource(d, mat, path, ctx):
    if not isinstance(d, dict):
        return
    nm = name_of(d, "")
    price = num(first_of(d, ("unit_price", "price", "rate", "fee", "cost_per_unit",
                             "unit_cost", "price_per_unit", "cost")))
    qty = num(first_of(d, ("qty", "quantity", "amount", "volume", "mass", "usage",
                           "per_run", "per_sample", "consumption", "dose")))
    unit = s(first_of(d, ("unit", "units"))) or unit_of(s(first_of(d, ("price", "unit_price"))))
    booking = first_of(d, ("booked", "booking", "reserved", "available_until", "slot",
                           "schedule", "capacity"))
    if price is not None and nm:
        ctx["prices"].append({"key": nkey(nm), "name": nm, "price": price, "unit": unit,
                              "material": mat["id"], "path": path,
                              "evidence": ev(mat, path, [nm, s(price)])})
    if qty is not None and nm and not (price is not None and qty == price):
        ctx["usages"].append({"key": nkey(nm), "name": nm, "qty": qty, "unit": unit,
                              "material": mat["id"], "path": path,
                              "evidence": ev(mat, path, [nm, s(qty)])})
    if booking is not None and nm:
        ctx["bookings"].append({"key": nkey(nm), "name": nm, "value": s(booking),
                                "material": mat["id"], "path": path,
                                "evidence": ev(mat, path, [nm, s(booking)])})


def _is_plan(d):
    if not isinstance(d, dict):
        return False
    ks = [nkey(k) for k in d.keys()]
    has_v = any("version" in k or k in ("v", "plan", "candidate") for k in ks)
    has_p = any(k in ks for k in ("params", "parameters", "values", "settings"))
    return bool(has_v and (has_p or "recommended" in ks))


def _plan_record(d, mat, path):
    ver = s(first_of(d, ("version", "id", "name", "label", "v")))
    params = {}
    for k in ("params", "parameters", "values", "settings", "recommended"):
        v = d.get(k)
        if isinstance(v, dict):
            for kk, vv in v.items():
                params[s(kk)] = vv
    if not params:
        for kk, vv in d.items():
            if isinstance(vv, (int, float)) and not isinstance(vv, bool):
                params[s(kk)] = vv
    cost = num(first_of(d, ("cost", "total_cost", "price", "budget_used")))
    return {"version": ver or "v%d" % (len(params) + 1), "params": params,
            "params_sig": ",".join(sorted(nkey(k) for k in params)), "cost": cost,
            "material": mat["id"], "path": path,
            "evidence": ev(mat, path, [ver] if ver else list(params.keys())[:1])}


def _add_objective(ctx, item, mat, path):
    nm = name_of(item, "")
    if not nm:
        return
    d = s(first_of(item, ("direction", "sense", "goal", "optimize", "mode"))).lower()
    if d in ("min", "minimize", "lower", "minimise", "smaller"):
        d = "min"
    elif d in ("max", "maximize", "higher", "maximise", "larger"):
        d = "max"
    else:
        d = direction_of(nm)
    prio = num(first_of(item, ("priority", "weight", "rank")))
    ctx["objectives"].append({
        "id": "O%d" % (len(ctx["objectives"]) + 1), "name": nm,
        "unit": s(first_of(item, ("unit", "units"))), "direction": d,
        "priority": int(prio) if prio else len(ctx["objectives"]) + 1,
        "measurement": s(first_of(item, ("measurement", "method", "how"))) or "as reported in source",
        "tolerance": s(first_of(item, ("tolerance", "precision", "band"))) or "not specified",
        "evidence": [ev(mat, path, [nm])], "declared": True})


def _cols(ctx):
    cols = {}
    for h in ctx["history"]:
        for k, v in h["row"].items():
            if num(v) is not None:
                cols.setdefault(k, []).append(num(v))
    return cols


def _domains_from_history(ctx):
    if not ctx["history"]:
        return
    cols = _cols(ctx)
    cand = [(k, v) for k, v in cols.items()
            if looks_like_param(k) and len(set(round(x, 9) for x in v)) >= 2]
    if not cand:
        cand = [(k, v) for k, v in cols.items() if is_response(k)
                and len(set(round(x, 9) for x in v)) >= 3]
    mat = _mat_by_id(ctx, ctx["history"][0]["mat"])
    for k, vals in cand[:4]:
        mn, mx = min(vals), max(vals)
        if mx <= mn:
            continue
        uniq = sorted(set(vals))
        diffs = sorted({round(b - a, 9) for a, b in zip(uniq, uniq[1:]) if b - a > 1e-9})
        _add_domain(ctx["domains"], k, mn, mx, diffs[0] if diffs else (mx - mn) / 10.0,
                    unit_of(k), mat, "history", [k])
    ctx["notes"]["domains_from_history"] = True


def _objectives_from_columns(ctx):
    cols = _cols(ctx)
    declared = {nkey(d["name"]) for d in ctx["domains"]}
    mat = _mat_by_id(ctx, ctx["history"][0]["mat"]) if ctx["history"] else None
    for k, vals in cols.items():
        if nkey(k) in declared or not is_response(k) or len(set(vals)) < 2:
            continue
        ctx["objectives"].append({
            "id": "O%d" % (len(ctx["objectives"]) + 1), "name": s(k),
            "unit": unit_of(k), "direction": direction_of(k),
            "priority": len(ctx["objectives"]) + 1,
            "measurement": "measured value recorded in history table",
            "tolerance": "not specified",
            "evidence": [ev(mat, "history", [s(k)])] if mat else [], "declared": True})
        if len(ctx["objectives"]) >= 3:
            break


def _mat_by_id(ctx, mid):
    for m in ctx["materials"]:
        if m["id"] == mid:
            return m
    return {"id": mid, "text": "", "paras": []}


def _bind_columns(ctx):
    if not ctx["domains"] or not ctx["history"]:
        return
    dmap = {}
    for d in ctx["domains"]:
        dmap[d["key"]] = d["key"]
        dmap[nkey(d["name"])] = d["key"]

    def match(col):
        kk = nkey(col)
        if not kk:
            return None
        if kk in dmap:
            return dmap[kk]
        hits = {v for k, v in dmap.items() if len(k) >= 3 and (k in kk or kk in k)}
        return hits.pop() if len(hits) == 1 else None

    for h in ctx["history"]:
        row = {}
        for k, v in h["row"].items():
            m = match(k)
            if m is not None:
                row[m] = num(v)
        h["bound"] = row
        for o in ctx["objectives"]:
            on = nkey(o["name"])
            for k, v in h["row"].items():
                kk = nkey(k)
                if kk and (kk == on or on in kk or kk in on):
                    h.setdefault("resp", {})[o["name"]] = num(v)
                    break
    ctx["notes"]["bound_rows"] = sum(1 for h in ctx["history"] if h.get("bound"))


def extract(case, mats):
    ctx = {"case_id": s((case or {}).get("case_id")) or "unknown-case",
           "task_instruction": s((case or {}).get("task_instruction")
                                 or (case or {}).get("prompt")
                                 or (case or {}).get("instruction")),
           "contract": (case or {}).get("output_contract"), "_case": case,
           "materials": mats, "domains": [], "constraints": [], "history": [],
           "objectives": [], "prices": [], "usages": [], "budget": None,
           "budget_ev": [], "bookings": [], "candidates": [], "mutex": [],
           "degradations": [], "errors": [], "notes": {}}
    sources = []
    if case:
        sources.append({"mat": {"id": "CASE", "text": json.dumps(case, ensure_ascii=False,
                                                                 indent=1),
                                "paras": [{"locator": "CASE/p1"}]},
                        "obj": case, "path": "$"})
    for m in mats:
        sources.append({"mat": m, "obj": m.get("json"), "path": "$"})

    dk = [nkey(x) for x in DOMAIN_KEYS]
    for src in sources:
        obj = src["obj"]
        if obj is None:
            continue
        if isinstance(obj, dict):
            for key in obj:
                if nkey(key) in dk and isinstance(obj[key], list):
                    for i, item in enumerate(obj[key]):
                        if isinstance(item, dict):
                            _domain_from_dict(item, name_of(item, ""), ctx["domains"],
                                              src["mat"], "%s.%s[%d]" % (src["path"], key, i))
                elif nkey(key) in dk and isinstance(obj[key], dict):
                    for nm, sub in obj[key].items():
                        _domain_from_dict(sub, nm, ctx["domains"], src["mat"],
                                          "%s.%s.%s" % (src["path"], key, nm))
        pairs = []
        walk(obj, src["path"], pairs)
        for path, d in pairs:
            _domain_from_dict(d, "", ctx["domains"], src["mat"], path)
        for path, d in pairs:
            _pair_domains(d, ctx["domains"], src["mat"], path)
    ctx["domains"] = _dedupe(ctx["domains"], ["key"])
    known = [d["key"] for d in ctx["domains"]]

    ck = [nkey(x) for x in CONSTRAINT_KEYS]
    for src in sources:
        obj = src["obj"]
        if obj is None:
            continue
        if isinstance(obj, dict):
            for key in obj:
                if nkey(key) in ck and isinstance(obj[key], list):
                    for i, item in enumerate(obj[key]):
                        _constrained(item, ctx["constraints"], src["mat"],
                                     "%s.%s[%d]" % (src["path"], key, i), known)
        pairs = []
        walk(obj, src["path"], pairs)
        for path, d in pairs:
            _constrained(d, ctx["constraints"], src["mat"], path, known)
        for path, d in pairs:
            _keyed_constraints(d, ctx["constraints"], src["mat"], path, known)
        for path, d in pairs:
            for k, v in d.items():
                if nkey(k) in ("budget", "maxcost", "costcap", "costlimit", "budgetusd"):
                    bv = num(v)
                    if bv is not None and ctx["budget"] is None:
                        ctx["budget"] = bv
                        ctx["budget_ev"].append(ev(src["mat"], path + "." + s(k), [s(k), s(v)]))
    for m in mats:
        scan_text_constraints(m, ctx["domains"], ctx["constraints"])
    ctx["constraints"] = [dict(c, id="C%02d" % (i + 1)) for i, c in
                          enumerate(_dedupe(ctx["constraints"], ["key", "op", "value"]))]
    ctx["mutex"] = [c for c in ctx["constraints"] if c["type"] == "mutex"]

    for m in mats:
        if m.get("json") is not None:
            _collect_history(m, m["json"], ctx["history"])
    ctx["history"] = ctx["history"][:300]

    rk = [nkey(x) for x in RESOURCE_KEYS]
    pk = [nkey(x) for x in PLAN_KEYS]
    for src in sources:
        obj = src["obj"]
        if obj is None:
            continue
        if isinstance(obj, dict):
            for key in obj:
                if (nkey(key) in rk or nkey(key) in pk) and isinstance(obj[key], list):
                    for i, item in enumerate(obj[key]):
                        if not isinstance(item, dict):
                            continue
                        path = "%s.%s[%d]" % (src["path"], key, i)
                        _classify_resource(item, src["mat"], path, ctx)
                        if nkey(key) in pk:
                            ctx["candidates"].append(_plan_record(item, src["mat"], path))
        pairs = []
        walk(obj, src["path"], pairs)
        for path, d in pairs:
            _classify_resource(d, src["mat"], path, ctx)
            if _is_plan(d):
                ctx["candidates"].append(_plan_record(d, src["mat"], path))
    ctx["prices"] = _dedupe(ctx["prices"], ["key", "price"])
    ctx["usages"] = _dedupe(ctx["usages"], ["key", "qty"])
    ctx["candidates"] = _dedupe(ctx["candidates"], ["version", "params_sig"])[:12]

    ok = [nkey(x) for x in OBJ_KEYS]
    for src in sources:
        obj = src["obj"]
        if obj is None:
            continue
        if isinstance(obj, dict):
            for key in obj:
                if nkey(key) in ok and isinstance(obj[key], list):
                    for i, item in enumerate(obj[key]):
                        if isinstance(item, dict):
                            _add_objective(ctx, item, src["mat"],
                                           "%s.%s[%d]" % (src["path"], key, i))

    if not ctx["domains"]:
        _domains_from_history(ctx)
    if not ctx["objectives"]:
        _objectives_from_columns(ctx)
    if not ctx["objectives"]:
        ctx["objectives"].append({
            "id": "O1", "name": "primary_response", "unit": "unspecified",
            "direction": "max", "priority": 1,
            "measurement": "not specified in supplied material",
            "tolerance": "not specified", "evidence": [], "declared": False})
        ctx["degradations"].append(
            "No response indicator declared in the material; a named stand-in objective is "
            "used and no numeric prediction is claimed.")
    _bind_columns(ctx)

    if not ctx["domains"]:
        ctx["degradations"].append(
            "No finite parameter domain (min max step) found; grid search, response model "
            "and cost ledger are reported absent with the searched locations listed.")
    if not ctx["history"]:
        ctx["degradations"].append(
            "No run history table supplied; the ranking uses a labelled constraint-margin "
            "design rule, not a fitted response.")
    if ctx["budget"] is None:
        ctx["degradations"].append(
            "No budget ceiling supplied; per-trial cost uses the price and usage formula "
            "and affordability is left open.")
    return ctx
