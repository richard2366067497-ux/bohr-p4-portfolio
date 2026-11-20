#!/usr/bin/env python3
"""search-09 engine: discover -> blocks(F##/#p<n>) -> records -> papers -> type -> checkpoints
-> verbatim anchors -> judgment/risk (rule ids) -> grading. stdlib only, no CWD use.
量表/关键词族来自 ../references/appraisal_rules.md 的 ```rules 块；缺失时退到内置最小量表（RULES_ERR）。
"""
import csv, json, re, zlib
from pathlib import Path

VERSION, NAME = "2.0.0", "search-09-appraisal"
EXTS = {".pdf", ".json", ".jsonl", ".csv", ".tsv", ".md", ".markdown", ".txt", ".html", ".htm"}
CONTRACT = {"case.json", "task.json", "challenge.json", "output_contract.json"}
DIMS = [("DESIGN", "研究设计"), ("SAMPLE", "样本与抽样"), ("MEASURE", "测量与结局"),
        ("STATSREP", "统计与报告完整性"), ("BIAS", "偏倚风险")]
DIM_LABEL = dict(DIMS)
RISK = {"insufficient": 0, "low": 1, "some": 2, "major": 3}
JUDG = ("met", "partial", "not_met", "not_assessable")
FLOOR = {"rct": "low", "sysrev": "low", "cohort": "some", "case_control": "some", "cross_sectional": "some",
         "diagnostic": "some", "preclinical": "some", "materials": "some", "modelling": "some",
         "qualitative": "major", "case_report": "major", "unknown": "some"}
W = {"topic": .40, "title": .25, "design": .20, "depth": .15}
CODES = {"I_TOPIC": "主题词重合达阈值", "I_DESIGN": "设计类型符合要求", "I_FULLTEXT": "有可评读全文",
         "R_OFFTOPIC": "主题词重合低", "R_DESIGN": "设计类型不符", "R_NOFT": "仅题录元数据",
         "R_UNCLEAR": "相关但证据不足", "R_DUP": "与已收录记录同一文献"}

# 内置最小量表：仅在 references 规则块缺失时使用（5 维 × 2 检查点）
FB_KW = {"design": r"randomi[sz]|study design|prospective|retrospective|设计", "sample": r"\bn\s*=\s*\d|sample size|participants|样本量",
         "outcome": r"primary (outcome|endpoint)|outcomes?|主要结局", "measure": r"measured|assessed (using|with)|assay|测量",
         "stats": r"statistical analysis|analysed|p\s*[<=]|统计", "limit": r"limitation|局限", "fund": r"funding|conflict of interest|资助",
         "blind": r"blind|masked|盲", "elig": r"eligib|inclusion criteria|纳入标准"}
FB_CP = [("F1", "DESIGN", "设计类型", "design", "-", "Methods", "low"), ("F2", "DESIGN", "纳入条件", "elig", "-", "Methods", "low"),
         ("F3", "SAMPLE", "样本量", "sample", "-", "Methods", "low"), ("F4", "SAMPLE", "抽样方式", "sample", "-", "Methods", "low"),
         ("F5", "MEASURE", "主要结局", "outcome", "-", "Methods", "low"), ("F6", "MEASURE", "测量方法", "measure", "-", "Methods", "low"),
         ("F7", "STATSREP", "统计方法", "stats", "-", "Methods", "low"), ("F8", "STATSREP", "局限性", "limit", "-", "Discussion", "some"),
         ("F9", "BIAS", "盲法", "blind", "-", "Methods", "low"), ("F10", "BIAS", "资助与冲突", "fund", "-", "Body", "low")]


