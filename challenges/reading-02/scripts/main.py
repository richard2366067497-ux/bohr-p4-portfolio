#!/usr/bin/env python3
"""scientific figure/table reader -- reading-02 v6 (entry point).

One deterministic pass discovers the supplied materials, decodes each figure with a
stdlib PNG reader, calibrates the axes from the tick geometry, colour-traces every
configured series, lifts the tables and every claim with verbatim evidence, then
writes the structured reading plus the contract-backfilled result.json.

    build      full flow (discover -> decode -> calibrate -> digitize -> claims -> result.json)
    show       print the figure/table/claim inventory with source anchors
    check      rerun the full flow and merge the agent draft with evidence checks
    selfcheck  rerun the full flow and audit the output_contract shape

Every subcommand rewrites a complete /app/output/result.json and exits 0 on all
paths (empty, unreadable or malformed input included). Standard library only;
offline; paths resolved from __file__, never from the current directory.
"""
import argparse
import os
import re
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from figurekit import (GEN, VERSION, build_figures, build_tables, contract_keys, denull, discover,
                       figure_digest, finalize, find_quote, jread, jwrite, load_json_materials, norm,
                       pick_material, pick_readings, read_text, table_digest, twrite, write_artifacts)


def paths(a):
    return Path(a.input or "/input"), Path(a.output or "/app/output"), Path(a.work or "/app/work")


# ---------------------------------------------------------------- claim layer
def normalize_claim(c):
    ev = c.get("evidence") if isinstance(c.get("evidence"), dict) else {}
    loc = ev.get("location") if isinstance(ev.get("location"), dict) else {}
    return {"claim_id": str(c.get("claim_id") or ""), "kind": str(c.get("kind") or "claim"),
            "text": norm(c.get("text") or ""), "readability": str(c.get("readability") or "directly_read"),
            "conditions": norm(c.get("conditions") or ""),
            "evidence": {"quote": norm(ev.get("quote") or ""), "quote_type": str(ev.get("quote_type") or "text"),
                         "source_id": str(ev.get("source_id") or ""), "location": denull(loc),
                         "read_basis": norm(ev.get("read_basis") or "")}}


def _id(claims, prefix):
    return "%s%02d" % (prefix, len(claims) + 1)


def _series_rgb(fig, name):
    return next((s["rgb"] for s in fig["series"] if s["name"] == name), [])


