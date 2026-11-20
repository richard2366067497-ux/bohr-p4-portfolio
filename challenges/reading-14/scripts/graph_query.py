#!/usr/bin/env python3
"""Answer one question against a graph.json produced by graph_build.py.

    graph_query.py --graph /app/output/graph.json --type outgoing --surface WideNet
    graph_query.py --graph /app/output/graph.json --queries /input/queries.json

This is a convenience wrapper; the required entry command
(`graph_build.py --input /input --out /app/output`) already executes every
query in the input bundle. Standard library only; exits 0 even on a miss.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_support as gs  # noqa: E402


def execute(graph, spec):
    return gs.run_query(spec, graph.get("nodes", []), graph.get("edges", []),
                        graph.get("conflicts", []))


def main(argv=None):
    ap = argparse.ArgumentParser(description="query an evidence graph")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--queries", default=None, help="JSON file with a list of query specs")
    ap.add_argument("--type", default="outgoing")
    ap.add_argument("--surface", default="")
    ap.add_argument("--depth", type=int, default=1)
    args = ap.parse_args(argv)

    graph = gs.load_json(args.graph) if Path(args.graph).is_file() else None
    if not isinstance(graph, dict):
        print(json.dumps({"status": "undetermined", "reason": "graph.json not readable"},
                         ensure_ascii=False))
        return 0

    if args.queries:
        bundle = gs.load_json(args.queries)
        specs = bundle if isinstance(bundle, list) else (bundle or {}).get("queries", [])
    else:
        specs = [{"query_id": "cli", "type": args.type, "surface": args.surface,
                  "depth": args.depth, "question": "%s %s" % (args.type, args.surface)}]

    out = {"queries": [execute(graph, s) for s in specs]}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
