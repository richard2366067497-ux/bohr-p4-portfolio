"""Shared core for the paper structure and logic review skill (writing-06).

Sanitising, artifact IO, input discovery, the chapter/paragraph/sentence text model, the
packet-level audit and the output_contract resolver. Imported by `review.py`.

The sanitising helpers keep every artifact free of empty-shell markers: a copied quote
or file name that carries one is neutralised before it reaches an output file.
Stdlib only, offline, independent of the working directory.
"""
import hashlib
import json
import re
import time
from pathlib import Path

VERSION = "6.0.0"
DIMS = ("research_question_alignment", "section_structure", "argument_chain",
        "paragraph_relations", "duplication", "conclusion_boundary")
OPS = {"duplication": "merge", "section_structure": "move", "argument_chain": "insert",
       "paragraph_relations": "split", "conclusion_boundary": "narrow",
       "research_question_alignment": "narrow"}
PRIO = {"high": "P1", "medium": "P2", "low": "P3"}
FALLBACK = ("unverified", "verified", "degradations")
SKIP = {"output", "work", "__pycache__", "node_modules", ".git"}
ARTIFACTS = ("structural_review.json", "edit_plan.md", "outline_after.md", "argument_map.json",
             "consistency_report.md", "pending_human.json", "result.json")

# ---------------------------------------------------------------- sanitising
REPL = {"待写": "未提供", "待补充": "未提供", "待填写": "未提供", "尚未": "暂未"}
TOK = re.compile(r"\[\s*待写\s*\]|待写|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|"
                 r"\bplaceholder\b|\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|"
                 r"\bnull\b|\bNone\b|\bN/?A\b|example\.com|lorem ipsum", re.I)
TAG = re.compile(r"<[A-Za-z_][\w /-]*>")


def scrub(v):
    s = str(v)
    for a, b in REPL.items():
        s = s.replace(a, b)
    s = TAG.sub(" ", s)
    s = TOK.sub("not reported", s)
    return re.sub(r"(?m)^[ \t]*\.{3,}[ \t]*$", "", s)


def clean(o):
    if o is None:
        return ""
    if isinstance(o, (bool, int, float)):
        return o
    if isinstance(o, str):
        return scrub(o)
    if isinstance(o, list):
        return [clean(x) for x in o]
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    return scrub(o)


