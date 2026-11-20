"""Structural review pass for writing-06: six detectors, edit actions and artifacts.

Every finding must carry a verbatim quote from the reviewed manuscript (checked against
the normalised source text); candidates that cannot be grounded are dropped. Findings and
actions are then rendered into the artifact set and result.json.
"""
from core import *  # noqa: F401,F403 - shared helpers, constants and the text model

# ------------------------------------------------------------------ detectors
RQ = re.compile(r"(?i)\b(we (?:ask|examine|investigate|hypothes\w*)|this (?:study|paper) "
                r"(?:examines|asks|investigates)|aim of this|research question)\b|本研究|本文|旨在|研究问题")
CLAIM = re.compile(r"(?i)\b(suggest\w*|indicat\w*|therefore|thus|demonstrat\w*|show\w*|conclud\w*)\b|表明|显示|因此|说明|提示")
CITE = re.compile(r"\[\d+(?:\s*[,\-–]\s*\d+)*\]|\([A-Z][A-Za-z\-]+(?: et al\.?)?,? \d{4}\)")
NUM = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|‰|°C|mg|kg|µg|ug|mL|L|mm|cm|km|h|min|s|nM|mM|µM|uM|K|kJ|kcal|d|wk|yr)")
FIG = re.compile(r"(?i)\b(?:fig(?:ure)?\.?|table)\s*\d+")
REFENT = re.compile(r"(?m)^\s*\[?(\d{1,3})[\]\.\)]\s+\S")
CONN = re.compile(r"(?i)^(however|moreover|therefore|thus|in contrast|similarly|furthermore|first|second|finally|"
                  r"we next|to test|in addition)\b|然而|因此|此外|与此相反|首先|其次")
CAUSAL = re.compile(r"(?i)\b(caus\w*|leads? to|results? in|drives?)\b|导致|造成|使得")
HEDGE = re.compile(r"(?i)\b(may|might|could|suggest\w*|consistent with|associated with|possibly)\b|可能|提示|相关")
ABS = re.compile(r"(?i)\b(always|never|prove[sd]?|proven|guarantee[sd]?|universally)\b|所有|全部|一律|一致")


def add(st, dim, sev, loc, quote, diag, basis, conf, op=None, to=""):
    q = nz(quote)
    if len(q) < 12 or q not in nz(st["doc"]["text"]) or TOK.search(q) or len(st["findings"]) >= 36:
        return None
    f = {"finding_id": "F%02d" % (len(st["findings"]) + 1), "dimension": dim, "severity": sev,
         "locator": loc, "quote": q, "diagnosis": diag, "evidence_for_judgment": basis,
         "confidence": conf, "operation": op or OPS[dim], "to_locator": to or loc}
    st["findings"].append(f)
    return f


def fpara(doc):
    for ch in doc["chapters"]:
        for p in ch["paragraphs"]:
            return p
    return None


def lpara(doc):
    for ch in reversed(doc["chapters"]):
        if ch["role"] == "references":
            continue
        for p in reversed(ch["paragraphs"]):
            return p
    return fpara(doc)


