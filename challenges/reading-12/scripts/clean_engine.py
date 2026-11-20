"""clean_engine.py - data layer for extraction-table-auditor.

Text/number/unit parsing, column-role detection, object-table construction,
candidate duplicate grouping and verbatim-quote verification. Stdlib only,
offline, no CWD assumptions, and no wall-clock or random value in any output:
two runs over the same input must be byte-identical.
"""
import csv
import json
import re
import unicodedata
from pathlib import Path

VERSION = "1.0.0"

CANON = ["row_id", "source_document_id", "source_locator", "field", "indicator", "material",
         "condition_summary", "value", "value_low", "value_high", "value_err", "unit",
         "original_value", "original_unit", "rule_ids", "judgment_key", "status",
         "duplicate_of", "note"]
CHG = ["row_id", "field", "before", "after", "unit_before", "unit_after", "factor", "offset",
       "formula", "precision", "rule_id", "source_document_id", "source_locator", "note"]
PEND = ["row_id", "field", "reason_code", "reason", "suggested_action", "original_value",
        "original_unit", "source_document_id", "source_locator"]

MISSING = {"", "-", "--", "n/a", "na", "n.a.", "nr", "n.r.", "nd", "n.d.", "n.m.", "none",
           "null", "nan", "not reported", "not given", "not available", "unreported", "?",
           "??", "tbd", "\u65e0", "\u7f3a", "\u672a\u62a5\u544a", "\u672a\u7ed9\u51fa",
           "\u672a\u6d4b", "\u2014"}
SUB = {"\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
       "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9"}
SUP = {"\u2070": "^0", "\u00b9": "^1", "\u00b2": "^2", "\u00b3": "^3", "\u2074": "^4",
       "\u2075": "^5", "\u2076": "^6", "\u2077": "^7", "\u2078": "^8", "\u2079": "^9",
       "\u207b": "^-", "\u207a": "^+"}
DASH = {"\u2212": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u00a0": " ",
        "\u00d7": "x", "\u00b7": "*", "\u22c5": "*", "\u2219": "*", "\uff0b": "+",
        "\uff0d": "-", "\uff0f": "/", "\uff08": "(", "\uff09": ")"}
NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NUM_UNIT = r"[A-Za-z\u03bc%\u00b0\u00c5/^]"
ROLE_ORDER = ("row_id", "source_document_id", "source_locator", "value_low", "value_high",
              "value_err", "value", "unit", "indicator", "material")
NOTE_HINT = ("note", "comment", "remark", "memo", "flag", "\u5907\u6ce8", "\u8bf4\u660e", "tag")
STATUS_OK = ("ok", "converted", "replicate")


# ---------------------------------------------------------------- io helpers
def read_text(path):
    """Decode with a cascade; returns (text, encoding, replacement-char count)."""
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(enc), enc, 0
        except UnicodeDecodeError:
            continue
    text = data.decode("utf-8", "replace")
    return text, "utf-8/replace", text.count("\ufffd")


def load_json(path):
    try:
        text, _, _ = read_text(path)
        return json.loads(text), None
    except Exception as exc:                                     # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:200])


def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, rows, cols):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        for row in rows:
            wr.writerow({c: fmt(row.get(c)) for c in cols})


def fmt(x):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            return str(x)
        return "%.12g" % x
    return str(x)


def num(x):
    try:
        if isinstance(x, str):
            x = x.strip().replace(",", "")
            if x == "":
                return None
        return float(x)
    except (TypeError, ValueError):
        return None


def nat(key):
    return tuple((0, int(p)) if p.isdigit() else (1, p)
                 for p in re.split(r"(\d+)", str(key)) if p != "")


def clip(text, n=160):
    s = "" if text is None else str(text)
    return s if len(s) <= n else s[:n - 1] + "\u2026"


# ------------------------------------------------------------------- text norm
def norm_cell(raw):
    s = "" if raw is None else str(raw)
    for a, b in SUB.items():
        s = s.replace(a, b)
    for a, b in SUP.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKC", s)
    for a, b in DASH.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def nkey(text):
    """Comparison key for names: TiO2 / TiO_2 / 'titanium  dioxide' collapse."""
    s = norm_cell(text).lower()
    s = s.replace("\u03bc", "u").replace("\u00b5", "u").replace("\u00c5", "angstrom")
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff.+/%-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def canonical(raw, table):
    """Return (canonical label, hit) for a material / indicator spelling."""
    key = nkey(raw)
    if not key:
        return "", False
    if key in table:
        return table[key], True
    for cand in sorted(table, key=len, reverse=True):
        if len(cand) >= 4 and re.search(r"(^|\s)%s(\s|$)" % re.escape(cand), key):
            return table[cand], True
    return re.sub(r"\s+", "_", key), False


