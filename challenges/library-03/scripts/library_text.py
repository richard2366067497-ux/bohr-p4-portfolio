"""library-curator text & metadata layer (stdlib only).

Bounded file reading, text-layer probing (PDF content streams via zlib, DOCX/XLSX via zip),
companion-table parsing (CSV/TSV/JSON/BibTeX) and metadata candidates that always carry a
locator. Nothing here guesses: a field without evidence is not emitted.
"""

import csv
import datetime
import difflib
import hashlib
import io
import json
import os
import re
import unicodedata
import zipfile
import zlib

TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".bib", ".yml", ".yaml",
            ".xml", ".html", ".tex", ".log"}
TABLE_EXT = {".csv", ".tsv", ".json", ".jsonl", ".bib"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
DOC_TEXT_EXT = {".pdf", ".docx", ".tex", ".html", ".xml", ".rtf"}

STOP = set("""a an the of in on for and or to with by from at as is are was were be been this that these those
we our it its their they them than then which where when what how not no nor but if into over under between among
per using used use also both all any each other such more most less least can may might will would should could do
does did study studies results result new via towards toward based analysis approach method methods review effect
effects high low novel""".split())

FOLD = (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2010", "-"),
        ("\u2011", "-"), ("\u2012", "-"), ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"),
        ("\u00a0", " "), ("\u200b", ""), ("\ufeff", ""))

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:<>A-Za-z0-9]+")
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
JOURNAL_HINT = re.compile(r"(journal of|letters|proceedings of|nature|science|cell|reviews|reports|"
                          r"bulletin|annals|frontiers in|plos|elife|pnas|acs |rsc |wiley|elsevier|springer)", re.I)
HEADER_NOISE = re.compile(r"^(doi|https?:|www\.|vol\.?|volume|issue|issn|isbn|copyright|©|received|accepted|"
                          r"published|available online|contents lists|article|research article|abstract|keywords?|"
                          r"introduction|summary|highlights)", re.I)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in FOLD:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def norm_keep(s):
    """Normalise each line but keep the line structure (needed for title/author heuristics)."""
    return "\n".join(x for x in (norm(p) for p in (s or "").split("\n")) if x)


def norm_key(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (s or "").lower())


def words(s):
    return re.findall(r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff\-]{1,}", s or "")


def hit_level(quote, text):
    """exact | normalized | keyspace | fuzzy | none — the evidence gate used by check/build."""
    q, t = (quote or "").strip(), text or ""
    if not q or not t:
        return "none"
    if q in t:
        return "exact"
    nq, nt = norm(q), norm(t)
    if nq and nq in nt:
        return "normalized"
    if norm_key(nq) and norm_key(nq) in norm_key(nt):
        return "keyspace"
    if len(nq) > 24:
        m = difflib.SequenceMatcher(None, nq[:400], nt[:20000]).find_longest_match(
            0, min(len(nq), 400), 0, min(len(nt), 20000))
        if m.size >= max(24, int(0.75 * min(len(nq), 400))):
            return "fuzzy"
    return "none"


def decode(b):
    for enc in ("utf-8", "utf-8-sig", "gb18030", "big5", "latin-1"):
        try:
            return b.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", "replace"), "replace"


def read_bytes(p, cap=8 * 1024 * 1024):
    with open(p, "rb") as fh:
        return fh.read(cap)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def iso(ts):
    try:
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


# ------------------------------------------------------------------ document text
_STR = re.compile(rb"\((?:\\.|[^\\()])*\)")
_OCT = re.compile(rb"\\([0-7]{1,3})")


def _pdf_strings(data):
    """Text of one content stream; T*/Td/TD operators become line breaks."""
    out = []
    tok = re.compile(_STR.pattern + b"|T[*]|T[D]|T[d]")
    for block in re.finditer(rb"BT(.*?)ET", data, re.S):
        for m in tok.finditer(block.group(1)):
            s = m.group(0)
            if s.startswith(b"("):
                raw = _OCT.sub(lambda x: bytes([int(x.group(1), 8) & 0xFF]), s[1:-1])
                raw = re.sub(rb"\\([nrtbf()\\])", b" ", raw)
                txt = raw.decode("latin-1", "replace")
                if txt.strip():
                    out.append(txt)
            elif out and not out[-1].endswith("\n"):
                out.append("\n")
    return "".join(out)


