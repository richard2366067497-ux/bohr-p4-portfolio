"""library-curator curation layer (stdlib only).

Dataset-level work: bounded scan, sha256/permission/mtime inventory, document-type rules,
controlled tag assignment, naming-template rendering with a documented degradation ladder,
duplicate grouping, version-chain grouping, verified copy, tree listing and index lookup.
Sources are never modified or deleted.
"""

import difflib
import json
import os
import re
import shutil
import stat

import library_text as T

DOC_TYPES = ("journal_article", "preprint", "conference", "thesis", "dataset",
             "supplement", "scan", "note", "other")
SKIP_CODES = ("corrupt_file", "encrypted_pdf", "no_text_layer", "permission_denied",
              "unreadable_encoding", "missing_on_disk", "unsupported_type", "out_of_scope")
RELATIONSHIPS = ("preprint", "accepted", "published", "supplement", "revision", "undetermined")
DATA_EXT = {".parquet", ".h5", ".hdf5", ".nc", ".tar", ".gz", ".npy", ".npz", ".mat",
            ".fa", ".fasta", ".vcf", ".zip"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
NOTE_HINT = re.compile(r"note|admin|readme|manifest|version|log|inventory|alias|catalog|answer", re.I)

DOC_TYPE_RULES = [
    ("preprint", re.compile(r"\b(preprint|arxiv|biorxiv|medrxiv|research\s*square|ssrn|chemrxiv|techrxiv)\b", re.I)),
    ("supplement", re.compile(r"(supplement|supporting\s*information|suppl[_-]|_si\b|\bsi[_-]\b)", re.I)),
    ("thesis", re.compile(r"(thesis|dissertation|学位论文|毕业论文|habilitation)", re.I)),
    ("conference", re.compile(r"(proceedings|conference|symposium|workshop|abstract\s*book|poster)", re.I)),
    ("scan", re.compile(r"(\bscan(ned)?\b|扫描件|\bocr\b)", re.I)),
]

# Controlled topic vocabulary: canonical tag -> surface forms that count as evidence.
TOPIC_LEXICON = {
    "catalysis": ["catalys", "catalyt", "catalyst"],
    "photocatalysis": ["photocataly"],
    "electrocatalysis": ["electrocataly"],
    "materials": ["material", "alloy", "ceramic", "polymer", "composite", "nanoparticle", "perovskite"],
    "battery": ["battery", "batteries", "lithium", "anode", "cathode", "electrolyte"],
    "solar-cell": ["solar cell", "photovoltaic"],
    "machine-learning": ["machine learning", "deep learning", "neural network", "random forest"],
    "spectroscopy": ["spectroscop", "xrd", "xps", "nmr", "raman", "ftir", "diffraction"],
    "microscopy": ["microscop", "sem image", "tem image", "\bafm\b"],
    "genomics": ["genom", "sequencing", "transcriptom", "rna-seq", "variant calling"],
    "proteomics": ["proteom", "mass spectrometry", "protein structure", "peptide"],
    "bioinformatics": ["bioinformatic", "alignment", "annotation", "database"],
    "ecology": ["ecolog", "biodiversity", "field survey", "species richness"],
    "climate": ["climate", "emission scenario", "carbon budget", "warming"],
    "clinical": ["clinical trial", "patient cohort", "randomised", "randomized", "placebo"],
    "neuroscience": ["neuro", "brain", "fmri", "eeg", "neuron"],
    "physics": ["quantum", "condensed matter", "superconduct", "magnetism", "phonon"],
    "mathematics": ["theorem", "lemma", "proof", "manifold", "stochastic"],
    "software": ["software package", "open-source", "github repository", "toolkit"],
    "dataset": ["dataset", "benchmark", "data release", "corpus"],
}
SYNONYM_MERGE = {"catalysis": ["catalytical", "catalytic"], "photocatalysis": ["photocatalytic"],
                 "machine-learning": ["ml", "deep-learning"], "solar-cell": ["photovoltaics", "pv"],
                 "dataset": ["data-set", "datasets"]}


# ------------------------------------------------------------------ classification
def looks_metadata_table(rec):
    return bool(re.search(r"title|doi|author|year|journal", " ".join(rec.get("table_keys") or []), re.I))


def kind_of(rec):
    ext = rec["ext"]
    if ext in (".md", ".txt", ".yml", ".yaml", ".log"):
        return "admin_note"
    if NOTE_HINT.search(rec["name"]) and ext not in (".pdf", ".docx"):
        return "admin_note"
    if ext == ".bib" or (ext in T.TABLE_EXT and looks_metadata_table(rec)):
        return "metadata_table"
    if ext in IMG_EXT:
        return "image"
    if ext in DATA_EXT:
        return "data"
    return "document"


def doc_type_of(rec):
    """-> (doc_type, locator, rule) ; every branch names the evidence it used."""
    for name, rx in DOC_TYPE_RULES:
        if rx.search(rec["name"]):
            return name, "file:%s" % rec["rel"], rx.pattern
    if rec["ext"] in IMG_EXT or rec["text_quality"] == "no_text_layer":
        loc = "text:%s#p1" % rec["rel"] if rec["pages"] else "file:%s" % rec["rel"]
        return "scan", loc, "no text layer / image"
    if rec["ext"] in (".xlsx", ".xlsm") or rec["kind"] == "data":
        return "dataset", "file:%s" % rec["rel"], "extension/kind"
    if rec["kind"] in ("admin_note", "metadata_table") or rec["ext"] in (".md", ".txt", ".bib", ".yml", ".yaml"):
        return "note", "file:%s" % rec["rel"], "note/manifest kind"
    blob = " ".join([rec["name"], (rec.get("pages") or [""])[0][:1200],
                     str((rec["meta"].get("journal") or {}).get("value", ""))])
    for name, rx in DOC_TYPE_RULES:
        m = rx.search(blob)
        if m:
            loc = "text:%s#p1" % rec["rel"] if rec["pages"] else "file:%s" % rec["rel"]
            return name, loc, m.group(0)
    if (rec["meta"].get("doi") or {}).get("value"):
        return "journal_article", rec["meta"]["doi"].get("locator"), "doi present"
    return "other", "file:%s" % rec["rel"], "no positive evidence"


def auto_tags(rec, limit=6):
    text = " ".join([rec["name"], (rec.get("pages") or [""])[0][:3000],
                     str((rec["meta"].get("title") or {}).get("value", ""))]).lower()
    tags, seen = [], set()
    for tag, forms in TOPIC_LEXICON.items():
        if any(f.lower() in text for f in forms):
            tags.append(tag)
            seen.add(tag)
        if len(tags) >= limit:
            break
    if not tags:
        for w in T.words((rec["meta"].get("title") or {}).get("value") or rec["name"]):
            lw = w.lower()
            if len(lw) >= 5 and lw not in T.STOP and lw not in seen:
                tags.append(lw)
                seen.add(lw)
            if len(tags) >= 2:
                break
    return tags


def auto_classify(rec):
    dtype, loc, why = doc_type_of(rec)
    year = (rec["meta"].get("year") or {}).get("value")
    tags = auto_tags(rec)
    topic = next((t for t in tags if t in TOPIC_LEXICON), "general")
    segs = [dtype] + ([year] if year else []) + [topic]
    return {"doc_id": rec["doc_id"], "path": rec["rel"], "class_path": "/".join(segs),
            "doc_type": dtype, "tags": tags, "basis": loc,
            "quote": (rec.get("pages") or [""])[0][:200] if rec["pages"] else "",
            "metadata": {k: v.get("value") for k, v in rec["meta"].items() if not k.endswith("_only")},
            "meta_locators": {k: v.get("locator") for k, v in rec["meta"].items()},
            "confidence": "low", "auto": True, "rule": why}


# ------------------------------------------------------------------ naming
def sanitize(name, maxlen=180, allow_empty=False):
    s = T.norm(name)
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip(" .-")[:maxlen].rstrip(" .-")
    if s:
        return s
    return "" if allow_empty else "untitled"


def title_short(title, maxlen=60):
    raw = T.words(title or "")
    ws = [w for w in raw if w.lower() not in T.STOP] or raw
    while ws and ws[0].lower() in T.STOP:
        ws.pop(0)
    if not ws:
        return ""
    return sanitize("-".join(ws[:8]), maxlen, allow_empty=True)


def surname(authors):
    first = re.split(r"[,;]| and ", T.norm(authors or ""))[0].strip()
    toks = first.split()
    if not toks:
        return ""
    if len(toks) == 1:
        return sanitize(toks[0], 40)
    if re.fullmatch(r"[A-Z]{2,}", toks[0]):
        return sanitize(toks[1], 40)
    return sanitize(toks[-1], 40)


def render_name(template, meta, orig_name, sha=None):
    """-> (filename, degradations[], fields_used[]) ; every dropped segment is recorded."""
    tpl = template or "{first_author}-{year}-{title_short}"
    meta = meta or {}
    vals, degr, used = {}, [], []
    fa = meta.get("first_author") or ""
    author = surname(meta.get("authors")) or (sanitize(fa, 40, allow_empty=True) if fa else "")
    journal = T.norm(meta.get("journal") or "")
    jabbr = sanitize(re.sub(r"\bof\b|\bthe\b", " ", journal).split()[0], 20) if journal else ""
    doi = meta.get("doi") or ""
    if author:
        vals["first_author"] = author
        used.append("first_author")
    else:
        vals["first_author"] = jabbr or "Anon"
        degr.append("first_author missing -> %s" % (jabbr or "Anon"))
    if meta.get("year"):
        vals["year"] = str(meta["year"])
        used.append("year")
    else:
        vals["year"] = ""
        degr.append("year missing -> year segment dropped (not guessed)")
    ts = title_short(meta.get("title") or "")
    if ts:
        vals["title_short"] = ts
        used.append("title_short")
    else:
        vals["title_short"] = sanitize(os.path.splitext(orig_name)[0], 40)
        degr.append("title missing -> original file stem used")
    vals["journal_abbrev"] = jabbr or "NoJournal"
    vals["doi_suffix"] = sanitize(re.sub(r"[^0-9A-Za-z]+", "-", doi).strip("-")[-24:], 24) if doi else "NoDOI"
    vals["doc_type"] = sanitize(meta.get("doc_type") or "doc", 20)
    vals["sha8"] = (sha or "")[:8] or "00000000"
    name = sanitize(re.sub(r"\{([a-z_0-9]+)\}", lambda m: vals.get(m.group(1), ""), tpl))
    if not name or re.fullmatch(r"[-_ ]*", name):
        name = sanitize(os.path.splitext(orig_name)[0]) or "untitled"
        degr.append("template rendered empty -> original stem used")
    if re.search(r"\{\w+\}", name):
        name = sanitize(re.sub(r"\{\w+\}", "", name))
        degr.append("unresolved placeholder removed")
    return name + os.path.splitext(orig_name)[1].lower(), degr, used


def unique_dest(existing, name):
    """Deterministic collision suffix (-v2, -v3 ...), stable across re-runs."""
    if name not in existing:
        return name
    stem, ext = os.path.splitext(name)
    i = 2
    while "%s-v%d%s" % (stem, i, ext) in existing:
        i += 1
    return "%s-v%d%s" % (stem, i, ext)


# ------------------------------------------------------------------ grouping
def dedupe_groups(recs):
    buckets = {}
    for r in recs:
        if r.get("sha256"):
            buckets.setdefault(r["sha256"], []).append(r)
    groups = []
    for sha, members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda r: (r["rel"].count("/"), len(r["rel"]), r["rel"]))
        groups.append({"sha256": sha, "keep": ordered[0]["rel"],
                       "archive": [m["rel"] for m in ordered[1:]],
                       "members": [{"path": m["rel"], "doc_id": m["doc_id"], "size": m["size"]} for m in ordered],
                       "reason": "identical_content"})
    return groups


