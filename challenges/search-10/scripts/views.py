#!/usr/bin/env python3
"""views.py - 双形态 views 发现 / 指纹 / 语种与版本标注 / 去重计数。

形态 A：一 view 一文件（可带 YAML 式 front matter），或 works/<work_id>/<lang>-<version>.md
形态 B：单 JSON 汇总（views.json / works.json；支持 works[].views[] 嵌套与 text|body|content 键名变体）
纯标准库、不联网；所有函数对畸形输入返回空值而非抛异常。
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".text", ".htm", ".html"}
JSON_EXT = {".json", ".jsonl", ".ndjson"}
BIB_EXT = {".bib", ".ris", ".csv", ".xml", ".tsv"}
BIN_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif",
           ".docx", ".xlsx", ".pptx", ".zip", ".gz", ".pyc"}
CASE_NAMES = {"case.json", "case_input.json", "input.json", "challenge.json"}

TEXT_KEYS = ("text", "body", "content", "plain_text", "fulltext", "full_text", "raw_text",
             "markdown", "article_text", "body_text", "content_text")
ABS_KEYS = ("abstract", "resumo", "summary", "abstract_text")
ID_KEYS = ("view_id", "doc_id", "record_id", "item_id", "id", "key", "slug")
WORK_KEYS = ("work_id", "work", "work_key", "group_id", "family_id", "record_group",
             "study_id", "item_group")
LANG_KEYS = ("language", "lang", "language_code", "language_of_text", "body_language",
             "doc_language", "lingua", "idioma")
VER_KEYS = ("version", "version_type", "view_type", "kind", "variant", "doc_type",
            "content_type", "representation")
TITLE_KEYS = ("title", "titulo", "article_title", "headline", "article_title_text")
DOI_KEYS = ("doi", "DOI", "digital_object_identifier", "identifier", "Identifier")

MARKERS = {
    "en": "the of and to in is that for with as on by are was were this from our which not "
          "has have been their between these findings data study results we they".split(),
    "pt": "de da do que os as um uma para com nao em dos das por mais como tambem entre sobre "
          "foram foi ser seu sua pelo pela nas nos ao se nao dos".split(),
    "es": "el la los las del que y en un una para con no es por mas como se su sus al fue "
          "fueron entre sobre estos datos resultados estudio".split(),
    "de": "der die das und den von mit ist im zu sich des auf fur nicht werden wird auch bei "
          "aus dem ein eine als diese".split(),
    "fr": "les des et est dans pour que qui aux sur avec pas plus par sont au du une le ce "
          "cette ces nous".split(),
    "it": "il lo la gli le di che e per con non sono una del della nel piu anche questo "
          "questa degli".split(),
}
SHARED = {}
for _lg, _ms in MARKERS.items():
    for _m in _ms:
        SHARED[_m] = SHARED.get(_m, 0) + 1

VER_PATTERNS = [
    ("publisher_translation", [r"tradu[cç][aã]o\s+(oficial|autorizada|integral|completa)",
                               r"vers[aã]o\s+traduzida", r"traduzido\s+por", r"translated\s+by",
                               r"official\s+translation", r"full\s+translation",
                               r"traducci[oó]n\s+(oficial|autorizada)",
                               r"traduction\s+officielle", r"autorisierte\s+[uü]bersetzung"]),
    ("abstract_only", [r"abstract[\s-]*only", r"only\s+the\s+abstract", r"somente\s+(o\s+)?resumo",
                       r"apenas\s+(o\s+)?resumo", r"resumo\s+apenas",
                       r"full\s+text\s+not\s+available", r"texto\s+completo\s+n[aã]o\s+dispon[ií]vel"]),
    ("duplicate", [r"\bduplicate\s+(copy|record|of)\b", r"\bc[oó]pia\s+(exata|do)\b",
                   r"\breprint\b", r"reimpress[aã]o", r"\bduplicado\b",
                   r"identical\s+to\s+the", r"same\s+content\s+as"]),
    ("preprint", [r"\bpreprint\b", r"manuscript\s+draft"]),
    ("erratum", [r"\berratum\b", r"corrigendum", r"\berrata\b"]),
    ("original", [r"original\s+(version|article|research|paper|manuscript)",
                  r"vers[aã]o\s+original", r"artigo\s+original", r"publicado\s+originalmente"]),
]
FILE_VERSION = [("publisher_translation", ("translation", "translated", "trans", "trad", "tradutor")),
                ("abstract_only", ("abstract", "resumo", "abs", "summary")),
                ("duplicate", ("duplicate", "dup", "copy", "copia", "reprint")),
                ("original", ("original", "orig", "body", "full"))]
LANG_TOKENS = {"pt": ("pt", "por", "port", "portuguese", "portugues", "ptbr", "pt-br"),
               "en": ("en", "eng", "english", "ingles"),
               "es": ("es", "spa", "spanish", "espanol", "castellano"),
               "de": ("de", "deu", "ger", "german", "deutsch"),
               "fr": ("fr", "fra", "fre", "french", "francais"),
               "zh": ("zh", "zho", "chi", "chinese", "cn"),
               "ja": ("ja", "jpn", "japanese"),
               "it": ("it", "ita", "italian", "italiano")}
HEAD_RE = re.compile(
    r"(?im)^[\s>#*\-]{0,6}(?:\d+[.)]?\s*)?(abstract|resumo|introduction|introdu[cç][aã]o|"
    r"introducci[oó]n|methods?|m[eé]todos?|material and methods|results?|resultados?|"
    r"discussion|discuss[aã]o|conclusions?|conclus[oõ]es|references?|refer[eê]ncias|"
    r"background|objectives?|objetivos?|participants|data analysis)\b")


# ---------------------------------------------------------------- text helpers
def read_text(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def low(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def sha(s):
    return hashlib.sha256(norm(low(s)).encode("utf-8")).hexdigest()


def wc(s):
    return len(re.findall(r"\S+", s or ""))


def first_str(d, keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for kk in ("name", "value", "text", "title"):
                if isinstance(v.get(kk), str) and v[kk].strip():
                    return v[kk].strip()
    return None


def doi_of(text):
    m = re.search(r"10\.\d{4,9}/[^\s\"'<>,;)\]]{3,80}", text or "")
    return m.group(0).rstrip(".,;") if m else None


# ---------------------------------------------------------------- language
def detect_lang(text, declared=None):
    raw = text or ""
    cjk = sum(1 for c in raw if "\u3040" <= c <= "\u9fff")
    kana = sum(1 for c in raw if "\u3040" <= c <= "\u30ff")
    hang = sum(1 for c in raw if "\uac00" <= c <= "\ud7af")
    letters = sum(1 for c in raw if c.isalpha())
    t = " " + low(raw) + " "
    toks = re.findall(r"[a-z']{2,}", t)
    total = max(1, len(toks))
    cnt = {}
    for w in toks:
        cnt[w] = cnt.get(w, 0) + 1
    scores, evid = {}, {}
    for lg, ms in MARKERS.items():
        sc = 0.0
        hits = []
        for m in ms:
            c = cnt.get(m, 0)
            if not c:
                continue
            wgt = 1.0 if SHARED.get(m, 0) <= 1 else 0.4
            sc += c * wgt
            hits.append((m, c, wgt))
        scores[lg] = round(sc / total, 4)
        evid[lg] = sorted(hits, key=lambda x: -x[1])[:6]
    best = max(scores, key=lambda k: scores[k]) if scores else "und"
    srt = sorted(scores.values(), reverse=True)
    second = srt[1] if len(srt) > 1 else 0.0
    if letters and (cjk + hang) / max(1, letters) > 0.15:
        best = "ja" if kana > 0.05 * max(1, cjk) else ("ko" if hang > cjk else "zh")
        conf = "high"
        scores[best] = 1.0
    elif scores.get(best, 0) >= 0.055 and (second == 0 or scores[best] >= 1.6 * second):
        conf = "high"
    elif scores.get(best, 0) >= 0.028:
        conf = "medium"
    else:
        conf = "low"
    return {"detected": best, "confidence": conf, "scores": scores,
            "evidence": [{"lang": best, "markers": [{"token": m, "count": c, "weight": w}
                                                    for m, c, w in evid.get(best, [])]}],
            "declared": declared, "tokens": len(toks)}


def lang_from_token(name):
    toks = re.split(r"[^a-z]+", low(name))
    for lg, variants in LANG_TOKENS.items():
        for v in variants:
            if v in toks:
                return lg
    return None


# ---------------------------------------------------------------- version / type
def version_signals(text, filename=""):
    t = low(text or "")
    hits = []
    for ver, pats in VER_PATTERNS:
        for p in pats:
            m = re.search(p, t)
            if m:
                hits.append({"version": ver, "pattern": p,
                             "quote": _raw_span(text, p)})
                break
    fn = re.split(r"[^a-z]+", low(filename or ""))
    for ver, toks in FILE_VERSION:
        for tk in toks:
            if tk in fn:
                hits.append({"version": ver, "pattern": "filename:" + tk, "quote": filename})
                break
    return hits


def _raw_span(text, pat):
    try:
        m = re.search(pat, low(text or ""))
        if not m:
            return None
        return norm((text or "")[max(0, m.start() - 20):m.end() + 40])[:160]
    except re.error:
        return None


def sections_of(text):
    return sorted({m.group(1).lower() for m in HEAD_RE.finditer(text or "")})


def classify_doc(text, has_abs_only_flag=False):
    words = wc(text)
    secs = sections_of(text)
    body_heads = [s for s in secs if s not in ("abstract", "resumo", "references", "referencias",
                                               "referências")]
    if len(body_heads) >= 2 or words >= 350:
        return "full_body", words, secs
    if has_abs_only_flag or "abstract" in [low(x) for x in secs] or "resumo" in [low(x) for x in secs]:
        return "abstract_only", words, secs
    return "unstructured", words, secs


# ---------------------------------------------------------------- view builders
def base_view(key_form, locator, text, meta):
    declared_lang = meta.get("language")
    det = detect_lang(text, declared_lang)
    vhits = version_signals(text, meta.get("file", "") or meta.get("view_id", ""))
    abs_flag = any(h["version"] == "abstract_only" for h in vhits)
    dtype, words, secs = classify_doc(text, abs_flag)
    dup_flag = [h for h in vhits if h["version"] == "duplicate"]
    ver = meta.get("version") or (vhits[0]["version"] if vhits else
                                  ("original" if dtype == "full_body" else "undetermined"))
    if dtype == "abstract_only" and not meta.get("version"):
        ver = "abstract_only"
    if dup_flag:
        ver = "duplicate"
    lang_declared = low(declared_lang)[:5] if declared_lang else None
    if lang_declared:
        for lg, variants in LANG_TOKENS.items():
            if lang_declared in variants or lg == lang_declared:
                lang_declared = lg
                break
    lang = lang_declared or det["detected"]
    basis = ("declared_metadata" if lang_declared else "text_detection")
    if lang_declared and det["detected"] != "und" and det["detected"] != lang_declared:
        basis = "declared_metadata(detected=%s,conflict)" % det["detected"]
    v = {
        "view_id": meta.get("view_id") or "",
        "work_id": meta.get("work_id") or "",
        "doi": meta.get("doi") or doi_of(text),
        "title": meta.get("title") or "",
        "language": lang,
        "language_basis": basis,
        "language_declared": lang_declared,
        "language_detected": det["detected"],
        "lang_confidence": det["confidence"],
        "lang_evidence": det["evidence"],
        "lang_scores": det["scores"],
        "version": ver,
        "version_basis": [{"version": h["version"], "pattern": h["pattern"],
                           "quote": h["quote"]} for h in vhits][:4],
        "doc_type": dtype,
        "sha256": sha(text),
        "chars": len(text or ""),
        "words": words,
        "sections": secs,
        "duplicate_of": None,
        "duplicate_kind": None,
        "locator": locator,
        "key_form": key_form,
        "source_path": meta.get("file") or meta.get("source_file") or "",
        "text": text or "",
    }
    if not v["title"]:
        v["title"] = guess_title(text)
    return v


def guess_title(text):
    for line in (text or "").splitlines():
        s = line.strip().lstrip("#").strip("* ").strip()
        if len(s) >= 12 and not s.lower().startswith(("---", "title:", "doi:", "language:")):
            return s[:220]
    return ""


def front_matter(text):
    m = re.match(r"\s*---\s*\n(.*?)\n\s*---\s*\n", text or "", re.S)
    out = {}
    if not m:
        return out, text
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, val = line.partition(":")
            k = k.strip().lower()
            val = val.strip().strip('"').strip("'")
            if k and val:
                out[k] = val
    return out, (text or "")[m.end():]


def view_from_file(p, rel):
    text = read_text(p)
    fm, body = front_matter(text)
    stem = p.stem
    meta = {"file": rel, "title": fm.get("title"), "doi": fm.get("doi"),
            "language": fm.get("language") or fm.get("lang") or lang_from_token(p.name),
            "version": _map_version_word(fm.get("version")),
            "view_id": fm.get("view_id") or stem,
            "work_id": fm.get("work_id") or derive_work_id(rel, fm, body)}
    key = "%s#L1-%d" % (rel, max(1, len(text.splitlines())))
    return base_view("file", key, text, meta)


def _map_version_word(w):
    if not w:
        return None
    x = low(w)
    for ver, toks in FILE_VERSION:
        if any(t in x for t in toks):
            return ver
    return x


def derive_work_id(rel, fm, body):
    if fm.get("work_id"):
        return fm["work_id"]
    d = fm.get("doi") or doi_of(body)
    if d:
        return "W-" + re.sub(r"[^a-z0-9]+", "-", d.lower())[:40]
    parts = [q for q in Path(rel).parts[:-1]]
    stem = Path(rel).stem
    tok = re.split(r"[_\-.]", stem)
    if len(tok) > 1 and re.fullmatch(r"(v|view)\d*", tok[0].lower()):
        return "W-" + tok[0].lower()
    if parts and low(parts[-1]) not in ("materials", "input", "views", "works", ""):
        return "W-" + re.sub(r"[^a-z0-9]+", "-", low(parts[-1]))[:30]
    return "W-" + re.sub(r"[^a-z0-9]+", "-", low(stem))[:40]


def view_from_obj(obj, rel, jsonpath, ctx):
    text = first_str(obj, TEXT_KEYS)
    abs_text = first_str(obj, ABS_KEYS)
    body = text or ""
    if not body and abs_text:
        body = abs_text
    elif text and abs_text and norm(abs_text) not in norm(text):
        body = text + "\n\n## Abstract\n" + abs_text
    if not body:
        return None
    meta = {
        "file": rel,
        "view_id": first_str(obj, ID_KEYS) or "%s::%s" % (Path(rel).stem, jsonpath),
        "work_id": first_str(obj, WORK_KEYS) or ctx.get("work_id") or "",
        "doi": first_str(obj, DOI_KEYS) or ctx.get("doi") or doi_of(body),
        "title": first_str(obj, TITLE_KEYS) or ctx.get("title") or "",
        "language": first_str(obj, LANG_KEYS),
        "version": _map_version_word(first_str(obj, VER_KEYS)),
    }
    key = "%s::%s" % (rel, jsonpath)
    v = base_view("json", key, body, meta)
    if not text and abs_text:
        v["doc_type"], v["version"] = "abstract_only", "abstract_only"
    return v


def _views_key(k):
    return low(k) in ("views", "view", "view_list", "views_list", "doc_views", "documents",
                      "records", "items", "entries")


def looks_like_view(d):
    if not isinstance(d, dict):
        return False
    body = first_str(d, TEXT_KEYS) or first_str(d, ABS_KEYS)
    if not body or len(body) < 40:
        return False
    return bool(first_str(d, ID_KEYS) or first_str(d, WORK_KEYS) or first_str(d, TITLE_KEYS))


def harvest(obj, rel, jsonpath, out, ctx, depth=0):
    if depth > 8:
        return
    if isinstance(obj, list):
        for i, it in enumerate(obj):
            harvest(it, rel, "%s[%d]" % (jsonpath, i), out, ctx, depth + 1)
        return
    if not isinstance(obj, dict):
        return
    if looks_like_view(obj):
        v = view_from_obj(obj, rel, jsonpath, ctx)
        if v:
            out.append(v)
        return
    nctx = dict(ctx)
    for k in WORK_KEYS:
        if isinstance(obj.get(k), str) and obj[k].strip():
            nctx["work_id"] = obj[k].strip()
            break
    for k in DOI_KEYS:
        if isinstance(obj.get(k), str) and obj[k].strip():
            nctx["doi"] = obj[k].strip()
            break
    for k in TITLE_KEYS:
        if isinstance(obj.get(k), str) and obj[k].strip():
            nctx["title"] = obj[k].strip()
            break
    for k, v in obj.items():
        if isinstance(v, (list, dict)):
            harvest(v, rel, "%s.%s" % (jsonpath, k), out, nctx, depth + 1)


def read_json_any(p):
    raw = read_text(p)
    if p.suffix in (".jsonl", ".ndjson"):
        rows = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows
    try:
        return json.loads(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------- discovery
def discover(inp, st=None):
    st = st or {"degradations": [], "errors": []}
    root = Path(inp)
    views, sources, seen_json = [], [], set()
    files = []
    try:
        files = [p for p in sorted(root.rglob("*")) if p.is_file()]
    except OSError as e:
        st["errors"].append({"stage": "scan", "message": str(e)[:200]})
    for p in files:
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = p.name
        ext = p.suffix.lower()
        if p.name in CASE_NAMES or low(p.name).startswith("task"):
            sources.append({"source_id": "task" if p.name != "case.json" else "case",
                            "file": rel, "type": ext.lstrip("."), "role": "task_input",
                            "notes": "input contract / instruction"})
            continue
        if ext in JSON_EXT:
            obj = read_json_any(p)
            if obj is None:
                st["degradations"].append({"item": rel, "stage": "json_parse",
                                           "action": "skip file, record as unreadable",
                                           "impact": "views in this file not indexed"})
                sources.append({"source_id": Path(rel).stem, "file": rel, "type": "json",
                                "role": "metadata", "notes": "unparsable JSON"})
                continue
            got = []
            harvest(obj, rel, "$", got, {})
            if got:
                views.extend(got)
                seen_json.add(rel)
                sources.append({"source_id": Path(rel).stem, "file": rel, "type": "json",
                                "role": "views_container", "notes": "%d views" % len(got)})
            else:
                sources.append({"source_id": Path(rel).stem, "file": rel, "type": "json",
                                "role": "metadata", "notes": "no view-shaped records"})
            continue
        if ext in TEXT_EXT:
            txt = read_text(p)
            if wc(txt) < 5:
                sources.append({"source_id": Path(rel).stem, "file": rel, "type": ext.lstrip("."),
                                "role": "empty", "notes": "no usable text"})
                continue
            v = view_from_file(p, rel)
            views.append(v)
            sources.append({"source_id": Path(rel).stem, "file": rel, "type": ext.lstrip("."),
                            "role": "view_file", "notes": "view_id=%s" % v["view_id"]})
            continue
        if ext in BIB_EXT:
            sources.append({"source_id": Path(rel).stem, "file": rel, "type": ext.lstrip("."),
                            "role": "metadata", "notes": "bibliographic/metadata only"})
            continue
        if ext in BIN_EXT:
            sources.append({"source_id": Path(rel).stem, "file": rel, "type": ext.lstrip("."),
                            "role": "binary", "notes": "not text-extractable by script"})
            st["degradations"].append({"item": rel, "stage": "binary_material",
                                       "action": "not parsed by pure-stdlib script",
                                       "impact": "read this file with the harness tool and "
                                                 "record its content in the draft"})
            continue
        sources.append({"source_id": Path(rel).stem or rel, "file": rel,
                        "type": ext.lstrip(".") or "unknown", "role": "other", "notes": ""})
    if not views:
        st["degradations"].append({"item": "views", "stage": "discovery",
                                   "action": "no view-shaped material found",
                                   "impact": "cards fall back to misses"})
    return assign_ids(views), sources


def assign_ids(views):
    """Unique view_id, then one canonical work_id per DOI (declared label wins if unanimous)."""
    seen = set()
    for i, v in enumerate(views):
        vid = (v.get("view_id") or "").strip()
        if not vid or vid in seen:
            vid = "%s-v%d" % (v.get("work_id") or "view", i + 1)
        seen.add(vid)
        v["view_id"] = vid
    groups = {}
    for v in views:
        d = low(v.get("doi") or "")
        if d:
            groups.setdefault(d, []).append(v)
    for x in views:
        x["work_id_basis"] = "declared" if x.get("work_id") else None
    for d, g in groups.items():
        declared = {x.get("work_id") for x in g if x.get("work_id")}
        wid = declared.pop() if len(declared) == 1 else "W-" + re.sub(
            r"[^a-z0-9]+", "-", d)[:28]
        for x in g:
            if x.get("work_id") != wid:
                x["merged_from_work"] = x.get("work_id") or None
                x["work_id"] = wid
            x["work_id_basis"] = "doi"
    for v in views:
        if not v.get("work_id"):
            v["work_id"] = derive_work_id(v.get("source_path") or v["view_id"], {},
                                          v.get("text", ""))
            v["work_id_basis"] = "filename"
    return views


def dedup(views, st=None):
    """精确 sha 去重 + 同 work 同语种近重复，写 duplicate_of。"""
    st = st or {"degradations": [], "uncertainties": []}
    by_sha = {}
    for v in sorted(views, key=lambda x: (x["work_id"], x["view_id"])):
        h = v["sha256"]
        if h in by_sha:
            v["duplicate_of"] = by_sha[h]["view_id"]
            v["duplicate_kind"] = "exact_sha256"
            v["version"] = "duplicate"
        else:
            by_sha[h] = v
    groups = {}
    for v in views:
        groups.setdefault((v["work_id"], low(v["language"])), []).append(v)
    for key, g in groups.items():
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g[i], g[j]
                if a["duplicate_of"] or b["duplicate_of"]:
                    continue
                sim = jaccard(a.get("text", ""), b.get("text", ""))
                if sim >= 0.92:
                    b["duplicate_of"] = a["view_id"]
                    b["duplicate_kind"] = "near_duplicate_jaccard=%.2f" % sim
                    b["version"] = "duplicate"
                elif sim >= 0.55:
                    st["uncertainties"].append({
                        "id": "U-dup-%s-%s" % (a["view_id"], b["view_id"]),
                        "type": "version_conflict", "object": "%s/%s" % (a["view_id"], b["view_id"]),
                        "description": "同 work 同语种两份视图内容相似度 %.2f，无法判定是否同版本"
                                       % sim,
                        "impact": "去重计数按 work 口径，明细保留两视图",
                        "quote": norm(a.get("text", ""))[:120]})
    return views


def jaccard(a, b):
    A, B = shingles(a), shingles(b)
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B))


def shingles(text, k=5):
    toks = re.findall(r"[a-z0-9]{2,}", low(text))
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


# ---------------------------------------------------------------- quoting
def units(view, limit=400):
    """句级证据单元：quote + locator（文件用行号，JSON 用 ::sN）。"""
    text = view.get("text", "")
    out = []
    is_json = view.get("key_form") == "json"
    base = view.get("locator") or view.get("view_id", "?")
    for ln, line in enumerate(text.splitlines(), start=1):
        s = line.strip().lstrip("#").strip()
        if len(s) < 25:
            continue
        for piece in re.split(r"(?<=[.!?;:])\s+(?=[A-ZÀ-Ý0-9\"“])", s):
            piece = norm(piece)
            if len(piece) < 25:
                continue
            loc = ("%s::s%d" % (base, len(out) + 1)) if is_json else \
                  ("%s#L%d" % (view.get("source_path") or view.get("view_id"), ln))
            out.append({"quote": piece[:600], "locator": loc, "line": ln})
            if len(out) >= limit:
                return out
    return out


def find_quote(views, quote):
    """在全部视图中逐字（空白归一化）查找 quote，返回命中点。"""
    q = norm(low(quote))
    if len(q) < 6:
        return []
    hits = []
    for v in views:
        hay = norm(low(v.get("text", "")))
        pos = hay.find(q)
        if pos >= 0:
            hits.append({"view_id": v["view_id"], "work_id": v["work_id"],
                         "locator": locate_at(v, hay, pos, len(q)),
                         "language": v["language"], "version": v["version"]})
    return hits


def locate_at(view, hay, pos, qlen):
    """把归一化文本里的偏移换回可复核 locator：文件给行号，JSON 给记录路径。"""
    if view.get("key_form") == "json":
        return "%s::q" % (view.get("locator") or view.get("view_id"))
    flat = low(view.get("text", ""))
    probe = norm(hay[pos:pos + min(qlen, 40)])
    idx = flat.find(probe)
    if idx < 0:
        idx = 0
    line = flat[:idx].count("\n") + 1
    return "%s#L%d" % (view.get("source_path") or view.get("view_id"), max(1, line))


def snippet_around(view, quote, width=180):
    raw = view.get("text", "")
    q = norm(quote)
    i = norm(low(raw)).find(norm(low(q))[:60])
    if i < 0:
        return None
    return norm(raw[max(0, i - width // 3):i + width])


def fingerprint(v):
    keep = ("view_id", "work_id", "doi", "title", "language", "language_basis",
            "language_declared", "language_detected", "lang_confidence", "version",
            "doc_type", "sha256", "chars", "words", "duplicate_of", "duplicate_kind",
            "locator", "key_form", "source_path", "sections", "work_id_basis")
    fp = {k: v.get(k) for k in keep}
    fp["version_basis"] = v.get("version_basis", [])[:2]
    fp["lang_evidence"] = (v.get("lang_evidence") or [{}])[0].get("markers", [])[:4]
    return fp


def counts(views):
    distinct = sorted({v["work_id"] for v in views})
    per_work = {w: sorted({v["view_id"] for v in views if v["work_id"] == w}) for w in distinct}
    langs = {}
    for v in views:
        if not v.get("duplicate_of"):
            langs.setdefault(v["language"], []).append(v["view_id"])
    return {"views_total": len(views), "distinct_works": len(distinct),
            "views_per_work": per_work,
            "unique_views": len([v for v in views if not v.get("duplicate_of")]),
            "duplicates": [v["view_id"] for v in views if v.get("duplicate_of")],
            "by_language": {k: len(v) for k, v in sorted(langs.items())},
            "languages": sorted(langs)}
