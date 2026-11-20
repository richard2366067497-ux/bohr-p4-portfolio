# -*- coding: utf-8 -*-
"""Material scanning + source-grounded extraction for the plan comparison.

Pulls the criteria dictionary, the state/grade/feasibility dictionaries, the cost and
time formulas and any candidate workbook rows out of the supplied material, each with a
locator and a verbatim quote.  Absent structures are recorded as searched-but-absent.
"""
import json
import math
import os
import re

DIR_HIGH = ("越高越好", "higher", "high-is-better", "max", "越高", "越大越好")
DIR_LOW = ("越低越好", "lower", "low-is-better", "min", "越低", "越小越好")

STATE_ROWS = [
    (4, ("已具备", "现有", "在库", "已批准", "已获批", "available", "ready", "已到位")),
    (3, ("可外协", "共享", "不适用", "在审", "已提交", "shared", "outsource", "in-review")),
    (2, ("需采购", "待申请", "待批", "排期中", "采购中", "procure", "pending", "排队")),
    (1, ("不具备", "无", "未申请", "不可用", "unavailable", "blocked", "停用")),
    (0, ("未声明", "未知", "unknown", "not-declared", "unspecified")),
]

CAND_KEYS = ("candidates", "plans", "options", "alternatives", "versions", "proposals", "方案")
CONSTRAINT_KEYS = ("constraints", "limits", "gates", "硬约束")
COSTTIME_KEYS = ("cost_time", "costtime", "cost", "ledger", "台账")
ASSUMPTION_KEYS = ("assumptions", "sensitivity", "假设")
RISK_KEYS = ("risks", "risk", "风险")
FLIP_KEYS = ("flip_points", "flip", "thresholds", "翻转点")

OP_MAP = {"<=": "le", "≤": "le", "<": "lt", ">=": "ge", "≥": "ge", ">": "gt",
          "==": "eq", "=": "eq", "!=": "ne"}


def s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
            return str(int(round(v)))
        return ("%.6f" % v).rstrip("0").rstrip(".")
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
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", t.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def first_of(d, keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and s(d[k]) != "":
            return d[k]
    for k in keys:
        for kk in d:
            if nkey(kk) == nkey(k) and s(d[kk]) != "":
                return d[kk]
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
            mid = "M%02d" % idx
            try:
                with open(full, "rb") as fh:
                    raw = fh.read(4_000_000)
            except OSError:
                raw = b""
            binary = b"\x00" in raw[:4096]
            text = "" if binary else raw.decode("utf-8", "replace")
            obj = None
            if fn.lower().endswith((".json", ".jsonl")) and text.strip():
                try:
                    obj = json.loads(text)
                except ValueError:
                    obj = None
            mats.append({"id": mid, "name": fn,
                         "rel": os.path.relpath(full, input_dir).replace("\\", "/"),
                         "path": full, "text": text, "json": obj,
                         "paras": _paras(mid, text), "chars": len(text), "binary": binary,
                         "kind": "json" if obj is not None else ("text" if text else "binary")})
    return mats


def _paras(mid, text):
    out, buf, pi = [], [], 0
    for ln in (text or "").splitlines():
        if ln.strip():
            buf.append(ln.rstrip())
        elif buf:
            pi += 1
            out.append({"locator": "%s#p%d" % (mid, pi), "text": "\n".join(buf)})
            buf = []
    if buf:
        pi += 1
        out.append({"locator": "%s#p%d" % (mid, pi), "text": "\n".join(buf)})
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


def ev(mat, locator, needles):
    text = mat.get("text", "") if isinstance(mat, dict) else ""
    q = find_quote(text, needles)
    ok = bool(q) and q[:80] in text
    if not q:
        q = "no quotable line located at %s" % locator
    return {"source_id": mat.get("id", ""), "locator": locator, "quote": q, "verified": ok}


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


def pipe_tables(mat):
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
                out.append({"mat": mat, "locator": "%s#p%d" % (mat["id"], i + 1),
                            "header": header, "rows": rows, "raws": raws, "line": i + 1})
            i = j
        else:
            i += 1
    return out


