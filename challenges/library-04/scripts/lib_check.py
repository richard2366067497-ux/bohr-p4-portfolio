#!/usr/bin/env python3
"""lib_check.py -- deterministic draft validation and docket rendering (stdlib only).

validate(): exhibit identity/existence, verbatim quote, locator agreement (the
claimed paragraph must contain the quote), version agreement, verdict/evidence
pairing, missing-evidence + search-scope completeness, dedupe claims, unreadable
flags, numeric anchoring, question coverage.
render(): report.md, dockets/<QID>/verdict.md, exhibit register, version witness,
conflicts, repair log, search scope, library index.
"""
import csv
import json
import re
from pathlib import Path

import lib_index as L

VERDICTS = ["supported", "contradicted", "contradicted_with_reason", "insufficient", "out_of_scope"]
ROLES = ["authoritative", "superseded", "duplicate", "supplementary", "unreadable", "unrelated", "unknown"]
OPS = ["rename", "move", "dedupe", "tag", "relink", "flag", "quarantine", "index", "repair"]


def num(s):
    return L.norm(s).lower()


def _disp(s):
    """Whitespace-only cleanup for display: never rewrites punctuation or quotes."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def locate_quote(doc_paras, quote):
    """Return locators whose paragraph contains the quote (normalized)."""
    q = L.norm(quote)
    if len(q) < 6:
        return []
    hits = [p["locator"] for p in doc_paras if q in L.norm(p["text"])]
    if hits:
        return hits
    ql = L.norm(quote, True)
    return [p["locator"] for p in doc_paras if ql and ql in L.norm(p["text"], True)]


def _draft_sections(draft):
    lib = draft.get("library") or {}
    docs = [d for d in (lib.get("documents") or []) if isinstance(d, dict)]
    return {
        "documents": docs,
        "families": [f for f in (lib.get("families") or []) if isinstance(f, dict)],
        "duplicates": [d for d in (lib.get("duplicates") or []) if isinstance(d, dict)],
        "actions": [a for a in (lib.get("repair_actions") or []) if isinstance(a, dict)],
        "questions": [q for q in (draft.get("questions") or []) if isinstance(q, dict)],
        "exhibits": [e for e in (draft.get("exhibits") or draft.get("evidence") or []) if isinstance(e, dict)],
        "witness": [w for w in (draft.get("version_witness") or []) if isinstance(w, dict)],
        "scope": draft.get("search_scope") or {},
        "conflicts": [c for c in (draft.get("conflicts") or []) if isinstance(c, dict)],
        "limitations": draft.get("limitations") or [],
        "uncertainty": draft.get("uncertainty") or [],
    }


def validate(draft, index):
    rep = {"errors": [], "warnings": [], "counts": {}}

    def err(code, detail, where=""):
        rep["errors"].append({"code": code, "detail": detail, "where": where})

    def warn(code, detail, where=""):
        rep["warnings"].append({"code": code, "detail": detail, "where": where})

    if not isinstance(draft, dict) or not draft:
        err("no_draft", "draft.json missing or empty: author %s" % "work/draft.json", "draft")
        rep["ok"] = False
        rep["counts"] = {"documents": len(index.get("docs") or {}), "exhibits": 0}
        return rep
    S = _draft_sections(draft)
    docs_i, paras, texts = index.get("docs") or {}, index.get("paras") or {}, index.get("texts") or {}
    dids = set(docs_i)
    if not S["exhibits"] and not S["questions"]:
        err("empty_draft_sections", "draft has neither exhibits nor questions", "draft")

    # ---- library side
    draft_versions = {}
    for d in S["documents"]:
        did = str(d.get("doc_id") or d.get("id") or "")
        if did and did not in dids:
            err("doc_unknown", "library.documents cites unknown doc_id %r" % did, "library.documents")
        if did:
            draft_versions[did] = str(d.get("version") or "")
            if str(d.get("role") or "") not in ROLES and d.get("role"):
                warn("role_unknown", "role %r not in enum %s" % (d.get("role"), "/".join(ROLES)), did)
    missing_docs = sorted(dids - {str(d.get("doc_id") or d.get("id") or "") for d in S["documents"]})
    if missing_docs and S["documents"]:
        warn("doc_not_classified", "%d input document(s) missing from library.documents: %s"
             % (len(missing_docs), ", ".join(missing_docs[:8])), "library.documents")

    # ---- exhibits: identity, verbatim quote, locator letter, version letter
    ex_by_id, quote_ok, loc_ok, unverified = {}, 0, 0, set()
    for e in S["exhibits"]:
        eid = str(e.get("exhibit_id") or e.get("id") or "")
        did = str(e.get("doc_id") or e.get("document_id") or "")
        q = e.get("quote") or e.get("text") or ""
        w = eid or "(no id)"
        if not eid:
            err("exhibit_missing_id", "exhibit without exhibit_id", "exhibits")
            continue
        if eid in ex_by_id:
            err("exhibit_duplicate_id", "duplicate exhibit_id %r" % eid, eid)
            continue
        ex_by_id[eid] = e
        if did not in dids:
            err("doc_unknown", "exhibit cites unknown doc_id %r" % did, eid)
            continue
        hits = locate_quote(paras.get(did) or [], q)
        if not L.norm(q) or not hits:
            err("quote_not_found", "quote not found verbatim in %s: %r" % (did, L.norm(q)[:80]), eid)
            unverified.add(eid)
            continue
        quote_ok += 1
        loc = str(e.get("locator") or e.get("paragraph_id") or e.get("page") or "")
        if not loc:
            err("locator_missing", "exhibit has no locator", eid)
        elif loc in hits:
            loc_ok += 1
        else:
            err("locator_mismatch", "claimed locator %r does not contain the quote; quote really occurs at %s"
                % (loc, ", ".join(hits[:3])), eid)
            unverified.add(eid)
        want = draft_versions.get(did) or (docs_i.get(did) or {}).get("version") or ""
        got = str(e.get("version") or "")
        if want and got and num(got) != num(want):
            err("version_mismatch", "exhibit version %r != registered version %r for %s" % (got, want, did), eid)

    # ---- issues and verdict/evidence pairing
    scope = S["scope"] if isinstance(S["scope"], dict) else {}
    idx_qs = {str(q.get("qid")): q for q in index.get("questions") or []}
    verdicts, cited, n_issues = {}, set(), 0
    seen_issues, quest_qids = set(), set()
    for q in S["questions"]:
        qid = str(q.get("qid") or "")
        quest_qids.add(qid)
        if qid and idx_qs and qid not in idx_qs:
            warn("qid_unknown", "qid %r not in input questions" % qid, qid)
        issues = [i for i in (q.get("issues") or []) if isinstance(i, dict)]
        if not issues:
            err("question_no_issues", "question has no issue (split it into 1-5 decidable issues)", qid or "?")
        sc = scope.get(qid) or scope.get(str(q.get("question") or "")[:80]) or {}
        for i in issues:
            n_issues += 1
            iid = str(i.get("issue_id") or "?")
            vd = num(i.get("verdict"))
            w = "%s/%s" % (qid or "?", iid)
            if iid in seen_issues:
                err("issue_duplicate_id", "duplicate issue_id %r" % iid, w)
            seen_issues.add(iid)
            if vd not in VERDICTS:
                err("verdict_invalid", "verdict %r not in %s" % (i.get("verdict"), "/".join(VERDICTS)), w)
                continue
            verdicts[vd] = verdicts.get(vd, 0) + 1
            pos = [str(x) for x in (i.get("positive_exhibits") or i.get("exhibits") or [])]
            cnt = [str(x) for x in (i.get("counter_exhibits") or [])]
            cited.update(pos + cnt)
            for x in pos + cnt:
                if x not in ex_by_id:
                    err("exhibit_undefined", "issue cites unregistered exhibit %r" % x, w)
            if vd in ("supported", "contradicted", "contradicted_with_reason") and not pos and not cnt:
                err("supported_without_evidence", "verdict %s but no exhibit cited" % vd, w)
            if vd == "contradicted" and not cnt:
                err("contradicted_without_counter", "contradicted needs >=1 counter exhibit", w)
            if vd == "contradicted_with_reason":
                if not cnt:
                    err("contradicted_without_counter", "contradicted_with_reason needs a counter exhibit", w)
                if len(L.norm(i.get("reasoning"))) < 20:
                    err("reasoning_thin", "state why one side wins (>=20 chars)", w)
            if vd == "supported" and cnt:
                err("counter_ignored", "counter exhibit present but verdict stays supported; use "
                                       "contradicted_with_reason and give reasoning", w)
            if vd in ("insufficient", "out_of_scope"):
                if not L.norm(i.get("missing_evidence")):
                    err("insufficient_no_scope", "missing_evidence is required (what evidence is absent)", w)
                files = sc.get("files") or []
                kws = sc.get("keywords") or []
                if not files or not kws:
                    err("insufficient_no_scope", "search_scope[%s] needs files[] and keywords[]" % qid, w)

    for qid, q in idx_qs.items():
        if S["questions"] and qid not in quest_qids:
            err("question_missing", "input question %s not handled in draft" % qid, qid)

    # ---- version witness
    for w in S["witness"]:
        for v in (w.get("versions") or []):
            for c in (v.get("claims") or []):
                ex = str(c.get("exhibit_id") or "")
                if ex:
                    cited.add(ex)
                    if ex not in ex_by_id:
                        err("exhibit_undefined", "version witness cites unregistered exhibit %r" % ex,
                            str(w.get("family_id") or "witness"))
        for c in (w.get("conflicts_between_versions") or []):
            if not L.norm(c.get("likely_cause")):
                warn("version_conflict_no_cause", "version conflict without likely_cause",
                     str(w.get("family_id") or "witness"))

    # ---- conflicts / actions
    for n, c in enumerate(S["conflicts"]):
        w = str(c.get("conflict_id") or "conflicts[%d]" % n)
        sides = [c.get("side_a") or {}, c.get("side_b") or {}]
        for s in sides:
            ex = str(s.get("exhibit_id") or "")
            if ex:
                cited.add(ex)
                if ex not in ex_by_id:
                    err("exhibit_undefined", "conflict cites unregistered exhibit %r" % ex, w)
        if not all((s.get("doc_id") or s.get("exhibit_id")) for s in sides):
            err("conflict_incomplete", "both sides need doc_id or exhibit_id", w)
    for n, a in enumerate(S["actions"]):
        w = str(a.get("action_id") or "actions[%d]" % n)
        if str(a.get("op") or "") not in OPS:
            warn("action_op_unknown", "op %r not in %s" % (a.get("op"), "/".join(OPS)), w)
        if str(a.get("target") or "") not in dids:
            err("doc_unknown", "repair action target %r not an input doc" % a.get("target"), w)
        for ex in (a.get("evidence") or []):
            cited.add(str(ex))
            if str(ex) not in ex_by_id:
                err("exhibit_undefined", "repair action cites unregistered exhibit %r" % ex, w)

    for eid, e in ex_by_id.items():
        if eid not in cited:
            warn("orphan_exhibit", "registered but never cited by an issue/conflict/witness/action", eid)
        if not str(e.get("kind") or ""):
            warn("exhibit_no_kind", "exhibit lacks kind (fact|number|method|conclusion|metadata|version_note)", eid)

    # ---- duplicates: claim must match hash/similarity evidence
    idx_dupes = index.get("duplicates") or []
    pairs = set()
    for g in idx_dupes:
        for d in [g.get("keep")] + list(g.get("drop") or []):
            for e in [g.get("keep")] + list(g.get("drop") or []):
                if d and e and d != e:
                    pairs.add((d, e))
    claimed = set()
    for n, g in enumerate(S["duplicates"]):
        keep, drop = str(g.get("keep") or ""), [str(x) for x in (g.get("drop") or [])]
        w = "duplicates[%d]" % n
        if keep not in dids or any(x not in dids for x in drop):
            err("doc_unknown", "duplicate group cites unknown doc(s) %s / %s" % (keep, drop), w)
            continue
        for x in drop:
            claimed.add((keep, x))
            if (keep, x) not in pairs:
                sh = L.text_shingles(texts.get(keep, ""))
                s = L.sim(sh, L.text_shingles(texts.get(x, "")))
                same_hash = docs_i.get(keep, {}).get("sha256") and docs_i[keep]["sha256"] == docs_i.get(x, {}).get("sha256")
                if not same_hash and s < 0.9:
                    err("dedupe_unsupported", "%s vs %s: hash differs and text similarity %.2f < 0.90" % (keep, x, s), w)
    for g in idx_dupes:
        keep, drop = g.get("keep"), (g.get("drop") or [])
        if drop and not all((keep, x) in claimed for x in drop):
            warn("unaddressed_duplicate", "duplicate group %s/%s not decided in library.duplicates"
                 % (keep, ",".join(drop)), "library.duplicates")

    # ---- unreadable documents must be declared
    roles = {str(d.get("doc_id") or ""): str(d.get("role") or "") for d in S["documents"]}
    blob = json.dumps({"deg": draft.get("degradations") or [], "lim": S["limitations"]}, ensure_ascii=False)
    for did, doc in docs_i.items():
        if doc.get("readable") is False or any("no_text_layer" in x for x in (doc.get("notes") or [])):
            if roles.get(did) != "unreadable" and did not in blob:
                warn("unreadable_unflagged", "%s is unreadable/no text layer but not declared" % did, did)

    # ---- numeric anchoring: numbers in an answer must exist in the cited quotes
    unanchored = []
    for q in S["questions"]:
        text = L.norm(q.get("answer_draft") or q.get("answer") or "")
        if not text:
            continue
        refs = set()
        for i in (q.get("issues") or []):
            refs.update(str(x) for x in (i.get("positive_exhibits") or []) + (i.get("counter_exhibits") or []))
        refs -= unverified
        corpus = " ".join(L.norm(ex_by_id[r].get("quote")) for r in refs if r in ex_by_id)
        for r in refs:
            did = str((ex_by_id.get(r) or {}).get("doc_id") or "")
            meta = next((d for d in S["documents"] if str(d.get("doc_id")) == did), {})
            corpus += " " + json.dumps(meta.get("metadata") or {}, ensure_ascii=False)
            corpus += " " + json.dumps((docs_i.get(did) or {}).get("meta_hint") or {}, ensure_ascii=False)
        digits = "".join(ch if ch.isdigit() else " " for ch in corpus)
        have = set(digits.split())
        for tok in re.findall(r"\d{2,}(?:\.\d+)?%?", text) + re.findall(r"\d+\.\d+", text):
            core = tok.rstrip("%").replace(",", "")
            if core not in have and core.replace(".", "") not in {h.replace(".", "") for h in have}:
                unanchored.append((str(q.get("qid")), tok))
    for qid, tok in unanchored[:12]:
        err("number_unanchored", "number %r in answer has no cited quote containing it" % tok, qid)

    total = max(len(ex_by_id), 1)
    rep["counts"] = {
        "documents": len(dids), "classified": len([d for d in S["documents"] if d.get("role")]),
        "questions": len(idx_qs) or len(S["questions"]), "questions_handled": len(quest_qids),
        "issues": n_issues, "exhibits": len(ex_by_id), "exhibits_cited": len(cited & set(ex_by_id)),
        "quote_verified": quote_ok, "locator_verified": loc_ok,
        "quote_pass_rate": round(quote_ok / total, 3), "locator_pass_rate": round(loc_ok / total, 3),
        "verdicts": verdicts,
        "insufficient": verdicts.get("insufficient", 0) + verdicts.get("out_of_scope", 0),
        "conflicts": len(S["conflicts"]), "duplicate_groups": len(S["duplicates"]),
        "repair_actions": len(S["actions"]), "families": len(index.get("families") or []),
        "coverage": round(len([q for q in S["questions"] if q.get("issues")]) / max(len(idx_qs) or len(S["questions"]), 1), 3),
    }
    rep["ok"] = not rep["errors"]
    return rep


# ------------------------------------------------------------------- rendering
def _e(s):
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def tbl(head, rows):
    out = ["| " + " | ".join(_e(h) for h in head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(_e(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _meta_join(m):
    if not isinstance(m, dict):
        return ""
    return "; ".join("%s=%s" % (k, v) for k, v in m.items() if v not in (None, "", [], {}))


def render(index, draft, out_dir, gen, status, errs, degr):
    """Write every artifact; returns (files, stats)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    S = _draft_sections(draft or {})
    docs_i, paras = index.get("docs") or {}, index.get("paras") or {}
    texts = index.get("texts") or {}
    dmap = {str(d.get("doc_id") or d.get("id") or ""): d for d in S["documents"]}
    fams = index.get("families") or []
    files = []

    # 1. library index (json + csv)
    rows = []
    for did in sorted(docs_i):
        d, dd = docs_i[did], dmap.get(did, {})
        rows.append({"doc_id": did, "file": d.get("filename"), "rel_path": d.get("rel_path", d.get("path")),
                     "kind": d.get("kind"), "bytes": d.get("size"), "sha256": d.get("sha256"),
                     "mode": d.get("mode"), "readable": d.get("readable"), "blocks": d.get("n_blocks"),
                     "paragraphs": d.get("n_paras"), "engine": d.get("engine"), "text_quality": d.get("quality"),
                     "family_id": d.get("family_id"), "version": dd.get("version") or "",
                     "version_rank": dd.get("version_rank") or d.get("version_rank"),
                     "role": dd.get("role") or ("unreadable" if d.get("readable") is False else "unknown"),
                     "title": dd.get("title") or (d.get("meta_hint") or {}).get("title_hint", ""),
                     "metadata": dd.get("metadata") or {}, "notes": dd.get("notes") or "; ".join(d.get("notes") or [])})
    (out / "library_index.json").write_text(json.dumps({"case_id": index.get("case_id"), "documents": rows,
                                                       "families": fams,
                                                       "duplicates": S["duplicates"] or index.get("duplicates") or []},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["doc_id", "file", "rel_path", "kind", "bytes", "sha256", "mode", "readable", "blocks",
            "paragraphs", "family_id", "version", "version_rank", "role", "title", "metadata", "notes"]
    with (out / "library_index.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([json.dumps(r[c], ensure_ascii=False) if isinstance(r.get(c), (dict, list)) else r.get(c, "")
                        for c in cols])
    files += ["library_index.json", "library_index.csv"]

    # 2. exhibit register
    reg = []
    for e in S["exhibits"]:
        did, q = str(e.get("doc_id") or ""), e.get("quote") or ""
        hits = locate_quote(paras.get(did) or [], q)
        reg.append({**e, "quote_verified": bool(hits),
                    "locator_verified": str(e.get("locator") or "") in hits,
                    "verified_locators": hits[:3]})
    (out / "exhibits").mkdir(parents=True, exist_ok=True)
    (out / "exhibits" / "exhibit_register.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in reg) + ("\n" if reg else ""), encoding="utf-8")
    files.append("exhibits/exhibit_register.jsonl")

    # 3. per-question dockets
    scope = S["scope"] if isinstance(S["scope"], dict) else {}
    docket_rows = []
    for q in S["questions"]:
        qid = str(q.get("qid") or "Q1")
        qdir = out / "dockets" / re.sub(r"[^0-9A-Za-z_.-]+", "_", qid)
        qdir.mkdir(parents=True, exist_ok=True)
        issues = [i for i in (q.get("issues") or []) if isinstance(i, dict)]
        (qdir / "issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1), encoding="utf-8")
        lines = ["# %s · %s" % (qid, q.get("question") or "(no question text)"), "",
                 "> case `%s` ｜ status **%s** ｜ %s" % (index.get("case_id") or "unknown", status, gen), "",
                 "## 答案（逐句带 [E#] 证据编号）", "", _disp(q.get("answer_draft") or q.get("answer") or "_未作答（见争点裁决与缺证说明）_"), "",
                 "## 争点裁决", "", tbl(["issue", "争点", "裁决", "支持证据", "反证", "理由"],
                                       [[i.get("issue_id"), i.get("issue_text"), i.get("verdict"),
                                         ", ".join(i.get("positive_exhibits") or []) or "—",
                                         ", ".join(i.get("counter_exhibits") or []) or "—",
                                         i.get("reasoning") or ""] for i in issues]) or "_无争点_", "",
                 "## 证据（逐字引文 + 定位）", ""]
        refs = []
        for i in issues:
            refs += [str(x) for x in (i.get("positive_exhibits") or []) + (i.get("counter_exhibits") or [])]
        by_id = {str(e.get("exhibit_id") or ""): e for e in S["exhibits"]}
        for r in list(dict.fromkeys(refs)):
            e = by_id.get(r)
            if not e:
                lines.append("- **%s** 未登记（悬空引用）" % r)
                continue
            lines.append("- **%s** [%s %s] `%s` %s — “%s”" % (
                r, e.get("doc_id"), e.get("version") or "?", e.get("locator") or "?",
                "反证" if L.norm(e.get("polarity")) == "counter" else "支持", _disp(e.get("quote"))[:400]))
        sc = scope.get(qid) or {}
        lines += ["", "## 检索范围", "",
                  "- 文件：%s" % (", ".join(sc.get("files") or []) or "（未记录）"),
                  "- 关键词：%s" % (", ".join(sc.get("keywords") or []) or "（未记录）"),
                  "- 同义词：%s" % (", ".join(sc.get("synonyms") or []) or "（未记录）"),
                  "- 扫描段落数：%s" % (sc.get("chunks_scanned") if sc.get("chunks_scanned") is not None else "（未记录）"),
                  "- 未见依据说明：%s" % (_disp(sc.get("not_found_note")) or "（无）"), "",
                  "## 缺证", ""]
        miss = [i for i in issues if L.norm(i.get("missing_evidence"))]
        lines += ["- **%s**：%s" % (i.get("issue_id"), _disp(i.get("missing_evidence"))) for i in miss] or ["- 无（争点均有证据或已声明范围）"]
        (qdir / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        files += ["dockets/%s/issues.json" % qdir.name, "dockets/%s/verdict.md" % qdir.name]
        docket_rows.append([qid, q.get("question"), len(issues),
                            ", ".join("%s=%s" % (i.get("issue_id"), i.get("verdict")) for i in issues) or "—"])

    # 4. version witness / conflicts / repair log / search scope
    witness = S["witness"]
    if not witness:
        for fam in fams:
            if len(fam.get("members") or []) > 1:
                witness.append({"family_id": fam.get("family_id"), "members": fam.get("members"),
                                "versions": [{"doc_id": m, "version": dmap.get(m, {}).get("version") or "",
                                              "claims": []} for m in fam.get("members") or []],
                                "conflicts_between_versions": [], "derived": "structure_only"})
    (out / "version_witness.json").write_text(json.dumps(witness, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "conflicts.json").write_text(json.dumps(S["conflicts"], ensure_ascii=False, indent=1), encoding="utf-8")
    actions = S["actions"]
    (out / "repair_log.json").write_text(json.dumps(
        {"case_id": index.get("case_id"), "actions": actions,
         "duplicates": S["duplicates"] or index.get("duplicates") or [],
         "unreadable": [d for d in docs_i if (docs_i[d].get("readable") is False)],
         "reversible": "所有动作均为记录（未改动原文件），可照 target/to 复跑"}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (out / "search_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=1), encoding="utf-8")
    files += ["version_witness.json", "conflicts.json", "repair_log.json", "search_scope.json"]

    # 5. main report
    kinds, depths = {}, {}
    for did, d in docs_i.items():
        kinds[d.get("kind")] = kinds.get(d.get("kind"), 0) + 1
        rp = d.get("rel_path") or d.get("filename") or ""
        depth = len([x for x in str(rp).split("/")[:-1] if x])
        depths[depth] = depths.get(depth, 0) + 1
    meta_filled = sum(1 for r in rows if _meta_join(r.get("metadata")))
    multi = [f for f in fams if len(f.get("members") or []) > 1]
    R = ["# 科研知识库整理与问答卷宗 · report", "",
         "> case `%s` ｜ status **%s** ｜ %s" % (index.get("case_id") or "unknown", status, gen), "",
         "## 1. 资料盘点（六维）", "",
         "### 1.1 文件类型与规模", "",
         tbl(["类型", "数量"], [[k, v] for k, v in sorted(kinds.items())]), "",
         "共 %d 个文件，%d 个段落可定位。" % (len(docs_i), sum(len(v) for v in paras.values())), "",
         "### 1.2 目录层级", "",
         tbl(["层级深度", "文件数"], [[k, v] for k, v in sorted(depths.items())]), "",
         "### 1.3 元数据字段（%d/%d 已填）" % (meta_filled, len(rows)), "",
         tbl(["doc_id", "文件", "标题", "元数据"], [[r["doc_id"], r["file"], (r.get("title") or "")[:60],
                                                  _meta_join(r.get("metadata")) or "—"] for r in rows]), "",
         "### 1.4 重复副本", "",
         tbl(["保留", "剔除", "依据"], [[g.get("keep"), ", ".join(g.get("drop") or []), g.get("basis")]
                                      for g in (S["duplicates"] or index.get("duplicates") or [])]) or "_无重复组_", "",
         "### 1.5 版本家族与差异", "",
         tbl(["家族", "成员", "权威版", "判定依据"],
             [[f.get("family_id"), ", ".join(f.get("members") or []), f.get("canonical_doc"),
               (f.get("basis") or "")[:120]] for f in fams]) or "_未识别版本家族_", "",
         "多成员家族 %d 个；版本间相反陈述见 `version_witness.json` / `conflicts.json`。" % len(multi), "",
         "### 1.6 权限与来源", "",
         tbl(["doc_id", "来源路径", "权限位", "可读", "引擎", "备注"],
             [[r["doc_id"], r.get("rel_path"), r.get("mode"), r.get("readable"), r.get("engine"),
               (r.get("notes") or "")[:80]] for r in rows]), "",
         "## 2. 问答卷宗", ""]
    if docket_rows:
        R += [tbl(["qid", "问题", "争点数", "争点裁决"], [[a, b, c, d] for a, b, c, d in docket_rows]), ""]
        for q in S["questions"]:
            qid = str(q.get("qid") or "Q1")
            R += ["### %s · %s" % (qid, q.get("question") or ""), "",
                  _disp(q.get("answer_draft") or q.get("answer") or "_未作答_"), "",
                  "详见 `dockets/%s/verdict.md`。" % re.sub(r"[^0-9A-Za-z_.-]+", "_", qid), ""]
    else:
        R += ["_本次运行未产出可裁决问答：工作稿缺失或未覆盖问题，见第 5 节缺口清单。_", "",
              "候选证据（未经裁决，供人工/Agent 复核）：", ""]
        for q in index.get("questions") or []:
            cands = L.search({k: {"paras": paras.get(k) or []} for k in paras}, q.get("question") or "", 4)
            R.append("- **%s** %s" % (q.get("qid"), q.get("question")))
            for c in cands:
                R.append("  - `%s` %s — “%s”" % (c["doc_id"], c["locator"], _disp(c["text"])[:160]))
        R.append("")
    R += ["## 3. 冲突（不取平均，分层报告）", "",
          tbl(["冲突", "主题", "A 方", "B 方", "可能原因", "处置"],
              [[c.get("conflict_id"), c.get("topic"),
                "%s %s" % ((c.get("side_a") or {}).get("doc_id"), (c.get("side_a") or {}).get("exhibit_id") or ""),
                "%s %s" % ((c.get("side_b") or {}).get("doc_id"), (c.get("side_b") or {}).get("exhibit_id") or ""),
                c.get("likely_cause"), c.get("handling")] for c in S["conflicts"]]) or "_未登记跨文档冲突_", "",
          "## 4. 整理与恢复操作记录", "",
          tbl(["动作", "op", "目标", "去向", "理由", "证据"],
              [[a.get("action_id"), a.get("op"), a.get("target"), a.get("to") or "—",
                (a.get("reason") or "")[:80], ", ".join(a.get("evidence") or []) or "—"]
               for a in actions]) or "_无动作记录_", "",
          "动作只记录、未改原文件；剔除项保留原位，可照 `target`/`to` 复跑。", "",
          "## 5. 覆盖、降级与缺口", ""]
    cnt = index.get("counts") or {}
    R += ["- 文档 %d；可定位段落 %d；版本家族 %d（多成员 %d）；重复组 %d" % (
              len(docs_i), sum(len(v) for v in paras.values()), len(fams), len(multi),
              len(S["duplicates"] or index.get("duplicates") or [])),
          "- 问题 %d；产出争点 %d；证据 %d；裁决分布 %s" % (
              len(index.get("questions") or []), sum(len(q.get("issues") or []) for q in S["questions"]),
              len(S["exhibits"]), json.dumps(cnt.get("verdicts") or {}, ensure_ascii=False)),
          "- 降级：%s" % ("; ".join(degr) if degr else "无"),
          "- 不确定：%s" % ("; ".join(S["uncertainty"]) if S["uncertainty"] else "见各争点 missing_evidence"),
          "- 限制：%s" % ("; ".join(S["limitations"]) if S["limitations"] else "见 SKILL.md 第 9 节"), "",
          "## 6. 复跑步骤", "",
          "```bash", "python3 -B scripts/main.py init", "python3 -B scripts/main.py show --query '<问题关键词>' --emit",
          "python3 -B scripts/main.py check", "python3 -B scripts/main.py build", "python3 -B scripts/main.py selfcheck", "```", ""]
    (out / "report.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    files.append("report.md")
    return files, {"documents": len(docs_i), "exhibits": len(reg), "issues": sum(len(q.get("issues") or []) for q in S["questions"]),
                   "questions": len(S["questions"]), "families": len(fams),
                   "duplicates": len(S["duplicates"] or index.get("duplicates") or [])}
