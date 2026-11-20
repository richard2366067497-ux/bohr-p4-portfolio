#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.py — 材料发现、文本提取、语义切段、保护性 span 与术语候选（纯标准库、离线、确定性）。

只做确定性机械工作：读文件、分页、切段、给 locator、抽 span 与候选术语；译什么、怎么译、
术语定什么名由 Agent 写进 work/draft.json，不在本模块。

切段规则 R1–R7 与 SKILL.md §4.2 同一套编号（空行/句末/连字符/跨页/页眉页脚/双栏/标题）。

类型标签（type 字段）：heading / body / caption_figure / caption_table / table_header /
table_row / formula / reference
"""
import html
import json
import os
import re
import zipfile
import zlib

TEXT_EXT = (".txt", ".md", ".markdown", ".html", ".htm", ".docx", ".json")
SKIP_NAMES = {"case.json", "task.md", "readme.md", "result.json", "index.json",
              "audit_report.json", "check_report.json", "glossary.json",
              "paragraph_pairs.jsonl", "run_log.txt"}
SKIP_DIRS = {"work", "output", "app", ".git", "__pycache__", "node_modules",
             ".scimaster-runtime", "skills"}


def norm_ws(s):
    """空白归一化：连续空白压成单空格并去首尾（引文比对与展示都用它）。"""
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


PLACEHOLDER_ONLY = re.compile(
    r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|"
    r"\bplaceholder\b|\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|\bnull\b|\bNone\b|"
    r"\bN/?A\b|^\s*\.\.\.\s*$|<[A-Za-z_][\w /-]*>|example\.com|lorem ipsum", re.I | re.M)


def placeholder_only(text):
    """整页只剩占位符/标记（或短到不构成材料）→ 判为不可用，不作素材。"""
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "", PLACEHOLDER_ONLY.sub(" ", text or ""))
    return len(s) < 12


def quote_find(hay, needle):
    """逐字定位，返回 (found, offset, matched)。

    只容忍空白差异与软连字符；不做标点/大小写模糊匹配——回译或补省略必须判为未命中。
    """
    n = norm_ws(needle)
    if not n:
        return False, -1, ""
    if n in hay:
        return True, hay.find(n), n
    h = norm_ws(hay).replace("­", "")
    n2 = n.replace("­", "")
    if n2 and n2 in h:
        return True, h.find(n2), n2
    return False, -1, ""


# --- PDF 文本层

LIG = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
       "ﬄ": "ffl", "’": "'", "“": '"', "”": '"'}


def _fix_lig(t):
    for k, v in LIG.items():
        t = t.replace(k, v)
    return t


def _pdf_decode(raw):
    """解码 PDF 字面量字符串（处理 \\n \\t \\( \\) \\\\ 与八进制转义）。"""
    out, i, n = bytearray(), 0, len(raw)
    esc = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
           ord("("): 40, ord(")"): 41, ord("\\"): 92}
    while i < n:
        c = raw[i]
        if c == 0x5C and i + 1 < n:
            nxt = raw[i + 1]
            if nxt in esc:
                out.append(esc[nxt]); i += 2; continue
            if 0x30 <= nxt <= 0x37:
                j, o = i + 1, ""
                while j < n and len(o) < 3 and 0x30 <= raw[j] <= 0x37:
                    o += chr(raw[j]); j += 1
                out.append(int(o, 8) & 0xFF); i = j; continue
            i += 2; continue
        out.append(c); i += 1
    if out[:2] == b"\xfe\xff":
        return out[2:].decode("utf-16-be", "replace")
    return out.decode("latin-1")


PDF_TOKEN = re.compile(
    rb"\((?:\\.|[^\\()])*\)|\[|\]|<<|>>|/[^\s/\[\]<>()]+|[-+]?(?:\d+\.\d*|\.\d+|\d+)|[A-Za-z'\"*]+", re.S)


def _pdf_stream_text(stream):
    """把一个 content stream 解释成文本行（只处理文本块与常用定位算子）。"""
    lines, cur, stack = [], [], []
    for m in PDF_TOKEN.finditer(stream):
        tok = m.group(0)
        if not tok:
            continue
        c0 = tok[0:1]
        if c0 == b"(":
            (stack[-1] if stack else cur).append(_pdf_decode(tok[1:-1]))
        elif tok == b"[":
            stack.append([])
        elif tok == b"]":
            if stack:
                arr = stack.pop()
                (stack[-1] if stack else cur).append("".join(x for x in arr if isinstance(x, str)))
        elif c0 == b"/" or tok in (b"<<", b">>"):
            continue
        else:
            try:
                float(tok)
                if stack:
                    stack[-1].append(" ")
                continue
            except ValueError:
                pass
            if tok.decode("latin-1") in ("Tj", "TJ", "'", '"', "Td", "TD", "T*", "TL", "Tm", "BT", "ET"):
                text = "".join(cur)
                if text:
                    lines.append(text)
                cur = []
    if cur and "".join(cur):
        lines.append("".join(cur))
    return "\n".join(ln.rstrip() for ln in lines if ln.strip())


def _pdf_builtin(path):
    """内置 PDF 文本层抢救：解 FlateDecode 也接受未压缩流；无文本层返回空并标 degraded。"""
    with open(path, "rb") as f:
        raw = f.read()
    if b"/Encrypt" in raw[:200000]:
        return [], "encrypted_pdf"
    streams = []
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        body = raw[start:end]
        for attempt in (lambda b: zlib.decompress(b),
                        lambda b: zlib.decompressobj().decompress(b)):
            try:
                streams.append(attempt(body)); break
            except Exception:
                continue
        else:
            if b"BT" in body and (b"Tj" in body or b"TJ" in body):
                streams.append(body)
    pages = []
    for st in streams:
        if b"BT" not in st:
            continue
        txt = _fix_lig(_pdf_stream_text(st))
        if txt.strip():
            pages.append(txt)
    return pages, ("ok" if pages else "no_text_layer")


# --- 其他格式

def _html_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|section|article|table)>", "\n\n", raw)
    raw = re.sub(r"(?is)<t[dh][^>]*>", "\t", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return html.unescape(raw)


def _docx_text(path):
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            return ""
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"(?is)<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"(?is)</w:p>", "\n\n", xml)
    xml = re.sub(r"(?is)<w:br[^>]*/>", "\n", xml)
    xml = re.sub(r"(?is)</w:tc>", "\t", xml)
    return html.unescape(re.sub(r"(?s)<[^>]+>", "", xml))


def _plain(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _json_text(path):
    """材料型 json：挑最长的长字符串字段，避免把元数据当论文。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return ""
    best = []

    def walk(node, depth=0):
        if depth > 4:
            return
        if isinstance(node, str):
            if len(node) > 400:
                best.append(node)
        elif isinstance(node, dict):
            for k in sorted(node.keys()):
                walk(node[k], depth + 1)
        elif isinstance(node, list):
            for it in node:
                walk(it, depth + 1)

    walk(data)
    best.sort(key=len, reverse=True)
    return "\n\n".join(best[:1])


