#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search-coverage-gap-auditor (search-07) - single-file CLI.

Frozen reference set -> graded record matching -> coverage/miss rate over an explicit
denominator policy -> per-miss attribution with a locator -> targeted supplement with
marginal yield and a stop rule -> recomputable audit trail.
Commands: all(default) / init / show / check / build / selfcheck / compare. Always exit 0
(only an argparse usage error returns 2). Pure stdlib, offline, deterministic.
"""
import argparse
import csv
import difflib
import hashlib
import io
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"
STATUSES = ("ok", "partial", "insufficient_evidence", "input_error")
SKIP = {"case.json", "task.md"}
CJK = "一-鿿"
STOP = {"and", "the", "for", "with", "from", "into", "over", "that", "this", "are", "was", "its",
        "our", "you", "not", "but", "can", "all", "any", "how", "why", "who", "which", "study",
        "studies", "review", "effect", "effects", "using", "based", "in", "on", "of", "to", "a"}
REF_HINT = re.compile(r"reference|known|seed|gold|anchor|include|expert|do_not_miss|refset|参考|专家|纳入", re.I)
QUERY_KEY = ("query", "q", "query_string", "term", "expression", "strategy", "检索式")
TITLE_KEY = ("title", "name", "article_title", "ti", "标题")
DOI_KEY = ("doi", "identifier", "digital_object_identifier")
PMID_KEY = ("pmid", "pmcid", "uid")
YEAR_KEY = ("year", "pub_year", "publication_year", "issued", "py", "年份")
AUTH_KEY = ("authors", "author", "first_author", "creator", "作者")
VENUE_KEY = ("venue", "journal", "container_title", "source", "publication", "期刊")
FIELD_KEY = ("field", "fields", "search_field", "字段")
WIN_KEY = ("date_from", "date_to", "start", "end", "window", "time_window", "时间窗")
SRC_KEY = ("source", "database", "provider", "来源", "库")
ABS_KEY = ("abstract", "summary", "description")
CATEGORIES = ("query_term_missing", "field_too_narrow", "time_window_cut",
              "source_not_indexed", "ref_record_anomaly", "ranking_depth")
WHY = {"query_term_missing": "fixable_by_query", "field_too_narrow": "fixable_by_query",
       "time_window_cut": "fixable_by_query", "ranking_depth": "fixable_by_query",
       "source_not_indexed": "needs_new_source", "ref_record_anomaly": "data_defect"}
CANON = ["case", "parse", "read", "discover", "queries", "gap", "draft", "quote",
         "paths", "products", "init", "show", "check", "build", "selfcheck"]
ALIAS = {}
for _g, _f in [
    ("case caseid casename search_case", "case"),
    ("parse parsed parse_summary", "parse"), ("read reading read_summary", "read"),
    ("discover discovery discover_summary", "discover"),
    ("queries query queryplan searchplan querylog", "queries"),
    ("gap gaps gap_summary miss misses omissions missed", "gap"),
    ("draft draftjson workdraft", "draft"),
    ("quote quotes evidence evidence_map verbatim", "quote"),
    ("paths pathsmap", "paths"), ("products products deliverables outputs", "products"),
    ("init initialize", "init"), ("show display", "show"), ("check verify", "check"),
    ("build finalize", "build"), ("selfcheck selftest", "selfcheck"),
    ("status state runstatus", "status"), ("coverage coveragereport recall", "coverage"),
    ("supplement supplemental supplementplan", "supplement"), ("sources provenance", "sources"),
    ("uncertainty uncertainties", "uncertainty"),
    ("change_records changes changelog", "change_records"), ("report summary narrative", "report"),
    ("reference_set refset known_relevant seed_papers", "reference_set"),
    ("hit_ledger hitledger ledger", "hit_ledger"), ("params parameters", "params")]:
    for _n in _g.split():
        ALIAS[_n] = _f
NOTE = "recorded for this run; see the delivered audit artifacts"
PLACE = re.compile(r"\[\s*待写\s*\]|待写|待补充|待填写|TBD|TODO|FIXME|NOT_EXTRACTED", re.I)
EXT = (".md", ".json", ".csv", ".tsv", ".jsonl")


def nkey(v):
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_json(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:
        return None, str(exc)[:200]


def strip_none(o):
    if isinstance(o, dict):
        return {k: strip_none(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [strip_none(x) for x in o if x is not None]
    return o


def _write_text(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)


def dump_json(p, obj):
    _write_text(p, json.dumps(strip_none(obj), ensure_ascii=False, indent=2))


def dump_text(p, s):
    _write_text(p, s)


def sha12(s):
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def ntokens(s, cap=60):
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}|[%s]{2,}" % CJK, str(s or "")):
        wl = w.lower()
        if wl not in out and wl not in STOP:
            out.append(wl)
        if len(out) >= cap:
            break
    return out


def clean_doi(v):
    s = re.sub(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", "", str(v or "").strip(), flags=re.I)
    return s.strip().rstrip(".").lower()


def norm_title(s):
    s = re.sub(r"^retracted:\s*", "", str(s or "").lower())
    return re.sub(r"[^a-z0-9%s]+" % CJK, " ", s).strip()


def sim(a, b):
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()


def pick(d, names):
    if not isinstance(d, dict):
        return None
    low = {nkey(k): v for k, v in d.items()}
    for n in names:
        v = low.get(nkey(n))
        if isinstance(v, (str, int, float)) and str(v).strip():
            return v
        if isinstance(v, list) and v:
            return v
    return None


def year_of(r):
    m = re.search(r"(19|20)\d{2}", str(pick(r, YEAR_KEY) or ""))
    return int(m.group(0)) if m else 0


def surname(a):
    parts = [p for p in norm(a).lower().replace(",", " ").split() if p]
    return parts[0] if parts else ""


def iter_objs(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from iter_objs(v)
    elif isinstance(o, list):
        for v in o:
            yield from iter_objs(v)


def as_bib(r):
    if not isinstance(r, dict):
        return None
    t, d, pm = norm(pick(r, TITLE_KEY) or ""), clean_doi(pick(r, DOI_KEY) or ""), norm(pick(r, PMID_KEY) or "")
    au = pick(r, AUTH_KEY)
    au = "; ".join(norm(x) for x in au[:8]) if isinstance(au, list) else norm(au or "")
    if (t or d or pm) and (d or pm or (t and (year_of(r) or au))):
        ab = pick(r, ABS_KEY)
        return {"title": t, "doi": d, "pmid": pm, "year": year_of(r), "author": au,
                "venue": norm(pick(r, VENUE_KEY) or ""), "abstract": norm(ab or "")}
    return None


def as_query(r):
    if not isinstance(r, dict):
        return None
    q = pick(r, QUERY_KEY)
    if isinstance(q, (str, int)) and str(q).strip():
        return {"query": norm(q), "field": norm(pick(r, FIELD_KEY) or ""),
                "window": norm(pick(r, WIN_KEY) or ""), "source": norm(pick(r, SRC_KEY) or "")}
    return None


def parse_file(path):
    ext, text = path.suffix.lower(), read_text(path)
    recs, qs, lines = [], [], []
    if ext == ".json":
        obj, err = load_json(path)
        if err is not None:
            return [], [], [], "invalid-json"
        for o in iter_objs(obj):
            b, q = as_bib(o), as_query(o)
            if b:
                recs.append(b)
            if q:
                qs.append(q)
    elif ext == ".jsonl":
        for ln in text.splitlines():
            if ln.strip():
                try:
                    for o in iter_objs(json.loads(ln)):
                        b, q = as_bib(o), as_query(o)
                        if b:
                            recs.append(b)
                        if q:
                            qs.append(q)
                except Exception:
                    continue
    elif ext in (".csv", ".tsv"):
        try:
            for r in csv.DictReader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else ","):
                b, q = as_bib(r), as_query(r)
                if b:
                    recs.append(b)
                if q:
                    qs.append(q)
        except Exception:
            return [], [], [], "csv-error"
    else:
        for ln in text.splitlines():
            s = norm(re.sub(r"^[#>*\-\s]+", "", ln))
            if len(s) >= 24 and not PLACE.search(s):
                lines.append(s)
    return recs, qs, lines, ("parsed" if (recs or qs or lines) else "empty-file")


def build_context(inp):
    inp = Path(inp)
    case, case_err = {}, None
    if (inp / "case.json").is_file():
        obj, err = load_json(inp / "case.json")
        case, case_err = (obj if isinstance(obj, dict) else {}), (err or (None if isinstance(obj, dict) else "case.json is not an object"))
    task = read_text(inp / "task.md")
    files = [p for p in sorted(inp.rglob("*")) if p.is_file() and p.name not in SKIP] if inp.is_dir() else []
    sources, pool, refs, queries, lines, deg = [], [], [], [], [], []
    if case_err:
        deg.append({"stage": "case", "detail": str(case_err)})
    for i, p in enumerate(files, 1):
        mid, rel, text = "src-%02d" % i, p.relative_to(inp).as_posix(), read_text(p)
        recs, qs, lns, st = parse_file(p)
        sources.append({"id": mid, "name": rel, "kind": p.suffix.lower().lstrip(".") or "txt",
                        "parse_status": st, "bytes": p.stat().st_size, "sha1": sha12(text),
                        "records": len(recs), "queries": len(qs), "lines": len(lns)})
        isref = bool(REF_HINT.search(rel))
        for j, b in enumerate(recs, 1):
            b = dict(b, _sid=mid, _loc="%s#%d" % (mid, j), _file=rel)
            (refs if isref else pool).append(b)
        for j, l in enumerate(lns, 1):
            lines.append({"source_id": mid, "locator": "%s#L%d" % (mid, j), "text": l})
        for q in qs:
            queries.append(dict(q, _sid=mid))
        if st != "parsed":
            deg.append({"stage": "parse", "detail": "%s had no parseable record, query or line" % rel})
    for key in ("reference_set", "known_relevant", "seed_papers", "must_include"):
        v = case.get(key)
        if isinstance(v, list):
            for item in v:
                b = as_bib(item) if isinstance(item, dict) else None
                if b:
                    refs.append(dict(b, _sid="case.json", _loc="case.json#%s" % key, _file="case.json"))
    cid = norm(pick(case, ("case_id", "caseid", "id", "name")) or inp.name or "unknown-case")
    rq = norm(pick(case, ("research_question", "question", "topic", "task_instruction")) or "")
    if not rq:
        rq = next((norm(l.lstrip("#*> ").strip()) for l in task.splitlines()
                   if len(norm(l.lstrip("#*> ").strip())) >= 8), "")
    return {"inp": inp, "case": case, "case_id": cid, "rq": rq, "files": files, "sources": sources,
            "refs": refs, "pool": pool, "queries": queries, "lines": lines, "degradations": deg}


def freeze_refset(ctx):
    seen_doi, seen_title, out = {}, {}, []
    for i, r in enumerate(ctx["refs"], 1):
        rid = "R-%03d" % i
        e = {"ref_id": rid, "title": r["title"], "doi": r["doi"], "year": r["year"],
             "author": r["author"], "venue": r["venue"], "usable": True,
             "usability_reason": "usable", "dup_of": None, "locator": r["_loc"], "source": r["_sid"], "_b": r}
        blob = (r["title"] + " " + r["author"] + " " + r["venue"]).lower()
        if "retract" in blob or "withdraw" in blob:
            e["usable"], e["usability_reason"] = False, "retracted"
        elif not r["title"] or not r["year"]:
            e["usable"], e["usability_reason"] = False, "meta_incomplete"
        dk = r["doi"] or ("t:" + norm_title(r["title"])[:80])
        if dk and dk in seen_doi:
            e["dup_of"] = seen_doi[dk]
        elif dk:
            seen_doi[dk] = rid
        tk = norm_title(r["title"])
        if tk and tk in seen_title and not e["dup_of"]:
            e["dup_of"] = seen_title[tk]
        elif tk:
            seen_title.setdefault(tk, rid)
        out.append(e)
    fp = sha12("|".join("%s|%s|%s" % (e["ref_id"], e["doi"], norm_title(e["title"])) for e in out))
    return out, fp


def match_one(e, pool):
    r = e["_b"]
    for j, p in enumerate(pool, 1):
        if r["doi"] and p["doi"] and r["doi"] == p["doi"]:
            return p, "id_doi", True, "high", j
        if r["pmid"] and p["pmid"] and r["pmid"] == p["pmid"]:
            return p, "id_pmid", True, "high", j
    for j, p in enumerate(pool, 1):
        ts = sim(r["title"], p["title"])
        if ts >= 0.92:
            au = bool(surname(r["author"])) and surname(r["author"]) == surname(p["author"])
            yr = bool(r["year"]) and bool(p["year"]) and abs(r["year"] - p["year"]) <= 1
            if au or yr:
                return p, "bib_title_author_year", True, ("high" if ts >= 0.97 else "medium"), j
    best, bj = 0.0, None
    for j, p in enumerate(pool, 1):
        ts = sim(r["title"], p["title"])
        if ts > best:
            best, bj = ts, j
    if 0.80 <= best < 0.92 and bj:
        return pool[bj - 1], "bib_borderline", True, "low", bj
    return None, None, False, "high", None


def scope_of(frozen, policy):
    members = [e for e in frozen if e["dup_of"] is None]
    if policy == "all":
        return list(frozen)
    if policy == "dedup_only":
        return members
    return [e for e in members if e["usable"]]


def attribute(e, pool, queries):
    r = e["_b"]
    if not r["title"] or not r["year"] or not r["doi"]:
        return "ref_record_anomaly", "entry lacks a title, a year or an identifier"
    qtext = " ".join(q["query"].lower() for q in queries)
    disc = [t for t in ntokens(r["title"], 10) if t not in STOP]
    missing = [t for t in disc if t not in qtext]
    if queries and missing and len(missing) >= max(1, len(disc) // 2):
        return "query_term_missing", "discriminating term(s) absent from every query: " + ", ".join(missing[:4])
    if [q for q in queries if q["field"] and re.search(r"\bti\b|title|题名", q["field"], re.I)
            and not re.search(r"ab|abstract|all|tiab|摘要", q["field"], re.I)]:
        return "field_too_narrow", "a query restricted the field to title only"
    win = next((q for q in queries if re.search(r"(19|20)\d{2}", q["window"] or "")), None)
    if win and r["year"]:
        yrs = [int(y) for y in re.findall(r"(?:19|20)\d{2}", win["window"])]
        if yrs and not (min(yrs) <= r["year"] <= max(yrs)):
            return "time_window_cut", "reference year %d falls outside the query window %s" % (r["year"], win["window"])
    near = any(sim(r["title"], p["title"]) >= 0.80 for p in pool)
    srcs = {q["source"].lower() for q in queries if q["source"]}
    if srcs and r["venue"] and not any(s in r["venue"].lower() for s in srcs) and not near:
        return "source_not_indexed", "no declared source and no local record carries this item"
    if near:
        return "ranking_depth", "a similar record exists in the pool but not in the returned set"
    return "query_term_missing", "no query term reaches this title within the snapshot"


def plan_supplement(frozen, misses, pool):
    rows, hit_ids, by = [], set(), {}
    for m in misses:
        by.setdefault(m["category"], []).append(m)
    qi = 0
    for cat in ("query_term_missing", "field_too_narrow", "time_window_cut", "ranking_depth", "source_not_indexed"):
        grp = by.get(cat)
        if not grp:
            continue
        qi += 1
        terms = []
        for m in grp:
            terms += [t for t in ntokens(m["title"], 6) if t not in terms][:3]
        # only a ranking_depth miss is recoverable from the supplied snapshot (the record is
        # present in the pool but was not returned at the initial depth); every other class
        # needs a retrieval the snapshot does not carry, so no local hit is claimed.
        new_hits = ([m["ref_id"] for m in grp if any(sim(m["title"], p["title"]) >= 0.80 for p in pool)]
                    if cat == "ranking_depth" else [])
        new_records = sum(1 for p in pool if any(sim(p["title"], m["title"]) >= 0.80 for m in grp))
        rows.append({"query_id": "S-%02d" % qi, "target_gap": cat,
                     "planned_query": " OR ".join('"%s"' % t for t in terms[:6]) or '"broaden"',
                     "fields": "title/abstract", "window": "auto",
                     "actual_new_hits": len(new_hits), "new_records": new_records,
                     "hit_ref_ids": new_hits, "rationale": "targets the %s gap class" % cat,
                     "no_gain": (not new_hits and not new_records)})
        hit_ids |= set(new_hits)
    return rows, hit_ids


def build_payload(ctx):
    policy = "dedup_exclude_unavailable"
    frozen, fp = freeze_refset(ctx)
    pool, queries = ctx["pool"], ctx["queries"]
    for e in frozen:
        p, rule, hit, cert, j = match_one(e, pool)
        e["hit_status"] = "hit" if (hit and cert != "low") else ("needs_review" if hit else "miss")
        e["match_rule"] = rule if hit else ""
        e["certainty"] = cert
        e["matched_id"] = ("P-%04d" % j) if (hit and j) else ""
        e["needs_human"] = cert == "low"
        e["evidence_quote"] = p["title"] if (hit and p) else ""
        e["evidence_locator"] = p["_loc"] if (hit and p) else e["locator"]
    scope = scope_of(frozen, policy)
    ids = [e["ref_id"] for e in scope]
    hits = [e for e in scope if e["hit_status"] == "hit"]
    misses = [e for e in scope if e["hit_status"] != "hit"]
    cov = round(len(hits) / len(scope), 4) if scope else 0.0
    att = []
    for m in misses:
        cat, why = attribute(m, pool, queries)
        att.append({"ref_id": m["ref_id"], "title": m["title"], "year": m["year"], "category": cat,
                    "why": WHY.get(cat, "data_defect"), "verdict": why, "evidence": m["evidence_locator"]})
    supp, new_ids = plan_supplement(frozen, att, pool)
    final = round((len(hits) + len(new_ids)) / len(scope), 4) if scope else 0.0
    cats = {c: [a["ref_id"] for a in att if a["category"] == c] for c in CATEGORIES}
    status = "input_error" if not ctx["files"] else (
        "ok" if (scope and cov >= 0.5 and not misses) else ("partial" if scope else "insufficient_evidence"))
    unc = []
    if not queries:
        unc.append("no query log was recognised, so miss attribution could not point to a query")
    if pool and not queries:
        unc.append("a retrieved record pool exists but no query strings were available")
    unc = unc or ["scope is limited to the supplied snapshot; no remote coverage is claimed"]
    return {"policy": policy, "frozen": frozen, "fingerprint": fp, "scope_ids": ids, "hits": hits,
            "misses": misses, "coverage": cov, "miss_rate": round(1 - cov, 4) if scope else 0.0,
            "attributed": att, "supplement": supp, "new_ids": sorted(new_ids), "final_coverage": final,
            "gap_summary": {"denominator": len(scope), "hits": len(hits), "misses": len(misses),
                            "coverage": cov, "miss_rate": round(1 - cov, 4) if scope else 0.0,
                            "categories": {k: v for k, v in cats.items() if v}},
            "changes": [{"step": "freeze", "detail": "%d reference(s) frozen; fingerprint %s" % (len(frozen), fp)},
                        {"step": "match", "detail": "%d hit / %d miss within the %s scope" % (len(hits), len(misses), policy)},
                        {"step": "supplement", "detail": "%d supplemental quer(y/ies) added %d new hit(s)" % (len(supp), len(new_ids))}],
            "uncertainty": unc, "status": status}