def split_header(col):
    """'Band gap (eV)' / 'size/nm' -> ('Band gap', 'eV') / ('size', 'nm')."""
    s = str(col).strip()
    m = re.search(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]\s*$", s)
    if m:
        return s[:m.start()].strip(), m.group(1).strip()
    m = re.search(r"(?:/|_|\bper\s)\s*([A-Za-z\u03bc\u00b0\u00c5][\w\u03bc\u00b0\u00c5^*/. -]{0,18})$", s)
    if m and len(s[:m.start()].strip()) > 1:
        return s[:m.start()].strip(), m.group(1).strip()
    return s, ""


# ---------------------------------------------------------------------- cell
def parse_cell(raw):
    """value | range | value+-err | missing | text, plus any unit written inline."""
    out = {"raw": "" if raw is None else str(raw), "kind": "missing", "value": None,
           "low": None, "high": None, "err": None, "qual": "", "unit_inline": "",
           "decimals": 0, "text": norm_cell(raw)}
    s = out["text"]
    low = s.lower()
    if s == "" or low in MISSING or low.rstrip(" .;") in MISSING or low.rstrip(" .;") + "." in MISSING:
        return out
    tail = r"\s*(?P<u>%s[^\s]*)?\s*$" % NUM_UNIT
    pats = [("pm", r"^(?P<a>%s)\s*(?:\u00b1|\+/-|\+-)\s*(?P<b>%s)" % (NUM, NUM)),
            ("range", r"^(?P<a>%s)\s*(?:-|to|~)\s*(?P<b>%s)" % (NUM, NUM)),
            ("sci", r"^(?P<a>%s)\s*(?:[x*]\s*)?10\s*\^\s*(?P<e>[-+]?\d+)" % NUM),
            ("single", r"^(?P<q>[<>\u2264\u2265~\u2248])?\s*(?P<a>%s)" % NUM)]
    for kind, pat in pats:
        m = re.fullmatch(pat + tail, s, re.I)
        if not m:
            continue
        g = m.groupdict()
        a = num(g.get("a"))
        if a is None:
            continue
        out["unit_inline"] = (g.get("u") or "").strip(" .,;")
        out["decimals"] = _dp(g.get("a"))
        if kind == "pm":
            out.update(kind="pm", value=a, err=num(g.get("b")))
            out["decimals"] = max(out["decimals"], _dp(g.get("b")))
        elif kind == "range":
            b = num(g.get("b"))
            out.update(kind="range", low=min(a, b), high=max(a, b))
            out["decimals"] = max(out["decimals"], _dp(g.get("b")))
        elif kind == "sci":
            out.update(kind="single", value=a * 10.0 ** int(g.get("e") or 0))
        else:
            out.update(kind="single", value=a, qual=(g.get("q") or ""))
        return out
    out["kind"] = "text"
    return out


def _dp(txt):
    if not txt:
        return 0
    t = str(txt).split("e")[0].split("E")[0]
    return len(t.split(".", 1)[1]) if "." in t else 0


def mid_value(p):
    if p["kind"] == "single":
        return p["value"]
    if p["kind"] in ("range", "pm"):
        vals = [v for v in (p.get("low"), p.get("high"), p.get("value")) if v is not None]
        return sum(vals) / len(vals) if vals else None
    return None


# --------------------------------------------------------------------- units
def sig(dim):
    return ",".join("%s:%d" % (k, dim[k]) for k in sorted(dim) if dim[k])


