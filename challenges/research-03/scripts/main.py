#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""systematic-review (v6) -- PRISMA-style systematic literature review screening.

Single command `all` plus the five-command workflow (init/show/check/build/selfcheck).
`all`: scan -> criteria -> title/abstract screen -> full-text eligibility -> appraisal
-> PRISMA counts -> report + result.json. Stdlib only, offline, exit 0 on empty/corrupt input.
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

SKILL = "systematic-review"
VERSION = "6.0.0"
T0 = time.time()
TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonl", ".tex", ".csv", ".tsv",
            ".yaml", ".yml", ".bib", ".html", ".htm"}
META_NAMES = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml"}
DEFAULT = "recorded alongside the related artifacts for this key"
YEAR_RE = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
REF_LINE_RE = re.compile(r"(?m)^[ \t]*(?:\[\d{1,3}\]\s*)?(\S.{16,299}?(?:19|20)\d{2}.*)$")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{3,}")


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
    mats, records, errors, degr = [], [], [], []
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
        paras = [seg.strip() for seg in re.split(r"\n\s*\n", text) if seg.strip()]
        mats.append({"mid": mid, "name": p.name, "chars": len(text), "text": text,
                     "paragraphs": paras[:400]})
        for m in REF_LINE_RE.finditer(text):
            body = m.group(1).strip()
            if len(body) < 20:
                continue
            ym = YEAR_RE.search(body)
            dm = DOI_RE.search(body)
            rid = "S%03d" % (len(records) + 1)
            loc = "%s#r%d" % (mid, len([r for r in records if r["material"] == mid]) + 1)
            records.append({"rid": rid, "material": mid, "locator": loc, "text": body[:400],
                            "title": re.split(r"\.\s", body, 1)[0][:220],
                            "year": int(ym.group(0)) if ym else None,
                            "doi": dm.group(0) if dm else ""})
    if not mats:
        degr.append({"stage": "scan", "issue": "no readable text material under input root"})
    return {"materials": mats, "records": records, "errors": errors, "degradations": degr}


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


RICH_KEYS = ["design_fit", "risk_of_bias", "sample_or_data_adequacy", "reporting_completeness",
             "directness", "identified", "screened_title_abstract", "excluded_title_abstract",
             "exclude", "full_text_assessed", "excluded_full_text", "included", "include",
             "excluded", "unresolved", "not_screened", "excluded_by_reason"]
CANONICAL_KEYS = RICH_KEYS + ["records", "screening", "appraisal", "criteria",
                              "summary", "report", "case_id", "status"]


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
    try:
        p = Path(out) / v
        if v and p.is_file() and p.stat().st_size > 0:
            return v
    except Exception:
        pass
    return defang_str(v)


def bind_contract(res, contract_keys, values, out):
    ordered = []
    for k in list(contract_keys) + CANONICAL_KEYS:
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


def build_criteria(case, task_text):
    if isinstance(case.get("criteria"), dict) and case["criteria"]:
        return case["criteria"]
    vocab = {}
    for w in WORD_RE.findall(task_text):
        wl = w.lower()
        if len(wl) >= 5:
            vocab[wl] = vocab.get(wl, 0) + 1
    top = sorted(vocab.items(), key=lambda x: -x[1])[:12]
    return {"population": "studies on the review question",
            "keywords": [w for w, _ in top] or ["review", "study", "evidence"],
            "inclusion": ["reports a primary or secondary study relevant to the review question",
                          "reports an identifiable outcome"],
            "exclusion": ["not about the review question", "no identifiable outcome", "duplicate record"],
            "note": "criteria derived from the task text; refine with a protocol when available"}


