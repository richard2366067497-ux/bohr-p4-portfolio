# -*- coding: utf-8 -*-
"""extract.py - text extraction + block structure for research-file-locator.

Pure standard library. No network, no third-party deps, CWD-independent.

Public entry point:
    extract(path, doc_id) -> dict(status, kind, units, pages, notes, chars)
where every unit is:
    {"kind": "heading|para|table|caption|reference",
     "level": 1..6 (heading level, 0 otherwise),
     "text": str,
     "page_physical": int|None, "page_printed": int|None,
     "container": str|None}          # sheet name / slide no / table index

Extraction is honest: a file that cannot be read never yields invented text, it
returns a non-"ok" status with a machine-readable reason.
"""
import csv
import io
import json
import re
import subprocess
import zipfile
import zlib
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".tex", ".log",
            ".rst", ".html", ".htm", ".xml", ".bib", ".ini", ".cfg", ".srt", ".text"}
OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".xlsm", ".docm", ".pptm"}
LEGACY_EXT = {".doc", ".xls", ".ppt", ".wps", ".et", ".dps"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

CJK = re.compile(r"[㐀-鿿豈-﫿]")
HEAD_MD = re.compile(r"^(\s{0,3})(#{1,6})\s+(\S.*)$")
HEAD_NUM = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})[\.\s、]\s*(\S.{0,90})$")
HEAD_CN = re.compile(r"^\s*第\s*([一二三四五六七八九十百零〇\d]{1,4})\s*[章节節部分篇]\s*[、\.\s]?\s*(\S.{0,80})$")
HEAD_CN2 = re.compile(r"^\s*(?:[（(]?[一二三四五六七八九十]{1,3}[）)]?|[（(]?\d{1,2}[）)])\s*[、\.．]\s*(\S.{1,60})$")
HEAD_APP = re.compile(r"^\s*(附录|附表|附图|Appendix)\s*[A-Z\d一二三四五六七八九十]{0,3}\s*[：:\.\s]?\s*(\S.{0,80})$")
HEAD_NAMED = re.compile(
    r"^\s*(abstract|摘要|introduction|引言|绪论|前言|background|related work|"
    r"materials? and methods?|methods?|methodology|实验方法|材料与方法|方法与材料|"
    r"results?( and discussion)?|结果(与讨论)?|discussion|讨论|conclusions?|结论|"
    r"references?|bibliography|参考文献|acknowledg(e)?ments?|致谢|supplementary( materials?)?|"
    r"补充材料|supporting information|appendix)\s*[:：]?\s*$", re.I)
CAPTION = re.compile(r"^\s*(图|表|figure|fig\.?|table|scheme|chart)\s*[\dA-Z一二三四五六七八九十][\d\.\-–—:：]?",
                     re.I)
REF_LINE = re.compile(r"^\s*\[\d{1,3}\]\s+\S|^\s*\d{1,3}\.\s+[A-Z][^.]{5,120}\(?(19|20)\d\d\)?")
SENT_END = re.compile(r"[。．\.\!\?！？；;:：\)）\]】\"'”’]\s*$")


def _norm_ext(path):
    return Path(path).suffix.lower()


def kind_of(path):
    ext = _norm_ext(path)
    if ext == ".pdf":
        return "pdf"
    if ext in OFFICE_EXT:
        return ext.strip(".")
    if ext in LEGACY_EXT:
        return "legacy_" + ext.strip(".")
    if ext in IMAGE_EXT:
        return "image"
    if ext in TEXT_EXT:
        return "text"
    return "other"


def decode_bytes(data, path=""):
    """Return (text, encoding). Tries the encodings research files actually use."""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16"):
        try:
            return data.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace"), "utf-8-replace"


