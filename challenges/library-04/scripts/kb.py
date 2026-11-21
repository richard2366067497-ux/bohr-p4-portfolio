#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb.py — knowledge-base index, version families, retrieval and verbatim locators.

Deterministic work only (no model calls, no judgement):
  * discover /input, case.json, material roots, questions and metadata sidecars;
  * index every real file (sha256, aliases, permission, text layer, page/section/paragraph);
  * group files into version families, flag byte-identical duplicates;
  * cross-version numeric diff candidates (older edition A vs newer edition B);
  * lexical retrieval with section weighting and document-frequency filtering;
  * verbatim quote location with page/section recovery.
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from parse import (AUX_NAME, CHUNK_CHARS, COPY_MARK, DATE_TOKEN, INSTRUCTION_NAMES, MAX_BYTES,
                   NUM, VER_TOKEN, docx_units, guess_type, human, jload, jdump, norm_q, norm_ws,
                   load_sidecars, pdf_text, pptx_units, read_text, sha256_file, split_plain,
                   tokens, xlsx_units)

VERSION = "1.0.0"
CLAIM_STATUS = {"supported", "conflicting", "insufficient", "not_in_kb"}
LEVELS = {"none", "low", "medium", "high"}


# ------------------------------------------------------------------- discovery
def first_existing(paths):
    for p in paths:
        try:
            if p and Path(p).exists():
                return Path(p)
        except Exception:
            continue
    return None


def find_input(arg=None):
    cands = []
    if arg:
        cands.append(arg)
    env = os.environ.get("KB_INPUT")
    if env:
        cands.append(env)
    cands += ["/input", "/app/input", "./input"]
    return first_existing(cands) or Path("/input")


BAD_CASE = re.compile(r"(?i)(gold|answer_key|rubric|score|expected|verifier|whiteboard|白板)")


def find_case(inp, arg=None):
    inp = Path(inp)
    if arg:
        p = Path(arg)
        if p.exists():
            return p, None
    for name in ("case.json", "case_input.json", "input.json"):
        p = inp / name
        if p.is_file():
            return (p, None) if isinstance(jload(p), dict) else (p, f"{name} exists but is not a valid JSON object")
    best = None
    try:
        for p in sorted(inp.rglob("*.json")):
            if BAD_CASE.search(p.name) or BAD_CASE.search(str(p.parent)):
                continue
            data = jload(p)
            if isinstance(data, dict) and any(
                    k in data for k in ("output_contract", "task_instruction", "questions",
                                        "queries", "library_root", "case_id")):
                if best is None or p.name == "case.json":
                    best = p
    except Exception:
        pass
    return best, (None if best else "case.json not found")


ROOT_KEYS = ("library_root", "library_dir", "materials_root", "material_root", "docs_root",
             "document_root", "source_dir", "corpus_root", "kb_root", "library", "materials")
SUB_DIRS = ("library", "files", "artifacts", "documents", "docs", "kb", "corpus", "materials",
            "data", "source", "sources", "input_files")


def find_roots(inp, case):
    inp = Path(inp)
    roots, notes = [], []
    if isinstance(case, dict):
        for k in ROOT_KEYS:
            v = case.get(k)
            for cand in (v if isinstance(v, list) else [v]):
                if not isinstance(cand, str):
                    continue
                p = Path(cand)
                for q in ([p] if p.is_absolute() else [inp / p, inp / p.name]):
                    if q.is_dir():
                        roots.append(q.resolve())
                        notes.append(f"library root from case.json key '{k}': {q}")
                        break
    for name in SUB_DIRS:
        p = inp / name
        if p.is_dir():
            roots.append(p.resolve())
            notes.append(f"library root discovered at {p}")
    roots = [r for r in roots if str(r) != str(inp)]
    if not roots:
        roots = [inp.resolve()]
        notes.append("no dedicated library directory: using /input root as library")
    seen, uniq = set(), []
    for r in roots:
        if str(r) not in seen:
            seen.add(str(r))
            uniq.append(r)
    return uniq, notes


