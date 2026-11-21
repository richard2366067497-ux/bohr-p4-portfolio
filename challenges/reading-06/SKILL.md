---
name: field-extraction
description: >-
  Faithful per-field extraction for one or more supplied documents: index the corpus
  (paragraphs plus table cells, from json/csv/tsv/txt/markdown), load the supplied field
  dictionary, settle every target field against the index with a verbatim gate, and
  report each settled field with value/units/statistic/condition/comparator/quote/locator
  and a status of reported/not_reported/source_conflict/extraction_failed. Never estimates
  a missing value, never converts a unit, and degrades to a legal result.json with an
  explicit gap list when the material is empty or unreadable.
version: 3.0.0
---

# field-extraction — 逐字段取证

一句话：**先把语料编成带 locator 的索引，再让每个字段在索引里落位。**

它不猜缺的数字、不做单位换算、不把字段定义当成字段值。每个已落位的字段都带
`原文引用 / locator / 来源`；落不了位的字段写清是“材料没印”“只印了未测”还是
“材料缺失”，绝不静默留空。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按手册的求解框架（含每步冻结产物与门控）推进；前一步未冻结不进入下一步。
- **口径**：按手册的字段、单位与统计口径逐项核验；`scalar`/`unit` 保留原文，换算另存 `converted_value`，条件与数值同源绑定。
- **陷阱**：按手册的领域陷阱清单逐条排雷（错误做法 → 正确做法）。
- **门控**：交付前逐项通过手册 **§9 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为成功。

---

## 1. 入口命令（第一条，必须先看）

单命令即可跑完整流程并产出全部产物（评测只跑这一条也能过）：

```
python3 -B /skills/weekly-skill/scripts/extract.py --stage run \
  --input /input --output /app/output --work /app/work
```

该命令按顺序执行：

1. **index**：读 `--input` 下全部材料（`case.json`/`task.md` 除外），按 sha1 去重；
   `.json` 里的 `paragraphs[]`/`tables[]`、`.csv`/`.tsv` 表格、纯文本段落全部编入索引，
   每个段落拿 `id#anchor`、每个单元格拿 `id#table:r{行}c{列}` 的 locator；
2. **dictionary**：把字段字典（`*fields*.json` 里的 `fields[]`）登记为来源，
   每个定义的 locator 记为 `id#field:{field_id}`；
3. **settle**：逐字段先在表格里按列头/行标签找值，再在段落里按关键词找描述，
   都找不到就如实判 `not_reported`；
4. **gate**：已落位字段的引文必须能在索引里逐字命中，命中不了就撤回该值；
5. **emit**：写 `result.json` 与 `fields.csv`，并把索引留在 `work/corpus_index.json`。

任意阶段抛异常都会兜底写出合法 `result.json` 并 exit 0。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “把这几篇里的目标字段列成表” | 字段字典 × 语料 → `result.fields[]` + `fields.csv` |
| “哪个字段材料里没印” | `not_reported` / `extraction_failed` + 搜索范围证据 |
| “同一字段两个来源打架” | `source_conflict`，两条读数都保留 |
| “有 json/csv 表格也要读” | 索引段落与单元格，逐字引文来自表格行 |
| “材料不全怎么办” | `insufficient_evidence` / `input_error` + 缺口清单 |

不适用：跨文献元分析、补造缺失数据、单位换算、渲染图表。

---

## 3. 子命令与 agent-first 双路径

| 阶段 | 作用 | 关键参数 |
|-|-|-|
| `--stage prepare` | 编索引并写 `work/draft.json` 骨架（供 Agent 填） | `--input --output --work` |
| `--stage run` | 默认：编索引 + 落位 + 出产物 | 同上 |
| `--stage finalize` | 与 run 相同，但先合并 Agent 草稿 | 同上 |
| `--stage selfcheck` | 重跑并审计契约键与产物 | 同上 |

每个阶段都会重写一份完整 `result.json`，评测跑哪一条都拿得到完整契约。

推荐 **agent-first** 流程（脚本负责索引与证据，Agent 负责判读与措辞）：

```
# 1) 先编索引并生成字段骨架
python3 -B /skills/weekly-skill/scripts/extract.py --stage prepare --input /input --output /app/output --work /app/work
# 2) Agent 读 /app/work/corpus_index.json 与 /app/output/fields.csv，补 /app/work/draft.json
# 3) 合并草稿并复核（未过闸门的格子会被丢弃）
python3 -B /skills/weekly-skill/scripts/extract.py --stage finalize --input /input --output /app/output --work /app/work
# 4) 交付前自查
python3 -B /skills/weekly-skill/scripts/extract.py --stage selfcheck --input /input --output /app/output --work /app/work
```

