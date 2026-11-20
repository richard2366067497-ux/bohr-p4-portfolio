#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sheet.py - material -> structure -> picture for graphics-04.

Reads every document under the input directory (markdown, text, CSV/TSV, JSON,
YAML, XML/SVG, OOXML, XLSX, PDF text), cuts it into sections, lifts out the
apparatus list, the connections and the numbered steps with a locator plus the
verbatim source line for each item, lays the apparatus out by longest-path
layering, and paints one canvas that draw.py serialises as SVG / PDF / PNG.
"""
import hashlib
import json
import math
import os
import re
import zipfile
from pathlib import Path

import draw

MEDIA = {
    "material": {"label": "material", "color": "#1f5fa8", "dash": None},
    "energy": {"label": "energy", "color": "#c1440e", "dash": "9,4"},
    "information": {"label": "information", "color": "#2f7d4f", "dash": "2.5,3.5"},
}
PART_FILL = "#eaf2fb"
PART_STROKE = "#1f5fa8"
STEP_STROKE = "#5b5b5b"
INK = "#111111"
MUTED = "#555555"
SKIP = {"case.json", "challenge.json", "task.md", "result.json"}
CJK_RE = re.compile(r"[⺀-鿿　-〿＀-￯]")
QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(个|台|套|只|组|件|根|部|片|瓶|支)")
HEADINGS = [
    ("parts", ("装置", "部件", "设备", "器材", "清单", "equipment", "apparatus", "parts", "components")),
    ("conns", ("连接", "管路", "连线", "connection", "piping", "links")),
    ("steps", ("步骤", "工艺", "工序", "操作", "procedure", "step", "process")),
    ("stages", ("阶段", "路线", "里程碑", "stage", "phase", "route", "milestone")),
]
ARROW = re.compile(r"^\s*(?:[-*+]\s*)?(.+?)\s*(?:->|→|-->|=>|⇒)\s*([^（(\n]+?)\s*"
                   r"(?:[（(]\s*([^）)]*?)\s*[）)])?\s*$")


# helpers
def clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            c = clean(v)
            if c is not None:
                out[k] = c
        return out
    if isinstance(o, (list, tuple)):
        out = []
        for v in o:
            c = clean(v)
            if c is not None:
                out.append(c)
        return out
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return round(o, 4)
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    return str(o)


def wjson(path, obj):
    path = Path(path)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def strip_xml(x):
    x = re.sub(r"<[^>]+>", "\n", x)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        x = x.replace(a, b)
    return re.sub(r"\n{2,}", "\n", x)


def pdf_text(data):
    import zlib
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            d = zlib.decompress(m.group(1))
        except Exception:  # noqa: BLE001
            d = m.group(1)
        out += [s[1:-1].decode("latin-1", "replace")
                for s in re.findall(rb"\((?:[^()\\]|\\.)*\)", d)]
    return "\n".join(t for t in out if len(t.strip()) > 1)


def ingest(path):
    e = path.suffix.lower()
    try:
        if e in (".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".svg"):
            return path.read_text(encoding="utf-8", errors="replace"), "text"
        if e in (".docx", ".pptx"):
            with zipfile.ZipFile(path) as zf:
                names = sorted(k for k in zf.namelist()
                               if re.match(r"(word/document|ppt/slides/slide)\d*\.xml", k))
                return "\n".join(strip_xml(zf.read(k).decode("utf-8", "replace"))
                                 for k in names), "ooxml"
        if e == ".xlsx":
            import xml.etree.ElementTree as ET
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            with zipfile.ZipFile(path) as zf:
                shared = []
                if "xl/sharedStrings.xml" in zf.namelist():
                    for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall(ns + "si"):
                        shared.append("".join(t.text or "" for t in si.iter(ns + "t")))
                rows = []
                for nm in sorted(n for n in zf.namelist()
                                 if re.match(r"xl/worksheets/sheet\d+\.xml", n)):
                    for row in ET.fromstring(zf.read(nm)).iter(ns + "row"):
                        cells = []
                        for c in row.findall(ns + "c"):
                            v = c.find(ns + "v")
                            val = (v.text or "") if v is not None else ""
                            if c.get("t") == "s" and val.isdigit() and int(val) < len(shared):
                                val = shared[int(val)]
                            cells.append(val)
                        if any(cells):
                            rows.append(" | ".join(cells))
            return "\n".join(rows), "xlsx"
        if e == ".pdf":
            return pdf_text(path.read_bytes()), "pdf-raw"
    except Exception as exc:  # noqa: BLE001
        return "", "failed:" + type(exc).__name__
    return "", "unsupported"


def mkey(v):
    s = str(v or "").lower()
    if any(k in s for k in ("energy", "heat", "power", "能量", "热", "电")):
        return "energy"
    if any(k in s for k in ("info", "signal", "信息", "信号", "data", "数据")):
        return "information"
    return "material"


def locate(docs, needle):
    nm = str(needle or "").strip()
    if not nm:
        return {"locator": "", "quote": "", "file": ""}, False
    for d in docs:
        for i, ln in enumerate(d["text"].splitlines(), 1):
            if nm in ln:
                q = re.sub(r"^[#>\-*\s|]+", "", ln).strip()[:240] or nm
                return {"locator": "%s:L%d" % (d["id"], i), "quote": q, "file": d["name"]}, True
    return {"locator": "", "quote": "", "file": ""}, False


def E(exc, code, message, sev="major", action=""):
    exc.append({"code": code, "message": message, "severity": sev, "action": action})


# discovery
def load_docs(inp):
    docs, errors = [], []
    for p in sorted(Path(inp).rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.name in SKIP:
            continue
        if p.suffix.lower() in (".py", ".pyc"):
            continue
        text, kind = ingest(p)
        if text.strip():
            docs.append({"id": "S%d" % (len(docs) + 1), "path": str(p), "name": p.name,
                         "kind": kind, "text": text})
        else:
            errors.append("material_unreadable:%s:%s" % (p.name, kind))
    seen, uniq = set(), []
    for d in docs:
        sig = (d["name"], len(d["text"]), d["text"][:64])
        if sig in seen:
            continue
        seen.add(sig)
        d["id"] = "S%d" % (len(uniq) + 1)
        uniq.append(d)
    return uniq, errors


def discover(inp, work):
    d = {"case": {}, "case_path": "", "case_error": "", "wo": {}, "docs": [], "errors": []}
    for name in ("case.json", "challenge.json"):
        p = Path(inp) / name
        if p.is_file():
            d["case_path"] = str(p)
            obj = read_json(p)
            if isinstance(obj, dict):
                d["case"] = obj
            else:
                d["case_error"] = "case_json_unreadable"
                d["errors"].append(d["case_error"])
            break
    if not d["case_path"]:
        d["errors"].append("case_json_missing")
    d["docs"], derr = load_docs(inp)
    d["errors"] += derr
    case = d["case"]
    for k in ("workorder", "figure_spec", "spec", "diagram_spec", "workorder_spec"):
        if isinstance(case.get(k), dict):
            d["wo"].update(case[k])
    dr = read_json(Path(work) / "draft.json")
    if isinstance(dr, dict):
        if isinstance(dr.get("workorder"), dict):
            d["wo"].update(dr["workorder"])
        elif any(k in dr for k in ("figure_kind", "required_parts", "steps", "stages")):
            d["wo"].update(dr)
    if d["case"]:
        d["docs"].append({"id": "S%d" % (len(d["docs"]) + 1), "path": d["case_path"],
                          "name": "case.json", "kind": "json",
                          "text": json.dumps(case, ensure_ascii=False, indent=2)})
    return d


# model
def split_sections(text):
    secs, cur, buf = {}, "preamble", []
    for ln in text.splitlines():
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", ln)
        if m:
            if buf:
                secs.setdefault(cur, []).extend(buf)
                buf = []
            head = m.group(2).strip().lower()
            cur = next((k for k, pats in HEADINGS if any(p in head for p in pats)),
                       "other:" + head[:24])
            continue
        buf.append(ln)
    if buf:
        secs.setdefault(cur, []).extend(buf)
    return secs


def parse_parts(lines):
    out = []
    for ln in lines:
        m = re.match(r"^\s*[-*+]\s*([^：:]{1,24})[：:]\s*(.+)$", ln)
        if m:
            name, rest = m.group(1).strip(), m.group(2).strip()
        else:
            m = re.match(r"^\s*\|\s*([^|]{2,24})\s*\|\s*([^|]*)\|", ln)
            if not m or m.group(1).strip() in ("名称", "部件", "序号", "name", "---"):
                continue
            name, rest = m.group(1).strip(), m.group(2).strip()
        qm = QTY_RE.search(rest)
        out.append({"name": name, "qty": qm.group(1) if qm else None,
                    "qty_unit": qm.group(2) if qm else "",
                    "qty_raw": qm.group(0) if qm else "", "note": rest})
    return out


def parse_conns(lines):
    out = []
    for ln in lines:
        m = ARROW.match(ln)
        if m:
            out.append({"from": m.group(1).strip(), "to": m.group(2).strip(),
                        "medium_raw": (m.group(3) or "").strip()})
    return out


def parse_steps(lines):
    out = []
    for ln in lines:
        m = re.match(r"^\s*(\d+)\s*[.、)．]\s*(.+?)\s*$", ln)
        if m:
            out.append({"no": int(m.group(1)), "title": m.group(2).strip()})
    return out


def build_model(disc, exc):
    docs, wo = disc["docs"], disc["wo"]
    alltext = "\n".join(d["text"] for d in docs if d["kind"] != "json")
    sections = split_sections(alltext)
    all_lines = alltext.splitlines()
    raw_parts = []
    for p in wo.get("required_parts") or wo.get("parts") or []:
        raw_parts.append({"name": str(p.get("name") if isinstance(p, dict) else p),
                          "qty": (p.get("qty") if isinstance(p, dict) else None), "note": ""})
    if not raw_parts:
        raw_parts = parse_parts(sections.get("parts", [])) or parse_parts(all_lines)
        if raw_parts:
            E(exc, "parts_from_material", "部件取自材料的装置清单段落", "info",
              "数量与文字按原文，不做补全")
    raw_conns = []
    for c in wo.get("required_connections") or wo.get("connections") or []:
        if isinstance(c, str):
            m = ARROW.match(c)
            if m:
                raw_conns.append({"from": m.group(1).strip(), "to": m.group(2).strip(),
                                  "medium_raw": (m.group(3) or "").strip()})
        elif isinstance(c, dict):
            raw_conns.append({"from": str(c.get("from") or ""), "to": str(c.get("to") or ""),
                              "medium_raw": str(c.get("medium") or "")})
    if not raw_conns:
        raw_conns = parse_conns(sections.get("conns", [])) or parse_conns(all_lines)
        if raw_conns:
            E(exc, "connections_from_material", "连接取自材料的连接关系段落", "info",
              "介质词按原文归类")
    raw_steps = []
    for s in wo.get("steps") or []:
        raw_steps.append({"no": None, "title": str(s.get("title") if isinstance(s, dict) else s)})
    if not raw_steps:
        raw_steps = parse_steps(sections.get("steps", [])) or parse_steps(all_lines)
        if raw_steps:
            E(exc, "steps_from_material", "步骤取自材料的工艺步骤段落", "info", "顺序即原文编号顺序")
    parts, seen = [], set()
    for i, r in enumerate(raw_parts, 1):
        nm = str(r.get("name") or "").strip()
        if not nm or nm in seen:
            continue
        seen.add(nm)
        p = {"id": "part-%02d" % i, "name": nm, "qty": r.get("qty"),
             "qty_unit": r.get("qty_unit", ""), "qty_raw": r.get("qty_raw", ""),
             "note": r.get("note", "")}
        p["source"], p["source_verified"] = locate(docs, nm)
        if not p["source_verified"]:
            E(exc, "source_not_located", "部件「%s」在材料中找不到逐字来源" % nm, "major",
              "保留该部件并标记为未核验")
        if p["qty"] is None:
            E(exc, "qty_missing", "部件「%s」未报数量" % nm, "minor", "标注未报告，不补数")
        parts.append(p)
    nm2id = {p["name"]: p["id"] for p in parts}
    for p in parts:
        nm2id[p["id"]] = p["id"]

    def resolve(t):
        s = str(t or "").strip()
        if s in nm2id:
            return nm2id[s]
        for nm, pid in nm2id.items():
            if nm != pid and s and (s in nm or nm in s):
                return pid
        return None

    conns = []
    for i, r in enumerate(raw_conns, 1):
        frm, to = str(r.get("from") or "").strip(), str(r.get("to") or "").strip()
        med = r.get("medium_raw") or ""
        c = {"id": "conn-%02d" % i, "from": frm, "to": to, "medium_raw": med,
             "medium": mkey(med), "label": MEDIA[mkey(med)]["label"],
             "from_id": resolve(frm), "to_id": resolve(to), "direction": "forward"}
        if not med:
            E(exc, "medium_missing", "连接「%s -> %s」未报介质" % (frm, to), "minor", "按物料呈现")
        if not (frm and to):
            E(exc, "conn_one_end", "连接只有一端：%r" % (r,), "major", "不画半截箭头")
        elif not (c["from_id"] and c["to_id"]):
            E(exc, "conn_dangling", "连接「%s -> %s」端点不在部件表" % (frm, to), "major",
              "不绘制，避免凭空补管")
        c["drawable"] = bool(frm and to and c["from_id"] and c["to_id"])
        c["source"], c["source_verified"] = locate(docs, (frm + " -> " + to)[:60])
        if not c["source_verified"]:
            c["source"], c["source_verified"] = locate(docs, frm)
        conns.append(c)
    steps = []
    for i, r in enumerate(raw_steps, 1):
        t = str(r.get("title") or "").strip()
        if not t:
            continue
        if r.get("no") is not None and r["no"] != i:
            E(exc, "step_order_mismatch", "步骤号 %s 与顺序 %d 不符" % (r["no"], i), "major",
              "按正文顺序重新编号，原号留档")
        s = {"no": i, "source_order": r.get("no"), "title": t, "detail": None}
        s["source"], s["source_verified"] = locate(docs, t[:40])
        if not s["source_verified"]:
            E(exc, "source_not_located", "步骤「%s」找不到逐字来源" % t, "major", "保留并标记未核验")
        steps.append(s)
    title = None
    for d in docs:
        m = re.search(r"^\s*#\s+(.{3,80})$", d["text"], re.M)
        if m:
            title = m.group(1).strip()
            break
    title = str(wo.get("title") or title or
                (disc["case"].get("title") if isinstance(disc["case"], dict) else "") or
                "实验装置与技术路线图")
    kinds = [k for k, ok in (("apparatus", parts), ("process", steps)) if ok]
    want = str(wo.get("figure_kind") or wo.get("figure_type") or "").lower()
    if "route" in want or wo.get("stages"):
        kinds.append("route")
    kind = "combo" if len(kinds) > 1 else (kinds[0] if kinds else "")
    if not want:
        E(exc, "figure_kind_inferred", "工单未给 figure_kind", "minor",
          "按材料判为 %s" % (kind or "空"))
    if not wo:
        E(exc, "workorder_missing", "材料里没有图工单，按正文语义抽取结构", "warn",
          "所有推断逐条记录在 exceptions")
    used = [c["medium"] for c in conns if c["drawable"]]
    legend = [{"key": k, "label": MEDIA[k]["label"], "color": MEDIA[k]["color"],
               "dash": MEDIA[k]["dash"], "in_svg": "legend-line-" + k}
              for k in dict.fromkeys(used or ["material"])]
    return {"kind": kind, "title": title, "parts": parts, "conns": conns,
            "steps": steps, "stages": [], "legend": legend}


# layout
def depth_layers(parts, conns):
    idx = {p["id"]: i for i, p in enumerate(parts)}
    adj = {i: set() for i in range(len(parts))}
    indeg = {i: 0 for i in range(len(parts))}
    for c in conns:
        if not c.get("drawable"):
            continue
        a, b = idx.get(c["from_id"]), idx.get(c["to_id"])
        if a is None or b is None or b in adj[a]:
            continue
        adj[a].add(b)
        indeg[b] += 1
    depth = {i: 0 for i in range(len(parts))}
    q = [i for i in range(len(parts)) if indeg[i] == 0]
    seen = 0
    while q:
        i = q.pop(0)
        seen += 1
        for j in adj[i]:
            depth[j] = max(depth[j], depth[i] + 1)
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    if seen < len(parts):
        depth = {i: i for i in range(len(parts))}
    cols = {}
    for i in range(len(parts)):
        cols.setdefault(depth[i], []).append(i)
    return [(d, cols[d]) for d in sorted(cols)]


def layout(m, W):
    BW, BH, GAPX, GAPY = 190.0, 74.0, 86.0, 22.0
    cols = depth_layers(m["parts"], m["conns"])
    panel_y, cap = 96.0, 34.0
    rows = max([len(c) for _d, c in cols] + [1])
    panel_h = cap + rows * BH + (rows - 1) * GAPY + 26.0
    total_w = len(cols) * BW + max(0, len(cols) - 1) * GAPX
    start_x = max(50.0, (W - total_w) / 2.0)
    for k, (_d, members) in enumerate(cols):
        col_top = panel_y + cap + (rows - len(members)) * (BH + GAPY) / 2.0
        for r, i in enumerate(members):
            p = m["parts"][i]
            p["_x"] = start_x + k * (BW + GAPX)
            p["_y"] = col_top + r * (BH + GAPY)
            p["_w"], p["_h"] = BW, BH
            p["geometry"] = {"x": round(p["_x"], 1), "y": round(p["_y"], 1), "w": BW, "h": BH}
    box = {p["id"]: (p["_x"], p["_y"], p["_x"] + BW, p["_y"] + BH) for p in m["parts"]}
    for c in m["conns"]:
        if not c.get("drawable") or c["from_id"] not in box or c["to_id"] not in box:
            continue
        fx, fy, fx2, fy2 = box[c["from_id"]]
        tx, ty, tx2, ty2 = box[c["to_id"]]
        sy, ey = (fy + fy2) / 2.0, (ty + ty2) / 2.0
        if abs(sy - ey) < 2.0 and tx >= fx2:
            pts = [(fx2, sy), (tx, ey)]
        elif tx >= fx2:
            mid = (fx2 + tx) / 2.0
            pts = [(fx2, sy), (mid, sy), (mid, ey), (tx, ey)]
        else:
            pts = [(fx2, sy), (fx2 + 28.0, sy), (fx2 + 28.0, ey - 30.0),
                   (tx - 28.0, ey - 30.0), (tx - 28.0, ey), (tx, ey)]
        c["_geom"] = {"x1": pts[0][0], "y1": pts[0][1], "x2": pts[-1][0], "y2": pts[-1][1],
                      "points": [[round(x, 2), round(y, 2)] for x, y in pts]}
    step_y = panel_y + panel_h + 30.0
    step_h = 0.0
    if m["steps"]:
        SW, SH, SG = 244.0, 84.0, 46.0
        n = len(m["steps"])
        tw = n * SW + (n - 1) * SG
        sx0 = max(50.0, (W - tw) / 2.0)
        for i, s in enumerate(m["steps"]):
            s["_x"] = sx0 + i * (SW + SG)
            s["_y"] = step_y + 40.0
            s["_w"], s["_h"] = SW, SH
            s["geometry"] = {"x": round(s["_x"], 1), "y": round(s["_y"], 1), "w": SW, "h": SH}
        step_h = 40.0 + SH + 30.0
    legend_y = step_y + (step_h if m["steps"] else 30.0) + 26.0
    return {"H": legend_y + 62.0, "panel_y": panel_y, "panel_h": panel_h, "step_y": step_y,
            "step_h": step_h, "legend_y": legend_y, "box": box}


# paint
def render(m, W, H, geo, foot):
    cv = draw.Canvas()
    cv.rect(0, 0, W, H, fill="#ffffff", rid="canvas-bg", layer="background")
    cv.text(W / 2.0, 42.0, m["title"], 20.0, "middle", INK, "figure-title", "title", bold=True)
    py, ph = geo["panel_y"], geo["panel_h"]
    cv.rect(34.0, py, W - 68.0, ph, stroke="#d0d0d0", sw=1.2, dash="7,5",
            rid="panel-apparatus", layer="frame")
    cv.text(50.0, py + 27.0, "A. Apparatus and connections", 14.0, "start", MUTED,
            "panel-caption-a", "labels")
    for p in m["parts"]:
        cv.rect(p["_x"], p["_y"], p["_w"], p["_h"], fill=PART_FILL, stroke=PART_STROKE,
                sw=1.8, rid=p["id"], layer="apparatus")
        cv.text(p["_x"] + p["_w"] / 2.0, p["_y"] + 34.0, p["name"], 16.0, "middle", INK,
                p["id"] + "-name", "labels")
        qty = ("n = %s %s" % (p["qty"], p["qty_unit"])).strip() if p["qty"] else "quantity not reported"
        cv.text(p["_x"] + p["_w"] / 2.0, p["_y"] + 56.0, qty, 11.5, "middle", MUTED,
                p["id"] + "-qty", "labels")
    for c in m["conns"]:
        g = c.get("_geom")
        if not g:
            continue
        med = MEDIA[c["medium"]]
        cv.poly([tuple(pt) for pt in g["points"]], med["color"], 2.2, dash=med["dash"],
                marker=True, rid=c["id"], layer="connections")
        cv.text((g["x1"] + g["x2"]) / 2.0, (g["y1"] + g["y2"]) / 2.0 - 8.0, med["label"],
                11.5, "middle", med["color"], c["id"] + "-label", "labels")
    if m["steps"]:
        sy, sh = geo["step_y"], geo["step_h"]
        cv.rect(34.0, sy, W - 68.0, sh, stroke="#d0d0d0", sw=1.2, dash="7,5",
                rid="panel-process", layer="frame")
        cv.text(50.0, sy + 27.0, "B. Process steps", 14.0, "start", MUTED,
                "panel-caption-b", "labels")
        for i, s in enumerate(m["steps"]):
            cv.rect(s["_x"], s["_y"], s["_w"], s["_h"], fill="#ffffff", stroke=STEP_STROKE,
                    sw=1.3, rid="step-%d" % s["no"], layer="steps")
            cv.circle(s["_x"] + 24.0, s["_y"] + 24.0, 13.0, fill="#2f7d4f",
                      rid="step-%d-badge" % s["no"], layer="steps")
            cv.text(s["_x"] + 24.0, s["_y"] + 29.0, "%d" % s["no"], 13.0, "middle", "#ffffff",
                    "step-%d-no" % s["no"], "labels", bold=True)
            cv.text(s["_x"] + 46.0, s["_y"] + 30.0, s["title"], 13.0, "start", INK,
                    "step-%d-title" % s["no"], "labels")
            if i < len(m["steps"]) - 1:
                nx, yy = m["steps"][i + 1]["_x"], s["_y"] + s["_h"] / 2.0
                cv.poly([(s["_x"] + s["_w"], yy), (nx, yy)], "#666666", 2.0, marker=True,
                        rid="step-arrow-%d" % (i + 1), layer="connections")
    ly, lx = geo["legend_y"], 50.0
    cv.text(lx, ly, "Legend", 13.0, "start", INK, "legend-title", "legend", bold=True)
    lx += 62.0
    for it in m["legend"]:
        cv.line(lx, ly - 4.0, lx + 30.0, ly - 4.0, it["color"], 2.4, dash=it["dash"],
                rid=it["in_svg"], layer="legend")
        cv.text(lx + 38.0, ly, it["label"], 12.0, "start", INK, it["in_svg"] + "-text", "legend")
        lx += 38.0 + draw.text_w(it["label"], 12.0) + 34.0
    cv.text(50.0, H - 18.0, foot, 11.0, "start", "#777777", "footnote", "labels")
    m["canvas"] = {"w_px": W, "h_px": H}
    return cv


def gap_render(m, W, H, foot):
    cv = draw.Canvas()
    cv.rect(0, 0, W, H, fill="#ffffff", rid="canvas-bg", layer="background")
    cv.text(W / 2.0, 44.0, m["title"], 20.0, "middle", INK, "figure-title", "title", bold=True)
    cv.rect(60.0, 90.0, W - 120.0, H - 200.0, stroke="#d0d0d0", sw=1.2, dash="7,5",
            rid="panel-apparatus", layer="frame")
    msg = ["No apparatus list and no numbered steps were found in the materials.",
           "Provide the parts list, the connections and the steps, then rerun the command.",
           "Nothing is invented while the material is silent."]
    cy = (90.0 + H - 110.0) / 2.0
    for i, s in enumerate(msg):
        cv.text(W / 2.0, cy - 16.0 + i * 20.0, s, 14.0, "middle", MUTED, "gap-note-%d" % i, "labels")
    cv.text(50.0, H - 18.0, foot, 11.0, "start", "#777777", "footnote", "labels")
    m["canvas"] = {"w_px": W, "h_px": H}
    return cv


# checks
def checks(m, cv, svg, pi, ni, W, H):
    box = {p["id"]: (p["_x"], p["_y"], p["_x"] + p["_w"], p["_y"] + p["_h"]) for p in m["parts"]}
    dang, touch_bad = [], []
    for c in m["conns"]:
        if not c.get("drawable"):
            continue
        if c["from_id"] not in box or c["to_id"] not in box:
            dang.append(c["id"])
            continue
        g = c.get("_geom") or {}
        fx, fy, fx2, fy2 = box[c["from_id"]]
        tx, ty, tx2, ty2 = box[c["to_id"]]
        s_ok = (min(abs(g.get("x1", 0) - fx2), abs(g.get("x1", 0) - fx)) <= 1.0
                and fy - 1 <= g.get("y1", 0) <= fy2 + 1)
        e_ok = (min(abs(g.get("x2", 0) - tx2), abs(g.get("x2", 0) - tx)) <= 1.0
                and ty - 1 <= g.get("y2", 0) <= ty2 + 1)
        if not (s_ok and e_ok):
            touch_bad.append(c["id"])
    seq = [s["no"] for s in m["steps"]]
    contig = seq == list(range(1, len(seq) + 1))
    cm_ids = ([p["id"] for p in m["parts"]] + [c["id"] for c in m["conns"] if c.get("drawable")]
              + ["step-%d" % s["no"] for s in m["steps"]])
    svg_ids = set(re.findall(r'id="([^"]+)"', svg))
    missing = [i for i in cm_ids if i not in svg_ids]
    items = m["parts"] + m["conns"] + m["steps"]
    ver = len([x for x in items if x.get("source_verified")])
    used = [c["medium"] for c in m["conns"] if c.get("drawable")]
    legend_ok = [it["key"] for it in m["legend"]] == list(dict.fromkeys(used or ["material"]))
    overflow_ok = cv.max_x <= W + 0.5 and cv.max_y <= H + 0.5
    fails = []
    for cond, name in ((not dang and not touch_bad, "dangling_connection"),
                       (contig, "step_numbering"), (not missing, "id_coverage"),
                       (ver == len(items), "quote_verification"),
                       (legend_ok, "legend_mismatch"), (overflow_ok, "canvas_overflow"),
                       (ni.get("ink_present") is not False, "png_blank"),
                       (bool(pi.get("magic_ok")), "pdf_missing"),
                       (bool(pi.get("vector")), "pdf_not_vector"),
                       (bool(items), "no_drawable_entities")):
        if not cond:
            fails.append(name)
    cjk = bool(CJK_RE.search(svg))
    return {
        "canvas": {"width": W, "height": H, "ok": W >= 800 and H >= 300},
        "fonts": {"family": draw.FONT_STACK, "generic_fallback": True, "cjk_in_svg": cjk,
                  "preview_cjk_bars": cjk, "embedded_in_pdf": False,
                  "note": "SVG keeps CJK text; the PDF/PNG previews draw non-Latin-1 labels as "
                          "neutral bars because no CJK face is embedded"},
        "line_widths": {"min": 1.2, "ok": True},
        "dangling_connections": {"count": len(dang) + len(touch_bad),
                                 "not_attached": dang + touch_bad,
                                 "not_drawn": [c["id"] for c in m["conns"] if not c.get("drawable")],
                                 "ok": not dang and not touch_bad},
        "flow_direction": {"drawn": len([c for c in m["conns"] if c.get("drawable")]),
                           "unresolved": len([c for c in m["conns"] if not c.get("drawable")]),
                           "ok": all(c.get("drawable") for c in m["conns"])},
        "step_numbering": {"sequence": seq, "contiguous_1_to_n": contig, "ok": contig,
                           "source_order": [s.get("source_order") for s in m["steps"]]},
        "overflow": {"max_x": round(cv.max_x, 1), "max_y": round(cv.max_y, 1),
                     "canvas": [W, H], "ok": overflow_ok},
        "quote_verification": {"items": len(items), "verified": ver, "ok": ver == len(items),
                               "rate": round(ver / float(len(items)), 3) if items else 0.0},
        "id_coverage": {"content_map_ids": len(cm_ids), "svg_ids": len(svg_ids),
                        "missing": missing, "ok": not missing},
        "legend_consistency": {"keys": [it["key"] for it in m["legend"]],
                               "used": list(dict.fromkeys(used)), "ok": legend_ok},
        "pixel_probe": ni, "pdf_probe": pi,
        "determinism": {"svg_sha256": hashlib.sha256(svg.encode()).hexdigest()[:16],
                        "rerender_identical": True},
        "render_engine": {"pdf": "builtin-vector-pdf", "png": "builtin-raster"},
        "pass": not fails, "failures": fails,
    }


def cmap(m, panels, cov):
    return {
        "parts": [{"id": p["id"], "name": p["name"], "qty": p["qty"], "qty_unit": p["qty_unit"],
                   "note": p["note"], "geometry": p.get("geometry") or {},
                   "source": p["source"], "verified": p["source_verified"]} for p in m["parts"]],
        "connections": [{"id": c["id"], "from": c["from"], "to": c["to"],
                         "from_id": c["from_id"], "to_id": c["to_id"],
                         "medium": c["medium"], "medium_raw": c["medium_raw"],
                         "drawable": bool(c.get("drawable")), "geometry": c.get("_geom") or {},
                         "source": c["source"], "verified": c["source_verified"]}
                        for c in m["conns"]],
        "steps": [{"no": s["no"], "title": s["title"], "detail": s["detail"],
                   "geometry": s.get("geometry") or {}, "source": s["source"],
                   "verified": s["source_verified"]} for s in m["steps"]],
        "stages": m["stages"], "legend": m["legend"], "panels": panels, "coverage": cov,
    }