# ---------------------------------------------------------------- headings / paragraphs
def heading_level(line):
    """Detect a heading line -> (level, title) or None."""
    s = line.rstrip()
    if not s or len(s) > 130:
        return None
    m = HEAD_MD.match(s)
    if m:
        return len(m.group(2)), m.group(3).strip()
    m = HEAD_NAMED.match(s)
    if m:
        return 1, s.strip().rstrip(":：")
    m = HEAD_CN.match(s)
    if m:
        return m.group(1).count(".") + 1, s.strip()
    m = HEAD_APP.match(s)
    if m:
        return 2, s.strip()
    m = HEAD_CN2.match(s)
    if m and len(s.split()) <= 10 and not SENT_END.search(s):
        return 2, s.strip()
    m = HEAD_NUM.match(s)
    if m and not SENT_END.search(s) and len(s.split()) <= 16:
        return m.group(1).count(".") + 1, s.strip()
    return None


def merge_lines(lines, maxlen=900):
    """Merge raw text lines into paragraph-sized blocks (PPT/PDF give one line per run)."""
    out, buf = [], ""
    for ln in lines:
        t = ln.strip()
        if not t:
            if buf:
                out.append(buf)
                buf = ""
            continue
        if heading_level(t):
            if buf:
                out.append(buf)
                buf = ""
            out.append(t)
            continue
        if not buf:
            buf = t
            continue
        if CAPTION.match(t) and len(t) < 300:
            out.append(buf)
            buf = t
            continue
        joined = _join(buf, t)
        if len(joined) > maxlen or (SENT_END.search(buf) and t[:1].isupper() and len(buf) > 220):
            out.append(buf)
            buf = t
        else:
            buf = joined
    if buf:
        out.append(buf)
    return out


def _join(a, b):
    if not a:
        return b
    if CJK.search(a[-1:]) and CJK.search(b[:1]):
        return a + b
    if a[-1:] in "-–—":
        return a + b
    return a + " " + b


def units_from_text(text, page=None):
    """Split free text into heading/para/caption units."""
    units = []
    blocks = re.split(r"\n\s*\n", text)
    for blk in blocks:
        for para in merge_lines(blk.splitlines()):
            h = heading_level(para)
            if h:
                units.append({"kind": "heading", "level": h[0], "text": para})
            elif CAPTION.match(para) and len(para) < 400:
                units.append({"kind": "caption", "level": 0, "text": para})
            elif REF_LINE.match(para) and len(para) < 400:
                units.append({"kind": "reference", "level": 0, "text": para})
            else:
                units.append({"kind": "para", "level": 0, "text": para})
    for u in units:
        u.setdefault("page_physical", page)
        u.setdefault("page_printed", page)
        u.setdefault("container", None)
    return units


# ---------------------------------------------------------------- PDF
def _pdf_objects(data):
    objs = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", data, re.S):
        num, body = int(m.group(1)), m.group(3)
        sm = re.search(rb"stream\r?\n", body)
        if sm:
            dic, raw = body[:sm.start()], body[sm.end():]
            e = raw.rfind(b"endstream")
            if e >= 0:
                raw = raw[:e]
            if raw.endswith(b"\r\n"):
                raw = raw[:-2]
            elif raw.endswith(b"\n") or raw.endswith(b"\r"):
                raw = raw[:-1]
            objs[num] = (dic, raw)
        else:
            objs[num] = (body, None)
    return objs


def _inflate(dic, raw):
    if raw is None:
        return b""
    try:
        if b"FlateDecode" in dic:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompressobj().decompress(raw)
        if b"ASCII85Decode" in dic or b"ASCIIHexDecode" in dic:
            return b""
        return raw
    except Exception:  # noqa: BLE001
        return b""


def _unesc(b):
    out, i, n = bytearray(), 0, len(b)
    esc = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}
    while i < n:
        c = b[i]
        if c != 0x5C:
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = b[i]
        if bytes([c]) in esc:
            out += esc[bytes([c])]
            i += 1
        elif c in (0x28, 0x29, 0x5C):
            out.append(c)
            i += 1
        elif 0x30 <= c <= 0x37:
            oct_ = b""
            while i < n and 0x30 <= b[i] <= 0x37 and len(oct_) < 3:
                oct_ += bytes([b[i]])
                i += 1
            out.append(int(oct_.decode() or "0", 8) & 0xFF)
        elif c in (0x0A, 0x0D):
            i += 1
        else:
            out.append(c)
            i += 1
    return bytes(out)


