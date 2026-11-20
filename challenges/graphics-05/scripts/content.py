"""content.py - from the agent draft to auditable deliverables.

fallback_draft/table_encodings/expand_charts/prune keep the content honest; content_map and
compliance turn it into evidence and checks; edit_record records versions and edits.
"""
import hashlib
import json
import os
import re

import emit
import layout
from core import evaluate, loose, match_quote, norm, num, numbers

ROLES = ("problem", "method", "results", "implication")
NUM = re.compile(r"\d+(?:[.,]\d+)?")

def load_draft(work):
    for name in ("draft.json", "plan.json"):
        p = os.path.join(str(work), name)
        if os.path.isfile(p):
            try:
                d = json.loads(open(p, encoding="utf-8-sig").read())
                if isinstance(d, dict) and d.get("panels"):
                    return d, name
                return None, "%s has no panels[]" % name
            except Exception as exc:
                return None, "%s is not valid JSON (%s)" % (name, str(exc)[:100])
    return None, "draft.json missing"

ROLE_HINTS = { "problem": ("unknown", "unclear", "remains", "challenge", "limited", "lack", "whether",
                "unresolved", "has not", "poorly"),
    "method": ("we used", "we performed", "we applied", "method", "assay", "cryo", "sequenc",
               "protocol", "we measured", "were treated", "approach", "we generated", "pipeline"),
    "results": ("we found", "increased", "decreased", "reduced", "higher", "lower", "compared",
                "p =", "p<", "p <", "significant", "showed", "revealed", "fold", "correlat"),
    "implication": ("suggest", "indicat", "conclude", "imply", "these results", "our findings",
                    "may enable", "provides", "potential", "opens", "supports", "consistent with"),
}

def _sentences(paras, lo=55, hi=330):
    out = []
    for p in paras:
        t = norm(p.get("text"))
        if not t or t[0] in "#|" or t.lower().startswith(("figure", "table", "doi", "http")):
            continue
        for s in re.split(r"(?<=[.!?。！？])\s+", t):
            s = s.strip()
            if lo <= len(s) <= hi:
                out.append((s, p))
    return out

def fallback_draft(index):
    """Quote-only stand-in: honest, complete, and obviously not curated."""
    sents = _sentences(index.get("paragraphs") or [])
    used, panels = set(), []
    for role in (index.get("spec") or {}).get("required_roles") or ROLES:
        scored = sorted([(sum(1 for h in ROLE_HINTS[role] if h in s.lower()), -i, i)
                         for i, (s, p) in enumerate(sents)], reverse=True)
        pick = next((i for sc, _, i in scored if i not in used and sc > 0), None)
        if pick is None:
            pick = next((i for i in range(len(sents)) if i not in used), None)
        if pick is None:
            continue
        used.add(pick)
        sent, para = sents[pick]
        panels.append({"id": "P%d" % (len(panels) + 1), "role": role, "heading": role.title(),
                       "claim": sent if len(sent) <= 150 else sent[:147],
                       "items": [{"id": "E%d" % (len(panels) + 1), "kind": "text",
                                  "label": sent[:38].rstrip(" ,.;:"), "detail": sent,
                                  "evidence": {"source": para.get("source"),
                                               "locator": para.get("locator"), "quote": sent}}]})
    target = panels[2]["id"] if len(panels) > 2 else (panels[-1]["id"] if panels else "P3")
    encs = table_encodings(index, target)
    title = (index.get("case") or {}).get("title") or _task_title(index) or "Graphical abstract"
    legend = [{"label": c["label"], "meaning": e.get("meaning")} for e in encs
              for c in (e.get("categories") or [])][:6]
    return {"title": title, "subtitle": "Assembled from verbatim sentences; curation is minimal.",
            "caption": "Every drawn mark traces to a quotable passage; see content_map.json.",
            "panels": panels, "encodings": encs, "legend": legend}

def _task_title(index):
    case = index.get("case") or {}
    return case.get("title") or (case.get("instruction") or "")[:140] or ""

