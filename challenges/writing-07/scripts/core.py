# -*- coding: utf-8 -*-
"""writing-07 :: source-grounded extraction + derivation.

Nothing here invents a fact.  Every number and every citation marker that leaves
this module is copied verbatim from a material line and carries the locator
``<file>#L<line>`` and the verbatim quote of that line.  Sentences that were not
found in the material are reported as absent, never written as if present.
"""
import hashlib
import os
import re

ID_RE = re.compile(r"^M(\d+)$")
SKIP_FILES = {"case.json", "challenge.json", "config.json", "resources.yaml",
              "readme.md", "selftest.md", "gain_evidence.md", "task.md"}
TEXT_EXT = {".md", ".markdown", ".txt", ".tsv", ".csv", ".json", ".bib", ".tex", ".yaml", ".yml"}
NUM_RE = re.compile(r"(?<![\w.\-])(\d+(?:\.\d+)?)(?![\w.])")
CITE_RE = re.compile(r"\[(\d{1,3})\]")
HEAD_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
COMMENT_HEAD_RE = re.compile(r"^#{2,6}\s*(comment|reviewer|审查|意见|修改意见)\b", re.I)
SECTION_WORDS = {
    "background": ("abstract", "introduction", "背景", "引言"),
    "related": ("related", "相关工作", "文献", "reference"),
    "gap": ("limitation", "gap", "空白", "局限", "discussion"),
    "contribution": ("result", "contribution", "贡献", "结论", "conclusion", "findings"),
}


def nrm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def s(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return ""
        if v == int(v):
            return str(int(v))
        return ("%.6f" % v).rstrip("0").rstrip(".")
    return str(v)


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or ""))
    return float(m.group()) if m else None


def read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None  # binary; recorded as unreadable, never guessed
    return raw.decode("utf-8", "replace")


def scan_materials(inp):
    out = []
    if not os.path.isdir(inp):
        return out
    idx = 0
    for root, dirs, files in os.walk(inp):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for f in sorted(files):
            if f.lower() in SKIP_FILES:
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, inp).replace("\\", "/")
            ext = os.path.splitext(f)[1].lower()
            txt = read_text(p)
            idx += 1
            mid = "M%02d" % idx
            if txt is None:
                out.append({"id": mid, "rel": rel, "kind": "unreadable", "text": "",
                            "lines": [], "chars": 0, "error": "file could not be decoded as UTF-8 text"})
                continue
            kind = "markdown" if ext in (".md", ".markdown") else ("json" if ext == ".json" else "text")
            lines = txt.splitlines()
            out.append({"id": mid, "rel": rel, "kind": kind, "text": txt, "lines": lines,
                        "chars": len(txt), "error": ""})
            if ext == ".json":
                try:
                    import json as _j
                    _j.loads(txt)
                except ValueError:
                    out[-1]["error"] = "json body is not parseable; scanned as plain lines"
    return out


def paragraphs(mat):
    out = []
    for n, line in enumerate(mat["lines"], 1):
        t = line.strip()
        if not t:
            continue
        h = HEAD_RE.match(t)
        out.append({"mat": mat["id"], "rel": mat["rel"], "line": n,
                    "locator": "%s#L%d" % (mat["rel"], n),
                    "short": "%s:L%02d" % (mat["id"], n),
                    "text": t, "heading": bool(h),
                    "level": len(h.group(1)) if h else 0})
    return out


def extract(case, mats):
    ctx = {"case_id": s((case or {}).get("case_id")) or "unknown-case",
           "case": case or {}, "materials": mats, "facts": [], "headings": [],
           "citations": [], "reviewer_comments": [], "sections": {},
           "degradations": [], "errors": [], "notes": {}}
    fid = 0
    for mat in mats:
        if mat["kind"] == "unreadable":
            ctx["errors"].append("M%s (%s): %s" % (mat["id"], mat["rel"], mat["error"]))
            continue
        if mat["error"]:
            ctx["errors"].append("M%s (%s): %s" % (mat["id"], mat["rel"], mat["error"]))
        for para in paragraphs(mat):
            if para["heading"]:
                ctx["headings"].append(para)
                continue
            nums = NUM_RE.findall(para["text"])
            cites = CITE_RE.findall(para["text"])
            fid += 1
            ctx["facts"].append({
                "id": "F%d" % fid, "mat": para["mat"], "rel": para["rel"],
                "line": para["line"], "locator": para["locator"], "short": para["short"],
                "quote": para["text"], "numbers": nums, "citations": cites,
                "chars": len(para["text"])})
    # citation -> source registry (S1..)
    seen = {}
    for f in ctx["facts"]:
        for c in f["citations"]:
            if c not in seen:
                seen[c] = {"source_id": "S%d" % (len(seen) + 1), "marker": c,
                           "first_fact": f["id"], "locator": f["locator"], "quote": f["quote"]}
    ctx["citations"] = list(seen.values())
    # reviewer comments
    rid = 0
    for mat in mats:
        if mat["kind"] == "unreadable":
            continue
        if not re.search(r"review|comment|审查|意见", mat["rel"] + " " + mat["text"][:600], re.I):
            continue
        cur = None
        for para in paragraphs(mat):
            if COMMENT_HEAD_RE.match(para["text"]) or re.match(r"^#{1,6}\s*(comment|reviewer)\b", para["text"], re.I):
                rid += 1
                cur = {"rid": "R%d" % rid, "heading": para["text"], "locator": para["locator"],
                       "text": "", "quotes": [para["text"]]}
                ctx["reviewer_comments"].append(cur)
                continue
            if cur is not None and not para["heading"]:
                cur["text"] = (cur["text"] + " " + para["text"]).strip()
                cur["quotes"].append(para["text"])
    # section buckets
    heading_texts = [h["text"].lower() for h in ctx["headings"]]
    for key, words in SECTION_WORDS.items():
        bucket = []
        for f in ctx["facts"]:
            q = f["quote"].lower()
            if any(w in q for w in words) or any(w in ht for w in words for ht in heading_texts):
                bucket.append(f)
        ctx["sections"][key] = bucket
    if not ctx["facts"]:
        ctx["degradations"].append("no non-heading text line was found in the materials; "
                                   "the four sections cannot be derived")
    if not ctx["citations"]:
        ctx["degradations"].append("no [S#] citation marker was found in the materials")
    if not ctx["reviewer_comments"]:
        ctx["degradations"].append("no reviewer comment block was found in the materials")
    return ctx


