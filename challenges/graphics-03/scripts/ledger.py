"""Data layer for mechanism-figure-ledger: workorder parsing, verbatim evidence,
draft normalization, coverage, content map, mechanical audit. No file rendering."""
import hashlib
import json
import re
import time
from pathlib import Path

ENUM_REL = {"activation", "inhibition", "binding", "modification", "transport",
            "recruitment", "indirect", "unspecified"}
ENUM_ENT = {"gene", "protein", "complex", "ligand", "receptor", "cell_type",
            "compartment", "metabolite", "mirna", "phenotype", "unspecified"}
ENUM_CHANNEL = {"color", "line_width", "size", "shape", "line_style", "marker"}

ENT_KEYS = ("required_entities", "required_elements", "entities", "elements", "objects", "nodes")
REL_KEYS = ("required_relations", "required_edges", "relations", "edges", "interactions", "links")
COMP_KEYS = ("compartments", "required_compartments", "zones", "regions")
LEG_KEYS = ("legend_encodings", "legend", "encodings", "data_encoding", "mappings")

VERBS = (
    (("activat", "promot", "induc", "upregulat", "stimulat", "enhanc", "driv",
      "激活", "促进", "上调", "诱导", "增强", "启动"), "activation"),
    (("inhibit", "suppress", "repress", "block", "downregulat", "reduc", "attenuat", "restrain",
      "抑制", "下调", "阻断", "阻遏", "负反馈", "减弱"), "inhibition"),
    (("bind", "bound", "interact", "dimeriz", "结合", "互作", "相互作用"), "binding"),
    (("phosphorylat", "ubiquitin", "acetyl", "methylat", "sumoylat", "cleav",
      "磷酸化", "泛素化", "乙酰化", "甲基化", "切割"), "modification"),
    (("translocat", "transport", "export", "import", "secrete", "internaliz",
      "转运", "转位", "入核", "出核", "分泌", "内吞"), "transport"),
    (("recruit", "assembl", "募集", "组装", "形成复合物"), "recruitment"),
)

ZONES = [{"id": "extracellular", "label": "Extracellular space", "order": 0},
         {"id": "membrane", "label": "Plasma membrane", "order": 1, "kind": "membrane"},
         {"id": "cytoplasm", "label": "Cytoplasm", "order": 2},
         {"id": "nucleus", "label": "Nucleus", "order": 3},
         {"id": "other", "label": "Other / unspecified", "order": 9}]
ZALIAS = {"extracellular space": "extracellular", "extracellular": "extracellular", "secreted": "extracellular",
          "lumen": "extracellular", "胞外": "extracellular", "细胞外": "extracellular",
          "plasma membrane": "membrane", "membrane": "membrane", "cell membrane": "membrane",
          "surface": "membrane", "膜": "membrane", "细胞膜": "membrane", "质膜": "membrane",
          "cytoplasm": "cytoplasm", "cytosol": "cytoplasm", "cytosolic": "cytoplasm",
          "胞质": "cytoplasm", "胞内": "cytoplasm", "细胞质": "cytoplasm",
          "nucleus": "nucleus", "nuclear": "nucleus", "chromatin": "nucleus",
          "细胞核": "nucleus", "核内": "nucleus"}
ZK = (("extracellular", ("extracellular", "secreted", "lumen", "培养基", "胞外", "细胞外")),
      ("membrane", ("membrane", "receptor", "surface", "膜", "细胞膜", "质膜")),
      ("nucleus", ("nucleus", "nuclear", "chromatin", "细胞核", "核内")),
      ("cytoplasm", ("cytoplasm", "cytosol", "胞质", "胞内", "细胞质")))

WS = re.compile(r"\s+")
PUNCT = re.compile(r"[\s\u3000,.;:!?，。；：！？、（）()\[\]{}\"'“”‘’—–\-_/\\|<>]+")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def jread(path):
    p = Path(path)
    if not p.is_file():
        return None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return json.loads(p.read_text(encoding=enc))
        except Exception:
            continue
    return None


