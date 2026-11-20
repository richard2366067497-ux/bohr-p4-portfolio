"""core.py - input discovery, workorder spec, and the gates over draft and deliverables.

load_case/scan_materials give each passage a locator and a sha256; derive_spec turns a loosely named
workorder into canvas, roles, channels, font floor and exports, defaulting loudly; evaluate and
selfcheck decide whether claims are traceable and files are what they claim to be.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import emit
import layout

NUM = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)?(?![A-Za-z0-9])")

CONTRACT_KEYS = ("output_contract", "outputcontract", "output_schema", "contract",
                 "output_fields", "required_outputs", "deliverables")
WORKORDER_KEYS = ("organizer_workorder", "organizer_edit_workorder", "figure_workorder",
                  "workorder", "drawing_workorder", "edit_workorder")
ROLES = ("problem", "method", "results", "implication")

def norm(s):
    return " ".join(str(s if s is not None else "").split())

def dump(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""

def sha256_file(path, n=64):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()[:n] if n else h.hexdigest()
    except Exception:
        return None

def seek_key(obj, names, depth=0):
    """First value whose key matches one of names (shallow before deep)."""
    if depth > 4 or not isinstance(obj, (dict, list)):
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower().replace("-", "_").strip() in names:
                return v
        obj = list(obj.values())
    for v in obj[:25]:
        got = seek_key(v, names, depth + 1)
        if got is not None:
            return got
    return None

def num(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None

def strings(v):
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    out = []
    if isinstance(v, list):
        for x in v:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                t = x.get("label") or x.get("name") or x.get("text")
                if isinstance(t, str) and t.strip():
                    out.append(t.strip())
    return out

def load_case(ind):
    out = {"case": {}, "case_path": None, "task_text": "", "errors": [], "workorder": {}}
    ind = Path(ind)
    for fname in ("case.json", "task.md"):
        f = ind / fname
        if not f.is_file() and ind.exists():
            cands = sorted(ind.rglob(fname))
            f = cands[0] if cands else None
        if f is None or not Path(f).is_file():
            if fname == "case.json":
                out["errors"].append("case.json not found under %s" % ind)
            continue
        try:
            if fname == "case.json":
                out["case"], out["case_path"] = read_json(f), str(f)
            else:
                out["task_text"] = read_text(f)
        except Exception as exc:
            out["errors"].append("%s unreadable: %s" % (fname, str(exc).splitlines()[0][:160]))
    wo = seek_key(out["case"], WORKORDER_KEYS) if out["case"] else None
    if not isinstance(wo, dict):
        for f in sorted(ind.rglob("*workorder*.json")) if ind.exists() else []:
            try:
                cand = read_json(f)
                if isinstance(cand, dict):
                    wo = cand
                    break
            except Exception as exc:
                out["errors"].append("workorder %s unreadable: %s" % (f.name, str(exc)[:120]))
    out["workorder"] = wo if isinstance(wo, dict) else {}
    return out

def pdf_paragraphs(path, sid):
    exe = shutil.which("pdftotext")
    if not exe:
        return [], "PDF present but pdftotext is missing: read the page yourself and quote it"
    try:
        res = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, timeout=120)
        text = res.stdout.decode("utf-8", "replace")
        if text.strip():
            out = []
            for pi, page in enumerate(text.split("\f")):
                for bi, block in enumerate(re.split(r"\n\s*\n", page)):
                    if len(block.strip()) > 1:
                        out.append({"sid": sid, "locator": "p.%d b.%d" % (pi + 1, bi + 1),
                                    "text": block.strip()})
            return out, "pdftotext -layout; locator p.<page> b.<block>"
    except Exception as exc:
        return [], "PDF text extraction failed (%s): read the page yourself" % str(exc)[:100]
    return [], "PDF yielded no text: read the page yourself, never invent content"

def scan_materials(ind):
    ind = Path(ind)
    mats, paras = [], []
    files = sorted(x for x in ind.rglob("*") if x.is_file()) if ind.exists() else []
    for p in files:
        low = p.name.lower()
        if low in ("case.json", "task.md", "smoke.md") or (low.startswith("case") and low.endswith(".json")):
            continue
        if low.endswith(".json") and "workorder" in low:
            continue
        rel, sid = str(p.relative_to(ind)), "m%d" % (len(mats) + 1)
        head = p.open("rb").read(600) if p.stat().st_size else b""
        kind = "pdf" if head[:4] == b"%PDF" else ("binary" if b"\x00" in head else "text")
        rec = {"sid": sid, "name": rel, "kind": kind, "bytes": p.stat().st_size,
               "sha256": sha256_file(p, 32), "paragraphs": 0, "method": "utf-8 text"}
        got = []
        try:
            if kind == "text":
                text = p.read_text(encoding="utf-8-sig", errors="replace")
                if p.suffix.lower() in (".csv", ".tsv"):
                    rows = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                    got = [{"sid": sid, "locator": "para.%d" % i, "text": r.strip()}
                           for i, r in enumerate(rows, 1) if r.strip()]
                    rec["method"] = "csv/tsv rows; locator para.<line>, para.1 is the header"
                else:
                    got = [{"sid": sid, "locator": "para.%d" % (i + 1), "text": b.strip()}
                           for i, b in enumerate(re.split(r"\n\s*\n", text)) if len(b.strip()) > 2]
            elif kind == "pdf":
                got, rec["method"] = pdf_paragraphs(p, sid)
            else:
                rec["method"] = "binary: not parsed - convert it, never guess its content"
            for g in got:
                g["source"] = rel
        except Exception as exc:
            got, rec["method"] = [], "extraction failed: %s" % str(exc)[:120]
        rec["paragraphs"] = len(got)
        mats.append(rec)
        paras += got
    return mats, paras

def canvas_spec(wo, notes):
    box = seek_key(wo, ("canvas", "figure_size", "canvas_size", "page_size", "dimensions", "size"))
    w = h = unit = dpi = None
    if isinstance(box, dict):
        unit = str(box.get("unit") or "").lower() or None
        dpi = num(box.get("dpi"))
        for k in box:
            kl = str(k).lower()
            if kl.endswith("_mm"):
                unit = "mm"
            elif kl.endswith(("_in", "_inch")):
                unit = "in"
            elif kl.endswith("_px"):
                unit = "px"
        w = num(box.get("width") or box.get("w") or box.get("width_mm") or box.get("w_mm"))
        h = num(box.get("height") or box.get("h") or box.get("height_mm") or box.get("h_mm"))
    elif isinstance(box, (list, tuple)) and len(box) >= 2:
        w, h = num(box[0]), num(box[1])
    elif isinstance(box, str):
        nums = re.findall(r"\d+(?:[.,]\d+)?", box)
        if len(nums) >= 2:
            w, h = num(nums[0]), num(nums[1])
        low = box.lower()
        unit = "in" if re.search(r"\bin(ch|ches)?\b", low) else ("px" if "px" in low else
                                                                ("mm" if "mm" in low else None))
    if not (w and h and w > 0 and h > 0):
        w, h, unit = 180.0, 112.0, "mm"
        notes.append("canvas not specified: defaulted to 180x112 mm (single page)")
    unit = unit or "mm"
    if unit in ("in", "inch", "inches"):
        wpt, hpt = w * 72.0, h * 72.0
    elif unit in ("px", "pixel", "pixels"):
        wpt, hpt = w * 72.0 / (dpi or 300), h * 72.0 / (dpi or 300)
    elif unit == "pt":
        wpt, hpt = w, h
    else:
        wpt, hpt = w * 72.0 / 25.4, h * 72.0 / 25.4
    if wpt < 160 or hpt < 120 or wpt > 1600 or hpt > 1600:
        notes.append("canvas %gx%g %s outside the usable 160-1600 pt range: clamped to 180x112 mm"
                     % (w, h, unit))
        w, h, unit = 180.0, 112.0, "mm"
        wpt, hpt = 180 * 72 / 25.4, 112 * 72 / 25.4
    return {"width": w, "height": h, "unit": unit, "dpi": int(dpi or 300),
            "w_pt": round(wpt, 2), "h_pt": round(hpt, 2),
            "svg_attrs": ("%gmm" % (wpt / 72.0 * 25.4)) if unit == "mm" else ("%gpt" % wpt),
            "svg_attrs_h": ("%gmm" % (hpt / 72.0 * 25.4)) if unit == "mm" else ("%gpt" % hpt)}

def roles_from(wo, notes):
    req = seek_key(wo, ("required_panels", "panels", "panel_order", "sections", "narrative"))
    roles = []
    if isinstance(req, list):
        for item in req:
            r = (item.get("role") or item.get("name") or item.get("type") or item.get("title")
                 if isinstance(item, dict) else item)
            if r:
                roles.append(layout.norm_role(r))
    if not roles:
        return list(ROLES)
    for r in ROLES:
        if r not in roles:
            roles.append(r)
            notes.append("workorder named %d of the four narrative roles; %s added" %
                         (len(roles) - 1, r))
    return [r for r in ROLES if r in roles]

def derive_spec(ind, bundle, notes):
    wo, case = bundle.get("workorder") or {}, bundle.get("case") or {}
    canvas = canvas_spec(wo, notes)
    style = seek_key(wo, ("style", "typography", "visual_style")) or {}
    style = style if isinstance(style, dict) else {}
    min_pt = num(style.get("min_font_pt") or style.get("min_font_size") or
                 seek_key(wo, ("min_font_pt", "min_font_size", "min_font")))
    if not min_pt:
        min_pt = 7.0
        notes.append("minimum font size not specified: 7 pt used as the readable floor")
    export = seek_key(wo, ("export", "exports", "output_formats", "export_spec")) or {}
    export = export if isinstance(export, dict) else {}
    formats = strings(export.get("formats") or export.get("format")) or ["svg", "pdf", "png"]
    dpi = num(export.get("dpi")) or canvas["dpi"]
    enc = seek_key(wo, ("encodings", "encoding", "visual_encodings", "channels")) or []
    channels = []
    if isinstance(enc, list):
        for e in enc:
            if isinstance(e, dict) and e.get("channel"):
                channels.append(str(e["channel"]).lower())
            elif isinstance(e, str) and e.lower() in layout.CHANNELS:
                channels.append(e.lower())
    led = seek_key(wo, ("legend_requirements", "legend", "key")) or {}
    led = led if isinstance(led, dict) else {}
    spec = { "workorder_type": norm(seek_key(wo, ("workorder_type", "kind", "type")) or
                               seek_key(case, ("kind", "workorder_type")) or "graphical_abstract"),
        "canvas": canvas,
        "required_roles": roles_from(wo, notes),
        "must_include": (strings(seek_key(wo, ("must_include", "required_elements", "required_labels")))
                         + strings(seek_key(case, ("must_include", "required_elements")))),
        "must_exclude": (strings(seek_key(wo, ("must_exclude", "forbidden", "exclude"))) +
                         strings(seek_key(case, ("must_exclude", "forbidden")))),
        "required_channels": sorted(set(channels)),
        "style": {"min_font_pt": float(min_pt),
                  "font_family": style.get("font_family") or "Helvetica/Arial/Noto Sans",
                  "palette": style.get("palette") or "Okabe-Ito subset",
                  "colorblind_safe": bool(style.get("colorblind_safe", True)),
                  "grayscale_safe": bool(style.get("grayscale_safe", True))},
        "legend": {"max_items": int(num(led.get("max_items")) or 8),
                   "require_units": bool(led.get("require_units", True))},
        "export": {"formats": formats, "dpi": int(dpi),
                   "color_space": export.get("color_space") or "RGB"},
        "source_artifact": None,
        "defaults": notes,
    }
    src = seek_key(wo, ("source_artifact", "source_figure", "edit_source", "original_figure"))
    if isinstance(src, str) and src.strip():
        spec["source_artifact"] = src.strip()
    else:
        svgs = sorted(Path(ind).rglob("*.svg")) if Path(ind).exists() else []
        if svgs:
            spec["source_artifact"] = str(svgs[0])
            spec["source_artifact_name"] = str(svgs[0].relative_to(ind))
            notes.append("workorder named no edit source; existing %s treated as the edit source"
                         % svgs[0].name)
    return spec

def build_index(ind, work, errs):
    bundle = load_case(ind)
    errs.extend(bundle["errors"])
    mats, paras = scan_materials(ind)
    notes = []
    spec = derive_spec(ind, bundle, notes)
    case = bundle["case"] if isinstance(bundle["case"], dict) else {}
    cid = None
    for k in ("case_id", "caseId", "case_name", "id", "name"):
        if isinstance(case.get(k), (str, int)) and str(case.get(k)).strip():
            cid = str(case.get(k)).strip()
            break
    cid = cid or (Path(bundle["case_path"]).stem if bundle["case_path"] else None) or Path(ind).name or None
    if cid and not bundle["case_path"]:
        notes.append("case.json missing/unreadable: case_id taken from the input directory name")
    contract = seek_key(case, CONTRACT_KEYS)
    if isinstance(contract, list):
        contract = {str(k): None for k in contract}
    elif not isinstance(contract, dict):
        contract = {}
        errs.append("output_contract not found in case.json: result.json carries only the envelope")
    index = {
        "case_id": cid, "input_errors": list(errs), "input_dir": str(Path(ind).resolve()), "case_path": bundle["case_path"],
        "case": {"title": norm(seek_key(case, ("title", "case_title")))[:200],
                 "domain": norm(seek_key(case, ("domain", "field", "discipline")))[:80],
                 "instruction": norm(seek_key(case, ("task_instruction", "instruction", "prompt")))[:1200]},
        "contract": contract, "spec": spec, "materials": mats, "paragraphs": paras,
        "workorder_found": bool(bundle["workorder"]), "notes": notes,
        "input_error": bool(errs),
    }
    dump(Path(work) / "index.json", index)
    dump(Path(work) / "spec.json", spec)
    return index

def prepare_index(ind, work, errs):
    """Reuse an index only while it still carries passages and a spec."""
    work = Path(work)
    cached = None
    if (work / "index.json").is_file():
        try:
            cached = read_json(work / "index.json")
        except Exception as exc:
            errs.append("work/index.json unreadable, rebuilding: %s" % str(exc)[:100])
    if isinstance(cached, dict) and cached.get("spec") and isinstance(cached.get("paragraphs"), list):
        return cached
    return build_index(ind, work, errs)

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = (s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"')
         .replace("\u201d", '"').replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-"))
    return re.sub(r"\s+", " ", s).strip()

def loose(s):
    return re.sub(r"[\s\u00ad]+", "", norm(s)).lower()

def numbers(s):
    """Data values only: digits inside a token (SLC26A9, E203Q) are names."""
    return [x.replace(",", ".") for x in NUM.findall(norm(s))]

def match_quote(ev, paras):
    """Verbatim check: the sentence is the evidence, the locator is its address."""
    ev = ev if isinstance(ev, dict) else {}
    q, dec, src = norm(ev.get("quote")), norm(ev.get("locator")), norm(ev.get("source"))
    if len(q) < 4:
        return {"status": "no_quote", "locator": dec, "source": src, "quote": q,
                "note": "quote missing or shorter than 4 characters"}
    pool = paras
    if src:
        same = [p for p in paras if src in (norm(p.get("source")), norm(p.get("sid")))]
        pool = same or paras
    cands = [p for p in pool if loose(q) in loose(p.get("text"))]
    if not cands:
        return {"status": "unverified", "locator": dec, "source": src, "quote": q,
                "note": "no indexed passage contains this text character for character"}
    for p in cands:
        if dec and dec == norm(p.get("locator")):
            return {"status": "verified", "locator": p.get("locator"), "source": p.get("source"),
                    "quote": q, "note": ""}
    p = cands[0]
    return {"status": "relocated" if dec else "verified", "locator": p.get("locator"),
            "source": p.get("source"), "quote": q,
            "note": "" if not dec else "locator '%s' did not hold the quote; corrected to '%s'"
            % (dec, p.get("locator"))}

def _item_text(it):
    return " ".join(str(it.get(k) or "") for k in ("label", "value", "detail", "note"))

def evaluate(draft, paras, spec):
    rep = {"problems": [], "warnings": [], "items": 0, "verified": 0, "roles": [],
           "encodings": 0, "numbers": [], "unmatched_numbers": [], "claims": 0}
    panels = [p for p in (draft.get("panels") or []) if isinstance(p, dict)]
    seen, quotes, drawn = [], [], []
    for pi, pn in enumerate(panels):
        pid = str(pn.get("id") or "P%d" % (pi + 1))
        seen.append(layout.norm_role(pn.get("role") or pn.get("heading")))
        claim = norm(pn.get("claim"))
        if len(claim) < 12:
            rep["problems"].append("%s: claim missing or too short (>=12 chars): say what this panel must convey" % pid)
        else:
            rep["claims"] += 1
            drawn += numbers(claim)
        items = [i for i in (pn.get("items") or []) if isinstance(i, dict)]
        if not items:
            rep["problems"].append("%s: no items - each panel needs one evidenced element" % pid)
        if len(items) > 3:
            rep["warnings"].append("%s: %d items; one to three reads better" % (pid, len(items)))
        for ii, it in enumerate(items):
            rep["items"] += 1
            eid = it["_eid"] = str(it.get("id") or "%s-I%d" % (pid, ii + 1))
            m = it["_m"] = match_quote(it.get("evidence"), paras)
            if m["status"] in ("verified", "relocated"):
                rep["verified"] += 1
                quotes.append(m["quote"])
            else:
                rep["problems"].append("%s: %s - %s" % (eid, m["status"], m["note"]))
            bad = sorted({x for x in numbers(_item_text(it)) if x not in numbers(m.get("quote"))})
            if bad:
                rep["problems"].append("%s: number(s) %s not in its quote" % (eid, bad))
            drawn += numbers(_item_text(it))
    for role in (spec.get("required_roles") or ROLES):
        if role not in seen:
            rep["problems"].append("missing panel role: %s (problem -> method -> results -> implication)"
                                   % role)
    rep["roles"] = sorted(set(seen))
    if not 2 <= len(panels) <= 4:
        rep["warnings"].append("panel count %d is outside the 2-4 that fits a page" % len(panels))
    if not norm(draft.get("title")):
        rep["problems"].append("title is empty")

    legend = [x for x in (draft.get("legend") or []) if isinstance(x, dict)]
    labels = {loose(x.get("label")) for x in legend if norm(x.get("label"))}
    channels = []
    for i, enc in enumerate([x for x in (draft.get("encodings") or []) if isinstance(x, dict)]):
        eid = str(enc.get("id") or "enc%d" % (i + 1))
        rep["encodings"] += 1
        ch = str(enc.get("channel") or "").lower()
        channels.append(ch)
        if ch not in layout.CHANNELS:
            rep["problems"].append("%s: channel '%s' is not one of %s" % (eid, ch, list(layout.CHANNELS)))
        if len(norm(enc.get("meaning"))) < 6:
            rep["problems"].append("%s: meaning missing - say what the channel encodes" % eid)
        cats = [c for c in (enc.get("categories") or []) if isinstance(c, dict)]
        if len(cats) < 2:
            rep["problems"].append("%s: needs >=2 categories to be a decoding key" % eid)
        vals, per = [], []
        for c in cats:
            lab = norm(c.get("label"))
            if not lab:
                rep["problems"].append("%s: a category has no label" % eid)
                continue
            if legend and loose(lab) not in labels:
                rep["warnings"].append("%s: category '%s' is not restated in the legend" % (eid, lab))
            vals += numbers(c.get("value"))
            if isinstance(c.get("evidence"), dict):
                per.append((c, match_quote(c.get("evidence"), paras)))
        numeric = vals or any(isinstance(c.get("num"), (int, float)) for c in cats)
        if numeric:
            if per:
                bad_all = []
                for c, m in per:
                    if m["status"] not in ("verified", "relocated"):
                        rep["problems"].append("%s: category '%s' - %s" % (eid, norm(c.get("label")), m["note"]))
                    else:
                        quotes.append(m["quote"])
                        bad_all += [x for x in numbers(c.get("value")) if x not in numbers(m["quote"])]
                if bad_all:
                    rep["problems"].append("%s: encoded value(s) %s are not in their own data row" %
                                           (eid, sorted(set(bad_all))))
                enc["_m"] = per[0][1]
            else:
                m = enc["_m"] = match_quote(enc.get("evidence"), paras)
                if m["status"] not in ("verified", "relocated"):
                    rep["problems"].append("%s: encoded values need a verbatim data source - %s" % (eid, m["note"]))
                else:
                    quotes.append(m["quote"])
                    bad = sorted({x for x in vals if x not in numbers(m["quote"])})
                    if bad:
                        rep["problems"].append("%s: encoded value(s) %s are not in the data quote" % (eid, bad))
        else:
            rep["warnings"].append("%s: categories carry no numbers - a qualitative key cannot drive a "
                                   "length or area channel" % eid)
        if ch in ("length", "area") and not any(isinstance(c.get("num"), (int, float)) for c in cats):
            rep["problems"].append("%s: a %s channel needs one numeric value per category" % (eid, ch))
        drawn += vals
    for ch in spec.get("required_channels") or []:
        if ch not in channels:
            rep["problems"].append("workorder requires a '%s' encoding; none was declared" % ch)

    allowed = set(numbers(" ".join(quotes)))
    rep["numbers"] = sorted(set(drawn))
    rep["unmatched_numbers"] = sorted({n for n in drawn if n not in allowed})
    if rep["unmatched_numbers"]:
        rep["problems"].append("figure number(s) %s in no evidence quote" % rep["unmatched_numbers"])

    figure_text = norm(" ".join([draft.get("title") or "", draft.get("subtitle") or "",
                                 draft.get("caption") or ""] +
                                [str(p.get("heading") or "") + " " + str(p.get("claim") or "") for p in panels] +
                                [_item_text(i) for p in panels for i in (p.get("items") or [])
                                 if isinstance(i, dict)] +
                                [str(x.get("label") or "") + " " + str(x.get("meaning") or "")
                                 for x in legend])).lower()
    for token in spec.get("must_include") or []:
        if norm(token) and norm(token).lower() not in figure_text:
            rep["problems"].append("must_include not covered: %s" % token)
    for token in spec.get("must_exclude") or []:
        if norm(token) and norm(token).lower() in figure_text:
            rep["problems"].append("must_exclude violated: %s" % token)
    rep["ok"] = not rep["problems"]
    rep["coverage"] = round(rep["verified"] / rep["items"], 3) if rep["items"] else 0.0
    return rep

def selfcheck(outdir, index):
    res = {"checks": [], "pass": True}

    def add(cid, ok, detail, blocking=True):
        res["checks"].append({"id": cid, "ok": bool(ok), "detail": detail, "blocking": blocking})
        if blocking and not ok:
            res["pass"] = False

    def read(name):
        p = os.path.join(outdir, name)
        try:
            return json.loads(open(p, encoding="utf-8").read())
        except Exception:
            return None

    res_j = read("result.json")
    add("result_json", res_j is not None, "result.json parses")
    contract = (index or {}).get("contract") or {}
    if res_j is not None:
        missing = [k for k in contract if k not in res_j]
        add("contract_keys", not missing, "missing: %s" % missing if missing else
            "all %d contract key(s) present" % len(contract))
        add("case_id", bool(res_j.get("case_id")), "case_id=%r" % res_j.get("case_id"))
        add("status", res_j.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"),
            "status=%r" % res_j.get("status"))
    svg = os.path.join(outdir, "graphical_abstract.svg")
    rep = emit.svg_layer_report(open(svg, encoding="utf-8").read()) if os.path.isfile(svg) else {}
    add("svg_parses", rep.get("parsed"), "SVG parses as XML")
    add("svg_layers", rep.get("parsed") and not rep.get("missing_layers"), "layers=%s" % rep.get("layers"))
    add("svg_text_editable", rep.get("text_nodes", 0) > 0, "text nodes=%s" % rep.get("text_nodes"))
    model = read("figure_model.json")
    add("figure_model", isinstance(model, dict) and bool(model.get("ops")), "geometry present")
    if isinstance(model, dict) and model.get("ops") and os.path.isfile(svg):
        again = hashlib.sha256(emit.to_svg(model).encode("utf-8")).hexdigest()
        add("svg_deterministic", again == hashlib.sha256(open(svg, "rb").read()).hexdigest(),
            "re-emitting figure_model.json reproduces the SVG byte for byte")
    pdf = emit.pdf_report(os.path.join(outdir, "graphical_abstract.pdf"))
    add("pdf_valid", bool(pdf.get("valid")) and bool(pdf.get("ends_with_eof")),
        "header/EOF ok, bytes=%s" % pdf.get("bytes"))
    add("pdf_single_page", pdf.get("pages") == 1, "pages=%s" % pdf.get("pages"))
    png = os.path.join(outdir, "graphical_abstract.png")
    dims = emit._png_dims(png)
    add("png_present", dims is not None, "IHDR reads, dims=%s" % dims)
    if dims and isinstance(model, dict):
        cv = model.get("canvas") or {}
        exp = [round(cv.get("w_pt", 0) / 72.0 * (cv.get("dpi") or 300)),
               round(cv.get("h_pt", 0) / 72.0 * (cv.get("dpi") or 300))]
        add("png_dims", abs(dims[0] - exp[0]) <= max(8, exp[0] * 0.02) and
            abs(dims[1] - exp[1]) <= max(8, exp[1] * 0.02), "png=%s expected~%s" % (dims, exp),
            blocking=False)
        pr = emit.probe(model, png)
        add("png_pixels", pr.get("decoded") and not pr.get("blank"),
            "decoded=%s colour cells=%s (%s)" % (pr.get("decoded"), pr.get("distinct_colours"),
                                                 pr.get("error", "ok")))
        empty = [x["panel"] for x in pr.get("panels") or [] if not x.get("drawn")]
        add("panel_ink", not empty, "no ink in: %s" % empty if empty else "every panel region is drawn")
    cmap = read("content_map.json")
    add("content_map", isinstance(cmap, dict), "content_map.json parses")
    if isinstance(cmap, dict):
        panels = cmap.get("panels") or []
        add("content_map_panels", len(panels) >= 2, "%d panel(s) mapped" % len(panels))
        add("content_map_claims", all(x.get("claim") for x in panels),
            "panels without claim: %s" % [x.get("id") for x in panels if not x.get("claim")])
        filled = [x.get("id") for x in panels if x.get("elements")]
        quoted = [x.get("id") for x in panels if x.get("elements") and (x.get("source") or {}).get("quote")]
        add("content_map_sources", sorted(filled) == sorted(quoted),
            "with elements %s, with quoted source %s" % (filled, quoted))
        empty = [x.get("id") for x in panels if not x.get("elements")]
        if empty:
            add("placeholder_panels", False, "left as placeholder: %s" % empty, blocking=False)
        els = cmap.get("elements") or []
        bad = [e.get("element_id") for e in els if not (e.get("evidence") or {}).get("quote")]
        add("content_map_elements", bool(els) and not bad, "%d element(s); no quote: %s" %
            (len(els), bad[:6]))
        add("coverage", float((cmap.get("coverage") or {}).get("elements", 0) or 0) >= 0.99,
            "coverage=%s" % (cmap.get("coverage") or {}), blocking=False)
    comp = read("compliance_checks.json")
    add("compliance", isinstance(comp, dict) and "pass" in comp, "compliance_checks.json present")
    if isinstance(comp, dict):
        add("compliance_pass", comp.get("pass") is True,
            "failures: %s" % (comp.get("failures") or [])[:6], blocking=False)
    add("edit_record", os.path.isfile(os.path.join(outdir, "edit_record.json")), "edit_record.json present")
    return res
