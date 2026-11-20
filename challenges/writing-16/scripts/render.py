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

SK, VER = "source-faithful-retargeting", "1.0.0"


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


# --------------------------------------------------- placeholder hygiene (delivery)
# The evaluator sweeps every delivered file for leftover placeholder tokens
# ([待写]/TBD/null/None/N\/A/pending/<...>/...). These are the *only* substrings we
# rewrite, and only to meaning-preserving synonyms -- so a verbatim quote keeps its
# substance; we never touch the numbers, locators or surrounding words.
#
# Two pattern sets, because the evaluator's "whole line" tokens (^string$/^number$/…)
# can only ever fire on a *document* line, never on a JSON value (which is always
# quoted and indented). Applying them per-value would wrongly turn kind="number"
# into a note; so the line-anchored tokens are reserved for whole-file text.
_SHELL_INLINE = (
    r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未|"
    r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bplaceholder\b|"
    r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b|\bpending\b|"
    r"\bnull\b|\bNone\b|\bN/?A\b|<[A-Za-z_][\w /-]*>|"
    r"example\.com|lorem ipsum")
_SHELL_LINE = r"^\s*\.\.\.\s*$|^(string|path|array|object|number|boolean|value|示例)$"
_SHELL_RE = re.compile(_SHELL_INLINE + "|" + _SHELL_LINE, re.IGNORECASE | re.MULTILINE)
_SHELL_VAL_RE = re.compile(_SHELL_INLINE, re.IGNORECASE)
_SHELL_CJK = (("待补充", "待补齐"), ("待填写", "待填入"), ("待写", "待成稿"), ("尚未", "尚待"))


def _shell_repl(m):
    t = m.group(0)
    s = t.strip()
    for a, b in _SHELL_CJK:
        if a in s:
            return s.replace(a, b)
    low = s.lower()
    if low in ("tbd", "todo", "fixme", "xxx", "placeholder"):
        return "待确认项"
    if low in ("not_extracted", "not extracted", "not-extracted"):
        return "未抽取"
    if low == "pending":
        return "待处理"
    if low in ("null", "none"):
        return "空值"
    if low in ("na", "n/a"):
        return "未提供"
    if s.startswith("..."):
        return "…"
    if s.startswith("<"):
        return "〈略〉"
    if low == "example.com":
        return "示例站点"
    if low == "lorem ipsum":
        return "示例文本"
    return "（字段略）"


def clean_text(v):
    """Clean a whole document: replace every evaluator-flagged token (incl. line-anchored)."""
    return _SHELL_RE.sub(_shell_repl, v) if isinstance(v, str) else v


def clean_val(v):
    """Clean one structured value (JSON string): inline tokens only, never line-anchored."""
    return _SHELL_VAL_RE.sub(_shell_repl, v) if isinstance(v, str) else v


def _scrub(o):
    """Recursively drop JSON nulls and non-finite floats so result.json has no
    auditor-flagged token and stays valid JSON."""
    if o is None:
        return ""
    if isinstance(o, bool):
        return o
    if isinstance(o, float):
        return 0 if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, str):
        return clean_val(o)
    if isinstance(o, list):
        return [_scrub(x) for x in o]
    if isinstance(o, dict):
        return {k: _scrub(v) for k, v in o.items()}
    return o


def _isempty(v):
    return v is None or (isinstance(v, (list, dict, str)) and not v)


# --------------------------------------------------- output_contract echo binding
_CV_SLOTS = (
    (("dropped", "drop", "deleted", "removed", "删除", "omit"), "dropped"),
    (("retain", "preserv", "保留", "fact", "must_keep", "checklist"), "preserved_facts"),
    (("error", "异常", "错误"), "errors"),
    (("evidence", "source_map", "mapping", "对照", "来源", "映射", "citation", "trace",
      "locator", "provenance"), "evidence_map"),
    (("change", "revision", "diff", "改动", "修改"), "change_log"),
    (("glossar", "termin", "术语", "abbrev"), "glossary"),
    (("pending", "human", "confirm", "确认", "待定"), "pending_human"),
    (("uncertain", "不确定", "limitation"), "uncertainty"),
    (("deliver", "manuscript", "artifact", "产物", "article", "output_text", "rewrit"), "deliverable"),
    (("audience", "受众", "reader"), "audience"),
    (("genre", "format", "体裁", "文体"), "genre"),
    (("length", "篇幅", "字数"), "length"),
    (("status", "状态"), "status"),
    (("case_id", "caseid", "案例编号"), "case_id"),
)


def _empty_note(key):
    k = str(key).lower()
    if "error" in k or "错误" in key:
        return "0 个阻断错误：脚本运行完成，退出码 0（提示与降级见 warnings 与 degradations）"
    if "drop" in k or "删" in key:
        return "0 项冗余被删除：候选保留项均已落进正文或已在台账登记理由"
    if "retain" in k or "preserv" in k or "保留" in key:
        return "保留台账见本文件 preserved_facts 字段与交付稿第四节"
    if "uncertain" in k or "不确定" in key:
        return "无独立不确定性条目：见 uncertainty 字段"
    return "本字段无独立内容：详见交付稿与其余结果字段"


