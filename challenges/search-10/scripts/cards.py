#!/usr/bin/env python3
"""cards.py - term alignment, bidirectional known-item matching, answer cards.

Resources come from ../references/glossary.md (MIT, self-compiled). Judgement (target view,
work hit, quote choice) is written by the operator in the draft; here we only produce
reproducible candidates, evidence candidates and card assembly.
"""
import re
from pathlib import Path

import verify as VF
import views as VW

MIN_SCORE = 10.0
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "references" / "glossary.md"
FALLBACK = [
    ("G01", "systematic review", {"en": ["systematic review"], "pt": ["revisão sistemática"]}),
    ("G18", "protein", {"en": ["protein"], "pt": ["proteína"]}),
    ("G31", "translation", {"en": ["translation"], "pt": ["tradução"]}),
]


def load_resources(path=None):
    """Parse the tsv blocks of references/glossary.md (concepts + stopwords). Never raises."""
    p = Path(path) if path else RES
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return list(FALLBACK), "glossary_unavailable_fallback", set()
    rows, words, blk = [], set(), None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("```tsv"):
            blk = "concept" if s == "```tsv" or "stop" not in s else "stop"
            continue
        if blk and s.startswith("```"):
            blk = None
            continue
        if not blk or not s or s.startswith("#"):
            continue
        cols = [c.strip() for c in s.split("\t")]
        if cols[0].lower() in ("cid", "lang"):
            continue
        if blk == "concept" and len(cols) >= 2:
            forms = {}
            for lg, i in (("en", 1), ("pt", 2), ("es", 3), ("fr", 4), ("de", 5)):
                if i < len(cols) and cols[i]:
                    xs = [x.strip() for x in cols[i].split(";") if x.strip()]
                    if xs:
                        forms[lg] = xs
            if forms:
                rows.append((cols[0], cols[1], forms))
        else:
            for w in cols[-1].split():
                w = w.strip().lower()
                if len(w) >= 2:
                    words.add(w)
    if len(rows) < 5:
        return list(FALLBACK), "glossary_parse_failed_fallback", words
    return rows, "references/glossary.md (%d concepts)" % len(rows), words


GLOSSARY, GLOSS_SRC, STOP = load_resources()
GLOSS = {cid: {"cid": cid, "en": en, "forms": forms} for cid, en, forms in GLOSSARY}
NOT_AUTHOR = STOP  # capitalised stopwords are not author surnames
QWORD = re.compile(r"(?i)\b(question|quest[aã]o|pergunta|frage|pregunta)\b")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>,;)\]]{3,80}")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
QUOTE_RE = re.compile(r"[\"\u201c\u201d\u00ab\u00bb\u300c\u300d\u300e\u300f\u300a\u300b]"
                      r"([^\"\u201c\u201d\u00ab\u00bb\u300c\u300d\u300e\u300f\u300a\u300b]{8,160})"
                      r"[\"\u201c\u201d\u00ab\u00bb\u300c\u300d\u300e\u300f\u300a\u300b]")
CAP_RE = re.compile(r"\b([A-Z\u00c0-\u00dd][a-z\u00e0-\u00ff]{2,24})\b")
NOT_AUTHOR = set("""study research paper article journal revista universidade university school
department institute center centre faculty hospital clinica clinic doi english portuguese spanish french
german brazil brasil portugal lisboa paulo janeiro abstract resumo introduction methods results
discussion conclusion references figure table version original translation duplicate note case input
skill agent draft team system page january february march april may june july august september october
november december data based using used between during aims objective background findings
the this that these those we in a an and or of for with by from""".split())


# ------------------------------------------------------------------ glossary
def _idx():
    out = {}
    for cid, g in GLOSS.items():
        for lg, surfs in g["forms"].items():
            for s in surfs:
                out.setdefault(VW.norm(VW.low(s)), []).append((cid, lg, s))
    return out


GIDX = _idx()


def concepts_in(text):
    t = " " + VW.norm(VW.low(text)) + " "
    out, seen = [], set()
    for form, hits in GIDX.items():
        if len(form) < 3:
            continue
        if not re.search(r"(?<![a-z0-9])" + re.escape(form) + r"(?![a-z0-9])", t):
            continue
        for cid, lg, surf in hits:
            if (cid, lg) not in seen:
                seen.add((cid, lg))
                out.append({"cid": cid, "lang": lg, "surface": surf})
    return out


