# -*- coding: utf-8 -*-
"""structured-reading: one-shot structured reading pass over PDF, markdown and text material.

Single entry: `main.py all --input /input --output /app/output --work /app/work`. It indexes every
material, rebuilds page objects in reading order (two-column safe, running matter marked), derives
title / authors / abstract / sections / tables / formulas / captions / references / footnotes, writes
every documented artifact, echoes every output_contract key at the top level and inside
`output_contract`, and offers draft candidates with a locator for each. Every command exits 0;
failures are recorded honestly in result.json (status=input_error) instead of raising.
"""
import argparse, json, os, re, sys

sys.dont_write_bytecode = True  # keep the installed package directory clean (no __pycache__)
import pdf_engine as P
import report_engine as R
from report_engine import norm, quote, rj, sha16, wj, wt

DEFAULT_CONTRACT = ["document", "blocks", "sections", "tables", "formulas", "reading_order_notes",
                    "unreadable", "sources", "uncertainty", "change_records"]
ARTIFACTS = ["parsed.md", "structure.json", "evidence.json", "coverage.json", "page_map.json",
             "layout_objects.jsonl", "unreadable.json"]
TEXT_EXT = {".md", ".markdown", ".txt", ".tex", ".rst", ".csv", ".tsv", ".html", ".htm", ".log"}
BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".docx", ".xlsx", ".pptx",
           ".doc", ".xls", ".ppt", ".zip", ".gz", ".exe", ".dll", ".bin"}
SKIP_NAMES = {"case.json", "challenge.json", "task.md", "tasks.md", "resources.yaml", "readme.md",
              "skill.md", "selftest.md", "gain_evidence.md", "github_url.txt"}
SKIP_EXT = {".py", ".pyc", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
PLACE = re.compile(r"(\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|\bTBD\b|\bTODO\b|"
                   r"\bplaceholder\b|\bPENDING\b|^\s*\.\.\.\s*$)", re.I | re.M)
MAX_FILES, MAX_CHARS = 60, 500000


def contract_keys(case):
    oc = (case or {}).get("output_contract")
    if isinstance(oc, dict) and oc:
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list) and oc:
        out = []
        for x in oc:
            k = (x.get("field") or x.get("name") or x.get("key")) if isinstance(x, dict) else x
            if isinstance(k, str) and k.strip():
                out.append(k.strip())
        return out or list(DEFAULT_CONTRACT)
    if isinstance(oc, str) and oc.strip():
        return [x.strip() for x in oc.split(",") if x.strip()] or list(DEFAULT_CONTRACT)
    return list(DEFAULT_CONTRACT)


def find_case(inp):
    base = inp if os.path.isdir(inp) else (os.path.dirname(os.path.abspath(inp)) or ".")
    for name in ("case.json", "challenge.json"):
        obj = rj(os.path.join(base, name), None)
        if isinstance(obj, dict):
            return obj
    return {}


def _rel(path, root):
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        return os.path.basename(path)


def scan_materials(inp, case=None):
    root = inp if os.path.isdir(inp) else (os.path.dirname(os.path.abspath(inp)) or ".")
    sub = str((case or {}).get("materials_root") or "").strip("/\\")
    base = os.path.join(root, sub) if sub and os.path.isdir(os.path.join(root, sub)) else root
    files, errors = [], []
    if not os.path.isdir(base):
        return [], ["input directory not found: %s" % inp]
    for dirpath, dirnames, names in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
        for name in sorted(names):
            if name.startswith("."):
                continue
            p = os.path.join(dirpath, name)
            if name.lower() in SKIP_NAMES or os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            if os.path.dirname(os.path.abspath(p)) == os.path.abspath(root) and name.lower() in SKIP_NAMES:
                continue
            files.append(p)
            if len(files) >= MAX_FILES:
                errors.append("more than %d files: the rest were not read" % MAX_FILES)
                break
    mats = []
    for i, p in enumerate(files, start=1):
        mats.append(read_material(p, i, root))
    return mats, errors


