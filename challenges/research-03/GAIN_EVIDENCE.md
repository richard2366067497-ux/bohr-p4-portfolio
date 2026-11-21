# GAIN_EVIDENCE — research-03 / systematic-review（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` 固定 criteria 关键词 `perovskite/stability/additive/degradation`，加
`materials/records.md` 的 6 条题录）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **无 PRISMA 计数** —— 只给「筛出 3 篇相关文献」这类叙述，不给 `identified/screened/excluded/
   full_text_assessed/included/unresolved/not_screened` 的分阶段计数与别名。
2. **无契约回填** —— 不产出 `result.json`，`output_contract` 键覆盖 0。
3. **无逐题台账** —— 不给每题一条的 `ta_decision/full_text` 与理由，无法对账。
4. **无五维评价结构** —— 评价只写一句「质量较高」，无 `assessed/status/note`，无依据位置。
5. **无诚实降级** —— 空/坏输入直接报错或臆造纳入研究；无 `degradations` / `uncertainties` / `limits`。
6. **无确定性** —— 每次「相关文献」清单漂移，无稳定计数与可复算摘要。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：只按关键词数一句「相关 / 不相关」，不计分阶段计数、不写契约、不做台账
import json, re, pathlib
text = pathlib.Path("examples/materials/records.md").read_text(encoding="utf-8")
kws = ["perovskite", "stability", "additive", "degradation"]
hits = [ln for ln in text.splitlines() if sum(k in ln.lower() for k in kws) >= 2]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "advice.md").write_text(
    "相关文献约 %d 篇，建议纳入。\n" % len(hits), encoding="utf-8")
# 无 result.json、无 prisma_flow.json、无 screening_ledger.jsonl、无 appraisal.json、无 criteria.json
```

模拟结果：产物 **1** 件、PRISMA 计数 **0**、逐题台账 **0**、五维评价 **0**、契约键 **0**。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（exit 0，`status=screened`）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **6**（result.json / prisma_flow.json / screening_ledger.jsonl / appraisal.json / criteria.json / report.md） |
| 识别题录 `identified` | **6**（`M01#r1` … `M01#r6`，每条带 locator、year、doi） |
| 题录筛选 `screened_title_abstract` | **6**；`excluded_title_abstract` **2** |
| 全文评估 `full_text_assessed` | **4**；`excluded_full_text` **1** |
| 纳入 `included` / `include` | **3** / **3** |
| 待定 `unresolved` | **1**（题录阶段 uncertain，全文不可解析保守排除） |
| 排除合计 `excluded` | **3**；`not_screened` **0** |
| 排除原因 `excluded_by_reason` | **2** 类（`title_abstract: no criteria keyword` 2、`full_text: not resolvable in snapshot` 1） |
| 逐题台账 `screening_ledger.jsonl` | **6** 行（每行 rid + locator + ta_decision + full_text + 理由） |
| 五维评价 `appraisal.json` | **5** 维（design_fit / risk_of_bias / sample_or_data_adequacy / reporting_completeness / directness），每维非空 dict |
| 契约键覆盖 | **25/25**（case 的 17 键 + 内置规范 8 键，顶层与 `result.output_contract` 各回填一份） |
| `summary` | `identified 6, included 3, excluded 3, unresolved 1` |
| 占位符扫描 | **0**（文本产物经清洗写出） |
| 规范化摘要 | `sha256=1c9e3ad7123467ce`（对 `result.json` 去掉 `runtime`/`change_records`/`outputs` 后 `sort_keys` 序列化） |

关键产物：`prisma_flow.json`（分阶段计数与别名）、`screening_ledger.jsonl`（逐题台账）、
`appraisal.json`（五维非空结构）、`criteria.json`（标准与关键词）、`report.md`（人读报告）、
`result.json`（契约逐键回填 + counts + limits + uncertainties + change_records）。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件定性建议，无 `result.json` | 6 件成套产物（流程/台账/评价/标准/报告/契约） | **完成度 / 完整性** |
| 计数正确性 | 「约 3 篇相关」，无分阶段计数 | PRISMA 计数自洽：6 → 6 → (2 排除) → 4 → (1 排除) → 3 纳入 | **正确性** |
| 证据可核验 | 无 locator、无逐题理由 | 6 条台账均带 `M01#rN` locator 与理由 | **可核验性** |
| 契约回填 | 键覆盖 0 | 键覆盖 25/25（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 可能臆造纳入清单 | 计数全部由快照派生；缺失项如实记 `degradations` / `limits` | **正确性 / 可靠性** |
| 确定性与自检 | 每次清单漂移 | 规范化摘要稳定、`selfcheck` 全项通过 | **可靠性** |

**为什么对应 rubric**：完成度＝成套产物 + 契约回填；正确性＝阶段计数自洽 + 逐题理由与条款对应；
完整性＝流程/台账/评价/标准/报告；可核验性＝locator + 逐题理由 + 可复算计数；使用增益＝同输入下
多维同时提升。

---

## 4 复现命令

```bash
# 最小样例（本包 examples/）
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；6 件产物；status=screened；identified=6, included=3, excluded=3, unresolved=1；
# full_text_assessed=4, excluded_full_text=1；契约键 25/25；占位符 0

# 平台合成用例（rich / boundary × single / agent）
python scripts/eval_sim.py --pkg work/p4/v10/research-03 \
  --case work/p4/synth_cases/research-03/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/research-03 \
  --case work/p4/synth_cases/research-03/boundary --mode agent
```

摘要复算：读 `/tmp/out/result.json`，去掉 `runtime`/`change_records`/`outputs` 三键后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`1c9e3ad7123467ce`。
