#!/usr/bin/env python3
"""litread-bench-ledger io layer: material scan, stable locators, verbatim quote
verification, output_contract echo, case/workorder discovery. Stdlib only."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
import zlib
from html import unescape
from pathlib import Path

V = "1.0.0"
NM = "litread-bench-ledger"
T0 = time.time()
TT = ("extraction", "numeric", "method", "definition", "table", "conflict", "coverage", "other")
TEXT_EXT = {".md", ".txt", ".text", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm",
            ".xml", ".tex", ".yaml", ".yml", ".rst", ".log", ".bib", ".srt"}
IDK = ("case_id", "caseId", "task_id", "sample_id", "id")
CONK = ("output_contract", "outputContract", "contract", "required_outputs",
        "result_contract", "output_schema", "required_fields")
TASKK = ("task_instruction", "instruction", "prompt", "task_description", "task")
WOK = ("organizer_workorder", "workorder", "benchmark_workorder", "work_order",
       "items", "tasks", "cards", "questions", "item_cards")
CANDK = ("candidate_outputs", "candidate_output", "candidate_answers", "candidate_answer",
         "baseline_output", "model_output", "submissions", "responses")
CHKK = ("checker_log", "checker_logs", "technical_logs", "synthetic_logs")
CTX_MAP = (
    ("case_id", ("case_id", "caseid", "task_id", "sample_id")),
    ("status", ("status", "state", "run_status")),
    ("result", ("result", "main_result", "final_result", "deliverable")),
    ("claims", ("claim", "finding", "assertion", "conclusion")),
    ("uncertainty", ("uncertaint", "caveat", "limitation")),
    ("anchors", ("anchor", "evidence", "citation", "quote", "locator", "provenance", "proof")),
    ("scoring", ("score", "scoring", "grade", "rubric", "panel", "aggregate", "metric", "stat")),
    ("failures", ("failure", "reject", "error_case", "issue", "defect")),
    ("version_record", ("version", "diff", "compar", "history", "changelog", "iteration")),
    ("benchmark", ("item", "card", "question", "test", "suite", "tasks", "answer")),
    ("coverage_matrix", ("coverage", "completeness", "axis")),
    ("sources", ("source", "material", "input", "document", "corpus")),
    ("outputs", ("output", "artifact", "file", "path")),
    ("technical_synthetic", ("checker", "synthetic")),
)


def PK():
    return Path(__file__).resolve().parent.parent


def _home(env, cands, rel, make):
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    for c in cands:
        try:
            if Path(c).is_dir():
                return Path(c)
        except OSError:
            pass
    if make:
        try:
            p = Path(cands[0])
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            pass
    return PK().parent / rel


INPUT = _home("LITREAD_INPUT", ["/input", str(PK().parent / "input")], "input", False)
OUTPUT = _home("LITREAD_OUTPUT", ["/app/output", str(PK().parent / "output")], "output", True)
WORK = _home("LITREAD_WORK", ["/app/work", str(PK().parent / "work")], "work", True)


def set_roots(inp=None, out=None, wrk=None):
    global INPUT, OUTPUT, WORK
    if inp:
        INPUT = Path(inp).expanduser().resolve()
    if out:
        OUTPUT = Path(out).expanduser().resolve()
    if wrk:
        WORK = Path(wrk).expanduser().resolve()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def rd(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(e), e
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "ignore"), "utf-8-ignore"


def rj(p):
    t = rd(p)[0].replace("\ufeff", "").strip()
    if not t:
        raise ValueError("empty json file")
    return json.loads(t)


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wt(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s if s.endswith("\n") else s + "\n", encoding="utf-8")


def nm(s):
    return re.sub(r"\s+", " ", (s if isinstance(s, str) else "").replace("\ufeff", "")).strip()


def sq(s):
    return re.sub(r"\s+", "", s if isinstance(s, str) else "")


def sha(o):
    b = o if isinstance(o, bytes) else json.dumps(o, ensure_ascii=False, sort_keys=True,
                                                  default=str).encode("utf-8")
    return hashlib.sha1(b).hexdigest()


def dget(o, keys, d=0):
    if d > 5:
        return None
    low = [k.lower().replace("-", "_") for k in keys]
    if isinstance(o, dict):
        for k, v in o.items():
            if str(k).lower().replace("-", "_") in low and v not in (None, "", [], {}):
                return v
        for v in list(o.values())[:8]:
            r = dget(v, keys, d + 1)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o[:8]:
            r = dget(v, keys, d + 1)
            if r is not None:
                return r
    return None


def pick(d, *names, **kw):
    if not isinstance(d, dict):
        return kw.get("default")
    for n in names:
        if d.get(n) not in (None, "", [], {}):
            return d[n]
    return kw.get("default")


def kind(p):
    e, h = p.suffix.lower(), b""
    try:
        h = p.read_bytes()[:8]
    except OSError:
        pass
    if h.startswith(b"%PDF") or e == ".pdf":
        return "pdf"
    if h.startswith(b"PK") or e in (".docx", ".doc", ".xlsx", ".xls", ".pptx"):
        return "xlsx" if e in (".xlsx", ".xls") else "docx"
    if e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"):
        return "image"
    return "text" if e in TEXT_EXT else "binary"


def unxml(x):
    x = re.sub(r"</(w:p|w:tr|a:p|text:p|w:tc)>", "\n\n", x)
    x = re.sub(r"<(w:br|w:cr|w:tab)\s*/?>", "\n", x)
    return unescape(re.sub(r"<[^>]+>", "", x))


def zpart(p, part, pref):
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if part not in names:
            c = [x for x in names if x.startswith(pref) and x.endswith(".xml")]
            if not c:
                raise ValueError("missing " + part)
            part = c[0]
        return z.read(part).decode("utf-8", "ignore")


def pdfq(t):
    s = (t or "")[:4000]
    if len(s.strip()) < 40:
        return 0.0
    return round(min(sum(c.isprintable() or c in "\n\t" for c in s) / len(s),
                     sum(c.isalpha() or c.isspace() for c in s) / len(s)), 3)


def pdf_raw(p):
    d, out = Path(p).read_bytes(), []
    for m in re.finditer(rb"stream\r?\n", d):
        end = d.find(b"endstream", m.end())
        if end < 0:
            continue
        try:
            raw = zlib.decompressobj().decompress(d[m.end():end])
        except Exception:
            continue
        parts = []
        for t in re.finditer(rb"\((?:\\\\.|[^\\\\()])*\)", raw):
            s = re.sub(rb"\\\\([nrtbf()\\\\])",
                       lambda x: b" " if x.group(1) in b"nrtbf" else x.group(1), t.group()[1:-1])
            parts.append(s.decode("latin-1"))
        j = " ".join(parts)
        if j.strip():
            out.append(j)
    return "\f".join(out)


def ext_pdf(p):
    if shutil.which("pdftotext"):
        try:
            t = subprocess.run([shutil.which("pdftotext"), "-layout", str(p), "-"],
                               capture_output=True, timeout=90).stdout.decode("utf-8", "ignore")
            if pdfq(t) >= 0.55:
                return t, "pdftotext", pdfq(t)
        except Exception:
            pass
    for name, fn in (("pymupdf", lambda: "\f".join(g.get_text() for g in __import__("fitz").open(str(p)))),
                     ("pdfminer", lambda: __import__("pdfminer.high_level", fromlist=["x"]).extract_text(str(p)))):
        try:
            t = fn()
            if pdfq(t) >= 0.55:
                return t, name, pdfq(t)
        except Exception:
            pass
    try:
        return pdf_raw(p), "stdlib-zlib", pdfq(pdf_raw(p) if False else "")
    except Exception:
        return "", "failed", 0.0


def extract(p, k):
    if k == "text":
        t, e = rd(p)
        return t, "plain/" + e, ""
    if k == "docx":
        return unxml(zpart(p, "word/document.xml", "word/")), "docx-xml", ""
    if k == "xlsx":
        try:
            return unxml(zpart(p, "xl/sharedStrings.xml", "xl/")), "xlsx-xml", "cell strings only"
        except Exception as e:
            return "", "failed", "xlsx: %s" % e
    if k == "pdf":
        t, m, q = ext_pdf(p)
        return t, "pdf/" + m, "" if q >= 0.55 else "low_text_quality=%.2f" % q
    if k == "image":
        return "", "none", "image material: no stdlib OCR, needs visual/OCR pass"
    return "", "none", "unsupported binary type"


def blocks(t):
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n")
    raw = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
    if len(raw) < 3:
        raw = [b.strip() for b in t.split("\n") if b.strip()]
    out = [re.sub(r"[ \t]+", " ", b).strip() for b in raw]
    out = [b for b in out if len(b) >= 25]
    return out or ([nm(t)] if nm(t) else [])


def units(t):
    if "\f" in t:
        return [(i + 1, b) for i, pg in enumerate(t.split("\f")) for b in blocks(pg)]
    return [(None, b) for b in blocks(t)]


def structured(t):
    """Paragraphs / table rows from a JSON source, keeping the source's native ids."""
    try:
        o = json.loads(t.replace("\ufeff", ""))
    except Exception:
        return []
    out = []

    def walk(x):
        if isinstance(x, dict):
            txt = x.get("text") or x.get("content") or x.get("paragraph") or x.get("sentence")
            if isinstance(txt, str) and len(txt.strip()) >= 25:
                nid = x.get("paragraph_id") or x.get("para_id") or x.get("pid") or x.get("id")
                out.append((txt.strip(), str(nid) if nid else None))
                return
            rows = x.get("rows") or x.get("cells") or x.get("records")
            if isinstance(rows, list) and rows and all(isinstance(r, (list, dict)) for r in rows):
                nid = x.get("table_id") or x.get("id") or x.get("name")
                flat = [" | ".join("%s=%s" % (k, v) for k, v in r.items()) if isinstance(r, dict)
                        else " | ".join(str(c) for c in r) for r in rows]
                body = "\n".join(flat).strip()
                if len(body) >= 20:
                    out.append((body, str(nid) if nid else None))
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(o)
    return out


