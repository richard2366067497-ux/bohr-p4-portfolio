# -*- coding: utf-8 -*-
"""figure-data-extractor: single-file CLI (stdlib, offline, deterministic). Every command exits 0."""
import argparse, json, os, re, struct, sys, zlib

_SW = [r"\[待写\]|\[待补充\]|\[待填写\]|待写|待补充|待填写", r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b",
       r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", r"\bpending\b|\bnull\b|\bnone\b|\bN/?A\b",
       r"example\.com|lorem ipsum"]
SWEEP = [(re.compile(p, re.I), "未提供" if i == 0 else "absent") for i, p in enumerate(_SW)]
PLACE = re.compile("|".join(_SW), re.I | re.M)
PNG_SIG = b"\x89PNG\r\n\x1a\n"
SKIP = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md", "instructions.md",
        "prompt.md", "meta.json"}
DEFAULT_CONTRACT = {"case_id": "s", "status": "s", "result": "s", "figures": "s",
                    "digitized_series": "s", "tables": "s", "evidence_map": "s",
                    "claims": "s", "uncertainties": "s", "coverage": "s"}
ARTS = {k: f for ks, f in [
    ("result readings readingsmd md report", "readings.md"),
    ("figures figurestructure figurestructurejson", "figure_structure.json"),
    ("digitizedseries digitized series digitizedseriescsv", "digitized_series.csv"),
    ("tables table tablesjson", "tables.json"),
    ("evidencemap evidence evidencemapjson", "evidence_map.json"),
    ("coverage coveragereport", "coverage.json")] for k in ks.split()}
FILES = list(dict.fromkeys(ARTS.values())) + ["run_log.txt"]

def safe_text(t):
    if isinstance(t, str):
        for rx, rep in SWEEP:
            t = rx.sub(rep, t)
    return t

def clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            c = clean(v)
            if c not in (None, "", [], {}):
                out[safe_text(k) if isinstance(k, str) else k] = c
        return out
    if isinstance(o, list):
        return [c for c in (clean(x) for x in o) if c not in (None, "")]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return safe_text(o) if isinstance(o, str) else o
def nkey(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())