def jwrite(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def sha256(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def nw(t):
    return WS.sub(" ", str(t or "")).strip()


def sq(t):
    return PUNCT.sub("", str(t or "")).lower()


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", str(t or "").lower()).strip("-") or "x"


def key(t):
    return re.sub(r"[^a-z0-9]", "", str(t or "").lower())


def dig(obj, keys, depth=0):
    """First value whose key matches one of `keys`, shallow-first, bounded depth."""
    if depth > 4 or not isinstance(obj, (dict, list)):
        return None
    if isinstance(obj, dict):
        low = {key(k): v for k, v in obj.items()}
        for k in keys:
            if key(k) in low and low[key(k)] not in (None, "", [], {}):
                return low[key(k)]
        for v in obj.values():
            r = dig(v, keys, depth + 1)
            if r is not None:
                return r
    else:
        for v in obj:
            r = dig(v, keys, depth + 1)
            if r is not None:
                return r
    return None


# --------------------------------------------------------------- workorder
def ename(e):
    if isinstance(e, str):
        return nw(e)
    if isinstance(e, dict):
        for k in ("name", "label", "id", "entity", "symbol", "gene", "protein", "target"):
            v = e.get(k)
            if isinstance(v, str) and v.strip():
                return nw(v)
    return ""


def etype(e):
    if isinstance(e, dict):
        for k in ("type", "entity_type", "kind", "category", "role", "class"):
            v = e.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().lower().replace(" ", "_")
    return ""


def ecomp(e):
    if isinstance(e, dict):
        for k in ("compartment", "zone", "location", "region", "localization"):
            v = e.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def nm(v):
    return nw(v) if isinstance(v, str) else (ename(v) if isinstance(v, dict) else "")


def rsrc(r):
    if isinstance(r, dict):
        for k in ("from", "source", "subject", "src", "upstream", "regulator"):
            if r.get(k) not in (None, ""):
                return nm(r.get(k))
    return ""


def rdst(r):
    if isinstance(r, dict):
        for k in ("to", "target", "object", "dst", "downstream", "regulated"):
            if r.get(k) not in (None, ""):
                return nm(r.get(k))
    return ""


def rtype(r):
    if isinstance(r, dict):
        for k in ("relation_type", "type", "relation", "interaction", "semantics", "effect", "mode"):
            v = r.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().lower().replace(" ", "_")
    return ""


def rtext(r):
    if isinstance(r, str):
        return nw(r)
    if not isinstance(r, dict):
        return ""
    a, b = rsrc(r), rdst(r)
    return "%s %s %s" % (a, rtype(r) or "relates", b) if (a and b) else ""


def workorder(case):
    wo = dig(case, ["organizer_workorder", "organizerworkorder", "workorder", "figure_workorder",
                    "figureworkorder", "drawing_order", "drawingorder", "order"])
    return wo if isinstance(wo, dict) else {}


def req(wo, keys):
    v = dig(wo, list(keys))
    if isinstance(v, list):
        return [x for x in v if x not in (None, "")]
    if isinstance(v, dict):
        out = []
        for k, val in v.items():
            if isinstance(val, dict):
                out.append(dict(val, name=val.get("name", k)))
            else:
                out.append({"name": str(k)} if not isinstance(val, str) else {"name": val or k})
        return out
    return []


def cid_of(case):
    if not isinstance(case, dict):
        return None
    v = dig(case, ["case_id", "caseid", "id"], 0)
    return v if isinstance(v, (str, int)) else None


def cnames(case):
    """Declared output_contract field names, from list / dict / list-of-dicts / string."""
    oc = dig(case, ["output_contract", "outputcontract", "output_fields", "required_fields"])
    if isinstance(oc, dict):
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list):
        out = []
        for x in oc:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for k in ("name", "field", "key", "id"):
                    if isinstance(x.get(k), str):
                        out.append(x[k])
                        break
        return out
    if isinstance(oc, str):
        return [s.strip() for s in re.split(r"[,\n;]+", oc) if s.strip()]
    return []


# ------------------------------------------------------------------ verify
def verify(corpus, quote, locator=None):
    """(status, locator): verbatim > verbatim_loose > declared. Nothing is invented."""
    q = nw(quote)
    if q and locator:
        for b in corpus:
            if b.get("declared") and b["locator"] == locator:
                return "declared", locator
    if len(q) < 6:
        return None, None
    for b in corpus:
        if not b.get("declared") and q in b["text"]:
            return "verbatim", b["locator"]
    s = sq(q)
    if len(s) >= 6:
        for b in corpus:
            if not b.get("declared") and s in sq(b["text"]):
                return "verbatim_loose", b["locator"]
    if locator:
        for b in corpus:
            if b.get("declared") and b["locator"] == locator:
                return "declared", locator
    return None, None


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?。！？；;])\s*|\n+", text) if nw(s)]


