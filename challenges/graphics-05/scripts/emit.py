"""emit.py - SVG, PDF and PNG exporters plus a pixel probe over one display list.

Layer names, ids and geometry are stable, so the same model re-emits identical bytes.
"""
import json
import struct
import subprocess
import shutil
import zlib

from layout import LAYERS, tw, hex_rgb

SVG_NS = "http://www.w3.org/2000/svg"

def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))

def _num(v):
    return ("%.2f" % float(v)).rstrip("0").rstrip(".")

def model_digest(model):
    payload = {k: model.get(k) for k in ("canvas", "title", "panels", "elements", "encodings", "legend")}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "%08x" % (zlib.crc32(blob) & 0xFFFFFFFF)

def to_svg(model):
    cv = model["canvas"]
    W, H = cv["w_pt"], cv["h_pt"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="%s" version="1.1" width="%s" height="%s" viewBox="0 0 %s %s" '
           'data-model-digest="%s" role="img" aria-labelledby="ga-title">' %
           (SVG_NS, cv.get("svg_attrs") or _num(W), cv.get("svg_attrs_h") or _num(H),
            _num(W), _num(H), model_digest(model)),
           '  <title id="ga-title">%s</title>' % _esc(model.get("title")),
           '  <desc id="ga-desc">%s</desc>' % _esc(
               "Panels: %s. Every panel, arrow and encoding mark is listed in content_map.json with a "
               "source locator and a verbatim quote." %
               "; ".join("%d %s" % (p["order"], p["role"]) for p in model["panels"])),
           '  <defs><style type="text/css"><![CDATA[text{font-family:Helvetica,Arial,'
           '"Helvetica Neue","Noto Sans","Source Han Sans SC",sans-serif;}]]></style></defs>',
           '  <metadata><ga:model xmlns:ga="urn:ga-trace" digest="%s" panels="%d" elements="%d"/>'
           '</metadata>' % (model_digest(model), len(model["panels"]), len(model["elements"]))]
    groups = dict((name, []) for name in LAYERS)
    for op in model["ops"]:
        groups.setdefault(op.get("layer") or "labels", []).append(op)
    for name in LAYERS:
        out.append('  <g id="layer-%s" data-layer="%s">' % (name, name))
        for op in groups.get(name) or []:
            oid = (' id="%s"' % _esc(op["id"])) if op.get("id") else ""
            if op["op"] == "rect":
                st = ""
                if op.get("stroke"):
                    st = ' stroke="%s" stroke-width="%s"' % (op["stroke"], _num(op["sw"]))
                    if op.get("dash"):
                        st += ' stroke-dasharray="%s"' % op["dash"]
                rx = ' rx="%s"' % _num(op["rx"]) if op.get("rx") else ""
                out.append('    <rect%s x="%s" y="%s" width="%s" height="%s" fill="%s"%s%s/>' %
                           (oid, _num(op["x"]), _num(op["y"]), _num(op["w"]), _num(op["h"]),
                            op.get("fill") or "none", st, rx))
            elif op["op"] == "line":
                out.append('    <line%s x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                           'stroke-width="%s" stroke-linecap="round"/>' %
                           (oid, _num(op["x1"]), _num(op["y1"]), _num(op["x2"]), _num(op["y2"]),
                            op.get("stroke") or "#000", _num(op["sw"])))
            elif op["op"] == "poly":
                pts = " ".join("%s,%s" % (_num(a), _num(b)) for a, b in op["pts"])
                out.append('    <polygon%s points="%s" fill="%s"/>' %
                           (oid, pts, op.get("fill") or "#000"))
            else:
                fw = ' font-weight="bold"' if op.get("weight") == "bold" else ""
                anchor = op.get("anchor") if op.get("anchor") in ("middle", "end") else "start"
                out.append('    <text%s x="%s" y="%s" font-size="%s" fill="%s"%s '
                           'text-anchor="%s">%s</text>' %
                           (oid, _num(op["x"]), _num(op["y"]), _num(op["size"]),
                            op.get("color") or "#000", fw, anchor, _esc(op["text"])))
        out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"

