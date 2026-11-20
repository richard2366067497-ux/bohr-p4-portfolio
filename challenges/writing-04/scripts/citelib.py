#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citelib.py -- parsing, de-duplication and citation matching for reference
management (writing-04, v7). Standard library only; deterministic; offline.

This module turns real input into a flat record model and derives evidence:

  * parse_bib / parse_ris / parse_json_lib / parse_csv_lib / parse_manuscript_refs
        -> list[record]  (every field is a str/list; never None)
  * pair_decision(a, b)   -> (verdict, confidence, reason, conflicts)  (per pair)
  * cluster(records)      -> (canonical_groups, merge_rows, review_rows)
  * find_markers(text)    -> citation markers with character locators
  * resolve_markers(...)  -> per-occurrence key/number resolution
  * claim_support(...)    -> per "claim sentence <-> reference" evidence rows

A record is a dict with the fixed keys in ``RECORD_FIELDS``. Unknown fields are
empty strings, never ``None`` (so no artifact ever carries a JSON null token).
"""
from __future__ import annotations

import csv
import io
import json
import re

RECORD_FIELDS = ["key", "entry_type", "title", "authors", "year", "container",
                 "publisher", "volume", "issue", "pages", "doi", "url", "isbn",
                 "eprint", "raw", "source_format", "issues"]

TYPE_MAP = {
    "article": "J", "journal": "J", "inproceedings": "C", "conference": "C",
    "proceedings": "C", "book": "M", "inbook": "M", "incollection": "M",
    "phdthesis": "D", "mastersthesis": "D", "thesis": "D", "techreport": "R",
    "report": "R", "misc": "Z", "online": "EB", "webpage": "EB", "patent": "P",
    "standard": "S", "newspaper": "N", "dataset": "DS",
}
# BibTeX entry types that should not be used as a GB/T 文献类型标识 directly
STOP_TITLE_TOKENS = {"the", "a", "an", "of", "on", "in", "and", "for", "to",
                     "with", "using", "via", "from", "by", "at", "as", "is"}


def read_text(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8-sig", "replace")
    except OSError:
        return ""


def empty_record(source_format: str = "", raw: str = "") -> dict:
    rec = {f: "" for f in RECORD_FIELDS}
    rec["authors"] = []
    rec["issues"] = []
    rec["source_format"] = source_format
    rec["raw"] = raw
    rec["key"] = ""
    return rec


def clean(obj):
    """Recursively replace None/NaN with '' so no artifact carries a bare null."""
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return ""
    return obj


# --------------------------------------------------------------------------- #
# normalisation helpers
# --------------------------------------------------------------------------- #
def norm_doi(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    return s.strip().rstrip(".")


def norm_title(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\\[a-z]+", " ", s)          # strip latex macros
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_tokens(s: str):
    return [t for t in norm_title(s).split() if t and t not in STOP_TITLE_TOKENS]


def join_similarity(a: str, b: str) -> float:
    """Jaccard similarity over significant title tokens."""
    ta, tb = set(title_tokens(a)), set(title_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def surname(author: str) -> str:
    a = (author or "").strip()
    if not a:
        return ""
    if "," in a:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", a.split(",")[0].lower())
    parts = re.split(r"\s+", a)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", parts[-1].lower()) if parts else ""


def first_surname(rec: dict) -> str:
    return surname(rec["authors"][0]) if rec.get("authors") else ""


# --------------------------------------------------------------------------- #
# parsers -> records
# --------------------------------------------------------------------------- #
_BIB_SPLIT = re.compile(r"@(\w+)\s*\{\s*([^,]+),", re.S)


def _bib_value(v: str) -> str:
    v = v.strip()
    v = re.sub(r"^[{\"](.*)[}\"]$", r"\1", v, flags=re.S)
    v = re.sub(r"\s+", " ", v)
    return v.replace("{", "").replace("}", "").strip()


def parse_bib(text: str):
    out = []
    for m in _BIB_SPLIT.finditer(text):
        etype, key = m.group(1).lower(), m.group(2).strip()
        start = m.end()
        depth, i = 1, start
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]
        fields = {}
        for fm in re.finditer(r"([A-Za-z][\w-]*)\s*=\s*(\{.*?\}|\"[^\"]*\"|[^,}]+)", body, re.S):
            fields[fm.group(1).lower()] = _bib_value(fm.group(2))
        rec = empty_record("bib", text[m.start():i])
        rec["key"] = key
        rec["entry_type"] = etype
        rec["title"] = fields.get("title", "")
        rec["year"] = re.sub(r"\D", "", fields.get("year", ""))[:4]
        rec["container"] = fields.get("journal") or fields.get("booktitle") or fields.get("publisher", "")
        rec["publisher"] = fields.get("publisher", "")
        rec["volume"] = fields.get("volume", "")
        rec["issue"] = fields.get("number", "") or fields.get("issue", "")
        rec["pages"] = fields.get("pages", "")
        rec["doi"] = norm_doi(fields.get("doi", ""))
        rec["url"] = fields.get("url", "")
        rec["isbn"] = fields.get("isbn", "")
        rec["eprint"] = fields.get("eprint", "")
        auth = fields.get("author", "")
        rec["authors"] = [a.strip() for a in re.split(r"\s+and\s+", auth) if a.strip()] if auth else []
        out.append(rec)
    return out


_RIS_TYPE = {"JOUR": "article", "CONF": "inproceedings", "BOOK": "book",
             "THES": "phdthesis", "RPRT": "techreport", "ELEC": "online"}


def parse_ris(text: str):
    out = []
    cur, raw = {}, []
    def flush():
        if not cur:
            return
        rec = empty_record("ris", "\n".join(raw))
        rec["key"] = (cur.get("ID", "") or cur.get("DO", "") or cur.get("TI", [""])[0])
        rec["entry_type"] = _RIS_TYPE.get(cur.get("TY", ["MISC"])[0], "misc") if cur.get("TY") else "misc"
        rec["title"] = (cur.get("TI", [""])[0] or cur.get("T1", [""])[0])
        rec["authors"] = cur.get("AU", []) or cur.get("A1", [])
        yr = cur.get("PY", [""])[0] or cur.get("Y1", [""])[0]
        rec["year"] = re.sub(r"\D", "", yr)[:4]
        rec["container"] = (cur.get("JO", [""])[0] or cur.get("JF", [""])[0] or cur.get("T2", [""])[0])
        rec["publisher"] = (cur.get("PB", [""])[0])
        rec["volume"] = (cur.get("VL", [""])[0])
        rec["issue"] = (cur.get("IS", [""])[0])
        rec["pages"] = (cur.get("SP", [""])[0] + ("-" + cur["EP"][0] if cur.get("EP") else ""))
        rec["doi"] = norm_doi((cur.get("DO", [""])[0]))
        rec["url"] = (cur.get("UR", [""])[0])
        rec["isbn"] = (cur.get("SN", [""])[0] if rec["entry_type"] == "book" else "")
        out.append(rec)
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if re.match(r"^TY\s+-", line):
            cur = {}; raw = [line]; continue
        if re.match(r"^ER\s+-", line):
            flush(); cur = {}; raw = []; continue
        m = re.match(r"^([A-Z][A-Z0-9])\s+-\s*(.*)$", line)
        if m and cur is not None:
            cur.setdefault(m.group(1), []).append(m.group(2).strip())
            raw.append(line)
    flush()
    return [r for r in out if r["title"] or r["key"]]


_JSON_AUTHOR_KEYS = ("author", "authors")
_JSON_MAP = {
    "title": ("title",), "year": ("year", "published", "date", "issued"),
    "container": ("journal", "container-title", "container_title", "booktitle", "venue", "journal_name"),
    "publisher": ("publisher",), "volume": ("volume",), "issue": ("issue", "number"),
    "pages": ("page", "pages"), "doi": ("DOI", "doi"), "url": ("URL", "url"),
    "isbn": ("ISBN", "isbn", "issn"), "eprint": ("eprint", "arxiv", "arxiv_id"),
    "entry_type": ("type", "entry_type"), "key": ("id", "key", "ID", "citation-key"),
}


def _pick(d: dict, keys):
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return ""


def parse_json_lib(text: str):
    try:
        obj = json.loads(text)
    except Exception:
        return []
    items = obj if isinstance(obj, list) else (
        obj.get("references") or obj.get("items") or obj.get("records") or obj.get("data")
        if isinstance(obj, dict) else None)
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        rec = empty_record("json", json.dumps(it, ensure_ascii=False))
        for field, keys in _JSON_MAP.items():
            rec[field] = _pick(it, keys)
        for ak in _JSON_AUTHOR_KEYS:
            if ak in it and it[ak]:
                raw_a = it[ak]
                if isinstance(raw_a, list):
                    rec["authors"] = [(a.get("family", "") or a.get("name", "")) if isinstance(a, dict) else str(a) for a in raw_a]
                else:
                    rec["authors"] = [a.strip() for a in re.split(r";| and |,", str(raw_a)) if a.strip()]
                break
        rec["doi"] = norm_doi(rec["doi"])
        rec["year"] = re.sub(r"\D", "", str(rec["year"]))[:4]
        rec["entry_type"] = (rec["entry_type"] or "misc")
        if isinstance(rec["pages"], list):
            rec["pages"] = "-".join(str(p) for p in rec["pages"])
        for f in RECORD_FIELDS:
            if not isinstance(rec[f], (str, list)):
                rec[f] = str(rec[f])
        out.append(rec)
    return out


def parse_csv_lib(text: str):
    out = []
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception:
        return []
    low = {}
    for r in rows:
        for k in r:
            low[k.strip().lower()] = k
    def g(r, *names):
        for n in names:
            if n in low:
                return (r.get(low[n]) or "").strip()
        return ""
    for r in rows:
        if not any((v or "").strip() for v in r.values()):
            continue
        rec = empty_record("csv", json.dumps(r, ensure_ascii=False))
        rec["key"] = g(r, "key", "id", "citekey", "citation-key")
        rec["title"] = g(r, "title")
        rec["entry_type"] = g(r, "type", "entry_type") or "misc"
        rec["year"] = re.sub(r"\D", "", g(r, "year"))[:4]
        rec["container"] = g(r, "journal", "container", "container-title", "venue")
        rec["publisher"] = g(r, "publisher")
        rec["volume"] = g(r, "volume")
        rec["issue"] = g(r, "issue", "number")
        rec["pages"] = g(r, "pages", "page")
        rec["doi"] = norm_doi(g(r, "doi"))
        rec["url"] = g(r, "url")
        rec["isbn"] = g(r, "isbn", "issn")
        auth = g(r, "author", "authors")
        rec["authors"] = [a.strip() for a in re.split(r";| and |\|", auth) if a.strip()] if auth else []
        out.append(rec)
    return out


_MAN_REF = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+(.*\S)\s*$")
_GB_TYPE = re.compile(r"\[([JMCNDRSPZ]|EB/OL|DS|CP/DK|DB/OL|EB)\]")
_YEAR = re.compile(r"(1[5-9]\d\d|20\d\d)")
_VOL_ISS = re.compile(r",\s*(\d+)\s*(?:\((\d+)\))?\s*[:：]\s*([0-9A-Za-z\u2013\-]+)")


def parse_manuscript_refs(text: str):
    """Parse an in-manuscript numbered reference list (GB/T style, line 1..n)."""
    out = []
    for m in _MAN_REF.finditer(text):
        num = m.group(1) or m.group(2)
        body = m.group(3).strip()
        rec = empty_record("manuscript", body)
        rec["key"] = "ref" + num
        tm = _GB_TYPE.search(body)
        rec["entry_type"] = {"J": "article", "M": "book", "C": "inproceedings",
                             "D": "phdthesis", "R": "techreport", "S": "standard",
                             "N": "newspaper", "P": "patent", "EB": "online",
                             "EB/OL": "online", "DS": "dataset"}.get(
                                 tm.group(1) if tm else "", "misc")
        head = body[:tm.start()].strip() if tm else body
        parts = [p.strip() for p in re.split(r"[.,]\s+", head) if p.strip()]
        # last comma-part before [type] is usually the title
        rec["authors"] = [a.strip() for a in re.split(r",\s*", parts[0]) if a.strip()] if parts else []
        rec["title"] = parts[-1] if parts else ""
        tail = body[tm.end():] if tm else ""
        ym = _YEAR.search(tail)
        rec["year"] = ym.group(1) if ym else ""
        vm = _VOL_ISS.search(tail)
        if vm:
            rec["volume"], rec["issue"], rec["pages"] = vm.group(1), vm.group(2) or "", vm.group(3)
        rec["container"] = re.split(r",\s*1[5-9]\d\d", tail)[0].lstrip(". ").strip() if tail else ""
        dm = re.search(r"10\.\d{4,9}/\S+", body)
        rec["doi"] = norm_doi(dm.group(0)) if dm else ""
        out.append(rec)
    return out


def parse_any(name: str, text: str):
    """Dispatch by file extension; fall back to content sniffing."""
    low = name.lower()
    if low.endswith(".bib") or text.lstrip().startswith("@"):
        return parse_bib(text)
    if low.endswith(".ris") or re.search(r"^TY\s+-", text, re.M):
        return parse_ris(text)
    if low.endswith(".json") or text.lstrip()[:1] in "[{":
        got = parse_json_lib(text)
        if got:
            return got
    if low.endswith(".csv"):
        return parse_csv_lib(text)
    return []


# --------------------------------------------------------------------------- #
# de-duplication
# --------------------------------------------------------------------------- #
def pair_decision(a: dict, b: dict):
    """Return (verdict, confidence, reason, conflicts) for one ordered pair.

    verdict in {merge, review, distinct}. Evidence is explicit per rule so a
    reviewer can re-derive every decision from the two records alone.
    """
    da, db = norm_doi(a["doi"]), norm_doi(b["doi"])
    ta, tb = norm_title(a["title"]), norm_title(b["title"])
    conflicts = []
    if da and db and da == db:
        if ta and tb and join_similarity(a["title"], b["title"]) < 0.4:
            conflicts = ["same DOI, different title"]
            return "review", 0.90, "identical DOI (%s) but titles disagree" % da, conflicts
        return "merge", 0.99, "identical DOI: %s" % da, conflicts
    ea, eb = (a.get("eprint") or "").strip(), (b.get("eprint") or "").strip()
    if ea and eb and ea == eb:
        return "merge", 0.97, "identical arXiv/eprint id: %s" % ea, conflicts
    if ta and tb and ta == tb:
        sa, sb = first_surname(a), first_surname(b)
        yr_same = a["year"] and a["year"] == b["year"]
        if sa and sb and sa != sb:
            conflicts = ["same title, different first author"]
            return "review", 0.90, "identical title but first authors differ (%s vs %s)" % (sa, sb), conflicts
        if yr_same:
            return "merge", 0.98, "identical normalized title and same year %s" % a["year"], conflicts
        return "merge", 0.95, "identical normalized title and same first author %s" % (sa or "n/a"), conflicts
    j = join_similarity(a["title"], b["title"])
    sa, sb = first_surname(a), first_surname(b)
    if j >= 0.85 and sa and sa == sb and a["year"] and a["year"] == b["year"]:
        return "merge", 0.92, "title token similarity %.2f, same author %s and year %s" % (j, sa, a["year"]), conflicts
    if j >= 0.65:
        return "review", 0.65, "titles share token similarity %.2f (below merge threshold)" % j, conflicts
    return "distinct", 0.0, "no shared key/title evidence", conflicts


def cluster(records):
    """Union-find over merge-confidence pairs; returns
    (groups, merge_rows, review_rows, distinct_pairs)."""
    n = len(records)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        parent[find(x)] = find(y)
    merge_rows, review_rows = [], []
    for i in range(n):
        for k in range(i + 1, n):
            v, c, reason, conflicts = pair_decision(records[i], records[k])
            if v == "merge":
                union(i, k)
                merge_rows.append({"a": records[i]["key"], "b": records[k]["key"],
                                   "a_title": records[i]["title"], "b_title": records[k]["title"],
                                   "verdict": v, "confidence": c, "reasons": reason,
                                   "conflicts": "; ".join(conflicts)})
            elif v == "review":
                review_rows.append({"a": records[i]["key"], "b": records[k]["key"],
                                    "a_title": records[i]["title"], "b_title": records[k]["title"],
                                    "verdict": v, "confidence": c, "reasons": reason,
                                    "conflicts": "; ".join(conflicts)})
    buckets = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)
    groups = []
    for root, idxs in buckets.items():
        best = max(idxs, key=lambda i: sum(1 for f in RECORD_FIELDS[:-2] if records[i][f]))
        canon = dict(records[best])
        merged = [records[i]["key"] for i in idxs if i != best]
        # fill gaps in canonical from the other members
        for i in idxs:
            for f in RECORD_FIELDS[:-2]:
                if not canon[f] and records[i][f]:
                    canon[f] = records[i][f]
        groups.append({"canonical": canon, "members": [records[i]["key"] for i in idxs],
                       "merged": merged, "size": len(idxs)})
    return groups, merge_rows, review_rows


# --------------------------------------------------------------------------- #
# citation markers and matching
# --------------------------------------------------------------------------- #
BRACKET_RE = re.compile(r"\[\s*(\d+(?:\s*[-,\u2013]\s*\d+)*)\s*\]")
LATEX_RE = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?"
                      r"(?:\[[^\]]*\]){0,2}\{([^}]+)\}")
AUTHYEAR_RE = re.compile(r"((?:[A-Z][A-Za-z\-']+\s*(?:et\s+al\.?|&\s*[A-Z][A-Za-z\-']+)?)"
                         r"\s*[,;]\s*)?\(?((?:19|20)\d\d)[a-z]?\)?")


def expand_numbers(spec: str):
    out = []
    for part in re.split(r",", spec):
        part = part.strip()
        rng = re.split(r"[-\u2013]", part)
        if len(rng) == 2 and rng[0].strip().isdigit() and rng[1].strip().isdigit():
            out.extend(range(int(rng[0]), int(rng[1]) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def find_markers(text: str):
    """Return markers with 1-based line:col locators and verbatim quote slice."""
    marks = []
    for m in BRACKET_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        col = m.start() - (text.rfind("\n", 0, m.start()) + 1) + 1
        marks.append({"kind": "number", "raw": m.group(0),
                      "numbers": expand_numbers(m.group(1)),
                      "keys": [], "locator": "L%d:C%d" % (line, col),
                      "quote": _line_of(text, m.start())})
    for m in LATEX_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        col = m.start() - (text.rfind("\n", 0, m.start()) + 1) + 1
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        marks.append({"kind": "latex", "raw": m.group(0), "numbers": [],
                      "keys": keys, "locator": "L%d:C%d" % (line, col),
                      "quote": _line_of(text, m.start())})
    return marks


def _line_of(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return text[start:end].strip()[:300]


def split_sentences(text: str):
    """Sentence segmentation that keeps the char offset of each sentence."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        base = text.find(para)
        for m in re.finditer(r"[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$", para):
            s = m.group(0).strip()
            if len(s) >= 8:
                out.append({"text": s, "offset": base + m.start()})
    return out


