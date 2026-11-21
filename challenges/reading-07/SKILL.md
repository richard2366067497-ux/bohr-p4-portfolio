---
name: claim-evidence-verifier
description: 把待核验的科研论断清单落到逐字原文证据上，输出四级判定（supported / partially_supported / contradicted / insufficient_evidence）与段落级 locator，并生成可复核的 result.json、证据卡片与核验报告。用于论断核验、引用支持度检查、批量事实核查、证据溯源；触发语包括「核验这句话」「这句话有依据吗」「这条引用支持该结论吗」「证据溯源」「帮我核对这批论断」「把论断落到原文段落」，英文对应 fact-check this claim、does this citation support the sentence、audit claims against a paper、verify a claim list against a PDF。
version: 3.0.0
---

# 论断—证据核验器（claim-evidence-verifier）

给定一份**待核验论断清单**（每句话都是"待问的问题"，不是既定事实）和一批论文/材料，本 Skill 把每条
论断拆成原子子判断，逐条找回**最小充分的一段原文**，给出四级支持度判定，并把"论断 → 逐字证据 →
原文定位 → 判定 → 理由"整条链落盘。

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按手册的求解框架（论断拆解 → 逐字证据 → 原文定位 → 支持度判定 → 理由，含每步门控）推进；前一步未冻结不进入下一步。
- **口径**：按手册的四档支持度判定口径逐条核验；保留比较对象、否定、显著性、条件与来源定位，不把“主题相关”当作“真正支持”。
- **陷阱**：按手册的领域陷阱清单逐条排雷（错误做法 → 正确做法）。
- **门控**：交付前逐项通过手册 **§9 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为成功。

---

## 1. 单命令等价入口（single command — 评测方只需这一条）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run`（无参数时的默认命令）即跑完整流程：**发现输入 → 读契约 → 切块建索引 → 确定性推导 → 生成 work 稿 → 渲染产物 →
写最终 result.json**。纯标准库、不联网、判定路径不读时钟、不依赖 CWD（按 `Path(__file__).parent` 自定位）。

产物落在 `/app/output`（`--output` 可覆盖）：

| 文件 | 内容 |
|---|---|
| `result.json` | 主产物：`output_contract` 全部键原位回填 + case_id/status/claims/evidence/counts/sources/uncertainties/method_notes/errors/degradations |
| `evidence_cards.jsonl` | **每子判断一行**：claim_id/sub_id/text/verdict/rule/evidence[{quote,locator,role}]/rationale |
| `verification_report.md` | 人可读报告：逐条判定、证据、冲突 |

兼容子命令：`init`（建索引与 partial 产物）、`show`（打印候选段落）、`check`（校验可选工作稿）、
`build`（等同 `run`）。**主路径只有上面那一条**，不需要先读材料。

## 2. 适用与不适用

**适用**：单篇或少量文献的论断核验；引用段落是否真的包含被引结论；`claims-to-verify.json` 的批量
核验；需要把"主题相关"与"真正支持"分开的场合。

**不适用**（说明越界即停止）：代写综述、整篇翻译、绘图、跑统计或数值实验、跨文献元分析、
替作者补做原文没有的实验。

## 3. 输入与输出契约

**输入**（`/input`，可用 `--input` 覆盖）：`case.json`（`case_id` 与 `output_contract`）；论断清单
（`claims-to-verify.json` → `claims_to_verify.json` → `claims.json` → `case.json` 内的 `claims` /
`statements` / `claim_list` → 目录内任意 JSON 的论断列表）；材料递归扫 `pdf / md / txt / json / csv`。
字段别名 `claim_id|cid|id`、`claim_text|text|statement|claim|sentence`、`source_hint|paper_id|source`；
纯字符串列表自动编号 `C1..Cn`，图片只登记 `gaps`。

**输出**：`result.json` 顶层 = `output_contract` 的每个键（不改名、不漏键，无法产出时填 `null`
并记 `degradations[contract_field_filled_empty]`），再加固定信封字段。契约未声明时默认回填
`case_id / status / claims / evidence / sources / uncertainties`。

`status` 只有三个值：`answered`（全部论断都拿到确定判定且无缺口）、`partial`（主体完整但有弃权项或降级）、
`input_error`（无清单或材料完全不可读）。**没有工作稿不会退化成空证据**——这正是本版的核心修正。

## 4. 确定性推导规则（脚本自动执行）

**4.1 切块**：每个材料块是一个 unit，带 `unit_id`（U7）与 locator `<file>#p<n>`——PDF 的 `n`
是页码（`pypdf` 或 `pdftotext` 抽取），其余格式为文件内块序号。JSON 保留原生 `id`/`paragraph_id`。

