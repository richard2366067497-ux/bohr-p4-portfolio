# GAIN_EVIDENCE — field-contract-cleaner（analysis-01 · v9）

对照口径见 SKILL.md 的「运行契约」与「自查」两节。每一项都给出**可由交付文件自行核验**的证据与复现方式；拿不到证据的项一律写「未通过」。

## 对照组

- **baseline**：材料按字面读入 → 一张表 + 一句结论（不建契约、不记账、不回算）。
- **skill**：`python3 scripts/main.py all --input /input --output /app/output --work /app/work`。

## 逐项证据

| 能力 | baseline | skill | 证据（文件 → 字段） | 复现 |
|---|---|---|---|---|
| 契约化 | 列名即语义，无契约 | 每字段一条契约，动作受契约约束 | `field_contract.json → fields[]` | 数 `fields[]` 条数 |
| 缺失处理 | `dropna`/填 0（隐形改数） | `mark_missing` + `__flags`，原值保留 | `cleaned_table.csv → __flags` 含 `MISSING_*`/`BELOW_LOD`，同格原值仍在 | 数 flags 出现次数 |
| 单位换算 | 就地换数，无记录 | 注册表 + 显式 factor，逐格记账 | `transform_ledger.jsonl` 的 `kind=cell,action=convert_unit` 行 | `selfcheck → ledger_invertible == ok` |
| 重复 | 删整行 | 隔离不删，`duplicate_of` 回链 | `reconciliation.json → row_accounting`（`raw=kept+marked+quarantined`） | `selfcheck → row_accounting == ok` |
| 报告数字 | 人写散文数字 | 每个数字由 `__flags` 回算 | `reconciliation.json → report_table.ok` | `selfcheck → report_matches_table == ok` |
| 失败处理 | 报错退出，半个目录 | 恒 exit 0 + 降级矩阵 | `result.json → status/degradations/pending_human` | `echo $?` + 读 `degradations` |
| 契约回填 | 无该概念 | 每个契约键都有非空块 | `result.json → output_contract`（键集合 = 契约键集合） | 比对键集合 |
| 可复现 | 每次输出不同 | 固定 seed、无时钟，字节稳定 | 两次运行 `cleaned_table.csv` sha256 相同 | `sha256sum out/cleaned_table.csv` 跑两次 |

## 现状（本仓库合成 case 实测）

- rich（`synth_cases/analysis-01/rich`：字典 32 字段 + 99 条工单、**无数据表**）：
  `status=partial`；契约 32 条（`source=synthesized:dictionary_only`）；`no_table_found` 如实降级；
  `output_contract` 11/11 键回填；placeholder 扫描 0 命中。
- boundary（`case.json.output_contract=null`、材料 0/坏）：
  `status=insufficient_evidence`；契约退回包声明（SKILL.md「Output contract」节）后仍 11/11 回填；产物齐、exit 0。

> 说明：这两个合成 case 都不含数据表，清洗表因此是**降级骨架**（说明行 + 0 影响聚合行），不是伪造行数据。真实带表 case 走同一路径，`__flags`/账本/对账按行产生。

## 增量一句话

基线产出「一张看起来干净的表」；本包产出「一张表 + 一条任何人可逐格复核、换台机器重跑仍一致的证据链」。
