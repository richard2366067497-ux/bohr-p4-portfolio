#!/usr/bin/env python3
"""lib_index.py -- discovery, extraction, hashing, duplicate/version families,
administrative version-note mining and keyword retrieval (stdlib only).

Every material becomes locator-bearing paragraphs. A quote is accepted only when
it literally occurs in that document's extracted text; the validator also checks
that the claimed locator paragraph really contains the quote.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

WS = re.compile(r"\s+")
TR = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-",
      "\u2212": "-", "\u00a0": " ", "\u200b": "", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl"}

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".log", ".yaml", ".yml", ".html", ".htm",
            ".bib", ".tex", ".jsonl", ".csv", ".tsv", ".json", ".xml", ".rtf"}
SKIP_NAMES = {"case.json", "task.md", "task.txt", "skill.md"}


def norm(s, sq=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if sq else " ", s).strip()


def slug(s, fb="x"):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", norm(s).lower()).strip("_")[:60] or fb


# ------------------------------------------------------------------ extraction
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
        for key, kind in (("word/document", "docx"), ("xl/workbook", "xlsx"), ("ppt/presentation", "pptx")):
            if key in names:
                return kind
        return "zip"
    if b"\x00" in head:
        return "binary"
    return "text"


def sha256_file(p):
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _decode(b):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return b.decode(enc), enc
        except Exception:
            continue
    return b.decode("utf-8", "replace"), "replace"


# --- PDF: pdftotext if present, else a small builtin FlateDecode text-stream reader
PDF_DELIM = b" \t\r\n\x00\x0c()<>[]{}/%"


def _pdf_lit(cs, i):
    i, buf, n = i + 1, bytearray(), len(cs)
    while i < n:
        c = cs[i]
        if c == 0x5C and i + 1 < n:
            nx = cs[i + 1]
            if nx in (0x6E, 0x72, 0x74, 0x62, 0x66):
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
            depth, i = 1, i + 1
            while i < n and depth:
                if cs[i] == 0x5C:
                    buf.extend(cs[i:i + 2])
                    i += 2
                    continue
                depth += 1 if cs[i] == 0x28 else (-1 if cs[i] == 0x29 else 0)
                i += 1
                if depth:
                    buf.append(cs[i - 1])
            continue
        if c == 0x29:
            return bytes(buf), i + 1
        buf.append(c)
        i += 1
    return bytes(buf), i


def _pdf_dec(b):
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be", "replace")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("cp1252", "replace")


def _pdf_content(cs):
    i, n, out, args = 0, len(cs), [], []

    def emit(v):
        if v and out and out[-1] and out[-1][-1].isalnum() and v[:1].isalnum():
            out.append(" ")
        out.append(v)

    while i < n:
        c = cs[i:i + 1]
        if c in b" \t\r\n\x00\x0c":
            i += 1
            continue
        if c == b"%":
            k = cs.find(b"\n", i)
            i = n if k < 0 else k + 1
            continue
        if c == b"(":
            s, i = _pdf_lit(cs, i)
            args.append(("s", _pdf_dec(s)))
            continue
        if c == b"<":
            if cs[i + 1:i + 2] == b"<<":
                k = cs.find(b">>", i)
                i = n if k < 0 else k + 2
                continue
            e = cs.find(b">", i)
            hx = re.sub(rb"[^0-9A-Fa-f]", b"", cs[i + 1:e if e >= 0 else i + 1])
            i = e + 1 if e >= 0 else n
            try:
                args.append(("s", _pdf_dec(bytes.fromhex(hx.decode()))))
            except Exception:
                pass
            continue
        if c in b"[]{}{}":
            i += 1
            continue
        k = i
        while k < n and cs[k:k + 1] not in PDF_DELIM:
            k += 1
        tok, i = (cs[i:k], k) if k > i else (cs[i:i + 1], i + 1)
        if re.fullmatch(rb"[-+]?[\d.]+", tok):
            args.append(("n", tok.decode()))
            continue
        op = tok.decode("latin-1", "replace")
        if op == "TJ":
            for t, v in args:
                if t == "s":
                    out.append(v)
                elif abs_safe(v) >= 120:
                    out.append(" ")
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


def abs_safe(v):
    try:
        return abs(float(v))
    except Exception:
        return 0.0


def _pdf_builtin(data):
    streams, pos = [], 0
    while True:
        i = data.find(b"stream", pos)
        if i < 0:
            break
        j = i + 6
        j += 2 if data[j:j + 2] == b"\r\n" else (1 if data[j:j + 1] in (b"\n", b"\r") else 0)
        e = data.find(b"endstream", j)
        if e < 0:
            break
        streams.append((data[max(0, i - 700):i], data[j:e]))
        pos = e + 9
    pages = []
    for head, raw in streams:
        if any(k in head for k in (b"/Image", b"DCTDecode", b"JPXDecode")):
            continue
        body = raw
        if b"FlateDecode" in head:
            import zlib
            for fn in (zlib.decompress, lambda x: zlib.decompressobj().decompress(x)):
                try:
                    body = fn(raw)
                    break
                except Exception:
                    body = raw
        try:
            if b"Tj" in body or b"TJ" in body:
                t = _pdf_content(body)
                if t.strip():
                    pages.append(t)
        except Exception:
            continue
    return pages, "builtin-zlib", ([] if pages else ["no_text_layer"])


def pdf_pages(raw):
    if shutil.which("pdftotext"):
        try:
            td = Path(tempfile.mkdtemp(prefix="bkd_"))
            (td / "d.pdf").write_bytes(raw)
            subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(td / "d.pdf"), str(td / "d.txt")],
                           timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            txt = (td / "d.txt").read_text(encoding="utf-8", errors="replace")
            pages = [t for t in txt.split("\f") if t.strip()]
            if pages:
                return pages, "pdftotext", []
        except Exception:
            pass
    return _pdf_builtin(raw)


def docx_blocks(p):
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(p) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    out = []
    for para in root.iter(ns + "p"):
        t = norm("".join(x.text or "" for x in para.iter(ns + "t")))
        if t:
            out.append(t)
    if not out:
        for tbl in root.iter(ns + "tbl"):
            for row in tbl.iter(ns + "tr"):
                cells = [norm("".join(x.text or "" for x in c.iter(ns + "t"))) for c in row.iter(ns + "tc")]
                if any(cells):
                    out.append(" | ".join(cells))
    return out, "docx-xml"


def xlsx_rows(p):
    from xml.etree import ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rows, sheet_name = [], "sheet1"
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        shared = []
        if any("sharedStrings" in n for n in names):
            root = ET.fromstring(z.read([n for n in names if "sharedStrings" in n][0]))
            for si in root.iter(ns + "si"):
                shared.append(norm("".join(x.text or "" for x in si.iter(ns + "t"))))
        sheets = [n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        for idx, sname in enumerate(sorted(sheets)[:3]):
            sheet_name = "sheet%d" % (idx + 1)
            root = ET.fromstring(z.read(sname))
            for row in root.iter(ns + "row"):
                vals = []
                for c in row.iter(ns + "c"):
                    v = c.find(ns + "v")
                    txt = ""
                    if v is not None and v.text:
                        txt = shared[int(v.text)] if (c.get("t") == "s" and v.text.isdigit()
                                                      and int(v.text) < len(shared)) else v.text
                    else:
                        isel = c.find(ns + "is")
                        if isel is not None:
                            txt = norm("".join(x.text or "" for x in isel.iter(ns + "t")))
                    vals.append(txt)
                if any(vals):
                    rows.append(" | ".join(vals))
    return rows, sheet_name, "xlsx-xml"


def pptx_slides(p):
    from xml.etree import ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    out = []
    with zipfile.ZipFile(p) as z:
        names = sorted(n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n))
        for n in names:
            root = ET.fromstring(z.read(n))
            txt = norm(" ".join((x.text or "") for x in root.iter(ns + "t")))
            out.append(txt)
    return out, "pptx-xml"


def table_rows(text):
    delim = "\t" if ("\t" in text and text.count("\t") >= text.count(",")) else ","
    rows, buf, cur = [], [], []
    for line in text.splitlines():
        if line.count(delim) == 0 and buf:
            buf.append(line.strip())
            continue
        cur.append(delim.join(buf + [line]) if buf else line)
        buf = []
    for line in (cur or text.splitlines()):
        cells = [norm(c.strip().strip('"')) for c in line.split(delim)]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def paragraphize(blocks, chunk=680):
    """blocks: list[(label, text, unit)] -> paragraphs with locator <label>#<unit><n>."""
    paras = []
    for label, text, unit in blocks:
        raw = re.sub(r"[ \t]+", " ", text or "")
        raw = re.sub(r"\n(?=#{1,6}\s)", "\n\n", raw)          # markdown headings stand alone
        pieces = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
        split = []
        for b in pieces:                       # list-like blocks keep one line per paragraph
            lines = [x.strip() for x in b.splitlines() if x.strip()]
            if unit == "row" or (len(lines) >= 3 and sum(len(x) for x in lines) / len(lines) < 170):
                split += lines
            else:
                split.append(b)
        pieces = split
        if len(pieces) <= 1 and len(raw) > 1200:
            pieces, cur = [], []
            for ln in [x.strip() for x in raw.splitlines() if x.strip()]:
                cur.append(ln)
                if len(" ".join(cur)) > chunk:
                    pieces.append(" ".join(cur))
                    cur = []
            if cur:
                pieces.append(" ".join(cur))
        k = 0
        for b in pieces:
            b = re.sub(r"-\n(?=[a-zA-Z])", "", b)
            b = WS.sub(" ", b).strip()
            if len(b) < 2:
                continue
            while len(b) > chunk * 2:
                cut = b.rfind(". ", 0, chunk)
                cut = cut + 1 if cut > chunk // 2 else chunk
                chunks = b[:cut].strip()
                b = b[cut:].strip()
                if chunks:
                    k += 1
                    paras.append({"pid": "p%d" % (len(paras) + 1), "locator": "%s#%s%d" % (label, unit, k),
                                  "block": label, "idx": k, "text": chunks})
            if len(b) < 30 and unit != "row" and paras and paras[-1]["block"] == label:
                paras[-1]["text"] = (paras[-1]["text"] + " " + b).strip()
                continue
            k += 1
            paras.append({"pid": "p%d" % (len(paras) + 1), "locator": "%s#%s%d" % (label, unit, k),
                          "block": label, "idx": k, "text": b})
    return paras