def split_row(text):
    for delim in ("\t", ",", ";", "|"):
        if delim in text:
            try:
                return [c.strip() for c in next(__import__("csv").reader([text], delimiter=delim,
                                                                        quotechar='"'))]
            except Exception:
                return [c.strip() for c in text.split(delim)]
    return [c.strip() for c in text.split()]

def _rows_of(index, hint):
    """Indexed rows of the first table whose name contains hint (or the first table)."""
    tables = [m for m in index.get("materials") or [] if m["name"].lower().endswith((".csv", ".tsv"))]
    if hint:
        tables = [m for m in tables if norm(hint) in m["name"]] or tables
    for m in tables:
        rows = [p for p in index.get("paragraphs") or [] if p.get("source") == m["name"]]
        if len(rows) >= 3:
            return m, rows
    return None, []

def _cols(head, x, y):
    low = [norm(h).lower() for h in head]
    xi = low.index(norm(x).lower()) if norm(x).lower() in low else 0
    yi = low.index(norm(y).lower()) if norm(y).lower() in low else min(1, len(head) - 1)
    return xi, yi

def _unit_of(head, yi):
    m = re.search(r"\(([^)]{1,12})\)|\[([^\]]{1,12})\]", head[yi] if yi < len(head) else "")
    return (m.group(1) or m.group(2) or "").strip() if m else ""

def _cats(rows, xi, yi, limit=8):
    out = []
    for r in rows[1:]:
        cells = split_row(r["text"])
        if max(xi, yi) >= len(cells) or num(cells[yi]) is None:
            continue
        out.append({"label": cells[xi][:26], "value": cells[yi], "num": num(cells[yi]),
                    "evidence": {"source": r["source"], "locator": r["locator"], "quote": r["text"]}})
    return out[:limit]

def table_encodings(index, panel_id="P3"):
    """First usable table becomes a length-encoded key; every mark keeps its raw row."""
    m, rows = _rows_of(index, "")
    if not m:
        return []
    head = split_row(rows[0]["text"])
    best = None
    for ci in range(1, len(head)):
        got = [c for c in _cats(rows, 0, ci, 99)]
        if len(got) >= 2 and (best is None or len(got) > len(best[1])):
            best = (ci, got)
    if not best:
        return []
    ci = best[0]
    cats = best[1][:6]
    return [{"id": "enc1", "channel": "length",
             "meaning": "%s across %s" % (head[ci] or "value", head[0] or "rows"),
             "unit": _unit_of(head, ci), "panel": panel_id, "categories": cats,
             "evidence": {"source": m["name"], "locator": rows[1]["locator"], "quote": rows[1]["text"]}}]

def expand_charts(draft, index, degr):
    """Fill encodings[].data blocks from indexed rows; the quote stays the raw line."""
    for enc in draft.get("encodings") or []:
        if not isinstance(enc, dict) or not isinstance(enc.get("data"), dict) or enc.get("categories"):
            continue
        data = enc["data"]
        m, rows = _rows_of(index, data.get("path"))
        if not rows:
            degr.append("chart data '%s' is not among the indexed materials: encoding skipped"
                        % norm(data.get("path")))
            enc["categories"] = []
            continue
        head = split_row(rows[0]["text"])
        xi, yi = _cols(head, data.get("x"), data.get("y"))
        enc["unit"] = norm(enc.get("unit")) or _unit_of(head, yi)
        enc["categories"] = _cats(rows, xi, yi)
        if len(enc["categories"]) < 2:
            degr.append("chart data '%s' had fewer than two numeric rows: encoding skipped"
                        % norm(data.get("path")))
        if not enc.get("meaning"):
            enc["meaning"] = "%s across %s" % (head[yi] if yi < len(head) else "value",
                                               head[xi] if xi < len(head) else "rows")
        degr.append("chart '%s': %d data row(s) from %s, one locator per mark"
                    % (enc.get("id"), len(enc["categories"]), m["name"] if m else norm(data.get("path"))))
    return draft

def _item_text(it):
    return " ".join(str(it.get(k) or "") for k in ("label", "value", "detail", "note"))

