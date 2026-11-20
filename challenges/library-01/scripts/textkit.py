# -*- coding: utf-8 -*-
"""textkit -- decoding, type classification, text extraction and quote anchoring.

Standard library only. Every public function is total: it returns data instead
of raising. Used by libscan (inventory) and main (evidence checks).
"""
import io
import os
import re
import hashlib
import json
import zlib
import zipfile
import datetime
import unicodedata

TEXT_LIMIT = 240000
PDF_READ_CAP = 48 * 1024 * 1024
LINE_CAP = 6000

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".log",
            ".yaml", ".yml", ".ini", ".cfg", ".xml", ".html", ".htm", ".bib",
            ".tex", ".rst", ".srt", ".tab", ".py", ".r", ".m"}
PDF_EXT = {".pdf"}
ZIP_EXT = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".zip", ".epub"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".svg"}
BIN_EXT = {".bin", ".dat", ".raw", ".h5", ".hdf5", ".nc", ".mat", ".npy", ".npz",
           ".pkl", ".feather", ".parquet", ".sqlite", ".db"}


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def nfc(s):
    try:
        return unicodedata.normalize("NFKC", s)
    except Exception:
        return s


def norm(s):
    """Comparison key: NFKC, case-folded, quote/dash unified, whitespace removed."""
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    s = nfc(s).lower()
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u3000", " "), ("\u00a0", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def read_json(path):
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return json.load(f)


def read_text(path, limit=TEXT_LIMIT):
    """-> (text, encoding); tolerance ordered utf-8-sig -> utf-8 -> gb18030 -> latin-1."""
    try:
        with io.open(path, "rb") as f:
            raw = f.read(limit)
    except OSError:
        return "", "unreadable"
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("latin-1", "replace"), "latin-1"


def magic_of(path, n=8):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def kind_of(ext, head):
    """Content-first classification; extension only as a tie-breaker."""
    e = (ext or "").lower()
    if head[:5] == b"%PDF-":
        return "pdf"
    if head[:4] == b"PK\x03\x04":
        return e.lstrip(".") if e in ZIP_EXT and e != ".zip" else "zip"
    if e in PDF_EXT:
        return "pdf"
    if e in ZIP_EXT:
        return e.lstrip(".")
    if e in TEXT_EXT:
        return "text"
    if e in IMG_EXT:
        return "image"
    if e in BIN_EXT:
        return "binary"
    printable = sum(1 for c in head if 9 <= c < 127 or c >= 160)
    return "text" if head and printable >= max(4, len(head) - 1) else "binary"