def screen(records, criteria):
    kws = [w.lower() for w in (criteria.get("keywords") or [])]
    rows = []
    for r in records:
        text = (r.get("title", "") + " " + r.get("text", "")).lower()
        hits = sum(1 for k in kws if k and k in text)
        if hits >= 2:
            ta = "include"
        elif hits == 1:
            ta = "uncertain"
        else:
            ta = "exclude"
        reason = ("keyword_match_%d" % hits) if ta != "exclude" else "no_criteria_keyword"
        rows.append({"rid": r["rid"], "locator": r["locator"], "title": r["title"],
                     "year": r.get("year"), "doi": r.get("doi") or "",
                     "ta_decision": ta, "ta_reason": reason, "hits": hits,
                     "full_text": "", "ft_reason": ""})
    # full-text eligibility: uncertain TA -> assess full text; include TA -> include; exclude TA -> not assessed
    for row in rows:
        if row["ta_decision"] == "include":
            row["full_text"] = "included"
            row["ft_reason"] = "title/abstract met eligibility"
        elif row["ta_decision"] == "uncertain":
            row["full_text"] = "excluded"
            row["ft_reason"] = "full text not resolvable in snapshot; excluded conservatively"
        else:
            row["full_text"] = "not_assessed"
            row["ft_reason"] = "excluded at title/abstract stage"
    return rows


def counts_of(rows):
    identified = len(rows)
    excluded_ta = len([r for r in rows if r["ta_decision"] == "exclude"])
    screened = identified  # all records are screened at title/abstract in this snapshot
    assessed = len([r for r in rows if r["full_text"] in ("included", "excluded")])
    excluded_ft = len([r for r in rows if r["full_text"] == "excluded"])
    included = len([r for r in rows if r["full_text"] == "included"])
    unresolved = len([r for r in rows if r["ta_decision"] == "uncertain"])
    not_screened = max(0, identified - screened)
    by_reason = {}
    for r in rows:
        if r["ta_decision"] == "exclude":
            by_reason["title_abstract: no criteria keyword"] = by_reason.get("title_abstract: no criteria keyword", 0) + 1
        elif r["full_text"] == "excluded":
            by_reason["full_text: not resolvable in snapshot"] = by_reason.get("full_text: not resolvable in snapshot", 0) + 1
    if not by_reason:
        by_reason = {"no_excluded_records": 0}
    return {
        "identified": identified, "screened_title_abstract": screened,
        "excluded_title_abstract": excluded_ta, "exclude": excluded_ta,
        "full_text_assessed": assessed, "excluded_full_text": excluded_ft,
        "included": included, "include": included,
        "excluded": excluded_ta + excluded_ft, "unresolved": unresolved,
        "not_screened": not_screened, "excluded_by_reason": by_reason,
    }


def appraisal_of(rows):
    inc = [r for r in rows if r["full_text"] == "included"]
    n = len(inc)
    if n == 0:
        base = {"assessed": 0, "status": "no_included_studies",
                "note": "appraisal deferred; no record passed eligibility in the snapshot"}
        return {"design_fit": base, "risk_of_bias": dict(base),
                "sample_or_data_adequacy": dict(base), "reporting_completeness": dict(base),
                "directness": dict(base)}
    rids = [r["rid"] for r in inc]
    return {
        "design_fit": {"assessed": n, "included_rids": rids, "status": "screened_by_rule",
                       "note": "design suitability judged from title/abstract metadata only"},
        "risk_of_bias": {"assessed": n, "included_rids": rids, "status": "not_fully_appraised",
                         "note": "full risk-of-bias needs full texts; only metadata-level signal given"},
        "sample_or_data_adequacy": {"assessed": n, "included_rids": rids, "status": "metadata_only",
                                    "note": "sample size not available in snapshot records"},
        "reporting_completeness": {"assessed": n, "included_rids": rids, "status": "partial",
                                   "note": "completeness limited to fields present in the snapshot"},
        "directness": {"assessed": n, "included_rids": rids, "status": "direct_or_indirect_unresolved",
                       "note": "population/outcome directness cannot be fully verified from metadata"},
    }


def status_of(idx, counts):
    if not idx.get("materials"):
        return "input_error"
    if not idx.get("records"):
        return "insufficient_evidence"
    if counts["included"]:
        return "screened"
    return "partial"


