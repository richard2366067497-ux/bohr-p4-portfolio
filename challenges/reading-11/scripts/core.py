#!/usr/bin/env python3
"""litread-bench-ledger card layer: card normalisation, validation, 0/1/2 rule
scoring, calibration probes, pointer closure, coverage matrix, aggregates."""
import json
import re
from pathlib import Path

import litio as L
from litio import TT, NM, V, nm, now, pick, sha, verify

def _as_list(x):
    return [] if x is None else (x if isinstance(x, list) else [x])


def norm_ref(r):
    if isinstance(r, str):
        return {"material": None, "locator": None, "quote": nm(r), "native_id": None}
    if not isinstance(r, dict):
        return {"material": None, "locator": None, "quote": "", "native_id": None}
    return {"material": r.get("material") or r.get("mid") or r.get("material_id"),
            "locator": r.get("locator") or r.get("pid") or r.get("ref") or r.get("para"),
            "quote": nm(r.get("quote") or r.get("text") or r.get("excerpt") or ""),
            "native_id": r.get("native_id") or r.get("paragraph_id") or r.get("source_id")}


def norm_ans(a):
    if isinstance(a, str):
        return {"text": nm(a), "locator": None}
    if isinstance(a, dict):
        return {"text": nm(a.get("text") or a.get("answer") or a.get("value") or ""),
                "locator": a.get("locator") or a.get("ref") or a.get("pid")}
    return {"text": nm(str(a)), "locator": None}


def norm_item(raw, n):
    if not isinstance(raw, dict):
        raw = {"question": str(raw)}
    tt = str(pick(raw, "task_type", "type", "category", default="other")).lower()
    rule = pick(raw, "scoring_rule", "rubric", "grading_rule", default={})
    if isinstance(rule, list):
        terms, scale = [], {}
        for x in rule:
            if isinstance(x, dict):
                terms += [str(t) for t in _as_list(x.get("key_terms"))]
                if x.get("score") is not None:
                    scale[str(x["score"])] = nm(str(x.get("text") or x.get("rubric_id") or ""))
        rule = {"mode": "key_terms", "scale": scale, "key_terms": terms}
    rule = rule if isinstance(rule, dict) else {}
    scale = rule.get("scale") if isinstance(rule.get("scale"), dict) else {}
    terms = [nm(str(t)) for t in _as_list(rule.get("key_terms") or rule.get("keys")
                                          or rule.get("must_have_terms")) if nm(str(t))]
    ans = [norm_ans(a) for a in _as_list(pick(raw, "reference_answer", "reference", "gold",
                                             "answer", default=[]))]
    ans = [a for a in ans if a["text"]]
    return {"item_id": str(pick(raw, "item_id", "id", "qid", "card_id", "task_id",
                                default="Q%02d" % n)),
            "task_type": tt if tt in TT else "other",
            "question": nm(str(pick(raw, "question", "task", "prompt", "instruction", default=""))),
            "source_refs": [norm_ref(r) for r in _as_list(pick(
                raw, "source_refs", "sources", "material_refs", "evidence", "refs", default=[]))],
            "reference_answer": ans,
            "reference_missing": bool(raw.get("reference_missing")) or not ans,
            "scoring_rule": {"mode": str(rule.get("mode") or ("key_terms" if terms else "manual_only")),
                             "scale": {k: nm(str(v)) for k, v in scale.items()},
                             "key_terms": terms,
                             "must_have": rule.get("must_have") if isinstance(rule.get("must_have"), int) else 1},
            "difficulty": str(pick(raw, "difficulty", "level", default="unknown")),
            "license": str(pick(raw, "license", "rights", default="unknown")),
            "notes": nm(str(pick(raw, "notes", "note", "rationale", default=""))),
            "origin": raw.get("origin") or "draft"}


