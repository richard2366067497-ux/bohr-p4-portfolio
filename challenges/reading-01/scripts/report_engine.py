# -*- coding: utf-8 -*-
"""report_engine: structure, coverage, evidence, draft candidates.

Every derived item keeps the locator of the page object it came from plus the verbatim substring it
was read from. Nothing is invented: an unreadable field carries its reason.
"""
import hashlib, json, os, re
from pdf_engine import CAP_RE, MATH_RE, is_caption

REF_HEAD = re.compile(r"^\s*(references|bibliography|literature cited)\b", re.I)
ABS_HEAD = re.compile(r"^\s*(abstract|摘要|summary)\s*[:：]?\s*$", re.I)
REF_ITEM = re.compile(r"(?=\[\d{1,3}\])|(?=^\s*\d{1,3}\.\s)")
AUTH_RE = re.compile(r"(\b[A-Z]\.\s?){0,3}[A-Z][a-zà-ÿ'’-]{1,}")


def looks_like_authors(text):
    t = norm(text)
    if not (3 <= len(t.split()) <= 16) or len(t) > 160 or FIG_RE.search(t):
        return False
    if re.search(r"\bet al\b", t, re.I):
        return True
    if re.search(r"[.!?。]\s+\S", t) and not re.match(r"^[A-Z]\.", t):
        return False
    return len(AUTH_RE.findall(t)) >= 3
FIG_RE = re.compile(r"\b(fig(?:ure)?\.?|table|tab\.|scheme|chart)\b", re.I)
FOOT_RE = re.compile(r"^\s*[*†‡§¶]|^\s*\d{1,2}\s+(?=[A-Z])")


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def sha16(s):
    return hashlib.sha256(norm(s).encode("utf-8", "replace")).hexdigest()[:16]


