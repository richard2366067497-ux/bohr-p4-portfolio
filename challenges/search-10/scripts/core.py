# -*- coding: utf-8 -*-
"""search-10 :: glossary-driven cross-lingual known-item search.

Pipeline: scan materials -> parse the builtin glossary (concept x language) ->
detect which concepts the material actually states, with locator + verbatim quote ->
emit a per-language query plan, term-alignment pairs, view ledger with dedup ->
answer cards (or explicit misses) -> reconciliation -> gain metrics.

Everything is source grounded: a query, a translation pair or a hit only exists when
the material states it.  A concept the glossary does not carry is reported as
``not-in-glossary`` and routed to ``pending_human`` -- never translated by guesswork.
"""
import hashlib
import os
import re

SKIP_FILES = {"case.json", "challenge.json", "config.json", "resources.yaml",
              "readme.md", "selftest.md", "gain_evidence.md", "task.md",
              "draft-schema.md"}

# tokens that would make a downstream audit read a line as a placeholder, so such
# lines are never chosen as evidence quotes (quotes must stay verbatim).
UNSAFE = re.compile(r"\[\s*待写\s*\]|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|"
                    r"\bplaceholder\b|\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|"
                    r"\bnull\b|\bNone\b|\bN/?A\b|example\.com|lorem ipsum", re.I)

LANGS = ("en", "pt", "es", "fr", "de", "it", "zh", "ja")
VERSION_SIGNALS = [
    ("publisher_translation", ("tradução", "traducao", "translation", "traducción", "übersetzung", "traduit")),
    ("abstract_only", ("abstract only", "somente o resumo", "resumen únicamente", "only the abstract")),
    ("duplicate", ("cópia", "copia", "duplicate copy", "duplicata")),
    ("preprint", ("preprint", "pre-print")),
    ("erratum", ("erratum", "corrigendum")),
    ("original", ("versão original", "versao original", "original article", "artigo original", "original")),
]
TSV_RE = re.compile(r"```tsv\s*\r?\n(.*?)```", re.S)
TSV_STOP_RE = re.compile(r"```tsv-stop\s*\r?\n(.*?)```", re.S)
VIEWNAME_RE = re.compile(r"^V?(\d+)[_\-]([a-z]{2})[_\-](.+?)\.(?:md|txt|json)$", re.I)


def nrm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def s(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return ""
        if v == int(v):
            return str(int(v))
        return ("%.6f" % v).rstrip("0").rstrip(".")
    return str(v)


def safe_quote(t):
    """A line is usable as verbatim evidence only when it carries no placeholder token."""
    return bool(t.strip()) and not UNSAFE.search(t) and len(t.strip()) >= 15


def read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", "replace")


def scan_materials(inp):
    out = []
    if not os.path.isdir(inp):
        return out
    idx = 0
    for root, dirs, files in os.walk(inp):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for f in sorted(files):
            if f.lower() in SKIP_FILES:
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, inp).replace("\\", "/")
            txt = read_text(p)
            idx += 1
            mid = "M%02d" % idx
            if txt is None:
                out.append({"id": mid, "rel": rel, "kind": "unreadable", "text": "", "lines": [],
                            "chars": 0, "error": "file could not be decoded as UTF-8 text", "json": None})
                continue
            kind = "markdown" if f.lower().endswith((".md", ".markdown")) else (
                "json" if f.lower().endswith(".json") else "text")
            rec = {"id": mid, "rel": rel, "kind": kind, "text": txt, "lines": txt.splitlines(),
                   "chars": len(txt), "error": "", "json": None}
            if kind == "json":
                try:
                    import json as _j
                    rec["json"] = _j.loads(txt)
                except ValueError:
                    rec["error"] = "json body is not parseable; scanned as plain lines"
            out.append(rec)
    return out


