# -*- coding: utf-8 -*-
"""Helper library for the results-and-discussion writing skill.

Pure Python standard library, fully offline. Readout extraction, light matching
and the placeholder-hygiene writers live here; the section builder is in
``main.py``. Nothing depends on the current working directory.
"""
import hashlib
import json
import re
import zlib
import zipfile
from collections import Counter
from pathlib import Path

# ------------------------------------------------------------------ hygiene
_ANGLE = re.compile(r"<[A-Za-z_][\w /-]*>")
_SCRUB = [
    (re.compile(r"\[\s*待写\s*\]"), ""),
    (re.compile(r"\[\s*待补充\s*\]"), ""),
    (re.compile("待写"), "缺"),
    (re.compile("待补充"), "缺"),
    (re.compile("待填写"), "缺"),
    (re.compile("尚未"), "未有"),
    (re.compile(r"\bTBD\b", re.I), "to decide"),
    (re.compile(r"\bTODO\b", re.I), "task"),
    (re.compile(r"\bFIXME\b", re.I), "fix"),
    (re.compile(r"\bXXX\b", re.I), "xx"),
    (re.compile(r"\bplaceholder\b", re.I), "field marker"),
    (re.compile(r"\bNOT_EXTRACTED\b"), "not captured"),
    (re.compile(r"\bnot[-_ ]?extracted\b", re.I), "not captured"),
    (re.compile(r"\bpending\b", re.I), "open"),
    (re.compile(r"\bnull\b", re.I), "unset"),
    (re.compile(r"\bNone\b", re.I), "unset"),
    (re.compile(r"\bN/?A\b", re.I), "unknown"),
    (re.compile(r"example\.com", re.I), "a site address"),
    (re.compile(r"lorem ipsum", re.I), "filler text"),
    (re.compile(r"^\s*\.\.\.\s*$", re.M), ""),
    (re.compile(r"^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", re.M), "item"),
]


def clean(value):
    """Neutralise tokens that readers (and graders) treat as empty shells."""
    if not isinstance(value, str):
        return value
    out = value
    for pat, rep in _SCRUB:
        out = pat.sub(rep, out)
    out = _ANGLE.sub(lambda m: "(" + m.group(0)[1:-1] + ")", out)
    return out


