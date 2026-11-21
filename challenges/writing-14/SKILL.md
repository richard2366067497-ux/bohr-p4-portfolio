---
name: sci-mindmap-builder
description: >-
  把一批科研材料整理成一张可编辑、可核验的分层思维导图：单条命令即完成「发现材料 → 建索引 →
  归一化工作稿 → 逐字证据核验 → 结构校验 → 渲染 SVG/PNG → 来源映射 → 回填 result.json」。
  节点带材料 locator 与逐字 quote，跨分支关系只用语料支持的 9 类方向语义；随产物落盘五项可核验
  资产（金标准、对照报告、版本记录、自检、日志）。自带 agent-first 路径：Agent 在 init 之后编辑
  /app/work/mindmap.json，再 build 按同一口径成稿。材料为空或损坏时如实记 insufficient_evidence，
  仍 exit 0 并留下合法 result.json。
  Use for turning papers, notes and datasets into hierarchical mindmaps with traceable evidence,
  structural validation, editable SVG/JSON deliverables and reproducible self-check assets.
version: 2.0.0
---

# sci-mindmap-builder — 材料 → 可核验思维导图

把「一批材料」变成「一张带证据的导图」：中心主题、分支、要点、关系、来源映射与 `result.json` 一次落盘。
导图只描述材料里能逐字引到的东西；找不到原文支撑的节点与关系不会进入成稿。

安装根目录固定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，与当前目录无关。

---

## 0. 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、求解框架（读取建档→证据卡→问题与目标→
技术路线→计划核算→风险与成果→写作验证）、量化口径与公式（七要素覆盖率 / 论断溯源率 / 目标
对齐率 / 样本量 / RSD / 百分点与相对提升 / 人员负载与预算）、领域知识清单、交付物清单与专家
检查表、完整虚构案例、交付前门控。执行顺序固定为：先读手册 → 再按手册求解框架逐阶段落盘冻结
产物 → 交付前逐项勾选手册 §5 专家检查表。手册与 `SKILL.md` 冲突时，契约键名与入口命令以
`SKILL.md` 为准，方法与判分口径以手册为准。

---

## 1. 入口命令（第一条；评测入口，无 draft 时执行）

单命令即可跑完全流程并产出全部关键产物（评测只跑这一条也能通过）。**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 是 `init + check + build` 的合并形态。默认值：`--input /input`、`--output /app/output`、
`--work /app/work`。退出码恒为 0；先写 partial `result.json`，结束时无条件 finalize 覆盖。
全流程为确定性计算，秒级完成，无网络、无第三方包；`--no-probe` 可跳过空输入/坏输入子进程探针。

---

## 2. 这个包解决什么

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| 「把这篇材料摊成一张图」 | 按标题切分小节，形成中心主题 + 主分支 + 要点节点 |
| 「图上每一句凭什么？」 | 每个节点至少一条 evidence：`材料 + locator + 逐字 quote`，命中才算 verified |
| 「层级会不会乱？」 | `level` 由 `parent` 推出，深度 ≤ 4，父子链查环，同级标签去重 |
| 「关系能不能随便画？」 | 跨分支关系只允许 9 类方向语义，且必须有 quote；无证据的关系直接丢弃并记录 |
| 「数字是不是编的？」 | 节点里的数字必须能在材料或该节点 quote 中找到，逐条进数字台账 |
| 「换个人能不能复算？」 | 金标准、对照报告、版本记录、自检、日志五项资产随产物落盘，重跑复现同一计数 |

不适用范围：需要联网检索的素材、需要 OCR 的扫描件（图片材料只登记、不臆造内容）、主观创意配图。

---

## 3. agent-first 主路径

脚本负责机械判定与落盘，Agent 负责「图怎么长」。两者不可互相替代：

```
# 1) 建索引：抽单元、写工作稿骨架，先落一份 partial result.json
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# 2) Agent 读材料，亲手编辑 /app/work/mindmap.json（theme / nodes / edges）
python3 /skills/weekly-skill/scripts/main.py show  --input /input --work /app/work --material M1 --limit 20
# 3) 校验：结构、证据、关系、标签逐条体检
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
# 4) 成稿：渲染 SVG/PNG、写来源映射、finalize result.json
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

工作稿 `/app/work/mindmap.json` 约定（`build` 读取；缺失或全无效时回退到确定性抽取并记 `degradations`）：

```
{"theme": {"label": "材料主题", "material": "M1", "quote": "主题所在原文片段"},
 "nodes": [{"id": "n1", "label": "研究问题", "parent": "root", "role": "question",
            "status": "fact",
            "evidence": [{"material": "M1", "locator": "¶2", "quote": "原文连续片段"}]},
           {"id": "n2", "label": "样本规模 30 份", "parent": "n1", "role": "evidence",
            "status": "fact",
            "evidence": [{"material": "M1", "locator": "¶4", "quote": "共采集样本 30 份"}]}],
 "edges": [{"from": "n2", "to": "n3", "type": "support",
            "evidence": [{"material": "M1", "locator": "¶9", "quote": "支持结论的原文片段"}]}]}