def load_rules():
    """解析 references 的规则块 -> (KW, CP, TYPE_RULES, GEN, err)。失败时不抛异常。"""
    p = Path(__file__).resolve().parent.parent / "references" / "appraisal_rules.md"
    kw, cps, types, gen, err = {}, [], [], {}, ""
    try:
        m = re.search(r"```rules\n(.*?)\n```", p.read_text(encoding="utf-8"), re.S)
        if not m:
            err = "no ```rules``` block in %s" % p.name
        for line in (m.group(1) if m else "").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or " " not in line:
                continue
            kind, rest = line.split(" ", 1)
            if kind in ("kw", "type", "gen") and "|" in rest:
                name, pat = rest.split("|", 1)
                if kind == "kw":
                    kw[name.strip()] = pat
                elif kind == "type":
                    types.append((name.strip(), pat))
                else:
                    gen[name.strip()] = pat
            elif kind == "cp":
                f = [x.strip() for x in rest.split("|")]
                if len(f) >= 8 and f[3] in kw:
                    cps.append({"checkpoint_id": f[0], "dimension": f[1], "question": f[2], "kw": f[3],
                                "neg": None if f[4] == "-" else f[4],
                                "sections": [s for s in f[5].split(",") if s], "floor": f[6],
                                "type": "" if f[7] == "-" else f[7]})
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    if err or not kw or not cps:
        cps = [{"checkpoint_id": a, "dimension": b, "question": c, "kw": d, "neg": None if e == "-" else e,
                "sections": [s for s in f.split(",") if s], "floor": g, "type": ""}
               for a, b, c, d, e, f, g in FB_CP]
        return FB_KW, cps, [], {"preprint": r"preprint|medRxiv|bioRxiv|arXiv", "fixture": r"fixture|synthetic|duplicate"}, \
               err or "rules block has no kw/cp rows"
    return kw, cps, types, gen, ""


KW, CP_ALL, TYPE_RULES, GEN, RULES_ERR = load_rules()
PREPRINT = GEN.get("preprint") or r"preprint|medRxiv|bioRxiv|arXiv"
FIXTURE = GEN.get("fixture") or r"fixture|synthetic|duplicate|占位"
STOP = set("a an the of in on for and or to with by from at as is are was were be been this that these those we our it its "
           "their they them than which where when what how not no nor but if into over under between among per via vs "
           "using used use also both all any each other such more most less least can may might will would should could "
           "does did has have had during within without across about after before while thus therefore however there study"
           .split())
_MAP = {"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u00a0": " ", "\u2009": " ", "\u202f": " ", "\u00ad": "", "\u200b": "",
        "\ufeff": "", "\u00b5": "\u03bc"}


def norm(s):
    s = s or ""
    for k, v in _MAP.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip().lower()


def toks(s):
    return [t for t in re.findall(r"[a-z0-9\u00c0-\u024f\u0370-\u03ff\u4e00-\u9fff]{2,}", norm(s)) if t not in STOP]


def verify(quote, text):
    """逐字核验：exact / normalized / mismatch。"""
    q, t = quote or "", text or ""
    if len(norm(q)) < 8:
        return "mismatch", 0.0
    if q in t:
        return "exact", 1.0
    nq, nt = norm(q), norm(t)
    return ("normalized", .98) if (nq and nq in nt) else \
        (("normalized", .96) if (nq and nq.replace("-", " ") in nt.replace("-", " ")) else ("mismatch", 0.0))


def overlap(a, b):
    ta, tb = set(toks(a)), set(toks(b))
    return len(ta & tb) / float(len(ta)) if ta else 0.0


def rx(f):
    return re.compile(KW.get(f) or f, re.I)


def _stream(c):
    m = re.search(rb"stream\r?\n(.*?)endstream", c, re.S)
    if not m:
        return b""
    raw = m.group(1)
    for f in (zlib.decompress, lambda b: zlib.decompressobj().decompress(b)):
        try:
            return f(raw)
        except Exception:
            pass
    return raw


def _text(raw):
    """PDF 内容流 -> 文本：Tj/TJ 括号字面串（支持嵌套/转义），Td/T*/ET 视为换行。"""
    out, pos = [], 0
    for m in re.finditer(rb"(?<![A-Za-z])(Tj|TJ|T\*|Td|TD)(?![A-Za-z])", raw):
        seg, pos = raw[pos:m.end()], m.end()
        if m.group(1) not in (b"Tj", b"TJ"):
            out.append("\n")
            continue
        i = 0
        while i < len(seg):
            if seg[i:i + 1] != b"(":
                i += 1
                continue
            d, j, buf = 1, i + 1, bytearray()
            while j < len(seg) and d:
                ch = seg[j:j + 1]
                if ch == b"\\":
                    buf += seg[j:j + 2]; j += 2; continue
                d += 1 if ch == b"(" else (-1 if ch == b")" else 0)
                if d:
                    buf += ch
                j += 1
            b2 = re.sub(rb"\\([0-7]{1,3})", lambda m2: bytes([int(m2.group(1), 8) & 0xFF]),
                        re.sub(rb"\\([()\\])", rb"\1", bytes(buf)))
            out.append(b2.replace(b"\n", b" ").decode("latin-1", "replace")); i = j
    return re.sub(r"[ \t]+", " ", "".join(out))


