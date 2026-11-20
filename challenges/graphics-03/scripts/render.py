"""Layout, SVG and geometry audits for mechanism-figure-ledger.

Compartments become upstream->downstream lanes, membrane proteins straddle the
bilayer, edges are orthogonal and semantic (activation arrow vs inhibition T-bar).
`display()` is the shared primitive list consumed by export.py (PDF/PNG), so all
three artifacts use one geometry; `probe()` recomputes the consistency gates.
"""
import math
import re
import xml.etree.ElementTree as ET

CANVAS = {"w": 1600, "h": 1000}
MARGIN = 48
TITLE_H = 84
MIN_FONT = 14
LAYER_IDS = ["layer-title", "layer-compartments", "layer-entities", "layer-edges",
             "layer-labels", "layer-legend", "layer-notes"]
FONT_FAMILY = "Helvetica, Arial, 'Liberation Sans', sans-serif"

EDGE_STYLE = {
    "activation":   {"marker": "arrow",  "dash": None,      "width": 2.4, "color": "#1F6FB2"},
    "inhibition":   {"marker": "tee",    "dash": None,      "width": 2.4, "color": "#C0392B"},
    "binding":      {"marker": "hollow", "dash": None,      "width": 2.0, "color": "#2E7D5B"},
    "modification": {"marker": "arrow",  "dash": None,      "width": 2.0, "color": "#8E44AD"},
    "transport":    {"marker": "double", "dash": None,      "width": 3.4, "color": "#B9770E"},
    "recruitment":  {"marker": "dot",    "dash": None,      "width": 1.8, "color": "#5D6D7E"},
    "indirect":     {"marker": "arrow",  "dash": "7 5",     "width": 1.8, "color": "#7F8C8D"},
    "unspecified":  {"marker": "none",   "dash": "2 3 7 3", "width": 1.6, "color": "#95A5A6"},
}
ENTITY_FILL = {"gene": "#F7E7C6", "protein": "#CFE3F5", "complex": "#D7CDEB",
               "ligand": "#CDEFD8", "receptor": "#F5D2C8", "cell_type": "#E8E1CF",
               "compartment": "#E3E8EA", "metabolite": "#F0E6A8", "mirna": "#E6D3F0",
               "phenotype": "#E9E9E9", "unspecified": "#ECEFF1"}


def tw(s, size, bold=False):
    """Approximate advance width: CJK ~1em, narrow latin ~0.34em, upper/digit ~0.62em."""
    total = 0.0
    for ch in str(s):
        if ch == " ":
            total += 0.28
        elif ord(ch) > 0x2E80:
            total += 1.0
        elif ch in "iljtf.,:;'|!()[]":
            total += 0.34
        elif ch.isupper() or ch.isdigit():
            total += 0.62
        else:
            total += 0.52
    return total * size * (1.05 if bold else 1.0)


def wrap(s, size, maxw, max_lines=2):
    s = str(s or "")
    if tw(s, size) <= maxw:
        return [s]
    words, lines, cur = s.split(" "), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if tw(trial, size) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines - 1:
                break
    if cur:
        lines.append(cur)
    if len(lines) >= 2 and tw(lines[-1], size) > maxw:
        keep = max(3, int(len(lines[-1]) * maxw / max(tw(lines[-1], size), 1)))
        lines[-1] = lines[-1][:keep].rstrip() + "…"
    return lines[:max_lines]


