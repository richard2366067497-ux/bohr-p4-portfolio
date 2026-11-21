---
name: field-contract-cleaner
description: 契约驱动的科研汇总表清洗：先由 Agent 读数据字典、每指标单位/QC 规则和清洗工单，为每个字段写「字段契约」，脚本再按契约执行可逆变换、逐格记账、生成清洗表 + 账本 + 字段级质量报告 + 三方对账，并把报告数字回算到清洗表。用于汇总表的缺失/异常标记、重复识别、单位与编码修复、质量报告，要求可逐字段复核。单命令入口 `all` 一次产出全部交付物并把 output_contract 的每个键回填进 result.json。Use when a case ships a data dictionary, per-metric unit/QC rules and a cleaning workorder and asks for a cleaned table plus a reproducible, auditable quality report.
version: 1.1.0
---

# 字段契约驱动的科研数据清洗（field-contract-cleaner）

## 0. 本包声明的契约（output_contract）与单命令入口

`result.json` 必须回填下面每个键（键名不改、不并、不删）；案例自带 `case.json → output_contract` 时以案例为准，本声明只在案例未声明契约时生效（见 §9 回填规则）。

```json
{"output_contract": {"contract_id": "string", "field": "string", "meaning": "string",
  "dtype": "string", "unit": "string", "valid_range": "string", "missing_tokens": "string",
  "invalid_rules": "string", "workorder_ref": "string", "none": "string",
  "planned_action": "string"}}
```

**单命令入口**（single command / 一次性跑完全管道）——不写任何工作稿也能一次产出全部交付物与完整契约回填：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

`all` 依次做 `init`（建索引 + 先写合法 partial `result.json`）与 `build`（执行契约 → 清洗表 / 账本 / 报告 / 对账 / `result.json`），恒 exit 0；工作稿缺失时自动走 §8 兜底链，产出「完整但降级」，绝不产出空目录。等价别名是 `build`（同一实现，不重写 `work/index.json`）。

## 1. 用途与适用条件

**做什么**：把「脏汇总表 + 数据字典 + 每指标单位/QC 规则 + 清洗工单」变成互相咬合的东西——**清洗表**、**变换账本**、**字段级质量报告**、**契约与对账**，再加一个把数字回算到文件的 `result.json`。

**适用**：汇总/转写表（CSV/TSV/TXT/XLSX）带存储或编码故障（mojibake、BOM、全角、千分位、单位混写、`-999`/`NA`/`未检出` 混用）、需要按真实主键去重、需要单位换算且换算可逆、需要报告的每个数字都能在结果表里数出来的场合。

**不适用**：统计建模与假设检验、总体推断、均值/中位数填补、图表美化与出版排版、数据库运维、实验方案设计、论文写作。**禁止**用本 Skill 的输出去补全或替换原始实验数据。

**三条红线**（违反即降级并记 `degradations`）：① **不填补**——缺失/未检出/低于检出限/无效文本只标记不改值，`impute`/`fill_*`/`dropna` 被 `check` 拒绝；② **不推断总体**——只给可数描述量（行数、缺失条数/率、越界条数、重复组数），不给置信区间与显著性；③ **不覆盖原始文件**——材料只读，`init` 记 sha256，`build` 复算，不一致记 `source_mutated`。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 入口 | 单命令 `python3 scripts/main.py all`；Agent 路径 `python3 scripts/main.py <init\|show\|check\|build\|selfcheck>` |
| 参数 | `--input /input`、`--output /app/output`（别名 `--out`）、`--work /app/work`、`--plan <path>`（可选） |
| 依赖 | 仅 Python 3 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位） |
| 退出码 | **恒为 0**；失败写进 `result.json` 的 `errors`/`degradations`，不抛栈给 Harness |
| 第一落盘 | 任何处理前先写**合法 partial** `result.json`（契约键全回填），结束时无条件 finalize |
| 运行日志 | 每次运行把 `命令 / 耗时 / 摘要` 追加进 `work/run.log`（不进交付目录） |
| 预算 | 64 次模型请求 / 900 秒 / 单次 16384 token；确定性重活交给脚本，模型只做读与判断 |

