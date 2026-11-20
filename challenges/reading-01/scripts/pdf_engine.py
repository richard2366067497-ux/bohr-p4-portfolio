# -*- coding: utf-8 -*-
"""pdf_engine: pure-stdlib PDF text layer, layout rebuild and reading order.

Content streams are decoded with zlib plus a small object scanner (no xref needed). Text becomes
words with a bbox and font size; lines are rebuilt here rather than trusted from an engine, because
some engines merge a two-column page into one line. Reading order follows whitespace gutters measured
on words. Coordinates are top-left origin, pages are 1-based. An optional pymupdf accelerator is used
only if already installed. Anything undecodable is reported as a flag, never guessed.
"""
import json, os, re, zlib

MATH_RE = re.compile(r"[=≈≤≥∑∏∫√∞∂∆αβγδεθλμνπρστφχψωΓΔΘΛΞΠΣΦΨΩ^_{}]")
HEAD_WORDS = ("abstract", "introduction", "background", "related work", "methods", "method",
              "materials and methods", "results", "discussion", "conclusion", "conclusions",
              "references", "bibliography", "acknowledgements", "acknowledgments", "appendix",
              "supplementary", "data availability", "author contributions", "limitations")
CAP_RE = re.compile(r"^\s*(?:fig(?:ure)?\.?|table|tab\.|scheme|chart|algorithm|"
                    r"supplementary\s+(?:fig(?:ure)?\.?|table))\s*"
                    r"(?:S)?([0-9]{1,3}[A-Za-z]?)(?![0-9A-Za-z])", re.I)
NUM_HEAD_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(\S.{0,110})$")
CAP_VERB_RE = re.compile(r"^\s*(reports?|shows?|summari[sz]es?|presents?|gives?|lists?|compares?|"
                         r"displays?|illustrates?|depicts?|contains?|provides?)\b", re.I)

# ---------------------------------------------------------------- pdf stdlib
FLAG = []


def _flags(msg):
    if msg not in FLAG:
        FLAG.append(msg)


class PDFError(Exception):
    pass


def read_objects(data):
    objs = {}
    for m in re.finditer(rb"(?<![0-9])(\d{1,7})\s+(\d{1,5})\s+obj\b", data):
        start, end = m.end(), data.find(b"endobj", m.end())
        objs[int(m.group(1))] = data[start:end if end >= 0 else min(len(data), start + 4_000_000)]
    return objs


def stream_bytes(body):
    i = body.find(b"stream")
    if i < 0:
        return None
    j = i + 6
    if body[j:j + 2] == b"\r\n":
        j += 2
    elif body[j:j + 1] in (b"\n", b"\r"):
        j += 1
    k = body.find(b"endstream", j)
    raw, head = body[j:k if k >= 0 else len(body)], body[:i]
    if b"/FlateDecode" in head:
        for trim in (0, 1, 2):
            try:
                return zlib.decompress(raw[:len(raw) - trim] if trim else raw)
            except zlib.error:
                continue
        _flags("flate_decode_failed")
        return None
    if b"/ASCIIHexDecode" in head:
        try:
            return bytes.fromhex(re.sub(rb"[^0-9A-Fa-f]", b"", raw.split(b">")[0]).decode("ascii"))
        except ValueError:
            return None
    if b"/Filter" not in head:
        return raw
    _flags("unsupported_filter")
    return None


def refs(value):
    return [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", value or b"")]


def dict_slice(body, key):
    m = re.search(rb"/" + key + rb"\b", body or b"")
    if not m:
        return None
    i = m.end()
    while i < len(body) and body[i:i + 1] in (b" ", b"\n", b"\r", b"\t"):
        i += 1
    if body[i:i + 1] == b"[":
        depth, j = 0, i
        while j < len(body):
            c = body[j:j + 1]
            if c == b"[":
                depth += 1
            elif c == b"]":
                depth -= 1
                if depth == 0:
                    return body[i:j + 1]
            j += 1
        return body[i:]
    m2 = re.match(rb"(<<.*?>>|/\w+|[-\d.]+\s+[-\d.]+\s+R|\d+\s+\d+\s+R)", body[i:], re.S)
    return m2.group(1) if m2 else None


def nums(value, default=None):
    if value is None:
        return default
    try:
        return [float(x) for x in re.findall(rb"-?\d+\.?\d*", value)]
    except ValueError:
        return default


def decode_text_string(tok):
    if tok.startswith(b"<") and not tok.startswith(b"<<"):
        hexs = re.sub(rb"[^0-9A-Fa-f]", b"", tok[1:-1])
        if len(hexs) % 2:
            hexs += b"0"
        try:
            return bytes.fromhex(hexs.decode("ascii"))
        except ValueError:
            return b""
    body, out, i = tok[1:-1], bytearray(), 0
    table = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
             b"(": b"(", b")": b")", b"\\": b"\\"}
    while i < len(body):
        c = body[i:i + 1]
        if c == b"\\" and i + 1 < len(body):
            n = body[i + 1:i + 2]
            if n in table:
                out += table[n]
                i += 2
            elif n.isdigit():
                m = re.match(rb"[0-7]{1,3}", body[i + 1:i + 4])
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
            else:
                i += 2
        else:
            out += c
            i += 1
    return bytes(out)


