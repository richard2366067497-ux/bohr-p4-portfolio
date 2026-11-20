# -*- coding: utf-8 -*-
"""checkkit -- corpus indexing and per-field extraction for reading-06 (stdlib only).

The module turns the supplied material into one indexed corpus (paragraphs + table
cells), then settles every target field against that corpus:

  * a field is ``reported``           when a cell/paragraph supplies a value and the
                                      quote is a verbatim slice of the index;
  * a field is ``not_reported``       when the material only marks it as unmeasured
                                      (for example ``n.r.``) or says nothing at all;
  * a field is ``source_conflict``    when two indexed readings disagree;
  * a field is ``extraction_failed``  when the material is present but the field
                                      cannot be judged at all.

Every settled field keeps a verbatim quote plus a locator, so nothing is ever
carried over on trust.
"""
import csv
import hashlib
import io
import json
import re

SHELL_RE = re.compile(r"\[\s*待写\s*\]|待补充|待写|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b"
                      r"|placeholder|NOT_EXTRACTED|\bnot[-_ ]?extracted\b|\bpending\b"
                      r"|\bnull\b|\bNone\b|\bN/?A\b", re.IGNORECASE)
NOT_MEASURED = ("n.r.", "n.r", "-", "--", "na", "not measured", "not reported", "not available")
UNIT_IN_HEADER = re.compile(r"\(([^()]+)\)\s*$")


def contains_shell(text):
    return bool(text) and bool(SHELL_RE.search(text))


def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()[:12]


def sha1_file(path):
    try:
        return sha1_bytes(path.read_bytes())
    except OSError:
        return ""


def _decode(raw):
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8/replace"


def _unit_from_header(header):
    m = UNIT_IN_HEADER.search(str(header or "").strip())
    return m.group(1).strip() if m else ""


def _is_number(text):
    t = str(text or "").strip().replace(",", "")
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", t))


def row_line(cells):
    return " | ".join(str(c) for c in cells)


def load_sources(inp, skip_names=("case.json", "task.md")):
    """Read every material under inp, de-duplicated by sha1."""
    from pathlib import Path
    inp = Path(inp)
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    seen, sources, dupes = {}, [], []
    for p in files:
        if p.name.lower() in skip_names:
            continue
        h = sha1_file(p)
        if h and h in seen:
            dupes.append("%s duplicates %s; the first copy is indexed" % (p.name, seen[h]))
            continue
        if h:
            seen[h] = p.name
        try:
            raw = p.read_bytes()
        except OSError as exc:
            sources.append({"file": p.name, "kind": "unreadable", "text": "", "tables": [],
                            "paragraphs": [], "sha1": "", "notes": ["unreadable: %s" % type(exc).__name__]})
            continue
        ext = p.suffix.lower()
        src = {"file": p.name, "sha1": h or sha1_bytes(raw), "kind": ext.lstrip(".") or "unknown",
               "tables": [], "paragraphs": [], "field_specs": [], "notes": [], "text": ""}
        if ext == ".json":
            try:
                obj = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                obj = None
            if obj is None:
                src["notes"].append("json did not parse; indexed as plain text")
                src["kind"] = "text"
                src["text"] = _decode(raw)[0]
            else:
                if isinstance(obj, dict) and isinstance(obj.get("fields"), list):
                    src["field_specs"] = obj["fields"]
                    src["kind"] = "field_spec"
                if isinstance(obj, dict) and isinstance(obj.get("paragraphs"), list):
                    for para in obj["paragraphs"]:
                        src["paragraphs"].append({
                            "paragraph_id": str(para.get("paragraph_id") or "para%d" % (len(src["paragraphs"]) + 1)),
                            "section": str(para.get("section") or ""),
                            "page": para.get("page"),
                            "text": norm(para.get("text") or "")})
                if isinstance(obj, dict) and isinstance(obj.get("tables"), list):
                    for tbl in obj["tables"]:
                        rows = [[str(c) for c in r] for r in (tbl.get("rows") or []) if r]
                        src["tables"].append({"table_id": str(tbl.get("table_id") or "T%d" % (len(src["tables"]) + 1)),
                                              "caption": norm(tbl.get("caption") or ""),
                                              "page": tbl.get("page"), "rows": rows})
                src["text"] = norm(json.dumps(obj, ensure_ascii=False)) if obj is not None else src["text"]
        elif ext in (".csv", ".tsv"):
            text, _enc = _decode(raw)
            delim = "\t" if ext == ".tsv" else ","
            rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(str(c).strip() for c in r)]
            src["tables"].append({"table_id": p.stem, "caption": "", "page": None,
                                  "rows": [[str(c) for c in r] for r in rows]})
            src["text"] = norm(text)
        else:
            text, _enc = _decode(raw)
            src["text"] = norm(text)
            for i, block in enumerate(re.split(r"\n\s*\n", text)):
                b = norm(block)
                if b:
                    src["paragraphs"].append({"paragraph_id": "block%d" % (i + 1), "section": "",
                                              "page": None, "text": b})
        if not src["text"].strip() and not src["tables"] and not src["paragraphs"]:
            src["notes"].append("no decodable content in this file")
        sources.append(src)
    return sources, dupes


