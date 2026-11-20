#!/usr/bin/env python3
"""litread-bench-ledger ledger layer: artifacts (cards / anchors / raw outputs /
scoring records / scores.csv / panel / failures / version), calibration probes,
pointer closure and the self-check. Called by main.py; stdlib only."""
import csv
import json
from pathlib import Path

import core as C
import litio as L

BD = "benchmark"


def bdir():
    return L.OUTPUT / BD


def attribute(case):
    """Explicit item_id -> answer text from candidate payloads. No guessing."""
    out = []
    for cand in L.candidates(case):
        p = cand.get("payload")
        rows = list(p.items()) if isinstance(p, dict) else (
            [(None, v) for v in p] if isinstance(p, list) else [])
        for k, v in rows:
            if isinstance(v, str) and k:
                out.append({"agent": cand["agent"], "item_id": str(k), "text": v,
                            "source": cand["source"]})
            elif isinstance(v, dict):
                t = v.get("answer") or v.get("output") or v.get("response") or v.get("text")
                iid = v.get("item_id") or v.get("id") or k
                if isinstance(t, str) and iid:
                    out.append({"agent": cand["agent"], "item_id": str(iid), "text": t,
                                "source": cand["source"]})
    return out


def csv_line(vals):
    out = []
    for v in vals:
        s = "" if v is None else str(v)
        out.append('"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n') else s)
    return ",".join(out)


def run_config():
    cfg = {"schema": L.NM + "/run_config@1", "runner_version": L.V, "scale": [0, 1, 2],
           "scale_version": "1",
           "matching": "casefold + whitespace-normalised substring over key_terms",
           "thresholds": {"two": 0.75, "one": 0.25},
           "non_scorable_states": ["missing_reference", "no_anchor", "manual_review"],
           "budget": {"model_requests": 64, "wall_seconds": 900, "tokens_per_response": 16384},
           "permissions": "read /input; write /app/work + /app/output; stdlib only; offline",
           "model": "fixed by platform (official DeepSeek Harness)",
           "prompt_version": "skill:%s@%s" % (L.NM, L.V), "seed": 0, "generated_at": L.now()}
    cfg["run_config_hash"] = L.sha(cfg)[:16]
    return cfg


def version_of(set_meta, cfg, items, prev):
    cur = {"set_id": set_meta.get("set_id") or "reading-set",
           "set_version": set_meta.get("version") or "v1",
           "scale_version": cfg["scale_version"], "run_config_hash": cfg["run_config_hash"],
           "n_items": len(items),
           "item_ids_sha1": L.sha(sorted(i["item_id"] for i in items))[:12]}
    cur["listing"] = "%s / scale %s / cfg %s" % (cur["set_version"], cur["scale_version"],
                                                 cur["run_config_hash"])
    hist, comp, incmp = ([prev] if prev else []), [], []
    if prev:
        why = []
        for k, label in (("set_version", "set version changed"),
                         ("scale_version", "scoring scale changed"),
                         ("run_config_hash", "run config changed"),
                         ("item_ids_sha1", "item-id set changed")):
            if prev.get(k) != cur[k]:
                why.append(label)
        if why:
            incmp.append({"version": prev.get("listing") or str(prev.get("set_version")),
                          "reason": "; ".join(why),
                          "action": "recompute the history under the current scale before comparing"})
        else:
            comp.append({"version": prev.get("listing") or str(prev.get("set_version")),
                         "reason": "same set version, scale version, run config and item-id set"})
    return {"schema": L.NM + "/version_diff@1", "generated_at": L.now(), "current": cur,
            "history": hist, "comparable": comp, "incomparable": incmp,
            "rules": ["comparable only if set_version + scale_version + run_config_hash + "
                      "item-id set are identical",
                      "item-set change -> compare the intersection only, never the totals",
                      "no history -> this run is the baseline, no historical score is mixed in"]}


