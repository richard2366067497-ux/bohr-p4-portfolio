# 清洗规则表（field-contract-cleaner 可编辑资源）

`references/cleaning-rules.md` 是包内唯一需要按课题调整的规则资源：改词表 / 单位 / 动作，不用改
`scripts/engine.py`。未知键被忽略。脚本与本文不一致时，行为以脚本为准，本文给出可核对的清单。

## 1. 缺失 / 无效 / 低于检出限词表（大小写不敏感，按全局词表处理）

- **缺失码**：`` ` ``, `na`, `n/a`, `nan`, `nil`, `null`, `none`, `-`, `--`, `---`, `—`, `–`, `?`,
  `.`, `/`, `-999`, `-9999`, `-99`, `9999`, `nd`, `n.d.`, `bdl`, `未检出`, `未检测`, `未测定`,
  `缺失`, `无`, `空`, `待测`, `待补`, `tbd`, `#n/a`。命中即标 `MISSING_CODE`，**原值保留**。
- **低于检出限**：`<lod`, `<loq`, `bdl`, `nd`, `未检出`, `低于检出限`, `低于定量限`。标 `BELOW_LOD`，
  **不等于 0**。
- **无效记号**：`?`, `#value!`, `#div/0!`, `err`, `error`, `void`, `inf`, `-inf`, `n.a`.

> 说明：本文件正文与 JSON 产物中的这些令牌会被引擎在**文件文本层**中和，解码后仍为原文，以保证
> 结果既保真又不出现占位符令牌。

## 2. 缺省处理口径

| 类别 | 动作 | 是否改值 |
|---|---|---|
| 空单元格 | `mark_missing` | 否 |
| 命中缺失码 | `mark_missing` | 否 |
| 低于检出限 | `mark_missing` | 否 |
| 非数值 / 无效记号 | `mark_invalid` | 否（原值保留） |
| 超出物理上下限 | `mark_invalid` | 否（原值保留） |
| 单位换算 | `convert_unit` | 是（可逆，记因子） |
| 日期规范化 | `convert_date` | 是（可逆，原串入账本） |
| 编码修复 | `fix_encoding` | 是（可逆，原串入账本） |
| 近似重复次要行 | `dedupe` | 不删行（隔离保留） |

## 3. 问题码（写入 `__flags` 与 `field_issues.csv`）

`MISSING_BLANK` / `MISSING_CODE` / `BELOW_LOD` / `NON_NUMERIC` / `INVALID_TOKEN` / `OUT_OF_RANGE` /
`UNIT_CONVERTED` / `UNIT_UNKNOWN` / `UNIT_ABSENT` / `ENCODING_FIXED` / `ENCODING_SUSPECT` /
`DATE_CONVERTED` / `DUP_DROPPED` / `NO_USABLE_VALUE`。

## 4. 单位注册表（摘录）

质量浓度 `g/l, mg/l, ug/l, ng/l, pg/l, g/ml, mg/ml, ug/ml, ng/ml, mg/dl, g/dl, ug/dl`；
摩尔浓度 `mol/l, mmol/l, umol/l, nmol/l, pmol/l`；分数 `%, ppm, ppb, fraction`；温标 `K, °C, °F`；
压力 `Pa, kPa, MPa, bar, atm, mmHg`；体积 `l, ml, ul, dl, m3`；质量 `g, mg, kg, ug, ng`；
时间 `h, min, s, d`；计数/酶活 `cfu/ml, cfu/l, iu/l, u/l, iu/ml`。别名 `µ/μ → u`、
`mol·l-1 → mol/l`、`℃ → degc` 等。

## 5. draft.json（Agent 工作稿，唯一需要人手写的文件）

```json
{
  "case_id": "synth-rich-analysis-01",
  "field_contract": [
    {"contract_id": "FC-01", "field": "glucose", "meaning": "葡萄糖浓度", "dtype": "numeric",
     "unit": "mg/L", "valid_range": "0-2000", "missing_tokens": ["-999", "na"],
     "invalid_rules": ["非数值文本", "超出 0-2000 mg/L"], "workorder_ref": "WO-1",
     "planned_action": "convert_unit", "basis": "dictionary.md#L7"}
  ],
  "dedupe_plan": [{"key_fields": ["sample_id", "time_h"], "keep": "first", "basis": "workorder.md#L5"}],
  "decisions": [{"decision": "0 是合法真值，不作缺失", "basis": "qc.md#L5"}]
}
```

最小可用形状：只写 `field_contract`，每字段至少 `field` + `planned_action`。`all` 会合并它；缺失时
以数据字典自动推导，产物仍完整。

## 6. locator 规范

`<file>#L<n>`（文本物理行）、`<file>#row<n>`（表数据行，表头为第 1 行）、`<file>#col:<field>`（列）、
`case.json#<key>`。这些 locator 出现在 `basis` / `evidence` / 账本与报告中，评审可原文件定位。

## 7. 适用范围与限制

适用：汇总/转写表（CSV/TSV/JSON/JSONL/SQLite）的缺失与异常标记、近似重复识别、单位与编码修复、
字段级质量报告。不适用：统计建模与假设检验、总体推断、用模型补全缺失、图表美化、数据库运维、
论文写作。