def concept_support(cids, work_views):
    """cid -> {lang: [{view_id, surface, locator, verified}]}: cross-language term evidence.

    A concept supported by >=2 distinct surface forms proves the same idea is expressed
    differently across the work's language versions (alignment, not merely overlap).
    """
    sup = {}
    hay = {v["view_id"]: " " + VW.norm(VW.low(v.get("text", ""))) + " " for v in work_views}
    for cid in cids:
        forms = GLOSS[cid]["forms"] if cid in GLOSS else {}
        langs = {}
        for v in work_views:
            h = hay.get(v["view_id"], "")
            raw = " " + (v.get("text") or "").lower() + " "
            cands = []
            for lg, surfs in forms.items():
                for s in surfs:
                    sf = VW.norm(VW.low(s))
                    if sf and re.search(r"(?<![a-z0-9])" + re.escape(sf) + r"(?![a-z0-9])", h):
                        literal = VW.norm(s.lower()) in raw
                        cands.append((0 if literal else 1, lg, s))
            for _, lg, hit in sorted(cands)[:1]:   # one surface per view: accent-literal wins
                loc = VW.find_quote([v], hit)
                langs.setdefault(lg, []).append(
                    {"view_id": v["view_id"], "surface": hit,
                     "locator": loc[0]["locator"] if loc else v["locator"],
                     "verified": bool(loc)})
        if langs:
            sup[cid] = langs
    return sup


