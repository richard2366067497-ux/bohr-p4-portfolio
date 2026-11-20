#!/usr/bin/env python3
"""schematic-trace-studio :: case indexing kit (pure stdlib, no side effects on import).

Everything that turns a case directory into structured, locator-tagged facts lives here:
input discovery, material reading (pdf via pdftotext + page/line locators), workorder
normalisation by semantic keys, surface relation candidates, table previews, quote
resolution, and the fallback draft synthesised when the agent wrote none.
"""
import hashlib
import json
import os
import re
import subprocess
import time
import traceback  # noqa: F401  (kept for callers that format tracebacks)
import unicodedata
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".tex", ".xml",
      ".log", ".r", ".py", ".mdown", ".markdown", ".bib", ".tab"}
UNSUPPORTED = {".docx", ".xlsx", ".xls", ".doc", ".pptx", ".png", ".jpg", ".jpeg",
               ".gif", ".tif", ".tiff", ".zip", ".gz", ".pyc"}
DEFAULT_CONTRACT = ["editable_source", "export_artifact", "content_map",
          "compliance_checks", "exceptions"]

# relation vocabulary: type -> rendering semantics + surface patterns (en / zh)
REL = {
  "activation": {"label": "Activation", "marker": "arrow", "color": "#0072B2",
                   "en": [r"activates?", r"activated", r"activating", r"stimulat(es|ed|ing)",
                          r"promot(es|ed|ing)", r"in-?duc(es|ed|ing)", r"up-?regulat(es|ed)",
                          r"enhanc(es|ed)", r"driv(es|ing)", r"triggers?"],
                   "zh": ["激活", "促进", "上调", "增强", "诱导", "触发"]},
  "inhibition": {"label": "Inhibition", "marker": "tbar", "color": "#D55E00",
                   "en": [r"inhibits?", r"inhibited", r"inhibiting", r"suppress(es|ed|ing)",
                          r"repress(es|ed)", r"blocks?", r"blocked", r"reduc(es|ed)",
                          r"decreas(es|ed)", r"attenuat(es|ed)", r"down-?regulat(es|ed)"],
                   "zh": ["抑制", "下调", "阻断", "降低", "减弱", "阻遏"]},
  "binding": {"label": "Binding", "marker": "diamond", "color": "#009E73",
        "en": [r"binds?", r"bound", r"binding", r"interacts? with", r"associates? with",
                       r"complex(es)? with", r"docks?"],
        "zh": ["结合", "互作", "相互作用", "复合", "锚定"]},
  "modification": {"label": "Modification", "marker": "thin", "color": "#CC79A7",
                     "en": [r"phosphorylat(es|ed)", r"methylat(es|ed)", r"ubiquitinat(es|ed)",
              r"cleav(es|ed)", r"acetylates?", r"modifi(es|ed)"],
                     "zh": ["磷酸化", "甲基化", "泛素化", "剪切", "乙酰化", "修饰"]},
  "expression": {"label": "Expression", "marker": "thin", "color": "#56B4E9",
                   "en": [r"express(es|ed)", r"encodes?", r"transcrib(es|ed)", r"translat(es|ed)"],
                   "zh": ["表达", "编码", "转录", "翻译"]},
  "transport": {"label": "Transport", "marker": "thin", "color": "#E69F00",
                  "en": [r"transports?", r"translocat(es|ed)", r"secret(es|ed)", r"exports?",
                         r"imports?", r"release[ds]?"],
                  "zh": ["转运", "易位", "分泌", "输出", "输入", "释放"]},
  "containment": {"label": "Containment", "marker": "square", "color": "#8C8C8C",
          "en": [r"contains?", r"comprises?", r"includes?", r"consists? of",
                           r"is part of", r"subunit of", r"belongs? to"],
          "zh": ["包含", "组成", "属于", "包括", "位于"]},
  "sequence": {"label": "Sequence", "marker": "thin", "color": "#666666",
                 "en": [r"then", r"subsequently", r"followed by", r"after that"],
                 "zh": ["随后", "然后", "接着", "之后"]},
  "association": {"label": "Association", "marker": "line", "color": "#3C3C3C",
          "en": [r"associates?", r"correlates?", r"is related to", r"is linked to"],
          "zh": ["相关", "关联", "有关"]},
}
PASSIVE = [r"\bis\s+\w*ed\s+by\b", r"\bare\s+\w*ed\s+by\b", r"\bwas\s+\w*ed\s+by\b",
           r"被.{0,12}(抑制|激活|促进|阻断|下调|上调)", r"受.{0,12}(抑制|调控)"]

