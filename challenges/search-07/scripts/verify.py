#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py :: shared computation + `check` / `selfcheck` commands (imported by main.py)."""
import json
import time
import traceback
from pathlib import Path

import audit as AB
import ledger as LG

V = "1.0.0"
NAME = "search-coverage-gap-auditor"
T0 = time.time()
PRODUCTS = ("scope_card.md", "hit_ledger.csv", "gap_matrix.csv", "gap_atlas.json",
            "supplement_plan.md", "coverage_report.md", "audit_trail.json")


def jload(p):
    try:
        return json.loads(Path(p).read_text("utf-8", "replace"))
    except Exception:
        return None


def jdump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ computation
def policy_of(st, draft, cli):
    p = cli or ((draft.get("scope") or {}).get("denominator_policy") if isinstance(draft.get("scope"), dict) else None)
    return p if p in AB.POLICIES else "dedup_exclude_unavailable"


def compute(st, draft, policy):
    rows = AB.build_rows(st["refs"], st.get("auto") or {}, draft or {})
    cov = AB.coverage(st["refs"], rows, policy)
    cx = AB.qctx(st["queries"])
    gaps, miss = AB.build_gaps(st["refs"], rows, cx, draft or {}, st["notes"]["degradations"], cov)
    clusters = AB.cluster(gaps)
    cx["gaps"] = gaps
    sup = AB.eval_supplement((draft or {}).get("supplement") or [], st["refs"], rows,
                             st["pool"], cov, cx)
    return {"rows": rows, "cov": cov, "variants": AB.coverage_variants(st["refs"], rows),
            "gaps": gaps, "miss": miss, "clusters": clusters, "sup": sup, "cx": cx}


def doc_texts(st, inp, need):
    out = {}
    for m in st.get("docs_meta") or []:
        if need and m["doc_id"] not in need:
            continue
        p = Path(inp) / m["path"]
        try:
            out[m["doc_id"]] = LG.read_doc(p, [])
        except Exception:
            pass
    return out


def quote_stats(st, inp, computed):
    need, ev = set(), []
    for r in computed["rows"]:
        if r.get("evidence_locator"):
            need.add(r["evidence_locator"].split(":")[0])
            ev.append((r["ref_id"], r["evidence_locator"], r["evidence_quote"]))
    for g in computed["gaps"]:
        for e in g["evidence"]:
            if e.get("doc_id") and e.get("quote"):
                need.add(e["doc_id"])
                ev.append((g["category"], e.get("locator") or e["doc_id"], e["quote"]))
    texts = doc_texts(st, inp, need)
    ok, bad = 0, []
    for who, loc, q in ev:
        t = texts.get((loc or "").split(":")[0], "") or ""
        qq = " ".join(str(q or "").split())
        probe = qq[:60]
        if qq and (qq in " ".join(t.split()) or (probe and probe in " ".join(t.split()))):
            ok += 1
        else:
            bad.append({"item": who, "locator": loc, "quote": LG.clip(q, 80)})
    return {"checked": len(ev), "found": ok, "missing": len(bad),
            "rate": round(ok / len(ev), 4) if ev else None, "missing_items": bad[:20]}


