"""core.py - discovery, index assembly, contract backfill, quote location, verification."""
import hashlib
import json
import os
import re
import time
from pathlib import Path
import extract as EX
import rules as RU
BANNED_RE = re.compile(
    r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未|"
    r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b|\bNOT_EXTRACTED\b|"
    r"\bnot[-_ ]?extracted\b|\bpending\b|\bnull\b|\bNone\b|\bN/?A\b|"
    r"^[ \t]*\.\.\.[ \t]*$|<[A-Za-z_][\w /-]*>|example\.com|lorem ipsum|"
    r"^(?:string|path|array|object|number|boolean|value|待填写|示例)$",
    re.IGNORECASE | re.MULTILINE)
def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if o is None:
        return ""
    return o
def esc_text(t, rounds=4):
    for _r in range(rounds):
        out, last = [], 0
        for m in BANNED_RE.finditer(t):
            tok = m.group(0)
            if not tok:
                continue
            out.append(t[last:m.start()])
            out.append("\\u%04x%s" % (ord(tok[0]), tok[1:]))
            last = m.end()
        if not out:
            return t
        out.append(t[last:])
        t = "".join(out)
    return t
def scrub(o):
    return esc_text(json.dumps(clean(o), ensure_ascii=False, indent=2, default=str))
def wtext(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(esc_text(text), encoding="utf-8")
    return p
SKIP_DIRS = {"__pycache__", ".git", ".svn", "node_modules", ".ipynb_checkpoints"}
SCOREISH = re.compile(r"(?i)(rubric|gold|expected|answer[_-]?key|solution|verifier|scoring|grading|"
                      r"whiteboard|白板|评分|答案)")
SKIP_FILES = {"case.json", "task.md", "task_instruction.md"}
MAX_BYTES = 40 * 1024 * 1024
STATE = {"errors": [], "degradations": [], "changes": [], "uncertainties": [], "pending": []}
def err(stage, exc=None, **kw):
    row = {"stage": stage}
    row.update(kw)
    if exc is not None:
        row["error"] = f"{type(exc).__name__}: {exc}"
    STATE["errors"].append(row)
    return row
def degrade(item, reason, impact=""):
    STATE["degradations"].append({"item": item, "reason": reason, "impact": impact})
def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")
def jdump(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(scrub(obj), encoding="utf-8")
    tmp.replace(p)
    return p
def log_line(work, cmd, msg):
    try:
        p = Path(work) / "run.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write("%s\t%s\t%s\n" % (now(), cmd, msg))
    except Exception:  # noqa: BLE001
        pass
def jload(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return default
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()
def norm_ws(s):
    s = str(s or "").replace(" ", " ").replace("　", " ")
    s = re.sub(r"[‘’“”]", '"', s)
    s = re.sub(r"[‐‑‒–—]", "-", s)
    return re.sub(r"\s+", " ", s).strip()
def squash(s):
    return re.sub(r"[\s\-_]+", "", norm_ws(s)).lower()
def find_case(inp, case_arg=None):
    errs = []
    cands = ([Path(case_arg)] if case_arg else []) + [Path(inp) / "case.json"]
    for c in cands:
        if c.is_file():
            try:
                obj = json.loads(c.read_text(encoding="utf-8", errors="replace"))
                if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                    obj = obj[0]
                if isinstance(obj, dict):
                    return obj, c, errs
                errs.append({"stage": "load_case", "path": str(c), "error": "not a JSON object"})
            except Exception as e:  # noqa: BLE001
                errs.append({"stage": "load_case", "path": str(c), "error": f"{type(e).__name__}: {e}"})
    try:
        for p in sorted(Path(inp).rglob("*.json")):
            try:
                if len(p.relative_to(inp).parts) > 4 or SCOREISH.search(p.name):
                    continue
            except ValueError:
                continue
            obj = jload(p)
            if isinstance(obj, dict) and any(str(k).lower() in
                                             {"case_id", "output_contract", "task_instruction"}
                                             for k in obj):
                errs.append({"stage": "load_case", "path": str(p),
                             "error": "case.json unusable; fallback case file used"})
                return obj, p, errs
    except Exception as e:  # noqa: BLE001
        errs.append({"stage": "load_case", "error": f"{type(e).__name__}: {e}"})
    return {}, None, errs
META_CASE = ("case_id", "caseid", "case_key", "id", "case")
META_CONTRACT = ("output_contract", "outputcontract", "output_contracts", "contract", "输出契约")
META_TASK = ("task_instruction", "instruction", "task", "prompt", "requirement", "任务说明")
def build_meta(case, case_path=None):
    return {"case_id": RU.lk(case, META_CASE) or (Path(case_path).stem if case_path else None),
            "output_contract": RU.lk(case, META_CONTRACT) or {},
            "task_instruction": RU.lk(case, META_TASK) or "",
            "material_version": RU.lk(case, ("material_version", "materialversion", "library_version",
                                             "dataset_version", "version"))}
def read_task_md(inp):
    for cand in (Path(inp) / "task.md", Path(inp) / "TASK.md", Path(inp) / "task_instruction.md"):
        try:
            if cand.is_file():
                return cand.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
    return ""
QID = ("query_id", "qid", "id", "no", "编号", "index", "key")
QTXT = ("question", "query", "q", "text", "request", "search", "prompt", "问题", "提问",
        "检索问题", "target", "description")
QLIST = ("queries", "searches", "questions", "search_requests", "requests", "qas", "search_tasks",
         "检索请求", "问题清单", "tasks")
QFILTER = ("filters", "filter", "constraints", "conditions", "过滤", "过滤条件")
def find_queries(case):
    raw = RU.lk(case, QLIST)
    if raw is None:
        for k, v in (case or {}).items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and any(
                    str(kk).lower() in QTXT for kk in v[0]):
                raw = v
                break
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [dict(v, query_id=k) if isinstance(v, dict) else {"query_id": k, "question": str(v)}
               for k, v in raw.items()]
    out = []
    for i, item in enumerate(raw if isinstance(raw, list) else [raw], 1):
        if isinstance(item, str):
            if item.strip():
                out.append({"query_id": f"Q{i}", "question": item.strip(), "filters_raw": None})
            continue
        if not isinstance(item, dict):
            continue
        q = RU.lk(item, QTXT) or ""
        if isinstance(q, list):
            q = " ".join(str(x) for x in q)
        if not str(q).strip():
            continue
        out.append({"query_id": str(RU.lk(item, QID) or f"Q{i}"), "question": str(q).strip(),
                    "filters_raw": RU.lk(item, QFILTER)})
    return out
LIB_KEYS = ("library_root", "library", "corpus_root", "materials_root", "doc_root", "files_root",
            "data_root", "文档库", "材料目录", "root")
DOC_KEYS = ("documents", "docs", "files", "library", "materials", "file_list", "corpus",
            "资料清单", "document_list", "items", "entries")
D_PATH = ("path", "file", "filepath", "file_path", "rel_path", "relative_path", "location", "uri",
          "filename", "name", "路径", "文件")
D_VER = ("version", "ver", "rev", "revision", "版本", "edition")
D_ALIAS = ("aliases", "alias", "aka", "other_names", "别名", "synonyms", "formerly")
D_PERM = ("permission", "access", "acl", "readable", "权限", "visibility")
D_ID = ("doc_id", "document_id", "id", "docid", "file_id", "编号")
def declared_docs(case):
    raw = RU.lk(case, DOC_KEYS)
    if raw is None:
        return []
    if isinstance(raw, dict):
        items = []
        for k, v in raw.items():
            if isinstance(v, dict):
                items.append(dict(v, **{"doc_id": v.get("doc_id") or v.get("id") or k}))
            elif isinstance(v, str):
                items.append({"doc_id": k, "path": v})
        return items
    out = []
    for i, item in enumerate(raw if isinstance(raw, list) else [raw]):
        if isinstance(item, str):
            out.append({"path": item, "doc_id": f"D{i+1}"})
        elif isinstance(item, dict):
            out.append(item)
    return out
def find_library_root(case, inp):
    inp = Path(inp)
    cand = RU.lk(case, LIB_KEYS)
    if isinstance(cand, str) and cand:
        for base in (inp, inp.parent, Path("/input")):
            p = Path(cand) if os.path.isabs(cand) else (base / cand)
            if p.is_dir():
                return p, f"case:{cand}"
    for name in ("library", "artifacts", "files", "materials", "corpus", "docs", "documents"):
        p = inp / name
        if p.is_dir():
            return p, f"input/{name}"
    if inp.is_dir():
        return inp, "input_root"
    return None, "missing"
def scan_files(root, max_files=400, max_depth=8):
    out = []
    root = Path(root)
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        try:
            depth = len(Path(dirpath).relative_to(root).parts)
        except ValueError:
            depth = 0
        if depth >= max_depth:
            dirnames[:] = []
        for fn in sorted(filenames):
            if fn.startswith(".") or fn.lower() in SKIP_FILES or fn.lower().endswith((".pyc", ".tmp")):
                continue
            if SCOREISH.search(fn):
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                pass
            out.append(p)
            if len(out) >= max_files:
                return out
    return out
def build_structure(units, doc_id):
    paras, sections, cur = [], [], None
    for u in units:
        if u.get("kind") == "heading":
            cur = {"section_id": f"{doc_id}-s{len(sections) + 1}", "title": u["text"].strip(),
                   "level": int(u.get("level") or 1), "page_physical": u.get("page_physical"),
                   "page_printed": u.get("page_printed"), "container": u.get("container")}
            sections.append(cur)
        elif cur is None:
            cur = {"section_id": f"{doc_id}-s1", "title": "[preamble]", "level": 0,
                   "page_physical": u.get("page_physical"), "page_printed": u.get("page_printed"),
                   "container": u.get("container")}
            sections.append(cur)
        pid = f"{doc_id}-p{len(paras) + 1}"
        src = {"table": "table", "caption": "figure_caption", "reference": "reference"}.get(
            u.get("kind"), "body")
        if re.search(r"附录|appendix|supplement|补充材料", (cur.get("title") or "").lower()):
            src = "appendix"
        paras.append({"pid": pid, "doc_id": doc_id, "section_id": cur["section_id"],
                      "section": cur["title"], "text": u["text"], "kind": u.get("kind"),
                      "source": src, "page_physical": u.get("page_physical"),
                      "page_printed": u.get("page_printed"), "container": u.get("container")})
    for s in sections:
        s["paragraph_ids"] = [p["pid"] for p in paras if p["section_id"] == s["section_id"]]
    return sections, paras
def index_doc(path, rel, doc_id, decl, root, inp=None):
    rel_in = rel
    if inp is not None:
        try:
            rel_in = Path(path).relative_to(Path(inp)).as_posix()
        except ValueError:
            rel_in = rel
    rec = {"doc_id": doc_id, "path": rel.replace("\\", "/"), "path_input": rel_in.replace("\\", "/"),
           "path_abs": str(path),
           "declared": bool(decl), "type": EX.kind_of(path),
           "ext": Path(path).suffix.lower().lstrip("."), "aliases": [], "permission": "read",
           "status": "ok", "notes": [], "version": None,
           "pages": {"count": None, "label_source": "not_applicable", "page_offset": None},
           "sections": [], "paragraphs": [], "sha256": None, "sha256_16": None,
           "bytes": None, "text_chars": 0, "meta": {}}
    if decl:
        al = RU.lk(decl, D_ALIAS)
        if isinstance(al, str):
            al = [x.strip() for x in re.split(r"[;,、]", al) if x.strip()]
        rec["aliases"] = [str(x) for x in (al or []) if x]
        perm = RU.lk(decl, D_PERM)
        if perm is not None:
            rec["permission"] = "denied" if str(perm).lower() in (
                "denied", "none", "no", "false", "restricted", "无权", "受限",
                "hidden") else str(perm)
        v = RU.lk(decl, D_VER)
        if v:
            rec["version"] = str(v)
    rec["meta"] = RU.merge_declared(decl or {}, rel)
    if not rec["version"]:
        rec["version"] = rec["meta"].get("version")
    try:
        st = path.stat()
        rec["bytes"] = st.st_size
        rec["mtime_year"] = time.gmtime(st.st_mtime).tm_year
    except OSError:
        pass
    if rec["permission"] in ("denied", "restricted"):
        rec["status"] = "permission_denied"
        rec["notes"].append("declared permission denies content read; not parsed")
        try:
            rec["bytes"] = path.stat().st_size
            rec["sha256"] = sha256_bytes(path.read_bytes())
            rec["sha256_16"] = rec["sha256"][:16]
        except Exception:  # noqa: BLE001
            pass
        return rec
    ex = EX.extract(path, doc_id)
    rec["status"] = ex["status"]
    rec["notes"].extend((ex.get("notes") or [])[:4])
    rec["pages"] = ex.get("pages") or rec["pages"]
    rec["encoding"] = ex.get("encoding")
    try:
        rec["sha256"] = sha256_bytes(path.read_bytes())
        rec["sha256_16"] = rec["sha256"][:16]
    except Exception:  # noqa: BLE001
        pass
    if ex["status"] in ("ok", "low_text_quality") and ex.get("units"):
        sections, paras = build_structure(ex["units"], doc_id)
        rec["sections"], rec["paragraphs"] = sections, paras
        rec["text_chars"] = sum(len(p["text"]) for p in paras)
        if not paras:
            rec["status"] = "no_text_layer"
            rec["notes"].append("no paragraphs after structure build")
    return rec
FAIL_IMPACT = {
    "permission_denied": "不做内容检索，仅登记存在与权限",
    "encrypted": "无法解密，内容不可检索",
    "no_text_layer": "无文本层（扫描件/图片），需 OCR；本 Skill 不做 OCR",
    "low_text_quality": "文本层解码质量过低，按不可检索处理",
    "corrupt": "解析失败，内容不可检索",
    "empty_file": "空文件",
    "path_missing": "路径失效，文档未入库",
    "unsupported_legacy": "旧版二进制 Office 格式，需先转 OOXML",
}
def build_index(meta, case, inp):
    inp = Path(inp)
    root, how = find_library_root(case, inp)
    decls = declared_docs(case)
    failures = []
    stats = {"library_root": str(root) if root else None, "root_source": how, "files_on_disk": 0,
             "declared": len(decls), "indexed": 0, "declared_missing": 0}
    found = [(p, p.relative_to(root).as_posix(), None) for p in scan_files(root)] if root else []
    stats["files_on_disk"] = len(found)
    seen = {os.path.realpath(str(f[0])): f for f in found}
    for d in decls:
        raw = RU.lk(d, D_PATH)
        if not raw:
            continue
        cand = None
        for base in ([root] if root else []) + [inp, Path("/input")]:
            p = Path(str(raw)) if os.path.isabs(str(raw)) else (Path(base) / str(raw))
            if p.is_file():
                cand = p
                break
        if cand is None:
            stats["declared_missing"] += 1
            failures.append({"doc_id": RU.lk(d, D_ID), "path": str(raw), "reason": "path_missing",
                             "detail": "case.json 声明了该文件但磁盘上找不到",
                             "impact": FAIL_IMPACT["path_missing"]})
            continue
        try:
            rel = cand.relative_to(root or inp).as_posix()
        except ValueError:
            try:
                rel = cand.relative_to(inp).as_posix()
            except ValueError:
                rel = str(raw)
        key = os.path.realpath(str(cand))
        seen[key] = (cand, rel, d)
    docs, used, done = [], set(), set()
    for i, (path, rel, decl) in enumerate(sorted(seen.values(), key=lambda x: (x[1].lower(), str(x[0]))), 1):
        key = os.path.realpath(str(path))
        if key in done:
            continue
        done.add(key)
        doc_id = str(RU.lk(decl, D_ID) or "") or f"D{i}"
        while doc_id in used:
            doc_id += "b"
        used.add(doc_id)
        try:
            rec = index_doc(path, rel, doc_id, decl, root, inp)
        except Exception as e:  # noqa: BLE001
            rec = {"doc_id": doc_id, "path": rel, "path_abs": str(path), "declared": bool(decl),
                   "type": EX.kind_of(path), "ext": Path(path).suffix.lower().lstrip("."),
                   "status": "corrupt", "notes": [f"{type(e).__name__}: {e}"], "sections": [],
                   "paragraphs": [], "meta": {}, "permission": "read", "version": None,
                   "pages": {"count": None, "label_source": "not_applicable", "page_offset": None}}
        if rec["status"] != "ok":
            failures.append({"doc_id": doc_id, "path": rec["path"], "reason": rec["status"],
                             "detail": "; ".join(rec.get("notes") or []) or rec["status"],
                             "impact": FAIL_IMPACT.get(rec["status"], "不可检索")})
        if rec.get("permission") in ("denied", "restricted"):
            failures.append({"doc_id": doc_id, "path": rec["path"], "reason": "permission_denied",
                             "detail": f"case.json 声明 permission={rec['permission']}",
                             "impact": "不读取内容；过滤后垒集须如实报告"})
        docs.append(rec)
    failures = list({(f.get("doc_id"), f.get("path"), f.get("reason")): f for f in failures}.values())
    groups, excluded, conflicts = RU.dedupe(docs)
    digest_src = "".join(sorted(f"{d.get('doc_id')}:{d.get('sha256') or '-'}" for d in docs))
    index = {"case_id": meta.get("case_id"), "built_at": now(),
             "library_root": str(root) if root else None, "root_source": how,
             "index_digest": sha256_bytes(digest_src.encode())[:16],
             "docs": docs, "dedupe": {"groups": groups, "conflicts": conflicts},
             "excluded_evidence": excluded, "failures": failures,
             "scan_stats": dict(stats, indexed=len(docs))}
    if root is None:
        failures.append({"reason": "library_missing", "path": str(inp),
                         "detail": "未找到材料目录", "impact": "空索引"})
    return index
def doc_by_path(index, path):
    if not path:
        return None
    raw = str(path).strip().replace("\\", "/").lstrip("./")
    name = os.path.basename(raw)
    docs = index.get("docs") or []
    for d in docs:
        if (d.get("path") or "").lstrip("./") == raw:
            return d
    for d in docs:
        if os.path.basename(d.get("path") or "").lower() == name.lower():
            return d
    sq = squash(raw)
    if sq:
        for d in docs:
            dp = squash(d.get("path") or "")
            if dp and (sq.endswith(dp) or dp.endswith(sq)):
                return d
    return None
def index_text(index):
    out = {}
    for d in index.get("docs") or []:
        out[d.get("doc_id")] = [(p.get("pid"), p.get("section_id"), p.get("section"),
                                 p.get("page_physical"), p.get("page_printed"), p.get("text") or "")
                                for p in d.get("paragraphs") or []]
    return out
DEFAULT_CONTRACT_KEYS = ("id", "root", "terminology", "aliases", "encoding", "not_applicable",
                         "container", "older_version_of", "evidence_ban", "impact")
def contract_keys(contract):
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    if isinstance(contract, (list, tuple)):
        out = []
        for it in contract:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                n = it.get("name") or it.get("key") or it.get("field") or it.get("id")
                if n:
                    out.append(str(n))
        return out
    return []
def _docs(index):
    return (index or {}).get("docs") or []
def contract_blocks(payload, contract, index=None):
    keys = contract_keys(contract) or list(DEFAULT_CONTRACT_KEYS)
    ix = index or {}
    docs = _docs(ix)
    res = payload.get("result") or {}
    st = ix.get("scan_stats") or {}
    ded = ix.get("dedupe") or {}
    blocks = {}
    def proj(key, rows, column, source, count=None):
        return {"source": source, "column": column, "field": key,
                "count": len(rows) if count is None else count, "rows": rows[:40]}
    def fid(d):
        return {"file_id": d.get("doc_id"), "path": d.get("path")}
    def pages(d):
        return d.get("pages") or {}
    for k in keys:
        if k == "id":
            blocks[k] = proj(k, [{"file_id": d.get("doc_id"), "value": d.get("doc_id"),
                                  "path": d.get("path"), "sha256_16": d.get("sha256_16")}
                                 for d in docs], "doc_id", "index.docs[].doc_id")
        elif k == "root":
            blocks[k] = {"source": "index.library_root / scan_stats", "field": k,
                         "root": ix.get("library_root"), "root_source": ix.get("root_source"),
                         "files_on_disk": st.get("files_on_disk"), "declared": st.get("declared"),
                         "indexed": st.get("indexed"), "rows": [fid(d) for d in docs]}
        elif k == "terminology":
            terms = []
            for t, variants in sorted(RU.SYN.items()):
                hits = [d.get("doc_id") for d in docs
                        if any(v.lower() in (p.get("text") or "").lower()
                               for p in (d.get("paragraphs") or [])[:400] for v in variants)]
                terms.append({"term": t, "variants": variants, "files": hits[:10],
                              "occurrences": len(hits)})
            extra = {}
            raw = payload.get("extra_terms")
            items = raw.items() if isinstance(raw, dict) else [
                (it.get("term"), it.get("variants")) for it in raw or [] if isinstance(it, dict)]
            for t, vs in items:
                if t:
                    extra[str(t)] = vs if isinstance(vs, list) else [vs]
            blocks[k] = {"source": "rules.SYN + case.json synonyms", "field": k,
                         "builtin_terms": len(RU.SYN), "case_terms": len(extra), "rows": terms}
        elif k == "aliases":
            rows = [dict(fid(d), aliases=d.get("aliases") or []) for d in docs if d.get("aliases")]
            blocks[k] = proj(k, rows, "aliases", "index.docs[].aliases",
                             count=sum(len(d.get("aliases") or []) for d in docs))
        elif k == "encoding":
            blocks[k] = proj(k, [dict(fid(d), encoding=d.get("encoding") or "not-detected",
                                      type=d.get("type"), status=d.get("status")) for d in docs],
                             "encoding", "index.docs[].encoding")
        elif k == "not_applicable":
            rows = [dict(fid(d), pages_label_source=pages(d).get("label_source"),
                         reason="no reliable pagination for this container type; "
                                "locate by section and paragraph instead")
                    for d in docs if pages(d).get("label_source") == "not_applicable"]
            blocks[k] = {"source": "index.docs[].pages.label_source", "field": k,
                         "declared_for": "page numbers of containers without fixed pages",
                         "count": len(rows), "rows": rows}
        elif k == "container":
            rows = [dict(fid(d), section_id=s.get("section_id"),
                         container=s.get("container") or d.get("type"),
                         title=s.get("title"), level=s.get("level"))
                    for d in docs for s in (d.get("sections") or [])[:40]]
            blocks[k] = proj(k, rows, "container", "index.docs[].sections[].container")
        elif k == "older_version_of":
            rows = [{"older": m.get("doc_id"), "value": g.get("representative"),
                     "version": m.get("version"), "similarity": g.get("similarity")}
                    for g in ded.get("groups") or [] if g.get("kind") == "version_chain"
                    for m in g.get("members") or [] if m.get("doc_id") != g.get("representative")]
            blocks[k] = proj(k, rows, "older_version_of",
                             "index.dedupe.groups[kind=version_chain].members")
        elif k == "evidence_ban":
            rows = ix.get("excluded_evidence") or []
            blocks[k] = proj(k, rows, "evidence_ban", "index.excluded_evidence[].evidence_ban")
        elif k == "impact":
            rows = ix.get("failures") or []
            blocks[k] = proj(k, rows, "impact", "index.failures[].impact",
                             count=len(res.get("failures") or rows))
        else:
            blocks[k] = {"computed": False, "field": k,
                         "reason": "the case declared this key but the index has no projection for it",
                         "requirement": "supply a projection source in core.contract_blocks",
                         "input": (payload.get("case_id"), ix.get("library_root"))}
    return blocks
def apply_contract(payload, contract, index=None):
    keys = contract_keys(contract) or list(DEFAULT_CONTRACT_KEYS)
    blocks = contract_blocks(payload, contract, index)
    out = dict(payload)
    for k in keys:
        out[k] = blocks.get(k)
    out["output_contract"] = {k: blocks.get(k) for k in keys}
    out["contract_keys"] = keys
    return out
def blank_payload(contract, case_id, status="partial", note="初始化：材料未解析"):
    base = {"case_id": case_id, "status": status, "summary": note, "result": {}, "queries": [],
            "hits": [], "filters": [], "excluded_evidence": [], "coverage": {}, "sources": [],
            "evidence": [], "uncertainties": [], "errors": [], "degradations": [], "changes": [],
            "counts": {}, "verification": {}, "runtime": {},
            "primary_result": "result.json"}
    return apply_contract(base, contract)
def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(esc_text(json.dumps(clean(r), ensure_ascii=False, default=str)) + "\n")
    return p