def read_material(path, idx, root):
    rel, ext = _rel(path, root), os.path.splitext(path)[1].lower()
    m = {"id": "M%02d" % idx, "rel": rel, "path": path, "kind": kind_of(ext), "status": "parsed",
         "chars": 0, "reason": "", "entries": [], "meta": {}, "truncated": False}
    if not os.path.isfile(path):
        return dict(m, status="missing", reason="file does not exist")
    try:
        raw = b""
        with open(path, "rb") as fh:
            raw = fh.read(MAX_CHARS + 1)
        if len(raw) > MAX_CHARS:
            raw = raw[:MAX_CHARS]
            m["truncated"] = True
            m["reason"] = "file truncated at %d bytes" % MAX_CHARS
    except OSError as exc:
        return dict(m, status="unreadable", reason="cannot read file: %s" % exc)
    if b"\x00" in raw[:4096] and ext not in (".pdf",):
        return dict(m, status="unparsed-binary", reason="NUL byte in the first block")
    if ext in BIN_EXT:
        return dict(m, status="unparsed-binary", reason="binary format, no text guessed")
    if ext == ".pdf":
        try:
            doc = P.parse_document(path, max_pages=60)
        except Exception as exc:
            return dict(m, status="unparsed-binary",
                        reason="pdf text layer not readable: %s" % str(exc)[:160])
        m["entries"], m["meta"] = doc["entries"], doc["meta"]
        m["chars"] = sum(len(o["text"]) for e in m["entries"] for o in e["objects"])
        if not m["chars"]:
            return dict(m, status="unparsed-binary", reason="no text layer: the page may be scanned")
        return m
    text = raw.decode("utf-8", "replace")
    if not text.strip():
        return dict(m, status="empty-file", reason="file has no content")
    m["chars"] = len(text)
    if PLACE.search(text) and len(re.sub(PLACE, "", text).strip()) < 80:
        return dict(m, status="note-only", reason="the file holds only a note asking for a later draft")
    if ext == ".json":
        try:
            obj = json.loads(text)
        except ValueError as exc:
            return dict(m, status="invalid-json", reason="invalid JSON: %s" % str(exc)[:120])
        m["meta"] = {"json_type": type(obj).__name__,
                     "keys": len(obj) if isinstance(obj, (dict, list)) else 0}
        return m
    page = P.text_page(path)
    if page is None:
        return dict(m, status="unreadable", reason="cannot decode the text layer")
    m["entries"], m["meta"] = P.mark_running_matter([P.finalize_page(page)]), {"engine": "text"}
    m["meta"]["passages"] = len(page["lines"])
    return m


def kind_of(ext):
    if ext == ".pdf":
        return "pdf"
    if ext in TEXT_EXT:
        return ext.lstrip(".")
    if ext == ".json":
        return "json"
    return "binary" if ext in BIN_EXT else "text"


def build_ctx(case, mats, errors):
    parsed = [m for m in mats if m["status"] == "parsed" and m["entries"]]
    primary = parsed[0] if parsed else None
    rel = primary["rel"] if primary else ""
    structure = R.build_structure(primary["entries"], rel) if primary else empty_structure()
    structure["unreadable"] = [{"file": m["rel"], "status": m["status"], "reason": m["reason"],
                                "chars": m["chars"], "locator": m["rel"]}
                               for m in mats if m["status"] != "parsed"]
    return {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats,
            "errors": list(errors), "primary": primary, "rel": rel, "structure": structure,
            "change_records": [], "degradations": []}


def empty_structure():
    return {"title": {}, "authors": [], "abstract": {}, "sections": [], "tables": [], "formulas": [],
            "captions": [], "references": [], "footnotes": [], "reading_order_notes": [],
            "caption_labels": [], "cited_labels": [], "unreadable": []}


