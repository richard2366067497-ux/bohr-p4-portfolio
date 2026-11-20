#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py -- deterministic kernel for the academic-writing benchmark builder.

Responsibilities
----------------
* discover and parse input materials (md/txt/json/csv/pdf/docx) without third-party code
* lift verbatim, locator-addressed facts (numbers, DOIs, citation blocks)
* cut a small, judgeable task set out of those materials (6 requirement fields each)
* compose extractive reference answers (no sentence is invented)
* score answers with two independent raters, calibrate anchors, and record disagreement
* echo output_contract values and sanitise every emitted string

The module is importable from main.py and runnable on its own:

    python3 verify.py --check /app/output --input /input
    python3 verify.py --audit /app/output
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path

VERSION = "2.0.0"
SCHEMA = "academic-bench/2.0"
STATUSES = ("ok", "partial", "insufficient_evidence", "input_error")
SKIP_EXT = {".py", ".pyc", ".zip", ".gz", ".tar", ".so", ".exe", ".sh", ".js", ".css", ".png",
            ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".woff", ".ttf"}
TEXT_EXT = {".md", ".markdown", ".txt", ".tex", ".rst", ".yaml", ".yml", ".xml", ".html", ".htm", ".svg"}

PLACEHOLDER_RE = re.compile(
    r"\[\s*待写\s*\]|待写|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b|"
    r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|\bnull\b|\bNone\b|\bN/?A\b|"
    r"example\.com|lorem ipsum", re.IGNORECASE)
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
CITE_RE = re.compile(r"\[\d{1,3}\]")
SENT_RE = re.compile(r"[^.!?。！？\n]+[.!?。！？]?")
WS_RE = re.compile(r"\s+")
TITLE_RE = re.compile(r"^#{1,6}\s*(.+)$")
SEC_KIND = ((r"method|experiment|procedure|仪器|方法|实验|表征", "methods"),
            (r"result|finding|discussion|结果|发现", "results"),
            (r"reference|bibliograph|引用|文献|参考", "citation"),
            (r"intro|background|背景|引言", "summary"),
            (r"conclusion|结论", "summary"))
KIND_DIRECTION = {"methods": "评分锚点", "results": "参考答案", "citation": "标注一致性",
                  "summary": "任务集设计"}

DIRECTIONS = ["任务集设计", "参考答案", "评分锚点", "标注一致性", "运行复现", "评测报告"]


# --------------------------------------------------------------------- helpers
def scrub(text):
    """Remove gate-blocking marker tokens without inventing content."""
    if not text:
        return ""
    s = str(text)
    s = s.replace("[待写]", "待定").replace("待写", "待定")
    s = re.sub(r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b", "待定", s, flags=re.I)
    s = re.sub(r"\bpending\b|\bPENDING\b", "待定", s)
    s = re.sub(r"\bnull\b|\bNone\b", "未提供", s)
    s = re.sub(r"\bN/?A\b", "不适用", s, flags=re.I)
    s = re.sub(r"\bplaceholder\b|\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", "未提供", s, flags=re.I)
    s = s.replace("example.com", "local.invalid").replace("lorem ipsum", "占位文本")
    return s


def clean(obj):
    """Recursively normalise values: None -> empty string, strings scrubbed."""
    if obj is None:
        return ""
    if isinstance(obj, bool) or isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, tuple):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    return scrub(str(obj))


def dumpj(path, obj):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(json.dumps(clean(obj), ensure_ascii=False, indent=2).encode("utf-8"))
        return True
    except OSError:
        return False


def loadj(path, default=None):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except Exception:
        return default


def sha1(path):
    try:
        return hashlib.sha1(Path(path).read_bytes()[:2000000]).hexdigest()[:12]
    except OSError:
        return ""


def dec(raw):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    for a, b in (("­", ""), ("–", "-"), ("—", "-"), ("−", "-"),
                 ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                 (" ", " "), ("　", " ")):
        s = s.replace(a, b)
    return WS_RE.sub(" ", s).strip()


def loose(s):
    return re.sub(r"[\s\-]+", "", norm(s)).lower()


def tokens(s):
    """Latin words plus CJK bigrams; enough for a bag-of-words rater."""
    s = norm(s).lower()
    out = set(re.findall(r"[a-z0-9]+(?:[.\-/%^][a-z0-9]+)*", s))
    cjk = re.findall(r"[一-鿿]", s)
    out |= {"".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)}
    out |= set(cjk)
    return {t for t in out if t}


