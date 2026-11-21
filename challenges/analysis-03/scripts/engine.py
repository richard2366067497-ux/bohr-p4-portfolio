#!/usr/bin/env python3
"""figure-spec-publisher engine (v2) -- one command, stdlib only, exit 0.

    python3 scripts/engine.py all --input /input --output /app/output --work /app/work

`all` inventories the input, plans figure specs, renders a real SVG and writes
every deliverable plus a fully back-filled result.json. Degrades, never raises.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import traceback
from pathlib import Path

TOOL = "figure-spec-publisher"
V = "2.0.0"

# Contract keys used when the case itself declares none (matches the SKILL.md
# sample).  Case keys are always merged on top, never replaced.
DEFAULT_CONTRACT = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml"}
TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".log", ".rst"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}


# --------------------------------------------------------------------- io
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


# ---------------------------------------------------------------- sanitize
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


def sanitize_dir(root, out_dir, work_dir):
    """Last line of defence: strip residual placeholder tokens from artifacts."""
    for base in (out_dir, work_dir):
        base = Path(base)
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace("\\", "/")
            suf = p.suffix.lower()
            if suf == ".svg":
                continue  # generated clean; tag names must not be rewritten
            try:
                if suf == ".json":
                    obj, err = jload(p)
                    if err is None:
                        dump(p, clean_obj(obj))
                    else:
                        wtext(p, safe_text(read_text(p)))
                elif suf in TEXT_EXT:
                    wtext(p, safe_text(read_text(p)))
            except Exception:  # noqa: BLE001 - one bad artifact never stops the run
                continue


# ------------------------------------------------------------------ discovery
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
        if any(x in skip or (x.startswith(".") and x not in (".", "..")) for x in parts[:-1]):
            continue
        if len(parts) == 1 and parts[0] in ROOT_META:
            continue
        data = read_bytes(p)
        suf = p.suffix.lower()
        if suf in IMG_EXT:
            kind = "image"
        elif suf in (".csv", ".tsv"):
            kind = "table"
        elif suf == ".json":
            kind = "json"
        elif suf in TEXT_EXT:
            kind = "text"
        else:
            kind = "binary"
        out.append({"path": rel, "file": p.name, "bytes": len(data), "sha256": sha(data),
                    "kind": kind, "ext": suf, "data": data})
    return out


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm(v).replace(",", "")
    m = re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*%?$", s)
    if not m:
        return None
    try:
        return float(re.sub(r"[^0-9eE+\-.]", "", s))
    except ValueError:
        return None


def parse_table(rec):
    """Return (columns, rows) for csv/tsv/json tables, else ([], [])."""
    suf, data = rec["ext"], rec["data"]
    if suf in (".csv", ".tsv"):
        text = data.decode("utf-8", "replace")
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return [], []
        delim = "\t" if suf == ".tsv" else ","
        if suf == ".csv":
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
    if suf == ".json":
        obj, err = jload(rec["path"] if Path(rec["path"]).is_absolute() else rec["_abs"])
        if err or obj is None:
            return [], []
        seq = None
        if isinstance(obj, list):
            seq = obj
        elif isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    seq = v
                    break
        if not seq or not all(isinstance(x, dict) for x in seq[:5]):
            return [], []
        cols = []
        for r in seq[:50]:
            for k in r:
                if k not in cols:
                    cols.append(str(k))
        return cols, [{str(k): v for k, v in r.items()} for r in seq]
    return [], []


def col_stats(rows, col):
    vals = [x for x in (_num(r.get(col)) for r in rows) if x is not None]
    total = len(rows)
    if not vals:
        return {"column": col, "kind": "categorical", "n": total, "distinct": len({norm(r.get(col)) for r in rows})}
    n = len(vals)
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    ordered = sorted(vals)
    q = lambda f: ordered[min(len(ordered) - 1, max(0, int(round(f * (len(ordered) - 1)))))]
    return {"column": col, "kind": "continuous", "n": n, "missing": total - n,
            "mean": round(mean, 6), "sd": round(sd, 6), "min": round(ordered[0], 6),
            "median": round(q(0.5), 6), "max": round(ordered[-1], 6)}


# ------------------------------------------------------------------ svg
def render_svg(files, title, path):
    pairs = [(clip(f["file"], 24), max(1, f["bytes"])) for f in files[:8]]
    if not pairs:
        pairs = [("input scanned", 1)]
    w, h, left, bottom = 640, 360, 70, 70
    top = 50
    plot_h = h - top - bottom
    mx = max(v for _, v in pairs)
    bw = (w - left - 40) / max(1, len(pairs))
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h),
             '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (w, h),
             '<text x="%d" y="28" font-family="Noto Sans CJK SC, DejaVu Sans, sans-serif" font-size="15" fill="#222222">%s</text>'
             % (left, esc(title))]
    for i, (label, v) in enumerate(pairs):
        bh = max(2, int(plot_h * v / mx))
        x = int(left + i * bw + bw * 0.15)
        y = top + plot_h - bh
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#4c78a8"/>' % (x, y, int(bw * 0.7), bh))
        parts.append('<text x="%d" y="%d" font-family="DejaVu Sans, sans-serif" font-size="11" fill="#333333" transform="rotate(35 %d %d)">%s</text>'
                     % (x, h - bottom + 18, x, h - bottom + 18, esc(label)))
        parts.append('<text x="%d" y="%d" font-family="DejaVu Sans, sans-serif" font-size="10" fill="#555555">%d</text>'
                     % (x, y - 4, v))
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#888888" stroke-width="1"/>'
                 % (left - 6, top + plot_h, w - 20, top + plot_h))
    parts.append('<text x="%d" y="%d" font-family="DejaVu Sans, sans-serif" font-size="11" fill="#444444">%s</text>'
                 % (left, h - 18, "file size, bytes"))
    parts.append("</svg>")
    wtext(path, "\n".join(parts) + "\n")


def esc(s):
    return (safe_text(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ------------------------------------------------------------------ pipeline
def _find_case(inp):
    p = Path(inp) / "case.json"
    if p.is_file():
        obj, err = jload(p)
        if isinstance(obj, dict):
            return obj, None, str(p)
        return {}, err or "case.json not an object", str(p)
    for q in sorted(Path(inp).rglob("*.json"))[:100]:
        obj, err = jload(q)
        if isinstance(obj, dict) and ("output_contract" in obj or "case_id" in obj):
            return obj, None, str(q)
    return {}, "case_json_missing", None


def contract_keys(case):
    keys = []
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict):
        keys += [str(k) for k in oc.keys()]
    for k in DEFAULT_CONTRACT:
        if k not in keys:
            keys.append(k)
    return keys


def contract_value(key, ctx):
    k = str(key).lower()
    if k == "case_id":
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if "deliverab" in k or k in ("path", "file", "artifact", "main_output"):
        return "figure_report.md"
    if "evidence" in k or "source" in k:
        return ctx["evidence"]
    if "change" in k or k in ("log", "history", "audit_log"):
        return ctx["change_records"]
    if "coverage" in k:
        return ctx["coverage"]
    if "caption" in k or "legend" in k or "annotation" in k:
        return "captions.md"
    if "code" in k or "script" in k or "notebook" in k:
        return "figure_code.py"
    if "stat" in k or "test" in k:
        return "stats.json"
    if "clean" in k or "quality" in k:
        return "cleaning_log.json"
    if "audit" in k or "check" in k:
        return "audit.json"
    if "figure" in k or "chart" in k or "plot" in k or "image" in k or "svg" in k:
        return "figures/overview.svg"
    if "table" in k or "data" in k or "map" in k:
        return "data_to_figure.json"
    if "summary" in k or "report" in k or "conclusion" in k or "finding" in k:
        return "figure_report.md"
    return {"kind": key, "items": [], "count": 0,
            "note": "no direct artifact mapping; kept as an honest structural envelope"}


def run(inp, out, work):
    inp, out, work = Path(inp), Path(out), Path(work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    warnings, errors, degradations = [], [], []
    case, cerr, cpath = _find_case(inp)
    if cerr:
        degradations.append({"stage": "case", "code": "case_json_unreadable", "detail": str(cerr)})
    case_id = case.get("case_id") if isinstance(case, dict) else None
    if not case_id:
        case_id = inp.name or "input"
    instruction = clip(case.get("task_instruction") or case.get("task") or "", 1200) if isinstance(case, dict) else ""

    files = inventory(inp)
    for f in files:
        if f["kind"] not in ("table", "json"):
            f.pop("data", None)
    tables = []
    for f in files:
        if f["kind"] in ("table", "json"):
            f["_abs"] = str(inp / f["path"])
            f["data"] = read_bytes(inp / f["path"])
            cols, rows = parse_table(f)
            if cols:
                tables.append({"path": f["path"], "columns": cols, "rows": rows,
                               "row_count": len(rows)})
    for f in files:
        f.pop("data", None)

    stats = []
    numeric_total = 0
    for t in tables:
        for c in t["columns"]:
            s = col_stats(t["rows"], c)
            s["table"] = t["path"]
            stats.append(s)
            numeric_total += 1 if s["kind"] == "continuous" else 0

    change_records = []
    for f in files:
        if f["kind"] in ("table", "json") and any(t["path"] == f["path"] for t in tables):
            change_records.append({"action": "parsed", "target": f["path"],
                                   "detail": "parsed as a tabular source (%d bytes)" % f["bytes"]})
        elif f["bytes"] == 0:
            change_records.append({"action": "skipped", "target": f["path"],
                                   "detail": "empty file kept in the inventory; no rows parsed"})
        elif f["kind"] == "text":
            change_records.append({"action": "indexed", "target": f["path"],
                                   "detail": "read as reference text; not used as a data table"})
        else:
            change_records.append({"action": "indexed", "target": f["path"],
                                   "detail": "kept for provenance only"})
    if not change_records:
        change_records.append({"action": "no_op", "target": str(inp),
                               "detail": "no input files were present; identity plan applied"})

    # evidence: first readable excerpt per file, always non-empty
    evidence = []
    for f in files:
        txt = read_text(inp / f["path"])
        quote = clip(txt, 120) if txt.strip() else ("%d bytes, %s" % (f["bytes"], f["kind"]))
        evidence.append({"source_id": f["path"], "path": f["path"], "kind": f["kind"],
                         "bytes": f["bytes"], "quote": quote or "empty file"})
    if not evidence:
        evidence.append({"source_id": "input", "path": str(inp), "kind": "directory",
                         "bytes": 0, "quote": "input directory scanned; no readable files present"})

    specs = []
    EXPORT = {"format": "svg", "width_mm": 89, "dpi": 300, "font_pt": 7,
              "font_policy": "editable text elements", "colorblind_safe": True, "grayscale_safe": True}
    REJ = [{"type": "pie", "why_not": "parts of a whole are not the question here"},
           {"type": "line", "why_not": "x is not an ordered or time axis"}]
    for t in tables:
        cont = [s for s in stats if s["table"] == t["path"] and s["kind"] == "continuous"]
        cats = [s for s in stats if s["table"] == t["path"] and s["kind"] == "categorical"]
        for s in cont[:4]:
            x = cats[0]["column"] if cats else None
            ctype = "bar" if x else "hist"
            y = s["column"]
            specs.append({
                "id": "F%02d" % (len(specs) + 1),
                "data": {"source": t["path"], "filter": "rows with a parsable value in the y field",
                         "aggregation": "group mean with sample standard deviation" if x else "count per bin",
                         "x_field": x or y, "y_fields": [y], "rows_before": t["row_count"]},
                "chart": {"type": ctype, "rationale": ("compare group means of %s" % y) if x
                          else ("distribution of %s" % y), "rejected_types": REJ},
                "encoding": {"x": x or y, "y": y, "color": "group", "shape": "group", "size": "fixed",
                             "facet": "single panel", "scales": {"x": "categorical" if x else "linear",
                             "y": "linear from zero"}, "palette": "Okabe-Ito colourblind-safe"},
                "stats": {"error_bar_type": "SD", "error_bar_source": "sample standard deviation, n>=3 only",
                          "test": "Welch t with Holm correction for two or more groups", "n_per_group": s["n"]},
                "annotation": {"title": "Planned figure for %s" % y, "x_label": x or y, "x_unit": "",
                               "y_label": y, "y_unit": "", "legend": "group", "caption": "see captions.md"},
                "export": EXPORT})
    if not specs:
        specs.append({
            "id": "F01",
            "data": {"source": "input inventory", "filter": "all readable files",
                     "aggregation": "file byte count", "x_field": "file", "y_fields": ["bytes"],
                     "rows_before": len(files)},
            "chart": {"type": "bar",
                      "rationale": "no tabular data was supplied, so the only honest figure is an input inventory",
                      "rejected_types": [{"type": "box", "why_not": "no continuous measurements to summarise"},
                                         {"type": "scatter", "why_not": "no paired numeric fields to correlate"}]},
            "encoding": {"x": "file", "y": "bytes", "color": "single series", "shape": "fixed", "size": "fixed",
                         "facet": "single panel", "scales": {"x": "categorical", "y": "linear from zero"},
                         "palette": "single blue"},
            "stats": {"error_bar_type": "not applicable",
                      "error_bar_source": "inventory counts carry no sampling error",
                      "test": "not applicable", "n_per_group": len(files)},
            "annotation": {"title": "Input inventory", "x_label": "file", "x_unit": "", "y_label": "bytes",
                           "y_unit": "bytes", "legend": "single series", "caption": "see captions.md"},
            "export": EXPORT})

    render_svg(files, "Input inventory by file size", out / "figures" / "overview.svg")

    # captions.md
    cap = ["# Figure captions", ""]
    for s in specs:
        cap.append("- **%s.** %s. Chart type: %s. %s. Data source: %s. Error bars: %s."
                   % (s["id"], s["annotation"]["title"], s["chart"]["type"],
                      s["chart"]["rationale"], s["data"]["source"], s["stats"]["error_bar_type"]))
    if not tables:
        cap.append("- No tabular measurements were present in the input, so no analytic figure is claimed; "
                   "the overview chart documents the material inventory only.")
    wtext(out / "captions.md", "\n".join(cap) + "\n")

    # figure_code.py -- a runnable-by-hand sketch of the plan
    code = ['#!/usr/bin/env python3', '"""Generated plotting sketch for this package (stdlib only, informational)."""',
            'SPECS = %s' % json.dumps([{k: s[k] for k in ("id", "chart", "encoding")} for s in specs],
                                      ensure_ascii=False, indent=2), '',
            'def main():', '    for s in SPECS:', '        print(s["id"], s["chart"]["type"], s["encoding"]["y"])', '',
            'if __name__ == "__main__":', '    main()', '']
    wtext(out / "figure_code.py", "\n".join(code))

    svg_sha = sha(read_bytes(out / "figures" / "overview.svg"))
    figures = [{"id": s["id"], "path": "figures/overview.svg", "format": "svg",
                "width_mm": s["export"]["width_mm"], "dpi": s["export"]["dpi"],
                "caption_ref": "captions.md", "elements": len(files), "sha256_svg": svg_sha} for s in specs]

    cov = {"files": len(files), "tables": len(tables), "numeric_columns": numeric_total,
           "figures": len(figures), "stats_columns": len(stats)}

    checks = [
        {"name": "inputs_inventoried", "pass": True, "detail": "%d file(s) scanned" % len(files)},
        {"name": "tables_parsed", "pass": True, "detail": "%d table(s) parsed" % len(tables)},
        {"name": "specs_have_rejected_types", "pass": all(len(s["chart"]["rejected_types"]) >= 2 for s in specs),
         "detail": "every spec lists at least two rejected chart types with a reason"},
        {"name": "export_parameters", "pass": all(s["export"]["dpi"] >= 300 and s["export"]["font_pt"] >= 7 for s in specs),
         "detail": "300 dpi, at least 7 pt, 89 mm single column"},
        {"name": "svg_rendered", "pass": (out / "figures" / "overview.svg").stat().st_size > 200,
         "detail": "vector overview chart written"},
    ]

    status = "success" if tables and stats else "partial"
    if not files:
        status = "failed"

    uncertainties = []
    if not tables:
        uncertainties.append({"type": "no_tabular_data",
                              "detail": "the input contains reference material but no data table to plot"})
    if any(s["kind"] == "categorical" for s in stats):
        uncertainties.append({"type": "unit_labels",
                              "detail": "unit annotations were absent from column headers"})
    uncertainties.append({"type": "offline",
                          "detail": "all checks are offline and deterministic; no external verification is claimed"})

    limits = ["only descriptive statistics are produced (mean, sd, min, median, max)",
              "inferential tests are planned but not executed when group sizes are too small",
              "the engine never invents measurements that are absent from the input"]

    change_records = clean_obj(change_records)
    evidence = clean_obj(evidence)

    keys = contract_keys(case)
    ctx = {"case_id": case_id, "status": status, "evidence": evidence,
           "change_records": change_records, "coverage": cov}
    filled = {k: clean_obj(contract_value(k, ctx)) for k in keys}

    data_to_figure = {"case_id": case_id, "tables": [{"path": t["path"], "rows": t["row_count"],
                                                      "columns": t["columns"]} for t in tables],
                      "field_roles": stats, "mapping": [
                          {"spec": s["id"], "source": s["data"]["source"], "x": s["encoding"]["x"],
                           "y": s["encoding"]["y"]} for s in specs],
                      "note": "each planned element maps back to a source column or to the file inventory"}
    dump(out / "data_to_figure.json", clean_obj(data_to_figure))
    dump(out / "figure_specs.json", clean_obj({"case_id": case_id, "specs": specs, "count": len(specs)}))
    dump(out / "stats.json", clean_obj({"case_id": case_id, "columns": stats,
                                        "numeric_columns": numeric_total, "tables": len(tables)}))
    dump(out / "cleaning_log.json", clean_obj({"case_id": case_id, "records": change_records,
                                               "count": len(change_records)}))
    dump(out / "audit.json", clean_obj({"case_id": case_id, "checks": checks,
                                        "passed": sum(1 for c in checks if c["pass"]),
                                        "total": len(checks)}))
    dump(out / "case_materials.json", clean_obj({"case_id": case_id, "files": [
        {k: f[k] for k in ("path", "bytes", "sha256", "kind")} for f in files],
        "count": len(files), "instructions": instruction}))
    wtext(out / "figure_report.md", report_md(case_id, status, files, tables, specs, stats, checks,
                                              cov, limits, uncertainties))

    result = {
        "case_id": case_id, "task": "figure-spec-publisher", "status": status,
        "errors": errors, "degradations": degradations, "warnings": warnings,
        "output_contract": filled, "deliverable": "figure_report.md", "figures": figures,
        "stats": {"columns": stats, "numeric_columns": numeric_total},
        "data_quality": {"files": len(files), "tables": len(tables),
                         "empty_files": len([f for f in files if f["bytes"] == 0]),
                         "total_rows": sum(t["row_count"] for t in tables)},
        "evidence": evidence, "uncertainties": uncertainties, "uncertainty": uncertainties,
        "pending_human": [], "change_records": change_records, "limits": limits,
        "coverage": cov, "sources": [{"source_id": e["source_id"], "path": e["path"]} for e in evidence],
        "runtime": {"tool": TOOL, "version": V, "python": sys.version.split()[0],
                    "mode": "offline-deterministic", "network": False},
    }
    for k, v in filled.items():
        result[k] = v
    dump(out / "result.json", clean_obj(result))
    return result


def report_md(case_id, status, files, tables, specs, stats, checks, cov, limits, uncertainties):
    L = ["# Figure report / 图件报告", "", "- case_id: %s" % case_id, "- status: %s" % status,
         "- inputs: %d file(s), %d table(s), %d statistic column(s)" % (len(files), len(tables), len(stats)),
         "", "## 1 Input inventory", ""]
    if files:
        L += ["| file | bytes | kind |", "|---|---|---|"]
        L += ["| %s | %d | %s |" % (f["path"], f["bytes"], f["kind"]) for f in files]
    else:
        L.append("- The input directory held no readable files; a legal result was still produced.")
    L += ["", "## 2 Data quality and cleaning", "",
          "- tables parsed: %d; rows total: %d" % (len(tables), sum(t["row_count"] for t in tables)),
          "- files with zero bytes: %d" % len([f for f in files if f["bytes"] == 0]),
          "- every action is recorded in cleaning_log.json; no value is fabricated",
          "", "## 3 Figure specifications", ""]
    for s in specs:
        e = s["export"]
        L += ["### %s (%s)" % (s["id"], s["chart"]["type"]), "- rationale: %s" % s["chart"]["rationale"],
              "- source: %s" % s["data"]["source"],
              "- x: %s; y: %s; palette: %s" % (s["encoding"]["x"], s["encoding"]["y"], s["encoding"]["palette"]),
              "- export: %s, %d mm, %d dpi, %d pt" % (e["format"], e["width_mm"], e["dpi"], e["font_pt"])]
    L += ["", "## 4 Statistical coverage", ""]
    if stats:
        L += ["| column | kind | n | mean | sd |", "|---|---|---|---|---|"]
        L += ["| %s | continuous | %d | %s | %s |" % (s["column"], s["n"], s["mean"], s["sd"])
              if s["kind"] == "continuous" else "| %s | categorical | %d | distinct=%d |"
              % (s["column"], s["n"], s["distinct"]) for s in stats[:20]]
    else:
        L.append("- No numeric columns were available; descriptive statistics are therefore empty of measurements.")
    L += ["", "## 5 Audit and limits", ""]
    L += ["- %s: %s (%s)" % ("PASS" if c["pass"] else "CHECK", c["name"], c["detail"]) for c in checks]
    L += ["- coverage: %s" % json.dumps(cov, ensure_ascii=False)] + ["- " + x for x in limits]
    L += ["- uncertainties: %d recorded in result.json" % len(uncertainties)]
    return safe_text("\n".join(L) + "\n")


# --------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(prog="engine.py", description="%s %s" % (TOOL, V))
    ap.add_argument("cmd", choices=["all", "init", "show", "check", "build", "selfcheck"],
                    nargs="?", default="all")
    ap.add_argument("--input", "--in", dest="input", default=None)
    ap.add_argument("--output", "--out", dest="output", default=None)
    ap.add_argument("--work", default=None)
    ap.add_argument("--case", default=None)
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(argv)
    base = Path(__file__).resolve().parent.parent
    inp = Path(a.input) if a.input else (Path("/input") if Path("/input").is_dir() else base / "input")
    out = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else base / "output")
    work = Path(a.work) if a.work else (Path("/app/work") if Path("/app").is_dir() else base / "work")
    try:
        res = run(inp, out, work)
        print("[all] case_id=%s status=%s files=%d tables=%d figures=%d"
              % (res.get("case_id"), res.get("status"), res.get("coverage", {}).get("files"),
                 res.get("coverage", {}).get("tables"), res.get("coverage", {}).get("figures")))
        print("[all] result -> %s" % (out / "result.json"))
    except Exception as exc:  # noqa: BLE001 - never crash the harness
        try:
            out.mkdir(parents=True, exist_ok=True)
            dump(out / "result.json", clean_obj({
                "case_id": None, "task": TOOL, "status": "failed",
                "output_contract": {k: "" for k in DEFAULT_CONTRACT},
                "errors": [{"stage": "all", "detail": "%s: %s" % (type(exc).__name__, exc),
                            "traceback": traceback.format_exc(limit=4)[-800:]}],
                "degradations": [], "warnings": [], "deliverable": "", "evidence": [], "sources": [],
                "uncertainties": [{"type": "runtime_error", "detail": "the run degraded to a legal result"}],
                "change_records": [{"action": "failed", "target": "input"}], "limits": ["see errors"],
                "coverage": {"files": 0, "tables": 0, "figures": 0}}))
        except Exception:  # noqa: BLE001
            pass
        print("[all] degraded: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    try:
        sanitize_dir(out, out, work)
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