def _content_lines(content):
    """Pull text lines out of a PDF content stream (Tj/TJ with Td/T*/Tm line breaks)."""
    pat = re.compile(rb"\((?:\\.|[^\\()])*\)|\[(?:[^\[\]]*)\]|\bT\*|\bTd\b|\bTD\b|\bTm\b|\bET\b", re.S)
    out, buf = [], []
    for m in pat.finditer(content):
        tok = m.group(0)
        if tok.startswith(b"("):
            s = _unesc(tok[1:-1]).decode("latin-1")
            if s:
                buf.append(s)
        elif tok.startswith(b"["):
            for sm in re.finditer(rb"\((?:\\.|[^\\()])*\)", tok):
                s = _unesc(sm.group(0)[1:-1]).decode("latin-1")
                if s:
                    buf.append(s)
        elif tok in (b"T*", b"Td", b"TD", b"Tm", b"ET"):
            if tok in (b"Td", b"TD"):
                pre = content[max(0, m.start() - 48):m.start()]
                nums = re.findall(rb"-?\d+(?:\.\d+)?", pre)
                if len(nums) >= 2:
                    try:
                        if abs(float(nums[-1])) < 0.5:
                            continue
                    except ValueError:
                        pass
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out


def _page_order(objs):
    kids = {}
    for num, (dic, _s) in objs.items():
        if re.search(rb"/Type\s*/Pages", dic):
            mm = re.search(rb"/Kids\s*\[(.*?)\]", dic, re.S)
            if mm:
                kids[num] = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", mm.group(1))]
    linked = {k for v in kids.values() for k in v}
    roots = [n for n in kids if n not in linked]
    order = []

    def walk(n, depth=0):
        if depth > 16 or len(order) > 5000:
            return
        if n in kids:
            for k in kids[n]:
                walk(k, depth + 1)
        else:
            order.append(n)

    for r in sorted(roots):
        walk(r)
    if not order:
        order = [n for n, (d, _s) in sorted(objs.items()) if re.search(rb"/Type\s*/Page[^s]", d)]
    return order


def _page_label_map(data, objs):
    """Parse /PageLabels -> {physical_index(0-based): printed_number} and a source tag."""
    blob = data
    m = re.search(rb"/PageLabels\s+(\d+)\s+0\s+R", data)
    if m:
        obj = objs.get(int(m.group(1)))
        blob = obj[0] if obj else b""
    if b"/PageLabels" not in blob and b"/Nums" not in blob:
        return {}, "none"
    nums = re.search(rb"/Nums\s*\[(.*?)\]\s*>>", blob, re.S) or re.search(rb"/Nums\s*\[(.*?)\]", blob, re.S)
    if not nums:
        return {}, "none"
    labels = {}
    for pm in re.finditer(rb"(\d+)\s*<<(.*?)>>", nums.group(1), re.S):
        start = int(pm.group(1))
        st = re.search(rb"/St\s+(\d+)", pm.group(2))
        if not st:
            continue
        base = int(st.group(1))
        for i in range(start, start + 1):
            labels[i] = base
    if not labels:
        return {}, "none"
    # extend the first label range across the document
    first = min(labels)
    base = labels[first]
    return {first: base - (first + 1)}, "pagelabels"


def _footer_offset(pages):
    """Infer a constant printed/physical page offset from footer/header page numbers."""
    if len(pages) < 3:
        return 0, "assumed_equal"
    cands = {}
    for i, txt in enumerate(pages):
        lines = [x.strip() for x in txt.splitlines() if x.strip()]
        probe = lines[:2] + lines[-2:]
        for ln in probe:
            n = None
            mm = re.match(r"^[-–—\s]*(\d{1,3})[-–—\s]*$", ln)
            if mm:
                n = int(mm.group(1))
            else:
                mm = re.search(r"(?:第\s*(\d{1,3})\s*页)|(?:page\s*(\d{1,3}))", ln, re.I)
                if mm:
                    n = int(mm.group(1) or mm.group(2))
            if n and 1 <= n <= 2000:
                d = n - (i + 1)
                cands[d] = cands.get(d, 0) + 1
                break
    if not cands:
        return 0, "assumed_equal"
    best, cnt = max(cands.items(), key=lambda kv: kv[1])
    if cnt >= max(3, int(0.6 * len(pages))):
        return best, "footer_offset"
    return 0, "assumed_equal"


