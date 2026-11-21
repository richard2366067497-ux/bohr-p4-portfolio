# GAIN_EVIDENCE — search-10 / 术语表驱动的跨语种 known-item 检索（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小材料上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包在 rich 材料上的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 = 内置跨语种术语表（60 概念 × 5 语种）+ 工作稿 schema。未加载本 Skill 的基线 Agent 典型缺口：

1. **无逐语种查询式** —— 只按提问语言检索一次，不给出可复核的语种路由。
2. **术语对齐靠接口直译** —— 不记录「哪个语种写法来自材料原文」，无法回查。
3. **版本/去重缺失** —— 同一论文的原文、全译、摘要版各算一条命中。
4. **无 locator / 无 quote** —— 命中理由无法逐字复核。
5. **无契约回填 / 无增益指标** —— 不产出结构化 `result.json`，无法算非英语召回与效率。
6. **易幻觉** —— 补造术语译法（术语表未收录也照译）。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把材料读成散文，写一段「找到了相关文献」的说明
import pathlib
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "answer.md").write_text(
    "Searched the topic and found related work. The keyword was translated and several "
    "articles match; the Portuguese original and its English translation both count.\n",
    encoding="utf-8")
# 无 lang_queries.md、无 query_plan.json、无 term_pairs、无 locator/quote、无 gain_metrics、无契约回填
```

模拟结果：产物 **1** 件、逐语种查询式 **0**、术语对齐对数 **0**、翻译调用 **N 次（不可复算）**、
去重 **无**、契约键 **0/6**、无效率指标。

---

## 2 加载本 Skill（真实运行）

命令（§5）在 rich 材料上实测（`status=partial`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **10**（result.json + 9 交付物） |
| 术语表解析 | 概念 **60** × 语种 **5**（pt/en/es/fr/de） |
| 概念锚点（材料逐字） | **300** 条（60 概念 × 5 语种），每条带 locator |
| 逐语种查询式 | **300** 条，`query_languages = [de, en, es, fr, pt]` |
| 无效语种查询 | **0** |
| 跨语种术语对齐 | **217** 条成对证据，`term_alignment_accuracy = 1.0` |
| 逐字证据 `evidence_stats` | total **94** / verbatim_hits **94** / hit_rate **1.0** |
| 视图台账 | views_total 0 / distinct_works 0 / duplicates 0（材料未提供视图） |
| 命中卡 | 0 张（材料无题面、无视图 → 如实留空，不伪造） |
| 翻译服务 | `offline-builtin-glossary (no API call)`，调用 **0** 次 |
| 人工核对 | **1** 条（题面缺失）→ `human_review_items_saved_vs_manual = 299` |
| 契约键覆盖 | **6/6**（顶层 + `result.output_contract`） |
| `check_report.json` | `status = ok`（D0–D8 / K1–K4 全通过） |
| 占位符扫描 | **0** |

关键产物：`search_report.md` / `lang_queries.md` / `query_plan.json` / `glossary_index.json` /
`answer_cards.json` / `reconciliation.md` / `check_report.json` / `evidence.json` /
`baseline_comparison.md` / `result.json`。

边界对照：同一引擎在 boundary 材料（空文件 + 坏 JSON + 6 字节文本）上 `status=insufficient_evidence`，
概念/查询/视图均为 0，契约仍 6/6 回填，仍是合法非空产物——**降级但不编造**。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 语种路由 | 只按提问语言检索 | 300 条查询覆盖 5 个语种 | **实际效果** |
| 术语对齐 | 接口直译，无出处 | 217 条成对证据，双向逐字 + locator | **实际效果 / 可核验性** |
| 去重口径 | 原文/全译/摘要各算一条 | work 级去重 + `reconciliation.md` | **实际效果** |
| 逐字证据 | 无 locator / 无 quote | 94 条证据、命中率 1.0 | **可核验性** |
| 翻译调用 | 逐语种调用（次数不可复算） | **0 次**，离线内置表 | **使用增益** |
| 人工核对 | 全靠人工 | 自动核对 299 条，人工仅 1 条 | **使用增益** |
| 增益可验证 | 无指标定义 | `gain_metrics` 字段 + 本节口径 | **使用增益** |
| 契约回填 | 键覆盖 0/6 | 键覆盖 6/6（顶层 + nested） | **完成度** |
| 抗幻觉 | 术语表未收录也照译 | `not-in-glossary` → `pending_human` | **正确性 / 可靠性** |
| 可复用资源 | 无模板无题集 | `templates/query_templates.md`（模板 + 题集 + 3 案例） | **生态贡献** |
| 效率指标 | 无记录 | elapsed_s / requests / rounds 落盘 | **使用增益** |

**为什么这些差异对应 rubric**：实际效果＝「语种路由 + 术语对齐 + 去重 + 逐字证据」；
使用增益＝「翻译调用 0 次、无效语种查询 0 条、人工核对条数可复算」；创新增益＝「术语表驱动查询生成 +
双向回译校验 + work 级去重」；可靠体验＝「缺题面/缺视图如实降级，重复运行确定性」；
生态贡献＝「术语表来源/许可/版本 + 多语种查询模板 + 题集」。

---

## 4 失败分析与 Benchmark（rubric 创新/边界证据）

| 失败模式 | 触发 | 本包的处置 |
|---|---|---|
| 术语错配 | 词面对应但语义错配 | 术语表 `cid` 驱动对齐 + 回译校验，未收录即 `not-in-glossary` |
| 版本错标 | 把全译当原文 | 版本信号词典 + `basis` 明示判据 |
| 重复计数 | 原文/全译/副本各算一条 | 内容指纹去重，命中只数 `distinct_works` |
| 摘要当正文 | `abstract_only` 作命中证据 | `doc_type=abstract_only` 在台账暴露，不计正文证据 |
| 假召回 | 题面语言之外不可检索 | 逐语种查询式固化到 `lang_queries.md` / `query_plan.json` |
| 占位符污染 | 术语表行含占位词 | 引文候选过滤：含占位词的行不作证据，引文保持逐字 |

**与通用对话模型 / 翻译插件的边界**：本包不做泛检索，而是把**语种路由、术语对齐出处、版本判据、
去重口径**做成确定性校验（`query_plan.json`、`term_alignment`、`reconciliation.md`、
`check_report.json`），并给出可复算的 `gain_metrics`；通用模型难以稳定给出逐字命中率与可回填契约。

---

## 5 复现命令

```bash
python3 scripts/main.py all --input <case> --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 10 个文件；result.json.status=partial；
#       概念 60 × 语种 5、查询 300、术语对齐 217、evidence_stats={total:94,verbatim_hits:94,hit_rate:1.0}；
#       契约键 6/6；gain_metrics.translation_service_calls=0；check_report.json.status=ok
```