def _utf16(hexbytes):
    try:
        raw = bytes.fromhex(hexbytes.decode() if isinstance(hexbytes, bytes) else hexbytes)
    except (ValueError, AttributeError):
        return ""
    return raw.decode("utf-16-be", "replace")


def parse_tounicode(cmap):
    table = {}
    if not cmap:
        return table
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            try:
                table[int(src, 16)] = _utf16(dst)
            except ValueError:
                continue
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", cmap, re.S):
        for m in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])", block):
            lo, hi, dst = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            if dst.startswith(b"["):
                for off, p in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", dst)):
                    if lo + off <= hi:
                        table[lo + off] = _utf16(p)
            else:
                base = bytearray(bytes.fromhex(dst[1:-1].decode()) or b"\x00")
                span = max(1, hi - lo + 1)
                if span > 65536:
                    continue
                for off in range(span):
                    b = bytearray(base)
                    if b:
                        b[-1] = (b[-1] + off) & 0xFF
                    table[lo + off] = _utf16(b.hex().encode())
    return table


SIMPLE_MAP = {b: chr(b) for b in range(32, 127)}
GLYPH_MAP = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "theta": "θ",
             "lambda": "λ", "mu": "μ", "nu": "ν", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ",
             "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ",
             "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ",
             "Omega": "Ω", "minus": "−", "plusminus": "±", "approxequal": "≈", "lessequal": "≤",
             "greaterequal": "≥", "infinity": "∞", "summation": "∑", "radical": "√", "partialdiff": "∂",
             "degree": "°", "multiply": "×", "divide": "÷", "notequal": "≠", "periodcentered": "·"}


def build_fonts(body, objs):
    fonts = {}
    fdict = dict_slice(body, b"Font")
    if not fdict:
        return fonts
    for name, num in re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+\d+\s+R", fdict):
        fbody = objs.get(int(num), b"")
        two = b"/Type0" in fbody or b"Identity" in fbody
        cmap, glyphs = {}, {}
        tu = dict_slice(fbody, b"ToUnicode")
        for ref in refs(tu):
            if ref in objs:
                cmap = parse_tounicode(stream_bytes(objs[ref]))
                break
        diffs = dict_slice(fbody, b"Differences")
        if diffs:
            cur = None
            for tok in re.findall(rb"(\d{1,3})|/([A-Za-z0-9_.+-]+)", diffs or b""):
                if tok[0]:
                    cur = int(tok[0])
                elif tok[1] is not None and cur is not None:
                    nm = tok[1].decode("latin-1")
                    if nm in GLYPH_MAP:
                        glyphs[cur] = GLYPH_MAP[nm]
                    cur += 1
        fonts[name.decode("latin-1")] = {"two_byte": two, "map": cmap, "glyphs": glyphs}
    return fonts


TOKEN = re.compile(rb"\s*(?:(?P<num>-?\d*\.?\d+)|/(?P<name>[A-Za-z0-9#_.+-]*)|"
                   rb"(?P<str>\()|(?P<hex><[0-9A-Fa-f\s]*>)|(?P<arr>\[)|(?P<arrend>\])|"
                   rb"(?P<dict><<)|(?P<dictend>>>)|(?P<op>[A-Za-z'\"*]+))")