def render_panel(cid, cards, n_anc, n_ver, rows, agg, cm, cal, ver, idx, mode, unc):
    mats = "\n".join("| %s | %s | %s | %d | %d | %s |" % (m["mid"], m["name"][:32], m["kind"],
                                                          len(m["paragraphs"]), m["chars"], m["status"])
                     for m in idx.get("materials", [])) or "| - | no material | - | 0 | 0 | - |"
    tb = ["| item | type | difficulty | verified anchors | rule |", "|---|---|---|---|---|"] + [
        "| %s | %s | %s | %d | %s |" % (i["item_id"], i["task_type"], i["difficulty"],
                                        sum(1 for x in i["source_refs"]
                                            if (x.get("_v") or {}).get("verified")),
                                        i["scoring_rule"]["mode"]) for i in cards["items"]] or \
        ["| - | no card | - | 0 | - |"]
    sb = ["| agent | rows | scored | mean(0-2) |", "|---|---|---|---|"] + [
        "| %s | %d | %d | %s |" % (k, v["n"], v["scored"], v["mean"])
        for k, v in sorted(agg["by_agent"].items())]
    ax = ["| axis | status | detail |", "|---|---|---|"] + [
        "| %s | %s | %s |" % (k, v["status"], v["detail"]) for k, v in cm["axes"].items()]
    return "\n".join([
        "# 文献阅读题集与评分台账 · %s" % (cid or "unknown-case"), "",
        "- 生成 %s | set=%s（%s）| mode=%s | 题卡 %d | 锚点 %d/%d verified"
        % (L.now(), cards["set_id"], cards["set_version"], mode, len(cards["items"]), n_ver, n_anc),
        "- 口径：0/1/2 规则评分（key_terms 覆盖率，阈值 0.75/0.25），配置见 `benchmark/run_config.json`",
        "- **声明**：本台账分数是题集可判性与候选输出的一致性记录，**不是官方 Harness / DSH 分数**。", "",
        "## 1. 输入材料", "", "| id | name | kind | paras | chars | status |",
        "|---|---|---|---|---|---|", mats, "",
        "## 2. 题卡", "", *tb, "",
        "## 3. 逐题得分", "", "| item | agent | score | status | coverage | raw_output_ref |",
        "|---|---|---|---|---|---|",
        *(["| %s | %s | %s | %s | %s | `%s` |" % (r["item_id"], r["agent"],
                                                 "-" if r["score"] is None else r["score"],
                                                 r["status"], r["coverage"], r["raw_output_ref"])
           for r in rows] or ["| - | - | - | - | - | - |"]), "",
        "汇总 rows=%d scored=%d mean=%s 分布 2/1/0=%d/%d/%d judgeable=%s"
        % (agg["n_rows"], agg["n_scored"], agg["mean"], agg["distribution"][2],
           agg["distribution"][1], agg["distribution"][0], agg["judgeable_rate"]),
        "", *sb, "", "## 4. 覆盖矩阵", "", *ax, "",
        "verdict **%s**（ok=%d partial=%d missing=%d）"
        % (cm["verdict"], cm["n_ok"], cm["n_partial"], cm["n_missing"]), "",
        "## 5. 校准与版本", "",
        "- 探针校准 agreement=%s（%d/%d）" % (cal["agreement"], cal["n_agree"], cal["n_probes"]),
        "- 版本 %s；历史 %d，可比 %d，不可比 %d"
        % (ver["current"]["listing"], len(ver["history"]), len(ver["comparable"]),
           len(ver["incomparable"])), "",
        "## 6. 缺口", "", *(["- " + x for x in unc[:10]] or ["- 无"]), "",
        "复现 `init` → `show` → 写 `work/draft.json` → `check` → `build` → `selfcheck`。"])


def render_failures(cid, fails, recs):
    head = ["# 失败样例库 · %s" % (cid or "unknown-case"), "",
            "每条失败可追到题目 ID 与原始输出，并给出下一版专项题建议。", ""]
    if not fails:
        head += ["本批没有登记失败样例。", ""]
    else:
        head += ["| # | type | item | detail | ref | next action |", "|---|---|---|---|---|---|"] + [
            "| %d | %s | %s | %s | `%s` | %s |" % (i, f["type"], f["item_id"],
                                                   f["detail"][:80].replace("|", "/"),
                                                   f.get("ref") or "-", f["next_action"][:70])
            for i, f in enumerate(fails, 1)] + [""]
    if recs:
        head += ["## 下一版专项题建议", ""] + [
            "- `%s` ← %s ×%d：%s" % (r["suggested_item"], r["type"], r["n"], r["hint"])
            for r in recs] + [""]
    return "\n".join(head + [
        "## 归类口径", "",
        "- `missing_reference`：题卡无参考答案（不猜、不补造），只能问“材料是否报告”。",
        "- `no_anchor`：引文未逐字命中原文，题不可判，被拒收。",
        "- `locator_mismatch`：声明 locator 与引文实际段落不符，已按真实段号更正并登记。",
        "- `calibration_disagreement`：探针未拿到预期档位，评分规则或关键项写法需改。",
        "- `unattributed_raw_output`：候选输出无法归属到题，只登记不计分。",
        "- `low_coverage`：候选答案命中率 <0.25，得 0 分。"])


