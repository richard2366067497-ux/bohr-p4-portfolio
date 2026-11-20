#!/usr/bin/env python3
"""schematic-trace-studio :: exporters (PNG rasteriser chain, vector PDF writer, preserve-edit).

Every function consumes the same `geom` produced by draw.geometry(model), so the three artefacts
cannot drift apart: they differ in rasterisation, not in content or coordinates.
"""
import hashlib
import math
import re
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import casekit as ck

# 5x7 bitmap glyphs: 35 bits per glyph, row-major. Used only when no SVG converter exists.
F57 = {
  "A": "01110100011000111111100011000110001", "B": "11110100011000111110100011000111110",
  "C": "01110100011000010000100001000101110", "D": "11110100011000110001100011000111110",
  "E": "11111100001000011110100001000011111", "F": "11111100001000011110100001000010000",
  "G": "01110100011000010111100011000101111", "H": "10001100011000111111100011000110001",
  "I": "01110001000010000100001000010001110", "J": "00111000100001000010000101001001100",
  "K": "10001100101010011000101001001010001", "L": "10000100001000010000100001000011111",
  "M": "10001110111010110001100011000110001", "N": "10001110011010110011100011000110001",
  "O": "01110100011000110001100011000101110", "P": "11110100011000111110100001000010000",
  "Q": "01110100011000110001101011001001101", "R": "11110100011000111110101001001010001",
  "S": "01111100001000001110000010000111110", "T": "11111001000010000100001000010000100",
  "U": "10001100011000110001100011000101110", "V": "10001100011000110001100010101000100",
  "W": "10001100011000110101101011101110001", "X": "10001100010101000100010101000110001",
  "Y": "10001100010101000100001000010000100", "Z": "11111000010001000100010001000011111",
  "0": "01110100011001110101110011000101110", "1": "00100011000010000100001000010001110",
  "2": "01110100010000100010001000100011111", "3": "11111000100010000010000110001101110",
  "4": "00010001100101010010111110001000010", "5": "11111100001111000001000011000101110",
  "6": "00110010001000011110100011000101110", "7": "11111000010001000100010000100001000",
  "8": "01110100011000101110100011000101110", "9": "01110100011000101111000010001001100",
  " ": "00000000000000000000000000000000000", ".": "00000000000000000000000001100011000",
  ",": "00000000000000000000011000110001100", ":": "00000011000110000000011000110000000",
  "-": "00000000000000011111000000000000000", "/": "00001000100001000100010000100010000",
  "(": "00010001000100001000010000010000010", ")": "01000001000001000001000001000100100",
  "%": "11001110100001000100010000101110011", "+": "00000001000010011111001000010000000",
  "'": "00100001000100000000000000000000000", "_": "00000000000000000000000000000011111",
  "?": "01110100010000100010001000000000100",
}

def _rgb(c):
  c = (c or "#000000").lstrip("#")
  if len(c) == 3:
    c = "".join(ch * 2 for ch in c)
  try:
    return bytes((int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)))
  except Exception:
    return b"\x00\x00\x00"

def _png_write(path, w, h, px):
  raw = bytearray()
  stride = w * 3
  for y in range(h):
    raw.append(0)
    raw += px[y * stride:(y + 1) * stride]

  def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

  Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" +
                           chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))

