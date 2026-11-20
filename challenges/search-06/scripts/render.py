#!/usr/bin/env python3
"""render.py -- deterministic renderers for the literature watch desk (stdlib only).

Turns merged decision rows into the three human-facing products:
  watch_brief.md, candidates.csv, decision_trail.jsonl
Pure formatting: no judgement, no network, no input discovery.
"""
import csv
import io
import json
import time

GEN = "literature-watch-desk 1.0.0"

CSV_COLS = ["work_key", "op", "title", "doi", "arxiv_id", "venue", "published", "published_prec",
            "indexed", "version", "sources", "n_records", "relevance", "alert", "alert_group",
            "suppress_reason", "evidence_locator", "evidence_quote", "why", "verified"]


def aslist(v):
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)] if str(v or "").strip() else []


def brief_md(idx, rows, sub, win, alerts, misses, unc, cov, status, cid):
    L = ["# 追踪简报 — %s" % cid, ""]
    L += ["> 本简报由 Skill `%s` 生成。它报告的是**记录的增量变化**，不是科学结论。" % GEN, ""]
    L += ["## 0. 订阅与窗口", "",
          "| 项 | 值 |", "|---|---|",
          "| 检索式 / 研究问题 | %s |" % (sub.get("query") or "(未在输入中声明)").replace("|", "/"),
          "| 来源 | %s |" % (", ".join(aslist(sub.get("sources")) or [s["source_id"] for s in idx.get("sources") or []]) or "(none)"),
          "| 时区 | %s |" % (win.get("timezone") or "UTC"),
          "| 节奏 | %s |" % (sub.get("cadence") or "single-window run"),
          "| 窗口 | `[%s, %s)` |" % (win.get("start") or "?", win.get("end") or "?"),
          "| 窗口依据 | %s |" % ("; ".join(aslist(win.get("basis"))) or "no explicit watermark; derived from snapshot dates"),
          "| 运行状态 | %s |" % status, ""]
    L += ["## 1. 来源覆盖", "", "| 来源 | 文件 | 角色 | 记录数 | 状态 | 说明 |", "|---|---|---|---|---|---|"]
    for s in idx.get("sources") or []:
        L.append("| %s | `%s` | %s | %d | %s | %s |" % (s["source_id"], s["file"], s["role"],
                                                        s.get("n_records", 0), s.get("status"), (s.get("note") or "")[:120]))
    L += ["", "覆盖说明：" + ("；".join(cov) if cov else "无额外说明（未填写 coverage_notes）"), ""]
    order = [("new", "2. 本窗口新增"), ("update", "3. 版本更新 / 更正"), ("retract", "4. 撤稿与撤回"),
             ("late_index", "5. 延迟入库（出版早于窗口、本窗口才被索引；默认不提醒）"),
             ("seen", "6. 已见且无变化"), ("out_of_window", "7. 窗口外")]
    for op, head in order:
        sel = [r for r in rows if r["op"] == op]
        L += ["## %s（%d）" % (head, len(sel)), ""]
        if not sel:
            L += ["（无）", ""]
            continue
        if op == "seen":
            L.append("共 %d 条，均为上次快照已见且字段无变化，仅计数。" % len(sel))
            L.append("")
            continue
        if op == "out_of_window":
            L.append("共 %d 条，出版与入库都不在本窗口；不计入新增，不提醒。" % len(sel))
            L.append("")
            continue
        for i, r in enumerate(sel, 1):
            L.append("%d. **%s**" % (i, r["title"] or "(无标题记录)"))
            L.append("   - work_key: `%s` ｜ DOI: `%s` ｜ arXiv: `%s`" % (r["work_key"], r["doi"] or "-", r["arxiv"] or "-"))
            L.append("   - venue: %s ｜ published: %s (%s) ｜ first published: %s ｜ indexed(max): %s ｜ version: %s" % (
                r["venue"] or "-", r["published"] or "-", r["published_prec"] or "?",
                r.get("published_first") or r["published"] or "-", r.get("indexed_max") or r["indexed"] or "-",
                r["version"] or "-"))
            L.append("   - 来源: %s ｜ 原始记录 %d 条%s" % (", ".join(r["sources"]), r["n_records"],
                                                    "（%d 条重复副本已合并）" % len(r["duplicates"]) if r["duplicates"] else ""))
            if r["baseline"]:
                L.append("   - 上一次快照: `%s` venue=%s version=%s published=%s" % (
                    r["baseline"].get("locator"), r["baseline"].get("venue") or "-",
                    r["baseline"].get("version") or "-", r["baseline"].get("published") or "-"))
            if r["change_signals"]:
                L.append("   - 变化信号: %s" % ", ".join(r["change_signals"]))
            L.append("   - 相关性: %s ｜ 依据: %s" % (r["relevance"], r["why"] or "(未填写依据)"))
            L.append("   - 证据: `%s` ｜ 逐字: \"%s\"" % (r["evidence"]["locator"], (r["evidence"]["quote"] or "")[:300]))
            L.append("   - 提醒: %s%s" % ("是" if r["alert"] else "否",
                                          "（组 %s）" % r["alert_group"] if r["alert"] and r["alert_group"] else ""))
            if not r["alert"] and r["suppress_reason"]:
                L.append("   - 抑制理由: %s" % r["suppress_reason"])
            L.append("")
    L += ["## 8. 提醒投递计划", ""]
    if alerts:
        for g in alerts:
            L.append("- **%s** %s ｜ members: %s ｜ 方式: %s ｜ 合并理由: %s" % (
                g.get("group_id"), g.get("title") or "", ", ".join(g.get("members") or []),
                g.get("delivery") or "digest", g.get("merge_reason") or g.get("reason") or "-"))
    else:
        L.append("(无提醒组：本窗口无 new/update/retract 条目，或 draft 未定义 alert_groups)")
    L += ["", "被抑制的条目见第 6/7 节与 `decision_trail.jsonl` 的 `suppress_reason` 字段——抑制留痕，便于复核区分"
              "“没发现”与“故意不推”。", ""]
    L += ["## 9. 遗漏、冲突与不确定", ""]
    L.append("**遗漏 / 缺口**：" + ("；".join(misses) if misses else "无（或未填写）"))
    L.append("")
    L.append("**不确定**：" + ("；".join(unc) if unc else "无（或未填写）"))
    L += ["", "## 10. 复算步骤", "",
          "```bash",
          "python3 scripts/main.py init    # 重建索引（输入指纹见 result.json.fingerprints.input）",
          "python3 scripts/main.py show    # 复核窗口、来源与每个 work 的 before/after",
          "python3 scripts/main.py check   # 复核契约、覆盖、逐字引文与计数恒等",
          "python3 scripts/main.py build   # 重放同一窗口，得到同一 decision_trail",
          "```", "",
          "计数对账：%s" % json.dumps({k: v for k, v in cov_counts(rows).items() if isinstance(v, int)}, ensure_ascii=False), ""]
    return "\n".join(L)


