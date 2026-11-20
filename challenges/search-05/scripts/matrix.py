#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""federated-search-reconcile :: matrix layer.

Query matrix, evidence-voting deduplication, cluster merge with declared field
precedence, database-by-field coverage gap matrix, the five-piece renderer and
the output_contract semantic filler. Pure functions over the index built by
ledger.py; no I/O beyond the paths handed in. Stdlib only, offline.
"""
import difflib, json, re
from pathlib import Path

import ledger as L

V = "1.0.0"
COV = ("title", "authors", "year", "venue", "doi", "abstract")
PRIO = {"elsevier": 9, "springer": 9, "wiley": 9, "taylorfrancis": 9, "sage": 9, "ieee": 9,
        "acm": 9, "plos": 9, "mdpi": 9, "frontiers": 9, "pnas": 9, "bmj": 9, "jama": 9,
        "nejm": 9, "cell": 9, "science": 9, "publisher": 9, "crossref": 8, "pubmed": 7,
        "europepmc": 7, "scopus": 6, "webofscience": 6, "openalex": 5, "semanticscholar": 4,
        "doaj": 4, "jstage": 4, "cnki": 4, "wanfang": 4, "arxiv": 3, "lens": 3,
        "dimensions": 3, "core": 3, "openaire": 3, "scholar": 2}
STOP = {"a", "an", "the", "of", "on", "in", "for", "and", "to", "with", "by", "from", "at",
        "de", "la", "le", "der", "die", "das", "und", "et", "al", "into", "via", "its", "is"}


def prio(db):
    return PRIO.get(db or "", 2)


# ------------------------------------------------------------------ text match
def tnorm(s):
    s = L.strip_tags(s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", s)
    toks = [t for t in s.split() if t and t not in STOP]
    return " ".join(toks)


def toks(s):
    return set(tnorm(s).split())


def sim(a, b):
    na, nb = tnorm(a), tnorm(b)
    if not na or not nb:
        return 0.0
    r = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    j = len(ta & tb) / float(len(ta | tb)) if (ta | tb) else 0.0
    return max(r, j)


def val_of(rec, f):
    return (rec.get("fields", {}).get(f) or {}).get("value")


def state_of(rec, f):
    return (rec.get("fields", {}).get(f) or {}).get("state", "unknown")


# ----------------------------------------------------------------- dedup votes
def vote_pair(a, b):
    v, why = [], []
    da, db_ = val_of(a, "doi"), val_of(b, "doi")
    if da and db_ and da == db_:
        v.append(("doi_equal", 3, da)); why.append("DOI 相同（%s）" % da)
    shared = []
    for f in ("pmid", "pmcid", "arxiv"):
        x, y = val_of(a, f), val_of(b, f)
        if x and y and str(x).lower() == str(y).lower():
            shared.append("%s=%s" % (f, x))
    if shared:
        v.append(("id_family_equal", 2, ",".join(shared))); why.append("标识符族相同（%s）" % ",".join(shared))
    s = sim(val_of(a, "title") or "", val_of(b, "title") or "")
    if s >= 0.92:
        v.append(("title_sim>=0.92", 2, round(s, 3))); why.append("标题相似 %.3f ≥0.92" % s)
    elif s >= 0.80:
        v.append(("title_sim>=0.80", 1, round(s, 3))); why.append("标题相似 %.3f ∈[0.80,0.92)" % s)
    sa, sb = L.first_surname(a), L.first_surname(b)
    ya, yb = val_of(a, "year"), val_of(b, "year")
    if sa and sa == sb and ya and yb and int(ya) == int(yb):
        v.append(("first_author_year_equal", 1, "%s/%s" % (sa, ya)))
        why.append("首作者姓 %s 与年份 %s 一致" % (sa, ya))
    score = sum(x[1] for x in v)
    return {"score": score, "votes": [{"signal": x[0], "weight": x[1], "detail": str(x[2])} for x in v],
            "reason": "；".join(why) if why else "四路信号均未命中"}


def candidates(records):
    blocks = {}
    for r in records:
        ks = []
        d = val_of(r, "doi")
        if d:
            ks.append("doi:" + d)
        for f in ("pmid", "pmcid", "arxiv"):
            x = val_of(r, f)
            if x:
                ks.append("%s:%s" % (f, str(x).lower()))
        s, y = L.first_surname(r), val_of(r, "year")
        if s and y:
            ks.append("ay:%s|%s" % (s, y))
        tk = sorted(toks(val_of(r, "title") or ""))
        for i in range(len(tk) - 1):
            ks.append("t:%s|%s" % (tk[i], tk[i + 1]))
        for k in ks:
            blocks.setdefault(k, []).append(r)
    byid = {r["rid"]: r for r in records}
    seen, pairs = set(), []
    for k, group in sorted(blocks.items()):
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i]["rid"], group[j]["rid"]
                key = tuple(sorted((a, b)))
                if key in seen:
                    continue
                seen.add(key)
                vt = vote_pair(byid[a], byid[b])
                pairs.append({"pair_id": "P-%04d" % (len(pairs) + 1), "a": key[0], "b": key[1],
                              "score": vt["score"], "votes": vt["votes"], "reason": vt["reason"],
                              "rule_decision": "duplicate" if vt["score"] >= 4 else
                                               ("maybe" if vt["score"] == 3 else "distinct")})
    pairs.sort(key=lambda p: (-p["score"], p["pair_id"]))
    for i, p in enumerate(pairs, 1):
        p["pair_id"] = "P-%04d" % i
    return pairs


# -------------------------------------------------------------------- clusters
class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def decisions_map(pairs, draft):
    """draft cluster_decisions -> {(rid_a, rid_b): decision dict}."""
    idx = {tuple(sorted((p["a"], p["b"]))): p for p in pairs}
    bypid = {p["pair_id"]: p for p in pairs}
    out, problems = {}, []
    for d in (draft.get("cluster_decisions") or []):
        if not isinstance(d, dict):
            continue
        raw = d.get("pair") or d.get("pair_id") or d.get("rids") or d.get("members")
        if isinstance(raw, str) and raw in bypid:
            key = tuple(sorted((bypid[raw]["a"], bypid[raw]["b"])))
        elif isinstance(raw, list) and len(raw) >= 2:
            key = tuple(sorted((str(raw[0]), str(raw[1]))))
        elif isinstance(raw, str) and "-" in raw and len(raw.split("-")) >= 2:
            key = tuple(sorted((raw.split("-")[0].strip(), raw.split("-")[1].strip())))
        else:
            problems.append({"pair": raw, "error": "unresolvable pair reference"})
            continue
        if key not in idx:
            problems.append({"pair": list(key), "error": "pair not in candidate set"})
            continue
        dec = str(d.get("decision") or "").lower()
        dec = {"dup": "duplicate", "duplicated": "duplicate", "same": "duplicate", "merge": "duplicate",
               "different": "distinct", "unique": "distinct", "split": "distinct",
               "unsure": "maybe", "uncertain": "maybe", "pending": "maybe"}.get(dec, dec)
        if dec not in ("duplicate", "distinct", "maybe"):
            problems.append({"pair": list(key), "error": "decision must be duplicate|distinct|maybe"})
            continue
        out[key] = {"decision": dec, "reason": L.clip(d.get("reason") or "", 400),
                    "locator": d.get("locator") or "", "source": "agent"}
    return out, problems


def build_clusters(records, pairs, dmap):
    uf = UF()
    byid = {r["rid"]: r for r in records}
    for r in records:
        uf.find(r["rid"])
    decided = {}
    for p in pairs:
        key = tuple(sorted((p["a"], p["b"])))
        dd = dmap.get(key)
        dec = dd["decision"] if dd else p["rule_decision"]
        decided[p["pair_id"]] = dict(p, final_decision=dec,
                                    decision_source=("agent" if dd else "rule"),
                                    decision_reason=(dd or {}).get("reason") or p["reason"])
        if dec == "duplicate":
            uf.union(p["a"], p["b"])
    groups = {}
    for r in records:
        groups.setdefault(uf.find(r["rid"]), []).append(r["rid"])
    clusters = []
    for i, (_, rids) in enumerate(sorted(groups.items(),
                                        key=lambda kv: (-max(byid[x]["completeness"] for x in kv[1]),
                                                        sorted(kv[1])[0])), 1):
        members = [byid[x] for x in sorted(rids)]
        mine = [d for d in decided.values()
                if d.get("final_decision") == "duplicate" and d["a"] in rids and d["b"] in rids]
        clusters.append({"cluster_id": "C-%04d" % i, "member_ids": sorted(rids),
                         "members": members, "pairs": mine})
    return clusters, decided


def pick_canon(f, cands):
    """cands: [(rec, field_dict)] all state=present. Return (rec, field_dict, rule)."""
    def key(item):
        r, fl = item
        v = fl["value"]
        lp = len(v) if isinstance(v, str) else (len(v) if isinstance(v, list) else 1)
        return (-prio(r["db"]), -lp)
    if f == "doi":
        best = sorted(cands, key=lambda it: (0 if it[0]["db"] == "crossref" else 1, prio(it[0]["db"])))
        return best[0][0], best[0][1], "N-05"
    if f == "year":
        best = sorted(cands, key=lambda it: (-prio(it[0]["db"]), it[1]["value"]))
        return best[0][0], best[0][1], "N-03"
    if f == "authors":
        best = sorted(cands, key=lambda it: (-prio(it[0]["db"]), -len(it[1]["value"] or [])))
        return best[0][0], best[0][1], "N-02"
    best = sorted(cands, key=key)[0]
    rid = {"title": "N-01", "venue": "N-04", "abstract": "N-06"}.get(f, "N-09")
    return best[0], best[1], rid


def norm_val(f, v):
    if isinstance(v, list):
        return "|".join(L.first_surname({"fields": {"authors": {"value": [x]}}}) or tnorm(x) for x in v)
    if f == "year":
        return str(v)
    if f == "doi":
        return str(v).lower()
    return tnorm(v) or str(v).lower()


def merge_clusters(clusters, cres):
    """Attach canonical fields, conflicts and merge reasons to every cluster."""
    out = []
    for c in clusters:
        members = c["members"]
        canon, conflicts, untraced = {}, [], []
        for f in COV + L.IDF:
            cands = [(r, r["fields"][f]) for r in members
                     if (r["fields"].get(f) or {}).get("state") == "present"]
            if not cands:
                st = "unknown" if all(state_of(r, f) == "unknown" for r in members) else "missing"
                canon[f] = {"value": None, "src_db": None, "rid": None, "locator": None,
                            "rule": None, "state": st}
                continue
            rec, fl, rule = pick_canon(f, cands)
            vals, mvals = {}, {}
            for r, g in cands:
                vals.setdefault(norm_val(f, g["value"]), []).append(r["rid"])
                mvals[r["rid"]] = g["value"]
            chosen_val, src, note = fl["value"], "rule", ""
            for k in (f, "*"):
                for cr in cres:
                    if str(cr.get("cluster")) in (c["cluster_id"], "*") and str(cr.get("field")) in (f, "*", k):
                        chosen_val = cr.get("value", chosen_val)
                        src = "agent"
                        note = cr.get("reason") or ""
                        break
                if src == "agent":
                    break
            canon[f] = {"value": chosen_val, "src_db": rec["db"], "rid": rec["rid"],
                        "locator": rec["locator"], "rule": rule, "state": "present",
                        "resolution": src, "note": note}
            if len(vals) > 1:
                conflicts.append({"field": f, "values": mvals,
                                  "chosen": chosen_val, "chosen_rid": rec["rid"], "rule": rule,
                                  "resolution": src, "note": note,
                                  "status": "resolved_by_agent" if src == "agent" else "resolved_by_rule"})
            if chosen_val != fl["value"] and src == "agent":
                pass
            # value-level provenance: chosen value must be findable in some member raw text
            if isinstance(chosen_val, str) and chosen_val:
                pool = " ".join(str(m.get("raw", "")) for m in members).lower()
                probe = tnorm(chosen_val)
                if probe and probe not in tnorm(pool) and not any(
                        probe in tnorm(str((m["fields"].get(f) or {}).get("value"))) for m in members):
                    if probe not in tnorm(json.dumps([m["fields"].get(f) for m in members], ensure_ascii=False)):
                        untraced.append(f)
        dbs = sorted({r["db"] for r in members})
        reason = []
        for p in sorted([x for x in c.get("pairs", [])], key=lambda q: -q["score"]):
            reason.append("%s: %s" % ("+".join(sorted({p["a"], p["b"]})), p["reason"]))
        out.append({"cluster_id": c["cluster_id"], "member_ids": sorted(c["member_ids"]),
                    "members": members, "canonical": canon, "conflicts": conflicts, "source_dbs": dbs,
                    "merge_reason": reason[0] if reason else
                    ("single-record cluster (%s)" % dbs[0] if dbs else "empty"),
                    "member_reasons": reason, "untraced_fields": untraced,
                    "completeness": max([r["completeness"] for r in members] or [0])})
    return out


# -------------------------------------------------------------------- coverage
def coverage_rows(idx, clusters):
    dbs = []
    for r in idx["records"]:
        if r["db"] not in dbs:
            dbs.append(r["db"])
    for f in list(idx.get("failures", [])) + list(idx.get("empty", [])):
        if f.get("db") and f["db"] not in dbs:
            dbs.append(f["db"])
    failed = {f.get("db") for f in idx.get("failures", [])}
    rows = []
    for db in sorted(dbs):
        recs = [r for r in idx["records"] if r["db"] == db]
        cells = {}
        for f in COV:
            cnt = {"present": 0, "missing": 0, "suspect": 0, "unknown": 0}
            for r in recs:
                cnt[state_of(r, f)] = cnt.get(state_of(r, f), 0) + 1
            cells[f] = cnt
        n = len(recs)
        present = sum(cells[f]["present"] for f in COV)
        rows.append({"db": db, "records": n, "cells": cells,
                     "fields_present": present,
                     "field_ratio": round(present / float(n * len(COV)), 3) if n else 0.0,
                     "status": ("FAILED" if db in failed and not n else ("ok" if n else "no_records")),
                     "files": [f["path"] for f in idx["files"] if f["db"] == db]})
    single = [c["cluster_id"] for c in clusters if len(c["source_dbs"]) == 1]
    sysmiss = []
    for f in COV:
        present_dbs = sum(1 for r in rows if r["cells"][f]["present"] > 0)
        if rows and present_dbs <= max(0, len(rows) // 2):
            sysmiss.append({"field": f, "dbs_with_value": present_dbs, "dbs_total": len(rows),
                            "note": "field present in at most half of the databases"})
    return {"rows": rows, "failed": sorted(x for x in failed if x), "single_db_clusters": single,
            "systematic_missing": sysmiss,
            "unparsed": [f["path"] for f in idx["files"] if not f["n_records"] and f.get("db") not in failed]}


# ------------------------------------------------------------------ query rows
QKEYS = ("query", "q", "searchterms", "search_terms", "term", "terms", "keyword", "keywords",
         "querystring", "query_string", "expression", "request", "requesturl", "uri", "href",
         "searchurl", "parameters")


def query_evidence(idx):
    """db -> (verbatim query, locator, extra params) found inside the snapshots."""
    out = {}
    for f in idx["files"]:
        p = Path(idx["input"]) / f["path"]
        try:
            kind, obj, text, lists, _ = L.parse_one(p)
        except Exception:
            continue
        got, loc = "", ""
        if obj is not None:
            for k in QKEYS:
                vals = L.pick(obj, k) if k != "q" else (L.pick(obj, "q") or [])
                for v in vals:
                    if isinstance(v, str) and 2 < len(v) < 400:
                        got, loc = v, "%s#$.%s" % (f["path"], k)
                        break
                if got:
                    break
        if not got:
            for k in QKEYS:
                m = re.search(r"[?&](?:%s)=([^&\s\"']{2,200})" % k, text[:20000])
                if m:
                    got, loc = m.group(1), "%s#url-param:%s" % (f["path"], k)
                    break
        if got:
            out.setdefault(f["db"], []).append({"query": L.clip(got, 300), "locator": loc,
                                                "file": f["path"]})
    return out


def query_rows(idx, clusters, draft):
    ev = query_evidence(idx)
    notes = {}
    for n in (draft.get("query_matrix_notes") or []):
        if isinstance(n, dict) and n.get("db"):
            notes[str(n["db"]).lower()] = n
    rows = []
    for row in coverage_rows(idx, clusters)["rows"]:
        db = row["db"]
        e = (ev.get(db) or [{}])[0]
        n = notes.get(db, {})
        members = [c for c in clusters if db in c["source_dbs"]]
        rows.append({"db": db,
                     "topic_terms": n.get("topic_terms") or "",
                     "field_scope": n.get("field_scope") or "",
                     "time_window": n.get("time_window") or "",
                     "paging": n.get("paging") or "",
                     "query_sent": n.get("query_sent") or e.get("query") or "",
                     "query_origin": "agent" if n.get("query_sent") else ("snapshot" if e.get("query") else "not_recorded"),
                     "evidence_locator": n.get("locator") or e.get("locator") or "",
                     "calls": n.get("calls") if n.get("calls") is not None else "",
                     "returned": row["records"],
                     "unique_clusters": len(members),
                     "status": row["status"],
                     "note": n.get("note") or ""})
    failed = {f.get("db") for f in idx.get("failures", [])}
    for db in sorted(x for x in failed if x and x not in [r["db"] for r in rows]):
        fail = next((f for f in idx["failures"] if f.get("db") == db), {})
        rows.append({"db": db, "topic_terms": "", "field_scope": "", "time_window": "", "paging": "",
                     "query_sent": "", "query_origin": "not_recorded", "evidence_locator": fail.get("path", ""),
                     "calls": "", "returned": 0, "unique_clusters": 0,
                     "status": "FAILED(%s)" % L.clip(fail.get("reason") or "unusable response", 60),
                     "note": "response unusable; coverage gap reported, nothing fabricated"})
    # convergence audit: same verbatim query copied across databases
    groups = {}
    for r in rows:
        q = tnorm(r["query_sent"])
        if q and len(q) > 6:
            groups.setdefault(q, []).append(r["db"])
    dup = [{"query_prefix": k[:90], "dbs": v} for k, v in groups.items() if len(v) > 1]
    return rows, dup