def stem(w):
    for suf in ("amentos", "amento", "acoes", "acao", "coes", "cao", "mente", "ities", "ity",
                "ies", "ing", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def content_terms(text):
    out, seen = [], set()
    for w in re.findall(r"[a-z0-9]{4,}", VW.low(text)):
        w = stem(w)
        if w in STOP or len(w) < 4 or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


# ------------------------------------------------------------------ questions
def _qid(it, i):
    if isinstance(it, dict):
        q = VW.first_str(it, ("question_id", "id", "qid", "key"))
        if q:
            return q
    return "Q%d" % (i + 1)


def split_questions(case, task_text=""):
    """Extract known-item questions from case.json (list or text) or task.md."""
    out = []
    if isinstance(case, dict):
        for key in ("questions", "research_questions", "known_items", "queries", "items"):
            val = case.get(key)
            if not isinstance(val, list) or not val:
                continue
            for i, it in enumerate(val):
                if isinstance(it, str):
                    txt, loc = it, "case.json#%s[%d]" % (key, i)
                elif isinstance(it, dict):
                    txt = VW.first_str(it, ("question", "text", "query", "prompt", "instruction",
                                            "q", "title")) or ""
                    loc = "case.json#%s[%d]" % (key, i)
                else:
                    continue
                if len(VW.norm(txt)) >= 15:
                    out.append({"question_id": _qid(it, i), "text": VW.norm(txt), "locator": loc})
            if out:
                return out
    src, base = "", "case.json#task_instruction"
    if isinstance(case, dict):
        src = VW.first_str(case, ("task_instruction", "instruction", "task", "description",
                                  "prompt", "content")) or ""
    if len(VW.norm(src)) < 20:
        src, base = task_text, "task.md"
    for i, b in enumerate(_split_blocks(src)):
        out.append({"question_id": "Q%d" % (i + 1), "text": b["text"],
                    "locator": "%s#%s" % (base, b["anchor"])})
    return out


def _split_blocks(text):
    lines = (text or "").splitlines()
    blocks, cur, anchor, kind = [], [], None, "para"
    for ln, line in enumerate(lines, start=1):
        s = line.strip()
        start = bool(re.match(r"(?i)^(#{1,4}\s*)?(q\s*\d+|question\s*\d+|quest[aã]o\s*\d+|\d+[.)])\b", s)) \
            or bool(QWORD.match(s))
        if start and cur:
            blocks.append({"text": VW.norm(" ".join(cur)), "anchor": "L%d" % anchor,
                           "kind": kind})
            cur, anchor = [], None
        if start:
            anchor, kind = ln, ("qmark" if QWORD.match(s) or
                                re.match(r"(?i)^(#{1,4}\s*)?q\s*\d+", s) else "numbered")
        if s and not s.startswith(("|", "```")):
            cur.append(s.lstrip("#").strip())
    if cur:
        blocks.append({"text": VW.norm(" ".join(cur)), "anchor": "L%d" % (anchor or 1),
                       "kind": kind})
    keep = [b for b in blocks if 15 <= len(b["text"]) <= 3000]
    strict = [b for b in keep if b.get("kind") == "qmark"]
    if strict:
        keep = strict
    else:
        like = [b for b in keep if ("?" in b["text"] or YEAR_RE.search(b["text"])
                                    or DOI_RE.search(b["text"]))]
        keep = like or keep
    if not keep:
        paras = [p for p in re.split(r"\n\s*\n", text or "") if VW.wc(p) >= 6]
        keep = [{"text": VW.norm(p)[:2500], "anchor": "p%d" % (i + 1)}
                for i, p in enumerate(paras[:6])]
    if not keep and VW.norm(text):
        keep = [{"text": VW.norm(text)[:2500], "anchor": "L1"}]
    return keep[:8]


def q_features(qtext):
    doi = DOI_RE.search(qtext)
    caps = []
    for w in CAP_RE.findall(qtext):
        if w not in caps and VW.low(w) not in NOT_AUTHOR and VW.low(w) not in STOP:
            caps.append(w)
    return {"doi": doi.group(0).rstrip(".,;") if doi else None,
            "quoted": QUOTE_RE.findall(qtext),
            "years": sorted(set(YEAR_RE.findall(qtext))),
            "authors": caps[:8], "terms": content_terms(qtext),
            "concepts": concepts_in(qtext)}


# ------------------------------------------------------------------ scoring
def score_views(feats, views, qlang):
    rows = []
    for v in views:
        hay = " " + VW.norm(VW.low((v.get("title") or "") + " \n " + v.get("text", ""))) + " "
        comp, hits = {}, []
        if feats["doi"] and v.get("doi") and VW.low(feats["doi"]) == VW.low(v["doi"]):
            comp["doi"] = 60.0
        ph = [p for p in feats["quoted"] if VW.norm(VW.low(p)) in hay]
        if ph:
            comp["phrase"] = 18.0 * len(ph)
        yr = [y for y in feats["years"] if re.search(r"\b%s\b" % y, hay)]
        if yr:
            comp["year"] = 4.0 * len(yr)
        au = [a for a in feats["authors"]
              if re.search(r"(?<![a-z])" + VW.low(a) + r"(?![a-z])", hay)]
        if au:
            comp["author"] = 6.0 * len(au)
        for c in feats["concepts"]:
            surf = VW.norm(VW.low(c["surface"]))
            if surf and re.search(r"(?<![a-z0-9])" + re.escape(surf) + r"(?![a-z0-9])", hay):
                hits.append({"cid": c["cid"], "lang": c["lang"], "surface": c["surface"],
                             "view_lang": v["language"]})
        cids = []
        for h in hits:
            if h["cid"] not in cids:
                cids.append(h["cid"])
        if cids:
            comp["concept"] = 5.0 * len(cids)
            comp["crosslang_bonus"] = 1.0 * len({h["lang"] for h in hits if h["lang"] != v["language"]})
        ttl = set(re.findall(r"[a-z]{4,}", VW.low(v.get("title") or "")))
        ov = len(ttl & set(feats["terms"]))
        if ov:
            comp["title_tokens"] = 1.5 * min(ov, 8)
        ov2 = len(set(re.findall(r"[a-z0-9]{4,}", VW.low(v.get("text", "")))) & set(feats["terms"]))
        if ov2:
            comp["term_overlap"] = 1.0 * min(ov2, 8)
        rows.append({"view_id": v["view_id"], "work_id": v["work_id"], "language": v["language"],
                     "version": v["version"], "doc_type": v["doc_type"],
                     "duplicate_of": v.get("duplicate_of"), "score": round(sum(comp.values()), 2),
                     "components": comp, "concept_hits": hits})
    return sorted(rows, key=lambda r: (-r["score"], r["view_id"]))


def rank_works(rows, views, qlang, cids=None):
    by_id = {v["view_id"]: v for v in views}
    by = {}
    for r in rows:
        w = by.setdefault(r["work_id"], {"work_id": r["work_id"], "components": {},
                                         "views": [], "score": 0.0})
        w["views"].append(r)
        w["score"] = max(w["score"], r["score"])
    for w in by.values():
        best_row = max(w["views"], key=lambda r: r["score"])
        w["components"] = dict(best_row["components"])
        wv = [by_id[r["view_id"]] for r in w["views"] if r["view_id"] in by_id]
        sup = concept_support(cids or [], wv)
        w["concept_support"] = sup
        multi = [c for c, lg in sup.items()
                 if len({VW.norm(VW.low(it["surface"])) for its in lg.values()
                         for it in its}) >= 2]
        w["aligned_concepts"] = sorted(multi)
        w["anchor_languages"] = sorted({lg for cid in sup for lg in sup[cid]})
        if multi:
            bonus = 6.0 * min(len(multi), 3)
            w["score"] += bonus
            w["components"]["bilingual_term_evidence"] = bonus
        best = max(w["views"], key=lambda r: r["score"])
        if best["language"] != qlang:
            w["score"] += 4.0
            w["components"]["cross_language"] = 4.0
        if len([x for x in w["views"] if not x["duplicate_of"]]) >= 2:
            w["score"] += 1.0
            w["components"]["multi_view"] = 1.0
        w["score"] = round(w["score"], 2)
        w["best_view"] = best["view_id"]
        w["doi"] = next((v["doi"] for v in views if v["work_id"] == w["work_id"] and v.get("doi")), None)
        w["title"] = next((v["title"] for v in views if v["work_id"] == w["work_id"] and v.get("title")), "")
    return sorted(by.values(), key=lambda x: (-x["score"], x["work_id"]))


LANG_WORDS = {"pt": ("português", "portugues", "portuguese", "portugués"),
              "en": ("inglês", "ingles", "english"),
              "es": ("espanhol", "español", "spanish", "castellano"),
              "de": ("alemão", "aleman", "german", "deutsch"),
              "fr": ("francês", "frances", "french", "français"),
              "zh": ("中文", "汉语", "漢語", "chinês", "chinese"),
              "ja": ("日本語", "japonês", "japanese")}
ORIG_WORDS = ("original", "origina", "原文", "原版", "as published", "first published")


def lang_mentions(text):
    """Languages the question names explicitly - the requested target language signal."""
    t = " " + VW.low(text) + " "
    out = [lg for lg, ws in LANG_WORDS.items() if any(VW.low(w) in t for w in ws)]
    return sorted(set(out))


def wants_original(text):
    return any(VW.low(w) in VW.low(text) for w in ORIG_WORDS)


def pick_primary(view_rows, views_by_id, qlang, prefer=None, want_original=False):
    cand = [r for r in view_rows if not r["duplicate_of"]] or view_rows

    def key(r):
        v = views_by_id[r["view_id"]]
        lang = 0 if (prefer and v["language"] in prefer) else (1 if v["language"] != qlang else 2)
        ver = 0 if (want_original and v["version"] == "original") else (
            0 if v["version"] in ("publisher_translation", "original") else 1)
        return (lang, 0 if v["doc_type"] == "full_body" else 1, ver, -r["score"])
    return sorted(cand, key=key)[0]


def queries_for(feats, qlang, target_langs, views):
    out, qual = {}, {}
    for c in feats["concepts"]:
        for lg, surfs in GLOSS[c["cid"]]["forms"].items():
            qual.setdefault(lg, set()).update(surfs)
    for lg in sorted(set(target_langs) | {qlang}):
        parts = sorted(qual.get(lg, set())) or feats["terms"][:6] or ["*"]
        q = "(%s)" % " OR ".join('"%s"' % p for p in parts[:8])
        if feats["years"]:
            q += " AND (%s)" % " OR ".join("year:%s" % y for y in feats["years"])
        if feats["doi"]:
            q += " AND doi:%s" % feats["doi"]
        out[lg] = {"language": lg, "query": q, "terms": parts[:8],
                   "template": "title+abstract+keywords[%s]" % lg,
                   "concept_ids": sorted({c["cid"] for c in feats["concepts"]})}
    return out


# ------------------------------------------------------------------ evidence
def best_sentence(view, cids, terms):
    units = VW.units(view)
    scored = []
    for u in units:
        t = VW.norm(VW.low(u["quote"]))
        sc = 0
        for cid in cids:
            if any(VW.norm(VW.low(s)) in t for s in sum(GLOSS[cid]["forms"].values(), []) if s):
                sc += 2
        sc += sum(1 for w in terms[:12] if w in t)
        if sc:
            scored.append((sc, len(t), u))
    if not scored:
        return units[0] if units else None
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2]


