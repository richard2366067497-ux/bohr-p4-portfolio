#!/usr/bin/env python3
"""readkit -- reading, anchoring, validation and rendering for multi-doc-comparison v3.

Discovery and paragraph anchoring: kind sniffing, stdlib-only PDF/DOCX text,
paragraph splitting into stable ``p<page>#para<n>`` locators, workorder parsing,
and the deterministic best-effort cell heuristics. Then validation, comparability,
agreement adjudication, output_contract backfill and the three rendered artifacts.
Standard library only.
"""
import csv
import hashlib
import json
import re
import time
import unicodedata
import zipfile
import zlib
from pathlib import Path

VERSION = "3.0.0"
GEN = "multi-doc-comparison v3"
DIMS = ["task", "dataset", "sample", "material", "method", "metric", "unit", "budget"]
DEFAULT_CONTRACT = ["case_id", "status", "result", "claims", "uncertainties"]
TEXT_EXT = (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".html", ".htm", ".tex")
TR = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-",
      "−": "-", " ": " ", "​": "", "­": "", "ﬁ": "fi", "ﬂ": "fl"}
WS = re.compile(r"\s+")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def norm(s, squeeze=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if squeeze else " ", s).strip()


def find_quote(text, quote):
    q, t = norm(quote), norm(text)
    if len(q) < 3 or not t:
        return {"found": False, "mode": "short"}
    if q in t:
        return {"found": True, "mode": "exact"}
    if norm(quote, True) and norm(quote, True) in norm(text, True):
        return {"found": True, "mode": "loose"}
    return {"found": False, "mode": "miss"}


def denull(o):
    """Recursively replace empty slots so no literal JSON null reaches disk."""
    if o is None:
        return ""
    if isinstance(o, dict):
        return {k: denull(v) for k, v in o.items()}
    if isinstance(o, list):
        return [denull(v) for v in o]
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return ""
    return o


def jwrite(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(denull(obj), ensure_ascii=False, indent=1), encoding="utf-8")


