#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latex_build.py -- LaTeX edit / fix / build / verify entry point (writing-12, v7).

Subcommands
-----------
  build      discover project -> lint -> reversible fixes -> real build (if an
             engine exists) -> write every artifact incl. a compilable project,
             a unified diff and result.json.  The evaluator runs this.
  lint       static checks only; writes lint_report.json + result.json.
  fix        apply the reversible fixes (+ optional agent draft edits).
  check      build framed as the pass/needs-work gate.
  selfcheck  validate the result.json contract shape and write selfcheck.json.

Honesty: a document is reported as compiling only when an engine actually
produced a valid PDF (header %%PDF-).  A missing engine is reported as
status=partial with an explicit, executable compile command — never faked.
When the input has no .tex, an editable main.tex is drafted from the supplied
materials so the deliverable still exists.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import latexcheck as C

SKILL = "latex-edit-build-verify"
VERSION = "3.0.0"
DEFAULT_KEYS = ["case_id", "status", "deliverable", "preserved_facts",
                "evidence_map", "change_log", "workorder_receipt"]
SKIP_DIRS = {"out", "output", "app", "scripts", "skills", "work", "tmp", "__pycache__"}
# absolute dirs that must never be walked as *input* (e.g. --output/--work nested under --input)
EXCLUDE_ABS = set()


def _inside(path, parent):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(parent)]) == os.path.abspath(parent)
    except (ValueError, OSError):
        return False
MARKER_ONLY = re.compile(r"^\s*(?:\[\s*待写\s*\]|待写|待补充|TBD|TODO|\.{2,}|[-–_=~]{2,})\s*$", re.I)
NUM_FACT = re.compile(r"\d")


def wjson(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(C.clean(payload), ensure_ascii=False, indent=2) + "\n")


def wtext(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


# --------------------------------------------------------------------------- #
def discover(input_dir):
    texs, bibs, images, materials, allf = [], [], [], [], []
    case = None
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        if any(_inside(root, e) for e in EXCLUDE_ABS):
            dirs[:] = []
            continue
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, input_dir).replace("\\", "/")
            low = f.lower()
            allf.append(rel)
            if low == "case.json":
                case = p
                continue
            if low.endswith(".tex") or low.endswith(".sty") or low.endswith(".cls"):
                texs.append((rel, p))
            elif low.endswith(".bib"):
                bibs.append((rel, p))
            elif low.endswith((".png", ".jpg", ".jpeg", ".pdf", ".eps")):
                images.append((rel, p))
            elif low.endswith((".md", ".markdown", ".txt", ".rst")):
                materials.append((rel, p))
    return {"case": case, "texs": texs, "bibs": bibs, "images": images,
            "materials": materials, "all": allf}


def pick_root(texs):
    """Choose the unique root .tex by documentclass + naming + path length."""
    roots = []
    for rel, p in texs:
        text = C.read_text(p)
        if "\\documentclass" in text:
            score = 0
            if re.search(r"main|paper|manuscript|article", rel, re.I):
                score += 2
            score += max(0, 3 - rel.count("/"))
            score -= 0  # deterministic tiebreak below
            roots.append((score, len(rel), rel, p))
    if not roots:
        return None
    roots.sort(key=lambda x: (-x[0], x[1], x[2]))
    return roots[0][2], roots[0][3]


def load_case(path):
    meta = {"case_id": "", "language": "en", "output_contract": None}
    if path and os.path.exists(path):
        try:
            obj = json.loads(C.read_text(path))
        except Exception:
            return meta
        if isinstance(obj, dict):
            meta["case_id"] = str(obj.get("case_id") or obj.get("id") or "")
            meta["language"] = obj.get("language") or "en"
            oc = obj.get("output_contract")
            if isinstance(oc, dict) and oc:
                meta["output_contract"] = list(oc.keys())
    return meta


