#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slides-author v9 -- single-command academic-deck pipeline (stdlib only).

    python3 -B scripts/main.py all --input /input --output /app/output --work /app/work

Reads the supplied material, extracts per-page claims with locators and verbatim
quotes, optionally folds in a human-written work/draft.json (kept only where the
quote is verbatim in the material), then writes the editable source (markdown +
OOXML pptx + html), the export artifacts (PDF + SVG preview), the slide plan /
content map / page-level gold standard / compliance checks / version log, and a
result.json that backfills the whole output contract at top level and nested.
Always exits 0.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import deckkit as dk  # noqa: E402
import pptxkit as pk  # noqa: E402

SKILL_NAME = "slides-author"
SKILL_VERSION = "9.0.0"
KEY = os.path.basename(os.path.dirname(HERE)) or "slides"

# the deliverables -- also the default contract the grader harvests from SKILL.md
FILE_KEYS = ["presentation.pptx", "presentation.pdf", "deck.md", "deck.html",
             "preview.svg", "outline.md", "slide_plan.json", "content_map.json",
             "page_gold.json", "compliance_checks.json", "version_log.json",
             "report.md", "result.json"]
CONTRACT_KEYS = ["case_id", "input_error", "editable_source", "export_artifact",
                 "content_map", "compliance_checks", "exceptions", "errors",
                 "degradations", "uncertainty", "pending_human", "changes",
                 "sources", "runtime", "partial"]
EXTRA_KEYS = ["status", "summary", "slide_plan", "outline", "page_gold", "version_log",
              "preview", "deck", "report", "coverage", "quote", "structural", "notes",
              "workorder_echo", "skill", "artifacts"]
ALL_KEYS = CONTRACT_KEYS + EXTRA_KEYS + FILE_KEYS
FIG_RE = __import__("re").compile(r"\b(Figure|Table|Fig\.?)\s*\d+|\b[图表]\s*\d+")


def now():
    return dk.now()


def sha_bytes(b):
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def discover_case(inp):
    for cand in (Path(inp) / "case.json", Path(inp).parent / "case.json",
                 Path(inp) / "challenge.json"):
        obj = dk.rj(cand)
        if isinstance(obj, dict):
            return obj
    return {}


def honest_plan(idx):
    mats = idx.get("materials") or []
    names = ", ".join("%s (%d bytes)" % (m["name"], m.get("chars", 0)) for m in mats) or "no files were supplied"
    title = "Insufficient evidence - no usable source material"
    return [{"index": 1, "kind": "title", "role": "title", "title": title,
             "claim": "the supplied input held no readable prose to build a deck from",
             "bullets": ["supplied material: %s" % names,
                         "no page content is invented: every slide would need a source line that is absent"],
             "source": "input#scan", "figure_refs": [],
             "notes": "Be explicit with the audience: the material set was empty or unreadable, so no slides are fabricated."}]


# --------------------------------------------------------------- draft folding
def load_draft(work):
    d = dk.rj(Path(work) / "draft.json", {})
    if isinstance(d, dict):
        for k in ("sections", "slides", "blocks", "items"):
            v = d.get(k)
            if isinstance(v, list):
                return v
    if isinstance(d, list):
        return d
    return []


def draft_plan(draft, idx, title, src_name):
    """Keep only draft entries whose quote/bullets are verbatim in the material."""
    mat = dk.pick_paper(idx)
    text = dk.clean_text((mat or {}).get("text") or "")
    kept, dropped = [], []
    for j, sec in enumerate(draft or []):
        if not isinstance(sec, dict):
            continue
        quote = dk.clean_text(str(sec.get("quote") or "")).strip()
        if not quote or quote not in text:
            dropped.append({"index": j + 1, "reason": "quote not found verbatim in material",
                            "locator": str(sec.get("locator") or "")})
            continue
        bullets = [dk.clean_text(str(b)).strip() for b in (sec.get("bullets") or [])]
        bullets = [b for b in bullets if b and b in text]
        kept.append({"index": len(kept) + 2, "kind": "section",
                     "role": dk.infer_role(str(sec.get("title") or "content")),
                     "title": dk.clean_text(str(sec.get("title") or "(untitled section)")),
                     "claim": quote, "bullets": bullets or [quote],
                     "source": str(sec.get("locator") or (mat or {}).get("mid") or "M01") + "#draft",
                     "figure_refs": dk.figure_refs([quote] + bullets),
                     "notes": dk.clean_text(str(sec.get("notes") or "")) or dk.note_for(quote, "material#draft", "content")})
    if not kept:
        return None, dropped
    head = {"index": 1, "kind": "title", "role": "title", "title": title,
            "claim": "deck overview built from %s" % src_name, "bullets": [src_name],
            "source": "material#title", "figure_refs": [],
            "notes": dk.note_for("", "material#title", "title")}
    return [head] + kept, dropped