def scan(ip):
    ip = Path(ip)
    idx = {"schema": NM + "/index@1", "generated_at": now(), "input_root": str(ip),
           "materials": [], "n_paragraphs": 0, "degradations": [], "errors": []}
    if not ip.is_dir():
        idx["errors"].append({"stage": "scan", "error": "input root not found: %s" % ip})
        return idx
    try:
        files = [p for p in sorted(ip.rglob("*")) if p.is_file() and not p.name.startswith(".")
                 and not any(s in p.parts for s in ("__pycache__", ".git", "node_modules"))
                 and not (p.parent == ip and p.name in ("case.json", "task.md", "result.json"))]
    except OSError as e:
        idx["errors"].append({"stage": "scan", "error": str(e)})
        return idx
    mats, deg, errs = idx["materials"], idx["degradations"], idx["errors"]
    for n, p in enumerate(files, 1):
        mid, k = "M%02d" % n, kind(p)
        rec = {"mid": mid, "name": p.name, "path": str(p), "kind": k, "status": "ok",
               "method": "none", "note": "", "bytes": -1, "sha1": None,
               "paragraphs": [], "chars": 0, "n_native_ids": 0}
        try:
            b = p.read_bytes()
            rec["bytes"], rec["sha1"] = len(b), sha(b)[:16]
        except OSError:
            pass
        try:
            t, m, note = extract(p, k)
            rec.update(method=m, note=note)
            if note:
                deg.append({"material": mid, "file": p.name, "issue": note,
                            "action": "quote needs re-verification with platform parser"})
            if not t.strip():
                rec["status"] = "no_text"
                errs.append({"stage": "material", "material": mid, "error": "no extractable text"})
            st = structured(t) if k == "text" else []
            if st:
                for i, (body, nid) in enumerate(st, 1):
                    par = {"pid": "%s#p%d" % (mid, i), "n": i, "text": re.sub(r"[ \t]+", " ", body)}
                    if nid:
                        par["native_id"] = nid
                        rec["n_native_ids"] += 1
                    rec["paragraphs"].append(par)
                rec["method"] = m + "+json-structured"
            else:
                for i, (pg, body) in enumerate(units(t), 1):
                    par = {"pid": "%s#p%d" % (mid, i), "n": i, "text": body}
                    if pg:
                        par["page"] = pg
                    rec["paragraphs"].append(par)
            rec["chars"] = sum(len(x["text"]) for x in rec["paragraphs"])
        except Exception as e:
            rec.update(status="error", note="extract_failed: %s" % e)
            errs.append({"stage": "material", "material": mid, "error": str(e)})
            deg.append({"material": mid, "file": p.name, "issue": "extract_failed: %s" % e,
                        "action": "treated as no_text"})
        mats.append(rec)
    idx["n_paragraphs"] = sum(len(m["paragraphs"]) for m in mats)
    return idx


