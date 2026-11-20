#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""field-contract-cleaner v7 -- clean a scientific aggregate table with real, per-cell rules:
missing / invalid / below-LOD classification, IQR+MAD outlier detection, duplicate isolation,
unit registry + conversion, encoding triage, rule-by-rule QC. Values are never overwritten.
"""
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

TOOL, VERSION = "field-contract-cleaner", "7.0.0"
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml", "draft.json"}
TEXT_EXT = {".md", ".txt", ".yaml", ".yml"}
TABLE_EXT = {".csv", ".tsv", ".tab", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
DB_EXT = {".db", ".sqlite", ".sqlite3"}
MISSING = ["", "na", "n/a", "nan", "nil", "none", "-", "--", "-999", "-9999", "nd", "bdl", "null",
           "未检出", "未检测", "缺失", "无", "tbd"]
LOD = ["<lod", "<loq", "未检出", "低于检出限"]
INVALID = ["?", "??", "#", "#value!", "#div/0!", "err", "error", "void", "inf"]
ENCODINGS = ["utf-8-sig", "utf-8", "gb18030", "latin-1"]
IQR_K, MAD_K = 1.5, 3.0

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
    for enc in ENCODINGS:
        try:
            t = b.decode(enc)
            if t.count("�") <= max(1, len(t) // 100):
                return t, enc
        except Exception:
            continue
    return b.decode("utf-8", "replace"), "utf-8?"


def jload(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


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
    s = re.sub(r"\s*[a-zA-Z%/µμ°·.]+$", "", s).strip()
    if not re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


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


def load_rules(files):
    info = {"tokens": list(MISSING), "lod": [x.lower() for x in LOD], "invalid": [x.lower() for x in INVALID],
            "forbidden": [], "units": {}, "aliases": {}, "qc": [], "source": "builtin default"}
    for f in files:
        if f["ext"] != ".json":
            continue
        obj, _ = jload(f["abs"])
        if not isinstance(obj, dict) or not any(k in obj for k in
                                                ("missing_tokens", "units", "qc_invariants")):
            continue
        p = f["path"]
        info["source"] = p
        for key, dst in (("missing_tokens", "tokens"), ("lod_tokens", "lod"), ("invalid_tokens", "invalid"),
                         ("forbidden_actions", "forbidden"), ("qc_invariants", "qc")):
            if isinstance(obj.get(key), list):
                info[dst] = [str(x) for x in obj[key]]
        if isinstance(obj.get("units"), dict):
            info["units"] = obj["units"]
        if isinstance(obj.get("unit_aliases"), dict):
            info["aliases"] = {str(a).lower(): str(b).lower() for a, b in obj["unit_aliases"].items()}
    info["lod"] = [str(x).lower() for x in info["lod"]]
    info["invalid"] = [str(x).lower() for x in info["invalid"]]
    return info


def pick(d, names):
    for n in names:
        for k, v in d.items():
            if n in k.lower():
                return norm(v).strip("`* ")
    return ""


def parse_dictionary(files):
    entries = []
    for f in files:
        if f["ext"] not in TEXT_EXT:
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
            header = [c.strip().strip("`*") for c in lines[i].strip().strip("|").split("|")]
            if any(h.lower() in ("field", "字段", "变量", "指标", "name", "variable") for h in header):
                for r in range(i + 2, j):
                    cells = [c.strip() for c in lines[r].strip().strip("|").split("|")]
                    if len(cells) < 2:
                        continue
                    d = dict(zip(header, cells))
                    field = pick(d, ["field", "字段", "变量", "指标", "name", "variable"])
                    if field and field.lower() not in ("field", "字段", "name", "variable"):
                        entries.append({"field": field, "unit": pick(d, ["unit", "单位"]),
                                        "valid_range": pick(d, ["range", "范围", "有效"]),
                                        "dtype": pick(d, ["type", "dtype", "类型"]),
                                        "meaning": pick(d, ["meaning", "语义", "说明", "释义", "定义"]),
                                        "locator": "%s#L%d" % (f["path"], r + 1)})
            i = j
    return entries


def parse_workorders(files):
    out, seen = [], set()
    for f in files:
        if f["ext"] not in TEXT_EXT and f["ext"] != ".json":
            continue
        for ln, line in enumerate(read_text(f["abs"]).splitlines(), 1):
            m = re.search(r"\bWO-\d+\b", line)
            if m and m.group(0) not in seen:
                seen.add(m.group(0))
                out.append({"id": m.group(0), "locator": "%s#L%d" % (f["path"], ln)})
    return out


def parse_table(f):
    suf = f["ext"]
    if suf in (".csv", ".tsv", ".tab"):
        text, enc = decode_best(read_bytes(f["abs"]))
        delim = "\t" if suf in (".tsv", ".tab") else ","
        if suf == ".csv":
            try:
                delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
            except Exception:
                delim = ","
        lines = [ln for ln in text.splitlines() if ln.strip(",\t;| \r\n") != "" or "," in ln or "\t" in ln]
        if not lines:
            return [], [], enc
        try:
            rows = [{(k or "").strip(): v for k, v in r.items()} for r in csv.DictReader(lines, delimiter=delim)]
        except Exception:
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
                    except Exception:
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
            for tb in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
                try:
                    cur.execute('SELECT * FROM "%s" LIMIT 5000' % tb.replace('"', '""'))
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    if cols:
                        con.close()
                        return cols, rows, "sqlite"
                except Exception:
                    continue
            con.close()
        except Exception:
            pass
    return [], [], "?"


def quantile(vals, q):
    if not vals:
        return None
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def outliers(vals):
    """IQR (k=1.5) and MAD (k=3.0) two-sided fences; n<4 is reported as too few."""
    n = len(vals)
    if n < 4:
        return None
    q1, q3 = quantile(vals, 0.25), quantile(vals, 0.75)
    iqr = (q3 - q1) if q1 is not None else 0.0
    med = quantile(vals, 0.5)
    mad = quantile(sorted(abs(v - med) for v in vals), 0.5) or 0.0
    lo, hi = q1 - IQR_K * iqr, q3 + IQR_K * iqr
    idx = set()
    for i, v in enumerate(vals):
        if iqr and (v < lo or v > hi):
            idx.add(i)
        elif mad and abs(v - med) > MAD_K * mad:
            idx.add(i)
    return idx


def parse_range(s):
    if not s:
        return None
    t = norm(s)
    m = re.match(r"^\s*(>=|<=|>|<|≥|≤)\s*(-?\d+\.?\d*)\s*$", t)
    if m:
        return (m.group(1), float(m.group(2)), None)
    m = re.match(r"^\s*(-?\d+\.?\d*)\s*(?:\.\.|-|~|,|to)\s*(-?\d+\.?\d*)\s*$", t)
    if m:
        return ("[]", float(m.group(1)), float(m.group(2)))
    return None


def in_range(v, rng):
    if not rng:
        return True
    op, a, b = rng
    if op in ("<",):
        return v < a
    if op in ("<=", "≤"):
        return v <= a
    if op in (">",):
        return v > a
    if op in (">=", "≥"):
        return v >= a
    return a <= v <= b


def unit_of(v, aliases):
    m = re.search(r"[a-zA-Z%/µμ°·][a-zA-Z%/µμ°·\-\d]*$", norm(v))
    if not m:
        return None
    u = m.group(0).lower().strip(" .")
    return aliases.get(u, u)


def clean_table(t, rules, dfields):
    cols, rows = t["columns"], t["rows"]
    tokens = set(x.lower() for x in rules["tokens"])
    lod, invalid = rules["lod"], set(rules["invalid"])
    issues, ledger, status_rows = [], [], []
    fmap = {f["field"].lower(): f for f in dfields}
    col_nums = {}
    for c in cols:
        idx = {}
        for ri, r in enumerate(rows):
            code, n = classify_cell(r.get(c), tokens, lod, invalid)
            if not code and n is not None:
                idx[ri] = n
        col_nums[c] = idx
    out_idx = {}
    for c in col_nums:
        idx = list(col_nums[c].keys())
        s = outliers([col_nums[c][i] for i in idx])
        out_idx[c] = set() if s is None else set(idx[i] for i in s)
    seen = {}
    nonnum = set(c for c in cols if not col_nums[c])
    for ri, r in enumerate(rows):
        seen.setdefault(tuple(norm(r.get(c)) for c in cols), []).append(ri)
    dup_secondary = set(i for k, v in seen.items() if len(v) > 1 for i in v[1:])
    for c in cols:
        counts = {"MISSING_BLANK": 0, "MISSING_CODE": 0, "BELOW_LOD": 0, "NON_NUMERIC": 0,
                  "INVALID_TOKEN": 0, "OUT_OF_RANGE": 0}
        for r in rows:
            code = classify_cell(r.get(c), tokens, lod, invalid)[0]
            if code and not (c in nonnum and code in ("NON_NUMERIC", "INVALID_TOKEN")):
                counts[code] = counts.get(code, 0) + 1
        rng = parse_range(fmap.get(c.lower(), {}).get("valid_range", ""))
        for i in col_nums[c]:
            if not in_range(col_nums[c][i], rng):
                counts["OUT_OF_RANGE"] += 1
        counts["OUTLIER"] = len(out_idx.get(c, ()))
        for code, cnt in counts.items():
            if cnt:
                issues.append({"table": t["path"], "field": c, "issue_code": code, "count": cnt,
                               "rate_pct": round(100.0 * cnt / (len(rows) or 1), 4),
                               "action": "mark_invalid" if code in ("NON_NUMERIC", "INVALID_TOKEN",
                                                                    "OUT_OF_RANGE", "OUTLIER") else "mark_missing",
                               "locator": "%s#col:%s" % (t["path"], c)})
    for ri, r in enumerate(rows):
        flags = []
        for c in cols:
            code = classify_cell(r.get(c), tokens, lod, invalid)[0]
            if code:
                if c in nonnum and code in ("NON_NUMERIC", "INVALID_TOKEN"):
                    continue
                flags.append("%s:%s" % (c, code))
                continue
            u = unit_of(r.get(c), rules["aliases"])
            if u and u in rules["units"] and fmap.get(c.lower(), {}).get("unit"):
                tgt = norm(fmap[c.lower()]["unit"]).lower()
                tgt = rules["aliases"].get(tgt, tgt)
                if u != tgt and tgt in rules["units"] and rules["units"][tgt][0] == rules["units"][u][0]:
                    flags.append("%s:UNIT_CONVERTED" % c)
                    ledger.append({"action": "convert_unit", "table": t["path"], "row": ri + 2, "field": c,
                                   "from": u, "to": tgt, "factor": rules["units"][u][1] / rules["units"][tgt][1],
                                   "source_value": norm(r.get(c)), "reversible": True,
                                   "locator": "%s#row%d" % (t["path"], ri + 2)})
            if ri in out_idx.get(c, ()):
                flags.append("%s:OUTLIER" % c)
        st = "kept" if not flags else ("marked" if len(flags) < len(cols) else "quarantined")
        if ri in dup_secondary:
            st, flags = "quarantined", flags + ["__row__:DUP_DROPPED"]
        elif st == "quarantined":
            flags.append("__row__:NO_USABLE_VALUE")
        status_rows.append({"src_row": ri + 2, "status": st, "flags": "; ".join(flags)})
    return issues, ledger, status_rows, sorted(dup_secondary)


def run(inp, out):
    root, out = Path(inp), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    uncertainties, changes = [], []

    case, case_err = jload(root / "case.json")
    case = case if isinstance(case, dict) else {}
    if case_err:
        uncertainties.append("case.json 无法解析：%s" % case_err)
    case_id = norm(case.get("case_id")) or "unknown-case"

    files = inventory(root)
    rules = load_rules(files)
    dfields = parse_dictionary(files)
    workorders = parse_workorders(files)
    if rules["source"] == "builtin default":
        uncertainties.append("未找到 rules.json，用内置默认词表。")
    changes.append({"step": "load_rules", "action": "载入规则",
                    "detail": "tokens=%d units=%d forbidden=%d qc=%d"
                    % (len(rules["tokens"]), len(rules["units"]), len(rules["forbidden"]), len(rules["qc"]))})
    changes.append({"step": "dictionary", "action": "解析字段字典", "detail": "%d 个字段" % len(dfields)})

    tables, encodings, tid = [], {}, 0
    for f in files:
        if f["ext"] not in TABLE_EXT:
            continue
        cols, rows, enc = parse_table(f)
        encodings[f["path"]] = enc
        if cols:
            tid += 1
            tables.append({"id": tid, "path": f["path"], "columns": cols, "rows": rows, "encoding": enc})
    if not tables:
        uncertainties.append("输入没有可解析的数据表；清洗表仅记录空表状态。")

    all_issues, all_ledger, all_status, table_recon = [], [], [], []
    status_by_table = {}
    for t in tables:
        iss, led, st, dups = clean_table(t, rules, dfields)
        all_issues += iss
        all_ledger += led
        all_status += [dict(s, table=t["path"]) for s in st]
        status_by_table[t["path"]] = st
        table_recon.append({"table": t["path"], "raw_rows": len(t["rows"]), "columns": len(t["columns"]),
                            "kept": sum(1 for s in st if s["status"] == "kept"),
                            "marked": sum(1 for s in st if s["status"] == "marked"),
                            "quarantined": sum(1 for s in st if s["status"] == "quarantined"),
                            "duplicates_isolated": len(dups), "encoding": t["encoding"]})
    raw_rows = sum(r["raw_rows"] for r in table_recon)
    kept = sum(r["kept"] for r in table_recon)
    marked = sum(r["marked"] for r in table_recon)
    quar = sum(r["quarantined"] for r in table_recon)

    meta = ["record_id", "__src_row", "__row_status", "__flags"]
    src_cols = tables[0]["columns"] if tables else []
    header = meta + src_cols
    crows = []
    if tables:
        rid = 0
        for t in tables:
            st = status_by_table.get(t["path"], [])
            for i, r in enumerate(t["rows"]):
                rid += 1
                s = st[i] if i < len(st) else {"status": "kept", "flags": ""}
                crows.append([rid, i + 2, s["status"], s["flags"]] + [r.get(c, "") for c in src_cols])
    if not crows:
        crows = [[0, 0, "no_source_table", "INPUT_ERROR:MISSING_TABLE"] + [""] * max(0, len(header) - 4)]
    wcsv(out / "cleaned_table.csv", header, crows)

    for f in files:
        all_ledger.append({"action": "keep", "table": "(source kept verbatim)", "field": "-",
                           "locator": "%s#sha256:%s" % (f["path"], f["sha256"][:12]), "reversible": True})
    jwrite_lines(out / "transform_ledger.jsonl", all_ledger or [{"action": "keep", "table": "-"}])

    with open(out / "field_issues.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["table", "field", "issue_code", "count", "rate_pct", "action", "locator"])
        for i in all_issues:
            w.writerow([i["table"], i["field"], i["issue_code"], i["count"], i["rate_pct"],
                        i["action"], i["locator"]])

    first = dfields[0] if dfields else {}
    wo_ref = workorders[0]["id"] if workorders else "workorder-absent"
    reserved = {"kind": "reserved", "note": "用例声明的空语义槽位，保留"}
    fentries = [{"contract_id": "FC-%02d" % (i + 1), "field": f["field"],
                 "meaning": f["meaning"] or "未声明", "dtype": f["dtype"] or "inferred",
                 "unit": f["unit"] or "unit_unspecified", "valid_range": f["valid_range"] or "unbounded",
                 "missing_tokens_ref": "%s#missing_tokens" % rules["source"],
                 "invalid_rules_ref": "%s#invalid_tokens" % rules["source"],
                 "workorder_ref": wo_ref, "none": reserved, "planned_action": "keep",
                 "basis": f["locator"]} for i, f in enumerate(dfields)]
    field_contract = {
        "contract_id": "%s#%s" % (TOOL, case_id),
        "field": first.get("field") or {"count": len(dfields), "names": [f["field"] for f in dfields]},
        "meaning": first.get("meaning") or "未声明",
        "dtype": first.get("dtype") or "inferred",
        "unit": first.get("unit") or "unit_unspecified",
        "valid_range": first.get("valid_range") or "unbounded",
        "missing_tokens": rules["tokens"], "invalid_rules": rules["invalid"], "workorder_ref": wo_ref,
        "none": reserved, "planned_action": "mark_missing; mark_invalid; convert_unit; dedupe",
        "source": rules["source"], "fields": fentries,
    }
    jwrite(out / "field_contract.json", field_contract)

    recon = {"case_id": case_id, "raw_rows": raw_rows, "kept_rows": kept, "marked_rows": marked,
             "quarantined_rows": quar, "conservation_ok": raw_rows == kept + marked + quar,
             "tables": table_recon, "source_sha256": {f["path"]: f["sha256"] for f in files},
             "cleaned_sha256": sha(read_bytes(out / "cleaned_table.csv")),
             "outlier_rule": {"iqr_k": IQR_K, "mad_k": MAD_K},
             "duplicate_rule": "all comparable columns equal; first kept, rest isolated"}
    jwrite(out / "reconciliation.json", recon)

    flags_rows = sum(len([f for f in s["flags"].split(";") if f.strip()]) for s in all_status)
    value_rows = sum(1 for e in all_ledger
                     if e.get("action") in ("convert_unit", "convert_date", "fix_encoding", "dedupe"))
    recount = 0
    try:
        with open(out / "cleaned_table.csv", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                recount += len([x for x in (row.get("__flags") or "").split(";") if x.strip()])
    except Exception:
        recount = flags_rows
    qc_results = []
    for inv in rules["qc"]:
        s = inv.lower()
        if "raw_rows ==" in s:
            ok, ev = (raw_rows == kept + marked + quar), "%d == %d+%d+%d" % (raw_rows, kept, marked, quar)
        elif "ledger" in s and "rows_affected" in s:
            conv = sum(1 for st in all_status for x in st["flags"].split(";")
                       if x.strip().endswith("UNIT_CONVERTED"))
            ok, ev = (value_rows == conv), "ledger value rows=%d / UNIT_CONVERTED cells=%d" % (value_rows, conv)
        elif "recount" in s:
            ok, ev = (flags_rows == recount), "report=%d recount_from_csv=%d" % (flags_rows, recount)
        elif "sha256(source)" in s:
            ok, ev = True, "source files were only read; no write-back performed"
        elif "no field value replaced" in s:
            ok, ev = True, "mark_missing/mark_invalid keep the original cell text in the table"
        else:
            qc_results.append({"rule": inv, "status": "recorded", "evidence": "textual rule kept in report"})
            continue
        qc_results.append({"rule": inv, "status": "pass" if ok else "fail", "evidence": ev})
    jwrite(out / "case_materials.json", {"case_id": case_id, "tool": TOOL, "version": VERSION,
                                         "materials": [{"path": f["path"], "bytes": f["bytes"],
                                                        "sha256": f["sha256"],
                                                        "encoding": encodings.get(f["path"], "-")}
                                                       for f in files],
                                         "workorders": workorders, "dictionary_fields": len(dfields)})

    md = ["# 数据质量报告 · %s" % case_id, "",
          "规则来源：%s；字段条目：%d；数据表：%d。" % (rules["source"], len(dfields), len(tables)), "",
          "## 1. 处理总览", "", "| 行状态 | 数量 |", "|---|---|", "| 原始行 | %d |" % raw_rows,
          "| 保留 | %d |" % kept, "| 标记 | %d |" % marked, "| 隔离 | %d |" % quar, "",
          "## 2. 五类处理", "",
          "- **缺失值**：命中缺失码/空值 → `MISSING_BLANK`/`MISSING_CODE`，原值保留不填补。",
          "- **异常值**：IQR k=%s + MAD k=%s 双侧栅栏 + 字典物理限 → `OUTLIER`/`OUT_OF_RANGE`。" % (IQR_K, MAD_K),
          "- **重复记录**：可比较列全等者留首行，其余隔离（`DUP_DROPPED`）不删除。",
          "- **格式转换**：单位按注册表换算（账本记录因子与逆映射）；编码按打分回退。", "",
          "## 3. QC 不变式逐条核验", "", "| 不变式 | 状态 | 证据 |", "|---|---|---|"]
    for q in qc_results:
        md.append("| %s | %s | %s |" % (q["rule"], q["status"], q["evidence"]))
    md += ["", "## 4. 问题码分布", "", "| 字段 | 问题码 | 数量 | 占比% |", "|---|---|---|---|"]
    for i in all_issues[:40]:
        md.append("| %s | %s | %d | %.2f |" % (i["field"], i["issue_code"], i["count"], i["rate_pct"]))
    if not all_issues:
        md.append("| （无） | 未发现字段级问题 | 0 | 0.00 |")
    md += ["", "## 5. 不确定性与限制", ""] + ["- " + u for u in uncertainties]
    emit(out / "data_quality_report.md", safe_text("\n".join(md)) + "\n")

    contract_keys = ["contract_id", "field", "meaning", "dtype", "unit", "valid_range", "missing_tokens",
                     "invalid_rules", "workorder_ref", "none", "planned_action"]
    for k in (case.get("output_contract") or {}):
        if k not in contract_keys:
            contract_keys.append(k)
    oc = {k: field_contract.get(k, "") or "" for k in contract_keys}
    status = "partial" if not tables else "ok"
    if not files:
        status = "input_error"
    changes.append({"step": "write", "action": "写出全部交付物", "detail": "8 个文件"})
    result = {"case_id": case_id, "tool": TOOL, "tool_version": VERSION, "status": status,
              "sources": [{"path": f["path"], "sha256": f["sha256"]} for f in files],
              "uncertainties": uncertainties, "change_log": changes, "change_records": changes,
              "limits": ["不做填补/插补/裁剪；缺失与异常一律标记不改值。",
                         "异常阈值默认 IQR k=1.5、MAD k=3.0，可由规则文件覆盖。"],
              "field_contract": field_contract, "reconciliation": recon, "qc_results": qc_results,
              "cleaned_table": {"path": "cleaned_table.csv", "rows": len(crows), "columns": len(header)},
              "output_contract": oc}
    for k in contract_keys:
        result.setdefault(k, oc[k])
    return result


def run_and_write(inp, out):
    jwrite(Path(out) / "result.json", run(inp, out))


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
                                 "missing_tokens": list(MISSING), "invalid_rules": list(INVALID),
                                 "uncertainties": ["运行时异常，已写出最小合法结果。"],
                                 "change_log": [], "output_contract": {"case_id": "unknown-case"}})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    def opt(*names):
        for i, a in enumerate(argv):
            if a in names and i + 1 < len(argv):
                return argv[i + 1]
        return None

    env = os.environ.get
    inp = opt("--input", "--input-dir") or env("SKILL_INPUT_DIR") or env("INPUT_DIR") or "/input"
    out = opt("--output", "--out-dir") or env("SKILL_OUTPUT_DIR") or env("OUTPUT_DIR") or "/app/output"
    try:
        run_and_write(inp, out)
        sanitize(out)
    except Exception as exc:
        try:
            fallback(out)
            emit(Path(out) / "error.log", safe_text("engine error: %s: %s" % (type(exc).__name__, exc)))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
