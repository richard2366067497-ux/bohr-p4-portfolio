#!/usr/bin/env python3
"""core.py - I/O layer: input discovery, record normalisation, locators, criteria facets.

Stdlib only, no network, no randomness. Imported by main.py / analyze.py.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path

VERSION = "1.0.0"
PKG = Path(__file__).resolve().parent.parent
LABELS = ("keep", "maybe", "exclude")
RELEVANCE = ("direct", "indirect", "none")
RULES = {
    "R1": "topic_match", "R2": "object_match", "R3": "method_match", "R4": "time_window",
    "R5": "record_type", "R6": "evidence_available", "R7": "metadata_complete", "R8": "hard_exclusion",
    "R9": "duplicate_version", "R10": "same_study_group", "R11": "abstract_insufficient",
    "R12": "label_conflict",
}
TYPE_WEIGHT = {"primary": 1.0, "review": 0.8, "preprint": 0.7, "other": 0.3}
REL_ORDER = {"direct": 0, "indirect": 1, "none": 2}
W = {"topic": 0.40, "object": 0.20, "method": 0.15, "evidence": 0.10, "recency": 0.10, "completeness": 0.05}
KEEP_MIN, MAYBE_MIN = 0.55, 0.35
MAX_RECORDS = int(os.environ.get("SCREEN_MAX_RECORDS", "400") or 400)
ABS_CHARS = int(os.environ.get("SCREEN_ABSTRACT_CHARS", "1600") or 1600)

TITLE_K = ("title", "paper_title", "doc_title", "article_title", "study_title", "题名", "标题")
ABS_K = ("abstract", "abstract_text", "summary", "snippet", "description", "abstract_text_en")
ID_K = ("record_id", "paper_id", "doc_id", "uid", "key", "id", "pmid", "openalex_id", "corpus_id")
DOI_K = ("doi", "DOI", "DigitalObjectIdentifier")
YEAR_K = ("year", "pub_year", "publication_year", "publish_year", "issued", "date", "pub_date", "published")
AUTH_K = ("authors", "author", "author_list", "creators", "creator", "byline")
VENUE_K = ("venue", "journal", "container_title", "container", "source", "publisher", "publication", "booktitle")
TYPE_K = ("type", "record_type", "pub_type", "publication_type", "study_type", "genre", "article_type")
KW_K = ("keywords", "keyword", "subject", "subjects", "mesh", "concepts", "tags")
URL_K = ("url", "link", "href", "fulltext_url", "landing_page")
CITE_K = ("citation_count", "cited_by_count", "n_cites", "cites", "is_referenced_by_count")
SYNTH_K = ("synthetic", "is_synthetic", "fixture", "is_fixture")

LIST_KEYS = ("candidates", "records", "items", "results", "works", "papers", "articles", "documents",
             "corpus", "pool", "hits", "entries", "rows", "data", "search_results", "screening_records",
             "candidate_pool", "candidate_set", "docs", "literature")
ANNOT_PAT = ("conflicting_opinion", "conflict", "opinion")
QUERY_PAT = ("quer", "search_log", "strategy")
STATE_PAT = ("import_state", "ingest", "state")
DUPFILE_PAT = ("duplicate_export", "duplicates", "dedup_export", "duplicate_records")

CJK = re.compile(r"[\u4e00-\u9fff]+")
LAT = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
WS = re.compile(r"[ \t\u3000\xa0]+")
TAG = re.compile(r"<[^>]{1,80}>")
SENT = re.compile(r"(?<=[。！？；!?;])|(?<=[.;])\s+(?=[A-Z(])|\n+")
PREPRINT = re.compile(r"arxiv|biorxiv|medrxiv|ssrn|research\s*square|preprint|chemrxiv|techrxiv|osf", re.I)
BAD_TYPE = re.compile(r"retract|withdraw|erratum|correction|retraction|editorial|comment|letter|"
                      r"撤稿|勘误|更正|社论|编者按|征稿|广告|call for paper", re.I)
RESULT_CUE = re.compile(r"we (?:found|show|report|observe|demonstrate)|results? (?:show|indicate|suggest)|"
                        r"significan|p\s*[<=]\s*0?\.\d|increase|decrease|reduc|improv|"
                        r"结果|表明|显示|显著|提高|降低|增加|减少|提升|下降|效应", re.I)
BAD_BIGRAM = {"研究", "文献", "方法", "分析", "结果", "任务", "题目", "相关", "需要", "要求", "进行",
              "提供", "包括", "以下", "如下", "对应", "记录", "条目", "候选", "筛选", "排序", "输出", "输入",
              "内容", "格式", "字段", "说明", "条件", "标准", "问题", "目标", "范围", "示例", "数据"}
EN_STOP = {"the", "and", "task", "screen", "screening", "provided", "candidate", "candidates", "list",
           "research", "question", "below", "return", "ranked", "short", "record", "records", "note",
           "answer", "expected", "finite", "snapshot", "claim", "global", "recall", "given", "input",
           "output", "must", "should", "value", "values", "field", "fields", "number", "string", "for", "with", "that", "this", "these", "those", "was", "were", "are", "from",
           "have", "has", "had", "not", "but", "than", "into", "there", "which", "while", "also", "such",
           "can", "may", "been", "being", "its", "they", "them", "however", "used", "use", "using", "study",
           "studies", "paper", "papers", "article", "articles", "review", "based", "among", "between",
           "their", "our", "his", "her", "more", "most", "some", "all", "any", "how", "what", "when", "who",
           "will", "would", "should", "could", "about", "over", "under", "both", "each", "other", "same"}
CJK_STOP = set("的了和与及或在是对为把被而并且也等就都还又很更最则其之该此是我方可将能会从对向于以但与或如若虽因由于这那些个中上下有条篇文献研究分析于方法结果进行以及关于通过")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def s(v):
    """Coerce to str without turning None into 'None'."""
    return "" if v is None else (v if isinstance(v, str) else str(v))


def norm_ws(text):
    return WS.sub(" ", s(text).replace("\r\n", "\n").replace("\r", "\n")).strip()


def flat(text):
    return re.sub(r"\s+", " ", s(text)).strip()


def clean(text):
    return flat(TAG.sub(" ", s(text)))


def stem(w):
    w = w.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("es") and not w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def terms(text, cap=24):
    """Content terms: latin stems (>=3 chars) + CJK bigrams, order preserved."""
    out, seen = [], set()
    t = s(text)
    for w in LAT.findall(t):
        k = stem(w)
        if k in EN_STOP or k in seen or len(k) < 3:
            continue
        seen.add(k)
        out.append(k)
    for run in CJK.findall(t):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg[0] in CJK_STOP or bg[1] in CJK_STOP or bg in seen or bg in BAD_BIGRAM:
                continue
            seen.add(bg)
            out.append(bg)
    return out[:cap]


def term_set(text):
    return set(terms(text, cap=200))


def as_text(v):
    """Flatten abstract-like values (str / list / structured dict) to text."""
    if v is None:
        return ""
    if isinstance(v, str):
        return clean(v)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return " ".join(x for x in (as_text(i) for i in v) if x)
    if isinstance(v, dict):
        pref = ("text", "value", "content", "abstract", "summary", "sentence", "paragraph")
        buf = []
        for k in pref:
            if k in v:
                buf.append(as_text(v[k]))
        if not buf:
            buf = [as_text(x) for _, x in sorted(v.items(), key=lambda kv: str(kv[0]))]
        return " ".join(x for x in buf if x)
    return clean(v)


def year_of(v):
    if isinstance(v, (int, float)) and 1500 < int(v) < 2200:
        return int(v)
    m = re.search(r"(1[6-9]\d{2}|20\d{2}|21\d{2})", s(v))
    return int(m.group(1)) if m else None


def doi_of(v):
    m = re.search(r"10\.\d{4,9}/[^\s\"'<>,;]+", s(v), re.I)
    if not m:
        return None
    return m.group(0).rstrip(").,;]").lower()


def title_key(t):
    t = s(t).lower()
    t = re.sub(r"[\W_]+", "", t, flags=re.U)
    return t


def sim(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    A, B = term_set(a), term_set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B))


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gb18030", "utf-16", "latin-1"):
        try:
            return Path(path).read_text(encoding=enc)
        except Exception:
            continue
    return ""


def load_json(path):
    raw = read_text(path)
    if not raw.strip():
        return None, "empty file"
    try:
        return json.loads(raw), None
    except Exception as exc:
        m = re.search(r"[\[{]", raw)
        if m:
            frag = raw[m.start():]
            for tail in ("", "]", "}", "]}", "}]"):
                try:
                    return json.loads(frag + tail), "repaired trailing text"
                except Exception:
                    continue
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:120])


def jwrite(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(p)


def jlwrite(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(p)


def pick_input(explicit=None):
    cands = []
    if explicit:
        cands.append(explicit)
    cands += ["/input", "/app/input", str(Path.cwd() / "input"), str(PKG / "input"), str(PKG.parent / "input")]
    for c in cands:
        p = Path(c)
        if p.is_dir():
            return p
    return Path(explicit or "/input")


def pick_dir(explicit, defaults):
    if explicit:
        p = Path(explicit)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p
    for c in defaults:
        p = Path(c)
        if p.is_dir():
            return p
    for c in defaults:
        p = Path(c)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    return Path(defaults[-1])


def pick_output(explicit=None):
    return pick_dir(explicit, ["/app/output", str(Path.cwd() / "output"), str(PKG.parent / "output")])


def pick_work(explicit=None):
    return pick_dir(explicit, ["/app/work", str(Path.cwd() / "work"), str(PKG.parent / "work")])



def rel(path, base):
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except Exception:
        return str(path)


CONTRACT_K = ("output_contract", "expected_output", "output_fields", "contract", "required_fields",
              "output_schema", "deliverables")
TASK_K = ("task_instruction", "instruction", "research_question", "question", "task", "query", "topic",
          "objective")
CRIT_K = ("screening_criteria", "inclusion_criteria", "exclusion_criteria", "inclusion", "exclusion",
          "criteria", "eligibility", "pico", "selection_criteria", "scope")
K_K = ("k", "top_k", "target_k", "n_results", "top_n", "keep_k")


def load_case(inp):
    cases = [inp / "case.json"] + sorted(inp.glob("case*.json"))
    for p in cases:
        if p.is_file():
            obj, err = load_json(p)
            if isinstance(obj, dict):
                return obj, str(p), err
            if isinstance(obj, list):
                return {"candidates": obj}, str(p), err
            rec = {}
            m = re.search(r'"case_?id"\s*:\s*"([^"]{1,80})"', read_text(p), re.I)
            if m:
                rec["case_id"] = m.group(1)
            return rec, str(p), err or "case.json is not a JSON object"
    return {}, None, None


def first_key(d, keys):
    if not isinstance(d, dict):
        return None
    low = {str(k).lower(): k for k in d}
    for k in keys:
        if k in low:
            return d[low[k]]
    return None


def contract_specs(case):
    raw = first_key(case, CONTRACT_K)
    specs = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            kind = "unknown"
            txt = (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)).lower()
            for name, pat in (("list", ("list", "array", "[]")), ("dict", ("dict", "object", "map", "{}")),
                              ("string", ("str", "text", "markdown")), ("number", ("int", "float", "number")),
                              ("bool", ("bool",))):
                if name == "list" and isinstance(v, list):
                    kind = "list"
                if any(p in txt for p in pat):
                    kind = name
                    break
            if isinstance(v, (list, dict, bool, int, float)) and kind == "unknown":
                kind = "list" if isinstance(v, list) else ("dict" if isinstance(v, dict) else "unknown")
            specs.append((str(k), kind, v))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                specs.append((item, "unknown", None))
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if name:
                    specs.append((str(name), str(item.get("type") or "unknown").lower(), item))
    elif isinstance(raw, str):
        for part in re.split(r"[,;\s]+", raw):
            part = part.strip(" .`\"'")
            if part:
                specs.append((part, "unknown", None))
    if not specs:
        for k, kd in (("results", "list"), ("screening", "list"), ("ranking", "list"),
                      ("coverage", "dict"), ("conflicts", "dict"), ("report", "string"),
                      ("status", "string")):
            specs.append((k, kd, None))
    return specs


def split_clauses(text):
    out = []
    for line in re.split(r"[\n]+", s(text)):
        line = re.sub(r"^[\s\-*•·>]+", "", line).strip()
        if not line:
            continue
        for part in re.split(r"[;；]+|(?<=[。])", line):
            part = part.strip(" ，,、.")
            if len(part) >= 2:
                out.append(part)
    return out


def load_criteria(case, inp, task_md):
    blocks = []
    tid = first_key(case, TASK_K)
    if isinstance(tid, dict):
        blocks.append((as_text(tid), "case.json#/task_instruction"))
    elif tid:
        blocks.append((clean(tid), "case.json#/task_instruction"))
    crit_raw = first_key(case, CRIT_K)
    if isinstance(crit_raw, dict):
        for k, v in crit_raw.items():
            blocks.append((as_text(v), "case.json#/%s" % k))
    elif crit_raw:
        blocks.append((as_text(crit_raw), "case.json#/criteria"))
    for name in ("criteria.md", "screening_criteria.md", "criteria.json", "protocol.md", "query.json"):
        p = inp / name
        if p.is_file():
            txt = read_text(p)
            blocks.append((clean(txt)[:6000], rel(p, inp)))
    if task_md:
        blocks.append((task_md, "task.md"))
    text = "\n".join(b[0] for b in blocks if b[0])
    clarify = " ".join(a for a in (as_text(tid), as_text(crit_raw)) if a)[:2500]
    question = ""
    m = re.search(r"(?:research question|研究问题|科研问题|核心问题)\s*[:：]?\s*([^。\n]{6,200})", text, re.I)
    if m:
        question = m.group(1).strip(" 。.;；")
    if not question:
        question = clarify[:300] or text[:300]

    # --- k
    k = None
    kv = first_key(case, K_K)
    if isinstance(kv, (int, float)) and 0 < int(kv) <= 200:
        k = int(kv)
    if k is None:
        for pat in (r"top[\s_\-]?k\s*[:=]?\s*(\d{1,3})", r"\bk\s*=\s*(\d{1,3})",
                    r"(?:前|top)\s*(\d{1,3})\s*(?:篇|条|papers|results|records)",
                    r"(?:至少|不少于|保留)\s*(\d{1,3})\s*(?:篇|条)"):
            m = re.search(pat, text, re.I)
            if m:
                k = int(m.group(1))
                break
    if k is None:
        k = 10

    # --- time window
    win = None
    for pat in (r"((?:19|20)\d{2})\s*[-–—~至到到]\s*((?:19|20)\d{2})",
                r"(?:since|after|from|自|自\s*)\s*((?:19|20)\d{2})"):
        m = re.search(pat, text, re.I)
        if m:
            y0 = int(m.group(1))
            y1 = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else 2100
            win = [y0, y1]
            break
    if not win:
        m = re.search(r"(?:近|最近|past|last|recent)\s*([0-9一二三四五六七八九十]{1,2})\s*(?:年|years?)", text, re.I)
        if m:
            raw = m.group(1)
            n = CN_NUM.get(raw) or (int(raw) if raw.isdigit() else None)
            if n:
                now = 2026
                win = [now - n, now]

    # --- facet clauses: case-specific text only, exclusion clauses never feed object/method/type
    clauses = []                                    # (text, key_hint)
    if isinstance(crit_raw, dict):
        for ck, cv in crit_raw.items():
            for cl in split_clauses(as_text(cv)):
                clauses.append((cl, str(ck)))
    elif crit_raw:
        for cl in split_clauses(as_text(crit_raw)):
            clauses.append((cl, "criteria"))
    if isinstance(tid, str):
        for cl in split_clauses(clean(tid)):
            clauses.append((cl, "task_instruction"))
    if not clauses:
        for cl in split_clauses(text):
            clauses.append((cl, "text"))
    excl, incl, obj, meth = [], [], [], []
    t_in, t_out = [], []
    TYPE_PAT = (("review", r"综述|review|survey|meta[- ]?analys|元分析|系统评价"),
                ("preprint", r"预印本|preprint"),
                ("primary", r"原始研究|期刊论文|primary stud|original research|research article|临床研究|实验研究"),
                ("rct", r"随机对照|randomi[sz]ed|\brct\b"),
                ("cohort", r"队列|cohort|case[- ]control|病例对照"))
    for cl, hint in clauses:
        low = (hint + " " + cl).lower()
        is_excl = bool(re.search(r"排除|不纳入|剔除|不予纳入|exclud|not (?:be )?included|filter out|exclusion", low))
        tag_hit = [tg for tg, pat in TYPE_PAT if re.search(pat, low, re.I)]
        if is_excl:
            excl.append(cl)
            t_out += [tg for tg in tag_hit if tg not in t_out]
            continue
        if re.search(r"纳入|入选|应满足|须|必须|requir|must|includ|inclusion|eligible", low):
            incl.append(cl)
        t_in += [tg for tg in tag_hit if tg not in t_in]
        is_question = bool(re.search(r"研究问题|research question|核心问题", low))
        if is_question:
            continue
        if re.search(r"人群|患者|样本|研究对象|物种|材料体系|体系|population|participant|cohort|patient|subject|sample|specimen", low):
            obj.append(cl)
        if re.search(r"方法|技术|模型|表征|检测|干预|试验设计|method|technique|assay|approach|intervention|design", low):
            meth.append(cl)
    facets = {
        "topic": terms(question, cap=14) or terms(clarify, cap=10),
        "object": terms(" ".join(obj), cap=8),
        "object_source": (obj[:2] or None),
        "method": terms(" ".join(meth), cap=8),
        "type_include": t_in,
        "type_exclude": [x for x in t_out if x not in t_in],
        "time_window": win,
        "exclusions": [x for cl in excl for x in terms(cl, cap=6)],
    }
    return {
        "text": text[:12000],
        "blocks": [{"locator": loc, "chars": len(txt)} for txt, loc in blocks],
        "question": flat(question)[:400],
        "k": k,
        "facets": facets,
        "clauses": {"inclusion": incl[:20], "exclusion": excl[:20]},
        "exclusion_clauses": excl[:20],
    }


def is_record(d):
    if not isinstance(d, dict):
        return False
    low = {str(k).lower() for k in d}
    has_title = any(k in low for k in TITLE_K)
    has_body = any(k in low for k in (ABS_K + DOI_K + YEAR_K + AUTH_K + VENUE_K))
    return (has_title and has_body) or (has_title and any(k in low for k in ID_K))


def walk_lists(doc, ptr="", depth=0):
    if depth > 4:
        return
    if isinstance(doc, list):
        recs = [x for x in doc if isinstance(x, dict) and is_record(x)]
        if recs:
            yield ptr or "/", doc
            return
        for i, x in enumerate(doc[:300]):
            if isinstance(x, dict):
                for y in walk_lists(x, "%s/%d" % (ptr, i), depth + 1):
                    yield y
    elif isinstance(doc, dict):
        for k, v in list(doc.items())[:200]:
            for y in walk_lists(v, "%s/%s" % (ptr, str(k)), depth + 1):
                yield y


def mk_record(d, file, ptr, idx, fixture=False):
    def g(keys):
        for k in keys:
            v = None
            low = {str(kk).lower(): kk for kk in d}
            if k in low:
                v = d[low[k]]
            if v not in (None, "", [], {}):
                return v
        return None

    title = clean(g(TITLE_K))[:400]
    abstract = as_text(g(ABS_K))[:ABS_CHARS * 2]
    raw_type = clean(g(TYPE_K))[:60]
    venue = clean(g(VENUE_K))[:200]
    tlow = (raw_type + " " + venue).lower()
    if PREPRINT.search(tlow) and not re.search(r"journal|proceedings|published", tlow):
        rtype = "preprint"
    elif re.search(r"review|survey|meta-analysis|系统综述|综述|元分析", tlow):
        rtype = "review"
    elif raw_type:
        rtype = "primary" if re.search(r"article|journal|research|primary|原始|论文", tlow) else "other"
    else:
        rtype = "primary" if abstract else "other"
    au = g(AUTH_K)
    if isinstance(au, list):
        au = [clean(a.get("name") or a.get("family") or a.get("literal") or "") if isinstance(a, dict)
              else clean(a) for a in au[:12]]
        authors = [n for n in au if n][:12]
    else:
        authors = [x.strip() for x in re.split(r"[;；,，]", clean(au)) if x.strip()][:12]
    rid = clean(g(ID_K))[:80] or (doi_of(g(DOI_K)) or "r%03d" % (idx + 1))
    synth = any(str(g([k]) or "").lower() in ("1", "true", "yes") for k in SYNTH_K) or fixture
    return {
        "record_id": rid, "title": title, "abstract": abstract,
        "authors": authors, "year": year_of(g(YEAR_K)), "doi": doi_of(g(DOI_K)),
        "venue": venue, "record_type": rtype, "type_raw": raw_type,
        "keywords": as_text(g(KW_K))[:400], "url": clean(g(URL_K))[:300] or None,
        "cites": g(CITE_K) if isinstance(g(CITE_K), (int, float)) else None,
        "fixture": bool(synth),
        "locator": {"file": file, "pointer": ptr, "fields": {
            "title": ptr + "/title", "abstract": ptr + "/abstract"}},
        "order": idx,
    }


def csv_records(path, base):
    err = None
    try:
        rows = list(csv.DictReader(io.StringIO(read_text(path))))
    except Exception as exc:
        rows, err = [], "%s: %s" % (type(exc).__name__, str(exc)[:80])
    out = []
    for i, row in enumerate(rows):
        low = {str(k).lower(): v for k, v in row.items() if k}
        if is_record(low):
            rec = mk_record(low, rel(path, base), "row %d" % (i + 2), len(out))
            rec["locator"]["fields"] = {"title": "row %d/title" % (i + 2),
                                        "abstract": "row %d/abstract" % (i + 2)}
            out.append(rec)
    return out, err


def text_records(path, base):
    """Plain-text / Markdown fallback: a title line followed by its abstract block."""
    raw = read_text(path)
    out = []
    for m in re.finditer(r"(?m)^[ \t]*(\S[^\n]{0,240})\n((?:(?!\s*\n).+\n?)*)", raw):
        head, body = m.group(1).strip(), flat(m.group(2))[:ABS_CHARS * 2]
        if head.startswith("#") or (not body and not re.search(r"\d{4}|doi", head, re.I)):
            continue
        out.append(mk_record({"title": head, "abstract": body, "year": year_of(head + " " + body),
                              "doi": doi_of(head + " " + body)}, rel(path, base),
                             "line %d" % (raw[:m.start()].count("\n") + 1), len(out)))
    return out


def load_candidates(inp, skip_files=()):
    cands, sources, degradations = [], [], []
    skip = {str(Path(x).resolve()) for x in skip_files if x}
    files = sorted(p for p in inp.rglob("*") if p.is_file() and p.suffix.lower() in
                   (".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".md", ".txt", ".yaml", ".yml"))
    json_hits = 0
    for p in files:
        try:
            if str(p.resolve()) in skip:
                continue
            name = p.name.lower()
            if name in ("task.md", "readme.md", "criteria.md", "protocol.md", "screening_criteria.md"):
                continue
            is_dup_file = any(k in name for k in DUPFILE_PAT)
            is_annot = any(k in name for k in ANNOT_PAT) and not is_dup_file
            if is_annot or any(k in name for k in QUERY_PAT + STATE_PAT):
                sources.append({"path": rel(p, inp), "kind": "annotation", "records": 0})
                continue
            ext = p.suffix.lower()
            got = []
            if ext in (".json", ".jsonl", ".ndjson"):
                docs = []
                if ext in (".jsonl", ".ndjson"):
                    for line in read_text(p).splitlines():
                        try:
                            docs.append(json.loads(line))
                        except Exception:
                            continue
                else:
                    obj, err = load_json(p)
                    if err:
                        degradations.append({"stage": "discover", "file": rel(p, inp),
                                             "issue": "json_parse", "detail": err})
                    docs = [obj] if obj is not None else []
                for doc in docs:
                    for ptr, lst in walk_lists(doc):
                        for i, item in enumerate(lst):
                            if isinstance(item, dict) and is_record(item):
                                got.append(mk_record(item, rel(p, inp), "%s/%d" % (ptr.rstrip("/"), i),
                                                     len(got), fixture=is_dup_file))
                json_hits += 1 if got else 0
            elif ext in (".csv", ".tsv"):
                got, err = csv_records(p, inp)
                if err:
                    degradations.append({"stage": "discover", "file": rel(p, inp), "issue": "csv_parse",
                                         "detail": err})
            elif ext != ".md" or not json_hits:
                got = text_records(p, inp)
            if got:
                for r in got:
                    r["order"] = len(cands)
                    cands.append(r)
                sources.append({"path": rel(p, inp), "kind": "duplicates_fixture" if is_dup_file else "candidates",
                                "records": len(got), "fixture": is_dup_file})
            else:
                sources.append({"path": rel(p, inp), "kind": "scanned", "records": 0})
        except Exception as exc:
            degradations.append({"stage": "discover", "file": rel(p, inp), "issue": "file_skipped",
                                 "detail": "%s: %s" % (type(exc).__name__, str(exc)[:120])})
    seen = {}
    for r in cands:
        base = re.sub(r"\s+", "", s(r["record_id"])) or "r"
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            r["record_id"] = "%s#%d" % (base, seen[base])
    overflow = max(0, len(cands) - MAX_RECORDS)
    return cands[:MAX_RECORDS], sources, degradations, overflow


def load_annotations(inp):
    """Annotation-only files: opinions (fixtures), query logs, import state."""
    out = {"opinions": [], "queries": [], "state": [], "fixtures": []}
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".json", ".jsonl", ".csv"):
            continue
        name = p.name.lower()
        if any(k in name for k in DUPFILE_PAT):
            continue
        try:
            if any(k in name for k in ANNOT_PAT):
                obj, err = load_json(p)
                for it in (obj if isinstance(obj, list) else [obj]):
                    if isinstance(it, dict):
                        for k, v in list(it.items())[:20]:
                            if isinstance(v, list):
                                out["opinions"] += [{"source": rel(p, inp), "key": str(k), "item": x}
                                                    for x in v[:30]]
                            else:
                                out["opinions"].append({"source": rel(p, inp), "key": str(k), "item": v})
                if err:
                    out["state"].append({"file": rel(p, inp), "issue": err})
            elif any(k in name for k in QUERY_PAT):
                out["queries"] += [{"query": q[:300], "source": rel(p, inp)} for q in
                                   re.findall(r'"([^"]{12,300})"', read_text(p))[:20] if " " in q]
            elif any(k in name for k in STATE_PAT):
                obj, _ = load_json(p)
                out["state"].append({"file": rel(p, inp), "value": obj if isinstance(obj, (dict, list)) else None})
        except Exception:
            continue
    return out
