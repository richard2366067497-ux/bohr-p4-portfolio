#!/usr/bin/env python3
"""writing-15 | render layer: consistency report Markdown, HTML preview, real PDF preview,
unified diff. Pure standard library; never raises on content, only on I/O which callers guard.
"""
from __future__ import annotations

import difflib
import html as _html
import re

def _clip(s, n=180):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1] + "…"

def _cell(s, n=110):
    return _clip(s, n).replace("|", "\\|")

def unified_diff(a: str, b: str, name: str = "revised_manuscript.md") -> str:
    d = difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(),
                             fromfile="v1_original/" + name, tofile="v2_revised/" + name,
                             lineterm="", n=2)
    out = list(d)
    head = ("# unified diff v1 -> v2 (%d hunk lines)\n"
            "# only inserted annotation blocks should appear as '+' lines\n" % len(out))
    return head + "\n".join(out) + "\n"

def consistency_md(cons: dict, meta: dict) -> str:
    cons = cons or {}
    led = cons.get("ledgers") or {}
    counts = cons.get("counts") or {}
    comp = cons.get("computed_findings") or []
    agent = cons.get("agent_findings") or []
    impact = cons.get("impact") or {}
    st = (meta.get("stats") or {})
    L = []
    A = L.append
    A("# 跨章节一致性报告（%s）\n" % (meta.get("case_id") or "-"))
    A("生成：longdoc-source-ledger %s ｜ 状态：`%s` ｜ 材料 %s 份 / 块 %s 个\n"
      % ("1.0.0", meta.get("status") or "-", st.get("materials", "-"), st.get("blocks", "-")))
    A("> 本报告分两层：**机械台账/候选**（`basis: computed`，正则可复算，但不是语义结论）与"
      "**Agent 科学核验**（`basis: agent_review`，逐条读原文后写下的判断）。"
      "任务书明确：机械清单本身不构成科学核验，因此两层不合并、不互相替代。\n")
    A("## 1. 工单执行与定位\n")
    A("| target | 状态 | locator | 注记 | 受影响段落 |")
    A("|---|---|---|---|---|")
    for t in meta.get("targets") or []:
        A("| `%s` | %s | %s | %s | %s |" % (t.get("target_id"), t.get("status"),
                                            _cell(t.get("locator") or "-", 90),
                                            t.get("annotation_id") or "-",
                                            len(t.get("affects") or [])))
    A("")
    A("## 2. 机械台账（候选线索，需判读）\n")
    A("行数统计：%s\n" % "，".join("%s=%s" % (k, v) for k, v in counts.items()))
    terms = led.get("terms") or []
    if terms:
        A("### 2.1 术语与缩写\n")
        A("| 缩写 | 展开式 | 出现次数 | 首次定义 |")
        A("|---|---|---|---|")
        for r in terms[:25]:
            A("| `%s` | %s | %s | %s |" % (r.get("abbrev"), _cell("; ".join(r.get("expansions") or []), 90),
                                           r.get("uses", "-"), _cell(r.get("defined_at") or "-", 70)))
        A("")
    syms = led.get("symbols") or []
    if syms:
        A("### 2.2 符号\n")
        A("| 符号 | 含义 | 定义处 |")
        A("|---|---|---|")
        for r in syms[:20]:
            A("| `%s` | %s | %s |" % (r.get("symbol"), _cell("; ".join(r.get("meanings") or []), 90),
                                      _cell("; ".join(r.get("defined_at") or []), 80)))
        A("")
    defs = led.get("definitions") or []
    if defs:
        A("### 2.3 定义\n")
        A("| 术语 | 出现次数 | 不同措辞 | 位置 |")
        A("|---|---|---|---|")
        for r in defs[:20]:
            A("| %s | %s | %s | %s |" % (_cell(r.get("term"), 40), r.get("occurrences", "-"),
                                         r.get("distinct_wording", "-"),
                                         _cell("; ".join(r.get("locators") or []), 90)))
        A("")
    nums = led.get("numbering") or []
    if nums:
        A("### 2.4 图表与公式编号\n")
        A("| 类别 | 引用到的编号 | 题注编号 | 重号 | 断号 | 引用但无题注 |")
        A("|---|---|---|---|---|---|")
        for r in nums:
            A("| %s | %s | %s | %s | %s | %s |" % (r.get("family"),
                                                   _cell(r.get("references"), 60), _cell(r.get("captions"), 60),
                                                   _cell(r.get("duplicate_captions"), 30),
                                                   _cell(r.get("gaps"), 40),
                                                   _cell(r.get("referenced_without_caption"), 40)))
        A("")
    cits = (led.get("citations") or [{}])[0] or {}
    if cits:
        A("### 2.5 引用锚点\n")
        A("- 文献表：%s" % ("找到" if cits.get("bibliography_found") else "**未找到**（引用完整性无法从材料确认）"))
        A("- 正文引用编号：%s" % (_clip(", ".join(str(x) for x in cits.get("in_text_numbers") or []) or "无", 200)))
        A("- 文献表编号：%s" % (_clip(", ".join(str(x) for x in cits.get("listed_numbers") or []) or "无", 200)))
        A("- 引而未列：%s ｜ 列而未引：%s"
          % (_clip(", ".join(str(x) for x in cits.get("cited_not_listed") or []) or "-",
                   120), _clip(", ".join(str(x) for x in cits.get("listed_not_cited") or []) or "-", 120)))
        ph = cits.get("placeholders") or []
        if ph:
            A("- 占位符：%s" % "; ".join("%s@%s" % (p.get("token"), _clip(p.get("locator"), 60)) for p in ph))
        A("")
    claims = led.get("claims") or []
    if claims:
        A("### 2.6 结论性陈述\n")
        A("| locator | 极性 | 带量值 | 句子 |")
        A("|---|---|---|---|")
        for r in claims[:20]:
            A("| %s | %s | %s | %s |" % (_cell(r.get("locator"), 60), r.get("polarity"),
                                         "是" if r.get("has_quantity") else "否", _cell(r.get("sentence"), 120)))
        A("")
    A("## 3. Agent 科学核验发现（agent_review）\n")
    if agent:
        for f in agent:
            A("- **[%s/%s] %s**" % (f.get("category"), f.get("severity"), _clip(f.get("statement"), 220)))
            if f.get("locator_a"):
                A("  - A：`%s` — “%s”" % (f.get("locator_a"), _clip(f.get("quote_a"), 160)))
            if f.get("locator_b"):
                A("  - B：`%s` — “%s”" % (f.get("locator_b"), _clip(f.get("quote_b"), 160)))
            A("  - 决定人：%s%s" % (f.get("decision_owner") or "author",
                                   ("；建议：" + _clip(f.get("note"), 120)) if f.get("note") else ""))
        A("")
    else:
        A("> **本次未提供 Agent 判读发现。** 下面的机械候选不能替代科学核验；"
          "这是完整性上的已知缺口，已同时写入 result.json 的 `uncertainty`。\n")
    A("## 4. 机械候选（computed，需人工判读）\n")
    if comp:
        by_cat = {}
        for f in comp:
            by_cat.setdefault(f.get("category") or "other", []).append(f)
        for cat, rows in by_cat.items():
            A("### %s（%d 条）\n" % (cat, len(rows)))
            for f in rows[:12]:
                A("- [%s] %s" % (f.get("severity"), _clip(f.get("statement") or "", 240)))
                if f.get("locator_a"):
                    A("  - A `%s`：%s" % (_clip(f.get("locator_a"), 80), _clip(f.get("quote_a"), 140)))
                if f.get("locator_b"):
                    A("  - B `%s`：%s" % (_clip(f.get("locator_b"), 80), _clip(f.get("quote_b"), 140)))
            A("")
    else:
        A("> 机械扫描未产生候选（正则未命中不等于不存在，见第 6 节口径说明）。\n")
    A("## 5. 受影响段落回链\n")
    any_imp = False
    for tid, rows in impact.items():
        if not rows:
            continue
        any_imp = True
        A("- `%s` 改动后需一并查看：" % tid)
        for r in rows:
            A("  - `%s`（共享：%s）" % (r.get("locator"), ", ".join((r.get("shared_terms") or [])[:5]) or "-"))
    if not any_imp:
        A("> 无可计算回链（材料过短或术语不重叠）。")
    A("")
    A("## 6. 口径与限制\n")
    A("- 台账由正则与统计得出，可复算但不理解语义；一行冲突代表「需要看一眼」，不代表作者出错。")
    A("- 数值只比较字面量，不做单位换算；含糊单位只记录、不静默纠正；编号/文献缺失只报「无法核对」。")
    A("- 结论极性由否定词近似判定，跨章对比用词汇重叠阈值，可能漏检大幅改写的句子。")
    A("- 所有 `decision_owner` 非 editor 的行都留给作者或人工确认，报告不替代作者判断。\n")
    return "\n".join(L) + "\n"