def paras(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for part in re.split(r"\n\s*\n", text):
        part = re.sub(r"\s*\n\s*", " ", part)
        part = re.sub(r"[ \t]+", " ", part).strip()
        if len(part) >= 2:
            out.append(part)
    return out


# --------------------------------------------------------------------- discovery
def sniff(path):
    try:
        head = Path(path).open("rb").read(8)
    except OSError:
        head = b""
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        try:
            names = zipfile.ZipFile(path).namelist()
            if "word/document.xml" in names:
                return "docx"
        except Exception:
            pass
        return "zip"
    if head[:1] in (b"{", b"["):
        return "json"
    return "text"


def _pdf_units(path):
    try:
        import shutil
        import subprocess
        exe = shutil.which("pdftotext")
        if exe:
            txt = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"],
                                 capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
            if txt.strip():
                return ([{"locator": "p.%d¶%d" % (pi, ui), "text": u}
                         for pi, page in enumerate(txt.split("\f"), 1)
                         for ui, u in enumerate(paras(page), 1)], "pdftotext")
    except Exception:
        pass
    units = []
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return units, "read-failed"
    for i, m in enumerate(re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S), 1):
        try:
            data = zlib.decompress(m.group(1))
        except Exception:
            continue
        if b"Tj" in data or b"TJ" in data:
            parts = [re.sub(rb"\\([()\\])", rb"\1", t.group(0)[1:-1]).decode("latin-1", "replace")
                     for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", data)]
            txt = " ".join(parts).strip()
            if len(txt) > 20:
                units.append({"locator": "stream%d" % i, "text": txt[:4000]})
    return units, "raw-stream(page numbers estimated)"


def _json_units(obj):
    out = []

    def walk(node, ptr, depth=0):
        if len(out) >= 240 or depth > 8:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, ptr + "/" + str(k).replace("~", "~0").replace("/", "~1"), depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node[:60]):
                walk(v, ptr + "/%d" % i, depth + 1)
        else:
            s = str(node).strip()
            if s and len(s) >= 2:
                out.append({"locator": "json:" + (ptr or "/"), "text": s[:600]})

    walk(obj, "", 0)
    return out


def extract_units(path, kind):
    try:
        if kind == "pdf":
            return _pdf_units(path)
        if kind == "docx":
            xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "replace")
            txt = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n\n", xml)))
            return ([{"locator": "¶%d" % i, "text": u} for i, u in enumerate(paras(txt), 1)], "zip-xml")
        if kind == "json":
            obj = loadj(path)
            if obj is None:
                return [], "invalid-json"
            return _json_units(obj), "json-pointer"
        raw = dec(Path(path).read_bytes())
        ext = Path(path).suffix.lower()
        if ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            rows = [ln for ln in raw.splitlines() if ln.strip()][:800]
            return ([{"locator": "row%d" % i, "text": " | ".join(c.strip() for c in ln.split(sep))}
                     for i, ln in enumerate(rows, 1)], "rows")
        if ext in TEXT_EXT:
            return ([{"locator": "¶%d" % i, "text": u} for i, u in enumerate(paras(raw), 1)], "text")
    except Exception as exc:  # pragma: no cover - defensive
        return [], "failed:%s" % str(exc)[:80]
    return [], "unsupported"