def build_claims(readings, figures, tables):
    claims = [normalize_claim(c) for c in (readings.get("claims") or []) if isinstance(c, dict)]
    for fig in figures:
        ax, ay = fig["axes"].get("x", {}), fig["axes"].get("y", {})
        quote = "x: %s-%s %s, y: %s-%s %s" % (ax.get("tick_labels", [""])[0] if ax.get("tick_labels") else "",
                                              ax.get("tick_labels", [""])[-1] if ax.get("tick_labels") else "", ax.get("unit", ""),
                                              ay.get("tick_labels", [""])[0] if ay.get("tick_labels") else "",
                                              ay.get("tick_labels", [""])[-1] if ay.get("tick_labels") else "", ay.get("unit", ""))
        claims.append({"claim_id": _id(claims, "fig"), "kind": "element",
                       "text": "%s panel %s reads %s on x and %s on y." % (fig["figure_id"], fig["panel"] or "-",
                                                                           ax.get("label", ""), ay.get("label", "")),
                       "readability": "directly_read", "conditions": "panel %s" % (fig["panel"] or "-"),
                       "evidence": {"quote": quote, "quote_type": "visual", "source_id": fig["image"].get("file", ""),
                                    "location": {"figure": fig["figure_id"], "panel": fig["panel"],
                                                 "axis_basis": "tick labels"},
                                    "read_basis": "axis tick labels"}})
        for s in fig.get("digitized", []):
            if s["status"] == "digitized" and s["n_points"]:
                pts = s["points"]
                claims.append({"claim_id": _id(claims, "ser"), "kind": "digitized_series",
                               "text": "Series %s in %s digitized to %d point(s), spanning x %s..%s and y %s..%s."
                                       % (s["name"], fig["figure_id"], s["n_points"], pts[0]["x"], pts[-1]["x"],
                                          min(p["y"] for p in pts), max(p["y"] for p in pts)),
                               "readability": "digitized", "conditions": "colour tolerance %d" % s.get("tol", 60),
                               "evidence": {"quote": "rgb %s" % (_series_rgb(fig, s["name"]) or ""),
                                            "quote_type": "visual", "source_id": fig["image"].get("file", ""),
                                            "location": {"figure": fig["figure_id"], "panel": fig["panel"],
                                                         "series": s["name"]},
                                            "read_basis": "colour-cluster trace"}})
    for t in tables:
        if t["caption"]:
            claims.append({"claim_id": _id(claims, "tab"), "kind": "table",
                           "text": "%s reports %d row(s) x %d column(s): %s." % (t["table_id"], t["n_rows"], t["n_cols"],
                                                                                 ", ".join(t["columns"])),
                           "readability": "directly_read", "conditions": t["source"],
                           "evidence": {"quote": t["caption"], "quote_type": "text", "source_id": t["source"],
                                        "location": {"table_id": t["table_id"]},
                                        "read_basis": "literal table caption"}})
        for r_i, row in enumerate(t["rows"]):
            for c_i, val in enumerate(row):
                if c_i == 0 or not re.match(r"^[-+]?\d+(?:\.\d+)?$", val.strip()):
                    continue
                col = t["columns"][c_i]
                claims.append({"claim_id": _id(claims, "cell"), "kind": "table_cell",
                               "text": "%s[%s] %s = %s %s." % (t["table_id"], row[0], col, val, t["column_units"][c_i]),
                               "readability": "directly_read", "conditions": "%s / %s" % (t["source"], row[0]),
                               "evidence": {"quote": "%s %s = %s" % (row[0], col, val), "quote_type": "json",
                                            "source_id": t["source"],
                                            "location": {"table_id": t["table_id"], "row": r_i, "column": c_i},
                                            "read_basis": "literal table cell"}})
    return claims


def validate_claims(claims, text_corpus, figure_ids, table_ids, errors):
    ids = {str(t).lower() for t in figure_ids} | {Path(str(t)).stem.lower() for t in figure_ids}
    for c in claims:
        ev, q = c["evidence"], c["evidence"]["quote"]
        if not q:
            errors.append({"code": "claim_without_quote", "where": c["claim_id"], "detail": "empty quote"})
            continue
        if ev["quote_type"] == "visual":
            src = Path(ev["source_id"]).stem.lower() if ev["source_id"] else ""
            if ids and src and src not in ids and not any(src in t or t in src for t in ids):
                errors.append({"code": "visual_source_unknown", "where": c["claim_id"],
                               "detail": "figure %s not in the reading set" % ev["source_id"]})
            continue
        if ev["quote_type"] == "json":
            loc = ev.get("location") or {}
            tid = str(loc.get("table_id") or "") if isinstance(loc, dict) else ""
            if tid and tid not in table_ids:
                errors.append({"code": "table_unknown", "where": c["claim_id"],
                               "detail": "table %s not in the reading set" % tid})
            continue
        if not any(find_quote(t, q)["found"] for t in text_corpus.values()):
            errors.append({"code": "quote_not_found", "where": c["claim_id"], "detail": "quote not in any material"})
    return errors


def merge_draft(draft, claims, text_corpus, degradations):
    """Agent claims replace the deterministic ones covering the same claim_id when they validate."""
    incoming = draft.get("claims") if isinstance(draft, dict) else None
    if not isinstance(incoming, list):
        return claims, 0
    ok, rejected = [], 0
    for c in [normalize_claim(x) for x in incoming if isinstance(x, dict)]:
        q = c["evidence"]["quote"]
        if q and (c["evidence"]["quote_type"] == "visual" or any(find_quote(t, q)["found"] for t in text_corpus.values())):
            ok.append(c)
        else:
            rejected += 1
    if rejected:
        degradations.append("%d agent claim(s) dropped: quote not found in any material" % rejected)
    if not ok:
        return claims, 0
    replaced = {c["claim_id"] for c in ok if c["claim_id"]}
    merged = [c for c in claims if not (c["claim_id"] and c["claim_id"] in replaced)] if replaced else list(claims)
    return ok + [c for c in merged if c not in ok], len(ok)


