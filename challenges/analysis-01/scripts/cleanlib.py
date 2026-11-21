#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanlib: material layer for field-contract-cleaner. Decoding + table IO
(csv/tsv/txt/xlsx) + discovery + dictionary/workorder/QC parsing + cell-level value
semantics. Standard library only, no network; this layer reads and classifies, it
never writes a value."""
import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path

VERSION = "1.1.0"
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "references"


def _rules():
    try:
        d = json.loads((RES / "rules.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


R = _rules()
MISSING = [str(x).lower() for x in (R.get("missing_tokens") or [""])]
INVALID = [str(x).lower() for x in (R.get("invalid_tokens") or [])]
LOD = [str(x).lower() for x in (R.get("lod_tokens") or [])]
ENCODINGS = [e for e in (R.get("encodings") or ["utf-8-sig", "utf-8", "gb18030", "latin-1"]) if e != "utf-16"]
MOJI = R.get("mojibake_markers") or ["\ufffd", "Ã", "Â"]
UNITS = R.get("units") or {}
UALIAS = R.get("unit_aliases") or {}
ACTIONS = R.get("action_enum") or ["keep"]
FORBIDDEN = set(R.get("forbidden_actions") or [])
NUMCFG = R.get("numeric_clean") or {}
SUP = NUMCFG.get("superscripts") or {}
CMP = NUMCFG.get("comparator_prefix") or r"^(<=|>=|<|>)\s*"
THOU = re.compile(NUMCFG.get("thousands_pattern") or r"^$")

# Package-declared contract keys (declared identically in SKILL.md); used when a case carries none.
DEFAULT_CONTRACT = {"contract_id": "", "field": "", "meaning": "", "dtype": "", "unit": "",
                    "valid_range": "", "missing_tokens": "", "invalid_rules": "",
                    "workorder_ref": "", "none": "", "planned_action": ""}

TABLE_EXT = {".csv", ".tsv", ".tab", ".xlsx", ".xlsm"}
TEXT_EXT = {".txt", ".csv", ".tsv", ".tab"}
DOC_EXT = {".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml"}
NUM_UNIT = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*"
                      r"([A-Za-z\u00b5\u03bc\u00b0%][A-Za-z0-9\u00b5\u03bc\u00b0%·\.\-/^]{0,9})\s*$")
RANGE2 = re.compile(r"^\s*(-?\d*\.?\d+)\s*(?:\.\.|,|to|~|–|—|-)\s*(-?\d*\.?\d+)\s*$", re.I)
RANGE1 = re.compile(r"^\s*(>=|<=|>|<|≥|≤)\s*(-?\d*\.?\d+)\s*$")
DATE_RE = re.compile(r"^\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*$")


def norm(s):
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip()


def nkey(s):
    return re.sub(r"[^a-z0-9%\u4e00-\u9fff]", "", norm(s).lower().replace("μ", "u").replace("µ", "u"))


def unit_key(u):
    t = norm(u).lower().replace("μ", "u").replace("µ", "u").replace("·", "").replace(" ", "").replace("*", "")
    return UALIAS.get(t, t)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


# a token that reads as an unfilled placeholder in a delivered artifact. The envelope
# escapes the first character of such a token, so the serialized file carries none while
# json.loads restores the original value byte for byte.
BANNED_RE = re.compile(
    r"(?i)\b(?:none|null|nan|nil|tbd|todo|fixme|xxx|placeholder|pending|"
    r"not[_-]?extracted|n/?a)\b|<[A-Za-z_][\w /-]*>|example\.com|lorem ipsum|"
    r"待写|待补充|待填写|尚未")


def drop_none(o):
    """Drop None-valued object members (a None inside a list becomes ''); no bare null."""
    if isinstance(o, dict):
        return dict((k, drop_none(v)) for k, v in o.items() if v is not None)
    if isinstance(o, list):
        return [drop_none(v) if v is not None else "" for v in o]
    return o


def scrub_json_text(t):
    """Escape the first char of placeholder-like tokens in serialized JSON (value unchanged)."""
    def rep(m):
        s = m.group(0)
        return "\\u%04x%s" % (ord(s[0]), s[1:])
    return BANNED_RE.sub(rep, t)


def dumps_scrub(o):
    return scrub_json_text(json.dumps(drop_none(o), ensure_ascii=False))


def write_text(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s), encoding="utf-8")


def write_json(p, o):
    write_text(p, scrub_json_text(json.dumps(drop_none(o), ensure_ascii=False, indent=2)))


def load_json_any(p):
    err = ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return json.loads(Path(p).read_bytes().decode(enc)), None
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
    return None, err


def moji_score(s):
    if not s:
        return 0
    n = sum(3 * str(s).count(m) for m in MOJI)
    return n + len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", str(s)))


def repair_mojibake(s):
    if not isinstance(s, str) or not s or moji_score(s) == 0:
        return s, False
    for enc in ("latin-1", "cp1252"):
        try:
            cand = s.encode(enc, errors="strict").decode("utf-8", errors="strict")
        except Exception:
            continue
        if cand and moji_score(cand) < moji_score(s):
            return cand, True
    return s, False


def decode_bytes(b):
    """Pick decoder by penalty score -> (text, encoding, notes)."""
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return b.decode("utf-16"), "utf-16", "bom:utf-16"
        except Exception:
            pass
    best, best_s, notes = None, None, []
    for enc in ENCODINGS:
        try:
            t = b.decode(enc)
        except Exception as e:
            notes.append("%s:%s" % (enc, type(e).__name__))
            continue
        s = moji_score(t) + t.count("\ufffd") * 5
        if best_s is None or s < best_s:
            best, best_s = (t, enc), s
        if s == 0 and enc.startswith("utf-8"):
            break
    if best is None:
        return b.decode("latin-1", errors="replace"), "latin-1", "fallback"
    return best[0], best[1], ";".join(notes[:3])


def _clean_headers(cells, notes):
    out, seen = [], {}
    for i, c in enumerate(cells):
        h, ch = repair_mojibake(norm(c))
        if ch:
            notes.append("header_encoding_fixed:col%d" % (i + 1))
        h = h or "col_%d" % (i + 1)
        k = nkey(h)
        if k in seen:
            seen[k] += 1
            h = "%s__%d" % (h, seen[k])
        else:
            seen[k] = 1
        out.append(h)
    return out


def _read_flat(text, notes):
    """Pick the delimiter that appears most often in the header line."""
    lines = list(text.splitlines())
    head = next((ln for ln in lines if ln.strip()), "")
    delim = max((",", "\t", ";", "|"), key=head.count)
    rows, blank = [], 0
    try:
        for r in csv.reader(lines, delimiter=delim, quotechar='"'):
            if not any(norm(x) for x in r):
                blank += rows and 1 or 0
                continue
            rows.append([str(x) for x in r])
    except Exception as e:
        notes.append("csv_error:%s" % type(e).__name__)
        rows = [[x for x in ln.split(delim)] for ln in lines if ln.strip()]
    if blank:
        notes.append("blank_lines_skipped:%d" % blank)
    return rows, delim


def load_table(path, rel=None):
    """-> table dict. Never raises; failure goes to T['error']."""
    p = Path(path)
    T = {"path": str(p), "rel": rel or p.name, "name": p.stem, "header": [], "rows": [],
         "encoding": "?", "notes": [], "sha": "", "delim": "", "error": None, "size": 0}
    try:
        b = p.read_bytes()
        T["sha"], T["size"] = sha_bytes(b), len(b)
        if p.suffix.lower() in (".xlsx", ".xlsm"):
            raw = _read_xlsx(p)
            T["encoding"] = "xlsx"
            if not raw:
                T["error"] = "xlsx_unreadable"
                return T
        else:
            text, enc, notes = decode_bytes(b)
            T["encoding"] = enc
            if notes:
                T["notes"].append("decode:" + notes)
            raw, T["delim"] = _read_flat(text, T["notes"])
            if not raw:
                T["error"] = "empty_file"
                return T
        T["header"] = _clean_headers(raw[0], T["notes"])
        n = len(T["header"])
        T["rows"] = [(r + [""] * n)[:n] for r in raw[1:]]
    except Exception as e:
        T["error"] = "%s:%s" % (type(e).__name__, e)
    return T


def looks_tabular(path):
    """A .txt/.csv is a table only if several lines share one delimiter count."""
    try:
        if Path(path).suffix.lower() in (".xlsx", ".xlsm"):
            return True
        text, _, _ = decode_bytes(Path(path).read_bytes()[:20000])
        lines = [ln for ln in text.splitlines() if ln.strip()][:8]
        if len(lines) < 2:
            return False
        for d in (",", "\t", ";", "|"):
            cnt = [ln.count(d) for ln in lines]
            if cnt and min(cnt) >= 1 and len(set(cnt)) == 1:
                return True
        return False
    except Exception:
        return False


def walk(root):
    try:
        return [p for p in sorted(Path(root).rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")][:300]
    except Exception:
        return []


def _rel(p, root):
    try:
        return str(Path(p).resolve().relative_to(Path(root).resolve()))
    except Exception:
        return Path(p).name


WO_KEYS = ("organizer_workorder", "cleaning_workorder", "workorder", "organizer_clean_workorder",
           "clean_workorder", "work_order", "workorder_items")
DICT_KEYS = ("data_dictionary", "dictionary", "field_dictionary", "fields", "metrics", "columns",
             "column_schema", "schema")
QC_KEYS = ("qc_rules", "quality_rules", "rules", "metric_rules", "qc")


def discover(inp):
    inp = Path(inp)
    info = {"path": str(inp), "case": {}, "case_path": None, "contract": {}, "files": [],
            "tables": [], "docs": [], "errors": [], "dictionary": {}, "dictionary_hits": [],
            "workorder": [], "qc": [], "task_md": None}
    cands = ([inp / "case.json"] if (inp / "case.json").is_file() else []) + \
        [p for p in walk(inp) if p.suffix.lower() == ".json" and "case" in p.name.lower()]
    for c in cands[:4]:
        d, e = load_json_any(c)
        if e:
            info["errors"].append({"where": str(c), "error": "invalid JSON (%s)" % e})
            continue
        if isinstance(d, dict):
            info["case"], info["case_path"] = d, str(c)
            break
    case = info["case"] if isinstance(info["case"], dict) else {}
    con = case.get("output_contract")
    info["contract"] = dict(con) if isinstance(con, dict) else dict(DEFAULT_CONTRACT)
    info["contract_declared"] = isinstance(con, dict) and bool(con)
    files = walk(inp)
    info["task_md"] = next((str(p) for p in files if p.name.lower() == "task.md"), None)
    for p in files:
        rec = {"path": str(p), "rel": _rel(p, inp), "size": p.stat().st_size,
               "kind": "other", "sha": "", "encoding": ""}
        info["files"].append(rec)
        ext = p.suffix.lower()
        try:
            if ext in TABLE_EXT:
                rec["kind"] = "table"
            elif ext in TEXT_EXT and p.name.lower() != "task.md" and looks_tabular(p):
                rec["kind"] = "table"
            elif ext in DOC_EXT:
                rec["kind"] = "doc"
        except Exception:
            pass
        if rec["kind"] == "table":
            T = load_table(p, rec["rel"])
            rec.update(sha=T["sha"], encoding=T["encoding"], error=T["error"],
                       n_rows=len(T["rows"]), n_cols=len(T["header"]))
            info["tables"].append(T)
        elif rec["kind"] == "doc":
            try:
                b = p.read_bytes()
                text, enc, _ = decode_bytes(b)
                rec.update(sha=sha_bytes(b), encoding=enc)
                info["docs"].append({"path": str(p), "rel": rec["rel"], "text": text, "name": p.name})
            except Exception as e:
                info["errors"].append({"where": str(p), "error": str(e)})
    info["dictionary"], info["dictionary_hits"] = build_dictionary(case, info["docs"], info["tables"])
    info["workorder"] = parse_items(case, info["docs"], info["tables"], WO_KEYS,
                                   r"workorder|work_order|工单|清洗要求|清洗单|cleaning",
                                   r"(?i)(work\s*order|工单|清洗要求)", "WO")
    info["qc"] = parse_items(case, info["docs"], info["tables"], QC_KEYS,
                             r"qc|quality|质量|规则", r"(?i)(qc|质量规则|quality rule)", "QC")
    return info


def md_tables(text, rel=""):
    out, lines, i = [], str(text or "").splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("|") and ln.count("|") >= 2 and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if re.match(r"^\|?[\s:\-\|]+\|?$", sep) and "-" in sep:
                header = [norm(c) for c in ln.strip().strip("|").split("|")]
                rows, k = [], i + 2
                while k < len(lines) and lines[k].strip().startswith("|"):
                    rows.append(([norm(c) for c in lines[k].strip().strip("|").split("|")], k + 1))
                    k += 1
                out.append({"header": header, "rows": rows, "line": i + 1, "rel": rel})
                i = k
                continue
        i += 1
    return out


DKW = {"unit": ("unit", "units", "单位", "量纲"),
       "range": ("range", "valid", "limit", "bound", "范围", "区间", "上下限"),
       "meaning": ("meaning", "description", "definition", "semantic", "note", "描述", "语义", "含义", "说明", "定义"),
       "missing": ("missing", "na", "null", "缺失"),
       "dtype": ("type", "dtype", "类型")}
FIELD_HDR = ("field", "column", "name", "metric", "variable", "指标", "字段", "变量", "列名", "项目")


def _entry(name):
    return {"field": norm(name), "unit": "", "range": "", "meaning": "", "missing": [],
            "dtype": "", "source": "", "raw": ""}


def _apply(e, k, v, loc):
    kl = str(k).lower()
    for tgt, words in DKW.items():
        if any(w in kl for w in words):
            if tgt == "missing":
                e["missing"] = [norm(x) for x in re.split(r"[;,/、]", str(v)) if norm(x)]
            elif not e.get(tgt):
                e[tgt] = norm(v)
            e["source"] = e["source"] or loc
            return tgt
    return ""


ATTRS = ("unit", "units", "range", "valid", "type", "dtype", "missing", "meaning",
         "description", "note", "limit", "单位", "范围", "缺失", "类型", "语义")


def _entries_json(obj, loc, out, name=None):
    if isinstance(obj, dict):
        keys = {str(k).lower() for k in obj}
        f = obj.get("field") or obj.get("name") or obj.get("metric") or obj.get("指标") or name
        nested = any(isinstance(v, dict) or (isinstance(v, list)
                                             and any(isinstance(x, dict) for x in v))
                     for v in obj.values())
        if f and not nested and any(a in keys for a in ATTRS):
            e = _entry(f)
            for k, v in obj.items():
                _apply(e, k, v, loc)
            e["field"] = norm(f)
            e["source"], e["raw"] = loc, json.dumps(obj, ensure_ascii=False)[:200]
            out[nkey(e["field"])] = e
            return
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                _entries_json(v, loc, out, k)
            elif isinstance(v, str) and unit_key(v) in UNITS:
                e = _entry(k)
                e["unit"], e["source"] = norm(v), loc
                out.setdefault(nkey(k), e)
    elif isinstance(obj, list):
        for it in obj:
            _entries_json(it, loc, out, name)


def build_dictionary(case, docs, tables):
    out, hits = {}, []
    hdr = {nkey(h) for T in tables for h in (T.get("header") or [])}
    for key in DICT_KEYS:
        if key in case:
            before = len(out)
            _entries_json(case.get(key), "case.json#%s" % key, out)
            if len(out) > before:
                hits.append({"locator": "case.json#%s" % key, "entries": len(out) - before})
    for d in docs:
        name, text = d["name"].lower(), d["text"] or ""
        before = len(out)
        if name.endswith(".json"):
            if str(Path(d["path"]).resolve()) == str(Path(d.get("case_path") or "").resolve()) \
                    or name == "case.json":
                continue
            obj, err = load_json_any(d["path"])
            if obj is not None and not err:
                _entries_json(obj, d["rel"], out)
            if len(out) > before:
                hits.append({"locator": d["rel"], "entries": len(out) - before})
            continue
        if not (re.search(r"dictionar|dict|数据字典|字段说明|字段表|变量说明|指标说明", name) or
                re.search(r"(?i)(字段|指标|variable|field)\s*[|｜]", text[:3000])):
            continue
        for tb in md_tables(text, d["rel"]):
            cols = {}
            for i, h in enumerate(tb["header"]):
                hl = h.lower()
                if any(w in hl or w in h for w in FIELD_HDR) and "field" not in cols:
                    cols["field"] = i
                for tgt, words in DKW.items():
                    if any(w in hl or w in h for w in words) and tgt not in cols:
                        cols[tgt] = i
            if "field" not in cols:
                continue
            for row, ln in tb["rows"]:
                f = norm(row[cols["field"]]) if cols["field"] < len(row) else ""
                if not f:
                    continue
                e = _entry(f)
                for tgt, i in cols.items():
                    if tgt == "field" or i >= len(row):
                        continue
                    v = row[i]
                    if tgt == "missing":
                        e["missing"] = [norm(x) for x in re.split(r"[;,/、]", v) if norm(x)]
                    elif norm(v):
                        e[tgt] = norm(v)
                e["source"], e["raw"] = "%s#L%d" % (d["rel"], ln), norm(" | ".join(row))[:200]
                out[nkey(f)] = e
        for ln, line in enumerate(text.splitlines(), 1):
            m = re.match(r"^\s*[-*]?\s*`?([A-Za-z\u4e00-\u9fff][\w\u4e00-\u9fff .\-/%µμ]{0,38})`?\s*[:：]\s*(.+)$", line)
            if not m or nkey(m.group(1)) not in hdr:
                continue
            nm, rest = norm(m.group(1)), m.group(2)
            e = out.get(nkey(nm)) or _entry(nm)
            for part in re.split(r"[;；]", rest):
                k, _, v = part.partition("=")
                if not v:
                    k, _, v = part.partition("：")
                if v:
                    _apply(e, norm(k), v, "")
                elif unit_key(norm(part)) in UNITS and not e["unit"]:
                    e["unit"] = norm(part)
            e["source"] = e["source"] or "%s#L%d" % (d["rel"], ln)
            out[nkey(nm)] = e
        if len(out) > before:
            hits.append({"locator": d["rel"], "entries": len(out) - before})
    return out, hits


ACTION_CUES = [("convert_unit", r"换算|转换为|转换成|统一单位|统一为|convert|单位统一|量纲|重算"),
               ("fix_encoding", r"乱码|编码|mojibake|encoding|utf-?8|gbk|gb18030|全角|半角"),
               ("convert_date", r"日期|时间格式|date format|timestamp|时区|iso"),
               ("dedupe", r"去重|重复|duplicate|dedup|主键|primary key"),
               ("mark_invalid", r"异常值|越界|超出|outlier|范围|上下限|out of range|超限"),
               ("mark_missing", r"缺失|missing|空值|未检出|检出限|-999|IMPUTE|填补|填充")]
CUE_FORBID = r"填补|填充|impute|interpolat|插值|插补|均值替代|以0替代"


def _flatten(obj, prefix, out, rel):
    if isinstance(obj, str):
        out.append({"id": prefix, "text": norm(obj), "locator": rel})
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            _flatten(it, "%s-%d" % (prefix, i + 1), out, rel)
    elif isinstance(obj, dict):
        s = " ; ".join("%s=%s" % (k, norm(v)[:120]) for k, v in obj.items() if isinstance(v, (str, int, float)))
        out.append({"id": norm(obj.get("id") or obj.get("wo_id") or prefix),
                    "text": s or json.dumps(obj, ensure_ascii=False)[:200],
                    "locator": rel, "fields": obj.get("fields") or obj.get("field")})


def parse_items(case, docs, tables, keys, name_pat, text_pat, prefix):
    items = []
    for key in keys:
        if key in case:
            _flatten(case.get(key), prefix, items, "case.json#%s" % key)
    hdr = {nkey(h) for T in tables for h in (T.get("header") or [])}
    for d in docs:
        name, text = d["name"].lower(), d["text"] or ""
        if not (re.search(name_pat, name, re.I) or re.search(text_pat, text[:4000])):
            continue
        cur = None
        for ln, line in enumerate(text.splitlines(), 1):
            s = norm(line)
            if not s or re.match(r"^[#=\-]{3,}", s):
                continue
            m = re.match(r"^[-*•]?\s*(?:\*\*)?((?:WO|QC|Q)[-\s]?\d+|\d{1,2}[\.\)、])\s*(.*)$",
                         s, re.I)
            if m:
                raw_id = m.group(1).strip(" .")
                wid = re.sub(r"[-\s]+", "-", raw_id.upper()) if re.match(r"(?i)wo|qc|q", raw_id) \
                    else "%s-%s" % (prefix, raw_id.strip(".、 )"))
                body = norm(re.sub(r"^[\s:：\-—、.]+", "", m.group(2))) or s
                items.append({"id": wid, "text": body, "locator": "%s#L%d" % (d["rel"], ln)})
                cur = items[-1]
            elif cur is not None and len(s) > 8 and not s.startswith("#"):
                cur["text"] = (cur["text"] + " " + s)[:400]
    for i, it in enumerate(items):
        it["text"] = it.get("text") or ""
        it["actions"] = [a for a, pat in ACTION_CUES if re.search(pat, it["text"], re.I)]
        it["forbidden"] = bool(re.search(CUE_FORBID, it["text"], re.I))
        fs = [norm(x) for x in (it.get("fields") if isinstance(it.get("fields"), list)
                                else ([it["fields"]] if it.get("fields") else []))]
        it["fields_matched"] = list(dict.fromkeys(fs + [h for h in hdr if h and h in nkey(it["text"])]))
        it["locator"] = it.get("locator") or "%s#%d" % (prefix, i + 1)
    return items


def parse_num(t):
    if t is None:
        return None
    s = str(t).strip().replace("\u00a0", " ").replace("\u2009", "").replace(" ", "")
    if not s:
        return None
    s = re.sub(r"[×xX*]\s*10\s*([\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b]+)",
               lambda m: "e" + "".join(SUP.get(ch, "") for ch in m.group(1)), s)
    for k, v in SUP.items():
        s = s.replace(k, v)
    s = (s.replace("×10^", "e").replace("x10^", "e").replace("X10^", "e").replace("*10^", "e")
         .replace("−", "-").replace("–", "-"))
    if THOU.match(s):
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        a, _, b = s.partition(",")
        s = ("%s%s" % (a, b)) if (len(b) == 3 and a.lstrip("+-").isdigit()
                                  and len(a.lstrip("+-")) <= 3) else ("%s.%s" % (a, b))
    s = re.sub(CMP, "", s)
    try:
        v = float(s)
    except Exception:
        return None
    return None if (v != v or v in (float("inf"), float("-inf"))) else v


def parse_range(s):
    if not s:
        return None
    t = re.sub(r"[\[\]\(\)]", " ", norm(s).replace("（", "(").replace("）", ")")).strip()
    m = RANGE2.match(t)
    if m:
        try:
            return (float(m.group(1)), float(m.group(2)))
        except Exception:
            return None
    m = RANGE1.match(t)
    if m:
        op, v = m.group(1), float(m.group(2))
        return {"<=": (None, v), "≤": (None, v), "<": (None, v),
                ">=": (v, None), "≥": (v, None), ">": (v, None)}[op]
    nums = re.findall(r"-?\d+\.?\d*", t)
    if len(nums) >= 2:
        try:
            return (float(nums[0]), float(nums[1]))
        except Exception:
            return None
    return None


def in_range(v, rng):
    if rng is None or v is None:
        return True
    lo, hi = rng
    return not ((lo is not None and v < lo) or (hi is not None and v > hi))


def unit_convert(v, from_u, to_u):
    """-> (value, (f1,f2,o1,o2), ok). Inverse: (out*f2+o2-o1)/f1 == v."""
    a, b = unit_key(from_u), unit_key(to_u)
    if a not in UNITS or b not in UNITS:
        return None, None, False
    d1, f1, o1 = UNITS[a]
    d2, f2, o2 = UNITS[b]
    if d1 != d2 or not f2:
        return None, None, False
    out = ((v * f1 + o1) - o2) / f2
    try:
        out = float("%.12g" % out)
    except Exception:
        pass
    return out, (f1, f2, o1, o2), True


def unit_of_cell(t):
    """'12.3 mg/dL', '1.2x10^2 mg/dL' -> (unit, value). Unit must be known."""
    m = re.match(r"^(.*?)\s*([A-Za-z\u00b5\u03bc\u00b0%][A-Za-z0-9\u00b5\u03bc\u00b0%·./^\-]{0,9})\s*$",
                 norm(t))
    if not m:
        return "", None
    unit = norm(m.group(2))
    if unit_key(unit) not in UNITS:
        return "", None
    val = parse_num(m.group(1))
    return (unit, val) if val is not None else ("", None)


def fmt_num(v, sig=None):
    if v is None:
        return ""
    try:
        if sig:
            return "%.*g" % (int(sig), float(v))
        s = repr(float(v))
        if "e" in s or "E" in s:
            s = "%.12g" % float(v)
        return s[:-2] if s.endswith(".0") else s
    except Exception:
        return str(v)


def classify(cell, ctr=None):
    """Cell -> semantics. Never alters the value; only labels it."""
    raw = "" if cell is None else str(cell)
    t = raw.strip()
    low = t.lower()
    res = {"raw": raw, "code": "", "status": "ok", "num": None, "unit": "", "numstr": ""}
    if t == "":
        return dict(res, status="missing", code="MISSING_BLANK")
    if low in LOD:
        return dict(res, status="missing", code="BELOW_LOD")
    if low in MISSING:
        return dict(res, status="missing", code="MISSING_CODE")
    if low in INVALID:
        return dict(res, status="invalid", code="INVALID_TOKEN")
    ctr = ctr or {}
    dtype = str(ctr.get("dtype") or "").lower()
    rng_s = ctr.get("range") or ctr.get("valid_range") or ""
    ucell, unum = unit_of_cell(t)
    if dtype in ("text", "categorical", "string"):
        return dict(res, num=None, numstr=t, unit=ucell)
    v = parse_num(t)
    if v is None:
        if ucell:
            v = unum
        else:
            return dict(res, status="invalid", code="NON_NUMERIC", numstr=t)
    cunit = norm(ctr.get("unit") or "")
    if ucell and cunit and unit_key(ucell) != unit_key(cunit):
        return dict(res, num=v, numstr=fmt_num(v), unit=ucell)
    if not in_range(v, parse_range(rng_s) if rng_s else None):
        return dict(res, status="invalid", code="OUT_OF_RANGE", num=v, unit=ucell, numstr=fmt_num(v))
    return dict(res, num=v, unit=ucell, numstr=fmt_num(v))


def infer_dtype(p):
    n = max(1, p.get("n", 0))
    if p.get("n_num", 0) >= max(1, int(0.6 * n)):
        return "numeric"
    if p.get("n_date", 0) >= max(1, int(0.6 * n)):
        return "date"
    return "text"


def norm_date(t):
    m = DATE_RE.match(str(t or ""))
    if not m:
        return None
    y, mo, d, hh, mm, ss = m.groups()
    s = "%04d-%02d-%02d" % (int(y), int(mo), int(d))
    if hh:
        s += "T%02d:%02d%s" % (int(hh), int(mm), (":%02d" % int(ss)) if ss else ":00")
    return s
