#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入发现与索引层：材料抽取（PDF/DOCX/XLSX/文本）、题录对象表、别名与版本和解。
只做机械解析，不做任何案例假设；解析失败只降级该材料，不中断。"""
import json, re, shutil, subprocess, time, zipfile, zlib
from pathlib import Path

import gates as G

IMG = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif")
VER = [("retracted", r"(retract|撤稿|撤回|withdrawn)"), ("correction", r"(corrigend|erratum|勘误|更正|correction)"),
       ("preprint", r"(preprint|预印本)"), ("superseded", r"(supersed|取代|被替换|replaced by)"),
       ("version_update", r"(\bv[2-9]\b|version\s*[2-9]|第[二三]版|修订版|updated version|revised)")]


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def dec(raw):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def key(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", G.norm(s).lower())


def pdf_plain(raw):
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        b = m.group(1)
        try:
            b = zlib.decompress(b)
        except Exception:
            pass
        if b"Tj" in b or b"TJ" in b:
            t = " ".join(x.decode("latin-1", "replace") for x in re.findall(rb"\(((?:\\.|[^\\()]){1,500})\)", b))
            if G.norm(t):
                out.append(t)
    return "\n".join(out)


def pdf_text(p):
    for exe in ("pdftotext", "pdf-text-tool"):
        w = shutil.which(exe)
        if w:
            try:
                cmd = [w, str(p)] if exe == "pdf-text-tool" else [w, "-layout", str(p), "-"]
                t = dec(subprocess.run(cmd, capture_output=True, timeout=120).stdout)
                if len(G.norm(t)) > 200:
                    return t, "ext:" + exe
            except Exception:
                pass
    try:
        import fitz  # type: ignore
        t = "\n".join(g.get_text() for g in fitz.open(str(p)))
    except Exception:
        try:
            t = __import__("pdfminer.high_level", fromlist=["x"]).extract_text(str(p))
        except Exception:
            t = ""
    if len(G.norm(t)) > 50:
        return t, "optional-lib"
    return pdf_plain(Path(p).read_bytes()), "stdlib-crude"


def zip_text(p):
    with zipfile.ZipFile(p) as z:
        n = z.namelist()
        if any(x.startswith("word/") for x in n):
            s = "\n".join(z.read(f).decode("utf-8", "replace")
                          for f in sorted(x for x in n if re.match(r"word/(document|header|footer)", x)))
            return re.sub(r"<[^>]+>", "", re.sub(r"<w:tab[^>]*/>", "\t", re.sub(r"</w:p>", "\n", s)))
        out = []
        for f in sorted(x for x in n if x.startswith("xl/worksheets/")):
            for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(f).decode("utf-8", "replace"), re.S):
                vals = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<c\b[^>]*>(.*?)</c>", row, re.S)]
                if any(G.norm(v) for v in vals):
                    out.append("\t".join(vals))
        return "\n".join(out)


def read_mat(p):
    p, e = Path(p), Path(p).suffix.lower()
    try:
        raw = p.read_bytes()
        if e == ".pdf" or raw[:4] == b"%PDF":
            t, how = pdf_text(p)
            return "pdf", t, how
        if e in (".docx", ".xlsx", ".xlsm") or raw[:2] == b"PK":
            return "office", zip_text(p), "zip-openxml"
        if e in IMG:
            return "image", "", "no_ocr"
        t = dec(raw)
        head = t[:3000]
        if t and sum(c.isprintable() or c in "\n\t" for c in head) > 0.9 * max(1, len(head)):
            return "text", t, "plain"
        return "binary", "", "unsupported"
    except Exception as x:
        return "error", "", "%s: %s" % (type(x).__name__, x)


def scan(root):
    root = Path(root)
    if not root.exists():
        return []
    return [p for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.startswith(".") and "__pycache__" not in p.parts]


def role_of(rel):
    s = rel.lower()
    if s.endswith("task.md"):
        return "instruction"
    if re.match(r"^(case|input)[^/]*\.json$", Path(rel).name.lower()):
        return "meta"
    if re.search(r"(proposal|idea|research_plan|设想|申请)", s):
        return "proposal"
    if re.search(r"(^|/)(sources?|papers?|refs?|literature|docs?)/", s):
        return "source"
    if re.search(r"(constraint|约束|budget)", s):
        return "constraints"
    if re.search(r"(records?|search_hits|检索)", s):
        return "records"
    return "other"


def find_case(indir):
    bad = None
    cand = [Path(indir) / x for x in ("case.json", "input.json", "case/case.json", "task/case.json")]
    cand += [p for p in scan(indir) if re.match(r"(case|input|task_?case)[^/]*\.json$", p.name, re.I)]
    for p in cand:
        if p.is_file():
            o, e = G.load_json(p)
            if isinstance(o, dict):
                return o, str(p), None
            bad = "%s: %s" % (p.name, e)
    return {}, None, bad or "未找到 case.json（%s）" % indir


def gk(case, *names, default=None):
    for n in names:
        for k, v in (case or {}).items():
            if str(k).lower() == n.lower() and v not in (None, "", [], {}):
                return v
    return default


def contract_of(case):
    c = gk(case, "output_contract", "outputcontract", "contract", "required_outputs", "result_schema")
    if isinstance(c, dict):
        return {str(k): v for k, v in c.items()}
    if isinstance(c, list):
        return {str(x if not isinstance(x, dict) else (x.get("field") or x.get("name") or "item%d" % i)): x
                for i, x in enumerate(c, 1)}
    if isinstance(c, str) and G.norm(c):
        return {G.norm(c): None}
    return {}


def ver_flag(text):
    t = G.norm(text)
    for lab, pat in VER:
        m = re.search(pat, t, re.I)
        if m:
            return lab, t[max(0, m.start() - 30):m.end() + 40]
    return "", ""


def mk_source(i, d, origin):
    sid = G.norm(d.get("id") or d.get("source_id") or d.get("key") or d.get("uid") or "S%d" % i)
    title = G.norm(d.get("title") or d.get("name") or d.get("title_en") or d.get("label"))
    doi = G.norm(d.get("doi") or d.get("DOI"))
    aliases = G.strs(d.get("aliases") if d.get("aliases") is not None else
                     (d.get("also_known_as") or d.get("alias") or d.get("alternate_ids") or d.get("synonyms")))
    note = G.norm(d.get("note") or d.get("notes") or d.get("status") or d.get("version") or d.get("admin_note"))
    abst = G.norm(d.get("abstract") or d.get("abstract_text") or d.get("summary") or d.get("content") or d.get("text"))
    vf, vq = ver_flag(" ".join([note, G.norm(d.get("version")), title]))
    return {"sid": sid, "title": title, "doi": doi, "year": G.norm(d.get("year") or d.get("pub_year")),
            "aliases": aliases, "raw_id": G.norm(d.get("id") or d.get("source_id")), "note": note,
            "version_flag": vf, "version_quote": vq, "material": "", "origin": origin, "abstract": abst}


def mk_rec(i, d):
    rid = G.norm(d.get("id") or d.get("record_id") or d.get("key") or "R%d" % i)
    ref = G.norm(d.get("source_id") or d.get("source") or d.get("ref") or d.get("target")
                 or d.get("alias_of") or d.get("matched_source") or d.get("matched"))
    note = G.norm(d.get("note") or d.get("notes") or d.get("version_note") or d.get("status")
                  or d.get("administrative_note") or d.get("comment"))
    vf, vq = ver_flag(" ".join([note, G.norm(d.get("version"))]))
    return {"rid": rid, "raw_ref": ref, "note": note, "version_flag": vf, "version_quote": vq,
            "sid": "", "resolved_by": "", "duplicate_of": ""}


def build_index(indir, cpath=None, case=None):
    indir = Path(indir)
    case = case if isinstance(case, dict) else {}
    skip = {str(Path(cpath).resolve())} if cpath else set()
    mats, notes = [], []
    for i, p in enumerate([x for x in scan(indir) if str(x.resolve()) not in skip], 1):
        kind, text, how = read_mat(p)
        rel = str(p.relative_to(indir)) if indir in p.parents else p.name
        if kind in ("image", "binary", "error") or not G.norm(text):
            notes.append({"material": rel, "note": how})
        mats.append({"id": "M%d" % i, "rel": rel, "role": role_of(rel), "kind": kind,
                     "chars": len(text or ""), "extract": how, "size": p.stat().st_size,
                     "text": (text or "")[:400000],
                     "paras": [{"loc": "p%d" % j, "text": t} for j, t in enumerate(G.paras(text), 1)]})
    otexts, sources, records, cons = [], [], [], []
    for i, d in enumerate(G.al(gk(case, "sources", "source_list", "documents", "library", "papers",
                                  "corpus", "references")), 1):
        if not isinstance(d, dict):
            d = {"id": str(d)}
        s = mk_source(i, d, "case.json")
        sources.append(s)
        if s["abstract"]:
            otexts.append({"id": s["sid"], "locator": "abstract", "text": s["abstract"]})
    for i, d in enumerate(G.al(gk(case, "records", "record_list", "hits", "search_results",
                                  "retrieved_records")), 1):
        records.append(mk_rec(i, d if isinstance(d, dict) else {"ref": str(d)}))
    for m in mats:
        if m["role"] != "records" and not m["rel"].lower().endswith(".jsonl"):
            continue
        for line in (m["text"] or "").split("\n"):
            if not G.norm(line).startswith("{"):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if isinstance(d, dict) and any(k in d for k in ("source_id", "source", "ref", "alias", "record_id")):
                records.append(mk_rec(len(records) + 1, d))
    raw_cons = gk(case, "constraints", "limits", "conditions")
    if isinstance(raw_cons, dict):
        cons = [{"id": "K%d" % i, "text": "%s: %s" % (k, G.norm(v)), "locator": "case.json"}
                for i, (k, v) in enumerate(raw_cons.items(), 1)]
    else:
        cons = [{"id": "K%d" % i, "text": G.norm(d if not isinstance(d, dict) else json.dumps(d, ensure_ascii=False)),
                 "locator": "case.json"} for i, d in enumerate(G.al(raw_cons), 1)]
    if not sources:
        for m in ([x for x in mats if x["role"] == "source" and x["chars"] > 40]
                  or [x for x in mats if x["role"] not in ("meta", "instruction") and x["chars"] > 40]
                  or [x for x in mats if x["role"] == "source"]):
            head = next((pa["text"] for pa in m["paras"] if len(G.norm(pa["text"])) > 12), m["rel"])
            sources.append({"sid": "S%d" % (len(sources) + 1), "title": G.norm(head)[:120] or m["rel"],
                            "doi": "", "year": "", "aliases": [m["rel"], Path(m["rel"]).stem],
                            "raw_id": m["rel"], "note": "", "version_flag": ver_flag(m["rel"])[0],
                            "version_quote": "", "material": m["id"], "origin": "materials", "abstract": ""})
    kmap = {}
    for s in sources:
        for k in [s["sid"], s["raw_id"], s["title"], s["doi"]] + s["aliases"]:
            if key(k):
                kmap.setdefault(key(k), s["sid"])
    for r in records:
        k = key(r["raw_ref"])
        if k and k in kmap:
            r["sid"], r["resolved_by"] = kmap[k], "exact"
        elif k:
            for kk, sid in kmap.items():
                if k in kk or kk in k:
                    r["sid"], r["resolved_by"] = sid, "partial"
                    break
    for s in sources:
        if s["material"]:
            continue
        kt = key(s["title"])[:24]
        if kt:
            for m in mats:
                if kt in key(m["rel"]) or kt in key(G.norm(m["text"])[:4000]):
                    s["material"] = m["id"]
                    break
    seen = {}
    for r in records:
        if not r["sid"]:
            continue
        if r["sid"] in seen:
            r["duplicate_of"] = seen[r["sid"]]
        else:
            seen[r["sid"]] = r["rid"]
    unresolved = [r for r in records if not r["sid"]]
    dups = [r for r in records if r["duplicate_of"]]
    vflags = [{"kind": "source", "id": s["sid"], "flag": s["version_flag"], "quote": s["version_quote"]}
              for s in sources if s["version_flag"]] + \
             [{"kind": "record", "id": r["rid"], "flag": r["version_flag"], "quote": r["version_quote"]}
              for r in records if r["version_flag"]]
    return {"input_dir": str(indir), "case_path": cpath, "built_at": now(), "materials": mats,
            "objects": {"sources": sources, "records": records, "constraints": cons},
            "object_texts": otexts, "extract_notes": notes,
            "unresolved_records": [{"rid": r["rid"], "raw_ref": r["raw_ref"]} for r in unresolved],
            "duplicate_records": [{"rid": r["rid"], "duplicate_of": r["duplicate_of"], "sid": r["sid"]} for r in dups],
            "version_notes": vflags,
            "total_chars": sum(m["chars"] for m in mats),
            "counts": {"materials": len(mats), "readable": sum(1 for m in mats if m["chars"]),
                       "sources": len(sources), "records": len(records),
                       "records_resolved": len([r for r in records if r["sid"]]),
                       "records_unresolved": len(unresolved), "duplicate_records": len(dups),
                       "version_notes": len(vflags), "constraints": len(cons),
                       "inline_texts": len(otexts)}}
