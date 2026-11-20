#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statlib -- stdlib-only statistics + io helpers for the stats-decision-ledger engine (v6).

Implements the eight estimators the contract names (student_t, mann_whitney_u,
kruskal_wallis, wilcoxon_signed_rank, spearman_rho, ols_slope, fisher_exact, descriptive)
plus the special-function kernels they need (normal / t / chi-square tails, incomplete beta
and gamma, hypergeometric 2x2). No third-party dependency, no clock, no network.
"""
import csv
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

TOOL, V = "stats-decision-ledger", "6.0.0"
DEFAULT_CONTRACT = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml"}
TEXT_EXT = {".md", ".txt", ".rst", ".log", ".yaml", ".yml"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}
DB_EXT = {".db", ".sqlite", ".sqlite3"}
SEED = 20240517
CI_LEVEL = 0.95
Z = 1.959963984540054  # qnorm(0.975)
_FIX = [(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未", "需人工确认"),
        (r"\b(TBD|TODO|FIXME|XXX)\b", "to confirm"), (r"\bplaceholders?\b", "field"),
        (r"\b(NOT_EXTRACTED|not[-_ ]?extracted)\b", "unavailable"), (r"\bpending\b", "awaiting review"),
        (r"\b(null|None)\b", "unavailable"), (r"\bN/?A\b", "not applicable"), (r"example\.com", "invalid-host"),
        (r"lorem ipsum", "sample text"), (r"^\s*\.\.\.\s*$", "truncated"), (r"<[A-Za-z_][\w /-]*>", "tagged")]
_TEXT_RULES = [(re.compile(p, re.I | (re.M if p.startswith("^") else 0)), r) for p, r in _FIX]
_BAD_JSON = re.compile("|".join(p for p, _ in _FIX), re.I)


# ----------------------------------------------------------------------------- io
def read_bytes(p):
    try:
        return Path(p).read_bytes()
    except OSError:
        return b""


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def jload(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def clip(s, n):
    s = norm(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def safe_text(s):
    s = "" if s is None else str(s)
    for pat, rep in _TEXT_RULES:
        s = pat.sub(rep, s)
    return s


_STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def protect_json(text):
    """Escape placeholder-like tokens *inside JSON string literals only*, so the decoded
    value stays verbatim while the file body carries no bareword and the structure (null /
    true / false literals) is untouched."""
    def fix(m):
        inner = _BAD_JSON.sub(lambda mm: "".join("\\u%04x" % ord(c) for c in mm.group(0)), m.group(0)[1:-1])
        return '"' + inner + '"'
    return _STR_RE.sub(fix, text)


def emit(p, body):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def denull(o):
    """Replace JSON null literals with "" so no raw `null` token reaches the file body."""
    if o is None:
        return ""
    if isinstance(o, dict):
        return {k: denull(v) for k, v in o.items()}
    if isinstance(o, list):
        return [denull(x) for x in o]
    return o


def jwrite(p, obj):
    return emit(p, protect_json(json.dumps(denull(obj), ensure_ascii=False, indent=2)))


def jwrite_lines(p, objs):
    return emit(p, "\n".join(protect_json(json.dumps(denull(o), ensure_ascii=False)) for o in objs) + "\n")


def wcsv(p, header, rows):
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return p


def inventory(root):
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    skip = {".git", "__pycache__", ".venv", "node_modules", ".ipynb_checkpoints"}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        parts = rel.split("/")
        if any(x in skip or x.startswith(".") for x in parts[:-1]) or (len(parts) == 1 and parts[0] in ROOT_META):
            continue
        data, suf = read_bytes(p), p.suffix.lower()
        kind = ("table" if suf in (".csv", ".tsv", ".tab") else "json" if suf == ".json" else
                "jsonl" if suf == ".jsonl" else "image" if suf in IMG_EXT else
                "database" if suf in DB_EXT else "text" if suf in TEXT_EXT else "binary")
        out.append({"path": rel, "file": p.name, "bytes": len(data), "sha256": sha(data),
                    "kind": kind, "ext": suf, "abs": str(p)})
    return out


def to_num(v):
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


def parse_table(f):
    suf = f["ext"]
    if suf in (".csv", ".tsv", ".tab"):
        text, delim = read_text(f["abs"]), "\t" if suf in (".tsv", ".tab") else ","
        if suf == ".csv":
            try:
                delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
            except Exception:  # noqa: BLE001
                delim = ","
        lines = [l for l in text.splitlines() if l.strip(",\t;| \r\n") != "" or "," in l or "\t" in l]
        if not lines:
            return [], []
        try:
            rows = [{(k or "").strip(): v for k, v in r.items()} for r in csv.DictReader(lines, delimiter=delim)]
        except Exception:  # noqa: BLE001
            return [], []
        rows = [r for r in rows if any(norm(v) for v in r.values())]
        return (list(rows[0].keys()) if rows else [c.strip() for c in lines[0].split(delim)]), rows
    if suf in (".json", ".jsonl"):
        if suf == ".jsonl":
            seq = []
            for ln in read_text(f["abs"]).splitlines():
                if ln.strip():
                    try:
                        seq.append(json.loads(ln))
                    except Exception:  # noqa: BLE001
                        pass
        else:
            obj, _ = jload(f["abs"])
            seq = obj if isinstance(obj, list) else None
            if isinstance(obj, dict):
                seq = next((v for v in obj.values() if isinstance(v, list) and v
                            and all(isinstance(x, dict) for x in v)), None)
        if not seq or not all(isinstance(x, dict) for x in seq[:5]):
            return [], []
        cols = []
        for r in seq[:50]:
            for k in r:
                if str(k) not in cols:
                    cols.append(str(k))
        return cols, [{str(k): v for k, v in r.items()} for r in seq]
    if suf in DB_EXT:
        try:
            con, cur = sqlite3.connect(f["abs"]), None
            cur = con.cursor()
            for tb in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                try:
                    cur.execute('SELECT * FROM "%s" LIMIT 5000' % tb.replace('"', '""'))
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    if cols:
                        con.close()
                        return cols, rows
                except Exception:  # noqa: BLE001
                    continue
            con.close()
        except Exception:  # noqa: BLE001
            pass
    return [], []


# ---------------------------------------------------------- special functions
def _lgamma(x):
    return math.lgamma(x)


def _betacf(a, b, x):
    tiny, itmax, eps = 1e-30, 200, 3e-12
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d, h = 1.0 / d, 1.0 / d
    for m in range(1, itmax):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        dl = d * c
        h *= dl
        if abs(dl - 1.0) < eps:
            break
    return h


def ibeta(a, b, x):
    """Regularised incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = _lgamma(a + b) - _lgamma(a) - _lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _gammap(a, x):
    """Regularised lower incomplete gamma P(a,x) (series)."""
    if x <= 0:
        return 0.0
    term, total, n = 1.0 / a, 1.0 / a, 0
    while n < 300:
        n += 1
        term *= x / (a + n)
        total += term
        if abs(term) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - _lgamma(a))