def jread(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def twrite(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------ extraction
def kind_of(p):
    try:
        head = Path(p).read_bytes()[:8]
    except OSError:
        return "unreadable"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        try:
            names = " ".join(zipfile.ZipFile(p).namelist()[:60])
        except Exception:
            return "zip"
        for key, val in (("word/document", "docx"), ("xl/workbook", "xlsx"), ("ppt/presentation", "pptx")):
            if key in names:
                return val
        return "zip"
    return "text"


def _pdf_strings(raw):
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        body = m.group(1)
        try:
            body = zlib.decompress(body)
        except Exception:
            pass
        for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", body):
            piece = re.sub(rb"\\([()\\])", rb"\1", t.group(0)[1:-1])
            out.append(piece.decode("latin-1", "replace"))
    return re.sub(r"\s+", " ", " ".join(out))


def pages_of(p, kind):
    if kind == "pdf":
        try:
            return [("p1", _pdf_strings(Path(p).read_bytes()))], "stdlib-pdf-strings"
        except Exception:
            return [], "pdf-failed"
    if kind == "docx":
        try:
            from xml.etree import ElementTree as ET
            with zipfile.ZipFile(p) as z:
                root = ET.fromstring(z.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            lines = ["".join(t.text or "" for t in para.iter(ns + "t")) for para in root.iter(ns + "p")]
            return [("p1", "\n\n".join(x for x in lines if x.strip()))], "docx-xml"
        except Exception:
            return [], "docx-failed"
    b = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return [("p1", b.decode(enc))], enc
        except Exception:
            pass
    return [("p1", b.decode("utf-8", "replace"))], "replace"


def paragraphize(pages):
    paras = []
    for label, text in pages:
        t = re.sub(r"[ \t]+", " ", text or "")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
        if len(blocks) <= 1 and len(t) > 1200:
            blocks, cur = [], []
            for line in [x.strip() for x in t.splitlines() if x.strip()]:
                cur.append(line)
                if len(" ".join(cur)) > 600:
                    blocks.append(" ".join(cur))
                    cur = []
            if cur:
                blocks.append(" ".join(cur))
        k = 0
        for b in blocks:
            b = re.sub(r"-\n(?=[a-z])", "", b)
            b = re.sub(r"\s+", " ", b).strip()
            if len(b) < 3:
                continue
            if len(b) < 40 and paras and paras[-1]["page"] == label:
                paras[-1]["text"] += " " + b
                continue
            k += 1
            paras.append({"pid": "p%d" % (len(paras) + 1), "page": label,
                          "locator": "%s#para%d" % (label, k), "text": b})
    return paras or [{"pid": "p1", "page": "p1", "locator": "p1#para1", "text": ""}]


def extract_doc(p):
    kind = kind_of(p)
    pages, eng = pages_of(p, kind)
    notes = []
    if kind == "pdf":
        notes.append("page numbers not authoritative; locators use %s block" % eng)
    if kind not in ("pdf", "docx", "text"):
        notes.append("%s container kept as opaque material" % kind)
    if eng in ("pdf-failed", "docx-failed"):
        notes.append("%s text extraction failed; no body text guessed" % kind)
    paras = paragraphize(pages)
    text = " ".join(x["text"] for x in paras)
    alnum = sum(ch.isalnum() for ch in text) / max(len(text), 1)
    if text and alnum < 0.5:
        notes.append("low text quality (alnum %.2f); CID font or scan likely" % alnum)
    return {"kind": kind, "engine": eng, "paras": paras, "text": text,
            "quality": round(alnum, 3), "notes": notes}


# ------------------------------------------------------------------ workorder
def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj[:40]:
            yield from walk(v)


def find_case(inp, errors):
    if not inp.exists():
        errors.append({"code": "input_missing", "detail": "input directory not found"})
        return {}, None
    candidates = sorted(inp.rglob("case.json")) or sorted(inp.rglob("*.json"))
    for p in candidates:
        try:
            return jread(p), p
        except Exception as e:
            errors.append({"code": "case_unreadable", "detail": "%s: %r" % (p.name, e)})
    return {}, None


def find_workorder(case, files):
    for f in files:
        if "workorder" in f.name.lower() and f.suffix.lower() == ".json":
            try:
                return jread(f), f.name
            except Exception:
                pass
    for k, v in walk(case):
        if "workorder" in k.lower() and isinstance(v, dict):
            return v, "case:" + k
    return {}, ""


def wo_fields(wo):
    raw = None
    for k, v in walk(wo):
        if k.lower() in ("fields", "field_definitions", "common_fields", "comparison_fields", "columns", "schema") \
                and isinstance(v, list) and (raw is None or len(v) > len(raw)):
            raw = v
    out = []
    for i, f in enumerate(raw or []):
        if isinstance(f, str):
            out.append({"field_id": slug(f, "f%d" % (i + 1)), "name": f, "definition": "", "unit": "", "value_rule": ""})
        elif isinstance(f, dict):
            nm = f.get("name") or f.get("label") or f.get("field") or "?"
            out.append({"field_id": str(f.get("field_id") or f.get("id") or f.get("key") or slug(nm, "f%d" % (i + 1))),
                        "name": nm, "definition": f.get("definition") or f.get("desc") or "",
                        "unit": f.get("unit") or "", "value_rule": f.get("value_rule") or f.get("rule") or ""})
    if not out:
        out = [{"field_id": d, "name": d, "definition": "", "unit": "", "value_rule": ""} for d in DIMS]
    return out


def wo_papers(wo):
    raw = next((v for k, v in walk(wo)
                if k.lower() in ("documents", "papers", "corpus", "source_documents", "paper_list")
                and isinstance(v, list) and v), [])
    got = lambda it, *ks: next((str(it[k]) for k in ks if isinstance(it, dict) and it.get(k)), "")
    return [{"doc_id": got(it, "document_id", "doc_id", "id", "source_document_id") or "D%d" % (i + 1),
             "title": it if isinstance(it, str) else got(it, "title", "name"),
             "file": got(it, "file", "filename", "path")}
            for i, it in enumerate(raw)]


def wo_list(wo, keys):
    raw = next((v for k, v in walk(wo) if k.lower() in keys and isinstance(v, list)), [])
    return [str(x) for x in raw]


def wo_dims(wo):
    return wo_list(wo, ("comparison_dimensions", "dimensions", "axes")) or DIMS


def wo_forbidden(wo):
    return wo_list(wo, ("forbidden_pooling", "forbidden_merges", "no_pool"))


def slug(s, fallback="f"):
    return re.sub(r"[^0-9a-z一-鿿]+", "_", norm(s).lower()).strip("_") or fallback


# ------------------------------------------------------------------ heuristics
def value_for(text, field):
    """Deterministic best-effort cell: (value, quote) or (None, None)."""
    fid = (field.get("field_id") or "").lower()
    unit = (field.get("unit") or "").strip()
    if unit and unit.lower() != "ph":
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*" + re.escape(unit) + r"\b", text, re.I)
        if m:
            return m.group(1), sentence_with(text, m.start())
    if unit == "pH" or "ph" in fid:
        m = re.search(r"\bpH\s*([-+]?\d+(?:\.\d+)?)", text, re.I)
        if m:
            return m.group(1), sentence_with(text, m.start())
    if "removal" in fid or "yield" in fid or "efficiency" in fid or "%" in unit:
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*%", text)
        if m:
            return m.group(1), sentence_with(text, m.start())
    if "concentration" in fid or "mg/l" in unit.lower():
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*mg/L", text)
        if m:
            return m.group(1), sentence_with(text, m.start())
    if any(k in fid for k in ("material", "catalyst", "substrate", "adsorbent")):
        m = re.search(r"\b([A-Z][a-z]?\d?(?:[A-Z][a-z]?\d?)+)\b", text)
        if m:
            return m.group(1), sentence_with(text, m.start())
    abbr = r"(?<![A-Za-z])([A-Za-z][A-Za-z0-9]*(?:[ -][A-Za-z0-9]+){0,3})\s*\(([A-Za-z]{2,8})\)"

    def _abbr():
        m = re.search(abbr, text)
        if not m:
            return None
        toks = m.group(1).split()
        name = " ".join(toks[-2:]) if len(toks) > 2 else m.group(1).strip()
        return name + " " + m.group(2), sentence_with(text, m.start())

    if any(k in fid for k in ("pollutant", "dye", "analyte", "contaminant")) and _abbr():
        return _abbr()
    if _abbr():
        return _abbr()
    m = re.search(r"\b([A-Z][a-z]?\d?(?:[A-Z][a-z]?\d?)+)\b", text)
    if m:
        return m.group(1), sentence_with(text, m.start())
    return None, None


def sentence_with(text, idx):
    left = max(text.rfind(".", 0, idx), text.rfind("\n", 0, idx))
    right = text.find(".", idx)
    return norm(text[left + 1: right + 1 if right >= 0 else len(text)]) or norm(text[:200])


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return str(p)


# ============================================================== cells & draft
CSV_COLS = ["source_document_id", "field_id", "field_name", "value", "unit", "dataset",
            "metric_scope", "status", "confidence", "quote", "locator", "note"]


def cell(doc_id, f, value="", status="unreported", conf="auto", quote="", locator="", note=""):
    return {"doc_id": doc_id, "field_id": f["field_id"], "field_name": f["name"], "value": value,
            "unit": f.get("unit") or "", "dataset": "", "metric_scope": "", "status": status,
            "confidence": conf, "quote": quote, "locator": locator, "note": note}


def normalize_draft(draft, docs, fields):
    fids = [f["field_id"] for f in fields]
    out = []
    for c in (draft.get("matrix") or draft.get("cells") or draft.get("rows")
              or draft.get("records") or draft.get("items") or draft.get("entries") or []):
        if not isinstance(c, dict):
            continue
        fid = str(c.get("field_id") or c.get("field") or "")
        did = str(c.get("doc_id") or c.get("source_document_id") or "")
        if did not in docs or fid not in fids:
            continue
        f = next(x for x in fields if x["field_id"] == fid)
        out.append(cell(did, f, value=c.get("value") if c.get("value") is not None else "",
                        status=c.get("status") or ("reported" if c.get("value") not in (None, "") else "unreported"),
                        conf="agent", quote=c.get("quote") or "", locator=c.get("locator") or "",
                        note=c.get("note") or ""))
    return out


def fill_cells(docs, fields, cells):
    seen = {(c["doc_id"], c["field_id"]) for c in cells}
    for d, doc in docs.items():
        for f in fields:
            if (d, f["field_id"]) in seen:
                continue
            val, quote = value_for(doc["text"], f)
            loc = next((p["locator"] for p in doc["paras"] if quote and norm(quote) in norm(p["text"])), None)
            if val is not None and quote:
                cells.append(cell(d, f, value=val, status="reported", quote=quote,
                                  locator=loc or (doc["paras"][0]["locator"] if doc["paras"] else "p1#para1"),
                                  note="auto-extracted outside the agent draft; verify against the paragraph"))
            else:
                cells.append(cell(d, f, note="no value found and no agent draft row for this cell"))
    return cells


# ============================================================== validation
def validate(cells, docs, fields, comparability, agreement):
    errors, warnings = [], []
    fids = [f["field_id"] for f in fields]
    seen, counted = set(), {"reported": 0, "unreported": 0, "quote_miss": 0, "quote_bad": 0, "locator_miss": 0}
    for c in cells:
        w = "%s/%s" % (c["doc_id"], c["field_id"])
        key = (c["doc_id"], c["field_id"])
        if key in seen:
            errors.append({"code": "duplicate_cell", "where": w, "detail": "doc x field appears twice"})
        seen.add(key)
        if c["doc_id"] not in docs:
            errors.append({"code": "cell_unknown_doc", "where": w, "detail": "unknown document"})
            continue
        if c["field_id"] not in fids:
            errors.append({"code": "cell_unknown_field", "where": w, "detail": "undeclared field"})
        if norm(c["status"]).lower() == "reported":
            if c["value"] in (None, ""):
                errors.append({"code": "reported_without_value", "where": w, "detail": "reported but empty"})
                continue
            counted["reported"] += 1
            if not c["quote"]:
                counted["quote_miss"] += 1
                errors.append({"code": "quote_missing", "where": w, "detail": "reported cell without quote"})
            elif not find_quote(docs[c["doc_id"]]["text"], c["quote"])["found"]:
                counted["quote_bad"] += 1
                errors.append({"code": "quote_not_found", "where": w, "detail": "quote not in source paragraph"})
            if not c["locator"]:
                counted["locator_miss"] += 1
                errors.append({"code": "locator_missing", "where": w, "detail": "reported cell without locator"})
        else:
            counted["unreported"] += 1
            if not c["note"]:
                warnings.append({"code": "unreported_no_reason", "where": w, "detail": "no reason recorded"})
    for i, comp in enumerate(comparability):
        if not comp.get("dimension"):
            errors.append({"code": "comparability_no_dimension", "where": "comparability[%d]" % i,
                           "detail": "missing axis"})
    items = agreement.get("items") if isinstance(agreement, dict) else agreement
    for i, it in enumerate(items or []):
        if norm(it.get("verdict")).lower() == "conflicting" and norm(it.get("attribution")).lower() in ("", "unresolved"):
            errors.append({"code": "conflict_without_attribution", "where": "agreement[%d]" % i,
                           "detail": "conflicting verdict needs a cause"})
    total = max(len(fields) * max(len(docs), 1), 1)
    counts = {"documents": len(docs), "fields": len(fields), "cells": len(cells),
              "reported": counted["reported"], "unreported": counted["unreported"],
              "coverage": round(counted["reported"] / total, 3),
              "quote_pass_rate": round((counted["reported"] - counted["quote_miss"] - counted["quote_bad"])
                                       / max(counted["reported"], 1), 3)}
    return {"errors": errors, "warnings": warnings, "counts": counts}


def build_comparability(docs, fields, cells, dims, forbidden):
    comp = []
    by = {(c["doc_id"], c["field_id"]): c for c in cells}
    for dim in dims:
        ids = [f["field_id"] for f in fields if dim in (f["field_id"] + " " + str(f["name"])).lower()]
        vals, shown = {}, {}
        for d in docs:
            picks = [(fid, by[(d, fid)]) for fid in ids
                     if (d, fid) in by and by[(d, fid)]["status"] == "reported"]
            if picks:
                vals[d] = norm(picks[0][1]["value"], True)
                shown[d] = picks[0][1]["value"]
        if not vals:
            continue
        comparable = len(set(vals.values())) == 1
        basis = "%d document(s) report this axis; %s" % (
            len(vals), "identical so a pooled value is admissible" if comparable
            else "values differ between documents, so keep them stratified")
        if forbidden and not comparable:
            basis += "; forbidden pooling enforced"
        comp.append({"dimension": dim, "doc_ids": sorted(vals), "comparable": comparable,
                     "basis": basis, "values": shown})
    return comp


def build_claims(docs, fields, cells, comparability):
    by = {(c["doc_id"], c["field_id"]): c for c in cells}
    claims, cid = [], 0
    for f in fields:
        rep = [(d, by[(d, f["field_id"])]) for d in docs
               if (d, f["field_id"]) in by and by[(d, f["field_id"])]["status"] == "reported"]
        if not rep:
            continue
        cid += 1
        vals = ", ".join("%s=%s%s" % (d, c["value"], (" " + c["unit"]) if c["unit"] else "") for d, c in rep)
        comp = next((x for x in comparability if x["dimension"] in (f["field_id"] + " " + str(f["name"])).lower()), None)
        verdict = "consistent" if (comp and comp["comparable"]) else \
            ("partially_consistent" if len(rep) > 1 else "insufficient")
        claims.append({"claim_id": "c%02d" % cid, "kind": "comparison", "field_id": f["field_id"],
                       "text": "%s across %d document(s): %s" % (f["name"], len(rep), vals), "verdict": verdict,
                       "evidence": [{"source_document_id": d, "quote": c["quote"], "locator": c["locator"]}
                                    for d, c in rep]})
    return claims


def build_agreement(docs, fields, cells, claims):
    items = [{"topic": c["field_id"], "verdict": c["verdict"],
              "attribution": "condition" if c["verdict"] != "insufficient" else "unresolved",
              "explanation": c["text"],
              "evidence": [{"source_document_id": e["source_document_id"], "locator": e["locator"]}
                           for e in c["evidence"]]} for c in claims]
    overall = "insufficient" if not claims else \
        ("consistent" if all(i["verdict"] == "consistent" for i in items) else "partially_consistent")
    n_conf = len([c for c in claims if c["verdict"] == "partially_consistent" and len(c["evidence"]) > 1])
    return {"overall": overall, "items": items, "n_conflicting": n_conf}


# ============================================================== contract
def contract_keys(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict) and oc:
        return list(oc.keys())
    if isinstance(oc, list) and oc:
        return [f if isinstance(f, str)
                else str((f or {}).get("name") or (f or {}).get("key") or "field_%d" % (i + 1))
                for i, f in enumerate(oc)]
    return list(DEFAULT_CONTRACT)


def contract_value(key, ctx):
    k = key.lower()
    if k == "case_id":
        return ctx["case_id"]
    if k == "status":
        return ctx["status"]
    if k in ("result", "comparison", "matrix", "payload", "answer"):
        return ctx["result"]
    if "claim" in k or "finding" in k:
        return ctx["claims"]
    if "uncertain" in k or "gap" in k or "limit" in k:
        return ctx["uncertainties"]
    if "source" in k or "provenance" in k:
        return ctx["sources"]
    if "artifact" in k or "deliver" in k or "output" in k:
        return ctx["artifacts"]
    if "field" in k or "schema" in k:
        return ctx["fields"]
    if "paper" in k or "document" in k or "corpus" in k:
        return ctx["papers"]
    if "tabl" in k or "csv" in k:
        return ctx["cells"]
    if "comparab" in k:
        return ctx["comparability"]
    if "agree" in k or "consisten" in k or "conclusion" in k:
        return ctx["agreement"]
    if "coverage" in k or "count" in k or "stat" in k:
        return ctx["counts"]
    if "method" in k or "repro" in k:
        return {"pipeline": "discover -> anchor -> per-cell extract -> comparability -> agreement",
                "deterministic": True, "entry": "scripts/main.py build"}
    if "pending" in k or "human" in k:
        return ctx["pending_human"] or [{"item": "confirm auto-extracted cells", "action": "panel-check paragraphs"}]
    return {"kind": "unrecognised contract key", "key": key,
            "resolved": "echoed verbatim; no dedicated producer, see result for the full payload"}


def finalize(case, ctx):
    keys = contract_keys(case)
    echo = {}
    for k in keys:
        v = contract_value(k, ctx)
        if v in (None, "", [], {}) and k != "case_id":
            v = contract_value("result", ctx)
        echo[k] = v
    res = {"case_id": ctx["case_id"], "status": ctx["status"], "summary": ctx["summary"], "output_contract": echo}
    for k, v in echo.items():
        res.setdefault(k, v)
    res.update({"sources": ctx["sources"], "uncertainties": ctx["uncertainties"], "uncertainty": ctx["uncertainties"],
                "claims": ctx["claims"], "errors": ctx["errors"], "degradations": ctx["degradations"],
                "changes": ctx["changes"], "change_records": ctx["changes"], "pending_human": ctx["pending_human"],
                "limits": ctx["limits"], "counts": ctx["counts"], "runtime": ctx["runtime"]})
    return res


# ============================================================== rendering
def cell_md(s):
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def table_md(ctx):
    by = {(c["doc_id"], c["field_id"]): c for c in ctx["cells"]}
    docs = [p["doc_id"] for p in ctx["papers"]] or sorted({c["doc_id"] for c in ctx["cells"]})
    lines = ["# Comparison matrix -- common-field view", "",
             "> case `%s` | status **%s** | %s" % (ctx["case_id"], ctx["status"], GEN), ""]
    if ctx["result"]["question"]:
        lines += ["## 0. Comparison question", "", ctx["result"]["question"], ""]
    lines += ["## 1. Per-cell matrix (every reported cell carries a locator)", "",
              "| field (name) | " + " | ".join(docs) + " |", "|" + "---|" * (len(docs) + 1)]
    for f in ctx["fields"]:
        row = ["%s (%s)" % (f["field_id"], f["name"])]
        for d in docs:
            c = by.get((d, f["field_id"]))
            row.append("- unreported" if not c or c["status"] != "reported"
                       else "%s%s  \n*(%s)*" % (c["value"], (" " + c["unit"]) if c["unit"] else "", c["locator"]))
        lines.append("| " + " | ".join(cell_md(x) for x in row) + " |")
    lines += ["", "## 2. Comparability test", ""]
    lines += ["- **%s** | %s -> %s: %s" % (x["dimension"], ", ".join(x["doc_ids"]),
                                           "comparable" if x["comparable"] else "not comparable", x["basis"])
              for x in ctx["comparability"]] or ["- no axis had two reported values; nothing was pooled."]
    lines += ["", "## 3. Agreement and conflict attribution", ""]
    lines += ["- **%s** | %s | cause: %s | %s" % (i["topic"] or "overall", i["verdict"], i["attribution"],
                                                  i["explanation"])
              for i in ctx["agreement"]["items"]] or ["- insufficient evidence for an agreement call."]
    lines += ["", "## 4. Coverage and rerun", "",
              "- cells %s; reported %s; unreported %s; coverage %s; quote pass %s" % (
                  ctx["counts"]["cells"], ctx["counts"]["reported"], ctx["counts"]["unreported"],
                  ctx["counts"]["coverage"], ctx["counts"]["quote_pass_rate"]),
              "- rerun: `main.py build` -> `main.py show --doc D1` -> agent writes work/draft.json"
              " -> `main.py check` -> `main.py selfcheck`.", ""]
    return "\n".join(lines)


def write_artifacts(out, ctx):
    with (out / "comparison_matrix.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for c in ctx["cells"]:
            w.writerow([c["doc_id"] if k == "source_document_id" else c.get(k, "") for k in CSV_COLS])
    twrite(out / "comparison_table.md", table_md(ctx))
    with (out / "evidence_cards.jsonl").open("w", encoding="utf-8") as fh:
        cards = [{"card_id": "C%03d" % (i + 1), "source_document_id": c["doc_id"], "field_id": c["field_id"],
                  "value": c["value"], "unit": c["unit"], "quote": c["quote"], "locator": c["locator"]}
                 for i, c in enumerate(c for c in ctx["cells"] if c["status"] == "reported")]
        fh.write("\n".join(json.dumps(denull(c), ensure_ascii=False) for c in cards) + "\n")
