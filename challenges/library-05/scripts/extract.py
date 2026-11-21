#!/usr/bin/env python3
"""extract.py -- reading-artifact extraction core + shared io helpers (stdlib only).

Mechanical only: file typing, hashing, PDF page tree + /Annots + content-stream text
blocks, DOCX comments, HTML highlight clips, annotation overlays, alias/version
grouping, verbatim quote matching, json io. Semantic judgement lives in draft.json.
"""
import hashlib
import json
import re
import unicodedata
import zipfile
import zlib
from pathlib import Path

TRUNC = 900000
WS = re.compile(r"\s+")
TR = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-",
      "\u2212": "-", "\u00a0": " ", "\u200b": "", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl",
      "\u3000": " ", "\u2026": "..."}
TYPES = "highlight underline squiggly strikeout margin_note handwritten web_clip word_comment region_mark unknown".split()
SECTIONS = "question method result conclusion reusable to_verify".split()
RELS = "supports contradicts extends same_topic method_of authored_by version_of annotates".split()


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))


def jw(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return len(p.read_bytes())


def jl(p, rows):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except Exception:
        return ""


def contract_keys(ct):
    if isinstance(ct, dict):
        return [str(k) for k in ct]
    if isinstance(ct, list):
        return [f if isinstance(f, str) else str(f.get("name") or f.get("key") or "field_%d" % (i + 1))
                for i, f in enumerate(ct) if isinstance(f, (str, dict))]
    return []


def empty_like(spec):
    t = json.dumps(spec, ensure_ascii=False).lower() if spec is not None else ""
    for k, v in (("array", []), ("list", []), ("object", {}), ("dict", {}), ("string", "")):
        if '"%s"' % k in t or (k in t and "type" in t):
            return v
    return None


def tokens(s):
    s = norm(s).lower()
    out = set(re.findall(r"[a-z][a-z0-9\-]{2,}", s))
    cj = re.findall(r"[\u4e00-\u9fff]", s)
    return out | {"".join(cj[i:i + 2]) for i in range(len(cj) - 1)}


def norm(s, squash=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if squash else " ", s).strip()


def fq(text, quote):
    """Verbatim-ish match: exact after whitespace/NFKC normalisation, then squashed."""
    q, t = norm(quote), norm(text or "")
    if len(q) < 3 or not t:
        return {"found": False, "mode": "too_short", "at": -1}
    i = t.find(q)
    if i >= 0:
        return {"found": True, "mode": "exact", "at": i}
    j = norm(text, True).find(norm(quote, True))
    return {"found": True, "mode": "loose", "at": j} if j >= 0 else {"found": False, "mode": "miss", "at": -1}


def decode_bytes(b):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", "replace")


def pnum(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def rect_of(v):
    if isinstance(v, list) and len(v) >= 4:
        r = [pnum(x) for x in v[:4]]
        return [min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])]
    return None


def sha256_file(p):
    return sha(p)


def kind_of(p):
    try:
        h = Path(p).read_bytes()[:16]
    except Exception:
        return "unreadable"
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK"):
        try:
            with zipfile.ZipFile(p) as z:
                n = " ".join(z.namelist()[:80])
        except Exception:
            return "zip"
        for k, v in (("word/document", "docx"), ("xl/workbook", "xlsx"), ("ppt/presentation", "pptx")):
            if k in n:
                return v
        return "zip"
    low = h.lower().lstrip()
    if low.startswith((b"<html", b"<!doctype")) or b"<html" in low:
        return "html"
    if h.startswith((b"\x89PNG", b"\xff\xd8", b"II*\x00")):
        return "image"
    return "text"


