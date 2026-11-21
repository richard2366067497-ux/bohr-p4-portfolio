# -*- coding: utf-8 -*-
"""rules.py - term scoring, hard filters, dedupe/version chains and deterministic retrieval."""
import os
import re
from pathlib import Path

YEAR_RE = re.compile(r"(?<!\d)(20\d{2}|19[89]\d)(?!\d)")
VER_RE = re.compile(r"(?i)(?:\bv(?:er(?:sion)?)?\s*[-_.]?(\d+(?:\.\d+)*)\b|\brev(?:ision)?\s*[-_.]?(\d+)\b"
                    r"|第\s*(\d+)\s*版|\br(\d+)\b)")
FINAL_RE = re.compile(r"(?i)(final|submitted|accepted|published|终版|定稿|最终|已提交)")
BATCH_RE = re.compile(r"(?i)\b(?:batch|批次|lot|run)[-_\s]?([A-Z]?\d{1,4})\b")
PROJ_RE = re.compile(r"(?i)\b(?:project|proj|项目)[-_\s]?(?:no\.?|编号)?[-_\s]?([A-Z]{1,4}[-_]?\d{2,6})\b")

FKEY = {"year": "year", "年份": "year", "年": "year", "date": "year", "time": "year",
        "时间": "year", "pub_year": "year", "published": "year",
        "type": "type", "类型": "type", "格式": "type", "format": "type", "ext": "type",
        "extension": "type", "filetype": "type", "file_type": "type", "扩展名": "type",
        "project": "project", "项目": "project", "项目编号": "project",
        "project_id": "project", "proj": "project", "课题": "project",
        "batch": "batch", "批次": "batch", "实验批次": "batch", "run": "batch",
        "lot": "batch",
        "version": "version", "版本": "version", "rev": "version", "revision": "version",
        "permission": "permission", "权限": "permission", "access": "permission",
        "visibility": "permission",
        "author": "author", "作者": "author", "tag": "tag", "标签": "tag"}
TYPE_WORD = re.compile(r"(?i)\b(pdf|docx?|xlsx?|pptx?|csv|txt|markdown|md|tex|json|png|jpe?g|"
                       r"扫描件|图片)\b")
OPS = (">=", "<=", "!=", "==", "=>", "=<", "=", ">", "<")

def lk(d, keys, default=None):
    if not isinstance(d, dict):
        return default
    low = {str(k).lower().replace("-", "_"): v for k, v in d.items()}
    for k in keys:
        kk = k.lower().replace("-", "_")
        if kk in low and low[kk] not in (None, "", [], {}):
            return low[kk]
    return default

def norm_type_word(w):
    w = str(w).lower().strip(".")
    return {"doc": "docx", "xls": "xlsx", "ppt": "pptx", "markdown": "md",
            "扫描件": "pdf", "图片": "image"}.get(w, w)

# ---------------------------------------------------------------- path metadata
def meta_from_name(rel):
    s = str(rel)
    out = {"sources": {}}
    m = YEAR_RE.search(s)
    if m:
        out["year"] = int(m.group(1))
        out["sources"]["year"] = "path"
    m = VER_RE.search(s)
    if m:
        out["version"] = "v" + next(g for g in m.groups() if g)
        out["sources"]["version"] = "path"
    elif FINAL_RE.search(s):
        out["version"] = "final"
        out["sources"]["version"] = "path"
    m = BATCH_RE.search(s)
    if m:
        out["batch"] = m.group(1)
        out["sources"]["batch"] = "path"
    m = PROJ_RE.search(s)
    if m:
        out["project"] = m.group(1)
        out["sources"]["project"] = "path"
    return out

def merge_declared(decl, rel):
    out = {"year": None, "version": None, "project": None, "batch": None, "tags": [], "sources": {}}
    guess = meta_from_name(rel)
    md = lk(decl, ("metadata", "meta", "attributes", "properties", "元数据")) or {}
    for src, tag in ((guess, "path"), (md if isinstance(md, dict) else {}, "declared")):
        for k in ("year", "version", "project", "batch"):
            v = src.get(k) if isinstance(src, dict) else None
            if v not in (None, ""):
                out[k] = v
                out["sources"][k] = tag
    for k, alt in (("year", "pub_year"), ("version", "edition"), ("project", "project_id"),
                   ("batch", "experiment_batch"), ("author", "creator")):
        v = lk(decl, (k, alt))
        if v not in (None, ""):
            out[k] = v
            out["sources"][k] = "declared"
    tg = lk(decl, ("tags", "labels", "keywords", "标签"))
    if isinstance(tg, list):
        out["tags"] = [str(t) for t in tg]
    elif isinstance(tg, str):
        out["tags"] = [t.strip() for t in re.split(r"[,;、]", tg) if t.strip()]
    return out

