#!/usr/bin/env python3
"""schematic-trace-studio :: probes, audits and the draft rule engine.

  png_probe      real IHDR decode (8/16-bit, ct 0/2/3/4/6) + unfilter + non-white ratio
  pdf_probe      %PDF- header, page objects, MediaBox, %%EOF, image-free vector check
  pdf_text       pdftotext back-extraction (proves the text was not outlined)
  svg_audit       XML parse: layer groups, live text nodes, markers, ids, min font/stroke
  layout_checks  box overlap, label overflow, canvas containment, min gap
  determinism    render the same model twice and compare hashes
  draft_rules    C1..C10e: the checks that decide whether a draft is trustworthy
"""
import hashlib
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import casekit as ck
from casekit import REL, as_list, nrm

def _png_chunks(data):
  if data[:8] != b"\x89PNG\r\n\x1a\n":
    return None
  i, out = 8, []
  while i + 8 <= len(data):
    ln = struct.unpack(">I", data[i:i + 4])[0]
    typ = data[i + 4:i + 8]
    out.append((typ, data[i + 8:i + 8 + ln]))
    i += 12 + ln
  return out

def png_probe(path):
  """Decode enough of a PNG to prove it is a real, non-blank raster."""
  p = Path(path)
  res = {"ok": False, "path": str(p), "bytes": None, "width": None, "height": None,
           "bit_depth": None, "color_type": None, "nonwhite_ratio": None, "blank": None,
           "error": None}
  try:
    data = p.read_bytes()
    res["bytes"] = len(data)
    ch = _png_chunks(data)
    if not ch:
      res["error"] = "bad_png_signature"
      return res
    ihdr = next((d for t, d in ch if t == b"IHDR"), None)
    if not ihdr:
      res["error"] = "missing_IHDR"
      return res
    w, h, bd, ct, _comp, _filt, inter = struct.unpack(">IIBBBBB", ihdr[:13])
    res.update({"width": w, "height": h, "bit_depth": bd, "color_type": ct})
    idat = b"".join(d for t, d in ch if t == b"IDAT")
    if not idat or inter != 0:
      res["error"] = "no_idat" if not idat else "interlaced_unsupported"
      res["ok"] = res["error"] is None
      return res
    ch_n = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ct)
    if ch_n is None or bd not in (8, 16):
      res["error"] = "unsupported_color_type_%s_%s" % (ct, bd)
      return res
    raw = zlib.decompress(idat)
    bpp = ch_n * (bd // 8)
    stride = w * bpp
    if len(raw) < (stride + 1) * h:
      res["error"] = "truncated_idat"
      return res
    prev = bytearray(stride)
    step_x = max(1, w // 220)
    dark = tot = 0
    pos = 0
    for y in range(h):
      ft = raw[pos]
      row = bytearray(raw[pos + 1:pos + 1 + stride])
      pos += stride + 1
      if ft == 1:
        for i in range(bpp, stride):
          row[i] = (row[i] + row[i - bpp]) & 0xFF
      elif ft == 2:
        for i in range(stride):
          row[i] = (row[i] + prev[i]) & 0xFF
      elif ft == 3:
        for i in range(stride):
          a = row[i - bpp] if i >= bpp else 0
          row[i] = (row[i] + ((a + prev[i]) >> 1)) & 0xFF
      elif ft == 4:
        for i in range(stride):
          a = row[i - bpp] if i >= bpp else 0
          b = prev[i]
          c = prev[i - bpp] if i >= bpp else 0
          pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
          pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
          row[i] = (row[i] + pr) & 0xFF
      elif ft != 0:
        res["error"] = "bad_filter_%d" % ft
        return res
      if y % 2 == 0:
        for x in range(0, w, step_x):
          o = x * bpp
          if ch_n >= 3:
            if bd == 8:
              rgb = (row[o], row[o + 1], row[o + 2])
            else:
              rgb = (row[o] << 8 | row[o + 1], row[o + 2] << 8 | row[o + 3],
                                   row[o + 4] << 8 | row[o + 5])
            lum = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) // 1000
            lim = 65025 if bd == 16 else 255
          else:
            v = row[o] if bd == 8 else (row[o] << 8 | row[o + 1])
            lim = 255 if bd == 8 else 65535
            lum = v
          tot += 1
          if lum < lim * 0.97:
            dark += 1
      prev = row
    ratio = round(dark / tot, 5) if tot else 0.0
    res["nonwhite_ratio"] = ratio
    res["blank"] = ratio < 0.0005
    res["ok"] = (w > 16 and h > 16 and not res["blank"])
    if not res["ok"]:
      res["error"] = "blank_or_too_small"
  except Exception as e:
    res["error"] = repr(e)[:160]
  return res

def pdf_probe(path):
  p = Path(path)
  res = {"ok": False, "path": str(p), "bytes": None, "header": None, "eof": None,
           "pages": None, "page_objects": None, "media_box": None, "vector": None, "error": None}
  try:
    data = p.read_bytes()
    res["bytes"] = len(data)
    res["header"] = data[:5] == b"%PDF-"
    res["eof"] = b"%%EOF" in data[-2048:]
    res["page_objects"] = len(re.findall(rb"/Type\s*/Page[^s]", data))
    m = re.search(rb"/Count\s+(\d+)", data)
    res["pages"] = int(m.group(1)) if m else res["page_objects"]
    mb = re.search(rb"/MediaBox\s*\[\s*([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s*\]", data)
    if mb:
      x0, y0, x1, y1 = (float(v) for v in mb.groups())
      res["media_box"] = [round(x1 - x0, 1), round(y1 - y0, 1)]
    res["vector"] = b"/Subtype /Image" not in data and b"/Subtype/Image" not in data
    res["ok"] = bool(res["header"] and res["eof"] and (res["page_objects"] or 0) >= 1 and res["vector"])
    if not res["ok"]:
      res["error"] = "pdf_structure_incomplete"
  except Exception as e:
    res["error"] = repr(e)[:160]
  return res

def pdf_text(path, timeout=40):
  code, out, _ = ck.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], timeout=timeout)
  if code != 0 or not out.strip():
    return None
  return out

