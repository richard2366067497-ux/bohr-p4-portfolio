#!/usr/bin/env python3
"""figurekit -- scientific figure/table reading primitives (reading-02 v6).

Stdlib-only PNG decoding (zlib + scanline unfilter + palette expansion), axis
calibration by least squares (linear/log), colour-cluster curve digitization,
JSON table extraction, claim building/validation with verbatim evidence,
output_contract backfill and artifact rendering. No third-party packages.
"""
import csv
import hashlib
import json
import math
import re
import struct
import time
import unicodedata
import zlib
from pathlib import Path

VERSION = "2.0.0"
GEN = "scientific-figure-parser v2"
DEFAULT_CONTRACT = ["case_id", "status", "result", "claims", "uncertainties", "figure_tables_digest"]
TEXT_EXT = (".json", ".txt", ".md", ".markdown", ".csv", ".tsv")
IMG_EXT = (".png",)
TR = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-",
      "—": "-", "−": "-", " ": " ", "​": ""}
WS = re.compile(r"\s+")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def norm(s, squeeze=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if squeeze else " ", s).strip()


def find_quote(text, quote):
    q, t = norm(quote), norm(text)
    if len(q) < 3 or not t:
        return {"found": False, "mode": "short"}
    if q in t:
        return {"found": True, "mode": "exact"}
    if norm(quote, True) and norm(quote, True) in norm(text, True):
        return {"found": True, "mode": "loose"}
    return {"found": False, "mode": "miss"}


def denull(o):
    """Replace empty slots so no literal JSON null reaches disk."""
    if o is None:
        return ""
    if isinstance(o, dict):
        return {k: denull(v) for k, v in o.items()}
    if isinstance(o, list):
        return [denull(v) for v in o]
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return ""
    return o


def jwrite(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(denull(obj), ensure_ascii=False, indent=1), encoding="utf-8")


def jread(path):
    return json.loads(read_text(path))


