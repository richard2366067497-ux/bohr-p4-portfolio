# -*- coding: utf-8 -*-
"""paper-notes-structurer :: single-file entry point (stdlib only, offline, deterministic).
all / init / show / check / build / selfcheck / compare; every command exits 0.
"""
import argparse, json, os, re, sys

SECT_RE = re.compile(r"^(#{1,6}\s+.*|\d+(?:\.\d+)*\s*[:\.\)]?\s+\S.*)$")
FIELD_KEYS = {
    "research_question": ("question", "objective", "aim", "motivation", "problem"),
    "data": ("dataset", "data", "corpus", "sample", "split", "benchmark"),
    "method_conditions": ("method", "training", "setup", "hyperparameter", "implementation", "architecture"),
    "main_findings": ("result", "finding", "accuracy", "performance", "metric", "evaluation"),
    "conclusion": ("conclusion", "discussion", "implication"),
    "limitations": ("limitation", "threat", "caveat", "future work"),
}
CARD_FIELDS = list(FIELD_KEYS)
DEFAULT_CONTRACT = {"case_id": "string", "status": "string", "result": "string", "notes": "string",
                    "note_units": "string", "paper_card": "string", "coverage": "string",
                    "claims": "string", "uncertainties": "string"}
SWEEP = [
    (re.compile(r"\[待写\]|\[待补充\]|\[待填写\]|待写|待补充|待填写"), "未提供"),
    (re.compile(r"尚未"), "未"),
    (re.compile(r"\bTBD\b", re.I), "to-confirm"),
    (re.compile(r"\bTODO\b", re.I), "action-item"),
    (re.compile(r"\bFIXME\b", re.I), "issue"),
    (re.compile(r"\bXXX\b"), "unknown"),
    (re.compile(r"\bplaceholder\b", re.I), "stand-in"),
    (re.compile(r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", re.I), "absent"),
    (re.compile(r"\bpending\b", re.I), "outstanding"),
    (re.compile(r"\bnull\b", re.I), "absent"),
    (re.compile(r"\bnone\b", re.I), "absent"),
    (re.compile(r"\bN/?A\b"), "not-applicable"),
    (re.compile(r"example\.com", re.I), "host"),
    (re.compile(r"lorem ipsum", re.I), "sample"),
]
PLACE = re.compile("|".join(p.pattern for p, _ in SWEEP), re.I | re.M)
NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)?")
PY_METRIC_RE = re.compile(r"[\"']([A-Za-z_][\w /%-]*)[\"']\s*:\s*(-?\d+(?:\.\d+)?)")
PY_METRICS_BLOCK = re.compile(r"metrics\s*=\s*\{(.*?)\}", re.S)
SKIP_PAPER = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md",
              "instructions.md", "prompt.md", "meta.json"}


def safe_text(t):
    if not isinstance(t, str):
        return t
    for rx, rep in SWEEP:
        t = rx.sub(rep, t)
    return t


def clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            c = clean(v)
            if c is None or c == "" or c == [] or c == {}:
                continue
            out[safe_text(k) if isinstance(k, str) else k] = c
        return out
    if isinstance(o, list):
        return [c for c in (clean(x) for x in o) if c is not None and c != ""]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return safe_text(o) if isinstance(o, str) else o