def load_material(path):
    low = path.lower()
    if low.endswith(".pdf"):
        pages, how = _pdf_builtin(path)
        return pages, "pdf", "builtin:" + how, ["builtin_pdf_extractor"] + \
            ([] if how == "ok" else [how])
    if low.endswith((".html", ".htm")):
        return [_html_text(path)], "html", "html->text", []
    if low.endswith(".docx"):
        return [_docx_text(path)], "docx", "docx->text", []
    if low.endswith(".json"):
        t = _json_text(path)
        return ([t] if t else []), "json", "json->text", []
    return [_plain(path)], "txt", "plain", []


def discover(input_dir):
    """递归发现输入材料；跳过 case.json/task.md、既往产物目录与草稿文件。"""
    mats, skipped = [], []
    if not os.path.isdir(input_dir):
        return mats, skipped, ["input_dir_missing:" + input_dir]
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(files):
            p = os.path.join(root, fn)
            low = fn.lower()
            if low in SKIP_NAMES or low.startswith(("smoke", "draft")):
                skipped.append(p)
            elif low.endswith(".pdf") or low.endswith(TEXT_EXT):
                mats.append(p)
            else:
                skipped.append(p)
    return mats, skipped, []


# --- case.json

def salvage_case(raw):
    """case.json 坏掉时抢救 case_id 与 output_contract 顶层键名（字面扫描，不编造取值）。"""
    out = {}
    try:
        m = re.search(r'"case_id"\s*:\s*"([^"]{1,120})"', raw)
        if m:
            out["case_id"] = m.group(1)
        m = re.search(r'"output_contract"\s*:\s*\{', raw)
        if m:
            block, depth, i = raw[m.end():min(len(raw), m.end() + 6000)], 1, 0
            keys = []
            while i < len(block):
                ch = block[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif ch == '"':
                    j = block.find('"', i + 1)
                    if j < 0:
                        break
                    name = block[i + 1:j]
                    k = j + 1
                    while k < len(block) and block[k] in " \t\r\n":
                        k += 1
                    if depth == 1 and k < len(block) and block[k] == ":" \
                            and re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$", name) \
                            and name not in keys:
                        keys.append(name)
                    i = j
                i += 1
            if keys:
                out["output_contract"] = dict((k, None) for k in keys)
    except Exception:
        pass
    return out


def read_case(input_dir):
    """读 case.json / task.md；任何异常只记录到 errors，不抛出。"""
    case, task_text, errors = {}, "", []
    cpath = os.path.join(input_dir, "case.json")
    if os.path.isfile(cpath):
        raw = ""
        try:
            with open(cpath, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()
            case = json.loads(raw)
            if not isinstance(case, dict):
                errors.append("case_json_not_object")
                case = {"_raw": raw}
        except Exception as e:
            errors.append("case_json_parse_error:" + type(e).__name__)
            case = salvage_case(raw)
            if case.get("case_id"):
                errors.append("case_json_salvaged:case_id=%s" % case["case_id"])
    else:
        errors.append("case_json_missing")
    tpath = os.path.join(input_dir, "task.md")
    if os.path.isfile(tpath):
        try:
            task_text = _plain(tpath)
        except Exception as e:
            errors.append("task_md_read_error:" + type(e).__name__)
    else:
        errors.append("task_md_missing")
    return case, task_text, errors


def embedded_text(case):
    """case.json 可能内嵌正文：在已知正文字段名里挑最长的一段。"""
    cand = []
    keys = ("text", "content", "body", "paper_text", "fulltext", "article",
            "source_text", "material", "manuscript")

    def walk(node, depth=0):
        if depth > 4:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and k.lower() in keys and len(v) > 400 \
                        and "`" not in v[:40]:
                    cand.append(v)
                walk(v, depth + 1)
        elif isinstance(node, list):
            for it in node:
                walk(it, depth + 1)

    try:
        walk(case)
    except Exception:
        pass
    cand.sort(key=len, reverse=True)
    return cand[0] if cand else ""


# --- 版面与切段

ABBREV = ("et al.", "e.g.", "i.e.", "fig.", "figs.", "eq.", "eqs.", "vs.", "no.",
          "approx.", "ref.", "refs.", "sec.", "resp.", "cf.", "al.", "dr.", "prof.")

SEC_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s*)?(abstract|summary|introduction|background|related work|"
    r"materials? and methods?|methods?|experimental|results?|discussion|conclusions?|"
    r"acknowledg(?:e)?ments?|references?|bibliography|supplementary|appendix(?:es)?|"
    r"摘要|引言|前言|方法|结果|讨论|结论|参考文献|致谢)\b", re.I)
HEAD_NUM_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z一-鿿]")
CAP_RE = re.compile(r"^(fig(?:ure)?\.?\s*\d+|table\s*\d+|图\s*\d+|表\s*\d+|scheme\s*\d+)", re.I)
FORMULA_RE = re.compile(r"(?:^|\s)\(?\d{1,3}\)\s*$")
ROW_RE = re.compile(r"\t.*\t|\s\|\s")


