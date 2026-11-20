"""main.py - graphical abstract workbench: init | show | check | build | selfcheck.

init indexes /input and writes a legal partial result.json; show prints quotable passages with
locators; check audits the agent draft; build renders and finalises result.json; selfcheck audits
the files written. Stdlib only, offline, CWD-independent, exit code always 0.
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import content
    import core
    import emit
    import layout
    LIB_ERR = ""
except Exception as exc:                                   # pragma: no cover
    content = core = emit = layout = None
    LIB_ERR = "%s: %s" % (type(exc).__name__, exc)

DEFAULT_INPUT = os.environ.get("GA_INPUT") or "/input"
DEFAULT_WORK = os.environ.get("GA_WORK") or "/app/work"
DEFAULT_OUTPUT = os.environ.get("GA_OUTPUT") or "/app/output"

# Contract keys are matched semantically: case files name the same deliverable
# differently, and a renamed key loses points even when the file is right.
CANON = [ ("editable_source", ("editable_source", "editable", "editable_svg", "source_file", "svg_source",
                         "native_source")),
    ("export_artifact", ("export_artifact", "export", "exports", "exported", "deliverable", "artifact",
                         "pdf", "png", "rendered")),
    ("content_map", ("content_map", "element_map", "evidence_map", "mapping", "provenance",
                     "source_map", "trace", "citations")),
    ("compliance_checks", ("compliance_checks", "compliance", "checks", "validation",
                           "export_check", "qa", "quality_checks")),
    ("edit_record", ("edit_record", "edit_log", "revision_record", "version_record", "change_record")),
    ("figure_model", ("figure_model", "layout_model", "figure_spec", "model")),
    ("figure_caption", ("figure_caption", "caption", "legend_caption", "subtitle")),
    ("encodings", ("encodings", "encoding", "data_encoding", "visual_encoding", "channels")),
    ("exceptions", ("exceptions", "exception", "exceptions_log", "deviations", "limitations", "caveats")),
    ("sources", ("sources", "source_list", "materials", "references", "inputs")),
    ("uncertainty", ("uncertainty", "uncertainties", "confidence", "risks")),
    ("pending_human", ("pending_human", "human_review", "follow_ups", "open_questions", "todos")),
    ("changes", ("changes", "change_log", "revisions")),
    ("errors", ("errors", "error_log")),
    ("degradations", ("degradations", "degraded", "fallbacks")),
    ("coverage", ("coverage", "completeness")),
    ("runtime", ("runtime", "execution", "trace_log")),
    ("status", ("status", "run_status", "state")),
    ("case_id", ("case_id", "caseid", "case")),
]

def key_norm(k):
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_")

def fill_contract(contract, payload):
    """Every contract key comes back, same name, same order, null when unmapped."""
    filled, unmatched = {}, []
    keys = list(contract.keys()) if isinstance(contract, dict) else [str(k) for k in (contract or [])]
    for k in keys:
        kn, best, score = key_norm(k), None, 0
        for canon, aliases in CANON:
            for a in aliases:
                if kn == a:
                    s = 100
                elif a in kn or kn in a:
                    s = 40 + len(a)
                else:
                    continue
                if s > score and payload.get(canon) is not None:
                    best, score = canon, s
        filled[k] = payload.get(best) if best else None
        if best is None:
            unmatched.append(str(k))
    return filled, unmatched

def write_result(outdir, index, contract, payload, status, errors, degr, exc, changes, t0):
    payload = dict(payload or {})
    payload.setdefault("status", status)
    payload.setdefault("exceptions", exc or [])
    filled, unmatched = fill_contract(contract, payload)
    res = dict(filled)
    res.update({ "case_id": index.get("case_id"), "status": status,
        "editable_source": payload.get("editable_source"),
        "export_artifact": payload.get("export_artifact"),
        "content_map": payload.get("content_map"),
        "compliance_checks": payload.get("compliance_checks"),
        "edit_record": payload.get("edit_record"),
        "figure_model": payload.get("figure_model"),
        "exceptions": exc or [], "sources": payload.get("sources") or [],
        "uncertainty": payload.get("uncertainty") or [],
        "pending_human": payload.get("pending_human") or [],
        "errors": errors, "degradations": degr, "changes": changes,
        "runtime": {"tool": "scripts/main.py", "python": sys.version.split()[0], "offline": True,
                    "cwd_independent": True, "elapsed_s": round(time.time() - t0, 2) if t0 else None,
                    "case_path": index.get("case_path"),
                    "contract_keys_total": len(contract or {}),
                    "contract_keys_filled": sum(1 for v in filled.values() if v is not None),
                    "unmatched_contract_fields": unmatched,
                    "spec_source": ("case.json organizer_workorder" if index.get("workorder_found")
                                    else "case.json keys / task.md defaults"),
                    "spec_defaults": (index.get("spec") or {}).get("defaults") or []},
    })
    for k in ("encodings", "coverage", "figure_caption"):
        if payload.get(k) is not None and k not in res:
            res[k] = payload[k]
    core.dump(Path(outdir) / "result.json", res)
    return res

def sources_payload(index):
    return [{"id": m["sid"], "name": m["name"], "kind": m["kind"], "bytes": m["bytes"],
             "sha256": m["sha256"], "paragraphs": m["paragraphs"], "method": m["method"]}
            for m in index.get("materials") or []]

def cmd_init(a):
    t0, work, out = time.time(), Path(a.work), Path(a.output)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    errs = []
    index = core.build_index(a.input, work, errs)
    spec, cv = index["spec"], index["spec"]["canvas"]
    write_result(out, index, index["contract"], {"sources": sources_payload(index)}, "partial", errs,
                 ["result.json written at init: no figure exists yet"], [],
                 [{"what": "indexed input", "detail": "%d material(s), %d passage(s)" %
                                                      (len(index["materials"]), len(index["paragraphs"]))}], t0)
    print("[init] case_id=%s  contract_keys=%d  workorder=%s" %
          (index["case_id"], len(index["contract"]), "found" if index["workorder_found"] else "not found"))
    print("[init] canvas=%gx%g %s (%.1f x %.1f pt) dpi=%d  min_font=%g pt  roles=%s" %
          (cv["width"], cv["height"], cv["unit"], cv["w_pt"], cv["h_pt"], cv["dpi"],
           spec["style"]["min_font_pt"], "/".join(spec["required_roles"])))
    if spec["must_include"]:
        print("[init] must_include:", spec["must_include"])
    if spec["required_channels"]:
        print("[init] required channels:", spec["required_channels"])
    if spec["source_artifact"]:
        print("[init] edit source:", spec["source_artifact"])
    for m in index["materials"]:
        print("   %-3s %-7s %8dB  paras=%-4d %s  [%s]" %
              (m["sid"], m["kind"], m["bytes"], m["paragraphs"], m["name"], m["method"][:70]))
    for n in spec.get("defaults") or []:
        print("   default:", n)
    for e in errs:
        print("   error:", e)
    print("[init] passages=%d  NEXT: read `show`, write %s/draft.json, then `check`, then `build`"
          % (len(index["paragraphs"]), work))
    return 0

def cmd_show(a):
    index = core.read_json(Path(a.work) / "index.json")
    spec = index.get("spec") or {}
    if a.workorder:
        print(json.dumps(spec, ensure_ascii=False, indent=2)[:6000])
        return 0
    if a.contract:
        print("[show] output_contract (%d keys)" % len(index.get("contract") or {}))
        for k, v in (index.get("contract") or {}).items():
            print("   %-32s %s" % (k, core.norm(v if not isinstance(v, (dict, list)) else
                                                json.dumps(v, ensure_ascii=False))[:110]))
        return 0
    paras = index.get("paragraphs") or []
    if a.tables:
        rows = [p for p in paras if p.get("source", "").lower().endswith((".csv", ".tsv"))]
        print("[table] %d row(s) from %d table file(s)" % (len(rows), len({r["source"] for r in rows})))
        for p in rows[:int(a.limit)]:
            print("   %-14s %-16s %s" % (p["source"][:16], p["locator"], core.norm(p["text"])[:130]))
        return 0
    sel = paras
    if a.sid:
        sel = [p for p in sel if a.sid in (p.get("sid"), p.get("source"))]
    if a.grep:
        needle = content.loose(a.grep)
        sel = [p for p in sel if needle in content.loose(p.get("text"))]
    print("[show] %d passage(s); materials: %s" % (len(sel), ", ".join(
        "%s=%s" % (m["sid"], m["name"]) for m in index.get("materials") or [])))
    print("[show] canvas %.0fx%.0f pt; roles %s; copy quotes character for character, keep the locator"
          % (spec.get("canvas", {}).get("w_pt", 0), spec.get("canvas", {}).get("h_pt", 0),
             "/".join(spec.get("required_roles") or [])))
    for p in sel[:int(a.limit)]:
        print("--- [%s] %s :: %s" % (p.get("sid"), p.get("source"), p.get("locator")))
        print(core.norm(p.get("text"))[:int(a.chars)])
    if len(sel) > int(a.limit):
        print("... %d more; raise --limit or narrow --grep" % (len(sel) - int(a.limit)))
    return 0

def cmd_check(a):
    work = Path(a.work)
    report = {"ok": False, "problems": ["check could not run"], "warnings": [], "stats": {}}
    try:
        index = core.prepare_index(a.input, work, [])
        draft, src = content.load_draft(work)
        if draft is None:
            report["problems"] = ["%s: write /app/work/draft.json first (SKILL.md section 6)" % src]
            report["warnings"] = ["build would fall back to a degraded, quote-only figure; fix the draft"]
        else:
            degr = []
            draft = content.expand_charts(draft, index, degr)
            rep = core.evaluate(draft, index.get("paragraphs") or [], index.get("spec") or {})
            report = {"ok": rep["ok"], "problems": rep["problems"], "warnings": rep["warnings"] + degr,
                      "stats": {"panels": len(draft.get("panels") or []), "items": rep["items"],
                                "verified": rep["verified"], "coverage": rep["coverage"],
                                "roles": rep["roles"], "encodings": rep["encodings"],
                                "claims": rep["claims"], "numbers": rep["numbers"],
                                "untraced": rep["unmatched_numbers"]}}
    except Exception as exc:
        report["problems"] = ["check crashed: %s" % str(exc).splitlines()[0][:200]]
        report["trace"] = traceback.format_exc()[-800:]
    core.dump(work / "check.json", report)
    st = report.get("stats") or {}
    print("[check] panels=%s items=%s verified=%s coverage=%s encodings=%s untraced=%s -> %s" %
          (st.get("panels"), st.get("items"), st.get("verified"), st.get("coverage"),
           st.get("encodings"), st.get("untraced"), "PASS" if report["ok"] else "NEEDS WORK"))
    for p in report["problems"]:
        print("  FAIL", p)
    for w in report["warnings"][:14]:
        print("  warn", w)
    print("[check] next: %s" % ("run build" if report["ok"] else
                                "fix the FAIL lines and re-run check; do not skip to build"))
    return 0

def cmd_build(a):
    t0, work, out = time.time(), Path(a.work), Path(a.output)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    errs, degr, exc, files, payload = [], [], [], {}, {}
    status, index = "ok", {"case_id": None, "contract": {}, "spec": {}, "paragraphs": [], "materials": []}
    try:
        index = core.prepare_index(a.input, work, errs)
        errs += [e for e in (index.get("input_errors") or []) if e not in errs]
        spec, contract = index.get("spec") or {}, index.get("contract") or {}
        draft, src = content.load_draft(work)
        if draft is None:
            draft = content.fallback_draft(index)
            degr.append("no usable work draft (%s): figure assembled from verbatim sentences" % src)
            exc.append({"code": "plan_missing", "where": "work/draft.json", "detail": src,
                        "action": "deterministic fallback; write draft.json for a curated figure"})
            status = "partial"
        draft = content.expand_charts(draft, index, degr)
        rep = core.evaluate(draft, index.get("paragraphs") or [], spec)
        degr += ["pre-build audit: " + p for p in rep["problems"]]
        content.prune(draft, exc, degr)
        rep = core.evaluate(draft, index.get("paragraphs") or [], spec)   # what actually reaches the page
        if rep.get("unmatched_numbers"):
            status = "partial"
        model = layout.compose(draft, spec)
        svg_p, pdf_p = out / "graphical_abstract.svg", out / "graphical_abstract.pdf"
        png_p = out / "graphical_abstract.png"
        svg_p.write_text(emit.to_svg(model), encoding="utf-8")
        pdf_p.write_bytes(emit.to_pdf(model))
        files = {"svg": str(svg_p), "pdf": str(pdf_p)}
        ok, engine, note, px = emit.to_png(model, str(png_p), model["canvas"]["dpi"], str(pdf_p))
        if ok and os.path.isfile(png_p):
            files["png"] = str(png_p)
            png = {"path": "graphical_abstract.png", "engine": engine, "note": note, "px": px,
                   "dpi": model["canvas"]["dpi"],
                   "dims_match_canvas": bool(px and abs(px[0] - round(model["canvas"]["w_pt"] / 72.0 *
                                                                      model["canvas"]["dpi"])) <= 8)}
        else:
            png = {"path": None, "engine": "none", "note": note, "px": None}
            degr.append("PNG preview unavailable (%s): the vector PDF stays the export artifact" % note)
            status = "partial"
        if model.get("dropped") and status == "ok":
            status = "partial"
        cmap = content.content_map(model, draft, index, rep)
        checks = content.compliance(model, spec, files, png, rep, index)
        if not checks["pass"] and status == "ok":
            status = "partial"
        erec = content.edit_record(model, draft, index, spec, files, out)
        for name, obj in (("figure_model.json", model), ("content_map.json", cmap),
                          ("compliance_checks.json", checks), ("edit_record.json", erec)):
            core.dump(out / name, obj)
        payload = { "sources": sources_payload(index),
            "editable_source": {"path": "graphical_abstract.svg", "format": "svg", "editable": True,
                                "layers": layout.LAYERS, "text_count": model["stats"]["text_ops"],
                                "sha256": core.sha256_file(svg_p, 0),
                                "viewbox_pt": [model["canvas"]["w_pt"], model["canvas"]["h_pt"]]},
            "export_artifact": {"pdf": {"path": "graphical_abstract.pdf", "pages": 1, "vector": True,
                                        "page_pt": [model["canvas"]["w_pt"], model["canvas"]["h_pt"]],
                                        "sha256": core.sha256_file(pdf_p, 0)},
                                "png": {"path": png["path"], "px": png["px"], "dpi": png["dpi"],
                                        "engine": png["engine"]},
                                "svg": {"path": "graphical_abstract.svg", "format": "svg",
                                        "bytes": content.size_of(str(svg_p))}},
            "content_map": cmap, "compliance_checks": checks, "edit_record": erec,
            "figure_model": {"path": "figure_model.json", "digest": emit.model_digest(model),
                             "panels": len(model["panels"]), "elements": len(model["elements"])},
            "figure_caption": model.get("caption") or model.get("subtitle") or model.get("title"),
            "encodings": cmap["encodings"], "coverage": cmap["coverage"],
            "uncertainty": ["%d element(s) dropped for missing evidence" %
                            sum(1 for x in exc if x["code"] == "element_dropped")
                            if any(x["code"] == "element_dropped" for x in exc)
                            else "no element was dropped for missing evidence",
                            "numbers drawn %s; untraced %s" %
                            (cmap["numbers"]["drawn"], cmap["numbers"]["untraced"])],
            "pending_human": ([x["detail"] for x in exc if x["code"] == "element_dropped"] +
                              (["an earlier figure was present: rebuild vs edit needs confirmation"]
                               if spec.get("source_artifact") and
                               erec["mode"] != "source_preserving_patch" else [])),
        }
        if not index.get("paragraphs"):
            status = "input_error" if index.get("input_error") else "insufficient_evidence"
            payload["uncertainty"].append("no parseable material under /input; nothing was asserted")
    except Exception as crash:
        errs.append("build crashed: %s" % str(crash).splitlines()[0][:200])
        degr.append(traceback.format_exc()[-900:])
        status, payload = "partial", {"sources": []}
        try:                                   # last resort: an empty but legal page
            model = layout.compose({"title": "Graphical abstract", "panels": []}, index.get("spec") or {})
            s, p = out / "graphical_abstract.svg", out / "graphical_abstract.pdf"
            s.write_text(emit.to_svg(model), encoding="utf-8")
            p.write_bytes(emit.to_pdf(model))
            files = {"svg": str(s), "pdf": str(p)}
            payload.update({"editable_source": {"path": "graphical_abstract.svg", "format": "svg",
                                                "editable": True, "layers": layout.LAYERS,
                                                "text_count": model["stats"]["text_ops"],
                                                "sha256": core.sha256_file(s, 0)},
                            "export_artifact": {"pdf": {"path": "graphical_abstract.pdf", "pages": 1,
                                                        "vector": True}}})
        except Exception:
            pass
    res = write_result(out, index, index.get("contract") or {}, payload, status, errs, degr, exc,
                       [{"what": "build", "detail": "figure + exports + evidence map + checks"},
                        {"what": "exports", "detail": ", ".join(os.path.basename(v)
                                                                for v in files.values()) or "none"}], t0)
    cm = res.get("content_map") or {}
    print("[build] status=%s elements=%s panels=%s files={%s}" %
          (status, len(cm.get("elements") or []), len(cm.get("panels") or []),
           ", ".join("%s:%sB" % (k, content.size_of(v)) for k, v in files.items())))
    print("[build] contract: %s key(s), filled %s; result.json written" %
          (res["runtime"]["contract_keys_total"], res["runtime"]["contract_keys_filled"]))
    for line in (errs + degr)[:10]:
        print("  note:", line[:180])
    print("[build] next: python3 %s selfcheck" % Path(__file__).as_posix())
    return 0

def cmd_selfcheck(a):
    out = Path(a.output)
    index = {}
    if (Path(a.work) / "index.json").is_file():
        try:
            index = core.read_json(Path(a.work) / "index.json")
        except Exception:
            index = {}
    rep = core.selfcheck(str(out), index) if core else {"pass": False, "checks": []}
    core.dump(out / "selfcheck.json", rep)
    bad = [c for c in rep.get("checks") or [] if not c["ok"]]
    print("[selfcheck] %s (%d checks, %d failing)" %
          ("PASS" if rep.get("pass") else "ATTENTION", len(rep.get("checks") or []), len(bad)))
    for c in rep.get("checks") or []:
        print("  %-4s %-22s %s" % ("ok" if c["ok"] else "FAIL", c["id"], str(c["detail"])[:120]))
    return 0

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    for k in ("input", "work", "output"):
        common.add_argument("--" + k, default=None)
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="graphical abstract workbench: init / show / check / build / selfcheck")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("init", parents=[common], help="index /input and write a partial result.json")
    sh = sub.add_parser("show", parents=[common], help="print indexed passages with locators")
    sh.add_argument("--sid", default="")
    sh.add_argument("--grep", default="")
    sh.add_argument("--limit", default=40)
    sh.add_argument("--chars", default=700)
    sh.add_argument("--tables", action="store_true")
    sh.add_argument("--workorder", action="store_true")
    sh.add_argument("--contract", action="store_true")
    sub.add_parser("check", parents=[common], help="audit work/draft.json")
    sub.add_parser("build", parents=[common], help="render exports and finalise result.json")
    sub.add_parser("selfcheck", parents=[common], help="audit the delivered files")
    a = ap.parse_args(argv)
    a.input = a.input or DEFAULT_INPUT
    a.work = a.work or DEFAULT_WORK
    a.output = a.output or DEFAULT_OUTPUT
    cmd = a.cmd or "init"
    if LIB_ERR:
        print("[%s] helper modules failed to import: %s" % (cmd, LIB_ERR))
    fn = {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
          "selfcheck": cmd_selfcheck}.get(cmd)
    try:
        return fn(a) if fn else 0
    except SystemExit:
        return 0
    except Exception:
        tb = traceback.format_exc()
        try:
            Path(a.output).mkdir(parents=True, exist_ok=True)
            idx = (core.read_json(Path(a.work) / "index.json")
                   if (Path(a.work) / "index.json").is_file() else {})
            write_result(a.output, idx, (idx or {}).get("contract") or {}, {"sources": []}, "partial",
                         ["%s crashed: %s" % (cmd, tb.splitlines()[-1][:200])], [tb[-800:]], [], [],
                         time.time())
        except Exception:
            pass
        print("[%s] failed, result.json finalised:\n%s" % (cmd, tb[-1200:]))
        return 0

if __name__ == "__main__":
    sys.exit(main())
