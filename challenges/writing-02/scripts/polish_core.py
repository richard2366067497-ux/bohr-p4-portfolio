"""claim-preserving-polish — core library (Python stdlib only).

本模块只做确定性重活：解析输入、切段、抽取可核验原子、限定强度分级、
契约字段解析、差异度量。语义判断（怎么写、为什么改）由 Agent 写进工作稿。
"""
import csv
import difflib
import hashlib
import json
import os
import re
import time
from collections import Counter

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_PATH = os.path.join(SKILL_ROOT, "assets", "hedge_lexicon.json")
SKILL_NAME = "claim-preserving-polish"
SKILL_VERSION = "1.0.0"

EDIT_TYPES = [
    "grammar", "syntax", "terminology", "register", "punctuation", "concision",
    "cohesion", "word_choice", "article", "preposition", "tense", "voice",
    "agreement", "spelling", "capitalization", "restructure", "translate", "other",
]
OVERRIDE_TYPES = {"restructure", "translate"}
WEAK_REASONS = {"", "better", "improve", "改进", "更学术", "优化", "润色", "更好", "ok", "n/a"}

_FALLBACK_LEX = {
    "hedge_levels": {
        "4": {"en": ["demonstrate", "prove", "confirm", "clearly", "always", "never", "conclusively"],
              "zh": ["证明", "证实", "显然", "必然", "总是", "从不"]},
        "3": {"en": ["show", "indicate", "reveal", "likely", "primarily"],
              "zh": ["显示", "表明", "发现", "很可能", "主要"]},
        "2": {"en": ["suggest", "may", "might", "could", "appear", "seem", "possibly", "potential"],
              "zh": ["提示", "可能", "或许", "似乎", "潜在"]},
        "1": {"en": ["associated with", "correlat", "linked to"], "zh": ["相关", "关联", "伴随"]},
        "0": {"en": ["cannot exclude", "remains unclear", "insufficient"],
              "zh": ["无法排除", "尚不清楚", "证据不足"]},
    },
    "absolute_markers": {"en": ["always", "never", "all", "none", "entirely"],
                         "zh": ["总是", "从不", "所有", "全部", "完全"]},
    "association_markers": {"en": ["associated with", "correlat", "linked to"], "zh": ["相关", "关联"]},
    "causal_markers": {"en": ["causes", "leads to", "results in", "drives", "due to"],
                       "zh": ["导致", "引起", "造成", "驱动"]},
    "negation_markers": {"en": ["not", "no", "none", "never", "without", "cannot", "fail to"],
                         "zh": ["没有", "无法", "不能", "并非", "未能"]},
    "claim_core": {"en": ["may", "might", "could", "suggest", "indicate", "appear", "seem", "likely",
                          "demonstrate", "confirm", "associated with", "correlat"],
                   "zh": ["可能", "提示", "似乎", "显示", "表明", "证明", "相关"]},
    "units": ["%", "mg", "kg", "mL", "min", "mm", "cm", "nm", "kDa", "mM", "µM", "mM", "h", "yr", "°C", "Hz", "eV"],
    "citation_patterns": [r"\[\s*\d+(?:\s*[-,–—]\s*\d+)*\s*\]",
                          r"\(\s*[A-Z][A-Za-z\-']{1,30}(?:\s+et\s+al\.?)?\s*,\s*\d{4}[a-z]?\s*\)"],
    "pointer_patterns": [r"(?:Fig(?:ure)?\.?|fig\.?)\s*\d+[A-Za-z]?",
                         r"(?:Table|Tab\.?)\s*\d+[A-Za-z]?", r"(?:Sec(?:tion)?\.?)\s*\d+(?:\.\d+)*"],
    "abbrev_pattern": r"\b(?:[A-Z]{2,6}s?|[A-Z][a-z]?[A-Z]{1,4}[a-z]?)\b",
    "abbrev_stopwords": ["A", "I", "AN", "AND", "OR", "THE", "NOT", "ALL", "FOR", "IS", "ARE", "WE", "IN"],
    "term_candidate_suffixes": ["网络", "模型", "算法", "分析", "方法", "机制", "network", "model", "analysis"],
    "equivalence_hints": [],
}

_LEX_CACHE = {}