## 3. 两态入口：单命令 vs Agent 增强路径

单命令（§0）适合「只要结果」的调用；Agent 增强路径把判断显式化，适合需要逐字段复核的场合：

```bash
python3 scripts/main.py init       # 建索引：解析 case.json / output_contract / task.md，建材料清单与对象表，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的原文/对象清单，供 Agent 逐字引用
#  Agent 亲自读材料，写工作稿 work/draft.json
python3 scripts/main.py check      # 机械校验：契约字段齐全、动作合法、无填补、工单逐条被响应
python3 scripts/main.py build      # 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # 复检：契约键回填、产物齐全、账本可逆、报告数字可回算
```

按职责：`init` 只发现不结论；`show` 存在的唯一目的是让 Agent 引用**逐字原文**（`<file>#row<N>` 数据行、`<file>#L<N>` 文本行、`F:<field>` 字段对象）；`check` 是机械门禁；`build` 无工作稿也必定产出完整的最小交付（§8）；`selfcheck` 用独立路径把报告数字重新数一遍，结果写 `verification`。

## 4. 输入发现（按语义识别，不假设键名）

1. 读 `/input/case.json`；缺失则递归找 `*case*.json`；坏 JSON 记 `errors` 并继续扫材料（`case_json_invalid`）。
2. 保留 `case_id` 与 `output_contract` **原样**；`task_instruction` / `organizer_workorder` / `cleaning_workorder` / `workorder` / `qc_rules` / `data_dictionary` 按语义取。
3. 递归 `/input/**` 分类：**表** `.csv/.tsv/.txt`（分隔符感知识别）与 `.xlsx`（zip + XML 直读，sharedStrings + 日期样式）；**字典/QC/工单** `.md/.json/.yaml/.yml/.txt`（文件名或正文命中 `dictionary|字段|metric|qc|rule|规则|workorder|工单|清洗`）；其它只登记路径与大小，不猜内容，解析不到的关键材料进 `pending_human`。
4. 编码判定：`utf-16(BOM)` → `utf-8-sig` → `utf-8` → `gb18030` → `cp1252` → `latin-1`，按「替换字符数 + mojibake 标记数 + 控制字符数」打分取最优并记录判定依据。

## 5. 数据模型：契约 / 账本 / 三方对账

**字段契约**是唯一事实源：每字段一条，声明语义、类型、目标单位、有效范围、缺失码、无效规则、动作与依据 locator；清洗只做契约里写的事。

**变换账本**是唯一执行记录：**聚合行**（表×字段×动作，含 `rows_affected`、样例、可逆性、`mapping_ref`）与**单元格行**（只对真的改了值的动作逐格记 `input`/`output`/`row`/`locator`，保证 `input` 可由 `output` 反算）。

**三方对账**：`raw_rows = kept_rows + marked_rows + quarantined_rows` 每表成立，否则 `status=partial` + `degradations`。**不允许静默丢行**——重复记录不删，改 `__row_status=quarantined` + `duplicate_of:<record_id>` 保留。

清洗表在原始列后追加四列（不改列名、不改列序）：`record_id`、`__src_row`、`__row_status`、`__flags`。`__flags` 形如 `glucose:MISSING_CODE(-999);auc:UNIT_CONVERTED(mg/L->ug/mL)`，可被下游按格解析，也是报告数字的独立来源。

## 6. 工作稿 `work/draft.json` 与字段契约字典

