#!/usr/bin/env python3
"""Section/heading recogniser for the layout JSON produced by pdf_layout_extract.py.

Recognises numbered headings (1, 1.1, 2.3.4), roman numerals, and the common
academic section labels (Abstract, Introduction, Related Work, Method(s),
Experiments, Results, Discussion, Conclusion, References, Appendix). Returns a
flat heading list plus a nested outline. Pure standard library.

Standalone:  python3 section_structure.py paper.layout.json [out.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STD_LABELS = [
    "abstract", "introduction", "background", "related work", "related works",
    "preliminaries", "problem statement", "problem formulation", "method",
    "methods", "methodology", "approach", "model", "architecture", "experiments",
    "experimental setup", "evaluation", "results", "results and discussion",
    "analysis", "ablation", "ablation study", "discussion", "limitations",
    "conclusion", "conclusions", "future work", "acknowledgments",
    "acknowledgements", "references", "appendix", "supplementary material",
]

NUM_HEADING = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Z][\w\-:,'()&/ ]{2,80})\s*$")
ROMAN_HEADING = re.compile(r"^\s*((?:I|II|III|IV|V|VI|VII|VIII|IX|X))\.\s+([A-Z][\w\-:,'()&/ ]{2,80})\s*$")
ALPHA_HEADING = re.compile(r"^\s*([A-Z])\.\s+([A-Z][\w\-:,'()&/ ]{2,80})\s*$")
UPPER_LABEL = re.compile(r"^\s*([A-Z][A-Z \-&]{3,40})\s*$")


def _level_of(number: str) -> int:
    return number.count(".") + 1


def _is_label(text: str):
    t = text.strip().lower().rstrip(".")
    for lab in sorted(STD_LABELS, key=len, reverse=True):
        if t == lab or t.startswith(lab + " ") or t.startswith(lab + ":"):
            return lab
    return None


def _heading_from_line(line: dict, page: int):
    text = line.get("text", "").strip()
    if not text or len(text) > 90:
        return None
    m = NUM_HEADING.match(text)
    if m and not re.search(r"[.!?]\s*$", text.rstrip()):
        title = m.group(2).strip()
        if title.lower() in ("fig", "figure", "table", "eq", "equation", "alg"):
            return None
        return {"text": text, "title": title, "number": m.group(1), "level": _level_of(m.group(1)),
                "page": page, "line_id": line.get("id"), "region": line.get("id"),
                "kind": "numbered", "confidence": "high"}
    m = ROMAN_HEADING.match(text) or ALPHA_HEADING.match(text)
    if m:
        return {"text": text, "title": m.group(2).strip(), "number": m.group(1), "level": 1,
                "page": page, "line_id": line.get("id"), "region": line.get("id"),
                "kind": "roman", "confidence": "medium"}
    lab = _is_label(text)
    if lab:
        return {"text": text, "title": text, "number": None, "level": 1, "page": page,
                "line_id": line.get("id"), "region": line.get("id"), "kind": "label",
                "confidence": "high"}
    m = UPPER_LABEL.match(text)
    if m and len(m.group(1).split()) <= 6 and any(w.isalpha() for w in m.group(1).split()):
        return {"text": text, "title": text, "number": None, "level": 2, "page": page,
                "line_id": line.get("id"), "region": line.get("id"), "kind": "caps",
                "confidence": "low"}
    return None


def analyze(layout: dict) -> dict:
    headings = []
    for page in layout.get("pages", []):
        pno = page.get("page")
        for line in page.get("lines", []) or page.get("blocks", []):
            h = _heading_from_line(line, pno)
            if h:
                # a heading never follows immediately in the same line as body prose
                if len(h["text"].split()) <= 10 or h["kind"] == "label":
                    headings.append(h)
    # de-duplicate consecutive repeats (headers/footers repeated across pages)
    deduped = []
    for h in headings:
        if deduped and deduped[-1]["title"] == h["title"] and h["page"] == deduped[-1]["page"]:
            continue
        deduped.append(h)
    outline = []
    stack = []
    for h in deduped:
        node = {"title": h["title"], "number": h["number"], "level": h["level"],
                "page": h["page"], "region": h["region"], "children": []}
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            outline.append(node)
        stack.append(node)
    return {"status": "success", "source": layout.get("source"),
            "heading_count": len(deduped), "headings": deduped, "outline": outline,
            "labels_hit": sorted({h["title"].strip().lower().rstrip(".") for h in deduped
                                  if h["kind"] == "label"})}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    path = Path(sys.argv[1])
    try:
        layout = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        out = analyze(layout)
    except Exception as exc:  # noqa: BLE001
        out = {"status": "failed", "error": str(exc)[:200], "headings": [], "outline": []}
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