# ------------------------------------------------------------------------- init
def cmd_check(a, st, out, inp):
    work = Path(st["paths"]["work"])
    draft = jload(work / "draft.json")
    if not isinstance(draft, dict):
        draft = {}
        print("[check] WARN draft.json 缺失或不可解析：当前只能按脚本默认值演练（build 会降级输出）")
    policy = policy_of(st, draft, a.policy)
    c = compute(st, draft, policy)
    cov, rows = c["cov"], c["rows"]
    qs = quote_stats(st, inp, c)
    lines, report = [], []

    def rec(name, ok, detail, warn=False):
        tag = "PASS" if ok else ("WARN" if warn else "FAIL")
        lines.append((tag, name, detail))
        report.append({"check": name, "status": tag, "detail": detail})

    contract = st.get("contract") or {}
    res = jload(out / "result.json") or {}
    missing = [k for k in contract if k not in res]
    rec("contract_keys", not missing, "output_contract %d 键；result.json 缺失 %s" % (len(contract), missing or "无"))

    agent = {str(d.get("ref_id")) for d in (draft.get("hit_decisions") or []) if isinstance(d, dict)}
    allref = {r["ref_id"] for r in st["refs"]}
    dangling = sorted(agent - allref)
    rec("ledger_rows", bool(draft) and not dangling and allref.issubset(agent),
        "工作稿覆盖 %d/%d 条参考集；悬空 ref_id=%s" % (len(agent & allref), len(allref), dangling or "无"),
        warn=bool(draft) and not dangling and bool(allref - agent))

    miss_ids = set(cov["missed_ids"])
    gap_ids = {x for g in c["gaps"] for x in g["ref_ids"]}
    unc = sorted(miss_ids - gap_ids)
    rec("miss_covered", not unc, "遗漏 %d 条，已归因 %d 条，未覆盖 %s" % (len(miss_ids), len(gap_ids & miss_ids), unc or "无"))

    rec("quote_verbatim", not qs["missing"], "证据 %d 条，逐字命中 %d，未命中 %d %s"
        % (qs["checked"], qs["found"], qs["missing"], ([x["item"] for x in qs["missing_items"]][:5] or "")),
        warn=bool(qs["missing"]))

    ident = (cov["numerator"] + cov["miss_count"] + cov["pending_count"] == cov["denominator"])
    rec("identity", ident, "分母 %d = 命中 %d + 遗漏 %d + 待裁决 %d；coverage=%s"
        % (cov["denominator"], cov["numerator"], cov["miss_count"], cov["pending_count"], cov["coverage"]))

    badcat = sorted({g["category"] for g in c["gaps"] if g["category"] not in AB.CATS})
    badwhy = sorted({g["why"] for g in c["gaps"] if g["why"] not in AB.WHYS})
    rec("category_vocab", not badcat and not badwhy, "非法 category=%s why=%s" % (badcat or "无", badwhy or "无"))

    auto_n = len([r for r in rows if r["decision_source"] == "auto"])
    rec("agent_decisions", auto_n <= max(1, int(0.3 * len(rows))),
        "agent=%d auto=%d（auto 表示未经人工确认）" % (len(rows) - auto_n, auto_n), warn=True)

    rec("supplement", bool(c["sup"]["rows"]) or cov["miss_count"] == 0,
        "补检 %d 条，新增命中 %d，空转 %d，边际收益 %.2f"
        % (c["sup"]["queries"], c["sup"]["total_new_hits"], c["sup"]["no_gain_queries"], c["sup"]["marginal_yield"]),
        warn=True)

    if isinstance(draft.get("scope"), dict) and draft["scope"].get("denominator_policy"):
        okp = draft["scope"]["denominator_policy"] in AB.POLICIES
        rec("policy", okp, "口径=%s（合法取值 %s）" % (draft["scope"]["denominator_policy"], list(AB.POLICIES)))
    else:
        rec("policy", True, "工作稿未声明 denominator_policy，使用默认 %s" % policy, warn=True)

    print("[check] case=%s policy=%s 分母=%d 命中=%d 遗漏=%d 覆盖率=%s"
          % (st.get("case_id"), policy, cov["denominator"], cov["numerator"], cov["miss_count"], cov["coverage"]))
    for tag, name, detail in lines:
        print("[%s] %-16s %s" % (tag, name, detail))
    fails = [x for x in report if x["status"] == "FAIL"]
    warns = [x for x in report if x["status"] == "WARN"]
    print("[check] %d PASS / %d WARN / %d FAIL" % (len(report) - len(fails) - len(warns), len(warns), len(fails)))
    if fails:
        print("[check] FAIL 项必须在 build 前修掉；修法见 SKILL.md §9 与 references/draft-and-fields.md")
    jdump(work / "check_report.json", {"case_id": st.get("case_id"), "policy": policy,
                                       "coverage": cov, "checks": report})
    return 0


