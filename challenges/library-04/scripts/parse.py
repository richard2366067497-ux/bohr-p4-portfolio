#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse.py — text extraction layer for kb-version-qa (standard library only).

Reads real files, never assumes content from a label: PDF via pdftotext when
present, otherwise a stdlib zlib stream decoder; DOCX/XLSX/PPTX via zipfile +
ElementTree; plain text with encoding fallback. Every failure is returned as a
note so the caller can record an honest degradation instead of inventing text.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "1.0.0"

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".log", ".tex", ".bib", ".yaml", ".yml",
            ".html", ".htm", ".json", ".csv", ".tsv", ".xml", ".ini", ".cfg"}
OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm"}
INSTRUCTION_NAMES = {"case.json", "task.md", "task_instruction.md", "brief.md", "prompt.md"}
MAX_BYTES = 24 * 1024 * 1024
CHUNK_CHARS = 1400
WS = re.compile(r"[\s\u00a0\u3000\u200b\u200e\u200f\ufeff]+")
NUM = re.compile(r"\d+(?:[.,]\d+)*")
CJK = re.compile(r"[\u3400-\u9fff]")
VER_TOKEN = re.compile(r"(?i)(?:^|[_\-.\s(（\[])(?:v|ver|vers|version|rev|revision|r|第)?\s*(\d+(?:[._]\d+){0,2})\s*(?:版|次)?(?=$|[_\-.）)\]\s])")
DATE_TOKEN = re.compile(r"(20\d{2})[-_.年]?(\d{1,2})[-_.月]?(\d{1,2})?")
COPY_MARK = re.compile(r"(?i)(?:[-_.\s(（\[]|^)(?:copy|副本|拷贝|备份|duplicate|下载|\(1\)|（1）|final|定稿|终稿|最新|latest|old|旧版|new|新版|修订)(?:[-_.\s)）\]]|$|\d*)")
AUX_NAME = re.compile(r"(?i)(metadata|meta|manifest|alias|catalog|inventory|index|version|版本|目录|清单|notes|说明|readme)")
STOP = set("""a an the of and or in on for to with by from at as is are was were be been this that these those
we our it its their there than then such using used use can may might could should would will not no also both
each more most less between among during after before under over into within via vs which what how why when
where who do have has had if while about""".split())


# --------------------------------------------------------------------------- io
def jload(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return json.loads(fh.read())
        except Exception:
            return default


def jdump(path, obj, indent=1):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=indent)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return None


def read_text(path):
    try:
        data = Path(path).read_bytes()
    except Exception:
        return None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", "replace")


def norm_ws(s):
    if s is None:
        return ""
    s = str(s).replace("\u00ad", "")
    return WS.sub(" ", s).strip()


def norm_q(s):
    """Normalise typographic quotes so verbatim checks survive PDF/DOCX quoting."""
    s = norm_ws(s)
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
                 ("\u300c", '"'), ("\u300d", '"'), ("\u2013", "-"), ("\u2014", "-")):
        s = s.replace(a, b)
    return s.lower()


def tokens(text):
    low = norm_q(text)
    out = set()
    for w in re.findall(r"[a-z][a-z0-9\-]{1,}", low):
        if w not in STOP and len(w) >= 2:
            out.add(w)
    for n in re.findall(r"\d+(?:\.\d+)?", low):
        if len(n) >= 2:
            out.add(n)
    han = re.sub(r"[^\u3400-\u9fff]", "", low)
    for i in range(len(han) - 1):
        out.add(han[i:i + 2])
    return out


def human(nbytes):
    try:
        v = float(nbytes)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.0f}{unit}" if unit == "B" else f"{v:.1f}{unit}"
        v /= 1024.0
    return "?"



# -------------------------------------------------------------------- parse: pdf
def _pdf_literal(chunk):
    out, i, n = [], 0, len(chunk)
    while i < n:
        c = chunk[i:i + 1]
        if c == b"\\":
            nxt = chunk[i + 1:i + 2]
            if nxt in (b"n", b"r", b"t"):
                out.append({b"n": " ", b"r": " ", b"t": " "}[nxt])
                i += 2
            elif nxt in (b"(", b")", b"\\"):
                out.append(nxt.decode("latin-1"))
                i += 2
            elif nxt.isdigit():
                m = re.match(rb"[0-7]{1,3}", chunk[i + 1:i + 4])
                try:
                    out.append(chr(int(m.group(0), 8)))
                    i += 1 + len(m.group(0))
                except Exception:
                    i += 2
            else:
                i += 2
        else:
            out.append(c.decode("latin-1", "replace"))
            i += 1
    return "".join(out)