def find_questions(case):
    """Recover the question list from several possible key names; report the key used."""
    if not isinstance(case, dict):
        return [], None
    for key in ("questions", "question_list", "queries", "search_requests", "searches",
                "tasks", "qas", "qa", "requests", "问题清单", "问题"):
        val = case.get(key)
        if isinstance(val, list) and val:
            return val, key
        if isinstance(val, dict) and val:
            flat = []
            for k, v in val.items():
                if isinstance(v, dict):
                    v.setdefault("question_id", k)
                    flat.append(v)
                elif isinstance(v, str):
                    flat.append({"question_id": k, "question": v})
            if flat:
                return flat, key
    return [], None


def normalise_questions(raw):
    out = []
    for i, item in enumerate(raw or [], 1):
        if isinstance(item, str):
            out.append({"question_id": f"Q{i}", "question": item.strip(), "raw": item})
            continue
        if not isinstance(item, dict):
            out.append({"question_id": f"Q{i}", "question": str(item)})
            continue
        qid = None
        for k in ("question_id", "qid", "id", "q_id", "key", "name"):
            if isinstance(item.get(k), (str, int)) and str(item.get(k)).strip():
                qid = str(item.get(k)).strip()
                break
        qtext = None
        for k in ("question", "query", "text", "task", "prompt", "content", "q", "问题", "问句"):
            if isinstance(item.get(k), str) and item[k].strip():
                qtext = item[k].strip()
                break
        if not qtext:
            qtext = json.dumps(item, ensure_ascii=False)[:400]
        rec = {"question_id": qid or f"Q{i}", "question": qtext}
        for extra in ("scope", "evidence_requirements", "expected_evidence", "type",
                      "question_type", "keywords", "must_cite"):
            if extra in item:
                rec[extra] = item[extra]
        out.append(rec)
    return out


# ------------------------------------------------------------------ index build
def version_tokens(name):
    low = name.lower()
    out, dates = [], []
    for m in VER_TOKEN.finditer(low):
        raw = m.group(1).replace("_", ".")
        try:
            out.append(float(raw))
        except Exception:
            pass
    for m in DATE_TOKEN.finditer(low):
        try:
            y, mo = int(m.group(1)), int(m.group(2) or 1)
            d = int(m.group(3) or 1)
            dates.append(y * 10000 + mo * 100 + d)
        except Exception:
            pass
    return out, dates


def family_key(name, metadata=None):
    stem = Path(name).stem.lower()
    for key in ("title", "document_title", "doc_title", "work", "series"):
        if isinstance(metadata, dict) and isinstance(metadata.get(key), str) and metadata[key].strip():
            stem = metadata[key].strip().lower()
            break
    s = COPY_MARK.sub(" ", stem)
    s = VER_TOKEN.sub(" ", s)
    s = DATE_TOKEN.sub(" ", s)
    s = re.sub(r"(?i)\.(pdf|docx?|xlsx?|pptx?|csv|md|txt)$", " ", s)
    s = re.sub(r"[\s_\-—–·.,;:()（）\[\]【】]+", "", s)
    s = re.sub(r"\d{1,2}$", "", s) if len(s) > 6 else s
    return s or stem


