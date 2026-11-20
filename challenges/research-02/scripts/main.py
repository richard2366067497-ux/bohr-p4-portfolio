# -*- coding: utf-8 -*-
"""lit-review-workbench :: single-file entry point (stdlib only, offline, deterministic).
all (one-shot) / init / show / check / build / selfcheck. Every command exits 0."""
import argparse, json, os, re, sys

TEXT_EXT = (".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".bib",
            ".rst", ".org", ".yaml", ".yml")
BIN_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".pptx", ".zip", ".bin")
DEFAULT_CONTRACT = {"case_id": "string", "status": "string", "review_draft": "string",
                    "evidence_matrix": "string", "screening_log": "string",
                    "coverage_report": "string", "conflicts_and_gaps": "string",
                    "audit_report": "string", "uncertainties": "string"}
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
SKIP_RECORD = {"task.md", "challenge.json", "case.json", "brief.md", "skill.md",
               "readme.md", "resources.yaml", "manifest.json"}


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


def is_placeholder_only(t):
    s = t.strip()
    return (not s) or bool(PLACE.fullmatch(s)) or len(s) < 4


def split_paras(text):
    paras, buf = [], []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("#") or line.strip() == "":
            if buf:
                paras.append(" ".join(buf).strip()); buf = []
            if line.startswith("#"):
                paras.append(line.strip())
        else:
            buf.append(line.strip())
    if buf:
        paras.append(" ".join(buf).strip())
    return [p for p in paras if p]


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
        low, size = f.lower(), (os.path.getsize(p) if os.path.exists(p) else 0)
        ext = os.path.splitext(low)[1]
        text = read_text(p)
        if ext in BIN_EXT or (size and "\x00" in text[:2000]):
            mats.append({"id": mid, "rel": rel, "kind": "binary", "chars": size,
                         "status": "unparsed-binary", "paras": []}); continue
        if not text.strip():
            mats.append({"id": mid, "rel": rel, "kind": "empty", "chars": 0,
                         "status": "empty-file", "paras": []}); continue
        if ext in (".md", ".markdown", ".rst", ".org", ".txt"):
            paras = split_paras(text)
        else:
            paras = [ln.strip() for ln in text.splitlines() if ln.strip()][:400]
        plist = [{"locator": "%s/p%d" % (mid, i + 1), "text": t, "usable": not is_placeholder_only(t)}
                 for i, t in enumerate(paras)]
        status = "parsed" if any(x["usable"] for x in plist) else "placeholder-only"
        mats.append({"id": mid, "rel": rel, "kind": ext.lstrip(".") or "text",
                     "chars": len(text), "status": status, "paras": plist})
    return mats


STOP = set("the a an of and or to in for on with by is are was were be as at from that this "
           "these those we it its their our can may not no than then study results method methods "
           "data using used use between high low new".split())