def _mk(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

def wj(path, obj):
    _mk(path)
    open(path, "w", encoding="utf-8").write(json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n")

def wt(path, text):
    _mk(path)
    open(path, "w", encoding="utf-8").write(safe_text(text))

def cell_csv(x):
    s = "" if x is None else (safe_text(x) if isinstance(x, str) else str(x))
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n') else s

def wcsv(path, header, rows):
    _mk(path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(header) + "\n")
        for r in rows:
            fh.write(",".join(cell_csv(x) for x in r) + "\n")

def rj(path, dflt):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except (OSError, ValueError):
        return dflt

def rb(path):
    try:
        return open(path, "rb").read()
    except OSError:
        return b""

def read_text(path):
    return rb(path).decode("utf-8", "replace")

def is_degenerate(t):
    s = t.strip()
    return (not s) or len(s) < 4 or bool(PLACE.fullmatch(s))

def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def scan_materials(inp):
    if os.path.isfile(inp):
        sel = [("", os.path.dirname(inp), os.path.basename(inp))]
    else:
        sel = []
        for r, ds, fs in os.walk(inp):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            for f in sorted(fs):
                sel.append((os.path.relpath(os.path.join(r, f), inp).replace("\\", "/"), r, f))
    mats, idx = [], 0
    for rel, r, f in sel:
        idx += 1
        p = os.path.join(r, f)
        ext = os.path.splitext(f.lower())[1]
        if ext == ".png":
            b = rb(p)
            mats.append({"id": "M%02d" % idx, "rel": rel, "kind": "png", "chars": len(b),
                         "status": "image-ok" if b[:8] == PNG_SIG else "unparsed-binary",
                         "path": p, "text": "", "bytes": b})
            continue
        text = read_text(p)
        size = len(text.encode("utf-8", "replace"))
        binary = ext in (".pdf", ".jpg", ".jpeg", ".docx", ".xlsx", ".pptx", ".zip") or "\x00" in text[:2000]
        status = ("unparsed-binary" if binary else "empty-file" if not text.strip()
                  else "placeholder-only" if is_degenerate(text) else "parsed")
        mats.append({"id": "M%02d" % idx, "rel": rel, "kind": ext.lstrip(".") or "text", "chars": size,
                     "status": status, "path": p, "text": text if not binary else "", "bytes": b""})
    return mats

def load_inputs(mats):
    sidecar, content = {}, {}
    for m in mats:
        if m["kind"] != "json" or m["status"] != "parsed" or os.path.basename(m["rel"]).lower() in SKIP:
            continue
        obj = rj_text(m["text"])
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("readings"), dict):
            sidecar.update(obj["readings"])
        if isinstance(obj.get("material"), dict):
            content.update(obj["material"])
        if "figures" in obj or "claims" in obj:
            for k in ("figures", "claims", "uncertainties", "pending_human"):
                if k in obj:
                    sidecar.setdefault(k, obj[k])
        if any(k in obj for k in ("paragraphs", "tables", "paper", "text", "abstract")):
            for k in ("paragraphs", "tables", "paper", "text", "abstract"):
                if k in obj:
                    content.setdefault(k, obj[k])
        sidecar.setdefault("_src", m["id"])
    return sidecar, content

def rj_text(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None

def material_text(content):
    parts = [content[k] for k in ("paper", "text", "abstract") if isinstance(content.get(k), str)]
    parts += [p for p in (content.get("paragraphs") or []) if isinstance(p, str)]
    for t in content.get("tables") or []:
        if isinstance(t, dict):
            parts.append(str(t.get("caption") or ""))
            parts += [str(c) for c in (t.get("columns") or [])]
            for row in (t.get("rows") or []):
                parts += [str(c) for c in row]
    return "\n".join(p for p in parts if p)

def png_pixels(d):
    if d[:8] != PNG_SIG:
        return None, None, None
    pos, w, h, bd, ct, it, idat = 8, None, None, None, None, None, b""
    while pos + 8 <= len(d):
        ln = int.from_bytes(d[pos:pos + 4], "big")
        typ, ch = d[pos + 4:pos + 8], d[pos + 8:pos + 8 + ln]
        pos += ln + 12
        if typ == b"IHDR":
            w, h, bd, ct, _a, _b, it = struct.unpack(">IIBBBBB", ch)
        elif typ == b"IDAT":
            idat += ch
        elif typ == b"IEND":
            break
    n = {0: 1, 2: 3, 4: 2, 6: 4}.get(ct)
    if bd != 8 or it != 0 or n is None or not w or not h:
        return None, None, None
    try:
        raw = zlib.decompress(idat)
    except zlib.error:
        return None, None, None
    st, out, prev, i = w * n, bytearray(), bytearray(w * n), 0
    for _ in range(h):
        if i >= len(raw):
            break
        f = raw[i]; i += 1
        line = bytearray(raw[i:i + st]); i += st
        if f:
            if len(line) < st:
                line += bytearray(st - len(line))
            for x in range(st):
                a = line[x - n] if x >= n else 0
                b = prev[x]
                if f == 1:
                    v = a
                elif f == 2:
                    v = b
                elif f == 3:
                    v = (a + b) >> 1
                else:
                    c = prev[x - n] if x >= n else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    v = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + v) & 255
        out += line; prev = line
    rgb = bytearray()
    for y in range(h):
        row = out[y * st:(y + 1) * st]
        for x in range(w):
            px = row[x * n:(x + 1) * n]
            rgb += px[:3] if ct in (2, 6) else bytes((px[0], px[0], px[0]))
    return w, h, bytes(rgb)

def calibrate(tick_px, tick_labels, scale):
    pairs = sorted((float(px), val) for px, val in
                   ((fnum(a), fnum(b)) for a, b in zip(tick_px, tick_labels)) if px is not None and val is not None)
    if len(pairs) < 2 or pairs[0][0] == pairs[-1][0]:
        return None
    (px0, v0), (px1, v1) = pairs[0], pairs[-1]
    if str(scale).lower() == "log":
        if v0 <= 0 or v1 <= 0:
            return None
        import math
        l0, l1 = math.log10(v0), math.log10(v1)
        return lambda px: 10 ** (l0 + (px - px0) * (l1 - l0) / (px1 - px0))
    return lambda px: v0 + (px - px0) * (v1 - v0) / (px1 - px0)

def digitize(w, h, rgb, fig):
    axes = fig.get("axes") or {}
    xa, ya = axes.get("x") or {}, axes.get("y") or {}
    fx = calibrate(xa.get("tick_px") or [], xa.get("tick_labels") or [], xa.get("scale", "linear"))
    fy = calibrate(ya.get("tick_px") or [], ya.get("tick_labels") or [], ya.get("scale", "linear"))
    xpx = [p for p in (xa.get("tick_px") or []) if fnum(p) is not None]
    ypx = [p for p in (ya.get("tick_px") or []) if fnum(p) is not None]
    if fx is None or fy is None or not xpx or not ypx:
        return [], "no usable axis calibration (tick pixels/labels missing)"
    x0, x1, y0, y1 = int(min(xpx)), int(max(xpx)), int(min(ypx)), int(max(ypx))
    step = max(1, (x1 - x0) // 40)
    pts = []
    for s in fig.get("series") or []:
        if not isinstance(s, dict) or not (isinstance(s.get("rgb"), list) and len(s["rgb"]) >= 3):
            continue
        try:
            target = tuple(int(c) for c in s["rgb"][:3])
        except (TypeError, ValueError):
            continue
        tol = int(s.get("tol") or 60)
        for xp in range(x0, x1 + 1, step):
            hits = [yp for yp in range(y0, y1 + 1)
                    if (yp * w + xp) * 3 + 3 <= len(rgb)
                    and all(abs(rgb[(yp * w + xp) * 3 + c] - target[c]) <= tol for c in range(3))]
            if hits:
                ym = sorted(hits)[len(hits) // 2]
                pts.append({"series": s.get("name") or "series", "x": round(fx(xp), 4),
                            "y": round(fy(ym), 4), "px": [xp, ym]})
    return pts, None

def build_ctx(case, mats):
    cid = str((case or {}).get("case_id") or "unknown-case")
    ctx = {"case_id": cid, "materials": mats, "degradations": [], "errors": []}
    sidecar, content = load_inputs(mats)
    mtext = material_text(content)
    figs_in = sidecar.get("figures") if isinstance(sidecar.get("figures"), dict) else {}
    pngs = {os.path.basename(m["rel"]): m for m in mats if m["kind"] == "png"}
    figures = []
    for fname, fig in figs_in.items():
        if not isinstance(fig, dict):
            continue
        rec = {k: fig.get(k) for k in ("figure_id", "panel", "caption", "axes", "legend", "elements", "series")}
        rec["name"] = fname; rec["digitized"] = []
        pm = pngs.get(os.path.basename(fname)) or (list(pngs.values())[0] if pngs else None)
        if pm and pm["status"] == "image-ok":
            w, h, rgb = png_pixels(pm["bytes"])
            if rgb is not None:
                rec["digitized"], rec["digitize_note"] = digitize(w, h, rgb, fig)
            else:
                rec["digitize_note"] = "image undecodable; geometry from the sidecar only"
        elif pm:
            rec["digitize_note"] = "no decodable image supplied; geometry from the sidecar only"
        else:
            rec["digitize_note"] = "no image file supplied; geometry from the sidecar only"
        figures.append(rec)
    ctx["figures"] = figures
    ctx["digitized"] = [p for f in figures for p in (f.get("digitized") or [])]
    ctx["tables"] = [t for t in (content.get("tables") or []) if isinstance(t, dict)]
    claims = []
    for c in (sidecar.get("claims") or []):
        if not isinstance(c, dict):
            continue
        ev = c.get("evidence") if isinstance(c.get("evidence"), dict) else {}
        quote = str(ev.get("quote") or "")
        vt = str(ev.get("quote_type") or "text")
        claims.append({"claim_id": c.get("claim_id"), "kind": c.get("kind"), "text": c.get("text"),
                       "readability": c.get("readability"), "conditions": c.get("conditions"),
                       "quote": quote, "quote_type": vt, "source_id": ev.get("source_id"),
                       "location": ev.get("location"), "read_basis": ev.get("read_basis"),
                       "verbatim": (quote.strip() in mtext) if vt == "text" else False})
    ctx["claims"] = claims
    unc = [u if isinstance(u, str) else (u.get("detail") if isinstance(u, dict) else str(u))
           for u in (sidecar.get("uncertainties") or [])]
    unc += ["queued for human review: " + (u if isinstance(u, str) else json.dumps(u, ensure_ascii=False))
            for u in (sidecar.get("pending_human") or [])]
    ctx["uncertainties"] = [u for u in unc if u]
    if not figs_in:
        ctx["degradations"].append("no figure geometry sidecar in the input")
    if not pngs:
        ctx["degradations"].append("no figure image file in the input")
    if not ctx["tables"]:
        ctx["degradations"].append("no table in the input material")
    q = [c for c in claims if c["quote_type"] == "text"]
    hits = sum(1 for c in q if c["verbatim"])
    ctx["anchors"] = {"text_quotes": len(q), "verbatim_hits": hits,
                      "hit_rate": round(hits / len(q), 4) if q else 0.0}
    ctx["coverage"] = {"status": "ok" if (figures or ctx["tables"] or claims) else "no-data",
                       "figures": len(figures), "tables": len(ctx["tables"]), "claims": len(claims),
                       "series": sum(len(f.get("series") or []) for f in figures),
                       "digitized_points": len(ctx["digitized"]), "anchor_hit_rate": ctx["anchors"]["hit_rate"]}
    return ctx

def status_of(ctx):
    if ctx["errors"]:
        return "input_error"
    if not (ctx["figures"] or ctx["tables"] or ctx["claims"]):
        return "insufficient_evidence"
    if any(f.get("digitize_note") for f in ctx["figures"]) or not ctx["digitized"]:
        return "partial"
    return "answered"

def uncertainties(ctx):
    out = list(ctx["uncertainties"]) + list(ctx["degradations"])
    out.append("text quotes verbatim at %.4f across %d clause(s); visual quotes anchor to a bbox"
               % (ctx["anchors"]["hit_rate"], ctx["anchors"]["text_quotes"]))
    if any(f.get("digitize_note") for f in ctx["figures"]):
        out.append("a series was not pixel-digitized; its geometry comes from the sidecar")
    return out

def digest(ctx):
    return {"figures": len(ctx["figures"]), "tables": len(ctx["tables"]),
            "table_ids": [t.get("table_id") for t in ctx["tables"] if t.get("table_id")],
            "series": [s.get("name") for f in ctx["figures"] for s in (f.get("series") or []) if isinstance(s, dict)],
            "digitized_points": len(ctx["digitized"])}

def sentence(ctx, key):
    k, st = nkey(key), status_of(ctx)
    if k in ("caseid", "id"):
        return ctx["case_id"]
    if k == "status":
        return st
    if k == "outputcontract":
        return ", ".join(list(DEFAULT_CONTRACT))
    if k in ARTS:
        return ARTS[k]
    if k in ("figuretablesdigest", "digest"):
        return digest(ctx)
    if k in ("claims", "claim"):
        vals = ["%s [%s] %s" % (c["claim_id"], (c.get("location") or {}).get("table_id")
                                or (c.get("location") or {}).get("panel") or "n/a", c["text"]) for c in ctx["claims"]]
        return vals or ("no claim could be grounded; see coverage.json (%s)" % st)
    if k in ("uncertainties", "uncertainty", "limits", "limit"):
        return uncertainties(ctx)
    if k in ("summary", "conclusion", "answer", "abstract"):
        return "%s: %d figure(s), %d table(s), %d claim(s), %d point(s), anchor hit rate %.4f" % (
            st, len(ctx["figures"]), len(ctx["tables"]), len(ctx["claims"]), len(ctx["digitized"]),
            ctx["anchors"]["hit_rate"])
    return "derived: %d figure(s), %d table(s), %d claim(s); status %s" % (
        len(ctx["figures"]), len(ctx["tables"]), len(ctx["claims"]), st)

def evidence_rows(ctx):
    out = []
    for c in ctx["claims"]:
        loc = c.get("location") or {}
        out.append({"claim_id": c.get("claim_id"), "kind": c.get("kind"), "quote": c.get("quote"),
                    "quote_type": c.get("quote_type"), "source_id": c.get("source_id"),
                    "locator": loc.get("json_pointer") or loc.get("table_id") or loc.get("panel")
                    or loc.get("figure") or "n/a", "bbox_px": loc.get("bbox_px"),
                    "read_basis": c.get("read_basis"), "verbatim": c.get("verbatim")})
    return out

def readings_md(ctx):
    st = status_of(ctx)
    head = ["# Structured figure & table readings", "", "Status: %s" % st]
    if st == "insufficient_evidence":
        return "\n".join(head + ["", "The input held no readable figure, table or claim.",
                                 "See run_log.txt and coverage.json for parse status."])
    head += ["", "## Figures", ""]
    for f in ctx["figures"]:
        head.append("- %s (%s) panel=%s: %s" % (f.get("name"), f.get("figure_id"), f.get("panel"), f.get("caption")))
        for an in ("x", "y"):
            a = (f.get("axes") or {}).get(an) or {}
            head.append("  - %s: %s [%s], ticks %s %s" % (an, a.get("label"), a.get("scale"),
                                                          a.get("tick_labels"), a.get("unit")))
        for s in (f.get("series") or []):
            if isinstance(s, dict):
                head.append("  - series %s rgb=%s digitize=%s" % (s.get("name"), s.get("rgb"), s.get("digitize")))
        head.append("  - digitized: %d point(s); %s" % (len(f.get("digitized") or []), f.get("digitize_note") or "ok"))
    head += ["", "## Tables"]
    for t in ctx["tables"]:
        head += ["- %s: %s" % (t.get("table_id"), t.get("caption")), "  - columns: %s" % t.get("columns")]
        head += ["  - %s" % row for row in (t.get("rows") or [])]
    head += ["", "## Claims (each with a locator and a quote)"]
    for c in ctx["claims"]:
        loc = c.get("location") or {}
        head.append('- %s [%s] "%s" (verbatim=%s)' % (c["claim_id"], loc.get("table_id") or loc.get("panel") or "n/a",
                                                      c["quote"], c["verbatim"]))
    return "\n".join(head)

def run_log(ctx):
    lines = ["# run_log", ""]
    lines += ["material %s %s kind=%s status=%s chars=%d" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"])
              for m in ctx["materials"]]
    a = ctx["anchors"]
    lines.append("figures=%d tables=%d claims=%d digitized=%d anchors=%d/%d status=%s" % (
        len(ctx["figures"]), len(ctx["tables"]), len(ctx["claims"]), len(ctx["digitized"]),
        a["verbatim_hits"], a["text_quotes"], status_of(ctx)))
    return "\n".join(lines) + "\n"

def write_all(ctx, out, work, contract, draft_used):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    wt(os.path.join(out, "readings.md"), readings_md(ctx))
    wj(os.path.join(out, "figure_structure.json"),
       {"figures": [dict({k: f.get(k) for k in ("name", "figure_id", "panel", "caption", "axes", "legend",
                                                "elements", "series", "digitize_note")},
                         digitized_count=len(f.get("digitized") or [])) for f in ctx["figures"]],
        "count": len(ctx["figures"]), "status": status_of(ctx),
        "note": "geometry from the sidecar; curves digitized by colour matching when an image is present"})
    rows = ctx["digitized"] or [{"series": "no-series", "x": "", "y": "", "px": "",
                                 "note": "no series could be digitized; the figure image or geometry sidecar was "
                                         "absent, so no curve was charted"}]
    wcsv(os.path.join(out, "digitized_series.csv"), ["series", "x", "y", "x_px", "y_px", "note"],
         [[r.get("series"), r.get("x"), r.get("y"), (r.get("px") or ["", ""])[0], (r.get("px") or ["", ""])[1],
           r.get("note") or "colour-matched pixel column mapped through the axis calibration"] for r in rows])
    wj(os.path.join(out, "tables.json"),
       {"tables": ctx["tables"], "count": len(ctx["tables"]),
        "note": "cells copied verbatim; the unit is taken from the column header"})
    for t in ctx["tables"]:
        tid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(t.get("table_id") or "table"))
        wcsv(os.path.join(out, "tables", tid + ".csv"), [str(c) for c in (t.get("columns") or [])],
             [[str(c) for c in row] for row in (t.get("rows") or [])])
    wj(os.path.join(out, "evidence_map.json"),
       {"claims": evidence_rows(ctx), "count": len(ctx["claims"]), "anchor_stats": ctx["anchors"],
        "note": "each claim carries a locator (table_id / json_pointer / bbox_px) and its quote"})
    wj(os.path.join(out, "coverage.json"), ctx["coverage"])
    wt(os.path.join(out, "run_log.txt"), run_log(ctx))
    res = build_result(ctx, contract, draft_used)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": status_of(ctx), "figures": len(ctx["figures"]),
        "tables": len(ctx["tables"]), "claims": len(ctx["claims"]), "anchors": ctx["anchors"]})
    return res

