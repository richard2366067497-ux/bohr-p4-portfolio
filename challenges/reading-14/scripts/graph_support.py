#!/usr/bin/env python3
"""Shared helpers for the literature graph builder: small JSON/CSV utilities,
the query engine, and the delivery self-check. Standard library only."""
import csv
import json
import re
from pathlib import Path

NODE_TYPES = ("researcher", "material", "method", "task", "metric", "conclusion")
REL_TYPES = ("uses", "compares", "outperforms", "supports", "contradicts")
DECISIONS = ("merge", "keep_distinct", "undetermined")
STATUSES = ("success", "partial", "undetermined", "refused")
REQUIRED_RESULT = ("case_id", "status", "graph", "queries", "alignment", "conflicts",
                   "uncertainty", "artifacts")


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def slug(text, limit=32):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return s[:limit] or "x"


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        return None


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def count_by(rows, key):
    out = {}
    for r in rows:
        out[r.get(key)] = out.get(r.get(key), 0) + 1
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------
# query engine
# --------------------------------------------------------------------------
def match_nodes(nodes, surface):
    key = norm(surface).lower()
    return [n for n in nodes if norm(n["label"]).lower() == key
            or any(norm(a).lower() == key for a in n["aliases"])
            or key in norm(n["label"]).lower()]


def run_query(spec, nodes, edges, conflicts):
    qid = spec.get("query_id") or spec.get("id") or "q?"
    qtype = (spec.get("type") or "find_surface").lower()
    surface = spec.get("surface") or spec.get("start") or ""
    question = spec.get("question") or "Query %s over the graph" % qid

    if qtype in ("conflicts", "conflict"):
        evidence = [{"source_id": c["source_a"].split("/")[0], "paragraph_id": c["source_a"],
                     "quote": c["detail"]} for c in conflicts]
        return {"query_id": qid, "question": question,
                "answer": conflicts if conflicts else "No conflict is recorded in the supplied corpus.",
                "status": "answered" if conflicts else "undetermined", "start_nodes": [],
                "subgraph": {"nodes": [], "edges": []}, "claims": [], "evidence": evidence,
                "undetermined": [] if conflicts else
                [{"reason": "no conflicting statement found", "subject": "conflicts"}]}

    starts = match_nodes(nodes, surface)
    if not starts:
        return {"query_id": qid, "question": question,
                "answer": "No node matches %r in the supplied corpus." % surface,
                "status": "undetermined", "start_nodes": [], "subgraph": {"nodes": [], "edges": []},
                "claims": [], "evidence": [],
                "undetermined": [{"reason": "surface not present in graph", "subject": surface}]}

    if qtype == "find_surface":
        sub_nodes = [n["node_id"] for n in starts]
    else:  # outgoing / incoming / neighbours: bounded BFS
        depth = spec.get("depth", 1)
        rels = spec.get("relation_types") or list(REL_TYPES)
        frontier = {n["node_id"] for n in starts}
        seen = set(frontier)
        for _ in range(max(0, int(depth or 0))):
            nxt = set()
            for e in edges:
                if e["type"] not in rels:
                    continue
                if e["source"] in frontier and e["target"] not in seen:
                    nxt.add(e["target"])
                if qtype in ("incoming", "neighbours", "neighbors") and \
                        e["target"] in frontier and e["source"] not in seen:
                    nxt.add(e["source"])
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        sub_nodes = sorted(seen)
    ids = set(sub_nodes)
    sub_edges = [e["edge_id"] for e in edges if e["source"] in ids and e["target"] in ids]
    evidence = []
    for e in edges:
        if e["edge_id"] in sub_edges:
            evidence.extend(e["evidence"])
    for n in starts:
        evidence.extend(n["mentions"])
    undetermined = []
    status = "answered"
    if not sub_edges and qtype != "find_surface":
        status = "undetermined"
        undetermined.append({"reason": "no relation of the requested type connects these nodes",
                             "subject": surface})
    return {"query_id": qid, "question": question,
            "answer": {"nodes": sub_nodes, "edges": sub_edges}, "status": status,
            "start_nodes": [n["node_id"] for n in starts],
            "subgraph": {"nodes": sub_nodes, "edges": sub_edges}, "claims": [],
            "evidence": evidence, "undetermined": undetermined}