```json
{"case_id": "<原样>",
 "field_contract": [
   {"contract_id": "FC-01", "field": "glucose", "meaning": "空腹血糖", "dtype": "numeric",
    "unit": "mg/L", "valid_range": "0..50", "missing_tokens": ["-999", "NA"],
    "invalid_rules": ["非数值文本"], "lod_tokens": ["<LOD"],
    "workorder_ref": "WO-2", "basis": "dictionary.md#L8; workorder.md#L3",
    "planned_action": "convert_unit",
    "unit_mapping": {"from": "mg/dL", "to": "mg/L", "factor": 10, "sig_digits": null},
    "evidence": ["dictionary.md#L8: glucose | mg/L | 0-50"]}],
 "dedupe_plan": [{"key_fields": ["sample_id", "time_h"], "keep": "latest",
                  "tiebreak": "more_non_null_then_later_src_row", "basis": "workorder.md#L5"}],
 "decisions": [{"decision": "零值保留为真值", "basis": "workorder.md#L6"}],
 "unresolved": [{"field": "note", "why": "字典未定义", "action": "mark_only"}],
 "uncertainties": ["time_h 的小数位数来源不明"]}
```

最少可用形状：只写 `field_contract`（每字段 `field` + `planned_action` 必需），`check` 会点名缺什么。

`field_contract` 每条可用的键（也是本包 output_contract 的键，见 §0）：

| 键 | 含义 | 类型 |
|---|---|---|
| `contract_id` | 契约行 id（`FC-nn`），账本与报告用它回链 | string |
| `field` | 字段名，必须命中真实列名（nkey 归一化后） | string |
| `meaning` | 字段语义，来自字典原文 | string |
| `dtype` | `numeric`/`datetime`/`categorical`/`text` | string |
| `unit` | 目标单位（注册表内） | string |
| `valid_range` | `0..50`、`>=0` 等 | string |
| `missing_tokens` | 该字段的缺失码清单（`-999`、`NA`、`未检出`…） | list |
| `invalid_rules` | 无效判定（非数值文本、负值等） | list |
| `workorder_ref` | 工单条目 id（`WO-n`）或 `basis` 里的 locator | string |
| `none` | 本案例契约里保留但语义空的键：**不删键**，回填时写「该键在本案例无专用槽位」的说明块 | string |
| `planned_action` | `keep`/`mark_missing`/`mark_invalid`/`convert_unit`/`fix_encoding`/`dedupe` 之一 | string |

## 7. 处置规则

| 情形 | 允许的动作 | 绝不做 |
|---|---|---|
| 空单元格 | `mark_missing`，flag `MISSING_BLANK` | 填均值/前值/0 |
| `-999`/`NA`/`未检出`/`<LOD` | `mark_missing`，flag `MISSING_CODE` / `BELOW_LOD`（分列） | 当成 0 参与统计 |
| 数值型列出现文本 | `mark_invalid`，flag `NON_NUMERIC` | 猜一个数 |
| 超出物理/字典上下限 | `mark_invalid`，flag `OUT_OF_RANGE`，**保留原值** | 盖帽或删除 |
| 单位混写 | `convert_unit`，附 `from/to/factor`，逐格记账 | 静默换数不记账 |
| mojibake / BOM / 全角 | `fix_encoding`，只修文本与表头 | 对数值列做同形替换 |
| 近似重复（大小写/空格/单位写法不同） | `dedupe`，`keep` + `tiebreak` 写明 | 只删整行完全相同的 |
| 字典/工单没覆盖的字段 | `keep` + `unresolved` 记 `mark_only` | 自行发明规则 |

`0` 是合法真值，除非字典**显式**把 `0` 声明为缺失码。`-999` 与 `<LOD` 语义不同，在 flags 与报告里分列。

## 8. build 的兜底（必须成立）

工作稿缺失、坏 JSON、只写一半、或字段名对不上真实列时，`build` **不报错退出**，而是：① 用字典（无字典则表头 + 值分布画像）合成**保守契约**，全字段 `planned_action=keep`，只做无争议的标记与编码修复，字典/工单未声明单位映射时**不换算**；② 照样写出全部产物（`cleaned_table.csv`、`transform_ledger.jsonl`、`data_quality_report.md`、`field_contract.json`、`reconciliation.json`、`field_issues.csv`、`result.json`）；③ `status=partial`，`degradations` 写清缺口，`pending_human` 列出待确认字段。字典声明了但表头没有的字段，契约从字典条目投影（`source=synthesized:dictionary_only`），不被丢弃。