# ---------------------------------------------------------------- filter parsing
def _cond(key, value, op=None):
    k = FKEY.get(str(key).strip().lower()) or FKEY.get(str(key).strip())
    if not k:
        return None
    if isinstance(value, (list, tuple)):
        return {"key": k, "op": "in", "value": [norm_type_word(v) if k == "type" else v for v in value],
                "raw": f"{key} in {list(value)}"}
    s = str(value).strip()
    op2 = op
    if op2 is None:
        for o in OPS:
            if s.startswith(o):
                op2 = ">=" if o == "=>" else "<=" if o == "=<" else "=" if o == "==" else o
                s = s[len(o):].strip()
                break
    if k == "type":
        s = norm_type_word(s)
    return {"key": k, "op": op2 or "=", "value": s, "raw": f"{key} {op2 or '='} {s}"}

def _cond_str(part):
    part = part.strip()
    if not part:
        return []
    m = re.match(r"^(?P<k>[A-Za-z_一-龥][A-Za-z_一-龥 ]{0,12}?)\s*"
                 r"(?P<op>>=|<=|!=|==|=|>|<|:|：)\s*(?P<v>.+)$", part)
    if m and FKEY.get(m.group("k").strip().lower()):
        c = _cond(m.group("k"), m.group("v"),
                  None if m.group("op") in (":", "：") else m.group("op"))
        return [c] if c else []
    low = part.lower()
    ty = TYPE_WORD.search(part)
    if ty and re.search(r"(?i)only|仅|只|限定|限|type|格式|类型", part):
        return [{"key": "type", "op": "=", "value": norm_type_word(ty.group(1)), "raw": part}]
    ym = re.search(r"(?<!\d)(20\d{2})(?!\d)", part)
    if ym:
        op = ">=" if re.search(r"之后|以后|以来|起|since|after|later than|"
                               r"≥|>=", low) else "="
        return [{"key": "year", "op": op, "value": int(ym.group(1)), "raw": part}]
    pm = PROJ_RE.search(part) or re.search(r"\b([A-Z]{1,4}[-_]\d{2,6})\b", part)
    if pm:
        return [{"key": "project", "op": "=", "value": pm.group(1), "raw": part}]
    bm = BATCH_RE.search(part)
    if bm:
        return [{"key": "batch", "op": "=", "value": bm.group(1), "raw": part}]
    vm = VER_RE.search(part)
    if vm:
        return [{"key": "version", "op": "=", "value": "v" + next(g for g in vm.groups() if g), "raw": part}]
    if FINAL_RE.search(part):
        return [{"key": "version", "op": "=", "value": "final", "raw": part}]
    if ty:
        return [{"key": "type", "op": "=", "value": norm_type_word(ty.group(1)), "raw": part}]
    return [{"key": "unparsed", "op": "=", "value": part, "raw": part}]

def parse_filters(raw):
    conds = []
    if raw in (None, "", [], {}):
        return conds
    if isinstance(raw, dict):
        for k, v in raw.items():
            c = _cond(k, v)
            if c:
                conds.append(c)
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict):
                fld = item.get("field") or item.get("key") or item.get("name") or item.get("filter")
                if fld and ("value" in item or "values" in item):
                    c = _cond(fld, item.get("value", item.get("values")), item.get("op"))
                    if c:
                        conds.append(c)
                else:
                    for k, v in item.items():
                        c = _cond(k, v)
                        if c:
                            conds.append(c)
            elif isinstance(item, str):
                conds.extend(_cond_str(item))
    elif isinstance(raw, str):
        for part in re.split(r"[;,、]|\band\b|\bAND\b", raw):
            conds.extend(_cond_str(part))
    return [c for c in conds if c]

def filter_text(c):
    return f"{c['key']}{c['op']}{c['value']}" if c["op"] != "in" else f"{c['key']} in {c['value']}"