def tokenize(stream):
    pos, n = 0, len(stream)
    while pos < n:
        m = TOKEN.match(stream, pos)
        if not m:
            pos += 1
            continue
        if m.group("str") is not None:
            depth, j = 1, m.end()
            while j < n and depth:
                c = stream[j:j + 1]
                if c == b"\\":
                    j += 2
                    continue
                depth += 1 if c == b"(" else (-1 if c == b")" else 0)
                j += 1
            yield ("str", stream[m.start("str"):j])
            pos = j
            continue
        if m.group("num") is not None:
            yield ("num", m.group("num"))
        elif m.group("name") is not None:
            yield ("name", m.group("name"))
        elif m.group("hex") is not None:
            yield ("hex", m.group("hex"))
        elif m.group("arr"):
            yield ("[", b"[")
        elif m.group("arrend"):
            yield ("]", b"]")
        elif m.group("op"):
            yield ("op", m.group("op"))
        pos = m.end()


def decode_show(raw, font):
    if not font:
        return raw.decode("latin-1", "replace")
    glyphs = font.get("glyphs") or {}
    if font["two_byte"] or (font["map"] and max(font["map"]) > 255):
        return "".join(font["map"].get((raw[i] << 8) | raw[i + 1], "") for i in range(0, len(raw) - 1, 2))
    if font["map"]:
        return "".join(font["map"].get(b, glyphs.get(b, chr(b) if 32 <= b < 127 else "")) for b in raw)
    return "".join(glyphs.get(b, chr(b) if 32 <= b < 127 or b in (9, 10) else
                             (SIMPLE_MAP.get(b) or (" " if b == 160 else ""))) for b in raw)


def parse_content(stream, fonts):
    chunks, stack, font, size = [], [], None, 10.0
    x = y = leading = 0.0
    leading = 12.0
    for kind, val in tokenize(stream):
        if kind in ("num", "str", "hex", "name", "["):
            stack.append(val)
            continue
        if kind == "]":
            continue
        op = val
        nums_ = [s for s in stack if re.fullmatch(rb"-?\d*\.?\d+", s or b"")]
        if op == b"Tf":
            names = [s for s in stack if isinstance(s, bytes) and s.decode("latin-1") in fonts]
            if names:
                font = fonts.get(names[0].decode("latin-1"))
            if nums_:
                try:
                    size = float(nums_[-1])
                except ValueError:
                    pass
        elif op in (b"Td", b"TD") and len(nums_) >= 2:
            try:
                tx, ty = float(nums_[-2]), float(nums_[-1])
                x, y = x + tx, y + ty
                if op == b"TD":
                    leading = -ty
            except ValueError:
                pass
        elif op == b"Tm" and len(nums_) >= 6:
            try:
                x, y = float(nums_[-2]), float(nums_[-1])
            except ValueError:
                pass
        elif op == b"T*":
            y -= leading or 12.0
        elif op == b"TL" and nums_:
            try:
                leading = float(nums_[-1])
            except ValueError:
                pass
        elif op in (b"Tj", b"TJ", b"'", b'"'):
            text = "".join(decode_show(decode_text_string(s), font) for s in stack
                           if isinstance(s, bytes) and s[:1] in (b"(", b"<") and s != b"[")
            if op in (b"'", b'"'):
                y -= leading or 12.0
            if text.strip():
                chunks.append({"x": round(x, 2), "y": round(y, 2), "size": round(size, 2), "text": text})
            if op in (b"'", b'"'):
                x = 0.0
        stack = []
    return chunks


def pages_of(data):
    objs = read_objects(data)
    if not objs:
        raise PDFError("no_indirect_objects")
    if b"/Encrypt" in data:
        _flags("encrypted_pdf")
    page_nums = sorted(n for n, b in objs.items() if re.search(rb"/Type\s*/Page\b(?!s)", b))
    if not page_nums:
        _flags("no_page_objects")
        raise PDFError("no_page_objects")
    out = []
    for idx, num in enumerate(page_nums, start=1):
        body, box = objs[num], None
        for key in (b"MediaBox", b"CropBox"):
            got = nums(dict_slice(body, key))
            if got and len(got) >= 4:
                box = got[:4]
                break
        if box is None:
            for ref in refs(dict_slice(body, b"Parent")):
                got = nums(dict_slice(objs.get(ref, b""), b"MediaBox"))
                if got and len(got) >= 4:
                    box = got[:4]
                    break
        width = (box[2] - box[0]) if box else 612.0
        height = (box[3] - box[1]) if box else 792.0
        blobs = [s for s in (stream_bytes(objs.get(r, b"")) for r in refs(dict_slice(body, b"Contents"))) if s]
        if not blobs:
            _flags("page_without_content")
        res = body
        if b"/Font" not in res:
            for ref in refs(dict_slice(body, b"Resources")):
                if b"/Font" in objs.get(ref, b""):
                    res = objs[ref]
                    break
        fonts = build_fonts(res, objs)
        chunks = []
        for blob in blobs:
            chunks.extend(parse_content(blob, fonts))
        out.append({"page": idx, "width": round(width, 1), "height": round(height, 1), "chunks": chunks})
    return out


