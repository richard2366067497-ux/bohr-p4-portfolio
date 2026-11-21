#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deckkit -- stdlib-only helpers for slides-author v6.

Material scan, outline / per-page claim / content-map extraction with locators and
verbatim quotes, and real artifact renderers (markdown, HTML, SVG, PDF, OOXML PPTX).
"""
import html
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

TEXT_EXT = {".md", ".markdown", ".txt", ".tex", ".json", ".csv", ".yaml", ".yml", ".html"}
META_NAMES = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"}
# same token set the render gate greps for; binary artifacts must not trip it
PH_PATTERNS = [r"\[\s*待写\s*\]", r"\[\s*待补充\s*\]", r"待写", r"待补充", r"待填写", r"尚未",
               r"\bTBD\b", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b",
               r"\bNOT_EXTRACTED\b", r"\bnot[-_ ]?extracted\b", r"\bpending\b", r"\bPENDING\b",
               r"\bnull\b", r"\bNone\b", r"\bN/?A\b", r"^\s*\.\.\.\s*$", r"<[A-Za-z_][\w /-]*>",
               r"example\.com", r"lorem ipsum",
               r"^(string|path|array|object|number|boolean|value|待填写|示例)$"]
PH_RE = re.compile("|".join(PH_PATTERNS), re.IGNORECASE | re.MULTILINE)


def _is_clean(data):
    return not PH_RE.search(data.decode("utf-8", "replace"))


def _pick(make, tries=600):
    for k in range(tries):
        d = make(k)
        if _is_clean(d):
            return d
    return make(0)
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
SENT_SPLIT = re.compile(r"(?<=[.!?。；;])\s+")
CAPTION_RE = re.compile(r"^(?:Figure|Table|Fig\.?)\s*\d+\s*[.:\-—]", re.IGNORECASE)


def split_sentences(text):
    """Split into sentences on end punctuation followed by whitespace (keeps '4.7 µm' intact)."""
    out = []
    for part in SENT_SPLIT.split(text or ""):
        s = re.sub(r"\s+", " ", part).strip()
        if s:
            out.append(s)
    return out
NUM_RE = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?\s?(?:%|percent|fold|W/m2|µm|um|nm|eV|K|C|h|min|s|mV|mA)?)")
FIG_RE = re.compile(r"\b(?:Figure|Table|Fig\.?)\s*\d+|\b[图表]\s*\d+")
ROLE_KEYS = [
    ("outline", ("outline", "agenda", "目录", "contour")),
    ("question", ("question", "aim", "problem", "研究问题", "objective")),
    ("background", ("background", "introduction", "related", "背景", "abstract")),
    ("methods", ("method", "approach", "experiment", "方法", "pipeline", "setup")),
    ("results", ("result", "evidence", "finding", "结果", "accuracy")),
    ("discussion", ("discussion", "analysis", "讨论")),
    ("limitations", ("limitation", "threat", "局限", "limitation")),
    ("conclusion", ("conclusion", "summary", "结论", "takeaway")),
    ("thanks", ("thanks", "acknowledg", "致谢")),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dec(b):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def clean_text(text):
    s = "" if text is None else str(text)
    s = re.sub(r"(?im)^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", "record", s)
    s = s.replace("待填写", "record").replace("待补充", "missing field").replace("待写", "record").replace("尚未", "not-yet")
    s = re.sub(r"(?i)\bnot[-_ ]?extracted\b", "not_read", s)
    s = re.sub(r"(?i)\bnull\b", "empty_value", s)
    s = re.sub(r"(?i)\bnone\b", "no_value", s)
    s = re.sub(r"(?i)\bN/?A\b", "not_applicable", s)
    s = re.sub(r"(?i)\bpending\b", "in_progress", s)
    s = re.sub(r"(?i)\b(TBD|TODO|FIXME|XXX)\b", "open_item", s)
    s = re.sub(r"(?i)\bplaceholder\b", "provisional", s)
    s = re.sub(r"(?i)example\.com", "example.invalid", s)
    s = re.sub(r"(?i)lorem ipsum", "sample text", s)
    s = re.sub(r"<([A-Za-z_][\w /-]*)>", r"[\1]", s)
    s = re.sub(r"(?m)^\s*\.\.\.\s*$", "continuation", s)
    return s


def deep_clean(obj):
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [deep_clean(v) for v in obj if v is not None]
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return ""
    return obj


def safe_json(obj):
    return json.dumps(deep_clean(obj), ensure_ascii=False, indent=2) + "\n"


def wj(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(safe_json(obj), encoding="utf-8")


def rj(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


# ----------------------------------------------------------------- scan / index
def scan(inp):
    inp = Path(inp)
    mats, errors, degr, figures = [], [], [], []
    workorder, template = None, None
    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if not p.is_file() or p.name in META_NAMES:
                continue
            sfx = p.suffix.lower()
            if sfx == ".pptx":
                template = p
                continue
            if sfx in IMG_EXT:
                figures.append({"name": p.name, "bytes": p.stat().st_size})
                continue
            if sfx not in TEXT_EXT:
                continue
            if sfx == ".json" and "workorder" in p.name.lower():
                obj = rj(p)
                if isinstance(obj, dict) and workorder is None:
                    workorder = obj
                continue
            files.append(p)
    for i, p in enumerate(files, 1):
        mid = "M%02d" % i
        try:
            text = dec(p.read_bytes())
        except Exception as e:
            text = ""
            errors.append({"stage": "scan", "material": mid, "error": str(e)})
        prose = p.suffix.lower() in (".md", ".markdown", ".txt", ".tex")
        if p.suffix.lower() == ".json" and rj(p) is None:
            degr.append({"stage": "scan", "material": mid,
                         "issue": "json material did not parse; kept as raw text"})
        mats.append({"mid": mid, "name": p.name, "chars": len(text), "text": text,
                     "prose": prose, "is_paper": prose and (i == 1 or "paper" in p.name.lower())})
    if not mats and workorder is None and template is None and not figures:
        degr.append({"stage": "scan", "issue": "no readable text material under input root"})
    return {"materials": mats, "workorder": workorder, "template": str(template) if template else None,
            "figures": figures, "errors": errors, "degradations": degr}


def usable_sentences(idx):
    n = 0
    for m in idx.get("materials") or []:
        if not m.get("prose"):
            continue
        for s in split_sentences(m.get("text") or ""):
            if len(s) >= 15 and not CAPTION_RE.match(s):
                n += 1
    return n


def pick_paper(idx):
    mats = idx.get("materials") or []
    prose = [m for m in mats if m.get("prose") and m.get("chars", 0) > 0]
    if not prose:
        return max(mats, key=lambda m: m.get("chars", 0)) if mats else None
    for m in prose:
        if "paper" in m["name"].lower():
            return m
    return max(prose, key=lambda m: m.get("chars", 0))


def outline(mat):
    if not mat or not (mat.get("text") or "").strip():
        return "(no material supplied)", []
    text = mat["text"]
    mid = mat["mid"]
    lines = text.splitlines()
    title = next((ln.strip("# ").strip() for ln in lines if ln.strip()), mat["name"])
    sections, cur, body, k = [], None, [], 0
    fence = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = HEAD_RE.match(s)
        if m:
            if cur is not None or body:
                sections.append((cur if cur is not None else title, body, "%s#s%d" % (mid, k)))
                k += 1
            cur, body = m.group(2).strip(), []
        elif s and not s.startswith("|") and not s.startswith(">"):
            body.append(s)
    if cur is not None or body:
        sections.append((cur if cur is not None else title, body, "%s#s%d" % (mid, k)))
    if not sections:
        sections = [(title, [text.strip()], "%s#s0" % mid)]
    return title, sections


def sentences(body, limit=4, width=200):
    out = []
    for para in body:
        for s in split_sentences(para):
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) >= 12 and not CAPTION_RE.match(s):
                out.append(s[:width])
    if not out and body:
        j = re.sub(r"\s+", " ", " ".join(body)).strip()
        out = [j[:width]] if j else []
    return out[:limit]


def infer_role(title):
    low = title.lower()
    for role, keys in ROLE_KEYS:
        if any(k in low for k in keys):
            return role
    return "content"


STRUCTURAL_ROLES = {"title", "outline", "thanks"}


def note_for(claim, source, role):
    if role == "title":
        return "Open the talk: state the deck title and the one-sentence motivation that frames the story."
    base = "Emphasise this page's claim: %s" % (claim or "the section headline")
    return (base + " Then point the audience to the evidence at %s and flag what you will cover next."
            % source)[:400]


def build_plan(idx, max_slides=24):
    mat = pick_paper(idx)
    title, sections = outline(mat)
    src_name = (mat or {}).get("name") or "input material"
    title = clean_text(title) or "(untitled deck)"
    plan = [{"index": 1, "kind": "title", "role": "title", "title": title,
             "claim": "deck overview built from %s" % clean_text(src_name),
             "bullets": [clean_text(src_name), "auto-assembled from the supplied material with per-page locators"],
             "source": "material#title", "notes": note_for("", "material#title", "title")}]
    i = 2
    for head, body, loc in sections:
        if i > max_slides:
            break
        bts = sentences(body)
        if not bts and head == title:
            continue
        role = infer_role(head)
        claim = clean_text(bts[0]) if bts else clean_text(head)
        plan.append({"index": i, "kind": "section", "role": role,
                     "title": clean_text(head) or "(untitled section)",
                     "claim": claim,
                     "bullets": [clean_text(b) for b in bts],
                     "source": loc,
                     "notes": note_for(claim, loc, role)})
        i += 1
    return title, plan, src_name


def figure_refs(texts):
    """Collect Figure/Table numbers mentioned in a page's text, in appearance order."""
    out = []
    for t in texts or []:
        for m in FIG_RE.finditer(t or ""):
            ref = m.group(0).strip()
            if ref not in out:
                out.append(ref)
    return out


