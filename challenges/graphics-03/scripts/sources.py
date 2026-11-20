"""Input layer for mechanism-figure-ledger.

Material discovery and text recovery (md/txt/csv/json/pdf/docx/xlsx/pptx), the
workorder object table, and the deterministic fallback draft used when the Agent
has not written one. Nothing here judges biology; it only quotes what exists.
"""
import re
import zipfile
import zlib
from pathlib import Path

import ledger as LD

TEXT_EXT = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml",
            ".xml", ".html", ".htm", ".svg", ".tex", ".log"}
OFFICE_EXT = {".docx", ".pptx", ".xlsx"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp"}

MINE_EN = re.compile(r"\b([A-Za-z][A-Za-z0-9\-]{1,14})\s+"
                     r"(activates|inhibits|binds|phosphorylates|ubiquitinates|transports|"
                     r"translocates|suppresses|promotes|recruits|represses|induces)\s+"
                     r"([A-Za-z][A-Za-z0-9\-]{1,14})\b", re.I)
MINE_ZH = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9\-]{2,12})\s*"
                     r"(促进|激活|抑制|下调|上调|结合|磷酸化|泛素化|转运|转位|募集)\s*"
                     r"([\u4e00-\u9fa5A-Za-z0-9\-]{2,12})")


def kind_of(p):
    e = Path(p).suffix.lower()
    if e == ".pdf":
        return "pdf"
    if e in OFFICE_EXT:
        return "office"
    if e in IMAGE_EXT:
        return "image"
    if e in TEXT_EXT:
        return "text"
    return "binary"


def pdf_text(p):
    """Best-effort text layer: FlateDecode streams -> literal (..) strings."""
    parts = []
    try:
        data = Path(p).read_bytes()
    except Exception:
        return parts
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1)
        try:
            dec = zlib.decompress(raw)
        except Exception:
            dec = raw
        if b"Tj" not in dec and b"TJ" not in dec:
            continue
        buf = []
        for s in re.finditer(rb"\((?:\\.|[^()\\])*\)", dec):
            lit = re.sub(rb"\\([()\\])", rb"\1", s.group(0)[1:-1])
            try:
                buf.append(lit.decode("latin-1"))
            except Exception:
                pass
        txt = LD.nw(" ".join(buf))
        if len(txt) > 20:
            parts.append(txt)
    return parts


def office_text(p):
    out = []
    try:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if not n.endswith(".xml"):
                    continue
                if not (n.startswith("word/") or n.startswith("xl/") or n.startswith("ppt/")):
                    continue
                raw = z.read(n).decode("utf-8", "ignore")
                raw = re.sub(r"</(w:p|a:p|text:p|row|c|si)>", "\n", raw)
                out.append(re.sub(r"<[^>]+>", " ", raw))
    except Exception as exc:
        return "", "%s: %s" % (type(exc).__name__, exc)
    return "\n".join(out), None


def blocks_of(p):
    p = Path(p)
    k = kind_of(p)
    try:
        if k == "text":
            t = p.read_bytes().decode("utf-8-sig", "ignore")
            if not t.strip():
                return [], "empty file"
        elif k == "pdf":
            parts = pdf_text(p)
            if not parts:
                return [], "no extractable text (scanned or image-only PDF)"
            return [("%s#stream%d" % (p.name, i + 1), x) for i, x in enumerate(parts) if x], None
        elif k == "office":
            t, note = office_text(p)
            if note:
                return [], note
        elif k == "image":
            return [], "bitmap material: indexed as a gap, not used as text evidence"
        else:
            return [], "unsupported binary"
        paras = [LD.nw(x) for x in re.split(r"\n\s*\n", t)]
        paras = [x for x in paras if x]
        if not paras:
            paras = [LD.nw(x) for x in t.splitlines() if LD.nw(x)]
        return [("%s#para%d" % (p.name, i + 1), x) for i, x in enumerate(paras)], None
    except Exception as exc:
        return [], "%s: %s" % (type(exc).__name__, exc)


def collect(inp):
    root = Path(inp)
    mats, corpus = [], []
    if not root.exists():
        return mats, corpus, "input directory not found: %s" % root
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        blocks, note = blocks_of(p)
        rel = p.relative_to(root).as_posix()
        mats.append({"id": p.name, "rel": rel, "kind": kind_of(p), "bytes": p.stat().st_size,
                     "blocks": len(blocks), "note": note, "locators": [b[0] for b in blocks[:3]]})
        for loc, txt in blocks:
            corpus.append({"material": rel, "locator": loc, "text": txt, "declared": False})
    return mats, corpus, None


def get_case(inp):
    root = Path(inp)
    cand = root / "case.json"
    if cand.is_file():
        obj = LD.jread(cand)
        if isinstance(obj, dict):
            return obj
    for p in sorted(root.glob("*.json")):
        obj = LD.jread(p)
        if isinstance(obj, dict) and any(k in obj for k in ("output_contract", "outputContract", "case_id")):
            return obj
    return None