def extract(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"%PDF"):
        raise PDFError("not_a_pdf")
    pages = pages_of(data)
    total = sum(len(p["chunks"]) for p in pages)
    meta = {"engine": "stdlib", "flags": list(FLAG), "chunks": total, "encrypted": b"/Encrypt" in data}
    if total == 0:
        meta["flags"].append("no_text_layer")
    return pages, meta


# ---------------------------------------------------------------- layout
def is_caption(text):
    m = CAP_RE.match(text or "")
    if not m:
        return False
    rest = (text or "")[m.end():]
    if CAP_VERB_RE.match(rest):
        return False
    if rest[:1] in (".", ":", "|", ")", "—", "–", "-"):
        return True
    return len((text or "").strip()) <= 70 and not (text or "").rstrip().endswith(".")


def _median(vals, default=10.0):
    vals = sorted(v for v in vals if v)
    return vals[len(vals) // 2] if vals else default


def _word(x0, y0, x1, y1, text, size):
    if not text or not text.strip():
        return None
    return {"x0": round(float(x0), 2), "y0": round(float(y0), 2), "x1": round(float(x1), 2),
            "y1": round(float(y1), 2), "text": text, "size": round(float(size or (y1 - y0) or 10.0), 2)}


def _split_words(text, x0, x1):
    out, parts, total = [], text.split(" "), max(1, len(text))
    for piece in parts:
        if not piece:
            x0 += (x1 - x0) / total
            continue
        w = (x1 - x0) * len(piece) / total
        out.append((x0, x0 + w, piece))
        x0 += w + (x1 - x0) / total
    return out


def engine_pymupdf(path, max_pages):
    import pymupdf as fitz
    doc = fitz.open(path)
    if getattr(doc, "is_encrypted", False):
        raise RuntimeError("encrypted_pdf")
    pages = []
    for i in range(min(doc.page_count, max_pages)):
        pg, words = doc[i], []
        for blk in pg.get_text("dict").get("blocks", []):
            if blk.get("type") != 0:
                continue
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    txt = sp.get("text", "")
                    if not txt.strip():
                        continue
                    bx = sp.get("bbox") or ln.get("bbox") or [0, 0, 0, 0]
                    for wx0, wx1, piece in _split_words(txt, bx[0], bx[2]):
                        w = _word(wx0, bx[1], wx1, bx[3], piece, sp.get("size") or (bx[3] - bx[1]))
                        if w:
                            words.append(w)
        pages.append({"page": i + 1, "width": pg.rect.width, "height": pg.rect.height, "words": words})
    doc.close()
    return pages, {"engine": "pymupdf"}


def engine_stdlib(path, max_pages):
    pages, meta = extract(path)
    out = []
    for p in pages[:max_pages]:
        H, words = p["height"], []
        for ch in p["chunks"]:
            txt = ch.get("text") or ""
            if not txt.strip():
                continue
            size = ch.get("size") or 10.0
            y_top, x0 = H - ch["y"], ch["x"]
            for wx0, wx1, piece in _split_words(txt, x0, x0 + len(txt) * size * 0.5):
                item = _word(wx0, y_top, wx1, y_top + size * 1.1, piece, size)
                if item:
                    words.append(item)
        out.append({"page": p["page"], "width": p["width"], "height": H, "words": words})
    meta["engine"] = "stdlib"
    return out, meta


ENGINES = [("pymupdf", engine_pymupdf), ("stdlib", engine_stdlib)]


def extract_layout(path, max_pages=60, prefer="auto"):
    notes = []
    order = ENGINES if prefer in ("auto", None) else \
        [e for e in ENGINES if e[0] == prefer] + [e for e in ENGINES if e[0] != prefer]
    for name, fn in order:
        try:
            pages, meta = fn(path, max_pages)
        except Exception as exc:
            notes.append({"engine": name, "error": type(exc).__name__ + ": " + str(exc)[:140]})
            continue
        chars = sum(len(w["text"]) for p in pages for w in p["words"])
        if not pages or chars < 40:
            notes.append({"engine": name, "error": "insufficient_text:%d" % chars})
            continue
        for p in pages:
            finalize_page(p)
        kept = [p for p in pages if p["lines"]]
        if not kept:
            notes.append({"engine": name, "error": "no_line_rebuilt"})
            continue
        meta.update({"engine_notes": notes, "chars": chars, "file": os.path.basename(path),
                     "pages": len(kept)})
        if meta.get("flags"):
            meta["flags"] = sorted(set(meta["flags"]))
        return kept, meta
    raise RuntimeError("all_engines_failed: " + json.dumps(notes, ensure_ascii=False))


def _cluster_rows(words, height):
    rows, cur, ref = [], [], None
    for w in sorted(words, key=lambda w: (w["y0"], w["x0"])):
        if ref is None or abs(w["y0"] - ref) <= 0.55 * height:
            cur.append(w)
            ref = w["y0"] if ref is None else ref
        else:
            rows.append(cur)
            cur, ref = [w], w["y0"]
    if cur:
        rows.append(cur)
    return rows


def _find_gutters(rows, W, H):
    """A gutter is a wide inter-word gap shared by many rows (survives spanning titles)."""
    if len(rows) < 6:
        return []
    n = int(W) + 2
    gap_cov = [0] * n
    for r in rows:
        ws = sorted(r, key=lambda w: w["x0"])
        for a, b in zip(ws, ws[1:]):
            if b["x0"] - a["x1"] < 6:
                continue
            for x in range(max(0, int(a["x1"])), min(n - 1, int(b["x0"])) + 1):
                gap_cov[x] += 1
    thr = max(4, int(0.15 * len(rows)))
    runs, run = [], None
    for x in range(n):
        if gap_cov[x] >= thr and run is None:
            run = x
        elif gap_cov[x] < thr and run is not None:
            runs.append((run, x))
            run = None
    if run is not None:
        runs.append((run, n - 1))
    keep = []
    for a, b in runs:
        if b - a < max(9.0, 0.015 * W) or a < 0.04 * W or b > 0.96 * W:
            continue
        strad = [r for r in rows if any(w["x1"] <= a + 5 for w in r) and any(w["x0"] >= b - 5 for w in r)]
        if len(strad) < 3:
            continue
        y0 = min(min(w["y0"] for w in r) for r in strad)
        y1 = max(max(w["y1"] for w in r) for r in strad)
        if (y1 - y0) < max(120.0, 0.15 * H):
            continue
        keep.append((a, b))
    keep.sort(key=lambda g: g[1] - g[0], reverse=True)
    return sorted(keep[:2])


def finalize_page(page):
    W, H = page["width"] or 612.0, page["height"] or 792.0
    words = [w for w in page["words"] if w["text"].strip()]
    height = _median([w["y1"] - w["y0"] for w in words], 10.0)
    rows = _cluster_rows(words, height)
    gutters = _find_gutters(rows, W, H)
    lines = []
    right_start = {}
    for a, b in gutters:
        starts = [w["x0"] for w in words if w["x0"] > b]
        right_start[(a, b)] = min(starts) if starts else b
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        segs, cur = [], [row[0]]
        for w in row[1:]:
            cut = any(cur[-1]["x1"] < a and w["x0"] > b and (w["x0"] - cur[-1]["x1"]) > 8
                      and w["x0"] >= right_start[(a, b)] - 6 for a, b in gutters)
            if cut:
                segs.append(cur)
                cur = [w]
            else:
                cur.append(w)
        segs.append(cur)
        for seg in segs:
            lines.append({"x0": min(w["x0"] for w in seg), "y0": min(w["y0"] for w in seg),
                          "x1": max(w["x1"] for w in seg), "y1": max(w["y1"] for w in seg),
                          "size": round(_median([w["size"] for w in seg], height), 2),
                          "text": " ".join(w["text"] for w in seg),
                          "words": [{"x0": w["x0"], "x1": w["x1"], "text": w["text"]} for w in seg]})
    seen, kept = set(), []
    for ln in lines:
        sig = (round(ln["y0"], 0), re.sub(r"\s+", "", ln["text"]))
        if sig not in seen:
            seen.add(sig)
            kept.append(ln)
    page["lines"] = kept
    page["gutters"] = [[round(a, 1), round(b, 1)] for a, b in gutters]
    page["height"], page["width"] = H, W
    return page


def _sig(t):
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", (t or "").strip().lower()))[:90]


def mark_running_matter(pages):
    norm = {}
    for p in pages:
        H = p["height"] or 792
        for ln in p["lines"]:
            if ln["y1"] < 0.085 * H or ln["y0"] > 0.925 * H:
                norm.setdefault(_sig(ln["text"]), set()).add(p["page"])
    repeated = {k for k, v in norm.items() if len(v) >= 3}
    for p in pages:
        H = p["height"] or 792
        for ln in p["lines"]:
            band = ln["y1"] < 0.085 * H or ln["y0"] > 0.925 * H
            ln["band"] = band
            ln["running"] = bool(band and (_sig(ln["text"]) in repeated or
                                           re.fullmatch(r"[\s\-–—|·•0-9]+", ln["text"] or "")))
    return pages


def page_objects(page):
    W = page["width"] or 612
    body = [l for l in page["lines"] if not l.get("running")]
    gut = [tuple(g) for g in page.get("gutters") or []]
    bounds = [0.0] + [x for g in gut for x in g] + [W]
    cols = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds) - 1, 2)]
    for l in body:
        hits = [i for i, (a, b) in enumerate(cols)
                if min(l["x1"], b) - max(l["x0"], a) > 0.5 * max(1.0, l["x1"] - l["x0"])]
        l["col"] = hits[0] if len(hits) == 1 else -1
        l["spanning"] = len(hits) > 1
    body.sort(key=lambda l: (round(l["y0"], 1), l["x0"]))
    bands, cur = [], []
    for l in body:
        if l["spanning"]:
            if cur:
                bands.append(("cols", cur))
                cur = []
            bands.append(("span", [l]))
        else:
            cur.append(l)
    if cur:
        bands.append(("cols", cur))
    ordered = []
    for kind, group in bands:
        if kind == "span":
            ordered.extend(sorted(group, key=lambda l: l["y0"]))
            continue
        for ci in range(len(cols)):
            ordered.extend(sorted([l for l in group if l["col"] == ci], key=lambda l: l["y0"]))
        ordered.extend(sorted([l for l in group if l["col"] == -1], key=lambda l: l["y0"]))
    return ordered, cols, gut


