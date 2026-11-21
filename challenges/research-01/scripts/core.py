#!/usr/bin/env python3
"""core.py -- deep-research evidence-map kernel (Python standard library only).

Responsibilities (all deterministic, no network, no CWD assumptions):
  * material sniffing  : extension + magic bytes (pdf / docx / text / jsonl / csv)
  * paragraph indexing : every material -> locator-bearing paragraphs (p3#para7 / b2#para4)
  * quote anchoring    : a quote is accepted only if it occurs verbatim in the claimed source;
                         the authoritative paragraph locator is filled back into the evidence row
  * record loading     : records.jsonl / records[]. in case.json / *record*.csv
  * contract filling   : enumerate output_contract keys, type-aware fill, never rename/drop
  * draft validation   : schema, enums, dependency graph, retrieval coverage, conflicts, gaps
  * rendering          : report.md, synthesis.json, coverage.json, research_plan.json
"""
import json
import re
import shutil
import subprocess
import unicodedata
import zipfile
import zlib
from pathlib import Path

GEN = "deep-research-evidence-map v1.0.0"

WS = re.compile(r"\s+")
TR = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-",
      "\u2212": "-", "\u00a0": " ", "\u200b": "", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl"}


# ------------------------------------------------------------------ text utils
def norm(s, squeeze=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if squeeze else " ", s).strip()


def slug(s, fb="f"):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", norm(s).lower()).strip("_") or fb


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))


def jwrite(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def twrite(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(s, encoding="utf-8")


def walk(o, depth=0):
    """yield (key, value) over nested dict/list, bounded."""
    if depth > 5:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k), v
            yield from walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o[:40]:
            yield from walk(v, depth + 1)


def bigrams(s):
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", norm(s).lower())
    return set(s[i:i + 2] for i in range(len(s) - 1)) if len(s) > 2 else set()


def overlap(a, b):
    """containment of a's bigrams inside b (0..1) -- keyword-rewrite detector."""
    A, B = bigrams(a), bigrams(b)
    return 0.0 if not A else len(A & B) / float(len(A))


# ------------------------------------------------------------------ materials
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
                names = " ".join(z.namelist()[:80])
        except Exception:
            return "zip"
        for marker, kind in (("word/document", "docx"), ("xl/workbook", "xlsx"), ("ppt/presentation", "pptx")):
            if marker in names:
                return kind
        return "zip"
    return "text"


def _inflate(buf):
    for fn in (lambda b: zlib.decompress(b),
               lambda b: zlib.decompressobj().decompress(b),
               lambda b: zlib.decompressobj(-15).decompress(b)):
        try:
            out = fn(buf)
            if out:
                return out
        except Exception:
            continue
    return b""


def _lstr(cs, i):
    """read a PDF literal string starting at '(' ; returns (bytes, next_index)."""
    i, buf, n, depth = i + 1, bytearray(), len(cs), 1
    while i < n:
        c = cs[i]
        if c == 0x5C and i + 1 < n:
            nx = cs[i + 1]
            if nx in b"nrtbf":
                buf.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}[nx])
                i += 2
                continue
            if 0x30 <= nx <= 0x37:
                k = 0
                while k < 3 and i + 1 + k < n and 0x30 <= cs[i + 1 + k] <= 0x37:
                    k += 1
                buf.append(int(cs[i + 1:i + 1 + k], 8) & 0xFF)
                i += 1 + k
                continue
            if nx not in (10, 13):
                buf.append(nx)
            i += 2
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return bytes(buf), i + 1
        buf.append(c)
        i += 1
    return bytes(buf), i


def _dec(b):
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be", "replace")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("cp1252", "replace")


def _hexs(b):
    b = re.sub(rb"[^0-9A-Fa-f]", b"", b)
    if len(b) % 2:
        b += b"0"
    try:
        raw = bytes.fromhex(b.decode("ascii"))
    except Exception:
        return ""
    return _dec(raw) if raw[:2] == b"\xfe\xff" else raw.decode("latin-1", "replace")


def stream_text(cs):
    """pull glyph strings out of a PDF content stream, keeping soft line breaks."""
    out, pend, i, n = [], [], 0, len(cs)
    while i < n:
        c = cs[i]
        if c == 0x28:
            s, i = _lstr(cs, i)
            pend.append(_dec(s))
            continue
        if c == 0x3C and i + 1 < n and cs[i + 1] != 0x3C:
            j = cs.find(b">", i)
            if j > 0:
                pend.append(_hexs(cs[i + 1:j]))
                i = j + 1
                continue
        if 0x41 <= c <= 0x7A or c in (0x2A, 0x27, 0x22):
            j = i
            while j < n and (0x41 <= cs[j] <= 0x5A or 0x61 <= cs[j] <= 0x7A or cs[j] in b"*'\""):
                j += 1
            op = cs[i:j]
            if op in (b"Tj", b"TJ", b"'", b'"'):
                out.append("".join(pend))
                pend = []
            elif op in (b"Td", b"TD", b"T*", b"ET"):
                if out and not out[-1].endswith("\n"):
                    out.append("\n")
                pend = []
            i = j
            continue
        i += 1
    if pend:
        out.append("".join(pend))
    return "".join(out)