def pdf_pages(p):
    flags = []
    try:
        b = read_bytes(p, 16 * 1024 * 1024)
    except OSError:
        return [], "corrupt", ["unreadable"]
    if b"%PDF" not in b[:4096]:
        return [], "corrupt", ["no_pdf_header"]
    if b"/Encrypt" in b:
        flags.append("encrypted")
    pages, streams, imgs = [], 0, b"/Image" in b
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", b, re.S):
        streams += 1
        data, raw = None, m.group(1)
        for cand in (raw, raw.rstrip(b"\r\n")):
            try:
                data = zlib.decompress(cand)
                break
            except zlib.error:
                continue
        if data is None:
            continue
        txt = _pdf_strings(data)
        if len(txt.strip()) >= 3:
            pages.append(norm_keep(txt)[:4000])
    text = " ".join(pages)
    if not text.strip():
        if "encrypted" in flags:
            return [], "encrypted", flags
        return [], ("no_text_layer" if (imgs or streams) else "corrupt"), flags + ["empty_streams"]
    quality = "usable" if len(text) >= 200 else "low"
    if imgs and len(text) < 200:
        flags.append("image_present_low_text")
    return pages, quality, flags


def docx_pages(p):
    try:
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return [], "corrupt", ["docx_unreadable"]
    xml = re.sub(r"</w:p>", "\n", xml)
    txt = re.sub(r"<[^>]+>", " ", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        txt = txt.replace(a, b)
    txt = norm_keep(txt)
    return ([txt[:6000]] if txt else []), ("usable" if len(txt) > 200 else "low"), []


def xlsx_lines(p):
    try:
        with zipfile.ZipFile(p) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                sx = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
                shared = [norm(re.sub(r"<[^>]+>", "", m)) for m in re.findall(r"<si>(.*?)</si>", sx, re.S)]
            sheet = ""
            for n in z.namelist():
                if n.startswith("xl/worksheets/sheet"):
                    sheet = z.read(n).decode("utf-8", "replace")
                    break
    except Exception:
        return [], "corrupt", ["xlsx_unreadable"]
    lines = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        cells = []
        for typ, body in re.findall(r"<c[^>]*?(?:t=\"(\w+)\")?[^>]*>(.*?)</c>", row, re.S):
            v = re.search(r"<v>(.*?)</v>", body, re.S)
            val = v.group(1) if v else norm(re.sub(r"<[^>]+>", "", body))
            if typ == "s" and val.isdigit() and int(val) < len(shared):
                val = shared[int(val)]
            cells.append(norm(val))
        if any(cells):
            lines.append("\t".join(cells))
    return lines, ("usable" if lines else "low"), []


def pages_of(p):
    """-> (pages, text_quality, flags). text_quality: usable|low|no_text_layer|encrypted|corrupt|unreadable_encoding|unsupported_type."""
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            return pdf_pages(p)
        if ext == ".docx":
            return docx_pages(p)
        if ext in (".xlsx", ".xlsm"):
            lines, q, f = xlsx_lines(p)
            return ["\n".join(lines[:2000])], q, f
        if ext in TEXT_EXT:
            txt, enc = decode(read_bytes(p, 4 * 1024 * 1024))
            if enc in ("replace", "latin-1") and re.search(r"[\x80-\x9f]{3,}", txt[:800] or ""):
                return [], "unreadable_encoding", ["encoding_uncertain"]
            txt = txt.replace("\r\n", "\n").replace("\r", "\n")
            return [txt[:20000]], ("usable" if len(txt) > 100 else "low"), []
    except OSError:
        return [], "corrupt", ["unreadable"]
    except Exception as e:
        return [], "corrupt", ["parse_error:%s" % type(e).__name__]
    if ext in IMG_EXT:
        return [], "no_text_layer", ["image_no_text_layer"]
    return [], "unsupported_type", ["binary_or_unsupported"]


# ------------------------------------------------------------------ metadata candidates
def article_noise(line):
    return bool(HEADER_NOISE.match(line.strip())) or len(line.strip()) < 8


def meta_from_filename(name):
    stem = os.path.splitext(name)[0]
    out = {}
    years = YEAR_RE.findall(stem)
    if years:
        out["year"] = {"value": years[-1], "confidence": "low", "locator": "file:"}
    m = DOI_RE.search(stem)
    if m:
        out["doi"] = {"value": m.group(0).rstrip(".,;"), "confidence": "low", "locator": "file:"}
    m = re.match(r"^([A-Z][A-Za-z\-']{1,20})(?:[_ ,]+(?:et al\.?)?)?", stem)
    if m and not re.match(r"^(the|a|an|new|on|toward)", m.group(1), re.I):
        out["first_author"] = {"value": m.group(1), "confidence": "low", "locator": "file:"}
    arx = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", stem)
    if arx:
        out["arxiv_id"] = {"value": arx.group(1) + (arx.group(2) or ""), "confidence": "low", "locator": "file:"}
    return out


def meta_from_text(text):
    out = {}
    head = text[:4000]
    m = DOI_RE.search(head)
    if m:
        out["doi"] = {"value": m.group(0).rstrip(".,;)>"), "confidence": "high", "locator": "p1"}
    ym = re.search(r"(©|\(c\)|copyright|received|accepted|published|online)[^\d]{0,25}((19|20)\d{2})", head, re.I)
    if ym:
        out["year"] = {"value": ym.group(2), "confidence": "medium", "locator": "p1"}
    elif YEAR_RE.search(head):
        out["year"] = {"value": YEAR_RE.findall(head)[0], "confidence": "low", "locator": "p1"}
    lines = [l.strip() for l in text[:2500].split("\n") if l.strip()]
    cand = [l for l in lines[:16] if 15 <= len(l) <= 300 and not article_noise(l)
            and not JOURNAL_HINT.search(l) and len(words(l)) >= 3]
    if cand:
        title = max(cand[:6], key=len)
        out["title"] = {"value": title[:300], "confidence": "medium", "locator": "p1", "quote": title[:300]}
        idx = lines.index(title) if title in lines else -1
        if idx >= 0:
            for l in lines[idx:idx + 4]:
                if 10 <= len(l) <= 300 and l.count(",") >= 1 and len(words(l)) >= 3 and not article_noise(l):
                    out["authors"] = {"value": l[:300], "confidence": "low", "locator": "p1", "quote": l[:300]}
                    break
    for l in lines[:30]:
        if JOURNAL_HINT.search(l) and 8 <= len(l) <= 160 and not article_noise(l):
            out["journal"] = {"value": l[:160], "confidence": "medium", "locator": "p1", "quote": l[:160]}
            break
    return out


def meta_from_pdfinfo(p):
    out = {}
    try:
        b = read_bytes(p, 2 * 1024 * 1024)
    except OSError:
        return out
    for key, field in ((rb"/Title", "title"), (rb"/Author", "authors"),
                       (rb"/Subject", "journal"), (rb"/CreationDate", "year")):
        m = re.search(key + rb"\s*\((?:\\.|[^\\()])*\)", b)
        if not m:
            continue
        txt = norm(_OCT.sub(lambda x: b" ", m.group(0)[len(key):].strip()[1:-1]).decode("latin-1", "replace"))
        if not txt:
            continue
        if field == "year":
            y = YEAR_RE.search(txt)
            if y:
                out["year"] = {"value": y.group(1), "confidence": "medium", "locator": "meta:pdfinfo"}
        elif len(txt) >= 4:
            out[field] = {"value": txt[:300], "confidence": "high", "locator": "meta:pdfinfo"}
    xmp = re.search(rb"<dc:title>(.*?)</dc:title>", b, re.S)
    if xmp and "title" not in out:
        title = norm(re.sub(r"<[^>]+>", " ", xmp.group(1).decode("utf-8", "replace")))
        if title:
            out["title"] = {"value": title[:300], "confidence": "high", "locator": "meta:xmp"}
    return out


def parse_table(p):
    """Companion metadata tables (csv/tsv/json/jsonl/bib) -> list of normalised rows."""
    ext = p.suffix.lower()
    rows = []
    try:
        if ext in (".csv", ".tsv"):
            text, _ = decode(read_bytes(p, 2 * 1024 * 1024))
            rdr = list(csv.reader(io.StringIO(text), delimiter=("\t" if ext == ".tsv" else ",")))
            if len(rdr) >= 2:
                head = [norm(h).lower() for h in rdr[0]]
                for r in rdr[1:]:
                    if any(c.strip() for c in r):
                        rows.append({head[i] if i < len(head) else "c%d" % i: r[i] for i in range(len(r))})
        elif ext == ".bib":
            text, _ = decode(read_bytes(p, 2 * 1024 * 1024))
            for m in re.finditer(r"@\w+\s*\{[^,]*,(.*?)\n\}", text, re.S):
                row = {}
                for f in re.finditer(r"(\w+)\s*=\s*[{\"](.*?)[}\"],?\s*\n", m.group(1), re.S):
                    row[f.group(1).lower()] = norm(f.group(2))
                if row:
                    rows.append(row)
        elif ext in (".json", ".jsonl"):
            data, _ = decode(read_bytes(p, 2 * 1024 * 1024))
            obj = json.loads(data) if ext == ".json" else [json.loads(l) for l in data.splitlines() if l.strip()]
            seq = obj if isinstance(obj, list) else [obj]
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, list):
                        seq = v
                        break
            for r in seq:
                if isinstance(r, dict):
                    rows.append({norm(str(k)).lower(): (norm(v) if isinstance(v, str)
                                                         else json.dumps(v, ensure_ascii=False))
                                 for k, v in r.items() if not isinstance(v, (dict, list))})
    except Exception:
        return []
    return rows