def term_pairs(support, primary, qlang):
    """Align the same concept across languages: source-side surface vs primary-view surface."""
    pairs = []
    for cid, langs in support.items():
        if len(pairs) >= 3:
            break
        tgt_items = langs.get(primary["language"]) or []
        other = [(lg, it) for lg, its in sorted(langs.items()) if lg != primary["language"]
                 for it in its]
        if not tgt_items or not other:
            continue
        src_lang, src = sorted(other, key=lambda x: (x[0] != qlang,))[0]
        pairs.append({"concept": GLOSS[cid]["en"] if cid in GLOSS else cid, "concept_id": cid,
                      "source_lang": src_lang, "source_term": src["surface"],
                      "source_quote": src["surface"], "source_locator": src["locator"],
                      "target_lang": primary["language"], "target_term": tgt_items[0]["surface"],
                      "target_quote": tgt_items[0]["surface"],
                      "target_locator": tgt_items[0]["locator"],
                      "glossary": "builtin:%s" % cid,
                      "verified": bool(tgt_items[0]["verified"])})
    return pairs


# ------------------------------------------------------------------ cards
def _dlang(q, draft, key=("source_lang", "source_language", "query_language")):
    for it in (draft or {}).get("questions") or []:
        if isinstance(it, dict) and it.get("question_id") == q["question_id"]:
            v = VW.first_str(it, key)
            if v:
                return VW.low(v)[:5]
    return None