def pdf_builtin(raw):
    """best-effort text layer extraction: inflate object streams, read text operators."""
    texts, notes = [], []
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            break
        body = raw[start:end]
        head = raw[max(0, m.start() - 400):m.start()]
        if b"FlateDecode" in head:
            body = _inflate(body)
        chunk = stream_text(body)
        chunk = "".join(ch for ch in chunk if ch == "\n" or (ch.isprintable() and ch not in "\x00"))
        if sum(ch.isalnum() for ch in chunk) >= 20:
            texts.append(chunk)
    pages = [t for t in texts if t.strip()]
    if not pages:
        notes.append("no extractable text layer (scanned image or CID-only fonts): OCR required, content NOT guessed")
    notes.append("builtin stream parser: page boundaries are content-stream order, so page numbers are not authoritative")
    return pages, "builtin", notes


def pdf_pages(raw):
    if shutil.which("pdftotext"):
        tmp = None
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(raw)
                tmp = f.name
            out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", tmp, "-"],
                                 capture_output=True, timeout=90)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.decode("utf-8", "replace").split("\f"), "pdftotext", []
        except Exception:
            pass
        finally:
            if tmp:
                try:
                    Path(tmp).unlink()
                except Exception:
                    pass
    return pdf_builtin(raw)


def docx_pages(p):
    pages = []
    try:
        with zipfile.ZipFile(p) as z:
            for name in ("word/document.xml",):
                if name in z.namelist():
                    xml = z.read(name).decode("utf-8", "replace")
                    xml = re.sub(r"</w:p>", "\n", xml)
                    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
                    txt = re.sub(r"<[^>]+>", "", xml)
                    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
                        txt = txt.replace(a, b)
                    pages.append(txt)
    except Exception:
        pass
    return pages


def text_pages(p):
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "utf-16", "gb18030", "cp1252", "latin-1"):
        try:
            return [raw.decode(enc)]
        except Exception:
            continue
    return [raw.decode("utf-8", "replace")]


def paragraphize(pages, kind):
    """-> [{loc, unit, idx, text, page}] with a stable locator scheme per document."""
    tag = "p" if kind in ("pdf", "docx") else "b"
    paras = []
    for ui, page in enumerate(pages):
        lines = [ln.strip() for ln in str(page).replace("\r", "\n").split("\n")]
        idx = 0
        for ln in lines:
            if not ln:
                continue
            idx += 1
            paras.append({"loc": "%s%d#para%d" % (tag, ui + 1, idx), "unit": ui + 1, "idx": idx,
                          "text": ln, "page": ui + 1 if kind in ("pdf", "docx") else None})
    if len(paras) < 3 and pages:  # very long single block -> split on sentence boundaries
        blob = " ".join(str(p) for p in pages)
        pieces = [s.strip() for s in re.split(r"(?<=[.!?;:\u3002\uff1b\uff1a])\s+", blob) if s.strip()]
        chunks, cur = [], ""
        for piece in pieces:
            if len(cur) + len(piece) > 900 and cur:
                chunks.append(cur)
                cur = piece
            else:
                cur = (cur + " " + piece).strip()
        if cur:
            chunks.append(cur)
        paras = [{"loc": "%s1#para%d" % (tag, i + 1), "unit": 1, "idx": i + 1, "text": c,
                  "page": None} for i, c in enumerate(chunks)]
    return paras


def extract_doc(p):
    kind, notes = kind_of(p), []
    try:
        if kind == "pdf":
            pages, engine, notes = pdf_pages(Path(p).read_bytes())
        elif kind == "docx":
            pages, engine = docx_pages(p), "docx-xml"
        elif kind in ("text", "unreadable"):
            pages, engine = text_pages(p), "text"
        else:
            pages, engine = [], "unsupported"
            notes.append("%s container not parsed; recorded as unsupported material" % kind)
    except PermissionError:
        pages, engine = [], "permission_denied"
        notes.append("permission denied while reading; file skipped")
    except Exception as e:
        pages, engine = [], "failed"
        notes.append("extraction failed: %r" % (e,))
    paras = paragraphize(pages, kind)
    text = "\n".join(x["text"] for x in paras)
    alnum = sum(ch.isalnum() for ch in text) / float(max(len(text), 1))
    if text and alnum < 0.45:
        notes.append("low text quality (alnum %.2f): CID font or scan likely; quotes may be unreliable" % alnum)
    if not paras:
        notes.append("no text paragraphs extracted (0 chars)")
    return {"kind": kind, "engine": engine, "paras": paras, "text": text, "n_units": len(pages),
            "quality": round(alnum, 3), "notes": notes}