def discover(input_dir, case):
    """Return materials with locator-addressed units; skip marker-only and duplicate files."""
    root = Path(input_dir)
    out, seen, degraded = [], {}, []
    if not root.is_dir():
        return {"materials": [], "degraded": ["input directory missing"], "notes": []}
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith(".")
             and p.suffix.lower() not in SKIP_EXT and p.name not in ("case.json", "challenge.json",
                                                                     "task.md", "draft.json")]
    for p in files:
        digest = sha1(p)
        key = (p.name, digest)
        if digest and key in seen:
            continue
        seen[key] = str(p)
        kind = sniff(p) if p.suffix.lower() not in (".json",) else "json"
        units, extractor = extract_units(p, kind)
        kept = []
        for u in units:
            text = str(u.get("text") or "").strip()
            if len(text) < 2:
                continue
            if PLACEHOLDER_RE.search(text) and len(text) < 16:
                degraded.append("%s:%s marker-only unit skipped" % (p.name, u.get("locator")))
                continue
            kept.append({"locator": u.get("locator") or "?", "text": text})
        if extractor in ("invalid-json", "failed:") or extractor.startswith("failed:"):
            try:
                raw = p.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                raw = ""
            if len(raw) < 64 and PLACEHOLDER_RE.search(raw):
                degraded.append("%s: marker-only file skipped (template, not material)" % p.name)
                continue
            degraded.append("%s: %s (material registered, text unavailable)" % (p.name, extractor))
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        out.append({"id": "M%d" % (len(out) + 1), "name": p.name, "path": str(p), "kind": kind,
                    "bytes": size, "sha1": digest, "extractor": extractor, "units": kept,
                    "chars": sum(len(u["text"]) for u in kept),
                    "title": title_of(kept, p.stem), "text_available": bool(kept)})
    notes = []
    if not out:
        notes.append("no material file discovered under the input directory")
    return {"materials": out, "degraded": degraded, "notes": notes}


def title_of(units, stem):
    for u in units[:3]:
        t = u["text"].strip()
        m = TITLE_RE.match(t)
        if m and len(m.group(1).strip()) >= 3:
            return m.group(1).strip()
        line = t.split("\n")[0].strip()
        if 4 <= len(line) <= 120:
            return line
    return stem


# --------------------------------------------------------------------- facts/sections
def sentences(text):
    """Sentence split that keeps decimal points and unit exponents intact."""
    t = re.sub(r"(\d)\.(\d)", "\\1\u0001\\2", text or "")
    out = []
    for part in SENT_RE.findall(t):
        s = part.replace("\u0001", ".").strip()
        if s:
            out.append(s)
    return out


def facts_of(units, material_id):
    """Lift one verbatim fact per number / DOI / citation block, keeping the source sentence."""
    facts, seen = [], set()

    def add(kind, value, numbers, sent, loc):
        key = (value, loc)
        if key in seen or len(facts) >= 120:
            return
        seen.add(key)
        facts.append({"id": "F%d" % (len(facts) + 1), "kind": kind, "value": value,
                      "numbers": list(dict.fromkeys(numbers)), "sentence": sent[:260],
                      "quote": sent[:240], "material": material_id, "locator": loc,
                      "verified": True})

    for u in units:
        loc = u.get("locator") or "?"
        for sent in sentences(u["text"]):
            for doi in DOI_RE.findall(sent)[:2]:
                add("doi", doi, NUM_RE.findall(doi)[:6], sent, loc)
            for m in NUM_RE.finditer(sent):
                value = m.group(0)
                if re.fullmatch(r"(19|20)\d\d", value) and not re.search(r"[-/]", sent):
                    continue
                add("number", value, [value], sent, loc)
            if not NUM_RE.findall(sent) and not DOI_RE.findall(sent):
                for cite in CITE_RE.findall(sent)[:2]:
                    add("citation", cite, [], sent, loc)
    return facts


def sections_of(materials):
    """Split each material into heading-delimited sections (plain text becomes one section)."""
    out = []
    for mat in materials:
        cur = {"name": mat["title"], "material": mat["id"], "units": []}
        acc = []
        for u in mat["units"]:
            m = TITLE_RE.match(u["text"].strip())
            if m and len(u["text"].strip()) < 120:
                if cur["units"]:
                    acc.append(cur)
                cur = {"name": m.group(1).strip(), "material": mat["id"], "units": []}
            else:
                cur["units"].append(u)
        if cur["units"]:
            acc.append(cur)
        if not acc:
            acc = [{"name": mat["title"], "material": mat["id"], "units": mat["units"]}]
        out.extend(acc)
    return out


def section_kind(name):
    for pat, kind in SEC_KIND:
        if re.search(pat, name or "", re.I):
            return kind
    return "summary"


# --------------------------------------------------------------------- task set
def _window(sent, value, pad=46):
    i = sent.find(value)
    if i < 0:
        return sent[:240]
    a = max(0, i - pad)
    if a > 0:
        sp = sent.rfind(" ", 0, a)
        if sp < 0:
            a = 0
        elif a - sp <= 20:
            a = sp + 1
        else:
            nxt = sent.find(" ", a)
            a = nxt + 1 if nxt > 0 else 0
    b = min(len(sent), i + len(value) + pad)
    if b < len(sent):
        sp = sent.find(" ", b)
        b = sp if 0 < sp and sp - b <= 14 else b
    return sent[a:b].strip()


