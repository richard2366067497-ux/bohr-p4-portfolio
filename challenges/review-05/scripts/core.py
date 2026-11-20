#!/usr/bin/env python3
"""core.py -- extraction and signal detection for the academic-compliance-matrix skill.

* every material becomes locator-bearing paragraphs (``p3#para7``); locators are the
  addressing scheme the Agent must quote back verbatim
* detect() returns the four signal families printed by ``show``: per-requirement candidate
  snippets, declaration-block hits/misses, citation markers vs bibliography entries, and
  PII candidates
* nothing here judges compliance: verdicts belong to the Agent's draft.json
"""
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from rules import (CAT, DECL, DECL_CN, DOMAINS, VERSION, find_quote, has_raw_pii,  # noqa: F401
                   mask_pii, norm)

CITE_NUM = re.compile(r"\[([0-9]{1,3}(?:\s*[-,–]\s*[0-9]{1,3})*)\]")
CITE_AUTH = re.compile(r"\(([A-Z][A-Za-z\u00C0-\u024F'\-]{1,24}"
                       r"(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z'\-]{1,24}))?,\s*(?:19|20)\d{2}[a-z]?)\)")
REF_HEAD = re.compile(r"^\s*(?:\d+[\.\s]*)?(references?|bibliography|literature\s+cited|参考文献|引用文献)\s*$", re.I)
REF_LINE = re.compile(r"^\s*[\[\(]?(\d{1,3})[\]\)\.:、\s]\s*(.*)$")
GUIDE_PATS = ("instructions?\\s+for\\s+authors", "guide\\s+for\\s+authors", "author\\s+guidelines?",
              "submission\\s+guidelines?", "投稿要求", "征稿", "call\\s+for\\s+papers")


# ---------------------------------------------------------------- extraction
def kind_of(p):
    try:
        head = Path(p).read_bytes()[:8]
    except Exception:
        return "unreadable"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(p) as z:
                names = " ".join(z.namelist()[:60])
        except Exception:
            return "zip"
        for key, kind in (("word/document", "docx"), ("xl/workbook", "xlsx"), ("ppt/presentation", "pptx")):
            if key in names:
                return kind
        return "zip"
    return "text"


DELIM = b" \t\r\n\x00\x0c()<>[]{}/%"


def _decode(b):
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be", "replace")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("cp1252", "replace")


def _literal(cs, i):
    i, buf, n = i + 1, bytearray(), len(cs)
    while i < n:
        c = cs[i]
        if c == 0x5C and i + 1 < n:
            nx = cs[i + 1]
            if nx in (0x6E, 0x72, 0x74, 0x62, 0x66):
                buf.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}[nx]); i += 2; continue
            if 0x30 <= nx <= 0x37:
                k = 0
                while k < 3 and i + 1 + k < n and 0x30 <= cs[i + 1 + k] <= 0x37:
                    k += 1
                buf.append(int(cs[i + 1:i + 1 + k], 8) & 0xFF); i += 1 + k; continue
            if nx not in (10, 13):
                buf.append(nx)
            i += 2; continue
        if c == 0x28:
            d, i = 1, i + 1
            while i < n and d:
                if cs[i] == 0x5C:
                    buf.extend(cs[i:i + 2]); i += 2; continue
                d += 1 if cs[i] == 0x28 else (-1 if cs[i] == 0x29 else 0)
                i += 1
                if d:
                    buf.append(cs[i - 1])
            continue
        if c == 0x29:
            return bytes(buf), i + 1
        buf.append(c); i += 1
    return bytes(buf), i


def _content_text(cs):
    i, n, out, args = 0, len(cs), [], []

    def emit(v):
        if v and out and out[-1] and out[-1][-1].isalnum() and v[:1].isalnum():
            out.append(" ")
        out.append(v)

    while i < n:
        c = cs[i:i + 1]
        if c in b" \t\r\n\x00\x0c":
            i += 1; continue
        if c == b"%":
            k = cs.find(b"\n", i); i = n if k < 0 else k + 1; continue
        if c == b"(":
            s, i = _literal(cs, i); args.append(("s", _decode(s))); continue
        if c == b"<":
            if cs[i + 1:i + 2] == b"<<":
                k = cs.find(b">>", i); i = n if k < 0 else k + 2; continue
            e = cs.find(b">", i)
            hexs = re.sub(rb"[^0-9A-Fa-f]", b"", cs[i + 1:e if e >= 0 else i + 1])
            i = e + 1 if e >= 0 else n
            try:
                args.append(("s", _decode(bytes.fromhex(hexs.decode()))))
            except Exception:
                pass
            continue
        if c in b"[]{}":
            i += 1; continue
        k = i
        while k < n and cs[k:k + 1] not in DELIM:
            k += 1
        tok, i = (cs[i:k], k) if k > i else (cs[i:i + 1], i + 1)
        if re.fullmatch(rb"[-+]?[\d.]+", tok):
            args.append(("n", tok.decode())); continue
        op = tok.decode("latin-1", "replace")
        if op == "TJ":
            for t, v in args:
                if t == "s":
                    out.append(v)
                else:
                    try:
                        if abs(float(v)) >= 100:
                            out.append(" ")
                    except Exception:
                        pass
        elif op == "Tj":
            for t, v in args:
                if t == "s":
                    emit(v)
        elif op in ("'", '"'):
            out.append("\n")
            out += [v for t, v in args if t == "s"]
        elif op in ("Td", "TD", "Tm", "T*", "BT", "ET"):
            out.append("\n")
        args = []
    return "".join(out)


