# field-contract-cleaner（v6 修复包）

把带缺失 / 异常 / 重复 / 单位与编码问题的科研汇总表，清洗成**可复核、可复跑**的结果。
**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 交付物（`/app/output`）

`cleaned_table.csv`、`transform_ledger.jsonl`、`field_issues.csv`、`field_contract.json`、
`reconciliation.json`、`data_quality_report.md`、`case_materials.json`、`result.json`。

## 为什么这样改

上一版宣称支持异常值 / 去重 / 单位换算，但**零实现**：异常与重复没有任何判定逻辑，
清洗表表头与数据行列数不一致（表头 4 列、数据 4+N 列）。本版补齐真实实现并修正对齐。

## 设计要点

- **真实推导**：字段契约、问题计数、行数对账全部由输入材料逐项计算，每条带 locator
  （`<file>#row<n>` / `<file>#L<n>` / `<file>#col:<field>`）；报告数字与清洗表可回算。
- **异常检测**：数值列 IQR（k=1.5）+ MAD（k=3.0）双侧栅栏，叠加字典物理上下限。
- **重复记录**：可比较列全等的次要行隔离保留（不删除）。
- **单位换算**：注册表 + 别名归一，量纲一致才换算，账本记录因子与逆映射。
- **QC 逐条核验**：`qc_invariants` 每条给出 `pass`/`fail`/`recorded` 与证据。
- **标记不改值**：源文件只读（sha256 前后一致）；缺失 / 无效 / 越界只写 `__flags`。
- **表头对齐**：`cleaned_table.csv` 表头 = `record_id,__src_row,__row_status,__flags` + 源列，数据行列数一致。
- **无占位符**：写出前对 JSON 文本做令牌中和（解码后仍为原文）。
- **优雅降级**：空目录、坏 JSON、零字节文件、无表输入都不抛错；仍输出全部交付物与合法
  `result.json`（`status=partial`/`input_error`）。
- **可复跑**：无网络、无时钟读取，同输入重复运行字节稳定。

## 目录

```
SKILL.md                          题面式技能说明（第一条即单命令入口）
README.md                         本文件
SELFTEST.md                       自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                    仓库地址
environment/resources.yaml        运行时与输入/输出资源清单
scripts/engine.py                 单命令入口 + 清洗流水线 / 对账 / QC / 契约回填
references/cleaning-rules.md      可编辑清洗规则 / 问题码 / 阈值 / 降级策略
examples/README.md                一个最小可跑示例
```
