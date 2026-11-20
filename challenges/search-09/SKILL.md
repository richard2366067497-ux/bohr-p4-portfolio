---
name: search-09-appraisal
description: 量表驱动的文献质量评价 Skill：读 /input 的材料（PDF/TXT/MD/HTML/JSON/CSV），现场产出「维度—判断—证据—等级」评价表、可逐字核对的锚点表、可复算的偏倚分级，以及候选筛选与缺口/弃权登记。确定性规则为主（无模型调用），Agent 工作稿仅作可选增强。适用于文献检索筛选、研究设计与报告质量评价、偏倚风险分级、证据定位（locator+逐字 quote）等需要第二个人逐条复核的任务；也适用于中文/英文混合材料。不联网、不补造文献、不做事实核验。
version: 2.0.0
---

# search-09-appraisal — 证据定位的文献质量评价

## 1. 一条命令即可完成

```bash
python3 scripts/main.py          # 无参数 = 全流程
```

一次调用依次完成：**建索引 → 确定性推导 → 自动生成工作稿 → 渲染全部产物 → 写最终 result.json**，
退出码恒为 0。无需先读材料、无需写任何中间文件，也无需联网或第三方包。

- 输入默认 `/input`，产物默认 `/app/output`，工作区默认 `/app/work`（Harbor 契约）；
  若 `/input` 不存在则退回当前目录下的 `input/`、`output/`、`work/`。
- 需要显式路径时：`python3 scripts/main.py --input /input --output /app/output --work /app/work`。
- 分步调试（等价、可选）：`init`（只建索引 + 合法 partial result.json）、`show`（列材料/文献/量表）、
  `check`（机械校验并写 `work/check_report.json`）、`build`（同无参）。

## 2. 确定性推导规则（可复算）

| 步骤 | 规则 | 落点 |
|---|---|---|
| 索引 | 按相对路径排序分配 `doc_id=F01..`；文本按空行/标题切块，locator=`F##/#pN`；PDF 走 zlib 文本层并按 `/Type /Page` 顺序给 `page` | `sources[]`、`anchor_table.locator` |
| 题录 | JSON 递归识别含 title + (doi/year/type/author/abstract) 的对象为记录；记录挂接同标题全文（标题词重合 ≥0.6） | `candidates[]` |
| 类型 | 标题+前 6 块按 `TYPE_RULES` 首个命中：sysrev / rct / diagnostic / case_control / cross_sectional / cohort / preclinical / materials / modelling / qualitative / case_report，全不命中=`unknown`；命中句同时作为类型证据 | `paper_type`、`candidates[].type_anchor` |
| 量表 | 优先用 case.json/task.md 声明的维度（键 `rubric/dimensions/checkpoints/criteria/appraisal_scheme`，或文本行 `- 维度：…`）追加为 `DECL#` 检查点；其余走内置 5 维量表：研究设计 / 样本与抽样 / 测量与结局 / 统计与报告完整性 / 偏倚风险（18 个通用检查点 + 每种类型 2–3 个附加检查点） | `rubric_used`、`appraisal[]` |
| 取证 | 每个检查点有专属关键词族；在同族命中的块中按「优先章节 → 命中次数 → locator 字典序」取前 2 块，quote 取命中位置所在的整句（原文切片，故必然逐字可检出） | `anchor_table` |
| 判定 | `R_J1_ABSTAIN` 无命中 → `not_assessable`；`R_J2_NEG` 命中反向词族（未随机/未设盲/未做样本量）→ `not_met`+`major`；`R_J3_MET` ≥2 条锚点或 1 条含数字 → `met`（风险取检查点下限）；`R_J4_WEAK` 仅 1 条弱锚点 → `partial`+`some` | `appraisal[].judgment/risk/rule_id/rationale` |
| 分级 | 维度取最严重者（major>some>low）；`DESIGN` 受文献类型上限约束（rct/sysrev=low，观察性=some，qualitative/case_report=major）；总体：弃权 ≥50%→`insufficient_evidence`，DESIGN/SAMPLE/BIAS 有 major→`high_risk`，some 维度 ≥2→`some_concerns`，否则 `low_risk` | `grading.json`、`grading.*.trace` |
| 筛选排序 | `score=0.40·topic+0.25·title+0.20·design+0.15·depth`（分项 0–2）；`depth=0`→exclude，`≥0.55`→include，`<0.30`→exclude，其余 unclear；排序 score 降序 → 年份降序 → candidate_id 升序 | `candidate_pool.csv`、`candidates[].rank` |
| 隔离 | 文件名含 fixture/synthetic/duplicate/conflict 的文档只登记为 fixture，**不作任何判断的证据** | `fixtures[]` |

