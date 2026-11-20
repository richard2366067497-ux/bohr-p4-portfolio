"""layout.py - the single layout authority for the graphical abstract.

Input: a draft (what the agent decided to say) plus a spec (canvas, reading
direction, minimum font size, palette). Output: a display list of rectangles,
lines, polygons and text runs, plus the element table, the encoding table and
the legend that content_map.json is built from.

Everything is derived from the canvas; there are no magic coordinates, no
random numbers and no timestamps, so the same draft always produces the same
bytes. Coordinates and font sizes are in PostScript points.
"""
import math

ROLE_COLOR = {"problem": "#D55E00", "method": "#0072B2",
              "results": "#009E73", "implication": "#CC79A7", "other": "#5A5A5A"}
ROLE_TAG = {"problem": "PROBLEM", "method": "METHOD", "results": "KEY RESULTS",
            "implication": "TAKEAWAY", "other": "NOTE"}
ROLE_ALIAS = (
    ("problem", ("problem", "question", "gap", "aim", "motivation", "challenge", "unknown", "issue")),
    ("method", ("method", "approach", "pipeline", "strategy", "experiment", "workflow", "design", "route")),
    ("results", ("result", "finding", "outcome", "evidence", "data", "effect", "measurement", "observation")),
    ("implication", ("implication", "conclusion", "significance", "impact", "outlook", "takeaway", "meaning")),
)
LAYERS = ["background", "panels", "marks", "arrows", "labels", "legend", "footer"]
LAYER_INDEX = {n: i for i, n in enumerate(LAYERS)}
# Okabe-Ito, colour-vision-deficiency aware; also used for categorical encoding.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7",
           "#56B4E9", "#D55E00", "#F0E442", "#666666"]
CHANNELS = ("color", "length", "area", "brightness", "shape")

def strip(s):
    return " ".join(str(s if s is not None else "").split())

def norm_role(r):
    r = str(r or "").lower()
    for canon, names in ROLE_ALIAS:
        if any(n in r for n in names):
            return canon
    return "other"

def _wide(ch):
    return ord(ch) > 0x2E7F

def cw(ch, size):
    if _wide(ch):
        return size
    if ch in "ilj.,;:'!|()`[]":
        return size * 0.30
    if ch in "mwMW":
        return size * 0.86
    if ch.isupper():
        return size * 0.66
    if ch.isdigit():
        return size * 0.56
    return size * 0.52

def tw(s, size):
    return sum(cw(c, size) for c in str(s or ""))

def _tokens(s):
    out, buf = [], ""
    for ch in s:
        if ch.isspace():
            if buf:
                out.append(buf)
                buf = ""
            out.append(" ")
        elif _wide(ch):
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out

def wrap(s, size, width, maxlines=0):
    s = strip(s)
    if not s or width <= size * 0.6:
        return []
    lines, cur = [], ""
    for tk in _tokens(s):
        cand = cur + tk
        if not cur.strip() or tw(cand.strip(), size) <= width:
            cur = cand
        else:
            lines.append(cur.strip())
            cur = "" if tk == " " else tk
    if cur.strip():
        lines.append(cur.strip())
    lines = [ln for ln in lines if ln]
    if maxlines and len(lines) > maxlines:
        keep = lines[:maxlines]
        keep[-1] = keep[-1].rstrip(" ,.;:-") + "…"
        return keep
    return lines

def lines_h(lines, size, lead=1.30):
    return len(lines) * size * lead

def hex_rgb(h):
    h = str(h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except Exception:
        return (0.0, 0.0, 0.0)

def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def luminance(h):
    r, g, b = hex_rgb(h)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

def mix(h, keep):
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(255 * (1 - keep) + c * 255 * keep))) for c in hex_rgb(h))

def shade(h, f=0.70):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c * 255 * f))) for c in hex_rgb(h))

def pick_colours(n):
    """Spread categories across luminance as well as hue, so greyscale keeps them apart."""
    pool = sorted(PALETTE, key=luminance)
    if n <= 0:
        return []
    if n == 1:
        return [pool[len(pool) // 2]]
    step = (len(pool) - 1) / float(n - 1)
    return [pool[int(round(i * step))] for i in range(n)]

def _ups(h):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c * 255))) for c in hex_rgb(h))