def det_structure(st):
    doc = st["doc"]
    headed = [c for c in doc["chapters"] if c["heading"]]
    if len(headed) <= 1:
        p = fpara(doc)
        if p:
            add(st, "section_structure", "high", p["locator"], p["text"],
                "The manuscript exposes no heading-based section structure.",
                "headings=%d" % len(headed), "high", "insert")
    present = {c["role"] for c in doc["chapters"]}
    tail = next((c["id"] for c in reversed(doc["chapters"]) if c["role"] != "references"), "")
    a = lpara(doc)
    for need in ("introduction", "method", "result"):
        if need not in present and a:
            add(st, "section_structure", "high", a["locator"], a["text"],
                "No %s section anchors this part of the argument." % need,
                "roles=%s" % ",".join(sorted(present)), "high", "insert", tail)
    if "conclusion" not in present and "discussion" not in present and a:
        add(st, "section_structure", "high", a["locator"], a["text"],
            "Neither a discussion nor a conclusion closes the argument.",
            "roles=%s" % ",".join(sorted(present)), "high", "insert", tail)
    seq = [(c["id"], c["role"]) for c in doc["chapters"]
           if c["role"] in ("introduction", "method", "result", "discussion", "conclusion")]
    order = [r for _, r in seq]
    for x, y in (("method", "result"), ("result", "discussion")):
        if x in order and y in order and order.index(x) > order.index(y):
            target = next((cid for cid, r in seq if r == x), "")
            ch = next((c for c in doc["chapters"] if c["role"] == y), None)
            if ch and ch["paragraphs"]:
                p = ch["paragraphs"][0]
                add(st, "section_structure", "high", p["locator"], p["text"],
                    "%s is placed before %s." % (y, x), "order=%s" % " > ".join(order), "high", "move", target)
            break