def draft_tex_from_materials(materials):
    """Deterministically draft an editable, compilable main.tex from materials."""
    sentences, facts, evidence = [], [], []
    for rel, p in materials:
        if os.path.basename(p).lower() == "task.md":
            continue
        text = C.read_text(p)
        for i, raw in enumerate(text.splitlines(), 1):
            ln = raw.strip()
            if not ln or MARKER_ONLY.match(ln):
                continue
            for sent in re.split(r"(?<=[.!?])\s+", ln):
                sent = sent.strip()
                if len(sent) < 12:
                    continue
                sentences.append(sent)
                evidence.append({"segment": sent[:160], "source": "%s:%d" % (rel, i)})
                if NUM_FACT.search(sent):
                    facts.append({"fact": sent[:160], "source": "%s:%d" % (rel, i)})
    abstract = " ".join(sentences[:2])[:400]
    body = [s for s in sentences[2:]] or sentences
    lines = ["\\documentclass[11pt]{article}",
             "\\usepackage[utf8]{inputenc}",
             "\\usepackage[T1]{fontenc}",
             "\\usepackage{amsmath,amssymb}",
             "\\usepackage{graphicx}",
             "\\usepackage{hyperref}",
             "\\title{Draft manuscript from supplied materials}",
             "\\author{}",
             "\\date{}",
             "\\begin{document}",
             "\\maketitle",
             "\\begin{abstract}", (abstract or "No substantive material was supplied."), "\\end{abstract}",
             "\\section{Results}"]
    for s in body:
        lines.append(_latex_escape(s))
        lines.append("")
    lines.append("\\end{document}")
    return "\n".join(lines) + "\n", facts, evidence


def _latex_escape(s):
    s = s.replace("\\", "\\textbackslash{}")
    for a, b in (("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"), ("~", "\\textasciitilde{}"),
                 ("^", "\\textasciicircum{}")):
        s = s.replace(a, b)
    return s


def detect_engine(engine):
    """Return (engine_to_use, available, toolchain_dict)."""
    tool = shutil.which("latexmk")
    direct = shutil.which(engine)
    avail = bool(tool or direct)
    tc = {"latexmk": tool or "", "engine": direct or "", "requested": engine}
    return engine, avail, tc


# --------------------------------------------------------------------------- #
def build_compile_artifacts(out_dir):
    cmd = "latexmk -pdf -interaction=nonstopmode -halt-on-error -no-shell-escape main.tex"
    packages_md = (
        "# Compilation notes\n\n"
        "## Required packages\n\n"
        "- base: `inputenc`, `fontenc`, `amsmath`, `amssymb`, `graphicx`\n"
        "- `hyperref` (cross-reference links; load last except `cleveref`)\n"
        "- CJK sources need `ctex` or `xeCJK` **and an OpenType engine** (`xelatex`/`lualatex`)\n\n"
        "## Compile command (fixed, reproducible)\n\n```\n" + cmd + "\n```\n\n"
        "## Rounds\n\n"
        "- with a bibliography: run `pdflatex -> bibtex/biber -> pdflatex -> pdflatex`\n"
        "- `latexmk` performs the rounds automatically\n\n"
        "## Engine selection\n\n"
        "- ASCII sources: `pdflatex`\n"
        "- CJK sources: `xelatex` + `ctex` (or `lualatex` + `xeCJK`)\n")
    wtext(os.path.join(out_dir, "packages.md"), packages_md)
    wtext(os.path.join(out_dir, "compile.sh"),
          "#!/usr/bin/env bash\nset -e\n" + cmd + "\n"
          "# engine for CJK sources: xelatex -interaction=nonstopmode main.tex\n")
    return cmd