def verb_hits(sentence):
    low = sentence.lower()
    hits = []
    for words, rt in VERBS:
        for w in words:
            i = low.find(w.lower())
            if i >= 0:
                hits.append((i, rt, w))
                break
    return hits


def direction_scan(corpus, a, b):
    """Material sentences naming both entities, with who-acts-on-whom as `a>b` / `b>a`."""
    out = []
    if not (a and b):
        return out
    na, nb = nw(a).lower(), nw(b).lower()
    for blk in corpus:
        if blk.get("declared"):
            continue
        low = blk["text"].lower()
        if na not in low or nb not in low:
            continue
        for st in sentences(blk["text"]):
            s = st.lower()
            ia, ib = s.find(na), s.find(nb)
            if ia < 0 or ib < 0:
                continue
            hits = verb_hits(st)
            if not hits:
                continue
            if re.search(re.escape(nb) + r"\s*(is|was|are|were|be)\b[^.]{0,40}?\bby\b\s*" + re.escape(na), s):
                out.append(("b>a", "passive", blk["locator"], nw(st)))
            elif re.search(re.escape(na) + r".{0,4}被.{0,16}" + re.escape(nb), s):
                out.append(("b>a", "passive-zh", blk["locator"], nw(st)))
            else:
                vi = min(h[0] for h in hits)
                if ia < vi < ib:
                    out.append(("a>b", "order", blk["locator"], nw(st)))
                elif ib < vi < ia:
                    out.append(("b>a", "order", blk["locator"], nw(st)))
    return out


# ------------------------------------------------------------------- draft
def zone_id(name):
    t = nw(name).lower()
    if t in ZALIAS:
        return ZALIAS[t]
    for zid, kws in ZK:
        if any(k in t for k in kws):
            return zid
    return "cytoplasm"


def guess_zone(text, hint=""):
    t = (nw(text) + " " + nw(hint)).lower()
    for zid, kws in ZK:
        if any(k in t for k in kws):
            return zid
    return "cytoplasm"


def first_str(d, keys, default=""):
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return nw(v)
    return default


def load_draft(work, out=None):
    cands = [Path(work) / "draft.json", Path(work) / "plan.json"]
    if out:
        cands.append(Path(out) / "draft.json")
    for p in cands:
        if p.is_file():
            obj = jread(p)
            if isinstance(obj, dict) and (obj.get("entities") or obj.get("relations")):
                return obj, str(p), None
            if isinstance(obj, dict):
                return None, str(p), "draft present but has no entities/relations"
    return None, None, "draft.json not found"


