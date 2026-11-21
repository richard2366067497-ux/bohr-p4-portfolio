---
name: field-contract-cleaner
description: 契约驱动的科研汇总表清洗：先由 Agent 读数据字典、每指标单位/QC 规则和清洗工单，为每个字段写「字段契约」，脚本再按契约执行可逆变换、逐格记账、生成清洗表 + 账本 + 字段级质量报告 + 三方对账，并把报告数字回算到清洗表。用于汇总表的缺失/异常标记、重复识别、单位与编码修复、质量报告，要求可逐字段复核。单命令入口 `all` 一次产出全部交付物并把 output_contract 的每个键回填进 result.json。Use when a case ships a data dictionary, per-metric unit/QC rules and a cleaning workorder and asks for a cleaned table plus a reproducible, auditable quality report.
version: 1.2.0
---

# 字段契约驱动的科研数据清洗（field-contract-cleaner）

把「脏汇总表 + 数据字典 + 每指标单位/QC 规则 + 清洗工单」变成互相咬合的东西——清洗表、变换账本、
字段级质量报告、契约与对账，再加一个把数字回算到文件的 `result.json`。

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 `references/expert_playbook.md`**，并按它组织全部产出：按其 §2 六步流程推进，
按其 §4 公式与口径核算缺失率/异常条数/重复组/转换记录，按其 §5 逐条排雷，按其 §7 自查表交付。

## Output contract（逐键回填）

`result.json` 必须回填下面每个键（键名不改、不并、不删）；案例自带 `case.json → output_contract` 时以案例为准，
本声明只在案例未声明契约时生效。

```json
{"output_contract": {"contract_id": "string", "field": "string", "meaning": "string",
  "dtype": "string", "unit": "string", "valid_range": "string", "missing_tokens": "string",
  "invalid_rules": "string", "workorder_ref": "string", "none": "string",
  "planned_action": "string"}}
```

回填规则：能对应真实列的键填该列的逐字段投影块 `{"source","column","count","rows":[...]}`；能对应信封的键填真值；
跑不了的键填 `{"computed": false, "reason", "requirement", "input"}`；无专用槽位的键（如 `none`）填
「本案例无专用槽位」说明块。**绝不写空壳、绝不写裸 `null`、绝不删键**。

## 单命令入口（评测单命令，先跑这一条）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

`all` 依次做 `init`（建索引 + 先写合法 partial `result.json`）与 `build`（执行契约 → 清洗表 / 账本 /
报告 / 对账 / `result.json`），恒 exit 0；工作稿缺失时自动走兜底链，产出「完整但降级」，绝不产出空目录。
等价别名是 `build`（同一实现，不重写 `work/index.json`）。

## 用途与适用条件

**适用**：汇总/转写表（CSV/TSV/TXT/XLSX）带存储或编码故障（mojibake、BOM、全角、千分位、单位混写、
`-999`/`NA`/`未检出` 混用）、需按真实主键去重、需单位换算且可逆、需报告的每个数字都能在结果表里数出来。

**不适用**：统计建模与假设检验、总体推断、均值/中位数填补、图表美化与出版排版、数据库运维、实验方案设计、论文写作。
**禁止**用本 Skill 的输出去补全或替换原始实验数据。

**三条红线**（违反即降级并记 `degradations`）：① **不填补**——缺失/未检出/低于检出限/无效文本只标记不改值；
② **不推断总体**——只给可数描述量（行数、缺失条数/率、越界条数、重复组数）；
③ **不覆盖原始文件**——材料只读，`init` 记 sha256，`build` 复算，不一致记 `source_mutated`。

## 运行契约

| 项 | 值 |
|---|---|
| 入口 | 单命令 `python3 scripts/main.py all`；Agent 路径 `python3 scripts/main.py <init\|show\|check\|build\|selfcheck>` |
| 参数 | `--input /input`、`--output /app/output`（别名 `--out`）、`--work /app/work`、`--plan <path>`（可选） |
| 依赖 | 仅 Python 3 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位） |
| 退出码 | **恒为 0**；失败写进 `result.json` 的 `errors`/`degradations`，不抛栈给 Harness |
| 第一落盘 | 任何处理前先写**合法 partial** `result.json`（契约键全回填），结束时无条件 finalize |
| 运行日志 | 每次运行把 `命令 / 耗时 / 摘要` 追加进 `work/run.log`（不进交付目录） |
| 预算 | 64 次模型请求 / 900 秒 / 单次 16384 token；确定性重活交给脚本，模型只做读与判断 |