def binary_in_text(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return True
    if not head:
        return False
    bad = sum(1 for c in head if c < 9 or (13 < c < 32))
    return bad > max(8, len(head) // 10)


def _pdf_unescape(b):
    out = bytearray()
    i = 0
    mp = {110: 10, 114: 13, 116: 9, 98: 8, 102: 12, 40: 40, 41: 41, 92: 92}
    while i < len(b):
        c = b[i]
        if c == 92 and i + 1 < len(b):
            n = b[i + 1]
            if n in mp:
                out.append(mp[n])
                i += 2
                continue
            if 48 <= n <= 55:
                m = re.match(rb"[0-7]{1,3}", b[i + 1:i + 4])
                if m:
                    out.append(int(m.group(0), 8) & 0xFF)
                    i += 1 + len(m.group(0))
                    continue
        out.append(c)
        i += 1
    return bytes(out)


def _pdf_text(path):
    """Best-effort: inflate content streams and pull (...)Tj / TJ strings."""
    try:
        with open(path, "rb") as f:
            data = f.read(PDF_READ_CAP)
    except OSError as e:
        return [], "none", "read_failed:%s" % type(e).__name__
    chunks = []
    for m in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", m.end())
        if end < 0:
            continue
        raw = data[m.end():end]
        dec = b""
        try:
            dec = zlib.decompress(raw)
        except Exception:
            if b"Tj" in raw or b"TJ" in raw:
                dec = raw
        if not dec:
            continue
        parts = [_pdf_unescape(x.group(0)[1:-1]) for x in re.finditer(rb"\((?:\\.|[^\\()])*\)", dec)]
        if parts:
            chunks.append(b" ".join(parts))
    if not chunks:
        pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
        return [], "none", "no_text_layer(pages=%d)" % pages
    txt = b"\n".join(chunks).decode("latin-1", "replace")
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    return lines, "pdf_basic", "inflated_streams=%d" % len(chunks)


def _zip_text(path, ext):
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return [], "none", "bad_zip:%s" % type(e).__name__
    out = []
    try:
        names = z.namelist()
        if ext == "docx":
            cand = [x for x in names if x == "word/document.xml"] or \
                   [x for x in names if x.endswith(".xml")][:2]
            for n in cand:
                xml = z.read(n).decode("utf-8", "replace")
                for p in re.split(r"</w:p>", xml):
                    t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))
                    t = re.sub(r"<[^>]+>", "", t).strip()
                    if t:
                        out.append(t)
        elif ext == "xlsx":
            shared = []
            if "xl/sharedStrings.xml" in names:
                sx = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
                shared = [re.sub(r"<[^>]+>", "", si).strip()
                          for si in re.findall(r"<si>(.*?)</si>", sx, re.S)]
            for n in sorted(x for x in names if x.startswith("xl/worksheets/") and x.endswith(".xml"))[:4]:
                sx = z.read(n).decode("utf-8", "replace")
                for row in re.findall(r"<row[^>]*>(.*?)</row>", sx, re.S):
                    cells = []
                    for t, body in re.findall(r"<c[^>]*?(?:t=\"(\w+)\")?[^>]*>(.*?)</c>", row, re.S):
                        v = re.search(r"<v>(.*?)</v>", body, re.S)
                        val = v.group(1) if v else ""
                        if t == "s" and val.isdigit() and int(val) < len(shared):
                            val = shared[int(val)]
                        cells.append(re.sub(r"<[^>]+>", "", val).strip())
                    line = "\t".join(cells).strip()
                    if line:
                        out.append(line)
        else:
            for n in names[:20]:
                if n.endswith(".xml"):
                    t = re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace"))
                    out.extend([x.strip() for x in t.split("\n") if x.strip()][:50])
    except Exception as e:
        return out, "zip_partial", "partial:%s" % type(e).__name__
    finally:
        try:
            z.close()
        except Exception:
            pass
    return out, ("ooxml" if out else "none"), "members=%d" % len(out)


def extract(path, kind):
    """-> {mode, lines, note, n_lines}. mode in plain|pdf_basic|ooxml|zip_partial|none."""
    try:
        if kind == "pdf":
            lines, mode, note = _pdf_text(path)
        elif kind in ("docx", "xlsx", "pptx", "odt", "ods"):
            lines, mode, note = _zip_text(path, kind)
        elif kind == "text":
            txt, enc = read_text(path)
            lines = [ln.rstrip() for ln in txt.splitlines()]
            mode, note = "plain", "encoding=%s" % enc
        else:
            lines, mode, note = [], "none", "non_text_kind:%s" % kind
    except Exception as e:
        return {"mode": "none", "lines": [], "note": "extract_error:%s" % type(e).__name__, "n_lines": 0}
    if len(lines) > LINE_CAP:
        note += ";truncated_at_%d" % LINE_CAP
    return {"mode": mode, "lines": lines[:LINE_CAP], "n_lines": len(lines), "note": note}


def find_quote(lines, quote, max_win=3):
    """1-based (start, end) line span where `quote` occurs verbatim, else None.

    Matching ignores whitespace and quote-glyph differences but not characters,
    so a hit is real evidence rather than a fuzzy guess.
    """
    q = norm(quote)
    if len(q) < 4:
        return None
    for i, ln in enumerate(lines):
        if q in norm(ln):
            return (i + 1, i + 1)
    for i in range(len(lines)):
        buf = ""
        for w in range(1, max_win + 1):
            if i + w > len(lines):
                break
            buf += lines[i + w - 1]
            if q in norm(buf):
                return (i + 1, i + w)
    return None


def snippet(lines, span, width=180):
    if not span:
        return ""
    a, b = span
    return " ".join(x.strip() for x in lines[a - 1:b])[:width]


# ------------------------------------------------------------ shared io helpers
DEFAULT_CONTRACT = ["inventory", "directory_tree", "metadata", "versions", "duplicates",
                    "queries", "recovery", "operations", "archive"]


