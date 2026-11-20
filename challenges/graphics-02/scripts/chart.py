#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chart.py - source table -> data-to-mark model -> one primitive canvas; draw.py serialises it."""
import csv
import hashlib
import json
import math
import os
import re
import zipfile
from pathlib import Path

import draw

PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7",
    "#E69F00", "#56B4E9", "#F0E442", "#8C564B"]
STY = {
    "journal": {"f": 8.0, "ti": 11.0, "axl": 0.9, "bw": 0.74},
    "nature": {"f": 7.0, "ti": 10.0, "axl": 0.8, "bw": 0.80},
    "thesis": {"f": 9.0, "ti": 12.0, "axl": 1.0, "bw": 0.66},
    "presentation": {"f": 11.0, "ti": 15.0, "axl": 1.1, "bw": 0.60},
    }
MISSING = {"", "-", "--", "–", "—", ".", "na", "n/a", "n.a.", "nan", "nd",
    "n.d.", "nr", "null", "none", "missing", "not measured"}
ERR_TAIL = {"sd", "sem", "se", "stdev", "std", "err", "error", "ci", "ci95", "pm", "sd."}
INDEX_HINTS = {"replicate", "rep", "reps", "sample", "sampleid", "id", "index",
    "no", "number", "run", "trial", "well", "lane", "groupid", "row"}
SKIP_FILES = {"case.json", "challenge.json", "task.md", "result.json"}
CJK_RE = re.compile(r"[⺀-鿿　-〿＀-￯]")


def cr(i):
    s, i = "", int(i) + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def fmt(x):
    if x is None:
        return ""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    if abs(x) >= 100:
        return "%.0f" % x
    if abs(x) >= 1:
        return ("%.2f" % x).rstrip("0").rstrip(".")
    return ("%.3f" % x).rstrip("0").rstrip(".")