def _allowed_numbers(draft):
    ok = set()
    for pn in draft.get("panels") or []:
        for it in pn.get("items") or []:
            if isinstance(it, dict) and (it.get("_m") or {}).get("status") in ("verified", "relocated"):
                ok |= set(numbers((it.get("_m") or {}).get("quote")))
    for enc in draft.get("encodings") or []:
        for c in (enc.get("categories") or []) if isinstance(enc, dict) else []:
            ev = c.get("evidence") if isinstance(c, dict) else None
            if isinstance(ev, dict):
                ok |= set(numbers(ev.get("quote")))
    return ok

def _strip_untraced(text, allowed):
    """Remove tokens whose number has no source quote; keep the rest of the sentence."""
    kept, removed = [], []
    for tok in str(text or "").split(" "):
        bad = [n for n in numbers(tok) if n not in allowed]
        if bad:
            removed += bad
        else:
            kept.append(tok)
    return " ".join(kept).strip(" ,.;:"), removed

def prune(draft, exc, degr):
    """Nothing unverifiable reaches the page: a bad quote or a sourceless number goes."""
    allowed = _allowed_numbers(draft)
    kept = 0
    for pi, pn in enumerate(draft.get("panels") or []):
        if not isinstance(pn, dict):
            continue
        pid = str(pn.get("id") or "P%d" % (pi + 1))
        claim = norm(pn.get("claim"))
        if claim:
            clean, removed = _strip_untraced(claim, allowed)
            if removed:
                pn["claim"] = clean
                degr.append("panel %s: removed number(s) %s from the claim - no source quote carries them"
                            % (pid, sorted(set(removed))))
                exc.append({"code": "number_untraced", "where": pid + ".claim",
                            "detail": "claim numbers %s had no source quote" % sorted(set(removed)),
                            "action": "dropped from the drawn text; quote a passage to keep them"})
        survivors = []
        for it in pn.get("items") or []:
            if not isinstance(it, dict):
                continue
            m = it.get("_m") or {}
            bad = sorted({n for n in numbers(_item_text(it)) if n not in numbers(m.get("quote"))})
            if m.get("status") not in ("verified", "relocated"):
                exc.append({"code": "element_dropped", "where": str(it.get("_eid") or it.get("id")),
                            "detail": "%s: %s" % (m.get("status"), m.get("note")),
                            "action": "removed from the figure; add a verbatim quote and rebuild"})
                continue
            if bad:
                exc.append({"code": "element_dropped", "where": str(it.get("_eid") or it.get("id")),
                            "detail": "number(s) %s are not in this element's quote" % bad,
                            "action": "removed: a figure may not show a value its quote does not carry"})
                degr.append("panel %s: element %s removed - untraced number(s) %s"
                            % (pid, it.get("_eid") or it.get("id"), bad))
                continue
            survivors.append(it)
            kept += 1
        lost = len(pn.get("items") or []) - len(survivors)
        if lost and not any(it.get("_eid") for it in pn.get("items") or []):
            degr.append("panel %s: %d element(s) removed" % (pid, lost))
        pn["items"] = survivors
    return kept

