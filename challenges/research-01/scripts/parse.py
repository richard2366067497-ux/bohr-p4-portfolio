#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse.py - research-01 input discovery, parsing, segmentation, index and locators.

Discovery, parsing (pdf/docx/html/text/structured), sentence-level indexing with
locators and verbatim quote localisation. Standard library only, offline, independent of CWD.
"""

import csv
import html as _html
import io
import json
import os
import re
import subprocess
import zipfile
import zlib
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
MAX_TEXT = 2_000_000
MAX_FILE = 24 * 1024 * 1024

TEXT_EXT = {".md", ".markdown", ".txt", ".text", ".rst", ".tex", ".html", ".htm", ".json",
            ".jsonl", ".ndjson", ".csv", ".tsv", ".yaml", ".yml", ".bib"}
TABLE_EXT = {".jsonl", ".ndjson", ".csv", ".tsv", ".json"}
META_NAMES = {"case.json", "task.md", "readme.md", "readme.txt"}

SQ_FIELDS = ["sq_id", "text", "object", "mechanism", "method", "time_scope",
             "comparison", "evidence_requirement"]
LAYERS = ["what", "how_far", "why", "what_missing"]
STATUSES = ["established", "provisional", "contested", "undetermined"]
CONFIDENCE = ["high", "medium", "low"]
F_TYPES = ["material_fact", "inference", "undetermined"]
OQ_TYPES = ["retrieval_gap", "unresolved_conflict", "method_limitation", "scope_limit"]

DEFAULT_CONTRACT = ["case_id", "research_question", "sub_questions", "search_plan",
                    "evidence_matrix", "findings", "synthesis", "conflicts",
                    "open_questions", "sources", "status"]


# --------------------------------------------------------------------------- paths
def _try_dir(p):
    if p is None:
        return None
    try:
        q = Path(p)
        q.mkdir(parents=True, exist_ok=True)
        probe = q / ".write_probe"
        probe.write_text("ok", "utf-8")
        probe.unlink()
        return q.resolve()
    except Exception:
        return None


def resolve_paths(inp=None, work=None, out=None):
    ip = None
    for c in [inp, os.environ.get("RESEARCH_INPUT"), "/input",
              str(SKILL_ROOT / "input"), str(Path.cwd() / "input")]:
        if c and Path(c).is_dir():
            ip = Path(c).resolve()
            break
    if ip is None:
        ip = Path(inp or "/input")
    op = None
    for c in [out, "/app/output", str(Path.cwd() / "output"), str(SKILL_ROOT / "output")]:
        op = _try_dir(c)
        if op:
            break
    if op is None:
        op = _try_dir(Path.cwd()) or Path.cwd()
    wp = None
    for c in [work, "/app/work", str(op / "work"), str(SKILL_ROOT / "work")]:
        wp = _try_dir(c)
        if wp:
            break
    if wp is None:
        wp = op
    return ip, wp, op


# --------------------------------------------------------------------------- parsing
def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read(MAX_FILE)
    if len(raw) > MAX_TEXT * 3:
        raw = raw[: MAX_TEXT * 3]
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return raw.decode(enc), enc, (len(raw) >= MAX_FILE)
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8-replace", len(raw) >= MAX_FILE


_PDF_ESC = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
            "(": "(", ")": ")", "\\": "\\"}


def _pdf_literal(buf):
    """Decode a PDF literal string body (bytes, escapes included)."""
    out = []
    i = 0
    n = len(buf)
    while i < n:
        c = buf[i:i + 1]
        if c == b"\\":
            nxt = buf[i + 1:i + 2]
            if nxt in b"nrtbf()\\":
                out.append(_PDF_ESC.get(nxt.decode("latin-1"), ""))
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", buf[i + 1:i + 4])
            if m:
                out.append(chr(int(m.group(0), 8) & 0xFF))
                i += 1 + len(m.group(0))
                continue
            i += 2
            continue
        out.append(c.decode("latin-1"))
        i += 1
    return "".join(out)


_PDF_TOKEN = re.compile(
    rb"\((?:\\.|[^()\\])*\)|\[(?:\\.|[^\]\\])*\]\s*TJ|<[0-9A-Fa-f\s]+>\s*Tj|[Tt][dD]|T\*|ET|BT", re.S)


def _pdf_stream_text(data):
    parts = []
    for m in _PDF_TOKEN.finditer(data):
        tok = m.group(0)
        if tok.startswith(b"("):
            parts.append(_pdf_literal(tok[1:-1]))
        elif tok.startswith(b"["):
            inner = tok[: tok.rfind(b"]") + 1]
            chunk = []
            for sm in re.finditer(rb"\((?:\\.|[^()\\])*\)|<[0-9A-Fa-f\s]+>", inner):
                s = sm.group(0)
                if s.startswith(b"("):
                    chunk.append(_pdf_literal(s[1:-1]))
                else:
                    try:
                        hx = re.sub(rb"\s+", b"", s[1:-1])
                        if len(hx) % 2:
                            hx += b"0"
                        b = bytes.fromhex(hx.decode("latin-1"))
                        chunk.append(b.decode("utf-16-be", "replace") if b[:2] == b"\xfe\xff"
                                     else b.decode("latin-1", "replace"))
                    except Exception:
                        pass
            parts.append("".join(chunk))
        elif tok[:1] in (b"T", b"t") or tok == b"ET":
            parts.append("\n")
    return "".join(parts)


def pdf_text(path):
    try:
        r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                           capture_output=True, timeout=25)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.decode("utf-8", "replace"), "pdftotext"
    except Exception:
        pass
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_FILE)
        chunks = []
        for m in re.finditer(rb"stream\r?\n?", raw):
            start = m.end()
            end = raw.find(b"endstream", start)
            if end < 0:
                continue
            blob = raw[start:end]
            try:
                data = zlib.decompress(blob)
            except Exception:
                data = blob
            if b"Tj" not in data and b"TJ" not in data:
                continue
            txt = _pdf_stream_text(data)
            if txt.strip():
                chunks.append(txt)
        out = "\n".join(chunks)
        if out.strip():
            return out, "internal-flate"
    except Exception:
        pass
    return "", "none"


def docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return "", "none"
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return _html.unescape(xml), "docx-xml"


def html_text(path):
    txt, enc, _ = read_text(path)
    txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", txt)
    txt = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return _html.unescape(txt), enc


def parse_file(path):
    """Return (text, read_method, extra_degradation_or_None)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        t, m = pdf_text(path)
        return t, m, (None if t.strip() else "pdf_no_text_layer")
    if ext == ".docx":
        t, m = docx_text(path)
        return t, m, (None if t.strip() else "docx_no_text")
    if ext in (".html", ".htm"):
        t, e = html_text(path)
        return t, e, None
    if ext in (".doc", ".ppt", ".pptx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        return "", "unsupported", "unsupported_format"
    t, e, clipped = read_text(path)
    return t, e, ("file_truncated" if clipped else None)


# --------------------------------------------------------------------------- records
REC_ID_KEYS = ["record_id", "id", "rec_id", "pmid", "doi", "title"]
REC_TITLE_KEYS = ["title", "name", "heading", "study"]
REC_YEAR_KEYS = ["year", "pub_year", "publication_year", "date"]


def _rec_from_obj(obj, src_id, locator, fallback):
    if not isinstance(obj, dict):
        return {"rec_id": fallback, "source_id": src_id, "locator": locator,
                "title": str(obj)[:160], "year": None, "doi": None, "preview": str(obj)[:160]}
    rid = None
    for k in REC_ID_KEYS:
        v = obj.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            rid = str(v).strip()[:80]
            break
    title = None
    for k in REC_TITLE_KEYS:
        if isinstance(obj.get(k), str) and obj[k].strip():
            title = obj[k].strip()[:200]
            break
    year = None
    for k in REC_YEAR_KEYS:
        v = obj.get(k)
        if v is not None and str(v).strip():
            year = str(v).strip()[:24]
            break
    doi = obj.get("doi") or obj.get("DOI")
    return {"rec_id": rid or fallback, "source_id": src_id, "locator": locator,
            "title": title or rid or fallback, "year": year,
            "doi": str(doi)[:120] if doi else None,
            "preview": json.dumps(obj, ensure_ascii=False)[:240]}


def load_records(path, rel, src_id, start_index):
    rows = []
    ext = path.suffix.lower()
    try:
        if ext in (".jsonl", ".ndjson"):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for ln, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        obj = {"raw": line[:400]}
                    rows.append(_rec_from_obj(obj, src_id, "%s#L%d" % (rel, ln),
                                              "R%03d" % (start_index + len(rows) + 1)))
        elif ext in (".csv", ".tsv"):
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
                rd = csv.DictReader(fh, delimiter="\t" if ext == ".tsv" else ",")
                for i, obj in enumerate(rd, 1):
                    rows.append(_rec_from_obj(obj, src_id, "%s#row%d" % (rel, i),
                                              "R%03d" % (start_index + len(rows) + 1)))
        elif ext == ".json":
            obj = json.loads(path.read_text("utf-8", errors="replace"))
            seq = None
            if isinstance(obj, list):
                seq = obj
            elif isinstance(obj, dict):
                for k in ("records", "items", "papers", "articles", "documents", "corpus", "data"):
                    if isinstance(obj.get(k), list):
                        seq = obj[k]
                        break
            for i, item in enumerate(seq or []):
                rows.append(_rec_from_obj(item, src_id, "%s#item[%d]" % (rel, i),
                                          "R%03d" % (start_index + len(rows) + 1)))
    except Exception:
        pass
    return rows


# --------------------------------------------------------------------------- segmentation
def split_blocks(text):
    """Split into blocks by blank lines / markdown headings; keep absolute offsets."""
    blocks = []
    buf = []
    bstart = None
    pos = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        lstart = pos
        pos += len(line)
        blank = not body.strip()
        head = bool(re.match(r"^#{1,6}\s", body))
        if (blank or head) and buf:
            blk = "".join(buf)
            blocks.append({"start": bstart, "text": blk})
            buf = []
            bstart = None
        if blank:
            continue
        if head:
            blk = body + "\n"
            blocks.append({"start": lstart, "text": blk})
            continue
        if bstart is None:
            bstart = lstart
        buf.append(line)
    if buf:
        blocks.append({"start": bstart, "text": "".join(buf)})
    return [b for b in blocks if b["text"].strip()]


_ENDERS = "。！？!?；;"
_CLOSERS = "”’\"')）]】》"


def split_sents(block_text, base):
    sents = []
    i = 0
    st = 0
    n = len(block_text)
    while i < n:
        ch = block_text[i]
        cut = False
        if ch in _ENDERS:
            j = i + 1
            while j < n and block_text[j] in _CLOSERS:
                j += 1
            i = j
            cut = True
        elif ch == "\n":
            i += 1
            cut = True
        elif ch == "." and i + 2 < n and block_text[i + 1] in " \n" and block_text[i + 2].isupper():
            i += 1
            cut = True
        else:
            i += 1
        if cut:
            seg = block_text[st:i]
            if seg.strip():
                lead = len(seg) - len(seg.lstrip())
                s = base + st + lead
                sents.append({"start": s, "end": base + i, "text": seg.strip()})
            st = i
    seg = block_text[st:]
    if seg.strip():
        lead = len(seg) - len(seg.lstrip())
        sents.append({"start": base + st + lead, "end": base + len(seg), "text": seg.strip()})
    return sents


def annotate(mat):
    """Attach block/sentence structure to a material dict."""
    blocks = split_blocks(mat["text"])
    out = []
    for bi, b in enumerate(blocks, 1):
        sents = split_sents(b["text"], b["start"])
        rows = []
        for si, s in enumerate(sents, 1):
            rows.append({"sid": "S%d" % si, "start": s["start"], "end": s["end"],
                         "text": s["text"]})
        out.append({"bid": "B%d" % bi, "start": b["start"], "text": b["text"],
                    "sents": rows})
    mat["blocks"] = out
    return mat


def make_material(mid, rel, src_path, kind, text, read_method):
    m = {"id": mid, "rel": rel, "path": str(src_path), "kind": kind,
         "read_method": read_method, "text": text, "chars": len(text)}
    return annotate(m)


# --------------------------------------------------------------------------- index
def _case_json(inp):
    for cand in [inp / "case.json"] + sorted(inp.glob("*/case.json")):
        if cand.is_file():
            try:
                return json.loads(cand.read_text("utf-8", errors="replace")), cand
            except Exception:
                return {"__invalid__": True}, cand
    return {}, None


def _task_md(inp):
    for cand in [inp / "task.md"] + sorted(inp.glob("*/task.md")):
        if cand.is_file():
            try:
                return cand.read_text("utf-8", errors="replace"), cand
            except Exception:
                return "", cand
    for cand in sorted(inp.rglob("*.md")):
        if "task" in cand.name.lower():
            try:
                return cand.read_text("utf-8", errors="replace"), cand
            except Exception:
                pass
    return "", None


def contract_fields(case):
    if not isinstance(case, dict):
        return []
    raw = None
    for k in ("output_contract", "outputContract", "contract", "deliverable_contract"):
        if case.get(k) is not None:
            raw = case[k]
            break
    fields = []
    if isinstance(raw, dict):
        props = raw.get("properties")
        if isinstance(props, dict):
            for k, v in props.items():
                fields.append({"key": k, "spec": _spec(v)})
        elif isinstance(raw.get("fields"), (dict, list)):
            fields.extend(contract_fields({"output_contract": raw["fields"]}))
        elif isinstance(raw.get("required"), list) and not any(
                k in raw for k in ("properties",)):
            for k in raw["required"]:
                fields.append({"key": str(k), "spec": ""})
            for k, v in raw.items():
                if k != "required" and k not in [f["key"] for f in fields]:
                    fields.append({"key": k, "spec": _spec(v)})
        else:
            for k, v in raw.items():
                fields.append({"key": k, "spec": _spec(v)})
    elif isinstance(raw, str):
        fields.extend(_contract_from_text(raw))
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                fields.append({"key": it, "spec": ""})
            elif isinstance(it, dict):
                key = it.get("name") or it.get("key") or it.get("field") or it.get("id")
                if key:
                    fields.append({"key": str(key), "spec": _spec(it)})
    return [f for f in fields if f["key"]]


def _contract_from_text(raw):
    """Conservative key extraction from a markdown/plain-text contract block."""
    out = []
    lines = raw.splitlines()
    for i, ln in enumerate(lines):
        cells = [c.strip().strip("`*") for c in ln.strip().strip("|").split("|")]
        if ln.strip().startswith("|") and len(cells) >= 2 and re.search(
                r"(字段|键|field|key|名称|name)", cells[0] + cells[1], re.I):
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                c = [x.strip().strip("`*") for x in row.strip().strip("|").split("|")]
                if c and re.match(r"^[A-Za-z_][A-Za-z0-9_.\-]{1,48}$", c[0] or ""):
                    out.append({"key": c[0], "spec": " | ".join(c[1:])[:300]})
            if out:
                return out
    for ln in lines:
        mm = re.match(r"^\s*[-*\d.\s]*`?([A-Za-z_][A-Za-z0-9_.\-]{1,48})`?\s*[:：]\s*(.+)$", ln)
        if mm:
            out.append({"key": mm.group(1), "spec": mm.group(2).strip()[:300]})
    return out


def _spec(v):
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)[:600]
    except Exception:
        return str(v)[:600]