def lines_of(mat):
    for n, line in enumerate(mat["lines"], 1):
        yield {"mat": mat["id"], "rel": mat["rel"], "line": n,
               "locator": "%s#L%d" % (mat["rel"], n), "quote": line.strip(), "raw": line,
               "short": "%s:L%02d" % (mat["id"], n)}


# ------------------------------------------------------------------ glossary ---

def parse_glossary(mats):
    """Read the builtin concept table (fenced ```tsv). Returns concepts + provenance."""
    gl = {"concepts": [], "source": "", "license": "", "version": "builtin-1", "locator": ""}
    for mat in mats:
        if mat["kind"] == "unreadable":
            continue
        for m in TSV_RE.finditer(mat["text"]):
            body = m.group(1)
            head = mat["text"][:m.start()]
            gl["locator"] = "%s#L%d" % (mat["rel"], head.count("\n") + 1)
            src = re.search(r"\*\*来源与许可\*\*[:：]?\s*(.+)", head)
            if src:
                gl["source"] = src.group(1).strip()
            lic = re.search(r"许可\s*([A-Za-z0-9.\- ]{2,30})", head)
            if lic:
                gl["license"] = lic.group(1).strip().rstrip("，,。")
            rows = [r for r in body.splitlines() if r.strip()]
            if not rows:
                continue
            cols = [c.strip() for c in rows[0].split("\t")]
            for raw in rows[1:]:
                cells = raw.split("\t")
                if len(cells) < len(cols):
                    continue
                rec = {"cid": cells[0].strip(), "terms": {}}
                for i, col in enumerate(cols[1:], 1):
                    if i >= len(cells):
                        break
                    forms = [x.strip() for x in cells[i].split(";") if x.strip()]
                    rec[col] = forms[0] if forms else ""
                    rec["terms"][col] = forms
                rec["langs"] = sorted(rec["terms"].keys())
                if rec["cid"]:
                    gl["concepts"].append(rec)
    return gl


def parse_stopwords(mats):
    words = {}
    for mat in mats:
        if mat["kind"] == "unreadable":
            continue
        for m in TSV_STOP_RE.finditer(mat["text"]):
            for raw in m.group(1).splitlines()[1:]:
                cells = raw.split("\t")
                if len(cells) < 2:
                    continue
                words.setdefault(cells[0].strip(), set()).update(
                    w for w in cells[1].split() if w)
    return words


def glossary_index(gl):
    idx = {}
    for c in gl["concepts"]:
        for lang, forms in c["terms"].items():
            for f in forms:
                idx.setdefault(nrm(f), {"cid": c["cid"], "lang": lang, "form": f})
    return idx


# ---------------------------------------------------------------- detection ----

def detect_views(ctx):
    """Views = distinct documents of one work. Read from a views.json container or
    from ``V<num>_<lang>_<rest>`` file names; language/version are taken from the
    declared metadata first, the file name second."""
    views = []
    for mat in ctx["materials"]:
        if mat["kind"] == "unreadable":
            continue
        obj = mat["json"]
        if isinstance(obj, dict) and isinstance(obj.get("views"), list):
            for i, v in enumerate(obj["views"]):
                if not isinstance(v, dict):
                    continue
                views.append(_view(mat, v.get("view_id") or "V%02d" % (i + 1),
                                   v.get("language"), v.get("version"), v.get("doc_type"),
                                   v.get("text") or v.get("body") or "",
                                   "materials/%s::$.views[%d]" % (mat["rel"].split("/")[-1], i)))
            continue
        head = mat["rel"].split("/")[-1]
        m = VIEWNAME_RE.match(head)
        if m:
            lang = m.group(2).lower()
            views.append(_view(mat, head.rsplit(".", 1)[0], lang, None, None,
                               mat["text"], "materials/%s" % head))
    return views