def html_preview(text: str, meta: dict) -> str:
    body = _html.escape(text or "")
    body = re.sub(r"^(.*> \*\*〔.*〕\*\*)$", r"<span class='ann'>\1</span>", body, flags=re.M)
    css = ("body{font:14px/1.65 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:0;"
           "background:#f6f7f9;color:#1b1d21}"
           ".wrap{max-width:980px;margin:0 auto;padding:24px}"
           ".meta{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:12px 16px;"
           "margin-bottom:16px;font-size:13px;color:#444}"
           "pre{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:18px;"
           "white-space:pre-wrap;word-break:break-word;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}"
           ".ann{color:#0b6b3a;font-weight:600}")
    return ("<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
            "<title>%s · revised manuscript</title><style>%s</style></head><body><div class='wrap'>"
            "<div class='meta'>case <b>%s</b> ｜ skill %s %s ｜ status <b>%s</b> ｜ "
            "green lines are inserted annotations; all other lines are author text</div>"
            "<pre>%s</pre></div></body></html>"
            % (_html.escape(str(meta.get("case_id") or "-")), css,
               _html.escape(str(meta.get("case_id") or "-")), _html.escape(str(meta.get("skill") or "")),
               _html.escape(str(meta.get("version") or "")), _html.escape(str(meta.get("status") or "")), body))