def norm_draft(d, corp, degradations):
    """Agent draft -> normalized model with per-item evidence status."""
    comps = []
    for i, c in enumerate(d.get("compartments") or []):
        if isinstance(c, str):
            comps.append({"id": slug(c), "label": nw(c), "order": float(i)})
        elif isinstance(c, dict):
            label = first_str(c, ("label", "name", "id"), "zone%d" % (i + 1))
            cid = first_str(c, ("id",), slug(label))
            try:
                order = float(c.get("order", i))
            except Exception:
                order = float(i)
            item = {"id": cid, "label": label, "order": order}
            if cid == "membrane" or "membrane" in label.lower() or "膜" in label:
                item["kind"] = "membrane"
            comps.append(item)
    if not comps:
        comps = [dict(z) for z in ZONES]
        degradations.append("draft declared no compartments; default 4 lanes used")
    ids = {c["id"] for c in comps}

    ents, byname = [], {}
    for e in (d.get("entities") or []):
        if not isinstance(e, dict):
            continue
        name = first_str(e, ("name", "label", "symbol", "id"))
        if not name:
            continue
        eid = first_str(e, ("id",), slug(name))
        et = first_str(e, ("entity_type", "type", "kind"), "unspecified").lower().replace(" ", "_")
        if et not in ENUM_ENT:
            et = "unspecified"
        comp = first_str(e, ("compartment", "zone", "location"))
        comp = zone_id(comp) if comp else guess_zone(name + " " + first_str(e, ("sublabel",)), et)
        if comp not in ids:
            comps.append({"id": comp, "label": comp.replace("_", " ").title(),
                          "order": max([c["order"] for c in comps] or [0.0]) + 1})
            ids.add(comp)
        src = e.get("source") if isinstance(e.get("source"), dict) else {}
        quote = nw(src.get("quote") or e.get("quote") or "")
        loc = nw(src.get("locator") or e.get("locator") or "")
        status, hit = verify(corp, quote, loc)
        ents.append({"id": eid, "name": name, "label": first_str(e, ("label",), name),
                     "type": et, "species": first_str(e, ("species", "organism")),
                     "compartment": comp, "italic": bool(e.get("italic")) or et == "gene",
                     "sublabel": first_str(e, ("sublabel", "note", "detail")),
                     "quote": quote, "locator": hit or loc, "status": status, "declared_locator": loc})
        byname[sq(name)] = eid
        byname[sq(eid)] = eid

    rels, seen = [], set()
    for i, r in enumerate(d.get("relations") or []):
        if not isinstance(r, dict):
            continue
        fa = byname.get(sq(first_str(r, ("from", "source", "subject", "src"))))
        fb = byname.get(sq(first_str(r, ("to", "target", "object", "dst"))))
        if not (fa and fb):
            degradations.append("relation %d dropped: endpoint is not an entity id (%s -> %s)" % (
                i + 1, first_str(r, ("from", "source")), first_str(r, ("to", "target"))))
            continue
        rt = first_str(r, ("relation_type", "type", "relation", "semantics"),
                       "unspecified").lower().replace(" ", "_")
        if rt not in ENUM_REL:
            degradations.append("relation %s: unknown relation_type '%s' -> unspecified" % (i + 1, rt))
            rt = "unspecified"
        src = r.get("source") if isinstance(r.get("source"), dict) else {}
        quote = nw(src.get("quote") or r.get("quote") or "")
        loc = nw(src.get("locator") or r.get("locator") or "")
        status, hit = verify(corp, quote, loc)
        if (fa, fb, rt) in seen:
            continue
        seen.add((fa, fb, rt))
        rels.append({"id": first_str(r, ("id",), "r%d" % (i + 1)), "from": fa, "to": fb, "type": rt,
                     "label": first_str(r, ("label", "verb")),
                     "direction": first_str(r, ("direction",), "forward"),
                     "strength": first_str(r, ("evidence_strength", "strength", "confidence"), "stated"),
                     "badge": first_str(r, ("badge",)), "quote": quote, "locator": hit or loc,
                     "status": status, "declared_locator": loc})

    legend = []
    for i, l in enumerate(d.get("legend") or []):
        if not isinstance(l, dict):
            continue
        ch = first_str(l, ("channel", "encoding"), "color").lower().replace(" ", "_")
        if ch not in ENUM_CHANNEL:
            degradations.append("legend %d: unknown channel '%s' ignored" % (i + 1, ch))
            continue
        src = l.get("source") if isinstance(l.get("source"), dict) else {}
        quote = nw(src.get("quote") or l.get("quote") or "")
        loc = nw(src.get("locator") or l.get("locator") or "")
        status, hit = verify(corp, quote, loc)
        mapping = l.get("mapping") if isinstance(l.get("mapping"), dict) else {}
        legend.append({"channel": ch, "meaning": first_str(l, ("meaning", "label", "description")),
                       "mapping": {str(k): str(v) for k, v in mapping.items()},
                       "source_column": first_str(l, ("source_column", "column", "field")),
                       "quote": quote, "locator": hit or loc, "status": status})

    vals = []
    for v in d.get("data_values") or []:
        if not isinstance(v, dict):
            continue
        src = v.get("source") if isinstance(v.get("source"), dict) else {}
        quote = nw(src.get("quote") or v.get("quote") or "")
        loc = nw(src.get("locator") or v.get("locator") or "")
        status, hit = verify(corp, quote, loc)
        try:
            num = float(v.get("value"))
        except Exception:
            num = None
        vals.append({"entity": sq(first_str(v, ("entity", "id", "name"))),
                     "metric": first_str(v, ("metric", "measure")), "value": num,
                     "unit": first_str(v, ("unit",)), "quote": quote,
                     "locator": hit or loc, "status": status})

    return {"title": first_str(d, ("title",), "Biological mechanism figure"),
            "subtitle": first_str(d, ("subtitle", "caption")),
            "compartments": sorted(comps, key=lambda c: (c.get("order", 0), c["id"])),
            "entities": ents, "relations": rels, "legend": legend, "data_values": vals,
            "edits": [x for x in (d.get("edits") or []) if isinstance(x, dict)],
            "gaps": [nw(g) for g in (d.get("gaps") or []) if nw(g)]}, byname