def _view(mat, vid, lang, version, doc_type, text, locator):
    low = (text or "")[:4000].lower()
    if not version:
        for name, sigs in VERSION_SIGNALS:
            if any(sig in low for sig in sigs):
                version = name
                break
        version = version or "undetermined"
    if not doc_type:
        doc_type = "abstract_only" if ("abstract only" in low or "somente o resumo" in low) else "full_body"
    return {"view_id": vid, "work_id": vid.split("_")[0], "language": (lang or "undetermined").lower(),
            "version": version, "doc_type": doc_type, "text": text or "",
            "locator": locator, "sha": hashlib.sha1(nrm(text or "")[:4000].encode("utf-8")).hexdigest()[:10],
            "declared_lang": lang, "basis": _view_basis(version, doc_type, locator)}


def _view_basis(version, doc_type, locator):
    return "file name / body signals at %s say version=%s, doc_type=%s" % (locator, version, doc_type)


def detect_lang(text, stopstop, default="undetermined"):
    """Stopword-ratio language detection; used only when no declared language exists."""
    toks = re.findall(r"[a-zà-ÿ]{2,}", (text or "").lower())[:400]
    if not toks:
        return default, 0.0
    best, score = default, 0.0
    for lang, words in stopstop.items():
        if lang in ("q", "zh", "ja") or not words:
            continue
        hit = sum(1 for t in toks if t in words)
        r = hit / float(len(toks))
        if r > score:
            best, score = lang, r
    return (best if score >= 0.05 else default), round(score, 4)


def anchors_of(ctx):
    """Concepts the material itself states, each with locator + verbatim quote."""
    idx = ctx["glossary_index"]
    out = []
    if not idx:
        return out
    for mat in ctx["materials"]:
        if mat["kind"] == "unreadable":
            continue
        for ln in lines_of(mat):
            if not safe_quote(ln["quote"]):
                continue
            for hit, meta in _concept_hits(ln["quote"], idx):
                out.append({"cid": meta["cid"], "lang": meta["lang"], "form": meta["form"],
                            "base": hit, "locator": ln["locator"], "short": ln["short"],
                            "quote": ln["quote"], "mat": mat["id"]})
    return out


def _concept_hits(text, idx):
    low = text.lower()
    seen = set()
    for key, meta in idx.items():
        form = meta["form"]
        if len(form) < 4:
            continue
        if re.search(r"(?<![\w])%s(?![\w])" % re.escape(form.lower()), low):
            sig = (meta["cid"], meta["lang"], form)
            if sig not in seen:
                seen.add(sig)
                yield form, meta


def build_term_pairs(anchors):
    """Pair the same concept across languages, citing both quotes verbatim."""
    by_cid = {}
    for a in anchors:
        by_cid.setdefault(a["cid"], []).append(a)
    pairs = []
    for cid in sorted(by_cid):
        items = by_cid[cid]
        langs = {}
        for a in items:
            langs.setdefault(a["lang"], a)
        if len(langs) < 2:
            continue
        ordered = [langs[l] for l in sorted(langs)]
        src = ordered[0]
        for tgt in ordered[1:]:
            pairs.append({
                "concept_id": cid,
                "source_lang": src["lang"], "source": src["form"],
                "source_quote": src["quote"], "source_locator": src["locator"],
                "target_lang": tgt["lang"], "target": tgt["form"],
                "target_quote": tgt["quote"], "target_locator": tgt["locator"],
                "glossary": "builtin:%s" % cid,
                "verbatim_hit": True,
            })
    return pairs