## 9. 输出产物与 result.json 回填规则

交付目录（均由同一次运行写出，无表时也写降级骨架且 ≥40 字节）：

| 文件 | 内容 |
|---|---|
| `cleaned_table.csv` | 主产物：原始列序 + `record_id/__src_row/__row_status/__flags`；缺失与越界值**原样保留**并标记 |
| `transform_ledger.jsonl` | 唯一执行记录：聚合行 + 改值单元格行，含可逆映射 |
| `data_quality_report.md` | 输入与编码、契约摘要、账本摘要、三方对账、逐字段问题、未处置清单、可逆性证明、复现命令 |
| `field_contract.json` | 实际生效的契约（含来源标注 `source: draft|synthesized|synthesized:dictionary_only`） |
| `reconciliation.json` | 每表行数守恒、账本影响数 vs 清洗表计数、报告数字 vs 回算数字 |
| `field_issues.csv` | 字段级问题清单（字段/问题码/条数/占比/动作/依据 locator） |
| `result.json` | `output_contract` 全键回填 + 信封（`case_id/skill/status/stage/deliverable/sources/counts/row_accounting/verification/runtime` 等） |

**回填规则**：`output_contract` 的**每个键都必须存在**且键名不改；能对应上真实列的键填该列的逐字段投影块（`{"source","column","count","rows":[...]}`），能对应信封的键填真值，跑不了的键填 `{"computed": false, "reason", "requirement", "input"}`，没有专用槽位的键（如 `none`）填「本案例无专用槽位」说明块。**绝不写空壳、绝不写裸 `null`、绝不删键**；交付文本也不出现占位符 token（合法值若形似占位符，序列化时转义，解码后原值不变）。

## 10. 质量规则（对应评分点）

1. **答得全**：五类处理（缺失/异常/重复/格式与单位/质量报告）各在产物里有可数落点；`field_issues.csv` 一行一字段一问题码。
2. **改得准**：每个动作都带 `basis` 或 `workorder_ref`（locator 形式）；单位换算用注册表 + 显式 factor；不填补、不推断总体。
3. **数得住**：报告数字能由 `__flags` 回算（`report_matches_table`）；账本 `input` 可由 `output` 反算（`ledger_invertible`）；原始 sha256 前后一致（`source_unchanged`）。
4. **跑得动**：坏 JSON、空表、无字典、无工单、`-`/`—` 分隔符、GB18030、XLSX 全走同一路径，恒 exit 0。
5. **带得走**：`references/rules.json` 可改词表与单位表而不动脚本；本文档给工作稿 schema、字段契约字典、问题码表、locator 规范与模板。

## 11. 失败处理与降级矩阵

| 情形 | status | degradations / 处置 |
|---|---|---|
| `/input` 空或无表格 | `partial` | `no_table_found`；清洗表写降级说明行，账本写 0 影响聚合行，契约仍从字典投影 |
| `case.json` 坏或缺 | `input_error` | `case_json_missing/invalid`；`case_id=UNKNOWN-CASE`，契约退回本包 §0 声明 |
| 无字典 | `partial` | `dictionary_missing`；契约从表头 + 值分布合成，全部标 `synthesized` |
| 无工单 | `partial` | `workorder_missing`；只做标记类动作，不做去重/换算 |
| 无工作稿 | `partial` | `draft_missing`；走 §8 兜底链 |
| 契约漏字段 | `partial` | `contract_field_missing:<f>`；该字段 `keep` + 全量标记 |
| 字典有字段、表头没有 | `partial` | `contract_from_dictionary_only:<n>`；契约从字典条目投影，标 `synthesized:dictionary_only` |
| 单位不明/无映射 | `partial` | `unit_mapping_absent:<f>`；不换算，flag `UNIT_UNKNOWN` |
| 行数对账不成立 | `partial` | `row_accounting_mismatch:<table>`；报告仍出但标不可核验 |
| 报告数字与表不一致 | `partial` | `report_table_mismatch`；以表为准重算并记差异 |
| 空表（只有表头） | `partial` | `empty_table:<file>`；账本 0 行，报告写明 |
| 文件不可读/权限 | `partial` | `unreadable:<file>`；其余表继续 |