def build_index(inp, case_path, case, roots, log):
    docs, chunks, errors, skipped = [], [], [], []
    seen_paths = set()
    files = []
    for root in roots:
        try:
            for p in sorted(Path(root).rglob("*")):
                if not p.is_file() or p.is_symlink():
                    continue
                if p.name in INSTRUCTION_NAMES:
                    continue
                if BAD_CASE.search(p.name):
                    continue
                rp = str(p.resolve())
                if rp in seen_paths:
                    continue
                seen_paths.add(rp)
                files.append(p)
        except Exception as exc:
            errors.append({"stage": "walk", "path": str(root), "error": str(exc)})
    doc_paths = [str(p) for p in files]
    aux, aux_applied = load_sidecars(roots, case, doc_paths)
    aux_by_path = {}
    for block in aux:
        for path, fields in (block.get("applied") or {}).items():
            merged = aux_by_path.setdefault(path, {})
            for k, v in fields.items():
                merged.setdefault(k, v)

    family_members, sha_map = {}, {}
    for idx, path in enumerate(files, 1):
        doc_id = f"D{idx:02d}"
        try:
            st = path.stat()
            size = st.st_size
            mtime = int(st.st_mtime)
        except Exception:
            size, mtime = 0, 0
        ext = path.suffix.lower()
        dtype = guess_type(ext)
        rec_path = str(path).replace("\\", "/")
        rel = rec_path
        for root in roots:
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
                break
            except Exception:
                continue
        entry = {
            "doc_id": doc_id, "path": rel, "abs_path": rec_path, "name": path.name,
            "dir": str(Path(rel).parent).replace("\\", "/"),
            "ext": ext, "type": dtype, "size": size, "sha256": None, "mtime": mtime,
            "permission": "readable", "readable": False, "no_text_layer": False,
            "pages": None, "sections": [], "chars": 0, "chunks": 0,
            "family": None, "version": None, "version_rank": None, "dup_of": None,
            "aliases": [], "metadata": {}, "extract_method": None, "note": None,
        }
        meta = dict(aux_by_path.get(rec_path, {}))
        entry["metadata"] = meta
        if isinstance(meta.get("aliases") or meta.get("alias"), (list, str)):
            al = meta.get("aliases") or meta.get("alias")
            entry["aliases"] = [str(x) for x in (al if isinstance(al, list) else [al])]
        if isinstance(meta.get("version"), (str, int)):
            entry["version"] = str(meta["version"]).strip()
        if isinstance(meta.get("title"), str) and meta["title"].strip():
            entry["aliases"].append(meta["title"].strip())
        if size == 0:
            entry["permission"] = "empty"
            entry["note"] = "zero-byte file"
            docs.append(entry)
            continue
        if size > MAX_BYTES:
            entry["note"] = f"skipped: {human(size)} exceeds {human(MAX_BYTES)} parse budget"
            skipped.append(entry["doc_id"])
            docs.append(entry)
            continue
        entry["sha256"] = sha256_file(path)
        if entry["sha256"] and entry["sha256"] in sha_map:
            entry["dup_of"] = sha_map[entry["sha256"]]
            entry["permission"] = "readable"
        elif entry["sha256"]:
            sha_map[entry["sha256"]] = doc_id
        units, method, note = [], None, None
        try:
            if dtype == "pdf":
                pages, method, note = pdf_text(path)
                if pages:
                    for pno, page_text in enumerate(pages, 1):
                        for kind, sec, txt in split_plain(page_text):
                            units.append((pno, sec, txt))
            elif dtype == "docx":
                units = [("page", s, t) for kind, s, t in docx_units(path)]
                method = "zipfile word/document.xml"
            elif dtype == "pptx":
                units = pptx_units(path)
                method = "zipfile ppt/slides"
            elif dtype == "xlsx":
                units = xlsx_units(path)
                method = "zipfile xl/worksheets"
            elif dtype in ("text", "csv", "structured", "json"):
                text = read_text(path)
                if text:
                    units = [(None, s, t) for kind, s, t in split_plain(text)]
                    method = "plain text decode"
                else:
                    note = "decode failed"
            elif dtype in ("image", "binary", "doc_legacy", "xls_legacy"):
                note = f"{dtype} not parsed to text (binary container or legacy format)"
        except PermissionError:
            entry["permission"] = "denied"
            note = "permission denied while reading"
        except Exception as exc:
            errors.append({"stage": "parse", "doc_id": doc_id, "path": rel, "error": f"{type(exc).__name__}: {exc}"})
            note = f"parse failed: {type(exc).__name__}"
        body_chars = sum(len(t) for _, _, t in units)
        entry["extract_method"] = method
        entry["note"] = note
        entry["chars"] = body_chars
        if dtype == "pdf" and body_chars < 40:
            entry["no_text_layer"] = True
            entry["note"] = note or "PDF text layer empty after extraction (scanner output)"
        entry["readable"] = body_chars >= 8
        pages_seen = sorted({p for p, _, _ in units if isinstance(p, int)})
        entry["pages"] = (max(pages_seen) if pages_seen else None)
        entry["sections"] = sorted({s for _, s, _ in units if s and s != "body"})[:40]
        # chunking: one chunk per (page, section) run, capped by CHUNK_CHARS
        buf, section, page, cidx = [], "body", None, 0

        def flush():
            nonlocal buf, cidx
            if not buf:
                return
            cidx += 1
            chunks.append({"chunk_id": (f"{doc_id}#p{page}c{cidx}" if page is not None else f"{doc_id}#c{cidx}"),
                           "doc_id": doc_id, "page": page, "section": section,
                           "text": " ".join(buf), "chars": len(" ".join(buf))})
            buf = []

        for pno, sec, txt in units:
            upg = pno if isinstance(pno, int) else page
            if buf and (sec != section or (upg is not None and page is not None and upg != page)
                        or sum(len(t) + 1 for t in buf) + len(txt) > CHUNK_CHARS):
                flush()
            if not buf:
                section, page = sec, upg
            buf.append(txt)
        flush()
        entry["chunks"] = cidx
        # family / version
        fam = family_key(path.name)
        entry["family"] = fam
        nums, dates = version_tokens(path.name + " " + str(meta.get("version") or ""))
        if not entry["version"]:
            if nums:
                entry["version"] = "v" + ("%g" % max(nums))
            elif dates:
                entry["version"] = str(max(dates))
            elif re.search(r"(?i)(final|定稿|终稿|latest|最新)", path.name):
                entry["version"] = "final"
            elif COPY_MARK.search(path.name) or entry["dup_of"]:
                entry["version"] = "copy"
            else:
                entry["version"] = "v1" if body_chars else None
        entry["version_rank"] = (max(nums) if nums else (max(dates) / 1000000.0 if dates else 1.0))
        family_members.setdefault(fam, []).append(doc_id)
        docs.append(entry)

    # duplicates inherit family/version of what they copy, and share sidecar metadata inside a sha group
    by_id = {d["doc_id"]: d for d in docs}
    groups = {}
    for d in docs:
        if d.get("sha256"):
            groups.setdefault(d["sha256"], []).append(d)
    for members in groups.values():
        if len(members) > 1:  # the record with a copy-marker in its name is the duplicate, not the original
            ranked = sorted(members, key=lambda m: (1 if COPY_MARK.search(m["name"]) else 0, m["doc_id"]))
            for m in members:
                m["dup_of"] = None if m is ranked[0] else ranked[0]["doc_id"]
                if m is not ranked[0]:
                    m["note"] = ((m.get("note") or "") + f" | byte-identical copy of {ranked[0]['doc_id']}").strip(" |")
        titled = [m for m in members if isinstance((m.get("metadata") or {}).get("title"), str)
                  and m["metadata"]["title"].strip()]
        for m in members:
            if titled and not isinstance((m.get("metadata") or {}).get("title"), str):
                m["metadata"] = dict(m["metadata"] or {}, title=titled[0]["metadata"]["title"],
                                     title_inherited_from=titled[0]["doc_id"])
    for d in docs:
        src = by_id.get(d.get("dup_of"))
        if src:
            d["version"], d["version_rank"] = src["version"], src["version_rank"]
            d["note"] = ((d.get("note") or "") + " | byte-identical copy of " + src["doc_id"]).strip(" |")
    for d in docs:
        title = (d.get("metadata") or {}).get("title")
        d["family"] = (str(title).strip()) if isinstance(title, str) and title.strip() else family_key(d["name"])
    family_members = {}
    for d in docs:
        if not d.get("dup_of") and d.get("family"):
            family_members.setdefault(d["family"], []).append(d["doc_id"])
    relations = []
    for fam, members in family_members.items():
        copies = [d["doc_id"] for d in docs if d.get("dup_of") and d.get("family") == fam]
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda d: ((by_id[d]["version_rank"] or 0), by_id[d]["mtime"]))
        relations.append({
            "family": fam, "doc_ids": ordered, "current": ordered[-1], "copies": copies,
            "versions": [{"doc_id": d, "version": by_id[d]["version"], "sha256_16": (by_id[d]["sha256"] or "")[:16],
                          "path": by_id[d]["path"], "size": by_id[d]["size"], "mtime": by_id[d]["mtime"]}
                         for d in ordered],
            "rule": "ordered by explicit version token, then embedded date, then mtime; byte-identical copies excluded",
        })
    for rel in relations:
        for v in rel["versions"]:
            v["is_current"] = v["doc_id"] == rel["current"]
    return docs, chunks, relations, errors, skipped, aux