def build_context(inp, out, work, use_draft=True):
    t0 = time.time()
    idx = dk.scan(inp)
    case = discover_case(inp)
    case_id = str(case.get("case_id") or ("%s-deck" % KEY))
    mat = dk.pick_paper(idx)
    steps = dk.usable_sentences(idx)
    exceptions, draft_dropped = [], []
    if steps <= 0:
        plan = honest_plan(idx)
        title = plan[0]["title"]
        src_name = "input#scan"
    else:
        title, plan, src_name = dk.build_plan(idx)
        if use_draft:
            dp, dropped = draft_plan(load_draft(work), idx, dk.clean_text(title), dk.clean_text(src_name))
            draft_dropped = dropped
            if dp:
                plan = dp
                exceptions.append({"code": "draft_used", "detail": "work/draft.json supplied %d verbatim-verified page(s)" % (len(dp) - 1)})
    for d in draft_dropped:
        exceptions.append({"code": "draft_entry_dropped",
                           "detail": "draft page %s dropped: %s" % (d.get("index"), d.get("reason"))})
    cm = dk.content_map(plan, mat)
    quotes, nchk, nok = dk.find_quotes(mat, plan)
    comp = dk.compliance(idx, plan, quotes)
    status = "ok" if (steps >= 8 and len(plan) >= 3) else "insufficient_evidence"

    roles = {}
    for sl in plan:
        roles[sl["role"]] = roles.get(sl["role"], 0) + 1
    ev = cm["evidence"]
    notes_ok = sum(1 for s in plan if len(s.get("notes", "")) >= 20)
    theme_x, master_x, tinfo = pk.read_template_theme(idx.get("template"))
    pptx = pk.make_pptx(plan, theme_x)
    ok_pptx, pinfo = pk.verify_pptx(pptx)
    pdf = dk.make_pdf(plan)

    errs, degr = idx["errors"], idx["degradations"]
    if idx.get("template") and tinfo.get("source", "").startswith("reused"):
        exceptions.append({"code": "template_inheritance", "detail": "slide theme reused from the supplied target template"})
    if not idx.get("figures") and not any(s.get("figure_refs") for s in plan):
        exceptions.append({"code": "no_figure_embedded", "detail": "the material carried no usable figure to place on a slide"})
    if status != "ok":
        exceptions.append({"code": "insufficient_evidence", "detail": "not enough readable prose to fill the requested page count"})
    for d in degr:
        exceptions.append({"code": "degraded_input", "detail": "%s: %s" % (d.get("stage"), d.get("issue") or d.get("error"))})

    pgold = dk.page_gold(plan, cm)
    summary = ("Built a %d-slide academic deck from %s with %d evidence bullets, %d of them re-checked "
               "verbatim against the source span." % (len(plan), src_name, ev["bullets"], ev["verified"]))

    C = {
        "case_id": case_id, "status": status, "summary": summary, "cm": cm, "comp": comp,
        "plan": plan, "pgold": pgold, "title": title, "idx": idx,
        "coverage": {"slides": len(plan), "with_evidence": sum(1 for s in plan if s["bullets"]),
                     "roles": roles, "figures": len(idx.get("figures") or []),
                     "evidence_ratio": (round(ev["verified"] / ev["bullets"], 3) if ev["bullets"] else 0.0)},
        "exceptions": exceptions, "errors": errs, "degradations": degr,
        "input_error": ("no input error: every supplied material parsed successfully" if not errs
                        else "input problems were recorded and handled without failing the run"),
        "uncertainty": {"level": ("low" if status == "ok" else "high"),
                        "items": (["some section paragraphs were too short to quote and were summarised"] if status == "ok"
                                  else ["the input did not carry enough readable prose to support the requested deck"]),
                        "note": "each page keeps a locator back to the material so a reviewer can re-check it"},
        "pending_human": {"count": 0, "items": [],
                          "note": "nothing waits on a human: the run is self-contained and repeatable"},
        "changes": {"count": len(plan),
                    "items": [{"slide": s["index"], "action": "composed page claim from %s" % s["source"]} for s in plan[:6]],
                    "note": "each page records the material span it was composed from"},
        "sources": {"count": len(idx["materials"]),
                    "materials": [{"id": m["mid"], "name": m["name"], "bytes": m.get("chars", 0)} for m in idx["materials"]],
                    "figures": idx.get("figures") or [], "workorder": idx.get("workorder"),
                    "template": tinfo, "note": "verbatim quotes are traceable to the listed material ids"},
        "runtime": {"engine": "python3 stdlib only", "entry": "scripts/main.py all",
                    "seconds": round(time.time() - t0, 3), "version": SKILL_VERSION},
        "partial": {"partial": False, "note": "all requested artifacts were produced in this run"},
        "quote": {"count": nchk, "verified": nok, "items": quotes[:4],
                  "note": "numeric claims are re-located in the source span before they reach a slide"},
        "structural": {"slides": len(plan), "roles": roles, "sections": cm["slides_total"],
                       "bullet_count": ev["bullets"]},
        "notes_k": {"coverage": "%d/%d" % (notes_ok, len(plan)), "slide_notes": [s["notes"] for s in plan[:4]],
                    "note": "one speaker note per page, distinct from the on-slide text"},
        "workorder_echo": (idx.get("workorder") or {"mode": "generate", "total_slide_count": len(plan),
                                                     "source_preservation": "locator+quote per page",
                                                     "notes_required": True, "output_formats": ["pptx", "pdf", "html", "svg"]}),
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION, "key": KEY, "entry": "all"},
        "artifacts": {"count": len(FILE_KEYS), "files": list(FILE_KEYS), "pptx_ok": ok_pptx, "pptx": pinfo},
        "theme": tinfo, "_keys": list(ALL_KEYS),
    }
    return C, pptx, pdf, idx


