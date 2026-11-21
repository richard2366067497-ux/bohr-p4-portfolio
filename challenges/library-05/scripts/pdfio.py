#!/usr/bin/env python3
"""pdfio.py -- dependency-free PDF reader for reading artefacts (stdlib only).

Page tree (incl. /ObjStm), content-stream text blocks with approximate geometry,
/Annots of every page (highlight/underline/squiggly/strikeout/text/freetext/ink),
rect x text-block overlay for anchor candidates, two-column aware reading order.
No meaning is interpreted here; nothing is invented when a page has no text layer.
"""
import re
import zlib
from pathlib import Path

from extract import norm, pnum, rect_of

DELIM = b" \t\r\n\x00\x0c()<>[]{}/%"
SUB = {"/Highlight": "highlight", "/Underline": "underline", "/Squiggly": "squiggly",
       "/StrikeOut": "strikeout", "/Text": "margin_note", "/FreeText": "margin_note",
       "/Ink": "handwritten", "/Square": "region_mark", "/Circle": "region_mark",
       "/Stamp": "region_mark", "/Polygon": "region_mark"}


def _name(b, i):
    j, n = i + 1, len(b)
    while j < n and b[j] not in DELIM:
        j += 1
    return b[i:j].decode("latin-1", "replace"), j


def _literal(b, i):
    i, out, n, d = i + 1, bytearray(), len(b), 1
    while i < n:
        c = b[i]
        if c == 0x5C and i + 1 < n:
            nx = b[i + 1]
            if nx in (0x6E, 0x72, 0x74, 0x62, 0x66):
                out.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}[nx]); i += 2; continue
            if 0x30 <= nx <= 0x37:
                k = 0
                while k < 3 and i + 1 + k < n and 0x30 <= b[i + 1 + k] <= 0x37:
                    k += 1
                out.append(int(b[i + 1:i + 1 + k], 8) & 0xFF); i += 1 + k; continue
            out.append(nx); i += 2; continue
        if c == 0x28:
            d += 1
        elif c == 0x29:
            d -= 1
            if d == 0:
                i += 1
                break
        out.append(c); i += 1
    return bytes(out), i


def pval(b, i, depth=0):
    """Parse one PDF object: dict->{}, array->[], ref->('ref',num), string->bytes."""
    n = len(b)
    while i < n and b[i] in b" \t\r\n\x00\x0c":
        i += 1
    if i < n and b[i] == 0x25:
        j = b.find(b"\n", i); i = n if j < 0 else j + 1
        while i < n and b[i] in b" \t\r\n":
            i += 1
    if i >= n or depth > 40:
        return None, i
    if b[i:i + 2] == b"<<":
        i, d = i + 2, {}
        while i < n:
            while i < n and b[i] in b" \t\r\n\x00\x0c":
                i += 1
            if i >= n:
                return d, i
            if b[i:i + 2] == b">>":
                return d, i + 2
            if b[i] != 0x2F:
                v, i2 = pval(b, i, depth + 1)
                if i2 <= i:
                    return d, i + 1
                i = i2
                continue
            k, i = _name(b, i)
            d[k], i = pval(b, i, depth + 1)
        return d, i
    c = b[i]
    if c == 0x5B:
        i, a = i + 1, []
        while i < n:
            while i < n and b[i] in b" \t\r\n\x00\x0c":
                i += 1
            if i < n and b[i] == 0x5D:
                return a, i + 1
            if i >= n:
                return a, i
            v, i2 = pval(b, i, depth + 1)
            if i2 <= i:
                return a, i + 1
            i = i2
            a.append(v)
        return a, i
    if c == 0x2F:
        return _name(b, i)
    if c == 0x28:
        return _literal(b, i)
    if c == 0x3C:
        j = b.find(b">", i)
        hx = re.sub(rb"[^0-9A-Fa-f]", b"", b[i + 1:j if j > 0 else i + 1])
        try:
            s = bytes.fromhex(hx.decode()) if hx else b""
        except Exception:
            s = b""
        return s, (j + 1 if j > 0 else n)
    j = i
    while j < n and b[j] not in DELIM:
        j += 1
    tok, j = (b[i:j], j) if j > i else (b[i:i + 1], i + 1)
    if re.fullmatch(rb"[-+]?\d+", tok):
        k = j
        while k < n and b[k] in b" \t\r\n":
            k += 1
        m = re.match(rb"(\d+)\s+R(?![A-Za-z0-9])", b[k:k + 26])
        if m:
            return ("ref", int(tok)), k + m.end()
        return int(tok), j
    if re.fullmatch(rb"[-+]?\d*\.\d*", tok) and tok.strip(b"+-.") != b"":
        return (float(tok) if True else 0.0), j
    return tok.decode("latin-1", "replace"), j


