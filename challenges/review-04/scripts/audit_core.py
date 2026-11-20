#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim-graph-auditor core: text units, claim/evidence nodes, edges, findings.

Pure standard library. Deterministic. No network.
"""
import hashlib
import json
import re
import subprocess
import shutil
from pathlib import Path

VERSION = "2.0.0"
SKILL = "claim-graph-auditor"
DEFAULT_KEYS = ["case_id", "status", "deliverable", "findings", "claim_graph",
                "evidence_matrix", "logic_report", "check_report", "uncertainties",
                "degradations", "errors", "truncated_sections", "dangling_edge", "changes"]
MAX_UNITS_PER_FILE = 400
MAX_TEXT_CHARS = 240000

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


def has_placeholder(value):
    s = str(value or "")
    return bool(re.search(r"\bnull\b|\bnone\b|待写|TBD|TODO|NOT_EXTRACTED|placeholder", s, re.I))


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
    for p in sorted(Path(out).rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".json", ".md", ".csv", ".txt", ".tsv"):
            continue
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


# ------------------------------------------------------------- input discovery
def extract_text(path):
    """Return (text, note). Supports md/txt/json/csv/rst/tex and pdf via pdftotext."""
    note = ""
    try:
        if path.suffix.lower() == ".pdf":
            exe = shutil.which("pdftotext")
            if exe:
                tmp = path.with_suffix(".pdftotext.txt")
                try:
                    subprocess.run([exe, "-layout", str(path), str(tmp)],
                                   capture_output=True, timeout=60)
                    if tmp.is_file() and tmp.stat().st_size > 0:
                        txt = tmp.read_text(encoding="utf-8", errors="replace")
                        tmp.unlink(missing_ok=True)
                        return txt, note
                except Exception:
                    pass
            raw = path.read_bytes()
            txt = raw.decode("latin-1", "replace")
            runs = re.findall(r"[ -~]{6,}", txt)
            return "\n".join(runs), "builtin-pdf-lowconf"
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "utf-16", "gb18030", "latin-1"):
            try:
                txt = raw.decode(enc)
                break
            except Exception:
                continue
        else:
            txt = raw.decode("utf-8", "replace")
        if path.suffix.lower() == ".json":
            try:
                obj = json.loads(txt)
                parts = []
                def walk(o):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            parts.append(str(k))
                            walk(v)
                    elif isinstance(o, list):
                        for v in o:
                            walk(v)
                    elif isinstance(o, str):
                        parts.append(o)
                walk(obj)
                txt = "\n".join(parts)
            except Exception:
                note = "json-not-parseable; read as plain text"
                txt = re.sub(r'[{}"\[\]]', " ", txt)
        return txt, note
    except Exception as exc:
        return "", "unreadable: %s" % exc


def discover(inp):
    inp = Path(inp)
    case, cpath, case_note = {}, None, ""
    for p in [inp / "case.json", inp / "challenge.json"] + sorted(inp.rglob("*.json")):
        if not p.is_file():
            continue
        obj = rj(p)
        if isinstance(obj, dict) and any(k in obj for k in ("case_id", "output_contract", "task_instruction")):
            case, cpath = obj, p
            break
    if not cpath:
        case_note = "case.json not found; packaged default contract keys were used"
    texts, degradations = [], []
    deny = ("case.json", "challenge.json", "task.md", "readme.md", "skill.md")
    for p in sorted(inp.rglob("*")):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low in deny or low.startswith("resources"):
            continue
        if p.suffix.lower() not in (".md", ".markdown", ".txt", ".json", ".csv", ".rst", ".tex", ".pdf"):
            continue
        txt, note = extract_text(p)
        if note:
            degradations.append({"file": p.relative_to(inp).as_posix(), "note": note})
        if not txt.strip():
            degradations.append({"file": p.relative_to(inp).as_posix(), "note": "no extractable text"})
            continue
        texts.append({"path": p.relative_to(inp).as_posix(), "text": txt})
    return case, cpath, case_note, texts, degradations


# ---------------------------------------------------------------- text units
HEAD_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
SECTION_WORDS = [
    ("abstract", r"abstract|摘要"), ("introduction", r"introduction|引言|前言|绪论"),
    ("methods", r"method|materials and methods|方法|材料"), ("results", r"result|结果"),
    ("discussion", r"discussion|讨论"), ("conclusion", r"conclusion|conclusion|结论|总结"),
    ("references", r"reference|bibliograph|参考文献"),
]
SENT_SPLIT = re.compile(r"(?<=[。！？!?])\s*|(?<=[.])\s+(?=[A-Z0-9(\[])|\n{2,}")
CLAIM_VERBS = [
    (4, r"\b(prove[sd]?|demonstrate[sd]?|confirm[sd]?|establishe[sd]?|证明|证实|表明)\b"),
    (3, r"\b(show(s|ed)?|find(s|ings)?|conclude[sd]?|reveal[sd]?|indicate[sd]?|显示|说明|发现|结论是)\b"),
    (2, r"\b(correlate[sd]?|associat(e|ed|ion)|related to|related with|相关|关联|伴随)\b"),
    (1, r"\b(may|could|might|suggest(s|ed)?|appear(s|ed)?|likely|可能|提示|或许)\b"),
]
HYP_RE = re.compile(r"\b(hypothes|assum|suppose|if we|假设|假定|若)\w*", re.I)
DEF_RE = re.compile(r"\b(is defined as|we define|refers to|refer to|定义为|指的是|所谓)\b", re.I)
OBLIG_RE = re.compile(r"\b(we aim|this (paper|study|work) (aims|analyses|analyzes|investigates|reports)|"
                      r"we (analyse|analyze|investigate|examine|set out)|本文|本研究|我们(旨在|分析|考察|研究))", re.I)
STAT_RE = re.compile(r"\b(p\s*[<>=]\s*0?\.\d+|\bn\s*=\s*\d+|standard deviation|\bSD\b|confidence interval|\bCI\b|"
                     r"±|percentage point|百分|显著性|标准差)\b", re.I)
NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|mm|MPa|GPa|min|s|°C|kg|h|µm|μm|mL)\b")
CITE_RE = re.compile(r"\[\d+(?:\s*[,;–-]\s*\d+)*\]|\([A-Z][A-Za-z]+(?:\s*(?:&|and|et al\.?)\s*[A-Za-z]*)?,?\s*\d{4}\)")
UP_RE = re.compile(r"\b(increase[sd]?|rise[s]?|rose|higher|greater|up|上升|增加|提高|高于)\b", re.I)
DOWN_RE = re.compile(r"\b(decrease[sd]?|fall[s]?|fell|lower|reduc(e|ed|tion)|down|下降|减少|降低|低于)\b", re.I)
NEG_RE = re.compile(r"\b(no|not|never|none|cannot|fail(s|ed)?|未|没有|不能|无法)\b", re.I)


def section_of(heading):
    h = heading.lower()
    for name, pat in SECTION_WORDS:
        if re.search(pat, h):
            return name
    return "body"


def build_units(files):
    units = []
    for f in files:
        lines = f["text"].splitlines()
        heading = ""
        sec = "body"
        buf = []
        idx = 0

        def flush():
            nonlocal buf, idx
            body = " ".join(x.strip() for x in buf).strip()
            if body:
                idx += 1
                units.append({
                    "unit_id": "U%04d" % len(units),
                    "file": f["path"],
                    "section": sec,
                    "heading": heading,
                    "ordinal": idx,
                    "text": body,
                    "locator": "%s §%s U%04d" % (f["path"], sec, len(units)),
                })
            buf = []

        for line in lines:
            hm = HEAD_RE.match(line)
            if hm:
                flush()
                heading = hm.group(2).strip()
                sec = section_of(heading)
                continue
            if not line.strip():
                flush()
                continue
            buf.append(line)
        flush()
    return units


def split_sentences(text):
    parts = [p.strip() for p in SENT_SPLIT.split(text) if p and p.strip()]
    out = []
    for p in parts:
        if len(p) < 12 and out:
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out or [text.strip()]


def strength_of(sentence):
    for level, pat in CLAIM_VERBS:
        m = re.search(pat, sentence, re.I)
        if m:
            return level, m.group(0)
    return 0, ""


def make_nodes(units):
    nodes = []
    counter = {"claim": 0, "evidence": 0, "cited_view": 0, "hypothesis": 0, "definition": 0, "obligation": 0}
    prefix = {"claim": "C", "evidence": "EV", "cited_view": "CV", "hypothesis": "H",
              "definition": "D", "obligation": "O"}
    for u in units:
        for s in split_sentences(u["text"]):
            if has_placeholder(s):
                continue
            quote = s.strip()
            if len(quote) < 20:
                continue
            level, verb = strength_of(quote)
            kind = None
            if OBLIG_RE.search(quote) and u["section"] in ("abstract", "introduction", "body"):
                kind = "obligation"
            elif HYP_RE.search(quote):
                kind = "hypothesis"
            elif DEF_RE.search(quote):
                kind = "definition"
            elif CITE_RE.search(quote) and level:
                kind = "cited_view"
            elif level:
                kind = "claim"
            elif NUM_RE.search(quote) or STAT_RE.search(quote):
                kind = "evidence"
            if not kind:
                continue
            counter[kind] += 1
            nodes.append({
                "node_id": "%s-%02d" % (prefix[kind], counter[kind]),
                "kind": kind,
                "quote": quote,
                "source_locator": "%s · %s" % (u["locator"], " ".join(s.split()[:2])[:24]),
                "unit_id": u["unit_id"],
                "section": u["section"],
                "strength_expression": verb,
                "strength_level": level if kind != "evidence" else 0,
                "stats_reported": bool(STAT_RE.search(quote)),
                "has_citation": bool(CITE_RE.search(quote)),
                "has_number": bool(NUM_RE.search(quote)),
            })
            if len(nodes) >= 400:
                return nodes
    return nodes


# ------------------------------------------------------------------- edges
def keywords(text):
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}|[一-鿿]{2,4}", text.lower())
    stop = {"this", "that", "with", "from", "have", "were", "which", "these", "those", "study",
            "paper", "result", "results", "作者", "本文", "研究", "结果", "表明"}
    return {w for w in words if w not in stop}


def build_edges(nodes):
    edges, eid = [], 0
    def add(etype, src, dst, why, quote, locator, severity_hint=""):
        nonlocal eid
        eid += 1
        edges.append({
            "edge_id": "E-%02d" % eid, "type": etype, "from": src, "to": dst,
            "rationale": why, "evidence_quote": quote, "locator": locator,
            "severity_hint": severity_hint,
        })

    claims = [n for n in nodes if n["kind"] == "claim"]
    evidences = [n for n in nodes if n["kind"] == "evidence"]
    obligations = [n for n in nodes if n["kind"] == "obligation"]
    cited = [n for n in nodes if n["kind"] == "cited_view"]

    for c in claims:
        same = [e for e in evidences if e["section"] == c["section"]]
        near = same or evidences
        if near:
            ev = near[0]
            shared = keywords(c["quote"]) & keywords(ev["quote"])
            if shared or ev["has_number"]:
                add("supports", ev["node_id"], c["node_id"],
                    "evidence unit shares topic terms and/or reports measured numbers",
                    ev["quote"], ev["source_locator"])
        stats_backed = any(e["stats_reported"] for e in same)
        if c["strength_level"] >= 3 and not stats_backed:
            add("overclaims", c["node_id"], "A-uncertainty",
                "claim uses a strength verb with no dispersion or significance statistic in the same section",
                c["quote"], c["source_locator"],
                "critical" if c["strength_level"] >= 4 else "major")
        if c["has_citation"] and not same:
            add("overclaims", c["node_id"], "A-citation",
                "claim carries a citation but no in-section evidence unit was located for the quoted sentence",
                c["quote"], c["source_locator"], "major")
    for o in obligations:
        hit = None
        for c in claims:
            if len(keywords(o["quote"]) & keywords(c["quote"])) >= 2:
                hit = c
                break
        if hit:
            add("delivers", o["node_id"], hit["node_id"],
                "a later claim addresses the same topic as the stated obligation",
                hit["quote"], hit["source_locator"])
        else:
            add("unaddressed", o["node_id"], "A-structure",
                "obligation stated in the front matter has no matching claim in the later sections",
                o["quote"], o["source_locator"], "major")
    for cv in cited:
        if not any(e["section"] == cv["section"] for e in evidences):
            add("unaddressed", cv["node_id"], "A-citation",
                "cited view is asserted without a supporting evidence unit in the audited text",
                cv["quote"], cv["source_locator"], "minor")
    dirs = [(n, "up") for n in claims if UP_RE.search(n["quote"])] + \
           [(n, "down") for n in claims if DOWN_RE.search(n["quote"])]
    seen_pairs = set()
    for a, da in dirs:
        for b, db in dirs:
            if a["node_id"] >= b["node_id"] or da == db:
                continue
            shared = keywords(a["quote"]) & keywords(b["quote"])
            if len(shared) >= 2 and (a["node_id"], b["node_id"]) not in seen_pairs:
                seen_pairs.add((a["node_id"], b["node_id"]))
                polarity = NEG_RE.search(a["quote"]) is not None
                if polarity == (NEG_RE.search(b["quote"]) is not None):
                    add("contradicts", a["node_id"], b["node_id"],
                        "two claims describe opposite directions for the same topic terms: %s" %
                        ", ".join(sorted(shared)[:4]),
                        a["quote"], a["source_locator"], "major")
    return edges


FACETS = ["fact", "citation", "method", "statistics", "argument", "structure"]
FACET_RULES = [
    ("fact", r"\b(data|value|measure|number|数值|数据|测量)\b"),
    ("citation", r"\b(cit|cited|reference|文献|引用|观点)\b"),
    ("method", r"\b(method|protocol|procedure|design|sample|方法|流程|设计|样本)\b"),
    ("statistics", r"\b(statistic|significan|p\s*[<>=]|variance|dispersion|统计|显著|离散)\b"),
    ("argument", r"\b(because|therefore|thus|implies|cause|argument|因此|导致|推理|因果)\b"),
    ("structure", r"\b(section|chapter|introduction|discussion|章节|结构|前后|衔接)\b"),
]


def facet_for(edge):
    blob = edge["rationale"]
    for name, pat in FACET_RULES:
        if re.search(pat, blob, re.I):
            return name
    return "argument"


def derive_findings(edges, nodes):
    findings, fid = [], 0
    recs = {
        "overclaims": "Lower the claim verb to match the evidence, or add the missing statistic "
                      "(sample size, dispersion or significance) for the quoted sentence.",
        "unaddressed": "Either deliver the promised analysis with its own results unit, or remove the "
                       "obligation sentence from the front matter.",
        "contradicts": "Reconcile the two sentences: state the direction once and cite the unit that "
                       "supports it, or mark the exception explicitly.",
    }
    kind = {"overclaims": "insufficient_evidence", "unaddressed": "error", "contradicts": "error"}
    for e in edges:
        if e["type"] not in recs:
            continue
        fid += 1
        sev = e.get("severity_hint") or "major"
        findings.append({
            "finding_id": "F-%02d" % fid,
            "facet": facet_for(e),
            "finding_type": kind.get(e["type"], "error"),
            "severity": sev,
            "edge": e["edge_id"],
            "edge_type": e["type"],
            "quote": e["evidence_quote"],
            "locator": e["locator"],
            "rationale": e["rationale"],
            "recommendation": recs[e["type"]],
        })
    for n in nodes:
        if n["kind"] == "claim" and n["has_number"] and not n["stats_reported"]:
            fid += 1
            findings.append({
                "finding_id": "F-%02d" % fid, "facet": "statistics",
                "finding_type": "suggestion", "severity": "minor",
                "edge": "", "edge_type": "reports_gap",
                "quote": n["quote"], "locator": n["source_locator"],
                "rationale": "a numeric claim is reported without sample size, dispersion or a significance statistic",
                "recommendation": "Report n and the dispersion (SD or CI) next to the quoted number, "
                                  "or label the number as illustrative.",
            })
            if len(findings) >= 60:
                break
    order = {"critical": 0, "major": 1, "minor": 2, "suggestion": 3}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["finding_id"]))
    for i, f in enumerate(findings, 1):
        f["finding_id"] = "F-%02d" % i
    return findings
