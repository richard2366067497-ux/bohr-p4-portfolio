#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger.py :: discovery, reference-set freeze, graded hit matching, ledger CSV (stdlib, offline)."""
import csv
import difflib
import hashlib
import io
import json
import re
from pathlib import Path

V = "1.0.0"
TEXT_EXT = (".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".md", ".txt", ".html", ".htm", ".yaml", ".yml")
MAXC = 400000
MAXPOOL = 6000
MAXWALK = 40000

STOP = set("""a an the of and or in on for to with from by at as is are was were be been being this that these those
we our us their its it not no than then also such can may might show shows shown study studies result results
resulting use used using based between among under over into via per within without versus vs toward towards
review reviews systematic search analysis approach effect effects role new novel high low two three one
""".split())

BOOL = {"and", "or", "not", "near", "adj", "same"}

TITLE_K = ("title", "display_title", "article_title", "primary_title", "ti", "题名", "标题", "标题名")
DOI_K = ("doi", "dois", "identifier_doi", "article_doi")
PMID_K = ("pmid", "pm_id", "pubmed_id")
PMCID_K = ("pmcid", "pmc_id")
YEAR_K = ("year", "pub_year", "publication_year", "published_year", "issued", "published",
          "publication_date", "first_publication_date", "date", "pubyear", "年份", "年")
AUTH_K = ("author", "authors", "authorstring", "author_string", "creator", "creators", "作者")
VENUE_K = ("container_title", "journal", "journal_title", "journaltitle", "venue", "publication",
           "publisher", "source_title", "book_title", "期刊", "来源")
ABS_K = ("abstract", "abstracttext", "abstract_text", "summary", "摘要")
TYPE_K = ("type", "pub_type", "publication_type", "subtype", "genre", "类型")

REFHINT = re.compile(r"ref[_-]?set|reference|known|seed|gold|anchor|include|expert|must[_-]?find|"
                     r"do[_-]?not[_-]?miss|benchmark|参考|专家|必检|纳入|核对", re.I)
RESHINT = re.compile(r"result|hit|search|retriev|snapshot|response|record|pool|candidate|检索|结果|命中", re.I)
QRYHINT = re.compile(r"quer|search[_-]?log|strateg|search[_-]?str|iteration|string|syntax|查询|检索式", re.I)
IMPHINT = re.compile(r"import|incremental|last[_-]?run|upstream|sync|导入|同步", re.I)

DOI_RX = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>()\[\]{},;]+")
PMID_RX = re.compile(r"\bPMID[:\s]*(\d{6,9})\b", re.I)
YEAR_RX = re.compile(r"\b(1[89]\d\d|20\d\d|21\d\d)\b")
WW = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


# --------------------------------------------------------------------- helpers
def sha(s):
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def clip(s, n=200):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def ndoi(s):
    if not isinstance(s, str):
        return ""
    t = s.strip().lower()
    t = re.sub(r"^(https?://(dx\.)?doi\.org/|doi[:\s]+|https?://doi\.org/)", "", t)
    t = t.strip(" .,;:)]}>\"'")
    return t if t.startswith("10.") else ""


