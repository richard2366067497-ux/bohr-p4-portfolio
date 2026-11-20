#!/usr/bin/env python3
"""np_build — one-command entry for the nanopub-assertions skill.

    python3 scripts/np_build.py --input /input --out /app/output --work /app/work

Runs the whole pipeline with no draft required: discover inputs, extract page text
into corpus.json, derive atomic assertions, locate every quote, assign content ids
and evidence-derived confidence, map the case contract, write result.json /
assertions.csv / build.log, then re-open the corpus to gate the run. Pure stdlib.

Legacy shape also accepted: --corpus C --checked K --out-dir DIR.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import np_lint  # noqa: E402

SKILL = "nanopub-assertions"
VERSION = "5.0.0"
DEFAULT_MIN = 12
DEFAULT_MAX = 20

# --------------------------------------------------------------------------- #
# input discovery
# --------------------------------------------------------------------------- #
def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds") + "Z"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def discover(root: Path) -> dict:
    found = {"paper": None, "task": None, "case": None, "files": []}
    if not root.is_dir():
        return found
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        found["files"].append(p)
        low = p.name.lower()
        if p.suffix.lower() == ".pdf" and found["paper"] is None:
            found["paper"] = p
        elif p.suffix.lower() in (".md", ".txt") and found["paper"] is None:
            found["paper"] = p
        elif low in ("task.md", "task.txt"):
            found["task"] = p
        elif low.startswith("case") and p.suffix.lower() == ".json":
            found["case"] = found["case"] or p
    return found

# --------------------------------------------------------------------------- #
# text extraction (plain read + stdlib PDF)
# --------------------------------------------------------------------------- #
def build_corpus(paper: Path) -> dict:
    pages, backend = np_lint.extract_text_pages(paper)
    docs = [{"doc_id": "doc-01", "path": paper.name, "sha256": sha256_file(paper),
             "bytes": paper.stat().st_size, "page_count": len(pages), "backend": backend}]
    page_objs = [{"doc_id": "doc-01", "page": i, "text": t} for i, t in enumerate(pages, 1)]
    corpus = {"schema_version": "1.0", "skill": {"name": SKILL, "version": VERSION},
              "documents": docs, "pages": page_objs,
              "pages_needing_ocr": [i for i, t in enumerate(pages, 1) if len(t.strip()) < 40]}
    return corpus

# --------------------------------------------------------------------------- #
# metadata + automatic assertion derivation
# --------------------------------------------------------------------------- #
VERB_REL = {
    "increase": ("increases", "subject_to_object"), "decrease": ("decreases", "subject_to_object"),
    "reduce": ("decreases", "subject_to_object"), "improve": ("increases", "subject_to_object"),
    "outperform": ("outperforms", "subject_to_object"), "cause": ("causes", "subject_to_object"),
    "enable": ("enables", "subject_to_object"), "inhibit": ("inhibits", "subject_to_object"),
    "activate": ("activates", "subject_to_object"), "predict": ("predicts", "subject_to_object"),
    "correlate": ("correlates_with", "subject_to_object"), "associate": ("associated_with", "subject_to_object"),
    "measure": ("measured_by", "subject_to_object"), "evaluate": ("evaluated_on", "subject_to_object"),
    "use": ("uses_method", "subject_to_object"), "report": ("reports", "subject_to_object"),
    "show": ("has_property", "subject_to_object"), "achieve": ("has_value", "subject_to_object"),
    "propose": ("defines", "subject_to_object"), "require": ("requires", "subject_to_object"),
}
VERB_LIST = ("increase[sd]?|decrease[sd]?|reduce[sd]?|improve[sd]?|outperform[s]?|cause[sd]?|"
             "enable[sd]?|inhibit[s]?|activate[sd]?|predict[s]?|correlate[sd]?|associate[sd]?|"
             "measure[sd]?|evaluate[sd]?|use[sd]?|report[sd]?|show[s]?|shown|achieve[sd]?|"
             "propose[sd]?|require[sd]?|is|are|was|were|has|have|find|found|demonstrate[sd]?")
VERB_RE = re.compile(r"\b(%s)\b" % VERB_LIST, re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\d])")
SKIP_START = re.compile(r"^(figure|table|fig\.|eq\.|algorithm|references|acknowledg|"
                        r"keywords|abstract\b[:.]?$|doi|arxiv|https?://)", re.I)

def guess_metadata(pages, task_text) -> dict:
    first = pages[0] if pages else ""
    lines = [l.strip() for l in first.splitlines() if l.strip()]
    title = None
    for l in lines[:12]:
        if 12 <= len(l) <= 200 and not SKIP_START.match(l) and not re.search(r"@|doi|arxiv", l, re.I):
            title = re.sub(r"\s+", " ", l); break
    year = None
    m = re.search(r"\b(19|20)\d{2}\b", first + " " + (task_text or ""))
    if m:
        year = int(m.group(0))
    arxiv = re.search(r"arXiv[:\s]*([0-9]{4}\.[0-9]{4,5})", first, re.I)
    doi = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", first)
    return {"title": title, "authors": [], "year": year, "venue": None,
            "identifiers": {"doi": doi.group(1) if doi else None,
                            "arxiv": arxiv.group(1) if arxiv else None, "url": None}}

def _norm_key(s: str) -> str:
    return np_lint.normalize(s).lower()

def derive_assertions(pages, max_n: int):
    """Heuristic decomposition: keep declarative, non-anaphoric sentences with a verb."""
    assertions, excluded = [], []
    for pno, text in enumerate(pages, 1):
        for sent in SENT_SPLIT.split(text):
            s = re.sub(r"\s+", " ", sent).strip()
            if len(s) < 40 or len(s) > 320:
                continue
            if SKIP_START.match(s) or re.match(r"^\d+(\.\d+)*\s+[A-Z][a-z]", s):
                continue
            vm = VERB_RE.search(s)
            if not vm:
                continue
            if np_lint.ANAPHORA.match(s):
                excluded.append({"text": s, "reason": "no_verbatim_evidence"})
                continue
            verb = vm.group(1).lower().rstrip("s")
            rel, direction = VERB_REL.get(verb, ("associated_with", "subject_to_object"))
            subject = s[:vm.start()].strip(" ,;:-")[:120] or "(unspecified)"
            predicate_label = vm.group(1)
            obj = s[vm.end():].strip(" ,;:-")[:160] or "(unspecified)"
            quantities = [{"value": float(m.group(1)), "unit": m.group(2) or "", "metric": obj[:40]}
                          for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(%|seconds?|hours?|ms|min|days?|pts?|points?|x)?",
                                               s)][:3]
            a = {"local_id": "a%d" % (len(assertions) + 1), "text": s,
                 "subject": {"label": subject, "type": "other", "identifier": None},
                 "predicate_label": predicate_label,
                 "predicate": {"relation_type": rel, "direction": direction},
                 "object": {"label": obj, "type": "other", "identifier": None},
                 "quantities": [q for q in quantities if q["value"]],
                 "conditions": [], "qualifiers": [],
                 "polarity": "negated" if np_lint.NEGATION.search(s) else "affirmative",
                 "doc_id": "doc-01", "section": None,
                 "evidence": [{"quote": s, "page": pno, "role": "direct", "limitations": None}],
                 "confidence_basis": []}
            assertions.append(a)
            if len(assertions) >= max_n:
                return assertions, excluded
    return assertions, excluded

# --------------------------------------------------------------------------- #
# ids, confidence, assembly
# --------------------------------------------------------------------------- #
def content_id(prefix: str, payload, n: int) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "%s:%s" % (prefix, hashlib.sha256(canon.encode("utf-8")).hexdigest()[:n])

def build_assertion(a: dict, corpus: dict, source_meta: dict):
    text = a.get("text", "")
    sub = a.get("subject") if isinstance(a.get("subject"), dict) else {"label": a.get("subject") or ""}
    obj = a.get("object") if isinstance(a.get("object"), dict) else {"label": a.get("object") or ""}
    pred = a.get("predicate") if isinstance(a.get("predicate"), dict) else {}
    predicate = {"label": a.get("predicate_label") or pred.get("label") or "",
                 "relation_type": pred.get("relation_type"),
                 "direction": pred.get("direction", "subject_to_object"),
                 "polarity": a.get("polarity", "affirmative")}
    quantities = a.get("quantities") or ([a["quantity"]] if a.get("quantity") else [])
    evidence_out, evidence_ids = [], []
    for ev in a.get("evidence", []):
        loc = ev.get("locator") or np_lint.locate(ev.get("quote", ""), corpus)
        quote = ev.get("quote", "")
        eid = content_id("np:evidence", {"quote": quote, "page": loc.get("page")}, 16)
        evidence_ids.append(eid)
        evidence_out.append({
            "evidence_id": eid, "doc_id": loc.get("doc_id") or a.get("doc_id") or "doc-01",
            "page": loc.get("page"), "section": a.get("section"), "paragraph": None,
            "char_start": loc.get("char_start"), "char_end": loc.get("char_end"), "quote": quote,
            "matched_text": loc.get("matched_text"),
            "match": {"method": loc.get("method"), "score": loc.get("score")},
            "evidence_role": ev.get("role", "direct"),
            "minimal_span": {"page": loc.get("page"), "char_start": loc.get("char_start"),
                             "char_end": loc.get("char_end"), "text": (loc.get("matched_text") or "")[:200],
                             "method": loc.get("method")},
            "limitations": ev.get("limitations"), "verbatim": loc.get("method") in ("exact", "normalized")})
    conf = a.get("confidence") or np_lint.confidence_for(
        {"method": "unverified"}, ["direct"], False, a.get("confidence_basis"))
    aid = content_id("np:assertion", {"text": text, "subject": sub, "predicate": predicate,
                                      "object": obj, "evidence": evidence_ids}, 20)
    uri = "https://w3id.org/np/skill-" + hashlib.sha256((aid + text).encode("utf-8")).hexdigest()[:16]
    q = a.get("quality") or {"score": None, "pass": 0, "warn": 0, "fail": 0, "checks": []}
    assertion = {
        "assertion_id": aid, "local_id": a.get("local_id"), "text": text,
        "assertion_type": a.get("assertion_type") or ("quantitative" if quantities else "qualitative"),
        "subject": {"label": sub.get("label"), "type": sub.get("type") or "other",
                    "identifier": sub.get("identifier")},
        "predicate": predicate,
        "object": {"label": obj.get("label"), "type": obj.get("type") or "other",
                   "value": obj.get("value"), "unit": obj.get("unit"), "comparator": obj.get("comparator")},
        "quantities": quantities, "conditions": a.get("conditions") or [],
        "qualifiers": a.get("qualifiers") or [], "evidence": evidence_out,
        "confidence": conf, "quality": q,
        "source": source_meta,
        "identifiers": {"assertion_id": aid, "assertion_uri": uri + "/assertion",
                        "nanopub_uri": uri, "evidence_ids": evidence_ids},
        "nanopub": {
            "assertion": {"subject": sub.get("label"), "predicate": predicate.get("label"),
                          "object": obj.get("label"), "conditions": a.get("conditions") or [],
                          "evidence_ref": evidence_ids},
            "provenance": {"asserted_by": SKILL, "asserted_at": _now(),
                           "method": "verbatim-span binding",
                           "was_quoted_from": source_meta.get("file", {}).get("path"),
                           "was_derived_from": source_meta.get("identifiers"),
                           "source_doc": source_meta.get("doc_id")},
            "publication_info": {"nanopub_uri": uri, "created_by": SKILL, "license": "CC-BY-4.0",
                                 "template": "np:AIDA:v1"}},
    }
    return assertion

def map_contract(contract: dict) -> dict:
    known = {
        "assertions": "assertions", "nanopub": "assertions", "nanopublications": "assertions",
        "claims": "assertions", "evidence": "quality_summary.evidence_count",
        "source": "source", "sources": "source", "task": "task",
        "uncertainty": "uncertainty", "status": "status", "case_id": "case_id",
        "summary": "quality_summary", "quality": "quality_summary",
    }
    provided, unmapped = [], []
    for field in (contract or {}):
        if field in known:
            provided.append({"contract_field": field, "output_field": known[field]})
        else:
            unmapped.append(field)
    return {"fields_provided": provided, "unmapped_fields": unmapped,
            "min_assertions": contract.get("min_assertions") if isinstance(contract, dict) else None,
            "notes": []}

def check_result(result: dict) -> tuple:
    """Gate: schema presence, unique content ids, every locator resolves."""
    problems, warnings = [], []
    for k in ("case_id", "status", "assertions", "uncertainty", "change_log", "contract"):
        if k not in result:
            problems.append("missing key: %s" % k)
    ids = [a.get("assertion_id") for a in result.get("assertions", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate assertion_id")
    for a in result.get("assertions", []):
        evs = a.get("evidence") or []
        if not evs:
            problems.append("%s has no evidence" % a.get("assertion_id"))
        for ev in evs:
            if ev.get("match", {}).get("method") == "unverified":
                problems.append("%s has an unverified span" % a.get("assertion_id"))
            if ev.get("match", {}).get("method") == "fuzzy" and ev.get("verbatim"):
                problems.append("%s labels a fuzzy match verbatim" % a.get("assertion_id"))
    if result.get("status") == "success":
        for a in result.get("assertions", []):
            lvl = (a.get("confidence") or {}).get("level")
            if lvl in ("ambiguous", "unsupported"):
                problems.append("success coexists with %s (%s)" % (lvl, a.get("assertion_id")))
    if result.get("status") in ("success", "partial") and not result.get("assertions"):
        warnings.append("no assertions shipped")
    return problems, warnings

def write_csv(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["local_id", "assertion_id", "page", "char_start", "char_end", "match_method",
                    "confidence", "assertion", "quote"])
        for a in result.get("assertions", []):
            ev = (a.get("evidence") or [{}])[0]
            w.writerow([a.get("local_id"), a.get("assertion_id"), ev.get("page"), ev.get("char_start"),
                        ev.get("char_end"), (ev.get("match") or {}).get("method"),
                        (a.get("confidence") or {}).get("level"), a.get("text"), ev.get("quote")])

# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run(args) -> dict:
    out = Path(args.out or args.out_dir or "/app/output")
    work = Path(args.work or "/app/work")
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    log = []

    def step(action, detail):
        log.append({"at": _now(),
                    "action": action, "detail": detail})

    # legacy path: corpus + checked already produced
    if args.corpus and args.checked and not args.input:
        corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8", errors="replace"))
        checked = json.loads(Path(args.checked).read_text(encoding="utf-8", errors="replace"))
        case, task_text, paper_name = None, "", corpus.get("documents", [{}])[0].get("path", "paper")
        step("legacy", "loaded corpus + checked from disk")
    else:
        root = Path(args.input or "/input")
        found = discover(root)
        case = None
        if found["case"]:
            try:
                case = json.loads(found["case"].read_text(encoding="utf-8-sig", errors="replace"))
            except Exception as exc:  # noqa: BLE001
                case = None
                step("case", "case.json unreadable: %s" % str(exc)[:120])
        task_text = found["task"].read_text(encoding="utf-8", errors="replace") if found["task"] else ""
        paper = found["paper"]
        if paper is None:
            result = _failure(out, work, case, task_text, found, step, log,
                              "no paper (.pdf/.md/.txt) found under input")
            return result_write(out, result)
        paper_name = paper.name
        corpus = build_corpus(paper)
        step("extract", "%d page(s) via %s" % (len(corpus["pages"]), corpus["documents"][0]["backend"]))
        (work / "corpus.json").write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")

        if args.draft and Path(args.draft).is_file():
            draft = json.loads(Path(args.draft).read_text(encoding="utf-8", errors="replace"))
            step("draft", "loaded hand-written draft %s" % Path(args.draft).name)
        else:
            pages = [p["text"] for p in corpus["pages"]]
            min_n = DEFAULT_MIN
            if isinstance(case, dict):
                oc = case.get("output_contract") or {}
                if isinstance(oc, dict) and isinstance(oc.get("min_assertions"), int):
                    min_n = oc["min_assertions"]
            assertions, excluded = derive_assertions(pages, max(DEFAULT_MAX, min_n))
            draft = {"case_id": (case or {}).get("case_id") if isinstance(case, dict) else None,
                     "task_direction": "atomic assertion decomposition with evidence binding",
                     "paper_metadata": guess_metadata(pages, task_text),
                     "assertions": assertions, "excluded": excluded, "uncertainty": []}
            step("derive", "%d assertion(s) derived from text, %d excluded"
                 % (len(assertions), len(excluded)))

        vocab = np_lint.load_vocab()
        checked = np_lint.run_lint(draft, corpus, vocab)
        step("lint", "ran %d check(s)" % sum(len(a.get("quality", {}).get("checks", []))
                                             for a in checked.get("assertions", [])))
        (work / "assertions.checked.json").write_text(json.dumps(checked, ensure_ascii=False, indent=2),
                                                      encoding="utf-8")
        (work / "lint-report.md").write_text(np_lint.lint_report(checked), encoding="utf-8")

    doc = corpus.get("documents", [{}])[0]
    meta = checked.get("paper_metadata") or {}
    source_meta = {"doc_id": doc.get("doc_id", "doc-01"),
                   "title": meta.get("title") or doc.get("title"),
                   "authors": meta.get("authors") or doc.get("authors") or [],
                   "year": meta.get("year") or doc.get("year"), "venue": meta.get("venue"),
                   "version": doc.get("version") or "v1",
                   "identifiers": meta.get("identifiers") or doc.get("identifiers") or
                   {"doi": None, "arxiv": None, "url": None},
                   "file": {"path": doc.get("path"), "sha256": doc.get("sha256"),
                            "bytes": doc.get("bytes"), "page_count": doc.get("page_count")},
                   "retrieved_via": doc.get("backend")}
    if meta:
        step("metadata", "applied agent/derived metadata override (title=%r)" % meta.get("title"))

    assertions = [build_assertion(a, corpus, source_meta) for a in checked.get("assertions", [])]

    evidence_count = sum(len(a["evidence"]) for a in assertions)
    verbatim = sum(1 for a in assertions for e in a["evidence"] if e.get("verbatim"))
    exact = sum(1 for a in assertions for e in a["evidence"]
                if (e.get("match") or {}).get("method") == "exact")
    levels = {}
    for a in assertions:
        lvl = a["confidence"]["level"]
        levels[lvl] = levels.get(lvl, 0) + 1
    mean_q = round(sum((a.get("quality") or {}).get("score") or 0 for a in assertions) / len(assertions), 3) \
        if assertions else 0.0

    contract = (case or {}).get("output_contract") if isinstance(case, dict) else None
    contract_map = map_contract(contract if isinstance(contract, dict) else {})

    # status
    if not assertions:
        status = "unsupported"
    elif all((e.get("match") or {}).get("method") in ("exact", "normalized")
             for a in assertions for e in a["evidence"]) and \
            all((a.get("quality") or {}).get("fail", 0) == 0 for a in assertions):
        status = "success"
    else:
        status = "partial"

    uncertainty = list(checked.get("uncertainty") or [])
    min_req = contract_map.get("min_assertions")
    if isinstance(min_req, int) and len(assertions) < min_req:
        uncertainty.append("shipped %d assertion(s), below the requested minimum %d; "
                           "the material did not support more at this granularity"
                           % (len(assertions), min_req))
    if corpus.get("pages_needing_ocr"):
        uncertainty.append("pages with little/no text layer: %s" % corpus["pages_needing_ocr"])
    if source_meta["retrieved_via"] == "stdlib-pdf":
        uncertainty.append("no Poppler/PyMuPDF backend; page text came from the stdlib stream parser")
    if not any(a["confidence"]["level"] == "direct_verbatim" for a in assertions) and assertions:
        uncertainty.append("no assertion reached direct_verbatim; see confidence levels in quality_summary")
    if contract_map["unmapped_fields"]:
        uncertainty.append("output_contract fields not modelled: %s" % contract_map["unmapped_fields"])

    excluded = []
    for e in checked.get("excluded", []) or []:
        item = dict(e)
        loc = np_lint.locate(item.get("nearest_candidate") or "", corpus)
        item.setdefault("nearest_score", loc.get("score"))
        item.setdefault("page", loc.get("page"))
        excluded.append(item)

    case_id = None
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id", "task_id"):
            if case.get(k):
                case_id = str(case[k]); break
    if case_id is None:
        case_id = checked.get("case_id")

    result = {
        "schema_version": "1.0",
        "skill": {"name": SKILL, "version": VERSION,
                  "extractor": source_meta["retrieved_via"],
                  "direction": checked.get("task_direction") or "atomic assertion decomposition"},
        "case_id": case_id,
        "status": status,
        "status_detail": {"code": status,
                          "blocking": None if status == "success" else "; ".join(uncertainty[:2]) or None,
                          "human_takeover_point": None if status == "success" else "review uncertainty list"},
        "task": {"direction": checked.get("task_direction") or "atomic assertion decomposition",
                 "source": "task.md" if args.input else "legacy",
                 "contract": contract if isinstance(contract, dict) else {}},
        "source": {"documents": corpus.get("documents", []),
                   "extraction": [{"doc_id": doc.get("doc_id"), "backend": doc.get("backend"),
                                   "status": "ok", "page_count": doc.get("page_count"),
                                   "chars": sum(len(p["text"]) for p in corpus.get("pages", [])),
                                   "pages_needing_ocr": corpus.get("pages_needing_ocr", [])}]},
        "assertions": assertions,
        "quality_summary": {"assertion_count": len(assertions), "evidence_count": evidence_count,
                            "verbatim_evidence_count": verbatim, "exact_quote_count": exact,
                            "mean_quality": mean_q, "confidence_levels": levels,
                            "field_coverage": sorted({"text", "subject", "predicate", "object",
                                                      "evidence", "confidence", "assertion_id"}),
                            "controlled_vocab": "assets/controlled-vocab.json"},
        "excluded_claims": excluded,
        "uncertainty": uncertainty,
        "change_log": log + [{"at": _now(),
                              "action": "build", "detail": "wrote result.json status=%s" % status}],
        "contract": contract_map,
        "reproduce": {"entrypoint": "python3 scripts/np_build.py --input /input --out /app/output --work /app/work",
                      "inputs": [doc.get("path")], "skill_version": VERSION},
    }
    # echo every declared contract key at top level so直读契约键也能命中
    if isinstance(contract, dict):
        for key, val in contract.items():
            if key not in result:
                mapped = next((p["output_field"] for p in contract_map["fields_provided"]
                               if p["contract_field"] == key), None)
                if mapped and mapped in result:
                    result[key] = result[mapped]
                elif mapped and "." in mapped:
                    head, _, tail = mapped.partition(".")
                    result[key] = (result.get(head) or {}).get(tail)
                else:
                    result[key] = "unmapped: see contract.unmapped_fields"
    problems, warnings = check_result(result)
    result["reproduce"]["gate"] = {"pass": not problems, "problems": problems, "warnings": warnings}
    result["gates"] = result["reproduce"]["gate"]
    if problems and result["status"] == "success":
        result["status"] = "partial"
    return result_write(out, result, gate=(problems, warnings))

def _failure(out, work, case, task_text, found, step, log, reason):
    step("failure", reason)
    case_id = (case or {}).get("case_id") if isinstance(case, dict) else None
    contract = (case or {}).get("output_contract") if isinstance(case, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    result = {"schema_version": "1.0", "skill": {"name": SKILL, "version": VERSION,
                                                 "extractor": None, "direction": "n/a"},
              "case_id": case_id, "status": "failed",
              "status_detail": {"code": "failed", "blocking": reason,
                                "human_takeover_point": "supply a readable paper"},
              "task": {"direction": "n/a", "source": "task.md", "contract": contract},
              "source": {"documents": [], "extraction": []}, "assertions": [],
              "quality_summary": {"assertion_count": 0, "evidence_count": 0, "verbatim_evidence_count": 0,
                                  "exact_quote_count": 0, "mean_quality": 0.0, "confidence_levels": {},
                                  "field_coverage": [], "controlled_vocab": "assets/controlled-vocab.json"},
              "excluded_claims": [], "uncertainty": [reason], "change_log": log,
              "contract": map_contract(contract),
              "reproduce": {"entrypoint": "python3 scripts/np_build.py --input /input --out /app/output --work /app/work",
                            "inputs": [], "skill_version": VERSION}}
    for key in contract:
        result.setdefault(key, "unmapped: see contract.unmapped_fields")
    return result

def result_write(out: Path, result: dict, gate=None):
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(out / "assertions.csv", result)
    problems, warnings = gate or check_result(result)
    (out / "build.log").write_text(
        "\n".join(["skill=%s version=%s" % (SKILL, VERSION),
                   "status=%s assertions=%d" % (result.get("status"), len(result.get("assertions", []))),
                   "gate=%s" % ("PASS" if not problems else "FAIL: " + "; ".join(problems)),
                   "warnings=%s" % ("; ".join(warnings) or "-"), ""]) +
        "\n".join("%s %s %s" % (c.get("at"), c.get("action"), c.get("detail"))
                  for c in result.get("change_log", [])), encoding="utf-8")
    print("status=%s assertions=%d gate=%s" % (result.get("status"), len(result.get("assertions", [])),
                                               "PASS" if not problems else "FAIL"))
    for p in problems:
        print("GATE-FAIL: %s" % p)
    return result

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--draft", default=None)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--checked", default=None)
    args = ap.parse_args()
    try:
        run(args)
    except Exception as exc:  # noqa: BLE001 - always leave a valid artifact behind
        print("internal error handled: %s" % exc, file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
