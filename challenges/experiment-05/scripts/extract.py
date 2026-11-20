# -*- coding: utf-8 -*-
"""Material scanning + source-grounded extraction for the interpretation dossier.

Reads every supplied file, indexes it with a locator, and pulls out the screening rules
(R1-R9), the unit dictionary, the threshold constants, the status table, the attribution
enum, the contract-key mapping and the artifact manifest -- each with a locator and a
verbatim quote.  A structure the material does not carry is recorded as searched-but-absent
rather than invented.
"""
import json
import math
import os
import re

RULE_ID = re.compile(r"^R\d+[′']?$")
NUMCELL = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\s*$")


def strict_num(v):
    """A cell counts as numeric only when the whole cell is a number."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return float(v)
    t = s(v)
    if NUMCELL.match(t):
        try:
            return float(t)
        except ValueError:
            return None
    return None

THRESH_MARKERS = [
    ("tol_default", "0.05", "--tol", "relative-deviation tolerance used by R3"),
    ("mad_scale", "0.6745", "0.6745", "modified z scale in 0.6745*(x-median)/MAD"),
    ("iqr_k", "1.5", "1.5*IQR", "IQR fence multiplier (Q1-1.5*IQR, Q3+1.5*IQR)"),
    ("modified_z_cut", "3.5", "|z|>3.5", "R1 fires when |modified z| exceeds this"),
    ("tol_cross_source", "0.05", "max(tol, 0.05)", "R9 cross-source comparison uses this floor"),
    ("tol_recalibration", "0.10", "max(tol, 0.10)", "R3' back-calculation widens the tolerance"),
]
CONFLICT_MARKERS = [
    ("tol_calibration", "0.05", "tol=0.05", "R7 example: analysis.m constant vs paper value"),
]


def s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
            return str(int(round(v)))
        return ("%.6f" % v).rstrip("0").rstrip(".")
    return str(v).strip()


def nkey(v):
    t = s(v).lower().replace("°", "").replace("℃", "c").replace("µ", "u")
    return re.sub(r"[^0-9a-z一-鿿]+", "", t)


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return float(v)
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", s(v).replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _paras(mid, text):
    out, buf, pi = [], [], 0
    for ln in (text or "").splitlines():
        if ln.strip():
            buf.append(ln.rstrip())
        elif buf:
            pi += 1
            out.append({"locator": "%s#p%d" % (mid, pi), "text": "\n".join(buf)})
            buf = []
    if buf:
        pi += 1
        out.append({"locator": "%s#p%d" % (mid, pi), "text": "\n".join(buf)})
    return out


def scan_materials(input_dir):
    mats = []
    if not os.path.isdir(input_dir):
        return mats
    idx = 0
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            idx += 1
            mid = "M%02d" % idx
            try:
                with open(full, "rb") as fh:
                    raw = fh.read(4_000_000)
            except OSError:
                raw = b""
            binary = b"\x00" in raw[:4096]
            text = "" if binary else raw.decode("utf-8", "replace")
            obj = None
            if fn.lower().endswith((".json", ".jsonl")) and text.strip():
                try:
                    obj = json.loads(text)
                except ValueError:
                    obj = None
            kind = "json"
            if obj is None:
                kind = "text" if text.strip() else ("binary" if binary else "empty")
            mats.append({"id": mid, "name": fn,
                         "rel": os.path.relpath(full, input_dir).replace("\\", "/"),
                         "path": full, "text": text, "json": obj,
                         "paras": _paras(mid, text), "chars": len(text),
                         "binary": binary, "kind": kind})
    return mats


def find_quote(text, needles, limit=280):
    if not text:
        return ""
    for n in needles:
        tok = s(n)
        if not tok:
            continue
        i = text.find(tok)
        if i < 0:
            i = text.lower().find(tok.lower())
            if i < 0:
                continue
        start = text.rfind("\n", 0, i)
        start = 0 if start < 0 else start + 1
        end = min(len(text), start + limit)
        if end < i + len(tok):
            end = min(len(text), i + len(tok) + 40)
        return text[start:end].strip()[:limit]
    return ""


def ev(mat, locator, needles):
    text = mat.get("text", "") if isinstance(mat, dict) else ""
    q = find_quote(text, needles)
    ok = bool(q) and q[:60] in text
    if not q:
        q = "no quotable line located at %s" % locator
    return {"source_id": mat.get("id", ""), "locator": locator, "quote": q, "verified": ok}


def line_of(text, needle, start=0):
    """Return (1-based line number, stripped line) of the first line containing needle."""
    if not text or not needle:
        return None, ""
    idx = text.find(needle, start)
    if idx < 0:
        idx = text.lower().find(needle.lower(), start)
        if idx < 0:
            return None, ""
    n = text.count("\n", 0, idx) + 1
    ls = text.rfind("\n", 0, idx) + 1
    le = text.find("\n", idx)
    if le < 0:
        le = len(text)
    return n, text[ls:le].strip()


# --------------------------------------------------------------- tables ------

def _split_cells(line):
    """Split a markdown table row on | but never inside a `code span`."""
    st = line.strip()
    if st.startswith("|"):
        st = st[1:]
    if st.endswith("|"):
        st = st[:-1]
    out, buf, in_code = [], [], False
    for ch in st:
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
        elif ch == "|" and not in_code:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf).strip())
    return out


def pipe_tables(mat):
    t = _md_tables(mat)
    if t:
        return t
    return _delimited_tables(mat)


def _delimited_tables(mat):
    """Parse a .csv/.tsv/.dat/.txt readout file with delimiter sniffing."""
    if not mat.get("name", "").lower().endswith((".csv", ".tsv", ".dat", ".txt", ".asc")):
        return []
    text = mat.get("text", "")
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 3:
        return []
    delim = None
    for d in (",", "\t", ";", "|"):
        cnts = [l.count(d) for l in lines[:20]]
        if cnts and min(cnts) >= 1 and len(set(cnts)) == 1:
            delim = d
            break
    if delim is None:
        return []
    header = [c.strip() for c in lines[0].split(delim)]
    if len(header) < 2:
        return []
    rows, raws, rlines = [], [], []
    for i, l in enumerate(lines[1:], start=2):
        cells = [c.strip() for c in l.split(delim)]
        if len(cells) < 2:
            continue
        rows.append({header[k] if k < len(header) else "col%d" % k: cells[k]
                     for k in range(len(cells))})
        raws.append(l.strip())
        rlines.append(i)
    if not rows:
        return []
    return [{"mat_id": mat["id"], "text": text, "locator": "%s#L1" % mat["id"],
             "header": header, "rows": rows, "raws": raws, "row_lines": rlines, "line": 1}]


def _md_tables(mat):
    text = mat.get("text", "")
    if not text:
        return []
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.count("|") >= 2 and i + 1 < len(lines) and re.match(
                r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = _split_cells(ln)
            j, rows, raws, rlines = i + 2, [], [], []
            while j < len(lines) and lines[j].count("|") >= 2 and lines[j].strip():
                cells = _split_cells(lines[j])
                if len(cells) >= 2:
                    rows.append({header[k] if k < len(header) else "col%d" % k: cells[k]
                                 for k in range(len(cells))})
                    raws.append(lines[j].strip())
                    rlines.append(j + 1)
                j += 1
            if rows:
                out.append({"mat_id": mat["id"], "text": text,
                            "locator": "%s#L%d" % (mat["id"], i + 1),
                            "header": header, "rows": rows, "raws": raws,
                            "row_lines": rlines, "line": i + 1})
            i = j
        else:
            i += 1
    return out


def classify(t):
    hn = [nkey(h) for h in t["header"]]
    j = "".join(hn)
    if "判据" in j and "触发条件" in j:
        return "rules"
    if hn and hn[0] == "status" and "触发" in j:
        return "status_map"
    if "正则" in j and hn and hn[-1] == "值":
        return "contract_map"
    if "枚举" in j:
        return "attr_enum"
    if "默认禁区" in j:
        return "dnc"
    if "概念" in j and "来源" in j and "说明" in j:
        return "field_dict"
    if "可改" in j:
        return "ownership"
    if "评分点" in j:
        return "rubric"
    if "扩展名" in j:
        return "parse_map"
    if "引用形态" in j:
        return "locator_form"
    if "作用" in j and "文件" in j:
        return "artifacts"
    if hn and hn[0] == "量" and "定义" in j:
        return "stats_def"
    return "table"


def extract_tables(ctx):
    for m in ctx["materials"]:
        for t in pipe_tables(m):
            kind = classify(t)
            for ri, row in enumerate(t["rows"]):
                if ri < len(t["row_lines"]):
                    loc = "%s#L%d" % (t["mat_id"], t["row_lines"][ri])
                else:
                    loc = "%s!r%d" % (t["locator"], ri + 1)
                quote = (t["raws"][ri] if ri < len(t["raws"]) else "")[:280]
                ctx["kinds"].setdefault(kind, []).append(
                    {"kind": kind, "locator": loc, "quote": quote,
                     "verified": bool(quote) and quote[:40] in t["text"],
                     "mat": t["mat_id"], "cells": {h: row.get(h, "") for h in t["header"]}})


# --------------------------------------------------------------- units -------

def extract_units(ctx):
    for m in ctx["materials"]:
        text = m["text"]
        if "单位" not in text:
            continue
        in_sec = False
        for i, ln in enumerate(text.splitlines()):
            st = ln.strip()
            if st.startswith("#"):
                in_sec = ("单位" in st and ("量纲" in st or "字典" in st))
                continue
            if not in_sec or not st or st.startswith("|") or st.startswith("-") or st.startswith(">"):
                continue
            mm = re.match(r"^([^：:]{2,24})[：:]\s*(.+)$", st)
            if not mm:
                continue
            units = []
            for v in re.findall(r"`([^`]+)`", mm.group(2)):
                units += [x.strip() for x in re.split(r"[,,、，]", v) if x.strip()]
            if units:
                ctx["units"].append({"quantity": mm.group(1).strip(), "units": units[:40],
                                     "evidence": ev(m, "%s#L%d" % (m["id"], i + 1), [st[:24]])})


def extract_thresholds(ctx):
    for name, value, marker, role in THRESH_MARKERS + CONFLICT_MARKERS:
        found = False
        for m in ctx["materials"]:
            n, line = line_of(m["text"], marker)
            if n:
                v = num(value)
                ctx["thresholds"].append(
                    {"name": name, "value": (v if v is not None else value), "unit": "",
                     "role": role, "locator": "%s#L%d" % (m["id"], n), "quote": line[:280],
                     "verified": line in m["text"],
                     "conflict": name.startswith("tol_calibration"),
                     "note": "indexed from the material definition"})
                found = True
                break
        if not found:
            ctx["searched"].append({"item": "threshold:%s" % name,
                                    "why": "no line carrying the marker %r was found" % marker})


# --------------------------------------------------------------- draft -------

def _is_true(v):
    if v is True:
        return True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v == 1
    return s(v).lower() in ("true", "yes", "1", "confirmed")


def _candidate_dossier(d, i):
    if not isinstance(d, dict):
        return None
    did = s(d.get("id")) or "A-%03d" % (i + 1)
    return {"id": did,
            "anomaly_type": s(d.get("anomaly_type")) or "outlier",
            "target": s(d.get("target")),
            "locator": s(d.get("locator")),
            "observed": s(d.get("observed")),
            "expected_or_rule": s(d.get("expected_or_rule")),
            "rule_id": s(d.get("rule_id")),
            "severity": s(d.get("severity")) or "medium",
            "verdict": (s(d.get("verdict")) or "undetermined") if _is_true(d.get("judged")) else "undetermined",
            "judged": _is_true(d.get("judged")),
            "attribution": s(d.get("attribution")),
            "attribution_basis": s(d.get("attribution_basis")),
            "evidence_quote": s(d.get("evidence_quote")),
            "excluded_alternatives": list(d.get("excluded_alternatives") or []),
            "do_not_conclude": list(d.get("do_not_conclude") or []),
            "recheck_actions": list(d.get("recheck_actions") or []),
            "next_experiment": s(d.get("next_experiment")),
            "strength": s(d.get("strength")) or "A",
            "source": "agent_added" if d.get("source") == "agent_added" else "draft"}


def extract_from_draft(ctx, draft):
    if not isinstance(draft, dict):
        return
    ctx["notes"]["draft_present"] = True
    ctx["trends"] = [d for d in (draft.get("trends") or []) if isinstance(d, dict)][:30]
    ctx["causes"] = [d for d in (draft.get("causes") or []) if isinstance(d, dict)][:30]
    for i, d in enumerate(draft.get("dossiers") or []):
        rec = _candidate_dossier(d, i)
        if rec:
            ctx["dossiers"].append(rec)
    ctx["draft_uncertainties"] = [s(x) for x in (draft.get("uncertainties") or [])][:30]
    ctx["draft_confirmations"] = [s(x) for x in (draft.get("confirmations") or [])][:30]
    ctx["draft_next_steps"] = [s(x) for x in (draft.get("next_steps") or [])][:30]
    if isinstance(draft.get("result_fields"), dict):
        ctx["draft_result_fields"] = {s(k): s(v) for k, v in draft["result_fields"].items()}
    if s(draft.get("dataset_note")):
        ctx["notes"]["dataset_note"] = s(draft.get("dataset_note"))


# --------------------------------------------------------------- assemble ----

def extract(case, mats, draft=None):
    ctx = {"case_id": s((case or {}).get("case_id")) or s((case or {}).get("id")) or "unknown-case",
           "_case": case, "materials": [], "errors": [], "kinds": {},
           "units": [], "thresholds": [], "searched": [], "degradations": [],
           "dossiers": [], "trends": [], "causes": [], "draft_result_fields": {},
           "draft_uncertainties": [], "draft_confirmations": [], "draft_next_steps": [],
           "series": [], "notes": {},
           "task_instruction": s((case or {}).get("task_instruction")
                                 or (case or {}).get("prompt") or (case or {}).get("task"))}
    for m in mats:
        ctx["materials"].append(m)
    extract_tables(ctx)
    extract_units(ctx)
    extract_thresholds(ctx)
    ctx["series"] = find_series(ctx)
    extract_from_draft(ctx, draft)
    _degradations(ctx)
    return ctx


def find_series(ctx):
    """Numeric tables: a column with >=5 parseable numbers is treated as a series."""
    out = []
    for m in ctx["materials"]:
        for t in pipe_tables(m):
            head = t["header"]
            for ci, h in enumerate(head):
                col, rows = [], []
                for ri, row in enumerate(t["rows"]):
                    v = strict_num(row.get(h))
                    if v is not None:
                        col.append(v)
                        rows.append(t["row_lines"][ri] if ri < len(t["row_lines"]) else 0)
                if len(col) >= 5:
                    out.append({"mat": m["id"], "column": h, "n": len(col),
                                "values": [round(x, 6) for x in col[:400]],
                                "locator": "%s#L%d" % (m["id"], t["line"] + 1),
                                "row_lines": rows[:400]})
    return out[:24]


def _degradations(ctx):
    if not any(m["chars"] > 0 for m in ctx["materials"]):
        ctx["degradations"].append(
            "No readable material file was supplied; only the inventory and the rule "
            "index derived from the case instruction are reported.")
    if not ctx["kinds"].get("rules"):
        ctx["degradations"].append(
            "No screening-rule table (id/judge/trigger) was found; the anomaly screen is "
            "reported as not declared rather than assumed from the case label.")
    if not ctx["units"]:
        ctx["degradations"].append(
            "No unit dictionary was found; the unit-consistency check is reported as not declared.")
    if not ctx["thresholds"]:
        ctx["degradations"].append(
            "No threshold constant was found; the deviation checks report their searched locations.")
    if not ctx["series"]:
        ctx["degradations"].append(
            "No numeric readout column with five or more values was found, so no trend or "
            "deviation could be computed; the searched locations are listed and the rule "
            "definitions are indexed instead.")
    if not ctx["dossiers"]:
        ctx["degradations"].append(
            "No anomaly dossier was supplied in the work draft and no numeric series was "
            "available to raise one from the rules; the dossier set is reported as empty.")
    if not ctx["trends"]:
        ctx["degradations"].append(
            "No trend statement was supplied in the work draft; the five-part conclusion "
            "keeps its trend section as an explicit evidence gap.")
    for m in ctx["materials"]:
        if m["kind"] == "json" and m["json"] is None and m["chars"]:
            ctx["degradations"].append(
                "Material %s looks like JSON but did not parse; only its size is recorded." % m["id"])
        if m["kind"] in ("binary", "empty"):
            ctx["degradations"].append(
                "Material %s is %s; only its size is recorded." % (m["id"], m["kind"]))
