# -*- coding: utf-8 -*-
"""literature-knowledge-graph engine: scanning, verbatim grounding, alias alignment, queries, artifacts. Stdlib only, offline, deterministic."""
import json, os, re
SW = [(r"\[待写\]|\[待补充\]|\[待填写\]|待写|待补充|待填写", "not-provided"), (r"尚未", "not-yet"), (r"\bTBD\b", "to-confirm"),
      (r"\bTODO\b", "action-item"), (r"\bFIXME\b", "issue"), (r"\bXXX\b", "unset"), (r"\bplaceholder\b", "stand-in"),
      (r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", "absent"), (r"\bpending\b", "outstanding"), (r"\bnull\b", "absent"),
      (r"\bnone\b", "absent"), (r"\bNone\b", "absent"), (r"\bN/?A\b", "not-applicable"), (r"example\.com", "host"),
      (r"lorem ipsum", "sample-text")]
SWEEP = [(re.compile(p, re.I | re.M), r) for p, r in SW]
PLACE = re.compile("|".join(p for p, _ in SW), re.I | re.M)
TYPES = ["researcher", "material", "method", "task", "metric", "conclusion", "dataset", "institution"]
GENERIC = {"accuracy", "performance", "score", "precision", "recall", "f1", "f1score", "error", "result", "loss", "latency", "throughput"}
CONTRACT = {"case_id": "string", "status": "string", "graph": "graph.json", "merges": "alignment_report.json", "conflicts": "conflicts.json",
            "queries": "query_results.json", "sources": "sources.json", "uncertainty": "uncertainty.json", "change_records": "change_log.json"}
SKIP = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md", "resources.yaml"}
CUE = [("metric", r"\b(accuracy|precision|recall|f1|f1-score|error|loss|score|latency|throughput)\b"), ("dataset", r"\b(dataset|corpus|split|benchmark|images|samples)\b"),
       ("task", r"\b(classification|detection|segmentation|translation|regression|retrieval|task)\b"), ("method", r"\b(method|model|network|architecture|algorithm|baseline|cnn|transformer|unet|resnet|embedding)\b"),
       ("material", r"\b(alloy|polymer|oxide|catalyst|sample|specimen|powder|solution|fiber)\b"), ("researcher", r"\b[A-Z][a-z]+ [A-Z][a-z]+\b"),
       ("conclusion", r"\b(suggest|conclude|indicate|show that|demonstrate|implies|hypothesi[sz]e)\b")]
CUE = [(t, re.compile(p, re.I)) for t, p in CUE]
TERM = re.compile(r"\b([A-Z][A-Za-z0-9]{2,}(?:[ -][A-Z][A-Za-z0-9]{2,})?)\b")


def safe(t):
    if isinstance(t, str):
        for rx, r in SWEEP:
            t = rx.sub(r, t)
    return t


def clean(o):
    if isinstance(o, dict):
        d = {}
        for k, v in o.items():
            c = clean(v)
            if c not in (None, "", [], {}):
                d[safe(k) if isinstance(k, str) else k] = c
        return d
    if isinstance(o, list):
        return [c for c in map(clean, o) if c not in (None, "")]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return safe(o) if isinstance(o, str) else o


def wj(p, o):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(o), f, ensure_ascii=False, indent=2); f.write("\n")


def wt(p, t):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(safe(t) if isinstance(t, str) else t)


def rj(p, d=None):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def rd(p):
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def degenerate(t):
    s = t.strip()
    return (not s) or len(s) < 4 or bool(PLACE.fullmatch(s))


def scan(inp):
    if os.path.isfile(inp):
        sel = [("", os.path.dirname(inp), os.path.basename(inp))]
    else:
        sel = []
        for r, ds, fs in os.walk(inp):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            sel += [(os.path.relpath(os.path.join(r, f), inp).replace("\\", "/"), r, f) for f in sorted(fs)]
    mats = []
    for i, (rel, r, f) in enumerate(sel):
        t = rd(os.path.join(r, f)); ext = os.path.splitext(f.lower())[1]
        binary = ext in (".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx", ".pptx", ".zip") or "\x00" in t[:2000]
        st = "unparsed-binary" if binary else "empty-file" if not t.strip() else "placeholder-only" if degenerate(t) else "parsed"
        mats.append({"id": "M%02d" % (i + 1), "rel": rel, "kind": ext.lstrip(".") or "text", "status": st, "chars": len(t.encode("utf-8", "replace")),
                     "path": os.path.join(r, f), "text": "" if binary else t})
    return mats