def _streams(data):
    out, pos = [], 0
    while True:
        i = data.find(b"stream", pos)
        if i < 0:
            return out
        j = i + 6
        j += 2 if data[j:j + 2] == b"\r\n" else (1 if data[j:j + 1] in (b"\n", b"\r") else 0)
        e = data.find(b"endstream", j)
        if e < 0:
            return out
        out.append((data[max(0, i - 600):i], data[j:e]))
        pos = e + 9


def _builtin_pdf(data):
    import zlib
    pages = []
    for head, raw in _streams(data):
        if any(k in head for k in (b"Image", b"DCTDecode", b"JPXDecode")):
            continue
        body = raw
        if b"FlateDecode" in head:
            for dec in (zlib.decompress, lambda x: zlib.decompressobj().decompress(x)):
                try:
                    body = dec(raw); break
                except Exception:
                    body = raw
        try:
            if b"Tj" in body or b"TJ" in body:
                t = _content_text(body)
                if t.strip():
                    pages.append(("s%d" % (len(pages) + 1), t))
        except Exception:
            continue
    return pages, "builtin-zlib", ([] if pages else ["no extractable text layer (scan?): OCR unavailable"])


def pdf_pages(raw):
    if shutil.which("pdftotext"):
        try:
            td = Path(tempfile.mkdtemp(prefix="acm_"))
            (td / "d.pdf").write_bytes(raw)
            subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(td / "d.pdf"), str(td / "d.txt")],
                           timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pages = [("p%d" % (i + 1), t) for i, t in
                     enumerate((td / "d.txt").read_text(encoding="utf-8", errors="replace").split("\f"))
                     if t.strip()]
            if pages:
                return pages, "pdftotext", []
        except Exception:
            pass
    return _builtin_pdf(raw)


def docx_text(p):
    try:
        with zipfile.ZipFile(p) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except Exception:
        return [], "docx-failed"
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines = ["".join(x.text or "" for x in para.iter(ns + "t")) for para in root.iter(ns + "p")]
    return [("p1", "\n\n".join(x for x in lines if x.strip()))], "docx-xml"


def text_pages(p):
    b = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return [("p1", b.decode(enc))], enc
        except Exception:
            pass
    return [("p1", b.decode("utf-8", "replace"))], "replace"


def paragraphize(pages):
    paras = []
    for label, text in pages:
        t = re.sub(r"[ \t]+", " ", text or "")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
        if len(blocks) <= 1 and len(t) > 1500:
            blocks, cur = [], []
            for ln in [x.strip() for x in t.splitlines() if x.strip()]:
                cur.append(ln)
                if len(" ".join(cur)) > 600:
                    blocks.append(" ".join(cur)); cur = []
            if cur:
                blocks.append(" ".join(cur))
        k = 0
        for b in blocks:
            b = re.sub(r"-\n(?=[a-z])", "", b)
            b = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in b.split("\n"))
            b = b.strip()
            if len(b) < 3:
                continue
            if len(b) < 40 and paras and paras[-1]["locator"].split("#")[0] == label:
                paras[-1]["text"] += " " + b
                continue
            k += 1
            paras.append({"locator": "%s#para%d" % (label, k), "page": label, "text": b})
    return paras or [{"locator": "p1#para1", "page": "p1", "text": ""}]