def layout(model):
    """Attach lane geometry, entity boxes, orthogonal paths and the display list."""
    comps = [c for c in model.get("compartments", []) if isinstance(c, dict)]
    bycomp = {}
    for e in model["entities"]:
        bycomp.setdefault(e["compartment"], []).append(e)
    if not comps:
        comps = [{"id": "all", "label": "Mechanism", "order": 0}]
    used = [c for c in comps if c["id"] in bycomp] or comps
    used.sort(key=lambda c: (c.get("order", 0), c["id"]))

    etypes = sorted({e["type"] for e in model["entities"]})
    rtypes = sorted({r["type"] for r in model["relations"]})
    legend_rows, declared_keys = [], set()
    for t in etypes:
        legend_rows.append({"channel": "color", "key": t, "label": t.replace("_", " "),
                            "meaning": "entity type"})
    for t in rtypes:
        legend_rows.append({"channel": "line_style", "key": t, "label": t.replace("_", " "),
                            "meaning": "relation type"})
    have = {(r["channel"], r["key"]) for r in legend_rows}
    for l in (model.get("legend") or []):
        if not isinstance(l, dict):
            continue
        for k in (l.get("mapping") or {}):
            key = (l.get("channel", "color"), str(k))
            declared_keys.add(key)
            if key in have:
                continue                      # already auto-generated: no duplicate row
            have.add(key)
            legend_rows.append({"channel": key[0], "key": key[1], "label": key[1],
                                "meaning": l.get("meaning", ""), "declared": True})

    rows = max(1, int(math.ceil(len(legend_rows) / 4.0)))
    legend_h = max(76, 30 * rows + 38)
    plot_top = MARGIN + TITLE_H
    plot_bottom = CANVAS["h"] - MARGIN - legend_h
    avail = max(120.0, plot_bottom - plot_top)

    counts = [max(1, len(bycomp.get(c["id"], []))) for c in used]
    weights = [0.75 + 0.45 * n for n in counts]
    heights = [avail * w / sum(weights) for w in weights]
    y = plot_top
    lane_w = CANVAS["w"] - 2 * MARGIN
    for c, hgt in zip(used, heights):
        c["y"], c["h"], c["x"], c["w"] = y, hgt, MARGIN, lane_w
        if not c.get("kind"):
            c["kind"] = "membrane" if re.search(r"membrane|膜", str(c.get("id")) + str(c.get("label")), re.I) else "lane"
        y += hgt

    for c in used:
        items = bycomp.get(c["id"], [])
        n = max(1, len(items))
        nrows = 1 if n <= 4 else (2 if n <= 9 else 3)
        ncols = int(math.ceil(n / float(nrows)))
        bw = min(212.0, max(126.0, (c["w"] - 2 * 16) / max(ncols, 1) - 18))
        bh = 54.0
        gapx = (c["w"] - bw * ncols) / max(ncols, 1)
        gapy = min(34.0, max(0.0, (c["h"] - bh * nrows) / max(nrows, 1)))
        top = c["y"] + max(26.0, (c["h"] - (bh * nrows + gapy * (nrows - 1))) / 2.0)
        if c["kind"] == "membrane":
            top = c["y"] + c["h"] / 2.0 - bh / 2.0
        for i, e in enumerate(items):
            r, col = i // ncols, i % ncols
            x = c["x"] + gapx * (col + 0.5) + bw * col
            yy = top + (bh + gapy) * r
            e["box"] = {"x": x, "y": yy, "w": bw, "h": bh, "cx": x + bw / 2.0, "cy": yy + bh / 2.0}

    boxes = {e["id"]: e["box"] for e in model["entities"] if e.get("box")}
    for i, r in enumerate(model["relations"]):
        a, b = boxes.get(r["from"]), boxes.get(r["to"])
        if not (a and b):
            continue
        r["path"] = route(a, b, i)

    model["compartments"] = used
    model["legend_rows"] = legend_rows
    model["legend_used"] = {(r["channel"], r["key"]) for r in legend_rows if not r.get("declared")}
    model["legend_declared"] = declared_keys
    model["legend_h"] = legend_h
    model["dl"] = display(model)
    return model


def route(a, b, idx):
    if abs(b["cy"] - a["cy"]) > 80:
        down = b["cy"] > a["cy"]
        p0 = (a["cx"], a["y"] + a["h"] if down else a["y"])
        p1 = (b["cx"], b["y"] if down else b["y"] + b["h"])
        my = (p0[1] + p1[1]) / 2.0 + (idx % 3 - 1) * 5
        return [p0, (p0[0], my), (p1[0], my), p1]
    right = b["cx"] > a["cx"]
    p0 = (a["x"] + a["w"], a["cy"]) if right else (a["x"], a["cy"])
    p1 = (b["x"], b["cy"]) if right else (b["x"] + b["w"], b["cy"])
    mx = (p0[0] + p1[0]) / 2.0
    return [p0, (mx, p0[1]), (mx, p1[1]), p1]