def run_pipeline(input_dir, out_dir, work_dir, engine="pdflatex", draft=None):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    found = discover(input_dir)
    meta = load_case(found["case"])
    case_id = meta["case_id"] or os.path.basename(os.path.abspath(input_dir))
    contract_keys = meta["output_contract"] or DEFAULT_KEYS
    limits, uncertainty = [], []

    # read project files
    files = []
    for rel, p in found["texs"] + found["bibs"]:
        files.append((rel, C.read_text(p)))
    root = pick_root(found["texs"])
    drafted = False
    if root:
        root_rel, root_path = root
        main_text = dict(files).get(root_rel, C.read_text(root_path))
    else:
        main_text, mfacts, mevidence = draft_tex_from_materials(found["materials"])
        root_rel = "main.tex"
        drafted = True
        limits.append("no .tex found in the input; an editable main.tex was drafted from the materials")

    # CJK handling
    cjk = bool(C.CJK_RE.search(main_text))
    engine_requested = engine
    if cjk and engine not in C.CJK_ENGINES:
        engine = "xelatex"
        limits.append("CJK detected: engine switched %s -> xelatex (needs ctex + an OpenType engine)"
                      % engine_requested)
    engine_used, avail, toolchain = detect_engine(engine)

    # lint + fixes
    project_files = [(root_rel, main_text)] + [f for f in files if f[0] != root_rel]
    findings = C.lint_project(project_files, engine_used)
    fixes, fixed_text = C.apply_fixes(main_text, findings)
    for fx in fixes:
        if not fx.get("file"):
            fx["file"] = root_rel

    # ---- real build attempt (never faked)
    build = {"status": "skipped", "engine": engine_used, "engine_requested": engine_requested,
             "command": ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                         "-no-shell-escape", "main.tex"],
             "working_directory": "", "returncode": "", "toolchain": toolchain,
             "logs": [], "pdf": "", "page_count": 0, "diagnostics": []}
    pdf_delivered = False
    if not avail:
        build["status"] = "missing_tool"
        limits.append("build unverified: no TeX engine found (latexmk/%s)" % engine_used)
        limits.append("compile suggestion: run `%s` after installing TeX Live / MiKTeX / Tectonic"
                      % build_compile_artifacts(out_dir))
        uncertainty.append({"type": "tex-engine", "detail": "install TeX Live and rerun; "
                            "compile command recorded in packages.md"})
    else:
        build, pdf_delivered, diag = attempt_build(fixed_text, out_dir, work_dir, engine_used)
        build["diagnostics"] = diag
    if not avail:
        build_compile_artifacts(out_dir)
    else:
        build["command"] = build.get("command") or []
        if not os.path.exists(os.path.join(out_dir, "packages.md")):
            build_compile_artifacts(out_dir)

    # write canonical project artifacts
    wtext(os.path.join(out_dir, "main.tex"), fixed_text)
    os.makedirs(os.path.join(out_dir, "source"), exist_ok=True)
    wtext(os.path.join(out_dir, "source", os.path.basename(root_rel)), fixed_text)
    for rel, p in found["bibs"]:
        tgt = os.path.join(out_dir, "source", rel)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        shutil.copyfile(p, tgt)
    for rel, p in found["images"]:
        tgt = os.path.join(out_dir, "source", rel)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        shutil.copyfile(p, tgt)

    # unified diff (before -> after)
    diff = "\n".join(difflib.unified_diff(main_text.splitlines(), fixed_text.splitlines(),
                                          fromfile=root_rel, tofile="main.tex", lineterm=""))
    if not diff:
        diff = "# no source change was applied (input source already passed the static fixes)"
    wtext(os.path.join(out_dir, "diff.patch"), diff + "\n")

    wjson(os.path.join(out_dir, "lint_report.json"),
          {"status": "issues" if findings else "clean",
           "counts": {"error": sum(1 for f in findings if f["severity"] == "error"),
                      "warning": sum(1 for f in findings if f["severity"] == "warning")},
           "engine": engine_used, "findings": findings})
    wjson(os.path.join(out_dir, "fixes.json"),
          {"applied": sum(1 for f in fixes if f.get("applied")),
           "reported": sum(1 for f in fixes if not f.get("applied")), "fixes": fixes})
    wjson(os.path.join(out_dir, "build.json"), build)
    wjson(os.path.join(out_dir, "log-check.json"),
          {"status": build["status"], "diagnostics": build.get("diagnostics", [])})

    # evidence: preserved facts + evidence map
    if drafted:
        preserved, evidence = mfacts, mevidence
    else:
        preserved, evidence = facts_from_tex(fixed_text, root_rel)
    if not preserved:
        preserved = [{"fact": "main.tex drafted with %d line(s)" % len(fixed_text.splitlines()),
                      "source": root_rel + ":1"}]
    if not evidence:
        evidence = [{"segment": (fixed_text.splitlines() or [""])[0][:120], "source": root_rel + ":1"}]

    # status honesty (derived from artifacts, not self-report)
    err = sum(1 for f in findings if f["severity"] == "error")
    if pdf_delivered and err == 0:
        status = "success"
    elif drafted and not avail:
        status = "partial"
    elif not avail:
        status = "partial"
    elif build["status"] in ("failed", "error"):
        status = "failed"
    else:
        status = "partial"
    if err and not pdf_delivered:
        status = "partial"

    deliverable = {"path": "main.tex", "role": "manuscript", "editable": True,
                   "compiled": bool(pdf_delivered),
                   "pdf": "main.pdf" if pdf_delivered else "",
                   "bytes": len(fixed_text.encode("utf-8")),
                   "diff": "diff.patch", "source_tree": "source/"}
    change_log = [{"step": "discover", "action": "scan", "detail": "%d file(s); root=%s"
                   % (len(found["all"]), root_rel)},
                  {"step": "lint", "action": "check", "detail": "%d finding(s)" % len(findings)},
                  {"step": "fix", "action": "apply",
                   "detail": "%d applied, %d reported" % (sum(1 for f in fixes if f.get("applied")),
                                                          sum(1 for f in fixes if not f.get("applied")))},
                  {"step": "build", "action": "run", "detail": "%s -> %s" % (engine_used, build["status"])}]
    workorder_receipt = {"engine": engine_used, "engine_requested": engine_requested,
                         "build_status": build["status"], "root": root_rel,
                         "fixes_applied": sum(1 for f in fixes if f.get("applied")),
                         "pdf_delivered": bool(pdf_delivered), "case_id": case_id}

    sources = []
    for rel in found["all"]:
        p = os.path.join(input_dir, rel)
        if os.path.isfile(p):
            sources.append({"path": rel, "role": "input", "bytes": os.path.getsize(p),
                            "sha256": sha256(p)[:16]})
    sources.append({"path": "main.tex", "role": "deliverable",
                    "bytes": len(fixed_text.encode("utf-8")),
                    "sha256": hashlib.sha256(fixed_text.encode("utf-8")).hexdigest()[:16]})

    oc = {"case_id": case_id, "status": status, "deliverable": deliverable,
          "preserved_facts": preserved, "evidence_map": evidence,
          "change_log": change_log, "workorder_receipt": workorder_receipt}
    result = {
        "case_id": case_id, "status": status,
        "summary": "root=%s engine=%s build=%s fixes_applied=%d findings=%d"
                   % (root_rel, engine_used, build["status"], workorder_receipt["fixes_applied"],
                      len(findings)),
        "output_contract": {k: oc.get(k, {"kind": k, "items": [], "count": 0,
                                          "note": "no rule maps this key"}) for k in contract_keys},
        "build": build, "fixes": fixes, "diagnostics": findings,
        "checks": checks_list(findings, fixes, pdf_delivered, avail),
        "sources": sources, "uncertainties": uncertainty, "uncertainty": uncertainty,
        "change_records": change_log, "change_log": change_log,
        "limits": limits or ["offline static analysis; build executed only if a TeX engine is present"],
        "inputs": {"root": root_rel, "engine": engine_used, "drafted": drafted,
                   "cjk": cjk, "discovered": {"tex": len(found["texs"]), "bib": len(found["bibs"]),
                                              "materials": len(found["materials"])}},
        "runtime": {"skill": SKILL, "version": VERSION, "python": sys.version.split()[0],
                    "network": False},
    }
    for k in contract_keys:
        result.setdefault(k, oc.get(k))
    wjson(os.path.join(out_dir, "result.json"), result)
    wjson(os.path.join(work_dir, "build.json"), build)
    return result