def work_key(rec):
    doi = T.norm_key((rec["meta"].get("doi") or {}).get("value", ""))
    if doi:
        return "doi:" + doi
    title = T.norm_key((rec["meta"].get("title") or {}).get("value", ""))[:60]
    if not title or len(title) < 8:
        title = re.sub(r"(19|20)\d{2}$", "", T.norm_key(os.path.splitext(rec["name"])[0]))[:60]
    return "title:%s|%s" % (title, (rec["meta"].get("year") or {}).get("value", ""))


def version_chains(recs, notes):
    buckets = {}
    for r in recs:
        k = work_key(r)
        if k and not k.endswith("|"):
            buckets.setdefault(k, []).append(r)
    chains = []
    for k, members in sorted(buckets.items()):
        if len(members) < 2 or len({m["sha256"] for m in members}) < 2:
            continue
        rel = [m["rel"] for m in members]
        evidence, quote = "", ""
        for note in notes:
            for i, line in enumerate(note.get("lines") or []):
                hits = sum(1 for m in members if os.path.splitext(m["name"])[0][:24].lower() in line.lower())
                if hits >= 2 or (hits >= 1 and re.search(r"version|preprint|accepted|published|supersed|replace", line, re.I)):
                    evidence, quote = "note:%s#L%d" % (note["rel"], i + 1), line.strip()[:300]
                    break
            if evidence:
                break
        published = [m for m in members if m.get("doc_type") == "journal_article"]
        preprints = [m for m in members if m.get("doc_type") == "preprint"]
        supp = [m for m in members if m.get("doc_type") == "supplement"]
        if evidence and re.search(r"supplement|supporting", quote, re.I):
            relationship, keep = "supplement", (published[0]["rel"] if published else rel[0])
        elif published and preprints:
            relationship, keep = "published", published[0]["rel"]
        elif evidence and re.search(r"supersed|revis|replace", quote, re.I):
            relationship, keep = "revision", rel[0]
        elif evidence and re.search(r"accepted", quote, re.I):
            relationship, keep = "accepted", rel[0]
        elif supp and published:
            relationship, keep = "supplement", published[0]["rel"]
        else:
            relationship, keep = "undetermined", rel[0]
        chains.append({"chain_id": "V%d" % (len(chains) + 1), "work_key": k, "members": rel,
                       "relationship": relationship, "keep": keep,
                       "archive": [r for r in rel if r != keep],
                       "evidence": evidence, "quote": quote,
                       "doc_types": {m["rel"]: m.get("doc_type") for m in members}})
    return chains


