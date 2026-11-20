# 系统综述筛选规格（research-03）

## PRISMA 阶段与计数键

| 阶段 | 计数键 | 含义 |
|-|-|-|
| 识别 | `identified` | 快照中识别到的题录数 |
| 题摘筛选 | `screened_title_abstract` | 进入标题/摘要筛选的题录数 |
| 题摘排除 | `excluded_title_abstract` / `exclude` | 标题/摘要阶段排除数（别名同值） |
| 全文评估 | `full_text_assessed` | 进入全文评估的题录数 |
| 全文排除 | `excluded_full_text` | 全文阶段排除数 |
| 纳入 | `included` / `include` | 最终纳入研究数（别名同值） |
| 合计排除 | `excluded` | 题摘排除 + 全文排除 |
| 待定 | `unresolved` | 题摘阶段判为 uncertain 的数量 |
| 未筛 | `not_screened` | 识别但未进入筛选的数量 |
| 排除原因 | `excluded_by_reason` | 原因 → 数量的非空映射 |

一致性：`identified = screened_title_abstract + not_screened`；
`excluded = excluded_title_abstract + excluded_full_text`；
`included ⊆ full_text_assessed`。

## 质量评价五维（appraisal.json）

| 键 | 含义 | 快照证据不足时 |
|-|-|-|
| `design_fit` | 研究设计是否契合综述问题 | `status=no_included_studies` |
| `risk_of_bias` | 偏倚风险 | `status=no_included_studies` |
| `sample_or_data_adequacy` | 样本/数据是否充分 | `status=no_included_studies` |
| `reporting_completeness` | 报告完整度 | `status=no_included_studies` |
| `directness` | 人群/结局直接性 | `status=no_included_studies` |

每个维度始终是非空 dict，至少含 `assessed`、`status`、`note`。

## screening_ledger.jsonl

每行一题：`rid`、`locator`、`title`、`year`、`doi`、`ta_decision`（include/exclude/uncertain）、
`ta_reason`、`hits`、`full_text`（included/excluded/not_assessed）、`ft_reason`。

## 标准（criteria.json）

`population`、`keywords`、`inclusion`、`exclusion`、`note`；来自 `case.json:criteria`（若有）
或由任务文本关键词推得。

## 诚实边界

- 只在给定快照上筛选，不做真实数据库检索，不宣称全球召回。
- 全文不可解析时保守排除，原因写入 `excluded_by_reason`。
- 评价是元数据级信号，不等同于完整 RoB 评估；不臆造样本量或效应量。