def legend_geom(model):
    rows = model.get("legend_rows") or []
    top = CANVAS["h"] - MARGIN - model.get("legend_h", 76)
    colw = (CANVAS["w"] - 2 * MARGIN) / 4.0
    out = []
    for i, r in enumerate(rows):
        out.append({"row": r, "x": MARGIN + (i % 4) * colw, "y": top + 46 + (i // 4) * 30,
                    "label": "%s: %s" % (r["meaning"] or r["channel"], r["label"])[:34]})
    return top, out


def marker(path, st, rel):
    out = []
    p, q = path[-2], path[-1]
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    kind = st["marker"]
    if kind == "none":
        return out
    if kind == "tee":
        px, py = -math.sin(ang), math.cos(ang)
        return [("line", q[0] - px * 9, q[1] - py * 9, q[0] + px * 9, q[1] + py * 9, st["color"], 3.2, None)]
    if kind == "dot":
        return [("poly", [(q[0], q[1] - 5), (q[0] + 5, q[1]), (q[0], q[1] + 5), (q[0] - 5, q[1])],
                 st["color"], st["color"], 1.0)]
    tips = [q]
    if kind == "double":
        tips.append((q[0] - math.cos(ang) * 12, q[1] - math.sin(ang) * 12))
    for tip in tips:
        bx, by = tip[0] - math.cos(ang) * 11, tip[1] - math.sin(ang) * 11
        px, py = -math.sin(ang) * 4.6, math.cos(ang) * 4.6
        pts = [tip, (bx + px, by + py), (bx - px, by - py)]
        if kind == "hollow":
            out.append(("poly", pts, "#FFFFFF", st["color"], 1.6))
        else:
            out.append(("poly", pts, st["color"], st["color"], 1.0))
    return out


def legend_swatch(model, dl):
    top, rows = legend_geom(model)
    dl.append(("line", MARGIN, top, CANVAS["w"] - MARGIN, top, "#CFD8DC", 1.0, None))
    dl.append(("text", MARGIN, top + 22, 14, "Legend (generated from what the canvas encodes)",
               "#37474F", False, True, "start"))
    for item in rows:
        r, x, y = item["row"], item["x"], item["y"]
        if r["channel"] == "color":
            dl.append(("rect", x, y - 12, 18, 14, ENTITY_FILL.get(r["key"], "#ECEFF1"),
                       "#546E7A", 1.0, 3))
        else:
            st = EDGE_STYLE.get(r["key"], EDGE_STYLE["unspecified"])
            dl.append(("line", x, y - 5, x + 22, y - 5, st["color"], st["width"], st["dash"]))
            dl.extend(marker([(x + 2, y - 5), (x + 22, y - 5)], st, {})[:1])
        dl.append(("text", x + 28, y, 14, item["label"], "#37474F", False, False, "start"))


def display(model):
    """Shared primitive list: rect / line / poly / text, consumed by export.py."""
    dl = []
    y_title = MARGIN + 26
    dl.append(("text", CANVAS["w"] / 2.0, y_title, 25, model.get("title") or "Mechanism figure",
               "#1B2A33", True, True, "middle"))
    if model.get("subtitle"):
        dl.append(("text", CANVAS["w"] / 2.0, y_title + 26, 14, str(model["subtitle"])[:150],
                   "#5D6D7E", False, False, "middle"))
    for c in model.get("compartments", []):
        if "y" not in c:
            continue
        dl.append(("rect", c["x"], c["y"], c["w"], c["h"], "#FAFBFC", "#D5DBDF", 1.0, 4))
        dl.append(("text", c["x"] + 12, c["y"] + 24, 15, c["label"], "#37474F", False, True, "start"))
        if c.get("kind") == "membrane":
            my = c["y"] + c["h"] / 2.0
            dl.append(("line", c["x"] + 12, my - 6, c["x"] + c["w"] - 12, my - 6, "#90A4AE", 2.0, None))
            dl.append(("line", c["x"] + 12, my + 6, c["x"] + c["w"] - 12, my + 6, "#90A4AE", 2.0, None))
    for e in model["entities"]:
        bx = e.get("box")
        if not bx:
            continue
        dl.append(("rect", bx["x"], bx["y"], bx["w"], bx["h"],
                   ENTITY_FILL.get(e["type"], ENTITY_FILL["unspecified"]),
                   "#8A5A2B" if e["type"] == "gene" else "#546E7A",
                   2.4 if e["type"] == "complex" else 1.3, 9))
        lines = wrap(e["name"], 15, bx["w"] - 16)
        base = bx["cy"] - (len(lines) - 1) * 8 + (5 if e.get("sublabel") else 0)
        for k, ln in enumerate(lines):
            dl.append(("text", bx["cx"], base + k * 17, 15, ln, "#102A33",
                       bool(e["italic"]), False, "middle"))
        if e.get("sublabel"):
            dl.append(("text", bx["cx"], bx["y"] + bx["h"] - 7, 14, str(e["sublabel"])[:26],
                       "#546E7A", False, False, "middle"))
    for r in model.get("relations", []):
        path = r.get("path")
        if not path:
            continue
        st = EDGE_STYLE.get(r["type"], EDGE_STYLE["unspecified"])
        for p, q in zip(path, path[1:]):
            dl.append(("line", p[0], p[1], q[0], q[1], st["color"], st["width"], st["dash"]))
        dl.extend(marker(path, st, r))
        if r.get("label"):
            mid = path[len(path) // 2]
            dl.append(("text", mid[0] + 6, mid[1] - 7, 14, str(r["label"])[:24],
                       "#37474F", False, False, "start"))
        if r.get("badge"):
            p = path[-1]
            dl.append(("text", p[0] + 9, p[1] - 9, 14, str(r["badge"])[:4], st["color"], True, True, "start"))
        if r.get("direction") == "undirected":
            p = path[-1]
            dl.append(("text", p[0] + 6, p[1] + 16, 14, "dir?", "#95A5A6", False, False, "start"))
    legend_swatch(model, dl)
    dl.append(("text", MARGIN, CANVAS["h"] - 16, 14,
               "Every node and edge carries a locator and a verbatim quote in content_map.json; "
               "all text is editable <text>.", "#78909C", False, False, "start"))
    return dl


# ---------------------------------------------------------------------- SVG
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def svg(model):
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
         'font-family="%s">' % (CANVAS["w"], CANVAS["h"], CANVAS["w"], CANVAS["h"], esc(FONT_FAMILY)),
         '<rect id="bg" x="0" y="0" width="%d" height="%d" fill="#FFFFFF"/>' % (CANVAS["w"], CANVAS["h"])]
    y_title = MARGIN + 26
    o.append('<g id="layer-title">')
    o.append('<text x="%.1f" y="%.1f" font-size="25" font-weight="bold" text-anchor="middle" fill="#1B2A33">%s</text>'
             % (CANVAS["w"] / 2.0, y_title, esc(model.get("title") or "Mechanism figure")))
    if model.get("subtitle"):
        o.append('<text x="%.1f" y="%.1f" font-size="14" text-anchor="middle" fill="#5D6D7E">%s</text>'
                 % (CANVAS["w"] / 2.0, y_title + 26, esc(str(model["subtitle"])[:150])))
    o.append("</g>")

    o.append('<g id="layer-compartments">')
    for c in model.get("compartments", []):
        if "y" not in c:
            continue
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="#FAFBFC" '
                 'stroke="#D5DBDF" stroke-width="1"/>' % (c["x"], c["y"], c["w"], c["h"]))
        o.append('<text x="%.1f" y="%.1f" font-size="15" font-weight="bold" fill="#37474F">%s</text>'
                 % (c["x"] + 12, c["y"] + 24, esc(c["label"])))
        if c.get("kind") == "membrane":
            my = c["y"] + c["h"] / 2.0
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#90A4AE" stroke-width="2"/>'
                     % (c["x"] + 12, my - 6, c["x"] + c["w"] - 12, my - 6))
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#90A4AE" stroke-width="2"/>'
                     % (c["x"] + 12, my + 6, c["x"] + c["w"] - 12, my + 6))
    o.append("</g>")

    o.append('<g id="layer-entities">')
    for e in model["entities"]:
        bx = e.get("box")
        if not bx:
            continue
        o.append('<g id="ent-%s" data-entity-type="%s" data-compartment="%s" data-italic="%s" '
                 'data-locator="%s" data-quote="%s" data-quote-status="%s">'
                 % (esc(e["id"]), esc(e["type"]), esc(e["compartment"]),
                    "true" if e["italic"] else "false", esc(e.get("locator") or ""),
                    esc((e.get("quote") or "")[:300]), esc(e.get("status") or "none")))
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="9" fill="%s" stroke="%s" '
                 'stroke-width="%.1f"/>'
                 % (bx["x"], bx["y"], bx["w"], bx["h"],
                    ENTITY_FILL.get(e["type"], ENTITY_FILL["unspecified"]),
                    "#8A5A2B" if e["type"] == "gene" else "#546E7A",
                    2.4 if e["type"] == "complex" else 1.3))
        lines = wrap(e["name"], 15, bx["w"] - 16)
        base = bx["cy"] - (len(lines) - 1) * 8 + (5 if e.get("sublabel") else 0)
        for i, ln in enumerate(lines):
            o.append('<text x="%.1f" y="%.1f" font-size="15" text-anchor="middle" fill="#102A33"%s>%s</text>'
                     % (bx["cx"], base + i * 17,
                        ' font-style="italic"' if e["italic"] else "", esc(ln)))
        if e.get("sublabel"):
            o.append('<text x="%.1f" y="%.1f" font-size="14" text-anchor="middle" fill="#546E7A">%s</text>'
                     % (bx["cx"], bx["y"] + bx["h"] - 7, esc(str(e["sublabel"])[:26])))
        o.append("</g>")
    o.append("</g>")

    o.append('<g id="layer-edges">')
    for r in model.get("relations", []):
        if not r.get("path"):
            continue
        st = EDGE_STYLE.get(r["type"], EDGE_STYLE["unspecified"])
        dash = ' stroke-dasharray="%s"' % st["dash"] if st["dash"] else ""
        o.append('<g id="rel-%s" data-relation-type="%s" data-from="%s" data-to="%s" '
                 'data-direction="%s" data-evidence="%s" data-locator="%s" data-quote="%s" '
                 'data-quote-status="%s">'
                 % (esc(r["id"]), esc(r["type"]), esc(r["from"]), esc(r["to"]),
                    esc(r.get("direction", "forward")), esc(r.get("strength", "stated")),
                    esc(r.get("locator") or ""), esc((r.get("quote") or "")[:300]),
                    esc(r.get("status") or "none")))
        pts = " ".join("%.1f,%.1f" % (p[0], p[1]) for p in r["path"])
        o.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%.1f"%s '
                 'stroke-linejoin="round"/>' % (pts, st["color"], st["width"], dash))
        for it in marker(r["path"], st, r):
            o.append(_svg_item(it))
        o.append("</g>")
    o.append("</g>")

    o.append('<g id="layer-labels">')
    for r in model.get("relations", []):
        if not r.get("path"):
            continue
        st = EDGE_STYLE.get(r["type"], EDGE_STYLE["unspecified"])
        if r.get("label"):
            mid = r["path"][len(r["path"]) // 2]
            o.append('<text x="%.1f" y="%.1f" font-size="14" fill="#37474F">%s</text>'
                     % (mid[0] + 6, mid[1] - 7, esc(str(r["label"])[:24])))
        if r.get("badge"):
            p = r["path"][-1]
            o.append('<text x="%.1f" y="%.1f" font-size="14" font-weight="bold" fill="%s">%s</text>'
                     % (p[0] + 9, p[1] - 9, st["color"], esc(str(r["badge"])[:4])))
        if r.get("direction") == "undirected":
            p = r["path"][-1]
            o.append('<text x="%.1f" y="%.1f" font-size="14" fill="#95A5A6">dir?</text>'
                     % (p[0] + 6, p[1] + 16))
    o.append("</g>")

    top, rows = legend_geom(model)
    o.append('<g id="layer-legend">')
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#CFD8DC" stroke-width="1"/>'
             % (MARGIN, top, CANVAS["w"] - MARGIN, top))
    o.append('<text x="%d" y="%.1f" font-size="14" font-weight="bold" fill="#37474F">%s</text>'
             % (MARGIN, top + 22, esc("Legend (generated from what the canvas encodes)")))
    for item in rows:
        r, x, y = item["row"], item["x"], item["y"]
        if r["channel"] == "color":
            o.append('<rect x="%.1f" y="%.1f" width="18" height="14" rx="3" fill="%s" stroke="#546E7A" '
                     'stroke-width="1"/>' % (x, y - 12, ENTITY_FILL.get(r["key"], "#ECEFF1")))
        else:
            st = EDGE_STYLE.get(r["key"], EDGE_STYLE["unspecified"])
            dash = ' stroke-dasharray="%s"' % st["dash"] if st["dash"] else ""
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f"%s/>'
                     % (x, y - 5, x + 22, y - 5, st["color"], st["width"], dash))
            for it in marker([(x + 2, y - 5), (x + 22, y - 5)], st, {})[:1]:
                o.append(_svg_item(it))
        o.append('<text x="%.1f" y="%.1f" font-size="14" fill="#37474F">%s</text>'
                 % (x + 28, y, esc(item["label"])))
    o.append("</g>")
    o.append('<g id="layer-notes">')
    o.append('<text x="%d" y="%d" font-size="14" fill="#78909C">%s</text>'
             % (MARGIN, CANVAS["h"] - 16,
                esc("Every node and edge carries a locator and a verbatim quote in content_map.json; "
                    "all text is editable <text>.")))
    o.append("</g>")
    o.append("</svg>")
    return "\n".join(o) + "\n"