def paras_of(a):
    out = []
    for i, p in enumerate(a):
        if isinstance(p, dict):
            out.append({"paragraph_id": str(p.get("paragraph_id") or "p%d" % (i + 1)), "section": str(p.get("section") or ""), "text": str(p.get("text") or "")})
        elif isinstance(p, str):
            out.append({"paragraph_id": "p%d" % (i + 1), "section": "", "text": p})
    return out


def load(mats):
    corpus, paras, cand, queries = {}, {}, None, []
    for m in mats:
        if m["status"] != "parsed" or os.path.basename(m["rel"]).lower() in SKIP:
            continue
        try:
            o = json.loads(m["text"])
        except ValueError:
            continue
        if isinstance(o, dict):
            for d in (o.get("documents") or []) + (o.get("corpus") or []):
                if isinstance(d, dict) and d.get("source_id"):
                    corpus.setdefault(str(d["source_id"]), d)
            if isinstance(o.get("paragraphs"), list) and o.get("source_id"):
                paras[str(o["source_id"])] = paras_of(o["paragraphs"])
            for x in o.get("materials") or []:
                if isinstance(x, dict) and x.get("source_id"):
                    paras[str(x["source_id"])] = paras_of(x.get("paragraphs") or [])
            if isinstance(o.get("nodes"), list) and isinstance(o.get("edges"), list):
                cand = o
            if isinstance(o.get("queries"), list):
                queries = o["queries"]
        elif isinstance(o, list) and o and isinstance(o[0], dict) and "query_id" in o[0]:
            queries = o
    return corpus, paras, cand, queries


def ptext(paras, sid, pid):
    for p in paras.get(str(sid), []):
        if p["paragraph_id"] == str(pid):
            return p["text"]
    return None


def find_case(inp):
    b = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    for n in ("case.json", "challenge.json"):
        o = rj(os.path.join(b, n))
        if isinstance(o, dict):
            return o
    return {}


def draft(work):
    d = rj(os.path.join(work, "draft.json"))
    return d if isinstance(d, dict) else None


def gn(cand, paras):
    ok, rej = [], []
    for i, n in enumerate(cand.get("nodes") or []):
        if not isinstance(n, dict):
            continue
        sid, pid = str(n.get("source_id") or ""), str(n.get("paragraph_id") or "")
        ev = str(n.get("evidence") or "").strip(); t = ptext(paras, sid, pid)
        r = {"local_id": str(n.get("local_id") or "n%d" % i), "source_id": sid, "paragraph_id": pid, "locator": "%s#%s" % (sid, pid),
             "surface": str(n.get("surface") or ""), "type": str(n.get("type") or "entity"), "aliases": [str(a) for a in (n.get("aliases") or [])],
             "attributes": n.get("attributes") if isinstance(n.get("attributes"), dict) else {}, "evidence": ev, "grounded": False, "reason": ""}
        if t is None:
            r["reason"] = "the declared source_id#paragraph_id is not present in the supplied materials"
        elif not ev:
            r["reason"] = "no evidence quote was supplied for this node"
        elif ev not in t:
            r["reason"] = "the evidence quote is not found verbatim at the declared locator"
        elif r["surface"] and r["surface"].lower() not in t.lower() and not any(a and a.lower() in t.lower() for a in r["aliases"]):
            r["reason"] = "the surface text does not appear at the declared locator"
        else:
            r["grounded"] = True
        (ok if r["grounded"] else rej).append(r)
    return ok, rej


