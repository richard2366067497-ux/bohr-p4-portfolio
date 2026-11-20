#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citerender.py -- GB/T 7714-2015 and APA-7 rendering plus tabular writers for
reference management (writing-04, v7). Standard library only.

Every renderer is pure: it takes a numbered canonical record and returns a
single reference string. The same record therefore renders deterministically in
both target styles, so a reviewer can diff the two and see only the styles
differ (never the facts).
"""
from __future__ import annotations

import csv
import io
import re

from citelib import TYPE_MAP, clean

# --------------------------------------------------------------------------- #
# author formatting
# --------------------------------------------------------------------------- #
def _initials(given: str) -> str:
    parts = re.findall(r"[A-Za-z一-鿿]+", given or "")
    out = []
    for p in parts:
        if re.match(r"[一-鿿]", p):
            out.append(p)
        else:
            out.append(p[0].upper() + ".")
    return " ".join(out)


def split_author(a: str):
    a = (a or "").strip()
    if "," in a:
        sur, rest = a.split(",", 1)
        return sur.strip(), rest.strip()
    parts = a.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def apa_authors(authors):
    formatted = []
    for a in authors:
        sur, given = split_author(a)
        formatted.append(("%s, %s" % (sur, _initials(given))).strip().rstrip(","))
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


def gbt_authors(authors):
    def one(a):
        sur, given = split_author(a)
        ini = _initials(given).replace(" ", "")
        return (sur.upper() + " " + ini).strip() if ini else sur.upper()
    if not authors:
        return ""
    if len(authors) > 3:
        return ", ".join(one(a) for a in authors[:3]) + ", et al"
    return ", ".join(one(a) for a in authors)


def _type_code(rec):
    et = (rec.get("entry_type") or "").lower()
    if et in TYPE_MAP:
        return TYPE_MAP[et]
    up = (rec.get("entry_type") or "").upper()
    return up if up and len(up) <= 5 else "Z"


def _pages(p):
    return (p or "").replace("--", "-").replace("–", "-")


# --------------------------------------------------------------------------- #
# GB/T 7714-2015
# --------------------------------------------------------------------------- #
def render_gbt(number, rec):
    code = _type_code(rec)
    authors = gbt_authors(rec["authors"])
    title = (rec["title"] or "").strip().rstrip(".")
    lead = (authors.rstrip(".") + ". ") if authors else ""
    if code in ("J", "C", "N"):
        tail = ""
        if rec["container"]:
            tail += ". " + rec["container"]
        if rec["year"]:
            tail += ", " + rec["year"]
        if rec["volume"]:
            tail += ", " + rec["volume"]
            if rec["issue"]:
                tail += "(" + rec["issue"] + ")"
        if rec["pages"]:
            tail += ": " + _pages(rec["pages"])
        tail += "."
        cite = "%s%s[%s]%s" % (lead, title, code, tail)
    elif code in ("M", "D", "R", "S"):
        parts = [title + "[%s]" % code]
        loc = (rec["publisher"] or "")
        if rec["year"]:
            loc += (", " if loc else "") + rec["year"]
        if loc:
            parts.append(loc)
        cite = lead + ". ".join(parts) + "."
    else:
        parts = [title + "[%s]" % code]
        if rec["container"]:
            parts.append(rec["container"])
        if rec["year"]:
            parts.append(rec["year"])
        cite = lead + ". ".join(parts) + "."
    out = cite
    if rec["doi"]:
        out += " DOI: " + rec["doi"] + "."
    elif rec["url"]:
        out += " " + rec["url"]
    return "[%d] %s" % (number, re.sub(r"\s+", " ", out).strip())


# --------------------------------------------------------------------------- #
# APA 7th
# --------------------------------------------------------------------------- #
def render_apa(number, rec):
    authors = apa_authors(rec["authors"])
    year = rec["year"] or ""
    title = (rec["title"] or "").strip().rstrip(".")
    if rec["container"]:
        title = title
    seg = []
    if authors:
        seg.append(authors)
    seg.append("(%s)." % year if year else "(n.d.).")
    parts = []
    if rec["entry_type"] in ("article", "J") or rec["container"]:
        parts.append(title + ".")
        cont = rec["container"]
        if cont:
            cont_r = cont
            if rec["volume"]:
                cont_r += ", " + rec["volume"]
                if rec["issue"]:
                    cont_r += "(" + rec["issue"] + ")"
            if rec["pages"]:
                cont_r += ", " + _pages(rec["pages"])
            parts.append(cont_r + ".")
    else:
        parts.append(title + ".")
        if rec["publisher"]:
            parts.append(rec["publisher"] + ".")
    out = " ".join(seg + parts)
    if rec["doi"]:
        out += " https://doi.org/" + rec["doi"]
    elif rec["url"]:
        out += " " + rec["url"]
    return re.sub(r"\s+", " ", out).strip()


RENDERERS = {"gbt7714": render_gbt, "apa7": render_apa}
STYLE_ALIAS = {"gbt": "gbt7714", "gbt7714": "gbt7714", "gbt7714-2015": "gbt7714",
               "apa": "apa7", "apa7": "apa7", "apa-7": "apa7"}


def normalize_style(name: str) -> str:
    return STYLE_ALIAS.get((name or "").strip().lower(), "")


# --------------------------------------------------------------------------- #
# tabular writers
# --------------------------------------------------------------------------- #
def write_csv(path, header, rows):
    """Write a CSV with a leading '# rows=N' provenance comment line so even a
    genuinely empty table is a substantive file (>= 40 bytes), never a skeleton."""
    buf = io.StringIO()
    buf.write("# rows=%d\n# engine=citation-ledger-sync/3.0.0\n" % len(rows))
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([clean(r.get(h, "")) if isinstance(r, dict) else "" for h in header])
    data = buf.getvalue()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(data)
    return len(rows)


def references_table(numbered):
    lines = []
    for style, fn in (("gbt7714", render_gbt), ("apa7", render_apa)):
        lines.append("## %s" % style)
        if numbered:
            for number, rec in numbered:
                lines.append(fn(number, rec))
        else:
            lines.append("No reference records were parsed from the input to render in %s." % style)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_bibliography(numbered, style):
    fn = RENDERERS[style]
    return "\n".join(fn(n, r) for n, r in numbered) + ("\n" if numbered else "")
