# extraction_rules — 状态、claim 与 locator 口径

本文件冻结 `result.json` 的字段语义、四类状态的判定规则、locator 方案与字段字典口径。

## 1. 字段记录逐键语义

| 键 | 类型 | 语义 |
|-|-|-|
| `field_id` | string | 字段字典里的稳定标识，原样透传 |
| `field_name` | string | 人读字段名 |
| `definition` | string | 字段字典给出的定义（同时作为“未落位”时的搜索范围证据） |
| `expected_type` | string | 期望类型（number / text），仅用于选择落位策略 |
| `unit_hint` | string | 字典给出的单位提示 |
| `context_hint` | string | 字典给出的语境提示 |
| `value` | string | 已落位的值；未落位时为空串 |
| `units` | string | 单位；优先取列头括号内的标注 |
| `statistic` | string | 统计量类型，点值记 `point` |
| `condition` | string | 取值条件（表格行标签，如 `T6 aged` / `As-cast`） |
| `comparator` | string | 取的是哪一列（yield strength / elongation / hardness） |
| `source` | string | 取值处的 locator |
| `quote` | string | 逐字引文（表格行渲染串或段落句子） |
| `locator` | string | 引文所在位置的 locator |
| `claim_type` | string | `measured` / `reported` / `qualitative` / `unsupported` |
| `validation` | string | 该值是如何通过校验的 |
| `condition_complete` | bool | 条件是否完整（有无行标签） |
| `notes` | string | 未落位原因或补充说明 |
| `status` | string | 见 §2 |

## 2. 四类状态

| status | 判定 |
|-|-|
| `reported` | 表格单元格或段落句子给出了值，且引文通过逐字闸门 |
| `not_reported` | 材料只把该量标注为未测（`n.r.` 等），或材料里根本没有该量；证据取该行或字段定义 |
| `source_conflict` | 同一字段在两个来源出现互斥读数；两条读数都保留在 `notes` 与证据里 |
| `extraction_failed` | 材料/字典都在，但该字段无法判定；或因逐字闸门失败而撤回值 |

覆盖率：`coverage = reported / total`；`result.coverage` 同时给出四类计数。

## 3. locator 方案

| 对象 | 形式 | 例 |
|-|-|-|
| JSON 段落 | `{来源id}#{paragraph_id}` | `P2#P-S01` |
| 纯文本段落 | `{来源id}#block{n}` | `P1#block3` |
| 表格单元格 | `{来源id}#{table_id}:r{行}c{列}` | `P2#T1:r3c2` |
| 表格行 | `{来源id}#{table_id}:r{行}` | `P2#T1:r3` |
| 字段定义 | `{来源id}#field:{field_id}` | `P3#field:elongation_t6` |
| 任务文件句子 | `task.md#char{起}-char{止}` | `task.md#char3932-char3991` |

来源 id 按材料在索引中的顺序记为 `P1`、`P2`……重复材料按 sha1 去重，保留先出现的一份。

## 4. 表格行渲染与逐字闸门

- 一条表格行渲染为各单元格以 `" | "` 连接，例如 `T6 aged | 318 | 6.2 | 95`。
- 该渲染串在编索引时写入引文池；`quote` 必须是引文池里某个段落或行的逐字切片
  （比较前做空白归一，不忽略标点与大小写差异）。
- 段落策略只在**非定义段落**上执行：字段字典自身的定义段落永不作为值来源，
  以免把定义误当成值。

## 5. 列头与单位

- 单位从列头末端的括号里取：`Yield strength (MPa)` → `MPa`，`Hardness (HV)` → `HV`。
- 表格列头与行标签的匹配是大小写不敏感的包含匹配；定义里出现 `T6`/`aged` 时优先取行标签含
  `t6`/`aged` 的行，出现 `as-cast` 时优先取行标签含 `as-cast`/`as cast` 的行。
- 不做单位换算：列头标 `%` 就写 `%`，标 `MPa` 就写 `MPa`，不折算、不补 dispersion。

## 6. 不变量

- 不补写材料里没有的数字、单位、条件或结论。
- 每个已判定字段都要有 `quote` + `locator`；落不了位的字段也要带搜索范围证据。
- 草稿（agent-first）只能收紧、不能放松取证：未过逐字闸门的格子一律丢弃。
- 输出件中不出现未填写的模板标记；空值一律以空串或结构化说明表达。