def _dec(b):
    if isinstance(b, str):
        return b
    if not isinstance(b, (bytes, bytearray)):
        return "" if b is None else str(b)
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be", "replace")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("cp1252", "replace")


def deref(objs, v):
    seen = 0
    while isinstance(v, tuple) and len(v) == 2 and v[0] == "ref" and seen < 32:
        v, seen = objs.get(v[1]), seen + 1
    return v


def stream_data(raw):
    i = raw.find(b"stream")
    if i < 0:
        return b""
    j = i + 6
    if raw[j:j + 2] == b"\r\n":
        j += 2
    elif raw[j:j + 1] in (b"\n", b"\r"):
        j += 1
    e = raw.find(b"endstream", j)
    body, head = (raw[j:e] if e > 0 else raw[j:]), raw[:i]
    if b"FlateDecode" in head:
        for fn in (zlib.decompress, lambda x: zlib.decompressobj().decompress(x),
                   lambda x: zlib.decompressobj(-15).decompress(x[2:])):
            try:
                return fn(body)
            except Exception:
                continue
        return b""
    return body


def scan_objects(d):
    objs = {}
    for m in re.finditer(rb"(?<![0-9])(\d{1,9})\s+(\d{1,5})\s+obj\b", d):
        e = d.find(b"endobj", m.end())
        objs.setdefault(int(m.group(1)), d[m.end():e if e > 0 else min(len(d), m.end() + 400000)])
    for num, raw in list(objs.items()):          # expand /ObjStm (PDF >= 1.5)
        if b"/ObjStm" not in raw:
            continue
        data = stream_data(raw)
        if not data:
            continue
        head, _ = pval(raw, 0)
        first = int(pnum(head.get("/First"))) if isinstance(head, dict) else 0
        tk = data[:max(first, 0)].split()
        pairs = []
        for k in range(0, len(tk) - 1, 2):
            try:
                pairs.append((int(tk[k]), int(tk[k + 1])))
            except Exception:
                break
        for k, (onum, off) in enumerate(pairs):
            end = pairs[k + 1][1] if k + 1 < len(pairs) else len(data) - first
            try:
                objs.setdefault(onum, data[first + off:first + max(end, off + 1)])
            except Exception:
                continue
    return objs


def parsed(objs, cache, num):
    if num not in cache:
        v, _ = pval(objs.get(num, b""), 0)
        cache[num] = v if isinstance(v, dict) else {}
    return cache[num]


def pdict(objs, v):
    """Resolve a value to a dict: deref then parse when it is an indirect object."""
    if isinstance(v, tuple) and v and v[0] == "ref":
        d, _ = pval(objs.get(v[1], b""), 0)
        return d if isinstance(d, dict) else {}
    return v if isinstance(v, dict) else {}


def page_refs(objs, cache):
    root = None
    for num, raw in objs.items():
        if b"/Root" in raw:
            v, _ = pval(raw, 0)
            if isinstance(v, dict) and isinstance(v.get("/Root"), tuple):
                root = v["/Root"][1]
                break
    if root is None:
        for num in objs:
            d = parsed(objs, cache, num)
            if d.get("/Type") == "/Catalog" and isinstance(d.get("/Pages"), tuple):
                root = d["/Pages"][1]
                break
    order, seen = [], set()

    def walk(ref, depth=0):
        if not isinstance(ref, tuple) or depth > 60 or ref[1] in seen:
            return
        seen.add(ref[1])
        d = parsed(objs, cache, ref[1])
        kids = deref(objs, d.get("/Kids"))
        if isinstance(kids, list) and kids:
            for k in kids:
                walk(k, depth + 1)
        elif d.get("/Type") == "/Page" or "/Contents" in d or "/MediaBox" in d:
            order.append(ref[1])

    if root is not None:
        walk(("ref", root))
    if not order:
        order = [n for n in sorted(objs) if parsed(objs, cache, n).get("/Type") == "/Page"]
    return order


