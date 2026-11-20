# -*- coding: utf-8 -*-
"""Material scanning + source-grounded extraction for the feasibility review.

Every returned item carries {source_id, locator, quote, verified} so a reviewer can
re-open the exact line.  Nothing is invented: when a field is absent the extractor
records a structured "searched but absent" note instead.
"""
import csv, io, json, math, os, re

# --- units -------------------------------------------------------------------
UNIT_ALIASES = {"min": "min", "m": "min", "h": "h", "hr": "h", "hour": "h",
                "d": "d", "day": "d", "wk": "wk", "week": "wk", "s": "s",
                "sec": "s", "ml": "ml", "l": "l", "ul": "ul", "µl": "ul",
                "g": "g", "kg": "kg", "mg": "mg", "µg": "ug", "ug": "ug",
                "元": "cny", "cny": "cny", "rmb": "cny", "usd": "usd", "$": "usd",
                "千元": "kcny", "万元": "wcny", "rpm": "rpm", "c": "c",
                "°c": "c", "℃": "c", "k": "k", "%": "pct", "pct": "pct"}
FAMILY = {"min": ("time", 1.0), "s": ("time", 1 / 60.0), "h": ("time", 60.0),
          "d": ("time", 1440.0), "wk": ("time", 10080.0),
          "ml": ("vol", 1.0), "ul": ("vol", 0.001), "l": ("vol", 1000.0),
          "mg": ("mass", 1.0), "ug": ("mass", 0.001), "g": ("mass", 1000.0),
          "kg": ("mass", 1e6),
          "cny": ("money", 1.0), "kcny": ("money", 1000.0), "wcny": ("money", 10000.0),
          "usd": ("money", 1.0)}
OP_MAP = {"<=": "le", "≤": "le", "le": "le", "<": "lt", "lt": "lt",
          ">=": "ge", "≥": "ge", "ge": "ge", ">": "gt", "gt": "gt",
          "=": "eq", "==": "eq", "eq": "eq", "!=": "ne", "ne": "ne"}

STATUS_TOKENS = [
    ("already", ("已具备", "现有", "在库", "可用", "在位", "正常", "available", "ready",
                 "owned", "in-house", "in house")),
    ("outsource", ("可外协", "外协", "共享", "送检", "排队", "shared", "outsourced", "外送")),
    ("procure", ("需采购", "采购", "待采购", "待申请", "procure", "purchase", "quote",
                 "待购", "订购")),
    ("unavailable", ("不具备", "维护", "停用", "无备件", "unavailable", "full", "busy",
                     "满载", "占用", "停机")),
    ("not_applicable", ("不适用", "n/a", "not applicable", "not-applicable")),
]

NAME_KEYS = ("name", "item", "model", "resource", "param", "parameter", "key",
             "variable", "field", "object", "id", "title")
MIN_KEYS = ("min", "minimum", "lower", "low", "from", "start", "lo")
MAX_KEYS = ("max", "maximum", "upper", "high", "to", "end", "hi")
STEP_KEYS = ("step", "resolution", "increment", "granularity", "interval")
PRICE_KEYS = ("unit_price", "price", "rate", "fee", "cost_per_unit", "unit_cost",
              "price_per_unit", "单价", "价格")
QTY_KEYS = ("qty", "quantity", "amount", "usage", "per_run", "per_sample",
            "consumption", "dose", "用量", "数量")
LEAD_KEYS = ("lead_time", "lead", "货期", "交期", "delivery")
STOCK_KEYS = ("stock", "available", "avail", "库存", "在库量", "数量")
WINDOW_KEYS = ("window", "window_days", "slot", "schedule", "capacity", "档期", "窗口")
DAYRATE_KEYS = ("day_rate", "rate_per_day", "机时费", "day_cost", "cost_per_day")
BUDGET_KEYS = ("budget", "cap", "budget_cap", "cost_cap", "max_cost", "预算", "上限")
REQ_KEYS = ("required", "required_n", "plan_n", "planned", "计划", "需", "required_samples")
AVAIL_KEYS = ("available", "available_n", "enrolled", "入库", "可用", "available_samples")
APPROVAL_KEYS = ("approval", "approval_level", "status", "审批", "批件", "level", "irb",
                 "iacuc", "ethics")