def _col(head, *names):
    ns = [nkey(n) for n in names]
    for i, h in enumerate(head):
        if nkey(h) in ns:
            return i
    for i, h in enumerate(head):
        for n in ns:
            if n and (n in nkey(h) or nkey(h) in n):
                return i
    return None


def _cell(row, head, i):
    if i is None:
        return None
    key = head[i] if i < len(head) else None
    for k, v in row.items():
        if nkey(k) == nkey(key):
            return v
    return None


def extract_tables(ctx):
    for m in ctx["materials"]:
        ctx["tables"].extend(pipe_tables(m))
    for t in ctx["tables"]:
        head = t["header"]
        cols = [nkey(h) for h in head]
        joined = "".join(cols)
        i_id = _col(head, "id", "criterion", "准则")
        i_name = _col(head, "name", "名称")
        i_unit = _col(head, "unit", "单位")
        i_dir = _col(head, "direction", "方向")
        i_w = _col(head, "weight", "权重", "默认权重")
        i_why = _col(head, "why", "理由")
        i_score = _col(head, "分值", "score", "分")
        i_tokens = _col(head, "典型写法", "写法", "tokens")
        i_grade = _col(head, "等级", "grade")
        i_state = _col(head, "状态", "state")
        i_cond = _col(head, "判定条件", "条件", "condition")
        i_field = _col(head, "字段", "field")
        for ri, row in enumerate(t["rows"]):
            loc = "%s!r%d" % (t["locator"], ri + 1)
            raws = t.get("raws") or []
            quote = (raws[ri] if ri < len(raws)
                     else " | ".join("%s: %s" % (k, v) for k, v in row.items()))[:280]
            base = {"source_id": t["mat"]["id"], "locator": loc, "quote": quote,
                    "verified": quote[:50] in t["mat"]["text"]}
            if i_w is not None and i_id is not None and i_dir is not None:
                cid = s(_cell(row, head, i_id))
                w = num(_cell(row, head, i_w))
                if cid and w is not None and not cid.isdigit():
                    ctx["criteria"].append(
                        {"id": cid, "name": s(_cell(row, head, i_name)) or cid,
                         "unit": s(_cell(row, head, i_unit)),
                         "direction": _direction(s(_cell(row, head, i_dir))),
                         "weight": w, "why": s(_cell(row, head, i_why)), "evidence": base})
                    continue
            if i_score is not None and i_tokens is not None:
                sc = num(_cell(row, head, i_score))
                toks = s(_cell(row, head, i_tokens))
                if sc is not None and toks and 0 <= sc <= 4:
                    ctx["state_map"].append({"score": sc, "tokens": toks, "evidence": base})
                    continue
            if i_grade is not None:
                g = s(_cell(row, head, i_grade))
                if g and len(g) <= 3:
                    ctx["grades"].append({"grade": g, "source": s(_cell(row, head, 1)),
                                          "strength": s(_cell(row, head, 2)), "evidence": base})
                    continue
            if i_state is not None and i_cond is not None:
                st = s(_cell(row, head, i_state))
                if st and ("`" in st or st.isascii()):
                    ctx["feasibility_states"].append(
                        {"state": st, "condition": s(_cell(row, head, i_cond)), "evidence": base})
                    continue
            if i_field is not None and joined:
                f = s(_cell(row, head, i_field))
                if f and not f.isdigit():
                    ctx["field_rules"].append({"field": f, "evidence": base})


def _direction(v):
    t = s(v).lower()
    for tok in DIR_LOW:
        if tok.lower() in t:
            return "lower"
    for tok in DIR_HIGH:
        if tok.lower() in t:
            return "higher"
    return "higher"