def _pdftotext(path):
    try:
        r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.decode("utf-8", "replace").split("\f")
    except Exception:  # noqa: BLE001
        return None
    return None


def _clean_pdf_lines(lines):
    out = []
    for ln in lines:
        t = ln.rstrip()
        if not t.strip():
            out.append("")
            continue
        out.append(t)
    return out


def pdf_extract(path, data):
    info = {"status": "ok", "pages": [], "label_source": "assumed_equal", "offset": 0,
            "engine": None, "notes": []}
    if re.search(rb"/Encrypt\b", data):
        info["status"] = "encrypted"
        info["notes"].append("PDF /Encrypt present; not decrypted")
        return info
    pages = _pdftotext(path)
    if pages is not None:
        info["engine"] = "pdftotext"
        while pages and not pages[-1].strip():
            pages.pop()
    else:
        info["engine"] = "stdlib"
        try:
            objs = _pdf_objects(data)
            order = _page_order(objs)
            offsets, src = _page_label_map(data, objs)
            info["label_source"] = src
            info["offset"] = offsets.get(0, 0) if offsets else 0
            pages = []
            for num in order:
                dic, raw = objs.get(num, (b"", None))
                refs = re.findall(rb"/Contents\s+(\d+)\s+0\s+R", dic)
                if not refs:
                    arr = re.search(rb"/Contents\s*\[(.*?)\]", dic, re.S)
                    if arr:
                        refs = re.findall(rb"(\d+)\s+0\s+R", arr.group(1))
                chunks = []
                for r_ in refs:
                    od, oraw = objs.get(int(r_), (b"", None))
                    chunks.append(_inflate(od, oraw))
                if not chunks and raw is not None:
                    chunks = [_inflate(dic, raw)]
                content = b"\n".join(chunks)
                pages.append("\n".join(_content_lines(content)))
        except Exception as e:  # noqa: BLE001
            info["status"] = "corrupt"
            info["notes"].append(f"{type(e).__name__}: {e}")
            return info
    if not any(p.strip() for p in pages):
        info["status"] = "no_text_layer"
        info["notes"].append("no extractable text (scanned image or unsupported font encoding)")
        info["pages"] = []
        return info
    # text quality gate: mostly non-printable => unusable codepoints
    sample = "".join(pages)[:4000]
    good = sum(1 for ch in sample if ch.isprintable() or ch in "\n\t")
    if sample and good / max(1, len(sample)) < 0.80:
        info["status"] = "low_text_quality"
        info["notes"].append("decoded text has too many control characters; treated as unreadable")
        info["pages"] = []
        return info
    if info["engine"] == "pdftotext":
        off, src = _footer_offset(pages)
        info["offset"], info["label_source"] = off, src
    elif info["label_source"] == "none":
        off, src = _footer_offset(pages)
        info["offset"], info["label_source"] = off, src
    pages = [_clean_pdf_lines(p.splitlines()) for p in pages]
    off = info["offset"]
    for idx, lines in enumerate(pages, 1):
        keep = []
        for k, ln in enumerate(lines):
            t = ln.strip()
            edge = k < 3 or k >= len(lines) - 3
            m = re.fullmatch(r"[-\u2013\u2014\s]*(\d{1,4})[-\u2013\u2014\s]*", t)
            if edge and m and int(m.group(1)) in (idx, idx + off):
                continue
            if edge and re.match(r"(?i)^(?:page|\u7b2c)\s*\d{1,4}\s*(?:\u9875)?$", t):
                continue
            keep.append(ln)
        pages[idx - 1] = keep
    info["pages"] = pages
    return info