def T(x, y, s, size, weight="normal", color="#1A1A1A", anchor="start", oid=None, layer="labels"):
    return {"op": "text", "x": float(x), "y": float(y), "text": str(s), "size": float(size),
            "weight": weight, "color": color, "anchor": anchor, "id": oid, "layer": layer}

def R(x, y, w, h, fill=None, stroke=None, sw=1.0, rx=0.0, oid=None, layer="panels", dash=None):
    return {"op": "rect", "x": float(x), "y": float(y), "w": float(w), "h": float(h),
            "fill": fill, "stroke": stroke, "sw": float(sw), "rx": float(rx), "id": oid,
            "layer": layer, "dash": dash}

def L(x1, y1, x2, y2, color="#6E6E6E", sw=1.4, oid=None, layer="arrows"):
    return {"op": "line", "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2),
            "stroke": color, "sw": float(sw), "id": oid, "layer": layer}

def P(pts, fill="#6E6E6E", oid=None, layer="arrows"):
    return {"op": "poly", "pts": [(float(a), float(b)) for a, b in pts], "fill": fill,
            "id": oid, "layer": layer}

def _sizes(min_pt):
    """Type ladder in points. Nothing is allowed below min_pt."""
    base = {"title": 18.0, "subtitle": 9.4, "heading": 9.0, "claim": 7.9,
            "label": 8.4, "detail": 7.6, "value": 13.0, "legend": 7.3,
            "role": 6.6, "footer": 6.6, "small": 6.8}
    return {k: max(float(min_pt), v) for k, v in base.items()}

def _text_block(it, width, sz):
    lab = strip(it.get("label"))
    det = strip(it.get("detail") or it.get("note"))
    ops, y = [], 0.0
    if lab:
        for ln in wrap(lab, sz["label"], width, 2):
            y += sz["label"] * 1.22
            ops.append(T(0, y, ln, sz["label"], "bold", "#141414"))
        y += 1.2
    for ln in wrap(det, sz["detail"], width, 6):
        y += sz["detail"] * 1.28
        ops.append(T(0, y, ln, sz["detail"], "normal", "#3A3A3A"))
    return ops, y + 2.0

def _value_block(it, width, sz):
    val = strip(it.get("value") or it.get("label"))
    det = strip(it.get("detail") or it.get("note"))
    vs, y = sz["value"], 0.0
    while tw(val, vs) > width and vs > sz["detail"]:
        vs -= 0.6
    lines = wrap(val, vs, width, 2)
    ops = []
    for ln in lines:
        y += vs * 1.14
        ops.append(T(0, y, ln, vs, "bold", "#141414"))
    for ln in wrap(det, sz["detail"], width, 3):
        y += sz["detail"] * 1.28
        ops.append(T(0, y, ln, sz["detail"], "normal", "#3A3A3A"))
    return ops, y + 3.0

