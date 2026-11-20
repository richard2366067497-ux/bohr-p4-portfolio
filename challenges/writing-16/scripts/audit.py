#!/usr/bin/env python3
"""audit.py -- deterministic verdict on an Agent-written draft + output_contract binding.

Standard library only. Import-safe. Standalone use:
    python3 scripts/audit.py --draft /app/work/draft.json --index /app/work/index.json [--json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
try:
    import kit
except Exception:                                    # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kit

LOC = kit.LOC
REQ = ("audience", "genre", "sections", "retained", "trace", "changes")
KINDS = {"conclusion", "number", "condition", "sample", "metric", "figure", "citation", "limitation", "term"}
TREAT = {"kept", "condensed", "moved", "reworded"}
DECIDE = {"keep", "compress", "merge", "split", "drop"}
META = re.compile(r"本文将|本文主要|本文旨在|接下来我们|下面将|本稿将|"
                  r"this article will|in this (?:article|paper), we will|the following will", re.I)
SLOTS = ((("case_id", "caseid", "案例编号"), "case_id"),
         (("deliver", "manuscript", "artifact", "transformed", "产物", "稿", "article", "output_text",
           "converted", "retarget", "rewrit", "draft_text", "final_text", "translation"), "deliverable"),
         (("preserv", "retain", "保留", "fact", "事实", "must_keep", "checklist"), "preserved_facts"),
         (("evidence", "source_map", "mapping", "对照", "来源", "映射", "citation", "trace", "locator", "provenance"),
          "evidence_map"),
         (("change", "revision", "diff", "改动", "修改", "log"), "change_log"),
         (("glossar", "termin", "术语", "abbrev", "lexicon", "nomenclature"), "glossary"),
         (("drop", "deleted", "removed", "删除", "omit", "reject"), "dropped"),
         (("pending", "human", "confirm", "确认", "待定"), "pending_human"),
         (("uncertain", "不确定", "limitation"), "uncertainty"),
         (("audience", "受众", "reader", "readership", "profile"), "audience"),
         (("genre", "format", "体裁", "文体"), "genre"),
         (("length", "篇幅", "word", "字数"), "length"),
         (("status", "状态"), "status"),
         (("quality", "gain", "增益", "metric", "score"), "fidelity_summary"))


def as_list(v):
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def overlap(quote, body_norm, n=6):
    """Prose-kind evidence: does a 6-gram of the verbatim quote survive in the body?"""
    q = kit.normalize(quote)
    if len(q) < n or not body_norm:
        return False
    return any(q[i:i + n] in body_norm for i in range(0, len(q) - n + 1, 2))


def qhit(q, he, hl):
    n = kit.normalize(q)
    if not n:
        return "empty"
    if n in he:
        return "exact"
    return "loose" if kit.normalize(q, True) in hl else "miss"


def check_draft(d, idx):
    E, W, P, S = [], [], [], {}
    err = lambda c, m, **k: E.append(dict(code=c, msg=m, **k))
    warn = lambda c, m, **k: W.append(dict(code=c, msg=m, **k))
    stats = {"sections": 0, "body_words": 0, "quote_hit": 0, "quote_total": 0,
             "numbers_in_body": 0, "number_errors": [], "retention_total": 0, "retention_covered": 0,
             "silent_drop": [], "term_drift": [], "abbr_unexpanded": [], "paragraph_coverage": None}

    if not isinstance(d, dict):
        err("draft_not_object", "draft.json 顶层必须是 JSON 对象")
        return {"status": "partial", "errors": E, "warnings": W, "pending": P, "stats": stats}

    for k in REQ:
        if k not in d:
            err("missing_field", "draft 缺字段 `%s`（见 references/draft-schema.md）" % k)
        elif d[k] in (None, "", [], {}):
            err("empty_field", "draft 字段 `%s` 为空，无法成稿" % k)

    paras = {p["loc"]: p for p in idx.get("paragraphs", [])}
    he, hl = idx.get("norm_exact", ""), idx.get("norm_loose", "")
    if not paras:
        err("no_material", "输入没有可解析的事实材料：无法完成改写")
    a = d.get("audience") if isinstance(d.get("audience"), dict) else {}
    g = d.get("genre") if isinstance(d.get("genre"), dict) else {}
    for f in ("label", "profile", "knowledge", "goal", "depth"):
        if not str(a.get(f) or "").strip():
            warn("audience_field_empty", "audience.%s 为空：适配策略缺依据" % f)
    if not str(g.get("label") or "").strip():
        warn("genre_label_missing", "genre.label 为空：体裁要素无法核对")

    # ---- body
    secs = as_list(d.get("sections"))
    ids, body_parts, tq, hq = [], [], 0, 0
    for i, s in enumerate(secs, 1):
        sid = str(s.get("id") or "S%d" % i)
        ids.append(sid)
        title, text = str(s.get("title") or "").strip(), str(s.get("text") or "").strip()
        if not text:
            err("section_empty", "section %s 正文为空（只写标题＝提纲，不能交付）" % sid)
        elif len(text) < 40:
            warn("section_too_short", "section %s 短于 40 字符，疑似要点而非成段正文" % sid)
        if not title:
            warn("section_title_empty", "section %s 缺标题" % sid)
        if s.get("strength") and str(s["strength"]) not in ("established", "preliminary", "hypothesis"):
            warn("strength_value_unknown", "section %s 的 strength=%s 不在三级枚举内" % (sid, s["strength"]))
        for c in ([s.get("cites")] if isinstance(s.get("cites"), str) else list(s.get("cites") or [])):
            if c and not (set(LOC.findall(str(c))) & set(paras)):
                err("locator_not_found", "section %s 的 cites 定位不存在：%s" % (sid, c))
        body_parts.append(text)
    stats["sections"] = len(ids)
    body = "\n".join(body_parts)
    stats["body_words"] = kit.words(body)
    if len(secs) < 2:
        err("too_few_sections", "成稿只有 %d 段：不足以构成一次成品改写" % len(secs))
    elif len(secs) == 2:
        warn("few_sections", "成稿只有 2 段，确认体裁要素是否齐备")

    # ---- length
    tgt = None
    for c in (g.get("length_target"), d.get("length_target"),
              (d.get("length") or {}).get("target") if isinstance(d.get("length"), dict) else None):
        if num(c):
            tgt = num(c)
            break
    stats["length_target"] = tgt
    if tgt:
        r = stats["body_words"] / tgt
        stats["length_ratio"] = round(r, 3)
        stats["length_target"] = int(tgt) if tgt == int(tgt) else tgt
        if r < 0.45:
            err("too_short", "正文 %d 字，仅为上限 %d 字的 %d%%：属提纲/片段，不是成品稿"
                % (stats["body_words"], int(tgt), int(r * 100)))
        elif r < 0.7:
            warn("short", "正文 %d 字，为上限的 %d%%，可在不删证据的前提下补足"
                 % (stats["body_words"], int(r * 100)))
        elif r > 1.05:
            err("over_budget", "正文 %d 字，超过篇幅上限 %d 字 %d%%：先删 P2 冗余（不得删证据）"
                % (stats["body_words"], int(tgt), int((r - 1) * 100)))
    else:
        warn("no_length_target", "未识别篇幅上限：按体裁常规处理，并在 uncertainty 说明")

    # ---- retained ledger
    ret = as_list(d.get("retained"))
    kept_in_body = 0
    for i, it in enumerate(ret, 1):
        v = str(it.get("value") or "").strip()
        lc = str(it.get("locator") or "").strip()
        kind = str(it.get("kind") or "").strip().lower()
        treat = str(it.get("treatment") or "").strip().lower()
        if not v:
            err("retained_value_missing", "retained[%d] 缺 value" % i)
        if not lc:
            err("retained_locator_missing", "retained[%d] 缺 locator（无法回溯）" % i)
        elif LOC.findall(lc) and set(LOC.findall(lc)) - set(paras):
            err("locator_not_found", "retained[%d] 定位 %s 不存在于材料索引" % (i, lc))
        if kind and kind not in KINDS:
            warn("retained_kind_unknown", "retained[%d] kind=%s 不在枚举内" % (i, kind))
        if treat and treat not in TREAT:
            warn("retained_treatment_unknown", "retained[%d] treatment=%s 不在枚举内" % (i, treat))
        wh = str(it.get("where") or "").strip()
        if wh and ids and wh not in ids and not set(LOC.findall(wh)):
            warn("retained_where_unknown", "retained[%d] 的 where=%s 不指向任何 section" % (i, wh))
        q = it.get("quote")
        if not q:
            warn("retained_quote_missing", "retained[%d] 无逐字 quote：无法核验" % i)
        else:
            tq += 1
            r = qhit(q, he, hl)
            if r == "miss":
                err("retained_quote_miss", "retained[%d] 的 quote 在源文中找不到（禁止改原文凑通过），值=%s"
                    % (i, v[:40]))
            elif r != "empty":
                hq += 1
        body_n = kit.normalize(body)
        if v and (kit.normalize(v) in body_n or
                  (kind in ("conclusion", "limitation", "condition", "metric") and
                   overlap(it.get("quote") or "", body_n))):
            kept_in_body += 1
        elif v and kind in ("number", "sample", "figure", "citation", "term", "conclusion"):
            if treat == "reworded" and str(it.get("note") or "").strip():
                warn("retained_reworded_absent", "retained[%d] 标注 reworded 且正文无原值，请确认仍可核对：%s"
                     % (i, v[:40]))
            else:
                err("retained_not_in_body", "必保留项未落进正文：%s（locator %s）——压缩可以，删除不行"
                    % (v[:40], lc or "?"))
    stats["retention_total"] = len(ret)
    stats["retention_covered"] = kept_in_body

    # ---- trace
    trace = as_list(d.get("trace"))
    used, traced = set(), set()
    for i, it in enumerate(trace, 1):
        sid = str(it.get("section_id") or "").strip()
        if sid and ids and sid not in ids:
            err("trace_section_unknown", "trace[%d] 指向不存在的 section_id=%s" % (i, sid))
        traced.add(sid)
        ls = set(LOC.findall(str(it.get("source_locator") or "")))
        if not ls:
            err("trace_locator_missing", "trace[%d] 缺可解析的 source_locator（形如 M1:P3）" % i)
        elif ls - set(paras):
            err("locator_not_found", "trace[%d] 定位不存在：%s" % (i, ",".join(sorted(ls - set(paras)))))
        used |= (ls & set(paras))
        if it.get("source_quote"):
            tq += 1
            if qhit(it["source_quote"], he, hl) == "miss":
                err("trace_quote_miss", "trace[%d] 的 source_quote 在源文中找不到" % i)
            else:
                hq += 1
        dec_ = str(it.get("decision") or "").strip().lower()
        if dec_ and dec_ not in DECIDE:
            warn("trace_decision_unknown", "trace[%d] decision=%s 不在枚举内" % (i, dec_))
    for sid in ids:
        if trace and sid not in traced:
            err("trace_missing_for_section", "section %s 没有逐段对照条目（原作者无法复核）" % sid)

    # ---- changes / dropped
    ch = as_list(d.get("changes"))
    for i, it in enumerate(ch, 1):
        if not str(it.get("action") or "").strip():
            err("change_action_missing", "changes[%d] 缺 action（保留/压缩/改写/删除）" % i)
        if not str(it.get("reason") or "").strip():
            err("change_reason_missing", "changes[%d] 缺 reason：改动无法复核" % i)
        if it.get("original_quote"):
            tq += 1
            if qhit(it["original_quote"], he, hl) == "miss":
                err("change_quote_miss", "changes[%d] 的 original_quote 在源文中找不到" % i)
            else:
                hq += 1
        ls = set(LOC.findall(str(it.get("locator") or "")))
        if ls and ls - set(paras):
            err("locator_not_found", "changes[%d] 定位不存在：%s" % (i, ",".join(sorted(ls - set(paras)))))
        used |= (ls & set(paras))
    stats["changes"] = len(ch)

    drop = as_list(d.get("dropped"))
    dropped_locs = set()
    for i, it in enumerate(drop, 1):
        if not str(it.get("why") or "").strip():
            err("dropped_reason_missing", "dropped[%d] 缺 why：为何是冗余而不是证据" % i)
        dropped_locs |= set(LOC.findall(str(it.get("locator") or "")))
        used |= (set(LOC.findall(str(it.get("locator") or ""))) & set(paras))

    # ---- numeric drift
    allow_vals = set()
    for it in as_list(d.get("numbers_allow")):
        v = kit.canon(str(it.get("value") or "").split(" ")[0].rstrip("%‰"))
        if v:
            allow_vals.add(v)
    src = set(idx.get("numbers", []))
    tgt_n = None
    if tgt:
        for cand in (str(int(tgt)), str(int(tgt)) + "字", "%d" % tgt):
            src.add(kit.canon(cand))
        tgt_n = kit.canon(str(int(tgt)))
    dv, dp = kit.numbers_of(body)
    drift = []
    for v in sorted(dv):
        if v in src or v in allow_vals:
            continue
        f = num(v)
        if f is not None and (kit.canon("%.10g" % (f / 100.0)) in src or
                              any(abs(f - (num(s) or 1e18)) < 1e-9 for s in src if num(s) is not None)):
            continue
        drift.append(v)
    stats["numbers_in_body"] = len(dv)
    stats["numbers_in_source"] = len(src)
    stats["number_errors"] = drift
    if drift:
        err("number_not_in_source", "成稿含源文没有的数字：%s（改回原值；换算/取整须写 numbers_allow 并进 "
                                    "open_questions）" % ", ".join(drift[:10]))
    if allow_vals:
        warn("numbers_allow_used", "使用了 %d 个 numbers_allow 数值（需作者确认口径）：%s"
             % (len(allow_vals), ", ".join(sorted(allow_vals)[:6])))
    unit_var = sorted({p for p in dp if p.split(p[-1])[0] in src and p not in set(idx.get("pairs", []))})
    if unit_var:
        warn("unit_variant", "单位写法与源文不一致：%s" % ", ".join(unit_var[:8]))

    # ---- figures / citations
    sf, bf = set(idx.get("figures", [])), kit.figrefs_of(body)
    if bf - sf:
        err("figure_mismatch", "成稿引用了源文没有的图表编号：%s（源文有：%s）"
            % (", ".join(sorted(bf - sf)[:6]), ", ".join(sorted(sf)[:8]) or "无"))

    # ---- silent deletion of candidates
    body_norm = kit.normalize(body)
    gap = []
    for c in idx.get("candidates", []):
        if c["locator"] in dropped_locs or c["locator"] in used:
            continue
        v = str(c.get("value") or "")
        probe = kit.canon(re.sub(r"[^\d.]", "", v)) if c.get("kind") == "number" else kit.normalize(v)
        if probe and probe in body_norm:
            continue
        if c.get("kind") in ("conclusion", "limitation"):
            gap.append({"locator": c["locator"], "kind": c.get("kind"), "value": v[:40]})
            continue
        gap.append({"locator": c["locator"], "kind": c.get("kind"), "value": v[:40]})
    stats["silent_drop"] = gap[:12]
    stats["candidates_total"] = len(idx.get("candidates", []))
    stats["retention_gap"] = len(gap)
    if len(gap) > max(3, int(0.25 * max(1, len(idx.get("candidates", []))))):
        warn("silent_drop", "%d 个候选保留项既未进正文也未在 dropped 说明（疑似悄悄删证据）：%s"
             % (len(gap), "; ".join("%s@%s" % (g["value"], g["locator"]) for g in gap[:6])))

    # ---- terminology
    drift_t = []
    for i, it in enumerate(as_list(d.get("glossary")), 1):
        usage = str(it.get("usage") or it.get("term") or "").strip()
        for v in (it.get("variants") or []):
            v, usage_s = str(v).strip(), usage
            if not v or v in usage_s or usage_s in v:
                continue
            if kit.normalize(v) in body_norm:
                drift_t.append(v)
    stats["term_drift"] = sorted(set(drift_t))
    if drift_t:
        err("term_variant_used", "正文出现术语表声明不用的变体：%s（同一概念全文只能一个说法）"
            % ", ".join(sorted(set(drift_t))[:8]))
    gl = {str(it.get("term") or "").strip(): it for it in as_list(d.get("glossary"))}
    unexp = []
    for ac in sorted(kit.acronyms_of(body))[:40]:
        pos = body.find(ac)
        if pos < 0:
            continue
        win = body[max(0, pos - 60):pos + len(ac) + 60]
        if "（" in win or "(" in win:
            continue
        if ac in gl and kit.normalize(gl[ac].get("expansion") or "") in body_norm:
            continue
        unexp.append(ac)
    stats["abbr_unexpanded"] = unexp[:10]
    if unexp:
        warn("abbr_not_expanded", "缩写首次出现未展开：%s（首次出现处给全称，或登记进 glossary）"
             % ", ".join(unexp[:8]))

    # ---- claim strength
    src_causal = set(idx.get("causal", []))
    up = sorted({c for c in kit.causal_of(body) if c not in src_causal})
    stats["strength_upgrades"] = up
    if up:
        warn("strength_upgrade", "正文出现源文未使用的因果/绝对化措辞：%s（相关不写成因果，初步不写成定论）"
             % ", ".join(up[:8]))
    src_h, body_h = set(idx.get("hedges", [])), kit.hedges_of(body)
    stats["hedge_source"], stats["hedge_kept"] = len(src_h), len(body_h)
    if len(src_h) >= 3 and not body_h:
        err("hedge_lost", "源文有 %d 类限定/不确定表述（%s），成稿一处未保留：论据边界被抹平"
            % (len(src_h), ", ".join(sorted(src_h)[:5])))
    elif len(src_h) >= 4 and len(body_h) / len(src_h) < 0.4:
        warn("hedge_thin", "成稿限定语仅覆盖源文的 %d%%：检查是否把初步结果写成定论"
             % int(100 * len(body_h) / len(src_h)))

    if META.search(body):
        warn("meta_discourse", "正文出现元话语（\"本文将…\"）：成稿应直接给内容")

    # ---- coverage
    mloc = {p["loc"] for p in idx.get("paragraphs", []) if p.get("role") != "instruction"}
    stats["material_paragraphs"] = len(mloc)
    stats["paragraphs_used"] = len(used & mloc)
    if mloc:
        cov = len(used & mloc) / len(mloc)
        stats["paragraph_coverage"] = round(cov, 3)
        if cov < 0.15:
            warn("low_coverage", "仅 %d/%d 段进入对照：确认关键证据段没有被漏读"
                 % (stats["paragraphs_used"], len(mloc)))

    stats["quote_total"], stats["quote_hit"] = tq, hq
    stats["quote_hit_rate"] = round(hq / tq, 3) if tq else None
    if tq and hq < tq:
        P.append({"issue": "有 %d 条 quote 未能在源文逐字命中" % (tq - hq),
                  "why": "引文必须逐字取自源材料", "action": "改用源文原句后重跑 check", "owner": "author"})
    if drift:
        P.append({"issue": "数字与源文不一致：%s" % ", ".join(drift[:6]),
                  "why": "改稿不得改变数值、单位或比较基准", "action": "改回原值或登记 numbers_allow",
                  "owner": "author"})
    return {"status": "ok" if not E else "partial", "errors": E, "warnings": W, "pending": P, "stats": stats}


def fidelity(stats, idx, contract_fill, fallback, status):
    total = stats.get("retention_total") or 0
    cand = stats.get("candidates_total") or 0
    return {
        "status": status,
        "fallback_draft": bool(fallback),
        "sections": stats.get("sections"),
        "body_words": stats.get("body_words"),
        "length_target": stats.get("length_target"),
        "length_ratio": stats.get("length_ratio"),
        "quote_hit": stats.get("quote_hit"), "quote_total": stats.get("quote_total"),
        "quote_hit_rate": stats.get("quote_hit_rate"),
        "numeric_drift": len(stats.get("number_errors") or []),
        "numbers_in_body": stats.get("numbers_in_body"),
        "retained_total": total, "retained_in_body": stats.get("retention_covered"),
        "retained_coverage": round(stats.get("retention_covered", 0) / total, 3) if total else None,
        "candidates_total": cand, "unexplained_gap": stats.get("retention_gap"),
        "silent_drop": [g["value"] for g in (stats.get("silent_drop") or [])][:10],
        "term_drift": stats.get("term_drift"),
        "abbr_unexpanded": stats.get("abbr_unexpanded"),
        "strength_upgrades": stats.get("strength_upgrades"),
        "hedge_source": stats.get("hedge_source"), "hedge_kept": stats.get("hedge_kept"),
        "paragraph_coverage": stats.get("paragraph_coverage"),
        "contract_fields": contract_fill.get("total"), "contract_filled": contract_fill.get("filled"),
        "contract_null": contract_fill.get("null_fields"),
        "recompute": "python3 scripts/main.py check  # 全部指标由 source+result.json 复算，非自述",
    }


def contract_fill(contract, ctx):
    """Bind every original output_contract key to produced content, preserving its type."""
    out, rep = {}, {"total": 0, "filled": 0, "null_fields": [], "keys": []}
    if not isinstance(contract, dict):
        return out, rep
    for f, raw in contract.items():
        rep["total"] += 1
        rep["keys"].append(f)
        slot = next((s for heads, s in SLOTS if any(h in str(f).lower() for h in heads)), None)
        v = ctx.get(slot)
        empty = v is None or (isinstance(v, (list, dict, str)) and not v)
        if empty:
            if isinstance(raw, list):
                v = []
            elif isinstance(raw, dict):
                v = {}
            elif isinstance(raw, bool):
                v = False
            else:
                v = None
            rep["null_fields"].append(f)
        else:
            rep["filled"] += 1
        out[f] = v
    return out, rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="audit.py", description="工作稿确定性校验（引文/数字/覆盖/术语/强度/篇幅）")
    ap.add_argument("--draft", default="/app/work/draft.json")
    ap.add_argument("--index", default="/app/work/index.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = {"status": "partial", "errors": [], "warnings": [], "pending": [], "stats": {}}
    try:
        d = kit.read_json(a.draft)
        idx = kit.read_json(a.index)
        rep = check_draft(d, idx)
    except Exception as e:
        rep["errors"].append({"code": "exception", "msg": "%s: %s" % (type(e).__name__, e)})
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        s = rep["stats"]
        print("状态 %s | 段落 %s | 正文 %s 字 | 引文 %s/%s | 数字漂移 %s"
              % (rep["status"], s.get("sections"), s.get("body_words"), s.get("quote_hit"),
                 s.get("quote_total"), len(s.get("number_errors") or [])))
        for e in rep["errors"]:
            print("  [错误] " + str(e.get("msg")))
        for w in rep["warnings"]:
            print("  [提示] " + str(w.get("msg")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