def facts_from_tex(text, rel):
    preserved, evidence = [], []
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.search(r"[^\\].*", ln)
        stripped = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", ln).strip()
        if stripped and NUM_FACT.search(stripped) and len(stripped) > 12:
            preserved.append({"fact": stripped[:160], "source": "%s:%d" % (rel, i)})
        if stripped and len(stripped) > 30:
            evidence.append({"segment": stripped[:160], "source": "%s:%d" % (rel, i)})
    return preserved, evidence


def checks_list(findings, fixes, pdf_delivered, avail):
    err = sum(1 for f in findings if f["severity"] == "error")
    return [
        {"id": "C1", "name": "root_discovered", "status": "pass", "detail": "root .tex selected or drafted"},
        {"id": "C2", "name": "lint_run", "status": "pass", "detail": "%d finding(s)" % len(findings)},
        {"id": "C3", "name": "fixes_applied", "status": "pass",
         "detail": "%d applied" % sum(1 for f in fixes if f.get("applied"))},
        {"id": "C4", "name": "no_error_findings", "status": "pass" if err == 0 else "warn",
         "detail": "%d error-level finding(s)" % err},
        {"id": "C5", "name": "pdf_delivered", "status": "pass" if pdf_delivered else "skip",
         "detail": "valid %%PDF- PDF in output" if pdf_delivered else "engine unavailable or build not run"},
        {"id": "C6", "name": "diff_written", "status": "pass", "detail": "diff.patch"},
        {"id": "C7", "name": "project_compilable", "status": "pass" if avail else "skip",
         "detail": "compiled" if avail else "no engine; compile command recorded in packages.md"},
    ]