def version_diffs(docs, chunks, relations, per_pair=4):
    """Numeric cross-version diff candidates: same topic sentence, different numbers."""
    by_doc = {}
    for ch in chunks:
        by_doc.setdefault(ch["doc_id"], []).append(ch)
    out = []
    for rel in relations:
        ids = rel["doc_ids"]
        older = ids[0]
        for newer in ids[1:]:
            a = " ".join(c["text"] for c in by_doc.get(older, []))
            b = " ".join(c["text"] for c in by_doc.get(newer, []))
            if len(a) < 20 or len(b) < 20:
                continue
            na = {n for n in NUM.findall(a) if len(n) >= 2}
            nb = {n for n in NUM.findall(b) if len(n) >= 2}
            only_a, only_b = sorted(na - nb)[:6], sorted(nb - na)[:6]
            if not only_a and not only_b:
                continue
            out.append({
                "family": rel["family"], "older": older, "newer": newer,
                "numbers_only_older": only_a, "numbers_only_newer": only_b,
                "hint": "older/newer disagree on numeric values; cite both editions verbatim before choosing",
            })
            if len(out) >= per_pair * max(1, len(relations)):
                break
    return out


# -------------------------------------------------------------------- retrieval
def search(chunks, question, topk=8, dup_ids=frozenset()):
    terms = tokens(question)
    if not terms or not chunks:
        return []
    df = {}
    for ch in chunks:
        for t in terms & tokens(ch["text"][:3000]):
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    keep = {t for t in terms if n < 20 or df.get(t, 0) <= max(3, int(0.6 * n))}
    if not keep:
        keep = terms
    scored = []
    for ch in chunks:
        body = tokens(ch["text"])
        head = tokens(ch.get("section") or "")
        s = 0.0
        for t in keep:
            w = 1.9 if t in head else 1.0
            if t in body:
                s += w
            elif t in head:
                s += w * 0.6
        if s > 0:
            s = s / (1.0 + ch["chars"] / 4000.0)
            if ch["doc_id"] in dup_ids:
                s *= 0.85
            scored.append((s, ch))
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(s, 2), "chunk_id": c["chunk_id"], "doc_id": c["doc_id"],
             "page": c["page"], "section": c["section"],
             "excerpt": c["text"][:420]} for s, c in scored[:topk]]


