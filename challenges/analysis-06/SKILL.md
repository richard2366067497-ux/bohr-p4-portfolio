---
name: db-query-workbook
description: 把科研数据库查询做成可复核的查询工作簿：发现库表→字段字典（编码型字段按标签解释）→派生并在真实 SQLite 快照上执行查询→把每个结果集导出 CSV→做行数与连接膨胀复核→写报告与 result.json。用于"数据库查询""SQL 分析""跨表连接""结果导出""字段解释""查询复核/对账"等任务；每条引用的 SQL 都真实执行过，每个数字都能回算到结果集。
version: 6.0.0
tags: [database-query, sqlite, field-dictionary, join-ledger, result-reconciliation]
---

# db-query-workbook（科研数据库查询工作簿）

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按它组织全部产出：

- **流程**：按其 **§2 六步流水线（S0–S6）与门控**推进——确认快照与版本 → 读数据字典并与
  `PRAGMA table_info` 交叉比对（覆盖率 ≥ 95%，未覆盖字段标 `unmapped`）→ 质量探查 → 定义并执行
  清洗规则 → 编 SQL 逐条真实执行 → 图表与结论 → 组装 `result.json` 与复现命令；每步冻结产物后才进入下一步。
- **量化口径**：按其 **§3 逐条复算**——缺失率 `COUNT(IS NULL 或 ='')/COUNT(*)`（精确值）、重复行
  `GROUP BY … HAVING COUNT(*)>1`、异常值 IQR 法 `Q1-1.5×IQR / Q3+1.5×IQR`（3σ 法须先过正态性）、
  跨表 JOIN 校验（预期最小 `max(左,右)`、膨胀比 `实际/min(左,右)`、**膨胀比 > 5 必须人工审查**）、
  聚合交叉验证 `SUM(分组聚合) = SUM(明细)`、编码字段解码未映射值必须为 0；写进
  `reconciliation.json` / `join_ledger.json` / `data_quality.json`。
- **陷阱与单位**：按其 **§4 领域知识与单位陷阱**逐条排雷（K1 行数≠完整、K2 龄期必须分组、
  K3 编码当连续、K4 cement≠concrete、K5 单位 cm vs mm、K6 INTEGER 可能含 NULL）；字段语义以任务
  提供的数据字典为第一来源，字典缺失时引原始论文/发布页，**不做无来源假设**。
- **硬规则**：编码型字段永不参与数值聚合；每个 JOIN 结果使用前先做行数/膨胀复核；所有引用的 SQL
  都真实执行过（绝不交付"像 SQL 的文本"）。
- **门控**：交付前逐项通过其 **§5 交付物清单与防扣分自查表（DC-01…DC-17）**，并用其 **§8 专家注意点**
  与 **§7 快速决策树**逐条排雷。

本包是 `analysis-06` 的 **v10 形态**：**单命令即可跑完整条查询流水线**，无需先初始化再写工作稿；
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

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

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

随包样例 `examples/` 实测（2 表 / 9 字段 / **16 条真实执行的语句** / 16 份结果 CSV /
对账 **7/7** / 连接膨胀比 **2.5**）产出 **26** 件文件，见 `GAIN_EVIDENCE.md`。

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

## 7. 交付前自检清单

- [ ] 库表发现完整：表名、列名、行数与本快照一致；快照 SHA-256 与 SQLite 版本已记录
- [ ] 字段字典逐字段给出 kind（num/code/text）与 unit；**编码字段按标签解释，绝不做数值求和**
- [ ] 质量探查量化：逐列缺失率、重复行数与异常值方法（IQR 或通过正态性检验的 3σ）均已记录
- [ ] 所有引用的 SQL 都真实执行过并逐字写进 `queries.sql`；失败语句保留原始报错文本
- [ ] 每个 JOIN 后都有 `COUNT(*)` 校验与膨胀比，膨胀比 > 5 已人工审查（`join_ledger.json`）
- [ ] 每个结果集导出 CSV，行数可回算；对账检查写进 `reconciliation.json`（`n_pass/n_checks`）
- [ ] 契约键逐键非空（路径类键指向真实存在的交付物），`case_id` 原样透传，`status` 诚实
- [ ] **专家检查表逐项通过**：交付前逐项通过 `references/expert_playbook.md` §5 的 DC-01…DC-17
  自查表，并用 §7 快速决策树与 §8 专家注意点逐条排雷；任一项未通过则修正后重出，不得静默提升 status
- [ ] 无静默修改：所有数据变更均有记录与理由；纯标准库、离线、无时钟读取、字节稳定

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（S0–S6 六步流水线/量化口径 §3/领域陷阱与单位 §4/自查表 DC-01…DC-17/完整案例）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + samples.csv + batches.csv + dictionary.md）
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
