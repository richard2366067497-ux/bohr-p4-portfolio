#!/usr/bin/env python3
"""schematic-trace-studio :: model -> layout -> one geometry -> SVG.

`geometry(model)` is the single source of coordinates. It feeds the SVG serialiser here and the
PNG/PDF exporters in render.py, which is why `content_map.svg_ids_expected` can be asserted
against the emitted SVG: there is no second geometry to drift.
"""
import math
import re

import casekit as ck
import render as rd

FONT = "Arial, Helvetica, 'DejaVu Sans', sans-serif"
STY = {"title": 15.0, "entity": 11.0, "note": 9.3, "legend": 9.3,
       "lw_box": 1.0, "lw_edge": 1.1, "lw_band": 0.8,
       "ink": "#1A1A1A", "box_fill": "#F4F7FA", "box_stroke": "#33404D",
       "band_fill": "#FBFBF7", "band_stroke": "#9AA3AB", "paper": "#FFFFFF"}
PAD, PADY, GAPX, GAPY, M, TITLE_H = 9, 7, 64, 34, 26, 46
MARKERS = {"arrow": "M0,0 L9,4.5 L0,9 z", "thin": "M0,1.5 L7,3.5 L0,5.5 z",
           "tbar": "M1,0 L1,9", "diamond": "M0,4.5 L4.5,0 L9,4.5 L4.5,9 z",
           "square": "M1,1 L1,8 L8,8 L8,1 z", "line": ""}

def est_w(s, size):
  """width estimate in px; CJK counts ~1.0 em, latin ~0.56 em."""
  return sum(1.0 if ord(ch) > 0x2E80 else (0.34 if ch in " .,:;'|!il" else 0.56)
               for ch in str(s)) * size

def wrap(label, size, max_w):
  parts = re.split(r"(\s+|(?<=[/\-_]))", str(label))
  lines, cur = [], ""
  for w in parts:
    if not w:
      continue
    if est_w(cur + w, size) <= max_w or not cur.strip():
      cur += w
    else:
      lines.append(cur.strip())
      cur = w
  if cur.strip():
    lines.append(cur.strip())
  out = []
  for ln in lines:                                   # hard-split over-long CJK runs
    while est_w(ln, size) > max_w * 1.35 and len(ln) > 4:
      cut = max(2, int(len(ln) * max_w * 1.1 / max(1e-6, est_w(ln, size))))
      out.append(ln[:cut])
      ln = ln[cut:]
    out.append(ln)
  return out[:4] or [str(label)[:32]]

def sid(s):
  s = re.sub(r"[^0-9A-Za-z_.\-]+", "-", str(s)).strip("-")
  return s or "x"

