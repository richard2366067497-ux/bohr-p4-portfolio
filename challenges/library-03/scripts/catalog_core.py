#!/usr/bin/env python3
"""catalog_core -- scanning and evidence engine for facet-catalog-curator.

Stdlib only, offline, no CWD dependency, no case-specific answers.
Covers: file inventory (sha256 / magic / text layer), candidate metadata with
locators, facet candidates, duplicate & version candidate pairs, quote checking.
"""
import hashlib
import json
import re
import sys
import zlib
import zipfile
from pathlib import Path

V = "1.0.0"
TOOL = "facet-catalog-curator"
HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9<>]+")
ARX_RE = re.compile(r"arxiv[:\s]*([0-9]{4}\.[0-9]{4,5})(v[0-9]+)?", re.I)
YEAR_RE = re.compile(r"\b(19[5-9][0-9]|20[0-4][0-9])\b")
TOK = re.compile(r"[a-z0-9]+")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".bib", ".ris", ".yaml", ".yml", ".xml", ".html",
            ".htm", ".log", ".note", ".notes", ".rst"}
COMP_EXT = {".csv", ".tsv", ".json", ".bib", ".ris"}
PLACEHOLDERS = {"first_author", "year", "short_title", "identifier_tail", "doc_type", "project",
                "version_state", "original_stem", "language"}
IMG = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"II*\x00", b"MM\x00*", b"BM")


# ------------------------------------------------------------------ io utils
def rd(p):
    return Path(p).read_bytes()


def ljson(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="replace")), None
    except Exception as exc:  # noqa: BLE001 - any decode failure degrades, never raises
        return None, "%s: %s" % (type(exc).__name__, exc)


def wjson(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def wtext(p, txt):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return p


def norm(s):
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def tol(s):
    return norm(s).lower()


def toks(s):
    return TOK.findall(tol(s))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def filled(v):
    return not (v is None or v == "" or v == [] or v == "unknown")


# ------------------------------------------------------------------ text layer
def decode(b, cascade):
    for enc in cascade:
        try:
            t = b.decode(enc)
            return t, enc, t.count("\ufffd")
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("latin-1", "replace"), "latin-1", len(b)


def _pdf_strings(data):
    out = []
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\[\]]|\\.)*\]\s*TJ", data):
        parts = []
        for p in re.findall(rb"\((?:\\.|[^\\()])*\)", m.group(0)):
            s = re.sub(rb"\\([nrt])", lambda x: {b"n": b"\n", b"r": b"\r", b"t": b" "}[x.group(1)], p[1:-1])
            parts.append(re.sub(rb"\\(.)", rb"\1", s).decode("latin-1", "replace"))
        out.append("".join(parts))
    return "\n".join(out)


def _pdf_text(b):
    if b"/Encrypt" in b:
        return "", "unreadable"
    chunks = []
    for m in re.finditer(rb"stream\r?\n", b):
        end = b.find(b"endstream", m.end())
        if end < 0:
            continue
        raw = data = b[m.end():end]
        if b"FlateDecode" in b[max(0, m.start() - 800):m.start()]:
            try:
                data = zlib.decompress(raw)
            except Exception:  # noqa: BLE001 - non-zlib stream: keep raw bytes
                data = raw
        if b"Tj" in data or b"TJ" in data:
            chunks.append(_pdf_strings(data))
        if sum(len(c) for c in chunks) > 400000:
            break
    lines = [re.sub(r"[ \t]+", " ", x).strip() for c in chunks for x in c.replace("\x00", " ").split("\n")]
    txt = "\n".join([l for l in lines if l])
    if not txt:  # fall back to the document info dictionary only
        for m in re.finditer(rb"/(?:Title|Author|Subject)\s*\(((?:\\.|[^\\()])*)\)", b):
            txt += " " + m.group(1).decode("latin-1", "replace")
    return txt, ("ok" if len(txt) > 20 else "no_text_layer")


def _zip_text(path, members):
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if any(n.startswith(m) for m in members))[:40]
            buf = []
            for n in names:
                buf.extend(re.findall(r"<(?:w:t|a:t|t)[^>]*>([^<]{1,4000})</(?:w:t|a:t|t)>",
                                      z.read(n).decode("utf-8", "replace")))
            txt = norm(" ".join(buf))
            return txt, ("ok" if len(txt) > 20 else "no_text_layer")
    except Exception:  # noqa: BLE001 - corrupt container
        return "", "unreadable"


