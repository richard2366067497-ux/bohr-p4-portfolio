#!/usr/bin/env python3
"""writing-15 | audit layer: six computed consistency ledgers, impact back-links,
draft validation (shared with the fault probes).

Imported by main.py. Standard library only; returns data, never exits.
"""
from __future__ import annotations

import re

from ledger import (CATEGORIES, SEVERITIES, _STOP, norm, sha, tokens, number_keys, find_quote,
                    resolve_locator, resolve_target, by_id)

PAIR_EN = re.compile(r"([A-Za-z][A-Za-z0-9\-]*(?:\s+[A-Za-z][A-Za-z0-9\-]*){0,4})\s*[（(]\s*([A-Z][A-Z0-9\-]{1,9})\s*[)）]")
PAIR_REV = re.compile(r"\b([A-Z][A-Z0-9\-]{1,9})\s*[（(]\s*([A-Za-z][A-Za-z0-9\-]*(?:\s+[A-Za-z][A-Za-z0-9\-]*){0,4})\s*[)）]")
PAIR_ZH = re.compile(r"([\u4e00-\u9fff]{2,14})\s*[（(]\s*([A-Z][A-Z0-9\-]{1,9})\s*[)）]")
ABBR_USE = re.compile(r"\b([A-Z]{2,9})\b")
SYM_EN = re.compile(r"[Ww]here\s+([A-Za-z\u03b1-\u03c9\u0391-\u03a9][A-Za-z0-9]?)\s+"
                    r"(?:is|denotes|represents|stands for)\s+([^.;\n]{3,140})")
SYM_ZH = re.compile(r"式中[，,]?\s*([A-Za-z\u03b1-\u03c9\u0391-\u03a9][A-Za-z0-9]?)\s*"
                    r"(?:为|表示|是)\s*([^。；\n]{2,90})")
DEF_EN = re.compile(r"([A-Za-z][A-Za-z\-]{2,30}(?:\s+[A-Za-z][A-Za-z\-]{2,30}){0,2})\s+"
                    r"(?:is|are)\s+defined\s+as\s+([^.;\n]{4,160})", re.I)
DEF_ZH = re.compile(r"([\u4e00-\u9fffA-Za-z]{2,18})\s*(?:定义为|是指|称为|记作)\s*([^。；\n]{2,120})")
FIG = re.compile(r"(?:Figure|Fig\.?|FIGURE|图)\s*(\d{1,3})")
TAB = re.compile(r"(?:Table|TABLE|表)\s*(\d{1,3})")
EQ = re.compile(r"(?:Equation|Eq\.?|式|公式)\s*[（(]?\s*(\d{1,3})\s*[)）]?")
CAPTION = re.compile(r"^\s*(?:Figure|Fig\.?|Table|图|表)\s*(\d{1,3})\s*[\.:：]")
CITE_NUM = re.compile(r"\[(\d{1,3}(?:\s*[,\-–]\s*\d{1,3})*)\]")
CITE_AUTH = re.compile(r"\(([A-Z][A-Za-z\-']+)(?:\s+et\s+al\.)?,\s*((?:19|20)\d{2})\)")
BIB_HEAD = re.compile(r"^\s*(references|reference list|bibliography|参考文献|文献)\s*$", re.I)
BIB_ENTRY = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[\.\)])\s+\S")
PLACEHOLDER = re.compile(r"(\[\?+\]|\?\?|TODO|TBD|XXX|待补|待引|\[citation needed\])")
CUE = re.compile(r"(significant|significantly|increase|decrease|improv|reduc|correlat|higher|lower|"
                 r"greater|smaller|enhanc|strengthen|表明|说明|显示|显著|提高|降低|增强|减弱|优于|"
                 r"因此|综上|consequently)", re.I)
NEG = re.compile(r"(\bno\b|\bnot\b|\bnone\b|\bnever\b|\bwithout\b|\bdid not\b|\bdoes not\b|"
                 r"\bcannot\b|\bneither\b|未|没有|不|无|并未)", re.I)
UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|MPa|GPa|kPa|Pa|mm/min|mm/s|mm·min|mm min|mm|cm|µm|um|nm|"
                  r"km|kg|mg|g|mL|L|min|s|h|Hz|kHz|MHz|rpm|°C|K|N|kN|vol%|wt%|at%)", re.I)

def _unit_canon(u: str) -> str:
    u = (u or "").replace("−", "-").replace("·", "/").replace(" ", "")
    u = u.replace("min-1", "/min").replace("s-1", "/s")
    return {"um": "µm", "min-1": "/min"}.get(u, u)

def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z(])|\n+", text or "")
    return [p.strip() for p in parts if p and p.strip()]

def _find(cat, sev, la, qa, lb="", qb="", statement="", owner="author", basis="computed", note=""):
    return {"category": cat, "severity": sev, "locator_a": la, "quote_a": qa,
            "locator_b": lb, "quote_b": qb, "statement": statement,
            "decision_owner": owner, "basis": basis, "note": note}

def scan_consistency(ix: dict, cap: int = 80) -> dict:
    led = {k: [] for k in ("terms", "symbols", "definitions", "numbering", "citations", "claims")}
    findings = []
    blocks = [b for b in ix["blocks"] if b["kind"] != "heading"]
    exp = {}

    def _trim(words):
        toks = str(words).split()
        while len(toks) > 1 and toks[0].lower() in _STOP:
            toks.pop(0)
        return " ".join(toks[-5:]) if len(toks) > 5 else " ".join(toks)

    for b in blocks:
        for rx, rev in ((PAIR_EN, False), (PAIR_REV, True), (PAIR_ZH, False)):
            for m in rx.finditer(b["body"]):
                ab = (m.group(2) if not rev else m.group(1)).upper()
                expansion = (m.group(1) if not rev else m.group(2)).strip()
                exp.setdefault(ab, []).append({"expansion": _trim(expansion), "locator": b["loc"],
                                               "quote": m.group(0)[:160], "bid": b["bid"]})
    for ab, rows in sorted(exp.items()):
        distinct = {}
        for r in rows:
            distinct.setdefault(norm(r["expansion"]).lower(), r)
        led["terms"].append({"abbrev": ab, "expansions": [r["expansion"] for r in distinct.values()],
                             "uses": sum(len(ABBR_USE.findall(b["body"])) for b in blocks
                                         if re.search(r"\b%s\b" % re.escape(ab), b["body"])),
                             "defined_at": rows[0]["locator"], "instances": len(rows)})
        if len(distinct) > 1:
            a, c = list(distinct.values())[:2]
            findings.append(_find("term", "high", a["locator"], a["quote"], c["locator"], c["quote"],
                                  "same abbreviation '%s' carries two different expansions" % ab,
                                  note="keep one expansion or split the abbreviation"))
    by_exp = {}
    for b in blocks:
        for rx in (PAIR_EN, PAIR_ZH):
            for m in rx.finditer(b["body"]):
                by_exp.setdefault(norm(m.group(1)).lower(), set()).add(m.group(2).upper())
    for e, abs_ in by_exp.items():
        if len(abs_) > 1:
            b = next(x for x in blocks if e in norm(x["body"]).lower())
            findings.append(_find("term", "medium", b["loc"], b["body"][:120], "", "",
                                  "one expansion is abbreviated two ways: %s" % ", ".join(sorted(abs_)),
                                  note="unify the abbreviation in the terminology table"))
    sym = {}
    for b in blocks:
        for rx in (SYM_EN, SYM_ZH):
            for m in rx.finditer(b["body"]):
                sym.setdefault(m.group(1), []).append({"meaning": m.group(2).strip()[:140],
                                                       "locator": b["loc"], "quote": m.group(0)[:160]})
    for s, rows in sorted(sym.items()):
        meanings = {norm(r["meaning"]).lower() for r in rows}
        led["symbols"].append({"symbol": s, "meanings": sorted(meanings)[:4],
                               "defined_at": [r["locator"] for r in rows][:4]})
        if len(meanings) > 1:
            findings.append(_find("symbol", "high", rows[0]["locator"], rows[0]["quote"],
                                  rows[1]["locator"], rows[1]["quote"],
                                  "symbol '%s' is defined with %d different meanings" % (s, len(meanings)),
                                  note="rename one symbol or add a symbol table entry"))
    defs = {}
    for b in blocks:
        for rx in (DEF_EN, DEF_ZH):
            for m in rx.finditer(b["body"]):
                defs.setdefault(norm(m.group(1)).lower(), []).append(
                    {"term": m.group(1), "text": m.group(2).strip()[:160], "locator": b["loc"],
                     "quote": m.group(0)[:180]})
    for term, rows in sorted(defs.items()):
        led["definitions"].append({"term": rows[0]["term"], "occurrences": len(rows),
                                   "locators": [r["locator"] for r in rows][:5],
                                   "distinct_wording": len({norm(r["text"]).lower() for r in rows})})
        if len(rows) > 1 and len({norm(r["text"]).lower() for r in rows}) > 1:
            findings.append(_find("definition", "medium", rows[0]["locator"], rows[0]["quote"],
                                  rows[1]["locator"], rows[1]["quote"],
                                  "term '%s' is defined twice with different wording" % rows[0]["term"],
                                  note="define once and cross-reference"))
    refs = {"figure": {}, "table": {}, "equation": {}}
    caps = {"figure": {}, "table": {}}
    for b in blocks:
        for fam, rx in (("figure", FIG), ("table", TAB), ("equation", EQ)):
            for m in rx.finditer(b["body"]):
                refs[fam].setdefault(int(m.group(1)), []).append(b["loc"])
        for ln in b["body"].splitlines():
            mc = CAPTION.match(ln)
            if mc:
                fam = "figure" if re.match(r"^\s*(?:Figure|Fig|图)", ln) else "table"
                caps[fam].setdefault(int(mc.group(1)), []).append(b["loc"])
    for fam in ("figure", "table"):
        r, c = set(refs[fam]), set(caps[fam])
        led["numbering"].append({"family": fam, "references": sorted(r), "captions": sorted(c),
                                 "duplicate_captions": sorted({n for n, v in caps[fam].items() if len(v) > 1}),
                                 "gaps": [n for n in range(1, max(c) + 1) if n not in c] if c else [],
                                 "referenced_without_caption": sorted(r - c) if c else []})
        for n, locs in sorted(caps[fam].items()):
            if len(locs) > 1:
                findings.append(_find("numbering", "high", locs[0], "%s %d caption" % (fam, n),
                                      locs[1], "%s %d caption" % (fam, n),
                                      "%s %d has two captions" % (fam, n)))
        for n in sorted(r - c)[:6] if c else []:
            findings.append(_find("numbering", "medium", refs[fam][n][0], "%s %d" % (fam, n),
                                  "", "", "%s %d is cited but has no caption" % (fam, n)))
        gap = [n for n in range(1, max(c) + 1) if n not in c] if c else []
        if gap:
            findings.append(_find("numbering", "low", "", "", "", "",
                                  "%s numbering has gaps: %s" % (fam, gap[:8])))
    cited, listed, placeholders = set(), set(), []
    bib_on = False
    for b in blocks:
        if BIB_HEAD.match(b["body"]):
            bib_on = True
            continue
        if bib_on:
            me = BIB_ENTRY.match(b["body"])
            if me:
                listed.add(int(me.group(1) or me.group(2)))
                continue
            if b["kind"] == "heading" or len(b["body"]) > 400:
                bib_on = False
        for m in CITE_NUM.finditer(b["body"]):
            for part in re.split(r",", m.group(1)):
                part = part.strip()
                if re.match(r"^\d+\s*[\-–]\s*\d+$", part):
                    a, c = re.split(r"[\-–]", part)
                    try:
                        cited.update(range(int(a), int(c) + 1))
                    except ValueError:
                        pass
                elif part.isdigit():
                    cited.add(int(part))
        if PLACEHOLDER.search(b["body"]):
            hit = PLACEHOLDER.search(b["body"])
            placeholders.append({"locator": b["loc"], "token": hit.group(1), "quote": b["body"][:120]})
    led["citations"].append({"in_text_numbers": sorted(cited), "listed_numbers": sorted(listed),
                             "cited_not_listed": sorted(cited - listed) if listed else [],
                             "listed_not_cited": sorted(listed - cited) if cited else [],
                             "bibliography_found": bib_on, "placeholders": placeholders[:8]})
    if not bib_on:
        findings.append(_find("citation", "medium", "", "", "", "",
                              "no bibliography/reference-list section found; citation completeness "
                              "cannot be verified from the supplied material",
                              owner="human", note="supply the reference list or confirm it is out of scope"))
    if listed:
        for n in sorted(cited - listed)[:6]:
            findings.append(_find("citation", "high", "", "[%d]" % n, "", "",
                                  "citation [%d] has no entry in the reference list" % n))
        for n in sorted(listed - cited)[:6]:
            findings.append(_find("citation", "low", "", "[%d]" % n, "", "",
                                  "reference [%d] is listed but never cited" % n))
    for p in placeholders[:4]:
        findings.append(_find("citation", "high", p["locator"], p["quote"], "", "",
                              "placeholder citation token '%s' left in the text" % p["token"]))
    claims = []
    for b in blocks:
        for s in _sentences(b["body"]):
            if len(s) < 25 or not CUE.search(s):
                continue
            claims.append({"locator": b["loc"], "material": b["material"], "sentence": s[:260],
                           "polarity": "negative" if NEG.search(s) else "positive",
                           "has_quantity": bool(UNIT.search(s)), "tokens": set(tokens(s))})
    led["claims"] = [{"locator": c["locator"], "polarity": c["polarity"],
                      "has_quantity": c["has_quantity"], "sentence": c["sentence"]} for c in claims[:cap]]
    seen, pairs = set(), 0
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            if pairs > 4000:
                break
            a, c = claims[i], claims[j]
            if a["material"] == c["material"] or a["polarity"] == c["polarity"]:
                continue
            ta, tc = a["tokens"], c["tokens"]
            if not ta or not tc:
                continue
            inter = len(ta & tc)
            if inter < 4:
                continue
            jac = inter / float(len(ta | tc) or 1)
            if jac < 0.45:
                continue
            key = (a["locator"], c["locator"])
            if key in seen:
                continue
            seen.add(key)
            pairs += 1
            findings.append(_find("claim", "medium", a["locator"], a["sentence"],
                                  c["locator"], c["sentence"],
                                  "two chapters state opposite polarity about the same subject "
                                  "(overlap %.2f); both sides kept, author decides" % jac,
                                  owner="author", note="check whether the scope/condition differs"))
            if pairs >= 12:
                break
    forms = {}
    for b in blocks:
        for m in UNIT.finditer(b["body"]):
            forms.setdefault(_unit_canon(m.group(2)), set()).add(m.group(2))
    for canon, variants in sorted(forms.items()):
        if len(variants) > 1:
            b = next((x for x in blocks if any(v in x["body"] for v in variants)), blocks[0])
            findings.append(_find("unit", "medium", b["loc"], b["body"][:120], "", "",
                                  "unit '%s' is written %d ways: %s" % (canon, len(variants),
                                                                       ", ".join(sorted(variants))),
                                  note="do not silently convert; confirm the intended unit"))
    return {"ledgers": led, "findings": findings,
            "counts": {k: len(v) for k, v in led.items()},
            "finding_count": len(findings),
            "basis_note": "computed rows are candidates for judgement, not scientific verdicts"}