```

---

## 4. 导图设计规则

以下规则逐条由 `check` 与 `self_check.json` 校验，也是金标准的来源句：

- **层级**：层级：root（中心主题）→ level 1 分支 → level 2 要点，深度 ≤ 4。
- **分支规模**：同一父节点下 2–5 个子节点，同级粒度对齐。
- **标签**：标签为名词短语，≤ 20 字，不带装饰语。
- **证据**：每个节点至少一条 evidence，quote 为材料原文连续片段。
- **关系**：跨分支关系只用 9 类方向语义，无 quote 支撑不画。
- **数字**：节点中的数字必须能在材料或该节点 quote 中找到。
- **契约**：原样回填 output_contract 的全部字段，不改名、不遗漏。
- **资产**：随产物落盘五项可核验资产：金标准、对照、版本、自检、日志。

中心主题取自材料主题，不写「思维导图 / mindmap」这类元词；一句话结论写进节点的 `summary`，
不塞进 `label`。**角色**（`role`）：`question` `method` `evidence` `finding` `conclusion`
`limitation` `gap` `task` `risk` `concept` `subtopic`。**状态**（`status`）：`fact`（原文直述）、
`summary`（材料内概括）、`inference`（你的推断，必须进 `pending_human`）。

**关系方向表**（`edges` 只写跨分支关系；层级用 `parent` 表达）：

| type | 方向语义 | 何时用 |
|-|-|-|
| `cause` | 因 → 果 | 材料明说 A 导致 B |
| `contrast` | A ↔ B 对照 | 两组条件或结论相反 |
| `support` | 证据 → 论断 | 某结果支撑某结论 |
| `conflict` | A ↔ B 冲突 | 两处材料结论不一致 |
| `sequence` | 先 → 后 | 步骤、时间线、阶段 |
| `depends` | 依赖 → 被依赖 | 方法依赖某数据或前序 |
| `cite` | 引用方 → 被引 | 明确引用关系 |
| `example` | 概念 → 例证 | 例子支撑概念 |
| `definition` | 术语 → 定义 | 概念界定 |

本表逐行即「方向语义」的权威定义：`build` 会把本表写进 `golden_standard.json` 的 `edge_semantics`，
评审可据此核对每条边的 from→to 是否符合语义（因→果、证据→论断、先→后…）。

---

## 5. 证据与定位规范

- `quote`：从材料**复制**的连续片段，≥ 6 字（建议 10–200），不改写、不拼接、不翻译；中文标点保持原样。
- 比对口径：NFKC 归一、空白折叠、去软连字符；仍不命中即 `verified:false`，节点进 `pending_human`。
- `locator`：文本/Markdown `¶12`（第 12 段）、PDF `p.3¶2`（第 3 页第 2 段）、DOCX `¶7`、
  CSV/TSV `row5`、JSON `json:/path/key`、图片 `figure1`（此类须在 `summary` 说明未 OCR）。
- 材料互相矛盾：两个节点都保留，用 `conflict` 关系相连，`uncertainty` 写明分歧位置。
- 材料缺失章节或数据：不补，写 `pending_human`；图片材料无文本时登记存在性并注明未 OCR。

---

## 6. 产物清单（全部落在 `--output`）

| 文件 | 内容 |
|-|-|
| `mindmap.svg` | 可编辑导图：每个节点 `g#node-*` 带 `data-quote` / `data-locator`，文字可改 |
| `mindmap.json` | 结构文件：主题、节点、边、模型来源与丢弃记录 |
| `content_map.json` | 来源映射：每个可定位单元被哪些节点引用、覆盖缺口 |
| `mindmap.png` | 预览图：标准库按坐标绘制的几何缩略（标签文字在 SVG/JSON） |
| `structure.md` | 结构摘要：主题、节点/分支/深度/关系计数与逐节点定位 |
| `golden_standard.json` | 金标准：规则句、材料、契约期望，每条带 `source` 回查 |
| `diff_report.md` | 实际产物对金标准的逐项对照（达标/偏差/缺失/待定） |
| `version_history.md` | v0 骨架 → v1 成稿的构建链与回退方法 |
| `run.log` | 运行日志（同时保留在 `--work`） |
| `self_check.json` | C1–C10 自检与空输入/坏 JSON 子进程探针 |
| `result.json` | 结构化结果 + 契约回填（见 §7） |

所有产物均为文本或标准库生成的位图，单文件远小于 30KB。

---

## 7. 结果契约与诚实规则

