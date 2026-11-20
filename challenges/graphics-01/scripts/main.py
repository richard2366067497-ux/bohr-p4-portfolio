#!/usr/bin/env python3
"""schematic-trace-studio :: five-command, agent-first entry point.

  init       index the case (contract echo, locator-tagged sources, workorder, candidates)
  show       print locator-tagged material + object tables for the agent to read
  check      mechanically verify the agent's /app/work/draft.json
  build      render figure.svg/png/pdf + finalize result.json (fallback draft if absent)
  selfcheck  re-probe artifacts, re-audit ids, prove deterministic re-render

Exit code is always 0; failure is expressed in result.json / check.json / exceptions.
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
  sys.path.insert(0, str(HERE))
import casekit as ck
import verify as vf
from casekit import REL, as_list, jdump, jload, mkdir, nrm
try:
  import draw
except Exception:
  draw = None

VERSION = "1.0.0"
KNOWN = {"editable_source", "export_artifact", "content_map", "compliance_checks", "exceptions",
         "edit_record", "status", "case_id", "figure_model", "source_binding", "changes",
         "uncertainty", "degradations", "errors", "pending_human", "sources", "runtime"}

def skeleton(idx):
  res = {k: None for k in (idx.get("contract") or ck.DEFAULT_CONTRACT)}
  res.update({"case_id": idx.get("case_id"), "status": "partial",
        "errors": list(idx.get("errors") or []),
        "degradations": list(idx.get("degradations") or []),
        "exceptions": [], "uncertainty": [], "pending_human": [], "changes": [],
        "runtime": {"skill": "schematic-trace-studio", "version": VERSION, "stage": "init",
              "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        "output_contract_echo": idx.get("contract_raw")})
  if "case_id" in res:
    res["case_id"] = idx.get("case_id")
  if "status" in res:
    res["status"] = "partial"
  return res

def load_index(a, inp):
  work = mkdir(ck.discover_out(a.work, work=True))
  idx, _ = jload(work / "index.json")
  if not isinstance(idx, dict):
    idx = ck.build_index(inp)
    jdump(work / "index.json", idx)
  return idx, work

def cmd_init(a, t0):
  inp = ck.discover_input(a.input)
  out, work = mkdir(ck.discover_out(a.output)), mkdir(ck.discover_out(a.work, work=True))
  idx = ck.build_index(inp)
  jdump(work / "index.json", idx)
  res = skeleton(idx)
  res["runtime"].update({"stage": "init", "input_dir": idx["input_dir"]})
  jdump(out / "result.json", res)
  wo = idx["workorder"]
  print("[init] input=%s\n[init] case_id=%r contract=%s" % (idx["input_dir"], idx["case_id"], idx["contract"]))
  print("[init] materials=%d readable_lines=%d workorder=%s baseline=%s"
          % (len([s for s in idx["sources"] if s.get("role") == "material"]),
             sum(s.get("lines") or 0 for s in idx["sources"]), "yes" if wo["present"] else "no",
             (idx["baseline"] or {}).get("rel", "none")))
  print("[init] workorder: entities=%d relations=%d legend=%d tables=%d | candidates: entities=%d relations=%d"
          % (len(wo["entities"]), len(wo["relations"]), len(wo["legend"]), len(idx["tables"]),
             len(idx["candidates"]["entities"]), len(idx["candidates"]["relations"])))
  gaps = sorted({d["type"] for d in idx["degradations"] + idx["errors"]})
  if gaps:
    print("[init] gaps: %s" % ", ".join(gaps))
  print("[init] partial result.json -> %s" % (out / "result.json"))
  print("[init] NEXT: python3 scripts/main.py show")
  return res

def cmd_show(a, t0):
  inp = ck.discover_input(a.input)
  idx, work = load_index(a, inp)
  L = []

  def P(s=""):
    L.append(s)
    print(s)

  wo = idx["workorder"]
  P("=" * 76)
  P("CASE %r   contract=%s" % (idx.get("case_id"), idx.get("contract")))
  P("=" * 76)
  P("\n## sources  (locator: file#Lnn for text, file#pN,Lnn for pdf pages, file#row=N for tables)")
  for s in idx["sources"]:
    P("  %-40s kind=%-4s lines=%-5s pages=%-3s bytes=%-8s %s"
          % (str(s["rel"])[:40], s["kind"], s.get("lines"), s.get("pages"), s.get("bytes"), s.get("error") or ""))
  if idx.get("task_instruction"):
    P("\n## task_instruction (first 1000 chars)\n%s" % idx["task_instruction"][:1000])
  P("\n## workorder  present=%s  type=%s\n  title: %s" % (wo["present"], wo["kind"] or "-", wo["title"] or "(none)"))
  for k in ("canvas", "export", "legend", "annotations", "edits"):
    if wo.get(k):
      P("  %s: %s" % (k, json.dumps(wo[k], ensure_ascii=False)[:300]))
  for i, e in enumerate(wo["entities"], 1):
    P("  [E%02d] %-30s type=%-14s group=%s" % (i, e["label"][:30], e["entity_type"] or "-", e["group"] or "-"))
  for i, r in enumerate(wo["relations"], 1):
    P("  [R%02d] %-26s -[%s]-> %-26s dir=%s"
          % (i, r["from_label"][:26], r["type"], r["to_label"][:26], r["direction"]))
  if idx["baseline"]:
    b = idx["baseline"]
    P("\n## baseline SVG (source-preserving edit target): %s sha256=%s ids=%d texts=%d"
          % (b["rel"], (b["sha256"] or "")[:16], b["n_ids"], b["n_texts"]))
    for t in b["texts"][:24]:
      P("  text: %s" % t)
    P("  ids : %s" % ", ".join(b["ids"][:24]))
  docs, _, _ = ck.corpus_from(idx, inp)
  P("\n## material excerpts with locators  (read here, then quote verbatim in draft.json)")
  focus = [nrm(e["label"]) for e in wo["entities"]] + [nrm(e["label"]) for e in idx["candidates"]["entities"][:40]]
  shown = 0
  for d in docs:
    if not d["lines"]:
      P("  --- %s: no readable text (%s) ---" % (d["rel"], d.get("error")))
      continue
    P("  --- %s (%d lines) ---" % (d["rel"], len(d["lines"])))
    hits = [i for i, (_l, t) in enumerate(d["lines"]) if any(f and f in nrm(t) for f in focus)]
    idxs = sorted({j for i in hits for j in range(max(0, i - 1), min(len(d["lines"]), i + 2))}) \
      or list(range(min(25, len(d["lines"]))))
    prev = -9
    for i in idxs:
      if i - prev > 1:
        P("     ...")
      loc, t = d["lines"][i]
      P("  %-24s %s" % (loc.split("#")[-1], t[:200]))
      prev, shown = i, shown + 1
      if shown > 240:
        break
    if shown > 240:
      break
  if idx["candidates"]["relations"]:
    P("\n## candidate triples (surface extraction, NOT verified: you judge each one)")
    for i, c in enumerate(idx["candidates"]["relations"][:30], 1):
      P("  [K%02d] %-28s -[%s]-> %-28s %s @%s"
              % (i, c["from_label"][:28], c["type"], c["to_label"][:28],
                 "<-passive" if c["direction"] == "reversed" else "", c["locator"]))
      P("        quote: %s" % c["quote"][:180])
  for t in idx["tables"]:
    P("\n## table %s header=%s rows=%d" % (t["rel"], t["header"], t["n_rows"]))
    for r in t["sample"]:
      P("  %s  %s" % (r["locator"], r["cells"]))
  P("\n## draft.json minimum shape (full schema: references/authoring-guide.md §1)")
  P('  {"figure":{"title":"..."},"entities":[{"id":"e1","label":"<verbatim>","entity_type":"<type>",'
      '"group":"<group>","col":0,"row":0,"evidence":{"locator":"<file#Lnn>","quote":"<verbatim line>"}}],'
      '"relations":[{"id":"r1","from":"e1","to":"e2","type":"%s","direction":"forward",'
      '"evidence":{"locator":"...","quote":"..."}}],"legend":[{"key":"activation","label":"Activation",'
      '"color":"#0072B2","marker":"arrow"}],"groups":[],"annotations":[],"edit":{"mode":"none"},'
      '"exceptions":[]}' % "|".join(REL))
  P("  -> write it to %s" % (work / "draft.json"))
  P("\n## NEXT: write draft.json -> python3 scripts/main.py check -> build -> selfcheck")
  (work / "show.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
  print("\n[show] transcript -> %s" % (work / "show.txt"))
  return None

def cmd_check(a, t0):
  inp = ck.discover_input(a.input)
  idx, work = load_index(a, inp)
  draft, err = jload(work / "draft.json")
  docs, by_file, _ = ck.corpus_from(idx, inp)
  rules, blocking, warnings, exc, stats = vf.draft_rules(draft if isinstance(draft, dict) else {},
                                                           idx, docs, by_file)
  report = {"stage": "check", "draft": str(work / "draft.json"), "draft_state": err or "ok",
              "rules": rules, "blocking": blocking, "warnings": warnings, "exceptions": exc,
              "stats": stats, "verdict": "PASS" if stats and not blocking else "FAIL"}
  jdump(work / "check.json", report)
  print("[check] draft=%s" % (err or "ok"))
  for r in rules:
    print("  %s %-5s %s" % ("PASS" if r["ok"] else "FAIL", r["id"], r["detail"]))
  for w in warnings[:10]:
    print("  WARN  %s" % w)
  for e in exc[:8]:
    print("  EXC   %-16s %s" % (e.get("type"), e.get("reason")))
  print("[check] blocking=%d warnings=%d -> %s" % (len(blocking), len(warnings), report["verdict"]))
  if blocking:
    print("[check] edit draft.json per the FAIL lines above, then rerun check")
  return report

def build_figure(idx, draft, inp, out):
  docs, by_file, _ = ck.corpus_from(idx, inp)
  model = draw.make_model(draft, idx, REL)
  geom = draw.geometry(model)
  paths = draw.write_outputs(model, geom, out)
  aud = vf.svg_audit(paths["svg"]["path"])
  cm = {"entities": [], "relations": [], "legend": [], "groups": [],
          "data_points": model.get("data_points", []), "coverage": {}, "svg_ids_expected": [],
          "svg_sha256": paths["svg"].get("sha256"), "element_count": len(geom["items"])}

  def ev_ok(ev):
    return bool(ev.get("locator") and ev.get("quote")
          and ck.quote_hit(ev["quote"], ck.resolve_locator(ev["locator"], by_file, {})[2] or ""))

  for e in model["entities"]:
    ev = e.get("evidence") or {}
    cm["entities"].append({"id": e["id"], "label": e["label"], "entity_type": e.get("entity_type", ""),
                               "group": e.get("group", ""), "svg_ids": [e["id"] + "-box", e["id"] + "-label"],
                               "source": {"kind": "material", "locator": ev.get("locator"), "quote": ev.get("quote")},
                               "verified": ev_ok(ev)})
  for r in model["relations"]:
    ev = r.get("evidence") or {}
    cm["relations"].append({"id": r["id"], "from": r["from"], "to": r["to"], "type": r["type"],
                "direction": r.get("direction", "forward"), "svg_id": r["id"] + "-path",
                "marker": r.get("marker"), "legend_key": r["type"],
                "source": {"kind": "material", "locator": ev.get("locator"), "quote": ev.get("quote")},
                "verified": ev_ok(ev)})
  for g in model["legend"]:
    cm["legend"].append({"id": g["id"], "key": g["key"], "label": g["label"], "color": g["color"],
                             "marker": g["marker"], "svg_ids": [g["id"] + "-swatch", g["id"] + "-label"]})
  for g in model.get("groups", []):
    cm["groups"].append({"id": g["id"], "label": g["label"], "members": g["members"],
                             "svg_ids": [g["id"] + "-band", g["id"] + "-label"]})
  cov = ck.coverage(model["entities"], model["relations"], idx.get("workorder") or {})
  cov.update({"legend_items": len(model["legend"]),
        "encodings_used": len({nrm(r["type"]) for r in model["relations"]}),
        "entities_with_locator": sum(1 for e in cm["entities"] if e["source"]["locator"]),
        "entities_verified": sum(1 for e in cm["entities"] if e["verified"]),
        "relations_verified": sum(1 for r in cm["relations"] if r["verified"])})
  cm["coverage"] = cov
  cm["svg_ids_expected"] = sorted({i for e in cm["entities"] for i in e["svg_ids"]}
                  | {r["svg_id"] for r in cm["relations"]}
                  | {i for g in cm["legend"] for i in g["svg_ids"]}
                  | {i for g in cm["groups"] for i in g["svg_ids"]})
  cc = {"canvas": {"ok": model["canvas"]["width"] > 40 and model["canvas"]["height"] > 40,
                     "width": model["canvas"]["width"], "height": model["canvas"]["height"],
                     "unit": model["canvas"].get("unit", "px")},
          "svg_wellformed": {"ok": bool(aud.get("ok")), "groups": aud.get("groups", []),
                             "text_nodes": aud.get("text_nodes", 0), "paths": aud.get("paths", 0),
                             "markers": aud.get("markers", []), "fonts": aud.get("fonts", []),
                             "error": aud.get("error")}}
  exp, got = set(cm["svg_ids_expected"]), set(aud.get("ids", []))
  cc["id_map"] = {"ok": exp <= got, "expected": len(exp), "found": len(exp & got),
          "missing": sorted(exp - got)[:10]}
  hit = [e for e in cm["entities"] if e["verified"]]
  cc["labels_verbatim"] = {"ok": bool(cm["entities"]) and len(hit) == len(cm["entities"]),
                             "checked": len(cm["entities"]), "hit": len(hit),
                             "miss": [e["label"] for e in cm["entities"] if not e["verified"]][:10]}
  cc["style"] = {"ok": (aud.get("min_font_pt") or 0) >= 6.5 and (aud.get("min_stroke") or 0) >= 0.5,
                   "min_font_pt": aud.get("min_font_pt"), "stroke_widths": aud.get("stroke_widths", []),
                   "palette": sorted({r.get("color") for r in model["relations"]})}
  enc = {nrm(r["type"]) for r in model["relations"]}
  lk = {nrm(g["key"]) for g in model["legend"]}
  cc["markers"] = {"ok": len(aud.get("markers", [])) >= (2 if len(enc) >= 2 else 1),
                     "declared": sorted({g["marker"] for g in model["legend"]}),
                     "svg_markers": aud.get("markers", [])}
  cc["legend_consistency"] = {"ok": enc <= lk and (not enc or len(lk) == len(enc)),
                "encodings": sorted(enc), "legend_items": sorted(lk)}
  lay = vf.layout_checks(model, geom)
  cc["layout"] = {"ok": not lay["overlaps"] and not lay["overflow"], "overlaps": lay["overlaps"][:8],
          "overflow": lay["overflow"][:8], "min_gap": lay.get("min_gap")}
  cc["text_live"] = {"ok": aud.get("text_nodes", 0) >= len(model["entities"]),
                       "svg_text_nodes": aud.get("text_nodes", 0),
                       "pdf_text_extracted": paths["pdf"].get("text_extracted"),
                       "pdf_labels_hit": paths["pdf"].get("label_hits")}
  cc["pixel_probe"] = dict(paths["png"].get("probe") or {}, ok=bool((paths["png"].get("probe") or {}).get("ok")))
  cc["pdf_probe"] = dict(paths["pdf"].get("probe") or {}, ok=bool((paths["pdf"].get("probe") or {}).get("ok")))
  d1, d2 = vf.determinism(model, draw)
  cc["determinism"] = {"ok": bool(d1) and d1 == d2, "svg_sha256": d1, "svg_sha256_recheck": d2}
  fails = [k for k, v in cc.items() if isinstance(v, dict) and v.get("ok") is False]
  cc["pass"], cc["failures"] = not fails, fails
  status = "partial"
  if not fails and not cov["unmapped_required"] and len(hit) == len(cm["entities"]) and not draft.get("_auto"):
    status = "ok"
  if not model["entities"] and not any(s.get("role") == "material" and (s.get("lines") or 0)
                                         for s in idx["sources"]):
    status = "input_error"
  return model, paths, cm, cc, status

def cmd_build(a, t0):
  inp = ck.discover_input(a.input)
  out, work = mkdir(ck.discover_out(a.output)), mkdir(ck.discover_out(a.work, work=True))
  idx, _ = jload(work / "index.json")
  if not isinstance(idx, dict):
    idx = ck.build_index(inp)
    jdump(work / "index.json", idx)
  res = skeleton(idx)
  res["runtime"]["stage"] = "build"
  jdump(out / "result.json", res)                 # legal partial before any heavy work
  draft, err = jload(work / "draft.json")
  docs, by_file, _ = ck.corpus_from(idx, inp)
  degraded = []
  if not isinstance(draft, dict):
    draft = ck.auto_draft(idx, docs)
    degraded.append("draft_missing" if err == "missing" else "draft_invalid")
  rules, blocking, warnings, exc, stats = vf.draft_rules(draft, idx, docs, by_file)
  if blocking:
    degraded.append("draft_incomplete")
  model, paths, cm, cc, status = build_figure(idx, draft, inp, out)
  jdump(out / "figure_model.json", model)
  if idx.get("baseline") and draw:
    rec = draw.edit_record(idx["baseline"], draft)
    if rec:
      jdump(out / "edit_record.json", rec)
  exceptions = list(exc) + [e for e in as_list(draft.get("exceptions")) if isinstance(e, dict)]
  for k in (idx.get("contract") or []):
    if k not in KNOWN:
      exceptions.append({"type": "unknown_contract_field", "object": k,
                               "reason": "contract field not produced by this skill",
                               "action": "left null as contracted (no fabrication)", "locator": None})
  res.update({
    "case_id": idx.get("case_id"), "status": status,
    "editable_source": {"path": str(paths["svg"]["path"]), "format": "svg", "editable": True,
              "text_live": bool(cc["text_live"]["ok"]), "layers": cc["svg_wellformed"]["groups"],
              "text_count": cc["svg_wellformed"]["text_nodes"], "element_count": cm["element_count"],
              "marker_types": cc["svg_wellformed"]["markers"], "sha256": paths["svg"].get("sha256"),
              "coordinate_system": "px, y-down, viewBox = canvas",
              "mode": "preserve" if idx.get("baseline") else "generate"},
    "export_artifact": {"png": paths["png"], "pdf": paths["pdf"]},
    "content_map": cm, "compliance_checks": cc, "exceptions": exceptions,
    "degradations": list(idx["degradations"]) + [{"type": d, "object": "draft", "reason": d,
                                                      "action": "rule-based fallback path used"} for d in degraded],
    "errors": idx["errors"],
    "pending_human": [e for e in exceptions if e.get("type") in
                          ("label_unsourced", "missing_in_source", "pending_human", "quote_unsourced")],
    "uncertainty": [{"type": "extraction_mode",
                         "value": "auto_fallback" if draft.get("_auto") else "agent_draft"},
            {"type": "relation_semantics",
                         "value": "directions asserted in the draft; passive-voice hints raised as warnings"}],
    "sources": [{"rel": s["rel"], "kind": s["kind"], "sha256": s.get("sha256"), "bytes": s.get("bytes"),
                     "lines": s.get("lines"), "role": s.get("role")} for s in idx["sources"]],
    "changes": (json.loads((out / "edit_record.json").read_text(encoding="utf-8")).get("changes", [])
          if (out / "edit_record.json").exists() else []),
    "runtime": {"skill": "schematic-trace-studio", "version": VERSION, "stage": "build",
          "elapsed_s": round(time.time() - t0, 2),
          "engines": {"png": paths["png"].get("engine"), "pdf": paths["pdf"].get("engine"),
                "pdf_text_probe": paths["pdf"].get("text_probe_engine")},
          "contract_fields": len(idx.get("contract") or []),
          "draft_used": "auto_fallback" if draft.get("_auto") else "agent",
          "check_blocking": blocking[:6], "check_warnings": warnings[:8],
          "input_dir": idx.get("input_dir"), "output_dir": str(out)}})
  jdump(out / "result.json", res)
  print("[build] status=%s entities=%d relations=%d legend=%d groups=%d"
          % (status, len(model["entities"]), len(model["relations"]), len(model["legend"]),
             len(model.get("groups", []))))
  print("[build] svg=%s bytes=%s | png=%s engine=%s | pdf=%s pages=%s"
          % (paths["svg"]["path"], paths["svg"]["bytes"], paths["png"].get("path"), paths["png"].get("engine"),
             paths["pdf"].get("path"), (paths["pdf"].get("probe") or {}).get("pages")))
  print("[build] coverage=%s checks_pass=%s failures=%s"
          % (json.dumps({k: cm["coverage"][k] for k in ("entity_coverage", "relation_coverage")},
            ensure_ascii=False), cc["pass"], cc["failures"]))
  print("[build] result.json -> %s" % (out / "result.json"))
  if degraded:
    print("[build] DEGRADED (%s): write /app/work/draft.json, rerun check then build for a judged figure"
              % ",".join(sorted(set(degraded))))
  return res

def cmd_selfcheck(a, t0):
  out = ck.discover_out(a.output)
  res, err = jload(Path(out) / "result.json")
  if not isinstance(res, dict):
    print("[selfcheck] result.json missing/invalid (%s) - run build first" % err)
    return None
  checks = {}
  es = res.get("editable_source") or {}
  sp = es.get("path")
  checks["svg_present"] = bool(sp and Path(sp).exists())
  checks["svg_sha_matches"] = bool(checks["svg_present"] and ck.sha_file(sp) == es.get("sha256"))
  model, _ = jload(Path(out) / "figure_model.json")
  if checks["svg_present"] and isinstance(model, dict) and draw:
    try:
      checks["deterministic_rerender"] = (ck.sha_bytes(draw.render_svg(model).encode("utf-8"))
                        == es.get("sha256"))
    except Exception as e:
      checks["deterministic_rerender"] = "error: %r" % e
  ea = res.get("export_artifact") or {}
  for k in ("png", "pdf"):
    p = (ea.get(k) or {}).get("path")
    checks[k + "_present"] = bool(p and Path(p).exists())
    if checks[k + "_present"]:
      checks[k + "_probe"] = vf.png_probe(p) if k == "png" else vf.pdf_probe(p)
  cm = res.get("content_map") or {}
  if checks["svg_present"]:
    aud = vf.svg_audit(sp)
    exp = set(cm.get("svg_ids_expected") or [])
    checks["id_map_recheck"] = {"ok": exp <= set(aud.get("ids", [])), "expected": len(exp),
                  "missing": sorted(exp - set(aud.get("ids", [])))[:8]}
  cc = res.get("compliance_checks") or {}
  verdict = "ok"
  if not checks["svg_present"] or not checks["svg_sha_matches"] or not cc.get("pass") \
      or checks.get("deterministic_rerender") is False:
    verdict = "partial"
  print("[selfcheck] verdict=%s  status=%s" % (verdict, res.get("status")))
  for k, v in checks.items():
    if isinstance(v, dict):
      print("  %-22s ok=%s %s" % (k, v.get("ok"), {kk: vv for kk, vv in v.items() if kk != "ok"}))
    else:
      print("  %-22s %s" % (k, v))
  return {"verdict": verdict, "checks": checks}

def main(argv=None):
  ap = argparse.ArgumentParser(prog="schematic-trace-studio",
                                 description="agent-first scientific schematic pipeline: init/show/check/build/selfcheck")
  ap.add_argument("cmd", nargs="?", default="help",
          choices=["init", "show", "check", "build", "selfcheck", "help"])
  ap.add_argument("--input", default=None, help="case dir (default: /input, /app/input, ./input)")
  ap.add_argument("--work", default=None, help="working dir (default: /app/work)")
  ap.add_argument("--output", default=None, help="output dir (default: /app/output)")
  a = ap.parse_args(argv)
  t0 = time.time()
  if a.cmd == "help":
    print(__doc__)
    print("order: init -> show -> (write /app/work/draft.json) -> check -> build -> selfcheck")
    print("note : the script never reads the material for you; build alone yields a degraded deliverable")
    return 0
  fn = {"init": cmd_init, "show": cmd_show, "check": cmd_check,
          "build": cmd_build, "selfcheck": cmd_selfcheck}[a.cmd]
  try:
    fn(a, t0)
  except Exception:
    tb = traceback.format_exc()
    print("[fatal] %s" % tb.splitlines()[-1])
    try:
      out = mkdir(ck.discover_out(a.output))
      res, _ = jload(Path(out) / "result.json")
      if not isinstance(res, dict):
        res = skeleton(ck.build_index(None))
      res.setdefault("errors", []).append({"type": "unhandled_exception", "object": a.cmd,
                                                 "reason": tb.splitlines()[-1],
                                                 "action": "partial result kept; artifacts may be incomplete",
                                                 "traceback_tail": tb[-900:]})
      res["status"] = res.get("status") or "partial"
      jdump(out / "result.json", res)
    except Exception:
      pass
  return 0

if __name__ == "__main__":
  sys.exit(main())
