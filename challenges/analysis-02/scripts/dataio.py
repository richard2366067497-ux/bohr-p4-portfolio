import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import zlib

MAX_BYTES = 500000
TEXT_EXT = ("md", "txt", "rst", "tex", "log")
SKIP_EXT = ("png", "jpg", "jpeg", "gif", "zip", "gz", "docx", "xlsx", "pptx", "pdf", "pyc")
SKIP_NAMES = ("case.json", "task.md", "challenge.json", "config.json", "resources.yaml")
UNIT_RE = re.compile(r"(?:\[([^\]]{1,16})\]|\(([^)]{1,16})\)|_((?:ug|mg|g|kg|mm|cm|m|km|s|ms|min|h|"
                     r"day|year|year_old|years|%|c|k|w|j|mj|kj|n|pa|kpa|mpa|ohm|v|a|hz|dpi|rpm))$)",
                     re.I)

def rj(path, default=None):
    try:
        with open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8-sig"))
    except Exception:
        return default

def rb(path):
    with open(path, "rb") as fh:
        return fh.read()

def sha16(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]

def wj(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")

def wt(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)

def classify(name, data):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if name.lower() in SKIP_NAMES:
        return "meta", "this file carries the task or the contract, not data"
    if ext in SKIP_EXT:
        return "binary", "this file type is not a table of measurements"
    if ext in ("csv", "tsv"):
        return "table", ""
    if ext in ("db", "sqlite", "sqlite3"):
        return "sqlite", ""
    if ext == "jsonl":
        return "jsonl", ""
    if ext == "json":
        return "json", ""
    if ext in TEXT_EXT:
        return "text", ""
    if not data:
        return "binary", "the file is empty"
    if b"\x00" in data[:4096]:
        return "binary", "the file holds NUL bytes, so it is not text"
    return "text", ""

def scan_materials(inp):
    mats = []
    if not os.path.isdir(inp):
        return mats
    n = 0
    for root, dirs, files in os.walk(inp):
        dirs.sort()
        for name in sorted(files):
            n += 1
            if n > 60:
                break
            path = os.path.join(root, name)
            rel = os.path.relpath(path, inp).replace("\\", "/")
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            data = b""
            try:
                data = rb(path)
            except OSError:
                pass
            data = data[:MAX_BYTES]
            kind, why = classify(name, data)
            m = {"id": "M%02d" % (len(mats) + 1), "rel": rel, "path": path, "kind": kind, "bytes": size,
                 "read_bytes": len(data), "truncated": size > MAX_BYTES, "sha256_16": sha16(data),
                 "status": "indexed", "reason": why, "note_bytes": 0}
            if kind == "meta":
                m["status"] = "not-data"
            elif size == 0:
                m["status"] = "empty-file"
                m["reason"] = "the file is 0 bytes"
            elif kind == "binary":
                m["status"] = "unparsed-binary"
            elif kind == "json":
                obj = None
                try:
                    obj = json.loads(data.decode("utf-8-sig"))
                    m["status"] = "loaded"
                except Exception as exc:
                    m["status"] = "invalid-json"
                    m["reason"] = "the file is not valid JSON (%s)" % str(exc)[:60]
                m["_json"] = obj
            elif kind == "text":
                txt = data.decode("utf-8", "replace").strip()
                m["note_bytes"] = len(txt)
                if not txt:
                    m["status"] = "empty-file"
                    m["reason"] = "the file holds no text"
                elif len(txt) < 40 and re.fullmatch(r"\[?[\s\w一-鿿]{1,12}\]?", txt):
                    m["status"] = "note-only"
                    m["reason"] = "the file holds only a short note, not a measurement table"
                else:
                    m["status"] = "loaded"
                m["_text"] = txt
            else:
                m["status"] = "loaded"
            mats.append(m)
    return mats

def coerce(v):
    if isinstance(v, bool):
        return None, "text"
    if isinstance(v, (int, float)):
        return float(v), "number"
    s = str(v).strip()
    if s == "":
        return None, "missing"
    s2 = s.replace(",", "") if re.fullmatch(r"-?[\d,]+(\.\d+)?", s) else s
    try:
        return float(s2), "number"
    except ValueError:
        return s, "text"

def looks_date(s):
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?", str(s).strip()))

def table_from_rows(cols, rows, source):
    columns = []
    for c in cols:
        vals = [r.get(c) for r in rows]
        kinds, nums = [], []
        for v in vals:
            num, k = coerce(v)
            kinds.append(k)
            if k == "number":
                nums.append(num)
        n_num = kinds.count("number")
        n_date = sum(1 for v in vals if looks_date(v))
        if n_num and n_num >= max(1, int(0.7 * (len(vals) - kinds.count("missing")) or 1)):
            ctype = "number"
        elif n_date and n_date >= 0.7 * max(1, len(vals)):
            ctype = "date"
        else:
            ctype = "text"
        m = UNIT_RE.search(str(c))
        unit = (m.group(1) or m.group(2) or m.group(3)) if m else ""
        columns.append({"name": c, "type": ctype, "unit": unit, "n": len(vals),
                        "missing": kinds.count("missing"), "n_number": n_num,
                        "distinct": len({str(v) for v in vals if coerce(v)[1] != "missing"})})
    return {"source": source, "columns": columns, "rows": rows, "n_rows": len(rows)}

def load_csv(path, delim=None, source=None):
    raw = rb(path)[:MAX_BYTES].decode("utf-8-sig", "replace")
    lines = [l for l in raw.splitlines() if l.strip()]
    if not lines:
        return None, "the file has no rows"
    if delim is None:
        try:
            delim = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t|").delimiter
        except Exception:
            delim = "\t" if lines[0].count("\t") > lines[0].count(",") else ","
    rows = list(csv.DictReader(lines, delimiter=delim))
    if not rows:
        return None, "the header row was found but no data row followed"
    return table_from_rows(list(rows[0].keys()), rows, source or os.path.basename(path)), ""

def json_rows(obj):
    best = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            dicts = [x for x in cur if isinstance(x, dict)]
            if len(dicts) > len(best):
                best = dicts
            for x in cur:
                if isinstance(x, (list, dict)):
                    stack.append(x)
        elif isinstance(cur, dict):
            for v in cur.values():
                if isinstance(v, (list, dict)):
                    stack.append(v)
    return best

def load_json(path, source=None):
    obj = rj(path)
    if obj is None:
        return None, "the file is not valid JSON"
    rows = json_rows(obj)
    if not rows:
        return None, "no list of records was found inside this JSON document"
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    return table_from_rows(cols, rows, source or os.path.basename(path)), ""

def load_sqlite(path, source=None):
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path.replace("?", "%3f"), uri=True)
    except Exception as exc:
        return None, "the database could not be opened (%s)" % str(exc)[:60]
    try:
        cur = con.cursor()
        tabs = [r[0] for r in cur.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' "
            "order by name").fetchall()]
        best, best_n = None, -1
        for t in tabs:
            try:
                n = cur.execute('select count(*) from "%s"' % t).fetchone()[0]
            except Exception:
                continue
            if n > best_n:
                best, best_n = t, n
        if best is None:
            return None, "the database holds no user table"
        cur.execute('select * from "%s"' % best)
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        ds = table_from_rows(names, rows, "%s:%s" % (source or os.path.basename(path), best))
        ds["tables"] = tabs
        ds["table"] = best
        return ds, ""
    except Exception as exc:
        return None, "the database query failed (%s)" % str(exc)[:60]
    finally:
        con.close()

