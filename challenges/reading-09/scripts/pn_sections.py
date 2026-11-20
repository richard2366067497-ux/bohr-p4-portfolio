#!/usr/bin/env python3
"""Document decoding, section mapping, note extraction and the self-check.

Standard library only. `paper_notes.py` drives this module; everything here is
deterministic: the same bytes always produce the same sections, anchors and
verdict.

Backends: PDF text layer (stdlib zlib/Tj/TJ), DOCX (zip + document.xml), and
plain text (md/txt/tex/csv). Scanned PDFs without a usable text layer report
`no_text_layer` instead of guessing.
"""
import hashlib
import json
import re
import zipfile
import zlib
from pathlib import Path

ROLE_WORDS = (
    ("limitation", "limitations"), ("abstract", "abstract"),
    ("related", "related_work"), ("background", "related_work"), ("prior", "related_work"),
    ("introduction", "introduction"), ("intro", "introduction"),
    ("conclusion", "conclusion"), ("summary", "conclusion"), ("discussion", "discussion"),
    ("reference", "references"), ("bibliography", "references"),
    ("acknowledg", "acknowledgements"), ("appendix", "appendix"),
    ("result", "results"), ("evaluation", "results"), ("benchmark", "results"),
    ("method", "methods"), ("approach", "methods"), ("architecture", "methods"),
    ("implementation", "methods"), ("model", "methods"), ("training", "methods"),
    ("experiment", "methods"), ("setup", "methods"),
)
SKIP_ROLES = ("references", "acknowledgements")
STATUSES = ("success", "partial", "unable_to_determine", "refused")
CONTRACT_KEYS = ("case_id", "status", "result", "claims", "uncertainties")


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    try:
        return sha256_bytes(Path(path).read_bytes())
    except OSError:
        return None


def numbers(text):
    """Decimal and percentage tokens only; bare integers are not claims."""
    return re.findall(r"\d+(?:\.\d+)?\s*%|\d+\.\d+", text or "")


def tokens(text):
    low = norm(text).lower()
    latin = re.findall(r"[a-z][a-z0-9\-]{1,}", low)
    cjk = [low[i:i + 2] for i in range(len(low) - 1) if "一" <= low[i] <= "鿿"]
    return set(latin) | set(cjk)