class Units:
    def __init__(self, table):
        self.pf = {str(k): float(v) for k, v in (table.get("prefixes") or {}).items()}
        self.canon = {}
        self.unknown = {str(x).lower() for x in (table.get("unknown_tokens") or [])}
        self.ambiguous = {str(x).lower() for x in (table.get("ambiguous_tokens") or [])}
        self.sym = {}
        for key, val in (table.get("units") or {}).items():
            entry = (dict(val.get("dim") or {}), float(val.get("scale", 1.0)),
                     float(val.get("offset", 0.0)))
            self.sym.setdefault(key, entry)
            for alias in val.get("aliases") or []:
                self.sym.setdefault(alias, entry)
        for alias, target in (table.get("extra_aliases") or {}).items():
            if target in self.sym:
                self.sym.setdefault(alias, self.sym[target])
        for key, name in (table.get("canonical") or {}).items():
            parsed = self.parse(name)
            self.canon[parsed["sig"] if parsed.get("ok") else key] = name
        self.version = table.get("version", "1.0.0")

    def token(self, tok):
        if tok in ("1", "1.0", "-"):
            return ({}, 1.0, 0.0)
        m = re.fullmatch(r"10\^([-+]?\d+)", tok)
        if m:
            return ({}, 10.0 ** int(m.group(1)), 0.0)
        m = re.fullmatch(r"([A-Za-z\u00b0\u00c5%]+)(?:\^?([-+]?\d+))?", tok)
        if not m:
            return None
        sym, exp = m.group(1), int(m.group(2) or 1)
        entry = self.sym.get(sym)
        if entry is None:
            for i in range(len(sym) - 1, 0, -1):
                pre, rest = sym[:i], sym[i:]
                if pre in self.pf and rest in self.sym:
                    dim, scale, off = self.sym[rest]
                    entry = (dim, scale * self.pf[pre], off)
                    break
        if entry is None:
            return None
        dim, scale, off = entry
        return ({k: v * exp for k, v in dim.items()}, scale ** exp, off if exp == 1 else 0.0)

    def parse(self, text):
        if text is None:
            return {"ok": False, "reason": "empty"}
        s = unicodedata.normalize("NFKC", str(text)).strip()
        s = s.replace("\u03bc", "u").replace("\u00b5", "u").replace("\u2212", "-")
        s = s.replace("\u00b7", "*").replace("\u22c5", "*").replace("\u00d7", "*")
        s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
        s = re.sub(r"\s+", " ", s).strip(" .,;")
        if not s:
            return {"ok": False, "reason": "empty"}
        if s.lower() in self.unknown:
            return {"ok": False, "reason": "unknown_token", "token": s}
        if s.lower() in self.ambiguous:
            return {"ok": False, "reason": "ambiguous_token", "token": s}
        dim, scale, offset, ntok, sign = {}, 1.0, 0.0, 0, 1
        for tok in re.findall(r"[*/]|[^\s*/]+", s):
            if tok in ("*", "/"):
                sign = 1 if tok == "*" else -1
                continue
            hit = self.token(tok)
            if hit is None:
                return {"ok": False, "reason": "unknown_token", "token": tok}
            d, sc, of = hit
            for k, e in d.items():
                dim[k] = dim.get(k, 0) + e * sign
            scale *= sc ** sign
            offset += of if sign == 1 else 0.0
            ntok += 1
        dim = {k: v for k, v in dim.items() if v}
        return {"ok": True, "dim": dim, "sig": sig(dim), "scale": scale,
                "offset": offset if ntok == 1 else 0.0, "tokens": ntok, "text": s}

    def convert(self, src, dst):
        a, b = self.parse(src), self.parse(dst)
        if not a.get("ok") or not b.get("ok"):
            bad = a if not a.get("ok") else b
            return {"ok": False, "reason": bad.get("reason", "unparsed_unit"),
                    "token": bad.get("token", "")}
        if a["sig"] != b["sig"]:
            return {"ok": False, "reason": "dim_mismatch", "from_sig": a["sig"], "to_sig": b["sig"]}
        return {"ok": True, "factor": a["scale"] / b["scale"],
                "offset": (a["offset"] - b["offset"]) / b["scale"]}

    def canonical(self, unit):
        p = self.parse(unit)
        return self.canon.get(p["sig"]) if p.get("ok") else None

    def to_canonical(self, value, unit):
        """Value re-expressed for comparison: canonical unit, else SI base units."""
        p = self.parse(unit)
        if not p.get("ok") or value is None:
            return None, None
        target = self.canon.get(p["sig"])
        if not target:
            return value * p["scale"] + p["offset"], "SI-base"
        res = self.convert(unit, target)
        if not res.get("ok"):
            return value * p["scale"] + p["offset"], "SI-base"
        return value * res["factor"] + res["offset"], target