def validate(draft, c, wo=None, uncovered=None):
    issues, warns, items, rejected = [], [], [], []
    raw_items = _as_list(draft.get("items") if isinstance(draft, dict) else draft)
    seen = set()
    for n, raw in enumerate(raw_items, 1):
        it = norm_item(raw, n)
        iid, bad = it["item_id"], []
        if iid in seen:
            bad.append("duplicate item_id '%s'" % iid)
        seen.add(iid)
        if len(it["question"]) < 10:
            bad.append("question shorter than 10 chars")
        if not it["source_refs"]:
            bad.append("no source_refs")
        if it["reference_missing"] and it["reference_answer"]:
            bad.append("reference_missing=true but reference_answer is non-empty")
        ok_refs = []
        for ref in it["source_refs"]:
            mid = ref["material"]
            if not mid:
                hits = [k for k in c if verify(c, k, ref["quote"]).get("verified")]
                if len(hits) == 1:
                    mid = ref["material"] = hits[0]
                    warns.append({"item": iid, "msg": "material inferred as %s" % mid})
            v = verify(c, mid, ref["quote"]) if mid else {"verified": False,
                                                          "reason": "material_missing"}
            ref["_v"] = v
            if not v.get("verified"):
                warns.append({"item": iid, "msg": "quote not verified (%s): %s"
                              % (v.get("reason"), ref["quote"][:60])})
                continue
            ok_refs.append(ref)
            if ref["locator"] and v.get("pid") and nm(str(ref["locator"])) != v["pid"]:
                warns.append({"item": iid, "msg": "locator_mismatch: declared %s, quote is in %s"
                              % (ref["locator"], v["pid"])})
                ref["locator_declared"] = ref["locator"]
            ref["locator"] = v.get("pid") or ref["locator"]
            ref["native_id"] = ref.get("native_id") or v.get("native_id")
        it["_anchors_ok"] = bool(ok_refs)
        if not ok_refs:
            bad.append("no verbatim-verified anchor")
        rule = it["scoring_rule"]
        if rule["mode"] == "key_terms" and not rule["key_terms"]:
            bad.append("mode=key_terms but key_terms empty")
        if rule["mode"] not in ("key_terms", "numeric", "manual_only"):
            warns.append({"item": iid, "msg": "unknown scoring mode -> manual_only"})
            rule["mode"] = "manual_only"
        if rule["mode"] == "key_terms" and rule["key_terms"] and it["reference_answer"]:
            miss = [t for t in rule["key_terms"]
                    if not any(t.casefold() in a["text"].casefold() for a in it["reference_answer"])]
            if miss:
                warns.append({"item": iid, "msg": "key_terms absent from reference_answer: %s "
                              "(gold probe cannot reach 2)" % ", ".join(miss[:4])})
        if rule["mode"] == "key_terms" and not {"2", "1", "0"} <= set(rule["scale"]):
            warns.append({"item": iid, "msg": "scoring scale missing 0/1/2 wording"})
        if it["reference_missing"]:
            warns.append({"item": iid, "msg": "reference_missing: not scored, kept as "
                                              "'is it reported?' probe"})
        if bad:
            issues += [{"item": iid, "level": "error", "msg": m} for m in bad]
            rejected.append({"item_id": iid, "question": it["question"][:120], "reasons": bad})
        else:
            items.append(it)
    wo = wo or []
    covered = {it["item_id"] for it in items} | {r["item_id"] for r in rejected} | {
        str(x) for x in _as_list(uncovered) if x}
    wc = []
    for w in wo:
        wc.append({"item_id": w["item_id"], "covered": w["item_id"] in covered})
        if w["item_id"] not in covered:
            issues.append({"item": w["item_id"], "level": "error",
                           "msg": "workorder item has no card (list it in set_meta.uncovered)"})
    if not raw_items:
        issues.append({"item": "-", "level": "error", "msg": "draft has no items"})
    return {"items": items, "rejected": rejected, "issues": issues, "warnings": warns,
            "workorder_coverage": wc, "n_raw": len(raw_items)}


