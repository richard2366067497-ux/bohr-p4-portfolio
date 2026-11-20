#!/usr/bin/env python3
"""mechanism-figure-ledger — Agent-led, verifiable biological mechanism figure builder.

  init       index /input materials + workorder, write a legal partial result.json
  show       print source blocks with locators and the workorder object table
  check      verify draft.json: quotes, ids, workorder coverage, legend, numeric provenance
  build      layout + render SVG/PNG/PDF + content_map + compliance + final result.json
  selfcheck  re-read artifacts from disk and re-assert the 12 gates

The Agent reads the material and writes /app/work/draft.json. These commands index,
verify, lay out, render and audit; they never replace the reading step. Standard
library only, offline, CWD-independent, always exit 0, always leave a legal result.json.
"""
import argparse
import re
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
try:
    import ledger as LD
    import sources as SC
    import render as RD
    import export as EX
except Exception:                                     # pragma: no cover
    LD = SC = RD = EX = None

VERSION = "1.0.0"
SKILL_NAME = "mechanism-figure-ledger"
CANVAS = {"w": 1600, "h": 1000}
DEFAULT_INPUT, DEFAULT_WORK, DEFAULT_OUTPUT = "/input", "/app/work", "/app/output"

CANON = {"caseid": "case_id", "status": "status", "editablesource": "editable_source",
         "exportartifact": "export_artifact", "contentmap": "content_map",
         "compliancechecks": "compliance_checks", "exceptions": "exceptions",
         "sources": "sources", "uncertainty": "uncertainty", "changes": "changes"}


def say(msg=""):
    print(msg, flush=True)


def finalise(out, case, status, values, declared=None):
    """Fill every declared contract field verbatim; unknown extras -> null + degradation."""
    names = list(declared if declared is not None else LD.cnames(case))
    res, missing = {}, []
    for name in names:
        v = values.get(CANON.get(LD.key(name), LD.key(name)))
        if v is None:
            v = values.get(name)
        res[name] = v
        if v is None:
            missing.append(name)
    for k, v in values.items():
        res.setdefault(k, v)
    res["case_id"] = values.get("case_id") or LD.cid_of(case)
    res["status"] = status
    for k in ("sources", "uncertainty", "pending_human", "errors", "degradations", "changes"):
        if not isinstance(res.get(k), list):
            res[k] = []
    if missing:
        res["degradations"] = list(res["degradations"]) + [
            "contract field(s) with no producer: %s" % ", ".join(missing)]
    res.setdefault("runtime", {})
    res["skill"] = {"name": SKILL_NAME, "version": VERSION}
    res["contract_fields"] = {"declared": names,
                              "filled": [n for n in names if res.get(n) is not None],
                              "null_fields": [n for n in names if res.get(n) is None]}
    LD.jwrite(Path(out) / "result.json", res)
    return res


def empty_values(mats):
    return {"case_id": None, "editable_source": None, "export_artifact": None,
            "content_map": {"entities": [], "relations": [], "compartments": [],
                            "legend_encodings": [], "pending": [], "coverage": {}},
            "compliance_checks": {"pass": False, "failures": ["not rendered yet"]},
            "exceptions": [], "sources": [m["rel"] for m in mats],
            "uncertainty": [], "pending_human": [], "degradations": [], "changes": [],
            "errors": []}


def read_inputs(inp):
    mats, corp, err = SC.collect(inp)
    case = SC.get_case(inp) or SC.salvage_case(inp)
    wo = LD.workorder(case)
    corp = corp + SC.declared_corpus(wo)
    return mats, corp, case, wo, err