def extract_formulas(ctx):
    for m in ctx["materials"]:
        text = m.get("text", "")
        if not text:
            continue
        for i, ln in enumerate(text.splitlines()):
            low = ln.lower()
            if ("总成本" in ln or "total_cost" in low) and ("=" in ln or "Σ" in ln):
                ctx["formulas"].append({"kind": "cost", "text": ln.strip()[:200],
                                        "locator": "%s#p%d" % (m["id"], i + 1), "evidence": ev(m, "%s#p%d" % (m["id"], i + 1), [ln.strip()[:30]])})
            elif "总周期" in ln or "total_duration" in low:
                if "=" in ln or "＋" in ln or "+" in ln:
                    ctx["formulas"].append({"kind": "duration", "text": ln.strip()[:200],
                                            "locator": "%s#p%d" % (m["id"], i + 1), "evidence": ev(m, "%s#p%d" % (m["id"], i + 1), [ln.strip()[:30]])})
            elif "n = (v - lo)" in ln or "n = (hi - v)" in ln:
                ctx["norm_rules"].append({"text": ln.strip()[:160],
                                          "locator": "%s#p%d" % (m["id"], i + 1)})
            elif "score = 100" in low or "score = 100" in ln:
                ctx["weight_rule"] = {"text": ln.strip()[:160],
                                      "locator": "%s#p%d" % (m["id"], i + 1)}


def _candidate_from_dict(d, mat, path, ctx):
    if not isinstance(d, dict):
        return None
    cid = s(first_of(d, ("candidate_id", "id", "key", "name", "方案", "候选")))
    values = d.get("values") if isinstance(d.get("values"), dict) else d.get("criteria")
    if not cid or not isinstance(values, dict):
        return None
    vals = {}
    for k, v in values.items():
        if isinstance(v, dict):
            disp = first_of(v, ("display", "value", "v", "值"))
            e = v.get("evidence") if isinstance(v.get("evidence"), dict) else {}
            vals[s(k)] = {"display": disp, "unit": s(first_of(v, ("unit", "单位"))),
                          "grade": s(first_of(v, ("grade", "等级"))),
                          "locator": s(first_of(e, ("locator", "source"))),
                          "quote": s(first_of(e, ("quote", "text")))}
        else:
            vals[s(k)] = {"display": v, "unit": "", "grade": "", "locator": "",
                          "quote": ""}
    params = d.get("params") if isinstance(d.get("params"), dict) else {}
    return {"candidate_id": cid, "name": s(first_of(d, ("name", "title", "方案"))) or cid,
            "values": vals, "params": {s(k): v for k, v in params.items()},
            "source": "%s/%s" % (mat.get("id", ""), path),
            "evidence": ev(mat, path, [cid])}


def extract_from_obj(ctx, obj, mat, tag):
    if not isinstance(obj, dict):
        return
    pairs = []
    walk(obj, tag, pairs)
    for path, d in pairs:
        for k in d:
            if nkey(k) in [nkey(x) for x in CAND_KEYS] and isinstance(d[k], list):
                for i, it in enumerate(d[k]):
                    c = _candidate_from_dict(it, mat, "$.%s[%d]" % (k, i), ctx)
                    if c:
                        ctx["candidates"].append(c)
            if nkey(k) in [nkey(x) for x in CONSTRAINT_KEYS] and isinstance(d[k], list):
                for i, it in enumerate(d[k]):
                    _constraint(ctx, it, mat, "$.%s[%d]" % (k, i))
            if nkey(k) in [nkey(x) for x in COSTTIME_KEYS] and isinstance(d[k], dict):
                ctx["cost_time"] = dict(ctx["cost_time"], **d[k]) if ctx["cost_time"] else d[k]
                ctx["cost_time_src"] = ev(mat, path + "." + s(k), [s(k)])
            if nkey(k) in [nkey(x) for x in ASSUMPTION_KEYS] and isinstance(d[k], list):
                ctx["assumptions"] = list(d[k])[:12]
                ctx["assumptions_src"] = ev(mat, path + "." + s(k), [s(k)])
            if nkey(k) in [nkey(x) for x in RISK_KEYS] and isinstance(d[k], list):
                ctx["risks"] = list(d[k])[:12]
                ctx["risks_src"] = ev(mat, path + "." + s(k), [s(k)])
            if nkey(k) in [nkey(x) for x in FLIP_KEYS] and isinstance(d[k], list):
                ctx["flip_claims"] = list(d[k])[:12]
    if isinstance(obj.get("case_id"), str):
        pass


