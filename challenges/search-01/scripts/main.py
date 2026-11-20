#!/usr/bin/env python3
"""main.py - CLI for traceable-literature-retrieval (search-01).

Five commands: init / show / check / build / selfcheck.
Deterministic work (parsing, locators, dedup, quote verification, rendering) is
done here and in sr_core/sr_output; the relevance and keep/drop judgement is
written by the agent into <work>/draft.json. `build` never fails: without a
draft it emits a complete but explicitly degraded result and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sr_core as C  # noqa: E402
import sr_build as B  # noqa: E402
import sr_output as O  # noqa: E402

VERSION = "1.0.0"
START = time.time()
STATUSES = ("answered", "partial", "insufficient_evidence", "input_error")
# ------------------------------------------------------------------ plumbing
def say(msg=""):
    try:
        print(msg, flush=True)
    except Exception:
        pass


def resolve_dir(arg, env_name, defaults, create=True):
    if arg:  # an explicit path always wins, and is created when asked to
        p = Path(arg).resolve()
        if create:
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        return p
    cands = []
    if os.environ.get(env_name):
        cands.append(Path(os.environ[env_name]))
    cands.extend(Path(d) for d in defaults)
    for c in cands:
        if c.is_dir():
            return c.resolve()
    chosen = cands[0] if arg else Path(defaults[0])
    if create:
        for c in [chosen] + [Path(d) for d in defaults]:
            try:
                c.mkdir(parents=True, exist_ok=True)
                return c.resolve()
            except Exception:
                continue
    return chosen.resolve()


def dirs(a):
    inp = resolve_dir(a.input, "SKILL_INPUT", ["/input", str(HERE.parent / "input"), "input"], create=False)
    work = resolve_dir(a.work, "SKILL_WORK", ["/app/work", str(HERE.parent / "work"), "work"])
    out = resolve_dir(a.output, "SKILL_OUTPUT", ["/app/output", str(HERE.parent / "output"), "output"])
    return inp, work, out


def read_case(inp):
    errors = []
    for name in ("case.json", "case.JSON", "case.yaml"):
        p = inp / name
        if p.is_file():
            if p.suffix.lower() == ".yaml":
                errors.append({"code": "case_yaml_unsupported", "detail": "case.yaml found; JSON expected"})
                continue
            obj, note = C.load_json(p)
            if note:
                errors.append({"code": "case_json_parse_note", "detail": str(note)[:200]})
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                obj = obj[0]
            if isinstance(obj, dict):
                return obj, errors
            if obj is not None:
                errors.append({"code": "case_json_not_object", "detail": type(obj).__name__})
    for p in sorted(inp.glob("*case*.json")):
        obj, note = C.load_json(p)
        if isinstance(obj, dict):
            errors.append({"code": "case_json_renamed", "detail": "used %s" % p.name})
            return obj, errors
    if not errors:
        errors.append({"code": "case_json_missing",
                       "detail": "no /input/case.json; contract fields cannot be enumerated"})
    return {}, errors


def empty_value(key):
    """Contract-shaped empty placeholder so no declared key is ever omitted."""
    t = B.ALIAS.get(C.nkey(key), C.nkey(key))
    if t == "status":
        return "partial"
    if t in B.LIST_NAMES:
        return []
    if t in B.DICT_NAMES:
        return {}
    return None


def envelope(cid, status, inp, work, out, command):
    return {
        "case_id": cid,
        "status": status if status in STATUSES else "partial",
        "skill": "traceable-literature-retrieval",
        "version": VERSION,
        "errors": [],
        "degradations": [],
        "runtime": {"command": command, "input_dir": str(inp), "work_dir": str(work),
                    "output_dir": str(out), "started_unix": int(START),
                    "elapsed_s": round(time.time() - START, 2)},
    }


def write_partial(out, res, contract, code, detail):
    """Always leave a legal result.json on disk before doing heavy work."""
    res = dict(res)
    res["degradations"] = list(res.get("degradations") or []) + [{"code": code, "detail": detail}]
    for k in contract:
        if k not in res:
            res[k] = empty_value(k)
    try:
        C.dump_json(out / "result.json", res)
    except Exception:
        pass


def load_index(work):
    p = work / "index.json"
    if p.is_file():
        obj, note = C.load_json(p)
        if isinstance(obj, dict) and obj.get("objects") is not None:
            return obj
    return None


def ensure_index(a, inp, work):
    idx = load_index(work)
    if idx:
        return idx
    case, _errs = read_case(inp)
    idx = B.make_index(inp, case)
    try:
        C.dump_json(work / "index.json", idx)
    except Exception:
        pass
    return idx



def drafts_path(work):
    for name in ("draft.json", "plan.json", "draft.min.json"):
        p = work / name
        if p.is_file():
            return p
    return work / "draft.json"


def load_draft(work):
    p = drafts_path(work)
    if not p.is_file():
        return None, {"code": "draft_missing",
                      "detail": "no %s; run `show`, read the material, write the draft, then `build`" % p.name}
    obj, note = C.load_json(p)
    if obj is None:
        return None, {"code": "draft_unreadable", "detail": str(note)[:200]}
    if isinstance(obj, list):
        obj = {"selections": obj}
    if not isinstance(obj, dict):
        return None, {"code": "draft_not_object", "detail": type(obj).__name__}
    return obj, None


# --------------------------------------------------------------- init/show
def cmd_init(a):
    inp, work, out = dirs(a)
    case, errors = read_case(inp)
    contract = C.contract_keys(case)
    cid = C.case_id_of(case, inp)
    res = envelope(cid, "partial", inp, work, out, "init")
    res["errors"] = list(errors)
    res["summary"] = "partial result written by init; run build to finalize"
    write_partial(out, res, contract, "init_partial",
                  "legal partial result.json written before indexing; candidates not built yet")
    index = B.make_index(inp, case)
    C.dump_json(work / "index.json", index)
    st = index["stats"]
    say("== init ==")
    say("case_id       : %s" % cid)
    say("input / work  : %s | %s" % (inp, work))
    say("contract keys : %s" % (", ".join(contract) if contract else "(none declared -> canonical keys used)"))
    say("materials     : %d files, %d objects, %d duplicate(s), %d with DOI, %d with abstract"
        % (st["files"], st["objects"], st["duplicates"], st["with_doi"], st["with_abstract"]))
    say("required refs : %d | reference-graph checkpoints: %d | import states: %d"
        % (st["required_items"], len(index["reference_graph"]["refs"]), st["import_states"]))
    say("target_k      : %s (%s) | time window: %s"
        % (index["task"]["target_k"], index["task"]["target_k_source"], index["task"]["time_window"]))
    say("partial result: %s" % (out / "result.json"))
    for e in (index["errors"] + index["degradations"])[:8]:
        say("  ! %s: %s" % (e.get("code"), str(e.get("detail"))[:140]))
    say("next          : python3 scripts/main.py show")
    return 0


def cmd_show(a):
    inp, work, out = dirs(a)
    index = ensure_index(a, inp, work)
    task = index["task"]
    if a.task:
        say("== task ==")
        for k in ("research_question", "target_k", "target_k_source", "time_window",
                  "seed_keywords", "exclude_terms", "languages", "declared_sources"):
            say("%-16s: %s" % (k, task.get(k)))
        say("%-16s: %s" % ("constraints", str(task.get("constraints_text"))[:900]))
        say("\n== suggested query plan (yours to accept, edit or replace) ==")
        for i, q in enumerate(index["suggested_queries"], 1):
            say("Q%d  %s   [intent: %s]" % (i, q["query"], q["intent"]))
        say("\n== required references / coverage checkpoints ==")
        for r in index["required"][:40]:
            say("%-7s %-40s %s" % (r["ref_id"], (r["doi"] or "-")[:40], (r["title"] or "")[:80]))
        if index["import_states"]:
            say("\n== organizer-local import states (coverage limits) ==")
            for s in index["import_states"]:
                say("%s: %s" % (s["source"], json.dumps(s["state"], ensure_ascii=False)[:300]))
        say("\n== sources ==")
        for s in index["sources"]:
            say("%-34s %-6s %-14s records=%s" % (s["source_id"][:34], s["format"], s["role"], s["records"]))
        say("")
    objs = index["objects"]
    if a.grep:
        pat = a.grep.lower()
        objs = [o for o in objs if pat in (o.get("text") or "") or pat in o["object_id"].lower()]
    if a.ids:
        want = {x.strip().upper() for x in a.ids.split(",") if x.strip()}
        objs = [o for o in objs if o["object_id"].upper() in want]
    limit = a.limit if a.limit and a.limit > 0 else len(objs)
    say("== objects (showing %d of %d) ==" % (min(limit, len(objs)), len(objs)))
    for o in objs[:limit]:
        say("[%s] %s | %s | doi:%s | %s" % (
            o["object_id"], o.get("year") or "n/a", (o.get("venue") or "no-venue")[:42],
            o.get("doi") or "-", o["locator"]))
        say("      title: %s" % o["title"][:220])
        if o.get("authors"):
            say("      authors: %s" % "; ".join(o["authors"][:6])[:200])
        ab = o.get("abstract")
        if ab:
            say("      abstract: %s" % (ab if a.full else C.snippet(ab, a.chars)))
        say("      quote from the locator above, verbatim; do not paraphrase inside `quote`.")
        say("")
    say("next: write %s (schema: references/draft-and-screening.md), then `check`" % drafts_path(work))
    return 0


# ------------------------------------------------------------------- check
def cmd_check(a):
    inp, work, out = dirs(a)
    index = ensure_index(a, inp, work)
    draft, derr = load_draft(work)
    rep = B.validate(index, draft, derr)
    rep["checked_draft"] = str(drafts_path(work))
    C.dump_json(work / "check_report.json", rep)
    say("== check ==")
    say("draft         : %s" % drafts_path(work))
    say("stats         : %s" % json.dumps(rep["stats"], ensure_ascii=False))
    say("ok            : %s" % rep["ok"])
    for it in rep["issues"][:40]:
        say("  [%s] %s: %s" % (it["level"], it["code"], it.get("detail", "")))
    if len(rep["issues"]) > 40:
        say("  ... %d more issues, see %s" % (len(rep["issues"]) - 40, work / "check_report.json"))
    say("next          : fix errors, then python3 scripts/main.py build")
    return 0


# ------------------------------------------------------------------- build
def cmd_build(a):
    inp, work, out = dirs(a)
    case, case_errs = read_case(inp)
    contract = C.contract_keys(case)
    res = envelope(C.case_id_of(case, inp), "partial", inp, work, out, "build")
    res["errors"] = list(case_errs)
    write_partial(out, res, contract, "build_partial",
                  "partial result.json written before assembly; will be finalized in this run")
    draft, derr = load_draft(work)
    try:
        index = ensure_index(a, inp, work)
    except Exception as exc:
        index = {"case_id": res["case_id"], "objects": [], "sources": [], "required": [],
                 "task": {"target_k": 20, "research_question": ""}, "suggested_queries": [],
                 "expansions": [], "import_states": [], "errors": [
                     {"code": "index_build_failed", "detail": "%s: %s" % (exc.__class__.__name__, exc)}],
                 "degradations": []}
    try:
        payload, mode = B.assemble(index, draft, "agent_draft" if draft else "fallback_keyword_ranking")
    except Exception as exc:
        payload, mode = B.assemble(index, None, "fallback_keyword_ranking")
        payload["errors"].append({"code": "assemble_error",
                                  "detail": "%s: %s" % (exc.__class__.__name__, str(exc)[:200])})
        payload["status"] = "partial"
        payload["degradations"].append({"code": "assembly_degraded",
                                        "detail": "agent draft could not be assembled; deterministic fallback used"})
    if derr:
        payload["degradations"].append(dict(derr))
    final = dict(res)
    final.update({k: v for k, v in payload.items() if k not in ("errors", "degradations")})
    final["errors"] = list(res.get("errors") or []) + list(payload.get("errors") or [])
    final["degradations"] = [d for d in (res.get("degradations") or []) if d.get("code") != "build_partial"] + \
                            list(payload.get("degradations") or [])
    final["status"] = payload["status"]
    final["runtime"].update({"mode": mode, "elapsed_s": round(time.time() - START, 2),
                             "index_objects": len(index.get("objects") or [])})
    filled = B.fill_contract(final, payload, contract)
    if not contract:
        final["degradations"].append({"code": "no_output_contract_declared",
                                      "detail": "case.json declares no output_contract; canonical field names used"})
    try:
        C.dump_json(out / "result.json", final)
        C.dump_text(out / "candidates.jsonl", O.jsonl_lines(payload["candidates"]))
        C.dump_json(out / "search_log.json", payload["search_log"])
        C.dump_json(out / "coverage.json", payload["coverage"])
        C.dump_json(out / "screening.json", {"excluded": payload["excluded"], "conflicts": payload["conflicts"]})
        C.dump_text(out / "report.md", payload["report"])
    except Exception as exc:
        say("! artifact write problem: %s" % exc)
    st = {"status": final["status"], "mode": mode, "candidates": len(payload["candidates"]),
          "excluded": len(payload["excluded"]), "required_matched": payload["coverage"]["required_matched_count"],
          "required_total": payload["coverage"]["required_total"],
          "contract_filled": len(filled), "degradations": len(final["degradations"]),
          "errors": len(final["errors"])}
    say("== build ==")
    say("mode          : %s" % mode)
    say("status        : %s" % st["status"])
    say("candidates    : %d (excluded %d, target_k %s)"
        % (st["candidates"], st["excluded"], index["task"].get("target_k")))
    say("coverage      : %d/%d required references matched"
        % (st["required_matched"], st["required_total"]))
    say("contract keys : %d filled%s" % (len(filled), "" if filled else " (none declared)"))
    say("artifacts     : result.json, candidates.jsonl, search_log.json, coverage.json, screening.json, report.md")
    for d in final["degradations"][:8]:
        say("  ! %s: %s" % (d.get("code"), str(d.get("detail"))[:150]))
    say("next          : python3 scripts/main.py selfcheck")
    return 0


# --------------------------------------------------------------- selfcheck
def selfcheck_checks(result, contract, out):
    """Return a list of {check, ok, detail} over the finalized artifacts."""
    checks = [{"check": "result_json_parses", "ok": isinstance(result, dict),
               "detail": "ok" if isinstance(result, dict) else "result.json is not a JSON object"}]
    if not isinstance(result, dict):
        return checks
    missing = [k for k in contract if k not in result]
    checks.append({"check": "contract_keys_present", "ok": not missing,
                   "detail": ("missing: %s" % missing) if missing else "%d keys" % len(contract)})
    checks.append({"check": "status_is_enum", "ok": result.get("status") in STATUSES,
                   "detail": str(result.get("status"))})
    cands = result.get("candidates") or []
    checks.append({"check": "candidates_present",
                   "ok": bool(cands) or result.get("status") in ("insufficient_evidence", "input_error"),
                   "detail": "%d rows / %s" % (len(cands), result.get("status"))})
    bad = [c.get("object_id") for c in cands if not (c.get("source_id") and c.get("locator"))]
    checks.append({"check": "every_candidate_has_locator", "ok": not bad, "detail": str(bad[:5])})
    unver = [c.get("object_id") for c in cands if not ((c.get("relevance") or {}).get("quote_verified"))]
    checks.append({"check": "quotes_verified", "ok": len(unver) <= max(1, len(cands) // 3),
                   "detail": "%d/%d unverified: %s" % (len(unver), len(cands), unver[:5])})
    ranks = [c.get("rank") for c in cands]
    checks.append({"check": "rank_contiguous", "ok": ranks == list(range(1, len(cands) + 1)),
                   "detail": str(ranks[:8])})
    jp = out / "candidates.jsonl"
    lines = len([l for l in jp.read_text(encoding="utf-8").splitlines() if l.strip()]) if jp.is_file() else 0
    checks.append({"check": "jsonl_matches_json", "ok": lines == len(cands),
                   "detail": "jsonl=%d json=%d" % (lines, len(cands))})
    rep = out / "report.md"
    checks.append({"check": "report_non_empty", "ok": rep.is_file() and rep.stat().st_size > 200,
                   "detail": "%d bytes" % (rep.stat().st_size if rep.is_file() else 0)})
    checks.append({"check": "dois_shaped_like_dois",
                   "ok": all((c.get("doi") or "/") .count("/") >= 1 for c in cands if c.get("doi")),
                   "detail": "DOI prefix present"})
    return checks


def cmd_selfcheck(a):
    inp, work, out = dirs(a)
    result, note = C.load_json(out / "result.json")
    checks = selfcheck_checks(result, C.contract_keys(read_case(inp)[0]), out)
    if note:
        checks[0]["detail"] = str(note)
    ok = all(c["ok"] for c in checks)
    C.dump_json(out / "selfcheck.json", {"ok": ok, "checks": checks})
    say("== selfcheck ==")
    for c in checks:
        say("  [%s] %-32s %s" % ("PASS" if c["ok"] else "FAIL", c["check"], c["detail"]))
    say("overall       : %s -> %s" % ("PASS" if ok else "NEEDS ATTENTION", out / "selfcheck.json"))
    return 0


# -------------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(prog="main.py", description="traceable literature retrieval (search-01)")
    p.add_argument("command", nargs="?", default="init",
                   choices=["init", "show", "check", "build", "selfcheck"])
    p.add_argument("--input", default=None, help="input dir (default /input)")
    p.add_argument("--work", default=None, help="work dir (default /app/work)")
    p.add_argument("--output", default=None, help="output dir (default /app/output)")
    p.add_argument("--limit", type=int, default=0, help="show: max objects to print")
    p.add_argument("--chars", type=int, default=700, help="show: abstract chars per object")
    p.add_argument("--grep", default=None, help="show: filter objects by substring")
    p.add_argument("--ids", default=None, help="show: comma separated object ids")
    p.add_argument("--full", action="store_true", help="show: full abstract")
    p.add_argument("--task", action="store_true", help="show: print parsed task, query plan, required refs")
    return p


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit:
        return 0  # --help or bad flags: argparse already reported, exit code stays 0
    cmd = {"init": cmd_init, "show": cmd_show, "check": cmd_check,
           "build": cmd_build, "selfcheck": cmd_selfcheck}[args.command]
    try:
        cmd(args)
    except Exception as exc:
        say("! unexpected %s: %s" % (exc.__class__.__name__, exc))
        traceback.print_exc()
        try:
            inp, work, out = dirs(args)
            case, _ = read_case(inp)
            res = envelope(C.case_id_of(case, inp), "partial", inp, work, out, args.command)
            res["errors"] = [{"code": "unhandled_exception",
                              "detail": "%s: %s" % (exc.__class__.__name__, str(exc)[:300])}]
            res["degradations"] = [{"code": "crash_guard", "detail": "result.json rewritten by the crash guard"}]
            for k in C.contract_keys(case):
                res.setdefault(k, empty_value(k))
            C.dump_json(out / "result.json", res)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