def _heading_level(line, med_size, W):
    t = (line["text"] or "").strip()
    if not t or len(t) > 140:
        return 0
    low = re.sub(r"^\d+(\.\d+)*\.?\s*", "", t.lower()).strip(" .:：")
    if low in HEAD_WORDS:
        return 1
    m = NUM_HEAD_RE.match(t)
    if m and not t.rstrip().endswith((".", ";", ",")) and len(t.split()) <= 14:
        return min(4, m.group(1).count(".") + 1)
    if MATH_RE.search(t) and "=" in t:
        return 0
    size = line.get("size") or 10
    if size >= med_size * 1.18 and len(t) < 100 and not t.endswith((".", ",")):
        return 1 if size >= med_size * 1.35 else 2
    if t.isupper() and 4 <= len(t) <= 70 and len(t.split()) <= 9:
        return 2
    return 0


def _rowish(ln, size):
    ws = ln.get("words") or []
    if len(ws) < 3:
        return False
    gaps = 0
    for a, b in zip(ws, ws[1:]):
        end = a.get("x1") or (a["x0"] + len(a["text"]) * 0.5 * max(6.0, size))
        if (b["x0"] - end) > 1.2 * max(6.0, size):
            gaps += 1
    return gaps >= 2


def blockify(ordered_lines, med_size, W, col_left=None):
    col_left = col_left or {}
    blocks = []
    for ln in ordered_lines:
        text = ln["text"].strip()
        if not text:
            continue
        prev0 = blocks[-1] if blocks else None
        if prev0 and prev0["type"] == "formula" and re.fullmatch(r"\(\s*\d{1,3}[a-z]?\s*\)", text):
            prev0["text"] += " " + text
            prev0["_y1"] = ln["y1"]
            continue
        lvl, cap = _heading_level(ln, med_size, W), is_caption(text)
        is_formula = bool(MATH_RE.search(text)) and len(text) < 170 and \
            sum(text.count(c) for c in "=±≈<>") >= 1
        if is_formula:
            kind, lvl = "formula", 0
        elif lvl:
            kind = "heading"
        elif cap:
            kind = "caption"
        elif _rowish(ln, ln["size"]):
            kind = "table_row"
        else:
            kind = "paragraph"
        prev = blocks[-1] if blocks else None
        gap = (ln["y0"] - prev["_y1"]) if prev else 999
        col = ln.get("col", -1)
        indented = (ln["x0"] - col_left.get(col, 0.0)) > 0.9 * max(6.0, ln["size"])
        closed = bool(prev) and bool(re.search(r"[.!?。！？:：]$", prev["text"].strip()))
        lower_next = bool(re.match(r"^[a-z一-鿿(（\"']", text))
        continuation = (not closed) or lower_next
        joinable = bool(prev and kind == "paragraph" and prev["type"] == "paragraph"
                        and prev["_col"] == col and col >= 0 and not indented
                        and gap < 1.7 * max(6.0, ln["size"]) and gap > -2 and continuation
                        and not prev["_ends_caption"])
        if joinable:
            sep = "" if prev["text"].rstrip().endswith("-") else " "
            prev["text"] = prev["text"].rstrip("-") + sep + text
            prev["_y1"], prev["_x1"] = ln["y1"], ln["x1"]
            prev["lines"].append(text)
            continue
        blocks.append({"type": kind, "text": text,
                       "bbox": [round(ln["x0"], 1), round(ln["y0"], 1), round(ln["x1"], 1), round(ln["y1"], 1)],
                       "size": ln["size"], "level": lvl, "col": col, "words": ln.get("words", []),
                       "lines": [text], "_y1": ln["y1"], "_x1": ln["x1"], "_x0": ln["x0"], "_col": col,
                       "_ends_caption": bool(is_caption(text))})
    for b in blocks:
        for k in [k for k in list(b) if k.startswith("_")]:
            b.pop(k)
    return blocks