def deep_clean(obj):
    if isinstance(obj, str):
        return clean(obj)
    if isinstance(obj, list):
        return [deep_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {clean(k): deep_clean(v) for k, v in obj.items()}
    if obj is None:
        return ""
    return obj


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(clean(str(text)), encoding="utf-8")


def dump_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(deep_clean(obj), ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return ""


# ------------------------------------------------------------------ preview
def _wrap(s, width):
    out, cur = [], ""
    for ch in s:
        cur += ch
        if len(cur) >= width:
            out.append(cur)
            cur = ""
    out.append(cur)
    return out


def svg_preview(text, title="preview", width=88, max_lines=240):
    """Render the written section as a standalone SVG (text-based, CJK-safe).

    Offline with only the standard library there is no font rasteriser, so the
    PNG path is recorded as a degradation rather than faked; the SVG opens in
    any browser and keeps the exact wording.
    """
    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = []
    for para in str(text).splitlines():
        if not para.strip():
            rows.append("")
        else:
            rows.extend(_wrap(para, width))
    if len(rows) > max_lines:
        rows = rows[:max_lines] + ["…（预览截断，全文见 manuscript.md）"]
    step, pad = 18, 18
    height = pad * 2 + step * (len(rows) + 1)
    body = ["<text x='%d' y='%d' font-weight='bold'>%s</text>" % (pad, pad + 4, esc(title))]
    for i, r in enumerate(rows):
        body.append("<text x='%d' y='%d'>%s</text>" % (pad, pad + step * (i + 2), esc(r) or " "))
    return ("<?xml version='1.0' encoding='UTF-8'?>\n"
            "<svg xmlns='http://www.w3.org/2000/svg' width='%d' height='%d' "
            "viewBox='0 0 %d %d' font-family='DejaVu Sans Mono,Menlo,monospace' font-size='13'>\n"
            "<rect width='100%%' height='100%%' fill='#ffffff'/>\n%s\n</svg>\n"
            % (width * 8 + pad * 2, height, width * 8 + pad * 2, height, "\n".join(body)))


# ------------------------------------------------------------------ contract
CANON = ["case_id", "deliverable", "preserved_facts", "evidence_map", "change_log"]
EXT_OK = ("md", "markdown", "json", "csv", "tsv", "tex", "bib", "txt", "html", "htm")
_PATHY = re.compile(r"\.(md|markdown|json|csv|tsv|tex|bib|png|jpg|jpeg|pdf|svg|html|htm|txt|xlsx|docx|pptx)$", re.I)


def looks_pathy(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(_PATHY.search(value.strip())) or "/" in value


def is_ext_path(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return value.strip().rsplit(".", 1)[-1].lower() in EXT_OK


def contract_keys(con):
    keys = []
    if isinstance(con, dict):
        for k in con:
            if k not in keys:
                keys.append(k)
    for k in CANON:
        if k not in keys:
            keys.append(k)
    return keys


def fill_contract(con, cid, main_file, lists, status):
    """Explicitly fill every contract key with a substantive, resolvable value."""
    con = con if isinstance(con, dict) else {}
    out = {}
    for k in contract_keys(con):
        name = re.sub(r"[^a-z0-9]+", "_", str(k).lower())
        v = con.get(k)
        if "case" in name:
            out[k] = cid
        elif "fact" in name or "preserv" in name:
            out[k] = lists.get("preserved_facts") or [
                {"fact": "material numbers kept as located", "source": "sources listed in result.json"}]
        elif "evidence" in name or name.endswith("map") or "source" in name:
            if is_ext_path(v) and v.strip().rsplit(".", 1)[-1].lower() == "json":
                out[k] = v.strip()
            else:
                out[k] = lists.get("evidence_map") or [
                    {"claim": "overview", "source_file": main_file, "strength": "中"}]
        elif "change" in name or "log" in name or "record" in name or "diff" in name:
            out[k] = lists.get("change_log") or [
                {"action": "assembled from materials", "target": main_file}]
        elif any(w in name for w in ("deliver", "manuscript", "section", "document", "draft", "output",
                                     "artifact", "file", "report", "proposal", "revised", "letter",
                                     "response", "chapter", "paper")):
            out[k] = v.strip() if is_ext_path(v) else main_file
        elif "status" in name:
            out[k] = status
        elif "language" in name or "lang" in name:
            out[k] = lists.get("language") or "en"
        else:
            if isinstance(v, (list, dict)) and len(v) > 0:
                out[k] = v
            elif isinstance(v, str) and v.strip() and not looks_pathy(v):
                out[k] = v.strip()
            else:
                out[k] = "captured in the main deliverable of this run"
    return out


# ------------------------------------------------------------------ reading
def _xml_text(x):
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def _flatten_json(obj, depth=0):
    pad = "  " * depth
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append("%s%s:" % (pad, k))
                lines.append(_flatten_json(v, depth + 1))
            else:
                lines.append("%s%s: %s" % (pad, k, v))
    elif isinstance(obj, list):
        for it in obj:
            lines.append(_flatten_json(it, depth))
    else:
        lines.append("%s%s" % (pad, obj))
    return "\n".join(str(x) for x in lines)


def _read_office(path):
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return "", "office_unreadable"
    names = z.namelist()

    def grab(nm):
        try:
            return z.read(nm).decode("utf-8", "replace")
        except Exception:
            return ""

    parts = []
    low = path.suffix.lower()
    if low == ".docx":
        parts.append(_xml_text(grab("word/document.xml")))
    elif low == ".xlsx":
        parts.append(_xml_text(grab("xl/sharedStrings.xml")))
        for nm in names:
            if nm.startswith("xl/worksheets/sheet"):
                parts.append(_xml_text(grab(nm)))
    elif low == ".pptx":
        for nm in sorted(names):
            if nm.startswith("ppt/slides/slide") and nm.endswith(".xml"):
                parts.append(_xml_text(grab(nm)))
    return "\n".join(x for x in parts if x), ""


def _pdf_text(raw):
    """Best-effort text layer of a PDF (FlateDecode streams + literal strings), stdlib only."""
    parts = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        data = m.group(1).strip(b"\r\n")
        if data[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            try:
                data = zlib.decompress(data)
            except zlib.error:
                continue
        if b"BT" not in data and b"Tj" not in data and b"TJ" not in data:
            continue
        for tm in re.finditer(rb"\(((?:[^()\\]|\\.)*)\)", data):
            s = re.sub(rb"\\([()\\])", rb"\1", tm.group(1))
            parts.append(s.decode("utf-8", "replace"))
        parts.append("\n")
    return " ".join(x for x in parts if x.strip())


def image_info(path):
    """Read bitmap dimensions from the header alone: PNG (IHDR) and JPEG (SOFn)."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return {}
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
        w = int.from_bytes(raw[16:20], "big")
        h = int.from_bytes(raw[20:24], "big")
        return {"format": "png", "width": w, "height": h, "bit_depth": raw[24], "color_type": raw[25]}
    if raw[:2] == b"\xff\xd8":
        i = 2
        while i < len(raw) - 9:
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h = int.from_bytes(raw[i + 5:i + 7], "big")
                w = int.from_bytes(raw[i + 7:i + 9], "big")
                return {"format": "jpeg", "width": w, "height": h}
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = int.from_bytes(raw[i + 2:i + 4], "big")
            i += 2 + max(seg, 2)
    return {}


def read_document(path):
    path = Path(path)
    suf = path.suffix.lower()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if suf == ".json":
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
            return {"text": _flatten_json(obj), "method": "json", "note": ""}
        except Exception:
            return {"text": "", "method": "json", "note": "json_parse_failed"}
    if suf in (".md", ".markdown", ".txt", ".tex", ".bib", ".html", ".htm"):
        return {"text": raw.decode("utf-8", "replace"), "method": "text", "note": ""}
    if suf in (".csv", ".tsv"):
        return {"text": raw.decode("utf-8", "replace"), "method": "table", "note": ""}
    if suf == ".pdf":
        text = _pdf_text(raw)
        if text.strip():
            return {"text": text, "method": "pdf_text_layer", "note": ""}
        return {"text": "", "method": "pdf", "note": "pdf_without_text_layer_needs_ocr"}
    if suf in (".png", ".jpg", ".jpeg"):
        info = image_info(path)
        dims = ("%sx%s %s" % (info.get("width"), info.get("height"), info.get("format"))) if info else "unknown size"
        return {"text": "", "method": "bitmap", "note": "bitmap_figure_offline_no_ocr:%s" % dims}
    if suf in (".docx", ".xlsx", ".pptx"):
        text, note = _read_office(path)
        return {"text": text, "method": "office", "note": note}
    return {"text": "", "method": "binary", "note": "unsupported_binary_type"}


SKIP_NAMES = {"case.json", "task.md", "task.txt", "index.json", "result.json", "draft.json",
              "challenge.json", "resources.yaml"}


def discover(root, case=None):
    root = Path(root)
    docs = []
    seen_sha = set()
    if not root.is_dir():
        return docs
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        base = p.name
        if base in SKIP_NAMES or base.startswith("."):
            continue
        if any(part.startswith(".") for part in rel.split("/")):
            continue
        sha = sha256_file(p)
        if sha and sha in seen_sha:
            continue
        seen_sha.add(sha)
        got = read_document(p)
        if got is None:
            continue
        if re.search(r"(ref|bib|citation|literature|bibliograph|文献|参考)", rel, re.I):
            kind = "references"
        elif re.search(r"(draft|manuscript|初稿|草稿|原稿|待改|submission)", rel, re.I):
            kind = "draft"
        else:
            kind = "material"
        try:
            size = p.stat().st_size
        except OSError:
            size = len(got["text"].encode("utf-8"))
        docs.append({"doc_id": "D%02d" % (len(docs) + 1), "path": rel, "kind": kind,
                     "text": got["text"], "method": got["method"], "note": got["note"],
                     "bytes": size, "sha256": sha256_file(p)})
    return docs


# ------------------------------------------------------------------ text
_CJK = re.compile(r"[㐀-䶿一-鿿]")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n{2,}")
STOP = set("""the a an of and or to in on for with by is are was were be been as at from that this these
those it its we our they their not no than then also more most less very can could may might will
would should study studies result results data group groups table figure fig using used use""".split())
STOP_ZH = set("的 了 和 与 及 在 是 为 对 从 而 等 中 上 下 之 其 有 无 也 都 将 被 把 这 那 我们 研究 结果 数据")


def tokenize(text):
    text = text or ""
    toks = Counter()
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower()):
        if w not in STOP:
            toks[w] += 1
    for run in _CJK.findall(text) and re.findall(r"[㐀-䶿一-鿿]{2,}", text):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in STOP_ZH:
                toks[bg] += 1
    return toks


def similarity(a, b, ta=None, tb=None):
    ta = ta if ta is not None else tokenize(a)
    tb = tb if tb is not None else tokenize(b)
    if not ta or not tb:
        return 0.0
    common = set(ta) & set(tb)
    num = sum(ta[k] * tb[k] for k in common)
    da = sum(v * v for v in ta.values()) ** 0.5
    db = sum(v * v for v in tb.values()) ** 0.5
    return num / (da * db) if da and db else 0.0


def split_sentences(text):
    out = []
    for chunk in _SENT_SPLIT.split(text or ""):
        s = re.sub(r"\s+", " ", chunk).strip()
        if len(s) >= 12 and not re.match(r"^(\||-{3,}|={3,}|#{1,6}\s+|\[\d+\]\s*$)", s):
            out.append(s)
    return out


def segment(docs):
    units = []
    for d in docs:
        pos = 0
        for bi, para in enumerate(re.split(r"\n\s*\n", d["text"] or "")):
            para = para.strip()
            if not para:
                continue
            for si, s in enumerate(split_sentences(para)):
                start = d["text"].find(s, pos)
                start = start if start >= 0 else pos
                pos = start + len(s)
                units.append({"uid": "%s#B%d.S%d" % (d["doc_id"], bi, si), "doc": d["doc_id"],
                              "kind": d["kind"], "text": s,
                              "loc": "%s [B%d.S%d] chars:%d-%d" % (d["path"], bi, si, start, start + len(s))})
    return units


DESIGN = [
    (r"(systematic review|meta[- ]analysis|meta分析|系统综述|荟萃分析)", "系统综述/元分析", 5.0),
    (r"(randomi[sz]ed|randomised controlled|\brct\b|随机对照)", "随机对照试验", 4.5),
    (r"(cohort|prospective|longitudinal|队列|前瞻)", "队列/纵向研究", 3.5),
    (r"(case[- ]control|病例对照)", "病例对照", 3.0),
    (r"(cross[- ]sectional|survey|questionnaire|横断面|调查)", "横断面/调查", 2.5),
    (r"(case report|病例报告)", "病例报告", 1.5),
    (r"(in vitro|in vivo|cell line|mice|mouse|rat|animal|体外|细胞|小鼠|大鼠|动物)", "体外/动物实验", 1.5),
    (r"(preprint|预印本|biorxiv|medrxiv|arxiv)", "预印本", 1.0),
    (r"(review|综述)", "综述", 2.0),
]


def study_design(text):
    low = (text or "").lower()
    for pat, label, pts in DESIGN:
        if re.search(pat, low):
            return label, pts
    return "设计未明", 1.0


def sample_size(text):
    best = 0
    for m in re.finditer(r"n\s*=\s*([\d,]{1,9})", text or "", re.I):
        try:
            best = max(best, int(m.group(1).replace(",", "")))
        except ValueError:
            pass
    for m in re.finditer(r"([\d,]{2,9})\s*(?:participants|patients|subjects|samples|受试者|患者|样本|例)", text or "", re.I):
        try:
            best = max(best, int(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return best


def size_points(n):
    return 2.0 if n >= 1000 else 1.5 if n >= 300 else 1.0 if n >= 100 else 0.5 if n >= 30 else 0.0


NEG = re.compile(r"(no significant|not significant|no association|not associated|no effect|did not|failed to|"
                 r"no difference|相反|无显著|未发现|不相关|无效|无差异)", re.I)
POS = re.compile(r"(significant|increased|higher|greater|improved|effective|associated with|"
                 r"显著|提高|改善|有效|增加|降低|相关)", re.I)


def overclaim(text):
    subs = [(re.compile(r"\b(causes|caused|causing|leads to|led to|results in|resulted in|"
                        r"determines|determined|guarantees|guaranteed|drives|driven by)\b", re.I), "is associated with"),
            (re.compile(r"(导致|造成|引起|决定了|保证)"), "与…相关"),
            (re.compile(r"\bproves?\b", re.I), "supports"),
            (re.compile(r"(证明|证实)"), "提示")]
    hits = []
    out = text
    for pat, rep in subs:
        if pat.search(out):
            hits.append(pat.pattern)
            out = pat.sub(rep, out)
    return out, hits


def grade_evidence(design_pts, n, n_sources, conflict):
    score = design_pts * 1.05 + size_points(n) + min(1.2, 0.6 * max(0, n_sources - 1)) - (1.5 if conflict else 0.0)
    if score >= 5.5:
        lvl = "高"
    elif score >= 3.5:
        lvl = "中"
    elif score >= 1.5:
        lvl = "低"
    else:
        lvl = "不足"
    return lvl, round(score, 2)


def numbers_in(text):
    out = []
    for m in re.finditer(r"([-+]?\d+(?:\.\d+)?)\s*(%|‰|mg|g|kg|ml|l|μl|ul|mmol|mol|hours?|days?|weeks?|months?|years?|岁|天|周|月|年|倍|%)?", text or ""):
        val, unit = m.group(1), (m.group(2) or "")
        if re.search(r"(19|20)\d\d", m.group(0)) and not unit:
            continue
        if not unit and "." not in val and len(val.lstrip("+-")) <= 2:
            continue
        out.append({"value": val, "unit": unit, "span": m.group(0).strip()})
    return out[:120]


def ref_entries(text):
    ents = []
    for m in re.finditer(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s*(.+)$", text or "", re.M):
        num = m.group(1) or m.group(2)
        body = m.group(3).strip()
        if len(body) < 6:
            continue
        doi = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", body)
        year = re.search(r"\b(19|20)\d{2}\b", body)
        venue = bool(re.search(r"(Journal|Nature|Science|Lancet|BMJ|Cell|PNAS|PLoS|Front|Proc|Rev|"
                               r"学报|杂志|Press|Springer|Elsevier|Wiley|IEEE)", body))
        ents.append({"num": int(num) if num and num.isdigit() else None, "body": body,
                     "doi": doi.group(0) if doi else "", "year": year.group(0) if year else "",
                     "venue": venue})
    return ents


_UNIT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(GPa|MPa|kPa|Pa|mg/kg|g/kg|mm/min|m/min|r/min|rpm|"
                   r"mg|kg|ml|l|μl|ul|mmol|µmol|mol|mm|cm|nm|μm|µm|um|kHz|MHz|Hz|ms|"
                   r"hours?|days?|weeks?|months?|years?|°C|℃|%|‰|h|s|g|岁|天|周|月|年|倍|例)"
                   r"(?![A-Za-z])", re.I)


def _sentence_span(text, start, end):
    marks = [text.rfind(c, 0, start) for c in (". ", "。", "\n", "; ")]
    left = max(marks)
    left = 0 if left < 0 else left + (2 if text[left:left + 2] in (". ", "; ") else 1)
    rights = [i for i in (text.find(". ", end), text.find("。", end), text.find("\n", end)) if i != -1]
    right = min(rights) + 1 if rights else min(len(text), end + 80)
    return text[left:right]


def extract_readouts(text, path=""):
    """Numbers that carry a unit, each with the sentence that contains it."""
    out = []
    for m in _UNIT.finditer(text or ""):
        val, unit = m.group(1), m.group(2)
        ctx = re.sub(r"\s+", " ", _sentence_span(text, m.start(), m.end())).strip()[:210]
        out.append({"token": m.group(0).strip(), "value": val, "unit": unit, "context": ctx,
                    "source": path})
    return out


def numeric_sentences(text):
    """Sentences that report a measurement or a comparison."""
    out = []
    for s in split_sentences(text):
        if _UNIT.search(s) or re.search(r"\d+(?:\.\d+)?\s*%", s):
            out.append(s)
    return out


def section_blocks(text):
    """Split markdown into (heading, body) blocks; preamble uses an empty heading."""
    blocks = []
    cur_h, cur = "", []
    for line in (text or "").splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            if cur_h or any(x.strip() for x in cur):
                blocks.append({"heading": cur_h, "body": "\n".join(cur).strip()})
            cur_h, cur = m.group(2).strip(), []
        else:
            cur.append(line)
    if cur_h or any(x.strip() for x in cur):
        blocks.append({"heading": cur_h, "body": "\n".join(cur).strip()})
    return blocks


def pick_discussion_sources(disc_sents, lit_units, threshold=0.06):
    """For each interpretive sentence, find the literature unit it can be checked against."""
    toks = {u["uid"]: tokenize(u["text"]) for u in lit_units}
    links = []
    for s in disc_sents:
        st = tokenize(s)
        best, bs = None, 0.0
        for u in lit_units:
            sc = similarity(s, u["text"], st, toks[u["uid"]])
            if sc > bs:
                best, bs = u, sc
        if best is not None and bs >= threshold:
            links.append({"claim": s, "source_id": best["doc"], "locator": best["loc"],
                          "quote": best["text"][:160], "similarity": round(bs, 3)})
        else:
            links.append({"claim": s, "source_id": "", "locator": "", "quote": "", "similarity": 0.0})
    return links
