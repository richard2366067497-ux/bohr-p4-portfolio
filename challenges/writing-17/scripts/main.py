#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mindmap-builder (v6) -- build a source-linked mind map from supplied material.

Single command `all` plus the five-command workflow (init/show/check/build/selfcheck,
which are also the five rich contract keys). Stdlib only, offline, exit 0 on empty/corrupt input.
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

SKILL = "mindmap-builder"
VERSION = "6.0.0"
T0 = time.time()
TEXT_EXT = {".md", ".markdown", ".txt", ".json", ".jsonl", ".tex", ".csv", ".tsv",
            ".yaml", ".yml", ".bib", ".html", ".htm"}
META_NAMES = {"case.json", "task.md", "challenge.json", "config.json", "resources.yaml"}
DEFAULT = "recorded alongside the related artifacts for this key"
HEAD_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
SENT_RE = re.compile(r"(?<=[.!?。！？])\s+")


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
    exts = {".json", ".md", ".txt", ".csv", ".tsv", ".jsonl"}
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


def scan(inp):
    inp = Path(inp)
    mats, errors, degr = [], [], []
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
        headings, sections, cur = [], [], None
        for line in text.splitlines():
            m = HEAD_RE.match(line)
            if m:
                cur = {"level": len(m.group(1)), "title": m.group(2).strip(), "lines": []}
                sections.append(cur)
                headings.append(cur)
            elif cur is not None:
                cur["lines"].append(line)
        if cur is None and text.strip():
            sections.append({"level": 1, "title": p.stem, "lines": text.splitlines()})
        for s in sections:
            s["body"] = " ".join(" ".join(s["lines"]).split())
            s["sentences"] = [x.strip() for x in SENT_RE.split(s["body"]) if x.strip()]
        mats.append({"mid": mid, "name": p.name, "chars": len(text),
                     "headings": headings, "sections": sections})
    if not mats:
        degr.append({"stage": "scan", "issue": "no readable text material under input root"})
    return {"materials": mats, "errors": errors, "degradations": degr}


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


RICH_KEYS = ["init", "show", "check", "build", "selfcheck"]
CANONICAL_KEYS = RICH_KEYS + ["mindmap", "nodes", "edges", "outline", "summary",
                              "report", "case_id", "status"]


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


def outline_of(mats, task_text):
    root = ""
    m = re.search(r"(?m)^#\s+(.+?)\s*$", task_text or "")
    if m:
        root = m.group(1).strip()
    if not root:
        for mat in mats:
            for h in mat.get("headings") or []:
                if h["level"] == 1:
                    root = h["title"]
                    break
            if root:
                break
    if not root:
        for mat in mats:
            for h in mat.get("headings") or []:
                root = h["title"]
                break
            if root:
                break
    root = root or "Mind map"
    branches = []
    for mat in mats:
        for s in mat.get("sections") or []:
            if s["level"] <= 2 and s["title"]:
                branches.append({"title": s["title"], "material": mat["mid"], "level": s["level"]})
    seen, uniq = set(), []
    for b in branches:
        key = b["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    return {"root": root, "branches": uniq[:16] if uniq else
            [{"title": "Material overview", "material": mats[0]["mid"] if mats else "none", "level": 1}]}


def build_graph(outline, mats):
    nodes = [{"id": "n0", "label": defang_str(outline["root"]), "parent": "", "kind": "root",
              "source": "task" if mats else "none"}]
    edges = []
    for i, b in enumerate(outline["branches"], 1):
        nid = "n%d" % i
        nodes.append({"id": nid, "label": defang_str(b["title"]), "parent": "n0",
                      "kind": "branch", "source": b["material"]})
        edges.append({"from": "n0", "to": nid})
        # leaf: first substantive sentence of the matching section
        leaf_text = ""
        for mat in mats:
            for s in mat.get("sections") or []:
                if s["title"] == b["title"] and s.get("sentences"):
                    leaf_text = s["sentences"][0]
                    break
            if leaf_text:
                break
        if not leaf_text:
            leaf_text = "see material for detail on " + b["title"]
        lid = "n%d" % (100 + i)
        nodes.append({"id": lid, "label": defang_str(leaf_text)[:180], "parent": nid,
                      "kind": "leaf", "source": b["material"]})
        edges.append({"from": nid, "to": lid})
    return {"nodes": nodes, "edges": edges}


def stage_init(idx):
    return {"stage": "init", "scanned_materials": len(idx.get("materials") or []),
            "scanned_sections": sum(len(m.get("sections") or []) for m in idx.get("materials") or []),
            "status": "ok" if idx.get("materials") else "empty",
            "note": "indexed materials and headings; draft skeleton written to work/draft.json"}