def twrite(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def read_text(path):
    b = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def sha256_file(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def round4(x):
    try:
        return round(float(x), 4)
    except Exception:
        return ""


# ============================================================== PNG decoding
def read_png(path):
    b = Path(path).read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG stream")
    pos, w, h, bd, ct, inter, plte, idat = 8, 0, 0, 8, 2, 0, None, b""
    while pos + 8 <= len(b):
        ln = struct.unpack(">I", b[pos:pos + 4])[0]
        typ = b[pos + 4:pos + 8]
        data = b[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, bd, ct, _c, _f, inter = struct.unpack(">IIBBBBB", data)
        elif typ == b"PLTE":
            plte = [tuple(data[i:i + 3]) for i in range(0, len(data) - 2, 3)]
        elif typ == b"IDAT":
            idat += data
        elif typ == b"IEND":
            break
    if bd != 8:
        raise ValueError("unsupported bit depth %d" % bd)
    if inter:
        raise ValueError("interlaced PNG not supported")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ct)
    if ch is None:
        raise ValueError("unsupported colour type %d" % ct)
    raw = zlib.decompress(idat)
    stride = w * ch
    rows, prev, i = [], bytearray(stride), 0
    for _y in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        if f == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                bb = prev[x]
                c = prev[x - ch] if x >= ch else 0
                pp = a + bb - c
                pa, pb, pc = abs(pp - a), abs(pp - bb), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (bb if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        elif f != 0:
            raise ValueError("bad filter type %d" % f)
        prev = line
        rows.append(bytes(line))
    return {"width": w, "height": h, "color_type": ct, "bit_depth": bd,
            "channels": ch, "palette": plte, "rows": rows}


def rgb_rows(img):
    """Expand to a list of rows of (r,g,b) tuples."""
    ct, ch, plte = img["color_type"], img["channels"], img["palette"]
    out = []
    for line in img["rows"]:
        row = []
        if ct == 3:
            for v in line:
                row.append(plte[v] if plte and v < len(plte) else (v, v, v))
        elif ct in (0, 4):
            for x in range(0, len(line), ch):
                g = line[x]
                row.append((g, g, g))
        elif ct == 2:
            for x in range(0, len(line), 3):
                row.append((line[x], line[x + 1], line[x + 2]))
        else:
            for x in range(0, len(line), 4):
                row.append((line[x], line[x + 1], line[x + 2]))
        out.append(row)
    return out


def near(a, b, tol):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol and abs(a[2] - b[2]) <= tol


# ============================================================== calibration
def _fit(pxs, vals):
    n = len(pxs)
    if n < 2:
        return None
    mx, my = sum(pxs) / n, sum(vals) / n
    den = sum((p - mx) ** 2 for p in pxs)
    if den == 0:
        return None
    a = sum((p - mx) * (v - my) for p, v in zip(pxs, vals)) / den
    return a, my - a * mx


def calibrate(tick_px, tick_labels, scale="linear"):
    pairs = []
    for px, lab in zip(tick_px or [], tick_labels or []):
        try:
            v = float(norm(lab))
        except Exception:
            continue
        pairs.append((float(px), v))
    if len(pairs) < 2:
        return None
    log = str(scale).lower() == "log"
    vals = [math.log10(v) if (log and v > 0) else v for _p, v in pairs]
    fit = _fit([p for p, _v in pairs], vals)
    if not fit:
        return None
    a, b = fit
    return {"a": a, "b": b, "log": log, "n_ticks": len(pairs),
            "px_span": [min(p for p, _v in pairs), max(p for p, _v in pairs)]}


def apply_cal(cal, px):
    if not cal:
        return None
    v = cal["a"] * px + cal["b"]
    if cal["log"]:
        try:
            v = 10 ** v
        except OverflowError:
            return None
    return v


def digitize(rows, series, ax_cal, ay_cal):
    """One point per pixel column: the mean y of pixels within tol of the series colour."""
    rgb = tuple(series.get("rgb") or [])
    tol = int(series.get("tol") or 60)
    if len(rgb) != 3:
        return []
    cols = {}
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if near(c, rgb, tol):
                cols.setdefault(x, []).append(y)
    pts = []
    for x in sorted(cols):
        ys = cols[x]
        py = sum(ys) / len(ys)
        dx, dy = apply_cal(ax_cal, x), apply_cal(ay_cal, py)
        pts.append({"px": x, "py": round4(py), "x": round4(dx), "y": round4(dy)})
    return pts


def axis_summary(ax):
    lab = norm(ax.get("label") or "")
    unit = norm(ax.get("unit") or "")
    ticks = [norm(t) for t in (ax.get("tick_labels") or [])]
    return {"label": lab, "unit": unit, "scale": norm(ax.get("scale") or "linear"),
            "tick_labels": ticks, "tick_px": [int(t) for t in (ax.get("tick_px") or []) if str(t).lstrip("-").isdigit()]}


# ============================================================== discovery
def discover(inp):
    """-> (files, dupes, notes): duplicate copies collapsed by sha256."""
    if not inp.exists():
        return [], [], ["input directory not found"]
    notes, dupes, seen, out = [], [], {}, []
    for p in sorted(inp.rglob("*")):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low in ("case.json", "task.md", "challenge.json"):
            continue
        if p.suffix.lower() not in TEXT_EXT + IMG_EXT:
            notes.append("%s: unsupported extension, skipped" % p.name)
            continue
        try:
            h = sha256_file(p)
        except OSError:
            continue
        if h in seen:
            dupes.append("%s duplicates %s; the earlier copy is used" % (p.name, Path(seen[h]).name))
            continue
        seen[h] = str(p)
        out.append(p)
    return out, dupes, notes


def load_json_materials(files, errors):
    docs = {}
    for p in files:
        if p.suffix.lower() != ".json":
            continue
        try:
            docs[p.name] = {"path": p, "data": jread(p), "text": read_text(p)}
        except Exception as e:
            errors.append({"code": "json_unreadable", "detail": "%s: %r" % (p.name, e)})
    return docs


def pick_readings(docs):
    best = None
    for name, d in docs.items():
        obj = d["data"]
        if not isinstance(obj, dict):
            continue
        score = 0
        if "readings" in name.lower():
            score += 2
        if isinstance(obj.get("figures"), dict):
            score += 3
        if isinstance(obj.get("claims"), list):
            score += 1
        if score and (best is None or score > best[0]):
            best = (score, name, obj)
    return (best[1], best[2]) if best else ("", {})


def pick_material(docs):
    best = None
    for name, d in docs.items():
        obj = d["data"]
        if not isinstance(obj, dict) or name == "":
            continue
        score = 0
        if isinstance(obj.get("paragraphs"), list):
            score += 3
        if isinstance(obj.get("tables"), list):
            score += 2
        if isinstance(obj.get("paper_title"), str):
            score += 1
        if score and (best is None or score > best[0]):
            best = (score, name, obj)
    return (best[1], best[2]) if best else ("", {})


def resolve_image(name, files):
    base = Path(str(name)).name.lower()
    for p in files:
        if p.suffix.lower() in IMG_EXT and (p.name.lower() == base or Path(p.name).stem.lower() == Path(base).stem.lower()):
            return p
    for p in files:
        if p.suffix.lower() in IMG_EXT:
            return p
    return None


# ============================================================== figures
def build_figures(readings, files, degradations):
    figs = readings.get("figures") if isinstance(readings, dict) else None
    out = []
    if not isinstance(figs, dict):
        for p in files:
            if p.suffix.lower() in IMG_EXT:
                try:
                    img = read_png(p)
                except Exception as e:
                    degradations.append("%s: PNG decode failed (%s)" % (p.name, e))
                    continue
                out.append({"figure_id": Path(p.stem).upper(), "panel": "",
                            "caption": "", "axes": {}, "legend": [], "series": [],
                            "elements": {}, "image": image_meta(p, img), "digitized": []})
        return out
    for key, cfg in figs.items():
        if not isinstance(cfg, dict):
            continue
        rec = {"figure_id": str(cfg.get("figure_id") or Path(key).stem), "panel": str(cfg.get("panel") or ""),
               "caption": norm(cfg.get("caption") or ""), "axes": {}, "legend": [], "series": [],
               "elements": {}, "image": {}, "digitized": []}
        for axis in ("x", "y"):
            ax = (cfg.get("axes") or {}).get(axis)
            rec["axes"][axis] = axis_summary(ax or {})
        leg = ((cfg.get("legend") or {}).get("entries") or [])
        rec["legend"] = [{"label": norm(e.get("label") or ""), "rgb": [int(v) for v in (e.get("rgb") or [])]}
                         for e in leg if isinstance(e, dict)]
        for s in (cfg.get("series") or []):
            if isinstance(s, dict):
                rec["series"].append({"name": norm(s.get("name") or ""),
                                      "rgb": [int(v) for v in (s.get("rgb") or [])],
                                      "digitize": bool(s.get("digitize", True)),
                                      "tol": int(s.get("tol") or 60)})
        el = cfg.get("elements") or {}
        rec["elements"] = {str(k): norm(v) for k, v in el.items()} if isinstance(el, dict) else {}
        imgp = resolve_image(key, files)
        if imgp is None:
            degradations.append("%s: image %s not found in the input; structure kept without pixels" % (rec["figure_id"], key))
            out.append(rec)
            continue
        try:
            img = read_png(imgp)
        except Exception as e:
            degradations.append("%s: PNG decode failed (%s)" % (imgp.name, e))
            out.append(rec)
            continue
        rec["image"] = image_meta(imgp, img)
        rows = rgb_rows(img)
        calx = calibrate(rec["axes"]["x"]["tick_px"], rec["axes"]["x"]["tick_labels"], rec["axes"]["x"]["scale"])
        caly = calibrate(rec["axes"]["y"]["tick_px"], rec["axes"]["y"]["tick_labels"], rec["axes"]["y"]["scale"])
        rec["calibration"] = {"x": calx, "y": caly}
        if not calx or not caly:
            degradations.append("%s: fewer than two usable ticks; digitization skipped" % rec["figure_id"])
        for s in rec["series"]:
            if not s["digitize"] or not calx or not caly:
                rec["digitized"].append({"name": s["name"], "points": [], "status": "not_digitized",
                                         "reason": "digitize=false" if not s["digitize"] else "axis ticks unusable"})
                continue
            pts = digitize(rows, s, calx, caly)
            rec["digitized"].append({"name": s["name"], "points": pts, "status": "digitized" if pts else "no_pixels",
                                     "n_points": len(pts), "tol": s["tol"]})
            if not pts:
                degradations.append("%s/%s: no pixel within tolerance %d of rgb %s"
                                    % (rec["figure_id"], s["name"], s["tol"], s["rgb"]))
        out.append(rec)
    return out


def image_meta(p, img):
    return {"file": p.name, "width": img["width"], "height": img["height"],
            "color_type": img["color_type"], "bit_depth": img["bit_depth"],
            "palette_entries": len(img["palette"] or []), "sha256": sha256_file(p)}


def figure_digest(fig):
    d = {"figure_id": fig["figure_id"], "panel": fig["panel"], "n_series": len(fig["series"]),
         "x": "%s (%s)" % (fig["axes"].get("x", {}).get("label", ""), fig["axes"].get("x", {}).get("unit", "")),
         "y": "%s (%s)" % (fig["axes"].get("y", {}).get("label", ""), fig["axes"].get("y", {}).get("unit", "")),
         "x_ticks": fig["axes"].get("x", {}).get("tick_labels", []),
         "y_ticks": fig["axes"].get("y", {}).get("tick_labels", []),
         "caption": fig["caption"], "image": fig.get("image", {})}
    for s in fig.get("digitized", []):
        d.setdefault("series", []).append({"name": s["name"], "status": s["status"], "n_points": s.get("n_points", 0)})
    return d


# ============================================================== tables
def build_tables(material, src_name, degradations):
    raw = material.get("tables") if isinstance(material, dict) else None
    out = []
    for t in raw or []:
        if not isinstance(t, dict):
            continue
        cols = [norm(c) for c in (t.get("columns") or [])]
        rows = [[("" if v is None else str(v)) for v in r] for r in (t.get("rows") or []) if isinstance(r, list)]
        if not cols:
            degradations.append("table %s has no columns; skipped" % t.get("table_id"))
            continue
        width = len(cols)
        fixed = []
        for r in rows:
            r = (r + [""] * width)[:width]
            fixed.append(r)
        units = [units_of(c) for c in cols]
        out.append({"table_id": str(t.get("table_id") or "T%02d" % (len(out) + 1)),
                    "caption": norm(t.get("caption") or ""), "columns": cols, "rows": fixed,
                    "n_rows": len(fixed), "n_cols": width, "column_units": units, "source": src_name})
    return out


def units_of(header):
    m = re.search(r"\(([^()]*)\)\s*$", header or "")
    return norm(m.group(1)) if m else ""


def table_digest(t):
    return {"table_id": t["table_id"], "caption": t["caption"], "n_rows": t["n_rows"], "n_cols": t["n_cols"],
            "columns": t["columns"], "column_units": t["column_units"], "source": t["source"]}


# ============================================================== contract
def contract_keys(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict) and oc:
        return list(oc.keys())
    if isinstance(oc, list) and oc:
        return [f if isinstance(f, str) else str((f or {}).get("name") or "field_%d" % (i + 1))
                for i, f in enumerate(oc)]
    return list(DEFAULT_CONTRACT)


def contract_value(key, ctx):
    k = key.lower()
    if k == "case_id":
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if k in ("result", "reading", "payload", "answer"):
        return ctx["result"]
    if "claim" in k:
        return ctx["claims"]
    if "uncertain" in k or "gap" in k or "limit" in k:
        return ctx["uncertainties"]
    if "source" in k or "provenance" in k:
        return ctx["sources"]
    if "digest" in k or "figure_table" in k or "figure" in k and "table" in k:
        return ctx["digest"]
    if "figure" in k:
        return ctx["result"]["figures"]
    if "table" in k or "tabl" in k:
        return ctx["result"]["tables"]
    if "series" in k or "digit" in k:
        return ctx["result"]["digitization"]
    if "artifact" in k or "deliver" in k or "output" in k:
        return ctx["artifacts"]
    if "element" in k or "legend" in k:
        return ctx["result"]["elements"]
    if "coverage" in k or "count" in k or "stat" in k:
        return ctx["counts"]
    if "method" in k or "repro" in k:
        return {"pipeline": "discover -> decode png -> calibrate -> digitize -> claims",
                "deterministic": True, "entry": "scripts/main.py build"}
    if "pending" in k or "human" in k:
        return ctx["pending_human"] or [{"item": "confirm digitized traces", "action": "compare against the panel"}]
    return {"kind": "unrecognised contract key", "key": key,
            "resolved": "echoed verbatim; see result for the full payload"}


def finalize(case, ctx):
    echo = {}
    for k in contract_keys(case):
        v = contract_value(k, ctx)
        if v in (None, "", [], {}) and k != "case_id":
            v = contract_value("result", ctx)
        echo[k] = v
    res = {"case_id": ctx["case_id"], "status": ctx["status"], "summary": ctx["summary"], "output_contract": echo}
    for k, v in echo.items():
        res.setdefault(k, v)
    res.update({"sources": ctx["sources"], "uncertainties": ctx["uncertainties"], "uncertainty": ctx["uncertainties"],
                "claims": ctx["claims"], "errors": ctx["errors"], "degradations": ctx["degradations"],
                "changes": ctx["changes"], "change_records": ctx["changes"], "pending_human": ctx["pending_human"],
                "limits": ctx["limits"], "counts": ctx["counts"], "runtime": ctx["runtime"]})
    return res


# ============================================================== rendering
def write_artifacts(out, ctx):
    figs = ctx["result"]["figures"]
    tabs = ctx["result"]["tables"]
    jwrite(out / "figure_structure.json", {"figures": figs, "digitization": ctx["result"]["digitization"],
                                           "figure_count": len(figs),
                                           "note": "axes/legend/series/calibration/digitized per figure" if figs
                                                   else "no figure could be read from the supplied materials"})
    with (out / "digitized_series.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["figure_id", "panel", "series", "px", "py", "x", "y", "unit_x", "unit_y"])
        for fig in ctx["result"]["figures"]:
            ux = fig["axes"].get("x", {}).get("unit", "")
            uy = fig["axes"].get("y", {}).get("unit", "")
            for s in fig.get("digitized", []):
                for pt in s.get("points", []):
                    w.writerow([fig["figure_id"], fig["panel"], s["name"], pt["px"], pt["py"],
                                pt["x"], pt["y"], ux, uy])
    jwrite(out / "tables.json", {"tables": tabs, "digests": ctx["digest"].get("tables", []), "table_count": len(tabs),
                                 "note": "columns/rows/units per table" if tabs
                                         else "no table could be read from the supplied materials"})
    for t in tabs:
        (out / "tables").mkdir(parents=True, exist_ok=True)
        with (out / "tables" / ("%s.csv" % t["table_id"])).open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(t["columns"])
            for row in t["rows"]:
                w.writerow(row)


def digest_md(ctx):
    d = ctx["digest"]
    lines = ["# Figure & table digest", "",
             "> case `%s` | status **%s** | %s" % (ctx["case_id"], ctx["status"], GEN), ""]
    lines += ["## Figures", ""]
    for f in d.get("figures", []):
        lines += ["- **%s%s** %s x %s px | %s (%s) vs %s (%s)" % (
            f["figure_id"], (" panel " + f["panel"]) if f["panel"] else "", f["image"].get("width", ""),
            f["image"].get("height", ""), f["x"], "", f["y"], ""), "  series: " + ", ".join(
                "%s (%s, %d pts)" % (s["name"], s["status"], s["n_points"]) for s in f.get("series", [])) or "  series: -",
            "  caption: " + (f["caption"] or "-")]
        for s in f.get("series", []):
            lines.append("    - %s -> %s, %d point(s)" % (s["name"], s["status"], s["n_points"]))
    lines += ["", "## Tables", ""]
    for t in d.get("tables", []):
        lines += ["- **%s** %d x %d | %s | units: %s" % (t["table_id"], t["n_rows"], t["n_cols"], t["caption"],
                                                         ", ".join(u or "-" for u in t["column_units"])),
                  "  columns: " + ", ".join(t["columns"])]
    lines += ["", "## Counts", "",
              "- figures %s; tables %s; claims %s; errors %s" % (
                  ctx["counts"]["figures"], ctx["counts"]["tables"], ctx["counts"]["claims"], ctx["counts"]["errors"]), ""]
    return "\n".join(lines)