def extract(path):
    p = Path(path)
    kind, notes, engine = kind_of(p), [], "none"
    pages, unit = [], "para"
    try:
        if kind == "pdf":
            pages, engine, notes = pdf_pages(p.read_bytes())
            if engine != "pdftotext":
                notes.append("page_numbers_not_authoritative")
        elif kind == "docx":
            pages, engine = docx_blocks(p)
        elif kind == "xlsx":
            pages, sheet, engine = xlsx_rows(p)
            notes.append("sheet=%s" % sheet)
            unit = "row"
        elif kind == "pptx":
            pages, engine = pptx_slides(p)
        elif kind in ("text", "binary"):
            raw = p.read_bytes()
            text, enc = _decode(raw)
            engine = "text:" + enc
            if p.suffix.lower() in (".csv", ".tsv"):
                pages, unit = table_rows(text), "row"
            else:
                pages = [text]
        else:
            pages, engine = [], "unsupported"
            notes.append("container_not_parsed:%s" % kind)
    except PermissionError:
        notes.append("permission_denied")
        engine = "failed"
    except Exception as e:
        notes.append("extract_failed:%s" % type(e).__name__)
        engine = "failed"
    blocks = []
    if not pages:
        blocks = []
    elif kind == "pdf":
        blocks = [("p%d" % (i + 1), t, "para") for i, t in enumerate(pages)]
    elif kind == "pptx":
        blocks = [("sl%d" % (i + 1), t, "para") for i, t in enumerate(pages)]
    elif kind == "docx":
        blocks = [("s1", "\n\n".join(pages), "para")]
    elif unit == "row":
        blocks = [("t1", "\n".join(pages), "row")]
    else:
        blocks = [("t1", "\n\n".join(pages), "para")]
    paras = paragraphize(blocks)
    text = " ".join(x["text"] for x in paras)
    alnum = sum(ch.isalnum() for ch in text) / max(len(text), 1)
    notes = list(dict.fromkeys(notes))
    if not text.strip() and "no_text_layer" not in notes:
        notes.append("no_text_layer")
    elif alnum < 0.45:
        notes.append("low_text_quality:%.2f" % alnum)
    try:
        readable = bool(os.access(p, os.R_OK))
        mode = oct(p.stat().st_mode & 0o777)
        size = p.stat().st_size
    except Exception:
        readable, mode, size = False, "", 0
    return {"kind": kind, "engine": engine, "paras": paras, "text": text,
            "n_blocks": len(blocks), "quality": round(alnum, 3),
            "readable": readable and bool(text.strip()), "size": size, "mode": mode,
            "sha256": sha256_file(p), "notes": notes}