def nrm(s):
  if s is None:
    return ""
  s = unicodedata.normalize("NFKC", str(s))
  for a, b in (("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"),
                 ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u00a0", " ")):
    s = s.replace(a, b)
  return re.sub(r"\s+", " ", s).strip().lower()

def sha_bytes(b):
  return hashlib.sha256(b).hexdigest()

def sha_file(p):
  try:
    return sha_bytes(Path(p).read_bytes())
  except Exception:
    return None

def jload(p, default=None):
  p = Path(p)
  if not p.exists():
    return default, "missing"
  try:
    return json.loads(p.read_text(encoding="utf-8", errors="replace")), None
  except Exception as e:
    return default, "invalid_json: %s" % (str(e)[:160])

def jdump(p, obj):
  p = Path(p)
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  return p

def mkdir(p):
  p = Path(p)
  p.mkdir(parents=True, exist_ok=True)
  return p

def pick(d, *keys, **kw):
  """first present key (case/space/dash insensitive) of a dict."""
  default = kw.get("default")
  if not isinstance(d, dict):
    return default
  low = {re.sub(r"[\s\-]+", "_", str(k)).lower(): k for k in d}
  for k in keys:
    kk = re.sub(r"[\s\-]+", "_", k).lower()
    if kk in low:
      return d[low[kk]]
  return default

def as_list(v):
  if v is None:
    return []
  return v if isinstance(v, list) else [v]

def rows_text(p):
  try:
    return Path(p).read_text(encoding="utf-8", errors="replace")
  except Exception:
    return ""

def run(cmd, timeout=45):
  try:
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
  except Exception as e:
    return 127, "", repr(e)

def discover_input(arg):
  for c in ([Path(arg)] if arg else []) + [Path("/input"), Path("/app/input"),
                                             Path.cwd() / "input", Path(__file__).resolve().parent.parent / "input"]:
    try:
      if c.is_dir():
        return c.resolve()
    except Exception:
      continue
  return None

def discover_out(arg, work=False):
  if arg:
    return Path(arg).resolve()
  base = Path("/app") if Path("/app").is_dir() and os.access("/app", os.W_OK) else Path.cwd()
  return (base / ("work" if work else "output")).resolve()

def material_files(root, limit=60):
  out, skip = [], {"__pycache__", ".git", "node_modules", "scripts", "references"}
  if not root:
    return out
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
    for fn in sorted(filenames):
      p = Path(dirpath) / fn
      try:
        if p.stat().st_size > 12 * 1024 * 1024:
          continue
      except Exception:
        continue
      out.append(p)
      if len(out) >= limit:
        return out
  return out

def read_doc(p, root=None):
  """-> {rel, kind, lines:[(locator, text)], pages, bytes, sha256, error, unsupported}"""
  p = Path(p)
  rel = (str(p.relative_to(root)) if root and str(p).startswith(str(root)) else p.name).replace(os.sep, "/")
  ext = p.suffix.lower()
  doc = {"rel": rel, "kind": ext.lstrip(".") or "bin", "lines": [], "pages": 0,
           "bytes": 0, "sha256": None, "error": None, "unsupported": False}
  try:
    doc["bytes"] = p.stat().st_size
  except Exception:
    pass
  if ext == ".pdf":
    code, out, _ = run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"], timeout=60)
    if code != 0 or not out.strip():
      doc["error"] = "no_text_layer" if code == 0 else "pdftotext_failed"
      doc["sha256"] = sha_file(p)
      return doc
    pages = out.split("\f")
    doc["pages"] = len([x for x in pages if x.strip()]) or 1
    for pi, page in enumerate(pages, 1):
      for li, line in enumerate(page.splitlines(), 1):
        if line.strip():
          doc["lines"].append(("%s#p%d,L%d" % (rel, pi, li), line.rstrip()))
  elif ext in TEXT_EXT:
    txt = rows_text(p)
    doc["sha256"] = sha_bytes(txt.encode("utf-8", "replace"))
    for li, line in enumerate(txt.splitlines(), 1):
      if line.strip():
        doc["lines"].append(("%s#L%d" % (rel, li), line.rstrip()))
  elif ext in UNSUPPORTED:
    doc["unsupported"] = True
    doc["error"] = "unsupported_source"
    doc["sha256"] = sha_file(p)
  else:
    doc["unsupported"] = True
    doc["error"] = "unknown_extension"
  return doc

def norm_entities(raw):
  out = []
  for i, e in enumerate(as_list(raw)):
    if isinstance(e, str):
      out.append({"label": e.strip(), "entity_type": "", "group": "", "raw_index": i})
    elif isinstance(e, dict):
      lab = pick(e, "label", "name", "id", "entity", "value", "text", "node", default="")
      out.append({"label": str(lab).strip(),
            "entity_type": str(pick(e, "entity_type", "type", "category", "class", default="") or ""),
            "group": str(pick(e, "group", "compartment", "layer", "panel", "region", default="") or ""),
            "raw_index": i})
  return [e for e in out if e["label"]]

def norm_relations(raw):
  out = []
  for i, r in enumerate(as_list(raw)):
    if isinstance(r, str):
      m = re.match(r"\s*([^\[\-<>→]+?)\s*(?:->|→|\[\s*([\w_]+)\s*\]|-\s*\[([\w_]+)\]-)\s*(.+?)\s*$", r)
      if not m:
        continue
      out.append({"from_label": m.group(1).strip(), "to_label": m.group(4).strip(),
            "type": (m.group(2) or m.group(3) or "association").strip().lower(),
            "direction": "forward", "condition": "", "raw_index": i})
    elif isinstance(r, dict):
      a = pick(r, "from", "source", "src", "head", "subject", "parent", "upstream",
                     "from_entity", "a", default="")
      b = pick(r, "to", "target", "dst", "tail", "object", "child", "downstream",
                     "to_entity", "b", default="")
      t = pick(r, "type", "relation", "rel", "kind", "effect", "modality",
                     "relationship", "interaction", default="association")
      if isinstance(a, dict):
        a = pick(a, "label", "name", "id", default="")
      if isinstance(b, dict):
        b = pick(b, "label", "name", "id", default="")
      out.append({"from_label": str(a).strip(), "to_label": str(b).strip(),
            "type": str(t or "association").strip().lower().replace(" ", "_"),
            "direction": str(pick(r, "direction", "dir", "orientation", "sense",
                                              default="forward") or "forward").lower(),
            "condition": str(pick(r, "condition", "context", "when", "note", default="") or ""),
            "raw_index": i})
  return [r for r in out if r["from_label"] and r["to_label"]]

def find_workorder(case, files):
  cands = []
  if isinstance(case, dict):
    for k in ("organizer_workorder", "organizer_edit_workorder", "figure_workorder",
                  "workorder", "figure_spec", "figure_specification", "drawing_workorder", "edit_workorder"):
      v = pick(case, k)
      if isinstance(v, dict) and v:
        cands.append(v)
    for k in ("material", "materials", "inputs", "metadata"):
      v = pick(case, k)
      if isinstance(v, dict):
        w = pick(v, "workorder", "figure_workorder", "figure_spec")
        if isinstance(w, dict):
          cands.append(w)
  for f in files:
    n = f.name.lower()
    if "workorder" in n or "work_order" in n or n in ("material.json", "figure_spec.json", "figure.json"):
      obj, _ = jload(f)
      if isinstance(obj, dict):
        inner = pick(obj, "workorder", "figure_workorder", "figure_spec")
        cands.append(inner if isinstance(inner, dict) else obj)
  wo = {}
  for c in cands:
    for k, v in c.items():
      wo.setdefault(re.sub(r"[\s\-]+", "_", str(k)).lower(), v)
  return wo, len(cands)

def norm_workorder(wo):
  canvas = pick(wo, "canvas", "size", "dimensions", "page", "figure_size", default={}) or {}
  if isinstance(canvas, str):
    m = re.findall(r"\d+", canvas)
    canvas = {"width": int(m[0]), "height": int(m[1])} if len(m) >= 2 else {}
  if not isinstance(canvas, dict):
    canvas = {}
  exp = pick(wo, "export", "export_formats", "exports", "output_formats", "deliverables", default={}) or {}
  if isinstance(exp, (list, str, int)):
    exp = {"formats": as_list(exp)} if not isinstance(exp, dict) else exp
  return {
    "present": bool(wo),
    "title": str(pick(wo, "figure_title", "title", "caption", "figure_name", "name", default="") or ""),
    "kind": str(pick(wo, "workorder_type", "figure_kind", "diagram_type", "kind",
                         "schema_type", default="editable_relationship_schematic") or ""),
    "entities": norm_entities(pick(wo, "required_entities", "entities", "nodes", "objects",
                                       "actors", "participants", "elements", "components", default=[])),
    "relations": norm_relations(pick(wo, "required_relations", "relations", "edges", "links",
                                         "interactions", "connections", "arrows", default=[])),
    "legend": as_list(pick(wo, "legend_requirements", "legend", "legend_items", "key_items", default=[])),
    "annotations": as_list(pick(wo, "required_annotations", "annotations", "must_include",
                  "required_labels", "labels", default=[])),
    "canvas": {k: v for k, v in canvas.items() if k in ("width", "height", "unit")},
    "export": exp,
    "baseline": str(pick(wo, "source_artifact", "baseline", "source_figure", "edit_target",
                             "base_svg", "source_svg", "base_figure", default="") or ""),
    "edits": as_list(pick(wo, "edit_operations", "edits", "changes", "modifications",
                              "operations", "rewrites", default=[])),
    "style": pick(wo, "style", "font_family", "palette", "colors", default={}) or {},
    "raw_keys": sorted(wo.keys())[:40],
  }

def extract_candidates(docs):
  """surface A-[relation]->B candidates; passive voice flips direction (a hint, not a verdict)."""
  rels, ents, seen_e = [], [], set()
  for doc in docs:
    for loc, text in doc["lines"]:
      for rt, spec in REL.items():
        for pat in list(spec["en"]) + list(spec["zh"]):
          if pat.isascii():
            rx = (r"(?P<a>[A-Za-z0-9][\w\-/\.]{1,38}?(?:\s[A-Z0-9][\w\-]{1,20}){0,3})\s+"
                              r"(?:" + pat + r")\s+"
                              r"(?P<b>[A-Za-z0-9][\w\-/\.]{1,38}?(?:\s[A-Z0-9][\w\-]{1,20}){0,3})")
          else:
            rx = (r"(?P<a>[\u4e00-\u9fa5A-Za-z0-9\-]{2,18}?)(?:可|能|会|显著|直接|进一步)?"
                              r"(?:" + pat + r")(?:了|着)?(?P<b>[\u4e00-\u9fa5A-Za-z0-9\-]{2,18})")
          try:
            m = re.search(rx, text)
          except re.error:
            continue
          if not m:
            continue
          a, b = m.group("a").strip(" ,.;:()[]"), m.group("b").strip(" ,.;:()[]")
          if len(a) < 2 or len(b) < 2 or nrm(a) == nrm(b):
            continue
          rev = any(re.search(p, text, re.I) for p in PASSIVE)
          rels.append({"from_label": b if rev else a, "to_label": a if rev else b,
                                 "type": rt, "direction": "reversed" if rev else "forward",
                                 "locator": loc, "quote": text.strip()[:400]})
          for x in (a, b):
            if nrm(x) not in seen_e:
              seen_e.add(nrm(x))
              ents.append({"label": x, "locator": loc, "quote": text.strip()[:400]})
          break
      if len(rels) > 220:
        return {"entities": ents, "relations": rels}
  return {"entities": ents, "relations": rels}

def parse_tables(docs):
  tabs = []
  for doc in docs:
    if doc["kind"] not in ("csv", "tsv", "tab"):
      continue
    rows = [t for _, t in doc["lines"]]
    if len(rows) < 2:
      continue
    sep = "\t" if doc["kind"] in ("tsv", "tab") else ","
    head = [c.strip().strip('"') for c in rows[0].split(sep)]
    body = [{"row": i, "cells": [c.strip().strip('"') for c in r.split(sep)],
                 "locator": "%s#row=%d" % (doc["rel"], i)}
        for i, r in enumerate(rows[1:7], 2)]
    tabs.append({"rel": doc["rel"], "header": head, "sample": body, "n_rows": len(rows) - 1})
  return tabs

def contract_of(case):
  raw = pick(case, "output_contract", "outputContract", "outputs_contract", "result_contract",
               "required_outputs", "contract") if isinstance(case, dict) else None
  names = []
  if isinstance(raw, list):
    for it in raw:
      if isinstance(it, str):
        names.append(it.strip())
      elif isinstance(it, dict):
        n = pick(it, "name", "field", "key", "id", "path", "output", default="")
        if n:
          names.append(str(n).strip())
  elif isinstance(raw, dict):
    names = [str(k).strip() for k in raw.keys()]
  elif isinstance(raw, str):
    names = [x.strip() for x in re.split(r"[,\s;]+", raw) if x.strip()]
  seen, out = set(), []
  for n in names:
    if n and n not in seen:
      seen.add(n)
      out.append(n)
  return out, raw

def build_index(inp):
  idx = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "input_dir": str(inp) if inp else None, "case_id": None, "contract": [],
           "contract_raw": None, "task_instruction": "", "task_md_excerpt": "", "sources": [],
           "workorder": {}, "workorder_sources": 0, "candidates": {"entities": [], "relations": []},
           "tables": [], "baseline": None, "errors": [], "degradations": []}
  if not inp:
    idx["errors"].append({"type": "no_input_dir", "object": None,
                              "reason": "none of /input, /app/input, ./input exists",
                              "action": "result.json written with status=input_error"})
    idx["workorder"] = norm_workorder({})
    idx["contract"] = list(DEFAULT_CONTRACT)
    return idx
  files = material_files(inp)
  case_path = next((f for f in files if f.name.lower() == "case.json"), None) or \
    next((f for f in files if f.name.lower().startswith("case") and f.suffix.lower() == ".json"), None)
  case = {}
  if case_path:
    case, err = jload(case_path)
    if err:
      idx["errors"].append({"type": "case_json_" + err.split(":")[0], "object": case_path.name,
                                  "reason": err, "action": "continued with empty case shell"})
    case = case if isinstance(case, dict) else {}
  else:
    idx["errors"].append({"type": "case_json_missing", "object": str(inp),
                              "reason": "no case.json in input tree",
                              "action": "case_id left null; contract defaults applied"})
  idx["case_id"] = pick(case, "case_id", "caseId", "case", "id", "uid") if case else None
  names, raw = contract_of(case)
  if names:
    idx["contract"], idx["contract_raw"] = names, raw
  else:
    idx["contract"] = list(DEFAULT_CONTRACT)
    idx["degradations"].append({"type": "contract_defaulted", "object": "output_contract",
                  "reason": "no output_contract in case.json",
                  "action": "used the five documented core fields"})
  idx["task_instruction"] = str(pick(case, "task_instruction", "instruction", "prompt", "task",
                                       "description", default="") or "")[:4000]
  tmd = next((f for f in files if f.name.lower() in ("task.md", "task.txt")), None)
  if tmd:
    t = rows_text(tmd)
    idx["task_md_excerpt"] = t[:2500]
    idx["sources"].append({"rel": tmd.name, "kind": "md", "bytes": len(t.encode("utf-8", "replace")),
                               "sha256": sha_bytes(t.encode("utf-8", "replace")),
                               "lines": len(t.splitlines()), "pages": 0, "role": "task"})
  docs = []
  for f in files:
    if (tmd and f == tmd) or (case_path and f == case_path):
      continue
    d = read_doc(f, inp)
    d["role"] = "material"
    docs.append(d)
    idx["sources"].append({"rel": d["rel"], "kind": d["kind"], "bytes": d.get("bytes"),
                               "sha256": d.get("sha256"), "lines": len(d["lines"]),
                               "pages": d["pages"], "role": "material", "error": d.get("error")})
    if d.get("unsupported") and d["kind"] != "svg":
      idx["degradations"].append({"type": "unsupported_source", "object": d["rel"],
                    "reason": d.get("error"),
                    "action": "registered as gap; content not invented"})
    if d.get("error") == "no_text_layer":
      idx["errors"].append({"type": "no_text_layer", "object": d["rel"],
                                  "reason": "pdftotext returned no text",
                                  "action": "content not guessed; recorded as gap"})
  wo_raw, nwo = find_workorder(case, files)
  idx["workorder"] = norm_workorder(wo_raw)
  idx["workorder_sources"] = nwo
  if not idx["workorder"]["present"]:
    idx["degradations"].append({"type": "workorder_missing", "object": "workorder",
                  "reason": "no workorder object in case.json or *workorder*.json",
                  "action": "figure built from material candidates only"})
  idx["candidates"] = extract_candidates(docs)
  idx["tables"] = parse_tables(docs)
  want = nrm(idx["workorder"]["baseline"])
  svgs = [f for f in files if f.suffix.lower() == ".svg"]
  base = None
  if want:
    base = next((f for f in svgs if nrm(f.name) == want or want in nrm(str(f))), None)
  base = base or (svgs[0] if svgs else None)
  if base is not None:
    txt = rows_text(base)
    ids = re.findall(r'id="([^"]+)"', txt)
    labels = re.findall(r"<text[^>]*>(.*?)</text>", txt, re.S)
    idx["baseline"] = {"rel": base.name, "path": str(base), "sha256": sha_file(base),
                           "bytes": len(txt.encode("utf-8", "replace")), "ids": ids[:200],
                           "texts": [re.sub(r"<[^>]+>", "", t).strip()[:120] for t in labels][:120],
                           "n_ids": len(ids), "n_texts": len(labels)}
  if not any(s.get("role") == "material" and (s.get("lines") or 0) > 0 for s in idx["sources"]):
    idx["degradations"].append({"type": "no_readable_material", "object": None,
                  "reason": "no material source with readable lines",
                  "action": "status=input_error unless an edit baseline exists"})
  return idx