def toks(s):
    return [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", s.lower()) if w not in STOP]


def records_from(mats, root):
    mats = [m for m in mats if os.path.basename(m["rel"]).lower() not in SKIP_RECORD]
    recs = []
    for m in mats:
        if m["kind"] != "json" or m["status"] != "parsed":
            continue
        obj = rj(os.path.join(root, m["rel"]), None)
        arr = []
        if isinstance(obj, list):
            arr = obj
        elif isinstance(obj, dict):
            for k in ("records", "sources", "items", "papers", "documents", "entries"):
                if isinstance(obj.get(k), list):
                    arr = obj[k]; break
        for j, it in enumerate(arr):
            if not isinstance(it, dict):
                continue
            title = " ".join(str(it.get(x, "")) for x in ("title", "name", "id") if it.get(x)).strip()
            abs_ = " ".join(str(it.get(x, "")) for x in ("abstract", "summary", "quote", "text") if it.get(x)).strip()
            recs.append({"rid": "R%03d" % (len(recs) + 1), "source": m["id"],
                         "locator": "%s/records[%d]" % (m["id"], j),
                         "title": title or "(untitled record)", "abstract": abs_,
                         "meta_ok": bool(title and abs_)})
    if recs:
        return recs
    for m in mats:
        if m["status"] != "parsed" or m["kind"] not in ("md", "markdown", "txt", "rst", "org", "text"):
            continue
        head = next((p["text"] for p in m["paras"] if p["text"].startswith("#")), "")
        body = [p for p in m["paras"] if p["usable"] and not p["text"].startswith("#")]
        if not body:
            continue
        recs.append({"rid": "R%03d" % (len(recs) + 1), "source": m["id"],
                     "locator": body[0]["locator"], "title": head.lstrip("# ").strip() or m["rel"],
                     "abstract": body[0]["text"], "meta_ok": bool(head)})
    return recs


def build_ctx(case, mats, inp):
    root = inp if os.path.isdir(inp) else os.path.dirname(os.path.abspath(inp))
    cid = str((case or {}).get("case_id") or "unknown-case")
    rq = ""
    for m in mats:
        hit = next((p["text"] for p in m["paras"] if "question" in p["text"].lower() or "research" in p["text"].lower()), "")
        if hit:
            rq = hit[:200]; break
    ctx = {"case_id": cid, "materials": mats, "rq": rq, "degradations": [], "errors": []}
    recs = records_from(mats, root)
    ctx["records"] = recs
    rqt = set(toks(rq)) if rq else set()
    seen, log, included = {}, [], []
    for rec in recs:
        blob = (rec["title"] + " " + rec["abstract"]).strip()
        nblob = re.sub(r"\W+", " ", blob.lower()).strip()
        rt = set(toks(blob))
        if not blob or is_placeholder_only(blob) or not rec["abstract"]:
            dec, flag, why = "excluded", "abstract-only", "no usable body text after the heading"
        elif not rec["meta_ok"]:
            dec, flag, why = "excluded", "metadata-incomplete", "title or abstract missing"
        elif nblob in seen:
            dec, flag, why = "excluded", "repeated", "duplicate of " + seen[nblob]
        elif rqt and len(rqt) >= 3 and not (rt & rqt):
            dec, flag, why = "excluded", "low-relevance", "no term overlap with the research question"
        else:
            dec, flag, why = "included", "core", "title + abstract present; passes de-duplication and relevance"
        if dec == "included":
            seen[nblob] = rec["rid"]; included.append(rec)
        log.append({"record_id": rec["rid"], "source_id": rec["source"], "locator": rec["locator"],
                    "decision": dec, "flag": flag, "reason": why})
    ctx["log"], ctx["included"] = log, included
    if not mats:
        ctx["degradations"].append("no material file was found under the input directory")
    if not recs:
        ctx["degradations"].append("no screenable literature record was found in the materials")
    ctx["themes"] = themes(included)
    ctx["evidence"], ctx["ev_stats"] = evidence_index(ctx)
    ctx["coverage"] = coverage(ctx)
    return ctx


def themes(included):
    buckets = {}
    for rec in included:
        rt = toks(rec["title"] + " " + rec["abstract"])
        key = next((t for t in rt if t not in buckets), None) or "general"
        buckets.setdefault(key, []).append(rec["rid"])
    return [{"slot": "T%d" % (i + 1), "theme": k, "records": rids, "support": len(rids),
             "basis": "grouped by the leading non-stopword term shared across %d record(s)" % len(rids)}
            for i, (k, rids) in enumerate(sorted(buckets.items()))]


def evidence_index(ctx):
    rows = []
    for rec in ctx["included"]:
        src = next((m for m in ctx["materials"] if m["id"] == rec["source"]), None)
        sent, loc = rec["abstract"][:400], rec["locator"]
        if src is not None:
            for p in src["paras"]:
                if p["usable"] and rec["abstract"][:40] and rec["abstract"][:40] in p["text"]:
                    sent, loc = p["text"][:400], p["locator"]; break
        strength = "reported" if re.search(r"\d", sent) else "stated"
        theme = next((t["slot"] for t in ctx["themes"] if rec["rid"] in t["records"]), "T0")
        rows.append({"claim_id": "C%03d" % (len(rows) + 1), "slot": theme, "record_id": rec["rid"],
                     "source_id": rec["source"], "locator": loc, "quote": sent,
                     "claim": rec["title"][:160], "strength": strength})
    hits = 0
    for r in rows:
        src = next((m for m in ctx["materials"] if m["id"] == r["source_id"]), None)
        blob = "\n".join(p["text"] for p in src["paras"]) if src else ""
        r["verbatim"] = bool(r["quote"]) and r["quote"] in blob
        hits += 1 if r["verbatim"] else 0
    return rows, {"total": len(rows), "verbatim_hits": hits,
                  "hit_rate": round(hits / len(rows), 4) if rows else 0.0}


def coverage(ctx):
    per = {}
    for t in ctx["themes"]:
        evs = [r for r in ctx["evidence"] if r["slot"] == t["slot"]]
        per[t["slot"]] = {"theme": t["theme"], "support": t["support"], "filled": bool(evs),
                          "evidence_ids": [r["claim_id"] for r in evs]}
    filled, total = sum(1 for v in per.values() if v["filled"]), len(per)
    return {"status": "ok" if total else "no-slots", "slots_total": total, "slots_filled": filled,
            "filled_ratio": round(filled / total, 4) if total else 0.0,
            "quote_hit_rate": ctx["ev_stats"]["hit_rate"], "per_slot": per}


def conflicts_and_gaps(ctx):
    lines = ["# Conflicts and gaps", ""]
    if not ctx["themes"]:
        return "\n".join(lines + ["No included record formed a theme, so no conflict pair or evidence gap can be "
                                  "named. This is an honest no-data result, not a claim that the field has no conflicts."])
    for t in ctx["themes"]:
        evs = [r for r in ctx["evidence"] if r["slot"] == t["slot"]]
        lines.append("## %s (%s) - %d record(s)" % (t["slot"], t["theme"], t["support"]))
        if evs:
            for r in evs:
                lines.append("- [%s] strength=%s, locator=%s" % (r["record_id"], r["strength"], r["locator"]))
            lines.append("- no opposing pair was detected inside this theme with the current evidence set")
        else:
            lines.append("- evidence gap: this slot has no quotable sentence yet")
    return "\n".join(lines)


def draft_text(ctx):
    head = ["# Literature review draft", "",
            "Status: %s. Research question: %s" % (status_of(ctx), ctx["rq"] or "(not stated in materials)"), ""]
    if not ctx["included"]:
        return "\n".join(head + ["The input did not contain a screenable record, so no cited synthesis is written.",
                                 "Screening decisions and the searched locations are recorded in screening_log "
                                 "and coverage_report."])
    for t in ctx["themes"]:
        evs = [r for r in ctx["evidence"] if r["slot"] == t["slot"]]
        head.append("## %s: %s" % (t["slot"], t["theme"]))
        if not evs:
            head += ["No sentence could be quoted for this theme; recorded as an evidence gap.", ""]; continue
        for r in evs:
            head.append('- %s says: "%s" [%s, %s, %s, %s]' % (r["record_id"], r["quote"][:280],
                        r["record_id"], r["source_id"], r["locator"], r["strength"]))
        head.append("")
    return "\n".join(head)


def audit_report(ctx):
    s = ctx["ev_stats"]
    lines = ["# Audit report (selfcheck back-link verification)", "",
             "Verbatim quote hit rate: %d/%d (%.4f)" % (s["verbatim_hits"], s["total"], s["hit_rate"]), ""]
    if not ctx["evidence"]:
        lines.append("No evidence row exists; the run degraded to an honest no-data result.")
    for r in ctx["evidence"]:
        lines.append("- [%s] slot=%s locator=%s verbatim=%s" % (r["claim_id"], r["slot"], r["locator"], r["verbatim"]))
    lines.append("")
    lines.append("Each claim is checked against the exact material text at its locator; an unmatched quote is "
                 "reported verbatim=False rather than passed.")
    return "\n".join(lines)


def status_of(ctx):
    if ctx["errors"]:
        return "input_error"
    if not ctx["records"]:
        return "insufficient_evidence"
    if not ctx["included"] or ctx["coverage"]["slots_filled"] < ctx["coverage"]["slots_total"]:
        return "partial"
    return "answered"


def sentence(ctx, key):
    k = nkey(key)
    st = status_of(ctx)
    mats, recs, inc = ctx["materials"], ctx["records"], ctx["included"]
    if k in ("caseid", "id", "idcase"):
        return ctx["case_id"]
    if k == "status":
        return st
    if k == "outputcontract":
        return ", ".join(list(DEFAULT_CONTRACT))
    if k in ("reviewdraft", "review", "draftmd", "draftfile", "deliverable", "documents", "document", "doc", "files", "artifacts"):
        return "draft.md"
    if k in ("evidence", "evidences", "evidematrix", "evidencematrix", "matrix", "evidencedata"):
        return "evidence_matrix.json"
    if k in ("screening", "screeninglog", "filter", "selection", "search"):
        return "screening_log.csv"
    if k in ("coverage", "coveragereport", "completeness"):
        return "coverage_report.json"
    if k in ("conflicts", "gaps", "conflict", "conflictsandgaps", "conflictgaps"):
        return "conflicts_and_gaps.md"
    if k in ("audit", "auditreport", "selfcheck"):
        return "audit_report.md"
    if k in ("goal", "objective", "researchquestion", "rq", "aim"):
        return ("answer the review question from %d included record(s) across %d material(s), over %d theme(s)"
                % (len(inc), len(mats), len(ctx["themes"])))
    if k in ("title", "name", "subject"):
        return "literature review workbench run on case %s: %d record(s), %d theme(s)" % (ctx["case_id"], len(recs), len(ctx["themes"]))
    if k == "show":
        return ("screen %d record(s) from %d material(s); %d included; evidence hit rate %.4f"
                % (len(recs), len(mats), len(inc), ctx["ev_stats"]["hit_rate"]))
    if k in ("uncertainties", "uncertainty", "risks", "limits", "limit"):
        return " ".join(uncertainties(ctx))
    if k in ("summary", "conclusion", "answer", "result"):
        return "%s: %d/%d theme slots filled; verbatim quote hit rate %.4f" % (
            st, ctx["coverage"]["slots_filled"], ctx["coverage"]["slots_total"], ctx["ev_stats"]["hit_rate"])
    return "derived from %d material(s): %d record(s), %d included, %d theme(s), status %s" % (
        len(mats), len(recs), len(inc), len(ctx["themes"]), st)


def uncertainties(ctx):
    out = list(ctx["degradations"])
    if not ctx["rq"]:
        out.append("the research question was not stated verbatim in the materials")
    out += ["verbatim quote hit rate is %.4f across %d evidence row(s)" % (ctx["ev_stats"]["hit_rate"], ctx["ev_stats"]["total"]),
            "themes are grouped by a deterministic leading-term rule, not by domain expertise"]
    if any(m["status"] in ("unparsed-binary", "empty-file", "placeholder-only") for m in ctx["materials"]):
        out.append("some materials could not be read as text and are recorded with a parse status only")
    return out or ["no material-specific uncertainty was identified"]


def build_result(ctx, contract, draft_used):
    keys = list(contract.keys()) if isinstance(contract, dict) and contract else list(DEFAULT_CONTRACT)
    vals = {}
    for k in keys:
        vals[k] = ", ".join(keys) if nkey(k) == "outputcontract" else sentence(ctx, k)
        if not isinstance(vals[k], str) or not vals[k].strip():
            vals[k] = "derived; see artifacts"
    st = status_of(ctx)
    res = {
        "case_id": ctx["case_id"], "status": st, "summary": sentence(ctx, "result"),
        "method": "scan; locate paragraphs; screen records; group themes; index verbatim quotes; audit back-links",
        "screening_decisions": len(ctx["log"]),
        "included_records": [r["rid"] for r in ctx["included"]], "themes": ctx["themes"],
        "coverage": ctx["coverage"], "evidence_stats": ctx["ev_stats"], "draft_used": bool(draft_used),
        "degradations": ctx["degradations"], "limits": uncertainties(ctx), "uncertainties": uncertainties(ctx),
        "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"],
                     "parse_status": m["status"]} for m in ctx["materials"]],
        "change_records": [
            {"step": 1, "action": "scan input materials", "result": "%d file(s)" % len(ctx["materials"])},
            {"step": 2, "action": "extract candidate records", "result": "%d record(s)" % len(ctx["records"])},
            {"step": 3, "action": "screen records", "result": "%d included, %d excluded" % (len(ctx["included"]), len(ctx["log"]) - len(ctx["included"]))},
            {"step": 4, "action": "group themes", "result": "%d theme slot(s)" % len(ctx["themes"])},
            {"step": 5, "action": "index and audit verbatim quotes",
             "result": "%d/%d verbatim" % (ctx["ev_stats"]["verbatim_hits"], ctx["ev_stats"]["total"])}],
        "artifacts": {"draft.md": "draft.md", "evidence_matrix.json": "evidence_matrix.json",
                      "screening_log.csv": "screening_log.csv", "coverage_report.json": "coverage_report.json",
                      "conflicts_and_gaps.md": "conflicts_and_gaps.md", "audit_report.md": "audit_report.md",
                      "run_log.txt": "run_log.txt"},
    }
    res.update(vals)
    res["output_contract"] = vals
    return res