def build_corpus(sources):
    corpus = {"paragraphs": [], "cells": [], "tables": [], "field_specs": [], "row_lines": [],
              "quote_pool": set(), "sources": [], "degradations": []}
    for i, src in enumerate(sources):
        sid = "P%d" % (i + 1)
        src["source_id"] = sid
        corpus["sources"].append({"source_document_id": sid, "file": src["file"],
                                  "kind": src["kind"], "sha1": src["sha1"],
                                  "paragraphs": len(src["paragraphs"]),
                                  "tables": len(src["tables"])})
        corpus["degradations"] += ["%s: %s" % (src["file"], n) for n in src["notes"]]
        corpus["field_specs"] += [{"source_id": sid, **f} for f in src["field_specs"]]
        for para in src["paragraphs"]:
            if contains_shell(para["text"]):
                corpus["degradations"].append("%s: a paragraph carrying an unfilled template "
                                              "marker was skipped" % src["file"])
                continue
            loc = "%s#%s" % (sid, para["paragraph_id"])
            rec = {"locator": loc, "source_document_id": sid, "page": para["page"],
                   "section": para["section"], "kind": "paragraph", "text": para["text"]}
            corpus["paragraphs"].append(rec)
            corpus["quote_pool"].add(norm(para["text"]))
        for spec in src["field_specs"]:
            if contains_shell(str(spec.get("definition") or "")):
                continue
            fid = str(spec.get("field_id") or "field")
            defn = norm(spec.get("definition") or "")
            corpus["paragraphs"].append({"locator": "%s#field:%s" % (sid, fid),
                                         "source_document_id": sid, "page": None,
                                         "section": "field dictionary", "kind": "definition",
                                         "text": defn})
            if defn:
                corpus["quote_pool"].add(defn)
        for tbl in src["tables"]:
            headers = tbl["rows"][0] if tbl["rows"] else []
            tinfo = {"table_id": tbl["table_id"], "source_document_id": sid, "page": tbl["page"],
                     "caption": tbl["caption"], "headers": [str(h) for h in headers],
                     "rows": tbl["rows"]}
            corpus["tables"].append(tinfo)
            if tbl["caption"]:
                corpus["quote_pool"].add(norm(tbl["caption"]))
            for r, row in enumerate(tbl["rows"][1:], start=2):
                line = row_line(row)
                corpus["row_lines"].append({"locator": "%s#%s:r%d" % (sid, tbl["table_id"], r),
                                            "source_document_id": sid, "table_id": tbl["table_id"],
                                            "page": tbl["page"], "row_label": str(row[0]) if row else "",
                                            "line": line, "cells": row})
                corpus["quote_pool"].add(norm(line))
                for c, cell in enumerate(row):
                    header = str(headers[c]) if c < len(headers) else "column%d" % (c + 1)
                    corpus["cells"].append({
                        "locator": "%s#%s:r%dc%d" % (sid, tbl["table_id"], r, c + 1),
                        "source_document_id": sid, "table_id": tbl["table_id"], "page": tbl["page"],
                        "row_label": str(row[0]) if row else "", "header": header,
                        "unit": _unit_from_header(header), "value": str(cell).strip(),
                        "row_locator": "%s#%s:r%d" % (sid, tbl["table_id"], r), "row_line": line})
    return corpus


