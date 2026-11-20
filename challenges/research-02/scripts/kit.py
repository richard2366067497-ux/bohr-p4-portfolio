#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""outline-slot-review 文本层：环境与输入发现 / 定位切分 / 逐字引文校验 / 强度判据。
分层 kit（怎么读）→ rules（怎么判）→ main（命令行）；纯标准库、离线、不依赖 CWD。"""

import csv, hashlib, json, re, shutil, subprocess, time, unicodedata, zipfile, zlib
from difflib import SequenceMatcher
from pathlib import Path

V = "1.0.0"
SKILL = "outline-slot-review"
DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
ABS = re.compile(r"(?i)(?:^|\b)(abstract|summary|摘要|概要)(?:\b|$)")
SKIPNAME = {"case.json", "task.md", "task.txt"}
GAP_TYPES = ("retrieval_gap", "unresolved_conflict", "method_limitation", "scope_limit")
STAGE = ("title_abstract", "full_text")
ORDER = {"weak": 0, "moderate": 1, "strong": 2}

# 错误码：code -> (名称, 级别, 处置, 含义)。FIX=必须修；WARN=build 自动处置或记降级。
CODES = {
 "S101": ("criteria_empty", "FIX", "写至少 1 条 include 与 1 条 exclude 条款", "纳排标准缺失：标准须先于筛选写定"),
 "S102": ("screening_empty", "WARN", "按记录逐条给 decision", "筛选记录为空"),
 "S103": ("row_unknown_criterion", "FIX", "改用已声明的 criterion_id", "筛选行引用了不存在的条款"),
 "S104": ("exclude_without_criterion", "FIX", "补 criterion_id 与 reason", "排除/待定决策未挂条款"),
 "S105": ("record_uncovered", "WARN", "补该记录的筛选行", "输入记录未出现在筛选记录中"),
 "S106": ("duplicate_unmarked", "WARN", "标 duplicate_of 并排除", "重复记录未标注"),
 "S107": ("stage_order", "WARN", "先 title_abstract 再 full_text", "全文阶段行缺题录阶段行"),
 "O101": ("outline_empty", "FIX", "写至少 2 节，每节 ≥1 slot", "提纲为空"),
 "O102": ("section_fields", "WARN", "补 heading/purpose", "section 缺 heading 或 purpose"),
 "O103": ("slot_orphan", "FIX", "删除或并入 outline", "slots 中的槽位未在 outline 声明"),
 "O105": ("outline_generic", "WARN", "补 outline_basis 说明分布依据", "提纲标题疑似通用模板"),
 "Q101": ("filled_no_evidence", "FIX", "补 evidence_refs 或改判 gap", "filled 槽位没有证据行"),
 "Q102": ("source_unknown", "FIX", "改用输入中存在的 source_id", "证据引用了不存在的文献"),
 "Q103": ("quote_not_verbatim", "FIX", "从材料逐字复制 quote", "引文仅差异于空白/标点"),
 "Q104": ("quote_miss", "FIX", "回原文重取或改判 gap", "引文在所指文献中找不到"),
 "Q105": ("source_excluded", "WARN", "改用纳入文献或说明理由", "引文来自被排除/待定文献"),
 "Q106": ("abstract_only_overclaim", "WARN", "强度封顶 moderate", "仅摘要文献支撑了 strong"),
 "Q107": ("strength_overclaim", "WARN", "按 strength_hint 下调", "自评强度高于证据判据"),
 "Q108": ("doi_not_in_material", "WARN", "删除或改为材料原样", "文本中的 DOI 不在材料里"),
 "G101": ("gap_missing_fields", "FIX", "补 gap_reason/search_scope/missing_evidence", "缺口槽位字段不全"),
 "G102": ("gap_type_invalid", "FIX", "用 GAP_TYPES 中的取值", "gap_type 非法"),
 "G103": ("gap_cliche", "WARN", "把空白落到具体缺口 id", "缺口/空白用了套话"),
 "D101": ("lead_without_slots", "WARN", "补 lead_slot_ids 或删 lead", "节首导语没有槽位回链"),
 "C101": ("draft_json_missing", "FIX", "按 SKILL.md 第 5 节写 draft.json", "工作稿缺失：build 走兜底"),
 "C102": ("json_invalid", "FIX", "修 JSON 语法后重跑 check", "工作稿不是合法 JSON"),
 "C103": ("case_id_mismatch", "WARN", "与 case.json 对齐", "工作稿 case_id 与输入不一致"),
 "C104": ("contract_unmapped", "WARN", "人工确认该字段含义", "contract 字段无对应产物"),
 "X101": ("conflict_unknown_slot", "WARN", "删除无效引用", "conflicts_with 指向不存在的槽位"),
 "X102": ("conflict_asymmetric", "WARN", "build 自动补对称", "冲突关系单向声明"),
}


# ------------------------------------------------------------------ 基础 I/O
def sha256(p):
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(1 << 16), b""):
                h.update(c)
        return h.hexdigest()
    except Exception:
        return None


def write_text(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, "utf-8")


def write_json(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=2), "utf-8")
    t.replace(p)


def write_jsonl(p, rows):
    write_text(p, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_json(p, dflt=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return dflt


def nq(s):
    """比对归一：NFKC + 引号/破折号统一 + 去空白。只判"是否同一段文字"，不改写原文。"""
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2014", "-"), ("\u2013", "-"), ("\u00a0", " "), ("\u3000", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def detect_lang(text):
    t = (text or "")[:20000]
    return "zh" if len(CJK.findall(t)) > max(20, len(t) * 0.02) else "en"


# ------------------------------------------------------------------ 环境与输入
def resolve(a):
    """定位输入/产物/工作目录；不可写则退到 CWD 下同名目录。"""
    ind = Path(a.input or "/input")
    if not ind.is_dir():
        ind = next((Path(c) for c in ("input", "./input", "/app/input") if Path(c).is_dir()), ind)
    out, work = Path(a.output or "/app/output"), Path(a.work or "/app/work")
    for name, p in (("out", out), ("work", work)):
        try:
            p.mkdir(parents=True, exist_ok=True)
            t = p / ".probe"
            t.write_text("x", "utf-8")
            t.unlink()
            res = p
        except Exception:
            res = Path.cwd() / name
            try:
                res.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        if name == "out":
            out = res
        else:
            work = res
    return ind, out, work


def prepare(a):
    """读 case.json / task.md / 全部材料 / 题录，返回上下文；不写盘。"""
    t0 = time.time()
    ind, out, work = resolve(a)
    errs, degs, case, cpath = [], [], {}, None
    for c in [ind / "case.json"] + sorted(ind.glob("*case*.json")):
        if c.is_file():
            j = read_json(c)
            if isinstance(j, dict):
                case, cpath = j, c
                break
            errs.append({"stage": "input", "type": "case_json_invalid", "detail": "%s 不是 JSON 对象" % c.name})
    if not case:
        errs.append({"stage": "input", "type": "no_case_json", "detail": "未找到可解析的 case.json；按最小兜底继续"})
    con = case.get("output_contract") or case.get("outputs") or case.get("deliverables") or {}
    if isinstance(con, list):
        con = {str(k): "" for k in con}
    if not isinstance(con, dict):
        con = {}
    cid = str(case.get("case_id") or case.get("id") or "UNKNOWN")
    instr = " ".join(str(case.get(k) or "") for k in
                     ("task_instruction", "instruction", "task", "prompt", "goal", "research_question", "question"))
    tp = next((p for p in (ind / "task.md", ind / "task.txt") if p.is_file()), None)
    task = tp.read_text(encoding="utf-8", errors="replace") if tp else ""
    docs = discover(ind, case) if ind.is_dir() else []
    segment(docs)
    records = load_records(ind, case, docs) if ind.is_dir() else []
    for d in docs:
        if d["note"]:
            degs.append({"stage": "extract", "source_id": d["sid"], "type": "extraction_note",
                         "detail": "%s: %s" % (d["path"], d["note"])})
        if not (d["text"] or "").strip():
            degs.append({"stage": "extract", "source_id": d["sid"], "type": "no_text",
                         "detail": "%s 无可抽文本（%s）" % (d["path"], d["method"])})
    lg = detect_lang(" ".join((d["text"] or "")[:2000] for d in docs) + instr + task)
    rq = (case.get("research_question") or case.get("question") or case.get("rq") or case.get("topic")
          or case.get("title") or "")
    if not rq:
        m = re.search(r"(?m)^#+\s*(.+)$", task)
        rq = m.group(1).strip()[:200] if m else ""
    return {"ind": ind, "out": out, "work": work, "case": case, "case_path": str(cpath or ""), "con": con,
            "cid": cid, "instr": instr[:4000], "task": task, "docs": docs, "records": records,
            "units": [u for d in docs for u in d["units"]],
            "dmap": {d["sid"]: d for d in docs if d["sid"]}, "lg": lg, "rq": str(rq)[:300],
            "errs": errs, "degs": degs, "t0": t0,
            "sources": [{"source_id": d["sid"], "path": d["path"], "kind": d["kind"], "bytes": d["bytes"],
                         "sha256": (d["sha256"] or "")[:16], "read_method": d["method"],
                         "abstract_only": d["abstract_only"], "chars": len(d["text"] or ""),
                         "sentences": len(d["units"]), "meta": d["meta"]} for d in docs]}


def contract_default(k):
    return [] if re.search(r"(evidence|criteri|screen|slot|gap|outline|source|list|rows|matrix|record|"
                           r"uncertaint|conflict|item|log)", k.lower()) else None


def blank_result(ctx):
    """合法的最小 result.json：契约字段全在（缺值 null/[]）+ 信封字段。"""
    r = {}
    for k in ctx["con"]:
        r[k] = contract_default(k)
    r.update({"case_id": ctx["cid"], "status": "partial", "skill": SKILL, "skill_version": V,
              "contract_map": {}, "artifacts": {}, "sources": ctx["sources"], "errors": ctx["errs"],
              "degradations": ctx["degs"], "uncertainty": ["尚未构建：仅写入初始终止状态"], "changes": [],
              "metrics": {}, "runtime": {"stage": "init"}})
    return r


def scaffold(ctx):
    """init 的工作稿脚手架：筛选项已列出（decision=pending），结构与内容留空由 Agent 填。"""
    if ctx["records"]:
        rows = [{"record_id": r["record_id"], "source_id": r["source_id"], "stage": "title_abstract",
                 "decision": "pending", "criterion_ids": [], "reason": "", "locator": ""} for r in ctx["records"]]
    else:
        rows = [{"record_id": "R%02d" % i, "source_id": d["sid"], "stage": "title_abstract", "decision": "pending",
                 "criterion_ids": [], "reason": "", "locator": ""}
                for i, d in enumerate([x for x in ctx["docs"] if x["kind"] == "source"], 1)]
    return {"_scaffold": True,
            "_readme": "init 脚手架：按 SKILL.md 第 5、6 节填写 criteria/screening/outline/slots 后覆盖保存，"
                       "再跑 check、build；删 _scaffold 键或置 false 表示已填写。",
            "case_id": ctx["cid"], "research_question": ctx["rq"],
            "protocol": {"scope": "", "time_window": "", "languages": [], "criteria_frozen": False, "amendments": []},
            "outline_basis": "", "criteria": [], "screening": rows, "outline": [], "slots": [],
            "method_notes": {"strength_rule": "", "render_rule": "", "theme_rule": ""}}


def fail_result(out, e):
    """致命异常兜底：仍写合法 partial result.json。"""
    try:
        o = Path(out)
        o.mkdir(parents=True, exist_ok=True)
        p = o / "result.json"
        cur = read_json(p, {}) or {}
        if not isinstance(cur, dict):
            cur = {}
        cur.setdefault("case_id", "UNKNOWN")
        cur["status"] = "partial"
        for k in ("sources", "errors", "degradations", "uncertainty", "changes"):
            cur.setdefault(k, [])
        cur["errors"] = list(cur.get("errors") or []) + [{"stage": "fatal", "type": type(e).__name__,
                                                          "detail": str(e)[:300]}]
        write_json(p, cur)
    except Exception:
        pass


# ------------------------------------------------------------------ 文档解析
def _zip_text(p, pat):
    out = []
    try:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if re.search(pat, n):
                    x = z.read(n).decode("utf-8", "ignore")
                    out.append(unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", " ", x)))
    except Exception:
        return ""
    return "\n".join(out)


def _pdf_std(raw):
    """无 pdftotext/pypdf 时的近似抽取：解压内容流里的 (...)Tj / [...]TJ 文本块。"""
    buf = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            d = zlib.decompress(m.group(1))
        except Exception:
            continue
        if b"Tj" not in d and b"TJ" not in d:
            continue
        for mm in re.finditer(rb"\((?:\\.|[^\\()])*\)", d):
            t = re.sub(rb"\\([()\\])", rb"\1", mm.group(0)[1:-1])
            try:
                buf.append(t.decode("utf-8"))
            except Exception:
                buf.append(t.decode("latin-1", "ignore"))
        buf.append("\n")
    return " ".join(buf)


def read_doc(p):
    """-> (text, method, note)"""
    p = Path(p)
    e = p.suffix.lower()
    try:
        if e == ".pdf":
            exe = shutil.which("pdftotext")
            if exe:
                try:
                    r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"],
                                       capture_output=True, timeout=120)
                    if r.returncode == 0 and r.stdout.strip():
                        return r.stdout.decode("utf-8", "ignore"), "pdftotext", ""
                except Exception:
                    pass
            for m in ("pypdf", "PyPDF2"):
                try:
                    t = "\n".join((g.extract_text() or "") for g in
                                  getattr(__import__(m), "PdfReader")(str(p)).pages)
                    if t.strip():
                        return t, m, ""
                except Exception:
                    continue
            try:
                t = _pdf_std(p.read_bytes())
                if t.strip():
                    return t, "std-miniz", "PDF 未装 pdftotext/pypdf：内置流解压近似抽取，版式不可靠，引文须回原文复核"
            except Exception:
                pass
            return "", "none", "PDF 无可用文本层（疑扫描件或加密），需 OCR / 渲染后人工转录"
        if e == ".docx":
            return _zip_text(p, r"^word/document\.xml$"), "ooxml", ""
        if e in (".xlsx", ".xlsm"):
            return _zip_text(p, r"^xl/(sharedStrings|worksheets)/.*\.xml$"), "ooxml", ""
        if e == ".pptx":
            return _zip_text(p, r"^ppt/slides/slide\d+\.xml$"), "ooxml", ""
        if e == ".doc":
            return "", "unsupported", "旧版 .doc 无法离线解析，请转 .docx 或 .txt"
        if e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"):
            return "", "image", "图像材料需视觉读取；本 Skill 不做 OCR，请另转文本"
        t = p.read_text(encoding="utf-8", errors="ignore")
        if e in (".html", ".htm", ".xml"):
            t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
            t = re.sub(r"<[^>]+>", " ", t)
        return t, "text", ""
    except Exception as ex:
        return "", "error", "%s: %s" % (type(ex).__name__, str(ex)[:160])


def meta_of(text, path):
    head = "\n".join((text or "").splitlines()[:30])
    title = None
    m = re.search(r"(?im)^\s*(?:title|标题)\s*[:：]\s*(.+)$", head)
    if m:
        title = m.group(1).strip()[:200]
    else:
        for line in (text or "").splitlines():
            s = line.strip().lstrip("#").strip()
            if 12 <= len(s) <= 220 and not ABS.match(s) and not re.match(r"(?i)(keywords|关键词|doi|http)", s):
                title = s
                break
    ym = re.search(r"\b(19|20)\d{2}\b", head) or re.search(r"\b(19|20)\d{2}\b", (text or "")[:2500])
    dm = DOI.search((text or "")[:5000])
    return {"title": title, "year": ym.group(0) if ym else None, "doi": dm.group(0) if dm else None}


def abstract_only(p, text):
    n = p.name.lower()
    low = (text or "")[:1800]
    if re.search(r"(?i)(仅摘|only (the )?abstract|no full ?text|abstract[- _]?only)", low):
        return True
    if "abstract" in n and len(text or "") < 6000:
        return True
    return len(text or "") < 3200 and bool(ABS.search(low)) and not re.search(
        r"(?i)(method|方法|participants|受试者|results|结果)", text or "")


def kind_of(name, text):
    n = name.lower()
    if re.search(r"(protocol|prisma|search[-_ ]?strategy|检索式|检索方案|纳排)", n):
        return "protocol"
    if n.endswith(".jsonl") or re.search(r"(records|record[-_]?list|题录|文献表|corpus)", n):
        return "records"
    if re.search(r"(readme|license|changelog)", n):
        return "other"
    return "source"


def discover(ind, case):
    """遍历输入目录，给每份材料一个 source_id（S=文献 P=方案 L=题录 X=其他）。"""
    docs, seen = [], set()
    for p in sorted(Path(ind).rglob("*")):
        if not p.is_file() or p.name in SKIPNAME:
            continue
        rel = str(p.relative_to(ind))
        if "__pycache__" in rel or p.suffix.lower() in (".pyc", ".log"):
            continue
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp in seen:
            continue
        seen.add(rp)
        text, meth, note = read_doc(p)
        docs.append({"sid": "", "path": rel, "kind": kind_of(p.name, text), "text": text, "method": meth,
                     "note": note, "bytes": p.stat().st_size, "sha256": sha256(p),
                     "meta": meta_of(text, p), "abstract_only": abstract_only(p, text), "units": []})
    for pre, kind in (("S", "source"), ("P", "protocol"), ("L", "records"), ("X", "other")):
        for i, d in enumerate([x for x in docs if x["kind"] == kind], 1):
            d["sid"] = "%s%02d" % (pre, i)
    return docs


# ------------------------------------------------------------------ 题录与去重
RID = ("record_id", "rid", "id", "key", "uid", "编号")
TTL = ("title", "标题", "name", "heading")
YR = ("year", "pub_year", "年", "publication_year", "date")
DOIK = ("doi", "DOI", "identifier")
AU = ("authors", "author", "作者")


def _pick(d, keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def load_records(ind, case, docs):
    """题录来源：case 内的列表键、*.jsonl、*.csv、非 case 的 *.json；随后去重并链接到文献文件。"""
    raw = []
    for k in ("records", "items", "studies", "literature", "papers", "documents", "references"):
        v = case.get(k)
        if isinstance(v, list):
            raw += [("case." + k, x) for x in v]
        elif isinstance(v, str) and v.strip()[:1] in "[{":
            try:
                j = json.loads(v)
                raw += [("case." + k, x) for x in (j if isinstance(j, list) else [j])]
            except Exception:
                pass
    for p in sorted(Path(ind).rglob("*")):
        if not p.is_file():
            continue
        e = p.suffix.lower()
        if e == ".jsonl":
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    raw.append((p.name, json.loads(line)))
                except Exception:
                    continue
        elif e == ".csv":
            try:
                with open(p, encoding="utf-8", errors="ignore", newline="") as f:
                    raw += [(p.name, dict(r)) for r in csv.DictReader(f)]
            except Exception:
                pass
        elif e == ".json" and p.name != "case.json":
            o = read_json(p)
            if isinstance(o, list):
                raw += [(p.name, x) for x in o]
            elif isinstance(o, dict):
                for k in ("records", "items", "studies"):
                    if isinstance(o.get(k), list):
                        raw += [(p.name, x) for x in o[k]]
    recs = []
    for src, o in raw:
        o = {"title": o} if isinstance(o, str) else o
        if not isinstance(o, dict):
            continue
        title, doi = _pick(o, TTL), _pick(o, DOIK)
        if not (title or doi):
            continue
        rid = _pick(o, RID)
        recs.append({"record_id": str(rid) if rid else "", "title": str(title).strip()[:300] if title else "",
                     "year": str(_pick(o, YR) or "")[:4] or None, "doi": str(doi).strip() if doi else None,
                     "authors": str(_pick(o, AU) or "")[:200], "origin": src, "source_id": None,
                     "duplicate_of": None, "note": ""})
    for i, r in enumerate(recs, 1):
        r["record_id"] = r["record_id"] or "R%02d" % i
    for i, r in enumerate(recs):
        for o in recs[:i]:
            same = r["doi"] and o["doi"] and nq(r["doi"]).lower() == nq(o["doi"]).lower()
            if not same and r["title"] and o["title"]:
                same = SequenceMatcher(None, nq(r["title"]).lower(), nq(o["title"]).lower()).ratio() >= 0.94
            if same:
                r["duplicate_of"] = o["record_id"]
                r["note"] = "重复记录：与 %s 同源" % o["record_id"]
                break
    for r in recs:
        best = (0.0, None)
        for d in [x for x in docs if x["kind"] == "source"]:
            sc = 0.0
            if r["doi"] and r["doi"].lower() in (d["text"] or "").lower():
                sc = 1.0
            elif r["title"] and d["meta"].get("title"):
                sc = SequenceMatcher(None, nq(r["title"]).lower(), nq(d["meta"]["title"]).lower()).ratio()
            if r["title"] and Path(d["path"]).stem and Path(d["path"]).stem.lower() in nq(r["title"]).lower():
                sc = max(sc, 0.9)
            if sc > best[0]:
                best = (sc, d["sid"])
        r["source_id"] = best[1] if best[0] >= 0.62 else None
        if not r["source_id"]:
            r["note"] = (r["note"] + "；" if r["note"] else "") + "未在材料中定位到对应文献文件"
    return recs


# ------------------------------------------------------------------ 定位切分
def sents(t):
    out = []
    for raw in re.split(r"(?<=[\u3002\uff01\uff1f!?])", t or ""):
        for s in re.split(r"(?<=\.)\s+(?=[A-Z0-9\"\u201c(\[]|[\u4e00-\u9fff])", raw):
            s = s.strip()
            if len(s) > 1:
                out.append(s)
    return out


def segment(docs):
    """块→句切分，每句带可回查 locator：<path>#B<块>S<句>@<start>-<end>。"""
    for d in docs:
        t = (d.get("text") or "").replace("\r\n", "\n")
        d["units"] = []
        if not t.strip():
            continue
        bi = 0
        for m in re.finditer(r"[^\n]+(?:\n(?![ \t]*\n)[^\n]+)*", t):
            blk, bstart = m.group(0), m.start()
            bi += 1
            off = bstart
            head = bool(re.match(r"^\s*#{1,6}\s", blk))
            for si, s in enumerate(sents(blk), 1):
                if re.match(r"^\s*\|?\s*:?-{3,}", s) or re.match(r"^\s*([-=*_]\s*){3,}$", s):
                    continue
                q = t.find(s, off)
                q = off if q < 0 else q
                off = q + len(s)
                d["units"].append({"uid": "%s#B%dS%d" % (d["sid"] or d["path"], bi, si), "sid": d["sid"],
                                   "doc": d["path"], "bi": bi, "si": si, "text": s, "heading": head,
                                   "loc": "%s#B%dS%d@%d-%d" % (d["path"], bi, si, q, q + len(s)),
                                   "start": q, "end": q + len(s)})
    return docs


