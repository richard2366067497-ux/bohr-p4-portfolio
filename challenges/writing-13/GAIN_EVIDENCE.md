# GAIN_EVIDENCE — writing-13 / academic-writing-benchmark-builder（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**（本包 `examples/`）上的对照，
并把差异映射到官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。
所有「加载本 Skill」的数字均来自本包 `examples/` 的真实运行，命令见 §4 可逐字复现。

> **诚实声明**：本文「基线（无 Skill）」一行为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，
> 不代表任何官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线（无 Skill）

### 1.1 典型输出与缺口

同一输入 `examples/`（`materials/paper.md`，含方法段与结果段数值）下，一个未加载本 Skill 的基线
通常只写「一段泛泛的写作建议」或一段范例文本，典型缺口：

1. **无题面结构** —— 没有「六字段」题面（`input_material`/`instruction`/`word_limit`/
   `must_include_points`/`acceptable_variants`/`completion_criteria`），无法机械判分。
2. **无逐字要点 / 无定位** —— 要点不带 `quote` 与 `材料 + ¶定位`，不可回查。
3. **无可观察锚点** —— 没有 0/1/2 档锚点（数值保留、不新增数值、字数、小节顺序），评分不可复算。
4. **无多评一致性** —— 不产生双评分员分数、delta 与 Cohen's kappa。
5. **无校准** —— 无正控（参考答案须通过）/ 负控（删数字截断须被拒）。
6. **无契约回填 / 无复现记录** —— 不产出 `result.json`（契约键覆盖 0/5）与输入 sha1 复现步骤。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意，随包内嵌说明、不单独占文件）：同一 examples/ 输入，只写一段泛化建议。
from pathlib import Path
paper = Path("examples/materials/paper.md").read_text(encoding="utf-8")
(out := Path("baseline_out")).mkdir(exist_ok=True)
(out / "advice.md").write_text("Write clear methods and results sections.\n" + paper[:200],
                               encoding="utf-8")
# 无题面、无锚点、无 kappa、无校准、无契约
```

模拟结果：文件数 **1**、可判分题 **0**、锚点 **0**、kappa **N/A**、契约键覆盖 **0/5**、无复现记录。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=ok`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **16**（含 `result.json` 与 `reference_answers/T01..T03.md`） |
| 材料数 materials / 可用 usable | **1 / 1** |
| 生成的写作题 tasks | **3**（`summary` / `methods` / `results`，各六字段齐全） |
| 必需要点 points | **8**（逐条带逐字 `quote` + `材料¶定位`） |
| 要点核验 evidence_verified | **8/8** |
| 每题锚点 anchors | **≥5**（`contains_all`/`number_preserved`/`no_new_numbers`/`word_limit`/`section_order`，共 15 条） |
| 双评分数 scores | 3 题 × (rater_a, rater_b, delta=0, 覆盖 1.0/1.0) |
| 一致性 kappa | **1.0**（`consistency.kappa`） |
| 校准 controls | 3 组：正控 **通过**、负控 **被拒**（pos=2 / neg=0） |
| 自检 self_check | **pass**（C1–C10 全 PASS） |
| 契约键覆盖 | **5/5**（`case_id, deliverable, preserved_facts, evidence_map, change_log`） |
| 占位符扫描 | **0**（无 TODO / TBD / null / 待写 …） |

关键产物：`tasks.jsonl`、`reference_answers/T01..T03.md`、`anchors.md`、`scores.csv`、
`scores_detail.csv`、`evaluation_report.md`、`reproducibility.md`、`golden_standard.json`、
`diff_report.md`、`version_history.md`、`deliverable.md`、`self_check.json`、`result.json`
（顶层与 `output_contract` 同名键齐全，`case_id=example-writing-13` 透传）。

同一命令在较大输入（`synth_cases/writing-13/rich`）上实测：`tasks=3`、`points=12`、
`evidence_verified=12`、`kappa=1.0`、`self_check.pass=true`，口径与最小样例一致。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 题面可判分性 | 无结构建议 | 3 题 × 六字段齐全 | **实际效果** |
| 要点可核验 | 无 quote / 无定位 | 8/8 要点带逐字 quote + ¶定位 | **实际效果 / 可靠体验** |
| 评分可复算 | 无锚点 / 无分数 | 15 条 0/1/2 档锚点 + 双评分数与 delta | **创新增益 / 可靠体验** |
| 多评一致性 | 无 | Cohen's kappa=1.0 + 分歧登记 | **创新增益** |
| 校准防松 | 无 | 正控通过、负控被拒 | **可靠体验** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + `output_contract`） | **实际效果 / 生态贡献** |
| 可复用性 | 一次性建议 | 单命令 `run` + init/check/build，附复现记录 | **使用增益 / 生态贡献** |

**为什么这些差异对应 rubric**：实际效果靠「可判分题面 + 逐字要点」；使用增益靠「一条命令产出完整
benchmark 包」；创新增益靠「可观察锚点 + 双评 kappa + 正/负控校准」；可靠体验靠「要点核验 + 自检
C1–C10 + 离线确定性」；生态贡献靠「契约逐键回填 + `reproducibility.md` 复现记录 + 纯标准库离线」。

---

## 4 复现命令

```bash
# 在包根目录执行（示例用本机 python；平台为 python3）
python -X utf8 scripts/main.py run --input examples --output /tmp/w13out --work /tmp/w13work
# 期望：exit 0；/tmp/w13out 下 16 个文件；result.json.status=ok
#       summary="3 道题 / 8 条要点 / 双评 kappa=1.0 / 状态 ok"
#       coverage={materials:1, usable:1, tasks:3, points:8, evidence_verified:8}
#       controls 3 组正控通过/负控被拒；self_check.pass=true；契约 5/5
```

四格评测仿真（rich/boundary × single/agent，均 PASS）：

```bash
for c in rich boundary; do for m in single agent; do
  python -X utf8 scripts/eval_sim.py --pkg work/p4/v10/writing-13 \
    --case work/p4/synth_cases/writing-13/$c --mode $m
done; done
```
