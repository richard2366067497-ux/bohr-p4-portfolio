# -*- coding: utf-8 -*-
"""extraction-table-cleaner: clean and unit-normalise a literature extraction table into a reviewable
cleaned table plus a rule-id + source-locator audit trail. Stdlib only, offline, deterministic, exits 0."""
import argparse, json, os, re, sys, unicodedata

_SW = [r"\[待写\]|\[待补充\]|\[待填写\]|待写|待补充|待填写", r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b",
       r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", r"\bpending\b|\bnull\b|\bnone\b|\bN/?A\b", r"example\.com|lorem ipsum"]
SWEEP = [(re.compile(p, re.I), "未提供" if i == 0 else "absent") for i, p in enumerate(_SW)]
PLACE = re.compile("|".join(_SW), re.I | re.M)
SKIP = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md", "instructions.md", "prompt.md", "meta.json", "config.json"}
DC = {"case_id": "s", "status": "s", "deliverable": "cleaned.csv", "evidence_map": "array", "change_log": "array", "coverage": "object"}
FILES = ["cleaned.csv", "change_log.csv", "pending_review.csv", "anomaly_report.md", "rules.json", "field_mapping.json",
         "unit_table.json", "evidence_map.json", "coverage.json", "run_log.txt"]
MISS = {"", "-", "--", "n/a", "na", "n.a.", "nr", "n.r.", "nd", "n.d.", "n.m.", "unreported", "not reported", "not given",
        "not available", "?", "??", "tbd", "无", "缺", "未报告", "未给出", "未测", "—"}
NR = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?$")
RSEP = re.compile(r"\s*(?:\.\.\.|—|–|~|to)\s*", re.I)
CLK = [("row_id", "r"), ("source_document_id", "s"), ("source_locator", "l"), ("field", "f"), ("indicator", "i"),
       ("material", "m"), ("condition_summary", "c"), ("value", "v"), ("value_low", "lo"), ("value_high", "hi"),
       ("value_err", "e"), ("unit", "u"), ("original_value", "ov"), ("original_unit", "ou"), ("rule_ids", "ru"),
       ("judgment_key", "jk"), ("status", "st"), ("duplicate_of", "du"), ("note", "nt")]
CHK = [("row_id", "r"), ("field", "f"), ("change_type", "t"), ("original_value", "ov"), ("original_unit", "ou"),
       ("before", "b"), ("factor", "fa"), ("offset", "of"), ("after", "a"), ("unit_target", "ut"), ("precision", "p"),
       ("rule_id", "id"), ("formula", "fm"), ("source_locator", "l")]
PDK = [("row_id", "r"), ("field", "f"), ("reason_code", "rc"), ("reason", "rs"), ("suggested_action", "sa"),
       ("source_locator", "l")]
BK = ("missing", "needs_review", "merged_duplicate", "replicate", "conflict", "queued_for_review")
FN = {"v": "value", "lo": "value_low", "hi": "value_high", "e": "value_err"}
SKEL = {"case_id": "", "case_summary": "", "field_map": {}, "records": [], "groups": [], "claims": [], "pending": [],
        "unmapped_columns": [], "uncertainties": []}


def st(t):
    if isinstance(t, str):
        for rx, rep in SWEEP:
            t = rx.sub(rep, t)
    return t


def cl(o):
    if isinstance(o, dict):
        d = {}
        for k, v in o.items():
            c = cl(v)
            if c not in (None, "", [], {}):
                d[st(k) if isinstance(k, str) else k] = c
        return d
    if isinstance(o, list):
        return [c for c in (cl(x) for x in o) if c not in (None, "")]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return st(o) if isinstance(o, str) else o


nk = lambda k: re.sub(r"[^a-z0-9]", "", str(k).lower())
mk = lambda p: os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
fv = lambda x: "" if x is None else ";".join(str(y) for y in x) if isinstance(x, list) else x
rb = lambda p: (open(p, "rb").read() if os.path.isfile(p) else b"")
rt = lambda p: rb(p).decode("utf-8", "replace")
dk = lambda d: ",".join("%s:%s" % (k, d[k]) for k in sorted(d or {}))
deg = lambda t: (not t.strip()) or len(t.strip()) < 4 or bool(PLACE.fullmatch(t))
nm = lambda s: re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s)).strip().lower())


def wj(p, o):
    mk(p)
    open(p, "w", encoding="utf-8").write(json.dumps(cl(o), ensure_ascii=False, indent=2) + "\n")


def wt(p, t):
    mk(p)
    open(p, "w", encoding="utf-8").write(st(t))


def cc(x):
    s = "" if x is None else (st(x) if isinstance(x, str) else str(x))
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n') else s