def _constraint(ctx, it, mat, path):
    if not isinstance(it, dict):
        return
    crit = s(first_of(it, ("criterion", "param", "field", "约束", "指标")))
    op = OP_MAP.get(s(first_of(it, ("op", "operator", "relation"))).lower())
    val = num(first_of(it, ("value", "limit", "threshold", "bound")))
    sev = s(first_of(it, ("severity", "level"))) or "hard"
    if crit and op and val is not None:
        ctx["constraints"].append({"id": s(first_of(it, ("id", "key"))) or "K%d" % (len(ctx["constraints"]) + 1),
                                   "criterion": crit, "op": op, "value": val,
                                   "severity": sev, "evidence": ev(mat, path, [crit, s(val)])})


def extract(case, mats, draft=None):
    ctx = {"case_id": s((case or {}).get("case_id")) or "unknown-case",
           "_case": case, "materials": mats, "tables": [], "criteria": [],
           "state_map": [], "grades": [], "feasibility_states": [], "field_rules": [],
           "formulas": [], "norm_rules": [], "weight_rule": {}, "candidates": [],
           "constraints": [], "cost_time": {}, "cost_time_src": {}, "assumptions": [],
           "assumptions_src": {}, "risks": [], "risks_src": {}, "flip_claims": [],
           "degradations": [], "errors": [],
           "task_instruction": s((case or {}).get("task_instruction")
                                 or (case or {}).get("prompt"))}
    extract_tables(ctx)
    extract_formulas(ctx)
    for m in mats:
        if m.get("json") is not None:
            extract_from_obj(ctx, m["json"], m, m["id"])
    if isinstance(draft, dict):
        extract_from_obj(ctx, draft, {"id": "DRAFT", "text": ""}, "draft")
        if isinstance(draft.get("criteria"), list):
            w = [c for c in draft["criteria"] if isinstance(c, dict)]
            if w:
                ctx["criteria"] = [{"id": s(c.get("id")), "name": s(c.get("name")) or s(c.get("id")),
                                    "unit": s(c.get("unit")),
                                    "direction": _direction(s(c.get("direction"))) if c.get("direction") else _dir_from_default(s(c.get("id"))),
                                    "weight": num(c.get("weight")) or 0.0,
                                    "why": s(c.get("why")),
                                    "evidence": {"source_id": "DRAFT", "locator": "draft.criteria",
                                                 "quote": "draft criterion %s" % s(c.get("id")),
                                                 "verified": False}}
                                   for c in w if s(c.get("id"))]
    # dedupe candidates
    seen, uniq = set(), []
    for c in ctx["candidates"]:
        if c["candidate_id"] in seen:
            continue
        seen.add(c["candidate_id"])
        uniq.append(c)
    ctx["candidates"] = uniq[:12]
    # dedupe criteria by id keeping first
    cseen, cu = set(), []
    for c in ctx["criteria"]:
        if c["id"] in cseen:
            continue
        cseen.add(c["id"])
        cu.append(c)
    ctx["criteria"] = cu[:24]
    if not ctx["criteria"]:
        ctx["degradations"].append(
            "No criteria dictionary was found in the material; the weighted comparison is "
            "reported as not computable and the searched locations are listed.")
    if not ctx["candidates"]:
        ctx["degradations"].append(
            "No candidate workbook was found in the material (no candidates/options list and "
            "no filled draft); the matrix is reported with its criteria index only.")
    if not ctx["constraints"]:
        ctx["degradations"].append(
            "No hard or soft constraint was declared; the feasibility gate is reported as not "
            "declared rather than assumed passed.")
    if not ctx["assumptions"]:
        ctx["degradations"].append(
            "No assumption with an effect was declared; the flip-threshold scan is reported as "
            "not computable.")
    if not ctx["cost_time"]:
        ctx["degradations"].append(
            "No cost_time ledger was declared; the per-item arithmetic recomputation is "
            "reported as not declared.")
    for m in mats:
        if m["kind"] == "binary":
            ctx["degradations"].append("Material %s is binary or unparsed; only its size is recorded." % m["id"])
        if m["kind"] == "json" and m["json"] is None and m["chars"]:
            ctx["degradations"].append("Material %s looks like JSON but did not parse." % m["id"])
    return ctx


def _dir_from_default(cid):
    low = ("total_cost", "total_duration", "risk_level")
    return "lower" if nkey(cid) in [nkey(x) for x in low] else "higher"