def _draft_match(draft, qid):
    for m in (draft or {}).get("matches") or []:
        if isinstance(m, dict) and str(m.get("question_id")) == str(qid):
            return m
    return None


def _apply_draft(card, dm, views_by_id, okmap):
    vid = VW.first_str(dm, ("view_id", "view", "primary_view"))
    v = views_by_id.get(vid) if vid else None
    if not v:
        card["notes"].append("draft match 指向不存在的 view_id=%s，已退回机器候选" % vid)
        return card
    ev = dm.get("evidence") if isinstance(dm.get("evidence"), dict) else {}
    pairs = []
    for p in ev.get("term_pairs") or []:
        if not isinstance(p, dict):
            continue
        tq = p.get("target_quote") or p.get("quote")
        pairs.append({"concept": p.get("concept"), "concept_id": p.get("concept_id"),
                      "source_lang": p.get("source_lang") or card["source_language"],
                      "source_term": p.get("source") or p.get("source_term") or p.get("term"),
                      "source_quote": p.get("source_quote"),
                      "source_locator": p.get("source_locator"),
                      "target_lang": p.get("target_lang") or v["language"],
                      "target_term": p.get("target") or p.get("target_term"),
                      "target_quote": tq,
                      "target_locator": p.get("target_locator") or p.get("locator"),
                      "glossary": p.get("glossary") or "agent_draft",
                      "verified": bool(okmap.get(VW.norm(tq or "")))})
    card["target_view"] = {"view_id": v["view_id"], "work_id": v["work_id"], "doi": v.get("doi"),
                           "title": v.get("title"), "language": v["language"],
                           "version": v["version"], "doc_type": v["doc_type"],
                           "locator": v["locator"],
                           "basis": "agent_draft:" + (VW.first_str(dm, ("basis", "reason")) or
                                                      "operator read materials")}
    quote = ev.get("quote") or dm.get("quote")
    card["evidence_chain"] = {
        "doi_anchor": ({"doi": v["doi"], "quote": v["doi"], "locator": v["locator"],
                        "verified": True} if v.get("doi") else None),
        "title_anchor": ({"quote": VW.norm(v.get("title") or "")[:220], "locator": v["locator"],
                          "verified": bool(VW.find_quote([v], v.get("title") or ""))}
                         if v.get("title") else None),
        "term_alignment": pairs,
        "body_quote": ({"quote": VW.norm(quote),
                        "locator": ev.get("locator") or dm.get("locator") or v["locator"],
                        "verified": bool(okmap.get(VW.norm(quote or ""))),
                        "view_id": v["view_id"], "language": v["language"]} if quote else None),
    }
    card["false_positive_check"] = VF.backtranslate(pairs, GLOSS)
    fp = dm.get("false_positive") if isinstance(dm.get("false_positive"), dict) else {}
    if fp:
        card["false_positive_check"].update({
            "method": fp.get("method") or card["false_positive_check"]["method"],
            "verdict": fp.get("verdict") or card["false_positive_check"]["verdict"],
            "agent_basis": fp.get("basis")})
    card["dedup"] = {"counted_as": "work:%s" % v["work_id"],
                     "duplicate_views_excluded": [x["view_id"] for x in views_by_id.values()
                                                  if x["work_id"] == v["work_id"] and
                                                  x.get("duplicate_of")],
                     "same_work_views": [x["view_id"] for x in views_by_id.values()
                                         if x["work_id"] == v["work_id"]]}
    card["counted_hits"] = 1
    card["confidence"] = VW.first_str(dm, ("confidence",)) or "medium"
    card["status"] = VW.first_str(dm, ("status",)) or "found"
    card["agent_authored"] = True
    if isinstance(dm.get("note"), str):
        card["notes"].append(dm["note"][:300])
    return card