def first_citation_order(groups, text):
    """Order canonical groups by first appearance of any member in the text."""
    pos = {}
    for gi, g in enumerate(groups):
        keys = g["members"]
        for k in keys:
            i = text.find(k)
            if i >= 0:
                pos[gi] = min(pos.get(gi, 10 ** 9), i)
    for gi, g in enumerate(groups):
        if gi not in pos:
            num = g["canonical"].get("key", "")
            i = text.find(num)
            pos[gi] = i if i >= 0 else 10 ** 9
    return sorted(range(len(groups)), key=lambda gi: (pos.get(gi, 10 ** 9), gi))


def claim_support(sentences, groups, key_to_number):
    """For each sentence carrying a marker, score its match to each reference."""
    rows = []
    for st in sentences:
        marks = find_markers(st["text"])
        if not marks:
            continue
        nums, keys = [], []
        for mk in marks:
            nums.extend(mk["numbers"])
            keys.extend(mk["keys"])
        targets = []
        for g in groups:
            c = g["canonical"]
            hit = False
            if str(key_to_number.get(c["key"])) in [str(n) for n in nums]:
                hit = True
            if c["key"] in keys or any(k in keys for k in g["members"]):
                hit = True
            if hit:
                targets.append(c)
        for c in targets:
            shared = sorted(set(title_tokens(st["text"])) & set(title_tokens(c["title"])))
            score = len(shared) / float(max(1, len(set(title_tokens(c["title"])))))
            status = "matched" if score >= 0.34 else ("weak" if score > 0 else "mismatch_suspect")
            line = st["text"].count("\n", 0, 0)
            rows.append({
                "sentence": st["text"][:200],
                "marker": " ".join(mk["raw"] for mk in marks)[:80],
                "ref": c["key"],
                "score": round(score, 2),
                "shared_terms": "|".join(shared[:8]),
                "status": status,
                "locator": "C%d" % (st["offset"] + 1),
                "quote": st["text"][:200],
            })
    return rows


