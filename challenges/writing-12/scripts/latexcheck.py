#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latexcheck.py -- static LaTeX lint + reversible fixes for writing-12 (v7).

Standard library only; deterministic; no engine required. Two pure entry points:

  lint_project(files, engine)   -> list[finding]
  apply_fixes(main_rel, texts, findings) -> (fixes, new_text)

``files`` is a list of ``(relpath, text)`` for every ``.tex``/``.sty``/``.bib`` in
the project. ``findings`` are ``{id, severity, kind, message, file, line}``.
``fixes`` are ``{id, kind, file, line, before, after, applied, locator, reason}``.

Only *provable, reversible* edits are auto-applied (missing \\end{document},
unclosed environments at EOF, duplicate \\usepackage lines, duplicate \\label).
Semantic problems (undefined refs, unresolved citations, unit spacing, tabular
column mismatch, package order, CJK font) are located and reported, never guessed.
"""
from __future__ import annotations

import os
import re

CJK_RE = re.compile(r"[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7A3]")
CJK_ENGINES = {"xelatex", "lualatex"}
PACKAGE_RE = re.compile(r"\\(?:usepackage|RequirePackage)(?:\[([^\]]*)\])?\{([^}]+)\}")
BEGIN_RE = re.compile(r"\\begin\{([^}]+)\}")
END_RE = re.compile(r"\\end\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref|nameref)\*?\{([^}]+)\}")
CITE_RE = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite|citeauthor)"
                     r"\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}")
BIBFILE_RE = re.compile(r"\\bibliography\{([^}]+)\}")
BIBKEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,")
TABULAR_RE = re.compile(r"\\begin\{(tabular\*?|longtable|array)\}\{([^}]*)\}(.*?)\\end\{\1\}", re.S)
CAPTION_RE = re.compile(r"\\caption")
FLOAT_RE = re.compile(r"\\begin\{(figure\*?|table\*?)\}(.*?)\\end\{\1\}", re.S)
UNIT_BAD_RE = re.compile(
    r"(?<![\\A-Za-z{\d.])(\d+(?:\.\d+)?)(mm|cm|km|min|h|s|kg|mg|g|mol|MPa|kPa|GPa|Pa|"
    r"mL|L|Hz|kHz|MHz|V|mV|A|mA|W|kW|\u00B0C|%)(?![A-Za-z0-9])")
ANGLE_PLACE_RE = re.compile(r"<[A-Za-z_][\w /-]*>")
LINE_LIMIT = 400000


def lineno(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def line_quote(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    end = len(text) if end < 0 else end
    return text[start:end].strip()[:200]


def read_text(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8-sig", "replace")
    except OSError:
        return ""


def clean(obj):
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return ""
    return obj


# --------------------------------------------------------------------------- #
def _strip_verbatim(text: str) -> str:
    """Blank out verbatim/lstlisting bodies so their braces/quotes don't count."""
    def blank(m):
        return "\n" * m.group(0).count("\n")
    return re.sub(r"\\begin\{(verbatim|lstlisting|minted)\}.*?\\end\{\1\}", blank, text, flags=re.S)


def collect_env_stack(text: str):
    """Return (unclosed_envs_outermost_first, mismatched) from \\begin/\\end pairs."""
    stripped = _strip_verbatim(text)
    stack, mismatched, doc_unclosed = [], [], []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", stripped):
        kind, name = m.group(1), m.group(2)
        line = lineno(stripped, m.start())
        if kind == "begin":
            stack.append((name, line))
        elif name == "document":
            while stack and stack[-1][0] != "document":
                doc_unclosed.append(stack.pop())
            if stack and stack[-1][0] == "document":
                stack.pop()
        elif stack and stack[-1][0] == name:
            stack.pop()
        elif any(s[0] == name for s in stack):
            while stack and stack[-1][0] != name:
                mismatched.append(stack.pop())
            if stack:
                stack.pop()
        else:
            mismatched.append((name, line))
    unclosed = list(reversed(doc_unclosed)) + stack
    return unclosed, mismatched