def build_index(inp):
    inp = Path(inp)
    idx = {"input_dir": str(inp), "case": {}, "case_path": None, "task_md": "",
           "task_path": None, "materials": [], "records": [], "contract": [],
           "degradations": [], "errors": [], "stats": {}}
    case, cp = _case_json(inp)
    if case.get("__invalid__"):
        idx["errors"].append({"code": "case_json_invalid", "detail": "case.json is not valid JSON"})
        case = {}
    if cp is not None:
        idx["case_path"] = str(cp.relative_to(inp)) if str(cp).startswith(str(inp)) else cp.name
    else:
        idx["degradations"].append({"code": "case_json_missing", "detail": "no case.json under input"})
    idx["case"] = case if isinstance(case, dict) else {}
    task, tp = _task_md(inp)
    idx["task_md"] = task
    idx["task_path"] = str(tp.relative_to(inp)) if tp else None

    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(inp))
            if any(part.startswith(".") for part in Path(rel).parts):
                continue
            if rel in ("case.json", "task.md"):
                continue
            files.append((p, rel))
    seq = 0
    for p, rel in files:
        seq += 1
        mid = "src-%d" % seq
        low = rel.lower()
        if "protocol" in low or "prisma" in low or "search_strategy" in low:
            kind = "protocol"
        elif p.suffix.lower() in TABLE_EXT:
            kind = "table"
        else:
            kind = "source"
        try:
            text, method, deg = parse_file(p)
        except Exception as e:
            idx["errors"].append({"code": "unreadable_file", "path": rel, "detail": type(e).__name__})
            continue
        if deg:
            idx["degradations"].append({"code": deg, "path": rel})
        if p.suffix.lower() in TABLE_EXT:
            rows = load_records(p, rel, mid, len(idx["records"]))
            idx["records"].extend(rows)
        mat = make_material(mid, rel, p, kind, text, method)
        if not text.strip():
            mat["kind"] = "unreadable"
        idx["materials"].append(mat)

    # materials embedded in case.json
    for key in ("sources", "documents", "papers", "articles", "corpus", "materials"):
        seq_items = idx["case"].get(key)
        if not isinstance(seq_items, list):
            continue
        for i, item in enumerate(seq_items):
            seq += 1
            mid = "src-%d" % seq
            if isinstance(item, str):
                text = item
                rel = "case.json:%s[%d]" % (key, i)
            elif isinstance(item, dict):
                text = ""
                for tk in ("text", "full_text", "content", "body", "abstract"):
                    if isinstance(item.get(tk), str) and item[tk].strip():
                        text = item[tk]
                        break
                rel = "case.json:%s[%d]" % (key, i)
                if not text.strip():
                    idx["records"].append(_rec_from_obj(
                        item, mid, rel, "R%03d" % (len(idx["records"]) + 1)))
                    continue
            else:
                continue
            mat = make_material(mid, rel, idx["input_dir"], "source", text, "inline")
            idx["materials"].append(mat)

    for key in ("records", "records_list", "evidence_records", "items", "papers"):
        rows = idx["case"].get(key)
        if isinstance(rows, list):
            for i, item in enumerate(rows):
                rid = "R%03d" % (len(idx["records"]) + 1)
                idx["records"].append(_rec_from_obj(item, "case.json",
                                                    "case.json:%s[%d]" % (key, i), rid))

    idx["contract"] = contract_fields(idx["case"])
    if not idx["contract"]:
        idx["contract"] = [{"key": k, "spec": "default"} for k in DEFAULT_CONTRACT]
        idx["degradations"].append({"code": "contract_defaulted",
                                    "detail": "output_contract absent; default key set used"})
    idx["stats"] = {
        "materials": len(idx["materials"]),
        "readable_materials": sum(1 for m in idx["materials"] if m["text"].strip()),
        "records": len(idx["records"]),
        "contract_keys": len(idx["contract"]),
        "chars": sum(m["chars"] for m in idx["materials"]),
    }
    return idx


