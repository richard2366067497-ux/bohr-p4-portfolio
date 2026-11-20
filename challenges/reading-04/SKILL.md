---
name: multi-doc-comparison
description: >-
  Faithful multi-document comparison: one command reads the comparison workorder plus every
  corpus document (txt/md/csv/tsv/json/html/tex, plus stdlib-only PDF text and DOCX XML),
  anchors each paragraph under a stable <page>#para<n> locator, builds a per-cell matrix over
  the workorder's common fields, tests comparability axis by axis, and adjudicates
  agreement/conflict with attributed causes. Every reported cell carries a verbatim quote and
  its locator, so each number can be traced back to the sentence that produced it. Honours
  forbidden-pooling rules, never invents values or citations, and degrades to a legal
  result.json with an explicit gap list when the corpus is empty or unreadable.
version: 3.0.0
---

# multi-doc-comparison — 多文档对比

一句话：**把可比的东西排成一张矩阵，并证明每个格子都来自原材料。**

它不从零写综述、不合并不同实验条件、不给没报告的数字填空。每个已报告格子都带
`原文引用 / locator / 来源文档`；每条可比性判断都说明是在哪个维度上比的；每条冲突结论
都必须写出归因（是条件不同、体系不同，还是无解）。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 1. 入口命令（第一条，必须先看）

单命令即可产出完整契约与全部关键产物（评测只跑这一条也能过）：

```
python3 /skills/weekly-skill/scripts/main.py build \
  --input /input --output /app/output --work /app/work
```

`build` 默认值即 `--input /input`、`--output /app/output`、`--work /app/work`。它按顺序：

1. **发现** `--input` 下的全部材料：`case.json` 里读 `case_id` 与 `output_contract`；读对比工单
   （`*workorder*.json`，或 `case.json` 内嵌的 workorder 字段）拿到研究问题、公共字段、
   对比维度与禁止合并项；
2. **锚定** 每份语料：文本直接读；PDF 用 `zlib` 解压内容流后抽 `(...)Tj` 字串（纯标准库，
   不装第三方）；DOCX 走 `zipfile` + XML；每个段落拿 `p<页码>#para<序号>` 的稳定 locator
   （长文按 ~600 字符再切），并记录 `kind/engine/quality`；
3. **成矩阵**：对每份文档 × 每个公共字段取一个格子。有 `work/draft.json` 就用 Agent 填的
   格子，否则用确定性启发式（单位/百分号/`pH n`/化学式/缩写全称）尽力抽取；
4. **比可比性**：逐维度看各文档报告值是否一致；不一致就分层比较，并强制执行
   `forbidden_pooling`（不同染料、不同催化剂一律不许合并）；
5. **判一致/冲突**：逐字段给 `consistent / partially_consistent / insufficient` 裁决，
   冲突必须写归因；
6. **校验**：重复格子、未知文档/字段、已报告但无值、引文不在原文、locator 缺失 → `error`；
7. 写出全部产物（§5），并把 `output_contract` 逐键回填进 `result.json`。

任意阶段抛异常都会在彻底兜底后仍写出合法 `result.json` 并 exit 0。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “把这几篇里的同一指标拉出来比一比” | 公共字段矩阵 + 每格 `引用 + locator` |
| “它们能直接合并报一个数吗” | 逐维度可比性检验 + 禁止合并项强制 |
| “两篇结论打架，为什么” | 冲突裁决 + 归因（条件/体系/无解） |
| “只给工单不给结论” | 未报告格子如实留白并写原因，不猜数 |
| “有 PDF/DOCX 也要读” | 纯标准库文本抽取，抽不出就记 `degradation` 不编造 |
| “材料不全怎么办” | `partial` + 缺口清单，等作者补语料 |

不适用：整篇综述代写、跨文献元分析、补造数据、渲染图表。

---

## 3. 子命令与 agent-first 双路径