def _enc_block(enc, width, sz, panel_accent):
    """Draw the visual channel. Returns (ops, height, marks)."""
    chan = str(enc.get("channel") or "color").lower()
    cats = [c for c in (enc.get("categories") or []) if isinstance(c, dict)]
    unit = strip(enc.get("unit"))
    ops, marks, y = [], [], 0.0
    head = "Encoding: " + (strip(enc.get("meaning")) or chan)
    if unit:
        head += " (" + unit + ")"
    for ln in wrap(head, sz["small"], width, 2):
        y += sz["small"] * 1.30
        ops.append(T(0, y, ln, sz["small"], "normal", "#4A4A4A"))
    y += 2.0
    if not cats:
        for ln in wrap("not reported in the supplied material", sz["small"], width, 1):
            y += sz["small"] * 1.30
            ops.append(T(0, y, ln, sz["small"], "normal", "#8A8A8A"))
        return ops, y + 2.0, marks
    nums = [c.get("num") for c in cats if isinstance(c.get("num"), (int, float))]
    top = max(nums) if nums else 0.0
    if chan in ("length", "area"):
        row = max(sz["small"] * 1.85, 9.6)
        lab_w = min(width * 0.42, max(tw(strip(c.get("label")), sz["small"]) for c in cats) + 4)
        for i, c in enumerate(cats):
            lab = strip(c.get("label"))
            rx, ry = 0.0, y + i * row
            ops.append(T(rx, ry + row * 0.66, lab, sz["small"], "normal", "#242424"))
            colour = c.get("color") or PALETTE[i % len(PALETTE)]
            track_w = max(10.0, width - lab_w - sz["small"] * 3.0)
            ops.append(R(lab_w, ry + row * 0.20, track_w, row * 0.56, "#F1F1F1", "#D8D8D8", 0.6, 1.5,
                         oid=None, layer="marks"))
            num = c.get("num")
            frac = (float(num) / top) if (top and isinstance(num, (int, float))) else 0.0
            frac = max(0.0, min(1.0, frac))
            if chan == "area":
                side = max(3.0, math.sqrt(frac) * row * 0.56 * 2.2)
                ops.append(R(lab_w, ry + row * 0.20, side, min(row * 0.56, side), colour, None, 0,
                             1.0, oid="%s-m%d" % (enc.get("id"), i + 1), layer="marks"))
            else:
                ops.append(R(lab_w, ry + row * 0.20, max(1.5, track_w * frac), row * 0.56, colour,
                             None, 0, 1.5, oid="%s-m%d" % (enc.get("id"), i + 1), layer="marks"))
            val = strip(c.get("value"))
            if val:
                ops.append(T(width, ry + row * 0.66, val, sz["small"], "bold", shade(colour, 0.75),
                             "end"))
            marks.append({"mark_id": "%s-m%d" % (enc.get("id"), i + 1), "label": lab,
                          "value": val, "color": colour, "channel": chan})
        y += row * len(cats)
    else:
        chip = max(sz["small"] * 1.55, 7.0)
        pad = sz["small"] * 0.55
        cx, cy = 0.0, y
        for i, c in enumerate(cats):
            lab = strip(c.get("label"))
            txt = lab + ((" " + strip(c.get("value"))) if strip(c.get("value")) else "")
            need = tw(txt, sz["small"]) + chip + 4 * pad
            if cx > 0 and cx + need > width:
                cx, cy = 0.0, cy + chip + pad
            base = c.get("color") or PALETTE[i % len(PALETTE)]
            colour = _ups(mix(shade(base, 0.85), 0.55)) if chan == "brightness" else base
            ops.append(R(cx, cy + 1.0, chip, chip, colour,
                         "#9E9E9E" if chan == "shape" else None, 1.4, 1.5,
                         oid="%s-m%d" % (enc.get("id"), i + 1), layer="marks"))
            ops.append(T(cx + chip + pad, cy + chip * 0.92, txt, sz["small"], "normal", "#242424"))
            marks.append({"mark_id": "%s-m%d" % (enc.get("id"), i + 1), "label": lab,
                          "value": strip(c.get("value")), "color": colour, "channel": chan})
            cx += need + pad * 2
        y = cy + chip + 2.0
    return ops, y + 3.0, marks