`result.json` 顶层键（键名冻结）：`case_id` / `status` / `summary` / `output_contract` /
`sources` / `uncertainties` / `change_records` / `limits` / `errors` / `degradations` / `runtime` /
`artifacts` / `checks` / `coverage` / `mindmap` / `structure` / `edges` / `diff_report` /
`golden_standard` / `version_history` / `self_check`。

`output_contract` 的每个键都**原样回填**（逐键保留键名，不合并、不改名），并把每个契约键浅拷贝到顶层：

```
{"output_contract": {
  "deliverable": {"summary": "16 节点 / 1 关系 / 深度 2 / 模型来源 work/mindmap.json",
                  "primary": "mindmap.svg", "structure": "mindmap.json", "preview": "mindmap.png"},
  "evidence_map": [{"node": "n2", "material": "M1", "locator": "¶4", "quote": "共采集样本 30 份",
                    "verified": true}],
  "preserved_facts": [{"fact": "30", "node": "n2", "material": "M1", "locator": "¶4",
                       "grounded": true}],
  "change_log": [{"action": "build", "detail": "节点 16 个，关系 1 条，模型来源 work/mindmap.json"}],
  "content_map": {"coverage": {"units": 16, "mapped": 16, "unmapped": []},
                  "node_count": 16, "edge_count": 1}}}
```

- `case.json` 未给契约时，回填上面 5 个标准键（与本节示例一致）；
- `case_id` 从 `case.json` 的 `case_id` / `id` / `challenge_id` 取，都没有时用输入目录名；
- 契约值为路径时给出真实存在的产物路径；数组项逐条带 `material` 与 `locator`，可回查；
- 任何键不得为空串或类型占位符；确实缺内容时给出可判读的说明对象。

---

## 8. 异常与降级（每次都 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| 输入目录为空 / 只有空文件 | `discover` 无可解析单元 | `insufficient_evidence`，`degradations` 写缺口 |
| 材料是坏 JSON / 坏二进制 | 解析异常，按字节指纹记录 | 该材料只登记、不造内容，`degradations` 记录 |
| 材料只有标记行（如待写占位） | 单元长度与标记正则 | 跳过该文件并记 `degradations` |
| `case.json` 缺失或损坏 | 解析失败 | 继续用默认契约构建，`case_id` 用目录名 |
| 工作稿缺失或全无效 | 节点为空 / 全部 quote 未命中 | 回退确定性抽取成稿，记 `degradations` |
| quote 命中失败 | 归一比对不通过 | 节点标 `unverified` 并进 `pending_human`，`status=partial` |
| 节点规模失控 | 节点 > 40 或关系 > 6 | 保留但告警，`degradations` 建议合并同级 |
| 输出目录不可写 | `OSError` | stderr 打印，退出码仍 0 |
| 主流程异常 | 兜底写最小合法 `result.json` | `status=input_error` |

`status` 由产物推导：材料有可用文本、节点存在、校验无 error、证据全部命中且规模合理记 `ok`；
有节点但未全部达标记 `partial`；材料无可用文本或无节点记 `insufficient_evidence`。自检失败只降级，
不伪造通过。

---

## 9. 交付前自查

- [ ] **`references/expert_playbook.md` §5 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，`case_id` 在，`output_contract` 逐键回填且无占位符。
- [ ] `mindmap.svg` 节点数与 `mindmap.json` 一致，每个 `g#node-*` 带 `data-quote` / `data-locator`。
- [ ] 每个节点至少一条 evidence，命中率 100%；数字台账全部 grounded。
- [ ] 深度 ≤ 4，每个主分支下 ≥ 2 个子节点，同级标签不重复。
- [ ] 跨分支关系 ≤ 6 条且类型在本包 9 类之内，每条都有 quote。
- [ ] `diff_report.md` 的缺失项清零；`self_check.json.summary.pass` 为 `true`。
- [ ] 空输入与坏 JSON 各跑过：exit 0、`result.json` 合法、`status` 合理。
- [ ] 重复运行产物字节一致（仅 `run.log` 与 `self_check.json` 的 `generated` 因时间戳变化）。

## 10. 文件清单

```
SKILL.md                    本文件：入口、agent-first、规则、契约、降级、自查
scripts/main.py             入口：init / show / check / build / run，产物编排与 result.json
scripts/verify.py           确定性内核：发现、单元抽取、工作稿归一化、证据核验、结构校验、契约回填
scripts/render.py           渲染与资产层：布局、SVG/PNG、来源映射、金标准、对照、版本、自检
references/expert_playbook.md  专家方法论：判分要点、公式、检查表、虚构案例
README.md                   安装、最小示例、限制与维护
SELFTEST.md                 自测记录：空/坏输入与 rich/boundary × single/agent 结果
GITHUB_URL.txt              仓库位置
environment/resources.yaml  资源入口声明（命令、预算、离线、纯标准库）
```

依赖：Python 3.9+ 标准库；`pdftotext` 存在则优先用于 PDF 取文（缺失即用内置解流兜底）。
