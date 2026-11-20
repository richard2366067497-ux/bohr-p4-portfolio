# GAIN_EVIDENCE — research-02 / lit-review-workbench（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小语料上的对照证据，并映射到
官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（4 条记录，含 1 条重复、1 条无摘要；研究问题见 `case.json`）下，未加载本 Skill 的
基线 Agent 典型缺口：

1. **无纳排记录** —— 不产出 `screening_log`，重复/仅摘要/低相关记录与正式记录混在一起。
2. **无定位 / 无逐字引文** —— 不给 `locator`（如 `M02/records[0]`）与原文逐字 `quote`。
3. **无契约回填** —— 不产出 `result.json`，契约键覆盖 0/9。
4. **易幻觉** —— 可能为凑数把重复记录写成"两篇独立证据"，或编造相关性结论。
5. **主题靠模板** —— 套用"背景/方法/挑战/展望"，与该批语料实际分布无关。
6. **无自检** —— 无逐字命中核验，无法回答"这条引文真的在原文里吗"。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把每条记录的摘要连成一段，不纳排、不定位、不建证据表
import json, pathlib
recs = json.loads(pathlib.Path("examples/params.json").read_text(encoding="utf-8"))["records"]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "summary.md").write_text(
    "综述：\n" + "\n".join("- " + r["title"] for r in recs) + "\n", encoding="utf-8")
# 无 screening_log、无 evidence_matrix、无 coverage_report、无 audit_report、无 result.json
```

模拟结果：产物 **1** 件、纳排决策 **0**、逐字证据 **0**、契约键 **0/9**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=answered`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **8** |
| 候选记录 `records` | **4** |
| 纳排结果 | **included R001,R002；excluded 2**（R003 `repeated`、R004 `abstract-only`） |
| 主题 slot | **2/2 填满**（`filled_ratio = 1.0`） |
| 逐字证据 `evidence_stats` | total **2** / verbatim_hits **2** / hit_rate **1.0** |
| 契约键覆盖 | **9/9**（顶层 + `result.output_contract`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=4639b0010043bfbe`（剔除 `runtime`） |

关键产物：`draft.md`（带 `[record, source, locator, strength]` 的引用草稿）/
`evidence_matrix.json`（逐字 quote + 命中统计）/ `screening_log.csv`（decision+flag+reason）/
`coverage_report.json` / `conflicts_and_gaps.md` / `audit_report.md`（回链核验）/ `run_log.txt`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件拼接摘要，无 `result.json` | 8 件成套产物（纳排/证据/覆盖/自检） | **完成度 / 完整性** |
| 筛选一致性 | 重复与正式记录混同 | 逐条 decision + flag + reason，重复被剔 | **正确性 / 可靠性** |
| 证据可核验 | 无 locator / 无 quote | 逐字 quote + locator，命中率 1.0，selfcheck 回链 | **可核验性** |
| 主题归纳 | 套用背景/方法/挑战/展望 | 从语料频次长出 slot，附 `outline_basis` | **创新增益 / 方法改进** |
| 契约回填 | 键覆盖 0/9 | 键覆盖 9/9（顶层 + `output_contract`） | **完成度** |
| 抗幻觉 | 可能编造证据 | 无记录即 no-data，引文不命中标 `verbatim=False` | **正确性 / 可靠性** |

**为什么这些差异对应 rubric**：完成度＝「成套产物 + 契约回填」；正确性＝「先写纳排标准再逐条执行 +
引述强度如实标注」；完整性＝「纳排 + 主题 + 证据表 + 覆盖 + 缺口」；可核验性＝「locator + 逐字引文 +
命中率 + 自检回链」；使用增益＝「同输入下相对基线在多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 8 个文件；result.json.status=answered；
#       included R001,R002；coverage slots 2/2；evidence_stats = {total:2, verbatim_hits:2, hit_rate:1.0}
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`4639b0010043bfbe`。
