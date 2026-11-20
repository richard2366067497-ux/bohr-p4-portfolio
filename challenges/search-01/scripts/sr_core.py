#!/usr/bin/env python3
"""sr_core.py - discovery, record parsing and rendering primitives for
traceable-literature-retrieval (search-01).

Standard library only, no network, no CWD dependency. Everything here is
deterministic heavy lifting: find materials, lift bibliographic records with
locators, learn in-corpus term variants, deduplicate, verify verbatim quotes and
render artifacts. Judgement (relevance, keep/drop, coverage reasoning) is written
by the calling agent in /app/work/draft.json and is NOT decided here.
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path

VERSION = "1.0.0"
MAX_FILES = 400
MAX_OBJECTS = 3000
ABS_MAX = 4000
SKIP_NAMES = {"case.json", "task.md", "challenge.json", "brief.md", "readme.md"}

TITLE_K = ("title", "article_title", "paper_title", "document_title", "titles",
           "display_name", "article-title")
VENUE_K = ("container_title", "journal", "journal_title", "journaltitle", "venue",
           "source_title", "publication", "book_title", "proceedings_title",
           "published_in", "journal-title")
YEAR_K = ("year", "pub_year", "publication_year", "published_year", "issued",
          "publication_date", "pubyear", "pub-date", "date", "published",
          "firstpublicationdate", "first_publication_date", "created", "print_date")
DOI_K = ("doi", "dois", "digital_object_identifier", "doi_url")
AUTH_K = ("author", "authors", "authorstring", "author_list", "creator", "creators",
          "contributors", "byline", "authorname")
ABS_K = ("abstract", "abstracttext", "abstract_text", "abstracttext", "summary",
         "description", "abstract_snippet")
TYPE_K = ("type", "record_type", "document_type", "article_type", "pub_type", "genre")
URL_K = ("url", "link", "links", "full_url", "landing_page", "html", "self")
PMID_K = ("pmid", "pmcid", "europepmc_id", "pubmed_id", "ext_id")

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)
YEAR_RE = re.compile(r"(1[89]\d\d|20\d\d|21\d\d)")
TAG_RE = re.compile(r"<[^>]+>")
_WS = re.compile(r"[\s\u3000\xa0]+")
YEAR_TOKEN = re.compile(r"\((?:19|20)\d\d\)|\b(?:19|20)\d\d\b")

CONTRACT_KEYS = ("output_contract", "outputcontract", "contract", "required_output",
                 "output_fields", "required_fields", "outputs", "expected_output")


# ---------------------------------------------------------------- text helpers
def flat(s):
    return _WS.sub(" ", str(s if s is not None else "")).strip()


def nkey(k):
    return re.sub(r"[^a-z0-9]", "", str(k or "").lower())


def norm_text(s):
    t = flat(s)
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"), ("\u00a0", " ")):
        t = t.replace(a, b)
    return t.lower()


def snippet(s, n=260):
    t = flat(s)
    return t if len(t) <= n else t[:n].rstrip() + " ..."


def as_text(v):
    if isinstance(v, list):
        return "; ".join(flat(x) for x in v if flat(x))
    if isinstance(v, dict):
        return flat(json.dumps(v, ensure_ascii=False))
    return flat(v)


def strip_tags(s):
    return flat(html.unescape(TAG_RE.sub(" ", str(s or ""))))


def clean_doi(v):
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dict):
        v = v.get("value") or v.get("id") or ""
    s = flat(v).replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
    m = DOI_RE.search(s)
    return m.group(0).rstrip(".,;)]}").lower() if m else None


def clean_year(v):
    if isinstance(v, dict):
        dp = v.get("date-parts") or v.get("date_parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            v = dp[0][0]
        else:
            v = v.get("year") or v.get("date") or v.get("value") or ""
    if isinstance(v, list) and v:
        v = v[0]
    m = YEAR_RE.search(str(v or ""))
    return int(m.group(1)) if m else None


def clean_title(v):
    if isinstance(v, list) and v:
        v = v[0]
    t = strip_tags(v)
    return t or None


def clean_authors(v):
    out = []
    items = v if isinstance(v, list) else [v]
    for it in items:
        if isinstance(it, dict):
            fam = first(it, "family", "last", "surname", "name", "literal", "full_name")
            giv = first(it, "given", "first", "forename", "initials")
            fam, giv = flat(fam), flat(giv)
            nm = ("%s %s" % (giv, fam)).strip() if fam and giv else (fam or giv)
            if nm:
                out.append(nm)
        elif isinstance(it, str):
            raw = flat(it)
            if not raw:
                continue
            if len(raw) > 80 or raw.count(",") >= 2:
                out.extend([flat(x) for x in re.split(r"[;]|,(?=\s*[A-Z])", raw) if flat(x)])
            else:
                out.append(raw)
    seen, uniq = set(), []
    for a in out:
        k = a.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    return uniq[:40]


def first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return None


def pick(rec, *keys):
    """Spelling-tolerant lookup: compares nkey() of record keys to nkey() of keys."""
    if not isinstance(rec, dict):
        return None
    want = [nkey(k) for k in keys]
    for k, v in rec.items():
        if nkey(k) in want and v not in (None, "", [], {}):
            return v
    return None


# ---------------------------------------------------------------------- io
def read_text(path, limit=8 * 1024 * 1024):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit], None
    except Exception as exc:  # pragma: no cover - defensive
        return "", "read_error:%s" % exc.__class__.__name__


def load_json(path):
    """Return (obj, note). Tolerates JSONL and truncated tails."""
    raw, err = read_text(path)
    if err:
        return None, err
    s = raw.strip()
    if not s:
        return None, "empty_file"
    try:
        return json.loads(s), None
    except Exception:
        pass
    items, bad = [], 0
    for line in s.splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[", "{", "]", "}"):
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            bad += 1
    if items:
        return items, ("jsonl_recovered_bad_lines=%d" % bad if bad else None)
    return None, "invalid_json"


def dump_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def dump_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------ record lifting
def looks_like_record(d):
    if not isinstance(d, dict) or len(d) > 120:
        return False
    t = pick(d, *TITLE_K)
    if isinstance(t, list):
        t = t[0] if t else None
    if not isinstance(t, str) or len(flat(t)) < 8:
        return False
    signals = 0
    for keys in (DOI_K, YEAR_K, AUTH_K, ABS_K, VENUE_K):
        if pick(d, *keys):
            signals += 1
    if pick(d, "query") or pick(d, "queries"):
        return False
    return signals >= 1


def normalize_record(raw, source_id, locator, source_name=""):
    if not isinstance(raw, dict):
        return None
    title = clean_title(pick(raw, *TITLE_K))
    if not title:
        return None
    doi = clean_doi(pick(raw, *DOI_K))
    if not doi:
        for k, v in raw.items():
            if nkey(k) in ("id", "identifier", "ids", "eid"):
                doi = clean_doi(v)
                if doi:
                    break
    authors = clean_authors(pick(raw, *AUTH_K))
    year = clean_year(pick(raw, *YEAR_K))
    venue = flat(as_text(pick(raw, *VENUE_K)))
    abstract = strip_tags(pick(raw, *ABS_K))
    rec = {
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue or None,
        "doi": doi,
        "abstract": abstract or None,
        "record_type": flat(as_text(pick(raw, *TYPE_K))) or None,
        "pmid": flat(as_text(pick(raw, *PMID_K))) or None,
        "url": flat(as_text(pick(raw, *URL_K)))[:500] or None,
        "source_id": source_id,
        "source_name": source_name or source_id,
        "locator": locator,
        "kind": "structured_record",
        "raw_keys": [str(k) for k in raw][:40],
    }
    rec["raw_text"] = " ".join(x for x in (title, abstract or "", venue or "",
                                           "; ".join(authors)) if x)
    rec["text"] = norm_text(rec["raw_text"])
    missing = [f for f in ("authors", "year", "venue", "doi", "abstract")
               if not rec.get(f)]
    rec["missing_fields"] = missing
    rec["completeness"] = round(1 - len(missing) / 5.0, 3)
    return rec


def looks_citation(s):
    t = flat(s)
    return 50 <= len(t) <= 900 and bool(YEAR_TOKEN.search(t)) and ("." in t or "," in t)


def normalize_citation(text, source_id, locator, source_name=""):
    t = flat(text)
    doi = clean_doi(t)
    year = None
    m = YEAR_TOKEN.search(t)
    if m:
        year = clean_year(m.group(0))
    parts = [p.strip() for p in t.split(".") if p.strip()]
    title = parts[1] if len(parts) > 1 and len(parts[1]) > 12 else parts[0]
    rec = normalize_record({"title": title[:400], "doi": doi, "year": year,
                            "abstract": None, "authors": [parts[0][:120]] if parts else []},
                           source_id, locator, source_name)
    if rec:
        rec["kind"] = "text_citation"
        rec["raw_text"] = t
        rec["text"] = norm_text(t)
        rec["completeness"] = 0.3
        rec["missing_fields"] = ["venue", "abstract"] + ([] if doi else ["doi"])
    return rec


def walk_json(obj, source_id, source_name, pointer="", depth=0, out=None):
    if out is None:
        out = []
    if depth > 14 or len(out) >= MAX_OBJECTS:
        return out
    if isinstance(obj, dict):
        if looks_like_record(obj):
            rec = normalize_record(obj, source_id, pointer or "/", source_name)
            if rec:
                out.append(rec)
            return out
        for k, v in obj.items():
            walk_json(v, source_id, source_name, "%s/%s" % (pointer, str(k).replace("~", "~0").replace("/", "~1")),
                      depth + 1, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_json(v, source_id, source_name, "%s/%d" % (pointer, i), depth + 1, out)
    elif isinstance(obj, str) and looks_citation(obj):
        rec = normalize_citation(obj, source_id, pointer or "/", source_name)
        if rec:
            out.append(rec)
    return out


def _tag(block, tag):
    m = re.search(r"<%s[^>]*>(.*?)</%s>" % (tag, tag), block, re.S | re.I)
    return strip_tags(m.group(1)) if m else None


def parse_xml(text, source_id, rel):
    out = []
    blocks = (re.findall(r"<article\b.*?</article>", text, re.S | re.I)
              or re.findall(r"<record\b.*?</record>", text, re.S | re.I) or [text])
    for i, b in enumerate(blocks[:400]):
        title = _tag(b, "article-title") or _tag(b, "title")
        if not title:
            continue
        doi_m = re.search(r'<article-id[^>]*pub-id-type="doi"[^>]*>(.*?)</article-id>', b, re.S | re.I)
        auth = ["%s %s" % (flat(g), flat(s)) for s, g in
                re.findall(r"<surname>(.*?)</surname>\s*<given-names>(.*?)</given-names>", b, re.S | re.I)]
        rec = normalize_record({
            "title": title,
            "doi": strip_tags(doi_m.group(1)) if doi_m else None,
            "year": _tag(b, "year"),
            "journal": _tag(b, "journal-title"),
            "abstract": _tag(b, "abstract"),
            "type": "xml-article",
            "author": auth,
        }, source_id, "%s#article=%d" % (rel, i + 1), "xml")
        if rec:
            out.append(rec)
    return out


def parse_html(text, source_id, rel):
    metas = {}
    for m in re.finditer(r"<meta\b[^>]*>", text, re.I):
        tag = m.group(0)
        n = re.search(r'(?:name|property)\s*=\s*"([^"]+)"', tag, re.I)
        c = re.search(r'content\s*=\s*"([^"]*)"', tag, re.I)
        if n and c:
            metas.setdefault(n.group(1).lower(), []).append(html.unescape(c.group(1)))
    title = (metas.get("citation_title") or metas.get("dc.title")
             or metas.get("og:title") or [_tag(text, "title")])
    if not title or not title[0]:
        return []
    rec = normalize_record({
        "title": title[0],
        "doi": (metas.get("citation_doi") or [None])[0],
        "year": (metas.get("citation_publication_date") or metas.get("citation_date")
                 or metas.get("dc.date") or [None])[0],
        "journal": (metas.get("citation_journal_title") or [None])[0],
        "author": [a for a in metas.get("citation_author", [])],
        "abstract": (metas.get("citation_abstract") or metas.get("abstract")
                     or metas.get("dc.description") or metas.get("description") or [None])[0],
        "type": (metas.get("citation_article_type") or ["html-snapshot"])[0],
        "url": (metas.get("citation_public_url") or [None])[0],
    }, source_id, "%s#meta" % rel, "html")
    return [rec] if rec else []


def parse_csv_text(text, source_id, rel):
    out = []
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception:
        return out
    if not rows:
        return out
    hdr = {nkey(h) for h in rows[0].keys() if h}
    wanted = {nkey(k) for k in TITLE_K}
    if hdr & wanted:
        for i, row in enumerate(rows[:1000]):
            rec = normalize_record(row, source_id, "%s#row=%d" % (rel, i + 2), "csv")
            if rec:
                out.append(rec)
    return out


# ---------------------------------------------------------------- discovery
def discover(input_dir):
    files = []
    try:
        paths = sorted(Path(input_dir).rglob("*"))
    except Exception:
        return files
    for p in paths:
        try:
            if p.is_dir() or p.is_symlink():
                continue
            if p.name.startswith(".") or p.name.lower() in SKIP_NAMES:
                continue
            size = p.stat().st_size
            if size <= 0 or size > 20 * 1024 * 1024:
                continue
            files.append({"rel": p.relative_to(input_dir).as_posix(), "abs": p,
                          "kind": p.suffix.lower().lstrip(".") or "txt", "bytes": size})
        except Exception:
            continue
        if len(files) >= MAX_FILES:
            break
    return files


def collect(input_dir):
    """Return (records, notes, sources, errors, degradations)."""
    records, notes, sources, errors, degradations = [], [], [], [], []
    for f in discover(input_dir):
        rel, kind, path = f["rel"], f["kind"], f["abs"]
        src_id = rel.replace("/", "_")
        got, role = [], "records"
        try:
            if kind == "json" or kind == "jsonl":
                obj, note = load_json(path)
                if note and note != "jsonl_recovered_bad_lines=0":
                    degradations.append({"code": "json_parse_note", "source_id": src_id,
                                         "detail": str(note)[:200]})
                if obj is None:
                    role = "unreadable"
                else:
                    got = walk_json(obj, src_id, f["kind"], "")
                    for rec in got:  # file-qualified pointer, e.g. responses/x.json#/message/items/0
                        ptr = rec.get("locator") or "/"
                        rec["locator"] = "%s#%s" % (rel, ptr if ptr.startswith("/") else "/" + ptr)
            elif kind in ("xml", "nxml", "jats"):
                text, err = read_text(path)
                got = parse_xml(text, src_id, rel) if not err else []
            elif kind in ("html", "htm"):
                text, err = read_text(path)
                got = parse_html(text, src_id, rel) if not err else []
            elif kind == "csv" or kind == "tsv":
                text, err = read_text(path)
                got = parse_csv_text(text, src_id, rel) if not err else []
            elif kind in ("pdf", "docx", "zip", "png", "jpg", "jpeg", "tif", "tiff"):
                note = "binary_or_pdf_not_parsed"
                degradations.append({"code": note, "source_id": src_id,
                                     "detail": "binary material kept as locator only; read it with the "
                                               "pdf/ocr tools before quoting"})
                role = "unparsed_binary"
            else:
                text, err = read_text(path)
                units = []
                for i, line in enumerate([l for l in text.splitlines() if flat(l)]):
                    units.append({"locator": "%s#L%d" % (rel, i + 1), "text": flat(line)})
                cites = [u for u in units if looks_citation(u["text"])]
                got = [normalize_citation(u["text"], src_id, u["locator"], kind) for u in cites[:200]]
                got = [g for g in got if g]
                notes.append({"source_id": src_id, "locator": rel, "lines": len(units),
                              "preview": snippet(text, 400)})
                if not got:
                    role = "notes_only"
        except Exception as exc:
            errors.append({"code": "material_parse_error", "source_id": src_id,
                           "detail": "%s: %s" % (exc.__class__.__name__, str(exc)[:160])})
            got = []
        finally:
            sources.append({"source_id": src_id, "path": rel, "format": f["kind"],
                            "bytes": f["bytes"], "role": role,
                            "records": len(got), "extractor": "sr_core"})
        records.extend(got)
    return records, notes, sources, errors, degradations


# ------------------------------------------------------------------- task
def find_task_text(case, task_md):
    ti = pick(case, "task_instruction", "task", "instruction", "query", "question",
              "research_question", "prompt", "objective", "description")
    parts = []
    if isinstance(ti, (str, list)):
        parts.append(as_text(ti))
    if task_md:
        parts.append(str(task_md))
    return "\n".join(p for p in parts if p)


def parse_task(case, task_md):
    rq = pick(case, "research_question", "question", "topic", "subject", "aim", "goal")
    text = find_task_text(case, task_md)
    task = {
        "research_question": flat(rq) if rq else snippet(text, 400),
        "source_text_chars": len(text),
    }
    k = None
    for key in ("top_k", "k", "target_k", "n", "limit", "num_results", "target_count", "expected_count"):
        v = pick(case, key)
        if isinstance(v, (int, float)) and 0 < v <= 500:
            k = int(v)
            break
    if k is None:
        m = (re.search(r"(?:top[_\s-]?k|arget[_\s-]?k|k)\s*[=:：]\s*(\d{1,3})", text, re.I)
             or re.search(r"(?:top|前|至少|最少|返回)\s*(\d{1,3})\s*(?:篇|条|papers|results)?", text)
             or re.search(r"\b(\d{1,3})\s*(?:篇|条)\s*(?:文献|论文)", text))
        if m:
            k = max(1, min(200, int(m.group(1))))
    task["target_k"] = k
    task["target_k_source"] = "case_field_or_instruction" if k else "default"
    if k is None:
        task["target_k"] = 20
    win = pick(case, "time_window", "year_range", "date_range", "window", "recency")
    if not win:
        m = re.search(r"((?:19|20)\d\d)\s*[-–~至]\s*((?:19|20)\d\d)", text)
        if m:
            win = "%s-%s" % (m.group(1), m.group(2))
        else:
            m = re.search(r"(?:近|最近|last|past)\s*(\d{1,2})\s*(?:年|years)", text, re.I)
            if m:
                win = "last %s years" % m.group(1)
    task["time_window"] = flat(win) if win else None
    kws = pick(case, "keywords", "terms", "must_include", "include_terms", "topic_terms",
               "concepts", "search_terms")
    task["seed_keywords"] = [flat(x) for x in kws] if isinstance(kws, list) else ([flat(kws)] if kws else [])
    exc = pick(case, "exclude_terms", "exclusions", "exclude", "negative_terms", "must_exclude")
    task["exclude_terms"] = [flat(x) for x in exc] if isinstance(exc, list) else ([flat(exc)] if exc else [])
    langs = pick(case, "languages", "language", "lang")
    task["languages"] = [flat(x) for x in langs] if isinstance(langs, list) else ([flat(langs)] if langs else [])
    dbs = pick(case, "databases", "sources", "repositories", "target_sources")
    task["declared_sources"] = [flat(x) for x in dbs] if isinstance(dbs, list) else ([flat(dbs)] if dbs else [])
    task["constraints_text"] = snippet(text, 1200)
    return task


def find_required(case, records_cfg):
    for key in ("required", "required_references", "key_papers", "must_cite", "checklist",
                "required_coverage", "gold", "reference_list", "targets", "key_references"):
        v = pick(case, key)
        if v:
            return v
    return records_cfg


def find_graph(files):
    for f in files:
        if "reference" in f["rel"].lower() and f["rel"].lower().endswith(".json"):
            obj, _ = load_json(f["abs"])
            if obj is not None:
                return {"source": f["rel"], "data": obj}
    return None


def find_import_states(files, case):
    states = []
    v = pick(case, "import_state", "import_states", "incremental", "import_status", "sync_state")
    if v:
        states.append({"source": "case.json", "state": v})
    for f in files:
        low = f["rel"].lower()
        if "import" in low and low.endswith(".json"):
            obj, _ = load_json(f["abs"])
            if obj is not None:
                states.append({"source": f["rel"], "state": obj})
    return states


def graph_refs(graph):
    """Flatten a retained reference graph into {doi, title} checkpoints."""
    refs = []

    def walk(o, depth=0):
        if depth > 10 or len(refs) > 500:
            return
        if isinstance(o, dict):
            doi = clean_doi(pick(o, "doi", "DOI", "id") if pick(o, "doi", "DOI") else None)
            title = clean_title(pick(o, "title", "titles"))
            if doi or (title and len(title) > 12):
                refs.append({"doi": doi, "title": flat(title)[:300] if title else None})
                return
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)

    walk(graph.get("data") if isinstance(graph, dict) else graph)
    seen, out = set(), []
    for r in refs:
        key = r["doi"] or norm_text(r["title"] or "")[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def C_TITLE_IS_DOI(title):
    return bool(DOI_RE.search(flat(title))) and len(flat(title)) <= 80


def required_items(raw):
    """Accept list[str] / list[dict] / {items:[...]} and return {ref_id, doi, title}."""
    if isinstance(raw, dict):
        for key in ("items", "references", "required", "list", "papers", "data"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raw = [raw]
    if not isinstance(raw, list):
        return []
    out = []
    for i, it in enumerate(raw[:200]):
        if isinstance(it, str):
            doi, title = clean_doi(it), flat(it)
        elif isinstance(it, dict):
            doi = clean_doi(pick(it, "doi", "DOI", "id"))
            title = clean_title(pick(it, "title", "name", "label", "reference"))
            if not title and not doi:
                continue
            title = flat(title)[:300] if title else None
        else:
            continue
        if title and doi and C_TITLE_IS_DOI(title):
            title = None
        if not doi and not title:
            continue
        out.append({"ref_id": "REQ%02d" % (i + 1), "doi": doi, "title": title})
    return out


# ------------------------------------------------------- term expansion
PAIRS = (("aluminium", "aluminum"), ("behaviour", "behavior"), ("colour", "color"),
         ("fibre", "fiber"), ("sulphur", "sulfur"), ("haemoglobin", "hemoglobin"),
         ("tumour", "tumor"), ("ageing", "aging"), ("catalyse", "catalyze"),
         ("modelling", "modeling"), ("labelled", "labeled"), ("nanoparticle", "nanoparticles"))


def stem(w):
    w = w.lower().strip("-")
    for suf in ("ies", "ses", "es", "s"):
        if w.endswith(suf) and len(w) > len(suf) + 3:
            return w[: -len(suf)]
    return w


def learn_expansions(texts, cap=60):
    """Learn in-corpus abbreviation / spelling variants instead of shipping a fixed list."""
    joined = "\n".join(texts)
    found = {}
    for m in re.finditer(r"([A-Za-z][A-Za-z\-]{3,40}(?:\s+[A-Za-z][A-Za-z\-]{2,30}){0,4})\s*\(([A-Z][A-Za-z0-9\-]{1,9})\)", joined):
        long_form, short = flat(m.group(1)), flat(m.group(2))
        if len(short) >= 2 and len(long_form) > len(short):
            found.setdefault(short.lower(), {"short": short, "long": long_form})
    for a, b in PAIRS:
        found.setdefault(a, {"short": a, "long": b, "kind": "spelling"})
    return list(found.values())[:cap]


def tokens(text, cap=60):
    out, seen = [], set()
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", norm_text(text)):
        s = stem(w)
        if len(s) < 3 or s in seen:
            continue
        seen.add(s)
        out.append(s)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", str(text or "")):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in seen:
                seen.add(bg)
                out.append(bg)
    return out[:cap]


# ----------------------------------------------------------- fallback rank
def fingerprint(rec):
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", norm_text(rec.get("title") or ""))
    return "title:" + t[:90]


def cluster(records):
    """Group records by DOI (else title fingerprint); surface metadata conflicts."""
    groups, order = {}, []
    for r in records:
        key = fingerprint(r)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    clusters, conflicts = [], []
    for key in order:
        members = groups[key]
        keeper = max(members, key=lambda r: (r.get("completeness") or 0, len(r.get("abstract") or "")))
        clusters.append({"key": key, "keeper": keeper, "members": members})
        if len(members) > 1:
            for field in ("year", "venue"):
                vals = {flat(m.get(field)) for m in members if m.get(field)}
                if len(vals) > 1:
                    conflicts.append({"field": field, "kind": "metadata_conflict", "values": sorted(vals),
                                      "objects": [m.get("object_id") for m in members],
                                      "note": "same work reported differently across sources; keeper chosen by "
                                              "completeness, both versions remain inspectable in sources"})
    return clusters, conflicts


def verify_quote(quote, rec, min_len=12):
    """Verbatim check of an agent quote against the record text at its locator."""
    q = norm_text(quote)
    if len(q) < min_len:
        return False, "too_short", 0.0
    hay = rec.get("text") or norm_text(rec.get("raw_text") or "")
    if q in hay:
        return True, "text", 1.0
    parts = [p for p in re.split(r"\.\.\.|…", q) if len(p.strip()) >= 8]
    if len(parts) >= 2 and all(p.strip() in hay for p in parts):
        return True, "text_elided", 0.9
    return False, "not_found", 0.0


def score_record(rec, families, exclude):
    if not families:
        return 0.0, 0
    hay = rec.get("text") or ""
    score, hits = 0.0, 0
    for fam in families:
        terms = fam if isinstance(fam, (list, tuple)) else [fam]
        if any(t and norm_text(t) in hay for t in terms):
            hits += 1
            if any(t and norm_text(t) in norm_text(rec.get("title") or "") for t in terms):
                score += 1.0
            else:
                score += 0.5
    if any(e and norm_text(e) in hay for e in exclude):
        score *= 0.4
    return round(min(1.0, score / max(1.0, len(families))), 3), hits


def contract_keys(case):
    """Enumerate the output_contract keys declared by the case, tolerantly."""
    for key in CONTRACT_KEYS:
        v = pick(case, key)
        if not v:
            continue
        keys = []
        if isinstance(v, dict):
            keys = [str(k) for k in v.keys()]
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str):
                    keys.append(it)
                elif isinstance(it, dict):
                    keys.extend(str(k) for k in it.keys())
        elif isinstance(v, str):
            keys = [x.strip() for x in re.split(r"[,;]", v) if x.strip()]
        if keys:
            return keys[:60]
    return []


def case_id_of(case, inp):
    v = pick(case, "case_id", "caseid", "id", "case_name", "name")
    if isinstance(v, (str, int)):
        return str(v)
    return (Path(inp).name if inp else "") or "unknown-case"