def parse_number(raw):
    """(value, kind) with kind in ok | censored | missing | text."""
    if raw is None:
        return None, "missing"
    s = str(raw).strip()
    if s[:1] in "<>":
        s = s[1:].strip()
        lead = True
    else:
        lead = False
    if s.lower() in MISSING:
        return None, "missing"
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1].strip()
    s = s.replace(",", "").replace("−", "-").replace("±", "").replace("%", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None, "text"
    return (-v if neg else v), ("censored" if lead else "ok")


def header_unit(h):
    m = re.search(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]\s*$", str(h))
    if m:
        return m.group(1).strip(), str(h)[:m.start()].strip()
    return "", str(h).strip()


def clean(o):
    """Drop None / NaN so the JSON never carries a bare null literal."""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            c = clean(v)
            if c is not None:
                out[k] = c
        return out
    if isinstance(o, (list, tuple)):
        out = []
        for v in o:
            c = clean(v)
            if c is not None:
                out.append(c)
        return out
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return round(o, 6)
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    return str(o)


def wjson(path, obj):
    path = Path(path)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def read_delim(path):
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    delim = ","
    if sample.count("\t") > sample.count(","):
        delim = "\t"
    elif sample.count(";") > sample.count(","):
        delim = ";"
    rows = []
    for i, cells in enumerate(csv.reader(text.splitlines(), delimiter=delim)):
        cells = [c.strip() for c in cells]
        if not any(cells):
            continue
        rows.append({"row": i + 1, "cells": cells, "line": delim.join(cells)})
    return rows


def read_xlsx(path):
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall(ns + "si"):
                shared.append("".join(t.text or "" for t in si.iter(ns + "t")))
        sheets = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        if not sheets:
            return []
        rows = []
        for i, row in enumerate(ET.fromstring(zf.read(sheets[0])).iter(ns + "row")):
            cells = []
            for c in row.findall(ns + "c"):
                v = c.find(ns + "v")
                val = (v.text or "") if v is not None else ""
                if c.get("t") == "s" and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
                cells.append(val)
            rows.append({"row": int(row.get("r") or i + 1), "cells": cells, "line": ",".join(cells)})
        return rows


def split_table(rows):
    header_i = 0
    for i, r in enumerate(rows[:8]):
        nums = sum(1 for c in r["cells"] if parse_number(c)[1] in ("ok", "censored"))
        if nums >= 2:
            header_i = max(0, i - 1)
            break
    header_row = rows[header_i] if rows else {"row": 0, "cells": []}
    data = [r for r in rows[header_i + 1:] if any(c for c in r["cells"])]
    return header_row["cells"], data, header_row["row"]


def discover(inp, work):
    d = {"case": {}, "case_path": "", "case_error": "", "wo": {}, "tables": [],
    "errors": [], "notes": []}
    for name in ("case.json", "challenge.json"):
        p = Path(inp) / name
        if p.is_file():
            d["case_path"] = str(p)
            obj = read_json(p)
            if isinstance(obj, dict):
                d["case"] = obj
            else:
                d["case_error"] = "case_json_unreadable"
                d["errors"].append("case_json_unreadable:%s" % name)
            break
    if not d["case"] and not d["case_path"]:
        d["errors"].append("case_json_missing")
    case = d["case"]
    for k in ("workorder", "chart_spec", "spec", "figure_spec"):
        if isinstance(case.get(k), dict):
            d["wo"].update(case[k])
    dr = read_json(Path(work) / "draft.json")
    if isinstance(dr, dict):
        if isinstance(dr.get("workorder"), dict):
            d["wo"].update(dr["workorder"])
            d["notes"].append("workorder merged from /app/work/draft.json")
        elif any(k in dr for k in ("chart_type", "title", "x", "y", "series")):
            d["wo"].update(dr)
            d["notes"].append("draft.json treated as a chart workorder")
    exts = {".csv": 1, ".tsv": 1, ".xlsx": 2}
    seen = set()
    for p in sorted(Path(inp).rglob("*")):
        if not p.is_file() or p.name in SKIP_FILES or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext not in exts:
            continue
        try:
            raw = read_xlsx(p) if ext == ".xlsx" else read_delim(p)
        except Exception as exc:  # noqa: BLE001
            d["errors"].append("table_read_failed:%s:%s" % (p.name, type(exc).__name__))
            continue
        if not raw:
            d["notes"].append("empty_table:%s" % p.name)
            continue
        headers, data, header_row = split_table(raw)
        sig = (p.name, tuple(headers), len(data))
        if sig in seen:  # the same table reached through two paths
            d["notes"].append("duplicate_table_skipped:%s" % p.name)
            continue
        seen.add(sig)
        if not data:
            d["notes"].append("header_only:%s" % p.name)
        score = 2 * sum(1 for r in data for c in r["cells"]
    if parse_number(c)[1] in ("ok", "censored")) + len(data)
        d["tables"].append({"file": p.name, "path": str(p), "sheet": "table1",
    "headers": headers, "rows": data, "header_row": header_row,
    "score": score})
    d["tables"].sort(key=lambda t: -t["score"])
    d["source_present"] = bool(d["tables"])
    return d


def spec(wo, style):
    y = wo.get("y") or wo.get("y_fields") or wo.get("series") or []
    if not isinstance(y, list):
        y = [y]
    sp = {
    "type": str(wo.get("chart_type") or wo.get("type") or ""),
    "title": str(wo.get("title") or ""),
    "x": str(wo.get("x") or wo.get("x_field") or ""),
    "y": [v for v in y if str(v).strip()],
    "xl": str(wo.get("x_label") or ""),
    "xu": str(wo.get("x_unit") or ""),
    "yl": str(wo.get("y_label") or ""),
    "yu": str(wo.get("y_unit") or ""),
    "em": str(wo.get("error_mode") or ""),
    "style": style or str(wo.get("style") or "journal"),
    "wm": float(wo.get("width_mm") or 170.0),
    "dpi": int(wo.get("dpi") or 96),
    "tb": str(wo.get("source_table") or ""),
    }
    sp["hm"] = float(wo.get("height_mm") or round(sp["wm"] * 0.62, 1))
    if sp["style"] not in STY:
        sp["style"] = "journal"
    return sp


def bind(tb, sp, ex):
    rows, hs = tb["rows"], list(tb["headers"])
    ncol = max([len(hs)] + [len(r["cells"]) for r in rows] + [0])
    hs = [hs[i] if i < len(hs) else "col_%d" % (i + 1) for i in range(ncol)]
    tb["headers"] = hs

    def cell(r, i):
        return r["cells"][i] if i < len(r["cells"]) else ""

    cov = [sum(1 for r in rows if parse_number(cell(r, i))[1] in ("ok", "censored"))
    for i in range(ncol)]
    norms = [norm(h) for h in hs]
    err_of = {}
    for j in range(ncol):
        for k in range(ncol):
            if j == k or not norms[k] or len(norms[j]) <= len(norms[k]):
                continue
            if not norms[j].startswith(norms[k]):
                continue
            if norms[j][len(norms[k]):] in ERR_TAIL and cov[j] > 0 and cov[k] > 0 and k not in err_of:
                err_of[k] = j
    xi = -1
    want = norm(sp["x"])
    if want:
        for j, h in enumerate(hs):
            if norms[j] == want or want in norms[j]:
                xi = j
                break
    if xi < 0:
        for j in range(ncol):
            if cov[j] < max(1, len(rows) * 0.6):
                xi = j
                break
    if xi < 0:
        xi = 0 if ncol else -1
    want_y = [norm(v) for v in sp["y"] if norm(v)]
    ycols = []
    for j in range(ncol):
        if j == xi or cov[j] == 0 or j in err_of.values():
            continue
        if norms[j] in INDEX_HINTS or "replicat" in norms[j]:
            ex("index_column_skipped", "column %r carries row index, not a measure" % hs[j],
    "info", "not charted")
            continue
        if want_y and not any(w == norms[j] or w in norms[j] or norms[j] in w for w in want_y):
            continue
        ycols.append(j)
    if not ycols:
        for j in range(ncol):
            if j != xi and cov[j] > 0 and j not in err_of.values():
                if norms[j] in INDEX_HINTS or "replicat" in norms[j]:
                    continue
                ycols.append(j)
    series = []
    for si, j in enumerate(ycols[:6]):
        unit, base = header_unit(hs[j])
        series.append({"name": base or hs[j], "unit": unit, "col": j, "err_col": err_of.get(j)})
    if not series:
        raise ValueError("no numeric series resolved from headers")
    xvals = [cell(r, xi).strip() for r in rows] if xi >= 0 else ["%d" % r["row"] for r in rows]
    xnum = [parse_number(v)[0] for v in xvals if parse_number(v)[1] == "ok"]
    x_is_num = bool(xnum) and len(xnum) >= max(1, len(rows) * 0.8)
    aggr = {si: {} for si in range(len(series))}
    missing = []
    for r, xv in zip(rows, xvals):
        if not xv:
            continue
        for si, sr in enumerate(series):
            raw = cell(r, sr["col"])
            v, kind = parse_number(raw)
            if kind != "ok":
                if kind in ("missing", "censored"):
                    missing.append({"row": r["row"], "column": hs[sr["col"]],
    "raw": raw[:40], "kind": kind})
                continue
            e, eraw = None, ""
            if sr["err_col"] is not None:
                eraw = cell(r, sr["err_col"])
                ev, ek = parse_number(eraw)
                if ek == "ok":
                    e = ev
                elif eraw.strip():
                    ex("error_value_unparsable", "row %d %r=%r" % (r["row"], hs[sr["err_col"]],
    eraw[:24]),
    "info", "bar drawn without error whisker")
            key = "r%d" % r["row"] if x_is_num else xv
            aggr[si].setdefault(key, []).append(
    {"v": v, "e": e, "eraw": eraw, "row": r["row"], "quote": r["line"], "x": xv})
    order, seen = [], set()
    for si in aggr:
        for key, items in sorted(aggr[si].items(), key=lambda kv: kv[1][0]["row"]):
            if key not in seen:
                seen.add(key)
                order.append((key, items[0]["x"]))
    total_reps = 0
    for si, sr in enumerate(series):
        pts = []
        for key, xlabel in order:
            items = aggr[si].get(key)
            if not items:
                continue
            n = len(items)
            if n > 1:
                total_reps = max(total_reps, n)
            y = sum(it["v"] for it in items) / float(n)
            es = [it["e"] for it in items if it["e"] is not None]
            e = sum(es) / float(len(es)) if es else None
            eras = [it["eraw"] for it in items if it["eraw"].strip()]
            src_rows = [it["row"] for it in items]
            pts.append({
    "id": "s%d-p%d" % (si + 1, len(pts) + 1), "x": xlabel,
    "y": y, "yr": ", ".join(fmt(it["v"]) for it in items),
    "n": n, "err": e, "eraw": ", ".join(eras),
    "src": {"file": tb["file"], "sheet": tb["sheet"], "row": src_rows[0],
    "rows": src_rows, "col": cr(sr["col"]), "col_index": sr["col"],
    "header": hs[sr["col"]], "x_header": hs[xi] if xi >= 0 else "",
    "x_col": cr(xi) if xi >= 0 else "", "quote": items[0]["quote"]},
    "_row": min(src_rows),
    })
        pts.sort(key=lambda p: p["_row"])
        for i, p in enumerate(pts):
            p.pop("_row", None)
            p["id"] = "s%d-p%d" % (si + 1, i + 1)
        series[si]["points"] = pts
        series[si]["color"] = PALETTE[si % len(PALETTE)]
    if total_reps > 1 and not x_is_num:
        ex("replicate_aggregated", "up to %d rows shared a category; plotted the arithmetic mean of "
    "the reported values" % total_reps, "warn",
    "mean per category, n kept on each point")
    categories = [x for _, x in order]
    covered = sum(len(sr["points"]) for sr in series)
    attempted = covered + len(missing)
    return {
    "xi": xi, "x_is_num": x_is_num, "series": series, "categories": categories,
    "missing": missing,
    "coverage": {"required": attempted, "mapped": covered, "missing_count": len(missing),
    "missing": missing[:20],
    "ratio": round(covered / float(attempted), 4) if attempted else 0.0},
    }


def nice_ticks(lo, hi, target=6):
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / float(target)
    mag = 10 ** math.floor(math.log10(raw))
    step = 10 * mag
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    ticks, v = [], start
    while v <= end + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    if len(ticks) > 14:
        ticks = ticks[::2]
    return start, end, ticks


def ymap(v, lo, hi, y0, y1):
    if hi <= lo:
        return y1
    return y1 - (v - lo) / (hi - lo) * (y1 - y0)


def build_model(B, sp, tb, ex):
    ys = [p["y"] for sr in B["series"] for p in sr["points"]]
    if not ys:
        raise ValueError("no numeric values in %s" % tb["file"])
    vmax = max(ys)
    lo, hi, ticks = nice_ticks(0.0, max(vmax, 1e-9) * 1.08)
    chart = sp["type"]
    if chart in ("", "auto"):
        chart = "line" if B["x_is_num"] else "bar"
        ex("chart_type_inferred", "no workorder chart type; %s chosen from the table shape" % chart,
    "info", "explicit chart_type in the workorder overrides this")
    yu = sp["yu"] or B["series"][0]["unit"]
    if not yu:
        ex("unit_unknown", "no unit in the headers or the workorder",
    "warn", "axis caption says 'unit not reported', no unit invented")
    if not sp["yl"] and len(B["series"]) > 3:
        ex("many_series", "%d measure columns; palette cycles after 8" % len(B["series"]),
    "info", "grouped bars")
    xhead = tb["headers"][B["xi"]] if B["xi"] >= 0 else "row"
    title = sp["title"] or ("%s by %s" % (" / ".join(sr["name"] for sr in B["series"]), xhead))
    legend = [{"id": "legend-" + sr["id"] if "id" in sr else "legend-s%d" % (i + 1),
    "series_id": sr.get("id") or "s%d" % (i + 1),
    "label": sr["name"], "color": sr["color"]}
    for i, sr in enumerate(B["series"])]
    for i, sr in enumerate(B["series"]):
        sr["id"] = "s%d" % (i + 1)
        sr["column"] = tb["headers"][sr["col"]]
    for i, it in enumerate(legend):
        it["id"], it["series_id"] = "legend-s%d" % (i + 1), "s%d" % (i + 1)
    return {
    "chart_type": chart,
    "title": title,
    "axes": {
    "x": {"label": sp["xl"] or xhead, "unit": sp["xu"] or "",
    "scale": "linear" if B["x_is_num"] else "category",
    "categories": B["categories"],
    "source": {"header": xhead, "col": cr(B["xi"]) if B["xi"] >= 0 else ""}},
    "y": {"label": sp["yl"] or " / ".join(sr["name"] for sr in B["series"]),
    "unit": yu, "scale": "linear", "min": lo, "max": hi, "ticks": ticks,
    "source": {"header": B["series"][0]["column"],
    "note": "titles and units copied from the table header"}},
    },
    "series": B["series"],
    "legend": legend,
    "coverage": B["coverage"],
    "source_table": {"file": tb["file"], "sheet": tb["sheet"], "header_row": tb["header_row"],
    "data_rows": len(tb["rows"]), "headers": tb["headers"]},
    }


def render(m, st, W, H):
    cv = draw.Canvas()
    ya, xa = m["axes"]["y"], m["axes"]["x"]
    lo, hi, cats = ya["min"], ya["max"], xa["categories"]
    cv.rect(0, 0, W, H, fill="#ffffff", rid="canvas-bg", layer="background")
    top = 24.0
    if m["title"]:
        cv.text(W / 2.0, 17.0, m["title"], st["ti"], "middle", "#111111",
    "figure-title", "title", bold=True)
        top = 34.0
    lx, ly = 18.0, top
    for it in m["legend"]:
        w = 20.0 + draw.text_w(it["label"], st["f"] - 0.5)
        if lx + w > W - 18.0:
            lx, ly = 18.0, ly + 13.0
        if m["chart_type"] == "bar":
            cv.rect(lx, ly - 8.0, 10.0, 8.0, fill=it["color"], rid=it["id"] + "-swatch",
    layer="legend")
        else:
            cv.circle(lx + 5.0, ly - 4.0, 3.4, fill=it["color"], rid=it["id"] + "-swatch",
    layer="legend")
        cv.text(lx + 14.0, ly - 1.0, it["label"], st["f"] - 0.5, "start", "#111111",
    it["id"] + "-text", "legend")
        it["xy"] = [round(lx, 1), round(ly, 1)]
        lx += w + 16.0
    x0 = max(50.0, st["f"] * 5.0)
    y0 = max(top + 24.0, ly + 27.0)
    x1, y1 = W - 20.0, H - 44.0
    if not cats:
        cats = ["no category"]
    cv.line(x0, y0, x0, y1, "#111111", st["axl"], rid="axis-y", layer="axes")
    cv.line(x0, y1, x1, y1, "#111111", st["axl"], rid="axis-x", layer="axes")
    for ti, tv in enumerate(ya["ticks"]):
        yy = ymap(tv, lo, hi, y0, y1)
        if yy < y0 - 0.5 or yy > y1 + 0.5:
            continue
        cv.line(x0 - 3.0, yy, x0, yy, "#111111", st["axl"], rid="ytick-%d" % ti, layer="axes")
        cv.text(x0 - 5.0, yy + st["f"] * 0.35, fmt(tv), st["f"] - 1.0, "end", "#111111",
    "yticklabel-%d" % ti, "axes")
    band = (x1 - x0) / float(max(1, len(cats)))
    for ci, ct in enumerate(cats):
        size = st["f"] - 0.5
        tw = draw.text_w(ct, size)
        if tw > band - 4.0 and tw > 0:
            size = max(4.5, size * (band - 6.0) / tw)
        cv.text(x0 + (ci + 0.5) * band, y1 + 13.0, ct, size, "middle", "#111111",
    "xtick-%d" % ci, "axes")
    yl = ya["label"] + ((" (%s)" % ya["unit"]) if ya["unit"] else " (unit not reported)")
    cv.text(x0, y0 - 9.0, yl, st["f"], "start", "#111111", "label-yaxis", "labels")
    xl = xa["label"]
    if xa["unit"] and xa["unit"] not in xl:
        xl = (xl + " (%s)" % xa["unit"]) if xl else xa["unit"]
    cv.text((x0 + x1) / 2.0, H - 12.0, xl, st["f"], "middle", "#111111", "label-xaxis", "labels")
    bv = max(lo, 0.0) if lo <= 0 <= hi else lo
    base = ymap(bv, lo, hi, y0, y1)
    nser = max(1, len(m["series"]))
    slot = band * st["bw"] / nser
    for si, sr in enumerate(m["series"]):
        line_pts = []
        for p in sr["points"]:
            ci = cats.index(p["x"]) if p["x"] in cats else 0
            yy = ymap(p["y"], lo, hi, y0, y1)
            if m["chart_type"] == "bar":
                bx = x0 + ci * band + band * (1 - st["bw"]) / 2.0 + si * slot + slot * 0.06
                bw = max(1.0, slot * 0.88)
                tp = min(yy, base)
                cv.rect(bx, tp, bw, max(0.6, abs(base - yy)), fill=sr["color"],
    rid="bar-" + p["id"], layer="data")
                p["g"] = {"id": p["id"], "kind": "bar", "x_px": bx, "w_px": bw, "top": tp,
    "h_px": abs(base - yy), "base": base, "bv": bv,
    "y_px": yy, "pt": y0, "pb": y1, "category": p["x"]}
                xc = bx + bw / 2.0
            else:
                cx = x0 + (ci + 0.5) * band
                line_pts.append((cx, yy))
                cv.circle(cx, yy, max(2.0, st["f"] * 0.28), fill=sr["color"], stroke="#ffffff",
    sw=0.6, rid="pt-" + p["id"], layer="data")
                p["g"] = {"id": p["id"], "kind": "line", "x_px": cx,
    "y_px": yy, "pt": y0, "pb": y1, "category": p["x"]}
                xc = cx
            if p.get("err"):
                e = abs(p["err"])
                yt = max(y0, min(y1, ymap(p["y"] + e, lo, hi, y0, y1)))
                yb = max(y0, min(y1, ymap(p["y"] - e, lo, hi, y0, y1)))
                cv.line(xc, yt, xc, yb, "#111111", st["axl"] * 0.8, rid="err-" + p["id"],
    layer="error")
                cv.line(xc - 3.2, yt, xc + 3.2, yt, "#111111", st["axl"] * 0.8,
    rid="errt-" + p["id"], layer="error")
                cv.line(xc - 3.2, yb, xc + 3.2, yb, "#111111", st["axl"] * 0.8,
    rid="errb-" + p["id"], layer="error")
                p["g"].update(et=round(yt, 2), eb=round(yb, 2))
        if len(line_pts) > 1:
            cv.poly(line_pts, sr["color"], st["axl"] * 0.9, rid="line-" + sr["id"], layer="data")
    m["plot"] = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "w_px": round(W, 2), "h_px": round(H, 2)}
    m["canvas"] = {"w_px": round(W, 2), "h_px": round(H, 2)}
    return cv