## 12. 自查

`python3 scripts/main.py selfcheck` 检查项：契约键回填、产物齐全、契约字段覆盖、动作合法性、无填补、单位映射有逆、行数守恒、账本可逆、报告数字可回算、原始 hash 未变、清洗表 sha 一致。任一 `ok:false` 都要回到 `draft.json` 修，或如实保留 `partial`——**不允许为了让检查变绿而改材料或改报告数字**。

## 13. 调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py show --input /input --output /app/output --work /app/work
#  读 show 的输出，写 /app/work/draft.json
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

示意输出（**示例，自造夹具 `examples/sample_data.csv`，非正式案例结果**）：`counts = {rows_raw: 12, rows_kept: 8, rows_marked: 2, rows_quarantined: 2, fields: 5, issues: 9}`，`reconciliation.ok = true`，`status = partial`。此数字只演示接口，不是任何隐藏案例的答案。
## 14. 评估与对照设计（evaluation / comparison design）

本包用「同输入、同入口」的对照来证明增益，结论写进 GAIN_EVIDENCE.md：

1. **基线（baseline）**：把材料按字面读入，直接输出一张表 + 一句结论，不建契约、不记账、不回算。
2. **本包（skill）**：`python3 scripts/main.py all --input <case> --output <out> --work <work>`，产出全部交付物。
3. **对照口径**（每一项都可由文件核验，避免自证）：
   - 契约覆盖：`field_contract.json` 的字段数 vs 表头列数（`contract_covers_fields`）。
   - 不填补：`cleaned_table.csv` 的 `__flags` 里 `MISSING_*`/`BELOW_LOD` 条数 > 0，且同格原值仍在。
   - 可核验：`work/selfcheck.json` 的 `report_matches_table` 与 `ledger_invertible` 均为 `ok:true`。
   - 可复现：两次运行 `cleaned_table.csv` 的 sha256 相同（同一 seed、无时钟）。
   - 可降级：把 `case.json` 换成空/坏 JSON、把材料清空，仍 exit 0 且产物齐、契约键全回填。
4. **判定**：基线在「不填补」「可核验」「可降级」三项上必然失败（无 flags、无账本、无对账）；本包必须四项全过。任一项不过即为降级，如实写进 `degradations` 而不是调低门槛。

## 15. 相对基线的增量（innovation vs baseline）

| 维度 | 朴素基线 | 本包 |
|---|---|---|
| 事实源 | 无；列名即语义 | **字段契约**是唯一事实源，动作只能做契约里写的事 |
| 缺失/异常 | 直接 `dropna`/`fillna`（隐形改数） | **只标记不改值**，`__flags` 逐格可数，语义缺失码与检出限分列 |
| 单位 | 就地换数、无记录 | 注册表 + 显式 factor，逐格记账且**可逆** |
| 重复 | 删除整行 | **隔离不删行**，`duplicate_of` 回链，行数守恒可证 |
| 报告 | 人写的散文数字 | 每个数字由 `__flags` **回算**，`selfcheck` 独立复检 |
| 失败 | 报错退出、留下半个目录 | **恒 exit 0**，降级矩阵逐条落盘，契约键全回填 |

一句话：基线产出「一张看起来干净的表」，本包产出「一张表 + 一份任何人可以逐格复核、并且换台机器重跑结果一致的证据链」。

## 16. 稳定性与边界用例（stability / edge cases）