def png_raster(geom, model, scale, out_path):
  cw, chh = geom["canvas"]["width"], geom["canvas"]["height"]
  w, h = int(round(cw * scale)), int(round(chh * scale))
  px = bytearray(b"\xff" * (w * h * 3))
  stats = {"glyphs": 0, "skipped_chars": 0}

  def fill(x0, y0, x1, y1, col):
    x0, x1 = max(0, int(x0)), min(w, int(x1))
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
      return
    span = col * (x1 - x0)
    for y in range(y0, y1):
      o = (y * w + x0) * 3
      px[o:o + (x1 - x0) * 3] = span

  def line(p0, p1, col, t):
    x0, y0, x1, y1 = p0[0] * scale, p0[1] * scale, p1[0] * scale, p1[1] * scale
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    half = max(0.6, t * scale / 2.0)
    for i in range(n + 1):
      f = i / n
      x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
      fill(x - half, y - half, x + half, y + half, col)

  def poly(pts, col):
    ys = [p[1] for p in pts]
    for y in range(int(min(ys)), int(max(ys)) + 1):
      xs = []
      for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        if (ay <= y < by) or (by <= y < ay):
          xs.append(ax + (bx - ax) * (y - ay) / (by - ay))
      xs.sort()
      for i in range(0, len(xs) - 1, 2):
        fill(xs[i], y, xs[i + 1] + 1, y + 1, col)

  def text(it, col):
    s = max(1, int(round(it["size"] * scale / 8.0)))
    lh = it.get("lh", it["size"] * 1.18) * scale
    for k, ln in enumerate(it["lines"]):
      gw = 6 * s * len(ln)
      x = it["x"] * scale - (gw / 2.0 if it.get("anchor") == "middle" else 0)
      y = it["y"] * scale + k * lh - 7 * s
      for ch in ln:
        pat = F57.get(ch.upper())
        if pat is None:
          stats["skipped_chars"] += 1
          x += 6 * s
          continue
        for r in range(7):
          for c in range(5):
            if pat[r * 5 + c] == "1":
              fill(x + c * s, y + r * s, x + (c + 1) * s, y + (r + 1) * s, col)
        stats["glyphs"] += 1
        x += 6 * s

  def marker(it, col):
    pts = it["pts"]
    if len(pts) < 2 or it.get("marker") in (None, "line"):
      return
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ang = math.atan2((y1 - y0) * scale, (x1 - x0) * scale)
    tip = (x1 * scale, y1 * scale)
    size = 9 * scale
    k = {"arrow": 1.0, "thin": 0.75}.get(it["marker"], 1.0)

    def rot(dx, dy):
      return (tip[0] + dx * math.cos(ang) - dy * math.sin(ang),
          tip[1] + dx * math.sin(ang) + dy * math.cos(ang))
    if it["marker"] in ("arrow", "thin"):
      poly([rot(-size * k, -size * 0.42 * k), rot(0, 0), rot(-size * k, size * 0.42 * k)], col)
    elif it["marker"] == "tbar":
      a, b = rot(-1, -size * 0.34), rot(-1, size * 0.34)
      line((a[0] / scale, a[1] / scale), (b[0] / scale, b[1] / scale), col, 2.2)
    else:
      r = size * (0.30 if it["marker"] == "diamond" else 0.22)
      if it["marker"] == "diamond":
        poly([rot(-2 * r, 0), rot(-r, -r), rot(0, 0), rot(-r, r)], col)
      else:
        poly([rot(-2 * r, -r), rot(-2 * r, r), rot(0, r), rot(0, -r)], col)

  for it in geom["items"]:
    if it["kind"] == "rect":
      if it.get("fill"):
        fill(it["x"] * scale, it["y"] * scale, (it["x"] + it["w"]) * scale,
                     (it["y"] + it["h"]) * scale, _rgb(it["fill"]))
      if it.get("stroke"):
        col, t = _rgb(it["stroke"]), it.get("lw", 1)
        x, y, ww, hh = it["x"], it["y"], it["w"], it["h"]
        for p0, p1 in (((x, y), (x + ww, y)), ((x + ww, y), (x + ww, y + hh)),
                               ((x + ww, y + hh), (x, y + hh)), ((x, y + hh), (x, y))):
          line(p0, p1, col, t)
    elif it["kind"] == "path":
      col = _rgb(it["stroke"])
      for a, b in zip(it["pts"][:-1], it["pts"][1:]):
        line(a, b, col, it.get("lw", 1.2))
      marker(it, col)
    elif it["kind"] == "text":
      text(it, _rgb(it.get("fill")))
  _png_write(out_path, w, h, px)
  return stats

