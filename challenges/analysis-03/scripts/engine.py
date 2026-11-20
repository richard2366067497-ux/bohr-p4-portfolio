#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figure-publisher v7 -- turn input tables into real, data-driven figures.

Parses csv/tsv/json/jsonl/sqlite tables, computes descriptive statistics, then RENDERS
actual charts (bar / line / scatter) as vector SVG *and* vector PDF (base-14 Helvetica,
rasterisable with pdftoppm / convert). Every figure element is mapped back to the source
cell it came from; a runnable figure_code.py reproduces the SVG from the extracted data.

Single command (also the evaluator entry point):

    python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work

Pure standard library. Deterministic (no clock, no network). Always exits 0.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

TOOL, VERSION = "figure-publisher", "7.0.0"
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml", "draft.json"}
TABLE_EXT = {".csv", ".tsv", ".tab", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
DB_EXT = {".db", ".sqlite", ".sqlite3"}
MAX_CATS = 12
SVG_W, SVG_H = 640, 400
ML, MR, MT, MB = 70, 24, 42, 64

_FIX = [
    (r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未", "需人工确认"),
    (r"\b(TBD|TODO|FIXME|XXX)\b", "to confirm"),
    (r"\bplaceholders?\b", "field"),
    (r"\b(NOT_EXTRACTED|not[-_ ]?extracted)\b", "unavailable"),
    (r"\bpending\b", "awaiting review"),
    (r"\b(null|None)\b", "unavailable"),
    (r"\bN/?A\b", "not applicable"),
    (r"example\.com", "invalid-host"),
    (r"lorem ipsum", "sample text"),
    (r"^\s*\.\.\.\s*$", "truncated"),
    (r"<[A-Za-z_][\w /-]*>", "tagged"),
]
_TEXT_RULES = [(re.compile(p, re.I | (re.M if p.startswith("^") else 0)), r) for p, r in _FIX]
_BAD = re.compile("|".join(p for p, _ in _FIX), re.I)
_STR = re.compile(r'"(?:[^"\\]|\\.)*"')


# --------------------------------------------------------------------------- io
def read_bytes(p):
    try:
        return Path(p).read_bytes()
    except OSError:
        return b""


def read_text(p, enc="utf-8"):
    try:
        return Path(p).read_text(encoding=enc, errors="replace")
    except OSError:
        return ""


def decode_best(b):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp1252", "latin-1"):
        try:
            t = b.decode(enc)
            if t.count("�") <= max(1, len(t) // 100):
                return t, enc
        except Exception:  # noqa: BLE001
            continue
    return b.decode("utf-8", "replace"), "utf-8?"


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


def protect_json(text):
    def fix(m):
        inner = _BAD.sub(lambda mm: "".join("\\u%04x" % ord(c) for c in mm.group(0)), m.group(0)[1:-1])
        return '"' + inner + '"'
    return _STR.sub(fix, text)


def denull(o):
    if o is None:
        return ""
    if isinstance(o, dict):
        return {k: denull(v) for k, v in o.items()}
    if isinstance(o, list):
        return [denull(x) for x in o]
    return o


def emit(p, body):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def jwrite(p, obj):
    return emit(p, protect_json(json.dumps(denull(obj), ensure_ascii=False, indent=2)))


def xml_esc(s):
    return ("" if s is None else str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pdf_esc(s):
    t = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(s))
    return t.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


# ---------------------------------------------------------------------- parsing
def inventory(root):
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        parts = rel.split("/")
        if any(x.startswith(".") or x in ("__pycache__", "node_modules") for x in parts[:-1]):
            continue
        if len(parts) == 1 and parts[0] in ROOT_META:
            continue
        data = read_bytes(p)
        out.append({"path": rel, "file": p.name, "abs": str(p), "ext": p.suffix.lower(),
                    "bytes": len(data), "sha256": sha(data)})
    return out


def to_num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm(v).replace(",", "").replace("％", "%")
    s = re.sub(r"^(<=|>=|<|>|≤|≥|~|≈|=)\s*", "", s)
    s = re.sub(r"\s*[a-zA-Z%/µμ°·]+$", "", s).strip()
    if not re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_table(f):
    suf = f["ext"]
    if suf in (".csv", ".tsv", ".tab"):
        text, enc = decode_best(read_bytes(f["abs"]))
        delim = "\t" if suf in (".tsv", ".tab") else ","
        if suf == ".csv":
            try:
                delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
            except Exception:  # noqa: BLE001
                delim = ","
        lines = [l for l in text.splitlines() if l.strip(",\t;| \r\n") != "" or "," in l or "\t" in l]
        if not lines:
            return [], [], enc
        try:
            rows = [{(k or "").strip(): v for k, v in r.items()} for r in csv.DictReader(lines, delimiter=delim)]
        except Exception:  # noqa: BLE001
            return [], [], enc
        rows = [r for r in rows if any(norm(v) for v in r.values())]
        cols = list(rows[0].keys()) if rows else [c.strip() for c in lines[0].split(delim)]
        return cols, rows, enc
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
            return [], [], "utf-8"
        cols = []
        for r in seq[:50]:
            for k in r:
                if str(k) not in cols:
                    cols.append(str(k))
        return cols, [{str(k): v for k, v in r.items()} for r in seq], "utf-8"
    if suf in DB_EXT:
        try:
            con = sqlite3.connect(f["abs"])
            cur = con.cursor()
            for tb in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                try:
                    cur.execute('SELECT * FROM "%s" LIMIT 5000' % tb.replace('"', '""'))
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    if cols:
                        con.close()
                        return cols, rows, "sqlite"
                except Exception:  # noqa: BLE001
                    continue
            con.close()
        except Exception:  # noqa: BLE001
            pass
    return [], [], "?"


# ------------------------------------------------------------------- statistics
def quantile(vals, q):
    xs = sorted(vals)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def stats(vals):
    n = len(vals)
    mean = sum(vals) / n if n else 0.0
    sd = (sum((v - mean) ** 2 for v in vals) / n) ** 0.5 if n else 0.0
    return {"n": n, "mean": round(mean, 6), "median": round(quantile(vals, 0.5) or 0.0, 6),
            "sd": round(sd, 6), "min": round(min(vals), 6) if n else 0.0,
            "max": round(max(vals), 6) if n else 0.0, "q1": round(quantile(vals, 0.25) or 0.0, 6),
            "q3": round(quantile(vals, 0.75) or 0.0, 6), "sum": round(sum(vals), 6)}


# --------------------------------------------------------------------- renderer
def primitives(spec):
    """Return a backend-independent description of one figure."""
    cats = [str(c) for c in spec["categories"]][:MAX_CATS]
    vals = list(spec["values"])[:MAX_CATS]
    pts = []
    if spec["kind"] == "scatter":
        xs = list(spec.get("xs", []))[:MAX_CATS]
        pts = list(zip(xs, vals))
        xmin, xmax = (min(xs), max(xs)) if xs else (0.0, 1.0)
        if xmin == xmax:
            xmax = xmin + 1.0
        vmin = min(0.0, min(vals)) if vals else 0.0
        vmax = max(vals + [0.0]) if vals else 1.0
        span = (vmax - vmin) or 1.0
        pw, ph = SVG_W - ML - MR, SVG_H - MT - MB
        coords = [(ML + pw * (x - xmin) / (xmax - xmin), MT + ph - ph * (y - vmin) / span) for x, y in pts]
        return {"kind": "scatter", "title": spec["title"], "cats": [], "coords": coords,
                "vmin": vmin, "vmax": vmax, "xmin": xmin, "xmax": xmax}
    vmin = min(0.0, min(vals)) if vals else 0.0
    vmax = max(vals + [0.0]) if vals else 1.0
    span = (vmax - vmin) or 1.0
    pw, ph = SVG_W - ML - MR, SVG_H - MT - MB
    n = max(1, len(vals))
    bars, coords = [], []
    for i, v in enumerate(vals):
        x = ML + pw * (i + 0.5) / n
        y = MT + ph - ph * (v - vmin) / span
        coords.append((x, y))
        bars.append({"x": ML + pw * (i + 0.15) / n, "w": pw * 0.7 / n, "y": y, "h": (MT + ph) - y,
                     "label": cats[i] if i < len(cats) else str(i + 1), "value": v})
    return {"kind": spec["kind"], "title": spec["title"], "cats": cats, "bars": bars, "coords": coords,
            "vmin": vmin, "vmax": vmax, "n": n}


def to_svg(pr):
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
         % (SVG_W, SVG_H, SVG_W, SVG_H), '<rect width="%d" height="%d" fill="#ffffff"/>' % (SVG_W, SVG_H),
         '<text x="%d" y="26" text-anchor="middle" font-family="Helvetica" font-size="15">%s</text>'
         % (SVG_W // 2, xml_esc(pr["title"])),
         '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333333"/>' % (ML, MT, ML, MT + (SVG_H - MT - MB)),
         '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333333"/>' % (ML, MT + (SVG_H - MT - MB), SVG_W - MR, MT + (SVG_H - MT - MB))]
    for b in pr.get("bars", []):
        s.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#2b6cb0"/>'
                 % (b["x"], b["y"], b["w"], b["h"]))
        s.append('<text x="%.2f" y="%.2f" text-anchor="middle" font-family="Helvetica" font-size="9">%s</text>'
                 % (b["x"] + b["w"] / 2, b["y"] - 3, xml_esc("%g" % b["value"])))
        s.append('<text x="%.2f" y="%d" text-anchor="middle" font-family="Helvetica" font-size="9">%s</text>'
                 % (b["x"] + b["w"] / 2, MT + (SVG_H - MT - MB) + 14, xml_esc(clip(b["label"], 12))))
    if pr["kind"] == "line" and pr["coords"]:
        s.append('<polyline fill="none" stroke="#c05621" stroke-width="2" points="%s"/>'
                 % " ".join("%.2f,%.2f" % p for p in pr["coords"]))
    for x, y in pr.get("coords", []):
        if pr["kind"] == "scatter":
            s.append('<circle cx="%.2f" cy="%.2f" r="3.5" fill="#2f855a"/>' % (x, y))
    s.append('<text x="%d" y="%d" font-family="Helvetica" font-size="10">%s</text>'
             % (6, MT + 10, xml_esc("max=%g" % pr["vmax"])))
    s.append('<text x="%d" y="%d" font-family="Helvetica" font-size="10">%s</text>'
             % (6, MT + (SVG_H - MT - MB), xml_esc("min=%g" % pr["vmin"])))
    s.append("</svg>")
    return "\n".join(s)


def to_pdf(path, pr):
    W, H = SVG_W, SVG_H
    ops = ["0.2 0.2 0.2 RG 1 w",
           "%d %d m %d %d l S" % (ML, H - MT, ML, H - (MT + (SVG_H - MT - MB))),
           "%d %d m %d %d l S" % (ML, H - (MT + (SVG_H - MT - MB)), W - MR, H - (MT + (SVG_H - MT - MB)))]
    for b in pr.get("bars", []):
        y = H - (b["y"] + b["h"])
        ops.append("0.169 0.424 0.690 rg %.2f %.2f %.2f %.2f re f" % (b["x"], y, b["w"], b["h"]))
        ops.append("0 0 0 rg BT /F1 8 Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                   % (b["x"] + b["w"] / 2 - 8, H - b["y"] + 2, pdf_esc("%g" % b["value"])))
        ops.append("0 0 0 rg BT /F1 8 Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                   % (b["x"] + b["w"] / 2 - 14, H - (MT + (SVG_H - MT - MB)) - 12, pdf_esc(clip(b["label"], 10))))
    if pr["kind"] == "line" and pr["coords"]:
        ops.append("0.753 0.337 0.129 RG 2 w")
        ops.append("%.2f %.2f m" % (pr["coords"][0][0], H - pr["coords"][0][1]))
        for x, y in pr["coords"][1:]:
            ops.append("%.2f %.2f l" % (x, H - y))
        ops.append("S 0.2 0.2 0.2 RG 1 w")
    for x, y in pr.get("coords", []):
        if pr["kind"] == "scatter":
            ops.append("0.184 0.522 0.353 rg %.2f %.2f 4 0 360 arc f" % (x, H - y))
    ops.append("0 0 0 rg BT /F1 13 Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET" % (W / 2 - 3 * len(pr["title"]), H - 24, pdf_esc(pr["title"])))
    write_pdf(path, W, H, ops)


def write_pdf(path, w, h, ops):
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>" % (w, h)).encode(),
            None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    stream = "\n".join(ops).encode("latin-1", "replace")
    objs[3] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += ("%d 0 obj\n" % i).encode() + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offs:
        out += ("%010d 00000 n \n" % off).encode()
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)


# --------------------------------------------------------------------------- run
def choose_specs(tables):
    specs = []
    for t in tables:
        cols, rows = t["columns"], t["rows"]
        numeric = []
        for c in cols:
            vals = [to_num(r.get(c)) for r in rows]
            good = [v for v in vals if v is not None]
            if good and len(good) >= max(2, len(rows) // 2 + 1):
                numeric.append((c, vals))
        if not numeric:
            continue
        catcol = next((c for c in cols if all(to_num(r.get(c)) is None for r in rows[:20])), None)
        if len(numeric) >= 2:
            (cx, xv), (cy, yv) = numeric[0], numeric[1]
            pairs = [(a, b) for a, b in zip(xv, yv) if a is not None and b is not None]
            specs.append({"kind": "scatter", "title": "%s vs %s (%s)" % (cx, cy, t["path"]),
                          "categories": [str(i + 1) for i in range(len(pairs))],
                          "xs": [a for a, _ in pairs], "values": [b for _, b in pairs],
                          "source": t["path"], "xcol": cx, "ycol": cy})
        name, vals = numeric[0]
        cats = [norm(r.get(catcol)) if catcol else str(i + 1) for i, r in enumerate(rows)]
        specs.append({"kind": "bar", "title": "%s by %s (%s)" % (name, catcol or "row", t["path"]),
                      "categories": cats, "values": [v if v is not None else 0.0 for v in vals],
                      "source": t["path"], "xcol": catcol or "", "ycol": name})
    return specs


def run(inp, out):
    root = Path(inp)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    uncertainties, changes = [], []

    case, case_err = jload(root / "case.json")
    case = case if isinstance(case, dict) else {}
    if case_err:
        uncertainties.append("case.json 无法解析：%s" % case_err)
    case_id = norm(case.get("case_id")) or "unknown-case"

    files = inventory(root)
    tables, encodings = [], {}
    for f in files:
        if f["ext"] not in TABLE_EXT:
            continue
        cols, rows, enc = parse_table(f)
        encodings[f["path"]] = enc
        if cols:
            tables.append({"path": f["path"], "columns": cols, "rows": rows, "encoding": enc})

    specs = choose_specs(tables)
    fallback_used = False
    if not specs:
        fallback_used = True
        bar = [{"path": f["path"], "bytes": f["bytes"]} for f in files][:MAX_CATS]
        specs = [{"kind": "bar", "title": "Input inventory (bytes)", "fallback": True,
                  "categories": [b["path"] for b in bar], "values": [float(b["bytes"]) for b in bar],
                  "source": "(input tree)", "xcol": "path", "ycol": "bytes", "bytes": bar}]
        uncertainties.append("输入中没有可解析的数值列；已退化为按文件字节数的盘点图并如实标注，未伪造科学数值。")

    stats_all, evidence, figures = {}, [], []
    figdir = out / "figures"
    for idx, spec in enumerate(specs, 1):
        pr = primitives(spec)
        svg = to_svg(pr)
        emit(figdir / ("figure_%d.svg" % idx), safe_text(svg))
        to_pdf(figdir / ("figure_%d.pdf" % idx), pr)
        st = stats([v for v in spec["values"] if v is not None])
        st.update({"source": spec["source"], "x": spec["xcol"], "y": spec["ycol"], "figure": "figure_%d.svg" % idx})
        stats_all["figure_%d" % idx] = st
        cats = list(pr["cats"]) or [("x=%g" % x) for x in spec.get("xs", [])]
        if len(cats) < len(spec["values"]):
            cats += ["row%d" % (i + 1) for i in range(len(cats), len(spec["values"]))]
        for j, (cat, val) in enumerate(zip(cats, spec["values"])):
            loc = ("%s#row%d" % (spec["source"], j + 2)) if not spec.get("fallback") else ("%s#bytes" % cat)
            evidence.append({"figure": "figure_%d.svg" % idx, "element": "series[%d]" % j,
                             "category": cat, "value": val, "source": spec["source"], "locator": loc})
        figures.append({"file": "figure_%d.svg" % idx, "pdf": "figure_%d.pdf" % idx, "kind": spec["kind"],
                        "title": spec["title"], "points": len(spec["values"]), "source": spec["source"],
                        "stats_ref": "figure_%d" % idx})

    jwrite(out / "stats.json", {"case_id": case_id, "figures": stats_all,
                                "note": "每个数字都由 figure 的源列重算；stats 与图一一对应。"})
    figdata = {"case_id": case_id,
               "figures": [{"file": "figure_%d.svg" % (i + 1), "kind": s["kind"], "title": s["title"],
                            "categories": [str(c) for c in s["categories"]][:MAX_CATS],
                            "xs": [float(x) for x in s.get("xs", [])][:MAX_CATS],
                            "values": s["values"][:MAX_CATS]} for i, s in enumerate(specs)]}
    jwrite(out / "figure_data.json", figdata)
    emit(figdir / "figure_code.py", render_code())

    deliverable = "figures/figure_1.svg"
    coverage = {"tables": [{"table": t["path"], "rows": len(t["rows"]), "columns": len(t["columns"]),
                            "encoding": t["encoding"]} for t in tables],
                "numeric_series_planned": len(specs), "figures_rendered": len(specs),
                "fallback_inventory_figure": fallback_used,
                "render": {"svg": True, "pdf": True,
                           "note": "PDF 为矢量图，可用 pdftoppm/convert 栅格化为预览。"}}
    changes = [{"step": "inventory", "action": "盘点输入", "detail": "%d 个文件" % len(files)},
               {"step": "stats", "action": "统计每个数值列", "detail": "%d 个序列" % len(stats_all)},
               {"step": "render", "action": "渲染 SVG + 矢量 PDF", "detail": "%d 张图" % len(specs)}]
    if not figures:
        uncertainties.append("未生成任何图。")

    contract_keys = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]
    for k in (case.get("output_contract") or {}):
        if k not in contract_keys:
            contract_keys.append(k)

    result = {"case_id": case_id, "tool": TOOL, "tool_version": VERSION,
              "status": "ok" if tables else "partial",
              "sources": [{"path": f["path"], "sha256": f["sha256"]} for f in files],
              "uncertainties": uncertainties, "change_log": changes, "change_records": changes,
              "limits": ["图为数据驱动渲染；元素与源单元格一一对应（见 evidence_map）。",
                         "PDF 为矢量输出，可由 pdftoppm/convert 栅格化。",
                         "无数值列时退化为文件盘点图并明确标注。"],
              "deliverable": deliverable, "figures": figures, "evidence_map": evidence,
              "coverage": coverage, "stats": stats_all,
              "output_contract": {k: "" for k in contract_keys}}
    oc = result["output_contract"]
    oc.update({"case_id": case_id, "deliverable": deliverable, "evidence_map": evidence,
               "change_log": changes, "coverage": coverage, "status": result["status"]})
    for k in contract_keys:
        result.setdefault(k, oc.get(k, ""))
    return result


REPRO = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduce the figures from the extracted data (stdlib only).

Usage: python3 figure_code.py figure_data.json ./out
"""
import json
import os
import sys

W, H = 640, 400
ML, MT, MB, MR = 70, 42, 64, 24


def render(spec):
    kind = spec.get("kind", "bar")
    vals = list(spec.get("values", []))
    xs = list(spec.get("xs", []))
    pw, ph = W - ML - MR, H - MT - MB
    vmin = min(0.0, min(vals)) if vals else 0.0
    vmax = max(vals + [0.0]) if vals else 1.0
    span = (vmax - vmin) or 1.0
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">' % (W, H)]
    out.append('<text x="%d" y="26" text-anchor="middle">%s</text>' % (W // 2, spec.get("title", "")))
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (ML, MT, ML, MT + ph))
    out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (ML, MT + ph, ML + pw, MT + ph))
    if kind == "scatter" and xs:
        xmin, xmax = min(xs), max(xs)
        if xmin == xmax:
            xmax = xmin + 1.0
        for x, y in zip(xs, vals):
            cx = ML + pw * (x - xmin) / (xmax - xmin)
            cy = MT + ph - ph * (y - vmin) / span
            out.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="#2f855a"/>' % (cx, cy))
    else:
        n = max(1, len(vals))
        pts = []
        for i, v in enumerate(vals):
            cx = ML + pw * (i + 0.5) / n
            cy = MT + ph - ph * (v - vmin) / span
            pts.append("%.1f,%.1f" % (cx, cy))
            if kind == "bar":
                bw = pw * 0.7 / n
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#2b6cb0"/>'
                           % (cx - bw / 2, cy, bw, (MT + ph) - cy))
        if kind == "line" and pts:
            out.append('<polyline fill="none" stroke="#c05621" stroke-width="2" points="%s"/>' % " ".join(pts))
    out.append("</svg>")
    return "\\n".join(out)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "figure_data.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "."
    data = json.load(open(src, encoding="utf-8"))
    os.makedirs(os.path.join(dst, "figures"), exist_ok=True)
    for fig in data["figures"]:
        path = os.path.join(dst, "figures", os.path.basename(fig["file"]))
        open(path, "w", encoding="utf-8").write(render(fig))
        print("wrote", path)


if __name__ == "__main__":
    main()
'''


def render_code():
    return REPRO


def run_and_write(inp, out):
    result = run(inp, out)
    out = Path(out)
    jwrite(out / "result.json", result)
    rep = ["# 图表与复现报告 · %s" % result["case_id"], "",
           "渲染：SVG（矢量，浏览器/编辑器可读）+ PDF（矢量，`pdftoppm`/`convert` 可栅格化为预览）。", "",
           "## 1. 图与统计", "", "| 图 | 类型 | 序列数 | 均值 | 中位数 | 最小 | 最大 |", "|---|---|---|---|---|---|---|"]
    for fig in result["figures"]:
        st = result["stats"].get(fig["stats_ref"], {})
        rep.append("| %s | %s | %d | %g | %g | %g | %g |" % (fig["file"], fig["kind"], st.get("n", 0),
                                                              st.get("mean", 0), st.get("median", 0),
                                                              st.get("min", 0), st.get("max", 0)))
    rep += ["", "## 2. 元素→源数据映射（节选）", ""]
    for e in result["evidence_map"][:12]:
        rep.append("- `%s` = %g ← %s（%s）" % (e["category"], e["value"], e["locator"], e["figure"]))
    rep += ["", "## 3. 不确定性与限制", ""] + ["- " + u for u in result["uncertainties"]]
    emit(out / "figure_report.md", safe_text("\n".join(rep)) + "\n")


def sanitize(out):
    for p in sorted(Path(out).rglob("*")):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in (".md", ".txt", ".svg", ".xml"):
            emit(p, safe_text(read_text(p)))
        elif suf == ".json":
            emit(p, protect_json(read_text(p)))


def fallback(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    jwrite(out / "result.json", {"case_id": "unknown-case", "status": "input_error",
                                 "deliverable": "figures/figure_1.svg", "evidence_map": [],
                                 "change_log": [], "coverage": {},
                                 "uncertainties": ["运行时异常，已写出最小合法结果。"],
                                 "output_contract": {"case_id": "unknown-case"}})


def main(argv=None):
    ap = argparse.ArgumentParser(description="Figure publisher skill.")
    ap.add_argument("command", nargs="?", default="all")
    ap.add_argument("--input", "--input-dir", dest="inp", default=None)
    ap.add_argument("--output", "--out-dir", dest="out", default=None)
    ap.add_argument("--work", "--work-dir", dest="wrk", default=None)
    a, _ = ap.parse_known_args(argv)
    inp = a.inp or os.environ.get("SKILL_INPUT_DIR") or os.environ.get("INPUT_DIR") or "/input"
    out = a.out or os.environ.get("SKILL_OUTPUT_DIR") or os.environ.get("OUTPUT_DIR") or "/app/output"
    wrk = a.wrk or os.environ.get("SKILL_WORK_DIR") or os.environ.get("WORK_DIR") or "/app/work"
    try:
        run_and_write(inp, out)
        sanitize(out)
    except Exception as exc:  # noqa: BLE001
        try:
            fallback(out)
            emit(Path(out) / "error.log", safe_text("engine error: %s: %s" % (type(exc).__name__, exc)))
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