def pdf_pages(path):
    """zlib 文本层：按 /Type /Page 顺序成页；无文本层标 quality。"""
    try:
        data = Path(path).read_bytes()
    except Exception:
        return [], {"quality": "unreadable", "pages": 0}
    meta = {"has_font": b"/Font" in data, "encrypted": b"/Encrypt" in data}
    objs = {}
    for m in re.finditer(rb"(\d+)\s+\d+\s+obj\b(.*?)endobj", data, re.S):
        objs.setdefault(int(m.group(1)), m.group(2))
    pages = []
    for pno, num in enumerate(sorted(n for n, b in objs.items() if re.search(rb"/Type\s*/Page[^s]", b)), 1):
        body, raw = objs[num], b""
        m = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", body)
        for ref in (re.findall(rb"(\d+)\s+\d+\s+R", m.group(1)) if m else []):
            raw += _stream(objs.get(int(ref), b""))
        pages.append({"page": pno, "text": _text(raw or _stream(body))})
    if not pages:
        for i, m in enumerate(re.finditer(rb"stream\r?\n", data), 1):
            t = _text(_stream(data[max(0, m.start() - 400):]))
            if len(t.strip()) > 40:
                pages.append({"page": None, "text": t, "stream": i})
    chars = sum(len(p["text"]) for p in pages)
    meta.update(pages=len(pages), chars=chars)
    meta["quality"] = ("encrypted" if meta["encrypted"] else "no_text_layer" if chars < 200 or not meta["has_font"]
                       else "low" if chars / max(1, len(pages)) < 400 else "usable")
    return pages, meta


SECT = ("abstract", "summary", "introduction", "background", "method", "methods", "materials and methods", "result",
        "results", "discussion", "conclusion", "conclusions", "limitation", "limitations", "references", "supplementary",
        "study design", "participants", "patients", "subjects", "intervention", "interventions", "outcome", "outcomes",
        "statistical analysis", "data availability", "funding", "conflict of interest", "conflicts of interest",
        "ethical approval", "acknowledg", "bibliography", "appendix")
HEAD = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*\.?\s*)?(" + "|".join(SECT) + r")[\w\s]{0,12}[:.]?\s*$", re.I)


