#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patent-search-dossier / registry.py

材料发现与分诊、专利号码规范化、候选提取（号码/族链接/状态行/许可行/技术文献）、
证据逐字（含 OCR 容错）定位、检索面覆盖率、输入指纹。纯标准库、不联网、不依赖 CWD。
"""
import csv
import difflib
import hashlib
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

SKILL_NAME = "patent-search-dossier"
VERSION = "1.0.0"

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")
COUNTRY = frozenset((
    "US WO EP CN JP KR DE GB FR CA AU IN TW RU BR NL SE CH AT IT ES FI DK NO PL IL SG MX ZA HK "
    "EA AP OA VN TH MY ID PH NZ AR CL CO PE SA AE EG MA UA CZ HU RO BG GR PT IE BE LU MC TR IS EE "
    "LV LT SI SK HR RS BA MK AL MD GE AM AZ BY KZ KG TJ TM UZ MN NP LK BD PK KE NG GH TZ UG ZM ZW").split())
KINDCODES = ("A1", "A2", "A3", "A4", "A8", "A9", "B1", "B2", "B3", "B4", "C1", "C2", "U1", "S1", "S2",
             "Y1", "A", "B", "C", "U", "S", "Y", "E", "T", "H", "P")
STATUS_KW = ("granted", "issued", "pending", "expired", "lapsed", "abandoned", "withdrawn", "rejected",
             "revoked", "ceased", "in force", "not in force", "active", "inactive",
             "date of patent", "status", "法律状态", "年费",
             "授权", "公开", "审中", "实审", "撤回", "驳回", "失效", "有效", "期限届满", "终止", "未缴年费")
FAMILY_KW = ("family", "同族", "continuation", "divisional", "cip", "priority claim", "优先权",
             "related application", "成员", "指定国", "分案", "续案")
LICENSE_KW = ("license", "licence", "permission", "许可", "授权范围", "保密", "confidential",
              "terms of use", "terms", "green", "amber", "red", "yellow", "允许展示", "不得展示", "受限")
PAPER_KW = ("doi", "arxiv", "abstract", "et al", "journal", "issn", "vol.", "参考文献", "preprint")
PATENT_KW = ("patent", "专利", "claims", "权利要求", "assignee", "申请人", "inventor", "发明人",
             "ipc", "cpc", "filing date", "申请日", "priority date", "公开号", "pub. no")

CAND_RE = re.compile(r"""
 (?<![A-Za-z0-9])
 (?:
    (?:PCT\s*[/\-]?\s*)?(?:[A-Z]{2}\s*[.\-]?\s*)(?:\d[\d\s,.\-/]{3,20}\d)(?:\s*[A-Z]\d?)?
  | (?:19|20)\d{2}\s*[/\-]\s*\d{5,7}
  | \d{1,2}\s*[/\-]\s*\d{3}\s*[,.]?\s*\d{3}
  | \d{1,3}(?:,\d{3}){2,4}
  | (?:19|20)\d{9}
  | \d{7,8}
 )
 (?![A-Za-z0-9])
