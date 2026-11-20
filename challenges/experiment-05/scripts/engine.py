# -*- coding: utf-8 -*-
"""Statistics, rule screening, the definitional self-test and the consistency checks.

The screening statistics are the ones the material defines (arithmetic mean, sample SD,
median, MAD, modified z, IQR fence, least-squares fit, relative deviation).  The self-test
recomputes each definition on a fixed five-value fixture so a second person can recheck the
numbers without the input data.
"""
import math

from extract import s, nkey, num

SELF_TEST_DATA = [1.0, 2.0, 3.0, 4.0, 100.0]
SEVERITY_Z = ((6.0, "high"), (4.0, "medium"))


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def sd(v):
    v = [x for x in v if x is not None]
    if len(v) < 2:
        return 0.0
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def quantile(v, p):
    xs = sorted(x for x in v if x is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    h = (len(xs) - 1) * p
    lo, hi = int(math.floor(h)), int(math.ceil(h))
    return xs[lo] + (xs[hi] - xs[lo]) * (h - lo)


def median(v):
    return quantile(v, 0.5)


def mad(v):
    xs = [x for x in v if x is not None]
    m = median(xs)
    if m is None:
        return None
    return median([abs(x - m) for x in xs])


def iqr(v):
    xs = [x for x in v if x is not None]
    q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
    if q1 is None or q3 is None:
        return 0.0
    return q3 - q1


def fence(v):
    xs = [x for x in v if x is not None]
    if not xs:
        return None, None
    q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
    k = 1.5 * (q3 - q1)
    return q1 - k, q3 + k


def modified_z(x, med, m):
    if m in (None, 0):
        return None
    return 0.6745 * (x - med) / m


def fit(xs, ys):
    n = min(len(xs), len(ys))
    if n < 2:
        return None, None, None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None, None, None
    a = sxy / sxx
    b = my - a * mx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 if syy == 0 else max(0.0, min(1.0, (sxy * sxy) / (sxx * syy)))
    return a, b, r2


def rel_dev(calc, rep):
    if rep in (None, 0):
        return None
    return (calc - rep) / abs(rep)


# ------------------------------------------------------------- rule screen ---

def severity_for_z(z):
    az = abs(z)
    for cut, sev in SEVERITY_Z:
        if az >= cut:
            return sev
    return "low"


def screen_series(series, tol=0.05):
    """Raise rule candidates (R1 / R2 / R5 / R8') for one numeric column."""
    vals = series.get("values") or []
    cands = []
    med = median(vals)
    m = mad(vals)
    for i, x in enumerate(vals):
        z = modified_z(x, med, m)
        if z is not None and abs(z) > 3.5:
            cands.append({"rule_id": "R1", "index": i, "value": x,
                          "detail": "modified z %.4f against median %s and MAD %s"
                                    % (z, s(med), s(m)),
                          "severity": severity_for_z(z), "hint": "data_quality"})
        elif z is None:
            lo, hi = fence(vals)
            if lo is not None and (x < lo or x > hi):
                cands.append({"rule_id": "R2", "index": i, "value": x,
                              "detail": "outside IQR fence [%s, %s]" % (s(lo), s(hi)),
                              "severity": "medium", "hint": "data_quality"})
    seen = {}
    for i, x in enumerate(vals):
        seen.setdefault(round(x, 9), []).append(i)
    for x, idxs in seen.items():
        if len(idxs) >= 2:
            cands.append({"rule_id": "R5", "index": idxs[0], "value": x,
                          "detail": "%d rows share the value %s" % (len(idxs), s(x)),
                          "severity": "medium", "hint": "data_quality"})
    if vals:
        top = max(vals)
        ntop = sum(1 for x in vals if abs(x - top) < 1e-9)
        if ntop >= 3 and (top in (255, 1023, 4095, 65535, 100, 1000, 10000, 32767)
                          or top % 10 == 0):
            cands.append({"rule_id": "R8'", "index": vals.index(top), "value": top,
                          "detail": "%d rows sit at the maximal value %s" % (ntop, s(top)),
                          "severity": "high", "hint": "method_artifact"})
    return cands


def screen_all(ctx):
    out = []
    for series in ctx.get("series", []):
        for c in screen_series(series, 0.05):
            out.append(dict(c, mat=series["mat"], column=series["column"],
                            locator="%s#L%s" % (series["mat"], (series["row_lines"] + [0])[c["index"]])))
    return out


# ------------------------------------------------------------ self-test ------

def self_test(ctx):
    d = SELF_TEST_DATA
    med = median(d)
    m = mad(d)
    lo, hi = fence(d)
    rows = [
        ("均值", "sum(x)/n", round(mean(d), 6), 22.0),
        ("SD", "sqrt(sum((x-m)^2)/(n-1))", round(sd(d), 6), 43.617657),
        ("中位数", "quantile(p=0.5)", round(med, 6), 3.0),
        ("MAD", "median(|x-median|)", round(m, 6), 1.0),
        ("修正 z", "0.6745*(x-median)/MAD", round(modified_z(100.0, med, m), 6), 65.4265),
        ("IQR 栅栏", "[Q1-1.5*IQR, Q3+1.5*IQR]", [round(lo, 6), round(hi, 6)], [-1.0, 7.0]),
        ("相对偏差", "(calc-rep)/|rep|", round(rel_dev(43.6, 40.0), 6), 0.09),
    ]
    defs = {nkey(_cell(r, ("量",))): r for r in ctx.get("kinds", {}).get("stats_def", [])}
    out = []
    for name, formula, got, want in rows:
        ref = defs.get(nkey(name))
        out.append({"quantity": name, "formula": formula,
                    "fixture": d, "value": got, "expected": want,
                    "ok": bool(_close(got, want)),
                    "locator": ref["locator"] if ref else "",
                    "quote": ref["quote"] if ref else ""})
    return out


def _close(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1e-3, abs(b) * 1e-3)


# --------------------------------------------------------------- digest ------

def rule_index(ctx):
    out = []
    for r in ctx.get("kinds", {}).get("rules", []):
        cid = ""
        for k, v in r["cells"].items():
            if nkey(k) == "id":
                cid = s(v)
                break
        out.append({"id": cid, "judge": _cell(r, ("判据",)),
                    "trigger": _cell(r, ("触发条件",)),
                    "severity": _cell(r, ("默认severity", "severity")),
                    "hint": _hint(_cell(r, ("归因提示", "归因提示不是结论"))),
                    "locator": r["locator"], "quote": r["quote"],
                    "verified": r["verified"]})
    return out


HINTS = ("data_quality", "method_artifact", "source_ambiguity", "undetermined")


def _hint(v):
    t = s(v).replace("`", "").strip()
    for e in HINTS:
        if t.startswith(e):
            return e
    return t


def _cell(r, names):
    ns = [nkey(n) for n in names]
    for k, v in r["cells"].items():
        if nkey(k) in ns or any(n and (n in nkey(k) or nkey(k) in n) for n in ns):
            return s(v).replace("`", "").strip()
    return ""


def digest(ctx):
    k = ctx.get("kinds", {})
    return {"rules": len(k.get("rules", [])),
            "units": len(ctx.get("units", [])),
            "thresholds": len(ctx.get("thresholds", [])),
            "status_states": len(k.get("status_map", [])),
            "attributions": len(k.get("attr_enum", [])),
            "do_not_conclude": len(k.get("dnc", [])),
            "artifacts": len(k.get("artifacts", [])),
            "contract_rules": len(k.get("contract_map", [])),
            "series": len(ctx.get("series", [])),
            "dossiers": len(ctx.get("dossiers", [])),
            "trends": len(ctx.get("trends", [])),
            "causes": len(ctx.get("causes", [])),
            "candidates": len(screen_all(ctx))}


def checks(ctx, res):
    st = self_test(ctx)
    ri = rule_index(ctx)
    out = [
        {"name": "stats_definition_self_test",
         "ok": all(r["ok"] for r in st),
         "detail": "%d of %d definitions recomputed on the fixture %s"
                   % (sum(1 for r in st if r["ok"]), len(st), SELF_TEST_DATA)},
        {"name": "rule_index_has_locator_and_quote",
         "ok": all(r["locator"] and r["quote"] for r in ri),
         "detail": "%d rule row(s) indexed" % len(ri)},
        {"name": "threshold_index_present",
         "ok": len(ctx.get("thresholds", [])) >= 3,
         "detail": "%d threshold constant(s) indexed" % len(ctx.get("thresholds", []))},
        {"name": "unit_dictionary_present",
         "ok": bool(ctx.get("units")),
         "detail": "%d quantity group(s) indexed" % len(ctx.get("units", []))},
    ]
    return out