def _symbols_in(text: str) -> set:
    return set(re.findall(r"(?<![\w])[A-Za-z]\s*=", text or "")) | set(re.findall(r"\b[A-Z]{2,9}\b", text or ""))

def impact_map(ix: dict, block: dict, maxn: int = 5) -> list:
    base = set(tokens(block["body"]))
    syms = _symbols_in(block["body"])
    out = []
    for b in ix["blocks"]:
        if b["bid"] == block["bid"] or b["kind"] == "heading":
            continue
        t = set(tokens(b["body"]))
        shared = base & t
        sym_shared = syms & _symbols_in(b["body"])
        if len(shared) < 2 and not sym_shared:
            continue
        if len(shared) < 3 and not sym_shared:
            continue
        score = len(shared) + 2 * len(sym_shared) + (1 if b["material"] != block["material"] else 0)
        out.append({"locator": b["loc"], "material": b["rel"], "score": score,
                    "shared_terms": sorted(shared)[:6], "shared_symbols": sorted(sym_shared)[:4]})
    out.sort(key=lambda x: -x["score"])
    return out[:maxn]

def _ann_text(a: dict) -> str:
    return str(a.get("annotation") or a.get("text") or a.get("note_text") or "").strip()

def _ann_anchor(a: dict) -> str:
    return str(a.get("anchor_quote") or a.get("anchor") or a.get("original_quote") or "").strip()

