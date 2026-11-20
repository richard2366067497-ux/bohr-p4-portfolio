#!/usr/bin/env python3
"""Quote locator, atomicity checks and evidence-derived confidence for the
nanopub-assertions pipeline. Pure standard library.

The locator answers one question: given a quote and the raw page text, where does
that quote live? It tries, in order, (1) an exact substring, (2) a whitespace /
hyphen / ligature-normalised match, (3) a >= 0.90 sentence window. Only the first
two may be presented as verbatim; the third is always `fuzzy`.

Importable (`import np_lint`) or runnable:

    python3 np_lint.py --corpus work/corpus.json --draft work/assertions.draft.json \
        --out work/assertions.checked.json --report work/lint-report.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

RULES = {
    "ATO-01": "assertion text starts with an anaphor (it/this/they/these) instead of a named entity",
    "ATO-02": "compound clause: two verbs with distinct objects joined by and/;/but/whereas",
    "ATO-03": "assertion text is longer than one sentence or a whole paragraph",
    "ATO-04": "a required slot (subject, predicate or object) is empty",
    "ATO-05": "two different metrics merged into one assertion",
    "EV-01": "quote not found in any page (unverified)",
    "EV-02": "quote span falls outside the page text",
    "EV-03": "no evidence object at all",
    "EV-04": "a key term of the assertion is absent from the quote",
    "EV-05": "polarity mismatch: assertion negates what the quote affirms (or the reverse)",
    "EV-06": "direction mismatch: the relation points the opposite way from the quote",
    "EV-07": "only a fuzzy match supports the assertion; do not ship as fact",
    "FMT-01": "relation_type not in the controlled vocabulary",
    "FMT-02": "entity type not in the controlled vocabulary",
    "FMT-03": "assertion_type not in the controlled vocabulary",
}

ANAPHORA = re.compile(r"^(it|this|that|these|those|they|he|she|its|their|its own)\b", re.I)
COMPOUND = re.compile(r"\b(and|but|whereas|while|;)\b", re.I)
HEDGE = re.compile(r"\b(may|might|could|suggest[s]?|suggests that|appears|seems|likely|"
                   r"is consistent with|we hypothesi[sz]e|potentially|possibly|tends to)\b", re.I)
NEGATION = re.compile(r"\b(not|no|never|did not|does not|do not|cannot|without|failed to|"
                      r"no significant)\b", re.I)
VERB_HINT = re.compile(r"\b(is|are|was|were|has|have|had|shows?|shown|reports?|reported|"
                       r"increases?|decreases?|reduces?|reduced|improves?|improved|outperforms?|"
                       r"causes?|leads?|results?|enables?|inhibits?|activates?|predicts?|"
                       r"correlates?|associated|compared|measures?|achieves?|found|demonstrated)\b", re.I)


def load_vocab(path=None) -> dict:
    p = Path(path) if path else (ASSETS / "controlled-vocab.json")
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 - vocab is advisory, defaults keep us honest
        return {"relation_types": [], "entity_types": [], "assertion_types": [],
                "confidence_levels": {}, "polarity": ["affirmative", "negated"],
                "match_methods": {"exact": "", "normalized": "", "fuzzy": "", "unverified": ""}}


def normalize(s: str) -> str:
    s = s.replace("­", "")           # soft hyphen
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
    s = re.sub(r"-\s*\n\s*", "", s)       # de-hyphenate line breaks
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _pages_index(corpus: dict):
    return [(p.get("doc_id"), int(p.get("page", 1)), p.get("text") or "")
            for p in corpus.get("pages", [])]


def locate(quote: str, corpus: dict) -> dict:
    """Resolve a quote to {page, char_start, char_end, matched_text, method, score}."""
    if not quote or not quote.strip():
        return {"page": None, "char_start": None, "char_end": None, "matched_text": None,
                "method": "unverified", "score": 0.0}
    pages = _pages_index(corpus)
    # 1. exact
    for doc_id, pno, text in pages:
        idx = text.find(quote)
        if idx >= 0:
            return {"doc_id": doc_id, "page": pno, "char_start": idx, "char_end": idx + len(quote),
                    "matched_text": quote, "method": "exact", "score": 1.0}
    # 2. normalized (whitespace / hyphen / wrap tolerant)
    target = normalize(quote)
    if target:
        pat = re.compile(r"\s+".join(re.escape(tok) for tok in target.split()))
        for doc_id, pno, text in pages:
            m = pat.search(text)
            if m:
                return {"doc_id": doc_id, "page": pno, "char_start": m.start(), "char_end": m.end(),
                        "matched_text": text[m.start():m.end()], "method": "normalized",
                        "score": round(difflib.SequenceMatcher(None, normalize(quote),
                                                               normalize(text[m.start():m.end()])).ratio(), 3)}
        for doc_id, pno, text in pages:  # de-hyphenated source
            flat = normalize(text)
            j = flat.find(target)
            if j >= 0:
                return {"doc_id": doc_id, "page": pno, "char_start": 0, "char_end": len(text),
                        "matched_text": target, "method": "normalized", "score": 0.95}
    # 3. fuzzy sentence window
    best = {"score": 0.0}
    for doc_id, pno, text in pages:
        for sent in re.split(r"(?<=[.!?])\s+", text):
            if len(sent) < 15:
                continue
            r = difflib.SequenceMatcher(None, target, normalize(sent)).ratio()
            if r > best["score"]:
                best = {"doc_id": doc_id, "page": pno, "char_start": text.find(sent),
                        "char_end": text.find(sent) + len(sent), "matched_text": sent.strip(),
                        "method": "fuzzy", "score": round(r, 3)} if r >= 0.90 else {"score": r}
    if best.get("method") == "fuzzy":
        return best
    return {"page": None, "char_start": None, "char_end": None, "matched_text": None,
            "method": "unverified", "score": round(best.get("score", 0.0), 3)}


def confidence_for(locator: dict, roles, hedged: bool, basis) -> dict:
    """Ordinal, evidence-derived. The agent never writes a number."""
    method = locator.get("method")
    basis_out = list(basis or [])
    if method == "exact":
        basis_out.append("verbatim_quote")
    roles = list(roles or ["direct"])
    if method == "unverified":
        return {"level": "unsupported", "basis": sorted(set(basis_out + ["unverified_quote"])),
                "rationale": "machine-generated: locator found no span"}
    if method == "fuzzy":
        return {"level": "ambiguous", "basis": sorted(set(basis_out + ["fuzzy_match_only"])),
                "rationale": "machine-generated: only a >=0.90 window matched"}
    if "contradicting" in roles:
        return {"level": "ambiguous", "basis": sorted(set(basis_out + ["conflicting"])),
                "rationale": "machine-generated: shipped spans conflict"}
    if "inferred" in roles:
        return {"level": "inferred", "basis": sorted(set(basis_out + ["indirect_inference"])),
                "rationale": "machine-generated: needs reasoning beyond the span"}
    if len(roles) >= 2 and "direct" not in roles:
        return {"level": "aggregated", "basis": sorted(set(basis_out)),
                "rationale": "machine-generated: several spans jointly support"}
    if hedged:
        return {"level": "direct_reported", "basis": sorted(set(basis_out + ["author_claim"])),
                "rationale": "machine-generated: verbatim but hedged wording"}
    return {"level": "direct_verbatim", "basis": sorted(set(basis_out)),
            "rationale": "machine-generated: verbatim span with direct role"}


def _slots(a: dict):
    sub = a.get("subject")
    sub = sub.get("label") if isinstance(sub, dict) else sub
    obj = a.get("object")
    obj = obj.get("label") if isinstance(obj, dict) else obj
    pred = a.get("predicate_label") or (a.get("predicate") or {}).get("label")
    return (sub or "").strip(), (pred or "").strip(), (obj or "").strip()


def lint_assertion(a: dict, corpus: dict, vocab: dict) -> dict:
    checks, quotes = [], []
    text = (a.get("text") or "").strip()
    sub, pred, obj = _slots(a)
    evidence = a.get("evidence") or []
    if not evidence:
        checks.append({"id": "EV-03", "status": "fail", "detail": "no evidence object",
                       "rule": RULES["EV-03"]})
    locators = []
    for ev in evidence:
        loc = locate(ev.get("quote", ""), corpus)
        locators.append(loc)
        quote = ev.get("quote", "") or ""
        quotes.append(quote)
        if loc["method"] == "unverified":
            checks.append({"id": "EV-01", "status": "fail",
                           "detail": "quote not found: %r" % quote[:60], "rule": RULES["EV-01"]})
        elif loc["method"] == "fuzzy":
            checks.append({"id": "EV-07", "status": "warn",
                           "detail": "fuzzy match score %.2f" % loc["score"], "rule": RULES["EV-07"]})
        else:
            checks.append({"id": "EV-01", "status": "pass",
                           "detail": "%s match on page %s" % (loc["method"], loc["page"]),
                           "rule": RULES["EV-01"]})
        jq = normalize(quote).lower()
        for term in (sub, obj):
            t = normalize(term).lower()
            if t and len(t) > 3 and t not in jq:
                checks.append({"id": "EV-04", "status": "warn",
                               "detail": "key term %r absent from quote" % term, "rule": RULES["EV-04"]})
    if text:
        if ANAPHORA.match(text):
            checks.append({"id": "ATO-01", "status": "fail",
                           "detail": "starts with an anaphor", "rule": RULES["ATO-01"]})
        if len(text) > 320:
            checks.append({"id": "ATO-03", "status": "fail",
                           "detail": "longer than one sentence", "rule": RULES["ATO-03"]})
        if COMPOUND.search(text) and len(re.findall(VERB_HINT, text)) >= 2:
            checks.append({"id": "ATO-02", "status": "warn",
                           "detail": "possible compound clause", "rule": RULES["ATO-02"]})
    if not (sub and pred and obj):
        checks.append({"id": "ATO-04", "status": "fail",
                       "detail": "empty slot subject=%r predicate=%r object=%r" % (sub, pred, obj),
                       "rule": RULES["ATO-04"]})
    rel = (a.get("predicate") or {}).get("relation_type")
    if rel and vocab.get("relation_types") and rel not in vocab["relation_types"]:
        checks.append({"id": "FMT-01", "status": "warn", "detail": "relation_type %r off-vocab" % rel,
                       "rule": RULES["FMT-01"]})
    polarity = a.get("polarity", "affirmative")
    jq_all = normalize(" ".join(quotes)).lower()
    if jq_all:
        quote_neg = bool(NEGATION.search(jq_all))
        if polarity == "affirmative" and quote_neg:
            checks.append({"id": "EV-05", "status": "warn",
                           "detail": "assertion affirmative but quote contains a negation",
                           "rule": RULES["EV-05"]})
        if polarity == "negated" and not quote_neg:
            checks.append({"id": "EV-05", "status": "warn",
                           "detail": "assertion negated but quote has no negation", "rule": RULES["EV-05"]})
    hedged = bool(HEDGE.search(text) or HEDGE.search(" ".join(quotes)))
    best = max(locators, key=lambda l: l["score"]) if locators else {"method": "unverified", "score": 0.0}
    roles = [ev.get("role", "direct") for ev in evidence] or ["direct"]
    conf = confidence_for(best, roles, hedged, a.get("confidence_basis"))
    fails = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    passes = sum(1 for c in checks if c["status"] == "pass")
    score = round(max(0.0, 1.0 - 0.25 * fails - 0.07 * warns), 3)
    a["evidence"] = [{**ev, "locator": locators[i]} for i, ev in enumerate(evidence)]
    a["confidence"] = conf
    a["quality"] = {"score": score, "pass": passes, "warn": warns, "fail": fails, "checks": checks}
    return a


def run_lint(draft: dict, corpus: dict, vocab: dict) -> dict:
    out = dict(draft)
    checked = []
    for a in draft.get("assertions", []) or []:
        checked.append(lint_assertion(dict(a), corpus, vocab))
    out["assertions"] = checked
    return out


def lint_report(checked: dict) -> str:
    lines = ["# lint report", "",
             "| local_id | quality | pass/warn/fail | confidence | issues |",
             "|-|-|-|-|-|"]
    for a in checked.get("assertions", []):
        issues = "; ".join("%s %s" % (c["id"], c["detail"])
                           for c in a.get("quality", {}).get("checks", []) if c["status"] != "pass")
        q = a.get("quality", {})
        lines.append("| %s | %s | %s/%s/%s | %s | %s |"
                     % (a.get("local_id"), q.get("score"), q.get("pass"), q.get("warn"),
                        q.get("fail"), (a.get("confidence") or {}).get("level"), issues or "-"))
    fails = sum(a.get("quality", {}).get("fail", 0) for a in checked.get("assertions", []))
    lines += ["", "failing: %d" % fails, ""]
    return "\n".join(lines)


def _pdf_literal(s: str, i: int):
    depth, i, buf = 1, i + 1, []
    while i < len(s) and depth:
        c = s[i]
        if c == "\\":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            m = {"n": "\n", "r": "\r", "t": "\t", "(": "(", ")": ")", "\\": "\\"}
            if nxt in m:
                buf.append(m[nxt]); i += 2; continue
            oct_m = re.match(r"[0-7]{1,3}", s[i + 1:i + 4])
            if oct_m:
                buf.append(chr(int(oct_m.group(0), 8))); i += 1 + len(oct_m.group(0)); continue
            i += 2; continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if not depth:
                i += 1; break
        buf.append(c); i += 1
    return "".join(buf), i


def _pdf_text_from_stream(data: bytes) -> str:
    s = data.decode("latin-1", "replace")
    out, pending, i = [], [], 0
    while i < len(s):
        c = s[i]
        if c == "(":
            t, i = _pdf_literal(s, i); pending.append(t); continue
        if c == "<" and i + 1 < len(s) and s[i + 1] != "<":
            j = s.find(">", i + 1)
            if j < 0:
                break
            hx = re.sub(r"[^0-9A-Fa-f]", "", s[i + 1:j])
            pending.append(bytes.fromhex(hx + ("0" if len(hx) % 2 else "")).decode("latin-1", "replace"))
            i = j + 1; continue
        if s.startswith(("Tj", "TJ"), i):
            out.append("".join(pending)); pending = []; i += 2; continue
        if s.startswith(("Td", "TD", "T*", "Tm", "BT", "ET"), i):
            if out and not out[-1].endswith("\n"):
                out.append("\n")
            i += 2; continue
        i += 1
    if pending:
        out.append("".join(pending))
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


def extract_pdf_pages(path):
    """Stdlib PDF text fallback: object scan, FlateDecode, Tj/TJ operators."""
    import zlib
    raw = path.read_bytes()
    objs = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b", raw):
        end = raw.find(b"endobj", m.end())
        if end != -1:
            objs[int(m.group(1))] = raw[m.end():end]
    refs_order = []
    for num in sorted(objs):
        body = objs[num]
        if b"/Type" in body and b"/Page" in body and b"/Pages" not in body:
            m = re.search(rb"/Contents\s+(\d+)\s+\d+\s+R", body)
            arr = re.search(rb"/Contents\s*\[([^\]]+)\]", body)
            if m:
                refs_order.append([int(m.group(1))])
            elif arr:
                refs_order.append([int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", arr.group(1))])
    pages = []
    for refs in refs_order:
        chunk = []
        for r in refs:
            body = objs.get(r, b"")
            sm = body.find(b"stream")
            if sm == -1:
                continue
            dict_text = body[:sm]
            data = body[sm + 6:].lstrip(b"\r\n")
            e = data.find(b"endstream")
            if e != -1:
                data = data[:e]
            if b"/FlateDecode" in dict_text:
                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    data = b""
            chunk.append(_pdf_text_from_stream(data))
        pages.append("\n".join(c for c in chunk if c))
    return pages


def split_plain_pages(text: str):
    if "\f" in text:
        return [p for p in text.split("\f")]
    # chunk by ~3000 chars on paragraph boundaries so char offsets stay page-local
    parts, buf, size = [], [], 0
    for para in text.split("\n\n"):
        if size + len(para) > 3000 and buf:
            parts.append("\n\n".join(buf)); buf, size = [], 0
        buf.append(para); size += len(para) + 2
    if buf:
        parts.append("\n\n".join(buf))
    return parts or [text]


def extract_text_pages(path):
    """Return (pages, backend) for a .pdf / .md / .txt input."""
    if path.suffix.lower() == ".pdf":
        return extract_pdf_pages(path), "stdlib-pdf"
    return split_plain_pages(path.read_text(encoding="utf-8", errors="replace")), "plain-read"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--vocab", default=None)
    args = ap.parse_args()
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8", errors="replace"))
    draft = json.loads(Path(args.draft).read_text(encoding="utf-8", errors="replace"))
    checked = run_lint(draft, corpus, load_vocab(args.vocab))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.report:
        Path(args.report).write_text(lint_report(checked), encoding="utf-8")
    print(lint_report(checked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