def gap_figure(m, st, W, H):
    """Boundary case: an honest empty frame, still a real vector figure."""
    cv = draw.Canvas()
    cv.rect(0, 0, W, H, fill="#ffffff", rid="canvas-bg", layer="background")
    cv.text(W / 2.0, 26.0, m["title"], st["ti"], "middle", "#111111",
    "figure-title", "title", bold=True)
    x0, y0, x1, y1 = 60.0, 70.0, W - 30.0, H - 60.0
    cv.line(x0, y0, x0, y1, "#111111", st["axl"], rid="axis-y", layer="axes")
    cv.line(x0, y1, x1, y1, "#111111", st["axl"], rid="axis-x", layer="axes")
    cv.text(x0, y0 - 10.0, "value (unit not reported)", st["f"], "start", "#111111",
    "label-yaxis", "labels")
    cv.text((x0 + x1) / 2.0, H - 14.0, "category", st["f"], "middle", "#111111",
    "label-xaxis", "labels")
    msg = ["No source table was supplied.",
    "Place the workorder table as CSV, TSV or XLSX under the input directory,",
    "then rerun the single command. Nothing is invented in the meantime."]
    for i, s in enumerate(msg):
        cv.text(W / 2.0, (y0 + y1) / 2.0 - 12.0 + i * 16.0, s, st["f"] + 0.5, "middle",
    "#555555", "gap-note-%d" % i, "labels")
    m["plot"] = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "w_px": round(W, 2), "h_px": round(H, 2)}
    m["canvas"] = {"w_px": round(W, 2), "h_px": round(H, 2)}
    return cv