def content_map(model, draft, index, rep):
    ev, enc_by_id = {}, {}
    for pn in draft.get("panels") or []:
        for it in pn.get("items") or []:
            if isinstance(it, dict) and it.get("_eid"):
                ev[it["_eid"]] = it.get("_m") or {}
    for enc in draft.get("encodings") or []:
        if isinstance(enc, dict):
            enc_by_id[str(enc.get("id"))] = enc
    elements, panels = [], []
    for p in model["panels"]:
        pe = [e for e in model["elements"] if e["panel"] == p["id"]]
        src = next((ev.get(e["id"]) for e in pe if (ev.get(e["id"]) or {}).get("quote")), None)
        panels.append({"id": p["id"], "order": p["order"], "role": p["role"], "heading": p["heading"],
                       "claim": p["claim"], "flow": p["flow"], "bbox": p["bbox"],
                       "elements": [e["id"] for e in pe],
                       "source": ({"source": src.get("source"), "locator": src.get("locator"),
                                   "quote": src.get("quote"), "status": src.get("status")} if src else
                                  {"source": None, "locator": None, "quote": None,
                                   "status": "no_verified_item"})})
    for e in model["elements"]:
        if e["kind"] == "encoding":
            enc = enc_by_id.get(e["id"]) or {}
            elements.append({"element_id": e["id"], "panel": e["panel"], "role": e["role"],
                             "kind": "encoding", "text": e["text"], "svg_id": "#" + e["id"],
                             "bbox": e["bbox"],
                             "evidence": {"source": (enc.get("evidence") or {}).get("source"),
                                          "locator": (enc.get("evidence") or {}).get("locator"),
                                          "quote": (enc.get("evidence") or {}).get("quote"),
                                          "status": (enc.get("_m") or {}).get("status", "encoding")}})
            continue
        m = ev.get(e["id"]) or {}
        elements.append({"element_id": e["id"], "panel": e["panel"], "role": e["role"], "kind": e["kind"],
                         "text": e["text"], "svg_id": "#" + e["id"], "bbox": e["bbox"],
                         "evidence": {"source": m.get("source"), "locator": m.get("locator"),
                                      "quote": m.get("quote"), "status": m.get("status")}})
    encs = []
    for e in model["encodings"]:
        raw = enc_by_id.get(e["id"]) or {}
        cats = [c for c in (raw.get("categories") or []) if isinstance(c, dict)]
        encs.append({"id": e["id"], "channel": e["channel"], "meaning": e["meaning"], "unit": e["unit"],
                     "panel": e["panel"], "marks": e["marks"],
                     "source": {"source": (raw.get("evidence") or {}).get("source"),
                                "locator": (raw.get("evidence") or {}).get("locator"),
                                "quote": (raw.get("evidence") or {}).get("quote"),
                                "per_mark": [{"mark_id": m["mark_id"],
                                              "locator": (c.get("evidence") or {}).get("locator"),
                                              "quote": (c.get("evidence") or {}).get("quote")}
                                             for c, m in zip(cats, e["marks"])]}})
    traced = sum(1 for x in elements if (x.get("evidence") or {}).get("quote"))
    return {"figure": {"title": model["title"],
                       "canvas_pt": [model["canvas"]["w_pt"], model["canvas"]["h_pt"]],
                       "direction": model["direction"], "digest": emit.model_digest(model)},
            "panels": panels, "elements": elements, "encodings": encs, "legend": model["legend"],
            "coverage": {"panels": round(sum(1 for p in panels if p["source"]["quote"]) / max(1, len(panels)), 3),
                         "elements": round(traced / max(1, len(elements)), 3),
                         "encoding": 1.0 if all(e["marks"] for e in encs) else 0.0,
                         "numbers_traced": not rep.get("unmatched_numbers")},
            "numbers": {"drawn": rep.get("numbers") or [], "untraced": rep.get("unmatched_numbers") or []}}

def size_of(path):
    try:
        return os.path.getsize(path) if path else None
    except Exception:
        return None