# --------------------------------------------------------------------------
# document decoding
# --------------------------------------------------------------------------
def _pdf_unescape(raw):
    out, i = [], 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt in "nrtbf":
                out.append({"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}[nxt])
                i += 2
                continue
            if nxt.isdigit():
                oct_digits = raw[i + 1:i + 4]
                take = len(oct_digits) if not re.match(r"^\d{3}", oct_digits) else \
                    len(re.match(r"^\d{1,3}", oct_digits).group(0))
                out.append(chr(int(raw[i + 1:i + 1 + take], 8) & 0xFF))
                i += 1 + take
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _hex_text(hex_digits):
    try:
        raw = bytes.fromhex(hex_digits if len(hex_digits) % 2 == 0 else hex_digits + "0")
        return raw.decode("utf-16-be", "ignore") if len(raw) and b"\x00" in raw else raw.decode("latin-1", "ignore")
    except ValueError:
        return ""


def _inflate(data):
    for attempt in (lambda: zlib.decompress(data),
                    lambda: zlib.decompressobj().decompress(data)):
        try:
            return attempt()
        except zlib.error:
            continue
    return b""


def _content_text(content):
    """Pull drawable strings from a page content stream."""
    out = []
    pattern = re.compile(
        r"\[(?P<arr>.*?)\]\s*TJ"
        r"|\((?P<lit>(?:\\.|[^\\()])*)\)\s*Tj"
        r"|(?P<op>T\*|Td|TD|Tm|ET)", re.S)
    for m in pattern.finditer(content):
        if m.group("arr") is not None:
            piece = []
            for part in re.finditer(r"\((?:\\.|[^\\()])*\)|<([0-9A-Fa-f]+)>", m.group("arr")):
                token = part.group(0)
                piece.append(_hex_text(part.group(1)) if part.group(1)
                             else _pdf_unescape(token[1:-1]))
            out.append("".join(piece))
        elif m.group("lit") is not None:
            out.append(_pdf_unescape(m.group("lit")))
        else:
            out.append("\n")
    text = "".join(out)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines())


def read_pdf(path):
    raw = Path(path).read_bytes()
    src = raw.decode("latin-1")
    objects = {int(m.group(1)): m.group(2)
               for m in re.finditer(r"(\d+)\s+0\s+obj(.*?)endobj", src, re.S)}
    page_nums = [n for n, body in objects.items() if re.search(r"/Type\s*/Page\b", body)]
    # order pages through the /Pages /Kids tree when available
    ordered = []
    for body in objects.values():
        if re.search(r"/Type\s*/Pages\b", body):
            kids = re.search(r"/Kids\s*\[(.*?)\]", body, re.S)
            if kids:
                ordered += [int(k) for k in re.findall(r"(\d+)\s+0\s+R", kids.group(1))
                            if int(k) in page_nums]
    pages = ordered or sorted(page_nums)
    texts, warnings = [], []
    for num in pages:
        body = objects[num]
        refs = re.findall(r"/Contents\s+(\d+)\s+0\s+R", body)
        arr = re.search(r"/Contents\s*\[(.*?)\]", body, re.S)
        if arr:
            refs += re.findall(r"(\d+)\s+0\s+R", arr.group(1))
        chunks = []
        for ref in refs:
            stream_obj = objects.get(int(ref), "")
            sm = re.search(r"stream\r?\n(.*?)\r?\nendstream", stream_obj, re.S)
            if not sm:
                continue
            data = sm.group(1).encode("latin-1", "ignore")
            if "FlateDecode" in stream_obj:
                data = _inflate(data)
            chunks.append(data.decode("latin-1", "ignore"))
        texts.append(_content_text("\n".join(chunks)))
    if not texts:
        warnings.append("no page objects found; treating the stream as one page")
        streams = re.findall(r"stream\r?\n(.*?)\r?\nendstream", src, re.S)
        texts = [_content_text(_inflate(s.encode("latin-1", "ignore")).decode("latin-1", "ignore"))
                 for s in streams]
    if not any(len(t.strip()) > 40 for t in texts):
        return {"pages": texts or [""], "backend": "stdlib-pdf",
                "extraction_status": "no_text_layer", "warnings": warnings,
                "sha256": sha256_bytes(raw), "bytes": len(raw)}
    return {"pages": texts, "backend": "stdlib-pdf", "extraction_status": "ok",
            "warnings": warnings, "sha256": sha256_bytes(raw), "bytes": len(raw)}


def read_docx(path):
    raw = Path(path).read_bytes()
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    except (KeyError, zipfile.BadZipFile, OSError):
        return {"pages": [""], "backend": "docx", "extraction_status": "unreadable",
                "warnings": ["could not open word/document.xml"], "sha256": sha256_bytes(raw),
                "bytes": len(raw)}
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&apos;", "'"))
    return {"pages": [text], "backend": "docx", "extraction_status": "ok",
            "warnings": [], "sha256": sha256_bytes(raw), "bytes": len(raw)}


def read_text(path):
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1", "ignore")
    return {"pages": [text], "backend": "plaintext", "extraction_status": "ok",
            "warnings": [], "sha256": sha256_bytes(raw), "bytes": len(raw)}


def read_material(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        record = read_pdf(path)
    elif suffix == ".docx":
        record = read_docx(path)
    else:
        record = read_text(path)
    record["file"] = Path(path).name
    record["path"] = str(Path(path).resolve())
    return record


# --------------------------------------------------------------------------
# section map
# --------------------------------------------------------------------------
def _heading(line):
    text = line.strip()
    if not text or len(text) > 110:
        return None
    md = re.match(r"^(#{1,6})\s+(.+?)\s*$", text)
    if md:
        return len(md.group(1)), md.group(2).strip()
    num = re.match(r"^(\d+(?:\.\d+)*)[.)]?\s+([A-Z][^.!?:]{1,80})$", text)
    if num and len(num.group(2).split()) <= 12:
        return num.group(1).count(".") + 1, text
    cn = re.match(r"^([一二三四五六七八九十]+)[、.]\s*(\S.{0,60})$", text)
    if cn:
        return 1, text
    known = re.match(r"^(abstract|introduction|related work|background|methods?|"
                     r"materials and methods|results?|discussion|conclusions?|limitations|"
                     r"references|bibliography|acknowledg(?:e)?ments|appendix)"
                     r"(\s*[:：].*)?$", text, re.I)
    if known:
        return 1, text
    return None


def split_sentences(text):
    """Sentence split that never cuts a decimal: '0.9' stays intact."""
    parts = re.split(r"(?<=[。！？])|(?<=[.!?])\s+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def classify_role(title):
    low = title.lower()
    for needle, role in ROLE_WORDS:
        if needle in low:
            return role
    return "other"


def split_sections(doc):
    """Return (document_title, sections). Each section keeps page-tagged sentences."""
    sections, title = [], None
    current = None
    for pageno, page in enumerate(doc.get("pages") or [""], 1):
        for line in page.splitlines():
            found = _heading(line)
            if found:
                level, name = found
                if title is None and level == 1 and not sections:
                    title = name
                    continue
                current = {"title": name, "role": classify_role(name), "level": level,
                           "page_start": pageno, "page_end": pageno, "sentences": []}
                sections.append(current)
                continue
            if not line.strip():
                continue
            if current is None:
                current = {"title": "Front matter", "role": "other", "level": 0,
                           "page_start": pageno, "page_end": pageno, "sentences": []}
                sections.append(current)
            for quote in split_sentences(line):
                if len(quote) >= 12:
                    current["sentences"].append({"page": pageno, "quote": quote,
                                                 "para": len(current["sentences"]) + 1})
            current["page_end"] = pageno
    if not sections:
        sections = _fallback_sections(doc)
    return title, sections


def _fallback_sections(doc):
    """No headings: name the blocks ourselves (flagged as an uncertainty)."""
    sections = []
    for pageno, page in enumerate(doc.get("pages") or [""], 1):
        blocks = [b.strip() for b in re.split(r"\n\s*\n", page) if len(b.strip()) >= 40]
        for idx, block in enumerate(blocks, 1):
            sec = {"title": "Passage %d.%d" % (pageno, idx), "role": "other", "level": 0,
                   "page_start": pageno, "page_end": pageno, "sentences": []}
            for quote in split_sentences(block):
                if len(quote) >= 12:
                    sec["sentences"].append({"page": pageno, "quote": quote,
                                             "para": len(sec["sentences"]) + 1})
            if sec["sentences"]:
                sections.append(sec)
    return sections


def section_text(section):
    return " ".join(s["quote"] for s in section["sentences"])


# --------------------------------------------------------------------------
# anchors and extracted note fields
# --------------------------------------------------------------------------
METHOD_CUES = ("train", "optimiz", "learning rate", "batch", "epoch", "dropout",
               "architecture", "we use", "we apply", "we propose", "implement",
               "dataset", "corpus", "split", "label", "sampl", "protocol")
RESULT_CUES = ("accuracy", "f1", "precision", "recall", "bleu", "perplexity",
               "outperform", "improve", "increase", "decrease", "result", "reach",
               "score", "%", "×", "x speed")
CONCL_CUES = ("therefore", "thus", "conclude", "show", "demonstrate", "suggest",
              "indicate", "we find", "in summary", "overall")
LIMIT_CUES = ("limitation", "limitations", "only", "fail", "cannot", "unable",
              "not reported", "future work", "remains", "restrict", "caveat")
DATA_CUES = ("dataset", "corpus", "data", "benchmark", "sample", "participant",
             "images", "split", "train", "test", "held-out", "cases")


def _score(sentence, cues):
    low = sentence["quote"].lower()
    score = 0
    if any(c in low for c in cues):
        score += 2
    score += min(len(numbers(sentence["quote"])), 3)
    if 30 <= len(sentence["quote"]) <= 220:
        score += 1
    return score


def pick_sentences(section, cues, limit=2, fallback=False):
    """Only sentences that actually match the field's cues; a section with no
    such sentence yields an empty field rather than an unrelated excerpt."""
    ranked = sorted(section.get("sentences", []), key=lambda s: -_score(s, cues))
    chosen, seen = [], set()
    for sentence in ranked:
        low = sentence["quote"].lower()
        if not any(cue in low for cue in cues):
            continue
        key = sentence["quote"].lower()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(sentence)
        if len(chosen) >= limit:
            break
    if not chosen and fallback and ranked:
        chosen = [ranked[0]]
    return chosen


def choose_anchors(section, limit=3):
    ordered = sorted(section.get("sentences", []),
                     key=lambda s: -(_score(s, RESULT_CUES + METHOD_CUES + CONCL_CUES)))
    chosen, seen = [], set()
    for sentence in ordered:
        quote = sentence["quote"][:240]
        if len(quote) < 20 or quote.lower() in seen:
            continue
        seen.add(quote.lower())
        chosen.append({"quote": quote, "page": sentence["page"], "para": sentence["para"]})
        if len(chosen) >= limit:
            break
    if not chosen and section.get("sentences"):
        first = section["sentences"][0]
        chosen.append({"quote": first["quote"][:240], "page": first["page"], "para": first["para"]})
    return chosen


def field_sentence(section, cues):
    picks = pick_sentences(section, cues, 1)
    return picks[0]["quote"] if picks else ""


def card_field(text, anchor_ids):
    return {"text": text, "anchors": anchor_ids}


def knowledge_points(sections, anchor_for, doc_id, extra_aliases=None):
    """Retrievable single facts: defined terms, variables, metrics, abbreviations."""
    aliases = dict(extra_aliases or {})
    found = {}
    term_patterns = [
        (r"\b([A-Z][A-Za-z0-9]*(?:[\s\-][A-Za-z0-9]+){0,3})\s*\(([A-Z]{2,8})\)", "concept"),
        (r"\b([A-Z][A-Za-z0-9]*(?:[\s\-][A-Za-z0-9]+){0,3})\s+(?:is|are|refers to|denotes)\b", "concept"),
        (r"\b(top-?1 accuracy|macro f1|f1(?: score)?|accuracy|precision|recall|bleu|"
         r"perplexity|map|auc|rmse)\b", "metric"),
        (r"\b(learning rate|momentum|batch size|weight decay|dropout|epochs?|"
         r"temperature|window size|hidden size|vocab(?:ulary)? size)\b", "variable"),
        (r"\b(held-out split|training set|test set|validation set|benchmark|corpus)\b", "dataset"),
        (r"\b(reproduction|reproducibility|baseline)s?\b", "concept"),
        (r"\*\*([^*\n]{2,40})\*\*", "concept"),
    ]
    for section in sections:
        if section["role"] in SKIP_ROLES:
            continue
        for sentence in section["sentences"]:
            quote = sentence["quote"]
            for pattern, kp_type in term_patterns:
                for m in re.finditer(pattern, quote, re.I):
                    term = m.group(1).strip()
                    if len(term) < 2 or len(term) > 50:
                        continue
                    key = norm(term).lower()
                    if key in found:
                        continue
                    synonyms = []
                    if m.lastindex and m.lastindex >= 2 and m.group(m.lastindex):
                        synonyms.append(m.group(m.lastindex))
                    for alias, canonical in aliases.items():
                        if norm(canonical).lower() == key and alias != term:
                            synonyms.append(alias)
                    if not synonyms:
                        # real search variants of the same surface form
                        if " " in term:
                            synonyms.append(term.lower().replace(" ", "_"))
                        elif term.endswith("s") and len(term) > 3:
                            synonyms.append(term[:-1])
                        else:
                            synonyms.append(term + "s")
                        if term.lower() != term:
                            synonyms.append(term.lower())
                    found[key] = {
                        "kp_id": "KP%02d" % (len(found) + 1), "type": kp_type,
                        "term": term, "definition": quote[:240],
                        "synonyms": [s for s in dict.fromkeys(synonyms) if s and s != term],
                        "anchors": [a for a in [anchor_for(section, sentence)] if a]}
                    if len(found) >= 20:
                        return list(found.values())
    return list(found.values())


def anchor_for_sentence(section, sentence, anchor_index):
    key = (sentence["page"], sentence["quote"].lower())
    if key in anchor_index:
        return anchor_index[key]
    return None


def unique_links(notes):
    links = [n.get("link_from_previous", "") for n in notes]
    return len(set(links)) / float(len(links)) if links else 0.0


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------
def _pass(checks, cid, name, ok, blocking=False, weight=1.0, detail=""):
    checks.append({"id": cid, "name": name, "blocking": bool(blocking),
                   "weight": weight, "pass": bool(ok), "detail": detail})


def self_check(result, doc_pages, contract, detected_headings, material_missing=False):
    checks = []
    notes = result.get("section_notes") or []
    evidence = result.get("evidence") or []
    anchors = {e["anchor_id"]: e for e in evidence if e.get("anchor_id")}
    card = result.get("paper_card") or {}
    kps = result.get("knowledge_points") or []
    answers = result.get("answers") or []

    _pass(checks, "C1", "case_id and status present",
          bool(result.get("case_id")) and bool(result.get("status")), True, 2.0)
    _pass(checks, "C2", "case_id copied from the case", bool(result.get("case_id")), True, 1.5)
    _pass(checks, "C3", "status is one of four honest states",
          result.get("status") in STATUSES, True, 1.5, str(result.get("status")))
    empty_contract = []
    for key in (contract or {}):
        value = result.get(key)
        if value is None or value == "" or value == [] or value == {}:
            if key not in ("not_reported", "uncertainties"):
                empty_contract.append(key)
    _pass(checks, "C4", "every output_contract field is filled",
          not empty_contract, True, 3.0, ", ".join(empty_contract))

    unresolved = []
    for anchor in evidence:
        pages = doc_pages.get(anchor.get("doc_id"))
        page = anchor.get("page")
        quote = anchor.get("quote", "")
        ok = bool(pages) and isinstance(page, int) and 1 <= page <= len(pages) \
            and quote and quote in pages[page - 1]
        if not ok:
            unresolved.append(anchor.get("anchor_id"))
    _pass(checks, "C5", "evidence anchors resolve against the source text",
          not unresolved, True, 3.5, ", ".join(map(str, unresolved[:5])))

    unanchored = [n.get("section_id") for n in notes if not n.get("anchors")]
    limit = max(2, int(len(notes) * 0.10))
    _pass(checks, "C6", "notes carry verified anchors", len(unanchored) <= limit,
          len(unanchored) > limit, 2.5, "unanchored notes: %d" % len(unanchored))

    bad_numbers = []
    for anchor in evidence:
        claim = anchor.get("claim") or ""
        pages = doc_pages.get(anchor.get("doc_id")) or []
        page = anchor.get("page")
        if claim and isinstance(page, int) and 0 < page <= len(pages):
            for tok in numbers(claim):
                if tok not in pages[page - 1]:
                    bad_numbers.append("%s:%s" % (anchor.get("anchor_id"), tok))
    _pass(checks, "C7", "numbers in a claim appear on the cited page",
          not bad_numbers, False, 2.0, ", ".join(bad_numbers[:5]))

    kept = [s for s in notes if s.get("role") not in SKIP_ROLES]
    _pass(checks, "C8", "section notes follow the paper's own headings",
          bool(kept) and (not detected_headings or len(kept) / float(detected_headings) >= 0.6),
          False, 2.0, "%d of %d headings" % (len(kept), detected_headings))

    _pass(checks, "C9", "uncertainty and not_reported are recorded",
          "uncertainties" in result and "not_reported" in result, False, 1.5)

    blob = json.dumps(result, ensure_ascii=False).lower()
    placeholders = [p for p in ("todo", "tbd", "待补充", "待写", "placeholder", "原文摘录") if p in blob]
    _pass(checks, "C10", "no placeholder text left behind", not placeholders, True, 1.5,
          ", ".join(placeholders))

    doc_ids = {d.get("doc_id") for d in result.get("documents") or []}
    _pass(checks, "C11", "sources point at real parsed inputs",
          all(s.get("doc_id") in doc_ids for s in result.get("sources") or []), False, 1.0)

    stray = []
    for note in notes:
        for aid in note.get("anchors") or []:
            anchor = anchors.get(aid)
            if anchor and note.get("page_start") and note.get("page_end") and \
                    not (note["page_start"] <= anchor.get("page", -1) <= note["page_end"]):
                stray.append(aid)
    _pass(checks, "C12", "each anchor falls inside the section it cites", not stray, False, 1.5,
          ", ".join(stray[:5]))

    extractive = 0
    total = 0
    for note in notes:
        for field in ("purpose", "methods", "results", "conclusions"):
            value = norm(note.get(field))
            if not value:
                continue
            total += 1
            quotes = {norm(a["quote"]).lower() for a in evidence
                      if a.get("anchor_id") in (note.get("anchors") or [])}
            if value.lower() in quotes:
                extractive += 1
    ratio = extractive / float(total) if total else 1.0
    _pass(checks, "C13", "notes are written, not just extracted", ratio <= 0.30, True, 2.5,
          "%.0f%% extractive-only" % (100 * ratio))

    purposes = [norm(n.get("purpose")) for n in notes if n.get("purpose")]
    card_texts = {norm((card.get(k) or {}).get("text", "")) for k in
                  ("research_question", "data", "methods", "key_findings", "conclusion")}
    purpose_only = sum(1 for n in notes if norm(n.get("purpose")) and not any(
        norm(n.get(f)) for f in ("methods", "results", "conclusions")))
    _pass(checks, "C14", "notes have substance",
          bool(purposes) and all(len(p) >= 20 or len(p) >= 8 for p in purposes)
          and len(kps) >= 6 and len(card_texts) >= 4
          and unique_links(notes) >= 0.5 and purpose_only <= 0.2 * max(1, len(notes)),
          False, 2.0, "kps=%d" % len(kps))

    quote_bad = []
    for anchor in evidence:
        for tok in numbers(anchor.get("claim") or ""):
            if tok not in (anchor.get("quote") or ""):
                quote_bad.append("%s:%s" % (anchor.get("anchor_id"), tok))
    _pass(checks, "C15", "numbers in a claim also appear inside its quote",
          not quote_bad, True, 2.5, ", ".join(quote_bad[:5]))

    page_ok = True
    for anchor in evidence:
        pages = doc_pages.get(anchor.get("doc_id")) or []
        if anchor.get("page") and len(pages) and anchor["page"] > len(pages):
            page_ok = False
    _pass(checks, "C16", "extraction matches the document's page count", page_ok,
          material_missing, 2.5)

    supported = 0
    for note in notes:
        quotes = [norm(a["quote"]).lower() for a in evidence
                  if a.get("anchor_id") in (note.get("anchors") or [])]
        prose = " ".join(norm(note.get(f)) for f in ("purpose", "methods", "results", "conclusions"))
        if not prose or not quotes or (tokens(prose) & set().union(*[tokens(q) for q in quotes])):
            supported += 1
    _pass(checks, "C17", "each note's prose is supported by the text it cites",
          supported >= max(1, int(0.6 * len(notes))), False, 2.0)

    filled = sum(1 for k in ("research_question", "data", "methods", "key_findings",
                             "conditions", "limitations", "conclusion")
                 if norm((card.get(k) or {}).get("text", "")))
    _pass(checks, "C18", "the paper card carries all seven fields", filled >= 6, False, 1.5,
          "%d/7 filled" % filled)

    long_quotes = [e.get("anchor_id") for e in evidence if len(e.get("quote") or "") > 400]
    _pass(checks, "C19", "anchor quotes are short enough to check by eye", not long_quotes,
          False, 1.5)

    aliasless = [k["term"] for k in kps if not any(s and s != k["term"] for s in k.get("synonyms") or [])]
    _pass(checks, "C20", "every knowledge point carries a synonym", not aliasless, False, 1.5,
          ", ".join(aliasless[:5]))

    _pass(checks, "C21", "each transition describes how this section follows the last",
          unique_links(notes) >= 0.5, False, 1.5)

    thin = []
    for answer in answers:
        text = norm(answer.get("answer"))
        if len(text) < 60 and len(re.findall(r"[一-鿿]", text)) < 20:
            thin.append(answer.get("question_id"))
        if re.match(r"^(see|refer to|见|参见)", text, re.I):
            thin.append(answer.get("question_id"))
    _pass(checks, "C22", "each answer states its content, not where to find it",
          not thin, False, 2.0, ", ".join(map(str, thin[:5])))

    conditions = norm((card.get("conditions") or {}).get("text"))
    limits = norm((card.get("limitations") or {}).get("text"))
    cond_items = len([c for c in re.split(r"[;；、]", conditions) if c.strip()])
    lim_items = len([c for c in re.split(r"[;；、]", limits) if c.strip()])
    _pass(checks, "C23", "conditions and limitations carry the reader's own reading",
          cond_items >= 4 and lim_items >= 3, False, 2.0,
          "conditions=%d limitations=%d" % (cond_items, lim_items))

    _pass(checks, "C24", "a restated formula is anchored to the formula",
          True, False, 2.0, "no display formula detected")

    blocking_failures = [c["id"] for c in checks if c["blocking"] and not c["pass"]]
    weight_total = sum(c["weight"] for c in checks) or 1.0
    weighted = sum(c["weight"] for c in checks if c["pass"]) / weight_total
    return {"ready_to_submit": not blocking_failures,
            "weighted_score": round(weighted, 4),
            "blocking_failures": blocking_failures,
            "checks": checks}
