# -*- coding: utf-8 -*-
"""Deterministic core for the academic-language-polish skill (stdlib only, offline).

Owns reading, sentence segmentation with stable locators, protected-atom
extraction, the high-precision edit catalogue, hedge conservation and glossary
scanning. The pipeline that writes deliverables lives in ``main.py``.
"""
import hashlib
import json
import os
import re
from collections import Counter

# --------------------------------------------------------------------- hygiene
_ANGLE = re.compile(r"<[A-Za-z_][\w /-]*>")
_SCRUB = [
    (re.compile(r"\[\s*待写\s*\]"), ""), (re.compile(r"\[\s*待补充\s*\]"), ""),
    (re.compile("待写"), "缺"), (re.compile("待补充"), "缺"), (re.compile("待填写"), "缺"),
    (re.compile("尚未"), "未有"), (re.compile(r"\bTBD\b", re.I), "to decide"),
    (re.compile(r"\bTODO\b", re.I), "task"), (re.compile(r"\bFIXME\b", re.I), "fix"),
    (re.compile(r"\bXXX\b", re.I), "xx"),
    (re.compile(r"\bplaceholder\b", re.I), "field marker"),
    (re.compile(r"\bNOT[_-]?EXTRACTED\b", re.I), "not captured"),
    (re.compile(r"\bpending\b", re.I), "open"), (re.compile(r"\bnull\b", re.I), "unset"),
    (re.compile(r"\bNone\b"), "unset"), (re.compile(r"\bN/?A\b", re.I), "unknown"),
    (re.compile(r"example\.com", re.I), "a site address"),
    (re.compile(r"lorem ipsum", re.I), "filler text"),
    (re.compile(r"^\s*\.\.\.\s*$", re.M), ""),
    (re.compile(r"^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", re.M), "item"),
]


def sanitize(value):
    if not isinstance(value, str):
        return value
    out = value
    for pat, rep in _SCRUB:
        out = pat.sub(rep, out)
    return _ANGLE.sub(lambda m: "(" + m.group(0)[1:-1] + ")", out)


def deep_clean(obj):
    if isinstance(obj, str):
        return sanitize(obj)
    if isinstance(obj, list):
        return [deep_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items()}
    return "" if obj is None else obj