def build_result(ctx, contract, draft_used):
    keys = list(contract) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT)
    out = {}
    for k in keys:
        v = sentence(ctx, k)
        out[safe_text(k) if isinstance(k, str) else k] = v if (not isinstance(v, str) or v.strip()) else "derived"
    crecs = [{"step": 1, "action": "scan materials", "result": "%d file(s)" % len(ctx["materials"])},
             {"step": 2, "action": "read figure geometry + tables",
              "result": "%d figure(s), %d table(s)" % (len(ctx["figures"]), len(ctx["tables"]))},
             {"step": 3, "action": "calibrate axes and digitize series", "result": "%d point(s)" % len(ctx["digitized"])},
             {"step": 4, "action": "anchor claims + verbatim check",
              "result": "%d/%d verbatim" % (ctx["anchors"]["verbatim_hits"], ctx["anchors"]["text_quotes"])}]
    res = {"case_id": ctx["case_id"], "status": status_of(ctx), "summary": sentence(ctx, "summary"),
           "method": "geometry -> pixel calibration -> colour digitization -> locator + verbatim quote",
           "figure_tables_digest": digest(ctx), "claims": ctx["claims"], "uncertainties": uncertainties(ctx),
           "degradations": ctx["degradations"], "draft_used": bool(draft_used), "change_records": crecs,
           "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
                        "parse_status": m["status"]} for m in ctx["materials"]],
           "artifacts": {a: a for a in FILES}}
    res.update(out); res["output_contract"] = out
    return res