def best_unit(nqs, units, thr=1.0):
    best, bs = None, -1.0
    for u in units:
        nu = nq(u["text"])
        if not nu:
            continue
        if thr >= 1.0:
            if nqs in nu and (best is None or len(u["text"]) < len(best["text"])):
                best = u
        else:
            if abs(len(nu) - len(nqs)) > max(40, len(nqs)):
                continue
            r = SequenceMatcher(None, nqs, nu).ratio()
            if r > bs:
                best, bs = u, r
    if thr >= 1.0:
        return best
    return best if (best is not None and bs >= thr) else None


def find_quote(q, doc):
    """-> (status, unit)。status: exact|normalized|fuzzy|miss|empty。"""
    if not (q or "").strip():
        return "empty", None
    t = doc.get("text") or ""
    if q in t:
        return "exact", next((x for x in doc.get("units", []) if q in x["text"]), None)
    n = nq(q)
    if not n:
        return "empty", None
    if n in nq(t):
        return "normalized", best_unit(n, doc.get("units", []))
    u = best_unit(n, doc.get("units", []), thr=0.86)
    return ("fuzzy", u) if u else ("miss", None)


# ------------------------------------------------------------------ 强度判据
DES = [(r"(systematic review|meta-?analys|系统评价|系统综述|荟萃)", "systematic_review", 3.0),
       (r"(guideline|consensus statement|指南|共识)", "guideline", 3.0),
       (r"(\bRCT\b|randomi[sz]ed|随机对照)", "rct", 3.0),
       (r"(cohort|prospective|longitudinal|队列|前瞻|纵向)", "cohort", 2.0),
       (r"(case-?control|病例对照)", "case_control", 2.0),
       (r"(cross-?sectional|survey|横断面|现况调查)", "cross_sectional", 1.5),
       (r"(case report|case series|病例报告|个案)", "case_report", 0.5),
       (r"(preprint|bioRxiv|medRxiv|arXiv|预印本)", "preprint", 1.0),
       (r"(\breview\b|综述)", "narrative_review", 1.0),
       (r"(in vitro|cell line|mice|mouse|rats?\b|体外|细胞系|小鼠|大鼠)", "preclinical", 1.0)]


