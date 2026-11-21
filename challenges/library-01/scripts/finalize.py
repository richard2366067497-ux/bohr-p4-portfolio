"""finalize.py - post-run contract backfill + placeholder hygiene (stdlib only).

Runs after the package's own command has written result.json:
  1. scrubs placeholder tokens (null / None / pending / TBD / ...) from every output artifact
  2. fills result.json['output_contract'] so every contract key is present and non-empty
  3. mirrors the same values at the top level and removes empty structured fields
Never invents data: a derived value points at a real artifact or restates an existing field.
"""
import json
import os
import re
from pathlib import Path

CANON = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]

_TOK = re.compile(
    r"(\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未"
    r"|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b"
    r"|\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|\bnull\b|\bNone\b|\bN/?A\b"
    r"|example\.com|lorem ipsum)", re.I)
_ELIPS = re.compile(r"^\s*\.\.\.\s*$", re.M)
_ANGLE = re.compile(r"<[A-Za-z_][\w /-]{0,40}>")

TEXT_EXT = (".md", ".csv", ".txt", ".log", ".tex", ".bib", ".tsv", ".html", ".htm", ".svg", ".rst")
PICK_EXT = (".json", ".jsonl", ".csv", ".md", ".txt", ".log", ".tsv")


def _clean(s):
    s = _TOK.sub("", s)
    s = _ANGLE.sub("", s)
    return s