# ------------------------------------------------------------------ quote anchor
def anchor(paras, quote):
    """locate a quote inside a document's paragraphs -> authoritative locator."""
    q = norm(quote)
    res = {"found": False, "mode": "miss", "loc": None, "para_index": None, "offset": None,
           "occurrences": 0, "span_paras": 0}
    if len(q) < 3 or not paras:
        res["mode"] = "too_short" if len(q) < 3 else "empty_doc"
        return res
    qs = norm(quote, True)
    hits = [i for i, p in enumerate(paras) if q in norm(p["text"])]
    mode = "exact"
    if not hits:
        hits = [i for i, p in enumerate(paras) if qs and qs in norm(p["text"], True)]
        mode = "loose"
    if hits:
        res.update(found=True, mode=mode, loc=paras[hits[0]]["loc"], para_index=hits[0],
                   offset=norm(paras[hits[0]]["text"]).find(q), occurrences=len(hits),
                   span_paras=1)
        return res
    for width in (2, 3, 4):  # quote wrapped over consecutive paragraphs
        for i in range(0, len(paras) - width + 1):
            joined = " ".join(norm(paras[k]["text"]) for k in range(i, i + width))
            if q in joined:
                res.update(found=True, mode="window", loc=paras[i]["loc"], para_index=i,
                           offset=0, occurrences=1, span_paras=width)
                return res
    return res


# ------------------------------------------------------------------ schema enums
ENUM_SQ_LAYER = ("what", "how_far", "why", "what_missing")
ENUM_TYPE = ("material_fact", "inference", "undetermined")
ENUM_STRENGTH = ("strong", "moderate", "weak")
ENUM_STANCE = ("supports", "refutes", "neutral")
ENUM_GAP = ("retrieval_gap", "unresolved_conflict", "method_limitation", "scope_limit")
ENUM_TOOL = ("read_file", "parse_pdf", "extract_table", "search", "calc", "screen", "other")


# ------------------------------------------------------------------ records
REC_KEYS = ("records", "record_list", "screening_records", "items", "entries", "candidates")