def design_of(text):
    for pat, name, pts in DES:
        if re.search(pat, text or "", re.I):
            return name, pts
    return "unspecified", 1.0


def strength_hint(refs, docs, conflict=False):
    """判据：最佳设计分 + 独立来源加分 − 冲突扣分；仅摘要/预印本封顶 moderate。"""
    by = {d["sid"]: d for d in docs}
    best, bestn, sids, absq, pre = 1.0, "unspecified", set(), False, False
    for r in refs or []:
        d = by.get(r.get("source_id"))
        if not d:
            continue
        sids.add(d["sid"])
        n, p = design_of((r.get("quote") or "") + " " + (d.get("text") or "")[:600])
        if p > best:
            best, bestn = p, n
        absq = absq or bool(d.get("abstract_only"))
        pre = pre or n == "preprint"
    score = best + (1.0 if len(sids) >= 2 else 0.0) - (1.0 if conflict else 0.0)
    cap = 2.4 if (absq or pre) else None
    sc = min(score, cap) if cap else score
    lv = "strong" if sc >= 3.8 else "moderate" if sc >= 1.8 else "weak"
    return lv, {"design": bestn, "design_pts": best, "distinct_sources": len(sids), "conflict": bool(conflict),
                "abstract_only": absq, "capped": bool(cap), "score": round(sc, 2)}