完整的检查点表、关键词族、反向词族与阈值阈值表在 `references/appraisal_rules.md`（机器可读的
```rules``` 块，engine 启动时解析；改量表只改该块）。

**两条硬约束**：① 每条非弃权判断都必须有 `source_id + locator + 逐字 quote`，脚本对 quote 做
包含校验，失败则该锚点作废、该判断降为 `not_assessable`；② 找不到证据就弃权并登记缺什么、
检索过哪些章节与关键词族，**不补一个"看起来合理"的判断**。

## 3. Agent 可选增强（不是前置条件）

确定性推导已覆盖全流程。若 Agent 读过原文、想覆盖个别结论，把工作稿写到 `/app/work/draft.json`
（或 `plan.json`）再跑同一条命令即可：

```json
{"schema": "search09-draft/1",
 "papers": [{"paper_id": "P01", "paper_type": "rct",
   "checkpoints": [{"checkpoint_id": "D1", "judgment": "partial", "risk": "some",
                    "anchors": [{"locator": "F01#p12", "quote": "逐字原文片段"}],
                    "rationale": "分配隐藏只在附录提到，正文未写"}]}],
 "candidates": [{"candidate_id": "P01", "decision": "include", "reason_codes": ["I_TOPIC"]}],
 "gaps": [{"kind": "access_error", "subject": "F03", "detail": "扫描件无文本层", "action": "OCR 后重跑"}]}
```

合并语义（`R_AGENT_DRAFT`）：draft 锚点必须先通过逐字校验，通过才覆盖该检查点的
`judgment/risk/rationale/evidence`；未通过只记一条 `review_log` 并保留确定性结论。draft 缺项、
格式错误、路径不存在都不影响产出——`status` 不会因为"没有 draft"而降级。

## 4. 输入 / 输出契约

输入：`/input/case.json`（`case_id`、`task_instruction`、`output_contract`，可缺）、`/input/task.md`、
`/input/**` 材料（PDF/TXT/MD/HTML/JSON/CSV/TSV）。材料按语义识别，不假设固定文件名。

产物（`/app/output/`）：

| 文件 | 内容 |
|---|---|
| `result.json` | `output_contract` 全键原样回填 + `case_id/status/summary/research_question/paper_type/candidates/appraisal/anchor_table/robs/grading/rubric_used/review_log/fixtures/gaps/counts/sources/uncertainties/method_notes/assumptions/degradations/errors/artifacts/runtime` |
| `appraisal.jsonl` | 一行一检查点：`paper_id/dimension/checkpoint_id/judgment/risk/rule_id/rationale/anchor_ids/evidence{locator,quote,match}/evidence_scope/confidence`（弃权另带 `abstain_reason/searched_scope`） |
| `anchor_table.csv` | `anchor_id,paper_id,checkpoint_id,dimension,doc_id,locator,section,page,quote,match,score,used_for` |
| `candidate_pool.csv` | 候选元数据 + 分项相关度 + score + rank + decision + reason_codes |
| `grading.json` | 逐篇维度等级、总体等级、依据、`trace` 计算过程与阈值 |

`status` 判定：材料不可读→`input_error`；有材料且产出 ≥1 条非弃权判断→`answered`；
其余（含弃权较多、单文件解析失败、坏 JSON 被跳过）→`partial`。`case_id` 缺失记 `null`，不编造。

## 5. 状态、失败与降级

| 情况 | 行为 |
|---|---|
| `case.json` 缺失/坏 JSON | 继续跑：`case_id=null`，契约键为空，`errors` + `degradations` 记录，仍产出全套产物 |
| 无材料/空目录 | `status=input_error`，`appraisal.jsonl` 写一条 `not_assessable` 说明行，`gaps: empty_result`，退出 0 |
| PDF 无文本层/加密/仅题录 | 该文件记 `access_error`，相关检查点弃权（`not_parsable`），不据此推断"原文未报告" |
| 单文件解析失败 | 记 `degradations`，其余材料照常 |
| 规则块缺失/不可解析 | 退到内置最小量表（5 维 × 2 检查点）并记 `rules_fallback`，不会静默产出 0 条判断 |
| draft 锚点不可核验 | 该检查点保留确定性结论，`review_log` 记一条 |
| 任何未捕获异常 | 打印原因、写合法 partial `result.json` 与全部产物，退出码仍为 0 |