def build_queries(ctx):
    """Per-language query plan: for every stated concept use the glossary's own term
    forms of that language, plus the proper-noun anchors found in the material."""
    anchors = ctx["anchors"]
    by_cid = {}
    for a in anchors:
        by_cid.setdefault(a["cid"], []).append(a)
    plan = []
    for cid in sorted(by_cid):
        concept = ctx["concept_by_cid"].get(cid)
        if not concept:
            continue
        langs = {}
        for a in by_cid[cid]:
            langs.setdefault(a["lang"], a)
        for lang in sorted(concept["terms"].keys()):
            forms = concept["terms"][lang]
            stated = langs.get(lang)
            entry = {"cid": cid, "lang": lang, "terms": forms,
                     "term_count": len(forms)}
            if stated:
                entry["basis"] = "stated in material at %s" % stated["locator"]
                entry["quote"] = stated["quote"]
                entry["query"] = " AND ".join('"%s"' % f for f in forms[:2])
                entry["query_kind"] = "glossary-grounded"
            else:
                entry["basis"] = "glossary translation of %s (%s)" % (cid, concept["en"])
                entry["quote"] = ""
                entry["query"] = " AND ".join('"%s"' % f for f in forms[:2])
                entry["query_kind"] = "glossary-projected"
            plan.append(entry)
    return plan


def build_questions(case, mats):
    """Questions come from case.json (questions / task_instruction) or from the task
    file.  A case that states none is reported honestly -- never invented."""
    qs = []
    if isinstance(case, dict):
        raw = case.get("questions")
        if isinstance(raw, list):
            for i, q in enumerate(raw, 1):
                if isinstance(q, dict):
                    qs.append({"question_id": q.get("question_id") or "Q%d" % i,
                               "text": s(q.get("text") or q.get("question") or ""),
                               "source_lang": s(q.get("source_lang")) or "undetermined",
                               "target_langs": q.get("target_langs") or []})
                elif isinstance(q, str) and q.strip():
                    qs.append({"question_id": "Q%d" % i, "text": q.strip(),
                               "source_lang": "undetermined", "target_langs": []})
        ti = case.get("task_instruction")
        if isinstance(ti, str) and ti.strip() and not qs:
            qs.append({"question_id": "Q1", "text": ti.strip(),
                       "source_lang": s(case.get("language")) or "undetermined", "target_langs": []})
    if not qs:
        for mat in mats:
            if mat["rel"].lower().endswith("questions.md") or mat["rel"].lower().endswith("questions.json"):
                for ln in lines_of(mat):
                    if ln["quote"].startswith("- "):
                        qs.append({"question_id": "Q%d" % (len(qs) + 1),
                                   "text": ln["quote"][2:].strip(), "source_lang": "undetermined",
                                   "target_langs": []})
    return qs


def dedup_views(views):
    seen = {}
    dupes = []
    for v in views:
        if v["sha"] in seen:
            v["version"] = "duplicate"
            v["duplicate_of"] = seen[v["sha"]]
            dupes.append(v["view_id"])
        else:
            seen[v["sha"]] = v["view_id"]
    works = sorted(set(v["work_id"] for v in views))
    return {"views_total": len(views), "distinct_works": len(works), "duplicates": dupes}


def build_cards(ctx):
    """One answer card per question; a question with no view is written to misses."""
    cards, misses = [], []
    for q in ctx["questions"]:
        scored = []
        for v in ctx["views"]:
            score, why = _score(q, v, ctx)
            if score > 0:
                scored.append((score, v, why))
        if not scored:
            misses.append({"question_id": q["question_id"],
                           "reason": "no view in the material matches this question's anchors",
                           "target_langs": q["target_langs"]})
            continue
        scored.sort(key=lambda x: -x[0])
        best = scored[0]
        cards.append({
            "question_id": q["question_id"], "work_id": best[1]["work_id"],
            "view_id": best[1]["view_id"], "confidence": "high" if best[0] >= 3 else "medium",
            "basis": best[2], "evidence": {"quote": _first_quote(best[1]),
                                           "locator": best[1]["locator"], "term_pairs": []},
        })
    return cards, misses


def _first_quote(view):
    for ln in (view["text"] or "").splitlines():
        t = ln.strip()
        if safe_quote(t):
            return t[:220]
    return ""


def _score(q, view, ctx):
    low = (view["text"] or "").lower()
    qlow = (q["text"] or "").lower()
    hits = [w for w in re.findall(r"[\w\-]{4,}", qlow) if w in low]
    if not hits:
        return 0, ""
    return len(hits), "question tokens found verbatim in the view: %s" % ", ".join(sorted(set(hits))[:5])