def det_rq(st):
    doc = st["doc"]
    bodies = [c for c in doc["chapters"] if c["role"] in ("body", "introduction")] or doc["chapters"]
    found = None
    for ch in bodies:
        for p in ch["paragraphs"][:8]:
            for s in p["sentences"]:
                if RQ.search(s["text"]) and wc(s["text"]) >= 8:
                    found = s
                    break
            if found:
                break
        if found:
            break
    if not found:
        p = fpara(doc)
        if p and doc["words"] >= 300:
            add(st, "research_question_alignment", "high", p["locator"], p["text"],
                "No sentence states the research question or the study aim.",
                "words=%d, question markers=0" % doc["words"], "medium", "insert")
        return
    tail = " ".join(p["text"] for c in doc["chapters"] if c["role"] in ("result", "discussion", "conclusion")
                    for p in c["paragraphs"])
    tt = set(toks(tail or doc["text"]))
    key = [t for t in toks(found["text"]) if len(t) > 4][:10]
    miss = [t for t in key if t not in tt]
    if key and len(miss) >= max(3, len(key) // 2):
        add(st, "research_question_alignment", "high", found["locator"], found["text"],
            "Key terms of the research question do not reappear after the results.",
            "key terms=%d, missing=%d (%s)" % (len(key), len(miss), ", ".join(miss[:6])), "medium", "narrow")


def evkind(t):
    return "citation" if CITE.search(t) else "number" if NUM.search(t) else "figure" if FIG.search(t) else ""


def det_arg(st):
    doc = st["doc"]
    cited = set()
    for ch in doc["chapters"]:
        if ch["role"] == "references":
            continue
        for p in ch["paragraphs"]:
            claims = [s for s in p["sentences"] if CLAIM.search(s["text"])]
            if claims and not any(evkind(s["text"]) for s in p["sentences"]) and wc(p["text"]) >= 30:
                add(st, "argument_chain", "medium" if ch["role"] == "body" else "high", claims[0]["locator"],
                    claims[0]["text"], "A claim-bearing paragraph carries no citation, value or figure reference.",
                    "sentences=%d, claims=%d, evidence markers=0" % (len(p["sentences"]), len(claims)),
                    "medium", "insert")
            for s in p["sentences"]:
                for m in re.finditer(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]", s["text"]):
                    cited.update(int(x) for x in re.findall(r"\d+", m.group(1)))
    refs = {int(x) for x in REFENT.findall(doc["text"])}
    if refs:
        for n in sorted(cited - refs)[:3]:
            hit = next((s for ch in doc["chapters"] for p in ch["paragraphs"] for s in p["sentences"]
                        if "[%d]" % n in s["text"]), None)
            if hit:
                add(st, "argument_chain", "high", hit["locator"], hit["text"],
                    "A citation number in the text has no entry in the reference list.",
                    "in-text citations=%d, reference entries=%d" % (len(cited), len(refs)), "high", "insert")
    st["cited"], st["refs"] = sorted(cited), sorted(refs)


def det_par(st):
    doc = st["doc"]
    flat = [p for ch in doc["chapters"] if ch["role"] != "references" for p in ch["paragraphs"]]
    n = 0
    for a, b in zip(flat, flat[1:]):
        if n >= 2:
            break
        if a["chapter"] != b["chapter"] or wc(a["text"]) < 55 or wc(b["text"]) < 55 or CONN.match(b["text"]):
            continue
        v = jac(set(toks(a["text"])), set(toks(b["text"])))
        if v < 0.05:
            n += 1
            s = b["sentences"][0]
            add(st, "paragraph_relations", "low", s["locator"], s["text"],
                "Adjacent paragraphs share no terms and the second opens without a transition.",
                "term overlap=%.3f between %s and %s" % (v, a["locator"], b["locator"]), "low-medium", "insert")
    n = 0
    for p in flat:
        if n >= 2:
            break
        nums = sum(1 for s in p["sentences"] if NUM.search(s["text"]))
        cl = sum(1 for s in p["sentences"] if CLAIM.search(s["text"]))
        if wc(p["text"]) >= 120 and nums >= 2 and cl >= 1:
            n += 1
            add(st, "paragraph_relations", "medium", p["locator"], p["text"],
                "One paragraph mixes measured values with interpretation.",
                "words=%d, value sentences=%d, claim sentences=%d" % (wc(p["text"]), nums, cl),
                "medium", "split", p["sentences"][0]["locator"])


def det_dup(st):
    doc = st["doc"]
    flat = [p for ch in doc["chapters"] if ch["role"] != "references"
            for p in ch["paragraphs"] if wc(p["text"]) >= 45]
    sh = {}
    for p in flat:
        t = toks(p["text"])
        sh[p["locator"]] = {tuple(t[i:i + 8]) for i in range(max(0, len(t) - 7))}
    pairs = [(jac(sh[a["locator"]], sh[b["locator"]]), a, b) for i, a in enumerate(flat)
             for b in flat[i + 1:] if sh[a["locator"]] and sh[b["locator"]]]
    pairs = sorted([p for p in pairs if p[0] >= 0.30], key=lambda x: -x[0])
    for v, a, b in pairs[:4]:
        add(st, "duplication", "high" if v >= 0.5 else "medium", b["locator"], b["text"],
            "Two paragraphs restate the same content in overlapping wording.",
            "8-token shingle overlap=%.3f between %s and %s" % (v, a["locator"], b["locator"]),
            "high" if v >= 0.5 else "medium", "merge", a["locator"])
    seen = {}
    for ch in doc["chapters"]:
        for p in ch["paragraphs"]:
            for s in p["sentences"]:
                k = re.sub(r"\W+", "", s["text"].lower())
                if len(k) >= 55:
                    seen.setdefault(k, []).append(s)
    dups = [h for h in seen.values() if len(h) >= 2]
    for h in dups[:3]:
        add(st, "duplication", "medium", h[-1]["locator"], h[-1]["text"],
            "The same sentence appears verbatim more than once.",
            "identical normalised sentence, occurrences=%d" % len(h), "high", "delete", h[0]["locator"])
    st["dups"] = len(dups)


def det_con(st):
    doc = st["doc"]
    body = " ".join(p["text"] for c in doc["chapters"] if c["role"] in ("method", "result")
                    for p in c["paragraphs"])
    corr = bool(re.search(r"(?i)(associated|correlat\w*|observational)|相关|关联", body))
    ctrl = bool(re.search(r"(?i)(randomi[sz]\w*|controlled|intervention)|随机|对照|干预", body))
    nums = set(re.findall(r"\d+(?:\.\d+)?", body))
    n = 0
    for ch in [c for c in doc["chapters"] if c["role"] in ("conclusion", "discussion")]:
        for p in ch["paragraphs"]:
            for s in p["sentences"]:
                if n >= 6:
                    return
                t = s["text"]
                if CAUSAL.search(t) and not HEDGE.search(t) and corr and not ctrl:
                    n += 1
                    add(st, "conclusion_boundary", "high", s["locator"], t,
                        "A causal verb is used although the study reports association only.",
                        "correlational wording=%s, controlled design=%s" % (corr, ctrl), "high", "narrow")
                elif ABS.search(t) and not HEDGE.search(t) and wc(t) >= 8:
                    n += 1
                    add(st, "conclusion_boundary", "medium", s["locator"], t,
                        "The sentence uses absolute wording without a limiting clause.",
                        "absolute markers=%s, hedges=0" % ",".join(sorted(set(ABS.findall(t)))[:3]),
                        "medium", "narrow")
                elif NUM.search(t):
                    vals = [m.group(0) for m in NUM.finditer(t)
                            if re.match(r"\d+(?:\.\d+)?", m.group(0)).group(0) not in nums]
                    if vals and n < 4:
                        n += 1
                        add(st, "conclusion_boundary", "low", s["locator"], t,
                            "A measured value appears only in the closing sections.",
                            "value absent from method and results: %s" % ", ".join(vals[:2]),
                            "low-medium", "narrow")


def coverage(st):
    doc = st["doc"]
    paras = sum(len(c["paragraphs"]) for c in doc["chapters"])
    out = {}
    for d in DIMS:
        ids = [f["finding_id"] for f in st["findings"] if f["dimension"] == d]
        out[d] = {"status": "findings" if ids else "no_issue_with_evidence", "finding_ids": ids,
                  "checked": ("%d chapters and %d paragraphs scanned" % (len(doc["chapters"]), paras))
                  if ids else ("checked %d chapters and %d paragraphs; no rule fired"
                               % (len(doc["chapters"]), paras))}
    return out


def actions(st):
    out = []
    for f in st["findings"]:
        op = f["operation"]
        out.append({"action_id": "A%02d" % (len(out) + 1), "finding_id": f["finding_id"], "operation": op,
                    "from_locator": f["locator"], "to_locator": f["to_locator"],
                    "priority": PRIO.get(f["severity"], "P3"),
                    "expected_effect": {"move": "restore the order the argument depends on",
                                        "merge": "keep one authoritative statement",
                                        "split": "separate observation from interpretation",
                                        "narrow": "make the claim match the evidence strength",
                                        "delete": "remove the duplicate copy",
                                        "insert": "add the missing element or support"}.get(op, "clarify the section"),
                    "risk": {"move": "cross-references to the old position need an update",
                             "merge": "wording unique to either copy may be lost",
                             "split": "the new boundary may need a transition",
                             "narrow": "over-tightening can weaken a supported finding",
                             "delete": "confirm the retained copy keeps the full meaning",
                             "insert": "inserted text must stay inside the supplied material"}.get(op, "review before applying"),
                    "executable": True})
    return out


# -------------------------------------------------------------------- pipeline
def run(input_dir, out_dir, work_dir):
    t0 = time.time()
    out, work = Path(out_dir), Path(work_dir)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case, errs = read_case(input_dir)
    cid = str(case.get("case_id") or "") if isinstance(case, dict) else ""
    files, uniq = discover(input_dir)
    draft = read_draft(work)
    pending = []
    srcs = [{"path": f["rel"], "role": f["role"], "bytes": f["bytes"], "sha256": f["sha256"],
             "empty": f["empty"], "duplicates": f["duplicates"]} for f in files]
    au = packet(uniq)
    mf = pick_man(uniq)
    man = build_doc(mf) if mf else None
    mode = "manuscript" if man else "packet"
    if not files:
        pending.append({"item": "input", "issue": "the input root holds no files",
                        "action": "provide case.json and the manuscript packet"})
    if not man:
        pending.append({"item": "manuscript", "issue": "no manuscript was identified in the input packet",
                        "action": "supply the manuscript to review, or confirm a packet-level review is intended"})
    if not uniq:
        pending.append({"item": "content", "issue": "no readable text was found in the packet",
                        "action": "supply readable UTF-8 text material"})
    for f in files:
        if f["empty"]:
            pending.append({"item": f["rel"], "issue": "the file is empty",
                            "action": "replace it with the intended content"})
        elif f["text"] is not None and not f["text"].strip():
            pending.append({"item": f["rel"], "issue": "the file carries whitespace only",
                            "action": "replace it with the intended content"})
    st = {"doc": man or {"text": "", "chapters": [], "words": 0, "rel": ""}, "findings": []}
    if man:
        for fn in (det_structure, det_rq, det_arg, det_par, det_dup, det_con):
            try:
                fn(st)
            except Exception as exc:
                errs.append({"stage": "detector", "detail": str(exc)})
        acts = actions(st)
        cov = coverage(st)
        outline = [{"locator": c["id"], "heading": c["heading"] or "(untitled opening)",
                    "role": c["role"], "paragraphs": len(c["paragraphs"])} for c in man["chapters"]]
        am = argmap(st, CLAIM, evkind)
        stats = {"chapters": len(man["chapters"]), "words": man["words"],
                 "paragraphs": sum(len(c["paragraphs"]) for c in man["chapters"]),
                 "findings": len(st["findings"]), "actions": len(acts), "duplicate_sentences": st.get("dups", 0),
                 "in_text_citations": len(st.get("cited", [])), "reference_entries": len(st.get("refs", []))}
    else:
        st["outline"] = [{"locator": h["document"], "heading": h["heading"], "role": "packet"} for h in au["headings"]]
        st["cited"], st["refs"] = [], []
        acts, cov = [], packet_cov(au, len(uniq))
        outline = st["outline"]
        am = {"research_question": {"quote": "", "locator": ""}, "chains": [], "unsupported_chains": 0,
              "method": "no manuscript, so no claim-evidence chain could be extracted"}
        stats = {"documents": len(uniq), "headings": au["heading_count"],
                 "duplicate_sentences": len(au["duplicates"]), "recurring_terms": len(au["recurring_terms"]),
                 "findings": 0, "actions": 0}
    st["coverage"] = cov
    ok = sum(1 for f in st["findings"] if nz(f["quote"]) in nz(st["doc"]["text"]))
    pending.append({"item": "review",
                    "issue": "the report holds %d findings and %d actions; each one is a proposal, not an applied edit"
                             % (len(st["findings"]), len(acts)),
                    "action": "confirm the severity and the operation of every action before applying it"})
    review = {"case_id": cid, "mode": mode, "findings": st["findings"], "actions": acts,
              "dimension_coverage": cov,
              "grounding": {"quotes": len(st["findings"]), "verbatim": ok,
                            "hit_rate": round(ok / float(len(st["findings"])), 3) if st["findings"] else 1.0},
              "stats": stats, "outline": outline, "packet_audit": {} if man else au, "pending_human": pending}
    wj(out / "structural_review.json", review)
    wt(out / "edit_plan.md", plan_md(st, acts, draft) if man else packet_plan(au, pending))
    wt(out / "outline_after.md", outline_md(st, acts, draft, mode))
    wj(out / "argument_map.json", am)
    wt(out / "consistency_report.md", report_md(files, au, st, mode))
    wj(out / "pending_human.json", pending)
    wj(out / "semantic_audit.json", semantic_audit(st, review, mode, cid))
    if man:
        binr = [f["rel"] for f in files if f["binary"]]
        verified = ("Examined %d chapters and %d paragraphs (%d words); %d findings carry a verbatim quote "
                    "(hit rate %.3f); %d executable actions generated."
                    % (stats["chapters"], stats["paragraphs"], stats["words"], ok,
                       review["grounding"]["hit_rate"], len(acts)))
        unverified = ("The strength of the evidence behind each claim was not judged; the review covers structure, "
                      "logic and boundary wording only.")
        if not st["findings"]:
            unverified += " No structural rule fired here, which is not proof of sound structure."
        degradations = "No reduced mode was used; all six detectors ran on the identified manuscript."
        if binr:
            degradations += (" Unparsed material recorded without text: %s (PDF/DOCX are read through their text "
                             "layer; other binary or scanned files are inventoried only)." % ", ".join(binr[:5]))
    else:
        binr = [f["rel"] for f in files if f["binary"]]
        verified = ("Audited %d readable documents: %d headings, %d duplicated sentences at the 55-character threshold "
                    "and %d terms shared across documents."
                    % (len(uniq), au["heading_count"], len(au["duplicates"]), len(au["recurring_terms"])))
        unverified = ("The six structural dimensions need a manuscript the packet does not contain; "
                      "research-question alignment, claim-evidence chains, paragraph transitions, duplication within "
                      "an argument and conclusion boundaries remain unassessed.")
        degradations = ("Reduced to a packet-level audit because no manuscript was identified; the edit plan lists the "
                        "target outline and the material still required.") if uniq else \
                       ("Reduced to an inventory-only audit: no readable text was available, so the review records the "
                        "gaps instead of inventing a manuscript.")
        if binr:
            degradations += (" Unparsed material recorded without text: %s." % ", ".join(binr[:5]))
    status = "input_error" if not files else \
        "insufficient_evidence" if not uniq or not any(wc(f["text"]) > 0 for f in uniq) else \
        "partial" if (mode == "packet" or errs) else "ok"
    limits = []
    if mode == "packet":
        limits.append("no manuscript was identified, so the six dimensions are reported as not assessed")
    if errs:
        limits.append("some stages recorded errors; see the errors array for the stage and detail")
    limits.append("review judgements describe structure and wording, not the scientific truth of the claims")
    if acts:
        limits.append("each action carries a risk note; applying it mechanically can still distort meaning")
    unc = pending + [{"item": "scope", "detail": unverified}]
    cx = {"case_id": cid, "status": status, "verified": verified, "unverified": unverified,
          "degradations": degradations, "actions": acts, "outline": outline, "argmap": am, "review": review,
          "limits": limits, "uncertain": unc, "pending": pending, "errors": errs, "metrics": stats}
    contract = fill(case, cx)
    res = {"case_id": cid, "status": status,
           "summary": "%s review: %d findings, %d actions" % (mode, len(st["findings"]), len(acts)),
           "deliverable": {"path": "edit_plan.md", "editable": True, "structured_result": "structural_review.json"},
           "structural_review": "structural_review.json", "edit_plan": "edit_plan.md",
           "outline_after": "outline_after.md", "argument_map": "argument_map.json",
           "consistency_report": "consistency_report.md", "semantic_audit": "semantic_audit.json",
           "baseline_metrics": "metrics.json", "metrics": stats, "verified": verified,
           "unverified": unverified, "degradations": degradations, "sources": srcs, "uncertainty": unc,
           "uncertainties": unc, "pending_human": pending, "limits": limits, "errors": errs,
           "change_records": [{"step": "review" if man else "packet-audit", "detail": "detector pass completed",
                               "findings": len(st["findings"]), "actions": len(acts)}],
           "runtime": {"skill": "paper-structure-logic-review", "version": VERSION,
                       "seconds": round(time.time() - t0, 3)},
           "output_contract": contract}
    for k, v in contract.items():
        res.setdefault(k, v)
    wj(out / "metrics.json", metrics_payload(res, review))
    wj(out / "result.json", res)
    wj(work / "review.json", {"mode": mode, "status": status, "findings": len(st["findings"]),
                              "actions": len(acts), "metrics": stats, "seconds": res["runtime"]["seconds"]})
    return res


def packet_plan(au, pending):
    lines = ["# Edit plan", "", "No manuscript was identified, so no sentence-level edit is proposed.",
             "The packet-level audit found:", "",
             "- %d headings across the readable documents" % au["heading_count"],
             "- %d duplicated sentences at the 55-character threshold" % len(au["duplicates"]),
             "- %d terms shared across documents" % len(au["recurring_terms"]), "",
             "## What the next run requires", ""]
    lines += ["- %s: %s — %s" % (p.get("item", "item"), p.get("issue", ""), p.get("action", "")) for p in pending[:8]]
    lines += ["", "## Suggested sequence", "",
              "1. Supply the manuscript as a single UTF-8 Markdown or text file.",
              "2. Re-run the full pipeline so the six detectors can produce locators and quotes.",
              "3. Apply the P1 actions first, then re-run to confirm the findings clear.", ""]
    return "\n".join(lines)


def probe(input_dir, work_dir):
    files, uniq = discover(input_dir)
    m = pick_man(uniq)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    inv = {"input": str(input_dir),
           "files": [{"path": f["rel"], "role": f["role"], "bytes": f["bytes"], "sha256": f["sha256"],
                      "empty": f["empty"], "binary": f["binary"], "duplicates": f["duplicates"]} for f in files],
           "manuscript": m["rel"] if m else "", "readable_documents": len([f for f in uniq if f["text"]])}
    wj(work / "inventory.json", inv)
    print(json.dumps({"files": len(files), "manuscript": inv["manuscript"]}, ensure_ascii=False))
    return inv


def selfcheck(input_dir, out_dir):
    out = Path(out_dir)
    try:
        res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"status": "fail", "detail": "result.json unreadable: %s" % exc}))
        return {"status": "fail"}
    case, _ = read_case(input_dir)
    raw = case.get("output_contract") if isinstance(case, dict) else None
    keys = list(raw) if isinstance(raw, dict) and raw else list(FALLBACK)
    echo = res.get("output_contract") if isinstance(res.get("output_contract"), dict) else {}
    miss = [k for k in keys if k not in echo]
    empty = [k for k in keys if k in echo and echo[k] in ("", None, [], {})]
    arts = {n: (out / n).stat().st_size if (out / n).is_file() else 0 for n in ARTIFACTS}
    status = "pass" if not miss and not empty and all(v > 40 for v in arts.values()) else "fail"
    rep = {"status": status, "contract_keys": keys, "missing": miss, "empty": empty, "artifacts": arts,
           "case_id": res.get("case_id", "")}
    wj(out / "selfcheck.json", rep)
    print(json.dumps({"status": status, "missing": miss, "empty": empty}, ensure_ascii=False))
    return rep


