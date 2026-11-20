# research-topic-innovation-eval — research-05 (v9)

把「科研选题与创新性评估」做成**可复核的五门判定**：运行时从输入材料里逐字读出五门规则、`verdict`
阈值、`E_*`/`W_*` 错误码、枚举词表、证据三态匹配与对象表消解步骤，每条规则/引文都带 `M#/p#` 定位符与
原文句子；工作稿（`draft.json`）若有则并入记分卡，并抓「判 go 但前提 unsupported」「总判定高于最弱一门」
这类自相矛盾；无法逐字命中的引文只进 `uncertainty.json`，不编造文献、数字或法律状态。纯标准库、离线、确定性。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 draft，也会写出**全部 15 件产物**与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M#/p# 定位符读材料，按 SKILL.md §1 填 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`check` 打印已 grounding 的门数、逐字命中率与未清零的 `E_*`；`compare` 把「基线散文 vs 本 Skill」的
对照写到 `/app/work/compare_report.json`。

## 3. 产物（写入 `--output`）

`result.json`、`decision_brief.md`、`gate_scorecard.json`、`prior_art_alignment_matrix.csv`、
`assumption_register.json`、`evidence_index.jsonl`、`conflicts.json`、`coverage.json`、
`self_check.json`、`change_log.json`、`search_log.json`、`uncertainty.json`、`gain_evidence.json`、
`run_log.txt`、`evidence/sources_snapshot.json`。契约键**同时**出现在 `result.json` 顶层与
`output_contract` 内，`case_id` 原样透传。

## 4. 契约键

默认键（`case.json` 未给 `output_contract` 时）：`case_id, status, deliverable, evidence_map, change_log, coverage`。
若 `/input/case.json` 自带 `output_contract`，**以它为准**逐键回填：指向产物的键解析为真实文件路径，
其余键给出真实派生值。`status ∈ {ok, partial, insufficient_evidence, input_error}`（口径取自材料 §8：
逐字命中率 <80% → partial；ok 还要求零 ERROR）。

## 5. 输入约定

- **规则材料**（Markdown）：含「五门与四类交付的映射」「verdict 阈值」「错误码」「警告码」「枚举词表」
  「模糊措辞」「检索不到 ≠ 新颖」「证据核验」「数字溯源」「输入对象表」「评分维度」「不适用的场景」等小节；
  本包按小节标题定位，缺哪节就少哪项，并在覆盖统计里如实显示。
- **字段字典**：含「顶层」「对齐矩阵长表」「最小可用工作稿」等小节；`最小可用工作稿` 一节会被标记为
  示例数据，不被当成答案引用。
- **工作稿（可选）**：`/app/work/draft.json` 或 `gate_draft.json`；`claims[].evidence[].quote` 必须逐字。
- 空文件 / 坏 JSON / 占位文件只记 `parse_status`，永不引用。

## 6. 目录（正好 12 个文件）

```
SKILL.md                                  # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
scripts/main.py                           # CLI：all / init / show / check / build / selfcheck / compare
scripts/kglib.py                          # 引擎：扫描、材料消解、五门、冲突、证据、契约回填
scripts/extract.py                        # 材料解析：按小节抽取门/阈值/错误码/枚举/评分行（带 locator+引文）
scripts/render.py                         # 产物写作：记分卡/矩阵/证据索引/简报/自检/result.json
environment/resources.yaml                # 入口声明：命令、路径、输入、契约、运行时、预算
templates/deliverable_templates.md        # 可复用骨架：对齐矩阵长表 + 证据表（含使用要点）
examples/case.json                        # 自带示例：内联两份迷你材料，--input examples 可直接跑通
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

> 引擎按职责拆成 `kglib.py` / `extract.py` / `render.py`，保证**任何单文件 <30KB**；四个脚本合计约 71KB。

## 7. 字段与口径（field contract）

| 字段 | 定义 | 口径/边界 |
|-|-|-|
| locator | `M#/p#`（材料编号 + 行号） | 每条规则、每条证据自带；未命中即拒绝 |
| evidence.match | `exact` / `despaced` / `quote_not_found` | 归一化空白后命中才算；`segments` 省略号保留原文 |
| gate.verdict | `go` / `conditional` / `no_go` | 由工作稿写入，本包按阈值表与一致性规则校验 |
| gate.conditions | 成立所需条件 | conditional/no_go 时给出可执行条件 |
| matrix row | 一 claim × 一最近工作 | 材料未给就写「材料未给」，不补猜 |
| assumption.state | `source` / `assumed` / `unsupported` | `unsupported` 存在时 G3 不得判 go |
| conflict | 支持侧 + 反证侧各带原话 | 无冲突时写 `no_contrary_found` 并限定范围 |
| gap.global_claim | 必须为 false | 材料级空白不升级为领域级断言 |
| status | `ok`/`partial`/`insufficient_evidence`/`input_error` | 由逐字命中率与 ERROR 数决定 |