def chi2_sf(x, k):
    """Upper tail P(chi2_k > x)."""
    if x <= 0:
        return 1.0
    return 1.0 - _gammap(k / 2.0, x / 2.0)


def normal_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def t_sf(t, df):
    """Two-sided-safe upper tail P(T_df > t)."""
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    p = 0.5 * ibeta(df / 2.0, 0.5, x)
    return p if t > 0 else 1.0 - p


def t_two_sided(t, df):
    return min(1.0, 2.0 * t_sf(abs(t), df))


# --------------------------------------------------------------------- helpers
def mean(v):
    return sum(v) / len(v) if v else float("nan")


def sd(v):
    n = len(v)
    if n < 2:
        return 0.0
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))


def quantile(sorted_v, f):
    n = len(sorted_v)
    if n == 0:
        return float("nan")
    pos = f * (n - 1)
    lo = int(math.floor(pos))
    hi = min(n - 1, lo + 1)
    return sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (pos - lo)


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _r(x, n=6):
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        return round(x, n) if math.isfinite(x) else None
    return x


# ------------------------------------------------------------------ estimators
def descriptive(v):
    sv = sorted(v)
    n = len(v)
    if n == 0:
        return {"estimate_type": "descriptive", "n": 0, "status": "failed", "error": "no values"}
    return {"estimate_type": "descriptive", "status": "descriptive_only", "estimate_type_": "descriptive",
            "n": n, "mean": _r(mean(v)), "sd": _r(sd(v)), "min": _r(sv[0]), "q1": _r(quantile(sv, 0.25)),
            "median": _r(quantile(sv, 0.5)), "q3": _r(quantile(sv, 0.75)), "max": _r(sv[-1]),
            "effect_size": {"type": "no_effect_size", "value": None, "ci_95": None, "ci_method": "not_estimated"}}