# ---------------------------------------------------------------- coverage
def coverage_of(wo, model, byname):
    want_e = [ename(e) for e in req(wo, ENT_KEYS) if ename(e)]
    want_r = [(rsrc(r), rdst(r)) for r in req(wo, REL_KEYS) if rsrc(r) and rdst(r)]
    got_e = {sq(e["name"]) for e in model["entities"]}
    got_r = {(e["from"], e["to"]) for e in model["relations"]}
    miss_e = [n for n in want_e if sq(n) not in got_e]
    miss_r = ["%s->%s" % (a, b) for a, b in want_r
              if (byname.get(sq(a)), byname.get(sq(b))) not in got_r]
    tot = len(want_e) + len(want_r)
    hit = (len(want_e) - len(miss_e)) + (len(want_r) - len(miss_r))
    return {"workorder_entities": {"declared": len(want_e), "covered": len(want_e) - len(miss_e),
                                   "missing": miss_e},
            "workorder_relations": {"declared": len(want_r), "covered": len(want_r) - len(miss_r),
                                    "missing": miss_r},
            "ratio": round(hit / float(tot), 4) if tot else None,
            "drawn_entities": len(model["entities"]), "drawn_relations": len(model["relations"])}


def build_content_map(model, coverage, pending):
    return {
        "entities": [{"svg_id": "ent-" + e["id"], "id": e["id"], "name": e["name"],
                      "entity_type": e["type"], "species": e.get("species", ""),
                      "compartment": e["compartment"], "italic_required": bool(e["italic"]),
                      "source": {"locator": e.get("locator"), "quote": e.get("quote")},
                      "quote_status": e.get("status")} for e in model["entities"]],
        "relations": [{"svg_id": "rel-" + r["id"], "id": r["id"], "from": r["from"], "to": r["to"],
                       "relation_type": r["type"], "direction": r.get("direction", "forward"),
                       "evidence_strength": r.get("strength", "stated"),
                       "source": {"locator": r.get("locator"), "quote": r.get("quote")},
                       "quote_status": r.get("status")} for r in model["relations"]],
        "compartments": [{"id": c["id"], "label": c["label"], "order": c.get("order", 0),
                          "entities": len([e for e in model["entities"] if e["compartment"] == c["id"]])}
                         for c in model["compartments"]],
        "legend_encodings": [{"channel": l["channel"], "meaning": l["meaning"],
                              "mapping": l.get("mapping", {}),
                              "source_column": l.get("source_column", ""),
                              "source": {"locator": l.get("locator"), "quote": l.get("quote")},
                              "quote_status": l.get("status"),
                              "on_canvas": l.get("on_canvas", True)} for l in model.get("legend", [])],
        "pending": pending, "coverage": coverage,
    }


