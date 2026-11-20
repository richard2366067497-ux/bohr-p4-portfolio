#!/usr/bin/env python3
"""main.py -- claim-evidence-verifier: `python3 scripts/main.py` (no arguments) runs everything:
init -> deterministic derivation -> optional agent draft merge -> artifacts -> result.json.
init/show/check/build remain available. Exit code is always 0 and a legal partial result.json
is written before any heavy work.
"""
import sys

sys.dont_write_bytecode = True                     # never leave __pycache__ inside the skill package

import argparse
import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E                                 # noqa: E402

VERSION = "2.0.0"
TYPES = ("fact", "comparison", "causal", "scope")
CONF = ("high", "medium", "low")
METHOD = [
    "claims are questions, never facts; claim text is never copied into a verdict slot",
    "each claim splits into atomic sub-claims (sentence / semicolon / conjunction), max 5",
    "retrieval = key-term overlap 0.72 + anchor-value match 0.28; ties by input order then unit id",
    "verdicts follow table R0..R6; contradicted needs a counter quote, supported a verified quote",
    "quotes are re-checked verbatim; failures degrade, nothing is invented; no match is never disproof",
    "deterministic: no random, no network, no clock in the decision path",
]

# 包内声明的默认契约键（case.json 未给 output_contract 时的兜底回填键，见 SKILL.md §1）
DECLARED_CONTRACT = ["case_id", "status", "result", "claims", "uncertainties",
                     "evidence", "sources", "counts", "changes", "self_check",
                     "rationale", "counter_evidence_searched", "readable", "minimal_sufficient"]
_PATHY_RE = re.compile(r"\.(md|markdown|json|jsonl|csv|tsv|txt|tex|bib|html?)$", re.IGNORECASE)


