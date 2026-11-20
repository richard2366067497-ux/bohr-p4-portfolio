# -*- coding: utf-8 -*-
"""libscan -- inventory, note parsing, dedupe, version chains, landing, archive.

Standard library only, offline, CWD-independent. Public functions return data
and record problems as values; they do not raise into the caller.
"""
import os
import re
import csv
import io
import json
import shutil
import hashlib
import difflib
import zipfile
import datetime

import textkit as T

MAX_DEPTH = 10
MAX_FILES = 5000
HASH_LIMIT = 200 * 1024 * 1024
COPY_LIMIT = 64 * 1024 * 1024
ZIP_LIMIT = 48 * 1024 * 1024
TEXT_EXT = T.TEXT_EXT
PDF_EXT = T.PDF_EXT
ZIP_EXT = T.ZIP_EXT

NOTE_NAME_HINT = ("alias", "synonym", "别名", "duplicate", "重复", "dedupe", "version",
                  "版本", "supersede", "replace", "note", "备注", "index", "catalog",
                  "inventory", "manifest", "metadata", "元数据", "清单", "filelist")

ALIAS_FROM = ("alias", "from", "old", "oldname", "source_name", "src", "原名",
              "别名", "aka", "synonym", "other_name", "filename_alias")
ALIAS_TO = ("to", "canonical", "target", "new", "newname", "dst", "正名", "指向",
            "canon", "standard", "canonical_name", "real_name")
SUP_KEYS = ("supersede", "supersedes", "superseded", "replace", "replaces", "replaced",
            "取代", "替代", "作废", "obsolete", "previous", "old_version", "前版本")
FILE_KEYS = ("file", "path", "filename", "文件", "路径", "object", "item", "name")
FIELD_KEYS = ("field", "字段", "key", "属性", "property", "attribute")
VALUE_KEYS = ("value", "值", "content", "内容", "val")

FIELD_DICT = [
    ("title", "string", "文档题名；正文标题优先，其次伴随表", "sidecar > body > filename"),
    ("author", "string[]", "作者；只接受伴随表或正文署名，不从文件名推断", "sidecar > body"),
    ("year", "integer", "年份；需在出处可见的四位数字", "sidecar > body"),
    ("project", "string", "项目号；需在伴随表、正文或组织规则中出现", "rules > sidecar > body"),
    ("doc_type", "enum", "raw_data|paper|supplement|analysis|admin|instrument|other", "rules > sidecar > body"),
    ("instrument", "string", "仪器型号；仅明确出现时填写", "sidecar > body"),
    ("doi", "string", "DOI；须逐字匹配 10.xxxx/... 形态", "sidecar > body"),
    ("keywords", "string[]", "关键词；来自伴随表或正文关键词段", "sidecar > body"),
    ("version", "string", "版本记号；来自备注或文件名，须注明依据", "note > filename"),
    ("status", "string", "superseded|current|draft|unknown；由版本备注裁决", "note"),
]


# ---------------------------------------------------------------- hash & time
def sha256_file(path, limit=HASH_LIMIT):
    h = hashlib.sha256()
    total = 0
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(512 * 1024)
                if not b:
                    break
                total += len(b)
                if total > limit:
                    return None, "exceeds_hash_limit"
                h.update(b)
        return h.hexdigest(), None
    except OSError as e:
        return None, type(e).__name__


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def iso(ts):
    try:
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def rel(p, base):
    try:
        return os.path.relpath(p, base).replace(os.sep, "/")
    except Exception:
        return p.replace(os.sep, "/")