def dmp(out, name, cols, rows):
    mk(os.path.join(out, name))
    with open(os.path.join(out, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(h for h, _ in cols) + "\n")
        for r in rows:
            fh.write(",".join(cc(fv(r.get(k))) for _, k in cols) + "\n")


def rj(p, d):
    try:
        return json.load(open(p, "r", encoding="utf-8"))
    except (OSError, ValueError):
        return d


def rjt(t):
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        return None


def scan(inp):
    if os.path.isfile(inp):
        sel = [("", os.path.dirname(inp), os.path.basename(inp))]
    else:
        sel = []
        for r, ds, fs in os.walk(inp):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            sel += [(os.path.relpath(os.path.join(r, f), inp).replace("\\", "/"), r, f) for f in sorted(fs)]
    out = []
    for i, (rel, r, f) in enumerate(sel, 1):
        t = rt(os.path.join(r, f))
        e = os.path.splitext(f.lower())[1]
        b = e in (".pdf", ".jpg", ".jpeg", ".docx", ".xlsx", ".pptx", ".zip", ".png") or "\x00" in t[:2000]
        out.append({"id": "M%02d" % i, "name": rel, "kind": e.lstrip(".") or "text", "chars": len(t.encode("utf-8", "replace")),
                    "parse_status": "unparsed-binary" if b else "empty-file" if not t.strip() else "placeholder-only"
                    if deg(t) else "parsed", "text": "" if b else t})
    return out


def cls(mats):
    fd = cat = ut = None
    recs = []
    for m in mats:
        if m["kind"] not in ("json", "jsonl", "ndjson", "txt") or m["parse_status"] != "parsed" or os.path.basename(m["name"]).lower() in SKIP:
            continue
        o = rjt(m["text"])
        if isinstance(o, dict):
            objs = [o] + [o[k] for k in ("material", "readings", "data") if isinstance(o.get(k), dict)]
        elif isinstance(o, list):
            objs = [{"records": o}]
        else:
            recs += [r for r in (rjt(ln) for ln in m["text"].splitlines()) if isinstance(r, dict)]
            continue
        for o in objs:
            for o in [o] + [v for v in o.values() if isinstance(v, dict)]:
                if fd is None and ("roles" in o or "synonyms" in o or "target_fields" in o):
                    fd = o
                if cat is None and isinstance(o.get("rules"), list):
                    cat = o
                if ut is None and isinstance(o.get("units"), dict):
                    ut = o
                for k in ("records", "rows", "measurements", "items"):
                    if isinstance(o.get(k), list):
                        recs += [x for x in o[k] if isinstance(x, dict)]
    return fd, cat, ut, recs


def ui(tok, ut):
    t = unicodedata.normalize("NFKC", str(tok)).strip().replace("µ", "u").replace("μ", "u")
    if not t:
        return "missing", None
    flat = " ".join(t.split())
    ut = ut or {}
    if flat.lower() in {nm(x) for x in ut.get("unknown_tokens") or []}:
        return "unknown", None
    if flat.lower() in {nm(x) for x in ut.get("ambiguous_tokens") or []}:
        return "ambiguous", None
    t = ut.get("extra_aliases", {}).get(flat, flat)
    u = ut.get("units") or {}
    if t in u:
        return "ok", [t, u[t]]
    for k, v in u.items():
        if t.lower() == k.lower() or flat.lower() in {nm(a) for a in v.get("aliases") or []}:
            return "ok", [k, v]
    pre = ut.get("prefixes") or {}
    for p in sorted(pre, key=len, reverse=True):
        if t.startswith(p) and t[len(p):] in u and t not in u:
            b = u[t[len(p):]]
            return "ok", [t, {"dim": b.get("dim") or {}, "scale": b.get("scale", 1.0) * pre[p], "offset": (b.get("offset") or 0.0) * pre[p]}]
    return "unknown", None


def cvt(v, s, d):
    if dk(s.get("dim")) != dk(d.get("dim")):
        return None
    f = s.get("scale", 1.0) / d.get("scale", 1.0)
    o = ((s.get("offset") or 0.0) - (d.get("offset") or 0.0)) / d.get("scale", 1.0)
    return round(v * f + o, 10), round(f, 10), round(o, 10)


def ex(t):
    t = re.sub(r"([0-9.])\s*[xX×✕]\s*10\s*\^?\s*([+-]?\d+)", r"\1e\2", str(t))
    t = re.sub(r"(?<=\d)\s*[eE]\s*([+-]?\d)", r"e\1", t)
    return re.sub(r"(?<=\d)\s*10\s*\^\s*([+-]?\d+)", r"e\1", t).replace(" ", "")


def nu(t):
    t = ex(t)
    if not NR.match(t):
        return None
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def pc(c, miss):
    t = "" if c is None else str(c).strip()
    if t == "" or nm(t) in miss:
        return {"kind": "missing"}
    if re.search(r"[（(]\s*(?:sd|stdev|std|σ|sigma)\s*=", t, re.I):
        return {"kind": "text"}
    body, err = t, None
    for sep in ("±", "+/-"):
        if sep in body:
            body, _, e = body.partition(sep)
            err = nu(e.strip())
            if err is None:
                return {"kind": "text"}
            break
    parts = [p for p in RSEP.split(body) if p.strip()]
    if len(parts) == 2 and nu(parts[0]) is not None and nu(parts[1]) is not None:
        return {"kind": "range", "low": nu(parts[0]), "high": nu(parts[1]), "err": err}
    m = re.match(r"^\s*(-?[\d][\d.,eE+-]*)\s*-\s*([\d][\d.,eE+-]*)\s*$", body)
    if m and nu(m.group(1)) is not None and nu(m.group(2)) is not None:
        return {"kind": "range", "low": nu(m.group(1)), "high": nu(m.group(2)), "err": err}
    v = nu(body)
    if v is None:
        return {"kind": "text"}
    m = re.search(r"\.(\d+)", ex(body))
    return {"kind": "err" if err is not None else "number", "value": v, "err": err, "decimals": len(m.group(1)) if m else 0}


def ro(col, ridx):
    n = nm(col)
    if n in ridx:
        return ridx[n], None
    m = re.match(r"^(.*?)[\s_]*[\(\[]\s*([^\)\]]+)\s*[\)\]]$", str(col))
    if m and m.group(2):
        return None, (m.group(1).strip(), m.group(2).strip())
    for tok, role in ridx.items():
        if tok and re.search(r"(?:^|[\s_\-(\[/])" + re.escape(tok) + r"(?:$|[\s_\-)\]/])", n):
            return role, None
    return None, None


def pn(r, f, rc, rs, sa, l):
    return {"r": r, "f": f, "rc": rc, "rs": rs, "sa": sa, "l": l}


def cr(recs, fd, cat, ut):
    ridx = {nm(t): r for r, ts in ((fd or {}).get("roles") or {}).items() for t in ts}
    miss = {nm(x) for x in ((fd or {}).get("missing_tokens") or [])} | MISS
    syn = (fd or {}).get("synonyms") or {}
    tol = (cat or {}).get("tolerance", {}).get("replicate_relative_spread", .05)
    rows, ch, pd, unm, used, seen = [], [], [], [], {}, {}
    for i, rec in enumerate(recs):
        rmap, conds, hdr = {}, [], {}
        for c in rec:
            r, sp = ro(c, ridx)
            if r:
                rmap[c] = r
            elif sp:
                r2 = ro(sp[0], ridx)[0]
                if r2:
                    rmap[c] = r2
                else:
                    conds.append(c)
                hdr[c] = sp[1]
            else:
                conds.append(c)
                if c not in unm:
                    unm.append(c)
        g = lambda role: next((rec[c] for c, x in rmap.items() if x == role), None)
        rid, note, rules = str(g("row_id") or "").strip(), [], []
        if not rid:
            rid = "derived-%d" % (i + 1)
            rules.append("R002")
            note.append("derived identifier (the source row carried no id)")
        else:
            rules.append("R001")
        b = rid.split("#")[0]
        seen[b] = seen.get(b, 0) + 1
        if seen[b] > 1:
            rid = "%s#%d" % (b, seen[b])
            rules.append("R002")
            note.append("duplicate identifier; a #k suffix was appended")
        loc = str(g("source_locator") or "")
        iraw, mraw = g("indicator") or "", g("material") or ""
        ind, mat = iraw, mraw
        for role in ("indicator", "material"):
            v = iraw if role == "indicator" else mraw
            t = (syn.get(role) or {}).get(nm(v)) if v else None
            if t and nm(t) != nm(v):
                ind, mat = (t, mat) if role == "indicator" else (ind, t)
                if "R014" not in rules:
                    rules.append("R014")
                ch.append({"r": rid, "f": role, "t": "synonym", "ov": v, "b": v, "a": t, "id": "R014",
                           "fm": "synonym_table: %s -> %s" % (v, t), "l": loc})
        vc = g("value")
        vc = g("value_low") if vc is None else vc
        uc = g("unit") or next((hdr[c] for c in rec if c in hdr and rmap.get(c) in ("value", "indicator")), "")
        fld = nm(ind) if ind else ""
        cond = "; ".join("%s=%s" % (c, rec[c]) for c in conds if str(rec[c] or "").strip())
        p, val, lo, hi, err, u, uni, s = pc(vc, miss), None, None, None, None, None, "", "ok"
        if p["kind"] == "missing":
            s = "missing"
            rules.append("R008")
            pd.append(pn(rid, fld, "missing_value", "the value cell is empty or holds a missing marker",
                         "confirm the measurement is genuinely absent in the source", loc))
        elif p["kind"] == "text":
            s = "needs_review"
            rules.append("R006")
            pd.append(pn(rid, fld, "unparsed_value", "the value cell is not a plain number",
                         "read the source cell and enter the value by hand", loc))
        else:
            if p["kind"] == "range":
                lo, hi, err = p["low"], p["high"], p.get("err")
                rules.append("R007")
            else:
                val, err = p["value"], p.get("err")
                if p["kind"] == "err":
                    rules.append("R009")
                if not NR.match(ex(str(vc).strip().split("±")[0].strip())):
                    rules.append("R005")
            uv = str(uc or "").strip()
            kind, info = ui(uv, ut) if uv else ("missing", None)
            if kind != "ok":
                s = "needs_review"
                rules.append("R013" if kind == "missing" else "R012")
                pd.append(pn(rid, fld, "missing_unit" if kind == "missing" else kind + "_unit",
                             "a numeric value carries no unit in the row or the header" if kind == "missing"
                             else "the unit %r could not be resolved to one dimension" % uv,
                             "supply the unit definition, state the basis, or correct the cell", loc))
                val = lo = hi = err = None
            else:
                uni, u = info[0], info[1]
                k = (fld, dk(u.get("dim")))
                used.setdefault(k, {})
                used[k][uni] = used[k].get(uni, 0) + 1
        rows.append({"r": rid, "s": str(g("source_document_id") or ""), "l": loc, "f": fld, "i": iraw, "m": mat,
                     "c": cond, "v": val, "lo": lo, "hi": hi, "e": err, "u": uni, "st": s, "nt": note, "ru": rules,
                     "ov": "" if vc is None else str(vc), "ou": str(uc or ""), "ui": u, "d": p.get("decimals", 0)})
    tgt = {k: max(v, key=v.get) for k, v in used.items()}
    for r in rows:
        if r["st"] != "ok" or not r["u"]:
            continue
        u = r["ui"] or {}
        t = tgt.get((r["f"], dk(u.get("dim"))))
        if not t or t == r["u"]:
            continue
        ti = ui(t, ut)[1][1]
        if ti is None or dk(u.get("dim")) != dk(ti.get("dim")):
            r["st"] = "needs_review"
            r["ru"].append("R020")
            pd.append(pn(r["r"], r["f"], "dim_mismatch", "source %s and target %s differ in dimension" % (r["u"], t),
                         "a molar mass or an explicit basis is required", r["l"]))
            r["v"] = r["lo"] = r["hi"] = r["e"] = None
            continue
        for k in ("v", "lo", "hi", "e"):
            if r.get(k) is None:
                continue
            c = cvt(r[k], u, ti if k != "e" else {"dim": ti.get("dim"), "scale": ti.get("scale", 1.0)})
            if c is None:
                continue
            r[k] = c[0]
            ch.append({"r": r["r"], "f": FN[k], "t": "unit_conversion", "ov": r["ov"], "ou": r["u"], "b": r["ov"],
                       "fa": c[1], "of": c[2], "a": c[0], "ut": t, "p": r["d"], "id": "R011", "l": r["l"],
                       "fm": "after = before * %s + %s" % (c[1], c[2])})
        r["u"] = t
        r["ru"].append("R011")
        r["st"] = "converted"
    grp = {}
    for r in rows:
        if r["st"] in ("ok", "converted") and r["v"] is not None:
            grp.setdefault("%s|%s|%s|%s" % (r["s"], r["c"], r["f"], r["m"]), []).append(r)
    for k, g in grp.items():
        for x in g:
            x["jk"] = k
        if len(g) < 2:
            continue
        vs = [x["v"] for x in g]
        sp = (max(vs) - min(vs)) / (abs(sum(vs) / len(vs)) or 1)
        if max(vs) == min(vs):
            for x in g[1:]:
                x["st"], x["du"] = "merged_duplicate", g[0]["r"]
                x["ru"].append("R016")
                x["nt"].append("identical judgment key and value as %s" % g[0]["r"])
        elif sp <= tol:
            for x in g:
                x["st"] = "replicate"
                x["ru"].append("R017")
                x["nt"].append("replicate within %.0f%% of the group mean; kept, not averaged" % (tol * 100))
        else:
            for x in g:
                x["st"] = "conflict"
                x["ru"].append("R018")
                pd.append(pn(x["r"], x["f"], "value_conflict",
                             "same judgment key, values spread %.1f%% beyond the tolerance" % (sp * 100),
                             "adjudicate against the source; both values are kept", x["l"]))
    return rows, ch, pd, unm