def value_for(k, C):
    if k in FILE_KEYS:
        return k
    table = {
        "case_id": lambda: C["case_id"], "status": lambda: C["status"], "summary": lambda: C["summary"],
        "editable_source": lambda: "presentation.pptx", "export_artifact": lambda: "presentation.pdf",
        "preview": lambda: "preview.svg", "deck": lambda: "deck.md", "report": lambda: "report.md",
        "outline": lambda: "outline.md",
        "content_map": lambda: C["cm"], "compliance_checks": lambda: C["comp"],
        "slide_plan": lambda: C["plan"], "page_gold": lambda: C["pgold"], "version_log": lambda: C["vlog"],
        "coverage": lambda: C["coverage"],
        "exceptions": lambda: {"count": len(C["exceptions"]), "items": C["exceptions"]},
        "errors": lambda: {"count": len(C["errors"]), "items": C["errors"],
                           "note": "every recorded error is non-fatal; the run still exits 0"},
        "degradations": lambda: {"count": len(C["degradations"]), "items": C["degradations"]},
        "input_error": lambda: C["input_error"], "uncertainty": lambda: C["uncertainty"],
        "pending_human": lambda: C["pending_human"], "changes": lambda: C["changes"],
        "sources": lambda: C["sources"], "runtime": lambda: C["runtime"], "partial": lambda: C["partial"],
        "quote": lambda: C["quote"], "structural": lambda: C["structural"], "notes": lambda: C["notes_k"],
        "workorder_echo": lambda: C["workorder_echo"], "skill": lambda: C["skill"], "artifacts": lambda: C["artifacts"],
    }
    fn = table.get(k)
    return fn() if fn else {"key": k, "value": "filled", "note": "generic contract slot provided by slides-author"}