# ---------------------------------------------------------------- OOXML
def _docx_units(data):
    import xml.etree.ElementTree as ET
    z = zipfile.ZipFile(io.BytesIO(data))
    name = "word/document.xml"
    if name not in z.namelist():
        raise ValueError("word/document.xml missing")
    root = ET.fromstring(z.read(name))

    def ptext(el):
        return "".join(t.text or "" for t in el.iter(W + "t")).strip()

    body = root.find(W + "body")
    if body is None:
        body = root
    units = []
    for el in list(body):
        if el.tag == W + "p":
            t = ptext(el)
            if not t:
                continue
            sty = el.find(f"{W}pPr/{W}pStyle")
            val = (sty.get(W + "val") if sty is not None else "") or ""
            lvl = 0
            m = re.search(r"(?i)heading\s*(\d)|标题\s*(\d)", val)
            if m:
                lvl = int(m.group(1) or m.group(2))
            elif re.search(r"(?i)^title$|^标题$", val):
                lvl = 1
            if not lvl and heading_level(t) and len(t) < 120:
                lvl = heading_level(t)[0]
            units.append({"kind": "heading" if lvl else "para", "level": lvl, "text": t,
                          "page_physical": None, "page_printed": None, "container": None})
        elif el.tag == W + "tbl":
            idx = sum(1 for u in units if u["kind"] == "table") + 1
            for tr in el.iter(W + "tr"):
                cells = [" ".join(x for x in (ptext(tc) for tc in tr.iter(W + "tc")) if x)]
                row = " | ".join(cells).strip(" |")
                if row:
                    units.append({"kind": "table", "level": 0, "text": row, "page_physical": None,
                                  "page_printed": None, "container": f"table{idx}"})
    return units