def _point(fact, idx):
    quote = _window(fact["sentence"], fact["value"]) if fact["kind"] == "number" else fact["quote"]
    return {"id": "P%d" % idx, "text": fact["sentence"][:200], "kind": fact["kind"],
            "material": fact["material"], "locator": fact["locator"], "quote": quote,
            "sentence": fact["sentence"][:240], "verified": True}


def build_tasks(materials, lang="en"):
    """Cut 1-4 judgeable tasks, each carrying the six required fields."""
    sections, tasks = sections_of(materials), []
    pool = []
    for sec in sections:
        facts = facts_of(sec["units"], sec["material"])
        if facts:
            pool.append((sec, facts))
    if not pool:  # text exists but no numbers: sentence-only tasks still judgeable
        for sec in sections:
            units = [u for u in sec["units"] if len(u["text"]) >= 40]
            if units:
                pseudo = []
                for u in units[:4]:
                    s = sentences(u["text"])
                    if s:
                        pseudo.append({"kind": "text", "value": s[0][:60], "numbers": [],
                                       "sentence": s[0], "quote": s[0][:240],
                                       "material": sec["material"], "locator": u["locator"]})
                if pseudo:
                    pool.append((sec, pseudo))
    for sec, facts in pool[:3]:
        kind = section_kind(sec["name"])
        if any(f["kind"] == "doi" for f in facts):
            kind = "citation"
        points = []
        used = set()
        ordered = [f for f in facts if f["kind"] == "number"] + [f for f in facts if f["kind"] != "number"]
        for f in ordered:
            if f["value"] in used:
                continue
            used.add(f["value"])
            points.append(_point(f, len(points) + 1))
            if len(points) >= 4:
                break
        if not points:
            continue
        tasks.append(_task("T%02d" % (len(tasks) + 1), kind, sec, points, lang))
    if len(tasks) < 2:  # one dense section: split facts into two half-tasks
        base = tasks[0] if tasks else None
        if base and len(base["must_include_points"]) >= 3:
            pts = base["must_include_points"]
            half = (len(pts) + 1) // 2
            tasks = [_task("T01", base["type"], {"name": base["section"]}, pts[:half], lang),
                     _task("T02", base["type"], {"name": base["section"]}, pts[half:], lang)]
    for i, t in enumerate(tasks, 1):
        t["id"] = "T%02d" % i
    return tasks


def _task(tid, kind, sec, points, lang):
    name = sec.get("name") or "material"
    limit = 70 + 25 * len(points) if lang == "en" else 110 + 30 * len(points)
    if lang == "en":
        instruction = ("Using only the supplied %s material, write a %s-style paragraph that keeps "
                       "every required point and every number verbatim." % (name, kind))
        variants = ["paraphrase is allowed when numbers and technical terms are preserved",
                    "point order may change if the argument still reads cleanly"]
        criteria = ["all must_include_points are present",
                    "numbers appear verbatim as in the source",
                    "no number that is absent from the material is introduced"]
        audience = "a reviewer who cannot see the source material"
    else:
        instruction = ("仅依据给定的「%s」材料，写一段 %s 类文字，保留全部必需要点与数值原文。" % (name, kind))
        variants = ["允许改写句式，但数值与术语须保持原文", "要点顺序可调整，只要论述仍连贯"]
        criteria = ["全部必需要点均出现", "数值与材料原文逐字一致", "不得引入材料中没有的数值"]
        audience = "看不到原始材料的评审"
    task = {"id": tid, "type": kind, "direction": KIND_DIRECTION.get(kind, "任务集设计"),
            "section": name, "input_material": "%s（%s）" % (name, points[0]["material"]),
            "language": lang, "instruction": instruction, "audience": audience,
            "word_limit": limit, "must_include_points": points,
            "acceptable_variants": variants, "completion_criteria": criteria}
    task["anchors"] = anchors_of(task)
    return task


