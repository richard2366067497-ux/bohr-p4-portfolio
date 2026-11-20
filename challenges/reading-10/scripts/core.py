#!/usr/bin/env python3
"""core.py -- deterministic kernel for repro-metric-crosscheck.

Responsibilities (no judgement, no network, standard library only):
  * tolerant IO (BOM / GB18030 / latin-1), atomic writes
  * material typing by magic bytes then suffix
  * text extraction into located units (PDF / DOCX / XLSX / CSV / JSON / MD / text)
  * verbatim evidence matching with locator rebinding
  * tolerance resolution and comparison arithmetic
  * metric parsing out of a candidate program's stdout (keeps the source line)
  * output_contract echo (same key names, never renamed, never dropped)

Run `python3 -B core.py --selftest` for the built-in check.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path

NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
ZERO = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0", "\u3000")


# --------------------------------------------------------------------- IO
def load_json(path):
    """Return (obj, err). Never raises."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except Exception as exc:
        return None, "read_failed:%s" % exc
    if not raw.strip():
        return None, "empty_file"
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        try:
            return json.loads(text), None
        except Exception as exc:
            return None, "parse_failed:%s" % str(exc)[:160]
    return None, "decode_failed"


def dump_json(path, obj, indent=2):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)
    return str(p)


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, p)
    return str(p)


def write_csv(path, header, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if c is None else c for c in r])
    os.replace(tmp, p)
    return str(p)


def sha1_file(path):
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:12]
    except Exception:
        return None


