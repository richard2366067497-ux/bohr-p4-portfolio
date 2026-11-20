"""Export layer for mechanism-figure-ledger: one display list -> single-page vector
PDF (base-14 Helvetica) and a zlib PNG rasterised with a 5x7 bitmap font.
Both are pure standard library; `probe_*` re-read the produced bytes.
"""
import math
import re
import struct
import zlib

import render as RD

FONT5 = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01110", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 11011 10001", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00110 01000 10000 11111", "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    " ": "00000 00000 00000 00000 00000 00000 00000", "-": "00000 00000 00000 11111 00000 00000 00000",
    ".": "00000 00000 00000 00000 00000 01100 01100", ",": "00000 00000 00000 00000 01100 01100 01000",
    ":": "00000 01100 01100 00000 01100 01100 00000", "/": "00001 00010 00010 00100 01000 01000 10000",
    "?": "01110 10001 00001 00110 00100 00000 00100", "(": "00010 00100 01000 01000 01000 00100 00010",
    ")": "01000 00100 00010 00010 00010 00100 01000", "_": "00000 00000 00000 00000 00000 00000 11111",
}


def _rgb(h):
    h = (h or "#000000").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _int(rgb):
    return tuple(int(round(v * 255)) for v in rgb)


def _pdf_text(s):
    keep, dropped = [], 0
    for ch in str(s):
        try:
            ch.encode("cp1252")
            keep.append(ch)
        except Exception:
            dropped += 1
    return "".join(keep).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)"), dropped


def pdf(model):
    dl = model.get("dl") or RD.display(model)
    W, H = RD.CANVAS["w"] * 0.75, RD.CANVAS["h"] * 0.75
    ops, dropped = [], 0
    for it in dl:
        if it[0] == "rect":
            _, x, y, w, h, fill, stroke, sw, rx = it
            X, Y = x * 0.75, H - (y + h) * 0.75
            if fill and fill.upper() != "NONE":
                r, g, b = _rgb(fill)
                ops.append("%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (r, g, b, X, Y, w * 0.75, h * 0.75))
            if stroke and stroke.upper() != "NONE" and sw:
                r, g, b = _rgb(stroke)
                ops.append("%.3f %.3f %.3f RG %.2f w %.2f %.2f %.2f %.2f re S"
                           % (r, g, b, sw * 0.75, X, Y, w * 0.75, h * 0.75))
        elif it[0] == "line":
            _, x1, y1, x2, y2, color, w, dash = it
            r, g, b = _rgb(color)
            d = "[%s] 0 d" % " ".join(str(float(v) * 0.75) for v in dash.split()) if dash else "[] 0 d"
            ops.append("%.3f %.3f %.3f RG %.2f w %s %.2f %.2f m %.2f %.2f l S"
                       % (r, g, b, w * 0.75, d, x1 * 0.75, H - y1 * 0.75, x2 * 0.75, H - y2 * 0.75))
        elif it[0] == "poly":
            _, pts, fill, stroke, sw = it
            if not pts:
                continue
            seg = ["%.2f %.2f m" % (pts[0][0] * 0.75, H - pts[0][1] * 0.75)]
            seg += ["%.2f %.2f l" % (p[0] * 0.75, H - p[1] * 0.75) for p in pts[1:]]
            seg.append("h")
            body = " ".join(seg)
            if fill and fill.upper() != "NONE":
                r, g, b = _rgb(fill)
                ops.append("%.3f %.3f %.3f rg %s f" % (r, g, b, body))
            if stroke and stroke.upper() != "NONE":
                r, g, b = _rgb(stroke)
                ops.append("%.3f %.3f %.3f RG %.2f w %s S" % (r, g, b, (sw or 1) * 0.75, body))
        elif it[0] == "text":
            _, x, y, size, s, color, italic, bold, anchor = it
            txt, dr = _pdf_text(s)
            dropped += dr
            if not txt:
                continue
            font = "F2" if italic else ("F3" if bold else "F1")
            sx = x * 0.75 - (RD.tw(s, size) * 0.75 / 2.0 if anchor == "middle" else 0)
            r, g, b = _rgb(color)
            ops.append("BT /%s %.2f Tf %.3f %.3f %.3f rg %.2f %.2f Td (%s) Tj ET"
                       % (font, size * 0.75, r, g, b, sx, H - y * 0.75, txt))
    content = "\n".join(ops).encode("cp1252", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.1f %.1f] /Resources << /Font << /F1 4 0 R "
         "/F2 5 0 R /F3 6 0 R >> >> /Contents 7 0 R >>" % (W, H)).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        ("<< /Length %d >>\nstream\n" % len(content)).encode() + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % i).encode() + body + b"\nendobj\n"
    xref = len(out)
    out += ("xref\n0 %d\n" % (len(objs) + 1)).encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref)).encode()
    return bytes(out)


