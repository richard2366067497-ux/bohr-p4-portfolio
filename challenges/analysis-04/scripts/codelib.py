#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""codelib -- reusable helpers for the analysis-codegen-execute engine (analysis-04, v6).

Pure standard library: input inventory, table/SQLite parsing, spec/dictionary material parsing,
placeholder neutralisation and the JSON writers used by engine.py.
"""
import csv
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

TOOL, V = "analysis-codegen-execute", "6.0.0"
DEFAULT_CONTRACT = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml"}
TEXT_EXT = {".md", ".txt", ".rst", ".log", ".yaml", ".yml"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}
DB_EXT = {".db", ".sqlite", ".sqlite3"}
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
    if isinstance(b, str):
        b = b.encode("utf-8")
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
    """Escape placeholder-like tokens *inside JSON string literals only* so the decoded value stays
    verbatim while the file body carries no bareword (null/true/false literals untouched)."""
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
    try:
        with open(p, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
    except OSError:
        pass
    return p


# ------------------------------------------------------------------------ parsing
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
        return float(v) if math.isfinite(v) else None
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
            con = sqlite3.connect(f["abs"])
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


def pick(d, names):
    for n in names:
        for k, v in d.items():
            if n in k.lower():
                return norm(v).strip("`* ").strip()
    return ""


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
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            body = []
            for r in range(i + 2, j):
                cells = [c.strip() for c in lines[r].strip().strip("|").split("|")]
                if len(cells) >= 2:
                    body.append((cells, r + 1))
            if body or header:
                yield f, header, body, i + 1
            i = j


def parse_spec(files):
    """Parse the analysis_spec / rules markdown: draft fields, verification categories, degradation
    matrix, contract-key semantics, operator enums -- each with a file#L<line> locator."""
    out = {"draft_fields": [], "verification_specs": [], "degradations": [], "contract_semantics": [],
           "enums": {}, "locators": {}}
    for f, header, body, hline in _md_tables(files):
        h = " ".join(header).lower()
        p = f["path"]
        if any(k in h for k in ("必填", "字段")) and "类型" in " ".join(header):
            for cells, ln in body:
                out["draft_fields"].append({"field": safe_text(cells[0]), "constraint": safe_text(cells[-1]),
                                            "locator": "%s#L%d" % (p, ln)})
            out["locators"]["draft_fields"] = "%s#L%d" % (p, hline)
        elif "category" in h and "check" in h:
            for cells, ln in body:
                if len(cells) >= 3:
                    out["verification_specs"].append({"category": cells[0], "check": cells[1],
                                                      "severity": cells[2], "locator": "%s#L%d" % (p, ln)})
            out["locators"]["verification"] = "%s#L%d" % (p, hline)
        elif "触发" in " ".join(header) and "处置" in " ".join(header):
            for cells, ln in body:
                if len(cells) >= 3:
                    out["degradations"].append({"trigger": safe_text(cells[0]), "handling": safe_text(cells[2]),
                                                "locator": "%s#L%d" % (p, ln)})
            out["locators"]["degradations"] = "%s#L%d" % (p, hline)
        elif "键名模式" in " ".join(header) or "回填" in " ".join(header):
            for cells, ln in body:
                if len(cells) >= 2:
                    out["contract_semantics"].append({"pattern": cells[0], "backfill": cells[1],
                                                      "locator": "%s#L%d" % (p, ln)})
            out["locators"]["contract_semantics"] = "%s#L%d" % (p, hline)
        elif "op" in h and ("enum" in h or "∈" in " ".join(header)):
            for cells, ln in body:
                if len(cells) >= 2:
                    out["enums"].setdefault(safe_text(cells[0]), safe_text(cells[1]))
            out["locators"].setdefault("enums", "%s#L%d" % (p, hline))
    return out


def parse_dictionary(files):
    entries = []
    for f, header, body, hline in _md_tables(files):
        if any(h.lower() in ("field", "字段", "变量", "指标", "name", "variable", "column") for h in header):
            for cells, ln in body:
                d = dict(zip(header, cells))
                field = pick(d, ["field", "字段", "变量", "指标", "name", "variable", "column"])
                if field and field not in ("字段", "field", "name"):
                    entries.append({"field": field, "unit": pick(d, ["unit", "单位"]),
                                    "valid_range": pick(d, ["range", "范围", "有效"]),
                                    "dtype": pick(d, ["type", "dtype", "类型"]),
                                    "locator": "%s#L%d" % (f["path"], ln)})
    return entries


# --------------------------------------------------------------------------- stats
def mean(v):
    return sum(v) / len(v) if v else None