def fallback_items(idx, limit=6):
    """Deterministic minimal cards from real paragraphs when no usable draft exists."""
    out = []
    for m in idx.get("materials", []):
        for par in m.get("paragraphs", []):
            if len(out) >= limit:
                return out
            t = nm(par.get("text"))
            if len(t) < 80:
                continue
            sents = [x.strip() for x in re.split(r"(?<=[。！？.!?])\s*", t) if x.strip()] or [t]
            nums = re.findall(r"\d+(?:[.,]\d+)?\s?(?:%|mg|g|kg|mL|L|µM|mM|nM|nm|mm|cm|h|min|s|°C|K|d-1)", t)
            sent = next((s for s in sents if nums and nums[0] in s), sents[0])[:280]
            if len(sent) < 40:
                continue
            terms = [x for x in ([nums[0]] if nums else []) + [sents[0][:24]] if x and x in t]
            out.append({"item_id": "F%02d" % (len(out) + 1),
                        "task_type": "numeric" if nums else "extraction",
                        "question": ("材料 %s 的 %s 段出现数值 %s，请给出该句原文与出处。"
                                     % (m["name"], par["pid"], nums[0])) if nums else
                                    ("逐字摘录材料 %s 的 %s 段首句，并给出 material 与 locator。"
                                     % (m["name"], par["pid"])),
                        "source_refs": [{"material": m["mid"], "locator": par["pid"], "quote": sent}],
                        "reference_answer": [{"text": sent, "locator": par["pid"]}],
                        "reference_missing": False,
                        "scoring_rule": {"mode": "key_terms",
                                         "scale": {"2": "原文关键串全部命中", "1": "只命中部分关键串",
                                                   "0": "未命中或空答"},
                                         "key_terms": terms, "must_have": 1},
                        "difficulty": "easy", "license": "unknown",
                        "notes": "deterministic fallback card (no agent draft available)",
                        "origin": "fallback"})
    return out


def cov(terms, text):
    t = nm(text).casefold()
    ts = [nm(x).casefold() for x in (terms or []) if nm(x)]
    return round(sum(1 for x in ts if x in t) / len(ts), 3) if ts else 0.0


def score_answer(item, text):
    """0/1/2 by key-term coverage. Non-scorable states stay separate from 0."""
    rule = item.get("scoring_rule") or {}
    if item.get("reference_missing"):
        return {"score": None, "status": "missing_reference", "coverage": None,
                "basis": "no reference answer in card; not scored, no gold invented"}
    if not item.get("_anchors_ok"):
        return {"score": None, "status": "no_anchor", "coverage": None,
                "basis": "no verbatim-verified anchor; item is not judgeable"}
    if rule.get("mode") == "manual_only":
        return {"score": None, "status": "manual_review", "coverage": None,
                "basis": "manual_only rule; routed to human review"}
    t = nm(text)
    if not t:
        return {"score": 0, "status": "ok", "coverage": 0.0, "basis": "empty answer"}
    c = cov(rule.get("key_terms"), t)
    if c >= 0.75:
        return {"score": 2, "status": "ok", "coverage": c,
                "basis": "coverage %.2f >= 0.75 with verified anchor" % c}
    if c >= 0.25:
        return {"score": 1, "status": "ok", "coverage": c,
                "basis": "0.25 <= coverage %.2f < 0.75 (partial)" % c}
    return {"score": 0, "status": "ok", "coverage": c, "basis": "coverage %.2f < 0.25" % c}