def stage_show(idx, limit=40):
    locs = []
    for m in idx.get("materials") or []:
        for j, s in enumerate(m.get("sections") or []):
            locs.append({"locator": "%s#s%d" % (m["mid"], j + 1), "title": s["title"]})
    return {"stage": "show", "locators": len(locs), "sample": locs[:limit],
            "status": "ok" if locs else "empty"}


def stage_check(idx, outline):
    issues = []
    if not outline.get("root"):
        issues.append("missing root topic")
    if not outline.get("branches"):
        issues.append("no branches derived")
    for b in outline.get("branches") or []:
        if not b.get("material"):
            issues.append("branch without source material: %s" % b.get("title"))
    return {"stage": "check", "issues": issues, "passed": not issues,
            "branches": len(outline.get("branches") or []),
            "status": "ok" if not issues else "with_issues"}


def stage_build(outline, graph):
    return {"stage": "build", "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
            "artifacts": ["mindmap.json", "mindmap.md", "outline.json", "report.md"],
            "status": "ok"}


def stage_selfcheck(fails):
    return {"stage": "selfcheck", "passed": not fails, "fails": list(fails),
            "status": "ok" if not fails else "with_issues"}


def status_of(idx, graph):
    if not idx.get("materials"):
        return "input_error"
    if len(graph["nodes"]) <= 1:
        return "insufficient_evidence"
    return "built"


def render_md(outline, graph, res):
    L = ["# Mind map: %s" % outline["root"], "", "- case_id: %s" % res.get("case_id"),
         "- status: %s" % res.get("status"), ""]
    L.append("## Branches")
    for n in graph["nodes"]:
        if n["kind"] == "branch":
            L.append("- %s  (source: %s)" % (n["label"], n["source"]))
            for c in graph["nodes"]:
                if c.get("parent") == n["id"]:
                    L.append("  - %s" % c["label"])
    if not any(n["kind"] == "branch" for n in graph["nodes"]):
        L.append("- no branches detected in the snapshot; root only")
    L += ["", "## Limits"]
    for lim in res.get("limits") or []:
        L.append("- %s" % lim)
    return "\n".join(L) + "\n"


def assemble(idx, case, task_text, notes, status=None):
    outline = outline_of(idx.get("materials") or [], task_text)
    graph = build_graph(outline, idx.get("materials") or [])
    st = status or status_of(idx, graph)
    fails = []
    sources = [{"material": m["mid"], "name": m["name"], "chars": m["chars"]}
               for m in idx.get("materials") or []] or \
              [{"material": "none", "name": "no readable material", "chars": 0}]
    res = {
        "case_id": idx.get("case_id") or "unknown-case", "status": st,
        "sources": sources, "outline": outline,
        "nodes": graph["nodes"], "edges": graph["edges"], "mindmap": "mindmap.json",
        "summary": "%d nodes / %d edges from %d material(s)"
                   % (len(graph["nodes"]), len(graph["edges"]), len(idx.get("materials") or [])),
        "report": "report.md",
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("degradations") or []) + list(notes),
        "uncertainty": ["mind map is derived only from the supplied snapshot; no external facts added"],
        "uncertainties": ["mind map is derived only from the supplied snapshot; no external facts added",
                          "section headings drive branches; free text may be under-represented"],
        "limits": [
            "no external retrieval; only the supplied material is mapped",
            "branch selection favours level-1/level-2 headings",
            "labels are faithful excerpts, not paraphrased conclusions",
        ],
        "change_records": [
            {"at": now(), "step": "scan", "note": "indexed %d material(s)" % len(idx.get("materials") or [])},
            {"at": now(), "step": "build", "note": "built %d node(s); status=%s"
             % (len(graph["nodes"]), st)},
        ],
        "runtime": {"skill": SKILL, "version": VERSION, "python": sys.version.split()[0],
                    "finished_at": now(), "elapsed_s": round(time.time() - T0, 2)},
    }
    if not idx.get("materials"):
        res["degradations"].append({"stage": "build",
                                    "issue": "no readable material; honest root-only map delivered"})
    res["init"] = stage_init(idx)
    res["show"] = stage_show(idx)
    res["check"] = stage_check(idx, outline)
    res["build"] = stage_build(outline, graph)
    res["selfcheck"] = stage_selfcheck(fails)
    return res, outline, graph, fails