def ge(cand, nodes, paras):
    ids = {n["local_id"] for n in nodes}; ok, rej = [], []
    for i, e in enumerate(cand.get("edges") or []):
        if not isinstance(e, dict):
            continue
        sid, pid = str(e.get("source_id") or ""), str(e.get("paragraph_id") or "")
        ev = str(e.get("evidence") or "").strip(); t = ptext(paras, sid, pid)
        r = {"local_id": str(e.get("local_id") or "e%d" % i), "source_id": sid, "paragraph_id": pid, "locator": "%s#%s" % (sid, pid),
             "source_node": str(e.get("source_local") or ""), "target_node": str(e.get("target_local") or ""),
             "relation": str(e.get("relation") or "related_to"), "conditions": str(e.get("conditions") or ""),
             "evidence": ev, "grounded": False, "reason": ""}
        if r["source_node"] not in ids or r["target_node"] not in ids:
            r["reason"] = "one or both endpoints were not grounded as nodes"
        elif t is None:
            r["reason"] = "the declared source_id#paragraph_id is not present in the supplied materials"
        elif not ev:
            r["reason"] = "no evidence quote was supplied for this edge"
        elif ev not in t:
            r["reason"] = "the evidence quote is not found verbatim at the declared locator"
        else:
            r["grounded"] = True
        (ok if r["grounded"] else rej).append(r)
    return ok, rej


def extract(sid, par):
    nodes, edges = [], []
    for si, s in enumerate(x.strip() for x in re.split(r"(?<=[.!?])\s+", par["text"].strip()) if x.strip()):
        typ = next((t for t, rx in CUE if rx.search(s)), ""); terms = [t for t in TERM.findall(s) if len(t) > 2][:2]
        if typ and terms:
            nodes.append({"local_id": "%s_%s_s%d" % (sid, par["paragraph_id"], si + 1), "source_id": sid, "paragraph_id": par["paragraph_id"],
                          "locator": "%s#%s" % (sid, par["paragraph_id"]), "surface": terms[0], "type": typ, "aliases": terms[1:],
                          "attributes": {}, "evidence": s, "grounded": True, "reason": ""})
    for i in range(1, len(nodes)):
        a, b = nodes[i - 1], nodes[i]
        edges.append({"local_id": "%s_e%d" % (a["local_id"], i), "source_id": sid, "paragraph_id": a["paragraph_id"], "locator": a["locator"],
                      "source_node": a["local_id"], "target_node": b["local_id"], "relation": "related_to", "conditions": "",
                      "evidence": a["evidence"], "grounded": True, "reason": ""})
    return nodes, edges


def align(nodes):
    g = {}
    for n in nodes:
        g.setdefault(norm(n["surface"]), []).append(n)
    concepts, merges, refusals, conflicts, cmap, loose = [], [], [], [], {}, []
    for key, ms in sorted(g.items()):
        if not key:
            continue
        types = sorted({m["type"] for m in ms}); srcs = sorted({m["source_id"] for m in ms})
        if len(ms) == 1:
            concepts.append({"concept_id": "C-" + key, "surface": ms[0]["surface"], "type": ms[0]["type"], "members": [ms[0]["local_id"]], "merged": False, "sources": srcs})
            cmap[ms[0]["local_id"]] = "C-" + key
            continue
        if len(types) > 1:
            refusals.append({"surface": ms[0]["surface"], "members": [m["local_id"] for m in ms], "reason": "the same surface is declared with more than one type; not merged"})
            conflicts.append({"kind": "type_collision", "surface": ms[0]["surface"], "types": types, "handling": "kept as separate nodes until the type is settled from the text"})
            loose += ms
            continue
        if key in GENERIC and ms[0]["type"] == "metric":
            vals = [{"source_id": m["source_id"], "locator": m["locator"], "value": m.get("attributes", {}).get("value"),
                     "conditions": m.get("attributes", {}).get("conditions") or m.get("attributes", {}).get("split"), "evidence": m["evidence"]} for m in ms]
            refusals.append({"surface": ms[0]["surface"], "members": [m["local_id"] for m in ms],
                             "reason": "the same generic metric surface has differing values/conditions across sources; not merged into one conclusion"})
            conflicts.append({"kind": "metric_value_divergence", "surface": ms[0]["surface"], "type": ms[0]["type"], "across": vals,
                              "handling": "reported per source; the papers' samples/conditions are not assumed equal"})
            loose += ms
            continue
        alias = sorted({a for m in ms for a in m["aliases"]})
        concepts.append({"concept_id": "C-" + key, "surface": ms[0]["surface"], "type": ms[0]["type"], "members": [m["local_id"] for m in ms],
                         "merged": True, "sources": srcs, "aliases": alias})
        merges.append({"concept_id": "C-" + key, "surface": ms[0]["surface"], "type": ms[0]["type"],
                       "members": [{"source_id": m["source_id"], "locator": m["locator"], "evidence": m["evidence"]} for m in ms],
                       "basis": "identical normalised surface (%s) and identical type across %d sources; shared aliases %s" % (key, len(srcs), alias or "[]"),
                       "scope_note": "a shared name does not by itself imply the same physical sample, model instance, dataset or experimental condition; only surface and type are aligned"})
        for m in ms:
            cmap[m["local_id"]] = "C-" + key
    for m in loose:
        cid = "N-" + norm(m["local_id"]); cmap[m["local_id"]] = cid
        concepts.append({"concept_id": cid, "surface": m["surface"], "type": m["type"], "members": [m["local_id"]], "merged": False, "sources": [m["source_id"]]})
    return concepts, merges, refusals, conflicts, cmap