def question_of(idx):
    case = idx.get("case") or {}
    for k in ("research_question", "question", "task_instruction", "instruction",
              "research_goal", "brief", "title", "objective"):
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    tm = idx.get("task_md") or ""
    for line in tm.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s
    return "未提供研究问题（材料缺失）"


# --------------------------------------------------------------------------- quote maps
_MAPCH = {"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201c": '"', "\u201d": '"',
          "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " ", "\u3000": " ",
          "\u200b": "", "\u00ad": ""}


def _norm_pair(text, drop_space=False):
    out = []
    mp = []
    prev_sp = False
    for i, ch in enumerate(text):
        c = _MAPCH.get(ch, ch)
        if c == "":
            continue
        if c == " " or ch.isspace():
            if prev_sp or drop_space:
                continue
            out.append(" ")
            mp.append(i)
            prev_sp = True
            continue
        prev_sp = False
        out.append(c.lower())
        mp.append(i)
    return "".join(out), mp


def norm_str(s, drop_space=False):
    return _norm_pair(s, drop_space)[0]


def _mat_norm(mat, drop_space=False):
    key = "_norm2" if drop_space else "_norm1"
    if key not in mat:
        mat[key] = _norm_pair(mat["text"], drop_space)
    return mat[key]


def locator_for(mat, start, end=None):
    end = start + 1 if end is None else end
    for b in mat.get("blocks") or []:
        for s in b["sents"]:
            if s["start"] <= start < s["end"] or (start <= s["start"] and end >= s["end"]):
                return "%s#%s.%s chars:%d-%d" % (mat["rel"], b["bid"], s["sid"], start, s["end"])
    return "%s chars:%d-%d" % (mat["rel"], start, end)


