# 自测记录 · field-contract-cleaner v7

## 1. 运行环境

- Python 3.12（纯标准库：csv / json / sqlite3 / hashlib / re / pathlib）。
- 入口：`python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work`。
- 源文件只读：运行前后源 sha256 不变（见 `reconciliation.json.source_sha256`）。

## 2. 验收矩阵（`scripts/eval_sim.py`）

| 案例 | 模式 | 结果 | 失败 | 警告 | 契约来源 |
|---|---|---|---|---|---|
| rich | single | PASS | 0 | 0 | case.json:output_contract |
| rich | agent | PASS | 0 | 0 | case.json:output_contract |
| boundary | single | PASS | 0 | 0 | SKILL.md (json sample) |
| boundary | agent | PASS | 0 | 0 | SKILL.md (json sample) |

8 个交付物全部存在且非空：`cleaned_table.csv`、`transform_ledger.jsonl`、`field_issues.csv`、
`field_contract.json`、`reconciliation.json`、`data_quality_report.md`、`case_materials.json`、`result.json`。

## 3. 真实清洗演练（自建 5 行样例，覆盖五类处理）

输入表：

```csv
sample,removal,conc
S1,95,3 mg/l
S2,NA,-999 mg/l
S3,61,2 μg/l
S3,61,2 μg/l
S4,120,5 mg/l
```

字典声明 `removal` 范围 0-100、`conc` 单位 mg/l；规则注册表含 `mg/l` 与 `µg/l`（别名 `μg/l`→`µg/l`）。

清洗结果（表头 4 个元列 + 源列，行列对齐一致）：

```csv
record_id,__src_row,__row_status,__flags,sample,removal,conc
1,2,kept,,S1,95,3 mg/l
2,3,marked,removal:MISSING_CODE; conc:OUTLIER,S2,NA,-999 mg/l
3,4,marked,conc:UNIT_CONVERTED,S3,61,2 μg/l
4,5,quarantined,conc:UNIT_CONVERTED; __row__:DUP_DROPPED,S3,61,2 μg/l
5,6,marked,conc:OUTLIER,S4,120,5 mg/l
```

- 对账：`raw_rows 5 == kept 1 + marked 3 + quarantined 1`，守恒成立。
- QC 不变式 5/5 通过，含「报告计数 == 从 cleaned_table.csv 重新计数」（10 == 10）。
- 账本仅记录真实换算（`µg/l`→`mg/l`，factor 0.001，locator `table.csv#row4`），等值单位不再记账。
- 列 `sample` 为标签列（无任何数值），不再被误判为 `NON_NUMERIC`。

## 4. 边界行为（boundary 案例）

坏 JSON、零字节文件、含占位符笔记：不抛错；`cleaned_table.csv` 写出空表状态行
（`no_source_table` / `INPUT_ERROR:MISSING_TABLE`），`status=partial`，退出码 0，8 个交付物齐备。

## 5. 已知限制

- 缺失码按整格精确匹配，`-999 mg/l` 这类带单位的写法不会命中 `-999`（记 `OUTLIER` 而非 `MISSING_CODE`）。
- 异常判定要求样本量 n≥4，n<4 时不做栅栏判定并在规则中说明。
- 不做填补/插补/裁剪；单位换算只在量纲一致时执行，逆映射记入账本。