# ------------------------------------------------------------------------- scan
def scan(input_dir, roots):
    entries, dir_issues = [], []
    seen = set()
    truncated = False
    for root in roots:
        stack = [(root, 0)]
        while stack and not truncated:
            cur, depth = stack.pop()
            try:
                kids = sorted(os.scandir(cur), key=lambda d: d.name)
            except OSError as e:
                dir_issues.append({"path": rel(cur, input_dir), "reason": type(e).__name__})
                continue
            subdirs = []
            for de in kids:
                p = de.path
                if p in seen:
                    continue
                seen.add(p)
                try:
                    if de.is_symlink():
                        entries.append(_entry(p, input_dir, depth, "symlink", "symlink_not_followed", None))
                        continue
                    if de.is_dir():
                        if depth + 1 > MAX_DEPTH:
                            dir_issues.append({"path": rel(p, input_dir), "reason": "max_depth_exceeded"})
                            continue
                        subdirs.append((p, depth + 1))
                        continue
                    if not de.is_file():
                        continue
                except OSError as e:
                    entries.append(_entry(p, input_dir, depth, "unreadable", type(e).__name__, None))
                    continue
                if len(entries) >= MAX_FILES:
                    truncated = True
                    break
                entries.append(_describe(p, input_dir, depth))
            for s in reversed(subdirs):
                stack.append(s)
    entries.sort(key=lambda e: e["path"])
    stats = {"files": len(entries), "bytes": sum(e.get("size") or 0 for e in entries),
             "max_depth": max([e.get("depth") or 0 for e in entries] or [0]),
             "dir_issues": len(dir_issues), "truncated": truncated,
             "roots": [rel(r, input_dir) for r in roots]}
    return entries, dir_issues, stats


def _entry(p, base, depth, status, reason, size):
    return {"path": rel(p, base), "_abs": p, "size": size, "ext": os.path.splitext(p)[1].lower(),
            "kind": "unknown", "status": status, "reason": reason, "sha256": None,
            "mtime": None, "depth": depth, "mode": None, "_text": None}