# ---------------------------------------------------------------- filter evaluation
def doc_attrs(doc):
    md = doc.get("meta") or {}
    a = {"year": md.get("year"), "version": doc.get("version") or md.get("version"),
         "project": md.get("project"), "batch": md.get("batch"),
         "type": norm_type_word(doc.get("ext") or doc.get("type") or ""),
         "permission": doc.get("permission") or "read", "author": md.get("author"),
         "tag": list(md.get("tags") or []) + list(doc.get("aliases") or [])}
    if a["year"] is None:
        m = YEAR_RE.search(doc.get("path") or "")
        if m:
            a["year"] = int(m.group(1))
    if a["year"] is None and doc.get("mtime_year"):
        a["year"] = doc["mtime_year"]
    return a

def _cmp(op, have, want):
    if op == "in":
        wants = [str(w).lower() for w in (want if isinstance(want, (list, tuple)) else [want])]
        if isinstance(have, list):
            return any(str(h).lower() in wants for h in have)
        return str(have).lower() in wants
    hs, ws = str(have).strip(), str(want).strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", hs) and re.fullmatch(r"-?\d+(?:\.\d+)?", ws):
        h, w = float(hs), float(ws)
        return {"=": h == w, ">=": h >= w, "<=": h <= w, ">": h > w, "<": h < w,
                "!=": h != w}.get(op, False)
    if op in ("=", "=="):
        return hs.lower() == ws.lower() or ws.lower() in hs.lower()
    if op == "!=":
        return hs.lower() != ws.lower()
    if op in (">", "<", ">=", "<="):
        a, b = _natkey(hs), _natkey(ws)
        if a == b:
            return op in (">=", "<=")
        return a > b if op in (">", ">=") else a < b
    return False

def _natkey(s):
    return [(0, int(t)) if t.isdigit() else (1, t.lower()) for t in re.split(r"(\d+)", str(s or ""))]

def eval_filters(conds, doc):
    attrs = doc_attrs(doc)
    fails = []
    for c in conds:
        k, op, want = c["key"], c["op"], c["value"]
        if k == "unparsed":
            fails.append({"filter": c["raw"], "reason": "unparsed_condition",
                          "detail": "条件未被机器解析，按不可满足处理"})
            continue
        have = attrs.get(k)
        res = _cmp(op, have, want)
        if res is None:
            fails.append({"filter": c["raw"], "reason": "attribute_unknown",
                          "detail": f"文档缺少 {k} 属性，无法满足该条件"})
        elif not res:
            fails.append({"filter": c["raw"], "reason": "mismatch",
                          "detail": f"{k}={have!r} 不满足 {op} {want!r}"})
    return (not fails), fails

def filter_ledger(conds, docs):
    rows = []
    for c in conds:
        kept, removed, reasons = [], [], {}
        for d in docs:
            ok, f = eval_filters([c], d)
            if ok:
                kept.append(d.get("doc_id"))
            else:
                removed.append(d.get("doc_id"))
                for x in f:
                    reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
        rows.append({"filter": filter_text(c), "raw": c.get("raw"), "key": c["key"], "op": c["op"],
                     "value": c["value"], "kept": len(kept), "removed": len(removed),
                     "kept_docs": kept[:20], "removed_docs": removed[:20],
                     "removal_reasons": reasons,
                     "satisfiable": bool(kept),
                     "relaxation_note": ("若放宽该条件，会命中 "
                                         + ", ".join(removed[:5]) if removed else
                                         "放宽后无额外命中")})
    return rows

def apply_all(conds, docs):
    allowed, blocked = [], {}
    for d in docs:
        ok, f = eval_filters(conds, d)
        if ok:
            allowed.append(d)
        else:
            blocked[d.get("doc_id")] = f
    return allowed, blocked, bool(allowed)

# ---------------------------------------------------------------- duplicates / versions
COPY_RE = re.compile(r"(?i)(?:^|[\s_\-.])copy(?:[\s_\-.]|$)|copy\s*of|duplicate|backup|\bbak\b|"
                     r"副本|拷贝|复制件")

