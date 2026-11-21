---
name: academic-writing-benchmark-builder
description: >-
  从一批科研材料构建可判分的学术写作 benchmark 包：单条命令即完成「发现材料 → 抽取可核对事实 →
  设计 1–4 道写作题（每题六字段）→ 生成抽取式参考答案 → 写出 0/1/2 档可观察锚点 → 双评分员独立
  打分并给出 Cohen's kappa → 正控/负控校准 → 逐题评测报告与复现记录 → 回填 result.json」。
  自带 agent-first 路径（Agent 在 init 之后写 answers.json，再 build 按同一口径评分）；
  材料为空或损坏时如实记 insufficient_evidence，仍 exit 0 并留下合法 result.json。
  Use for building writing-task sets, reference answers, observable rubrics, inter-rater
  agreement checks, calibration controls, and reproducible evaluation reports from papers.
version: 2.0.0
---

# academic-writing-benchmark-builder — 写作题金标准与双评一致性

本 Skill 把「一批材料」变成「一套可判分的写作题」：题面、要点、锚点、分数、报告、复现记录一次落盘。
判分只依赖材料原文，不依赖内置范文；任何无法从材料核实的要点都不会进入题面。

安装根目录固定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，与当前目录无关。

---

## 0. 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、求解框架（七要素对齐）、量化口径与公式
（要素覆盖率 / 事实支持率 / 定位有效率 / 计划链覆盖率 / 状态准确率 / 数值复算）、领域知识清单、
交付物清单与专家检查表、完整虚构案例、交付前门控。执行顺序固定为：先读手册 → 再按手册求解框架
逐阶段落盘冻结产物 → 交付前逐项勾选手册 §5 专家检查表。手册与 `SKILL.md` 冲突时，契约键名与
入口命令以 `SKILL.md` 为准，方法与判分口径以手册为准。

---

## 1. 入口命令（第一条）

单命令即可跑完全流程并产出全部关键产物（评测只跑这一条也能通过）：

```
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 是 `init + check + build` 的合并形态。默认值：`--input /input`、`--output /app/output`、
`--work /app/work`。退出码恒为 0；先写 partial `result.json`，结束时无条件 finalize 覆盖。
全流程为确定性计算，秒级完成，无网络、无第三方包。

README.md 里给出最小可运行示例：包内 `environment/resources.yaml` 约定的 `/input` 布局与一次真实调用结果。

---

## 2. 这个包解决什么

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| 「把这篇论文变成写作练习题」 | 按材料小节切分，生成 1–4 道 methods/results/discussion/citation/abstract 风格题 |
| 「答案怎么算对？」 | 每题 4 个必需要点，逐字取自材料，带 `材料 + ¶定位` |
| 「评分标准能不能复算？」 | 每题 5 条可观察锚点（含数值保留、不新增数值、字数、小节顺序），0/1/2 档 |
| 「两个评分员分歧怎么办？」 | rater_a（严格归一化包含）与 rater_b（词袋覆盖）独立计分，记录 delta 与 Cohen's kappa |
| 「标准会不会太松？」 | 正控（参考答案）必须通过、负控（删数字并截断）必须被拒绝，否则记 partial |
| 「换个人能不能复现？」 | `reproducibility.md` 记录输入 sha1、命令、版本与逐题复算步骤 |

不适用范围：需要联网检索的评测、主观创意写作（无可核对事实时本包不造题）。

---

## 3. agent-first 主路径

脚本负责机械判定与落盘，Agent 负责「写什么」。两者不可互相替代：

```
# 1) 建索引：抽事实、出题、写锚点与参考答案，先落一份 partial result.json
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# 2) Agent 读 /app/output/tasks.jsonl 与 /app/output/reference_answers/，把作答写入 /app/work/answers.json
# 3) 校验：题面字段、要点定位、锚点阶梯逐条体检
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
# 4) 成稿：按同一口径评分（Agent 作答优先，否则用抽取式参考答案）并 finalize result.json
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

`answers.json` 约定（可选；缺省或坏 JSON 一律回退到抽取式参考答案，不报错）：