**方法边界（须在解读时保留）**：本 Skill 是确定性规则评价，不是同行评审，不判断论文数据真伪；
覆盖范围仅限 `/input` 实际材料，不声称查全率或"最新发表"；`evidence_scope=abstract` 的结论弱于
全文；关键词族可能漏掉改写表述，弃权条目正是供人工补检的位置。

## 6. 自查（交付前逐条核对）

1. `python3 scripts/main.py`（无参数）退出码 0，`/app/output/result.json` 可被 `json.load` 解析。
2. `output_contract` 每个键都出现在 `result.json` 顶层（`contract_filled.filled == declared`）。
3. `appraisal.jsonl` 行数 = `counts.checkpoints`；每行非弃权判断都有 `evidence.locator` 与 `evidence.quote`。
4. `anchor_table.csv` 每行 `match ∈ {exact, normalized}`；抽 3 行用 locator 回原文核对。
5. `grading.json` 可用 `engine.grade` 复算（`python3 scripts/main.py check` → `RESULT: PASS`）。
6. `counts` 各数与非空产物一致；`fixtures` 未混入任何 `anchor_table` 行。
7. 空输入与坏 JSON 两例仍退出 0 且 `result.json` 合法（见 §5）。

## 7. 最小调用示例（示例，非正式案例结果）

```bash
mkdir -p /tmp/case/input && cd /tmp/case
printf '{"case_id":"DEMO-1","output_contract":{"appraisal":"x","evidence":"y"},"dimensions":["研究设计"]}' > input/case.json
printf '# Trial\n\n## Methods\n\nWe randomised 120 adults (n = 120) to drug A or placebo; the primary outcome was change in BP at 12 weeks (95%% CI reported).\n' > input/paper.md
python3 /bohr-workspace/submission/scripts/main.py --input input --output output --work work
```

示意输出（示例）：`status=partial`、`counts.checkpoints≈19`、`met≈4`、`not_assessable≈12`；
`appraisal.jsonl` 中 `D1` 为 `met`，`evidence.locator=F02#p2`、`quote="We randomised 120 adults (n = 120) to drug A or placebo…"`。
**以上仅为接口示意，不是任何正式案例的结论。**

## 8. 与基础 Agent 的差异（评分维度对照）

| 评分维度 | 本 Skill 提供的证据 |
|---|---|
| 任务完成度 / 正确性 | 一条命令产出完整评价表；判断由关键词族+逐字锚点推导，quote 与 locator 强制一致，错配即弃权 |
| 结果完整性 | 5 维 × 18 通用检查点 + 类型附加检查点 + 声明维度；覆盖度写入 `counts.dimensions_covered` |
| 结果可核验 | 每个判断可回到 `anchor_table.csv` 的 `locator + quote`；`grading.json.trace` 给出等级计算过程 |
| 使用增益 | 相比泛化摘要，强制落到维度、证据位置与可复算等级；弃权显式化，人工只需复核弃权与 partial 条目 |
| 创新 | 规则表外置（可改量表）、设计强度下限、反向词族极性、Agent 覆盖需先过逐字校验 |
| 可靠体验 | 任何输入都退出 0 并写合法 result.json；缺材料/坏 JSON/无文本层分别处置并留痕 |
| 生态贡献 | 量表与关键词族集中在 `references/appraisal_rules.md`，可被他人直接改写复用；产物为通用 csv/jsonl/json |

## 9. 文件清单与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 入口：一条命令、规则摘要、契约、draft schema、降级、自查 |
| `scripts/main.py` | 入口编排：索引→推导→auto-draft→渲染→result.json；`init/show/check/build` |
| `scripts/engine.py` | 底层：材料解析、切块与 locator、题录/论文、类型路由、锚点、判定、分级 |
| `references/appraisal_rules.md` | 规则块（检查点/关键词族/类型路由）+ 判定与阈值 + 维护说明 |

依赖：Python 3.8+ 标准库，无第三方包、不联网、不依赖 CWD（路径由 `Path(__file__)` 推导），
运行时不写 `__pycache__`（`sys.dont_write_bytecode=True`）。改规则只需改 `references` 的 ```rules``` 块，
改完重跑无参命令并核对 §6 的 1–7 条即可。
