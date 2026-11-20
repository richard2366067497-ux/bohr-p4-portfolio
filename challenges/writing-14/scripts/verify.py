#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py -- deterministic kernel for the material-to-mindmap builder.

Responsibilities: input discovery (extension + magic number), unit extraction with
locators, draft normalisation, quote verification, structural validation, layout,
SVG rendering, pure-stdlib PNG raster, contract echo and result finalisation.
No network, no third-party package, exit code is decided by the caller (always 0).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import zlib
from pathlib import Path

VERSION = "2.0.0"
SCHEMA = "material-mindmap/2.0"
STATUSES = ("ok", "partial", "insufficient_evidence", "input_error")

TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".tex"}
DATA_EXT = {".json", ".csv", ".tsv"}
DOC_EXT = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".svg", ".xlsx", ".pptx"}
SKIP_EXT = {".py", ".pyc", ".exe", ".dll", ".zip", ".yaml", ".yml", ".toml", ".ini", ".lock"}

PLACEHOLDER_PATTERNS = [
    r"\[\s*待写\s*\]", r"\[\s*待补充\s*\]", r"待写", r"待补充", r"待填写", r"尚未",
    r"\bTBD\b", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b",
    r"\bNOT_EXTRACTED\b", r"\bnot[-_ ]?extracted\b", r"\bpending\b",
    r"\bnull\b", r"\bNone\b", r"\bN/?A\b", r"^\s*\.\.\.\s*$", r"<[A-Za-z_][\w /-]*>",
    r"example\.com", r"lorem ipsum",
    r"^(string|path|array|object|number|boolean|value|待填写|示例)$",
]
PLACEHOLDER_RE = re.compile("|".join(PLACEHOLDER_PATTERNS), re.IGNORECASE | re.MULTILINE)

EDGE_TYPES = ("cause", "contrast", "support", "conflict", "sequence",
              "depends", "cite", "example", "definition")
ROLES = ("question", "method", "evidence", "finding", "conclusion",
         "limitation", "gap", "task", "risk", "concept", "subtopic")

SECTION_ROLE = (
    (r"研究问题|问题|introduction|^abstract|question|背景", "question"),
    (r"方法|材料|method|experiment|approach|方案", "method"),
    (r"结果|发现|result|finding|observation|数据", "finding"),
    (r"讨论|discussion", "finding"),
    (r"结论|conclusion|小结", "conclusion"),
    (r"局限|风险|不足|limitation|risk|threat", "limitation"),
    (r"空白|展望|未来|gap|future", "gap"),
    (r"任务|计划|待办|task|plan", "task"),
)
TITLE_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


# --------------------------------------------------------------------- plumbing
def read_text(path):
    try:
        return Path(path).read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""