def build_card(q, views, views_by_id, rows, works, draft, okmap):
    qf = q_features(q["text"])
    qf["qid"] = q["question_id"]
    qlang = _dlang(q, draft) or VW.detect_lang(q["text"])["detected"]
    targets = _dlang(q, draft, ("target_langs", "target_languages"))
    if not targets:
        tl = []
        for it in (draft or {}).get("questions") or []:
            if isinstance(it, dict) and it.get("question_id") == q["question_id"]:
                tl = it.get("target_langs") or it.get("target_languages") or []
        targets = [VW.low(str(x))[:5] for x in tl] if isinstance(tl, list) else []
    if not targets:
        targets = lang_mentions(q["text"]) or sorted(
            {v["language"] for v in views if v["language"] not in (qlang, "und")}) or ["en"]
    basis = "agent_draft" if _dlang(q, draft) else (
        "question_text_detection(%s)" % VW.detect_lang(q["text"])["confidence"])
    card = {"question_id": q["question_id"], "question_text": q["text"],
            "question_locator": q["locator"], "source_language": qlang,
            "source_language_basis": basis, "target_languages": targets,
            "queries_by_lang": queries_for(qf, qlang, targets, views), "target_view": None,
            "evidence_chain": {"doi_anchor": None, "title_anchor": None, "term_alignment": [],
                               "body_quote": None},
            "false_positive_check": {"method": "glossary_inverse_backtranslation(offline)",
                                     "service": "none", "pairs_checked": 0, "passed": 0,
                                     "risks": [], "verdict": "not_applicable"},
            "dedup": {"counted_as": None, "duplicate_views_excluded": [], "same_work_views": []},
            "counted_hits": 0, "confidence": "low", "status": "not_found", "misses": None,
            "agent_authored": False, "notes": []}
    dm = _draft_match(draft, q["question_id"])
    if dm:
        card = _apply_draft(card, dm, views_by_id, okmap)
        if card["target_view"]:
            return card
    best = works[0] if works else None
    if not best or best["score"] < MIN_SCORE:
        card["misses"] = {"reason": "no_work_above_threshold", "threshold": MIN_SCORE,
                          "best_score": best["score"] if best else 0,
                          "searched_languages": sorted({v["language"] for v in views}),
                          "searched_terms": [c["surface"] for c in qf["concepts"]][:10] or
                                            qf["terms"][:10],
                          "views_examined": len(views),
                          "missing_objects": [] if views else ["views/materials"],
                          "next_action": "放宽语种或术语（同义/缩写/音译），或确认材料是否缺该文献"}
        return card
    wv = [views_by_id[r["view_id"]] for r in best["views"] if r["view_id"] in views_by_id]
    named = lang_mentions(q["text"])
    prim = views_by_id[pick_primary(best["views"], views_by_id, qlang, named,
                                    wants_original(q["text"]))["view_id"]]
    cids = (best.get("aligned_concepts") or
            sorted({h["cid"] for r in best["views"] for h in r["concept_hits"]}) or
            [c["cid"] for c in qf["concepts"]])
    pairs = term_pairs(best.get("concept_support") or {}, prim, qlang)
    body = best_sentence(prim, cids, qf["terms"])
    title = VW.norm(prim.get("title") or "")[:220]
    card["target_view"] = {"view_id": prim["view_id"], "work_id": best["work_id"],
                           "doi": prim.get("doi") or best.get("doi"),
                           "title": title or best.get("title"), "language": prim["language"],
                           "version": prim["version"], "doc_type": prim["doc_type"],
                           "locator": prim["locator"],
                           "basis": "machine_candidate(score=%.1f, anchors=%s)"
                                    % (best["score"], ",".join(best["anchor_languages"]))}
    card["evidence_chain"] = {
        "doi_anchor": ({"doi": prim["doi"], "quote": prim["doi"], "locator": prim["locator"],
                        "verified": True} if prim.get("doi") else None),
        "title_anchor": ({"quote": title, "locator": prim["locator"],
                          "verified": bool(VW.find_quote([prim], title))} if title else None),
        "term_alignment": pairs,
        "body_quote": ({"quote": body["quote"], "locator": body["locator"],
                        "verified": bool(VW.find_quote([prim], body["quote"])),
                        "view_id": prim["view_id"], "language": prim["language"]} if body else None),
    }
    card["false_positive_check"] = VF.backtranslate(pairs, GLOSS)
    card["dedup"] = {"counted_as": "work:%s" % best["work_id"],
                     "duplicate_views_excluded": [v["view_id"] for v in views
                                                  if v["work_id"] == best["work_id"] and
                                                  v.get("duplicate_of")],
                     "same_work_views": [v["view_id"] for v in wv]}
    card["counted_hits"] = 1
    bq = card["evidence_chain"]["body_quote"]
    if (best["components"].get("doi") or len(best["anchor_languages"]) >= 2) and pairs and \
            bq and bq["verified"]:
        card["confidence"] = "high"
    elif pairs:
        card["confidence"] = "medium"
    card["status"] = "found"
    if len(works) > 1 and works[1]["score"] >= best["score"] - 1.0:
        card["status"] = "ambiguous"
        card["notes"].append("次优 work 分数接近（%s=%.1f / %s=%.1f），需人工确认"
                             % (best["work_id"], best["score"], works[1]["work_id"],
                                works[1]["score"]))
    return card


def apply_view_labels(views, draft):
    labels = {}
    for it in (draft or {}).get("view_labels") or []:
        if isinstance(it, dict):
            vid = VW.first_str(it, ("view_id", "id"))
            if vid:
                labels[vid] = it
    for v in views:
        lb = labels.get(v["view_id"])
        if not lb:
            continue
        for src, dst in (("language", "language"), ("version", "version"),
                         ("duplicate_of", "duplicate_of"), ("work_id", "work_id"),
                         ("doc_type", "doc_type")):
            val = VW.first_str(lb, (src,))
            if not val or val.lower() in ("null", "none", "-"):
                continue
            if v.get(dst) and str(v[dst]).lower() != val.lower():
                v.setdefault("label_conflicts", []).append(
                    {"field": dst, "script": str(v[dst]), "agent": val,
                     "basis": VW.first_str(lb, ("basis",)) or "agent_draft"})
            v[dst] = VW.low(val)[:5] if dst == "language" else val
        v["label_source"] = "agent_draft"
    return views