def doc_text_map(docs, chunks):
    """doc_id -> (normalised concatenated text, [(start, end, chunk)])"""
    out = {}
    for ch in chunks:
        text, spans = out.setdefault(ch["doc_id"], ["", []])
        if text:
            text += " "
        start = len(text)
        text += norm_q(ch["text"])
        spans.append((start, len(text), ch))
        out[ch["doc_id"]] = [text, spans]
    return out


def locate_quote(dmap, doc_id, quote):
    """Return dict(chunk_id, page, section, offset, match) or None."""
    if doc_id not in dmap:
        return None
    text, spans = dmap[doc_id]
    q = norm_q(quote)
    if not q or len(q) < 4:
        return None
    idx = text.find(q)
    match = "exact"
    if idx < 0:
        squashed = re.sub(r"[ \t]+", "", q)
        hay = re.sub(r"[ \t]+", "", text)
        j = hay.find(squashed)
        if j >= 0:
            # map back approximately by walking the original text
            running, idx = 0, -1
            for i, ch in enumerate(text):
                if running == j:
                    idx = i
                    break
                if ch not in " \t":
                    running += 1
            match = "whitespace_normalised"
    if idx < 0:
        return None
    for a, b, ch in spans:
        if a <= idx < b:
            return {"chunk_id": ch["chunk_id"], "page": ch["page"], "section": ch["section"],
                    "offset": idx - a, "match": match}
    return None