def cmap(m):
    return {
    "chart": {"type": m["chart_type"], "title": m["title"],
    "canvas_px": [m["canvas"]["w_px"], m["canvas"]["h_px"]],
    "source_table": m["source_table"]["file"],
    "marks": sum(len(sr["points"]) for sr in m["series"])},
    "axes": [
    {"axis": "x", "label": m["axes"]["x"]["label"], "scale": m["axes"]["x"]["scale"],
    "categories": m["axes"]["x"]["categories"],
    "source": m["axes"]["x"]["source"]},
    {"axis": "y", "label": m["axes"]["y"]["label"], "unit": m["axes"]["y"]["unit"],
    "min": m["axes"]["y"]["min"], "max": m["axes"]["y"]["max"],
    "ticks": m["axes"]["y"]["ticks"], "source": m["axes"]["y"]["source"]},
    ],
    "series": [{"id": sr["id"], "name": sr["name"], "column": sr["column"],
    "color": sr["color"], "points": [
    {"id": p["id"], "x": p["x"], "value": p["y"], "n": p["n"],
    "error": p.get("err"), "error_raw": p.get("eraw"),
    "mark": p.get("g"), "src": p["src"]} for p in sr["points"]]}
    for sr in m["series"]],
    "legend": m["legend"],
    "coverage": m["coverage"],
    }


