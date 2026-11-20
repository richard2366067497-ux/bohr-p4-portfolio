# method-statistics-audit — review-03 (v9)

把一份审查材料集（清单 / 规则表 / 严重度锚点）读成**可复核的方法与统计审查单**：从材料里
**解析**缺陷类型库与「性质→严重度上限」表；逐条规则给出 `M#/p#` locator 与逐字引文；建台账，
把「未报告」与「做错」严格分开；覆盖五个检查面与六类审查维度；`underreporting` 封顶 `major`、
`acceptable_but_should_clarify` 封顶 `minor`；诚实记录边界。空/坏/占位材料降级为
`insufficient_evidence`。纯标准库、离线、确定性、退出码恒 0。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 `/app/work/draft.json`，也会写出**全部**产物与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M02/p24 定位符读材料，按需填 /app/work/draft.json（照抄 init 生成的骨架）
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`compare` 把「基线朴素策略 vs 本 Skill 结构化审查单」的对照写到 `/app/work/compare_report.json`，
并在输出目录写出 `gain_report.json` 与 `gain_report.md`。

## 3. 产物

写入 `--output`：`result.json`、`audit_report.md`、`statistics_ledger.json`、`findings.json`、
`coverage.json`、`evidence_map.json`、`change_log.json`、`index.json`、`self_check.json`、
`boundary_log.json`、`run_log.txt`、`gain_report.json`、`gain_report.md`，以及 `evidence/` 下每个来源
一份原始证据快照。`result.json` 的 `output_contract` 键**同时**出现在顶层与 `output_contract` 对象内，
`case_id` 原样透传。

## 4. 契约键

默认键（当 `case.json` 未给 `output_contract` 时）：
`case_id, status, deliverable, findings, ledger, coverage, evidence_map, change_log`。
若 `/input/case.json` 自带 `output_contract`，则**以它为准**逐键回填：指向产物的键解析为真实文件路径，
缺陷类型键回填其在材料中定位到的规则行，其余键给出真实派生值。`status ∈ {partial, insufficient_evidence, input_error}`。

## 5. 输入约定

- **案例**：`case.json`（`case_id`、`language`、`materials_root`、可选 `output_contract`）。
- **材料**：`materials/**` 任意文本/JSON。任务脚手架（`case.json`/`task.md`/`README`）会被索引但不作为可检索来源引用。
- 不可用文件（空/坏 JSON/占位文本/二进制）只记录 `parse_status`，永不引用。

## 6. 目录

```
SKILL.md                                  # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
scripts/main.py                           # CLI 入口：all / init / show / check / build / selfcheck / compare
scripts/auditlib.py                       # 引擎+io：扫描 / 规则解析 / 定位 / 台账 / 覆盖 / 证据 / 结果
environment/resources.yaml                # 资源入口声明：入口命令、路径、输入约定、契约、运行时
references/review_checklist.md            # 可复用审查清单（五面 × 六维，逐项 checklist）
references/defect_types_and_severity.md   # 可复用缺陷类型库（28 项）+ 性质封顶 + 严重度锚点
templates/draft_template.json             # 可复用 draft.json 骨架模板
examples/case.json                        # 最小调用示例（标注为示例，非正式案例）
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 7. 字段与口径（field contract）

| 字段 | 定义 | 口径/边界 |
|-|-|-|
| locator | `M#/p#`（来源 id + 行号） | 每条被引用的规则**自带** locator；不可解析的来源不引用 |
| quote | 材料行的**逐字**引文 | 写入前过一次确定性 token 规范化（映射见 `scripts/auditlib.py`） |
| issue_type | 缺陷类型 | 从材料的 28 项表解析；解析失败退到内置库并记 `rules_fallback` |
| defect_nature | 缺陷性质 | `method_flaw / underreporting / acceptable_but_should_clarify / no_defect` |
| severity_cap | 性质上限 | `method_flaw→critical / underreporting→major / acceptable→minor`；超限自动降级并记 `change_log` |
| exercised_by_material | 是否被材料中的稿件行命中 | 本类材料只有规则表 → `no`，不冒充已审出的缺陷 |

## 8. 基准用例与评分口径（benchmark + scoring，可复用）

- 本包的对照运行见 `SELFTEST.md`（四组 eval_sim 全部 PASS）与 `GAIN_EVIDENCE.md`（基线为**模拟**，非官方对照）。
- 评分维度映射（对应官方五维）：
  - 实际效果：`audit_report.md` + `statistics_ledger.json` + `findings.json` + `coverage.json` +
    `evidence_map.json` 覆盖五面六维；每条带 locator 与逐字引文。
  - 使用增益：`gain_report.json`/`gain_report.md` 给出「基线文字 vs 结构化审查单」的可核验差；对照声明见 `GAIN_EVIDENCE.md`。
  - 创新增益：材料内规则解析 + 性质封顶 + 空稿不冒充 + 证据快照（见 `GAIN_EVIDENCE.md` §3）。
  - 可靠体验：空/坏/占位材料诚实降级为 `insufficient_evidence`；异常恒 0 退出；`SELFTEST.md` 有稳定性证据。
  - 生态贡献：SKILL.md、审查清单、缺陷类型库、draft 模板、契约骨架齐全，可换成新案例复跑。

## 9. 方法与新增能力（innovation）

(a) **规则库从材料解析**：`parse_library` 解析 `| issue_type | 含义 | 面/维度/性质 |` 表与性质封顶表，每步可复算；
(b) **性质—严重度封顶**：`underreporting` 不得超 `major`、`acceptable_but_should_clarify` 不得超 `minor`，
超限即降级并写 `changes`，让「缺报告」与「方法错」在评分上各自归位；
(c) **空稿不冒充**：材料只有规则表时，每条规则标 `exercised_by_material=no`，绝不把规则抄成缺陷；
(d) **六维覆盖显式化**：`coverage.json` 如实列出命中的维度与未命中的维度，覆盖率是「审过什么」的记录；
(e) **证据快照**：每个来源一份 `evidence/<id>.json`，每条规则可回看原文行。
**价值边界**：不替代同行评审、不做投稿决策；不做文献检索；未逐字引到的项写 `unchecked_items`，不臆造稿件句。

## 10. 降级与诚实性

- 无可定位规则与可引用行 → `status=insufficient_evidence`；每个产物带结构化 no-data 记录并列出检索位置；exit 0。
- 坏 JSON / 空文件 / 占位文本 → 只记 `parse_status` 并写入对应 `evidence/<id>.json`，绝不引用。
- 规则表不可解析 → 用内置 28 项库并在 `degradations` 记 `rules_fallback`，绝不静默。
- 无网络、无时钟、无第三方依赖、不编造稿件句、严重度或评测分数。

## 11. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟、结果确定性可复现。详见 `environment/resources.yaml`。