def _pdf_streams_text(raw):
    pieces = []
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        blob = raw[start:end].rstrip(b"\r\n")
        data, ok = None, False
        for cand in (blob,):
            try:
                data = zlib.decompress(cand)
                ok = True
            except Exception:
                try:
                    data = zlib.decompressobj().decompress(cand)
                    ok = bool(data)
                except Exception:
                    ok = False
            if ok:
                break
        if not ok or not data:
            continue
        buf = []
        for op in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\[\]]{0,4000})\]\s*TJ|(?:T\*|TD|Td|ET)\b", data):
            s = op.group(0)
            if s.endswith(b"Tj"):
                buf.append(_pdf_literal(s[s.find(b"(") + 1:s.rfind(b")")]))
            elif s.endswith(b"TJ"):
                for lit in re.findall(rb"\((?:\\.|[^\\()])*\)", s):
                    buf.append(_pdf_literal(lit[1:-1]))
            else:
                buf.append("\n")
        txt = "".join(buf)
        if txt.strip():
            pieces.append(txt)
    return "\n".join(pieces)


def pdf_text(path):
    """Return (pages[list[str]] or None, method, note)."""
    txt, method = None, None
    exe = shutil.which("pdftotext")
    if exe:
        try:
            proc = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, timeout=90)
            if proc.returncode == 0 and proc.stdout:
                txt, method = proc.stdout.decode("utf-8", "replace"), "pdftotext -layout"
        except Exception:
            txt = None
    if not txt or len(txt.strip()) < 20:
        try:
            alt = _pdf_streams_text(Path(path).read_bytes())
        except Exception:
            alt = ""
        if alt and len(alt.strip()) > len((txt or "").strip()):
            txt, method = alt, "stdlib zlib stream decode"
    if txt and len(txt.strip()) >= 20:
        pages = txt.split("\f")
        return [p for p in pages] if len(pages) > 1 else [txt], method, None
    return None, method or "none", "no extractable text layer (scanned image or encoded fonts)"


# ------------------------------------------------------------------ parse: office
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def docx_units(path):
    units = []
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    if body is None:
        return units
    section, para = "body", 0
    for el in list(body):
        tag = el.tag.split("}")[-1]
        if tag == "p":
            text = "".join(t.text or "" for t in el.iter(W + "t"))
            style = ""
            for st in el.iter(W + "pStyle"):
                style = st.get(W + "val") or ""
            text = norm_ws(text)
            if not text:
                continue
            if re.search(r"(?i)(heading|title|标题)", style or ""):
                section = text[:80]
                para = 0
                units.append(("head", section, text))
                continue
            para += 1
            units.append(("para", section, text))
        elif tag == "tbl":
            for tr in el.iter(W + "tr"):
                cells = [norm_ws("".join(t.text or "" for t in tc.iter(W + "t"))) for tc in tr.iter(W + "tc")]
                line = " | ".join(c for c in cells if c)
                if line:
                    para += 1
                    units.append(("para", section or "table", line))
    return units


def pptx_units(path):
    units = []
    with zipfile.ZipFile(path) as zf:
        names = sorted([n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                       key=lambda n: int(re.findall(r"\d+", n)[-1]))
        for idx, name in enumerate(names, 1):
            try:
                root = ET.fromstring(zf.read(name))
            except Exception:
                continue
            lines = [norm_ws(t.text or "") for t in root.iter(A + "t")]
            lines = [ln for ln in lines if ln]
            for j, ln in enumerate(lines, 1):
                units.append((idx, f"slide{idx}", ln))
    return units


def xlsx_units(path):
    units = []
    shared = []
    with zipfile.ZipFile(path) as zf:
        try:
            ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss.iter():
                if si.tag.endswith("}si"):
                    shared.append(norm_ws("".join(t.text or "" for t in si.iter() if t.tag.endswith("}t"))))
        except Exception:
            pass
        sheets = sorted([n for n in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)],
                        key=lambda n: int(re.findall(r"\d+", n)[-1]))
        names = {}
        try:
            wb = ET.fromstring(zf.read("xl/workbook.xml"))
            names = {f"sheet{i}": s.get("name") for i, s in enumerate(
                [x for x in wb.iter() if x.tag.endswith("}sheet")], 1)}
        except Exception:
            pass
        for idx, name in enumerate(sheets, 1):
            section = names.get(f"sheet{idx}") or f"sheet{idx}"
            try:
                root = ET.fromstring(zf.read(name))
            except Exception:
                continue
            for row in [r for r in root.iter() if r.tag.endswith("}row")]:
                vals = []
                for c in [x for x in row if x.tag.endswith("}c")]:
                    t = c.get("t")
                    v = ""
                    for node in c:
                        if node.tag.endswith("}v"):
                            v = node.text or ""
                        elif node.tag.endswith("}is"):
                            v = "".join(x.text or "" for x in node.iter() if x.tag.endswith("}t"))
                    if t == "s":
                        try:
                            v = shared[int(v)]
                        except Exception:
                            pass
                    if v:
                        vals.append(f"{c.get('r','')}:{norm_ws(v)}")
                if vals:
                    units.append(("para", section, " | ".join(vals)))
    return units