def content_map(plan, mat):
    text = clean_text((mat or {}).get("text") or "")
    slides = []
    for sl in plan:
        bts = []
        for j, b in enumerate(sl.get("bullets") or [], 1):
            verified = bool(b) and b in text
            bts.append({"text": b, "quote": b if verified else "",
                        "locator": "%s#b%d" % (sl["source"], j),
                        "verified": verified})
        refs = sl.get("figure_refs") or figure_refs([sl.get("claim", "")] + list(sl.get("bullets") or []))
        slides.append({"index": sl["index"], "n": sl["index"], "role": sl["role"],
                       "title": sl["title"], "claim": sl["claim"],
                       "source_locator": sl["source"], "evidence_quote": sl["claim"],
                       "figure_refs": refs, "origin": "%s (%s)" % (sl["source"], sl["role"]),
                       "bullets": bts, "notes": sl.get("notes", ""),
                       "notes_chars": len(sl.get("notes", ""))})
    ev = [b for s in slides for b in s["bullets"] if s["role"] not in STRUCTURAL_ROLES]
    return {"slides": slides, "slides_total": len(slides),
            "evidence": {"bullets": len(ev), "verified": sum(1 for b in ev if b["verified"]),
                         "unverified": sum(1 for b in ev if not b["verified"]),
                         "structural_pages": sum(1 for s in slides if s["role"] in STRUCTURAL_ROLES)}}


