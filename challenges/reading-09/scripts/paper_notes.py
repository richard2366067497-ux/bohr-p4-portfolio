#!/usr/bin/env python3
"""paper_notes.py — turn a supplied paper into section-aligned, evidence-anchored
structured notes.

    paper_notes.py all --input /input --out /app/output [--work /app/work]

One run ingests the case, the paper (PDF / DOCX / Markdown / TeX / plain text)
and any supplementary files, maps the paper's own headings, binds every note to
a verbatim quote on its page, fills the paper card, extracts retrievable
knowledge points, answers the case's questions, records conflicts and gaps, and
writes result.json, notes.md, anchors.csv and the work/ ledger. `prepare`,
`finalize`, `check` and `doctor` are kept for compatibility; every subcommand
is safe to run on its own and always exits 0 with a valid result.json.

No network, no third-party packages.
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pn_sections as pn  # noqa: E402
import pn_notes as pnt  # noqa: E402

DOC_SUFFIXES = (".pdf", ".docx", ".md", ".markdown", ".txt", ".tex", ".csv", ".rst")
CODE_SUFFIXES = (".py", ".json", ".yaml", ".yml")
DEFAULT_QUESTIONS = [
    "按章节总结每节的目的、方法、结果与结论。",
    "填好论文卡片（研究问题、数据、方法、主要发现、条件、局限、结论）。",
    "给出可检索的知识点（术语 + 定义 + 同义词）。",
]


def norm(text):
    return pn.norm(text)


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        return None


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def clip(text, limit=240):
    text = norm(text)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


# --------------------------------------------------------------------------
# input discovery
# --------------------------------------------------------------------------
def discover(input_dir, case_override=None):
    input_dir = Path(input_dir)
    case_path = Path(case_override) if case_override else input_dir / "case.json"
    if not case_path.is_file():
        found = sorted(input_dir.rglob("case.json"))
        case_path = found[0] if found else None
    case = load_json(case_path) if case_path else None
    if case_path and not isinstance(case, dict):
        case = {}
    task_path = input_dir / "task.md"
    task_text = task_path.read_text(encoding="utf-8-sig") if task_path.is_file() else ""

    root = input_dir
    if isinstance(case, dict) and case.get("materials_root"):
        candidate = input_dir / str(case["materials_root"])
        if candidate.is_dir():
            root = candidate
    exclude = {"case.json", "task.md", "README.md"}
    docs, supplements, problems = [], [], []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in exclude or path.name.startswith("."):
            continue
        rel = path.relative_to(root).as_posix()
        if "/work/" in "/%s/" % rel or rel.startswith("work/"):
            continue
        suffix = path.suffix.lower()
        if suffix in DOC_SUFFIXES:
            if path.stat().st_size == 0:
                problems.append("%s is empty" % rel)
                continue
            docs.append(path)
        elif suffix in CODE_SUFFIXES:
            supplements.append(path)
    # explicit material list in the case overrides / adds to the scan
    if isinstance(case, dict):
        for item in case.get("materials") or []:
            rel = item.get("path") if isinstance(item, dict) else str(item)
            if not rel:
                continue
            path = (input_dir / rel)
            if path.is_file() and path not in docs:
                docs.append(path)
    return case_path, case or {}, task_text, docs, supplements, problems


def read_documents(paths):
    docs, warnings = [], []
    for idx, path in enumerate(paths, 1):
        try:
            record = pn.read_material(path)
        except Exception as exc:  # noqa: BLE001
            warnings.append("%s could not be read: %s" % (path.name, exc))
            continue
        record["doc_id"] = "d%d" % idx
        if record.get("extraction_status") == "no_text_layer":
            warnings.append("%s has no usable text layer; OCR was unavailable" % path.name)
        text = "\n".join(record.get("pages") or [])
        if len(text.strip()) < 20:
            warnings.append("%s yielded too little text to read" % path.name)
            if re.search(r"\[[^\]]{0,6}(待写|待补充|todo|tbd)[^\]]{0,6}\]", text, re.I):
                warnings.append("%s contains an unfinished-text marker" % path.name)
            continue
        docs.append(record)
    return docs, warnings


def order_documents(docs):
    """Primary paper = the richest readable document; others become supplements."""
    def rank(doc):
        text = "\n".join(doc.get("pages") or [])
        suffix_bonus = {".pdf": 3, ".docx": 2}.get(Path(doc["file"]).suffix.lower(), 1)
        return (len(text), suffix_bonus)
    return sorted(docs, key=rank, reverse=True)


# --------------------------------------------------------------------------
# case → questions, contract
# --------------------------------------------------------------------------
def questions_from(case, task_text):
    """Questions come from the case itself; the generic task brief is never mined
    for questions (that would invent deliverables the case did not ask for)."""
    raw = []
    if isinstance(case, dict):
        for key in ("questions", "question", "tasks"):
            value = case.get(key)
            if isinstance(value, list):
                raw += [v.get("question") if isinstance(v, dict) else v for v in value]
            elif isinstance(value, str):
                raw.append(value)
        if isinstance(case.get("instruction"), str):
            raw.append(case["instruction"])
    cleaned = []
    for item in raw:
        item = norm(item)
        if len(item) >= 8 and item not in cleaned:
            cleaned.append(item)
    if not cleaned:
        return DEFAULT_QUESTIONS, True
    return cleaned[:6], False


def contract_of(case):
    value = case.get("output_contract") if isinstance(case, dict) else None
    return value if isinstance(value, dict) else {}


# --------------------------------------------------------------------------
# note assembly
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
def run(args):
    t0 = time.time()
    input_dir = Path(args.input).resolve()
    out_dir = Path(args.out).resolve()
    work_dir = Path(args.work).resolve() if args.work else out_dir / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    case_path, case, task_text, doc_paths, supp_paths, problems = discover(input_dir, args.case)
    case_id = None
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id", "task_id"):
            if isinstance(case.get(key), str) and case[key].strip():
                case_id = case[key].strip()
                break
    contract = contract_of(case)

    docs, warnings = read_documents(doc_paths)
    warnings = problems + warnings
    docs = order_documents(docs)
    supplements = pnt.code_metrics(supp_paths)

    languages = (case.get("language") if isinstance(case, dict) else None) or "en"
    change_log = [{"step": "scan", "action": "discovered input",
                   "detail": "%d document(s), %d supplement(s)" % (len(docs), len(supp_paths))}]

    if not docs:
        result = _empty_result(case_id, contract, warnings, str(input_dir), str(out_dir), t0)
        write_outputs(out_dir, work_dir, result, {}, {})
        print(json.dumps({"status": result["status"], "case_id": case_id,
                          "sections": 0, "anchors": 0, "answers": 0, "ready": False},
                         ensure_ascii=False))
        return result

    primary = docs[0]
    doc_pages = {}
    for doc in docs:
        doc_pages[doc["doc_id"]] = doc.get("pages") or []
        write_json(work_dir / "text" / ("%s.json" % doc["doc_id"]),
                   {"doc_id": doc["doc_id"], "file": doc["file"],
                    "pages": [{"page": i + 1, "paras": p.splitlines()} for i, p in enumerate(doc.get("pages") or [])]})
    title, sections = pn.split_sections(primary)
    detected = len([s for s in sections if s["role"] not in pn.SKIP_ROLES])
    if not sections:
        warnings.append("no section structure could be recovered from the primary document")

    anchor_for, evidence, page_of = pnt.make_anchor_store(primary["doc_id"])
    notes, _ = pnt.build_notes(sections, primary["doc_id"], anchor_for)
    card, not_reported_card = pnt.build_card(sections, anchor_for)

    raw_kps = pn.knowledge_points(sections, anchor_for, primary["doc_id"],
                                  extra_aliases=_alias_map(supplements))

    questions, defaulted = questions_from(case, task_text)
    answers = pnt.build_answers(questions, sections, card, raw_kps, anchor_for, notes, page_of)
    evidence = list(evidence)  # answer/keypoint anchors were appended in place

    uncertainties = []
    if primary.get("backend") == "plaintext":
        uncertainties.append({"item": "page numbers",
                              "why": "plain-text input has no physical pages; anchors use a virtual page",
                              "what_would_resolve": "supply the typeset PDF"})
    if warnings:
        uncertainties += [{"item": "input warning", "why": w, "what_would_resolve": "inspect or replace the file"}
                          for w in warnings]
    if defaulted:
        uncertainties.append({"item": "questions", "why": "the case supplied no explicit questions; the three standard deliverables were used",
                              "what_would_resolve": "add a questions list to the case input"})
    for note in notes:
        if not note.get("methods") and note.get("role") in ("methods", "results"):
            uncertainties.append({"item": "%s field" % note["section_id"],
                                  "why": "the section states no extractable field for this role",
                                  "what_would_resolve": "read the section on the page"})

    reproduction = {"paper_metrics": pnt.paper_metrics(section_text_all(sections)),
                    "candidates": []}
    for cand in supplements:
        deltas = {}
        for key, value in cand["metrics"].items():
            base = reproduction["paper_metrics"].get(key)
            if base is not None and abs(base - value) > 0.002:
                deltas[key] = {"paper": base, "candidate": value}
        reproduction["candidates"].append({"file": cand["file"], "metrics": cand["metrics"],
                                           "deltas": deltas})
        if deltas:
            uncertainties.append({
                "item": "candidate %s disagrees with the paper" % cand["file"],
                "why": "; ".join("%s paper=%s candidate=%s" % (k, v["paper"], v["candidate"])
                                 for k, v in sorted(deltas.items())),
                "what_would_resolve": "rerun the candidate under the paper's stated setup, or report the run variance"})

    not_reported = list(not_reported_card)
    for key in ("research_question", "data", "limitations"):
        if not norm((card.get(key) or {}).get("text")) or \
                str((card.get(key) or {}).get("text", "")).startswith("所给材料未"):
            if not any(item.get("item") == key for item in not_reported):
                not_reported.append({"item": key, "why_expected": "the field is part of the paper card"})

    section_map = {"document_title": title, "doc_id": primary["doc_id"],
                   "sections": [{"section_id": "S%02d" % (i + 1), "title": s["title"],
                                 "role": s["role"], "page_start": s["page_start"],
                                 "page_end": s["page_end"],
                                 "sentences": len(s["sentences"])} for i, s in enumerate(sections)]}
    write_json(work_dir / "section_map.json", section_map)
    write_text(work_dir / "digest.md", _digest(title, sections))
    draft = {"case_id": case_id, "section_notes": notes, "paper_card": card,
             "answers": answers, "knowledge_points": raw_kps,
             "uncertainties": uncertainties, "not_reported": not_reported}
    write_json(work_dir / "notes_draft.json", draft)

    claims = []
    for note in notes:
        for field in ("purpose", "methods", "results", "conclusions"):
            if note.get(field):
                claims.append({"claim_id": "CL%02d" % (len(claims) + 1),
                               "section_id": note["section_id"], "field": field,
                               "text": note[field], "anchors": note.get("anchors") or []})
    claims = claims[:60]

    documents = [{"doc_id": d["doc_id"], "file": d["file"], "path": d["path"],
                  "sha256": d.get("sha256"), "bytes": d.get("bytes"),
                  "pages": len(d.get("pages") or []), "backend": d.get("backend"),
                  "extraction_status": d.get("extraction_status"),
                  "warnings": d.get("warnings") or []} for d in docs]

    result = {
        "schema_version": "paper-notes/1",
        "case_id": case_id,
        "status": "partial",
        "status_reason": "",
        "language": languages,
        "documents": documents,
        "answers": answers,
        "section_notes": notes,
        "paper_card": card,
        "knowledge_points": raw_kps,
        "evidence": evidence,
        "uncertainties": uncertainties,
        "not_reported": not_reported,
        "sources": [{"doc_id": d["doc_id"], "file": d["file"], "pages": len(d.get("pages") or []),
                     "sha256": d.get("sha256")} for d in docs],
        "change_log": change_log + [
            {"step": "section", "action": "split by the paper's own headings",
             "detail": "%d section(s), %d note(s)" % (len(sections), len(notes))},
            {"step": "anchor", "action": "bound notes to verbatim quotes",
             "detail": "%d anchor(s)" % len(evidence)},
            {"step": "answer", "action": "answered the case questions", "detail": "%d answer(s)" % len(answers)}],
        "reproduction": reproduction,
        "result": {"document_title": title, "sections": len(notes),
                   "anchors": len(evidence), "knowledge_points": len(raw_kps),
                   "answers": len(answers)},
        "claims": claims,
        "output_contract": contract,
    }
    for key, value in contract.items():
        result.setdefault(key, value)
    unfilled = [k for k in contract if result.get(k) in (None, "", [], {})]
    if unfilled:
        not_reported.append({"item": "contract fields without a deterministic source",
                             "why_expected": ", ".join(unfilled)})

    result["status"], result["status_reason"] = decide_status(
        result, notes, evidence, raw_kps, unfilled, warnings, primary)
    report = pn.self_check(result, doc_pages, contract, detected, material_missing=False)
    if report["blocking_failures"] and result["status"] == "success":
        result["status"] = "partial"
        result["status_reason"] = "self-check blocked success: %s" % ", ".join(report["blocking_failures"])
        report = pn.self_check(result, doc_pages, contract, detected, material_missing=False)
    result["self_check"] = report
    if result["status"] != "success" and not result["status_reason"]:
        result["status_reason"] = "notes are complete for the readable material but not every field is anchored"

    write_outputs(out_dir, work_dir, result, doc_pages, section_map)
    print(json.dumps({"status": result["status"], "case_id": case_id,
                      "sections": len(notes), "anchors": len(evidence),
                      "answers": len(answers), "ready": report["ready_to_submit"]},
                     ensure_ascii=False))
    return result


def section_text_all(sections):
    return "\n".join(pn.section_text(s) for s in sections)


def _alias_map(supplements):
    """Map a code metric key to the canonical term so it can become a synonym."""
    aliases = {}
    for cand in supplements:
        for key in cand["metrics"]:
            canonical = key.replace("_", " ").replace("top1", "top-1")
            aliases[key] = canonical
    return aliases


def _digest(title, sections):
    lines = ["# Digest — %s" % (title or "paper")]
    for i, section in enumerate(sections, 1):
        lines += ["", "## S%02d %s [%s]" % (i, section["title"], section["role"])]
        for sentence in section["sentences"][:6]:
            lines.append("- %s" % clip(sentence["quote"], 200))
    return "\n".join(lines) + "\n"


def decide_status(result, notes, evidence, kps, unfilled, warnings, primary):
    if not notes:
        return "unable_to_determine", "no section with readable text could be recovered"
    if primary.get("extraction_status") == "no_text_layer":
        return "partial", "the primary document has no usable text layer; OCR was unavailable"
    if unfilled:
        return "partial", "the case contract asks for field(s) with no deterministic source: %s" % ", ".join(unfilled)
    if not evidence:
        return "partial", "no verbatim anchor could be bound to the source text"
    if any("too little text" in w for w in warnings):
        return "partial", "some input files were unreadable or empty"
    if len(kps) < 3:
        return "partial", "only %d knowledge point(s) were extractable; the reading may be thin" % len(kps)
    return "success", ""


def _empty_result(case_id, contract, warnings, input_dir, out_dir, t0):
    result = {
        "schema_version": "paper-notes/1", "case_id": case_id,
        "status": "unable_to_determine",
        "status_reason": "no readable paper material was supplied; nothing was read or invented",
        "language": None,
        "documents": [], "answers": [], "section_notes": [], "paper_card": {},
        "knowledge_points": [], "evidence": [], "uncertainties": [
            {"item": "material", "why": "no readable document was found under the input",
             "what_would_resolve": "supply the paper as PDF, DOCX or text"}],
        "not_reported": [{"item": "paper", "why_expected": "every requested field depends on it"}],
        "sources": [], "change_log": [{"step": "scan", "action": "no material",
                                       "detail": "; ".join(warnings) or "empty input"}],
        "reproduction": {}, "result": {"document_title": None, "sections": 0, "anchors": 0,
                                       "knowledge_points": 0, "answers": 0},
        "claims": [], "self_check": {"ready_to_submit": False, "weighted_score": 0.0,
                                     "blocking_failures": [], "checks": []},
        "output_contract": contract,
    }
    for key, value in contract.items():
        result.setdefault(key, value)
    return result


def write_outputs(out_dir, work_dir, result, doc_pages, section_map):
    write_json(out_dir / "result.json", result)
    write_text(out_dir / "notes.md", pnt.render_notes(result))
    pnt.write_anchors_csv(out_dir / "anchors.csv", result, doc_pages)
    write_json(work_dir / "selfcheck.json", result.get("self_check") or {})
    write_json(work_dir / "notes_draft.json", {"case_id": result.get("case_id"),
                                               "section_notes": result.get("section_notes"),
                                               "paper_card": result.get("paper_card"),
                                               "answers": result.get("answers"),
                                               "knowledge_points": result.get("knowledge_points"),
                                               "uncertainties": result.get("uncertainties"),
                                               "not_reported": result.get("not_reported")})


def main(argv=None):
    parser = argparse.ArgumentParser(description="structured paper notes")
    sub = parser.add_subparsers(dest="command")
    for name in ("all", "prepare", "finalize", "check", "doctor"):
        p = sub.add_parser(name)
        p.add_argument("--input", default="/input")
        p.add_argument("--out", default="/app/output")
        p.add_argument("--work", default=None)
        p.add_argument("--case", default=None)
        p.add_argument("--result", default=None)
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args.command = "all"
        args.input, args.out, args.work = "/input", "/app/output", None
        args.case = args.result = None
    try:
        if args.command == "doctor":
            case_path, case, task_text, docs, supps, problems = discover(args.input, args.case)
            print(json.dumps({"case_found": bool(case_path), "case_id": (case or {}).get("case_id"),
                              "documents": [str(p) for p in docs],
                              "supplements": [str(p) for p in supps],
                              "problems": problems}, ensure_ascii=False))
            return 0
        if args.command == "check" and args.result:
            result = load_json(args.result) or {}
            doc_pages = {}
            text_dir = (Path(args.work).resolve() if args.work else Path(args.out).resolve() / "work") / "text"
            candidates = sorted(text_dir.glob("*.json")) if text_dir.is_dir() else []
            for path in candidates:
                record = load_json(path) or {}
                doc_pages[record.get("doc_id")] = ["\n".join(p.get("paras") or [])
                                                   for p in record.get("pages") or []]
            report = pn.self_check(result, doc_pages, result.get("output_contract") or {},
                                   len(result.get("section_notes") or []), False)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        run(args)
    except Exception as exc:  # noqa: BLE001 — always exit 0 with a valid result.json
        sys.stderr.write("paper_notes.py internal error: %s\n" % exc)
        try:
            out = Path(getattr(args, "out", "/app/output")).resolve()
            out.mkdir(parents=True, exist_ok=True)
            write_json(out / "result.json", {
                "schema_version": "paper-notes/1", "case_id": None,
                "status": "unable_to_determine", "status_reason": "internal error: %s" % exc,
                "language": None,
                "documents": [], "answers": [], "section_notes": [], "paper_card": {},
                "knowledge_points": [], "evidence": [], "uncertainties": [
                    {"item": "internal error", "why": str(exc), "what_would_resolve": "inspect the input"}],
                "not_reported": [], "sources": [], "change_log": [], "reproduction": {},
                "result": {}, "claims": [], "self_check": {"ready_to_submit": False},
                "output_contract": {}})
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