def split_plain(text, page=None):
    """Split plain text into (kind, section, text) units honouring markdown headings."""
    units, section = [], "body"
    for block in re.split(r"\n\s*\n|\r\n\s*\r\n", text):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", block)
        if m:
            section = norm_ws(m.group(2))[:80]
            rest = block[m.end():].strip()
            units.append(("head", section, section))
            if rest:
                for line in rest.splitlines():
                    if line.strip():
                        units.append(("para", section, norm_ws(line)))
            continue
        for line in block.splitlines():
            line = norm_ws(line)
            if not line:
                continue
            if re.match(r"^\d+(?:\.\d+)*[.、)]?\s+\S", line) and len(line) < 90:
                section = line[:80]
                units.append(("head", section, section))
            else:
                units.append(("para", section, line))
    return units


def guess_type(ext):
    ext = (ext or "").lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".docx", ".docm"):
        return "docx"
    if ext in (".xlsx", ".xlsm"):
        return "xlsx"
    if ext == ".pptx":
        return "pptx"
    if ext in (".csv", ".tsv"):
        return "csv"
    if ext in (".json", ".yaml", ".yml", ".xml"):
        return "structured"
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"):
        return "image"
    if ext in TEXT_EXT:
        return "text"
    if ext == ".doc":
        return "doc_legacy"
    if ext == ".xls":
        return "xls_legacy"
    return "binary"


# --------------------------------------------------------------- sidecar metadata
def resolve_metadata(record, doc_paths):
    """Match a sidecar record to a library document by path/name, return (doc_path, fields)."""
    if not isinstance(record, dict):
        return None, {}
    target = None
    for k in ("path", "file", "filename", "file_name", "path_rel", "location", "doc", "document"):
        v = record.get(k)
        if isinstance(v, str) and v.strip():
            target = v.strip().replace("\\", "/")
            break
    fields = {}
    for k, v in record.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            fields[str(k)] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v):
            fields[str(k)] = v
    if not target:
        return None, fields
    tn = target.lower().lstrip("./")
    for p in doc_paths:
        pl = str(p).replace("\\", "/").lower()
        if pl.endswith(tn) or tn.endswith(pl.split("library/")[-1]) or Path(pl).name == Path(tn).name:
            return p, fields
    return None, fields


def load_sidecars(roots, case, doc_paths):
    """Parse metadata / alias / version-note sidecars (files and case.json structures)."""
    aux, sources = [], []
    candidates = []
    for root in roots:
        try:
            for p in sorted(Path(root).rglob("*")):
                if p.is_file() and p.suffix.lower() in (".json", ".csv", ".tsv", ".md", ".txt") \
                        and AUX_NAME.search(p.name):
                    candidates.append(p)
        except Exception:
            continue
    if isinstance(case, dict):
        for key in ("metadata", "meta", "aliases", "alias_map", "version_notes", "documents",
                    "files", "manifest", "catalog", "inventory", "notes"):
            val = case.get(key)
            if isinstance(val, (list, dict)) and val:
                aux.append({"source": f"case.json:{key}", "key": key, "records": val})
    for p in candidates:
        try:
            if p.suffix.lower() == ".json":
                data = jload(p)
                if isinstance(data, dict):
                    for k in ("documents", "files", "records", "entries", "items", "docs"):
                        if isinstance(data.get(k), list):
                            data = data[k]
                            break
                    else:
                        data = [dict(v, path=k) if isinstance(v, dict) else {"path": k, "note": v}
                                for k, v in data.items()]
                if isinstance(data, list):
                    aux.append({"source": str(p), "key": p.name, "records": data})
                    sources.append(str(p))
            elif p.suffix.lower() in (".csv", ".tsv"):
                with open(p, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
                    rows = list(csv.DictReader(fh, delimiter="\t" if p.suffix.lower() == ".tsv" else ","))
                if rows:
                    aux.append({"source": str(p), "key": p.name, "records": rows})
                    sources.append(str(p))
            else:
                text = read_text(p) or ""
                if text.strip():
                    aux.append({"source": str(p), "key": p.name, "records": [], "text": text[:4000]})
                    sources.append(str(p))
        except Exception as exc:
            aux.append({"source": str(p), "key": p.name, "records": [], "error": f"{type(exc).__name__}: {exc}"})
    applied = 0
    for block in aux:
        for rec in block.get("records") or []:
            doc, fields = resolve_metadata(rec, doc_paths)
            if doc is not None and fields:
                block.setdefault("applied", {})[str(doc)] = fields
                applied += 1
    return aux, applied


