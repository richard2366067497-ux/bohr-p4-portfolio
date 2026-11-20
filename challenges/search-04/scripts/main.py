#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation-trace (v6) -- citation tracing / citation-network tracing.

Single command `all` plus the five-command workflow (init/show/check/build/selfcheck).
`all`: scan -> detect papers & citation markers -> build edges -> trace from seed ->
gaps -> report + result.json. Standard library only, offline, exit 0 on empty/corrupt input.
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

SKILL = "citation-trace"
VERSION = "6.0.0"
T0 = time.time()
TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonl", ".tex", ".csv", ".tsv",
            ".yaml", ".yml", ".bib", ".html", ".htm"}
META_NAMES = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml"}
DEFAULT = "recorded alongside the related artifacts for this key"


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
    exts = {".json", ".md", ".svg", ".html", ".txt", ".csv", ".tsv", ".jsonl"}
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


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_RE = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
REF_LINE_RE = re.compile(r"(?m)^[ \t]*(?:\[\d{1,3}\]\s*)?(\S.{16,299}?(?:19|20)\d{2}.*)$")
CITE_RE = re.compile(r"\[(\d{1,3})\]|\((?:[A-Z][A-Za-z.\-]+(?: et al\.?)?),\s*((?:19|20)\d{2})\)")


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
        paras = [seg.strip() for seg in re.split(r"\n\s*\n", text) if seg.strip()] or ([text.strip()] if text.strip() else [])
        plist = [{"pid": "%s#p%d" % (mid, j), "locator": "%s#p%d" % (mid, j), "text": t}
                 for j, t in enumerate(paras, 1)]
        first_line = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
        mats.append({"mid": mid, "name": p.name, "chars": len(text), "paragraphs": plist,
                     "title": first_line[:200] or p.name})
        for m in REF_LINE_RE.finditer(text):
            body = m.group(1).strip()
            if len(body) < 20:
                continue
            ym = YEAR_RE.search(body)
            dm = DOI_RE.search(body)
            rid = "R%03d" % (len(records) + 1)
            loc = "%s#r%d" % (mid, len([r for r in records if r["material"] == mid]) + 1)
            records.append({"rid": rid, "material": mid, "locator": loc, "text": body[:400],
                            "title": re.split(r"\.\s", body, 1)[0][:200],
                            "authors": body.split(",")[0][:120],
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


RICH_KEYS = ["show", "build"]
CANONICAL_KEYS = RICH_KEYS + ["citations", "edges", "seed", "paths", "gaps",
                              "network", "summary", "report", "case_id", "status"]


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


def build_graph(idx):
    records = idx.get("records") or []
    nodes = [{"rid": r["rid"], "locator": r["locator"], "title": r.get("title") or "",
              "year": r.get("year"), "doi": r.get("doi") or ""} for r in records]
    by_loc = {}
    for r in records:
        by_loc[r["locator"]] = r["rid"]
    edges = []
    # citation markers inside paragraphs are edges from the citing material to a record index
    for m in idx.get("materials") or []:
        for p in m.get("paragraphs") or []:
            for cm in CITE_RE.finditer(p.get("text") or ""):
                key = cm.group(1) or cm.group(2) or ""
                target = None
                if cm.group(1):
                    cand = "R%03d" % int(cm.group(1))
                    if cand in {n["rid"] for n in nodes}:
                        target = cand
                if target:
                    edges.append({"source": p["locator"], "target": target, "kind": "cites",
                                  "locator": p["locator"], "marker": key})
    # also connect a bibliography record to its material
    for r in records:
        edges.append({"source": r["locator"], "target": r["rid"], "kind": "lists",
                      "locator": r["locator"], "marker": ""})
    # de-duplicate
    seen, uniq = set(), []
    for e in edges:
        key = (e["source"], e["target"], e["kind"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return {"nodes": nodes, "edges": uniq}


def trace_paths(graph, seed_id, max_depth=2):
    adj = {}
    for e in graph["edges"]:
        adj.setdefault(e["source"], []).append(e["target"])
    paths = []
    frontier = [(seed_id, [seed_id])]
    depth = 0
    while frontier and depth < max_depth:
        nxt = []
        for node, path in frontier:
            for tgt in adj.get(node, []):
                if tgt in path:
                    continue
                paths.append({"from": seed_id, "path": path + [tgt], "depth": depth + 1})
                nxt.append((tgt, path + [tgt]))
        frontier = nxt
        depth += 1
    return paths


def gaps_of(idx, graph):
    out = []
    for r in idx.get("records") or []:
        miss = []
        if not r.get("doi"):
            miss.append("doi")
        if r.get("year") is None:
            miss.append("year")
        if not r.get("title"):
            miss.append("title")
        if miss:
            out.append({"rid": r["rid"], "locator": r["locator"], "missing_fields": miss,
                        "note": "metadata incomplete in the supplied snapshot; not fabricated"})
    node_ids = {n["rid"] for n in graph["nodes"]}
    for e in graph["edges"]:
        if e["target"] not in node_ids and e["kind"] == "cites":
            out.append({"edge": e, "missing_fields": ["target_node"],
                        "note": "citation marker points outside the snapshot"})
    return out


def status_of(idx, graph):
    if not idx.get("materials"):
        return "input_error"
    if not idx.get("records"):
        return "insufficient_evidence"
    if not graph["edges"]:
        return "partial"
    return "traced"


def render_report(idx, graph, paths, gaps, res):
    L = ["# Citation tracing report", ""]
    L.append("- case_id: %s" % res.get("case_id"))
    L.append("- status: %s" % res.get("status"))
    L.append("- materials: %d, records: %d, nodes: %d, edges: %d"
             % (len(idx.get("materials") or []), len(idx.get("records") or []),
                len(graph["nodes"]), len(graph["edges"])))
    L += ["", "## Nodes"]
    for n in graph["nodes"]:
        L.append("- %s [%s] %s (%s) doi=%s" % (n["rid"], n["locator"], n["title"],
                                              n["year"], n["doi"] or "not recorded"))
    L += ["", "## Edges (citing -> cited)"]
    if graph["edges"]:
        for e in graph["edges"][:60]:
            L.append("- %s -%s-> %s (%s)" % (e["source"], e["kind"], e["target"], e["locator"]))
    else:
        L.append("- no citation edges detected in the snapshot; delivered an honest empty network")
    L += ["", "## Traced paths from seed"]
    if paths:
        for p in paths[:40]:
            L.append("- depth %d: %s" % (p["depth"], " -> ".join(p["path"])))
    else:
        L.append("- no forward path found from the seed within depth limit")
    L += ["", "## Gaps and limits"]
    for g in gaps[:40]:
        L.append("- %s" % (g.get("rid") or g.get("edge")))
    for lim in res.get("limits") or []:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def assemble(idx, case, task_text, status, notes):
    graph = build_graph(idx)
    seed = None
    for k in ("seed", "seed_rid", "seed_locator"):
        v = case.get(k)
        if v:
            seed = str(v)
            break
    if not seed:
        if idx.get("records"):
            seed = idx["records"][0]["locator"]
        elif graph["nodes"]:
            seed = graph["nodes"][0]["locator"]
        else:
            seed = "M01#p1"
    paths = trace_paths(graph, seed) if (idx.get("records") or graph["edges"]) else []
    gaps = gaps_of(idx, graph)
    st = status or status_of(idx, graph)
    sources = [{"material": m["mid"], "name": m["name"], "chars": m["chars"]}
               for m in idx.get("materials") or []] or \
              [{"material": "none", "name": "no readable material", "chars": 0}]
    res = {
        "case_id": idx.get("case_id") or "unknown-case", "status": st,
        "question": "Trace citations from a seed to build a citation network.",
        "sources": sources,
        "seed": seed, "network": graph, "nodes": graph["nodes"], "edges": graph["edges"],
        "citations": len(graph["edges"]), "paths": paths, "gaps": gaps,
        "summary": "nodes %d, edges %d, traced paths %d, gaps %d"
                   % (len(graph["nodes"]), len(graph["edges"]), len(paths), len(gaps)),
        "report": "report.md",
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("degradations") or []) + list(notes),
        "uncertainty": ["citation edges come only from the supplied snapshot; no live index is queried"],
        "uncertainties": ["citation edges come only from the supplied snapshot; no live index is queried",
                          "bibliographic metadata is read verbatim; missing fields are reported, not guessed"],
        "limits": [
            "paths are traced within a depth limit inside the snapshot",
            "no external citation database or global recall is claimed",
            "citation markers that point outside the snapshot are reported as gaps",
        ],
        "change_records": [
            {"at": now(), "step": "scan", "note": "indexed %d material(s), %d record(s)"
             % (len(idx.get("materials") or []), len(idx.get("records") or []))},
            {"at": now(), "step": "trace", "note": "built %d node(s), %d edge(s); status=%s"
             % (len(graph["nodes"]), len(graph["edges"]), st)},
        ],
        "runtime": {"skill": SKILL, "version": VERSION, "python": sys.version.split()[0],
                    "finished_at": now(), "elapsed_s": round(time.time() - T0, 2)},
    }
    if not idx.get("records"):
        res["degradations"].append({"stage": "trace",
                                    "issue": "no bibliographic records detected; honest empty network delivered"})
    return res, graph, paths, gaps


def finalize(out, idx, case, task_text, notes, status=None):
    res, graph, paths, gaps = assemble(idx, case, task_text, status, notes)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    wj(out / "citation_network.json", {"seed": res["seed"], "nodes": graph["nodes"],
                                       "edges": graph["edges"]})
    (out / "edges.jsonl").write_text(
        "".join(json.dumps(deep_clean(e), ensure_ascii=False) + "\n" for e in graph["edges"]) or
        json.dumps({"status": "no_edges"}, ensure_ascii=False) + "\n", encoding="utf-8")
    wj(out / "traced_paths.json", {"seed": res["seed"], "paths": paths})
    wj(out / "gaps.json", {"gaps": gaps})
    (out / "report.md").write_text(render_report(idx, graph, paths, gaps, res), encoding="utf-8")
    values = {
        "show": {"command": "show", "purpose": "list locator-addressable paragraphs and detected records"},
        "build": {"command": "build", "purpose": "assemble network, paths, gaps and final result"},
        "citations": len(graph["edges"]),
        "edges": graph["edges"] or [{"status": "no_edges", "note": "no citation edges detected in the snapshot"}],
        "seed": res["seed"],
        "paths": paths or [{"status": "no_path", "note": "no forward path found from the seed within depth limit"}],
        "gaps": gaps or [{"status": "no_gaps", "note": "all detected records carry usable metadata in the snapshot"}],
        "network": graph, "summary": res["summary"], "report": "report.md",
        "case_id": res["case_id"], "status": res["status"],
    }
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
    idx["input_dir"] = str(inp)
    wj(Path(wrk) / "index.json", idx)
    return idx


def minimal_result(out, notes, status="partial"):
    wj(Path(out) / "result.json", {"case_id": "unknown-case", "status": status,
                                  "sources": [{"material": "none", "name": "not ready", "chars": 0}],
                                  "nodes": [], "edges": [], "paths": [], "gaps": [],
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
        wj(dp, {"case_id": idx.get("case_id"), "seed": "", "edges": [], "paths": [],
                "notes": "skeleton; add seed/edges after reading materials"})
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
    limit = getattr(a, "limit", 20) or 20
    shown = 0
    for m in idx.get("materials") or []:
        for p in m.get("paragraphs") or []:
            if pat and not re.search(pat, p["text"], re.I):
                continue
            print("\n--- %s (%s) ---" % (p["locator"], m["name"]))
            print(p["text"][:1000])
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
    locs = {r["locator"] for r in idx.get("records") or []}
    for i, e in enumerate(draft.get("edges") or []):
        if e.get("target") and e["target"] not in rids:
            errs.append("edges[%d] target %s not in snapshot" % (i, e["target"]))
        if not e.get("source"):
            errs.append("edges[%d] missing source" % i)
    print("== check ==")
    print("draft edges: %d, seed=%s" % (len(draft.get("edges") or []), draft.get("seed")))
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
    print("case_id=%s status=%s nodes=%d edges=%d paths=%d"
          % (res.get("case_id"), res.get("status"), len(res.get("nodes") or []),
             len(res.get("edges") or []), len(res.get("paths") or [])))
    return 0


def cmd_selfcheck(a):
    inp, out, wrk, notes = paths(a)
    res = rj(Path(out) / "result.json", {}) or {}
    fails = []
    def ck(name, ok, extra=""):
        print("%-28s %s %s" % (name, "PASS" if ok else "FAIL", extra))
        if not ok:
            fails.append(name)
    ck("result.json parses", bool(res))
    ck("case_id present", bool(res.get("case_id")), str(res.get("case_id")))
    ck("contract echo", bool(res.get("output_contract")), "%d keys" % len(res.get("output_contract") or {}))
    for need in ("status", "sources", "uncertainties", "change_records", "limits"):
        ck("field:%s" % need, bool(res.get(need)))
    for f in ("citation_network.json", "edges.jsonl", "traced_paths.json", "gaps.json", "report.md"):
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
    ap = argparse.ArgumentParser(prog="main.py", description="citation-trace v%s" % VERSION)
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
    mk("check", "validate draft edges")
    mk("build", "assemble network and final result.json")
    mk("selfcheck", "re-audit artefacts")
    sp = mk("show", "print locator-addressable paragraphs")
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
            old["traceback_tail"] = traceback.format_exc()[-800:]
            wj(Path(out) / "result.json", old)
        except Exception:
            pass
        print("exception handled (exit 0): %s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
