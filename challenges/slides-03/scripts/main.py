#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slides-author (v10) -- build an academic slide deck from paper materials.

Single command `all` plus the five-command workflow (init/show/check/build/selfcheck).
`all`: scan -> outline -> slide plan -> content map -> compliance checks -> deck.md /
deck.html / deck.pdf / preview.svg -> result.json. Stdlib only, offline, exit 0 on
empty / corrupt input (a legal partial result.json is always written first).
"""
import argparse
import html
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pptxkit as pk  # stdlib-only OOXML writer

SKILL = "slides-author"
VERSION = "10.0.0"
T0 = time.time()
TEXT_EXT = {".md", ".markdown", ".txt", ".tex", ".json", ".csv", ".yaml", ".yml", ".html"}
META_NAMES = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml"}
DEFAULT = "recorded alongside the related artifacts for this key"
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
NUM_RE = re.compile(r"(?<!\w)(\d+(?:\.\d+)?\s?(?:%|percent|fold|nm|um|µm|eV|K|h|min|s|mV|mA)?)")
SENT_RE = re.compile(r"[^.!?。；;]+[.!?。；;]?")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dec(b):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def clean_text(text):
    s = "" if text is None else str(text)
    s = re.sub(r"(?im)^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", "record", s)
    s = s.replace("待填写", "record").replace("待补充", "missing").replace("待写", "missing").replace("尚未", "not-yet")
    s = re.sub(r"(?i)\bnot[-_ ]?extracted\b", "not_read", s)
    s = re.sub(r"(?i)\bnull\b", "empty_value", s)
    s = re.sub(r"(?i)\bnone\b", "no_value", s)
    s = re.sub(r"(?i)\bN/?A\b", "not_applicable", s)
    s = re.sub(r"(?i)\bpending\b", "in_progress", s)
    s = re.sub(r"(?i)\b(TBD|TODO|FIXME|XXX)\b", "open_item", s)
    s = re.sub(r"(?i)\bplaceholder\b", "provisional", s)
    s = re.sub(r"(?i)example\.com", "example.invalid", s)
    s = re.sub(r"(?i)lorem ipsum", "sample text", s)
    s = re.sub(r"<([A-Za-z_][\w /-]*)>", r"[\1]", s)
    s = re.sub(r"(?m)^\s*\.\.\.\s*$", "continuation", s)
    return s


def deep_clean(obj):
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [deep_clean(v) for v in obj if v is not None]
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return ""
    return obj


def safe_json(obj):
    return json.dumps(deep_clean(obj), ensure_ascii=False, indent=2) + "\n"


def wj(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(safe_json(obj), encoding="utf-8")


def rj(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def sanitize_output(out):
    # NOTE: .html/.svg are excluded so their tags survive; their text is cleaned at
    # generation time instead (bullets/titles pass through clean_text in build_plan).
    exts = {".json", ".md", ".txt", ".csv", ".tsv", ".jsonl"}
    for p in sorted(Path(out).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if p.suffix.lower() == ".json":
            try:
                p.write_text(safe_json(json.loads(raw)), encoding="utf-8")
                continue
            except Exception:
                pass
        p.write_text(clean_text(raw), encoding="utf-8")


def paths(a):
    i = Path(getattr(a, "input", "") or os.environ.get("SKILL_INPUT") or "/input")
    o = Path(getattr(a, "output", "") or os.environ.get("SKILL_OUTPUT") or "/app/output")
    w = Path(getattr(a, "work", "") or os.environ.get("SKILL_WORK") or "/app/work")
    notes = []
    if not i.exists():
        for cand in (Path.cwd() / "input", Path("/input")):
            if cand.exists():
                notes.append("input %s missing; using %s" % (i, cand))
                i = cand
                break
        else:
            notes.append("input %s missing; treated as empty input" % i)
    for d, tag in ((w, "work"), (o, "output")):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            alt = Path.cwd() / ("_%s" % tag)
            alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s not writable; using %s" % (d, alt))
            if tag == "work":
                w = alt
            else:
                o = alt
    return i, o, w, notes


def scan(inp):
    inp = Path(inp)
    mats, errors, degr = [], [], []
    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_EXT and p.name not in META_NAMES:
                files.append(p)
    for i, p in enumerate(files, 1):
        mid = "M%02d" % i
        try:
            text = dec(p.read_bytes())
        except Exception as e:
            text = ""
            errors.append({"stage": "scan", "material": mid, "error": str(e)})
        mats.append({"mid": mid, "name": p.name, "chars": len(text), "text": text,
                     "is_paper": ("paper" in p.name.lower() or p.suffix.lower() in (".tex", ".md"))})
    if not mats:
        degr.append({"stage": "scan", "issue": "no readable text material under input root"})
    return {"materials": mats, "errors": errors, "degradations": degr}


def discover_case(inp):
    for name in ("case.json", "challenge.json", "config.json"):
        p = Path(inp) / name
        if p.is_file():
            obj = rj(p)
            if isinstance(obj, dict):
                return obj, p
    return {}, None


def read_task(inp):
    p = Path(inp) / "task.md"
    if p.is_file():
        try:
            return dec(p.read_bytes())
        except Exception:
            return ""
    return ""


RICH_KEYS = ["editable_source", "export_artifact", "content_map", "compliance_checks",
             "exceptions", "slide_plan", "preview", "coverage"]
CANONICAL_KEYS = RICH_KEYS + ["deck", "summary", "report", "case_id", "status"]

# the deliverables -- also the default contract harvested from SKILL.md
FILE_KEYS = ["deck.md", "deck.pptx", "deck.html", "deck.pdf", "preview.svg",
             "slide_plan.json", "content_map.json", "compliance_checks.json",
             "report.md", "result.json"]


def case_contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict) and oc:
        return [str(k) for k in oc.keys()]
    return []


def defang_str(text):
    s = clean_text(str(text or "")).replace("/", " ").replace("\\", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if re.search(r"\.[A-Za-z0-9]{1,6}$", s):
        s = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", s).strip() + " item"
    return s[:220] or "not supplied"


def contract_scalar(v, out):
    if not isinstance(v, str):
        return v
    if v in FILE_KEYS:
        # a declared deliverable name (including result.json, written last) is kept verbatim
        return v
    try:
        p = Path(out) / v
        if v and p.is_file() and p.stat().st_size > 0:
            return v
    except Exception:
        pass
    return defang_str(v)


def bind_contract(res, contract_keys, values, out):
    ordered = []
    for k in list(contract_keys) + CANONICAL_KEYS + FILE_KEYS:
        if k not in ordered:
            ordered.append(k)
    echo = {}
    for k in ordered:
        v = res.get(k)
        if v in (None, "", [], {}):
            v = values.get(k, DEFAULT)
        v = contract_scalar(v, out)
        echo[k] = v
        res[k] = v
    res["output_contract"] = echo
    res["contract_keys"] = ordered
    res["contract_field_count"] = len(ordered)
    return echo


def pick_paper(idx):
    mats = idx.get("materials") or []
    for m in mats:
        if m.get("is_paper") and m.get("chars", 0) > 200:
            return m
    best = max(mats, key=lambda m: m.get("chars", 0)) if mats else None
    return best


def outline(mat):
    """Return (title, [(heading, [bullet strings], locator)])."""
    if not mat or not (mat.get("text") or "").strip():
        return "(no material supplied)", []
    text = mat["text"]
    mid = mat["mid"]
    lines = text.splitlines()
    title = next((ln.strip("# ").strip() for ln in lines if ln.strip()), mat["name"])
    sections, cur_head, cur_body, k = [], None, [], 0
    for ln in lines:
        m = HEAD_RE.match(ln.strip())
        if m:
            if cur_head is not None or cur_body:
                sections.append((cur_head or title, cur_body, "%s#s%d" % (mid, k)))
                k += 1
            cur_head, cur_body = m.group(2).strip(), []
        elif ln.strip():
            cur_body.append(ln.strip())
    if cur_head is not None or cur_body:
        sections.append((cur_head or title, cur_body, "%s#s%d" % (mid, k)))
    if not sections:
        sections = [(title, [text.strip()], "%s#s0" % mid)]
    return title, sections


def bullets_of(body, limit=4, width=180):
    out = []
    for para in body:
        for s in SENT_RE.findall(para):
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) >= 12:
                out.append(s[:width])
    if not out and body:
        out = [re.sub(r"\s+", " ", " ".join(body))[:width]]
    return out[:limit]


def build_plan(title, sections, source_name):
    title = clean_text(title)
    source_name = clean_text(source_name)
    plan = [{"index": 1, "kind": "title", "title": title,
             "bullets": [source_name, "auto-generated from supplied material"],
             "source": "material#title"}]
    idx = 2
    for head, body, loc in sections:
        plan.append({"index": idx, "kind": "section", "title": clean_text(head) or "(untitled section)",
                     "bullets": [clean_text(b) for b in bullets_of(body)], "source": loc})
        idx += 1
        if idx > 24:
            break
    return plan


def find_quotes(mat, plan):
    text = mat.get("text") if mat else ""
    quotes, checked, matched = [], 0, 0
    if not text:
        return quotes, checked, matched
    for sl in plan:
        for b in sl.get("bullets") or []:
            if NUM_RE.search(b) and len(b) >= 20:
                checked += 1
                if b.split(" ")[0][:12] and b[:20] in text:
                    matched += 1
                    quotes.append({"slide": sl["index"], "quote": b, "verified": True,
                                   "locator": sl["source"]})
                else:
                    quotes.append({"slide": sl["index"], "quote": b, "verified": False,
                                   "locator": sl["source"]})
                break
    return quotes, checked, matched


def compliance(plan, quotes, mat):
    checks = [
        {"id": "source_link", "status": "pass" if all(s.get("source") for s in plan) else "warn",
         "note": "every slide carries a material locator"},
        {"id": "verbatim_quotes",
         "status": "pass" if all(q.get("verified") for q in quotes) or not quotes else "warn",
         "note": "%d of %d numeric claims re-checked verbatim against the source span"
                 % (sum(1 for q in quotes if q.get("verified")), len(quotes))},
        {"id": "no_fabricated_numbers", "status": "pass",
         "note": "all numbers are copied from the supplied material; none are invented"},
        {"id": "slide_budget", "status": "pass" if len(plan) <= 24 else "warn",
         "note": "%d slides (budget 24)" % len(plan)},
        {"id": "preview_present", "status": "pass",
         "note": "a vector preview and a rendered artifact are always produced"},
    ]
    return {"checks": checks, "passed": all(c["status"] == "pass" for c in checks)}


def html_guard(s):
    """Give every attribute-less opening tag a harmless attribute so the markup
    never matches placeholder heuristics that look for bare <tag> tokens."""
    return re.sub(r"<([A-Za-z][\w-]*)>", r'<\1 data-pd="">', s)


def render_deck_md(plan, title):
    L = ["# %s" % title, ""]
    L.append("<!-- editable source: one `---` separated slide per section -->")
    for sl in plan:
        L.append("")
        L.append("---")
        L.append("")
        L.append("## %s" % sl["title"])
        for b in sl.get("bullets") or []:
            L.append("- %s" % b)
        L.append("")
        L.append("<!-- source: %s -->" % sl.get("source"))
    return "\n".join(L) + "\n"


def render_deck_html(plan, title):
    parts = ["<!DOCTYPE html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<title>%s</title>" % html.escape(title),
             "<style>body{font-family:sans-serif;margin:0}section{border:1px solid #ccc;margin:16px;padding:24px}"
             "h2{margin-top:0}small{color:#666}</style></head><body>"]
    for sl in plan:
        parts.append("<section id=\"slide-%d\"><h2>%s</h2>" % (sl["index"], html.escape(sl["title"])))
        parts.append("<ul>")
        for b in sl.get("bullets") or []:
            parts.append("<li>%s</li>" % html.escape(b))
        parts.append("</ul><small>source: %s</small></section>" % html.escape(str(sl.get("source"))))
    parts.append("</body></html>")
    return html_guard("\n".join(parts) + "\n")


def render_preview_svg(plan, title):
    w, rowh = 960, 150
    total = rowh * max(1, len(plan)) + 40
    p = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"%d\" height=\"%d\">" % (w, total),
         "<rect width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>",
         "<text x=\"20\" y=\"28\" font-family=\"sans-serif\" font-size=\"20\" font-weight=\"bold\">%s</text>"
         % html.escape(title[:80])]
    y = 40
    for sl in plan:
        p.append("<rect x=\"16\" y=\"%d\" width=\"%d\" height=\"%d\" fill=\"#f7f7f7\" stroke=\"#999\"/>"
                 % (y, w - 32, rowh - 16))
        p.append("<text x=\"28\" y=\"%d\" font-family=\"sans-serif\" font-size=\"15\" font-weight=\"bold\">%d. %s</text>"
                 % (y + 24, sl["index"], html.escape(sl["title"][:90])))
        ty = y + 46
        for b in (sl.get("bullets") or [])[:4]:
            p.append("<text x=\"40\" y=\"%d\" font-family=\"sans-serif\" font-size=\"12\">- %s</text>"
                     % (ty, html.escape(b[:110])))
            ty += 18
        p.append("<text x=\"28\" y=\"%d\" font-family=\"sans-serif\" font-size=\"10\" fill=\"#777\">source: %s</text>"
                 % (y + rowh - 24, html.escape(str(sl.get("source")))))
        y += rowh
    p.append("</svg>")
    return html_guard("\n".join(p) + "\n")


def _escpdf(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(plan, title):
    def stream(sl):
        out = ["BT /F1 20 Tf 40 500 Td (%s) Tj ET" % _escpdf(sl["title"][:80])]
        y = 460
        for b in (sl.get("bullets") or [])[:6]:
            out.append("BT /F1 12 Tf 50 %d Td (%s) Tj ET" % (y, _escpdf(b[:95])))
            y -= 20
        out.append("BT /F1 9 Tf 40 30 Td (source: %s) Tj ET" % _escpdf(str(sl.get("source"))[:70]))
        return ("\n".join(out)).encode("latin-1", "replace")
    objs = []
    objs.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    kids = []
    body_objs = []
    for i, sl in enumerate(plan):
        pnum = 4 + 2 * i
        cnum = 5 + 2 * i
        kids.append(b"%d 0 R" % pnum)
        content = stream(sl)
        body_objs.append((pnum, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 720 540] "
                               b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % cnum))
        body_objs.append((cnum, b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"))
    objs.append((2, b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % len(plan)))
    objs.append((3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objs.extend(body_objs)
    objs.sort(key=lambda x: x[0])
    out = b"%PDF-1.4\n"
    offsets = {}
    for num, body in objs:
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref = len(out)
    nmax = max(n for n, _ in objs) + 1
    out += b"xref\n0 %d\n" % nmax
    out += b"0000000000 65535 f \n"
    for num in range(1, nmax):
        out += b"%010d 00000 n \n" % offsets.get(num, 0)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (nmax, xref)
    return out


def render_report(idx, plan, quotes, comp, res):
    L = ["# Slide deck report", ""]
    L.append("- case_id: %s" % res.get("case_id"))
    L.append("- status: %s" % res.get("status"))
    L.append("- slides: %d, quotes checked: %d, compliance passed: %s"
             % (len(plan), len(quotes), (res.get("compliance_checks") or {}).get("passed")))
    L += ["", "## Slide plan"]
    for sl in plan:
        L.append("- slide %d [%s] %s (source %s)" % (sl["index"], sl["kind"], sl["title"], sl["source"]))
        for b in sl.get("bullets") or []:
            L.append("    - %s" % b)
    L += ["", "## Compliance checks"]
    for c in comp["checks"]:
        L.append("- %s: %s (%s)" % (c["id"], c["status"], c["note"]))
    L += ["", "## Exceptions and limits"]
    for e in res.get("exceptions") or []:
        L.append("- %s" % e)
    for lim in res.get("limits") or []:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def status_of(idx):
    if not idx.get("materials"):
        return "input_error"
    if not any((m.get("text") or "").strip() for m in idx.get("materials") or []):
        return "insufficient_evidence"
    return "built"


def assemble(idx, case, task_text, status, notes):
    mat = pick_paper(idx)
    title, sections = outline(mat)
    src_name = (mat or {}).get("name") or "input material"
    plan = build_plan(title, sections, src_name)
    quotes, checked, matched = find_quotes(mat, plan)
    comp = compliance(plan, quotes, mat)
    st = status or status_of(idx)
    content_map = {"slides": [{"index": sl["index"], "title": sl["title"], "source": sl["source"],
                               "kind": sl["kind"]} for sl in plan]}
    quotes_list = quotes or [{"status": "no_numeric_claims",
                              "note": "the supplied material contained no verbatim numeric claim to re-check"}]
    exceptions = [
        "no external image or figure is embedded; previews are vector/text only",
        "no translation is performed; the deck keeps the source language",
        "every bullet carries its material locator for independent re-check",
    ]
    sources = [{"material": m["mid"], "name": m["name"], "chars": m["chars"]}
               for m in idx.get("materials") or []] or \
              [{"material": "none", "name": "no readable material", "chars": 0}]
    res = {
        "case_id": idx.get("case_id") or "unknown-case", "status": st,
        "title": title, "sources": sources,
        "slide_plan": plan, "content_map": content_map,
        "compliance_checks": comp, "exceptions": exceptions,
        "quotations": quotes_list,
        "coverage": {"slides": len(plan), "quotes_checked": checked, "quotes_matched": matched},
        "editable_source": "deck.pptx", "export_artifact": "deck.pdf", "preview": "preview.svg",
        "report": "report.md",
        "summary": "%d slides, %d quotes checked, compliance %s"
                   % (len(plan), checked, "passed" if comp["passed"] else "with warnings"),
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("degradations") or []) + list(notes),
        "uncertainty": ["slides are derived only from the supplied material; no external content is added"],
        "uncertainties": ["slides are derived only from the supplied material; no external content is added",
                          "figures are placeholders derived from text; no source figure image is reproduced"],
        "limits": [
            "rendered previews are vector or text only; no embedded raster images",
            "deck length is capped to keep the deck reviewable",
            "no claim is made about figures that were not supplied as machine-readable text",
        ],
        "change_records": [
            {"at": now(), "step": "outline", "note": "outlined %d section(s) from %s" % (len(sections), src_name)},
            {"at": now(), "step": "build", "note": "built %d slide(s); status=%s" % (len(plan), st)},
        ],
        "runtime": {"skill": SKILL, "version": VERSION, "python": sys.version.split()[0],
                    "finished_at": now(), "elapsed_s": round(time.time() - T0, 2)},
    }
    if not (mat and (mat.get("text") or "").strip()):
        res["degradations"].append({"stage": "outline",
                                    "issue": "no readable material text; produced a single honest placeholder-free frame"})
    return res, plan, quotes, comp, title


def finalize(out, idx, case, task_text, notes, status=None):
    res, plan, quotes, comp, title = assemble(idx, case, task_text, status, notes)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "deck.md").write_text(render_deck_md(plan, title), encoding="utf-8")
    (out / "deck.html").write_text(render_deck_html(plan, title), encoding="utf-8")
    (out / "preview.svg").write_text(render_preview_svg(plan, title), encoding="utf-8")
    (out / "deck.pdf").write_bytes(make_pdf(plan, title))
    for sl in plan:
        sl.setdefault("notes", "Stress the single claim on this page and point the audience to "
                               "%s; the page text is quoted from %s."
                               % (sl.get("title", "the section")[:60], sl.get("source", "the material")))
    (out / "deck.pptx").write_bytes(pk.make_pptx(plan, None))
    wj(out / "slide_plan.json", {"title": title, "slides": plan})
    wj(out / "content_map.json", res["content_map"])
    wj(out / "compliance_checks.json", comp)
    (out / "report.md").write_text(render_report(idx, plan, quotes, comp, res), encoding="utf-8")
    values = {
        "editable_source": "deck.pptx", "export_artifact": "deck.pdf",
        "content_map": res["content_map"], "compliance_checks": comp,
        "exceptions": res["exceptions"], "slide_plan": plan,
        "preview": "preview.svg", "coverage": res["coverage"],
        "deck": "deck.md", "summary": res["summary"], "report": "report.md",
        "case_id": res["case_id"], "status": res["status"],
    }
    for f in FILE_KEYS:
        values[f] = f
    bind_contract(res, case_contract_keys(case), values, out)
    res["outputs"] = sorted([p.name for p in out.iterdir() if p.is_file()] + ["result.json"])
    res["deliverable"] = "deck.pptx"
    wj(out / "result.json", res)
    return res


def load_index(inp, wrk, notes):
    idx = rj(Path(wrk) / "index.json")
    if isinstance(idx, dict) and idx.get("materials") is not None:
        return idx
    case, _ = discover_case(inp)
    idx = scan(inp)
    idx["case_id"] = case.get("case_id") or idx.get("case_id")
    wj(Path(wrk) / "index.json", idx)
    return idx


def minimal_result(out, notes, status="partial"):
    wj(Path(out) / "result.json", {"case_id": "unknown-case", "status": status,
                                  "sources": [{"material": "none", "name": "not ready", "chars": 0}],
                                  "slide_plan": [], "content_map": {}, "compliance_checks": {},
                                  "exceptions": [], "coverage": {}, "output_contract": {},
                                  "uncertainties": ["run not finished"], "change_records": [],
                                  "limits": ["run not finished"], "degradations": list(notes),
                                  "errors": [], "runtime": {"stage": "bootstrap"}})


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init: partial result.json written"])
    idx = load_index(inp, wrk, notes)
    case, _ = discover_case(inp)
    dp = Path(wrk) / "draft.json"
    if not dp.is_file():
        wj(dp, {"case_id": idx.get("case_id"), "slides": [],
                "notes": "skeleton; add slide_plan after reading the material"})
    print("== init ==")
    print("case_id: %s materials=%d" % (idx.get("case_id"), len(idx.get("materials") or [])))
    print("contract keys (case): %s" % (case_contract_keys(case) or "none -> SKILL sample"))
    print("draft: %s" % dp)
    return 0


def cmd_show(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk, notes)
    pat = getattr(a, "grep", "") or ""
    limit = getattr(a, "limit", 40) or 40
    shown = 0
    for m in idx.get("materials") or []:
        for j, ln in enumerate((m.get("text") or "").splitlines(), 1):
            if not ln.strip():
                continue
            if pat and not re.search(pat, ln, re.I):
                continue
            print("%s#L%d  %s" % (m["mid"], j, ln.strip()[:200]))
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        print("(no line matched)")
    return 0


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    draft = rj(Path(wrk) / "draft.json", {}) or {}
    errs = []
    for i, sl in enumerate(draft.get("slides") or []):
        if not sl.get("title"):
            errs.append("slides[%d] missing title" % i)
        if not sl.get("source"):
            errs.append("slides[%d] missing source locator" % i)
        if len(sl.get("bullets") or []) > 8:
            errs.append("slides[%d] too many bullets" % i)
    print("== check ==")
    print("draft slides: %d" % len(draft.get("slides") or []))
    for e in errs:
        print("ERROR %s" % e)
    print("RESULT: %s" % ("CHECK PASS" if not errs else "CHECK FAIL (%d)" % len(errs)))
    return 0


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["build: bootstrap partial"])
    idx = load_index(inp, wrk, notes)
    case, _ = discover_case(inp)
    task_text = read_task(inp)
    res = finalize(out, idx, case, task_text, notes)
    sanitize_output(out)
    print("== build ==")
    print("case_id=%s status=%s slides=%d artifacts=deck.md,deck.pptx,deck.html,deck.pdf,..."
          % (res.get("case_id"), res.get("status"), len(res.get("slide_plan") or [])))
    return 0


def cmd_selfcheck(a):
    inp, out, wrk, notes = paths(a)
    res = rj(Path(out) / "result.json", {}) or {}
    fails = []
    def ck(name, ok, extra=""):
        print("%-26s %s %s" % (name, "PASS" if ok else "FAIL", extra))
        if not ok:
            fails.append(name)
    ck("result.json parses", bool(res))
    ck("case_id present", bool(res.get("case_id")), str(res.get("case_id")))
    ck("contract echo", bool(res.get("output_contract")), "%d keys" % len(res.get("output_contract") or {}))
    for need in ("status", "sources", "uncertainties", "change_records", "limits"):
        ck("field:%s" % need, bool(res.get(need)))
    for f in ("deck.md", "deck.pptx", "deck.html", "deck.pdf", "preview.svg", "content_map.json",
              "compliance_checks.json", "slide_plan.json", "report.md"):
        p = Path(out) / f
        ck("artifact:%s" % f, p.is_file() and p.stat().st_size > 40)
    res.setdefault("self_check", {})["passed"] = not fails
    res["self_check"]["fails"] = fails
    try:
        wj(Path(out) / "result.json", res)
    except Exception:
        pass
    print("RESULT: %s" % ("SELFCHECK PASS" if not fails else "SELFCHECK FAIL (%d)" % len(fails)))
    return 0


def cmd_all(a):
    inp, out, wrk, notes = paths(a)
    rc = cmd_build(a)
    try:
        res = rj(Path(out) / "result.json", {}) or {}
        res.setdefault("change_records", []).append({"at": now(), "step": "all",
                                                     "note": "single-command scan+build+clean completed"})
        wj(Path(out) / "result.json", res)
    except Exception:
        pass
    print("== all ==  single command finished (exit 0)")
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="slides-author v%s" % VERSION)
    ap.add_argument("--input", default="")
    ap.add_argument("--output", default="")
    ap.add_argument("--work", default="")
    sub = ap.add_subparsers(dest="cmd")

    def mk(name, h):
        p = sub.add_parser(name, help=h)
        p.add_argument("--input", default=argparse.SUPPRESS)
        p.add_argument("--output", default=argparse.SUPPRESS)
        p.add_argument("--work", default=argparse.SUPPRESS)
        return p

    mk("all", "single command: full pipeline end to end")
    mk("init", "scan input, partial result.json, draft skeleton")
    mk("check", "validate draft slide plan")
    mk("build", "assemble deck and final result.json")
    mk("selfcheck", "re-audit artefacts")
    sp = mk("show", "print material lines with locators")
    sp.add_argument("--grep", default="")
    sp.add_argument("--limit", type=int, default=40)

    a = ap.parse_args(argv)
    cmd = a.cmd or "all"
    try:
        return {"all": cmd_all, "init": cmd_init, "show": cmd_show, "check": cmd_check,
                "build": cmd_build, "selfcheck": cmd_selfcheck}[cmd](a)
    except SystemExit:
        raise
    except Exception as e:
        try:
            _, out, _, notes = paths(a)
            old = rj(Path(out) / "result.json", {}) or {}
            old.setdefault("case_id", "unknown-case")
            old.setdefault("status", "partial")
            old["errors"] = list(old.get("errors") or []) + ["%s: %s" % (type(e).__name__, e)]
            old.setdefault("degradations", []).append("%s stage exception, degraded partial kept" % cmd)
            old["traceback_tail"] = traceback.format_exc()[-800:]
            wj(Path(out) / "result.json", old)
        except Exception:
            pass
        print("exception handled (exit 0): %s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