# ------------------------------------------------------------------ 语料与套话
HEDGE = {"strong": ("多项证据一致表明", "Evidence consistently indicates that"),
         "moderate": ("现有研究提示", "Studies suggest that"),
         "weak": ("初步证据提示", "Preliminary evidence suggests")}
HEDGED = re.compile(r"(?i)(可能|提示|初步|尚|倾向于|或许|may|might|suggest|preliminary|appears|likely|indicates)")
COUNTER = {"zh": "与此相反，", "en": "By contrast, "}
COUNTEREX = re.compile(r"(?i)^(然而|但是|相反|与此相反|另一方面|however|by contrast|in contrast|conversely)")
CLICHE = [r"未来研究(应|需要|可)(进一步)?(深入)?(探讨|研究|探索|验证)", r"有待进一步(的)?(研究|探讨|验证)",
          r"亟需(更多|进一步)(的)?研究", r"具有(重要|较大)的?(理论|实践|临床)(意义|价值)", r"综上所述",
          r"日益受到(广泛)?关注", r"(?i)further (research|studies|work) (is|are) (needed|required|warranted)",
          r"(?i)future (studies|research) should", r"(?i)more research is needed",
          r"(?i)plays? an important role", r"(?i)is of great significance",
          r"(?i)growing (attention|interest) (has been|is being) paid"]
