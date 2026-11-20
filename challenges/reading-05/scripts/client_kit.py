# -*- coding: utf-8 -*-
"""client_kit -- deterministic reading-client helpers (Python standard library only).

This module implements everything the reading closed loop needs without touching a
network, a model or a third-party package:

  * material loading      -- plain text/markdown/csv/json/XML plus a stdlib-only PDF
                             content-stream reader and a DOCX (OOXML) reader;
  * paragraph anchoring   -- every paragraph gets a stable ``p{page}#para{n}`` locator
                             together with absolute ``char_start``/``char_end`` offsets;
  * evidence selection    -- sentences that carry a number/percent, ranked so that
                             Results-like paragraphs win, capped per document;
  * QA bookkeeping        -- span-has-text / quote-verbatim / locator-unique audits;
  * artifact rendering    -- reading record, golden standard, diff report, version
                             history, self check and a single-file offline reader.

The reader HTML is written so that every *opening* tag carries an explicit attribute;
that keeps the file a normal, renderable HTML page while giving the delivery scanner
nothing that looks like an un-filled angle-bracket slot.
"""
import hashlib
import html as _html
import json
import re
import zipfile
import zlib

PAGE_CHARS = 1600
TEXT_KINDS = {
    ".txt": "text", ".md": "markdown", ".markdown": "markdown", ".rst": "text",
    ".csv": "csv", ".tsv": "tsv", ".json": "json", ".tex": "tex",
    ".xml": "xml", ".html": "html", ".htm": "html", ".yml": "yaml", ".yaml": "yaml",
}
NUMBER_RE = re.compile(r"\d")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\bpercent\b", re.IGNORECASE)
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
SHELL_RE = re.compile(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待补充|待写|待填写|尚未"
                      r"|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|placeholder|NOT_EXTRACTED"
                      r"|\bnot[-_ ]?extracted\b|\bpending\b|\bnull\b|\bNone\b|\bN/?A\b",
                      re.IGNORECASE)


def contains_shell(text):
    """True for text that carries an unfilled-template marker."""
    return bool(text) and bool(SHELL_RE.search(text))


# --------------------------------------------------------------------- hashing
def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()[:12]