```
{"answers": [{"task_id": "T01", "text": "Agent 按题面写出的段落，数值与术语保持原文。"}]}
```

同时兼容 `/app/work/draft.json` 的 `answers` / `items` / `responses` 字段；`init` 后的任何时刻写入都生效。

---

## 4. 任务集：每题六个必填字段

题面字段不是装饰，缺一项该题即不可判分。以下规则逐条由 `check` 与 `self_check.json` 校验：

- 题面必须指明使用的材料（`input_material`：材料名 + 小节 + 段号）。
- 题面必须给出可执行指令（`instruction`：一句话说明要写的体裁与约束）。
- 题面必须给出字数或引用要求（`word_limit`：正文词数上限，中文按字数）。
- 题面必须列出必需要点（`must_include_points`：4 条，逐条带 `quote` 与 `locator`）。
- 题面必须声明可接受变体（`acceptable_variants`：改写、合并句子、调整语序仍接受的条件）。
- 题面必须给出完成判定（`completion_criteria`：全部要点命中 + 锚点无失败 + 字数达标）。

题型按材料小节确定：`method` → methods 题，`result` → results 题，`discussion` / `conclusion` →
discussion 题，`reference` → citation 题，`abstract` / `introduction` → abstract 题。
材料不足 4 个要点时拆题或降为 1 题；完全没有可解析正文时不造题（见 §8）。

---

## 5. 锚点、双评与校准

每题至少 5 条可观察锚点，覆盖 0/1/2 档（`anchor_ladder` 固定三档）：

| 锚点 | 规则类型 | 可观察现象 |
|-|-|-|
| A1 | `contains_all` | 必需要点的原文片段全部出现（归一化后按子串判断） |
| A2 | `number_preserved` | 要点涉及的每个数值原样出现（`750`、`99.1`、`1.2` 等） |
| A3 | `no_new_numbers` | 答案中不出现材料之外的数值 |
| A4 | `word_limit` | 正文词数不超过题面上限 |
| A5 | `section_order` | 必需要点按材料中出现的先后顺序出现 |

评分口径：

- 两名评分员独立打分并记录 delta：rater_a 用严格归一化包含，rater_b 用词袋覆盖率；
- 记录 Cohen's kappa 与分歧项：kappa 写入 `scores.csv` 同目录的 `consistency`，分歧项进 `change_log`；
- 正控必须通过、负控必须被拒绝：正控取抽取式参考答案，负控由删数字并截断 16 词得到；
- delta 大于 1 只登记锚点复查项，分数保持原样，第三方可复算。

`status` 由产物推导：全部题 accepted 且校准通过记 `ok`；有题但未全部通过记 `partial`；
材料无可用正文记 `insufficient_evidence`。自检失败只降级不伪造通过。

---

## 6. 产物清单（全部落在 `--output`）

| 文件 | 内容 |
|-|-|
| `deliverable.md` | 交付清单：题量、方向覆盖、产物字节与用途 |
| `tasks.jsonl` | 每行一道题，六字段齐全 |
| `reference_answers/T01.md` … | 抽取式参考答案 + 要点来源定位 |
| `anchors.md` | 每题 5 条锚点 + 0/1/2 档阶梯 |
| `scores.csv` | 双评分数、delta、覆盖率和结论 |
| `scores_detail.csv` | 锚点逐条判定（applicable / pass / observed） |
| `evaluation_report.md` | 逐题分数、证据、失败类型、校准对照与改进建议 |
| `reproducibility.md` | 输入 sha1、命令、版本、复算步骤与结果清单 |
| `golden_standard.json` | 结构要求与契约期望，每条带 `source` 回查 |
| `diff_report.md` | 实际产物对金标准的逐项对照 |
| `version_history.md` | 构建链版本记录与回退方法 |
| `run.log` | 运行日志（同时保留在 `--work`） |
| `self_check.json` | C1–C10 自检与空输入/坏 JSON 探针 |
| `result.json` | 结构化结果 + 契约回填（见 §7） |

