# field-contract-cleaner（分析-01 · v9 包）

把「脏汇总表 + 数据字典 + 每指标单位/QC 规则 + 清洗工单」变成可逐格复核的证据链：
清洗表 + 变换账本 + 字段级质量报告 + 契约与三方对账，`result.json` 回填每个契约键。

## 30 秒上手

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

单命令入口（等价别名 `build`）：不写工作稿也产出全部交付物，恒 exit 0。目录约定：
输入 `/input`、交付 `/app/output`、工作区 `/app/work`（三者都可由 `--input/--output/--work` 改）。

Agent 增强路径（需要逐字段复核时）：

```bash
python3 scripts/main.py init  --input /input --output /app/output --work /app/work
python3 scripts/main.py show  --input /input --output /app/output --work /app/work
#  读 show 的逐字原文，写 /app/work/draft.json（schema 见 SKILL.md §6）
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

## 交付物

| 文件 | 说明 |
|---|---|
| `result.json` | 机器答案：`output_contract` 全键回填 + 信封（status/sources/verification/degradations…） |
| `cleaned_table.csv` | 主产物：原始列序 + `record_id/__src_row/__row_status/__flags`，缺失与越界值原样保留并标记 |
| `transform_ledger.jsonl` | 唯一执行记录：聚合行 + 改值单元格行，`input` 可由 `output` 反算 |
| `data_quality_report.md` | 输入与编码、契约、账本、三方对账、逐字段问题、未处置、可逆性与复现 |
| `field_contract.json` / `reconciliation.json` | 生效契约 / 行数守恒与报告-表一致性 |
| `field_issues.csv` | 字段级问题清单，可直接排序筛选 |

## 与基线的差别

基线直接 `dropna/fillna`、就地换单位、删重复行、人写数字——结果不可复核也不可复现。
本包：**不填补只标记**、单位换算逐格记账且可逆、重复行隔离不删、报告每个数字由 `__flags` 回算、
`selfcheck` 独立复检，并且坏 JSON / 空材料 / 无字典 / 无工单全部恒 exit 0 并如实降级。
详见 SKILL.md §14/§15 与 GAIN_EVIDENCE.md。

## 不做什么

统计检验与总体推断、填补缺失、图表美化、数据库运维、用输出替换原始实验数据。

作品集：见 GITHUB_URL.txt。
