#!/usr/bin/env python3
"""core.py -- deterministic engine for the literature watch desk (stdlib only).

Discovery -> record extraction -> normalization -> work grouping -> window -> op hints.
It never writes anywhere; main.py owns all I/O. No network access.
"""
import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPS = ("new", "update", "retract", "late_index", "seen", "out_of_window")
RELS = ("high", "medium", "low", "unreviewed")
REC_EXT = (".json", ".jsonl", ".ndjson", ".csv", ".tsv")
TEXT_EXT = (".txt", ".md", ".xml", ".html", ".yaml", ".yml")
FULL_EXT = (".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".zip", ".gz", ".db", ".sqlite")
SKIP_NAMES = ("case.json", "task.md", "readme.md", "skill.md", "resources.yaml")

STATE_PAT = re.compile(r"prev|snapshot|import.?state|watermark|last.?sync|last.?seen|seen|"
                       r"cursor|baseline|manifest|state|checkpoint|ledger", re.I)
RETRACT_PAT = re.compile(r"retract|withdraw|correct|erratum|corrigend|expression.?of.?concern", re.I)
VERSION_PAT = re.compile(r"version|revision|update.?hist|history", re.I)

# ---------------------------------------------------------------- field aliases
TITLE = {"title", "titles", "articletitle", "primarytitle", "name", "heading", "displayname", "fulltitle"}
DOI = {"doi", "dois", "digitalobjectidentifier"}
ARX = {"arxiv", "arxivid", "eprint", "arxivid", "eprintid", "primaryarxiv", "arxividentifier"}
IDK = {"id", "identifier", "pmid", "pmcid", "pubmedid", "recordid", "uid", "objid"}
VENUE = {"journaltitle", "journal", "containertitle", "venue", "source", "publication",
         "journalname", "booktitle", "hostname", "srctitle"}
VENUE_ORDER = ("journaltitle", "containertitle", "journalname", "srctitle", "journal", "booktitle",
               "publication", "venue", "hostname", "source")
AUTH = {"author", "authors", "authorstring", "authorname", "creator", "contributors", "authlist"}
PUB = ("publishedonline", "publishedprint", "published", "issued", "firstpublicationdate", "pubdate",
       "publicationdate", "printdate", "onlinefirstdate", "dateofpublication", "epubdate", "year", "releasedate")
IDX = ("created", "firstindexdate", "indexed", "importedat", "insertdate", "addeddate", "modified",
       "updated", "revisiondate", "lastupdated", "timestamp", "date", "datetime")
ABS = {"abstract", "summary", "description", "abstracttext", "snippet"}
TYPE = {"type", "publicationtype", "pubtype", "articletype", "category", "typeofwork", "recordtype"}
VER = {"version", "versionnumber", "edition", "revision", "updateversion"}
UPD = {"updateto", "updatedby", "isretractedby", "retractiondoi", "correctionsof", "relation", "relations"}

RETRACT_TYPES = ("retraction", "retracted", "withdrawal", "withdrawn", "expression of concern",
                 "retraction of", "removal")
CORRECT_TYPES = ("correction", "erratum", "corrigendum", "addendum", "editorial expression")

TZ_FALLBACK = {"utc": 0, "gmt": 0, "asia/shanghai": 8, "asia/tokyo": 9, "asia/seoul": 9,
               "asia/beijing": 8, "asia/kolkata": 5.5, "asia/singapore": 8,
               "europe/london": 0, "europe/paris": 1, "europe/berlin": 1, "europe/amsterdam": 1,
               "america/new_york": -5, "us/eastern": -5, "america/los_angeles": -8, "us/pacific": -8,
               "australia/sydney": 10}
MON = {m: i + 1 for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split())}


# ---------------------------------------------------------------- primitives
def as_str(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(x for x in (as_str(i) for i in v) if x)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)[:400]
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def norm(s, squash=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"), ("\u00a0", " "),
                 ("\u200b", ""), ("\u00ad", "")):
        s = s.replace(a, b)
    s = re.sub(r"<[^>]{1,120}>", " ", s)
    return re.sub(r"\s+", "" if squash else " ", s).strip()