def base_key(rel):
    s = Path(str(rel)).name.lower()
    s = re.sub(r"\.(pdf|docx?|xlsx?|pptx?|txt|md|csv|tsv|json|tex|png|jpe?g|tiff?)$", "", s)
    s = COPY_RE.sub("", s)
    s = re.sub(r"\(\s*\d+\s*\)|（\s*\d+\s*）", "", s)
    s = re.sub(r"(?i)(^|[\s_\-.])(ver(?:sion)?|rev(?:ision)?|v|r)[\s_\-.]?\d+(?:[._]\d+)*",
               r"\1", s)
    s = re.sub(r"(?i)(^|[\s_\-.])(final|submitted|accepted|published|draft|revised|终版|定稿|最终|修订版?)",
               r"\1", s)
    s = re.sub(r"[\s_\-.]+", "", s)
    return s or Path(str(rel)).stem.lower()

def ver_rank(doc):
    v = str(doc.get("version") or (doc.get("meta") or {}).get("version") or "")
    if not v:
        return (-1,)
    if FINAL_RE.search(v):
        return (9999,)
    nums = re.findall(r"\d+", v)
    return tuple(int(x) for x in nums) if nums else (0,)

def _tokens(doc):
    txt = (doc.get("_head") or " ".join(p.get("text", "")[:120] for p in (doc.get("paragraphs") or [])[:4])
           or "")[:1600].lower()
    return set(re.findall(r"[a-z0-9一-龥]{2,}", txt))

def _sim(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))

def dedupe(docs):
    groups, excluded = [], []
    by_sha = {}
    for d in docs:
        if d.get("status") not in ("ok", "low_text_quality") or not d.get("sha256"):
            continue
        by_sha.setdefault(d["sha256"], []).append(d)

    def pref(g):
        return sorted(g, key=lambda d: (bool(d.get("declared")),
                                        0 if COPY_RE.search(d.get("path", "")) else 1,
                                        ver_rank(d), -len(d.get("path", "")),
                                        str(d.get("doc_id"))))[-1]

    for sha, g in by_sha.items():
        if len(g) < 2:
            continue
        rep = pref(g)
        groups.append({"group_id": "dup:" + sha[:12], "kind": "identical_copy", "sha256_12": sha[:12],
                       "representative": rep.get("doc_id"),
                       "members": [{"doc_id": d.get("doc_id"), "path": d.get("path")} for d in g]})
        for d in g:
            d["representative"] = d is rep
            if d is not rep:
                d["duplicate_of"] = rep.get("doc_id")
                excluded.append({"doc_id": d.get("doc_id"), "path": d.get("path"),
                                 "reason": f"duplicate_of:{rep.get('doc_id')}",
                                 "detail": "字节级副本（sha256 相同），"
                                           "不作为独立证据",
                                 "evidence_ban": True})
    by_base = {}
    for d in docs:
        if d.get("status") not in ("ok", "low_text_quality") or d.get("duplicate_of"):
            continue
        by_base.setdefault(base_key(d.get("path", "")), []).append(d)
    for base, g in by_base.items():
        if len(g) < 2:
            continue
        gg = sorted(g, key=lambda d: ver_rank(d))
        rep = gg[-1]
        for d in gg[:-1]:
            sim = _sim(d, rep)
            if sim < 0.35:
                continue
            d["representative"] = False
            d["older_version_of"] = rep.get("doc_id")
            groups.append({"group_id": "ver:" + base[:16], "kind": "version_chain",
                           "representative": rep.get("doc_id"), "similarity": round(sim, 3),
                           "members": [{"doc_id": x.get("doc_id"), "path": x.get("path"),
                                        "version": x.get("version")} for x in gg]})
            excluded.append({"doc_id": d.get("doc_id"), "path": d.get("path"),
                             "reason": f"older_version_of:{rep.get('doc_id')}",
                             "detail": f"同基名版本链，相似度 {sim:.2f}，"
                                       f"代表版本为 {rep.get('doc_id')} ({rep.get('version')})",
                             "evidence_ban": True})
    for d in docs:
        d.setdefault("representative", True)
    conflicts = []
    by_name = {}
    for d in docs:
        by_name.setdefault(Path(d.get("path", "")).name.lower(), []).append(d)
    for name, g in by_name.items():
        if len(g) > 1 and len({d.get("sha256") for d in g}) > 1:
            conflicts.append({"basename": name, "same_name_diff_content": True,
                              "members": [{"doc_id": d.get("doc_id"), "path": d.get("path"),
                                           "sha256_16": d.get("sha256_16")} for d in g]})
    return groups, excluded, conflicts