def salvage_case(inp):
    """Broken JSON: regex-rescue case_id and the declared contract field names."""
    cand = Path(inp) / "case.json"
    if not cand.is_file():
        return None
    raw = cand.read_bytes().decode("utf-8", "ignore")
    cid = re.search(r'"(?:case_id|caseId)"\s*:\s*"([^"]+)"', raw)
    keep = []
    m = re.search(r'"(?:output_contract|outputContract)"\s*:\s*\[(.*?)\]', raw, re.S)
    if m:
        keep = re.findall(r'"([A-Za-z_][A-Za-z0-9_]{1,40})"', m.group(1))
    if not keep:
        known = ("case_id", "status", "editable_source", "export_artifact",
                 "content_map", "compliance_checks", "exceptions")
        if re.search(r'"(?:output_contract|outputContract)"', raw):
            keep = list(known)                      # declared but unreadable: fill the known set
        else:
            keys = re.findall(r'"([A-Za-z_][A-Za-z0-9_]{2,40})"\s*:', raw)
            keep = [n for n in known if n in keys]
    return {"case_id": cid.group(1) if cid else None, "output_contract": keep, "_salvaged": True}


def objtable(wo):
    rows = {"entities": [], "relations": [], "compartments": [], "legend": []}
    for i, e in enumerate(LD.req(wo, LD.ENT_KEYS)):
        rows["entities"].append({"name": LD.ename(e), "type": LD.etype(e), "compartment": LD.ecomp(e),
                                 "locator": "case.json#workorder.required_entities[%d]" % i})
    for i, r in enumerate(LD.req(wo, LD.REL_KEYS)):
        rows["relations"].append({"from": LD.rsrc(r), "to": LD.rdst(r), "type": LD.rtype(r),
                                  "locator": "case.json#workorder.required_relations[%d]" % i})
    for i, c in enumerate(LD.req(wo, LD.COMP_KEYS)):
        rows["compartments"].append({"name": LD.ename(c) or LD.nm(c),
                                     "locator": "case.json#workorder.compartments[%d]" % i})
    for i, l in enumerate(LD.req(wo, LD.LEG_KEYS)):
        if isinstance(l, dict):
            rows["legend"].append({"channel": l.get("channel"), "meaning": l.get("meaning"),
                                   "locator": "case.json#workorder.legend_encodings[%d]" % i})
    return rows


def declared_corpus(wo):
    """Workorder entries are quotable, but counted separately as `declared`."""
    out = []
    for i, e in enumerate(LD.req(wo, LD.ENT_KEYS)):
        v = LD.ename(e)
        if v:
            out.append({"material": "case.json", "declared": True, "text": LD.nw(v),
                        "locator": "case.json#workorder.required_entities[%d]" % i})
    for i, r in enumerate(LD.req(wo, LD.REL_KEYS)):
        v = LD.rtext(r)
        if v:
            out.append({"material": "case.json", "declared": True, "text": LD.nw(v),
                        "locator": "case.json#workorder.required_relations[%d]" % i})
    for i, c in enumerate(LD.req(wo, LD.COMP_KEYS)):
        v = LD.ename(c) or LD.nm(c)
        if v:
            out.append({"material": "case.json", "declared": True, "text": LD.nw(v),
                        "locator": "case.json#workorder.compartments[%d]" % i})
    return out


def fallback_draft(wo, corp):
    """Deterministic last resort: workorder items + explicit 'A verb B' sentences only."""
    ents, rels, seen = [], [], {}

    def add(name, et, comp, quote, loc):
        sid = LD.slug(name)
        if sid in seen:
            return seen[sid]
        seen[sid] = sid
        ents.append({"id": sid, "name": name, "label": name,
                     "entity_type": et if et in LD.ENUM_ENT else "unspecified",
                     "compartment": comp or LD.guess_zone(name, et), "italic": et == "gene",
                     "source": {"locator": loc, "quote": quote}})
        return sid

    for i, e in enumerate(LD.req(wo, LD.ENT_KEYS)):
        v = LD.ename(e)
        if v:
            add(v, LD.etype(e), LD.zone_id(LD.ecomp(e)) if LD.ecomp(e) else "",
                v, "case.json#workorder.required_entities[%d]" % i)
    for i, r in enumerate(LD.req(wo, LD.REL_KEYS)):
        a, b = LD.rsrc(r), LD.rdst(r)
        if a and b:
            loc = "case.json#workorder.required_relations[%d]" % i
            rels.append({"id": "r%d" % (len(rels) + 1), "from": add(a, "unspecified", "", a, loc),
                         "to": add(b, "unspecified", "", b, loc),
                         "relation_type": LD.rtype(r) if LD.rtype(r) in LD.ENUM_REL else "unspecified",
                         "direction": "forward", "evidence_strength": "declared",
                         "source": {"locator": loc, "quote": LD.rtext(r)}})

    if len(ents) < 3:
        for blk in corp:
            if blk.get("declared"):
                continue
            for st in LD.sentences(blk["text"]):
                for pat in (MINE_EN, MINE_ZH):
                    for m in pat.finditer(st):
                        a, verb, b = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                        if len(a) < 2 or len(b) < 2 or a.lower() == b.lower():
                            continue
                        rt = next((t for ws, t in LD.VERBS if any(w in verb.lower() for w in ws)),
                                  "unspecified")
                        rels.append({"id": "r%d" % (len(rels) + 1),
                                     "from": add(a, "unspecified", "", st, blk["locator"]),
                                     "to": add(b, "unspecified", "", st, blk["locator"]),
                                     "relation_type": rt, "direction": "forward",
                                     "evidence_strength": "mined",
                                     "source": {"locator": blk["locator"], "quote": st}})
    return {"title": "Mechanism figure (draft not supplied - degraded from workorder/material)",
            "subtitle": "status=partial: entity types, arrow semantics and compartments are unconfirmed",
            "compartments": [dict(z) for z in LD.ZONES], "entities": ents, "relations": rels,
            "legend": [], "data_values": [], "edits": [], "gaps": []}