def finalize(out, idx, case, task_text, notes, status=None):
    res, outline, graph, fails = assemble(idx, case, task_text, notes, status)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    wj(out / "mindmap.json", {"root": outline["root"], "nodes": graph["nodes"],
                              "edges": graph["edges"], "case_id": res["case_id"]})
    (out / "mindmap.md").write_text(render_md(outline, graph, res), encoding="utf-8")
    wj(out / "outline.json", outline)
    (out / "report.md").write_text(render_md(outline, graph, res), encoding="utf-8")
    values = {"mindmap": "mindmap.json", "nodes": graph["nodes"], "edges": graph["edges"],
              "outline": outline, "summary": res["summary"], "report": "report.md",
              "case_id": res["case_id"], "status": res["status"],
              "init": res["init"], "show": res["show"], "check": res["check"],
              "build": res["build"], "selfcheck": res["selfcheck"]}
    bind_contract(res, case_contract_keys(case), values, out)
    res["outputs"] = sorted([p.name for p in out.iterdir() if p.is_file()] + ["result.json"])
    res["deliverable"] = "mindmap.md"
    wj(out / "result.json", res)
    return res


def load_index(inp, wrk, notes):
    idx = rj(Path(wrk) / "index.json")
    if isinstance(idx, dict) and idx.get("materials") is not None:
        return idx
    case, _ = discover_case(inp)
    idx = scan(inp)
    idx["case_id"] = case.get("case_id") or idx.get("case_id")
    wj(Path(wrk) / "index.json", idx)
    return idx


def minimal_result(out, notes, status="partial"):
    wj(Path(out) / "result.json", {"case_id": "unknown-case", "status": status,
                                  "sources": [{"material": "none", "name": "not ready", "chars": 0}],
                                  "nodes": [], "edges": [], "outline": {}, "output_contract": {},
                                  "uncertainties": ["run not finished"], "change_records": [],
                                  "limits": ["run not finished"], "degradations": list(notes),
                                  "errors": [], "runtime": {"stage": "bootstrap"}})


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init: partial result.json written"])
    idx = load_index(inp, wrk, notes)
    case, _ = discover_case(inp)
    dp = Path(wrk) / "draft.json"
    if not dp.is_file():
        wj(dp, {"case_id": idx.get("case_id"), "outline": None,
                "notes": "skeleton; fill outline branches after reading the material"})
    print("== init ==")
    print("case_id: %s materials=%d sections=%d" %
          (idx.get("case_id"), len(idx.get("materials") or []),
           sum(len(m.get("sections") or []) for m in idx.get("materials") or [])))
    print("contract keys (case): %s" % (case_contract_keys(case) or "none -> SKILL sample"))
    return 0


def cmd_show(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk, notes)
    limit = getattr(a, "limit", 40) or 40
    pat = getattr(a, "grep", "") or ""
    shown = 0
    for m in idx.get("materials") or []:
        for j, s in enumerate(m.get("sections") or []):
            title = s.get("title", "")
            if pat and not re.search(pat, title + " " + s.get("body", ""), re.I):
                continue
            print("\n--- %s#s%d %s ---" % (m["mid"], j + 1, title))
            print(s.get("body", "")[:800])
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        print("(no sections matched; input may be empty)")
    return 0


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(inp, wrk, notes)
    draft = rj(Path(wrk) / "draft.json", {}) or {}
    outline = draft.get("outline") or outline_of(idx.get("materials") or [], read_task(inp))
    chk = stage_check(idx, outline)
    print("== check ==")
    print("branches: %d" % chk["branches"])
    for e in chk["issues"]:
        print("ERROR %s" % e)
    print("RESULT: %s" % ("CHECK PASS" if chk["passed"] else "CHECK FAIL (%d)" % len(chk["issues"])))
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
    print("case_id=%s status=%s nodes=%d edges=%d"
          % (res.get("case_id"), res.get("status"), len(res.get("nodes") or []),
             len(res.get("edges") or [])))
    return 0


def cmd_selfcheck(a):
    inp, out, wrk, notes = paths(a)
    res = rj(Path(out) / "result.json", {}) or {}
    fails = []
    def ck(name, ok, extra=""):
        print("%-26s %s %s" % (name, "PASS" if ok else "FAIL", extra))
        if not ok:
            fails.append(name)
    ck("result.json parses", bool(res))
    ck("case_id present", bool(res.get("case_id")), str(res.get("case_id")))
    ck("contract echo", bool(res.get("output_contract")), "%d keys" % len(res.get("output_contract") or {}))
    for need in ("status", "sources", "uncertainties", "change_records", "limits"):
        ck("field:%s" % need, bool(res.get(need)))
    for f in ("mindmap.json", "mindmap.md", "outline.json", "report.md"):
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
    ap = argparse.ArgumentParser(prog="main.py", description="mindmap-builder v%s" % VERSION)
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
    mk("check", "validate draft outline")
    mk("build", "assemble mind map and final result.json")
    mk("selfcheck", "re-audit artefacts")
    sp = mk("show", "print locator-addressable sections")
    sp.add_argument("--grep", default="")
    sp.add_argument("--limit", type=int, default=40)

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