def docx_extract(p):
    from xml.etree import ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    annots, notes = [], []
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        doc = z.read("word/document.xml") if "word/document.xml" in names else b""
        cmts = z.read("word/comments.xml") if "word/comments.xml" in names else b""
    paras, spans, open_ids = [], {}, {}
    if doc:
        for el in ET.fromstring(doc).iter():
            if el.tag == W + "commentRangeStart":
                open_ids[el.get(W + "id")] = []
            elif el.tag == W + "commentRangeEnd":
                spans[el.get(W + "id")] = "".join(open_ids.pop(el.get(W + "id"), []))
            elif el.tag == W + "t" and el.text:
                for buf in open_ids.values():
                    buf.append(el.text)
                if paras and paras[-1].get("_open"):
                    paras[-1]["text"] += el.text
                else:
                    paras.append({"locator": "p1#para%d" % (len(paras) + 1), "text": el.text, "_open": True})
            elif el.tag == W + "p" and paras:
                paras[-1]["_open"] = False
    for x in paras:
        x.pop("_open", None)
    paras = paras or [{"locator": "p1#para1", "text": ""}]
    for i, c in enumerate(ET.fromstring(cmts).iter(W + "comment") if cmts else []):
        rng = norm(spans.get(c.get(W + "id"), ""))
        annots.append({"page": 1, "locator": "p1#cmt%d" % (i + 1), "rect": None, "quadpoints": None,
                       "raw_subtype": "WordComment", "type": "word_comment", "color": None,
                       "author": c.get(W + "author") or "", "created": c.get(W + "date") or "",
                       "comment": norm("".join(t.text or "" for t in c.iter(W + "t"))),
                       "line_text": rng, "rect_text": rng, "rect_overlap": 1.0 if rng else 0.0,
                       "source": "docx_comments"})
    if not cmts:
        notes.append("no comments.xml: document carries no Word comments")
    text = "\n".join(x["text"] for x in paras if x["text"].strip())
    return {"pages": [{"page": 1, "locator": "p1", "text": text, "layout": "docx", "width": 612.0}],
            "annots": annots, "engine": "docx-xml", "notes": notes, "paras": paras,
            "has_text_layer": bool(text.strip()), "n_pages": 1}


def html_extract(p):
    s = decode_bytes(Path(p).read_bytes())
    annots, notes = [], []
    m = re.search(r'<link[^>]+rel=["\']?canonical["\']?[^>]+href=["\']([^"\']+)', s, re.I) or \
        re.search(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)', s, re.I)
    url = m.group(1) if m else ""
    mt = re.search(r"<title[^>]*>(.*?)</title>", s, re.I | re.S)
    title = norm(re.sub(r"<[^>]+>", "", mt.group(1))) if mt else ""
    pat = re.compile(r"<(mark|span|div)[^>]*(?:class=[\"'][^\"']*highlight|style=[\"'][^\"']*"
                     r"background-color:\s*([^;\"']+))[^>]*>(.*?)</\1>", re.I | re.S)
    for i, mm in enumerate(pat.finditer(s)):
        frag = norm(re.sub(r"<[^>]+>", "", mm.group(3)))
        if len(frag) < 4:
            continue
        annots.append({"page": 1, "locator": "p1#clip%d" % (i + 1), "rect": None, "quadpoints": None,
                       "raw_subtype": "HtmlHighlight", "type": "web_clip", "color": norm(mm.group(2) or "") or None,
                       "author": "", "created": "", "comment": "", "line_text": frag, "rect_text": frag,
                       "rect_overlap": 1.0, "source": "html_mark"})
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    text = norm(decode_bytes(re.sub(r"(?s)<[^>]+>", "\n", body).encode("utf-8", "ignore")))
    if not annots:
        notes.append("no <mark>/highlight element: clip carries no explicit annotation")
    if not url:
        notes.append("source_url not declared in the clipped page")
    return {"pages": [{"page": 1, "locator": "p1", "text": text, "layout": "html", "width": 612.0}],
            "annots": annots, "engine": "html-regex", "notes": notes, "src": {"url": url, "title": title},
            "has_text_layer": bool(text.strip()), "n_pages": 1}


def text_extract(p):
    s = decode_bytes(Path(p).read_bytes())
    paras = [{"locator": "p1#para%d" % (i + 1), "text": ln.strip()}
             for i, ln in enumerate(s.splitlines()) if ln.strip()]
    return {"pages": [{"page": 1, "locator": "p1", "text": "\n".join(x["text"] for x in paras),
                       "layout": "text", "width": 612.0}],
            "annots": [], "engine": "text", "paras": paras, "notes": [] if paras else ["empty text file"],
            "has_text_layer": bool(paras), "n_pages": 1}