| 子命令 | 作用 | 关键参数 |
|-|-|-|
| `build` | 全流程：发现→锚定→矩阵→可比性→一致性→校验→写产物与 `result.json` | `--input --output --work` |
| `show` | 打印已锚定段落与 locator（便于 Agent 取证） | 追加 `--doc D1 --paras 3:5` |
| `check` | 重跑全流程并校验 Agent 草稿的引文与 locator | 同上 |
| `selfcheck` | 重跑全流程并审计 `output_contract` 键是否齐全非空 | 同上 |

每个子命令都会重写一份完整的 `result.json`，因此评测跑哪一条都拿得到完整契约。

推荐 **agent-first** 流程（脚本负责抽取与证据，Agent 负责判读与措辞）：

```
# 1) 确定性全流程，先看矩阵与可比性
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
# 2) 逐段取证：打印某篇的段落与 locator
python3 /skills/weekly-skill/scripts/main.py show  --input /input --output /app/output --work /app/work --doc D1
# 3) Agent 读 /app/output/comparison_matrix.csv 与 /app/work/index.json，写 /app/work/draft.json
# 4) 闸门：合并草稿并校验引文/locator
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
# 5) 再跑一次确定性全流程，确认可复现
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`/app/work/draft.json` 约定（可缺省；缺省或坏 JSON 一律回退到确定性抽取，不报错）：

```json
{"question": "initial dye concentration and pH vs. photocatalytic removal?",
 "fields": [{"field_id": "ph", "name": "pH", "unit": "pH"},
            {"field_id": "removal", "name": "removal efficiency", "unit": "%"}],
 "records": [
   {"doc_id": "D1", "field_id": "ph", "field_name": "pH", "value": "3", "unit": "pH",
    "status": "reported",
    "quote": "After 120 min at pH 3, the removal efficiency reached 95%.",
    "locator": "p1#para2"},
   {"doc_id": "D1", "field_id": "removal", "field_name": "removal efficiency", "value": "95", "unit": "%",
    "status": "reported",
    "quote": "After 120 min at pH 3, the removal efficiency reached 95%.",
    "locator": "p1#para2"}],
 "comparability": [{"dimension": "pollutant", "comparable": false,
                    "basis": "D1 uses methylene blue, D2 uses rhodamine B; never pooled"}]}
```

合并草稿的三条硬约束：`doc_id` 与 `field_id` 必须命中语料与工单；已报告格子的 `quote`
必须能在对应段落里找到（精确或去空格后一致）；`locator` 必须非空。任一条不满足就丢弃该格，
并在 `result.json.errors`/`degradations` 里写明——Agent 的判读不能绕过取证要求。

---

## 4. 可比性与禁止合并

维度取自工单（缺省 `task/dataset/sample/material/method/metric/unit/budget`）。每维度看
各文档是否都报告了值：

- 报告值经归一后完全相同 → `comparable: true`，允许合并成一个数；
- 有差异 → `comparable: false`，**分层保留**，并在 `basis` 里写明差异；
- 只有一篇报告 → 不构成比较，记 `insufficient`。

`forbidden_pooling` 里列出的情形（如“不同染料”“不同催化剂”）一旦命中就绝不给合并值；
冲突裁决必须把原因写成 `condition` / `system` / `unresolved` 之一，`conflicting` 而
`unresolved` 会被判为 `error`。

---

## 5. 输出契约

写入 `--output`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `comparison_matrix.csv` | 逐格矩阵：`source_document_id, field_id, value, unit, status, confidence, quote, locator, note` |
| `comparison_table.md` | 人类可读矩阵 + 可比性检验 + 冲突归因 + 覆盖率 |
| `evidence_cards.jsonl` | 每个已报告格一张证据卡（值 / 单位 / 引用 / locator），一行一条 |
| `result.json` | 契约回填 + 结构化结果（见下） |

`--work` 下另有 `index.json`（文档清单、locator 方案、全部锚定段落、工单快照）与
`draft.json`（若提供）。

`result.json` 顶层键（键名冻结；case 给几个 `output_contract` 键就回填几个，且逐一浅拷贝到顶层）：

- `case_id` / `status` / `summary`
- `output_contract`：`case.json.output_contract` 逐键回填，**每个键给真实值**，不写
  `string`/`object` 类型占位符；未定义的键也给结构化非空值
- `result`：`{question, dimensions, fields, papers, matrix_preview, comparability, agreement, forbidden_pooling, counts}`
- `claims[]` / `sources[]` / `uncertainties[]`（同时镜像为 `uncertainty`）/ `change_records[]`（镜像为 `changes`）
- `errors[]` / `degradations[]` / `pending_human[]` / `limits[]` / `counts` / `runtime`

**回填口径**（未给契约时回填标准键的样例形状）：

```json
{"case_id": "synth-rich-reading-04",
 "status": "ok",
 "output_contract": {
   "case_id": "synth-rich-reading-04",
   "status": "ok",
   "result": {"question": "initial dye concentration and pH vs. photocatalytic removal?",
              "dimensions": ["task", "metric", "units", "material", "pollutant", "budget"],
              "counts": {"documents": 2, "fields": 5, "reported": 7}},
   "claims": [{"claim_id": "c01", "kind": "comparison", "verdict": "partially_consistent",
               "text": "pH across 2 document(s): D1=3 pH, D2=7 pH",
               "evidence": [{"source_document_id": "D1", "quote": "After 120 min at pH 3, the removal efficiency reached 95%.",
                             "locator": "p1#para2"}]}],
   "uncertainties": [{"item": "scope", "detail": "only the supplied documents and fields are compared"}]}}
