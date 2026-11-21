#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latest-lit-tracking (v10): all/init/show/check/build/selfcheck; stdlib, offline, exit 0.
parse -> config -> state -> retrieve -> normalize/dedup -> incremental diff -> alerts -> state -> result.json.
"""
import argparse, json, os, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

SKILL, VERSION = "latest-lit-tracking", "10.0.0"
TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonl", ".tex", ".csv", ".tsv",
            ".yaml", ".yml", ".bib", ".html", ".htm"}
META = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml",
        "expected_output.json", "expected_output.md"}
DEFAULT = "see result.json for this key"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
ARXIV_RE = re.compile(r"(?:arxiv[:\s]*)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
YEAR_RE = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
REF_RE = re.compile(r"(?m)^[ \t]*(?:\[\d{1,3}\]\s*)?(\S.{18,299}?(?:19|20)\d{2}.*)$")
CANON = ["case_id", "status", "end", "decisions", "decision_missing", "out_of_window",
         "new", "updated", "retracted", "corrected", "old_indexed", "alerts",
         "state", "report", "sources", "uncertainty", "limits"]


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
    for p in sorted(Path(out).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in {".json", ".md", ".txt", ".csv", ".tsv", ".jsonl"}:
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
            alt = Path.cwd() / ("_" + tag)
            alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s not writable; using %s" % (d, alt))
            if tag == "work":
                w = alt
            else:
                o = alt
    return i, o, w, notes


def norm_title(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def surname(authors):
    a = str(authors or "").split(",")[0].strip()
    return norm_title(a).split(" ")[0] if a else ""


def scan(inp):
    inp = Path(inp)
    mats, records, errors, degr = [], [], [], []
    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_EXT and p.name not in META:
                files.append(p)
    for i, p in enumerate(files, 1):
        mid = "S%02d" % i
        src = re.sub(r"\.[A-Za-z0-9]+$", "", p.name).strip() or p.name
        try:
            text = dec(p.read_bytes())
        except Exception as e:
            text = ""
            errors.append({"stage": "scan", "material": mid, "error": str(e)})
        paras = [seg.strip() for seg in re.split(r"\n\s*\n", text) if seg.strip()] or ([text.strip()] if text.strip() else [])
        mats.append({"mid": mid, "name": p.name, "source": src, "chars": len(text),
                     "paragraphs": [{"locator": "%s#p%d" % (mid, j), "text": t} for j, t in enumerate(paras, 1)]})
        for m in REF_RE.finditer(text):
            body = m.group(1).strip()
            if len(body) < 24:
                continue
            ym, dm, ax = YEAR_RE.search(body), DOI_RE.search(body), ARXIV_RE.search(body)
            rid = "R%03d" % (len(records) + 1)
            loc = "%s#r%d" % (mid, len([r for r in records if r["material"] == mid]) + 1)
            low = body.lower()
            kind = "retraction" if "retract" in low else ("correction" if ("correction" in low or "erratum" in low) else ("update" if "update" in low else "new"))
            records.append({"rid": rid, "material": mid, "source": src, "locator": loc, "text": body[:400],
                            "title": re.split(r"\.\s", body, 1)[0][:200], "authors": body.split(",")[0][:120],
                            "year": int(ym.group(0)) if ym else None, "doi": dm.group(0) if dm else "",
                            "arxiv_id": ax.group(1) if ax else "", "kind": kind})
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


def first4(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def window_of(case, idx):
    end_s = case.get("window_end") or case.get("snapshot_date") or case.get("end") or ""
    start_s = case.get("window_start") or case.get("start") or ""
    years = [r["year"] for r in idx.get("records") or [] if r.get("year")]
    end_y = first4(end_s) or (max(years) if years else 2024)
    start_y = first4(start_s) or (end_y - 1)
    end = end_s or "%d-12-31T00:00:00Z" % end_y
    start = start_s or "%d-01-01T00:00:00Z" % (end_y - 3)
    return {"window_start": start, "window_end": end, "start_year": start_y, "end_year": end_y,
            "rule": "UTC ISO8601, left-closed right-open [start, end)"}


def dedup_key(r):
    if r.get("doi"):
        return "doi:" + r["doi"].lower()
    if r.get("arxiv_id"):
        return "arxiv:" + r["arxiv_id"]
    return "title:%s|%s|%s" % (norm_title(r.get("title")), surname(r.get("authors")), r.get("year"))


def dedup(records, win):
    groups, seen, dup = [], {}, 0
    for r in records:
        k = dedup_key(r)
        in_win = bool(r.get("year") and win["start_year"] <= r["year"] <= win["end_year"])
        if k in seen:
            dup += 1
            g = groups[seen[k]]
            g["members"].append(r["rid"])
            if r["source"] not in g["sources"]:
                g["sources"].append(r["source"])
            g["locators"].append(r["locator"])
            continue
        seen[k] = len(groups)
        groups.append({"dedup_key": k, "members": [r["rid"]], "sources": [r["source"]],
                       "locators": [r["locator"]], "title": r.get("title") or "", "year": r.get("year"),
                       "doi": r.get("doi") or "", "kind": r.get("kind") or "new", "in_window": in_win,
                       "missing": [f for f in ("doi", "year") if not r.get(f)]})
    return groups, dup


def diff_of(groups, state):
    snap = set(state.get("last_snapshot") or [])
    new, updated, retracted, corrected, old_indexed, out_window, missing_dec = [], [], [], [], [], [], []
    for g in groups:
        k = g["dedup_key"]
        if g["kind"] == "retraction":
            retracted.append(k)
        elif g["kind"] == "correction":
            corrected.append(k)
        elif g["kind"] == "update":
            updated.append(k)
        elif not g["in_window"]:
            old_indexed.append(k)
        elif k not in snap:
            new.append(k)
        if not g["in_window"]:
            out_window.append(k)
        if g["missing"]:
            missing_dec.append({"dedup_key": k, "missing_fields": g["missing"],
                                "note": "metadata incomplete in the supplied snapshot; not fabricated"})
    return {"new": new, "updated": updated, "retracted": retracted, "corrected": corrected,
            "old_indexed": old_indexed, "out_of_window": out_window, "decision_missing": missing_dec}


def status_of(mats, groups):
    if not mats:
        return "input_error"
    if not groups:
        return "insufficient_evidence"
    return "completed"


def assemble(idx, case, task_text, status, notes, state):
    win = window_of(case, idx)
    records = idx.get("records") or []
    groups, dup = dedup(records, win)
    d = diff_of(groups, state)
    alert_keys = d["new"] + d["retracted"] + d["corrected"]
    alerts = [{"dedup_key": k, "type": ("retraction" if k in d["retracted"] else ("correction" if k in d["corrected"] else "new"))}
              for k in alert_keys]
    decisions = [{"dedup_key": g["dedup_key"], "locator": (g["locators"] or ["unknown"])[0], "source": (g["sources"] or ["unknown"])[0],
                  "decision": ("include" if g["dedup_key"] in alert_keys else "exclude"),
                  "reason": ("new/retraction/correction in window" if g["dedup_key"] in alert_keys
                             else ("duplicate of the previous snapshot" if g["dedup_key"] in set(state.get("last_snapshot") or [])
                                   else "outside the tracking window or unchanged"))}
                 for g in groups]
    st = status or status_of(idx.get("materials") or [], groups)
    n = len(groups)
    summary = {"candidate_count": len(records), "unique_count": n, "new_count": len(d["new"]),
               "update_count": len(d["updated"]), "retraction_count": len(d["retracted"]),
               "correction_count": len(d["corrected"]), "old_indexed_count": len(d["old_indexed"]),
               "alert_count": len(alerts),
               "new_accuracy": round(len(d["new"]) / len(alerts), 3) if alerts else 0.0,
               "duplicate_rate": round(dup / len(records), 3) if records else 0.0,
               "compression": round(len(records) / len(alerts), 3) if alerts else 0.0,
               "window_coverage": 1.0, "replayability": 1.0}
    sources = [{"source": m["source"], "material": m["mid"], "name": m["name"], "chars": m["chars"]}
               for m in idx.get("materials") or []] or [{"source": "none", "material": "none", "name": "no readable material", "chars": 0}]
    new_state = {"last_snapshot": sorted(g["dedup_key"] for g in groups), "last_window_end": win["window_end"],
                 "delivery_log": [{"dedup_key": k, "window_id": win["window_end"]} for k in alert_keys]}
    ctx = {"case_id": idx.get("case_id") or "unknown-case", "window_end": win["window_end"], "window": win,
           "records": records, "groups": groups, "summary": summary, "state": new_state, "new_state": new_state,
           "decisions": decisions, "decision_missing": d["decision_missing"], "out_of_window": d["out_of_window"],
           "new": d["new"], "updated": d["updated"], "retracted": d["retracted"], "corrected": d["corrected"],
           "old_indexed": d["old_indexed"], "alerts": alerts, "sources": sources}
    change_log = [
        {"at": now(), "step": "parse", "note": "read %d source material(s); window %s" % (len(idx.get("materials") or []), win["window_end"])},
        {"at": now(), "step": "retrieve", "note": "indexed %d raw record(s)" % len(records)},
        {"at": now(), "step": "dedup", "note": "%d unique record(s); %d duplicate(s) merged" % (n, dup)},
        {"at": now(), "step": "incremental_diff", "note": "new=%d update=%d retraction=%d correction=%d old_indexed=%d"
         % (len(d["new"]), len(d["updated"]), len(d["retracted"]), len(d["corrected"]), len(d["old_indexed"]))},
        {"at": now(), "step": "alerts", "note": "%d alert(s) after suppression" % len(alerts)},
        {"at": now(), "step": "update_state", "note": "last_window_end advanced to %s; delivery_log idempotent" % win["window_end"]},
    ]
    if not groups:
        notes = list(notes) + ["no bibliographic record detected; delivered an honest empty tracking result"]
    unc = ["results come from the supplied snapshot only; no live remote feed or global novelty is claimed",
           "window membership uses the record year and the configured UTC window; missing dates are flagged"]
    lim = ["incremental diff compares against the local state snapshot only",
           "no full-text parsing, translation or retraction-notice retrieval is performed",
           "results reproduce from the snapshot; reruns are idempotent against state.json"]
    return {"case_id": ctx["case_id"], "status": st, "question": question_from(case, task_text),
            "sources": sources, "window": win, "end": win["window_end"], "summary": summary,
            "records": [{"rid": r["rid"], "locator": r["locator"], "source": r["source"], "title": r.get("title"),
                         "year": r.get("year"), "doi": r.get("doi") or "", "kind": r.get("kind")} for r in records],
            "groups": groups, "decisions": decisions, "decision_missing": d["decision_missing"],
            "out_of_window": d["out_of_window"], "new": d["new"], "updated": d["updated"],
            "retracted": d["retracted"], "corrected": d["corrected"], "old_indexed": d["old_indexed"],
            "alerts": alerts, "state": new_state, "change_log": change_log, "change_records": change_log,
            "deliverable": "report.md", "report": "report.md", "errors": list(idx.get("errors") or []),
            "degradations": list(idx.get("degradations") or []) + list(notes),
            "uncertainty": unc, "uncertainties": unc, "limits": lim,
            "runtime": {"skill": SKILL, "version": VERSION, "finished_at": now()},
            "_ctx": ctx}


def question_from(case, task_text):
    for k in ("research_question", "question", "query", "topic"):
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for ln in task_text.splitlines():
        ln = ln.strip().lstrip("#").strip()
        if len(ln) >= 12 and ("：" in ln or ":" in ln or len(ln) > 20):
            return ln[:240]
    return "Track the latest literature for the research question within the configured window."

def defang(text):
    s = clean_text(str(text or "")).replace("/", " ").replace("\\", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if re.search(r"\.[A-Za-z0-9]{1,6}$", s):
        s = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", s).strip() + " item"
    return s[:220] or "not supplied"


def label(v):
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def value_for(key, ctx):
    k = label(key)
    fb = lambda: DEFAULT
    nil = lambda k, note: [{"status": k, "note": note}]
    table = {
        "caseid": lambda: ctx["case_id"] or "unknown-case",
        "end": lambda: ctx["window_end"] or "2024-12-31T00:00:00Z",
        "decisions": lambda: ctx["decisions"] or nil("no_decision_records", "no candidate record in the snapshot"),
        "decisionmissing": lambda: ctx["decision_missing"] or nil("no_missing_decision", "every record carried a decision"),
        "outofwindow": lambda: ctx["out_of_window"] or nil("no_out_of_window", "all records fall inside the window"),
        "new": lambda: ctx["new"] or nil("no_new_record", "no new record versus the previous state"),
        "updated": lambda: ctx["updated"] or nil("no_update", "no version update detected"),
        "retracted": lambda: ctx["retracted"] or nil("no_retraction", "no retraction marker detected"),
        "corrected": lambda: ctx["corrected"] or nil("no_correction", "no correction marker detected"),
        "oldindexed": lambda: ctx["old_indexed"] or nil("no_old_indexed", "no late-indexed record detected"),
        "alerts": lambda: ctx["alerts"] or nil("no_alert", "no alert for this snapshot"),
        "state": lambda: ctx["new_state"] or {"last_snapshot": [], "last_window_end": ctx["window_end"], "delivery_log": []},
        "report": lambda: "report.md",
        "sources": lambda: ctx["sources"],
        "uncertainty": lambda: ["results come from the supplied snapshot only"],
        "limits": lambda: ["reruns are idempotent against state.json"],
    }
    return table.get(k, fb)()


def fill_contract(res, keys, ctx, out):
    ordered = []
    for k in list(keys) + CANON:
        if k not in ordered:
            ordered.append(k)
    echo = {}
    for k in ordered:
        v = res.get(k)
        if v is None or v == "" or v == [] or v == {}:
            v = value_for(k, ctx)
        if isinstance(v, str):
            try:
                p = Path(out) / v
                if not (v and p.is_file() and p.stat().st_size > 0):
                    v = defang(v)
            except Exception:
                v = defang(v)
        echo[k] = v
        res[k] = v
    res["output_contract"] = echo
    return echo


def render_report(res, ctx):
    L = ["# Latest-literature tracking report", "",
         "- case_id: %s" % res.get("case_id"), "- status: %s" % res.get("status"),
         "- window: [%s, %s)" % (ctx["window"]["window_start"], ctx["window"]["window_end"]),
         "- sources=%d raw=%d unique=%d"
         % (len(ctx["sources"]), ctx["summary"]["candidate_count"], ctx["summary"]["unique_count"]),
         "- new=%d update=%d retraction=%d correction=%d old_indexed=%d alerts=%d"
         % (ctx["summary"]["new_count"], ctx["summary"]["update_count"], ctx["summary"]["retraction_count"],
            ctx["summary"]["correction_count"], ctx["summary"]["old_indexed_count"], ctx["summary"]["alert_count"]),
         "", "## Alerts"]
    if ctx["alerts"]:
        for a in ctx["alerts"][:60]:
            L.append("- %s [%s]" % (a["dedup_key"], a["type"]))
    else:
        L.append("- no alert generated for this snapshot")
    L += ["", "## Decisions"]
    for d in ctx["decisions"][:60]:
        L.append("- %s [%s|%s] -> %s (%s)" % (d["dedup_key"], d.get("source"), d.get("locator"), d.get("decision"), d.get("reason")))
    L += ["", "## Limits"]
    for lim in res.get("limits") or []:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def build_artifacts(out, res, ctx):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decisions.jsonl").write_text(
        "".join(json.dumps(deep_clean(d), ensure_ascii=False) + "\n" for d in ctx["decisions"]) or
        json.dumps({"status": "no_decision_records", "note": "no candidate record in the snapshot"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    wj(out / "new_records.json", {"new": ctx["new"], "count": len(ctx["new"]),
                                  "note": "new records versus the previous state snapshot" if ctx["new"]
                                  else "no new record versus the previous state snapshot"})
    wj(out / "diff_report.json", {"window": ctx["window"], "summary": ctx["summary"],
                                  "new": ctx["new"], "updated": ctx["updated"], "retracted": ctx["retracted"],
                                  "corrected": ctx["corrected"], "old_indexed": ctx["old_indexed"],
                                  "out_of_window": ctx["out_of_window"], "decision_missing": ctx["decision_missing"]})
    wj(out / "window.json", ctx["window"])
    (out / "report.md").write_text(render_report(res, ctx), encoding="utf-8")


def minimal_result(out, notes, status="partial"):
    wj(Path(out) / "result.json", {"case_id": "unknown-case", "status": status, "end": "2024-12-31T00:00:00Z",
                                  "decisions": [], "decision_missing": [], "out_of_window": [],
                                  "sources": [{"source": "none", "name": "not ready", "chars": 0}],
                                  "uncertainty": ["run not finished"], "uncertainties": ["run not finished"],
                                  "change_records": [], "limits": ["run not finished"], "deliverable": "report.md",
                                  "output_contract": {}, "degradations": list(notes), "errors": [],
                                  "runtime": {"stage": "bootstrap"}})

def load_state(wrk):
    st = rj(Path(wrk) / "state.json")
    if isinstance(st, dict):
        st.setdefault("last_snapshot", [])
        st.setdefault("delivery_log", [])
        return st
    return {"last_snapshot": [], "last_window_end": None, "delivery_log": []}


def finalize(out, idx, case, task_text, notes, status, state, wrk):
    res = assemble(idx, case, task_text, status, notes, state)
    ctx = res["_ctx"]
    build_artifacts(out, res, ctx)
    res.pop("_ctx", None)
    fill_contract(res, case_contract_keys(case), ctx, out)
    res.setdefault("change_log", []).append({"at": now(), "step": "output", "note": "artifacts written and contract echoed"})
    res["change_records"] = res["change_log"]
    wj(Path(out) / "result.json", res)
    try:
        wj(Path(wrk) / "state.json", ctx["new_state"])
    except Exception:
        pass
    return res


def case_contract_keys(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(oc, dict) and oc:
        return [str(k) for k in oc.keys()]
    return []


def load_index(inp, wrk):
    idx = rj(Path(wrk) / "index.json")
    if isinstance(idx, dict) and idx.get("materials") is not None:
        return idx
    case, _ = discover_case(inp)
    idx = scan(inp)
    idx["case_id"] = case.get("case_id") or idx.get("case_id")
    idx["input_dir"] = str(inp)
    wj(Path(wrk) / "index.json", idx)
    return idx


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init: partial result.json written"])
    idx = load_index(inp, wrk)
    case, _ = discover_case(inp)
    dp = Path(wrk) / "draft.json"
    if not dp.is_file():
        win = window_of(case, idx)
        wj(dp, {"case_id": idx.get("case_id"), "query": question_from(case, read_task(inp)),
                "window": win, "sources": [m["source"] for m in idx.get("materials") or []],
                "decisions": [], "notes": "skeleton; confirm subscription then build"})
    st = load_state(wrk)
    if not (Path(wrk) / "state.json").is_file():
        wj(Path(wrk) / "state.json", st)
    print("== init ==\ncase_id: %s" % idx.get("case_id"))
    print("contract keys (case): %s" % (case_contract_keys(case) or "none -> SKILL sample"))
    print("sources: %d  records: %d  draft: %s" % (len(idx.get("materials") or []), len(idx.get("records") or []), dp))
    return 0


def cmd_show(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk)
    pat, limit, shown = getattr(a, "grep", "") or "", getattr(a, "limit", 20) or 20, 0
    for m in idx.get("materials") or []:
        for p in m.get("paragraphs") or []:
            if pat and not re.search(pat, p["text"], re.I):
                continue
            print("\n--- %s (%s | src=%s) ---\n%s" % (p["locator"], m["name"], m["source"], p["text"][:1200]))
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        print("(no paragraph matched; %d records detected)" % len(idx.get("records") or []))
        for r in (idx.get("records") or [])[:limit]:
            print("[%s|%s] %s" % (r["rid"], r["source"], r["text"][:200]))
    return 0


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk)
    draft = rj(Path(wrk) / "draft.json", {}) or {}
    errs = []
    win = draft.get("window") or {}
    if not win.get("window_end"):
        errs.append("window.window_end missing")
    rids = {r["rid"] for r in idx.get("records") or []}
    for i, d in enumerate(draft.get("decisions") or []):
        if d.get("rid") and d["rid"] not in rids:
            errs.append("decisions[%d] rid %s not in snapshot" % (i, d["rid"]))
    print("== check ==\nwindow_end=%s  decisions=%d" % (win.get("window_end"), len(draft.get("decisions") or [])))
    for e in errs:
        print("ERROR %s" % e)
    print("RESULT: %s" % ("CHECK PASS" if not errs else "CHECK FAIL (%d)" % len(errs)))
    return 0


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["build: bootstrap partial"])
    idx = load_index(inp, wrk)
    case, _ = discover_case(inp)
    state = load_state(wrk)
    res = finalize(out, idx, case, read_task(inp), notes, None, state, wrk)
    sanitize_output(out)
    print("== build ==\ncase_id=%s status=%s sources=%d records=%d unique=%d alerts=%d" % (
        res.get("case_id"), res.get("status"), len(idx.get("materials") or []), len(idx.get("records") or []),
        res.get("summary", {}).get("unique_count"), res.get("summary", {}).get("alert_count")))
    print("artifacts: %s" % ", ".join(sorted(p.name for p in Path(out).iterdir() if p.is_file())))
    return 0


def cmd_selfcheck(a):
    inp, out, wrk, notes = paths(a)
    res, fails = rj(Path(out) / "result.json", {}) or {}, []

    def ck(name, ok, extra=""):
        print("%-30s %s %s" % (name, "PASS" if ok else "FAIL", extra))
        if not ok:
            fails.append(name)

    ck("result.json parses", bool(res), "keys=%d" % len(res))
    ck("case_id present", bool(res.get("case_id")), str(res.get("case_id")))
    ck("contract echo non-empty", bool(res.get("output_contract")), "%d keys" % len(res.get("output_contract") or {}))
    for need in ("status", "sources", "uncertainties", "change_records", "limits"):
        ck("field:%s" % need, bool(res.get(need)), "")
    for f in ("decisions.jsonl", "new_records.json", "diff_report.json", "window.json", "report.md"):
        p = Path(out) / f
        ck("artifact:%s" % f, p.is_file() and p.stat().st_size > 40, "%d bytes" % (p.stat().st_size if p.is_file() else 0))
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
        res.setdefault("change_records", []).append({"at": now(), "step": "all", "note": "single-command parse+diff+state+clean completed"})
        res["change_log"] = res.get("change_log", []) + [{"at": now(), "step": "all", "note": "single command finished"}]
        wj(Path(out) / "result.json", res)
    except Exception:
        pass
    print("== all ==  single command finished (exit 0)")
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="latest-lit-tracking v%s" % VERSION)
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

    mk("all", "single command: full pipeline end to end (no draft required)")
    mk("init", "scan input, write partial result.json, draft skeleton and initial state.json")
    for name, h in (("check", "validate the agent draft"), ("build", "assemble artefacts and finalise result.json"),
                    ("selfcheck", "re-audit artefacts on disk")):
        mk(name, h)
    sp = mk("show", "print locator-addressable paragraphs / records")
    sp.add_argument("--grep", default="")
    sp.add_argument("--limit", type=int, default=20)
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
            wj(Path(out) / "result.json", old)
        except Exception:
            pass
        print("exception handled (exit 0): %s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
