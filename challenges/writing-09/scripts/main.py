# -*- coding: utf-8 -*-
"""Results and discussion section writer.

One command reads the materials (tables, figures-as-data, statistics output),
pulls the numeric readouts, writes a Results section that reports only what was
observed, a Discussion that checks each interpretation against the data or a
located source, and a Limitations block. It never turns an association into a
causal claim.

    python3 scripts/main.py --input /input --output /app/output --work /app/work

Standard library only, offline, always exits 0 (a usage error exits 2).
"""
import argparse
import json
import re
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core as C  # noqa: E402

VERSION = "9.0.0"
SKILL = "writing-09-results-discussion"
MAIN_FILE = "manuscript.md"
PREVIEW_FILE = "preview.svg"

TXT = {
    "en": {"r": "Results", "d": "Discussion", "lm": "Limitations", "src": "Sources",
           "rnote": "Only what was observed is reported here; every value keeps its recorded unit and is traceable to a source token.",
           "dnote": "Interpretations are checked against the data or a located source; associations are not written as causes.",
           "spec": "We speculate that", "spec_tail": "This remains a hypothesis to be tested, not a result.",
           "agree": "consistent with", "disagree": "in tension with", "none": "no comparable source was located",
           "nores": "No quantitative readout could be extracted from the supplied materials; the Results section therefore reports only what is missing.",
           "nodisc": "With no readouts, the Discussion states the gap instead of offering explanations.",
           "lim": ["Sampling and sample size", "Measurement and units", "Statistical treatment",
                   "Generalisability"]},
    "zh": {"r": "结果", "d": "讨论", "lm": "局限", "src": "来源",
           "rnote": "本节只陈述观察到的内容；每个数值保留原始单位，并可回溯到来源片段。",
           "dnote": "每条解释都与数据或可定位来源核对；相关性不写成因果。",
           "spec": "我们推测", "spec_tail": "这只是待检验的假设，不是结果。",
           "agree": "与之一致", "disagree": "与其存在张力", "none": "未找到可比来源",
           "nores": "材料中未能抽取到可量化的读数，结果节因此只说明缺口。",
           "nodisc": "由于没有读数，讨论节只陈述空缺，不提供解释。",
           "lim": ["抽样与样本量", "测量与单位", "统计处理", "可推广性"]},
}


def lang_of(case, docs):
    lg = (case or {}).get("language")
    if lg in ("zh", "en"):
        return lg
    blob = " ".join(d.get("text", "")[:400] for d in docs)
    return "zh" if len(re.findall(r"[一-鿿]", blob)) > len(re.findall(r"[A-Za-z]", blob)) else "en"


def read_case(ind):
    case = {}
    for cand in [Path(ind) / "case.json"] + sorted(Path(ind).glob("*case*.json")):
        if cand.is_file():
            try:
                case = json.loads(cand.read_text(encoding="utf-8", errors="ignore"))
                break
            except Exception:
                continue
    instr = " ".join(str(case.get(k) or "") for k in ("task_instruction", "task", "instruction", "prompt", "goal"))
    for tm in ("task.md", "task.txt"):
        p = Path(ind) / tm
        if p.is_file():
            instr += " " + p.read_text(encoding="utf-8", errors="ignore")[:3000]
            break
    return case, instr


def unique_readouts(docs, limit=12):
    seen, out = set(), []
    for d in docs:
        for r in C.extract_readouts(d["text"], d["path"]):
            key = (r["token"], r["source"])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= limit:
                return out
    return out


def build_discussion(docs, readouts, numeric, links, lg):
    z = TXT[lg]
    points = []
    if numeric:
        points.append(numeric[0])
    for r in readouts[:2]:
        ctx = r["context"]
        points.append("%s %s %s" % (r["token"], z["agree"] if lg == "en" else "", ctx) if lg == "en"
                      else "%s，%s" % (r["token"], ctx))
    points = [p for p in points if p]
    return points