# ------------------------------------------------------------- families/dupes
NUMV = re.compile(r"(?i)(?:^|[^a-z0-9])v(?:er)?\.?\s?(\d{1,3})(?:[._-](\d{1,2}))?|rev(?:ision)?\.?\s?(\d{1,3})")
STAGE = [(r"preprint|draft|初稿|预印本|submitted", 0.10), (r"accepted|in[ _-]?press|接收", 0.55),
         (r"proof|校样", 0.65), (r"published|final|正式版|终稿|定稿|见刊", 1.20),
         (r"revised|corrected|updated|修订|勘误", 0.30), (r"copy|副本|duplicate", -0.60),
         (r"supp|supplement|补充|附件", -0.20), (r"old|旧", -0.10)]


def version_score(name):
    """Higher = newer. Filename version token dominates; stage words and copy
    markers adjust it; a date gives a small deterministic tie-break."""
    n = (name or "").lower()
    score = 0.0
    m = NUMV.search(n)
    if m:
        score += float(next(g for g in m.groups() if g))
        if m.group(2):
            score += float("0." + m.group(2))
    for pat, w in STAGE:
        if re.search(pat, n):
            score += w
    d = re.search(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})", n)
    if d:
        score += 0.001 * (int(d.group(2)) * 31 + int(d.group(3)))
    return round(score, 4)