def corpus_from(idx, inp):
  """re-read sources: docs list + per-file lines + locator->text map."""
  docs, by_file, lines_by_loc = [], {}, {}
  for s in idx.get("sources") or []:
    if s.get("role") != "material":
      continue
    p = (Path(inp) / s["rel"]) if inp else None
    if (not p or not p.exists()) and inp:
      cand = list(Path(inp).rglob(Path(s["rel"]).name))
      p = cand[0] if cand else None
    if not p or not p.exists():
      continue
    d = read_doc(p, inp)
    docs.append(d)
    by_file[d["rel"]] = [t for _, t in d["lines"]]
    for loc, t in d["lines"]:
      lines_by_loc[loc] = t
    lines_by_loc.setdefault(d["rel"], "\n".join(t for _, t in d["lines"]))
  return docs, by_file, lines_by_loc

def resolve_locator(loc, by_file, lines_by_loc=None):
  """-> (file_rel, lineno|None, text|None). Accepts file#L12, file#p3,L7, file#row=4, or a bare file."""
  lines_by_loc = lines_by_loc or {}
  if not loc:
    return None, None, None
  loc = str(loc).strip()
  if loc in lines_by_loc:
    m = re.search(r"#(?:p\d+,)?L(\d+)$", loc) or re.search(r"#row=(\d+)", loc)
    return loc.split("#")[0], (int(m.group(1)) if m else None), lines_by_loc[loc]
  m = re.match(r"^(.*?)#(?:p(\d+),)?L(\d+)$", loc)
  if m:
    f, ln = m.group(1), int(m.group(3))
    for rel, lines in by_file.items():
      if rel == f or rel.endswith("/" + f) or Path(rel).name == Path(f).name:
        if 0 < ln <= len(lines):
          return rel, ln, lines[ln - 1]
    return f, ln, None
  for rel in by_file:
    if rel == loc or Path(rel).name == Path(loc).name:
      return rel, None, "\n".join(by_file[rel])
  return loc, None, None