def _xlsx_units(data):
    import xml.etree.ElementTree as ET
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        sroot = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in sroot.findall(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    names = []
    if "xl/workbook.xml" in z.namelist():
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") or f"sheet{i+1}" for i, s in enumerate(wb.iter(NS + "sheet"))]
    sheets = sorted([n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)],
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
    units = []
    for si, name in enumerate(sheets):
        title = names[si] if si < len(names) else f"sheet{si+1}"
        units.append({"kind": "heading", "level": 1, "text": f"[sheet] {title}", "page_physical": None,
                      "page_printed": None, "container": title})
        root = ET.fromstring(z.read(name))
        for ri, row in enumerate(root.iter(NS + "row")):
            if ri > 3000:
                break
            vals = []
            for c in row.findall(NS + "c"):
                t = c.get("t")
                v = c.find(NS + "v")
                isel = c.find(NS + "is")
                if t == "s" and v is not None and v.text:
                    try:
                        vals.append(shared[int(v.text)])
                    except (ValueError, IndexError):
                        vals.append(v.text)
                elif t == "inlineStr" and isel is not None:
                    vals.append("".join(x.text or "" for x in isel.iter(NS + "t")))
                elif v is not None:
                    vals.append(v.text or "")
            rowtxt = " | ".join(x for x in vals if x is not None).strip(" |")
            if rowtxt:
                units.append({"kind": "table", "level": 0, "text": rowtxt, "page_physical": None,
                              "page_printed": None, "container": title})
    return units


def _pptx_units(data):
    import xml.etree.ElementTree as ET
    z = zipfile.ZipFile(io.BytesIO(data))
    slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
    units = []
    for si, name in enumerate(slides, 1):
        root = ET.fromstring(z.read(name))
        first = True
        for p in root.iter(A + "p"):
            t = "".join(x.text or "" for x in p.iter(A + "t")).strip()
            if not t:
                continue
            if first:
                units.append({"kind": "heading", "level": 1, "text": t, "page_physical": si,
                              "page_printed": si, "container": f"slide{si}"})
                first = False
            else:
                units.append({"kind": "para", "level": 0, "text": t, "page_physical": si,
                              "page_printed": si, "container": f"slide{si}"})
    return units


def _csv_units(text, delim=None):
    rows = []
    try:
        rd = csv.reader(io.StringIO(text), delimiter=delim or _sniff(text))
        for i, r in enumerate(rd):
            if i > 3000:
                break
            cells = [c.strip() for c in r if c and c.strip()]
            if cells:
                rows.append(" | ".join(cells))
    except Exception:  # noqa: BLE001
        rows = [ln for ln in text.splitlines() if ln.strip()]
    units = [{"kind": "table", "level": 0, "text": r, "page_physical": None, "page_printed": None,
              "container": "csv"} for r in rows]
    return units


def _sniff(text):
    head = text.splitlines()[0] if text.splitlines() else ""
    for d in ("\t", ";", ",", "|"):
        if head.count(d) >= 2:
            return d
    return ","


# ---------------------------------------------------------------- public
def extract(path, doc_id=""):
    p = Path(path)
    res = {"status": "ok", "kind": kind_of(p), "units": [], "pages": {"count": None,
           "label_source": "not_applicable", "page_offset": None},
           "notes": [], "chars": 0, "encoding": None}
    try:
        data = p.read_bytes()
    except PermissionError:
        res["status"] = "permission_denied"
        res["notes"].append("OS denied read permission")
        return res
    except FileNotFoundError:
        res["status"] = "path_missing"
        res["notes"].append("file not found at index time")
        return res
    except OSError as e:
        res["status"] = "corrupt"
        res["notes"].append(f"{type(e).__name__}: {e}")
        return res
    if len(data) == 0:
        res["status"] = "empty_file"
        res["notes"].append("0 bytes")
        return res

    kind = res["kind"]
    try:
        if kind == "pdf":
            info = pdf_extract(p, data)
            res["notes"].extend(info["notes"])
            if info["status"] != "ok":
                res["status"] = info["status"]
                return res
            pages = info["pages"]
            res["pages"] = {"count": len(pages), "label_source": info["label_source"],
                            "page_offset": info["offset"]}
            for idx, lines in enumerate(pages, 1):
                printed = idx + info["offset"]
                for u in units_from_text("\n".join(lines), page=idx):
                    u["page_physical"] = idx
                    u["page_printed"] = printed
                    res["units"].append(u)
            res["encoding"] = "pdf-" + (info["engine"] or "stdlib")
        elif kind in ("docx", "pptx", "xlsx"):
            if kind == "docx":
                units = _docx_units(data)
            elif kind == "pptx":
                units = _pptx_units(data)
            else:
                units = _xlsx_units(data)
            for u in units:
                u.setdefault("container", None)
            res["units"] = units
            res["pages"] = {"count": None, "label_source": "not_applicable", "page_offset": None}
        elif kind in ("legacy_doc", "legacy_xls", "legacy_ppt", "legacy_wps", "legacy_et", "legacy_dps"):
            res["status"] = "unsupported_legacy"
            res["notes"].append("legacy binary Office format; convert to OOXML to index")
            return res
        elif kind == "image":
            res["status"] = "no_text_layer"
            res["notes"].append("raster image without text layer; OCR not available in stdlib")
            return res
        else:
            text, enc = decode_bytes(data, str(p))
            res["encoding"] = enc
            if p.suffix.lower() in (".csv", ".tsv"):
                res["units"] = _csv_units(text)
            elif p.suffix.lower() in (".html", ".htm", ".xml"):
                plain = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
                plain = re.sub(r"<[^>]+>", "\n", plain)
                plain = re.sub(r"&nbsp;?", " ", plain)
                res["units"] = units_from_text(plain)
            else:
                res["units"] = units_from_text(text)
    except zipfile.BadZipFile:
        res["status"] = "corrupt"
        res["notes"].append("OOXML container is not a valid zip")
        return res
    except Exception as e:  # noqa: BLE001
        res["status"] = "corrupt"
        res["notes"].append(f"{type(e).__name__}: {e}")
        return res

    res["units"] = [u for u in res["units"] if u.get("text")]
    res["chars"] = sum(len(u["text"]) for u in res["units"])
    if not res["units"]:
        res["status"] = "no_text_layer"
        res["notes"].append("parser produced no text blocks")
    return res