## 数据模型：契约 / 账本 / 三方对账

**字段契约**是唯一事实源：每字段一条，声明语义、类型、目标单位、有效范围、缺失码、无效规则、动作与依据 locator。
**变换账本**是唯一执行记录：聚合行（表×字段×动作，含 `rows_affected`、样例、可逆性、`mapping_ref`）与
单元格行（只对真改值的动作逐格记 `input`/`output`/`row`/`locator`，保证 `input` 可由 `output` 反算）。
**三方对账**：`raw_rows = kept_rows + marked_rows + quarantined_rows` 每表成立，否则 `status=partial`。
**不允许静默丢行**——重复记录不删，改 `__row_status=quarantined` + `duplicate_of:<record_id>` 保留。

清洗表在原始列后追加四列（不改列名、不改列序）：`record_id`、`__src_row`、`__row_status`、`__flags`。
`__flags` 形如 `glucose:MISSING_CODE(-999);auc:UNIT_CONVERTED(mg/L->ug/mL)`，可被下游按格解析，也是报告数字的独立来源。

## 工作稿 `work/draft.json`（可选）与字段契约字典

```json
{"case_id": "<原样>",
 "field_contract": [{"contract_id": "FC-01", "field": "glucose", "meaning": "空腹血糖", "dtype": "numeric",
   "unit": "mg/L", "valid_range": "0..50", "missing_tokens": ["-999", "NA"], "invalid_rules": ["非数值文本"],
   "workorder_ref": "WO-2", "basis": "dictionary.md#L8; workorder.md#L3", "planned_action": "convert_unit",
   "unit_mapping": {"from": "mg/dL", "to": "mg/L", "factor": 10, "sig_digits": null}}],
 "dedupe_plan": [{"key_fields": ["sample_id", "time_h"], "keep": "latest", "basis": "workorder.md#L5"}],
 "unresolved": [{"field": "note", "why": "字典未定义", "action": "mark_only"}], "uncertainties": []}
```

最少可用形状：只写 `field_contract`（每字段 `field` + `planned_action` 必需），`check` 会点名缺什么。
`planned_action` ∈ `keep|mark_missing|mark_invalid|convert_unit|fix_encoding|dedupe`。

## 处置规则

| 情形 | 允许的动作 | 绝不做 |
|---|---|---|
| 空单元格 | `mark_missing`，flag `MISSING_BLANK` | 填均值/前值/0 |
| `-999`/`NA`/`未检出`/`<LOD` | `mark_missing`，flag `MISSING_CODE`/`BELOW_LOD`（分列） | 当成 0 参与统计 |
| 数值列出现文本 | `mark_invalid`，flag `NON_NUMERIC` | 猜一个数 |
| 超出物理/字典上下限 | `mark_invalid`，flag `OUT_OF_RANGE`，**保留原值** | 盖帽或删除 |
| 单位混写 | `convert_unit`，附 `from/to/factor`，逐格记账 | 静默换数不记账 |
| mojibake / BOM / 全角 | `fix_encoding`，只修文本与表头 | 对数值列做同形替换 |
| 近似重复 | `dedupe`，`keep` + `tiebreak` 写明 | 只删整行完全相同的 |
| 字典/工单未覆盖的字段 | `keep` + `unresolved` 记 `mark_only` | 自行发明规则 |

`0` 是合法真值，除非字典**显式**把 `0` 声明为缺失码。`-999` 与 `<LOD` 语义不同，在 flags 与报告里分列。

## 交付产物（均由同一次运行写出，无表时也写降级骨架且 ≥40 字节）