def quote_hit(quote, text):
  q, t = nrm(quote), nrm(text)
  return bool(q) and bool(t) and q in t

def locate_quote(quote, docs):
  q = nrm(quote)
  if not q:
    return None, None
  for d in docs:
    for loc, t in d["lines"]:
      if q in nrm(t):
        return loc, t.strip()
  for d in docs:
    if q in nrm(" ".join(t for _, t in d["lines"])):
      return d["rel"], "(multi-line quote)"
  return None, None

def label_in_material(label, docs):
  loc, txt = locate_quote(label, docs)
  return bool(loc)

def coverage(entities, relations, wo):
  lab = {nrm(e["label"]): str(e["id"]) for e in entities}
  by_id = {str(e["id"]): nrm(e["label"]) for e in entities}
  wo_e = [nrm(e["label"]) for e in wo.get("entities") or []]
  have_r = {(by_id.get(str(r.get("from")), ""), by_id.get(str(r.get("to")), ""), nrm(r.get("type")))
              for r in relations}
  wo_r = [(nrm(r["from_label"]), nrm(r["to_label"]), nrm(r["type"])) for r in wo.get("relations") or []]
  miss_e = [x for x in wo_e if x not in lab]
  miss_r = ["%s -[%s]-> %s" % w for w in wo_r if w not in have_r]
  return {"required_entities": len(wo_e), "mapped_entities": len(wo_e) - len(miss_e),
      "entity_coverage": round((len(wo_e) - len(miss_e)) / len(wo_e), 3) if wo_e else None,
      "required_relations": len(wo_r), "mapped_relations": len(wo_r) - len(miss_r),
      "relation_coverage": round((len(wo_r) - len(miss_r)) / len(wo_r), 3) if wo_r else None,
      "unmapped_required": (["entity:" + m for m in miss_e] +
                                  ["relation:" + m for m in miss_r])[:20]}