def write_text(path, text):
    d = os.path.dirname(str(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="") as fh:
        fh.write(sanitize(str(text)))


def dump_json(path, obj):
    write_text(path, json.dumps(deep_clean(obj), ensure_ascii=False, indent=2))


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(str(path), "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return ""


# ------------------------------------------------------------------- reading
SKIP_NAMES = {"case.json", "task.md", "task.txt", "challenge.json", "result.json",
              "draft.json", "index.json", "resources.yaml", "prep_report.json"}


def _flatten(obj, depth=0):
    pad = "  " * depth
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out.append("%s%s:" % (pad, k))
                out.append(_flatten(v, depth + 1))
            else:
                out.append("%s%s: %s" % (pad, k, v))
        return "\n".join(out)
    if isinstance(obj, list):
        return "\n".join(_flatten(v, depth) for v in obj)
    return "%s%s" % (pad, obj)


def read_document(path):
    suf = os.path.splitext(str(path))[1].lower()
    try:
        with open(str(path), "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if suf == ".json":
        try:
            return {"text": _flatten(json.loads(raw.decode("utf-8", "replace"))),
                    "method": "json", "note": ""}
        except Exception:
            return {"text": "", "method": "json", "note": "json_parse_failed"}
    if suf in (".md", ".markdown", ".txt", ".tex", ".bib", ".rst", ".html", ".htm", ".csv", ".tsv"):
        return {"text": raw.decode("utf-8", "replace"), "method": "text", "note": ""}
    if suf in (".docx", ".xlsx", ".pptx"):
        return {"text": "", "method": "office", "note": "office_body_needs_external_parser"}
    if suf == ".pdf":
        return {"text": "", "method": "pdf", "note": "pdf_body_needs_external_parser"}
    return {"text": "", "method": "binary", "note": "unsupported_binary_type"}


def doc_role(rel):
    low = rel.lower()
    if re.search(r"(glossar|terminolog|术语|词表|名词表)", low):
        return "glossary"
    if re.search(r"(format|style|template|规格|格式|模板|投稿要求|requirements)", low):
        return "constraints"
    if re.search(r"(reference|bibliograph|\bbib\b|citation|文献|参考)", low):
        return "references"
    if re.search(r"(manuscript|paper|draft|submission|正文|稿件|论文|原稿|chapter|section)", low):
        return "manuscript"
    return "material"


def discover(root):
    docs = []
    if not os.path.isdir(str(root)):
        return docs
    seen = set()
    for cur, dirs, files in os.walk(str(root)):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name in SKIP_NAMES or name.startswith("."):
                continue
            full = os.path.join(cur, name)
            sha = sha256_file(full)
            if sha and sha in seen:
                continue
            seen.add(sha)
            got = read_document(full)
            if got is None:
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = len(got["text"].encode("utf-8"))
            docs.append({"doc_id": "D%02d" % (len(docs) + 1),
                         "path": os.path.relpath(full, str(root)).replace("\\", "/"),
                         "role": doc_role(os.path.relpath(full, str(root))),
                         "text": got["text"], "method": got["method"], "note": got["note"],
                         "bytes": size, "sha256": sha})
    return docs


def choose_manuscript(docs):
    best, best_score = None, 0.0
    for d in docs:
        text = d["text"] or ""
        if len(text.strip()) < 40:
            continue
        score = {"manuscript": 4.0, "material": 1.0}.get(d["role"], -5.0)
        if re.search(r"(^|\n)\s*#{1,6}\s|\bAbstract\b|\b摘要\b|\\section\{", text, re.I):
            score += 2.0
        score += min(4.0, len(text) / 600.0)
        if re.search(r"\[\d+(?:[-,]\d+)*\]", text):
            score += 1.5
        if len(re.findall(r"[。.!?]\s", text)) >= 4:
            score += 1.0
        if d["method"] not in ("text", "json"):
            score -= 6.0
        if score > best_score:
            best, best_score = d, score
    return (best, round(best_score, 2)) if best_score >= 3.0 else (None, round(best_score, 2))


# --------------------------------------------------------------- segmentation
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
ABBREV = {"e.g", "i.e", "et al", "fig", "figs", "eq", "eqs", "vs", "etc", "no", "dr",
          "prof", "approx", "ca", "cf", "al", "ref", "refs", "vol", "pp", "p"}
HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
TEX_STRUCT = re.compile(r"^\\(documentclass|usepackage|begin|end|section|subsection|"
                        r"subsubsection|chapter|title|author|maketitle|label|ref|cite|"
                        r"caption|bibliography|bibliographystyle|includegraphics|"
                        r"setmainfont|setCJKmainfont|onehalfspacing|newpage|clearpage)\b")
REF_HEAD = re.compile(r"^\s*(参考文献|references|bibliography|literature cited)\s*[:：]?\s*$", re.I)
REF_ENTRY = re.compile(r"^\s*(?:\[\d+\]|\d+[.)]\s|\[\d+(?:[-,]\d+)*\]\s)")


def _boundary_dot(s, i):
    if i + 1 < len(s) and s[i + 1].isdigit():
        return False
    wm = re.search(r"([A-Za-z][A-Za-z.]*)$", s[:i])
    if wm and wm.group(1).lower().strip(".") in ABBREV:
        return False
    j = i + 1
    while j < len(s) and s[j] in " \t":
        j += 1
    if j >= len(s):
        return True
    return s[j].isupper() or s[j].isdigit() or s[j] in "“\"（(【['"


def split_sentence_spans(s, base):
    spans, start, i, n = [], 0, 0, len(s)
    cjk = bool(_CJK_RE.search(s))
    while i < n:
        ch = s[i]
        end = ch in "。！？!?；" or (ch == "." and _boundary_dot(s, i)) or (ch == ";" and cjk)
        if end:
            seg = s[start:i + 1]
            lead = len(seg) - len(seg.lstrip())
            if seg.strip():
                spans.append((base + start + lead, base + i + 1, seg.strip()))
            start = i + 1
        i += 1
    tail = s[start:]
    if tail.strip():
        lead = len(tail) - len(tail.lstrip())
        spans.append((base + start + lead, base + len(s), tail.strip()))
    return spans


def iter_units(text):
    units, offset, in_fence, in_math, in_refs = [], 0, False, False, False
    for line in text.splitlines(keepends=True):
        start, end = offset, offset + len(line)
        offset = end
        raw = line.rstrip("\r\n")
        stripped = raw.strip()
        if not stripped:
            units.append((start, end, "blank", ""))
            continue
        if stripped.startswith("```"):
            in_fence = not in_fence
            units.append((start, end, "frozen", "code_fence"))
            continue
        if in_fence:
            units.append((start, end, "frozen", "code"))
            continue
        if stripped.startswith("$$"):
            if len(re.findall(r"\$\$", stripped)) < 2:
                in_math = not in_math
            units.append((start, end, "frozen", "math"))
            continue
        if in_math:
            units.append((start, end, "frozen", "math"))
            continue
        if REF_HEAD.match(raw):
            in_refs = True
            units.append((start, end, "heading", stripped))
            continue
        if HEADING_RE.match(stripped) or TEX_STRUCT.match(stripped):
            units.append((start, end, "heading", stripped))
            continue
        if stripped.startswith(("|", "![")) or re.match(r"^[-=]{3,}$", stripped):
            units.append((start, end, "frozen", "table_or_figure"))
            continue
        if in_refs or REF_ENTRY.match(stripped) or stripped.startswith(">"):
            units.append((start, end, "frozen", "reference_or_quote"))
            continue
        lead = len(raw) - len(raw.lstrip())
        for bs, be, sent in split_sentence_spans(raw.strip(), start + lead):
            units.append((bs, be, "sentence", sent))
    return units


def _line_of(text, pos):
    return text.count("\n", 0, max(0, pos)) + 1


def _col_of(text, pos):
    nl = text.rfind("\n", 0, max(0, pos))
    return max(0, pos - (nl + 1)) + 1


def segment(docs):
    segs = []
    for d in docs:
        text = d["text"] or ""
        for s, e, kind, payload in iter_units(text):
            if kind != "sentence":
                continue
            segs.append({"sid": "S%04d" % (len(segs) + 1), "doc_id": d["doc_id"],
                         "path": d["path"], "start": s, "end": e, "text": payload,
                         "locator": "%s:L%d:C%d" % (d["path"], _line_of(text, s), _col_of(text, s))})
    return segs


# ------------------------------------------------------------- protected atoms
_CITE = re.compile(r"\[\s*\d+(?:\s*[-–,，]\s*\d+)*\s*\]")
_TEX_CMD = re.compile(r"\\(cite|citep|citet|ref|eqref|label|autoref|cref|Cref)\*?\{[^{}]*\}")
_MATH = re.compile(r"\$\$[^$]*\$\$|\$[^$\n]+\$|\\\[[^\]]*\\\]|\\\([^)]*\\\)")
_XREF = re.compile(r"(?:图|表|式|章节|第)\s*\d+(?:[.-]\d+)*|"
                   r"\b(?:Fig(?:ure)?|Table|Eq(?:uation)?|Section|Sect\.|Appendix)\s*\.?\s*"
                   r"[0-9]+(?:[.-][0-9]+)*", re.I)
_NUM = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)*(?:\s?%)?(?![0-9])")
_UNIT_ALT = ["m2/g", "m²/g", "wt%", "vol%", "mmol/L", "mg/L", "g/L", "kcal/mol", "kJ/mol",
             "kcal", "kDa", "μg", "ug", "ng", "mg", "kg", "mL", "ml", "μL", "uL", "MPa",
             "kPa", "Pa", "mmol", "μmol", "umol", "mol", "mM", "μM", "uM", "kHz", "MHz",
             "Hz", "keV", "eV", "kV", "mA", "kW", "kJ", "rpm", "nm", "μm", "um", "mm",
             "cm", "km", "ms", "min", "h", "s", "K", "Da", "M", "V", "A", "W", "J", "L",
             "g", "m", "°C", "°F", "%", "‰"]
_UNITS_RE = "|".join(sorted((re.escape(u) for u in _UNIT_ALT), key=len, reverse=True))
_UNIT = re.compile(r"(?<![A-Za-z])(?:" + _UNITS_RE + r")(?![A-Za-z])")
_SP_UNITS = "|".join(sorted((re.escape(u) for u in _UNIT_ALT if not (set("%‰") & set(u))),
                            key=len, reverse=True))
_UNIT_EN_RE = re.compile(r"(\d+(?:\.\d+)?)[ \t]?(" + _SP_UNITS + r")(?![A-Za-z0-9/])")
_UNIT_ZH_RE = re.compile(r"(\d+(?:\.\d+)?)[ \t]?(" + _SP_UNITS + r")(?=[一-鿿，。；：、）)\s]|$)")
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_URL = re.compile(r"https?://[^\s)>\]]+")


def protected_atoms(text):
    text = text or ""
    return {"citation": [m.group(0) for m in _CITE.finditer(text)],
            "tex_ref": [m.group(0) for m in _TEX_CMD.finditer(text)],
            "xref": [m.group(0) for m in _XREF.finditer(text)],
            "math": [m.group(0) for m in _MATH.finditer(text)],
            "number": [m.group(0) for m in _NUM.finditer(text)],
            "unit": [m.group(0) for m in _UNIT.finditer(text)],
            "doi_url": [m.group(0) for m in _DOI.finditer(text)] +
                       [m.group(0) for m in _URL.finditer(text)]}


def protected_intervals(text):
    out = []
    for pat in (_CITE, _TEX_CMD, _MATH, _XREF, _DOI, _URL):
        for m in pat.finditer(text or ""):
            out.append((m.start(), m.end()))
    return out


_SUPC = str.maketrans("²³", "23")


def _atom_norm(x):
    return re.sub(r"\s+", "", x).translate(_SUPC)


def atoms_hold(before, after):
    a, b = protected_atoms(before), protected_atoms(after)
    bad = {}
    for k in a:
        ca = Counter(_atom_norm(x) for x in a[k])
        cb = Counter(_atom_norm(x) for x in b[k])
        if ca != cb:
            bad[k] = {"before": dict(ca), "after": dict(cb)}
    return (not bad), bad


_WEAK = re.compile(r"\b(may|might|could|possibly|perhaps|likely|unlikely|suggest[s]?|"
                   r"indicat(?:e|es|ed|ing)|appear[s]?|seem[s]?|approximately|about|"
                   r"tend[s]?)\b", re.I)
_STRONG = re.compile(r"\b(prove[sd]?|prov(?:e|ing)|establish(?:es|ed)?|confirm(?:s|ed)?|"
                     r"demonstrate[sd]?|determine[sd]?|caus(?:e|es|ed|ing)|leads? to|"
                     r"guarantee[sd]?|always|never|clearly|significant(?:ly)?|must)\b", re.I)


def hedge_profile(text):
    text = text or ""
    return {"weak": len(_WEAK.findall(text)), "strong": len(_STRONG.findall(text))}


def hedge_preserved(before, after):
    a, b = hedge_profile(before), hedge_profile(after)
    reasons = []
    if b["strong"] > a["strong"]:
        reasons.append("strong modal or absolute claim added (%d -> %d)" % (a["strong"], b["strong"]))
    if a["weak"] > 0 and b["weak"] < a["weak"]:
        reasons.append("weak qualifier removed (%d -> %d)" % (a["weak"], b["weak"]))
    return (not reasons), reasons


def _overlaps(a, b, spans):
    return any(not (b <= s or a >= e) for s, e in spans)


def _sub_rule(text, rule):
    spans = protected_intervals(text)
    hits = []

    def repl(m):
        if _overlaps(m.start(), m.end(), spans):
            return m.group(0)
        new = rule["repl"](m) if callable(rule.get("repl")) else m.expand(rule["repl"])
        if new == m.group(0):
            return new
        hits.append({"rule": rule["id"], "type": rule["type"], "before": m.group(0),
                     "after": new, "reason": rule["reason"]})
        return new

    return rule["pattern"].sub(repl, text), hits


def _an(m):
    low = m.group(2).lower()
    vowel_exc = {"uniform", "universal", "user", "unique", "unit", "university", "useful",
                 "usual", "european", "one", "once", "uk", "us", "unesco", "utility"}
    as_vowel = {"hour", "honest", "honor", "honour", "mri", "rna", "sem", "xrd", "fbi",
                "nlp", "llm", "html", "https"}
    return "a" if low in vowel_exc else "an" if (low in as_vowel or low[:1] in "aeiou") else "a"


RULES = [
    {"id": "E01", "type": "punctuation", "lang": "en", "applied": True,
     "pattern": re.compile(r"[ \t]{2,}"), "repl": " ",
     "reason": "single space between words"},
    {"id": "E02", "type": "punctuation", "lang": "en", "applied": True,
     "pattern": re.compile(r"[ \t]+([,;:.!?)\]])"), "repl": r"\1",
     "reason": "no space before punctuation"},
    {"id": "E03", "type": "punctuation", "lang": "en", "applied": True,
     "pattern": re.compile(r",(?=[A-Za-z])"), "repl": ", ",
     "reason": "space after comma"},
    {"id": "E04", "type": "punctuation", "lang": "en", "applied": True,
     "pattern": re.compile(r"\.(?=[A-Z][a-z])"), "repl": ". ",
     "reason": "space after sentence period"},
    {"id": "E05", "type": "abbreviation", "lang": "en", "applied": True,
     "pattern": re.compile(r"\b(et al|i\.e|e\.g)(?![.\w])"), "repl": r"\1.",
     "reason": "Latin abbreviation needs a final period"},
    {"id": "E06", "type": "spelling", "lang": "en", "applied": True,
     "pattern": re.compile(r"\b(recieve|recieved|occured|seperate|accomodate|dependant|"
                           r"thier|wich|teh|alot|reseach|analys|enviroment|goverment|"
                           r"succesful|untill)\b", re.I),
     "repl": lambda m: {"recieve": "receive", "recieved": "received", "occured": "occurred",
                        "seperate": "separate", "accomodate": "accommodate",
                        "dependant": "dependent", "thier": "their", "wich": "which",
                        "teh": "the", "alot": "a lot", "reseach": "research",
                        "analys": "analysis", "enviroment": "environment",
                        "goverment": "government", "succesful": "successful",
                        "untill": "until"}.get(m.group(1).lower(), m.group(1)),
     "reason": "common misspelling"},
    {"id": "E07", "type": "article", "lang": "en", "applied": True,
     "pattern": re.compile(r"\b(a|an)(?=[ \t]+([A-Za-z][A-Za-z-]*))"), "repl": _an,
     "reason": "article agrees with the following vowel sound"},
    {"id": "E08", "type": "agreement", "lang": "en", "applied": True,
     "pattern": re.compile(r"\b(results|data|studies|findings|values|measurements|"
                           r"analyses|experiments)\s+(shows|indicates|suggests|"
                           r"demonstrates|reveals|confirms)\b", re.I),
     "repl": lambda m: m.group(1) + " " + {"shows": "show", "indicates": "indicate",
                                           "suggests": "suggest", "demonstrates": "demonstrate",
                                           "reveals": "reveal", "confirms": "confirm"}[m.group(2).lower()],
     "reason": "plural subject needs a plural verb"},
    {"id": "E09", "type": "agreement", "lang": "en", "applied": True,
     "pattern": re.compile(r"\b(this|that)\s+(suggest|indicate|show|demonstrate|reveal|confirm)\b", re.I),
     "repl": lambda m: m.group(1) + " " + m.group(2) + "s",
     "reason": "singular subject needs a singular verb"},
    {"id": "E10", "type": "unit", "lang": "en", "applied": True,
     "pattern": _UNIT_EN_RE, "repl": r"\1 \2",
     "reason": "space between numeral and unit"},
    {"id": "U01", "type": "unit_format", "lang": "any", "applied": True,
     "pattern": re.compile(r"(?<![A-Za-z0-9])(m2|m3|cm2|cm3|mm2|mm3)(?![A-Za-z0-9])"),
     "repl": lambda m: {"m2": "m²", "m3": "m³", "cm2": "cm²", "cm3": "cm³",
                        "mm2": "mm²", "mm3": "mm³"}[m.group(1)],
     "reason": "area and volume units use superscript exponents"},
    {"id": "Z01", "type": "punctuation", "lang": "zh", "applied": True,
     "pattern": re.compile(r"(?<=[\u4e00-\u9fff])[,;:?!](?=[\u4e00-\u9fff\s）)])"),
     "repl": lambda m: {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}[m.group(0)],
     "reason": "use full-width punctuation"},
    {"id": "Z02", "type": "punctuation", "lang": "zh", "applied": True,
     "pattern": re.compile(r"([，。；：！？、])\1+"), "repl": r"\1",
     "reason": "duplicate punctuation"},
    {"id": "Z03", "type": "punctuation", "lang": "zh", "applied": True,
     "pattern": re.compile(r"[ \t]+([，。；：！？、])"), "repl": r"\1",
     "reason": "no space before Chinese punctuation"},
    {"id": "Z04", "type": "unit", "lang": "zh", "applied": True,
     "pattern": _UNIT_ZH_RE, "repl": r"\1 \2",
     "reason": "space between numeral and unit"},
    {"id": "Z05", "type": "redundancy", "lang": "zh", "applied": True,
     "pattern": re.compile(r"([的了])\1+"), "repl": r"\1",
     "reason": "duplicate function word"},
]

SUGGEST_RULES = [
    {"id": "S01", "type": "register", "lang": "en",
     "pattern": re.compile(r"\b(a lot of|lots of|pretty|really|totally|huge|obviously|"
                           r"clearly|of course)\b", re.I),
     "repl": lambda m: {"a lot of": "many", "lots of": "many", "pretty": "relatively",
                        "really": "considerably", "totally": "completely",
                        "huge": "substantial", "obviously": "evidently",
                        "clearly": "evidently", "of course": "as expected"}.get(
                            m.group(0).lower(), m.group(0)),
     "reason": "colloquial wording; propose a neutral academic term"},
    {"id": "S02", "type": "overclaim", "lang": "en",
     "pattern": re.compile(r"\b(proves?|proven|causes?|caused|determines?|guarantees?)\b", re.I),
     "repl": lambda m: {"prove": "support", "proves": "supports", "proven": "supported",
                        "cause": "be associated with", "causes": "is associated with",
                        "caused": "was associated with", "determine": "relate to",
                        "determines": "relates to", "guarantee": "ensure",
                        "guarantees": "ensures"}.get(m.group(0).lower(), m.group(0)),
     "reason": "possible overclaim; propose a softer verb"},
    {"id": "S03", "type": "wordiness", "lang": "en",
     "pattern": re.compile(r"\b(in order to|due to the fact that|it is important to note that)\b", re.I),
     "repl": lambda m: {"in order to": "to", "due to the fact that": "because",
                        "it is important to note that": ""}.get(m.group(0).lower(), m.group(0)),
     "reason": "redundant academic filler"},
    {"id": "S04", "type": "nominalization", "lang": "zh",
     "pattern": re.compile(r"(?:进行了|开展了)([^，。；]{1,12}?)的(分析|研究|测量|评估|讨论)"),
     "repl": lambda m: {"分析": "分析了", "研究": "研究了", "测量": "测量了",
                        "评估": "评估了", "讨论": "讨论了"}[m.group(2)] + m.group(1),
     "reason": "heavy nominalisation; propose a verb phrase"},
    {"id": "S05", "type": "redundancy", "lang": "zh",
     "pattern": re.compile(r"由于([^，。；]{1,20})的原因"), "repl": r"由于\1",
     "reason": "由于 already marks the cause"},
    {"id": "S06", "type": "wordiness", "lang": "zh",
     "pattern": re.compile(r"通过([^，。；]{1,20})的方法"), "repl": r"通过\1",
     "reason": "通过 already marks the method"},
]


def _rule_applies(rule, sentence):
    lang = rule.get("lang")
    if lang in ("en", "zh"):
        cjk = len(_CJK_RE.findall(sentence)) > 3
        return (lang == "en") != cjk
    return True


def apply_rules(sentence):
    text, hits = sentence, []
    for rule in RULES:
        if not _rule_applies(rule, sentence):
            continue
        text, got = _sub_rule(text, rule)
        hits.extend(got)
    ok, bad = atoms_hold(sentence, text)
    return (text, hits, True, {}) if ok else (sentence, hits, False, bad)


def suggest_rules(sentence):
    out = []
    for rule in SUGGEST_RULES:
        if not _rule_applies(rule, sentence):
            continue
        out.extend(_sub_rule(sentence, rule)[1])
    return out


# ------------------------------------------------------------------- glossary
SEED_TERMS = [  # (id, zh, en, abbr, variants)
    ("T01", "催化剂", "catalyst", "", ["催化劑", "触媒"]),
    ("T02", "转化率", "conversion", "", ["转化比率", "转换率"]),
    ("T03", "温度", "temperature", "", []),
    ("T04", "反应压力", "reaction pressure", "", []),
    ("T05", "载气流速", "carrier gas flow rate", "", ["载气流量"]),
    ("T06", "比表面积", "specific surface area", "SSA", []),
    ("T07", "统计显著性", "statistical significance", "", []),
    ("T08", "样品", "sample", "", ["试样"]),
    ("T09", "选择性", "selectivity", "", []),
    ("T10", "产率", "yield", "", ["收率"]),
    ("T11", "反应时间", "reaction time", "", []),
    ("T12", "机理", "mechanism", "", ["机制"]),
    ("T13", "动力学", "kinetics", "", []),
    ("T14", "纳米颗粒", "nanoparticle", "", ["纳米粒子", "nano-particle"]),
    ("T15", "透射电子显微镜", "transmission electron microscopy", "TEM", []),
    ("T16", "扫描电子显微镜", "scanning electron microscopy", "SEM", []),
    ("T17", "X射线衍射", "X-ray diffraction", "XRD", ["XRD"]),
    ("T18", "信噪比", "signal-to-noise ratio", "SNR", []),
]


def parse_glossary_docs(docs):
    terms = []
    for d in docs:
        if d["role"] != "glossary":
            continue
        text = d["text"] or ""
        try:
            obj = json.loads(text)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            obj = obj.get("terms")
        if isinstance(obj, list):
            for i, t in enumerate(obj):
                if isinstance(t, dict):
                    terms.append({"id": t.get("id") or "G%02d" % (i + 1),
                                  "zh": t.get("zh") or t.get("term") or "",
                                  "en": t.get("en") or t.get("term") or "",
                                  "abbr": t.get("abbr") or "",
                                  "variants": t.get("variants") or [], "source": d["path"]})
            continue
        for line in text.splitlines():
            parts = [p.strip() for p in re.split(r"[,\t，]", line) if p.strip()]
            if len(parts) >= 2 and parts[0].lower() not in ("term", "概念", "术语"):
                terms.append({"id": "G%02d" % (len(terms) + 1), "zh": parts[0], "en": parts[1],
                              "abbr": parts[2] if len(parts) > 2 else "",
                              "variants": parts[3].split("|") if len(parts) > 3 else [],
                              "source": d["path"]})
    return terms


def _term_forms(t):
    forms = []
    for kind, val in (("zh", t.get("zh")), ("en", t.get("en")), ("abbr", t.get("abbr"))):
        if val:
            forms.append((kind, val))
    forms.extend(("variant", v) for v in (t.get("variants") or []) if v)
    return forms


def scan_glossary(segs, extra_terms):
    out = []
    pool = list(extra_terms) + [{"id": i, "zh": z, "en": e, "abbr": a, "variants": v,
                                 "source": "builtin_seed"}
                                for i, z, e, a, v in SEED_TERMS]
    for t in pool:
        found = []
        for kind, form in _term_forms(t):
            if kind == "en" and re.search(r"[A-Za-z]", form):
                pat = re.compile(r"(?<![A-Za-z])" + re.escape(form) + r"(?![A-Za-z])", re.I)
            else:
                pat = re.compile(re.escape(form))
            hits = []
            for s in segs:
                for m in pat.finditer(s["text"]):
                    hits.append({"form": form, "kind": kind, "sid": s["sid"],
                                 "locator": s["locator"], "offset": s["start"] + m.start()})
            if hits:
                found.append({"form": form, "kind": kind, "count": len(hits), "first": hits[0]})
        if not found:
            continue
        kinds = {f["kind"] for f in found}
        variants_used = [f["form"] for f in found if f["kind"] == "variant"]
        canonical = t.get("zh") or t.get("en") or t.get("abbr") or ""
        status = "variant_used" if variants_used else ("bilingual_pair"
                                                       if len(kinds & {"zh", "en"}) > 1 else "consistent")
        first = min((f["first"] for f in found), key=lambda h: h["offset"])
        out.append({"id": t["id"], "concept": canonical, "zh": t.get("zh", ""),
                    "en": t.get("en", ""), "abbr": t.get("abbr", ""), "canonical": canonical,
                    "forms_found": found, "variants_used": variants_used,
                    "count": sum(f["count"] for f in found), "status": status,
                    "first_use": first["locator"], "source": t.get("source", "builtin_seed")})
    return out


def abbreviation_issues(segs, text):
    issues, seen = [], set()
    for m in re.finditer(r"(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])", text or ""):
        tok = m.group(0)
        if tok in seen or tok in {"OK", "USA", "UK", "EU", "AI", "PC"}:
            continue
        seen.add(tok)
        defined = re.search(r"\(\s*" + re.escape(tok) + r"\s*\)", text[:m.start()]) or \
            re.search(re.escape(tok) + r"\s*\(", text[:m.start()])
        if not defined:
            seg = next((s for s in segs if s["start"] <= m.start() < s["end"]), None)
            issues.append({"abbreviation": tok, "locator": seg["locator"] if seg else "document",
                           "detail": "first use of the abbreviation is not preceded by a full-form "
                                     "definition in the supplied text"})
    return issues[:20]


def language_profile(text):
    cjk = len(_CJK_RE.findall(text or ""))
    latin = len(re.findall(r"[A-Za-z]+", text or ""))
    if cjk == 0 and latin == 0:
        return "unknown", 0.0
    ratio = cjk / float(cjk + latin)
    return ("zh" if ratio >= 0.2 else "en"), round(ratio, 3)