def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

def pdf_preview(lines, title: str = "revised manuscript", per_page: int = 58, width: int = 96) -> bytes:
    wrapped = []
    for ln in (lines or [""]):
        s = str(ln).encode("ascii", "replace").decode("ascii").rstrip()
        if not s:
            wrapped.append("")
            continue
        while len(s) > width:
            wrapped.append(s[:width])
            s = s[width:]
        wrapped.append(s)
    head = ["%s | generated by longdoc-source-ledger 1.0.0" % str(title)[:80],
            "CJK glyphs are not embeddable without a font file and appear as '?';",
            "preview.html and revised_manuscript.md are authoritative for those characters.",
            "-" * 60, ""]
    wrapped = head + wrapped
    pages = [wrapped[i:i + per_page] for i in range(0, max(len(wrapped), 1), per_page)] or [[""]]
    objs = {}
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    page_ids, next_id = [], 4
    for page in pages:
        pid, cid = next_id, next_id + 1
        next_id += 2
        page_ids.append((pid, cid, page))
    kids = " ".join("%d 0 R" % pid for pid, _, _ in page_ids)
    objs[2] = ("<< /Type /Pages /Count %d /Kids [%s] >>" % (len(page_ids), kids)).encode()
    for pid, cid, page in page_ids:
        objs[pid] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                     "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % cid).encode()
        parts = ["BT", "/F1 8.5 Tf", "40 800 Td", "11.4 TL"]
        for ln in page:
            parts.append("(%s) Tj" % _pdf_escape(ln))
            parts.append("T*")
        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1", "replace")
        objs[cid] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for oid in sorted(objs):
        offsets[oid] = len(out)
        out += ("%d 0 obj\n" % oid).encode() + objs[oid] + b"\nendobj\n"
    xref = len(out)
    n = max(objs) + 1
    out += ("xref\n0 %d\n" % n).encode()
    out += b"0000000000 65535 f \n"
    for oid in range(1, n):
        out += ("%010d 00000 n \n" % offsets.get(oid, 0)).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xref)).encode()
    return bytes(out)
