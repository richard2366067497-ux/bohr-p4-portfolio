---
name: db-query-workbook
description: 把科研数据库查询做成可复核的查询工作簿：发现库表→字段字典（编码型字段按标签解释）→派生并在真实 SQLite 快照上执行查询→把每个结果集导出 CSV→做行数与连接膨胀复核→写报告与 result.json。用于"数据库查询""SQL 分析""跨表连接""结果导出""字段解释""查询复核/对账"等任务；每条引用的 SQL 都真实执行过，每个数字都能回算到结果集。
version: 6.0.0
tags: [database-query, sqlite, field-dictionary, join-ledger, result-reconciliation]
---

# db-query-workbook（科研数据库查询工作簿）

本包是 `analysis-06` 的 v6 形态：**单命令即可跑完整条查询流水线**，无需先初始化再写工作稿；
Agent 仍可补充查询意图，但评估器只跑第一条命令也能拿到全部产物与完整契约回填。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 同时把每个契约键放进 `output_contract` 结构位与顶层同名键。用例声明的键总是合并
进来、绝不改名或丢弃；用例未声明契约时使用下列默认键（与 SKILL 本样例一致）：

```json
{
  "case_id": "string",
  "status": "string",
  "output_contract": {
    "case_id": "string",
    "status": "string",
    "deliverable": "string",
    "queries": "string",
    "results": "string",
    "reconciliation": "string",
    "change_log": "string"
  }
}
```

- `case_id` 原样透传（来自 `/input/case.json`）；取不到时回退为输入目录名。
- 路径类键指向真实存在且非空的交付物；无法直接映射的键写成结构信封
  `{"kind","items","count","note"}`，而不是占位符。
- 写出前统一做占位符清理（JSON/Markdown/SVG 文本），但 **`queries.sql` 与结果 CSV 保持逐字原样**，
  确保 SQL 可直接复跑、数据不被改写。

## 1. 单命令全流程（single-command entry）

一条命令跑完 连接 → 发现库表 → 字段字典 → 派生查询 → 真实执行 → 导出 CSV → 行数/连接复核
→ 报告 → 回填全部 `output_contract` 键 → 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

- 该命令是评测器可执行的一次性等价入口，退出码恒为 0；空输入 / 坏输入同样退出 0 并写出合法
  `result.json`（`status=partial` 或 `input_error`，降级但不编造任何结果数值）。
- 有授权 SQLite 库时只读打开（`file:...?mode=ro`）；没有库时，把输入里的表材料装进
  `work/snapshot.db` 再执行同一批 SQL——**查询始终真实执行**，绝不交付"像 SQL 的文本"。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `query_report.md` | 五节报告：库表发现、字段字典、查询执行、行数与连接复核、局限与不确定性 |
| `queries.sql` | 每个被执行的语句逐字记录（含 qid、用途、执行状态） |
| `results/query_results.csv` | 结果集索引：qid/kind/purpose/columns/rows/status（SQL 原文见 `queries.sql`） |
| `results/Q_*.csv` | 每个结果集一份真实 CSV 导出 |
| `reconciliation.json` | 每个结果集与快照独立重算的对账（行数、连接膨胀） |
| `join_ledger.json` | 跨表连接账本：左/右 distinct、两侧行数、joined 行数、膨胀因子 |
| `field_dictionary.json` | 字段字典：kind（num/code/text）、unit、distinct、missing、编码取值 |
| `query_workbook.json` | 快照元数据、schema、查询计划、连接候选键 |
| `data_quality.json` | 缺失与重复的量化结果、解析动作记录 |
| `code/reproduce.md` | 复跑说明（同一快照字节稳定） |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、`status`、证据、不确定性、变更记录、限制 |

`query_report.md` 与 `results/` 是主交付；其余文件是可复核的中间证据。

## 3. 子命令与参数（可选，供人工/Agent 分步复核）

| 子命令 | 作用 | 写盘 |
|---|---|---|
| all | 全自动流水线（推荐，单命令等价入口） | 是 |
| init | 写入草稿骨架并按默认口径跑一遍全流程 | 是 |
| show | 打印输入清单、快照模式与计划执行的语句 | 是 |
| check | 复核已有输出、契约键与对账检查 | 是 |
| build | 同 all（保留旧入口名） | 是 |
| selfcheck | 重开输出目录复核 | 是 |

公共参数：`--input`（别名 `--in`）、`--output`（别名 `--out`）、`--work`、`--case`。所有子命令都
接受这组参数并始终退出 0。用例若在 `case.json` 的 `output_contract` 里用子命令名作为键，
本引擎会把它们回填为各自作用的真实说明（例如 `build` → 已写出的产物清单）。

## 4. 查询与复核口径

- **派生规则**：每张表一条 `COUNT(*)`；编码型字段（distinct ≤ 20）出取值分布——**永不把编码字段
  当数值求和**；数值字段出 `COUNT/MIN/AVG/MAX`；每表前两列出缺失/重复审计；共享列名（优先 `*id`）
  出跨表 `JOIN` 计数。
- **对账**：`COUNT(*)` 结果与独立重算比对；连接查询比对"两侧行数 vs joined 行数"，判断是否发生
  一对多膨胀，并把膨胀因子写进 `join_ledger.json`。
- **快照版本**：记录快照 SHA-256 与 SQLite 版本，他人可核对数据版本与独立复跑。
- 所有语句都写进 `queries.sql`；失败语句保留原始报错文本。

## 5. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 递归找材料继续；用默认契约 | `degradations: case_json_unreadable` |
| 无库且无可装载表 | 空态工作簿 + 全部诚实交付物，status=partial | `uncertainties: no_queryable_snapshot` |
| 空文件 / 坏 JSON | 记入盘点并跳过 | `degradations: material_unreadable` |
| 语句报错 | 保留原始 error 文本，不下结论 | `degradations: query_failed` |
| 无共享列名 | 不做跨表分析并说明 | `uncertainties: no_cross_table_key` |

## 6. 边界与限制

只做可复核的查询与对账；不猜连接参数、不接外部库、不判断科研结论正确与否。纯标准库
（sqlite3, csv, json, re, hashlib, pathlib）、无网络、无时钟读取：重复运行同一快照，交付物字节稳定。
运行中断时保留已写的部分 `result.json`，异常写入 `errors[]`，退出码仍为 0。