def _body(panel, width, avail, sz, encs):
    """Fit claim + items + encoding into avail height, shrinking before dropping."""
    claim = strip(panel.get("claim"))
    items = [i for i in (panel.get("items") or []) if isinstance(i, dict)]
    enc = encs.get(str(panel.get("id")))
    for scale in (1.0, 0.94, 0.88, 0.82, 0.76):
        s = {k: max(sz["min"], v * scale) for k, v in sz.items()}
        ops, y = [], 0.0
        if claim:
            cl = wrap(claim, s["claim"], width, 3)
            for ln in cl:
                y += s["claim"] * 1.32
                ops.append(T(0, y, ln, s["claim"], "bold", "#2B2B2B"))
            y += 2.5
        built = []
        for it in items:
            kind = str(it.get("kind") or "text").lower()
            if kind == "value":
                iops, ih = _value_block(it, width, s)
            elif kind == "chart" and enc is not None:
                iops, ih, _ = _enc_block(enc, width, s, None)
            else:
                iops, ih = _text_block(it, width, s)
            built.append((it, iops, ih))
            y += ih + s["detail"] * 0.55
        extra_marks = []
        if enc is not None and not any(str(i.get("kind")).lower() == "chart" for i in items):
            eops, eh, emarks = _enc_block(enc, width, s, None)
            y += s["detail"] * 0.55 + eh
            extra_marks = emarks
            built.append(({"id": enc.get("id"), "kind": "encoding"}, eops, eh))
        if y <= avail:
            return ops, built, extra_marks, y, scale, []
    # still too tall at the smallest step: drop items from the end
    dropped = []
    while len(built) > 1:
        it = built.pop()
        dropped.append(str(it[0].get("id")))
        y = sum(b[2] + s["detail"] * 0.55 for b in built) + (3.0 if claim else 0.0)
        if claim:
            y += lines_h(wrap(claim, s["claim"], width, 3), s["claim"], 1.32)
        if y <= avail:
            break
    return ops, built, extra_marks, y, 0.76, dropped