def cov_counts(rows):
    by = {o: sum(1 for x in rows if x["op"] == o)
          for o in ("new", "update", "retract", "late_index", "seen", "out_of_window")}
    c = {"records_total": sum(x["n_records"] for x in rows), "works_total": len(rows),
         "alerted": sum(1 for x in rows if x["alert"])}
    c.update(by)
    return c


def trail_rows(rows, case_id):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = []
    for r in rows:
        out.append({
            "ts": ts, "case_id": case_id, "work_key": r["work_key"], "op": r["op"], "auto_op": r["auto_op"],
            "op_differs_from_mechanical": r["op"] != r["auto_op"],
            "title": r["title"], "doi": r["doi"], "arxiv": r["arxiv"], "venue": r["venue"],
            "published": r["published"], "published_prec": r["published_prec"],
            "published_first": r.get("published_first") or r["published"],
            "indexed": r.get("indexed_max") or r["indexed"],
            "version": r["version"], "sources": r["sources"], "n_records": r["n_records"],
            "before": r["baseline"], "after": {"doi": r["doi"], "venue": r["venue"], "version": r["version"],
                                               "published": r["published"], "locator": r["evidence"]["locator"]},
            "change_signals": r["change_signals"], "duplicates": r["duplicates"],
            "decision": {"relevance": r["relevance"], "why": r["why"], "alert": r["alert"],
                         "alert_group": r["alert_group"], "suppress_reason": r["suppress_reason"]},
            "evidence": r["evidence"], "quote_verified": r["quote_verified"],
            "mechanical_reasons": r["auto_reasons"], "reviewed": r["reviewed"],
        })
    return out




def csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in rows:
        w.writerow([r["work_key"], r["op"], r["title"], r["doi"], r["arxiv"], r["venue"],
                    r["published"], r["published_prec"], r["indexed"], r["version"],
                    ";".join(r["sources"]), r["n_records"], r["relevance"],
                    "true" if r["alert"] else "false", r["alert_group"], r["suppress_reason"],
                    r["evidence"]["locator"], r["evidence"]["quote"], r["why"],
                    "true" if r["quote_verified"] else "false"])
    return buf.getvalue()


def jsonl_text(rows):
    return "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in rows)