def exec_formula(before, factor, offset):
    try:
        return float(before) * float(factor or 0.0) + float(offset or 0.0)
    except (TypeError, ValueError):
        return None


def formula_text(before, ub, factor, offset, after, ua):
    if offset:
        return "(%s %s) x %s + %s = %s %s" % (fmt(before), ub, fmt(factor), fmt(offset),
                                              fmt(after), ua)
    return "%s %s x %s = %s %s" % (fmt(before), ub, fmt(factor), fmt(after), ua)


def verify_quote(blob, quote):
    """Verbatim (or whitespace-insensitive) containment of quote in the source row."""
    q, b = norm_cell(quote), norm_cell(blob)
    if not q:
        return False, "empty_quote"
    if q in b:
        return True, "exact"
    if re.sub(r"\s+", "", q) in re.sub(r"\s+", "", b):
        return True, "whitespace_insensitive"
    return False, "not_found"


# -------------------------------------------------------- roles and objects
def detect_roles(cols, fdict):
    """Two-pass column role detection: exact key match, then word-boundary hit."""
    syn = fdict.get("roles") or {}
    roles, used = {}, set()
    norm = {c: nkey(c) for c in cols}
    for role in ROLE_ORDER:
        cands = {nkey(x) for x in syn.get(role, [])}
        for col in cols:
            if col not in used and norm[col] in cands:
                roles[col] = role
                used.add(col)
    for role in ROLE_ORDER:
        if role in roles.values():
            continue
        cands = sorted({nkey(x) for x in syn.get(role, [])}, key=len, reverse=True)
        for col in cols:
            if col in used:
                continue
            if any(len(c) >= 3 and re.search(r"(^|\s)%s(\s|$)" % re.escape(c), norm[col])
                   for c in cands):
                roles[col] = role
                used.add(col)
                break
    return roles


def build_objects(tables, fdict, idx):
    """One object per extraction row; row identity is preserved verbatim."""
    objects, columns_all, seen = [], [], {}
    msyn = (fdict.get("synonyms") or {}).get("material") or {}
    isyn = (fdict.get("synonyms") or {}).get("indicator") or {}
    for tab in tables:
        cols = list(tab["columns"])
        roles = detect_roles(cols, fdict)
        notes = [c for c in cols if c not in roles and any(h in nkey(c) for h in NOTE_HINT)]
        conds = [c for c in cols if c not in roles and c not in notes]
        inv = {}
        for col, role in roles.items():
            inv.setdefault(role, col)
        for c in cols:
            if c not in columns_all:
                columns_all.append(c)
        for i, raw in enumerate(tab["rows"]):
            row = {str(k): ("" if v is None else str(v)) for k, v in raw.items()}
            rid = str(row.get(inv.get("row_id", ""), "")).strip()
            if not rid:
                rid = "derived-%d" % (i + 1)
                idx["degradations"].append({"stage": "identity", "file": tab["file"],
                                            "note": "row %d had no id, generated %s" % (i + 1, rid)})
            if rid in seen:
                seen[rid] += 1
                idx["degradations"].append({"stage": "identity", "file": tab["file"],
                                            "note": "duplicate row id %s -> %s#%d"
                                                    % (rid, rid, seen[rid])})
                rid = "%s#%d" % (rid, seen[rid])
            else:
                seen[rid] = 1
            cells = {k: str(row.get(inv.get(k, ""), "")) for k in
                     ("value", "unit", "indicator", "material", "value_low", "value_high",
                      "value_err")}
            blob = json.dumps(row, ensure_ascii=False) + " " + " ".join(
                v for v in cells.values() if v)
            objects.append({"locator": "%s#%s" % (tab["file"], rid), "row_id": rid,
                            "file": tab["file"], "index": i,
                            "source_document_id": str(row.get(inv.get("source_document_id", ""), "")).strip(),
                            "source_locator": str(row.get(inv.get("source_locator", ""), "")).strip(),
                            "raw": row, "cells": cells,
                            "conditions": {c: str(row.get(c, "")).strip() for c in conds},
                            "blob": blob, "roles": roles, "note_columns": notes,
                            "key_material": canonical(cells["material"], msyn)[0],
                            "key_indicator": canonical(cells["indicator"], isyn)[0]})
    mapped = {c for o in objects for c in o["roles"]}
    conditions = sorted({c for o in objects for c in o["conditions"]})
    columns = {"all": columns_all,
               "roles": sorted({c: r for o in objects for c, r in o["roles"].items()}.items()),
               "conditions": conditions,
               "unmapped": [c for c in columns_all if c not in mapped and c not in conditions]}
    return objects, columns


