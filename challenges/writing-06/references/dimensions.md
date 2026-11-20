# 六维审读规则与字段口径

本文件是 `scripts/core.py` 与 `scripts/review.py` 的规则说明书：定位符格式、六个维度的触发条件、阈值、finding 与
action 的字段含义以本文为准；改阈值时同步代码与本表。

## 1 定位符

正文按标题切章、按空行/换行切段、按句末标点切句，依次编号：

```
C01         第 1 章（无标题的开头内容也算一章）
C01-P002    该章第 2 段
C01-P002-S03 该段第 3 句
```

章 id 用 `C%02d`，段用 `P%03d`，句用 `S%02d`。每条 finding 的 `quote` 必须是该定位符所在正文里
的**逐字子串**（空白归一化后比较）；核验率写入 `structural_review.json` 的 `grounding.hit_rate`，
命中不了的候选结论直接丢弃，不进产物。

## 2 维度与触发条件

| 维度 | 触发条件（满足其一即产生 finding） | 严重度基线 |
|-|-|-|
| `section_structure` | 有标题的章 ≤1；缺 introduction / method / result；discussion 与 conclusion 都缺；method 排在 result 之后或 result 排在 discussion 之后 | high |
| `research_question_alignment` | 前 8 段中找不到研究问题句且正文 ≥300 词；或问题句关键词 ≥50% 未在 result/discussion/conclusion 复现 | high |
| `argument_chain` | 主张句（suggest/indicate/therefore/表明/因此…）所在段无引用、无带单位量值、无图表引用，且段 ≥30 词；正文引用编号无对应条目 | medium / high |
| `paragraph_relations` | 同章相邻两段均 ≥55 词、词集 Jaccard <0.05 且后段无过渡词；单段 ≥120 词且 ≥2 处量值 + ≥1 处主张 | low / medium |
| `duplication` | 两段均 ≥45 词且 8-gram 集合 Jaccard ≥0.30；同一句子归一化后 ≥55 字符出现 ≥2 次 | high |
| `conclusion_boundary` | 结论/讨论/摘要句含因果词且无模糊限制词，而方法与结果只有相关性措辞；含绝对化措辞且无限制词；量值只在结尾章出现 | high / medium / low |

上限：总 finding ≤36，`paragraph_relations` 每类 ≤2，`duplication` 段落对 ≤4、重复句 ≤3，
`conclusion_boundary` ≤6。超限时按严重度优先保留。

## 3 字段

finding：

| 字段 | 含义 |
|-|-|
| `finding_id` | `F01` 起顺序编号 |
| `dimension` | 六维之一 |
| `severity` | `high` / `medium` / `low` |
| `locator` / `to_locator` | 结论所在位置 / 建议操作的目标位置 |
| `quote` | 正文逐字引文（已核验） |
| `diagnosis` | 一句可读判断 |
| `evidence_for_judgment` | 触发该判断的计数，如 `term overlap=0.031 between C02-P001 and C02-P002` |
| `confidence` | `high` / `medium` / `low-medium` |
| `operation` | `move` / `merge` / `split` / `narrow` / `delete` / `insert` |

action：每条 finding 一条，`action_id` 形如 `A01`，带 `priority`（high→P1、medium→P2、low→P3）、
`expected_effect`、`risk`、`executable=true`。

## 4 维度覆盖

`structural_review.json` 的 `dimension_coverage` 对六个维度各给一条：

- `findings`：该维度产生了 finding，`finding_ids` 列出编号；
- `no_issue_with_evidence`：检测器跑过且未触发，`checked` 记录扫描了多少章多少段；
- `not_assessed`：包内没有正文，六维只能标为未审，原因写在 `unverified` 与 `degradations`。

## 5 包级审读（无正文时）

没有识别出正文时不做句子级判断，改为包级审计并写入 `structural_review.json.packet_audit`：

- 标题清单：每份文档的标题、层级、是否带数字编号；
- 重复句：归一化 ≥55 字符的句子在文档内或跨文档重复出现；
- 跨文档术语：长度 >4 且出现在 ≥2 份文档的词，按文档数与字母序排序。

同时 `outline_after.md` 给出作者应当补齐的目标稿件骨架，`edit_plan.md` 列出下一步需要的材料。