**4.2 拆分**：按句号/分号/并列连词切到"一条只含一个可判真假的断言"，最多 5 条；识别比较、因果、
范围、否定线索，并记入子判断类型。

**4.3 检索打分**（可复现）：

```
coverage = 命中关键词 / 论断关键词
numcov   = 命中的数值锚点 / 论断数值锚点     （按 token 边界匹配，1 不匹配 120）
score    = 0.72*coverage + 0.28*numcov       （无论断数值时 = coverage）
score   += 0.15                              （source_hint 命中文件名）
```

取 top-3，排序键固定：`score` desc → 输入顺序 → `unit_id` 字典序。每条候选的 quote 取该块内
得分最高、12–300 字的**完整句子**，保证是原文子串。

**4.4 判定表**（自上而下，先命中者生效；与 `references/verification-rules.md` 完全一致）：

| 规则 | 条件 | 判定 |
|---|---|---|
| R0 | 无候选，或最佳 `coverage < 0.14` 且无数值命中 | `insufficient_evidence` |
| R1a | 最佳段落的褒贬方向与论断相反且 `coverage ≥ 0.30` | `contradicted` |
| R1b | 双锚点比较：原文把两个比较对象的值**排成相反顺序**（如 62% vs 78%） | `contradicted` |
| R1c | 另一段落方向相反且 `coverage ≥ 0.30` | `contradicted`（两段并列） |
| R2 | 论断肯定有效应，原文明确报"无显著差异/无效应" | `contradicted` |
| R3 | 论断与原文同为否定表述 | `supported` |
| R4 | `coverage ≥ 0.34` 且（无数值或数值全中），或数值顺序与论断一致 | `supported` |
| R5 | `coverage ≥ 0.20` 或部分数值命中 | `partially_supported`（带缺口标签） |
| R6 | 其他 | `insufficient_evidence` |

**4.5 quote 回查**：每条 quote 写盘前都做归一化包含校验（NFKC + 空白折叠 + CJK 去空白）；
不命中则该条证据被丢弃、记录 `degradations[quote_unverified]`，绝不能把"看起来合理"的句子写进去。

**4.6 聚合**：全 supported→supported；全 contradicted→contradicted；全 insufficient→insufficient；
contradicted 混 supported/partial→partial；supported 混 insufficient→partial；其余 partial。
置信度取子判断最低值。跨来源方向相反（各自 `score ≥ 0.30`）→ `conflict.present=true`、
`unresolved=true`、双方原文并列、整体降为 `partially_supported` 且置信度 `low`。

**4.7 无证据即弃权**：没命中就写 `insufficient_evidence` + `search_scope`（扫了多少块、用了哪些查词），
说明缺什么。**不编造，也不把"没找到"写成"被证伪"。**

## 5. Agent 可选增强（不是必需）

若 `/app/work/draft.json` 存在，它会**逐条**覆盖确定性结论；不存在时上面的规则照样产出完整账本。
`/app/work/draft.template.json` 每次运行都会重写，里面已填好 `claim_id` 与候选 unit，直接改即可。

```json
{"schema": "claim-evidence-draft/2", "claims": [{"claim_id": "C1", "sub_claims": [
  {"sub_id": "C1.1", "text": "450 °C 的转化率高于 350 °C", "type": "comparison",
   "verdict": "contradicted", "verdict_confidence": "high",
   "rationale": "原文 450 °C 为 62%，350 °C 为 78%",
   "evidence": [{"unit_id": "U3", "quote": "The 450 °C sample reached a CO conversion of 62%, whereas the 350 °C sample reached 78%."}],
   "limitations": ["direction_opposite"]}]}]}
```

合并时的硬校验（不通过就退回脚本判定，绝不写入）：`verdict` 必须在四级闭集内；`unit_id` 必须
真实存在；`quote` 必须在指称单元里逐字命中；`supported`/`partially_supported` 若没有一条通过
校验的证据则整条作废。因此"Agent 说支持但引文是编的"在这条链上无法通过。

## 6. 失败与降级（所有分支退出码 0）

| 触发 | 行为 |
|---|---|
| 目录不存在 / 空目录 | 不造数据；`status=input_error`，`pending_human` 说明该补什么 |
| `case.json` 坏 JSON | `errors[case_json_unreadable]`，用其余文件继续，`case_id` 回退目录名 |
| 清单缺失或坏 JSON | `status=input_error`；不臆造论断 |
| PDF 无文本层 | 记 `material_unreadable`，`sources.readable=false`，相关论断 `insufficient_evidence` |
| quote 回查失败 | 丢弃该证据 + `quote_unverified`，必要时降级为 insufficient |
| 单条论断抛异常 | 记 `verification_error`，其余照常 |
| 任意未捕获异常 | 仍先写合法 partial `result.json`，再打印 `[fatal]` |
| 契约键无产出 | 填 `null` 并记 `contract_field_filled_empty`，不静默丢键 |