# --------------------------------------------------------------------------- #
# offline verification
# --------------------------------------------------------------------------- #
PLACEHOLDER_DOI = ("10.1234/", "10.0000/", "10.5555/", "10.9999/", "10.1000/xyz")
CONTAINER_PLACEHOLDER = ("journal name", "unknown journal", "lorem ipsum", "to be determined")


def verify_record(rec: dict):
    issues = []
    doi = norm_doi(rec["doi"])
    if doi:
        if not re.match(r"^10\.\d{4,9}/\S+$", doi):
            issues.append("doi_syntax:not 10.<4-9 digits>/...")
        elif doi.startswith(PLACEHOLDER_DOI):
            issues.append("doi_example_prefix:prefix %s reserved for examples" % doi.split("/")[0] + "/")
    else:
        issues.append("doi_missing:no DOI to verify against")
    t = norm_title(rec["title"])
    cont = norm_title(rec["container"])
    if t and cont and t == cont:
        issues.append("title_equals_container:title and journal identical")
    for place in CONTAINER_PLACEHOLDER:
        if place in (rec["title"] + " " + rec["container"]).lower():
            issues.append("example_text:contains %r" % place)
    if rec["year"]:
        y = int(rec["year"])
        if not (1500 <= y <= 2100):
            issues.append("year_out_of_range:%s" % rec["year"])
    else:
        issues.append("year_missing:no publication year")
    if not rec["authors"]:
        issues.append("no_author:no author field")
    if rec["entry_type"] in ("article", "J") and not (rec["volume"] or rec["pages"]):
        issues.append("missing_vol_pages:journal article without volume/pages")
    status = "error" if any(i.split(":")[0] in ("doi_syntax", "doi_example_prefix",
                                                "title_equals_container", "example_text",
                                                "year_out_of_range") for i in issues) else "warn"
    if not issues:
        status = "clean"
    detail = {"clean": "no syntax-level issue found",
              "warn": "advisory issues only; metadata present but incomplete",
              "error": "blocking issue: record likely fabricated or mis-typed"}[status]
    return {"key": rec["key"], "doi": doi, "status": status,
            "detail": detail, "issues": "; ".join(issues)}