def extract_doc(p):
    kind, notes = kind_of(Path(p)), []
    if kind == "pdf":
        pages, engine, notes = pdf_pages(Path(p).read_bytes())
        if engine != "pdftotext":
            notes.append("page numbers not authoritative; locators use %s blocks" % engine)
    elif kind == "docx":
        pages, engine = docx_text(p)
    elif kind == "text":
        pages, engine = text_pages(p)
    else:
        pages, engine = [], "unsupported"
        notes.append("%s container not parsed; ask for a PDF/CSV/text export" % kind)
    paras = paragraphize(pages)
    text = " ".join(x["text"] for x in paras)
    quality = (sum(ch.isalnum() for ch in text) / len(text)) if text else 0.0
    if text and quality < 0.5:
        notes.append("low text quality (alnum %.2f): CID font or scanned page likely" % quality)
    return {"kind": kind, "engine": engine, "paras": paras, "text": text, "n_pages": len(pages),
            "quality": round(quality, 3), "notes": notes}


# ---------------------------------------------------------------- signals
def _lines(paras):
    out = []
    for p in paras:
        for ln in p["text"].split("\n"):
            out.append((ln, p["locator"]))
    return out


def ref_region(paras):
    """Index of the reference heading line, or None."""
    lines = _lines(paras)
    return next((i for i, (ln, _) in enumerate(lines)
                 if REF_HEAD.match(re.sub(r"^[#*\s]+", "", ln)[:60])), None)


def parse_bibliography(paras):
    lines = _lines(paras)
    start = ref_region(paras)
    if start is None:
        return []
    out, cur = [], None
    for ln, loc in lines[start + 1:]:
        m = REF_LINE.match(re.sub(r"^[*\s]+", "", ln))
        if m and len(m.group(2)) > 8:
            if cur:
                out.append(cur)
            cur = [int(m.group(1)), m.group(2).strip(), loc]
        elif cur and len(ln.strip()) > 6:
            cur[1] += " " + ln.strip()
    if cur:
        out.append(cur)
    return [(n, raw[:400], loc) for n, raw, loc in out]


def cite_markers(paras):
    """In-text markers only: bibliography lines are excluded so entries are not 'citations'."""
    lines = _lines(paras)
    start = ref_region(paras)
    out = []
    for i, (ln, loc) in enumerate(lines):
        if start is not None and i >= start:
            continue
        for m in CITE_NUM.finditer(ln):
            for num in [int(x) for x in re.split(r"[,\-–]", m.group(1)) if x.strip().isdigit()]:
                out.append({"num": num, "locator": loc, "marker": m.group(0)})
        for m in CITE_AUTH.finditer(ln):
            out.append({"num": None, "locator": loc, "marker": m.group(0), "author_year": m.group(1)})
    return out


def _locate(paras, needle):
    for p in paras:
        if needle and needle in p["text"]:
            return p["locator"]
    return ""


def detect(docs):
    sig = {"seeds": {}, "declarations": {}, "pii": [], "guideline_present": False, "guideline_docs": [],
           "citations": {"markers": [], "entries": [], "dangling": [], "orphan": [], "duplicates": [],
                         "gaps": [], "n_markers": 0, "n_entries": 0}}
    seeds = [(c[0], c[1], c[2], c[3], c[4]) for c in CAT] + \
            [(d[0], "declaration", "ethical_norm", "声明区块（%s）应存在且与正文一致" % DECL_CN.get(d[1], d[1]), d[2])
             for d in DECL]
    for rid, domain, src, req, probes in seeds:
        sig["seeds"][rid] = {"row_id": rid, "domain": domain, "rule_source": src,
                             "requirement": req, "probes": probes, "candidates": []}
    for did, doc in docs.items():
        paras = doc["paras"]
        for rid, domain, src, req, probes in seeds:
            for pat in probes:
                if len(sig["seeds"][rid]["candidates"]) >= 3:
                    break
                try:
                    rx = re.compile(pat, re.I)
                except Exception:
                    continue
                seen = {(x["doc"], x["locator"]) for x in sig["seeds"][rid]["candidates"]}
                for p in paras:
                    m = rx.search(p["text"])
                    if m and (did, p["locator"]) not in seen:
                        sig["seeds"][rid]["candidates"].append(
                            {"doc": did, "locator": p["locator"], "match": m.group(0)[:80],
                             "text": p["text"][:240]})
                        break
        for dec_id, name, probes in DECL:
            for pat in probes:
                try:
                    m = re.search(pat, doc["text"], re.I)
                except Exception:
                    continue
                if m:
                    sig["declarations"].setdefault(dec_id, {"name": name, "cn": DECL_CN.get(name, name),
                                                            "found": True, "hits": []})
                    sig["declarations"][dec_id]["hits"].append(
                        {"doc": did, "locator": _locate(paras, m.group(0)), "match": m.group(0)[:80]})
                    break
        for n, raw, loc in parse_bibliography(paras):
            sig["citations"]["entries"].append({"num": n, "raw": raw, "locator": loc, "doc": did})
        for mk in cite_markers(paras):
            mk["doc"] = did
            sig["citations"]["markers"].append(mk)
        for rx, ptype in ((r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "email"),
                          (r"(?<!\d)1[3-9]\d{9}(?!\d)", "phone"),
                          (r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])", "id_number"),
                          (r"(?:patient|subject|受试者|患者)\s*(?:id|no\.?|编号|#)\s*[:：]?\s*[A-Z]{0,3}\d{1,6}",
                           "patient_id")):
            for m in re.finditer(rx, doc["text"], re.I):
                sig["pii"].append({"pii_type": ptype, "doc": did, "locator": _locate(paras, m.group(0)),
                                   "sample": mask_pii(m.group(0)), "chars": len(m.group(0))})
        for pat in GUIDE_PATS:
            if re.search(pat, doc["text"], re.I):
                sig["guideline_present"] = True
                sig["guideline_docs"].append(did)
                break
    nums = [m["num"] for m in sig["citations"]["markers"] if m.get("num")]
    enum = [e["num"] for e in sig["citations"]["entries"]]
    c = sig["citations"]
    c["dangling"] = sorted(set(nums) - set(enum))
    c["orphan"] = sorted(set(enum) - set(nums))
    c["duplicates"] = sorted({n for n in enum if enum.count(n) > 1})
    c["gaps"] = ([n for n in range(min(enum), max(enum) + 1) if n not in set(enum)][:20] if enum else [])
    c["n_markers"], c["n_entries"] = len(nums), len(enum)
    c["n_author_year"] = len([m for m in sig["citations"]["markers"] if m.get("author_year")])
    sig["guideline_docs"] = sorted(set(sig["guideline_docs"]))
    sig["pii"] = sig["pii"][:40]
    return sig