def lint_project(files, engine="pdflatex"):
    findings = []
    def add(kind, severity, message, f, line):
        findings.append({"id": "%s:%s" % (kind, len(findings) + 1), "severity": severity,
                         "kind": kind, "message": message, "file": f, "line": line})

    labels = {}
    all_cite_keys = set()
    bib_keys = set()
    have_bibfile = False
    packages = []
    hyperref_line = cleveref_line = 0
    main_text_used = ""

    for rel, text in files:
        if rel.endswith(".bib"):
            bib_keys |= set(BIBKEY_RE.findall(text))
            continue
        if not rel.endswith(".tex") and not rel.endswith(".sty"):
            continue
        main_text_used = main_text_used or text
        # document structure + environments
        if rel.endswith(".tex"):
            if "\\begin{document}" in text and "\\end{document}" not in text:
                add("document_structure", "error", "\\begin{document} without \\end{document}",
                    rel, lineno(text, text.find("\\begin{document}")))
            unclosed, mismatched = collect_env_stack(text)
            for name, line in unclosed:
                if name not in ("document",):
                    add("environment_mismatch", "error", "unclosed \\begin{%s}" % name, rel, line)
            for name, line in mismatched:
                add("environment_mismatch", "error", "\\end{%s} has no matching \\begin" % name, rel, line)
        # braces
        nb = _strip_verbatim(text)
        nb = re.sub(r"\\[{}]", "", nb)
        if nb.count("{") != nb.count("}"):
            add("unbalanced_braces", "error",
                "brace count %d vs %d" % (nb.count("{"), nb.count("}")), rel, 1)
        # packages
        for m in PACKAGE_RE.finditer(text):
            for pkg in m.group(2).split(","):
                pkg = pkg.strip()
                packages.append((pkg, rel, lineno(text, m.start())))
                if pkg == "hyperref":
                    hyperref_line = hyperref_line or lineno(text, m.start())
                if pkg == "cleveref":
                    cleveref_line = lineno(text, m.start())
        # labels
        for m in LABEL_RE.finditer(text):
            key = m.group(1)
            ln = lineno(text, m.start())
            if key in labels:
                add("duplicate_label", "warning", "duplicate \\label{%s} (first at %s:%d)"
                    % (key, labels[key][0], labels[key][1]), rel, ln)
            else:
                labels[key] = (rel, ln)
        # citations
        for m in CITE_RE.finditer(text):
            all_cite_keys |= set(k.strip() for k in m.group(1).split(",") if k.strip())
        for m in BIBITEM_RE.finditer(text):
            bib_keys.add(m.group(1))
        if BIBFILE_RE.search(text) or any(r.endswith(".bib") for r, _ in files):
            have_bibfile = True
        # graphics + inputs
        for m in GRAPHICS_RE.finditer(text):
            tgt = m.group(1)
            if tgt.startswith("http") or "{" in tgt:
                continue
            base = os.path.dirname(rel)
            cands = [tgt, os.path.join(base, tgt)]
            if not any(os.path.exists(c) or any(os.path.exists(c + e)
                       for e in (".pdf", ".png", ".jpg", ".jpeg", ".eps")) for c in cands):
                add("missing_input", "warning", "\\includegraphics target not found: %s" % tgt,
                    rel, lineno(text, m.start()))
        for m in INPUT_RE.finditer(text):
            tgt = m.group(1)
            cands = [tgt if tgt.endswith(".tex") else tgt + ".tex"]
            if not any(os.path.exists(c) for c in cands):
                add("missing_input", "warning", "\\input target not found: %s" % tgt,
                    rel, lineno(text, m.start()))
        # unit spacing
        for m in UNIT_BAD_RE.finditer(text):
            if m.start() > 0 and text[m.start() - 1] == "}":
                continue
            add("unit_spacing", "warning", "number+unit without \\SI: %s%s" % (m.group(1), m.group(2)),
                rel, lineno(text, m.start()))
        # tabular columns
        for m in TABULAR_RE.finditer(text):
            spec = re.sub(r"[^lcrpX|]", "", m.group(2))
            ncol = sum(1 for c in m.group(2) if c in "lcrpX") or len(spec.replace("|", ""))
            body = m.group(3)
            for row in body.split("\\\\"):
                row = re.sub(r"\\hline|\\toprule|\\midrule|\\bottomrule|\\cmidrule\S*", "", row)
                if "&" in row:
                    ncell = row.count("&") + 1
                    if ncell > ncol:
                        add("tabular_columns", "warning",
                            "row has %d cells but tabular declares %d columns" % (ncell, ncol),
                            rel, lineno(text, m.start()))
                        break
        # label before caption inside floats
        for m in FLOAT_RE.finditer(text):
            body = m.group(2)
            lp = body.find("\\label")
            cp = CAPTION_RE.search(body)
            if lp >= 0 and (cp is None or lp < cp.start()):
                add("label_before_caption", "warning",
                    "\\label appears before \\caption in float", rel, lineno(text, m.start()))

    # global: undefined references
    for rel, text in files:
        if not rel.endswith((".tex", ".sty")):
            continue
        for m in REF_RE.finditer(text):
            for key in m.group(1).split(","):
                key = key.strip()
                if key and key not in labels:
                    add("undefined_reference", "warning", "\\ref{%s} has no \\label" % key,
                        rel, lineno(text, m.start()))
    # global: citations
    unresolved = sorted(all_cite_keys - bib_keys)
    if unresolved:
        sev = "warning" if have_bibfile else "warning"
        kind = "unresolved_citation" if have_bibfile else "no_bibliography_database"
        add(kind, sev, "citation key(s) without a bibliography entry: %s" % ", ".join(unresolved[:8]),
            files[0][0] if files else "main.tex", 1)
    # packages order
    if hyperref_line and cleveref_line and hyperref_line < cleveref_line:
        add("package_order", "warning", "hyperref loaded before cleveref; load cleveref last",
            files[0][0] if files else "main.tex", hyperref_line)
    # duplicates
    seen = {}
    for pkg, rel, ln in packages:
        if pkg in seen:
            add("duplicate_package", "warning", "\\usepackage{%s} repeated (first at %s:%d)"
                % (pkg, seen[pkg][0], seen[pkg][1]), rel, ln)
        else:
            seen[pkg] = (rel, ln)
    # font / CJK
    if main_text_used and CJK_RE.search(main_text_used) and engine not in CJK_ENGINES:
        add("font_missing", "error",
            "CJK text with non-OpenType engine %s: switch to xelatex or add ctex" % engine,
            files[0][0] if files else "main.tex", 1)
    return findings


