#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""federated-search-reconcile :: ledger layer.

Discover /input, fingerprint responses (sha256/format/shape/db attribution/
error markers), locate record lists in heterogeneous search responses,
normalise records keeping the per-field source path and a raw-record
fingerprint (db -> query -> raw response -> field stays replayable), and keep
present / suspect / missing / unknown apart. Stdlib only, offline.
"""
import csv, hashlib, io, json, re, zlib
from pathlib import Path

V = "1.0.0"
FIELDS = ("title", "authors", "year", "venue", "doi", "abstract")
IDF = ("pmid", "pmcid", "arxiv")
EXTRA = ("volume", "issue", "pages", "type", "url")
ALLF = FIELDS + IDF + EXTRA
SYNSET = ("title", "authors", "year", "venue", "doi", "abstract", "pmid", "pmcid",
          "arxiv", "volume", "issue", "pages", "type", "url")


def sha(s):
    if isinstance(s, bytes):
        return hashlib.sha256(s).hexdigest()
    return hashlib.sha256(str(s).encode("utf-8", "replace")).hexdigest()


def sh(s, n=16):
    return sha(s)[:n]


def jd(o, **kw):
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("indent", 2)
    return json.dumps(o, **kw)


def cj(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def clip(v, n=300):
    s = v if isinstance(v, str) else cj(v)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def norm_ws(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def strip_tags(s):
    s = re.sub(r"<[^>]{0,400}>", " ", str(s))
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&apos;", "'"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    return norm_ws(s)


def nkey(k):
    """key -> lowercase alphanumerics, namespace prefix dropped."""
    s = str(k).lower()
    if ":" in s:
        s = s.split(":")[-1]
    return re.sub(r"[^a-z0-9]", "", s)


DB_TOKENS = (
    ("crossref", ("crossref",)), ("europepmc", ("europepmc", "europe_pmc", "epmc", "europmc")),
    ("pubmed", ("pubmed", "medline")), ("openalex", ("openalex",)),
    ("semanticscholar", ("semanticscholar", "semantic_scholar", "s2api", "_s2")),
    ("scopus", ("scopus",)), ("webofscience", ("webofscience", "web_of_science", "wos", "isiknowledge")),
    ("arxiv", ("arxiv",)), ("doaj", ("doaj",)), ("jstage", ("jstage",)), ("cnki", ("cnki",)),
    ("wanfang", ("wanfang", "cqvip")), ("ieee", ("ieee", "xplore")), ("acm", ("acm", "dlacm")),
    ("elsevier", ("elsevier", "sciencedirect", "scidir")), ("springer", ("springer", "nature", "biomedcentral")),
    ("wiley", ("wiley", "onlinelibrary")), ("taylorfrancis", ("taylorfrancis", "tandfonline", "tandf")),
    ("sage", ("sagepub",)), ("plos", ("plos",)), ("mdpi", ("mdpi",)), ("frontiers", ("frontiers",)),
    ("pnas", ("pnas",)), ("bmj", ("bmj",)), ("jama", ("jama",)), ("nejm", ("nejm",)),
    ("cell", ("cell",)), ("science", ("sciencemag",)), ("lens", ("lens",)),
    ("dimensions", ("dimensions",)), ("unpaywall", ("unpaywall",)), ("openaire", ("openaire",)),
    ("core", ("coreac", "coreapi")), ("scholar", ("googlescholar", "scholar")),
    ("publisher", ("publisher",)),
)
SHAPES = (("crossref", ("message", "items")), ("europepmc", ("resultlist", "result")),
          ("elasticsearch", ("hits", "hits")), ("scopus", ("search-results", "entry")),
          ("webofscience", ("data", "records")), ("solr", ("response", "docs")),
          ("atom", ("feed", "entry")), ("openalex", ("results",)))


def _keys(obj, depth=0):
    if depth > 5:
        return []
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k).lower())
            if isinstance(v, (dict, list)):
                out += _keys(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:5]:
            out += _keys(v, depth + 1)
    return out


def db_from_obj(obj):
    ks = set(_keys(obj))
    for db, path in SHAPES:
        if all(p in ks for p in path):
            return db, ".".join(path)
    return None, None


def db_from_name(name):
    t = re.sub(r"[^a-z0-9]+", "_", name.lower())
    best = (0, None)
    for db, toks in DB_TOKENS:
        for tk in toks:
            if tk in t and len(tk) > best[0]:
                best = (len(tk), db)
    return best[1]


def read_bytes(p, cap=1200000):
    try:
        return p.read_bytes()[:cap]
    except Exception:
        return b""


def pdf_text(b):
    """Heuristic text layer: Tj/TJ literals in (Flate) content streams."""
    out = []
    for m in re.finditer(rb"stream\r?\n", b):
        e = b.find(b"endstream", m.end())
        if e < 0:
            continue
        raw = b[m.end():e]
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        if b"Tj" in raw or b"TJ" in raw:
            out.append(" ".join(x.group(0)[1:-1].decode("latin-1", "replace")
                                for x in re.finditer(rb"\([^)]{2,}\)", raw)))
    return norm_ws(" ".join(out))


def html_meta(text):
    """citation_* / dc.* / og meta tags -> record dicts."""
    tags = []
    for m in re.finditer(r"<meta\b[^>]*>", text, re.I):
        tag = m.group(0)
        n = re.search(r"""name\s*=\s*["']([^"']+)["']""", tag, re.I) or \
            re.search(r"""property\s*=\s*["']([^"']+)["']""", tag, re.I)
        c = re.search(r"""content\s*=\s*["']([^"']*)["']""", tag, re.I)
        if n and c:
            tags.append((n.group(1).strip().lower(), strip_tags(c.group(1))))
    keep = [t for t in tags if t[0].startswith(("citation_", "dc.", "dcterms.", "og:"))]
    start = ("citation_title", "citation_firstpage", "dc.title", "og:title")
    recs, cur = [], {}
    for k, v in keep:
        if k in start and k in cur:
            recs.append(cur)
            cur = {}
        cur.setdefault(k, []).append(v)
    if cur:
        recs.append(cur)
    return [{k: (v if len(v) > 1 else v[0]) for k, v in r.items()} for r in recs]


def parse_jsonl(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] not in "{[":
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _is_rec(v):
    if not isinstance(v, dict) or not v:
        return False
    ks = {nkey(k) for k in v}
    hit = ks & {nkey(s) for s in SYNSET}
    return len(hit) >= 2 or ("id" in ks and len(hit) >= 1)


def looks_records(lst):
    ds = [x for x in lst if isinstance(x, dict)]
    if not ds:
        return False
    good = sum(1 for x in ds if _is_rec(x))
    return good >= max(1, int(0.5 * len(ds)))


def record_lists(obj):
    """All (path, [dict,...]) positions that look like record lists."""
    found, seen = [], set()

    def walk(node, path, depth):
        if depth > 6:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                p = path + "." + str(k)
                if isinstance(v, list) and v and looks_records(v) and id(v) not in seen:
                    seen.add(id(v))
                    found.append((p[1:] if p.startswith("$.") else p, v))
                walk(v, p, depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node[:60]):
                walk(v, "%s[%d]" % (path, i), depth + 1)

    if isinstance(obj, list) and obj and looks_records(obj):
        return [("$", obj)]
    walk(obj, "$", 0)
    if not found and isinstance(obj, dict) and _is_rec(obj):
        return [("$", [obj])]
    return found


SYN = {
    "title": ("title", "titles", "articletitle", "documenttitle", "primarytitle", "displayname",
              "titletext", "maintitle", "name"),
    "authors": ("author", "authors", "authorlist", "authorname", "authornames", "creators",
                "creator", "contributors", "contributor", "byline", "authorships", "names", "person"),
    "year": ("year", "pubyear", "publicationyear", "published", "issued", "publisheddate",
             "publicationdate", "pubdate", "coverdate", "printdate", "copyrightyear",
             "onlinefirstdate", "date", "earliestdate", "pubinfo"),
    "venue": ("venue", "journal", "journaltitle", "journalname", "containertitle", "container",
              "source", "publicationname", "publication", "host", "booktitle", "series"),
    "doi": ("doi", "dois", "digitalobjectidentifier", "prismdoi", "articleid"),
    "abstract": ("abstract", "abstracttext", "abstracts", "summary", "description", "teaser"),
    "pmid": ("pmid", "pubmedid", "medlineid"),
    "pmcid": ("pmcid", "pmccid", "pmc"),
    "arxiv": ("arxiv", "arxivid", "arxividentifier"),
    "volume": ("volume", "vol", "prismvolume"),
    "issue": ("issue", "number", "prismissue"),
    "pages": ("page", "pages", "pagination", "pagerange", "prismpagrange", "startpage"),
    "type": ("type", "publicationtype", "articletype", "doctype", "documenttype", "genre"),
    "url": ("url", "link", "links", "href", "fulltexturl", "landingpage"),
}

ADAPTERS = {
    "crossref": {"title": ["title.0", "title"], "authors": ["author"],
                 "year": ["issued.date-parts.0.0", "published-print.date-parts.0.0",
                          "published-online.date-parts.0.0", "published.date-parts.0.0",
                          "created.date-parts.0.0"],
                 "venue": ["container-title.0", "container-title", "short-container-title.0"],
                 "doi": ["DOI"], "abstract": ["abstract"], "type": ["type"]},
    "europepmc": {"title": ["title"], "authors": ["authorList.author"],
                  "year": ["pubYear", "firstPublicationDate"],
                  "venue": ["journalInfo.journal.title", "bookOrReportDetails.publisher", "journalTitle"],
                  "doi": ["doi"], "abstract": ["abstractText"], "pmid": ["pmid"], "pmcid": ["pmcid"],
                  "type": ["pubTypeList.pubType.0", "pubType"]},
    "openalex": {"title": ["title", "display_name"], "authors": ["authorships.author"],
                 "year": ["publication_year"],
                 "venue": ["primary_location.source.display_name", "host_venue.display_name"],
                 "doi": ["doi"], "pmid": ["ids.pmid"], "type": ["type"],
                 "volume": ["biblio.volume"], "issue": ["biblio.issue"], "pages": ["biblio.first_page"]},
    "publisher": {"title": ["citation_title"], "authors": ["citation_author"],
                  "year": ["citation_publication_date", "citation_online_date", "published",
                           "copyrightYear", "year"],
                  "venue": ["citation_journal_title", "citation_conference_title", "journal"],
                  "doi": ["citation_doi", "doi"], "abstract": ["citation_abstract", "abstract"],
                  "volume": ["citation_volume"], "issue": ["citation_issue"],
                  "pages": ["citation_firstpage"]},
    "semanticscholar": {"title": ["title"], "authors": ["authors"], "year": ["year"],
                        "venue": ["venue", "journal.name"],
                        "doi": ["externalIds.DOI", "external_ids.DOI"],
                        "abstract": ["abstract"], "pmid": ["externalIds.PubMed"]},
    "scopus": {"title": ["dc:title", "title"], "authors": ["dc:creator", "author"],
               "year": ["prism:coverDate", "coverDate"], "venue": ["prism:publicationName"],
               "doi": ["prism:doi", "doi"]},
    "webofscience": {"title": ["titles.title.0.value", "titles.title"], "authors": ["names.name"],
                     "year": ["pub_info.pubyear"], "venue": ["titles.title.0.title", "source.title"],
                     "doi": ["dynamic_data.cluster_related.object_id.value", "other.identifier"],
                     "pmid": ["other.ids"]},
}


def pick(obj, path):
    cur = [obj]
    for seg in str(path).split("."):
        nxt = []
        for c in cur:
            if seg.isdigit():
                i = int(seg)
                if isinstance(c, list) and len(c) > i:
                    nxt.append(c[i])
                elif isinstance(c, dict) and str(i) in c:
                    nxt.append(c[str(i)])
            elif isinstance(c, dict):
                if seg in c:
                    nxt.append(c[seg])
                else:
                    for k in c:
                        if nkey(k) == nkey(seg):
                            nxt.append(c[k])
                            break
            elif isinstance(c, list):
                for e in c:
                    if isinstance(e, dict) and seg in e:
                        nxt.append(e[seg])
        cur = nxt
    return [c for c in cur if c not in (None, "", [], {})]


def leaves(rec, depth=0, path="", out=None):
    out = [] if out is None else out
    if depth > 3:
        return out
    if isinstance(rec, dict):
        for k, v in rec.items():
            p = (path + "." + str(k)) if path else str(k)
            if isinstance(v, (dict, list)):
                leaves(v, depth + 1, p, out)
            else:
                out.append((p, str(k), v))
    elif isinstance(rec, list):
        for i, v in enumerate(rec[:40]):
            if isinstance(v, (dict, list)):
                leaves(v, depth + 1, path + "[%d]" % i, out)
            else:
                out.append((path + "[%d]" % i, nkey(path.split(".")[-1]), v))
    return out


def _names(v):
    out = []
    if isinstance(v, list):
        for e in v:
            out += _names(e)
        return out
    if isinstance(v, dict):
        keys = {nkey(k): k for k in v}
        fam = v.get(keys.get("family", ""), "") or v.get(keys.get("lastname", ""), "")
        giv = v.get(keys.get("given", ""), "") or v.get(keys.get("firstname", ""), "")
        if fam:
            return [("%s, %s" % (fam, giv)).strip(", ") if giv else str(fam)]
        for k in ("fullname", "displayname", "name", "authorname", "value", "literal"):
            if keys.get(k):
                return [norm_ws(v[keys[k]])]
        return []
    s = norm_ws(v)
    if not s:
        return []
    if ";" in s or " and " in s:
        return [x.strip() for x in re.split(r";| and ", s) if x.strip()]
    return [s]


def _year(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        y = int(v)
        return y if 1500 < y < 2100 else None
    if isinstance(v, dict):
        for vv in v.values():
            y = _year(vv)
            if y:
                return y
        return None
    if isinstance(v, list):
        for e in v:
            y = _year(e)
            if y:
                return y
        return None
    m = re.search(r"(1[5-9]\d{2}|20\d{2}|21\d{2})", str(v))
    return int(m.group(1)) if m else None


def _doi(v):
    m = re.search(r"10\.\d{4,9}/[^\s\"'<>,;]+", str(v))
    return m.group(0).rstrip(".").lower() if m else None


def _scalar(v, field):
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        for k in v:
            if nkey(k) in ("value", "name", "title", "text", "url"):
                return _scalar(v[k], field)
        return None
    if v is None:
        return None
    s = strip_tags(v) if field in ("title", "venue", "abstract") else norm_ws(v)
    return s or None


SHAPE = {"title": lambda s: len(s) >= 8 and "<" not in s and not (s.isupper() and len(s) > 24),
         "authors": lambda l: bool(l) and all(re.search(r"[A-Za-z\u4e00-\u9fa5]", a) for a in l)
         and not any(a.lower() in ("et al", "et al.", "anonymous", "unknown", "n/a", "null") for a in l),
         "year": lambda y: isinstance(y, int) and 1800 <= y <= 2035,
         "venue": lambda s: len(s) >= 2 and s.lower() not in ("none", "null", "n/a", "unknown"),
         "doi": lambda d: bool(re.match(r"^10\.\d{4,9}/\S+$", d)),
         "abstract": lambda s: len(s) >= 40,
         "pmid": lambda s: bool(re.match(r"^\d{4,9}$", str(s))),
         "pmcid": lambda s: bool(re.match(r"^PMC\d+$", str(s), re.I)),
         "arxiv": lambda s: bool(re.search(r"\d{4}\.\d{4,5}", str(s))),
         "volume": lambda s: len(s) <= 20, "issue": lambda s: len(s) <= 12,
         "pages": lambda s: len(s) <= 40, "type": lambda s: len(s) <= 40,
         "url": lambda s: s.startswith("http")}


def extract(rec, db):
    """-> {field: {value, state, src_field, note}}."""
    ad = ADAPTERS.get(db or "", {})
    lv = leaves(rec)
    out = {}
    for f in ALLF:
        val, src = None, ""
        for p in ad.get(f, []):
            got = pick(rec, p)
            if got:
                val, src = got, p
                break
        if val is None:
            cands, want = [], {nkey(s) for s in SYN[f]}
            for p, k, v in lv:
                kk = nkey(k)
                if kk.startswith("citation"):
                    kk = kk[8:]
                if kk in want:
                    cands.append((p.count("."), p, v))
            if cands:
                cands.sort(key=lambda x: x[0])
                val, src = [c[2] for c in cands], cands[0][1]
        if f == "authors":
            vv = []
            for x in (val if isinstance(val, list) else [val]) if val is not None else []:
                vv += _names(x)
            vv = [a for a in vv if a]
        elif f == "year":
            vv = _year(val) if val is not None else None
        elif f == "doi":
            first = val[0] if isinstance(val, list) and val else val
            vv = _doi(first) if first is not None else None
        else:
            vv = _scalar(val, f) if val is not None else None
        if vv in ("", []):
            vv = None
        if vv is None or (isinstance(val, list) and all(x in (None, "", [], {}) for x in val)):
            if val is not None:
                st, note = "missing", "key present but value empty/null in raw response"
            elif db in (None, "", "unknown") or not ad:
                st, note = "unknown", "response structure not attributed to a known database schema"
            elif f in ad:
                st, note = "missing", "field expected for this database schema, absent in this record"
            else:
                st, note = "missing", "database family does not expose this field"
        else:
            chk = SHAPE.get(f)
            try:
                ok = chk(vv) if chk else True
            except Exception:
                ok = True
            st = "present" if ok else "suspect"
            note = "" if ok else "value fails shape check for %s" % f
        out[f] = {"value": vv, "state": st, "src_field": src or "", "note": note}
    return out


def completeness(fields):
    return sum(1 for f in FIELDS if fields.get(f, {}).get("state") == "present")


def first_surname(rec):
    a = (rec.get("fields", {}).get("authors") or {}).get("value") or []
    if not a:
        return ""
    s = re.split(r"[,;\s]+", str(a[0]).strip())[0]
    return re.sub(r"[^a-z\u4e00-\u9fa5]", "", s.lower())


BAD = {400: "bad request", 401: "credentials required", 403: "forbidden", 404: "not found",
       429: "rate limited", 500: "server error", 502: "bad gateway", 503: "service unavailable",
       504: "gateway timeout"}


def failure_of(obj, text, n_rec):
    code, msg = None, ""
    if isinstance(obj, (dict, list)):
        for p in ("status", "statusCode", "http_status", "httpStatus", "status_code", "code"):
            for v in pick(obj, p):
                if isinstance(v, (int, str)) and str(v).strip().isdigit():
                    code = int(str(v).strip())
                    break
            if code:
                break
        for p in ("error", "errors", "fault", "errmsg", "errMsg", "error.message", "detail",
                  "errorMessage", "message"):
            for v in pick(obj, p):
                if isinstance(v, str) and 3 < len(v) < 300:
                    msg = clip(v, 200)
                    break
            if msg:
                break
    if not msg:
        for p in ("rate limit", "timeout", "timed out", "forbidden", "unauthorized",
                  "service unavailable", "too many requests", "quota", "not authorized"):
            if p in text[:4000].lower():
                msg = p
                break
    if n_rec and not (code in BAD):
        return {"http_status": code, "reason": msg} if msg else None
    if code in BAD:
        return {"http_status": code, "reason": BAD[code] + ("; " + msg if msg else "")}
    if msg:
        return {"http_status": code, "reason": msg}
    return None


MAT_EXT = (".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".txt", ".md", ".html", ".htm",
           ".xml", ".pdf", ".yaml", ".yml")
SKIP = ("case.json", "resources.yaml", "public-manifest.json", "draft.json")


def find_case(inp):
    c = Path(inp) / "case.json"
    if c.is_file():
        try:
            return json.loads(c.read_text("utf-8", "replace")), "case.json", []
        except Exception as e:
            return None, "case.json", [{"stage": "case", "path": "case.json",
                                        "error": "bad json: %s" % e}]
    errs = []
    base = Path(inp)
    cands = sorted(base.rglob("case*.json")) if base.is_dir() else []
    for q in cands:
        try:
            o = json.loads(q.read_text("utf-8", "replace"))
            if isinstance(o, dict):
                return o, q.name, [{"stage": "case", "path": q.name, "error": "fallback case json"}]
        except Exception as e:
            errs.append({"stage": "case", "path": q.name, "error": str(e)})
    for q in (sorted(base.rglob("*.json")) if base.is_dir() else []):
        if q.name in SKIP or "manifest" in q.name.lower():
            continue
        try:
            o = json.loads(q.read_text("utf-8", "replace"))
            if isinstance(o, dict) and ("case_id" in o or "output_contract" in o or "task_instruction" in o):
                return o, q.name, errs + [{"stage": "case", "path": q.name, "error": "case json fallback"}]
        except Exception:
            continue
    return None, None, errs + [{"stage": "case", "error": "no case.json found under input"}]


def parse_one(p):
    """-> (kind, obj, text, record_lists, note)."""
    b = read_bytes(p)
    ext = p.suffix.lower()
    text = b.decode("utf-8", "replace")
    if ext == ".pdf":
        t = pdf_text(b)
        return "pdftext", None, t, [], ("heuristic text layer (%d chars)" % len(t)) if t else "no text layer"
    if ext in (".json", ".jsonl", ".ndjson"):
        if ext != ".json":
            rows = parse_jsonl(text)
            if rows:
                return "jsonl", rows, text, ([("$", rows)] if looks_records(rows) else []), \
                    "%d jsonl rows" % len(rows)
        try:
            obj = json.loads(text)
            return "json", obj, text, record_lists(obj), ""
        except Exception as e:
            rows = parse_jsonl(text)
            note = "json parse failed: %s; %d jsonl rows recoverable" % (e, len(rows))
            return "json?", (rows or None), text, ([("$", rows)] if rows else []), note
    if ext in (".csv", ".tsv"):
        delim = "\t" if ext == ".tsv" else ","
        try:
            reader = list(csv.reader(io.StringIO(text), delimiter=delim))
        except Exception as e:
            return "csv", None, text, [], "csv parse failed: %s" % e
        if not reader:
            return "csv", None, text, [], "empty table"
        head = [h.strip() for h in reader[0]]
        rows = [dict(zip(head, r + [""] * (len(head) - len(r)))) for r in reader[1:]
                if any(x.strip() for x in r)]
        return "csv", {"header": head, "rows": rows}, text, ([("$.rows", rows)] if rows else []), \
            "%d rows x %d cols" % (len(rows), len(head))
    if ext in (".html", ".htm", ".xml"):
        recs = html_meta(text)
        return "html", {"meta": recs}, text, ([("$.meta", recs)] if recs else []), \
            ("%d meta blocks" % len(recs)) if recs else "no citation_* meta tags"
    return "text", {"text": text[:400000]}, text, [], "plain text (%d chars)" % len(text)


def build_index(inp):
    """Deterministic index of the input tree."""
    inp = Path(inp)
    idx = {"version": V, "input": str(inp), "case": {}, "case_from": None, "task_md": None,
           "files": [], "records": [], "failures": [], "errors": [], "degradations": [],
           "assumptions": [], "docs": []}
    case, cfrom, cerrs = find_case(inp)
    idx["errors"] += cerrs
    idx["case_from"] = cfrom
    case = case if isinstance(case, dict) else {}
    idx["case"] = {k: case.get(k) for k in ("case_id", "task_instruction", "instruction", "prompt",
                                            "output_contract", "title", "difficulty", "tags")}
    for k, v in case.items():
        if k not in idx["case"]:
            idx["case"][k] = v if not isinstance(v, (dict, list)) else None
    if not idx["case"].get("case_id"):
        idx["assumptions"].append({"item": "case_id", "note": "absent in input; null retained"})
    tm = inp / "task.md"
    if tm.is_file():
        t = tm.read_text("utf-8", "replace")
        idx["task_md"] = {"path": "task.md", "chars": len(t), "sha256": sh(t),
                          "head": [clip(x, 240) for x in t.splitlines() if x.strip()][:12]}
    else:
        idx["degradations"].append({"stage": "init", "note": "task.md absent; scope text unavailable"})

    paths = sorted(q for q in inp.rglob("*") if q.is_file()) if inp.is_dir() else []
    rid = 0
    for p in paths:
        rel = p.relative_to(inp).as_posix()
        if p.name in SKIP or rel.startswith(".") or "__MACOSX" in rel:
            continue
        if p.suffix.lower() not in MAT_EXT:
            continue
        entry = {"path": rel, "bytes": p.stat().st_size, "sha256": sh(read_bytes(p, 8192))}
        try:
            kind, obj, text, lists, note = parse_one(p)
        except Exception as e:
            idx["errors"].append({"stage": "parse", "path": rel, "error": "%s: %s" % (type(e).__name__, e)})
            kind, obj, text, lists, note = "unreadable", None, "", [], str(e)
        shape_db = db_from_obj(obj)[0] if obj is not None else None
        name_db = db_from_name(rel)
        db = name_db or shape_db or "unknown"
        if shape_db and db in ("unknown", "publisher"):
            db = shape_db
        entry.update(kind=kind, shape=(lists[0][0] if lists else ""), note=note, n_records=0,
                     db=db, db_basis=("filename" if name_db else "") + ("+shape:" + shape_db if shape_db else ""))
        if kind in ("text", "pdftext", "html"):
            if text.strip():
                idx["docs"].append({"path": rel, "kind": kind, "chars": len(text), "sha256": sh(text),
                                    "head": [clip(x, 200) for x in text.splitlines()[:6] if x.strip()]})
        if not lists and kind in ("json", "json?", "jsonl", "csv"):
            fail = failure_of(obj, text, 0)
            if fail:
                fail.update(path=rel, db=db)
                idx["failures"].append(fail)
        for path_expr, lst in lists:
            for i, rec in enumerate(lst):
                if not isinstance(rec, dict):
                    continue
                rid += 1
                try:
                    fields = extract(rec, db)
                except Exception as e:
                    idx["degradations"].append({"stage": "normalise", "path": rel, "index": i,
                                                "note": "record skipped: %s" % e})
                    continue
                ptr = "%s[%d]" % (path_expr, i) if path_expr != "$" else "$[%d]" % i
                idx["records"].append(
                    {"rid": "R-%04d" % rid, "db": db, "source_id": rel,
                     "locator": "%s#%s" % (rel, ptr), "ptr": ptr,
                     "raw_id": clip(fields.get("doi", {}).get("value") or
                                    fields.get("pmid", {}).get("value") or "", 60),
                     "raw_sha": sha(cj(rec)), "raw": clip(rec, 300), "fields": fields,
                     "completeness": completeness(fields)})
                entry["n_records"] += 1
        idx["files"].append(entry)
    if not idx["records"]:
        idx["degradations"].append({"stage": "init", "note": "no bibliographic record parsed from any response"})
    for e in idx["files"]:
        if not e["n_records"] and e["db"] not in {f.get("db") for f in idx["failures"]} \
                and e["kind"] in ("json", "jsonl", "csv", "json?"):
            idx.setdefault("empty", []).append({"path": e["path"], "db": e["db"], "kind": e["kind"],
                                                "note": e.get("note") or ""})
            idx["degradations"].append({"stage": "parse", "db": e["db"], "path": e["path"],
                                        "note": "response parsed but no record list recognised"})
    for f in idx["failures"]:
        idx["degradations"].append({"stage": "query", "db": f.get("db"), "path": f.get("path"),
                                    "note": "response unusable: %s" % f.get("reason")})
    return idx


def resolve(rel, ptr, inp):
    """Replay a locator on the original input; return the raw value or None."""
    p = Path(inp) / rel
    if not p.is_file():
        return None
    kind, obj, text, lists, _ = parse_one(p)
    toks = re.findall(r"[^.\[\]]+|\[\d+\]", ptr.lstrip("$").lstrip("."))
    if obj is not None and toks:
        cur = [obj]
        for tok in toks:
            nxt = []
            for c in cur:
                if tok.startswith("["):
                    i = int(tok[1:-1])
                    if isinstance(c, list) and len(c) > i:
                        nxt.append(c[i])
                elif isinstance(c, dict) and tok in c:
                    nxt.append(c[tok])
            cur = nxt
        if cur:
            return cur[0]
    if ptr.startswith("L") and text:
        return {"text": text}
    return obj if isinstance(obj, dict) else None