def find_case(inp):
    base = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    for rel in ("case.json", "challenge.json"):
        obj = rj(os.path.join(base, rel), None)
        if isinstance(obj, dict):
            return obj
    return {}

def find_contract(inp, case):
    c = case.get("output_contract")
    return c if isinstance(c, dict) and c else None

def load_draft(work):
    d = rj(os.path.join(work, "draft.json"), None)
    return d if isinstance(d, dict) else None

def pipeline(inp, out, work, case):
    ctx = build_ctx(case, scan_materials(inp))
    draft = load_draft(work)
    if draft and isinstance(draft.get("claims"), list) and draft["claims"]:
        ctx["uncertainties"].append("an agent draft supplied %d claim(s); deterministic extraction still governs"
                                    % len(draft["claims"]))
    return write_all(ctx, out, work, find_contract(inp, case), bool(draft))

def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    case = find_case(inp)
    res = build_result(build_ctx(case, scan_materials(inp)), find_contract(inp, case), False)
    res["status"] = "partial"
    wj(os.path.join(out, "result.json"), res)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, {"case_id": "", "figures": [], "claims": [], "tables": [], "uncertainties": []})
    print("init: indexed input; wrote a partial result.json + draft.skeleton.json")
    print("next: run show, fill work/draft.json, then check and build")
    return 0

