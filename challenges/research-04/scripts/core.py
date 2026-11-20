#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.py -- 语料解析、索引构建与工作稿校验。仅标准库；离线；不依赖 CWD。"""
import csv, json, re, shutil, subprocess, unicodedata, zipfile, zlib
from collections import Counter, defaultdict
from pathlib import Path

EVENT_TYPES = ["proposal", "validation", "refutation", "method_introduced",
               "merged", "split", "declined", "application_transfer"]
YEAR_SOURCES = ["published", "online", "preprint", "venue", "unknown"]
GAP_TYPES = ["missing_validation", "stalled_theme", "no_transfer",
             "unresolved_conflict", "retrieval_gap"]
LIFECYCLES = ["emerging", "consolidating", "maturing", "declining"]
CRITERIA = ["first_of_type", "type_shift", "density_jump", "theme_birth", "theme_death"]
CONFIDENCE = ["high", "medium", "low"]
OVERREACH = ["显著", "证明", "必然", "毫无疑问", "完全确立", "significantly", "proves"]
TEXT_EXT = {".md", ".markdown", ".txt", ".text", ".rst", ".tex", ".json", ".jsonl",
            ".csv", ".tsv", ".yaml", ".yml", ".xml", ".bib", ".html", ".htm"}
CUES = {
    "proposal": r"propose|proposed|hypothes|we suggest|we argue|put forward|提出|设想|假设|构想",
    "validation": r"demonstrat|confirm|we show|we find|validat|verify|验证|证实|支持了|观察到",
    "refutation": r"fail(?:s|ed)? to|cannot reproduce|contradict|refut|challeng|反驳|未能|不一致|相反",
    "method_introduced": r"we introduce|novel method|new (?:method|framework|approach|dataset|model)|first (?:time )?.{0,20}method|首次|新方法|提出了.{0,12}方法",
    "merged": r"combin|integrat|unify|merg|bridge|结合|融合|统一|打通",
    "split": r"distinguish|split into|two (?:classes|families)|diverg|separate|分为|分化|区分",
    "declined": r"supersed|no longer|obsolet|abandon|fall(?:s|en)? out of|被取代|逐渐(?:减少|消退)|降温|不再",
    "application_transfer": r"applied to|apply to|extend(?:ed)? to|transfer|deploy|应用于|推广到|迁移到|移植到",
}


# ---------------------------------------------------------------- 文本解析

# ---- 文本解析 ----
def dec(b):
    for e in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def _pdf_streams(data):
    out = []
    for m in re.finditer(rb"stream\r?\n?(.*?)endstream", data, re.S):
        s = m.group(1)
        try:
            s = zlib.decompress(s)
        except Exception:
            pass
        out.append(s)
    return out


def pdf_text(p):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"],
                               capture_output=True, timeout=60)
            t = dec(r.stdout or b"")
            if len(t.strip()) > 40:
                return t, "pdftotext"
        except Exception:
            pass
    try:
        data = Path(p).read_bytes()
        chunks = []
        for s in _pdf_streams(data):
            for m in re.finditer(rb"\((?:\\.|[^\\()])*\)", s):
                raw = m.group(0)[1:-1]
                raw = re.sub(rb"\\([()\\])", rb"\1", raw)
                try:
                    chunks.append(raw.decode("latin-1"))
                except Exception:
                    pass
        t = " ".join(chunks)
        t = re.sub(r"\s{2,}", " ", t)
        if len(t.strip()) > 40:
            return t, "builtin-pdf-lowconf"
    except Exception:
        pass
    return "", "pdf-unreadable"


def docx_text(p):
    try:
        with zipfile.ZipFile(p) as z:
            x = z.read("word/document.xml").decode("utf-8", "replace")
        x = re.sub(r"</w:p>", "\n\n", x)
        x = re.sub(r"<[^>]+>", "", x)
        return re.sub(r"[ \t]{2,}", " ", x), "docx-xml"
    except Exception:
        return "", "docx-unreadable"