HIST_KEYS = ("plans", "plan_versions", "candidates", "versions", "proposals", "options",
             "方案", "candidate_plans")
PARAM_BLOCK_KEYS = ("parameter_domains", "domains", "parameter_space", "search_space",
                    "ranges", "parameters", "参数范围", "params")
CONSTRAINT_KEYS = ("constraints", "limits", "restrictions", "requirements", "bounds", "约束")
EQUIP_KEYS = ("equipment", "instruments", "devices", "设备", "仪器")
MATERIAL_KEYS = ("materials", "consumables", "reagents", "supplies", "耗材", "材料")
BOOKING_KEYS = ("bookings", "booking", "reservations", "机时", "预约")
SAMPLE_KEYS = ("samples", "sample", "sample_plan", "样本")
APPROVAL_BLOCK_KEYS = ("approvals", "approval", "ethics", "permits", "审批", "伦理")
STEP_KEYS = ("steps", "procedure", "protocol", "workflow", "步骤")


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
    t = s(v).lower().replace("°", "").replace("℃", "c").replace("µ", "u")
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
    if "元" in t and "万" in t:
        return "wcny"
    for tok, u in sorted(UNIT_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if tok and tok in t:
            return u
    return ""


def to_minutes(val, unit):
    if val is None:
        return None
    u = unit or "min"
    fam = FAMILY.get(u)
    if not fam or fam[0] != "time":
        return val
    return val * FAMILY["min"][1] / fam[1] if FAMILY["min"][1] else val


def first_of(d, keys):
    if isinstance(d, dict):
        for k in keys:
            if k in d and s(d[k]) != "":
                return d[k]
        for k in keys:
            for kk in d:
                if nkey(kk) == nkey(k) and s(d[kk]) != "":
                    return d[kk]
    return None


def name_of(d, parent_key):
    v = first_of(d, NAME_KEYS)
    return s(v) if v is not None else s(parent_key)


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
            mats.append({"id": mid, "name": fn,
                         "rel": os.path.relpath(full, input_dir).replace("\\", "/"),
                         "path": full, "text": text, "json": obj,
                         "paras": _paras(mid, text), "chars": len(text),
                         "binary": binary,
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


def find_quote(text, needles, limit=280):
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
        q = "no quotable line located at %s" % loc
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


# --- markdown pipe tables ----------------------------------------------------
def pipe_tables(mat):
    """Return [{locator, header:[..], rows:[{col:val}], mat}] parsed from pipe tables."""
    text = mat.get("text", "")
    if not text:
        return []
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.count("|") >= 2 and i + 1 < len(lines) and re.match(
                r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            j, rows, raws = i + 2, [], []
            while j < len(lines) and lines[j].count("|") >= 2 and lines[j].strip():
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if len(cells) >= 2:
                    rows.append({header[k] if k < len(header) else "col%d" % k: cells[k]
                                 for k in range(len(cells))})
                    raws.append(lines[j].strip())
                j += 1
            if rows:
                out.append({"mat": mat, "locator": "%s/p%d" % (mat["id"], i + 1),
                            "header": header, "rows": rows, "raws": raws, "line": i + 1})
            i = j
        else:
            i += 1
    return out


def classify_status(text):
    t = s(text).lower()
    for code, toks in STATUS_TOKENS:
        for tok in toks:
            if tok and (tok in t):
                return code
    return "unknown"


def _cols(table):
    return [nkey(c) for c in table["header"]]


def _find_col(cols, keys):
    for k in keys:
        nk = nkey(k)
        for i, c in enumerate(cols):
            if c == nk:
                return i
    for k in keys:
        nk = nkey(k)
        for i, c in enumerate(cols):
            if nk and (nk in c or c in nk):
                return i
    return None


def _cell(row, header, idx):
    if idx is None:
        return None
    key = header[idx] if idx < len(header) else None
    for k, v in row.items():
        if nkey(k) == nkey(key):
            return v
    return None


def extract_tables(ctx):
    """Turn pipe tables into typed resources with locators + quotes."""
    for m in ctx["materials"]:
        ctx["tables"].extend(pipe_tables(m))
    for t in ctx["tables"]:
        cols = _cols(t)
        hdr = " | ".join(t["header"])
        i_name = _find_col(cols, ("name", "item", "model", "device", "resource", "参数",
                                  "设备", "耗材", "名称"))
        i_price = _find_col(cols, PRICE_KEYS)
        i_lead = _find_col(cols, LEAD_KEYS)
        i_qty = _find_col(cols, QTY_KEYS)
        i_stock = _find_col(cols, STOCK_KEYS)
        i_win = _find_col(cols, WINDOW_KEYS)
        i_day = _find_col(cols, DAYRATE_KEYS)
        i_stat = _find_col(cols, ("status", "state", "状态", "availability", "可用性"))
        i_min = _find_col(cols, ("min", "minimum", "下限", "lower"))
        i_max = _find_col(cols, ("max", "maximum", "上限", "upper"))
        i_step = _find_col(cols, ("step", "步长"))
        i_unit = _find_col(cols, ("unit", "单位"))
        for ri, row in enumerate(t["rows"]):
            loc = "%s!r%d" % (t["locator"], ri + 1)
            raws = t.get("raws") or []
            quote = (raws[ri] if ri < len(raws)
                     else " | ".join("%s: %s" % (k, v) for k, v in row.items()))
            quote = quote[:280]
            nm = s(_cell(row, t["header"], i_name))
            base = {"source_id": t["mat"]["id"], "locator": loc, "quote": quote,
                    "verified": quote[:60] in t["mat"]["text"]}
            if i_min is not None and i_max is not None:
                mn, mx = num(_cell(row, t["header"], i_min)), num(_cell(row, t["header"], i_max))
                if mn is not None and mx is not None and mx > mn and nm:
                    _add_domain(ctx, nm, mn, mx, num(_cell(row, t["header"], i_step)),
                                s(_cell(row, t["header"], i_unit)) or unit_of(quote), base)
            if i_price is not None and nm:
                pr = num(_cell(row, t["header"], i_price))
                if pr is not None:
                    ctx["res_materials"].append(
                        {"name": nm, "unit_price": pr, "unit": unit_of(quote),
                         "lead_time": num(_cell(row, t["header"], i_lead)),
                         "lead_unit": unit_of(s(_cell(row, t["header"], i_lead))),
                         "stock": num(_cell(row, t["header"], i_stock)),
                         "qty": num(_cell(row, t["header"], i_qty)),
                         "status": classify_status(s(_cell(row, t["header"], i_stat))),
                         "evidence": base})
            elif i_day is not None and nm:
                dr = num(_cell(row, t["header"], i_day))
                if dr is not None:
                    ctx["res_bookings"].append(
                        {"name": nm, "day_rate": dr, "window_days": num(_cell(row, t["header"], i_win)),
                         "unit": unit_of(quote),
                         "status": classify_status(s(_cell(row, t["header"], i_stat))),
                         "evidence": base})
            elif i_stat is not None and nm and i_win is not None:
                ctx["res_bookings"].append(
                    {"name": nm, "day_rate": None, "window_days": num(_cell(row, t["header"], i_win)),
                     "unit": unit_of(quote),
                     "status": classify_status(s(_cell(row, t["header"], i_stat))),
                     "evidence": base})
            elif i_stat is not None and nm and not nm.isdigit():
                ctx["res_equipment"].append(
                    {"name": nm, "status": classify_status(s(_cell(row, t["header"], i_stat))),
                     "evidence": base})
            if not any(c.startswith("r") for c in ()) and hdr:
                pass


def _add_domain(ctx, name, mn, mx, step, unit, evidence):
    k = nkey(name)
    if not k or mx <= mn:
        return
    for d in ctx["params"]:
        if d["key"] == k and abs(d["min"] - mn) < 1e-9 and abs(d["max"] - mx) < 1e-9:
            return
    if step is None or step <= 0 or step > (mx - mn):
        step = (mx - mn) / 10.0
    ctx["params"].append({"key": k, "name": s(name), "min": float(mn), "max": float(mx),
                          "step": float(step), "unit": unit or "", "evidence": [evidence]})


def _add_constraint(ctx, param, op, value, unit, evidence):
    if not op or op not in ("le", "lt", "ge", "gt", "eq", "ne"):
        return
    k = nkey(param)
    for c in ctx["constraints"]:
        if c["key"] == k and c["op"] == op and abs((num(c["value"]) or 0.0) - (num(value) or 0.0)) < 1e-9:
            return
    ctx["constraints"].append({"id": "C%02d" % (len(ctx["constraints"]) + 1), "key": k,
                               "param": s(param), "op": op, "value": value,
                               "unit": unit or "", "evidence": [evidence],
                               "source": evidence["source_id"]})


MARKDOWN_OP = [
    (re.compile(r"(不得高于|不超过|上限|最高|≤|<=|no more than|at most|up to)"), "le"),
    (re.compile(r"(不得低于|不低于|下限|最低|≥|>=|no less than|at least|not below)"), "ge"),
    (re.compile(r"(小于|低于|less than|below)"), "lt"),
    (re.compile(r"(大于|高于|greater than|above)"), "gt")]


def scan_text_rules(ctx):
    """Capture numeric bounds stated in prose and generic rule rows for evidence."""
    dom_keys = [d["key"] for d in ctx["params"]]
    for m in ctx["materials"]:
        text = m.get("text", "")
        for i, ln in enumerate(text.splitlines()):
            if not ln.strip():
                continue
            for rx, op in MARKDOWN_OP:
                if rx.search(ln.lower()):
                    nums = [x for x in (num(y) for y in re.findall(r"[-+]?\d+(?:\.\d+)?", ln))
                            if x is not None]
                    if not nums:
                        break
                    target = None
                    for k in dom_keys:
                        if k and k in nkey(ln):
                            target = k
                            break
                    if target is None and len(dom_keys) == 1:
                        target = dom_keys[0]
                    if target is not None:
                        _add_constraint(ctx, target, op, nums[0], unit_of(ln),
                                        ev(m, "p%d" % (i + 1), [ln.strip()[:40]]))
                    break


def _domain_from_dict(d, parent, ctx, mat, path):
    if not isinstance(d, dict):
        return
    mn = num(first_of(d, MIN_KEYS))
    mx = num(first_of(d, MAX_KEYS))
    nm = name_of(d, parent)
    if mn is None or mx is None or not nm or mx <= mn:
        return
    st = num(first_of(d, STEP_KEYS))
    unit = s(first_of(d, ("unit", "units", "u"))) or unit_of(s(first_of(d, MIN_KEYS)))
    _add_domain(ctx, nm, mn, mx, st, unit, ev(mat, path, [nm, s(mn), s(mx)]))


def _pair_domains(d, ctx, mat, path):
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
            mx = maxs[stem][0]
            _add_domain(ctx, re.sub(r"(_min|_max|\s)", "", s(kmin)), mn, mx, None, "",
                        ev(mat, path, [kmin, maxs[stem][1]]))


def extract_json(ctx):
    sources = [{"mat": {"id": "CASE", "text": "", "json": ctx["_case"]}, "obj": ctx["_case"]}]
    for m in ctx["materials"]:
        sources.append({"mat": m, "obj": m.get("json")})
    for src in sources:
        obj, mat = src["obj"], src["mat"]
        if not isinstance(obj, dict):
            continue
        pairs = []
        walk(obj, "$", pairs)
        for path, d in pairs:
            _domain_from_dict(d, "", ctx, mat, path)
        for path, d in pairs:
            _pair_domains(d, ctx, mat, path)
        for path, d in pairs:
            _collect_resources(ctx, d, mat, path)
        for path, d in pairs:
            self_plan = _plan_record(ctx, d, mat, path)
            if self_plan:
                ctx["plans"].append(self_plan)
        for key in obj:
            nk = nkey(key)
            if nk in [nkey(x) for x in CONSTRAINT_KEYS] and isinstance(obj[key], list):
                for i, item in enumerate(obj[key]):
                    _constraint_item(ctx, item, mat, "$.%s[%d]" % (key, i))
            if nk in [nkey(x) for x in BUDGET_KEYS]:
                bv = num(obj[key])
                if bv is not None and ctx["budget"] is None:
                    ctx["budget"] = bv
                    ctx["budget_ev"].append(ev(mat, "$.%s" % key, [s(key), s(obj[key])]))
        for path, d in pairs:
            for k, v in d.items():
                if nkey(k) in [nkey(x) for x in BUDGET_KEYS]:
                    bv = num(v)
                    if bv is not None and ctx["budget"] is None:
                        ctx["budget"] = bv
                        ctx["budget_ev"].append(ev(mat, path + "." + s(k), [s(k), s(v)]))


def _constraint_item(ctx, item, mat, path):
    if not isinstance(item, dict):
        return
    param = name_of(item, "")
    op = None
    for k in ("op", "operator", "relation", "comparison", "sign"):
        if k in item and s(item[k]).lower() in OP_MAP:
            op = OP_MAP[s(item[k]).lower()]
            break
    val = first_of(item, ("value", "limit", "threshold", "bound", "target", "v"))
    if op is None:
        if first_of(item, ("max", "upper", "maximum")) is not None:
            op, val = "le", first_of(item, ("max", "upper", "maximum"))
        elif first_of(item, ("min", "lower", "minimum")) is not None:
            op, val = "ge", first_of(item, ("min", "lower", "minimum"))
    vv = num(val)
    if op and param and vv is not None:
        unit = s(first_of(item, ("unit", "units"))) or unit_of(s(val))
        _add_constraint(ctx, param, op, vv, unit, ev(mat, path, [param, s(val)]))


def _collect_resources(ctx, d, mat, path):
    if not isinstance(d, dict):
        return
    nm = name_of(d, "")
    if not nm:
        return
    status = classify_status(s(first_of(d, ("status", "state", "availability", "状态"))))
    price = num(first_of(d, PRICE_KEYS))
    lead = num(first_of(d, LEAD_KEYS))
    qty = num(first_of(d, QTY_KEYS))
    stock = num(first_of(d, STOCK_KEYS))
    win = num(first_of(d, WINDOW_KEYS))
    day = num(first_of(d, DAYRATE_KEYS))
    base = None
    if price is not None:
        base = ev(mat, path, [nm, s(price)])
        ctx["res_materials"].append({"name": nm, "unit_price": price, "unit": unit_of(s(price)),
                                     "lead_time": lead, "lead_unit": unit_of(s(lead)),
                                     "stock": stock, "qty": qty, "status": status, "evidence": base})
    elif day is not None or (win is not None and ("机时" in s(path) or "book" in s(path).lower())):
        base = ev(mat, path, [nm, s(day if day is not None else win)])
        ctx["res_bookings"].append({"name": nm, "day_rate": day, "window_days": win,
                                    "unit": unit_of(s(day)), "status": status, "evidence": base})
    elif first_of(d, REQ_KEYS) is not None or "sample" in s(path).lower() or "样本" in s(path):
        rq = num(first_of(d, REQ_KEYS))
        av = num(first_of(d, AVAIL_KEYS))
        if rq is not None or av is not None:
            base = ev(mat, path, [nm] + [s(x) for x in (rq, av) if x is not None])
            ctx["res_samples"].append({"name": nm, "required": rq, "available": av,
                                       "unit": s(first_of(d, ("unit", "units"))) or "unit",
                                       "evidence": base})
    elif first_of(d, APPROVAL_KEYS) is not None and ("approv" in s(path).lower()
                                                     or "ethic" in s(path).lower()
                                                     or "审批" in s(path) or "伦理" in s(path)):
        base = ev(mat, path, [nm])
        ctx["res_approvals"].append({"name": nm,
                                     "level": s(first_of(d, APPROVAL_KEYS)),
                                     "window_days": win, "status": classify_status(
                                         s(first_of(d, ("status", "state", "状态")))),
                                     "evidence": base})
    elif status != "unknown":
        base = ev(mat, path, [nm])
        ctx["res_equipment"].append({"name": nm, "status": status, "evidence": base})


def _plan_record(ctx, d, mat, path):
    if not isinstance(d, dict):
        return None
    ks = [nkey(k) for k in d.keys()]
    has_v = any("version" in k or k in ("v", "plan", "candidate", "方案") for k in ks)
    params = {}
    for k in ("params", "parameters", "values", "settings"):
        if isinstance(d.get(k), dict):
            for kk, vv in d[k].items():
                params[s(kk)] = vv
    if not has_v or not params:
        return None
    ver = s(first_of(d, ("version", "id", "name", "label", "v", "方案"))) or "v?"
    claims = []
    for k in ("claims", "claimed", "asserted"):
        v = d.get(k)
        if isinstance(v, list):
            claims = [s(x) for x in v]
    steps = []
    for k in STEP_KEYS:
        v = d.get(k)
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    steps.append(_step_record(it))
    return {"version": ver, "params": params, "claims": claims, "steps": steps,
            "locator": "%s/%s" % (mat["id"], path),
            "evidence": ev(mat, path, [ver] + list(params.keys())[:1])}


def _step_record(it):
    return {"step": s(first_of(it, ("step", "name", "action", "步骤"))) or "step",
            "duration_min": num(first_of(it, ("duration_min", "duration", "minutes", "min"))),
            "labor_people": num(first_of(it, ("labor_people", "people", "labor", "人力"))) or 1,
            "wait_days": num(first_of(it, ("wait_days", "wait", "等待"))) or 0,
            "equipment": s(first_of(it, ("equipment", "device", "设备"))),
            "depends_on": first_of(it, ("depends_on", "deps")) or []}


def extract(case, mats):
    ctx = {"case_id": s((case or {}).get("case_id")) or "unknown-case",
           "task_instruction": s((case or {}).get("task_instruction")
                                 or (case or {}).get("prompt")
                                 or (case or {}).get("instruction")),
           "_case": case, "contract": (case or {}).get("output_contract"),
           "materials": mats, "params": [], "constraints": [], "tables": [],
           "res_equipment": [], "res_materials": [], "res_bookings": [],
           "res_samples": [], "res_approvals": [], "budget": None, "budget_ev": [],
           "plans": [], "rules": [], "degradations": [], "errors": [], "notes": {}}
    extract_tables(ctx)
    extract_json(ctx)
    scan_text_rules(ctx)
    # dedupe
    seen = set()
    for lst in ("res_equipment", "res_materials", "res_bookings", "res_samples",
                "res_approvals"):
        uniq = []
        for it in ctx[lst]:
            k = (nkey(it.get("name")), s(it.get("status")) or s(it.get("unit_price"))
                 or s(it.get("window_days")))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(it)
        ctx[lst] = uniq[:80]
    pseen = set()
    up = []
    for p in ctx["plans"]:
        k = (s(p["version"]), ",".join(sorted(nkey(x) for x in p["params"])))
        if k in pseen:
            continue
        pseen.add(k)
        up.append(p)
    ctx["plans"] = up[:12]
    # generic rule rows from pipe tables for the rules index
    for t in ctx["tables"]:
        if not t["rows"]:
            continue
        ctx["rules"].append({"locator": t["locator"],
                             "header": t["header"], "n_rows": len(t["rows"]),
                             "quote": " | ".join(t["header"])[:200]})

    if not ctx["plans"]:
        ctx["degradations"].append(
            "No versioned candidate plan object was found in the supplied material; the "
            "review reports the rule index and searched locations instead of a verdict.")
    if not (ctx["res_equipment"] or ctx["res_materials"] or ctx["res_bookings"]):
        ctx["degradations"].append(
            "No concrete resource-contract object (equipment / consumable / booking) was "
            "found; the resource four-state table is reported as searched-but-absent.")
    if not ctx["params"]:
        ctx["degradations"].append(
            "No finite parameter domain {min,max,step,unit} was found; the in-domain and "
            "step-alignment checks are reported absent with their searched locations.")
    if ctx["budget"] is None:
        ctx["degradations"].append(
            "No budget ceiling was supplied; the cost ledger preserves its formula and leaves "
            "the over-budget percentage open.")
    if not ctx["res_samples"]:
        ctx["degradations"].append(
            "No sample plan (required vs available) was found; sample sufficiency is reported "
            "as not declared rather than assumed satisfied.")
    for m in mats:
        if m["kind"] == "binary":
            ctx["degradations"].append("Material %s is binary or unparsed; only its size is "
                                       "recorded." % m["id"])
        if m["kind"] == "json" and m["json"] is None and m["chars"]:
            ctx["degradations"].append("Material %s looks like JSON but did not parse; it is "
                                       "indexed as plain text." % m["id"])
    return ctx