def _describe(p, base, depth):
    """One file -> one inventory row: size, mtime, kind, integrity verdict, sha256."""
    e = _entry(p, base, depth, "ok", None, None)
    try:
        st = os.stat(p)
        e["size"] = st.st_size
        e["mtime"] = iso(st.st_mtime)
        e["mode"] = oct(st.st_mode & 0o777)
    except OSError as ex:
        e["status"], e["reason"] = "unreadable", type(ex).__name__
        return e
    head = T.magic_of(p)
    e["kind"] = T.kind_of(e["ext"], head)
    if e["size"] == 0:
        e["status"], e["reason"] = "empty", "zero_byte"
        e["sha256"] = sha256_bytes(b"")
        return e
    if e["size"] > HASH_LIMIT:
        e["status"] = "too_large"
        e["reason"] = "size_gt_%dMB" % (HASH_LIMIT // 1024 // 1024)
        return e
    if e["kind"] == "pdf" and head[:5] != b"%PDF-":
        e["status"] = "corrupt"
        e["reason"] = "magic_mismatch(expected=%%PDF- got=%r)" % head[:5]
    elif e["ext"] in ZIP_EXT and head[:4] != b"PK\x03\x04":
        e["status"] = "corrupt"
        e["reason"] = "magic_mismatch(expected=PK got=%r)" % head[:4]
    elif e["kind"] in ("docx", "xlsx", "pptx", "zip") and head[:4] == b"PK\x03\x04":
        try:
            zipfile.ZipFile(p).namelist()
        except Exception as ex:
            e["status"], e["reason"] = "corrupt", "bad_zip:%s" % type(ex).__name__
    elif e["kind"] == "text" and T.binary_in_text(p):
        e["status"], e["reason"] = "corrupt", "binary_bytes_in_text_file"
    h, err = sha256_file(p) if e["status"] != "too_large" else (None, "skipped_too_large")
    e["sha256"] = h
    if err and err != "skipped_too_large" and e["status"] == "ok":
        e["status"], e["reason"] = "unreadable", err
    if e["mode"] and int(e["mode"], 8) & 0o444 == 0 and e["status"] == "ok":
        e["reason"] = "perm_note:no_read_bits_but_readable"
    return e


def attach_text(entries, only=None):
    for e in entries:
        if only and e["path"] not in only:
            continue
        if e["status"] in ("too_large", "symlink") or not e.get("_abs"):
            e["_text"] = {"mode": "none", "lines": [], "note": e["status"], "n_lines": 0}
            continue
        if e["ext"] in PDF_EXT or e["ext"] in ZIP_EXT or e["kind"] == "text":
            e["_text"] = T.extract(e["_abs"], e["kind"])
    return entries


# ------------------------------------------------------------------------ notes
def _looks_like_note(e):
    name = os.path.basename(e["path"]).lower()
    if any(h in name for h in NOTE_NAME_HINT):
        return True
    t = e.get("_text") or {}
    head = "\n".join((t.get("lines") or [])[:3]).lower()
    return any(k in head for k in ("alias", "supersede", "replace", "别名", "版本", "field", "sha256"))


def _pick(d, keys):
    for k in d:
        nk = str(k).strip().lower().replace(" ", "_").replace("-", "_")
        for want in keys:
            if nk == want or nk.startswith(want) or want in nk:
                return d[k]
    return None


def _rows_of(e):
    """Yield (row_dict, locator) for a note file: JSON, CSV/TSV, or plain text lines."""
    t = e.get("_text") or {}
    lines = t.get("lines") or []
    ext = e["ext"]
    if ext in (".json", ".jsonl") and e.get("_abs"):
        try:
            obj = T.read_json(e["_abs"])
        except Exception:
            return
        for i, d in enumerate(_json_rows(obj)):
            yield d, "%s#r%d" % (e["path"], i + 1)
        return
    if ext in (".csv", ".tsv", ".tab") and e.get("_abs"):
        try:
            txt, _ = T.read_text(e["_abs"])
            rd = list(csv.reader(io.StringIO(txt), delimiter=("\t" if ext != ".csv" else ",")))
        except Exception:
            rd = []
        if len(rd) >= 2:
            hdr = [h.strip() for h in rd[0]]
            for i, row in enumerate(rd[1:]):
                if not any(x.strip() for x in row):
                    continue
                d = {}
                for j, h in enumerate(hdr):
                    d[h or ("col%d" % j)] = row[j].strip() if j < len(row) else ""
                yield d, "%s#r%d" % (e["path"], i + 2)
            return
    for i, ln in enumerate(lines):
        yield {"_raw": ln}, "%s#L%d" % (e["path"], i + 1)


def _json_rows(obj, depth=0):
    out = []
    if isinstance(obj, list):
        for x in obj:
            out.extend(_json_rows(x, depth + 1))
    elif isinstance(obj, dict):
        if all(not isinstance(v, (dict, list)) for v in obj) and obj:
            out.append({str(k): v for k, v in obj.items()})
        else:
            for k, v in obj.items():
                if isinstance(v, (list, dict)):
                    for x in _json_rows(v, depth + 1):
                        x = dict(x)
                        x.setdefault("_group", str(k))
                        out.append(x)
    return out


TXT_ALIAS = re.compile(r"^\s*[\"'\u201c\u300c]?(?P<a>[^\"'\u201d\u300d]{2,200}?)[\"'\u201d\u300d]?\s*"
                       r"(?:->|=>|\u2192|\u21d2|\u522b\u540d\u4e3a|\u4ea6\u540d|is\s+an?\s+alias\s+of|alias\s+of)"
                       r"\s*[\"'\u201c\u300c]?(?P<b>[^\"'\u201d\u300d]{2,200}?)[\"'\u201d\u300d]?\s*$", re.I)
TXT_SUP = re.compile(r"^\s*[\"'\u201c\u300c]?(?P<a>[^\"'\u201d\u300d]{2,200}?)[\"'\u201d\u300d]?\s+"
                     r"(?:supersedes|supersede|replaces|replace|\u53d6\u4ee3|\u66ff\u4ee3|\u4f5c\u5e9f)\s+"
                     r"[\"'\u201c\u300c]?(?P<b>[^\"'\u201d\u300d]{2,200}?)[\"'\u201d\u300d]?\s*$", re.I)


def parse_notes(entries, case_notes=None):
    """Extract alias edges, version edges and metadata rows from sidecars.

    Order matters: a "<new> supersedes <old>" row means the OLD file is
    superseded, so the version edge stores (prev=<old>, cur=<new>).
    """
    alias, ver, md = [], [], []
    for e in entries:
        if e["status"] in ("too_large", "symlink") or not _looks_like_note(e):
            continue
        base = os.path.basename(e["path"]).lower()
        is_index = any(h in base for h in ("index", "catalog", "inventory", "filelist", "清单"))
        for d, loc in _rows_of(e):
            raw = d.get("_raw")
            if raw is not None:
                if is_index:
                    continue
                m = TXT_ALIAS.match(raw)
                if m:
                    alias.append(_edge(m.group("a"), m.group("b"), e["path"], loc, "text"))
                m = TXT_SUP.match(raw)
                if m:
                    ver.append(_vedge(m.group("a"), m.group("b"), e["path"], loc, "text"))
                continue
            a, b = _pick(d, ALIAS_FROM), _pick(d, ALIAS_TO)
            if a and b and str(a).strip() and str(b).strip() and str(a).strip() != str(b).strip():
                alias.append(_edge(a, b, e["path"], loc, "table"))
            f, sup = _pick(d, FILE_KEYS), _pick(d, SUP_KEYS)
            if f and sup and str(sup).strip() and str(f).strip() != str(sup).strip():
                ver.append(_vedge(sup, f, e["path"], loc, "table"))
            fld, val = _pick(d, FIELD_KEYS), _pick(d, VALUE_KEYS)
            if f and fld and val not in (None, ""):
                md.append({"file": str(f).strip(), "field": str(fld).strip().lower(),
                           "value": val, "source": loc})
    for kind, obj in (case_notes or {}).items():
        for i, d in enumerate(_json_rows(obj)):
            if not isinstance(d, dict):
                continue
            loc = "case.json#%s[%d]" % (kind, i)
            a, b = _pick(d, ALIAS_FROM), _pick(d, ALIAS_TO)
            if a and b:
                alias.append(_edge(a, b, "case.json", loc, "case"))
            f, sup = _pick(d, FILE_KEYS), _pick(d, SUP_KEYS)
            if f and sup:
                ver.append(_vedge(sup, f, "case.json", loc, "case"))
    return alias, ver, md


def _edge(a, b, src, loc, how):
    return {"alias": _clean(a), "canonical": _clean(b), "source": src, "locator": loc, "how": how}


def _vedge(prev, cur, src, loc, how):
    return {"supersedes": _clean(prev), "file": _clean(cur), "source": src, "locator": loc, "how": how}


def _clean(s):
    s = T.nfc(str(s)).strip().strip("\"'\u201c\u201d\u300c\u300d")
    return re.sub(r"\s+", " ", s).strip(" ,.;:|\t")


def resolve_ref(token, entries):
    """Exact rel-path -> unique basename -> unique stem -> unique substring."""
    t = _clean(token).replace("\\", "/").lstrip("./")
    if not t:
        return None
    low = T.nfc(t).lower()
    for e in entries:
        if e["path"].lower() == low:
            return e
    base = os.path.basename(low)
    hits = [e for e in entries if os.path.basename(e["path"]).lower() == base]
    if len(hits) == 1:
        return hits[0]
    stem = os.path.splitext(base)[0]
    hits = [e for e in entries if os.path.splitext(os.path.basename(e["path"]).lower())[0] == stem]
    if len(hits) == 1:
        return hits[0]
    hits = [e for e in entries if stem and stem in os.path.basename(e["path"]).lower()]
    return hits[0] if len(hits) == 1 else None


def link_edges(alias, ver, entries):
    a_out, v_out, issues = [], [], []
    for a in alias:
        ae, ce = resolve_ref(a["alias"], entries), resolve_ref(a["canonical"], entries)
        row = dict(a, alias_path=ae["path"] if ae else None, canonical_path=ce["path"] if ce else None)
        row["status"] = "resolved" if (ae and ce) else ("dangling_alias" if not ae else "dangling_canonical")
        if row["status"] != "resolved":
            issues.append({"type": "dangling_alias", "locator": a["locator"],
                           "detail": "%s -> %s" % (a["alias"], a["canonical"]),
                           "unresolved": a["alias"] if not ae else a["canonical"],
                           "action": "not_linked; recorded only"})
        a_out.append(row)
    for v in ver:
        pe, ce = resolve_ref(v["supersedes"], entries), resolve_ref(v["file"], entries)
        row = dict(v, prev_path=pe["path"] if pe else None, cur_path=ce["path"] if ce else None)
        row["status"] = "resolved" if (pe and ce) else "dangling_version"
        if row["status"] != "resolved":
            issues.append({"type": "dangling_version", "locator": v["locator"],
                           "detail": "%s supersedes %s" % (v["file"], v["supersedes"]),
                           "unresolved": v["supersedes"] if not pe else v["file"],
                           "action": "not_linked; needs human confirmation"})
        v_out.append(row)
    return a_out, v_out, issues


# ------------------------------------------------------------- groups & chains
def doc_key(name):
    s = T.nfc(os.path.splitext(os.path.basename(name))[0]).lower()
    s = re.sub(r"[\(\)\[\]\u3010\u3011\u300a\u300b]", " ", s)
    s = re.sub(r"(?i)\b(copy|backup|final|draft|version|ver|rev)\b", " ", s)
    s = re.sub(r"(\u526f\u672c|\u5907\u4efd|\u6700\u7ec8|\u5b9a\u7a3f|\u4fee\u8ba2|\u65e7\u7248|\u65b0\u7248)", " ", s)
    s = re.sub(r"(?i)([\s_\-.])+(v|rev|ver|r)\s*\d+([\s_\-.]|$)", r"\1", s)
    s = re.sub(r"[\s_\-.]+\(\d+\)$", "", s)
    s = re.sub(r"[\s_\-.]+", "_", s).strip("_. -")
    return s


def version_rank(name):
    base = T.nfc(os.path.basename(name)).lower()
    nums = [int(n) for n in re.findall(r"(?:^|[_\-. ])(?:v|rev|ver|r)(\d+)", base)]
    score = max(nums) if nums else 0
    if re.search(r"(final|\u5b9a\u7a3f|\u6700\u7ec8)", base):
        score += 1000
    elif "\u65b0\u7248" in base:
        score += 500
    return score


class _UF(object):
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.p[rb] = ra
        return True


def build_chains(entries, alias_links, ver_links, draft_versions):
    """Edge priority: note:supersedes > alias note > agent draft > name+time candidate."""
    idx = {e["path"]: i for i, e in enumerate(entries)}
    uf = _UF(len(entries))
    edges = []
    for a in alias_links:
        if a["status"] == "resolved" and a["alias_path"] in idx and a["canonical_path"] in idx \
                and a["alias_path"] != a["canonical_path"]:
            if uf.union(idx[a["alias_path"]], idx[a["canonical_path"]]):
                edges.append({"a": a["alias_path"], "b": a["canonical_path"],
                              "basis": "alias-note:%s" % a["locator"], "confidence": "medium",
                              "detail": a["alias"] + " -> " + a["canonical"]})
    for v in ver_links:
        if v["status"] == "resolved" and v["prev_path"] in idx and v["cur_path"] in idx:
            if uf.union(idx[v["prev_path"]], idx[v["cur_path"]]):
                edges.append({"a": v["prev_path"], "b": v["cur_path"],
                              "basis": "note:supersedes:%s" % v["locator"],
                              "confidence": "high",
                              "detail": "%s supersedes %s" % (v["cur_path"], v["prev_path"])})
    for dv in draft_versions or []:
        mem = [m for m in (dv.get("members") or []) if m in idx]
        for m in mem[1:]:
            if uf.union(idx[mem[0]], idx[m]):
                edges.append({"a": mem[0], "b": m,
                              "basis": "draft:%s" % (dv.get("basis") or "agent_judgement"),
                              "confidence": dv.get("confidence") or "medium",
                              "detail": dv.get("diff_note") or ""})
    groups = {}
    for e in entries:
        if e.get("sha256"):
            groups.setdefault(doc_key(e["path"]), []).append(e)
    for key, mem in groups.items():
        if len(mem) < 2 or len(set(m["sha256"] for m in mem)) < 2:
            continue
        mem = sorted(mem, key=lambda x: (x.get("mtime") or "", version_rank(x["path"])))
        for a, b in zip(mem, mem[1:]):
            if uf.union(idx[a["path"]], idx[b["path"]]):
                edges.append({"a": a["path"], "b": b["path"],
                              "basis": "name-candidate(key=%s)" % key, "confidence": "low",
                              "detail": "name similarity only; requires human confirmation"})
    comps = {}
    for e in entries:
        if e.get("sha256"):
            comps.setdefault(uf.find(idx[e["path"]]), []).append(e)
    chains, n = [], 0
    for root, mem in sorted(comps.items(), key=lambda kv: min(x["path"] for x in kv[1])):
        if len(mem) < 2:
            continue
        # byte-identical members are one version: keep one representative, list the rest
        by_hash, reps, aliases = {}, [], []
        for m in sorted(mem, key=lambda x: (len(x["path"]), x["path"])):
            h = m.get("sha256")
            if h and h in by_hash:
                aliases.append({"path": m["path"], "same_as": by_hash[h], "sha256": h,
                                "relation": "identical_bytes_alias"})
                continue
            if h:
                by_hash[h] = m["path"]
            reps.append(m)
        if len(reps) < 2:
            continue
        n += 1
        mem = sorted(reps, key=lambda x: (x.get("mtime") or "", version_rank(x["path"]), x["path"]))
        paths = [m["path"] for m in mem]
        ce = [x for x in edges if x["a"] in paths and x["b"] in paths]
        conf = "high" if any(x["confidence"] == "high" for x in ce) else \
               ("medium" if any(x["confidence"] == "medium" for x in ce) else "low")
        chains.append({
            "chain_id": "C%02d" % n,
            "doc_key": doc_key(mem[0]["path"]),
            "members": [{"path": m["path"], "sha256": m["sha256"], "mtime": m["mtime"],
                         "size": m["size"], "version_rank": version_rank(m["path"])} for m in mem],
            "order": paths,
            "supersedes": paths[-1],
            "current": paths[-1],
            "basis": [{"edge": "%s -> %s" % (x["a"], x["b"]), "basis": x["basis"],
                       "confidence": x["confidence"], "detail": x["detail"]} for x in ce],
            "confidence": conf,
            "aliases": aliases,
            "diffs": _diffs(mem),
        })
    return chains, edges


def _diffs(mem):
    out = []
    for a, b in zip(mem, mem[1:]):
        d = {"from": a["path"], "to": b["path"], "type": "binary_metadata_only",
             "size_delta": (b.get("size") or 0) - (a.get("size") or 0),
             "sha256_changed": a.get("sha256") != b.get("sha256")}
        ta = (a.get("_text") or {}).get("lines") or []
        tb = (b.get("_text") or {}).get("lines") or []
        if ta and tb:
            sm = difflib.SequenceMatcher(None, ta, tb)
            add = rem = 0
            samples = []
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag in ("replace", "insert"):
                    add += j2 - j1
                    if len(samples) < 3:
                        for k in range(j1, min(j2, j1 + 2)):
                            samples.append({"locator": "%s#L%d" % (b["path"], k + 1), "text": tb[k][:160]})
                elif tag == "delete":
                    rem += i2 - i1
            d.update({"type": "text_line_diff", "lines_added": add, "lines_removed": rem,
                      "ratio": round(sm.ratio(), 4), "added_samples": samples})
        out.append(d)
    return out


# ---------------------------------------------------------------------- search


# ------------------------------------------------------ input discovery & index
def pick(obj, names, default=None):
    """Case-insensitive, separator-insensitive key lookup (accepts zh/en keys)."""
    if not isinstance(obj, dict):
        return default
    norm = {re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(k).lower()): k for k in obj}
    for want in names:
        w = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", want.lower())
        if w in norm:
            return obj[norm[w]]
    for want in names:
        w = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", want.lower())
        for nk, k in norm.items():
            if nk.startswith(w) or (len(w) > 4 and w in nk):
                return obj[k]
    return default


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def norm_q(item):
    if isinstance(item, str):
        return {"question": item.strip(), "id": None}
    if isinstance(item, dict):
        q = pick(item, ["question", "query", "q", "text", "ask", "prompt", "问题", "检索"])
        return {"question": (q or "").strip() if isinstance(q, str) else "",
                "id": pick(item, ["id", "qid", "question_id", "编号"]), "raw": item}
    return {"question": str(item), "id": None}