| 文件 | 内容 |
|---|---|
| `cleaned_table.csv` | 主产物：原始列序 + `record_id/__src_row/__row_status/__flags`；缺失与越界值原样保留并标记 |
| `transform_ledger.jsonl` | 唯一执行记录：聚合行 + 改值单元格行，含可逆映射 |
| `data_quality_report.md` | 输入与编码、契约摘要、账本摘要、三方对账、逐字段问题、未处置清单、可逆性证明、复现命令 |
| `field_contract.json` | 实际生效的契约（含 `source: draft\|synthesized\|synthesized:dictionary_only`） |
| `reconciliation.json` | 每表行数守恒、账本影响数 vs 清洗表计数、报告数字 vs 回算数字 |
| `field_issues.csv` | 字段级问题清单（字段/问题码/条数/占比/动作/依据 locator） |
| `result.json` | `output_contract` 全键回填 + 信封（`case_id/skill/status/stage/sources/counts/row_accounting/verification/runtime` 等） |

## 失败处理与降级矩阵

| 情形 | status | degradations / 处置 |
|---|---|---|
| `/input` 空或无表格 | `partial` | `no_table_found`；清洗表写降级说明行，账本写 0 影响聚合行，契约仍从字典投影 |
| `case.json` 坏或缺 | `input_error` | `case_json_missing/invalid`；`case_id=UNKNOWN-CASE`，契约退回本包声明 |
| 无字典 | `partial` | `dictionary_missing`；契约从表头 + 值分布合成，全部标 `synthesized` |
| 无工单 | `partial` | `workorder_missing`；只做标记类动作，不做去重/换算 |
| 无工作稿 | `partial` | `draft_missing`；走兜底链，产出完整但降级 |
| 字典有字段、表头没有 | `partial` | `contract_from_dictionary_only:<n>`；契约从字典条目投影 |
| 单位不明/无映射 | `partial` | `unit_mapping_absent:<f>`；不换算，flag `UNIT_UNKNOWN` |
| 行数对账不成立 | `partial` | `row_accounting_mismatch:<table>`；报告仍出但标不可核验 |
| 空表（只有表头） | `partial` | `empty_table:<file>`；账本 0 行，报告写明 |
| 文件不可读/权限 | `partial` | `unreadable:<file>`；其余表继续 |

## Agent 增强路径（同一引擎，先读后写）

```bash
python3 scripts/main.py init       # 建索引：解析 case.json / output_contract / task.md，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的原文/对象清单，供 Agent 逐字引用
#  Agent 亲自读材料，写工作稿 work/draft.json
python3 scripts/main.py check      # 机械校验：契约字段齐全、动作合法、无填补、工单逐条被响应
python3 scripts/main.py build      # 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # 复检：契约键回填、产物齐全、账本可逆、报告数字可回算
```

`show` 存在的唯一目的是让 Agent 引用**逐字原文**（`<file>#row<N>` 数据行、`<file>#L<N>` 文本行、`F:<field>` 字段对象）。

## 自查

`python3 scripts/main.py selfcheck` 检查项：契约键回填、产物齐全、契约字段覆盖、动作合法性、无填补、单位映射有逆、
行数守恒、账本可逆、报告数字可回算、原始 hash 未变、清洗表 sha 一致，并**逐项通过 `references/expert_playbook.md` §7 的专家检查表**。
任一 `ok:false` 都要回到 `draft.json` 修，或如实保留 `partial`——**不允许为了让检查变绿而改材料或改报告数字**。

## 文件清单

```
SKILL.md                 本文档（入口/契约/规则/降级/自查）
README.md                30 秒上手、入口、产物、基线差别
SELFTEST.md              自查清单 + 边界用例结论
GAIN_EVIDENCE.md         对照证据（可由交付文件核验）
GITHUB_URL.txt           作品集地址（两行）
environment/resources.yaml  运行环境声明（解释器、标准库、无网络、seed、预算）
examples/sample_data.csv 最小夹具（演示 flags/账本/对账）
references/rules.json    可编辑词表：缺失/无效/LOD 码、编码顺序、mojibake、单位注册表、动作枚举、红线、不变式
references/expert_playbook.md  专家手册（六步流程/公式/陷阱/自查表/案例）
scripts/main.py          CLI 与编排（all/init/show/check/build/selfcheck），兜底 finalize，exit 0
scripts/cleanlib.py      材料层：编码判定与 mojibake 修复、读表(csv/tsv/txt/xlsx)、发现、字典/工单解析、单元格语义
scripts/cleanrun.py      执行层：字段画像、契约归一化与合成、逐格执行、账本聚合、行数守恒、报告数字回算
scripts/report.py        呈现层：报告渲染、问题清单、契约回填信封、独立审计
```
