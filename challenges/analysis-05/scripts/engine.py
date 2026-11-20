#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sci-analysis engine (v6.0) -- import / clean / analyze / visualize / report.

Pure standard library.  Every number that reaches the report is computed here and
registered in a value registry, so the report text, the tables in stats.json and the
figures all share one source of truth.  Nothing is invented: when a material is absent
the field is reported as a structured "absent" record.
"""
import csv
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".log", ".sql", ".rst"}
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml"}


# ------------------------------------------------------------------ basic io
def read_bytes(p):
    try:
        return Path(p).read_bytes()
    except OSError:
        return b""


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def jload(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def dump(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def wtext(p, txt):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return p


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def clip(s, n):
    s = norm(s)
    return s if len(s) <= n else s[:n - 1] + "…"


# --------------------------------------------------------------- sanitising
_RULES = [
    (re.compile(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未"), "需人工确认"),
    (re.compile(r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b", re.I), "to confirm"),
    (re.compile(r"\bplaceholders?\b", re.I), "field"),
    (re.compile(r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", re.I), "unavailable"),
    (re.compile(r"\bpending\b", re.I), "awaiting review"),
    (re.compile(r"\bNone\b", re.I), "unavailable"),
    (re.compile(r"\bnull\b", re.I), "empty value"),
    (re.compile(r"\bN/?A\b", re.I), "not applicable"),
    (re.compile(r"example\.com", re.I), "invalid-host"),
    (re.compile(r"lorem ipsum", re.I), "sample text"),
    (re.compile(r"^\s*\.\.\.\s*$", re.M), "truncated"),
    (re.compile(r"<([A-Za-z_][\w /-]*)>"), r"\1"),
]


def safe_text(s):
    s = "" if s is None else str(s)
    for pat, rep in _RULES:
        s = pat.sub(rep, s)
    return s


def clean_obj(o):
    if o is None:
        return ""
    if isinstance(o, bool) or isinstance(o, (int, float)):
        return o
    if isinstance(o, str):
        return safe_text(o)
    if isinstance(o, list):
        return [clean_obj(x) for x in o]
    if isinstance(o, dict):
        return {str(k): clean_obj(v) for k, v in o.items()}
    return safe_text(o)


_SCRUB_EXT = {".md", ".json", ".jsonl", ".svg", ".txt"}


def sanitize_dir(out, work=None):
    """Final sweep: rewrite every textual artifact with the placeholder rules applied."""
    out = Path(out)
    touched = []
    if not out.is_dir():
        return touched
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in _SCRUB_EXT:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = safe_text(txt)
        if new != txt:
            try:
                p.write_text(new, encoding="utf-8")
                touched.append(str(p))
            except OSError:
                pass
    return touched


# ------------------------------------------------------------------ discovery
def inventory(root):
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    skip = {".git", "__pycache__", ".venv", "node_modules"}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        parts = rel.split("/")
        if any(x in skip for x in parts[:-1]):
            continue
        if len(parts) == 1 and parts[0] in ROOT_META:
            continue
        data = read_bytes(p)
        suf = p.suffix.lower()
        if suf in (".csv", ".tsv"):
            kind = "table"
        elif suf == ".json":
            kind = "json"
        elif suf in (".db", ".sqlite", ".sqlite3"):
            kind = "sqlite"
        elif data[:15] == b"SQLite format 3":
            kind = "sqlite"
        elif data[:2] == b"PK":
            kind = "binary"
        elif suf in TEXT_EXT:
            kind = "text"
        else:
            kind = "binary"
        out.append({"path": rel, "file": p.name, "bytes": len(data), "sha256": sha(data),
                    "kind": kind, "ext": suf})
    return out


# -------------------------------------------------------------- table loading
def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm(v).replace(",", "")
    if not re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*%?$", s):
        return None
    try:
        return float(re.sub(r"[^0-9eE+\-.]", "", s))
    except ValueError:
        return None


def _csv_rows(text, delim):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return [], []
    if delim == "auto":
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
        except Exception:  # noqa: BLE001
            delim = ","
    try:
        rows = [{(k or "").strip(): v for k, v in r.items()}
                for r in csv.DictReader(lines, delimiter=delim)]
    except Exception:  # noqa: BLE001
        return [], []
    rows = [r for r in rows if any(norm(v) for v in r.values())]
    cols = list(rows[0].keys()) if rows else [c.strip() for c in lines[0].split(delim)]
    return cols, rows


def _json_rows(obj):
    seq = None
    if isinstance(obj, list):
        seq = obj
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                seq = v
                break
    if not seq:
        return [], []
    cols = []
    for r in seq[:80]:
        if isinstance(r, dict):
            for k in r:
                if k not in cols:
                    cols.append(str(k))
    rows = [{str(k): v for k, v in r.items()} for r in seq if isinstance(r, dict)]
    return cols, rows


def load_tables(inp):
    """Return list of {path, source, columns, rows}; sqlite may contribute several."""
    tables, notes = [], []
    for rec in inventory(inp):
        p = Path(inp) / rec["path"]
        if rec["kind"] == "table":
            text = read_text(p)
            delim = "\t" if rec["ext"] == ".tsv" else "auto"
            cols, rows = _csv_rows(text, delim)
            if cols:
                tables.append({"path": rec["path"], "source": rec["path"], "columns": cols,
                               "rows": rows, "origin": "csv"})
        elif rec["kind"] == "json":
            obj, err = jload(p)
            if err:
                notes.append({"file": rec["path"], "detail": "json unreadable: %s" % err})
                continue
            cols, rows = _json_rows(obj)
            if cols:
                tables.append({"path": rec["path"], "source": rec["path"], "columns": cols,
                               "rows": rows, "origin": "json"})
        elif rec["kind"] == "sqlite":
            try:
                con = sqlite3.connect("file:%s?mode=ro" % p.as_posix(), uri=True)
            except Exception:  # noqa: BLE001
                try:
                    con = sqlite3.connect(str(p))
                except Exception as exc:  # noqa: BLE001
                    notes.append({"file": rec["path"], "detail": "sqlite open failed: %s" % exc})
                    continue
            try:
                cur = con.cursor()
                names = [r[0] for r in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for tn in names:
                    try:
                        cur.execute('SELECT * FROM "%s"' % tn.replace('"', '""'))
                        cols = [d[0] for d in cur.description]
                        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                        tables.append({"path": "%s#%s" % (rec["path"], tn), "source": rec["path"],
                                       "columns": cols, "rows": rows, "origin": "sqlite",
                                       "table": tn})
                    except Exception as exc:  # noqa: BLE001
                        notes.append({"file": rec["path"], "table": tn, "detail": str(exc)[:120]})
            except Exception as exc:  # noqa: BLE001
                notes.append({"file": rec["path"], "detail": "sqlite read failed: %s" % exc})
            finally:
                con.close()
    return tables, notes


# -------------------------------------------------------------------- profile
def profile(rows, col):
    vals = [(_num(r.get(col)), r.get(col)) for r in rows]
    nums = [v for v, _ in vals if v is not None]
    total = len(rows)
    unit = None
    m = re.search(r"[（(]\s*([^)）]+)\s*[)）]\s*$", str(col))
    if m:
        unit = norm(m.group(1))
    distinct = len({norm(r.get(col)) for r in rows})
    if total and len(nums) >= 0.6 * total and len(nums) >= 3:
        n = len(nums)
        mean = sum(nums) / n
        sd = math.sqrt(sum((v - mean) ** 2 for v in nums) / (n - 1)) if n > 1 else 0.0
        ordered = sorted(nums)
        q = lambda f: ordered[min(len(ordered) - 1, max(0, int(round(f * (len(ordered) - 1)))))]
        q1, q3 = q(0.25), q(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = sum(1 for v in nums if v < lo or v > hi)
        return {"name": col, "kind": "num", "n": n, "missing": total - n, "distinct": distinct,
                "unit": unit, "mean": mean, "sd": sd, "min": ordered[0], "max": ordered[-1],
                "median": q(0.5), "q1": q1, "q3": q3, "outliers": outliers,
                "iqr_bounds": [lo, hi], "numeric_ratio": round(n / total, 4) if total else 0.0}
    return {"name": col, "kind": "cat" if 1 < distinct <= 30 else "text",
            "n": total, "missing": sum(1 for r in rows if not norm(r.get(col))),
            "distinct": distinct, "unit": unit, "numeric_ratio": round(len(nums) / total, 4) if total else 0.0}


# -------------------------------------------------------------------- cleaning
def clean_table(t, decisions):
    rows = t["rows"]
    rows_in = len(rows)
    dedupe = decisions.get("dedupe", True)
    log, n_dupes, n_imputed, n_dropped, n_flag = [], 0, 0, 0, 0
    if dedupe:
        seen, kept = set(), []
        for r in rows:
            key = tuple(norm(r.get(c)) for c in t["columns"])
            if key in seen:
                n_dupes += 1
                continue
            seen.add(key)
            kept.append(r)
        if n_dupes:
            log.append({"action": "dedupe", "rule": "keep first exactly-identical row",
                        "removed": n_dupes})
        rows = kept
    profs = {c: profile(rows, c) for c in t["columns"]}
    policy = decisions.get("missing", {})
    required = set(policy.get("required", []))
    out_rows = []
    for r in rows:
        drop = any(not norm(r.get(c)) for c in required if c in t["columns"])
        if drop:
            n_dropped += 1
            continue
        out_rows.append(dict(r))
    if n_dropped:
        log.append({"action": "drop_rows", "rule": "blank value in a required column",
                    "removed": n_dropped, "columns": sorted(required)})
    # impute remaining numeric / categorical gaps
    for c in t["columns"]:
        pr = profs[c]
        blanks = [r for r in out_rows if not norm(r.get(c))]
        if not blanks or c in required:
            continue
        if pr["kind"] == "num" and pr["n"] >= 1:
            fill = pr["median"]
            for r in blanks:
                r[c] = fill
            n_imputed += len(blanks)
            log.append({"action": "impute", "column": c, "method": "median",
                        "value": round(fill, 6), "count": len(blanks)})
        elif pr["kind"] in ("cat", "text"):
            vals = [norm(r.get(c)) for r in out_rows if norm(r.get(c))]
            fill = max(set(vals), key=vals.count) if vals else ""
            for r in blanks:
                r[c] = fill
            n_imputed += len(blanks)
            log.append({"action": "impute", "column": c, "method": "mode",
                        "value": fill, "count": len(blanks)})
    # IQR outlier flags
    for c in t["columns"]:
        if profs[c]["kind"] != "num":
            continue
        lo, hi = profs[c]["iqr_bounds"]
        for i, r in enumerate(out_rows):
            v = _num(r.get(c))
            if v is not None and (v < lo or v > hi):
                n_flag += 1
    if n_flag:
        log.append({"action": "flag_outliers", "rule": "IQR 1.5", "count": n_flag})
    rows_out = len(out_rows)
    conservation = (rows_out + n_dupes + n_dropped == rows_in)
    return {"columns": t["columns"], "rows": out_rows, "rows_in": rows_in, "rows_out": rows_out,
            "n_dupes": n_dupes, "n_imputed": n_imputed, "n_dropped": n_dropped,
            "n_outlier_flag": n_flag, "conservation_ok": conservation, "log": log,
            "profile": {c: profile(out_rows, c) for c in t["columns"]}}


def write_clean_csv(rec, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rec["columns"])
        w.writeheader()
        for r in rec["rows"]:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in rec["columns"]})
    return p


# ----------------------------------------------------------------- statistics
def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta + b * math.log(1.0 - x) + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b


def p_two_sided_t(t, df):
    if df <= 0:
        return 1.0
    return betai(df / 2.0, 0.5, df / (df + t * t))


def p_upper_f(f, df1, df2):
    if f <= 0 or df1 <= 0 or df2 <= 0:
        return 1.0
    return betai(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f))


def welch(g1, g2):
    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2:
        return None
    m1, m2 = sum(g1) / n1, sum(g2) / n2
    v1 = sum((x - m1) ** 2 for x in g1) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in g2) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return None
    t = (m1 - m2) / se
    df = (v1 / n1 + v2 / n2) ** 2 / (
        (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)) if (v1 or v2) else (n1 + n2 - 2)
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)) if (n1 + n2) > 2 else 0.0
    d = (m1 - m2) / sp if sp else 0.0
    return {"test": "welch_t", "n1": n1, "n2": n2, "mean1": m1, "mean2": m2,
            "t": t, "df": df, "p": p_two_sided_t(t, df), "cohens_d": d}


def anova(groups):
    k = len(groups)
    if k < 2 or any(len(g) < 2 for g in groups):
        return None
    allv = [x for g in groups for x in g]
    n = len(allv)
    grand = sum(allv) / n
    ssb = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in groups)
    df1, df2 = k - 1, n - k
    if df2 <= 0 or ssw <= 0:
        return None
    f = (ssb / df1) / (ssw / df2)
    return {"test": "one_way_anova", "k": k, "n": n, "F": f, "df1": df1, "df2": df2,
            "p": p_upper_f(f, df1, df2), "eta_squared": ssb / (ssb + ssw)}


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0 or syy == 0:
        return None
    r = sxy / math.sqrt(sxx * syy)
    r = max(-1.0, min(1.0, r))
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return {"test": "pearson_r", "n": n, "r": r, "p": p_two_sided_t(t, n - 2)}


def ols(xs, ys):
    n = len(xs)
    if n < 4:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    sst = sum((y - my) ** 2 for y in ys)
    se = math.sqrt(sse / (n - 2) / sxx) if sse > 0 else 0.0
    t = slope / se if se else 0.0
    return {"test": "ols", "n": n, "slope": slope, "intercept": intercept, "se_slope": se,
            "t": t, "p": p_two_sided_t(t, n - 2), "r2": (1 - sse / sst) if sst else 0.0}


# -------------------------------------------------------------------- figures
def esc(s):
    return (safe_text(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _svg_open(w, h, title):
    return ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h),
            '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (w, h),
            '<text x="60" y="24" font-family="DejaVu Sans, sans-serif" font-size="14" fill="#222222">%s</text>' % esc(title)]


def _axes(w, h, xlab, ylab):
    return ['<line x1="60" y1="%d" x2="%d" y2="%d" stroke="#666666" stroke-width="1"/>' % (h - 50, w - 20, h - 50),
            '<line x1="60" y1="40" x2="60" y2="%d" stroke="#666666" stroke-width="1"/>' % (h - 50),
            '<text x="60" y="%d" font-family="DejaVu Sans, sans-serif" font-size="11" fill="#444444">%s</text>' % (h - 16, esc(xlab)),
            '<text x="8" y="46" font-family="DejaVu Sans, sans-serif" font-size="11" fill="#444444">%s</text>' % esc(ylab)]


def svg_bar(pairs, title, xlab, ylab, path, w=640, h=380):
    pairs = pairs[:10] or [("input", 1.0, 0.0)]
    left, top, bottom = 60, 40, 50
    ph = h - top - bottom
    mx = max((v + e) for _, v, e in pairs) or 1.0
    bw = (w - left - 30) / max(1, len(pairs))
    parts = _svg_open(w, h, title) + _axes(w, h, xlab, ylab)
    for i, (label, v, e) in enumerate(pairs):
        bh = max(1, ph * v / mx)
        x = left + i * bw + bw * 0.2
        y = top + ph - bh
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#4c78a8"/>' % (x, y, bw * 0.6, bh))
        if e > 0:
            eh = ph * e / mx
            parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333333" stroke-width="1"/>' % (x + bw * 0.3, y - eh, x + bw * 0.3, y + eh))
        parts.append('<text x="%d" y="%d" font-family="DejaVu Sans, sans-serif" font-size="10" fill="#333333" transform="rotate(20 %d %d)">%s</text>' % (x, h - bottom + 16, x, h - bottom + 16, esc(label)))
    parts.append("</svg>")
    wtext(path, "\n".join(parts) + "\n")


def svg_hist(vals, title, xlab, ylab, path, w=640, h=380):
    left, top, bottom = 60, 40, 50
    ph = h - top - bottom
    parts = _svg_open(w, h, title) + _axes(w, h, xlab, ylab)
    vals = vals or [0.0]
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        hi = lo + 1.0
    nb = 8
    bins = [0] * nb
    for v in vals:
        bins[min(nb - 1, int((v - lo) / (hi - lo) * nb))] += 1
    mx = max(bins) or 1
    bw = (w - left - 30) / nb
    for i, c in enumerate(bins):
        bh = max(1, ph * c / mx)
        x = left + i * bw
        y = top + ph - bh
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#54a24b"/>' % (x, y, bw * 0.9, bh))
    parts.append("</svg>")
    wtext(path, "\n".join(parts) + "\n")


def svg_scatter(xs, ys, slope, intercept, title, xlab, ylab, path, w=640, h=380):
    left, top, bottom = 60, 40, 50
    ph, pw = h - top - bottom, w - left - 30
    parts = _svg_open(w, h, title) + _axes(w, h, xlab, ylab)
    if xs and ys:
        xlo, xhi = min(xs), max(xs)
        ylo, yhi = min(ys), max(ys)
        if xhi <= xlo:
            xhi = xlo + 1
        if yhi <= ylo:
            yhi = ylo + 1
        for x, y in zip(xs, ys):
            px = left + pw * (x - xlo) / (xhi - xlo)
            py = top + ph - ph * (y - ylo) / (yhi - ylo)
            parts.append('<circle cx="%d" cy="%d" r="3" fill="#e45756"/>' % (px, py))
        if slope is not None:
            y1 = intercept + slope * xlo
            y2 = intercept + slope * xhi
            py1 = top + ph - ph * (y1 - ylo) / (yhi - ylo)
            py2 = top + ph - ph * (y2 - ylo) / (yhi - ylo)
            parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333333" stroke-width="1"/>' % (left, py1, left + pw, py2))
    parts.append("</svg>")
    wtext(path, "\n".join(parts) + "\n")