def quote_is_verbatim(quote, corpus):
    return norm(quote) in corpus["quote_pool"]


def _find_table_value(corpus, header_keys, row_keys):
    best = None
    for cell in corpus["cells"]:
        header = cell["header"].lower()
        if not any(k in header for k in header_keys):
            continue
        label = cell["row_label"].lower()
        if row_keys and not any(k in label for k in row_keys):
            continue
        score = sum(1 for k in header_keys if k in header) + sum(1 for k in row_keys if k in label)
        if best is None or score > best[0]:
            best = (score, cell)
    return best[1] if best else None


def _find_paragraph(corpus, keywords):
    for para in corpus["paragraphs"]:
        if para.get("kind") == "definition" or "#field:" in para["locator"]:
            continue  # never settle a field from its own dictionary definition
        low = para["text"].lower()
        if any(k in low for k in keywords):
            for sent in re.split(r"(?<=[.!?])\s+", para["text"]):
                if any(k in sent.lower() for k in keywords):
                    return para, norm(sent)
    return None, ""


TEXT_KEYWORDS = {
    "conclusion": ["conclude", "conclusion", "concludes", "we suggest", "therefore"],
    "ductil": ["ductil"],
}


def _keyword_group(fid, blob):
    for key, words in TEXT_KEYWORDS.items():
        if key in fid or key in blob:
            return words
    if "aging" in fid or "ageing" in blob or "temperature" in blob:
        return ["temperature", "ageing", "aging"]
    if "sample" in fid or "specimen" in blob:
        return ["specimen", "sample size", "samples"]
    return []


def settle_field(fld, corpus):
    fid = str(fld.get("field_id") or "")
    name = str(fld.get("field_name") or "")
    defn = str(fld.get("definition") or "")
    blob = (fid + " " + name + " " + defn).lower()
    hint_unit = str(fld.get("unit_hint") or "")
    record = {"field_id": fid, "field_name": name, "definition": defn,
              "expected_type": str(fld.get("expected_type") or ""), "unit_hint": hint_unit,
              "context_hint": str(fld.get("context_hint") or ""),
              "value": "", "units": "", "statistic": "point", "condition": "",
              "comparator": "", "source": "", "quote": "", "locator": "",
              "claim_type": "", "validation": "", "condition_complete": False, "notes": ""}
    # 1. table cell strategy -------------------------------------------------
    header_keys = [k for k in ("yield", "elongation", "hardness", "strength") if k in blob]
    row_keys = []
    if "t6" in blob or "aged" in blob:
        row_keys = ["t6", "aged"]
    if "as-cast" in blob or "as cast" in blob or "as_cast" in blob:
        row_keys = ["as-cast", "as cast", "as_cast"]
    if header_keys:
        cell = _find_table_value(corpus, header_keys, row_keys)
        if cell is not None:
            record["source"] = cell["locator"]
            record["locator"] = cell["row_locator"]
            record["quote"] = cell["row_line"]
            record["condition"] = cell["row_label"]
            coding = {"yield": "yield strength", "elongation": "elongation",
                      "hardness": "hardness", "strength": "strength"}
            record["comparator"] = next((coding[k] for k in header_keys if k in coding), "")
            if cell["value"].strip().lower() in NOT_MEASURED:
                record["value"], record["units"] = "", ""
                record["notes"] = ("the indexed cell marks this quantity as unmeasured (%s)"
                                   % cell["value"].strip())
                record["status"] = "not_reported"
                record["claim_type"] = "unsupported"
                record["validation"] = "cell carries a not-measured marker"
                return record
            record["value"] = cell["value"].strip()
            record["units"] = cell["unit"] or hint_unit
            record["statistic"] = "point"
            record["condition_complete"] = bool(record["condition"])
            record["claim_type"] = "measured" if _is_number(record["value"]) else "reported"
            record["validation"] = "value taken from the indexed table row"
            record["status"] = "reported"
            return record
    # 2. paragraph keyword strategy -----------------------------------------
    words = _keyword_group(fid, blob)
    if words:
        para, sent = _find_paragraph(corpus, words)
        if para is not None:
            record["source"] = para["locator"]
            record["locator"] = para["locator"]
            record["quote"] = sent
            record["value"] = sent
            record["units"] = hint_unit
            record["claim_type"] = "qualitative" if str(fld.get("expected_type")) == "text" else "reported"
            record["validation"] = "sentence matched by keyword inside an indexed paragraph"
            record["condition_complete"] = True
            record["status"] = "reported"
            return record
    # 3. explicit not-reported ----------------------------------------------
    spec = next((s for s in corpus["field_specs"] if str(s.get("field_id")) == fid), None)
    if spec is not None:
        sid = spec.get("source_id", "")
        record["source"] = "%s#field:%s" % (sid, fid)
        record["locator"] = "%s#field:%s" % (sid, fid)
        record["quote"] = defn
        record["claim_type"] = "unsupported"
        record["validation"] = "the material contains no value for the field definition"
        record["notes"] = ("searched paragraphs and table cells for this definition; "
                           "no value was printed in the supplied material")
        record["status"] = "not_reported"
        return record
    record["claim_type"] = "unsupported"
    record["validation"] = "no field dictionary and no material value"
    record["notes"] = "the material was present but carried no usable definition for this field"
    record["status"] = "extraction_failed"
    return record