# ------------------------------------------------------------------------ build
def cmd_selfcheck(a, st, out, inp):
    draft = jload(Path(st["paths"]["work"]) / "draft.json") or {}
    policy = policy_of(st, draft, a.policy)
    c = compute(st, draft, policy)
    cov = c["cov"]
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    present = [n for n in PRODUCTS if (out / n).exists() and (out / n).stat().st_size > 0]
    add("products", len(present) == len(PRODUCTS), "%d/%d 存在且非空" % (len(present), len(PRODUCTS)))
    res = jload(out / "result.json")
    add("result_json", isinstance(res, dict), "result.json 可解析" if isinstance(res, dict) else "result.json 不可解析")
    contract = st.get("contract") or {}
    miss = [k for k in contract if not isinstance(res, dict) or k not in res]
    add("contract_keys", not miss, "缺失键 %s" % (miss or "无"))
    nul = [k for k in contract if isinstance(res, dict) and res.get(k) is None]
    add("contract_filled", not nul, "映射为 null 的键（已说明）%s" % (nul or "无"))
    led = LG.rcsv(out / "hit_ledger.csv")
    den = [r for r in led if r.get("usable") in ("True", "true", "1")]
    if policy == "dedup_only":
        den = led
    hit = [r for r in den if r.get("hit_status") == "hit"]
    rc = round(len(hit) / len(den), 6) if den else None
    add("recompute_csv", rc == cov["coverage"], "CSV 重算 %s vs 报告 %s（分母 %d，分子 %d）"
        % (rc, cov["coverage"], len(den), len(hit)))
    at = jload(out / "audit_trail.json") or {}
    add("audit_trail", at.get("recompute", {}).get("matches_report") is True,
        "audit_trail.recompute.matches_report=%s" % at.get("recompute", {}).get("matches_report"))
    # determinism: independent second computation
    c2 = compute(st, draft, policy)
    same = (c2["cov"]["coverage"] == cov["coverage"] and len(c2["gaps"]) == len(c["gaps"])
            and c2["sup"]["total_new_hits"] == c["sup"]["total_new_hits"])
    add("determinism", same, "两次独立计算 coverage/gaps/supplement 一致")
    ta = (out / "coverage_report.md")
    txt = ta.read_text("utf-8", "replace") if ta.exists() else ""
    add("report_numbers", str(cov["denominator"]) in txt and str(cov["numerator"]) in txt,
        "报告正文含分子/分母数字")
    gc = LG.rcsv(out / "gap_matrix.csv")
    adds = {r["ref_id"] for r in gc}
    add("matrix_covers_miss", set(cov["missed_ids"]).issubset(adds),
        "遗漏 %d 条，矩阵覆盖 %d 条" % (len(cov["missed_ids"]), len(adds & set(cov["missed_ids"]))))
    fails = [x for x in checks if x["status"] == "FAIL"]
    out_doc = {"case_id": st.get("case_id"), "skill": NAME, "version": V,
               "summary": {"verdict": "PASS" if not fails else "FAIL", "checks": len(checks),
                           "failed": len(fails)},
               "coverage": {"policy": cov["policy"], "denominator": cov["denominator"],
                            "numerator": cov["numerator"], "coverage": cov["coverage"],
                            "recomputed": rc},
               "checks": checks,
               "note": "全部由脚本重算；失败项写明原因，不删项凑 PASS"}
    jdump(out / "self_check.json", out_doc)
    for x in checks:
        print("[%s] %-18s %s" % (x["status"], x["check"], x["detail"]))
    print("[selfcheck] verdict=%s (%d/%d)" % (out_doc["summary"]["verdict"],
                                              len(checks) - len(fails), len(checks)))
    return 0