# ---------------------------------------------------------------- retrieval (deterministic candidates)
def _nw(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\u3000", " ").replace("\u00a0", " ")).strip()

SYN = {
    "buffer": ["缓冲液", "缓冲", "pbs", "tris", "hepes"],
    "缓冲液": ["buffer", "pbs", "tris", "hepes"],
    "protocol": ["方案", "流程", "操作步骤", "procedure", "sop", "workflow"],
    "方案": ["protocol", "procedure", "plan", "sop"],
    "batch": ["批次", "批", "lot", "run"],
    "批次": ["batch", "lot", "run"],
    "sample": ["样品", "样本", "specimen"],
    "样品": ["sample", "specimen"],
    "instrument": ["仪器", "设备", "装置", "device", "equipment"],
    "仪器": ["instrument", "device", "equipment"],
    "measurement": ["测量", "测定", "检测", "measure", "assay"],
    "测定": ["measurement", "measure", "assay"],
    "calibration": ["校准", "标定", "calibrate"],
    "校准": ["calibration", "calibrate"],
    "室温": ["room temperature", "rt", "ambient"],
    "离心": ["centrifuge", "centrifugation", "spin"],
    "图": ["figure", "fig", "plot"],
    "表": ["table", "sheet"],
    "补充材料": ["supplementary", "supporting information", "appendix"],
    "摘要": ["abstract", "summary"],
    "方法": ["method", "methods", "methodology", "procedure"],
    "结果": ["result", "results", "finding"],
    "讨论": ["discussion"],
    "结论": ["conclusion", "conclusions"],
    "参考文献": ["references", "bibliography"],
    "project": ["项目", "项目编号", "proj"],
}

# ---------------------------------------------------------------- retrieval
def q_terms(q, extra=None):
    terms = {}

    def add(t, w):
        t = _nw(t).lower()
        if len(t) < 2:
            return
        terms[t] = max(terms.get(t, 0.0), w)

    low = q.lower()
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-_.]{2,}", q):
        add(tok, 1.3)
    for num in re.findall(r"\d+(?:\.\d+)?", q):
        if len(num) >= 2:
            add(num, 1.0)
    for seg in re.findall(r"[㐀-鿿]{2,}", q):
        for i in range(len(seg) - 1):
            add(seg[i:i + 2], 1.0)
        if len(seg) <= 6:
            add(seg, 1.4)
    for k, vs in list(SYN.items()) + list((extra or {}).items()):
        if k.lower() in low:
            for v in vs:
                add(v, 1.2)
    return terms

def score_para(text, terms, phrase=None):
    low = text.lower()
    s, hits, toks = 0.0, [], None
    for t, w in terms.items():
        c = low.count(t)
        if not c and len(t) >= 5:
            if toks is None:
                toks = set(re.findall(r"[a-z0-9一-鿿]+", low))
            c = sum(1 for x in toks if x.startswith(t[:5]))
        if c:
            s += w * (1 + 0.2 * min(c - 1, 3))
            hits.append(t)
    if not hits:
        return 0.0, []
    s /= 1.0 + len(low) / 1200.0
    if phrase and len(phrase) > 6 and phrase.lower() in low:
        s += 2.0
    return round(s, 4), hits

def search(index, question, conds, extra=None, k=8):
    docs = index.get("docs") or []
    allowed, blocked, ok = apply_all(conds, docs)
    if not ok and conds:
        return [], blocked, False
    terms = q_terms(question, extra)
    hits = []
    for d in allowed:
        if d.get("status") != "ok" or not d.get("paragraphs"):
            continue
        for p in d.get("paragraphs") or []:
            s, hs = score_para(p.get("text") or "", terms, question)
            if s > 0:
                hits.append({"doc_id": d.get("doc_id"), "path": d.get("path"),
                             "version": d.get("version"), "section_id": p.get("section_id"),
                             "section": p.get("section"), "paragraph_id": p.get("pid"),
                             "page_physical": p.get("page_physical"),
                             "page_printed": p.get("page_printed"), "source": p.get("source"),
                             "score": s, "terms": hs[:8], "origin": "script",
                             "text": (p.get("text") or "")[:400]})
    hits.sort(key=lambda h: (-h["score"], h["doc_id"], h["paragraph_id"]))
    return hits[:k], blocked, True