def _scrub_none(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return {k: _scrub_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_none(x) for x in value]
    return value


def _echo_value(out, key, value):
    """output_contract 的值：多行/像路径的字符串改成可回查的产物指针，写不出的留空，绝不编造。"""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return ""
    if "\n" in s or _PATHY_RE.search(s) or "/" in s:
        try:
            cand = Path(out) / s
            if cand.is_file():
                return s
        except Exception:
            pass
        return ""
    return value


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure(path, fallback):
    p = Path(path or fallback)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        alt = Path("/tmp/claim-verifier") / Path(str(p)).name
        alt.mkdir(parents=True, exist_ok=True)
        return alt


def wjson(path, obj):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:
        return False


def wtext(path, text):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        return True
    except Exception:
        return False


def context(args):
    inp = E.find_input(getattr(args, "input", None))
    work = ensure(getattr(args, "work", None), "/app/work")
    out = ensure(getattr(args, "output", None), "/app/output")
    case, cpath, cerr = E.load_case(inp)
    claims, corigin, cnotes = E.load_claims(inp, case)
    idx = E.build_index(inp, skip=[cpath, corigin])
    errors = list(cnotes)
    if cerr:
        errors.append({"stage": "input", "issue": "case_json_unreadable", "detail": cerr})
    units = idx["units"]
    return {"inp": inp, "work": work, "out": out, "case": case, "case_path": cpath,
            "case_id": E.case_id_of(case, cpath, inp), "claims": claims, "claims_origin": corigin,
            "index": idx, "units": units, "sources": idx["sources"], "gaps": idx["gaps"], "errors": errors,
            "umap": {u["unit_id"]: u for u in units}, "query_log": [],
            "full": {s["source_id"]: " ".join(u["text"] for u in units if u["source_id"] == s["source_id"])
                     for s in idx["sources"]}}


def shell(ctx, status="partial"):
    return {"case_id": ctx["case_id"], "status": status, "summary": {"claims": len(ctx["claims"])},
            "result": {"task": "literature_evidence_verification", "claims": []},
            "claims": [], "counts": {}, "evidence": [], "sources": ctx["sources"], "uncertainties": [],
            "assumptions": [], "errors": list(ctx["errors"]), "degradations": list(ctx["index"]["degradations"]), "pending_human": [], "query_log": [], "method_notes": METHOD,
            "artifacts": {}, "self_check": {"passed": None, "stage": "shell"}, "changes": [], "runtime": {}}


def runtime(ctx, hist):
    return {"skill": "claim-evidence-verifier", "version": VERSION,
            "input_dir": str(ctx["inp"]), "work_dir": str(ctx["work"]), "output_dir": str(ctx["out"]),
            "case_file": ctx["case_path"], "claims_source": ctx["claims_origin"],
            "claims": len(ctx["claims"]), "corpus_units": len(ctx["units"]), "commands": hist[-8:],
            "deterministic": True, "no_network": True, "model_requests": 0, "seconds_soft_cap": 780,
            "notes": "stdlib only; no model or network calls"}


CKMAP = (("case_id", "case_id"), ("case", "case_id"), ("status", "status"), ("claim", "claims"),
         ("verdict", "claims"), ("evidence", "evidence"), ("quote", "evidence"), ("card", "evidence"),
         ("source", "sources"), ("doc", "sources"), ("summary", "counts"), ("answer", "claims"),
         ("count", "counts"),
         ("coverage", "counts"), ("stat", "counts"), ("uncertain", "uncertainties"), ("limit", "uncertainties"),
         ("conflict", "uncertainties"), ("assumption", "assumptions"), ("method", "method_notes"),
         ("rule", "method_notes"), ("query", "query_log"), ("log", "query_log"), ("error", "errors"),
         ("degrad", "degradations"), ("pending", "pending_human"), ("human", "pending_human"),
         ("artifact", "artifacts"), ("self", "self_check"), ("quality", "self_check"),
         ("runtime", "runtime"), ("change", "changes"), ("task", "result"))


def contract_keys(case):
    for k in ("output_contract", "output_schema", "result_contract", "required_output", "contract"):
        oc = case.get(k) if isinstance(case, dict) else None
        if isinstance(oc, dict) and oc:
            return [(str(x), oc[x]) for x in oc]
        if isinstance(oc, list) and oc:
            return [(str(x), None) for x in oc]
    return [(k, None) for k in ("case_id", "status", "claims", "evidence", "sources", "uncertainties")]


def echo_contract(case, payload):
    """Every output_contract key is echoed verbatim at top level; unknown keys are filled, never dropped."""
    env, missing = {}, []
    for key, hint in contract_keys(case):
        if payload.get(key) is not None:
            env[key] = payload[key]
            continue
        val = next((payload[f] for w, f in CKMAP if w in key.lower() and payload.get(f) is not None), None)
        env[key] = val
        if val is None:
            missing.append({"stage": "contract", "issue": "contract_field_filled_empty", "field": key})
    for k, v in payload.items():
        env.setdefault(k, v)
    return env, missing


def with_output_contract(ctx, env):
    """逐键显式回填 output_contract：case 契约键 ∪ 包内声明键，全部保留、绝不删键。"""
    keys = [k for k, _ in contract_keys(ctx["case"])]
    for d in DECLARED_CONTRACT:
        if d not in keys:
            keys.append(d)
    env = _scrub_none(env)
    # 契约里出现但本条产线未单列的字段：给出与材料一致的真实值，不编造
    for k, v in (("rationale", "四级判定 R0..R6；每条子判断的 verdict_basis 即判定理由"),
                 ("counter_evidence_searched", "对每个子判断检索对立引文；无对立引文时不判 contradicted"),
                 ("minimal_sufficient", "evidence[].role=minimal_sufficient 表示最小充分引文")):
        if k in keys and not env.get(k):
            env[k] = v
    if "readable" in keys and not env.get("readable"):
        srcs = env.get("sources") or []
        if isinstance(srcs, list):
            env["readable"] = {"readable_sources":
                               sum(1 for s in srcs if isinstance(s, dict) and s.get("readable")),
                               "total_sources": len(srcs)}
    oc = dict((k, _echo_value(ctx["out"], k, env.get(k))) for k in keys)
    env["output_contract"] = _scrub_none(oc)
    for k in keys:
        env.setdefault(k, "")
    return env


def finalize(ctx, payload, hist):
    payload["runtime"] = runtime(ctx, hist)
    env, missing = echo_contract(ctx["case"], payload)
    if missing:
        env["degradations"] = list(env.get("degradations") or []) + missing
    env.setdefault("case_id", ctx["case_id"])
    env.setdefault("status", payload.get("status", "partial"))
    if not env.get("case_id"):
        env["case_id"] = ctx["case_id"] or "UNKNOWN-CASE"
    env = with_output_contract(ctx, env)
    wjson(ctx["out"] / "result.json", env)
    return env


def read_draft(work):
    for name in ("draft.json", "claims-draft.json"):
        p = Path(work) / name
        if p.is_file():
            obj, err = E.load_json(p)
            return (obj, str(p), None) if isinstance(obj, dict) else (None, str(p), err or "root not an object")
    return None, None, None


def apply_draft(claims, draft, ctx):
    notes, used, rejected = [], 0, 0
    if not isinstance(draft, dict):
        return claims, notes
    by_id = {str(e["claim_id"]).strip(): e for e in draft.get("claims") or []
             if isinstance(e, dict) and str(e.get("claim_id") or "").strip()}
    for idx, c in enumerate(claims):
        e = by_id.get(c["claim_id"])
        if not e:
            continue
        subs = []
        for j, s in enumerate(e.get("sub_claims") or [], 1):
            if not isinstance(s, dict) or s.get("verdict") not in E.VERDICTS:
                rejected += 1
                continue
            evs = []
            for x in s.get("evidence") or []:
                if not isinstance(x, dict):
                    continue
                q, unit = E.soft(x.get("quote") or ""), ctx["umap"].get(x.get("unit_id"))
                if not E.verify_quote(q, unit, ctx["full"].get((unit or {}).get("source_id"), ""))["verified"]:
                    rejected += 1
                    continue
                evs.append({"source_id": x.get("source_id") or unit["source_id"], "unit_id": unit["unit_id"],
                            "locator": x.get("locator") or unit["locator"], "quote": q, "score": 1.0,
                            "supports": bool(x.get("supports", True)),
                            "role": x.get("role") or "minimal_sufficient", "verified": True})
            if s["verdict"] in ("supported", "partially_supported") and not evs:
                rejected += 1
                continue
            subs.append({"sub_id": s.get("sub_id") or "%s.%d" % (c["claim_id"], j),
                         "text": E.soft(s.get("text") or c["claim_text"]),
                         "type": s.get("type") if s.get("type") in TYPES else "fact",
                         "required_evidence_type": E.soft(s.get("required_evidence_type") or ""),
                         "verdict": s["verdict"],
                         "verdict_confidence": s.get("verdict_confidence") if s.get("verdict_confidence") in CONF
                         else "medium", "rule_id": "DRAFT",
                         "verdict_basis": E.soft(s.get("rationale") or "agent-supplied judgement"),
                         "evidence": evs, "rationale": E.soft(s.get("rationale") or ""),
                         "limitations": [str(v) for v in (s.get("limitations") or [])]})
        if not subs:
            continue
        claims[idx] = dict(c, sub_claims=subs, verdict=E.aggregate([s["verdict"] for s in subs]),
                           status="verified+draft",
                           verdict_confidence=e.get("verdict_confidence")
                           if e.get("verdict_confidence") in CONF else "medium")
        used += 1
    if used or rejected:
        notes.append({"stage": "draft", "issue": "draft_merged",
                      "detail": "claims overridden=%d, evidence items rejected=%d" % (used, rejected)})
    return claims, notes


def template(ctx):
    return {"schema": "claim-evidence-draft/2", "case_id": ctx["case_id"],
            "note": "OPTIONAL: verdicts must come from text you read, quotes verbatim; see references/.",
            "claims": [{"claim_id": c["claim_id"], "claim_text": c["claim_text"], "sub_claims": []}
                       for c in ctx["claims"]]}


def counts_of(claims, ctx):
    subs = [s for c in claims for s in c["sub_claims"]]
    cnt = {"claims": len(claims), "sub_claims": len(subs), "sources": len(ctx["sources"]),
           "corpus_units": len(ctx["units"]),
           "evidence_items": sum(len(s["evidence"]) for s in subs),
           "verified_quotes": sum(1 for s in subs for e in s["evidence"] if e.get("verified")),
           "claims_with_conflict": sum(1 for c in claims if c["conflict"]["present"])}
    for v in E.VERDICTS:
        cnt[v] = sum(1 for s in subs if s["verdict"] == v)
        cnt["claims_" + v] = sum(1 for c in claims if c["verdict"] == v)
    return cnt


def evidence_rows(claims):
    keys = ("source_id", "unit_id", "locator", "quote", "score", "role", "supports")
    return [{"claim_id": c["claim_id"], "claim_text": c["claim_text"], "sub_id": s["sub_id"], "type": s["type"],
             "text": s["text"], "verdict": s["verdict"], "verdict_confidence": s["verdict_confidence"],
             "rule_id": s["rule_id"], "verdict_basis": s["verdict_basis"], "rationale": s["rationale"],
             "limitations": s["limitations"], "evidence": [{k: e[k] for k in keys} for e in s["evidence"]]}
            for c in claims for s in c["sub_claims"]]


def report_md(payload):
    claims = payload.get("claims") or []
    n = payload.get("counts") or {}
    out = ["# Claim verification report", "",
           "- case_id `%s` · status `%s` · claims %d · sub-claims %d · units %d · sources %d"
           % (payload.get("case_id"), payload.get("status"), n.get("claims", 0), n.get("sub_claims", 0),
              n.get("corpus_units", 0), n.get("sources", 0)),
           "- sub-claim verdicts: supported %d | partial %d | contradicted %d | insufficient %d"
           % (n.get("supported", 0), n.get("partially_supported", 0), n.get("contradicted", 0),
              n.get("insufficient_evidence", 0)),
           "- aggregation: %s" % E.AGG_RULE, "",
           "Locators are `FILE#pN` (N = PDF page when reported, else block ordinal). Every quote was "
           "re-checked verbatim against its unit: `verified: true` means it is a substring of that unit.", "",
           "", "## Per-claim findings", ""]
    for c in claims:
        out += ["### %s — %s" % (c["claim_id"], c["verdict"]), "", "> %s" % c["claim_text"], ""]
        for s in c["sub_claims"]:
            out += ["**%s [%s] → %s** (%s, %s)" % (s["sub_id"], s["type"], s["verdict"],
                                                   s["verdict_confidence"], s["rule_id"]),
                    "- %s" % s["text"], "- %s" % s["verdict_basis"]]
            out += ["- evidence [%s, verified=%s, score=%.2f] `%s`: \"%s\""
                    % (e["role"], e["verified"], e["score"], e["locator"], e["quote"]) for e in s["evidence"]]
            if not s["evidence"]:
                out.append("- evidence: no supporting quote found (searched %d units; %s)"
                           % (s.get("search_scope", {}).get("units_scanned", 0),
                              ", ".join(s["limitations"]) or "no lexical candidate"))
            if s["limitations"]:
                out.append("- limits: %s" % "; ".join(s["limitations"]))
            out.append("")
        if c["conflict"]["present"]:
            out.append("**Conflict — both sides verbatim**")
            out += ["- `%s`: \"%s\"" % (x.get("locator"), x.get("quote")) for x in c["conflict"]["both_sides"]]
            out.append("")
    out += ["## Uncertainty", ""]
    unc = payload.get("uncertainties") or []
    out += ["- %s → %s" % (u.get("issue"), u.get("next_step") or u.get("detail") or "") for u in unc]
    if not unc:
        out.append("- no additional uncertainty beyond the per-sub-claim limitations above.")
    out += ["", "## Limits", "",
            "- Lexical overlap, anchor values and direction cues are not peer review and not entailment; shared "
            "wording about another cohort/dose/endpoint surfaces as `partially_supported`, needing a re-read.",
            "- `insufficient_evidence` = no matching passage in this corpus, not disproof.",
            "", "Reproduce: `python3 scripts/main.py`; same input gives identical verdicts."]
    return "\n".join(out) + "\n"


def self_check(payload, ctx, keys):
    issues = [{"code": "E-601", "message": "contract key missing: %s" % k} for k in keys if k not in payload]
    claims = payload.get("claims") or []
    subs = [s for c in claims for s in c["sub_claims"]]
    if len(claims) != len(ctx["claims"]):
        issues.append({"code": "E-102", "message": "verifications %d != input claims %d"
                       % (len(claims), len(ctx["claims"]))})
    for s in subs:
        sid, v, ev = s["sub_id"], s["verdict"], s["evidence"]
        if v not in E.VERDICTS:
            issues.append({"code": "E-204", "message": "verdict out of set: " + sid})
        if v in ("supported", "partially_supported") and not any(e["verified"] for e in ev):
            issues.append({"code": "E-301", "message": "no verified evidence: " + sid})
        if v == "contradicted" and not any(not e["supports"] for e in ev):
            issues.append({"code": "E-304", "message": "no counter evidence: " + sid})
        if any(not e.get("locator") or not e.get("quote") for e in ev):
            issues.append({"code": "E-302", "message": "missing locator/quote: " + sid})
    unverified = sum(1 for s in subs for e in s["evidence"] if not e.get("verified"))
    if unverified:
        issues.append({"code": "E-302", "message": "%d unverified quotes" % unverified})
    return {"passed": not issues, "issues": issues[:40],
            "checked": {"claims": len(claims), "sub_claims": len(subs), "unverified_quotes": unverified}}


def compose(ctx, claims, draft_notes, hist):
    counts = counts_of(claims, ctx)
    degr = list(ctx["index"]["degradations"]) + draft_notes
    pending, unc = [], []
    for c in claims:
        for s in c["sub_claims"]:
            if s["verdict"] == "insufficient_evidence":
                unc.append({"claim_id": c["claim_id"], "sub_id": s["sub_id"],
                            "issue": "no sufficient evidence in the supplied corpus",
                            "next_step": "read the range by hand or add the missing source",
                            "search_scope": s.get("search_scope")})
            elif s["verdict"] == "partially_supported":
                unc.append({"claim_id": c["claim_id"], "sub_id": s["sub_id"],
                            "issue": "; ".join(s["limitations"]) or "partial alignment",
                            "next_step": "check comparator, values and conditions against the quote"})
        if c["conflict"]["present"]:
            unc.append({"claim_id": c["claim_id"], "issue": "cross-source conflict, unresolved",
                        "next_step": "the quoted passages disagree; adjudicate on the full texts"})
    if not unc:
        unc.append({"claim_id": "", "sub_id": "",
                    "issue": "no residual uncertainty: every sub-claim resolved or answered from the corpus",
                    "next_step": "spot-check a verdict against the quoted passage if a second reader is available"})
    if not ctx["claims"]:
        pending.append({"action": "provide a claims list", "reason": "no claim-shaped input found",
                        "expected": "claims-to-verify.json -> [{claim_id, claim_text}]"})
    if not ctx["units"]:
        pending.append({"action": "provide readable material", "reason": "no text unit extracted",
                        "expected": "input/** pdf|md|txt|json|csv"})
    pending += [{"action": "OCR or re-supply " + s["file"], "reason": s["extraction"]}
                for s in ctx["sources"] if not s.get("readable")]
    unver = sum(1 for c in claims for s in c["sub_claims"] for e in s["evidence"] if not e.get("verified"))
    if unver:
        degr.append({"stage": "evidence", "issue": "quote_unverified",
                     "detail": "%d quote(s) failed the verbatim re-check" % unver})
    status = ("input_error" if (not ctx["claims"] or not ctx["units"]) else
              "partial" if (degr or unver or
                            any(c["verdict"] == "insufficient_evidence" for c in claims)) else "answered")
    return {"case_id": ctx["case_id"], "status": status,
            "result": {"task": "literature_evidence_verification", "aggregation_rule": E.AGG_RULE,
                       "method": {"levels": list(E.VERDICTS), "rules": "R0..R6", "deterministic": True,
                                  "no_network": True, "agent_draft": bool(draft_notes)}},
            "claims": claims, "counts": counts, "evidence": evidence_rows(claims),
            "sources": ctx["sources"], "uncertainties": unc,
            "assumptions": ["the claim list is a set of questions, not established facts",
                            "locator = FILE#pN; N is the page when pages are reported, else the block ordinal",
                            "lexical overlap is a retrieval heuristic, not semantic entailment"],
            "errors": list(ctx["errors"]), "degradations": degr, "gaps": ctx["gaps"],
            "pending_human": pending, "query_log": ctx["query_log"], "method_notes": METHOD,
            "artifacts": {"result_json": "result.json", "evidence_cards": "evidence_cards.jsonl",
                          "report": "verification_report.md"},
            "self_check": {"passed": None}, "changes": hist}


def index_doc(ctx):
    return {"schema": "claim-evidence-index/2", "case_id": ctx["case_id"], "input": str(ctx["inp"]),
            "claims_source": ctx["claims_origin"], "claims": ctx["claims"], "sources": ctx["sources"],
            "units": [{k: u[k] for k in ("unit_id", "source_id", "locator", "page", "section", "text")}
                      for u in ctx["units"]], "gaps": ctx["gaps"]}


def pipeline(ctx, hist):
    wjson(ctx["work"] / "index.json", index_doc(ctx))
    finalize(ctx, shell(ctx), hist)                    # legal partial first, always
    claims = E.verify_all(ctx)
    draft, dpath, derr = read_draft(ctx["work"])
    notes = []
    if derr:
        ctx["errors"].append({"stage": "draft", "issue": "draft_unreadable", "detail": derr,
                              "action": "deterministic verdicts used instead"})
    if draft:
        claims, notes = apply_draft(claims, draft, ctx)
    payload = compose(ctx, claims, notes, hist)
    payload["runtime"] = runtime(ctx, hist)
    env, missing = echo_contract(ctx["case"], payload)
    if missing:
        env["degradations"] = list(env.get("degradations") or []) + missing
    env["self_check"] = self_check(env, ctx, [k for k, _ in contract_keys(ctx["case"])])
    env = with_output_contract(ctx, env)
    wjson(ctx["out"] / "result.json", env)
    wtext(ctx["out"] / "evidence_cards.jsonl",
          "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in evidence_rows(claims)))
    wtext(ctx["out"] / "verification_report.md", report_md(env))
    wjson(ctx["work"] / "draft.template.json", template(ctx))
    return env


def cmd_run(args):
    ctx = context(args)
    env = pipeline(ctx, [{"at": now(), "command": args.command, "status": "run"}])
    c = env.get("counts") or {}
    print("[run] %s | case=%s claims=%d sub_claims=%d units=%d sources=%d"
          % (ctx["inp"], env.get("case_id"), c.get("claims", 0), c.get("sub_claims", 0),
             c.get("corpus_units", 0), c.get("sources", 0)))
    print("[run] supported=%d partial=%d contradicted=%d insufficient=%d | quotes=%d/%d | status=%s | self_check=%s"
          % (c.get("supported", 0), c.get("partially_supported", 0), c.get("contradicted", 0),
             c.get("insufficient_evidence", 0), c.get("verified_quotes", 0), c.get("evidence_items", 0),
             env.get("status"), (env.get("self_check") or {}).get("passed")))
    for d in (env.get("degradations") or [])[:4]:
        print("  degrade %s: %s" % (d.get("issue"), d.get("detail") or d.get("field")))
    return 0


def cmd_init(args):
    ctx = context(args)
    env = finalize(ctx, shell(ctx), [{"at": now(), "command": "init", "status": "partial"}])
    wjson(ctx["work"] / "index.json", index_doc(ctx))
    wjson(ctx["work"] / "draft.template.json", template(ctx))
    print("[init] case_id=%s claims=%d units=%d sources=%d status=%s"
          % (ctx["case_id"], len(ctx["claims"]), len(ctx["units"]), len(ctx["sources"]), env["status"]))
    for s in ctx["sources"]:
        print("  %s %s %s units=%d %s" % (s["source_id"], s["file"], s["format"], s["units"], s["extraction"]))
    return 0


def cmd_show(args):
    ctx = context(args)
    print("=== %s : %d claims, %d units ===" % (ctx["case_id"], len(ctx["claims"]), len(ctx["units"])))
    for c in ctx["claims"]:
        print("[%s] %s" % (c["claim_id"], c["claim_text"]))
        for r in E.candidates(E.profile(c["claim_text"]), ctx["units"], 3, c.get("source_hint")):
            print("  %s %.2f %s" % (r["unit"]["unit_id"], r["score"], r["unit"]["locator"]))
            print("     %s" % E.soft(r["quote"])[:300])
    return 0


def cmd_check(args):
    ctx = context(args)
    draft, dpath, derr = read_draft(ctx["work"])
    if derr or not draft:
        print("[check] no usable draft (%s); rules do not need one" % (derr or "absent"))
        return 0
    claims, notes = apply_draft(E.verify_all(ctx), draft, ctx)
    print("[check] %s accepted=%d" % (dpath, sum(1 for c in claims for s in c["sub_claims"]
                                                 if s["rule_id"] == "DRAFT")))
    for n in notes:
        print("  %s: %s" % (n.get("issue"), n.get("detail")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="claim-evidence-verifier (no args = full run)")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "init", "show", "check", "build"])
    ap.add_argument("--input", default=None, help="/input")
    ap.add_argument("--work", default=None, help="/app/work")
    ap.add_argument("--output", default=None, help="/app/output")
    args = ap.parse_args(argv)
    try:
        {"run": cmd_run, "build": cmd_run, "init": cmd_init,
         "show": cmd_show, "check": cmd_check}[args.command](args)
    except Exception as exc:                            # never crash without an artifact
        try:
            ctx = context(args)
            payload = shell(ctx)
            payload["errors"].append({"stage": "run", "issue": "unhandled",
                                      "detail": "%s: %s" % (type(exc).__name__, exc),
                                      "action": traceback.format_exc(limit=3)})
            finalize(ctx, payload, [])
            print("[fatal] %s -> wrote a legal partial result.json" % type(exc).__name__)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