# --------------------------------------------------------------------- init
def do_init(inp, work, out):
    mats, corp, case, wo, err = read_inputs(inp)
    names = LD.cnames(case)
    LD.jwrite(Path(work) / "index.json",
              {"generated": LD.now(), "input": str(inp), "case_id": LD.cid_of(case),
               "contract": names, "materials": mats, "blocks": len(corp),
               "workorder": SC.objtable(wo), "errors": [err] if err else []})
    vals = empty_values(mats)
    vals["case_id"] = LD.cid_of(case)
    vals["degradations"] = ["partial result.json written by init; run build after writing draft.json"]
    if err:
        vals["errors"] = [err]
    if case is None:
        vals["degradations"].append("case.json missing or unparsable")
    status = "input_error" if (err or case is None) else "partial"
    res = finalise(out, case, status, vals)

    say("init  → materials %d | blocks %d | contract %d field(s)" % (len(mats), len(corp), len(names)))
    for m in mats:
        say("      - %-30s %-7s %7dB blocks=%d%s" % (m["rel"][:30], m["kind"], m["bytes"], m["blocks"],
                                                     ("  NOTE: " + m["note"]) if m["note"] else ""))
    say("      contract: %s" % (", ".join(names) if names else "(none found)"))
    say("      partial result.json → %s | case_id=%s | status=%s"
        % (Path(out) / "result.json", res.get("case_id"), res["status"]))
    if err:
        say("      WARNING: %s" % err)
    say("      next: run `show` to read the material, then write %s" % (Path(work) / "draft.json"))
    return 0


# --------------------------------------------------------------------- show
def do_show(inp, work, doc=None, locator=None, limit=2600):
    mats, corp, case, wo, err = read_inputs(inp)
    if not corp:
        say("show  → no readable material under %s%s" % (inp, ("  (%s)" % err) if err else ""))
        say("        Write draft.json from the workorder table below, or record gaps in pending_human.")
    shown = 0
    for b in corp:
        if b.get("declared") or b["material"] == "case.json":
            continue                      # case.json is summarised by the workorder table below
        if doc and doc.lower() not in b["locator"].lower() and doc.lower() not in b["material"].lower():
            continue
        if locator and locator.lower() not in b["locator"].lower():
            continue
        txt = b["text"]
        cut = "" if len(txt) <= limit else "\n …[truncated %d chars]" % (len(txt) - limit)
        say("\n--- %s ---\n%s%s" % (b["locator"], txt[:limit], cut))
        shown += 1
    say("\n[show] %d block(s) printed / %d indexed" % (shown, len(corp)))
    t = SC.objtable(wo)
    if any(t.values()):
        say("\n[workorder] declared objects (quote them with locator case.json#workorder...):")
        for i, e in enumerate(t["entities"]):
            say("  E%-2d %-24s type=%-11s compartment=%-13s %s"
                % (i + 1, e["name"][:24], e["type"] or "-", e["compartment"] or "-", e["locator"]))
        for i, r in enumerate(t["relations"]):
            say("  R%-2d %-16s -> %-16s type=%-11s %s"
                % (i + 1, r["from"][:16], r["to"][:16], r["type"] or "-", r["locator"]))
        for c in t["compartments"]:
            say("  C    %s" % c["name"])
        for l in t["legend"]:
            say("  L    channel=%s meaning=%s" % (l.get("channel"), l.get("meaning")))
    names = LD.cnames(case)
    say("\n[contract] %s" % (", ".join(names) if names else "(none declared)"))
    say("[next] write %s with entities/relations/legend/data_values (references/), then check → build."
        % (Path(work) / "draft.json"))
    say("       Do not skip the reading step: build alone cannot judge biology.")
    return 0


# -------------------------------------------------------------------- check
def do_check(inp, work, out):
    mats, corp, case, wo, err = read_inputs(inp)
    declarations = LD.cnames(case)
    draft, dpath, derr = LD.load_draft(work, out)
    if draft is None:
        LD.jwrite(Path(work) / "check_report.json",
                  {"generated": LD.now(), "declared_contract": declarations,
                   "issues": [derr or "draft.json not found"], "clean": False})
        say("check → NOT CLEAN: %s" % (derr or "draft.json not found"))
        say("        expected %s with entities[] and relations[]" % (Path(work) / "draft.json"))
        say("        build would fall back to a workorder-only degraded figure (status=partial).")
        return 0
    report, lines = LD.audit(draft, corp, wo, declarations)
    LD.jwrite(Path(work) / "check_report.json", report)
    say("check → %s" % lines[0])
    for ln in lines[1:]:
        say("        %s" % ln)
    say("        %s" % ("CLEAN — build will draw every item" if report.get("clean") else
                       "NOT CLEAN — unverified items are not drawn (moved to pending / pending_human)"))
    say("        next: build")
    return 0