def export_png(svg_text, model, geom, out_path):
  out_path = Path(out_path)
  cw, chh = model["canvas"]["width"], model["canvas"]["height"]
  scale = max(1.5, min(2.4, 1800.0 / max(1, cw)))
  W, H = int(round(cw * scale)), int(round(chh * scale))
  tmp = out_path.parent / "_tmp_figure.svg"
  tmp.write_text(svg_text, encoding="utf-8")
  res = {"path": str(out_path), "engine": None, "bytes": None, "width": W, "height": H,
           "dpi": int(round(96 * scale)), "probe": None, "attempts": []}
  import verify as vf
  engines = []
  try:
    import cairosvg
    engines.append(("cairosvg", None, 60))
  except Exception:
    pass
  if shutil.which("rsvg-convert"):
    engines.append(("rsvg-convert", ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out_path), str(tmp)], 60))
  if shutil.which("inkscape"):
    engines.append(("inkscape", ["inkscape", str(tmp), "--export-type=png",
                                     "--export-filename=" + str(out_path), "-w", str(W), "-h", str(H)], 90))
  if shutil.which("convert"):
    engines.append(("imagemagick", ["convert", "-background", "white", "-density", str(int(96 * scale)),
                    str(tmp), "-resize", "%dx%d!" % (W, H), "-depth", "8", str(out_path)], 90))
  if shutil.which("soffice") or shutil.which("libreoffice"):
    engines.append(("libreoffice", [shutil.which("soffice") or shutil.which("libreoffice"), "--headless",
                    "--convert-to", "png", "--outdir", str(out_path.parent), str(tmp)], 120))
  for name, cmd, timeout in engines:
    try:
      if cmd is None:
        cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=str(out_path),
                                 output_width=W, output_height=H, background_color="white")
      else:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
      cand = out_path
      if name == "libreoffice":
        cand = out_path.parent / (tmp.stem + ".png")
        if cand.exists():
          cand.replace(out_path)
      if not out_path.exists() or out_path.stat().st_size < 200:
        res["attempts"].append({"engine": name, "ok": False, "reason": "no_output"})
        continue
      pr = vf.png_probe(out_path)
      aspect_ok = abs((pr.get("width") or 1) / float(max(1, pr.get("height") or 1))
              - cw / float(chh)) < 0.06
      ok = bool(pr.get("ok")) and aspect_ok
      res["attempts"].append({"engine": name, "ok": ok, "nonwhite_ratio": pr.get("nonwhite_ratio"),
                  "size": [pr.get("width"), pr.get("height")]})
      if ok:
        res.update({"engine": name, "probe": pr, "bytes": out_path.stat().st_size,
              "width": pr["width"], "height": pr["height"]})
        break
      if out_path.exists():
        out_path.unlink()
    except Exception as e:
      res["attempts"].append({"engine": name, "ok": False, "reason": repr(e)[:120]})
  if not res["engine"]:
    try:
      st = png_raster(geom, model, scale, out_path)
      pr = vf.png_probe(out_path)
      res.update({"engine": "builtin-raster", "probe": pr, "bytes": out_path.stat().st_size,
            "width": pr.get("width"), "height": pr.get("height"),
            "degradation": "no_svg_converter_builtin_bitmap_raster", "bitmap_stats": st})
    except Exception as e:
      res["probe"] = {"ok": False, "error": repr(e)[:160]}
  if tmp.exists():
    tmp.unlink()
  if not res.get("engine"):
    res.update({"status": "missing", "path": None})
    return res
  # honest density: report the dpi the file actually has, then resample up if the engine
  # (LibreOffice defaults to 96 dpi) produced fewer pixels than the requested export width.
  if res.get("width") and res["width"] < 0.75 * W and shutil.which("convert"):
    before = res["width"]
    try:
      rs = out_path.with_name("_rs_figure.png")
      subprocess.run(["convert", str(out_path), "-resize", "%dx%d!" % (W, H), "-depth", "8", str(rs)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
      pr2 = vf.png_probe(rs)
      if pr2.get("ok"):
        rs.replace(out_path)
        res.update({"probe": pr2, "width": pr2["width"], "height": pr2["height"],
              "bytes": out_path.stat().st_size, "resampled_from_width": before})
      elif rs.exists():
        rs.unlink()
    except Exception:
      pass
  res["dpi"] = int(round(96.0 * (res.get("width") or cw) / max(1, cw)))
  res["target_width"] = W
  return res

def _ps(s):
  out, skip = [], 0
  for ch in str(s):
    if ch in "()\\":
      out.append("\\" + ch)
    elif 32 <= ord(ch) < 127:
      out.append(ch)
    else:
      skip += 1
      out.append("?")
  return "".join(out), skip

def pdf_doc(model, geom):
  cw, chh = geom["canvas"]["width"], geom["canvas"]["height"]
  k = 0.75
  W, H = cw * k, chh * k
  ops, skipped = [], 0

  def y(v):
    return round((chh - v) * k, 2)

  def num(v):
    return round(v * k, 2)

  for it in geom["items"]:
    if it["kind"] == "rect":
      x, yy = num(it["x"]), y(it["y"] + it["h"])
      w, h = num(it["w"]), num(it["h"])
      if it.get("fill"):
        ops.append("%.3f %.3f %.3f rg %s %s %s %s re f" % (_rgb(it["fill"])[0] / 255.0,
                                                                   _rgb(it["fill"])[1] / 255.0,
                                                                   _rgb(it["fill"])[2] / 255.0, x, yy, w, h))
      if it.get("stroke"):
        c = _rgb(it["stroke"])
        ops.append("%.3f %.3f %.3f RG %s w %s %s %s %s re S" % (c[0] / 255.0, c[1] / 255.0,
                                    c[2] / 255.0, num(it.get("lw", 1)), x, yy, w, h))
    elif it["kind"] == "path":
      c = _rgb(it["stroke"])
      ops.append("%.3f %.3f %.3f RG %s w 1 J" % (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0,
                                                       num(it.get("lw", 1.2))))
      if it.get("dash"):
        ops.append("[%s] 0 d" % " ".join(str(num(float(v))) for v in it["dash"].split()))
      ops.append("%s %s m" % (num(it["pts"][0][0]), y(it["pts"][0][1])))
      for p in it["pts"][1:]:
        ops.append("%s %s l" % (num(p[0]), y(p[1])))
      ops.append("S" + (" [] 0 d" if it.get("dash") else ""))
      _marker_pdf(it, ops, num, y, c)
    elif it["kind"] == "text":
      for i, ln in enumerate(it["lines"]):
        s, sk = _ps(ln)
        skipped += sk
        c = _rgb(it.get("fill"))
        wid = sum(1.0 if ord(ch) > 0x2E80 else (0.34 if ch in " .,:;'|!il" else 0.56)
                          for ch in ln) * it["size"] * k
        x = num(it["x"]) - (wid / 2.0 if it.get("anchor") == "middle" else 0)
        ops.append("BT /%s %s Tf %.3f %.3f %.3f rg %s %s Td (%s) Tj ET"
                           % ("F2" if str(it.get("weight")) in ("600", "700") else "F1",
                              num(it["size"]), c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, round(x, 2),
                              y(it["y"] + i * it.get("lh", it["size"] * 1.18)), s))
  content = "\n".join(ops).encode("latin-1", "replace")
  objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
      b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << /F1 5 0 R "
             "/F2 6 0 R >> >> /Contents 4 0 R >>" % (W, H)).encode("latin-1"),
      b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
      b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
      b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
  out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
  offs = []
  for i, o in enumerate(objs, 1):
    offs.append(len(out))
    out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
  xref = len(out)
  out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
  for off in offs:
    out += b"%010d 00000 n \n" % off
  out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
  return bytes(out), skipped

def _marker_pdf(it, ops, num, y, c):
  pts = it["pts"]
  if len(pts) < 2 or it.get("marker") in (None, "line"):
    return
  (x0, y0), (x1, y1) = pts[-2], pts[-1]
  ang = math.atan2(y0 - y1, x1 - x0)
  tip = (x1, y1)
  size = 9.0

  def rot(dx, dy):
    return (tip[0] + dx * math.cos(ang) - dy * math.sin(ang),
        tip[1] - (dx * math.sin(ang) + dy * math.cos(ang)))
  kind = it["marker"]
  col = "%.3f %.3f %.3f" % (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
  if kind in ("arrow", "thin"):
    k = 1.0 if kind == "arrow" else 0.75
    q = [rot(-size * k, -size * 0.42 * k), rot(0, 0), rot(-size * k, size * 0.42 * k)]
    ops.append("%s rg %s %s m %s %s l %s %s l f" % (col, *[v for p in q for v in (num(p[0]), y(p[1]))]))
  elif kind == "tbar":
    a, b = rot(-1, -size * 0.34), rot(-1, size * 0.34)
    ops.append("%s RG 1.6 w %s %s m %s %s l S" % (col, num(a[0]), y(a[1]), num(b[0]), y(b[1])))
  else:
    r = size * (0.30 if kind == "diamond" else 0.22)
    q = ([rot(-2 * r, 0), rot(-r, -r), rot(0, 0), rot(-r, r)] if kind == "diamond"
             else [rot(-2 * r, -r), rot(-2 * r, r), rot(0, r), rot(0, -r)])
    ops.append("%s rg %s %s m %s %s l %s %s l %s %s l f" % (col, *[v for p in q for v in (num(p[0]), y(p[1]))]))

def export_pdf(model, geom, out_path):
  out_path = Path(out_path)
  data, skipped = pdf_doc(model, geom)
  out_path.write_bytes(data)
  import verify as vf
  pr = vf.pdf_probe(out_path)
  hits, n = vf.pdf_label_hits(out_path, [e["label"] for e in model["entities"]])
  res = {"path": str(out_path), "engine": "builtin-vector-pdf", "bytes": len(data), "probe": pr,
           "vector": True, "pages": pr.get("pages"), "text_extracted": hits, "label_hits": n,
           "text_probe_engine": "pdftotext", "non_latin_chars_replaced": skipped}
  if pr.get("media_box"):
    res["page_size_pt"] = pr["media_box"]
  if not pr.get("ok"):
    res.update({"status": "missing", "degradation": "pdf_structure_check_failed"})
  if hits is None:
    res["text_probe_engine"] = None
    res["degradation_text_probe"] = "pdftotext_unavailable"
  elif skipped:
    res["degradation_text"] = "non_latin_characters_replaced_in_pdf_text_layer"
  return res

def write_outputs(model, geom, outdir):
  outdir = Path(outdir)
  outdir.mkdir(parents=True, exist_ok=True)
  import draw
  svg = draw.svg_doc(geom, model)
  sp = outdir / "figure.svg"
  sp.write_text(svg, encoding="utf-8")
  enc = svg.encode("utf-8")
  return {"svg": {"path": str(sp), "format": "svg", "bytes": len(enc), "vector": True,
          "sha256": hashlib.sha256(enc).hexdigest()},
      "png": export_png(svg, model, geom, outdir / "figure.png"),
      "pdf": export_pdf(model, geom, outdir / "figure.pdf")}

def edit_record(baseline, draft):
  """Change only the targeted text nodes of the baseline; every other id/layer/style survives."""
  ops = [o for o in ck.as_list((draft.get("edit") or {}).get("operations")) if isinstance(o, dict)]
  base_path = Path(baseline.get("path") or "")
  rec = {"mode": "preserve", "baseline": {"path": str(base_path), "sha256": baseline.get("sha256"),
                      "bytes": baseline.get("bytes")},
           "operations_requested": len(ops), "changes": [], "preserved": {},
           "status": "no_operations" if not ops else "recorded"}
  if not base_path.exists():
    rec["status"] = "baseline_missing"
    return rec
  txt = base_path.read_text(encoding="utf-8", errors="replace")
  orig_ids = set(re.findall(r'id="([^"]+)"', txt))
  for i, op in enumerate(ops, 1):
    tid, new, old = str(op.get("target_id") or ""), str(op.get("new_text") or ""), str(op.get("target_text") or "")
    pat = None
    if tid:
      pat = re.compile(r'(<text[^>]*id="%s"[^>]*>)(.*?)(</text>)' % re.escape(tid), re.S)
    elif old:
      pat = re.compile(r'(<text[^>]*>)([^<]*%s[^<]*)(</text>)' % re.escape(old), re.S)
    done = False
    if pat and new:
      txt2, cnt = pat.subn(lambda m: m.group(1) + new + m.group(3), txt, count=1)
      if cnt:
        txt, done = txt2, True
    rec["changes"].append({"op": i, "svg_id": tid or None, "original": old or None, "revised": new,
                               "applied": done, "locator": (op.get("evidence") or {}).get("locator"),
                               "quote": (op.get("evidence") or {}).get("quote")})
  rec["preserved"] = {"ids_total": len(orig_ids),
            "ids_preserved": len(orig_ids & set(re.findall(r'id="([^"]+)"', txt))),
            "layer_ids": len([i for i in orig_ids if i.startswith("layer-")]),
            "text_nodes": len(re.findall(r"<text[^>]*>", txt))}
  rec["edited_sha256"] = hashlib.sha256(txt.encode("utf-8")).hexdigest()
  if rec["changes"]:
    rec["status"] = "applied" if all(c["applied"] for c in rec["changes"]) else "partial"
  return rec
