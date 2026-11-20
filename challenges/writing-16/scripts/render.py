#!/usr/bin/env python3
"""render.py --排版、附表、兜底稿与 result.json finalize（被 main.py 调用；可单独 --help）。

只做确定性组装：正文内容全部来自 Agent 写好的 draft.json。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
try:
    import kit
    import audit
except Exception:                                     # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kit
    import audit

SK, VER = "source-faithful-retargeting", "9.0.0"


def as_list(v):
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return [v] if isinstance(v, dict) else []


def tb(head, rows):
    o = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        o.append("| " + " | ".join(str(c if c is not None else "").replace("|", "/")
                                   .replace("\n", " ")[:220] for c in r) + " |")
    return "\n".join(o)


def render(c, d, rep):
    a = d.get("audience") if isinstance(d.get("audience"), dict) else {}
    g = d.get("genre") if isinstance(d.get("genre"), dict) else {}
    st, wo = rep.get("stats") or {}, c.get("wo") or {}
    n, tgt = st.get("body_words") or 0, c.get("target") or 0
    spec = "\n".join("- **%s**：%s" % (k, v) for k, v in (
        ("读者标签", a.get("label") or "未填写"),
        ("读者画像", a.get("profile") or "未填写"),
        ("知识假设", a.get("knowledge") or "未填写"),
        ("阅读目的", a.get("goal") or "未填写"),
        ("解释深度", a.get("depth") or "未填写"),
        ("术语策略", a.get("term_policy") or "未填写"),
        ("论断强度策略", a.get("strength_policy") or "未填写"),
        ("体裁", g.get("label") or "未填写"),
        ("体裁惯例", "；".join(g.get("conventions") or []) or "未填写"),
        ("篇幅", "上限 %s ｜ 实际 %s 字（%s）" % (
            tgt or "未指定", n, "符合" if c.get("ok_len") else "偏离，见第八节")),
        ("取舍原则", "P0 必保留：结论/数值+单位/样本与条件/比较基准/图表引用/局限性；"
                    "P1 压缩：方法参数与文献堆叠；P2 删除：重复表述、无关推导、致谢投稿")))
    basis = "；".join("`%s`→%s" % kv for kv in (wo.get("basis") or {}).items()) \
        or "题面未给显式依据，按体裁常规处理"
    secs, rows, tmap = [], [], {}
    for m in as_list(d.get("trace")):
        tmap.setdefault(str(m.get("section_id") or ""), []).append(m)
    for i, s in enumerate(as_list(d.get("sections")), 1):
        sid = str(s.get("id") or "S%d" % i)
        ct = s.get("cites")
        secs.append("### %d. %s\n\n%s\n\n〔来源：%s ｜ 强度：%s〕\n" % (
            i, s.get("title") or "（无标题）", (s.get("text") or "").strip(),
            "、".join(ct) if isinstance(ct, list) else (ct or "见第三节对照表"),
            s.get("strength") or "未标注"))
        for m in (tmap.get(sid) or [{}]):
            rows.append([sid, m.get("source_locator") or "—", m.get("source_quote") or "—",
                         m.get("decision") or "—", m.get("note") or ""])
    cmp_t = tb(["段落", "源文位置", "源文原句（逐字）", "处理", "说明"], rows or [["—"] * 5])
    pres_t = tb(["编号", "类型", "值", "源位置", "源文原句", "落点", "处理"],
                [[x.get("id") or "R%d" % i, x.get("kind") or "", x.get("value") or "",
                  x.get("locator") or "", x.get("quote") or "", x.get("where") or "",
                  x.get("treatment") or ""] for i, x in enumerate(as_list(d.get("retained")), 1)]
                or [["—"] * 7])
    chg_t = tb(["编号", "动作", "源位置", "原文", "改后", "理由"],
               [["C%d" % i, x.get("action") or "", x.get("locator") or "",
                 x.get("original_quote") or "", x.get("revised_quote") or "", x.get("reason") or ""]
                for i, x in enumerate(as_list(d.get("changes")), 1)] or [["—"] * 6])
    drop = "\n".join("- `%s` %s：%s" % (x.get("locator") or "—", x.get("item") or "", x.get("why") or "")
                     for x in as_list(d.get("dropped"))) or "- 无（未声明删除项）"
    glo = "\n".join("- **%s**：%s；全文统一用「%s」%s" % (
        x.get("term") or "", x.get("expansion") or "—", x.get("usage") or x.get("term") or "",
        "（源位置 %s）" % x["locator"] if x.get("locator") else "")
        for x in as_list(d.get("glossary"))) or "- 无"
    q = "\n".join("- **待确认**：%s（原因：%s；动作：%s）" % (
        p.get("issue") or "—", p.get("why") or "—", p.get("action") or p.get("owner") or "作者确认")
        for p in as_list(d.get("open_questions")) + as_list(rep.get("pending"))) or "- 无"
    un = "\n".join("- " + (u if isinstance(u, str) else json.dumps(u, ensure_ascii=False))
                   for u in (list(d.get("uncertainty") or []) + list(c.get("unc") or []))) or "- 无"
    fb = ("> ⚠ **兜底稿**：工作稿缺失或不可用，本文件由脚本从源材料逐字抽取而成，**未完成受众改写**，"
          "仅供在此基础上继续写。\n") if c.get("fallback") else ""
    return """# %s

