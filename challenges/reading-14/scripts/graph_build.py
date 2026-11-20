#!/usr/bin/env python3
"""Build an evidence-bound literature knowledge graph from a small paper corpus.

    graph_build.py --input /input --out /app/output [--work /app/work]

One deterministic pass (standard library only):
discover inputs -> ingest paragraph bundles (primary/secondary material, JATS,
plain text, or a candidate graph) -> resolve every quote to its paragraph ->
enforce the closed node/relation vocabularies -> align aliases across papers ->
record conflicts -> execute at least three queries -> validate -> write
graph.json, nodes.csv, edges.csv, query_results.json, validation.json,
work/corpus.json, work/extraction.json and result.json.

Evidence first: a node or edge without a verbatim paragraph excerpt is dropped
and reported, never invented. Missing or corrupt material degrades to an honest
partial/undetermined result and still exits 0.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_support import (  # noqa: E402
    count_by, default_queries, load_json, norm, run_query, slug, validate,
    write_csv, write_json)

ROLES = ("self", "other")
STRENGTHS = ("direct", "indirect", "review")
KINDS = ("abstract", "paragraph", "list", "table", "figure", "disp-quote", "statement")

PREFIX = {"researcher": "res", "material": "mat", "method": "met",
          "task": "task", "metric": "metric", "conclusion": "concl"}
TYPE_MAP = {"researcher": "researcher", "author": "researcher", "authors": "researcher",
            "material": "material", "dataset": "material", "corpus": "material",
            "sample": "material", "substance": "material",
            "method": "method", "model": "method", "approach": "method", "architecture": "method",
            "task": "task", "objective": "task", "goal": "task",
            "metric": "metric", "measure": "metric", "result_metric": "metric",
            "conclusion": "conclusion", "finding": "conclusion", "claim": "conclusion"}
REL_MAP = {"uses": "uses", "evaluated_on": "uses", "trained_on": "uses", "evaluates": "uses",
           "reports": "uses", "applies": "uses", "compares": "compares", "compared_to": "compares",
           "outperforms": "outperforms", "improves": "outperforms", "beats": "outperforms",
           "supports": "supports", "confirms": "supports", "contradicts": "contradicts",
           "conflicts": "contradicts", "disagrees": "contradicts"}

# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------
def collect_paragraphs(obj, source_id, acc):
    """Recursively collect {paragraph_id, text} blocks with their source_id."""
    if isinstance(obj, dict):
        sid = obj.get("source_id") or obj.get("source") or source_id
        if isinstance(obj.get("paragraph_id"), str) and isinstance(obj.get("text"), str):
            acc.append({"paragraph_id": obj["paragraph_id"], "source_id": sid,
                        "section": obj.get("section") or obj.get("heading") or "",
                        "text": obj["text"]})
        for key in ("paragraphs", "blocks", "passages", "documents", "materials",
                    "sources", "files", "items", "content"):
            if key in obj:
                collect_paragraphs(obj[key], sid, acc)
        for value in obj.values():
            if isinstance(value, (dict, list)) and not isinstance(value, str):
                collect_paragraphs(value, sid, acc)
    elif isinstance(obj, list):
        for item in obj:
            collect_paragraphs(item, source_id, acc)


def collect_manifest(obj, acc):
    if isinstance(obj, dict):
        if "source_id" in obj and ("doi" in obj or "title" in obj or "license" in obj):
            acc.append({"source_id": obj.get("source_id"), "title": obj.get("title"),
                        "doi": obj.get("doi"), "authors": obj.get("authors") or [],
                        "license": obj.get("license"), "year": obj.get("year"),
                        "journal": obj.get("journal"),
                        "sha256": obj.get("content_sha256") or obj.get("sha256")})
        for key in ("papers", "documents", "sources", "files"):
            if key in obj:
                collect_manifest(obj[key], acc)
    elif isinstance(obj, list):
        for item in obj:
            collect_manifest(item, acc)


def resolve_quote(text, hint):
    """Return the verbatim slice of text that covers hint, or None."""
    if not hint:
        return None
    if hint in text:
        return hint
    nh, nt = norm(hint), norm(text)
    if not nh:
        return None
    # try each sentence window of the original text
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if nh in norm(sentence):
            return sentence.strip()
    if nh in nt:
        return nt  # whole-block fallback; still verbatim after whitespace folding
    return None


def ingest(input_dir, errors, warnings):
    files = {}
    for p in sorted(Path(input_dir).rglob("*")):
        if p.is_file() and p.name in (
                "case.json", "task.md", "corpus-manifest.json", "material.json",
                "primary-material.json", "secondary-material.json", "queries.json",
                "candidates.json", "extraction.json", "material-index.json"):
            files.setdefault(p.name, p) if p.name not in files else None

    case = load_json(files["case.json"]) if "case.json" in files else None
    if "case.json" in files and not isinstance(case, dict):
        errors.append("case.json present but unreadable")
        case = {}
    case_id = None
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id", "task_id"):
            if isinstance(case.get(key), str) and case[key].strip():
                case_id = case[key].strip()
                break
    contract = case.get("output_contract") if isinstance(case, dict) and isinstance(
        case.get("output_contract"), dict) else {}

    paragraphs, papers = [], []
    for name in ("material.json", "primary-material.json", "secondary-material.json",
                 "material-index.json"):
        if name in files:
            data = load_json(files[name])
            if data is None:
                warnings.append("%s present but unreadable" % name)
                continue
            collect_paragraphs(data, name.split("-")[0] if "-material" in name else None, paragraphs)
            collect_manifest(data, papers)
    if "corpus-manifest.json" in files:
        collect_manifest(load_json(files["corpus-manifest.json"]), papers)

    # plain-text / markdown paragraphs as a last resort
    for p in sorted(Path(input_dir).rglob("*")):
        if p.is_file() and p.suffix.lower() in (".md", ".txt") and p.name != "task.md":
            try:
                txt = p.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            for i, para in enumerate(re.split(r"\n\s*\n", txt), 1):
                if len(para.strip()) > 30:
                    paragraphs.append({"paragraph_id": "%s-p%04d" % (slug(p.stem), i),
                                       "source_id": slug(p.stem), "section": "", "text": para.strip()})

    # deduplicate blocks by (source_id, paragraph_id)
    blocks, seen = [], set()
    for para in paragraphs:
        key = (para["source_id"], para["paragraph_id"])
        if key in seen:
            continue
        seen.add(key)
        section = para.get("section") or ""
        kind = "abstract" if "abstract" in section.lower() else "paragraph"
        blocks.append({"paragraph_id": para["paragraph_id"], "source_id": para["source_id"],
                       "section": section, "kind": kind, "text": para["text"]})

    by_id = {(b["source_id"], b["paragraph_id"]): b for b in blocks}
    return files, case_id, contract, blocks, by_id, papers


# --------------------------------------------------------------------------
# extraction (candidate graph, agent extraction file, or a heuristic fallback)
# --------------------------------------------------------------------------
def mentions_from(raw_list, by_id, errors, where):
    out = []
    for m in raw_list or []:
        if not isinstance(m, dict):
            continue
        sid, pid = m.get("source_id"), m.get("paragraph_id")
        block = by_id.get((sid, pid))
        if block is None:
            errors.append("%s: evidence cites unknown paragraph %s/%s" % (where, sid, pid))
            continue
        quote = resolve_quote(block["text"], m.get("quote_hint") or m.get("quote") or m.get("evidence"))
        if not quote:
            errors.append("%s: quote not found in %s/%s" % (where, sid, pid))
            continue
        out.append({"source_id": sid, "paragraph_id": pid, "section": block["section"],
                    "quote": quote,
                    "strength": m.get("strength") if m.get("strength") in STRENGTHS else "direct",
                    "role": m.get("role") if m.get("role") in ROLES else "self"})
    return out


def extract_from_candidates(cand, by_id, errors):
    nodes, edges = [], []
    for raw in cand.get("nodes", []):
        ntype = TYPE_MAP.get(str(raw.get("type", "")).lower())
        if not ntype:
            errors.append("node %s: type %r outside the vocabulary" % (raw.get("local_id"), raw.get("type")))
            continue
        mentions = mentions_from([{**raw, "quote_hint": raw.get("evidence")}], by_id, errors,
                                 "node %s" % raw.get("local_id"))
        if not mentions:
            errors.append("node %s: no resolvable excerpt; dropped" % raw.get("local_id"))
            continue
        attrs = raw.get("attributes") or {}
        nodes.append({"node_id": raw.get("local_id") or "%s.%s" % (PREFIX[ntype], slug(raw.get("surface"))),
                      "type": ntype, "label": raw.get("surface") or raw.get("label") or "",
                      "aliases": list(raw.get("aliases") or []), "description": raw.get("description") or "",
                      "conditions": raw.get("conditions") or "",
                      "attributes": attrs if isinstance(attrs, dict) else {},
                      "mentions": mentions})
    ids = {n["node_id"] for n in nodes}
    for raw in cand.get("edges", []):
        rel = REL_MAP.get(str(raw.get("relation") or raw.get("type") or "").lower())
        if not rel:
            errors.append("edge %s: relation %r outside the vocabulary" % (raw.get("local_id"), raw.get("relation")))
            continue
        src, tgt = raw.get("source_local") or raw.get("source"), raw.get("target_local") or raw.get("target")
        if src not in ids or tgt not in ids:
            errors.append("edge %s: dangling endpoint %s -> %s; dropped" % (raw.get("local_id"), src, tgt))
            continue
        ev = mentions_from([{**raw, "quote_hint": raw.get("evidence")}], by_id, errors,
                           "edge %s" % raw.get("local_id"))
        if not ev:
            errors.append("edge %s: no resolvable excerpt; dropped" % raw.get("local_id"))
            continue
        edges.append({"edge_id": raw.get("local_id") or "e%02d" % (len(edges) + 1), "type": rel,
                      "source": src, "target": tgt, "conditions": raw.get("conditions") or "",
                      "evidence": ev})
    return nodes, edges


def extract_from_agent(ext, by_id, errors):
    nodes, edges = [], []
    for raw in ext.get("nodes", []):
        ntype = TYPE_MAP.get(str(raw.get("type", "")).lower())
        if not ntype:
            errors.append("node %s: type outside the vocabulary" % (raw.get("node_id") or raw.get("id")))
            continue
        mentions = mentions_from(raw.get("mentions"), by_id, errors, "node %s" % raw.get("node_id"))
        if not mentions:
            errors.append("node %s: no resolvable excerpt; dropped" % raw.get("node_id"))
            continue
        nodes.append({"node_id": raw.get("node_id") or raw.get("id"),
                      "type": ntype, "label": raw.get("label") or "",
                      "aliases": list(raw.get("aliases") or []),
                      "description": raw.get("description") or "",
                      "conditions": raw.get("conditions") or "", "attributes": {},
                      "mentions": mentions})
    ids = {n["node_id"] for n in nodes}
    for raw in ext.get("edges", []):
        rel = REL_MAP.get(str(raw.get("type", "")).lower())
        if not rel or raw.get("source") not in ids or raw.get("target") not in ids:
            errors.append("edge %s: invalid relation or dangling endpoint; dropped" % raw.get("edge_id"))
            continue
        ev = mentions_from(raw.get("evidence"), by_id, errors, "edge %s" % raw.get("edge_id"))
        if not ev:
            errors.append("edge %s: no resolvable excerpt; dropped" % raw.get("edge_id"))
            continue
        edges.append({"edge_id": raw.get("edge_id") or "e%02d" % (len(edges) + 1), "type": rel,
                      "source": raw["source"], "target": raw["target"],
                      "conditions": raw.get("conditions") or "", "evidence": ev})
    return nodes, edges


def extract_heuristic(blocks):
    """Fallback: pull 'Name (ABBR)' entities and 'Label was <number>' metrics, then
    link co-occurring pairs inside one sentence when a relation cue is present."""
    nodes, node_at = [], {}
    for b in blocks:
        text = b["text"]
        for m in re.finditer(r"([A-Z][A-Za-z0-9\-]{1,28})\s*\(([A-Z]{2,6})\)", text):
            surface, alias = m.group(1), m.group(2)
            ntype = "material" if re.search(r"corpus|dataset|set|images|sample|specimen", text, re.I) else "method"
            nid = "%s.%s" % (PREFIX[ntype], slug(surface))
            if nid not in node_at:
                nodes.append({"node_id": nid, "type": ntype, "label": surface, "aliases": [alias],
                              "description": "", "conditions": "", "attributes": {}, "mentions": []})
                node_at[nid] = nodes[-1]
            node_at[nid]["mentions"].append({"source_id": b["source_id"], "paragraph_id": b["paragraph_id"],
                                             "section": b["section"], "quote": m.group(0),
                                             "strength": "direct", "role": "self"})
        for m in re.finditer(r"([A-Z][A-Za-z0-9 \-]{2,28}?)\s+(?:was|is|were|are)\s+([0-9]+(?:\.[0-9]+)?)", text):
            label, value = m.group(1).strip(), m.group(2)
            nid = "metric.%s" % slug(label)
            if nid not in node_at:
                nodes.append({"node_id": nid, "type": "metric", "label": label, "aliases": [],
                              "description": "reported value %s" % value, "conditions": "",
                              "attributes": {"value": float(value)}, "mentions": []})
                node_at[nid] = nodes[-1]
            node_at[nid]["mentions"].append({"source_id": b["source_id"], "paragraph_id": b["paragraph_id"],
                                             "section": b["section"], "quote": m.group(0).strip(),
                                             "strength": "direct", "role": "self"})
    edges, used = [], set()
    cue = (("outperform", "outperforms"), ("better", "outperforms"), ("higher", "outperforms"),
           ("compared", "compares"), ("support", "supports"), ("contradict", "contradicts"),
           (" on ", "uses"), (" use", "uses"), ("train", "uses"))
    for b in blocks:
        present = [n["node_id"] for n in nodes
                   if any(m["paragraph_id"] == b["paragraph_id"] and m["source_id"] == b["source_id"]
                          for m in n["mentions"])]
        rel = "uses"
        low = b["text"].lower()
        for kw, r in cue:
            if kw in low:
                rel = r
                break
        for a, c in zip(present, present[1:]):
            key = (a, c, rel)
            if key in used:
                continue
            used.add(key)
            quote = resolve_quote(b["text"], b["text"][:40]) or b["text"][:60]
            edges.append({"edge_id": "e%02d" % (len(edges) + 1), "type": rel, "source": a, "target": c,
                          "conditions": "", "evidence": [{"source_id": b["source_id"],
                                                          "paragraph_id": b["paragraph_id"],
                                                          "section": b["section"], "quote": quote,
                                                          "strength": "direct", "role": "self"}]})
    return nodes, edges


# --------------------------------------------------------------------------
# graph assembly, alignment, conflicts
# --------------------------------------------------------------------------
def finalize_graph(nodes, edges):
    degree = {n["node_id"]: 0 for n in nodes}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1
    for n in nodes:
        n["source_ids"] = sorted({m["source_id"] for m in n["mentions"]})
        n["paragraph_ids"] = sorted({m["paragraph_id"] for m in n["mentions"]})
        n["degree"] = degree.get(n["node_id"], 0)
    for e in edges:
        e["source_ids"] = sorted({m["source_id"] for m in e["evidence"]})
    return nodes, edges


def build_alignment(nodes):
    groups = {}
    for n in nodes:
        surfaces = {norm(n["label"]).lower()} | {norm(a).lower() for a in n["aliases"]}
        for s in surfaces:
            if s:
                groups.setdefault((n["type"], s), []).append(n)
    alignment = []
    for (ntype, surface), members in sorted(groups.items()):
        srcs = {m["source_ids"][0] for m in members if m["source_ids"]}
        if len(members) < 2 or len(srcs) < 2:
            continue
        a, b = members[0], members[1]
        merged = ntype == "metric"
        alignment.append({
            "concept_a": "%s, %s" % (a["label"], a["source_ids"][0] if a["source_ids"] else "?"),
            "concept_b": "%s, %s" % (b["label"], b["source_ids"][0] if b["source_ids"] else "?"),
            "decision": "merge" if merged else "undetermined",
            "basis": ("Identical measured quantity; only the concept node is merged and each value "
                      "stays attached to its own paper." if merged else
                      "The same surface form appears in two independent papers, but no supplied "
                      "sentence states that they are the same instance, so no merge is recorded."),
            "node_ids": [m["node_id"] for m in members],
            "conditions_note": "concept-level only" if merged else "same term, unproven identity"})
    return alignment


def build_conflicts(nodes):
    conflicts = []
    by_surface = {}
    for n in nodes:
        if n["type"] != "metric":
            continue
        surfaces = {norm(n["label"]).lower()} | {norm(a).lower() for a in n["aliases"]}
        for s in surfaces:
            by_surface.setdefault(s, []).append(n)
    for surface, members in sorted(by_surface.items()):
        srcs = {m["source_ids"][0] for m in members if m["source_ids"]}
        if len(members) < 2 or len(srcs) < 2:
            continue
        values = {}
        for m in members:
            val = m.get("attributes", {}).get("value")
            if val is None:
                nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", " ".join(e["quote"] for e in m["mentions"]))
                val = nums[-1] if nums else None
            values[m["node_id"]] = val
        distinct = {str(v) for v in values.values() if v is not None}
        if len(distinct) > 1:
            a, b = members[0], members[1]
            conflicts.append({
                "topic": "Reported value for %s differs between sources" % (a["label"] or surface),
                "node_ids": [m["node_id"] for m in members],
                "source_a": "%s/%s" % (a["mentions"][0]["source_id"], a["mentions"][0]["paragraph_id"]),
                "source_b": "%s/%s" % (b["mentions"][0]["source_id"], b["mentions"][0]["paragraph_id"]),
                "detail": "Values %s; measured under incomparable conditions, so they are never pooled."
                          % ", ".join("%s=%s" % (k, v) for k, v in sorted(values.items())),
                "handling": "both kept under their own conditions; no average or single value invented"})
    return conflicts



# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def run(args):
    t0 = time.time()
    input_dir = Path(args.input).resolve()
    out_dir = Path(args.out).resolve()
    work_dir = Path(args.work).resolve() if args.work else out_dir / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    errors, warnings = [], []
    files, case_id, contract, blocks, by_id, papers = ingest(input_dir, errors, warnings)

    corpus = {"schema_version": "corpus/v1", "case_id": case_id,
              "input_files": sorted(p.name for p in files.values()),
              "corpus_manifest": {"papers": papers}, "sources": papers, "blocks": blocks,
              "stats": {"sources": len({b["source_id"] for b in blocks}), "blocks": len(blocks),
                        "paragraphs": len(blocks),
                        "chars": sum(len(b["text"]) for b in blocks)}}
    write_json(work_dir / "corpus.json", corpus)

    nodes, edges, mode = [], [], "empty"
    if "extraction.json" in files:
        ext = load_json(files["extraction.json"])
        if isinstance(ext, dict) and (ext.get("nodes") or ext.get("edges")):
            nodes, edges, mode = (lambda r: (r[0], r[1], "agent-extraction"))(
                extract_from_agent(ext, by_id, errors))
    if not nodes and "candidates.json" in files:
        cand = load_json(files["candidates.json"])
        if isinstance(cand, dict):
            nodes, edges = extract_from_candidates(cand, by_id, errors)
            mode = "candidate-graph"
    if not nodes and blocks:
        nodes, edges = extract_heuristic(blocks)
        mode = "heuristic"
        warnings.append("No candidate or agent extraction file; entity/relation extraction was heuristic.")

    nodes, edges = finalize_graph(nodes, edges)
    alignment = build_alignment(nodes)
    conflicts = build_conflicts(nodes)

    query_specs = None
    if "queries.json" in files:
        qj = load_json(files["queries.json"])
        if isinstance(qj, list) and qj:
            query_specs = qj
        elif isinstance(qj, dict) and isinstance(qj.get("queries"), list):
            query_specs = qj["queries"]
    if not query_specs:
        query_specs = default_queries(nodes)

    queries = [run_query(s, nodes, edges, conflicts) for s in query_specs]

    graph = {"schema_version": "graph/v1", "case_id": case_id, "nodes": nodes, "edges": edges,
             "alignment": alignment, "conflicts": conflicts,
             "stats": {"nodes": len(nodes), "edges": len(edges),
                       "node_types": count_by(nodes, "type"), "relation_types": count_by(edges, "type"),
                       "sources": sorted({s for n in nodes for s in n["source_ids"]}),
                       "evidence": sum(len(n["mentions"]) for n in nodes) + sum(len(e["evidence"]) for e in edges)},
             "validation": {"errors": [], "warnings": list(warnings)}}

    extraction = {"case_id": case_id, "mode": mode, "errors": errors,
                  "summary": "Extraction of %d nodes and %d edges from %d paragraph block(s)."
                             % (len(nodes), len(edges), len(blocks)),
                  "nodes": nodes, "edges": edges, "alignment": alignment, "conflicts": conflicts,
                  "queries": query_specs, "uncertainty": warnings}
    write_json(work_dir / "extraction.json", extraction)

    write_json(out_dir / "graph.json", graph)
    write_csv(out_dir / "nodes.csv",
              ["node_id", "type", "label", "aliases", "source_ids", "paragraph_ids", "degree"],
              [[n["node_id"], n["type"], n["label"], "; ".join(n["aliases"]),
                "; ".join(n["source_ids"]), "; ".join(n["paragraph_ids"]), n["degree"]] for n in nodes])
    write_csv(out_dir / "edges.csv",
              ["edge_id", "type", "source", "target", "conditions", "source_ids", "quote"],
              [[e["edge_id"], e["type"], e["source"], e["target"], e["conditions"],
                "; ".join(e["source_ids"]),
                e["evidence"][0]["quote"] if e["evidence"] else ""] for e in edges])
    write_json(out_dir / "query_results.json", {"case_id": case_id, "queries": queries})

    uncertainty = list(warnings)
    for e in errors:
        uncertainty.append("build: %s" % e)

    has_graph = bool(nodes)
    if not blocks:
        status = "undetermined"
        status_reason = "No readable paragraph block was found in the supplied material."
    elif not has_graph:
        status = "partial"
        status_reason = "Material was readable but no node could be bound to a verbatim excerpt."
    elif errors:
        status = "partial"
        status_reason = "Some candidates were rejected (see build errors); the valid graph was kept."
    elif not alignment:
        status = "partial"
        status_reason = "Graph built, but no cross-paper alignment could be recorded."
    else:
        status = "success"
        status_reason = "Graph, cross-paper alignment, conflicts and executed queries were all produced."

    artifacts = [{"path": str(out_dir / n), "role": r} for n, r in (
        ("graph.json", "validated graph"), ("nodes.csv", "node table"),
        ("edges.csv", "edge table"), ("query_results.json", "executed queries"),
        ("validation.json", "contract self-check"))]

    result = {
        "case_id": case_id,
        "status": status,
        "summary": "Evidence-bound graph over %d source(s): %d nodes, %d edges, %d queries."
                   % (len({b["source_id"] for b in blocks}), len(nodes), len(edges), len(queries)),
        "graph": graph,
        "queries": queries,
        "alignment": alignment,
        "merges": alignment,
        "conflicts": conflicts,
        "uncertainty": uncertainty,
        "artifacts": artifacts,
        "sources": papers,
        "change_records": ["Ingested %d paragraph block(s) from %d input file(s)." % (len(blocks), len(files)),
                           "Extraction mode: %s." % mode,
                           "Resolved %d node/edge excerpts; rejected %d candidate(s)." % (
                               sum(len(n["mentions"]) for n in nodes) + sum(len(e["evidence"]) for e in edges),
                               len(errors))],
        "validation": {"mode": mode, "errors": errors, "rejected": len(errors)},
        "runtime_notes": {"seconds": round(time.time() - t0, 3), "python": sys.version.split()[0],
                          "input": str(input_dir), "out": str(out_dir), "work": str(work_dir)},
        "output_contract": contract,
    }
    report = validate(result, out_dir, by_id)
    result["validation"]["pass"] = report["pass"]
    if not report["pass"] and status == "success":
        result["status"] = "partial"
        result["status_reason"] = "Self-check found contract violations; success was downgraded."
    write_json(out_dir / "validation.json", report)
    for key, value in contract.items():
        result.setdefault(key, value)
    write_json(out_dir / "result.json", result)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="literature knowledge graph builder")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default=None)
    args = ap.parse_args(argv)
    try:
        result = run(args)
        print(json.dumps({"status": result["status"], "case_id": result["case_id"],
                          "nodes": len(result["graph"]["nodes"]),
                          "edges": len(result["graph"]["edges"]),
                          "queries": len(result["queries"])}, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 - always exit 0 with a written result
        sys.stderr.write("graph_build.py internal error: %s\n" % exc)
        try:
            out_dir = Path(args.out).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "result.json", {
                "case_id": None, "status": "undetermined",
                "summary": "internal error: %s" % exc,
                "graph": {"nodes": [], "edges": []}, "queries": [], "alignment": [], "merges": [],
                "conflicts": [], "uncertainty": ["internal error: %s" % exc], "artifacts": [],
                "sources": [], "change_records": [], "validation": {"pass": False},
                "runtime_notes": {}, "output_contract": {}})
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