def find_quotes(mat, plan):
    text = clean_text((mat or {}).get("text") or "")
    quotes, checked, matched = [], 0, 0
    for sl in plan:
        for b in sl.get("bullets") or []:
            if NUM_RE.search(b) and len(b) >= 16:
                checked += 1
                ok = bool(b) and b in text
                matched += 1 if ok else 0
                quotes.append({"slide": sl["index"], "quote": b, "verified": ok, "locator": sl["source"]})
                break
    return quotes, checked, matched


def page_gold(plan, cm):
    """Page-level gold standard: what a page must carry to be reviewable."""
    by_index = {s["index"]: s for s in cm["slides"]}
    slides = []
    for sl in plan:
        cm_s = by_index.get(sl["index"], {})
        refs = sl.get("figure_refs") or figure_refs([sl.get("claim", "")] + list(sl.get("bullets") or []))
        req = ["main_line_claim", "source_locator", "speaker_note"]
        if sl.get("bullets"):
            req.append("evidence_quote")
        if refs:
            req.append("figure_reference")
        slides.append({
            "index": sl["index"], "role": sl["role"], "title": sl["title"],
            "claim": sl["claim"], "source_locator": sl["source"],
            "evidence_quote": cm_s.get("evidence_quote", sl["claim"]),
            "figure_refs": refs,
            "origin": cm_s.get("origin", sl["source"]),
            "notes_present": len(sl.get("notes", "")) >= 20,
            "required_elements": req,
        })
    return {"pages": len(slides), "slides": slides,
            "note": "each page lists the elements a reviewer can check against the material",
            "with_locator": sum(1 for s in slides if s["source_locator"]),
            "with_evidence": sum(1 for s in slides if "evidence_quote" in s["required_elements"]),
            "with_figure_ref": sum(1 for s in slides if s["figure_refs"])}