def sha256_obj(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ text
def norm(s):
    """Match-safe normalisation: NFKC, zero-width removal, whitespace fold, casefold."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s)
    for ch in ZERO:
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().casefold()


def nk(s):
    """Key normalisation for metric / parameter names."""
    return re.sub(r"[^a-z0-9]", "", str(s).casefold())


def snip(s, n=200):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n] + "..."


ALIAS = {
    "acc": ("accuracy", "acc", "top1", "top1accuracy", "testaccuracy", "valaccuracy",
            "classificationaccuracy", "overallaccuracy"),
    "f1": ("f1", "f1score", "macrof1", "weightedf1", "microf1"),
    "auc": ("auc", "rocauc", "auroc", "auprc"),
    "precision": ("precision", "prec"),
    "recall": ("recall", "sensitivity", "tpr"),
    "mse": ("mse", "meansquarederror", "meansquareerror", "mserror"),
    "rmse": ("rmse", "rootmeansquarederror", "rootmeansquareerror", "rmserror", "rms"),
    "mae": ("mae", "meanabsoluteerror"),
    "mape": ("mape", "meanabsolutepercentageerror"),
    "r2": ("r2", "r2score", "rsquared", "coefficientofdetermination"),
    "corr": ("corr", "correlation", "pearson", "pearsonr", "spearman"),
    "logloss": ("logloss", "crossentropy", "brier", "nll"),
    "loss": ("loss", "trainloss", "valloss", "testloss"),
    "time": ("time", "runtime", "elapsed", "walltime", "seconds"),
}


def metric_group(name):
    k = nk(name)
    if not k:
        return ""
    for grp, members in ALIAS.items():
        if k in members:
            return grp
    for grp, members in ALIAS.items():
        for m in members:
            if len(m) >= 3 and (m in k or k in m) and abs(len(m) - len(k)) <= 4:
                return grp
    return ""


def metric_match(a, b):
    """Same metric under different spellings? (name, confidence)."""
    if not a or not b:
        return False, 0
    ka, kb = nk(a), nk(b)
    if ka == kb:
        return True, 3
    ga, gb = metric_group(a), metric_group(b)
    if ga and ga == gb:
        return True, 2
    if len(ka) >= 4 and len(kb) >= 4 and (ka in kb or kb in ka):
        return True, 1
    return False, 0


# --------------------------------------------------------------- material
def sniff_kind(path):
    p = Path(path)
    ext = p.suffix.lower()
    try:
        head = p.open("rb").read(2048)
    except Exception:
        return "unreadable", 0
    size = 0
    try:
        size = p.stat().st_size
    except Exception:
        pass
    if head.startswith(b"%PDF"):
        return "pdf", size
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8") or head[:4] == b"GIF8":
        return "image", size
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(p) as z:
                names = set(z.namelist())
        except Exception:
            return "zip", size
        if "word/document.xml" in names:
            return "docx", size
        if any(n.startswith("xl/") for n in names):
            return "xlsx", size
        if any(n.startswith("ppt/") for n in names):
            return "pptx", size
        return "zip", size
    table = {".pdf": "pdf", ".json": "json", ".jsonl": "json", ".csv": "csv", ".tsv": "tsv",
             ".md": "md", ".markdown": "md", ".txt": "text", ".log": "text", ".py": "text",
             ".yaml": "text", ".yml": "text", ".toml": "text", ".cfg": "text", ".ini": "text",
             ".r": "text", ".jl": "text", ".m": "text", ".sh": "text", ".tex": "text",
             ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
             ".bmp": "image", ".webp": "image", ".tif": "image", ".tiff": "image",
             ".xlsx": "xlsx", ".docx": "docx", ".ipynb": "ipynb"}
    if ext in table:
        return table[ext], size
    try:
        head.decode("utf-8")
        return "text", size
    except Exception:
        return "binary", size


def _pdf_unescape(raw):
    try:
        s = raw.decode("latin-1")
    except Exception:
        return ""
    s = s.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    s = re.sub(r"\\[nrt]", lambda m: {"n": "\n", "r": "\n", "t": "\t"}[m.group(0)[1]], s)
    s = re.sub(r"\\[0-7]{1,3}", "", s)
    return s


def pdf_text(path):
    """(text, mode, pages). Tries pdftotext, else inflates content streams."""
    p = Path(path)
    import shutil
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"],
                               capture_output=True, timeout=90)
            if r.returncode == 0 and r.stdout.strip():
                txt = r.stdout.decode("utf-8", "ignore")
                return txt, "pdftotext", txt.count("\f") + 1
        except Exception:
            pass
    try:
        data = p.read_bytes()
    except Exception:
        return "", "unreadable", 0
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data)) or 0
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        start, end = m.end(), data.find(b"endstream", m.end())
        if end < 0:
            continue
        raw = data[start:end].rstrip(b"\r\n")
        try:
            raw = zlib.decompress(raw)
        except Exception:
            try:
                raw = zlib.decompress(raw, -15)
            except Exception:
                continue
        if b"Tj" not in raw and b"TJ" not in raw:
            continue
        buf = []
        for tok in re.finditer(rb"\((?:\\\\.|[^\\\\()])*\)\s*Tj|\[(?:[^\[\]]|\\\\.)*\]\s*TJ|T\*|Td|TD", raw):
            g = tok.group(0)
            if g.endswith(b"Tj"):
                buf.append(_pdf_unescape(g[g.find(b"(") + 1:g.rfind(b")")]))
            elif g.endswith(b"TJ"):
                parts = re.findall(rb"\((?:\\\\.|[^\\\\()])*\)", g)
                buf.append("".join(_pdf_unescape(x[1:-1]) for x in parts))
            else:
                buf.append("\n")
        seg = "".join(buf)
        if seg.strip():
            out.append(seg)
    txt = "\n\n".join(out)
    return txt, ("raw_stream" if txt.strip() else "failed"), pages


def _blocks(text, prefix, max_len=1400):
    out, n = [], 0
    for blk in re.split(r"\n\s*\n", text):
        blk = blk.strip()
        if not blk:
            continue
        pieces = [blk]
        if len(blk) > max_len:
            pieces = [x.strip() for x in blk.splitlines() if x.strip()]
        for piece in pieces:
            n += 1
            out.append(("%s.p%d" % (prefix, n), piece))
    return out


def _md_units(text, prefix):
    units, buf, sec, n = [], [], 0, 0

    def flush():
        nonlocal buf, n
        body = "\n".join(buf).strip()
        if body:
            n += 1
            units.append(("%s@s%d.u%d" % (prefix, sec, n), body))
        buf = []

    for line in text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s", line):
            flush()
            n = 0
            sec += 1
            buf.append(line.strip())
        elif not line.strip():
            flush()
        else:
            buf.append(line)
    flush()
    return units


def _json_units(obj, prefix, cap=3000):
    units = []

    def walk(node, ptr):
        if len(units) >= cap:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, ptr + "/" + str(k).replace("~", "~0").replace("/", "~1"))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, ptr + "/" + str(i))
        elif node is not None:
            key = ptr.rsplit("/", 1)[-1]
            units.append(("%s@j%s" % (prefix, ptr or "/"), "%s: %s" % (key, node)))

    walk(obj, "")
    return units


def _table_units(path, prefix, delim):
    try:
        raw = Path(path).read_bytes().decode("utf-8-sig", "replace")
    except Exception:
        return [], None
    try:
        rows = list(csv.reader(io.StringIO(raw), delimiter=delim))
    except Exception:
        return [], None
    if not rows:
        return [], None
    units = [("%s@header" % prefix, " | ".join(rows[0]))]
    for i, row in enumerate(rows[1:], start=1):
        if any(c.strip() for c in row):
            units.append(("%s@r%d" % (prefix, i), " | ".join(row)))
    return units, rows[0]


def _docx_units(path, prefix):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return []
    xml = re.sub(r"</w:p>", "\n\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
    return _blocks(html.unescape(re.sub(r"<[^>]+>", "", xml)), prefix)


def _xlsx_units(path, prefix, cap=2500):
    units = []
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            shared = []
            if "xl/sharedStrings.xml" in names:
                sx = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
                shared = [html.unescape(re.sub(r"<[^>]+>", "", s))
                          for s in re.findall(r"<si>([\s\S]*?)</si>", sx)]
            sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
            if not sheets:
                return []
            sx = z.read(sheets[0]).decode("utf-8", "ignore")
    except Exception:
        return []
    for ri, row in enumerate(re.finditer(r"<row\b[^>]*>([\s\S]*?)</row>", sx), start=1):
        cells = []
        for m in re.finditer(r"<c\b([^>]*)>([\s\S]*?)</c>", row.group(1)):
            attrs, body = m.group(1), m.group(2)
            v = re.search(r"<v>([\s\S]*?)</v>", body)
            val = v.group(1) if v else ""
            if 't="s"' in attrs and str(val).isdigit():
                i = int(val)
                val = shared[i] if 0 <= i < len(shared) else val
            elif 't="inlineStr"' in attrs:
                t = re.search(r"<t[^>]*>([\s\S]*?)</t>", body)
                val = t.group(1) if t else ""
            cells.append(html.unescape(re.sub(r"<[^>]+>", "", str(val))))
        if any(c.strip() for c in cells):
            units.append(("%s@r%d" % (prefix, ri), " | ".join(cells)))
        if len(units) >= cap:
            break
    return units


def extract_material(path, rel, mid):
    p = Path(path)
    kind, size = sniff_kind(p)
    rec = {"id": mid, "path": str(p), "rel": rel, "kind": kind, "bytes": size,
           "units": [], "quality": "ok", "notes": [], "sha1": None}
    if size > (28 << 20):
        rec.update(kind="skipped", quality="skipped", notes=[">28MB, not parsed"])
        return rec
    rec["sha1"] = sha1_file(p)
    try:
        if kind == "pdf":
            txt, mode, pages = pdf_text(p)
            rec["pages"] = pages
            rec["notes"].append("pdf_text:%s" % mode)
            if len(txt.strip()) < 200:
                rec["quality"] = "low_text"
                rec["notes"].append("no usable text layer; needs render/OCR")
            if mode == "pdftotext":
                for pi, page in enumerate(txt.split("\f"), start=1):
                    if page.strip():
                        rec["units"].extend(_blocks(page, "%s@pg%d" % (mid, pi)))
            else:
                rec["units"] = _blocks(txt, mid)
        elif kind == "docx":
            rec["units"] = _docx_units(p, mid)
        elif kind == "xlsx":
            rec["units"] = _xlsx_units(p, mid)
            rec["notes"].append("first worksheet only; formulas as cached values")
        elif kind in ("csv", "tsv"):
            units, header = _table_units(p, mid, "," if kind == "csv" else "\t")
            rec["units"] = units
            rec["columns"] = header or []
        elif kind in ("json", "ipynb"):
            obj, err = load_json(p)
            if obj is None:
                rec.update(quality="unparsed", notes=[err or "json parse failed"])
            else:
                rec["units"] = _json_units(obj, mid)
        elif kind == "md":
            rec["units"] = _md_units(p.read_text(encoding="utf-8-sig", errors="replace"), mid)
        elif kind == "text":
            rec["units"] = _blocks(p.read_text(encoding="utf-8-sig", errors="replace"), mid)
        elif kind == "image":
            rec.update(quality="no_ocr", notes=["image material: pixels not read"])
        elif kind == "pptx":
            rec.update(quality="not_parsed", notes=["pptx not text-extracted"])
        else:
            rec.update(quality="unsupported", notes=["kind=%s" % kind])
    except Exception as exc:
        rec.update(quality="unparsed", notes=["%s:%s" % (type(exc).__name__, str(exc)[:120])])
    if len(rec["units"]) > 4000:
        rec["units"] = rec["units"][:4000]
        rec["notes"].append("units truncated to 4000")
    return rec


def flat_units(index):
    out = []
    for m in index.get("materials", []):
        for loc, text in m.get("units", []):
            out.append({"source_id": m["id"], "locator": loc, "text": text,
                        "tn": norm(text), "kind": m.get("kind")})
    return out


# --------------------------------------------------------------- evidence
def find_quote(units, quote, source_id=None, cap=6):
    q = norm(quote)
    if len(q) < 4:
        return []
    hits = []
    for u in units:
        if source_id and u["source_id"] != source_id:
            continue
        if q in u["tn"]:
            hits.append({"source_id": u["source_id"], "locator": u["locator"],
                         "method": "normalized_substring"})
            if len(hits) >= cap:
                break
    return hits


def check_evidence(units, ev, require_locator=False):
    """(ok, hits, reason). A hit rebinds the locator instead of rejecting it."""
    if not isinstance(ev, dict):
        return False, [], "evidence_not_object"
    quote = str(ev.get("quote") or "")
    if not quote.strip():
        return False, [], "missing_quote"
    sid = ev.get("source_id") or None
    hits = find_quote(units, quote, sid)
    if not hits and sid:
        hits = find_quote(units, quote, None)
        if hits:
            return True, hits, "source_mismatch_differs_from_index"
    if not hits:
        return False, [], "quote_not_found"
    declared = norm(str(ev.get("locator") or ""))
    if declared:
        exact = [h for h in hits if norm(h["locator"]) == declared]
        if exact:
            return True, exact, "ok"
        return True, hits, "locator_rebound"
    if require_locator:
        return True, hits, "locator_missing"
    return True, hits[:3], "ok"


# -------------------------------------------------------------- tolerance
DEFAULT_ABS_FRAC = 0.005
DEFAULT_REL = 0.02


def prior_entry(reported=None, basis=None):
    e = {"abs_frac": DEFAULT_ABS_FRAC, "rel_tol": DEFAULT_REL,
         "basis": basis or ("prior_default: rel 2% (run-to-run spread of reported metrics) + "
                            "abs 0.5% of the reported magnitude to absorb rounding")}
    if isinstance(reported, (int, float)) and not isinstance(reported, bool):
        e["abs_frac"] = 0.005
    return e


def resolve_tol(entry, reported):
    e = dict(entry or {})
    atol = e.get("abs_tol")
    if not isinstance(atol, (int, float)):
        frac = e.get("abs_frac")
        if isinstance(frac, (int, float)) and isinstance(reported, (int, float)):
            atol = abs(float(reported)) * float(frac)
        else:
            atol = None
    rtol = e.get("rel_tol")
    return {"abs_tol": atol,
            "rel_tol": rtol if isinstance(rtol, (int, float)) else None,
            "basis": e.get("basis"), "source": e.get("source")}


def compare_values(observed, reported, abs_tol, rel_tol):
    if not isinstance(observed, (int, float)) or not isinstance(reported, (int, float)):
        return {"within_tolerance": None, "abs_dev": None, "rel_dev": None, "note": "non_numeric"}
    ad = abs(float(observed) - float(reported))
    rd = ad / abs(float(reported)) if reported else None
    ok = (abs_tol is not None and ad <= float(abs_tol) + 1e-15)
    if not ok and rd is not None and rel_tol is not None:
        ok = rd <= float(rel_tol) + 1e-15
    return {"within_tolerance": bool(ok), "abs_dev": round(ad, 12),
            "rel_dev": None if rd is None else round(rd, 8)}


def scale_note(observed, reported):
    """Detect a percent/fraction mismatch instead of silently calling it out of band."""
    if not isinstance(observed, (int, float)) or not isinstance(reported, (int, float)):
        return None
    if reported == 0 or observed == 0:
        return None
    ratio = abs(observed / reported)
    if 60 <= ratio <= 140:
        return {"factor": 0.01, "applied_to": "observed",
                "note": "observed looks like percent, reported is a fraction"}
    if 1 / 140 <= ratio <= 1 / 60:
        return {"factor": 100.0, "applied_to": "observed",
                "note": "observed looks like a fraction, reported is a percent"}
    return None


# ---------------------------------------------------------------- metrics
def _flatten_num(node, out, pre=""):
    if isinstance(node, dict):
        for k, v in node.items():
            _flatten_num(v, out, (pre + "." + str(k)) if pre else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node[:30]):
            _flatten_num(v, out, "%s[%d]" % (pre, i))
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out[pre] = float(node)


def parse_metrics(text):
    """(metrics{name: value}, provenance{name: source_line}). Never raises."""
    text = text or ""
    metrics, prov = {}, {}
    # 1) embedded JSON object (last one wins: programs usually print the final dict)
    for chunk in re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)[-6:]:
        try:
            obj = json.loads(chunk)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        flat = {}
        _flatten_num(obj, flat)
        for k, v in flat.items():
            name = k.split(".")[-1].split("[")[0]
            if name and name not in metrics:
                metrics[name] = v
                prov[name] = snip(chunk, 180)
        if metrics:
            return metrics, prov
    # 2) key = value / key: value / key | value / key \t value
    for line in text.splitlines():
        s = line.strip().strip("*`-").strip()
        if not s or len(s) > 300:
            continue
        pat = (r"^([A-Za-z][A-Za-z0-9 _\-./()]{0,48}?)\s*(?:=|:|,|\t|\||=~)\s*("
               + NUM + r")\s*(%|percent)?\s*$")
        m = re.match(pat, s, re.I)
        if m:
            name = re.sub(r"\s+", "_", m.group(1).strip().casefold())
            try:
                val = float(m.group(2))
            except Exception:
                continue
            if re.fullmatch(r"(step|epoch|iter|iteration|n|seed|version|fold|batch|n_iter|"
                            r"n_samples|num_samples|row|col)[s]?", name) or re.fullmatch(r"[\d._]+", name):
                continue
            if m.group(3) and abs(val) > 1.0:
                val = val / 100.0
            if name not in metrics:
                metrics[name] = val
                prov[name] = snip(s, 180)
    # 3) trailing "name value" pairs, e.g. "Test MAE 0.1871"
    for line in text.splitlines():
        s = line.strip()
        m = re.search(r"([A-Za-z][A-Za-z0-9 _\-]{2,40}?)\s*[:=]?\s*(" + NUM + r")\s*(%|percent)?\s*$", s)
        if m:
            name = re.sub(r"\s+", "_", m.group(1).strip().casefold())
            if name in metrics or len(name) < 3 or re.fullmatch(
                    r"(step|epoch|iter|iteration|n|seed|fold|batch|row|col)s?", name):
                continue
            try:
                val = float(m.group(2))
            except Exception:
                continue
            if m.group(3) and abs(val) > 1.0:
                val = val / 100.0
            metrics[name] = val
            prov[name] = snip(s, 180)
    return metrics, prov


# --------------------------------------------------------------- contract
SEM = [
    (("tolerance", "toler", "容差", "band"), "tolerance"),
    (("attribut", "归因", "cause", "rootcause"), "attributions"),
    (("compar", "contrast", "diff", "对比", "差异", "versus", "vs"), "comparison"),
    (("repro_record", "reproduction_record"), "record"),
    (("repro", "复现", "replicat"), "record"),
    (("environment", "environ", "环境", "snapshot"), "environment"),
    (("param", "参数", "hyper", "超参"), "params"),
    (("run", "exec", "运行", "command", "log", "日志"), "runs"),
    (("checklist", "清单", "material", "材料", "source", "来源", "licen", "permission", "dependency"), "checklist"),
    (("evid", "证据", "quote", "locator", "citation", "引用"), "evidence"),
    (("verdict", "conclusion", "结论", "tier", "grade", "判定", "复现结论"), "verdict"),
    (("uncert", "不确定", "unknown", "ambigu"), "uncertainty"),
    (("pending", "human", "人工", "handover", "接管"), "pending_human"),
    (("gap", "missing", "缺失", "缺口"), "gaps"),
    (("plan", "step", "流程", "procedure"), "plan"),
    (("claim", "结论点", "finding"), "claims"),
    (("report", "报告", "narrative", "markdown", "retell"), "report_markdown"),
    (("csv", "table", "表"), "comparison_csv"),
    (("summary", "摘要", "answer", "答案", "abstract", "overview"), "summary"),
    (("status", "状态"), "status"),
    (("result", "结果"), "record"),
]
UNKNOWN = object()


def _slot_for(key):
    k = str(key or "").casefold()
    for pats, slot in SEM:
        if any(p in k for p in pats):
            return slot
    return None


def _spec_names(con):
    """If the contract is a field-spec list, return the declared names."""
    if not isinstance(con, list):
        return []
    names = []
    for item in con:
        if isinstance(item, dict):
            for k in ("name", "key", "field", "id"):
                if isinstance(item.get(k), str) and item[k]:
                    names.append(item[k])
                    break
    return names


def contract_keys(con):
    if isinstance(con, dict):
        return list(con.keys())
    return _spec_names(con)


def echo_contract(con, values, unmapped, key=""):
    """Fill output_contract keeping every original key name. values: slot -> payload."""
    if isinstance(con, dict):
        if not con:
            slot = _slot_for(key)
            if slot is None or slot not in values:
                if key:
                    unmapped.append(str(key))
                return None
            return values[slot]
        return {k: echo_contract(v, values, unmapped, k) for k, v in con.items()}
    if _spec_names(con):
        out = {}
        for name in _spec_names(con):
            out[name] = echo_contract(None, values, unmapped, name)
        return out
    if isinstance(con, list):
        slot = _slot_for(key)
        if slot is None or slot not in values:
            if key:
                unmapped.append(str(key))
            return []
        val = values[slot]
        return val if isinstance(val, list) else [val]
    slot = _slot_for(key)
    if slot is None or slot not in values:
        if key:
            unmapped.append(str(key))
        return None
    return values[slot]


# --------------------------------------------------------------- selftest
def selftest():
    fails = []
    if norm("A  b\n c") != "a b c":
        fails.append("norm")
    units = [{"source_id": "p", "locator": "p@s1.u1", "text": "Table 2 reports MAE 0.184 on the test split",
              "tn": norm("Table 2 reports MAE 0.184 on the test split"), "kind": "md"}]
    ok, hits, why = check_evidence(units, {"quote": "reports MAE 0.184", "source_id": "p"})
    if not (ok and hits and why == "ok"):
        fails.append("evidence_hit")
    ok2, _, why2 = check_evidence(units, {"quote": "reports MAE 0.991"})
    if ok2 or why2 != "quote_not_found":
        fails.append("evidence_miss")
    ok3, hits3, why3 = check_evidence(units, {"quote": "MAE 0.184", "locator": "p@s9.u9"})
    if not (ok3 and why3 == "locator_rebound"):
        fails.append("locator_rebind")
    if compare_values(0.1871, 0.184, 0.00092, 0.02)["within_tolerance"] is not True:
        fails.append("cmp_in")
    if compare_values(0.260, 0.184, 0.00092, 0.02)["within_tolerance"] is not False:
        fails.append("cmp_out")
    sn = scale_note(76.5, 0.765)
    if not sn or sn["factor"] != 0.01:
        fails.append("scale")
    m, prov = parse_metrics('noise\n{"mae": 0.1871, "r2": 0.861}\ndone')
    if abs(m.get("mae", 0) - 0.1871) > 1e-9 or "mae" not in prov:
        fails.append("metrics_json")
    m2, _ = parse_metrics("epoch 3\nMAE: 0.1871\nR2 = 0.861\ntest accuracy 76.5%\n")
    if abs(m2.get("mae", 0) - 0.1871) > 1e-9:
        fails.append("metrics_text:%s" % m2)
    if not any(abs(v - 0.765) < 1e-9 and metric_match(k, "accuracy")[0] for k, v in m2.items()):
        fails.append("metrics_pct:%s" % m2)
    if not metric_match("rmse", "Root Mean Square Error")[0]:
        fails.append("alias")
    if metric_match("mae", "acc")[0]:
        fails.append("alias_false")
    un = []
    vals = {"status": "ok", "comparison": [{"metric": "mae"}], "record": {"v": 1},
            "tolerance": [1], "attributions": [], "evidence": [{"q": 1}],
            "params": [2], "runs": [3], "checklist": [], "environment": {},
            "verdict": {"tier": "x"}, "summary": "s", "claims": [], "plan": [],
            "report_markdown": "# r", "comparison_csv": "a.csv", "gaps": [],
            "uncertainty": [], "pending_human": []}
    filled = echo_contract({"status": None, "comparison_table": [], "repro_record": None,
                            "custom_blob_x": None}, vals, un)
    if filled.get("status") != "ok" or filled.get("comparison_table") != vals["comparison"]:
        fails.append("contract_fill")
    if filled.get("repro_record") != {"v": 1} or "custom_blob_x" not in un:
        fails.append("contract_unknown")
    if contract_keys({"a": 1, "b": None}) != ["a", "b"]:
        fails.append("contract_keys")
    spec = [{"name": "comparison_table", "type": "array"}, {"name": "verdict", "type": "object"}]
    if contract_keys(spec) != ["comparison_table", "verdict"]:
        fails.append("contract_spec")
    print("selftest: %s" % ("PASS" if not fails else "FAIL " + ", ".join(fails)))
    return 0 if not fails else 1


def main():
    import argparse
    ap = argparse.ArgumentParser(description="deterministic kernel for repro-metric-crosscheck")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(0)
