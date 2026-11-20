"""engine.py -- discovery, normalisation and deterministic verdict rules (stdlib only, no network).

units with locators -> atomic sub-claims -> lexical/numeric retrieval -> verdict (R0..R6).
A verdict never claims entailment: it says "this sentence, at this locator, shares these
terms/values and points this way". Anything weaker stays insufficient_evidence.
"""
import io
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

VERDICTS = ("supported", "partially_supported", "contradicted", "insufficient_evidence")
AGG_RULE = ("all supported->supported; all contradicted->contradicted; all insufficient->insufficient; "
            "contradicted+supported/partial->partial; supported+insufficient->partial; else partial; "
            "unresolved cross-source conflict -> partially_supported, low confidence")
REQ = {"comparison": "both comparators and the direction (or both values) in one passage",
       "causal": "cause and effect stated, not only co-occurrence",
       "scope": "the population/condition/range the claim is limited to",
       "fact": "the same entity and value"}
CLAIM_FILES = ("claims-to-verify.json", "claims_to_verify.json", "claims.json")
CLAIM_KEYS = ("claims", "claims_to_verify", "claims_to_check", "statements", "claim_list", "audit_claims",
              "assertions", "items")
ID_KEYS = ("claim_id", "cid", "id", "claim_no", "no")
TEXT_KEYS = ("claim_text", "text", "statement", "claim", "sentence", "content", "question", "assertion")
HINT_KEYS = ("source_hint", "paper_id", "source_id", "source", "citation", "cited_paper", "document")
SKIP = ("case.json", "task.md", "readme.md", "instructions.md", "skill.md")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg")
NUM_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?\s*(?:%|wt\.?\s*%|at\.?\s*%|°\s*C|℃|K|MPa|GPa|kPa|Pa|h|hr|"
                    r"min|s|nm|μm|um|mm|cm|mL|L|mg|g|kg|mM|μM|nM|M|Hz|kHz|MHz|GHz|eV|keV|MeV|dB|rpm|cycles?|"
                    r"vol\.?\s*%|mol\.?\s*%|次|倍|小时|分钟|秒|天|年|周|个月)?", re.I)
CJK = re.compile(r"[\u3400-\u9fff]")
CJK_STOP = set("的了是在和与及或对为以这那其之而并且但我们他们可以一个中上下也有会被把从到")
STOP = set("""the and for with that this from were was are has have had not but which their there these those than
then into such also more can may our its been between after before while using used show did""".split())
CONJ = re.compile(r"(?:;|；|\s+and\s+|\s+but\s+|\s+whereas\s+|\s+while\s+|，|、|并且|而且|同时|但是|然而)", re.I)


def _lex(spec):
    """'a|b/c|d' -> predicate(text): ascii word-boundary list / CJK substring list."""
    a, c = spec.split("/")
    rx = re.compile(r"\b(?:%s)" % "|".join(re.escape(w) for w in a.split("|") if w), re.I) if a.strip() else None
    cw = tuple(w for w in c.split("|") if w)
    return lambda t: bool(rx and rx.search(t)) or any(w in t for w in cw)


UP = _lex("higher|increase|increased|greater|above|exceed|improve|enhance|promote|elevated|superior"
          "/高于|提高|增加|升高|上升|增强|促进|优于|提升")
DOWN = _lex("lower|decrease|decreased|below|reduce|reduced|inhibit|suppress|inferior|less than|decline"
            "/低于|减少|降低|下降|抑制|削弱|劣于|减小")
NULL = _lex("no significant|not significant|no difference|did not differ|no effect|unchanged|failed to|no evidence"
            "/无显著|无差异|未见显著|没有变化|无变化|未观察到|不支持")
NEG = _lex("not|no|never|without|failed|absence|neither|nor|none/未|不|没有|无|并非|不能|缺乏")
COMP = _lex("than|versus|vs|compared|higher|lower|greater|less|more/高于|低于|相比|较|优于|劣于|倍|差异")
CAUSAL = _lex("because|due to|leads to|led to|results in|caused|therefore|thus"
              "/导致|因为|由于|因此|从而|使得|引起|归因于|造成")
