"""audit_core.py - input discovery, parsing, locators, citation pairing, candidates.

Stdlib only. This module produces locatable facts only (units, reference entries,
marker pairings, numeric occurrences). It never decides whether a citation
supports a claim - that judgement belongs to the agent's draft.
"""

from __future__ import annotations

import hashlib, json, re, shutil, subprocess, unicodedata, zipfile, zlib
from itertools import combinations
from pathlib import Path

INDEX_SCHEMA = "audit-index/1"
MAX_UNITS, MAX_READ_BYTES, MAX_FILE_BYTES = 4000, 24 << 20, 4 << 20
DATA_EXT = {".json", ".jsonl", ".csv", ".tsv", ".bib", ".yaml", ".yml"}
SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules", ".cache"}
SKIP_NAMES = {"case.json", "task.md", "brief.md", "readme.md", "resources.yaml",
              "instructions.md", "skill.md", "smoke.md"}

HEAD_RE = re.compile(
    r"^(?:#{1,6}\s*(?P<md>.{1,80})$)|^(?:(?:\d+(?:\.\d+)*)[\.\)]?\s+)?"
    r"(?P<sec>abstract|摘\s*要|introduction|引\s*言|绪\s*论|background|背\s*景|related work|"
    r"methods?|methodology|materials? and methods?|材料与方法|实验方法|方\s*法|results?|结\s*果|"
    r"findings|discussion|讨\s*论|conclusions?|结\s*论|limitations?|局\s*限|references?|"
    r"bibliography|参考文献|acknowledg\w*|致\s*谢|funding|基\s*金|data availability|"
    r"数据可用性|code availability|conflicts? of interest|利益冲突|author contributions|"
    r"作者贡献|supplementary|附\s*录|appendix)\s*[:：]?\s*$", re.I)
SEC_MAP = {"abstract": "abstract", "摘要": "abstract", "introduction": "intro", "引言": "intro",
           "绪论": "intro", "background": "intro", "背景": "intro", "method": "methods",
           "材料与方法": "methods", "实验方法": "methods", "方法": "methods", "result": "results",
           "结果": "results", "discussion": "discussion", "讨论": "discussion",
           "conclusion": "conclusion", "结论": "conclusion", "limitation": "limitations",
           "局限": "limitations", "reference": "references", "参考文献": "references",
           "bibliography": "references", "supplement": "supplementary", "附录": "supplementary",
           "acknowledg": "back", "致谢": "back", "funding": "back", "基金": "back"}
CUE = {
    "up": r"高于|更高|增大|增加|上升|提高|增强|促进|优于|超过|多于|more than|higher|greater|increas|enhanc|improv|superior",
    "down": r"低于|更低|减小|降低|下降|缩短|减弱|抑制|劣于|少于|lower|smaller|decreas|reduc|inhibit|declin|inferior",
    "neg": r"不|未|没有|无法|并非|不能|not\b|no\b|fail|none\b|without",
    "sig": r"显著|极显著|significan|p\s*[<=]\s*0?\.\d+|95%\s*ci|置信区间|confidence interval",
    "scope": r"所有|全部|任何|均|普遍|总是|从不|仅|只|every|all\b|always|never|universal|exclusively|solely",
    "causal": r"导致|引起|造成|因为|由于|因此|从而|使得|证明|表明|证实|说明|caus|lead to|due to|result in|demonstrat|confirm|attribut|driven by",
    "compar": r"高于|低于|优于|劣于|大于|小于|相比|compared|than\b|versus|vs\.?|比",
    "hedge": r"可能|或许|提示|推测|有待|尚需|may|might|suggest|could|potential|presumably",
}
CUE_RE = {k: re.compile(v, re.I) for k, v in CUE.items()}
NUM_MARK = re.compile(r"\[(\d{1,3}(?:\s*[-–—,;，、]\s*\d{1,3})*)\]")
AUTH_MARK = re.compile(r"([A-Z][A-Za-z\-']{1,20})(?:\s+et\s+al\.?)?\s*[,(（]\s*((?:19|20)\d{2})[a-z]?\s*[)）]")
CN_MARK = re.compile(r"([\u4e00-\u9fff]{2,4})\s*等?\s*[，,（(]\s*((?:19|20)\d{2})[a-z]?\s*[)）]")
CITE_TEX = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])?\{([^}]+)\}")
WS = re.compile(r"\s+")
REF_MARK = re.compile(r"\[(\d{1,3})\]\s*|(?:^|\s)(\d{1,3})[\.\)]\s+")