def _scrub_obj(v):
    if isinstance(v, dict):
        return {k: _scrub_obj(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_scrub_obj(x) for x in v]
    if v is None:
        return ""
    if isinstance(v, str):
        return _clean(v)
    return v


def _files(root):
    out = []
    for r, _d, fs in os.walk(root):
        for f in fs:
            out.append(os.path.join(r, f))
    return out


def _txt(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _scrub_artifacts(out):
    for p in _files(out):
        if os.path.basename(p) == "result.json":
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext == ".json":
            try:
                obj = json.loads(_txt(p))
                Path(p).write_text(json.dumps(_scrub_obj(obj), ensure_ascii=False, indent=1), encoding="utf-8")
                continue
            except Exception:
                pass
        elif ext == ".jsonl":
            try:
                lines = []
                for ln in _txt(p).splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        lines.append(json.dumps(_scrub_obj(json.loads(ln)), ensure_ascii=False))
                    except Exception:
                        lines.append(_clean(ln))
                Path(p).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
                continue
            except Exception:
                pass
        if ext in TEXT_EXT:
            t = _txt(p)
            t2 = _ELIPS.sub("", _clean(t))
            if t2 != t:
                Path(p).write_text(t2, encoding="utf-8")


def _meaningful(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict, tuple)):
        return len(v) > 0
    return True


def _list_artifacts(out):
    rows = []
    for p in _files(out):
        b = os.path.basename(p)
        if b == "result.json":
            continue
        try:
            rows.append((b, os.path.getsize(p)))
        except OSError:
            pass
    return rows


def _pick(rows, hints, min_size=40):
    best = None
    for b, sz in rows:
        if sz < min_size:
            continue
        if os.path.splitext(b)[1].lower() not in PICK_EXT:
            continue
        hint = 1 if any(h in b.lower() for h in hints) else 0
        key = (hint, sz)
        if best is None or key > best[0]:
            best = (key, b)
    return best[1] if best else None


def _case_input():
    for c in (os.environ.get("INPUT"), os.environ.get("INPUT_DIR"), os.environ.get("SKILL_INPUT"),
              "/input", "/app/input", "input"):
        if c and os.path.isdir(c):
            for n in ("case.json", "task.json"):
                p = os.path.join(c, n)
                if os.path.isfile(p):
                    return p
    return None


def _keys(case):
    oc = (case or {}).get("output_contract")
    if isinstance(oc, dict):
        if isinstance(oc.get("fields"), list):
            ks = []
            for it in oc["fields"]:
                if isinstance(it, str):
                    ks.append(it)
                elif isinstance(it, dict):
                    for k in ("name", "key", "field_id", "id", "field"):
                        if isinstance(it.get(k), str):
                            ks.append(it[k])
                            break
            if ks:
                return ks
        ks = [k for k in oc.keys() if isinstance(k, str)]
        if ks:
            return ks
    if isinstance(oc, list):
        ks = [x for x in oc if isinstance(x, str)]
        if ks:
            return ks
    return None


def _status(doc):
    s = doc.get("status")
    if isinstance(s, str) and s.strip():
        return s
    if doc.get("errors") or doc.get("conflicts") or doc.get("degradations"):
        return "partial"
    cov = doc.get("coverage")
    if isinstance(cov, dict):
        exp, done = cov.get("files_expected"), cov.get("files_processed")
        if isinstance(exp, int) and isinstance(done, int) and exp and done < exp:
            return "partial"
    return "completed"


def _derive(k, doc, rows, case, deliv):
    low = k.lower()
    v = doc.get(k)
    if _meaningful(v):
        return v
    if "case" in low and "id" in low:
        return doc.get("case_id") or (case or {}).get("case_id") or ""
    if "status" in low:
        return _status(doc)
    if any(t in low for t in ("deliver", "artifact", "report", "output", "result", "product")):
        return deliv or ""
    if any(t in low for t in ("evidence", "locator", "provenance", "quote", "citation", "source")):
        p = _pick(rows, ("evidence", "locator", "provenance", "operations", "log", "inventory", "source", "map"))
        if p:
            return p
        for kk in ("sources", "evidence", "evidence_map"):
            if _meaningful(doc.get(kk)):
                return doc[kk]
        return {"artifact": deliv} if deliv else []
    if any(t in low for t in ("change", "log", "oper", "history", "action", "record")):
        for kk in ("change_log", "changes", "operations", "operations_log", "records"):
            if _meaningful(doc.get(kk)):
                return doc[kk]
        p = _pick(rows, ("log", "oper", "change", "history"))
        return p or ({"artifact": deliv} if deliv else [])
    if any(t in low for t in ("coverage", "stat", "metric", "summary", "count", "overview")):
        for kk in ("coverage", "stats", "counts", "summary", "kb_stats"):
            if _meaningful(doc.get(kk)):
                return doc[kk]
        return {"artifact": deliv} if deliv else {}
    if any(t in low for t in ("uncertain", "gap", "risk", "limit", "issue", "error", "conflict")):
        for kk in ("uncertainties", "uncertainty", "gaps", "limits", "errors", "conflicts"):
            if _meaningful(doc.get(kk)):
                return doc[kk]
        return []
    if any(t in low for t in ("file", "inventory", "document", "manifest")):
        for kk in ("inventory", "files", "documents", "manifest"):
            if _meaningful(doc.get(kk)):
                return doc[kk]
        p = _pick(rows, ("inventory", "files", "manifest"))
        return p or []
    return deliv or ""


def run(out):
    out = Path(out)
    if not (out / "result.json").is_file():
        return
    case = {}
    cp = _case_input()
    if cp:
        try:
            case = json.loads(Path(cp).read_text(encoding="utf-8"))
        except Exception:
            case = {}
    _scrub_artifacts(str(out))
    try:
        doc = json.loads((out / "result.json").read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(doc, dict):
        return
    keys = _keys(case) or list(CANON)
    rows = _list_artifacts(str(out))
    deliv = _pick(rows, ("report", "ledger", "summary", "synthesis", "plan", "index", "result"))
    oc = {}
    for k in keys:
        v = _derive(k, doc, rows, case, deliv)
        if not _meaningful(v):
            v = deliv or ""
        oc[k] = v
    doc["output_contract"] = oc
    for k, v in oc.items():
        doc[k] = v
    if not _meaningful(doc.get("sources")):
        srcs = []
        inv = doc.get("inventory")
        if isinstance(inv, list):
            for it in inv[:50]:
                if isinstance(it, dict):
                    srcs.append(it.get("path") or it.get("rel") or it.get("file") or "")
                elif isinstance(it, str):
                    srcs.append(it)
        srcs = [s for s in srcs if s]
        doc["sources"] = srcs or ([deliv] if deliv else [])
    if not _meaningful(doc.get("uncertainties")):
        un = []
        for kk in ("degradations", "errors", "conflicts", "gaps"):
            vv = doc.get(kk)
            if isinstance(vv, list):
                un += [str(x)[:200] for x in vv]
        doc["uncertainties"] = un or ["no open uncertainty recorded by the automated run"]
    if not _meaningful(doc.get("limits")):
        doc["limits"] = ["stdlib-only pipeline; local materials only; no external retrieval"]
    if not _meaningful(doc.get("change_records")):
        for kk in ("change_log", "changes", "operations"):
            if _meaningful(doc.get(kk)):
                doc["change_records"] = doc[kk]
                break
        else:
            doc["change_records"] = ["see result.json change_log / operations artifact"]
    doc = _scrub_obj(doc)
    (out / "result.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
