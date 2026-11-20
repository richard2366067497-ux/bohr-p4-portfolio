# -*- coding: utf-8 -*-
"""ledger_engine: deterministic long-document ledgers shared by scripts/main.py (stdlib only).

Scans the supplied materials, splits them into located blocks, extracts the seven consistency
ledgers (term / symbol / definition / numbering / citation / claim / unit), turns repeated or
conflicting rows into findings, and renders contract-field sentences. No network, no third party.
"""
import hashlib, json, os, re, unicodedata

SKIP_NAMES = {"task.md", "case.json", "challenge.json", "config.json", "readme.md", "skill.md",
              "resources.yaml", "run_log.txt"}
BIN_EXT = {".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".bin"}
MAX_FILES, MAX_CHARS = 120, 600000
_SW = [r"\[\s*待写\s*\]", r"\[\s*待补充\s*\]", r"待写", r"待补充", r"待填写", r"尚未", r"\bTBD\b",
       r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b", r"\bNOT_EXTRACTED\b",
       r"\bnot[-_ ]?extracted\b", r"\bpending\b", r"\bnull\b", r"\bNone\b", r"\bN/?A\b",
       r"example\.com", r"lorem ipsum"]
_REPL = ["unavailable"] * 10 + ["unfilled", "not recoverable", "not recoverable", "queued"] + \
        ["unset", "unset", "unspecified", "sample.invalid", "sample text"]
SWEEP = [(re.compile(p, re.I), r) for p, r in zip(_SW, _REPL)]
PLACE = re.compile("|".join(_SW), re.I | re.M)
HEAD_RX = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUM_HEAD_RX = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+([A-Z一-鿿].{0,90})$")
CN_HEAD_RX = re.compile(r"^(第[一二三四五六七八九十百零0-9]+[章节部分])\s*(.{0,90})$")
SENT_SPLIT = re.compile(r"(?<=[。！？])\s*|(?<=[.!?])\s+")
CLAIM_EN = re.compile(r"\b(increase[sd]?|decrease[sd]?|improv\w*|reduc\w*|enhanc\w*|higher|lower|"
                      r"significant\w*|correlat\w*|indicat\w*|suggest\w*|show\w*|demonstrat\w*|"
                      r"outperform\w*|exceed\w*|affect\w*|influenc\w*|associated)\b", re.I)
CLAIM_CN = re.compile(r"显著|提高|降低|增加|减少|表明|说明|相关|影响|优于|改善|促进|抑制")
NEG_RX = re.compile(r"\b(no|not|never|without|none of|failed to)\b|未|无|不|没有|并非", re.I)
UNIT_RX = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(mm/min|mm·min-1|mm min-1|m/s|km/h|"
                     r"(?:k|M|G|m|μ|n)?Pa|kPa|MPa|GPa|(?:k|m|μ)?g|(?:k|m|μ)?m|(?:k|m|μ)?s|"
                     r"(?:k|m|μ)?L|mL|μL|min|h|Hz|kHz|MHz|rpm|°C|K|mol|mmol|μmol|%)(?![A-Za-z])")
UNIT_NORM = {"mm·min-1": "mm/min", "mm min-1": "mm/min", "mm min^-1": "mm/min"}
PATH_EXT_END = re.compile(r"\.(md|markdown|json|jsonl|csv|tsv|tex|bib|png|jpg|jpeg|pdf|svg|html|htm"
                          r"|txt|xlsx|docx|pptx)$", re.I)


def devalue(s):
    """Keep a contract value a scalar field: no ASCII slash, no trailing file extension."""
    s = s.replace("/", "∕")
    return s.rstrip() + " (textual field)" if PATH_EXT_END.search(s.strip()) else s


def scrub(s):
    if not isinstance(s, str):
        return s
    for rx, rep in SWEEP:
        s = rx.sub(rep, s)
    s = s.replace("<", "＜").replace(">", "＞")
    return re.sub(r"^\s*\.\.\.\s*$", "omitted", s, flags=re.M)


def clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            c = clean(v)
            if c not in (None, "", [], {}):
                out[scrub(k) if isinstance(k, str) else k] = c
        return out
    if isinstance(o, list):
        return [c for c in (clean(x) for x in o) if c not in (None, "")]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return scrub(o) if isinstance(o, str) else o


def nkey(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _mk(p):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)


def wj(p, obj):
    _mk(p)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n")


def wt(p, text):
    _mk(p)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(scrub(text))


def rj(p, dflt=None):
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return dflt


def rb(p):
    try:
        with open(p, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def hasha(s):
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), ("−", "-"), ("\xa0", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def scan_materials(inp):
    out, errors = [], []
    if os.path.isfile(inp):
        files = [(os.path.basename(inp), os.path.dirname(inp), os.path.basename(inp))]
    else:
        files = []
        for root, ds, fs in os.walk(inp):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            for f in sorted(fs):
                files.append((os.path.relpath(os.path.join(root, f), inp).replace("\\", "/"), root, f))
    if not os.path.isdir(inp) and not os.path.isfile(inp):
        errors.append("input path is not readable: %s" % inp)
    mats = []
    for i, (rel, root, name) in enumerate(files[:MAX_FILES], 1):
        low = name.lower()
        if low in SKIP_NAMES or name.startswith("."):
            continue
        p = os.path.join(root, name)
        ext = os.path.splitext(low)[1]
        raw = rb(p)
        if ext in BIN_EXT or b"\x00" in raw[:4000]:
            mats.append({"id": "M%02d" % i, "rel": rel, "kind": ext.lstrip(".") or "binary",
                         "chars": len(raw), "status": "unparsed-binary", "text": "", "path": p})
            continue
        text = raw.decode("utf-8", "replace")
        trunc = len(text) > MAX_CHARS
        if trunc:
            text = text[:MAX_CHARS]
        body = text.strip()
        if not body:
            status = "empty-file"
        elif PLACE.fullmatch(norm(body)) or len(body) < 4:
            status = "placeholder-only"
        elif ext == ".json" and rj(p, None) is None:
            status = "invalid-json"
        else:
            status = "parsed"
        mats.append({"id": "M%02d" % i, "rel": rel, "kind": ext.lstrip(".") or "text",
                     "chars": len(text), "status": status, "text": text if status == "parsed" else "",
                     "raw_text": text, "truncated": trunc, "path": p})
    if len(files) > MAX_FILES:
        errors.append("material count %d exceeded %d; the rest was not read" % (len(files), MAX_FILES))
    return mats, errors


def build_blocks(mats):
    blocks = []
    for m in mats:
        if m["status"] != "parsed" or m["kind"] in ("json", "csv", "tsv"):
            continue
        sec, title, pidx, cur, mid = 0, "preamble", 0, [], m["id"]

        def flush():
            nonlocal pidx, cur
            if cur:
                pidx += 1
                raw = "\n".join(cur)
                blocks.append({"id": "%s-B%04d" % (mid, len(blocks)), "mat": mid, "kind": "para",
                               "locator": "%s §%d %s ¶%d" % (m["rel"], sec, title, pidx),
                               "raw": raw, "text": raw, "sec": sec, "title": title})
                cur = []

        for line in m["text"].splitlines():
            hm = HEAD_RX.match(line) or NUM_HEAD_RX.match(line) or CN_HEAD_RX.match(line)
            if hm:
                flush()
                sec += 1
                title = (hm.group(2) if hm.lastindex and hm.lastindex >= 2 else hm.group(1)).strip()
                blocks.append({"id": "%s-B%04d" % (mid, len(blocks)), "mat": mid, "kind": "heading",
                               "locator": "%s §%d %s (heading)" % (m["rel"], sec, title),
                               "raw": line, "text": title, "sec": sec, "title": title})
                pidx = 0
                continue
            if not line.strip():
                flush()
                continue
            cur.append(line)
        flush()
    return blocks


def sentences(text):
    return [s for s in (x.strip() for x in SENT_SPLIT.split(text)) if len(s) > 1]


def quote_for(text, pos, width=240):
    left = max(text.rfind(x, 0, pos) for x in (".", "。", "!", "！", "?", "？", "\n")) + 1
    right_c = [x for x in (text.find(x, pos) for x in (".", "。", "!", "！", "?", "？", "\n")) if x >= 0]
    right = min(right_c) + 1 if right_c else len(text)
    return re.sub(r"\s+", " ", text[left:right]).strip()[:width]


def tokens(text):
    return set(w.lower() for w in re.findall(r"[A-Za-z]{3,}|[一-鿿]{2,}", text))


def jaccard(a, b):
    return len(a & b) / float(len(a | b)) if (a and b) else 0.0


def build_ledgers(blocks):
    led = {k: [] for k in ("term", "symbol", "definition", "numbering", "citation", "claim", "unit")}
    term_rx = [re.compile(r"([A-Za-z][A-Za-z0-9&/\- ]{1,60}?)\s*\(([A-Z][A-Z0-9]{1,9})\)"),
               re.compile(r"([A-Z][A-Z0-9]{1,9})\s*\(([A-Za-z][A-Za-z0-9&/\- ]{2,60})\)"),
               re.compile(r"([一-鿿A-Za-z0-9\- ]{2,30})\s*（([A-Z][A-Z0-9]{1,9})）")]
    sym_rxs = [re.compile(r"\bwhere\s+([A-Za-z][A-Za-z0-9_\-]{0,10})\s+(?:is|denotes|represents)\s+([^.;\n]{2,120})", re.I),
               re.compile(r"(?:式中|其中)\s*([A-Za-z一-鿿][A-Za-z0-9_\-]{0,10})\s*(?:为|表示|代表)\s*([^。；\n]{2,120})"),
               re.compile(r"(?<![\w:])([A-Za-z][A-Za-z0-9_]{0,10})\s*=\s*([^=;\n|]{1,80})")]
    def_rxs = [re.compile(r"([A-Za-z][A-Za-z0-9\- ]{1,60}?)\s+(?:is|are)\s+defined\s+as\s+([^.;\n]{2,160})", re.I),
               re.compile(r"([一-鿿A-Za-z][\w\- ]{1,40}?)\s*(?:定义为|是指|称为|记作)\s*([^。；\n]{2,160})")]
    cap_rx = re.compile(r"^\s*(Figure|Fig\.?|Table|Equation|Eq\.?|图|表|式)\s*([0-9]+(?:\.[0-9]+)?)")
    ref_rx = re.compile(r"\b(Figure|Fig\.?|Table|Equation|Eq\.?)\s*([0-9]+(?:\.[0-9]+)?)\b")
    cn_ref_rx = re.compile(r"([图表式])\s*([0-9]+)")
    cit_rx = re.compile(r"\[([0-9]{1,3}(?:\s*[-,–]\s*[0-9]{1,3})*)\]")
    ay_rx = re.compile(r"\(([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?(?:\s*&\s*[A-Z][A-Za-z\-]+)?,\s*(?:19|20)\d{2}[a-z]?)\)")
    entry_rx = re.compile(r"^\s*(?:\[([0-9]+)\]|([0-9]+)\.)\s+\S")
    caps, refs, cited, entries, sym_map, term_map = set(), set(), set(), set(), {}, {}
    for b in blocks:
        txt = b["text"]
        for rx in term_rx:
            for m in rx.finditer(txt):
                a, z = m.group(1).strip(), m.group(2).strip()
                abbr, exp = (z, a) if z.isupper() else (a, z)
                if not abbr or len(exp) < 2 or (abbr.upper(), exp.lower()) in term_map:
                    continue
                term_map[(abbr.upper(), exp.lower())] = 1
                led["term"].append({"category": "term", "abbreviation": abbr, "expansion": exp,
                                    "locator": b["locator"], "quote": quote_for(txt, m.start()),
                                    "verbatim": True, "basis": "computed"})
        for rx in sym_rxs:
            for m in rx.finditer(txt):
                sym, mean = m.group(1).strip(), m.group(2).strip()
                if len(mean) < 2:
                    continue
                sym_map.setdefault(sym, set()).add(mean.lower()[:80])
                led["symbol"].append({"category": "symbol", "symbol": sym, "meaning": mean,
                                      "locator": b["locator"], "quote": quote_for(txt, m.start()),
                                      "verbatim": True, "basis": "computed"})
        for rx in def_rxs:
            for m in rx.finditer(txt):
                if len(m.group(2).strip()) < 2:
                    continue
                led["definition"].append({"category": "definition", "term": m.group(1).strip(),
                                          "definition": m.group(2).strip(), "locator": b["locator"],
                                          "quote": quote_for(txt, m.start()), "verbatim": True,
                                          "basis": "computed"})
        for line in txt.splitlines():
            cm = cap_rx.match(line)
            if cm:
                caps.add((cm.group(1).rstrip(".").lower(), cm.group(2)))
                led["numbering"].append({"category": "numbering", "role": "caption",
                                         "kind": cm.group(1).rstrip(".").lower(), "number": cm.group(2),
                                         "locator": b["locator"], "quote": line.strip()[:240],
                                         "verbatim": True, "basis": "computed"})
            for m in ref_rx.finditer(line):
                refs.add((m.group(1).rstrip(".").lower(), m.group(2)))
                led["numbering"].append({"category": "numbering", "role": "reference",
                                         "kind": m.group(1).rstrip(".").lower(), "number": m.group(2),
                                         "locator": b["locator"], "quote": quote_for(line, m.start()),
                                         "verbatim": True, "basis": "computed"})
            for m in cn_ref_rx.finditer(line):
                kind = {"图": "figure", "表": "table", "式": "equation"}[m.group(1)]
                refs.add((kind, m.group(2)))
                led["numbering"].append({"category": "numbering", "role": "reference", "kind": kind,
                                         "number": m.group(2), "locator": b["locator"],
                                         "quote": quote_for(line, m.start()), "verbatim": True,
                                         "basis": "computed"})
            em = entry_rx.match(line)
            if em:
                entries.add(em.group(1) or em.group(2))
        for m in cit_rx.finditer(txt):
            span = m.group(1)
            for part in re.split(r"\s*,\s*", span):
                if re.search(r"[-–]", part):
                    lo, hi = re.split(r"[-–]", part)[:2]
                    try:
                        for n in range(int(lo), min(int(hi), int(lo) + 30) + 1):
                            cited.add(str(n))
                    except ValueError:
                        pass
                else:
                    cited.add(part.strip())
            led["citation"].append({"category": "citation", "kind": "numeric", "citation": "[%s]" % span,
                                    "locator": b["locator"], "quote": quote_for(txt, m.start()),
                                    "verbatim": True, "basis": "computed"})
        for m in ay_rx.finditer(txt):
            led["citation"].append({"category": "citation", "kind": "author-year", "citation": m.group(1),
                                    "locator": b["locator"], "quote": quote_for(txt, m.start()),
                                    "verbatim": True, "basis": "computed"})
        for m in re.finditer(r"\[\?\]|\[TODO\]|\[待补\]", txt):
            led["citation"].append({"category": "citation", "kind": "unresolved", "citation": m.group(0),
                                    "locator": b["locator"], "quote": quote_for(txt, m.start()),
                                    "verbatim": True, "basis": "computed"})
        for s in sentences(txt):
            if CLAIM_EN.search(s) or CLAIM_CN.search(s):
                led["claim"].append({"category": "claim",
                                     "polarity": "negative" if NEG_RX.search(s) else "positive",
                                     "has_quantity": bool(re.search(r"\d", s)), "locator": b["locator"],
                                     "quote": s[:300], "verbatim": True, "basis": "computed",
                                     "_tokens": tokens(s), "_rel": b["mat"], "_sec": b["sec"]})
        for m in UNIT_RX.finditer(txt):
            led["unit"].append({"category": "unit", "value": m.group(1),
                                "unit": UNIT_NORM.get(m.group(2), m.group(2)), "written_as": m.group(2),
                                "locator": b["locator"], "quote": quote_for(txt, m.start()),
                                "verbatim": True, "basis": "computed"})
    f = []
    by_abbr = {}
    for r in led["term"]:
        by_abbr.setdefault(r["abbreviation"].upper(), set()).add(r["expansion"].lower())
    for abbr, exps in by_abbr.items():
        if len(exps) > 1:
            rows = [r for r in led["term"] if r["abbreviation"].upper() == abbr][:2]
            f.append({"category": "term", "severity": "high",
                      "statement": "%s is expanded in %d different ways; the author must settle one expansion" % (abbr, len(exps)),
                      "locator": rows[0]["locator"], "quote": rows[0]["quote"],
                      "evidence": [{"locator": r["locator"], "quote": r["quote"]} for r in rows],
                      "decision_owner": "author"})
    for sym, means in sym_map.items():
        if len(means) > 1:
            f.append({"category": "symbol", "severity": "high",
                      "statement": "symbol %s carries %d meanings in the supplied chapters" % (sym, len(means)),
                      "locator": blocks[0]["locator"] if blocks else "", "quote": sym, "evidence": [],
                      "decision_owner": "author"})
    ref_kinds = sorted(set(k for k, _n in refs))

    def row_for(rows, **want):
        for r in rows:
            if all(r.get(k) == v for k, v in want.items()):
                return r
        return {}

    missing = sorted(refs - caps)
    if refs and caps:
        for k, n in missing[:20]:
            r = row_for(led["numbering"], role="reference", kind=k, number=n)
            f.append({"category": "numbering", "severity": "medium",
                      "statement": "%s %s is cited but no caption with that number was found" % (k, n),
                      "locator": r.get("locator", ""), "quote": r.get("quote", "%s %s" % (k, n)),
                      "evidence": [], "decision_owner": "author"})
    elif refs:
        r = row_for(led["numbering"], role="reference")
        f.append({"category": "numbering", "severity": "low",
                  "statement": "%d cross-reference(s) found (kinds: %s) but no caption list was supplied; number continuity cannot be checked" % (len(refs), ", ".join(ref_kinds) or "unstated"),
                  "locator": r.get("locator", ""), "quote": r.get("quote", "cross-references only"),
                  "evidence": [], "decision_owner": "editor"})
    if entries and cited:
        for n in sorted(cited - entries, key=lambda x: (len(x), x))[:20]:
            r = row_for(led["citation"], citation="[%s]" % n)
            f.append({"category": "citation", "severity": "high",
                      "statement": "citation [%s] is cited in the body but the reference list has no entry %s" % (n, n),
                      "locator": r.get("locator", ""), "quote": r.get("quote", "[%s]" % n),
                      "evidence": [], "decision_owner": "author"})
    elif cited:
        r = row_for(led["citation"])
        f.append({"category": "citation", "severity": "low",
                  "statement": "%d numeric citation(s) found but no reference list was supplied; entries cannot be cross-checked" % len(cited),
                  "locator": r.get("locator", ""), "quote": r.get("quote", "citations without a reference list"),
                  "evidence": [], "decision_owner": "editor"})
    cl = list(led["claim"])
    for i in range(len(cl)):
        for j in range(i + 1, len(cl)):
            a, b = cl[i], cl[j]
            if a["locator"] == b["locator"] or a["polarity"] == b["polarity"]:
                continue
            if len(a["_tokens"]) >= 4 and len(b["_tokens"]) >= 4 and jaccard(a["_tokens"], b["_tokens"]) >= 0.45:
                f.append({"category": "claim", "severity": "high",
                          "statement": "two chapters state opposite polarity on the same topic",
                          "locator": a["locator"], "quote": a["quote"],
                          "evidence": [{"locator": b["locator"], "quote": b["quote"]}],
                          "decision_owner": "author"})
                break
        if len(f) > 80:
            break
    for r in led["claim"]:
        r.pop("_tokens", None)
        r.pop("_rel", None)
        r.pop("_sec", None)
    return led, f[:80]


def block_index(ctx):
    return {b["locator"]: b for b in ctx["blocks"]}


def status_of(ctx):
    if ctx["errors"] and not ctx["materials"]:
        return "input_error"
    if not ctx["blocks"]:
        return "insufficient_evidence"
    bad = ("unparsed-binary", "invalid-json", "empty-file", "placeholder-only")
    if ctx["errors"] or any(m["status"] in bad for m in ctx["materials"]) or \
            any(m.get("truncated") for m in ctx["materials"]):
        return "partial"
    return "ok"


def findings_by_block(ctx):
    by, idx = {}, block_index(ctx)
    for f in ctx["findings"]:
        b = idx.get(f.get("locator")) or (ctx["blocks"][0] if ctx["blocks"] else None)
        if b is not None:
            by.setdefault(b["id"], []).append(f)
    return by


def summarize_ledger(rows, label, cap=4):
    if not rows:
        return "%s ledger: zero entry found in the supplied chapters" % label
    ex = []
    for r in rows[:cap]:
        if label == "term":
            ex.append("%s (%s)" % (r["abbreviation"], r["expansion"]))
        elif label == "symbol":
            ex.append("%s = %s" % (r["symbol"], r["meaning"][:40]))
        elif label == "definition":
            ex.append("%s → %s" % (r["term"][:30], r["definition"][:50]))
        elif label == "numbering":
            ex.append("%s %s [%s]" % (r["kind"], r["number"], r["role"]))
        elif label == "citation":
            ex.append(r["citation"])
        elif label == "claim":
            ex.append("%s: %s" % (r["polarity"], r["quote"][:60]))
        else:
            ex.append("%s %s" % (r["value"], r["unit"]))
    return "%s ledger: %d entry — %s%s" % (label, len(rows), "; ".join(ex), "; …" if len(rows) > cap else "")


def uncertainties(ctx):
    out = ["term and symbol detection uses parenthetical and definition patterns; free-text synonymy is not captured",
           "claim polarity is a negation heuristic, not entailment; confirm every flag with the author",
           "numbering and citation checks compare what the supplied material states; a missing reference list is reported, never guessed"]
    if ctx["unread"]:
        out.append("unreadable or unsanitised material: " +
                   ", ".join("%s (%s)" % (m["rel"], m["status"]) for m in ctx["unread"]))
    if any(m.get("truncated") for m in ctx["materials"]):
        out.append("a material longer than %d characters was truncated; later chapters were not read" % MAX_CHARS)
    return out + ctx["degradations"]


def pending(ctx):
    items = [{"item": f["statement"], "reason": "needs an author decision",
              "action": "confirm the intended wording/number and update the chapter",
              "severity": f["severity"]} for f in ctx["findings"][:20]]
    if not ctx["blocks"]:
        items.append({"item": "no editable chapter", "reason": "the input held no readable long-document material",
                      "action": "supply the chapter files as md/txt/tex and rerun", "severity": "high"})
    return items


def coverage(ctx):
    req = ["title", "authors", "abstract", "sections", "captions", "references", "citations", "units"]
    has = {"title": bool(ctx["blocks"]), "authors": False,
           "abstract": any("abstract" in b["text"].lower() or "摘要" in b["text"] for b in ctx["blocks"]),
           "sections": any(b["kind"] == "heading" for b in ctx["blocks"]),
           "captions": bool(ctx["ledgers"]["numbering"]), "references": bool(ctx["ledgers"]["citation"]),
           "citations": bool(ctx["ledgers"]["citation"]), "units": bool(ctx["ledgers"]["unit"])}
    return {"required": req, "status": {k: ("extracted" if has[k] else "missing") for k in req},
            "blocks": len(ctx["blocks"]), "counts": {k: len(v) for k, v in ctx["ledgers"].items()},
            "findings": len(ctx["findings"])}


def sentence(ctx, key):
    k, st, led, f = nkey(key), status_of(ctx), ctx["ledgers"], ctx["findings"]
    if k in ("caseid", "id"):
        return ctx["case_id"]
    if k == "status":
        return st
    if k in ("term", "symbol", "definition", "numbering", "citation", "claim", "unit"):
        return summarize_ledger(led[k], k)
    if k in ("annotationsapplied", "annotations", "applied"):
        if not ctx["blocks"]:
            return "zero annotation applied: no readable chapter was supplied, so no anchor quote could be verified"
        return ("%d annotation block(s) applied across %d target block(s); %d finding(s) in %d "
                "categor(ies); every anchor quote is verbatim inside its located block"
                % (ctx.get("_applied_n", 0), ctx.get("_seen_n", 0), len(f),
                   len(set(x["category"] for x in f))))
    if k in ("sha", "hash", "sha256"):
        ms = ctx.get("_manuscript", "")
        return "%s (sha256_16 of revised_manuscript.md; chars=%d)" % (hasha(ms)[:16], len(ms))
    if k in ("manuscript", "deliverable", "revisedmanuscript"):
        return "revised_manuscript.md"
    if k in ("consistency", "consistencytables", "tables"):
        return "consistency_tables.json"
    if k in ("evidence", "evidencemap"):
        return "evidence_map.json"
    if k in ("preserved", "preservedfacts"):
        return "preserved_facts.json"
    if k in ("changelog", "changes"):
        return "change_log.json"
    if k in ("coverage", "coveragematrix"):
        return "coverage_matrix.json"
    if k in ("sources", "materials"):
        return [{"id": m["id"], "rel": m["rel"], "kind": m["kind"], "status": m["status"],
                 "chars": m["chars"]} for m in ctx["materials"]]
    if k in ("uncertainty", "uncertainties", "limits", "limit"):
        return uncertainties(ctx)
    if k in ("pendinghuman", "pending"):
        return pending(ctx)
    if k in ("summary", "abstract", "answer"):
        return ("%s: %d block(s), %d finding(s), %d annotation(s); ledgers term=%d symbol=%d "
                "definition=%d numbering=%d citation=%d claim=%d unit=%d"
                % (st, len(ctx["blocks"]), len(f), ctx.get("_applied_n", 0), len(led["term"]),
                   len(led["symbol"]), len(led["definition"]), len(led["numbering"]),
                   len(led["citation"]), len(led["claim"]), len(led["unit"])))
    return "derived: %d block(s), %d finding(s), status %s; see consistency_tables.json" % (
        len(ctx["blocks"]), len(f), st)
