# patent-search-dossier — search-11 (v10)

把一个专利/文献材料集读成**可复核的检索档案**：定位每一条可引用的行并给出 `M#/p#` locator；
用可追溯的规则链规范化公开号、申请号、授权号、优先权号；逐条记录法律状态的来源分级与 `as_of`；
用绿/黄/红许可闸门给每个来源分级；族图只陈述观察到的链接、从不声称穷尽；把边界与缺口写清楚；
每个数字与标签都保留其原始证据快照；并渲染一张族图 PNG。空/坏/占位材料诚实降级为
`insufficient_evidence`。纯标准库、离线、确定性、退出码恒 0。

> **执行前必读**：`references/expert_playbook.md`（七步框架 / 授权分级 / 指标公式 / 事实边界 /
> 防扣分自查表）。产出前逐项过其 §8 自查表（26 项），任一项未过即 `status=partial`。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 `draft.json`，也会写出**全部**产物与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M03/p28 定位符读原文，按需填 /app/work/draft.json（照抄 init 生成的骨架）
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`compare` 把「基线朴素策略 vs 本 Skill 结构化档案」的对照写到 `/app/work/compare_report.json`，
并在输出目录写出 `gain_report.json` 与 `gain_report.md`。

## 3. 产物

写入 `--output`：`result.json`、`dossiers.md`、`number_registry.json`、`family_graph.json`、
`family_graph.png`、`status_provenance.csv`、`license_gate.md`、`boundary_log.json`、
`evidence_map.json`、`change_log.json`、`coverage.json`、`self_check.json`、`gain_report.json`、
`gain_report.md`、`run_log.txt`，以及 `evidence/` 下每个来源一份原始证据快照。
`result.json` 的 `output_contract` 键**同时**出现在顶层与 `output_contract` 对象内，`case_id` 原样透传。

## 4. 契约键

默认键（当 `case.json` 未给 `output_contract` 时）：
`case_id, status, deliverable, evidence_map, change_log, coverage`。
若 `/input/case.json` 自带 `output_contract`，则**以它为准**逐键回填：指向产物的键解析为真实文件路径，
其余键给出真实派生值。`status ∈ {partial, insufficient_evidence, input_error}`。

## 5. 输入约定

- **案例**：`case.json`（`case_id`、`language`、`materials_root`、可选 `output_contract`）。
- **材料**：`materials/**` 任意文本/JSON。任务脚手架（`case.json`/`task.md`/`README`）会被索引但不作为可检索来源引用。
- 不可用文件（空/坏 JSON/占位文本/二进制）只记录 `parse_status`，永不引用。

## 6. 目录

```
SKILL.md                                  # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
scripts/main.py                           # CLI 入口：all / init / show / check / build / selfcheck / compare
scripts/kglib.py                          # 引擎：扫描 / 号码规范化 / 状态 / 许可 / 边界 / 证据 / 结果
scripts/render.py                         # io+渲染：token 规范化、安全写盘、标准库 PNG 图、markdown 渲染
environment/resources.yaml                # 资源入口声明：入口命令、路径、输入约定、契约、运行时
references/expert_playbook.md             # 专家参考手册：七步框架/授权分级/指标公式/事实边界/自查表（执行前必读）
references/innovation-evidence.md         # 创新证据：与通用 Agent / 商用库的差异与价值边界
references/query-templates.md             # 可复用检索式模板（号码式/主题式/申请人式/引证式/文献式）
references/license-checklist.md           # 可复用授权核验清单与绿黄红分级判据
examples/materials.md                     # 最小可复跑样例材料（编号/查询/状态/权利要求，虚构）
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

复跑样例：`python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work`。

## 7. 字段与口径（field contract）

| 字段 | 定义 | 口径/边界 |
|-|-|-|
| locator | `M#/p#`（来源 id + 行号） | 每条被引用的行**自带** locator；不可解析的来源不引用 |
| quote | 来源行的**逐字**引文 | 写入前过一次确定性 token 规范化（映射见 `scripts/render.py`） |
| norm | 号码规范化结果 | 规则链 `strip_separators → cc:* → kind:* → 位数判型 → inferred_country:*` |
| parse_status | `parsed / ambiguous / unparsed` | 无国别靠位数推断 → `ambiguous`，不冒充确定号码 |
| status_value | 法律状态 | 无官方登记页一律 `unknown`，不得推断为已授权/已失效 |
| source_kind | 状态来源分级 | `official_register / facsimile_ocr / observed_link / aggregator`；本包无登记页 → `not-declared` |
| tier | 许可分级 | `green / yellow / red`；许可未声明 → `yellow` 并进 `gaps` |
| boundary.type | 边界类型 | 见 `references/license-checklist.md` §3 与 SKILL §6 |

## 8. 基准用例与评分口径（benchmark + scoring，可复用）

- 本包的对照运行见 `SELFTEST.md`（四组 eval_sim 全部 PASS）与 `GAIN_EVIDENCE.md`（基线为**模拟**，非官方对照）。
- 评分维度映射（对应官方五维）：
  - 实际效果：`number_registry.json` + `status_provenance.csv` + `family_graph.json` + `evidence_map.json` +
    `dossiers.md` 覆盖号码/族/状态/文献/许可五问；每条带 locator 与逐字引文。
  - 使用增益：`gain_report.json`/`gain_report.md` 给出「基线朴素策略 vs 本 Skill」的可核验差；对照声明见 `GAIN_EVIDENCE.md`。
  - 创新增益：规则链号码规范化 + 状态三字段纪律 + 族口径显式化 + 许可闸门（见 `references/innovation-evidence.md`）。
  - 可靠体验：空/坏/占位材料诚实降级为 `insufficient_evidence`；异常恒 0 退出；`SELFTEST.md` 有稳定性证据。
  - 生态贡献：SKILL.md、检索式模板、许可核验清单、契约骨架齐全，可换成新案例复跑。

## 9. 方法与新增能力（innovation）

(a) **规则链号码规范化**：`strip_separators → cc:* → kind:* → 位数判型 → inferred_country:*`，每步写入 `rules`；
(b) **状态三字段纪律**：`as_of` + `source_kind` + `needs_official_verification` 强制存在，非官方来源恒 true；
(c) **族口径显式化**：只陈述观察到链接，`not_exhaustive` 恒记，关键词命中不等于同族；
(d) **许可绿黄红闸门**：许可未声明按 yellow，red 来源只登记不引用；
(e) **证据快照**：每个来源一份 `evidence/<id>.json`，每条结论可回看原文行。
**价值边界**：不做侵权/FTO/价值判断，不提供法律意见；同名或同关键词不等同同一族；未写明的关系方向不臆造。

## 10. 降级与诚实性

- 无可定位号码与可引用行 → `status=insufficient_evidence`；每个产物带结构化 no-data 记录并列出检索位置；exit 0。
- 坏 JSON / 空文件 / 占位文本 → 只记 `parse_status` 并写入对应 `evidence/<id>.json`，绝不引用。
- 无官方登记页 → 状态保持 `unknown`，绝不写成 granted 或 lapsed。
- 无网络、无时钟、无第三方依赖、不编造文献、号码或法律状态。

## 11. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟、结果确定性可复现。详见 `environment/resources.yaml`。
