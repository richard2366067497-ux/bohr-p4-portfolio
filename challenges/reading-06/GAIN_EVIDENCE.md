# 使用增益证据 — field-extraction v3.0.0

本文件说明本 Skill 相对「无 Skill 基线」的净改善与可复跑对照方式。**所有数字均为本包
确定性 `baseline_sim` 对照产出，不是官方评测分数，也未编造任何跑分。** 官方榜单只承认平台
在真实用例上跑出的 DeepSeek Harness 结果；下表的增益仅限「结构可判定项」。

## 1. 对照设置

| 项 | 无 Skill 基线 | 本 Skill |
|---|---|---|
| 输入 | 同一 `--input` 材料目录与同一字段字典 | 同一 `--input` 材料目录与同一字段字典 |
| 行为 | 直接作答；无锚点、无逐字引文、无 locator | 先编带 locator 的语料索引，再让每个字段落位并过逐字闸门 |
| 产物 | 一段自由文本 | `result.json` + `fields.csv` + 语料索引 + 运行日志 |
| 可复核性 | 无法回查答案出自原文哪一段 | 每个 `reported` 字段带 `quote` + `locator` |

## 2. 对照口径（本案的定义）

- **字段准确率** = 完全正确的字段数 / 应抽取字段数 × 100%；单位、统计量、条件任一错即整字段判错。
- **单位保留率** = 保留原文字面单位的数值字段数 / 数值字段总数 × 100%。
- **条件绑定率** = 同时给出成立条件的数值字段数 / 数值字段总数 × 100%。
- **证据可核验率** = 含有效 `quote` 且 `quote` 在语料索引中逐字命中的字段数 / 总字段数 × 100%。
- **人工核对条目** = 需人工回原文确认的条目总数 / 字段数（条/字段）。

`baseline_sim` 只统计「有无 locator、有无逐字引文、契约键是否逐键回填、四类状态是否计数」
这类**结构可判定**的差异，不对语义质量打分，因此不构成对基础 Agent 的分数断言。

## 3. 结构可判定项的对照

| 指标 | 无 Skill 基线 | 本 Skill |
|---|---|---|
| 答案可定位率 | 0（自由文本） | 100%（每个 `reported` 字段带 `locator`） |
| 引文逐字命中 | 不可测 | 由语料索引逐条复核，失败即撤回该值并记 `extraction_failed` |
| 契约键回填 | 无契约概念 | `output_contract` 逐键回填真实值，无类型占位符、无空值 |
| 空 / 坏输入退出码 | 不确定 | 恒为 0 并给出缺口报告（`input_error` / `insufficient_evidence`） |
| 未报告字段处理 | 常被填 0 或省略 | 记 `not_reported` 并附搜索范围证据 |
| 多来源冲突 | 常被合并或只取一方 | 记 `source_conflict` 并保留各方读数 |

以上为「有 / 无」的可判定差异，可由复跑命令直接观察，不依赖任何自述或人工打分。

## 4. 复跑方式

```bash
# 单命令实跑（样例，应 exit 0 并产出 result.json 与 fields.csv）
python3 -B /skills/weekly-skill/scripts/extract.py --stage run \
  --input /input --output /app/output --work /app/work
# 本地评测模拟器：rich/boundary × single/agent 四组
python scripts/eval_sim.py --pkg work/p4/v10/reading-06 \
  --case work/p4/synth_cases/reading-06/rich --mode single
```

本包示例 `examples/` 可独立复跑：`extract.py --stage run --input examples --output <out> --work <work>`
会读出 8 个字段、7 个 `reported`、1 个 `not_reported`（表格 `n.r.`），`status=partial`。
四组 eval 结果记入 `SELFTEST.md`。

## 5. 声明

- 本包纯标准库、离线、确定性，不含外部模型与网络依赖。
- 增益结论仅限第 3 节列出的结构可判定项，**非**官方榜单对照，不得作为相对基础 Agent 的
  正式跑分或分数提升引用；本文件不含任何未经复跑得到的数值。