def build_set(case, cid, idx, c, items, rejected, issues, warns, wc, set_meta, mode):
    """Write every artifact. items must already carry _v / _anchors_ok."""
    anchors = []
    for it in items:
        for ref in it["source_refs"]:
            v = ref.get("_v") or L.verify(c, ref["material"], ref["quote"])
            ref["_v"] = v
            anchors.append({"item_id": it["item_id"], "material": ref["material"],
                            "locator": ref["locator"] or v.get("pid"),
                            "native_id": ref.get("native_id"), "page": v.get("page"),
                            "quote": ref["quote"], "verified": bool(v.get("verified")),
                            "match": v.get("match"),
                            "reason": None if v.get("verified") else v.get("reason")})
    n_ver = sum(1 for x in anchors if x["verified"])
    cfg = run_config()
    L.wj(bdir() / "run_config.json", cfg)
    prev = None
    if (bdir() / "cards.json").is_file():
        try:
            o = L.rj(bdir() / "cards.json")
            prev = {k: o.get(k) for k in ("set_id", "set_version", "scale_version",
                                          "run_config_hash", "n_items", "item_ids_sha1",
                                          "listing")}
        except Exception:
            prev = None
    cards = {"schema": L.NM + "/cards@1", "generated_at": L.now(), "case_id": cid,
             "set_id": set_meta.get("set_id") or ("set-" + (cid or "unknown")),
             "set_version": set_meta.get("version") or "v1",
             "license": set_meta.get("license") or "unknown",
             "scope": L.nm(str(set_meta.get("scope") or ""))[:400],
             "scale_version": cfg["scale_version"], "run_config_hash": cfg["run_config_hash"],
             "mode": mode, "n_items": len(items),
             "instruction": "逐题按 scoring_rule 打 0/1/2；引文须命中 anchors.json 的 locator。",
             "items": [{"item_id": it["item_id"], "task_type": it["task_type"],
                        "question": it["question"],
                        "source_refs": [{"material": r["material"], "locator": r.get("locator"),
                                         "native_id": r.get("native_id"), "quote": r["quote"],
                                         "verified": bool((r.get("_v") or {}).get("verified")),
                                         "locator_declared": r.get("locator_declared")}
                                        for r in it["source_refs"]],
                        "reference_answer": it["reference_answer"],
                        "reference_missing": it["reference_missing"],
                        "scoring_rule": it["scoring_rule"], "difficulty": it["difficulty"],
                        "license": it["license"], "origin": it["origin"],
                        "notes": it["notes"]} for it in items],
             "rejected": rejected, "workorder_coverage": wc,
             "item_ids_sha1": L.sha(sorted(i["item_id"] for i in items))[:12]}
    L.wj(bdir() / "cards.json", cards)
    L.wj(bdir() / "anchors.json",
         {"schema": L.NM + "/anchors@1", "case_id": cid, "generated_at": L.now(),
          "policy": "verbatim only; whitespace-normalised; paraphrase never counts",
          "n": len(anchors), "n_verified": n_ver, "anchors": anchors})

    raws, rows, records, fails = [], [], [], []

    def mkrow(it, agent, refidx, sc, extra=None):
        r = {"item_id": it["item_id"], "item_type": it["task_type"], "agent": agent,
             "run_id": cfg["run_config_hash"], "score": sc["score"], "max": 2,
             "status": sc["status"], "coverage": sc["coverage"],
             "expected": (extra or {}).get("expected"), "agreement": (extra or {}).get("agreement"),
             "rationale": sc["basis"],
             "raw_output_ref": "benchmark/raw_outputs.json#/items/%d/text" % refidx,
             "config_ref": "benchmark/run_config.json#/run_config_hash",
             "scoring_record_ref": "benchmark/scoring_records.json#/records/%d" % (len(records) - 1),
             "judgeable": sc["score"] is not None,
             "evidence_locator": next((a["locator"] for a in anchors
                                       if a["item_id"] == it["item_id"] and a["verified"]), None)}
        rows.append(r)
        return r

    for f in rejected:
        fails.append({"type": "no_anchor" if any("anchor" in x for x in f["reasons"]) else "schema",
                      "item_id": f["item_id"], "detail": "; ".join(f["reasons"]),
                      "ref": "benchmark/cards.json#/rejected",
                      "next_action": "补逐字引文或降级为“材料是否报告”题；不要改原文凑通过"})
    for w in warns:
        if "locator_mismatch" in w["msg"]:
            fails.append({"type": "locator_mismatch", "item_id": w.get("item"), "detail": w["msg"],
                          "ref": "benchmark/anchors.json#/anchors",
                          "next_action": "按真实段号改 locator，并核对引文是否取错段"})
    for it in items:
        if it["reference_missing"]:
            fails.append({"type": "missing_reference", "item_id": it["item_id"],
                          "detail": "card has no reference answer; not scored",
                          "ref": "benchmark/cards.json#/items",
                          "next_action": "索取参考答案，或把题改为“材料是否报告 X”"})
        if not it["_anchors_ok"]:
            fails.append({"type": "no_anchor", "item_id": it["item_id"],
                          "detail": "no verified quote", "ref": "benchmark/anchors.json#/anchors",
                          "next_action": "补一条逐字引文"})
        if (it["scoring_rule"]["mode"] == "manual_only" or it["reference_missing"]
                or not it["_anchors_ok"]):
            continue  # not scorable -> no probe, no invented score
        for pb in C.probe_answers(it):
            sc = C.score_answer(it, pb["answer"])
            raws.append({"output_id": "P:%s:%s" % (it["item_id"], pb["probe"]),
                         "item_id": it["item_id"], "agent": "calibration_probe",
                         "kind": "probe", "probe": pb["probe"], "text": pb["answer"]})
            records.append({"record_id": "R%03d" % (len(records) + 1), "item_id": it["item_id"],
                            "output_id": raws[-1]["output_id"], "score": sc["score"],
                            "status": sc["status"], "coverage": sc["coverage"],
                            "basis": sc["basis"], "expected": pb["expected"],
                            "agreement": sc["score"] == pb["expected"],
                            "rule": it["scoring_rule"]})
            mkrow(it, "calibration_probe", len(raws) - 1, sc,
                  {"expected": pb["expected"], "agreement": records[-1]["agreement"]})
            if not records[-1]["agreement"]:
                fails.append({"type": "calibration_disagreement", "item_id": it["item_id"],
                              "detail": "probe %s expected %s got %s"
                                        % (pb["probe"], pb["expected"], sc["score"]),
                              "ref": "benchmark/scoring_records.json#/records/%d" % (len(records) - 1),
                              "next_action": "改 scoring_rule（阈值/关键项）直到探针回到预期档位"})
    by_id = {it["item_id"]: it for it in items}
    for ca in attribute(case):
        it = by_id.get(ca["item_id"])
        if not it:
            fails.append({"type": "unattributed_raw_output", "item_id": ca["item_id"],
                          "detail": "candidate answer points at an unknown item id",
                          "ref": ca["source"], "next_action": "对齐题号后再评分"})
            continue
        sc = C.score_answer(it, ca["text"])
        raws.append({"output_id": "C:%s:%s" % (ca["agent"], ca["item_id"]),
                     "item_id": ca["item_id"], "agent": ca["agent"], "kind": "candidate",
                     "text": ca["text"][:6000]})
        records.append({"record_id": "R%03d" % (len(records) + 1), "item_id": it["item_id"],
                        "output_id": raws[-1]["output_id"], "score": sc["score"],
                        "status": sc["status"], "coverage": sc["coverage"], "basis": sc["basis"],
                        "expected": None, "agreement": None, "rule": it["scoring_rule"]})
        mkrow(it, ca["agent"], len(raws) - 1, sc)
        if sc["score"] == 0:
            fails.append({"type": "low_coverage", "item_id": it["item_id"],
                          "detail": "candidate coverage %.2f" % (sc["coverage"] or 0),
                          "ref": "benchmark/raw_outputs.json#/items/%d/text" % (len(raws) - 1),
                          "next_action": "入失败样例库，作为下一版同类专项题来源"})
    for cand in L.candidates(case):
        if cand.get("payload") is None:
            fails.append({"type": "unattributed_raw_output", "item_id": "-",
                          "detail": "candidate file not mappable to item ids: " + cand["output_id"],
                          "ref": "-", "next_action": "提供 item_id → answer 结构后再评分"})
    L.wj(bdir() / "raw_outputs.json",
         {"schema": L.NM + "/raw_outputs@1", "case_id": cid, "generated_at": L.now(),
          "note": "probe answers derive from the card's own reference answer; candidate texts "
                  "are copied verbatim from input", "items": raws})
    L.wj(bdir() / "scoring_records.json",
         {"schema": L.NM + "/scoring_records@1", "case_id": cid, "generated_at": L.now(),
          "scale": {"2": "coverage>=0.75 with verified anchor", "1": "0.25<=coverage<0.75",
                    "0": "coverage<0.25 or empty"}, "records": records})
    hdr = ["item_id", "item_type", "agent", "run_id", "score", "max", "status", "coverage",
           "judgeable", "expected", "agreement", "rationale", "raw_output_ref", "config_ref",
           "scoring_record_ref", "evidence_locator"]
    L.wt(bdir() / "scores.csv", ",".join(hdr) + "\n" + "\n".join(
        csv_line([r.get(h) for h in hdr]) for r in rows))
    closure = {"n_rows": len(rows), "n_resolved": 0, "closure_rate": 0.0, "failures": []}
    for i, r in enumerate(rows, 1):
        ok_all = True
        for field in ("raw_output_ref", "config_ref", "scoring_record_ref"):
            ok, why = C.resolve_ref(L.OUTPUT, r.get(field))
            if not ok:
                ok_all = False
                closure["failures"].append({"row": i, "field": field, "ref": r.get(field),
                                            "reason": why})
        closure["n_resolved"] += int(ok_all)
    closure["closure_rate"] = round(closure["n_resolved"] / len(rows), 3) if rows else 0.0
    n_judge = sum(1 for x in records if x["agreement"] is not None)
    cal = {"n_probes": len(records), "n_agree": sum(1 for x in records if x["agreement"] is True),
           "n_disagree": sum(1 for x in records if x["agreement"] is False),
           "agreement": round(sum(1 for x in records if x["agreement"] is True) / n_judge, 3)
           if n_judge else 0.0,
           "note": "probes prove the 0/1/2 rule separates gold / partial / empty answers; this "
                   "is self-calibration evidence, not a model score"}
    agg = C.agg_rows(rows)
    agg.update({"closure_rate": closure["closure_rate"], "n_anchors": len(anchors),
                "n_anchors_verified": n_ver})
    ver = version_of(set_meta, cfg, items, prev)
    cm = C.coverage_matrix(cards, rows, fails, ver)
    fails = fails[:40]
    seen = {}
    for f in fails:
        seen[f["type"]] = seen.get(f["type"], 0) + 1
    hint = {"missing_reference": "把无答案题改成“材料是否报告”二元题",
            "no_anchor": "引文定位专项题（给段落，要求指出段落号）",
            "locator_mismatch": "locator 反查专项题",
            "calibration_disagreement": "评分档位边界题（0/1/2 各一条）",
            "unattributed_raw_output": "输出格式约束题",
            "low_coverage": "同题型高难度变体"}
    recs = [{"suggested_item": "S%02d" % i, "type": t, "n": n, "hint": hint.get(t, "同题型变体")}
            for i, (t, n) in enumerate(sorted(seen.items(), key=lambda kv: -kv[1]), 1)]
    unc = []
    if any(i["reference_missing"] for i in items):
        unc.append("%d 张卡无参考答案（missing_reference），未评分未补造"
                   % sum(1 for i in items if i["reference_missing"]))
    if rejected:
        unc.append("%d 张卡被拒（无逐字锚点或字段不全），未进评分" % len(rejected))
    if closure["n_resolved"] < len(rows):
        unc.append("%d/%d 条评分行三指针未完全解析" % (len(rows) - closure["n_resolved"], len(rows)))
    if cal["n_disagree"]:
        unc.append("%d 条探针未拿到预期档位，评分规则需人工复核" % cal["n_disagree"])
    if any(m["note"] for m in idx["materials"]):
        unc.append("材料解析降级：%s（引文需平台解析器复核）"
                   % ", ".join(m["mid"] for m in idx["materials"] if m["note"]))
    if mode != "agent_authored":
        unc.append("本批为 %s：只覆盖摘录/数值类，推理题与冲突题未覆盖" % mode)
    if not idx["materials"]:
        unc.append("input 下没有可用材料")
    L.wt(bdir() / "failures.md", render_failures(cid, fails, recs))
    L.wt(bdir() / "panel.md", render_panel(cid, cards, len(anchors), n_ver, rows, agg, cm, cal,
                                           ver, idx, mode, unc))
    L.wj(bdir() / "version_diff.json", ver)
    outs = {"result": "result.json", "cards": "benchmark/cards.json",
            "anchors": "benchmark/anchors.json", "scores_csv": "benchmark/scores.csv",
            "scoring_records": "benchmark/scoring_records.json",
            "raw_outputs": "benchmark/raw_outputs.json",
            "run_config": "benchmark/run_config.json", "panel": "benchmark/panel.md",
            "failures": "benchmark/failures.md", "version_diff": "benchmark/version_diff.json"}
    return {"cards": cards, "anchors": anchors, "n_anchors": len(anchors), "n_verified": n_ver,
            "rows": rows, "records": records, "closure": closure, "cal": cal, "agg": agg,
            "ver": ver, "cm": cm, "fails": fails, "recs": recs, "unc": unc, "outs": outs,
            "cfg": cfg}


