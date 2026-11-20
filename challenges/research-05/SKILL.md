---
name: research-topic-gatekeeper
description: 把科研设想推进到可决策结论：读 /input/case.json 与文献材料，输出决策简报 decision_brief.md + 五门记分卡 gate_scorecard.json（go|conditional|no_go + 条件 + 证据回链）、逐条划界的 prior_art_alignment_matrix.csv、带 kill criteria 的 assumption_register.json、逐字证据索引与冲突登记。脚本做索引/校验/渲染与兜底成稿，判断由 Agent 写工作稿完成。
version: 1.0.0
---

# 科研选题与创新性评估：五门决策简报（research-topic-gatekeeper）

**一句话**：Agent 读材料亲自写工作稿 `draft.json`，脚本负责索引、机械校验与成稿；脚本永远能交出一份**最小但完整、标明降级**的稿子。

适用：拿到一份研究设想（proposal / research_idea）与一批文献材料（case.json 对象表 + `/input` 下的 PDF/MD/TXT/JSONL），要回答
“这个问题能不能做、别人做到哪、我的增量在哪、失败会怎样”。

不适用：纯文献综述写作、纯润色、在线检索新文献（本 Skill 不联网）、需要实验统计推断的任务。材料不足时它给的是 `partial` 与缺口清单，不是编出来的结论。

## 1. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id`、`task_instruction`、`output_contract`、可选 `sources[]`/`records[]`/`constraints`/`proposal`）+ `/input/task.md` + `/input/**` 材料 |
| 工作区 | `/app/work`：`index.json`（索引与对象表）、`draft.json`（**Agent 唯一必写**）、`draft.effective.json`、`check_report.json` |
| 产物 | `/app/output/`：`result.json`（主产物，契约全字段）+ `decision_brief.md` + `gate_scorecard.json` + `prior_art_alignment_matrix.csv` + `assumption_register.json` + `evidence_index.jsonl` + `conflicts.json` + `self_check.json` |
| 依赖 | Python 3.8+ 标准库；不联网；不依赖 CWD（`Path(__file__)` 定位）；PDF 优先 `pdftotext`/`pdf-text-tool`，退化为内置粗解析 |
| 参数 | `--input/--output/--work`，默认 `/input`、`/app/output`、`/app/work`；亦可用 `INPUT_DIR`/`OUTPUT_DIR`/`WORK_DIR` |
| 退出码 | **恒 0**；异常写进 `result.json.errors` / `degradations`，不靠退出码传信息 |
| 预算 | 64 次模型请求 / 900 秒 / 单响应 16384 token：索引、模板、CSV、校验全交脚本，模型只做理解与判断 |

## 2. 标准流程（Agent 主答，脚本辅助）

**主路径就是这五条命令，按顺序执行；顺序本身是方法论的一部分。**