def cache(idx):
    c = {}
    for m in idx.get("materials", []):
        buf, spans = "", []
        for par in m.get("paragraphs", []):
            t = nm(par["text"])
            if not t:
                continue
            buf += (" " if buf else "") + t
            spans.append((len(buf) - len(t), len(buf), par))
        if spans:
            c[m["mid"]] = {"t": buf, "cf": buf.casefold(), "sq": sq(buf), "spans": spans}
    return c


def verify(c, mid, q):
    """exact -> casefold -> whitespace-insensitive; locator comes from the real hit."""
    q = nm(q)
    if len(q) < 12:
        return {"verified": False, "reason": "quote_too_short_or_empty"}
    m = c.get(mid)
    if not m:
        return {"verified": False, "reason": "material_not_indexed"}
    for mode, needle, hay in (("exact", q, m["t"]), ("casefold", q.casefold(), m["cf"])):
        pos = hay.find(needle)
        if pos >= 0:
            for s, e, par in m["spans"]:
                if s <= pos < e or (pos < s < pos + len(needle)):
                    return {"verified": True, "match": mode, "pid": par["pid"],
                            "page": par.get("page"), "native_id": par.get("native_id")}
            return {"verified": True, "match": mode, "pid": None}
    if sq(q) and sq(q) in m["sq"]:
        pos, acc = m["sq"].find(sq(q)), 0
        for s, e, par in m["spans"]:
            acc += len(sq(par["text"]))
            if pos < acc:
                return {"verified": True, "match": "no_whitespace", "pid": par["pid"],
                        "page": par.get("page"), "native_id": par.get("native_id")}
        return {"verified": True, "match": "no_whitespace", "pid": None}
    return {"verified": False, "reason": "quote_not_found"}


