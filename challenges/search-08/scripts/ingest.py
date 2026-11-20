#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest.py -- parsing layer for systematic-screening-ledger.

IO helpers, semantic field lookup, bibliographic record parsing (json/jsonl/csv/text),
criteria parsing with version tracking, duplicate pre-clustering, anomaly flags.
Imported by main.py and screen.py; also runnable as a parser smoke check:
    python3 ingest.py /input
Standard library only; never raises to the caller at module import time.
"""
import csv, difflib, hashlib, io, json, re
from pathlib import Path

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "references"
TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".text"}


def _res(name, default):
    try:
        return json.loads((RES / name).read_text(encoding="utf-8"))
    except Exception:
        return default


RC = _res("reason_codes.json", {})
SYN = RC.get("field_synonyms") or {}
CODES = RC.get("codes") or {}
LABELS = RC.get("labels") or ["include", "exclude", "pending"]
ALIAS = RC.get("label_aliases") or {}
CONFLICT_TYPES = RC.get("conflict_types") or {}


# --------------------------------------------------------------------------- io
def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def write_text(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(str(s), encoding="utf-8")


def write_json(p, o):
    write_text(p, json.dumps(o, ensure_ascii=False, indent=2))


def load_json(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def norm(s):
    return re.sub(r"\s+", " ", str("" if s is None else s)).strip()


def clean(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(clean(x) for x in v if x is not None)
    if isinstance(v, dict):
        return norm(json.dumps(v, ensure_ascii=False))[:400]
    return norm(v)


def norm_doi(v):
    s = clean(v).lower()
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi\s*[:：]\s*", "", s)
    return s.strip(" .;,<>()[]")


def norm_title(t):
    s = clean(t).lower()
    s = re.sub(r"<[^>]{0,40}>", " ", s)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", s)


def norm_label(v):
    s = clean(v).lower()
    for lab, als in ALIAS.items():
        if s in [str(a).lower() for a in als]:
            return lab
    return ""


def grams(s, n=3):
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def sha1(s):
    return hashlib.sha1(str(s).encode("utf-8")).hexdigest()[:12]


def lang_of(t):
    t = str(t or "")
    zh, en = len(re.findall(r"[\u4e00-\u9fff]", t)), len(re.findall(r"[A-Za-z]", t))
    return "zh" if zh and zh * 2 >= en else "en"


def pick(d, field):
    """Semantic key lookup: exact synonym first, then containment for long synonyms."""
    keys = [str(k).lower() for k in (SYN.get(field) or [field])]
    low = {str(k).lower(): k for k in d.keys()}
    for k in keys:
        if k in low:
            return d[low[k]]
    for lk, ok in low.items():
        for k in keys:
            if len(k) >= 5 and k in lk:
                return d[ok]
    return None


def walk(root):
    out = []
    try:
        for p in sorted(Path(root).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                out.append(p)
    except Exception:
        pass
    return out[:600]


def relof(p, root):
    try:
        return str(Path(p).relative_to(root))
    except Exception:
        return str(p)


# ------------------------------------------------------------------- records
def _objs(text):
    t = str(text or "").strip()
    if not t:
        return []
    if t[0] in "[{":
        try:
            d = json.loads(t)
        except Exception:
            d = None
        if isinstance(d, list):
            return [x for x in d if isinstance(x, dict)]
        if isinstance(d, dict):
            for k in ("records", "items", "data", "results", "papers", "studies", "entries", "docs"):
                v = d.get(k)
                if isinstance(v, list) and v:
                    return [x for x in v if isinstance(x, dict)]
            return [d]
    out = []
    for ln in t.splitlines():
        ln = ln.strip()
        if not ln or ln[0] not in "[{":
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out[:400]


def mk(rel, line, o, title, abstract):
    return {
        "native_id": clean(pick(o, "id")),
        "title": clean(title),
        "abstract": clean(abstract),
        "doi": norm_doi(pick(o, "doi")),
        "authors": clean(pick(o, "authors")),
        "year": clean(pick(o, "year"))[:12],
        "journal": clean(pick(o, "journal")),
        "study": clean(pick(o, "study")),
        "reviewer": clean(pick(o, "reviewer")),
        "label": clean(pick(o, "label")),
        "reason_code": clean(pick(o, "reason")),
        "criteria_version": clean(pick(o, "version")),
        "source_file": rel,
        "source_line": line,
    }


def parse_structured(p, rel):
    suf = p.suffix.lower()
    rows = []
    if suf == ".csv":
        txt = read_text(p)
        try:
            rows = list(csv.DictReader(io.StringIO(txt)))
        except Exception:
            rows = []
        if len(rows) == 1 and len(rows[0]) == 1:
            try:
                rows = list(csv.DictReader(io.StringIO(txt), delimiter="\t"))
            except Exception:
                rows = []
    elif suf in (".json", ".jsonl", ".ndjson"):
        rows = _objs(read_text(p))
    out = []
    for i, o in enumerate(rows, 1):
        if not isinstance(o, dict):
            continue
        title, ab = clean(pick(o, "title")), clean(pick(o, "abstract"))
        if not title and not ab:
            continue
        out.append(mk(rel, i, o, title, ab))
    return out


def parse_labels(p, rel):
    """Reviewer label files carry no title/abstract: map id -> reviewer/label/reason."""
    suf = p.suffix.lower()
    if suf == ".csv":
        try:
            rows = list(csv.DictReader(io.StringIO(read_text(p))))
        except Exception:
            rows = []
    elif suf in (".json", ".jsonl", ".ndjson"):
        rows = _objs(read_text(p))
    else:
        rows = []
    out = []
    for i, o in enumerate(rows, 1):
        if not isinstance(o, dict):
            continue
        rev, lab = clean(pick(o, "reviewer")), clean(pick(o, "label"))
        if not rev or not lab:
            continue
        out.append({"native_id": clean(pick(o, "id")), "title": clean(pick(o, "title")),
                    "abstract": "", "doi": "", "authors": "", "year": "", "journal": "",
                    "study": clean(pick(o, "study")), "reviewer": rev, "label": lab,
                    "reason_code": clean(pick(o, "reason")),
                    "criteria_version": clean(pick(o, "version")),
                    "source_file": rel, "source_line": i})
    return out


def records_from_text(p, rel):
    t = read_text(p)
    if len(t) < 80:
        return []
    recs = []
    for i, b in enumerate([x.strip() for x in re.split(r"\n\s*\n", t) if x.strip()], 1):
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        head = re.sub(r"^(#{1,6}\s*|[-*\u2022]\s*|\d{1,3}[.)]\s*)", "", lines[0]).strip()
        if len(head) < 15 or len(head) > 400:
            continue
        recs.append(mk(rel, i, {}, head, norm(" ".join(lines[1:]))))
    return recs if len(recs) >= 2 else []


# ------------------------------------------------------------------ criteria
KIND_CUE = [("include", r"纳入|inclusion|include|eligib|\u5165\u9009"),
            ("exclude", r"排除|exclusion|exclude|\u4e0d\u7eb3\u5165")]
CRIT_LINE = re.compile(r"^\s*(?:[-*\u2022]\s*)?\(?([IEie])?\s*(\d{1,2})\s*[.):：、)）]\s*(.{4,})$")


def parse_criteria_text(p, rel):
    out, kind, ver = [], None, None
    for i, ln in enumerate(read_text(p).splitlines(), 1):
        s = ln.strip()
        if not s:
            continue
        head = re.sub(r"^#{1,6}\s*", "", s)
        m = (re.search(r"\bv(\d+(?:\.\d+)?)\b", head, re.I)
             or re.search(r"版本\s*(\d+(?:\.\d+)?)", head)
             or re.search(r"version\s*[:：]?\s*(?:v)?(\d+(?:\.\d+)?)", head, re.I))
        if m:
            ver = "v" + m.group(1)
        hit = [k for k, pat in KIND_CUE if re.search(pat, head, re.I)]
        if hit and len(head) < 90:
            kind = hit[0]
            continue
        mm = CRIT_LINE.match(s)
        if mm and len(mm.group(3)) >= 6:
            letter = (mm.group(1) or ("I" if kind == "include" else "E" if kind == "exclude" else "C")).upper()
            out.append({"id": "%s%s" % (letter, mm.group(2)),
                        "kind": kind or ("include" if letter == "I" else "exclude" if letter == "E" else "other"),
                        "text": norm(mm.group(3)), "version": ver or "v1",
                        "source": rel, "line": i})
    return out


def parse_criteria_case(case):
    out = []
    if not isinstance(case, dict):
        return out
    cver = clean(case.get("criteria_version")) or "v1"
    for key, kind in (("inclusion_criteria", "include"), ("exclusion_criteria", "exclude"),
                      ("criteria", None), ("eligibility_criteria", None)):
        v = case.get(key)
        if isinstance(v, dict):
            v = v.get("items") or v.get("list") or []
        if not isinstance(v, list):
            continue
        for i, it in enumerate(v, 1):
            if isinstance(it, str) and len(it.strip()) > 5:
                kk = kind or "other"
                letter = "I" if kk == "include" else "E" if kk == "exclude" else "C"
                out.append({"id": "%s%d" % (letter, i), "kind": kk, "text": norm(it),
                            "version": cver, "source": "case.json", "line": i})
            elif isinstance(it, dict):
                kk = clean(it.get("kind") or it.get("type") or it.get("group") or kind or "other").lower()
                kk = "exclude" if ("excl" in kk or "排除" in kk) else "include" if ("incl" in kk or "纳入" in kk) else "other"
                out.append({"id": (clean(it.get("id") or it.get("criterion_id")).upper() or "C%02d" % i),
                            "kind": kk,
                            "text": norm(it.get("text") or it.get("criterion") or it.get("description") or ""),
                            "version": clean(it.get("version")) or cver, "source": "case.json", "line": i})
    return [x for x in out if x["text"]]


# --------------------------------------------------------------------- dedup
def cluster_groups(records):
    n = len(records)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    keys = {}
    for i, r in enumerate(records):
        if r["doi"]:
            keys.setdefault("doi:" + r["doi"], []).append(i)
        nt = norm_title(r["title"])
        if len(nt) >= 18:
            keys.setdefault("tt:" + nt, []).append(i)
    for ids in keys.values():
        for j in ids[1:]:
            uni(ids[0], j)
    cand = [i for i, r in enumerate(records) if len(norm_title(r["title"])) >= 24]
    gr = {i: grams(norm_title(records[i]["title"])) for i in cand}
    for x in range(len(cand)):
        for y in range(x + 1, len(cand)):
            i, j = cand[x], cand[y]
            if find(i) == find(j):
                continue
            a, b = gr[i], gr[j]
            if not a or not b or len(a & b) / float(min(len(a), len(b))) < 0.8:
                continue
            if difflib.SequenceMatcher(None, norm_title(records[i]["title"]),
                                       norm_title(records[j]["title"])).ratio() >= 0.88:
                uni(i, j)
    buckets = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)
    return [v for v in buckets.values() if len(v) > 1]


def flags_of(r):
    f = []
    if not r["doi"]:
        f.append("no_doi")
    if len(r["abstract"]) < 40:
        f.append("no_abstract")
    if re.search(r"[\u00c2\u00c3\u00e2\ufffd]", r["title"] + r["abstract"]):
        f.append("mojibake")
    if len(norm_title(r["title"])) < 15:
        f.append("short_title")
    return f


def extract_query(files, inp, limit=8):
    qs = []
    for f in files:
        for ln in read_text(Path(inp) / f).splitlines():
            s = ln.strip(" -*\t")
            if 20 <= len(s) <= 400 and re.search(r"\bAND\b|\bOR\b|\bTI=|\[tiab\]|检索式|search string|\"", s):
                qs.append({"raw": s, "source": f})
            if len(qs) >= limit:
                return qs
    return qs


def research_question(case, task):
    for k in ("research_question", "question", "objective", "pico", "title"):
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and len(v.strip()) > 8:
            return norm(v)[:500]
    for ln in str(task or "").splitlines():
        if re.search(r"研究问题|research question|PICO|question is|待答问题", ln) and len(ln.strip()) > 12:
            return norm(ln)[:500]
    return ""


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "/input"
    n = 0
    for p in walk(root):
        if p.suffix.lower() in (".json", ".jsonl", ".ndjson", ".csv"):
            rs = parse_structured(p, relof(p, root))
            n += len(rs)
            print("%s -> %d records" % (relof(p, root), len(rs)))
    print("total records: %d" % n)
