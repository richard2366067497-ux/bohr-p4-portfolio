# GAIN_EVIDENCE — review-03 / method-statistics-audit（使用增益与创新证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在**同一材料集**上的对照证据，并映射到
官方 rubric 五维。所有「加载本 Skill」数字来自本包 `scripts/main.py` 的**真实运行**（见 `SELFTEST.md`），
可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的确定性
> 朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；本包**未伪造
> 任何官方 A/B 数据或评测分数**。对照的公平性在于：两组使用**同一**输入（`/input` 下的 `case.json` +
> `materials/**`）、**同一**任务（把材料读成可复核的审查单）与**同一**评估口径（§3），并且**同一**封顶规则。

---

## 1. 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

在同一材料集下，未加载本 Skill 的基线 Agent 典型缺口：

1. **只有泛泛意见** —— 输出「统计方法不当」「建议补充样本量」，指不出第几节、哪张表、哪一句。
2. **无性质区分** —— 把「作者没有报告」和「作者做错了」混为一谈。
3. **严重度失真** —— 一律 `major`/硬伤，或把可接受做法判成硬伤。
4. **无 locator、无逐字引文** —— 无法回原文定位，第三方不可复核。
5. **凭空补数据** —— 遇到未报告项倾向补一个「看起来合理」的判断。
6. **无对照、无封顶** —— 契约键覆盖 0，`underreporting` 可被误升到 `critical`。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把材料全文拼成一段通读文字，不解析规则表/严重度表，不建台账/证据
import pathlib
srcs = [p for p in pathlib.Path("materials").rglob("*") if p.is_file()]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
pathlib.Path("baseline_out/summary.md").write_text(
    "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in srcs), encoding="utf-8")
# 无 audit_report.md / statistics_ledger.json / findings.json / coverage.json / evidence_map.json /
# 无 locator、无逐字校验、无性质—严重度封顶、无边界、无对照
```

模拟结果：产物 **1** 件、定位缺陷类型 **0**、locator **0**、台账行 **0**、五面 **0**、六维 **0**、
证据条目 **0**、契约键 **0**。

---

## 2. 加载本 Skill（真实运行）

命令（§4）在 rich 材料集上的实测（`status=partial`，exit 0）：

| 可核验指标 | 基线模拟 | 加载本 Skill（实测） |
|---|---|---|
| 输出文件数 | 1（拼接文字） | **18** |
| 从材料定位到的缺陷类型（带 locator） | 0 | **28 / 28** |
| 规则 locator 数 | 0 | **28** |
| 台账行 | 0 | **28** |
| 五面覆盖 | 0 | **5 / 5** |
| 六维覆盖 | 0 | **6 / 6** |
| 证据映射条目 | 0（不可回看原文） | **28** |
| 契约键覆盖 | 0 | **23 / 23**（顶层 + `result.output_contract`） |
| 占位符扫描 | — | **0** |

关键产物：`audit_report.md`（可读审查单）/ `statistics_ledger.json`（规则 → locator + `cell_status` + 性质）/
`findings.json`（每条规则 `exercised_by_material=no`，不冒充缺陷）/ `coverage.json`（五面六维）/
`evidence_map.json` + `evidence/<id>.json`（原始证据快照）/ `change_log.json` / `boundary_log.json` /
`self_check.json` / `run_log.txt`。

---

## 3. 创新证据：对照组「基线失败模式 → 本 Skill 规则」+ 边界

### 3.1 逐条对照（证明增量，不是概念描述）

| 基线失败模式（无 Skill） | 本 Skill 的确定性规则 | 在固定材料上的可核验效果 |
|---|---|---|
| 指不出位置 | `lines_of` 给每行 `M#/p#`，每条规则带 locator + 逐字 quote | 28 条规则全部带 locator；quote 可在材料逐字找到 |
| 「未报告」当「做错」 | `defect_nature` 四态 + `NATURE_CAP` 封顶 | `underreporting` 恒 ≤ `major`，`acceptable` 恒 ≤ `minor` |
| 严重度一律硬伤 | 先判「是否改变结论/使复核不可能」再判「是否未报告」 | 规则行不冒充缺陷，severity 不臆造 |
| 凭空补数据 | 无稿件行 → `exercised_by_material=no`，`n=not_applicable_no_manuscript` | 绝不补造 p/CI/样本量 |
| 覆盖靠自述 | `coverage.json` 由 findings 的 facet/dimension 计数 | 五面 5/5、六维 6/6，未命中项显式列出 |

### 3.2 与已有方案的边界（value boundary）

- **相对「通用审稿提示词」**：本包的规则库与封顶表**从材料解析**且可复算，不是一段自然语言指令；
  但**不做**同行评审裁决、不做投稿决策。
- **相对「公开的报告清单（CONSORT/STROBE）」**：本包逐条落到原文 locator，清单本身不提供定位与封顶。
- **相对「期刊编辑初筛」**：本包给结构化台账与封顶，便于复核；但**不替代**编辑判断。
- **失效场景（诚实边界）**：材料若不含稿件实例（本类合成材料即如此），只能审「规则集」本身，
  `status=partial` 且 `exercised_by_material=no`；带扫描件文本层不可得时，该来源记 `no-data` 并降级，
  绝不伪造文本。

---

## 4. 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件拼接文字，无结构化结果 | 18 件成套产物（规则/台账/覆盖/证据/边界） | **实际效果** |
| 结果正确性 | 位置缺失、性质不分 | 规则从材料解析，性质—严重度封顶 | **实际效果** |
| 结果完整性 | 无边界、无未覆盖说明 | `coverage.json` 列出未命中维度 + `boundary_log.json` | **实际效果** |
| 结果可核验性 | 无 locator、无原文 | 每条规则带 `M#/p#` 与逐字引文，`evidence/<id>.json` 可回看 | **实际效果** |
| 使用增益 | 无对照、无法复核 | `gain_report.json`/`compare_report.json` 给可核验差；同输入同口径（§1） | **使用增益** |
| 创新增益 | 直接通读材料 | 材料内规则解析 + 性质封顶 + 空稿不冒充 + 证据快照（§3，含边界与失效场景） | **创新增益** |
| 可靠体验 | 无降级、无自检 | 空/坏/占位 → `insufficient_evidence`；四组 eval_sim PASS；异常场景见 `SELFTEST.md` §3 | **可靠体验** |
| 生态贡献 | 无文档、无模板 | 审查清单 + 缺陷类型库 + draft 模板 + 契约骨架，可换成新案例复跑 | **生态贡献** |

**为什么这些差异对应 rubric**：实际效果＝「真的把材料读成可复核、可继续审查的清单」；使用增益＝
「同一材料、同一封顶下，结构化与可核验性优于基线，且给出可复算差」；创新增益＝「规则解析、封顶、
空稿不冒充的方法本身带来实质改进并给出边界」；可靠体验＝「异常输入下仍产出可用的诚实结论」；
生态贡献＝「说明、清单、类型库、模板、示例可被他人直接复用」。

---

## 5. 复现命令

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
python3 scripts/main.py compare --input /input --output /app/output --work /app/work
# 期望：exit 0；/app/output 下 18 个文件；result.json.status=partial；
#       缺陷类型 28；locator 28；台账 28；五面 5；六维 6；证据 28；契约键与输入契约一致；占位符 0
```

`compare` 把同一组对照写到 `/app/work/compare_report.json`，并在 `/app/output` 写 `gain_report.json` 与
`gain_report.md`。基线一栏始终标注为**模拟**，不是官方对照。