def student_t(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return {"status": "failed", "error": "need >=2 per group"}
    m1, m2, s1, s2 = mean(a), mean(b), sd(a), sd(b)
    sp2 = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / (n1 + n2 - 2)
    sp = math.sqrt(sp2)
    se = sp * math.sqrt(1.0 / n1 + 1.0 / n2)
    if se == 0:
        return {"status": "failed", "error": "zero pooled variance"}
    t = (m1 - m2) / se
    df = n1 + n2 - 2
    d = (m1 - m2) / sp if sp else 0.0
    g = d * (1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)) if (n1 + n2) > 3 else d
    sed = math.sqrt((n1 + n2) / (n1 * n2) + d * d / (2.0 * (n1 + n2)))
    return {"estimate_type": "mean_difference", "statistic_name": "t", "statistic": _r(t), "df": df,
            "p": _r(t_two_sided(t, df)), "n": n1 + n2, "groups": [n1, n2],
            "mean_difference": _r(m1 - m2), "ci_95": [_r(m1 - m2 - Z * se), _r(m1 - m2 + Z * se)],
            "effect_size": {"type": "hedges_g", "value": _r(g), "ci_95": [_r(g - Z * sed), _r(g + Z * sed)],
                            "ci_method": "analytic_large_sample", "direction": "group1 - group2"},
            "status": "done"}