def fail_soft(input_dir, out_dir, exc):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        case, _ = read_case(input_dir)
    except Exception:
        case = {}
    cx = {"case_id": str(case.get("case_id") or ""), "status": "partial", "actions": [], "outline": [],
          "argmap": {"research_question": {"quote": "", "locator": ""}, "chains": [], "unsupported_chains": 0,
                     "method": "the run stopped before extraction"},
          "review": {"findings": [], "actions": [], "dimension_coverage": {}},
          "limits": ["the review may be incomplete because the run stopped early"],
          "uncertain": [{"item": "run", "detail": str(exc)[:400]}],
          "pending": [{"item": "run", "issue": "the run stopped early",
                       "action": "re-run after fixing the reported failure"}],
          "errors": [{"stage": "run", "detail": str(exc)[:400]}], "metrics": {"findings": 0, "actions": 0},
          "verified": "The run stopped before any structural check completed.",
          "unverified": "Every structural dimension is unverified because the run stopped early.",
          "degradations": "Partial result stored after an unhandled failure."}
    contract = fill(case, cx)
    wj(out / "result.json", {"case_id": cx["case_id"], "status": "partial", "summary": "the run stopped early",
                             "verified": cx["verified"], "unverified": cx["unverified"],
                             "degradations": cx["degradations"], "sources": [], "uncertainties": cx["uncertain"],
                             "change_records": [{"step": "abort", "detail": str(exc)[:400]}],
                             "limits": cx["limits"], "errors": cx["errors"],
                             "runtime": {"skill": "paper-structure-logic-review", "version": VERSION, "seconds": 0.0},
                             "output_contract": contract})