def magic_of(b, path):
    n, suf = str(path).lower(), Path(path).suffix.lower()
    if not b:
        return "empty"
    if b[:4] == b"%PDF":
        return "pdf"
    if b[:2] == b"PK":
        for ext, kind in ((".docx", "ooxml-docx"), (".xlsx", "ooxml-xlsx"), (".pptx", "ooxml-pptx")):
            if n.endswith(ext):
                return kind
        return "zip"
    if b[:4] == b"\xd0\xcf\x11\xe0":
        return "ole"
    if any(b.startswith(m) for m in IMG):
        return "image"
    if suf in TEXT_EXT:
        return "text"
    if b"\x00" in b[:4096]:
        return "binary"
    try:
        b[:4096].decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def extract(path, spec):
    b = rd(path)
    kind = magic_of(b, path)
    text, layer = "", "ok"
    if kind == "pdf":
        text, layer = _pdf_text(b)
    elif kind == "ooxml-docx":
        text, layer = _zip_text(path, ["word/document.xml"])
    elif kind == "ooxml-pptx":
        text, layer = _zip_text(path, ["ppt/slides/slide"])
    elif kind == "ooxml-xlsx":
        text, layer = _zip_text(path, ["xl/sharedStrings.xml"])
    elif kind == "text":
        text, _, _ = decode(b, spec.get("encoding_cascade") or ["utf-8", "latin-1"])
    elif kind in ("image", "zip"):
        layer = "no_text_layer"
    else:
        layer = "unreadable"
    cap = int((spec.get("limits") or {}).get("max_text_chars", 200000))
    return {"sha256": sha(b), "size": len(b), "magic": kind, "text": (text or "")[:cap], "text_layer": layer}


# ------------------------------------------------------------------ metadata
def where(loc, f):
    """Render a locator for humans without doubling the '#' separator."""
    loc = str(loc or "")
    return loc if "#" in loc else "%s#%s" % (f, loc)


def anc(i):
    return "c%d" % i


def line_at(text, pos, width=260):
    a = text.rfind("\n", 0, max(0, pos - 1))
    a = 0 if a < 0 else a + 1
    b = text.find("\n", a)
    return norm(text[a:(len(text) if b < 0 else b)])[:width]


def _title(text):
    cands = []
    for line in text[:6000].split("\n")[:40]:
        s = norm(line)
        cjk = len(CJK.findall(s))
        if not 6 <= len(s) <= 300 or (cjk < 6 and len(s) < 12):
            continue
        if re.search(r"(doi|arxiv|http|www\.|@|issn|volume|received|accepted|copyright|©)", s, re.I):
            continue
        if re.match(r"(abstract|摘要|keywords|关键词|introduction|引言)", s, re.I):
            continue
        if (sum(ch.isalpha() for ch in s) / len(s) >= 0.6 and 3 <= len(s.split()) <= 25) or cjk >= 6:
            cands.append(s)
        if len(cands) >= 4:
            break
    if not cands:
        return None, None
    best = cands[0] if cands[0].count(" ") >= 2 or len(CJK.findall(cands[0])) >= 6 else max(cands, key=len)
    return best, anc(max(0, text.find(best)))


def _authors(text):
    for line in text[:3000].split("\n")[:14]:
        s = norm(line)
        if not 6 <= len(s) <= 300 or re.search(r"(doi|arxiv|@|abstract)", s, re.I):
            continue
        words = s.split()
        if re.search(r"(,|and|;)", s) and len(words) >= 2 and \
                sum(1 for w in words if w[:1].isupper()) / len(words) >= 0.5:
            return s, anc(max(0, text.find(s)))
        if re.match(r"^[\u3400-\u9fff]{2,4}(\s*[,，、]\s*[\u3400-\u9fff]{2,4})+$", s):
            return s, anc(max(0, text.find(s)))
    return None, None


def _yearish(text, m):
    """Reject digits belonging to an arXiv id (YYYY.NNNNN) or a DOI tail."""
    return not re.match(r"\.[0-9]{4,5}", text[m.end():m.end() + 6])