SCOPE = _lex("only|all|under|within|in the range|in vitro|in vivo|in mice|in humans"
             "/所有|仅|只有|条件下|范围内|限于|均|全部|体外|体内")


_TBL = str.maketrans({" ": " ", "　": " ", "­": "", "​": "", "‘": "'", "’": "'",
                      "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "ﬁ": "fi",
                      "ﬂ": "fl"})


def norm(s, squash=False):
    """NFKC + glyph folding; squash=True drops whitespace (CJK-safe containment)."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s).translate(_TBL)
    return re.sub(r"\s+", "" if squash else " ", s).strip()


def soft(s):
    if not isinstance(s, str):
        return ""
    return re.sub(r"[ \t]+", " ", s.replace("\u00a0", " ").replace("\u3000", " ").replace("\u200b", "")).strip()


def read_text(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def load_json(path):
    try:
        return json.loads(read_text(path)), None
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def split_sentences(text):
    text = soft(text)
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?；;])\s*|(?<=[.])\s+(?=[A-Z0-9(\[])|(?<=\.)\s*$|\n+", text)
    return [p.strip() for p in parts if p and p.strip()] or [text]


def tokens(text):
    low = norm(text).lower()
    out = set(re.findall(r"[a-z][a-z0-9\-]{2,}", low))
    cj = "".join(CJK.findall(low))
    for i in range(len(cj) - 1):
        bg = cj[i:i + 2]
        if not (bg[0] in CJK_STOP and bg[1] in CJK_STOP):
            out.add(bg)
    return out


def numbers(text):
    out = []
    for m in NUM_RE.finditer(norm(text)):
        v = re.sub(r"\s+", " ", m.group(0).strip())
        if re.search(r"\d", v) and len(v) <= 24 and v.lower() not in [x.lower() for x in out]:
            out.append(v)
    return out


def num_in(text, core):
    """Token-bounded numeric match: '1' must not match '120'."""
    return re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(str(core)), text) is not None


def num_core(a):
    d = "".join(ch for ch in str(a) if ch.isdigit() or ch == ".")
    return d.strip(".") or norm(a).lower()


def profile(text):
    low = norm(text).lower()
    up, down = bool(UP(low)), bool(DOWN(low))
    rel = 1 if (up and not down) else (-1 if (down and not up) else 0)
    typ = "comparison" if (COMP(low) or rel) else ("causal" if CAUSAL(low) else
                                                   ("scope" if SCOPE(low) else "fact"))
    return {"text": soft(text), "keys": {t for t in tokens(text) if t not in STOP}, "nums": numbers(text),
            "rel": rel, "null": bool(NULL(low)), "neg": bool(NEG(low)), "type": typ}


def find_input(explicit=None):
    for c in ([explicit] if explicit else []) + ["/input", "/app/input", "input"]:
        if c and Path(c).expanduser().is_dir():
            return Path(c).expanduser().resolve()
    return Path(explicit or "/input").expanduser().resolve()


def load_case(inp):
    for p in [inp / n for n in ("case.json", "case_info.json")] + sorted(inp.glob("case*.json")):
        if p.is_file():
            obj, err = load_json(p)
            return (obj, str(p), None) if isinstance(obj, dict) else ({}, str(p), err or "case.json not an object")
    return {}, None, None


def case_id_of(case, path, inp):
    for h in [case] + [case[k] for k in ("input", "meta", "metadata") if isinstance(case.get(k), dict)]:
        for k in ("case_id", "caseId", "id", "uid", "name"):
            if isinstance(h.get(k), (str, int)) and str(h[k]).strip():
                return str(h[k]).strip()
    return (Path(path).stem if path and Path(path).stem != "case" else inp.name) or "unknown-case"


def _claim_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in CLAIM_KEYS:
            v = obj.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for k2 in CLAIM_KEYS:
                    if isinstance(v.get(k2), list):
                        return v[k2]
        for k in ("input", "payload"):
            if isinstance(obj.get(k), dict) and _claim_list(obj[k]):
                return _claim_list(obj[k])
    return []


def normalize_claims(raw):
    out = []
    for item in raw:
        item = {"text": item} if isinstance(item, str) else item
        if not isinstance(item, dict):
            continue
        cid = next((str(item[k]).strip() for k in ID_KEYS if item.get(k) not in (None, "")), None)
        text = next((item[k].strip() for k in TEXT_KEYS if isinstance(item.get(k), str) and item[k].strip()), None)
        hint = next((item[k] for k in HINT_KEYS if item.get(k) not in (None, "", [])), None)
        if text and len(norm(text)) >= 3:
            out.append({"claim_id": cid or "C%d" % (len(out) + 1), "claim_text": soft(text),
                        "source_hint": hint if isinstance(hint, str) or hint is None else str(hint)})
    return out


def load_claims(inp, case):
    notes = []
    for name in CLAIM_FILES:
        p = inp / name
        if not p.is_file():
            continue
        obj, err = load_json(p)
        if err:
            notes.append({"stage": "claims", "issue": "claims_json_parse_error", "detail": err})
            continue
        claims = normalize_claims(_claim_list(obj))
        if claims:
            return claims, str(p), notes
    if isinstance(case, dict) and _claim_list(case):
        return normalize_claims(_claim_list(case)), "case.json", notes
    for p in sorted(inp.rglob("*.json")):                 # last resort scan
        if p.name.lower() in SKIP or p.name.lower().startswith("case"):
            continue
        obj, err = load_json(p)
        claims = [] if err else normalize_claims(_claim_list(obj))
        if claims:
            notes.append({"stage": "claims", "issue": "claims_found_by_scan", "detail": p.name})
            return claims, str(p), notes
    return [], None, notes


def _para_split(text):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if norm(b)]
    return blocks if len(blocks) > 1 else [b for b in split_sentences(text) if norm(b)]


def _md_blocks(text):
    out, sec = [], None
    for c in (x.strip() for x in re.split(r"\n\s*\n", text)):
        if not c:
            continue
        lines = c.splitlines()
        m = re.match(r"#{1,6}\s*(.+)", lines[0])
        if m:
            sec = soft(m.group(1))[:80]
            rest = "\n".join(lines[1:]).strip()
            if rest:
                out.append({"text": rest, "section": sec})
        else:
            out.append({"text": c, "section": sec})
    return out


def _pdf_pages(path):
    """pypdf, then pdftotext; without either reader the PDF is reported as having no text layer."""
    raw = Path(path).read_bytes()
    try:
        import pypdf
        pages = [(pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(raw)).pages]
        if sum(len(norm(p)) for p in pages) > 40:
            return pages, "pypdf"
    except Exception:
        pass
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-layout", str(path), "-"], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, timeout=120).stdout.decode("utf-8", "replace")
            if len(norm(out)) > 40:
                return out.split("\f"), "pdftotext"
        except Exception:
            pass
    return [], "no_text_layer"


def _pdf_blocks(pages):
    return [{"text": soft(p), "page": n} for n, txt in enumerate(pages, 1)
            for p in _para_split(txt) if norm(p)]


def _json_blocks(obj):
    out = []

    def walk(o, sec=None):
        if isinstance(o, dict):
            kids = [k for k in ("paragraphs", "sections", "passages", "blocks", "abstract", "body")
                    if isinstance(o.get(k), (list, dict))]
            for k in kids:
                walk(o[k], o.get("section") or sec)
            text = next((o[k] for k in ("text", "content", "paragraph")
                         if isinstance(o.get(k), str) and o[k].strip()), "")
            if not kids and text:
                out.append({"text": text, "section": o.get("section") or sec,
                            "page": o.get("page") or o.get("p")})
        elif isinstance(o, list):
            for x in o[:600]:
                walk(x, sec) if isinstance(x, (dict, list)) else out.append({"text": x, "section": sec})
        elif isinstance(o, str):
            out.append({"text": o, "section": sec})

    walk(obj)
    return [b for b in out if norm(b.get("text"))]


def load_source(path):
    path, suf = Path(path), Path(path).suffix.lower()
    try:
        if suf == ".pdf":
            pages, how = _pdf_pages(path)
            return _pdf_blocks(pages), "pdf", how
        if suf in (".json", ".jsonl"):
            obj, err = load_json(path)
            return ([], "json", "parse_error") if err else (_json_blocks(obj), "json", "json_paragraphs")
        if suf in (".csv", ".tsv"):
            return [{"text": r.strip()} for r in read_text(path).splitlines() if norm(r)], "csv", "row_per_line"
        text = read_text(path)
        if suf in (".md", ".markdown"):
            return _md_blocks(text), "md", "heading_blocks"
        return [{"text": p} for p in _para_split(text)], "txt", "block_split"
    except Exception as exc:
        return [], (suf.lstrip(".") or "txt"), "extract_error:%s" % type(exc).__name__


def build_index(inp, skip=()):
    skip = {str(Path(p).resolve()) for p in skip if p}
    paths, gaps, sources, units, degr = [], [], [], [], []
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or str(p.resolve()) in skip:
            continue
        low = p.name.lower()
        if low in SKIP or low.startswith("claims-to") or low.startswith("claims_to"):
            continue
        if p.suffix.lower() in IMG_EXT:
            gaps.append({"path": str(p), "issue": "image_not_parsed", "detail": "caption text required"})
        elif p.stat().st_size > 12 * 1024 * 1024:
            gaps.append({"path": str(p), "issue": "file_too_large", "detail": ">12MB"})
        elif p.suffix.lower() not in (".pyc", ".pyo", ".zip", ".so"):
            paths.append(p)
    for i, p in enumerate(paths):
        blocks, fmt, note = load_source(p)
        sid = "S%d" % (i + 1)
        if not blocks:
            gaps.append({"path": str(p), "issue": "no_text_extracted", "format": fmt, "detail": note})
            degr.append({"stage": "material", "issue": "material_unreadable", "detail": "%s (%s)" % (p.name, note)})
            sources.append({"source_id": sid, "path": str(p), "file": p.name, "format": fmt, "units": 0,
                            "extraction": note, "chars": 0, "readable": False})
            continue
        before = len(units)
        for j, b in enumerate(blocks, 1):
            text = soft(b.get("text") or "")
            if len(norm(text)) < 8:
                continue
            page = b.get("page")
            ordinal = page if isinstance(page, int) and page > 0 else j
            units.append({"unit_id": "U%d" % (len(units) + 1), "source_id": sid, "file": p.name,
                          "locator": "%s#p%d" % (p.name, ordinal), "page": page, "section": b.get("section"),
                          "text": text,
                          "tokens": tokens(text), "sentences": split_sentences(text)})
        sources.append({"source_id": sid, "path": str(p), "file": p.name, "format": fmt,
                        "units": len(units) - before, "extraction": note,
                        "chars": sum(len(u["text"]) for u in units[before:]), "readable": True})
    return {"sources": sources, "units": units, "gaps": gaps, "degradations": degr}


def split_subs(text, limit=5):
    out = []
    for s in (soft(x) for x in split_sentences(text)):
        if not s:
            continue
        segs = [x.strip(" ,，、;；") for x in CONJ.split(s)]
        segs = [x for x in segs if len(norm(x)) >= 14]
        if 2 <= len(segs) <= 4 and sum(len(norm(x)) for x in segs) >= 0.6 * len(norm(s)):
            out.extend(segs)
        else:
            out.append(s)
    if len(out) > limit:
        out = out[: limit - 1] + [" ".join(out[limit - 1:])]
    return out or [soft(text)]


def pick_quote(unit, p):
    """Highest-scoring complete sentence verbatim, else a contiguous window of the unit."""
    keys, cores = p["keys"], [num_core(n) for n in p["nums"]]
    best, best_score = "", -1
    for s in unit["sentences"]:
        low, n = norm(s).lower(), len(norm(s))
        sc = len(keys & tokens(s)) + 2 * sum(num_in(low, x) for x in cores)
        if 12 <= n <= 300 and sc > best_score:
            best, best_score = s, sc
    if best:
        return soft(best)
    text = norm(unit["text"])
    if len(text) <= 300:
        return soft(text) if len(text) >= 12 else ""
    for probe in sorted(keys)[:6] + cores:
        idx = text.lower().find(str(probe).lower())
        if idx >= 0:
            return soft(text[max(0, idx - 60): max(0, idx - 60) + 280])
    return soft(text[:280])


def candidates(p, units, k=3, hint=None, qlog=None):
    ct, cores, scored = p["keys"], [num_core(n) for n in p["nums"]], []
    for u in units:
        cov = len(ct & u["tokens"]) / float(len(ct)) if ct else 0.0
        matched = [n for n in cores if num_in(norm(u["text"]).lower(), n)]
        numcov = len(matched) / float(len(cores)) if cores else 0.0
        score = (0.72 * cov + 0.28 * numcov) if cores else cov
        if hint and hint.lower() in (u["file"] + " " + u["source_id"]).lower():
            score += 0.15
        quote = pick_quote(u, p) if score > 0.02 else ""
        if not quote:
            continue
        qp = profile(quote)
        scored.append(dict(unit=u, score=round(min(score, 1.0), 3), cov=round(cov, 3), numcov=round(numcov, 3),
                           matched_nums=matched, quote=quote, rel=qp["rel"], null=qp["null"], neg=qp["neg"]))
    order = {u["unit_id"]: i for i, u in enumerate(units)}
    scored.sort(key=lambda x: (-x["score"], order.get(x["unit"]["unit_id"], 0), x["unit"]["unit_id"]))
    if qlog is not None:
        qlog.append({"units_scanned": len(units), "query_terms": sorted(ct)[:12],
                     "top": [[x["unit"]["unit_id"], x["score"]] for x in scored[:k]]})
    return scored[:k]


def verify_quote(quote, unit, full_text=""):
    q = norm(quote)
    if not q or len(q) < 6:
        return {"verified": False, "where": "empty_or_short", "ratio": 0.0}
    if unit is not None:
        t = norm(unit["text"])
        if q in t or norm(q, True) in norm(t, True):
            return {"verified": True, "where": "cited_unit", "ratio": 1.0}
    if full_text and q in norm(full_text):
        return {"verified": True, "where": "same_source_elsewhere", "ratio": 1.0}
    return {"verified": False, "where": "not_found", "ratio": 0.0}


def value_dir(p, quote):
    """'A higher than B' with two anchors: compare the value attached to each anchor in the quote."""
    if len(p["nums"]) < 2 or not p["rel"]:
        return None
    q, vals, cores = norm(quote).lower(), [], [num_core(n) for n in p["nums"][:2]]
    for a in cores:
        m = re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(a), q)
        vm = re.search(r"\d+(?:\.\d+)?", q[m.end():m.end() + 60]) if m else None
        if not vm or num_core(vm.group(0)) in cores:
            return None
        vals.append(float(vm.group(0)))
    if vals[0] == vals[1]:
        return None
    return "support" if (vals[0] > vals[1]) == (p["rel"] > 0) else "contradict"


def judge(p, cands, n_units):
    """R0..R6 decision table; returns the verdict and the passages that drove it."""
    def ev(c, role, supports):
        u = c["unit"]
        return {"source_id": u["source_id"], "unit_id": u["unit_id"], "locator": u["locator"],
                "quote": c["quote"], "score": c["score"], "numbers_matched": c["matched_nums"],
                "direction": c["rel"], "supports": supports,
                "role": role, "verified": True}

    scope = {"units_scanned": n_units, "queries": sorted(p["keys"])[:12], "numbers": p["nums"]}
    b = cands[0] if cands else None
    direct = bool(b and p["rel"] and b["rel"] == -p["rel"] and b["cov"] >= 0.30)
    counter = next((c for c in cands[1:] if p["rel"] and c["rel"] == -p["rel"] and c["cov"] >= 0.30), None)
    vdir = value_dir(p, b["quote"]) if b else None
    evs, lims = [], []
    if not cands:
        v, conf, rule, lims = "insufficient_evidence", "low", "R0", ["no_lexical_candidate"]
        rat = "no passage shares a key term or anchor value"
    elif b["cov"] < 0.14 and b["numcov"] == 0:
        v, conf, rule, lims = "insufficient_evidence", "low", "R0", ["overlap_below_threshold"]
        rat = "best candidate is topic-adjacent only (coverage %.2f)" % b["cov"]
    else:
        evs = [ev(b, "minimal_sufficient", True)]
        if direct or vdir == "contradict":
            evs = [ev(b, "counter", False)]
            v, rule, lims = "contradicted", "R1", ["direction_opposite"]
            conf = "high" if (vdir or b["cov"] >= 0.55) else "medium"
            rat = "the passage orders the comparison the other way"
        elif vdir == "support":
            v, conf, rule, lims = "supported", "high", "R4", []
            rat = "the values attached to both comparators are ordered as the claim states"
        elif counter:
            evs.append(ev(counter, "counter", False))
            v, rule, lims = "contradicted", "R1", ["direction_opposite"]
            conf = "high" if counter["cov"] >= 0.55 else "medium"
            rat = "another passage states the opposite direction for the same comparison"
        elif not p["neg"] and not p["null"] and b["null"] and b["cov"] >= 0.40:
            v, conf, rule, lims = "contradicted", "medium", "R2", ["material_reports_null_result"]
            rat = "passage reports a null result, contradicting the affirmative claim"
        elif p["neg"] and b["neg"]:
            v, conf, rule, lims = "supported", "medium", "R3", ["negation_aligned"]
            rat = "claim is negative and the passage negates the same predication"
        elif b["cov"] >= 0.34 and (not p["nums"] or b["numcov"] >= 1.0):
            v, rule = "supported", "R4"
            conf = "high" if (p["nums"] and b["numcov"] >= 1.0 and b["cov"] >= 0.5) else "medium"
            lims = []
            rat = "entity, direction and values covered verbatim; no counter-evidence"
        elif b["cov"] >= 0.20 or b["numcov"] > 0:
            v, rule = "partially_supported", "R5"
            conf = "medium" if b["cov"] >= 0.3 else "low"
            lims = (["value_not_matched"] if (p["nums"] and b["numcov"] < 1.0) else []) + \
                   (["direction_not_stated"] if not p["rel"] else []) + \
                   (["partial_key_term_coverage"] if b["cov"] < 0.34 else [])
            lims = lims or ["partial_alignment"]
            rat = "only part of the assertion is aligned"
        else:
            v, conf, rule, lims = "insufficient_evidence", "low", "R6", ["topic_overlap_only"]
            rat = "only topic overlap was found; topic relevance is not support"
    basis = "%s: coverage %.2f, anchors %d/%d" % (rule, b["cov"] if b else 0.0,
                                                  len(b["matched_nums"]) if b else 0, len(p["nums"]))
    return {"verdict": v, "confidence": conf, "rule": rule, "evidence": evs, "basis": basis,
            "rationale": rat, "limitations": lims, "scope": scope}


def aggregate(vs):
    if not vs:
        return "insufficient_evidence"
    if all(v == "supported" for v in vs):
        return "supported"
    if all(v == "contradicted" for v in vs):
        return "contradicted"
    if all(v == "insufficient_evidence" for v in vs):
        return "insufficient_evidence"
    return "partially_supported"


def _rank(c):
    return {"high": 3, "medium": 2, "low": 1}.get(str(c or "").lower(), 0)


def detect_conflict(subs):
    """Two sources pulling opposite ways: kept side by side, unresolved."""
    items = [e for s in subs for e in s["evidence"] if e["score"] >= 0.30 and e["direction"] in (1, -1)]
    for a in items:
        for b in items:
            if a["source_id"] != b["source_id"] and a["direction"] * b["direction"] == -1:
                return {"present": True, "unresolved": True, "both_sides": [dict(a), dict(b)],
                        "note": "sources point opposite ways; corpus does not adjudicate"}
    return {"present": False, "unresolved": False, "both_sides": []}


def verify_claim(c, ctx):
    p0, subs = profile(c["claim_text"]), []
    for i, s in enumerate(split_subs(c["claim_text"]), 1):
        p = profile(s)
        if not p["keys"] and not p["nums"]:
            p = dict(p0, text=s)
        qlog = []
        r = judge(p, candidates(p, ctx["units"], 3, c.get("source_hint"), qlog), len(ctx["units"]))
        sid = "%s.%d" % (c["claim_id"], i)
        ctx["query_log"].append(dict({"claim_id": c["claim_id"], "sub_id": sid, "text": s[:120]},
                                     **(qlog[0] if qlog else {})))
        subs.append({"sub_id": sid, "text": soft(s), "type": p["type"], "required_evidence_type": REQ[p["type"]],
                     "verdict": r["verdict"], "verdict_confidence": r["confidence"], "rule_id": r["rule"],
                     "verdict_basis": r["basis"], "evidence": r["evidence"], "rationale": r["rationale"],
                     "limitations": r["limitations"], "search_scope": r["scope"], "counter_evidence_searched": True})
    conflict = detect_conflict(subs)
    ranks = [_rank(s["verdict_confidence"]) for s in subs if _rank(s["verdict_confidence"])]
    low = norm(c["claim_text"]).lower()
    return {"claim_id": c["claim_id"], "claim_text": c["claim_text"], "claim_kind": p0["type"],
            "source_hint": c.get("source_hint"), "sub_claims": subs,
            "verdict": aggregate([s["verdict"] for s in subs]),
            "verdict_confidence": "low" if conflict["unresolved"] else
            ({3: "high", 2: "medium", 1: "low"}.get(min(ranks)) if ranks else "low"),
            "aggregation_rule": AGG_RULE, "conflict": conflict, "comparator": bool(p0["rel"]),
            "negation": p0["neg"],
            "conditions": sorted({w for w in ("only", "all", "under", "in vitro", "in vivo", "仅", "条件下")
                                  if w in low}),
            "limitations": sorted({l for s in subs for l in s["limitations"]}), "status": "verified",
            "rationale": "%d sub-claims: %s" % (len(subs), " / ".join(s["sub_id"] + "=" + s["verdict"]
                                                                       for s in subs))}


def failed_claim(c, ctx, exc):
    sub = {"sub_id": c["claim_id"] + ".1", "text": c["claim_text"], "type": "fact",
           "required_evidence_type": REQ["fact"], "verdict": "insufficient_evidence", "verdict_confidence": "low",
           "rule_id": "R0", "verdict_basis": "pipeline error: %s" % type(exc).__name__, "evidence": [],
           "rationale": "verification raised an exception", "limitations": ["verification_error"],
           "counter_evidence_searched": False, "search_scope": {"units_scanned": len(ctx["units"])}}
    return {"claim_id": c["claim_id"], "claim_text": c["claim_text"], "claim_kind": "fact", "sub_claims": [sub],
            "verdict": "insufficient_evidence", "verdict_confidence": "low", "aggregation_rule": AGG_RULE,
            "conflict": {"present": False, "unresolved": False, "both_sides": []},
            "limitations": ["verification_error"], "status": "error", "rationale": str(exc)[:200]}


def verify_all(ctx):
    out = []
    for c in ctx["claims"]:
        try:
            out.append(verify_claim(c, ctx))
        except Exception as exc:                       # one bad claim never kills the run
            out.append(failed_claim(c, ctx, exc))
    return out