def _svg_item(it):
    if it[0] == "rect":
        _, x, y, w, h, fill, stroke, sw, rx = it
        return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%s" fill="%s" stroke="%s" '
                'stroke-width="%.1f"/>' % (x, y, w, h, rx, fill or "none", stroke or "none", sw or 0))
    if it[0] == "line":
        _, x1, y1, x2, y2, color, w, dash = it
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f"%s/>'
                % (x1, y1, x2, y2, color, w, d))
    _, pts, fill, stroke, sw = it
    p = " ".join("%.1f,%.1f" % (a, b) for a, b in pts)
    return ('<polygon points="%s" fill="%s" stroke="%s" stroke-width="%.1f"/>'
            % (p, fill or "none", stroke or "none", sw or 0))


# ------------------------------------------------------------------- probes
def _pairs(v):
    """Accept {("ch","key")} or ["ch:key"] (figure_model.json round-trip)."""
    out = set()
    for x in v or []:
        if isinstance(x, (list, tuple)) and len(x) == 2:
            out.add((str(x[0]), str(x[1])))
        elif isinstance(x, str) and ":" in x:
            a, b = x.split(":", 1)
            out.add((a, b))
    return out


def probe(model, svg_text):
    fails, checks = [], {}
    try:
        root = ET.fromstring(svg_text)
        w = int(float(str(root.get("width", "0")).replace("px", "")))
        h = int(float(str(root.get("height", "0")).replace("px", "")))
        checks["svg_xml"] = True
    except Exception as exc:
        checks["svg_xml"] = False
        fails.append("svg not parseable: %s" % exc)
        w = h = 0
    checks["canvas"] = {"width": w, "height": h, "ok": (w == CANVAS["w"] and h == CANVAS["h"])}
    if not checks["canvas"]["ok"]:
        fails.append("canvas is %sx%s, expected %dx%d" % (w, h, CANVAS["w"], CANVAS["h"]))

    sizes = [int(float(x)) for x in re.findall(r'font-size="([0-9.]+)"', svg_text)]
    genes = [e for e in model["entities"] if e["italic"]]
    ital = svg_text.count('font-style="italic"')
    checks["font_style"] = {"min_font": min(sizes) if sizes else 0,
                            "min_font_ok": bool(sizes) and min(sizes) >= MIN_FONT,
                            "family": FONT_FAMILY, "italic_labels": ital, "genes": len(genes)}
    if sizes and min(sizes) < MIN_FONT:
        fails.append("font below %dpx" % MIN_FONT)

    used = sorted({r["type"] for r in model["relations"]})
    sig = {t: (EDGE_STYLE.get(t, {}).get("marker"), EDGE_STYLE.get(t, {}).get("dash"),
               EDGE_STYLE.get(t, {}).get("width")) for t in used}
    act, inh = sig.get("activation", ("a",)), sig.get("inhibition", ("b",))
    checks["markers"] = {"types_used": used, "signatures": {k: [str(x) for x in v] for k, v in sig.items()},
                         "distinct": len(set(sig.values())) == len(sig),
                         "activation_vs_inhibition": (act[0] != inh[0]) if (act and inh) else None}
    if not checks["markers"]["distinct"]:
        fails.append("relation encodings collide")
    checks["gene_italics"] = ital >= len(genes)
    if genes and ital < len(genes):
        fails.append("gene labels not italicised (%d < %d)" % (ital, len(genes)))

    lanes = {c["id"]: c for c in model.get("compartments", []) if "y" in c}
    comp_of = {e["id"]: e["compartment"] for e in model["entities"]}
    inside, bad, straddle = 0, [], 0
    for e in model["entities"]:
        bx, lane = e.get("box"), lanes.get(e["compartment"])
        if not (bx and lane):
            continue
        ok = (bx["y"] >= lane["y"] - 1) and (bx["y"] + bx["h"] <= lane["y"] + lane["h"] + 1)
        if lane.get("kind") == "membrane":
            mid = lane["y"] + lane["h"] / 2.0
            ok = ok and (bx["y"] < mid < bx["y"] + bx["h"])
            straddle += 1
        inside += 1 if ok else 0
        if not ok:
            bad.append(e["id"])
    checks["compartment_containment"] = {"entities": len([e for e in model["entities"] if e.get("box")]),
                                         "inside": inside, "failures": bad,
                                         "membrane_straddling": straddle}
    if bad:
        fails.append("entities outside their lane: %s" % ", ".join(bad[:4]))

    cross_bad, checked = [], 0
    for r in model.get("relations", []):
        a, b = lanes.get(comp_of.get(r["from"], "")), lanes.get(comp_of.get(r["to"], ""))
        if not (a and b) or a is b or not r.get("path"):
            continue
        checked += 1
        lo, hi = min(a["y"] + a["h"], b["y"] + b["h"]), max(a["y"], b["y"])
        ys = [p[1] for p in r["path"]]
        if not (min(ys) <= lo and max(ys) >= hi):
            cross_bad.append(r["id"])
    checks["cross_lane_edges"] = {"checked": checked, "crossing_failures": cross_bad, "ok": not cross_bad}
    if cross_bad:
        fails.append("cross-compartment edges do not cross the boundary: %s" % ", ".join(cross_bad[:4]))

    used_keys = _pairs(model.get("legend_used"))
    declared_keys = _pairs(model.get("legend_declared"))
    rows = model.get("legend_rows") or []
    row_keys = {(r.get("channel"), r.get("key")) for r in rows}
    unsourced = sorted("%s:%s" % k for k in used_keys - declared_keys)
    orphan = sorted("%s:%s" % k for k in declared_keys - used_keys)
    checks["legend_consistency"] = {"items": len(rows), "encodings_used": len(used_keys),
                                    "declared_by_agent": len(declared_keys),
                                    "one_item_per_encoding": len(rows) == len(row_keys),
                                    "unsourced": unsourced, "orphan": orphan,
                                    "ok": (not orphan) and len(rows) == len(row_keys)}
    if orphan:
        fails.append("legend entries not on canvas: %s" % ", ".join(orphan[:4]))
    if unsourced:
        checks.setdefault("notes", []).append(
            "encodings without an agent-sourced legend entry: %s" % ", ".join(unsourced[:6]))

    over = [e["id"] for e in model["entities"] if e.get("box") and
            max(tw(l, 15) for l in wrap(e["name"], 15, e["box"]["w"] - 16)) > e["box"]["w"] - 6]
    boxes = [(e["id"], e["box"]) for e in model["entities"] if e.get("box")]
    overlaps = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            if (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and
                    a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]):
                overlaps += 1
    checks["overflow"] = {"text_overflows": over, "box_overlaps": overlaps, "ok": not over and not overlaps}
    if over:
        fails.append("label overflow: %s" % ", ".join(over[:4]))
    if overlaps:
        fails.append("%d overlapping entity boxes" % overlaps)

    checks["layers"] = {k: ('id="%s"' % k) in svg_text for k in LAYER_IDS}
    checks["text_nodes"] = svg_text.count("<text")
    checks["failures"] = fails
    checks["pass"] = not fails
    return checks