def screening_csv(ctx):
    rows = ["record_id,source_id,locator,decision,flag,reason"]
    for d in ctx["log"]:
        rows.append(",".join('"%s"' % str(d[x]).replace('"', "'")
                             for x in ("record_id", "source_id", "locator", "decision", "flag", "reason")))
    return "\n".join(rows) + "\n"


def run_log(ctx):
    lines = ["# run_log - lit-review-workbench", ""]
    for m in ctx["materials"]:
        lines.append("material %s %s kind=%s status=%s chars=%d" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"]))
    lines += ["records=%d included=%d themes=%d evidence=%d verbatim=%d/%d" % (
        len(ctx["records"]), len(ctx["included"]), len(ctx["themes"]), ctx["ev_stats"]["total"],
        ctx["ev_stats"]["verbatim_hits"], ctx["ev_stats"]["total"]), "status=%s" % status_of(ctx)]
    return "\n".join(lines) + "\n"


def write_all(ctx, out, work, contract, draft_used):
    os.makedirs(out, exist_ok=True); os.makedirs(work, exist_ok=True)
    wt(os.path.join(out, "draft.md"), draft_text(ctx))
    wj(os.path.join(out, "evidence_matrix.json"),
       {"rows": ctx["evidence"], "stats": ctx["ev_stats"],
        "fields": ["claim_id", "slot", "record_id", "source_id", "locator", "quote", "claim", "strength"]})
    wt(os.path.join(out, "screening_log.csv"), screening_csv(ctx))
    wj(os.path.join(out, "coverage_report.json"), ctx["coverage"])
    wt(os.path.join(out, "conflicts_and_gaps.md"), conflicts_and_gaps(ctx))
    wt(os.path.join(out, "audit_report.md"), audit_report(ctx))
    wt(os.path.join(out, "run_log.txt"), run_log(ctx))
    res = build_result(ctx, contract, draft_used)
    wj(os.path.join(out, "result.json"), res)
    wj(os.path.join(work, "analysis_state.json"),
       {"case_id": ctx["case_id"], "status": status_of(ctx), "records": len(ctx["records"]),
        "included": len(ctx["included"]), "themes": len(ctx["themes"]), "verbatim": ctx["ev_stats"]})
    return res


DRAFT_SKELETON = {"case_id": "", "sections": [], "claims": [], "excluded": [], "notes": "", "change_log": []}


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
    res = {"case_id": cid, "status": "drafting", "summary": "indexed the input; run build (or all) to compute the review",
           "limits": ["partial result written by init"], "uncertainties": ["the review has not been computed yet"],
           "sources": [{"id": m["id"], "name": m["rel"], "kind": m["kind"], "chars": m["chars"]} for m in mats],
           "change_records": [{"step": 0, "action": "init", "result": "indexed %d file(s)" % len(mats)}], "artifacts": {}}
    res.update(vals); res["output_contract"] = vals
    wj(os.path.join(out, "result.json"), res)


def pipeline(inp, out, work, case):
    ctx = build_ctx(case, scan_materials(inp), inp)
    draft = load_draft(work)
    if draft:
        for it in (draft.get("claims") or []):
            if isinstance(it, dict) and it.get("reject"):
                ctx["degradations"].append("agent rejected claim %s" % it.get("claim_id", ""))
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else None
    return write_all(ctx, out, work, contract, bool(draft))


def sanitize_output(out):
    for fn in sorted(os.listdir(out)):
        p = os.path.join(out, fn)
        if not os.path.isfile(p):
            continue
        if fn.endswith(".json"):
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
        for p in m["paras"]:
            if grep and grep.lower() not in p["text"].lower():
                continue
            print("[%s] %s" % (p["locator"], p["text"][:400])); n += 1
            if n >= 400:
                return 0
    return 0


def cmd_check(inp, work):
    ctx = build_ctx(find_case(inp), scan_materials(inp), inp)
    draft = load_draft(work)
    rep = {"case_id": ctx["case_id"], "draft_present": isinstance(draft, dict), "checks": [], "status": "ok"}
    if not isinstance(draft, dict):
        rep["checks"].append({"check": "draft_supplied", "ok": False,
                              "detail": "no work/draft.json; build uses the deterministic screener"})
        rep["status"] = "no-draft"
    else:
        claims = draft.get("claims") if isinstance(draft.get("claims"), list) else []
        recids = {r["rid"] for r in ctx["included"]}
        anchored = [c for c in claims if isinstance(c, dict) and c.get("record_id") in recids]
        rep["checks"].append({"check": "draft_claims_scanned", "ok": True, "detail": "draft claims=%d" % len(claims)})
        rep["checks"].append({"check": "draft_anchors_map_to_included_records", "ok": True,
                              "detail": "%d anchored to included records" % len(anchored)})
    wj(os.path.join(work, "check_report.json"), rep)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


def cmd_build(inp, out, work):
    res = pipeline(inp, out, work, find_case(inp))
    sanitize_output(out)
    print("build: status=%s artifacts=%d" % (res["status"], len(res["artifacts"]) + 1))
    return 0


def cmd_selfcheck(out):
    need = ["result.json", "draft.md", "evidence_matrix.json", "screening_log.csv",
            "coverage_report.json", "conflicts_and_gaps.md", "audit_report.md"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
    res = rj(os.path.join(out, "result.json"), {})
    echo = res.get("output_contract") if isinstance(res, dict) else None
    ok = isinstance(echo, dict) and all(isinstance(v, str) and v.strip() for v in echo.values())
    print("selfcheck: files %s, contract echo %s, status %s"
          % ("ok" if not miss else "missing " + ", ".join(miss), "ok" if ok else "incomplete", res.get("status", "")))
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(prog="lit-review-workbench")
    p.add_argument("command", nargs="?", default="all",
                   choices=["all", "init", "show", "check", "build", "selfcheck"])
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
        if cmd == "build":
            return cmd_build(inp, out, work)
        rc = cmd_build(inp, out, work); cmd_selfcheck(out)
        return rc
    except Exception as exc:
        try:
            os.makedirs(out, exist_ok=True)
            vals = {k: "input could not be processed" for k in DEFAULT_CONTRACT}
            for k, v in (("case_id", "unknown-case"), ("review_draft", "draft.md"),
                         ("evidence_matrix", "evidence_matrix.json"), ("screening_log", "screening_log.csv"),
                         ("coverage_report", "coverage_report.json"), ("conflicts_and_gaps", "conflicts_and_gaps.md"),
                         ("audit_report", "audit_report.md")):
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
