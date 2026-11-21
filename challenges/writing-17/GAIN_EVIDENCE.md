# GAIN_EVIDENCE — writing-17 / mindmap-builder（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**（本包 `examples/`）上的对照，
并把差异映射到官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。
所有「加载本 Skill」的数字均来自本包 `examples/` 的真实运行，命令见 §4 可逐字复现。

> **诚实声明**：本文「基线（无 Skill）」一行为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，
> 不代表任何官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线（无 Skill）

### 1.1 典型输出与缺口

同一输入 `examples/`（`materials/material.md`，带一/二级标题）下，一个未加载本 Skill 的基线通常
把材料**全文复制**或列一段平铺要点，典型缺口：

1. **无大纲 / 无图结构** —— 不推导 `root + branches`，不产出 `outline.json`，无 `nodes/edges`。
2. **无来源定位** —— 每个分支/叶子不带 `locator`（`M01#s3`），无法回查挂在哪一节。
3. **无结构化产物** —— 不产出可机读的 `mindmap.json` 与人读 `mindmap.md`。
4. **无契约回填** —— 不读 `case.json:output_contract`，不产出 `result.json`（契约键覆盖 0/13）。
5. **无确定性 / 无自检** —— 每次结果不同，无 `init/show/check/build/selfcheck` 阶段摘记与产物复检。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意，随包内嵌说明、不单独占文件）：同一 examples/ 输入，只做「全文平铺」。
from pathlib import Path
mat = Path("examples/materials/material.md").read_text(encoding="utf-8")
(out := Path("baseline_out")).mkdir(exist_ok=True)
(out / "mindmap.md").write_text(mat, encoding="utf-8")   # 无 root/分支/叶子，无 locator
# 无 mindmap.json、无 outline.json、无 result.json、无契约、无自检
```

模拟结果：文件数 **1**、分支 **0**、带定位节点 **0**、契约键覆盖 **0/13**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=built`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **5**（`result.json`、`mindmap.json`、`mindmap.md`、`outline.json`、`report.md`） |
| 扫描材料 scanned_materials / 小节 scanned_sections | **1 / 4** |
| 定位点 locators（`show`） | **4**（`M01#s1`…`M01#s4`） |
| outline 分支 branches | **4**（root + 3 个二级分支） |
| 节点 nodes / 边 edges | **9 / 8**（root + 4 分支 + 4 叶子） |
| check 结果 | `passed=true`，`issues=[]` |
| build 结果 | `nodes=9, edges=8, artifacts=[mindmap.json, mindmap.md, outline.json, report.md]` |
| selfcheck 结果 | `passed=true`，`fails=[]` |
| 契约键覆盖 | **13/13**（`init, show, check, build, selfcheck, mindmap, nodes, edges, outline, summary, report, case_id, status`） |
| 占位符扫描 | **0**（无 TODO / TBD / null / 待写 …） |

关键产物：`mindmap.json`（root/nodes/edges/case_id）、`mindmap.md`（人读导图，分支+叶子+来源）、
`outline.json`（根与分支大纲）、`report.md`（导图正文+局限）、`result.json`（顶层契约键 +
`output_contract` 逐键回填，`case_id=example-writing-17` 原样透传，`init/show/check/build/selfcheck`
五阶段各写入非空结构化 dict）。

同一命令在较大输入（`synth_cases/writing-17/rich`）上实测：**17 节点 / 16 条边**，
`status=built`，契约 13/13 齐全，口径与最小样例一致。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件全文，无 `result.json` | 5 件成套产物（JSON+MD+outline+report） | **实际效果 / 使用增益** |
| 图结构 | 无 root/分支/叶子 | root→4 分支→4 叶子，`nodes`/`edges` 显式 | **实际效果** |
| 来源可核验 | 无 locator | 每节带 `M01#sN` 定位，分支/叶子可回查 | **实际效果 / 可靠体验** |
| 契约回填 | 键覆盖 0/13 | 键覆盖 13/13（顶层 + `output_contract`） | **实际效果 / 生态贡献** |
| 阶段可审计 | 无 | `init/show/check/build/selfcheck` 五阶段摘记 | **创新增益 / 可靠体验** |
| 确定性与自检 | 无稳定产物、无自检 | 离线确定性；`selfcheck.passed=true` | **可靠体验** |
| 可复用性 | 一次性文本 | 单命令 `all` + 五命令分段入口 | **使用增益 / 生态贡献** |

**为什么这些差异对应 rubric**：实际效果靠「结构化导图 + 来源定位」；使用增益靠「一条命令产出全套
产物、Agent 可先 `init/show` 再写草稿」；创新增益靠「五阶段契约摘记 + 结构化 JSON 图」；可靠体验靠
「`check`/`selfcheck` 复检 + 空/坏输入仍 exit 0 + 离线确定性」；生态贡献靠「契约逐键回填 + 纯标准库」。

---

## 4 复现命令

```bash
# 在包根目录执行（示例用本机 python；平台为 python3）
python -X utf8 scripts/main.py all --input examples --output /tmp/w17out --work /tmp/w17work
# 期望：exit 0；/tmp/w17out 下 5 个文件；result.json.status=built
#       summary="9 nodes 8 edges from 1 material(s)"
#       init/show/check/build/selfcheck 均为含 stage/status 的非空 dict；check.passed=true
#       契约键 13/13 齐全；case_id=example-writing-17 透传
```

四格评测仿真（rich/boundary × single/agent，均 PASS）：

```bash
for c in rich boundary; do for m in single agent; do
  python -X utf8 scripts/eval_sim.py --pkg work/p4/v10/writing-17 \
    --case work/p4/synth_cases/writing-17/$c --mode $m
done; done
```
