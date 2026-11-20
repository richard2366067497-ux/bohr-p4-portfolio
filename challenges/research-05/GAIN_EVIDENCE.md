# GAIN_EVIDENCE — research-05 / research-topic-innovation-eval（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一材料上的对照证据，并映射到官方 rubric
五维。所有「加载本 Skill」的数字来自本包 **rich 用例的真实运行**（3 次复跑一致，见 `SELFTEST.md`），可逐步复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**：由随包文档描述的确定性朴素策略
> （§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；本包**未伪造任何官方 A/B 数据**。
> 对照的公平性在于：两组使用**同一**输入（`work/p4/synth_cases/research-05/rich` 的两份材料）、**同一**任务
> （把材料读成可复核的五门判定）与**同一**评估口径（§3）。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

同一份材料（一份 `gate-rules.md` 规则文档 + 一份 `draft-schema.md` 字段字典）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **散文而非判定** —— 输出「该怎么做选题评估」的概览文字，没有 G1–G5 记分卡。
2. **无定位** —— 规则与阈值不标 `M#/p#`，不可复核。
3. **阈值不落地** —— 说「要判断可行性」，但不把每门的 `go/conditional/no_go` 充分条件逐行列出。
4. **矛盾证据被抹平** —— 「检索不到能不能当新颖」这类两处写法不一致的规则，被当成一句话带过。
5. **前提无状态** —— 可行性前提不区分 `source`/`assumed`/`unsupported`，也不会因 `unsupported` 而降级。
6. **无契约回填** —— 不产出 `result.json`，契约键覆盖 0/6。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把两份材料拼成一段通读文字，不建门、不定位、不查询
import json, pathlib
root = pathlib.Path("work/p4/synth_cases/research-05/rich/materials")
text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.glob("*.md")))
pathlib.Path("baseline_out").mkdir(exist_ok=True)
pathlib.Path("baseline_out/summary.md").write_text("材料概要：\n" + text + "\n", encoding="utf-8")
# 无 result.json / gate_scorecard.json / decision_brief.md / prior_art_alignment_matrix.csv /
# assumption_register.json / evidence_index.jsonl / conflicts.json：无门、无 locator、无阈值的逐行落地、无冲突登记
```

模拟结果：产物 **1** 件、门 **0**、locator 证据 **0**、阈值落地 **0**、冲突 **0**、前提状态 **0**、契约键 **0/6**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 rich 用例上的实测（`status=ok`，exit 0）：

| 可核验指标 | 基线模拟 | 加载本 Skill（实测） |
|---|---|---|
| 输出文件数 | 1（拼接文字） | **15** |
| 五门定义（逐门带 locator + 原文行） | 0 | **5**（M4/p12–p16） |
| 逐门阈值行落地 | 0 | **5**（go / conditional / no_go 三列逐行读出） |
| 抽取的错误码 / 警告码 / 枚举 | 0 / 0 / 0 | **33 / 15 / 6** |
| 抽取的评分维度行 | 0 | **18** |
| 证据条目（全部带 locator + 逐字引文） | 0 | **23** |
| 逐字命中率 | 不适用 | **1.0000**（23/23，零未命中） |
| 对齐矩阵长表行 | 0 | **5**（一行一主张，不可比给原因） |
| 可行性前提登记（含劝退条件） | 0 | **4**（4 类：data/compute/experiment/people；source 2 / assumed 1 / unsupported 1） |
| 冲突登记（支持侧+反证侧各带原话） | 0（被并成一句） | **1**（M3/p98 ↔ M4/p77） |
| 对象表消解 | 0 | 4 条记录，2 条未解析如实列出 |
| 契约键覆盖 | 0/6 | **6/6**（顶层 + `result.output_contract`） |
| 占位符扫描 | — | **0** |
| `result.json` 规范化哈希 | — | `sha256=aded3dea13857d49` |

关键产物：`decision_brief.md`（四交付↔五门 + 逐门条件 + 附录 A–C）/ `gate_scorecard.json`（每门 verdict、
conditions、evidence_ids、残余风险、pivot、规则与阈值原话）/ `prior_art_alignment_matrix.csv`（长表）/
`assumption_register.json`（kill criteria）/ `evidence_index.jsonl`（逐行可复核）/ `conflicts.json`（两侧原话 + 取舍）/
`coverage.json`（六类覆盖统计）/ `search_log.json`（检索式与筛选标准，含命中位置）/ `uncertainty.json`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件拼接文字 | 15 件成套产物，五门全覆盖 + 四交付映射 + 六类覆盖统计 | **实际效果** |
| 结果正确性 | 规则靠印象复述 | 阈值逐行读出并落到每门；矛盾证据两侧原话并存；`E_G3_GO`/`E_DECISION_INCONSISTENT` 拦截自相矛盾 | **实际效果** |
| 结果完整性 | 无缺口、无降级说明 | 附录 A–C 显式列出未命中引文、降级与不确定性；`status` 不掩盖 | **实际效果** |
| 结果可核验性 | 无 locator、无引文 | 每条规则/证据带 `M#/p#` + 逐字引文，命中率 1.0，`evidence_index.jsonl` 逐行复核 | **实际效果** |
| 使用增益 | 无对照、无法复核 | `gain_evidence.json` + `compare_report.json` 给「基线文字 vs 结构化判定」的可复算差；同输入同口径（§1） | **使用增益** |
| 创新增益 | 直接通读材料 | 五门记分卡 + 长表矩阵 + assumption register（kill criteria）+ 反证强制登记 + 对象表消解（README §9，含价值边界） | **创新增益** |
| 可靠体验 | 无降级、无自检 | 空/坏/占位 → `insufficient_evidence`；未命中引文记原因；四组 eval_sim PASS | **可靠体验** |
| 生态贡献 | 无文档、无模板 | README/SELFTEST + 锚点表 + 基准协议 + 模板文件（含两份骨架）+ 内联示例，换材料即可复跑 | **生态贡献** |

**为什么这些差异对应 rubric**：实际效果＝「真的把材料读成可复核、可继续评审的判定」；使用增益＝「同一材料、
同一口径下，结构化与可核验性优于基线，且给出可复算差」；创新增益＝「规则即证据、自相矛盾拦截、反证强制登记
这些方法本身带来实质改进并给出边界」；可靠体验＝「异常输入下仍产出可用的诚实结论」；生态贡献＝「说明、模板、
示例可被他人直接复用」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input work/p4/synth_cases/research-05/rich --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 15 个文件；result.json.status=ok；
#       门 5；证据 23（命中率 1.0）；矩阵 5 行；前提 4（4 类）；冲突 1；ERROR 0
python3 scripts/main.py all --input work/p4/synth_cases/research-05/boundary --output /tmp/outb --work /tmp/workb
# 期望：exit 0；status=insufficient_evidence；15 个文件；每个产物带 no-data 记录与检索位置
```

规范化哈希复算：读 `/tmp/out/result.json`，删除环境相关键 `runtime` 与 `artifacts` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`aded3dea13857d49`。