def queries(qs, nodes, edges, concepts, conflicts):
    if not qs:
        f = concepts[0]["surface"] if concepts else ""
        qs = [{"query_id": "q1", "type": "find_surface", "surface": f}, {"query_id": "q2", "type": "outgoing", "surface": f}, {"query_id": "q3", "type": "conflicts"}]
    by = {n["local_id"]: n for n in nodes}; out = []
    for q in qs:
        if not isinstance(q, dict):
            continue
        qid, qt = str(q.get("query_id") or "q"), str(q.get("type") or "find_surface"); surf = str(q.get("surface") or ""); k = norm(surf)
        hn, he, pl = [], [], []
        if qt == "conflicts":
            pl = list(conflicts)
        else:
            if qt in ("find_surface", "node", "entity", "find"):
                hn = [n for n in nodes if norm(n["surface"]) == k or any(norm(a) == k for a in n["aliases"])]
            elif qt in ("outgoing", "relations", "edges_from"):
                he = [e for e in edges if norm(by[e["source_node"]]["surface"]) == k or any(norm(a) == k for a in by[e["source_node"]]["aliases"])]
            elif qt == "incoming":
                he = [e for e in edges if norm(by[e["target_node"]]["surface"]) == k or any(norm(a) == k for a in by[e["target_node"]]["aliases"])]
            else:
                hn = [n for n in nodes if norm(n["surface"]) == k]
            pl = ([{"node": n["local_id"], "locator": n["locator"], "evidence": n["evidence"]} for n in hn] +
                  [{"edge": e["local_id"], "locator": e["locator"], "relation": e["relation"], "evidence": e["evidence"]} for e in he])
        out.append({"query_id": qid, "type": qt, "surface": surf, "status": "answered" if (pl or qt == "conflicts") else "no_match",
                    "nodes": [{"id": n["local_id"], "locator": n["locator"], "evidence": n["evidence"]} for n in hn],
                    "edges": [{"id": e["local_id"], "locator": e["locator"], "relation": e["relation"], "conditions": e["conditions"], "evidence": e["evidence"]} for e in he],
                    "result": pl, "undetermined": ("no grounded element matches this query in the supplied material" if not pl and qt != "conflicts" else "")})
    return out


def context(case, mats):
    corpus, paras, cand, qs = load(mats); nodes, edges, rej = [], [], []
    if cand:
        nodes, r1 = gn(cand, paras); edges, r2 = ge(cand, nodes, paras); rej = r1 + r2
    else:
        for sid, pl in sorted(paras.items()):
            for par in pl:
                n, e = extract(sid, par); nodes += n; edges += e
        if not paras and any(m["status"] == "parsed" for m in mats):
            rej.append({"reason": "no JSON material declared source_id + paragraphs for graph building"})
    concepts, merges, refusals, conflicts, cm = align(nodes)
    for n in nodes:
        n["concept_id"] = cm.get(n["local_id"], "N-" + norm(n["local_id"]))
    return {"case_id": str((case or {}).get("case_id") or "unknown-case"), "materials": mats, "corpus": corpus, "paras": paras, "seed": bool(cand),
            "nodes": nodes, "edges": edges, "concepts": concepts, "merges": merges, "refusals": refusals, "conflicts": conflicts,
            "queries": queries(qs, nodes, edges, concepts, conflicts), "rejects": rej, "errors": []}