## 8. 基准用例与评分口径

- `examples/case.json`：内联示例材料（迷你规则 + 迷你选题），解释器即可跑通；**示例不是任何正式案例的答案**。
- 评分维度映射（官方五维）：
  - 实际效果：五门全覆盖 + 四交付映射 + 六类覆盖统计（`coverage.six_checks`）；
  - 使用增益：`gain_evidence.json` 记录本轮可测指标，`compare` 给出基线对照（详见 `GAIN_EVIDENCE.md`）；
  - 创新增益：五门记分卡 + 对齐矩阵长表 + assumption register（kill criteria）+ 反证强制登记；
  - 可靠体验：空/坏/占位输入 → `insufficient_evidence`；四组 eval_sim PASS（`SELFTEST.md`）；
  - 生态贡献：模板、字段口径、锚点表、基准协议，换材料即可复跑。

## 9. 方法与新增能力（innovation）

(a) **规则即证据**：五门、阈值、错误码、枚举、匹配模式全部运行时读出，逐条带 locator + 逐字引文；
(b) **自相矛盾拦截**：判 go 但存在 unsupported 前提（`E_G3_GO`）、总判定高于最弱一门（`E_DECISION_INCONSISTENT`）、
    `covered` 无 `covered_by`、`novel` 无边界、矛盾证据未登记，全部报码而非静默；
(c) **“检索不到 ≠ 新颖”**：按材料 §7 的否定语境豁免口径执行，绝不把「无人研究」当新颖依据；
(d) **对象表三步消解**：别名归并、内容哈希查重、版本标记（retract/预印本/修订版）落进 `coverage.objects`；
(e) **长表矩阵**：矩阵是长表而非常规对照表，一行一主张，无法比较必须给原因。
**价值边界**：本包不联网、不做实验统计推断、不替作者决定是否投稿；材料不足时输出条件式判定并明说（材料 §12）。

## 10. 降级与诚实性

- 无可解析材料 → `status=insufficient_evidence`；每个产物带结构化 no-data 记录并列出检索位置；exit 0。
- 引文不在定位符处逐字命中 → 拒绝并记原因到 `uncertainty.json`，不计入已验证。
- 门引用的 claim 无逐字证据 → `E_GATE_NOEVID` 如实报出，不发布判定。
- 无相反证据 → `no_contrary_found` 限定范围，不等于「不存在冲突」。
- 无网络、无第三方依赖、不编造文献/数字/法律状态。

## 11. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟，结果确定性可复现（`SELFTEST.md` 给出复算哈希）。
详见 `environment/resources.yaml`。

---

## 附录 A 规则锚点表

本包**不**把规则硬编码在脚本里：运行时从输入材料按小节标题定位并逐步抽取，每条规则都带 `M#/p#` 定位符
与逐字引文。下表给出**参考材料**（本批 rich 用例的两份文档）中各规则的锚点，便于独立复核与换材料时对照。
定位符格式 `M#/p#`：`M#` 是在 `--input` 下的扫描顺序编号，`p#` 是行号。用
`python3 scripts/main.py show --input <dir>` 可打印同样的编号与每一行原文。

### A.1 规则文档（本批 rich 用例中扫描为 `M4`）