def pdf_label_hits(path, labels):
  """fraction of figure labels that survive as extractable text in the export."""
  txt = pdf_text(path)
  if txt is None:
    return None, None
  flat = nrm(txt)
  hit = [l for l in labels if nrm(l) and nrm(l) in flat]
  return round(len(hit) / len(labels), 3) if labels else None, len(hit)

def svg_audit(path):
  res = {"ok": False, "path": str(path), "ids": [], "groups": [], "text_nodes": 0, "paths": 0,
           "markers": [], "fonts": [], "min_font_pt": None, "stroke_widths": [], "min_stroke": None,
           "texts": [], "root": {}, "error": None}
  try:
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    root = ET.fromstring(txt)
    res["root"] = {"tag": root.tag.split("}")[-1], "width": root.get("width"),
                       "height": root.get("height"), "viewBox": root.get("viewBox")}
    ids, groups, fonts, strokes, texts = [], [], set(), [], []
    for el in root.iter():
      tag = el.tag.split("}")[-1]
      i = el.get("id")
      if i:
        ids.append(i)
      if tag == "g" and i:
        groups.append(i)
      elif tag == "text":
        res["text_nodes"] += 1
        texts.append("".join(el.itertext()).strip())
        fs = el.get("font-size")
        if fs:
          try:
            fonts.add(float(re.sub(r"[^0-9\.]", "", fs) or 0))
          except Exception:
            pass
      elif tag in ("path", "line", "polyline"):
        res["paths"] += 1
        sw = el.get("stroke-width")
        if sw:
          try:
            strokes.append(float(sw))
          except Exception:
            pass
      elif tag == "marker":
        res["markers"].append(i or "?")
      if el.get("font-family"):
        fonts.add(el.get("font-family"))
    res.update({"ids": ids, "groups": groups, "fonts": [f for f in fonts if isinstance(f, str)],
          "texts": texts[:80], "stroke_widths": sorted(set(strokes))});
    numeric = [f for f in fonts if isinstance(f, float)]
    res["min_font_pt"] = min(numeric) if numeric else None
    res["min_stroke"] = min(strokes) if strokes else None
    res["ok"] = (res["root"]["tag"] == "svg" and res["text_nodes"] >= 1 and bool(ids))
  except Exception as e:
    res["error"] = repr(e)[:200]
  return res