def selfcheck():
    """Re-read artefacts and reconcile. Returns (ok, checks, lines)."""
    if not (L.OUTPUT / "result.json").is_file():
        return False, [], ["! no result.json yet -> run init then build"]
    res = L.rj(L.OUTPUT / "result.json")
    checks, lines = [], []

    def ck(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        lines.append("  %-22s %s  %s" % (name, "OK  " if ok else "FAIL", detail))

    keys = res.get("contract_fields_present") or []
    missing = [k for k in keys if k not in res]
    ck("contract_keys_on_top", not missing, "%d fields, missing=%s" % (len(keys), missing or "none"))
    rows, problems = [], []
    p = bdir() / "scores.csv"
    if p.is_file():
        with p.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for i, r in enumerate(rows, 1):
            for field in ("raw_output_ref", "config_ref", "scoring_record_ref"):
                ok, why = C.resolve_ref(L.OUTPUT, r.get(field))
                if not ok:
                    problems.append({"row": i, "field": field, "why": why})
    ck("scores_csv_rows", bool(rows), "%d rows" % len(rows))
    bad_rows = {x["row"] for x in problems}
    rate = (len(rows) - len(bad_rows)) / len(rows) if rows else 0.0
    ck("pointer_closure", bool(rows) and not problems,
       "closure %.2f, %d unresolved rows" % (rate, len(bad_rows)))
    agg = ((res.get("scoring") or {}).get("aggregate") or {})
    d = agg.get("distribution") or {}
    val = lambda r: int(r["score"]) if r.get("score") not in ("", None) else None
    recount = {k: sum(1 for r in rows if val(r) == k) for k in (0, 1, 2)}
    ck("panel_vs_csv", recount == {k: int(d.get(str(k), d.get(k, -1))) for k in (0, 1, 2)},
       "csv=%s result=%s" % (recount, d))
    scored = [val(r) for r in rows if val(r) is not None]
    mean = round(sum(scored) / len(scored), 3) if scored else None
    ck("mean_matches", mean == agg.get("mean"), "csv mean=%s result=%s" % (mean, agg.get("mean")))
    anc = L.rj(bdir() / "anchors.json") if (bdir() / "anchors.json").is_file() else {}
    bad = [x for x in anc.get("anchors", []) if not x.get("verified")]
    ck("anchors_verified", not bad, "%d/%d verified"
       % (anc.get("n_verified", 0), anc.get("n", 0)))
    cal = res.get("calibration") or {}
    ck("calibration", cal.get("n_disagree", 1) == 0,
       "agreement=%s disagree=%s" % (cal.get("agreement"), cal.get("n_disagree")))
    cm = res.get("coverage_matrix") or {}
    ck("coverage_matrix", cm.get("n_missing") == 0, "verdict=%s" % cm.get("verdict"))
    ok = all(c["ok"] for c in checks)
    lines.append("closure_rate=%.2f | calibration_agreement=%s | SELFCHECK: %s"
                 % (rate, cal.get("agreement"), "PASS" if ok else "ATTENTION"))
    L.wj(L.WORK / "selfcheck.json", {"ok": ok, "checks": checks})
    res.setdefault("runtime", {})["selfcheck"] = {"ok": ok, "checks": checks, "at": L.now()}
    L.save(res, "selfcheck")
    return ok, checks, lines