def page_entries(pages):
    out = []
    for p in pages:
        W = p["width"] or 612
        med = _median([l["size"] for l in p["lines"] if 4 < l["size"] < 40], 10.0)
        ordered, cols, gut = page_objects(p)
        col_left = {}
        for ln in ordered:
            c = ln.get("col", -1)
            if c >= 0:
                col_left[c] = min(col_left.get(c, 1e9), ln["x0"])
        objs = []
        for i, b in enumerate(blockify(ordered, med, W, col_left), start=1):
            objs.append({"oid": "p%d-b%02d" % (p["page"], i), "page": p["page"], "type": b["type"],
                         "bbox": b["bbox"], "text": b["text"], "size": b["size"], "level": b["level"],
                         "reading_index": i, "col": b["col"], "words": b.get("words") or [], "flags": []})
        running = [{"oid": "p%d-x%02d" % (p["page"], i), "page": p["page"], "type": "running_matter",
                    "bbox": [round(l["x0"], 1), round(l["y0"], 1), round(l["x1"], 1), round(l["y1"], 1)],
                    "text": l["text"].strip(), "size": l["size"], "level": 0, "reading_index": None,
                    "col": -1, "flags": ["excluded_running_matter"]}
                   for i, l in enumerate([l for l in p["lines"] if l.get("running")], start=1)]
        out.append({"page": p["page"], "width": W, "height": p["height"] or 792, "columns": len(cols),
                    "gutters": [[round(a, 1), round(b, 1)] for a, b in gut],
                    "median_size": round(med, 1), "objects": objs, "excluded": running})
    return out


def text_page(path):
    """A text material becomes one synthetic page so the same pipeline can run on it."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return None
    lines, y = [], 0.0
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        lines.append({"x0": 40.0, "y0": y, "x1": 40.0 + 5.6 * len(ln), "y1": y + 11, "size": 10.0,
                      "text": ln, "band": False, "running": False,
                      "words": [{"x0": 40.0, "text": w} for w in ln.split()]})
        y += 13.0
    return {"page": 1, "width": 595.0, "height": max(842.0, y + 40), "lines": lines}


def parse_document(path, max_pages=60, prefer="auto"):
    pages, meta = extract_layout(path, max_pages=max_pages, prefer=prefer)
    pages = mark_running_matter(pages)
    return {"entries": page_entries(pages), "meta": meta}