def content_chunks(cs):
    """Text blocks with approximate x/y/size from a content stream (Tj/TJ/Tm/Td/Tf)."""
    out, i, n, stack = [], 0, len(cs), []
    size, x, y, lead = 12.0, 0.0, 0.0, 14.0
    while i < n:
        c = cs[i:i + 1]
        if c in b" \t\r\n\x00\x0c":
            i += 1; continue
        if c == b"%":
            j = cs.find(b"\n", i); i = n if j < 0 else j + 1; continue
        if c == b"(":
            v, i = _literal(cs, i); stack.append(("s", _dec(v))); continue
        if c == b"<":
            if cs[i + 1:i + 2] == b"<<":                      # skip inline property dict
                j, d = i, 0
                while j < n - 1:
                    if cs[j:j + 2] == b"<<":
                        d, j = d + 1, j + 2
                    elif cs[j:j + 2] == b">>":
                        d, j = d - 1, j + 2
                        if d <= 0:
                            break
                    else:
                        j += 1
                i = max(j, i + 2); continue
            j = cs.find(b">", i)
            hx = re.sub(rb"[^0-9A-Fa-f]", b"", cs[i + 1:j if j > 0 else i + 1])
            i = j + 1 if j > 0 else n
            try:
                if hx:
                    stack.append(("s", _dec(bytes.fromhex(hx.decode()))))
            except Exception:
                pass
            continue
        if c in b"[]":
            i += 1; continue
        j = i
        while j < n and cs[j] not in DELIM:
            j += 1
        tok, i = cs[i:j], (j if j > i else i + 1)
        if not tok:
            continue
        if re.fullmatch(rb"[-+]?[\d.]+", tok):
            stack.append(("n", tok)); continue
        op, nums = tok.decode("latin-1", "replace"), [pnum(v) for t, v in stack if t == "n"]
        if op == "Tf" and nums:
            size = nums[-1] or size
        elif op == "Tm" and len(nums) >= 6:
            x, y = nums[-2], nums[-1]
        elif op in ("Td", "TD") and len(nums) >= 2:
            x, y = x + nums[-2], y + nums[-1]
            lead = abs(nums[-1]) or lead if op == "TD" else lead
        elif op == "TL" and nums:
            lead = nums[-1] or lead
        elif op == "T*":
            y -= lead
        elif op in ("Tj", "TJ", "'", '"'):
            if op in ("'", '"'):
                y -= lead
            txt = "".join(v for t, v in stack if t == "s")
            if txt.strip():
                out.append({"i": len(out) + 1, "x": round(x, 1), "y": round(y, 1),
                            "size": round(size, 1), "text": txt})
                x += 0.5 * size * max(len(txt), 1)
        stack = []
    return out


def _lines(chunks, lo=0.0, hi=1e9):
    lines = {}
    for c in chunks:
        if lo <= c["x"] < hi:
            lines.setdefault(int(round(c["y"])), []).append(c)
    return [" ".join(t["text"].strip() for t in sorted(lines[k], key=lambda z: z["x"]) if t["text"].strip())
            for k in sorted(lines, reverse=True)]


def assemble(chunks, width=612.0):
    """Page text from blocks; a two-column layout is read column by column."""
    if not chunks:
        return "", "empty"
    xs = [c["x"] for c in chunks]
    two = False
    if len(chunks) >= 8 and width > 200:
        left = len([x for x in xs if x < 0.42 * width])
        right = len([x for x in xs if x > 0.55 * width])
        band = len([x for x in xs if 0.42 * width <= x <= 0.55 * width])
        two = left >= 3 and right >= 3 and band <= max(1, len(xs) // 10)
    if not two:
        return "\n".join(_lines(chunks)), "single"
    parts = _lines(chunks, 0.0, 0.5 * width) + _lines(chunks, 0.5 * width)
    return "\n".join(p for p in parts if p), "two_column"


def color_hex(v):
    if isinstance(v, list) and v:
        vals = [pnum(x) for x in v[:3]] + [0.0, 0.0]
        vals = vals[:3]
        if any(abs(x) > 1.01 for x in vals):
            vals = [x / 255.0 for x in vals]
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x * 255)))) for x in vals)
    return None