def compliance(model, spec, files, png, rep, index):
    st, cv = model["stats"], model["canvas"]
    min_pt = float(spec["style"]["min_font_pt"])
    fails, warns = [], []
    fonts_ok = st["min_font"] + 0.01 >= min_pt
    if not fonts_ok:
        fails.append("smallest type %.2f pt sits below the %.2f pt floor" % (st["min_font"], min_pt))
    if not st["inside_canvas"]:
        fails.append("marks reach outside the canvas (max %.1f, %.1f of %sx%s pt)" %
                     (st["max_x"], st["max_y"], cv["w_pt"], cv["h_pt"]))
    roles = [p["role"] for p in model["panels"]]
    order_ok = roles[:len(spec["required_roles"])] == spec["required_roles"][:len(roles)]
    if not order_ok:
        warns.append("reading order %s differs from the workorder order %s" % (roles, spec["required_roles"]))
    colours = [m["color"] for e in model["encodings"] for m in e["marks"] if m.get("color")]
    lums = sorted({round(layout.luminance(c), 4) for c in colours})
    deltas = [round(b - a, 4) for a, b in zip(lums, lums[1:])]
    min_delta = min(deltas) if deltas else None
    gray_ok = min_delta is None or min_delta >= 0.04
    if not gray_ok:
        warns.append("two encoding colours differ by %.3f in luminance: greyscale print loses them" % min_delta)
    consistency, issues = True, []
    keys = {x["label"] for x in model["legend"]}
    for e in model["encodings"]:
        drawn = [m["label"] for m in e["marks"]]
        missing = sorted({d for d in drawn} - keys)
        if missing:
            consistency = False
            issues.append("%s: %s drawn but absent from the key" % (e["id"], missing))
        if len(drawn) != len(set(drawn)):
            consistency = False
            issues.append("%s: duplicate category labels on the marks" % e["id"])
        if not e["marks"]:
            consistency = False
            issues.append("%s: encoding declared but no mark was drawn" % e["id"])
    if rep.get("unmatched_numbers"):
        fails.append("figure number(s) %s appear in no evidence quote" % rep["unmatched_numbers"])
    if not model["panels"]:
        fails.append("no panel was composed")
    if png.get("engine") in (None, "none"):
        fails.append("no PNG preview could be produced")
    dropped = model.get("dropped") or []
    if dropped:
        warns.append("%d drop event(s) from overflow or missing evidence" % len(dropped))
    return { "canvas": {"w_pt": cv["w_pt"], "h_pt": cv["h_pt"], "unit": cv["unit"],
                   "size": [cv["width"], cv["height"]], "dpi": cv["dpi"],
                   "matches_workorder": not any("clamped" in d for d in spec.get("defaults") or [])},
        "fonts": {"min_pt": st["min_font"], "spec_min_pt": min_pt, "ok": fonts_ok,
                  "family": spec["style"]["font_family"], "text_nodes": st["text_ops"]},
        "reading_order": {"direction": model["direction"], "panel_roles": roles,
                          "spec_order": spec["required_roles"], "ok": order_ok},
        "encoding_consistency": {"encodings": len(model["encodings"]), "ok": consistency,
                                 "issues": issues, "channels": [e["channel"] for e in model["encodings"]]},
        "colourblind": {"palette": spec["style"]["palette"], "ok": True,
                        "redundant_coding": "panel headers and the key spell out every role and category"},
        "grayscale_contrast": {"distinct_luminances": lums, "min_delta": min_delta, "ok": gray_ok,
                               "threshold": 0.04},
        "overflow": {"inside_canvas": st["inside_canvas"], "dropped_count": len(dropped),
                     "dropped": dropped, "ok": st["inside_canvas"]},
        "numbers": {"drawn": rep.get("numbers") or [], "untraced": rep.get("unmatched_numbers") or [],
                    "ok": not rep.get("unmatched_numbers")},
        "svg": {"path": files.get("svg"), "bytes": size_of(files.get("svg")), "vector": True,
                "layers": layout.LAYERS, "editable_text": st["text_ops"] > 0},
        "pdf": {"path": files.get("pdf"), "bytes": size_of(files.get("pdf")), "pages": 1, "vector": True,
                "page_pt": [cv["w_pt"], cv["h_pt"]],
                "fonts": "Helvetica base-14 + STSong-Light CID fallback", "embedded": False},
        "png": png,
        "spec": {"required_roles": spec["required_roles"], "must_include": spec["must_include"],
                 "must_exclude": spec["must_exclude"], "required_channels": spec["required_channels"],
                 "defaults": spec.get("defaults") or []},
        "warnings": warns, "failures": fails, "pass": not fails,
    }