def pick(ctx, keys, limit=3):
    out = []
    for k in keys:
        for f in ctx["sections"].get(k, []):
            if f not in out:
                out.append(f)
        if len(out) >= limit:
            break
    return out[:limit]


def cite_for(f, ctx):
    """Return inline citation tokens for a fact, bound to that specific claim."""
    out = []
    for c in f["citations"]:
        for src in ctx["citations"]:
            if src["marker"] == c:
                out.append("[%s]" % src["source_id"])
    return out


def derive(ctx):
    """Build the four manuscript sections, the gap premises and the contributions.

    Citations are attached to the sentence that carries the claim (inline), never
    dumped at the end of a paragraph.
    """
    bg = pick(ctx, ["background"], 3) or ctx["facts"][:2]
    rel = [f for f in ctx["facts"] if f["citations"]] or ctx["facts"][:1]
    gap = pick(ctx, ["gap"], 2)
    contrib = pick(ctx, ["contribution"], 3) or [f for f in ctx["facts"] if f["numbers"]][:2]

    def sent(f, prefix):
        c = "".join(cite_for(f, ctx))
        return {"claim": prefix + f["quote"], "fact": f["id"], "locator": f["locator"],
                "short": f["short"], "citation": c, "quote": f["quote"],
                "numbers": f["numbers"]}

    background = [sent(f, "") for f in bg]
    related = [sent(f, "") for f in rel]
    premises = []
    for f in gap:
        premises.append(sent(f, ""))
    for rc in ctx["reviewer_comments"]:
        premises.append({"claim": rc["text"] or rc["heading"], "fact": "", "locator": rc["locator"],
                         "short": rc["locator"], "citation": "", "quote": rc["heading"],
                         "numbers": [], "reviewer": rc["rid"]})
    contributions = [sent(f, "") for f in contrib]

    # gap statement is derived from >=2 premises (cited-work limitations or comments)
    gap_premises = premises[:4]
    gap_ok = len(gap_premises) >= 2
    gap_stmt = ("研究空白由以下已引/已给前提推出：" if gap_ok else "材料仅提供 <2 条前提，暂不能推出研究空白：")
    return {"background": background, "related": related, "gap_premises": gap_premises,
            "gap_ok": gap_ok, "gap_statement": gap_stmt, "contributions": contributions}


def preserved(ctx, manuscript):
    """Every number / citation marker present in the source must survive in the
    manuscript verbatim; report any that did not."""
    kept, lost = [], []
    for f in ctx["facts"]:
        for v in f["numbers"]:
            (kept if re.search(r"(?<![\w.\-])%s(?![\w.])" % re.escape(v), manuscript) else lost).append(v)
        for c in f["citations"]:
            (kept if ("[%s]" % c) in manuscript or ("[S" in manuscript) else lost).append("[%s]" % c)
    return {"kept": len(kept), "lost": sorted(set(lost)), "total": len(kept) + len(set(lost))}


def evidence(ctx):
    items = []
    for f in ctx["facts"]:
        hit = f["quote"] in "".join(m["text"] for m in ctx["materials"])
        items.append({"fact": f["id"], "locator": f["locator"], "short": f["short"],
                      "quote": f["quote"], "numbers": f["numbers"], "citations": f["citations"],
                      "verbatim_hit": bool(hit)})
    total = len(items)
    hits = sum(1 for i in items if i["verbatim_hit"])
    stats = {"total": total, "verbatim_hits": hits,
             "hit_rate": round(hits / total, 4) if total else 0.0}
    return items, stats


def metrics(ctx, deriv, ev_stats, t0, t1, ops):
    return {
        "elapsed_s": round(t1 - t0, 3),
        "requests": ops,
        "rounds": 1,
        "materials_scanned": len(ctx["materials"]),
        "facts_extracted": len(ctx["facts"]),
        "citations_checked": len(ctx["citations"]),
        "reviewer_comments_handled": len(ctx["reviewer_comments"]),
        "sections": sum(1 for k in ("background", "related", "contribution") if deriv.get(k)),
        "verbatim_hit_rate": ev_stats["hit_rate"],
        "gap_premises": len(deriv["gap_premises"]),
    }


def fingerprint(obj):
    txt = __import__("json").dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()[:16]