def load_lexicon():
    """读取词表资产；资产缺失或损坏时退回内置最小词表，绝不让流程中断。"""
    salt = ASSET_PATH
    if salt in _LEX_CACHE:
        return _LEX_CACHE[salt]
    lex = json.loads(json.dumps(_FALLBACK_LEX))
    note = ""
    try:
        with open(ASSET_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            for key, val in data.items():
                if val is not None:
                    lex[key] = val
    except Exception as exc:  # noqa: BLE001 - 资产缺失必须降级而不是崩
        note = "lexicon fallback: %s" % exc
    lex["_load_note"] = note
    _LEX_CACHE[salt] = lex
    return lex

def norm_ws(text):
    return re.sub(r"[ \t\u00a0\u3000]+", " ", (text or "").replace("\r", "")).strip()

def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

def read_text_any(path):
    """宽松读取：依次尝试 utf-8 / utf-8-sig / gb18030 / latin-1，返回 (text, encoding, warning)。"""
    try:
        raw = open(path, "rb").read()
    except Exception as exc:  # noqa: BLE001
        return "", "", "unreadable: %s" % exc
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            txt = raw.decode(enc)
            warn = ""
            if "\ufffd" in txt:
                warn = "replacement-char present after %s decode" % enc
            return txt, enc, warn
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1", "decoded with latin-1 (encoding suspect)"

def cjk_ratio(text):
    body = [ch for ch in (text or "") if not ch.isspace()]
    if not body:
        return 0.0
    cjk = sum(1 for ch in body if "\u4e00" <= ch <= "\u9fff")
    return cjk / float(len(body))

def detect_language(text):
    if not (text or "").strip():
        return "unknown"
    return "zh" if cjk_ratio(text) >= 0.30 else "en"

def similarity(before, after):
    a, b = norm_ws(before), norm_ws(after)
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()

_HEAD_RE = re.compile(r"^\s{0,3}(#{1,6}\s+\S|\\(?:sub)*section\*?\{|\\chapter\*?\{)")
_FENCE = ("```", "~~~")
_MATH_ENV = re.compile(r"^\s*\\begin\{(equation|align|eqnarray|gather|multline|displaymath|figure|table)\*?\}")
_ABBR_GUARD = ["e.g.", "i.e.", "et al.", "al.", "Fig.", "Figs.", "Eq.", "Eqs.", "Ref.", "Refs.", "vs.",
               "No.", "approx.", "cf.", "Dr.", "Prof.", "Suppl.", "resp.", "i.v.", "i.p.", "p.o."]

def split_paragraphs(text):
    """按空行/标题/代码块/公式环境切块；返回 [{'kind':..., 'text':...}]，不改动任何字符内容。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    blocks, buf, i = [], [], 0

    def flush():
        if buf:
            seg = "\n".join(buf).strip("\n")
            if seg.strip():
                blocks.append({"kind": "body", "text": seg})
            del buf[:]

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if s.startswith(_FENCE):
            flush()
            fence = s[:3]
            chunk = [raw]
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                chunk.append(lines[i])
                i += 1
            if i < len(lines):
                chunk.append(lines[i])
                i += 1
            blocks.append({"kind": "frozen", "text": "\n".join(chunk)})
            continue
        if s.startswith("$$") or _MATH_ENV.match(s):
            flush()
            chunk = [raw]
            i += 1
            if s.startswith("$$") and s.count("$$") < 2:
                while i < len(lines) and "$$" not in lines[i]:
                    chunk.append(lines[i])
                    i += 1
                if i < len(lines):
                    chunk.append(lines[i])
                    i += 1
            elif not s.startswith("$$"):
                env = _MATH_ENV.match(s).group(1)
                end_re = re.compile(r"\\end\{%s\*?\}" % env)
                while i < len(lines) and not end_re.search(lines[i]):
                    chunk.append(lines[i])
                    i += 1
                if i < len(lines):
                    chunk.append(lines[i])
                    i += 1
            blocks.append({"kind": "frozen", "text": "\n".join(chunk)})
            continue
        if not s:
            flush()
            i += 1
            continue
        if _HEAD_RE.match(s):
            flush()
            blocks.append({"kind": "heading", "text": s})
            i += 1
            continue
        buf.append(raw)
        i += 1
    flush()
    return blocks

def split_sentences(text):
    guarded, marks = text, {}
    for idx, tok in enumerate(_ABBR_GUARD):
        ph = "\x01%d\x01" % idx
        if tok in guarded:
            guarded = guarded.replace(tok, ph)
            marks[ph] = tok
    parts, start = [], 0
    for m in re.finditer(r"[.!?。！？]+(?=\s|$)", guarded):
        parts.append(guarded[start:m.end()])
        start = m.end()
    if guarded[start:].strip():
        parts.append(guarded[start:])
    out = []
    for part in parts:
        for ph, tok in marks.items():
            part = part.replace(ph, tok)
        if part.strip():
            out.append(part.strip())
    return out

def _unit_list(lex):
    units = [u for u in lex.get("units", []) if isinstance(u, str)]
    keep = [u for u in units if len(u) >= 2 or u in ("%", "‰", "°")]
    return sorted(set(keep), key=len, reverse=True)

def extract_spans(text, lex=None):
    """抽取不可编辑原子：数字、数字+单位、引用标记、图表/章节指向、公式、缩写。"""
    lex = lex or load_lexicon()
    text = text or ""
    spans = {"number": [], "unit_pair": [], "citation": [], "pointer": [], "equation": [], "abbr": []}
    unit_alt = "|".join(re.escape(u) for u in _unit_list(lex)) or r"(?!)"
    num_pat = r"[-+]?\d+(?:[.,]\d+)*(?:\s*[–—]\s*\d+(?:[.,]\d+)*)?(?:\s?[eE][-+]?\d+)?"
    quant_re = re.compile(r"(?<![A-Za-z0-9_])(" + num_pat + r")(?:\s?(" + unit_alt + r")(?![A-Za-z]))?")
    for m in quant_re.finditer(text):
        number = re.sub(r"\s+", "", m.group(1))
        spans["number"].append(number)
        if m.group(2):
            spans["unit_pair"].append("%s|%s" % (number, m.group(2)))
    for pat in lex.get("citation_patterns", []):
        try:
            for m in re.finditer(pat, text):
                spans["citation"].append(re.sub(r"\s+", "", m.group(0)))
        except re.error:
            continue
    for pat in lex.get("pointer_patterns", []):
        try:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                spans["pointer"].append(_norm_pointer(m.group(0)))
        except re.error:
            continue
    for m in re.finditer(r"\$\$[^$]+\$\$|\$[^$\n]+\$|\\\([^)]*\\\)|\\\[[^\]]*\\\]", text):
        spans["equation"].append(re.sub(r"\s+", "", m.group(0)))
    abbr_re = lex.get("abbrev_pattern") or r"\b[A-Z]{2,6}\b"
    stop = set(lex.get("abbrev_stopwords", []))
    try:
        for m in re.finditer(abbr_re, text):
            tok = m.group(0)
            base = tok.rstrip("s") if tok.endswith("s") and tok[:-1] in stop.union({"SD", "SE", "CI"}) else tok
            if base not in stop and not tok.isdigit():
                spans["abbr"].append(base)
    except re.error:
        pass
    return spans

def _norm_pointer(tok):
    same = tok.lower()
    num = re.search(r"\d+[A-Za-z]?", same)
    n = num.group(0) if num else "?"
    if re.match(r"^(fig|figure)", same):
        kind = "fig"
    elif re.match(r"^(table|tab)", same):
        kind = "table"
    elif re.match(r"^(sec|section)", same):
        kind = "sec"
    elif re.match(r"^(eq|equation)", same):
        kind = "eq"
    elif same.startswith("supp") or same.startswith("support"):
        kind = "supp"
    elif same.startswith("appendix"):
        kind = "appendix"
    elif same.startswith("章") or same.startswith("第"):
        kind = "sec"
    elif same.startswith("图"):
        kind = "fig"
    elif same.startswith("表"):
        kind = "table"
    elif same.startswith("式"):
        kind = "eq"
    else:
        kind = "other"
    return "%s:%s" % (kind, n)

HARD_ATOM_CLASSES = ("number", "unit_pair", "citation", "pointer", "equation")
ATOM_LABELS = {
    "number": "数字", "unit_pair": "数字+单位", "citation": "引用标记", "pointer": "图表/章节指向",
    "equation": "公式", "abbr": "缩写/专名",
}

def atom_counter(spans):
    return {k: Counter(v) for k, v in spans.items()}

def diff_atoms(before_spans, after_spans, classes=HARD_ATOM_CLASSES):
    """返回丢失/新增原子列表：只比对出现次数，丢失即违规（新增另计）。"""
    lost, added = [], []
    for cls in classes:
        cb = Counter(before_spans.get(cls, []))
        ca = Counter(after_spans.get(cls, []))
        for tok, n in (cb - ca).items():
            lost.append({"class": cls, "value": tok, "count": n})
        for tok, n in (ca - cb).items():
            added.append({"class": cls, "value": tok, "count": n})
    return lost, added

def _hits(text, markers):
    low = (text or "").lower()
    out = []
    for mk in markers or []:
        m = str(mk).lower()
        if not m:
            continue
        if re.search(r"[a-z]", m):
            pat = r"(?<![a-z])" + re.escape(m) + r"[a-z]{0,3}(?![a-z])"
            if re.search(pat, low):
                out.append(mk)
        elif m in (text or ""):
            out.append(mk)
    return out

def hedge(text, lex=None, lang=None):
    """返回 (等级, 命中标记列表)；等级 0–4，越大越接近“已确立事实”。"""
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    levels = lex.get("hedge_levels", {})
    hit = []
    best = -1
    for lvl in sorted(levels.keys(), key=lambda x: -int(x)):
        markers = []
        if lang != "en":
            markers += levels[lvl].get("zh", [])
        if lang != "zh":
            markers += levels[lvl].get("en", [])
        found = _hits(text, markers)
        if found and best < 0:
            best = int(lvl)
            hit = found
    return (best if best >= 0 else 0), hit

def hedge_profile(text, lex=None, lang=None):
    """返回全部层级上的命中：{'level','markers','all','by_level'}。
    单看最高级会漏掉“同级两个限定词删掉一个”的情况，故此处保留全量供逐词比对。"""
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    levels = lex.get("hedge_levels", {})
    by_level, overall = {}, 0
    for lvl in sorted(levels.keys(), key=lambda x: int(x)):
        markers = []
        if lang != "en":
            markers += levels[lvl].get("zh", [])
        if lang != "zh":
            markers += levels[lvl].get("en", [])
        found = _hits(text, markers)
        if found:
            by_level[int(lvl)] = found
            overall = max(overall, int(lvl))
    all_hits = [m for lvl in by_level for m in by_level[lvl]]
    return {"level": overall, "markers": by_level.get(overall, []), "all": all_hits,
            "by_level": by_level}

def claim_core(text, lex=None, lang=None):
    """主张内核词：情态动词与主张动词（不含 some/several 这类量词），
    用于检测“句子里明明还有一个限定词、但关键的 may 被删掉了”的隐性加强。"""
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    core = lex.get("claim_core", {})
    marks = []
    if lang != "en":
        marks += core.get("zh", [])
    if lang != "zh":
        marks += core.get("en", [])
    return _hits(text, marks)

def negation_count(text, lex=None, lang=None):
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    marks = lex.get("negation_markers", {})
    if lang == "zh":
        return len(_hits(text, marks.get("zh", [])))
    return len(_hits(text, marks.get("en", [])))

def causal_terms(text, lex=None, lang=None):
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    marks = lex.get("causal_markers", {})
    return _hits(text, marks.get("zh", [])) + _hits(text, marks.get("en", []))

def association_terms(text, lex=None, lang=None):
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    marks = lex.get("association_markers", {})
    return _hits(text, marks.get("zh", [])) + _hits(text, marks.get("en", []))

def absolutes(text, lex=None, lang=None):
    lex = lex or load_lexicon()
    lang = lang or detect_language(text)
    marks = lex.get("absolute_markers", {})
    return _hits(text, marks.get("zh", [])) + _hits(text, marks.get("en", []))

_PRESENTATION_RE = [
    r"\b(?:is|are|was|were|be|been)\s+(?:shown|presented|displayed|depicted|illustrated|listed|summari[sz]ed)\b",
    r"\b(?:Fig(?:ure)?\.?|Table|Tab\.?|Eq\.?|Equation)\s*\(?\d+[A-Za-z]?\)?\s+(?:shows?|presents?|displays?|depicts?|illustrates?|summari[sz]es?)\b",
    r"\b(?:shows?|presents?|displays?|depicts?|illustrates?)\s+(?:in\s+)?(?:Fig(?:ure)?\.?|Table)\s*\d+[A-Za-z]?",
    r"图\s*\d+[A-Za-z]?\s*(?:显示|展示|给出|列出|呈现|所示)",
    r"表\s*\d+[A-Za-z]?\s*(?:显示|列出|给出|汇总)",
    r"(?:如)?[图表]\s*\d+[A-Za-z]?\s*所示",
]

def mask_presentation(text):
    """把“图/表 2 显示…”这类**指路**用法掩掉：
    show/present 在指路句里是版式动词，不承载结论强度，不能因它改写而判为削弱/加强。"""
    out = text or ""
    for pat in _PRESENTATION_RE:
        try:
            out = re.sub(pat, " ", out, flags=re.IGNORECASE)
        except re.error:
            continue
    return out

_CONTRACT_RULES = [
    ("polished_text", ("polished", "polish", "revised", "rewrite", "rewritten", "corrected", "clean",
                       "final", "全文", "润色后", "改后", "成品")),
    ("edit_log", ("edit", "change", "revision", "diff", "modif", "修改", "改动")),
    ("glossary", ("glossar", "terminolog", "lexicon", "术语", "词表")),
    ("bilingual", ("bilingual", "parallel", "translation", "对照", "译文", "双语")),
    ("verification", ("verif", "check", "audit", "coverage", "metric", "stat", "校验", "覆盖", "自查")),
    ("pending_human", ("human", "pending", "confirm", "manual", "人工", "待确认")),
    ("uncertainty", ("uncertain", "ambigu", "risk", "flag", "open_question", "不确定", "存疑")),
    ("sources", ("source", "provenance", "evidence", "trace", "来源", "出处", "证据")),
    ("limits", ("limit", "caveat", "gap", "约束", "限制", "边界", "缺口")),
    ("structure", ("section", "structure", "outline", "段落", "结构")),
    ("status", ("status", "state", "状态",)),
    ("notes", ("note", "comment", "remark", "备注", "说明")),
]

def canon(name):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(name).lower())

def resolve_kind(field_name):
    """把契约字段名映射到载荷类型：先精确匹配，再取命中的最长关键词。
    取最长可避免 "status" 被 "stat"（verification）抢走这类子串误配。"""
    c = canon(field_name)
    if c in ("caseid", "id", "taskid", "sampleid"):
        return "case_id"
    best, best_len = "", 0
    for kind, tokens in _CONTRACT_RULES:
        for tok in tokens:
            if tok in c and len(tok) > best_len:
                best, best_len = kind, len(tok)
    return best

def shape_contract(contract):
    """把 output_contract 规整成 [(field_name, declared_value)]；容忍 list / 嵌套 dict 写法。"""
    if isinstance(contract, dict):
        return [(k, v) for k, v in contract.items()]
    if isinstance(contract, list):
        out = []
        for item in contract:
            if isinstance(item, str):
                out.append((item, None))
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if name:
                    out.append((name, item.get("type")))
        return out
    return []

def fill_value(declared, kind, ctx):
    """按 kind 取载荷；declared 若为 dict 则递归按同名字段填一层。"""
    payload = ctx.get(kind)
    if isinstance(declared, dict) and declared:
        nested = {}
        for key in declared.keys():
            sub = resolve_kind(key)
            nested[key] = ctx.get(sub) if sub else None
        if not any(v for v in nested.values()) and payload is not None:
            return payload
        return nested
    return payload

def log(msg=""):
    print(msg, flush=True)

def ensure(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

def jload(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default

def jdump(path, obj):
    ensure(os.path.dirname(path) or ".")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def write_text(path, text):
    ensure(os.path.dirname(path) or ".")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)

def write_csv(path, header, rows):
    ensure(os.path.dirname(path) or ".")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])
    os.replace(tmp, path)

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())

def find_span(base, needle):
    """在 base 中定位 needle：先逐字匹配，再容忍空白差异。返回 (start, end) 或 None。"""
    if not needle:
        return None
    pos = base.find(needle)
    if pos >= 0:
        return pos, pos + len(needle)
    parts = [re.escape(p) for p in re.split(r"\s+", needle.strip()) if p]
    if not parts:
        return None
    try:
        m = re.search(r"\s+".join(parts), base)
    except re.error:
        return None
    return (m.start(), m.end()) if m else None
