#!/usr/bin/env python3
"""main.py - five-command entry point for literature-screening-ranker.

  init      discover input, build index, write a legal partial result.json
  show      print criteria + candidates with locators (for verbatim quotes)
  check     machine-check the agent work draft (/app/work/draft*.json)
  build     render screening.jsonl / ranking.json / coverage / conflicts / report + final result.json
  selfcheck re-verify what landed on disk

Exit code is always 0. Every command is safe to interrupt: a legal partial
result.json exists before any long work starts.
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True          # keep the installed skill directory clean
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core as C          # noqa: E402
import analyze as A       # noqa: E402
import pipeline as P      # noqa: E402

START = time.time()
PRODUCTS = ("result.json", "screening.jsonl", "ranking.json", "coverage.json",
            "conflicts.json", "screening_report.md", "selfcheck.json")
DRAFT_GLOB = ("draft.json", "draft-*.json", "draft_*.json", "plan.json", "screen-*.json")
H = {}  # helpers injected into pipeline (avoids circular import)


def now():
    return round(time.time() - START, 2)


def norm_specs(specs):
    """Accept contract specs as dicts (index.json) or tuples (fresh build)."""
    out = []
    for s in specs or []:
        if isinstance(s, dict):
            out.append((s.get("key"), s.get("kind") or "unknown"))
        elif isinstance(s, (list, tuple)) and len(s) >= 2:
            out.append((s[0], s[1] or "unknown"))
        elif isinstance(s, str):
            out.append((s, "unknown"))
    return [(k, kd) for k, kd in out if k]


def dedupe_degr(items):
    seen, out = set(), []
    for d in items:
        key = json.dumps([d.get("stage"), d.get("issue"), d.get("field"), d.get("record_id")],
                         ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def case_id_of(case, cpath):
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id", "task_id", "challenge_id"):
            if case.get(k):
                return str(case[k])
    return Path(cpath).stem if cpath else "unknown"


def read_task_md(inp):
    for name in ("task.md", "TASK.md", "task_instruction.md", "instruction.md"):
        p = inp / name
        if p.is_file():
            return C.clean(C.read_text(p))[:9000], C.rel(p, inp)
    for p in sorted(inp.glob("*.md")):
        return C.clean(C.read_text(p))[:9000], C.rel(p, inp)
    return "", None


def build_index(inp):
    case, cpath, cerr = C.load_case(inp)
    task_md, task_loc = read_task_md(inp)
    crit = C.load_criteria(case, inp, task_md)
    specs = C.contract_specs(case)
    cands, sources, degr, overflow = C.load_candidates(inp, skip_files=[cpath])
    clusters, studies = A.cluster(cands) if cands else ([], [])
    annot = C.load_annotations(inp)
    idx = {
        "version": C.VERSION, "case_id": case_id_of(case, cpath), "input_dir": str(inp),
        "case_file": cpath, "task_md_locator": task_loc,
        "contract": [{"key": k, "kind": kd} for k, kd, _ in specs],
        "criteria": crit, "candidates": cands, "clusters": clusters, "studies": studies,
        "sources": sources, "annotations": annot, "overflow": overflow,
        "degradations": degr, "errors": ([{"stage": "input", "issue": "case_json", "detail": cerr}] if cerr else []),
        "counts": {"candidates": len(cands), "clusters": len(clusters),
                   "same_study_groups": len(studies), "contract_keys": len([s for s in specs if s[0] != "__implicit__"])},
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return idx, specs


def load_index(work, inp, force=False):
    p = work / "index.json"
    if p.is_file() and not force:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and "candidates" in obj:
                return obj, [{"key": k["key"], "kind": k.get("kind", "unknown")} for k in obj.get("contract", [])]
        except Exception:
            pass
    idx, specs = build_index(inp)
    try:
        C.jwrite(p, idx)
    except Exception:
        pass
    return idx, specs


def envelope_from(idx, specs, status):
    res = A.envelope(idx.get("case_id"), status, [(k, kd, None) for k, kd in norm_specs(specs)])
    res["sources"] = idx.get("sources", [])
    res["queries"] = (idx.get("annotations") or {}).get("queries", [])
    res["runtime"]["input_dir"] = idx.get("input_dir")
    res["runtime"]["case_file"] = idx.get("case_file")
    res["result"]["coverage"] = {
        "total_candidates": idx["counts"]["candidates"], "screened": 0,
        "coverage_ratio": 0.0, "labels": {k: 0 for k in C.LABELS},
        "merged_duplicates": 0, "recall_note": "only the supplied snapshot is screened",
    }
    res["degradations"] += idx.get("degradations", [])
    res["errors"] += idx.get("errors", [])
    if not idx["counts"]["candidates"]:
        res["pending_human"].append({"issue": "no_candidates", "action": "补齐候选文献集（/input 下未发现可识别的文献记录）",
                                     "reason": "扫描 JSON/JSONL/CSV/MD/TXT 未发现含题名的记录列表"})
    return res


def finalize(out, res):
    res["runtime"]["elapsed_sec"] = now()
    res["runtime"]["finished"] = True
    res["degradations"] = dedupe_degr(res.get("degradations", []))
    C.jwrite(out / "result.json", res)


LIST_KEYS = ("result", "screen", "candidate", "records", "items", "papers", "ranking", "order", "top",
             "conflict", "dup", "merge", "evidence", "quote", "quer", "uncertain", "gap", "error", "assumption")
DICT_KEYS = ("cover", "count", "stat", "criteria", "guideline", "label", "runtime", "meta", "provenance")
STR_KEYS = ("report", "summary", "markdown", "narrative", "explain", "rationale", "text")


def empty_like(key, kind):
    """Degraded contract fields must still have the declared/implied shape."""
    low = str(key).lower()
    if kind == "list" or (kind != "dict" and any(t in low for t in LIST_KEYS)):
        return []
    if kind == "dict" or any(t in low for t in DICT_KEYS):
        return {}
    if kind == "string" or any(t in low for t in STR_KEYS):
        return ""
    return None


def refresh_contract(res, specs):
    """Every output_contract key must exist at top level, correctly named."""
    for key, kind in norm_specs(specs):
        if key == "__implicit__":
            continue
        val = A.contract_value(key, res)
        if val in (None, [], {}, ""):
            val = empty_like(key, kind)
            res["degradations"].append({"stage": "contract", "issue": "contract_field_filled_empty", "field": key})
        else:
            res["degradations"] = [d for d in res["degradations"]
                                   if not (d.get("issue") == "contract_field_filled_empty" and d.get("field") == key)]
        res[key] = val
    return res


# ------------------------------------------------------------------ drafts
def load_drafts(work):
    files, seen = [], set()
    for pat in DRAFT_GLOB:
        for p in sorted(work.glob(pat)):
            if p.is_file() and str(p.resolve()) not in seen and p.name != "draft.template.json":
                seen.add(str(p.resolve()))
                files.append(p)
    entries, meta = {}, {"files": [], "errors": [], "criteria_used": [], "conflicts": [],
                         "uncertainties": [], "research_question": None}
    for p in files:
        try:
            obj = json.loads(C.read_text(p) or "null")
        except Exception as exc:
            meta["errors"].append({"file": p.name, "issue": "draft_parse", "detail": str(exc)[:160]})
            continue
        if not isinstance(obj, dict):
            meta["errors"].append({"file": p.name, "issue": "draft_not_object"})
            continue
        meta["files"].append(p.name)
        if obj.get("research_question"):
            meta["research_question"] = str(obj["research_question"])[:400]
        for k in ("criteria_used", "conflicts", "uncertainties"):
            if isinstance(obj.get(k), list):
                meta[k] += obj[k]
        recs = obj.get("records") or obj.get("screening") or obj.get("items") or []
        if isinstance(recs, dict):
            recs = [dict(v, record_id=v.get("record_id") or k) for k, v in recs.items() if isinstance(v, dict)]
        for r in recs if isinstance(recs, list) else []:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("record_id") or r.get("id") or "").strip()
            if rid:
                entries[rid] = r
    return entries, meta


def cmd_init(args, ctx):
    inp, out, work = ctx
    idx, specs = build_index(inp)
    C.jwrite(work / "index.json", idx)
    status = "input_error" if not idx["counts"]["candidates"] else "partial"
    res = envelope_from(idx, specs, status)
    for k in ("status", "case_id"):
        if k in res:
            res[k] = status if k == "status" else res["case_id"]
    refresh_contract(res, specs)
    if not idx["counts"]["candidates"]:
        res["degradations"].append({"stage": "init", "issue": "no_candidates_found",
                                    "detail": "no record list with a title field under /input"})
    else:
        res["degradations"].append({"stage": "init", "issue": "screening_not_started",
                                    "detail": "partial placeholder written before agent reads materials"})
    finalize(out, res)

    tpl = {"case_id": idx["case_id"], "research_question": "", "criteria_used": [], "records": [],
           "conflicts": [], "uncertainties": [],
           "_howto": "每条候选填 label/relevance/score/criteria_hit/evidence_quote+evidence_locator/confidence/rationale；"
                     "evidence_quote 必须逐字来自摘要或题名。schema 见 references/draft-schema.md"}
    for rec in idx["candidates"]:
        tpl["records"].append({"record_id": rec["record_id"], "label": "", "relevance": "", "score": None,
                               "criteria_hit": [], "criteria_violated": [], "evidence_quote": "",
                               "evidence_locator": A.locator_for(rec, {}), "confidence": "",
                               "rationale": "", "duplicate_of": rec.get("duplicate_of"), "flags": []})
    C.jwrite(work / "draft.template.json", tpl)

    crit = idx["criteria"]
    print("=" * 78)
    print("init: case_id=%s  status=%s" % (idx["case_id"], status))
    print("input   : %s  (case=%s)" % (inp, idx["case_file"]))
    print("contract: %d keys -> %s" % (idx["counts"]["contract_keys"],
                                       ", ".join(k["key"] for k in idx["contract"])[:400]))
    print("found   : %d candidates | %d duplicate clusters | %d same-study groups | overflow=%d"
          % (idx["counts"]["candidates"], idx["counts"]["clusters"], idx["counts"]["same_study_groups"],
             idx.get("overflow", 0)))
    print("question: %s" % (crit.get("question") or "(未明确给出)"))
    print("k       : %s | time_window=%s" % (crit.get("k"), (crit.get("facets") or {}).get("time_window")))
    f = crit.get("facets") or {}
    for name in ("topic", "object", "method"):
        print("facet   : %-8s %s" % (name, ", ".join(f.get(name) or [])[:160] or "-"))
    print("facet   : %-8s include=%s exclude=%s" % ("type", f.get("type_include") or "-", f.get("type_exclude") or "-"))
    print("materials:")
    for s in idx["sources"][:20]:
        print("  - %-46s %-18s records=%s" % (s.get("path"), s.get("kind"), s.get("records")))
    if idx.get("degradations") or idx.get("errors"):
        print("degradations/errors: %d (see index.json)" % (len(idx.get("degradations", [])) + len(idx.get("errors", []))))
    print("-" * 78)
    print("NEXT: python3 scripts/main.py show   # read criteria + candidates with locators")
    print("      then write %s from draft.template.json, then check, then build" % (work / "draft.json"))
    print("=" * 78)
    return res


def cmd_show(args, ctx):
    inp, out, work = ctx
    idx, _ = load_index(work, inp)
    crit = idx["criteria"]
    entries, _meta = load_drafts(work)
    cands = idx["candidates"]
    if args.criteria:
        print("=" * 78)
        print("研究问题: %s" % (crit.get("question") or "(未给出)"))
        print("目标 k  : %s   时间窗: %s" % (crit.get("k"), (crit.get("facets") or {}).get("time_window")))
        print("纳入条款:")
        for i, cl in enumerate((crit.get("clauses", {}).get("inclusion") or [])[:10], 1):
            print("  %d. %s" % (i, cl))
        print("排除条款:")
        for cl in (crit.get("exclusion_clauses") or [])[:10]:
            print("  - %s" % cl)
        print("来源定位: %s" % "; ".join("%s (%s chars)" % (b["locator"], b["chars"]) for b in crit.get("blocks", [])))
        print("规则表: R1..R12 见 references/labeling-guideline.md")
        print("=" * 78)
        return
    if args.ids:
        want = [x.strip() for x in args.ids.split(",") if x.strip()]
        sel = [c for c in cands if c["record_id"] in want]
    elif args.picks:
        sel = [c for c in cands if c["record_id"] not in entries]
    else:
        size = max(1, int(args.page_size))
        page = max(1, int(args.page))
        sel = cands[(page - 1) * size: page * size]
    print("=" * 78)
    print("case=%s  候选 %d 条，本次显示 %d 条（page=%s size=%s picks=%s）  draft=%d 条"
          % (idx["case_id"], len(cands), len(sel), args.page, args.page_size, args.picks, len(entries)))
    print("研究问题: %s" % (crit.get("question") or "-"))
    print("k=%s 时间窗=%s 主题词=%s" % (crit.get("k"), (crit.get("facets") or {}).get("time_window"),
                                    ", ".join((crit.get("facets") or {}).get("topic") or [])[:120]))
    print("-" * 78)
    for rec in sel:
        base = rec.get("locator") or {}
        tag = " [DUP->%s]" % rec["duplicate_of"] if rec.get("duplicate_of") else (
            " [cluster primary, merged %s]" % (rec.get("cluster_size", 1) - 1) if rec.get("cluster_size", 1) > 1 else "")
        fx = " [FIXTURE]" if rec.get("fixture") else ""
        print("[%s]%s%s type=%s year=%s" % (rec["record_id"], tag, fx, rec.get("record_type"), rec.get("year") or "-"))
        print("  TITLE: %s" % (rec.get("title") or "(无题名)"))
        if rec.get("authors"):
            print("  AUTH : %s" % "; ".join(rec["authors"][:4]))
        print("  META : venue=%s | doi=%s | venue_type=%s" % (rec.get("venue") or "-", rec.get("doi") or "-",
                                                            rec.get("type_raw") or "-"))
        print("  LOC  : %s#%s   abstract: %s#%s" % (base.get("file"), base.get("pointer"), base.get("file"),
                                                    (base.get("fields") or {}).get("abstract")))
        if rec.get("duplicate_of"):
            ev = rec.get("merge_evidence") or {}
            print("  MERGE: merged into %s | reasons=%s" % (rec["duplicate_of"], ",".join(ev.get("reasons") or [])))
        if rec.get("flags"):
            print("  FLAGS: %s" % ", ".join(rec["flags"][:4]))
        e = entries.get(rec["record_id"])
        if e:
            print("  DRAFT: label=%s relevance=%s score=%s" % (e.get("label"), e.get("relevance"), e.get("score")))
        ab = C.flat(rec.get("abstract") or "")
        if ab:
            show = ab if args.full else (ab[:args.chars] + (" ...[+%d chars, use --full]" % (len(ab) - args.chars)
                                                           if len(ab) > args.chars else ""))
            print("  ABSTRACT: %s" % show)
        else:
            print("  ABSTRACT: (缺失 -> R11 摘要不足，判 maybe 并在 flags 记 abstract_missing)")
        print()
    if not sel:
        print("（本页无记录；用 --page / --ids / --picks 调整）")
    print("-" * 78)
    print("逐条判断写入 %s ，然后 python3 scripts/main.py check" % (work / "draft.json"))
    print("=" * 78)


def cmd_selfcheck(args, ctx):
    inp, out, work = ctx
    idx, _specs = load_index(work, inp)
    try:
        res = json.loads(C.read_text(out / "result.json") or "null")
    except Exception:
        res = None
    res = res if isinstance(res, dict) else {}
    rows, prod = [], {}
    for name in ("screening.jsonl", "ranking.json", "coverage.json", "conflicts.json"):
        try:
            prod[name] = [json.loads(x) for x in C.read_text(out / name).splitlines() if x.strip()] \
                if name.endswith(".jsonl") else json.loads(C.read_text(out / name))
        except Exception:
            prod[name] = None
    rows = prod.get("screening.jsonl") or []
    by_id = {c["record_id"]: c for c in idx["candidates"]}
    keys = [k["key"] for k in idx.get("contract", []) if k.get("key") != "__implicit__"]
    merged = sum(1 for r in rows if r.get("duplicate_of"))
    with_quote = [r for r in rows if (r.get("reason") or {}).get("evidence_quote")]
    bad = [r["record_id"] for r in with_quote
           if not A.quote_check(by_id.get(r["record_id"], {}), (r.get("reason") or {}).get("evidence_quote"))[0]]
    recomputed = [r["record_id"] for r in A.rank_rows([dict(r, rank=None) for r in rows],
                                                      int(idx["criteria"].get("k") or 10))[0]]
    actual = [r["record_id"] for r in sorted([r for r in rows if r.get("rank")], key=lambda x: x["rank"])]
    checks = [
        ("result_json_parses", isinstance(res, dict) and bool(res), ""),
        ("contract_keys_present", all(k in res for k in keys),
         ("%d keys" % len(keys)) if all(k in res for k in keys)
         else "missing: " + ",".join([k for k in keys if k not in res][:6])),
        ("status_is_enum_string", res.get("status") in A.STATUS_SET, str(res.get("status"))),
        ("case_id_present", bool(res.get("case_id")), str(res.get("case_id"))),
        ("screening_covers_all_candidates", len(rows) == idx["counts"]["candidates"],
         "rows=%d candidates=%d" % (len(rows), idx["counts"]["candidates"])),
        ("quotes_verified", sum(1 for r in rows if (r.get("reason") or {}).get("quote_verified")) == len(with_quote),
         "%d verified / %d quoted" % (sum(1 for r in rows if (r.get("reason") or {}).get("quote_verified")), len(with_quote))),
        ("quotes_recheck_against_source", not bad, "not found: " + ",".join(bad[:5]) if bad else "all hit"),
        ("ranking_recomputable", recomputed == actual, "%d vs %d" % (len(recomputed), len(actual))),
        ("duplicate_links_valid", all((r.get("duplicate_of") is None) or (r.get("duplicate_of") in by_id) for r in rows), ""),
        ("merge_accounting", merged == sum(len(c.get("merged") or []) for c in idx.get("clusters") or []),
         "rows=%d clusters=%d" % (merged, sum(len(c.get("merged") or []) for c in idx.get("clusters") or []))),
        ("labels_in_enum", all(r.get("label") in A.LABELS for r in rows), ""),
        ("no_fabricated_candidates", set(r["record_id"] for r in rows) <= set(by_id), "no id outside input"),
        ("report_present", len(C.read_text(out / "screening_report.md")) > 200, ""),
    ]
    checks = [{"check": c[0], "pass": bool(c[1]), "detail": c[2] or ""} for c in checks]
    ok = all(c["pass"] for c in checks)
    C.jwrite(out / "selfcheck.json", {"case_id": idx.get("case_id"), "status": res.get("status"), "checks": checks,
                                      "pass": ok, "passed": sum(1 for c in checks if c["pass"]), "total": len(checks),
                                      "at": time.strftime("%F %T")})
    print("=" * 78)
    print("selfcheck: %s (%d/%d)" % ("PASS" if ok else "ATTENTION",
                                     sum(1 for c in checks if c["pass"]), len(checks)))
    for c in checks:
        print("  [%s] %-32s %s" % ("ok" if c["pass"] else "!!", c["check"], c["detail"]))
    print("written: %s" % (out / "selfcheck.json"))
    print("=" * 78)
    return checks


# ------------------------------------------------------------------ main
def ctx_dirs(args):
    inp = C.pick_input(args.input)
    out = C.pick_output(args.output)
    work = C.pick_work(args.work)
    return inp, out, work


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Screen + rank candidate literature with traceable evidence. Commands: "
                    "init | show | check | build | selfcheck. Exit code is always 0.")
    ap.add_argument("command", nargs="?", default="build",
                    choices=["init", "show", "check", "build", "selfcheck", "all"])
    ap.add_argument("--input", default=None, help="input dir (default /input -> /app/input -> ./input)")
    ap.add_argument("--output", default=None, help="output dir (default /app/output -> ./output)")
    ap.add_argument("--work", default=None, help="work dir (default /app/work -> ./work)")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--page-size", dest="page_size", type=int, default=15)
    ap.add_argument("--ids", default=None, help="show only these record ids (comma separated)")
    ap.add_argument("--full", action="store_true", help="print full abstracts")
    ap.add_argument("--chars", type=int, default=600, help="abstract chars in show (default 600)")
    ap.add_argument("--criteria", action="store_true", help="show only criteria block")
    ap.add_argument("--picks", action="store_true", help="show only records still missing a draft judgement")
    args = ap.parse_args(argv)
    ctx = ctx_dirs(args)
    P.H.update({"now": now, "dedupe_degr": dedupe_degr, "envelope_from": envelope_from,
              "finalize": finalize, "refresh_contract": refresh_contract,
              "load_index": load_index, "load_drafts": load_drafts})
    cmd = {"init": cmd_init, "show": cmd_show, "check": P.cmd_check, "build": P.cmd_build,
           "selfcheck": cmd_selfcheck}.get(args.command)
    try:
        if args.command == "all":
            cmd_init(args, ctx)
            P.cmd_build(args, ctx)
            cmd_selfcheck(args, ctx)
        else:
            cmd(args, ctx)
    except Exception as exc:
        try:
            out = ctx[1]
            res = A.envelope("unknown", "partial", [])
            res["errors"].append({"stage": "main", "command": args.command, "issue": "fatal",
                                  "detail": "%s: %s" % (type(exc).__name__, str(exc)[:200]),
                                  "trace": traceback.format_exc(limit=3)})
            finalize(out, res)
            print("fatal error captured -> partial result.json written: %s" % exc, file=sys.stderr)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
