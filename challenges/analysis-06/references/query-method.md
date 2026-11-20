# 查询方法 — 发现、派生、执行与对账口径

本文件是 `db-query-workbook` 的口径备忘；引擎实现与之一一对应。

## 1. 连接与快照

- 优先只读打开授权 SQLite 库：`sqlite3.connect("file:<path>?mode=ro", uri=True)`，绝不写库。
- 输入里没有库时，把 `.csv/.tsv/.json` 里的对象数组装载进 `work/snapshot.db`（列统一为 TEXT），
  再执行同一批 SQL。这一步是**真实的装载 + 真实的 SQL 执行**，不是拼字符串。
- 记录快照 SHA-256 与 `sqlite3.sqlite_version`，写进 `result.json.snapshot` 与报告。

## 2. 字段字典

对每张表的每一列统计：

- `distinct`（`COUNT(DISTINCT col)`）、`missing`（`NULL` 或空串计数）、前若干取值样本；
- `kind`：数值可解析比例 ≥ 80% → `num`；`0 < distinct ≤ 20` → `code`（编码型，按标签解释）；
  其余 → `text`；
- `unit`：从列名末尾括号抽取（如 `mass（mg）`），或识别 `_mg/_c/_pct` 等后缀。

**编码型字段只做取值分布，不做数值聚合**——这是"把编码字段当数值求和"这类常见错误的防线。

## 3. 查询派生（确定性）

按固定顺序派生，保证同一 schema 得到同一批语句：

1. 每表 `SELECT COUNT(*)`；
2. 每个编码字段 `GROUP BY` 取值分布（`ORDER BY n DESC`）；
3. 每个数值字段 `COUNT/MIN/AVG/MAX`；
4. 每表前两列的缺失/重复审计
   （`SUM(CASE WHEN col IS NULL OR col='' THEN 1 ELSE 0 END)` 与 `COUNT(*)-COUNT(DISTINCT col)`）；
5. 共享列名（优先含 `id`，其次 `*_no/*_code`）→ `JOIN` 计数，最多 3 条。

## 4. 对账（reconciliation）

- **计数对账**：`COUNT(*)` 的结果与一次独立重算比对（`count_matches_independent_recount`）。
- **连接对账**：取左/右表行数与两侧键的 `distinct`，比较 `joined_rows` 与两侧行数；若 joined 未超过
  较大的驱动表则通过（`no_join_inflation_beyond_driving_table`），并把 `expansion_factor`
  记进 `join_ledger.json` 供人工判断一对多关系是否符合预期。
- **质量对账**：确认缺失/重复指标已返回非空值（`quality_metrics_reported`）。

## 5. 落盘与不改写

- 每个结果集导出为 `results/<qid>.csv`；索引 `results/query_results.csv` 记录 qid/kind/purpose/sql/列/行数/状态。
- `queries.sql` 与结果 CSV **逐字原样**，不套占位符清理，确保 SQL 可直接复跑、数据不被改写；
  占位符清理只作用于 JSON / Markdown / SVG 文本。

## 6. 溯源

`reconciliation.json`、`join_ledger.json`、`field_dictionary.json`、`query_workbook.json` 共同构成
证据链：报告里的每个数字都能回算到某个 `results/<qid>.csv` 行，且该行由 `queries.sql` 里的一条
真实执行语句产生。