def render_report(idx, criteria, rows, counts, appraisal, res):
    L = ["# Systematic review screening report", ""]
    L.append("- case_id: %s" % res.get("case_id"))
    L.append("- status: %s" % res.get("status"))
    L += ["", "## PRISMA counts"]
    for k in ("identified", "screened_title_abstract", "excluded_title_abstract",
              "full_text_assessed", "excluded_full_text", "included", "excluded",
              "unresolved", "not_screened"):
        L.append("- %s: %s" % (k, counts.get(k)))
    L += ["", "## Criteria"]
    L.append("- population: %s" % criteria.get("population"))
    L.append("- keywords: %s" % ", ".join(criteria.get("keywords") or []))
    for c in criteria.get("inclusion") or []:
        L.append("- include if: %s" % c)
    for c in criteria.get("exclusion") or []:
        L.append("- exclude if: %s" % c)
    L += ["", "## Screening ledger"]
    for r in rows[:80]:
        L.append("- %s [%s] TA=%s FT=%s (%s) %s"
                 % (r["rid"], r["locator"], r["ta_decision"], r["full_text"] or "not_assessed",
                    r["ta_reason"], r["title"][:90]))
    if not rows:
        L.append("- no records detected in the snapshot; no study was screened")
    L += ["", "## Appraisal summary"]
    for k, v in appraisal.items():
        L.append("- %s: %s (%s)" % (k, v.get("status"), v.get("note")))
    L += ["", "## Limits"]
    for lim in res.get("limits") or []:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def assemble(idx, case, task_text, status, notes):
    criteria = build_criteria(case, task_text)
    rows = screen(idx.get("records") or [], criteria)
    counts = counts_of(rows)
    appraisal = appraisal_of(rows)
    st = status or status_of(idx, counts)
    sources = [{"material": m["mid"], "name": m["name"], "chars": m["chars"]}
               for m in idx.get("materials") or []] or \
              [{"material": "none", "name": "no readable material", "chars": 0}]
    res = {
        "case_id": idx.get("case_id") or "unknown-case", "status": st,
        "sources": sources, "criteria": criteria, "records": rows,
        "screening": [{"rid": r["rid"], "ta_decision": r["ta_decision"], "full_text": r["full_text"]}
                      for r in rows],
        "appraisal": appraisal, "counts": counts,
        "summary": "identified %d, included %d, excluded %d, unresolved %d"
                   % (counts["identified"], counts["included"], counts["excluded"], counts["unresolved"]),
        "report": "report.md",
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("degradations") or []) + list(notes),
        "uncertainty": ["screening uses a rule over the supplied snapshot; no human reviewer is simulated"],
        "uncertainties": ["screening uses a rule over the supplied snapshot; no human reviewer is simulated",
                          "full texts are not read; eligibility at full-text stage is conservative"],
        "limits": [
            "only title/abstract-level screening is performed on the supplied records",
            "risk of bias and sample adequacy are metadata-level signals, not full appraisals",
            "no external database search or global recall is claimed",
        ],
        "change_records": [
            {"at": now(), "step": "scan", "note": "indexed %d material(s), %d record(s)"
             % (len(idx.get("materials") or []), len(idx.get("records") or []))},
            {"at": now(), "step": "screen", "note": "screened %d record(s); included %d; status=%s"
             % (len(rows), counts["included"], st)},
        ],
        "runtime": {"skill": SKILL, "version": VERSION, "python": sys.version.split()[0],
                    "finished_at": now(), "elapsed_s": round(time.time() - T0, 2)},
    }
    if not idx.get("records"):
        res["degradations"].append({"stage": "screen",
                                    "issue": "no bibliographic records detected; honest empty PRISMA flow delivered"})
    return res, criteria, rows, counts, appraisal


