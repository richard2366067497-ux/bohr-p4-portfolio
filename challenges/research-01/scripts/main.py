#!/usr/bin/env python3
"""main.py -- deep-research-evidence-map driver (Agent-led, stdlib only, exit code always 0).

  init       index every material into locator-bearing paragraphs, print the object table,
             write a legal partial /app/output/result.json FIRST
  show       print sources / records / contract / paragraphs so the Agent can quote verbatim
  check      validate /app/work/draft.json (schema, enums, dependency graph, quote anchoring,
             retrieval coverage, conflict bidirectionality, gap evidence, undeclared conflicts)
  build      render research_plan.json, evidence_matrix(.jsonl/.csv), synthesis.json,
             coverage.json, report.md and the final result.json (unconditional finalize,
             with a complete-but-degraded fallback when no draft exists)
  selfcheck  re-verify the written artifacts and contract completeness

Defaults: --input /input  --output /app/output  --work /app/work  (env SKILL_INPUT/OUTPUT/WORK).
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C
import validate as V
import build as B

GEN = C.GEN
DEFAULT_CONTRACT = ["case_id", "research_question", "sub_questions", "retrieval_plan", "tool_calls",
                    "evidence", "claims", "conflicts", "gaps", "uncertainties", "coverage", "sources",
                    "report", "status"]
QKEYS = ("research_question", "question", "research_question_original", "question_original", "topic",
         "research_topic", "task_question", "instruction_question")


def paths(a):
    return (Path(a.input or os.environ.get("SKILL_INPUT", "/input")),
            Path(a.output or os.environ.get("SKILL_OUTPUT", "/app/output")),
            Path(a.work or os.environ.get("SKILL_WORK", "/app/work")))


def find_case(inp, errs):
    """case.json -> any *.json with an output_contract; never assume the filename."""
    if not inp.exists():
        errs.append({"code": "input_missing", "detail": "input directory not found: %s (indexing skipped, partial result written)" % inp})
        return {}, None
    cand = []
    p = inp / "case.json"
    if p.exists():
        cand.append(p)
    cand += [q for q in sorted(inp.rglob("case*.json")) if q != p]
    strict = [q for q in cand]
    for q in strict:
        try:
            return C.jread(q), q
        except Exception as e:
            errs.append({"code": "case_json_invalid", "detail": "%s: %r" % (q, e)})
    for q in [q for q in sorted(inp.rglob("*.json")) if q not in cand]:
        try:
            o = C.jread(q)
        except Exception:
            continue
        if isinstance(o, dict) and ("output_contract" in o or "case_id" in o):
            errs.append({"code": "case_recovered", "detail": "case metadata recovered from %s (case.json absent)" % q.name})
            return o, q
    return {}, None


def recover_question(case, taskmd, degr):
    for k in QKEYS:
        if isinstance(case.get(k), str) and len(case[k].strip()) > 8:
            if k != "research_question":
                degr.append("research question recovered from case key %r" % k)
            return case[k].strip(), "case:" + k
    for k, v in C.walk(case):
        if k.lower() in QKEYS and isinstance(v, str) and len(v.strip()) > 12:
            degr.append("research question recovered from nested key %r" % k)
            return v.strip(), "case:" + k
    if taskmd:
        for line in taskmd.splitlines():
            s = line.strip().lstrip("#").strip()
            if len(s) > 12 and not s.startswith("|"):
                degr.append("research question recovered from task.md leading line (no explicit question field)")
                return s[:400], "task.md"
    degr.append("no research question could be recovered from case.json or task.md")
    return "", "none"


def materials(inp, case):
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    skip = re.compile(r"^(case.*\.json|task\.md|readme.*|.*\.pyc)$", re.I)
    text_ext = (".pdf", ".docx", ".txt", ".md", ".json", ".jsonl", ".csv", ".tsv", ".html", ".htm", ".xml")
    out = []
    rec = re.compile(r"record|candidate", re.I)
    proto = re.compile(r"(^|[^a-z])(protocol|protocols|screening[_-]?plan|eligibility|搜索方案|检索方案|纳排)", re.I)
    for p in files:
        rel = str(p.relative_to(inp))
        if skip.match(p.name) or "workorder" in p.name.lower():
            continue
        if p.suffix.lower() not in text_ext:
            continue
        if rec.search(p.name) and p.suffix.lower() in (".jsonl", ".csv", ".tsv"):
            continue  # consumed by the record loader, not cited as a source
        if proto.search(p.stem) and p.suffix.lower() in (".md", ".txt", ".json"):
            continue  # the search/screening protocol is a rule set, not an evidence source
        out.append(p)
    return out


def build_index(inp, errs, degr):
    t0 = time.time()
    case, cpath = find_case(inp, errs)
    taskmd = ""
    for cand in ([inp / "task.md"] + sorted(inp.rglob("task.md"))) if inp.exists() else []:
        if cand.exists():
            taskmd = cand.read_text(encoding="utf-8", errors="replace")
            break
    q, qsrc = recover_question(case, taskmd, degr)
    mat = materials(inp, case)
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    declared = []
    for k in ("sources", "source_list", "documents", "papers", "corpus", "materials"):
        v = case.get(k)
        if isinstance(v, list) and v:
            declared = v
            break

    docs, para_map, calls = {}, {}, []
    step = 0
    for i, p in enumerate(mat):
        sid = "S%d" % (i + 1)
        meta = next((d for d in declared if isinstance(d, dict) and
                     str(d.get("file") or d.get("filename") or d.get("path") or "").split("/")[-1].lower()
                     == p.name.lower()), None)
        if meta:
            sid = str(meta.get("source_id") or meta.get("paper_id") or meta.get("id") or sid)
        d, notes, retry = None, [], 0
        for attempt in (1, 2):
            try:
                d = C.extract_doc(p)
                if d["paras"]:
                    break
            except Exception as e:
                notes.append("attempt %d failed: %r" % (attempt, e))
            retry = attempt
        if d is None:
            d = {"kind": C.kind_of(p), "engine": "failed", "paras": [], "text": "", "n_units": 0,
                 "quality": 0.0, "notes": notes or ["extraction failed"]}
        step += 1
        calls.append({"step_id": "T%d" % step, "tool": "parse_pdf" if d["kind"] == "pdf" else "read_file",
                      "params": {"path": str(p), "source_id": sid}, "origin": "script",
                      "result_summary": "%s, %d paras, %d chars, engine=%s" % (d["kind"], len(d["paras"]), len(d["text"]), d["engine"]),
                      "status": "retried" if retry else ("ok" if d["paras"] else "failed"),
                      "retry_count": retry, "produced_artifact": "work/index.json#%s" % sid})
        d.update(filename=p.name, path=str(p), source_id=sid,
                 title=str((meta or {}).get("title") or (meta or {}).get("name") or p.stem),
                 declared=bool(meta), scheme="p{page}#para{n}" if d["kind"] in ("pdf", "docx") else "b{block}#para{n}")
        docs[sid] = d
        para_map[sid] = d["paras"]
        degr += ["%s: %s" % (p.name, n) for n in (d["notes"] or [])]
        if not d["paras"]:
            errs.append({"code": "source_unreadable", "detail": "%s: no text extracted (see degradations); excluded from evidence" % p.name})

    if declared and len(declared) == len(docs) and not any(d["declared"] for d in docs.values()):
        degr.append("declared source files could not be matched by name: source ids reassigned positionally from case.json order")
        remap = {}
        for (old, d), meta in zip(sorted(docs.items()), declared):
            new = str((meta or {}).get("source_id") or (meta or {}).get("paper_id") or (meta or {}).get("id") or old) \
                if isinstance(meta, dict) else old
            if new != old:
                remap[old] = new
        for old, new in remap.items():
            docs[new] = docs.pop(old)
            docs[new]["source_id"] = new
            para_map[new] = para_map.pop(old)
    records, rsrc, rnotes = C.load_records(files, case)
    degr += rnotes
    if records:
        step += 1
        calls.append({"step_id": "T%d" % step, "tool": "extract_table", "params": {"file": rsrc},
                      "origin": "script", "result_summary": "%d records loaded" % len(records),
                      "status": "ok", "retry_count": 0, "produced_artifact": "work/index.json#records"})
    protocol = ""
    for k in ("search_protocol", "protocol", "screening_plan", "retrieval_protocol"):
        v = case.get(k)
        if isinstance(v, str):
            protocol = v
            break
        if isinstance(v, (dict, list)):
            protocol = json.dumps(v, ensure_ascii=False)
            break
    if not protocol and inp.exists():
        for cand in sorted(inp.rglob("*protocol*")):
            if cand.is_file() and cand.suffix.lower() in (".md", ".txt", ".json"):
                protocol = cand.read_text(encoding="utf-8", errors="replace")[:20000]
                degr.append("search protocol read from file %s (not declared in case.json)" % cand.name)
                break
    constraints = case.get("constraints") or case.get("constraint") or case.get("limits") or {}
    contract = case.get("output_contract")
    if not isinstance(contract, (dict, list)) or not C.contract_keys(contract):
        degr.append("output_contract missing or empty: using the built-in 14-key generic contract")
        contract = dict((k, "string" if k in ("research_question", "report", "status", "case_id") else "array")
                        for k in DEFAULT_CONTRACT)
    cid = str(case.get("case_id") or case.get("id") or (cpath.parent.name if cpath else "unknown"))
    index = dict(case_id=cid, case_path=str(cpath or ""), question=q, question_source=qsrc,
                 contract=contract,
                 constraints=constraints if isinstance(constraints, (dict, list)) else {},
                 protocol=protocol[:20000],
                 sources_expected=len(declared) if declared else len(docs),
                 records_expected=len(records),
                 generated=time.strftime("%Y-%m-%dT%H:%M:%S"),
                 docs={k: dict((f, v.get(f)) for f in ("filename", "kind", "engine", "n_units", "quality", "notes",
                                                       "path", "source_id", "title", "declared", "scheme"))
                       for k, v in docs.items()},
                 paras=para_map,
                 texts={k: v["text"] for k, v in docs.items()},
                 records=records, records_source=rsrc,
                 tool_calls=calls, seconds=round(time.time() - t0, 2))
    return index, case, errs, degr


def partial(case, errs, degr=None):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    if not isinstance(contract, (dict, list)) or not C.contract_keys(contract):
        contract = dict((k, "array") for k in DEFAULT_CONTRACT)
    res = dict((k, C.empty_like(C.contract_spec(contract, k)))
               for k in C.contract_keys(contract))
    res.update(case_id=str((case or {}).get("case_id") or (case or {}).get("id") or "unknown"),
               status="partial", sources=[], errors=errs, degradations=degr or [],
               uncertainties=["run not finalized: partial result written before any synthesis"],
               changes=[], artifacts=[], tool_calls=[], coverage={}, six_requirements={},
               runtime=dict(skill=GEN, stage="partial"))
    return res


def save_partial(case, errs, out, stage, degr=None):
    try:
        out.mkdir(parents=True, exist_ok=True)
        res = partial(case, errs, degr)
        res["runtime"]["stage"] = stage
        C.jwrite(out / "result.json", res)
    except Exception:
        pass


# ------------------------------------------------------------------ init
def cmd_init(a):
    t0 = time.time()
    inp, out, wk = paths(a)
    wk.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    errs, degr = [], []
    save_partial({}, [{"code": "not_started", "detail": "indexing not finished yet"}], out, "init_boot")
    index, case, errs, degr = build_index(inp, errs, degr)
    C.jwrite(wk / "index.json", index)
    cid = index["case_id"]
    res = partial(case, errs, degr)
    res.update(case_id=cid, sources=[dict(source_id=k, file=v["filename"], kind=v["kind"], engine=v["engine"],
                                          n_paras=len(index["paras"][k]), scheme=v["scheme"],
                                          declared=v["declared"], notes=v["notes"])
                                     for k, v in index["docs"].items()],
               tool_calls=index["tool_calls"],
               uncertainties=["not synthesized yet: read the materials, write /app/work/draft.json, then run build"],
               runtime=dict(skill=GEN, stage="init", seconds=round(time.time() - t0, 2),
                            sources=len(index["docs"]), records=len(index["records"])))
    C.jwrite(out / "result.json", res)
    print("== case ==")
    print("case_id=%s | case=%s | question_source=%s" % (cid, index["case_path"] or "none", index["question_source"]))
    print("question=%s" % (index["question"][:300] or "(not recovered)"))
    print("contract_keys=%s" % ", ".join(C.contract_keys(index["contract"])))
    print("== sources (%d, declared=%d) ==" % (len(index["docs"]), index["sources_expected"]))
    for k, v in index["docs"].items():
        print("%s | %s | %s | %d paras | %s | q=%s | %s" % (k, v["filename"], v["kind"],
                                                           len(index["paras"][k]), v["engine"], v["quality"],
                                                           "; ".join(v["notes"] or [])[:80]))
    print("== records (%d, src=%s) ==" % (len(index["records"]), index["records_source"] or "none"))
    for r in index["records"][:12]:
        keys = [k for k in r["fields"]][:6]
        print("%s | %s | %s" % (r["record_id"], r["source_id"] or "-", ", ".join(keys)))
    if index["protocol"]:
        print("== search protocol (first 300 chars) ==\n%s" % index["protocol"][:300].replace("\n", " "))
    if index["constraints"]:
        print("== constraints == %s" % json.dumps(index["constraints"], ensure_ascii=False)[:300])
    if errs:
        print("== errors == %s" % json.dumps(errs, ensure_ascii=False)[:600])
    print("== next == 1) show --doc S1  2) write %s  3) check  4) build  5) selfcheck" % (wk / "draft.json"))
    return 0


# ------------------------------------------------------------------ show
def cmd_show(a):
    inp, out, wk = paths(a)
    p = wk / "index.json"
    if not p.exists():
        print("no index yet: run init first")
        return 0
    try:
        idx = C.jread(p)
    except Exception as e:
        print("index unreadable (%r): re-run init" % e)
        return 0
    docs, paras = idx.get("docs") or {}, idx.get("paras") or {}
    if a.doc:
        if a.doc not in paras:
            print("unknown source %r; available: %s" % (a.doc, ", ".join(docs)))
            return 0
        ps = paras[a.doc]
        m = re.match(r"^(\d+)\s*[:.-]\s*(\d+)$", str(a.paras or ""))
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, min(len(ps), 60))
        hi = min(hi, len(ps))
        for q in ps[lo - 1:hi]:
            print("[%s %s] %s" % (a.doc, q["loc"], q["text"][:1500]))
        print("-- %s: %d paragraphs, showed %d..%d (locator scheme %s)" %
              (a.doc, len(ps), lo, hi, docs[a.doc].get("scheme")))
        return 0
    if a.records:
        recs = idx.get("records") or []
        if not recs:
            print("(no records loaded; case.json has no records list and no *record* file)")
        for r in recs:
            print("[%s] source=%s %s" % (r["record_id"], r["source_id"] or "-",
                                         json.dumps(r["fields"], ensure_ascii=False)[:900]))
        return 0
    if a.contract:
        ct = idx.get("contract") or {}
        for k in C.contract_keys(ct):
            spec = ct.get(k) if isinstance(ct, dict) else k
            print("%-28s %s" % (k, (json.dumps(spec, ensure_ascii=False) if not isinstance(spec, str) else spec)[:160]))
        return 0
    print("== question ==")
    print((idx.get("question") or "(none)")[:400])
    print("== sources (%d) ==" % len(docs))
    for k, v in docs.items():
        print("%s | %s | %s | %d paras | %s | declared=%s | %s" %
              (k, v["filename"], v["kind"], len(paras.get(k) or []), v["engine"], v["declared"], v["scheme"]))
    recs = idx.get("records") or []
    print("== records (%d) ==" % len(recs))
    for r in recs:
        print("%s | source=%s | %s" % (r["record_id"], r["source_id"] or "-",
                                       ", ".join(list(r["fields"])[:8])))
    print("== contract keys ==")
    print(", ".join(C.contract_keys(idx.get("contract") or {})))
    if idx.get("protocol"):
        print("== search protocol (head) ==")
        print(idx["protocol"][:500])
    print("== next == show --doc <S#> [--paras 1:40] | show --records | write draft.json | check | build")
    return 0


# ------------------------------------------------------------------ check
def cmd_check(a):
    inp, out, wk = paths(a)
    idx = {}
    try:
        idx = C.jread(wk / "index.json") if (wk / "index.json").exists() else {}
    except Exception as e:
        idx = {}
        print("WARN index unreadable (%r); run init" % e)
    dp = wk / "draft.json"
    draft, src = {}, "none"
    if dp.exists():
        try:
            draft = C.jread(dp)
            src = str(dp)
        except Exception as e:
            draft = {"_unreadable": repr(e)}
            print("FIX [draft_unreadable] %s :: %r -- rewrite it as valid JSON" % (dp, e))
    rep = V.validate_draft(draft, idx)
    rep["draft_source"] = src
    rep["contract_keys"] = C.contract_keys(idx.get("contract") or {})
    C.jwrite(wk / "check.json", rep)
    print(json.dumps({"ok": rep["ok"], "counts": rep["counts"], "six": rep["six"],
                      "errors": len(rep["errors"]), "warnings": len(rep["warnings"])},
                     ensure_ascii=False, indent=1))
    for f in rep["fixes"]:
        print(f)
    for w in rep["warnings"][:8]:
        print("WARN [%s] %s :: %s" % (w["code"], w["where"], w["detail"]))
    cn = rep["counts"]
    print("SUMMARY sub_questions=%s evidence=%s quote_pass=%s claims=%s backlink=%s conflicts=%s gaps=%s six=%d/6 errors=%d"
          % (cn.get("sub_questions"), cn.get("evidence"), cn.get("quote_pass_rate"), cn.get("claims"),
             cn.get("claims_backlinked_ratio"), cn.get("conflicts"), cn.get("gaps"),
             sum(1 for v in rep["six"].values() if v), len(rep["errors"])))
    print("next: fix every FIX line in %s, then run build" % (wk / "draft.json"))
    return 0


# ------------------------------------------------------------------ selfcheck
def cmd_selfcheck(a):
    inp, out, wk = paths(a)
    res, errs = {}, []
    rp = out / "result.json"
    if not rp.exists():
        errs.append("result.json missing")
    else:
        try:
            res = C.jread(rp)
        except Exception as e:
            errs.append("result.json invalid JSON: %r" % e)
    contract = {}
    try:
        case, _ = find_case(inp, [])
        contract = case.get("output_contract") or {}
    except Exception:
        pass
    if not C.contract_keys(contract):
        try:
            contract = (C.jread(wk / "index.json").get("contract") or {})
        except Exception:
            contract = {}
    keys = C.contract_keys(contract)
    miss = [k for k in keys if k not in res]
    empty = [k for k in keys if k in res and res[k] in (None, "", [], {})]
    arts = {}
    for name in ("research_plan.json", "evidence_matrix.jsonl", "evidence_matrix.csv", "synthesis.json",
                 "coverage.json", "report.md"):
        p = out / name
        arts[name] = p.stat().st_size if p.exists() else 0
    rep = {}
    try:
        rep = C.jread(wk / "check.json")
    except Exception:
        pass
    cov = res.get("coverage") or {}
    blanks = [n for n in ("report.md", "research_plan.json", "coverage.json") if not (out / n).exists()
              or (out / n).stat().st_size == 0]
    out_json = dict(ok=(not errs and not miss and not blanks), errors=errs, blank_artifacts=blanks, contract_keys=len(keys), missing_keys=miss,
                    empty_contract_values=empty, status=res.get("status"),
                    artifacts_bytes=arts, report_mentions=0, evidence=len(res.get("evidence") or []),
                    quote_pass_rate=cov.get("quote_pass_rate"), six_requirements=cov.get("six_requirements_met"),
                    check_errors=len((rep or {}).get("errors") or []))
    rmd = out / "report.md"
    if rmd.exists():
        txt = rmd.read_text(encoding="utf-8", errors="replace")
        ids = {str(e.get("evidence_id")) for e in (res.get("evidence") or [])}
        out_json["report_mentions"] = sum(1 for i in ids if "[%s]" % i in txt)
        out_json["report_chars"] = len(txt)
    print(json.dumps(out_json, ensure_ascii=False, indent=1))
    bad = [n for n, b in arts.items() if not b]
    if bad:
        print("WARN empty or missing artifacts: %s -- run build" % ", ".join(bad))
    if miss:
        print("WARN contract keys absent from result.json: %s" % ", ".join(miss))
    if out_json["report_mentions"] < len(res.get("evidence") or []):
        print("WARN report cites %d of %d evidence ids: every conclusion must carry its evidence id"
              % (out_json["report_mentions"], len(res.get("evidence") or [])))
    print("selfcheck %s" % ("PASS" if out_json["ok"] else "REVIEW"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="deep-research-evidence-map (%s)" % GEN)
    sub = ap.add_subparsers(dest="cmd")
    specs = (("init", "index materials + partial result.json"), ("show", "print sources/records/paragraphs"),
             ("check", "validate work/draft.json"), ("build", "render artifacts + final result.json"),
             ("selfcheck", "re-verify written artifacts"))
    for name, hlp in specs:
        p = sub.add_parser(name, help=hlp)
        for f in ("--input", "--output", "--work"):
            p.add_argument(f)
        if name == "show":
            p.add_argument("--doc")
            p.add_argument("--paras")
            p.add_argument("--records", action="store_true")
            p.add_argument("--contract", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        if a.cmd == "build":
            import types
            H = types.SimpleNamespace(DEFAULT_CONTRACT=DEFAULT_CONTRACT, **dict(
                (n, globals()[n]) for n in ("paths", "find_case", "partial", "save_partial", "build_index")))
            B.cmd_build(a, H)
        else:
            {"init": cmd_init, "show": cmd_show, "check": cmd_check,
             "selfcheck": cmd_selfcheck}[a.cmd](a)
    except Exception as e:
        try:
            inp, out, _ = paths(a)
            out.mkdir(parents=True, exist_ok=True)
            case = {}
            try:
                case, _ = find_case(inp, [])
            except Exception:
                pass
            res = partial(case, [{"code": "unhandled_exception",
                                  "detail": "%s: %s" % (type(e).__name__, e),
                                  "trace": traceback.format_exc()[-900:]}])
            res["runtime"]["stage"] = "exception:" + str(a.cmd)
            C.jwrite(out / "result.json", res)
        except Exception:
            pass
        print("ERROR %s: %s" % (type(e).__name__, e), file=sys.stderr)

    try:
        import finalize
        finalize.run(paths(a)[1])
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