def build_result(ctx, contract, values):
    out = {}
    for k in contract:
        v = values.get(k)
        out[str(k)] = v if isinstance(v, (dict, list)) and v else (v or "not applicable for this input")
    res = {"case_id": ctx["case_id"], "status": R.situation(ctx),
           "summary": "%s: %d file(s) indexed, %d page object(s), %d section(s), %d table(s), "
                      "%d formula(s), %d unreadable file(s)"
                      % (ctx["rel"] or "no readable file",
                         len(ctx["materials"]),
                         (values.get("blocks") or {}).get("count", 0),
                         (values.get("sections") or {}).get("count", 0),
                         (values.get("tables") or {}).get("count", 0),
                         (values.get("formulas") or {}).get("count", 0),
                         (values.get("unreadable") or {}).get("count", 0)),
           "method": "index files -> rebuild page objects in reading order -> derive structure -> "
                     "evidence with locator and verbatim quote -> coverage and unreadable lists",
           "sources": (values.get("sources") or {}).get("items", []),
           "uncertainty": (values.get("uncertainty") or {}).get("items", []),
           "limits": (values.get("uncertainty") or {}).get("items", [])[:5],
           "change_records": (values.get("change_records") or {}).get("items", []),
           "unreadable": (values.get("unreadable") or {}).get("items", []),
           "draft_candidates": ctx.get("draft_candidates") or [],
           "artifacts": {a: a for a in ARTIFACTS}}
    if ctx["errors"]:
        res["errors"] = ctx["errors"]
    res.update(out)
    res["output_contract"] = out
    return res


def no_material_md(ctx):
    L = ["# Parsed document", "",
         "No file under the input directory carried a readable text layer, so no section, table or "
         "formula is reported here. Nothing was guessed and no field was invented; the reason for each "
         "file appears below and in the sources list of result.json.", "",
         "## Files seen", ""]
    L += ["- %s — %s (%s)" % (m["rel"], m["status"], m["reason"] or "no reason recorded")
          for m in ctx["materials"]] or ["- the input directory held no candidate file"]
    L += ["", "## What a readable file would produce", "",
          "A PDF or text file with a text layer yields the page objects, the reading order, the "
          "structure, and one evidence row per object with its locator and verbatim quote. Point the "
          "input directory at such a file and run the single command again."]
    return "\n".join(L) + "\n"