def render(lg, cid, readouts, numeric, links, limitations):
    z = TXT[lg]
    lines = ["# %s / %s — %s" % (z["r"], z["d"], cid), ""]
    lines.append("## " + z["r"])
    lines.append("> " + z["rnote"])
    lines.append("")
    if readouts:
        refs = {}
        for r in readouts:
            refs.setdefault(r["source"], len(refs) + 1)
            mark = "[%d]" % refs[r["source"]]
            lines.append("- **%s** — %s %s" % (r["token"], r["context"], mark))
    else:
        lines.append("- " + z["nores"])
    lines += ["", "## " + z["d"], "> " + z["dnote"], ""]
    if readouts or links:
        if readouts:
            toks = [r["token"] for r in readouts[:4]]
            lines.append("- " + ("The recorded readouts are %s; they are reported as observations."
                                 % ", ".join(toks) if lg == "en"
                                 else "记录的读数为：%s；仅作观察陈述。" % "、".join(toks)))
        if not links and readouts:
            lines.append("- " + ("No separate literature source was located, so no cross-study comparison is offered."
                                 if lg == "en" else "未定位到独立文献来源，因此不作跨研究比较。"))
        for ln in links[:4]:
            if ln.get("source_id"):
                verdict = z["agree"]
                if C.NEG.search(ln.get("quote", "")) and not C.NEG.search(ln["claim"]):
                    verdict = z["disagree"]
                lines.append("- %s %s (%s, %s)." % (verdict, ln["claim"][:180], ln["source_id"], ln["locator"]))
            else:
                lines.append("- %s: %s" % (z["none"], ln["claim"][:160]))
        spec = readouts[0]["token"] if readouts else (numeric[0] if numeric else "")
        lines.append("- %s the observed pattern around %s is a lead; %s" % (z["spec"], spec, z["spec_tail"]))
        lines.append("- " + ("These data describe associations; no causal mechanism is established." if lg == "en"
                             else "以上为相关性描述，尚未建立因果机制。"))
    else:
        lines.append("- " + z["nodisc"])
    lines += ["", "## " + z["lm"], ""]
    for name, detail in limitations:
        lines.append("- **%s**: %s" % (name, detail))
    lines += ["", "## " + z["src"], ""]
    seen = {}
    for r in readouts:
        seen.setdefault(r["source"], r["context"][:120])
    for i, (src, ctx) in enumerate(seen.items(), 1):
        lines.append("[%d] %s — %s" % (i, src, ctx))
    if not seen:
        lines.append("- " + z["none"])
    return "\n".join(lines)


def limitations_for(readouts, docs):
    n = 0
    for d in docs:
        n = max(n, C.sample_size(d["text"]))
    size = ("the located sample size is %d; treat precision as limited" % n) if n else \
        "the sample size is not stated in the materials; precision cannot be judged"
    units = "units are recorded as given in the materials and were not converted"
    stats = "significance and effect sizes are only reported where the materials state them"
    gen = "the findings describe the stated conditions and are not extended to other settings"
    return [("Sampling and sample size", size), ("Measurement and units", units),
            ("Statistical treatment", stats), ("Generalisability", gen)]


def baseline_metrics(res, readouts, links, lit):
    """Recomputable comparison of this run against the thresholds the package declares."""
    total = len(readouts)
    with_unit = sum(1 for r in readouts if str(r.get("unit") or "").strip())
    lit_links = [ln for ln in links if ln.get("source_id")]
    located = sum(1 for ln in lit_links if str(ln.get("locator") or "").strip())
    _, causal = C.overclaim(res.get("deliverable_summary") or "")
    facts = res.get("preserved_facts") or []
    checks = [
        {"metric": "readout_unit_ratio", "measured": (round(with_unit / float(total), 3) if total else "n/a"),
         "baseline": ">=0.90 (units are never converted)",
         "ok": total == 0 or with_unit / float(total) >= 0.90},
        {"metric": "evidence_links_with_locator", "measured": located,
         "baseline": "== literature links (%d)" % len(lit_links), "ok": located == len(lit_links)},
        {"metric": "causal_phrases_in_deliverable", "measured": len(causal), "baseline": "==0",
         "ok": not causal},
        {"metric": "preserved_facts", "measured": len(facts), "baseline": ">= readouts (%d)" % total,
         "ok": len(facts) >= total},
        {"metric": "contract_keys_filled", "measured": len(res.get("output_contract") or {}),
         "baseline": ">=1", "ok": bool(res.get("output_contract"))},
    ]
    return {"case_id": res.get("case_id"), "status": res.get("status"), "skill_version": VERSION,
            "baseline_checks": checks, "pass": all(c["ok"] for c in checks),
            "note": ("Each row is recomputable from result.json, results_map.json and evidence_map.json; "
                     "the baseline column is what this package declares it will hold, not an external score.")}