def _mask_digits(s):
    return re.sub(r"\d+", "#", norm_ws(s))


def drop_running_lines(pages_lines):
    """R5：跨页重复的短行视为页眉页脚。返回 (清洗后的行, 丢弃数)。"""
    seen = {}
    for li, lines in enumerate(pages_lines):
        for pos, ln in enumerate(lines):
            if not ln.strip() or len(ln) > 80 or 1 < pos < len(lines) - 2:
                continue
            seen.setdefault(_mask_digits(ln), set()).add(li)
    repeated = {k for k, v in seen.items() if len(v) >= 3}
    out, dropped = [], 0
    for lines in pages_lines:
        kept = []
        for pos, ln in enumerate(lines):
            if ln.strip() and len(ln) <= 80 and (pos <= 1 or pos >= len(lines) - 2) \
                    and _mask_digits(ln) in repeated:
                dropped += 1
                continue
            kept.append(ln)
        out.append(kept)
    return out, dropped


def split_columns(lines):
    """R6：投影法找中部空白槽，返回 (left, right, used)。三条同时满足才切，避免误切单栏。"""
    cand = [ln for ln in lines if len(ln) >= 30]
    if len(cand) < 6:
        return lines, [], False
    width = max(len(ln) for ln in cand)
    if width < 60:
        return lines, [], False
    best_col, best_score = -1, 0
    for col in range(int(width * 0.38), int(width * 0.62) + 1):
        score = 0
        for ln in cand:
            if col >= len(ln) - 1 or ln[col] != " ":
                continue
            s = col
            while s > 0 and ln[s - 1] == " ":
                s -= 1
            e = col
            while e + 1 < len(ln) and ln[e + 1] == " ":
                e += 1
            if (e - s + 1) >= 3 and ln[:s].strip() and ln[e + 1:].strip():
                score += 1
        if score > best_score:
            best_score, best_col = score, col
    if best_col < 0 or best_score < 0.6 * len(cand):
        return lines, [], False
    left, right, used = [], [], False
    for ln in lines:
        if best_col < len(ln) and ln[best_col] == " " and ln[:best_col].strip() \
                and ln[best_col:].strip():
            left.append(ln[:best_col]); right.append(ln[best_col:]); used = True
        else:
            left.append(ln)
    return left, right, used