def load_case(ip):
    ip = Path(ip)
    cands = [ip / "case.json"]
    try:
        cands += sorted(ip.glob("case*.json"))
    except OSError:
        pass
    for p in cands:
        try:
            if p.is_file():
                o = rj(p)
                return (o if isinstance(o, dict) else {"_raw": o}), p
        except Exception as e:
            return {"_bad_json": "%s: %s" % (p.name, e)}, p
    return {}, None


def read_task_md(ip):
    for name in ("task.md", "TASK.md", "task.txt"):
        p = Path(ip) / name
        if p.is_file():
            try:
                return rd(p)[0], p
            except OSError:
                pass
    return "", None


def ckeys(con):
    if isinstance(con, dict):
        return [str(k) for k in con]
    out = []
    for x in (con if isinstance(con, list) else []):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for k in ("name", "field", "key", "id", "path", "title"):
                if isinstance(x.get(k), str):
                    out.append(x[k])
                    break
    return out


def mirror(s):
    if isinstance(s, dict):
        return {k: mirror(v) for k, v in s.items()}
    return [] if isinstance(s, list) else None


def _listish(lk):
    return lk.endswith("s") or lk.endswith("_items") or "list" in lk


def fill_contract(con, ctx):
    """Echo every declared contract key: real value if known, else null/[]. Never drops a key."""
    out, diag = {}, {}
    for k in ckeys(con):
        lk = str(k).lower().replace("-", "_").replace(" ", "_")
        v, src = None, "unmapped"
        if ctx.get(lk) is not None:
            v, src = ctx[lk], "exact"
        if v is None:
            for ck, pats in CTX_MAP:
                if any(p in lk for p in pats):
                    if ctx.get(ck) is not None:
                        v, src = ctx[ck], "semantic:" + ck
                    break
        if v is None and isinstance(con, dict):
            v, src = mirror(con[k]), "contract_mirror"
        if v is None:
            v, src = ([] if _listish(lk) else None), "placeholder"
        out[k] = v
        diag[k] = {"filled": v not in (None, [], {}), "from": src}
    return out, diag


def shell(cid, con, status, stage):
    return {"case_id": cid, "status": status, "stage": stage,
            "skill": {"name": NM, "version": V},
            "outputs": {}, "benchmark": None, "anchors": None, "scoring": None,
            "coverage_matrix": None, "calibration": None, "version_record": None,
            "failures": [], "sources": [], "uncertainty": [], "pending_human": [],
            "errors": [], "degradations": [], "changes": [],
            "technical_synthetic": {"present": False, "not_a_dsh_score": True},
            "runtime": {"skill_version": V, "python": sys.version.split()[0],
                        "started_at": now(), "elapsed_s": 0.0, "input_root": str(INPUT),
                        "output_root": str(OUTPUT), "work_root": str(WORK)},
            "contract_fields_present": ckeys(con), "contract_echo": con if con else {},
            "contract_fill": {}}


def save(res, stage):
    res.setdefault("runtime", {}).update({"stage": stage, "written_at": now(),
                                          "elapsed_s": round(time.time() - T0, 2),
                                          "argv": sys.argv[1:]})
    wj(OUTPUT / "result.json", res)