def validate_draft(ix: dict, draft: dict, targets: list) -> dict:
    draft = draft if isinstance(draft, dict) else {}
    tids = [str(t["target_id"]) for t in targets]
    corpus_nums = set()
    for b in ix["blocks"]:
        corpus_nums |= number_keys(b["body"])
    items, accepted, rejected = [], [], []
    used = {}
    for raw in draft.get("annotations") or []:
        a = raw if isinstance(raw, dict) else {}
        reasons, high = [], 0
        tid = str(a.get("target_id") or a.get("target") or "").strip()
        anchor = _ann_anchor(a)
        text = _ann_text(a)
        if not tid or not text:
            items.append({"kind": "annotation", "target_id": tid, "status": "reject",
                          "reasons": ["missing target_id or annotation text"]})
            rejected.append({"target_id": tid, "reason": "missing target_id or annotation text"})
            continue
        if tids and tid not in tids:
            items.append({"kind": "annotation", "target_id": tid, "status": "reject",
                          "reasons": ["target_id not in the workorder target_ids"]})
            rejected.append({"target_id": tid, "reason": "target not in workorder"})
            continue
        res = resolve_target(ix, tid)
        blk = res["block"]
        if blk is None:
            items.append({"kind": "annotation", "target_id": tid, "status": "reject",
                          "reasons": ["target not locatable: " + res["note"]]})
            rejected.append({"target_id": tid, "reason": "target not locatable"})
            continue
        bind = find_quote(ix, anchor, blk)
        if not anchor:
            reasons.append("anchor_quote missing")
            high += 1
        elif not bind["ok"] or bind["where"] != "block":
            reasons.append("anchor_quote is not verbatim inside the target block (found: %s)" % bind["where"])
            high += 1
        loc = str(a.get("locator") or "").strip()
        if loc:
            lb = resolve_locator(ix, loc)
            if lb is None:
                reasons.append("locator does not resolve; the true locator is %s" % blk["loc"])
            elif lb["bid"] != blk["bid"]:
                reasons.append("locator points at a different block (%s)" % lb["loc"])
                high += 1
        if len(text) < 25:
            reasons.append("annotation shorter than 25 characters")
            high += 1
        elif len(text) < 60:
            reasons.append("annotation shorter than 60 characters (likely too thin)")
        novel = number_keys(text) - corpus_nums
        if novel:
            ref_ctx = re.compile(r"(§|section|chapter|figure|fig\.|table|eq|step|第|节|章|图|表|式)", re.I)
            bad = []
            for n in novel:
                hits = [text[max(0, m.start() - 16):m.end() + 16]
                        for m in re.finditer(r"(?<![\w.])" + re.escape(n) + r"(?![\w])", text)]
                if not hits or not all(ref_ctx.search(h) for h in hits):
                    bad.append(n)
            if bad:
                reasons.append("text introduces numbers absent from the material: %s"
                               % ", ".join(sorted(bad)[:5]))
                high += 1
        terms = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)}
        if len(terms) >= 5:
            corpus = set()
            for b in ix["blocks"]:
                corpus |= {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", b["body"])}
            ground = len(terms & corpus) / float(len(terms))
            if ground < 0.40:
                reasons.append("low lexical grounding (%.2f) - risks generic advice" % ground)
        for ev in a.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            q = str(ev.get("quote") or ev.get("text") or "").strip()
            if not q:
                reasons.append("evidence entry without a quote")
                continue
            fq = find_quote(ix, q)
            if not fq["ok"]:
                reasons.append("evidence quote not found in the material: %r" % q[:40])
                high += 1
            elif fq["where"] != "block":
                ev_loc = str(ev.get("locator") or "").strip()
                if ev_loc:
                    lb = resolve_locator(ix, ev_loc)
                    if lb is None or lb["bid"] != (fq["block"] or {}).get("bid"):
                        reasons.append("evidence quote is not inside its stated locator")
        if tid in used:
            reasons.append("duplicate annotation for the same target")
        used[tid] = True
        status = "reject" if high else ("warn" if reasons else "accept")
        rec = {"kind": "annotation", "target_id": tid, "status": status, "reasons": reasons,
               "locator": blk["loc"], "block_id": blk["bid"], "resolution": res["resolution"],
               "annotation_id": a.get("annotation_id") or "EA-%02d" % (len(items) + 1),
               "text": text, "anchor_quote": anchor, "evidence": a.get("evidence") or [],
               "rationale": a.get("rationale") or "", "uncertainty": a.get("uncertainty") or "",
               "source": a}
        items.append(rec)
        if status == "reject":
            rejected.append({"target_id": tid, "reason": "; ".join(reasons) or "rejected"})
        else:
            accepted.append(rec)
    f_acc = []
    for raw in draft.get("findings") or []:
        f = raw if isinstance(raw, dict) else {}
        reasons, high = [], 0
        cat = str(f.get("category") or "").strip().lower()
        if cat not in CATEGORIES:
            reasons.append("category '%s' not in %s" % (cat, "/".join(CATEGORIES)))
            high += 1
        qa = str(f.get("quote_a") or "").strip()
        la = str(f.get("locator_a") or "").strip()
        if not qa and not la:
            reasons.append("finding has neither quote_a nor locator_a")
            high += 1
        if qa:
            fq = find_quote(ix, qa)
            if not fq["ok"]:
                reasons.append("quote_a not found verbatim")
                high += 1
            elif la:
                lb = resolve_locator(ix, la)
                if lb is None:
                    reasons.append("locator_a does not resolve")
                elif fq["block"] and lb["bid"] != fq["block"]["bid"]:
                    reasons.append("quote_a is not inside locator_a")
                    high += 1
        qb = str(f.get("quote_b") or "").strip()
        lb2 = str(f.get("locator_b") or "").strip()
        if qb:
            fq = find_quote(ix, qb)
            if not fq["ok"]:
                reasons.append("quote_b not found verbatim")
                high += 1
            elif lb2:
                lb = resolve_locator(ix, lb2)
                if lb is None:
                    reasons.append("locator_b does not resolve")
                elif fq["block"] and lb["bid"] != fq["block"]["bid"]:
                    reasons.append("quote_b is not inside locator_b")
                    high += 1
        st = str(f.get("statement") or "").strip()
        if len(st) < 15:
            reasons.append("statement shorter than 15 characters")
        sev = str(f.get("severity") or "medium").lower()
        if sev not in SEVERITIES:
            reasons.append("severity '%s' not in high/medium/low" % sev)
        status = "reject" if high else ("warn" if reasons else "accept")
        rec = {"kind": "finding", "status": status, "reasons": reasons, "category": cat,
               "severity": sev, "locator_a": la, "quote_a": qa, "locator_b": lb2, "quote_b": qb,
               "statement": st, "decision_owner": f.get("decision_owner") or "author",
               "note": f.get("note") or "", "basis": "agent_review",
               "finding_id": f.get("finding_id") or "FR-%02d" % (len(f_acc) + 1)}
        items.append(rec)
        if status != "reject":
            f_acc.append(rec)
    covered = sorted({r["target_id"] for r in accepted})
    cats = sorted({r["category"] for r in f_acc})
    summary = {"items": len(items), "accepted": len(accepted), "rejected": len(rejected),
               "high": sum(1 for r in items if r["status"] == "reject"),
               "warn": sum(1 for r in items if r["status"] == "warn"),
               "findings_accepted": len(f_acc),
               "targets_total": len(tids), "targets_covered": len(covered),
               "targets_missing": [t for t in tids if t not in covered],
               "categories_covered": cats,
               "categories_missing": [c for c in CATEGORIES if c not in cats]}
    return {"items": items, "accepted": accepted, "findings": f_acc, "rejected": rejected,
            "summary": summary, "coverage_targets": covered}

_LISTISH = re.compile(r"(fact|evidence|map|log|record|list|items|annotations|claims?|findings|sources|"
                      r"uncertain|pending|changes|receipt|consisten|coverage|table)", re.I)
_ALIAS = ((r"^results?$|main[_\s-]?result", "deliverable"),
          (r"claim|finding", "evidence_map"),
          (r"case[_\s-]?id", "case_id"), (r"deliverable|manuscript|artifact", "deliverable"),
          (r"preserved|preserv|fidelity", "preserved_facts"), (r"evidence", "evidence_map"),
          (r"change|diff|revision[_\s-]?log", "change_log"),
          (r"workorder|work[_\s-]?order|receipt", "workorder_execution"),
          (r"consisten", "consistency"), (r"coverage", "coverage"),
          (r"uncertaint", "uncertainty"), (r"pending|human", "pending_human"),
          (r"error", "errors"), (r"degrad", "degradations"), (r"status", "status"),
          (r"source", "sources"), (r"runtime|meta", "runtime"))

def contract_keys(contract):
    keys = []
    if isinstance(contract, dict):
        keys = [str(k) for k in contract.keys()]
    elif isinstance(contract, (list, tuple)):
        for it in contract:
            if isinstance(it, str):
                keys.append(it)
            elif isinstance(it, dict):
                v = next((it[k] for k in ("field", "name", "key", "id", "output")
                          if isinstance(it.get(k), str)), None)
                keys.extend([v] if v else [str(k) for k in it if str(k) not in
                                           ("type", "required", "description")])
    elif isinstance(contract, str):
        keys = [x.strip() for x in re.split(r"[,;、\n]", contract) if x.strip()]
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out

def contract_value(key, payload):
    if key in payload and payload[key] is not None:
        return payload[key]
    for pat, name in _ALIAS:
        if re.search(pat, str(key), re.I) and payload.get(name) is not None:
            return payload[name]
    return [] if _LISTISH.search(str(key)) else None

def echo_contract(contract, payload):
    return {k: contract_value(k, payload) for k in contract_keys(contract)}

def envelope(cid, contract, payload, status):
    payload = dict(payload)
    payload["case_id"] = cid
    payload["status"] = status
    res = echo_contract(contract, payload)
    for k, v in payload.items():
        res.setdefault(k, v)
    res["case_id"] = cid
    res["status"] = status
    res["contract_fields"] = contract_keys(contract)
    return res

def write_partial(out, cid, contract, note="", errors=None):
    payload = {"deliverable": None, "preserved_facts": [], "evidence_map": [], "change_log": [],
               "annotations": [], "workorder_execution": None, "consistency": None,
               "coverage": None, "sources": [], "uncertainty": [], "pending_human": [],
               "errors": [e for e in (errors or []) if e], "degradations": [note] if note else [],
               "changes": [], "runtime": rt()}
    res = envelope(cid, contract, payload, "partial")
    dump(Path(out) / "result.json", res)
    return res