def svg_layer_report(svg_text):
    """Check the layers actually exist and text stayed editable."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg_text)
    except Exception as exc:
        return {"parsed": False, "error": str(exc), "layers": [], "text_nodes": 0, "editable_text": False}
    layers, texts = [], 0
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "g" and str(el.get("id", "")).startswith("layer-"):
            layers.append(el.get("id")[6:])
        if tag == "text":
            texts += 1
    return {"parsed": True, "layers": layers, "missing_layers": [x for x in LAYERS if x not in layers],
            "text_nodes": texts, "editable_text": texts > 0}

def _pdf_text_ops(op, W, H, cjk):
    s, size = op["text"], float(op["size"])
    x = op["x"] - (tw(s, size) / 2.0 if op.get("anchor") == "middle" else
                   tw(s, size) if op.get("anchor") == "end" else 0.0)
    base = H - op["y"] + size * 0.24
    r, g, b = hex_rgb(op.get("color") or "#000000")
    out, i = [], 0
    while i < len(s):
        j, wide = i, ord(s[i]) > 0x2E7F
        while j < len(s) and (ord(s[j]) > 0x2E7F) == wide:
            j += 1
        part = s[i:j]
        fn = "F3" if wide else ("F2" if op.get("weight") == "bold" else "F1")
        if wide:
            hx = part.encode("utf-16-be", "replace").hex().upper()
            cjk.update(hx[k:k + 4] for k in range(0, len(hx), 4))
            lit = "<%s>" % hx
        else:
            enc = part.encode("latin-1", "replace").decode("latin-1")
            lit = "(" + "".join("\\" + c if c in "()\\" else c for c in enc) + ")"
        out.append("BT /%s %.2f Tf %.3f %.3f %.3f rg 1 0 0 1 %.2f %.2f Tm %s Tj ET" %
                   (fn, size, r, g, b, x, base, lit))
        x += tw(part, size)
        i = j
    return out

def _rounded(x, yb, w, h, rad):
    rad = max(0.0, min(rad, w / 2.0, h / 2.0))
    if rad < 0.3:
        return "%s %s %s %s re" % (_num(x), _num(yb), _num(w), _num(h))
    k = 0.5523 * rad
    p = ["%s %s m" % (_num(x + rad), _num(yb)), "%s %s l" % (_num(x + w - rad), _num(yb)),
         "%s %s %s %s %s %s c" % (_num(x + w - rad + k), _num(yb), _num(x + w), _num(yb + rad - k),
                                  _num(x + w), _num(yb + rad)),
         "%s %s l" % (_num(x + w), _num(yb + h - rad)),
         "%s %s %s %s %s %s c" % (_num(x + w), _num(yb + h - rad + k), _num(x + w - rad + k),
                                  _num(yb + h), _num(x + w - rad), _num(yb + h)),
         "%s %s l" % (_num(x + rad), _num(yb + h)),
         "%s %s %s %s %s %s c" % (_num(x + rad - k), _num(yb + h), _num(x), _num(yb + h - rad + k),
                                  _num(x), _num(yb + h - rad)),
         "%s %s l" % (_num(x), _num(yb + rad)),
         "%s %s %s %s %s %s c h" % (_num(x), _num(yb + rad - k), _num(x + rad - k), _num(yb),
                                    _num(x + rad), _num(yb))]
    return " ".join(p)

def to_pdf(model):
    W, H = model["canvas"]["w_pt"], model["canvas"]["h_pt"]
    cjk, cs = set(), []
    for op in model["ops"]:
        if op["op"] == "rect":
            if not op.get("fill") and not op.get("stroke"):
                continue
            cs.append("q")
            if op.get("fill"):
                cs.append("%.3f %.3f %.3f rg" % hex_rgb(op["fill"]))
            if op.get("stroke"):
                cs.append("%.3f %.3f %.3f RG %.2f w" % (hex_rgb(op["stroke"]) + (op["sw"],)))
                if op.get("dash"):
                    cs.append("[%s] 0 d" % " ".join(op["dash"].split()))
            cs.append("%s %s %s %s re" % (_num(op["x"]), _num(H - op["y"] - op["h"]),
                                          _num(op["w"]), _num(op["h"])))
            cs.append("B" if (op.get("fill") and op.get("stroke")) else
                      ("f" if op.get("fill") else "S"))
            cs.append("Q")
        elif op["op"] == "line":
            cs.append("q %.3f %.3f %.3f RG %.2f w 1 J %s %s m %s %s l S Q" %
                      (hex_rgb(op["stroke"]) + (op["sw"], _num(op["x1"]), _num(H - op["y1"]),
                                                _num(op["x2"]), _num(H - op["y2"]))))
        elif op["op"] == "poly" and op.get("pts"):
            pts = op["pts"]
            seg = "q %.3f %.3f %.3f rg %s %s m " + " ".join(["%s %s l"] * (len(pts) - 1)) + " h f Q"
            args = list(hex_rgb(op.get("fill"))) + [v for p in pts for v in (_num(p[0]), _num(H - p[1]))]
            cs.append(seg % tuple(args))
        elif op["op"] == "text":
            cs += _pdf_text_ops(op, W, H, cjk)
    content = "\n".join(cs).encode("latin-1", "replace")
    codes = sorted(cjk)
    bf = ""
    for i in range(0, len(codes), 100):
        chunk = codes[i:i + 100]
        bf += "%d beginbfchar\n" % len(chunk) + "".join("<%s> <%s>\n" % (c, c) for c in chunk) + "endbfchar\n"
    tounicode = ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
                 "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
                 "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n1 begincodespacerange\n"
                 "<0000> <FFFF>\n"
                 "endcodespacerange\n" + bf + "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n").encode("latin-1")

    def stream(data):
        return b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"

    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Resources << /ProcSet [/PDF /Text] "
             "/Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >> /Contents 8 0 R >>" %
             (_num(W), _num(H))).encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H "
            b"/DescendantFonts [7 0 R] /ToUnicode 9 0 R >>",
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo "
            b"<< /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> /DW 1000 >>",
            stream(content), stream(tounicode),
            b"<< /Producer (ga-trace-builder) /Creator (emit.to_pdf) /ModDate (D:20000101000000Z) >>"]
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, body in enumerate(objs):
        offs.append(len(out))
        out += b"%d 0 obj\n" % (i + 1) + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offs:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R /Info 10 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return bytes(out)

def pdf_report(path):
    try:
        data = open(path, "rb").read()
    except Exception as exc:
        return {"path": path, "valid": False, "error": str(exc)}
    return {"path": path, "valid": data[:5] == b"%PDF-", "bytes": len(data),
            "pages": data.count(b"/Type /Page\n") + data.count(b"/Type /Page "),
            "ends_with_eof": data.rstrip().endswith(b"%%EOF"),
            "vector": b"/Font" in data and b" Tj " in data}

def _unpack(ch):
    """7 rows x 5 bits packed as 14 hex digits; None when the glyph is unknown."""
    code = _GLYPHS.get(ch.upper())
    if not code:
        return None
    return [bin(int(code[i:i + 2], 16))[2:].zfill(5) for i in range(0, 14, 2)]

class _Frame(object):
    def __init__(self, w, h):
        self.w, self.h = int(w), int(h)
        self.px = bytearray(b"\xff" * (self.w * self.h * 3))

    def span(self, y, x0, x1, rgb):
        if y < 0 or y >= self.h:
            return
        x0, x1 = max(0, int(x0)), min(self.w, int(x1))
        if x1 <= x0:
            return
        b, n = (y * self.w + x0) * 3, (x1 - x0) * 3
        self.px[b:b + n] = bytes(rgb) * (x1 - x0)

    def rect(self, x, y, w, h, rgb):
        if w <= 0 or h <= 0:
            return
        for yy in range(int(round(y)), int(round(y + h))):
            self.span(yy, x, x + w, rgb)

    def line(self, x1, y1, x2, y2, rgb, width=1.0):
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) * 2) + 2
        half = max(0.5, width / 2.0)
        for i in range(steps + 1):
            t = i / float(steps)
            cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            for yy in range(int(cy - half), int(cy + half) + 1):
                self.span(yy, cx - half, cx + half, rgb)

    def poly(self, pts, rgb):
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for yy in range(int(min(ys)), int(max(ys)) + 1):
            xs = []
            for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
                if (ay <= yy < by) or (by <= yy < ay):
                    xs.append(ax + (bx - ax) * (yy - ay) / float(by - ay))
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                self.span(yy, a, b, rgb)

def _png_chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload +
            struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

def write_png(frame, path):
    raw = bytearray()
    for y in range(frame.h):
        raw.append(0)
        raw += frame.px[y * frame.w * 3:(y + 1) * frame.w * 3]
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(_png_chunk(b"IHDR", struct.pack(">IIBBBBB", frame.w, frame.h, 8, 2, 0, 0, 0)))
        fh.write(_png_chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        fh.write(_png_chunk(b"IEND", b""))

def _rgb(op_key, default="#000000"):
    return tuple(int(round(c * 255)) for c in hex_rgb(op_key or default))

def raster_stdlib(model, path, scale):
    W, H = model["canvas"]["w_pt"] * scale, model["canvas"]["h_pt"] * scale
    frame = _Frame(max(2, int(round(W))), max(2, int(round(H))))
    for op in model["ops"]:
        if op["op"] == "rect":
            if op.get("fill"):
                frame.rect(op["x"] * scale, op["y"] * scale, op["w"] * scale, op["h"] * scale, _rgb(op["fill"]))
            if op.get("stroke"):
                frame.rect(op["x"] * scale, op["y"] * scale, op["w"] * scale, op["h"] * scale, _rgb(op["stroke"]))
        elif op["op"] == "line":
            frame.line(op["x1"] * scale, op["y1"] * scale, op["x2"] * scale, op["y2"] * scale,
                       _rgb(op.get("stroke")), max(1.0, op["sw"] * scale))
        elif op["op"] == "poly":
            frame.poly([(a * scale, b * scale) for a, b in op["pts"]], _rgb(op.get("fill")))

    write_png(frame, path)
    return frame.w, frame.h

def to_png(model, path, dpi, pdf_path=None):
    """pdftoppm from the vector PDF, else the built-in rasteriser. (ok, engine, note, px)."""
    notes = []
    if pdf_path and shutil.which("pdftoppm"):
        try:
            subprocess.run(["pdftoppm", "-png", "-r", str(int(dpi)), "-singlefile", str(pdf_path),
                            str(path)[:-4] if str(path).lower().endswith(".png") else str(path)],
                           check=True, timeout=180, capture_output=True)
            if _png_dims(str(path)):
                return True, "pdftoppm from the vector PDF at %d dpi" % int(dpi), "", _png_dims(str(path))
            notes.append("pdftoppm produced no readable PNG")
        except Exception as exc:
            notes.append("pdftoppm failed (%s)" % str(exc).splitlines()[0][:120])
    try:
        scale = max(1.0, min(4.0, float(dpi) / 72.0))
        px = raster_stdlib(model, path, scale)
        return True, "stdlib zlib rasteriser (degraded: shapes only, no glyphs)", "; ".join(notes), px
    except Exception as exc:
        return False, "none", "; ".join(notes + ["stdlib rasteriser failed (%s)" % exc]), None

def _png_dims(path):
    try:
        head = open(path, "rb").read(33)
    except Exception:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return [int(w), int(h)]

def decode_png(path):
    """Minimal 8-bit PNG decoder (colour types 0/2/6, filters 0-4)."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w, h, ctype = 8, b"", 0, 0, 2
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + ln]
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", payload[:10])
            if depth != 8 or ctype not in (0, 2, 6):
                raise ValueError("unsupported PNG (depth %d type %d)" % (depth, ctype))
        elif kind == b"IDAT":
            idat += payload
        elif kind == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    nch = {0: 1, 2: 3, 6: 4}[ctype]
    stride = w * nch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                left = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, nch, out