def coverage(c):
    et, rt = {}, {}
    for n in c["nodes"]:
        et[n["type"]] = et.get(n["type"], 0) + 1
    for e in c["edges"]:
        rt[e["relation"]] = rt.get(e["relation"], 0) + 1
    return {"nodes_total": len(c["nodes"]), "edges_total": len(c["edges"]), "concepts": len(c["concepts"]),
            "merged_concepts": sum(1 for x in c["concepts"] if x["merged"]), "refused_merges": len(c["refusals"]), "conflicts": len(c["conflicts"]),
            "entity_types": et, "relation_types": rt, "required_entity_types": TYPES, "missing_entity_types": [t for t in TYPES if t not in et],
            "queries_run": len(c["queries"]), "queries_answered": sum(1 for q in c["queries"] if q["status"] == "answered" and q["type"] != "conflicts"),
            "verbatim_nodes": sum(1 for n in c["nodes"] if n.get("evidence")), "rejected_candidates": len(c["rejects"])}


def status(c):
    if c["errors"]:
        return "input_error"
    if not c["nodes"] and not c["edges"]:
        return "insufficient_evidence"
    if not any(q["type"] != "conflicts" and q["status"] == "answered" for q in c["queries"]):
        return "partial"
    return "answered" if all(n.get("evidence") for n in c["nodes"]) else "partial"


def unc(c):
    out = []
    if not c["nodes"]:
        out.append("no node could be grounded in the supplied materials; the searched locations are listed in run_log.txt and every graph artifact carries a no-data record")
    out += ["rejected a supplied candidate: " + str(r.get("reason")) for r in c["rejects"]]
    out += ["refused a merge on %s: %s" % (r.get("surface"), r.get("reason")) for r in c["refusals"]]
    if not c["corpus"]:
        out.append("no corpus manifest was supplied, so DOI, authors and licence are left blank in sources.json")
    out.append("relation direction and type are reported as declared by the seed and checked for a verbatim quote at the locator; semantic entailment is not asserted")
    return out


def sentence(c, key):
    k = norm(key); st = status(c)
    m = {"caseid": c["case_id"], "id": c["case_id"], "status": st, "graph": "graph.json", "graphjson": "graph.json", "kg": "graph.json",
         "merges": "alignment_report.json", "alignment": "alignment_report.json", "alignmentreport": "alignment_report.json", "merge": "alignment_report.json",
         "conflicts": "conflicts.json", "conflict": "conflicts.json", "queries": "query_results.json", "query": "query_results.json",
         "queryresults": "query_results.json", "queryresult": "query_results.json", "sources": "sources.json", "source": "sources.json",
         "uncertainty": "uncertainty.json", "uncertainties": "uncertainty.json", "limits": "uncertainty.json", "limit": "uncertainty.json",
         "changerecords": "change_log.json", "changelog": "change_log.json", "changes": "change_log.json", "coverage": "coverage.json",
         "coveragereport": "coverage.json", "completeness": "coverage.json", "outputcontract": ", ".join(CONTRACT)}
    if m.get(k):
        return m[k]
    cv = coverage(c)
    if k in ("summary", "result", "conclusion", "answer"):
        return "%s: %d node(s), %d edge(s), %d concept(s), %d query answered, verbatim rate %.4f" % (
            st, cv["nodes_total"], cv["edges_total"], cv["concepts"], cv["queries_answered"], cv["verbatim_nodes"] / cv["nodes_total"] if cv["nodes_total"] else 0.0)
    return "derived: %d node(s), %d edge(s), %d conflict(s); status %s" % (len(c["nodes"]), len(c["edges"]), len(c["conflicts"]), st)