def seed_skeleton(sig):
    """Matrix skeleton: one row per catalogue entry, no verdicts invented."""
    rows = []
    for rid, s in sig["seeds"].items():
        rows.append({"row_id": rid, "domain": s["domain"], "rule_source": s["rule_source"],
                     "requirement": s["requirement"], "expected": "", "observed": "", "verdict": None,
                     "doc_id": "", "evidence_locator": "", "quote": "", "searched_scope": "",
                     "severity": "", "severity_reason": "", "remediation": "", "what_human_must_check": ""})
    rows.sort(key=lambda r: (DOMAINS.index(r["domain"]) if r["domain"] in DOMAINS else 9, r["row_id"]))
    return rows


def sort_rows(rows):
    def key(r):
        d = str(r.get("domain") or "").lower()
        return (DOMAINS.index(d) if d in DOMAINS else 9, str(r.get("row_id") or ""))
    return sorted(rows, key=key)


# ---------------------------------------------------------------- show (presentation of the index)
def show_index(idx, domain=None, doc=None, paras=None, grep=None):
    """Print locator-bearing candidates so the Agent can quote them verbatim."""
    sig, para_map, docs = idx.get("signals") or {}, idx.get("paras") or {}, idx.get("docs") or {}
    if grep:
        try:
            rx = re.compile(grep, re.I)
        except Exception as e:
            print("bad regex %r: %r" % (grep, e))
            return
        for did, ps in para_map.items():
            for p in ps:
                if rx.search(p["text"]):
                    print("[%s %s] %s" % (did, p["locator"], p["text"][:600]))
        return
    if doc and doc in para_map:
        ps = para_map[doc]
        m = re.match(r"^(\d+)\s*[:\-]\s*(\d+)$", str(paras or ""))
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, len(ps))
        for p in ps[lo - 1:hi]:
            print("[%s %s] %s" % (doc, p["locator"], p["text"][:1500]))
        print("-- %s: %d paragraphs, showed %d..%d" % (doc, len(ps), lo, min(hi, len(ps))))
        return
    print("== materials ==")
    for k, d in docs.items():
        print("%s | %s | %s | %s paras | quality %.2f | %s" % (
            k, d.get("filename"), d.get("kind"), d.get("n_paras"), d.get("quality") or 0, d.get("engine")))
    print("\n== requirement seeds: candidate evidence, quote verbatim ==")
    for r in idx.get("seed_rows") or []:
        if domain and r["domain"] != domain:
            continue
        s = (sig.get("seeds") or {}).get(r["row_id"], {})
        print("\n%s | %s | %s | %s" % (r["row_id"], r["domain"], r["rule_source"], r["requirement"]))
        for c in (s.get("candidates") or [])[:3]:
            print("   [%s %s] ...%s..." % (c["doc"], c["locator"], norm(c["text"])[:200]))
        if not s.get("candidates"):
            print("   (no keyword hit: likely not_applicable, or search manually with --grep)")
    print("\n== declarations ==")
    for dec_id, name, _ in DECL:
        hit = (sig.get("declarations") or {}).get(dec_id)
        print("%s | %-20s | %s" % (dec_id, name, ("FOUND " + "; ".join(
            "%s %s" % (h["doc"], h["locator"]) for h in hit["hits"][:2])) if hit else "not found"))
    c = sig.get("citations") or {}
    print("\n== citations == markers=%s entries=%s dangling=%s orphan=%s duplicate=%s gaps=%s" % (
        c.get("n_markers"), c.get("n_entries"), c.get("dangling"), c.get("orphan"),
        c.get("duplicates"), c.get("gaps")))
    for e in (c.get("entries") or [])[:12]:
        print("   ref[%s] %s @%s" % (e["num"], norm(e["raw"])[:110], e["locator"]))
    print("\n== pii candidates ==")
    for p in (sig.get("pii") or [])[:15]:
        print("   %s | %s | %s | %s" % (p["pii_type"], p["doc"], p["locator"], p["sample"]))