# ------------------------------------------------------------------ audit
def audit(draft, corp, wo, declarations):
    """Mechanical check of a draft. Returns (report, printable lines)."""
    report = {"generated": now(), "issues": [], "rejected": [], "conflicts": [], "clean": False}
    degradations = []
    model, byname = norm_draft(draft, corp, degradations)
    ok_e = [e for e in model["entities"] if e["status"]]
    ok_r = [r for r in model["relations"] if r["status"]]

    for e in model["entities"]:
        if not e["status"]:
            report["rejected"].append({"kind": "entity", "id": e["id"], "name": e["name"],
                                       "reason": "quote not found in material",
                                       "quote": e["quote"][:160], "locator": e.get("declared_locator")})
    for r in model["relations"]:
        if not r["status"]:
            report["rejected"].append({"kind": "relation", "id": r["id"],
                                       "reason": "quote not found in material",
                                       "quote": r["quote"][:160], "locator": r.get("declared_locator")})
    for v in model["data_values"]:
        if v["value"] is None:
            report["issues"].append("data_value for %s has a non-numeric value" % v["entity"])
        elif v["status"] is None:
            report["rejected"].append({"kind": "data_value", "id": v["entity"],
                                       "reason": "numeric value has no verifiable source quote",
                                       "quote": v["quote"][:160], "locator": v["locator"]})
        elif ("%g" % v["value"]) not in (v["quote"] or "") and ("%.1f" % v["value"]) not in (v["quote"] or ""):
            report["issues"].append("data_value %s=%s is not literally present in its quote"
                                    % (v["entity"], "%g" % v["value"]))

    names = {e["id"]: e["name"] for e in model["entities"]}
    for r in model["relations"]:
        if r["type"] == "unspecified":
            continue
        for orient, how, loc, st in direction_scan(corp, names.get(r["from"], ""),
                                                   names.get(r["to"], ""))[:3]:
            if orient == "b>a":
                report["conflicts"].append({"relation": r["id"],
                                            "declared": "%s -> %s" % (names[r["from"]], names[r["to"]]),
                                            "material": st[:200], "locator": loc, "rule": how})
                break

    cov = coverage_of(wo, model, byname)
    if cov["workorder_entities"]["missing"]:
        report["issues"].append("workorder entities not covered: %s"
                                % ", ".join(cov["workorder_entities"]["missing"]))
    if cov["workorder_relations"]["missing"]:
        report["issues"].append("workorder relations not covered: %s"
                                % ", ".join(cov["workorder_relations"]["missing"]))
    report.update({"coverage": cov, "degradations": degradations,
                   "counts": {"entities": len(model["entities"]), "entities_verified": len(ok_e),
                              "relations": len(model["relations"]), "relations_verified": len(ok_r),
                              "rejected": len(report["rejected"]), "conflicts": len(report["conflicts"])},
                   "declared_contract": declarations})
    report["clean"] = not (report["rejected"] or report["issues"] or report["conflicts"])
    lines = ["entities %d (verified %d, rejected %d) | relations %d (verified %d, rejected %d)" % (
        len(model["entities"]), len(ok_e), len(model["entities"]) - len(ok_e),
        len(model["relations"]), len(ok_r), len(model["relations"]) - len(ok_r))]
    if cov["ratio"] is not None:
        lines.append("workorder coverage: entities %d/%d, relations %d/%d (ratio %.2f)" % (
            cov["workorder_entities"]["covered"], cov["workorder_entities"]["declared"],
            cov["workorder_relations"]["covered"], cov["workorder_relations"]["declared"], cov["ratio"]))
    for c in report["conflicts"][:3]:
        lines.append("CONFLICT %s: declared %s | material: %s"
                     % (c["relation"], c["declared"], c["material"][:80]))
    for it in report["rejected"][:5]:
        lines.append("REJECTED %s %s: %s" % (it["kind"], it.get("id"), it["reason"]))
    for it in report["issues"][:5]:
        lines.append("ISSUE %s" % it)
    return report, lines


def prepare(draft, corp, wo):
    """Draft -> drawable model. Unverified items are dropped, conflicting edges undirected."""
    degradations, uncertainty, pending = [], [], []
    model, byname = norm_draft(draft, corp, degradations)
    kept = []
    for e in model["entities"]:
        if e["status"]:
            kept.append(e)
        else:
            pending.append({"kind": "entity", "id": e["id"], "name": e["name"],
                            "reason": "quote unverified", "quote": e["quote"][:200],
                            "locator": e.get("declared_locator")})
    ids = {e["id"] for e in kept}
    rels = []
    for r in model["relations"]:
        if r["from"] not in ids or r["to"] not in ids:
            pending.append({"kind": "relation", "id": r["id"], "reason": "endpoint not drawn",
                            "quote": r["quote"][:200]})
        elif not r["status"]:
            pending.append({"kind": "relation", "id": r["id"], "reason": "quote unverified",
                            "quote": r["quote"][:200], "locator": r.get("declared_locator")})
        else:
            if r["direction"] in ("undirected", "none", "unknown"):
                r["direction"] = "undirected"
            rels.append(r)

    names = {e["id"]: e["name"] for e in kept}
    for r in rels:
        for orient, how, loc, st in direction_scan(corp, names.get(r["from"], ""),
                                                   names.get(r["to"], ""))[:2]:
            if orient == "b>a" and r["type"] != "unspecified":
                r["direction"] = "undirected"
                r["conflict"] = {"material": st[:200], "locator": loc}
                uncertainty.append("relation %s downgraded to undirected: wording in %s reads the other way"
                                   % (r["id"], loc))
                break
    model["entities"], model["relations"] = kept, rels
    if not kept:
        pending.append({"kind": "figure", "reason": "no verified entity; empty canvas emitted"})
    cov = coverage_of(wo, model, byname)
    for m in cov["workorder_entities"]["missing"]:
        pending.append({"kind": "workorder_entity", "name": m, "reason": "not produced by draft"})
    for m in cov["workorder_relations"]["missing"]:
        pending.append({"kind": "workorder_relation", "name": m, "reason": "not produced by draft"})
    return model, pending, degradations, uncertainty, cov, byname