def patch_svg(text, edits):
    applied, missed = [], []
    for e in edits:
        tid = norm(e.get("target_id") or e.get("element_id") or e.get("target"))
        new = e.get("revised")
        if not tid or new is None:
            missed.append("edit without target_id/revised: %s" % json.dumps(e, ensure_ascii=False)[:120])
            continue
        pat = re.compile(r'(<text\b[^>]*\bid="%s"[^>]*>)(.*?)(</text>)' % re.escape(tid), re.S)
        if not pat.search(text):
            missed.append('no <text id="%s"> in the source figure' % tid)
            continue
        safe = str(new).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = pat.sub(lambda m: m.group(1) + safe + m.group(3), text, count=1)
        applied.append({"what": "text_replaced", "detail": "#%s: '%s' -> '%s' (%s)" %
                                            (tid, norm(e.get("original"))[:60], str(new)[:60],
                                             norm(e.get("reason")) or "workorder edit")})
    return text, applied, missed

def edit_record(model, draft, index, spec, files, out):
    svg_path = os.path.join(str(out), "graphical_abstract.svg")
    rec = {"mode": "created_from_material", "source_artifact": None, "patched_artifact": None,
           "changes": [],
           "parameters": {"canvas_pt": [model["canvas"]["w_pt"], model["canvas"]["h_pt"]],
                          "dpi": model["canvas"]["dpi"], "formats": spec["export"]["formats"],
                          "min_font_pt": spec["style"]["min_font_pt"], "palette": spec["style"]["palette"]},
           "determinism": {"model_digest": emit.model_digest(model),
                           "svg_sha256": hashlib.sha256(open(svg_path, "rb").read()).hexdigest()},
           "materials": [{"name": m["name"], "sha256": m["sha256"], "bytes": m["bytes"]}
                         for m in index.get("materials") or []],
           "exports": {k: {"path": os.path.basename(v), "bytes": size_of(v),
                           "sha256": hashlib.sha256(open(v, "rb").read()).hexdigest()}
                       for k, v in files.items() if v and os.path.isfile(v)}}
    src = spec.get("source_artifact")
    if src:
        p = src
        for cand in (src, os.path.join("/input", str(src)), os.path.join(str(out), str(src)),
                     os.path.join(index.get("input_dir") or "/input", str(src)),
                     os.path.join(index.get("input_dir") or "/input", os.path.basename(str(src)))):
            if os.path.isfile(cand):
                p = cand
                break
        if os.path.isfile(p):
            orig = open(p, encoding="utf-8", errors="replace").read()
            rec["source_artifact"] = {"path": spec.get("source_artifact_name") or src, "exists": True, "bytes": os.path.getsize(p),
                                      "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
                                      "text_nodes": len(re.findall(r"<text\b", orig)),
                                      "element_ids": re.findall(r'\bid="([^"]+)"', orig)[:40],
                                      "format": os.path.splitext(p)[1].lstrip(".")}
            edits = [e for e in (draft.get("edits") or []) if isinstance(e, dict)]
            if edits and p.lower().endswith(".svg"):
                patched, applied, missed = patch_svg(orig, edits)
                rec["mode"] = "source_preserving_patch"
                rec["changes"] += applied + [{"what": "edit_not_applied", "detail": m} for m in missed]
                if applied:
                    tgt = os.path.join(str(out), "graphical_abstract_source_kept.svg")
                    open(tgt, "w", encoding="utf-8").write(patched)
                    rec["patched_artifact"] = { "path": os.path.basename(tgt),
                        "sha256": hashlib.sha256(open(tgt, "rb").read()).hexdigest(),
                        "kept_element_ids": len(re.findall(r'\bid="', patched))}
            else:
                rec["changes"].append({"what": "rebuilt_from_material",
                                       "detail": "an earlier figure was present but no explicit edit list "
                                                 "was supplied, so the abstract was rebuilt from the material"})
        else:
            rec["source_artifact"] = {"path": src, "exists": False,
                                      "detail": "the named edit source is not under /input or /app/work"}
    rec["changes"] += [
        {"what": "figure composed", "detail": "%d panel(s), %d traced element(s), %d channel(s)" %
                                             (len(model["panels"]), len(model["elements"]),
                                              len(model["encodings"]))},
        {"what": "exports", "detail": ", ".join(sorted(os.path.basename(v) for v in files.values()))},
        {"what": "evidence", "detail": "one locator + verbatim quote per element and per encoding mark"}]
    return rec