def _md(s):
    """去掉 markdown 前缀记号，便于标题/公式/表格的行形态判定。"""
    return re.sub(r"^[#*_>=\-\s]+", "", str(s)).strip()


def heading_like(s):
    """R7：行是否像标题（用于强制断段）。"""
    s = _md(s)
    if not s or len(s) > 95:
        return False
    if SEC_RE.match(s) and len(s.split()) <= 9:
        return True
    if HEAD_NUM_RE.match(s) and len(s.split()) <= 12:
        return True
    if re.search(r"[.!?。！？;:,]$", s):
        return False
    words = s.split()
    if 2 <= len(words) <= 13:
        caps = sum(1 for w in words if w[:1].isupper() or w.isupper())
        if caps >= max(2, int(0.7 * len(words))):
            return True
    return False


def page_to_blocks(page_text):
    """R1/R2/R3/R7：把一页文本切成段落候选块，返回 (块列表, 是否按双栏重排)。

    单栏时保留空行（R1 空行断段）；双栏重排后会丢掉空行位置，按 R2 的句末规则兜底。
    """
    lines = [ln.rstrip() for ln in page_text.split("\n")]
    left, right, used = split_columns([ln for ln in lines if ln.strip()])
    ordered = (left + [""] + right) if used else lines
    blocks, buf = [], []

    def flush():
        if buf:
            t = norm_ws(" ".join(buf))
            if t:
                blocks.append(t)
            del buf[:]

    for ln in ordered:
        s = ln.strip()
        if not s:
            flush(); continue
        if s.startswith(("•", "-", "·")) and buf:
            flush()
        if ROW_RE.search(s):
            flush(); blocks.append(s); continue
        if buf and (heading_like(buf[-1]) or heading_like(s)):
            flush()
        if buf:
            prev = buf[-1].rstrip()
            ends = bool(re.search(r"[.!?:;]$", prev))
            abbrev = any(prev.lower().endswith(a) for a in ABBREV)
            if ends and not abbrev and len(prev) > 30 \
                    and re.match(r"^[A-Z0-9(\[一-鿿]", s):
                flush()
        buf.append(s)
    flush()
    return blocks, used