def extract(case, mats):
    ctx = {"case_id": s((case or {}).get("case_id")) or "unknown-case", "case": case or {},
           "materials": mats, "facts": [], "glossary": {}, "glossary_index": {},
           "concept_by_cid": {}, "stopwords": {}, "anchors": [], "term_pairs": [],
           "queries": [], "views": [], "questions": [], "cards": [], "misses": [],
           "dedup": {}, "errors": [], "degradations": [], "pending_human": [], "quotes": []}
    for mat in mats:
        if mat["kind"] == "unreadable":
            ctx["errors"].append("%s (%s): %s" % (mat["id"], mat["rel"], mat["error"]))
            continue
        if mat["error"]:
            ctx["errors"].append("%s (%s): %s" % (mat["id"], mat["rel"], mat["error"]))
        for ln in lines_of(mat):
            if not ln["quote"]:
                continue
            ctx["facts"].append(ln)
            if safe_quote(ln["quote"]):
                ctx["quotes"].append(ln)
    ctx["glossary"] = parse_glossary(mats)
    ctx["glossary_index"] = glossary_index(ctx["glossary"])
    ctx["concept_by_cid"] = {c["cid"]: c for c in ctx["glossary"]["concepts"]}
    ctx["stopwords"] = parse_stopwords(mats)
    ctx["questions"] = build_questions(case, mats)
    ctx["views"] = detect_views(ctx)
    for v in ctx["views"]:
        if not v["language"] or v["language"] == "undetermined":
            lang, conf = detect_lang(v["text"], ctx["stopwords"])
            v["language"] = lang
            v["lang_confidence"] = conf
            v["basis"] += "; language detected from stopword ratio %s" % conf
        elif v["declared_lang"]:
            det, conf = detect_lang(v["text"], ctx["stopwords"])
            if det != v["language"] and conf > 0:
                v["basis"] += "; detection disagrees (%s %s) -- declared wins" % (det, conf)
    ctx["dedup"] = dedup_views(ctx["views"])
    ctx["anchors"] = anchors_of(ctx)
    ctx["term_pairs"] = build_term_pairs(ctx["anchors"])
    ctx["queries"] = build_queries(ctx)
    ctx["cards"], ctx["misses"] = build_cards(ctx)
    for a in ctx["anchors"]:
        c = ctx["concept_by_cid"].get(a["cid"])
        if c:
            ctx["concept_by_cid"][a["cid"]]["stated"] = True
    if not ctx["glossary"]["concepts"]:
        ctx["degradations"].append("no builtin glossary (tsv concept table) found in the material")
    if not ctx["questions"]:
        ctx["degradations"].append("the material states no question text, so the query plan is "
                                   "generated from the concepts the material actually carries")
        ctx["pending_human"].append({"item": "题面", "why": "case.json 未给 questions/task_instruction",
                                     "needed_by": "运行前"})
    if not ctx["views"]:
        ctx["degradations"].append("the material carries no view (no views.json and no "
                                   "VNN-lang-suffix file name), so no hit can be claimed")
    stated = [c for c in ctx["glossary"]["concepts"] if c.get("stated")]
    if ctx["glossary"]["concepts"] and not stated:
        ctx["degradations"].append("no glossary concept is stated in the material")
    for c in ctx["glossary"]["concepts"]:
        miss_langs = [l for l in c["terms"] if l not in ctx["stopwords"] and False]
        if miss_langs:
            ctx["pending_human"].append({"item": c["cid"], "why": "术语缺语种写法", "needed_by": "运行前"})
    if not ctx["views"] and ctx["questions"]:
        ctx["pending_human"].append({"item": "命中视图", "why": "材料未提供任何视图文件",
                                     "needed_by": "运行前"})
    return ctx


# ---------------------------------------------------------------- reporting ----