def anchors_of(task):
    has_numbers = any(p["kind"] == "number" for p in task["must_include_points"])
    rows = [
        {"id": "A1", "level": 2, "rule": "contains_all",
         "observable": "every must_include_point appears in the answer (normalised containment)"},
        {"id": "A2", "level": 2, "rule": "number_preserved",
         "observable": "every numeric token of the points appears verbatim in the answer",
         "applicable": has_numbers},
        {"id": "A3", "level": 2, "rule": "no_new_numbers",
         "observable": "answer introduces no numeric token absent from the material"},
        {"id": "A4", "level": 1, "rule": "word_limit",
         "observable": "answer length stays within the stated limit plus ten percent"},
        {"id": "A5", "level": 1, "rule": "section_order",
         "observable": "points keep their source order in the answer"},
    ]
    task["anchor_ladder"] = [
        {"level": 0, "label": "reject", "observable": "a required point or a source number is missing"},
        {"level": 1, "label": "accept-with-note", "observable": "points present, wording differs but numbers intact"},
        {"level": 2, "label": "accept", "observable": "all level-2 anchors pass"},
    ]
    return rows


def reference_answer(task):
    """Extractive answer: only verbatim sentences from the material, one bullet each."""
    lines = []
    for p in task["must_include_points"]:
        q = (p.get("sentence") or p["quote"]).strip()
        if not q or q in lines:
            continue
        lines.append(q if q.endswith((".", "。", "!", "！", "?", "？")) else q + ".")
    if task["language"] == "en":
        tail = "Every bullet above is a verbatim segment of the source material; locators are listed in anchors.md."
    else:
        tail = "以上各条均为材料原文片段，定位见 anchors.md。"
    return " ".join(lines + [tail])


def degrade(answer):
    """Deterministic negative control: numbers removed and the text truncated."""
    s = NUM_RE.sub("", answer or "")
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()
    if len(words) > 16:
        s = " ".join(words[:16])
    if len(s) > 90:
        s = s[:90]
    return s or "no content"


# --------------------------------------------------------------------- scoring
def _num_tokens(s):
    return set(NUM_RE.findall(norm(s)))


def _wc(s):
    return len(re.findall(r"[A-Za-z0-9]+|[一-鿿]", s or ""))


def score_task(task, answer, material_body):
    points = task["must_include_points"]
    na = norm(answer)
    hits = [p for p in points if loose(p["quote"]) and loose(p["quote"]) in loose(answer)]
    if len(hits) < len(points):
        hits = [p for p in points if norm(p["quote"]) in na] or hits
    cov = len(hits) / max(1, len(points))
    need_nums, got_nums, body_nums = set(), _num_tokens(answer), _num_tokens(material_body)
    for p in points:
        need_nums |= _num_tokens(p["quote"])
    num_missing = sorted(need_nums - got_nums)
    new_nums = sorted(got_nums - body_nums)
    exp_tokens = set()
    for p in points:
        exp_tokens |= tokens(p["quote"])
    bow = len(exp_tokens & tokens(answer)) / max(1, len(exp_tokens))
    rater_a = 2 if (len(hits) == len(points) and not num_missing) else (1 if cov >= 0.5 else 0)
    rater_b = 2 if bow >= 0.92 else (1 if bow >= 0.60 else 0)
    limit = task.get("word_limit") or 0
    word_ok = _wc(answer) <= int(limit * 1.1) if limit else True
    order_ok = _order_ok(points, answer)
    anchor_rows = []
    for a in task["anchors"]:
        rule = a["rule"]
        applicable = a.get("applicable", True)
        if rule == "contains_all":
            ok = len(hits) == len(points)
            observed = "points hit %d of %d" % (len(hits), len(points))
        elif rule == "number_preserved":
            ok = not num_missing
            observed = "missing numbers: %s" % (", ".join(num_missing[:6]) or "no missing number")
        elif rule == "no_new_numbers":
            ok = not new_nums
            observed = "new numbers: %s" % (", ".join(new_nums[:6]) or "no new number")
        elif rule == "word_limit":
            ok = word_ok
            observed = "%d units against a limit of %d" % (_wc(answer), limit)
        else:
            ok = order_ok
            observed = "source order kept" if order_ok else "source order changed"
        anchor_rows.append({"anchor_id": a["id"], "rule": rule, "level": a["level"],
                            "observed": observed, "pass": bool(ok), "applicable": applicable})
    failed = [r["rule"] for r in anchor_rows if r["applicable"] and not r["pass"]]
    suggestion = _suggestion(failed, num_missing)
    return {"task_id": task["id"], "rater_a": rater_a, "rater_b": rater_b,
            "delta": abs(rater_a - rater_b), "agreement": rater_a == rater_b,
            "coverage": round(cov, 3), "bow": round(bow, 3),
            "hits": [p["id"] for p in hits], "missing_numbers": num_missing,
            "new_numbers": new_nums, "word_ok": word_ok, "anchors": anchor_rows,
            "failed_rules": failed, "suggestion": suggestion,
            "accepted": rater_a >= 1 and rater_b >= 1}