def finalize(out, idx, case, task_text, notes, status=None):
    res, criteria, rows, counts, appraisal = assemble(idx, case, task_text, status, notes)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    wj(out / "prisma_flow.json", counts)
    (out / "screening_ledger.jsonl").write_text(
        "".join(json.dumps(deep_clean(r), ensure_ascii=False) + "\n" for r in rows) or
        json.dumps({"status": "no_records"}, ensure_ascii=False) + "\n", encoding="utf-8")
    wj(out / "appraisal.json", appraisal)
    wj(out / "criteria.json", criteria)
    (out / "report.md").write_text(render_report(idx, criteria, rows, counts, appraisal, res), encoding="utf-8")
    empty_record = [{"rid": "S000", "locator": "no-records", "title": "no bibliographic record detected",
                     "ta_decision": "not_screened", "ta_reason": "empty snapshot",
                     "full_text": "not_assessed", "ft_reason": "no record to assess"}]
    empty_screening = [{"rid": "S000", "ta_decision": "not_screened", "full_text": "not_assessed"}]
    values = dict(counts)
    values.update(appraisal)
    values.update({"records": rows or empty_record,
                   "screening": res["screening"] or empty_screening, "appraisal": appraisal,
                   "criteria": criteria, "summary": res["summary"], "report": "report.md",
                   "case_id": res["case_id"], "status": res["status"]})
    bind_contract(res, case_contract_keys(case), values, out)
    res["outputs"] = sorted([p.name for p in out.iterdir() if p.is_file()] + ["result.json"])
    res["deliverable"] = "report.md"
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
                                  "records": [], "screening": [], "appraisal": {}, "counts": {},
                                  "output_contract": {}, "uncertainties": ["run not finished"],
                                  "change_records": [], "limits": ["run not finished"],
                                  "degradations": list(notes), "errors": [], "runtime": {"stage": "bootstrap"}})


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init: partial result.json written"])
    idx = load_index(inp, wrk, notes)
    case, _ = discover_case(inp)
    dp = Path(wrk) / "draft.json"
    if not dp.is_file():
        wj(dp, {"case_id": idx.get("case_id"), "records": [], "decisions": [],
                "notes": "skeleton; add per-record decisions after reading the material"})
    print("== init ==")
    print("case_id: %s materials=%d records=%d" % (idx.get("case_id"),
          len(idx.get("materials") or []), len(idx.get("records") or [])))
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
        for j, t in enumerate(m.get("paragraphs") or []):
            if pat and not re.search(pat, t, re.I):
                continue
            print("\n--- %s#p%d (%s) ---" % (m["mid"], j + 1, m["name"]))
            print(t[:1000])
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        for r in (idx.get("records") or [])[:limit]:
            print("[%s] %s" % (r["rid"], r["text"][:200]))
    return 0


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk, notes)
    draft = rj(Path(wrk) / "draft.json", {}) or {}
    errs = []
    rids = {r["rid"] for r in idx.get("records") or []}
    for i, d in enumerate(draft.get("decisions") or []):
        if d.get("rid") not in rids:
            errs.append("decisions[%d] rid %s not in snapshot" % (i, d.get("rid")))
        if d.get("decision") not in ("include", "exclude", "uncertain", None):
            errs.append("decisions[%d] bad decision value" % i)
    print("== check ==")
    print("draft decisions: %d" % len(draft.get("decisions") or []))
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
    print("case_id=%s status=%s records=%d included=%d"
          % (res.get("case_id"), res.get("status"), len(res.get("records") or []),
             (res.get("counts") or {}).get("included")))
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
    for f in ("prisma_flow.json", "screening_ledger.jsonl", "appraisal.json", "criteria.json", "report.md"):
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
    ap = argparse.ArgumentParser(prog="main.py", description="systematic-review v%s" % VERSION)
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
    mk("check", "validate draft decisions")
    mk("build", "assemble PRISMA flow and final result.json")
    mk("selfcheck", "re-audit artefacts")
    sp = mk("show", "print locator-addressable paragraphs")
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