def checks(m, cv, svg, pi, ni):
    lo, hi = m["axes"]["y"]["min"], m["axes"]["y"]["max"]
    y0, y1 = m["plot"]["y0"], m["plot"]["y1"]
    span = max(1e-9, y1 - y0)
    mismatch, n = [], 0
    for sr in m["series"]:
        for p in sr["points"]:
            g = p.get("g") or {}
            if "top" not in g or m["chart_type"] != "bar":
                continue
            n += 1
            v = g["bv"] + (g["base"] - g["top"]) / span * (hi - lo)
            if abs(v - p["y"]) > 1e-6 * max(1.0, abs(p["y"])):
                mismatch.append(p["id"])
    colors = [sr["color"] for sr in m["series"]]
    labels = [it["label"] for it in m["legend"]]
    lc = {"items": len(m["legend"]), "series": len(m["series"]),
    "distinct_colors": len(set(colors)),
    "labels_match": labels == [sr["name"] for sr in m["series"]]}
    lc["ok"] = (lc["items"] == lc["series"] == lc["distinct_colors"] and lc["labels_match"])
    gc = {"checked": n, "mismatch": len(mismatch), "mismatch_ids": mismatch[:10],
    "ok": (not mismatch and (n > 0 or not m["series"]))}
    cov = m["coverage"]
    overflow = {"max_x": round(cv.max_x, 2), "max_y": round(cv.max_y, 2),
    "canvas": [m["canvas"]["w_px"], m["canvas"]["h_px"]],
    "ok": cv.max_x <= m["canvas"]["w_px"] + 0.5 and cv.max_y <= m["canvas"]["h_px"] + 0.5}
    fails = []
    if not lc["ok"]:
        fails.append("legend_series_mismatch")
    if not gc["ok"]:
        fails.append("geometry_mismatch")
    if not m["series"]:
        fails.append("no_source_table")
    if cov["required"] and cov["mapped"] != cov["required"]:
        fails.append("coverage_incomplete")
    if not overflow["ok"]:
        fails.append("canvas_overflow")
    if ni.get("ink_present") is False:
        fails.append("png_blank")
    if not pi.get("magic_ok"):
        fails.append("pdf_missing")
    if not pi.get("vector"):
        fails.append("pdf_not_vector")
    layers = re.findall(r'<g id="(layer-[^"]+)"', svg)
    st_names = [p for p in ("f", "axl", "bw") if p in STY["journal"]]
    return {
    "canvas": {"width_px": m["canvas"]["w_px"], "height_px": m["canvas"]["h_px"],
    "width_mm": round(m["canvas"]["w_px"] * 25.4 / 96.0, 1),
    "height_mm": round(m["canvas"]["h_px"] * 25.4 / 96.0, 1), "dpi": 96},
    "fonts": {"family": draw.FONT_STACK, "cjk_in_figure": bool(CJK_RE.search(svg)),
    "text_elements": svg.count("<text"), "text_kept_as_text": True},
    "line_widths": {"axis": STY["journal"]["axl"], "bar_slot_share": STY["journal"]["bw"],
    "keys": st_names},
    "colors": {"palette": colors, "distinct": len(set(colors))},
    "legend_consistency": lc,
    "geometry_roundtrip": gc,
    "content_coverage": cov,
    "canvas_overflow": overflow,
    "layers": layers,
    "png": ni,
    "pdf": pi,
    "pass": not fails,
    "failures": fails,
    }