def classify(text, section):
    """给块打类型标签；图表题注/表头/表行/公式/文献各自成类，便于完整性核对。"""
    t = norm_ws(text)
    raw = _md(text)
    if CAP_RE.match(t):
        return "caption_table" if re.match(r"^(table|表)", t, re.I) else "caption_figure"
    if ROW_RE.search(text):
        cells = [c for c in re.split(r"\t+|\s\|\s|\|", text) if c.strip()]
        if 2 <= len(cells) <= 14 and sum(len(c.strip()) for c in cells) < 220:
            numeric = sum(1 for c in cells if re.search(r"\d", c))
            return "table_row" if numeric else "table_header"
    if text.lstrip()[:1] in "#" and len(raw) <= 95:
        return "heading"
    if HEAD_NUM_RE.match(raw) and len(t) < 110:
        return "heading"
    if SEC_RE.match(raw) and len(t) < 110 and (raw.isupper() or len(raw.split()) <= 8):
        return "heading"
    if section == "references":
        return "reference"
    if len(t) < 200 and re.search(r"[=∑∏∫∂]", t) and FORMULA_RE.search(t):
        return "formula"
    words = t.split()
    if len(t) < 120 and len(words) <= 12 and "=" not in t and not re.search(r"[.!?;]\s", t):
        caps = sum(1 for w in words if w[:1].isupper() or w.isupper())
        if words and (caps >= 0.6 * len(words) or t.isupper()):
            return "heading"
    return "body"


# --- 保护性 span

SPAN_RULES = [
    ("pct", r"\d+(?:[.,]\d+)?\s?%"),
    ("pvalue", r"[pP]\s?[<=>]\s?0?\.\d+"),
    ("stat", r"(?<![A-Za-z])(?:r|R|R2|R²|t|F|d|χ2|χ²)\s?=\s?-?\d+(?:\.\d+)?"),
    ("pm", r"±\s?\d+(?:\.\d+)?"),
    ("num_unit", r"(?<![\w.])\d+(?:[.,]\d+)?\s?(?:kDa|MPa|kPa|GPa|Pa|kJ|kW|kV|keV|MeV|eV|"
                 r"GHz|MHz|kHz|Hz|mg/L|mg/kg|mg|µg|ug|kg|km|cm|mm|nm|µm|um|mL|µL|uL|ms|min|"
                 r"mol/L|mmol|mol|kcal|K|°C|°|rpm|ppm|ppb|dB|Da|bp|kb|Gy|Sv|mSv|atm|bar|"
                 r"Torr|s|h|g|L|m|M|V|A|W|J)\b"),
    ("cite_bracket", r"\[\d+(?:\s?[,–-]\s?\d+)*\]"),
    ("cite_author", r"\([A-Z][A-Za-z\-']+(?:\s+(?:et\s+al\.|and\s+[A-Z][A-Za-z\-']+))?,?\s?"
                    r"(?:19|20)\d{2}[a-z]?\)"),
    ("eq_tag", r"\(\s?\d{1,3}[a-z]?\s?\)"),
    ("fig_ref", r"(?:Fig(?:ure)?\.?|Table|Tab\.|Eq(?:uation)?\.?|Section|Sec\.)\s?"
                r"\d+(?:\.\d+)*[a-z]?"),
    ("greek", r"[α-ωΑ-Ωµ±×÷≈≤≥≠→←↑↓∑∏√∞∂∆]"),
]
SPAN_COMPILED = [(k, re.compile(p)) for k, p in SPAN_RULES]


def spans_of(text):
    """抽保护性 span（重叠保留更长匹配），返回按出现顺序去重的 [{kind,value}]。"""
    found = []
    for kind, rx in SPAN_COMPILED:
        for m in rx.finditer(text):
            found.append((m.start(), m.end(), kind, m.group(0)))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    used, out, seen = [], [], set()
    for s, e, kind, val in found:
        if any(not (e <= us or s >= ue) for us, ue in used):
            continue
        used.append((s, e))
        key = (kind, norm_ws(val))
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "value": norm_ws(val)})
    return out


# --- 术语候选

STOP = set("""the a an of and or in on at to for from with by as is are was were be been being
this that these those we our it its their they them can could may might would should must will
not no than then thus however therefore also such more most less least all any both each other
using used use based results result study studies show shows shown figure fig table eq equation
section data method methods approach proposed new two three one first second between within
which who whom whose what when where why how there here about into over under after before
during while because although though but if so do does did has have had""".split())


