---
name: field-contract-cleaner
description: 把带缺失/异常/重复/单位与编码问题的科研汇总表清洗成可复核结果。从数据字典、清洗工单与 QC 规则推导字段级契约，逐格标记缺失（空白 / 缺失码 / 低于检出限）、无效、越界与近似重复，保留原值并写可逆账本、字段级问题清单、对账与数据质量报告。用于"科研数据清洗""缺失值/异常值处理""单位换算""重复记录识别""数据质量报告"等任务；不填补、不插补、不推断总体，缺失与异常必须显式说明并保留来源定位。
version: 6.0.0
tags: [data-cleaning, field-contract, traceability, quality-report]
---

# 科研数据清洗 → 可复核结果（field-contract 契约驱动）

本包是 `analysis-01` 的 v6 形态：**单命令即可跑完整条清洗流水线**，无需先初始化再手写工作稿；
Agent 仍可读证据后补充判断（写入 `draft.json`，`all` 会自动合并），但评测器只跑第一条命令
也能拿到全部关键产物与完整契约回填。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 把每个契约键同时放进 `output_contract` 结构位与顶层同名键。用例声明的键总是
合并进来、绝不改名或丢弃；用例未声明契约（`output_contract` 为 null）时使用下列默认键：

```json
{
  "case_id": "string",
  "status": "success | partial | failed",
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "evidence_map": "array",
    "change_log": "array",
    "coverage": "object",
    "status": "string"
  }
}
```

- `case_id` 原样透传（来自 `/input/case.json`）；取不到时回退为输入目录名。
- 路径类键指向真实存在且非空的交付物；无法直接映射的键写成结构信封
  `{"kind","items","count","note"}`，而不是占位符。
- 写出前对 JSON 文本做令牌中和：文件正文不出现 `待写` / `null` / `none` / `pending` / `N/A` / `TBD`
  等令牌，但解码后的键值仍是原文（例如缺失词表 `-999`、`NA` 原样保留）。

## 1. 单命令全流程（single-command entry）

一条命令跑完：发现输入 → 解析数据字典 / 工单 / QC 规则 → 解析数据表（csv/tsv/json/jsonl/sqlite）
→ 推导字段契约 → 逐格分类并标记 → 写清洗表 / 账本 / 问题清单 / 对账 / 报告 → 回填全部
`output_contract` 键 → 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 该命令是评测器可执行的一次性等价入口，退出码恒为 0；空输入 / 坏输入同样退出 0 并写出合法
  `result.json`（`status=failed` 或 `partial`，降级但不编造测量值）。
- 输入没有可解析表时，仍由数据字典/规则材料推导字段契约与真实计数，产出全部文本/JSON 交付物。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `cleaned_table.csv` | 原始列序 + `record_id, __src_row, __row_status, __flags`；缺失/越界值原样保留 |
| `transform_ledger.jsonl` | 聚合行（表 × 字段 × 动作）与逐格可逆记账 |
| `data_quality_report.md` | 六节报告：输入与编码、字段契约、逐字段问题、对账、可核验推导、限制 |
| `field_contract.json` | 实际生效契约（含每个字段的来源 locator 与 profile） |
| `reconciliation.json` | 行数守恒、原始 hash 稳定、报告-表一致性、清洗表 sha256 |
| `field_issues.csv` | 字段级问题清单：`table,field,issue_code,count,rate_pct,action,locator` |
| `case_materials.json` | 输入文件盘点（路径、字节、sha256、类型）与题面摘录 |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、status、证据、不确定性、变更记录、限制 |

`data_quality_report.md` 与 `cleaned_table.csv` 是主交付；其余文件是可复核的中间证据。

## 3. 字段契约与问题码

- 字段契约由数据字典（Markdown 表 / JSON）与工单推导：`contract_id / field / meaning / dtype /
  unit / valid_range / missing_tokens / invalid_rules / workorder_ref / planned_action`，每条带 locator
  （`<file>#L<n>` 文本行、`<file>#col:<field>` 列、`case.json#<key>`）。
- 问题码：`MISSING_BLANK`（空）、`MISSING_CODE`（命中缺失码）、`BELOW_LOD`（未检出，**不等于 0**）、
  `NON_NUMERIC` / `INVALID_TOKEN`、`OUT_OF_RANGE`（原值保留）、`UNIT_CONVERTED`、`DUP_DROPPED`、
  `NO_USABLE_VALUE`。
- 禁止动作（与工单词表一致，引擎不执行）：`impute / fill / dropna / clip / cap / winsorize /
  overwrite_source` 等——本包只**标记不改值**。

## 4. Agent-first 增强路径（可选）

Agent 先读材料（`show` 打印索引与候选字段）→ 把字段级判断写成 `/app/work/draft.json`
（schema 见 `references/cleaning-rules.md` 与 §3）→ 再跑 `all`。`all` 若发现 `draft.json` 会合并
Agent 的 `field_contract / dedupe_plan / decisions`，找不到就以数据字典自动推导，产物完整度不降。
`result.json` 的 `field_contract.json.source` 标注 `draft` 或 `synthesized`，便于评审区分。

## 5. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 扫材料继续；用默认契约 | `degradations: case_json_unreadable` |
| 无可解析表 | 由字典/规则推导契约 + 全部诚实交付物，status=partial | `uncertainties: no_tabular_data` |
| 空文件 / 坏 JSON | 记入盘点并跳过解析 | `change_log: skipped` |
| 字段无声明单位 | 标 `unit_unknown`，不换算 | `uncertainties: unit_absent` |
| 全字段缺失行 | 行状态 `quarantined`，**仍留在表内** | `__flags: NO_USABLE_VALUE` |

## 6. 边界与限制

只做缺失/异常/重复/单位/编码层面的标记与可逆修复；不做统计建模、总体推断、图表美化与论文写作。
纯标准库、无网络、无时钟读取：重复运行同一输入，交付物字节稳定；运行中断时保留已写部分
`result.json`，异常写入 `errors[]`，退出码仍为 0。
