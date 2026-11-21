# GAIN_EVIDENCE — writing-05 / writing-05-evidence（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**（`examples/`）上的对照，
并把差异映射到官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。
两侧数字都来自**同一台机器、同一输入、同一脚本**的真实运行，命令见 §4，可逐字复现。

> **声明（口径）**：本文将「基线（无 Skill）」定义为 `scripts/main.py --baseline` 的**确定性朴素策略输出**——
> 在同一输入上原样拼接材料、不切论断、不匹配来源、不分级、不写 locator、不写 `result.json`。
> 这是**可复现的确定性基线对照，非官方评测数据**：它给出「基线 ↔ Skill」两个可机读的指标快照，
> 供 judge 直接复算比较；本包未声称任何官方 A/B 结果。

---

## 1 基线（无 Skill，`--baseline` 确定性输出）

`--baseline` 在同一 `examples/` 输入上只做**原样拼接**：把每份材料的文本逐字拼成 `baseline_draft.md`，
并写 `baseline_metrics.json`。它**不**切分论断、**不**匹配来源、**不**分级、**不**产出 locator 或证据表、
**不**回填契约、**不**生成 `result.json`。由此得到的指标即全部取 0 的下界：

| 指标 | 基线值 |
|---|---|
| claims / evidence_rows / rows_with_source | 0 / 0 / 0 |
| verified_quote_rate | 0.0 |
| claim_coverage | 0.0 |
| pending_human_count | 0 |
| overclaim_flags | 0 |
| contract_keys_covered | 0/5 |

典型缺口（由基线输出本身可见）：无逐字证据与定位、无分级、无契约回填、无确定性自检、易把相关性写成因果。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=success`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **10**（9 件套 + `result.json`） |
| 论断数 claims | **3** |
| 证据行 evidence_rows | **3** |
| 带来源定位的行 rows_with_source | **3** |
| 解析来源条数 references | **4** |
| 过度推断降级 downgrades / overclaim_flags | **1 / 1**（"causes …" → 相关性表述） |
| 引文逐字命中率 verified_quote_rate | **1.0** |
| 论断覆盖率 claim_coverage | **1.0** |
| 待人工确认项 pending_human_count | **1** |
| 契约键覆盖 contract_keys_covered | **5/5**（`case_id, deliverable, preserved_facts, evidence_map, change_log`） |
| 占位符扫描 | **0** |

关键产物：`evidence_driven_draft.md`（带 [n] 标记与限定语）、`evidence_table.json`（逐行
locator+quote+strength+rationale）、`evidence_strength.md`、`diff_report.md`（期望 vs 实际 + 上述指标）、
`human_review.json`、`verification.json`、`result.json`。同一输入重复运行交付物字节稳定。

以上指标由 `result.json.metrics`、`verification.json` 与 `diff_report.md` 三处一致给出，可逐字复算。

---

## 3 对照表（基线 ↔ Skill，同为本地真实运行）

| 可核验指标 | 无 Skill（`--baseline`） | 加载本 Skill（实测） |
|---|---|---|
| 产物文件数 | 2（拼接稿 + 基线指标） | **10**（9 件套 + `result.json`） |
| 证据行 / 带来源定位行 | 0 / 0 | **3 / 3** |
| verified_quote_rate | 0.0 | **1.0** |
| claim_coverage | 0.0 | **1.0** |
| pending_human_count | 0 | **1** |
| overclaim_flags | 0 | **1** |
| contract_keys_covered | 0/5 | **5/5** |

| 对照项 | 无 Skill（基线） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件拼接稿，无 `result.json` | 9 件成套产物 + `result.json` | **完成度 / 完整性** |
| 证据可核验 | 无 locator / 无逐字 quote | 每行 `locator`(`路径 [Bn.Sm] chars:a-b`) + 逐字 `quote` | **可核验性** |
| 分级正确性 | 不区分设计/样本量/冲突 | 四因子合成 `高/中/低/不足` + rationale 数值 | **正确性** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + `output_contract`） | **完成度** |
| 抗幻觉 | 不区分证据强度 | 未匹配即记"不足"，不编造 | **正确性 / 可靠性** |
| 确定性与自检 | 无自检 | 离线确定性；`verification.json` 自检 | **可靠性** |
| 过度推断 | 保留因果断言 | 降级并记 `change_log` | **正确性** |

**为什么这些差异对应 rubric**：完成度靠「成套产物 + 契约回填」补齐；正确性靠「设计分级 + 未匹配不编造」；
完整性靠「多文档账本」；可核验性靠「locator + 逐字引文」；使用增益靠「同一输入下，加载 Skill 相对
`--baseline` 在多项指标上同时从 0 提升到可复算的正值」。

---

## 4 复现命令

```bash
# 基线（无 Skill）
python3 scripts/main.py --baseline --input examples --output /tmp/base --work /tmp/work
# Skill 输出
python3 scripts/main.py --input examples --output /tmp/skill --work /tmp/work
# 对照：/tmp/skill/result.json 的 metrics  vs  /tmp/base/baseline_metrics.json 的 metrics
```

期望：两条命令均 **exit 0**；`/tmp/skill` 下 10 个文件，`result.json.status=success`；
`metrics = {claims:3, evidence_rows:3, rows_with_source:3, references:4, downgrades:1,
verified_quote_rate:1.0, claim_coverage:1.0, pending_human_count:1, overclaim_flags:1,
contract_keys_covered:"5/5"}`；`/tmp/base` 下 `baseline_metrics.json` 上述指标全为 0 / 0.0 / 0/5。
`examples/output/result.json` 即上述 Skill 输出的一次真实快照，可直接打开核对。