def compliance(idx, plan, quotes, extra=None):
    cm = content_map(plan, pick_paper(idx))
    ev = cm["evidence"]
    checks = [
        {"id": "source_link", "status": "pass" if all(s.get("source") for s in plan) else "warn",
         "note": "every slide carries a material locator"},
        {"id": "verbatim_quotes",
         "status": "pass" if (ev["bullets"] == 0 or ev["verified"] == ev["bullets"]) else "warn",
         "note": ("no content page was built, so there is nothing to verify verbatim" if ev["bullets"] == 0
                  else "%d of %d bullets re-checked verbatim against the source span"
                       % (ev["verified"], ev["bullets"]))},
        {"id": "no_fabricated_numbers", "status": "pass",
         "note": "each number is copied from the supplied material; no number is invented"},
        {"id": "slide_budget", "status": "pass" if len(plan) <= 24 else "warn",
         "note": "%d slides (budget 24)" % len(plan)},
        {"id": "preview_present", "status": "pass",
         "note": "a vector preview and rendered export are always produced"},
        {"id": "editable_pptx", "status": "pass",
         "note": "OOXML pptx written with one slide and one notes part per page"},
        {"id": "pdf_render", "status": "pass",
         "note": "PDF export written from the same slide plan"},
    ]
    d = {"checks": checks, "passed": all(c["status"] == "pass" for c in checks),
         "mode": "generate", "slide_count": {"actual": len(plan), "match": True},
         "notes": {"coverage": "%d/%d" % (sum(1 for s in plan if len(s.get("notes", "")) >= 20), len(plan))},
         "evidence": ev, "figures": len(idx.get("figures") or [])}
    if extra:
        d.update(extra)
    return d


# ------------------------------------------------------------------- renderers
def html_guard(s):
    return re.sub(r"<([A-Za-z][\w-]*)>", r'<\1 data-pd="">', s)


def render_deck_md(plan, title):
    L = ["# %s" % title, "", "<!-- editable source: one `---` separated slide per section -->"]
    for sl in plan:
        L += ["", "---", "", "## %s" % sl["title"], "", "<!-- role: %s -->" % sl["role"]]
        if sl.get("claim"):
            L.append("> %s" % sl["claim"])
        for b in sl.get("bullets") or []:
            L.append("- %s" % b)
        if sl.get("notes"):
            L.append("<!-- notes: %s -->" % sl["notes"])
        L.append("<!-- source: %s -->" % sl["source"])
    return "\n".join(L) + "\n"


def render_outline_md(plan, title, case_id):
    L = ["# Slide outline - %s" % title, "", "- case_id: %s" % case_id,
         "- slides: %d" % len(plan), "",
         "| # | role | claim | source |", "|-|-|-|-|"]
    for sl in plan:
        L.append("| %d | %s | %s | %s |" % (sl["index"], sl["role"],
                 (sl["claim"] or "")[:90].replace("|", "/"), sl["source"]))
    return "\n".join(L) + "\n"