def _year(text):
    for line in text[:4000].split("\n"):
        s = norm(line)
        if re.search(r"(published|accepted|copyright|©|received|issue|volume)", s, re.I):
            for m in YEAR_RE.finditer(s):
                if _yearish(s, m):
                    return int(m.group(1)), anc(max(0, text.find(s))), s[:200]
    for m in YEAR_RE.finditer(text[:6000]):
        if _yearish(text, m):
            return int(m.group(1)), anc(m.start()), line_at(text, m.start())
    return None, None, None


def _venue(text, spec):
    for line in text[:4000].split("\n"):
        s = norm(line)
        if 4 <= len(s) <= 200 and "http" not in tol(s) and any(
                mk in tol(s) for mk in spec.get("venue_markers") or []):
            return s[:160], anc(max(0, text.find(s)))
    return None, None


def _ident(text):
    m = DOI_RE.search(text)
    if m:
        d = m.group(0).rstrip(".,;)")
        return d, "doi", anc(m.start()), d
    m = ARX_RE.search(text)
    if m:
        return "arXiv:%s%s" % (m.group(1), m.group(2) or ""), "arxiv", anc(m.start()), m.group(0)
    return None, None, None, None


def meta_of(text, spec):
    meta, src = {}, {}
    ident, ikind, ia, iq = _ident(text)
    meta.update(identifier=ident, identifier_kind=ikind)
    if ident:
        src["identifier"] = {"locator": ia, "quote": iq}
    t, ta = _title(text)
    meta["title"] = t
    if t:
        src["title"] = {"locator": ta, "quote": t}
    au, aa = _authors(text)
    meta["authors"] = [au] if au else []
    meta["first_author"] = au.split(",")[0].strip() if au else None
    if au:
        src["authors"] = {"locator": aa, "quote": au}
    y, ya, yq = _year(text)
    meta["year"] = y
    if y:
        src["year"] = {"locator": ya, "quote": yq or str(y)}
    vn, va = _venue(text, spec)
    meta["venue"] = vn
    if vn:
        src["venue"] = {"locator": va, "quote": vn}
    return meta, src


def markers_of(text, spec):
    out, tl, lw = [], text[:40000], tol(text[:40000])
    for group in ("doc_type_markers", "version_markers", "source_markers"):
        for kind, words in (spec.get(group) or {}).items():
            for w in words:
                i = lw.find(tol(w))
                if i >= 0:
                    out.append({"group": group, "kind": kind, "marker": w,
                                "quote": line_at(tl, i), "locator": anc(i)})
                    break
    return out


def pick(mk, group, order):
    hits = [m for m in mk if m["group"] == group]
    for k in order:
        for m in hits:
            if m["kind"] == k:
                return m
    return None


def kw_hits(text, table, cap):
    tl = tol(text[:60000])
    scored = []
    for canon, aliases in (table or {}).items():
        found = [(tl.find(tol(a)), a) for a in aliases]
        found = [x for x in found if x[0] >= 0]
        if found:
            i, a = min(found)
            scored.append((i, canon, a))
    scored.sort()
    return [{"value": c, "marker": m, "locator": anc(i), "quote": line_at(text, i)} for i, c, m in scored[:cap]]


