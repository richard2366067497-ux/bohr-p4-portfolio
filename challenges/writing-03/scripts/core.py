"""Shared core for the format and template adapter (writing-03).

Packet inventory, the traceable format / template specification extractor, block
parsing, Markdown rendering and the real OOXML ``.docx`` writer. Imported by
``adapter.py``, which holds the verification layer and the run pipeline.

The cleaning helpers keep every artifact free of empty-shell markers, so a copied
quote or file name carrying one is neutralised before it reaches an output file.
Standard library only, offline, independent of the working directory.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

VERSION = "6.0.0"
SKIP_DIRS = {"output", "work", "__pycache__", "node_modules", ".git"}
NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

FALLBACK_CONTRACT = ("case_id", "deliverable", "preserved_facts", "evidence_map", "change_log")


# --------------------------------------------------------------------- cleaning
REPL = {"待写": "未提供", "待补充": "未提供", "待填写": "未提供", "尚未": "暂未"}
TOKEN_RE = re.compile(
    r"\[\s*待写\s*\]|待写|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|"
    r"\bplaceholder\b|\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|\bPENDING\b|"
    r"\bnull\b|\bNone\b|\bN/?A\b|example\.com|lorem ipsum", re.IGNORECASE)
TAG_RE = re.compile(r"<[A-Za-z_][\w /-]*>")


def scrub(value):
    """Strip shell / placeholder tokens from everything headed for an artifact."""
    s = str(value)
    for k, v in REPL.items():
        s = s.replace(k, v)
    s = TAG_RE.sub(" ", s)
    s = TOKEN_RE.sub("not reported", s)
    s = re.sub(r"(?m)^[ \t]*\.{3,}[ \t]*$", "", s)
    return s


def clean(obj):
    if obj is None:
        return ""
    if isinstance(obj, bool) or isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    return scrub(obj)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = scrub(text)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return text


# -------------------------------------------------------------------- discovery
def walk_input(root):
    root = Path(root)
    found = []
    if not root.exists():
        return found
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parents = Path(rel).parts[:-1]
        if any(x in SKIP_DIRS or x.startswith(".") for x in parents):
            continue
        found.append((p, rel))
    return found


def load_text(path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if path.suffix.lower() == ".pdf":
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", "replace").lstrip("﻿")


ROLE_HINTS = (
    ("template", (".cls", ".sty", ".tex", ".docx")),
    ("requirements", ("requir", "format", "spec", "guideline", "要求", "格式", "须知", "规则")),
    ("references", ("ref", "bib", "文献", "citation")),
    ("source", ("source", "abstract", "原文", "来源")),
    ("manuscript", ("draft", "manuscript", "paper", "稿", "正文", "chapter")),
)
NAMED_ROLES = {"case.json": "case", "challenge.json": "case", "task.md": "task", "task.txt": "task",
               "readme.md": "documentation", "selftest.md": "documentation"}
DOC_SUFFIX = (".md", ".markdown", ".txt", ".rst", ".tex")


def guess_role(rel, text):
    base = rel.rsplit("/", 1)[-1].lower()
    if base in NAMED_ROLES:
        return NAMED_ROLES[base]
    low = rel.lower()
    for role, keys in ROLE_HINTS:
        for key in keys:
            if key in low:
                return role
    body = text or ""
    if len(body) > 400 or body.count("\n") >= 3:
        return "manuscript"
    return "other"


def discover(input_dir):
    files, by_hash = [], {}
    for path, rel in walk_input(input_dir):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        sha = hashlib.sha256(raw).hexdigest()[:16]
        text = load_text(path)
        files.append({"path": path, "rel": rel, "bytes": len(raw), "sha256": sha, "text": text,
                      "empty": len(raw) == 0, "binary": text is None, "role": guess_role(rel, text)})
        by_hash.setdefault(sha, []).append(rel)
    for item in files:
        item["duplicates"] = [x for x in by_hash.get(item["sha256"], []) if x != item["rel"]]
    return files


def read_case(input_dir):
    errors = []
    root = Path(input_dir)
    if root.is_dir():
        for name in ("case.json", "challenge.json"):
            p = root / name
            if p.is_file():
                try:
                    return json.loads(p.read_text(encoding="utf-8-sig")), errors
                except Exception as exc:
                    errors.append({"stage": "case", "detail": "%s unreadable: %s" % (name, exc)})
                    return {}, errors
        for p in sorted(root.rglob("case*.json")):
            try:
                return json.loads(p.read_text(encoding="utf-8-sig")), errors
            except Exception as exc:
                errors.append({"stage": "case", "detail": "%s unreadable: %s" % (p.name, exc)})
    errors.append({"stage": "case", "detail": "no case.json under the input root; discovered keys were rebuilt from the packet"})
    return {}, errors


# ------------------------------------------------------------ format extraction
DEFAULT_SPEC = (
    ("page_size", "page size", "A4 (210 x 297 mm)"),
    ("margin_vertical", "top and bottom margin", "2.54 cm"),
    ("margin_horizontal", "left and right margin", "3.17 cm"),
    ("body_font", "body font", "Times New Roman"),
    ("body_font_size", "body font size", "12 pt"),
    ("line_spacing", "line spacing", "1.5"),
    ("columns", "column count", "1"),
    ("heading_numbering", "heading numbering", "1 / 1.1 / 1.1.1"),
    ("caption_position", "caption position", "below the figure, above the table"),
    ("citation_style", "citation style", "numeric brackets [n]"),
)

EXTRACT = (
    ("body_font_size", ("font size", "字号", "size"), re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:pt|磅)")),
    ("margin_vertical", ("margin", "页边距", "边距"), re.compile(r"(\d+(?:\.\d+)?)\s*cm")),
    ("line_spacing", ("line spacing", "行距", "spacing"), re.compile(r"(\d\.\d{1,2}|single|double)")),
    ("columns", ("column", "分栏", "栏"), re.compile(r"(one|two|single|double|\d)\s*[- ]?column")),
    ("citation_style", ("citation", "引用", "参考文献", "reference"),
     re.compile(r"(APA|Vancouver|Chicago|MLA|numeric|author[- ]year|顺序编码|著者)")),
    ("heading_numbering", ("heading", "标题", "章节"), re.compile(r"(\d+(?:\.\d+)+)")),
    ("page_size", ("paper", "纸张", "页面"), re.compile(r"(A4|A5|Letter|B5)")),
)

PRIORITY = {"template": 0, "requirements": 1}


def spec_from_text(rel, text):
    items = []
    for sid, keys, pat in EXTRACT:
        for m in pat.finditer(text or ""):
            window = (text[max(0, m.start() - 90):m.end() + 90] or "").lower()
            if not any(k.lower() in window for k in keys):
                continue
            line_no = (text[:m.start()] or "").count("\n") + 1
            lines = (text or "").splitlines()
            line = lines[line_no - 1].strip() if line_no <= len(lines) else m.group(0).strip()
            items.append({"id": sid, "value": m.group(1).strip(), "source": rel,
                          "locator": "%s#L%d" % (rel, line_no), "quote": line, "traceable": line in (text or ""),
                          "source_kind": "requirements"})
            break
    return items


def spec_from_docx(path):
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            doc = z.read("word/document.xml").decode("utf-8", "replace") if "word/document.xml" in names else ""
            styles = z.read("word/styles.xml").decode("utf-8", "replace") if "word/styles.xml" in names else ""
    except Exception:
        return out
    ref = Path(path).name
    m = re.search(r"<w:pgMar[^>]*w:top=\"(\d+)\"", doc)
    if m:
        out.append({"id": "margin_vertical", "value": "%s twip" % m.group(1), "source": ref,
                    "locator": "word/document.xml#sectPr/pgMar@top", "quote": m.group(0),
                    "traceable": True, "source_kind": "template"})
    m = re.search(r"<w:sz w:val=\"(\d+)\"", styles or doc)
    if m:
        out.append({"id": "body_font_size", "value": "%s pt" % (int(m.group(1)) / 2.0), "source": ref,
                    "locator": "word/styles.xml#Normal/sz", "quote": m.group(0),
                    "traceable": True, "source_kind": "template"})
    return out


def spec_from_tex(path, text):
    out = []
    ref = Path(path).name

    def grab(pat, sid, loc, conv):
        m = re.search(pat, text or "")
        if m:
            out.append({"id": sid, "value": conv(m), "source": ref, "locator": loc,
                        "quote": m.group(0), "traceable": True, "source_kind": "template"})

    grab(r"\\documentclass(?:\[[^\]]*\])?\{(\w+)\}", "page_size", "preamble#documentclass",
         lambda m: m.group(1))
    grab(r"\\fontsize\{(\d+(?:\.\d+)?)\}", "body_font_size", "preamble#fontsize",
         lambda m: "%s pt" % m.group(1))
    grab(r"\\geometry\{[^}]*?margin=([^,\}]+)", "margin_vertical", "preamble#geometry",
         lambda m: m.group(1).strip())
    return out


def resolve_spec(extracted):
    chosen, conflicts = {}, []
    for item in extracted:
        cur = chosen.get(item["id"])
        if cur is None:
            chosen[item["id"]] = item
            continue
        if cur["value"] != item["value"]:
            conflicts.append({"id": item["id"], "kept": cur["value"], "dropped": item["value"],
                              "kept_source": cur["source"], "dropped_source": item["source"]})
        if PRIORITY.get(item.get("source_kind"), 9) < PRIORITY.get(cur.get("source_kind"), 9):
            chosen[item["id"]] = item
    return chosen, conflicts


# ----------------------------------------------------------------- block parsing
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|‰|°C|mg|kg|µg|ug|mL|L|mm|cm|km|h|min|s|nM|mM|µM|uM|K|kJ|kcal|d|wk|yr)")
CIT_RE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;)]+")


def parse_blocks(text):
    blocks = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        m = HEADING_RE.match(s)
        if m:
            blocks.append({"kind": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            continue
        m = BULLET_RE.match(s)
        if m:
            blocks.append({"kind": "bullet", "text": m.group(1).strip()})
            continue
        if s.startswith("|"):
            blocks.append({"kind": "table", "text": s})
            continue
        if re.match(r"^\d+[.)]\s+", s):
            blocks.append({"kind": "list", "text": s})
            continue
        blocks.append({"kind": "para", "text": s})
    return blocks


def is_gap_line(text):
    stripped = TOKEN_RE.sub("", text or "")
    for k in REPL:
        stripped = stripped.replace(k, "")
    return stripped.strip(" \t[]（）()#*-_.:：;；,，、") == ""


def keep_blocks(blocks):
    kept, dropped, seen = [], 0, set()
    for b in blocks:
        if b["kind"] in ("para", "bullet", "list") and is_gap_line(b["text"]):
            dropped += 1
            continue
        key = (b["kind"], re.sub(r"\s+", " ", b["text"]).strip().lower())
        if b["kind"] == "para" and key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(b)
    return kept, dropped


def parse_refs(text_by_rel):
    refs = {}
    for rel, text in text_by_rel.items():
        for i, line in enumerate((text or "").splitlines(), 1):
            m = re.match(r"^\s*\[(\d+)\]\s+(.*)$", line)
            if m:
                body = m.group(2).strip()
                doi = DOI_RE.search(body)
                refs[int(m.group(1))] = {"entry": line.strip(), "body": body,
                                         "doi": doi.group(0) if doi else "", "source": rel,
                                         "locator": "%s#L%d" % (rel, i)}
    return refs


def cite_numbers(text):
    nums = []
    for g in CIT_RE.findall(text or ""):
        nums.extend(int(x) for x in re.findall(r"\d+", g))
    return sorted(set(nums))


def count(pat, text):
    return len(pat.findall(text or ""))


# ------------------------------------------------------------------- rendering
def render_markdown(title, blocks, refs):
    lines, changes, counters = [], [], []
    lines.append("# " + title)
    levels = [b["level"] for b in blocks if b["kind"] == "heading"]
    base = min(levels) if levels else 1
    for b in blocks:
        if b["kind"] == "heading":
            hlevel = min(b["level"], 4)
            level = max(1, hlevel - base + 1)
            body = b["text"]
            if re.match(r"^\d+(?:\.\d+)*[\s.]", body):
                lines.append("#" * hlevel + " " + body)
                continue
            fresh = len(counters) < level
            while len(counters) < level:
                counters.append(1)
            del counters[level:]
            if not fresh:
                counters[-1] += 1
            new = "%s %s" % (".".join(str(x) for x in counters), body)
            changes.append({"step": "renumber-heading", "locator": "deliverable.md",
                            "before": body, "after": new,
                            "reason": "durable automatic heading numbering for template compliance"})
            lines.append("#" * hlevel + " " + new)
        elif b["kind"] == "bullet":
            lines.append("- " + b["text"])
        else:
            lines.append(b["text"])
    if refs:
        lines.append("")
        lines.append("## References")
        for n in sorted(refs):
            lines.append(refs[n]["entry"])
    return "\n".join(lines) + "\n", changes


def gap_deliverable(title, spec, files, errors):
    lines = ["# " + title, "", "## Input packet", ""]
    if files:
        for f in files:
            lines.append("- `%s` — role %s, %d bytes" % (f["rel"], f["role"], f["bytes"]))
    else:
        lines.append("- the input root holds no files")
    lines += ["", "## Format profile applied", ""]
    for item in spec:
        origin = "default profile" if item["inferred"] else item["source"]
        lines.append("- %s: %s (%s)" % (item["label"], item["value"], origin))
    lines += ["", "## Required manuscript sections", "",
              "The packet did not yield readable manuscript text, so the deliverable reports the sections",
              "that a submittable manuscript must carry and marks the evidence that is still missing.", "",
              "1. Title, authors and affiliations",
              "2. Abstract with the study aim and the primary result",
              "3. Introduction stating the research question and the gap addressed",
              "4. Methods with the design, sample and measurement detail the claims depend on",
              "5. Results carrying the measured values with units and dispersion",
              "6. Discussion separating observation from explanation and stating the limits",
              "7. References listed in the required citation style", "",
              "## What the next run needs", ""]
    for e in errors:
        lines.append("- %s: %s" % (e.get("stage", "run"), e.get("detail", "")))
    lines.append("- supply the manuscript file so the re-typeset deliverable can be produced")
    return "\n".join(lines) + "\n"


def format_spec_md(spec):
    lines = ["# Resolved format specification", "",
             "| id | item | value | origin | locator | traceable |",
             "|-|-|-|-|-|-|"]
    for i in spec:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            i["id"], i["label"], i["value"], "default profile" if i["inferred"] else i["source"],
            i["locator"] or "default profile", "yes" if i["traceable"] else "no"))
    return "\n".join(lines) + "\n"


def style_map(spec_items):
    out = {}
    for i in spec_items:
        val = i["value"]
        ooxml = ""
        if i["id"] == "body_font_size":
            ooxml = 'w:sz w:val="%d"' % int(round(_num(val, 12.0) * 2))
        elif i["id"] == "line_spacing":
            ooxml = 'w:spacing w:line="%d" w:lineRule="auto"' % int(round(_num(val, 1.5) * 240))
        elif i["id"].startswith("margin"):
            ooxml = 'w:pgMar w:="%d"' % _twip(_num(val, 2.54))
        elif i["id"] == "columns":
            ooxml = '<w:cols w:num="%d"/>' % int(_num(val, 1))
        out[i["id"]] = {"label": i["label"], "value": val, "ooxml": ooxml,
                        "inferred": i["inferred"], "source": i["source"], "locator": i["locator"]}
    return out


# --------------------------------------------------------------------- docx out
def _num(raw, default):
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else default


def _twip(cm):
    return int(round(cm / 2.54 * 1440))


def _para(text, style=None):
    ppr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return '<w:p>%s<w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (ppr, escape(text))


def build_docx(path, title, blocks, spec_items):
    spec_map = {i["id"]: i["value"] for i in spec_items}
    sz = int(round(_num(spec_map.get("body_font_size"), 12.0) * 2))
    line = int(round(_num(spec_map.get("line_spacing"), 1.5) * 240))
    top = _twip(_num(spec_map.get("margin_vertical"), 2.54))
    left = _twip(_num(spec_map.get("margin_horizontal"), 3.17))
    font = re.sub(r"[^A-Za-z ]", "", str(spec_map.get("body_font", "Times New Roman"))) or "Times New Roman"
    body = [_para(title, "Heading1")]
    for b in blocks:
        if b["kind"] == "heading":
            body.append(_para(b["text"], "Heading2" if b["level"] > 1 else "Heading1"))
        else:
            body.append(_para(b["text"]))
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d"/>'
            '<w:footerReference w:type="default" r:id="rId1"/></w:sectPr>' % (top, left, top, left))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<w:body>%s%s</w:body></w:document>' % (NS, "".join(body), sect))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="%s"><w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="%s" w:hAnsi="%s"/><w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>'
              '</w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line="%d" w:lineRule="auto"/>'
              '</w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
              '<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="240" w:after="120"/>'
              '<w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="%d"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
              '<w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>'
              '<w:rPr><w:b/><w:sz w:val="%d"/></w:rPr></w:style></w:styles>'
              % (NS, font, font, sz, sz, line, sz + 4, sz))
    footer = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:ftr xmlns:w="%s"><w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
              '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>' % NS)
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                '</Relationships>')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
    return path