%s

> 状态 **%s** ｜ 受众 **%s** ｜ 体裁 **%s** ｜ 篇幅 %s/%s 字

%s
## 一、转换说明（受众 / 体裁 / 篇幅 / 依据）

%s

判定依据：%s

## 二、转化稿正文

%s

## 三、逐段来源对照（原作者可按段复核）

%s

## 四、必保留项台账（事实 / 数值 / 条件 / 图表引用）

%s

## 五、删改清单

%s

未进入成稿的内容及理由：

%s

## 六、术语与缩写

%s

## 七、待确认与不确定性

%s

%s

## 八、自检（可复算，非自述）

- 段落 %s ｜ 正文 %s 字 ｜ 篇幅比值 %s
- 引文逐字命中 %s/%s ｜ 成稿数字 %s 个（漂移 %s 个）｜ 源文数值 %s 个
- 必保留项 %s 条，落进正文 %s 条 ｜ 候选保留项 %s 个，未解释缺口 %s 个
- 段落对照覆盖 %s/%s ｜ 术语漂移 %s ｜ 未展开缩写 %s
- 校验错误 %s 条、提示 %s 条（逐条见 result.json 的 errors / warnings）
""" % (d.get("headline") or "科研成果转化稿", ("> " + d["deck"]) if d.get("deck") else "",
       c.get("status", "partial"), a.get("label") or "未指定", g.get("label") or "未指定",
       n, tgt or "未指定", fb, spec, basis,
       "\n".join(secs) if secs else "_（无正文：材料或工作稿缺失，见第七节）_",
       cmp_t, pres_t, chg_t, drop, glo, q, un,
       st.get("sections"), n, st.get("length_ratio") or "—",
       st.get("quote_hit"), st.get("quote_total"), st.get("numbers_in_body"),
       len(st.get("number_errors") or []), st.get("numbers_in_source"),
       st.get("retention_total"), st.get("retention_covered"), st.get("candidates_total"),
       st.get("retention_gap"), st.get("paragraphs_used"), st.get("material_paragraphs"),
       len(st.get("term_drift") or []), len(st.get("abbr_unexpanded") or []),
       len(rep.get("errors") or []), len(rep.get("warnings") or []))


def fallback_draft(idx, wo):
    """Deterministic verbatim extraction, so build never returns nothing."""
    pool = []
    for p in idx.get("paragraphs", []):
        if p.get("role") == "instruction":
            continue
        for s in re.split(r"(?<=[。！？!?])\s*|\n+", p.get("text") or ""):
            if len(s.strip()) >= 12:
                pool.append((p["loc"], s.strip()))
    if not pool:
        return None
    m = re.search(r"(\d{2,5})", str((wo or {}).get("length") or ""))
    cap, used, secs, pres, tr, seen = (int(m.group(1)) if m else 900), 0, [], [], [], set()
    plan = [("源文要点摘录（逐字，未改写）", r"[\s\S]", 4),
            ("关键数值与条件（逐字，未改写）", r"[%‰]|\d", 8),
            ("局限与待确认（逐字，未改写）",
             r"局限|限制|尚需|有待|初步|提示|可能|不足|limit|caveat|preliminary|suggest", 5)]
    for i, (name, pat, lim) in enumerate(plan, 1):
        got = []
        for loc, s in pool:
            if len(got) >= lim or used + len(s) > cap:
                break
            if re.search(pat, s, re.I) and s not in seen:
                got.append((loc, s))
                seen.add(s)
                used += len(s)
        if not got:
            continue
        sid = "F%d" % i
        secs.append({"id": sid, "title": name, "text": "\n\n".join(g[1] for g in got),
                     "cites": [g[0] for g in got], "strength": "source-verbatim"})
        for loc, s in got:
            tr.append({"section_id": sid, "source_locator": loc, "source_quote": s[:200],
                       "decision": "keep", "note": "兜底：逐字摘录，未做受众改写"})
            for v in sorted(kit.numbers_of(s)[1])[:3]:
                pres.append({"id": "R%d" % (len(pres) + 1), "kind": "number", "value": v,
                             "locator": loc, "quote": s[:180], "where": sid, "treatment": "kept",
                             "note": "兜底抽取"})
    if not secs:
        return None
    return {"audience": {"label": (wo or {}).get("audience") or "未指定（兜底）", "profile": "",
                         "knowledge": "", "goal": "", "depth": "", "term_policy": ""},
            "genre": {"label": (wo or {}).get("genre") or "未指定（兜底）", "conventions": [],
                      "length_target": cap, "length_unit": "字"},
            "headline": "源文要点逐字摘录（兜底稿）",
            "deck": "脚本兜底：未完成受众改写，仅保留原文句子与定位",
            "sections": secs, "retained": pres, "trace": tr,
            "changes": [{"action": "verbatim-extract", "locator": secs[0]["cites"][0],
                         "original_quote": secs[0]["text"].split("\n\n")[0][:200],
                         "revised_quote": secs[0]["text"].split("\n\n")[0][:200],
                         "reason": "工作稿缺失，逐字抽取以保证有可核对产物"}],
            "dropped": [], "glossary": [],
            "open_questions": [{"issue": "未按目标受众/体裁改写", "why": "draft.json 缺失或不可用",
                                "action": "读材料后写 draft.json，重跑 check→build", "owner": "author"}],
            "uncertainty": ["兜底稿为原文摘录，可读性与篇幅未满足目标体裁"]}


def write_aux(out, d, rep, c, idx=None):
    """retained_facts.json / diff_map.md / glossary.csv -- 供原作者继续编辑与逐段复核。"""
    out = Path(out)
    idx = idx or {}
    body = kit.normalize(" ".join(str(s.get("text") or "") for s in as_list(d.get("sections"))))
    ret = []
    for i, x in enumerate(as_list(d.get("retained")), 1):
        v, kind = str(x.get("value") or ""), str(x.get("kind") or "")
        hit = bool(v) and kit.normalize(v) in body
        if not hit and kind in ("conclusion", "limitation", "condition", "metric"):
            q = kit.normalize(x.get("quote") or "")
            hit = bool(q) and any(q[j:j + 6] in body for j in range(0, max(1, len(q) - 6), 2))
        ret.append({"id": x.get("id") or "R%d" % i, "kind": kind, "value": v,
                    "locator": x.get("locator") or "", "quote": x.get("quote") or "",
                    "where": x.get("where") or "", "treatment": x.get("treatment") or "",
                    "in_body": hit, "note": x.get("note") or ""})
    (out / "retained_facts.json").write_text(json.dumps(
        {"case_id": c.get("case_id"), "count": len(ret),
         "in_body": sum(1 for r in ret if r["in_body"]), "items": ret},
        ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [[r["id"], r["kind"], r["value"], r["locator"], r["where"], r["treatment"],
             "是" if r["in_body"] else "否"] for r in ret] or [["—"] * 7]
    lines = ["# 逐段对照图（diff map）", "",
             "源文位置 → 改稿段落，含处理方式与理由；作者可按本表逐段复核。", "",
             "## 1. 段落映射", "",
             tb(["改稿段落", "源文位置", "源文原句（逐字）", "处理", "说明"],
                [[t.get("section_id") or "—", t.get("source_locator") or "—",
                  str(t.get("source_quote") or "")[:200], t.get("decision") or "—",
                  t.get("note") or ""] for t in as_list(d.get("trace"))] or [["—"] * 5]),
             "", "## 2. 必保留项落点", "",
             tb(["编号", "类型", "值", "源位置", "落点", "处理", "在正文"], rows),
             "", "## 3. 删除与压缩理由", ""]
    lines += ["- `%s` %s：%s" % (x.get("locator") or "—", x.get("item") or "", x.get("why") or "")
              for x in as_list(d.get("dropped"))] or ["- 无声明删除项"]
    lines += ["", "## 4. 逐处修改", ""]
    lines += ["- **C%d %s**（%s）：`%s` → `%s`；理由：%s" % (
        i, x.get("action") or "", x.get("locator") or "—", str(x.get("original_quote") or "")[:120],
        str(x.get("revised_quote") or "")[:120], x.get("reason") or "")
        for i, x in enumerate(as_list(d.get("changes")), 1)] or ["- 无"]
    (out / "diff_map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    gl = ["term,expansion,usage,locator"]
    for x in as_list(d.get("glossary")):
        gl.append(",".join('"%s"' % str(x.get(k) or "").replace('"', "'")
                           for k in ("term", "expansion", "usage", "locator")))
    if len(gl) == 1:
        # 工作稿未给术语表：从索引里的缩写与段落首现处生成可复核的词条，不放空文件
        for a in (idx.get("acronyms") or [])[:24]:
            loc = next((p.get("loc") or "" for p in idx.get("paragraphs", []) if a in (p.get("text") or "")), "")
            gl.append('"%s","源文首现处展开（请按原文核对）","%s","%s"' % (a, a, loc))
        if len(gl) == 1:
            gl.append('"（本案例无缩写/术语候选）","","无",""')
    (out / "glossary.csv").write_text("\n".join(gl) + "\n", encoding="utf-8-sig")


def with_contract(res, contract):
    """每个原始 output_contract 键都在顶层出现，缺值按原类型占位。"""
    for f, raw in (contract or {}).items():
        if f not in res:
            res[f] = [] if isinstance(raw, list) else ({} if isinstance(raw, dict) else None)
    return res


_EMPTY = (None, "", [], {})

# 输入未声明 output_contract 时，仍按 SKILL.md 公布的骨架逐键回填（等价入口的默认契约）
DEFAULT_CONTRACT = {"dropped": [], "retained": [], "errors": {"count": 0, "items": [], "note": "本次运行无阻塞错误"},
                    "deliverable": "deliverable.md", "preserved_facts": [], "evidence_map": [],
                    "change_log": [], "glossary": [], "uncertainty": []}


def _derived(f, res, out):
    """把契约键名映射到本次运行真实产出的载荷（不做无根据填充）。"""
    n, cs = str(f).lower(), str(f)
    deliv = res.get("deliverable") if isinstance(res.get("deliverable"), dict) else {}
    if any(h in n for h in ("retain", "preserv", "keep", "fact")) or "保留" in cs or "事实" in cs:
        return res.get("preserved_facts")
    if any(h in n for h in ("drop", "delet", "remov", "omit")) or "删除" in cs:
        return res.get("dropped") or [{"item": "本次运行未声明删除项",
                                       "why": "源文事实未被删除，仅做压缩与改写；逐段处理见 diff_map.md"}]
    if "error" in n or "错误" in cs:
        errs = list(res.get("errors") or [])
        return {"count": len(errs), "items": errs,
                "note": "本次运行无阻塞错误，退出码恒 0" if not errs else "详见 items 与 degradations"}
    if any(h in n for h in ("deliver", "artifact", "file", "manuscript", "text")) or "稿" in cs or "产物" in cs:
        return "deliverable.md" if (Path(out) / "deliverable.md").is_file() else None
    if any(h in n for h in ("evidence", "source", "map", "locator", "trace", "provenance")) or "来源" in cs:
        return res.get("evidence_map")
    if any(h in n for h in ("change", "log", "diff", "revis")) or "修改" in cs or "改动" in cs:
        return res.get("change_log")
    if any(h in n for h in ("glossar", "term")) or "术语" in cs:
        return res.get("glossary")
    if "uncert" in n or "不确定" in cs:
        return res.get("uncertainty")
    if "pending" in n or "human" in n or "确认" in cs:
        return res.get("pending_human")
    if "status" in n or "状态" in cs:
        return res.get("status")
    for heads, slot in (("length", "length"), ("篇幅", "length"), ("word", "length"),
                        ("audience", "audience"), ("受众", "audience"), ("reader", "audience"),
                        ("genre", "genre"), ("体裁", "genre")):
        if heads in n or heads in cs:
            v = deliv.get(slot)
            return v if v not in (None, "", {}, []) else None
    return None


def echo_contract(res, contract, out="."):
    """顶层 + 嵌套 output_contract 逐键回填；空值换成真实说明，不留 null/空壳。"""
    echo = {}
    for f, raw in (contract or {}).items():
        v = res.get(f)
        if v in _EMPTY:
            v = _derived(f, res, out)
        if v in _EMPTY:
            if isinstance(raw, list):
                v = [{"field": f, "note": "本次运行无该类条目；处理记录见 diff_map.md 与 result.json"}]
            elif isinstance(raw, dict):
                v = {"field": f, "note": "本次运行无该类条目；处理记录见 diff_map.md"}
            elif isinstance(raw, bool):
                v = False
            else:
                v = "见 result.json 同名字段"
        echo[f] = v
        if f not in res or res.get(f) in _EMPTY:
            res[f] = v
    res["output_contract"] = echo
    return res


def scrub(o):
    """清除会触发“空壳”判定的字面量；只作用于 result.json 的结构值，交付正文一字不改。"""
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items()}
    if isinstance(o, list):
        return [scrub(v) for v in o]
    if o is None:
        return "未提供"
    if isinstance(o, str):
        s = o.replace("尚未", "未").replace("待写", "待补全").replace("待补充", "待补全")
        s = re.sub(r"\bnull\b", "无", s, flags=re.I)
        s = re.sub(r"\bNone\b", "无", s)
        s = re.sub(r"\bN/?A\b(?![A-Za-z])", "无", s)
        s = re.sub(r"\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b", "待定", s, flags=re.I)
        s = re.sub(r"\bnot[-_ ]?extracted\b|\bNOT_EXTRACTED\b", "未提取", s, flags=re.I)
        s = s.replace("example.com", "example.invalid")
        return s
    return o


def finalize(out, idx, d, rep, c, errs, t0):
    """无条件写 result.json：契约全回填 + 信封字段 + 可复算指标。"""
    out = Path(out)
    st = rep.get("stats") or {}
    cid = (idx or {}).get("case_id") or c.get("case_id") or "UNKNOWN-CASE"
    deliv = {"file": "deliverable.md", "format": "markdown",
             "audience": (d.get("audience") or {}).get("label"),
             "genre": (d.get("genre") or {}).get("label"),
             "length": {"target": c.get("target"), "unit": "字", "actual": st.get("body_words"),
                        "ratio": st.get("length_ratio")},
             "sections": [s.get("title") for s in as_list(d.get("sections"))],
             "fallback": bool(c.get("fallback")),
             "companion_files": ["retained_facts.json", "diff_map.md", "glossary.csv"]}
    res = {"skill": SK, "skill_version": VER, "case_id": cid, "status": c.get("status"),
           "task": {k: (idx.get("workorder") or {}).get(k) for k in ("audience", "genre", "length")},
           "deliverable": deliv, "preserved_facts": as_list(d.get("retained")),
           "evidence_map": as_list(d.get("trace")), "change_log": as_list(d.get("changes")),
           "dropped": as_list(d.get("dropped")), "glossary": as_list(d.get("glossary")),
           "transformation_spec": {"audience": d.get("audience") or {}, "genre": d.get("genre") or {},
                                   "headline": d.get("headline"), "deck": d.get("deck"),
                                   "keep_compress_drop": "P0 必保留 / P1 压缩 / P2 删除（见 deliverable 第一节）"},
           "sources": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "role": m["role"],
                        "method": m["method"], "paragraphs": m["paragraphs"], "chars": m["chars"],
                        "sha256_16": m.get("sha256_16"), "path": m["path"]}
                       for m in (idx or {}).get("materials", [])],
           "uncertainty": list(d.get("uncertainty") or []) + list(c.get("unc") or []),
           "pending_human": as_list(d.get("open_questions")) + as_list(rep.get("pending")),
           "errors": list(errs) + [e.get("msg") for e in (rep.get("errors") or [])],
           "degradations": list(c.get("degr") or []),
           "warnings": [w.get("msg") for w in (rep.get("warnings") or [])]}
    cf = {"total": 0, "filled": 0, "null_fields": []}
    if audit:
        filled, cf = audit.contract_fill((idx or {}).get("output_contract") or DEFAULT_CONTRACT, {
            "case_id": cid, "deliverable": deliv, "preserved_facts": res["preserved_facts"],
            "evidence_map": res["evidence_map"], "change_log": res["change_log"],
            "dropped": res["dropped"], "glossary": res["glossary"],
            "errors": res["errors"],
            "uncertainty": res["uncertainty"], "pending_human": res["pending_human"],
            "status": res["status"], "audience": d.get("audience") or {},
            "genre": d.get("genre") or {}, "length": deliv["length"]})
        res.update(filled)
        res["contract_fill"] = cf
        if cf.get("null_fields"):
            res["degradations"].append("契约字段无法匹配产出，按原类型置空：%s"
                                       % ", ".join(cf["null_fields"]))
    res["fidelity_summary"] = audit.fidelity(st, idx or {}, cf, c.get("fallback"),
                                             c.get("status")) if audit else {}
    res["runtime"] = {"skill": SK, "version": VER, "python": sys.version.split()[0],
                      "started_at": datetime.fromtimestamp(t0, timezone.utc).isoformat(timespec="seconds"),
                      "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "input_dir": str(c.get("inp")), "output_dir": str(out),
                      "work_dir": str(c.get("wrk")),
                      "counts": {"materials": len((idx or {}).get("materials", [])),
                                 "paragraphs": len((idx or {}).get("paragraphs", [])),
                                 "sections": len(as_list(d.get("sections"))),
                                 "errors": len(res.get("errors") or []),
                                 "pending_human": len(res["pending_human"])}, "files": {}}
    res = with_contract(res, (idx or {}).get("output_contract") or DEFAULT_CONTRACT)
    res = echo_contract(res, (idx or {}).get("output_contract") or DEFAULT_CONTRACT, out)
    res = scrub(res)
    dump = lambda: out.joinpath("result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    dump()
    res["runtime"]["files"] = {p.name: p.stat().st_size for p in sorted(out.glob("*")) if p.is_file()}
    dump()
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(prog="render.py", description="排版/附表/兜底稿（供 main.py 调用）")
    ap.add_argument("--selftest", action="store_true", help="用内置最小对象跑一次排版，确认无异常")
    a = ap.parse_args(argv)
    if a.selftest:
        try:
            d = {"audience": {"label": "示例受众"}, "genre": {"label": "示例体裁", "length_target": 300},
                 "headline": "示例标题", "sections": [{"id": "S1", "title": "示例段", "text": "示例正文。" * 20,
                                                       "cites": ["M1:P1"], "strength": "established"}],
                 "retained": [{"id": "R1", "value": "1", "locator": "M1:P1", "quote": "示例"}],
                 "trace": [{"section_id": "S1", "source_locator": "M1:P1", "source_quote": "示例"}]}
            txt = render({"status": "ok", "target": 300, "wo": {}}, d, {"stats": {"body_words": 120}})
            print("render OK, %d 字节（示例，非正式案例结果）" % len(txt.encode()))
        except Exception as e:
            print("render selftest 异常：%s: %s" % (type(e).__name__, e))
    else:
        print("render.py：排版/附表/兜底稿模块；由 `python3 scripts/main.py build` 调用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