""", re.X)

ROLE_KW = {
    "patent_record": PATENT_KW,
    "facsimile_ocr": ("united states patent", "uspto", "kind code", "ocr", "影印", "page 1 of",
                      "sheet", "printed on", "int. cl", "references cited"),
    "family_link": FAMILY_KW,
    "license": LICENSE_KW,
    "paper": PAPER_KW,
}


# ---------------------------------------------------------------- 基础工具
def now():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def norm_ws(s):
    s = str(s or "").replace("\u00ad", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    s = re.sub(r"[\s\u00a0\u3000]+", " ", s)
    return s.strip()


def al(x):
    return x if isinstance(x, list) else []


def dec(raw):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def load_json(path):
    p = Path(path)
    if not p.is_file():
        return None, "not_found"
    err = "unreadable"
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return json.loads(p.read_text(encoding=enc).lstrip("\ufeff")), None
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
    return None, err


def dump(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(t, p)


def paras(text, cap=2400):
    """按空行/编号行切段，返回 [{loc, text}]。"""
    out = []
    buf = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if not s:
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        buf.append(s)
        if len(buf) >= 6:
            out.append(" ".join(buf))
            buf = []
    if buf:
        out.append(" ".join(buf))
    out = [x for x in out if norm_ws(x)]
    if not out:
        t = norm_ws(text)
        out = [t[i:i + cap] for i in range(0, len(t), cap)] if t else []
    return [{"loc": "p%d" % i, "text": t} for i, t in enumerate(out, 1)]


def _pdf_plain(raw):
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        b = m.group(1)
        try:
            b = zlib.decompress(b)
        except Exception:
            pass
        if b"Tj" in b or b"TJ" in b:
            t = " ".join(x.decode("latin-1", "replace")
                         for x in re.findall(rb"\(((?:\\.|[^\\()]){1,500})\)", b))
            if norm_ws(t):
                out.append(t)
    return "\n".join(out)


def pdf_text(p):
    for exe in ("pdftotext", "pdf-text-tool"):
        w = shutil.which(exe)
        if not w:
            continue
        try:
            cmd = [w, str(p)] if exe == "pdf-text-tool" else [w, "-layout", str(p), "-"]
            t = dec(subprocess.run(cmd, capture_output=True, timeout=120).stdout)
            if len(norm_ws(t)) > 200:
                return t, "ext:" + exe
        except Exception:
            pass
    try:
        import fitz  # type: ignore
        t = "\n".join(g.get_text() for g in fitz.open(str(p)))
        if len(norm_ws(t)) > 50:
            return t, "fitz"
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        t = extract_text(str(p))
        if len(norm_ws(t)) > 50:
            return t, "pdfminer"
    except Exception:
        pass
    try:
        return _pdf_plain(Path(p).read_bytes()), "stdlib-crude"
    except Exception:
        return "", "pdf_failed"


def zip_text(p):
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if any(x.startswith("word/") for x in names):
            s = "\n".join(z.read(f).decode("utf-8", "replace") for f in sorted(
                x for x in names if re.match(r"word/(document|header|footer)", x)))
            s = s.replace("<w:tab/>", "\t").replace("</w:p>", "\n")
            s = re.sub(r"<[^>]+>", "", s)
            return re.sub(r"&(amp|lt|gt);", lambda m: {"amp": "&", "lt": "<", "gt": ">"}[m.group(1)], s)
        shared = []
        if "xl/sharedStrings.xml" in names:
            xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            shared = ["".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))
                      for si in re.findall(r"<si>(.*?)</si>", xml, re.S)]
        rows = []
        for f in sorted(x for x in names if x.startswith("xl/worksheets/")):
            xml = z.read(f).decode("utf-8", "replace")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
                vals = []
                for attr, body in re.findall(r"<c\b([^>]*)>(.*?)</c>", row, re.S):
                    v = (re.search(r"<v>(.*?)</v>", body, re.S) or [None, ""])[1]
                    if 't="s"' in attr and str(v).isdigit() and int(v) < len(shared):
                        vals.append(shared[int(v)])
                    else:
                        vals.append(v)
                if any(norm_ws(x) for x in vals):
                    rows.append(" | ".join(vals))
        return "\n".join(rows)


def read_material(p):
    p = Path(p)
    e = p.suffix.lower()
    try:
        raw = p.read_bytes()
        if e == ".pdf" or raw[:4] == b"%PDF":
            t, how = pdf_text(p)
            return "pdf", t, how
        if e in (".docx", ".xlsx", ".xlsm") or raw[:2] == b"PK":
            return e.lstrip(".") or "zip", zip_text(p), "zip-openxml"
        if e in IMAGE_EXT:
            return "image", "", "no_ocr"
        t = dec(raw)
        head = t[:3000]
        if head and sum(c.isprintable() or c in "\n\t" for c in head) > 0.9 * len(head):
            return "text", t, "plain"
        return "binary", "", "unsupported"
    except Exception as x:
        return "error", "", "%s: %s" % (type(x).__name__, x)


def scan(root):
    root = Path(root)
    if not root.exists():
        return []
    return [p for p in sorted(root.rglob("*")) if p.is_file()
            and not p.name.startswith(".") and "__pycache__" not in p.parts]


def find_case(indir):
    """递归定位 case.json，容忍改名与坏 JSON。"""
    indir = Path(indir)
    cands = [indir / "case.json", indir / "input.json", indir / "case" / "case.json"]
    cands += [x for x in scan(indir) if re.match(r"(case|input)[^/]*\.json$", x.name, re.I)]
    bad = None
    for p in cands:
        if not p.is_file():
            continue
        obj, err = load_json(p)
        if isinstance(obj, dict):
            return obj, str(p), None
        bad = "%s: %s" % (p.name, err)
    return {}, None, bad or "未找到 case.json（%s）" % indir


def gk(case, *names, default=None):
    for n in names:
        for k, v in (case or {}).items():
            if str(k).lower() == n.lower() and v not in (None, "", [], {}):
                return v
    return default


# ---------------------------------------------------------------- 号码规范化
def normalize_number(raw):
    """raw → {norm, country, serial, kindcode, doc_type, year, parse_status, rules}。"""
    out = {"raw": str(raw), "norm": None, "country": None, "serial": None, "kindcode": None,
           "year": None, "doc_type": "unknown", "parse_status": "unparsed", "confidence": "low",
           "rules": []}
    if raw is None or str(raw).strip() == "":
        return out
    s = unicodedata.normalize("NFKC", str(raw)).upper()
    body = re.sub(r"[^A-Z0-9/]", "", s)
    if not body:
        return out
    out["rules"].append("strip_separators")
    ccs, pct = None, False
    if body.startswith("PCT"):
        pct = True
        out["rules"].append("pct_prefix")
        body = body[3:].lstrip("/")
        m = re.match(r"([A-Z]{2})", body)
        if m and m.group(1) in COUNTRY:
            out["rules"].append("pct_cc:%s" % m.group(1))
            body = body[2:]
        ccs = "WO"
    if ccs is None:
        m = re.match(r"(PCT|[A-Z]{2})", body)
        if m and (m.group(1) == "PCT" or m.group(1) in COUNTRY):
            ccs = "WO" if m.group(1) == "PCT" else m.group(1)
            body = body[len(m.group(1)):]
            out["rules"].append("cc:%s" % ccs)
    kind = None
    for kc in KINDCODES:
        if body.endswith(kc) and len(body) - len(kc) >= 5:
            kind = kc
            body = body[:-len(kc)]
            out["rules"].append("kind:%s" % kc)
            break
    digits = re.sub(r"[^0-9]", "", body)
    if len(digits) < 5:
        out["parse_status"] = "unparsed"
        if ccs:
            out["country"] = ccs
        return out
    has_slash = "/" in body
    year = None
    doc = "unknown"
    serial = digits
    if ccs == "WO":
        doc = "pct_application" if pct else "pct_publication"
        if len(digits) in (10, 11):
            year, serial = digits[:4], digits[4:]
            out["rules"].append("wo_year_serial")
        else:
            serial = digits
    elif ccs == "US":
        if len(digits) == 11 and 1960 <= int(digits[:4]) <= 2035:
            year, serial = digits[:4], digits[4:]
            doc = "us_publication"
            out["rules"].append("us_pub_year7")
        elif has_slash and len(digits) in (7, 8):
            doc, serial = "us_application", digits[-6:]
            out["rules"].append("us_app_series")
        elif len(digits) in (7, 8):
            doc = "us_grant"
            out["rules"].append("us_grant_7_8")
        elif len(digits) == 6:
            doc = "us_application"
            out["rules"].append("us_app_serial6")
        else:
            doc, serial = "us_document", digits
    elif ccs == "EP":
        doc, serial = "ep_publication", digits
        out["rules"].append("ep_7")
    elif ccs:
        doc, serial = ("national_grant" if (kind or "").startswith("B") else "national_publication"), digits
        out["rules"].append("national_len:%d" % len(digits))
    else:
        if len(digits) == 11 and 1960 <= int(digits[:4]) <= 2035:
            ccs, year, serial, doc = "US", digits[:4], digits[4:], "us_publication"
            out["rules"].append("inferred_country:US")
        elif has_slash and len(digits) in (7, 8):
            ccs, doc = "US", "us_application"
            out["rules"].append("inferred_country:US")
        elif len(digits) in (7, 8):
            ccs, doc = "US", "us_grant"
            out["rules"].append("inferred_country:US")
        else:
            doc, serial = "unknown", digits
            out["rules"].append("no_country_context")
    out.update(country=ccs, serial=serial, kindcode=kind, doc_type=doc, year=year)
    if ccs and serial and doc != "unknown":
        out["norm"] = "%s%s%s" % (ccs, digits, kind or "")
        out["confidence"] = "high" if "inferred_country:US" not in out["rules"] else "medium"
        out["parse_status"] = "parsed" if out["confidence"] == "high" else "ambiguous"
    elif ccs and serial:
        out["norm"] = "%s%s%s" % (ccs, digits, kind or "")
        out["parse_status"] = "ambiguous"
    return out


def extract_candidates(paras_):
    """在一段文本里抽号码候选；返回 [{raw,norm,doc_type,locator,quote,weight}]。"""
    out = []
    for pa in paras_:
        text = pa["text"]
        for m in CAND_RE.finditer(text):
            raw = m.group(0).strip()
            if len(re.sub(r"[^0-9]", "", raw)) < 5:
                continue
            n = normalize_number(raw)
            if n["parse_status"] == "unparsed" or not n["norm"]:
                continue
            lo, hi = max(0, m.start() - 110), min(len(text), m.end() + 110)
            ctx = text[lo:hi].lower()
            weight = sum(1 for kw in ("patent", "专利", "pub", "公开", "appl", "申请", "grant", "授权",
                                      "priority", "优先权", "family", "同族") if kw in ctx)
            out.append({"raw": raw, "norm": n["norm"], "doc_type": n["doc_type"],
                        "kindcode": n["kindcode"], "country": n["country"],
                        "parse_status": n["parse_status"],
                        "locator": pa["loc"], "context": norm_ws(ctx)[:200], "weight": weight})
    return out


def classify_roles(rel, text):
    """多标签材料分诊：角色 → 0–1 得分。"""
    low = (str(rel) + "\n" + str(text)[:20000]).lower()
    scores = {}
    for role, kws in ROLE_KW.items():
        hit = sum(1 for kw in kws if kw.lower() in low)
        if hit:
            scores[role] = round(min(1.0, hit / 3.0), 2)
    name = Path(str(rel)).name.lower()
    if name in ("task.md", "readme.md") or name.startswith("task"):
        return {"task_instruction": 1.0}
    for role, hint in (("license", ("license", "licence", "permit", "terms")),
                       ("family_link", ("family", "related")),
                       ("facsimile_ocr", ("ocr", "facsimile", "scan")),
                       ("paper", ("paper", "abstract", "doi")),
                       ("patent_record", ("patent", "record", "biblio"))):
        if any(h in name for h in hint):
            scores[role] = max(scores.get(role, 0), 0.5)
    return dict(sorted(scores.items(), key=lambda kv: -kv[1]))


def ocr_quality(text):
    t = str(text or "")
    if not t:
        return "empty"
    bad = sum(1 for c in t if c == "\ufffd" or (ord(c) < 32 and c not in "\n\t"))
    ratio = bad / max(1, len(t))
    isolates = len(re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", t))
    if ratio > 0.02 or isolates > 0.15 * max(1, len(t.split())):
        return "noisy"
    return "clean"


def _tier(low):
    if re.search(r"\bred\b|受限|禁止|不得|需登录|付费|confidential|restricted|prohibited", low):
        return "red"
    if re.search(r"\byellow\b|\bamber\b|内部|有限|conditional|internal use", low):
        return "yellow"
    if re.search(r"\bgreen\b|允许|可展示|public|open access|unrestricted|permitted", low):
        return "green"
    return None


def _loc_for(m, line):
    head = norm_ws(line)[:24]
    for pa in m.get("paras", []):
        if head and head in norm_ws(pa["text"]):
            return "%s/%s" % (m["id"], pa["loc"])
    return "%s/p1" % m["id"]


# ---------------------------------------------------------------- 索引
def build_index(indir, skip_path=None, cap=200000):
    indir = Path(indir)
    mats, notes, cands, fam, stat, lic, papers = [], [], [], [], [], [], []
    skip = {str(Path(skip_path).resolve())} if skip_path else set()
    files = [p for p in scan(indir) if str(p.resolve()) not in skip
             and not re.match(r"^(case|input)[^/]*\.json$", p.name, re.I)]
    for i, p in enumerate(files, 1):
        kind, text, how = read_material(p)
        text = str(text or "")[:cap]
        try:
            rel = str(p.relative_to(indir))
        except Exception:
            rel = p.name
        pl = paras(text)
        roles = classify_roles(rel, text)
        blob = " ".join(norm_ws(x["text"]) for x in pl).lower()
        ranges, pos = [], 0
        for x in pl:
            t = norm_ws(x["text"]).lower()
            ranges.append({"loc": x["loc"], "start": pos, "end": pos + len(t)})
            pos += len(t) + 1
        m = {"id": "M%d" % i, "rel": rel, "kind": kind, "chars": len(text), "extract": how,
             "size": p.stat().st_size if p.exists() else 0, "roles": roles,
             "ocr": ocr_quality(text) if kind in ("text", "pdf") else "n/a",
             "text": text, "paras": pl, "blob": blob, "ranges": ranges,
             "sha256": hashlib.sha256(p.read_bytes() if p.exists() else b"").hexdigest()[:16]}
        if kind in ("image", "binary", "error") or not norm_ws(text):
            notes.append({"material": rel, "note": how})
        mats.append(m)
        for c in extract_candidates(pl):
            c["source_id"] = m["id"]
            c["role_rank"] = 2 if "patent_record" in roles else (1 if "facsimile_ocr" in roles else 0)
            cands.append(c)
        roles_k = roles.keys()
        for pa in pl:
            low = pa["text"].lower()
            loc = "%s/%s" % (m["id"], pa["loc"])
            nums = [normalize_number(x)["norm"] for x in
                    re.findall(CAND_RE, pa["text"])]
            nums = [n for n in nums if n]
            if "family_link" in roles_k and len(nums) >= 1 and any(k in low for k in FAMILY_KW):
                fam.append({"source_id": m["id"], "locator": loc, "quote": norm_ws(pa["text"])[:400],
                            "numbers": list(dict.fromkeys(nums))[:6],
                            "link_type_guess": ("continuation" if "continuation" in low or "续案" in low else
                                                "divisional" if "divisional" in low or "分案" in low else
                                                "shared_priority" if ("priority" in low or "优先权" in low) else
                                                "observed")})
            if any(k in low for k in STATUS_KW):
                stat.append({"source_id": m["id"], "locator": loc, "quote": norm_ws(pa["text"])[:400],
                             "status_kw": [k for k in STATUS_KW if k in low][:4],
                             "dates": re.findall(r"\b(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", pa["text"])[:4]})
            if "license" in roles_k:
                tier = _tier(low)
                if tier or any(k in low for k in ("license", "许可", "授权", "permission")):
                    lic.append({"source_id": m["id"], "locator": loc, "tier_guess": tier,
                                "line": norm_ws(pa["text"])[:300], "row": False})
        if "license" in roles_k:
            for line in [x.strip() for x in text.splitlines() if x.strip()]:
                t = _tier(line.lower())
                if (t and ("|" in line or "\t" in line or len(line) < 240)) or line.lower().startswith("|"):
                    lic.append({"source_id": m["id"], "locator": _loc_for(m, line),
                                "tier_guess": t, "line": norm_ws(line)[:300], "row": True})
        if (roles.get("paper") or 0) >= 0.5:
            for pa in pl:
                doi = re.search(r"10\.\d{4,9}/[^\s\"'<>)]+", pa["text"])
                if doi or any(k in pa["text"].lower() for k in ("abstract", "et al", "arxiv")):
                    papers.append({"source_id": m["id"], "locator": "%s/%s" % (m["id"], pa["loc"]),
                                   "doi": doi.group(0).rstrip(".,;") if doi else None,
                                   "line": norm_ws(pa["text"])[:300]})
    uniq = {}
    for c in cands:
        k = c["norm"]
        if k not in uniq or (c.get("role_rank", 0), c["weight"]) > (uniq[k].get("role_rank", 0),
                                                                    uniq[k]["weight"]):
            c = dict(c, occurrences=1)
            if k in uniq:
                c["occurrences"] = uniq[k].get("occurrences", 1) + 1
            uniq[k] = c
        else:
            uniq[k]["occurrences"] = uniq[k].get("occurrences", 1) + 1
    idx = {"skill": SKILL_NAME, "version": VERSION, "input_dir": str(indir), "built_at": now(),
           "materials": mats, "extract_notes": notes, "number_candidates": sorted(
               uniq.values(), key=lambda c: (-c.get("role_rank", 0), -c["weight"], c["norm"])),
           "family_candidates": fam, "status_candidates": stat, "license_candidates": lic,
           "paper_candidates": papers,
           "total_chars": sum(m["chars"] for m in mats),
           "fingerprint": fingerprint(indir)}
    return idx


def fingerprint(indir, skip=None):
    skip = {str(Path(x).resolve()) for x in (skip or [])}
    h = hashlib.sha256()
    files = [p for p in scan(indir) if str(p.resolve()) not in skip
             and not re.match(r"^(case|input)[^/]*\.json$", p.name, re.I)]
    total = 0
    for p in files:
        try:
            b = p.read_bytes()
        except Exception:
            b = b""
        total += len(b)
        h.update(str(p.name).encode("utf-8", "replace"))
        h.update(hashlib.sha256(b).hexdigest().encode())
    return {"files": len(files), "bytes": total, "sha256": h.hexdigest()[:32]}


# ---------------------------------------------------------------- 证据定位
def _grams(s, n=3):
    s = re.sub(r"\s+", "", str(s or "").lower())
    if len(s) <= n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def grams_overlap(q, t):
    g, h = _grams(q), _grams(t)
    if not g or not h:
        return 0.0
    return len(g & h) / float(len(g))


def _loc_at(m, pos):
    for r in m.get("ranges", []):
        if r["start"] <= pos <= r["end"]:
            return r["loc"]
    return None


def find_quote(idx, quote, source_id=None, locator=None):
    """逐字优先、OCR 容错次之；返回命中材料/段落与判定。"""
    q = norm_ws(quote)
    if not q:
        return {"ok": False, "match": "empty", "claimed": locator}
    ql = q.lower()
    mats = [m for m in idx.get("materials", []) if not source_id or m["id"] == source_id]
    if not mats:
        mats = idx.get("materials", [])
    for m in mats:
        pos = (m.get("blob") or "").find(ql)
        if pos >= 0:
            loc = _loc_at(m, pos)
            return {"ok": True, "match": "exact", "source_id": m["id"], "locator": loc,
                    "claimed": locator, "locator_ok": (not locator) or loc == locator}
    best = None
    for m in mats:
        for pa in m.get("paras", []):
            t = norm_ws(pa["text"])
            if not t or len(t) > 6 * max(len(q), 40):
                continue
            r = grams_overlap(q, t)
            if not best or r > best[0]:
                best = (r, m["id"], pa["loc"])
    if best and best[0] >= 0.90:
        return {"ok": True, "match": "ocr_tolerant", "ratio": round(best[0], 3),
                "source_id": best[1], "locator": best[2], "claimed": locator,
                "locator_ok": (not locator) or best[2] == locator}
    return {"ok": False, "match": "miss", "ratio": round(best[0], 3) if best else 0.0,
            "source_id": best[1] if best else None, "locator": best[2] if best else None,
            "claimed": locator}


# ---------------------------------------------------------------- 检索面覆盖
FACETS = [
    ("target_patent", "目标专利定位"),
    ("family", "同族归并"),
    ("status", "法律状态"),
    ("claims", "权利要求/保护范围"),
    ("technical_literature", "技术文献"),
    ("license", "授权与保密边界"),
    ("boundaries", "边界与遗漏声明"),
    ("evidence", "可核验证据链"),
]


def compute_facets(draft, idx, ev_stats=None):
    d = draft or {}
    ev_ok = (ev_stats or {}).get("ok", 0)
    ev_total = (ev_stats or {}).get("total", 0)
    checks = {
        "target_patent": (len(al(d.get("patent_objects"))), 1,
                          "patent_objects 至少 1 件且号码可定位"),
        "family": (len(al(d.get("family_edges"))), 1, "family_edges 至少 1 条带证据定位"),
        "status": (len([s for s in al(d.get("status_entries")) if s.get("value")]), 1,
                   "status_entries 三字段齐全"),
        "claims": (len([c for c in al(d.get("claims_versions")) if norm_ws(c.get("quote"))]), 1,
                   "claims_versions 有逐字摘录"),
        "technical_literature": (len(al(d.get("technical_papers"))),
                                 1 if any("paper" in (m.get("roles") or {}) for m in idx.get("materials", [])) else 0,
                                 "technical_papers（材料含文献角色时必须非空）"),
        "license": (len(al(d.get("license_decisions"))), 1, "license_decisions 至少 1 条"),
        "boundaries": (len(al(d.get("boundaries"))), 3, "boundaries 至少 3 类/3 条"),
        "evidence": (ev_ok, max(1, ev_total), "证据逐字/容错命中数"),
    }
    cov, hits = {}, 0
    for key, label in FACETS:
        got, need, how = checks[key]
        ok = got >= need if need else True
        cov[key] = {"label": label, "present": bool(ok), "got": got, "need": need, "rule": how}
        hits += 1 if ok else 0
    cov["_summary"] = {"facets_hit": hits, "facets_total": len(FACETS),
                       "percent": round(100.0 * hits / len(FACETS), 1)}
    return cov


# ---------------------------------------------------------------- 文件名/来源
def source_rows(idx):
    return [{"id": m["id"], "file": m["rel"], "kind": m["kind"], "chars": m["chars"],
             "extraction": m["extract"], "roles": list((m.get("roles") or {}).keys()),
             "ocr": m.get("ocr"), "sha256": m.get("sha256")} for m in idx.get("materials", [])]


def csv_rows(path):
    """读 CSV 许可表（若材料本身就是 csv 且未被文本解析覆盖）。"""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [dict(r) for r in csv.DictReader(f)]
    except Exception:
        return []