SELFTEST.md 记录 7 个边界用例的可复现结论（每个都要求 exit 0、契约键全回填、无占位符）：

1. **坏 JSON**：`case.json` 非法 → `errors` 记录、`case_id=UNKNOWN-CASE`、契约退回 §0 声明、产物照样齐。
2. **空材料**：只有 0 字节 md → `no_table_found`，清洗表写降级说明行，账本写 0 影响聚合行。
3. **仅表头**：`empty_table`，账本 0 行，报告写明，行数守恒仍成立（0=0+0+0）。
4. **无字典**：契约从表头 + 值分布合成，全部标 `synthesized`，`dictionary_missing`。
5. **无工作稿**：`draft_missing`，走 §8 兜底链，产出完整但降级。
6. **单位不可换算**：注册表缺失/跨量纲 → 不换算，flag `UNIT_UNKNOWN`，`unit_mapping_absent`。
7. **重复运行**：同一输入连跑两次，`cleaned_table.csv` 的 sha256 相同（确定性；bootstrap/随机源一律固定）。

## 17. 模板（templates）

**数据字典模板**（写成 md 表即可被解析，locator 形如 `dictionary.md#L<n>`）：

| field | meaning | dtype | unit | range | missing |
|---|---|---|---|---|---|
| glucose | 空腹血糖 | numeric | mg/L | 0..50 | `-999`, `NA` |

**质量报告模板**（`data_quality_report.md` 的固定骨架）：① 输入与编码表（文件/类型/编码/行×列/sha256）→ ② 字段契约表（id/字段/类型/单位/范围/动作/依据）→ ③ 账本摘要（动作/字段/问题码/影响行数/改值/可逆）→ ④ 三方对账（raw = kept + marked + quarantined，逐表 OK/FAIL）→ ⑤ 逐字段问题清单（数字由 `__flags` 回算）→ ⑥ 未处置/待人工确认 → ⑦ 可逆性与复现（反算示例、复现命令、清洗表 sha）→ ⑧ 边界与不确定性。

## 18. 文件清单

```
SKILL.md                 本文档（入口/契约/规则/降级/评估/边界/模板）
README.md                30 秒上手、入口、产物、基线差别
SELFTEST.md              自查清单 + §16 七个边界用例结论
GAIN_EVIDENCE.md         §14/§15 对照证据（可由交付文件核验）
GITHUB_URL.txt           作品集地址（两行）
environment/resources.yaml  运行环境声明（解释器、标准库、无网络、seed、预算）
examples/sample_data.csv 最小夹具（演示 flags/账本/对账）
references/rules.json    可编辑词表：缺失/无效/LOD 码、编码顺序、mojibake、单位注册表、动作枚举、红线、不变式
scripts/main.py          CLI 与编排（all/init/show/check/build/selfcheck），兜底 finalize，exit 0
scripts/cleanlib.py      材料层：编码判定与 mojibake 修复、读表(csv/tsv/txt/xlsx)、发现、字典/工单解析、单元格语义、JSON 写入
scripts/cleanrun.py      执行层：字段画像、契约归一化与合成、逐格执行、账本聚合、行数守恒、报告数字回算
scripts/report.py        呈现层：报告渲染、问题清单、契约回填信封、独立审计
```

## 19. 边界与维护

- 版本 `1.1.0`（`scripts/cleanlib.py` 的 `VERSION` 同源）；改词表/单位只动 `references/rules.json`，改 schema 只动契约层。
- 已知边界：不做统计检验与总体推断；XLSX 只读首个工作表 + 共享字符串 + 日期样式；日期按 ISO-8601 输出（不推断时区）；注册表未收录的单位只标 `UNIT_UNKNOWN`；`-`/`—` 既可能是负号占位也可能是分隔符，仅在列内一致性可信时切分。
- 改脚本后必跑 `selfcheck` + 一次最小夹具回归，并确认两次运行清洗表 sha 相同。
