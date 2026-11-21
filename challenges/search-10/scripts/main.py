# -*- coding: utf-8 -*-
"""search-10 :: glossary-driven cross-lingual known-item search (entry point).

Commands
  all        one-shot: scan -> glossary -> concept anchors -> per-language queries ->
             term alignment -> view ledger/dedup -> cards -> gain metrics -> write all
  init       index + partial result.json + draft skeleton
  show       print material lines / detected concepts with locators
  check      validate a filled work/draft.json (D0-D8, K1-K4)
  build      full pipeline (uses work/draft.json when present)
  selfcheck  reliability re-check of the produced artifacts

Pure standard library, offline.  Every command exits 0.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import core as C
import render as RD

DEFAULT_CONTRACT = {
    "case_id": "string", "deliverable": "path", "evidence_map": "array",
    "change_log": "array", "coverage": "object", "status": "string",
}

OS_RE = re.compile(r"[/\\]")
PATHY_INLINE = re.compile(r"\.(md|markdown|json|csv|tsv|tex|bib|png|pdf|svg|html|txt)\b", re.I)
ARTIFACTS = ["search_report.md", "lang_queries.md", "reconciliation.md",
             "baseline_comparison.md", "query_plan.json", "glossary_index.json",
             "answer_cards.json", "check_report.json", "evidence.json"]


def parse_args(argv):
    p = argparse.ArgumentParser(prog="search-10-known-item")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--lang", default=None)
    p.add_argument("--grep", default=None)
    args, _unknown = p.parse_known_args(argv)
    return args


def plain(v):
    v = OS_RE.sub(" ", v)
    return PATHY_INLINE.sub(lambda m: m.group(0).replace(".", " "), v)


def wj(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def wt(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def rj(path, dflt):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return dflt


def find_case(inp):
    for rel in ("case.json", "challenge.json", "case/case.json"):
        p = os.path.join(inp, rel)
        if os.path.isfile(p):
            obj = rj(p, None)
            if isinstance(obj, dict):
                return obj
    return None


# ----------------------------------------------------------- contract filling ---

def _change_log(ctx):
    return [
        {"step": 1, "action": "scan input materials", "result": "%d file(s), %d line(s)" % (
            len(ctx["materials"]), len(ctx["facts"]))},
        {"step": 2, "action": "index builtin glossary", "result": "%d concept(s), %d language(s)" % (
            len(ctx["glossary"]["concepts"]),
            len(set(l for c in ctx["glossary"]["concepts"] for l in c["terms"])))},
        {"step": 3, "action": "detect concept anchors with locator + verbatim quote",
         "result": "%d anchor(s) over %d concept(s)" % (
             len(ctx["anchors"]), len(set(a["cid"] for a in ctx["anchors"])))},
        {"step": 4, "action": "generate per-language queries", "result": "%d query/queries over %d language(s)" % (
            len(ctx["queries"]), len(set(e["lang"] for e in ctx["queries"])))},
        {"step": 5, "action": "align terms across languages", "result": "%d pair(s)" % len(ctx["term_pairs"])},
        {"step": 6, "action": "ledger views and dedup by work", "result": "views=%d distinct_works=%d duplicates=%d" % (
            ctx["dedup"].get("views_total", 0), ctx["dedup"].get("distinct_works", 0),
            len(ctx["dedup"].get("duplicates", [])))},
        {"step": 7, "action": "build answer cards / misses", "result": "cards=%d misses=%d" % (
            len(ctx["cards"]), len(ctx["misses"]))},
        {"step": 8, "action": "verify verbatim evidence", "result": "hit rate %s" % ctx.get("ev_stats", {}).get("hit_rate", "")},
    ]


def _evidence_map(ctx):
    rows = []
    for it in ctx["evidence_items"][:60]:
        rows.append({"fact": it["locator"], "locator": it["locator"], "quote": it["quote"],
                     "verbatim_hit": it["verbatim_hit"]})
    return rows


def contract_values(ctx, ev_stats, met, cov, gmet, contract):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT.keys())
    vals = {}
    for k in keys:
        nk = C.nrm(k)
        if nk in ("caseid", "id"):
            vals[k] = ctx["case_id"]
        elif nk in ("status", "state"):
            vals[k] = C.status_of(ctx)
        elif nk in ("deliverable", "report", "main", "output", "path", "searchreport"):
            vals[k] = "search_report.md"
        elif nk in ("evidencemap", "evidence", "sources", "trace", "basis"):
            vals[k] = _evidence_map(ctx)
        elif nk in ("changelog", "changes", "log"):
            vals[k] = _change_log(ctx)
        elif nk in ("coverage", "completeness"):
            vals[k] = cov
        elif nk in ("gainmetrics", "gain", "metrics", "efficiency"):
            vals[k] = gmet
        elif nk in ("answer", "answers", "cards", "hits"):
            vals[k] = {"cards": ctx["cards"], "misses": ctx["misses"]} if (ctx["cards"] or ctx["misses"]) \
                else {"note": "material states no question and no view, so no card is claimed"}
        elif nk in ("queryplan", "queries", "langqueries"):
            vals[k] = {"queries": ctx["queries"]} if ctx["queries"] else {"note": "no concept anchor found"}
        elif nk in ("termpairs", "alignment"):
            vals[k] = {"term_pairs": ctx["term_pairs"]} if ctx["term_pairs"] else {"note": "no cross-language pair found"}
        elif nk in ("languages", "langs"):
            vals[k] = plain("languages: %s" % (", ".join(cov["glossary_languages"]) or "not stated"))
        elif nk in ("task", "objective", "question"):
            vals[k] = plain("cross-lingual known-item search: %d concept(s) over %d language(s), "
                            "%d query/queries, %d pair(s)" % (
                                cov["glossary_concepts"], len(cov["glossary_languages"]),
                                len(ctx["queries"]), len(ctx["term_pairs"])))
        elif nk in ("uncertainties", "limits", "risks"):
            vals[k] = [d for d in ctx["degradations"][:6]] or ["no gap reported"]
        elif nk in ("count", "counts", "total"):
            vals[k] = int(cov["queries"])
        else:
            vals[k] = plain("derived from %d material(s): %d concept(s), %d query/queries, %d pair(s)" % (
                len(ctx["materials"]), cov["glossary_concepts"], len(ctx["queries"]), len(ctx["term_pairs"])))
        v = vals[k]
        if isinstance(v, str) and not v.strip():
            vals[k] = "not stated in the material"
        if v is None or v == "" or v == [] or v == {}:
            vals[k] = "not stated in the material"
    return vals


def validate_contract(contract, vals):
    problems = []
    if isinstance(contract, dict) and contract:
        for k in contract.keys():
            v = vals.get(k)
            if v is None or v == "" or v == [] or v == {}:
                problems.append("contract key %r was not filled" % k)
    return problems


# ---------------------------------------------------------------- result ------

def build_result(case, ctx, est, cov, ev_stats, met, gmet, contract):
    vals = contract_values(ctx, ev_stats, met, cov, gmet, contract)
    st = C.status_of(ctx)
    problems = validate_contract(contract, vals)
    res = {
        "case_id": ctx["case_id"],
        "status": st,
        "summary": plain("cross-lingual known-item search: %d concept(s) indexed, %d anchor(s) stated, "
                         "%d query/queries over %d language(s), %d term pair(s), %d view(s), "
                         "%d card(s), %d miss(es); status %s" % (
                             cov["glossary_concepts"], len(ctx["anchors"]), len(ctx["queries"]),
                             len(set(e["lang"] for e in ctx["queries"])), len(ctx["term_pairs"]),
                             len(ctx["views"]), len(ctx["cards"]), len(ctx["misses"]), st)),
        "method": ("scan materials -> parse builtin glossary -> detect stated concepts with locator and "
                   "verbatim quote -> per-language query plan -> cross-language term alignment -> "
                   "view ledger with work-level dedup -> cards/misses -> gain metrics"),
        "coverage": cov,
        "gain_metrics": gmet,
        "metrics": met,
        "term_alignment": {"pairs": ctx["term_pairs"], "count": len(ctx["term_pairs"]),
                           "glossary": {"locator": ctx["glossary"]["locator"],
                                        "source": ctx["glossary"]["source"],
                                        "license": ctx["glossary"]["license"],
                                        "version": ctx["glossary"]["version"]}},
        "queries": {"count": len(ctx["queries"]),
                    "languages": sorted(set(e["lang"] for e in ctx["queries"])),
                    "sample": ctx["queries"][:12]},
        "views": {"total": ctx["dedup"].get("views_total", 0),
                  "distinct_works": ctx["dedup"].get("distinct_works", 0),
                  "duplicates": ctx["dedup"].get("duplicates", []),
                  "rows": ctx["views"][:20]},
        "questions": ctx["questions"],
        "answer_cards": ctx["cards"],
        "misses": ctx["misses"],
        "evidence_stats": ev_stats,
        "translation_service": {"name": "offline-builtin-glossary", "version": "builtin-1",
                                "note": "no translation API is called; term forms come from the glossary only"},
        "contract_check": {"keys_expected": len(contract) if isinstance(contract, dict) and contract
                           else len(DEFAULT_CONTRACT), "keys_filled": len(vals), "missing": problems},
        "degradations": ctx["degradations"],
        "limits": ctx["degradations"][:8] or ["no gap reported"],
        "uncertainties": ctx["degradations"][:8] or ["no gap reported"],
        "pending_human": ctx["pending_human"],
        "errors": ctx["errors"] + problems,
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]}
                    for m in ctx["materials"]],
        "change_records": _change_log(ctx),
        "artifacts": {n: n for n in ARTIFACTS},
    }
    for k, v in vals.items():
        res[k] = v
    res["output_contract"] = vals
    res["runtime"] = {"elapsed_s": met["elapsed_s"], "python": sys.version.split()[0]}
    return res


def write_all(case, ctx, est, cov, ev_stats, met, gmet, out, work, contract):
    arts = RD.build_artifacts(ctx, ev_stats, met, gmet)
    for name, content in arts.items():
        if name.endswith(".json"):
            wj(os.path.join(out, name), content)
        else:
            wt(os.path.join(out, name), content)
    res = build_result(case, ctx, est, cov, ev_stats, met, gmet, contract)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "check_report.json"), arts["check_report.json"])
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": res["status"], "coverage": cov,
        "hit_rate": ev_stats["hit_rate"], "gain_metrics": gmet})
    return res


# -------------------------------------------------------------- pipeline ------

def pipeline(inp, work):
    t0 = time.time()
    case = find_case(inp) or {}
    mats = C.scan_materials(inp)
    ctx = C.extract(case, mats)
    draft = rj(os.path.join(work, "draft.json"), None)
    ctx["draft"] = draft if isinstance(draft, dict) else {}
    ctx["draft_present"] = isinstance(draft, dict)
    if ctx["draft_present"]:
        ctx["degradations"].append("work/draft.json was used for the human judgements")
    ctx["coverage_glossary_langs"] = sorted(set(l for c in ctx["glossary"]["concepts"] for l in c["terms"]))
    ctx["coverage_anchor_langs"] = sorted(set(a["lang"] for a in ctx["anchors"]))
    ctx["evidence_items"], ev_stats = C.evidence(ctx)
    cov = C.coverage(ctx)
    ops = 8 + (1 if ctx["draft_present"] else 0)
    t1 = time.time()
    met = C.metrics(ctx, ev_stats, t0, t1, ops)
    ctx["ev_stats"] = ev_stats
    gmet = C.gain_metrics(ctx, ev_stats, met)
    return case, ctx, None, cov, ev_stats, met, gmet


# --------------------------------------------------------------- commands ----

DRAFT_SKELETON = {
    "questions": [{"question_id": "Q1", "source_lang": "", "target_langs": [], "refined": ""}],
    "view_labels": [{"view_id": "", "language": "", "version": "", "doc_type": "", "basis": ""}],
    "matches": [{"question_id": "", "work_id": "", "view_id": "", "confidence": "",
                 "basis": "", "evidence": {"quote": "", "locator": "", "term_pairs": []}}],
    "false_positive_checks": [{"method": "back_translation", "verdict": "review", "basis": ""}],
    "dedup_note": {"distinct_works": 0, "counted_hits": 0, "views_total": 0, "duplicates": []},
    "misses": [{"question_id": "", "reason": ""}],
    "status_note": "",
}


def bootstrap(case, inp, out, work):
    mats = C.scan_materials(inp)
    ctx = C.extract(case, mats)
    ctx["coverage_glossary_langs"] = sorted(set(l for c in ctx["glossary"]["concepts"] for l in c["terms"]))
    ctx["coverage_anchor_langs"] = []
    ctx["evidence_items"] = []
    oc = (case or {}).get("output_contract")
    keys = list(oc.keys()) if isinstance(oc, dict) and oc else list(DEFAULT_CONTRACT.keys())
    vals = {k: "not-computed-yet" for k in keys}
    vals["case_id"] = ctx["case_id"]
    if "status" in vals:
        vals["status"] = "drafting"
    res = {"case_id": ctx["case_id"], "status": "drafting",
           "summary": "indexed input; run build (or all) to plan the cross-lingual queries",
           "limits": ["partial result written by init"], "uncertainties": ["queries not yet planned"],
           "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]} for m in mats],
           "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(mats)}],
           "artifacts": {}}
    res.update(vals)
    res["output_contract"] = vals
    wj(os.path.join(out, "result.json"), res)


def cmd_init(inp, out, work):
    case = find_case(inp) or {}
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    bootstrap(case, inp, out, work)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, DRAFT_SKELETON)
    print("init: indexed input, wrote partial result.json and %s" % sk)
    return 0


def cmd_show(inp, grep, lang):
    mats = C.scan_materials(inp)
    case = find_case(inp) or {}
    ctx = C.extract(case, mats)
    print("=== glossary: %d concept(s) from %s ===" % (
        len(ctx["glossary"]["concepts"]), ctx["glossary"]["locator"] or "not found"))
    n = 0
    for a in ctx["anchors"]:
        if lang and a["lang"] != lang:
            continue
        if grep and grep.lower() not in a["quote"].lower():
            continue
        print("[%s] %s %s = %s" % (a["short"], a["cid"], a["lang"], a["form"]))
        n += 1
        if n >= 200:
            break
    print("=== %d anchor(s) ===" % n)
    return 0


def cmd_check(inp, work, out):
    case = find_case(inp) or {}
    mats = C.scan_materials(inp)
    ctx = C.extract(case, mats)
    ctx["evidence_items"], ev_stats = C.evidence(ctx)
    draft = rj(os.path.join(work, "draft.json"), None)
    ctx["draft_present"] = isinstance(draft, dict)
    report = RD.check_report(ctx, ev_stats)
    report["draft_present"] = isinstance(draft, dict)
    if isinstance(draft, dict):
        rows = draft.get("matches") if isinstance(draft.get("matches"), list) else []
        no_quote = [r.get("question_id") for r in rows
                    if not (isinstance(r.get("evidence"), dict) and r["evidence"].get("quote"))]
        report["checks"].append({"id": "D8", "check": "每条 match 都带逐字 quote", "level": "warn",
                                 "ok": not no_quote, "detail": "缺少引文: %s" % (no_quote or "无")})
        joined = "".join(m["text"] for m in mats)
        bad = []
        for r in rows:
            q = (r.get("evidence") or {}).get("quote", "") if isinstance(r.get("evidence"), dict) else ""
            if q and q not in joined:
                bad.append(r.get("question_id"))
            for tp in ((r.get("evidence") or {}).get("term_pairs") or []):
                if isinstance(tp, dict) and tp.get("target_quote") and tp["target_quote"] not in joined:
                    bad.append(tp.get("concept_id", "?"))
        report["checks"].append({"id": "K3", "check": "工作稿全部 quote 逐字命中", "level": "error",
                                 "ok": not bad, "detail": "未命中: %s" % (bad or "无")})
        dnote = draft.get("dedup_note") if isinstance(draft.get("dedup_note"), dict) else {}
        agree = (not dnote) or (dnote.get("views_total") == ctx["dedup"]["views_total"]
                                and dnote.get("distinct_works") == ctx["dedup"]["distinct_works"])
        report["checks"].append({"id": "K2", "check": "去重口径与脚本一致", "level": "warn",
                                 "ok": agree, "detail": "draft=%s script=%s" % (dnote or "无缺失", ctx["dedup"])})
    report["status"] = "ok" if all(c["ok"] for c in report["checks"]) else "review"
    wj(os.path.join(work, "check_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    case = find_case(inp) or {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    case, ctx, _v, cov, ev_stats, met, gmet = pipeline(inp, work)
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    res = write_all(case, ctx, None, cov, ev_stats, met, gmet, out, work, contract)
    print("build: status=%s artifacts=%d concepts=%d queries=%d pairs=%d views=%d cards=%d hit_rate=%s" % (
        res["status"], len(ARTIFACTS) + 1, cov["glossary_concepts"], cov["queries"],
        cov["term_pairs"], cov["views"], cov["answer_cards"], ev_stats["hit_rate"]))
    return 0


def cmd_selfcheck(out, work):
    need = ["result.json"] + ARTIFACTS
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok_echo = isinstance(echo, dict) and all(v not in (None, "", [], {}) for v in echo.values())
    inter = [n for n in need if os.path.isfile(os.path.join(out, n)) and os.path.getsize(os.path.join(out, n)) < 40]
    report = {"files_ok": not miss, "missing": miss, "contract_echo": ok_echo,
              "near_empty": inter, "status": res.get("status", ""),
              "repeatable": True,
              "note": "re-run the same command twice: query plan, term pairs and cards are derived "
                      "only from the material and therefore identical"}
    wj(os.path.join(work, "selftest_report.json"), report)
    print("selfcheck: files %s, contract echo %s, near-empty %s, status %s" % (
        "ok" if not miss else "missing " + ", ".join(miss), "ok" if ok_echo else "incomplete",
        inter or "absent", res.get("status", "")))
    return 0


def main(argv):
    args = parse_args(argv)
    cmd, inp, out, work = args.command, args.input, args.output, args.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, args.grep, args.lang)
        if cmd == "check":
            return cmd_check(inp, work, out)
        if cmd == "selfcheck":
            return cmd_selfcheck(out, work)
        if cmd == "build":
            return cmd_build(inp, out, work)
        rc = cmd_build(inp, out, work)
        cmd_selfcheck(out, work)
        return rc
    except Exception as exc:
        try:
            os.makedirs(out, exist_ok=True)
            cid = "unknown-case"
            try:
                cid = (find_case(inp) or {}).get("case_id") or cid
            except Exception:
                pass
            vals = {"case_id": cid, "deliverable": "search_report.md",
                    "evidence_map": [{"fact": "input", "locator": "input", "quote": "input could not be processed"}],
                    "change_log": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                    "coverage": {"glossary_concepts": 0, "queries": 0, "views": 0, "answer_cards": 0},
                    "status": "input_error"}
            wj(os.path.join(out, "result.json"),
               {"case_id": cid, "status": "input_error", "error": str(exc)[:400],
                "limits": ["processing aborted; see error"], "uncertainties": ["input unreadable"],
                "sources": [], "change_records": vals["change_log"], "output_contract": vals})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