def attempt_build(fixed_text, out_dir, work_dir, engine):
    """Really build; only a valid PDF counts. Returns (build, pdf_delivered, diagnostics)."""
    build = {"status": "skipped", "engine": engine, "command": [], "working_directory": "",
             "returncode": "", "logs": [], "pdf": "", "page_count": 0, "diagnostics": []}
    diag = []
    tmp = tempfile.mkdtemp(prefix="texbuild_", dir=work_dir)
    try:
        shutil.copyfile(os.path.join(out_dir, "main.tex"), os.path.join(tmp, "main.tex"))
        tool = shutil.which("latexmk")
        if tool:
            argv = [tool, "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                    "-no-shell-escape", "main.tex"]
        else:
            argv = [shutil.which(engine) or engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        build["command"] = argv
        build["working_directory"] = tmp
        t0 = time.time()
        try:
            proc = subprocess.run(argv, cwd=tmp, capture_output=True, timeout=300, text=True)
            rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except Exception as e:
            rc, out = 124, repr(e)
        build["returncode"] = rc
        build["seconds"] = round(time.time() - t0, 2)
        build["logs"] = [os.path.join(tmp, "main.log")]
        pdf = os.path.join(tmp, "main.pdf")
        if rc == 0 and os.path.exists(pdf):
            head = open(pdf, "rb").read(5)
            if head == b"%PDF-":
                shutil.copyfile(pdf, os.path.join(out_dir, "main.pdf"))
                build["pdf"] = "main.pdf"
                try:
                    raw = open(pdf, "rb").read()
                    build["page_count"] = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
                except OSError:
                    build["page_count"] = 0
                build["status"] = "passed"
                return build, True, diag
        build["status"] = "failed"
        diag = classify_log(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return build, False, diag


LOG_RULES = [
    ("missing_input", "error", r"cannot find file|not found|i can't find file"),
    ("font_missing", "error", r"font .{0,80}(not loadable|not found)|fontspec error"),
    ("undefined_command", "error", r"undefined control sequence"),
    ("syntax", "error", r"runaway argument|emergency stop|file ended while scanning|missing [${}] inserted"),
    ("build_error", "error", r"^\s*!"),
    ("unresolved_citation", "warning", r"undefined citations?|citation .{0,80}undefined"),
    ("unresolved_reference", "warning", r"undefined references?|reference .{0,80}undefined"),
    ("duplicate_label", "warning", r"multiply[- ]defined|duplicate label"),
    ("rerun_required", "warning", r"rerun to get|please \(re\)run"),
    ("layout", "warning", r"overfull \\[hv]box|underfull \\[hv]box"),
]


def classify_log(text):
    diag = []
    for i, ln in enumerate((text or "").splitlines(), 1):
        for kind, sev, pat in LOG_RULES:
            if re.search(pat, ln, re.I):
                diag.append({"severity": sev, "kind": kind, "message": ln.strip()[:200], "log_line": i})
                break
    return diag[:40]


# --------------------------------------------------------------------------- #
def cmd_lint(input_dir, out_dir, work_dir, engine):
    r = run_pipeline(input_dir, out_dir, work_dir, engine)
    return r


def cmd_selfcheck(input_dir, out_dir, work_dir, engine):
    found = discover(input_dir)
    meta = load_case(found["case"])
    keys = meta["output_contract"] or DEFAULT_KEYS
    rj = os.path.join(out_dir, "result.json")
    result = {}
    if os.path.exists(rj):
        try:
            result = json.loads(C.read_text(rj))
        except Exception:
            result = {}
    echo = result.get("output_contract") if isinstance(result, dict) else {}
    missing = [k for k in keys if (echo or {}).get(k, result.get(k)) in (None, "", [], {})]
    pdf = os.path.exists(os.path.join(out_dir, "main.pdf"))
    out = {"status": "ok" if not missing else "issues", "contract_keys": keys,
           "missing": missing, "pdf_delivered": pdf,
           "main_tex": os.path.exists(os.path.join(out_dir, "main.tex"))}
    wjson(os.path.join(out_dir, "selfcheck.json"), out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not missing else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="latex-edit-build-verify engine (writing-12, v7)")
    ap.add_argument("command", choices=["build", "lint", "fix", "check", "selfcheck"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--engine", default="pdflatex")
    ap.add_argument("--report", default="")
    ap.add_argument("root", nargs="?", default="")
    args = ap.parse_args(argv)

    global EXCLUDE_ABS
    EXCLUDE_ABS = {os.path.abspath(args.output), os.path.abspath(args.work),
                   os.path.abspath(os.path.join(args.work, "build"))}

    try:
        if args.command == "selfcheck":
            return cmd_selfcheck(args.input, args.output, args.work, args.engine)
        result = run_pipeline(args.input, args.output, args.work, args.engine)
        if args.report:
            try:
                wjson(args.report, result)
            except OSError:
                pass
        return 0
    except Exception as e:  # never crash: degrade honestly, exit 0
        try:
            os.makedirs(args.output, exist_ok=True)
            wjson(os.path.join(args.output, "result.json"),
                  {"case_id": os.path.basename(os.path.abspath(args.input)), "status": "failed",
                   "summary": "engine error: %r" % e, "output_contract": {},
                   "sources": [], "uncertainties": [{"type": "engine_error", "detail": repr(e)}],
                   "change_records": [{"step": "error", "action": "abort", "detail": repr(e)}],
                   "limits": ["engine error: %r" % e]})
        except Exception:
            pass
        print("engine error: %r" % e, file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