def wj(path, obj):
    d = os.path.dirname(path) or "."
    try:
        os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def wt(path, s):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(s)
        return True
    except Exception:
        return False


def rj(path, default=None):
    try:
        return read_json(path)
    except Exception:
        return default


def pick(obj, names, default=None):
    if not isinstance(obj, dict):
        return default
    idx = {re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(k).lower()): k for k in obj}
    for want in names:
        w = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", want.lower())
        if w in idx:
            return obj[idx[w]]
    for want in names:
        w = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", want.lower())
        for nk, k in idx.items():
            if nk.startswith(w) or (len(w) > 4 and w in nk):
                return obj[k]
    return default


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _sha(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(512 * 1024), b""):
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------- draft verification
def validate(idx, draft):
    """Mechanical draft checks. FIX = must be repaired; WARN = recorded but tolerable."""
    files = {e["path"]: e for e in idx.get("files") or []}
    issues, counts = [], {}
    if not draft:
        return [{"level": "FIX", "code": "draft_missing",
                 "detail": "no draft.json; build will produce a degraded deliverable"}], counts
    if draft.get("case_id") and idx.get("case_id") and str(draft["case_id"]) != str(idx["case_id"]):
        issues.append({"level": "WARN", "code": "case_id_mismatch",
                       "detail": "draft=%r index=%r" % (draft["case_id"], idx["case_id"])})
    fl = as_list(draft.get("files"))
    counts["files"] = len(fl)
    for f in fl:
        p = f.get("path") if isinstance(f, dict) else f
        if p not in files:
            issues.append({"level": "FIX", "code": "path_not_in_index", "detail": str(p)})
    plan = as_list(draft.get("organization_plan") or draft.get("plan"))
    counts["plan"] = len(plan)
    for it in plan:
        if not isinstance(it, dict):
            issues.append({"level": "FIX", "code": "plan_item_not_object", "detail": repr(it)[:80]})
            continue
        src = it.get("from") or it.get("source")
        if src not in files:
            issues.append({"level": "FIX", "code": "plan_source_not_in_index", "detail": str(src)})
        if not (it.get("to") or it.get("target")):
            issues.append({"level": "FIX", "code": "plan_target_empty", "detail": str(src)})
    covered = set(i.get("from") or i.get("source") for i in plan if isinstance(i, dict))
    missing = [p for p in files if p not in covered and files[p]["status"] != "symlink"]
    if missing:
        issues.append({"level": "WARN", "code": "plan_incomplete",
                       "detail": "%d file(s) unplaced, fallback _unsorted/: %s"
                                 % (len(missing), ", ".join(missing[:5]))})
    md = as_list(draft.get("metadata"))
    counts["metadata"] = len(md)
    for m in md:
        if not isinstance(m, dict):
            continue
        mp = m.get("path")
        if mp not in files:
            issues.append({"level": "FIX", "code": "metadata_path_not_in_index", "detail": str(mp)})
        fields = m.get("fields")
        if not isinstance(fields, dict):
            issues.append({"level": "FIX", "code": "metadata_fields_not_object", "detail": str(mp)})
            continue
        for k, v in fields.items():
            src, val = (v.get("source"), v.get("value")) if isinstance(v, dict) else (None, v)
            if not src:
                issues.append({"level": "WARN", "code": "metadata_source_missing",
                               "detail": "%s.%s has no locator" % (mp, k)})
                continue
            sp = str(src).split("#")[0]
            if sp == "case.json":
                continue
            if sp not in files:
                issues.append({"level": "WARN", "code": "metadata_source_path_unknown",
                               "detail": "%s.%s -> %s" % (mp, k, sp)})
                continue
            lines = (files[sp].get("_text") or {}).get("lines") or []
            if lines and val not in (None, "") and not find_quote(lines, str(val)):
                issues.append({"level": "WARN", "code": "metadata_value_not_in_source",
                               "detail": "%s.%s=%r not in %s" % (mp, k, str(val)[:40], sp)})
    vs = as_list(draft.get("versions"))
    counts["versions"] = len(vs)
    for v in vs:
        if not isinstance(v, dict):
            continue
        mem = as_list(v.get("members"))
        if len(mem) < 2:
            issues.append({"level": "FIX", "code": "version_members_too_few",
                           "detail": "%s: %s" % (v.get("chain_id"), mem)})
        for m in mem:
            if m not in files:
                issues.append({"level": "FIX", "code": "version_member_not_in_index", "detail": str(m)})
        if not (v.get("basis") or v.get("evidence")):
            issues.append({"level": "FIX", "code": "version_without_evidence",
                           "detail": "%s lacks basis (hash or note locator)" % v.get("chain_id")})
    dp = as_list(draft.get("duplicates"))
    counts["duplicates"] = len(dp)
    hashes = set(e.get("sha256") for e in idx.get("files") or [] if e.get("sha256"))
    for d in dp:
        if not isinstance(d, dict):
            continue
        if d.get("sha256") and d["sha256"] not in hashes:
            issues.append({"level": "FIX", "code": "duplicate_hash_unknown",
                           "detail": str(d["sha256"])[:24]})
        if d.get("keep") and d["keep"] not in files:
            issues.append({"level": "FIX", "code": "duplicate_keep_not_in_index",
                           "detail": str(d.get("keep"))})
    qs = as_list(draft.get("queries"))
    counts["queries"] = len(qs)
    if idx.get("queries"):
        said = norm(" ".join(str(q.get("question") or "") for q in qs if isinstance(q, dict)))
        for q in idx["queries"]:
            if q.get("question") and norm(q["question"])[:12] not in said:
                issues.append({"level": "WARN", "code": "declared_query_unanswered",
                               "detail": q["question"][:80]})
    for qi, q in enumerate(qs):
        if not isinstance(q, dict):
            continue
        hits = as_list(q.get("hits"))
        for hi, h in enumerate(hits):
            if not isinstance(h, dict):
                continue
            p, quote = h.get("path"), h.get("quote")
            if p not in files:
                issues.append({"level": "FIX", "code": "query_hit_path_not_in_index",
                               "detail": "q%d %s" % (qi + 1, p)})
                continue
            if not quote:
                issues.append({"level": "FIX", "code": "query_hit_quote_empty",
                               "detail": "q%d %s" % (qi + 1, p)})
                continue
            lines = (files[p].get("_text") or {}).get("lines") or []
            if not lines:
                issues.append({"level": "WARN", "code": "query_hit_no_text_layer",
                               "detail": "q%d %s (%s)" % (qi + 1, p, (files[p].get("_text") or {}).get("mode"))})
                continue
            span = find_quote(lines, str(quote))
            if not span:
                issues.append({"level": "FIX", "code": "quote_not_found",
                               "detail": "q%d hit#%d %s -> %r" % (qi + 1, hi + 1, p, str(quote)[:60])})
            elif h.get("locator") and ("#L%d" % span[0]) not in str(h.get("locator")):
                issues.append({"level": "WARN", "code": "locator_drift",
                               "detail": "q%d %s says %s, actual #L%d" % (qi + 1, p, h.get("locator"), span[0])})
        if not hits and not (q.get("miss_reason") or q.get("no_hit_reason")):
            issues.append({"level": "FIX", "code": "query_miss_undocumented",
                           "detail": "q%d has no hits and no miss_reason" % (qi + 1)})
    for r in as_list(draft.get("recovery")):
        if isinstance(r, dict) and r.get("file") and r["file"] not in files \
                and str(r.get("action") or "").lower() not in ("reindex", "none"):
            issues.append({"level": "WARN", "code": "recovery_target_unknown", "detail": str(r.get("file"))})
    if not as_list(draft.get("uncertainties")) and (idx.get("note_issues") or []):
        issues.append({"level": "WARN", "code": "uncertainties_empty_with_open_issues",
                       "detail": "%d unresolved note edge(s) not acknowledged" % len(idx["note_issues"])})
    return issues, counts