def extract_doc(p):
    k = kind_of(p)
    try:
        if k == "pdf":
            from pdfio import pdf_extract
            d = pdf_extract(p)
        elif k == "docx":
            d = docx_extract(p)
        elif k == "html":
            d = html_extract(p)
        elif k == "text":
            d = text_extract(p)
        else:
            msg = {"image": "image file: no text layer, OCR required"}.get(k, "%s container not parsed" % k)
            d = {"pages": [{"page": 1, "locator": "p1", "text": "", "layout": k, "width": 612.0}],
                 "annots": [], "engine": "none" if k == "image" else "unsupported",
                 "notes": [msg], "has_text_layer": False, "n_pages": 0}
    except Exception as e:
        d = {"pages": [{"page": 1, "locator": "p1", "text": "", "layout": "failed", "width": 612.0}],
             "annots": [], "engine": "failed", "has_text_layer": False, "n_pages": 0,
             "notes": ["extraction failed: %s: %s" % (type(e).__name__, e)]}
    d["kind"] = k
    text = "\n".join(pg["text"] for pg in d["pages"])
    d["quality"] = round(sum(ch.isalnum() for ch in text) / max(len(text), 1), 3)
    if text.strip() and d["quality"] < 0.5:
        d["notes"].append("text_quality_low (alnum %.2f): CID font or garbled encoding" % d["quality"])
    d["text"] = text[:TRUNC]
    return d


NOISE = re.compile(r"(?i)(\(|（)?\s*(copy|副本|备份|final|draft|proof|preprint|accepted|published|"
                   r"supplementary|补充材料|download|downloaded|\d{8}|\d{4}-\d{2}-\d{2})\s*(\)|）)?")
VNOTE = re.compile(r"(?i)(supersed|replac|obsolete|deprecat|withdraw|取代|替代|作废|废止|修订|改版|"
                   r"版本|ver\.?\s*\d|v\d+(\.\d+)?\b)")


def alias_key(name):
    s = unicodedata.normalize("NFKC", Path(name).name)
    s = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", s).lower()
    s = re.sub(r"[_\-\s]+", " ", NOISE.sub(" ", s))
    s = re.sub(r"\bv(?:er|ersion)?\.?\s?\d{1,3}(\.\d{1,3})?\b", " ", s)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s) or Path(name).name.lower()


def version_token(name, meta=""):
    s = Path(name).name
    c = re.findall(r"(?i)(?:^|[_\-\.\s])v(?:er|ersion)?\.?\s*(\d{1,3}(?:\.\d{1,3})?)", s)
    c += re.findall(r"(?i)(?:^|[_\-\.\s])(?:rev|r)(\d{1,3})\b", s)
    c += re.findall(r"(?:版本|修订|第)\s*([0-9]{1,3}(?:\.[0-9]{1,3})?)", s)
    if meta:
        c += re.findall(r"(?i)\b(?:version|ver\.?|版本|修订)\s*[:：]?\s*([0-9]{1,3}(?:\.[0-9]{1,3})?)", meta)
    if not c:
        return ""
    try:
        return sorted(c, key=lambda x: float(x.split(".")[0]))[-1]
    except Exception:
        return c[-1]