def layout_checks(model, geom=None):
  """Box geometry lives in geom["boxes"] (model entities carry content, not coordinates)."""
  boxes = (geom or {}).get("boxes") or {}
  ents = [dict(id=e["id"], **boxes[e["id"]]) for e in model.get("entities") or [] if e["id"] in boxes]
  cw, chh = model["canvas"]["width"], model["canvas"]["height"]
  overlaps, overflow = [], []
  for i, a in enumerate(ents):
    if a["x"] < 4 or a["y"] < 4 or a["x"] + a["w"] > cw - 4 or a["y"] + a["h"] > chh - 4:
      overflow.append("%s outside canvas" % a["id"])
    for b in ents[i + 1:]:
      ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
      oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
      if ox > 1 and oy > 1:
        overlaps.append("%s/%s (%.0fx%.0f)" % (a["id"], b["id"], ox, oy))
  gaps = []
  for i, a in enumerate(ents):
    for b in ents[i + 1:]:
      gaps.append(max(0, max(a["x"], b["x"]) - min(a["x"] + a["w"], b["x"] + b["w"]),
              max(a["y"], b["y"]) - min(a["y"] + a["h"], b["y"] + b["h"])))
  return {"overlaps": overlaps, "overflow": overflow,
      "min_gap": round(min(gaps), 1) if gaps else None}

def determinism(model, draw, times=2):
  hs = []
  for _ in range(times):
    try:
      svg = draw.render_svg(model)
      hs.append(hashlib.sha256(svg.encode("utf-8")).hexdigest())
    except Exception:
      hs.append(None)
  return (hs + [None, None])[0], (hs + [None, None])[1]