def facets_of(text, meta, mk, spec, layer="ok", name="", kind=""):
    """Rule-based facet candidates; a value is only asserted when a marker backs it."""
    c, src = {}, {}
    dt = pick(mk, "doc_type_markers", ["supplement", "thesis", "conference", "dataset", "preprint", "article"])
    vs = pick(mk, "version_markers", ["supplementary", "revision", "postprint", "preprint", "published"])
    st = pick(mk, "source_markers", ["publisher", "repository", "data_repository", "personal_scan"])
    cjk = len(CJK.findall(text))
    c["language"] = "zh" if cjk > max(20, 0.2 * max(1, len(text))) else ("en" if text.strip() else "unknown")
    if dt:
        c["doc_type"] = dt["kind"]
    elif layer == "unreadable" or not text.strip():
        nm = tol(name)
        c["doc_type"] = ("scan" if any(k in nm for k in ("scan", "扫描")) else
                         "supplement" if any(k in nm for k in ("supp", "_si", "附录")) else
                         "scan" if kind == "image" else "unknown")
    else:
        c["doc_type"] = "unknown"
    c["version_state"] = vs["kind"] if vs else ("dataset" if c["doc_type"] == "dataset" else "unknown")
    c["source_type"] = st["kind"] if st else "unknown"
    for k, m in (("doc_type", dt), ("version_state", vs), ("source_type", st)):
        if m:
            src[k] = {"locator": m["locator"], "quote": m["quote"], "marker": m["marker"]}
    c["year"], c["identifier"] = meta.get("year"), meta.get("identifier")
    if meta.get("year"):
        src["year"] = src.get("year") or {"locator": None, "quote": str(meta["year"])}
    if meta.get("identifier"):
        src["identifier"] = src.get("identifier") or {"locator": None, "quote": meta["identifier"]}
    mh, th = kw_hits(text, spec.get("method_keywords"), 6), kw_hits(text, spec.get("topic_keywords"), 6)
    c["method"], c["topic"] = [x["value"] for x in mh], [x["value"] for x in th]
    for k, hits in (("method", mh), ("topic", th)):
        if hits:
            src.setdefault(k, {"locator": hits[0]["locator"], "quote": hits[0]["quote"], "marker": hits[0]["marker"]})
    return c, src, {"method": mh, "topic": th}


# ------------------------------------------------------------------ discovery
def load_spec(case):
    spec, err = ljson(REF / "facet_spec.json")
    if not isinstance(spec, dict):
        spec = {"facets": [], "naming": {}, "reconciliation": {}, "limits": {}}
    overrides = []
    if isinstance(case, dict):
        for key in ("facet_spec", "facets", "catalog_schema", "rules"):
            v = case.get(key)
            if (isinstance(v, list) and v and isinstance(v[0], dict)):
                spec["facets"], _ = v, overrides.append(key)
                break
            if isinstance(v, dict) and isinstance(v.get("facets"), list):
                spec["facets"], _ = v["facets"], overrides.append(key)
                break
        for key in ("naming_template", "naming", "rename_template"):
            v = case.get(key)
            if isinstance(v, str) and "{" in v:
                spec.setdefault("naming", {})["template"] = v
                overrides.append(key)
                break
            if isinstance(v, dict):
                spec.setdefault("naming", {}).update(v)
                overrides.append(key)
                break
    return spec, overrides, err


def scan_root(root, spec):
    root, out = Path(root), []
    if not root.exists():
        return out
    skip = {".git", "__pycache__", ".ipynb_checkpoints", ".venv", "node_modules"}
    cap = int((spec.get("limits") or {}).get("max_files", 4000))
    for p in sorted(root.rglob("*")):
        if len(out) >= cap:
            break
        rel = p.relative_to(root)
        if not p.is_file() or any(x in skip or (x.startswith(".") and x not in (".", "..")) for x in rel.parts[:-1]):
            continue
        if p.name in ("case.json", "task.md") and p.parent == root:
            continue
        try:
            info = extract(p, spec)
        except Exception as exc:  # noqa: BLE001 - one broken file must not stop the scan
            info = {"sha256": None, "size": 0, "magic": "error", "text": "", "text_layer": "unreadable",
                    "error": "%s: %s" % (type(exc).__name__, exc)}
        rec = {"file": str(rel).replace("\\", "/"), "sha256": info["sha256"], "size": info["size"],
               "magic": info["magic"], "text_layer": info["text_layer"], "text": info["text"]}
        if info.get("error"):
            rec["error"] = info["error"]
        out.append(rec)
    return out


def _filename_in(s):
    m = re.search(r"([\w\u3400-\u9fff.()\[\]-]+\.(?:pdf|docx?|pptx?|xlsx?|zip|csv|tsv|json|bib|txt))", s, re.I)
    return m.group(1) if m else None