# --------------------------------------------------------------------------- #
def apply_fixes(text, findings, keep_out_end=True):
    """Apply only the provable fixes; return (fixes, new_text)."""
    fixes = []
    new = text

    # 1) duplicate \usepackage lines (keep first occurrence)
    lines = new.split("\n")
    seen = {}
    out_lines = []
    for i, ln in enumerate(lines, 1):
        m = PACKAGE_RE.search(ln)
        if m:
            pkgs = [p.strip() for p in m.group(2).split(",")]
            first = pkgs[0]
            if first in seen:
                fixes.append({"id": "fix:duppkg:%d" % i, "kind": "duplicate_package",
                              "file": "", "line": i, "before": ln.strip(), "after": "(removed)",
                              "applied": True, "locator": "L%d" % i,
                              "reason": "duplicate \\usepackage{%s} (first at L%d)" % (first, seen[first])})
                continue
            seen[first] = i
        out_lines.append(ln)
    new = "\n".join(out_lines)

    # 2) duplicate \label -> rename later occurrences to <name>:dup
    seen_lbl = {}
    def _relbl(m):
        key = m.group(1)
        if key in seen_lbl:
            seen_lbl[key] += 1
            newk = "%s:dup%d" % (key, seen_lbl[key])
            return "\\label{%s}" % newk
        seen_lbl[key] = 0
        return m.group(0)
    before_lbl = new
    for m in LABEL_RE.finditer(before_lbl):
        pass
    new2 = LABEL_RE.sub(_relbl, new)
    if new2 != new:
        # record the renames with their lines
        for m in LABEL_RE.finditer(new):
            key = m.group(1)
            pass
        dups = re.findall(r"\\label\{([^}]*):dup\d+\}", new2)
        for key in dups:
            fixes.append({"id": "fix:duplabel:%s" % key, "kind": "duplicate_label",
                          "file": "", "line": lineno(new, new.find("\\label{%s}" % key)),
                          "before": "\\label{%s}" % key, "after": "\\label{%s:dup1}" % key,
                          "applied": True, "locator": "L%d" % lineno(new, new.find("\\label{%s}" % key)),
                          "reason": "duplicate label renamed to keep labels unique"})
        new = new2

    # 3) unclosed environments -> close them (before \end{document} if present)
    unclosed, _ = collect_env_stack(new)
    closers = [name for name, _ in reversed(unclosed) if name != "document"]
    if closers:
        block = "\n".join("\\end{%s}" % n for n in closers)
        if "\\end{document}" in new:
            idx = new.rfind("\\end{document}")
            new = new[:idx] + block + "\n" + new[idx:]
            loc = "L%d" % lineno(new, idx)
        else:
            new = new.rstrip() + "\n" + block + "\n"
            loc = "EOF"
        fixes.append({"id": "fix:env", "kind": "environment_mismatch", "file": "",
                      "line": len(new.split("\n")), "before": "(unclosed environment)",
                      "after": block.replace("\n", " "), "applied": True,
                      "locator": loc, "reason": "%d unclosed environment(s) closed" % len(closers)})

    # 4) missing \end{document}
    if "\\begin{document}" in new and "\\end{document}" not in new and keep_out_end:
        fixes.append({"id": "fix:enddoc", "kind": "missing_end_document", "file": "",
                      "line": len(new.split("\n")), "before": "(EOF)", "after": "\\end{document}",
                      "applied": True, "locator": "EOF", "reason": "\\begin{document} without \\end{document}"})
        new = new.rstrip() + "\n\\end{document}\n"

    # reported-only fixes (located, not applied)
    for f in findings:
        if f["kind"] in ("undefined_reference", "unresolved_citation", "no_bibliography_database",
                         "missing_input", "unit_spacing", "tabular_columns", "label_before_caption",
                         "package_order", "font_missing", "unbalanced_braces"):
            fixes.append({"id": "rep:%s:%d" % (f["kind"], f["line"]), "kind": f["kind"],
                          "file": f["file"], "line": f["line"], "before": f["message"], "after": "",
                          "applied": False, "locator": "L%d" % f["line"],
                          "reason": "located but not auto-changed to avoid altering scientific meaning"})
    return fixes, new