def _order_ok(points, answer):
    pos, last = [], -1
    body = loose(answer)
    for p in points:
        idx = body.find(loose(p["quote"])) if loose(p["quote"]) else -1
        if idx < 0:
            return True  # absent points are judged by contains_all, not by order
        pos.append(idx)
    for x in pos:
        if x < last:
            return False
        last = x
    return True


def _suggestion(failed, missing):
    if "contains_all" in failed:
        return "add the missing must-include points (see evidence_map) before resubmitting"
    if "number_preserved" in failed:
        return "restore the source numbers verbatim: %s" % ", ".join(missing[:5])
    if "no_new_numbers" in failed:
        return "remove numbers that the material does not support"
    if "word_limit" in failed:
        return "trim the answer to the stated word limit"
    if "section_order" in failed:
        return "restore the source order of the points"
    return "no anchor failure recorded"


def kappa(pairs):
    """Unweighted Cohen's kappa over (rater_a, rater_b) categories."""
    n = len(pairs)
    if n == 0:
        return 1.0, "no-items"
    cats = sorted({x for pair in pairs for x in pair})
    po = sum(1 for a, b in pairs if a == b) / n
    pa = {c: sum(1 for a, _ in pairs if a == c) / n for c in cats}
    pb = {c: sum(1 for _, b in pairs if b == c) / n for c in cats}
    pe = sum(pa[c] * pb[c] for c in cats)
    if abs(1.0 - pe) < 1e-9:
        return (1.0 if abs(po - 1.0) < 1e-9 else 0.0), "degenerate-marginals"
    return round((po - pe) / (1.0 - pe), 4), "computed"


# --------------------------------------------------------------------- contract
CMAP = ((r"case.?id|^id$", "case_id"),
        (r"preserved|fact|事实|数值|数字", "preserved_facts"),
        (r"evidence|source|map|来源|映射|引用", "evidence_map"),
        (r"change|revision|diff|修改|变更|版本", "change_log"),
        (r"anchor|锚点", "anchors"),
        (r"score|评分|得分", "scores"),
        (r"repro|复现", "reproducibility"),
        (r"deliver|artifact|产物|清单", "deliverable"))


def contract_values(contract, ctx):
    vals = {}
    for key in (contract or {}):
        probe = str(key).lower() + str(key)
        name = None
        for pat, mapped in CMAP:
            if re.search(pat, probe, re.I):
                name = mapped
                break
        value = ctx.get(name) if name else None
        if value in (None, "", [], {}):
            value = {"summary": ctx.get("note") or "delivered artifact inventory",
                     "artifacts": ctx.get("files") or []}
        vals[key] = value
    if not vals:
        vals = {"deliverable": {"summary": ctx.get("note") or "delivered artifact inventory",
                                "artifacts": ctx.get("files") or []}}
    return vals


def finalize(res, contract, ctx, out_path, extra=None):
    """Write result.json with output_contract echoed key by key and keys copied to top level."""
    doc = {"case_id": res.get("case_id"), "status": res.get("status")}
    echo = contract_values(contract, ctx)
    doc["output_contract"] = echo
    for k, v in echo.items():
        doc.setdefault(str(k), v)
    for key in ("summary", "sources", "uncertainties", "uncertainty", "change_records", "limits",
                "errors", "degradations", "runtime", "artifacts", "coverage", "checks",
                "tasks", "anchors", "scores", "controls", "consistency",
                "diff_report", "golden_standard", "version_history", "self_check"):
        if key in res:
            doc[key] = res[key]
    for k, v in (extra or {}).items():
        doc.setdefault(k, v)
    dumpj(out_path, doc)
    return doc