def text_shingles(text, k=3):
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", norm(text).lower())
    if len(t) < 40:
        return set()
    return {t[i:i + k] for i in range(0, len(t) - k, max(1, k // 2))}


def sim(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return round(inter / max(min(len(a), len(b)), 1), 3)


def build_families(docs, admin=None):
    """Group documents into families by hash identity / text similarity / name stem."""
    ids = sorted(docs)
    parent = {d: d for d in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    shingles = {d: text_shingles(docs[d]["text"]) for d in ids}
    basis = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ha, hb = docs[a].get("sha256"), docs[b].get("sha256")
            s = sim(shingles[a], shingles[b])
            if ha and ha == hb:
                union(a, b)
                basis[(a, b)] = "sha256_identical"
            elif s >= 0.72:
                union(a, b)
                basis[(a, b)] = "text_similarity_%.2f" % s
            else:
                sa, sb = Path(docs[a]["filename"]).stem.lower(), Path(docs[b]["filename"]).stem.lower()
                sa, sb = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", sa), re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", sb)
                if sa and sb and (sa.startswith(sb[:8]) or sb.startswith(sa[:8])) and s >= 0.4:
                    union(a, b)
                    basis[(a, b)] = "name_stem+text_%.2f" % s
    groups = {}
    for d in ids:
        groups.setdefault(find(d), []).append(d)
    fams = []
    for n, (root, members) in enumerate(sorted(groups.items()), 1):
        fid = "F%d" % n
        members = sorted(members, key=lambda x: docs[x]["filename"])
        for d in members:
            docs[d]["family_id"] = fid
        scored = sorted(((version_score(docs[d]["filename"]), len(docs[d].get("text") or ""), d) for d in members),
                        key=lambda x: (x[0], x[1], x[2]))
        for rank, (sc, _tl, d) in enumerate(scored, 1):
            docs[d]["version_rank"] = rank
            docs[d]["version_score"] = sc
            mm = NUMV.search(docs[d]["filename"].lower())
            docs[d]["version_label"] = ("v%s%s" % (mm.group(1), "." + mm.group(2) if mm.group(2) else "")) \
                if mm else "v%d" % rank
        canonical = scored[-1][2]
        fams.append({"family_id": fid, "members": members, "canonical_doc": canonical,
                     "basis": "; ".join("%s~%s:%s" % (a, b, v) for (a, b), v in sorted(basis.items())
                                        if a in members and b in members) or "singleton",
                     "version_ranks": {d: docs[d]["version_rank"] for d in members},
                     "version_scores": {d: docs[d]["version_score"] for d in members}})
    dupes = []
    for fam in fams:
        mem, groups = fam["members"], []
        by_hash = {}
        for d in mem:
            by_hash.setdefault(docs[d].get("sha256") or d, []).append(d)
        groups += [g for g in by_hash.values() if len(g) > 1]
        for i, a in enumerate(mem):
            for b in mem[i + 1:]:
                if docs[a].get("sha256") != docs[b].get("sha256") and sim(shingles[a], shingles[b]) >= 0.985:
                    groups.append([a, b])
        for g in groups:
            g = sorted(set(g), key=lambda d: (docs[d]["version_rank"], docs[d]["version_score"]))
            keep, drop = g[-1], g[:-1]
            dupes.append({"keep": keep, "drop": drop,
                          "basis": "sha256 identical" if docs[keep].get("sha256") == docs[drop[0]].get("sha256")
                                   else "text similarity >= 0.985"})
    return fams, dupes


ADMIN_PAT = re.compile(r"(?i)(版本|版次|修訂|修订|勘误|勘誤|撤回|作废|作廢|替代|取代|别名|別名|重复|重複|副本|勘正|"
                       r"不要用|勿用|以.{0,6}为准|为准|最新|最终|正式版|后印|再版|错误文件|"
                       r"supersed|supersede|obsolete|retract|alias|duplicate|renam|do not use|not the final|"
                       r"correct(ed)? (file|version)|replaced by|latest version|version note|changelog)")


def admin_notes(docs):
    """Mine paragraphs that read like administrative version notes."""
    names = {d: Path(docs[d]["filename"]).name for d in docs}
    stems = {d: Path(docs[d]["filename"]).stem.lower() for d in docs}
    out = []
    for d, doc in docs.items():
        if d.startswith("ADM"):
            pass
        hit_name = sum(1 for o in docs if o != d and names[o].lower() in doc["text"].lower())
        for para in doc["paras"]:
            t = para["text"]
            hits = ADMIN_PAT.findall(t)
            mentions = [o for o in docs if o != d and (names[o].lower() in t.lower() or
                                                      (len(stems[o]) > 8 and stems[o] in t.lower()))]
            score = len(hits) + (2 if mentions else 0) + (1 if hit_name and len(t) < 400 else 0)
            if score >= 2 and len(t) >= 15:
                out.append({"doc_id": d, "locator": para["locator"], "quote": t[:400],
                            "note_terms": list(dict.fromkeys(hits))[:6],
                            "mentions": mentions, "score": score})
    out.sort(key=lambda x: -x["score"])
    return out[:40]


# ------------------------------------------------------------------ retrieval
STOP = set("the a an of and or to in for on with by is are was were be been this that these those as at from "
           "we our it its their which what how why when where who not no than then there here can could may "
           "的 了 是 在 和 与 及 或 对 中 有 无 请 把 被 为 我 我们 你 他 它 这 那 并 也 都 就 而 从 到 及".split())


def tokenize(s):
    s = norm(s).lower()
    toks = [w for w in re.findall(r"[a-z][a-z0-9\-]{1,}", s) if w not in STOP]
    cjk = re.findall(r"[\u4e00-\u9fff]+", s)
    for run in cjk:
        toks += [run] if len(run) <= 4 else [run[i:i + 2] for i in range(len(run) - 1)]
    return list(dict.fromkeys(toks))


def search(docs, query, top=8):
    q = tokenize(query)
    if not q:
        return []
    df, res = {}, []
    for d, doc in docs.items():
        for para in doc["paras"]:
            toks = set(tokenize(para["text"]))
            for t in q:
                if t in toks:
                    df[t] = df.get(t, 0) + 1
    n = max(sum(len(doc["paras"]) for doc in docs.values()), 1)
    import math
    for d, doc in docs.items():
        for para in doc["paras"]:
            low = para["text"].lower()
            toks = set(tokenize(para["text"]))
            score, matched = 0.0, []
            for t in q:
                if t in toks:
                    score += math.log(1 + n / max(df.get(t, 1), 1))
                    matched.append(t)
            if norm(query).lower() in norm(para["text"]).lower():
                score += 2.5
            if score > 0:
                res.append({"doc_id": d, "locator": para["locator"], "score": round(score, 3),
                            "matched": matched[:8], "text": para["text"]})
    res.sort(key=lambda x: (-x["score"], x["doc_id"], x["locator"]))
    seen, out = {}, []
    for r in res:
        if r["doc_id"] in seen and len(seen) >= 3:
            continue
        seen[r["doc_id"]] = seen.get(r["doc_id"], 0) + 1
        out.append(r)
        if len(out) >= top:
            break
    return out


def excerpt(text, terms, maxlen=320):
    t = norm(text)
    if len(t) <= maxlen:
        return t
    low = t.lower()
    pos = min([low.find(x.lower()) for x in terms if x and low.find(x.lower()) >= 0] or [0])
    start = max(0, pos - maxlen // 3)
    cut = t[start:start + maxlen]
    for sep in ("。 ", ". ", "； ", "; ", "\n"):
        j = cut.rfind(sep)
        if j > maxlen // 2:
            cut = cut[:j + 1]
            break
    return cut.strip()


def metadata_hints(doc):
    t = doc.get("text") or ""
    h = {}
    m = re.search(r"(?i)\b(19[89]\d|20[0-4]\d)\b", t[:3000])
    if m:
        h["year_hint"] = m.group(1)
    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", t)
    if m:
        h["doi_hint"] = m.group(0).rstrip(".,;)")
    first = next((p["text"] for p in doc.get("paras") or [] if len(p["text"]) >= 12), "")
    if first:
        h["title_hint"] = re.sub(r"^[#>*\-\s]+", "", first)[:160]
    return h


# ------------------------------------------------------------------ discovery
def load_json(path):
    txt = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    try:
        return json.loads(txt)
    except Exception:
        body = re.sub(r",\s*([}\]])", r"\1", txt)          # trailing commas
        obj = json.JSONDecoder().raw_decode(body.lstrip())[0]      # first object of a damaged file
        load_json.repaired = True
        return obj


def walk(o, depth=0):
    if depth > 4:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k), v
            yield from walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o[:30]:
            yield from walk(v, depth + 1)


def find_case(inp, errs):
    inp = Path(inp)
    if not inp.exists():
        errs.append({"code": "input_missing", "detail": "input directory not found: %s" % inp})
        return {}, None
    cands = sorted(inp.rglob("case.json")) + sorted(p for p in inp.rglob("*.json")
                                                    if p.name.lower() != "case.json")
    load_json.repaired = False
    for p in cands:
        try:
            obj = load_json(p)
            if isinstance(obj, dict) and (obj.get("output_contract") or obj.get("contract")
                                          or obj.get("questions") or obj.get("task_instruction")):
                if getattr(load_json, "repaired", False):
                    errs.append({"code": "case_json_repaired", "detail": "recovered first JSON object from %s" % p.name})
                return obj, p
        except Exception as e:
            errs.append({"code": "case_json_invalid", "detail": "%s: %s" % (p.name, e)})
    return {}, None


def find_questions(case, task_text):
    raw, src = [], ""
    for k, v in walk(case):
        if k.lower() in ("questions", "queries", "qa", "questions_list", "asks", "tasks", "question_list", "searches") \
                and isinstance(v, list) and v:
            if len(str(v)) > len(str(raw)):
                raw, src = v, "case:" + k

    def qtext(x):
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            for kk in ("question", "q", "text", "query", "prompt", "ask", "title", "description"):
                if isinstance(x.get(kk), str) and x[kk].strip():
                    return x[kk]
        return ""

    qs = []
    for i, x in enumerate(raw):
        t = qtext(x)
        if not t:
            continue
        qid = (x.get("qid") or x.get("id") or x.get("q_id") or "Q%d" % (i + 1)) if isinstance(x, dict) else "Q%d" % (i + 1)
        item = {"qid": str(qid), "question": norm(t), "derived": False, "source": src}
        if isinstance(x, dict):
            for kk in ("issue_hints", "hints", "issues", "filters", "scope", "evidence_requirements", "expected"):
                if x.get(kk) not in (None, "", [], {}):
                    item[kk] = x[kk]
        qs.append(item)
    if not qs:
        for block in (task_text or "", str(case.get("task_instruction") or "")):
            for line in re.split(r"[\n。]", block):
                s = line.strip(" -*\t")
                if 6 <= len(s) <= 220 and (s.endswith("?") or s.endswith("？") or
                                           re.search(r"(哪一版|哪个版本|有没有|是否有|是否|what|which|how many|does|is there)", s)):
                    if not any(q["question"] == norm(s) for q in qs):
                        qs.append({"qid": "Q%d" % (len(qs) + 1), "question": norm(s), "derived": True,
                                   "source": "task_instruction_scan"})
        if qs:
            for q in qs:
                q["source"] = "derived_from_instruction"
    return qs[:12]


def scan_input(inp):
    """Return (materials, skipped) under the input tree."""
    inp = Path(inp)
    mats, skipped = [], []
    if not inp.exists():
        return mats, skipped
    for p in sorted(inp.rglob("*")):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low in SKIP_NAMES or low.endswith(".pyc") or "__pycache__" in str(p):
            skipped.append({"file": str(p), "reason": "control_file"})
            continue
        if p.stat().st_size > 40 * 1024 * 1024:
            skipped.append({"file": str(p), "reason": "too_large"})
            continue
        if p.suffix.lower() not in TEXT_EXT and kind_of(p) in ("unreadable", "binary", "zip"):
            skipped.append({"file": str(p), "reason": "unsupported_container"})
            continue
        mats.append(p)
    return mats, skipped