def text_in_rect(chunks, rect, tol=4.0):
    """(line_text, covered_text, coverage) guessed from block geometry vs /Rect."""
    if not rect or not chunks:
        return "", "", 0.0
    x0, y0, x1, y1 = rect
    hits = []
    for c in chunks:
        w = max(0.5 * c["size"] * len(c["text"]), 1.0)
        if not (y0 - tol <= c["y"] <= y1 + tol) or c["x"] > x1 + tol or c["x"] + w < x0 - tol:
            continue
        f0, f1 = max(0.0, (x0 - c["x"]) / w), min(1.0, (x1 - c["x"]) / w)
        if f1 <= f0:
            f0, f1 = 0.0, 1.0
        a, b = int(f0 * len(c["text"])), int(round(f1 * len(c["text"])))
        hits.append((c, c["text"][a:max(a + 1, b)].strip(), f1 - f0))
    if not hits:
        return "", "", 0.0
    hits.sort(key=lambda h: (-h[0]["y"], h[0]["x"]))
    size = max([h[0]["size"] for h in hits] or [12.0])
    if (y1 - y0) <= 2.2 * size:                     # rect spans one text line: keep the best one
        lines = {}
        for c, cov, f in hits:
            lines.setdefault(int(round(c["y"])), []).append((c, cov, f))
        score = {k: sum(v[2] for v in vs) for k, vs in lines.items()}
        best = max(score.values())
        hits = [h for k, vs in lines.items() if score[k] >= 0.6 * best for h in vs]
        hits.sort(key=lambda h: (-h[0]["y"], h[0]["x"]))
    return (" ".join(h[0]["text"].strip() for h in hits if h[0]["text"].strip()),
            " ".join(h[1] for h in hits if h[1]), round(sum(h[2] for h in hits) / len(hits), 2))


def pdf_extract(p):
    raw = Path(p).read_bytes()
    objs, cache = scan_objects(raw), {}
    order = page_refs(objs, cache)
    pages, annots, notes = [], [], []
    if not objs:
        notes.append("pdf object scan failed (damaged or encrypted)")
    for k, num in enumerate(order):
        pd = parsed(objs, cache, num)
        box = rect_of(deref(objs, pd.get("/MediaBox")))
        width = (box[2] - box[0]) if box else 612.0
        cont = deref(objs, pd.get("/Contents"))
        streams = cont if isinstance(cont, list) else [pd.get("/Contents")]
        chunks = []
        for s in streams if isinstance(streams, list) else []:
            ref = s[1] if isinstance(s, tuple) and s and s[0] == "ref" else None
            data = stream_data(objs.get(ref, b"")) if ref is not None else b""
            if data and (b"Tj" in data or b"TJ" in data):
                chunks += content_chunks(data)
        text, layout = assemble(chunks, width)
        pages.append({"page": k + 1, "locator": "p%d" % (k + 1), "text": text, "layout": layout, "width": width})
        al = deref(objs, pd.get("/Annots"))
        for a in al if isinstance(al, list) else []:
            ad = pdict(objs, a)
            if not isinstance(ad, dict) or ad.get("/Subtype") == "/Popup":
                continue
            rect = rect_of(deref(objs, ad.get("/Rect")))
            qp = deref(objs, ad.get("/QuadPoints"))
            line, cover, frac = text_in_rect(chunks, rect)
            typ = SUB.get(ad.get("/Subtype"), "unknown")
            if typ in ("margin_note", "handwritten", "region_mark"):
                cover, frac = "", 0.0          # note bodies anchor by position, not by covered text
            annots.append({"page": k + 1, "rect": rect,
                           "quadpoints": [round(pnum(v), 1) for v in qp] if isinstance(qp, list) else None,
                           "raw_subtype": ad.get("/Subtype") or "", "type": typ,
                           "color": color_hex(deref(objs, ad.get("/C"))),
                           "author": _dec(deref(objs, ad.get("/T"))) if ad.get("/T") else "",
                           "created": _dec(deref(objs, ad.get("/M"))) if ad.get("/M") else "",
                           "comment": norm(_dec(deref(objs, ad.get("/Contents")))) if ad.get("/Contents") else "",
                           "line_text": line, "rect_text": cover, "rect_overlap": frac, "source": "pdf_annots"})
    if not pages:
        pages = [{"page": 1, "locator": "p1", "text": "", "chunks": [], "layout": "empty", "width": 612.0}]
    has_text = any(pg["text"].strip() for pg in pages)
    if not has_text:
        notes.append("no_text_layer: no extractable text (scan or vector-only page)")
    if any(pg["layout"] == "two_column" for pg in pages):
        notes.append("two_column_layout: blocks ordered column-first")
    return {"pages": pages, "annots": annots, "engine": "builtin-pdf", "notes": notes,
            "has_text_layer": has_text, "n_pages": len(order) or len(pages)}