def make_model(draft, idx, REL):
  """Normalise the draft into the figure model: ids, markers, legend completeness, groups."""
  wo = idx.get("workorder") or {}
  ents, used = [], {}
  for i, e in enumerate([x for x in ck.as_list(draft.get("entities")) if isinstance(x, dict)]):
    eid = sid(e.get("id") or "e%d" % (i + 1))
    if eid in used:
      eid = "%s-%d" % (eid, i + 1)
    used[eid] = True
    ents.append({"id": eid, "label": str(e.get("label") or eid).strip(),
                     "entity_type": str(e.get("entity_type") or ""), "group": str(e.get("group") or ""),
                     "col": e.get("col") if isinstance(e.get("col"), int) else None,
                     "row": e.get("row") if isinstance(e.get("row"), int) else None,
                     "evidence": e.get("evidence") or {}})
  rels, dropped = [], []
  for i, r in enumerate([x for x in ck.as_list(draft.get("relations")) if isinstance(x, dict)]):
    a, b = sid(r.get("from")), sid(r.get("to"))
    if a not in used or b not in used or a == b:
      dropped.append({"id": str(r.get("id") or i), "from": r.get("from"), "to": r.get("to"),
              "reason": "endpoint is not a drawn entity"})
      continue
    if str(r.get("direction") or "").lower() in ("reversed", "reverse", "backward"):
      a, b = b, a
    typ = str(r.get("type") or "association").strip().lower().replace(" ", "_")
    if typ not in REL:
      typ = "association"
    rels.append({"id": sid(r.get("id") or "r%d" % (i + 1)), "from": a, "to": b, "type": typ,
                     "direction": str(r.get("direction") or "forward"),
                     "condition": str(r.get("condition") or ""),
                     "marker": REL[typ]["marker"], "color": REL[typ]["color"],
                     "label": REL[typ]["label"], "evidence": r.get("evidence") or {}})
  gl = {}
  for g in [x for x in ck.as_list(draft.get("legend")) if isinstance(x, dict)]:
    k = ck.nrm(g.get("key") or g.get("label"))
    if not k:
      continue
    base = REL.get(k, {})
    gl[k] = {"key": k, "label": str(g.get("label") or base.get("label") or k),
                 "color": str(g.get("color") or base.get("color") or "#3C3C3C"),
                 "marker": str(g.get("marker") or base.get("marker") or "line")}
  for r in rels:                                     # legend must cover every encoding drawn
    if r["type"] not in gl:
      gl[r["type"]] = {"key": r["type"], "label": r["label"], "color": r["color"], "marker": r["marker"]}
  legend = [dict(v, id="lg-%d" % (i + 1)) for i, (_k, v) in enumerate(sorted(gl.items()))]
  by_label = {}
  for g in [x for x in ck.as_list(draft.get("groups")) if isinstance(x, dict)]:
    mem = [sid(m) for m in ck.as_list(g.get("members")) if sid(m) in used]
    if str(g.get("label") or "") and mem:
      by_label.setdefault(str(g["label"]), set()).update(mem)
  for e in ents:
    if e["group"]:
      by_label.setdefault(e["group"], set()).add(e["id"])
  groups = [{"id": "grp-%d" % (i + 1), "label": lab, "members": sorted(mem)}
              for i, (lab, mem) in enumerate(sorted(by_label.items())) if len(mem) >= 2]
  ann = [{"id": "note-%d" % (i + 1),
      "text": str(a.get("text") if isinstance(a, dict) else a),
      "evidence": (a.get("evidence") if isinstance(a, dict) else {}) or {}}
           for i, a in enumerate(ck.as_list(draft.get("annotations"))) if a]
  chart = draft.get("chart") if isinstance(draft.get("chart"), dict) else None
  if chart:
    chart = {"title": str(chart.get("title") or ""), "unit": str(chart.get("unit") or ""),
                 "rows": [{"label": str(r.get("label")), "value": r.get("value"),
                           "color": str(r.get("color") or "#0072B2")}
                          for r in ck.as_list(chart.get("rows")) if isinstance(r, dict)]}
  cw = wo.get("canvas") or {}
  canvas = {"width": int(cw.get("width") or 960), "height": int(cw.get("height") or 560),
              "unit": str(cw.get("unit") or "px"), "background": STY["paper"],
              "min_width": int(cw.get("width") or 0), "min_height": int(cw.get("height") or 0)}
  return {"schema": "figure_model/v1", "case_id": idx.get("case_id"),
      "title": str((draft.get("figure") or {}).get("title") or wo.get("title") or ""),
      "kind": str((draft.get("figure") or {}).get("kind") or wo.get("kind") or "relationship_schematic"),
      "canvas": canvas,
      "style": {"font_family": FONT, "min_font_px": STY["note"], "line_width": STY["lw_edge"],
                      "palette": sorted({g["color"] for g in legend})},
      "entities": ents, "relations": rels, "legend": legend, "groups": groups,
      "annotations": ann, "chart": chart, "dropped_relations": dropped,
      "layers": ["layer-background", "layer-groups", "layer-edges", "layer-entities",
                       "layer-labels", "layer-title", "layer-legend", "layer-notes"]}

def _levels(ents, rels):
  ids = [e["id"] for e in ents]
  adj = {i: [] for i in ids}
  for r in rels:
    adj[r["from"]].append(r["to"])
  state, keep = {}, []

  def dfs(u):
    state[u] = 1
    for v in adj.get(u, []):
      if state.get(v) == 1:                      # back edge: dropped, cycle recorded
        continue
      keep.append((u, v))
      if state.get(v) is None:
        dfs(v)
    state[u] = 2

  for i in ids:
    if state.get(i) is None:
      dfs(i)
  lv = {i: 0 for i in ids}
  for _ in range(len(ids) + 1):
    changed = False
    for a, b in keep:
      if lv[b] < lv[a] + 1:
        lv[b], changed = lv[a] + 1, True
    if not changed:
      break
  return lv, len(keep) < len(rels)