def digest_md(ctx):
    d = ctx["digest"]
    lines = ["# Figure & table digest", "",
             "> case `%s` | status **%s** | %s" % (ctx["case_id"], ctx["status"], GEN), "", "## Figures", ""]
    for f in d.get("figures", []):
        lines.append("- **%s%s** %sx%s px | x %s | y %s" % (
            f["figure_id"], (" panel " + f["panel"]) if f["panel"] else "", f["image"].get("width", ""),
            f["image"].get("height", ""), f["x"], f["y"]))
        lines.append("  caption: " + (f["caption"] or "-"))
        for s in f.get("series", []):
            lines.append("    - %s -> %s, %d point(s)" % (s["name"], s["status"], s["n_points"]))
    lines += ["", "## Tables", ""]
    for t in d.get("tables", []):
        lines.append("- **%s** %d x %d | %s | units: %s" % (t["table_id"], t["n_rows"], t["n_cols"], t["caption"],
                                                            ", ".join(u or "-" for u in t["column_units"])))
        lines.append("  columns: " + ", ".join(t["columns"]))
    lines += ["", "## Counts", "", "- figures %s; tables %s; claims %s; errors %s" % (
        ctx["counts"]["figures"], ctx["counts"]["tables"], ctx["counts"]["claims"], ctx["counts"]["errors"]), ""]
    return "\n".join(lines)