def split_paras(text):
    """段落块 + 简易章节识别；硬换行复原为空格，空行分段。"""
    text = re.sub(r"(?<=[a-z,;])\n(?=[a-z(])", " ", (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    chunks, cur = [], []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            if cur:
                chunks.append(" ".join(cur)); cur = []
        elif len(s) < 60 and HEAD.match(s):
            if cur:
                chunks.append(" ".join(cur)); cur = []
            chunks.append("||H||" + s.strip("# ").strip().rstrip(":."))
        else:
            cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    out, sec = [], "Body"
    for c in chunks:
        if c.startswith("||H||"):
            sec = c[5:].strip() or sec
            continue
        c = re.sub(r"\s+", " ", c).strip()
        if len(c) >= 2:
            out.append({"section": sec, "text": c})
    return out


def load_text(p):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return Path(p).read_text(encoding=enc)
        except Exception:
            pass
    return Path(p).read_text(encoding="utf-8", errors="replace")


TITLE_K = ("title", "display_name", "article_title", "paper_title", "name", "titles")
DOI_K = ("doi", "digitalobjectidentifier", "article_doi", "self_doi")
ABS_K = ("abstract", "summary", "abstract_text", "description")
YEAR_K = ("year", "pub_year", "publication_year", "issued", "published", "date")
AUTH_K = ("author", "authors", "creator", "creators", "authorstring")
VENUE_K = ("container_title", "journal", "journal_title", "venue", "source", "publication")
TYPE_K = ("type", "publication_type", "pubtype", "article_type", "genre")
TEXT_K = ("text", "content", "paragraph", "passage", "sentence", "body", "caption", "value")


def _first(d, keys):
    for k in (keys if isinstance(d, dict) else []):
        for kk in (k, k.upper(), k.capitalize()):
            v = d.get(kk)
            if v in (None, "", [], {}):
                continue
            if isinstance(v, list):
                v = "; ".join(str(x.get("family") or x.get("name") or x) if isinstance(x, dict) else str(x) for x in v[:12])
            elif isinstance(v, dict):
                v = str(v.get("date-parts") or v.get("value") or v.get("year") or "")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def _flat(v):
    if isinstance(v, (str, int, float)):
        return str(v)
    if isinstance(v, list):
        return " ".join(_flat(x) for x in v)
    return " ".join(_flat(x) for x in v.values() if not isinstance(x, (int, float, bool))) if isinstance(v, dict) else ""


def _record(d):
    t = _first(d, TITLE_K)
    if not t or len(t) < 8 or not any(_first(d, k) for k in (DOI_K, YEAR_K, TYPE_K, AUTH_K, ABS_K)):
        return None
    return {"title": re.sub(r"\s+", " ", t)[:400], "doi": _first(d, DOI_K),
            "pmid": _first(d, ("pmid", "pubmedid", "pmcid")), "year": re.sub(r"[^0-9]", "", _first(d, YEAR_K))[:4],
            "authors": _first(d, AUTH_K)[:300], "venue": _first(d, VENUE_K)[:200],
            "abstract": re.sub(r"\s+", " ", _flat(_first(d, ABS_K)))[:6000]}


def add_blocks(doc, units):
    seen = {norm(b["text"]) for b in doc["blocks"]}
    for u in units:
        t = re.sub(r"\s+", " ", u.get("text") or "").strip()
        if len(t) < 2 or norm(t) in seen:
            continue
        seen.add(norm(t))
        n = len(doc["blocks"]) + 1
        doc["blocks"].append({"block_id": "p%d" % n, "locator": "%s#p%d" % (doc["doc_id"], n),
                              "section": u.get("section") or "Body", "page": u.get("page"), "text": t})


def _walk(doc, node, jp, depth=0):
    if depth > 12:
        return
    if isinstance(node, list):
        for i, v in enumerate(node):
            _walk(doc, v, "%s[%d]" % (jp, i), depth + 1)
        return
    if not isinstance(node, dict):
        return
    rec = _record(node)
    if rec:
        rec["source_record_id"], n0 = jp, len(doc["blocks"])
        doc["records"].append(rec)
        add_blocks(doc, [{"section": "Title", "text": rec["title"]}])
        if rec["abstract"]:
            add_blocks(doc, [{"section": "Abstract", "text": rec["abstract"]}])
        rec["locators"] = [b["locator"] for b in doc["blocks"][n0:]]
    for k, v in node.items():
        if isinstance(v, str) and len(v.strip()) > 40 and k.lower() in TEXT_K + ABS_K:
            add_blocks(doc, [{"section": "Body", "text": v}])
        else:
            _walk(doc, v, jp + "." + str(k), depth + 1)


def load_doc(doc):
    kind, path = doc["kind"], Path(doc["path"])
    if kind == "pdf":
        pages, meta = pdf_pages(path)
        doc["meta"].update(meta)
        for pg in pages:
            for u in split_paras(pg.get("text")):
                u["page"] = pg.get("page"); add_blocks(doc, [u])
    elif kind in ("json", "jsonl"):
        raw = load_text(path)
        data = []
        if kind == "jsonl":
            for line in raw.splitlines():
                try:
                    data.append(json.loads(line))
                except Exception:
                    pass
        else:
            data = json.loads(raw)
        _walk(doc, data, "$")
    elif kind in ("csv", "tsv"):
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            for r in list(csv.reader(fh, delimiter="\t" if kind == "tsv" else ","))[:400]:
                add_blocks(doc, [{"section": "Table", "text": " | ".join(x.strip() for x in r)}])
    else:
        text = load_text(path)
        if kind in ("html", "htm"):
            text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
            text = re.sub(r"(?i)<(br\s*/?|/p|/div|/h[1-6])>", "\n", text)
            text = re.sub(r"(?i)<h[1-6][^>]*>", "\n## ", text)
            text = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").replace("&amp;", "&")
        add_blocks(doc, split_paras(text))


def discover(root, max_files=200):
    """相对路径排序 -> doc_id F01..；role/fixture 只影响用途。"""
    docs, problems = [], []
    root = Path(root)
    files = []
    try:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in EXTS and not any(x.startswith(".") for x in p.relative_to(root).parts):
                files.append(p)
    except Exception as e:
        problems.append({"kind": "scan_failed", "detail": "%s: %s" % (type(e).__name__, e)})
    for i, p in enumerate(files[:max_files], 1):
        rel, low = str(p.relative_to(root)), p.name.lower()
        doc = {"doc_id": "F%02d" % i, "path": str(p), "rel": rel, "kind": p.suffix.lower().lstrip("."),
               "role": "material", "blocks": [], "records": [], "meta": {}}
        if low in CONTRACT:
            doc["role"] = "contract"
        elif low == "task.md" and "/" not in rel.replace("\\", "/"):
            doc["role"] = "task"
        elif re.search(FIXTURE, rel, re.I):
            doc["fixture"] = True
        try:
            load_doc(doc)
        except Exception as e:
            problems.append({"kind": "parse_failed", "doc_id": doc["doc_id"], "path": rel,
                             "detail": "%s: %s" % (type(e).__name__, e)})
            doc["meta"]["quality"] = "unreadable"
        docs.append(doc)
    return docs, problems


def type_of(text):
    low = norm(text)[:8000]
    for name, pat in TYPE_RULES:
        m = re.search(pat, low)
        if m:
            return name, m.group(0)
    return "unknown", ""


def sent_span(text, start, end, cap=400):
    """命中位置 -> 句级子串（原文切片，containment 成立）。"""
    d = ".!?;。；！？\n"
    s = start
    while s > 0 and text[s - 1] not in d:
        s -= 1
    e = end
    while e < len(text) and text[e] not in d:
        e += 1
    e += 1 if e < len(text) else 0
    q = text[s:e].strip()
    if len(q) < 24:
        e2 = e
        while e2 < len(text) and text[e2] not in d:
            e2 += 1
        q = text[s:min(len(text), e2 + 1)].strip()
    if len(q) > cap:
        q = q[:cap]
        cut = q.rfind(" ")
        q = q[:cut] if cut > 200 else q
    return q.strip()


def build_papers(docs, limit=12):
    """题录 -> papers；记录挂接同标题全文；无题录时用全文型文档成篇。"""
    papers, used = [], set()
    for d in docs:
        if d.get("role") in ("contract", "task") or d.get("fixture"):
            continue
        for r in d["records"]:
            if any(norm(r["title"])[:80] == norm(p["title"])[:80] for p in papers):
                continue
            papers.append({"paper_id": "P%02d" % (len(papers) + 1), "title": r["title"], "year": r.get("year", ""),
                           "doi": r.get("doi", ""), "pmid": r.get("pmid", ""), "authors": r.get("authors", ""),
                           "venue": r.get("venue", ""), "source_id": d["doc_id"], "source_path": d["rel"],
                           "source_record_id": r.get("source_record_id", ""),
                           "blocks": [b for b in d["blocks"] if b["locator"] in set(r.get("locators") or [])] or
                                     list(d["blocks"]),
                           "doc_ids": [d["doc_id"]], "scope": "abstract" if r.get("abstract") else "metadata"})
            used.add(d["doc_id"])
            if len(papers) >= limit:
                break
    for p in papers:
        for d in docs:
            if d["doc_id"] in p["doc_ids"] or d.get("role") in ("contract", "task") or d.get("fixture"):
                continue
            if len(d["blocks"]) >= 2 and overlap(p["title"], " ".join(b["text"] for b in d["blocks"][:4])) >= .6:
                p["blocks"] += d["blocks"]; p["doc_ids"].append(d["doc_id"])
                p["scope"] = "full_text" if len(d["blocks"]) >= 3 else "abstract"
                used.add(d["doc_id"])
    for d in docs:
        if d["doc_id"] in used or d.get("role") in ("contract", "task") or d.get("fixture"):
            continue
        secs, chars = {b["section"].lower() for b in d["blocks"]}, sum(len(b["text"]) for b in d["blocks"])
        if len(d["blocks"]) >= 4 and chars >= 800 and ({"abstract", "methods", "results"} & secs or chars > 2000):
            if len(papers) >= limit:
                break
            papers.append({"paper_id": "P%02d" % (len(papers) + 1), "title": d["blocks"][0]["text"][:200],
                           "year": "", "doi": "", "pmid": "", "authors": "", "venue": "",
                           "source_id": d["doc_id"], "source_path": d["rel"], "source_record_id": "$",
                           "blocks": list(d["blocks"]), "doc_ids": [d["doc_id"]], "scope": "full_text"})
    for p in papers:
        p["block_quality"] = next((d["meta"].get("quality") for d in docs
                                   if d["doc_id"] == p["source_id"] and d["meta"].get("quality")), None)
    return papers


def route_type(p):
    """类型 = 标题+前 6 块首个关键词命中，命中句即类型证据。"""
    text = " ".join([p["title"]] + [b["text"] for b in p["blocks"][:6]])
    ptype, kw = type_of(text)
    p["paper_type"], p["preprint"], p["type_anchor"] = ptype, bool(re.search(PREPRINT, text, re.I)), None
    for b in (p["blocks"] if kw else []):
        m = re.search(re.escape(kw), b["text"], re.I)
        if m:
            p["type_anchor"] = {"doc_id": b["locator"].split("#")[0], "locator": b["locator"], "section": b["section"],
                                "quote": sent_span(b["text"], m.start(), m.end()), "matched": kw}
            break
    return p


def plan(ptype):
    t = (ptype or "unknown").lower()
    return [c for c in CP_ALL if not c["type"] or c["type"] == t]


def anchors_for(cp, paper, cap=2):
    """章节优先 -> 命中次数 -> locator 字典序（同输入必得同锚点）。"""
    fam, scored = rx(cp["kw"]), []
    for b in paper["blocks"]:
        hits = list(fam.finditer(b["text"]))
        if not hits:
            continue
        low = b["section"].lower()
        pri = next((i for i, s in enumerate(cp["sections"]) if s.lower() in low or low in s.lower()), 99)
        scored.append((pri, -len(hits), b["locator"], b, hits))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    out = []
    for _p, _n, _l, b, hits in scored[:cap]:
        q = sent_span(b["text"], hits[0].start(), hits[0].end())
        state, score = verify(q, b["text"])
        if state != "mismatch":
            out.append({"doc_id": b["locator"].split("#")[0], "locator": b["locator"], "section": b["section"],
                        "page": b.get("page"), "quote": q, "match": state, "score": score})
    return out


def judge(cp, anc, paper):
    """R_J1 无锚点弃权 / R_J2 反向表述 not_met / R_J3 证据足 met / R_J4 弱锚点 partial。"""
    if not anc:
        why = "not_parsable" if paper.get("block_quality") in ("no_text_layer", "encrypted", "unreadable") else "unreported"
        return "not_assessable", "insufficient", "R_J1_ABSTAIN", \
               "关键词族 `%s` 在 %d 块中无命中；弃权原因=%s" % (cp["kw"], len(paper["blocks"]), why)
    quotes = [a["quote"] for a in anc]
    m = rx(cp["neg"]).search(" ".join(quotes)) if cp["neg"] else None
    if m:
        return "not_met", "major", "R_J2_NEG", "锚点含反向表述「%s」，判 not_met（%s）" % (m.group(0), anc[0]["locator"])
    num = any(re.search(r"\d", q) for q in quotes)
    if min(2, len(anc)) + (1 if num else 0) >= 2:
        return "met", cp["floor"], "R_J3_MET", "%d 条锚点%s，判 met；风险下限=%s（%s）" % (
            len(anc), "（含数值）" if num else "", cp["floor"], anc[0]["locator"])
    return "partial", "some", "R_J4_WEAK", "仅 %d 条弱锚点且无量化信息，判 partial；需复核 %s" % (
        len(anc), anc[0]["locator"])


def appraise(paper):
    """逐检查点取证 + 判定 -> (appraisal 行, 锚点)。"""
    rows, anchors = [], []
    for cp in plan(paper["paper_type"]):
        anc = anchors_for(cp, paper)
        j, risk, rule, why = judge(cp, anc, paper)
        ids = []
        for a in anc:
            aid = "A%03d" % (len(anchors) + 1)
            anchors.append(dict(a, anchor_id=aid, paper_id=paper["paper_id"], checkpoint_id=cp["checkpoint_id"],
                                dimension=cp["dimension"], used_for=cp["checkpoint_id"]))
            ids.append(aid)
        row = {"paper_id": paper["paper_id"], "dimension": cp["dimension"],
               "dimension_label": DIM_LABEL.get(cp["dimension"], cp["dimension"]), "checkpoint_id": cp["checkpoint_id"],
               "question": cp["question"], "judgment": j, "risk": risk, "rule_id": rule, "rationale": why,
               "anchor_ids": ids, "evidence_scope": paper.get("scope"),
               "confidence": "high" if (j == "met" and len(anc) >= 2) else ("medium" if j in ("met", "partial") else "low"),
               "evidence": {k: anc[0][k] for k in ("doc_id", "locator", "section", "page", "quote", "match")} if anc else {}}
        if j == "not_assessable":
            row["abstain_reason"] = "not_parsable" if paper.get("scope") == "metadata" else "unreported"
            row["searched_scope"] = {"blocks": len(paper["blocks"]),
                                     "sections": sorted({b["section"] for b in paper["blocks"]}),
                                     "keyword_family": cp["kw"], "sections_preferred": cp["sections"]}
        rows.append(row)
    return rows, anchors


def grade(rows, ptype):
    """维度最差项 + 设计强度下限 -> 总体等级；build 与 selfcheck 共用同一函数。"""
    dims = {k: {"count": 0, "met": 0, "partial": 0, "not_met": 0, "not_assessable": 0, "worst": None,
                "grade": "insufficient"} for k, _ in DIMS}
    trace = []
    for r in rows:
        d = dims.get(r["dimension"])
        if not d:
            continue
        d["count"] += 1; d[r["judgment"]] += 1
        if r["judgment"] != "not_assessable" and (d["worst"] is None or RISK[r["risk"]] > RISK[d["worst"]]):
            d["worst"] = r["risk"]
        trace.append("%s(%s) %s/%s %s" % (r["checkpoint_id"], r["dimension"], r["judgment"], r["risk"], r["rule_id"]))
    for v in dims.values():
        v["grade"] = v["worst"] if (v["count"] and v["worst"]) else "insufficient"
    floor, des = FLOOR.get((ptype or "unknown").lower(), "some"), dims["DESIGN"]
    if des["count"] and des["worst"] and RISK[floor] > RISK[des["grade"]]:
        des["floor_applied"], des["grade"] = floor, floor
        trace.append("设计强度下限：%s -> DESIGN 不可低于 %s" % (ptype, floor))
    total = sum(v["count"] for v in dims.values())
    na = sum(v["not_assessable"] for v in dims.values())
    some_n = sum(1 for v in dims.values() if v["grade"] == "some")
    major = [k for k in ("DESIGN", "SAMPLE", "BIAS") if dims[k]["grade"] == "major"]
    if total == 0:
        overall, why = "insufficient_evidence", "无任何检查点判断"
    elif na * 2 >= total:
        overall, why = "insufficient_evidence", "弃权 %d/%d 检查点，证据不足" % (na, total)
    elif major:
        overall, why = "high_risk", "%s 维度为 major" % "/".join(major)
    elif some_n >= 2:
        overall, why = "some_concerns", "%d 个维度 some，未达 major 但非低风险" % some_n
    else:
        overall, why = "low_risk", "各维度 low 或仅单一 some，弃权未过半"
    return {"dimensions": dims, "overall": overall, "reason": why, "design_floor": floor,
            "coverage": {"planned": len(plan(ptype)), "judged": total, "not_assessable": na}, "trace": trace}