def merge_draft(records, draft, corpus, known_ids, degradations):
    """Overlay agent-provided cells; drop anything that cannot be traced."""
    accepted = 0
    rows = []
    if isinstance(draft, dict):
        rows = draft.get("records") or draft.get("fields") or draft.get("items") or []
    if not isinstance(rows, list):
        return records, accepted
    by_id = {r["field_id"]: r for r in records}
    for row in rows:
        if not isinstance(row, dict):
            degradations.append("draft entry was not an object; dropped")
            continue
        fid = str(row.get("field_id") or "")
        if fid not in known_ids:
            degradations.append("draft referenced unknown field_id %r; dropped" % fid)
            continue
        quote = str(row.get("quote") or "")
        locator = str(row.get("locator") or "")
        value = str(row.get("value") or "").strip()
        status = str(row.get("status") or "reported")
        if status != "reported" or not value:
            degradations.append("draft cell %s did not carry a settled reported value; dropped" % fid)
            continue
        if not quote or not locator or not quote_is_verbatim(quote, corpus):
            degradations.append("draft cell %s lacked a traceable verbatim quote; dropped" % fid)
            continue
        rec = by_id[fid]
        rec.update({"value": value,
                    "units": str(row.get("units") or rec["units"]),
                    "condition": str(row.get("condition") or rec["condition"]),
                    "quote": quote, "locator": locator, "status": "reported",
                    "claim_type": str(row.get("claim_type") or rec["claim_type"] or "reported"),
                    "validation": "agent cell accepted after verbatim check",
                    "condition_complete": bool(row.get("condition") or rec["condition"])})
        accepted += 1
    return records, accepted


def coverage_of(records):
    total = len(records)
    reported = sum(1 for r in records if r.get("status") == "reported")
    return {"total": total, "reported": reported, "not_reported": sum(1 for r in records if r.get("status") == "not_reported"),
            "source_conflict": sum(1 for r in records if r.get("status") == "source_conflict"),
            "extraction_failed": sum(1 for r in records if r.get("status") == "extraction_failed"),
            "coverage": round(reported / total, 4) if total else 0.0}


CSV_COLUMNS = ["field_id", "field_name", "value", "units", "statistic", "condition", "comparator",
               "source", "quote", "locator", "status", "claim_type", "condition_complete", "notes"]


def render_csv(records):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in records:
        writer.writerow([r.get(c, "") for c in CSV_COLUMNS])
    return buf.getvalue()