def default_queries(nodes):
    specs = []
    if nodes:
        top = max(nodes, key=lambda n: n["degree"])
        specs.append({"query_id": "q1", "type": "outgoing", "depth": 1,
                      "surface": top["label"], "question": "What does %s connect to?" % top["label"]})
        for n in nodes:
            if n["aliases"]:
                specs.append({"query_id": "q2", "type": "find_surface", "surface": n["aliases"][0],
                              "question": "Which node is %r?" % n["aliases"][0]})
                break
    specs.append({"query_id": "q3", "type": "conflicts",
                  "question": "Do the two papers disagree anywhere?"})
    specs.append({"query_id": "q4", "type": "find_surface", "surface": "__absent_probe__",
                  "question": "Is there a relation between objects the corpus never mentions together?"})
    return specs


# --------------------------------------------------------------------------
# delivery self-check
# --------------------------------------------------------------------------
def validate(result, out_dir, by_id):
    checks, errors = [], []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            errors.append(name)

    graph = result.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    for k in REQUIRED_RESULT:
        check("result.%s" % k, k in result, "required field missing")
    check("status.enum", result.get("status") in STATUSES, "status=%r" % result.get("status"))
    check("graph.min_nodes", len(nodes) >= 1, "%d nodes" % len(nodes))
    ids = [n.get("node_id") for n in nodes]
    check("graph.unique_node_ids", len(ids) == len(set(ids)), "duplicate node ids")
    for n in nodes:
        check("node.type.%s" % n.get("node_id"), n.get("type") in NODE_TYPES, "type=%r" % n.get("type"))
        check("node.mentions.%s" % n.get("node_id"), bool(n.get("mentions")), "node has no excerpt evidence")
    eids = [e.get("edge_id") for e in edges]
    check("edge.unique_ids", len(eids) == len(set(eids)), "duplicate edge ids")
    for e in edges:
        check("edge.type.%s" % e.get("edge_id"), e.get("type") in REL_TYPES, "type=%r" % e.get("type"))
        check("edge.endpoints.%s" % e.get("edge_id"),
              e.get("source") in set(ids) and e.get("target") in set(ids), "endpoint node does not exist")
        check("edge.evidence.%s" % e.get("edge_id"), bool(e.get("evidence")), "edge has no evidence")
    for n in nodes:
        for m in n.get("mentions") or []:
            check("mention.fields", all(m.get(f) for f in ("source_id", "paragraph_id", "quote")),
                  "mention missing a required field")
            block = by_id.get((m["source_id"], m["paragraph_id"]))
            check("mention.verbatim", block is not None and m["quote"] in block["text"],
                  "quote is not verbatim in its paragraph")
    queries = result.get("queries") or []
    check("queries.min", len(queries) >= 3, "%d queries" % len(queries))
    for q in queries:
        for f in ("query_id", "question", "answer", "subgraph", "evidence"):
            check("query.%s.%s" % (f, q.get("query_id")), f in q, "missing field")
        check("query.subgraph.%s" % q.get("query_id"),
              q.get("status") == "undetermined" or bool((q.get("subgraph") or {}).get("nodes"))
              or bool(q.get("answer")), "empty subgraph and empty answer")
    alignment = result.get("alignment") or []
    check("alignment.present", bool(alignment), "no cross-paper alignment record")
    for a in alignment:
        for f in ("concept_a", "concept_b", "decision", "basis"):
            check("alignment.%s" % f, bool(a.get(f)), "missing field")
        check("alignment.decision.enum", a.get("decision") in DECISIONS, "decision=%r" % a.get("decision"))
    check("conflicts.present", "conflicts" in result, "conflicts field missing")
    check("uncertainty.present", "uncertainty" in result, "uncertainty must be stated")
    for name in ("graph.json", "nodes.csv", "edges.csv", "query_results.json"):
        check("artifact.exists.%s" % name, (Path(out_dir) / name).is_file(), "artifact file not found")
    return {"result": "result.json", "pass": not errors, "checks_total": len(checks),
            "checks_failed": len(errors), "errors": errors, "checks": checks}