def quote_locate(idx, quote, prefer=None):
    """Locate a verbatim quote. Returns dict with ok/source_id/locator/start/end/method."""
    q = (quote or "").strip()
    res = {"ok": False, "source_id": None, "locator": None, "reason": None, "method": None}
    if len(q) < 4:
        res["reason"] = "quote_too_short"
        return res
    mats = [m for m in idx["materials"] if m["text"].strip()]
    order = sorted(mats, key=lambda m: 0 if (prefer and m["id"] == prefer) else 1)
    qn = norm_str(q)
    qn2 = norm_str(q, drop_space=True)
    for drop, needle in ((False, qn), (True, qn2)):
        if not needle:
            continue
        for m in order:
            txt, mp = _mat_norm(m, drop)
            pos = txt.find(needle)
            if pos >= 0:
                st = mp[pos]
                en = mp[min(len(mp) - 1, pos + len(needle) - 1)] + 1
                res.update({"ok": True, "source_id": m["id"],
                            "locator": locator_for(m, st, en), "start": st, "end": en,
                            "method": "exact" if not drop else "space_insensitive"})
                return res
    # prefix hint: longest leading fragment that exists somewhere
    for m in mats:
        txt, mp = _mat_norm(m)
        for ln in (40, 28, 18, 12):
            if len(qn) <= ln:
                continue
            pos = txt.find(qn[:ln])
            if pos >= 0:
                res.update({"ok": False, "source_id": m["id"], "reason": "quote_mismatch",
                            "method": "prefix_only",
                            "locator": locator_for(m, mp[pos])})
                return res
    res["reason"] = "quote_not_found"
    return res


def quote_text_at(idx, mat_id, start, end):
    for m in idx["materials"]:
        if m["id"] == mat_id:
            return m["text"][start:end]
    return ""


def tok(s):
    s = str(s).lower()
    out = set(re.findall(r"[a-z][a-z\-]{3,}", s))
    for w in re.findall(r"[\u4e00-\u9fff]{2,}", s):
        out.update(w[i:i + 2] for i in range(max(1, len(w) - 1)))
    return out