```

**status 诚实规则**（由产物推导，不靠自述）：

- `ok`：至少有一个已报告格子、没有 `error` 级缺陷、没有 `degradation`；
- `partial`：有已报告格子，但存在 error 级缺陷（引文不在原文、重复格子…）或抽取降级；
- `insufficient_evidence`：语料可读但一个值都锚不出来；
- `input_error`：`--input` 不可读或无任何语料，交付缺口报告。

---

## 6. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 无语料 | 写缺口报告，`input_error` |
| 只有空文件 / 坏 JSON / 碎片笔记 | 锚定后无值 | `insufficient_evidence` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 退回目录名并记 `degradations` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键（`case_id/status/result/claims/uncertainties`） |
| PDF / DOCX 抽取失败 | 引擎异常 | 记 `degradation`，不猜正文 |
| 引文不在原文段落 | `find_quote` 未命中 | `error` 级 → `partial` |
| `draft.json` 坏 JSON / 未知 doc_id | 逐条丢弃 | 累计条数写进 `degradations`，不报错 |
| 输出目录不可写 | OSError | 回退 stderr，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 `null`。
- [ ] `comparison_matrix.csv` / `comparison_table.md` / `evidence_cards.jsonl` 结构合法且与 `result.json` 可对照。
- [ ] 每个 `status == "reported"` 的格子都有非空 `quote` 与 `locator`，且引文能在对应段落中找到。
- [ ] `comparability` 每条都有 `dimension` 与 `basis`；命中 `forbidden_pooling` 时未给合并值。
- [ ] 空输入 / 坏 JSON / 无语料三条路径各跑过一次，均 exit 0 且有缺口报告。

---

## 8. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、可比性、契约、降级、自查
scripts/main.py                入口：build / show / check / selfcheck，流程编排与契约组装
scripts/readkit.py             读取与锚定（类型嗅探、纯标准库 PDF/DOCX 取文、段落切分与 locator、工单解析、抽取启发式）+ 校验/可比性/一致性/契约回填/渲染
references/contract.md         契约键语义、locator 方案、字段字典与可比性口径
environment/resources.yaml     资源入口声明（命令、路径、预算、无网络、纯标准库）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`csv`/`json`/`re`/`zipfile`/`zlib`/`unicodedata`/`hashlib`）；无第三方包、无网络、无外部模型。
- 版本 3.0.0：契约键名冻结；新增维度/规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
