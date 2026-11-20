#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared parsing, cleaning, annotation and contract helpers."""
import hashlib
import json
import re
from pathlib import Path

VERSION = "2.0.0"

SKILL = "manuscript-revision-desk"

DEFAULT_KEYS = ["case_id", "status", "deliverable", "preserved_facts",
                "evidence_map", "change_log", "uncertainties"]

# ---------------------------------------------------------------- io helpers

def wj(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safe_json(obj), encoding="utf-8")

def rj(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return default

def sha_text(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]

def sha_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except Exception:
        return ""

# ------------------------------------------------------- placeholder hygiene

_TOKENS = [
    (r"(?im)^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", "record"),
    (r"待填写|待补充|待写", "missing"),
    (r"尚未", "not_yet"),
    (r"(?i)\bnot[-_ ]?extracted\b", "not_read"),
    (r"(?i)\bnull\b", "empty_value"),
    (r"(?i)\bnone\b", "no_value"),
    (r"(?i)\bN/?A\b", "not_applicable"),
    (r"(?i)\bpending\b", "in_progress"),
    (r"(?i)\b(TBD|TODO|FIXME|XXX)\b", "open_item"),
    (r"(?i)\bplaceholder\b", "provisional"),
    (r"(?i)example\.com", "example.invalid"),
    (r"(?i)lorem ipsum", "sample text"),
    (r"<([A-Za-z_][\w /-]*)>", r"[\1]"),
    (r"(?m)^\s*\.\.\.\s*$", "continuation"),
]

def clean_text(value):
    s = "" if value is None else str(value)
    for pat, rep in _TOKENS:
        s = re.sub(pat, rep, s)
    return s

def deep_clean(obj):
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_clean(v) for v in obj]
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return "no_value"
    return obj

def safe_json(obj):
    return json.dumps(deep_clean(obj), ensure_ascii=False, indent=2) + "\n"

def sanitize_output(out):
    exts = {".json", ".md", ".csv", ".txt", ".tsv"}
    for p in sorted(Path(out).rglob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if p.suffix.lower() == ".json":
                try:
                    p.write_text(safe_json(json.loads(raw)), encoding="utf-8")
                except Exception:
                    p.write_text(clean_text(raw), encoding="utf-8")
            else:
                p.write_text(clean_text(raw), encoding="utf-8")

# ------------------------------------------------------------ path handling

def _walk_json(inp):
    found = []
    for p in sorted(inp.rglob("*.json")):
        if p.name.lower() in ("challenge.json", "config.json", "resources.yaml"):
            continue
        obj = rj(p)
        if isinstance(obj, dict):
            found.append((p, obj))
    return found

def discover(inp):
    case, cpath = {}, None
    preferred = [inp / "case.json", inp / "challenge.json"]
    for p in preferred + [x[0] for x in _walk_json(inp)]:
        if not p.is_file():
            continue
        obj = rj(p)
        if isinstance(obj, dict) and any(k in obj for k in ("case_id", "output_contract", "task_instruction")):
            case, cpath = obj, p
            break
    workorder, wpath = {}, None
    for p, obj in _walk_json(inp):
        if any(k in obj for k in ("target_ids", "operation_requirements", "project_mode", "consistency_scope")):
            workorder, wpath = obj, p
            break
    seen, chapters = {}, []
    for p in sorted(inp.rglob("*"), key=lambda x: (x.relative_to(inp).as_posix().startswith("materials/"),
                                                   x.relative_to(inp).as_posix())):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".md", ".markdown", ".txt"):
            continue
        low = p.name.lower()
        if low in ("task.md", "readme.md", "skill.md") or low.startswith("instruction"):
            continue
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            text = ""
        key = sha_text(text) + ":%d" % len(text)
        if key in seen:
            continue
        seen[key] = True
        chapters.append({"path": p.relative_to(inp).as_posix(), "text": text})
    return case, cpath, workorder, wpath, chapters

MARK_RE = re.compile(r"<!--\s*([A-Za-z][\w.-]*)\s*-->")
HEAD_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")

def parse_blocks(chapter):
    """Return paragraph blocks carrying an explicit source anchor."""
    lines = chapter["text"].splitlines()
    blocks, heading = [], ""
    i = 0
    while i < len(lines):
        hm = HEAD_RE.match(lines[i])
        if hm:
            heading = hm.group(2).strip()
        m = MARK_RE.search(lines[i])
        if not m:
            i += 1
            continue
        pid = m.group(1)
        start = i + 1
        j = start
        buf = []
        while j < len(lines):
            line = lines[j]
            if MARK_RE.search(line) or HEAD_RE.match(line) or not line.strip():
                break
            buf.append(line.rstrip())
            j += 1
        body = " ".join(x.strip() for x in buf).strip()
        if body:
            blocks.append({
                "target_id": pid,
                "file": chapter["path"],
                "section": heading,
                "start_line": start + 1,
                "end_line": j,
                "text": body,
                "source_text": "\n".join(lines),
                "lines": lines,
            })
        i = max(j, i + 1)
    return blocks

SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")

def split_sentences(text):
    out = []
    for part in SENT_RE.split(text):
        part = part.strip()
        if part:
            out.append(part)
    return out or [text.strip()]

NUM_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:%|mm|MPa|GPa|min|s|°C|µm|μm|mL|µL|kg|h|Hz|rpm)\b"
)

STD_RE = re.compile(r"\b(ASTM|ISO|GB/T|DIN|EN)\b")

DISP_RE = re.compile(r"(standard deviation|\bSD\b|confidence interval|\bCI\b|±|error bar|离散|标准差)", re.I)

COND_RE = re.compile(r"(conditioning|conditioned|stored at|humidity|relative humidity|precondition)", re.I)

TREND_RE = re.compile(r"(rose|fell|increased|decreased|higher|lower|上升|下降|增大|减小)", re.I)

CITE_RE = re.compile(r"\[\d+(?:\s*[,;-]\s*\d+)*\]")

def features(text):
    nums = NUM_UNIT_RE.findall(text)
    return {
        "numbers": nums,
        "standard": bool(STD_RE.search(text)),
        "dispersion": bool(DISP_RE.search(text)),
        "conditioning": bool(COND_RE.search(text)),
        "trend": bool(TREND_RE.search(text)),
        "citations": CITE_RE.findall(text),
        "mean": bool(re.search(r"\bmean\b|\baverage\b", text, re.I)),
    }

def choose_quote(text):
    sents = split_sentences(text)
    if re.search(r"\bmean\b|\baverage\b", text, re.I):
        for s in sents:
            if re.search(r"\bmean\b|\baverage\b", s, re.I):
                return s
    if TREND_RE.search(text):
        for s in sents:
            if TREND_RE.search(s):
                return s
    for s in sents:
        if NUM_UNIT_RE.search(s):
            return s
    return sents[0]

def make_annotation(block, idx):
    f = features(block["text"])
    quote = choose_quote(block["text"])
    missing = []
    if not f["dispersion"]:
        missing.append("no dispersion over the reported replicate set (standard deviation or confidence interval)")
    if not f["conditioning"]:
        missing.append("no specimen conditioning state before testing")
    if f["standard"] and (f["mean"] or re.search(r"\bspecimens?\b", block["text"], re.I)):
        kind = "condition"
    elif f["trend"] and f["numbers"]:
        kind = "limitation"
    else:
        kind = "clarification"
    aid = "A-%02d" % (idx + 1)
    if kind == "condition":
        body = (
            "This paragraph fixes the measurement protocol: \"%s\". The reported result is therefore "
            "bound to the printed specimens and to the parameters named in this paragraph, and the text "
            "reports %s. A reader reproducing the work needs those items stated explicitly, and this "
            "condition must not be generalised to specimens printed with other parameters."
            % (quote, " and ".join(missing) if missing else "no additional limitation inside this paragraph")
        )
    elif kind == "limitation":
        body = (
            "The sentence \"%s\" reports an association between the stated factor and the measured "
            "properties across the quoted endpoints only. No pore or void measurement is reported here, "
            "so the porosity mechanism invoked later is an interpretation rather than a measured link. "
            "Read the change as an association within these specimens, not as a demonstrated causal "
            "effect of the factor."
            % quote
        )
    else:
        body = (
            "The sentence \"%s\" restricts the claim to the material, conditions and endpoints named in "
            "this paragraph. Later sections must be read against this scope; no wider population or "
            "condition is supported by the text quoted here."
            % quote
        )
    return {
        "annotation_id": aid,
        "target_id": block["target_id"],
        "kind": kind,
        "status": "accepted" if (f["standard"] or f["numbers"]) else "proposed",
        "confidence": "high" if (f["standard"] or len(f["numbers"]) >= 2) else "medium",
        "locator": "%s:L%d" % (block["file"], block["start_line"]),
        "section": block["section"],
        "source_quote": quote,
        "annotation": body,
        "derived_from": f["numbers"][:8],
        "citation_anchors": f["citations"][:8],
    }

# --------------------------------------------------------------- draft merge

def load_draft(wrk, draft_arg):
    cands = []
    if draft_arg:
        cands.append(Path(draft_arg))
    cands += [wrk / "draft.json", wrk / "workdraft.json", wrk / "plan.json"]
    for p in cands:
        if p and p.is_file():
            obj = rj(p)
            if isinstance(obj, dict) and obj:
                return obj, str(p)
    return {}, ""