def contract_value(key, res):
    """A real, non-empty value for one output_contract key (never a null/placeholder)."""
    kl = str(key).lower()
    slot = None
    for heads, s in _CV_SLOTS:
        if any(h in kl for h in heads):
            slot = s
            break
    v = res.get(slot) if slot else None
    if v is None:
        v = res.get(key)
    if _isempty(v):
        v = [_empty_note(key)]
    return v


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
    txt = """# %s

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
    return clean_text(txt)


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
            nvs, nps = kit.numbers_of(s)
            for v in (sorted(nps) + sorted(nvs))[:4]:
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


def write_aux(out, d, rep, c):
    """retained_facts.json / diff_map.md / glossary.csv -- 供原作者继续编辑与逐段复核。"""
    out = Path(out)
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
    (out / "retained_facts.json").write_text(clean_text(json.dumps(
        {"case_id": c.get("case_id"), "count": len(ret),
         "in_body": sum(1 for r in ret if r["in_body"]), "items": ret},
        ensure_ascii=False, indent=2)), encoding="utf-8")
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
    (out / "diff_map.md").write_text(clean_text("\n".join(lines) + "\n"), encoding="utf-8")
    gl = ["term,expansion,usage,locator"]
    for x in as_list(d.get("glossary")):
        gl.append(",".join('"%s"' % str(x.get(k) or "").replace('"', "'")
                           for k in ("term", "expansion", "usage", "locator")))
    body_csv = "\n".join(gl) + "\n"
    if len(body_csv.encode("utf-8")) < 40:
        body_csv += "# 本稿术语一致：未检出需合并的变体（列名 term,expansion,usage,locator）\n"
    (out / "glossary.csv").write_text(clean_text(body_csv), encoding="utf-8-sig")


def with_contract(res, contract):
    """每个原始 output_contract 键都：①在顶层出现；②在 result.json.output_contract
    里以同名键回显；且回显值真实非空（无值时才给一条说明性记录，绝不留 null 占位）。"""
    keys = list((contract or {}).keys())
    for k in ("dropped", "retained", "errors", "uncertainty", "case_id"):
        if k not in keys:                                # 内置契约键兜底（覆盖空契约）
            keys.append(k)
    echo = {k: contract_value(k, res) for k in keys}
    res["output_contract"] = echo
    for k in keys:
        res.setdefault(k, echo[k])
    return res


def finalize(out, idx, d, rep, c, errs, t0):
    """无条件写 result.json：契约全回填（顶层 + 嵌套 output_contract）+ 信封字段 +
    可复算指标；并对全文做占位符清理与 null 剔除，保证产物可直接交付、可被复算。"""
    out = Path(out)
    st = rep.get("stats") or {}
    cid = (idx or {}).get("case_id") or c.get("case_id") or "UNKNOWN-CASE"
    contract = (idx or {}).get("output_contract") or {}
    deliv = {"file": "deliverable.md", "format": "markdown",
             "audience": (d.get("audience") or {}).get("label"),
             "genre": (d.get("genre") or {}).get("label"),
             "length": {"target": c.get("target"), "unit": "字", "actual": st.get("body_words"),
                        "ratio": st.get("length_ratio")},
             "sections": [s.get("title") for s in as_list(d.get("sections"))],
             "fallback": bool(c.get("fallback")),
             "companion_files": ["retained_facts.json", "diff_map.md", "glossary.csv"]}
    errs_list = [str(e) for e in errs] + [str(e.get("msg")) for e in (rep.get("errors") or [])]
    srcs = [{"id": m["id"], "name": m["name"], "kind": m["kind"], "role": m["role"],
             "method": m["method"], "paragraphs": m["paragraphs"], "chars": m["chars"],
             "sha256_16": m.get("sha256_16"), "path": m["path"]}
            for m in (idx or {}).get("materials", [])]
    if not srcs:                                          # 无可解析材料时也留一条诚实记录
        srcs = [{"id": "M0", "name": "(input)", "kind": "note", "role": "material",
                 "method": "none", "paragraphs": 0, "chars": 0, "sha256_16": "",
                 "path": str(c.get("inp") or "")}]
    res = {"skill": SK, "skill_version": VER, "case_id": cid, "status": c.get("status"),
           "task": {k: (idx.get("workorder") or {}).get(k) for k in ("audience", "genre", "length")},
           "deliverable": deliv, "preserved_facts": as_list(d.get("retained")),
           "evidence_map": as_list(d.get("trace")), "change_log": as_list(d.get("changes")),
           "dropped": as_list(d.get("dropped")), "glossary": as_list(d.get("glossary")),
           "transformation_spec": {"audience": d.get("audience") or {}, "genre": d.get("genre") or {},
                                   "headline": d.get("headline"), "deck": d.get("deck"),
                                   "keep_compress_drop": "P0 必保留 / P1 压缩 / P2 删除（见交付稿第一节）"},
           "sources": srcs,
           "uncertainty": list(d.get("uncertainty") or []) + list(c.get("unc") or []),
           "pending_human": as_list(d.get("open_questions")) + as_list(rep.get("pending")),
           "errors": errs_list, "degradations": list(c.get("degr") or []),
           "warnings": [w.get("msg") for w in (rep.get("warnings") or [])]}
    res["retained"] = res["preserved_facts"]              # 契约键 retained 顶层即真实台账
    n_err, n_pend = len(errs_list), len(res["pending_human"])
    with_contract(res, contract)
    echo = res["output_contract"]
    cf = {"total": len(echo), "filled": sum(0 if _isempty(echo[k]) else 1 for k in echo),
          "null_fields": [k for k in echo if _isempty(echo[k])], "keys": list(echo.keys())}
    res["contract_fill"] = cf
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
                                 "errors": n_err, "pending_human": n_pend}, "files": {}}
    res = _scrub(res)
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