大文件风险已规避：所有产物均为文本（md/jsonl/csv/json），单文件远小于 30KB。

---

## 7. 结果契约与诚实规则

`result.json` 顶层键（键名冻结）：`case_id` / `status` / `summary` / `output_contract` /
`sources` / `uncertainties` / `change_records` / `limits` / `errors` / `degradations` / `runtime` /
`artifacts` / `checks` / `coverage` / `tasks` / `anchors` / `scores` / `controls` / `consistency` /
`diff_report` / `golden_standard` / `version_history` / `self_check`。

`output_contract` 的每个键都**原样回填**（逐键保留键名，不合并、不改名），并且把每个契约键浅拷贝到顶层：

```
{"output_contract": {
  "case_id": "案例 id，原样透传",
  "deliverable": {"summary": "3 道题 / 12 条要点 / 双评 kappa=1.0", "primary": "deliverable.md"},
  "preserved_facts": [{"fact": "99.1", "material": "M1", "locator": "¶5", "verified": true}],
  "evidence_map": [{"task_id": "T02", "point_id": "P1", "material": "M1", "locator": "¶5"}],
  "change_log": [{"action": "build", "detail": "题 3 道，双评 3 组，答案来源=auto_extract"}]}}
```

- `case.json` 未给契约时，回填上面 5 个标准键（与本节示例一致）；
- `case_id` 从 `case.json` 的 `case_id` / `id` / `challenge_id` 取，都没有时用输入目录名；
- 契约值为路径时给出真实存在的产物路径；数组项逐条带 `material` 与 `locator`，可回查；
- 任何键不得为 `null` / 空串 / 类型占位符。

---

## 8. 异常与降级（每次都 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| 输入目录为空 / 只有空文件 | `discover` 无可解析单元 | `insufficient_evidence`，`degradations` 写缺口 |
| 材料是坏 JSON / 坏二进制 | 解析异常，按字节指纹记录 | `insufficient_evidence` 或跳过该文件并记 `errors` |
| 材料只有标记行（如待写占位） | 单元长度与标记正则 | 跳过该文件并记 `notes` |
| `case.json` 缺失或损坏 | 解析失败 | 继续用默认契约构建，`case_id` 用目录名 |
| 只剩 1–2 个可用要点 | 要点不足 4 条 | 拆题或降题量，`status=partial` |
| 输出目录不可写 | `OSError` | stderr 打印，退出码仍 0 |
| 主流程异常 | 兜底 `crash_safe` | `status=input_error` + 最小合法 `result.json` |

---

## 9. 交付前自查

- [ ] **`references/expert_playbook.md` §5 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，`case_id` 在，`output_contract` 逐键回填且无占位符。
- [ ] `tasks.jsonl` 每题六字段齐全，要点带 `locator` 与逐字 `quote`。
- [ ] `anchors.md` 每题 ≥5 条锚点且覆盖 0/1/2 档。
- [ ] `scores.csv` 有双评与 delta；`self_check.json` 的 C4（双评）与 C6（校准）通过。
- [ ] 空输入与坏 JSON 各跑过：exit 0、`result.json` 合法、`status=insufficient_evidence`。
- [ ] `reproducibility.md` 的输入 sha1 与本次输入一致；重复运行产物字节一致。

## 10. 文件清单

```
SKILL.md                    本文件：入口、agent-first、六字段、锚点、契约、降级、自查
scripts/main.py             入口：init / check / build / run，产物编排与 result.json
scripts/verify.py           确定性内核：发现、事实抽取、出题、锚点、双评、kappa、契约回填
scripts/render.py           渲染层：题面/锚点/报告/复现/金标准/对照/版本
references/expert_playbook.md  专家方法论：判分要点、公式、检查表、虚构案例
README.md                   安装、最小示例、限制与维护
SELFTEST.md                 自测记录：空/坏输入与 rich/boundary × single/agent 结果
GITHUB_URL.txt              仓库位置
environment/resources.yaml  资源入口声明（命令、预算、离线、纯标准库）
```

依赖：Python 3.9+ 标准库；无网络、无第三方包、无外部服务。