def group_docs(docs):
    """sha256 duplicates + filename-alias groups; version chains ordered by token then size."""
    by_h, by_a = {}, {}
    for did, d in docs.items():
        if d.get("sha256"):
            by_h.setdefault(d["sha256"], []).append(did)
        by_a.setdefault(alias_key(d["filename"]), []).append(did)
    dup, alias = [], []
    for h, ids in by_h.items():
        if len(ids) > 1:
            ids.sort(key=lambda x: (len(docs[x]["filename"]), docs[x]["filename"]))
            for o in ids[1:]:
                docs[o]["duplicate_of"] = ids[0]
            dup.append({"sha256": h, "docs": ids, "canonical": ids[0], "kind": "byte_identical",
                        "detail": "同一 sha256：同一文件重复下载/多份拷贝，批注应归并到同一逻辑文档"})
    for k, ids in by_a.items():
        if len(ids) <= 1:
            continue
        gid = "G%d" % (len(alias) + 1)

        def key(x):
            head = (docs[x].get("version") or "").split(".")[0]
            return (float(head) if head.isdigit() else -1.0, docs[x].get("size") or 0)
        ids = sorted(ids, key=key)
        chain = [{"doc_id": x, "version": docs[x].get("version") or "",
                  "sha256": (docs[x].get("sha256") or "")[:12], "size": docs[x].get("size")} for x in ids]
        for x in ids:
            docs[x]["alias_group"], docs[x]["version_chain"] = gid, chain
        alias.append({"group": gid, "alias_key": k, "docs": ids, "canonical": ids[-1], "chain": chain,
                      "kind": "filename_alias",
                      "detail": "文件名归一后同名：需按版本/大小/哈希判定是否同一文献的不同版本"})
    return dup, alias


def version_notes_from_text(name, text, limit=30):
    out = []
    for i, ln in enumerate((x.strip() for x in (text or "").splitlines())):
        if len(ln) >= 6 and VNOTE.search(ln):
            out.append({"source": name, "locator": "p1#para%d" % (i + 1), "note": ln[:400]})
            if len(out) >= limit:
                break
    return out


def load_overlays(files):
    """External annotations*.json -> normalised annotation dicts."""
    out, errs = [], []
    for p in files:
        nm = Path(p).name.lower()
        if Path(p).suffix.lower() != ".json" or not nm.startswith(("annot", "highlight")):
            continue
        try:
            data = jread(p)
        except Exception as e:
            errs.append({"code": "overlay_invalid", "detail": "%s: %s" % (Path(p).name, e)})
            continue
        rows = data if isinstance(data, list) else []
        if isinstance(data, dict):
            rows = data.get("annotations") or data.get("items") or data.get("records") or []
            if not rows and data and all(isinstance(v, list) for v in data.values()):
                for f, lst in data.items():          # {"file.pdf": [ {...}, ... ]}
                    for it in lst:
                        if isinstance(it, dict):
                            it.setdefault("file", f)
                            rows.append(it)
        for it in rows if isinstance(rows, list) else []:
            if not isinstance(it, dict):
                continue
            g = lambda *ks: next((it[k] for k in ks if it.get(k) not in (None, "")), None)
            out.append({"file": str(g("file", "filename", "path", "document", "doc", "source") or ""),
                        "page": int(pnum(g("page", "page_number", "p", "pageIndex") or 1)) or 1,
                        "rect": rect_of(g("rect", "bbox", "bounds", "coordinates")),
                        "type": str(g("type", "kind", "annotation_type", "subtype", "category") or "unknown"),
                        "color": str(g("color", "colour", "fill") or "") or None,
                        "comment": norm(g("comment", "note", "content", "body", "annotation") or ""),
                        "quoted_text": norm(g("quoted_text", "quote", "text", "selected_text", "highlighted") or ""),
                        "author": str(g("author", "user", "creator") or ""),
                        "created": str(g("created", "date", "timestamp", "modified") or ""),
                        "source": "annotations_json"})
    return out, errs


def type_alias(t):
    t = norm(t).lower().replace("-", "_").replace(" ", "_")
    mp = {"high_light": "highlight", "mark": "highlight", "highlight": "highlight", "wavy": "squiggly",
          "strikethrough": "strikeout", "strike": "strikeout", "underline": "underline", "squiggly": "squiggly",
          "text": "margin_note", "note": "margin_note", "freetext": "margin_note", "margin": "margin_note",
          "sidenote": "margin_note", "ink": "handwritten", "handwriting": "handwritten", "freehand": "handwritten",
          "web": "web_clip", "clip": "web_clip", "comment": "word_comment", "wordcomment": "word_comment",
          "square": "region_mark", "circle": "region_mark", "region": "region_mark"}
    return mp.get(t, t or "unknown")
