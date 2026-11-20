# GAIN_EVIDENCE — search-11 / patent-search-dossier（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在**同一材料集**上的对照证据，并映射到官方
rubric 五维。所有「加载本 Skill」数字来自本包 `scripts/main.py` 的**真实运行**（见 `SELFTEST.md`），可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的确定性
> 朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；本包**未伪造任何
> 官方 A/B 数据或评测分数**。对照的公平性在于：两组使用**同一**输入（`/input` 下的 `case.json` + `materials/**`）、
> **同一**任务（把材料读成可复核的检索档案）与**同一**评估口径（§3），并且**同一**许可闸门。

---

## 1. 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

在同一材料集下，未加载本 Skill 的基线 Agent 典型缺口：

1. **散文而非档案** —— 输出「材料讲了号码规范和状态分级」这类总结，没有号码表、没有 locator。
2. **号码不规范化** —— 直接把 `US 2017/0123456 A1` 当授权号陈述，混淆公开号与授权号。
3. **状态不可复核** —— 用聚合站/转载页当法律状态依据，或自行推断「已授权」。
4. **同名/同关键词即同族** —— 把关键词命中的不同号码并成一族，不记 `not_exhaustive`。
5. **无许可闸门** —— 许可未声明也照抄长段原文，风险不可控。
6. **无对照、无证据快照** —— 每条结论不可回看原文行，契约键覆盖 0/6。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把材料全文拼成一段通读文字，不建号码表/状态表/证据，不查询
import pathlib
srcs = [p for p in pathlib.Path("materials").rglob("*") if p.is_file()]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
pathlib.Path("baseline_out/summary.md").write_text("\n".join(p.read_text(encoding="utf-8", errors="replace") for p in srcs), encoding="utf-8")
# 无 number_registry.json / status_provenance.csv / boundary_log.json / evidence_map.json / family_graph.png / result.json，
# 无 locator、无逐字校验、无许可分级、无边界、无对照
```

模拟结果：产物 **1** 件、规范化号码 **0**、locator **0**、状态行 **0**、许可行 **0**、边界 **0**、
证据条目 **0**、渲染图 **0**、契约键 **0/6**。

---

## 2. 加载本 Skill（真实运行）

命令（§4）在 rich 材料集上的实测（`status=partial`，exit 0）：

| 可核验指标 | 基线模拟 | 加载本 Skill（实测） |
|---|---|---|
| 输出文件数 | 1（拼接文字） | **19** |
| 规范化号码（带规则链） | 0 | **12** |
| locator（号码 → 出处行） | 0 | **29** |
| 状态 provenance 行 | 0 | **12**（全部 `unknown` + `needs_official_verification`） |
| 许可分级行 | 0 | **4**（全部 `yellow`） |
| 边界条目 | 0 | **7** |
| 证据映射条目 | 0（不可回看原文） | **17** |
| 渲染族图 | 不支持 | **1**（`family_graph.png`） |
| 契约键覆盖 | 0/6 | **6/6**（顶层 + `result.output_contract`） |
| 占位符扫描 | — | **0** |

关键产物：`dossiers.md`（可读档案）/ `number_registry.json`（号码 + `rules[]` 规则链 + locator）/
`status_provenance.csv`（状态三字段纪律）/ `family_graph.json` + `family_graph.png`（族图 + 渲染图）/
`license_gate.md`（绿黄红分级与降级方案）/ `boundary_log.json`（边界与缺口）/ `evidence_map.json` +
`evidence/<id>.json`（原始返回快照）/ `change_log.json` / `coverage.json` / `self_check.json` / `run_log.txt`。

---

## 3. 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件拼接文字，无结构化结果 | 19 件成套产物（号码/状态/族/许可/边界/证据/图） | **实际效果** |
| 结果正确性 | 号码不规范化、状态靠推断 | 规则链规范化，状态全 `unknown` 且带三字段纪律 | **实际效果** |
| 结果完整性 | 无边界、无缺口说明 | 7 条边界 + `gaps` + `coverage.facets` 如实说明未覆盖面 | **实际效果** |
| 结果可核验性 | 无 locator、无原文 | 每条结论带 `M#/p#` 与逐字引文，`evidence/<id>.json` 可回看 | **实际效果** |
| 使用增益 | 无对照、无法复核 | `gain_report.json`/`compare_report.json` 给「基线文字 vs 结构化档案」的可核验差；同输入同口径（§1） | **使用增益** |
| 创新增益 | 直接通读材料 | 规则链规范化 + 状态三字段 + 族口径显式化 + 许可闸门（`references/innovation-evidence.md`，含价值边界） | **创新增益** |
| 可靠体验 | 无降级、无自检 | 空/坏/占位 → `insufficient_evidence`；四组 eval_sim PASS | **可靠体验** |
| 生态贡献 | 无文档、无模板 | 检索式模板 + 许可核验清单 + 契约骨架 + 字段口径，可换成新案例复跑 | **生态贡献** |

**为什么这些差异对应 rubric**：实际效果＝「真的把材料读成可复核、可继续检索的档案」；使用增益＝
「同一材料、同一口径下，结构化与可核验性优于基线，且给出可复算差」；创新增益＝「规则链规范化、状态三字段、
许可闸门的方法本身带来实质改进并给出边界」；可靠体验＝「异常输入下仍产出可用的诚实结论」；
生态贡献＝「说明、模板、清单、示例可被他人直接复用」。

---

## 4. 复现命令

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
python3 scripts/main.py compare --input /input --output /app/output --work /app/work
# 期望：exit 0；/app/output 下 19 个文件；result.json.status=partial；
#       号码 12；locator 29；状态行 12；许可行 4；边界 7；证据 17；契约 6/6；占位符 0
```

`compare` 把同一组对照写到 `/app/work/compare_report.json`，并在 `/app/output` 写 `gain_report.json` 与
`gain_report.md`。基线一栏始终标注为**模拟**，不是官方对照。
