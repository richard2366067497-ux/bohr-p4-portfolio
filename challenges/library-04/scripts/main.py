#!/usr/bin/env python3
"""main.py -- research-library docket driver (stdlib only).

init inventory/extract/families/questions (+ partial result.json) | show registry,
--query [--emit], --template | check draft | build artifacts + result.json | selfcheck.
Defaults --input /input --output /app/output --work /app/work; exit code always 0.
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_index as L
import lib_check as C
import lib_contract as K

GEN = "kb-library-docket v1.0.0"
DOC_FIELDS = ("filename", "rel_path", "path", "kind", "engine", "size", "mode", "sha256", "readable",
              "n_blocks", "quality", "notes", "family_id", "version_label", "version_rank", "meta_hint")


def jwrite(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))


def paths(a):
    return (Path(a.input or os.environ.get("SKILL_INPUT") or "/input"),
            Path(a.output or os.environ.get("SKILL_OUTPUT") or "/app/output"),
            Path(a.work or os.environ.get("SKILL_WORK") or "/app/work"))


# --------------------------------------------------------------------- init
def cmd_init(a, quiet=False):
    t0, (inp, out, wk) = time.time(), paths(a)
    wk.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    errs, degr = [], []
    case, cpath = L.find_case(inp, errs)
    cid = str(case.get("case_id") or case.get("id") or case.get("case") or
              (cpath.parent.name if cpath else "unknown"))
    jwrite(out / "result.json", K.partial_result(case, cid, errs, GEN))     # legal partial first
    task_text = ""
    for cand in (inp / "task.md", inp / "task.txt"):
        if cand.exists():
            try:
                task_text = cand.read_text(encoding="utf-8", errors="replace")
                break
            except Exception as e:
                errs.append({"code": "task_md_unreadable", "detail": repr(e)})
    mats, skipped = L.scan_input(inp)
    for s in skipped[:20]:
        errs.append({"code": "material_skipped", "detail": "%s (%s)" % (s["file"], s["reason"])})
    docs, paras, texts = {}, {}, {}
    for i, p in enumerate(mats):
        did = "D%d" % (i + 1)
        try:
            d = L.extract(p)
        except Exception as e:
            errs.append({"code": "extract_failed", "detail": "%s: %r" % (p.name, e)})
            d = {"kind": L.kind_of(p), "engine": "failed", "paras": [], "text": "", "readable": False, "size": 0,
                 "mode": "", "sha256": "", "n_blocks": 0, "quality": 0.0, "notes": ["extract_failed"]}
        try:
            rel = str(p.relative_to(inp))
        except Exception:
            rel = p.name
        d.update(doc_id=did, filename=p.name, rel_path=rel, path=str(p), meta_hint=L.metadata_hints(d))
        docs[did], paras[did], texts[did] = d, d["paras"], d["text"]
        degr += ["%s/%s: %s" % (did, p.name, n) for n in d.get("notes") or []]
    fams, dupes = L.build_families(docs)
    notes, questions = L.admin_notes(docs), L.find_questions(case, task_text)
    if questions and all(q.get("derived") for q in questions):
        degr.append("derived_questions: questions parsed from the instruction, no structured list in case.json")
    if not questions:
        degr.append("no_questions: inventory and version relations only")
    if not case:
        degr.append("case_json_missing_or_invalid: output_contract unknown")
    if not docs:
        degr.append("no_materials: no readable material under the input directory")
    for did, d in docs.items():
        if d.get("readable") is False:
            degr.append("%s: unreadable (%s), counted as an evidence gap" % (did, ",".join(d.get("notes") or []) or "read_failed"))
    idx = {"case_id": cid, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "case_path": str(cpath or ""),
           "input_root": str(inp), "docs": {k: dict({f: v.get(f) for f in DOC_FIELDS}, n_paras=len(v["paras"]))
                                            for k, v in docs.items()},
           "paras": paras, "texts": texts, "families": fams, "duplicates": dupes, "admin_notes": notes,
           "questions": questions, "contract_keys": K.contract_keys(case.get("output_contract")),
           "task_instruction": str(case.get("task_instruction") or "")[:4000]}
    jwrite(wk / "index.json", idx)
    res = K.partial_result(case, cid, errs, GEN, stage="init")
    res.update(degradations=degr,
               sources=[dict(doc_id=k, file=v["filename"], kind=v["kind"], sha256=v["sha256"], engine=v["engine"],
                             readable=v["readable"]) for k, v in docs.items()],
               uncertainty=["evidence not adjudicated yet: read with show, author draft.json, then build"],
               pending_human=["read the materials, author %s, then run check and build" % (wk / "draft.json")],
               runtime=dict(skill=GEN, stage="init", seconds=round(time.time() - t0, 2), documents=len(docs),
                            questions=len(questions), families=len(fams), duplicates=len(dupes)))
    jwrite(out / "result.json", res)
    if quiet:
        return 0
    print("== registry (%d documents) ==" % len(docs))
    for k in sorted(docs):
        d = docs[k]
        print("%s | %-34s | %-5s | %8d B | sha %s | %s v%s | %s | %d paras%s" % (
            k, d["filename"][:34], d["kind"], d["size"], (d["sha256"] or "")[:8], d.get("family_id"),
            d.get("version_rank"), "readable" if d["readable"] else "UNREADABLE", len(d["paras"]),
            (" | " + ",".join(d["notes"])) if d.get("notes") else ""))
    print("== families ==")
    for f in fams:
        print("%s | members=%s | canonical=%s | %s" % (f["family_id"], ",".join(f["members"]),
                                                       f["canonical_doc"], f["basis"][:90]))
    for g in dupes:
        print("dup | keep %s / drop %s (%s)" % (g["keep"], ",".join(g["drop"]), g["basis"]))
    if notes:
        print("== administrative version notes (top %d) ==" % min(len(notes), 8))
        for n in notes[:8]:
            print("%s `%s` mentions=%s :: %s" % (n["doc_id"], n["locator"], ",".join(n["mentions"]) or "-",
                                                 n["quote"][:150]))
    print("== questions (%d) ==" % len(questions))
    for q in questions:
        print("%s | %s%s" % (q["qid"], q["question"][:150], "  [derived]" if q.get("derived") else ""))
    print("== next == show --doc D1 | show --query '<kw>' --emit | show --template -> draft.json -> check -> build")
    if degr:
        print("degradations: " + "; ".join(degr[:6]))
    return 0


# --------------------------------------------------------------------- show
def cmd_show(a):
    _, _, wk = paths(a)
    if not (wk / "index.json").exists():
        cmd_init(a, quiet=True)
    idx = jread(wk / "index.json")
    docs, paras = idx.get("docs") or {}, idx.get("paras") or {}
    if a.template:
        tpl = {"case_id": idx.get("case_id"), "library": {
            "documents": [{"doc_id": k, "family_id": docs[k].get("family_id"), "version": "",
                           "version_rank": docs[k].get("version_rank"),
                           "role": "unreadable" if docs[k].get("readable") is False else "",
                           "title": (docs[k].get("meta_hint") or {}).get("title_hint", "")[:120],
                           "metadata": {"authors": "", "year": (docs[k].get("meta_hint") or {}).get("year_hint", ""),
                                        "doi": (docs[k].get("meta_hint") or {}).get("doi_hint", ""), "venue": ""},
                           "notes": ""} for k in sorted(docs)],
            "families": [{"family_id": f["family_id"], "canonical_doc": f["canonical_doc"], "members": f["members"],
                          "basis": f["basis"]} for f in idx.get("families") or []],
            "duplicates": idx.get("duplicates") or [], "repair_actions": []},
            "questions": [{"qid": q["qid"], "question": q["question"], "issues": [], "answer_draft": ""}
                          for q in idx.get("questions") or []],
            "exhibits": [], "version_witness": [], "search_scope": {}, "conflicts": [],
            "limitations": [], "uncertainty": []}
        jwrite(wk / "draft.template.json", tpl)
        print("draft skeleton -> %s (copy to draft.json, fill verdicts/exhibits/scope)" % (wk / "draft.template.json"))
        return 0
    if a.query:
        hits = L.search({k: {"paras": paras.get(k) or []} for k in paras}, a.query, a.top)
        if not hits:
            print("(no match for %r; if the library really lacks this topic, verdict=insufficient + record the scope)" % a.query)
            return 0
        if a.emit:
            arr = [{"exhibit_id": "E%d" % n, "doc_id": h["doc_id"], "version": docs[h["doc_id"]].get("version_label") or "",
                    "locator": h["locator"],
                    "quote": L.excerpt(h["text"], h["matched"]), "kind": "fact", "polarity": "support",
                    "page_printed": "", "section": "",
                    "note": "candidate; set kind/polarity after reading"}
                   for n, h in enumerate(hits, 1)]
            print(json.dumps(arr, ensure_ascii=False, indent=1))
            return 0
        for h in hits:
            print("[%s %s score=%.2f family=%s] %s" % (h["doc_id"], h["locator"], h["score"],
                                                      docs.get(h["doc_id"], {}).get("family_id"),
                                                      L.norm(h["text"])[:700]))
        print("-- %d hit(s); --emit gives ready-to-paste exhibit JSON" % len(hits))
        return 0
    if a.doc:
        if a.doc not in paras:
            print("unknown doc_id %r; available: %s" % (a.doc, ", ".join(sorted(docs))))
            return 0
        ps = paras[a.doc]
        m = re.match(r"^(\d+)\s*[:,-]\s*(\d+)$", str(a.paras or ""))
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, len(ps))
        for p in ps[lo - 1:hi]:
            print("[%s %s] %s" % (a.doc, p["locator"], p["text"][:1400]))
        d = docs.get(a.doc, {})
        print("-- %s (%s) family=%s v=%s readable=%s: %d paragraphs, showed %d..%d" % (
            a.doc, d.get("filename"), d.get("family_id"), d.get("version_rank"), d.get("readable"),
            len(ps), lo, min(hi, len(ps))))
        return 0
    if a.families:
        for f in idx.get("families") or []:
            print("%s | members=%s | canonical=%s | %s" % (f["family_id"], ",".join(f["members"]),
                                                           f["canonical_doc"], f["basis"]))
        print("-- duplicates: %s" % json.dumps(idx.get("duplicates") or [], ensure_ascii=False))
        return 0
    print("== registry ==")
    for k in sorted(docs):
        d = docs[k]
        print("%s | %-32s | %-5s | %7s B | sha %s | %s v%s | %s | %s paras | %s" % (
            k, d["filename"][:32], d["kind"], d.get("size"), (d.get("sha256") or "")[:8], d.get("family_id"),
            d.get("version_rank"), "readable" if d.get("readable") else "UNREADABLE", d.get("n_paras"),
            ",".join(d.get("notes") or []) or "-"))
    print("== questions ==")
    for q in idx.get("questions") or []:
        print("%s | %s" % (q["qid"], q["question"][:140]))
    return 0


# -------------------------------------------------------------------- check
def cmd_check(a):
    _, _, wk = paths(a)
    if not (wk / "index.json").exists():
        cmd_init(a, quiet=True)
    idx = jread(wk / "index.json")
    dp = Path(a.draft) if a.draft else wk / "draft.json"
    if not dp.exists():
        rep = {"ok": False, "counts": {"documents": len(idx.get("docs") or {})}, "warnings": [],
               "errors": [{"code": "no_draft", "where": str(dp),
                           "detail": "draft missing: read with show, author it, rerun check"}]}
        jwrite(wk / "check_report.json", rep)
        print("FIX [no_draft] %s (tip: show --template writes a skeleton)" % dp)
        return 0
    try:
        draft = jread(dp)
    except Exception as e:
        rep = {"ok": False, "counts": {}, "warnings": [],
               "errors": [{"code": "draft_json_invalid", "where": str(dp), "detail": repr(e)}]}
        jwrite(wk / "check_report.json", rep)
        print("FIX [draft_json_invalid] %s" % repr(e))
        return 0
    rep = C.validate(draft, idx)
    jwrite(wk / "check_report.json", rep)
    cn = rep.get("counts") or {}
    print("ok=%s docs=%s questions=%s issues=%s exhibits=%s quote_pass=%s locator_pass=%s verdicts=%s errors=%d warnings=%d" % (
        rep.get("ok"), cn.get("documents"), cn.get("questions"), cn.get("issues"), cn.get("exhibits"),
        cn.get("quote_pass_rate"), cn.get("locator_pass_rate"),
        json.dumps(cn.get("verdicts") or {}, ensure_ascii=False), len(rep["errors"]), len(rep["warnings"])))
    for e in rep["errors"][:14]:
        print("FIX [%s] %s :: %s" % (e.get("code"), e.get("where"), e.get("detail")))
    for w in rep["warnings"][:8]:
        print("note [%s] %s :: %s" % (w.get("code"), w.get("where"), w.get("detail")))
    return 0


# -------------------------------------------------------------------- build
def cmd_build(a):
    t0, (inp, out, wk) = time.time(), paths(a)
    out.mkdir(parents=True, exist_ok=True)
    errs, degr, pend = [], [], []
    case, cpath = L.find_case(inp, errs)
    cid0 = str(case.get("case_id") or case.get("id") or (cpath.parent.name if cpath else "unknown"))
    jwrite(out / "result.json", K.partial_result(case, cid0, errs, GEN))    # legal partial first, always
    idx = {}
    if (wk / "index.json").exists():
        try:
            idx = jread(wk / "index.json")
        except Exception as e:
            errs.append({"code": "index_unreadable", "detail": repr(e)})
    if not idx.get("docs"):
        try:
            cmd_init(a, quiet=True)
            idx = jread(wk / "index.json")
            degr.append("index rebuilt during build")
        except Exception as e:
            errs.append({"code": "init_failed", "detail": repr(e)})
            idx = {"case_id": cid0, "docs": {}, "paras": {}, "texts": {}, "families": [], "duplicates": [],
                   "questions": [], "admin_notes": []}
    cid = idx.get("case_id") or cid0
    dp = Path(a.draft) if a.draft else wk / "draft.json"
    draft, dsrc = {}, ""
    if dp.exists():
        try:
            draft = jread(dp)
            dsrc = str(dp)
        except Exception as e:
            errs.append({"code": "draft_json_invalid", "detail": "%s: %s" % (dp, e)})
            degr.append("draft unreadable: automatic classification only, no adjudicated evidence")
    if not draft or not isinstance(draft, dict):
        draft = K.auto_draft(idx, degr)
        pend.append("read the materials and author %s" % dp)
    draft.setdefault("case_id", cid)
    if not draft.get("search_scope"):
        chunks = sum(len(v) for v in (idx.get("paras") or {}).values())
        draft["search_scope"] = {q.get("qid"): {"files": sorted(idx.get("docs") or {}), "keywords": [],
                                                "synonyms": [], "chunks_scanned": chunks}
                                 for q in draft.get("questions") or []}
        if not draft.get("_auto"):
            degr.append("search_scope absent in draft: filled with the whole scanned scope (judgement pending)")
    rep = C.validate(draft, idx)
    files, stats = C.render(idx, draft, out, GEN, "partial", errs, degr)
    S, cnt = C._draft_sections(draft), rep.get("counts") or {}
    verdicts = cnt.get("verdicts") or {}
    answered = len([q for q in S["questions"] if L.norm(q.get("answer_draft"))])
    blocked = verdicts.get("insufficient", 0) + verdicts.get("out_of_scope", 0)
    status = "partial" if (draft.get("_auto") or blocked or not answered or rep["errors"] or degr) else "ok"
    if not (idx.get("docs") or {}):
        errs.append({"code": "no_materials", "detail": "no readable material under input"})
        status = "failed" if not case else "partial"
        pend.append("no readable material under the input directory; the inventory is empty")
    lib = jread(out / "library_index.json")
    records = lib.get("documents") or []
    report_txt = (out / "report.md").read_text(encoding="utf-8") if (out / "report.md").exists() else ""
    base = {
        "case_id": cid, "status": status, "library_index": records, "documents": records,
        "duplicates": S["duplicates"] or idx.get("duplicates") or [],
        "version_witness": jread(out / "version_witness.json"),
        "metadata": [{"doc_id": r["doc_id"], "title": r.get("title"), "metadata": r.get("metadata")} for r in records],
        "permissions": [{"doc_id": r["doc_id"], "path": r.get("rel_path"), "mode": r.get("mode"),
                         "readable": r.get("readable")} for r in records],
        "sources": [dict(doc_id=k, file=v.get("filename"), kind=v.get("kind"), sha256=v.get("sha256"),
                         engine=v.get("engine"), readable=v.get("readable")) for k, v in (idx.get("docs") or {}).items()],
        "answers": [{"qid": q.get("qid"), "question": q.get("question"),
                     "answer": C._disp(q.get("answer_draft") or q.get("answer")),
                     "issues": q.get("issues") or [],
                     "verdicts": [i.get("verdict") for i in (q.get("issues") or [])]} for q in S["questions"]],
        "exhibits": K.load_register(out / "exhibits" / "exhibit_register.jsonl"),
        "conflicts": S["conflicts"],
        "not_found": [{"qid": str(q.get("qid")), "issue": i.get("issue_text"),
                       "missing_evidence": C._disp(i.get("missing_evidence")),
                       "searched_files": (S["scope"].get(str(q.get("qid"))) or {}).get("files") or [],
                       "searched_keywords": (S["scope"].get(str(q.get("qid"))) or {}).get("keywords") or []}
                      for q in S["questions"] for i in (q.get("issues") or [])
                      if L.norm(i.get("verdict")) in ("insufficient", "out_of_scope")],
        "repair_actions": S["actions"],
        "coverage": dict(cnt, available_paragraphs=sum(len(v) for v in (idx.get("paras") or {}).values()),
                         admin_notes=len(idx.get("admin_notes") or [])),
        "summary": report_txt[:12000],
        "method": ("init inventories every file (sha256/type/permissions) and extracts locator-bearing paragraphs; "
                   "duplicates group by hash identity and shingle similarity, version families by those plus filename "
                   "version tokens and administrative notes; the Agent adjudicates each issue with verbatim exhibits "
                   "(doc_id + version + locator), registers counter-exhibits and states missing evidence with the searched "
                   "scope; build verifies quote/locator agreement and numeric anchoring."),
        "artifacts": files + ["result.json"],
        "uncertainty": (S["uncertainty"] or []) + [i.get("missing_evidence") for q in S["questions"]
                                                   for i in (q.get("issues") or []) if L.norm(i.get("missing_evidence"))][:8],
        "pending_human": pend + ["spot-check 3 exhibits: show --doc <id> --paras <n>:<n>"],
    }
    res, missing = K.fill_contract(case, base, errs)
    res.update(case_id=cid, status=status, sources=base["sources"],
               errors=errs + ([] if draft.get("_auto") else rep["errors"]),
               degradations=degr + ([] if not missing else ["contract fields with no matching content: %s" % ", ".join(missing)]),
               uncertainty=base["uncertainty"], pending_human=base["pending_human"],
               changes=[dict(step="init", to="work/index.json"),
                        dict(step="build", source=dsrc or "(auto fallback)", to=files + ["result.json"]),
                        dict(step="contract", resolved=len(K.contract_keys(case.get("output_contract"))) - len(missing),
                             total=len(K.contract_keys(case.get("output_contract"))))],
               runtime=dict(skill=GEN, stage="build", seconds=round(time.time() - t0, 2), documents=stats["documents"],
                            questions=stats["questions"], exhibits=stats["exhibits"], issues=stats["issues"],
                            families=stats["families"], duplicates=stats["duplicates"], verdicts=verdicts,
                            check_ok=rep.get("ok"), auto_fallback=bool(draft.get("_auto"))))
    jwrite(out / "result.json", res)
    print("status=%s docs=%d families=%d duplicates=%d questions=%d issues=%d exhibits=%d verdicts=%s check_ok=%s" % (
        status, stats["documents"], stats["families"], stats["duplicates"], stats["questions"], stats["issues"],
        stats["exhibits"], json.dumps(verdicts, ensure_ascii=False), rep.get("ok")))
    print("artifacts:", ", ".join(files + ["result.json"]))
    print("unfilled contract:", missing or "none")
    if errs or rep["errors"]:
        print("errors:", json.dumps(errs[:5] or rep["errors"][:5], ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- selfcheck
def cmd_selfcheck(a):
    _, out, wk = paths(a)
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    try:
        res = jread(out / "result.json")
        add("result_json_parses", True, str(out / "result.json"))
    except Exception as e:
        res = {}
        add("result_json_parses", False, repr(e))
    try:
        idx = jread(wk / "index.json")
        add("index_parses", True, "%d docs" % len(idx.get("docs") or {}))
    except Exception as e:
        idx = {}
        add("index_parses", False, repr(e))
    missing = [k for k in (idx.get("contract_keys") or []) if k not in res]
    add("contract_keys_present", not missing, "missing: %s" % (missing or "none"))
    add("case_id_present", bool(res.get("case_id")), str(res.get("case_id")))
    add("status_valid", res.get("status") in ("ok", "partial", "failed"), str(res.get("status")))
    for f in ("report.md", "library_index.json", "repair_log.json", "version_witness.json",
              "conflicts.json", "search_scope.json", "exhibits/exhibit_register.jsonl"):
        p = out / f
        ok = p.exists() and (p.stat().st_size > 0 or f.endswith(".jsonl"))
        add("artifact:%s" % f, ok, "%d bytes" % (p.stat().st_size if p.exists() else 0))
    bad_q, bad_l, n = [], [], 0
    for e in K.load_register(out / "exhibits" / "exhibit_register.jsonl"):
        n += 1
        did, q, loc = str(e.get("doc_id") or ""), e.get("quote") or "", str(e.get("locator") or "")
        hits = C.locate_quote((idx.get("paras") or {}).get(did) or [], q)
        if not hits:
            bad_q.append(e.get("exhibit_id"))
        elif loc not in hits:
            bad_l.append("%s(%s)" % (e.get("exhibit_id"), loc))
    add("exhibit_quotes_reverify", not bad_q, "%d exhibits, bad=%s" % (n, bad_q[:5] or "none"))
    add("exhibit_locators_reverify", not bad_l, "mismatch=%s" % (bad_l[:5] or "none"))
    dockets = sorted((out / "dockets").glob("*/verdict.md")) if (out / "dockets").exists() else []
    add("dockets_rendered", bool(dockets) or not (idx.get("questions") or []), "%d verdict.md" % len(dockets))
    ok = all(c["ok"] for c in checks)
    jwrite(wk / "selfcheck.json", {"ok": ok, "checks": checks})
    for c in checks:
        print("%s %-28s %s" % ("PASS" if c["ok"] else "FAIL", c["check"], c["detail"]))
    print("selfcheck:", "PASS" if ok else "FAIL (details in %s)" % (wk / "selfcheck.json"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="research-library docket (%s)" % GEN)
    sub = ap.add_subparsers(dest="cmd")
    for n, h in (("init", "inventory + extract + families + questions (+partial result.json)"),
                 ("show", "registry / documents / candidates / draft skeleton"),
                 ("check", "validate the Agent draft"), ("build", "render dockets + finalize result.json"),
                 ("selfcheck", "re-verify produced artifacts")):
        q = sub.add_parser(n, help=h)
        for f in ("--input", "--output", "--work", "--draft"):
            q.add_argument(f)
        if n == "show":
            for f in ("--doc", "--paras", "--query"):
                q.add_argument(f)
            for f in ("--emit", "--template", "--families"):
                q.add_argument(f, action="store_true")
            q.add_argument("--top", type=int, default=8)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
         "selfcheck": cmd_selfcheck}[a.cmd](a)
    except Exception as e:
        try:
            inp, out, _ = paths(a)
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", K.partial_result(
                L.find_case(inp, [])[0], "unknown",
                [{"code": "unhandled_exception", "detail": "%s: %s" % (type(e).__name__, e),
                  "trace": traceback.format_exc()[-800:]}], GEN))
        except Exception:
            pass
        print("ERROR %s: %s" % (type(e).__name__, e), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