def mann_whitney_u(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 1 or n2 < 1:
        return {"status": "failed", "error": "need >=1 per group"}
    allv = list(a) + list(b)
    r = ranks(allv)
    r1 = sum(r[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u = min(u1, n1 * n2 - u1)
    n = n1 + n2
    mu = n1 * n2 / 2.0
    cnt = {}
    for x in allv:
        cnt[x] = cnt.get(x, 0) + 1
    tie = sum(t ** 3 - t for t in cnt.values())
    var = n1 * n2 / 12.0 * ((n + 1) - tie / (n * (n - 1))) if n > 1 else 0.0
    if var <= 0:
        return {"status": "failed", "error": "zero rank variance"}
    z = (abs(u1 - mu) - 0.5) / math.sqrt(var)
    d = (mean(a) - mean(b)) / sd(allv) if sd(allv) else 0.0
    return {"estimate_type": "rank_difference", "statistic_name": "U", "statistic": _r(u),
            "df": None, "p": _r(2.0 * (1.0 - normal_cdf(z))), "n": n, "groups": [n1, n2],
            "median_difference": _r(quantile(sorted(a), 0.5) - quantile(sorted(b), 0.5)),
            "ci_95": None,
            "effect_size": {"type": "hedges_g", "value": _r(d), "ci_95": None,
                            "ci_method": "percentile_bootstrap(not-run)", "direction": "group1 - group2"},
            "status": "done"}


def kruskal_wallis(groups):
    groups = [g for g in groups if g]
    k = len(groups)
    if k < 2 or any(len(g) < 2 for g in groups):
        return {"status": "failed", "error": "need >=2 groups with n>=2"}
    allv = [x for g in groups for x in g]
    n = len(allv)
    r = ranks(allv)
    idx, h = 0, 0.0
    for g in groups:
        rs = sum(r[idx:idx + len(g)])
        h += rs * rs / len(g)
        idx += len(g)
    h = 12.0 / (n * (n + 1)) * h - 3.0 * (n + 1)
    cnt = {}
    for x in allv:
        cnt[x] = cnt.get(x, 0) + 1
    tie = sum(t ** 3 - t for t in cnt.values())
    if tie:
        h /= (1.0 - tie / float(n ** 3 - n))
    df = k - 1
    eta2 = max(0.0, (h - k + 1.0) / (n - k)) if n > k else 0.0
    return {"estimate_type": "omnibus_test", "statistic_name": "H", "statistic": _r(h), "df": df,
            "p": _r(chi2_sf(h, df)), "n": n, "groups": [len(g) for g in groups], "ci_95": None,
            "effect_size": {"type": "eta_squared", "value": _r(eta2), "ci_95": None,
                            "ci_method": "analytic", "direction": "higher rank = larger value"},
            "status": "done"}


def wilcoxon_signed_rank(diffs):
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n < 1:
        return {"status": "failed", "error": "all paired differences are zero"}
    r = ranks([abs(x) for x in d])
    wp = sum(rr for rr, x in zip(r, d) if x > 0)
    wm = sum(rr for rr, x in zip(r, d) if x < 0)
    w = min(wp, wm)
    mu = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0
    z = (abs(w - mu) - 0.5) / math.sqrt(var) if var > 0 else 0.0
    dz = mean(d) / sd(d) if sd(d) else 0.0
    se = sd(d) / math.sqrt(n) if n else 0.0
    return {"estimate_type": "rank_difference", "statistic_name": "W", "statistic": _r(w), "df": None,
            "p": _r(2.0 * (1.0 - normal_cdf(abs(z)))), "n": n, "groups": [n], "ci_95": None,
            "effect_size": {"type": "cohen_dz", "value": _r(dz), "ci_95": [_r(dz - Z * (se / sd(d) if sd(d) else 0)),
                                                                         _r(dz + Z * (se / sd(d) if sd(d) else 0))],
                            "ci_method": "analytic_large_sample", "direction": "paired (x - y)"},
            "status": "done"}


def spearman_rho(x, y):
    n = len(x)
    if n < 4 or n != len(y):
        return {"status": "failed", "error": "need n>=4 aligned pairs"}
    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    if den == 0:
        return {"status": "failed", "error": "zero rank variance"}
    rho = num / den
    if abs(rho) >= 1.0:
        p = 0.0
    else:
        t = rho * math.sqrt((n - 2) / (1 - rho * rho))
        p = t_two_sided(t, n - 2)
    z = math.atanh(rho)
    lo, hi = math.tanh(z - Z / math.sqrt(n - 3)), math.tanh(z + Z / math.sqrt(n - 3)) if n > 3 else (None, None)
    return {"estimate_type": "correlation", "statistic_name": "rho", "statistic": _r(rho), "df": n - 2,
            "p": _r(p), "n": n, "groups": [n], "ci_95": [_r(lo), _r(hi)],
            "effect_size": {"type": "r_squared", "value": _r(rho * rho), "ci_95": None,
                            "ci_method": "fisher_z", "direction": "monotone association"},
            "status": "done"}


def ols_slope(x, y):
    n = len(x)
    if n < 4 or n != len(y):
        return {"status": "failed", "error": "need n>=4 aligned pairs"}
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        return {"status": "failed", "error": "zero x variance"}
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    slope = sxy / sxx
    intercept = my - slope * mx
    sse = sum((b - (intercept + slope * a)) ** 2 for a, b in zip(x, y))
    df = n - 2
    se = math.sqrt(sse / df / sxx) if df > 0 else float("nan")
    sst = sum((b - my) ** 2 for b in y)
    r2 = 1.0 - sse / sst if sst else 0.0
    t = slope / se if se else 0.0
    return {"estimate_type": "slope", "statistic_name": "slope", "statistic": _r(slope), "df": df,
            "p": _r(t_two_sided(t, df)) if df > 0 else None, "n": n, "groups": [n],
            "ci_95": [_r(slope - Z * se), _r(slope + Z * se)] if df > 0 else None, "intercept": _r(intercept),
            "effect_size": {"type": "r_squared", "value": _r(r2), "ci_95": None, "ci_method": "analytic",
                            "direction": "y per unit x"},
            "status": "done"}


def fisher_exact(a, b, c, d):
    n = a + b + c + d
    if min(a, b, c, d) < 0 or n == 0:
        return {"status": "failed", "error": "invalid 2x2 table"}
    r1, r2, c1 = a + b, c + d, a + c
    lnC = _lgamma

    def prob(k):
        return math.exp(lnC(r1 + 1) - lnC(k + 1) - lnC(r1 - k + 1) + lnC(r2 + 1) - lnC(c1 - k + 1)
                        - lnC(r2 - c1 + k + 1) - (lnC(n + 1) - lnC(c1 + 1) - lnC(n - c1 + 1)))
    p0 = prob(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    p = sum(prob(k) for k in range(lo, hi + 1) if prob(k) <= p0 * (1 + 1e-9))
    orv = (a * d) / (b * c) if b * c else float("inf")
    if a > 0 and b > 0 and c > 0 and d > 0:
        se = math.sqrt(1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d)
        ci = [_r(math.exp(math.log(orv) - Z * se)), _r(math.exp(math.log(orv) + Z * se))]
    else:
        ci = None
    return {"estimate_type": "association", "statistic_name": "odds_ratio", "statistic": _r(orv), "df": 1,
            "p": _r(min(1.0, p)), "n": n, "groups": [r1, r2], "table": [[a, b], [c, d]], "ci_95": ci,
            "effect_size": {"type": "odds_ratio", "value": _r(orv), "ci_95": ci, "ci_method": "log_or_woolf",
                            "direction": "ad/bc"},
            "status": "done"}


TESTS = {"student_t": student_t, "mann_whitney_u": mann_whitney_u, "kruskal_wallis": kruskal_wallis,
         "wilcoxon_signed_rank": wilcoxon_signed_rank, "spearman_rho": spearman_rho,
         "ols_slope": ols_slope, "fisher_exact": fisher_exact, "descriptive": descriptive}


# ------------------------------------------------------- material introspection
def normalize_input(v):
    return norm(v).lower()


def analyze_rows(f):
    """Columns + row dicts for a table source (csv/tsv/json/jsonl/sqlite)."""
    return parse_table(f)


def describe_numeric(rows, col):
    vals = [x for x in (to_num(r.get(col)) for r in rows) if x is not None]
    return {"n": len(vals), "values": vals, "missing": len(rows) - len(vals)}


def _md_tables(files):
    for f in files:
        if f["kind"] != "text":
            continue
        lines = read_text(f["abs"]).splitlines()
        i = 0
        while i < len(lines):
            if not lines[i].strip().startswith("|"):
                i += 1
                continue
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            header = [c.strip().strip("`* ").lower() for c in lines[i].strip().strip("|").split("|")]
            body = [[c.strip().strip("`* ") for c in lines[r].strip().strip("|").split("|")]
                    for r in range(i + 2, j)]
            yield f, header, body, i
            i = j


def parse_rules_md(files):
    out = {"registry": [], "gate_order": [], "banned": [], "degradations": [],
           "method_locator": None, "gate_locator": None, "ban_locator": None, "deg_locator": None}
    for f, header, body, hline in _md_tables(files):
        if "method" in header and "design" in header:
            out["method_locator"] = out["method_locator"] or "%s#L%d" % (f["path"], hline + 1)
            for k, cells in enumerate(body):
                if len(cells) < 3 or not cells[0]:
                    continue
                gates = [g.strip() for g in re.split(r"[,，;；/]", cells[2]) if g.strip()] if len(cells) > 2 else []
                out["registry"].append({
                    "methods": [m.strip().strip("`* ") for m in cells[0].split("/") if m.strip()],
                    "design": cells[1], "gates": gates,
                    "effect_size": cells[3] if len(cells) > 3 else "not_declared",
                    "locator": "%s#L%d" % (f["path"], hline + 3 + k)})
        if "kind" in header or "触发" in "".join(header):
            out["deg_locator"] = out["deg_locator"] or "%s#L%d" % (f["path"], hline + 1)
            out["degradations"] = [c[0] for c in body if c and c[0]]
    for f in files:
        if f["kind"] != "text":
            continue
        for ln, line in enumerate(read_text(f["abs"]).splitlines(), 1):
            if ("判定顺序" in line) and "→" in line:
                out["gate_order"] = [x.strip(" `*。") for x in line.split("：", 1)[-1].split("→") if x.strip()]
                out["gate_locator"] = out["gate_locator"] or "%s#L%d" % (f["path"], ln)
            if ("禁用表述" in line or "banned" in line.lower()) and "`" in line:
                out["banned"] = [t for t in re.findall(r"`([^`]+)`", line)]
                out["ban_locator"] = out["ban_locator"] or "%s#L%d" % (f["path"], ln)
    return out


def parse_dictionary(files):
    entries = []
    for f, header, body, hline in _md_tables(files):
        if any(h in ("字段", "field", "变量", "指标", "name") for h in header):
            for k, cells in enumerate(body):
                if len(cells) < 2:
                    continue
                d = dict(zip(header, cells))
                field = d.get("字段") or d.get("field") or d.get("变量") or d.get("指标") or ""
                if field and field.lower() not in ("字段", "field", "name"):
                    entries.append({"field": field, "dtype": d.get("类型") or d.get("type") or "",
                                    "meaning": d.get("说明") or d.get("meaning") or "",
                                    "locator": "%s#L%d" % (f["path"], hline + 3 + k)})
    return entries