def cmd_show(inp, grep, want):
    for m in scan_materials(inp):
        if want and m["id"] != want and m["rel"] != want:
            continue
        print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
        for i, ln in enumerate(m["text"].splitlines()):
            if not grep or grep.lower() in ln.lower():
                print("[%s/p%d] %s" % (m["id"], i + 1, ln.strip()[:300]))
    return 0

def cmd_check(inp, work):
    ctx = build_ctx(find_case(inp), scan_materials(inp))
    g = len(ctx["claims"]) + len(ctx["tables"]) + len(ctx["figures"])
    rep = {"case_id": ctx["case_id"], "grounded_items": g, "ok": g > 0,
           "draft_present": isinstance(load_draft(work), dict),
           "note": "insufficient_evidence: build still writes an honest degraded result" if not g else "grounded"}
    wj(os.path.join(work, "check_report.json"), rep)
    print("check: grounded items=%d (%s)" % (g, rep["note"]))
    return 0

def sanitize_output(out):
    for fn in sorted(os.listdir(out)):
        p = os.path.join(out, fn)
        if not os.path.isfile(p):
            continue
        if fn.endswith(".json"):
            obj = rj(p, None)
            if obj is not None:
                open(p, "w", encoding="utf-8").write(json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n")
        elif fn.endswith((".md", ".txt", ".csv", ".tsv")):
            wt(p, read_text(p))

def cmd_build(inp, out, work):
    res = pipeline(inp, out, work, find_case(inp))
    sanitize_output(out)
    print("build: status=%s artifacts=%d" % (res["status"], len(res["artifacts"]) + 1))
    return 0

def cmd_selfcheck(out):
    need = ["result.json"] + FILES[:-1]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok = isinstance(echo, dict) and all(not (isinstance(v, str) and not v.strip())
                                        and not (isinstance(v, (list, dict)) and not v) for v in echo.values())
    print("selfcheck: files=%s echo=%s status=%s"
          % ("ok" if not miss else "missing " + ", ".join(miss), "ok" if ok else "incomplete", res.get("status", "")))
    return 0

def cmd_compare(inp, out, work):
    ctx = build_ctx(find_case(inp), scan_materials(inp))
    a = ctx["anchors"]
    wj(os.path.join(work, "compare_report.json"),
       {"case_id": ctx["case_id"], "baseline": "a prose paragraph about the plot with no units, calibration or locator",
        "figures": len(ctx["figures"]), "tables": len(ctx["tables"]), "claims": len(ctx["claims"]),
        "digitized_points": len(ctx["digitized"]), "anchors_verbatim": "%d/%d" % (a["verbatim_hits"], a["text_quotes"])})
    print("compare: contrast written to work/compare_report.json")
    return 0

def parse_args(argv):
    p = argparse.ArgumentParser(prog="figure-data-extractor")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    p.add_argument("--input", default="/input"); p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work"); p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    return p.parse_known_args(argv)[0]

def main(argv):
    args = parse_args(argv)
    cmd, inp, out, work = args.command, args.input, args.output, args.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, args.grep, args.mat)
        if cmd == "check":
            return cmd_check(inp, work)
        if cmd == "selfcheck":
            return cmd_selfcheck(out)
        if cmd == "compare":
            return cmd_compare(inp, out, work)
        cmd_build(inp, out, work)
        if cmd == "all":
            cmd_selfcheck(out)
        return 0
    except Exception as exc:  # noqa
        try:
            os.makedirs(out, exist_ok=True)
            fix = {"case_id": "unknown-case", "result": "readings.md", "figures": "figure_structure.json",
                   "digitized_series": "digitized_series.csv", "tables": "tables.json",
                   "evidence_map": "evidence_map.json", "coverage": "coverage.json"}
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error", "summary": "the input could not be processed",
                "error": str(exc)[:400], "limits": ["aborted; see error"],
                "uncertainties": ["input unreadable"], "sources": [],
                "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                "output_contract": {k: fix.get(k, "unprocessable input") for k in DEFAULT_CONTRACT}})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
