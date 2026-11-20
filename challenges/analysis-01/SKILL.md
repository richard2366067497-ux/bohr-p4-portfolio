---
name: field-contract-cleaner
description: 把带缺失/异常/重复/单位与编码问题的科研汇总表清洗成可复核、可复跑的结果：缺失与异常按规则标记不改值，异常用 IQR+MAD 双侧栅栏诊断，重复记录隔离保留，单位按注册表换算并逐格记账，QC 不变式逐条核验；纯标准库、确定性、退出码恒 0。
---

# field-contract-cleaner · 科研数据清洗与处理

围绕「读字典与工单 → 逐格分类 → 标记不改值 → 记账与对账 → 质量报告」组织。

## 输出契约（result.json.output_contract）

```json
{
  "output_contract": {
    "contract_id": "string",
    "field": "string",
    "meaning": "string",
    "dtype": "string",
    "unit": "string",
    "valid_range": "string",
    "missing_tokens": [],
    "invalid_rules": [],
    "workorder_ref": "string",
    "none": {},
    "planned_action": "string"
  }
}
```

用例声明的每个键（含嵌套）都会写入 `result.json.output_contract` 与顶层同名键，`case_id` 原样透传。

## 单命令入口

一条命令完成全流程（也是评测器的等价入口）：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 输入

- `/input/case.json`：`case_id` 与（可选）`output_contract`。
- 数据表：`*.csv` / `*.tsv` / `*.json` / `*.jsonl` / `*.sqlite`（分隔符自动嗅探，编码按打分回退）。
- 字典：正文含 `字段|变量|field` 表头的 Markdown 表。
- 规则：`rules.json`（缺失码、LOD、无效码、单位注册表、单位别名、禁止动作、QC 不变式）。
- 工单：正文中的 `WO-n` 引用。

## 输出（`/app/output`）

`cleaned_table.csv`、`transform_ledger.jsonl`、`field_issues.csv`、`field_contract.json`、
`reconciliation.json`、`data_quality_report.md`、`case_materials.json`、`result.json`。

## 五类处理

1. **缺失值**：命中缺失码/空值 → `MISSING_BLANK` / `MISSING_CODE`，原值保留、不填补。
2. **异常值**：数值列 IQR（k=1.5）+ MAD（k=3.0）双侧栅栏，叠加字典物理上下限 → `OUTLIER` / `OUT_OF_RANGE`。
3. **重复记录**：可比较列全等的次要行 → `DUP_DROPPED`，隔离保留不删除。
4. **格式转换**：单位按注册表换算并逐格记账（因子 + 逆映射）；编码按打分回退。
5. **数据质量报告**：本报告的每个数字都能由清洗表与对账回算。

## 规则

- **标记不改值**：绝不填补、插补、裁剪、平滑或覆盖源文件（源文件只读，sha256 前后一致）。
- **逐格可逆**：每个动作在 `transform_ledger.jsonl` 有 locator（`<file>#row<n>`、`<file>#col:<field>`）。
- **QC 逐条核验**：`qc_invariants` 每条给出 `pass`/`fail`/`recorded` 与证据。
- **优雅降级**：空目录、坏 JSON、零字节文件、无表输入都不抛错；仍写出全部交付物与合法 `result.json`。
- **可复跑**：无网络、无时钟读取，同输入重复运行字节稳定。

可编辑的规则说明见 `references/cleaning-rules.md`。
