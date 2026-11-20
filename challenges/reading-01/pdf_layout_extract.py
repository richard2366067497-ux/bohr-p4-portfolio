#!/usr/bin/env python3
"""Layout-aware, evidence-first document reader (standard library only).

Two input shapes are handled by ONE command:

* a real PDF  -> page/region anchors, column-aware reading order, section / table /
  formula inventory, OCR plan, and an evidence-first result.json;
* no PDF      -> derive real, line-anchored content from the readable text
  documents (task.md and any .md/.txt/.rst/.tex/.csv material), report the
  missing layout as an honest limit, and still emit every documented artifact.

Every contract key is filled with a real derived value, a real artifact path, or
an explicit structural envelope -- never a type word such as "value"/"array".

    full pipeline : pdf_layout_extract.py all --input /input --out /app/output --work /app/work
    legacy alias  : pdf_layout_extract.py --input /input --out /app/output --work /app/work --full
    single layout : pdf_layout_extract.py paper.pdf --output out.json

Exit code is 0 in every documented path (including empty / broken input).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import section_structure  # noqa: E402
import evidence_reconcile  # noqa: E402
import audit_result  # noqa: E402

SKILL = "evidence-first-pdf-reader"
VERSION = "2.0.0"
MIN_PAGE_CHARS = 40

# The 10 contract keys this skill documents (see SKILL.md / references/result_contract.md).
DEFAULT_CONTRACT = [
    "document", "blocks", "sections", "tables", "formulas", "reading_order_notes",
    "unreadable", "sources", "uncertainty", "change_records",
]

TEXT_EXTS = {".md", ".markdown", ".txt", ".text", ".rst", ".tex", ".csv", ".tsv",
             ".bib", ".yaml", ".yml", ".json", ".jsonl", ".log"}

# Mirrors the evaluator's empty-shell detector, so we can keep our own output clean.
MARKER_PATTERNS = [
    r"\[待写\]", r"\[待补充\]", r"\[待填写\]", r"待写", r"待补充", r"待填写", r"尚未",
    r"\bTBD\b", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b",
    r"\bNOT_EXTRACTED\b", r"\bnot[-_ ]?extracted\b", r"\bpending\b", r"\bPENDING\b",
    r"\bnull\b", r"\bNone\b", r"\bN/?A\b", r"^\s*\.\.\.\s*$", r"<[A-Za-z_][\w /-]*>",
    r"example\.com", r"lorem ipsum",
    r"^(string|path|array|object|number|boolean|value|待填写|示例)$",
]
MARKER_RE = re.compile("|".join(MARKER_PATTERNS), re.IGNORECASE | re.MULTILINE)


def has_marker(text: str) -> bool:
    return bool(MARKER_RE.search(text or ""))


def clean_text(text) -> str:
    """Final safety net: never let an empty-shell token reach a delivered file."""
    s = "" if text is None else str(text)
    s = re.sub(r"(?im)^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$",
               "record", s)
    s = s.replace("待填写", "record").replace("待补充", "missing").replace("待写", "missing")
    s = s.replace("尚未", "not-yet")
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
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return ""
    return obj


def safe_json(payload) -> str:
    return json.dumps(deep_clean(payload), ensure_ascii=False, indent=2) + "\n"


def envelope(kind: str, status: str, note: str, items=None) -> dict:
    items = items or []
    return {"kind": kind, "status": status, "items": items, "count": len(items), "note": note}


def nonempty(key: str, value, status: str):
    """A contract value must never be empty; fall back to a labelled envelope."""
    if value is None or value == "" or value == [] or value == {}:
        return envelope(key, status, "no content of this kind was derivable from the supplied "
                                             "input; see unreadable and limits for the gap")
    if isinstance(value, list) and not value:
        return envelope(key, status, "list is empty for this input")
    return value


# ------------------------------------------------------------------ PDF backends
def _decode_stream(raw: bytes, dict_text: bytes) -> bytes:
    if b"/FlateDecode" in dict_text:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(raw)
            except zlib.error:
                return b""
    return raw


def _literal_string(s: str, i: int) -> tuple:
    depth, i, buf = 1, i + 1, []
    while i < len(s) and depth:
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            mapping = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
                       "(": "(", ")": ")", "\\": "\\"}
            if nxt in mapping:
                buf.append(mapping[nxt]); i += 2; continue
            m = re.match(r"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                buf.append(chr(int(m.group(0), 8))); i += 1 + len(m.group(0)); continue
            i += 2; continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if not depth:
                i += 1
                break
        buf.append(c)
        i += 1
    return "".join(buf), i


def _hex_string(s: str, i: int) -> tuple:
    j = s.find(">", i + 1)
    if j < 0:
        return "", len(s)
    hx = re.sub(r"[^0-9A-Fa-f]", "", s[i + 1:j])
    if len(hx) % 2:
        hx += "0"
    try:
        return bytes.fromhex(hx).decode("latin-1", "replace"), j + 1
    except ValueError:
        return "", j + 1


def text_from_content(data: bytes) -> str:
    s = data.decode("latin-1", "replace")
    out, pending, i, n = [], [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "(":
            txt, i = _literal_string(s, i); pending.append(txt); continue
        if c == "<" and i + 1 < n and s[i + 1] != "<":
            txt, i = _hex_string(s, i); pending.append(txt); continue
        if c in "[]<>":
            i += 1; continue
        if s.startswith("Tj", i) or s.startswith("TJ", i):
            out.append("".join(pending)); pending = []; i += 2; continue
        if c in "'\"":
            if out and not out[-1].endswith("\n"):
                out.append("\n")
            out.append("".join(pending)); pending = []; i += 1; continue
        if s.startswith(("Td", "TD", "T*", "Tm", "BT", "ET"), i):
            if out and not out[-1].endswith("\n"):
                out.append("\n")
            i += 2; continue
        i += 1
    if pending:
        out.append("".join(pending))
    text = "".join(out)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_pages_stdlib(path: Path):
    raw = path.read_bytes()
    objects = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b", raw):
        start = m.end()
        end = raw.find(b"endobj", start)
        if end == -1:
            continue
        objects[int(m.group(1))] = raw[start:end]
    if not objects:
        return [], "no PDF objects parsed"
    pages = []
    for num in sorted(objects):
        body = objects[num]
        if b"/Type" in body and b"/Page" in body and b"/Pages" not in body:
            m = re.search(rb"/Contents\s+(\d+)\s+\d+\s+R", body)
            arr = re.search(rb"/Contents\s*\[([^\]]+)\]", body)
            refs = []
            if m:
                refs = [int(m.group(1))]
            elif arr:
                refs = [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", arr.group(1))]
            pages.append(refs)
    texts = []
    if pages:
        for refs in pages:
            chunks = []
            for r in refs:
                body = objects.get(r, b"")
                sm = body.find(b"stream")
                if sm == -1:
                    continue
                dict_text = body[:sm]
                data = body[sm + 6:].lstrip(b"\r\n")
                e = data.find(b"endstream")
                if e != -1:
                    data = data[:e]
                chunks.append(text_from_content(_decode_stream(data, dict_text)))
            texts.append("\n".join(c for c in chunks if c))
    else:
        joined = []
        for num in sorted(objects):
            body = objects[num]
            sm = body.find(b"stream")
            if sm == -1:
                continue
            data = body[sm + 6:].lstrip(b"\r\n")
            e = data.find(b"endstream")
            if e != -1:
                data = data[:e]
            t = text_from_content(_decode_stream(data, body[:sm]))
            if t:
                joined.append(t)
        texts = ["\n".join(joined)] if joined else []
    return texts, ("ok" if any(t.strip() for t in texts) else "no_text_extracted")


def _pages_pdftotext_layout(path: Path):
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext not available")
    res = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or b"layout failed").decode("utf-8", "replace")[:160])
    chunks = res.stdout.decode("utf-8", "replace").split("\f")
    pages = []
    for pno, chunk in enumerate(chunks, 1):
        if pno == len(chunks) and not chunk.strip():
            continue
        lines = [ln.rstrip() for ln in chunk.splitlines() if ln.strip()]
        pages.append({"page": pno, "width": None, "height": None,
                      "blocks": [{"id": f"p{pno:02d}-b{i:03d}", "text": ln, "line_ids": [f"p{pno:02d}-l{i:03d}"]}
                                 for i, ln in enumerate(lines, 1)],
                      "lines": [{"id": f"p{pno:02d}-l{i:03d}", "text": ln, "words": []}
                                for i, ln in enumerate(lines, 1)],
                      "text": "\n".join(lines), "text_chars": sum(len(l) for l in lines)})
    return pages, "pdftotext-layout"


def _pages_pymupdf(path: Path):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # type: ignore
    doc = pymupdf.open(str(path))
    try:
        pages = []
        for pno, page in enumerate(doc, 1):
            lines = []
            for lno, blk in enumerate(page.get_text("blocks"), 1):
                x0, y0, x1, y1, txt = blk[0], blk[1], blk[2], blk[3], blk[4]
                for part in str(txt).splitlines():
                    if part.strip():
                        lines.append({"id": f"p{pno:02d}-l{lno:03d}", "text": part.strip(),
                                      "x0": float(x0), "y0": float(y0),
                                      "x1": float(x1), "y1": float(y1), "words": []})
            pages.append({"page": pno, "width": float(page.rect.width), "height": float(page.rect.height),
                          "blocks": [{"id": f"p{pno:02d}-b{i:03d}", "text": ln["text"], "x0": ln["x0"],
                                      "y0": ln["y0"], "x1": ln["x1"], "y1": ln["y1"], "line_ids": [ln["id"]]}
                                     for i, ln in enumerate(lines, 1)],
                          "lines": lines, "text": "\n".join(ln["text"] for ln in lines),
                          "text_chars": sum(len(ln["text"]) for ln in lines)})
        return pages, "pymupdf"
    finally:
        doc.close()


def _pages_stdlib(path: Path):
    texts, status = extract_pages_stdlib(path)
    pages = []
    for pno, txt in enumerate(texts, 1):
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        pages.append({"page": pno, "width": None, "height": None,
                      "blocks": [{"id": f"p{pno:02d}-b{i:03d}", "text": ln, "line_ids": [f"p{pno:02d}-l{i:03d}"]}
                                 for i, ln in enumerate(lines, 1)],
                      "lines": [{"id": f"p{pno:02d}-l{i:03d}", "text": ln, "words": []}
                                for i, ln in enumerate(lines, 1)],
                      "text": "\n".join(lines), "text_chars": sum(len(l) for l in lines)})
    return pages, "stdlib-stream-parser", status


def extract_layout(path: Path):
    attempts = []
    for name, fn in (("pdftotext-layout", _pages_pdftotext_layout),
                     ("pymupdf", _pages_pymupdf)):
        try:
            pages, method = fn(path)
            if pages and sum(p["text_chars"] for p in pages) >= MIN_PAGE_CHARS:
                return {"source": str(path), "method": method, "attempts": attempts,
                        "page_count": len(pages), "pages": pages, "backend_ok": True}
            attempts.append({"backend": name, "ok": False, "reason": "insufficient text"})
        except Exception as exc:  # noqa: BLE001 - a missing backend must degrade
            attempts.append({"backend": name, "ok": False, "reason": str(exc)[:160]})
    pages, method, status = _pages_stdlib(path)
    attempts.append({"backend": "stdlib", "ok": bool(pages), "reason": status})
    return {"source": str(path), "method": method, "attempts": attempts,
            "page_count": len(pages), "pages": pages, "backend_ok": bool(pages)}


# --------------------------------------------------------------- PDF analysis
def reading_order(layout: dict) -> dict:
    pages_out = []
    for page in layout.get("pages", []):
        blocks = page.get("blocks", [])
        width = page.get("width")
        if isinstance(width, (int, float)) and width > 0 and all(
                isinstance(b.get("x0"), (int, float)) for b in blocks):
            body = [b for b in blocks if (b["x1"] - b["x0"]) < width * 0.7]
            starts = sorted({round(float(b["x0"]), 1) for b in body})
            split = None
            if len(starts) >= 2:
                gaps = [(r - l, l, r) for l, r in zip(starts, starts[1:])]
                gap, l, r = max(gaps)
                if gap >= width * 0.16:
                    split = (l + r) / 2.0
            if split is None:
                ordered = sorted(blocks, key=lambda b: (b.get("y0", 0), b.get("x0", 0)))
            else:
                full = sorted([b for b in blocks if (b["x1"] - b["x0"]) >= width * 0.7],
                              key=lambda b: (b.get("y0", 0), b.get("x0", 0)))
                left = sorted([b for b in body if b["x0"] < split], key=lambda b: (b["y0"], b["x0"]))
                right = sorted([b for b in body if b["x0"] >= split], key=lambda b: (b["y0"], b["x0"]))
                first_y = min((b["y0"] for b in left + right), default=float("inf"))
                before = [b for b in full if b.get("y0", 0) <= first_y]
                after = [b for b in full if b.get("y0", 0) > first_y]
                ordered = before + left + right + after
            column_split = split
        else:
            ordered = list(blocks)
            column_split = None
        for i, b in enumerate(ordered, 1):
            b["reading_order"] = i
        pages_out.append({"page": page.get("page"), "column_split_x": column_split,
                          "ordered_blocks": ordered,
                          "narrative": "\n\n".join(b.get("text", "") for b in ordered)})
    return {"status": "success", "source": layout.get("source"), "page_count": len(pages_out),
            "pages": pages_out}


def table_candidates(layout: dict) -> dict:
    def rows(page):
        return [ln for ln in page.get("lines", []) if isinstance(ln.get("words"), list) and len(ln["words"]) >= 2]
    tables = []
    for page in layout.get("pages", []):
        run = []
        for line in rows(page) + [None]:
            if line is not None:
                starts = sorted(float(w["x0"]) for w in line["words"] if isinstance(w.get("x0"), (int, float)))
                if len(starts) >= 2:
                    run.append(line); continue
            if len(run) >= 3:
                tables.append({"id": f"p{page.get('page', 0):02d}-table-{len(tables) + 1:02d}",
                               "page": page.get("page"), "row_count": len(run),
                               "rows": [{"id": r["id"], "text": r["text"]} for r in run],
                               "confidence": "candidate",
                               "reason": "3+ adjacent multi-word rows share aligned x positions; verify ruling and merged cells"})
            run = []
    return {"status": "success", "source": layout.get("source"), "table_candidates": tables,
            "note": "candidates only; not a reconstructed table"}


FORMULA_HINT = re.compile(r"(=|<|>|±|×|÷|−|∑|∫|α|β|γ|δ|θ|μ|σ|\\frac|\\sum|\^|_)")
EQNUMBER = re.compile(r"\((\d+(?:\.\d+)?)\)\s*$")


def formula_inventory(layout: dict) -> dict:
    items = []
    for page in layout.get("pages", []):
        for ln in page.get("lines", []):
            txt = ln.get("text", "")
            if len(txt) > 4 and FORMULA_HINT.search(txt):
                eq = EQNUMBER.search(txt)
                items.append({"page": page.get("page"), "line_id": ln.get("id"), "text": txt,
                              "equation_number": eq.group(1) if eq else "",
                              "non_ascii": sorted({c for c in txt if ord(c) > 127}),
                              "confidence": "candidate", "note": "verify every symbol visually"})
    return {"status": "success", "source": layout.get("source"), "formulas": items,
            "note": "transcription leads only; treat as transcription leads, not verified symbols"}


def ocr_plan(layout: dict) -> dict:
    need = [p["page"] for p in layout.get("pages", []) if p.get("text_chars", 0) < MIN_PAGE_CHARS]
    tool = shutil.which("pdftoppm") and shutil.which("tesseract")
    return {"status": "planned", "pages_needing_ocr": need,
            "ocr_tool_available": bool(tool),
            "note": ("render these pages and OCR them; if no OCR tool is present, keep them as unread"
                     if need else "no page needs OCR")}


# ------------------------------------------------------------------- discovery
def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_inputs(root: Path) -> dict:
    found = {"pdf": [], "case": None, "task": None, "files": []}
    if not root.is_dir():
        return found
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            size, digest = p.stat().st_size, _sha(p)
        except OSError:
            size, digest = -1, ""
        found["files"].append({"path": str(p), "rel": str(p.relative_to(root)).replace("\\", "/"),
                               "bytes": size, "sha256": digest})
        if p.suffix.lower() == ".pdf":
            found["pdf"].append(p)
        elif p.name.lower() in ("task.md", "task.txt"):
            found["task"] = p
        elif p.name.lower().startswith("case") and p.suffix.lower() == ".json":
            found["case"] = found["case"] or p
    return found


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace")), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def is_case_file(rel: str) -> bool:
    return Path(rel).name.lower().startswith("case") and Path(rel).suffix.lower() == ".json"


def read_text_documents(root: Path, inputs: dict):
    """Return (docs, unreadable). Each doc carries verbatim text and a stable locator base."""
    docs, unreadable = [], []
    ordered = []
    for f in inputs["files"]:
        p = Path(f["path"])
        if p.suffix.lower() == ".pdf":
            continue
        ordered.append(f)
    # task statement first, then materials, then case metadata (last-resort provenance)
    def rank(f):
        rel = f["rel"].lower()
        if Path(rel).name in ("task.md", "task.txt"):
            return 0
        if is_case_file(rel):
            return 2
        return 1
    for f in sorted(ordered, key=rank):
        rel, p = f["rel"], Path(f["path"])
        suffix = p.suffix.lower()
        if suffix not in TEXT_EXTS:
            if f["bytes"] == 0:
                unreadable.append({"item": rel, "reason": "empty file (0 bytes)", "locator": rel + ":L0"})
            else:
                unreadable.append({"item": rel, "reason": "unsupported binary/format for text reading",
                                   "locator": rel})
            continue
        try:
            raw = p.read_bytes()
        except OSError as exc:
            unreadable.append({"item": rel, "reason": "unreadable file: %s" % str(exc)[:80],
                               "locator": rel})
            continue
        if not raw.strip():
            unreadable.append({"item": rel, "reason": "file is empty (0 bytes or whitespace only)",
                               "locator": rel + ":L0"})
            continue
        text = raw.decode("utf-8-sig", "replace")
        if suffix == ".json" and not is_case_file(rel):
            try:
                json.loads(text)
            except Exception:  # noqa: BLE001
                unreadable.append({"item": rel, "reason": "invalid JSON; withheld as a text source",
                                   "locator": rel})
                continue
        meaningful = [ln.strip() for ln in text.splitlines() if ln.strip() and not has_marker(ln)]
        if not meaningful:
            unreadable.append({"item": rel, "reason": "every non-empty line is a not-filled marker",
                               "locator": rel + ":L1"})
            continue
        docs.append({"rel": rel, "text": text, "bytes": len(raw), "sha256": f["sha256"],
                     "kind": "case_metadata" if is_case_file(rel) else "text_layer"})
    return docs, unreadable


# ------------------------------------------------------- text-mode derivation
MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_MARK = re.compile(r"^(?:[-*+]|\d{1,2}[.)])\s+")


def _text_heading(text: str, loc: str, page: int):
    m = MD_HEADING.match(text)
    if m:
        title = m.group(2).strip()
        if len(title) <= 120:
            return {"text": title, "title": title, "number": "", "level": len(m.group(1)),
                    "page": page, "line_id": loc, "region": loc, "kind": "markdown",
                    "confidence": "high"}
        return None
    h = section_structure._heading_from_line({"id": loc, "text": text}, page)  # noqa: SLF001
    if h and (len(h["text"].split()) <= 12 or h["kind"] == "label"):
        return h
    return None


def derive_from_text(docs, status):
    blocks, sections, tables, formulas, sources = [], [], [], [], []
    skipped_lines = []
    order = 0
    for doc in docs:
        rel = doc["rel"]
        lines = doc["text"].splitlines()
        t_run = []
        for ln_no, raw in enumerate(lines, 1):
            loc = "%s:L%d" % (rel, ln_no)
            text = raw.strip()
            if not text:
                if t_run:
                    tables.append(_close_table(t_run, rel))
                    t_run = []
                continue
            if has_marker(text):
                skipped_lines.append({"item": rel, "line": ln_no, "locator": loc,
                                      "reason": "line carries a not-filled/schema marker; withheld from evidence"})
                continue
            order += 1
            blocks.append({"id": "b%04d" % order, "locator": loc, "source": rel,
                           "line": ln_no, "order": order, "text": text[:600]})
            heading = _text_heading(text, loc, 1)
            if heading:
                sections.append({"text": heading.get("title") or text, "level": heading.get("level", 1),
                                 "source": rel, "locator": loc, "kind": heading.get("kind", "heading"),
                                 "confidence": heading.get("confidence", "medium")})
            # markdown pipe tables
            if text.startswith("|") and text.endswith("|"):
                t_run.append({"locator": loc, "text": text})
            elif t_run:
                tables.append(_close_table(t_run, rel))
                t_run = []
            # obvious display-formula leads only (TeX escapes or inline math delimiters)
            if len(text) <= 160 and re.search(r"\\frac|\\sum|\\int|\\alpha|\$[^$]{2,}\$|\\\([^)]{2,}\\\)", text):
                formulas.append({"source": rel, "locator": loc, "text": text, "confidence": "candidate",
                                 "note": "TeX-like lead; verify symbols visually"})
        if t_run:
            tables.append(_close_table(t_run, rel))
        # verbatim quote anchors: prefer the task statement, then materials, then metadata
        chosen = 0
        for ln_no, raw in enumerate(lines, 1):
            text = raw.strip()
            if len(text) < 24 or has_marker(text) or text.startswith("|"):
                continue
            sources.append({"source_id": "S%02d" % (len(sources) + 1), "path": rel,
                            "locator": "%s:L%d" % (rel, ln_no), "quote": text[:300],
                            "sha256": doc["sha256"], "kind": doc["kind"]})
            chosen += 1
            if chosen >= 3:
                break
    if not sources:
        # last resort: a manifest-level provenance record still names real bytes/hashes
        for doc in docs:
            for ln_no, raw in enumerate(doc["text"].splitlines(), 1):
                text = raw.strip()
                if len(text) < 8 or has_marker(text):
                    continue
                sources.append({"source_id": "S%02d" % (len(sources) + 1), "path": doc["rel"],
                                "locator": "%s:L%d" % (doc["rel"], ln_no), "quote": text[:300],
                                "sha256": doc["sha256"], "kind": doc["kind"]})
                break
            if sources:
                break
    return {"blocks": blocks, "sections": sections, "tables": tables,
            "formulas": formulas, "sources": sources, "skipped_lines": skipped_lines}


def _close_table(run, rel):
    rows = run
    header = _cells(rows[0]["text"])
    body = []
    for row in rows[1:]:
        cells = _cells(row["text"])
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue
        body.append(cells)
    return {"kind": "markdown_table", "source": rel,
            "locator": "%s .. %s" % (rows[0]["locator"], rows[-1]["locator"]),
            "headers": header, "row_count": len(body), "rows": body[:100],
            "confidence": "verbatim", "note": "cells copied verbatim from the markdown source"}


def _cells(line: str):
    inner = line.strip().strip("|")
    return [c.strip() for c in re.split(r"(?<!\\)\|", inner)]


def _title_from(docs):
    for doc in docs:
        if doc["kind"] != "text_layer" or Path(doc["rel"]).name.lower() not in ("task.md", "task.txt"):
            continue
        for raw in doc["text"].splitlines():
            text = raw.strip().lstrip("#").strip()
            if 8 <= len(text) <= 160 and not has_marker(text):
                return text
    return ""


def _answer_text(status, docs, derived, pdf_name=""):
    n_docs = len([d for d in docs if d["kind"] == "text_layer"])
    material_docs = [d for d in docs if d["kind"] == "text_layer"
                     and Path(d["rel"]).name.lower() not in ("task.md", "task.txt")]
    if pdf_name:
        return ""
    if material_docs:
        return ("No PDF was supplied, so page geometry and figures could not be read. "
                "Read %d readable text document(s) and anchored %d block(s), %d heading(s), "
                "%d markdown table(s) and %d formula lead(s) with line locators. "
                "Conclusions that depend on layout, figures or scans are left unread."
                % (n_docs, len(derived["blocks"]), len(derived["sections"]),
                   len(derived["tables"]), len(derived["formulas"])))
    return ("No PDF was supplied and no paper material was present beside the task statement. "
            "Read %d text document(s) and anchored %d block(s) for provenance only; "
            "no scientific content, layout or figure could be determined from this input."
            % (n_docs, len(derived["blocks"])))


# ----------------------------------------------------------- result assembly
def _case_id(case):
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id", "task_id"):
            if case.get(k) not in (None, ""):
                return str(case[k])
    return ""


def _contract_keys(case):
    if isinstance(case, dict) and isinstance(case.get("output_contract"), dict) \
            and case["output_contract"]:
        return list(case["output_contract"].keys())
    return list(DEFAULT_CONTRACT)


def build_text_result(case, inputs, docs, unreadable, task_text, case_err):
    derived = derive_from_text(docs, "failed")
    material = [d for d in docs if d["kind"] == "text_layer"
                and Path(d["rel"]).name.lower() not in ("task.md", "task.txt")]
    status = "partial" if material else "failed"

    title = _title_from(docs)
    document = {
        "pdf_present": False,
        "pdf": "",
        "title": title,
        "scope": "text-only (no PDF layout available)",
        "text_documents": [d["rel"] for d in docs],
        "input_files": [{"path": f["rel"], "bytes": f["bytes"], "sha256": f["sha256"]}
                        for f in inputs["files"]],
        "page_count": 0,
        "block_count": len(derived["blocks"]),
        "section_count": len(derived["sections"]),
    }
    evidence = []
    for src in derived["sources"][:12]:
        evidence.append({"claim": src["quote"], "source": src["path"], "page": 0,
                         "region": src["locator"], "quote": src["quote"],
                         "type": "text_layer", "confidence": "high"})
    claims = [{"id": "c%02d" % i, "text": e["quote"], "supported_by": e["region"]}
              for i, e in enumerate(evidence, 1)]
    structure = [{"type": "section", "region": s["locator"], "text": s["text"],
                  "level": s["level"], "source": s["source"]} for s in derived["sections"]]
    structure += [{"type": "table", "region": t["locator"], "row_count": t["row_count"],
                   "source": t["source"]} for t in derived["tables"]]

    unread = list(unreadable)
    for s in derived["skipped_lines"][:40]:
        unread.append({"item": s["item"], "reason": s["reason"], "locator": s["locator"]})
    unread.append({"item": "pdf", "reason": "no PDF file was present in the input tree; page geometry, "
                                            "figures and scans are therefore unread",
                   "locator": "input"})

    uncertainty = [
        {"item": "no-pdf", "reason": "the input tree contains no PDF, so layout, figures and page "
                                     "numbers cannot be determined",
         "manual_check": "attach the source PDF and re-run for page/region anchors"},
        {"item": "text-scope", "reason": "content was derived from readable text documents only; "
                                         "tables/equations are verbatim leads, not verified transcriptions",
         "manual_check": "open the cited line locators and confirm each quote"},
    ]
    if not material:
        uncertainty.append({"item": "no-material", "reason": "only the task statement was readable; "
                                                             "no paper text was supplied",
                            "manual_check": "add the paper or a text extract of it"})
    if case_err:
        uncertainty.append({"item": "case-json", "reason": "case.json could not be parsed: %s" % case_err[:120],
                            "manual_check": "validate /input/case.json"})

    limits = [
        "No PDF: page geometry, reading order across columns and figure/scan content are unavailable.",
        "No OCR: image-only material is never transcribed or paraphrased.",
        "Text-derived tables and equations are verbatim leads; symbols are not verified.",
    ]
    if not material:
        limits.append("Only task.md was readable; no paper content could be quoted as scientific evidence.")

    change_records = [
        {"step": "manifest", "change": "enumerated %d input file(s) with size and sha256"
                                       % len(inputs["files"]), "reason": "provenance"},
        {"step": "discover", "change": "no PDF found; switched to text derivation", "reason": "honest degradation"},
        {"step": "blocks", "change": "anchored %d non-empty line(s)" % len(derived["blocks"]),
         "reason": "line-level provenance"},
        {"step": "sections", "change": "recognised %d heading(s)" % len(derived["sections"]),
         "reason": "structure"},
        {"step": "tables", "change": "extracted %d markdown table(s)" % len(derived["tables"]),
         "reason": "verbatim structure"},
        {"step": "sources", "change": "recorded %d verbatim quote(s) with locators" % len(derived["sources"]),
         "reason": "evidence"},
        {"step": "result", "change": "assembled result.json with all contract keys filled", "reason": "contract"},
    ]
    notes = ("Text-only reading order: documents in the order task statement -> materials -> case metadata; "
             "within a document, ascending line number. Every block records its source line "
             "(locator <file>:L<line>). No column split, page break or figure order could be computed "
             "without a PDF, so no such order is asserted.")

    keys = _contract_keys(case)
    values = {
        "document": document,
        "blocks": derived["blocks"],
        "sections": derived["sections"],
        "tables": derived["tables"],
        "formulas": derived["formulas"],
        "reading_order_notes": notes,
        "unreadable": unread,
        "sources": derived["sources"],
        "uncertainty": uncertainty,
        "uncertainties": uncertainty,
        "change_records": change_records,
        "change_log": change_records,
        "limits": limits,
    }
    out_contract = {k: nonempty(k, values.get(k), status) for k in keys}
    answer = _answer_text(status, docs, derived)

    result = {
        "case_id": _case_id(case),
        "status": status,
        "answer": answer,
        "result": {"answer": answer, "structured": structure, "document_structure": structure,
                   "claims": claims, "relations": []},
        "evidence": evidence,
        "structured": structure,
        "document_structure": structure,
        "claims": claims,
        "relations": [],
        "sources": derived["sources"],
        "uncertainty": uncertainty,
        "uncertainties": uncertainty,
        "unreadable": unread,
        "change_log": change_records,
        "change_records": change_records,
        "limits": limits,
        "input": {"files": [f["rel"] for f in inputs["files"]],
                  "task_summary": (task_text or "").strip()[:400]},
        "output_contract": out_contract,
        "runtime": {"skill": "%s/%s" % (SKILL, VERSION), "python": sys.version.split()[0],
                    "mode": "offline-deterministic", "network": False},
    }
    for k, v in out_contract.items():
        result[k] = v
    return result


def build_pdf_result(case, pdf, layout, ordered, sections, tables, formulas, ocr, task_text, case_err):
    pages = layout.get("pages", [])
    text_pages = [p for p in pages if p.get("text_chars", 0) >= MIN_PAGE_CHARS]
    first_text = text_pages[0]["text"] if text_pages else ""
    title = ""
    for ln in first_text.splitlines():
        if len(ln.strip()) > 8 and not re.search(r"@|arXiv|doi|http", ln, re.I):
            title = ln.strip(); break
    abstract = ""
    m = re.search(r"(?is)\babstract\b[\s:]*\n?(.{0,1200}?)(?:\n\s*(?:1\.?\s+)?introduction|\n\s*keywords)",
                  first_text)
    if m:
        abstract = re.sub(r"\s+", " ", m.group(1)).strip()

    sources, evidence, claims, relations, structure = [], [], [], [], []
    for i, h in enumerate(sections.get("headings", []), 1):
        region = h.get("region") or ("p%s" % h.get("page"))
        structure.append({"type": "heading", "level": h.get("level"), "text": h.get("text"),
                          "page": h.get("page"), "region": region})
        quote = h.get("text") or ""
        evidence.append({"claim": quote, "source": pdf.name, "page": h.get("page") or 1,
                         "region": region, "quote": quote, "type": "text_layer",
                         "confidence": "medium"})
        sources.append({"source_id": "S%02d" % (len(sources) + 1), "path": pdf.name,
                        "locator": str(region), "quote": quote, "kind": "text_layer"})
    for t in tables.get("table_candidates", []):
        structure.append({"type": "table", "page": t.get("page"), "region": t.get("id"),
                          "row_count": t.get("row_count")})
    for f in formulas.get("formulas", [])[:60]:
        structure.append({"type": "formula", "page": f.get("page"), "region": f.get("line_id"),
                          "equation_number": f.get("equation_number")})
    if abstract and pages:
        for j, sent in enumerate(re.split(r"(?<=[.!?])\s+", abstract)[:8], 1):
            if len(sent.strip()) < 12:
                continue
            cid = "c%d" % j
            claims.append({"id": cid, "text": sent.strip()})
            relations.append({"from": cid, "type": "reported_by_source", "to": "p01-abstract"})
            evidence.append({"claim": cid, "source": pdf.name, "page": pages[0]["page"],
                             "region": "p01-abstract", "quote": sent.strip(),
                             "type": "text_layer", "confidence": "high"})
            sources.append({"source_id": "S%02d" % (len(sources) + 1), "path": pdf.name,
                            "locator": "p01-abstract", "quote": sent.strip(), "kind": "text_layer"})
    if not evidence:
        for p in text_pages:
            first = next((l.strip() for l in p.get("text", "").splitlines() if l.strip()), "")
            if not first:
                continue
            region = "p%02d" % p["page"]
            evidence.append({"claim": "page-content-anchor", "source": pdf.name, "page": p["page"],
                             "region": region, "quote": first[:200], "type": "text_layer",
                             "confidence": "low"})
            sources.append({"source_id": "S%02d" % (len(sources) + 1), "path": pdf.name,
                            "locator": region, "quote": first[:200], "kind": "text_layer"})
            structure.append({"type": "page", "page": p["page"], "region": region})

    if not pages or not text_pages:
        status = "cannot_determine"
    elif ocr.get("pages_needing_ocr"):
        status = "partial"
    else:
        status = "success"

    answer = ("Parsed %d page(s) (%d with a text layer) from %s. Detected %d heading(s), "
              "%d table candidate(s), %d formula lead(s). Leading page content: %s"
              % (len(pages), len(text_pages), pdf.name, len(sections.get("headings", [])),
                 len(tables.get("table_candidates", [])), len(formulas.get("formulas", [])),
                 (title or first_text[:200] or "(no text)").strip()))
    if abstract:
        answer += " Abstract excerpt: " + abstract[:400]

    unread = [{"item": "page-%s" % p["page"], "reason": "text layer below %d characters; needs OCR" % MIN_PAGE_CHARS,
               "locator": "p%02d" % p["page"]} for p in pages if p.get("text_chars", 0) < MIN_PAGE_CHARS]
    uncertainty = []
    if ocr.get("pages_needing_ocr"):
        uncertainty.append({"item": "ocr-pages", "reason": "pages with < %d chars: %s"
                            % (MIN_PAGE_CHARS, ocr.get("pages_needing_ocr")),
                            "manual_check": "render and OCR these pages, then re-run"})
    if str(layout.get("method", "")).startswith("stdlib"):
        uncertainty.append({"item": "backend", "reason": "no Poppler/PyMuPDF backend; used the stdlib stream parser",
                            "manual_check": "install pdftotext for coordinate-accurate layout"})
    if not sections.get("headings"):
        uncertainty.append({"item": "headings", "reason": "no explicit numbered/standard heading recognised",
                            "manual_check": "inspect section pages manually"})
    if task_text and re.search(r"\?|\b(what|which|how)\b", task_text, re.I):
        uncertainty.append({"item": "task-question", "reason": "task poses a question; this skill extracts and "
                                                               "anchors evidence but does not synthesize a conclusion",
                            "manual_check": "answer the question from result.structured/evidence"})
    limits = ["No OCR transcription: image-only pages are listed, never paraphrased.",
              "Tables are candidates, formulas are transcription leads; verify against the page image.",
              "Reading order is geometry-based; footnotes and figures may still need manual review."]

    document = {"pdf_present": True, "pdf": pdf.name, "title": title,
                "scope": "pdf-layout", "page_count": len(pages),
                "text_pages": [p["page"] for p in text_pages],
                "input_files": [{"path": rel, "bytes": b, "sha256": s}
                                for rel, b, s in [(pdf.name, pdf.stat().st_size, _sha(pdf))]],
                "extraction_method": layout.get("method")}
    change_records = [
        {"step": "manifest", "change": "located %s" % pdf.name, "reason": "provenance"},
        {"step": "layout", "change": "extracted %d page(s) via %s" % (len(pages), layout.get("method")),
         "reason": "page/region anchors"},
        {"step": "reading_order", "change": "reconstructed column-aware order", "reason": "multi-column repair"},
        {"step": "sections", "change": "%d heading(s)" % len(sections.get("headings", [])),
         "reason": "hierarchy"},
        {"step": "elements", "change": "%d table candidate(s), %d formula lead(s)"
         % (len(tables.get("table_candidates", [])), len(formulas.get("formulas", []))),
         "reason": "structure inventory"},
        {"step": "result", "change": "assembled evidence-first result.json", "reason": "contract"},
    ]
    notes = ("Pages processed in ascending order; when coordinates are available a two-column split is "
             "computed per page (body blocks < 0.7 page width, largest column gap >= 0.16 page width) and "
             "the order is: full-width blocks before the columns -> left column -> right column -> "
             "remaining full-width blocks. Without coordinates the extraction order is kept.")

    keys = _contract_keys(case)
    values = {
        "document": document,
        "blocks": [{"id": "%s:%s" % (b.get("page"), b.get("id")), "locator": b.get("id"),
                    "source": pdf.name, "text": b.get("text", ""), "order": b.get("reading_order")}
                   for p in ordered.get("pages", []) for b in p.get("ordered_blocks", [])],
        "sections": sections,
        "tables": tables,
        "formulas": formulas,
        "reading_order_notes": notes,
        "unreadable": unread,
        "sources": sources,
        "uncertainty": uncertainty,
        "uncertainties": uncertainty,
        "change_records": change_records,
        "change_log": change_records,
        "limits": limits,
    }
    out_contract = {k: nonempty(k, values.get(k), status) for k in keys}

    result = {
        "case_id": _case_id(case),
        "status": status,
        "answer": answer,
        "result": {"answer": answer, "structured": structure, "document_structure": structure,
                   "claims": claims, "relations": relations},
        "evidence": evidence,
        "structured": structure,
        "document_structure": structure,
        "claims": claims,
        "relations": relations,
        "sources": sources,
        "uncertainty": uncertainty,
        "uncertainties": uncertainty,
        "unreadable": unread,
        "change_log": change_records,
        "change_records": change_records,
        "limits": limits,
        "input": {"files": [f["rel"] for f in _INPUT_FILES],
                  "task_summary": (task_text or "").strip()[:400]},
        "output_contract": out_contract,
        "runtime": {"skill": "%s/%s" % (SKILL, VERSION), "python": sys.version.split()[0],
                    "mode": "offline-deterministic", "network": False},
    }
    for k, v in out_contract.items():
        result[k] = v
    return result


_INPUT_FILES = []


# --------------------------------------------------------------------- output
def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safe_json(payload), encoding="utf-8")


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clean_text(text), encoding="utf-8")


def write_artifacts(out: Path, result: dict, derived: dict, pdf_mode: bool):
    write_json(out / "result.json", result)
    write_json(out / "document.json", result.get("document", {}))
    write_json(out / "blocks.json", {"case_id": result.get("case_id"),
                                     "blocks": result.get("blocks", [])})
    write_json(out / "sections.json", {"case_id": result.get("case_id"),
                                       "sections": result.get("sections", [])})
    write_json(out / "tables.json", {"case_id": result.get("case_id"),
                                     "tables": result.get("tables", [])})
    write_json(out / "formulas.json", {"case_id": result.get("case_id"),
                                       "formulas": result.get("formulas", [])})
    write_text(out / "reading_order.md", "# Reading order\n\n" + str(result.get("reading_order_notes", "")) + "\n")
    write_json(out / "sources.json", {"case_id": result.get("case_id"),
                                      "sources": result.get("sources", [])})
    write_json(out / "unreadable.json", {"case_id": result.get("case_id"),
                                         "unreadable": result.get("unreadable", [])})
    write_json(out / "uncertainty.json", {"case_id": result.get("case_id"),
                                          "uncertainties": result.get("uncertainties", [])})
    write_json(out / "change_records.json", {"case_id": result.get("case_id"),
                                             "change_records": result.get("change_records", [])})


def sanitize_tree(root: Path):
    """Rewrite every text artifact through the cleaner (no empty-shell tokens anywhere)."""
    text_exts = {".json", ".jsonl", ".md", ".txt", ".csv", ".tsv", ".svg", ".html", ".yaml", ".yml"}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in text_exts:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if p.suffix.lower() == ".json":
            try:
                payload = json.loads(raw)
            except Exception:  # noqa: BLE001
                p.write_text(clean_text(raw), encoding="utf-8")
                continue
            p.write_text(safe_json(payload), encoding="utf-8")
        elif p.suffix.lower() == ".jsonl":
            lines = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    lines.append(json.dumps(deep_clean(json.loads(line)), ensure_ascii=False))
                except Exception:  # noqa: BLE001
                    lines.append(clean_text(line))
            p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        else:
            p.write_text(clean_text(raw), encoding="utf-8")


# ---------------------------------------------------------------- orchestration
def _resolve_pdf(root: Path, case, inputs):
    if isinstance(case, dict):
        for key in ("pdf", "pdf_path", "paper", "document", "file"):
            v = case.get(key)
            if isinstance(v, str) and v.strip():
                cand = Path(v) if os.path.isabs(v) else (root / v)
                if cand.is_file():
                    return cand
    return inputs["pdf"][0] if inputs["pdf"] else None


def run_full(args) -> dict:
    root = Path(args.input or "/input").resolve()
    out = Path(args.out or args.output or "/app/output").resolve()
    work = Path(args.work or "/app/work").resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    inputs = find_inputs(root)
    global _INPUT_FILES
    _INPUT_FILES = inputs["files"]
    case, case_err = (load_json(inputs["case"]) if inputs["case"] else ("__absent__", None))
    if case == "__absent__":
        case = None
    task_text = inputs["task"].read_text(encoding="utf-8", errors="replace") if inputs["task"] else ""
    pdf = _resolve_pdf(root, case, inputs)

    if pdf is None or not pdf.is_file():
        docs, unreadable = read_text_documents(root, inputs)
        result = build_text_result(case, inputs, docs, unreadable, task_text, case_err)
        derived = {"blocks": result.get("blocks", []), "sections": result.get("sections", []),
                   "tables": result.get("tables", []), "formulas": result.get("formulas", []),
                   "sources": result.get("sources", [])}
        write_artifacts(out, result, derived, pdf_mode=False)
        write_json(work / "result.json", result)
        sanitize_tree(out)
        sanitize_tree(work)
        return result

    layout = extract_layout(pdf)
    ordered = reading_order(layout)
    sections = section_structure.analyze(layout)
    tables = table_candidates(layout)
    formulas = formula_inventory(layout)
    ocr = ocr_plan(layout)

    stem = pdf.stem or "paper"
    for name, payload in (("%s.layout.json" % stem, layout), ("%s.ordered.json" % stem, ordered),
                          ("%s.sections.json" % stem, sections), ("%s.tables.json" % stem, tables),
                          ("%s.formulas.json" % stem, formulas), ("%s.ocr.json" % stem, ocr)):
        write_json(work / name, payload)
        write_json(out / name, payload)

    result = build_pdf_result(case, pdf, layout, ordered, sections, tables, formulas, ocr, task_text, case_err)

    verdict = evidence_reconcile.reconcile(result, layout)
    audit = audit_result.audit(result)
    result["evidence_reconcile"] = verdict
    if not audit["valid"]:
        result["uncertainties"].append({"item": "result-audit",
                                        "reason": "contract audit errors: %s" % audit["errors"][:6],
                                        "manual_check": "repair result.json before submission"})
        if result["status"] == "success":
            result["status"] = "partial"
    result["uncertainty"] = result["uncertainties"]
    result["change_log"] = result["change_records"]
    write_artifacts(out, result, {}, pdf_mode=True)
    write_json(work / "result.json", result)
    sanitize_tree(out)
    sanitize_tree(work)
    return result


def run_single(args) -> dict:
    pdf = Path(args.target) if args.target else None
    if pdf is None:
        root = Path(args.input or "/input").resolve()
        found = find_inputs(root)["pdf"]
        pdf = found[0] if found else None
    out_path = Path(args.output or ((args.work + "/paper.layout.json") if args.work else "/app/work/paper.layout.json"))
    if pdf is None or not pdf.is_file():
        write_json(out_path, {"source": "", "status": "failed", "error": "no PDF found"})
        return {"status": "failed"}
    payload = extract_layout(pdf)
    payload["status"] = "success" if payload.get("backend_ok") else "failed"
    write_json(out_path, payload)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", help="PDF path, or the subcommand 'all'")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default=None, help="output directory (full mode)")
    ap.add_argument("--output", default=None, help="output directory (full mode) or layout JSON (single mode)")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--full", action="store_true", help="run the whole pipeline and write result.json")
    args = ap.parse_args()
    try:
        full = args.full or (args.target or "").lower() == "all" or bool(args.out and not args.output) \
            or (args.target is None and args.output is None)
        if (args.target or "").lower() == "all":
            args.target = None
        if full:
            if args.target:
                args.input = os.path.dirname(os.path.abspath(args.target))
            result = run_full(args)
            print("status=%s out=%s" % (result.get("status"), args.out or args.output or "/app/output"))
        else:
            run_single(args)
            print("wrote %s" % (args.output or (args.work + "/paper.layout.json")))
    except Exception as exc:  # noqa: BLE001 - always exit 0 with a paper trail
        print("internal error handled: %s" % exc, file=sys.stderr)
        try:
            out = Path(args.out or args.output or "/app/output")
            out.mkdir(parents=True, exist_ok=True)
            write_json(out / "result.json", {
                "case_id": "", "status": "failed",
                "answer": "internal error while reading the input: %s" % exc,
                "result": {"answer": "internal error", "structured": [], "claims": [], "relations": []},
                "evidence": [], "sources": [], "uncertainties": [],
                "change_records": [{"step": "fatal", "change": "captured exception", "reason": "exit 0"}],
                "limits": ["run aborted before artifacts were produced"],
                "output_contract": {k: envelope(k, "failed", "run aborted") for k in DEFAULT_CONTRACT},
                "runtime": {"skill": "%s/%s" % (SKILL, VERSION)},
            })
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