# ------------------------------------------------------------------ handover
def render_report(idx, payload, cov, tree, land, chains, dups, queries, meta, recovery, version="1.0.0"):
    out = []
    a = out.append
    a("# 资料库落库与版本修复报告")
    a("")
    a("- case_id: `%s`  " % idx.get("case_id"))
    a("- status: **%s**  " % payload.get("status"))
    a("- skill: library-repair-desk %s  " % version)
    a("- roots: %s" % ", ".join("`%s`" % r for r in idx.get("stats", {}).get("roots") or []))
    a("")
    a("| 指标 | 值 |")
    a("|---|---|")
    for k in ("files_expected", "files_landed", "files_skipped", "files_duplicate",
              "metadata_fields_filled", "version_chains", "queries_hit", "operations"):
        a("| %s | %s |" % (k, cov.get(k)))
    a("")
    a("落库校验：%d 个副本复算 sha256；全部一致=%s；哈希不符 %d 项。" % (
        len(land["integrity"]), all(i["verified"] for i in land["integrity"]),
        len(land["quarantined"])))
    a("")
    if land["skipped"]:
        a("未落库条目（均带原因）：")
        for s in land["skipped"][:25]:
            a("- `%s` — %s" % (s.get("path"), s.get("reason")))
        a("")
    a("## 目录树")
    a("")
    a("```")
    a("\n".join(tree))
    a("```")
    a("")
    a("## 版本关系")
    a("")
    if not chains:
        a("未发现能由内容哈希或备注证明的版本链。")
    for c in chains:
        a("### %s（confidence=%s）" % (c["chain_id"], c["confidence"]))
        a("")
        a("顺序：%s；当前版本 `%s`" % (" → ".join("`%s`" % p for p in c["order"]), c["current"]))
        a("")
        for b in c["basis"]:
            a("- 依据 %s（%s）" % (b["basis"], b["confidence"]))
        for d in c["diffs"]:
            a("- 差异 %s → %s：%s +%s/-%s 行 size_delta=%s" % (
                d["from"], d["to"], d["type"], d.get("lines_added", "-"),
                d.get("lines_removed", "-"), d.get("size_delta")))
        a("")
    a("## 重复")
    a("")
    if not dups:
        a("未发现内容相同的文件。")
    for d in dups:
        a("- `%s` ×%d 保留 `%s`，同内容 %s" % (str(d["sha256"])[:16], d["count"], d.get("keep"),
                                           ", ".join("`%s`" % x for x in d.get("archive") or [])))
    a("")
    a("## 检索")
    a("")
    for q in queries:
        a("- **%s** → %s" % (q.get("question"), q.get("status")))
        for h in q.get("hits") or []:
            a("  - `%s` %s：%s" % (h.get("path"), h.get("locator"),
                                   "verified" if h.get("verified") else "UNVERIFIED(%s)" % h.get("issue")))
        if q.get("miss_reason"):
            a("  - 未命中说明：%s" % q["miss_reason"])
    a("")
    a("## 恢复与索引")
    a("")
    ir = recovery.get("index_rebuild") or {}
    a("索引重建 entries=%s landed=%s duplicates=%s skipped=%s 守恒=%s" % (
        ir.get("entries"), ir.get("landed"), ir.get("duplicates_not_landed"),
        ir.get("skipped_other"), ir.get("conserved")))
    a("")
    for i in (recovery.get("issues") or [])[:30]:
        a("- %s `%s` — %s" % (i.get("type"), i.get("path") or i.get("locator"), i.get("action")))
    a("")
    a("## 元数据口径")
    a("")
    a("%d 条记录，字段值带出处 locator；缺出处记为 empty，未从文件名推断作者/年份。" % len(meta))
    a("")
    a("## 降级与复跑")
    a("")
    for d in as_list(payload.get("degradations")):
        a("- `%s`：%s" % (d.get("code"), str(d.get("detail"))[:160]))
    a("")
    a("复跑：同一 `/input` 执行 `init` → `build` 可重建 inventory/duplicates/version_chains；"
      "排序键只含路径与哈希，不含时间戳。")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ self-check