# ------------------------------------------------------------------ records
def build_records(root, max_files=4000, max_depth=8):
    recs, degr, errs = [], [], []
    root = os.path.abspath(root)
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        depth = 0 if rel_dir == "." else len(rel_dir.split(os.sep))
        if depth >= max_depth:
            dirnames[:] = []
            degr.append({"stage": "scan", "detail": "depth cap %d at %s" % (max_depth, rel_dir)})
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.startswith("."):
                paths.append(os.path.join(dirpath, fn))
            if len(paths) >= max_files:
                degr.append({"stage": "scan", "detail": "file cap %d reached" % max_files})
                break
        if len(paths) >= max_files:
            break
    for i, ap in enumerate(paths):
        rec = {"doc_id": "D%02d" % (i + 1), "rel": os.path.relpath(ap, root).replace(os.sep, "/"),
               "abs": ap, "name": os.path.basename(ap), "ext": os.path.splitext(ap)[1].lower(),
               "size": 0, "sha256": None, "mtime": None, "readable": False, "permission": None,
               "kind": "document", "text_quality": "unsupported_type", "pages": [], "lines": [],
               "meta": {}, "flags": [], "table_keys": []}
        try:
            st = os.stat(ap)
            rec.update(size=st.st_size, mtime=T.iso(st.st_mtime),
                       permission=stat.filemode(st.st_mode)[-9:], readable=os.access(ap, os.R_OK))
        except OSError as e:
            rec["flags"].append("stat_failed")
            errs.append({"stage": "stat", "path": rec["rel"], "detail": str(e)[:120]})
        try:
            rec["sha256"] = T.sha256_file(ap)
        except OSError as e:
            rec["flags"].append("hash_failed")
            errs.append({"stage": "hash", "path": rec["rel"], "detail": str(e)[:120]})
        pages, quality, flags = T.pages_of(T_PATH(ap))
        rec["pages"], rec["text_quality"] = pages, quality
        rec["flags"].extend(flags)
        if rec["ext"] in T.TABLE_EXT and quality != "corrupt":
            rows = T.parse_table(T_PATH(ap))
            if rows:
                rec["table_keys"] = list(rows[0].keys())[:20]
                rec["rows"] = rows[:400]
        if pages and rec["ext"] in T.TEXT_EXT:
            rec["lines"] = pages[0].split("\n")[:600]
        rec["kind"] = "corrupt" if quality == "corrupt" else kind_of(rec)
        T.enrich(rec)
        rec["doc_type"], rec["doc_type_locator"], rec["doc_type_rule"] = doc_type_of(rec)
        rec["auto"] = auto_classify(rec)
        recs.append(rec)
    return recs, degr, errs


