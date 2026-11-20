#!/usr/bin/env python3
"""desk.py -- shared envelope helpers + check/build stages (stdlib only).

Owns: path resolution, the result.json envelope, contract back-fill, decision
merging, mechanical validation, alert assembly and the build stage that always
finalizes result.json. Imported by main.py; never imports main.
"""
import hashlib
from datetime import datetime, timedelta
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C
import render as R

GEN = R.GEN
CSV_COLS = ["work_key", "op", "title", "doi", "arxiv_id", "venue", "published", "published_prec",
            "indexed", "version", "sources", "n_records", "relevance", "alert", "alert_group",
            "suppress_reason", "evidence_locator", "evidence_quote", "why", "verified"]
ALERT_OPS = ("new", "update", "retract")
FILL = [
    ("retract|withdraw|correction|erratum", "retractions"),
    ("version|revision|update", "updates"),
    ("alert|notif|digest|deliver|remind", "alerts"),
    ("dedup|duplicate|merge|normaliz|canonical", "dedup"),
    ("rank|priorit|order|sort|top", "ranking"),
    ("screen|filter|relevan|inclusion|exclusion|criteri|decision", "screening"),
    ("evidence|quote|locator|provenance|trace|justif|audit", "evidence"),
    ("window|period|time_range|date_range|interval|snapshot", "window"),
    ("query|search|strategy|express|keyword", "query"),
    ("source|database|coverage|provider|crossref|europepmc|publisher", "sources"),
    ("miss|gap|omit|missing|absent|coverage_note", "misses"),
    ("status|progress|state|complete", "status_note"),
    ("uncertain|limitation|risk|caveat|assumption", "uncertainty"),
    ("count|stat|metric|number|summary_count", "counts"),
    ("method|process|workflow|procedur|how|approach", "method"),
    ("artifact|file|deliverable|output_list", "artifacts"),
    ("change|log|history|run|iteration", "changes"),
    ("candidate|paper|record|item|article|document|literature|work", "candidates"),
    ("brief|report|markdown|narrative|summary|conclusion|finding|text", "summary"),
]


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))