# -------------------------------------------------------------------- build
def do_build(inp, work, out):
    t0 = time.time()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    mats, corp, case, wo, err = read_inputs(inp)
    names = LD.cnames(case)

    vals = empty_values(mats)                       # 1) legal partial before any render
    vals["case_id"] = LD.cid_of(case)
    vals["degradations"] = ["partial result.json written before render"]
    if err:
        vals["errors"] = [err]
    finalise(out, case, "input_error" if (err or case is None) else "partial", vals)

    errors = list(vals["errors"])
    draft, dpath, derr = LD.load_draft(work, out)
    if draft is None:
        draft, source_kind = SC.fallback_draft(wo, corp), "fallback"
    else:
        source_kind = "draft"

    model, pending, degradations, uncertainty, cov, byname = LD.prepare(draft, corp, wo)
    if source_kind == "fallback":
        degradations.insert(0, derr or "draft.json not found; degraded from workorder/material")
    model["notes"] = ["Every node/edge carries a locator and a verbatim quote in content_map.json.",
                      "All text is <text>; relabelling needs no re-layout."]

    svg_text, png_bytes, pdf_bytes = "", b"", b""
    try:
        model = RD.layout(model)
        svg_text = RD.svg(model)
    except Exception as exc:
        errors.append("layout/svg failed: %s: %s" % (type(exc).__name__, exc))
        model = RD.layout({"title": "Mechanism figure (render fallback)", "subtitle": "",
                           "canvas": CANVAS, "compartments": [], "entities": [],
                           "relations": [], "legend": [], "legend_rows": [], "dl": []})
        svg_text = RD.svg(model)
    (out / "figure.svg").write_text(svg_text, encoding="utf-8")

    try:
        png_bytes = EX.png(model)
        (out / "figure.png").write_bytes(png_bytes)
    except Exception as exc:
        errors.append("png export failed: %s: %s" % (type(exc).__name__, exc))
    try:
        pdf_bytes = EX.pdf(model)
        (out / "figure.pdf").write_bytes(pdf_bytes)
    except Exception as exc:
        errors.append("pdf export failed: %s: %s" % (type(exc).__name__, exc))

    try:
        checks = RD.probe(model, svg_text)
    except Exception as exc:
        checks = {"pass": False, "failures": ["probe failed: %s: %s" % (type(exc).__name__, exc)]}
    checks["png"] = EX.png_probe(png_bytes) if png_bytes else {"ok": False, "error": "not produced"}
    checks["pdf"] = EX.pdf_probe(pdf_bytes) if pdf_bytes else {"ok": False, "error": "not produced"}
    fails = list(checks.get("failures", []))
    fails += ([] if checks["png"].get("ok") else ["png not verifiable"])
    fails += ([] if checks["pdf"].get("ok") else ["pdf not verifiable"])
    checks["failures"] = fails
    checks["pass"] = not fails

    cmap = LD.build_content_map(model, cov, pending)
    LD.jwrite(out / "content_map.json", cmap)
    LD.jwrite(out / "compliance_checks.json", checks)
    LD.jwrite(out / "figure_model.json", {
        "title": model.get("title"), "subtitle": model.get("subtitle"), "canvas": CANVAS,
        "compartments": model.get("compartments", []),
        "entities": [{k: e.get(k) for k in ("id", "name", "type", "species", "compartment",
                                            "box", "italic", "sublabel", "status", "locator")}
                     for e in model["entities"]],
        "relations": [{k: r.get(k) for k in ("id", "from", "to", "type", "direction", "strength",
                                             "path", "label", "badge", "status", "locator")}
                      for r in model["relations"]],
        "legend_rows": model.get("legend_rows", []),
        "legend_used": ["%s:%s" % k for k in (model.get("legend_used") or [])],
        "legend_declared": ["%s:%s" % k for k in (model.get("legend_declared") or [])],
        "legend_h": model.get("legend_h", 76),
        "source_material": [m["rel"] for m in mats]})

    status = "ok"
    if (pending or degradations or errors or not checks["pass"] or source_kind == "fallback"
            or case is None or err):
        status = "input_error" if (case is None or err) else "partial"

    exceptions = []
    for p in pending:
        exceptions.append({"kind": "pending:%s" % p["kind"], "detail": p.get("reason", ""),
                           "impact": "item not drawn", "action": "confirm source or drop"})
    for d in degradations:
        exceptions.append({"kind": "degradation", "detail": d, "impact": "reduced coverage",
                           "action": "supply the missing input or draft field"})
    for u in uncertainty:
        exceptions.append({"kind": "uncertainty", "detail": u, "impact": "undirected edge",
                           "action": "confirm direction with a domain expert"})
    for e in errors:
        exceptions.append({"kind": "error", "detail": e, "impact": "partial artifact",
                           "action": "inspect run.log, rerun build"})

    vals = {
        "case_id": LD.cid_of(case),
        "editable_source": {"path": str(out / "figure.svg"), "format": "svg", "editable": True,
                            "layers": RD.LAYER_IDS, "text_count": svg_text.count("<text"),
                            "bytes": len(svg_text.encode("utf-8")),
                            "sha256": LD.sha256(out / "figure.svg")},
        "export_artifact": {
            "png": {"path": str(out / "figure.png"), "width": CANVAS["w"], "height": CANVAS["h"],
                    "dpi": 96, "engine": "stdlib-zlib-raster", "bytes": len(png_bytes),
                    "non_uniform": checks["png"].get("unique_colors", 0) > 2},
            "pdf": {"path": str(out / "figure.pdf"), "pages": checks["pdf"].get("pages", 0),
                    "vector": bool(checks["pdf"].get("ok")), "engine": "stdlib-pdf-base14",
                    "header": checks["pdf"].get("header", ""), "eof": checks["pdf"].get("eof", False),
                    "bytes": len(pdf_bytes)}},
        "content_map": cmap, "compliance_checks": checks, "exceptions": exceptions,
        "sources": [{"material": m["rel"], "kind": m["kind"], "bytes": m["bytes"],
                     "blocks": m["blocks"], "note": m["note"]} for m in mats],
        "uncertainty": uncertainty + list(model.get("gaps", []) or []),
        "pending_human": [{"what": p.get("name") or p.get("id") or p.get("kind"),
                           "why": p.get("reason", "")} for p in pending],
        "degradations": degradations + ([] if dpath is None else ["draft: %s" % dpath]),
        "changes": model.get("edits", []),
        "errors": errors,
        "runtime": {"stage": "build", "seconds": round(time.time() - t0, 2), "draft": dpath,
                    "source_kind": source_kind, "version": VERSION},
    }
    res = finalise(out, case, status, vals)
    (out / "run.log").write_text(
        "\n".join([LD.now() + "  build  status=" + status,
                   "  materials=%d entities=%d relations=%d pending=%d errors=%d"
                   % (len(mats), len(model["entities"]), len(model["relations"]), len(pending), len(errors)),
                   "  contract=%s" % ", ".join(names)]) + "\n", encoding="utf-8")

    say("build → status=%s | source=%s | entities %d | relations %d | pending %d"
        % (status, source_kind, len(model["entities"]), len(model["relations"]), len(pending)))
    say("        figure.svg %.1fKB | figure.png %.1fKB | figure.pdf %.1fKB"
        % (len(svg_text) / 1024.0, len(png_bytes) / 1024.0, len(pdf_bytes) / 1024.0))
    say("        contract %d/%d field(s) filled | checks pass=%s"
        % (len(res["contract_fields"]["filled"]), len(res["contract_fields"]["declared"]),
           checks.get("pass")))
    for f in fails[:4]:
        say("        FAIL %s" % f)
    say("        result.json → %s" % (out / "result.json"))
    return 0