def T_PATH(ap):
    from pathlib import Path
    return Path(ap)


def apply_companion_tables(recs):
    """Attach metadata rows from companion tables to the documents they describe."""
    tables = [r for r in recs if r.get("rows") and r["kind"] in ("metadata_table", "admin_note")]
    docs = [r for r in recs if r["kind"] == "document" or r["ext"] == ".pdf"]
    hits = 0
    for t in tables:
        for d in docs:
            row, lineno = table_match(d, t["rows"])
            if not row:
                continue
            extra = {}
            for k, v in row.items():
                kk = T.norm(k).lower()
                for field, names in (("title", ("title", "articletitle", "documenttitle")),
                                     ("authors", ("author", "authors", "creator")),
                                     ("year", ("year", "date", "issued", "publicationyear")),
                                     ("journal", ("journal", "venue", "container", "publication")),
                                     ("doi", ("doi", "identifier"))):
                    if kk in names and v:
                        extra[field] = {"value": T.norm(v), "confidence": "medium"}
            if extra:
                T.merge_meta(d, extra, "note:%s#L%d" % (t["rel"], lineno))
                hits += 1
    return hits


def table_match(rec, rows):
    """Match a table row to a document: explicit file/path column first, then title overlap."""
    best, best_score = None, 0.0
    stem = T.norm_key(os.path.splitext(rec["name"])[0])
    own_title = T.norm_key(((rec.get("meta") or {}).get("title") or {}).get("value", ""))
    has_file_col = False
    for i, row in enumerate(rows):
        flat = {T.norm_key(k): (v or "") for k, v in row.items()}
        for k, v in flat.items():
            if k in ("file", "filename", "path", "filepath", "pdf", "attachment", "doc"):
                has_file_col = True
                nv = T.norm_key(v)
                if nv and (nv == stem or nv in stem or stem in nv):
                    return row, i + 2
        cand = next((v for k, v in flat.items()
                     if k in ("title", "articletitle", "name", "documenttitle") and v), "")
        if not cand:
            continue
        target = own_title or stem
        score = difflib.SequenceMatcher(None, cand[:160], target[:160]).ratio() if target else 0.0
        if score > best_score:
            best, best_score = (row, i + 2), score
    if has_file_col:
        return None, None
    return (best if best_score >= 0.62 else (None, None))