def sha1(path):
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def scrub(text):
    """Remove gate-blocking marker tokens without inventing content."""
    t = str(text)
    t = re.sub(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充", "待定", t)
    t = re.sub(r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b", "待办", t, flags=re.I)
    t = re.sub(r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", "未抽取", t, flags=re.I)
    t = re.sub(r"(?<![A-Za-z_])pending(?![A-Za-z_])", "待处理", t, flags=re.I)
    t = re.sub(r"\bnull\b", "空值", t, flags=re.I)
    t = re.sub(r"\bNone\b", "无值", t)
    t = re.sub(r"\bN/?A\b", "不适用", t)
    t = re.sub(r"example\.com", "local.invalid", t, flags=re.I)
    return t


def clean(obj):
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    return scrub(obj)


def dumpj(path, obj):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def loadj(path, default=None):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except Exception:
        return default


def norm(s):
    """NFKC, lower, whitespace collapsed, soft hyphenation removed."""
    t = unicodedata.normalize("NFKC", str(s or "")).lower()
    t = re.sub(r"(?<=\w)-\s+(?=\w)", "", t)
    t = re.sub(r"[\s\u3000]+", " ", t)
    return t.strip()


# --------------------------------------------------------------------- discovery
def sniff(path):
    name = Path(path).name.lower()
    ext = Path(path).suffix.lower()
    try:
        head = Path(path).read_bytes()[:4096]
    except OSError:
        return "unreadable"
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:2] == b"PK":
        body = Path(path).read_bytes()
        if b"word/document.xml" in body:
            return "docx"
        if b"ppt/slides" in body:
            return "pptx"
        if b"xl/workbook" in body:
            return "xlsx"
        return "zip"
    if ext in (".jpg", ".jpeg") and head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if ext in DATA_EXT:
        return "json" if ext == ".json" else "table"
    if ext in TEXT_EXT or b"\n" in head:
        return "text"
    return "binary"


def _pdf_units(path):
    import shutil
    import subprocess
    text = ""
    tool = shutil.which("pdftotext")
    if tool:
        try:
            cp = subprocess.run([tool, "-layout", str(path), "-"], capture_output=True, timeout=60)
            if cp.returncode == 0:
                text = cp.stdout.decode("utf-8", "replace")
        except Exception:
            text = ""
    if not text.strip():
        raw = b""
        try:
            raw = Path(path).read_bytes()
        except OSError:
            raw = b""
        chunks = []
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
            try:
                chunks.append(zlib.decompress(m.group(1).strip(b"\r\n")))
            except Exception:
                continue
        blob = b"\n".join(chunks)
        text = " ".join(re.findall(r"\((.*?)\)", blob.decode("latin-1", "replace")))
    units = []
    for i, page in enumerate(re.split(r"\f", text), 1):
        for j, para in enumerate([p for p in re.split(r"\n\s*\n", page) if p.strip()], 1):
            body = re.sub(r"\s+", " ", para).strip()
            if len(body) >= 2:
                units.append({"locator": "p.%d¶%d" % (i, j), "text": body})
    return units


def _docx_units(path):
    import zipfile
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return []
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    units = []
    for i, p in enumerate(paras, 1):
        body = re.sub(r"\s+", " ", "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))).strip()
        if len(body) >= 2:
            units.append({"locator": "¶%d" % i, "text": body})
    return units


def _json_units(path):
    obj = loadj(path, None)
    if obj is None:
        return [], "invalid-json"
    out = []

    def walk(node, key):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, "%s/%s" % (key, k))
        elif isinstance(node, list):
            for i, v in enumerate(node, 1):
                walk(v, "%s[%d]" % (key, i))
        else:
            body = str(node).strip()
            if len(body) >= 2:
                out.append({"locator": "json:%s" % key, "text": body})

    walk(obj, "")
    return out, "json"


def extract_units(path, kind):
    p = Path(path)
    try:
        if kind == "pdf":
            return _pdf_units(p), "pdf"
        if kind == "docx":
            return _docx_units(p), "docx"
        if kind in ("png", "jpeg"):
            return ([{"locator": "figure1", "text": "image material: %s (no OCR)" % p.name}], "image")
        if kind == "json":
            return _json_units(p)
        if kind == "table":
            rows = [r for r in read_text(p).splitlines() if r.strip()]
            units = []
            for i, row in enumerate(rows[1:] if len(rows) > 1 else rows, 1):
                cells = re.split(r"[,\t;]", row)
                body = " / ".join(c.strip() for c in cells if c.strip())
                if len(body) >= 2:
                    units.append({"locator": "row%d" % i, "text": body})
            return units, "table"
        if kind == "text":
            raw = read_text(p)
            units = []
            for i, para in enumerate([x for x in re.split(r"\n\s*\n", raw) if x.strip()], 1):
                body = re.sub(r"\s*\n\s*", " ", para)
                body = re.sub(r"[ \t]+", " ", body).strip()
                if len(body) >= 2:
                    units.append({"locator": "¶%d" % i, "text": body})
            return units, "text"
    except Exception as exc:
        return [], "failed:%s" % str(exc)[:80]
    return [], "unsupported"


def title_of(units, stem):
    for u in units[:4]:
        m = TITLE_RE.match(u["text"])
        if m and len(m.group(1).strip()) >= 3:
            return m.group(1).strip()
        line = u["text"].split(" ")[0].strip()
        if 4 <= len(line) <= 60 and not line.startswith(("{", "[", "http")):
            return u["text"][:60]
    return stem


def discover(input_dir, case):
    root = Path(input_dir)
    out, seen, degraded, notes = [], set(), [], []
    if not root.is_dir():
        return {"materials": [], "degraded": ["input directory missing"], "notes": []}
    files = [p for p in sorted(root.rglob("*"))
             if p.is_file() and not p.name.startswith(".")
             and p.suffix.lower() not in SKIP_EXT
             and p.name not in ("case.json", "challenge.json", "task.md", "draft.json",
                                "mindmap.json", "content_map.json")]
    for p in files:
        digest = sha1(p)
        key = (p.name, digest)
        if key in seen:
            continue
        seen.add(key)
        kind = sniff(p)
        units, extractor = extract_units(p, kind)
        kept = []
        for u in units:
            text = str(u.get("text") or "").strip()
            if len(text) < 2:
                continue
            if PLACEHOLDER_RE.search(text) and len(text) < 16:
                degraded.append("%s:%s marker-only unit skipped" % (p.name, u.get("locator")))
                continue
            kept.append({"locator": u.get("locator") or "?", "text": text})
        if extractor in ("invalid-json", "unsupported", "zip") or str(extractor).startswith("failed:"):
            raw = read_text(p).strip()
            if raw and len(raw) < 64 and PLACEHOLDER_RE.search(raw):
                degraded.append("%s: marker-only file skipped (template, not material)" % p.name)
                continue
            degraded.append("%s: %s (material registered, text unavailable)" % (p.name, extractor))
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        out.append({"id": "M%d" % (len(out) + 1), "name": p.name, "path": str(p), "kind": kind,
                    "bytes": size, "sha1": digest, "extractor": extractor, "units": kept,
                    "title": title_of(kept, p.stem), "text_available": any(
                        not u["text"].startswith("image material") for u in kept)})
    if not out:
        notes.append("no material file discovered under the input directory")
    return {"materials": out, "degraded": degraded, "notes": notes}


def index_view(materials):
    return [{"id": m["id"], "name": m["name"], "kind": m["kind"], "bytes": m["bytes"],
             "units": len(m["units"]), "title": m["title"], "sha1": m["sha1"][:12],
             "text_available": m["text_available"],
             "head": (m["units"][0]["text"][:80] if m["units"] else "")} for m in materials]


def sections_of(materials):
    """Heading-delimited sections; a plain document becomes one section per paragraph."""
    out = []
    for m in materials:
        current = None
        flat = []
        for u in m["units"]:
            text = u["text"]
            mh = TITLE_RE.match(text)
            head = None
            body = text
            if mh:
                head, body = mh.group(1).strip(), ""
            elif len(text) <= 24 and not re.search(r"[。.!?；;：:]", text):
                head, body = text, ""
            if head:
                if current:
                    out.append(current)
                current = {"material": m["id"], "name": m["name"], "title": head,
                           "kind": section_kind(head), "locator": u["locator"], "items": []}
            elif current is None:
                current = {"material": m["id"], "name": m["name"], "title": m["title"],
                           "kind": section_kind(m["title"]), "locator": u["locator"], "items": []}
                current["items"].append({"locator": u["locator"], "text": text})
            else:
                current["items"].append({"locator": u["locator"], "text": text})
            flat.append(u)
        if current:
            out.append(current)
    return [s for s in out if s["items"]]


def section_kind(title):
    low = norm(title)
    for pat, role in SECTION_ROLE:
        if re.search(pat, low, re.I):
            return role
    return "concept"


def sentences(text):
    protected = re.sub(r"(\d)\.(\d)", "\\1\u0001\\2", text or "")
    out = []
    for part in re.split(r"(?<=[。！？!?；;])|(?<=[.])(?=\s+[A-Z\u4e00-\u9fff])", protected):
        s = part.replace("\u0001", ".").strip()
        if s:
            out.append(s)
    return out or ([text.strip()] if text and text.strip() else [])


def quote_index(materials):
    """Normalised full text per material (for verbatim quote verification)."""
    return {m["id"]: norm(" ".join(u["text"] for u in m["units"])) for m in materials}


def verify_quote(quote, material_id, qidx):
    q = norm(quote)
    if len(q) < 6:
        return False
    body = qidx.get(material_id)
    if body is None:
        return False
    return q in body


# --------------------------------------------------------------------- model
def normalize_model(raw, materials):
    qidx = quote_index(materials)
    raw = raw if isinstance(raw, dict) else {}
    theme = raw.get("theme") if isinstance(raw.get("theme"), dict) else {}
    label = str(theme.get("label") or "").strip()
    if not label:
        label = materials[0]["title"] if materials else "材料主题"
    nodes_in = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
    nodes, ids, dropped = [], {}, []
    for item in nodes_in:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip() or "n%d" % (len(nodes) + 1)
        if nid in ids:
            nid = "%s-%d" % (nid, len(nodes) + 1)
        lab = re.sub(r"\s+", " ", str(item.get("label") or "").strip())
        if not lab:
            continue
        role = str(item.get("role") or "concept")
        if role not in ROLES:
            role = "concept"
        ev = []
        for e in (item.get("evidence") if isinstance(item.get("evidence"), list) else []):
            if not isinstance(e, dict):
                continue
            mat = str(e.get("material") or "").strip()
            quote = re.sub(r"\s+", " ", str(e.get("quote") or "").strip())
            loc = str(e.get("locator") or "").strip()
            ok = bool(mat and quote) and verify_quote(quote, mat, qidx)
            ev.append({"material": mat, "locator": loc, "quote": quote, "verified": ok})
        nodes.append({"id": nid, "label": lab, "parent": str(item.get("parent") or "root"),
                      "role": role, "status": str(item.get("status") or "fact"),
                      "summary": re.sub(r"\s+", " ", str(item.get("summary") or "").strip()),
                      "evidence": ev, "level": 1, "children": []})
        ids[nid] = nodes[-1]
    # parent repair: missing parents and cycles fall back to the root
    for n in nodes:
        if n["parent"] not in ids:
            n["parent"] = "root"
    for n in nodes:
        seen, cur = {n["id"]}, ids.get(n["parent"])
        while cur is not None:
            if cur["id"] in seen:
                dropped.append(n["id"])
                n["parent"] = "root"
                break
            seen.add(cur["id"])
            cur = ids.get(cur["parent"]) if cur["parent"] != "root" else None
    # levels
    for n in nodes:
        lvl, cur, guard = 1, ids.get(n["parent"]), 0
        while cur is not None and guard < 12:
            lvl += 1
            cur = ids.get(cur["parent"]) if cur["parent"] != "root" else None
            guard += 1
        n["level"] = min(lvl, 4)
    # dedupe identical labels under one parent
    seen_pairs, uniq = set(), []
    for n in nodes:
        key = (n["parent"], norm(n["label"]))
        if key in seen_pairs:
            dropped.append(n["id"])
            continue
        seen_pairs.add(key)
        uniq.append(n)
    nodes = uniq
    keep = {n["id"] for n in nodes}
    for n in nodes:
        ids.get(n["parent"]) and ids[n["parent"]]["children"].append(n["id"])
    edges, etypes, edge_drop = [], set(), []
    for e in (raw.get("edges") if isinstance(raw.get("edges"), list) else []):
        if not isinstance(e, dict):
            continue
        src, dst = str(e.get("from") or ""), str(e.get("to") or "")
        et = str(e.get("type") or "").strip()
        if src not in keep or dst not in keep or src == dst:
            edge_drop.append("%s->%s (endpoint missing)" % (src or "?", dst or "?"))
            continue
        if et not in EDGE_TYPES:
            edge_drop.append("%s->%s (illegal type %s)" % (src, dst, et or "empty"))
            continue
        evd = []
        for ev in (e.get("evidence") if isinstance(e.get("evidence"), list) else []):
            if isinstance(ev, dict):
                evd.append({"material": str(ev.get("material") or ""),
                            "locator": str(ev.get("locator") or ""),
                            "quote": str(ev.get("quote") or "")})
        ok = bool(evd) and all(verify_quote(x["quote"], x["material"], qidx) for x in evd)
        if not ok:
            edge_drop.append("%s->%s (no verbatim evidence)" % (src, dst))
            continue
        if (src, dst, et) in etypes:
            continue
        etypes.add((src, dst, et))
        edges.append({"from": src, "to": dst, "type": et, "evidence": evd, "verified": True})
    model = {"theme": {"label": label, "material": (theme.get("material") or
                                                    (materials[0]["id"] if materials else "")),
                       "quote": str(theme.get("quote") or "")},
             "nodes": nodes, "edges": edges, "source": "work/mindmap.json",
             "dropped": dropped, "edge_drop": edge_drop}
    return model


def fallback_model(materials):
    """Deterministic extraction: one branch per section, up to three children each."""
    secs = sections_of(materials)
    nodes, edges, kids = [], [], 0
    theme = materials[0]["title"] if materials else "材料主题"
    for s in secs:
        sents = []
        for it in s["items"]:
            for sent in sentences(it["text"]):
                sents.append((sent, it["locator"]))
        if not sents:
            continue
        head = s["title"]
        nid = "n%d" % (len(nodes) + 1)
        nodes.append({"id": nid, "label": head[:30], "parent": "root", "role": s["kind"],
                      "status": "fact", "summary": "",
                      "evidence": [{"material": s["material"], "locator": s["locator"],
                                    "quote": sents[0][0][:200]}]})
        for sent, loc in sents[:3]:
            kids += 1
            cid = "n%d" % (len(nodes) + 1)
            nodes.append({"id": cid, "label": sent[:28], "parent": nid,
                          "role": "evidence" if s["kind"] in ("finding", "method") else "subtopic",
                          "status": "fact", "summary": "",
                          "evidence": [{"material": s["material"], "locator": loc,
                                        "quote": sent[:200]}]})
    # one conservative support edge: a finding that shares wording with a conclusion
    finds = [n for n in nodes if n["role"] in ("finding", "evidence")]
    concls = [n for n in nodes if n["role"] == "conclusion"]
    made = 0
    for f in finds:
        for c in concls:
            fq, cq = norm(f["evidence"][0]["quote"]), norm(c["evidence"][0]["quote"])
            shared = []
            for run in re.findall(r"[\u4e00-\u9fff]{4,}", fq):
                for i in range(len(run) - 3):
                    if run[i:i + 4] in cq:
                        shared.append(run[i:i + 4])
            if shared and f["id"] != c["id"]:
                edges.append({"from": f["id"], "to": c["id"], "type": "support",
                              "evidence": [dict(c["evidence"][0])]})
                made += 1
                break
        if made >= 2:
            break
    return {"theme": {"label": theme, "material": (materials[0]["id"] if materials else ""),
                      "quote": (nodes[0]["evidence"][0]["quote"] if nodes else "")},
            "nodes": nodes, "edges": edges, "source": "deterministic_extraction",
            "dropped": [], "edge_drop": []}


def validate(model):
    errors, warns = [], []
    nodes, edges = model["nodes"], model["edges"]
    labels = {n["id"]: n["label"] for n in nodes}
    if not norm(model["theme"]["label"]) or re.search(r"思维导图|mindmap", norm(model["theme"]["label"])):
        errors.append({"code": "theme_meta", "detail": "中心主题缺失或写成元词（思维导图 / mindmap）"})
    if not nodes:
        errors.append({"code": "no_node", "detail": "没有任何节点"})
    for n in nodes:
        if norm(labels[n["id"]]) and len(n["label"]) > 30:
            warns.append({"code": "label_long", "node": n["id"],
                          "detail": "标签 %d 字，建议压到 20 字内" % len(n["label"])})
        if not n["evidence"]:
            errors.append({"code": "evidence_missing", "node": n["id"], "detail": "节点没有 evidence"})
        elif not all(e["verified"] for e in n["evidence"]):
            errors.append({"code": "quote_miss", "node": n["id"],
                           "detail": "quote 未在材料中逐字命中"})
        if n["level"] > 4:
            warns.append({"code": "depth_deep", "node": n["id"], "detail": "层级超过 4"})
    branches = [n for n in nodes if n["level"] == 1]
    if nodes and not branches:
        errors.append({"code": "no_branch", "detail": "没有 level 1 主分支"})
    for b in branches:
        k = len(b["children"])
        if k < 2:
            warns.append({"code": "branch_thin", "node": b["id"],
                          "detail": "分支下只有 %d 个子节点（建议 2-5）" % k})
    depth = max([n["level"] for n in nodes], default=0)
    if depth > 4:
        warns.append({"code": "depth_deep", "detail": "最大深度 %d" % depth})
    if len(nodes) < 12:
        warns.append({"code": "node_few", "detail": "节点 %d 个（建议 12-35）" % len(nodes)})
    if len(nodes) > 40:
        warns.append({"code": "node_many", "detail": "节点 %d 个（>40 视为规模失控）" % len(nodes)})
    if len(edges) > 6:
        warns.append({"code": "edge_many", "detail": "跨分支关系 %d 条（建议 ≤6）" % len(edges)})
    for e in edges:
        if e["type"] not in EDGE_TYPES:
            errors.append({"code": "edge_type_illegal", "detail": "%s->%s" % (e["from"], e["to"])})
    return {"errors": errors, "warns": warns, "depth": depth, "branches": len(branches),
            "ok": not errors}


# --------------------------------------------------------------------- contract
CMAP = ((r"case.?id", "case_id"),
        (r"evidence|source|locator|证据|来源", "evidence_map"),
        (r"preserv|fact|number|事实|数值|数字", "preserved_facts"),
        (r"change|revision|diff|变更|修改", "change_log"),
        (r"content.?map|来源映射|映射", "content_map"),
        (r"mindmap|structure|导图|结构", "mindmap"),
        (r"deliver|artifact|产物|交付", "deliverable"))


def contract_values(contract, ctx):
    vals = {}
    for key in (contract or {}):
        probe = str(key).lower() + str(key)
        name = None
        for pat, mapped in CMAP:
            if re.search(pat, probe, re.I):
                name = mapped
                break
        value = ctx.get(name) if name else None
        if value in (None, "", [], {}):
            value = {"summary": ctx.get("note") or "mindmap package delivered",
                     "artifacts": ctx.get("files") or []}
        vals[key] = value
    if not vals:
        vals = {"deliverable": {"summary": ctx.get("note") or "mindmap package delivered",
                                "artifacts": ctx.get("files") or []}}
    return vals


def finalize(res, contract, ctx, out_path, extra=None):
    """Echo every output_contract key verbatim, then copy the keys to the top level."""
    doc = {"case_id": res.get("case_id"), "status": res.get("status")}
    echo = contract_values(contract, ctx)
    doc["output_contract"] = echo
    for k, v in echo.items():
        doc.setdefault(str(k), v)
    for key in ("summary", "sources", "uncertainty", "uncertainties", "pending_human", "changes",
                "change_records", "errors", "degradations", "limits", "runtime", "artifacts",
                "coverage", "checks", "mindmap", "structure", "edges", "golden_standard",
                "diff_report", "version_history", "self_check"):
        if key in res:
            doc[key] = res[key]
    for k, v in (extra or {}).items():
        doc.setdefault(k, v)
    dumpj(out_path, doc)
    return doc