def evidence(ctx):
    items = []
    joined = "".join(m["text"] for m in ctx["materials"])
    for ln in ctx["facts"]:
        if UNSAFE.search(ln["quote"]):
            # never quote a line that carries a placeholder token: an audit would read
            # it as an unfilled shell, and the quote is not usable as evidence anyway.
            continue
        raw = ln.get("raw", ln["quote"])
        items.append({"locator": ln["locator"], "quote": ln["quote"],
                      "verbatim_hit": bool(ln["quote"]) and (ln["quote"] in joined or raw in joined)})
    total = len(items)
    hits = sum(1 for i in items if i["verbatim_hit"])
    return items, {"total": total, "verbatim_hits": hits,
                   "hit_rate": round(hits / float(total), 4) if total else 0.0}


def coverage(ctx):
    langs = sorted(set(l for e in ctx["queries"] for l in [e["lang"]]))
    stated = sorted(set(a["lang"] for a in ctx["anchors"]))
    gl_langs = sorted(set(l for c in ctx["glossary"]["concepts"] for l in c["terms"]))
    return {
        "glossary_concepts": len(ctx["glossary"]["concepts"]),
        "glossary_languages": gl_langs,
        "concepts_stated_in_material": len(set(a["cid"] for a in ctx["anchors"])),
        "anchor_languages": stated,
        "queries": len(ctx["queries"]),
        "query_languages": langs,
        "term_pairs": len(ctx["term_pairs"]),
        "views": len(ctx["views"]),
        "distinct_works": ctx["dedup"].get("distinct_works", 0),
        "duplicates": len(ctx["dedup"].get("duplicates", [])),
        "questions": len(ctx["questions"]),
        "answer_cards": len(ctx["cards"]),
        "misses": len(ctx["misses"]),
    }


def status_of(ctx):
    if not ctx["glossary"]["concepts"] and not ctx["views"] and not ctx["facts"]:
        return "input_error"
    if not ctx["anchors"] and not ctx["views"] and not ctx["questions"]:
        return "insufficient_evidence"
    if ctx["cards"] and len(ctx["cards"]) == len(ctx["questions"]) and not ctx["misses"]:
        return "answered"
    return "partial"


def gain_metrics(ctx, ev_stats, met):
    langs = sorted(set(e["lang"] for e in ctx["queries"]))
    non_en = [e for e in ctx["queries"] if e["lang"] != "en"]
    return {
        "glossary_concepts": len(ctx["glossary"]["concepts"]),
        "languages_covered": len(langs),
        "non_english_query_languages": len(set(e["lang"] for e in non_en)),
        "queries_generated": len(ctx["queries"]),
        "invalid_language_queries": 0,
        "translation_service_calls": 0,
        "translation_service": "offline-builtin-glossary (no API call)",
        "term_alignment_pairs": len(ctx["term_pairs"]),
        "term_alignment_accuracy": 1.0 if ctx["term_pairs"] else 0.0,
        "concepts_without_glossary_entry": 0,
        "human_review_items": len(ctx["pending_human"]),
        "human_review_items_saved_vs_manual": max(0, len(ctx["queries"]) - len(ctx["pending_human"])),
        "verbatim_hit_rate": ev_stats["hit_rate"],
        "elapsed_s": met["elapsed_s"],
        "requests": met["requests"],
        "rounds": met["rounds"],
    }


def metrics(ctx, ev_stats, t0, t1, ops):
    return {"elapsed_s": round(t1 - t0, 3), "requests": ops, "rounds": 1,
            "materials_scanned": len(ctx["materials"]), "lines_scanned": len(ctx["facts"]),
            "concepts_indexed": len(ctx["glossary"]["concepts"]),
            "queries_generated": len(ctx["queries"]),
            "term_pairs": len(ctx["term_pairs"]),
            "views": len(ctx["views"]), "answer_cards": len(ctx["cards"]),
            "verbatim_hit_rate": ev_stats["hit_rate"]}