def jwrite(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def twrite(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def paths(a):
    return (Path(a.input or os.environ.get("SKILL_INPUT", "/input")),
            Path(a.output or os.environ.get("SKILL_OUTPUT", "/app/output")),
            Path(a.work or os.environ.get("SKILL_WORK", "/app/work")))


def sha(s):
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()


def input_fp(inp, limit=64):
    items = []
    if inp.exists():
        for p in sorted(inp.rglob("*")):
            if p.is_file():
                try:
                    items.append("%s:%s" % (p.relative_to(inp), hashlib.sha256(p.read_bytes()).hexdigest()[:16]))
                except Exception:
                    items.append("%s:unreadable" % p.relative_to(inp))
                if len(items) >= limit:
                    break
    return sha("|".join(items))[:32]


def contract_keys(ct):
    if isinstance(ct, dict):
        return [str(k) for k in ct.keys()]
    if isinstance(ct, list):
        out = []
        for it in ct:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                out.append(str(it.get("name") or it.get("key") or it.get("field") or ""))
        return [k for k in out if k]
    return []


def empty_like(spec):
    if isinstance(spec, list):
        return []
    t = json.dumps(spec, ensure_ascii=False).lower() if spec is not None else ""
    if '"array"' in t or '"list"' in t or t.strip() == "array":
        return []
    if '"object"' in t or '"dict"' in t or t.strip() == "object":
        return {}
    if '"string"' in t:
        return ""
    return None


def partial(case, cid, errs, degr=None):
    ct = case.get("output_contract") if isinstance(case, dict) else None
    res = {}
    for k in contract_keys(ct):
        res[k] = empty_like(ct.get(k) if isinstance(ct, dict) else None)
    res.update(case_id=cid, status="partial", sources=[], uncertainty=[], pending_human=[],
               errors=errs or [], degradations=degr or [], changes=[],
               counts={}, fingerprints={}, runtime=dict(skill=GEN, stage="partial"))
    return res


def load_draft(wk):
    p = wk / "draft.json"
    if not p.exists():
        return {}, "", "missing"
    try:
        d = jread(p)
        if not isinstance(d, dict):
            return {}, str(p), "not_an_object"
        return d, str(p), ""
    except Exception as e:
        return {}, str(p), repr(e)


def sub_of(dr, case):
    s = dr.get("subscription") if isinstance(dr.get("subscription"), dict) else {}
    q = s.get("query") or s.get("search_query") or ""
    if not q and isinstance(case, dict):
        q = str(case.get("query") or case.get("research_question") or case.get("task_instruction") or "")[:400]
    return {"query": q, "sources": s.get("sources") or [], "timezone": s.get("timezone") or "",
            "cadence": s.get("cadence") or s.get("schedule") or "", "notes": s.get("notes") or ""}


def merge_decisions(idx, dr):
    """Join Agent decisions to mechanical works; return final work rows + gaps."""
    works = idx.get("works") or []
    by = {}
    raw = dr.get("decisions") if isinstance(dr.get("decisions"), list) else []
    for d in raw:
        if isinstance(d, dict) and d.get("work_key"):
            by[str(d["work_key"])] = d
    rows, gaps, extra = [], [], []
    for w in works:
        d = by.pop(w["work_key"], None) or {}
        ev = d.get("evidence") if isinstance(d.get("evidence"), dict) else {}
        quote = str(ev.get("quote") or "")
        loc = str(ev.get("locator") or w["rep"]["locator"])
        verified = bool(quote) and quote_hit(idx, loc, quote)
        rows.append({
            "work": w, "work_key": w["work_key"],
            "op": d.get("op") if d.get("op") in C.OPS else w["auto_op"],
            "auto_op": w["auto_op"],
            "relevance": d.get("relevance") if d.get("relevance") in C.RELS else "unreviewed",
            "why": str(d.get("why") or d.get("rationale") or "").strip(),
            "evidence": {"source_id": str(ev.get("source_id") or w["rep"]["source_id"]),
                         "locator": loc, "quote": quote},
            "quote_verified": verified,
            "alert": bool(d.get("alert", w["auto_op"] in ALERT_OPS)),
            "alert_group": str(d.get("alert_group") or ""),
            "suppress_reason": str(d.get("suppress_reason") or ""),
            "reviewed": bool(d),
            "title": w["title"], "doi": w["doi"], "arxiv": w["arxiv"], "venue": w["venue"],
            "published": w["published"], "published_prec": w["published_prec"],
            "published_first": w.get("published_first") or w["published"],
            "indexed_max": w.get("indexed_max") or w["indexed"],
            "indexed": w["indexed"], "version": w["version"], "type": w["type"],
            "sources": sorted({r["source_id"] for r in w["members"]}),
            "n_records": w["n_records"], "duplicates": w["duplicates"],
            "version_chain": w["version_chain"], "change_signals": w["change_signals"],
            "baseline": w["baseline"], "auto_reasons": w["auto_reasons"],
        })
        if not d:
            gaps.append("no draft decision for %s (mechanical op=%s kept)" % (w["work_key"], w["auto_op"]))
        elif d.get("op") not in C.OPS:
            gaps.append("%s: invalid op %r -> mechanical %s kept" % (w["work_key"], d.get("op"), w["auto_op"]))
    for k in by:
        extra.append(str(k))
    return rows, gaps, extra


def counts_of(rows):
    by = {o: sum(1 for r in rows if r["op"] == o) for o in C.OPS}
    recs = sum(r["n_records"] for r in rows)
    dups = recs - len(rows)
    alerted = sum(1 for r in rows if r["alert"])
    c = {"records_total": recs, "works_total": len(rows), "duplicate_records": dups, "alerted": alerted}
    c.update(by)
    c["identity_1"] = recs - len(rows) == dups
    c["identity_2"] = len(rows) == sum(by.values())
    c["identity_3"] = alerted <= by["new"] + by["update"] + by["retract"]
    return c


def quote_hit(idx, loc, quote):
    q = C.norm(quote, True)
    if len(q) < 4:
        return False
    base = str(loc).split(".")[0].strip()
    for r in idx.get("records") or []:
        if r.get("locator") == base or r.get("rid") == base:
            return q in C.norm(r["text"], True) or q in C.norm(r["title"], True)
    return False


def record_by_loc(idx, loc):
    base = str(loc).split(".")[0].strip()
    for r in idx.get("records") or []:
        if r.get("locator") == base:
            return r
    return {}


def build_index_or_fail(a, inp, errs):
    try:
        return discover(inp, "UTC")
    except Exception as e:
        import traceback
        errs.append({"code": "discover_failed", "detail": repr(e), "trace": traceback.format_exc()[-600:]})
        return {"case": {}, "sources": [], "records": [], "works": [], "baseline": [],
                "window": {"start": "", "end": "", "timezone": "UTC", "basis": []},
                "errors": errs, "degradations": [], "seen_n": 0, "retract_n": 0}


def fill_contract(case, base):
    ct = case.get("output_contract") if isinstance(case, dict) else None
    res, miss = {}, []
    for k in contract_keys(ct):
        v = base.get(k)
        if v in (None, "", [], {}):
            v = None
            for pat, alias in FILL:
                if re.search(pat, k.lower()) and base.get(alias) not in (None, "", [], {}):
                    v = base[alias]
                    break
        if v in (None, "", [], {}):
            v = empty_like(ct.get(k) if isinstance(ct, dict) else None)
            miss.append(k)
        res[k] = v
    return res, miss


def slim(idx, cid):
    def w(x):
        y = {k: x.get(k) for k in ("work_key", "keys", "n_records", "title", "doi", "arxiv", "venue",
                                   "published", "published_prec", "published_first", "indexed_max",
                                   "indexed", "version", "type",
                                   "duplicates", "version_chain", "change_signals", "notice_locator",
                                   "in_seen", "retracted", "auto_op", "auto_reasons", "baseline")}
        y["rep"] = {k: (x.get("rep") or {}).get(k) for k in ("locator", "source_id", "doi", "arxiv", "venue",
                                                            "published", "published_prec", "version", "type", "title")}
        y["members"] = [{k: m.get(k) for k in ("locator", "source_id", "doi", "arxiv", "venue", "published",
                                               "version", "type", "title")} for m in x.get("members") or []]
        return y
    return {"case_id": cid, "case_path": idx.get("case_path", ""), "generated": time.strftime("%FT%T"),
            "window": idx.get("window") or {}, "sources": idx.get("sources") or [],
            "works": [w(x) for x in idx.get("works") or []],
            "records": [{k: r.get(k) for k in ("locator", "source_id", "title", "doi", "arxiv",
                                               "published", "indexed", "text")} for r in idx.get("records") or []],
            "baseline_n": len(idx.get("baseline") or []), "seen_n": idx.get("seen_n"),
            "retract_n": idx.get("retract_n"), "errors": idx.get("errors") or [],
            "degradations": idx.get("degradations") or []}


def case_id_of(case, cpath):
    return str(case.get("case_id") or case.get("id") or (cpath.parent.name if cpath else "unknown"))


def load_index(wk, a, inp, errs):
    p = wk / "index.json"
    if p.exists():
        try:
            idx = jread(p)
            if idx.get("works") is not None and idx.get("records") is not None:
                return idx
        except Exception as e:
            errs.append({"code": "index_unreadable", "detail": repr(e)})
    return build_index_or_fail(a, inp, errs)


# ---------------------------------------------------------------- discovery
def find_case(inp, errs):
    if not inp.exists():
        errs.append({"code": "input_missing", "detail": "input dir not found: %s" % inp})
        return {}, None
    cands = sorted(inp.rglob("case.json"))
    if not cands:
        cands = sorted(inp.rglob("*.json"))
    for p in cands:
        try:
            o = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception as e:
            errs.append({"code": "case_json_invalid", "detail": "%s: %r" % (p.name, e)})
            continue
        if isinstance(o, dict) and (o.get("output_contract") or o.get("case_id") or o.get("task_instruction")):
            return o, p
    return {}, None


WSTART = re.compile(r"(window_?start|^start$|date_?from|^from$|^since$|start_?date|period_?start|^begin$|after)")
WEND = re.compile(r"(window_?end|^end$|date_?to|^to$|^until$|end_?date|period_?end|^cutoff$|before)")


def case_hints(case):
    """-> (start cands, end cands, tz name, query-ish text). All best-effort."""
    st, en, tz, txt = [], [], "", []
    def walk(o, depth=0):
        if depth > 4:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).lower()
                if isinstance(v, str):
                    d, _ = C.parse_date(v)
                    if d:
                        if WSTART.search(kl) and "watermark" not in kl:
                            st.append((d, "case:%s" % k))
                        elif WEND.search(kl):
                            en.append((d, "case:%s" % k))
                    if "timezone" in kl or kl in ("tz", "zone"):
                        tz = v
                    if kl in ("query", "search_query", "task_instruction", "question",
                              "research_question", "topic", "title"):
                        txt.append(v[:600])
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o[:20]:
                walk(v, depth + 1)
    walk(case)
    return st, en, tz, " ".join(txt)


def text_dates(txt):
    out = []
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", txt or ""):
        out.append(m.group(0))
    return sorted(set(out))


def signature(r):
    return (r.get("doi", ""), C.norm(r.get("venue", "")).lower(),
            C.version_num(r.get("version")), r.get("published", ""), r.get("type", ""))


SRC_TAG = re.compile(r"^(s\d+|crossref|europepmc|europe pmc|pubmed|ppr|med|arxiv|publisher|api)$", re.I)


def diff_signal(a, b):
    sa, sb = signature(a), signature(b)
    names = ("doi", "venue", "version", "published", "type")
    out = [names[i] + "_changed" for i in range(5)
           if sa[i] and sb[i] and sa[i] != sb[i]
           and not (names[i] == "venue" and (SRC_TAG.match(sa[i]) or SRC_TAG.match(sb[i])))]
    return out


def discover(inp, tzname="UTC"):
    """Full deterministic pass. Returns the index dict used by show/check/build."""
    errs, degr = [], []
    case, cpath = find_case(inp, errs)
    st, en, tz_case, txt = case_hints(case)
    tzname = tz_case or tzname or "UTC"
    off = C.tz_offset(tzname)
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    plans = []
    for p in files:
        nm = p.name.lower()
        rel = str(p.relative_to(inp))
        if nm in C.SKIP_NAMES or nm == "case.json":
            continue
        ext = p.suffix.lower()
        if ext in C.FULL_EXT:
            plans.append((p, rel, "fulltext", "binary"))
            continue
        if ext in C.REC_EXT:
            role = "state" if C.STATE_PAT.search(rel) else ("retract" if C.RETRACT_PAT.search(rel) else "records")
            if C.VERSION_PAT.search(rel) and role == "records":
                role = "version"
            plans.append((p, rel, role, "table"))
            continue
        if ext in C.TEXT_EXT or ext == "":
            plans.append((p, rel, "note", "text"))
            continue
        plans.append((p, rel, "unknown", C.sniff(p)))
    plans.sort(key=lambda x: ({"state": 0, "retract": 1, "version": 2, "records": 3}.get(x[2], 4), x[1]))

    sources, records, baseline, seen, retr_keys, wm = [], [], [], set(), set(), []
    for i, (p, rel, role, kind) in enumerate(plans, 1):
        sid = "S%d" % i
        src = {"source_id": sid, "file": rel, "role": role, "kind": kind,
               "n_records": 0, "status": "ok", "note": ""}
        objs = []
        if role in ("fulltext", "unknown", "note"):
            src["note"] = "registered only; content not parsed for bibliographic decisions"
            src["status"] = "not_parsed"
            sources.append(src)
            degr.append("%s (%s): %s kept as %s, not a record source" % (rel, sid, role, kind))
            continue
        try:
            if p.suffix.lower() in (".jsonl", ".ndjson"):
                objs = C.read_jsonl(p)
            elif p.suffix.lower() in (".csv", ".tsv"):
                objs = C.read_csv(p)
            else:
                raw = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
                objs = raw
        except Exception as e:
            src["status"] = "failed"
            src["note"] = "parse error: %r" % (e,)
            errs.append({"code": "source_unreadable", "detail": "%s: %r" % (rel, e)})
            sources.append(src)
            continue
        recs = C.records_from_obj(objs, sid) if objs not in ([], {}, None) else []
        src["n_records"] = len(recs)
        if isinstance(objs, (dict, list)):
            C.collect_ids(objs, seen, wm)
        if role == "state":
            baseline += recs
            if recs:
                src["note"] = "%d baseline record(s) treated as the previous snapshot" % len(recs)
            elif not src["note"]:
                src["note"] = "identifier set harvested; no per-record baseline"
            if not recs and not seen:
                src["status"] = "empty"
        elif role in ("retract", "version"):
            for r in recs:
                for k in ("doi:" + r["doi"] if r["doi"] else "",
                          "arxiv:" + r["arxiv"] if r["arxiv"] else "",
                          "title:" + r["title_fp"] if r["title_fp"] else ""):
                    if k:
                        retr_keys.add(k)
            src["note"] = "%d notice/version record(s) indexed as change evidence" % len(recs)
        else:
            records += recs
            for r in recs:
                if any(t in (r["type"] or "") for t in C.RETRACT_TYPES):
                    for m in re.finditer(r"10\.\d{4,9}/[^\s\"',;)\]]+", r["update_to"] or ""):
                        d = C.norm_doi(m.group(0))
                        if d:
                            retr_keys.add("doi:" + d)
            if not recs:
                src["status"] = "empty"
                degr.append("%s (%s): parsed but no bibliographic record recognised" % (rel, sid))
        sources.append(src)

    blob = txt + " " + " ".join((c.get("task_instruction") or "") if isinstance(c, dict) else ""
                                for c in (case.get("materials") or []) if isinstance(c, dict))
    tdates = text_dates(blob)
    if len(tdates) >= 2:
        st = st + [(tdates[0], "task-text")]
        en = en + [(tdates[-1], "task-text")]
    works = C.group_works(records, seen, retr_keys)
    for w in works:
        base = next((b for b in baseline if ({"doi:" + b["doi"] if b["doi"] else "",
                                              "arxiv:" + b["arxiv"] if b["arxiv"] else "",
                                              "title:" + b["title_fp"] if b["title_fp"] else ""}) & set(w["keys"])), None)
        w["baseline"] = {k: base.get(k) for k in ("locator", "doi", "venue", "published", "version", "type")} if base else None
        if base:
            extra = [s for s in diff_signal(base, w["rep"]) if s not in w["change_signals"]]
            w["change_signals"] += extra
    # window
    wm_dates = sorted({d for d, _ in wm if d}) if wm else []
    start_c, start_src = "", []
    for d, s in st:
        start_c, start_src = max(start_c, d), start_src + ["%s=%s" % (s, d)]
    if wm_dates:
        if wm_dates[-1] > start_c:
            start_c = wm_dates[-1]
        start_src.append("state:%s" % ",".join(wm_dates))
    end_c, end_src = "", []
    for d, s in en:
        end_c, end_src = max(end_c, d), end_src + ["%s=%s" % (s, d)]
    pubs = sorted({r["published"] for r in records if r["published"]})
    if not start_c and pubs:
        start_c = pubs[0]
        start_src.append("earliest published in snapshot")
    if not end_c:
        late = sorted({d for d in [r["published"] for r in records] + [r["indexed"] for r in records] if d})
        if late:
            end_c = (datetime.fromisoformat(C.dkey(late[-1])) + timedelta(days=1)).date().isoformat()
            end_src.append("latest date in snapshot +1d")
    win = {"start": start_c, "end": end_c, "timezone": tzname,
           "basis": start_src + end_src, "source_start": start_src, "source_end": end_src}
    for w in works:
        op, why = C.classify(w, win)
        w["auto_op"], w["auto_reasons"] = op, why
    return {"case": case, "case_path": str(cpath or ""), "sources": sources, "records": records,
            "baseline": baseline, "works": works, "window": win, "seen_n": len(seen),
            "retract_n": len(retr_keys), "errors": errs, "degradations": degr,
            "input_dir": str(inp)}


def validate(idx, rows, dr, gaps, extra):
    errs, warns = [], []
    win = idx.get("window") or {}
    dw = dr.get("window") if isinstance(dr.get("window"), dict) else {}
    s, e = str(dw.get("start") or win.get("start") or ""), str(dw.get("end") or win.get("end") or "")
    if not s or not e:
        errs.append({"code": "window_missing", "where": "window", "detail": "start/end empty; cannot prove the window"})
    elif C.dkey(s) >= C.dkey(e):
        errs.append({"code": "window_invalid", "where": "window", "detail": "start %s >= end %s" % (s, e)})
    if not dr:
        errs.append({"code": "draft_missing", "where": "draft.json",
                     "detail": "no draft: every decision is still mechanical (relevance=unreviewed)"})
    if not (dr.get("decisions") if isinstance(dr.get("decisions"), list) else []):
        errs.append({"code": "no_decisions", "where": "decisions", "detail": "draft has no decisions[] entries"})
    for g in gaps:
        errs.append({"code": "decision_missing", "where": "decisions", "detail": g})
    for k in extra:
        errs.append({"code": "unknown_work_key", "where": "decisions", "detail": "%s is not in the snapshot" % k})
    groups = {str(g.get("group_id")): g for g in (dr.get("alert_groups") or []) if isinstance(g, dict)}
    for r in rows:
        wk = r["work_key"]
        if r["op"] not in C.OPS:
            errs.append({"code": "invalid_op", "where": wk, "detail": repr(r["op"])})
        if r["relevance"] == "unreviewed":
            warns.append({"code": "relevance_unreviewed", "where": wk, "detail": "no relevance judgement written"})
        if not r["why"]:
            warns.append({"code": "why_missing", "where": wk, "detail": "no screening rationale written"})
        if not r["evidence"]["quote"]:
            warns.append({"code": "quote_missing", "where": wk, "detail": "no verbatim quote for this decision"})
        elif not r["quote_verified"]:
            errs.append({"code": "quote_not_found", "where": wk,
                         "detail": "quote not found verbatim at %s" % r["evidence"]["locator"]})
        if r["op"] in ALERT_OPS and not r["alert"] and not r["suppress_reason"]:
            errs.append({"code": "suppress_unexplained", "where": wk,
                         "detail": "%s not alerted but no suppress_reason" % r["op"]})
        if r["alert_group"] and groups and r["alert_group"] not in groups:
            warns.append({"code": "alert_group_unknown", "where": wk, "detail": r["alert_group"]})
    cn = counts_of(rows)
    for k in ("identity_1", "identity_2", "identity_3"):
        if not cn[k]:
            errs.append({"code": "counts_identity_failed", "where": "counts", "detail": k})
    reviewed = sum(1 for r in rows if r["reviewed"])
    hit = sum(1 for r in rows if r["quote_verified"])
    quoted = sum(1 for r in rows if r["evidence"]["quote"])
    return {"ok": not errs, "errors": errs, "warnings": warns,
            "counts": cn, "quote_hit_rate": round(hit / quoted, 3) if quoted else 0.0,
            "reviewed": reviewed, "works": len(rows),
            "coverage": {"decisions": reviewed, "needs_decision": len(rows),
                         "ratio": round(reviewed / len(rows), 3) if rows else 0.0}}


def cmd_check(a):
    inp, out, wk = paths(a)
    errs = []
    idx = load_index(wk, a, inp, errs)
    dr, dsrc, derr = load_draft(wk)
    if derr and derr != "missing":
        errs.append({"code": "draft_unreadable", "where": dsrc, "detail": derr})
    rows, gaps, extra = merge_decisions(idx, dr)
    rep = validate(idx, rows, dr, gaps, extra)
    rep["errors"] = errs + rep["errors"]
    rep["ok"] = not rep["errors"]
    print(json.dumps({k: rep[k] for k in ("ok", "counts", "quote_hit_rate", "reviewed", "coverage")},
                     ensure_ascii=False, indent=1))
    for x in rep["errors"][:12]:
        print("FIX [%s] %s :: %s" % (x["code"], x["where"], x["detail"][:160]))
    for x in rep["warnings"][:8]:
        print("WARN [%s] %s :: %s" % (x["code"], x["where"], x["detail"][:120]))
    print("errors=%d warnings=%d works=%d reviewed=%d quote_hit_rate=%s" % (
        len(rep["errors"]), len(rep["warnings"]), len(rows), rep["reviewed"], rep["quote_hit_rate"]))
    return 0


def assemble_alerts(rows, dr, degr):
    groups = [dict(g) for g in (dr.get("alert_groups") or []) if isinstance(g, dict)]
    if not groups and any(r["alert"] for r in rows):
        for op, title, dl in (("retract", "撤稿/撤回（立即处理）", "immediate"),
                              ("update", "版本更新与更正", "digest"),
                              ("new", "窗口内新增发现", "digest")):
            mem = [r["work_key"] for r in rows if r["op"] == op and r["alert"]]
            if mem:
                groups.append({"group_id": "G%d" % (len(groups) + 1), "title": title, "members": mem,
                               "delivery": dl, "merge_reason": "auto: grouped by op"})
        if groups:
            degr.append("alert_groups absent in draft: grouped mechanically by op")
    for i, g in enumerate(groups, 1):
        g.setdefault("group_id", "G%d" % i)
        g["members"] = [m for m in (g.get("members") or []) if isinstance(m, str)]
    gid = {m: g["group_id"] for g in groups for m in g["members"]}
    for r in rows:
        if r["alert"] and not r["alert_group"]:
            r["alert_group"] = gid.get(r["work_key"], "")
    orphan = [r for r in rows if r["alert"] and not r["alert_group"]]
    for r in orphan:
        tgt = next((g for g in groups if g.get("title") and r["op"] in ("new", "update", "retract")
                    and ({"new": "新增", "update": "更新", "retract": "撤稿"}[r["op"]] in g["title"])), None)
        if tgt is None:
            tgt = {"group_id": "G%d" % (len(groups) + 1), "title": "窗口内新增发现", "members": [],
                   "delivery": "digest", "merge_reason": "auto: unassigned alert"}
            groups.append(tgt)
        tgt["members"].append(r["work_key"])
        r["alert_group"] = tgt["group_id"]
    for r in rows:
        if r["op"] in ALERT_OPS and not r["alert"] and not r["suppress_reason"]:
            r["suppress_reason"] = "not assigned to any alert group (mechanical suppression)"
    return groups