| 锚点 | 小节 | 本包用它做什么 |
|-|-|-|
| `M4/p6` | 1. 五门与四类交付的映射 | 抽取 5 行门定义（门号/名称/问题/题面交付项/主要字段），映射到四项交付 |
| `M4/p8` | 同上的导语 | 交付映射的依据句（「四项交付不是四份并列文档」） |
| `M4/p12`–`M4/p16` | 同上表体 | G1…G5 各自的行原文，进 `gate_scorecard.json` 的 `rule_quote` |
| `M4/p18` | 2. verdict 阈值 | 逐门读出 `go` / 降级为 `conditional` / `no_go` 三列 |
| `M4/p22`–`M4/p26` | 同上表体 | 每门的阈值行原文，进 `threshold_quote` |
| `M4/p30` | 3. 错误码 | 抽取 `E_*` 码、触发条件与修法（本批 33 个码） |
| `M4/p51` | 4. 警告码 | 抽取 `W_*` 码（本批 15 个） |
| `M4/p59` | 5. 枚举词表 | 抽取受控词表（`overlap`/`comparison_status`/`novelty.type`/`novelty.verdict`/`assumptions.state`/`assumptions.category`/`gate.verdict`） |
| `M4/p69` | 6. 模糊措辞词表 | 抽取模糊词表，用于 `W_G1_VAGUE` 的可测量替换要求 |
| `M4/p75` | 7. 「检索不到 ≠ 新颖」 | 抽取否定语境豁免口径；与字段字典的绝对禁令构成一侧冲突 |
| `M4/p81` | 8. 证据核验的三种匹配 | 抽取 `exact`/`segments`/`despaced`/`quote_not_found` 与命中率降级口径 |
| `M4/p92` | 9. 数字溯源 | 抽取单位表，用于「计划值 / 缺依据」提醒 |
| `M4/p98` | 10. 输入对象表 | 抽取别名归并、重复检测、版本标记三步消解 |
| `M4/p109` | 11. 评分维度 | 抽取评分点 → 实现/检查项（本批 18 行） |
| `M4/p130` | 12. 不适用的场景 | 抽取明确边界，写进 `limits` 与简报附录 |

### A.2 字段字典（本批 rich 用例中扫描为 `M3`）

| 锚点 | 小节 | 本包用它做什么 |
|-|-|-|
| `M3/p7` | 0. 顶层 | 抽取必填字段表（`question`/`gates`/`matrix`/`novelty`/`assumptions`/`claims`/`research_gap`/`decision` 等） |
| `M3/p25` | 1. `question` | G1 的四项拆解与判伪条件口径 |
| `M3/p43` | 2. `search_protocol` | 检索覆盖记录（检索式、窗口、纳排、`screened`） |
| `M3/p56` | 3. `gates` | 五门记分卡字段与跨门一致性硬规则 |
| `M3/p73` | 4. `matrix` | 矩阵长表字段（含「材料未给就写材料未给」） |
| `M3/p86` | 5. `novelty` | 创新类型学与 `covered`/`novel`/`undetermined` 判定口径 |
| `M3/p98` | 同上正文 | 「不允许用检索不到支撑 novel」的绝对禁令（冲突的支持侧） |
| `M3/p100` | 6. `assumptions` | 可行性前提三分（`source`/`assumed`/`unsupported`）与 kill criteria |
| `M3/p113` | 7. `claims` | 证据回链锚点与 `polarity=contradict` 必须进冲突 |
| `M3/p122` | 8. `conflicts` | 冲突两侧写法与 `no_contrary_found` 的限定范围要求 |
| `M3/p134` | 9. `research_gap` | `global_claim` 必须为 false |
| `M3/p144` | 10. `decision` | 总判定、条件与下一步验证 |
| `M3/p153` | 11. `change_log` | 降级记录格式（before/after/reason） |
| `M3/p160` | 12. 最小可用工作稿 | **明确是示例数据**：本包只用它证明「材料未给工作稿」，绝不当作答案 |

### A.3 换材料时的对照方法

1. `show` 打印新材料的 `M#/p#` 编号与原文；
2. 本包按小节标题定位（中文标题关键词见 `scripts/extract.py` 的 `extract()`），标题不匹配即该节缺席，
   覆盖统计里如实显示；
3. 抽取到的每条规则都进入 `evidence_index.jsonl`，用同一编号即可回到原文逐字复核；
4. 材料不提供工作稿时，五门一律给条件式判定（`status` 与 `limits` 都会写明），不虚构结论。