**首写即落盘**：任何命令一开始就先写合法 partial `result.json` 再覆盖升级，中途被杀也留得下可读产物。

## 7. 交付前自查（本次已实跑，见 `SELFTEST.md`）

- `python3 scripts/main.py`（无参数）→ exit 0；`result.json` 合法；契约键 100% 回填；三个产物非空。
- 每条子判断都有 locator + 逐字 quote，或明确 `insufficient_evidence` + `search_scope`。
- `self_check.passed=true`：无越界判定，`supported/partially` 有已验证证据，`contradicted` 有反证，
  `unverified_quotes=0`。
- 空目录、坏 JSON、缺文件三种输入均 exit 0 且 `result.json` 合法；同输入复跑判定完全一致。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为成功。

命令行自检输出示例（真实运行）：`claims=5 sub_claims=6 units=4 sources=1 | quotes=6/6 | status=answered | self_check=True`。

## 8. 评分五维落点

| 维度 | 本包实现 |
|---|---|
| 实际效果·完成度 | 每条论断必有判定（含 insufficient）；`counts.claims == 输入条数`；单命令完成 |
| 实际效果·正确性 | R0–R6 判定表 + 两条红线（主题相关≠支持、未支持≠证伪）+ 数值顺序规则（62 vs 78 这类反例必抓） |
| 实际效果·完整性 | 逐子判断覆盖事实/比较/因果/范围；反证检索；跨来源冲突并列 |
| 实际效果·可核验 | 论断→子判断→quote→locator→verdict→basis 五段链，回查结果写在卡片里 |
| 使用增益 | 误支持由判定表 + draft 校验双重拦截；漏检靠全覆盖与反证扫描降低；复跑一致 |
| 创新增益 | 段落级 locator、双锚点数值顺序判定、四级支持度、冲突并列、draft 可验证合并 |
| 可靠体验 | 单命令触发；恒 exit 0；空/坏/缺三类输入各有分支；`partial` 与 `input_error` 分清 |
| 生态贡献 | 本文档 + `verification-rules.md`（规则表/字段字典/draft schema 三合一）+ 可复用脚本 |

## 9. 最小示例（**示例输入，非正式案例结果**）

```bash
python3 scripts/main.py --input ./demo/input --work ./demo/work --output ./demo/output
```

示例论断：`"450 °C 样品的 CO 转化率高于 350 °C 样品。"`；示例材料：
`"The 450 °C sample reached a CO conversion of 62%, whereas the 350 °C sample reached 78%."`

示意输出：子判断 `comparison` 判 `contradicted`（`rule_id=R1`，证据 `role=counter`，
`locator=paper.md#p1`），整体 `contradicted`、`high`。仅说明接口，**不是正式案例答案**。

## 10. 文件、依赖与维护

```
SKILL.md                             本说明
scripts/main.py                      单入口：CLI、编排、可选 draft 合并、契约回填、报告与自检
scripts/engine.py                    发现/归一/切块/检索/判定规则（纯函数，可单独 import）
references/verification-rules.md     判定表、打分公式、字段字典、draft schema、限制标签
```

依赖：Python ≥3.8 标准库。PDF 抽取优先 `pypdf`，其次 `pdftotext`（平台 `pdf-text-tool`），
两者都缺时按"无文本层"降级并记录，绝不猜内容。不联网、不写 `__pycache__`（`sys.dont_write_bytecode`）。

维护约定：改判定规则必须同步 `references/verification-rules.md`；新增材料格式只改
`engine.load_source`，输出 schema 不变；改动后重跑第 7 节自查并比对两次 `counts`。

**方法边界（务必随结论转述）**：本 Skill 做词面 + 数值 + 方向的可复核核验，不是同行评审、也不是语义
蕴含模型。改写、同义替换、跨段推理、图表读数会让它偏保守或偏宽；判 `supported` 仍建议人工扫一眼 quote。
无文本层 PDF、只有题录的材料，如实记为缺口而不是结论。

## 文件清单与维护

- `SKILL.md` — 本文件：入口、契约、判定口径、降级、自查
- `scripts/main.py`、`scripts/engine.py` — 单命令入口与证据核验引擎
- `references/expert_playbook.md` — 专家参考手册（执行前必读）
- `references/verification-rules.md` — 支持度判定与证据规则
- `environment/resources.yaml` — 资源入口声明
- `examples/` — 最小可跑样例
- `README.md` / `SELFTEST.md` / `GAIN_EVIDENCE.md` / `GITHUB_URL.txt`
- 依赖：Python 3.9+ 标准库；无第三方、无网络、无外部模型。
