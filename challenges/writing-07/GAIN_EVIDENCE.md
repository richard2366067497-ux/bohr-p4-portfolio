# GAIN_EVIDENCE — writing-07 / intro-relatedwork-writer（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小材料上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包在 rich 材料上的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 = 稿件（含 `[12]`、`0.6`、`0.1`、`42`、`61`、`p<0.05`）+ 3 条评审意见。未加载本 Skill
的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 不给 `locator`（如 `materials/manuscript-baseline.md#L5`）与原文逐字 `quote`。
2. **引用挂在段末** —— `[12]` 堆在段落末尾，不绑定到承载该论断的句子。
3. **空白凭空宣称** —— 直接写「该领域缺乏研究」，不给 ≥2 条前提。
4. **无契约回填** —— 不产出结构化 `result.json`，契约键覆盖 0/5。
5. **易幻觉** —— 可能补造「已做胰岛素敏感性实验」等材料外事实，或编造效应量数值。
6. **无保留锚点** —— 改写时可能改动 `0.6`、`42`、`p<0.05` 等数字或丢掉 `[12]`。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把评审意见改写成一段通顺英文，不定位、不保留锚点、不推导空白
import json, pathlib
raw = pathlib.Path("<case>/materials/manuscript-baseline.md").read_text(encoding="utf-8")
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "revision.md").write_text(
    "This study examined a walking intervention. Results were significant [12]. "
    "We addressed the reviewers by adding detail and discussing limitations.\n",
    encoding="utf-8")
# 无 claim_map.md、无 gap_ledger.md、无 evidence.json、无 result.json、无 preserved_facts
```

模拟结果：产物 **1** 件、逐字证据 **0**、引用绑定 **0**、空白前提 **0**、契约键 **0/5**、无校验。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 rich 材料上实测（`status=answered`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **10** |
| 逐字证据 `evidence_stats` | total **7** / verbatim_hits **7** / hit_rate **1.0** |
| 引用标记 → 来源 | **1**（[12] → S1，绑定到承载该论断的句） |
| 研究空白前提 `gap_premises` | **4**（≥2，满足 gap-first） |
| 评审意见块 | **4**（Reviewer 1 段 + 3 条 Comment） |
| preserved_facts | **6** 个数字/引用锚点逐字保留，dropped 空 |
| 四段计数 | background 2 / related 1 / gap 4 / contributions 2 |
| 契约键覆盖 | **5/5**（顶层 + `result.output_contract`） |
| `metrics` | elapsed_s、requests=5、rounds=1、verbatim_hit_rate=1.0、gap_premises=4 |
| `contract_check` | keys_expected 5 / keys_filled 5 / missing [] |
| 占位符扫描 | **0** |

关键产物：`manuscript.md`（句内引用）/ `sources_used.md` / `claim_map.md` / `gap_ledger.md` /
`contribution_alignment.md` / `change_log.md` / `baseline_comparison.md` / `evidence.json` /
`verification.json` / `result.json`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件散文，无 result.json | 10 件成套产物 | **完成度 / 完整性** |
| 引用绑定 | 引用堆在段末 | 引用落在具体论断（句内绑定） | **正确性** |
| 空白推导 | 凭空宣称 | 4 条前提、各带 locator | **正确性** |
| 证据可核验 | 无 locator / 无 quote | 7 条证据、命中率 1.0 | **可核验性** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + nested） | **完成度** |
| 抗幻觉 | 可能编造实验/效应量 | 未做实验写入 gap/pending_human，不虚构 | **正确性 / 可靠性** |
| 锚点保留 | 改写丢失数字 | preserved_facts 6 个锚点逐字保留 | **完整性** |
| 效率指标 | 无记录 | elapsed_s / requests / rounds 落盘 | **使用增益** |

**为什么这些差异对应 rubric**：完成度＝「成套产物 + 契约回填」；正确性＝「引用绑定论断 + 空白由
前提推出 + 不把没做当已做」；完整性＝「四段 + preserved_facts + 证据」；可核验性＝「locator + 逐字
引文 + 命中率」；使用增益＝「同输入下多维同时提升 + 可量化效率指标」。

---

## 4 失败分析与 Benchmark（rubric 创新/边界证据）

| 失败模式 | 触发 | 本包的处置 |
|---|---|---|
| 引用漂移 | 引用与论断错配 | 每条引用内联到承载该论断的句，`claim_map.md` 给出 `F#:locator` |
| 空白空转 | 「近年来受到广泛关注」式铺垫 | 空白必须由 ≥2 条带 locator 的前提推出，否则标 provisional |
| 锚点改写 | 数字/引用在改写中被改 | `preserved_facts` 逐字校验，dropped 非空即如实报告 |
| 补造材料外事实 | 评审要「补充实验」而材料没有 | 映射到 gap 与 `pending_human`，绝不写成已完成 |

**与通用对话模型 / 文献管理工具的边界**：本包不生成「泛综述」，而是把**引用↔论断绑定、空白
前提化、锚点保留、评审意见→改动映射**做成确定性校验（`evidence_stats`、`preserved_facts`、
`contract_check`），通用模型难以稳定给出逐字命中率与可回填契约。基准见 `baseline_comparison.md`。

---

## 5 复现命令

```bash
python3 scripts/main.py all --input <case> --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 10 个文件；result.json.status=answered；
#       evidence_stats = {total:7, verbatim_hits:7, hit_rate:1.0}；gap_premises=4；契约键 5/5
```