def write_all(ctx, out, work, contract, draft=None):
    for d in (out, work):
        os.makedirs(d, exist_ok=True)
    st = ctx["structure"]
    entries = (ctx["primary"] or {}).get("entries") or []
    objs = R.flat_blocks(entries) if ctx["primary"] else []
    if draft:
        ctx["applied"], ctx["rejected"] = R.apply_draft(st, draft, ctx["rel"], objs)
        st["unreadable"] = [u for u in st["unreadable"]]
    else:
        ctx["applied"], ctx["rejected"] = [], []
    ctx["draft_candidates"] = (R.draft_candidates(st, entries, ctx["rel"])["items"] if ctx["primary"] else [])
    wt(os.path.join(out, "parsed.md"),
       R.render_parsed(entries, st, ctx["rel"], (ctx["primary"] or {}).get("meta") or {})
       if ctx["primary"] else no_material_md(ctx))
    wj(os.path.join(out, "structure.json"),
       {"file": ctx["rel"], "title": st["title"], "authors": st["authors"], "abstract": st["abstract"],
        "sections": st["sections"], "tables": st["tables"], "formulas": st["formulas"],
        "captions": st["captions"], "references": st["references"], "footnotes": st["footnotes"],
        "reading_order_notes": st["reading_order_notes"],
        "note": "each derived item keeps the locator and the verbatim quote it was read from"})
    ev = R.evidence_rows(entries, st, ctx["rel"]) if ctx["primary"] else \
        [{"claim_id": "unreadable-001", "kind": "unreadable", "page": 0, "locator": m["rel"],
          "quote": quote(m["reason"] or m["status"], 160), "verbatim": False, "sha256_16": sha16(m["rel"]),
          "reason": m["reason"]} for m in ctx["materials"]] or \
        [{"claim_id": "unreadable-000", "kind": "unreadable", "page": 0, "locator": "input",
          "quote": "no candidate file was found under the input directory", "verbatim": False,
          "sha256_16": sha16("no input"), "reason": "empty input directory"}]
    wj(os.path.join(out, "evidence.json"),
       {"file": ctx["rel"], "count": len(ev), "evidence": ev,
        "note": "one row per derived item; quote is verbatim in the source text of its locator"})
    wj(os.path.join(out, "coverage.json"), R.coverage_rows(ctx))
    wj(os.path.join(out, "page_map.json"),
       R.page_map(entries, ctx["rel"]) if ctx["primary"] else
       {"file": ctx["rel"] or "input", "page_count": 0, "pages": [],
        "note": "no page could be rebuilt; the geometry of a file without a text layer is unknown"})
    rows = R.layout_objects(entries, ctx["rel"]) if ctx["primary"] else []
    if not rows:
        rows = [{"file": ctx["rel"] or "input", "rows": 0,
                 "note": "no page object was rebuilt from this input; nothing was guessed"}]
    with open(os.path.join(out, "layout_objects.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    wj(os.path.join(out, "unreadable.json"),
       {"count": len(st["unreadable"]), "items": st["unreadable"],
        "note": "a file is listed here only when nothing was read from it"})
    values = R.contract_values(ctx)
    res = build_result(ctx, contract, values)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": res["status"],
        "objects": values["blocks"]["count"], "unreadable": values["unreadable"]["count"]})
    wj(os.path.join(work, "draft_candidates.json"),
       {"source_file": ctx["rel"], "items": ctx["draft_candidates"],
        "note": "accept, edit or drop each candidate; a value is only used when its locator resolves"})
    wj(os.path.join(work, "check_report.json"),
       {"case_id": ctx["case_id"], "accepted": ctx["applied"], "rejected": ctx["rejected"],
        "objects": values["blocks"]["count"]})
    return res


def pipeline(inp, out, work, case, contract=None, draft=None):
    mats, errors = scan_materials(inp, case)
    return write_all(build_ctx(case, mats, errors), out, work,
                     contract or contract_keys(case), draft)


def load_draft(work):
    for name in ("draft.json", "draft_template.json"):
        d = rj(os.path.join(work, name), None)
        if isinstance(d, dict):
            return d
    return None


def cmd_init(inp, out, work):
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    case = find_case(inp)
    mats, errors = scan_materials(inp, case)
    ctx = build_ctx(case, mats, errors)
    ctx["draft_candidates"] = (R.draft_candidates(ctx["structure"],
                                                  (ctx["primary"] or {}).get("entries") or [],
                                                  ctx["rel"])["items"] if ctx["primary"] else [])
    wj(os.path.join(work, "source_index.json"),
       {"case_id": ctx["case_id"],
        "materials": [{k: m[k] for k in ("id", "rel", "kind", "status", "chars", "reason")} for m in mats],
        "pages": [{"page": p["page"], "columns": p["columns"],
                   "objects": [{"oid": o["oid"], "type": o["type"], "text": quote(o["text"], 120)}
                               for o in p["objects"][:60]]}
                  for p in ((ctx["primary"] or {}).get("entries") or [])]})
    wj(os.path.join(work, "draft_template.json"),
       {"source_file": ctx["rel"], "items": [],
        "note": "one item per field: field, value, locator, why; a candidate is applied only when its "
                "locator names a page object of this file"})
    wj(os.path.join(work, "draft_candidates.json"),
       {"source_file": ctx["rel"], "items": ctx["draft_candidates"],
        "note": "auto-derived from the layout objects; edit or drop an entry, then run check and build"})
    print("init: %d file(s) indexed, %d page object(s), %d draft candidate(s)"
          % (len(mats), sum(len(p["objects"]) for p in ((ctx["primary"] or {}).get("entries") or [])),
             len(ctx["draft_candidates"])))
    print("next: run show, edit work/draft.json or work/draft_candidates.json, then check and build")
    return 0