def compose(draft, spec):
    cv = spec.get("canvas") or {}
    W = float(cv.get("w_pt") or 510.0)
    H = float(cv.get("h_pt") or 317.0)
    min_pt = float((spec.get("style") or {}).get("min_font_pt") or 7.0)
    sz = _sizes(min_pt)
    sz["min"] = min_pt
    sc = max(0.86, min(1.22, min(W / 510.0, H / 317.0)))
    sz = {k: (v if k == "min" else round(v * sc, 2)) for k, v in sz.items()}
    sz = {k: (v if k == "min" else max(min_pt, v)) for k, v in sz.items()}
    M = max(9.0, min(0.034 * W, 0.05 * H))
    accent = (spec.get("style") or {}).get("accent") or "#0072B2"

    title = strip(draft.get("title")) or "Graphical abstract"
    subtitle = strip(draft.get("subtitle"))
    caption = strip(draft.get("caption"))
    raw_panels = [p for p in (draft.get("panels") or []) if isinstance(p, dict)]
    ops = [R(0, 0, W, H, "#FFFFFF", None, 0, 0, "canvas", "background")]
    els, dropped, warnings, sizes_used = [], [], [], []

    # -- title band
    ts = sz["title"]
    while tw(title, ts) > W - 2 * M and ts > sz["detail"]:
        ts -= 0.5
    y = M + ts * 0.92
    for ln in wrap(title, ts, W - 2 * M, 2):
        ops.append(T(M, y, ln, ts, "bold", "#101010", "start", "title", "labels"))
        sizes_used.append(ts)
        y += ts * 1.16
    y += 1.0
    for ln in wrap(subtitle, sz["subtitle"], W - 2 * M, 2):
        ops.append(T(M, y, ln, sz["subtitle"], "normal", "#3F3F3F", "start", "subtitle", "labels"))
        sizes_used.append(sz["subtitle"])
        y += sz["subtitle"] * 1.30

    # -- legend band height (computed before panels so panels get the rest)
    legend = []
    for i, e in enumerate([x for x in (draft.get("legend") or []) if isinstance(x, dict)]):
        legend.append({"label": strip(e.get("label")), "meaning": strip(e.get("meaning")),
                       "color": e.get("color") or pick_colours(1)[0]})
    encs = {}
    for i, e in enumerate([x for x in (draft.get("encodings") or []) if isinstance(x, dict)]):
        eid = str(e.get("id") or "enc%d" % (i + 1))
        e = dict(e)
        e["id"] = eid
        e.setdefault("channel", "color")
        cats = [c for c in (e.get("categories") or []) if isinstance(c, dict)]
        chosen = pick_colours(len(cats))
        for j, c in enumerate(cats):
            if not c.get("color"):
                c["color"] = chosen[j]
        if e.get("panel"):
            encs[str(e.get("panel"))] = e
    seen = {x["label"] for x in legend if x["label"]}
    for e in encs.values():
        for j, c in enumerate([c for c in (e.get("categories") or []) if isinstance(c, dict)]):
            lab = strip(c.get("label"))
            if lab and lab not in seen:
                legend.append({"label": lab, "meaning": strip(e.get("meaning")), "color": c.get("color")})
                seen.add(lab)
    if not legend:
        for p in raw_panels:
            role = norm_role(p.get("role") or p.get("heading"))
            if role != "other":
                legend.append({"label": ROLE_TAG[role].title(), "meaning": strip(p.get("heading")) or role,
                               "color": ROLE_COLOR[role]})
    ltop = H - M
    lsz = sz["legend"]
    lrows, lx, lh = 1, M, lsz * 2.15
    for item in legend:
        need = 10 + lsz * 0.55 + tw(item["label"], lsz) + tw(item["meaning"], lsz) * 0.0 + 14
        if lx + need > W - M and lx > M:
            lrows += 1
            lx = M
        lx += need
    legend_top = ltop - lrows * lh - 4.0
    cap_lines = wrap(caption, sz["footer"], W - 2 * M, 2)
    footer_h = lines_h(cap_lines, sz["footer"], 1.32) + sz["footer"] * 1.9 + 3.0
    ptop = y + max(6.0, 0.022 * H)
    pbottom = legend_top - max(5.0, 0.016 * H) - footer_h
    if pbottom - ptop < 0.28 * H:                      # keep a usable panel band
        ptop = max(ptop, M + 2 * ts)
        pbottom = max(ptop + 0.30 * H, legend_top - footer_h)
    n = max(1, len(raw_panels))
    gap = max(11.0, 0.036 * W)
    direction = "row" if (W / H >= 1.12 and n <= 4) else ("row" if W / H >= 1.12 else "column")
    if direction == "row":
        cols, rows = n, 1
    else:
        cols, rows = (2 if n >= 4 and W / H >= 0.85 else 1), (2 if n >= 4 and W / H >= 0.85 else n)
    pw = (W - 2 * M - (cols - 1) * gap) / cols
    ph = (pbottom - ptop - (rows - 1) * gap) / rows
    geom = []
    for i, p in enumerate(raw_panels):
        r_, c_ = divmod(i, cols)
        geom.append({"i": i, "p": p, "id": str(p.get("id") or "P%d" % (i + 1)),
                     "role": norm_role(p.get("role") or p.get("heading")),
                     "x": M + c_ * (pw + gap), "y": ptop + r_ * (ph + gap), "w": pw, "h": ph})

    # -- panels
    for g in geom:
        p, role, x0, y0, w, h = g["p"], g["role"], g["x"], g["y"], g["w"], g["h"]
        col = ROLE_COLOR[role]
        pid = g["id"]
        head_h = max(sz["heading"] * 2.3, 15.0)
        ops.append(R(x0, y0, w, h, "#FDFDFD", "#CFCFCF", 0.8, 5, pid + "-card"))
        ops.append(R(x0, y0, w, head_h, col, None, 0, 5, pid + "-header"))
        ops.append(R(x0, y0 + head_h - 6, w, 6, col, None, 0, 0, pid + "-headerbase"))
        ops.append(T(x0 + 6, y0 + head_h * 0.70, str(g["i"] + 1), sz["role"], "bold", "#FFFFFF",
                     "start", pid + "-order"))
        heading = strip(p.get("heading")) or ROLE_TAG[role].title()
        hx, hts = x0 + 6 + sz["role"] * 1.9, sz["heading"]
        tag_w = tw(ROLE_TAG[role], max(sz["role"], 5.6)) + 8 if role != "other" else 4
        while tw(heading, hts) > w - (hx - x0) - tag_w and hts > sz["detail"]:
            hts -= 0.4
        ops.append(T(hx, y0 + head_h * 0.70, heading, hts, "bold", "#FFFFFF", "start", pid + "-heading"))
        sizes_used.append(hts)
        if role != "other":
            ops.append(T(x0 + w - 5, y0 + head_h * 0.70, ROLE_TAG[role], max(sz["role"], 5.6),
                         "normal", "#FFFFFF", "end", pid + "-roletag"))
        body_w = w - 14
        avail = h - head_h - 10
        claim_ops, built, emarks, used, scale, lost = _body(p, body_w, avail, sz, encs)
        if lost:
            dropped.append({"panel": pid, "elements": lost, "reason": "vertical overflow at smallest type step"})
            warnings.append("panel %s: %d element(s) dropped for overflow" % (pid, len(lost)))
        claim_h = max([o["y"] for o in claim_ops] or [0.0])
        cy = y0 + head_h + 5
        for o in claim_ops:
            o = dict(o, x=o["x"] + x0 + 7, y=o["y"] + cy)
            ops.append(o)
            sizes_used.append(o["size"])
        cy += claim_h + (3.0 if claim_ops else 0.0)
        for it, iops, ih in built:
            eid = str(it.get("id") or "%s-I%d" % (pid, len(els) + 1))
            top = cy
            for o in iops:
                o = dict(o, x=o["x"] + x0 + 7, y=o["y"] + top)
                if o["op"] == "text":
                    o["id"] = eid if not o.get("id") else o.get("id")
                    sizes_used.append(o["size"])
                ops.append(o)
            text = " | ".join([strip(it.get("label")), strip(it.get("value")), strip(it.get("detail"))]).strip(" |")
            if str(it.get("kind")).lower() == "encoding":
                text = "encoding: " + strip((encs.get(pid) or {}).get("meaning"))
            els.append({"id": eid, "panel": pid, "role": role, "kind": str(it.get("kind") or "text"),
                        "text": text, "bbox": [round(x0 + 7, 1), round(top, 1), round(body_w, 1), round(ih, 1)],
                        "encoding": str(it.get("id")) if str(it.get("kind")).lower() == "encoding" else None})
            cy += ih + sz["detail"] * 0.55
        flow = strip(p.get("flow"))
        if flow and cy + sz["small"] * 2.1 < y0 + h - 2:
            label = wrap("<- " + flow, sz["small"], body_w, 1)
            if label:
                ops.append(T(x0 + 7, y0 + h - 6.0, label[0], sz["small"], "normal", shade(col, 0.85),
                             "start", pid + "-flow"))
                sizes_used.append(sz["small"])
                warnings.append("%s: relation word repeated in the card ('%s')" % (pid, flow))
        if not built:
            ops.append(R(x0 + 7, cy, body_w, max(12.0, h - (cy - y0) - 8), None, "#BDBDBD", 0.8, 3,
                         pid + "-placeholder", dash="3 2"))
            ops.append(T(x0 + 11, cy + 12, "no verified evidence for this panel", sz["small"],
                         "normal", "#8A8A8A"))
            dropped.append({"panel": pid, "elements": [], "reason": "no item survived evidence checks"})
        g["elements"] = [e["id"] for e in els if e["panel"] == pid]
        g["scale"] = scale

    # -- arrows between consecutive panels, labelled with the downstream flow word
    for a, b in zip(geom, geom[1:]):
        if abs(a["y"] - b["y"]) < 1.0 and b["x"] > a["x"]:
            mid = a["y"] + a["h"] / 2
            x1, x2 = a["x"] + a["w"] + 1.5, b["x"] - 2.0
            ops += [L(x1, mid, x2, mid, "#5A5A5A", 1.7, "flow-%d" % (a["i"] + 1)),
                    P([(x2, mid), (x2 - 5.4, mid - 3.4), (x2 - 5.4, mid + 3.4)], "#5A5A5A",
                      "flow-%d-head" % (a["i"] + 1))]
        elif b["y"] > a["y"]:
            cx = a["x"] + a["w"] / 2
            y1, y2 = a["y"] + a["h"] + 1.5, b["y"] - 2.0
            ops += [L(cx, y1, cx, y2, "#6E6E6E", 1.5, "flow-%d" % (a["i"] + 1)),
                    P([(cx, y2), (cx - 3.0, y2 - 4.6), (cx + 3.0, y2 - 4.6)], "#6E6E6E",
                      "flow-%d-head" % (a["i"] + 1))]

    # -- legend band
    ops.append(L(M, legend_top + 3.0, W - M, legend_top + 3.0, "#DCDCDC", 0.8, "legend-rule", "legend"))
    lx, ly, idx = M, legend_top + 9.0, 0
    for item in legend:
        txt = item["label"] + ((" — " + item["meaning"]) if item["meaning"] else "")
        need = 9 + sz["legend"] * 1.35 + tw(txt, lsz) + 12
        if lx + need > W - M and lx > M:
            lx, ly = M, ly + lh
        idx += 1
        ops.append(R(lx, ly + 1.0, sz["legend"] * 1.35, sz["legend"] * 1.05, item["color"] or "#888888",
                     None, 0, 1.5, "legend-%d" % idx, "legend"))
        ops.append(T(lx + sz["legend"] * 1.35 + 5, ly + sz["legend"] * 1.05, txt, lsz, "normal",
                     "#2E2E2E", "start", "legend-%d-label" % idx, "legend"))
        sizes_used.append(lsz)
        lx += need

    # -- footer
    fy = H - M - sz["footer"] * 1.6
    prov = "%d panels · %d traced elements · %d channels · editable SVG + vector PDF · every mark locatable" % (
        len(geom), len([e for e in els if e["kind"] != "encoding"]),
        len([e for e in encs.values()]))
    ops.append(T(M, fy, prov, sz["footer"], "normal", "#7A7A7A", "start", "footer-note", "footer"))
    sizes_used.append(sz["footer"])
    if cap_lines:
        cy = H - M - sz["footer"] * 1.6 - lines_h(cap_lines, sz["footer"], 1.30) - 1.0
        for ln in cap_lines:
            ops.append(T(M, cy, ln, sz["footer"], "normal", "#4A4A4A", "start", "caption", "footer"))
            sizes_used.append(sz["footer"])
            cy += sz["footer"] * 1.30

    ops.sort(key=lambda o: LAYER_INDEX.get(o.get("layer"), 3))
    box = [o for o in ops if o["op"] in ("rect", "text")]
    maxy = max([o["y"] + (o["h"] if o["op"] == "rect" else 0.0) for o in box] or [0.0])
    maxx = max([o["x"] + (o["w"] if o["op"] == "rect" else 0.0) for o in box] or [0.0])
    model = {
        "canvas": {"w_pt": round(W, 2), "h_pt": round(H, 2), "unit": cv.get("unit") or "mm",
                   "width": cv.get("width"), "height": cv.get("height"), "dpi": cv.get("dpi") or 300,
                   "svg_attrs": cv.get("svg_attrs") or "%gmm" % (W / 72.0 * 25.4)},
        "title": title, "subtitle": subtitle, "caption": caption,
        "direction": direction,
        "panels": [{"id": g["id"], "order": g["i"] + 1, "role": g["role"],
                    "heading": strip(g["p"].get("heading")), "flow": strip(g["p"].get("flow")),
                    "claim": strip(g["p"].get("claim")),
                    "bbox": [round(g["x"], 1), round(g["y"], 1), round(g["w"], 1), round(g["h"], 1)],
                    "elements": g["elements"]} for g in geom],
        "elements": els,
        "encodings": [{"id": e["id"], "channel": e.get("channel"), "meaning": strip(e.get("meaning")),
                       "unit": strip(e.get("unit")), "panel": e.get("panel"),
                       "marks": [{"mark_id": "%s-m%d" % (e["id"], j + 1), "label": strip(c.get("label")),
                                  "value": strip(c.get("value")), "num": c.get("num"),
                                  "color": c.get("color")}
                                 for j, c in enumerate(e.get("categories") or []) if isinstance(c, dict)],
                       "svg_group": e["id"]} for e in encs.values()],
        "legend": legend,
        "ops": ops,
        "stats": {"panels": len(geom), "elements": len(els), "text_ops": sum(o["op"] == "text" for o in ops),
                  "min_font": round(min(sizes_used), 2) if sizes_used else 0.0,
                  "max_y": round(maxy, 1), "max_x": round(maxx, 1),
                  "inside_canvas": maxx <= W + 0.6 and maxy <= H + 0.6},
        "dropped": dropped, "warnings": warnings,
    }
    return model