def judgment_key(obj):
    """source + every condition + normalised indicator + normalised material.

    Different papers and different conditions therefore never collide, while
    spelling variants of one measurement do.
    """
    cond = ";".join("%s=%s" % (k, v) for k, v in sorted(obj["conditions"].items()) if v != "")
    return "|".join([obj["source_document_id"] or obj["file"], cond,
                     obj.get("key_indicator") or nkey(obj["cells"].get("indicator") or ""),
                     obj.get("key_material") or nkey(obj["cells"].get("material") or "")])


def group_candidates(objects, units, tol=0.05):
    """Group rows that claim to describe the same measurement, with a first-pass signal."""
    buckets = {}
    for obj in objects:
        p = parse_cell(obj["cells"].get("value"))
        unit = obj["cells"].get("unit") or p["unit_inline"]
        val = mid_value(p)
        canon, canon_unit = (units.to_canonical(val, unit) if val is not None and unit
                             else (None, None))
        buckets.setdefault(judgment_key(obj), []).append(
            {"obj": obj, "val": val, "canon": canon, "unit": unit,
             "unit_norm": (units.parse(unit).get("text") or "") if unit else "", "p": p})
    groups = []
    for key in sorted(buckets):
        members = buckets[key]
        if len(members) < 2:
            continue
        vals = [m["canon"] if m["canon"] is not None else m["val"] for m in members]
        nums = [v for v in vals if v is not None]
        unit_set = sorted({m["unit_norm"] for m in members if m["unit_norm"]})
        exact = len({json.dumps(m["obj"]["raw"], ensure_ascii=False, sort_keys=True)
                     for m in members}) == 1
        signal, reason, spread = "undetermined", "non-numeric or unparsed unit", None
        if len(nums) == len(members) and nums:
            lo, hi = min(nums), max(nums)
            scale = max(abs(lo), abs(hi), 1e-30)
            spread = (hi - lo) / scale
            if spread <= 1e-9:
                signal, reason = "duplicate_record", "identical value under the same key"
            elif spread <= tol:
                signal, reason = "replicate", "spread %.3g within replicate tolerance %.3g" % (spread, tol)
            else:
                signal, reason = "conflict", "spread %.3g beyond tolerance %.3g" % (spread, tol)
        groups.append({"group_id": "G%02d" % (len(groups) + 1), "key": key,
                       "row_ids": [m["obj"]["row_id"] for m in members],
                       "locators": [m["obj"]["locator"] for m in members],
                       "values": [fmt(v) for v in vals],
                       "units": unit_set, "unit_variants": len(unit_set) > 1,
                       "exact_copy": exact, "signal": signal, "reason": reason,
                       "spread": None if spread is None else round(spread, 6)})
    return groups


# ------------------------------------------------------ discovery utilities
ART_KINDS = [("mapping|map|mapped", "field_mapping.json"), ("unit", "unit_table.json"),
             ("change|audit|history|log", "change_log.csv"),
             ("pending|review|hold|manual|confirm", "pending_review.csv"),
             ("anomal|report|issue|quality", "anomaly_report.md"),
             ("rule", "rules.json"), ("clean|table|normal|standard|dataset", "cleaned.csv")]
ART_DEFAULT = sorted(n for _, n in ART_KINDS)
REC_KEYS = ("records", "rows", "data", "items", "measurements", "extractions", "entries",
            "observations", "points", "samples", "lines", "table", "results")


def find_rows(obj):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if not isinstance(obj, dict):
        return []
    for key in REC_KEYS + tuple(sorted(obj)):
        val = obj.get(key)
        if isinstance(val, list) and val and all(isinstance(x, dict) for x in val):
            return val
        if isinstance(val, dict):
            hit = find_rows(val)
            if hit:
                return hit
    return []