def snippet(text, idx, before=40, after=60):
    """取 idx 附近的逐字片段：前后扩展但对齐到词边界，避免把 "NaCl" 截成 "Na"。"""
    if idx < 0:
        return ""
    a = max(0, idx - before)
    if a > 0:
        sp = text.find(" ", a)
        if 0 <= sp < idx:
            a = sp + 1
    b = min(len(text), idx + after)
    if b < len(text):
        sp = text.rfind(" ", idx + 1, b)
        if sp > idx:
            b = sp
    return norm_ws(text[a:b])


def term_candidates(segments, limit=40):
    """候选术语：缩写、连字符词、双词短语、`full name (ACRONYM)` 定义对。打分只用于排序。"""
    stats, defs = {}, {}
    for seg in segments:
        t = seg["text"]
        for m in re.finditer(r"([A-Z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,2})\s*\(([A-Z]{2,6})\)"
                             r"|\b([A-Z]{2,6})\b", t):
            if m.group(2) and len(m.group(1)) > 3:
                defs.setdefault(m.group(2), norm_ws(m.group(1)).lower())
        for tok in re.findall(r"[A-Za-z][A-Za-z\-]{2,}|\b[A-Z]{2,6}\b", t):
            key = tok if tok.isupper() else tok.lower().strip("-")
            if len(key) < 3 or key.lower() in STOP:
                continue
            rec = stats.setdefault(key, {"n": 0, "sids": [], "ctx": ""})
            rec["n"] += 1
            if seg["sid"] not in rec["sids"]:
                rec["sids"].append(seg["sid"])
                if not rec["ctx"]:
                    rec["ctx"] = snippet(t, t.find(tok))
        words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", t)
        for i in range(len(words) - 1):
            a, b = words[i].lower(), words[i + 1].lower()
            if a in STOP or b in STOP or len(a) < 4 or len(b) < 4:
                continue
            rec = stats.setdefault(a + " " + b, {"n": 0, "sids": [], "ctx": ""})
            rec["n"] += 1
            if seg["sid"] not in rec["sids"]:
                rec["sids"].append(seg["sid"])
    out = []
    for term, rec in stats.items():
        score = rec["n"] * (1.6 if term in defs else 1.0) * (1.4 if "-" in term else 1.0)
        out.append({"term": term, "count": rec["n"], "sids": rec["sids"][:8],
                    "expansion": defs.get(term, ""), "context": rec["ctx"],
                    "score": round(score, 2)})
    out.sort(key=lambda x: (-x["score"], x["term"]))
    return out[:limit]


# --- 索引

