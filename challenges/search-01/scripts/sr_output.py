#!/usr/bin/env python3
"""sr_output.py - artifact rendering for traceable-literature-retrieval.

Turns the built payload into human-auditable artifacts: the query-plan
suggestions shown to the drafting agent, the markdown report and the JSONL
screening log. Pure formatting, deterministic, standard library only.
"""

import json

import sr_core as C

VERSION = "1.0.0"


def suggest_queries(task, expansions, cap=8):
    seed = [k for k in task.get("seed_keywords", []) if k]
    if not seed:
        seed = [w for w in C.tokens(task.get("research_question", ""), 12) if len(w) > 3][:6]
    out = []
    if len(seed) >= 2:
        out.append({"query": " AND ".join('"%s"' % s for s in seed[:3]),
                    "intent": "core topic: all seed concepts co-occur",
                    "expected_fields": ["title", "abstract", "keywords"]})
        out.append({"query": " OR ".join('"%s"' % s for s in seed[:4]),
                    "intent": "recall widening across seed concepts",
                    "expected_fields": ["title", "abstract"]})
    for s in seed[:3]:
        exp = [e for e in expansions if e.get("long", "").lower().startswith(s.lower()[:5])][:1]
        if exp:
            e = exp[0]
            out.append({"query": '"%s" OR "%s"' % (s, e["long"]),
                        "intent": "term expansion: %s ~ %s" % (s, e["long"]),
                        "expected_fields": ["title", "abstract"]})
    return out[:cap]


# ------------------------------------------------------------- dedup/verify
def fingerprint(rec):
    if rec.get("doi"):
        return "doi:" + rec["doi"]
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", norm_text(rec.get("title") or ""))
    return "title:" + t[:90]


def cluster(records):
    groups, order = {}, []
    for r in records:
        key = fingerprint(r)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    clusters, conflicts = [], []
    for key in order:
        members = groups[key]
        keeper = max(members, key=lambda r: (r.get("completeness", 0), len(r.get("abstract") or "")))
        clusters.append({"key": key, "keeper": keeper, "members": members})
        if len(members) > 1:
            for field in ("year", "venue"):
                vals = {flat(m.get(field)) for m in members if m.get(field)}
                if len(vals) > 1:
                    conflicts.append({
                        "field": field, "kind": "metadata_conflict",
                        "values": sorted(vals),
                        "objects": [m["object_id"] for m in members],
                        "note": "same work reported differently across sources; both kept in record, keeper chosen by completeness",
                    })
    return clusters, conflicts


def verify_quote(quote, rec, min_len=12):
    q = norm_text(quote)
    if len(q) < min_len:
        return False, "too_short", 0.0
    hay = rec.get("text") or norm_text(rec.get("raw_text") or "")
    if q in hay:
        return True, "text", 1.0
    # tolerate an elided middle: check the two halves at the ellipsis
    parts = [p for p in re.split(r"\.\.\.|…", q) if len(p.strip()) >= 8]
    if len(parts) >= 2 and all(p.strip() in hay for p in parts):
        return True, "text_elided", 0.9
    return False, "not_found", 0.0




def render_report(payload, mode):
    rows, ex = payload.get("candidates") or [], payload.get("excluded") or []
    cov, log = payload.get("coverage") or {}, payload.get("search_log") or {}
    L = ["# Literature search report", "",
         "**Mode**: %s | **Status**: %s" % (mode, payload.get("status")), "",
         "## 1. Research question and scope", "",
         payload.get("summary") or "(not provided by the drafting agent)", "",
         "## 2. Candidate set (%d)" % len(rows), ""]
    if rows:
        L += ["| rank | year | title | venue | DOI | rel. | verbatim evidence |",
              "|---|---|---|---|---|---|---|"]
        for c in rows:
            r = c.get("relevance") or {}
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                c.get("rank"), c.get("year") or "n/a", (c.get("title") or "")[:90],
                (c.get("venue") or "n/a")[:40], c.get("doi") or "n/a",
                r.get("score") if r.get("score") is not None else "n/a",
                (r.get("quote") or "")[:70].replace("|", "/")))
    else:
        L.append("_No candidate passed screening; see coverage and status sections._")
    L += ["", "## 3. Screened out (%d)" % len(ex), ""]
    L += ["- `%s` %s — %s" % (e.get("object_id"), (e.get("title") or "")[:80],
                              (e.get("basis") or e.get("reason") or (e.get("relevance") or {}).get("basis") or (e.get("screening") or {}).get("reason") or "no reason recorded")[:160])
          for e in ex[:40]] or ["_Nothing recorded as excluded._"]
    L += ["", "## 4. Queries and search log", ""]
    L += ["- `%s` %s (source: %s, hits: %s, selected: %s)" % (
              q.get("query_id"), q.get("query"), q.get("source") or "n/a",
              q.get("hits", "n/a"), q.get("selected", "n/a"))
          for q in log.get("queries", [])] or ["_No query plan recorded._"]
    L += ["", "## 5. Coverage", "",
          "- target_k: %s, selected: %s, distinct after dedup: %s" % (
              cov.get("target_k"), cov.get("selected_count"), cov.get("distinct_after_dedup")),
          "- required references matched: %s / %s" % (
              cov.get("required_matched_count"), cov.get("required_total"))]
    L += ["- MISSING required: %s" % (m.get("doi") or m.get("title") or m.get("ref_id"))
          for m in cov.get("required_missing") or []]
    L += ["", "## 6. Conflicts and uncertainties", ""]
    L += ["- conflict on `%s`: %s" % (c.get("field"), c.get("values"))
          for c in payload.get("conflicts") or []]
    L += ["- %s" % (u if isinstance(u, str) else json.dumps(u, ensure_ascii=False))
          for u in payload.get("uncertainties") or []]
    if not payload.get("conflicts") and not payload.get("uncertainties"):
        L.append("_None recorded._")
    L += ["", "## 7. Status and degradations", "", "- status: `%s`" % payload.get("status")]
    L += ["- degradation `%s`: %s" % (d.get("code"), d.get("detail"))
          for d in payload.get("degradations") or []]
    L += ["- error `%s`: %s" % (e.get("code"), e.get("detail")) for e in payload.get("errors") or []]
    L += ["", "_traceable-literature-retrieval %s — every row keeps a source locator and a verbatim "
          "quote; re-verify with `main.py selfcheck`._" % VERSION, ""]
    return "\n".join(L)


def jsonl_lines(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