def auto_draft(idx, docs):
  """minimal working draft from workorder + candidates. No scientific judgement applied."""
  wo = idx["workorder"]
  ents, rels, lab2id = [], [], {}

  def add(label, etype="", group=""):
    k = nrm(label)
    if not k:
      return None
    if k in lab2id:
      return lab2id[k]
    eid = "e%d" % (len(ents) + 1)
    loc, quote = locate_quote(label, docs)
    ents.append({"id": eid, "label": label, "entity_type": etype, "group": group,
                     "evidence": {"locator": loc, "quote": (quote or "")[:300]}})
    lab2id[k] = eid
    return eid

  for e in wo.get("entities") or []:
    add(e["label"], e.get("entity_type", ""), e.get("group", ""))
  for r in wo.get("relations") or []:
    a, b = add(r["from_label"]), add(r["to_label"])
    if not a or not b:
      continue
    loc, quote = locate_quote(r["from_label"], docs)
    rels.append({"id": "r%d" % (len(rels) + 1), "from": a, "to": b,
                     "type": r["type"] if r["type"] in REL else "association",
                     "direction": r.get("direction", "forward"), "condition": r.get("condition", ""),
                     "evidence": {"locator": loc, "quote": (quote or "")[:300]}})
  if not rels:
    for c in (idx.get("candidates") or {}).get("relations", [])[:24]:
      a, b = add(c["from_label"]), add(c["to_label"])
      if a and b and a != b:
        rels.append({"id": "r%d" % (len(rels) + 1), "from": a, "to": b, "type": c["type"],
                             "direction": c.get("direction", "forward"), "condition": "",
                             "evidence": {"locator": c["locator"], "quote": c["quote"][:300]}})
  legend = [{"key": rt, "label": REL[rt]["label"], "color": REL[rt]["color"], "marker": REL[rt]["marker"]}
              for rt in REL if any(nrm(r["type"]) == nrm(rt) for r in rels)]
  return {"figure": {"title": (wo.get("title") or "") or ("Figure " + str(idx.get("case_id") or "schematic")),
                       "kind": (wo.get("kind") or "") or "relationship_schematic"},
      "entities": ents, "relations": rels, "legend": legend, "groups": [],
      "annotations": [], "edit": {"mode": "none"}, "exceptions": [], "_auto": True}