def load_records(files, case):
    recs, src, notes = [], "", []
    for k, v in (case or {}).items():
        if str(k).lower() in REC_KEYS and isinstance(v, list):
            for i, it in enumerate(v):
                if isinstance(it, dict):
                    recs.append(dict(it))
                elif isinstance(it, str):
                    recs.append({"title": it})
            if recs:
                src = "case:" + str(k)
    if not recs:
        cand = [p for p in files if re.search(r"record|screen|candidate|hit", p.name.lower())
                and p.suffix.lower() in (".jsonl", ".json", ".csv", ".tsv")]
        for p in cand:
            try:
                if p.suffix.lower() in (".jsonl",):
                    recs = [json.loads(l) for l in p.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
                elif p.suffix.lower() in (".csv", ".tsv"):
                    import csv
                    with p.open(encoding="utf-8-sig", newline="") as f:
                        recs = [dict(r) for r in csv.DictReader(f, delimiter="\t" if p.suffix.lower() == ".tsv" else ",")]
                else:
                    o = jread(p)
                    recs = o if isinstance(o, list) else next(
                        (v for k, v in (o.items() if isinstance(o, dict) else []) if isinstance(v, list)), [])
            except Exception as e:
                notes.append("%s: record file unreadable (%r)" % (p.name, e))
                continue
            if recs:
                src = p.name
                break
    out = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            r = {"value": r}
        out.append(dict(record_id=str(r.get("record_id") or r.get("id") or "R%d" % (i + 1)),
                        source_id=str(r.get("source_id") or r.get("paper_id") or r.get("source") or ""),
                        fields={k: v for k, v in r.items()
                                if k not in ("record_id", "id", "source_id", "paper_id", "source")}))
    return out, src, notes


# ------------------------------------------------------------------ contract
CONTRACT_MAP = [
    (r"sub_?question|decomposition|question_tree|拆解", "sub_questions"),
    (r"retrieval|search_?plan|query|protocol|screening|检索", "retrieval_plan"),
    (r"tool_?call|trace|call_log|steps|actions|工具", "tool_calls"),
    (r"evidence|citation|quote|matrix|证据|引文", "evidence"),
    (r"conflict|disagree|contradict|冲突", "conflicts"),
    (r"\bgaps?\b|open_?question|future_work|空白", "gaps"),
    (r"uncertain|limitation|caveat|风险|不确定", "uncertainties"),
    (r"coverage|metric|stat|count|覆盖", "coverage"),
    (r"source|provenance|bibliograph|reference|来源", "sources"),
    (r"claim|conclusion|finding|synthesis|conclusion_text|结论", "claims"),
    (r"report|markdown|narrative|write_?up|报告", "report"),
    (r"artifact|output_file|deliverable|产物", "artifacts"),
    (r"proposal|recommend|bounded|提案", "bounded_proposal"),
    (r"inclusion|exclusion|eligib|screen_?decision|纳排", "inclusion_decisions"),
    (r"method|approach|rationale|方法", "method_notes"),
    (r"^summary$|executive|overview|tl_dr|摘要|概要", "report"),
    (r"scan|abstract", "abstract"),
    (r"research_question|question|topic|问题", "research_question"),
    (r"status|状态", "status"),
]


def contract_keys(ct):
    if isinstance(ct, dict):
        return [str(k) for k in ct.keys()]
    if isinstance(ct, list):
        keys = []
        for it in ct:
            if isinstance(it, dict):
                k = it.get("name") or it.get("key") or it.get("field") or it.get("id")
                if k:
                    keys.append(str(k))
            elif isinstance(it, str):
                keys.append(it)
        return keys
    return []


def contract_spec(contract, key):
    """return the per-key spec object regardless of dict-form or list-form contracts."""
    if isinstance(contract, dict):
        return contract.get(key)
    if isinstance(contract, list):
        for it in contract:
            if isinstance(it, dict):
                n = it.get("name") or it.get("key") or it.get("field") or it.get("id")
                if str(n) == str(key):
                    return it
    return None


def _spec_text(spec):
    try:
        return json.dumps(spec, ensure_ascii=False).lower() if not isinstance(spec, str) else spec.lower()
    except Exception:
        return str(spec).lower()


def wants(spec, word):
    t = _spec_text(spec)
    return word in t


def empty_like(spec):
    if wants(spec, "array") or wants(spec, "list") or wants(spec, "[]"):
        return []
    if wants(spec, "object") or wants(spec, "dict") or wants(spec, "{}"):
        return {}
    if wants(spec, "integer") or wants(spec, "number") or wants(spec, "float"):
        return None
    if wants(spec, "boolean"):
        return None
    return None


def as_md(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, dict):
                out.append("- " + "; ".join("%s=%s" % (k, norm(jval(val))) for k, val in x.items() if val not in (None, "", [], {})))
            else:
                out.append("- " + norm(jval(x)))
        return "\n".join(out)
    if isinstance(v, dict):
        return "\n".join("%s: %s" % (k, norm(jval(val))) for k, val in v.items())
    return norm(jval(v))


def jval(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return "" if v is None else v


def coerce(spec, val):
    if val in (None, "", [], {}):
        return val if val not in ("",) else (empty_like(spec) if wants(spec, "string") is False else val)
    arr = wants(spec, "array") or wants(spec, "list") or wants(spec, "[]")
    obj = wants(spec, "object") or wants(spec, "dict")
    if arr and not isinstance(val, list):
        return [val] if not isinstance(val, dict) else [val]
    if obj and isinstance(val, list):
        return {"items": val}
    if not arr and not obj and isinstance(val, (list, dict)):
        return as_md(val)
    return val


def match_target(key):
    k = str(key).lower()
    for pat, tgt in CONTRACT_MAP:
        if re.search(pat, k):
            return tgt
    return None


def fill_contract(contract, M):
    """fill every contract key from the model dict M; never rename or drop keys."""
    res, missing, empty = {}, [], []
    for k in contract_keys(contract):
        spec = contract_spec(contract, k)
        val, src = None, ""
        if k in M and M[k] not in (None, "", [], {}):
            val, src = M[k], "exact"
        else:
            tgt = match_target(k)
            if tgt and M.get(tgt) not in (None, "", [], {}):
                val, src = M[tgt], tgt
        if val in (None, "", [], {}):
            val = M.get(k, empty_like(spec))
            if val in (None, "", [], {}):
                # an array/object contract field legitimately filled with [] / {} is complete, not missing
                (empty if (wants(spec, "array") or wants(spec, "list") or wants(spec, "object")
                           or wants(spec, "[]")) else missing).append(k)
        res[k] = coerce(spec, val)
    return res, missing, empty