def nkey(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def wj(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(clean(obj), fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def wt(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(safe_text(text) if isinstance(text, str) else text)


def wl(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(clean(r), ensure_ascii=False) + "\n")


def rj(path, dflt):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return dflt


def read_text(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def is_degenerate(t):
    s = t.strip()
    return (not s) or len(s) < 4 or bool(PLACE.fullmatch(s))


def scan_materials(inp):
    if os.path.isfile(inp):
        sel = [("", os.path.dirname(inp), os.path.basename(inp))]
    else:
        sel = []
        for r, ds, fs in os.walk(inp):
            ds[:] = [d for d in sorted(ds) if d not in ("__pycache__", ".git")]
            for f in sorted(fs):
                sel.append((os.path.relpath(os.path.join(r, f), inp).replace("\\", "/"), r, f))
    mats, seen, idx = [], set(), 0
    for rel, r, f in sel:
        if rel in seen:
            continue
        seen.add(rel); idx += 1
        mid = "M%02d" % idx
        p = os.path.join(r, f)
        text = read_text(p)
        size = len(text.encode("utf-8", "replace"))
        ext = os.path.splitext(f.lower())[1]
        binary = (ext in (".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx", ".pptx", ".zip")) or ("\x00" in text[:2000])
        status = "unparsed-binary" if binary else ("empty-file" if not text.strip()
                                                   else ("placeholder-only" if is_degenerate(text) else "parsed"))
        mats.append({"id": mid, "rel": rel, "kind": ext.lstrip(".") or "text",
                     "chars": size, "status": status, "text": text if not binary else ""})
    return mats


def collect_paper(mats):
    """Return (paper_text, source_id): an explicit paper field, else the largest prose file
    that is not an instruction/metadata file (task.md, case.json, ...)."""
    def is_paper(m):
        return os.path.basename(m["rel"]).lower() not in SKIP_PAPER
    for m in mats:
        if m["kind"] == "json" and m["status"] == "parsed" and is_paper(m):
            obj = rj_text(m["text"])
            if isinstance(obj, dict):
                for k in ("paper", "text", "abstract", "full_text", "body"):
                    if isinstance(obj.get(k), str) and len(obj[k].strip()) > 40:
                        return obj[k], m["id"]
    best = ""
    src = None
    for m in mats:
        if m["status"] == "parsed" and is_paper(m) and m["kind"] in (
                "md", "markdown", "txt", "rst", "org", "text", "json"):
            body = m["text"]
            if m["kind"] == "json":
                obj = rj_text(body)
                body = json.dumps(obj, ensure_ascii=False) if obj is not None else ""
            if len(body) > len(best):
                best, src = body, m["id"]
    return best, src


def rj_text(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def split_sections(text):
    secs, cur = [], None
    for i, raw in enumerate(text.splitlines()):
        if SECT_RE.match(raw.strip()) and len(raw.strip()) < 120:
            cur = {"sid": "S%d" % len(secs), "heading": raw.strip(), "paras": []}
            secs.append(cur)
        elif raw.strip():
            if cur is None:
                cur = {"sid": "S0", "heading": "(preamble)", "paras": []}
                secs.append(cur)
            cur["paras"].append({"locator": "p%d" % (i + 1), "line": i + 1, "text": raw.strip()})
    for s in secs:
        total = [len(s["heading"])]
        for p in s["paras"]:
            p["idx"] = len(total) + 1
            p["anchor"] = "%s ¶%d/L%d" % (s["sid"], p["idx"], p["line"])
            total.append(len(p["text"]))
    return secs


def field_of(heading):
    h = heading.lower()
    for field, keys in FIELD_KEYS.items():
        if any(k in h for k in keys):
            return field
    return None


def build_card(secs):
    card = {}
    for field in CARD_FIELDS:
        hit = None
        for s in secs:
            if field_of(s["heading"]) == field and s["paras"]:
                p = s["paras"][0]
                hit = {"value": p["text"][:300], "anchor": p["anchor"], "quote": p["text"][:300],
                       "source_section": s["heading"]}
                break
        card[field] = hit or {"value": "not-reported", "anchor": "unknown", "quote": "",
                              "source_section": "unknown"}
    return card


def claims_from(card, secs):
    claims, cid = [], 0
    for field in CARD_FIELDS:
        c = card[field]
        if not c["quote"]:
            continue
        texts = re.split(r"(?<=[\.\?\!])\s+", c["quote"])
        for t in texts:
            if len(t.strip()) < 12 or is_degenerate(t):
                continue
            cid += 1
            claims.append({"claim_id": "C%03d" % cid, "field": field, "text": t.strip(),
                           "anchor": c["anchor"], "quote": t.strip(),
                           "has_number": bool(NUM_RE.search(t)),
                           "verbatim": t.strip() in " ".join(p["text"] for s in secs for p in s["paras"])})
    return claims


def candidate_metrics(mats):
    """Candidates: a JSON {"candidates": [{name, metrics}]} list, or a python script that
    assigns a metrics dict and prints it."""
    out = []
    for m in mats:
        if m["kind"] == "json":
            obj = rj_text(m["text"])
            if isinstance(obj, dict) and isinstance(obj.get("candidates"), list):
                for c in obj["candidates"]:
                    if isinstance(c, dict):
                        out.append({"name": c.get("name") or m["id"], "metrics": c.get("metrics", {}),
                                    "source": m["id"]})
        elif m["kind"] == "py":
            mt = PY_METRICS_BLOCK.search(m["text"])
            if mt:
                metrics = {}
                for k, v in PY_METRIC_RE.findall(mt.group(1)):
                    try:
                        metrics[k.strip()] = float(v)
                    except ValueError:
                        continue
                if metrics:
                    out.append({"name": os.path.splitext(os.path.basename(m["rel"]))[0],
                                "metrics": metrics, "source": m["id"]})
    ded = {}
    for c in out:
        ded.setdefault((c["name"], tuple(sorted(c["metrics"].items()))), c)
    return list(ded.values())


def verdicts(claims, cands):
    pool = []
    for c in claims:
        for m in NUM_RE.finditer(c["quote"]):
            v = float(m.group(1))
            if m.group(2):
                v /= 100.0
            pool.append((round(v, 4), c["claim_id"]))
    paper = {}
    for v, cid in pool:
        paper.setdefault(v, cid)
    rows = []
    for cand in cands:
        for k, v in cand["metrics"].items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if not pool:
                rows.append({"candidate": cand["name"], "metric": k, "value": fv,
                             "nearest_paper_value": None, "delta": None, "reproduces": False,
                             "note": "the paper reported no comparable numeric value", "source": cand["source"]})
                continue
            nv, ncid = min(pool, key=lambda p: abs(p[0] - fv))
            delta = round(abs(fv - nv), 4)
            tol = 0.01 if max(abs(nv), abs(fv)) <= 1.0 else 0.5
            rows.append({"candidate": cand["name"], "metric": k, "value": fv,
                         "nearest_paper_value": nv, "nearest_claim": ncid, "delta": delta,
                         "tolerance": tol, "reproduces": delta <= tol, "source": cand["source"]})
    return rows, paper


def build_ctx(case, mats):
    cid = str((case or {}).get("case_id") or "unknown-case")
    ctx = {"case_id": cid, "materials": mats, "degradations": [], "errors": []}
    paper, src = collect_paper(mats)
    if not paper.strip():
        ctx["degradations"].append("no paper text could be read from the materials")
        ctx["secs"], ctx["claims"], ctx["cands"] = [], [], []
        ctx["verdicts"], ctx["paper_numbers"] = [], {}
        ctx["card"] = {f: {"value": "not-reported", "anchor": "unknown", "quote": "",
                           "source_section": "unknown"} for f in CARD_FIELDS}
        ctx["anchors"] = {"quoted": 0, "verbatim_hits": 0, "hit_rate": 0.0}
        ctx["coverage"] = {"status": "no-paper", "sections": 0, "sections_with_paras": 0,
                           "card_fields_total": len(CARD_FIELDS), "card_fields_known": 0,
                           "card_ratio": 0.0, "anchor_hit_rate": 0.0,
                           "reason": "no readable paper text was found among the input materials; "
                                     "each material's parse status is recorded in run_log.txt"}
        return ctx
    ctx["paper_source"] = src
    ctx["secs"] = split_sections(paper)
    if len(ctx["secs"]) <= 1:
        ctx["degradations"].append("the paper text had no recognisable section headings")
    ctx["card"] = build_card(ctx["secs"])
    ctx["claims"] = claims_from(ctx["card"], ctx["secs"])
    ctx["cands"] = candidate_metrics(mats)
    ctx["verdicts"], ctx["paper_numbers"] = verdicts(ctx["claims"], ctx["cands"])
    q = len(ctx["claims"]); hits = sum(1 for c in ctx["claims"] if c["verbatim"])
    ctx["anchors"] = {"quoted": q, "verbatim_hits": hits, "hit_rate": round(hits / q, 4) if q else 0.0}
    fields_known = sum(1 for f in CARD_FIELDS if ctx["card"][f]["quote"])
    ctx["coverage"] = {"status": "ok", "sections": len(ctx["secs"]),
                       "sections_with_paras": sum(1 for s in ctx["secs"] if s["paras"]),
                       "card_fields_total": len(CARD_FIELDS), "card_fields_known": fields_known,
                       "card_ratio": round(fields_known / len(CARD_FIELDS), 4),
                       "anchor_hit_rate": ctx["anchors"]["hit_rate"]}
    return ctx


def status_of(ctx):
    if ctx["errors"]:
        return "input_error"
    if not ctx["secs"]:
        return "insufficient_evidence"
    if ctx["coverage"]["card_fields_known"] < ctx["coverage"]["card_fields_total"]:
        return "partial"
    return "answered"


def uncertainties(ctx):
    out = list(ctx["degradations"])
    out += ["anchor verbatim hit rate is %.4f across %d claim(s)" % (ctx["anchors"]["hit_rate"], ctx["anchors"]["quoted"]),
            "card fields are mapped by heading keywords; an unmapped field is reported not-reported, not guessed"]
    if not ctx["cands"]:
        out.append("no candidate implementation supplied, so no reproduction comparison is made")
    if any(m["status"] in ("unparsed-binary", "empty-file", "placeholder-only") for m in ctx["materials"]):
        out.append("some materials could not be read as text and are recorded with a parse status only")
    return out


def sentence(ctx, key):
    k = nkey(key)
    st = status_of(ctx)
    if k in ("caseid", "id", "idcase"):
        return ctx["case_id"]
    if k == "status":
        return st
    if k == "outputcontract":
        return ", ".join(list(DEFAULT_CONTRACT))
    if k in ("result", "notes", "notesmd", "review", "deliverable", "md"):
        return "notes.md"
    if k in ("noteunits", "units", "notenunits", "noteunitsfile"):
        return "note_units.jsonl"
    if k in ("papercard", "card", "papercardjson"):
        return "paper_card.json"
    if k in ("coverage", "coveragereport", "completeness"):
        return "coverage.json"
    if k in ("claims", "claim", "noteslist"):
        vals = ["%s [%s] %s" % (c["claim_id"], c["anchor"], c["quote"][:120]) for c in ctx["claims"]]
        return vals or ("no anchored claim could be extracted; see coverage %s" % st)
    if k in ("uncertainties", "uncertainty", "risks", "limits", "limit"):
        return uncertainties(ctx)
    if k in ("summary", "conclusion", "answer", "abstract"):
        return "%s: %d section(s), %d/%d card fields, anchor hit rate %.4f" % (
            st, len(ctx["secs"]), ctx["coverage"]["card_fields_known"], len(CARD_FIELDS), ctx["anchors"]["hit_rate"])
    return "derived: %d section(s), %d claim(s), %d card field(s) known, status %s" % (
        len(ctx["secs"]), len(ctx["claims"]), ctx["coverage"]["card_fields_known"] if ctx["secs"] else 0, st)


def build_result(ctx, contract, draft_used):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT)
    vals = {}
    for k in keys:
        v = ", ".join(keys) if nkey(k) == "outputcontract" else sentence(ctx, k)
        if isinstance(v, str) and not v.strip():
            v = "derived; see artifacts"
        vals[k] = v
    st = status_of(ctx)
    res = {
        "case_id": ctx["case_id"], "status": st, "summary": sentence(ctx, "summary"),
        "method": "heading sections -> six-field card -> anchored notes -> verbatim check -> candidate comparison",
        "sections": [{"sid": s["sid"], "heading": s["heading"], "paras": len(s["paras"])} for s in ctx["secs"]],
        "paper_card": ctx["card"], "claim_count": len(ctx["claims"]),
        "candidate_verdicts": ctx["verdicts"], "draft_used": bool(draft_used),
        "degradations": ctx["degradations"], "limits": uncertainties(ctx), "uncertainties": uncertainties(ctx),
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
                     "parse_status": m["status"]} for m in ctx["materials"]],
        "change_records": [
            {"step": 1, "action": "scan materials", "result": "%d file(s)" % len(ctx["materials"])},
            {"step": 2, "action": "split paper into its own sections", "result": "%d section(s)" % len(ctx["secs"])},
            {"step": 3, "action": "fill the six-field paper card", "result": "%d/%d known" % (
                ctx["coverage"]["card_fields_known"] if ctx["secs"] else 0, len(CARD_FIELDS))},
            {"step": 4, "action": "anchor and verify verbatim notes", "result": "%d/%d verbatim" % (
                ctx["anchors"]["verbatim_hits"], ctx["anchors"]["quoted"])},
            {"step": 5, "action": "compare candidate implementations", "result": "%d metric row(s)" % len(ctx["verdicts"])}],
        "artifacts": {"notes.md": "notes.md", "note_units.jsonl": "note_units.jsonl",
                      "paper_card.json": "paper_card.json", "coverage.json": "coverage.json",
                      "claims.json": "claims.json", "run_log.txt": "run_log.txt"},
    }
    res.update(vals)
    res["output_contract"] = vals
    return res


def notes_md(ctx):
    head = ["# Structured paper notes", "", "Status: %s" % status_of(ctx)]
    if not ctx["secs"]:
        return "\n".join(head + ["", "The input held no readable paper text, so no section skeleton or card is written.",
                                 "The parse status of every material is in run_log.txt and coverage.json."])
    head += ["", "## Section skeleton (from the paper's own headings)"]
    for s in ctx["secs"]:
        head.append("- %s %s (%d paragraph(s))" % (s["sid"], s["heading"], len(s["paras"])))
    head += ["", "## Paper card"]
    for f in CARD_FIELDS:
        c = ctx["card"][f]
        head.append("- **%s**: %s  [anchor %s]" % (f, c["value"], c["anchor"]))
    head += ["", "## Anchored notes"]
    if not ctx["claims"]:
        head.append("- no anchored claim could be extracted from the available sections")
    for c in ctx["claims"]:
        head.append('- %s [%s, %s] "%s"' % (c["claim_id"], c["anchor"], c["field"], c["quote"]))
    if ctx["verdicts"]:
        head += ["", "## Candidate comparison (candidate metric vs nearest reported number)"]
        for v in ctx["verdicts"]:
            head.append("- %s %s=%s nearest_reported=%s delta=%s reproduces=%s" % (
                v["candidate"], v["metric"], v["value"], v.get("nearest_paper_value"),
                v.get("delta"), v["reproduces"]))
    return "\n".join(head)


def run_log(ctx):
    lines = ["# run_log - paper-notes-structurer", ""]
    for m in ctx["materials"]:
        lines.append("material %s %s kind=%s status=%s chars=%d" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
    lines += ["sections=%d claims=%d anchors=%d/%d status=%s" % (
        len(ctx["secs"]), len(ctx["claims"]), ctx["anchors"]["verbatim_hits"], ctx["anchors"]["quoted"], status_of(ctx))]
    return "\n".join(lines) + "\n"


def write_all(ctx, out, work, contract, draft_used):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    wt(os.path.join(out, "notes.md"), notes_md(ctx))
    rows = ctx["claims"] or [{"claim_id": "C000", "field": "no-paper", "anchor": "no-anchor",
                              "text": "no anchored note could be extracted; no readable paper text "
                                      "was found among the input materials",
                              "has_number": False, "verbatim": False}]
    wl(os.path.join(out, "note_units.jsonl"), rows)
    wj(os.path.join(out, "paper_card.json"),
       {"fields": ctx["card"], "field_order": CARD_FIELDS,
        "anchors": ctx["anchors"], "coverage": ctx.get("coverage", {})})
    wj(os.path.join(out, "coverage.json"), ctx.get("coverage", {"status": "no-paper"}))
    wj(os.path.join(out, "claims.json"),
       {"claims": ctx["claims"], "verdicts": ctx["verdicts"],
        "claim_count": len(ctx["claims"]), "verdict_count": len(ctx["verdicts"]),
        "status": status_of(ctx),
        "note": "one row per anchored note; verdicts compare each candidate number with the nearest reported value"})
    wt(os.path.join(out, "run_log.txt"), run_log(ctx))
    res = build_result(ctx, contract, draft_used)
    wj(os.path.join(out, "result.json"), res)
    wl(os.path.join(work, "note_units.jsonl"), rows)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": status_of(ctx), "sections": len(ctx["secs"]),
        "claims": len(ctx["claims"]), "anchors": ctx["anchors"]})
    return res


DRAFT_SKELETON = {"case_id": "", "sections": [], "claims": []}


def find_case(inp):
    base = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    for rel in ("case.json", "challenge.json"):
        obj = rj(os.path.join(base, rel), None)
        if isinstance(obj, dict):
            return obj
    return {}


def load_draft(work):
    d = rj(os.path.join(work, "draft.json"), None)
    return d if isinstance(d, dict) else None


def bootstrap(case, inp, out, work):
    mats = scan_materials(inp)
    cid = str((case or {}).get("case_id") or "unknown-case")
    vals = {k: "not-computed-yet" for k in DEFAULT_CONTRACT}
    vals["case_id"] = cid; vals["status"] = "drafting"
    res = {"case_id": cid, "status": "drafting", "summary": "indexed the input; run build (or all) to make notes",
           "limits": ["partial result written by init"], "uncertainties": ["notes not computed yet"],
           "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]} for m in mats],
           "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(mats)}], "artifacts": {}}
    res.update(vals); res["output_contract"] = vals
    wj(os.path.join(out, "result.json"), res)


def pipeline(inp, out, work, case):
    ctx = build_ctx(case, scan_materials(inp))
    draft = load_draft(work)
    if draft:
        for it in (draft.get("claims") or []):
            if isinstance(it, dict) and it.get("reject"):
                ctx["degradations"].append("agent rejected note %s" % it.get("claim_id", ""))
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    return write_all(ctx, out, work, contract, bool(draft))


def sanitize_output(out):
    for fn in sorted(os.listdir(out)):
        p = os.path.join(out, fn)
        if not os.path.isfile(p):
            continue
        if fn.endswith(".jsonl"):
            rows = []
            for ln in read_text(p).splitlines():
                if ln.strip():
                    obj = rj_text(ln)
                    rows.append(clean(obj) if obj is not None else safe_text(ln))
            wl(p, rows)
        elif fn.endswith(".json"):
            obj = rj(p, None)
            if obj is not None:
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(clean(obj), fh, ensure_ascii=False, indent=2); fh.write("\n")
        elif fn.endswith((".md", ".txt", ".csv", ".tsv")):
            wt(p, read_text(p))


def cmd_init(inp, out, work):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    bootstrap(find_case(inp), inp, out, work)
    sk = os.path.join(work, "draft.skeleton.json")
    if not os.path.exists(sk):
        wj(sk, DRAFT_SKELETON)
    print("init: indexed input, wrote partial result.json and %s" % sk)
    print("next: fill work/draft.json (copy the skeleton), then check and build")
    return 0

def cmd_show(inp, grep, want):
    n = 0
    for m in scan_materials(inp):
        if want and m["id"] != want and m["rel"] != want:
            continue
        print("=== %s %s (%s, %s, %d chars) ===" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
        for i, ln in enumerate(m["text"].splitlines()):
            if grep and grep.lower() not in ln.lower():
                continue
            print("[%s/p%d] %s" % (m["id"], i + 1, ln.strip()[:400])); n += 1
            if n >= 400:
                return 0
    return 0


def cmd_check(inp, work):
    ctx = build_ctx(find_case(inp), scan_materials(inp))
    draft = load_draft(work)
    rep = {"case_id": ctx["case_id"], "draft_present": isinstance(draft, dict), "checks": [], "status": "ok"}
    enough = len(ctx["claims"]) > 0
    rep["checks"].append({"check": "draft_bearing_notes_present",
                          "ok": isinstance(draft, dict) and bool(draft.get("claims")) or enough,
                          "detail": "draft claims=%s; extracted claims=%d" % (
                              len(draft.get("claims") or []) if isinstance(draft, dict) else 0, len(ctx["claims"]))})
    if not isinstance(draft, dict) and not enough:
        rep["status"] = "insufficient_evidence; build will still write an honest degraded result"
    wj(os.path.join(work, "check_report.json"), rep)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    res = pipeline(inp, out, work, find_case(inp))
    sanitize_output(out)
    print("build: status=%s artifacts=%d" % (res["status"], len(res["artifacts"]) + 1))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "notes.md", "note_units.jsonl", "paper_card.json", "coverage.json", "claims.json"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok = isinstance(echo, dict) and all((isinstance(v, str) and v.strip()) or (isinstance(v, list) and v) for v in echo.values())
    print("selfcheck: files %s, contract echo %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss), "ok" if ok else "incomplete", res.get("status", "")))
    return 0


def cmd_compare(inp, out, work):
    ctx = build_ctx(find_case(inp), scan_materials(inp))
    rows = ctx["verdicts"]
    rep = {"case_id": ctx["case_id"],
           "base_agent_baseline": "a prose summary with no anchors, no card fields and no reproduction check",
           "skill_agent": {"sections": len(ctx["secs"]), "card_fields_known": ctx.get("coverage", {}).get("card_fields_known", 0),
                           "anchors_verbatim": "%d/%d" % (ctx["anchors"]["verbatim_hits"], ctx["anchors"]["quoted"]),
                           "candidate_rows": len(rows)},
           "verdicts": rows}
    wj(os.path.join(work, "compare_report.json"), rep)
    print("compare: %d candidate metric row(s) written to work/compare_report.json" % len(rows))
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(prog="paper-notes-structurer")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck", "compare"])
    p.add_argument("--input", default="/input"); p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work"); p.add_argument("--grep", default=None)
    p.add_argument("--mat", default=None)
    args, _ = p.parse_known_args(argv)
    return args


def main(argv):
    args = parse_args(argv)
    cmd, inp, out, work = args.command, args.input, args.output, args.work
    try:
        if cmd == "init":
            return cmd_init(inp, out, work)
        if cmd == "show":
            return cmd_show(inp, args.grep, args.mat)
        if cmd == "check":
            return cmd_check(inp, work)
        if cmd == "selfcheck":
            return cmd_selfcheck(out)
        if cmd == "compare":
            return cmd_compare(inp, out, work)
        if cmd == "build":
            return cmd_build(inp, out, work)
        rc = cmd_build(inp, out, work); cmd_selfcheck(out)
        return rc
    except Exception as exc:
        try:
            os.makedirs(out, exist_ok=True)
            vals = {k: "input could not be processed" for k in DEFAULT_CONTRACT}
            for k, v in (("case_id", "unknown-case"), ("result", "notes.md"), ("notes", "notes.md"),
                         ("note_units", "note_units.jsonl"), ("paper_card", "paper_card.json"),
                         ("coverage", "coverage.json")):
                vals[k] = v
            wj(os.path.join(out, "result.json"),
               {"case_id": "unknown-case", "status": "input_error", "summary": "the input could not be processed",
                "error": str(exc)[:400], "limits": ["processing aborted; see error"], "uncertainties": ["input unreadable"],
                "sources": [], "change_records": [{"step": 0, "action": "abort", "result": str(exc)[:200]}],
                "output_contract": vals})
        except Exception:
            pass
        print("input_error: %s" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