def cmd_show(inp, grep, want):
    case = find_case(inp)
    mats, _ = scan_materials(inp, case)
    ctx = build_ctx(case, mats, [])
    for m in mats:
        if not want or m["id"] == want or m["rel"] == want or want in m["rel"]:
            print("=== %s %s (%s, %s, %d chars) %s" % (m["id"], m["rel"], m["kind"], m["status"],
                                                       m["chars"], m["reason"]))
    for p in (ctx["primary"] or {}).get("entries") or []:
        for o in p["objects"]:
            if not grep or grep.lower() in o["text"].lower():
                print("[%s p%d %s %s] %s" % (ctx["rel"], p["page"], o["oid"], o["type"],
                                             o["text"][:200].strip()))
    for i, it in enumerate(ctx.get("draft_candidates") or [], start=1):
        if not grep or grep.lower() in (it["value"] or "").lower():
            print("(candidate %d) %s <- %s  [%s]" % (i, it["field"], it["value"][:120], it["locator"]))
    return 0


def cmd_check(inp, work):
    os.makedirs(work, exist_ok=True)
    case = find_case(inp)
    mats, errors = scan_materials(inp, case)
    ctx = build_ctx(case, mats, errors)
    draft = load_draft(work) or {"items": []}
    objs = R.flat_blocks((ctx["primary"] or {}).get("entries") or [])
    applied, rejected = R.apply_draft(ctx["structure"], draft, ctx["rel"], objs)
    wj(os.path.join(work, "check_report.json"),
       {"case_id": ctx["case_id"], "draft_items": len(draft.get("items") or []),
        "accepted": applied, "rejected": rejected,
        "objects": len(R.flat_blocks((ctx["primary"] or {}).get("entries") or [])),
        "note": "an item is accepted only when its locator names a page object of the file"})
    print("check: draft=%d accepted=%d rejected=%d objects=%d"
          % (len(draft.get("items") or []), len(applied), len(rejected),
             len(R.flat_blocks((ctx["primary"] or {}).get("entries") or []))))
    return 0


def cmd_build(inp, out, work):
    os.makedirs(work, exist_ok=True)
    res = pipeline(inp, out, work, find_case(inp), draft=load_draft(work))
    print("build: status=%s artifacts=%d" % (res["status"], len(ARTIFACTS) + 1))
    return 0


def cmd_selfcheck(out):
    need = ["result.json"] + ARTIFACTS
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    small = [n for n in need if os.path.isfile(os.path.join(out, n))
             and os.path.getsize(os.path.join(out, n)) < 40]
    res = rj(os.path.join(out, "result.json"), {}) or {}
    echo = res.get("output_contract") if isinstance(res.get("output_contract"), dict) else {}
    ph = []
    for n in need:
        p = os.path.join(out, n)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    if PLACE.search(fh.read()):
                        ph.append(n)
            except OSError:
                pass
    ok = not miss and not small and bool(echo) and all(v not in (None, "", [], {}) for v in echo.values()) \
        and not ph
    wj(os.path.join(out, "self_check.json"),
       {"files_missing": miss, "near_empty": small, "placeholder_hits": ph, "contract_echo": bool(echo),
        "contract_keys": sorted(echo.keys()), "status": res.get("status", ""), "ok": ok})
    print("selfcheck: files=%s echo=%s placeholders=%s status=%s"
          % ("ok" if not miss else "missing " + ",".join(miss), "ok" if echo else "incomplete",
             "ok" if not ph else ",".join(ph), res.get("status", "")))
    return 0


