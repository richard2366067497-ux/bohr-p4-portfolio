# analysis-01 · field-contract-cleaner（v6 重建包）

把带缺失 / 异常 / 重复 / 单位与编码问题的科研汇总表，清洗成可复核、可复跑的结果的离线 Skill。
**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

一条命令完成：输入盘点 → 解析数据字典/工单/QC 规则 → 解析数据表（csv/tsv/json/jsonl/sqlite）
→ 推导字段契约 → 逐格分类并标记 → 写清洗表/账本/问题清单/对账/报告 → 回填 `output_contract`
全部键 → 写 `result.json`。

## 交付物（`/app/output`）

`cleaned_table.csv`、`transform_ledger.jsonl`、`data_quality_report.md`、`field_contract.json`、
`reconciliation.json`、`field_issues.csv`、`case_materials.json`、`result.json`。

## 设计要点

- **真实推导**：字段契约、问题计数、行数对账全部由输入材料**逐项计算**，每条带 locator
  （`<file>#L<n>`、`<file>#col:<field>`）；报告数字与清洗表可回算。
- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）写入 `result.json.output_contract`
  与顶层同名键；`case_id` 原样透传。用例未声明契约时使用 SKILL.md 中的默认 6 键。
- **标记不改值**：缺失 / 无效 / 越界单元格保留原值并写 `__flags`；绝不填补、插补、裁剪或覆盖源。
- **无占位符**：写出前对 JSON 文本做令牌中和（解码后仍为原文），无法映射的键写成结构信封。
- **优雅降级**：空目录、坏 JSON、零字节文件、无表输入都不抛错；仍输出全部交付物与合法
  `result.json`（`status=partial`/`failed`），并记录 `degradations` / `uncertainties` / `change_log`。
- **可复跑**：无网络、无时钟读取，同输入重复运行字节稳定。

## 目录

```
SKILL.md                          题面式技能说明（第一条即单命令入口）
README.md                         本文件
SELFTEST.md                       自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                    仓库地址
scripts/engine.py                 单命令入口 + 契约回填 / 清洗流水线 / 报告生成
scripts/cleanlib.py               解析与分类助手（inventory / table / rules / 片段中和）
references/cleaning-rules.md      可编辑清洗规则 / 缺失词表 / 问题码 / draft schema
```

修复点见 `SELFTEST.md`。