def png(model):
    W, H = RD.CANVAS["w"], RD.CANVAS["h"]
    buf = bytearray(b"\xff" * (W * H * 3))

    def px(x, y, col):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            buf[i:i + 3] = bytes(col)

    def rect(x, y, w, h, col):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(W, int(x + w)), min(H, int(y + h))
        row = bytes(col) * max(0, x1 - x0)
        for yy in range(y0, y1):
            i = (yy * W + x0) * 3
            buf[i:i + len(row)] = row

    def line(x1, y1, x2, y2, col, w=2, dash=None):
        segs = [(x1, y1, x2, y2)]
        if dash:
            nums = [float(v) for v in dash.split()]
            on, off = (nums + [4.0, 4.0])[:2]
            length = math.hypot(x2 - x1, y2 - y1) or 1.0
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            segs, t, draw = [], 0.0, True
            while t < length:
                t2 = min(length, t + (on if draw else off))
                if draw:
                    segs.append((x1 + ux * t, y1 + uy * t, x1 + ux * t2, y1 + uy * t2))
                t, draw = t2, not draw
        half = max(1, int(round(w / 2.0)))
        for a, b, c, d in segs:
            n = int(max(abs(c - a), abs(d - b))) + 1
            for i in range(n + 1):
                u = i / float(n) if n else 0.0
                x, y = int(a + (c - a) * u), int(b + (d - b) * u)
                for dx in range(-half, half + 1):
                    for dy in range(-half, half + 1):
                        px(x + dx, y + dy, col)

    def poly(pts, fill_col, stroke_col, sw=1):
        if not pts:
            return
        ys = [p[1] for p in pts]
        for yy in range(int(min(ys)), int(max(ys)) + 1):
            xs = []
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                if (y1 <= yy < y2) or (y2 <= yy < y1):
                    xs.append(x1 + (yy - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                rect(xs[i], yy, xs[i + 1] - xs[i], 1, fill_col)
        for i in range(len(pts)):
            line(pts[i][0], pts[i][1], pts[(i + 1) % len(pts)][0],
                 pts[(i + 1) % len(pts)][1], stroke_col, sw)

    def text(x, y, size, s, col, anchor="start"):
        s = str(s).upper()
        sc = max(1, int(round(size / 7.0)))
        adv = 6 * sc
        x0 = x - adv * len(s) / 2.0 if anchor == "middle" else x
        for i, ch in enumerate(s):
            glyph = FONT5.get(ch, FONT5["?"])
            for r, rowbits in enumerate(glyph.split()):
                for c, bit in enumerate(rowbits):
                    if bit == "1":
                        rect(x0 + i * adv + c * sc, y - 7 * sc + r * sc, sc, sc, col)

    for it in model.get("dl") or RD.display(model):
        if it[0] == "rect":
            _, x, y, w, h, fill, stroke, sw, rx = it
            if fill and fill.upper() != "NONE":
                rect(x, y, w, h, _int(_rgb(fill)))
            if stroke and stroke.upper() != "NONE" and sw:
                line(x, y, x + w, y, _int(_rgb(stroke)), max(1, int(sw)))
                line(x, y + h, x + w, y + h, _int(_rgb(stroke)), max(1, int(sw)))
                line(x, y, x, y + h, _int(_rgb(stroke)), max(1, int(sw)))
                line(x + w, y, x + w, y + h, _int(_rgb(stroke)), max(1, int(sw)))
        elif it[0] == "line":
            _, x1, y1, x2, y2, color, w, dash = it
            line(x1, y1, x2, y2, _int(_rgb(color)), max(1, int(round(w))), dash)
        elif it[0] == "poly":
            _, pts, fill, stroke, sw = it
            poly(pts, _int(_rgb(fill)) if fill and fill.upper() != "NONE" else (255, 255, 255),
                 _int(_rgb(stroke)) if stroke and stroke.upper() != "NONE" else (0, 0, 0),
                 max(1, int(sw or 1)))
        elif it[0] == "text":
            _, x, y, size, s, color, italic, bold, anchor = it
            text(x, y, size, s, _int(_rgb(color)), anchor)

    raw = bytearray()
    for yy in range(H):
        raw.append(0)
        raw += buf[yy * W * 3:(yy + 1) * W * 3]
    comp = zlib.compress(bytes(raw), 6)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def png_probe(data):
    if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
        return {"ok": False, "error": "missing PNG signature"}
    try:
        w, h = struct.unpack(">II", data[16:24])
        bit, color = data[24], data[25]
        idat, i = b"", 8
        while i < len(data):
            ln = struct.unpack(">I", data[i:i + 4])[0]
            if data[i + 4:i + 8] == b"IDAT":
                idat += data[i + 8:i + 8 + ln]
            i += 12 + ln
        raw = zlib.decompress(idat)
        step = max(1, h // 70)
        colors = set()
        for y in range(0, h, step):
            row = raw[y * (w * 3 + 1) + 1:(y + 1) * (w * 3 + 1)]
            for x in range(0, w, max(1, w // 70)):
                colors.add(bytes(row[x * 3:x * 3 + 3]))
        return {"ok": w == RD.CANVAS["w"] and h == RD.CANVAS["h"] and len(colors) > 2,
                "width": w, "height": h, "bit_depth": bit, "color_type": color,
                "unique_colors": len(colors), "non_uniform": len(colors) > 2}
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def pdf_probe(data):
    if not data or not data.startswith(b"%PDF-"):
        return {"ok": False, "error": "missing %PDF header"}
    head = data[:400000]
    pages = len(re.findall(rb"/Type\s*/Page[^s]", head))
    has_eof = head.rstrip().endswith(b"%%EOF")
    tj = head.count(b" Tj")
    return {"ok": pages >= 1 and has_eof and tj > 0, "header": head[:8].decode("latin-1"),
            "pages": pages, "eof": has_eof, "text_ops": tj, "bytes": len(data), "vector": True}