def _chart(model, x0, y0, w, h):
  rows = model["chart"]["rows"]
  try:
    vals = [float(r["value"]) for r in rows]
  except Exception:
    return []
  vmax = max(vals) if max(vals) > 0 else 1.0
  out = [{"layer": "notes", "kind": "text", "id": "chart-title", "x": M, "y": round(y0, 2),
      "lines": [(model["chart"].get("title") or "Values") +
                      (" (%s)" % model["chart"]["unit"] if model["chart"].get("unit") else "")],
      "size": STY["note"], "anchor": "start", "weight": "700", "fill": STY["ink"]}]
  step = (w - 60) / max(1, len(rows))
  bw = max(14.0, step * 0.6)
  for i, r in enumerate(rows):
    bh = h * vals[i] / vmax * 0.8
    bx, by = x0 + 46 + i * step, y0 + 22 + (h - bh)
    out.append({"layer": "notes", "kind": "rect", "id": "bar-%d" % (i + 1), "x": round(bx, 2),
          "y": round(by, 2), "w": round(bw, 2), "h": round(bh, 2), "rx": 1,
          "fill": r["color"], "stroke": "#2B2B2B", "lw": 0.6})
    out.append({"layer": "notes", "kind": "text", "id": "bar-%d-value" % (i + 1),
          "x": round(bx + bw / 2, 2), "y": round(by - 4, 2), "lines": [str(r["value"])],
          "size": STY["note"] - 1, "anchor": "middle", "weight": "400", "fill": STY["ink"]})
    out.append({"layer": "notes", "kind": "text", "id": "bar-%d-label" % (i + 1),
          "x": round(bx + bw / 2, 2), "y": round(y0 + 22 + h + 10, 2),
          "lines": [r["label"][:18]], "size": STY["note"] - 1, "anchor": "middle",
          "weight": "400", "fill": STY["ink"]})
  out.append({"layer": "notes", "kind": "path", "id": "chart-axis",
        "pts": [[x0 + 44, y0 + 22], [x0 + 44, y0 + 22 + h], [x0 + w - 4, y0 + 22 + h]],
        "stroke": "#2B2B2B", "lw": 1.0, "marker": "line", "dash": None})
  return out