def walk_strings(obj, acc=None):
    acc = [] if acc is None else acc
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for val in obj.values():
            walk_strings(val, acc)
    elif isinstance(obj, list):
        for val in obj:
            walk_strings(val, acc)
    return acc


def artifact_names(contract):
    """Honour the file names the case itself names inside output_contract."""
    out, used = {}, set()
    for raw in walk_strings(contract):
        base = raw.strip().replace("\\", "/").split("/")[-1]
        if not re.search(r"\.(csv|json|md|jsonl|tsv)$", base, re.I):
            continue
        for pat, name in ART_KINDS:
            if name in out or name in used:
                continue
            if any(h in base.lower() for h in pat.split("|")):
                out[name], _ = base, used.add(base)
                break
    for name in ART_DEFAULT:
        out.setdefault(name, name)
    return out


def iter_files(root):
    root = Path(root)
    if not root.exists():
        return []
    return [p for p in sorted(root.rglob("*"))
            if p.is_file() and not any(x.startswith(".") or x == "__pycache__" for x in p.parts)]


def try_json(text):
    try:
        return json.loads(text), None
    except Exception as exc:                                     # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def read_table(text, ext):
    delim = "\t"
    if ext != ".tsv":
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
        except Exception:                                        # noqa: BLE001
            delim = ","
    try:
        rows = [{(("" if k is None else str(k))).strip(): ("" if v is None else str(v))
                 for k, v in r.items()}
                for r in csv.DictReader(text.splitlines(), delimiter=delim)]
    except Exception as exc:                                     # noqa: BLE001
        return [], [], "%s: %s" % (type(exc).__name__, str(exc)[:120])
    rows = [r for r in rows if any(str(v).strip() for v in r.values())]
    return rows, (list(rows[0].keys()) if rows else []), None


def rules_of(obj):
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict) and ("rule_id" in r or "id" in r)]
    if not isinstance(obj, dict):
        return []
    for key in ("rules", "rule_set", "catalog", "cleaning_rules", "items"):
        val = obj.get(key)
        if isinstance(val, list):
            got = [r for r in val if isinstance(r, dict) and ("rule_id" in r or "id" in r)]
            if got:
                return got
    return [obj] if ("rule_id" in obj or "id" in obj) and "condition" in obj else []


def is_schema(obj, low):
    if not isinstance(obj, dict):
        return False
    if any(h in low for h in ("schema", "dictionar", "field", "column", "\u5b57\u6bb5")):
        return True
    return any(isinstance(obj.get(k), (dict, list)) and obj.get(k) for k in
               ("target_fields", "fields", "schema", "columns", "field_dictionary"))


def schema_fields(obj):
    for key in ("target_fields", "fields", "schema", "field_dictionary", "columns"):
        val = obj.get(key)
        if isinstance(val, dict) and val:
            return {str(k): (v if isinstance(v, dict) else {"label": v}) for k, v in val.items()}
        if isinstance(val, list) and val:
            return {str(v): {} for v in val if isinstance(v, str)}
    return {}


def merge_rules(builtin, case_rules):
    """Case rules default to priority 5 and win an id collision; the loser is recorded."""
    rules, suppressed = [dict(r) for r in builtin], []
    for raw in case_rules:
        rec = {"rule_id": str(raw.get("rule_id") or raw.get("id")),
               "priority": int(raw.get("priority", 5)), "name": raw.get("name", ""),
               "applies_to": raw.get("applies_to", "value"),
               "condition": raw.get("condition", ""),
               "transform": raw.get("transform") or raw.get("action") or "",
               "examples": raw.get("examples") or [],
               "failure_mode": raw.get("failure_mode", ""),
               "human_gate": bool(raw.get("human_gate", False)),
               "owner": raw.get("owner", "script"), "source": "case"}
        for i, old in enumerate(rules):
            if old["rule_id"] == rec["rule_id"]:
                win = rec["priority"] <= int(old.get("priority", 100))
                lost, kept = (old, rec) if win else (rec, old)
                suppressed.append({"rule_id": lost["rule_id"], "by": kept["rule_id"],
                                   "reason": "lower priority number wins",
                                   "kept_source": kept.get("source", "builtin")})
                if win:
                    rules[i] = rec
                break
        else:
            rules.append(rec)
    rules.sort(key=lambda r: (int(r.get("priority", 100)), r["rule_id"]))
    return rules, suppressed
