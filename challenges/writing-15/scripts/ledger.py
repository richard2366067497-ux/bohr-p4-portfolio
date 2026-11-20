#!/usr/bin/env python3
"""writing-15 | long-document source-faithful revision: ledger core.

Parsing, locator index, locator-bound quote verification, six-category consistency
ledgers, preserved-fact inventory, impact back-links, draft validation, manuscript
assembly.  Standard library only, no network, no CWD assumptions.

Design rule: every function returns data and never calls sys.exit; callers own the
exception handling and the exit code.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
import zipfile
from pathlib import Path
from xml.sax.saxutils import unescape as xml_unescape

VERSION = "1.0.0"
MAX_FILE = 4_000_000
MAX_LINES = 40_000
MAX_BLOCKS = 8000
CATEGORIES = ("term", "symbol", "definition", "numbering", "citation", "claim", "unit")
SEVERITIES = ("high", "medium", "low")

_TYPO = (
    ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
    ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"), ("\u00a0", " "),
    ("\u3000", " "), ("\ufb01", "fi"), ("\ufb02", "fl"), ("\u00ad", ""),
    ("\ufe50", ","), ("\ufe51", "`"),
)

_STOP = set("""a an and are as at be been being both but by can could due each for from had
has have how in into is it its may more most no not of on or other our per same should show
shown such than that the their them then there these they this those through to under up use
used uses using via was we were what when where which while with within would""".split())
_CJK_STOP = set("""的了是在和与及或对为中不有这那个们可会能要就都而被把从到由以进行以及因此所以
但是而且如果由于通过一个一些这些那些我们他们它们作者本文本章本节其之此即并且""".split())

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in _TYPO:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()

def sha(s: str, n: int = 16) -> str:
    return hashlib.sha256((s or "").encode("utf-8", "replace")).hexdigest()[:n]

def tokens(s: str) -> list:
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", (s or "").lower()):
        if w not in _STOP:
            out.append(w)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", s or ""):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in _CJK_STOP:
                out.append(bg)
    return out

_NUMPAT = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])")

def number_keys(text: str) -> set:
    keys = set()
    for m in _NUMPAT.finditer(text or ""):
        raw = m.group(1).replace(",", ".")
        try:
            keys.add("%g" % float(raw))
        except ValueError:
            keys.add(raw)
    return keys

def read_text(path: Path, cap: int = MAX_FILE):
    data = Path(path).read_bytes()[:cap]
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16", "latin-1"):
        try:
            return data.decode(enc), enc
        except Exception:
            continue
    return data.decode("utf-8", "replace"), "utf-8-replace"

def sniff(path: Path) -> str:
    try:
        head = Path(path).open("rb").read(8)
    except Exception:
        head = b""
    ext = Path(path).suffix.lower()
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            if any(n.startswith("word/") for n in names):
                return "docx"
            if any(n.startswith("xl/") for n in names):
                return "xlsx"
        except Exception:
            return "zip"
    return {".md": "md", ".markdown": "md", ".txt": "txt", ".text": "txt", ".json": "json",
            ".csv": "csv", ".tsv": "csv", ".tex": "tex", ".rst": "txt", ".yaml": "txt",
            ".yml": "txt", ".doc": "doc", ".xls": "xls", ".png": "binary", ".jpg": "binary",
            ".zip": "zip"}.get(ext, "txt")

def docx_lines(path: Path) -> list:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    lines = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S))
        txt = xml_unescape(re.sub(r"<[^>]+>", "", txt)).replace("\u00a0", " ")
        lines.append(txt)
    return lines

def pdf_lines(path: Path):
    if not shutil.which("pdftotext"):
        return None
    try:
        r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", "replace").splitlines()
    except Exception:
        return None

def json_lines(obj, depth: int = 0) -> list:
    ids = ("paragraph_id", "para_id", "target_id", "pid", "id", "label", "key", "anchor")
    txt = ("text", "content", "paragraph", "body", "en", "zh", "value", "sentence", "caption")
    lines = []
    if isinstance(obj, dict):
        bid = next((str(obj[k]) for k in ids if isinstance(obj.get(k), (str, int)) and str(obj[k]).strip()), "")
        body = next((obj[k] for k in txt if isinstance(obj.get(k), str) and obj[k].strip()), None)
        if body is not None and bid:
            lines.append("<!-- %s -->" % bid)
            lines.extend(body.splitlines() or [body])
            return lines
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                if depth < 8:
                    lines.extend(json_lines(v, depth + 1))
            elif isinstance(v, str) and v.strip():
                lines.append(("## " if depth <= 1 and len(v) < 80 else "") + v)
        return lines
    if isinstance(obj, list):
        for item in obj:
            lines.extend(json_lines(item, depth + 1))
        return lines
    return lines

def csv_lines(path: Path) -> list:
    text, _ = read_text(path)
    lines = []
    for i, row in enumerate(text.splitlines()):
        if not row.strip():
            continue
        if i == 0:
            lines.append("## table: %s" % Path(path).name)
        lines.append("<!-- row %d -->" % i)
        lines.append(row.replace("\t", " | "))
    return lines

MARK_ONLY = re.compile(r"^\s*(?:<!--\s*([A-Za-z0-9][A-Za-z0-9_.\-]{1,24})\s*-->"
                       r"|\[\s*([A-Za-z0-9][A-Za-z0-9_.\-]{1,24})\s*\]"
                       r"|\{#\s*([A-Za-z0-9][A-Za-z0-9_.\-]{1,24})\s*\})\s*$")
LEAD_MARK = re.compile(r"^\s*(?:<!--\s*([A-Za-z0-9][A-Za-z0-9_.\-]{1,24})\s*-->\s*"
                       r"|\[\s*([A-Za-z0-9][A-Za-z0-9_.\-]{1,24})\s*\]\s*"
                       r"|\{#\s*([A-Za-z0-9][A-Za-z0-9_.\-]{1,24})\s*\}\s*)")
INLINE_ID = re.compile(r"^([A-Za-z]{1,6}\d{0,3}[-_][A-Za-z]{1,3}\d{1,5})\s*(?:\||:|\t|—|–|-{1,2})\s+"
                     r"|^([A-Z]{1,3}\d{0,3}[-_][A-Z]{1,3}\d{2,5})\s+")
HED = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
NUM_HED = re.compile(r"^\s*(?:(?:\d+(?:\.\d+){0,3})[\.、)]?|第[一二三四五六七八九十百]+[章节]|Chapter\s+\d+)\s+\S")
RULE = re.compile(r"^\s*\|?[\s:\-|]{3,}$")

def _mark_id(line: str):
    m = MARK_ONLY.match(line)
    if m:
        return next((g for g in m.groups() if g), None)
    return None

def _kind(body: str, raw_lines: list) -> str:
    s = body.strip()
    if not s:
        return "blank"
    if len(raw_lines) >= 2 and RULE.match(raw_lines[1] or "") and "|" in (raw_lines[0] or ""):
        return "table"
    if s.startswith("$$") or s.startswith("\\begin{equation") or s.startswith("\\["):
        return "formula"
    if re.match(r"^\s*(?:Figure|Fig\.?|Table|图|表)\s*\d{1,3}\s*[\.:：]", s):
        return "caption"
    return "paragraph"

def parse_prose(lines: list, rel: str, mid: int) -> tuple:
    blocks, sections = [], []
    sec_no, sec_title = 0, "(front matter)"
    para = 0
    pending_id = None
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        mid_id = _mark_id(line)
        if mid_id:
            pending_id = mid_id
            i += 1
            continue
        m = HED.match(line)
        is_num_hed = bool(NUM_HED.match(line)) and len(line.strip()) < 120 and not line.strip().endswith(".")
        if m or is_num_hed:
            title = (m.group(2) if m else line).strip()
            sec_no += 1
            sec_title = re.sub(r"^[\d\.\s、)]+", "", title).strip()[:80] or title[:80]
            sections.append({"material": mid, "rel": rel, "sec_no": sec_no, "title": sec_title})
            head_id = pending_id if (pending_id and re.search(r"(?:^|[-_])(H|SEC|HEAD)$", pending_id, re.I)) else None
            blocks.append(_mkblock(mid, rel, sec_no, sec_title, 0, i, i, line, title, head_id,
                                   "heading", len(blocks)))
            if head_id:
                pending_id = None
            para = 0
            i += 1
            continue
        buf, j = [], i
        while j < n and lines[j].strip() and not HED.match(lines[j]) and not _mark_id(lines[j]):
            buf.append(lines[j])
            j += 1
        lead = None
        m2 = LEAD_MARK.match(buf[0])
        if m2:
            lead = next((g for g in m2.groups() if g), None)
            buf = [LEAD_MARK.sub("", buf[0])] + buf[1:]
        body = "\n".join(buf).strip()
        if body and not (lead or pending_id):
            mi = INLINE_ID.match(body)
            if mi:
                lead = mi.group(1) or mi.group(2)
                body = body[mi.end():].strip()
        if body:
            para += 1
            blocks.append(_mkblock(mid, rel, sec_no, sec_title, para, i, j - 1, "\n".join(buf), body,
                                   lead or pending_id, _kind(body, buf), len(blocks)))
        pending_id = None
        i = j
    return blocks, sections

def _mkblock(mid, rel, sec_no, sec_title, para, start, end, raw, body, bid, kind, order):
    if kind == "heading":
        loc = "%s §%d %s (heading)" % (rel, sec_no, sec_title)
        key = "%s|%d|H" % (rel, sec_no)
    else:
        loc = "%s §%d %s ¶%d" % (rel, sec_no, sec_title, para)
        key = "%s|%d|%d" % (rel, sec_no, para)
    if bid:
        loc = "%s · %s" % (loc, bid)
    return {"bid": order, "material": mid, "rel": rel, "sec_no": sec_no, "sec_title": sec_title,
            "para": para, "kind": kind, "start": start, "end": end, "raw": raw, "body": body,
            "id": bid or "", "loc": loc, "loc_key": key, "chars": len(body), "sha": sha(body, 12)}

def load_materials(input_dir: Path):
    notes, mats = [], []
    if not input_dir or not Path(input_dir).is_dir():
        return mats, ["input directory not found: %s" % input_dir]
    files = []
    for p in sorted(Path(input_dir).rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = p.relative_to(input_dir).as_posix()
        if re.match(r"^(case[^/]*\.json|task\.md|task_instruction[^/]*)$", rel, re.I):
            continue
        if "__MACOSX" in rel:
            continue
        if re.search(r"work[_\-]?order|interface-example|output[_\-]?contract", rel, re.I):
            notes.append("%s: metadata file, indexed as neither case nor material" % rel)
            continue
        files.append(p)
    if len(files) > 120:
        notes.append("material count %d exceeds 120; only the first 120 are indexed" % len(files))
        files = files[:120]
    for mid, p in enumerate(files):
        rel = p.relative_to(input_dir).as_posix()
        kind = sniff(p)
        rec = {"idx": mid, "rel": rel, "path": str(p), "kind": kind, "status": "parsed",
               "note": "", "lines": [], "chars": 0, "enc": ""}
        try:
            if kind in ("md", "txt", "tex"):
                text, enc = read_text(p)
                rec["enc"] = enc
                rec["lines"] = text.splitlines()[:MAX_LINES]
                if len(text.splitlines()) > MAX_LINES:
                    rec["note"] = "truncated at %d lines" % MAX_LINES
                rec["chars"] = len(text)
            elif kind == "docx":
                rec["lines"] = docx_lines(p)[:MAX_LINES]
                rec["note"] = "docx flattened to paragraphs; heading styles not preserved"
                rec["chars"] = sum(len(x) for x in rec["lines"])
            elif kind == "pdf":
                ls = pdf_lines(p)
                if ls is None:
                    rec["status"] = "degraded"
                    rec["note"] = "no pdftotext or unreadable PDF; text not extracted (nothing invented)"
                else:
                    rec["lines"] = ls[:MAX_LINES]
                    rec["chars"] = sum(len(x) for x in ls)
            elif kind == "json":
                text, enc = read_text(p)
                if re.search(r'"output_contract"|"organizer_edit_workorder"', text) and len(text) < 50000:
                    rec["status"] = "skipped"
                    rec["note"] = "case metadata JSON, not source material (nothing guessed)"
                    rec["lines"] = []
                    notes.append("%s: %s" % (rel, rec["note"]))
                    mats.append(rec)
                    continue
                rec["enc"] = enc
                try:
                    obj = json.loads(text)
                except Exception as exc:
                    rec["status"] = "degraded"
                    rec["note"] = "invalid JSON (%s); raw text indexed instead" % str(exc)[:80]
                    rec["lines"] = text.splitlines()[:MAX_LINES]
                else:
                    rec["lines"] = json_lines(obj)[:MAX_LINES]
                    rec["note"] = "JSON rendered to blocks with id markers"
                rec["chars"] = sum(len(x) for x in rec["lines"])
            elif kind == "csv":
                rec["lines"] = csv_lines(p)[:MAX_LINES]
                rec["chars"] = sum(len(x) for x in rec["lines"])
            else:
                rec["status"] = "skipped"
                rec["note"] = "unsupported material type '%s'; not parsed, nothing guessed" % kind
            if not rec["lines"] and rec["status"] == "parsed":
                rec["status"] = "unreadable"
                rec["note"] = rec["note"] or "no extractable text"
        except Exception as exc:
            rec["status"] = "unreadable"
            rec["note"] = "read failed: %r" % (exc,)
        if rec["status"] != "parsed":
            notes.append("%s: %s" % (rel, rec["note"]))
        rec["sha"] = sha("\n".join(rec["lines"]), 16)
        mats.append(rec)
    return mats, notes

def build_index(input_dir, input_notes=None) -> dict:
    mats, notes = load_materials(Path(input_dir) if input_dir else None)
    notes = list(input_notes or []) + notes
    blocks, sections, truncated = [], [], False
    for m in mats:
        if not m["lines"]:
            continue
        try:
            bs, ss = parse_prose(m["lines"], m["rel"], m["idx"])
        except Exception as exc:
            m["status"], m["note"] = "unreadable", "split failed: %r" % (exc,)
            notes.append("%s: %s" % (m["rel"], m["note"]))
            continue
        for b in bs:
            b["bid"] = len(blocks)
            blocks.append(b)
        sections.extend(ss)
    if len(blocks) > MAX_BLOCKS:
        truncated = True
        notes.append("block count %d exceeds %d; index truncated" % (len(blocks), MAX_BLOCKS))
        blocks = blocks[:MAX_BLOCKS]
    return {"version": VERSION, "blocks": blocks, "sections": sections, "materials": mats,
            "notes": notes, "truncated": truncated,
            "stats": {"materials": len(mats), "blocks": len(blocks),
                      "chars": sum(m["chars"] for m in mats),
                      "with_id": sum(1 for b in blocks if b["id"]),
                      "sections": len(sections),
                      "unreadable": sum(1 for m in mats if m["status"] != "parsed")}}

def by_id(ix: dict, ident: str):
    if not ident:
        return None
    ident = str(ident).strip()
    for b in ix["blocks"]:
        if b["id"] == ident:
            return b
    low = ident.lower()
    for b in ix["blocks"]:
        if b["id"].lower() == low:
            return b
    return None

def resolve_locator(ix: dict, loc: str):
    if not loc:
        return None
    s = str(loc).strip()
    for b in ix["blocks"]:
        if b["loc"] == s:
            return b
    m = re.search(r"([A-Za-z][A-Za-z0-9_.\-]{1,24})\s*$", s.split("·")[-1].strip()) if "·" in s else None
    if m:
        b = by_id(ix, m.group(1))
        if b:
            return b
    b = by_id(ix, s)
    if b:
        return b
    sec = re.search(r"§\s*(\d+)", s)
    par = re.search(r"¶\s*(\d+)", s)
    path = s.split("§")[0].strip().rstrip("·").strip()
    path = path.split("·")[0].strip()
    cands = ix["blocks"]
    if path:
        exact = [b for b in cands if b["rel"] == path or b["rel"].endswith(path) or path.endswith(b["rel"])]
        cands = exact or cands
    if sec:
        cands = [b for b in cands if b["sec_no"] == int(sec.group(1))] or cands
    if par:
        cands = [b for b in cands if b["para"] == int(par.group(1))]
        if len(cands) == 1:
            return cands[0]
    if "(heading)" in s:
        h = [b for b in cands if b["kind"] == "heading"]
        if len(h) == 1:
            return h[0]
    return None

def resolve_target(ix: dict, tid: str) -> dict:
    b = by_id(ix, tid)
    if b:
        return {"block": b, "resolution": "id", "note": ""}
    m = re.match(r"^\s*([A-Za-z]{1,8})[\-_ ]?([A-Za-z]{0,3})(\d{1,5})\s*$", str(tid or ""))
    if not m:
        return {"block": None, "resolution": "none", "note": "id does not look like <chapter>-P<nnn>"}
    chap, n = m.group(1) + (m.group(2) or ""), int(m.group(3))
    pool = [x for x in ix["blocks"] if chap.lower() in x["rel"].lower() or
            chap.lower() in (x["sec_title"] or "").lower()]
    hit = [x for x in pool if x["para"] == n and x["kind"] != "heading"]
    if len(hit) == 1:
        return {"block": hit[0], "resolution": "heuristic",
                "note": "no marker for %s; matched chapter token '%s' and paragraph index ¶%d" % (tid, chap, n)}
    wide = [x for x in ix["blocks"] if x["para"] == n and x["kind"] != "heading"]
    if len(wide) == 1:
        return {"block": wide[0], "resolution": "heuristic",
                "note": "no marker for %s; matched sole paragraph ¶%d in the corpus" % (tid, n)}
    return {"block": None, "resolution": "none",
            "note": "no marker and %d paragraph candidates for ¶%d" % (len(wide), n)}

def find_quote(ix: dict, quote: str, block=None) -> dict:
    nq = norm(quote)
    if not nq:
        return {"ok": False, "where": "empty", "block": None, "candidates": []}
    if block is not None and nq in norm(block["raw"]):
        return {"ok": True, "where": "block", "block": block, "candidates": [block["loc"]]}
    hits = []
    cross = []
    for b in ix["blocks"]:
        if nq in norm(b["raw"]):
            hits.append(b)
        elif nq in norm(b["body"]):
            hits.append(b)
    if hits:
        return {"ok": True, "where": "other_block", "block": hits[0],
                "candidates": [h["loc"] for h in hits[:5]]}
    for m in ix["materials"]:
        if m.get("lines") and nq in norm("\n".join(m["lines"])):
            cross.append(m["rel"])
    if cross:
        return {"ok": True, "where": "cross_block", "block": None, "candidates": cross[:5]}
    return {"ok": False, "where": "not_found", "block": None, "candidates": []}
ANN_HEAD = "> **〔%s · 编辑注记 · %s〕**"

def annotation_lines(a: dict) -> list:
    out = [ANN_HEAD % (a.get("annotation_id") or "EA", a.get("target_id") or "")]
    for ln in str(a.get("text") or "").splitlines() or [""]:
        out.append("> " + ln if ln.strip() else ">")
    if a.get("anchor_quote"):
        out.append("> ")
        out.append("> 锚点原文：%s" % str(a["anchor_quote"]).replace("\n", " ")[:300])
    out.append("> 依据：%s" % (", ".join(str(e.get("locator") or "") for e in a.get("evidence") or []
                                     if isinstance(e, dict)) or a.get("locator") or ""))
    return out

def assemble(ix: dict, placements: dict) -> dict:
    out, chunks, applied = [], [], 0
    for m in ix["materials"]:
        if not m.get("lines"):
            continue
        head_idx = len(out)
        out.append("<!-- source: %s | %s | %d lines -->" % (m["rel"], m["kind"], len(m["lines"])))
        for i, line in enumerate(m["lines"]):
            out.append(line)
            for a in placements.get((m["idx"], i), []):
                out.append("")
                out.extend(annotation_lines(a))
                applied += 1
        chunks.append({"rel": m["rel"], "material": m["idx"], "head": head_idx,
                       "body_start": head_idx + 1, "body_end": len(out) - 1, "lines": len(m["lines"])})
        out.append("")
    return {"lines": out, "text": "\n".join(out) + "\n", "chunks": chunks, "applied": applied}

def strip_annotations(lines: list) -> list:
    keep, in_ann = [], False
    for ln in lines:
        if ln.startswith("> **〔"):
            in_ann = True
            continue
        if in_ann:
            if ln.startswith(">"):
                continue
            in_ann = False
            if not ln.strip():
                continue
        keep.append(ln)
    return keep

def split_output(lines: list) -> dict:
    body = strip_annotations(lines)
    out, cur = {}, None
    for ln in body:
        m = re.match(r"^<!-- source: (.+?) \| ", ln or "")
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        if cur is not None:
            out[cur].append(ln)
    return out

def preserved_inventory(ix: dict, written_lines=None) -> dict:
    ref = split_output(written_lines) if written_lines is not None else None
    units, by_rel_before, by_rel_after = [], {}, {}
    for m in ix["materials"]:
        by_rel_before[m["rel"]] = len(m.get("lines") or [])
        if ref is not None:
            got = ref.get(m["rel"], [])
            by_rel_after[m["rel"]] = len(got)
    total_bad = 0
    for b in ix["blocks"]:
        u = {"unit_id": "PF-%04d" % (len(units) + 1), "type": b["kind"], "locator": b["loc"],
             "chars": b["chars"], "sha": b["sha"], "preserved": True}
        if ref is not None:
            got = "\n".join(ref.get(b["rel"], []))
            u["preserved"] = norm(b["raw"]) in norm(got) if norm(b["raw"]) else True
            if not u["preserved"]:
                total_bad += 1
        units.append(u)
    counts = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1
    return {"units": units, "counts": counts, "total": len(units), "not_preserved": total_bad,
            "line_counts_before": by_rel_before,
            "line_counts_after": by_rel_after if ref is not None else {},
            "basis": "per-block normalised substring test against the written manuscript",
            "sample": units[:400]}

def coverage_matrix(ix, vr, ledger, receipts, degradations, targets) -> dict:
    ev = sum(len([e for e in a.get("evidence") or [] if isinstance(e, dict) and e.get("quote")]) +
             (1 if a.get("anchor_quote") else 0) for a in vr["accepted"])
    return {
        "effect": {"targets_total": len(targets), "targets_done": vr["summary"]["targets_covered"],
                   "annotations_applied": len(vr["accepted"]),
                   "consistency_categories": len([c for c, v in ledger["counts"].items() if v > 0]),
                   "categories_required": list(CATEGORIES)},
        "gain": {"verbatim_evidence_items": ev,
                 "agent_findings": len(vr["findings"]),
                 "computed_findings": ledger["finding_count"],
                 "impact_backlinks": sum(len(a.get("affects") or []) for a in vr["accepted"]),
                 "preserved_units": None},
        "innovation": {"locator_bound_quotes": True, "impact_backlinks": True,
                       "separated_basis_sections": True, "replay_manifest": True},
        "reliability": {"fault_probes": len(receipts.get("fault_injections") or []),
                        "degradations": len(degradations or []),
                        "status": None},
        "ecosystem": {"reference_tables": 3, "commands": 5,
                      "docs": ["SKILL.md", "references/workflow.md",                                "references/checks.md"]},
    }

def _load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig")), None
    except Exception as exc:
        return None, "%s: %r" % (Path(p).name, exc)

def find_case(inp):
    errs, cands = [], []
    if inp.is_dir():
        cands = sorted(inp.glob("*.json"))
    for p in cands:
        obj, err = _load_json(p)
        if err:
            errs.append(err)
            try:
                raw = Path(p).read_text(encoding="utf-8-sig", errors="replace")
                m = re.search(r'"case_id"\s*:\s*"([^"]{1,64})"', raw)
                if m:
                    return {"case_id": m.group(1), "_damaged": True}, p, errs
            except Exception:
                pass
            continue
        if isinstance(obj, dict) and (obj.get("case_id") or obj.get("output_contract")):
            return obj, p, errs
    for p in cands[:1]:
        obj, _ = _load_json(p)
        if isinstance(obj, dict):
            return obj, p, errs
    if not cands:
        errs.append("no case JSON found in %s" % inp)
    return None, None, errs

def find_wo(case, inp):
    wo = {}
    for k, v in (case or {}).items():
        if re.search(r"work\s*[-_]?\s*order", str(k), re.I) and isinstance(v, (dict, list)):
            wo = dict(v) if isinstance(v, dict) else {"targets": v}
    if inp.is_dir():
        for p in sorted(inp.rglob("*workorder*.json")):
            obj, _ = _load_json(p)
            if isinstance(obj, dict):
                wo = {**wo, **obj}
    return wo

def wo_items(wo):
    raw = (wo or {}).get("target_ids") or (wo or {}).get("targets") or (wo or {}).get("edits") or []
    if isinstance(raw, dict):
        raw = [{"target_id": k, "instruction": v} if isinstance(v, str) else {"target_id": k, **(v or {})}
               for k, v in raw.items()]
    items = []
    for t in (raw if isinstance(raw, list) else []):
        if isinstance(t, str):
            items.append({"item_id": "WO-%02d" % (len(items) + 1), "target_id": t, "requirement": ""})
        elif isinstance(t, dict):
            tid = t.get("target_id") or t.get("id") or t.get("target") or t.get("paragraph_id")
            if tid:
                items.append({"item_id": "WO-%02d" % (len(items) + 1), "target_id": str(tid),
                              "requirement": str(t.get("instruction") or t.get("task") or t.get("note") or "")})
    if not items and (wo or {}).get("target_id"):
        items = [{"item_id": "WO-01", "target_id": str(wo["target_id"]), "requirement": ""}]
    return items

ID_PAT = re.compile(r"\b([A-Za-z]{1,6}\d{0,3}[-_][A-Za-z]{0,3}\d{1,5})\b")

def implicit_targets(text, index_ids):
    seen, out = set(), []
    for m in ID_PAT.finditer(text or ""):
        tid = m.group(1)
        if tid in seen or tid not in index_ids:
            continue
        seen.add(tid)
        out.append({"item_id": "WO-%02d" % (len(out) + 1), "target_id": tid,
                    "requirement": "id named in the instruction (no explicit workorder)"})
    return out