def wj(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")


def wt(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def rj(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def quote(text, limit=200):
    t = norm(text)
    return t if len(t) <= limit else t[:limit].rstrip() + "…"


def cells_from_words(words, size):
    ws = sorted([w for w in words if (w.get("text") or "").strip()], key=lambda w: w["x0"])
    cells, cur = [], []
    for w in ws:
        if cur:
            gap = w["x0"] - (cur[-1].get("x1") or (cur[-1]["x0"] + len(cur[-1]["text"]) * 0.5 * size))
            if gap > 1.2 * max(6.0, size):
                cells.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cells.append(cur)
    return [" ".join(x["text"] for x in c) for c in cells if c]


def flat_blocks(entries):
    """Reading-order list of every page object, with a stable file locator."""
    out = []
    for e in entries:
        for o in e["objects"]:
            out.append({"page": e["page"], "oid": o["oid"], "type": o["type"], "text": o["text"],
                        "bbox": o["bbox"], "size": o["size"], "level": o["level"],
                        "words": o.get("words") or []})
    return out


MAX_CHARS = 500000


def situation(ctx):
    mats, parsed = ctx["materials"], [m for m in ctx["materials"] if m["status"] == "parsed"]
    if not mats or not parsed:
        return "insufficient_evidence"
    if len(parsed) < len(mats) or any(m.get("truncated") for m in mats) or ctx["errors"]:
        return "partial"
    return "ok"


def changes(ctx):
    if ctx["change_records"]:
        return ctx["change_records"]
    recs, st = [], ctx["structure"]
    if ctx["primary"]:
        e = ctx["primary"]["entries"]
        cols = ", ".join("page %d: %d column(s)" % (p["page"], p["columns"]) for p in e)
        recs.append({"change_id": "CH-01", "action": "reading_order_reconstructed", "locator": ctx["rel"],
                     "detail": "objects ordered by column band on the page, then top to bottom (%s)" % cols,
                     "reversible": True})
        ex = sum(len([x for x in (p.get("excluded") or []) if x["text"]]) for p in e)
        recs.append({"change_id": "CH-02", "action": "running_matter_marked", "locator": ctx["rel"],
                     "detail": "%d repeated header/footer band(s) stayed in layout_objects.jsonl and "
                               "were left out of the reading order" % ex, "reversible": True})
    for i, a in enumerate(st.get("draft_applied") or [], start=len(recs) + 1):
        recs.append({"change_id": "CH-%02d" % i, "action": "draft_override_applied",
                     "locator": a.get("locator") or ctx["rel"], "field": a.get("field"),
                     "detail": "a reviewer value replaced the derived one", "reversible": True})
    if not recs:
        recs.append({"change_id": "CH-01", "action": "source_left_untouched",
                     "locator": ctx["rel"] or "input",
                     "detail": "no readable text layer was found; no field was derived and no source "
                               "byte was rewritten",
                     "reversible": True})
    ctx["change_records"] = recs
    return recs


def uncertain(ctx):
    out = []
    for m in ctx["materials"]:
        if m["status"] != "parsed":
            out.append("%s was not read as text: %s" % (m["rel"], m["reason"] or m["status"]))
        elif m.get("truncated"):
            out.append("%s was read only up to %d bytes" % (m["rel"], MAX_CHARS))
    st = ctx["structure"]
    if ctx["primary"]:
        if not st["references"]:
            out.append("no reference list was found, so citations cannot be cross-checked")
        if not st["tables"]:
            out.append("no table row was rebuilt; a scanned or image-only table stays unreadable")
        if st["cited_labels"]:
            missing = [c for c in st["cited_labels"] if c not in st["caption_labels"]]
            if missing:
                out.append("cited but not captioned in this file: %s" % ", ".join(missing[:8]))
        if ctx["primary"]["meta"].get("flags"):
            out.append("parser flags on %s: %s"
                       % (ctx["rel"], ", ".join(ctx["primary"]["meta"]["flags"])))
        if (ctx["primary"]["meta"].get("engine") or "").startswith("text"):
            out.append("a plain-text material has no page geometry, so columns and tables are "
                       "unrecoverable")
    out.append("reading order is rebuilt from word positions, so a layout without a whitespace gutter "
               "may be ordered top-to-bottom")
    for e in ctx["errors"]:
        out.append(e)
    return out[:24]


def coverage_rows(ctx):
    if not ctx["primary"]:
        return {"file": ctx["rel"] or "input", "pages": 0, "objects_total": 0, "objects_by_type": {},
                "checks": [{"check": "text_layer", "value": False,
                            "note": "no file under the input directory carried a text layer"}],
                "missing": ["title", "abstract", "sections", "tables", "formulas", "references"]}
    return coverage(ctx["primary"]["entries"], ctx["structure"], ctx["rel"],
                    ctx["structure"]["unreadable"])


def blocks_payload(ctx, cap=60):
    if not ctx["primary"]:
        return {"count": 0, "by_type": {}, "items": [],
                "note": "no page object was rebuilt; see unreadable"}
    rows = flat_blocks(ctx["primary"]["entries"])
    by = {}
    for b in rows:
        by[b["type"]] = by.get(b["type"], 0) + 1
    items = [{"locator": "%s p%d %s %s" % (ctx["rel"], b["page"], b["oid"], b["type"]),
              "type": b["type"], "page": b["page"], "chars": len(b["text"]),
              "quote": quote(b["text"], 160), "sha256_16": sha16(b["text"])} for b in rows[:cap]]
    return {"count": len(rows), "by_type": by, "items": items,
            "note": "each row keeps the page object it came from"}


def envelope(items, note, extra=None):
    out = {"count": len(items), "items": items, "note": note}
    if extra:
        out.update(extra)
    return out


def contract_values(ctx):
    st, mats = ctx["structure"], ctx["materials"]
    meta = (ctx["primary"] or {}).get("meta") or {}
    doc = {"file": ctx["rel"] or "no readable file",
           "pages": len((ctx["primary"] or {}).get("entries") or []),
           "engine": meta.get("engine") or "no text-layer engine was needed", "chars": meta.get("chars", 0),
           "title": (st["title"] or {}).get("text", "no title line was rebuilt"),
           "note": "the file this reading is based on"}
    return {
        "document": doc,
        "blocks": blocks_payload(ctx),
        "sections": envelope([{"id": s["id"], "level": s["level"], "title": s["title"],
                               "locator": s["locator"], "page": s["page"]} for s in st["sections"]],
                             "headings in reading order; level from the size or the numbering"),
        "tables": envelope([{"id": t["id"], "label": t["label"] or t["id"], "locator": t["locator"],
                             "rows": t["row_count"], "cols": t["col_count"],
                             "header": t["rows"][0] if t["rows"] else []} for t in st["tables"]],
                           "grids rebuilt from consecutive row objects"),
        "formulas": envelope([{"id": f["id"], "number": f["number"], "locator": f["locator"],
                               "quote": f["quote"]} for f in st["formulas"]],
                             "lines with math marks and an operator"),
        "reading_order_notes": envelope([{"page": n["page"], "kind": n["kind"], "detail": n["detail"]}
                                         for n in st["reading_order_notes"]],
                                        "one note per page needing a column decision",
                                        {"columns": sum(p["columns"] for p in
                                                        (ctx["primary"] or {}).get("entries") or [])}),
        "unreadable": envelope([{"file": u["file"], "status": u["status"], "reason": u["reason"],
                                 "locator": u["locator"]} for u in st["unreadable"]],
                               "files that could not be read, with the reason"),
        "sources": envelope([{"id": m["id"], "rel": m["rel"], "kind": m["kind"], "status": m["status"],
                              "chars": m["chars"], "reason": m["reason"]} for m in mats],
                            "every file under the input directory, read or not"),
        "uncertainty": envelope(uncertain(ctx), "limits of this pass, stated not hidden"),
        "change_records": envelope(changes(ctx), "every step that changed the order or a field; each "
                                                 "is reversible and names its locator"),
    }


def build_structure(entries, rel):
    blocks = flat_blocks(entries)
    loc = lambda b: "%s p%d %s %s" % (rel, b["page"], b["oid"], b["type"])
    first_page = [b for b in blocks if b["page"] == 1]
    body = [b for b in first_page if b["type"] in ("paragraph", "heading", "caption", "table_row")]
    title, authors, abstract = {}, [], {}
    cands = [b for b in body if b["type"] in ("paragraph", "heading") and 6 <= len(b["text"]) <= 220]
    tblock = None
    if cands:
        sizes = sorted(b["size"] for b in cands)
        med = sizes[len(sizes) // 2]
        big = [b for b in cands if b["size"] >= 1.12 * med and not FIG_RE.search(b["text"])]
        pool = big or [b for b in cands if len(b["text"]) >= 12]
        if pool:
            top = max(pool, key=lambda b: (b["size"], -b["bbox"][1]))
            tblock = top
            title = {"text": top["text"], "locator": loc(top), "page": 1, "size": top["size"],
                     "bbox": top["bbox"], "quote": quote(top["text"])}
    if tblock:
        for b in body:
            if b is tblock or b["text"] == title["text"]:
                continue
            if not (0 <= b["bbox"][1] - tblock["bbox"][3] <= 90):
                continue
            if looks_like_authors(b["text"]):
                authors.append({"text": b["text"], "locator": loc(b), "quote": quote(b["text"])})
    for i, b in enumerate(blocks):
        if ABS_HEAD.match(b["text"]):
            k = i + 1
            while k < len(blocks) and blocks[k]["type"] not in ("heading",):
                if blocks[k]["text"] and not ABS_HEAD.match(blocks[k]["text"]):
                    abstract = {"text": blocks[k]["text"], "locator": loc(blocks[k]),
                                "quote": quote(blocks[k]["text"], 260)}
                    break
                k += 1
            break
    else:
        for i, b in enumerate(blocks):
            if re.match(r"^\s*abstract\b", b["text"], re.I) and len(b["text"]) > 60:
                abstract = {"text": b["text"], "locator": loc(b), "quote": quote(b["text"], 260)}
                break
    sections, tables, formulas, captions, refs, footnotes = [], [], [], [], [], []
    def _tid():
        return "T%02d" % (len(tables) + 1)

    run = []
    for i, b in enumerate(blocks):
        if b["type"] == "table_row":
            run.append(b)
            continue
        if run:
            tables.append(_table(run, blocks, loc, rel, _tid()))
            run = []
        if b["type"] == "heading":
            if title and b["text"] == title.get("text"):
                continue
            sections.append({"id": "S%02d" % (len(sections) + 1), "level": b["level"],
                             "title": b["text"], "page": b["page"], "locator": loc(b),
                             "quote": quote(b["text"], 120), "blocks_after": 0})
        elif b["type"] == "formula":
            formulas.append({"id": "F%02d" % (len(formulas) + 1), "text": b["text"], "page": b["page"],
                             "locator": loc(b), "quote": quote(b["text"], 160),
                             "number": _fnum(b["text"])})
        elif b["type"] == "caption":
            m = CAP_RE.match(b["text"])
            captions.append({"id": "C%02d" % (len(captions) + 1), "page": b["page"], "locator": loc(b),
                             "quote": quote(b["text"], 200),
                             "kind": (m.group(0).strip() if m else "caption"), "label": b["text"]})
        if sections:
            sections[-1]["blocks_after"] += 1
    if run:
        tables.append(_table(run, blocks, loc, rel, _tid()))
    ref_start = None
    for i, b in enumerate(blocks):
        if b["type"] == "heading" and REF_HEAD.match(b["text"]):
            ref_start = i
            break
    if ref_start is not None:
        for j, b in enumerate(blocks[ref_start + 1:], start=ref_start + 1):
            if b["type"] == "heading":
                break
            for piece in [p for p in REF_ITEM.split(b["text"]) if p and p.strip()]:
                p = piece.strip()
                if not p:
                    continue
                m = re.match(r"^\[?(\d{1,3})\]?\.?\s*", p)
                refs.append({"id": "R%02d" % (len(refs) + 1), "page": b["page"], "locator": loc(b),
                             "label": ("[%s]" % m.group(1)) if m else "-", "quote": quote(p, 200)})
    for b in blocks:
        if b["type"] == "paragraph" and (FOOT_RE.match(b["text"]) or b["size"] < 8.6) \
                and b["bbox"][3] > 0.85 * 1000 and len(b["text"]) < 320:
            footnotes.append({"id": "FN%02d" % (len(footnotes) + 1), "page": b["page"],
                              "locator": loc(b), "quote": quote(b["text"], 160)})
    labels = {t["label"].lower() for t in tables if t.get("label")} | \
             {c["kind"].lower() for c in captions if c.get("kind")}
    cited = sorted({m.group(0).lower() for b in blocks for m in
                    re.finditer(r"(?:fig(?:ure)?\.?|table|scheme)\s*\d{1,3}", b["text"], re.I)})
    notes = []
    for e in entries:
        if e.get("gutters"):
            notes.append({"page": e["page"], "kind": "two_column",
                          "detail": "gutter(s) at x=%s split the body into %d reading column(s)"
                                    % (", ".join("%.0f-%.0f" % (g[0], g[1]) for g in e["gutters"]), e["columns"])})
        elif e["columns"] > 1:
            notes.append({"page": e["page"], "kind": "columns_inferred",
                          "detail": "no full-height gutter; %d column band(s) used" % e["columns"]})
        ex = [x for x in e.get("excluded") or [] if x["text"]]
        if ex:
            notes.append({"page": e["page"], "kind": "running_matter",
                          "detail": "%d band(s) outside the text block excluded: %s"
                                    % (len(ex), "; ".join(quote(x["text"], 40) for x in ex[:3]))})
    return {"title": title, "authors": authors, "abstract": abstract, "sections": sections,
            "tables": tables, "formulas": formulas, "captions": captions, "references": refs,
            "footnotes": footnotes, "reading_order_notes": notes,
            "caption_labels": sorted(labels), "cited_labels": cited}


def _fnum(text):
    m = re.search(r"\((\d{1,3}[a-z]?)\)\s*$", text or "")
    return "(%s)" % m.group(1) if m else ""


def _table(run, blocks, loc, rel, tid="T01"):
    rows, cols = [], 0
    for b in run:
        cells = cells_from_words(b["words"], b["size"]) if b.get("words") else []
        if len(cells) < 2:
            cells = [c for c in re.split(r"\s{3,}|\s*\|\s*", b["text"]) if c.strip()]
        rows.append(cells)
        cols = max(cols, len(cells))
    idx = blocks.index(run[0]) if run else 0
    label, cap = "", ""
    for b in blocks[max(0, idx - 2):idx + len(run) + 3]:
        if b["type"] == "caption" and re.match(r"^\s*(table|tab\.)", b["text"], re.I):
            cap = b["text"]
            m = CAP_RE.match(b["text"])
            label = m.group(0).strip() if m else ""
            break
    return {"id": tid, "page": run[0]["page"] if run else 0,
            "locator": loc(run[0]) if run else rel, "label": label, "caption": quote(cap, 200),
            "quote": quote(" | ".join(rows[0]) if rows else "", 200),
            "row_count": len(rows), "col_count": cols, "rows": rows[:40],
            "continuation_of": ""}


def coverage(entries, structure, rel, unreadable):
    blocks = flat_blocks(entries)
    kinds = {}
    for b in blocks:
        kinds[b["type"]] = kinds.get(b["type"], 0) + 1
    return {"file": rel, "pages": len(entries),
            "objects_total": len(blocks), "objects_by_type": kinds,
            "checks": [
                {"check": "text_layer", "value": bool(blocks), "note": "a page object was rebuilt"},
                {"check": "title", "value": bool(structure["title"]), "note": "largest body line on page 1"},
                {"check": "abstract", "value": bool(structure["abstract"]), "note": "block under an abstract heading"},
                {"check": "sections", "value": len(structure["sections"]), "note": "heading objects"},
                {"check": "tables", "value": len(structure["tables"]), "note": "consecutive row objects"},
                {"check": "formulas", "value": len(structure["formulas"]), "note": "math marks on a line"},
                {"check": "captions", "value": len(structure["captions"]), "note": "figure and table labels"},
                {"check": "references", "value": len(structure["references"]), "note": "items under a reference heading"},
                {"check": "reading_order", "value": len(structure["reading_order_notes"]),
                 "note": "column and gutter decisions"},
                {"check": "unreadable", "value": len(unreadable), "note": "files or glyphs left unread"}],
            "missing": [k for k in ("title", "abstract", "sections", "tables", "formulas",
                                    "references") if not structure.get(k)]}


def evidence_rows(entries, structure, rel):
    rows = []

    def add(kind, page, locator, text, extra=None):
        item = {"claim_id": "%s-%03d" % (kind, len(rows) + 1), "kind": kind, "page": page,
                "locator": locator, "quote": quote(text, 220), "verbatim": True,
                "sha256_16": sha16(text)}
        if extra:
            item.update(extra)
        rows.append(item)

    for b in flat_blocks(entries):
        add("block_" + b["type"], b["page"],
            "%s p%d %s %s" % (rel, b["page"], b["oid"], b["type"]), b["text"],
            {"bbox": b["bbox"], "size": b["size"]})
    for s in structure["sections"]:
        add("section", s["page"], s["locator"], s["title"], {"level": s["level"]})
    for t in structure["tables"]:
        add("table", t["page"], t["locator"], t["quote"], {"rows": t["row_count"], "cols": t["col_count"]})
    for f in structure["formulas"]:
        add("formula", f["page"], f["locator"], f["text"], {"number": f["number"]})
    for c in structure["captions"]:
        add("caption", c["page"], c["locator"], c["label"])
    for r in structure["references"]:
        add("reference", r["page"], r["locator"], r["quote"], {"label": r["label"]})
    for n in structure["reading_order_notes"]:
        add("reading_order", n["page"], "%s p%d reading-order" % (rel, n["page"]), n["detail"])
    for u in structure.get("unreadable") or []:
        add("unreadable", u.get("page") or 0, u.get("locator") or rel,
            u.get("text") or u.get("reason") or "", {"reason": u.get("reason")})
    return rows


def render_parsed(entries, structure, rel, meta):
    L = ["# Parsed document: %s" % rel, "",
         "Pages: %d · objects: %d · engine: %s · characters: %d"
         % (len(entries), sum(len(e["objects"]) for e in entries), meta.get("engine", "stdlib"),
            meta.get("chars", 0)), ""]
    if structure["title"]:
        L += ["## Title", "", "> %s" % structure["title"]["text"],
              "", "locator: `%s`" % structure["title"]["locator"], ""]
    if structure["authors"]:
        L += ["## Authors", ""] + ["> %s" % a["text"] for a in structure["authors"]] + [""]
    if structure["abstract"]:
        L += ["## Abstract", "", structure["abstract"]["text"], "",
              "locator: `%s`" % structure["abstract"]["locator"], ""]
    L += ["## Sections", ""]
    L += ["- %s%s — `%s`" % ("  " * max(0, s["level"] - 1), s["title"], s["locator"])
          for s in structure["sections"]] or ["- no heading object was rebuilt"]
    L += ["", "## Body in reading order", ""]
    for b in flat_blocks(entries):
        tag = b["type"]
        L.append("- `%s` [%s p%d %s %s] %s" % (tag, rel, b["page"], b["oid"], tag, quote(b["text"], 200)))
    if not flat_blocks(entries):
        L.append("- no text object could be rebuilt; see `unreadable.json`")
    L += ["", "## Tables", ""]
    for t in structure["tables"]:
        L += ["- %s page %d (%d×%d) `%s`" % (t["label"] or t["id"], t["page"], t["row_count"],
                                             t["col_count"], t["locator"])]
        for row in t["rows"][:12]:
            L.append("  - " + " | ".join(row))
    if not structure["tables"]:
        L.append("- no table row was rebuilt")
    L += ["", "## Formulas", ""]
    L += ["- `%s` page %d %s" % (f["text"], f["page"], f["number"]) for f in structure["formulas"]] \
        or ["- no line carried a math mark with an operator"]
    L += ["", "## Captions", ""]
    L += ["- page %d: %s" % (c["page"], quote(c["label"], 140)) for c in structure["captions"]] \
        or ["- no figure or table caption was matched"]
    L += ["", "## References", ""]
    L += ["- %s %s" % (r["label"], quote(r["quote"], 180)) for r in structure["references"]] \
        or ["- no reference list was found"]
    L += ["", "## Reading order notes", ""]
    L += ["- page %d (%s): %s" % (n["page"], n["kind"], n["detail"])
          for n in structure["reading_order_notes"]] or ["- single-column file: natural order kept"]
    return "\n".join(L) + "\n"


def page_map(entries, rel):
    pages = []
    for e in entries:
        pages.append({"page": e["page"], "size": [e["width"], e["height"]],
                      "columns": e["columns"], "gutters": e["gutters"],
                      "excluded_bands": len([x for x in (e.get("excluded") or []) if x["text"]]),
                      "objects": [{"oid": o["oid"], "type": o["type"], "bbox": o["bbox"],
                                   "chars": len(o["text"]), "text": quote(o["text"], 120)}
                                  for o in e["objects"]]})
    return {"file": rel, "page_count": len(pages), "pages": pages,
            "note": "bbox is [x0, y0, x1, y1], top-left origin; pages are 1-based"}


def layout_objects(entries, rel):
    rows = []
    for e in entries:
        for o in e["objects"]:
            rows.append({"file": rel, "page": e["page"], "oid": o["oid"], "type": o["type"],
                         "bbox": o["bbox"], "size": o["size"], "level": o["level"],
                         "reading_index": o.get("reading_index"), "text": o["text"]})
        for x in e.get("excluded") or []:
            rows.append({"file": rel, "page": e["page"], "oid": x["oid"], "type": x["type"],
                         "bbox": x["bbox"], "size": x["size"], "level": 0, "reading_index": None,
                         "text": x["text"]})
    return rows


def draft_candidates(structure, entries, rel):
    """Candidates to accept or correct: each value already carries its locator."""
    cands = {"source_file": rel, "items": []}

    def add(field, value, locator, why):
        if isinstance(value, str) and value:
            cands["items"].append({"field": field, "value": value, "locator": locator, "why": why})

    if structure["title"]:
        add("title", structure["title"]["text"], structure["title"]["locator"], "largest page-1 body line")
    if structure["authors"]:
        add("authors", "; ".join(a["text"] for a in structure["authors"]),
            structure["authors"][0]["locator"], "name pattern under the title")
    if structure["abstract"]:
        add("abstract", structure["abstract"]["text"], structure["abstract"]["locator"],
            "block under an abstract heading")
    for s in structure["sections"][:12]:
        add("section", s["title"], s["locator"], "heading object, level %d" % s["level"])
    for t in structure["tables"][:8]:
        add("table", t["caption"] or t["quote"], t["locator"],
            "%d×%d grid from consecutive row objects" % (t["row_count"], t["col_count"]))
    for f in structure["formulas"][:8]:
        add("formula", f["text"], f["locator"], "math marks with an operator%s"
            % (" numbered %s" % f["number"] if f["number"] else ""))
    for c in structure["captions"][:10]:
        add("caption", c["label"], c["locator"], "figure or table label")
    for r in structure["references"][:12]:
        add("reference", r["quote"], r["locator"], "item under a reference heading")
    return cands


def loc_resolves(locator, rel, objects):
    """A locator resolves only when it names a page object this reading rebuilt: '<file> pN <oid>'
    and anything behind it. Nothing else counts."""
    if not locator:
        return False
    for o in objects or []:
        pre = "%s p%d %s" % (rel, o["page"], o["oid"])
        if locator == pre or locator.startswith(pre + " "):
            return True
    return False


def apply_draft(structure, draft, rel, objects=None):
    """Human overrides win; unanchored entries are rejected and recorded."""
    applied, rejected = [], []
    items = draft.get("items") if isinstance(draft.get("items"), list) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        field = str(it.get("field") or "").strip()
        value = it.get("value")
        value = value.strip() if isinstance(value, str) else value
        locator = str(it.get("locator") or "").strip()
        rec = {"field": field, "locator": locator, "value": quote(str(value), 120)}
        if not field or not value:
            rejected.append(dict(rec, reason="empty field or value"))
            continue
        if not loc_resolves(locator, rel, objects):
            rejected.append(dict(rec, reason="locator does not name a page object of this file"))
            continue
        if field == "title":
            structure["title"] = {"text": value, "locator": locator, "page": 1,
                                  "size": (structure["title"] or {}).get("size", 0),
                                  "quote": quote(value), "from_draft": True}
        elif field == "abstract":
            structure["abstract"] = {"text": value, "locator": locator, "quote": quote(value, 260),
                                     "from_draft": True}
        elif field == "authors":
            structure["authors"] = [{"text": value, "locator": locator, "quote": quote(value),
                                     "from_draft": True}]
        elif field == "section":
            structure["sections"].append({"id": "S%02d" % (len(structure["sections"]) + 1), "level": 1,
                                          "title": value, "page": 0, "locator": locator,
                                          "quote": quote(value, 120), "blocks_after": 0,
                                          "from_draft": True})
        elif field == "caption":
            structure["captions"].append({"id": "C%02d" % (len(structure["captions"]) + 1), "page": 0,
                                          "locator": locator, "quote": quote(value, 200),
                                          "kind": "caption", "label": value, "from_draft": True})
        elif field == "reference":
            structure["references"].append({"id": "R%02d" % (len(structure["references"]) + 1),
                                            "page": 0, "locator": locator, "label": "-",
                                            "quote": quote(value, 200), "from_draft": True})
        else:
            rejected.append(dict(rec, reason="field is not one the draft schema accepts"))
            continue
        applied.append(rec)
    structure["draft_applied"] = applied
    structure["draft_rejected"] = rejected
    return applied, rejected