def _counter(it):
    out = {}
    for k in it:
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def build_index(input_dir):
    """产出 index.json 内容；单步失败降级记录，不抛异常。"""
    idx = {"input_dir": input_dir, "sources": [], "pages": [], "segments": [],
           "warnings": [], "errors": [], "skipped": [], "text_chars": 0, "terms": []}
    mats, skipped, warns = discover(input_dir)
    idx["skipped"] = [os.path.relpath(p, input_dir) for p in skipped]
    idx["warnings"].extend(warns)

    pages = []
    for path in mats:
        rel = os.path.relpath(path, input_dir)
        try:
            pg, kind, how, w = load_material(path)
        except Exception as e:
            idx["errors"].append("material_read_failed:%s:%s" % (rel, type(e).__name__))
            continue
        kept, dropped = [], 0
        for p in pg:
            if p.strip() and not placeholder_only(p):
                kept.append(p)
            else:
                dropped += 1
        if not kept:
            idx["warnings"].append("no_usable_text:%s" % rel)
            idx["skipped"].append(rel)
            continue
        if dropped:
            idx["warnings"].append("placeholder_or_empty_pages_dropped:%s:%d" % (rel, dropped))
        idx["sources"].append({"path": rel, "kind": kind, "extractor": how,
                               "pages": len(kept), "chars": sum(len(p) for p in kept)})
        idx["warnings"].extend(w)
        for p in kept:
            pages.append({"page": len(pages) + 1, "text": p, "source": rel})

    case, _task, cerrs = read_case(input_dir)
    idx["errors"].extend(cerrs)
    if sum(len(p["text"].strip()) for p in pages) < 200:
        emb = embedded_text(case)
        if emb:
            pages = [{"page": 1, "text": emb, "source": "case.json:embedded"}]
            idx["sources"].append({"path": "case.json", "kind": "embedded",
                                   "extractor": "embedded", "pages": 1, "chars": len(emb)})
            idx["warnings"].append("text_from_case_json_embedded")

    idx["pages"] = [{"page": p["page"], "chars": len(p["text"]), "source": p["source"]}
                    for p in pages]
    idx["text_chars"] = sum(len(p["text"]) for p in pages)

    page_lines = [[ln.rstrip() for ln in p["text"].split("\n")] for p in pages]
    page_lines, dropped = drop_running_lines(page_lines)
    if dropped:
        idx["warnings"].append("running_header_footer_dropped:%d" % dropped)

    blocks, cols = [], []
    for i, lines in enumerate(page_lines):
        try:
            blks, used = page_to_blocks("\n".join(lines))
        except Exception:
            blks, used = [norm_ws(" ".join(lines))], False
        if used:
            cols.append(i + 1)
        for b in blks:
            blocks.append({"text": b, "page": i + 1, "pages": [i + 1], "bridged": False})
    if cols:
        idx["warnings"].append("two_column_split:pages=%s" % ",".join(map(str, cols[:12])))

    merged = []
    for b in blocks:                                  # R4 跨页续段
        if merged:
            prev = merged[-1]
            if not re.search(r"[.!?。！？:；]$", prev["text"].rstrip()) \
                    and prev["page"] != b["page"]:
                if prev["text"].endswith("-") and b["text"][:1].islower():
                    prev["text"] = prev["text"][:-1] + b["text"]
                else:
                    prev["text"] = prev["text"] + " " + b["text"]
                prev["pages"] = sorted(set(prev["pages"] + [b["page"]]))
                prev["bridged"] = True
                continue
        merged.append(dict(b))

    section, segs = "body", []
    for b in merged:
        t = norm_ws(b["text"])
        if not t:
            continue
        typ = classify(b["text"], section)
        if typ == "heading":
            h = _md(t)
            m = SEC_RE.match(h)
            if m:
                w = m.group(1).lower()
                section = "references" if w.startswith(
                    ("reference", "bibliograph", "参考文献")) else w
            elif re.match(r"^\d+\s+[A-Z]", h):
                section = "body"
        if typ == "reference":
            section = "references"
        sid = "S%03d" % (len(segs) + 1)
        loc = "p%s" % ("-".join(str(p) for p in b["pages"])
                       if len(b["pages"]) > 1 else b["page"])
        segs.append({"sid": sid, "locator": "%s:%s" % (loc, sid), "page": b["page"],
                     "pages": b["pages"], "type": typ, "section": section,
                     "text": t, "words": len(t.split()), "chars": len(t),
                     "bridged": b["bridged"], "spans": spans_of(t)})

    idx["segments"] = segs
    idx["stats"] = {"segments": len(segs), "by_type": _counter(s["type"] for s in segs),
                    "words": sum(s["words"] for s in segs),
                    "bridged": sum(1 for s in segs if s["bridged"]),
                    "spans": sum(len(s["spans"]) for s in segs)}
    idx["terms"] = term_candidates(segs) if segs else []
    idx["quality"] = text_quality([p["text"] for p in pages])
    if idx["quality"]["flags"]:
        idx["warnings"].append("text_layer_quality:" + ",".join(idx["quality"]["flags"]))
    return idx


def text_quality(page_texts):
    """文本层质量：可读字符占比 + 词形密度；只作降级标记，不做 OCR（离线、纯标准库）。"""
    txt = " ".join(page_texts)
    if not txt.strip():
        return {"status": "empty", "readable": 0.0, "words": 0, "flags": ["no_text_layer"]}
    good = sum(1 for ch in txt if ch.isalnum() or ch in " .,;:()[]%-/'\n")
    words = len(re.findall(r"[A-Za-z]{2,}|[一-鿿]", txt))
    flags = []
    if good / max(1, len(txt)) < 0.75:
        flags.append("garbled_characters")
    if words < 30:
        flags.append("too_few_words")
    return {"status": "ok" if not flags else "low_quality",
            "readable": round(good / max(1, len(txt)), 3), "words": words, "flags": flags}