CLICHE_RE = [re.compile(p) for p in CLICHE]


def cliche_hits(text):
    return sorted({m.group(0) for r in CLICHE_RE for m in r.finditer(text or "")})


def render_claim(claim, strength, sids, lg, polarity="supports", hedge=True):
    """一句实质论断 = 强度限定语 + 论断 + 引用标记；同段同强度不重复限定语。"""
    t = (claim or "").strip()
    if not t:
        return ""
    hz, he = HEDGE.get(strength, HEDGE["weak"])
    if hedge and not HEDGED.search(t):
        t = (hz if lg == "zh" else he) + ("，" if lg == "zh" else " ") + t
    if polarity == "counter" and not COUNTEREX.search(t):
        t = COUNTER[lg] + (t[0].lower() + t[1:] if lg != "zh" and t[:1].isupper() else t)
    t = re.sub(r"[\s，,；;。.]+$", "", t)
    return t + "".join("[%s]" % s for s in sids) + ("。" if lg == "zh" else ".")


def source_line(d):
    m = d.get("meta") or {}
    bits = [d["sid"], m.get("title") or "(材料未给标题)", m.get("year") or "年缺"]
    if m.get("doi"):
        bits.append("doi:" + m["doi"])
    bits.append(d["path"])
    return " | ".join(str(b) for b in bits)