def companion_rows(path, rel, spec):
    """Parse a companion metadata table or note file into filename-keyed rows."""
    path, suf, rows = Path(path), Path(path).suffix.lower(), []
    syn = (spec.get("companion") or {}).get("header_synonyms") or {}
    cas = spec.get("encoding_cascade") or ["utf-8"]
    try:
        if suf in (".csv", ".tsv"):
            txt, _, _ = decode(rd(path), cas)
            lines = [l for l in txt.splitlines() if l.strip()]
            if not lines:
                return rows
            sep = "\t" if suf == ".tsv" else ("," if lines[0].count(",") >= lines[0].count(";") else ";")
            head = [norm(h) for h in lines[0].split(sep)]
            roles = {}
            for i, h in enumerate(head):
                for role, alist in syn.items():
                    if tol(h) in [tol(x) for x in alist]:
                        roles[role] = i
                        break
            for n, line in enumerate(lines[1:], 1):
                cells = [c.strip() for c in line.split(sep)]
                row = {r: (cells[i] if i < len(cells) else None) for r, i in roles.items()}
                if any(row.values()):
                    row["_locator"] = "%s#row:%d" % (rel, n)
                    row["_text"] = "; ".join("%s=%s" % (head[i], cells[i]) for i in range(min(len(head), len(cells))))
                    rows.append(row)
        elif suf == ".json":
            obj, err = ljson(path)
            if err or obj is None:
                return rows
            seq = obj if isinstance(obj, list) else next(
                (v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
            for n, item in enumerate(seq if isinstance(seq, list) else []):
                if not isinstance(item, dict):
                    continue
                row = {}
                for k, v in item.items():
                    for role, alist in syn.items():
                        if tol(k) in [tol(x) for x in alist]:
                            row[role] = norm(v) if not isinstance(v, list) else ", ".join(map(str, v))
                            break
                if any(row.values()):
                    row["_locator"] = "%s#item:%d" % (rel, n)
                    row["_text"] = json.dumps(item, ensure_ascii=False)[:400]
                    rows.append(row)
        elif suf == ".bib":
            txt, _, _ = decode(rd(path), cas)
            for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", txt, re.S):
                def f(k, body=m.group(2)):
                    mm = re.search(r"\b%s\s*=\s*[{\"]([^}\"]*)[}\"]" % k, body, re.I)
                    return norm(mm.group(1)) if mm else None
                row = {"file": m.group(1).strip() + ".pdf", "title": f("title"), "doi": f("doi"),
                       "authors": f("author"), "year": f("year"), "venue": f("journal") or f("booktitle")}
                row["_locator"] = "%s#entry:%s" % (rel, m.group(1).strip())
                row["_text"] = " ".join("%s=%s" % (k, v) for k, v in row.items() if v)
                rows.append(row)
        else:
            txt, _, _ = decode(rd(path), cas)
            keys = (spec.get("companion") or {}).get("version_note_keywords") or []
            for n, line in enumerate(txt.splitlines(), 1):
                s = norm(line)
                if s and len(s) <= 600 and any(k in tol(s) for k in keys):
                    rows.append({"file": _filename_in(s), "version_note": s,
                                 "_locator": "%s#L%d" % (rel, n), "_text": s})
    except Exception:  # noqa: BLE001 - parse failure is recorded, not fatal
        return rows
    return rows


def pairs_of(files, spec):
    rec = spec.get("reconciliation") or {}
    min_tok = int(rec.get("min_title_tokens", 3))
    out, seen = [], set()

    def add(fs, rel, basis, loc, quote, reason):
        key = tuple(sorted(fs)) + (rel,)
        if key in seen or len(set(fs)) < 2:
            return
        seen.add(key)
        out.append({"pair_id": "P%02d" % (len(out) + 1), "files": fs, "relation_hint": rel, "basis_hint": basis,
                    "evidence_locator": loc, "evidence_quote": quote, "reason": reason})

    by_sha, by_doi, by_title = {}, {}, {}
    for f in files:
        if f.get("sha256"):
            by_sha.setdefault(f["sha256"], []).append(f["file"])
        ident = tol(f["meta"].get("identifier") or "")
        if ident and not ident.startswith("arxiv"):
            by_doi.setdefault(ident.rstrip(".,;"), []).append(f["file"])
        tk = toks(f["meta"].get("title") or "")
        if len(tk) >= min_tok:
            fa = toks(f["meta"].get("first_author") or "")
            by_title.setdefault(" ".join(tk[:8]) + "|" + (fa[0] if fa else ""), []).append(f["file"])
    fmap = {f["file"]: f for f in files}
    for h, fs in sorted(by_sha.items()):
        if len(fs) > 1:
            add(fs, "duplicate", "sha256", "%s#sha256" % fs[0], h[:16], "identical content (sha256)")
    for d, fs in sorted(by_doi.items()):
        if len(fs) > 1:
            states = {fmap[x]["facets"].get("version_state") for x in fs}
            rel = "preprint_vs_published" if ("preprint" in states and states & {"published", "postprint"}) else "version_chain"
            add(fs, rel, "doi", (fmap[fs[0]]["meta_src"].get("identifier") or {}).get("locator") or "%s#text" % fs[0],
                d, "same DOI, different files")
    for _k, fs in sorted(by_title.items()):
        if len(fs) > 1 and len({fmap[x]["sha256"] for x in fs}) > 1:
            add(fs, "version_chain", "metadata", "%s#title" % fs[1],
                norm(fmap[fs[1]]["meta"].get("title"))[:120], "same title/first-author key")
    stems = {f["file"]: set(t for t in toks(Path(f["file"]).stem) if not (t.isdigit() and len(t) != 4)) for f in files}
    fl = sorted(stems)
    for i in range(len(fl)):
        for j in range(i + 1, len(fl)):
            a, b = stems[fl[i]], stems[fl[j]]
            if (len(a) >= 2 and len(b) >= 2 and (a <= b or b <= a)
                    and fmap[fl[i]]["sha256"] != fmap[fl[j]]["sha256"] and fmap[fl[i]]["sha256"] != fmap[fl[j]]["sha256"]):
                add([fl[i], fl[j]], "rename_alias", "metadata", "%s#filename" % fl[j], Path(fl[j]).name,
                    "one file name is an alias of the other")
    for f in files:
        for note in f.get("notes") or []:
            named = _filename_in(note.get("quote") or "")
            for other in files:
                if (named and other["file"] != f["file"] and Path(other["file"]).name == named
                        and other.get("sha256") != f.get("sha256")):
                    add([f["file"], other["file"]], "rename_alias", "version_note", note["locator"],
                        note["quote"][:200], "administrative note names the other file")
    return out


DECIDE = {"duplicate": ("keep_both", "same bytes: keep canonical copy, archive the rest"),
          "preprint_vs_published": ("keep_both", "preprint and published kept side by side"),
          "version_chain": ("version_chain", "same work, several versions: published is primary"),
          "supplement": ("keep_both", "supplement attached to the main paper"),
          "rename_alias": ("merge", "alias resolved to the canonical name"),
          "needs_human": ("needs_human", "evidence insufficient: keep as is")}


def default_decisions(pairs):
    out = []
    for p in pairs:
        dec, note = DECIDE.get(p["relation_hint"], DECIDE["needs_human"])
        out.append({"decision_id": "D%02d" % (len(out) + 1), "files": p["files"], "relation": p["relation_hint"],
                    "decision": dec, "basis": p["basis_hint"], "evidence_locator": p["evidence_locator"],
                    "evidence_quote": p["evidence_quote"], "evidence_verified": None, "decided_by": "script_default",
                    "rollback_action": "restore %s from _archive/%s" % (p["files"][-1], Path(p["files"][-1]).name),
                    "note": note})
    return out


# ------------------------------------------------------------------ evidence
def _short(q, min_q):
    return len(q) < min_q and len(CJK.findall(q)) < 4 and not (q.isdigit() and 4 <= len(q) <= 5)


def quote_ok(texts, locator, quote, min_q=8):
    """Verbatim quote check near the locator window, then over the whole file."""
    if not locator or not quote:
        return False, "missing_input"
    loc, q = str(locator), norm(quote)
    if loc in texts:  # companion row / line locator used verbatim
        if _short(q, min_q):
            return False, "quote_too_short"
        return (True, "exact") if q.lower() in norm(texts[loc]).lower() else (False, "not_found")
    f, _, an = loc.partition("#")
    if f not in texts:
        cand = [k for k in texts if k.endswith(f) or f.endswith(k)]
        if not cand:
            return False, "unknown_file"
        f = cand[0]
    if _short(q, min_q):
        return False, "quote_too_short"
    body = texts[f]
    m = re.match(r"c(\d+)$", an or "")
    if m:
        off = int(m.group(1))
        if q.lower() in norm(body[max(0, off - 400): off + max(600, len(q) * 3)]).lower():
            return True, "window"
    if q.lower() in norm(body).lower():
        return True, "file"
    return False, "not_found"


def evidence_ok(fc, value, src, texts, fname, min_q=8):
    """Verified quote, else path evidence, else an explicit judgment (schema-declared)."""
    ok, scope = quote_ok(texts, (src or {}).get("locator"), (src or {}).get("quote"), min_q)
    if ok:
        return True, scope
    if (fc or {}).get("evidence_kind") in ("judgment", "path_or_judgment"):
        vals = value if isinstance(value, list) else [value]
        if any(str(v) and tol(v) in tol(fname) for v in vals if v not in (None, "")):
            return True, "path"
        return True, "judgment"
    return False, scope


def build_texts(files, companions):
    texts = {f["file"]: norm(f.get("text") or "") for f in files}
    for c in companions:
        for row in c.get("rows") or []:
            if row.get("_locator"):
                texts[row["_locator"]] = norm(row.get("_text") or "")
    return texts


# ------------------------------------------------------------------ schema
def default_schema(spec):
    return [{"facet": fc.get("facet"), "definition": fc.get("definition", ""),
             "allowed_values": fc.get("allowed_values"), "pattern": fc.get("pattern"),
             "rule": fc.get("rule", ""), "multi": bool(fc.get("multi")),
             "sources_priority": fc.get("sources_priority", []),
             "evidence_kind": fc.get("evidence_kind") or "quote"} for fc in spec.get("facets") or []]


def schema_of(draft, spec):
    sch = draft.get("facet_schema")
    spec_kind = {fc.get("facet"): (fc.get("evidence_kind") or "quote") for fc in spec.get("facets") or []}
    if isinstance(sch, list) and sch and all(isinstance(x, dict) and x.get("facet") for x in sch):
        return [{"facet": str(x.get("facet")), "definition": norm(x.get("definition") or ""),
                 "allowed_values": x.get("allowed_values") if isinstance(x.get("allowed_values"), list) else None,
                 "pattern": x.get("pattern") or None, "rule": norm(x.get("rule") or ""),
                 "multi": bool(x.get("multi")), "sources_priority": x.get("sources_priority") or [],
                 "evidence_kind": x.get("evidence_kind") or spec_kind.get(str(x.get("facet")), "quote")}
                for x in sch], "draft"
    return default_schema(spec), "spec_default"


def valid_value(fc, v):
    if v is None or v == "":
        return True
    for x in (v if isinstance(v, list) else [v]):
        if x is None:
            continue
        allowed = fc.get("allowed_values")
        if isinstance(allowed, list) and allowed and str(x) not in [str(a) for a in allowed]:
            return False
        if fc.get("pattern"):
            try:
                if not re.match(fc["pattern"], str(x)):
                    return False
            except re.error:
                pass
    return True


# ------------------------------------------------------------------ harness io
def roots(a):
    """Resolve input/work/output with official-harness first choice and local fallback."""
    base = HERE.parent
    app = Path("/app")
    ind = Path(a.input) if getattr(a, "input", None) else (
        Path("/input") if Path("/input").exists() else base / "input")
    work = Path(a.work) if getattr(a, "work", None) else (app / "work" if app.is_dir() else base / "work")
    out = Path(a.output) if getattr(a, "output", None) else (app / "output" if app.is_dir() else base / "output")
    for d in (work, out):
        d.mkdir(parents=True, exist_ok=True)
    return ind, work, out


def read_case(ind):
    p = Path(ind) / "case.json"
    if p.exists():
        o, err = ljson(p)
        return (o if isinstance(o, dict) else {}), err, str(p)
    for q in sorted(Path(ind).rglob("*.json"))[:200]:
        o, err = ljson(q)
        if isinstance(o, dict) and ("output_contract" in o or "case_id" in o):
            return o, None, str(q)
    return {}, "case_json_missing", None


def envelope(case, ind, out):
    return {"case_id": case.get("case_id") if isinstance(case, dict) else None, "status": "partial",
            "result": {}, "sources": [], "evidence_index": [], "uncertainties": [], "errors": [],
            "degradations": [], "changes": [], "contract_mapping": {}, "contract_fields": {},
            "method_notes": [], "runtime": {"tool": TOOL, "version": V, "python": sys.version.split()[0],
                                            "input_root": str(ind), "output_root": str(out), "command": None}}