def prep(stage, case):
    """Write a legal partial result.json before anything expensive runs."""
    for d in (OUTPUT, WORK):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    con = dget(case, CONK) if isinstance(case, dict) else None
    con = con if isinstance(con, (dict, list)) else {}
    cid = dget(case, IDK) if isinstance(case, dict) else None
    res = shell(str(cid) if cid else None, con, "partial", stage)
    filled, diag = fill_contract(con, {})
    res.update(filled)
    res["contract_fill"] = diag
    res["pending_human"] = ["main.py show -> write work/draft.json -> check -> build"]
    save(res, stage)
    return res, con


def get_index(res=None):
    p = WORK / "index.json"
    if p.is_file():
        try:
            return rj(p)
        except Exception as e:
            if res is not None:
                res.setdefault("errors", []).append({"stage": "index", "error": str(e)})
    idx = scan(INPUT)
    wj(p, idx)
    return idx


def srcs(idx):
    return [{"id": m["mid"], "name": m["name"], "path": m["path"], "kind": m["kind"],
             "bytes": m["bytes"], "sha1": m["sha1"], "paragraphs": len(m["paragraphs"]),
             "chars": m["chars"], "status": m["status"], "method": m["method"],
             "note": m["note"], "native_ids": m.get("n_native_ids", 0)}
            for m in idx.get("materials", [])]


def workorder(case):
    """Normalise organizer workorder items (0..n). Absent -> []."""
    raw = dget(case, WOK) if isinstance(case, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("items") or raw.get("tasks") or raw.get("cards") or raw.get("workorder")
    if not isinstance(raw, list):
        raw = []
        try:
            files = sorted(Path(INPUT).rglob("*workorder*.json"))
        except OSError:
            files = []
        for p in files:
            try:
                o = rj(p)
                raw = o if isinstance(o, list) else (
                    o.get("items") or o.get("tasks") or o.get("cards") or [])
                raw = raw if isinstance(raw, list) else []
                if raw:
                    break
            except Exception:
                continue
    out = []
    for i, x in enumerate(raw, 1):
        if isinstance(x, str):
            out.append({"item_id": "W%02d" % i, "task": nm(x), "task_type": "other",
                        "source_refs": [], "reference_answer": None, "reference_missing": True,
                        "scoring_rule": None, "difficulty": None, "license": "unknown",
                        "origin": "workorder"})
            continue
        if not isinstance(x, dict):
            continue
        refs = pick(x, "source_refs", "sources", "material_refs", "refs", "source_documents",
                    "document_ids", default=[])
        refs = refs if isinstance(refs, list) else [refs]
        refs = [r if isinstance(r, dict) else {"ref": str(r)} for r in refs if r not in (None, "")]
        ans = pick(x, "reference_answer", "gold", "answer", "expected_answer")
        out.append({"item_id": str(pick(x, "item_id", "id", "qid", "task_id", "card_id",
                                       default="W%02d" % i)),
                    "task": nm(str(pick(x, "task", "question", "instruction", "prompt",
                                        "description", default="")))[:600],
                    "task_type": str(pick(x, "task_type", "type", "category", default="other")),
                    "source_refs": refs, "reference_answer": ans,
                    "reference_missing": ans in (None, "", [], {}),
                    "scoring_rule": pick(x, "scoring_rule", "rubric", "grading_rule"),
                    "difficulty": pick(x, "difficulty", "level", "hardness"),
                    "license": pick(x, "license", "rights", "data_license", default="unknown"),
                    "origin": "workorder"})
    return out


def candidates(case):
    found = []
    raw = dget(case, CANDK) if isinstance(case, dict) else None
    if isinstance(raw, (list, dict)) and raw:
        found.append({"output_id": "case:candidate", "agent": "case_candidate",
                      "source": "case.json", "payload": raw})
    ip = Path(INPUT)
    if ip.is_dir():
        try:
            for p in sorted(ip.rglob("*")):
                if p.is_file() and p.parent != ip and re.search(
                        r"(candidate|baseline|response|model_out|checker|submission)", p.name.lower()):
                    found.append({"output_id": "file:" + p.name, "agent": "file:" + p.name,
                                  "source": str(p), "payload": None})
                if len(found) >= 6:
                    break
        except OSError:
            pass
    return found[:6]


def checker_note():
    files = []
    try:
        files = [p.name for p in Path(INPUT).rglob("*checker*")]
    except OSError:
        pass
    return {"present": bool(files), "not_a_dsh_score": True, "kind": "technical_synthetic",
            "scored": False, "sources": files[:5],
            "note": "checker/synthetic logs are registered only: not a DSH score, not "
                    "independent semantic validation"}