def discover(inp):
    """Locate case.json (semantic keys, tolerant of renaming) and read its contract."""
    case, errors = {}, []
    path = os.path.join(inp, "case.json")
    if not os.path.isfile(path):
        cands = []
        for root, dirs, files in os.walk(inp):
            if os.path.relpath(root, inp).count(os.sep) > 3:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            cands += [os.path.join(root, f) for f in files if re.match(r"(?i)case.*\.json$", f)]
        if cands:
            path = sorted(cands, key=lambda p: (len(p), p))[0]
            errors.append({"code": "case_json_moved", "detail": path})
        else:
            errors.append({"code": "case_json_missing", "detail": "no case*.json under %s" % inp})
            path = None
    if path:
        try:
            case = T.read_json(path)
        except Exception as e:
            errors.append({"code": "case_json_invalid",
                           "detail": "%s: %s" % (type(e).__name__, str(e)[:160])})
            case = {}
    rules = pick(case, ["rules", "organization", "organisation", "directory_template", "template",
                        "organization_rules", "naming_rules", "目录规范", "规则"]) or {}
    notes = {"aliases": pick(case, ["aliases", "alias", "别名"]),
             "version_notes": pick(case, ["version_notes", "versionnotes", "版本备注"]),
             "metadata": pick(case, ["metadata", "meta", "字段表"])}
    return {"case": case,
            "case_id": pick(case, ["case_id", "caseid", "case", "id", "案例编号"]),
            "contract": pick(case, ["output_contract", "outputcontract", "output", "contract",
                                    "deliverable_contract", "output_fields", "required_output", "交付契约"]),
            "queries": [norm_q(x) for x in as_list(pick(case, ["queries", "questions", "searches",
                                                               "search_questions", "retrieval", "检索问题"]))],
            "rules": rules if isinstance(rules, dict) else {"note": str(rules)},
            "notes": {k: v for k, v in notes.items() if v not in (None, [], {})},
            "expected": pick(case, ["expected_counts", "counts", "expected", "预期计数"]) or {},
            "instruction": pick(case, ["task_instruction", "instruction", "task", "workorder", "任务说明"]) or "",
            "errors": errors}


