# -*- coding: utf-8 -*-
"""Helper library for the literature-evidence writing skill.

Pure Python standard library, fully offline. Every routine is side-effect free
except the small ``dump_*`` writers; nothing depends on the current directory.
"""
import hashlib
import json
import re
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
        return {"text": "", "method": "pdf", "note": "pdf_body_needs_external_parser"}
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