def ntitle(s):
    if not isinstance(s, str):
        return ""
    t = re.sub(r"^\s*(retracted|retraction|withdrawn|撤稿)[^:：]{0,20}[:：]\s*", "", s.strip(), flags=re.I)
    t = WW.sub(" ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def toks(s):
    return {w for w in ntitle(s).split() if len(w) > 2 and w not in STOP}


def surname(a):
    """family name from 'Smith J' / 'Smith, J.' / 'J. Smith'."""
    seg = str(a or "").split(",")[0]
    w = ntitle(seg).split()
    if not w:
        return ""
    if len(w) >= 2 and len(w[0]) > 2 and len(w[-1]) <= 2:
        return w[0]
    return w[-1]


def year_of(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 1500 < v < 2200 else None
    if isinstance(v, float):
        return int(v) if 1500 < v < 2200 else None
    if isinstance(v, dict):
        for k in ("date_parts", "date-parts", "value", "year"):
            if k in v:
                r = year_of(v[k])
                if r:
                    return r
        return None
    if isinstance(v, list):
        for x in v:
            r = year_of(x)
            if r:
                return r
        return None
    if isinstance(v, str):
        m = YEAR_RX.search(v)
        return int(m.group(1)) if m else None
    return None


def _flat(v, depth=0):
    """coerce list/dict/scalar to a short display string"""
    if v is None or depth > 3:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, list):
        for x in v:
            s = _flat(x, depth + 1)
            if s:
                return s
        return ""
    if isinstance(v, dict):
        for k in ("value", "title", "name", "family", "text", "string"):
            if k in v:
                s = _flat(v[k], depth + 1)
                if s:
                    return s
    return ""


def getk(d, names):
    low = {}
    for k, v in d.items():
        if isinstance(k, str):
            low[k.lower().replace("-", "_").replace(" ", "_")] = v
    for n in names:
        if n in low:
            s = _flat(low[n])
            if s:
                return s
    return ""


def locate(lines, needles):
    """1-based line of the first line containing any needle (longest probe first)."""
    cands = sorted([n for n in needles if n], key=len, reverse=True)
    for n in cands[:4]:
        probe = n if len(n) <= 120 else n[:120]
        for i, line in enumerate(lines):
            if probe in line:
                return i + 1
    return 0


# ---------------------------------------------------------------- case + docs
def salvage_case(text):
    """recover case_id / output_contract key names from a truncated or unparsable case.json."""
    o = {}
    m = re.search(r'"case_?id"\s*:\s*"([^"]{1,120})"', text, re.I)
    if m:
        o["case_id"] = m.group(1)
    m = re.search(r'"output_contract"\s*:\s*\{', text)
    if m:
        i, depth = m.end(), 1
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        keys = re.findall(r'"([^"]{1,60})"\s*:', text[m.end():i])
        if keys:
            o["output_contract"] = {k: None for k in keys}
    return o or None


def find_case(inp, notes):
    if not inp.is_dir():
        notes.append({"stage": "case", "error": "input dir missing: %s" % inp})
        return None, None
    p = inp / "case.json"
    if p.is_file():
        o = load_json(p, notes)
        if o is None:
            o = salvage_case(p.read_text("utf-8", "replace"))
            if o:
                notes.append({"stage": "case", "note": "case.json 解析失败，已按原文抢救字段 %s" % sorted(o)})
        return p, o
    for q in sorted(inp.rglob("case*.json")):
        o = load_json(q, notes)
        if isinstance(o, dict) and ("case_id" in o or "output_contract" in o):
            return q, o
    alt = sorted(q for q in inp.rglob("*.json") if "manifest" not in q.name.lower())
    for q in alt[:6]:
        o = load_json(q, notes)
        if isinstance(o, dict) and "case_id" in o:
            notes.append({"stage": "case", "note": "case.json fallback -> %s" % q.name})
            return q, o
    notes.append({"stage": "case", "error": "no case.json under input"})
    return None, None


def load_json(p, notes=None):
    try:
        return json.loads(Path(p).read_text("utf-8", "replace"))
    except Exception as e:
        if notes is not None:
            notes.append({"stage": "parse", "file": str(getattr(p, "name", p)), "error": "%s: %s" % (type(e).__name__, e)})
        return None


def read_doc(p, notes):
    """text of one material file; PDF/DOCX via light-weight stdlib extraction."""
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            import zlib
            data = p.read_bytes()
            out = []
            for m in re.finditer(rb"stream\r?\n", data):
                e = data.find(b"endstream", m.end())
                if e < 0:
                    continue
                raw = data[m.end():e]
                try:
                    raw = zlib.decompress(raw)
                except Exception:
                    pass
                if b"Tj" in raw or b"TJ" in raw:
                    out.append(b" ".join(x.group(0)[1:-1] for x in re.finditer(rb"\([^)]{2,}\)", raw)).decode("latin-1", "replace"))
            t = "\n".join(x.strip() for x in out if x.strip())
            if len(t) < 400:
                notes.append({"stage": "read", "file": p.name, "note": "PDF text layer thin/absent; no OCR used"})
            return t
        if ext == ".docx":
            import zipfile
            with zipfile.ZipFile(p) as z:
                x = z.read("word/document.xml").decode("utf-8", "replace")
            x = re.sub(r"</w:p>", "\n", x)
            return re.sub(r"<[^>]+>", "", x)
        t = p.read_text("utf-8", "replace")
        if ext in (".html", ".htm"):
            t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
            t = re.sub(r"<[^>]+>", "\n", t)
        return t
    except Exception as e:
        notes.append({"stage": "read", "file": p.name, "error": "%s: %s" % (type(e).__name__, e)})
        return ""


def discover(inp, notes):
    docs = []
    if not inp.is_dir():
        return docs
    skip = {"case.json", "resources.yaml", "public-manifest.json", "result.json"}
    for i, p in enumerate(sorted(q for q in inp.rglob("*") if q.is_file()), 1):
        if p.suffix.lower() not in TEXT_EXT or p.name in skip:
            continue
        if any(part in ("__pycache__", ".git") for part in p.parts):
            continue
        t = read_doc(p, notes)
        if len(t) > MAXC:
            notes.append({"stage": "read", "file": p.name, "note": "truncated at %d chars" % MAXC})
            t = t[:MAXC]
        docs.append({"doc_id": "src-%02d" % i, "path": p.relative_to(inp).as_posix(), "name": p.name,
                     "ext": p.suffix.lower(), "text": t, "lines": t.splitlines(), "sha256": sha(t),
                     "chars": len(t)})
    return docs


# --------------------------------------------------------------- record layer
def walk(node, ptr="", anc=(), out=None, depth=0, budget=None):
    """yield (node, ptr, ancestor_keys). Bounded."""
    out = [] if out is None else out
    budget = [MAXWALK] if budget is None else budget
    if depth > 14 or budget[0] <= 0:
        return out
    budget[0] -= 1
    if isinstance(node, dict):
        out.append((node, ptr, anc))
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                walk(v, "%s/%s" % (ptr, k), anc + (str(k),), out, depth + 1, budget)
    elif isinstance(node, list):
        for j, v in enumerate(node):
            if isinstance(v, (dict, list)):
                walk(v, "%s/%d" % (ptr, j), anc, out, depth + 1, budget)
    return out


def rec_of(d):
    """bibliographic view of a dict, or None when it is not a paper-like record."""
    if not isinstance(d, dict):
        return None
    title = getk(d, TITLE_K)
    if len(title) < 8:
        return None
    doi = ndoi(getk(d, DOI_K))
    if not doi:
        for v in d.values():
            if isinstance(v, str):
                m = DOI_RX.search(v)
                if m:
                    doi = ndoi(m.group(0))
                    break
    pmid = re.sub(r"\D", "", getk(d, PMID_K))
    if not pmid:
        for k, v in d.items():
            if isinstance(v, str) and re.search(r"pmid|pm_id", str(k), re.I):
                pmid = re.sub(r"\D", "", v)
    auth = getk(d, AUTH_K)
    if not auth:
        a = d.get("author") or d.get("authors")
        if isinstance(a, list):
            parts = []
            for x in a[:4]:
                if isinstance(x, dict):
                    parts.append(_flat(x.get("family") or x)) 
                else:
                    parts.append(_flat(x))
            auth = ", ".join([p for p in parts if p])
    yr = year_of(d.get("year"))
    if not yr:
        for kk, vv in d.items():
            if isinstance(kk, str) and kk.lower().replace("-", "_") in YEAR_K:
                yr = year_of(vv)
                if yr:
                    break
    venue = getk(d, VENUE_K)
    absr = getk(d, ABS_K)
    typ = getk(d, TYPE_K)
    return {"title": title, "ntitle": ntitle(title), "doi": doi, "pmid": pmid,
            "year": yr, "author": auth, "first_author": surname(auth.split(",")[0]) if auth else "",
            "venue": venue, "abstract": absr, "type": typ, "raw": d}


def flagged(rec):
    """usability flags read off the record itself."""
    blob = " ".join(str(rec.get(k) or "") for k in ("title", "type", "abstract", "venue")).lower()
    flags = []
    if re.search(r"retract|withdraw|撤稿|表达关注|expression of concern", blob):
        flags.append("retracted")
    if re.search(r"no full ?text|full ?text (not )?available|无法获取全文|无全文|only abstract", blob):
        flags.append("no_fulltext")
    if not rec.get("year"):
        flags.append("meta_incomplete")
    return flags


def doc_records(doc, notes):
    """all records in one document, each with a verbatim locator."""
    recs = []
    ext = doc["ext"]
    if ext in (".json",):
        try:
            obj = json.loads(doc["text"])
        except Exception:
            notes.append({"stage": "parse", "file": doc["path"], "note": "bad json; falling back to text scan"})
            obj = None
        if obj is not None:
            for node, ptr, anc in walk(obj):
                rec = rec_of(node)
                if not rec:
                    continue
                needles = [rec["doi"], rec["title"][:90]]
                ln = locate(doc["lines"], needles)
                rec.update(doc_id=doc["doc_id"], path=doc["path"], ptr=ptr,
                           anc=" ".join(anc[-4:]), container=container_of(anc, doc["path"]),
                           locator="%s:L%d" % (doc["doc_id"], ln) if ln else "%s:%s" % (doc["doc_id"], ptr),
                           quote=clip(doc["lines"][ln - 1], 220) if ln else clip(rec["title"], 220),
                           verbatim=bool(ln), line=ln)
                recs.append(rec)
            return recs
    if ext in (".jsonl", ".ndjson"):
        for i, line in enumerate(doc["lines"], 1):
            if not line.strip().startswith("{"):
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            rec = rec_of(o) if isinstance(o, dict) else None
            if rec:
                rec.update(doc_id=doc["doc_id"], path=doc["path"], ptr="/%d" % (i - 1), anc="",
                           container=container_of((), doc["path"]),
                           locator="%s:L%d" % (doc["doc_id"], i), quote=clip(line, 220),
                           verbatim=True, line=i)
                recs.append(rec)
        return recs
    if ext in (".csv", ".tsv"):
        sep = "\t" if ext == ".tsv" else ","
        try:
            rows = list(csv.reader(io.StringIO(doc["text"]), delimiter=sep))
        except Exception:
            rows = []
        if len(rows) >= 2 and any(len(r) > 1 for r in rows):
            head = [h.strip().lower().replace(" ", "_") for h in rows[0]]
            idx = {}
            for j, h in enumerate(head):
                for nm, keys in (("title", TITLE_K), ("doi", DOI_K), ("year", ("year", "pub_year", "publication_year")),
                                 ("author", AUTH_K), ("venue", ("journal", "venue", "container_title", "source")),
                                 ("pmid", PMID_K), ("type", TYPE_K)):
                    if nm not in idx and h in keys:
                        idx[nm] = j
            if "title" in idx:
                for i, r in enumerate(rows[1:], 2):
                    if len(r) <= idx["title"]:
                        continue
                    d = {nm: (r[j] if j < len(r) else "") for nm, j in idx.items()}
                    d.setdefault("title", r[idx["title"]])
                    rec = rec_of(d)
                    if rec:
                        rec.update(doc_id=doc["doc_id"], path=doc["path"], ptr="/row%d" % (i - 2), anc="",
                                   container=container_of((), doc["path"]),
                                   locator="%s:L%d" % (doc["doc_id"], i), quote=clip(r[idx["title"]], 220),
                                   verbatim=True, line=i)
                        recs.append(rec)
                return recs
    # markdown / txt fallback: DOI-bearing or numbered citation lines
    is_ref = bool(REFHINT.search(doc["path"]))
    for i, line in enumerate(doc["lines"], 1):
        s = line.strip()
        if len(s) < 24:
            continue
        m, yr = DOI_RX.search(s), YEAR_RX.search(s)
        if not (yr and (m or re.match(r"^(\d{1,3}[.)]|[-*]|\|)\s*", s))):
            continue
        if "|" in s:
            cells = [c.strip() for c in s.strip("|").split("|") if c.strip() and not set(c.strip()) <= set("-: ")]
            title = max(cells, key=len) if cells else s
        else:
            title = re.sub(r"^(\d{1,3}[.)]|[-*]|\|)\s*", "", s)
        rec = rec_of({"title": title[:300], "doi": m.group(0) if m else "", "year": yr.group(1)})
        if not rec:
            continue
        rec.update(doc_id=doc["doc_id"], path=doc["path"], ptr="/L%d" % i,
                   anc="refdoc" if is_ref else "", container=container_of((), doc["path"]),
                   locator="%s:L%d" % (doc["doc_id"], i), quote=clip(s, 220), verbatim=True, line=i)
        recs.append(rec)
    return recs


def container_of(anc, path):
    a, p = " ".join(anc).lower(), str(path).lower()
    for key, name in (("items", "crossref"), ("resultlist", "europepmc"), ("pubmed", "pubmed"),
                      ("openalex", "openalex"), ("semantic", "semanticscholar")):
        if key in a or key in p:
            return name
    return "local"


# ------------------------------------------------------------ collections
def is_refctx(r):
    """record belongs to a reference-set / known-relevant container (never a search result)."""
    return bool(REFHINT.search((r.get("anc") or "") + " " + (r.get("path") or "")))


def split_records(docs, notes):
    """parse each doc once -> (retrieval pool, reference-set records).

    Ref-set containers never enter the pool: self-matching a reference would push coverage
    towards 1.0, the "denominator defined by the results" failure mode this skill prevents.
    """
    pool, refrecs, seen = [], [], set()
    for d in docs:
        for r in doc_records(d, notes):
            if is_refctx(r):
                refrecs.append(r)
                continue
            key = r["doi"] or ("T:" + r["ntitle"])
            if key in seen:
                continue
            seen.add(key)
            r["pool_id"] = "P-%04d" % (len(pool) + 1)
            r["flags"] = flagged(r)
            r["also_in"] = []
            pool.append(r)
            if len(pool) >= MAXPOOL:
                notes.append({"stage": "pool", "note": "pool capped at %d records" % MAXPOOL})
                return pool, refrecs
    return pool, refrecs


def collect_refs(refrecs, case, notes):
    """frozen reference set: hinted containers + explicit case.json lists."""
    cand, origin = [], []

    def take(rec, why):
        if rec:
            rr = dict(rec)
            rr["_origin"] = why
            cand.append(rr)

    if isinstance(case, dict):
        for k, v in case.items():
            if not (isinstance(v, list) and v and isinstance(v[0], (dict, str))):
                continue
            if REFHINT.search(str(k)):
                for x in v:
                    if isinstance(x, dict):
                        take(rec_of(x), "case.json:%s" % k)
                    elif isinstance(x, str):
                        m = DOI_RX.search(x)
                        take(rec_of({"title": x, "doi": m.group(0) if m else "",
                                     "year": (YEAR_RX.search(x).group(1) if YEAR_RX.search(x) else "")}),
                             "case.json:%s" % k)

    for r in refrecs:
        take(r, "%s:%s" % (r.get("path"), r.get("ptr") or r.get("locator")))
    if not cand and isinstance(case, dict):
        for k, v in case.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                recs = [rec_of(x) for x in v]
                recs = [x for x in recs if x]
                if recs and len(recs) >= 2:
                    for x in recs:
                        take(x, "case.json:%s" % k)
                    notes.append({"stage": "refs", "note": "reference set inferred from case.json:%s" % k})
                    break

    # normalise, dedup, flag
    out, seen, order = [], {}, []
    for r in cand:
        ref = {k: r.get(k) for k in ("title", "ntitle", "doi", "pmid", "year", "author", "first_author",
                                     "venue", "abstract", "type", "doc_id", "path", "locator", "quote", "verbatim")}
        ref.setdefault("ntitle", ntitle(ref.get("title") or ""))
        if not ref.get("ntitle"):
            continue
        flags = flagged(ref) if ref.get("title") else []
        key = ref["doi"] or ("T:" + ref["ntitle"])
        if key in seen:
            seen[key]["dups"].append({"locator": ref.get("locator"), "title": clip(ref.get("title"), 90),
                                      "doi": ref.get("doi") or None})
            continue
        ref["flags"] = flags
        ref["dups"] = []
        ref["origin"] = r.get("_origin")
        seen[key] = ref
        order.append(ref)
    for i, ref in enumerate(order, 1):
        ref["ref_id"] = "R-%03d" % i
        ref["usable"] = "retracted" not in ref["flags"]
        ref["usability_reason"] = ("; ".join(ref["flags"]) if ref["flags"] else "usable")
    return order


def collect_queries(docs, notes):
    qs = []
    for d in docs:
        if d["ext"] not in (".json", ".jsonl", ".ndjson") and not QRYHINT.search(d["path"]):
            continue
        nodes = []
        if d["ext"] == ".json":
            try:
                obj = json.loads(d["text"])
            except Exception:
                obj = None
            if obj is not None:
                nodes = [(n, p, a) for n, p, a in walk(obj) if isinstance(n, dict)]
        for node, ptr, anc in nodes:
            if not isinstance(node, dict):
                continue
            q = ""
            for k, v in node.items():
                if isinstance(v, str) and re.search(r"^(query|q|query_string|querystring|term|terms|expression|strategy|search_string|searchstr|syntax|检索式|查询式)$", str(k), re.I):
                    q = v.strip()
                    break
            if len(q) < 3:
                continue
            fields = ""
            for k, v in node.items():
                if re.search(r"field|字段", str(k), re.I):
                    fields = _flat(v)
                    break
            src, w0, w1, it = "", None, None, ""
            for k, v in node.items():
                kl = str(k).lower()
                if re.search(r"source|database|provider|platform|来源|库", kl) and not src:
                    src = _flat(v)
                elif re.search(r"(from|start|begin|date_from|lower)", kl) and w0 is None:
                    w0 = year_of(v)
                elif re.search(r"(to|end|until|date_to|upper)", kl) and w1 is None:
                    w1 = year_of(v)
                elif re.search(r"iter|round|step|stage|轮", kl) and not it:
                    it = _flat(v)
            ln = locate(d["lines"], [q[:110]])
            if not ln:
                for i, line in enumerate(d["lines"], 1):
                    s = clip(q, 50)
                    if s and s in line:
                        ln = i
                        break
            qs.append({"q_id": "Q-%03d" % (len(qs) + 1), "query": q, "fields": fields,
                       "source": src, "year_from": w0, "year_to": w1, "iteration": it,
                       "doc_id": d["doc_id"], "path": d["path"], "ptr": ptr,
                       "locator": "%s:L%d" % (d["doc_id"], ln) if ln else "%s:%s" % (d["doc_id"], ptr),
                       "quote": clip(d["lines"][ln - 1], 220) if ln else clip(q, 220),
                       "verbatim": bool(ln), "container": "query_log"})
            if len(qs) >= 400:
                return qs
    return qs


def collect_imports(docs, notes):
    """organizer-local incremental import states (source-completeness hints, never a denominator)."""
    out = []
    for d in docs:
        if d["ext"] != ".json":
            continue
        try:
            obj = json.loads(d["text"])
        except Exception:
            continue
        for node, ptr, anc in walk(obj):
            if not isinstance(node, dict) or len(node) > 24:
                continue
            vals = {k: clip(_flat(v), 80) for k, v in node.items()
                    if isinstance(v, (str, int, float, bool)) and IMPHINT.search(str(k))}
            if not vals:
                continue
            ln = locate(d["lines"], [str(v) for v in list(vals.values())[:2]])
            out.append({"source": d["path"], "ptr": ptr, "values": vals,
                        "locator": "%s:L%d" % (d["doc_id"], ln) if ln else "%s:%s" % (d["doc_id"], ptr)})
            if len(out) >= 40:
                return out
    return out


def token_index(pool):
    """inverted title-token index with a hot-token list to keep matching linear-ish."""
    inv, df = {}, {}
    for i, p in enumerate(pool):
        for t in toks(p["title"]):
            inv.setdefault(t, set()).add(i)
            df[t] = df.get(t, 0) + 1
    hot = {t for t, c in df.items() if len(pool) and c > max(8, len(pool) * 0.25)}
    return inv, hot


def match_ref(ref, pool, inv, hot, thr=(0.92, 0.80)):
    """L1 identifier -> L2 bibliographic -> L3 borderline -> miss."""
    hi, lo = thr
    if ref.get("doi"):
        for i, p in enumerate(pool):
            if p.get("doi") and p["doi"] == ref["doi"]:
                return dict(pool_id=p["pool_id"], rule="id_doi", certainty="high", similarity=1.0,
                            locator=p["locator"], doc_id=p["doc_id"], quote=p["quote"], rival=[])
    if ref.get("pmid"):
        for p in pool:
            if p.get("pmid") and p["pmid"] == ref["pmid"]:
                return dict(pool_id=p["pool_id"], rule="id_pmid", certainty="high", similarity=1.0,
                            locator=p["locator"], doc_id=p["doc_id"], quote=p["quote"], rival=[])
    rt = toks(ref.get("title") or "")
    cands = set()
    for t in rt:
        if t in hot:
            continue
        cands |= inv.get(t, set())
    if not cands and len(pool) <= 800:
        cands = set(range(len(pool)))
    best, rivals = None, []
    for i in cands:
        p = pool[i]
        pt = toks(p["title"])
        inter = len(rt & pt)
        if inter < 2 and len(rt) > 3:
            continue
        sim = difflib.SequenceMatcher(None, ref.get("ntitle") or "", p["ntitle"]).ratio()
        inst = dict(pool_id=p["pool_id"], sim=sim, idx=i)
        if sim >= lo:
            rivals.append(inst)
        if best is None or sim > best["sim"]:
            best = inst
    if not best or best["sim"] < lo:
        return dict(pool_id=None, rule="none", certainty="high", similarity=round(best["sim"], 4) if best else 0.0,
                    locator=None, doc_id=None, quote=None, rival=[])
    p = pool[best["idx"]]
    auth_hit = bool(ref.get("first_author")) and ref["first_author"] != "" and ref["first_author"] == p.get("first_author")
    yr_ok = bool(ref.get("year")) and bool(p.get("year")) and abs(ref["year"] - p["year"]) <= 1
    if best["sim"] >= hi and (auth_hit or yr_ok):
        rule = "bib_title_author_year" if auth_hit else "bib_title_year"
        cert = "high" if best["sim"] >= 0.97 else "medium"
    elif best["sim"] >= hi:
        rule, cert = "bib_title_author_year", "medium"
    else:
        rule, cert = "bib_borderline", "low"
    rival = sorted([r for r in rivals if r["pool_id"] != p["pool_id"]], key=lambda x: -x["sim"])[:2]
    return dict(pool_id=p["pool_id"], rule=rule, certainty=cert, similarity=round(best["sim"], 4),
                locator=p["locator"], doc_id=p["doc_id"], quote=p["quote"],
                rival=[dict(pool_id=r["pool_id"], similarity=round(r["sim"], 4)) for r in rival])


def fingerprint(refs):
    parts = ["%s|%s|%s" % (r["ref_id"], r.get("doi") or "", r.get("ntitle") or "") for r in refs]
    return sha("\n".join(parts))[:16]


# --------------------------------------------------------------------- output
LEDGER_COLS = ["ref_id", "title", "doi", "year", "first_author", "usable", "usability_reason", "hit_status",
               "matched_id", "match_rule", "certainty", "evidence_locator", "evidence_quote",
               "decision_source", "needs_human"]
MATRIX_COLS = ["ref_id", "title", "primary_category", "co_factors", "why", "fixability",
               "affected_query_ids", "action", "evidence_locator"]


def wcsv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})


def rcsv(path):
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []
