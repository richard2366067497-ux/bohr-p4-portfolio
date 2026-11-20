#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""federated-search-reconcile :: entry point.

    main.py init      -> index /input, write a legal partial result.json first
    main.py show      -> print databases, records, candidate pairs, field views
    main.py check     -> verify the agent draft against real sources
    main.py build     -> assemble the five pieces + final result.json (always finalize)
    main.py selfcheck -> re-verify the emitted package

Exit code is always 0; every failure is caught, recorded and degraded.
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L          # noqa: E402
import matrix as M          # noqa: E402
import pack as P            # noqa: E402
import render as R          # noqa: E402

V = "1.0.0"
ROOT = Path(__file__).resolve().parent.parent
T0 = time.time()
BUDGET = 780.0


def log(m):
    print(m, flush=True)


def writable(d):
    try:
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        t = d / ".write_probe"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return True
    except Exception:
        return False


def resolve(args):
    deg = []
    inp = Path(args.input) if args.input else Path("/input")
    if not inp.is_dir() and (ROOT / "_input").is_dir():
        inp = ROOT / "_input"
        deg.append({"stage": "paths", "note": "input fallback to package _input"})
    if not inp.is_dir():
        deg.append({"stage": "paths", "note": "input directory %s not found" % inp})
    cands = [Path(args.work) if args.work else Path("/app/work"), ROOT / "_work", Path.cwd() / "_work"]
    work = next((c for c in cands if writable(c)), cands[-1])
    if str(work) != str(cands[0]):
        deg.append({"stage": "paths", "note": "work dir fallback to %s" % work})
    oc = [Path(args.output) if args.output else Path("/app/output"), ROOT / "_output",
          Path.cwd() / "_output"]
    out = next((c for c in oc if writable(c)), oc[-1])
    if str(out) != str(oc[0]):
        deg.append({"stage": "paths", "note": "output dir fallback to %s" % out})
    return inp, work, out, deg


# --------------------------------------------------------------- result writing
def envelope(case, status, errors, degradations, assumptions, extra=None):
    res = {}
    try:
        items = R.contract_items((case or {}).get("output_contract"))
    except Exception:
        items = []
    for k, spec in items:
        res[k] = [] if isinstance(spec, (list, tuple)) else None
    res.update(case_id=(case or {}).get("case_id"), status=status, errors=errors,
               degradations=degradations, assumptions=assumptions,
               runtime={"elapsed_s": round(time.time() - T0, 2), "python": sys.version.split()[0],
                        "skill_version": V, "llm_requests": 0},
               counts={"contract_keys": len(items)})
    if extra:
        res.update(extra)
    return res


def write_result(out, res, errors):
    try:
        (Path(out) / "result.json").write_text(L.jd(res), encoding="utf-8")
        return True
    except Exception as e:
        errors.append({"stage": "write", "error": str(e)})
        try:
            (Path(out) / "result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            log("[warn] cannot write result.json: %s" % e)
            log(json.dumps(res, ensure_ascii=False)[:4000])
            return False


def load_idx(work, inp, force=False):
    p = Path(work) / "index.json"
    if p.is_file() and not force:
        try:
            idx = json.loads(p.read_text("utf-8"))
            if idx.get("records") is not None:
                idx["input"] = str(inp)
                return idx, True
        except Exception:
            pass
    idx = L.build_index(inp)
    try:
        p.write_text(L.jd(idx), encoding="utf-8")
    except Exception:
        pass
    return idx, False


def load_draft(path, errors, degradations):
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        degradations.append({"stage": "draft", "note": "draft not found at %s; build runs in fallback mode" % p})
        return {}
    try:
        d = json.loads(p.read_text("utf-8"))
    except Exception as e:
        errors.append({"stage": "draft", "path": str(p), "error": "bad json: %s" % e})
        return {}
    if isinstance(d, dict) and isinstance(d.get("draft"), dict):
        d = d["draft"]
    if not isinstance(d, dict):
        errors.append({"stage": "draft", "path": str(p), "error": "draft root must be an object"})
        return {}
    return d


def state(idx):
    pairs = M.candidates(idx["records"])
    return pairs


# ------------------------------------------------------------------- subcommands
def cmd_init(args):
    errors, degradations, assumptions = [], [], []
    inp, work, out, deg = resolve(args)
    degradations += deg
    case = {}
    try:
        case, _, cerr = L.find_case(inp)
        errors += cerr
        case = case or {}
    except Exception as e:
        errors.append({"stage": "case", "error": str(e)})
    write_result(out, envelope(case, "partial", errors, degradations + [
        {"stage": "init", "note": "partial scaffold written before parsing; build will finalize"}],
        assumptions), errors)
    idx = L.build_index(inp)
    errors += [e for e in idx.get("errors", []) if e not in errors]
    degradations += idx.get("degradations", [])
    assumptions += idx.get("assumptions", [])
    try:
        (Path(work) / "index.json").write_text(L.jd(idx), encoding="utf-8")
    except Exception as e:
        errors.append({"stage": "cache", "error": str(e)})
    pairs = M.candidates(idx["records"])
    dup = len([p for p in pairs if p["rule_decision"] == "duplicate"])
    write_result(out, envelope(idx["case"], "partial", errors, degradations, assumptions,
                               extra={"counts": {"files": len(idx["files"]), "records": len(idx["records"]),
                                                 "databases": len({r["db"] for r in idx["records"]}),
                                                 "candidate_pairs": len(pairs), "rule_duplicates": dup}}), errors)
    log("[init] input=%s work=%s output=%s" % (inp, work, out))
    log("[init] files=%d records=%d databases=%s pairs=%d rule_duplicates=%d"
        % (len(idx["files"]), len(idx["records"]),
           ",".join(sorted({r["db"] for r in idx["records"]})) or "-", len(pairs), dup))
    for f in idx["files"]:
        log("       %-46s %-8s %-14s rec=%-3d %s" % (f["path"][:46], f["db"], f["kind"],
                                                     f["n_records"], L.clip(f.get("note") or "", 60)))
    for f in idx.get("failures", []):
        log("       [FAILED] %s (%s) %s" % (f.get("path"), f.get("http_status") or "-", f.get("reason")))
    log("[init] partial result.json written -> %s/result.json" % out)
    log("[next] python3 scripts/main.py show   # read the material, then write draft.json")
    return 0


def cmd_show(args):
    errors, degradations = [], []
    inp, work, out, deg = resolve(args)
    degradations += deg
    idx, cached = load_idx(work, inp)
    pairs = M.candidates(idx["records"])
    clusters, decided = M.build_clusters(idx["records"], pairs, {})
    merged = M.merge_clusters(clusters, [])
    cov = M.coverage_rows(idx, merged)
    vs = {x.strip() for x in (args.view or "all").split(",") if x.strip()}
    va = "all" in vs
    v = args.view or "all"
    if va or "files" in vs:
        log("== files ==")
        for f in idx["files"]:
            log("  %-44s %-8s %-6s shape=%-22s rec=%-3d sha=%s"
                % (f["path"][:44], f["db"], f["kind"], (f.get("shape") or "-")[:22], f["n_records"],
                   f["sha256"][:12]))
        for f in idx.get("failures", []):
            log("  [FAILED] %s (%s) %s" % (f.get("path"), f.get("http_status") or "-", f.get("reason")))
    if va or "records" in vs:
        log("\n== records (locator + verbatim raw snippet) ==")
        for r in idx["records"][:args.limit]:
            log("  %s [%s] %s" % (r["rid"], r["db"], r["locator"]))
            log("      raw: %s" % L.clip(r["raw"], 240))
            for f in M.COV:
                fl = r["fields"].get(f) or {}
                log("      %-8s %-8s %-28s %s" % (f, fl.get("state"), L.clip(fl.get("src_field") or "-", 28),
                                                  L.clip(fl.get("value") if not isinstance(fl.get("value"), list)
                                                         else " | ".join(fl["value"]), 90)))
    if va or "pairs" in vs:
        log("\n== candidate pairs (rubric-recomputable votes) ==")
        for p in pairs[:args.limit]:
            log("  %s %s~%s score=%d rule=%s" % (p["pair_id"], p["a"], p["b"], p["score"], p["rule_decision"]))
            log("      %s" % p["reason"])
    if va or "conflicts" in vs:
        log("\n== field conflicts (default precedence) ==")
        n = 0
        for c in merged:
            for cf in c["conflicts"]:
                n += 1
                if n <= args.limit:
                    log("  %s %-8s chosen=%s (rule %s, from %s)"
                        % (c["cluster_id"], cf["field"], L.clip(cf["chosen"], 90), cf["rule"],
                           cf["chosen_rid"]))
                    for rid, val in cf["values"].items():
                        log("      %s -> %s" % (rid, L.clip(val, 90)))
        log("  total conflicts: %d" % n)
    if va or "coverage" in vs:
        log("\n== coverage (db x field, P/M/S/U) ==")
        log("  %-16s %-6s %s" % ("db", "recs", " ".join("%-9s" % f for f in M.COV)))
        for r in cov["rows"]:
            cells = " ".join("%-9s" % ("%d/%d/%d/%d" % (r["cells"][f]["present"], r["cells"][f]["missing"],
                                                        r["cells"][f]["suspect"], r["cells"][f]["unknown"]))
                             for f in M.COV)
            log("  %-16s %-6d %s" % (r["db"], r["records"], cells))
        log("  single-db clusters: %d  systematic missing: %s"
            % (len(cov["single_db_clusters"]), ", ".join(s["field"] for s in cov["systematic_missing"]) or "none"))
    if va or "queries" in vs:
        rows, dupq = M.query_rows(idx, merged, {})
        log("\n== query matrix ==")
        for r in rows:
            log("  %-16s origin=%-12s returned=%-3d %s" % (r["db"], r["query_origin"], r["returned"],
                                                           L.clip(r["query_sent"], 60) or "-"))
            if r["evidence_locator"]:
                log("      evidence: %s" % r["evidence_locator"])
        if dupq:
            log("  [same-query warning] %s" % "; ".join("%s->%s" % (d["query_prefix"][:40], ",".join(d["dbs"]))
                                                        for d in dupq))
    if va or "rules" in vs:
        log("\n== field mapping rules (declared precedence) ==")
        for rid, f, prec in (("N-01", "title", "non-suspect > db priority > longer"),
                             ("N-02", "authors", "structured family/given > db priority > more authors"),
                             ("N-03", "year", "db priority; tie -> earlier"),
                             ("N-04", "venue", "non-suspect > db priority > longer"),
                             ("N-05", "doi", "Crossref registrant form"),
                             ("N-06", "abstract", "db priority > longer")):
            log("  %s %-8s %s" % (rid, f, prec))
        log("  priority: " + ", ".join("%s=%d" % (k, v) for k, v in
                                       sorted(M.PRIO.items(), key=lambda kv: -kv[1])[:10]))
    if va or "contract" in vs:
        log("\n== output_contract keys and current semantic target ==")
        for k, spec in R.contract_items(idx["case"].get("output_contract")):
            tgt, why = R.infer_target(k, spec)
            log("  %-34s -> %-12s (%s)" % (k[:34], tgt or "UNMAPPED", why))
        if not R.contract_items(idx["case"].get("output_contract")):
            log("  (no output_contract in input)")
    log("\n[show] files=%d records=%d pairs=%d canonical=%d (cache=%s)"
        % (len(idx["files"]), len(idx["records"]), len(pairs), len(merged), cached))
    log("[next] write %s/draft.json  (schema: references/playbook.md B) then run check" % work)
    return 0


def cmd_check(args):
    errors, degradations, warnings = [], [], []
    inp, work, out, deg = resolve(args)
    degradations += deg
    idx, _ = load_idx(work, inp)
    draft_path = Path(args.draft) if args.draft else Path(work) / "draft.json"
    draft = load_draft(draft_path, errors, degradations)
    pairs = M.candidates(idx["records"])
    dmap, pairprob = M.decisions_map(pairs, draft)
    clusters, decided = M.build_clusters(idx["records"], pairs, dmap)
    merged = M.merge_clusters(clusters, draft.get("conflict_resolutions") or [])
    smap, sbad = P.screening_map(merged, draft)
    problems, checks = [], []
    need = ("research_question", "scope", "query_matrix_notes", "cluster_decisions",
            "conflict_resolutions", "screening", "coverage_notes", "gaps", "ranked")
    miss = [k for k in need if not draft.get(k)]
    checks.append({"id": "draft-present", "ok": bool(draft), "detail": str(draft_path)})
    checks.append({"id": "draft-sections", "ok": len(miss) <= 3,
                   "detail": "missing/empty: %s" % (", ".join(miss) or "none")})
    for k in miss:
        warnings.append({"item": k, "note": "draft section empty; corresponding judgement will stay degraded"})
    for p in pairprob:
        problems.append({"where": "cluster_decisions", **p})
    for p in sbad:
        problems.append({"where": "screening", **p})
    kd = {c["cluster_id"] for c in merged}
    for c in (draft.get("conflict_resolutions") or []):
        if isinstance(c, dict) and c.get("cluster") not in kd and c.get("cluster") != "*":
            problems.append({"where": "conflict_resolutions", "error": "unknown cluster %s" % c.get("cluster")})
    # locator replay for every locator string found in the draft
    tested = failed = 0
    seen = set()

    def walk(o):
        nonlocal tested, failed
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and "#" in o and len(o) < 300 and o not in seen:
            seen.add(o)
            rel, _, ptr = o.partition("#")
            if not (Path(inp) / rel).is_file():
                tested += 1
                failed += 1
                problems.append({"where": "locator", "locator": o, "error": "source file not found"})
                return
            tested += 1
            try:
                if not L.resolve(rel, ptr, inp):
                    failed += 1
                    problems.append({"where": "locator", "locator": o, "error": "pointer did not resolve"})
            except Exception as e:
                failed += 1
                problems.append({"where": "locator", "locator": o, "error": str(e)})
    walk(draft)
    # verbatim quote check
    qt = qf = 0
    cache = {}

    def qwalk(o):
        nonlocal qt, qf
        if isinstance(o, dict):
            q = o.get("quote")
            if isinstance(q, str) and len(q) > 8:
                qt += 1
                hit = False
                for f in idx["files"]:
                    p = Path(inp) / f["path"]
                    if p.is_file():
                        if f["path"] not in cache:
                            cache[f["path"]] = L.strip_tags(p.read_text("utf-8", "replace")).lower()
                        if q.strip().lower() in cache[f["path"]]:
                            hit = True
                            break
                if not hit:
                    qf += 1
                    warnings.append({"item": "quote", "note": "quote not found verbatim: %s" % L.clip(q, 80)})
            for v in o.values():
                qwalk(v)
        elif isinstance(o, list):
            for v in o:
                qwalk(v)
    qwalk(draft)
    # contract coverage
    citems = R.contract_items(idx["case"].get("output_contract"))
    unmapped = [k for k, spec in citems if not R.infer_target(k, spec)[0]]
    checks.append({"id": "contract-keys", "ok": bool(citems),
                   "detail": "%d keys, %d unmapped%s" % (len(citems), len(unmapped),
                                                         (": " + ", ".join(unmapped[:6])) if unmapped else "")})
    checks.append({"id": "locators", "ok": failed == 0, "detail": "%d tested, %d failed" % (tested, failed)})
    checks.append({"id": "quotes", "ok": qf == 0, "detail": "%d tested, %d not found" % (qt, qf)})
    checks.append({"id": "cluster-coverage", "ok": len(merged) > 0 or not idx["records"],
                   "detail": "%d canonical from %d raw" % (len(merged), len(idx["records"]))})
    rep = {"schema": "federated-search-reconcile/check@1", "skill_version": V,
           "draft": str(draft_path), "draft_present": bool(draft),
           "sections_missing": miss, "problems": problems[:80], "warnings": warnings[:40],
           "locators": {"tested": tested, "failed": failed}, "quotes": {"tested": qt, "not_found": qf},
           "contract": {"keys": len(citems), "unmapped": unmapped},
           "counts": {"records": len(idx["records"]), "pairs": len(pairs),
                      "duplicates": len([d for d in decided.values() if d.get("final_decision") == "duplicate"]),
                      "maybe": len([d for d in decided.values() if d.get("final_decision") == "maybe"]),
                      "canonical": len(merged), "screened": len(smap), "conflicts":
                      sum(len(c["conflicts"]) for c in merged)},
           "checks": checks}
    try:
        (Path(work) / "check_report.json").write_text(L.jd(rep), encoding="utf-8")
    except Exception as e:
        errors.append({"stage": "check", "error": str(e)})
    log("[check] draft=%s present=%s" % (draft_path, bool(draft)))
    for c in checks:
        log("  [%s] %-16s %s" % ("PASS" if c["ok"] else "FAIL", c["id"], c["detail"]))
    log("  counts: records=%d pairs=%d dup=%d maybe=%d canonical=%d screened=%d conflicts=%d"
        % (rep["counts"]["records"], rep["counts"]["pairs"], rep["counts"]["duplicates"],
           rep["counts"]["maybe"], rep["counts"]["canonical"], rep["counts"]["screened"],
           rep["counts"]["conflicts"]))
    for p in problems[:8]:
        log("  [problem] %s" % L.clip(p, 160))
    for e in errors[:6]:
        log("  [error] %s" % L.clip(e, 160))
    for w in warnings[:6]:
        log("  [warn] %s" % L.clip(w, 160))
    log("  report -> %s/check_report.json" % work)
    log("[next] fix the findings above, then run build")
    return 0


def cmd_build(args):
    errors, degradations, assumptions = [], [], []
    inp, work, out, deg = resolve(args)
    degradations += deg
    idx, _ = load_idx(work, inp)
    draft_path = Path(args.draft) if args.draft else Path(work) / "draft.json"
    draft = load_draft(draft_path, errors, degradations)
    errors += [e for e in idx.get("errors", []) if e not in errors]
    for d in idx.get("degradations", []):
        if d not in degradations:
            degradations.append(d)
    assumptions += idx.get("assumptions", [])
    if time.time() - T0 > BUDGET:
        degradations.append({"stage": "budget", "note": "time budget nearly exhausted; minimal finalize"})
    res, B, merged, stats, gaps, cov, qrows = P.assemble(idx, draft, out, errors, degradations, assumptions)
    if not draft:
        degradations.append({"stage": "build", "note": "fallback build: no draft.json, judgements are rule-only"})
    elif any("未记录相关性筛选" in (g.get("item") or "") for g in gaps):
        degradations.append({"stage": "build", "note": "no screening[] in draft; relevance left unscreened"})
    if idx.get("failures"):
        degradations.append({"stage": "build", "note": "%d database response(s) unusable; gaps reported"
                                                       % len(idx["failures"])})
    if res["status"] != "ok":
        degradations.append({"stage": "build", "note": "status=%s; see degradations and gaps" % res["status"]})
    res["runtime"] = {"elapsed_s": round(time.time() - T0, 2), "python": sys.version.split()[0],
                      "skill_version": V, "llm_requests": 0}
    res["errors"], res["degradations"], res["assumptions"] = errors, degradations, assumptions
    res["uncertainty"] = gaps[:60]
    res["five_pieces"] = {n: {"path": n, "bytes": len((Path(out) / n).read_text("utf-8").encode("utf-8"))
                              if (Path(out) / n).is_file() else 0} for n in R.PIECES}
    write_result(out, res, errors)
    log("[build] records=%d pairs=%d dup=%d maybe=%d canonical=%d conflicts=%d gaps=%d"
        % (stats["raw"], stats["pairs"], stats["dup"], stats["maybe"], stats["canonical"],
           res["counts"]["conflicts"], len(gaps)))
    log("[build] status=%s contract_keys=%d unmapped=%d"
        % (res["status"], len(R.contract_items(idx["case"].get("output_contract"))),
           len([m for m in res.get("contract_map", []) if not m.get("target")])))
    for n in R.PIECES:
        p = Path(out) / n
        log("        %-24s %6d bytes" % (n, p.stat().st_size if p.is_file() else 0))
    log("[build] output -> %s" % out)
    log("[next] python3 scripts/main.py selfcheck")
    return 0


def cmd_selfcheck(args):
    inp, work, out, deg = resolve(args)
    idx, _ = load_idx(work, inp)
    rep = P.selfcheck(idx, inp, work, out)
    for c in rep["checks"]:
        log("  [%s] %-20s %s" % ("PASS" if c["ok"] else "FAIL", c["id"], L.clip(c["detail"], 120)))
    log("[selfcheck] verdict=%s  report -> %s/selfcheck.json" % (rep["verdict"], work))
    return 0


def main():
    ap = argparse.ArgumentParser(description="multi-database search reconciler (search-05)")
    ap.add_argument("cmd", nargs="?", default="build",
                    choices=["init", "show", "check", "build", "selfcheck"], help="subcommand")
    ap.add_argument("--input", default=None, help="input dir (default /input)")
    ap.add_argument("--work", default=None, help="work dir (default /app/work)")
    ap.add_argument("--output", default=None, help="output dir (default /app/output)")
    ap.add_argument("--draft", default=None, help="draft path (default <work>/draft.json)")
    ap.add_argument("--view", default="all",
                    help="show view: all|files|records|pairs|conflicts|coverage|queries|rules|contract")
    ap.add_argument("--limit", type=int, default=40, help="max rows printed by show")
    a = ap.parse_args()
    fn = {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
          "selfcheck": cmd_selfcheck}[a.cmd]
    log("[%s] skill=federated-search-reconcile v%s" % (a.cmd, V))
    try:
        return fn(a)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            _, _, out, _ = resolve(a)
            rp = Path(out) / "result.json"
            keep = False
            try:
                keep = isinstance(json.loads(rp.read_text("utf-8")).get("counts"), dict)
            except Exception:
                keep = False
            if keep:
                rp = Path(out) / "result.error.json"
            rp.write_text(L.jd({"case_id": None, "status": "partial", "skill_version": V,
                               "errors": [{"stage": "fatal", "error": "%s: %s" % (type(e).__name__, e)}],
                              "degradations": [{"stage": "fatal",
                                                "note": "unhandled exception; degraded partial written"}]}),
                         [])
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