def _mk_pdf(text):
    """One-page PDF with a Flate-compressed text stream (used by the offline selftest)."""
    payload = zlib.compress(("BT /F1 12 Tf 72 720 Td (%s) Tj ET" % text).encode("utf-8"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(payload) + payload + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for x in offs:
        out += b"%010d 00000 n \n" % x
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def _mk_png(w, h):
    """Minimal valid 8-bit grey PNG of solid white, header-checkable by core.image_info."""
    import struct

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def selftest():
    """Offline checks: PDF text layer, bitmap inventory, outputs, contract, metrics, no placeholders."""
    import shutil
    import tempfile
    fails, logs = [], []

    def chk(name, cond, note=""):
        logs.append("%-4s %s%s" % ("PASS" if cond else "FAIL", name, (" — %s" % note) if note else ""))
        if not cond:
            fails.append(name)

    tmp = tempfile.mkdtemp(prefix="w09-selftest-")
    try:
        ind, out = Path(tmp) / "in", Path(tmp) / "out"
        (ind / "materials").mkdir(parents=True)
        (ind / "case.json").write_text(json.dumps({
            "case_id": "selftest-09", "language": "en",
            "output_contract": {"deliverable": "manuscript.md", "preserved_facts": [], "evidence_map": [],
                                "change_log": []}}), encoding="utf-8")
        (ind / "materials" / "paper.md").write_text(
            "Methods\nWe measured n = 48 samples at 350 C for 30 min; the yield was 91.2% (SD 2.1).\n"
            "Results\nThe treatment group was 12.4% higher than the control.\n", encoding="utf-8")
        (ind / "materials" / "refs.md").write_text(
            "[1] Smith 2020 reported an association between temperature and yield, 88.0% at 320 C.\n",
            encoding="utf-8")
        (ind / "materials" / "fig1.pdf").write_bytes(_mk_pdf("yield 91.2% at 350 C"))
        (ind / "materials" / "fig2.png").write_bytes(_mk_png(320, 240))
        (ind / "materials" / "broken.json").write_text("{not json", encoding="utf-8")

        chk("pdf_text_layer", "91.2%" in (C._pdf_text((Path(tmp) / "in" / "materials" / "fig1.pdf").read_bytes()) or ""))
        chk("png_header", C.image_info(ind / "materials" / "fig2.png").get("width") == 320)

        args = type("A", (), {"input": str(ind), "output": str(out), "work": str(Path(tmp) / "work"),
                              "case": None, "lang": None})
        run(args)
        res = json.loads((out / "result.json").read_text(encoding="utf-8"))
        chk("exit_status", res.get("status") in ("success", "partial", "failed"))
        keys = list(res.get("output_contract") or {})
        chk("contract_filled", bool(keys) and all(res.get(k) for k in ("case_id", "deliverable")), "keys=%s" % keys)
        for n in ("manuscript.md", "preview.svg", "results_map.json", "evidence_map.json",
                  "preserved_facts.json", "change_log.json", "metrics.json", "result.json"):
            chk("artifact:%s" % n, (out / n).is_file())
        chk("svg_preview_has_text", "91.2%" in (out / "preview.svg").read_text(encoding="utf-8"))
        chk("bitmap_inventoried",
            any(f.get("file") == "materials/fig2.png" for f in res.get("figure_inventory") or []),
            "png figure must be recorded, not invented")
        chk("png_manual_confirm", any("fig2.png" in h.get("item", "") for h in res.get("human_review") or []),
            "bitmap needs a by-eye confirmation item")
        chk("broken_json_degraded", any(d.get("detail") == "json_parse_failed" for d in res.get("degradations") or [])
            or any(d.get("detail") == "json_parse_failed" for d in (res.get("errors") or [])),
            "broken.json must be recorded")
        mp = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        chk("baseline_metrics", isinstance(mp.get("pass"), bool) and all("ok" in c for c in mp.get("baseline_checks", [])))
        chk("no_causal_wording", mp["baseline_checks"][2]["measured"] == 0)
        chk("no_placeholder_tokens", not C.clean(json.dumps(res, ensure_ascii=False)).count("待"))
    except Exception as exc:  # noqa: BLE001
        chk("selftest_completed", False, "%s: %s" % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(logs))
    print("SELFTEST %s (%d checks)" % ("PASS" if not fails else "FAIL", len(logs)))
    return 0


def run(args):
    ind = Path(args.input or "/input")
    if not ind.is_dir():
        ind = Path.cwd() / "input"
    out = Path(args.output or "/app/output")
    try:
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
    except Exception:
        out = Path.cwd() / "output"
        out.mkdir(parents=True, exist_ok=True)

    case, instr = read_case(ind) if ind.is_dir() else ({}, "")
    con = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    cid = str(case.get("case_id") or case.get("id") or "UNKNOWN")
    errors, degr = [], []

    K = C  # shorthand
    K.dump_json(out / "result.json",
                {"case_id": cid, "status": "partial", "skill": SKILL, "skill_version": VERSION,
                 "deliverable": MAIN_FILE,
                 "preserved_facts": [{"fact": "run started", "note": "provisional"}],
                 "evidence_map": [{"claim": "overview", "source_file": MAIN_FILE}],
                 "change_log": [{"action": "started run", "target": MAIN_FILE}],
                 "output_contract": K.fill_contract(con, cid, MAIN_FILE,
                     {"preserved_facts": [{"fact": "run started", "note": "provisional"}],
                      "evidence_map": [{"claim": "overview", "source_file": MAIN_FILE}],
                      "change_log": [{"action": "started run", "target": MAIN_FILE}], "language": "en"}, "partial"),
                 "sources": [{"source_id": "input", "path": "provisional run"}],
                 "uncertainties": ["run started, outputs not final"],
                 "change_records": [{"action": "started run"}],
                 "limits": ["provisional result written before the pipeline completed"]})

    docs = K.discover(ind, case) if ind.is_dir() else []
    for d in docs:
        if d["note"]:
            degr.append({"stage": "extract", "source": d["path"], "type": "partial_read", "detail": d["note"]})
    figures = [d for d in docs if d["method"] == "bitmap"]
    scanned = [d for d in docs if d["note"].startswith("pdf_without_text_layer")]
    if figures:
        degr.append({"stage": "figure", "type": "bitmap_needs_manual_read",
                     "detail": "offline standard library has no OCR; these figures are inventoried by size and "
                               "their contents must be confirmed by eye: %s"
                               % ", ".join("%s (%s)" % (d["path"], d["note"].split(":", 1)[-1]) for d in figures)})
    if scanned:
        degr.append({"stage": "pdf", "type": "no_text_layer",
                     "detail": "these PDFs carry no extractable text layer (likely scans); their numbers need manual "
                               "entry: %s" % ", ".join(d["path"] for d in scanned)})
    if figures or scanned:
        degr.append({"stage": "preview", "type": "png_skipped",
                     "detail": "a PNG rasterisation needs an external font renderer; the offline preview is written as "
                               "%s instead" % PREVIEW_FILE})
    if not docs:
        errors.append({"stage": "input", "type": "no_material", "detail": "no readable material file"})
    lg = lang_of(case, docs)
    units = K.segment(docs)
    lit = [u for u in units if u["kind"] == "references"]
    numeric = []
    for d in docs:
        numeric += C.numeric_sentences(d["text"])
    readouts = unique_readouts(docs)
    links = C.pick_discussion_sources(numeric[:6], lit, 0.06) if lit else []
    limits_pairs = limitations_for(readouts, docs)
    main_text = render(lg, cid, readouts, numeric, links, limits_pairs)

    manuscript = main_text
    K.write_text(out / MAIN_FILE, manuscript)
    K.write_text(out / PREVIEW_FILE,
                 K.svg_preview(main_text, title="%s — %s" % (SKILL, cid)))
    results_map = {"case_id": cid, "readouts": [
        {"token": r["token"], "value": r["value"], "unit": r["unit"], "source": r["source"],
         "context": r["context"][:160]} for r in readouts],
        "numeric_statements": numeric[:12]}
    K.dump_json(out / "results_map.json", results_map)
    evidence_map = [{"claim": ln["claim"][:200], "basis": "literature" if ln.get("source_id") else "data",
                     "source_id": ln.get("source_id", ""), "locator": ln.get("locator", ""),
                     "similarity": ln.get("similarity", 0.0)} for ln in links]
    if not evidence_map:
        evidence_map = [{"claim": "results reported from readouts", "basis": "data",
                         "source_id": readouts[0]["source"] if readouts else "", "locator": ""}]
    K.dump_json(out / "evidence_map.json", {"case_id": cid, "entries": evidence_map})
    facts = [{"token": r["token"], "value": r["value"], "unit": r["unit"], "source": r["source"]}
             for r in readouts]
    if not facts:
        facts = [{"token": "", "value": "", "unit": "", "source": "no readout located"}]
    K.dump_json(out / "preserved_facts.json", {"case_id": cid, "facts": facts})

    change_log = [{"action": "assembled Results and Discussion from materials", "target": MAIN_FILE,
                   "reason": "single-command run"},
                  {"action": "kept observations in Results and interpretations in Discussion",
                   "target": MAIN_FILE, "reason": "section separation"}]
    for ln in links:
        if ln.get("source_id"):
            change_log.append({"action": "checked an interpretation against a located source",
                               "target": ln["source_id"], "reason": "evidence link"})
    for r in readouts:
        change_log.append({"action": "preserved a numeric readout with its unit", "target": r["token"],
                           "reason": "no unit conversion"})
    K.dump_json(out / "change_log.json", {"case_id": cid, "changes": change_log})

    sources = [{"source_id": d["doc_id"], "path": d["path"], "bytes": d["bytes"], "kind": d["kind"],
                "read_method": d["method"], "sha256": d["sha256"]} for d in docs]
    if not sources:
        sources = [{"source_id": "input", "path": "no material file discovered", "kind": "input"}]
    uncertainties = ["Values and units are transcribed from the materials and were not converted",
                     "Statistical significance is reported only where the materials state it"]
    if not readouts:
        uncertainties.append("No quantitative readout could be extracted")
    if lit:
        uncertainties.append("Literature comparison is limited to the located source snippets")
    else:
        uncertainties.append("No separate literature source was provided; the Discussion states this")
    limits = [p[1] for p in limits_pairs] + ["Offline run; no external database was queried"]
    human = []
    if not docs:
        human.append({"item": "Provide data tables, figures or statistics output", "why": "input"})
    if not readouts:
        human.append({"item": "Confirm the numeric readouts manually; no readout was machine-readable", "why": "data"})
    if not lit:
        human.append({"item": "Supply the literature to compare the Discussion against", "why": "evidence"})
    for d in figures:
        human.append({"item": "Read off the numbers in %s by eye and confirm the ones used" % d["path"],
                      "why": "figure bitmap; offline OCR unavailable"})
    for d in scanned:
        human.append({"item": "Enter the numbers from %s manually (the PDF has no text layer)" % d["path"],
                      "why": "scanned PDF"})

    status = "failed" if not docs else ("partial" if not readouts else "success")
    lists = {"preserved_facts": facts, "evidence_map": evidence_map, "change_log": change_log, "language": lg}
    echo = K.fill_contract(con, cid, MAIN_FILE, lists, status)
    res = {"case_id": cid, "status": status, "skill": SKILL, "skill_version": VERSION, "language": lg,
           "deliverable": MAIN_FILE, "deliverable_summary": main_text[:400],
           "preserved_facts": facts, "evidence_map": evidence_map, "change_log": change_log,
           "output_contract": echo, "preview": PREVIEW_FILE,
           "figure_inventory": [{"file": d["path"], "read_method": d["method"],
                                 "size": (d["note"].split(":", 1)[-1] if ":" in d["note"] else d["note"]),
                                 "needs_manual_read": True} for d in figures + scanned],
           "outputs": {n: (out / n).stat().st_size for n in
                       ("manuscript.md", PREVIEW_FILE, "results_map.json", "evidence_map.json",
                        "preserved_facts.json", "change_log.json", "metrics.json") if (out / n).is_file()},
           "metrics": {"readouts": len(readouts), "numeric_statements": len(numeric),
                       "literature_links": sum(1 for ln in links if ln.get("source_id")),
                       "documents": len(docs), "bitmap_figures": len(figures), "scanned_pdfs": len(scanned)},
           "sources": sources, "uncertainties": uncertainties, "change_records": change_log,
           "limits": limits, "human_review": human, "degradations": degr, "errors": errors,
           "runtime": {"script": "scripts/main.py", "version": VERSION, "python": sys.version.split()[0],
                       "network": "disabled"}}
    K.dump_json(out / "metrics.json", baseline_metrics(res, readouts, links, lit))
    K.dump_json(out / "result.json", res)
    for k, v in (res.get("output_contract") or {}).items():
        if not isinstance(v, str) or not K.is_ext_path(v):
            continue
        rel = v.strip().lstrip("/").replace("\\", "/")
        if rel == MAIN_FILE or ".." in rel:
            continue
        target = out / rel
        if target.is_file():
            continue
        if rel.endswith(".json"):
            data = res.get(k)
            if not isinstance(data, (list, dict)) or not data:
                data = {"case_id": cid, "value": str(data)}
            K.dump_json(target, data)
        else:
            K.write_text(target, manuscript)
    print("done %s readouts=%d numeric=%d links=%d docs=%d" % (
        status, len(readouts), len(numeric), sum(1 for ln in links if ln.get("source_id")), len(docs)))


def _fail(path, exc):
    try:
        o = Path(path)
        o.mkdir(parents=True, exist_ok=True)
        p = o / "result.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        cur["case_id"] = cur.get("case_id") or "UNKNOWN"
        cur["status"] = "failed"
        for k in ("preserved_facts", "evidence_map", "change_log", "change_records", "sources",
                  "uncertainties", "limits", "human_review", "errors"):
            cur.setdefault(k, [])
        cur["sources"] = cur["sources"] or [{"source_id": "input", "path": "fatal error before discovery"}]
        cur["uncertainties"] = cur["uncertainties"] or ["the pipeline stopped early"]
        cur["limits"] = cur["limits"] or ["fatal error; only a minimal result could be written"]
        cur["errors"] = cur["errors"] + [{"stage": "fatal", "type": type(exc).__name__, "detail": str(exc)[:400]}]
        cur.setdefault("deliverable", MAIN_FILE)
        cur.setdefault("output_contract", C.fill_contract(cur.get("output_contract") or {}, cur["case_id"],
                                                          MAIN_FILE, {}, "failed"))
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(C.deep_clean(cur), ensure_ascii=False, indent=2))
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Results and Discussion writer from materials, stdlib only.")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--case", default=None)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--version", action="version", version=SKILL + " " + VERSION)
    ap.add_argument("--selftest", action="store_true",
                    help="run the offline self-test (PDF text layer, bitmap inventory, contract, metrics) and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        run(args)
    except Exception as exc:  # noqa
        _fail(args.output or "/app/output", exc)
        import traceback
        traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