def doc_lookup(docs, ref):
    """Resolve a draft evidence reference (doc_id / path / alias) to a doc entry."""
    if not ref:
        return None
    r = str(ref).strip().replace("\\", "/").lower()
    for d in docs:
        if str(d["doc_id"]).lower() == r:
            return d
    for d in docs:
        cands = {str(d["path"]).lower().lstrip("./"), str(d["name"]).lower(),
                 str(d.get("abs_path", "")).lower()}
        cands |= {str(a).lower() for a in (d.get("aliases") or [])}
        if r in cands or any(c and (c.endswith(r) or r.endswith(c)) for c in cands if len(c) > 3):
            return d
    return None


# --------------------------------------------------------------- uncertainty
def uncertainty_grade(claims, related_unreadable=0, family_conflicts=0, editions=0):
    """Rule-based grade (see references/rules.md §4). Returns (level, reason)."""
    statuses = [str(c.get("status") or "").lower() for c in claims or []]
    supported = statuses.count("supported")
    if supported == 0 and any(s in ("not_in_kb", "insufficient") for s in statuses):
        return "high", "no verbatim support found in the indexed library"
    if "conflicting" in statuses or family_conflicts > 0:
        return "medium", "sources disagree; both sides quoted, no averaging"
    if related_unreadable > 0:
        return "medium", "part of the relevant material is unreadable or has no text layer"
    if supported == 0:
        return "high", "no claims recorded"
    if supported == 1:
        return "low", "single verbatim source"
    if editions >= 2:
        return "low", "several editions of one document family cited; version must be stated"
    return "none", ">=2 independent verbatim sources agree"


# ---------------------------------------------------------------- draft reading
def load_draft(work):
    for name in ("draft.json", "plan.json", "answers_draft.json", "worksheet.json"):
        p = Path(work) / name
        if p.is_file():
            data = jload(p)
            if isinstance(data, dict):
                return data, p, None
            return None, p, f"{name} 存在但不是合法 JSON 对象"
    return None, Path(work) / "draft.json", "draft.json not found"


def draft_answers(draft):
    for key in ("answers", "qa", "responses", "问答"):
        if isinstance(draft.get(key), list):
            return draft[key]
    return []


def match_answer(a, q):
    qid = str(q.get("question_id") or "")
    qtext = norm_q(q.get("question") or "")
    for k in ("question_id", "qid", "id"):
        if str(a.get(k) or "").strip() == qid:
            return True
    for k in ("question", "q", "query", "text", "prompt"):
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            av = norm_q(v)
            if av == qtext or (len(qtext) > 6 and (av in qtext or qtext in av)):
                return True
    return False


def akey(a, idx):
    for k in ("question_id", "qid", "id", "question", "q", "query"):
        v = a.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()[:48]
    return f"A{idx}"


def evs_of(c):
    ev = c.get("evidence")
    if isinstance(ev, dict):
        ev = [ev]
    return [e for e in (ev or []) if isinstance(e, dict)]


def sides_of(cf):
    return [s for s in (cf.get(k) for k in ("side_a", "side_b", "a", "b")) if isinstance(s, dict)]


# --------------------------------------------------------------------- validate
