#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screen.py -- decision layer: draft loading, decision cards, duplicate view,
conflict typology, final labels, artefact assembly, draft validation (delegated)."""
import json
import re
from pathlib import Path

import ingest as G
import report as R

VERSION = G.VERSION
LABELS = G.LABELS
CODES = G.CODES


# ---------------------------------------------------------------------- draft
def load_draft(work, explicit=None):
    """Locate the agent work draft; never raises."""
    cands = []
    if explicit:
        cands.append(Path(explicit))
    cands += [Path(work) / "draft.json", Path(work) / "plan.json",
              Path(work) / "screening" / "draft.json", Path(work).parent / "output" / "draft.json"]
    for p in cands:
        try:
            if not p.is_file():
                continue
        except Exception:
            continue
        d, e = G.load_json(p)
        if isinstance(d, list):
            return {"decisions": d}, str(p), None
        if isinstance(d, dict):
            return d, str(p), None
        return {}, str(p), "invalid JSON (%s)" % e
    return {}, None, "draft not found (write %s)" % (Path(work) / "draft.json")


def alias_map(idx):
    m = {}
    for r in idx["records"]:
        rid = r["record_id"]
        m[rid.lower()] = rid
        if r["native_id"]:
            m[r["native_id"].lower()] = rid
            m.setdefault("native_id:" + r["native_id"].lower(), rid)
        if r["doi"]:
            m.setdefault("doi:" + r["doi"], rid)
        nt = G.norm_title(r["title"])
        if nt:
            m.setdefault("ti:" + nt, rid)
    return m


def resolve(idx, key, amap):
    k = str(key or "").strip()
    if not k:
        return ""
    if k.lower() in amap:
        return amap[k.lower()]
    kl = k.lower()
    for pre in ("doi:", "ti:", "native_id:"):
        if kl.startswith(pre) and kl in amap:
            return amap[kl]
    nt = G.norm_title(k)
    if len(nt) > 20 and ("ti:" + nt) in amap:
        return amap["ti:" + nt]
    if len(nt) > 25:
        for r in idx["records"]:
            if G.norm_title(r["title"]).startswith(nt[:25]):
                return r["record_id"]
    return ""


def family(code):
    c = str(code or "").upper()
    for pre, fam in (("IN-", "include"), ("EX-", "exclude"), ("P-", "pending")):
        if c.startswith(pre):
            return fam
    return ""


def verify_quote(rec, quote, hint=""):
    q = G.norm(quote).strip(".\u2026 ")
    if not q:
        return False, "", None
    h = str(hint or "").lower()
    fields = [f for f in ("title", "abstract") if f in h] or ["title", "abstract"]
    for f in fields:
        txt = rec.get(f) or ""
        if not txt:
            continue
        i = txt.find(q)
        if i >= 0:
            return True, f, [i, i + len(q)]
        parts = [re.escape(x) for x in q.split()]
        if len(parts) > 1:
            m = re.search(r"\s*".join(parts), txt)
            if m:
                return True, f, [m.start(), m.end()]
    return False, "", None


# ----------------------------------------------------------------------- cards
def make_cards(idx, draft, crit, issues, have_draft):
    amap = alias_map(idx)
    byid = {r["record_id"]: r for r in idx["records"]}
    cards, seen = [], set()
    for d in (draft.get("decisions") or []):
        if not isinstance(d, dict):
            continue
        key = d.get("record_id") or d.get("record") or d.get("id") or d.get("title")
        rid = resolve(idx, key, amap)
        if not rid:
            issues.append({"kind": "unknown_record", "detail": str(key)[:120]})
            continue
        rev = G.clean(d.get("reviewer") or d.get("annotator") or "A") or "A"
        phase = "fulltext" if "full" in G.clean(d.get("phase")).lower() else "title_abstract"
        lab = G.norm_label(d.get("label") or d.get("decision") or d.get("verdict")) or "pending"
        if (rid, phase, rev) in seen:
            issues.append({"kind": "duplicate_card", "detail": "%s/%s/%s" % (rid, phase, rev)})
            continue
        seen.add((rid, phase, rev))
        rec = byid[rid]
        q = G.clean(d.get("evidence_quote") or d.get("quote") or d.get("evidence") or "")
        hit, field, span = verify_quote(rec, q, G.clean(d.get("locator") or d.get("evidence_locator")))
        cards.append({
            "record_id": rid, "study_key": "", "phase": phase, "reviewer": rev, "label": lab,
            "reason_code": G.clean(d.get("reason_code") or d.get("code")).upper(),
            "criterion_id": G.clean(d.get("criterion_id") or d.get("criterion")).upper(),
            "evidence_quote": q,
            "locator": ("%s@%s[%d:%d]" % (rid, field, span[0], span[1])) if hit else "",
            "evidence_hit": bool(hit), "evidence_field": field, "evidence_span": span,
            "criteria_version": G.clean(d.get("criteria_version") or crit["version"]),
            "confidence": d.get("confidence") if isinstance(d.get("confidence"), (int, float)) else None,
            "source": "agent", "note": G.clean(d.get("note"))[:400],
            "rejudged_from": G.clean(d.get("rejudged_from")),
        })
    for l in idx.get("labels") or []:
        rid = l.get("record_id")
        if not rid or rid not in byid:
            continue
        rev = l.get("reviewer") or "B"
        lab = l.get("label_norm") or G.norm_label(l.get("label")) or "pending"
        if (rid, "title_abstract", rev) in seen:
            continue
        seen.add((rid, "title_abstract", rev))
        cards.append({
            "record_id": rid, "study_key": "", "phase": "title_abstract", "reviewer": rev,
            "label": lab, "reason_code": G.clean(l.get("reason_code")).upper(), "criterion_id": "",
            "evidence_quote": "", "locator": "", "evidence_hit": False, "evidence_field": "",
            "evidence_span": None, "criteria_version": l.get("criteria_version") or crit["version"],
            "confidence": None, "source": "input_labels",
            "note": "label supplied by input material (%s line %s)" % (l.get("source_file"), l.get("line")),
            "rejudged_from": "",
        })
    covered = {c["record_id"] for c in cards if c["phase"] == "title_abstract"}
    for r in idx["records"]:
        if r["record_id"] in covered:
            continue
        cards.append({
            "record_id": r["record_id"], "study_key": "", "phase": "title_abstract",
            "reviewer": "agent", "label": "pending",
            "reason_code": "P-NODRAFT" if not have_draft else "P-ABS", "criterion_id": "",
            "evidence_quote": "", "locator": "", "evidence_hit": False, "evidence_field": "",
            "evidence_span": None, "criteria_version": crit["version"], "confidence": None,
            "source": "fallback",
            "note": ("no work draft supplied; record left pending" if not have_draft
                     else "no decision for this record in the work draft"),
            "rejudged_from": "",
        })
    return cards


def dedup_view(idx, draft, issues, degr, have_draft):
    dec = {}
    for d in (draft.get("dedup_decisions") or []):
        if not isinstance(d, dict):
            continue
        gid = re.sub(r"[^0-9]", "", G.clean(d.get("group_id") or d.get("group")))
        if gid:
            dec["D%02d" % int(gid)] = d
    rep, groups = {}, []
    for g in idx["clusters"]:
        d = dec.get(g["group_id"], {})
        choice = G.clean(d.get("decision")).lower()
        members = g["members"]
        rec = None
        if choice in ("merge", "merged", "combine", "1", "true", "yes"):
            rec = G.clean(d.get("representative")).upper() or members[0]
        elif choice in ("keep_separate", "separate", "split", "keep", "no"):
            groups.append(dict(g, applied="keep_separate"))
            continue
        elif not have_draft and g.get("recommend") == "merge":
            rec = members[0]
            degr.append({"kind": "auto_dedup_doi", "group": g["group_id"],
                         "detail": "group merged on identical DOI (identifier fact, not a screening judgement)"})
        else:
            issues.append({"kind": "dedup_undecided",
                           "detail": "%s (%s)" % (g["group_id"], ",".join(members))})
            groups.append(dict(g, applied="undecided"))
            continue
        if rec not in members:
            issues.append({"kind": "bad_representative", "detail": "%s: %s" % (g["group_id"], rec)})
            rec = members[0]
        for m in members:
            if m != rec:
                rep[m] = rec
        groups.append(dict(g, applied="merge", representative=rec))
    return rep, groups


def conflicts(idx, cards, draft, rep, sids):
    amap = alias_map(idx)
    res = {}
    for r in (draft.get("conflict_resolutions") or []):
        if not isinstance(r, dict):
            continue
        rid = resolve(idx, r.get("record_id") or r.get("id"), amap)
        if rid:
            res[rid] = r
    by = {}
    for c in cards:
        if c["phase"] != "title_abstract" or c["source"] == "fallback":
            continue
        by.setdefault(c["study_key"], []).append(c)
    out = []
    for sid, cs in by.items():
        if len({c["reviewer"] for c in cs}) < 2:
            continue
        labs = {c["label"] for c in cs}
        codes = {c["reason_code"] for c in cs if c["reason_code"]}
        vers = {c["criteria_version"] for c in cs}
        if len(labs) == 1 and len(codes) <= 1 and len(vers) <= 1:
            continue
        if len(vers) > 1:
            typ = "version_conflict"
        elif len(labs) > 1 and "pending" not in labs:
            typ = "direction_conflict"
        elif len(labs) > 1 or len(codes) > 1:
            typ = "boundary_conflict" if "pending" in labs else "reason_conflict"
        else:
            typ = "boundary_conflict"
        rep_id = cs[0]["record_id"]
        r = res.get(rep_id) or res.get(sids.get(rep_id, ""))
        verdict = G.norm_label((r or {}).get("verdict")) or "pending"
        open_ = (r is None) or verdict == "pending" or bool((r or {}).get("needs_human"))
        out.append({
            "study_key": sid, "record_id": rep_id, "type": typ,
            "sides": [{"reviewer": c["reviewer"], "label": c["label"],
                       "reason_code": c["reason_code"], "criterion_id": c["criterion_id"],
                       "quote": c["evidence_quote"][:260], "locator": c["locator"]} for c in cs],
            "verdict": "pending" if open_ else verdict,
            "reason_code": G.clean((r or {}).get("reason_code")).upper(),
            "basis_criterion_id": G.clean((r or {}).get("basis_criterion_id")).upper(),
            "basis_quote": G.clean((r or {}).get("basis_quote")),
            "basis_locator": G.clean((r or {}).get("basis_locator")),
            "rationale": G.clean((r or {}).get("rationale"))[:600],
            "unresolved_reason": (G.clean((r or {}).get("rationale"))[:300] if open_ else ""),
            "open": open_,
        })
    return out, res


def final_labels(studies, cards, confs):
    cmap = {c["study_key"]: c for c in confs}
    out = {}
    for sid in studies:
        real = [c for c in cards if c["study_key"] == sid and c["phase"] == "title_abstract"
                and c["source"] != "fallback"]
        labs = {c["label"] for c in real}
        if not real:
            out[sid] = ("pending", "no_decision")
        elif len(labs) == 1:
            out[sid] = (list(labs)[0], "agreement" if len(real) > 1 else "single_reviewer")
        else:
            c = cmap.get(sid)
            out[sid] = (c["verdict"], "arbitrated") if (c and not c["open"]) else ("pending", "conflict_open")
    return out


def analyse(idx, draft, have_draft, issues, degr):
    crit = R.criteria_view(idx, draft)
    cards = make_cards(idx, draft, crit, issues, have_draft)
    rep, groups = dedup_view(idx, draft, issues, degr, have_draft)
    cards = [c for c in cards if not (c["source"] == "fallback" and c["record_id"] in rep)]
    studies, sids = {}, {}
    for r in idx["records"]:
        key = rep.get(r["record_id"], r["record_id"])
        if key not in sids:
            sids[key] = "S%02d" % (len(sids) + 1)
            studies[sids[key]] = key
    for c in cards:
        c["study_key"] = sids.get(rep.get(c["record_id"], c["record_id"]), "S??")
    confs, _ = conflicts(idx, cards, draft, rep, sids)
    return {"crit": crit, "cards": cards, "rep": rep, "groups": groups,
            "studies": studies, "confs": confs, "labels": final_labels(studies, cards, confs)}


# ---------------------------------------------------------------------- build
def build(idx, draft, path, err, out, work):
    out, work = Path(out), Path(work)
    have_draft = bool(draft) and (bool(draft.get("decisions")) or bool(draft.get("dedup_decisions")))
    issues, degr, errors = [], list(idx["degradations"]), list(idx["errors"])
    if not have_draft:
        degr.append({"kind": "draft_missing",
                     "detail": "no usable work draft at %s (%s); every record is left pending"
                               % (path or "-", err or "empty")})
    A = analyse(idx, draft, have_draft, issues, degr)
    cards, crit, labels = A["cards"], A["crit"], A["labels"]
    if crit["source"] == "draft":
        degr = [d for d in degr if d.get("kind") != "criteria_missing"]
        degr.append({"kind": "criteria_from_draft",
                     "detail": "no criteria in the materials; the %d criteria in use were declared "
                               "in the working draft (fingerprint %s)"
                               % (len(crit["items"]), crit["fingerprint"])})

    identified = len(idx["records"])
    dup = len(A["rep"])
    screened = identified - dup
    inc = sum(1 for l, _ in labels.values() if l == "include")
    exc = sum(1 for l, _ in labels.values() if l == "exclude")
    pend = sum(1 for l, _ in labels.values() if l == "pending")
    c_total = len(A["confs"])
    c_open = sum(1 for c in A["confs"] if c["open"])
    with_cards = len({c["study_key"] for c in cards
                      if c["phase"] == "title_abstract" and c["source"] != "fallback"})
    qc = [c for c in cards if c["source"] == "agent" and c["evidence_quote"]]
    qhit = sum(1 for c in qc if c["evidence_hit"])
    eqs = [R.eq("E1", "identified - duplicates_removed = screened", identified - dup, screened),
           R.eq("E2", "screened = included + excluded + pending", screened, inc + exc + pend),
           R.eq("E3", "conflicts_total = arbitrated + conflicts_open", c_total, c_total - c_open + c_open),
           R.eq("E4", "pending = conflicts_open + awaiting_info", pend, c_open + (pend - c_open)),
           R.eq("E5", "studies_with_cards = screened", with_cards, screened)]

    rstats, code_by_study = {}, {}
    cmap = {c["study_key"]: c for c in A["confs"]}
    for sid, (lab, basis) in labels.items():
        cs = [c for c in cards if c["study_key"] == sid and c["phase"] == "title_abstract"
              and c["reason_code"]]
        code = (cmap.get(sid) or {}).get("reason_code", "") if basis == "arbitrated" else ""
        if not code:
            code = next((c["reason_code"] for c in cs if c["label"] == lab), "")
        code = code or (cs[0]["reason_code"] if cs else "") or "UNSPECIFIED"
        rstats[code] = rstats.get(code, 0) + 1
        code_by_study[sid] = code
    reason_stats = []
    for k, v in sorted(rstats.items(), key=lambda x: -x[1]):
        cid = next((c["criterion_id"] for c in cards if c["reason_code"] == k and c["criterion_id"]), "")
        reason_stats.append({"reason_code": k, "count": v, "criterion_id": cid,
                             "gloss": ((CODES.get(k) or {}).get("zh")
                                       or ("no decision card" if k == "UNSPECIFIED" else ""))})

    counts = {"identified": identified, "duplicates_removed": dup, "screened": screened,
              "included": inc, "excluded": exc, "pending": pend,
              "conflicts_total": c_total, "arbitrated": c_total - c_open, "conflicts_open": c_open,
              "coverage": round(with_cards / float(screened), 3) if screened else 0.0,
              "quote_hit_rate": round(qhit / float(len(qc)), 3) if qc else 0.0,
              "decision_cards": len(cards), "studies": len(labels),
              "identified_basis": R.basis_of(idx), "dedup_basis": R.dedup_basis(A["groups"])}

    meta = {"generated": idx.get("generated_at") or "", "draft": path or ""}
    label_rows = [{"study_key": s, "record_id": A["studies"][s], "label": labels[s][0],
                   "basis": labels[s][1]} for s in labels]
    files = {
        "flow_ledger.md": R.render_ledger(idx, crit, counts, eqs, label_rows, reason_stats, meta),
        "arbitration_docket.md": R.render_docket(idx, A["confs"], crit, meta),
        "decision_cards.jsonl": "\n".join(
            json.dumps({k: c[k] for k in ("study_key", "record_id", "phase", "reviewer", "label",
                                          "reason_code", "criterion_id", "evidence_quote", "locator",
                                          "evidence_hit", "criteria_version", "source", "note",
                                          "rejudged_from")}, ensure_ascii=False) for c in cards) + "\n",
    }
    audit = {"case_id": idx["case_id"],
             "criteria": {"version": crit["version"], "source": crit["source"],
                          "fingerprint": crit["fingerprint"], "available": crit["available"]},
             "equations": eqs, "counts": counts, "reason_codes": reason_stats,
             "anomalies": idx["anomalies"], "issues": issues,
             "coverage": {"screened": screened, "with_cards": with_cards,
                          "quote_checked": len(qc), "quote_hit": qhit},
             "cards_by_source": {s: sum(1 for c in cards if c["source"] == s)
                                 for s in ("agent", "input_labels", "fallback")}}
    files["audit_closure.json"] = json.dumps(audit, ensure_ascii=False, indent=2)

    artifacts = []
    for name, body in files.items():
        G.write_text(out / name, body)
        artifacts.append({"name": name, "bytes": len(str(body).encode("utf-8")),
                          "sha1": G.sha1(body), "role": R.role_of(name)})

    rec_rows = []
    for s in labels:
        rid = A["studies"][s]
        rec = next((r for r in idx["records"] if r["record_id"] == rid), {})
        cs = [c for c in cards if c["study_key"] == s and c["phase"] == "title_abstract"]
        best = next((c for c in cs if c["evidence_hit"]), cs[0] if cs else {})
        rec_rows.append({"study_key": s, "record_id": rid, "title": rec.get("title", ""),
                         "year": rec.get("year", ""), "doi": rec.get("doi", ""),
                         "label": labels[s][0], "basis": labels[s][1],
                         "reason_code": best.get("reason_code", ""),
                         "criterion_id": best.get("criterion_id", ""),
                         "evidence_quote": best.get("evidence_quote", ""),
                         "locator": best.get("locator", ""),
                         "criteria_version": crit["version"],
                         "reviewers": {c["reviewer"]: c["label"] for c in cs}})
    prot = draft.get("protocol") if isinstance(draft.get("protocol"), dict) else {}
    P = {
        "records": rec_rows,
        "counts": counts,
        "conflicts": [{"study_key": c["study_key"], "record_id": c["record_id"], "type": c["type"],
                       "verdict": c["verdict"], "open": c["open"],
                       "basis_criterion_id": c["basis_criterion_id"], "sides": c["sides"]}
                      for c in A["confs"]],
        "dedup": {"groups": A["groups"], "duplicates_removed": dup, "mapping": A["rep"]},
        "criteria": {"criteria_version": crit["version"], "source": crit["source"],
                     "fingerprint": crit["fingerprint"], "available_versions": crit["available"],
                     "items": crit["items"], "reason_codes": reason_stats},
        "protocol": {"research_question": idx.get("research_question"),
                     "reviewers": sorted({c["reviewer"] for c in cards if c["source"] == "agent"}),
                     "queries": prot.get("query_strings") or idx.get("query") or [],
                     "databases": sorted({q.get("database") for q in (prot.get("query_strings") or [])
                                          if isinstance(q, dict) and q.get("database")}),
                     "query_source": "draft" if prot.get("query_strings") else "materials"},
        "evidence": [{"record_id": c["record_id"], "study_key": c["study_key"], "claim": c["label"],
                      "reason_code": c["reason_code"], "criterion_id": c["criterion_id"],
                      "quote": c["evidence_quote"], "locator": c["locator"],
                      "verified": c["evidence_hit"], "source": c["source"]} for c in cards],
        "audit": audit,
        "sources": idx["files"],
        "uncertainty": R.uncertainty(idx, draft, issues),
        "artifacts": artifacts,
        "notes": (G.clean(draft.get("status_note")) or
                  "%d records identified, %d duplicates removed, %d screened: %d included, "
                  "%d excluded, %d pending; %d conflicts (%d open)."
                  % (identified, dup, screened, inc, exc, pend, c_total, c_open)),
        "status": "partial",
    }
    qmiss = [c for c in cards if c["source"] == "agent" and c["evidence_quote"]
             and not c["evidence_hit"]]
    if qmiss:
        degr.append({"kind": "quote_miss",
                     "detail": "%d card(s) quote text that is not verbatim in the record: %s"
                               % (len(qmiss), ", ".join(c["record_id"] for c in qmiss[:8]))})
    status = "ok"
    fallback_n = sum(1 for c in cards if c["source"] == "fallback")
    no_quote = [c for c in cards if c["source"] == "agent" and c["label"] != "pending"
                and not c["evidence_quote"]]
    if not idx["records"]:
        status = ("input_error" if any("case" in str(e.get("where", "")).lower() for e in errors)
                  else "insufficient_evidence")
    elif ((not have_draft) or c_open or counts["coverage"] < 1.0 or issues
          or fallback_n or no_quote):
        status = "partial"
    if qc and counts["quote_hit_rate"] < 1.0:
        status = "partial"
    P["status"] = status
    extra = {
        "case_id": idx["case_id"], "status": status, "errors": errors,
        "degradations": degr, "counts": counts,
        "verification": {"checks": [{"id": e["id"], "status": e["status"]} for e in eqs],
                         "quote_hit_rate": counts["quote_hit_rate"],
                         "contract_keys": len(idx["output_contract"] or {}),
                         "cards_parsable": True},
        "pending_human": R.pending_human(A, draft) + [
            {"item": "%s evidence" % c["record_id"],
             "reason": "quoted text is not verbatim in the record; the card needs re-checking"}
            for c in qmiss[:10]],
        "changes": [{"step": "init", "detail": "index built from the input snapshot"},
                    {"step": "build", "detail": "artefacts rendered from %s" % (path or "fallback")}],
        "assumptions": ["input snapshot only; no live database search was performed",
                        "reviewer labels found in materials are taken as given",
                        "merging duplicates beyond identical-DOI groups is a drafted human decision"],
        "runtime": {"version": VERSION, "draft_present": bool(have_draft),
                    "criteria_version": crit["version"]},
    }
    return R.envelope(idx, P, extra), {"counts": counts, "equations": eqs, "artifacts": artifacts}


# ---------------------------------------------------------------------- check
def check_draft(idx, draft, path, err):
    """Delegates to report.check_draft with this module's analyse()."""
    return R.check_draft(idx, draft, path, err, analyse)


# re-exports: main.py uses a single screen entry point
write_partial = R.write_partial
selfcheck = R.selfcheck