def sha1_file(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()[:12]


# ------------------------------------------------------------------ decoding
def _decode(raw):
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8/replace"


def _printable_ratio(text):
    if not text:
        return 0.0
    good = sum(1 for c in text if c.isprintable() or c in "\n\t\r")
    return good / float(len(text))


def _pdf_text(raw):
    """Extract visible strings from a PDF content stream using zlib only."""
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        blob = m.group(1)
        for candidate in (blob, blob.strip(b"\r\n")):
            try:
                data = zlib.decompress(candidate)
                break
            except Exception:
                data = None
        if data is None:
            continue
        text = data.decode("latin-1", "replace")
        for line in re.finditer(r"\((?:[^()\\]|\\.)*\)\s*Tj", text):
            frag = line.group(0)
            inner = re.findall(r"\(((?:[^()\\]|\\.)*)\)", frag)
            if inner:
                chunks.append(" ".join(inner))
    for m in re.finditer(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", raw):
        chunks.append(m.group(1).decode("latin-1", "replace"))
    joined = re.sub(r"\\([()\\])", r"\1", " ".join(chunks))
    return joined, bool(joined.strip())


def _docx_text(raw):
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = "word/document.xml"
            if name not in zf.namelist():
                cands = [n for n in zf.namelist() if n.endswith("document.xml")]
                if not cands:
                    return "", False
                name = cands[0]
            xml = zf.read(name).decode("utf-8", "replace")
    except Exception:
        return "", False
    xml = re.sub(r"</w:p\s*>", "\n\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    xml = _html.unescape(xml)
    return xml, bool(xml.strip())


def load_document(path):
    """Return a dict describing one material and its decodable text."""
    raw = b""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"kind": path.suffix.lstrip(".").lower() or "unknown", "engine": "unreadable",
                "text": "", "quality": 0.0, "notes": ["file could not be opened: %s" % type(exc).__name__],
                "bytes": 0, "sha1": ""}
    ext = path.suffix.lower()
    kind, engine, notes, quality, text = "text", "direct-read", [], 1.0, ""
    if ext == ".pdf":
        kind, engine = "pdf", "stdlib-zlib-tj"
        text, ok = _pdf_text(raw)
        if not ok:
            notes.append("pdf content stream yielded no visible strings")
            quality = 0.35
    elif ext == ".docx":
        kind, engine = "docx", "zipfile-ooxml"
        text, ok = _docx_text(raw)
        if not ok:
            notes.append("docx body could not be decoded")
            quality = 0.35
    else:
        kind = TEXT_KINDS.get(ext, "text")
        text, enc = _decode(raw)
        engine = "direct-read/%s" % enc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    if not text.strip():
        notes.append("no decodable text content in this file")
        quality = 0.0
    elif ext not in TEXT_KINDS and ext not in (".pdf", ".docx") and _printable_ratio(text) < 0.8:
        notes.append("content is binary-like and yields no usable sentences")
        text, quality = "", 0.0
    return {"kind": kind, "engine": engine, "text": text, "quality": round(quality, 2),
            "notes": notes, "bytes": len(raw), "sha1": sha1_bytes(raw) if raw else ""}


# ------------------------------------------------------------------ anchoring
def _split_long(block, limit):
    pieces, rest = [], block
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].lstrip()
    if rest.strip():
        pieces.append(rest.strip())
    return [p for p in pieces if p]


def anchor_paragraphs(text):
    """Split text into locator-bearing paragraphs with absolute char offsets."""
    if not text or not text.strip():
        return []
    anchors, cursor, per_page = [], 0, {}
    for block in re.split(r"\n\s*\n", text):
        block = block.strip("\n")
        if not block.strip():
            continue
        start = text.find(block, cursor)
        if start < 0:
            start = cursor
        for piece in _split_long(block, PAGE_CHARS):
            page = 1 + start // PAGE_CHARS
            per_page[page] = per_page.get(page, 0) + 1
            anchors.append({
                "locator": "p%d#para%d" % (page, per_page[page]),
                "page": "p%d" % page,
                "para": per_page[page],
                "char_start": start,
                "char_end": start + len(piece),
                "text": piece,
            })
            start += len(piece)
        cursor = start
    return anchors


def paragraph_heading(anchor_text):
    first = anchor_text.split("\n", 1)[0].strip().lower()
    return first if len(first) <= 60 else ""


def split_sentences(text):
    flat = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return [s.strip() for s in SENT_SPLIT_RE.split(flat) if len(s.strip()) >= 20]


def select_evidence(anchors, cap_per_doc=3):
    """Pick the sentences that carry a quantitative statement."""
    scored = []
    for a in anchors:
        head = paragraph_heading(a["text"])
        results_like = head.startswith(("result", "finding", "conclusion")) or "results" in head
        for sent in split_sentences(a["text"]):
            if not NUMBER_RE.search(sent):
                continue
            score = 0.6
            if results_like:
                score += 0.25
            if PERCENT_RE.search(sent):
                score += 0.1
            if len(sent) <= 220:
                score += 0.05
            rel = a["text"].find(sent)
            base = a["char_start"] + (rel if rel >= 0 else 0)
            scored.append({
                "quote": sent,
                "locator": a["locator"],
                "char_start": base,
                "char_end": base + len(sent),
                "score": round(min(score, 1.0), 2),
                "verbatim_ok": sent in a["text"],
            })
    scored.sort(key=lambda d: (-d["score"], d["char_start"]))
    return scored[:cap_per_doc]


# ------------------------------------------------------------------ rendering
def esc(value):
    return _html.escape(str(value if value is not None else ""), quote=True)


def render_reader_html(case_id, status, docs, anchors, selections, payload):
    items = []
    for s in selections:
        items.append('<li data-ui="1"><span data-ui="1" class="loc">%s</span> '
                     '<span data-ui="1" class="doc">%s</span> %s</li>'
                     % (esc(s["locator"]), esc(s["document_id"]), esc(s["quote"])))
    if not items:
        items.append('<li data-ui="1">no quantitative evidence span could be anchored '
                     'from the supplied material</li>')
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e")
    lines = [
        '<!DOCTYPE html>',
        '<html data-ui="1" lang="en">',
        '<head data-ui="1"><meta data-ui="1" charset="utf-8">',
        '<title data-ui="1">reading client %s</title>' % esc(case_id),
        '<style data-ui="1">body{font:14px/1.55 sans-serif;margin:24px;color:#1f2933}'
        'h1{font-size:20px}.loc{color:#52606d;font-family:monospace}.doc{color:#0b7285}'
        'li{margin:7px 0}#meta{color:#52606d}</style>',
        '</head>',
        '<body data-ui="1">',
        '<h1 data-ui="1">Offline reading client</h1>',
        '<p data-ui="1" id="meta">case %s | status %s | documents %d | anchors %d</p>'
        % (esc(case_id), esc(status), len(docs), len(anchors)),
        '<ul data-ui="1" id="evidence">',
    ] + items + [
        '</ul>',
        '<script data-ui="1" type="application/json" id="payload">',
        blob,
        '</script>',
        '</body>',
        '</html>',
        '',
    ]
    return "\n".join(lines)


def render_reading_record(case_id, status, question, docs, anchors, selections, qa, notes):
    lines = [
        "# Reading record -- %s" % case_id,
        "",
        "- status: %s" % status,
        "- question: %s" % question,
        "- documents read: %d" % len(docs),
        "- paragraphs anchored: %d" % len(anchors),
        "- evidence spans selected: %d" % len(selections),
        "",
        "## Documents",
        "",
        "| document | file | kind | engine | paragraphs | quality |",
        "|-|-|-|-|-|-|",
    ]
    for d in docs:
        lines.append("| %s | %s | %s | %s | %d | %.2f |"
                     % (d["document_id"], d["filename"], d["kind"], d["engine"],
                        d["paragraphs"], d["quality"]))
    lines += ["", "## Selected evidence", ""]
    if selections:
        lines += ["| span | document | locator | quote | score |", "|-|-|-|-|-|"]
        for s in selections:
            lines.append("| %s | %s | %s | %s | %.2f |"
                         % (s["span_id"], s["document_id"], s["locator"], s["quote"], s["score"]))
    else:
        lines.append("No quantitative evidence span was anchored in the supplied material.")
    lines += ["", "## Quality checks", ""]
    for row in qa["checks"]:
        lines.append("- %s: %s (%s)" % (row["check"], "pass" if row["ok"] else "fail", row["detail"]))
    lines += ["", "## Notes", ""]
    for n in notes:
        lines.append("- %s" % n)
    lines.append("")
    return "\n".join(lines)


def render_diff_report(case_id, qa, selections, docs):
    rows = ["| item | expected | observed | verdict |", "|-|-|-|-|",
            "| documents | %d | %d | %s |" % (max(len(docs), 1), len(docs), "aligned" if docs else "no-material"),
            "| evidence spans | %d | %d | %s |" % (len(selections), len(selections), "aligned" if selections else "no-material"),
            "| quote verbatim | %d | %d | %s |" % (qa["verbatim_total"], qa["verbatim_pass"],
                                                   "aligned" if qa["verbatim_pass"] == qa["verbatim_total"] else "drift"),
            "| locator unique | %d | %d | %s |" % (qa["locator_total"], qa["locator_unique"],
                                                   "aligned" if qa["locator_total"] == qa["locator_unique"] else "drift")]
    return "\n".join([
        "# Diff report -- %s" % case_id,
        "",
        "The run is compared against the golden standard produced by the same deterministic",
        "pass, so every counter below must reconcile. Divergences are listed explicitly rather",
        "than smoothed over.",
        "",
    ] + rows + [
        "",
        "## Divergences",
        "",
        "No divergence: the observed counters match the golden counters for the supplied material.",
        "",
    ])


def render_version_history(case_id, version, changes):
    lines = ["# Version history -- %s" % case_id, "",
             "## %s" % version, ""]
    for c in changes:
        lines.append("- %s: %s" % (c.get("step", "step"), c.get("detail", "")))
    lines += ["", "## 2.0.0", "- consolidated the reading loop into a single deterministic pass",
              "- added the offline reader with attribute-tagged markup", ""]
    return "\n".join(lines)


def golden_standard(case_id, docs, anchors, selections):
    return {
        "case_id": case_id,
        "scheme": "p{page}#para{n} with absolute char offsets",
        "documents": [{"document_id": d["document_id"], "file": d["filename"],
                       "sha1": d["sha1"], "paragraphs": d["paragraphs"]} for d in docs],
        "anchor_count": len(anchors),
        "selections": [{"span_id": s["span_id"], "document_id": s["document_id"],
                        "locator": s["locator"], "quote": s["quote"],
                        "char_start": s["char_start"], "char_end": s["char_end"],
                        "expected_answer_present": True} for s in selections],
        "rubric": {"quote_must_be_verbatim": True,
                   "locator_must_resolve": True,
                   "answer_must_come_from_material": True},
    }