def probe(model, png_path):
    """Pixel evidence: is each panel really drawn, and is the page not blank?"""
    res = {"path": str(png_path), "decoded": False, "panels": [], "distinct_colours": 0,
           "mean_luminance": None, "blank": None, "dims": _png_dims(str(png_path))}
    try:
        w, h, nch, px = decode_png(str(png_path))
    except Exception as exc:
        res["error"] = str(exc)
        return res
    res["decoded"] = True
    W, H = model["canvas"]["w_pt"], model["canvas"]["h_pt"]
    sx, sy = w / float(W), h / float(H)
    colours = set()
    step = max(1, int((w * h) / 240000))
    lum, n = 0.0, 0
    for i in range(0, w * h, step):
        o = i * nch
        r, g, b = px[o], px[o + 1] if nch > 1 else px[o], px[o + 2] if nch > 2 else px[o]
        colours.add((r >> 3, g >> 3, b >> 3))
        lum += 0.299 * r + 0.587 * g + 0.114 * b
        n += 1
    res["distinct_colours"] = len(colours)
    res["mean_luminance"] = round(lum / max(1, n), 1)
    for p in model["panels"]:
        x0, y0, pw, ph = p["bbox"]
        xa, xb = int(x0 * sx), int((x0 + pw) * sx)
        ya, yb = int(y0 * sy), int((y0 + ph) * sy)
        ink = tot = 0
        for yy in range(max(0, ya), min(h, yb), 2):
            base = yy * w * nch
            for xx in range(max(0, xa), min(w, xb), 2):
                o = base + xx * nch
                tot += 1
                if abs(px[o] - 255) + abs(px[o + 1] - 255) + abs(px[o + 2] - 255) > 42:
                    ink += 1
        res["panels"].append({"panel": p["id"], "ink_ratio": round(ink / float(max(1, tot)), 4),
                              "drawn": ink > 0})
    res["blank"] = res["distinct_colours"] < 3
    return res