```bash
python3 scripts/main.py init       # ① 解析 case.json/contract/task.md，建材料清单与对象表，先写合法 partial result.json
python3 scripts/main.py show       # ② 打印带 locator 的原文与对象清单，供逐字引用
#    ↓ 评审 Agent 亲自读材料，写工作稿 /app/work/draft.json（字段见 references/draft-schema.md）
python3 scripts/main.py check      # ③ 机械校验：契约/五门/矩阵/引文命中/前提状态/反例登记
python3 scripts/main.py build      # ④ 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # ⑤ 复检产物与契约完整性（可选，但交付前建议跑）
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

为什么必须这样：`build` 在没有工作稿时只能产出“五门全 conditional + 兜底骨架”的降级稿，它的价值是**不让你空手而归**，不是答案。
评审看的是判断：问题是否被拆成可检验表述、创新点是否与最近工作逐条划界、可行性每个前提是否有来源或被标为假设——这三件事脚本无法代做。

`show` 的几种用法（引用前先看清楚原文）：

```bash
python3 scripts/main.py show                      # 对象表 + 计数（sources/records/别名/版本标记/未解析）
python3 scripts/main.py show --id S2              # 某来源：题录、别名、行政说明、对应材料的逐段原文
python3 scripts/main.py show --id M3              # 某材料：按 p1,p2… 分段打印
python3 scripts/main.py show --grep 1550 --limit 20   # 全材料关键词定位，输出 [M5/p3] 这类 locator
```

### 2.1 输入发现与对象表

递归扫 `/input`，不假设键名：

- `case.json` 缺失或坏 JSON → 试 `input*.json`、`case/*.json`、`task_case*.json`；仍失败则记 `errors` 并按材料继续运行（不中断）。
- 契约：`output_contract`（dict 取值说明 / list 取字段名 / str 取单字段），缺失则产物按默认命名，`result.json` 仍写 `contract_keys: []`。
- 材料按扩展名 + 魔数识别（`%PDF`、`PK`），JSON 一律 `utf-8-sig` 读（防 BOM）；段落定位为 `M3/p2`。
- 对象表两级：`sources[]`（题录，可含 `aliases`）与 `records[]`（检索记录，可引用别名）；记录也可来自 `records.jsonl`。
- 三步机械和解：**别名解析**（`Zhang2021`→`S2`）、**重复检测**（同源多记录标 `duplicate_of`）、**版本标记**
  （`retract|撤稿`、`corrigend|勘误`、`preprint|预印本`、`supersed|取代`、`v2|修订版`）。未解析记录只登记、不猜归属。
- 材料里的内联摘要（`abstract`/`summary` 字段）作为可引用文本，定位 `S1/abstract`。

### 2.2 异常降级（全部不中断，但必须写进 `degradations`/`uncertainties`）

| 情况 | 处理 | 结果状态 |
|---|---|---|
| case.json 缺失/坏 JSON | 递归找替代；仍失败则记错误并按材料继续 | `partial`（无材料则 `failed`） |
| 契约缺失 | 产物按默认命名，`output_contract={}` 保留键 | `partial` |
| PDF 无文本层 | `pdftotext`→`pdf-text-tool`→PyMuPDF→pdfminer→标准库粗解析；只降级该材料 | `partial` |
| 图片材料 | 不转写像素，记 `no_ocr`，不猜内容 | `partial` |
| 记录别名找不到来源 | 列 `unresolved_records`，不计入覆盖判定 | `partial` |
| 材料无任何可解析文本 | 只交付骨架与缺口 | `partial` |
| 无输入材料 | 建空索引，`decision.overall=null`，说明未形成判定 | `failed` |
| 无工作稿 / 只有 `draft.md` | 兜底骨架（五门 conditional + 材料证据），`draft_source=fallback` | `partial` |
| 工作稿部分字段缺失 | `merge` 只补空字段，逐个写进 `degradations` | `partial`（或 `ok` 若仅补可选字段） |
| 引文命中率 <80% | 保留未命中行，标“不可作证据” | `partial` |

## 3. 工作稿 `draft.json`（Agent 唯一必写文件）

完整字段字典与模板：`references/draft-schema.md`。最小骨架：

```jsonc
{
  "question": {"problem_statement": "在<对象>上，<处理>相对<基线>能否把<指标>降到<阈值>？",
               "object": "…", "variables": ["…"], "baseline": "…", "expected": "…",
               "falsification": ["F1：若<观测>出现则设想被否定"], "vague_replaced": [{"vague": "显著提升", "measurable": "≥X"}]},
  "search_protocol": {"queries": ["…"], "windows": "2020-01 至 2024-12", "inclusion": ["…"], "exclusion": ["…"], "screened": 10},
  "gates": [{"gate_id": "G1", "verdict": "go", "conditions": [], "evidence_ids": ["C1"],
             "residual_risks": ["…"], "pivot_if_no_go": "…", "rationale": "…"}],
  "matrix": [{"claim_id": "C1", "source_id": "S1", "task": "…", "method": "…", "data": "…", "evaluation": "…",
              "overlap": "method", "comparison_status": "comparable", "cannot_compare_reason": "",
              "boundary_note": "…", "locator": "M3/p2"}],
  "novelty": [{"claim_id": "C1", "type": "method", "verdict": "covered", "covered_by": ["S1"], "boundary": "…",
               "evidence": [{"source_id": "S1", "locator": "M3/p2", "quote": "逐字原文"}]}],
  "assumptions": [{"id": "A2", "statement": "…", "category": "experiment", "state": "unsupported",
                   "source_locator": "", "kill_criteria": "…", "validation_experiment": "…"}],
  "claims": [{"claim_id": "C1", "text": "…", "evidence": [{"source_id": "S1", "locator": "M3/p2", "quote": "逐字原文",
                                                          "polarity": "support"}]}],
  "conflicts": [{"topic": "…", "support": [{"source_id": "S1", "locator": "M3/p2", "quote": "…"}],
                 "contradict": [{"source_id": "S2", "locator": "M4/p3", "quote": "…"}],
                 "resolution": "…", "impact_on_decision": "…"}],
  "research_gap": {"statement": "在本材料范围内未见…", "scope": "本材料与本次纳排范围", "basis": [], "global_claim": false},
  "decision": {"overall": "conditional", "summary": "…", "conditions": ["…"],
               "next_validation": [{"step": "…", "evidence_needed": "…", "gate": "G3"}]}
}
```

三条硬口径：`quote` 必须逐字（改写即失去证据资格）；`source_id` 只能用对象表里真实存在的编号；`verdict` 只能是 `go|conditional|no_go`。

## 4. 评审委员会五问（本 Skill 的组织方式）

五问是同一份判断的五个侧面；每问对应一门 gate，产物字段固定，避免“四平八稳的综述式回答”。

### Q1 值得做吗（G1 worth_doing）

- **判定规则**：问题必须可拆成“对象 / 关键变量 / 比较基线 / 预期结论”，并给出至少一条**可观测的判伪条件**（什么观测出现就否定它）。
- **需要的证据**：设想原文（`proposal` 或 `proposal.md`）、材料中对指标与基线的描述（`quote` + `locator`）。
- **verdict 阈值**：四项齐 + ≥1 条判伪条件 → 可判 `go`；缺任一项，或判伪条件不可观测 → 最高 `conditional`。
- **产物字段**：`question.*`、`gates[G1]`；正文 §1（拆解表 + 可证伪条件 + 模糊措辞替换 + untestable）。
- **常见退化**：把“提升性能”原样抄进问题；把不可测的“界面质量改善”写成指标。脚本用 `W_G1_VAGUE` 与 `E_G1_FALSIFY` 拦。

### Q2 别人做到哪一步（G2 nobody_done）

- **判定规则**：为每条主张找出 1–3 篇**最相近**的工作，按任务/方法/数据/评价四维填对照；不可直接比较的必须写原因。
- **需要的证据**：对象表里真实的 `S#` 编号 + 对应材料的段落定位；别名要归并到同一 `S#`（否则会把同一工作算两次）。
- **verdict 阈值**：每条主张 ≥2 个可比工作且已划界 → 可 `go`；对照不足 → `conditional`。
- **产物字段**：`matrix[]`、`gates[G2]`、`prior_art_alignment_matrix.csv`；正文 §4。
- **常见退化**：拿综述当对照；把 `not_comparable` 硬填成 `comparable`；编造文献编号（`E_G2_FAKE` 直接报错）。

### Q3 做得出来吗（G3 can_do）

- **判定规则**：把可行性拆成六类前提（数据/算力/实验/时间/人员/伦理），每条给 `state`、`kill_criteria`、`validation_experiment`。
- **需要的证据**：`state=source` 必须有逐字出处与定位；没有就写 `assumed` 或 `unsupported`，不许默认“可行”。
- **verdict 阈值**：无 `unsupported` 且类别 ≥3 → 可 `go`；存在 `unsupported` → 必须 `conditional` 并写清缺什么、怎么补。
- **产物字段**：`assumptions[]`、`gates[G3]`、`assumption_register.json`；正文 §6。
- **常见退化**：一句“技术路线可行”；把“预算还没批”写成 assumed 而不写 kill criteria。

### Q4 不是旧方案吗（G4 not_old_wine）

- **判定规则**：每条创新陈述先定类型（method / data / scenario_transfer / conclusion_correction），再判 `covered|novel|undetermined`；
  判 `covered` 给 `covered_by`，判 `novel` 给 `boundary`，判不了就 `undetermined`。
- **需要的证据**：矩阵里该主张的对照行 + 覆盖来源的逐字证据。
- **verdict 阈值**：无 `undetermined` → 可 `go`；核心主张 `covered` → 该主张不能当创新点，创新须改口或降级。
- **产物字段**：`novelty[]`、`gates[G4]`；正文 §5。
- **硬约束**：**“检索不到”不构成新颖性**（`E_G4_FALSE_NOVEL`）；场景迁移不得写成理论创新。

### Q5 失败会怎样（G5 downside）

- **判定规则**：登记相反结论与原话，说明取舍；给残余风险、退出成本与 `pivot_if_no_go`。
- **需要的证据**：`polarity=contradict` 的证据行、对象表里的勘误/预印本/撤稿标记。
- **verdict 阈值**：反证已登记并取舍 + kill criteria 可判定 → 可 `go`；否则 `conditional`。
- **产物字段**：`conflicts[]`、`gates[G5]`、`conflicts.json`；正文 §7。
- **常见退化**：只报支持证据（`E_CONFLICT_SILENT`）；把冲突写成“有待进一步研究”。

## 5. `check` 判什么

只报不改。ERROR 必须修完再 `build`（否则 `status=partial`）；WARN 允许存在但会进 `degradations`。
错误码与修法全表见 `references/gate-rules.md` §3–§4，核心几类：

- 契约/结构：五门是否齐（`E_GATE_MISSING`）、verdict 是否合法（`E_GATE_VERDICT`）、`evidence_ids` 是否解析到已验证证据（`E_GATE_BADEVID`）。
- 问题可检验：`E_G1_SPLIT`、`E_G1_FALSIFY`；模糊措辞 `W_G1_VAGUE`。
- 比较正确性：`E_G2_FAKE`（编造文献）、`E_G2_REASON`（不可比却不给原因）、`E_G2_OVERLAP`。
- 可行性口径：`E_G3_STATE`、`E_G3_UNSOURCED`（标 source 却无出处）、`E_G3_KILL`、`E_G3_GO`（有 unsupported 却判 go）。
- 创新判定：`E_G4_COVERED_BY`、`E_G4_BOUNDARY`、`E_G4_FALSE_NOVEL`。
- 反证与空白：`E_CONFLICT_UNLOGGED`、`E_CONFLICT_SILENT`、`E_GAP_GLOBAL`。
- 综合一致：`E_DECISION_INCONSISTENT`（某门 no_go 却总判 go，或有 conditional 却总判 go）。
- 引文核验：归一化空白后逐字比对，支持 `exact`/`segments`（`…` 省略）/`despaced`（PDF 断行）；命中率与逐条定位写进 `result.evidence`。
- 数字溯源：`数字+单位` 在材料中无同形文本 → `W_NUMBER`（计划值请标明）。

## 6. 输出契约

`result.json` 是主产物：

1. **原样回填 `output_contract` 的每一个字段**（不改名、不漏键，缺值 `null`/`[]`），同时把同名字段提升到顶层；
2. 信封字段：`case_id`、`status`（`ok|partial|failed`）、`skill`、`skill_version`、`note`、`errors[]`、`degradations[]`、`uncertainties[]`、`change_log[]`、`runtime{}`；
3. 业务字段：`decision{overall,summary,conditions,next_validation}`、`gates[]`、`prior_art_rows[]`、`novelty[]`、`assumptions[]`、`claims[]`、`conflicts[]`、`research_gap`、`search_protocol`、`question`、`evidence[]`、`sources[]`、`coverage{six_checks,six_passed,evidence_hit_rate,assumption_states,objects…}`、`deliverable{path,chars,companions,draft_source}`、`artifacts{}`、`self_check`（跑过 `selfcheck` 后）。

契约字段按语义映射到业务槽位（顺序即优先级）：`decision/gate/prior/novel/feasib/assumption/gap/conflict/search/question/source/evidence/uncertain/coverage/deliver/change/status/case/summary`。
未知字段保留键并给 `[]`，绝不静默删除。

状态判定：`ok` = 工作稿来自 Agent + 零 ERROR + 引文命中率 ≥80%；`partial` = 用了兜底/有 ERROR/命中不足/材料解析降级；
`failed` = 无输入材料（此时 `decision.overall=null` 并说明未形成判定）。

### 6.1 副产物清单

| 文件 | 内容 | 复核方式 |
|---|---|---|
| `decision_brief.md` | 叙事主体：速览 → 问题拆解 → 检索与对象表 → G1–G5 逐门（含证据引用与残余风险）→ 对齐矩阵 → 创新判定 → 前提登记 → 冲突 → 空白 → 结论与下一步最小验证 → 附录 A 证据索引 / B 覆盖自检 / C 变更与不确定性 | 每段带 `S#@M#/p#` 与逐字 quote |
| `gate_scorecard.json` | 五门判定、条件、证据计数、残余风险、pivot、`verdict_counts` | 与 `result.gates` 一致 |
| `prior_art_alignment_matrix.csv` | 长表：`proposal_claim_id,source_id,task,method,data,evaluation,overlap,comparison_status,cannot_compare_reason,boundary_note,evidence_locator` | 可直接进 Excel/pandas 复核 |
| `assumption_register.json` | 前提三态、来源定位、kill criteria、最小验证实验 | `counts` 给出 source/assumed/unsupported 分布 |
| `evidence_index.jsonl` | 每条 `{ref,source_id,locator,quote,polarity,match,status}` | 未命中行一目了然 |
| `conflicts.json` | 相反证据对、无冲突声明、对判定的影响 | 不允许只报支持证据 |
| `self_check.json` | 契约完整、产物非空、五门齐、状态诚实、证据命中率 | `overall_pass` + `failures` |

## 7. 自检清单（交付前逐条过）

- [ ] `draft.json` 是我读过材料后写的，不是脚本兜底（`build` 输出 `来源=agent`）。
- [ ] 五个门都有 verdict；`conditional`/`no_go` 都有条件与 pivot；总判定不高于最弱的一门。
- [ ] 问题被拆成四项 + ≥1 条可观测判伪条件；模糊措辞已替换或列入 untestable。
- [ ] 每条创新主张都有 `covered_by` 或 `boundary`；没有用“检索不到”支撑新颖。
- [ ] 每条前提有 `state` 与 `kill_criteria`；`source` 的有逐字证据；`unsupported` 的那门不是 `go`。
- [ ] 相反证据已登记并写取舍，或明确写了 `no_contrary_found` 的范围。
- [ ] 研究空白限定了范围，`global_claim=false`。
- [ ] 引文全部逐字命中（看 `check` 的 `证据 x/y`），未命中的已删或改回原文。
- [ ] `degradations` 里每条都能解释（材料缺失 / 版本冲突 / 未解析记录）。
- [ ] `selfcheck` 输出 `PASS`，或 FAIL 项已写明原因。

## 8. 最小调用示例（示例输出，**非任何正式案例结果**）

```bash
$ python3 scripts/main.py init --input /input --output /app/output --work /app/work
== init v1.0.0 == 输入 /input ｜ case /input/case.json ｜ task.md task.md
契约字段 7 个：question_definition、prior_work_matrix、novelty_assessment、feasibility、evidence_table、uncertainties、decision
任务指令：判断下列研究设想是否可立项：……
材料 6 份（可读 6，共 1828 字符）
  M1   proposal.md        proposal   text    158字   4段 plain
  M3   sources/S1.md      source     text    633字   5段 plain
对象表：sources 3 ｜ records 6（解析 5 / 未解析 1 / 重复 2）｜ constraints 4 ｜ 内联摘要 0
  S1    Dual-layer passivation for MAPbI3… 材料 M3  别名 Demo2022  版本 —
  R2    ref=Zhang2021  → S2  retrieved via alias
  R3    ref=S1         重复于 R1  corrigendum: Fig.3 axis mislabeled, v2
  ! 未解析记录：R4=S9（需人工确认，不得臆测归属）
NEXT: python3 scripts/main.py show  → 读材料判读  → 写 /app/work/draft.json  → check  → build

$ python3 scripts/main.py check
五门 5/5 ｜ 矩阵 4 行 ｜ 创新 2 ｜ 前提 3 ｜ 冲突 1 ｜ 证据 7/7 逐字命中 ｜ 六类 6/6 ｜ ERROR 0 WARN 1
WARN  W_NUMBER  数字在材料中无同形文本（须标计划值或补依据）：300 h、10 个月

$ python3 scripts/main.py build
== build == status=ok ｜ 来源=agent ｜ decision=conditional ｜ 五门 5/5 ｜ 矩阵 4 行 ｜ 证据 7/7 ｜ 六类 6/6
  decision_brief.md                  14730 B
  gate_scorecard.json                 5680 B
  prior_art_alignment_matrix.csv      1364 B
  assumption_register.json            1820 B
  evidence_index.jsonl                1393 B
  conflicts.json                      1136 B
result.json 已 finalize（契约 7 字段全部回填）
```

以上数字来自本包自测所用的小型合成材料，**不是任何正式案例的评测结果**。

## 9. 文件清单与版本

| 文件 | 作用 | 大小 |
|---|---|---|
| `SKILL.md` | 本说明：用途、五命令主路径、五问口径、契约、自检 | ~22KB |
| `scripts/main.py` | CLI、契约回填、finalize、五命令编排 | ~21KB |
| `scripts/indexer.py` | 材料抽取（PDF/DOCX/XLSX/文本）、对象表、别名与版本和解 | ~13KB |
| `scripts/gates.py` | 工作稿解析、逐条证据定位校验、五门判据、兜底工作稿 | ~29KB |
| `scripts/render.py` | 决策简报、记分卡、矩阵 CSV、前提登记、证据 jsonl、冲突 | ~23KB |
| `references/draft-schema.md` | 工作稿字段字典 + 模板 + 最小示例 | ~9KB |
| `references/gate-rules.md` | 五门阈值、错误码全表、枚举词表、评分维度映射、边界 | ~11KB |

版本 1.0.0。改判定口径 → 同时改 `gates.check()` 与 `references/gate-rules.md`；改版式 → 只改 `render.py`；改枚举 → 改 `gates.py` 顶部常量。四个脚本纯标准库，均支持 `--help`。

## 10. 维护与已知边界

- 定位基于“段”（空行分隔）；PDF 粗解析可能丢阅读顺序，重要引文先 `show --id Mn` 回看，再决定 `locator`。
- 不做 OCR：图片与无文本层 PDF 记 `no_ocr`/`pdf_text_empty`，不猜内容；材料无文本时状态为 `partial`。
- 不联网：检索协议只是**记录** Agent/使用者实际用过的检索式，脚本不会去检索，也不会把“本地没找到”升格成“领域内无人研究”。
- 数字溯源是**字面匹配**：`85%` 与 `85 %` 可能误报，属预期；计划值请显式标注。
- 别名/版本和解基于字符串规则，`v2` 这类标记在无关上下文里可能误判为版本更新，需在简报里说明并人工确认。
- 契约语义映射是关键词匹配：字段名与业务槽位差太远时会映射到 `[]`，此时 `result.json` 仍保留键，正文产物不受影响。
- 跨领域复用时只需换材料与 `output_contract`，五门口径与错误码无需改；学科特有的合规项（伦理批件、数据授权）请写进 `assumptions` 的 `ethics` 类，不要硬编码进脚本。