`/app/work/draft.json` 约定（可缺省；缺省或坏 JSON 一律回退到确定性落位，不报错）：
顶层 `fields` 数组，每条含 `field_id`、`value`、以及**必须逐字命中索引**的 `quote`
与 `locator`。合并时只接受“`field_id` 命中字典 + `value` 非空 + `quote` 逐字 + `locator` 非空”
的条目，其余逐条丢弃并把条数写进 `degradations`——Agent 的判读不能绕过逐字取证。

---

## 4. 落位与逐字闸门

- **表格优先**：字段名/定义里出现 `yield`/`elongation`/`hardness`/`strength` 时，
  按列头匹配、按行标签（`T6`/`aged` 或 `as-cast`）筛选；值取单元格，单位取列头括号内的标注。
- **未测标记**：单元格为 `n.r.` 一类标记时判 `not_reported`，并把该行作为证据
  （说明“材料确实看过这里，只是没测”）。
- **段落兜底**：文本类字段按关键词在段落里找句子；**字段字典自身的定义段落永不作为值来源**。
- **逐字闸门**：`quote` 必须是索引里某个段落或某条表格行渲染串的逐字切片；
  不通过就把该字段改为 `extraction_failed` 并撤回值，同时写 `errors`。
- 覆盖率 `coverage = reported / total`，四类状态分别计数，均在 `result.coverage` 里。

---

## 5. 输出契约

写入 `--output`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `result.json` | 契约回填 + 结构化结果（见下） |
| `fields.csv` | 逐字段表：`field_id,field_name,value,units,statistic,condition,comparator,source,quote,locator,status,claim_type,condition_complete,notes` |

`--work` 下另有 `corpus_index.json`（段落/表格/单元格/行/字典）与 `draft.json`（若提供）。

`result.json` 顶层键（键名冻结；case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层）：

- `case_id` / `status` / `summary`
- `output_contract`：逐键回填真实值，不写 `string`/`object` 类型占位符
- `result`：`{field_dictionary, fields[], coverage, corpus, scheme, method_notes}`
- `claims[]`（每个已判定字段一条，带 `evidence[]` 逐字引文 + locator）
  / `sources[]`（每条任务级 source 至少带一条逐字 quote + locator）
  / `uncertainties[]`（镜像 `uncertainty`）/ `change_records[]`（镜像 `changes`）
- `errors[]` / `degradations[]` / `pending_human[]` / `limits[]` / `counts` / `runtime`

**回填样例**（未给契约时回填标准五键）：

```json
{"case_id": "synth-rich-reading-06",
 "status": "partial",
 "output_contract": {
   "case_id": "synth-rich-reading-06",
   "status": "partial",
   "result": {"coverage": {"coverage": 0.375, "reported": 3, "total": 8}},
   "claims": [{"claim_id": "c01", "field_id": "elongation_t6", "status": "reported",
               "text": "elongation_t6 = 6.2 %",
               "evidence": [{"source_document_id": "P2",
                             "quote": "T6 aged | 318 | 6.2 | 95",
                             "locator": "P2#T1:r3"}]}],
   "uncertainties": [{"item": "not_reported", "detail": "aging_temperature: no value printed"}]}}
```

**status 诚实规则**（由产物推导，不靠自述）：

- `ok`：字段字典存在、全部字段 `reported`、无 `extraction_failed`；
- `partial`：有已落位字段，但存在未落位或冲突；
- `insufficient_evidence`：有材料文件但没有可用的字段字典；
- `input_error`：`--input` 不存在或没有任何材料文件。

---

## 6. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 无材料 | 缺口报告，`input_error` |
| 只有空文件 / 坏 JSON / 碎片笔记 | 无字段可判 | `insufficient_evidence` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 退回目录名并记 `degradations` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键（`case_id/status/result/claims/uncertainties`） |
| 引文不在索引 | 逐字闸门 | 撤回值 → `extraction_failed` + `errors` |
| `draft.json` 坏 JSON / 未知 field_id | 逐条丢弃 | 累计条数写进 `degradations`，不报错 |
| 输出目录不可写 | OSError | 回退 stderr，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] `fields.csv` 与 `result.fields[]` 逐行可对照，列数一致。
- [ ] 每个 `status == "reported"` 的字段都有非空 `quote` 与 `locator`，且引文在索引里逐字命中。
- [ ] `coverage` 四类状态之和等于字段总数；`not_reported` 每条都有搜索范围证据。
- [ ] 空输入 / 坏 JSON / 无字典三条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为成功。

---

## 8. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、落位口径、契约、降级、自查
scripts/extract.py             入口：prepare / run / finalize / selfcheck，索引与契约组装
scripts/checkkit.py            语料索引、字段落位、草稿合并、逐字闸门、CSV 渲染
references/extraction_rules.md 状态与 claim 规则、locator 方案、字段字典口径
references/expert_playbook.md  专家参考手册：口径、公式、陷阱、案例、§9 防扣分自查表
environment/resources.yaml     资源入口声明（命令、路径、预算、无网络、纯标准库）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`csv`/`json`/`re`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 3.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `extract.py --stage selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