def roots_of(inp, case):
    """Material roots: declared root(s) first, then conventional names."""
    cands = []
    for d in as_list(pick(case, ["library_root", "root", "materials", "files_dir", "library",
                                 "data_dir", "input_dir", "source_root", "资料根目录"])):
        if isinstance(d, str) and d.strip():
            cands.append(os.path.normpath(d if os.path.isabs(d) else os.path.join(inp, d)))
    for name in ("library", "artifacts", "files", "materials", "data", "docs"):
        cands.append(os.path.join(inp, name))
    out = []
    for c in cands:
        if os.path.isdir(c) and c not in out:
            out.append(c)
    return out or [inp]


def index_path(work):
    return os.path.join(work, "index.json")


def do_scan(inp, disc):
    """Scan + text extraction + note parsing -> the work index (kept out of result.json)."""
    roots = roots_of(inp, disc["case"])
    entries, dir_issues, stats = scan(inp, roots)
    attach_text(entries)
    alias, ver, md = parse_notes(entries, disc["notes"])
    a_links, v_links, note_issues = link_edges(alias, ver, entries)
    stats["roots"] = [rel(r, inp) for r in roots]
    return {"created": T.now(), "input": inp, "roots": roots, "case_id": disc["case_id"],
            "contract": disc["contract"], "queries": disc["queries"], "rules": disc["rules"],
            "expected": disc["expected"], "instruction": disc["instruction"],
            "case_errors": disc["errors"], "files": entries, "dir_issues": dir_issues,
            "stats": stats, "alias": a_links, "versions": v_links,
            "note_issues": note_issues, "metadata_rows": md}


def load_index(work, inp, with_text=False):
    """Reuse the index from `init`; rebuild it if missing. Text bodies are re-extracted
    on demand because they are deliberately not persisted in index.json."""
    idx = None
    try:
        idx = T.read_json(index_path(work))
    except Exception:
        idx = None
    if isinstance(idx, dict) and idx.get("files"):
        for e in idx["files"]:
            e["_text"] = None
        if with_text:
            attach_text(idx["files"])
        return idx, False
    return do_scan(inp, discover(inp)), True