def load_primary(mats):
    notes, best, best_key = [], None, None
    for m in mats:
        if m["status"] != "loaded":
            if m["kind"] in ("table", "json", "sqlite", "jsonl", "text"):
                notes.append("%s was not used as a table: %s" % (m["rel"], m["reason"] or m["status"]))
            continue
        ds, why = None, ""
        if m["kind"] == "table":
            ds, why = load_csv(m["path"], source=m["rel"])
        elif m["kind"] in ("json", "jsonl"):
            ds, why = load_json(m["path"], source=m["rel"])
        elif m["kind"] == "sqlite":
            ds, why = load_sqlite(m["path"], source=m["rel"])
        if ds is None:
            if why:
                notes.append("%s: %s" % (m["rel"], why))
            continue
        num = sum(1 for c in ds["columns"] if c["type"] == "number")
        key = (num, ds["n_rows"])
        if num >= 1 and (best_key is None or key > best_key):
            best, best_key = ds, key
    return best, notes

def outlier_bounds(vals, rule):
    s = sorted(vals)
    if rule == "z3":
        m = sum(vals) / float(len(vals))
        sd = (sum((x - m) ** 2 for x in vals) / float(len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
        return m - 3.0 * sd, m + 3.0 * sd, "mean minus/plus 3 sample standard deviations"
    if len(s) < 4:
        return None, None, "fewer than four values, so no quartile rule is applied"
    def q(p):
        pos = (len(s) - 1) * p
        lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)
    iqr = q(0.75) - q(0.25)
    return q(0.25) - 1.5 * iqr, q(0.75) + 1.5 * iqr, "Tukey 1.5 x IQR fences"

def clean(ds, plan):
    rows = [dict(r) for r in ds["rows"]]
    cols = [c for c in ds["columns"]]
    num_cols = [c["name"] for c in cols if c["type"] == "number"]
    rules, removed = [], 0
    mp = (plan.get("missing") or {})
    policy = mp.get("policy") or "mark_only"
    targets = mp.get("columns") or num_cols
    for c in cols:
        if c["name"] not in targets or c["missing"] == 0:
            continue
        if policy in ("listwise", "pairwise"):
            before = len(rows)
            rows = [r for r in rows if coerce(r.get(c["name"]))[1] != "missing"]
            gone = before - len(rows)
            removed += gone
            rules.append({"step": "missing_values", "column": c["name"], "policy": policy,
                          "missing_before": c["missing"], "rows_removed": gone,
                          "action": "rows with an empty cell were removed before analysis"})
        else:
            rules.append({"step": "missing_values", "column": c["name"], "policy": policy,
                          "missing_before": c["missing"], "rows_removed": 0,
                          "action": "the empty cell was kept and left out of that column's summary"})
    dp = (plan.get("duplicates") or {})
    dpol = dp.get("policy") or "flag_only"
    keys = dp.get("keys") or [c["name"] for c in cols]
    if dpol != "keep":
        seen, dup = set(), 0
        keep = []
        for r in rows:
            k = tuple(str(r.get(x)) for x in keys)
            if k in seen:
                dup += 1
                if dpol == "drop_exact":
                    continue
            else:
                seen.add(k)
            keep.append(r)
        if dpol == "drop_exact":
            removed += dup
            rows = keep
        rules.append({"step": "duplicate_records", "keys": keys, "policy": dpol, "found": dup,
                      "rows_removed": dup if dpol == "drop_exact" else 0,
                      "action": ("exact repeats were dropped, so the sample size is the count of distinct "
                                 "records" if dpol == "drop_exact"
                                 else "repeats were flagged and kept, so the sample size still counts them")})
    op = (plan.get("outliers") or {})
    opol = op.get("policy") or "flag"
    rule = op.get("rule") or "tukey_1.5iqr"
    for cname in (op.get("columns") or num_cols):
        vals = [coerce(r.get(cname))[0] for r in rows if coerce(r.get(cname))[1] == "number"]
        if len(vals) < 4:
            continue
        lo, hi, why = outlier_bounds(vals, rule)
        if lo is None:
            continue
        hits = [i for i, r in enumerate(rows)
                if coerce(r.get(cname))[1] == "number" and not (lo <= coerce(r.get(cname))[0] <= hi)]
        if not hits:
            rules.append({"step": "outliers", "column": cname, "rule": rule, "lower": lo, "upper": hi,
                          "count": 0, "rows_removed": 0, "action": "no value fell outside the fences"})
            continue
        if opol == "exclude":
            for i in sorted(hits, reverse=True):
                rows.pop(i)
            removed += len(hits)
            act = "values outside the fences were excluded from every summary"
        elif opol == "winsorize":
            for i in hits:
                v = coerce(rows[i].get(cname))[0]
                rows[i][cname] = lo if v < lo else hi
            act = "values outside the fences were pulled to the fence"
        else:
            act = "values outside the fences were flagged and kept in the analysis"
        rules.append({"step": "outliers", "column": cname, "rule": rule, "lower": lo, "upper": hi,
                      "count": len(hits), "rows_removed": len(hits) if opol == "exclude" else 0,
                      "action": act, "fences_from": why})
    return rows, rules, removed

def column_values(rows, name):
    out = []
    for r in rows:
        v, k = coerce(r.get(name))
        if k == "number":
            out.append(v)
    return out

def group_values(rows, gcol, ocol):
    groups = {}
    for r in rows:
        v, k = coerce(r.get(ocol))
        if k != "number":
            continue
        g = r.get(gcol)
        g = "" if g is None else str(g).strip()
        if g == "":
            continue
        groups.setdefault(g, []).append(v)
    return dict(sorted(groups.items()))

def pair_values(rows, xcol, ycol):
    xs, ys = [], []
    for r in rows:
        a, ka = coerce(r.get(xcol))
        b, kb = coerce(r.get(ycol))
        if ka == "number" and kb == "number":
            xs.append(a)
            ys.append(b)
    return xs, ys

def snapshot(mats, out):
    rows = []
    for m in mats:
        dest = "raw_snapshot/%03d_%s.bin" % (int(m["id"][1:]), os.path.basename(m["rel"]))
        try:
            data = rb(m["path"]) if os.path.isfile(m["path"]) else b""
        except OSError:
            data = b""
        p = os.path.join(out, dest.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        rows.append({"id": m["id"], "rel": m["rel"], "kind": m["kind"], "status": m["status"],
                     "bytes": m["bytes"], "sha256_16": m["sha256_16"], "snapshot": dest,
                     "snapshot_bytes": len(data), "reason": m["reason"] or "-"})
    wj(os.path.join(out, "input_manifest.json"),
       {"schema": "input-manifest/1", "materials": rows,
        "note": "raw_snapshot holds the exact input bytes; the .bin suffix marks a byte container, "
                "not a rendered image"})
    return rows

def svg_open(w, h):
    return ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            % (w, h, w, h), '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (w, h)]

def svg_text(L, x, y, s, size=11, anchor="start", color="#222222"):
    txt = (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    L.append('<text x="%.1f" y="%.1f" font-family="DejaVu Sans, Arial, sans-serif" font-size="%d" '
             'text-anchor="%s" fill="%s">%s</text>' % (x, y, size, anchor, color, txt))

def svg_line(L, x0, y0, x1, y1, color="#333333", width=1.2, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    L.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f"%s/>'
             % (x0, y0, x1, y1, color, width, d))

FW, FH = 640, 400
PALETTE = [(70, 110, 190), (200, 90, 60), (60, 140, 90), (150, 100, 180), (190, 150, 60)]

def _nice_step(span):
    for step in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100,
                 200, 500, 1000, 2000, 5000, 10000):
        if span / step <= 6:
            return step
    return span / 5.0

def _frame(scene, title, xlabel, ylabel, ymin, ymax, xs, xtitle):
    scene.append(("t", FW / 2.0, 24, title, 14, "middle"))
    if ymax <= ymin:
        ymax = ymin + 1.0
    step = _nice_step(ymax - ymin)
    y = ymin - ymin % step if ymin < 0 else ymin - (ymin % step)
    y = max(ymin, y - step * 0)
    ticks = []
    v = ymin
    while v <= ymax + 1e-9:
        ticks.append(round(v, 10))
        v += (ymax - ymin) / max(1, int(round((ymax - ymin) / step)))
        if len(ticks) > 12:
            break
    for tv in ticks:
        py = _py(tv, ymin, ymax)
        scene.append(("l", 70, py, 610, py, "#dddddd", None))
        scene.append(("t", 64, py + 4, svg_num(tv), 10, "end"))
    scene.append(("l", 70, _py(ymin, ymin, ymax), 70, _py(ymax, ymin, ymax), "#333333", None))
    scene.append(("l", 70, _py(ymin, ymin, ymax), 610, _py(ymin, ymin, ymax), "#333333", None))
    scene.append(("t", 340, 390, "%s / %s" % (xlabel, ylabel), 11, "middle"))
    for i, lab in enumerate(xs):
        scene.append(("t", _px(i, len(xs)), 368, lab, 10, "middle"))
    return ymin, ymax

def svg_num(x):
    if x is None or x != x:
        return "-"
    if x == int(x) and abs(x) < 1e6:
        return str(int(x))
    return ("%.4g" % x)

def _px(i, n):
    return 70 + (610 - 70) * ((i + 0.5) / float(max(1, n)))

def _py(v, ymin, ymax):
    return 350 - 305 * ((v - ymin) / float(ymax - ymin)) if ymax > ymin else 350

def scene_box(groups, title, ylabel, xlabel="group"):
    allv = [v for _, vs in groups for v in vs]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.1 or 1.0
    scene = []
    ymin, ymax = _frame(scene, title, xlabel, ylabel, lo - pad, hi + pad,
                        ["%s n=%d" % (g, len(vs)) for g, vs in groups], xlabel)
    for i, (g, vs) in enumerate(groups):
        s = sorted(vs)
        x = _px(i, len(groups))
        w = 34
        q1, med, q3 = _q(s, 0.25), _q(s, 0.5), _q(s, 0.75)
        lo_w, hi_w = _whisker(s, q1, q3)
        col = PALETTE[i % len(PALETTE)]
        scene.append(("l", x, _py(lo_w, ymin, ymax), x, _py(q1, ymin, ymax), "#444444", None))
        scene.append(("l", x, _py(q3, ymin, ymax), x, _py(hi_w, ymin, ymax), "#444444", None))
        scene.append(("l", x - 9, _py(hi_w, ymin, ymax), x + 9, _py(hi_w, ymin, ymax), "#444444", None))
        scene.append(("l", x - 9, _py(lo_w, ymin, ymax), x + 9, _py(lo_w, ymin, ymax), "#444444", None))
        scene.append(("r", x - w / 2.0, _py(q3, ymin, ymax), w, _py(q1, ymin, ymax) - _py(q3, ymin, ymax),
                      col, True))
        scene.append(("l", x - w / 2.0, _py(med, ymin, ymax), x + w / 2.0, _py(med, ymin, ymax),
                      "#ffffff", None))
        for v in vs:
            jitter = ((zlib.crc32(str(g).encode("utf-8")) + int(abs(v) * 1000)) % 17) - 8
            scene.append(("p", x + jitter, _py(v, ymin, ymax), "#222222"))
    return scene

def _q(s, p):
    if not s:
        return float("nan")
    pos = (len(s) - 1) * p
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)

def _whisker(s, q1, q3):
    iqr = q3 - q1
    inner = [v for v in s if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]
    return (min(inner), max(inner)) if inner else (q1, q3)

def scene_scatter(xs, ys, slope, intercept, title, xlabel, ylabel):
    lo, hi = min(xs), max(xs)
    pad = (hi - lo) * 0.08 or 1.0
    ylo, yhi = min(ys), max(ys)
    ypad = (yhi - ylo) * 0.1 or 1.0
    scene = []
    ymin, ymax = _frame(scene, title, xlabel, ylabel, ylo - ypad, yhi + ypad,
                        [_f(lo), _f((lo + hi) / 2.0), _f(hi)], xlabel)
    xa, xb = lo - pad, hi + pad
    scene.append(("l", _sx(xa, lo, hi), _py(intercept + slope * xa, ymin, ymax),
                  _sx(xb, lo, hi), _py(intercept + slope * xb, ymin, ymax), (200, 90, 60), None))
    for a, b in zip(xs, ys):
        scene.append(("p", _sx(a, lo, hi), _py(b, ymin, ymax), (70, 110, 190)))
    return scene

def _f(x):
    return svg_num(x)

def _sx(v, lo, hi):
    return 90 + (600 - 90) * ((v - lo) / float(hi - lo)) if hi > lo else 345

def scene_bars(labels, values, title, ylabel, xlabel="level"):
    hi = max(values + [0.0])
    scene = []
    ymin, ymax = _frame(scene, title, xlabel, ylabel, 0.0, hi * 1.15 or 1.0, labels, xlabel)
    for i, v in enumerate(values):
        x = _px(i, len(labels))
        scene.append(("r", x - 26, _py(v, ymin, ymax), 52, _py(0, ymin, ymax) - _py(v, ymin, ymax),
                      PALETTE[i % len(PALETTE)], True))
        scene.append(("t", x, _py(v, ymin, ymax) - 6, svg_num(v), 10, "middle"))
    return scene

def scene_svg(scene, w=FW, h=FH):
    L = svg_open(w, h)
    for p in scene:
        if p[0] == "r":
            L.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                     % (p[1], p[2], p[3], p[4], _col(p[5])))
        elif p[0] == "l":
            svg_line(L, p[1], p[2], p[3], p[4], p[5], 1.2, p[6])
        elif p[0] == "t":
            svg_text(L, p[1], p[2], p[3], p[4], p[5])
        elif p[0] == "p":
            L.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (p[1], p[2], _col(p[3])))
    L.append("</svg>")
    return "\n".join(L) + "\n"

def _col(c):
    if isinstance(c, str):
        return c
    return "#%02x%02x%02x" % c

def render(scene, path, w=FW, h=FH):
    wt(path, scene_svg(scene, w, h))
    return path