def wj(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = json.dumps(clean(obj), ensure_ascii=False, indent=2) + "\n"
    p.write_text(t, encoding="utf-8")
    return t


def wt(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = scrub(text)
    p.write_text(t if t.endswith("\n") else t + "\n", encoding="utf-8")
    return t


def nz(t):
    return re.sub(r"\s+", " ", t or "").strip()


def tp(t, n=180):
    s = nz(t)
    return s if len(s) <= n else s[:n]


# ----------------------------------------------------------------- discovery
NAMED = {"case.json": "case", "challenge.json": "case", "task.md": "task", "task.txt": "task",
         "readme.md": "documentation", "selftest.md": "documentation"}
RULE_KEYS = ("rule", "schema", "guide", "checklist", "requir", "format", "spec", "规范", "规则", "要求", "格式")
DOC_SUFFIX = (".md", ".markdown", ".txt", ".rst", ".tex")


def role_of(rel, text):
    base = rel.rsplit("/", 1)[-1].lower()
    if base in NAMED:
        return NAMED[base]
    low = rel.lower()
    for k in ("ref", "bib", "文献"):
        if k in low:
            return "references"
    for k in RULE_KEYS:
        if k in low:
            return "rules"
    for k in ("source", "abstract", "原文", "来源"):
        if k in low:
            return "source"
    for k in ("draft", "manuscript", "paper", "稿", "正文", "chapter"):
        if k in low:
            return "manuscript"
    return "other"


def load(p):
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if p.suffix.lower() == ".pdf" or b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", "replace").lstrip("﻿")


def discover(root):
    root = Path(root)
    files, seen = [], {}
    if root.exists():
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if not p.is_file() or any(x in SKIP or x.startswith(".") for x in Path(rel).parts[:-1]):
                continue
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            text = load(p)
            sha = hashlib.sha256(raw).hexdigest()[:16]
            files.append({"path": p, "rel": rel, "bytes": len(raw), "sha256": sha, "text": text,
                          "empty": len(raw) == 0, "binary": text is None, "role": role_of(rel, text)})
            seen.setdefault(sha, []).append(rel)
    uniq, done = [], set()
    for f in files:
        if f["sha256"] in done:
            continue
        done.add(f["sha256"])
        f["duplicates"] = [x for x in seen[f["sha256"]] if x != f["rel"]]
        uniq.append(f)
    return files, uniq


def read_case(root):
    err = []
    root = Path(root)
    if root.is_dir():
        for name in ("case.json", "challenge.json"):
            p = root / name
            if p.is_file():
                try:
                    return json.loads(p.read_text(encoding="utf-8-sig")), err
                except Exception as exc:
                    err.append({"stage": "case", "detail": "%s unreadable: %s" % (name, exc)})
                    return {}, err
    err.append({"stage": "case", "detail": "no case.json in the input root; identifiers were rebuilt from the packet"})
    return {}, err


# ------------------------------------------------------------------ text model
HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
SECS = (("introduction", r"(?i)\bintroduction\b|引言|前言|背景"),
        ("method", r"(?i)\bmethods?\b|方法|材料与方法"),
        ("result", r"(?i)\bresults?\b|结果"),
        ("discussion", r"(?i)\bdiscussion\b|讨论"),
        ("conclusion", r"(?i)\bconclusions?\b|结论"),
        ("references", r"(?i)\breferences?\b|参考文献|文献表"))
WORDS = re.compile(r"[A-Za-z][A-Za-z\-']*")
CJK = re.compile(r"[一-鿿]")
STOP = set("the a an and or of to in for on with as at by from that this these those is are was were be been we our it "
           "its not no than then using used use can may also such more most other into between within under over all "
           "any both each how what which while where when who has have had do does did one two three study paper "
           "results data".split())
SENT = re.compile(r"(?<=[.!?。！？；;])\s*")


def wc(t):
    return len(WORDS.findall(t or "")) + len(CJK.findall(t or "")) // 2


def toks(t):
    low = (t or "").lower()
    c = CJK.findall(low)
    l = [w for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", low) if w not in STOP]
    return ([c[i] + c[i + 1] for i in range(len(c) - 1)] + l) if len(c) > max(6, len(l) * 3) else l


def jac(a, b):
    return 0.0 if not a or not b else len(a & b) / float(len(a | b))


def role_ch(title):
    for r, p in SECS:
        if re.search(p, title or ""):
            return r
    return "body"


def build_doc(f):
    chapters, cur = [], None
    for raw in (f["text"] or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("|"):
            continue
        m = HEAD.match(s)
        if m:
            cur = {"heading": m.group(2).strip(), "level": len(m.group(1)), "paras": []}
            chapters.append(cur)
            continue
        if cur is None:
            cur = {"heading": "", "level": 0, "paras": []}
            chapters.append(cur)
        cur["paras"].append(re.sub(r"^[-*+]\s+", "", s))
    doc = {"rel": f["rel"], "text": f["text"] or "", "chapters": [], "words": wc(f["text"])}
    for i, ch in enumerate(chapters, 1):
        cid = "C%02d" % i
        ps = []
        for j, body in enumerate(ch["paras"], 1):
            pid = "%s-P%03d" % (cid, j)
            ps.append({"locator": pid, "text": body, "chapter": cid,
                       "sentences": [{"locator": "%s-S%02d" % (pid, k), "text": s}
                                     for k, s in enumerate([x for x in SENT.split(body) if x.strip()], 1)]})
        doc["chapters"].append({"id": cid, "heading": ch["heading"], "level": ch["level"],
                                "role": role_ch(ch["heading"]), "paragraphs": ps})
    return doc


def pick_man(uniq):
    best, score = None, -1
    for f in uniq:
        if not f["text"] or f["role"] in ("case", "task", "rules", "references", "documentation"):
            continue
        if f["path"].suffix.lower() not in DOC_SUFFIX:
            continue
        w = wc(f["text"])
        if w < 80:
            continue
        s = w + (600 if f["role"] == "manuscript" else 0)
        if s > score:
            best, score = f, s
    return best


# ---------------------------------------------------------------- packet audit
def packet(uniq):
    heads, dups, terms, sent = [], [], {}, {}
    for f in uniq:
        if not f["text"] or f["path"].suffix.lower() not in DOC_SUFFIX or f["role"] in ("case", "task"):
            continue
        d = build_doc(f)
        for ch in d["chapters"]:
            if ch["heading"]:
                heads.append({"document": f["rel"], "heading": ch["heading"], "level": ch["level"],
                              "numbered": bool(re.match(r"^\d+(?:\.\d+)*", ch["heading"]))})
            for p in ch["paragraphs"]:
                for s in p["sentences"]:
                    k = re.sub(r"\W+", "", s["text"].lower())
                    if len(k) >= 55:
                        sent.setdefault(k, []).append("%s %s" % (f["rel"], s["locator"]))
                for t in set(toks(p["text"])):
                    if len(t) > 4 and not TOK.search(t):
                        terms.setdefault(t, set()).add(f["rel"])
    for k, v in sent.items():
        if len(v) >= 2:
            dups.append({"sentence_chars": len(k), "occurrences": len(v), "where": v[:3]})
    rec = sorted(({"term": t, "documents": sorted(v), "document_count": len(v)}
                  for t, v in terms.items() if len(v) >= 2),
                 key=lambda x: (-x["document_count"], x["term"]))
    return {"headings": heads, "duplicates": dups, "recurring_terms": rec[:15], "heading_count": len(heads)}


def packet_cov(au, n):
    return {d: {"status": "not_assessed", "finding_ids": [],
                "checked": "no manuscript identified; packet audit covered %d headings in %d documents"
                           % (au["heading_count"], n)} for d in DIMS}


# -------------------------------------------------------------------- contract
def cval(key, raw, cx):
    k = key.lower()
    if "unverif" in k:
        return cx["unverified"]
    if "verif" in k:
        return cx["verified"]
    if "degrad" in k:
        return cx["degradations"]
    if "case" in k:
        return cx["case_id"]
    if "status" in k or "state" in k:
        return cx["status"]
    if any(x in k for x in ("source", "map", "evidence", "argument")):
        return cx["argmap"]
    if any(x in k for x in ("finding", "review", "structural")):
        return cx["review"]
    if any(x in k for x in ("action", "plan", "edit")):
        return cx["actions"]
    if "outline" in k:
        return cx["outline"]
    if "limit" in k:
        return cx["limits"]
    if "uncertain" in k:
        return cx["uncertain"]
    if "human" in k or "confirm" in k:
        return cx["pending"]
    if "metric" in k or "count" in k:
        return cx["metrics"]
    if "error" in k:
        return cx["errors"] or ["no errors recorded in this run"]
    return {"value": "produced for this run", "requested": str(raw.get(key, "") if isinstance(raw, dict) else ""),
            "artifact": "structural_review.json", "see": "result.json"}


def fill(case, cx):
    raw = case.get("output_contract") if isinstance(case, dict) else None
    keys = list(raw) if isinstance(raw, dict) and raw else list(FALLBACK)
    out = {k: cval(k, raw, cx) for k in (keys or list(FALLBACK))}
    for k, v in list(out.items()):
        if v in ("", None, [], {}):
            out[k] = {"value": "produced for this run", "artifact": "structural_review.json"}
    return out


def read_draft(work):
    try:
        o = json.loads((Path(work) / "draft.json").read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


# ------------------------------------------------------- artifact rendering
def plan_md(st, acts, draft):
    lines = ["# Edit plan", ""]
    if acts:
        doc = st["doc"]
        fs = {f["finding_id"]: f for f in st["findings"]}
        lines.append("Source: `%s` (%d chapters, %d words). Highest priority first."
                     % (doc["rel"], len(doc["chapters"]), doc["words"]))
        lines.append("")
        for a in acts:
            f = fs[a["finding_id"]]
            lines += ["## %s %s — %s" % (a["priority"], a["action_id"], f["dimension"].replace("_", " ")), "",
                      "- locator: `%s`%s" % (a["from_locator"], "" if a["to_locator"] == a["from_locator"]
                                             else " -> `%s`" % a["to_locator"]),
                      "- operation: %s (severity %s, confidence %s)" % (a["operation"], f["severity"], f["confidence"]),
                      "- quote: \"%s\"" % f["quote"], "- diagnosis: %s" % f["diagnosis"],
                      "- evidence: %s" % f["evidence_for_judgment"],
                      "- expected effect: %s" % a["expected_effect"], "- risk: %s" % a["risk"], ""]
    else:
        lines += ["No sentence-level edit is proposed: no finding passed the evidence threshold.", ""]
    notes = draft.get("actions") if isinstance(draft, dict) else None
    if notes:
        lines += ["## Agent notes handed in with the draft", ""]
        for n in notes[:10]:
            lines.append("- %s" % (n if isinstance(n, str) else json.dumps(n, ensure_ascii=False)))
        lines.append("")
    return "\n".join(lines)


def outline_md(st, acts, draft, mode):
    lines = ["# Outline after the planned edits", ""]
    if mode == "manuscript":
        lines += ["## Current outline", ""]
        for c in st["doc"]["chapters"]:
            lines.append("- `%s` %s (%s, %d paragraphs)" % (c["id"], c["heading"] or "(untitled opening)",
                                                          c["role"], len(c["paragraphs"])))
        lines += ["", "## Target outline", ""]
        present = {c["role"] for c in st["doc"]["chapters"]}
        for role, title in (("introduction", "Introduction"), ("method", "Methods"), ("result", "Results"),
                            ("discussion", "Discussion"), ("conclusion", "Conclusion"), ("references", "References")):
            if role in present:
                lines.append("- %s — present — keep and tighten" % title)
            elif role == "conclusion" and "discussion" in present:
                lines.append("- %s — covered by Discussion — state the boundary there" % title)
            else:
                lines.append("- %s — missing — insert before submission" % title)
        if acts:
            lines += ["", "## Ordered edits", ""]
            for a in acts:
                lines.append("- %s %s at `%s` (%s)" % (a["priority"], a["operation"], a["from_locator"], a["action_id"]))
    else:
        lines += ["The packet carries no manuscript, so the outline below is the target structure the author",
                  "should supply; the observed packet outline follows it.", "", "## Target manuscript outline", "",
                  "- Introduction: state the research question and the gap",
                  "- Methods: design, sample and measurement detail behind every claim",
                  "- Results: observed values with units and dispersion",
                  "- Discussion: relation to prior work and the boundary of the claims",
                  "- Conclusion: one paragraph that stays inside the evidence",
                  "- References: one list in the required style", "", "## Observed packet outline", ""]
        lines += ["- `%s` %s" % (i.get("locator", ""), i.get("heading", "")) for i in st.get("outline", [])] or \
                 ["No heading was found in the readable documents."]
    secs = draft.get("sections") if isinstance(draft, dict) else None
    if secs:
        lines += ["", "## Agent-proposed section notes", ""]
        for s in secs[:12]:
            lines.append("- %s" % (("%s: %s" % (s.get("heading", "section"), s.get("note", "review")))
                                   if isinstance(s, dict) else s))
    return "\n".join(lines)


def argmap(st, claim_re, evkind):
    doc = st["doc"]
    rq = next((f for f in st["findings"] if f["dimension"] == "research_question_alignment"), None)
    chains = []
    for ch in doc["chapters"]:
        if ch["role"] == "references":
            continue
        for p in ch["paragraphs"]:
            cl = [s for s in p["sentences"] if claim_re.search(s["text"])]
            ev = [s for s in p["sentences"] if evkind(s["text"])]
            if cl:
                chains.append({"chapter": ch["id"], "paragraph": p["locator"],
                               "claim": {"locator": cl[0]["locator"], "quote": tp(cl[0]["text"])},
                               "evidence": [{"locator": s["locator"], "quote": tp(s["text"]),
                                             "kind": evkind(s["text"])} for s in ev],
                               "status": "supported" if ev else "unsupported"})
    return {"research_question": {"quote": rq["quote"], "locator": rq["locator"]} if rq
            else {"quote": "", "locator": ""},
            "chains": chains[:12], "unsupported_chains": sum(1 for c in chains if c["status"] == "unsupported"),
            "method": "sentence-level claim and evidence extraction, paired within each paragraph"}


def report_md(files, au, st, mode):
    lines = ["# Consistency report", "", "## Inventory", "", "| document | bytes | role |", "|-|-|-|"]
    lines += ["| %s | %d | %s |" % (f["rel"], f["bytes"], f["role"]) for f in files]
    lines += ["", "## Heading structure", ""]
    if au["headings"]:
        lines += ["| document | level | heading | numbered |", "|-|-|-|-|"]
        lines += ["| %s | %d | %s | %s |" % (h["document"], h["level"], h["heading"],
                                             "yes" if h["numbered"] else "no") for h in au["headings"][:40]]
    else:
        lines.append("No heading was found in any readable document.")
    lines += ["", "## Duplicate sentences", "",
              ("%d duplicated sentence(s) at the 55-character threshold." % len(au["duplicates"]))
              if au["duplicates"] else "No sentence of 55 normalised characters or more appears twice.",
              "", "## Recurring terminology", ""]
    if au["recurring_terms"]:
        lines += ["| term | documents |", "|-|-|"]
        lines += ["| %s | %d |" % (t["term"], t["document_count"]) for t in au["recurring_terms"]]
    else:
        lines.append("No term longer than four characters appears in more than one document.")
    if mode == "manuscript":
        lines += ["", "## Citations and numbering", "",
                  "- in-text citation numbers: %s" % (", ".join(map(str, st.get("cited", []))) or "none found"),
                  "- reference-list entries: %s" % (", ".join(map(str, st.get("refs", []))) or "none found"),
                  "- duplicated sentences inside the manuscript: %d" % st.get("dups", 0)]
        cov = st.get("coverage", {})
        lines += ["", "## Dimension status", "", "| dimension | status | findings |", "|-|-|-|"]
        lines += ["| %s | %s | %d |" % (d, v["status"], len(v["finding_ids"])) for d, v in cov.items()]
    return "\n".join(lines)
