#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""federated-search-reconcile :: render layer (five pieces + contract).

Renders the five deliverable pieces (intake_ledger.md, query_matrix.csv,
normalize_rules.json, merge_cluster.jsonl, reconciliation.md) and fills the
output_contract semantically.
Stdlib only, offline, no CWD dependency.
"""
import csv, io, json, re
from pathlib import Path

import ledger as L
import matrix as M

V = "1.0.0"
COV = M.COV
MARK = {"present": "P", "missing": "M", "suspect": "S", "unknown": "U"}
PIECES = ("intake_ledger.md", "query_matrix.csv", "normalize_rules.json",
          "merge_cluster.jsonl", "reconciliation.md")


def w(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")
    return p


# ------------------------------------------------------------------- renderers
def render_ledger(idx, clusters):
    o = ["# 材料台账（intake ledger）", "",
         "本文件记录本次联合检索实际读到的每个输入响应：格式指纹、库归属依据、解析出的记录数、失败标记。",
         "所有数字来自对原始文件的解析；未读到的文件不会出现在记录表里，失败响应单独成行，不做补造。", "",
         "## 1. case 与题面", "", "| 项 | 值 |", "|---|---|",
         "| case_id | `%s` |" % (idx["case"].get("case_id") or "null"),
         "| case 来源 | `%s` |" % (idx.get("case_from") or "none"),
         "| task.md | %s |" % (("`task.md` %d 字符, sha256 `%s`" % (idx["task_md"]["chars"],
                                                                     idx["task_md"]["sha256"]))
                              if idx.get("task_md") else "缺失"),
         "| 材料文件 | %d |" % len(idx["files"]),
         "| 解析出记录 | %d |" % len(idx["records"]),
         "| 识别到的库 | %d（%s） |" % (len({r["db"] for r in idx["records"]}),
                                  ", ".join(sorted({r["db"] for r in idx["records"]})) or "none"), ""]
    if idx["case"].get("task_instruction"):
        o += ["**task_instruction（原文摘录）**：", "", "> " + L.clip(idx["case"]["task_instruction"], 600), ""]
    o += ["## 2. 响应文件清单", "",
          "| # | 路径 | 字节 | sha256 | 格式 | 形状 | 库 | 记录数 | 说明 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for i, f in enumerate(idx["files"], 1):
        o.append("| %d | `%s` | %d | `%s` | %s | %s | %s | %d | %s |"
                 % (i, f["path"], f["bytes"], f["sha256"], f["kind"], f.get("shape") or "-",
                    f["db"], f["n_records"], L.clip(f.get("note") or "-", 80)))
    o += ["", "库归属依据：文件名元词优先，否则用响应形状指纹（`message.items`→Crossref、"
          "`resultList.result`→EuropePMC、`search-results.entry`→Scopus、`Data.Records`→WoS 等）。", "",
          "## 3. 失败或不完整的响应", ""]
    if idx.get("failures"):
        o += ["| 路径 | 库 | HTTP/错误 | 判定 |", "|---|---|---|---|"]
        for f in idx["failures"]:
            o.append("| `%s` | %s | %s | %s |" % (f.get("path"), f.get("db"),
                                                 f.get("http_status") or "-", L.clip(f.get("reason"), 120)))
    else:
        o.append("本次未检测到 429/403/5xx 或错误结构的响应。")
    o += ["", "## 4. 记录级字段可得性（前 40 条）", "",
          "| rid | 库 | locator | title | authors | year | venue | doi | abstract | 完整度 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in idx["records"][:40]:
        o.append("| %s | %s | `%s` | %s | %s | %s | %s | %s | %s | %d/6 |"
                 % (r["rid"], r["db"], r["locator"][:70],
                    *[MARK.get((r["fields"].get(f) or {}).get("state"), "?") for f in COV],
                    r["completeness"]))
    o += ["", "图例：P=present，M=missing（该库 schema 应有而此记录没有），S=suspect（有值但形状可疑），"
          "U=unknown（结构未识别，无法判断）。", ""]
    return "\n".join(o)


def render_query_csv(rows):
    buf = io.StringIO()
    cols = ["db", "topic_terms", "field_scope", "time_window", "paging", "query_sent", "query_origin",
            "evidence_locator", "calls", "returned", "unique_clusters", "status", "note"]
    wr = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    wr.writeheader()
    for r in rows:
        wr.writerow(r)
    return buf.getvalue()


def render_rules(idx, draft, dbs):
    def paths(f):
        return {db: (L.ADAPTERS.get(db, {}).get(f) or ["<synonym match>"]) for db in sorted(dbs)}
    rules = [
        {"rule_id": "N-01", "field": "title", "semantic": "题名；去 HTML/JATS 标签、归一空白",
         "precedence": "非 suspect > 库优先级 > 字符串更长", "source_paths": paths("title"),
         "rationale": "出版商原始题名通常最完整；聚合器可能截断或补写副标题"},
        {"rule_id": "N-02", "field": "authors", "semantic": "作者列表；family+given 优先于整串 fullName",
         "precedence": "结构化 family/given > 库优先级 > 作者数更多", "source_paths": paths("authors"),
         "rationale": "EuropePMC fullName 与 Crossref family/given 不能直接比字符串，需归一到 'Family, Given'"},
        {"rule_id": "N-03", "field": "year", "semantic": "出版年（四位整数）；issued/coverDate 视为版本年",
         "precedence": "库优先级（出版商/Crossref > 聚合器），同级取更早年份", "source_paths": paths("year"),
         "rationale": "各库年份口径不同，冲突必须登记为 conflicts，而不是静默取第一个"},
        {"rule_id": "N-04", "field": "venue", "semantic": "期刊/会议/丛书名；取完整刊名而非缩写",
         "precedence": "非 suspect > 库优先级 > 长度", "source_paths": paths("venue"),
         "rationale": "缩写刊名会让同一期刊在不同库里看起来像两个来源"},
        {"rule_id": "N-05", "field": "doi", "semantic": "DOI 归一为小写纯标识（去 https://doi.org/ 前缀）",
         "precedence": "Crossref 注册机构形态优先，其余库 DOI 作校验", "source_paths": paths("doi"),
         "rationale": "DOI 大小写/前缀在各库不一致但指向同一注册记录；不一致按冲突登记"},
        {"rule_id": "N-06", "field": "abstract", "semantic": "摘要纯文本；过短视为 suspect",
         "precedence": "库优先级 > 长度（保留最长可得版本）", "source_paths": paths("abstract"),
         "rationale": "部分库只给摘要前若干字，长版本更接近原文，但差异需保留在 conflicts"},
        {"rule_id": "N-07", "field": "identifiers", "semantic": "doi/pmid/pmcid/arxiv 分别保留，不做跨族换算",
         "precedence": "各自独立字段", "source_paths": {"pmid": "europepmc:pmid / openalex:ids.pmid",
                                                        "pmcid": "europepmc:pmcid", "arxiv": "arxiv:arxivId"},
         "rationale": "没有原始证据的 id 换算等于编造标识符"},
        {"rule_id": "N-08", "field": "missing_vs_unknown", "semantic": "缺失与未知分开记录",
         "precedence": "-", "source_paths": {},
         "rationale": "missing=该库 schema 应有而本记录没有；unknown=结构未识别、无法判断；合并两者会让覆盖报告失真"},
        {"rule_id": "N-09", "field": "other", "semantic": "volume/issue/pages/type/url 等附加字段",
         "precedence": "非 suspect > 库优先级", "source_paths": {},
         "rationale": "附加字段用于核对卷期页码一致性，不参与去重投票"},
    ]
    over = []
    for i, o in enumerate((draft.get("normalization_overrides") or []), 1):
        if isinstance(o, dict):
            over.append({"rule_id": "O-%02d" % i, "origin": "agent", "supersedes": o.get("rule_id"),
                         "db": o.get("db"), "field": o.get("field"),
                         "semantic": o.get("semantic") or o.get("text"),
                         "reason": o.get("reason"), "locator": o.get("locator")})
    return {"schema": "federated-search-reconcile/normalize_rules@1", "version": V,
            "generated_from": idx.get("case_from"),
            "dedup": {"blocking": ["doi_equal", "identifier_family", "first_author_surname+year", "title_bigram"],
                      "votes": [{"signal": "doi_equal", "weight": 3},
                                {"signal": "id_family_equal(pmid/pmcid/arxiv)", "weight": 2},
                                {"signal": "title_similarity>=0.92", "weight": 2},
                                {"signal": "title_similarity in [0.80,0.92)", "weight": 1},
                                {"signal": "first_author_surname+year_equal", "weight": 1}],
                      "thresholds": {"duplicate": ">=4", "maybe": "==3 (需 agent/人工仲裁)",
                                     "distinct": "<=2"},
                      "similarity": "max(difflib.SequenceMatcher.ratio, token Jaccard) over normalised titles"},
            "field_states": {"present": "parsed and passes shape check",
                             "suspect": "parsed but shape check failed",
                             "missing": "schema expects the field, record has none",
                             "unknown": "structure unattributed/truncated, presence undecidable"},
            "db_priority": dict(sorted(M.PRIO.items(), key=lambda kv: -kv[1])),
            "rules": rules, "agent_overrides": over,
            "note": "跨库字段映射的机器可读版本；新增库只需扩展 source_paths，不必改脚本业务逻辑。"}


def render_clusters(merged, decided):
    lines = []
    for c in merged:
        pairs = [d for d in decided.values()
                 if d.get("final_decision") in ("duplicate", "maybe")
                 and d["a"] in c["member_ids"] and d["b"] in c["member_ids"]]
        row = {"cluster_id": c["cluster_id"], "rank": c.get("rank"),
               "relevance": c.get("relevance"),
               "canonical": c["canonical"],
               "source_dbs": c["source_dbs"],
               "members": [{"rid": m["rid"], "db": m["db"], "locator": m["locator"],
                            "raw_id": m.get("raw_id") or "", "raw_sha": m["raw_sha"],
                            "raw": m["raw"], "completeness": m["completeness"]}
                           for m in c["members"]],
               "voting_evidence": [{"pair_id": p["pair_id"], "a": p["a"], "b": p["b"],
                                    "score": p["score"], "votes": p["votes"],
                                    "decision": p.get("final_decision"),
                                    "decision_source": p.get("decision_source"),
                                    "reason": p.get("decision_reason")} for p in pairs],
               "merge_reason": c["merge_reason"],
               "conflicts": c["conflicts"],
               "untraced_fields": c.get("untraced_fields") or [],
               "decision_source": ("agent" if any(p.get("decision_source") == "agent" for p in pairs)
                                   else "rule")}
        lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def render_recon(idx, merged, cov, qrows, dupq, gaps, draft, stats):
    o = ["# 对账报告（reconciliation）", "",
         "本报告把「每份响应 → 字段归一 → 去重 → 合并 → 候选集」的链条摊开，"
         "所有计数都可从 `merge_cluster.jsonl` 与 `intake_ledger.md` 复算。", "",
         "## 1. 检索问题与范围", "",
         "- 研究问题：%s" % (draft.get("research_question") or "**未记录**（build 未读到工作稿的 research_question）"),
         "- 范围：%s" % (L.clip(draft.get("scope"), 400) if draft.get("scope") else "**未记录**"),
         "- 题面依据：%s" % ("`task.md` / `case.task_instruction`（见 intake_ledger §1）"
                          if idx.get("task_md") or idx["case"].get("task_instruction") else "**输入未给题面**"),
         ""]
    o += ["## 2. 去重对账数字", "", "| 阶段 | 计数 | 口径 |", "|---|---|---|",
          "| 原始记录 | %d | 各库响应解析出的记录条数（含跨库重复） |" % stats["raw"],
          "| 候选对 | %d | 共享 DOI/标识符族/首作者姓+年/标题 bigram 的记录对 |" % stats["pairs"],
          "| 判 duplicate | %d | 投票分 ≥4 或 Agent 签字 |" % stats["dup"],
          "| 判 maybe | %d | 投票分 =3，未合并，等 Agent/人工仲裁 |" % stats["maybe"],
          "| canonical 记录 | %d | 并查集聚类后的唯一文献数 |" % stats["canonical"],
          "| 单库独有 | %d | 只在一个库出现的 canonical 记录 |" % len(cov["single_db_clusters"]), ""]
    if stats["maybe_pairs"]:
        o += ["**待仲裁对（maybe）**：", "", "| pair | 记录 | 分 | 证据 |", "|---|---|---|---|"]
        for p in stats["maybe_pairs"][:15]:
            o.append("| %s | %s + %s | %d | %s |" % (p["pair_id"], p["a"], p["b"], p["score"],
                                                     L.clip(p["reason"], 90)))
        o.append("")
    o += ["## 3. 库 × 字段 覆盖缺口矩阵", "",
          "单元格为该库记录中该字段的状态计数 `P/M/S/U`（present/missing/suspect/unknown）。"
          "`M` 表示该库 schema 应有而没有，`U` 表示结构未识别、无法判断。", "",
          "| 库 | 记录 | " + " | ".join(COV) + " | 字段填充率 | 状态 |",
          "|---|---|" + "---|" * len(COV) + "---|---|"]
    for r in cov["rows"]:
        cells = []
        for f in COV:
            c = r["cells"][f]
            cells.append("%d/%d/%d/%d" % (c["present"], c["missing"], c["suspect"], c["unknown"]))
        o.append("| %s | %d | %s | %.0f%% | %s |" % (r["db"], r["records"], " | ".join(cells),
                                                    100 * r["field_ratio"], r["status"]))
    o += ["", "## 4. 单库独有记录", ""]
    if cov["single_db_clusters"]:
        for cid in cov["single_db_clusters"][:20]:
            c = next((x for x in merged if x["cluster_id"] == cid), None)
            if c:
                o.append("- `%s` [%s] %s" % (cid, ",".join(c["source_dbs"]),
                                             L.clip((c["canonical"].get("title") or {}).get("value") or "-", 110)))
    else:
        o.append("无（每条 canonical 记录都至少被两个库收录，或只有一个库可用）。")
    o += ["", "## 5. 系统性缺字段", ""]
    if cov["systematic_missing"]:
        for s in cov["systematic_missing"]:
            o.append("- `%s`：%d/%d 个库有值 —— %s" % (s["field"], s["dbs_with_value"], s["dbs_total"], s["note"]))
    else:
        o.append("未发现「至多一半库缺值」的字段。")
    if cov["unparsed"]:
        o += ["", "**未产出记录的文件（非失败响应）**："]
        for u in cov["unparsed"][:12]:
            o.append("- `%s`" % u)
    o += ["", "## 6. 失败库与降级", ""]
    if idx.get("failures"):
        o += ["| 库 | 路径 | HTTP | 原因 | 处置 |", "|---|---|---|---|---|"]
        for f in idx["failures"]:
            o.append("| %s | `%s` | %s | %s | 该库标记 FAILED，缺口写入第 8 节，不补造文献 |"
                     % (f.get("db"), f.get("path"), f.get("http_status") or "-", L.clip(f.get("reason"), 110)))
    else:
        o.append("本次无失败库。")
    o += ["", "## 7. 查询矩阵与趋同性审计", ""]
    o += ["| 库 | 查询（截断） | 来源 | 返回 | 去重后 | 状态 |", "|---|---|---|---|---|---|"]
    for r in qrows:
        o.append("| %s | %s | %s | %s | %s | %s |" % (r["db"], L.clip(r["query_sent"], 70),
                                                      r["query_origin"], r["returned"],
                                                      r["unique_clusters"], r["status"]))
    if dupq:
        o += ["", "**趋同性告警**：以下库使用了完全相同的查询串（可能意味着「把同一条查询机械复制到每个库」，"
              "各库字段域/语法未被利用）："]
        for d in dupq:
            o.append("- `%s` → %s" % (d["query_prefix"], ", ".join(d["dbs"])))
    else:
        o += ["", "未检测到跨库完全相同的查询串；各库查询差异见 `query_matrix.csv` 的 `query_sent` 列。"]
    o += ["", "## 8. 候选集排序", ""]
    if merged:
        o += ["| rank | cluster | 题名 | 年 | 来源库 | 相关性判定 | 依据 |", "|---|---|---|---|---|---|---|"]
        for c in merged[:40]:
            rel = c.get("relevance") or {}
            o.append("| %s | %s | %s | %s | %s | %s | %s |"
                     % (c.get("rank"), c["cluster_id"],
                        L.clip((c["canonical"].get("title") or {}).get("value") or "-", 80),
                        (c["canonical"].get("year") or {}).get("value") or "-",
                        ",".join(c["source_dbs"]), rel.get("verdict") or "unscreened",
                        L.clip(rel.get("reason") or "-", 80)))
    else:
        o.append("无 canonical 记录（输入未提供可解析的文献响应）。")
    o += ["", "## 9. 缺口与未完成项", ""]
    if gaps:
        o += ["| # | 类型 | 说明 | 依据 |", "|---|---|---|---|"]
        for i, g in enumerate(gaps, 1):
            o.append("| %d | %s | %s | %s |" % (i, g.get("kind") or "-", L.clip(g.get("note") or g.get("item"), 160),
                                                L.clip(g.get("locator") or "-", 60)))
    else:
        o.append("无记录在案的缺口。")
    o += ["", "## 10. 复算与核验入口", "",
          "```bash",
          "python3 scripts/main.py check     # 契约键/locator 回放/聚类覆盖",
          "python3 scripts/main.py build     # 由 draft 重新装配本报告",
          "python3 scripts/main.py selfcheck # 五件套与契约复检",
          "```", "",
          "每个 canonical 字段带 `src_db` + `locator` + `rule`；`locator` 形如 `<文件>#$.message.items[3]`，"
          "可用 `ledger.resolve()` 在原始文件上回放并比对 `raw_sha`。", ""]
    return "\n".join(o)


# -------------------------------------------------------------- contract fill
CMAP = (
    ("records", ("mergedrecords", "records", "record", "merged", "papers", "paper", "articles",
                 "article", "candidates", "candidate", "documents", "bibliography", "文献", "记录", "候选")),
    ("clusters", ("clusters", "cluster", "dedup", "duplicates", "duplicate", "groups", "group",
                  "聚类", "去重", "重复")),
    ("coverage", ("coverage", "gap", "gaps", "missing", "omission", "omissions", "blind",
                  "覆盖", "缺口", "遗漏")),
    ("queries", ("queries", "query", "qmatrix", "searchstrategy", "strategy", "检索", "查询")),
    ("ranked", ("ranked", "ranking", "rank", "order", "ordered", "sort", "sorted", "priority", "排序", "优先")),
    ("rules", ("normalization", "normalisation", "normalize", "normalise", "rules", "rule", "mapping",
               "fieldmap", "schema", "归一", "映射", "规则")),
    ("sources", ("sources", "source", "provenance", "evidence", "trace", "traceability", "locators",
                 "来源", "证据", "回溯")),
    ("databases", ("databases", "database", "dbs", "db", "libraries", "库", "数据库")),
    ("screening", ("screening", "screened", "relevance", "relevant", "inclusion", "include",
                   "筛选", "相关")),
    ("exclusions", ("exclusions", "exclusion", "excluded", "exclude", "rejected", "reject", "排除", "剔除")),
    ("conflicts", ("conflicts", "conflict", "dispute", "冲突")),
    ("failures", ("failures", "failure", "failed", "errors", "error", "异常", "失败")),
    ("counts", ("counts", "count", "numbers", "number", "total", "totals", "statistics", "统计", "数量")),
    ("uncertainty", ("uncertainty", "uncertain", "limitations", "limitation", "risks", "不确定", "限制")),
    ("summary", ("summary", "report", "narrative", "conclusion", "conclusions", "findings", "notes",
                 "explanation", "说明", "结论", "总结", "报告")),
    ("status", ("status", "state", "状态")),
)


def contract_items(oc):
    items = []

    def put(k, spec):
        k = str(k).strip()
        if k and k not in [x[0] for x in items]:
            items.append((k, spec))

    if isinstance(oc, dict):
        for k, v in oc.items():
            put(k, v)
    elif isinstance(oc, list):
        for x in oc:
            if isinstance(x, str):
                put(x, None)
            elif isinstance(x, dict):
                k = x.get("key") or x.get("name") or x.get("field") or x.get("id") or x.get("字段")
                if k:
                    put(k, x)
                else:
                    for kk, vv in x.items():
                        put(kk, vv)
    elif isinstance(oc, str):
        for line in oc.replace("；", "\n").splitlines():
            line = line.strip().strip("-*` ")
            if not line:
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_\-]{1,60})\s*[:：(（]", line)
            if m:
                put(m.group(1), line)
            elif re.match(r"^[A-Za-z_][A-Za-z0-9_\-]{1,60}$", line):
                put(line, None)
    return items


def infer_target(key, spec):
    txt = L.nkey(key)
    hint = ""
    if isinstance(spec, dict):
        hint = L.nkey(" ".join(str(v) for v in spec.values() if isinstance(v, str)))
    elif isinstance(spec, str):
        hint = L.nkey(spec)
    m = re.match(r"^(n|num|total|count|len)[_-](.+)$", key.lower())
    if m and len(m.group(2)) > 2:
        inner, _ = infer_target(m.group(2), spec)
        if inner in ("records", "clusters", "queries", "sources", "databases"):
            return inner + ":count", "numeric key over %s" % inner
        return "counts", "numeric key, no countable target"
    best, why, blen = None, "", 0
    for target, words in CMAP:
        for w in words:
            if w in txt and len(w) > blen:
                best, why, blen = target, "key token '%s'" % w, len(w)
    if not best and hint:
        for target, words in CMAP:
            for w in words:
                if w in hint and len(w) > blen:
                    best, why, blen = target, "spec hint '%s'" % w, len(w)
    if best == "status" and re.search(r"(db|database|source)", txt):
        best, why = "databases", "status of sources -> database table"
    return best, why


def fill_contract(oc, B):
    items = contract_items(oc)
    vals, cmap, unmapped = {}, [], []
    for k, spec in items:
        tgt, why = infer_target(k, spec)
        if not tgt:
            null_like = isinstance(spec, (list, tuple))
            vals[k] = [] if null_like else None
            unmapped.append({"key": k, "action": "null", "basis": "no semantic match"})
            cmap.append({"key": k, "target": None, "basis": "unmapped; value left null/[]"})
            continue
        if tgt.endswith(":count"):
            base = tgt.split(":")[0]
            vals[k] = len(B.get(base) or [])
            cmap.append({"key": k, "target": base, "basis": why + " (as count)"})
            continue
        vals[k] = B.get(tgt)
        cmap.append({"key": k, "target": tgt, "basis": why})
    return items, vals, cmap, unmapped