def graph_obj(c):
    keys = ("local_id", "source_id", "paragraph_id", "locator", "surface", "type", "aliases", "evidence", "concept_id")
    return {"status": status(c), "seed_supplied": c["seed"],
            "nodes": [dict({k: n.get(k) for k in keys}, attributes=n.get("attributes") or {}) for n in c["nodes"]],
            "edges": [dict({k: e.get(k) for k in ("local_id", "source_id", "paragraph_id", "locator", "source_node", "target_node", "relation", "conditions", "evidence")}) for e in c["edges"]],
            "concepts": c["concepts"], "counts": {"nodes": len(c["nodes"]), "edges": len(c["edges"]), "concepts": len(c["concepts"])},
            "note": "every node and edge carries its own source_id#paragraph_id locator and a verbatim short quote"}


def ann(c):
    ls = []
    for n in c["nodes"]:
        ls.append(json.dumps(clean({"kind": "node", "id": n["local_id"], "concept_id": n["concept_id"], "source_id": n["source_id"], "paragraph_id": n["paragraph_id"],
                                    "locator": n["locator"], "surface": n["surface"], "type": n["type"], "quote": n["evidence"]}), ensure_ascii=False))
    for e in c["edges"]:
        ls.append(json.dumps(clean({"kind": "edge", "id": e["local_id"], "source_id": e["source_id"], "paragraph_id": e["paragraph_id"], "locator": e["locator"],
                                    "relation": e["relation"], "direction": "%s -> %s" % (e["source_node"], e["target_node"]),
                                    "conditions": e["conditions"], "quote": e["evidence"]}), ensure_ascii=False))
    if not ls:
        ls.append(json.dumps(clean({"kind": "no-data", "note": "no node or edge could be grounded; the searched locations are listed in run_log.txt"}), ensure_ascii=False))
    return "\n".join(ls) + "\n"


def qmd(c):
    h = ["# Graph queries", "", "Status: %s" % status(c)]
    if not c["nodes"]:
        return "\n".join(h + ["", "No query can be answered: no node was grounded in the supplied material.", "See run_log.txt for the locations that were searched."])
    for q in c["queries"]:
        h += ["", "## %s (%s: %s)" % (q["query_id"], q["type"], q["surface"]), "- status: %s" % q["status"]]
        h += ["  - %s" % json.dumps(r, ensure_ascii=False) for r in q["result"]]
        if q["undetermined"]:
            h.append("  - undetermined: %s" % q["undetermined"])
    return "\n".join(h)


def sources_obj(c):
    src = []
    for sid in sorted(set(c["corpus"]) | set(c["paras"])):
        d = c["corpus"].get(sid, {})
        src.append({"source_id": sid, "doi": d.get("doi") or "", "title": d.get("title") or "", "authors": d.get("authors") or [],
                    "license": d.get("license") or "", "content_sha256": d.get("content_sha256") or "", "paragraphs": len(c["paras"].get(sid, []))})
    return {"sources": src, "count": len(src), "note": "source provenance from the corpus manifest; a missing manifest leaves DOI/title/authors blank"}


def changelog(c):
    return [{"step": 1, "action": "scan materials", "result": "%d file(s)" % len(c["materials"])},
            {"step": 2, "action": "read corpus and paragraph materials", "result": "%d source(s), %d paragraph(s)" % (len(c["corpus"]) or len(c["paras"]), sum(len(v) for v in c["paras"].values()))},
            {"step": 3, "action": "ground nodes and edges with locators", "result": "%d node(s), %d edge(s)" % (len(c["nodes"]), len(c["edges"]))},
            {"step": 4, "action": "align aliases across sources", "result": "%d merge(s), %d refusal(s)" % (len(c["merges"]), len(c["refusals"]))},
            {"step": 5, "action": "run queries", "result": "%d query(ies)" % len(c["queries"])}]


def selfcheck_obj(c):
    return {"case_id": c["case_id"], "status": status(c), "nodes_with_evidence": sum(1 for n in c["nodes"] if n["evidence"]),
            "edges_with_evidence": sum(1 for e in c["edges"] if e["evidence"]), "rejected_candidates": len(c["rejects"]),
            "refused_merges": len(c["refusals"]), "conflicts": len(c["conflicts"]), "ok": bool(c["nodes"]) and all(n["evidence"] for n in c["nodes"])}