def title_fp(t):
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff\u0370-\u03ff]+", "", norm(t).lower())
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12] if len(s) >= 8 else ""


def norm_doi(d):
    s = norm(d).lower()
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    s = re.sub(r"[\s.,;)\]]+$", "", s)
    return s if re.match(r"^10\.\d{4,9}/\S+$", s) else ""


def arxiv_of(*vals):
    for v in vals:
        s = norm(as_str(v)).lower()
        if not s:
            continue
        m = re.search(r"(?:arxiv[:./\s]*|10\.48550/arxiv\.)(\d{4}\.\d{4,5}|\d{7})(v\d+)?", s)
        if m:
            return m.group(1), (m.group(2) or "").lstrip("v")
    return "", ""


def version_num(v):
    m = re.search(r"(\d+)", as_str(v))
    return int(m.group(1)) if m else 0


def tz_offset(name):
    k = (name or "utc").strip().lower()
    if k in TZ_FALLBACK:
        return timedelta(hours=TZ_FALLBACK[k])
    try:
        from zoneinfo import ZoneInfo
        off = datetime.now(ZoneInfo(name)).utcoffset()
        return off if off is not None else timedelta(0)
    except Exception:
        return timedelta(0)


def parse_date(raw, off=None, dparts=None):
    """-> (iso date string, precision day|month|year|'') kept at source precision."""
    off = off or timedelta(0)
    s = norm(as_str(raw)).strip()
    if dparts:
        parts = [int(x) for x in dparts if str(x).strip().lstrip("-").isdigit()]
        if len(parts) >= 3:
            s = "%04d-%02d-%02d" % (parts[0], parts[1], parts[2])
        elif len(parts) == 2:
            s = "%04d-%02d" % (parts[0], parts[1])
        elif len(parts) == 1:
            s = "%04d" % parts[0]
    if not s:
        return "", ""
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?"
                 r"(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?)?$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return "", ""
        if m.group(4) is not None and m.group(7):
            try:
                iso = "%04d-%02d-%02dT%02d:%02d:%02d" % (y, mo, d, int(m.group(4)),
                                                         int(m.group(5)), int(m.group(6) or 0))
                tzs = m.group(7)
                zone = timezone.utc if tzs == "Z" else timezone(
                    timedelta(hours=int(tzs[1:3]), minutes=int(tzs[-2:])) * (1 if tzs[0] == "+" else -1))
                dt = datetime.fromisoformat(iso).replace(tzinfo=zone).astimezone(timezone(off))
                return dt.date().isoformat(), "day"
            except Exception:
                pass
        return "%04d-%02d-%02d" % (y, mo, d), "day"
    m = re.match(r"^(\d{4})[-/.](\d{1,2})$", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return "%04d-%02d" % (int(m.group(1)), int(m.group(2))), "month"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$", s)
    if m and m.group(2)[:3].lower() in MON:
        return "%04d-%02d-%02d" % (int(m.group(3)), MON[m.group(2)[:3].lower()], int(m.group(1))), "day"
    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", s)
    if m and m.group(1)[:3].lower() in MON:
        return "%04d-%02d-%02d" % (int(m.group(3)), MON[m.group(1)[:3].lower()], int(m.group(2))), "day"
    m = re.match(r"^(\d{4})$", s)
    if m:
        return m.group(1), "year"
    return "", ""


def dkey(iso, fill="01"):
    """Comparable key for a possibly low-precision date."""
    if not iso:
        return ""
    parts = iso.split("-")
    return "-".join(parts + ["01"] * (3 - len(parts)))


def in_window(iso, start, end):
    k = dkey(iso)
    return bool(k) and bool(start) and bool(end) and dkey(start) <= k < dkey(end)


# ---------------------------------------------------------------- json walking
def flat(o, prefix="", out=None, depth=0):
    if out is None:
        out = {}
    if depth > 3:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            kk = str(k).lower()
            flat(v, (prefix + "." if prefix else "") + kk, out, depth + 1)
    elif isinstance(o, list):
        if o and all(not isinstance(x, (dict, list)) for x in o) and len(o) <= 12:
            if prefix and prefix not in out:
                out[prefix] = o
        else:
            for it in o[:8]:
                flat(it, prefix, out, depth + 1)
    elif prefix and prefix not in out:
        out[prefix] = o
    return out


def seg(p):
    return p.rsplit(".", 1)[-1].replace("_", "").replace("-", "").replace(" ", "")


def pick_any(fl, names):
    for p, v in fl.items():
        if seg(p) in names:
            s = as_str(v)
            if s:
                return s, p
    return "", ""


def pick_seq(fl, order):
    for n in order:
        for p, v in fl.items():
            if seg(p) == n:
                s = as_str(v)
                if s:
                    return s, p
    return "", ""


def walk_lists(o, path="", depth=0, out=None):
    """Yield (path, list) for every list of dicts that could be a record set."""
    if out is None:
        out = []
    if depth > 4:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            walk_lists(v, (path + "." if path else "") + str(k), depth + 1, out)
    elif isinstance(o, list):
        dicts = [x for x in o if isinstance(x, dict)]
        if len(dicts) >= 1 and len(dicts) >= max(1, len(o) // 2):
            out.append((path or "$", o))
        for i, v in enumerate(o[:6]):
            if isinstance(v, (dict, list)):
                walk_lists(v, "%s[%d]" % (path, i), depth + 1, out)
    return out


# ---------------------------------------------------------------- record parsing
def looks_bib(d):
    if not isinstance(d, dict):
        return False
    fl = flat(d)
    t, _ = pick_any(fl, TITLE)
    if len(t) < 6:
        return False
    has_id = bool(pick_any(fl, DOI)[0] or pick_any(fl, ARX)[0] or pick_any(fl, IDK)[0])
    has_date = bool(pick_any(fl, set(IDX) | set(PUB))[0])
    return has_id or has_date


def record_of(d, sid, idx):
    fl = flat(d)
    title, tloc = pick_any(fl, TITLE)
    doi, dloc = pick_any(fl, DOI)
    pub, ploc = pick_seq(fl, PUB)
    idxd, iloc = pick_any(fl, IDX)
    venue, vloc = pick_seq(fl, VENUE_ORDER)
    auth, _ = pick_any(fl, AUTH)
    abs_, aloc = pick_any(fl, ABS)
    typ, _ = pick_any(fl, TYPE)
    ver, _ = pick_any(fl, VER)
    upd, _ = pick_any(fl, UPD)
    dp = next((v for p, v in fl.items() if "dateparts" in seg(p) and isinstance(v, list)), None)
    a_id = next((as_str(v) for p, v in fl.items() if seg(p) in ARX and v), "")
    arx, aver = arxiv_of(doi, a_id, as_str(flat(d).get("url", "")))
    d_doi = norm_doi(doi)
    text = " | ".join(x for x in (as_str(v)[:300] for v in fl.values()) if x)[:4000]
    return {
        "locator": "%s#r%d" % (sid, idx),
        "source_id": sid,
        "rid": "%s#r%d" % (sid, idx),
        "title": title,
        "title_loc": "%s#r%d.%s" % (sid, idx, seg(tloc) if tloc else "title"),
        "doi": d_doi,
        "arxiv": arx,
        "arxiv_version": aver or version_num(ver),
        "venue": venue,
        "authors": auth,
        "published": parse_date(pub, None, dp)[0],
        "published_prec": parse_date(pub, None, dp)[1],
        "indexed": parse_date(idxd, None, None)[0],
        "indexed_prec": parse_date(idxd, None, None)[1],
        "abstract": abs_[:1200],
        "type": typ.lower(),
        "version": ver,
        "update_to": upd,
        "title_fp": title_fp(title),
        "text": text,
        "fields": {k: seg(k) for k in (ploc, iloc, dloc) if k},
    }


def records_from_obj(obj, sid):
    recs, seen_loc = [], set()
    cands = []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        cands.append(("$", obj))
    cands += walk_lists(obj)
    best = []
    for path, lst in cands:
        dicts = [x for x in lst if isinstance(x, dict) and looks_bib(x)]
        if len(dicts) > len(best):
            best = dicts
    if not best and isinstance(obj, dict) and looks_bib(obj):
        best = [obj]
    for i, d in enumerate(best, 1):
        r = record_of(d, sid, i)
        if r["locator"] in seen_loc:
            continue
        seen_loc.add(r["locator"])
        recs.append(r)
    return recs


def read_jsonl(p):
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def read_csv(p):
    try:
        txt = p.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []
    sample = txt[:4000]
    delim = max((",", ";", "\t"), key=lambda d: sample.count(d))
    try:
        rows = list(csv.DictReader(txt.splitlines(), delimiter=delim))
    except Exception:
        return []
    out = []
    for r in rows:
        d = {str(k).strip().lower(): v for k, v in r.items() if k}
        if looks_bib(d):
            out.append(d)
    return out


def sniff(p):
    try:
        head = p.read_bytes()[:8]
    except Exception:
        return "unreadable"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        return "zip_container"
    return "text"


def collect_ids(obj, into, dates):
    """Harvest identifier strings + watermark-like dates from a state document."""
    fl = flat(obj)
    for p, v in fl.items():
        k = seg(p)
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            txt = as_str(x)
            if not txt:
                continue
            for m in re.finditer(r"10\.\d{4,9}/[^\s\"'<>,;)\]]+", txt):
                d = norm_doi(m.group(0))
                if d:
                    into.add("doi:" + d)
            for m in re.finditer(r"arxiv[:./\s]*(\d{4}\.\d{4,5}|\d{7})", txt, re.I):
                into.add("arxiv:" + m.group(1))
            if k in TITLE and len(txt) >= 8:
                fp = title_fp(txt)
                if fp:
                    into.add("title:" + fp)
        if re.search(r"watermark|lastsync|lastseen|since|cutoff|asof|windowstart|windowend|"
                     r"^from$|^start$|^end$|^until$|^to$", k):
            for m in re.finditer(r"\d{4}-\d{2}-\d{2}", as_str(v)):
                dates.append((m.group(0), p))
    return into, dates


# ---------------------------------------------------------------- grouping
def group_works(records, seen, retr_keys):
    n = len(records)
    par = list(range(n))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra

    slot = {}
    for i, r in enumerate(records):
        for k in [("doi", r["doi"]), ("arxiv", r["arxiv"]), ("title", r["title_fp"])]:
            if not k[1]:
                continue
            key = k[0] + ":" + k[1]
            if key in slot:
                union(slot[key], i)
            else:
                slot[key] = i
    buckets = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(records[i])

    works = []
    for members in buckets.values():
        def sort_key(r):
            vor = 1 if re.match(r"^10\.\d{4,9}/", r["doi"] or "") and not (r["doi"] or "").startswith("10.48550/") else 0
            return (version_num(r["version"]) + (r["arxiv_version"] or 0), dkey(r["published"]) or dkey(r["indexed"]), vor)
        members = sorted(members, key=sort_key)
        rep = members[-1]
        keys = set()
        for r in members:
            if r["doi"]:
                keys.add("doi:" + r["doi"])
            if r["arxiv"]:
                keys.add("arxiv:" + r["arxiv"])
            if r["title_fp"]:
                keys.add("title:" + r["title_fp"])
        wk = ("doi:" + rep["doi"]) if rep["doi"] else (
            ("arxiv:" + rep["arxiv"]) if rep["arxiv"] else ("title:" + (rep["title_fp"] or "unknown")))
        notice = next((r for r in members if any(t in (r["type"] or "") for t in RETRACT_TYPES)
                       or re.match(r"^\s*(retraction|retracted|withdrawal)", norm(r["title"]).lower())), None)
        correction = next((r for r in members if any(t in (r["type"] or "") for t in CORRECT_TYPES)), None)
        chain = [dict(locator=r["locator"], source_id=r["source_id"], doi=r["doi"], arxiv=r["arxiv"],
                      venue=r["venue"], published=r["published"], published_prec=r["published_prec"],
                      version=r["version"], type=r["type"]) for r in members]
        venue_set = {norm(m["venue"]).lower() for m in members if m["venue"]}
        vor_doi = {m["doi"] for m in members if m["doi"] and not m["doi"].startswith("10.48550/")}
        preprint_doi = {m["doi"] for m in members if (m["doi"] or "").startswith("10.48550/")}
        changed = []
        if len(vor_doi) >= 1 and preprint_doi:
            changed.append("preprint_to_version_of_record")
        if len(venue_set) > 1:
            changed.append("venue_changed")
        if len({version_num(m["version"]) for m in members}) > 1:
            changed.append("version_bumped")
        if correction:
            changed.append("correction_notice")
        pubs = sorted({m["published"] for m in members if m["published"]})
        idxs = sorted({m["indexed"] for m in members if m["indexed"]})
        works.append({
            "work_key": wk, "keys": sorted(keys), "n_records": len(members),
            "published_first": pubs[0] if pubs else "",
            "indexed_max": idxs[-1] if idxs else "",
            "indexed_sources": len(idxs),
            "members": members, "rep": rep, "chain": chain,
            "title": rep["title"], "doi": rep["doi"], "arxiv": rep["arxiv"],
            "venue": rep["venue"], "published": rep["published"], "published_prec": rep["published_prec"],
            "indexed": rep["indexed"], "version": rep["version"], "type": rep["type"],
            "duplicates": [dict(locator=m["locator"], source_id=m["source_id"], doi=m["doi"],
                                title=m["title"][:160], venue=m["venue"], published=m["published"])
                           for m in members[:-1]],
            "version_chain": chain if len(chain) > 1 else [],
            "change_signals": changed,
            "notice_locator": notice["locator"] if notice else "",
            "in_seen": bool(keys & seen) or wk in seen,
            "retracted": bool(keys & retr_keys) or bool(notice),
        })
    works.sort(key=lambda w: (dkey(w["published"]) or dkey(w["indexed"]) or "0000", w["work_key"]))
    return works


def classify(w, win):
    """Mechanical op hint + reasons. The Agent reviews and may override."""
    reasons = []
    s, e = win.get("start", ""), win.get("end", "")
    if w["retracted"]:
        reasons.append("retraction/withdrawal notice or target hit"
                       + (" @%s" % w["notice_locator"] if w["notice_locator"] else ""))
        return "retract", reasons
    if w["in_seen"]:
        if w["change_signals"]:
            reasons.append("already seen but changed: " + ",".join(w["change_signals"]))
            return "update", reasons
        reasons.append("identifier already in previous snapshot, no field change")
        return "seen", reasons
    if w["change_signals"]:
        reasons.append("multi-version group: " + ",".join(w["change_signals"]))
        return "update", reasons
    pub, idx = w.get("published_first") or w["published"], w.get("indexed_max") or w["indexed"]
    if pub and in_window(pub, s, e):
        reasons.append("published %s inside [%s,%s)" % (pub, s, e))
        return "new", reasons
    if pub and s and dkey(pub) < dkey(s):
        if idx and in_window(idx, s, e):
            reasons.append("published %s before window but indexed %s inside window" % (pub, idx))
            return "late_index", reasons
        reasons.append("published %s before window start" % pub)
        return "out_of_window", reasons
    if not pub and idx and in_window(idx, s, e):
        reasons.append("no published date; indexed %s inside window" % idx)
        return "new", reasons
    if pub and e and dkey(pub) >= dkey(e):
        reasons.append("published %s on/after window end" % pub)
        return "out_of_window", reasons
    reasons.append("no usable date inside window")
    return "out_of_window", reasons