def xlsx_text(p):
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            ss = []
            if "xl/sharedStrings.xml" in names:
                raw = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
                for si in re.findall(r"<si>(.*?)</si>", raw, re.S):
                    ss.append("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
            rows = []
            for n in [x for x in names if re.match(r"xl/worksheets/sheet\d+\.xml$", x)]:
                raw = z.read(n).decode("utf-8", "replace")
                for r in re.findall(r"<row[^>]*>(.*?)</row>", raw, re.S):
                    cells = []
                    for c in re.findall(r"<c[^>]*?(?:t=\"(\w+)\")?[^>]*>(?:<v>(.*?)</v>|<is>.*?</is>)?</c>", r, re.S):
                        t, v = c
                        v = v or ""
                        if t == "s" and v.isdigit() and int(v) < len(ss):
                            v = ss[int(v)]
                        cells.append(v)
                    if any(cells):
                        rows.append(" | ".join(cells))
            return "\n\n".join(rows), "xlsx-xml"
    except Exception:
        return "", "xlsx-unreadable"


def kind_of(p):
    s = p.suffix.lower()
    try:
        head = p.open("rb").read(8)
    except Exception:
        head = b""
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        if s == ".docx":
            return "docx"
        if s == ".xlsx":
            return "xlsx"
    if s in (".md", ".markdown"):
        return "markdown"
    if s in (".json",):
        return "json"
    if s in (".jsonl",):
        return "jsonl"
    if s in (".csv", ".tsv"):
        return "csv"
    if s in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return "image"
    if s == ".pdf":
        return "pdf"
    if s in TEXT_EXT:
        return "text"
    return "text"


def extract(p):
    k = kind_of(p)
    if k == "pdf":
        return pdf_text(p)
    if k == "docx":
        return docx_text(p)
    if k == "xlsx":
        return xlsx_text(p)
    if k == "image":
        return "", "image-no-ocr"
    try:
        return dec(Path(p).read_bytes()), k
    except Exception:
        return "", "unreadable"


def split_paras(t, maxp=80, minlen=3):
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+\n", "\n", t)
    raw = [x.strip() for x in re.split(r"\n\s*\n", t)]
    paras = [x for x in raw if len(x) >= minlen]
    if len(paras) <= 2 and len(t) > 1200:
        sents = re.split(r"(?<=[。！？.!?])\s+", t)
        buf, cur = [], ""
        for s in sents:
            if len(cur) + len(s) > 700:
                if cur:
                    buf.append(cur.strip())
                cur = s
            else:
                cur += " " + s
        if cur.strip():
            buf.append(cur.strip())
        paras = buf
    out = []
    for x in paras[:maxp]:
        out.append(re.sub(r"\n{2,}", "\n", x)[:2000])
    return out


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", "", s).lower()


# ---------------------------------------------------------------- 输入发现


def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        try:
            return json.loads(dec(Path(p).read_bytes()))
        except Exception:
            return None


def discover_case(inp):
    """返回 (case_dict, path_or_None, degradations)。"""
    degr = []
    p = Path(inp) / "case.json"
    if p.is_file():
        c = load_json(p)
        if isinstance(c, dict):
            return c, p, degr
        degr.append("case.json 不是合法 JSON 对象，已尝试回退")
    else:
        degr.append("未找到 /input/case.json")
    hits = []
    for q in sorted(Path(inp).rglob("*.json")):
        if q.name in ("case.json",) or q.stat().st_size > 2_000_000:
            continue
        o = load_json(q)
        if isinstance(o, dict) and ("output_contract" in o or "case_id" in o):
            hits.append((q, o))
    if hits:
        hits.sort(key=lambda x: (0 if "output_contract" in x[1] else 1, len(str(x[0]))))
        degr.append("回退使用 %s 作为 case 描述" % hits[0][0])
        return hits[0][1], hits[0][0], degr
    degr.append("未找到任何含 output_contract 的 JSON，使用内置默认契约")
    return {}, None, degr


def load_records(inp):
    """records.jsonl / records.json / case 内嵌 records。"""
    recs, src = [], None
    for name in ("records.jsonl", "records.json", "records.ndjson"):
        p = Path(inp) / name
        if not p.is_file():
            continue
        src = p
        if p.suffix == ".json":
            o = load_json(p)
            if isinstance(o, list):
                recs = [x for x in o if isinstance(x, dict)]
            elif isinstance(o, dict):
                for k in ("records", "items", "data", "entries"):
                    if isinstance(o.get(k), list):
                        recs = [x for x in o[k] if isinstance(x, dict)]
                        break
        else:
            for line in dec(p.read_bytes()).splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
        break
    if not recs:
        for q in sorted(Path(inp).rglob("*records*.json*")):
            if q.stat().st_size > 1_000_000:
                continue
            o = load_json(q)
            if isinstance(o, list) and o and isinstance(o[0], dict):
                recs, src = o, q
                break
    return recs, src


def pick(d, *names, default=None):
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n in d and d[n] not in (None, "", [], {}):
            return d[n]
        if n.lower() in low and low[n.lower()] not in (None, "", [], {}):
            return low[n.lower()]
    return default


def as_year(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v if 1800 <= v <= 2100 else None
    m = re.search(r"(19[5-9]\d|20[0-4]\d)", str(v))
    return int(m.group(1)) if m else None


def guess_year(text, rec=None):
    """返回 (year, year_source)。不猜：找不到就 None/unknown。"""
    if rec:
        for key, ys in (("year", None), ("published_year", "published"), ("year_published", "published"),
                        ("publication_year", "published"), ("year_online", "online"),
                        ("online_year", "online"), ("preprint_year", "preprint")):
            y = as_year(pick(rec, key))
            if y:
                src = pick(rec, "year_source", default=None) or ys or "published"
                return y, (src if src in YEAR_SOURCES else "published")
    head = (text or "")[:700]
    for pat, ys in ((r"(?:published|见刊|发表)[^\d]{0,12}(19[5-9]\d|20[0-4]\d)", "published"),
                    (r"(?:online|在线)[^\d]{0,12}(19[5-9]\d|20[0-4]\d)", "online"),
                    (r"(?:preprint|arXiv|bioRxiv|medRxiv)[^\d]{0,14}(19[5-9]\d|20[0-4]\d)", "preprint"),
                    (r"\((19[5-9]\d|20[0-4]\d)\)", "published"),
                    (r"\b(19[5-9]\d|20[0-4]\d)\b[^\n]{0,40}(?:vol\.|volume|pp\.|doi)", "venue")):
        m = re.search(pat, head, re.I)
        if m:
            return int(m.group(1)), ys
    m = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", head)
    if m:
        return int(m.group(1)), "published"
    return None, "unknown"


def mat_title(text, rec, name):
    for k in ("title", "name", "paper_title"):
        v = pick(rec, k) if rec else None
        if v:
            return str(v)[:160]
    for line in (text or "").splitlines()[:6]:
        line = line.strip().lstrip("#").strip()
        if 8 <= len(line) <= 160:
            return line[:160]
    return Path(name).stem[:160]


def scan(inp):
    """返回 (materials, records, degradations)。materials: [{path,kind,text,method,rec}]"""
    degr, mats = [], []
    root = Path(inp)
    skip_name = re.compile(r"^(case\.json|task\.md|.*records?\.(json|jsonl|ndjson)|protocol\.md|"
                           r"environment|resources\.yaml|readme\.md)$", re.I)
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            if p.stat().st_size > 40_000_000:
                degr.append("跳过超大文件 %s" % p.name)
                continue
        except Exception:
            continue
        files.append(p)
    recs, recpath = load_records(root)
    for p in files:
        rel = str(p.relative_to(root))
        if skip_name.match(p.name) or rel.startswith("reference"):
            continue
        if p.suffix.lower() in (".py", ".pyc"):
            continue
        text, method = extract(p)
        if method.endswith("unreadable") or method == "image-no-ocr":
            degr.append("%s 无法抽取文本（%s），仅登记元数据" % (rel, method))
        rec = match_record(recs, p, text)
        mats.append({"path": str(p), "rel": rel, "kind": kind_of(p), "text": text,
                     "method": method, "rec": rec})
    if not mats:
        degr.append("未发现任何可读材料（/input 下无文件或均不可解析）")
    return mats, recs, degr


def match_record(recs, p, text):
    if not recs:
        return None
    base = p.stem.lower()
    for r in recs:
        for k in ("file", "filename", "source", "source_file", "path", "local_path"):
            v = str(pick(r, k, default="") or "").lower()
            if v and (base in v or Path(v).stem.lower() == base):
                return r
    head = norm(text)[:400]
    for r in recs:
        t = str(pick(r, "title", "paper_title", "name", default="") or "")
        if len(t) > 12 and norm(t)[:60] and norm(t)[:60] in head:
            return r
    if len(recs) == 1 and len(recs) == 1:
        return recs[0]
    return None


# ---------------------------------------------------------------- 索引构建


def build_index(case, inp, mats, degr):
    srcs, paras = [], []
    for i, m in enumerate(mats, 1):
        sid = "S%02d" % i
        rec = m.get("rec")
        y, ys = guess_year(m.get("text", ""), rec)
        y_alt = None
        if rec:
            for k in ("year_online", "online_year", "preprint_year", "year_alt"):
                v = as_year(pick(rec, k))
                if v and v != y:
                    y_alt = v
                    break
        themes = pick(rec, "themes", "theme", "topics", "tags", default=None) if rec else None
        if isinstance(themes, str):
            themes = [themes]
        if not isinstance(themes, list):
            themes = []
        venue = pick(rec, "venue", "journal", "conference", "publisher", default="") if rec else ""
        title = mat_title(m.get("text", ""), rec, m["path"])
        segs = split_paras(m.get("text", ""))
        if not segs and m.get("text"):
            segs = [m["text"][:800]]
        plist = []
        for j, s in enumerate(segs, 1):
            loc = "%s:P%02d" % (sid, j)
            plist.append({"locator": loc, "text": s, "chars": len(s)})
            paras.append({"locator": loc, "source_id": sid, "text": s})
        srcs.append({"source_id": sid, "title": title, "name": Path(m["path"]).name,
                     "rel": m["rel"], "kind": m["kind"], "method": m["method"],
                     "year": y, "year_source": ys if y else "unknown", "year_alt": y_alt,
                     "venue": venue or "", "themes": themes, "has_fulltext": len(m.get("text", "")) > 200,
                     "chars": len(m.get("text", "")), "paragraphs": plist,
                     "sha256_16": _sha(m.get("text", ""))})
    vocab = pick(case, "themes", "topics", "theme_vocab", "subdomains", default=None)
    if isinstance(vocab, dict):
        vocab = list(vocab.keys())
    if not isinstance(vocab, list):
        vocab = []
    idx = {"case_id": pick(case, "case_id", "id", "caseId", default="UNKNOWN-CASE"),
           "task_instruction": pick(case, "task_instruction", "instruction", "task", default=""),
           "research_question": pick(case, "research_question", "question", "topic", default=""),
           "time_range": pick(case, "time_range", "years", "window", default=None),
           "output_contract": pick(case, "output_contract", "contract", "output", default={}),
           "theme_vocab": vocab, "sources": srcs, "paragraphs": paras,
           "degradations": degr, "input_dir": str(inp)}
    if not idx["research_question"] and idx["task_instruction"]:
        idx["research_question"] = str(idx["task_instruction"])[:200]
    return idx


def _sha(t):
    import hashlib
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()[:16]


def corpus_facts(idx):
    """无 draft 时的确定性事实底座：年度来源计数（仅用登记年份，不猜）。"""
    yr = Counter()
    unknown = 0
    for s in idx.get("sources", []):
        if s.get("year"):
            yr[str(s["year"])] += 1
        else:
            unknown += 1
    return {"by_year_sources": dict(sorted(yr.items())), "sources_without_year": unknown}


# ---------------------------------------------------------------- 事件候选


def candidate_events(idx, limit=24):
    """规则化候选事件（低置信，供 Agent 改写）。quote 为原文子串，绝不拼造。"""
    out = []
    seen = set()
    yrs = {s["source_id"]: s.get("year") for s in idx.get("sources", [])}
    for p in idx.get("paragraphs", []):
        if len(out) >= limit * 3:
            break
        for etype, pat in CUES.items():
            m = re.search(pat, p["text"], re.I)
            if not m:
                continue
            sent = _sentence_at(p["text"], m.start())
            key = (p["locator"], etype, norm(sent)[:80])
            if key in seen or len(sent) < 12:
                continue
            seen.add(key)
            out.append({"event_id": "C%02d" % (len(out) + 1), "year": yrs.get(p["source_id"]),
                        "year_source": "published" if yrs.get(p["source_id"]) else "unknown",
                        "event_type": etype, "statement": re.sub(r"\s+", " ", sent)[:200],
                        "source_id": p["source_id"], "locator": p["locator"], "quote": sent[:400],
                        "theme_id": "T1", "method": "", "object": "", "confidence": "low",
                        "reviewed": False, "auto": True})
            if len(out) >= limit:
                return out
    return out


def _sentence_at(text, pos):
    a = max(text.rfind("。", 0, pos), text.rfind(". ", 0, pos), text.rfind("\n", 0, pos))
    b = len(text)
    for ch in ("。", "！", "？"):
        i = text.find(ch, pos)
        if i != -1:
            b = min(b, i + 1)
    for pat in (". ", "? ", "! "):
        i = text.find(pat, pos)
        if i != -1:
            b = min(b, i + 1)
    start = a + 1 if a >= 0 else 0
    return text[start:b].strip()


# ---------------------------------------------------------------- 校验


def validate(draft, idx, prev_stats=None):
    ev = [e for e in (draft.get("events") or []) if isinstance(e, dict)]
    errs, hints = [], []
    pmap = {p["locator"]: p["text"] for p in idx.get("paragraphs", [])}
    sids = {s["source_id"] for s in idx.get("sources", [])}
    full = {s["source_id"]: norm(" ".join(p["text"] for p in s["paragraphs"]))
            for s in idx.get("sources", [])}
    eid = set()
    for i, e in enumerate(ev, 1):
        tag = e.get("event_id") or "E%02d" % i
        if not e.get("event_id"):
            errs.append("%s EV_NO_ID：缺 event_id" % tag)
        eid.add(str(e.get("event_id") or tag))
        if e.get("event_type") not in EVENT_TYPES:
            errs.append("%s EV_TYPE_INVALID：%r 不在枚举 %s" % (tag, e.get("event_type"), "/".join(EVENT_TYPES)))
        y = e.get("year")
        if y is None:
            errs.append("%s EV_YEAR_MISSING：year 为空（缺年份须显式 null 且 year_source=unknown，"
                        "但事件不能无年）" % tag)
        elif not (isinstance(y, int) and 1800 <= y <= 2100):
            errs.append("%s YEAR_INVALID：%r" % (tag, y))
        if e.get("year_source") not in YEAR_SOURCES:
            errs.append("%s YEAR_SOURCE_INVALID：%r" % (tag, e.get("year_source")))
        if not str(e.get("source_id") or "") in sids:
            errs.append("%s SRC_NO_ID：source_id=%r 不在语料登记中" % (tag, e.get("source_id")))
        loc = str(e.get("locator") or "")
        q = str(e.get("quote") or "")
        if not q.strip():
            errs.append("%s EV_NO_QUOTE：缺逐字 quote" % tag)
        elif not loc:
            errs.append("%s EV_NO_LOCATOR：缺 locator" % tag)
        else:
            ptext = pmap.get(loc)
            if ptext is None:
                errs.append("%s LOC_MISS：locator %s 不存在（用 show 查真实段号）" % (tag, loc))
            elif norm(q) not in norm(ptext):
                if norm(q) in full.get(str(e.get("source_id")), ""):
                    errs.append("%s QUOTE_NOT_IN_LOCATOR：quote 命中该来源其他段，locator %s 不准确" % (tag, loc))
                else:
                    errs.append("%s QUOTE_MISS：quote 未在 %s 命中（须逐字，可短不可改）" % (tag, loc))
        st = str(e.get("statement") or "")
        if not st.strip():
            errs.append("%s EV_NO_STATEMENT：缺 statement" % tag)
        if any(w in st for w in ("重要突破", "里程碑", "开创性", "巨大影响")):
            hints.append("%s EV_STATEMENT_EVALUATIVE：statement 含无证据评价词，改为事实陈述" % tag)
        if e.get("confidence") not in CONFIDENCE:
            hints.append("%s CONF_INVALID：confidence 建议取 high/medium/low" % tag)
        if e.get("auto") and not e.get("reviewed"):
            hints.append("%s 仍为脚本候选（auto=true, reviewed=false）：请读原文后改写或删除" % tag)
        nums = re.findall(r"(?:19[5-9]\d|20[0-4]\d)", st)
        if nums and q and not any(n in q for n in nums):
            hints.append("%s NUM_UNSOURCED：statement 年份 %s 未出现在 quote 中，确认来源" % (tag, nums))
    # 时序一致性
    first_prop = {}
    for e in ev:
        if e.get("event_type") == "proposal" and isinstance(e.get("year"), int):
            t = e.get("theme_id") or "T1"
            first_prop[t] = min(first_prop.get(t, 9999), e["year"])
    for e in ev:
        if e.get("event_type") in ("validation", "refutation") and isinstance(e.get("year"), int):
            t = e.get("theme_id") or "T1"
            if t in first_prop and e["year"] < first_prop[t]:
                hints.append("%s CHRONO_CONFLICT：%s 年早于主题 %s 的首次 proposal（%s 年），"
                             "标注 chronology_conflict 并写入 uncertainty" % (e.get("event_id"), e["year"], t, first_prop[t]))
    # 阶段
    stages = [s for s in (draft.get("stage_division") or []) if isinstance(s, dict)]
    for i, s in enumerate(stages, 1):
        tag = s.get("stage_id") or "G%d" % i
        basis = [b for b in (s.get("basis_event_ids") or []) if str(b) in eid]
        if not basis:
            errs.append("%s STAGE_NO_BASIS：basis_event_ids 为空或不存在" % tag)
        yr = s.get("year_range")
        if not (isinstance(yr, (list, tuple)) and len(yr) == 2 and all(isinstance(x, int) for x in yr)):
            errs.append("%s STAGE_YEAR_RANGE：year_range 须为 [起始年, 结束年]" % tag)
        elif yr[0] > yr[1]:
            errs.append("%s STAGE_YEAR_ORDER：year_range 起止颠倒" % tag)
    for a, b in zip(stages, stages[1:]):
        ya, yb = a.get("year_range"), b.get("year_range")
        if isinstance(ya, (list, tuple)) and isinstance(yb, (list, tuple)) and ya and yb and yb[0] - ya[1] > 1:
            hints.append("STAGE_GAP：%s→%s 之间存在空白年（%s–%s），需在 rationale 说明" % (a.get("stage_id"), b.get("stage_id"), ya[1], yb[0]))
    # 转折
    turns = [t for t in (draft.get("turning_points") or []) if isinstance(t, dict)]
    for i, t in enumerate(turns, 1):
        tag = t.get("turning_id") or "P%d" % i
        if not [x for x in (t.get("event_ids") or []) if str(x) in eid]:
            errs.append("%s TURNING_EVENT_MISSING：event_ids 为空或不在台账" % tag)
        ch = t.get("criteria_hit")
        if isinstance(ch, str):
            ch = [ch]
        if not ch or any(c not in CRITERIA for c in (ch or [])):
            errs.append("%s TURNING_NO_CRITERIA：criteria_hit 须取 %s" % (tag, "/".join(CRITERIA)))
    # 空白
    gaps = [g for g in (draft.get("gaps") or []) if isinstance(g, dict)]
    for i, g in enumerate(gaps, 1):
        tag = g.get("gap_id") or "N%d" % i
        if g.get("gap_type") not in GAP_TYPES:
            errs.append("%s GAP_TYPE_INVALID：%r 不在 %s" % (tag, g.get("gap_type"), "/".join(GAP_TYPES)))
        evid = [x for x in (g.get("events_evidence") or []) if str(x) in eid]
        if not evid:
            errs.append("%s GAP_NO_EVENT_EVIDENCE：events_evidence 为空或不在台账" % tag)
        if not str(g.get("search_scope") or "").strip():
            errs.append("%s GAP_NO_SCOPE：search_scope 为空（写清检索词/范围）" % tag)
        if not str(g.get("exclusion_evidence") or "").strip():
            errs.append("%s GAP_NO_EXCLUSION：exclusion_evidence 为空（说明为何不是检索遗漏）" % tag)
    # 代表作覆盖
    from derive import compute_stats, coverage
    stats = compute_stats(ev)
    cov = coverage(idx, ev, stats)
    if cov["small_sample"]:
        blob = " ".join([str(e.get("statement") or "") for e in ev] +
                        [str(draft.get("research_question") or "")] +
                        [str(t.get("why_turning") or "") for t in turns])
        hit = [w for w in OVERREACH if w in blob]
        if hit:
            hints.append("CLAIM_OVERREACH：small_sample=true 时禁用 %s 类断言，改'提示性/初步'" % hit[:3])
    if stats.get("mismatch"):
        errs.append("STAT_MISMATCH：%s" % stats["mismatch"])
    if prev_stats and prev_stats.get("by_year") is not None:
        if prev_stats.get("by_year") != stats.get("by_year"):
            errs.append("STAT_DRIFT：derived/trend_stats.json 与当前台账重算不一致，重跑 build")
    rep = {"errors": errs, "hints": hints, "stats": stats, "coverage": cov,
           "events": len(ev), "stages": len(stages), "turning": len(turns), "gaps": len(gaps),
           "event_ids": sorted(eid), "stages_obj": stages}
    if not ev:
        rep["errors"].append("EV_EMPTY：台账为空（尚未读材料/未写 draft）")
    if len(ev) < 8:
        rep["hints"].append("SMALL_LEDGER：事件仅 %d 条，趋势结论只能是提示性" % len(ev))
    if not stages:
        rep["hints"].append("STAGE_EMPTY：无阶段划分，无法回答'何时、因何变化'")
    if not gaps:
        rep["hints"].append("GAP_EMPTY：无研究空白条目")
    # 代表作阶段覆盖
    for i, s in enumerate(stages, 1):
        yr = s.get("year_range")
        if not (isinstance(yr, (list, tuple)) and len(yr) == 2):
            continue
        inr = [e for e in ev if isinstance(e.get("year"), int) and yr[0] <= e["year"] <= yr[1]]
        tg = [t for t in turns if any(str(x) in {str(x2.get("event_id")) for x2 in inr} for x in (t.get("event_ids") or []))]
        if inr and not tg:
            hints.append("REP_STAGE_UNCOVERED：阶段 %s 内无转折事件，代表作只能用 stage_first_event 兜底" % s.get("stage_id"))
    return rep