def run_pipeline(a):
    t0 = time.time()
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    errors, degradations, changes, pending = [], [], [], []
    case, case_path = {}, None
    for cand in sorted(inp.rglob("case.json")) if inp.exists() else []:
        try:
            case, case_path = jread(cand), cand
            break
        except Exception as e:
            errors.append({"code": "case_unreadable", "detail": "%s: %r" % (cand.name, e)})
    cid = str(case.get("case_id") or case.get("id") or (case_path.parent.name if case_path else "unknown"))
    jwrite(out / "result.json", {"case_id": cid, "status": "partial", "result": {}, "claims": [],
                                 "uncertainties": [{"item": "run in progress"}],
                                 "figure_tables_digest": {"note": "legal first-pass result"},
                                 "runtime": {"skill": GEN, "version": VERSION}})
    files, dupes, notes = discover(inp)
    degradations += notes
    if dupes:
        changes.append({"step": "dedupe", "note": "; ".join(dupes)})
    docs = load_json_materials(files, errors)
    rname, readings = pick_readings(docs)
    mname, material = pick_material(docs)
    text_corpus = {d["path"].name: d["text"] for d in docs.values()}
    text_corpus.update({p.name: read_text(p) for p in files if p.suffix.lower() in (".txt", ".md", ".markdown")})
    figures = build_figures(readings, files, degradations)
    tables = build_tables(material, mname, degradations)
    claims = build_claims(readings, figures, tables)
    if not rname and figures:
        changes.append({"step": "readings", "note": "no readings config found; figures decoded from image files only"})
    if not mname:
        changes.append({"step": "material", "note": "no material document found; tables and paragraph quotes are absent"})
    draft = {}
    if (work / "draft.json").exists():
        try:
            draft = jread(work / "draft.json")
            if not isinstance(draft, dict):
                draft = {}
                degradations.append("draft.json was not a JSON object; ignored")
        except Exception as e:
            degradations.append("draft.json unreadable (%s); deterministic reading used" % type(e).__name__)
    claims, n_agent = merge_draft(draft, claims, text_corpus, degradations)
    if n_agent:
        changes.append({"step": "draft", "note": "merged %d checked agent claim(s)" % n_agent})
    else:
        pending.append("review the digitized traces and claims, then restate them in work/draft.json")
    figure_ids = [f["image"].get("file", "") for f in figures if f.get("image")] + \
                 [f["figure_id"] for f in figures]
    table_ids = [t["table_id"] for t in tables]
    validate_claims(claims, text_corpus, figure_ids, table_ids, errors)
    digitization = []
    for f in figures:
        for s in f.get("digitized", []):
            digitization.append({"figure_id": f["figure_id"], "panel": f["panel"], "series": s["name"],
                                 "status": s["status"], "n_points": s.get("n_points", 0), "tol": s.get("tol", 60)})
    digest = {"figure_count": len(figures), "table_count": len(tables), "claim_count": len(claims),
              "figures": [figure_digest(f) for f in figures],
              "tables": [table_digest(t) for t in tables],
              "digitized_points": sum(d["n_points"] for d in digitization),
              "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    elements = {f["figure_id"]: f.get("elements", {}) for f in figures}
    uncertainties = [{"kind": "counts", "detail": {"figures": len(figures), "tables": len(tables),
                                                   "claims": len(claims), "errors": len(errors)}},
                     {"kind": "scope", "detail": "only the supplied materials are read; absent panels and "
                                                 "tables are declared gaps, never invented"}]
    for u in (readings.get("uncertainties") or []):
        uncertainties.append(u if isinstance(u, dict) else {"kind": "note", "detail": str(u)})
    pending += [str(x) for x in (readings.get("pending_human") or [])]
    counts = {"figures": len(figures), "tables": len(tables), "claims": len(claims),
              "digitized_points": digest["digitized_points"], "errors": len(errors),
              "degradations": len(degradations)}
    if not files:
        status = "input_error"
        pending.append("no readable material was found under the input directory")
    elif not figures and not tables and not [c for c in claims if c["kind"] != "coverage"]:
        status = "insufficient_evidence"
    elif errors or degradations:
        status = "partial"
    else:
        status = "answered"
    if not figures and not tables:
        claims = claims or [{"claim_id": "c00", "kind": "coverage",
                             "text": "No figure or table could be read from the supplied materials.",
                             "readability": "insufficient", "conditions": "",
                             "evidence": {"quote": "materials supplied: " + ", ".join(p.name for p in files[:5]),
                                          "quote_type": "visual", "source_id": "", "location": {},
                                          "read_basis": "input inventory"}}]
    summary = ("Read %d figure(s), %d table(s) and %d claim(s): %d digitized point(s); %d error(s), "
               "%d degradation(s)." % (len(figures), len(tables), len(claims), digest["digitized_points"],
                                       len(errors), len(degradations)))
    result = {"paper_title": material.get("paper_title", "") if isinstance(material, dict) else "",
              "readings_source": rname, "material_source": mname, "figures": figures, "tables": tables,
              "digitization": digitization, "elements": elements,
              "materials": [{"file": p.name, "extension": p.suffix.lower(), "bytes": p.stat().st_size} for p in files]}
    ctx = {"case_id": cid, "status": status, "summary": summary, "result": result, "claims": claims,
           "sources": [{"file": p.name, "extension": p.suffix.lower(), "bytes": p.stat().st_size,
                        "role": "figure" if p.suffix.lower() == ".png" else "material"} for p in files],
           "uncertainties": uncertainties, "errors": errors, "degradations": degradations, "changes": changes,
           "pending_human": pending,
           "limits": [{"item": "digitization_is_best_effort",
                       "detail": "traces come from colour clustering; anti-aliased or overlapping strokes are "
                                 "reported in degradations rather than smoothed over"},
                      {"item": "no_pdf_or_docx_render",
                       "detail": "vector sources are not rendered; only supplied raster figures are traced"}],
           "counts": counts, "digest": digest, "artifacts": ["figure_structure.json", "digitized_series.csv",
                                                             "tables.json", "figure_tables_digest.md",
                                                             "result.json"],
           "runtime": {"skill": GEN, "version": VERSION, "seconds": round(time.time() - t0, 2),
                       "figures": len(figures), "tables": len(tables), "claims": len(claims),
                       "digitized_points": digest["digitized_points"]}}
    jwrite(work / "index.json", {"case_id": cid, "generated": digest["generated"], "readings_source": rname,
                                 "material_source": mname, "figures": digest["figures"],
                                 "tables": digest["tables"], "claims": claims})
    write_artifacts(out, ctx)
    twrite(out / "figure_tables_digest.md", digest_md(ctx))
    res = finalize(case, ctx)
    jwrite(out / "result.json", res)
    print("status=%s figures=%d tables=%d claims=%d points=%d errors=%d" % (
        status, len(figures), len(tables), len(claims), digest["digitized_points"], len(errors)))
    print("artifacts:", ", ".join(ctx["artifacts"]), "| contract:", ", ".join(contract_keys(case)))
    for e in errors[:6]:
        print("issue:", e["code"], "@", e.get("where", ""))
    return res


def cmd_show(a):
    _, _, work = paths(a)
    idx = {}
    if (work / "index.json").exists():
        try:
            idx = jread(work / "index.json")
        except Exception:
            idx = {}
    if not idx:
        print("(no index yet; run `main.py build` first)")
        return 0
    for f in idx.get("figures", []):
        print("%s panel %s | %s | series: %s" % (f["figure_id"], f.get("panel") or "-",
                                                 f.get("caption") or "-",
                                                 ", ".join("%s(%s,%s pts)" % (s["name"], s["status"], s.get("n_points", 0))
                                                           for s in f.get("series", []))))
    for t in idx.get("tables", []):
        print("%s | %d x %d | %s" % (t["table_id"], t["n_rows"], t["n_cols"], t["caption"] or "-"))
    for c in idx.get("claims", [])[:20]:
        print("[%s] %s :: %s" % (c["claim_id"], c["kind"], c["text"][:110]))
    print("-- %d figure(s), %d table(s), %d claim(s)" % (len(idx.get("figures", [])), len(idx.get("tables", [])),
                                                         len(idx.get("claims", []))))
    return 0


def cmd_check(a):
    res = run_pipeline(a)
    print("check: %s | errors=%d | claims=%d" % (res.get("status"), len(res.get("errors") or []),
                                                 len(res.get("claims") or [])))
    return 0


def cmd_selfcheck(a):
    res = run_pipeline(a)
    oc = res.get("output_contract") or {}
    missing = [k for k, v in oc.items() if v in (None, "", [], {})]
    print("selfcheck: keys=%d missing=%d empty=%d status=%s" % (len(oc), len(missing), len(missing), res.get("status")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="scientific figure/table reader (%s)" % GEN)
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (("build", "full reading flow"), ("show", "print the figure/table/claim inventory"),
                           ("check", "rerun and merge the agent draft"),
                           ("selfcheck", "rerun and audit the contract")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--input")
        sp.add_argument("--output", "--out", dest="output")
        sp.add_argument("--work")
        sp.add_argument("--readings")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if not getattr(a, "cmd", None):
        a.cmd = "build"
    for attr in ("input", "output", "work", "readings"):
        if not hasattr(a, attr):
            setattr(a, attr, None)
    try:
        {"build": run_pipeline, "check": cmd_check, "selfcheck": cmd_selfcheck, "show": cmd_show}[a.cmd](a)
    except Exception:
        try:
            _, out, _ = paths(a)
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", {"case_id": "unknown", "status": "input_error", "result": {}, "claims": [],
                                         "uncertainties": [{"kind": "fatal", "detail": "see errors"}],
                                         "figure_tables_digest": {"note": "fatal"},
                                         "errors": [{"code": "unhandled_exception",
                                                     "detail": traceback.format_exc(limit=2).replace("\n", " | ")[:700]}],
                                         "runtime": {"skill": GEN, "version": VERSION}})
        except Exception:
            pass
        print("ERROR handled; legal result.json written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