def nfkc(s):
    try:
        return unicodedata.normalize("NFKC", str(s or ""))
    except Exception:
        return str(s or "")


def flatmatch(s):
    t = nfkc(s)
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
                 ("\u300c", '"'), ("\u300d", '"'), ("\u2013", "-"), ("\u2014", "-"),
                 ("\u2212", "-"), ("\u00a0", " ")):
        t = t.replace(a, b)
    return WS.sub("", t).lower()


def squash(s, n=300):
    return WS.sub(" ", str(s or "")).strip()[:n]


def terms(text):
    t = (text or "").lower()
    out = {w for w in re.findall(r"[a-z][a-z\-]{2,}", t)
           if w not in ("the", "and", "for", "with", "that", "this", "was", "were")}
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    return out


def cue(kind, text):
    m = CUE_RE[kind].search(text or "")
    return m.group(0) if m else None


def direction(text):
    up, down = bool(CUE_RE["up"].search(text or "")), bool(CUE_RE["down"].search(text or ""))
    return "up" if up and not down else "down" if down and not up else "mixed" if up else "none"


def sec_key(label):
    low = (label or "").lower()
    for k, v in SEC_MAP.items():
        if k in low:
            return v
    return "other"


def split_sentences(text):
    t = WS.sub(" ", str(text or "")).strip()
    if not t:
        return []
    parts = re.split(r"(?<=[。！？；!?;])\s*|(?<=[.])\s+(?=[A-Z0-9(\[])", t)
    return [p.strip() for p in parts if len(p.strip()) >= 6]


# ------------------------------------------------------------------ file readers
def read_text(path):
    raw = path.read_bytes()[:MAX_READ_BYTES]
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8/replace"