def merge_meta(rec, extra, locator_base=None):
    for field, val in (extra or {}).items():
        if not isinstance(val, dict) or not val.get("value"):
            continue
        prio = {"high": 3, "medium": 2, "low": 1}
        cur = rec["meta"].get(field)
        if cur is not None and prio.get(val.get("confidence", "low"), 1) <= prio.get(cur.get("confidence", "low"), 1):
            continue
        new = dict(val)
        loc = new.get("locator") or "file:"
        if locator_base and loc in ("file:", "p1", "meta:pdfinfo", "meta:xmp"):
            loc = locator_base
        new["locator"] = loc
        rec["meta"][field] = new


def enrich(rec):
    """Fill rec['meta'] from PDF info/XMP -> page-1 text -> file name, each with a locator."""
    if rec["ext"] == ".pdf":
        merge_meta(rec, meta_from_pdfinfo(rec["abs"]))
    text = "\n".join(rec.get("pages") or [])
    if text.strip() and rec["ext"] in DOC_TEXT_EXT:
        merge_meta(rec, meta_from_text(text), "text:%s#p1" % rec["rel"])
    merge_meta(rec, meta_from_filename(rec["name"]), "file:%s" % rec["rel"])
    for k, v in rec["meta"].items():
        if v.get("locator") == "file:":
            v["locator"] = "file:%s" % rec["rel"]
        elif v.get("locator") == "p1":
            v["locator"] = "text:%s#p1" % rec["rel"]
    if not (rec["meta"].get("title") or {}).get("value"):
        stem = os.path.splitext(rec["name"])[0]
        cleaned = re.sub(r"^[A-Z][A-Za-z\-']{1,20}[_ \-]?(et al\.?)?[_ \-]?(19|20)\d{2}[_ \-]?", "", stem)
        rec["meta"]["title_name_only"] = {"value": cleaned.replace("_", " ")[:200], "confidence": "low",
                                          "locator": "file:%s" % rec["rel"],
                                          "note": "file-name derived, not verified against text"}
    return rec
