#!/usr/bin/env python3
"""main.py -- annotation-ledger driver: init / show (+ CLI dispatch, always exit 0).

init   case.json + task.md + materials -> work/index.json + legal partial result.json first
show   documents / pages / annotations with locators (the only source of verbatim quotes)
check / build / selfcheck are delegated to checks.py and build.py.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract as X

GEN = "annotation-ledger v1.0.0"
LOW_CONF = 0.5
DEFAULT_CONTRACT = ["annotations", "notes", "links", "queries", "index", "files", "coverage", "summary", "status"]
ARTIFACTS = ["files.json", "annotations.jsonl", "notes.jsonl", "links.json", "index.json", "queries.json",
             "provenance.json", "skipped.json", "ledger.md", "result.json"]


# ------------------------------------------------------------------ io / paths
def paths(a):
    here = Path(__file__).resolve().parent.parent
    if getattr(a, "input", None):
        inp = Path(a.input)
    else:
        inp = next((Path(c) for c in (os.environ.get("SKILL_INPUT"), "/input", str(here / "input"), "input")
                    if c and Path(c).exists()), Path("/input"))
    wk = Path(getattr(a, "work", None) or os.environ.get("SKILL_WORK") or "/app/work")
    outp = Path(getattr(a, "output", None) or os.environ.get("SKILL_OUTPUT") or "/app/output")
    for name, p in (("work", wk), ("output", outp)):
        try:
            p.mkdir(parents=True, exist_ok=True)
            t = p / ".probe"
            t.write_text("x", encoding="utf-8")
            t.unlink()
        except Exception:
            fb = here / name
            try:
                fb.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if name == "work":
                wk = fb
            else:
                outp = fb
    return inp, outp, wk


def walk(o, depth=0):
    if depth > 6:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k), v
            yield from walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o[:80]:
            yield from walk(v, depth + 1)


def find_case(inp, errs):
    cands = []
    if inp.exists():
        cands = sorted(inp.rglob("case.json"))
        if not cands:
            js = [p for p in sorted(inp.rglob("*.json")) if not p.name.lower().startswith(("annot", "highlight"))]
            cands = [p for p in js if "case" in p.name.lower() or "workorder" in p.name.lower()] or js
    for p in cands:
        try:
            d = X.jread(p)
            if isinstance(d, dict):
                return d, p
        except Exception as e:
            errs.append({"code": "case_json_invalid", "detail": "%s: %s" % (p.name, e)})
    if not inp.exists():
        errs.append({"code": "input_missing", "detail": "input dir not found: %s" % inp})
    return {}, None


def q_of(case):
    raw = []
    for k, v in walk(case):
        if k.lower() in ("queries", "search_questions", "questions", "retrieval_queries", "search_queries") \
                and isinstance(v, list) and v and not raw:
            raw = v
    out = []
    for i, it in enumerate(raw):
        if isinstance(it, str):
            out.append({"qid": "Q%d" % (i + 1), "question": X.norm(it)})
        elif isinstance(it, dict):
            g = lambda *ks: next((it[k] for k in ks if it.get(k) not in (None, "")), "")
            out.append({"qid": str(g("qid", "id", "q_id") or "Q%d" % (i + 1)),
                        "question": X.norm(g("question", "text", "query", "q")),
                        "kind": str(g("kind", "type") or "text"), "expect": g("expect", "target", "doc")})
    return [q for q in out if q["question"]]


def envelope(case, cid, errs):
    ct = case.get("output_contract")
    res = {k: X.empty_like(ct.get(k) if isinstance(ct, dict) else None) for k in X.contract_keys(ct)}
    res.update({"case_id": cid, "status": "partial", "sources": [], "uncertainty": [], "pending_human": [],
                "errors": errs, "degradations": [], "changes": [],
                "runtime": {"skill": GEN, "stage": "partial", "ts": time.strftime("%FT%T")}})
    return res


# ------------------------------------------------------------------ index
def discover(inp, case):
    roots = []
    for k, v in walk(case):
        if k.lower() in ("library_root", "annotations_root", "materials_root", "documents_root", "root", "library") \
                and isinstance(v, str):
            c = Path(v) if Path(v).is_absolute() else inp / v
            if c.exists():
                roots.append(c)
    for nm in ("library", "materials", "documents", "annotations", "artifacts", "files", "input_files", "papers"):
        if (inp / nm).exists():
            roots.append(inp / nm)
    roots.append(inp)
    seen, mats, meta = set(), [], []
    for r in roots:
        for p in sorted(r.rglob("*")):
            if not p.is_file() or str(p) in seen:
                continue
            seen.add(str(p))
            nm = p.name.lower()
            overlay = nm.startswith(("annot", "highlight")) and p.suffix.lower() == ".json"
            if nm == "task.md" or nm.endswith("contract.json") or overlay \
                    or (nm.startswith("case") and p.suffix.lower() == ".json") \
                    or (p.suffix.lower() == ".json" and not overlay):
                meta.append(p)
            else:
                mats.append(p)
    return mats, meta


def anchor(ann, pages):
    """Verify/repair one anchor; returns the annotation (page may shift, never silently dropped)."""
    pmap = {pg["page"]: (pg.get("text") or "") for pg in pages or []}
    q = ann.get("quoted_text") or ""
    cand = q or ann.get("candidate_quote") or ""
    base = float(ann.get("anchor_confidence") or 0.35)
    meth = {"pdf_annots": "line_text_match", "annotations_json": "overlay_text_match",
            "docx_comments": "comment_range", "html_mark": "clip_text"}.get(ann.get("source"), "text_match")
    if q and X.fq(pmap.get(ann["page"], ""), q)["found"]:
        ann["anchor_method"] = meth
        ann["anchor_confidence"] = round(min(0.95, base + 0.2), 2)
        ann["anchor_confirmed"] = True
        return ann
    note_like = ann.get("type") in ("margin_note", "handwritten", "region_mark") and ann.get("rect")
    if note_like:
        # a margin note / ink stroke anchors by position: its meaning is the note body,
        # there is no covered sentence to quote, so it must not be marked low-confidence for that.
        has_text = bool((pmap.get(ann["page"]) or "").strip())
        ann["anchor_method"] = "rect_only_note"
        ann["anchor_confirmed"] = True
        ann["anchor_confidence"] = round(0.55 if has_text else 0.4, 2)
        return ann
    for step in (1, -1, 2, -2):
        tgt = ann["page"] + step
        if cand and tgt in pmap and X.fq(pmap[tgt], cand)["found"]:
            ann["page_shift"] = {"from": ann["page"], "to": tgt, "step": step}
            ann["page"] = tgt
            if not q:
                ann["quoted_text"] = cand
            ann["anchor_method"] = "page_shift"
            ann["anchor_confidence"] = round(min(0.7, base + 0.05), 2)
            ann["anchor_confirmed"] = True
            return ann
    ann["anchor_confirmed"] = False
    ann["anchor_method"] = "rect_unverified" if ann.get("rect") else "no_anchor"
    ann["anchor_confidence"] = round(min(base, 0.45), 2)
    return ann


def build_index(inp, errs, degr):
    case, cp = find_case(inp, errs)
    cid = str(case.get("case_id") or case.get("id") or (cp.parent.name if cp else "unknown"))
    mats, meta = discover(inp, case) if inp.exists() else ([], [])
    docs, skipped = {}, []
    for i, p in enumerate(mats):
        d = X.extract_doc(p)
        if d.get("kind") in ("zip", "xlsx", "pptx", "unreadable", "image"):
            skipped.append({"file": p.name, "code": "unsupported_or_image", "detail": "kind=%s" % d.get("kind"),
                            "action": "记录并降级"})
        d.update(filename=p.name, path=str(p), size=p.stat().st_size, sha256=X.sha256_file(str(p)),
                 version=X.version_token(p.name))
        docs["D%d" % (i + 1)] = d
    overlays, oerr = [], []
    try:
        overlays, oerr = X.load_overlays([p for p in inp.rglob("*.json")]) if inp.exists() else ([], [])
        errs += oerr
    except Exception as e:
        degr.append("overlay load failed: %s" % e)
    by_name = {}
    for did, d in docs.items():
        by_name[d["filename"].lower()] = did
        by_name[X.alias_key(d["filename"])] = did
    for ov in overlays:
        f = (ov.get("file") or "").lower()
        did = by_name.get(Path(f).name) or by_name.get(X.alias_key(f or "x"))
        if not did:
            skipped.append({"file": ov.get("file") or "?", "code": "annotation_target_missing",
                            "detail": "overlay 批注指向库中不存在的文件", "action": "记录并跳过"})
            continue
        docs[did].setdefault("annots", []).append(ov)
    anns = []
    for did in sorted(docs):
        d = docs[did]
        rows = [a for a in (d.pop("annots") or []) if isinstance(a, dict)]
        rows.sort(key=lambda a: (int(a.get("page") or 1), -(a.get("rect") or [0, 0, 0, 9e9])[1]))
        for k, a in enumerate(rows):
            a["doc_id"] = did
            a["ann_id"] = str(a.get("ann_id") or "A%04d" % (len(anns) + 1))
            a["page"] = int(a.get("page") or 1)
            a["type"] = X.type_alias(a.get("type") or a.get("raw_subtype") or "unknown")
            a["type"] = a["type"] if a["type"] in X.TYPES else "unknown"
            a["locator"] = a.get("locator") or "p%d#a%d" % (a["page"], k + 1)
            a["source_version"] = a.get("source_version") or d.get("version") or ""
            a["comment"] = X.norm(a.get("comment") or "")
            given = X.norm(a.get("quoted_text") or "")
            note_like = a["type"] in ("margin_note", "handwritten", "region_mark")
            body = "" if note_like else X.norm(a.get("line_text") or a.get("rect_text") or "")
            a["quoted_text"] = given or body
            a["candidate_quote"] = X.norm(a.get("rect_text") or a.get("line_text") or "")
            a["anchor_scope"] = "exact" if given else ("line" if body else "none")
            a["color"] = a.get("color") or None
            a.setdefault("anchor_confidence", {"pdf_annots": 0.7, "annotations_json": 0.8,
                                               "docx_comments": 0.85, "html_mark": 0.8}.get(a.get("source"), 0.6))
            a = anchor(a, d.get("pages"))
            a["low_confidence"] = bool(a["anchor_confidence"] < LOW_CONF or not a["anchor_confirmed"])
            anns.append(a)
    dup, alias = X.group_docs(docs)      # sha256 duplicates + alias groups + version chains
    duped = {k: v["duplicate_of"] for k, v in docs.items() if v.get("duplicate_of")}
    duplicate_anns = []
    if duped:
        keep, moved = [], []
        for a in anns:
            if a["doc_id"] in duped:
                moved.append(dict(a, duplicate_of=duped[a["doc_id"]]))
            else:
                keep.append(a)
        if moved:
            skipped.append({"file": ",".join(sorted({docs[d]["filename"] for d in duped})),
                            "code": "duplicate_copy_annotations",
                            "detail": "%d 条批注来自字节相同的重复文件，已归并到 canonical=%s，不重复计数"
                                      % (len(moved), ", ".join(sorted(set(duped.values())))),
                            "action": "保留在 index.duplicate_annotations 供审计，不进入账本主表"})
        duplicate_anns = moved
        anns = keep
    vnotes = []
    for k, v in walk(case):
        if k.lower() in ("version_notes", "administrative_notes", "admin_notes", "versions", "change_notes") and v:
            items = v if isinstance(v, list) else [v]
            for it in items:
                vnotes.append({"source": "case.json:%s" % k,
                               "note": X.norm(it if isinstance(it, str) else json.dumps(it, ensure_ascii=False))[:400]})
    for did, d in docs.items():
        if d.get("kind") in ("text", "html") and re.search(r"(?i)version|版本|修订|supersed", d.get("text") or ""):
            vnotes += X.version_notes_from_text(d["filename"], d.get("text"))
    for did, d in docs.items():
        if not d.get("has_text_layer"):
            skipped.append({"file": d["filename"], "doc_id": did, "code": "no_text_layer",
                            "detail": "页面无可抽取文本层（扫描/矢量图），引文无法逐字校验",
                            "action": "保留几何与批注坐标，标低置信度，需 OCR 或人工核对"})
        for n in d.get("notes") or []:
            if "failed" in n or "unsupported" in n:
                skipped.append({"file": d["filename"], "doc_id": did, "code": "extract_degraded", "detail": n,
                                "action": "记录并降级"})
        if d.get("has_text_layer") and (d.get("quality") or 1) < 0.5:
            skipped.append({"file": d["filename"], "doc_id": did, "code": "text_quality_low",
                            "detail": "alnum ratio %.2f: CID font or garbled encoding" % d["quality"],
                            "action": "低置信度抽取，引文需人工核对"})
    idx = {"case_id": cid, "case_path": str(cp or ""), "generated": time.strftime("%FT%T"),
           "task_instruction": X.norm(case.get("task_instruction") or case.get("instruction") or case.get("task") or "")[:4000],
           "contract_keys": X.contract_keys(case.get("output_contract")), "contract": case.get("output_contract"),
           "queries": q_of(case),
           "docs": {k: {kk: v.get(kk) for kk in ("filename", "kind", "engine", "n_pages", "has_text_layer", "quality",
                                                 "sha256", "size", "version", "duplicate_of", "alias_group",
                                                 "version_chain", "path", "notes", "src")} for k, v in docs.items()},
           "pages": {k: [{kk: pg.get(kk) for kk in ("page", "locator", "text", "layout")} for pg in v.get("pages") or []]
                     for k, v in docs.items()},
           "texts": {k: (v.get("text") or "")[:X.TRUNC] for k, v in docs.items()},
           "annotations": anns, "duplicate_annotations": duplicate_anns, "duplicates": dup, "aliases": alias, "version_notes": vnotes,
           "skipped": skipped, "overlay_errors": oerr}
    return idx, case, cid


def load_index(wk, errs=None):
    p = wk / "index.json"
    if not p.exists():
        return {}
    try:
        return X.jread(p)
    except Exception as e:
        if errs is not None:
            errs.append({"code": "index_unreadable", "detail": repr(e)})
        return {}


# ------------------------------------------------------------------ commands
def cmd_init(a):
    t0 = time.time()
    inp, outp, wk = paths(a)
    errs, degr = [], []
    case, cid = {}, "unknown"
    try:
        case, cp = find_case(inp, [])
        cid = str(case.get("case_id") or case.get("id") or (cp.parent.name if cp else "unknown"))
    except Exception as e:
        errs.append({"code": "case_probe_failed", "detail": repr(e)})
    X.jw(outp / "result.json", envelope(case, cid, errs))          # legal partial first
    idx = {}
    try:
        idx, case, cid = build_index(inp, errs, degr)
    except Exception as e:
        import traceback
        errs.append({"code": "index_failed", "detail": "%s: %s" % (type(e).__name__, e),
                     "trace": traceback.format_exc()[-600:]})
    try:
        X.jw(wk / "index.json", idx)
    except Exception as e:
        errs.append({"code": "index_write_failed", "detail": repr(e)})
    docs, anns = idx.get("docs") or {}, idx.get("annotations") or []
    low = [x["ann_id"] for x in anns if x.get("low_confidence")]
    tcnt = {}
    for x in anns:
        tcnt[x["type"]] = tcnt.get(x["type"], 0) + 1
    degr += ["%s: %s" % (s.get("file"), s.get("code")) for s in (idx.get("skipped") or [])]
    res = envelope(case, cid, errs)
    res.update(
        sources=[{"doc_id": k, "file": v.get("filename"), "kind": v.get("kind"),
                  "sha256": (v.get("sha256") or "")[:16], "pages": v.get("n_pages"),
                  "has_text_layer": v.get("has_text_layer")} for k, v in docs.items()],
        degradations=degr[:40],
        uncertainty=["锚点为几何推断（rect × 文本块），最终以 quoted_text 逐字命中为准"] if anns else [],
        pending_human=["读材料并写 %s（schema 见 SKILL.md 第 6 节），然后 check → build" % (wk / "draft.json")],
        coverage={"docs_expected": len(docs), "docs_processed": len([v for v in docs.values() if v.get("has_text_layer")]),
                  "annotations_extracted": len(anns), "annotations_low_confidence": len(low),
                  "notes_created": 0, "queries_total": len(idx.get("queries") or [])},
        runtime={"skill": GEN, "stage": "init", "seconds": round(time.time() - t0, 2),
                 "docs": len(docs), "annotations": len(anns)},
        status="input_error" if not docs else "partial")
    X.jw(outp / "result.json", res)
    print("== library ==")
    for k, v in docs.items():
        flag = []
        if not v.get("has_text_layer"):
            flag.append("NO_TEXT_LAYER")
        if v.get("duplicate_of"):
            flag.append("dup_of=%s" % v["duplicate_of"])
        if v.get("alias_group"):
            flag.append("alias=%s(v=%s)" % (v["alias_group"], v.get("version") or "?"))
        if (v.get("quality") or 1) < 0.5:
            flag.append("low_text_quality")
        print("%s | %s | %s | %s p | sha:%s | %s" % (k, v.get("filename"), v.get("kind"), v.get("n_pages"),
                                                    (v.get("sha256") or "")[:10], ",".join(flag) or "-"))
    print("== annotations == %d | %s | low_conf: %s" % (
        len(anns), ", ".join("%s=%d" % kv for kv in sorted(tcnt.items())) or "none", ", ".join(low[:8]) or "none"))
    for d in idx.get("duplicates") or []:
        print("   duplicate: %s (%s)" % (",".join(d["docs"]), d["kind"]))
    for g in idx.get("aliases") or []:
        print("   alias %s: %s -> canonical %s" % (g["group"], ",".join(g["docs"]), g["canonical"]))
    for n in (idx.get("version_notes") or [])[:6]:
        print("   version_note[%s]: %s" % (n.get("source") or n.get("locator"), n["note"][:150]))
    print("== queries == %d | %s" % (len(idx.get("queries") or []),
                                     "; ".join(q["question"][:70] for q in (idx.get("queries") or [])[:5]) or "none"))
    if idx.get("contract_keys"):
        print("== output_contract == %d keys: %s" % (len(idx["contract_keys"]), ", ".join(idx["contract_keys"])))
    print("== next == 1) show  2) show --ann  3) 写 %s  4) check  5) build" % (wk / "draft.json"))
    return 0


def cmd_show(a):
    _, _, wk = paths(a)
    idx = load_index(wk)
    if not idx:
        print("(no index yet: run `python3 -B scripts/main.py init` first)")
        return 0
    docs, anns = idx.get("docs") or {}, idx.get("annotations") or []
    chars = int(a.chars or 1200)
    if a.ann:
        rows = [x for x in anns if not a.doc or x["doc_id"] == a.doc]
        if a.page:
            rows = [x for x in rows if int(x.get("page") or 0) == int(a.page)]
        for x in rows:
            print("[%s] %s %s p%s type=%s color=%s conf=%.2f method=%s src=%s" % (
                x["ann_id"], x["doc_id"], x.get("locator"), x.get("page"), x.get("type"), x.get("color") or "-",
                float(x.get("anchor_confidence") or 0), x.get("anchor_method"), x.get("source")))
            if x.get("rect"):
                print("    rect=%s overlap=%s" % (x["rect"], x.get("rect_overlap")))
            print("    anchor_confirmed=%s quote: %s" % (x.get("anchor_confirmed"),
                                                         (x.get("quoted_text") or "(none)")[:320]))
            if not x.get("anchor_confirmed") and x.get("candidate_quote"):
                print("    candidate(需人工核对后再引用): %s" % x["candidate_quote"][:320])
            if x.get("comment"):
                print("    comment: %s" % x["comment"][:240])
            if x.get("author") or x.get("created"):
                print("    author=%s created=%s" % (x.get("author") or "-", x.get("created") or "-"))
        print("-- %d annotation(s); copy quoted_text character-for-character into draft.json" % len(rows))
        return 0
    if a.doc:
        if a.doc not in docs:
            print("unknown doc_id %r; available: %s" % (a.doc, ", ".join(docs)))
            return 0
        d = docs[a.doc]
        print("== %s | %s | %s | %s pages | sha256=%s | version=%s | alias=%s | dup_of=%s" % (
            a.doc, d.get("filename"), d.get("kind"), d.get("n_pages"), (d.get("sha256") or "")[:16],
            d.get("version") or "-", d.get("alias_group") or "-", d.get("duplicate_of") or "-"))
        for pg in (idx.get("pages") or {}).get(a.doc) or []:
            if a.page and int(pg.get("page") or 0) != int(a.page):
                continue
            print("\n--- p%s [%s] ---" % (pg.get("page"), pg.get("layout")))
            print((pg.get("text") or "(no text layer)")[:chars])
        for x in anns:
            if x["doc_id"] == a.doc:
                print("  ann %s p%s %s :: %s" % (x["ann_id"], x.get("page"), x.get("type"),
                                                 (x.get("quoted_text") or x.get("candidate_quote") or "")[:90]))
        return 0
    print("== documents ==")
    for k, v in docs.items():
        print("%s | %s | %s | %s p | text=%s | sha:%s | ver=%s | alias=%s | dup=%s" % (
            k, v.get("filename"), v.get("kind"), v.get("n_pages"), v.get("has_text_layer"),
            (v.get("sha256") or "")[:10], v.get("version") or "-", v.get("alias_group") or "-",
            v.get("duplicate_of") or "-"))
    print("\n== annotations (%d) ==" % len(anns))
    for x in anns:
        print("%s | %s | p%s | %s | %s | %s" % (x["ann_id"], x["doc_id"], x.get("page"), x.get("type"),
                                                x.get("color") or "-",
                                                (x.get("quoted_text") or x.get("candidate_quote") or "")[:80]))
    print("\n== version notes ==")
    for n in idx.get("version_notes") or []:
        print("- [%s] %s" % (n.get("source") or n.get("locator"), n["note"][:200]))
    print("\n== queries ==")
    for q in idx.get("queries") or []:
        print("- %s: %s" % (q["qid"], q["question"]))
    print("\n== skipped ==")
    for s in idx.get("skipped") or []:
        print("- %s | %s | %s" % (s.get("file"), s.get("code"), s.get("detail")))
    print("\n-- `show --doc D1` text | `show --ann --doc D1` anchors | `show --page 3` filter")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="annotation-ledger (%s)" % GEN)
    sub = ap.add_subparsers(dest="cmd")
    for n, h in (("init", "index the library, write partial result.json"),
                 ("show", "print documents / pages / annotations with locators"),
                 ("check", "validate work/draft.json (checks.py)"),
                 ("build", "render products + result.json (build.py)"),
                 ("selfcheck", "re-verify the products")):
        q = sub.add_parser(n, help=h)
        q.add_argument("--input")
        q.add_argument("--output")
        q.add_argument("--work")
        if n in ("check", "build"):
            q.add_argument("--draft")
        if n == "show":
            q.add_argument("--ann", action="store_true")
            for f in ("--doc", "--page", "--chars"):
                q.add_argument(f)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        if a.cmd in ("check", "selfcheck"):
            import checks
            (checks.run if a.cmd == "check" else checks.selfcheck)(a)
        elif a.cmd == "build":
            import build
            build.run(a)
        else:
            {"init": cmd_init, "show": cmd_show}[a.cmd](a)
    except Exception as e:
        import traceback
        try:
            inp, outp, _ = paths(a)
            case = find_case(inp, [])[0] if inp.exists() else {}
            r = envelope(case, str(case.get("case_id") or "unknown"),
                         [{"code": "unhandled_exception", "detail": "%s: %s" % (type(e).__name__, e),
                           "trace": traceback.format_exc()[-700:]}])
            r["status"] = "partial"
            r["pending_human"] = ["脚本在 %s 阶段异常，result.json 为合法降级结果" % a.cmd]
            X.jw(outp / "result.json", r)
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
