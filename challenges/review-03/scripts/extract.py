#!/usr/bin/env python3
"""extract.py - 输入发现与材料抽取（仅标准库、不联网、不依赖 CWD）。

职责：路径解析、宽松 JSON IO、材料类型嗅探、正文抽取为带 locator 的 unit、
逐字引文比对、以及"可能是一个被报告结果"的候选行机械抽取（不做任何判定）。

  python3 -B extract.py --selftest
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

RE_P = re.compile(r"\bp\s*(?:value\s*)?([=<>≤≥])\s*(0?\.\d+|\d\.\d+\s*e-?\s*\d+)", re.I)
RE_STAT = re.compile(r"\b(t|F|Z|chi2|χ2|χ²|U|H|W|OR|HR|RR|IRR|β|B)\s*(?:\(\s*([\d.,\s]{1,14})\))?\s*=\s*(-?\d+(?:\.\d+)?)", re.I)
RE_CI = re.compile(r"(95\s*%\s*(?:CI|confidence interval)|CI\s*[=:])[^.;]{0,30}?(-?\d+(?:\.\d+)?)\s*(?:[,\u2013\-]|to)\s*(-?\d+(?:\.\d+)?)", re.I)
RE_N = re.compile(r"\bn\s*=\s*(\d[\d,]*)", re.I)
MC_WORDS = ("bonferroni", "tukey", "dunnett", "holm", "benjamini", "hochberg", "fdr",
            "multiple compar", "multiplicity", "校正", "多重比较")
ATT_WORDS = ("lost to follow", "withdr", "dropout", "drop-out", "excluded", "missing data",
             "失访", "退出", "剔除", "缺失")
SS_WORDS = ("power", "sample size", "g*power", "把握度", "检验效能", "样本量", "效应量",
            "minimum detectable")
EFF_WORDS = ("odds ratio", "hazard ratio", "risk ratio", "cohen", "hedges", "eta", "epsilon",
             "standardized mean difference", "smd", "auc", "效应量")
DESIGN_WORDS = ("randomi", "rct", "cohort", "case-control", "case control", "cross-sectional",
                "cross sectional", "retrospective", "prospective", "blinded", "blinding",
                "随机", "队列", "病例对照", "横断面", "盲法")


def paths():
    """输入/输出/工作目录；可用 SCIM_INPUT/SCIM_OUTPUT/SCIM_WORK 覆盖，目录不可写时回退。"""
    pick = lambda k, d: Path(os.environ.get(k) or d)
    inp, out, wrk = pick("SCIM_INPUT", "/input"), pick("SCIM_OUTPUT", "/app/output"), pick("SCIM_WORK", "/app/work")
    if not inp.is_dir():
        cwd = Path.cwd()
        for cand in (cwd / "input", cwd.parent / "input", Path("/bohr-workspace/input"), Path("/workspace/input")):
            if cand.is_dir():
                inp = cand
                break
    for d in (out, wrk):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    if out.exists() and not os.access(str(out), os.W_OK):
        out = Path.cwd() / "output"
    if wrk.exists() and not os.access(str(wrk), os.W_OK):
        wrk = Path.cwd() / "work"
    for d in (out, wrk):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return inp, out, wrk


def load_json(path):
    """读 JSON，容忍 BOM / GB18030 / latin-1。返回 (obj, err)。"""
    try:
        raw = Path(path).read_bytes()
    except Exception as exc:
        return None, "read_failed:%s" % exc
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return json.loads(raw.decode(enc)), None
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            return None, "parse_failed:%s" % exc
    return None, "decode_failed"


def dump_json(path, obj, indent=2):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
        os.replace(tmp, p)
        return str(p)
    except Exception:
        try:
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
            return str(p)
        except Exception:
            return None


def write_text(path, text):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, p)
        return str(p)
    except Exception:
        try:
            p.write_text(text, encoding="utf-8")
            return str(p)
        except Exception:
            return None


def norm(s):
    """引文匹配用规范化：NFKC、去零宽/不换行空格、空白折叠、小写。不动实义字符。"""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s)
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0", "\u3000"):
        s = s.replace(ch, " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def snip(s, n=240):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


def sha1(path, n=10):
    try:
        q = Path(path)
        return hashlib.sha1(q.read_bytes() if q.is_file() else str(q).encode()).hexdigest()[:n]
    except Exception:
        return None


def sniff_kind(path):
    ext = path.suffix.lower()
    head = b""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except Exception:
        pass
    if head[:4] == b"%PDF" or ext == ".pdf":
        return "pdf"
    if head[:2] == b"PK":
        try:
            names = zipfile.ZipFile(path).namelist()
        except Exception:
            names = []
        for pre, kind in (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx")):
            if any(n.startswith(pre) for n in names):
                return kind
        return "zip"
    if head[:4] in (b"\x89PNG", b"GIF8") or head[:2] == b"\xff\xd8":
        return "image"
    return {".csv": "csv", ".tsv": "csv", ".json": "json", ".jsonl": "json", ".md": "md",
            ".markdown": "md", ".tex": "tex", ".latex": "tex", ".html": "html", ".htm": "html",
            ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image",
            ".bmp": "image", ".gif": "image", ".svg": "image", ".doc": "legacy_office",
            ".xls": "legacy_office", ".ppt": "legacy_office"}.get(ext, "text")


def _pdf_text(path):
    for cmd in (["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
                ["pdftotext", "-enc", "UTF-8", str(path), "-"]):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=180)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace").split("\f"), "pdftotext"
        except Exception:
            continue
    return _pdf_raw(path).split("\f"), "raw_fallback"


def _pdf_raw(path):
    """无 pdftotext 时兜底：解压流并抽括号字符串。质量差，调用方标注 quality。"""
    try:
        data = Path(path).read_bytes()
    except Exception:
        return ""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        blob = m.group(1)
        try:
            import zlib
            blob = zlib.decompress(blob)
        except Exception:
            pass
        out.extend(t[1:-1] for t in re.findall(rb"\((?:\\.|[^\\)])*\)", blob))
    txt = b" ".join(out).decode("latin-1", "replace")
    return txt.replace("\\(", "(").replace("\\)", ")")


def _docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return ""
    import html as _h
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    return _h.unescape(re.sub(r"<[^>]+>", "", xml))


def _xlsx_text(path):
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                sx = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
                shared = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", sx, re.S)]
            for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
                sx = z.read(name).decode("utf-8", "replace")
                out.append("### %s" % name.rsplit("/", 1)[-1])
                for row in re.findall(r"<row[^>]*>(.*?)</row>", sx, re.S):
                    cells = []
                    for typ, body in re.findall(r"<c[^>]*?(?:t=\"(\w+)\")?[^>]*>(.*?)</c>", row, re.S):
                        v = re.search(r"<v>(.*?)</v>", body, re.S)
                        val = v.group(1) if v else re.sub(r"<[^>]+>", "", body)
                        if typ == "s" and val.strip().isdigit() and int(val) < len(shared):
                            val = shared[int(val)]
                        cells.append(val.strip())
                    if any(cells):
                        out.append(" | ".join(cells))
    except Exception:
        return ""
    return "\n".join(out)


def _json_text(obj):
    lines, seen = [], [0]

    def walk(n, p, d=0):
        if seen[0] > 400 or d > 6:
            return
        if isinstance(n, dict):
            for k, v in n.items():
                walk(v, "%s/%s" % (p, k), d + 1)
        elif isinstance(n, list):
            for i, v in enumerate(n[:80]):
                walk(v, "%s/%d" % (p, i), d + 1)
        elif n is not None and n != "":
            seen[0] += 1
            lines.append("%s = %s" % (p or "/", n))

    walk(obj, "")
    return "\n".join(lines)


def extract_material(path, rel, mid):
    """抽取材料为带 locator 的 unit 列表；不猜测无法解析的内容。"""
    kind = sniff_kind(path)
    rec = {"id": mid, "path": str(path), "rel": rel, "kind": kind, "bytes": 0,
           "units": [], "quality": "ok", "notes": [], "sha1": sha1(path), "chars": 0}
    try:
        rec["bytes"] = path.stat().st_size
    except Exception:
        pass
    pages, text = None, ""
    try:
        if kind == "pdf":
            pages, engine = _pdf_text(path)
            rec["notes"].append("pdf_engine:%s" % engine)
            if not any((p or "").strip() for p in pages):
                rec["quality"] = "no_text_layer"
                rec["notes"].append("pdf_no_text_layer: 建议 pdf-render + ocr；不得凭空推断内容")
        elif kind == "docx":
            text = _docx_text(path)
        elif kind == "xlsx":
            text = _xlsx_text(path)
        elif kind == "json":
            obj, err = load_json(path)
            text = _json_text(obj) if err is None else path.read_text(encoding="utf-8", errors="replace")
            if err:
                rec["notes"].append("json_material:%s" % err)
        elif kind in ("image", "legacy_office", "zip", "pptx"):
            rec["quality"] = "unreadable"
            rec["notes"].append("需 OCR/转换后才能读；已跳过，不得猜测内容")
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        rec["quality"] = "extract_failed"
        rec["notes"].append("extract_failed:%s" % exc)
    if pages is not None:
        for i, pg in enumerate(pages, 1):
            t = (pg or "").strip()
            if not t:
                continue
            if len(t) > 9000:
                for k, chunk in enumerate(re.split(r"\n\s*\n", t), 1):
                    if chunk.strip():
                        rec["units"].append({"locator": "%s:p%d.%d" % (mid, i, k), "text": chunk.strip()})
            else:
                rec["units"].append({"locator": "%s:p%d" % (mid, i), "text": t})
    else:
        rec["units"] = _text_units(mid, text)
    if not rec["units"] and rec["quality"] == "ok":
        rec["quality"] = "empty"
        rec["notes"].append("no_text_extracted")
    rec["chars"] = sum(len(u["text"]) for u in rec["units"])
    return rec


HEAD_RE = re.compile(r"^\s*(?:#{1,6}\s+\S|\d+(?:\.\d+)*[.)]?\s+[A-Z\u4e00-\u9fff][^\n]{0,60}$|"
                     r"(?:abstract|introduction|methods?|materials and methods|results?|discussion|"
                     r"conclusions?|references|摘要|引言|前言|方法|材料与方法|结果|讨论|结论|参考文献)\s*$)", re.I)


def _text_units(mid, text):
    units, sec, buf, start = [], "front", [], 1
    for idx, raw in enumerate((text or "").splitlines(), 1):
        line = raw.rstrip()
        if HEAD_RE.match(line) and len(line.strip()) <= 90:
            if buf:
                units.append(_mk_unit(mid, sec, start, buf))
                buf = []
            sec = re.sub(r"^#+\s*", "", line.strip())[:60] or sec
            start = idx
            continue
        if not line.strip():
            if buf:
                units.append(_mk_unit(mid, sec, start, buf))
                buf = []
            start = idx + 1
            continue
        buf.append(line)
        if sum(len(x) for x in buf) > 1400:
            units.append(_mk_unit(mid, sec, start, buf))
            buf, start = [], idx + 1
    if buf:
        units.append(_mk_unit(mid, sec, start, buf))
    return [u for u in units if u["text"].strip()]


def _mk_unit(mid, sec, start, buf):
    body = "\n".join(buf)
    if sec and sec != "front":
        return {"locator": "%s:§%s/L%d" % (mid, re.sub(r"\s+", "_", sec)[:24], start), "text": body}
    return {"locator": "%s:L%d" % (mid, start), "text": body}


INSTR_NAMES = ("task.md", "readme.md", "instruction.md", "instructions.md", "case_readme.md")


def index_input(inp):
    """递归索引输入目录，跳过 case.json。"""
    mats, used = [], set()
    base = Path(inp)
    files = [p for p in sorted(base.rglob("*"))] if base.is_dir() else []
    for p in files:
        if not p.is_file() or p.name.lower() == "case.json":
            continue
        stem = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", p.stem).strip("_")[:40] or "mat"
        mid, k = stem, 1
        while mid in used:
            k += 1
            mid = "%s%d" % (stem, k)
        used.add(mid)
        if p.stat().st_size > 40 << 20:
            mats.append({"id": mid, "path": str(p), "rel": str(p.relative_to(base)), "kind": "skipped",
                         "bytes": p.stat().st_size, "units": [], "quality": "skipped",
                         "notes": [">40MB,skipped"], "sha1": None, "chars": 0})
            continue
        rec = extract_material(p, str(p.relative_to(base)), mid)
        rec["role"] = "instruction" if p.name.lower() in INSTR_NAMES else "material"
        mats.append(rec)
    return {"root": str(base), "materials": mats,
            "stats": {"materials": len(mats), "chars": sum(m.get("chars", 0) for m in mats)}}


def qmatch(index, quote, locator=None):
    """逐字引文比对。返回 (ok, locator, material_id, note)。"""
    nq = norm(quote)
    if len(nq) < 8:
        return False, locator, None, "quote_too_short"
    hint = str(locator).split(":", 1)[0] if locator and ":" in str(locator) else None
    mats = [m for m in index.get("materials", []) if not hint or m.get("id") == hint]
    for m in mats:
        for u in m.get("units", []):
            if nq in norm(u.get("text", "")):
                return True, u.get("locator"), m.get("id"), "unit_hit"
    for m in mats:
        blob = norm("\n".join(u.get("text", "") for u in m.get("units", [])))
        if nq in blob:
            return True, (locator or "%s:coarse" % m.get("id")), m.get("id"), "coarse_hit"
    return False, locator, hint, "not_found"


def material_text(index, mid=None):
    return "\n".join(u["text"] for m in index.get("materials", [])
                     if (not mid or m["id"] == mid) and m.get("role") != "instruction"
                     for u in m.get("units", []))


def _sentences(text):
    return [p.strip() for p in re.split(r"(?<=[。．.;；!?！？])\s+|\n{2,}", text) if len(p.strip()) >= 12]


def extract_candidates(index, limit=40):
    """机械抽取"可能是被报告结果"的句子/表行，作为台账骨架；不做判定。"""
    rows, seen = [], set()
    for m in index.get("materials", []):
        if m.get("role") == "instruction":
            continue
        for u in m.get("units", []):
            for sent in _sentences(u.get("text", "")):
                low = sent.lower()
                has_p, has_ci = bool(RE_P.search(sent)), bool(RE_CI.search(sent))
                has_stat = bool(RE_STAT.search(sent)) and bool(re.search(r"\b(t|f|z|χ2|chi2|or|hr|rr|β)\b", low))
                is_tableish = sent.count("|") >= 2 and len(re.findall(r"\d", sent)) >= 4
                if not (has_p or has_ci or has_stat or is_tableish):
                    continue
                key = norm(sent)[:160]
                if key in seen:
                    continue
                seen.add(key)
                flags = []
                for words, tag in ((MC_WORDS, "mentions_multiple_comparison"), (ATT_WORDS, "mentions_attrition"),
                                   (SS_WORDS, "mentions_sample_size"), (EFF_WORDS, "mentions_effect_size")):
                    if any(w in low for w in words):
                        flags.append(tag)
                rows.append({"seed_id": "L-%02d" % (len(rows) + 1), "material": m["id"],
                             "source_locator": u.get("locator"), "quote": snip(sent, 300),
                             "observed_tokens": {
                                 "p": [x.group(0).strip() for x in RE_P.finditer(sent)][:3],
                                 "statistic": ["%s=%s" % (x.group(1), x.group(3)) for x in RE_STAT.finditer(sent)][:4],
                                 "ci": ["%s %s–%s" % (x.group(2), x.group(3), x.group(4)) for x in RE_CI.finditer(sent)][:2],
                                 "n": [x.group(1) for x in RE_N.finditer(sent)][:3]},
                             "flags": flags, "is_tableish": is_tableish})
                if len(rows) >= limit:
                    return rows
    return rows


def design_hints(index):
    """从正文词面提取设计/规范线索，供 Agent 判断口径（不是结论）。"""
    txt = material_text(index).lower()
    hints = {"design_words": sorted({w for w in DESIGN_WORDS if w in txt})[:8]}
    for kw, tag in (("consort", "CONSORT"), ("strobe", "STROBE"), ("prisma", "PRISMA"),
                    ("stard", "STARD"), ("trend", "TREND"), ("arrive", "ARRIVE")):
        if kw in txt:
            hints.setdefault("guidelines", []).append(tag)
    for kw, tag in (("trial regist", "registration"), ("clinicaltrials", "registration"),
                    ("ethic", "ethics"), ("irb", "ethics"), ("informed consent", "consent"),
                    ("conflict of interest", "coi"), ("data availability", "data_availability")):
        if kw in txt:
            hints.setdefault("norms_mentioned", []).append(tag)
    return hints


def _selftest():
    ok = True

    def chk(c, msg):
        nonlocal ok
        print(("PASS  " if c else "FAIL  ") + msg)
        ok = ok and bool(c)

    chk(norm("  P  = 0.03\u00a0 ") == "p = 0.03", "norm 处理空白/不换行空格")
    idx = {"materials": [{"id": "ms", "units": [
        {"locator": "ms:§Results/L10", "text": "The three groups differed (F(2,45)=3.21, p = 0.049)."},
        {"locator": "ms:§Results/L12", "text": "No confidence interval was reported for the primary effect."}]}]}
    chk(qmatch(idx, "F(2,45)=3.21, p = 0.049")[0], "逐字引文命中")
    chk(qmatch(idx, "F(2,45)=9.99")[0] is False, "伪造引文被拒绝")
    chk(qmatch(idx, "short")[0] is False, "过短引文被拒绝")
    chk(len(_text_units("m", "# Methods\nWe enrolled 120 patients.\n\n# Results\np = 0.02 (n = 120).")) >= 2,
        "标题切分为多个 unit")
    cands = extract_candidates(idx)
    chk(len(cands) >= 1 and cands[0]["observed_tokens"]["p"], "候选行抽取含 p 令牌")
    chk("design_words" in design_hints(idx), "设计线索块存在")
    print("\nSELFTEST(extract) %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