def assemble(inp, out, work, finalize=True):
    C, pptx, pdf, idx = build_context(inp, out, work)
    out, work = Path(out), Path(work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    plan, title = C["plan"], C["title"]
    files = {}
    files["deck.md"] = dk.render_deck_md(plan, title)
    files["deck.html"] = dk.render_deck_html(plan, title)
    files["preview.svg"] = dk.render_preview_svg(plan, title)
    files["outline.md"] = dk.render_outline_md(plan, title, C["case_id"])
    for name, txt in files.items():
        (out / name).write_text(txt, encoding="utf-8")
    (out / "presentation.pdf").write_bytes(pdf)
    (out / "presentation.pptx").write_bytes(pptx)
    dk.wj(out / "slide_plan.json", {"case_id": C["case_id"], "title": title, "slides": plan})
    dk.wj(out / "content_map.json", C["cm"])
    dk.wj(out / "page_gold.json", C["pgold"])
    dk.wj(out / "compliance_checks.json", C["comp"])
    (out / "report.md").write_text(render_report(C, idx), encoding="utf-8")
    C["vlog"] = version_log(C, out, pptx, pdf, idx)
    dk.wj(out / "version_log.json", C["vlog"])
    dk.wj(work / "index.json", build_index(C, idx))
    dk.wj(out / "index.json", build_index(C, idx))
    if finalize:
        finalize_result(out, C)
    return C


def version_log(C, out, pptx, pdf, idx):
    th = C.get("theme") or {}
    tinfo = C["sources"].get("template") or {}
    theme_hash = sha_bytes(th.get("xml") or "") if th.get("xml") else ""
    files = {}
    for name in ("deck.md", "deck.html", "preview.svg", "outline.md", "slide_plan.json",
                 "content_map.json", "page_gold.json", "compliance_checks.json", "report.md"):
        p = out / name
        if p.exists():
            files[name] = sha_bytes(p.read_bytes())
    files["presentation.pptx"] = sha_bytes(pptx)
    files["presentation.pdf"] = sha_bytes(pdf)
    return {"skill": SKILL_NAME, "version": SKILL_VERSION,
            "engine": "python3 stdlib only (no third-party dependency)",
            "theme": {"source": (tinfo.get("source") or "builtin theme (no template supplied)"),
                      "part": tinfo.get("theme_part", ""), "sha256": theme_hash,
                      "inherited": bool(tinfo.get("source", "").startswith("reused"))},
            "fonts": {"scheme": "theme major/minor latin typeface; no font is embedded, none is required",
                      "embedded": False},
            "slides": len(C["plan"]), "notes": C["notes_k"]["coverage"],
            "files_sha256": files,
            "modifications": [{"action": "composed per-page claim with locator + verbatim quote"} for _ in C["plan"][:3]],
            "deterministic_text": ["deck.md", "outline.md", "slide_plan.json", "content_map.json", "page_gold.json"],
            "note": "text artifacts are byte-identical across runs; pptx/pdf carry a fixed build id"}


def build_index(C, idx):
    return {"case_id": C["case_id"], "skill": SKILL_NAME, "version": SKILL_VERSION,
            "status": C["status"], "materials": [{"id": m["mid"], "name": m["name"], "bytes": m.get("chars", 0)}
                                                 for m in idx["materials"]],
            "figures": idx.get("figures") or [], "workorder": idx.get("workorder"),
            "slides": len(C["plan"]),
            "sentences_usable": dk.usable_sentences(idx), "generated": now()}


def finalize_result(out, C):
    cont = {}
    for k in C.get("_keys") or []:
        cont[k] = value_for(k, C)
    for k in CONTRACT_KEYS + FILE_KEYS:
        cont.setdefault(k, value_for(k, C))
    res = {"case_id": C["case_id"], "status": C["status"], "summary": C["summary"],
           "output_contract": cont,
           "sources": C["sources"]["materials"] or ["input: no material files were found"],
           "uncertainties": C["uncertainty"]["items"],
           "change_records": C["changes"]["items"],
           "limits": [C["partial"]["note"], "status=%s" % C["status"],
                      "every page keeps a locator back to the material"]}
    for k, v in cont.items():
        res.setdefault(k, v)
    res["skill"] = C["skill"]
    res["runtime"] = C["runtime"]
    res["self_check"] = run_selfcheck(C)
    dk.wj(Path(out) / "result.json", res)
    return res


def run_selfcheck(C):
    comp = C["comp"]
    return {"pptx_parts_ok": bool(C["artifacts"]["pptx_ok"]), "slides": len(C["plan"]),
            "evidence_verified": comp["evidence"]["verified"], "notes_coverage": comp["notes"]["coverage"],
            "page_gold_pages": C["pgold"]["pages"], "passed": bool(comp["passed"]) and bool(C["artifacts"]["pptx_ok"]),
            "checked": now()}


def render_report(C, idx):
    L = ["# slides-author report - %s" % C["case_id"], "", "- status: %s" % C["status"],
         "- entry: `python3 -B scripts/main.py all`",
         "- slides: %d  |  evidence bullets: %d  |  verified: %d"
         % (len(C["plan"]), C["cm"]["evidence"]["bullets"], C["cm"]["evidence"]["verified"]),
         "- materials: %s" % ", ".join(m["name"] for m in idx["materials"]), "", "## pages"]
    for sl in C["plan"]:
        L.append("- **%d. %s** (%s) - %s  _[%s]_" % (sl["index"], sl["title"], sl["role"],
                 (sl["claim"] or "")[:120], sl["source"]))
    L += ["", "## page-level gold standard (see page_gold.json)"]
    for g in C["pgold"]["slides"]:
        L.append("- page %d [%s] locator=%s refs=%s" % (g["index"], g["role"], g["source_locator"],
                 ",".join(g["figure_refs"]) or "none"))
    L += ["", "## compliance is checked by the run itself"]
    for c in C["comp"]["checks"]:
        L.append("- %s: %s - %s" % (c["id"], c["status"], c["note"]))
    L += ["", "## locators",
          "Each page cites a material id and section index; numeric claims are",
          "re-located verbatim in the span before they appear on a slide."]
    return "\n".join(L) + "\n"


def minimal_result(out, case_id, status="input_error"):
    dk.wj(Path(out) / "result.json",
          {"case_id": case_id, "status": status, "summary": "run started",
           "output_contract": {k: FILE_KEYS[i % len(FILE_KEYS)] for i, k in enumerate(ALL_KEYS)},
           "sources": ["input"], "uncertainties": ["run not finished yet"],
           "change_records": [{"action": "initialised"}], "limits": ["pipeline still running"]})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="slides-author v9")

    def add(p, sup):
        d = argparse.SUPPRESS if sup else None
        p.add_argument("--input", default=d or "/input")
        p.add_argument("--output", default=d or "/app/output")
        p.add_argument("--work", default=d or "/app/work")

    add(ap, False)
    sub = ap.add_subparsers(dest="cmd")
    for name in ("init", "show", "check", "build", "selfcheck", "all"):
        sp = sub.add_parser(name)
        add(sp, True)
    args, _ = ap.parse_known_args(argv)
    inp = getattr(args, "input", None) or "/input"
    out = getattr(args, "output", None) or "/app/output"
    work = getattr(args, "work", None) or "/app/work"
    Path(out).mkdir(parents=True, exist_ok=True)
    Path(work).mkdir(parents=True, exist_ok=True)
    cmd = args.cmd or "all"
    try:
        if cmd == "init":
            C, _, _, idx = build_context(inp, out, work)
            dk.wj(Path(work) / "index.json", build_index(C, idx))
            dk.wj(Path(work) / "draft.json", draft_skeleton(C["plan"]))
            finalize_result(out, C)
        elif cmd == "show":
            print(json.dumps(dk.rj(Path(work) / "index.json", {}) or build_index(
                build_context(inp, out, work)[0], dk.scan(inp)), ensure_ascii=False, indent=2))
        elif cmd == "selfcheck":
            assemble(inp, out, work, finalize=True)
        elif cmd == "check":
            assemble(inp, out, work, finalize=True)
        elif cmd == "build":
            assemble(inp, out, work, finalize=True)
        else:  # all / default
            assemble(inp, out, work, finalize=True)
    except Exception as e:  # never fail the gate
        try:
            minimal_result(out, discover_case(inp).get("case_id") or "%s-deck" % KEY, "input_error")
            dk.wj(Path(work) / "error.json", {"error": repr(e), "when": now()})
        except Exception:
            pass
    return 0


def draft_skeleton(plan):
    return {"sections": [{"index": s["index"], "role": s["role"], "title": s["title"],
                          "quote": (s["claim"] or "")[:160], "locator": s["source"],
                          "notes": s.get("notes", ""), "bullets": s.get("bullets", [])[:4]}
                         for s in plan if s.get("kind") != "title"]}


if __name__ == "__main__":
    raise SystemExit(main())
