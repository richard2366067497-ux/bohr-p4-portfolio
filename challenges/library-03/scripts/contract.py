"""Contract layer for library-curator (stdlib only).

Path resolution with relative fallbacks, /input case discovery, output_contract key extraction,
rule recovery, the result.json envelope with semantic contract filling, and index I/O.
No dependency on the kernel modules, so a legal partial result.json can always be written.
"""

import json
import os
import re
import time
from pathlib import Path

START = time.time()
MISSING = object()
DRIVER = "library-curator/1.0.0"

CONTRACT_MAP = [
    ("classification", ("classification", "classify", "catalog", "catalogue", "assignment", "record")),
    ("inventory", ("inventory", "file_list", "files", "manifest", "documents")),
    ("renames", ("rename", "filename", "naming", "name_map")),
    ("duplicates", ("dup", "dedup", "redundan")),
    ("versions", ("version", "chain", "relation")),
    ("operations", ("operation", "log", "change", "action", "ops")),
    ("skipped", ("skip", "unprocessed", "unhandled", "exception", "failed")),
    ("coverage", ("coverage", "stats", "statistic", "summary", "count", "metric")),
    ("answers", ("answer", "question", "query", "search", "qa")),
    ("tree", ("tree", "structure", "director", "folder", "layout", "hierarch")),
    ("rollback", ("rollback", "undo", "recovery", "restore", "revert")),
    ("evidence", ("evidence", "locator", "proof", "provenance", "citation")),
    ("method_notes", ("method", "rule", "note", "approach", "explain")),
    ("uncertainties", ("uncertain", "unresolved", "open")),
    ("status", ("status",)),
    ("case_id", ("case_id", "caseid")),
]


def resolve_dir(arg, env, defaults, create=False):
    cands = ([arg] if arg else []) + ([os.environ.get(env)] if env else []) + list(defaults)
    for c in cands:
        if c and os.path.isdir(c):
            return Path(c).resolve()
    if create:
        for c in cands:
            if not c:
                continue
            try:
                os.makedirs(c, exist_ok=True)
                return Path(c).resolve()
            except OSError:
                continue
    return Path(cands[-1]).resolve() if cands else Path(".").resolve()


def paths(args):
    inp = resolve_dir(getattr(args, "input", None), "INPUT_DIR", ["/input", "/app/input", "input"])
    work = resolve_dir(getattr(args, "work", None), "WORK_DIR", ["/app/work", "work"], create=True)
    out = resolve_dir(getattr(args, "output", None), "OUTPUT_DIR", ["/app/output", "output"], create=True)
    return inp, work, out


def load_json(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return json.load(fh), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:200])


def dump_json(p, obj):
    p = str(p)
    d = os.path.dirname(os.path.abspath(p))
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def load_case(inp):
    for name in ("case.json", "task.json", "case.yaml"):
        p = Path(inp) / name
        if p.is_file():
            obj, err = load_json(p)
            if isinstance(obj, dict):
                return obj, None
            if err:
                return {}, "%s: %s" % (name, err)
    return {}, "case.json not found in %s" % inp


def contract_keys(case):
    oc = case.get("output_contract") or case.get("outputContract") or case.get("contract") or {}
    keys = []
    if isinstance(oc, dict):
        if isinstance(oc.get("fields"), list):
            for it in oc["fields"]:
                if isinstance(it, str):
                    keys.append(it)
                elif isinstance(it, dict):
                    for k in ("name", "key", "field_id", "id", "field"):
                        if isinstance(it.get(k), str):
                            keys.append(it[k])
                            break
        if not keys:
            keys = [k for k in oc.keys() if isinstance(k, str)]
    elif isinstance(oc, list):
        for it in oc:
            if isinstance(it, str):
                keys.append(it)
            elif isinstance(it, dict):
                for k in ("name", "key", "field_id", "id", "field"):
                    if isinstance(it.get(k), str):
                        keys.append(it[k])
                        break
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def extract_rules(case):
    rules = {"naming_template": None, "target_root": None, "questions": [], "declared": [], "dimensions": None}
    for k in ("naming_template", "naming", "filename_template", "name_template", "rename_template"):
        v = case.get(k)
        if isinstance(v, str) and "{" in v:
            rules["naming_template"] = v
            break
        if isinstance(v, dict):
            for kk in ("template", "pattern", "format"):
                if isinstance(v.get(kk), str):
                    rules["naming_template"] = v[kk]
                    break
        if rules["naming_template"]:
            break
    for k in ("target_root", "output_root", "library_target", "target_dir", "target"):
        v = case.get(k)
        if isinstance(v, str) and v.strip():
            rules["target_root"] = v.strip()
            break
    for k in ("questions", "queries", "metadata_questions", "search_requests", "qa"):
        v = case.get(k)
        if isinstance(v, list):
            for i, it in enumerate(v):
                if isinstance(it, str):
                    rules["questions"].append({"question_id": "Q%d" % (i + 1), "question": it})
                elif isinstance(it, dict):
                    q = next((it[x] for x in ("question", "text", "query", "prompt") if isinstance(it.get(x), str)), "")
                    qid = next((str(it[x]) for x in ("id", "question_id", "qid") if it.get(x) is not None),
                               "Q%d" % (i + 1))
                    if q:
                        rules["questions"].append({"question_id": qid, "question": q})
            break
    for k in ("manifest", "inventory", "files", "expected_files", "documents"):
        v = case.get(k)
        if isinstance(v, list) and v and all(isinstance(x, (str, dict)) for x in v):
            for it in v:
                if isinstance(it, str):
                    rules["declared"].append(it)
                elif isinstance(it, dict):
                    for kk in ("path", "file", "filename", "name"):
                        if isinstance(it.get(kk), str):
                            rules["declared"].append(it[kk])
                            break
            break
    dims = case.get("rules") or case.get("classification_rules") or case.get("taxonomy")
    if isinstance(dims, (dict, list)):
        rules["dimensions"] = dims
    return rules