# ---------------------------------------------------------------- selfcheck (read-only)
def selfcheck(out, keys=()):
    """Re-verify the produced artifacts; returns True when every check passes."""
    import csv
    import json
    ok = []

    def add(name, cond, detail=""):
        ok.append(bool(cond))
        print("%s %-26s %s" % ("PASS" if cond else "FAIL", name, detail))

    rd = lambda n: (Path(out) / n).read_text(encoding="utf-8")
    try:
        res = json.loads(rd("result.json"))
    except Exception as e:
        add("result_json_parses", False, repr(e))
        return False
    add("result_json_parses", True, str(Path(out) / "result.json"))
    absent = [k for k in keys if k not in res]
    add("contract_keys_complete", not absent, "missing %s" % absent if absent else "%d keys" % len(keys))
    add("case_id_present", bool(res.get("case_id")), str(res.get("case_id")))
    add("status_valid", res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"),
        str(res.get("status")))
    rows = res.get("compliance_matrix") or []
    add("matrix_non_empty", bool(rows), "%d rows" % len(rows))
    order = [(DOMAINS.index(norm(r.get("domain")).lower()) if norm(r.get("domain")).lower() in DOMAINS else 9,
              str(r.get("row_id"))) for r in rows]
    add("matrix_sorted", order == sorted(order), "(domain, row_id)")
    ungated = [r.get("row_id") for r in rows if norm(r.get("verdict")).lower() == "violation"
               and not (norm(r.get("quote")) and norm(r.get("evidence_locator")))]
    add("violation_evidence_gate", not ungated, "ungated %s" % ungated[:6] if ungated else "all gated")
    ids = {r.get("row_id") for r in rows}
    orphan = [f.get("finding_id") for f in (res.get("findings") or []) if f.get("matrix_row_id") not in ids]
    add("findings_traceable", not orphan, "orphans %s" % orphan[:6] if orphan
        else "%d findings back-referenced" % len(res.get("findings") or []))
    try:
        led = json.loads(rd("pii_ledger.json"))
        leak = [e.get("ledger_id") for e in led.get("entries") or []
                if has_raw_pii(json.dumps(e, ensure_ascii=False))]
        add("pii_ledger_redacted", not leak, "leaking %s" % leak if leak
            else "%d entries" % len(led.get("entries") or []))
    except Exception as e:
        add("pii_ledger_redacted", False, repr(e))
    try:
        rep = rd("compliance_report.md")
        gone = [n for n in ("## 1. 合规矩阵", "## 2. 违规清单", "## 3. 待人工核实", "## 4. 整改建议")
                if n not in rep]
        add("report_sections", not gone and len(rep) > 400, "missing %s" % gone if gone else "%d chars" % len(rep))
        add("report_pii_masked", not has_raw_pii(rep), "raw PII in report" if has_raw_pii(rep) else "clean")
    except Exception as e:
        add("report_sections", False, repr(e))
    try:
        with (Path(out) / "compliance_matrix.csv").open(encoding="utf-8") as f:
            n = sum(1 for _ in csv.reader(f)) - 1
        add("csv_rows_match", n == len(rows), "%d csv vs %d matrix" % (n, len(rows)))
    except Exception as e:
        add("csv_rows_match", False, repr(e))
    print("\n%d/%d passed | status=%s rows=%s judged=%s" % (
        sum(1 for c in ok if c), len(ok), res.get("status"), len(rows),
        (res.get("coverage") or {}).get("judged")))
    return all(ok)