# ------------------------------------------------------------------ filesystem
def copy_verified(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return T.sha256_file(dst)


def remove_file(p):
    try:
        if os.path.isfile(p):
            os.remove(p)
            return True
    except OSError:
        return False
    return False


def tree_lines(root, limit=400):
    out, root = [], os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        depth = os.path.relpath(dirpath, root).count(os.sep) if dirpath != root else -1
        out.append("  " * (depth + 1) + os.path.basename(dirpath) + "/" if dirpath != root else root + "/")
        for fn in sorted(filenames):
            out.append("  " * (depth + 2) + fn)
            if len(out) >= limit:
                out.append("… (truncated)")
                return out
    return out


def dir_stats(root):
    dirs = files = total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirs += len(dirnames)
        files += len(filenames)
        for fn in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return {"dirs": dirs, "files": files, "bytes": total}


def load_json(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return json.load(fh), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:200])


def dump_json(p, obj):
    d = os.path.dirname(os.path.abspath(p))
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return str(p)


def find_rec(recs, path):
    """Resolve an Agent-written path against the index (tolerates ./ and parent prefixes)."""
    if not path:
        return None
    p = str(path).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    for r in recs:
        if p in (r["rel"], r["name"]):
            return r
    for r in recs:
        if p.endswith("/" + r["rel"]) or r["rel"].endswith("/" + p):
            return r
    cands = [r for r in recs if r["name"] == os.path.basename(p)]
    return cands[0] if len(cands) == 1 else None