def draft_rules(draft, idx, docs, by_file):
  """C1..C10e over the agent's working draft. Returns rules/blocking/warnings/exceptions/stats."""
  rules, blocking, warnings, exc = [], [], [], []

  def rule(rid, ok, detail, counts=None):
    rules.append({"id": rid, "ok": bool(ok), "detail": detail, "counts": counts or {}})
    if not ok:
      blocking.append("%s: %s" % (rid, detail))

  if not isinstance(draft, dict):
    rule("C1", False, "draft.json missing or not a JSON object")
    return rules, blocking, warnings, exc, {}
  ents = [e for e in as_list(draft.get("entities")) if isinstance(e, dict)]
  rels = [r for r in as_list(draft.get("relations")) if isinstance(r, dict)]
  rule("C1", True, "draft parsed (%d entities, %d relations)" % (len(ents), len(rels)))
  ids, bad_ids = [], []
  for e in ents:
    i = str(e.get("id") or "").strip()
    if not i or i in ids:
      bad_ids.append(i or "(empty for %r)" % e.get("label"))
    ids.append(i)
  rule("C2", len(ents) >= 1 and not bad_ids and all(str(e.get("label") or "").strip() for e in ents),
         "entities=%d unique_ids=%s labels_filled=%d/%d"
         % (len(ents), not bad_ids, sum(1 for e in ents if str(e.get("label") or "").strip()), len(ents)),
         {"bad_ids": bad_ids[:6]})
  q_tot = q_here = q_near = 0
  for kind, items in (("entity", ents), ("relation", rels)):
    for it in items:
      ev = it.get("evidence") or {}
      loc, quote = ev.get("locator"), ev.get("quote")
      q_tot += 1
      here = bool(loc and quote and ck.quote_hit(quote, ck.resolve_locator(loc, by_file, {})[2] or ""))
      aloc = None if here else ck.locate_quote(quote or "", docs)[0]
      q_here += 1 if here else 0
      q_near += 1 if (aloc and not here) else 0
      if not here:
        if aloc:
          warnings.append("%s %r: quote not on the declared line %s (found at %s) - fix the locator"
                  % (kind, it.get("id"), loc, aloc))
        elif quote:
          exc.append({"type": "quote_unsourced", "object": str(it.get("id") or it.get("label")),
                "reason": "quote not found anywhere in readable material",
                "action": "element kept in the figure but marked verified=false",
                "locator": str(loc)})
  rule("C3", q_tot > 0 and q_here == q_tot, "quote verbatim on declared locator: %d/%d" % (q_here, q_tot),
         {"on_line": q_here, "elsewhere": q_near, "total": q_tot})
  rule("C4", q_here + q_near == q_tot, "quotes resolvable in material: %d/%d (off-line=%d)"
         % (q_here + q_near, q_tot, q_near))
  dangling, bad_type, passive = [], [], []
  for r in rels:
    if str(r.get("from")) not in ids or str(r.get("to")) not in ids:
      dangling.append(str(r.get("id")))
    t = str(r.get("type") or "").strip().lower()
    if t and t not in REL:
      bad_type.append("%s:%s" % (r.get("id"), t))
    quote = str((r.get("evidence") or {}).get("quote") or "")
    if t == "inhibition" and any(re.search(p, quote, re.I) for p in ck.PASSIVE):
      passive.append(str(r.get("id")))
  rule("C5", not dangling, "relation endpoints resolved %d/%d" % (len(rels) - len(dangling), len(rels)),
         {"dangling": dangling[:6]})
  rule("C6", not bad_type, "relation types in vocabulary (%d unknown)" % len(bad_type), {"unknown": bad_type[:6]})
  warnings += ["C7 passive voice on inhibition %s: direction must be inhibitor -> target" % i for i in passive]
  cov = ck.coverage(ents, rels, idx.get("workorder") or {})
  rule("C8", not cov["unmapped_required"],
         "workorder coverage: entities %d/%d, relations %d/%d%s"
         % (cov["mapped_entities"], cov["required_entities"], cov["mapped_relations"], cov["required_relations"],
      "" if not cov["unmapped_required"] else " missing=" + str(cov["unmapped_required"][:4])), cov)
  miss_lab = [e.get("label") for e in ents if e.get("label") and not ck.label_in_material(str(e["label"]), docs)]
  for m in miss_lab:
    exc.append({"type": "label_unsourced", "object": str(m),
          "reason": "label does not appear verbatim in readable material",
          "action": "flagged for human check (figure-only source possible)", "locator": None})
  rule("C9", not miss_lab, "labels verbatim in material: %d/%d" % (len(ents) - len(miss_lab), len(ents)),
         {"unsourced": [str(x) for x in miss_lab][:6]})
  legend = [g for g in as_list(draft.get("legend")) if isinstance(g, dict)]
  keys = {nrm(g.get("key") or g.get("label")) for g in legend}
  used = {nrm(r.get("type") or "association") for r in rels}
  missing = sorted(used - keys)
  rule("C10", not missing, "legend covers every encoding (%d encodings / %d legend items)"
         % (len(used), len(legend)), {"missing_keys": missing})
  if missing:
    exc.append({"type": "legend_gap", "object": missing,
          "reason": "relation types drawn without a legend entry",
          "action": "legend completed from the vocabulary map during build", "locator": None})
  edit = draft.get("edit") or {}
  if isinstance(edit, dict) and str(edit.get("mode")) == "preserve":
    ops = [o for o in as_list(edit.get("operations")) if isinstance(o, dict)]
    base_ids = set((idx.get("baseline") or {}).get("ids") or [])
    bad = [o.get("target_id") for o in ops
               if o.get("target_id") and base_ids and o["target_id"] not in base_ids]
    rule("C10e", not bad, "edit targets exist in the baseline SVG (%d operations)" % len(ops),
             {"missing_targets": bad[:6]})
  stats = {"entities": len(ents), "relations": len(rels), "quotes": q_tot,
             "quotes_on_line": q_here, "coverage": cov, "legend_items": len(legend)}
  return rules, blocking, warnings, exc, stats