def probe_answers(item):
    """gold / partial / empty probes plus the score each must receive."""
    gold = " ".join(a["text"] for a in item.get("reference_answer") or [])
    terms = (item.get("scoring_rule") or {}).get("key_terms") or []
    out = [{"probe": "gold", "answer": gold, "expected": 2},
           {"probe": "empty", "answer": "", "expected": 0}]
    n = len(terms)
    if n >= 2:
        k = max(1, -(-n // 4))
        if k < n:
            out.insert(1, {"probe": "partial", "answer": " ".join(terms[:k]), "expected": 1})
    return out


def resolve_ref(root, ref):
    """Resolve 'rel/path#/json/ptr' | 'rel#row=N' | 'rel#L3-L9'."""
    if not isinstance(ref, str) or not ref.strip():
        return False, "empty_ref"
    path, _, frag = ref.partition("#")
    p = Path(path) if Path(path).is_absolute() else Path(root) / path
    try:
        if not p.is_file():
            return False, "file_missing"
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return False, "unreadable:%s" % e
    if not frag:
        return True, "file"
    if frag.startswith("/"):
        try:
            cur = json.loads(text)
        except Exception:
            return False, "not_json"
        for tok in [t for t in frag.strip("/").split("/") if t]:
            tok = tok.replace("~1", "/").replace("~0", "~")
            if isinstance(cur, list):
                if not tok.lstrip("-").isdigit() or not (-len(cur) <= int(tok) < len(cur)):
                    return False, "ptr_index_out_of_range"
                cur = cur[int(tok)]
            elif isinstance(cur, dict):
                if tok not in cur:
                    return False, "ptr_key_missing"
                cur = cur[tok]
            else:
                return False, "ptr_into_scalar"
        return True, "json_pointer"
    if frag.startswith("row="):
        n = frag[4:].strip()
        if n.lstrip("-").isdigit() and 1 <= int(n) < len(text.splitlines()):
            return True, "csv_row"
        return False, "row_out_of_range"
    if frag.startswith("L"):
        m = re.match(r"L(\d+)(?:-L?(\d+))?$", frag)
        if not m:
            return False, "bad_line_fragment"
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        n = len(text.splitlines())
        return (1 <= a <= b <= n), ("line_range" if 1 <= a <= b <= n else "line_out_of_range")
    return False, "unknown_fragment"


def coverage_matrix(cards, rows, failures, version):
    def st(ok, tot):
        return "ok" if tot and ok == tot else ("partial" if ok else "missing")

    items, n = cards.get("items", []), len(cards.get("items", []))
    q_ok = sum(1 for i in items if len(i["question"]) >= 10)
    a_ok = sum(1 for i in items if i.get("reference_missing") or i.get("reference_answer"))
    meta_ok = bool(cards.get("set_version")) and bool(cards.get("license"))
    r_ok = sum(1 for i in items if i["scoring_rule"]["mode"] == "key_terms" and
               i["scoring_rule"]["key_terms"])
    raw_ok = sum(1 for r in rows if resolve_ref(L.OUTPUT, r["raw_output_ref"])[0])
    ax = {
        "task_definition": {"status": st(q_ok, n), "detail": "%d/%d judgeable questions" % (q_ok, n)},
        "data_answer_management": {"status": st(a_ok, n) if meta_ok else ("partial" if a_ok else "missing"),
                                   "detail": "%d/%d answer status; version+license=%s"
                                             % (a_ok, n, "yes" if meta_ok else "no")},
        "scoring_dimension": {"status": st(r_ok, n), "detail": "%d/%d machine-usable 0/1/2 rules"
                                                              % (r_ok, n)},
        "raw_output_retention": {"status": st(raw_ok, len(rows)),
                                 "detail": "%d/%d score rows resolve to a stored raw output"
                                           % (raw_ok, len(rows))},
        "error_analysis": {"status": "ok" if failures else ("partial" if n else "missing"),
                           "detail": "%d failure-library entries" % len(failures)},
        "version_iteration": {"status": "ok" if (version.get("current") or {}).get("listing")
                              and version.get("rules") else "partial",
                              "detail": "%d history, %d comparable, %d incomparable"
                                        % (len(version.get("history") or []),
                                           len(version.get("comparable") or []),
                                           len(version.get("incomparable") or []))},
    }
    v = list(ax.values())
    return {"axes": ax, "n_ok": sum(a["status"] == "ok" for a in v),
            "n_partial": sum(a["status"] == "partial" for a in v),
            "n_missing": sum(a["status"] == "missing" for a in v),
            "verdict": "ok" if all(a["status"] == "ok" for a in v) else (
                "partial" if not any(a["status"] == "missing" for a in v) else "gaps")}


def agg_rows(rows):
    scored = [r for r in rows if isinstance(r.get("score"), int)]
    n = len(scored)
    by = {}
    for r in rows:
        for key in ("agent", "item_type"):
            cell = by.setdefault(key, {}).setdefault(r.get(key) or "-",
                                                     {"n": 0, "sum": 0, "scored": 0})
            cell["n"] += 1
            if isinstance(r.get("score"), int):
                cell["sum"] += r["score"]
                cell["scored"] += 1
    for b in by.values():
        for cell in b.values():
            cell["mean"] = round(cell["sum"] / cell["scored"], 3) if cell["scored"] else None
    return {"n_rows": len(rows), "n_scored": n,
            "mean": round(sum(r["score"] for r in scored) / n, 3) if n else None,
            "distribution": {k: sum(1 for r in scored if r["score"] == k) for k in (2, 1, 0)},
            "judgeable_rate": round(n / len(rows), 3) if rows else 0.0,
            "by_agent": by.get("agent", {}), "by_type": by.get("item_type", {})}