def export_all(out, m, cv, style, title, subtitle):
    W, H = m["canvas"]["w_px"], m["canvas"]["h_px"]
    svg = draw.to_svg(cv, W, H, title, subtitle)
    (Path(out) / "chart.svg").write_bytes(svg.encode("utf-8"))
    pdf = draw.to_pdf(cv, W, H)
    (Path(out) / "chart.pdf").write_bytes(pdf)
    png = draw.to_png(cv, W, H)
    (Path(out) / "chart.png").write_bytes(png)
    return svg, pdf, png


def source_info(svg, out):
    layers = re.findall(r'<g id="(layer-[^"]+)"', svg)
    data = svg.encode("utf-8")
    return {"path": "chart.svg", "format": "svg", "editable": True, "text_selectable": True,
    "layers": layers, "layer_count": len(layers), "text_count": svg.count("<text"),
    "element_count": svg.count("<"), "bytes": len(data),
    "sha256": hashlib.sha256(data).hexdigest(),
    "viewBox": (re.search(r'viewBox="([^"]+)"', svg) or [None, ""])[1],
    "model": "chart_model.json", "font_stack": draw.FONT_STACK}


def artifacts(out, pi, ni, dpi):
    return {
    "svg": {"path": "chart.svg", "role": "editable vector master",
    "bytes": os.path.getsize(Path(out) / "chart.svg")},
    "pdf": {"path": "chart.pdf", "engine": "builtin-vector-pdf", "vector": pi.get("vector"),
    "pages": pi.get("pages"), "mediabox_pt": pi.get("mediabox_pt"),
    "bytes": pi.get("bytes")},
    "png": {"path": "chart.png", "engine": "builtin-raster", "width": ni.get("width"),
    "height": ni.get("height"), "dpi": dpi, "color_type": ni.get("color_type"),
    "unique_colors": ni.get("unique_colors"), "bytes": ni.get("bytes")},
    "model": {"path": "chart_model.json", "role": "data-to-mark model with source locators",
    "bytes": os.path.getsize(Path(out) / "chart_model.json")},
    }
