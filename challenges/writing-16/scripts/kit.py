#!/usr/bin/env python3
"""kit.py -- material parsing, paragraph indexing, fact-candidate extraction.

Standard library only. No network. Import-safe: no work is done at import time.
Used by main.py; can also be inspected standalone:
    python3 scripts/kit.py --help
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path

sys.dont_write_bytecode = True

U = ("%|‰|mg|kg|μg|µg|ng|pg|g|mL|ml|μL|µL|uL|L|nM|µM|μM|uM|mM|pM|mol|mmol|μmol|nm|µm|μm|um|"
     "mm|cm|km|kDa|Da|bp|kb|°C|℃|K|kPa|MPa|Pa|GPa|Hz|kHz|MHz|GHz|V|mV|mA|A|W|kW|J|kJ|"
     "kcal|cal|rpm|h|hr|hrs|min|s|ms|d|wk|yr|fold|×|倍|例|名|人|份|次|天|小时|分钟|秒|年|月|日|个|项|组|家|款")
PAIR = re.compile(r"(?<![A-Za-z0-9.])(\d[\d,]*(?:\.\d+)?)\s*(" + U + r")(?![A-Za-z])")
ANY = re.compile(r"(?<![A-Za-z0-9.])(\d[\d,]*(?:\.\d+)?)(?![A-Za-z])")
LOC = re.compile(r"M\d+:P\d+")
ACRO = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Za-z]{0,10}[A-Z][A-Za-z0-9\-]{0,12})(?![A-Za-z0-9])")
FIG = re.compile(r"(?:图|表|Fig(?:ure)?\.?|Tab(?:le)?\.?)\s*(\d+[A-Za-z]?)", re.I)
CITE = re.compile(r"\[\d{1,3}(?:[,\-–]\d{1,3})*\]|\([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?,?\s*(?:19|20)\d\d[a-z]?\)")
SAMPLE = re.compile(r"(?<![A-Za-z])n\s*=\s*\d+", re.I)
HEDGE = ("初步", "提示", "可能", "尚需", "尚待", "有待", "潜在", "推测", "倾向于", "有限", "局限",
         "不确定", "未验证", "尚未", "仍需", "尚不能", "体外", "临床前", "小样本", "趋势", "相关", "关联",
         "preliminary", "suggest", "may ", "might", "could", "potential", "limitation",
         "unclear", "trend", "associat", "correlat", "in vitro", "preclinical")
CAUSAL = ("证明", "证实", "导致", "引起", "使得", "造成", "必然", "彻底", "治愈", "根除", "完全恢复",
          "prove", "confirm", "cause", "lead to", "demonstrat", "eliminat", "cure")
CLAIM = ("结论", "因此", "表明", "显示", "说明", "可见", "综上", "本研究", "总之",
         "conclusion", "therefore", "we show", "we find", "demonstrat", "indicat", "suggest that", "overall")
STOP_ACRO = {"PDF", "DOI", "URL", "JSON", "CSV", "XML", "HTML", "DOCX", "PPTX", "XLSX", "FIG", "TAB",
             "AND", "THE", "FOR", "WITH", "FROM", "NOT", "ALL", "ANY", "OK", "NA", "VS", "ET", "AL",
             "II", "III", "IV", "ID", "NOTE", "TBD", "TODO", "N/A", "MD", "TXT", "MS", "SD", "SE",
             "CI", "OR", "HR", "RR", "USA", "EU", "UK", "AI"}

AUD = (("非专业公众", r"公众|大众|科普|普通读者|非专业|媒体|记者|外行|public|lay\s*(?:audience|reader)|general\s*audience|popular"),
       ("产业界/投资方", r"产业界|企业|公司|工业|投资|商业化|合作方|技术转移|落地|industry|investor|business|commercial|partner"),
       ("基金/项目评审", r"基金|资助|评审|申报|立项|课题|funder|grant|panel|review\s*panel|proposal\s*reviewer"),
       ("政策/管理部门", r"政策|监管|政府|决策|管理部门|policy|regulator|government|decision\s*maker"),
       ("同行专家", r"同行|领域专家|审稿人|专业读者|peers?|specialist|expert\s*reader|referee"))
GEN = (("科普文章", r"科普|大众文章|新闻稿|通稿|公众号|博客|popular[\s-]*science|press\s*release|blog"),
       ("技术转化简报", r"简报|白皮书|一页纸|技术转化|投资说明|brief(?:ing)?|whitepaper|one[\s-]*pager|tech\s*transfer"),
       ("项目申报摘要", r"申报|立项|提案|申请书|proposal|application\s*summary|grant\s*summary"),
       ("政策简报", r"政策简报|政策建议|policy\s*brief|policy\s*note"),
       ("论文摘要", r"论文摘要|期刊摘要|abstract|structured\s*abstract"),
       ("双语发布稿", r"双语|中英|bilingual|中文和英文|two\s*languages"))


def dec(b):
    for e in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def normalize(s, loose=False):
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    if loose:
        s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u3000", " ").replace("\u00a0", " ").replace("\u200b", "")
    s = re.sub(r"\s+", "", s)
    return s.casefold() if loose else s


def words(t):
    t = t or ""
    return len(re.findall(r"[\u3400-\u9fff]", t)) + len(re.findall(r"[A-Za-z][A-Za-z0-9\-']*", t))


def canon(v):
    s = str(v).replace(",", "").strip()
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f == int(f) and abs(f) < 1e15 else "%.10g" % f


def numbers_of(t):
    """-> (bare values set, value+unit pairs set)"""
    t = LOC.sub(" ", t or "")
    vals, pairs = set(), set()
    for m in PAIR.finditer(t):
        v, u = canon(m.group(1)), m.group(2).replace("μ", "u").replace("µ", "u")
        vals.add(v)
        pairs.add(v + u)
    for m in ANY.finditer(t):
        vals.add(canon(m.group(1)))
    return vals, pairs


def acronyms_of(t):
    return {m.group(1) for m in ACRO.finditer(t or "")
            if 1 < len(m.group(1)) <= 14 and m.group(1).upper() not in STOP_ACRO
            and sum(c.isupper() for c in m.group(1)) >= 2}


def figrefs_of(t):
    return {"%s%s" % (re.sub(r"[.\s]", "", m.group(0)[:2]).lower()[:1], m.group(1)) if False else
            re.sub(r"\s", "", m.group(0)) for m in FIG.finditer(t or "")}


def hedges_of(t):
    low = (t or "").lower()
    return {h for h in HEDGE if h.lower() in low}


def causal_of(t):
    low = (t or "").lower()
    return {c for c in CAUSAL if c.lower() in low}


# ---------------------------------------------------------------- extraction
def pdf_text(p):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"],
                               capture_output=True, timeout=90)
            if r.returncode == 0 and len(r.stdout.strip()) > 40:
                return dec(r.stdout), "pdftotext"
        except Exception:
            pass
    try:
        data = p.read_bytes()
    except Exception:
        return "", "unreadable"
    parts = []
    for m in re.finditer(rb"stream\r?\n", data):
        e = data.find(b"endstream", m.end())
        if e <= 0:
            continue
        b = data[m.end():e]
        try:
            b = zlib.decompress(b)
        except Exception:
            pass
        if b"Tj" in b or b"TJ" in b:
            parts.append(" ".join(x.decode("latin-1") for x in re.findall(rb"\(([^()\\]{2,})\)", b)))
        elif b"BT" in b and b"ET" in b:
            parts.append(" ".join(x.decode("latin-1") for x in re.findall(rb"\(([^()\\]{2,})\)", b)))
    t = re.sub(r"[ \t]{2,}", " ", "\n".join(parts)).strip()
    solid = len(re.sub(r"\s", "", t))
    return t, ("builtin-pdf" if solid > 200 else "builtin-pdf-lowconf")


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        x = z.read("word/document.xml").decode("utf-8", "replace")
    x = re.sub(r"</w:p>", "\n\n", re.sub(r"<w:(tab|br)[^>]*/>", "\t", x))
    return html.unescape(re.sub(r"<[^>]+>", "", x))


def xlsx_text(p):
    out = []
    with zipfile.ZipFile(p) as z:
        sh = []
        if "xl/sharedStrings.xml" in z.namelist():
            blob = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            sh = [html.unescape(re.sub(r"<[^>]+>", "", si))
                  for si in re.findall(r"<si>(.*?)</si>", blob, re.S)]
        for n in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
            body = z.read(n).decode("utf-8", "replace")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", body, re.S):
                cells = []
                for c in re.findall(r"<c[^>]*?(?:/>|>.*?</c>)", row, re.S):
                    v = re.search(r"<v>(.*?)</v>", c, re.S)
                    ty = re.search(r't="(\w+)"', c)
                    val = v.group(1) if v else ""
                    if val.isdigit() and ty and ty.group(1) == "s" and int(val) < len(sh):
                        val = sh[int(val)]
                    cells.append(val)
                out.append("\t".join(cells))
    return "\n".join(r for r in out if r.strip())


def kind_of(p):
    e = p.suffix.lower().lstrip(".")
    try:
        head = p.open("rb").read(8)
    except Exception:
        head = b""
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return e if e in ("docx", "xlsx", "pptx") else "zip"
    if head[:3] == b"\xff\xd8\xff" or head[:4] == b"\x89PNG" or head[:4] == b"GIF8":
        return "image"
    return {"md": "text", "markdown": "text", "txt": "text", "csv": "text", "tsv": "text",
            "json": "json", "tex": "text", "html": "text", "htm": "text", "xml": "text",
            "yaml": "text", "yml": "text", "bib": "text", "rtf": "text"}.get(e, e or "unknown")


def extract(p):
    """-> (text, method). Never raises."""
    k = kind_of(p)
    try:
        if k == "pdf":
            return pdf_text(p)
        if k == "docx":
            return docx_text(p), "docx-xml"
        if k == "xlsx":
            return xlsx_text(p), "xlsx-xml"
        if k == "json":
            o = json.loads(dec(p.read_bytes()))
            flat = "\n".join(x.strip() for x in re.findall(r'"([^"]{4,})"', json.dumps(o, ensure_ascii=False)))
            return flat, "json-leaves"
        if k == "image":
            return "", "image-no-ocr"
        if k in ("pptx", "zip"):
            return "", "unsupported:" + k
        t = dec(p.read_bytes())
        head = t[:2000]
        if head and sum(c.isprintable() or c in "\n\t " for c in head) / len(head) < .85:
            return "", "binary-skip"
        return t, ("text" if k in ("text", "csv") else "raw-bytes")
    except Exception as e:
        return "", "failed:%s" % type(e).__name__


def split_paras(t):
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for block in [x.strip() for x in re.split(r"\n\s*\n", t) if x.strip()]:
        pieces = ([x.strip() for x in re.split(r"\n(?=\S)", block) if x.strip()]
                  if len(block) > 1400 else [block])
        for s in pieces:
            if len(s) <= 1400:
                out.append(s)
                continue
            cur = ""
            for piece in re.split(r"(?<=[。！？；.!?])\s*", s):
                cur += piece
                if len(cur) >= 700:
                    out.append(cur.strip())
                    cur = ""
            if cur.strip():
                out.append(cur.strip())
    return [re.sub(r"[ \t]+", " ", x) for x in out]


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def scan(inp):
    """Recursively read /input. -> (case, case_path, materials, degradations, instruction)"""
    mats, degr = [], []
    inp = Path(inp)
    files = []
    if inp.exists():
        files = [p for p in sorted(inp.rglob("*"))
                 if p.is_file() and not p.name.startswith(".") and "__pycache__" not in p.parts]
    case = cpath = None
    if (inp / "case.json").is_file():
        try:
            case, cpath = read_json(inp / "case.json"), inp / "case.json"
        except Exception as e:
            degr.append("case.json 解析失败（%s），转入递归查找" % type(e).__name__)
    if not isinstance(case, dict) or not case:
        for p in files:
            if p.suffix.lower() != ".json":
                continue
            try:
                o = read_json(p)
            except Exception:
                continue
            if isinstance(o, dict) and ("output_contract" in o or "case_id" in o):
                case, cpath = o, p
                degr.append("case.json 不可用，改用 %s" % p.name)
                break
    instr = ""
    for cand in (inp / "task.md", inp / "TASK.md", inp / "task.txt"):
        if cand.is_file():
            try:
                instr = dec(cand.read_bytes())
            except Exception:
                instr = ""
            break
    for p in files:
        if cpath and p == cpath:
            continue
        if p.name.lower() == "case.json":
            continue
        text, how = extract(p)
        is_instr = bool(re.match(r"task.*\.(md|txt)$", p.name, re.I))
        if is_instr and text:
            instr = instr or text
        try:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except Exception:
            sha = ""
        mats.append({"name": p.name, "path": str(p), "kind": kind_of(p), "method": how,
                     "text": text, "chars": len(text), "sha256": sha,
                     "role": "instruction" if is_instr else "material"})
        if how.startswith("failed") or how in ("unreadable", "binary-skip"):
            degr.append("%s 解析失败（%s），未入索引" % (p.name, how))
        elif how == "image-no-ocr":
            degr.append("%s 是图片，未做 OCR；如需图注请人工补充文本" % p.name)
        elif how.startswith("unsupported"):
            degr.append("%s 类型暂不支持（%s），未入索引" % (p.name, how))
        elif how.startswith("builtin-pdf"):
            degr.append("%s 使用内置 PDF 解析（无 pdftotext），多栏可能错序" % p.name)
        elif how == "raw-bytes":
            degr.append("%s 按原始字节读取，结构信息可能丢失" % p.name)
    return (case if isinstance(case, dict) else {}), cpath, mats, degr, instr


# ---------------------------------------------------------------- work order
def flat_keys(o, out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            out.setdefault(str(k).lower(), v)
            flat_keys(v, out)
    elif isinstance(o, list):
        for v in o:
            flat_keys(v, out)
    return out


def pick(f, *names):
    for n in names:
        v = f.get(n.lower())
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
        if isinstance(v, dict):
            for k in ("label", "name", "value", "text", "target", "type"):
                if isinstance(v.get(k), str) and v[k].strip():
                    return v[k].strip()
        if isinstance(v, list) and v and isinstance(v[0], str):
            return "; ".join(v)[:300]
    return None


def workorder(case, instr):
    f = flat_keys(case or {})
    text = "%s\n%s" % (instr or "", pick(f, "task_instruction", "instruction", "task", "prompt") or "")
    wo = {"audience": pick(f, "audience", "target_audience", "readers", "reader", "受众", "target_reader"),
          "genre": pick(f, "genre", "format", "text_type", "文体", "体裁", "output_format"),
          "length": pick(f, "length", "word_limit", "max_words", "word_count", "max_length", "limit",
                         "篇幅", "字数", "word_budget"),
          "bilingual": pick(f, "language", "lang", "bilingual", "语言", "双语"),
          "instruction": pick(f, "task_instruction", "instruction", "task", "prompt") or (instr or "")[:1500],
          "workorder": pick(f, "organizer_workorder", "organizer_edit_workorder", "workorder", "requirements"),
          "basis": {}}
    for key, rules in (("audience", AUD), ("genre", GEN)):
        if wo[key]:
            continue
        for label, pat in rules:
            m = re.search(pat, text, re.I)
            if m:
                wo[key], wo["basis"][key] = label, m.group(0)
                break
    if not wo["length"]:
        m = re.search(r"(?:不超过|不多于|上限|控制在|约)\s*(\d{2,5})\s*(?:字|词|words?|chars?)", text, re.I) \
            or re.search(r"(\d{2,5})\s*(?:字|词|words?|chars?)\s*(?:以内|以下|左右|上限)", text, re.I) \
            or re.search(r"(\d{2,5})\s*(?:字|词|words?|chars?)", text, re.I)
        if m:
            wo["length"], wo["basis"]["length"] = m.group(1) + " 字", m.group(0)
    if not wo["bilingual"]:
        m = re.search(r"双语|中英|bilingual|in\s+Chinese\s+and\s+English", text, re.I)
        if m:
            wo["bilingual"] = m.group(0)
    return wo


# ---------------------------------------------------------------- candidates
def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。！？!?])\s*|\n+", text or "") if len(s.strip()) >= 8]


def candidates(idx, cap=48):
    """Deterministic must-retain candidates extracted from material paragraphs."""
    out, seen = [], set()

    def add(kind, value, loc, quote):
        key = (kind, value, loc)
        if key in seen or len(out) >= cap:
            return
        seen.add(key)
        out.append({"kind": kind, "value": value, "locator": loc,
                    "quote": re.sub(r"\s+", " ", quote or "")[:180]})

    def snip(t, m=None, w=40):
        seg = t if m is None else t[max(0, m.start() - w):m.end() + w]
        ss = sentences(seg) or sentences(t)
        return (ss[0] if ss else seg)[:180]

    paras = [p for p in idx.get("paragraphs", []) if p.get("role") != "instruction"]
    for p in paras:
        t, loc = p.get("text") or "", p.get("loc")
        for m in PAIR.finditer(t):
            add("number", canon(m.group(1)) + m.group(2), loc, snip(t, m))
        for m in SAMPLE.finditer(t):
            add("sample", re.sub(r"\s", "", m.group(0)), loc, snip(t, m))
        for f in sorted(figrefs_of(t))[:3]:
            add("figure", f, loc, snip(t))
        for c in sorted(set(CITE.findall(t)))[:2]:
            add("citation", c, loc, snip(t))
    for p in paras:
        t = (p.get("text") or "").strip()
        if len(t) < 30 or t.startswith("#") or t.startswith("**"):
            continue
        if any(h.lower() in t.lower() for h in ("局限", "限制", "尚需", "有待", "不足",
                                                "limitation", "caveat")):
            q = snip(t)
            add("limitation", q[:24], p.get("loc"), q)
    for p in paras:
        t = (p.get("text") or "").strip()
        if len(t) < 30 or t.startswith("#") or t.startswith("**"):
            continue
        hit = [s for s in sentences(t) if any(c.lower() in s.lower() for c in CLAIM)]
        if hit:
            add("conclusion", hit[0][:24], p.get("loc"), hit[0][:180])
    return out


def build_index(case, cpath, mats, instr):
    paras, ms = [], []
    for i, m in enumerate(mats, 1):
        mid = "M%d" % i
        pp = split_paras(m["text"])
        row = {k: m[k] for k in ("name", "path", "kind", "method", "role", "chars")}
        row.update({"id": mid, "paragraphs": len(pp), "sha256_16": m["sha256"]})
        ms.append(row)
        paras += [{"loc": "%s:P%d" % (mid, j), "mat": mid, "text": t,
                   "role": m["role"], "chars": len(t)} for j, t in enumerate(pp, 1)]
    body = "\n".join(p["text"] for p in paras if p["role"] != "instruction")
    allt = "\n".join(p["text"] for p in paras)
    vals, pairs = numbers_of(body)
    idx = {"case_id": (case or {}).get("case_id") or (case or {}).get("id") or "UNKNOWN-CASE",
           "output_contract": (case or {}).get("output_contract") or {},
           "task_instruction": (case or {}).get("task_instruction") or (case or {}).get("instruction") or "",
           "case_path": str(cpath) if cpath else None,
           "workorder": workorder(case, instr),
           "materials": ms, "paragraphs": paras,
           "norm_exact": normalize(allt), "norm_loose": normalize(allt, True),
           "numbers": sorted(vals), "pairs": sorted(pairs),
           "acronyms": sorted(acronyms_of(body))[:60],
           "figures": sorted(figrefs_of(body))[:40],
           "citations": sorted({c for c in CITE.findall(body)})[:40],
           "hedges": sorted(hedges_of(body)),
           "causal": sorted(causal_of(body))}
    idx["candidates"] = candidates(idx)
    idx["key_pairs"] = [p for p in idx["pairs"]
                        if re.search(r"[%‰]|mg|kg|mL|mol|nM|mM|μM|µM|uM|h|min|d|kDa|fold|倍", p)][:60]
    return idx


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit.py", description="材料解析/切段/候选保留项抽取（供 main.py 调用）")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        case, cpath, mats, degr, instr = scan(a.input)
        idx = build_index(case, cpath, mats, instr)
        if a.json:
            print(json.dumps({"materials": idx["materials"], "paragraphs": len(idx["paragraphs"]),
                              "candidates": idx["candidates"], "degradations": degr},
                             ensure_ascii=False, indent=2)[:8000])
        else:
            print("材料 %d 份 / 段落 %d / 候选保留项 %d / 降级 %d"
                  % (len(idx["materials"]), len(idx["paragraphs"]), len(idx["candidates"]), len(degr)))
            for m in idx["materials"]:
                print("  %-3s %-26s %-6s %-18s %5d字 %3d段 [%s]"
                      % (m["id"], m["name"][:26], m["kind"], m["method"], m["chars"],
                         m["paragraphs"], m["role"]))
            for d in degr:
                print("  ! " + d)
    except Exception as e:
        print("kit 自检异常（不影响主流程）：%s: %s" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