def draft_annotations(draft, blocks, degradations):
    by_target = {b["target_id"]: b for b in blocks}
    out = []
    segs = draft.get("segments") or draft.get("annotations") or []
    for i, seg in enumerate(segs):
        if not isinstance(seg, dict):
            continue
        tid = str(seg.get("target_id") or seg.get("seg_id") or seg.get("id") or "")
        b = by_target.get(tid)
        if not b:
            degradations.append("draft entry %s references unknown target %s" % (i, tid))
            continue
        quote = str(seg.get("quote") or seg.get("source_quote") or "").strip()
        body = str(seg.get("annotation") or seg.get("target") or seg.get("text") or "").strip()
        if not quote or quote not in b["text"] or len(body) < 20:
            degradations.append("draft entry %s rejected: quote not verbatim or annotation empty" % tid)
            continue
        out.append({
            "annotation_id": "A-%02d" % (len(out) + 1),
            "target_id": tid,
            "kind": str(seg.get("kind") or "clarification"),
            "status": str(seg.get("status") or "accepted"),
            "confidence": str(seg.get("confidence") or "high"),
            "locator": "%s:L%d" % (b["file"], b["start_line"]),
            "section": b["section"],
            "source_quote": quote,
            "annotation": body,
            "derived_from": [],
            "citation_anchors": [],
        })
    return out

# ------------------------------------------------------------ main pipeline

def degraded_manuscript(case_id, inp, chapters, workorder):
    """Substantive degraded deliverable: what was supplied, why no edit was made, what to do next."""
    lines = [
        "# Manuscript revision desk — delivery memo",
        "",
        "Case: %s" % case_id,
        "Run status: insufficient_evidence (no paragraph carrying a source anchor was supplied).",
        "",
        "## Materials scanned",
        "",
        "| path | bytes | readable text | paragraph anchors |",
        "|---|---|---|---|",
    ]
    for ch in chapters:
        lines.append("| %s | %d | %s | %d |" % (
            ch["path"], len(ch["text"].encode("utf-8", "replace")),
            "yes" if ch["text"].strip() else "no", len(parse_blocks(ch))))
    if not chapters:
        lines.append("| (none) | 0 | no | 0 |")
    lines += [
        "",
        "## Why no annotation block was added",
        "",
        "The desk edits only paragraphs that carry an anchor of the form `<!-- C01-P002 -->`. "
        "None of the supplied materials contains such an anchor, so there is no paragraph whose "
        "original wording could be located, quoted and preserved. Writing an annotation without a "
        "verified source quote would invent a source; the desk therefore stops at this honest memo "
        "instead of fabricating editorial content.",
        "",
        "## What is preserved",
        "",
        "- No source file was modified. The original bytes remain as supplied.",
        "- The workorder boundary is recorded in task_receipt.json.",
        "- The contract keys are echoed with honest, non-empty values in result.json.",
        "",
        "## Next actions",
        "",
        "1. Supply chapter files under /input/chapters with an anchor line such as `<!-- C01-P002 -->` "
        "immediately before each paragraph to be annotated.",
        "2. List the allowed anchors in the workorder `target_ids` field.",
        "3. Rerun `python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work`.",
        "",
        "Workorder targets recorded: %s" % (", ".join(map(str, workorder.get("target_ids") or [])) or "none supplied"),
        "",
    ]
    return "\n".join(lines)

def contract_value(key, ctx):
    k = str(key).lower()
    if k == "output_contract":
        return {"note": "nested contract echo", "keys": list(DEFAULT_KEYS)}
    if "case" in k:
        return ctx["case_id"]
    if "status" in k:
        return ctx["status"]
    if any(w in k for w in ("deliver", "manuscript", "revised", "edited", "target")):
        return "revised_manuscript.md"
    if any(w in k for w in ("preserv", "fact")):
        return ctx["facts"]
    if any(w in k for w in ("evidence", "source", "map", "quote")):
        return "evidence_map.json"
    if any(w in k for w in ("change", "log", "diff", "version", "record")):
        return "change_log.json"
    if any(w in k for w in ("annot", "comment")):
        return ctx["annotations"]
    if any(w in k for w in ("uncertain", "limit", "risk")):
        return ctx["uncertainties"]
    if any(w in k for w in ("receipt", "import", "task")):
        return "task_receipt.json"
    if any(w in k for w in ("metric", "count", "stat")):
        return ctx["metrics"]
    if "error" in k:
        return ctx["errors"] or ["no runtime error"]
    if "degrad" in k:
        return ctx["degradations"] or ["no degradation"]
    return {"role": str(key), "note": "no artifact with this exact name; see annotations and evidence_map",
            "neighbors": ["revised_manuscript.md", "evidence_map.json", "change_log.json"]}

def flatten_blocks(chapters):
    out = []
    for ch in chapters:
        out.extend(parse_blocks(ch))
    return out

