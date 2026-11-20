#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.py -- rendering and result envelope for systematic-screening-ledger.

flow ledger / arbitration docket / contract echo / partial result / self-check.
Imported by screen.py and main.py; stdlib only; exit code is owned by the caller.
"""
import json
import re
from pathlib import Path

import ingest as G

VERSION = G.VERSION
CODES = G.CODES
LABELS = G.LABELS


def eq(eid, name, left, right):
    return {"id": eid, "equation": name, "left": left, "right": right,
            "diff": left - right, "status": "PASS" if left == right else "FAIL"}


def render_ledger(idx, crit, counts, eqs, labels, reason_stats, meta):
    L = []
    ap = L.append
    ap("# Flow ledger - case %s" % idx["case_id"])
    ap("")
    ap("- criteria version: `%s` (source=%s, fingerprint=%s)"
       % (crit["version"], crit["source"], crit["fingerprint"] or "-"))
    ap("- pipeline v%s | draft: %s (counts are reproducible from the cards below)"
       % (VERSION, meta.get("draft") or "none (degraded)"))
    if idx.get("research_question"):
        ap("- research question: %s" % idx["research_question"])
    ap("")
    ap("## 1. Flow (PRISMA style)")
    ap("")
    ap("| # | stage | n | basis (file / field) | independently checkable by |")
    ap("|---|---|---|---|---|")
    ap("| 1 | identified | %d | %s | index.json `records[]` |"
       % (counts["identified"], counts["identified_basis"]))
    ap("| 2 | duplicates_removed | %d | %d merged record(s): %s | index.json `clusters[]` + draft `dedup_decisions[]` |"
       % (counts["duplicates_removed"], counts["duplicates_removed"], counts["dedup_basis"]))
    ap("| 3 | screened | %d | identified - duplicates_removed | identity E1 |" % counts["screened"])
    ap("| 4 | excluded | %d | decision_cards.jsonl label=exclude | per-card locator |"
       % counts["excluded"])
    ap("| 5 | included | %d | decision_cards.jsonl label=include | per-card locator |" % counts["included"])
    ap("| 6 | pending | %d | label=pending (P-ABS / P-CONFLICT / P-NODRAFT) | per-card reason_code |"
       % counts["pending"])
    ap("| 7 | conflicts_total | %d | arbitration_docket.md | docket sections |" % counts["conflicts_total"])
    ap("| 8 | arbitrated | %d | docket entries with verdict != pending | docket basis |"
       % counts["arbitrated"])
    ap("| 9 | conflicts_open | %d | docket entries still pending | pending_human in result.json |"
       % counts["conflicts_open"])
    ap("")
    ap("## 2. Identity checks")
    ap("")
    ap("| id | equation | left | right | diff | status |")
    ap("|---|---|---|---|---|---|")
    for e in eqs:
        ap("| %s | %s | %d | %d | %d | %s |" % (e["id"], e["equation"], e["left"], e["right"],
                                                e["diff"], e["status"]))
    ap("")
    ap("## 3. Exclusion reasons in use")
    ap("")
    ap("| reason_code | n | criterion | gloss |")
    ap("|---|---|---|---|")
    for r in reason_stats:
        ap("| %s | %d | %s | %s |" % (r["reason_code"], r["count"], r["criterion_id"] or "-",
                                      (r["gloss"] or "-").replace("|", "/")))
    ap("")
    ap("## 4. Per-study outcome")
    ap("")
    ap("| study | record | label | basis |")
    ap("|---|---|---|---|")
    for s in labels:
        ap("| %s | %s | %s | %s |" % (s["study_key"], s["record_id"], s["label"], s["basis"]))
    ap("")
    return "\n".join(L)


def render_docket(idx, confs, crit, meta):
    L = []
    ap = L.append
    ap("# Arbitration docket - case %s" % idx["case_id"])
    ap("")
    ap("criteria version: `%s` (fingerprint %s) | conflicts: %d | open: %d"
       % (crit["version"], crit["fingerprint"] or "-", len(confs),
          sum(1 for c in confs if c["open"])))
    ap("")
    if not confs:
        ap("No reviewer disagreement was detected in the supplied decision cards.")
        ap("")
        return "\n".join(L)
    for i, c in enumerate(confs, 1):
        ap("## Docket %d - %s / %s - `%s`" % (i, c["study_key"], c["record_id"], c["type"]))
        ap("")
        ap("| reviewer | label | reason_code | criterion | evidence (verbatim) | locator |")
        ap("|---|---|---|---|---|---|")
        for s in c["sides"]:
            ap("| %s | %s | %s | %s | %s | %s |"
               % (s["reviewer"], s["label"], s["reason_code"] or "-", s["criterion_id"] or "-",
                  (s["quote"] or "-").replace("|", "/")[:180], s["locator"] or "-"))
        ap("")
        ap("- divergence: %s" % (G.CONFLICT_TYPES.get(c["type"], c["type"])))
        ap("- verdict: **%s**%s" % (c["verdict"], "" if not c["open"] else " (open, needs a human)"))
        if c["basis_criterion_id"] or c["basis_quote"]:
            ap("- basis: criterion `%s` + %s %s"
               % (c["basis_criterion_id"] or "-", c["basis_quote"][:200] or "-",
                  ("(" + c["basis_locator"] + ")") if c["basis_locator"] else ""))
        if c["rationale"]:
            ap("- rationale: %s" % c["rationale"])
        if c["open"]:
            ap("- unresolved: %s" % (c["unresolved_reason"] or "no arbitration entry in the work draft"))
        ap("")
    return "\n".join(L)


def _by_type(t):
    t = str(t or "").lower()
    if any(w in t for w in ("array", "list", "[]")):
        return []
    if any(w in t for w in ("object", "dict", "map", "{}")):
        return {}
    if any(w in t for w in ("str", "text", "string")):
        return ""
    if any(w in t for w in ("int", "num", "float", "count")):
        return 0
    if "bool" in t:
        return False
    return None


def fallback_value(spec):
    if isinstance(spec, dict):
        t = spec.get("type") or spec.get("format") or ""
        return _by_type(t) if t else {}
    if isinstance(spec, str):
        return _by_type(spec)
    if isinstance(spec, bool):
        return False
    if isinstance(spec, (int, float)):
        return 0
    if isinstance(spec, list):
        return []
    return None


def contract_value(key, spec, P, idx):
    """Map a contract key onto real pipeline content; token match, not raw substring."""
    raw = str(key).lower()
    toks = {x for x in re.split(r"[^a-z0-9]+", raw) if x}
    k = "_".join(sorted(toks))

    def t(*ws):
        return bool(toks & set(ws))

    def hit(*ws):
        return any(w in k for w in ws)

    if raw in ("case_id", "id", "case", "caseid"):
        return idx["case_id"]
    if t("protocol", "protocols", "query", "queries", "search", "searches",
         "strategy", "strategies", "database", "databases", "limits"):
        return P["protocol"]
    if t("note", "notes", "comment", "comments", "remark", "remarks",
         "conclusion", "conclusions"):
        return P.get("notes") or ""
    if t("record", "records", "screening", "screen", "screened", "decision", "decisions",
         "candidate", "candidates", "paper", "papers", "literature", "entry", "entries",
         "shortlist", "item", "items") or hit("screening_"):
        return P["records"]
    if t("conflict", "conflicts", "arbitration", "arbitrations", "disagreement",
         "disagreements", "docket"):
        return P["conflicts"]
    if t("dedup", "deduplication", "duplicate", "duplicates", "merge", "merges"):
        return P["dedup"]
    if t("criteria", "criterion", "standard", "standards", "reason", "reasons", "code", "codes"):
        return P["criteria"]
    if t("evidence", "verification", "locator", "locators", "provenance", "quote", "quotes", "trace"):
        return P["evidence"]
    if t("flow", "ledger", "prisma", "count", "counts", "statistics", "statistic",
         "summary", "closure"):
        return P["counts"]
    if t("audit", "log", "logs", "change", "changes"):
        return P["audit"]
    if t("source", "sources", "material", "materials", "input", "inputs", "files"):
        return P["sources"]
    if t("uncertainty", "uncertainties", "limitation", "limitations", "gap", "gaps",
         "missing", "risk", "risks"):
        return P["uncertainty"]
    if t("artifact", "artifacts", "deliverable", "deliverables", "output", "outputs",
         "product", "products", "file"):
        return P["artifacts"]
    if t("status", "state"):
        return P["status"]
    if t("title", "question", "objective", "topic", "aim"):
        return idx.get("research_question") or ""
    if t("lang", "language"):
        return "as in input"
    return fallback_value(spec)


def coerce(v, spec):
    """Honour the declared shape of a contract field (array / object / string)."""
    t = ""
    if isinstance(spec, str):
        t = spec.lower()
    elif isinstance(spec, dict):
        t = str(spec.get("type") or spec.get("format") or "").lower()
    if not t:
        return v
    if any(w in t for w in ("array", "list")) and isinstance(v, dict):
        for k in ("groups", "items", "records", "conflicts", "entries", "codes"):
            if isinstance(v.get(k), list):
                return v[k]
        return [v] if v else []
    if any(w in t for w in ("object", "dict", "map")) and isinstance(v, list):
        return {"items": v}
    if any(w in t for w in ("str", "text")) and not isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)[:2000]
    return v


def envelope(idx, P, extra):
    res, unmapped = {}, []
    for k, spec in (idx["output_contract"] or {}).items():
        v = coerce(contract_value(k, spec, P, idx), spec)
        if spec is not None and v == fallback_value(spec):
            unmapped.append(k)
        res[k] = v
    res.update(extra)
    res["contract_unmapped"] = unmapped
    res["output_contract_echo"] = idx["output_contract"]
    return res


def write_partial(idx, out):
    P = {"records": [], "counts": {}, "conflicts": [],
         "dedup": {"groups": idx["clusters"], "duplicates_removed": 0},
         "criteria": {"criteria_version": idx["criteria"]["active"] or None,
                      "available_versions": idx["criteria"]["versions"], "items": []},
         "protocol": {"research_question": idx.get("research_question"), "queries": []},
         "evidence": [], "audit": {}, "sources": idx["files"],
         "uncertainty": idx["degradations"], "artifacts": [], "status": "partial"}
    extra = {"case_id": idx["case_id"], "status": "partial", "stage": "partial",
             "errors": idx["errors"],
             "degradations": list(idx["degradations"]) +
                             [{"kind": "partial", "detail": "pipeline started; final artefacts not written yet"}],
             "runtime": {"version": VERSION}}
    G.write_json(Path(out) / "result.json", envelope(idx, P, extra))
    return 0


def basis_of(idx):
    f = ", ".join(sorted({r["source_file"] for r in idx["records"]})) or "-"
    return "%s (%d rows)" % (f, len(idx["records"]))


def dedup_basis(groups):
    used = [g for g in groups if g.get("applied") == "merge"]
    if not used:
        return "none merged"
    return "; ".join("%s(%s)" % (g["group_id"], ",".join(g["members"])) for g in used)


def role_of(name):
    return {"flow_ledger.md": "flow", "decision_cards.jsonl": "cards",
            "arbitration_docket.md": "docket", "audit_closure.json": "audit"}.get(name, "artifact")


def uncertainty(idx, draft, issues):
    out = [{"kind": d["kind"], "detail": d["detail"]} for d in idx["degradations"]]
    out += [{"kind": "anomaly", "record_id": a["record_id"], "flag": a["flag"],
             "detail": a.get("gloss", "")} for a in idx["anomalies"][:20]]
    out += [{"kind": g.get("kind") or "gap",
             "detail": G.clean(g.get("reason") or g.get("item"))[:300]}
            for g in (draft.get("gaps") or []) if isinstance(g, dict)]
    out += [{"kind": i.get("kind") or i.get("where") or "issue",
             "detail": i.get("detail") or i.get("error") or ""} for i in issues[:20]]
    seen, keep = set(), []
    for u in out:
        k = (u.get("kind"), u.get("detail"))
        if k in seen:
            continue
        seen.add(k)
        keep.append(u)
    return keep[:40]


def pending_human(A, draft):
    out = []
    for c in A["confs"]:
        if c["open"]:
            out.append({"item": "%s (%s)" % (c["study_key"], c["record_id"]),
                        "reason": "%s at %s; %s"
                                  % (c["type"], c["record_id"],
                                     c["unresolved_reason"] or "needs a documented arbitration decision")})
    for sid, (lab, basis) in A["labels"].items():
        if basis == "no_decision":
            out.append({"item": "%s (%s)" % (sid, A["studies"][sid]),
                        "reason": "no screening decision in the work draft"})
    for g in (draft.get("gaps") or []):
        if isinstance(g, dict):
            out.append({"item": G.clean(g.get("item"))[:120], "reason": G.clean(g.get("reason"))[:300]})
    return out[:40]


def selfcheck(idx, out):
    out = Path(out)
    checks = []
    res, e = G.load_json(out / "result.json")
    res = res if isinstance(res, dict) else {}
    checks.append({"id": "S1-result", "status": "pass" if res else "fail",
                   "detail": "result.json %s" % ("parsed" if res else ("missing/bad: %s" % e))})
    missing = [k for k in (idx.get("output_contract") or {}) if k not in res]
    checks.append({"id": "S2-contract", "status": "pass" if not missing else "fail",
                   "detail": "contract keys=%d missing=%s"
                             % (len(idx.get("output_contract") or {}), ",".join(missing[:8]) or "none")})
    checks.append({"id": "S3-case-id", "status": "pass" if res.get("case_id") else "fail",
                   "detail": "case_id=%s status=%s" % (res.get("case_id"), res.get("status"))})
    for name in ("flow_ledger.md", "decision_cards.jsonl", "arbitration_docket.md", "audit_closure.json"):
        p = out / name
        ok = p.is_file() and p.stat().st_size > 20
        checks.append({"id": "S4-%s" % name.split(".")[0], "status": "pass" if ok else "fail",
                       "detail": "%s (%dB)" % (name, p.stat().st_size if p.is_file() else 0)})
    bad = 0
    try:
        for ln in (out / "decision_cards.jsonl").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                json.loads(ln)
    except Exception:
        bad += 1
    checks.append({"id": "S5-cards-jsonl", "status": "pass" if not bad else "fail",
                   "detail": "unparsable lines=%d" % bad})
    diffs = []
    try:
        a = json.loads((out / "audit_closure.json").read_text(encoding="utf-8"))
        diffs = [x for x in a.get("equations", []) if x.get("diff")]
    except Exception:
        diffs = [{"id": "audit-read", "diff": -1}]
    checks.append({"id": "S6-identities", "status": "pass" if not diffs else "warn",
                   "detail": "non-zero diffs=%d %s" % (len(diffs), [x.get("id") for x in diffs])})
    fails = sum(1 for c in checks if c["status"] == "fail")
    return {"ok": fails == 0, "fail": fails, "checks": checks}


def family(code):
    c = str(code or "").upper()
    for pre, fam in (("IN-", "include"), ("EX-", "exclude"), ("P-", "pending")):
        if c.startswith(pre):
            return fam
    return ""


def check_draft(idx, draft, path, err, analyse):
    issues, degr, checks = [], [], []
    have_draft = bool(draft) and (bool(draft.get("decisions")) or bool(draft.get("dedup_decisions")))

    def add(cid, ok, detail, items=None, warn=False):
        checks.append({"id": cid, "status": "pass" if ok else ("warn" if warn else "fail"),
                       "detail": detail, "items": items or []})

    add("C0-draft", have_draft,
        ("draft=%s decisions=%d dedup=%d" % (path or "-", len(draft.get("decisions") or []),
                                             len(draft.get("dedup_decisions") or [])))
        if have_draft else "no usable draft: %s" % (err or "empty"))
    if not have_draft:
        return {"ok": False, "errors": 1, "warnings": 0, "checks": checks,
                "counts": {"records": len(idx["records"]), "coverage": 0.0}}

    A = analyse(idx, draft, True, issues, degr)
    crit, cards = A["crit"], [c for c in A["cards"] if c["source"] == "agent"]
    ck = list((idx.get("output_contract") or {}).keys())
    add("C1-contract", True, "output_contract keys=%d (%s)" % (len(ck), ", ".join(ck[:6]) or "-"),
        warn=not ck)
    add("C2-criteria-version", crit["version"] in (crit["available"] or [crit["version"]]) or crit["source"] == "draft",
        "version=%s source=%s available=%s fingerprint=%s"
        % (crit["version"], crit["source"], ",".join(crit["available"]) or "-", crit["fingerprint"] or "-"))
    bad = [c for c in cards if c["label"] not in LABELS]
    add("C3-labels", not bad, "agent cards=%d invalid labels=%d" % (len(cards), len(bad)),
        [c["record_id"] for c in bad[:8]])
    unknown = [c for c in cards if c["reason_code"] and c["reason_code"] not in CODES]
    mismatch = [c for c in cards if c["reason_code"] in CODES and family(c["reason_code"]) != c["label"]]
    add("C4-reason-codes", not unknown and not mismatch,
        "unknown=%d family_mismatch=%d" % (len(unknown), len(mismatch)),
        ["%s:%s/%s" % (c["record_id"], c["reason_code"], c["label"]) for c in (unknown + mismatch)[:8]])
    no_reason = [c for c in cards if not c["reason_code"] and c["label"] != "pending"]
    if no_reason:
        add("C4b-reason-missing", False, "%d include/exclude cards carry no reason_code" % len(no_reason),
            [c["record_id"] for c in no_reason[:8]], warn=True)
    ids = {i["id"] for i in crit["items"]}
    bad_cid = [c for c in cards if c["criterion_id"] and c["criterion_id"] not in ids]
    add("C5-criterion-ids", not bad_cid, "known criteria=%d unknown refs=%d" % (len(ids), len(bad_cid)),
        ["%s:%s" % (c["record_id"], c["criterion_id"]) for c in bad_cid[:8]], warn=not ids)
    qc = [c for c in cards if c["evidence_quote"]]
    miss = [c for c in qc if not c["evidence_hit"]]
    rate = round((len(qc) - len(miss)) / float(len(qc)), 3) if qc else 0.0
    add("C6-quotes", not miss, "quoted=%d verbatim_hit=%d rate=%.3f" % (len(qc), len(qc) - len(miss), rate),
        ["%s: %s" % (c["record_id"], c["evidence_quote"][:60]) for c in miss[:6]], warn=not qc)
    with_cards = {c["study_key"] for c in A["cards"]
                  if c["phase"] == "title_abstract" and c["source"] != "fallback"}
    cov = round(len(with_cards) / float(len(A["studies"])), 3) if A["studies"] else 0.0
    missing = sorted(set(A["studies"]) - with_cards)
    add("C7-coverage", cov >= 1.0, "studies=%d covered=%d coverage=%.3f"
        % (len(A["studies"]), len(with_cards), cov), [A["studies"][s] for s in missing][:12])
    dup = [i for i in issues if i["kind"] == "duplicate_card"]
    add("C8-duplicate-cards", not dup, "duplicate cards=%d" % len(dup), [i["detail"] for i in dup[:6]])
    und = [i for i in issues if i["kind"] == "dedup_undecided"]
    add("C9-dedup", not und, "groups=%d merged_records=%d undecided=%d"
        % (len(idx["clusters"]), len(A["rep"]), len(und)), [i["detail"] for i in und[:6]], warn=True)
    open_c = [c for c in A["confs"] if c["open"]]
    add("C10-arbitration", not open_c, "conflicts=%d resolved=%d open=%d"
        % (len(A["confs"]), len(A["confs"]) - len(open_c), len(open_c)),
        ["%s (%s)" % (c["study_key"], c["type"]) for c in open_c[:6]], warn=True)
    bad_basis = [c for c in A["confs"] if not c["open"] and not c["basis_criterion_id"] and not c["basis_quote"]]
    if bad_basis:
        add("C10b-arbitration-basis", False,
            "%d resolutions cite neither a criterion nor a quote" % len(bad_basis),
            [c["study_key"] for c in bad_basis[:6]], warn=True)
    gaps = [g for g in (draft.get("gaps") or []) if isinstance(g, dict)]
    add("C11-gaps", True, "declared gaps=%d" % len(gaps), warn=not gaps)
    lab = [l for l, _ in A["labels"].values()]
    screened = len(idx["records"]) - len(A["rep"])
    add("C12-identity", screened == len(lab),
        "screened=%d included=%d excluded=%d pending=%d"
        % (screened, lab.count("include"), lab.count("exclude"), lab.count("pending")))
    unack = [a for a in idx["anomalies"] if a["flag"] in ("no_abstract", "mojibake", "no_doi")
             and a["record_id"] not in {c["record_id"] for c in A["cards"]}]
    add("C13-anomalies", not unack, "anomalies=%d unhandled=%d" % (len(idx["anomalies"]), len(unack)),
        [a["record_id"] for a in unack[:8]], warn=True)
    errs = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    return {"ok": errs == 0, "errors": errs, "warnings": warns, "checks": checks,
            "counts": {"records": len(idx["records"]), "screened": screened,
                       "included": lab.count("include"), "excluded": lab.count("exclude"),
                       "pending": lab.count("pending"), "coverage": cov, "quote_hit_rate": rate},
            "issues": issues[:40]}


def criteria_view(idx, draft):
    prot = draft.get("protocol") if isinstance(draft.get("protocol"), dict) else {}
    dc = prot.get("criteria") or draft.get("criteria") or []
    sets = idx["criteria"]["sets"]
    ver = str(prot.get("criteria_version") or prot.get("version") or "").strip()
    items, src = [], "materials"
    if ver and ver in sets:
        items = sets[ver]
    elif not ver and idx["criteria"]["active"]:
        ver = idx["criteria"]["active"]
        items = sets.get(ver, [])
    if not items and isinstance(dc, list) and dc:
        items, src = draft_criteria(dc, idx), "draft"
    if not items:
        src = "none"
    fp = G.sha1("|".join("%s:%s:%s" % (i.get("id"), i.get("kind"), G.norm(i.get("text"))) for i in items))
    return {"version": ver or "unversioned", "items": items, "source": src,
            "fingerprint": fp if items else "", "available": idx["criteria"]["versions"]}


def draft_criteria(dc, idx):
    out = []
    for i, it in enumerate(dc, 1):
        if isinstance(it, str):
            out.append({"id": "C%02d" % i, "kind": "other", "text": G.norm(it),
                        "version": "draft", "source": "draft", "line": i})
        elif isinstance(it, dict):
            kk = G.clean(it.get("kind") or it.get("type")).lower()
            kk = ("exclude" if ("excl" in kk or "排除" in kk)
                  else "include" if ("incl" in kk or "纳入" in kk) else "other")
            out.append({"id": (G.clean(it.get("id")).upper() or "C%02d" % i), "kind": kk,
                        "text": G.norm(it.get("text") or it.get("criterion") or ""),
                        "version": G.clean(it.get("version")) or "draft",
                        "source": "draft", "line": i})
    return [x for x in out if x["text"]]