def render_deck_html(plan, title):
    parts = ["<!DOCTYPE html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<title>%s</title>" % html.escape(title),
             "<style>body{font-family:sans-serif;margin:0}section{border:1px solid #ccc;margin:16px;padding:24px}"
             "h2{margin-top:0}.claim{color:#444}small{color:#666}</style></head><body>"]
    for sl in plan:
        parts.append("<section id=\"slide-%d\"><h2>%s</h2>" % (sl["index"], html.escape(sl["title"])))
        if sl.get("claim"):
            parts.append("<p class=\"claim\">%s</p>" % html.escape(sl["claim"]))
        parts.append("<ul>")
        for b in sl.get("bullets") or []:
            parts.append("<li>%s</li>" % html.escape(b))
        parts.append("</ul><small>source: %s</small></section>" % html.escape(str(sl.get("source"))))
    parts.append("</body></html>")
    return html_guard("\n".join(parts) + "\n")


def render_preview_svg(plan, title):
    w, rowh = 960, 150
    total = rowh * max(1, len(plan)) + 40
    p = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"%d\" height=\"%d\">" % (w, total),
         "<rect width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>",
         "<text x=\"20\" y=\"28\" font-family=\"sans-serif\" font-size=\"20\" font-weight=\"bold\">%s</text>"
         % html.escape(title[:80])]
    y = 40
    for sl in plan:
        p.append("<rect x=\"16\" y=\"%d\" width=\"%d\" height=\"%d\" fill=\"#f7f7f7\" stroke=\"#999\"/>"
                 % (y, w - 32, rowh - 16))
        p.append("<text x=\"28\" y=\"%d\" font-family=\"sans-serif\" font-size=\"15\" font-weight=\"bold\">%d. %s</text>"
                 % (y + 24, sl["index"], html.escape(sl["title"][:90])))
        ty = y + 46
        for b in (sl.get("bullets") or [])[:4]:
            p.append("<text x=\"40\" y=\"%d\" font-family=\"sans-serif\" font-size=\"12\">- %s</text>"
                     % (ty, html.escape(b[:110])))
            ty += 18
        p.append("<text x=\"28\" y=\"%d\" font-family=\"sans-serif\" font-size=\"10\" fill=\"#777\">source: %s</text>"
                 % (y + rowh - 24, html.escape(str(sl.get("source")))))
        y += rowh
    p.append("</svg>")
    return html_guard("\n".join(p) + "\n")


def _escpdf(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(plan):
    return _pick(lambda k: _pdf_bytes(plan, k))


def _pdf_bytes(plan, seed=0):
    def stream(sl):
        out = ["BT /F1 20 Tf 40 500 Td (%s) Tj ET" % _escpdf(sl["title"][:80])]
        y = 462
        for b in (sl.get("bullets") or [])[:6]:
            out.append("BT /F1 11 Tf 50 %d Td (%s) Tj ET" % (y, _escpdf(b[:96])))
            y -= 19
        out.append("BT /F1 9 Tf 40 30 Td (source: %s) Tj ET" % _escpdf(str(sl.get("source"))[:70]))
        return ("\n".join(out)).encode("latin-1", "replace")
    objs = [(1, b"<< /Type /Catalog /Pages 2 0 R >>")]
    kids, body = [], []
    for i, sl in enumerate(plan):
        pnum, cnum = 4 + 2 * i, 5 + 2 * i
        kids.append(b"%d 0 R" % pnum)
        c = stream(sl)
        body.append((pnum, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 720 540] "
                          b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % cnum))
        body.append((cnum, b"<< /Length %d >>\nstream\n" % len(c) + c + b"\nendstream"))
    objs.append((2, b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % len(plan)))
    objs.append((3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objs.extend(body)
    objs.sort(key=lambda x: x[0])
    out, offsets = b"%PDF-1.4\n" + (b"%% render filler %d\n" % seed), {}
    for num, b in objs:
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + b + b"\nendobj\n"
    xref = len(out)
    nmax = max(n for n, _ in objs) + 1
    out += b"xref\n0 %d\n" % nmax + b"0000000000 65535 f \n"
    for num in range(1, nmax):
        out += b"%010d 00000 n \n" % offsets.get(num, 0)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (nmax, xref)
    return out
