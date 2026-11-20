#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""draw.py - one primitive canvas feeds three exporters so the delivered previews
cannot drift from the editable SVG:

    Canvas (rect / line / polyline / circle / text)
        -> to_svg()  layered, ids + live <text>, the editable deliverable
        -> to_pdf()  hand-written vector PDF 1.4 (Helvetica base-14, no dependencies)
        -> to_png()  8-bit RGB raster encoded with zlib, for an engine-free preview

Everything is standard library.  Text that cannot be encoded in Latin-1 (CJK) is
drawn in the previews as a neutral label bar; the SVG keeps the real string, and
the caller records that degradation explicitly.
"""
import math
import struct
import zlib

FONT_STACK = "Helvetica, Arial, 'Noto Sans CJK SC', 'DejaVu Sans', sans-serif"
LAYERS = ["background", "title", "axes", "data", "error", "legend", "labels"]
INK = "#111111"


def esc_xml(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def hex_rgb(h):
    h = (h or "#000000").lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def is_ascii(s):
    return all(ord(c) < 128 for c in str(s))


def is_latin1(s):
    try:
        str(s).encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def text_w(s, size):
    """Estimated advance in canvas px (CJK 1.0 em, other 0.55 em)."""
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in str(s)) * size


class Canvas:
    def __init__(self):
        self.p = []
        self.max_x = 0.0
        self.max_y = 0.0

    def _grow(self, x, y):
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    def rect(self, x, y, w, h, fill=None, stroke=None, sw=1.0, dash=None, rid=None, layer="data"):
        self.p.append({"t": "r", "x": x, "y": y, "w": w, "h": h, "fill": fill, "stroke": stroke,
                       "sw": sw, "dash": dash, "id": rid, "layer": layer})
        self._grow(x + w, y + h)

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.0, dash=None, rid=None, layer="axes"):
        self.p.append({"t": "l", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": stroke,
                       "sw": sw, "dash": dash, "id": rid, "layer": layer})
        self._grow(max(x1, x2), max(y1, y2))

    def poly(self, pts, stroke=INK, sw=1.0, dash=None, marker=False, rid=None, layer="error"):
        self.p.append({"t": "p", "pts": list(pts), "stroke": stroke, "sw": sw, "dash": dash,
                       "marker": marker, "id": rid, "layer": layer})
        for x, y in pts:
            self._grow(x, y)

    def circle(self, cx, cy, r, fill=None, stroke=None, sw=1.0, rid=None, layer="data"):
        self.p.append({"t": "c", "cx": cx, "cy": cy, "r": r, "fill": fill, "stroke": stroke,
                       "sw": sw, "id": rid, "layer": layer})
        self._grow(cx + r, cy + r)

    def text(self, x, y, s, size=8.0, anchor="middle", fill=INK, rid=None, layer="labels", bold=False):
        self.p.append({"t": "t", "x": x, "y": y, "s": str(s), "size": size, "anchor": anchor,
                       "fill": fill, "id": rid, "layer": layer, "bold": bold})
        w = text_w(s, size)
        x0 = x - (w if anchor == "end" else (w / 2.0 if anchor == "middle" else 0.0))
        self._grow(x0 + w, y + size * 0.4)


# --------------------------------------------------------------------- SVG
def _svg_anchor(a):
    return {"middle": "middle", "end": "end"}.get(a, "start")


def to_svg(cv, W, H, title, subtitle):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="%g" height="%g" '
           'viewBox="0 0 %g %g" font-family="%s">' % (W, H, W, H, esc_xml(FONT_STACK)),
           '<title id="svg-title">%s</title>' % esc_xml(title),
           '<desc id="svg-desc">%s</desc>' % esc_xml(subtitle)]
    for layer in LAYERS:
        prims = [p for p in cv.p if p["layer"] == layer]
        if not prims:
            continue
        out.append('<g id="layer-%s">' % layer)
        for p in prims:
            out.append(_svg_prim(p))
        out.append('</g>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def _svg_prim(p):
    ident = ' id="%s"' % esc_xml(p["id"]) if p["id"] else ""
    dash = ' stroke-dasharray="%s"' % p["dash"] if p.get("dash") else ""
    t = p["t"]
    if t == "r":
        fill = ' fill="%s"' % p["fill"] if p["fill"] else ' fill="transparent"'
        stroke = ' stroke="%s" stroke-width="%g"' % (p["stroke"], p["sw"]) if p["stroke"] else ""
        return '<rect%s x="%g" y="%g" width="%g" height="%g"%s%s%s/>' % (
            ident, p["x"], p["y"], p["w"], p["h"], fill, stroke, dash)
    if t == "l":
        return '<line%s x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="%g"%s/>' % (
            ident, p["x1"], p["y1"], p["x2"], p["y2"], p["stroke"], p["sw"], dash)
    if t == "p":
        pts = " ".join("%g,%g" % (x, y) for x, y in p["pts"])
        marker = ' marker-end="url(#arrow-ink)"' if p.get("marker") else ""
        return ('<polyline%s points="%s" fill="transparent" stroke="%s" stroke-width="%g" '
                'stroke-linejoin="round"%s%s/>' % (ident, pts, p["stroke"], p["sw"], dash, marker))
    if t == "c":
        fill = ' fill="%s"' % p["fill"] if p["fill"] else ' fill="transparent"'
        stroke = ' stroke="%s" stroke-width="%g"' % (p["stroke"], p["sw"]) if p["stroke"] else ""
        return '<circle%s cx="%g" cy="%g" r="%g"%s%s/>' % (ident, p["cx"], p["cy"], p["r"], fill, stroke)
    weight = ' font-weight="bold"' if p.get("bold") else ""
    return '<text%s x="%g" y="%g" font-size="%g" text-anchor="%s" fill="%s"%s>%s</text>' % (
        ident, p["x"], p["y"], p["size"], _svg_anchor(p["anchor"]), p["fill"], weight,
        esc_xml(p["s"]))


# --------------------------------------------------------------------- PDF
def _pdf_str(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def to_pdf(cv, W, H):
    """Return PDF bytes (vector, one page, MediaBox in points at 96 dpi)."""
    k = 72.0 / 96.0
    page_w, page_h = round(W * k, 2), round(H * k, 2)
    ops = ["q", "%.4f 0 0 %.4f 0 %.4f cm" % (k, k, H * k)]  # flip to top-left px coords
    skipped_text = 0
    for p in cv.p:
        t = p["t"]
        if p.get("dash"):
            d = [seg for seg in p["dash"].replace(",", " ").split() if seg]
            ops.append("[%s] 0 d" % " ".join(d))
        if t == "r":
            if p["fill"]:
                r, g, b = hex_rgb(p["fill"])
                ops.append("%.3f %.3f %.3f rg" % (r / 255.0, g / 255.0, b / 255.0))
            if p["stroke"]:
                r, g, b = hex_rgb(p["stroke"])
                ops.append("%.3f %.3f %.3f RG" % (r / 255.0, g / 255.0, b / 255.0))
                ops.append("%.3f w" % p["sw"])
            ops.append("%.3f %.3f %.3f %.3f re" % (p["x"], p["y"], p["w"], p["h"]))
            ops.append("B" if (p["fill"] and p["stroke"]) else ("f" if p["fill"] else "S"))
        elif t == "l":
            r, g, b = hex_rgb(p["stroke"])
            ops.append("%.3f %.3f %.3f RG %.3f w" % (r / 255.0, g / 255.0, b / 255.0, p["sw"]))
            ops.append("%.3f %.3f m %.3f %.3f l S" % (p["x1"], p["y1"], p["x2"], p["y2"]))
        elif t == "p":
            r, g, b = hex_rgb(p["stroke"])
            ops.append("%.3f %.3f %.3f RG %.3f w" % (r / 255.0, g / 255.0, b / 255.0, p["sw"]))
            seg = ["%.3f %.3f m" % tuple(p["pts"][0])]
            seg += ["%.3f %.3f l" % (x, y) for x, y in p["pts"][1:]]
            ops.append(" ".join(seg) + " S")
            if p.get("marker") and len(p["pts"]) >= 2:
                (x0, y0), (x1, y1) = p["pts"][-2], p["pts"][-1]
                ops.append(_arrow(x1, y1, math.atan2(y1 - y0, x1 - x0), p["stroke"]))
        elif t == "c":
            if p["fill"]:
                r, g, b = hex_rgb(p["fill"])
                ops.append("%.3f %.3f %.3f rg" % (r / 255.0, g / 255.0, b / 255.0))
            ops.append(_circle_path(p["cx"], p["cy"], p["r"]))
            ops.append("f" if p["fill"] else "S")
        elif t == "t":
            if is_latin1(p["s"]):
                r, g, b = hex_rgb(p["fill"])
                x = _anchor_x(p)
                ops.append("%.3f %.3f %.3f rg BT /F1 %.3f Tf %.3f %.3f Td (%s) Tj ET" % (
                    r / 255.0, g / 255.0, b / 255.0, p["size"], x, p["y"], _pdf_str(p["s"])))
            else:
                skipped_text += 1
                w = text_w(p["s"], p["size"])
                x0 = p["x"] - (w if p["anchor"] == "end" else (w / 2.0 if p["anchor"] == "middle" else 0.0))
                ops.append("0.62 0.62 0.62 rg %.3f %.3f %.3f %.3f re f" % (
                    x0, p["y"] - p["size"] * 0.72, w, p["size"] * 0.85))
        ops.append("[] 0 d")
    ops.append("Q")
    stream = "\n".join(ops).encode("latin-1", "replace")

    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %g %g] "
                 "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
                 % (page_w, page_h)).encode("latin-1"))
    objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % i).encode() + body + b"\nendobj\n"
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    return bytes(out)


def _anchor_x(p):
    w = text_w(p["s"], p["size"])
    return p["x"] - (w if p["anchor"] == "end" else (w / 2.0 if p["anchor"] == "middle" else 0.0))


def _circle_path(cx, cy, r):
    c = 0.5523 * r
    return ("%.3f %.3f m %.3f %.3f %.3f %.3f %.3f %.3f c %.3f %.3f %.3f %.3f %.3f %.3f c "
            "%.3f %.3f %.3f %.3f %.3f %.3f c %.3f %.3f %.3f %.3f %.3f %.3f c" % (
                cx + r, cy,
                cx + r, cy + c, cx + c, cy + r, cx, cy + r,
                cx - c, cy + r, cx - r, cy + c, cx - r, cy,
                cx - r, cy - c, cx - c, cy - r, cx, cy - r,
                cx + c, cy - r, cx + r, cy - c, cx + r, cy))


def _arrow(x, y, ang, color):
    size = 5.0
    a1, a2 = ang + math.pi - 0.42, ang + math.pi + 0.42
    r, g, b = hex_rgb(color)
    pts = [(x, y), (x + size * math.cos(a1), y + size * math.sin(a1)),
           (x + size * math.cos(a2), y + size * math.sin(a2))]
    return ("%.3f %.3f %.3f rg %.3f %.3f m %.3f %.3f l %.3f %.3f l h f" % (
        r / 255.0, g / 255.0, b / 255.0, pts[0][0], pts[0][1], pts[1][0], pts[1][1],
        pts[2][0], pts[2][1]))


# --------------------------------------------------------------------- PNG
def to_png(cv, W, H):
    w, h = int(round(W)), int(round(H))
    buf = bytearray(b"\xff" * (w * h * 3))

    def put(x, y, rgb):
        if 0 <= x < w and 0 <= y < h:
            o = (y * w + x) * 3
            buf[o:o + 3] = bytes(rgb)

    def fill_rect(x, y, rw, rh, rgb):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(w, int(x + rw + 0.999)), min(h, int(y + rh + 0.999))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(rgb) * (x1 - x0)
        for yy in range(y0, y1):
            o = (yy * w + x0) * 3
            buf[o:o + (x1 - x0) * 3] = row

    def draw_line(x1, y1, x2, y2, rgb, width=1.0):
        steps = int(max(abs(x2 - x1), abs(y2 - y1))) + 1
        rad = max(1, int(round(width)))
        for i in range(steps + 1):
            u = i / float(steps)
            x, y = x1 + (x2 - x1) * u, y1 + (y2 - y1) * u
            if rad == 1:
                put(int(x), int(y), rgb)
            else:
                fill_rect(x - rad / 2.0, y - rad / 2.0, rad, rad, rgb)

    def draw_circle(cx, cy, r, rgb, fill=True):
        r = max(0.6, r)
        for dy in range(-int(r), int(r) + 1):
            dx = int(math.sqrt(max(0.0, r * r - dy * dy)))
            x0, x1 = int(cx - dx), int(cx + dx)
            if fill:
                fill_rect(x0, cy + dy, max(1, x1 - x0 + 1), 1, rgb)
            else:
                put(x0, int(cy + dy), rgb)
                put(x1, int(cy + dy), rgb)

    def draw_text(p):
        rgb = hex_rgb(p["fill"])
        if not is_ascii(p["s"]):
            w2 = text_w(p["s"], p["size"])
            x0 = p["x"] - (w2 if p["anchor"] == "end" else (w2 / 2.0 if p["anchor"] == "middle" else 0.0))
            fill_rect(x0, p["y"] - p["size"] * 0.72, w2, p["size"] * 0.8, (170, 170, 170))
            return
        cell = max(1.0, p["size"] / 7.0)
        advance = 6.0 * cell
        total = advance * len(p["s"])
        x0 = p["x"] - (total if p["anchor"] == "end" else (total / 2.0 if p["anchor"] == "middle" else 0.0))
        for i, ch in enumerate(p["s"]):
            gx = x0 + i * advance
            for gy, row in enumerate(FONT5.get(ch.upper(), FONT5["?"]).split("/")):
                for col in range(5):
                    if row[col] == "1":
                        fill_rect(gx + col * cell, p["y"] - p["size"] + gy * cell,
                                  max(1, cell), max(1, cell), rgb)

    for p in cv.p:
        t = p["t"]
        if t == "r":
            if p["fill"]:
                fill_rect(p["x"], p["y"], p["w"], p["h"], hex_rgb(p["fill"]))
            if p["stroke"]:
                rgb, sw = hex_rgb(p["stroke"]), p["sw"]
                draw_line(p["x"], p["y"], p["x"] + p["w"], p["y"], rgb, sw)
                draw_line(p["x"] + p["w"], p["y"], p["x"] + p["w"], p["y"] + p["h"], rgb, sw)
                draw_line(p["x"] + p["w"], p["y"] + p["h"], p["x"], p["y"] + p["h"], rgb, sw)
                draw_line(p["x"], p["y"] + p["h"], p["x"], p["y"], rgb, sw)
        elif t == "l":
            draw_line(p["x1"], p["y1"], p["x2"], p["y2"], hex_rgb(p["stroke"]), p["sw"])
        elif t == "p":
            rgb = hex_rgb(p["stroke"])
            for a, b in zip(p["pts"], p["pts"][1:]):
                draw_line(a[0], a[1], b[0], b[1], rgb, p["sw"])
        elif t == "c":
            if p["fill"]:
                draw_circle(p["cx"], p["cy"], p["r"], hex_rgb(p["fill"]))
            if p["stroke"]:
                draw_circle(p["cx"], p["cy"], p["r"], hex_rgb(p["stroke"]), fill=False)
        elif t == "t":
            draw_text(p)

    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += buf[y * w * 3:(y + 1) * w * 3]

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------- probes
def probe_png(data):
    info = {"bytes": len(data), "magic_ok": data[:8] == b"\x89PNG\r\n\x1a\n"}
    if not info["magic_ok"]:
        return info
    info["width"], info["height"] = struct.unpack(">II", data[16:24])
    info["color_type"] = data[25]
    idat, i = b"", 8
    while i + 8 <= len(data):
        ln = int.from_bytes(data[i:i + 4], "big")
        if data[i + 4:i + 8] == b"IDAT":
            idat += data[i + 8:i + 8 + ln]
        i += 12 + ln
    try:
        raw = zlib.decompress(idat)
        step = max(3, (len(raw) // 8000) * 3)
        colors = {raw[j:j + 3] for j in range(0, len(raw) - 3, step)}
        info["unique_colors"] = len(colors)
        info["ink_present"] = len(colors) > 1
    except Exception as exc:  # noqa: BLE001
        info["note"] = "idat_decode_failed:%s" % type(exc).__name__
        info["ink_present"] = False
    return info


def probe_pdf(data):
    import re
    info = {"bytes": len(data), "magic_ok": data[:5] == b"%PDF-"}
    info["pages"] = len(re.findall(rb"/Type\s*/Page[^s]", data))
    info["vector"] = b"/Subtype /Image" not in data
    info["has_font"] = b"/BaseFont" in data
    m = re.search(rb"/MediaBox\s*\[\s*([\d.\-]+) +([\d.\-]+) +([\d.\-]+) +([\d.\-]+)", data)
    if m:
        v = [float(x) for x in m.groups()]
        info["mediabox_pt"] = [round(v[2] - v[0], 2), round(v[3] - v[1], 2)]
    return info


# --------------------------------------------------------------- tiny font 5x7
_GLYPHS = {
    " ": "00000/00000/00000/00000/00000/00000/00000",
    "0": "01110/10001/10011/10101/11001/10001/01110",
    "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111",
    "3": "11111/00010/00100/00010/00001/10001/01110",
    "4": "00010/00110/01010/10010/11111/00010/00010",
    "5": "11111/10000/11110/00001/00001/10001/01110",
    "6": "00110/01000/10000/11110/10001/10001/01110",
    "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110",
    "9": "01110/10001/10001/01111/00001/00010/01100",
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01110/10001/10000/10000/10000/10001/01110",
    "D": "11100/10010/10001/10001/10001/10010/11100",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01110/10001/10000/10111/10001/10001/01111",
    "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "01110/00100/00100/00100/00100/00100/01110",
    "J": "00111/00010/00010/00010/00010/10010/01100",
    "K": "10001/10010/10100/11000/10100/10010/10001",
    "L": "10000/10000/10000/10000/10000/10000/11111",
    "M": "10001/11011/10101/10101/10001/10001/10001",
    "N": "10001/11001/10101/10011/10001/10001/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "Q": "01110/10001/10001/10001/10101/10010/01101",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/11011/10001",
    "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100",
    "Z": "11111/00001/00010/00100/01000/10000/11111",
    ".": "00000/00000/00000/00000/00000/01100/01100",
    ",": "00000/00000/00000/00000/01100/01100/01000",
    "-": "00000/00000/00000/11111/00000/00000/00000",
    "_": "00000/00000/00000/00000/00000/00000/11111",
    "/": "00001/00001/00010/00100/01000/10000/10000",
    ":": "00000/01100/01100/00000/01100/01100/00000",
    "%": "11001/11010/00010/00100/01000/01011/10011",
    "(": "00010/00100/01000/01000/01000/00100/00010",
    ")": "01000/00100/00010/00010/00010/00100/01000",
    "+": "00000/00100/00100/11111/00100/00100/00000",
    "=": "00000/00000/11111/00000/11111/00000/00000",
    "?": "01110/10001/00001/00110/00100/00000/00100",
    "<": "00010/00100/01000/10000/01000/00100/00010",
    ">": "01000/00100/00010/00001/00010/00100/01000",
    "'": "00100/00100/01000/00000/00000/00000/00000",
    "*": "00000/10101/01110/11111/01110/10101/00000",
}
FONT5 = dict(_GLYPHS)