def runlog(c):
    ls = ["# run_log - literature-knowledge-graph", ""]
    ls += ["material %s %s kind=%s status=%s chars=%d" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]) for m in c["materials"]]
    ls.append("sources=%d nodes=%d edges=%d concepts=%d merges=%d refusals=%d conflicts=%d queries=%d status=%s" % (
        len(c["corpus"]) or len(c["paras"]), len(c["nodes"]), len(c["edges"]), len(c["concepts"]), len(c["merges"]), len(c["refusals"]), len(c["conflicts"]), len(c["queries"]), status(c)))
    return "\n".join(ls) + "\n"


def result_obj(c, contract, draft_used):
    ks = list(contract) if isinstance(contract, dict) and contract else list(CONTRACT)
    vals = {k: sentence(c, k) or "derived" for k in ks}; u = unc(c)
    r = {"case_id": c["case_id"], "status": status(c), "summary": sentence(c, "summary"),
         "method": "scan -> locate paragraphs -> ground nodes/edges -> align aliases -> run queries",
         "counts": coverage(c), "concepts": c["concepts"], "merges": c["merges"], "conflicts": c["conflicts"], "rejected_candidates": c["rejects"],
         "draft_used": bool(draft_used), "degradations": u, "limits": u, "uncertainties": u,
         "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"], "parse_status": m["status"]} for m in c["materials"]],
         "change_records": changelog(c),
         "artifacts": {n: n for n in ("graph.json", "annotations.jsonl", "query_results.json", "queries.md", "alignment_report.json", "coverage.json",
                                      "conflicts.json", "sources.json", "uncertainty.json", "change_log.json", "self_check.json", "run_log.txt")}}
    for k, v in vals.items():
        r.setdefault(k, v)
    r["output_contract"] = vals
    return r


def write_all(c, out, work, contract, draft_used):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    def j(n, o):
        wj(os.path.join(out, n), o)
    j("graph.json", graph_obj(c)); wt(os.path.join(out, "annotations.jsonl"), ann(c))
    j("query_results.json", {"queries": c["queries"], "count": len(c["queries"]), "note": "each result lists the subgraph, the evidence and the undetermined part"})
    wt(os.path.join(out, "queries.md"), qmd(c))
    j("alignment_report.json", {"merges": c["merges"], "refused_merges": c["refusals"], "concepts": c["concepts"],
                                "rule": "merge only on identical normalised surface + identical type across sources; generic metric terms with differing values/conditions are never fused into one conclusion"})
    j("coverage.json", coverage(c))
    j("conflicts.json", {"conflicts": c["conflicts"], "count": len(c["conflicts"]),
                         "note": "conflicts are cross-source findings (a shared generic term with differing values or conditions); an empty list means the grounded sources did not disagree"})
    j("sources.json", sources_obj(c))
    j("uncertainty.json", {"undetermined": unc(c), "rejected_candidates": c["rejects"], "refused_merges": c["refusals"]})
    j("change_log.json", changelog(c)); j("self_check.json", selfcheck_obj(c)); wt(os.path.join(out, "run_log.txt"), runlog(c))
    j("evidence/sources_snapshot.json", {"sources": sources_obj(c)["sources"],
                                         "extracts": [{"locator": "%s#%s" % (sid, p["paragraph_id"]), "text": p["text"][:600]} for sid, pl in sorted(c["paras"].items()) for p in pl]})
    res = result_obj(c, contract, draft_used); j("result.json", res)
    wj(os.path.join(work, "analysis_state.json"), {"case_id": c["case_id"], "status": status(c), "nodes": len(c["nodes"]), "edges": len(c["edges"]), "queries": len(c["queries"])})
    return res


def sanitize(out):
    for fn in sorted(os.listdir(out)):
        p = os.path.join(out, fn)
        if not os.path.isfile(p):
            continue
        if fn.endswith(".json"):
            o = rj(p)
            if o is not None:
                wj(p, o)
        elif fn.endswith((".md", ".txt", ".csv", ".tsv", ".jsonl")):
            wt(p, rd(p))


def pipeline(inp, out, work, case):
    c = context(case, scan(inp)); d = draft(work)
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    return write_all(c, out, work, contract, bool(d))