def material_root(case, inp):
    cands = []
    for k in ("library_root", "materials_root", "corpus_root", "input_root", "materials"):
        v = case.get(k)
        if isinstance(v, str):
            cands.append(v)
    cands += [str(Path(inp) / "library"), str(Path(inp) / "files"), str(Path(inp) / "artifacts"),
              str(Path(inp) / "materials"), str(inp), str(Path(inp) / "input")]
    for c in cands:
        p = Path(c)
        if not p.is_absolute():
            p = Path(inp) / c
        try:
            if p.is_dir() and any(x.is_file() for x in p.iterdir()):
                return p.resolve(), None
        except OSError:
            continue
    return Path(inp).resolve(), "no material subdirectory found; scanned /input itself"


def map_contract(key, P):
    k = key.lower()
    if "dup" in k and "version" in k:
        return {"duplicates": P.get("duplicates", []), "versions": P.get("versions", [])}
    for name, toks in CONTRACT_MAP:
        if any(t in k for t in toks):
            return P.get(name, MISSING)
    return MISSING


def cap(lst, n=400):
    if isinstance(lst, list) and len(lst) > n:
        return lst[:n] + [{"_truncated": "%d more entries in the on-disk artifact" % (len(lst) - n)}]
    return lst


def envelope(case_id, status, result, keys, errs, degr, unc, sources, notes, changes):
    """result.json = envelope + every output_contract key, filled by semantic match."""
    doc = {"case_id": case_id, "status": status, "result": result,
           "errors": errs, "degradations": degr, "uncertainties": unc, "sources": sources,
           "method_notes": notes, "changes": changes,
           "runtime": {"seconds": round(time.time() - START, 1), "driver": DRIVER}}
    payload = dict(result)
    for k in keys:
        val = map_contract(k, payload)
        if val is MISSING:
            val = [] if re.search(r"(s$|list|item|row|record|entr|table|array|map)", k.lower()) else None
            degr.append("output_contract key '%s' not mapped to an artifact -> %s (nothing fabricated)"
                        % (k, "[]" if val == [] else "null"))
        doc[k] = val
    return doc


def write_result(out, doc):
    p = Path(out) / "result.json"
    dump_json(p, doc)
    return p


def index_path(work):
    return Path(work) / "index.json"


def save_index(work, idx):
    slim = {k: v for k, v in idx.items() if k != "recs"}
    slim["recs"] = [{k: v for k, v in r.items() if k != "rows"} for r in idx.get("recs") or []]
    dump_json(index_path(work), slim)
    return index_path(work)


def load_index(work):
    idx, err = load_json(index_path(work))
    if isinstance(idx, dict) and isinstance(idx.get("recs"), list):
        return idx, None
    return None, err or "index.json missing"


def materialised(o):
    """A file is accounted for when it was copied now or already present with the same hash."""
    return o.get("op") in ("copy", "archive", "noop") and o.get("result") in ("ok", "already_present")


def coverage(recs, entries, skips, ops, renames, dupes, chains):
    filled = sum(1 for e in entries.values() for f in ("title", "authors", "year", "journal", "doi")
                 if (e.get("metadata") or {}).get(f))
    shall = max(1, len(entries)) * 5
    copied = {o["from"] for o in ops if materialised(o)}
    return {"files_expected": len(recs), "files_processed": len(copied), "skipped": len(skips),
            "classified": len(entries), "renamed": len(renames),
            "duplicate_groups": len(dupes), "version_chains": len(chains),
            "metadata_fields_filled": filled, "metadata_fields_missing": max(0, shall - filled),
            "metadata_fields_expected": shall,
            "coverage_ratio": round(len(copied) / len(recs), 3) if recs else 0.0,
            "elements": {"file_types": len({r["ext"] for r in recs}),
                         "directory_levels": len({len(str(e.get("class_path") or "").split("/"))
                                                   for e in entries.values()}),
                         "duplicates_declared": len(dupes), "versions_declared": len(chains),
                         "permissions_recorded": len([r for r in recs if r.get("permission")]),
                         "hashes_recorded": len([r for r in recs if r.get("sha256")])}}

def compute_status(recs, draft, entries, cov, ops):
    if not recs:
        return "failed"
    complete = cov["files_processed"] + cov["skipped"] >= cov["files_expected"]
    agent = draft is not None and bool(draft.get("classification")) and \
        not any(e.get("auto") for e in entries.values())
    failed_ops = [o for o in ops if o.get("result") == "failed"]
    return "ok" if (complete and agent and not failed_ops) else "partial"

def by_key(entries, field):
    out = {}
    for e in entries.values():
        out.setdefault(str(e.get(field) or "unknown"), []).append(e["path"])
    return {k: v[:50] for k, v in sorted(out.items())}

def by_year(entries):
    out = {}
    for e in entries.values():
        out.setdefault(str((e.get("metadata") or {}).get("year") or "unknown"), []).append(e["path"])
    return {k: v[:50] for k, v in sorted(out.items())}

def by_sha(recs):
    out = {}
    for r in recs:
        if r.get("sha256"):
            out.setdefault(r["sha256"], []).append(r["rel"])
    return {k: v for k, v in out.items() if len(v) > 1}


def inv_row(r):
    return {"doc_id": r["doc_id"], "path": r["rel"], "size": r["size"], "sha256": r["sha256"],
            "mtime": r["mtime"], "ext": r["ext"], "kind": r["kind"], "readable": r["readable"],
            "permission": r["permission"], "text_quality": r["text_quality"],
            "flags": r["flags"], "declared_doc_type": r.get("doc_type")}