def selfcheck(inp, work, out):
    checks = []

    def ck(cid, name, ok, detail=""):
        checks.append({"id": cid, "check": name, "ok": bool(ok), "detail": detail})

    res = rj(os.path.join(out, "result.json"))
    ck("SC-01", "result.json parses", isinstance(res, dict))
    if not isinstance(res, dict):
        wj(os.path.join(out, "self_check.json"),
           {"checks": checks, "summary": {"failed_ids": ["SC-01"]}})
        print("[selfcheck] result.json missing/invalid (exit 0, nothing fabricated)")
        return checks
    idx = rj(os.path.join(work, "index.json"), {}) or {}
    contract = idx.get("contract") or DEFAULT_CONTRACT
    keys = list(contract.keys()) if isinstance(contract, dict) else as_list(contract)
    missing = [k for k in keys if k not in res]
    ck("SC-02", "output_contract keys present", not missing, "missing=%s" % missing[:6])
    ck("SC-03", "case_id field present", "case_id" in res, "case_id=%r" % res.get("case_id"))
    ck("SC-04", "status is one of ok/partial/failed",
       res.get("status") in ("ok", "partial", "failed"),
       "status=%s degradations=%d" % (res.get("status"), len(as_list(res.get("degradations")))))
    gone = [r.get("path") for r in as_list(res.get("inventory"))
            if r.get("path") and r.get("status") not in ("too_large", "symlink")
            and not os.path.exists(os.path.join(inp, r["path"]))]
    ck("SC-05", "inventory paths resolvable in input", not gone, "missing=%s" % gone[:5])
    plan = rj(os.path.join(out, "directory_plan.json"), {}) or {}
    libroot = os.path.join(work, "library")
    mism, n_ok = [], 0
    for m in as_list(plan.get("map")):
        if m.get("status") != "landed":
            continue
        t = m.get("target_path")
        p = os.path.join(libroot, t) if t else None
        if not p or not os.path.isfile(p):
            mism.append({"file": m.get("from"), "issue": "target_missing"})
            continue
        src = os.path.join(inp, m.get("from") or "")
        a, b = _sha(p), (_sha(src) if os.path.isfile(src) else None)
        if a != b:
            mism.append({"file": m.get("from"), "issue": "hash_differs"})
        else:
            n_ok += 1
    ck("SC-06", "landed copies re-hash identical to source", not mism,
       "%d verified, %d mismatched" % (n_ok, len(mism)))
    ops = []
    try:
        with open(os.path.join(out, "operations.log"), encoding="utf-8") as f:
            ops = [json.loads(x) for x in f if x.strip()]
        ck("SC-07", "operations.log parsed as JSONL", True, "%d ops" % len(ops))
    except Exception as e:
        ck("SC-07", "operations.log parsed as JSONL", False, type(e).__name__)
    failed = [o for o in ops if o.get("result") == "failed"]
    ck("SC-08", "failed ops all carry a reason", all(o.get("reason") for o in failed),
       "%d failed op(s)" % len(failed))
    bad_skip = [r for r in as_list(res.get("skipped")) if not r.get("reason")]
    ck("SC-09", "skipped items carry reasons", not bad_skip, "%d without reason" % len(bad_skip))
    unver = [h.get("path") for q in as_list(res.get("queries"))
             for h in as_list(q.get("hits")) if not h.get("verified")]
    ck("SC-10", "query hits verified verbatim", not unver, "%d unverified" % len(unver))
    arts = ["inventory.json", "directory_plan.json", "tree.txt", "metadata.jsonl",
            "version_chains.json", "duplicates.json", "queries.json", "recovery.json",
            "archive_manifest.json", "operations.log", "report.md"]
    absent = [f for f in arts if not os.path.isfile(os.path.join(out, f))]
    ck("SC-11", "all declared artifacts exist", not absent, "absent=%s" % absent)
    ok_n = len([c for c in checks if c["ok"]])
    rep = {"generated": now(), "checks": checks,
           "summary": {"total": len(checks), "ok": ok_n,
                       "failed_ids": [c["id"] for c in checks if not c["ok"]],
                       "hash_verified": n_ok, "mismatches": mism[:20]}}
    wj(os.path.join(out, "self_check.json"), rep)
    print("[selfcheck] %d/%d ok | failed=%s | hash_verified=%d" % (
        ok_n, len(checks), rep["summary"]["failed_ids"] or "-", n_ok))
    print("[selfcheck] status=%s -> %s" % (res.get("status"), os.path.join(out, "self_check.json")))
    return checks


# ------------------------------------------------------------ work index

def strip_index_text(idx):
    """index.json stores text metadata only; bodies are re-extracted on demand."""
    out = json.loads(json.dumps(idx, ensure_ascii=False, default=str))
    for e in out.get("files") or []:
        t = e.get("_text") or {}
        e["text_mode"] = t.get("mode")
        e["text_lines"] = t.get("n_lines") or 0
        e["text_note"] = t.get("note")
        e["_text"] = None
    return out