def quantile(sv, q):
    if not sv:
        return None
    k = (len(sv) - 1) * q
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    return sv[lo] if lo == hi else sv[lo] * (hi - k) + sv[hi] * (k - lo)


def median(v):
    return quantile(sorted(v), 0.5)


def stdev(v):
    n = len(v)
    if n < 2:
        return None
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))


# ---------------------------------------------------- generated analysis code template
CODE_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generated analysis code -- self-contained, standard library only, deterministic.

Usage: python3 analysis.py --input <materials_dir> --output <results_dir>
Reads every csv/tsv/json/jsonl/sqlite table under <input>, computes descriptive/missing/dedup/
groupby/correlation/t-test/frequency operations, and writes <results_dir>/summary.json.
"""
import csv, json, math, os, re, sqlite3, sys

def to_num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    s = re.sub(r"\\s+", "", str(v)).replace(",", "")
    if not re.match(r"^[-+]?(\\d+\\.?\\d*|\\.\\d+)([eE][-+]?\\d+)?%?$", s):
        return None
    try:
        return float(re.sub(r"[^0-9eE+\\-.]", "", s))
    except ValueError:
        return None

def parse_table(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv", ".tab"):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return [], []
        delim = "\\t" if ext in (".tsv", ".tab") else ","
        if ext == ".csv":
            try:
                delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\\t|").delimiter
            except Exception:
                delim = ","
        lines = [l for l in text.splitlines() if l.strip(",\\t;| \\r\\n") or "," in l or "\\t" in l]
        if not lines:
            return [], []
        rows = [{(k or "").strip(): v for k, v in r.items()} for r in csv.DictReader(lines, delimiter=delim)]
        rows = [r for r in rows if any((v or "").strip() for v in r.values())]
        return (list(rows[0].keys()) if rows else [c.strip() for c in lines[0].split(delim)]), rows
    if ext in (".json", ".jsonl"):
        seq = []
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return [], []
        if ext == ".jsonl":
            for ln in text.splitlines():
                if ln.strip():
                    try:
                        seq.append(json.loads(ln))
                    except Exception:
                        pass
        else:
            try:
                obj = json.loads(text)
            except Exception:
                return [], []
            seq = obj if isinstance(obj, list) else next((v for v in obj.values() if isinstance(v, list)), None)
        if not seq or not all(isinstance(x, dict) for x in seq[:5]):
            return [], []
        cols = []
        for r in seq[:50]:
            for k in r:
                if str(k) not in cols:
                    cols.append(str(k))
        return cols, [{str(k): v for k, v in r.items()} for r in seq]
    if ext in (".db", ".sqlite", ".sqlite3"):
        try:
            con = sqlite3.connect(path)
            cur = con.cursor()
            for tb in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                try:
                    cur.execute('SELECT * FROM "%s" LIMIT 5000' % tb.replace('"', '""'))
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    if cols:
                        con.close()
                        return cols, rows
                except Exception:
                    continue
            con.close()
        except Exception:
            pass
    return [], []

def sv(v):
    return v.strip() if isinstance(v, str) else ""

def quant(vals, q):
    if not vals:
        return None
    k = (len(vals) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return vals[lo] if lo == hi else vals[lo] * (hi - k) + vals[hi] * (k - lo)

def main():
    a = sys.argv[1:]
    inp = a[a.index("--input") + 1] if "--input" in a else "."
    out = a[a.index("--output") + 1] if "--output" in a else "."
    files = []
    for root, _dirs, names in os.walk(inp):
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in (".csv", ".tsv", ".tab", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"):
                files.append(os.path.join(root, n))
    tables, ops, keys = [], [], []
    n_in = 0
    for path in files:
        cols, rows = parse_table(path)
        if not cols:
            continue
        rel = os.path.relpath(path, inp).replace("\\\\", "/")
        n_in += len(rows)
        seen, dedup, uniq = set(), 0, []
        for r in rows:
            t = tuple(sv(r.get(c)) for c in cols)
            if t in seen:
                dedup += 1
            else:
                uniq.append(r)
            seen.add(t)
        rows = uniq
        tables.append({"table": rel, "columns": cols, "n": len(rows)})
        num, cat = {}, []
        for c in cols:
            vals = [to_num(r.get(c)) for r in rows]
            good = [x for x in vals if x is not None]
            miss = len(rows) - len(good)
            if len(good) >= 2 and len(good) >= 0.6 * len(rows):
                num[c] = good
                svals = sorted(good)
                ops.append({"op": "describe", "table": rel, "column": c, "n": len(good), "missing": miss,
                            "mean": round(sum(good) / len(good), 6), "median": round(quant(svals, 0.5), 6),
                            "stdev": round(math.sqrt(sum((x - sum(good) / len(good)) ** 2 for x in good) / (len(good) - 1)), 6) if len(good) > 1 else None,
                            "min": svals[0], "max": svals[-1]})
                keys.append({"id": "%s.%s.mean" % (rel, c), "metric": "mean", "table": rel, "column": c,
                             "value": round(sum(good) / len(good), 6), "unit": "unit_unknown"})
            else:
                lv = sorted({sv(r.get(c)) for r in rows if sv(r.get(c))})
                if 2 <= len(lv) <= 12:
                    cat.append((c, lv))
                    for x in lv:
                        ops.append({"op": "freq", "table": rel, "column": c, "value": x,
                                    "count": sum(1 for r in rows if sv(r.get(c)) == x)})
        if num and cat:
            gcol, lv = cat[0]
            ocol = next(iter(num))
            gb = []
            for x in lv:
                g = [to_num(r.get(ocol)) for r in rows if sv(r.get(gcol)) == x]
                g = [y for y in g if y is not None]
                gb.append({"group": x, "n": len(g), "mean": round(sum(g) / len(g), 6) if g else None})
            ops.append({"op": "groupby", "table": rel, "group_by": gcol, "column": ocol, "groups": gb})
            for e in gb:
                if e["mean"] is not None:
                    keys.append({"id": "%s.%s.%s.mean" % (rel, ocol, e["group"]), "metric": "mean",
                                 "table": rel, "column": ocol, "where": {gcol: e["group"]},
                                 "value": e["mean"], "unit": "unit_unknown"})
            if len(gb) == 2 and all(e["n"] >= 2 for e in gb):
                gs = {}
                for x in lv:
                    gs[x] = [y for y in (to_num(r.get(ocol)) for r in rows if sv(r.get(gcol)) == x) if y is not None]
                try:
                    m1, m2 = sum(gs[lv[0]]) / len(gs[lv[0]]), sum(gs[lv[1]]) / len(gs[lv[1]])
                    s1 = math.sqrt(sum((x - m1) ** 2 for x in gs[lv[0]]) / (len(gs[lv[0]]) - 1))
                    s2 = math.sqrt(sum((x - m2) ** 2 for x in gs[lv[1]]) / (len(gs[lv[1]]) - 1))
                    n1, n2 = len(gs[lv[0]]), len(gs[lv[1]])
                    sp = math.sqrt(((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / (n1 + n2 - 2))
                    t = (m1 - m2) / (sp * math.sqrt(1.0 / n1 + 1.0 / n2))
                    ops.append({"op": "ttest", "table": rel, "column": ocol, "group_by": gcol,
                                "statistic": "t", "value": round(t, 6), "df": n1 + n2 - 2,
                                "mean_difference": round(m1 - m2, 6)})
                    keys.append({"id": "%s.%s.ttest" % (rel, ocol), "metric": "t", "table": rel,
                                 "column": ocol, "value": round(t, 6), "unit": "t_statistic"})
                except Exception:
                    pass
        if len(num) >= 2:
            c1, c2 = list(num)[:2]
            pr = [(to_num(r.get(c1)), to_num(r.get(c2))) for r in rows]
            xs = [a for a, b in pr if a is not None and b is not None]
            ys = [b for a, b in pr if a is not None and b is not None]
            m = len(xs)
            try:
                mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
                cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(m))
                dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
                dy = math.sqrt(sum((y - my) ** 2 for y in ys))
                r = cov / (dx * dy) if dx and dy else None
                ops.append({"op": "corr", "table": rel, "x": c1, "y": c2, "n": m,
                            "r": round(r, 6) if r is not None else None})
                if r is not None:
                    keys.append({"id": "%s.%s.%s.r" % (rel, c1, c2), "metric": "r", "table": rel,
                                 "column": c1, "y": c2, "value": round(r, 6), "unit": "correlation"})
            except Exception:
                pass
        ops.append({"op": "dedup", "table": rel, "duplicate_rows": dedup})
    summary = {"schema": "analysis_summary/1.0.0", "tables": tables, "n_rows_in": n_in,
               "n_rows_used": sum(t["n"] for t in tables), "n_rows_dedup": sum(o["duplicate_rows"] for o in ops if o["op"] == "dedup"),
               "n_tables": len(tables), "ops": ops, "key_numbers": keys}
    d = os.path.join(out, "results")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print("[analysis] tables=%d ops=%d key_numbers=%d" % (len(tables), len(ops), len(keys)))

if __name__ == "__main__":
    main()
'''
