# GAIN_EVIDENCE — writing-05 / writing-05-evidence（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**（`examples/`）上的对照，
并把差异映射到官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。
所有「加载本 Skill」的数字均来自本包 `examples/` 的**真实运行**，命令见 §4 可逐字复现。

> **诚实声明**：本文「基线（无 Skill）」一行为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，
> 不代表任何官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线（无 Skill）

### 1.1 典型输出与缺口

同一输入 `examples/`（`manuscript.md` 3 句 + `refs.md` 4 条来源）下，一个未加载本 Skill 的基线
通常给出一段自然语言回答或一份直接拼接的文献清单，典型缺口：

1. **无逐字证据 / 无定位** —— 结论不带 `locator` 与逐字 `quote`，无法回查。
2. **无契约回填** —— 不读 `case.json:output_contract`，不产出 `result.json`（5 个契约键覆盖 0/5）。
3. **无分级** —— 不区分研究设计/样本量/冲突，把 RCT、队列、横断面一视同仁。
4. **易幻觉** —— 可能「补全」缺失字段（DOI / 年份）而非如实标注未知。
5. **无确定性** —— 每次措辞不同、无稳定产物集合。
6. **过度推断** —— 把材料里的相关性写成因果（如 "causes"），不做降级。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意，随包内嵌说明、不单独占文件）：同一 examples/ 输入，只做「原样拼接」。
from pathlib import Path
inp = Path("examples/materials")
draft = (inp / "manuscript.md").read_text(encoding="utf-8")
refs = (inp / "refs.md").read_text(encoding="utf-8")
(out := Path("baseline_out")).mkdir(exist_ok=True)
(out / "draft.md").write_text(draft + "\n\n" + refs, encoding="utf-8")   # 不切论断、不匹配、不分级
# 无 result.json、无足证表、无 locator、无契约
```

模拟结果：文件数 **1**、证据行 **0**、带来源定位的行 **0**、契约键覆盖 **0/5**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=success`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **10**（9 件套 + `result.json`；含 `diff_report.md`） |
| 论断数 claims | **3** |
| 证据行 evidence_rows | **3** |
| 带来源定位的行 rows_with_source | **3** |
| 解析来源条数 references | **4** |
| 过度推断降级 downgrades / overclaim_flags | **1 / 1**（"causes …" → 相关性表述） |
| 引文逐字命中率 verified_quote_rate | **1.0** |
| 论断覆盖率 claim_coverage | **1.0** |
| 待人工确认项 pending_human_count | **1** |
| 契约键覆盖 | **5/5**（`case_id, deliverable, preserved_facts, evidence_map, change_log`） |
| 占位符扫描 | **0**（无 TODO / TBD / null / N-A / 待补 …） |

关键产物：`evidence_driven_draft.md`（带 [n] 标记与限定语）、`evidence_table.json`（逐行
locator+quote+strength+rationale）、`evidence_strength.md`、`diff_report.md`（期望 vs 实际 + 上述指标）、
`human_review.json`、`verification.json`、`result.json`。

以上 `verified_quote_rate` / `claim_coverage` / `pending_human_count` / `overclaim_flags` 四项由
`result.json.metrics`、`verification.json` 与 `diff_report.md` 三处一致给出，同一输入可逐字复算。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件拼接清单，无 `result.json` | 9 件成套产物 + `result.json` | **完成度 / 完整性** |
| 证据可核验 | 无 locator / 无逐字 quote | 每行 `locator`(`路径 [Bn.Sm] chars:a-b`) + 逐字 `quote` | **可核验性** |
| 分级正确性 | 不区分设计/样本量/冲突 | 四因子合成 `高/中/低/不足` + rationale 数值 | **正确性** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + `output_contract`） | **完成度** |
| 抗幻觉 | 倾向补全缺失字段 | 未匹配即记"不足"，不编造 | **正确性 / 可靠性** |
| 确定性与自检 | 无稳定产物、无自检 | 离线确定性；`verification.json` 自检 | **可靠性** |
| 过度推断 | 保留因果断言 | 降级并记 `change_log` | **正确性** |

**为什么这些差异对应 rubric**：完成度靠「成套产物 + 契约回填」补齐；正确性靠「设计分级 + 未匹配不编造」；
完整性靠「多文档账本」；可核验性靠「locator + 逐字引文」；使用增益靠「同一输入下，加载 Skill 相对基线在多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/main.py --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 10 个文件；result.json.status=success
#       metrics = {claims:3, evidence_rows:3, rows_with_source:3, references:4, downgrades:1,
#                  verified_quote_rate:1.0, claim_coverage:1.0, pending_human_count:1, overclaim_flags:1}
```
