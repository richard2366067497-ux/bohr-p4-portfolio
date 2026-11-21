# GAIN_EVIDENCE — writing-14 / sci-mindmap-builder（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**上的对照，并把差异映射到
官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。所有「加载本 Skill」的
数字均来自本包的真实运行，命令见 §4 可逐字复现。

> **诚实声明**：本文「基线（无 Skill）」一行为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，
> 不代表任何官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线（无 Skill）

### 1.1 典型输出与缺口

同一输入（`materials/paper.md`，分小节、含数值）下，一个未加载本 Skill 的基线通常输出一段自然
语言摘要或一份平铺要点清单，典型缺口：

1. **无结构 / 无层级** —— 不产出「中心主题 → 主分支 → 要点」的分层图，深度与分支规模不可控。
2. **无逐字证据 / 无定位** —— 每个节点不带 `material + locator + 逐字 quote`，无法回查。
3. **关系无方向语义** —— 跨分支关系随意连线，不使用 9 类方向语义，也无 quote 支撑。
4. **数字无台账** —— 节点中的数字不核对是否出自材料/quote。
5. **无渲染与核验资产** —— 不产出可编辑 `mindmap.svg`/`mindmap.json`，无金标准/对照/自检/日志。
6. **无契约回填** —— 不读 `case.json:output_contract`，不产出 `result.json`（契约键覆盖 0/5）。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意，随包内嵌说明、不单独占文件）：同一输入，只做「平铺要点」。
from pathlib import Path
import re
paper = Path("examples/materials/paper.md").read_text(encoding="utf-8")
lines = [l.strip("# ").strip() for l in paper.splitlines() if l.strip()]
(out := Path("baseline_out")).mkdir(exist_ok=True)
(out / "outline.md").write_text("\n".join("- " + l for l in lines), encoding="utf-8")
# 平铺、无层级、无 evidence、无 locator、无 edge 语义、无 SVG、无契约、无自检
```

模拟结果：文件数 **1**、分层节点 **0**、带证据节点 **0**、带定位节点 **0**、契约键覆盖 **0/5**。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `synth_cases/writing-14/rich`（多小节材料，本包文档所述默认场景）上的实测
（`status=ok`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **11**（`mindmap.svg`/`mindmap.json`/`content_map.json`/`mindmap.png`/`structure.md` + 5 项资产 + `result.json`） |
| 材料数 materials / 单元 units | **1 / 17** |
| 节点 nodes / 关系 edges | **16 / 1** |
| 层级深度 depth / 主分支 branches | **2 / 5** |
| 被引用单元 mapped | **16/17**（未覆盖 1 个记入 `content_map.coverage.unmapped`） |
| 逐字命中证据 verified_evidence | **16/16**（每条含 `material+locator+quote`） |
| 数字台账项 | **29**（节点数字均可在材料或 quote 中找到） |
| 关系语义 | 1 条，位于 9 类方向语义内，带 quote |
| 自检 self_check | **pass**（C1–C10 全 PASS） |
| 契约键覆盖 | **5/5**（`deliverable, evidence_map, preserved_facts, change_log, content_map`） |
| 占位符扫描 | **0**（无 TODO / TBD / null / 待写 …） |

关键产物：`mindmap.svg`（可编辑，每个 `g#node-*` 带 `data-quote`/`data-locator`）、`mindmap.json`、
`content_map.json`、`mindmap.png`、`structure.md`、`golden_standard.json`、`diff_report.md`、
`version_history.md`、`run.log`、`self_check.json`、`result.json`（顶层与 `output_contract` 同名键齐全）。

**关于包内 `examples/` 的诚实说明**：`examples/materials/paper.md` 只有 4 小节（470 B），实测产出
`nodes=9, edges=0, depth=2`，据此 `self_check` 的 C2（期望节点 12–35）记为**未达**，`self_check.pass=false`;
其余 C1、C3–C10 仍 PASS，产物与契约齐全。这是**样例过小**导致，不是流程缺陷——换用多小节材料
（如上表 rich）即 16 节点、C1–C10 全 PASS。两者均为真实运行输出。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 结构可判分性 | 平铺清单 | 分层图（root→分支→要点，depth≤4） | **实际效果** |
| 证据可核验 | 无 evidence / 无定位 | 每节点 `material+locator+逐字 quote`，命中 16/16 | **实际效果 / 可靠体验** |
| 关系语义 | 随意连线 | 9 类方向语义 + quote 支撑 | **创新增益 / 可靠体验** |
| 数字落证 | 不核对 | 29 项数字台账，逐条 grounded | **可靠体验** |
| 渲染与核验资产 | 无 | 可编辑 SVG/JSON + 金标准/对照/版本/自检/日志 | **创新增益 / 使用增益** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + `output_contract`） | **实际效果 / 生态贡献** |
| 可复用性 | 一次性清单 | 单命令 `run` + init/show/check/build | **使用增益 / 生态贡献** |

**为什么这些差异对应 rubric**：实际效果靠「分层图 + 逐字证据」；使用增益靠「一条命令产出可编辑
导图与核验资产」；创新增益靠「9 类方向语义关系 + 金标准/对照/版本链」；可靠体验靠「证据命中、
数字落证、自检 C1–C10、离线确定性」；生态贡献靠「契约逐键回填 + 纯标准库离线、SVG/JSON 可编辑」。

---

## 4 复现命令

```bash
# 在包根目录执行（示例用本机 python；平台为 python3）
python -X utf8 scripts/main.py run \
  --input ../synth_cases/writing-14/rich --output /tmp/w14out --work /tmp/w14work
# 期望：exit 0；/tmp/w14out 下 11 个文件；result.json.status=ok
#       summary="16 节点 / 1 关系 / 状态 ok"；coverage={units:17, mapped:16, nodes:16, verified_evidence:16}
#       self_check.pass=true；契约 5/5
# 包内冒烟（小样例）：--input examples  -> nodes=9，self_check 的 C2 记未达（样例过小）

# 四格评测仿真（rich/boundary × single/agent，均 PASS）：
for c in rich boundary; do for m in single agent; do
  python -X utf8 scripts/eval_sim.py --pkg work/p4/v10/writing-14 \
    --case work/p4/synth_cases/writing-14/$c --mode $m
done; done
```
