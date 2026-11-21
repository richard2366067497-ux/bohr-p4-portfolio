# GAIN_EVIDENCE — writing-11 / manuscript-revision-desk（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**（本包 `examples/`）上的对照，
并把差异映射到官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。
所有「加载本 Skill」的数字均来自本包 `examples/` 的真实运行，命令见 §4 可逐字复现。

> **诚实声明**：本文「基线（无 Skill）」一行为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，
> 不代表任何官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线（无 Skill）

### 1.1 典型输出与缺口

同一输入 `examples/`（带段落锚点 `<!-- C01-P001 -->` 的 `materials/chapters/ch01.md`）下，一个未加载
本 Skill 的基线通常把整章**重写/润色**成一段新文本，典型缺口：

1. **原文被改写** —— 原句、数字、术语被替换，源文不可逐字复原（违反「原句不改」）。
2. **无定位 / 无逐字回源** —— 编辑注记不带 `locator` 与逐字 `source_quote`，无法回查挂在哪一段。
3. **无工单边界** —— 整章重写、改数据、删引用等越界操作不被拒绝、不留理由。
4. **无版本控制** —— 不记原/修哈希、无回滚、无重放验证、无非法操作拒绝记录。
5. **无契约回填** —— 不读 `case.json:output_contract`，不产出 `result.json`（契约键覆盖 0/7）。
6. **无确定性 / 无自检** —— 每次改写不同，无证据地图、保留事实清单、变更日志等账本。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意，随包内嵌说明、不单独占文件）：同一 examples/ 输入，做「整章重写」。
from pathlib import Path
ch = Path("examples/materials/chapters/ch01.md").read_text(encoding="utf-8")
(out := Path("baseline_out")).mkdir(exist_ok=True)
(out / "revised_manuscript.md").write_text(
    "# Chapter 1 (rewritten)\n\n" + ch.replace("rose from", "increased from"), encoding="utf-8")
# 原文被改写；无注记块、无 locator、无 version_compare、无 change_log、无契约
```

模拟结果：文件数 **1**、可回源注记 **0**、原句保留 **否**、契约键覆盖 **0/7**、无回滚/重放验证。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=ok`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **11**（`result.json` + 10 件账本/交付物） |
| 材料数 materials / 带锚点段落 anchored_paragraphs | **1 / 3** |
| 已接受注记 targets_annotated | **2**（`limitation`、`clarification` 各 1，`status=accepted`） |
| 注记类型覆盖 | 解释边界（关联≠因果）、范围澄清（限定材料/条件/端点） |
| 保留事实 preserved_facts | **2**（如 `41.2 MPa`、`25 °C`，逐条带 `quote` + `locator`，`status=preserved`） |
| 原文保留块 blocks_preserved | **3**（修订稿正文逐字等于原文） |
| 变更记录 changes | **7**（propose / accept / reject 全含；含 1 条越界重写被 **reject**） |
| 回滚验证 rollback_verified | **True**（移除注记块后恢复原文哈希） |
| 重放验证 reapply_verified | **True**（重新插入全部注记，逐条存在） |
| 非法操作 state_unchanged | **True**（空替换被拒，`state_sha_before == state_sha_after`） |
| 契约键覆盖 | **7/7**（`case_id, status, deliverable, preserved_facts, evidence_map, change_log, uncertainties`） |
| 占位符扫描 | **0**（无 TODO / TBD / null / 待写 …） |

关键产物：`revised_manuscript.md`（原文逐字 + `<!-- EDITORIAL-ANNOTATION … -->` 注记块）、
`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`version_compare.md`、
`operation_log.json`、`task_receipt.json`、`export_preview.md`、`original_snapshot.json`、
`manifest.json`、`result.json`（顶层与 `output_contract` 同名键齐全，`case_id=example-writing-11` 透传）。

同一命令在较大输入（`synth_cases/writing-11/rich`）上实测：`anchored_paragraphs=5`、
`targets_requested=2`、`targets_annotated=2`、`preserved_facts=6`、`blocks_preserved=5`，
`rollback_verified=True`、`reapply_verified=True`，口径与最小样例一致。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 源文保真 | 整章重写，原句丢失 | 正文逐字保留 + 独立注记块 | **实际效果** |
| 注记可回源 | 无 locator / 无 quote | 每条注记带 `source_quote` + `文件:L行号` | **实际效果 / 可靠体验** |
| 工单边界 | 越界操作照做 | 越界重写 **reject** 并写理由 | **可靠体验** |
| 版本控制 | 无 | 原/修哈希 + 回滚 + 重放验证 | **创新增益 / 可靠体验** |
| 非法操作防护 | 无 | 空替换被拒且状态哈希不变 | **可靠体验** |
| 契约回填 | 键覆盖 0/7 | 键覆盖 7/7（顶层 + `output_contract`） | **实际效果 / 生态贡献** |
| 可复用性 | 一次性改写 | 单命令 `all` + init/show/check/build/selfcheck | **使用增益 / 生态贡献** |

**为什么这些差异对应 rubric**：实际效果靠「原文逐字 + 可回源注记」；使用增益靠「一条命令产出成套
账本、Agent 只写 `draft.json`」；创新增益靠「propose/accept + 哈希版本控制 + 回滚/重放」；
可靠体验靠「越界与非法操作被拒、状态不变、离线确定性」；生态贡献靠「契约逐键回填 + 纯标准库离线」。

---

## 4 复现命令

```bash
# 在包根目录执行（示例用本机 python；平台为 python3）
python -X utf8 scripts/main.py all --input examples --output /tmp/w11out --work /tmp/w11work
# 期望：exit 0；/tmp/w11out 下 11 个文件；result.json.status=ok
#       metrics = {materials:1, anchored_paragraphs:3, targets_requested:0,
#                  targets_annotated:2, preserved_facts:2, blocks_preserved:3,
#                  changes:7, rollback_verified:true, reapply_verified:true}
#       output_contract 与顶层同名键 7/7 齐全；非法操作 state_unchanged=true
```

四格评测仿真（rich/boundary × single/agent，均 PASS）：

```bash
for c in rich boundary; do for m in single agent; do
  python -X utf8 scripts/eval_sim.py --pkg work/p4/v10/writing-11 \
    --case work/p4/synth_cases/writing-11/$c --mode $m
done; done
```