# ---------------------------------------------------------------- selfcheck
def do_selfcheck(inp, work, out):
    out, work = Path(out), Path(work)
    res = LD.jread(out / "result.json") or {}
    model = LD.jread(out / "figure_model.json")
    svgp, pngp, pdfp = out / "figure.svg", out / "figure.png", out / "figure.pdf"
    svg_text = svgp.read_text(encoding="utf-8") if svgp.is_file() else ""
    if not (model and svg_text):
        say("selfcheck → SKIP: missing figure_model.json or figure.svg (run build first)")
        LD.jwrite(work / "selfcheck.json", {"generated": LD.now(), "gates": {}, "failed": ["no artifacts"]})
        return 0
    checks = RD.probe(model, svg_text)
    checks["png"] = EX.png_probe(pngp.read_bytes()) if pngp.is_file() else {"ok": False}
    checks["pdf"] = EX.pdf_probe(pdfp.read_bytes()) if pdfp.is_file() else {"ok": False}
    cmap = LD.jread(out / "content_map.json") or {}
    ids = re.findall(r'id="(ent-[^"]+|rel-[^"]+)"', svg_text)
    gates = {
        "svg_xml": bool(checks.get("svg_xml")),
        "canvas": checks.get("canvas", {}).get("ok", False),
        "markers": checks.get("markers", {}).get("distinct", False),
        "gene_italics": bool(checks.get("gene_italics")),
        "compartment_containment": checks.get("compartment_containment", {}).get("ok", True)
        and not checks.get("compartment_containment", {}).get("failures"),
        "cross_lane_edges": checks.get("cross_lane_edges", {}).get("ok", True),
        "legend_consistency": checks.get("legend_consistency", {}).get("ok", True),
        "content_map_1to1": len(set(ids)) == len(cmap.get("entities", [])) + len(cmap.get("relations", [])),
        "evidence": not (cmap.get("pending")),
        "png": checks["png"].get("ok", False),
        "pdf": checks["pdf"].get("ok", False),
        "contract": not (res.get("contract_fields", {}).get("null_fields")),
    }
    LD.jwrite(work / "selfcheck.json",
              {"generated": LD.now(), "gates": gates, "failed": [k for k, v in gates.items() if not v],
               "counts": {"entities": len(cmap.get("entities", [])),
                          "relations": len(cmap.get("relations", [])),
                          "svg_text_nodes": svg_text.count("<text")}})
    say("selfcheck → %d/%d gates pass" % (sum(1 for v in gates.values() if v), len(gates)))
    for k, v in gates.items():
        say("        %-24s %s" % (k, "PASS" if v else "FAIL"))
    say("        report → %s" % (work / "selfcheck.json"))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="main.py", description="mechanism-figure-ledger: verifiable mechanism/pathway figure builder")
    ap.add_argument("command", choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--work", default=DEFAULT_WORK)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--doc", default=None, help="show: filter by material name substring")
    ap.add_argument("--locator", default=None, help="show: filter by locator substring")
    ap.add_argument("--limit", type=int, default=2600, help="show: chars per block")
    ap.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    inp, work, out = Path(args.input), Path(args.work), Path(args.output)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    try:
        if LD is None or SC is None:
            say("ERROR: skill modules missing next to main.py")
            return 0
        if args.command == "init":
            return do_init(inp, work, out)
        if args.command == "show":
            return do_show(inp, work, args.doc, args.locator, args.limit)
        if args.command == "check":
            return do_check(inp, work, out)
        if args.command == "build":
            return do_build(inp, work, out)
        return do_selfcheck(inp, work, out)
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc(limit=4)
        try:
            case = SC.get_case(inp) or SC.salvage_case(inp)
            mats, _, _ = SC.collect(inp)
            vals = empty_values(mats)
            vals["case_id"] = LD.cid_of(case)
            vals["errors"] = [tb.strip().splitlines()[-1]]
            vals["degradations"] = ["unhandled exception in %s; partial result emitted" % args.command]
            finalise(out, case, "input_error", vals)
        except Exception:
            pass
        say("ERROR (captured, exit 0): %s" % tb.strip().splitlines()[-1])
        return 0


if __name__ == "__main__":
    sys.exit(main())