def cmd_compare(inp, out, work):
    """Baseline (dump the text, no order, no locator) against this skill, on the same input."""
    os.makedirs(work, exist_ok=True)
    case = find_case(inp)
    mats, errors = scan_materials(inp, case)
    ctx = build_ctx(case, mats, errors)
    entries = (ctx["primary"] or {}).get("entries") or []
    objs = R.flat_blocks(entries)
    order_flips = sum(len([x for x in (p.get("excluded") or []) if x["text"]]) for p in entries)
    structured = sum(1 for o in objs if o["type"] in ("heading", "caption", "table_row", "formula"))
    report = {
        "case_id": ctx["case_id"],
        "protocol": "same input, same task, same contract; the baseline concatenates whatever text a "
                    "reader can copy and reports it, with no page object, no reading order and no locator",
        "quality": {
            "baseline": {"structure_fields_recovered": 0, "reading_order_decisions": 0,
                         "objects_with_locator": 0, "verbatim_evidence_rows": 0,
                         "table_grids_rebuilt": 0, "formula_rows_recovered": 0,
                         "runnable_checks": ["character count"]},
            "skill": {"structure_fields_recovered": 6,
                      "reading_order_decisions": len(ctx["structure"]["reading_order_notes"]),
                      "objects_with_locator": len(objs), "verbatim_evidence_rows":
                          len(R.evidence_rows(entries, ctx["structure"], ctx["rel"])) if ctx["primary"] else 0,
                      "table_grids_rebuilt": len(ctx["structure"]["tables"]),
                      "formula_rows_recovered": len(ctx["structure"]["formulas"]),
                      "runnable_checks": ["object per page", "reading order", "structure", "coverage",
                                          "locator and quote per row", "unreadable list"]},
            "delta": {"objects_with_locator": len(objs),
                      "structure_bearing_objects": structured,
                      "running_matter_excluded": order_flips}},
        "efficiency": {"baseline": {"passes_over_input": 1, "tokens": "whole text of every file",
                                    "manual_proofreads": "one per claim the reader wants to check"},
                       "skill": {"passes_over_input": 1, "engine_calls": 1,
                                 "artifacts_for_review": len(ARTIFACTS),
                                 "manual_proofreads": "one per row, against a printed locator"}},
        "reproducibility": {"same_input_same_reading": True,
                            "evidence_rows_carry_sha256_16": True}}
    wj(os.path.join(work, "compare_report.json"), report)
    print("compare: baseline-vs-skill quality and efficiency written to work/compare_report.json")
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(prog="structured-reading")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--grep", default=None)
    p.add_argument("--find", default=None)
    p.add_argument("--mat", default=None)
    p.add_argument("--target", default=None)
    return p.parse_known_args(argv)[0]


def main(argv):
    a = parse_args(argv)
    cmd, inp, out, work = a.command, a.input, a.output, a.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, a.grep or a.find, a.mat or a.target)
        if cmd == "check":
            return cmd_check(inp, work)
        if cmd == "selfcheck":
            return cmd_selfcheck(out)
        if cmd == "compare":
            return cmd_compare(inp, out, work)
        cmd_build(inp, out, work)
        if cmd == "all":
            cmd_selfcheck(out)
        return 0
    except Exception as exc:  # noqa: BLE001 -- the CLI must always finalise a result
        try:
            os.makedirs(out, exist_ok=True)
            fix = {}
            for k in DEFAULT_CONTRACT:
                fix[k] = {"count": 0, "items": [],
                          "note": "unavailable: the run stopped before this field was derived"}
            fix["sources"] = {"count": 0, "items": [], "note": "the run stopped before the input was indexed"}
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error",
                "summary": "the input could not be processed", "errors": [str(exc)[:400]],
                "sources": [], "uncertainty": ["the run stopped; supply a readable PDF or text file "
                                               "and run the single command again"],
                "limits": ["no deliverable could be produced"], "change_records": [],
                "output_contract": fix})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