def read_docx(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return ""
    xml = re.sub(r"</w:p>", "\n\n", re.sub(r"<w:tab[^>]*/>", "\t", xml))
    xml = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        xml = xml.replace(a, b)
    return xml


def _pdf_hex(bs):
    hexs = re.sub(rb"[^0-9A-Fa-f]", b"", bs)
    try:
        return bytes.fromhex(hexs[:len(hexs) // 2 * 2].decode())
    except Exception:
        return b""


def _content_text(dec):
    """Pull literal and hex strings out of one PDF content stream."""
    esc = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}
    out = []
    for m in re.finditer(rb"\((?:\\.|[^()\\])*\)|<[0-9A-Fa-f\s]{4,}>", dec):
        tok = m.group(0)
        bs = _pdf_hex(tok[1:-1]) if tok[:1] == b"<" else tok[1:-1]
        if tok[:1] != b"<":
            bs = re.sub(rb"\\([0-7]{1,3})", lambda mm: bytes([int(mm.group(1), 8) & 0xFF]), bs)
            bs = re.sub(rb"\\(.)", lambda mm: esc.get(mm.group(1), mm.group(1)), bs)
        if not bs:
            continue
        if bs[:2] in (b"\xfe\xff", b"\xff\xfe") or bs.count(b"\x00") > len(bs) // 3:
            try:
                out.append(bs.decode("utf-16"))
                continue
            except Exception:
                pass
        try:
            out.append(bs.decode("utf-8"))
        except Exception:
            out.append(bs.decode("latin-1"))
    return WS.sub(" ", "".join(out)).strip()


def read_pdf(path):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            pr = subprocess.run([exe, "-layout", "-enc", "UTF-8", "-q", str(path), "-"],
                                capture_output=True, timeout=90)
            txt = pr.stdout.decode("utf-8", "replace")
            if pr.returncode == 0 and len(txt.strip()) > 80:
                pages = [p for p in txt.split("\f") if p.strip()] or [txt]
                return {"pages": pages, "parser": "pdftotext", "quality": "ok"}
        except Exception:
            pass
    try:
        data = path.read_bytes()[:MAX_READ_BYTES]
    except Exception:
        return {"pages": [], "parser": "none", "quality": "empty"}
    pages = []
    for m in re.finditer(rb"stream\r?\n", data):
        start, end = m.end(), data.find(b"endstream", m.end())
        if end < 0:
            continue
        blob = data[start:end]
        try:
            dec = zlib.decompress(blob)
        except Exception:
            dec = blob if (b"Tj" in blob or b"TJ" in blob) else None
        if not dec:
            continue
        try:
            txt = _content_text(dec)
        except Exception:
            txt = ""
        if len(txt) > 40:
            pages.append(txt)
    joined = "\n".join(pages)
    if not joined.strip():
        guess = re.sub(rb"[^\x20-\x7e\xc0-\xff]+", b" ", data).decode("latin-1", "replace")
        return {"pages": [guess] if len(guess.strip()) > 80 else [],
                "parser": "raw-bytes", "quality": "low" if guess.strip() else "empty"}
    return {"pages": pages, "parser": "internal-flate",
            "quality": "ok" if len(WS.sub("", joined)) > 400 else "low"}


def json_text(obj, depth=0):
    if depth > 6:
        return ""
    if isinstance(obj, dict):
        return "\n".join(json_text(v, depth + 1) if isinstance(v, (dict, list))
                         else str(v) for v in obj.values()
                         if isinstance(v, (str, dict, list)) and len(str(v)) > 8)
    if isinstance(obj, list):
        return "\n".join(json_text(v, depth + 1) for v in obj[:400])
    return obj if isinstance(obj, str) else ""


def read_any(path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        return read_pdf(path)
    if ext == ".docx":
        t = read_docx(path)
        return {"pages": [t] if t.strip() else [], "parser": "docx-xml",
                "quality": "ok" if len(t.strip()) > 100 else ("low" if t.strip() else "empty")}
    if ext in (".html", ".htm"):
        t, enc = read_text(path)
        t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>", "\n\n", t)
        t = re.sub(r"<[^>]+>", " ", t)
        for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")):
            t = t.replace(a, b)
        return {"pages": [t], "parser": "html/%s" % enc,
                "quality": "ok" if len(t.strip()) > 100 else "low"}
    if ext in (".json", ".jsonl"):
        raw, _ = read_text(path)
        try:
            obj = json.loads(raw) if ext == ".json" else [json.loads(l) for l in raw.splitlines() if l.strip()]
            return {"pages": [json_text(obj)], "parser": "json-text", "quality": "ok"}
        except Exception:
            return {"pages": [raw], "parser": "json/raw", "quality": "low"}
    if ext in (".csv", ".tsv"):
        raw, enc = read_text(path)
        rows = [l for l in raw.splitlines() if l.strip()]
        return {"pages": ["\n".join(rows[:800])], "parser": "csv/%s" % enc,
                "quality": "ok" if rows else "empty"}
    t, enc = read_text(path)
    return {"pages": [t], "parser": "text/%s" % enc, "quality": "ok" if t.strip() else "empty"}


# ------------------------------------------------------------------ locators
def text_to_units(text, sid, rel, page=None, cap=MAX_UNITS):
    units, section, para = [], "Body", 0

    def add(body):
        nonlocal para
        body = body.strip()
        if len(WS.sub("", body)) < 12:
            return
        chunks = [body]
        if len(body) > 900:
            chunks, cur = [], ""
            for sent in re.split(r"(?<=[。！？.!?])\s*", body):
                if len(cur) + len(sent) > 700 and cur:
                    chunks.append(cur)
                    cur = sent
                else:
                    cur += sent
            if cur:
                chunks.append(cur)
        for ch in chunks:
            para += 1
            loc = "%s §%s" % (rel, section) + (" P%d" % page if page else "") + " ¶%d" % para
            units.append({"uid": "U%04d" % (len(units) + 1), "source_id": sid, "rel": rel,
                          "section": section, "section_key": sec_key(section), "page": page,
                          "para": para, "locator": loc, "text": WS.sub(" ", ch).strip()})

    blocks, buf = [], []
    for line in (text or "").split("\n"):
        if not line.strip():
            if buf:
                blocks.append(buf)
                buf = []
        else:
            buf.append(line.rstrip())
    if buf:
        blocks.append(buf)

    for block in blocks:
        first = block[0].strip()
        head = None
        m = HEAD_RE.match(first) if len(first) <= 90 else None
        if m:
            head = (m.group("md") or m.group("sec") or "").strip()
        elif len(first) <= 70 and len(block) > 1 and not re.search(r"[。.!?；;：:]$", first) \
                and len(first.split()) <= 8 and re.match(r"^[A-Z\u4e00-\u9fff]", first):
            head = first
        if head:
            section = head
            block = block[1:] if len(block) > 1 else []
        if block:
            add(" ".join(block))
        if len(units) >= cap:
            break
    return units


def discover(input_dir):
    out, root = [], Path(input_dir)
    if not root.exists():
        return out
    for p in sorted(root.rglob("*"), key=lambda x: str(x)):
        try:
            if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.name.startswith(".") or p.suffix.lower() in (".pyc", ".pyo"):
                continue
            size = p.stat().st_size
        except Exception:
            continue
        if size > MAX_FILE_BYTES:
            continue
        out.append({"path": p, "rel": str(p.relative_to(root)).replace("\\", "/"),
                    "ext": p.suffix.lower(), "bytes": size})
    return out


def classify(rel, ext):
    low, name = rel.lower(), Path(rel).name.lower()
    if name in SKIP_NAMES or low.startswith("environment/") or name.endswith(".zip"):
        return "instruction"
    if re.match(r"^(references?|refs?|bibliography|cit\w*|literature)", name) or ext == ".bib":
        return "reference"
    if re.match(r"^(paper|manuscript|article|main|draft|submission|preprint)", name):
        return "manuscript"
    if re.search(r"(^|/)(figures?|figs?)/", low):
        return "figure"
    if re.search(r"(^|/)(tables?)/", low):
        return "table"
    if ext in DATA_EXT:
        return "data"
    return "manuscript"


# ------------------------------------------------------------------ references
def parse_bib(text):
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\s*\}\s*", text or "", re.S):
        kind, key, body = m.group(1).lower(), m.group(2), m.group(3)

        def fld(nm):
            f = re.search(r"\b%s\s*=\s*[{\"]([^}\"]*)[}\"]" % nm, body, re.I)
            return f.group(1).strip() if f else None
        yr = re.search(r"(?:19|20)\d{2}", fld("year") or "")
        out.append({"ref_id": "", "label": key, "style": "bib", "raw": squash(m.group(0), 400),
                    "year": yr.group(0) if yr else None, "title": fld("title"),
                    "authors": fld("author"), "doi": fld("doi"),
                    "arxiv": None, "container": fld("journal") or fld("booktitle"),
                    "status_flag": "preprint" if kind in ("unpublished", "preprint") else None,
                    "locator": None, "source_id": None})
    return out


def mk_entry(label, raw, unit):
    raw = squash(raw, 600)
    year = re.search(r"(?<!\d)((?:19|20)\d{2})[a-z]?(?!\d)", raw)
    doi = re.search(r"10\.\d{4,9}/[^\s,;)\]}>]+", raw)
    arx = re.search(r"arxiv[:\s]*((?:\d{4}\.\d{4,5})|([a-z\-]+/\d{7}))", raw, re.I)
    low = raw.lower()
    st = "retracted" if ("retract" in low or "撤稿" in raw) else \
         "corrected" if ("erratum" in low or "corrigendum" in low or "更正" in raw) else \
         "preprint" if re.search(r"arxiv|biorxiv|medrxiv|ssrn|researchsquare|chemrxiv|preprint|预印本", low) else None
    authors = re.split(r"[\(（]?(?:19|20)\d{2}", raw)[0].strip(" .,，、")[:160]
    return {"ref_id": "", "label": label, "style": "numeric" if label else "author_year",
            "raw": raw, "year": year.group(1) if year else None, "title": None,
            "authors": authors or None, "doi": doi.group(0) if doi else None,
            "arxiv": arx.group(1) if arx else None, "container": None, "status_flag": st,
            "locator": unit.get("locator"), "source_id": unit.get("source_id")}


def value_of_refs(units, bib_entries):
    entries, seen = list(bib_entries), {}
    for u in units:
        if u["section_key"] != "references":
            continue
        t = u["text"]
        marks = list(REF_MARK.finditer(t))
        if not marks:
            for line in [x for x in t.split("\n") if len(x.strip()) > 20]:
                entries.append(mk_entry(None, line, u))
            continue
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(t)
            e = mk_entry(m.group(1) or m.group(2), t[m.start():end], u)
            if e["label"] in seen:
                seen[e["label"]]["dup"] = True
                continue
            seen[e["label"]] = e
            entries.append(e)
    for i, e in enumerate(entries, 1):
        e["ref_id"] = "R%02d" % i
    return entries


# ------------------------------------------------------------------ citations
def expand_nums(raw):
    out = []
    for part in re.split(r"\s*[,;，、]\s*", raw):
        m = re.match(r"^(\d{1,3})\s*[-–—]\s*(\d{1,3})$", part.strip())
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(str(x) for x in range(a, b + 1)) if 0 < b - a <= 40 else out.extend([m.group(1), m.group(2)])
        elif part.strip().isdigit():
            out.append(part.strip())
    return out


def pair_citations(units, refs):
    by_label = {}
    for e in refs:
        by_label.setdefault(str(e["label"]).lower(), e)
    nums = sorted(int(k) for k in by_label if str(k).isdigit())
    gap = bool(nums) and nums[-1] > len(nums)
    cites = []
    for u in units:
        if u["section_key"] == "references":
            continue
        for sent in split_sentences(u["text"]):
            found = [("numeric", m.group(0), expand_nums(m.group(1))) for m in NUM_MARK.finditer(sent)]
            found += [("bib", m.group(0), [k.strip() for k in m.group(1).split(",") if k.strip()])
                      for m in CITE_TEX.finditer(sent)]
            found += [("author_year", m.group(0), [m.group(1).lower() + "|" + m.group(2)])
                      for m in AUTH_MARK.finditer(sent)]
            found += [("author_year", m.group(0), [m.group(1) + "|" + m.group(2)])
                      for m in CN_MARK.finditer(sent)]
            for style, marker, targets in found:
                hit, pairing = [], "paired"
                for t in targets:
                    if style == "author_year":
                        sn, yr = t.split("|", 1)
                        cand = [e for e in refs if str(e.get("year") or "") == yr
                                and sn in (str(e.get("authors") or "") + " " + str(e.get("raw") or "")).lower()]
                        if not cand:
                            pairing = "missing_entry"
                        elif len(cand) > 1:
                            pairing = "ambiguous" if pairing == "paired" else pairing
                            hit.extend(c["ref_id"] for c in cand[:3])
                        else:
                            hit.append(cand[0]["ref_id"])
                    else:
                        e = by_label.get(str(t).lower())
                        if not e:
                            pairing = "missing_entry"
                        else:
                            hit.append(e["ref_id"])
                if pairing == "paired" and gap and style == "numeric":
                    pairing = "numbering_gap"
                cites.append({"cite_id": "CIT-%03d" % (len(cites) + 1), "marker": marker,
                              "style": style, "uid": u["uid"], "locator": u["locator"],
                              "page": u["page"], "section": u["section"],
                              "sentence": squash(sent, 400), "targets": targets,
                              "ref_ids": hit, "pairing": pairing})
    return cites, gap


# ------------------------------------------------------------------ candidates
# ------------------------------------------------------------------ case / index
def load_case(input_dir):
    p = Path(input_dir) / "case.json"
    if not p.exists():
        return {}, ["case.json not found"]
    obj, err = load_json(p)
    if obj is None:
        salv = {}
        try:
            raw = p.read_text("utf-8", "replace")
            m = re.search(r'"(?:case_id|caseId|task_id|id)"\s*:\s*"([^"]{1,80})"', raw)
            if m:
                salv["case_id"] = m.group(1)
        except Exception:
            pass
        return salv, ["case.json unreadable (%s)%s" % (err, "; case_id salvaged by regex"
                                                       if salv else "")]
    if not isinstance(obj, dict):
        return {}, ["case.json is not a JSON object"]
    return obj, []


def norm_contract(v):
    keys, spec = [], {}
    if isinstance(v, dict):
        for k, s in v.items():
            keys.append(str(k))
            spec[str(k)] = s if isinstance(s, (dict, list, str)) else {"value": s}
    elif isinstance(v, list):
        for it in v:
            if isinstance(it, str):
                keys.append(it)
                spec[it] = {}
            elif isinstance(it, dict):
                nm = it.get("name") or it.get("key") or it.get("field") or it.get("id")
                if nm:
                    keys.append(str(nm))
                    spec[str(nm)] = it
    return keys, spec


def contract_of(case):
    for k in ("output_contract", "outputContract", "contract", "output_schema",
              "expected_output", "output_fields", "deliverable_contract"):
        if isinstance(case.get(k), (dict, list)) and case.get(k):
            return norm_contract(case[k]), k
    for nest in ("input", "inputs", "task", "meta"):
        sub = case.get(nest)
        if isinstance(sub, dict):
            for k in ("output_contract", "contract", "output_schema"):
                if isinstance(sub.get(k), (dict, list)) and sub.get(k):
                    return norm_contract(sub[k]), "%s.%s" % (nest, k)
    return ([], {}), None


def case_id_of(case):
    for k in ("case_id", "caseId", "id", "task_id", "case", "instance_id"):
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v)
    return None


def read_task(input_dir):
    for nm in ("task.md", "TASK.md", "task.txt", "instruction.md"):
        p = Path(input_dir) / nm
        if p.exists():
            try:
                return p.read_text("utf-8", "replace")
            except Exception:
                pass
    return ""


def new_index():
    return {"schema": INDEX_SCHEMA, "input_dir": "", "case_id": None, "case_meta": {},
            "task_excerpt": "", "contract_keys": [], "contract_spec": {}, "contract_from": None,
            "sources": [], "units": [], "references": [], "citations": [],
            "claim_candidates": [], "numeric_candidates": [], "numeric_index": {},
            "gaps": [], "errors": [], "stats": {}}


def build_index(input_dir):
    idx = new_index()
    idx["input_dir"] = str(input_dir)
    case, errs = load_case(input_dir)
    idx["errors"].extend(errs)
    idx["case_id"] = case_id_of(case)
    (keys, spec), src = contract_of(case)
    idx["contract_keys"], idx["contract_spec"], idx["contract_from"] = keys, spec, src
    if not keys:
        idx["gaps"].append({"code": "contract_missing",
                            "detail": "case.json 未提供 output_contract；使用内置标准字段集"})
    for k in ("task_instruction", "instruction", "task", "title", "description"):
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            idx["case_meta"][k] = squash(v, 3000)
    idx["task_excerpt"] = squash(read_task(input_dir), 2500)

    files = discover(input_dir)
    if not files:
        idx["gaps"].append({"code": "no_input_files", "detail": "/input 下未发现可读材料"})
    units = []
    for f in files:
        kind, sid = classify(f["rel"], f["ext"]), "S%02d" % (len(idx["sources"]) + 1)
        rec = {"source_id": sid, "path": str(f["path"]), "rel": f["rel"], "kind": kind,
               "format": f["ext"].lstrip("."), "parser": None, "bytes": f["bytes"],
               "units": 0, "text_chars": 0, "quality": "unread", "sha256_12": None}
        try:
            rec["sha256_12"] = hashlib.sha256(f["path"].read_bytes()[:MAX_READ_BYTES]).hexdigest()[:12]
        except Exception:
            pass
        if kind == "instruction":
            rec["quality"] = "skipped_instruction"
            idx["sources"].append(rec)
            continue
        try:
            got = read_any(f["path"])
        except Exception as e:
            got = {"pages": [], "parser": "error", "quality": "empty"}
            idx["errors"].append("parse %s: %s: %s" % (f["rel"], type(e).__name__, e))
        rec["parser"], rec["quality"] = got["parser"], got["quality"]
        pages = got["pages"] or []
        rec["text_chars"] = sum(len(p) for p in pages)
        if rec["format"] == "pdf" and rec["quality"] == "low":
            idx["gaps"].append({"code": "pdf_text_quality_low", "scope": f["rel"],
                                "detail": "PDF 文本层质量低（parser=%s），段落边界可能丢失，"
                                          "locator 粒度降为页/块" % got["parser"]})
        if rec["text_chars"] < 60:
            idx["gaps"].append({"code": "unreadable_material", "scope": f["rel"],
                                "detail": "解析文本不足（parser=%s），相关结论只能待复核" % got["parser"]})
        new = []
        for pi, ptxt in enumerate(pages):
            new.extend(text_to_units(ptxt, sid, f["rel"],
                                     page=(pi + 1) if len(pages) > 1 else None))
        if len(new) > MAX_UNITS:
            new = new[:MAX_UNITS]
            idx["gaps"].append({"code": "units_truncated", "scope": f["rel"],
                                "detail": "段落单元超过上限 %d，已截断" % MAX_UNITS})
        for u in new:
            u["uid"] = "U%04d" % (len(units) + 1)
            units.append(u)
        rec["units"] = len(new)
        idx["sources"].append(rec)
        if len(units) >= MAX_UNITS:
            break

    idx["units"] = units
    bib = []
    for f in files:
        if f["ext"] == ".bib":
            try:
                bib.extend(parse_bib(f["path"].read_text("utf-8", "replace")))
            except Exception as e:
                idx["errors"].append("bib parse %s: %s" % (f["rel"], e))
    idx["references"] = value_of_refs(units, bib)
    if not idx["references"]:
        idx["gaps"].append({"code": "no_reference_list",
                            "detail": "未找到参考文献表；引文无法配对，全部待复核"})
    cites, gap = pair_citations(units, idx["references"])
    idx["citations"] = cites
    if gap:
        idx["gaps"].append({"code": "numbering_gap",
                            "detail": "文献表编号不连续，可能错位"})
    missing = [c for c in cites if c["pairing"] != "paired"]
    if missing:
        idx["gaps"].append({"code": "unpaired_citations", "count": len(missing),
                            "detail": "%d 处引文标记无法与文献表条目配对" % len(missing)})
    idx["claim_candidates"] = []
    idx["numeric_candidates"] = []
    idx["numeric_index"] = {}
    idx["stats"] = {"files": len(idx["sources"]), "corpus_files": sum(1 for s in idx["sources"] if s["units"]),
                    "units": len(units), "references": len(idx["references"]),
                    "citations": len(cites), "claim_candidates": len(idx["claim_candidates"]),
                    "numeric_candidates": len(idx["numeric_candidates"]),
                    "text_chars": sum(s["text_chars"] for s in idx["sources"])}
    return idx


def dump_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(p)
    return p


def load_json(path):
    p = Path(path)
    if not p.exists():
        return None, "missing: %s" % p
    try:
        return json.loads(p.read_text("utf-8")), None
    except Exception as e:
        try:
            return json.loads(p.read_text("utf-8-sig")), None
        except Exception:
            return None, "bad json (%s): %s" % (type(e).__name__, e)
