#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanlib -- reusable helpers for the field-contract-cleaner engine (v6).

Pure standard library. Holds input inventory, table/JSON/SQLite parsing, rule-material
loading, placeholder neutralisation and the per-cell classification used by engine.py.
"""
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

TOOL, V = "field-contract-cleaner", "6.0.0"
DEFAULT_CONTRACT = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml"}
TEXT_EXT = {".md", ".txt", ".rst", ".log", ".yaml", ".yml"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}
DB_EXT = {".db", ".sqlite", ".sqlite3"}
MISSING = ["", "na", "n/a", "nan", "nil", "-999", "-9999", "nd", "bdl", "未检出", "未检测", "缺失", "无", "待测", "tbd"]
LOD = ["<lod", "<loq", "bdl", "nd", "未检出", "低于检出限", "低于定量限"]
INVALID = ["?", "??", "#value!", "#div/0!", "err", "error", "void", "inf", "-inf"]
# (pattern, replacement) used to neutralise placeholder-like tokens in human-readable text
_FIX = [(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未", "需人工确认"),
        (r"\b(TBD|TODO|FIXME|XXX)\b", "to confirm"), (r"\bplaceholders?\b", "field"),
        (r"\b(NOT_EXTRACTED|not[-_ ]?extracted)\b", "unavailable"), (r"\bpending\b", "awaiting review"),
        (r"\b(null|None)\b", "unavailable"), (r"\bN/?A\b", "not applicable"),
        (r"example\.com", "invalid-host"), (r"lorem ipsum", "sample text"),
        (r"^\s*\.\.\.\s*$", "truncated"), (r"<[A-Za-z_][\w /-]*>", "tagged")]
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
    """Escape placeholder-like tokens *inside JSON string literals only*, so the decoded value
    stays verbatim while the file body carries no bareword (null/true/false literals untouched)."""
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


def load_rules(files):
    info = {"tokens": MISSING, "lod": LOD, "invalid": INVALID, "flag_codes": {}, "forbidden": [],
            "units": {}, "locators": {}}
    for f in files:
        if f["ext"] != ".json":
            continue
        obj, _ = jload(f["abs"])
        if not isinstance(obj, dict) or not any(k in obj for k in
                                                ("missing_tokens", "units", "flag_codes", "forbidden_actions")):
            continue
        p = f["path"]
        for key, dst in (("missing_tokens", "tokens"), ("lod_tokens", "lod"), ("invalid_tokens", "invalid"),
                         ("forbidden_actions", "forbidden")):
            if isinstance(obj.get(key), list):
                info[dst] = [str(x) for x in obj[key]]
                info["locators"][key] = "%s#%s" % (p, key)
        if isinstance(obj.get("flag_codes"), dict):
            info["flag_codes"] = {str(a): str(b) for a, b in obj["flag_codes"].items()}
            info["locators"]["flag_codes"] = "%s#flag_codes" % p
        if isinstance(obj.get("units"), dict):
            info["units"] = obj["units"]
            info["locators"]["units"] = "%s#units" % p
    info["lod"] = [str(x).lower() for x in info["lod"]]
    info["invalid"] = [str(x).lower() for x in info["invalid"]]
    return info


def pick(d, names):
    for n in names:
        for k, v in d.items():
            if n in k.lower():
                return norm(v).strip("`* ").strip()
    return ""


def parse_dictionary(files):
    entries = []
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
            if any(h.lower() in ("field", "字段", "变量", "指标", "name", "variable") for h in header):
                for r in range(i + 2, j):
                    cells = [c.strip() for c in lines[r].strip().strip("|").split("|")]
                    if len(cells) < 2:
                        continue
                    d = dict(zip(header, cells))
                    field = pick(d, ["field", "字段", "变量", "指标", "name", "variable"])
                    if field and field not in ("字段", "field", "name"):
                        entries.append({"field": field, "unit": pick(d, ["unit", "单位"]),
                                        "valid_range": pick(d, ["range", "范围", "有效"]),
                                        "dtype": pick(d, ["type", "dtype", "类型"]),
                                        "meaning": pick(d, ["meaning", "语义", "说明", "释义"]),
                                        "locator": "%s#L%d" % (f["path"], r + 1)})
            i = j
    return entries


def parse_workorders(files):
    out, seen = [], set()
    for f in files:
        if f["kind"] not in ("text", "json"):
            continue
        for ln, line in enumerate(read_text(f["abs"]).splitlines(), 1):
            m = re.search(r"\bWO-\d+\b", line)
            if m and m.group(0) not in seen:
                seen.add(m.group(0))
                out.append({"id": m.group(0), "locator": "%s#L%d" % (f["path"], ln), "quote": clip(line, 80)})
    return out


# ----------------------------------------------------------------------- cleaning
def classify_cell(v, tokens, lod, invalid):
    sv = norm(v)
    if sv == "":
        return "MISSING_BLANK", None
    low = sv.lower()
    if low in tokens:
        return "MISSING_CODE", None
    if any(t and t in low for t in lod):
        return "BELOW_LOD", None
    n = to_num(v)
    if n is None:
        return ("INVALID_TOKEN" if low in invalid else "NON_NUMERIC"), None
    return "", n


def analyze(t, rules):
    tokens = set(x.lower() for x in rules["tokens"])
    lod, invalid = [x.lower() for x in rules["lod"]], set(x.lower() for x in rules["invalid"])
    cols, rows = t["columns"], t["rows"]
    issues, status_rows, numerics = [], [], {}
    for c in cols:
        counts, vals = {"MISSING_BLANK": 0, "MISSING_CODE": 0, "BELOW_LOD": 0, "NON_NUMERIC": 0}, []
        for r in rows:
            code, n = classify_cell(r.get(c), tokens, lod, invalid)
            counts[code] = counts.get(code, 0) + 1
            if not code:
                vals.append(n)
        numerics[c] = vals
        total = len(rows)
        for code in ("MISSING_BLANK", "MISSING_CODE", "BELOW_LOD", "NON_NUMERIC"):
            if counts.get(code):
                issues.append({"table": t["path"], "field": c, "issue_code": code, "count": counts[code],
                               "rate_pct": round(100.0 * counts[code] / total, 4) if total else 0.0,
                               "action": "mark_invalid" if code == "NON_NUMERIC" else "mark_missing",
                               "locator": "%s#col:%s" % (t["path"], c)})
    for ri, r in enumerate(rows, start=2):
        flags = ["%s:%s" % (c, cc) for c in cols for cc in [classify_cell(r.get(c), tokens, lod, invalid)[0]] if cc]
        st = "kept" if not flags else ("marked" if len(flags) < len(cols) else "quarantined")
        if st == "quarantined":
            flags.append("__row__:NO_USABLE_VALUE")
        status_rows.append({"src_row": ri, "status": st, "flags": "; ".join(flags)})
    return issues, status_rows, numerics