def geometry(model):
  ents, rels = model["entities"], model["relations"]
  items, boxes = [], {}
  cw0, ch0 = model["canvas"]["width"], model["canvas"]["height"]
  if not ents:
    items.append({"layer": "background", "kind": "rect", "id": "bg", "x": 0, "y": 0, "w": cw0,
                      "h": ch0, "fill": STY["paper"], "stroke": None, "lw": 0})
    items.append({"layer": "title", "kind": "text", "id": "title", "x": M, "y": M + 12,
                      "lines": [model["title"] or "No drawable content"], "size": STY["title"],
                      "anchor": "start", "weight": "700", "fill": STY["ink"]})
    items.append({"layer": "notes", "kind": "text", "id": "note-empty", "x": M, "y": M + 40,
                      "lines": ["No entity could be sourced from the input material."],
                      "size": STY["note"], "anchor": "start", "weight": "400", "fill": "#8A8A8A"})
    return {"canvas": model["canvas"], "items": items, "boxes": {}, "cycle_broken": False}
  lv, cycle_broken = _levels(ents, rels)
  for e in ents:
    if e.get("col") is not None:
      lv[e["id"]] = max(0, int(e["col"]))
  cols = {}
  for e in ents:
    cols.setdefault(lv[e["id"]], []).append(e)
  for k in cols:
    cols[k].sort(key=lambda e: (e["row"] if e.get("row") is not None else 10 ** 6, e["id"]))
  ncols = max(cols) + 1
  metrics, nw, nh = {}, 90.0, 42.0
  for e in ents:
    lines = wrap(e["label"], STY["entity"], 132)
    w = max(est_w(l, STY["entity"]) for l in lines) + 2 * PAD
    h = len(lines) * (STY["entity"] * 1.18) + 2 * PADY
    metrics[e["id"]] = (lines, max(78.0, w), max(38.0, h))
    nw, nh = max(nw, metrics[e["id"]][1]), max(nh, metrics[e["id"]][2])
  maxrows = max(len(v) for v in cols.values())
  diag_w = ncols * nw + (ncols - 1) * GAPX
  diag_h = maxrows * nh + (maxrows - 1) * GAPY
  lrows = max(1, math.ceil(len(model["legend"]) / 4)) if model["legend"] else 0
  legend_h = (18 + lrows * 17) if model["legend"] else 0
  notes_h = (len(model["annotations"]) * 15 + 10) if model["annotations"] else 0
  chart_h = 150 if (model.get("chart") or {}).get("rows") else 0
  cw = max(int(model["canvas"].get("min_width") or 0), int(2 * M + diag_w), 640)
  chh = max(int(model["canvas"].get("min_height") or 0),
              int(TITLE_H + diag_h + 20 + legend_h + notes_h + chart_h + M), 420)
  model["canvas"].update({"width": int(cw), "height": int(chh)})
  dx = (cw - diag_w) / 2.0
  for c, members in sorted(cols.items()):
    x = dx + c * (nw + GAPX)
    off = (maxrows - len(members)) * (nh + GAPY) / 2.0
    for k, e in enumerate(members):
      y = TITLE_H + off + k * (nh + GAPY)
      bx = {"x": round(x + (nw - metrics[e["id"]][1]) / 2.0, 2), "y": round(y, 2),
                  "w": round(metrics[e["id"]][1], 2), "h": round(nh, 2), "col": c}
      bx["cx"], bx["cy"] = round(bx["x"] + bx["w"] / 2, 2), round(bx["y"] + bx["h"] / 2, 2)
      boxes[e["id"]] = bx
  bottom = max((b["y"] + b["h"]) for b in boxes.values())
  items.append({"layer": "background", "kind": "rect", "id": "bg", "x": 0, "y": 0, "w": cw, "h": chh,
                  "fill": STY["paper"], "stroke": None, "lw": 0})
  items.append({"layer": "title", "kind": "text", "id": "title", "x": M, "y": M + 8,
                  "lines": wrap(model["title"] or "Schematic", STY["title"], cw - 2 * M),
                  "size": STY["title"], "anchor": "start", "weight": "700", "fill": STY["ink"]})
  for g in model["groups"]:
    boxes_g = [boxes[m] for m in g["members"] if m in boxes]
    if not boxes_g:
      continue
    x0 = min(p["x"] for p in boxes_g) - 12
    y0 = min(p["y"] for p in boxes_g) - 14
    x1 = max(p["x"] + p["w"] for p in boxes_g) + 12
    y1 = max(p["y"] + p["h"] for p in boxes_g) + 11
    items.append({"layer": "groups", "kind": "rect", "id": g["id"] + "-band", "x": round(x0, 2),
                      "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2), "rx": 8,
                      "fill": STY["band_fill"], "stroke": STY["band_stroke"], "lw": STY["lw_band"],
                      "dash": "5 4"})
    items.append({"layer": "groups", "kind": "text", "id": g["id"] + "-label", "x": round(x0 + 7, 2),
                      "y": round(y0 + 11, 2), "lines": [g["label"]], "size": STY["note"] - 0.6,
                      "anchor": "start", "weight": "600", "fill": "#5B666F"})
  per = {}
  for r in sorted(rels, key=lambda r: (boxes[r["from"]]["col"], boxes[r["to"]]["col"],
                                         r["from"], r["to"], r["id"])):
    a, b = boxes[r["from"]], boxes[r["to"]]
    key = tuple(sorted((r["from"], r["to"])))
    k = per.get(key, 0)
    per[key] = k + 1
    sp = (k - k // 2) * 9 * (1 if k % 2 == 0 else -1)
    if b["col"] > a["col"]:
      p0 = [a["x"] + a["w"], round(a["cy"] + sp, 2)]
      p1 = [b["x"] - 3, round(b["cy"] + sp, 2)]
      mx = round((p0[0] + p1[0]) / 2.0, 2)
      pts = [p0, [mx, p0[1]], [mx, p1[1]], p1]
    elif b["col"] < a["col"]:                      # feedback arc routed below the diagram
      y = round(bottom + 16 + 9 * k, 2)
      pts = [[a["cx"], a["y"] + a["h"]], [a["cx"], y], [b["cx"], y], [b["cx"], b["y"] + b["h"] + 3]]
    else:                                          # same column: detour to the right
      x = round(max(a["x"] + a["w"], b["x"] + b["w"]) + 16 + 9 * k, 2)
      pts = [[a["x"] + a["w"], a["cy"]], [x, a["cy"]], [x, b["cy"]], [b["x"] + b["w"] + 3, b["cy"]]]
    items.append({"layer": "edges", "kind": "path", "id": r["id"] + "-path", "pts": pts,
                      "stroke": r["color"], "lw": STY["lw_edge"], "marker": r["marker"],
                      "dash": "4 3" if r["type"] in ("association", "containment") else None,
                      "data": {"rel-type": r["type"], "from": r["from"], "to": r["to"]}})
  for e in ents:
    b, (lines, _w, _h) = boxes[e["id"]], metrics[e["id"]]
    items.append({"layer": "entities", "kind": "rect", "id": e["id"] + "-box", "x": b["x"], "y": b["y"],
                      "w": b["w"], "h": b["h"], "rx": 7, "fill": STY["box_fill"],
                      "stroke": STY["box_stroke"], "lw": STY["lw_box"],
                      "data": {"entity-id": e["id"], "entity-type": e["entity_type"]}})
    lh = STY["entity"] * 1.18
    y0 = b["cy"] - (len(lines) - 1) * lh / 2.0 + STY["entity"] * 0.35
    items.append({"layer": "labels", "kind": "text", "id": e["id"] + "-label", "x": b["cx"],
                      "y": round(y0, 2), "lines": lines, "lh": round(lh, 2), "size": STY["entity"],
                      "anchor": "middle", "weight": "600", "fill": STY["ink"]})
  for r in rels:
    if not r.get("condition"):
      continue
    a, b = boxes[r["from"]], boxes[r["to"]]
    items.append({"layer": "edges", "kind": "text", "id": r["id"] + "-cond",
                      "x": round((a["cx"] + b["cx"]) / 2.0, 2), "y": round((a["cy"] + b["cy"]) / 2.0 - 4, 2),
                      "lines": [r["condition"][:40]], "size": STY["note"] - 1, "anchor": "middle",
                      "weight": "400", "fill": "#6B7480"})
  y = max(bottom + 26, TITLE_H + diag_h + 26)
  if model["legend"]:
    items.append({"layer": "legend", "kind": "text", "id": "legend-title", "x": M, "y": round(y, 2),
                      "lines": ["Legend"], "size": STY["note"], "anchor": "start", "weight": "700",
                      "fill": STY["ink"]})
    percol = max(120.0, (cw - 2 * M) / 4.0)
    for i, g in enumerate(model["legend"]):
      row, col = divmod(i, 4)
      gx, gy = M + col * percol, y + 16 + row * 17
      items.append({"layer": "legend", "kind": "path", "id": g["id"] + "-swatch",
                          "pts": [[round(gx, 2), round(gy, 2)], [round(gx + 24, 2), round(gy, 2)]],
                          "stroke": g["color"], "lw": 1.3, "marker": g["marker"], "dash": None})
      items.append({"layer": "legend", "kind": "text", "id": g["id"] + "-label",
                          "x": round(gx + 31, 2), "y": round(gy + 3.2, 2), "lines": [g["label"]],
                          "size": STY["legend"], "anchor": "start", "weight": "400", "fill": STY["ink"]})
    y += 14 + lrows * 17
  if (model.get("chart") or {}).get("rows"):
    items += _chart(model, M, y + 4, cw - 2 * M, 108)
    y += chart_h - 14
  for a in model["annotations"]:
    lines = wrap(a["text"], STY["note"], cw - 2 * M)
    items.append({"layer": "notes", "kind": "text", "id": a["id"], "x": M, "y": round(y + 12, 2),
                      "lines": lines, "lh": round(STY["note"] * 1.18, 2), "size": STY["note"],
                      "anchor": "start", "weight": "400", "fill": "#5B666F"})
    y += 13 * len(lines) + 2
  return {"canvas": model["canvas"], "items": items, "boxes": boxes, "cycle_broken": cycle_broken}

def _num(v):
  return ("%.2f" % float(v)).rstrip("0").rstrip(".")

def _esc(s):
  return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

def _data(it):
  d = it.get("data") or {}
  return "".join(' data-%s="%s"' % (k, _esc(v)) for k, v in sorted(d.items()))

def marker_id(marker, color):
  """one marker def per (semantics, colour) pair: arrows must match the relation colour and
  ImageMagick/librsvg do not understand `context-stroke`."""
  return "mk-%s-%s" % (marker, str(color or "#333333").lstrip("#").lower())

def svg_doc(geom, model):
  cw, chh = geom["canvas"]["width"], geom["canvas"]["height"]
  used = sorted({(i["marker"], i.get("stroke")) for i in geom["items"]
                   if i.get("marker") and i["marker"] != "line"})
  out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="%d" height="%d" '
           'viewBox="0 0 %d %d" data-figure="%s" data-schema="figure_model/v1" font-family="%s">'
           % (cw, chh, cw, chh, _esc(model.get("case_id") or "figure"), FONT),
           "  <title>%s</title>" % _esc(model.get("title") or "Schematic"),
           "  <desc>Editable, source-bound schematic. Layers: %s. Every element id is listed in "
           "content_map of result.json.</desc>" % ", ".join(model["layers"]),
           "  <defs>"]
  refs = {"arrow": 9, "thin": 7, "tbar": 1, "diamond": 9, "square": 1}
  for m, col in used:
    style = (' stroke="%s" stroke-width="1.8" fill="none"' % col if m == "tbar"
                 else ' fill="%s" stroke="none"' % col)
    out.append('    <marker id="%s" viewBox="0 0 10 10" refX="%s" refY="4.5" markerWidth="10" '
                   'markerHeight="10" markerUnits="userSpaceOnUse" orient="auto">'
                   '<path d="%s"%s/></marker>' % (marker_id(m, col), refs.get(m, 0),
                                                  MARKERS.get(m, ""), style))
  out.append("  </defs>")
  for layer in model["layers"]:
    name = layer.replace("layer-", "")
    sel = [i for i in geom["items"] if i["layer"] == name]
    if not sel:
      continue
    out.append('  <g id="%s" data-layer="%s">' % (layer, name))
    for it in sel:
      if it["kind"] == "rect":
        attrs = ('x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"'
                         % (_num(it["x"]), _num(it["y"]), _num(it["w"]), _num(it["h"]),
              _num(it.get("rx", 0)), it.get("fill") or "none"))
        if it.get("stroke"):
          attrs += ' stroke="%s" stroke-width="%s"%s' % (
            it["stroke"], _num(it.get("lw", 1)),
            ' stroke-dasharray="%s"' % it["dash"] if it.get("dash") else "")
        out.append('    <rect id="%s" %s%s/>' % (it["id"], attrs, _data(it)))
      elif it["kind"] == "path":
        d = "M" + " L".join("%s,%s" % (_num(p[0]), _num(p[1])) for p in it["pts"])
        mk = it.get("marker")
        ex = (' marker-end="url(#%s)"' % marker_id("square" if mk == "line" else mk, it.get("stroke"))
                      if mk else "")
        out.append('    <path id="%s" d="%s" fill="none" stroke="%s" stroke-width="%s" '
                           'stroke-linecap="round" stroke-linejoin="round"%s%s%s/>'
                           % (it["id"], d, it["stroke"], _num(it.get("lw", 1)),
                              ' stroke-dasharray="%s"' % it["dash"] if it.get("dash") else "", ex, _data(it)))
      elif it["kind"] == "text":
        spans = "".join('<tspan x="%s"%s>%s</tspan>'
                % (_num(it["x"]), ' dy="%s"' % _num(it.get("lh", it["size"] * 1.18)) if k else "",
                                   _esc(ln)) for k, ln in enumerate(it["lines"]))
        out.append('    <text id="%s" x="%s" y="%s" font-size="%s" font-weight="%s" '
                           'text-anchor="%s" fill="%s"%s>%s</text>'
                           % (it["id"], _num(it["x"]), _num(it["y"]), _num(it["size"]),
                              it.get("weight", "400"), it.get("anchor", "start"),
                              it.get("fill", STY["ink"]), _data(it), spans))
    out.append("  </g>")
  out.append("</svg>")
  return "\n".join(out) + "\n"

def render_svg(model):
  return svg_doc(geometry(model), model)

# public exporters live in render.py (single geometry is imported, not recomputed)
def write_outputs(model, geom, outdir):
  return rd.write_outputs(model, geom, outdir)

def edit_record(baseline, draft):
  return rd.edit_record(baseline, draft)
