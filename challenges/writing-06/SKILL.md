---
name: paper-structure-logic-review
description: Review an academic manuscript for section structure, research-question alignment, argument chains, paragraph relations, duplication and conclusion boundaries; emit locator-anchored findings, an executable edit plan and a consistency report.
version: 6.0.0
---

# 论文结构与逻辑优化（writing-06）

输入一个稿件包（案例描述、正文、参考文献、规则或数据说明），输出六维结构审读：每条结论都带
`C01-P002-S03` 形式的定位符与正文逐字引文；每条修改建议都可执行（move / merge / split / narrow /
delete / insert），并附预期效果与风险。最后把案例契约逐键回填进 `result.json`。

## 1 单命令全流程

单命令即可完成全部流程：清点输入 → 解析章节/段落/句子定位符 → 六维检测 → 生成审读与修改计划 →
回填契约 → 自检产物。

```
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

三个路径都有默认值，省略与上面等同；退出码恒为 0（含所有降级路径），仅 argparse 用法错误返回 2。

## 2 六维审读口径

| 维度 | 检查什么 | 典型结论 |
|-|-|-|
| `section_structure` | 是否有标题层级、核心段落是否齐全、章节顺序 | 缺 Methods / Results 被提前 |
| `research_question_alignment` | 研究问题是否明示、关键术语是否在结果与讨论中复现 | 问题句关键词在后文消失 |
| `argument_chain` | 主张段是否带引用/数值/图表；正文引用是否有条目 | 主张句无任何证据标记 |
| `paragraph_relations` | 相邻段是否有衔接、长段是否混合观测与解释 | 两段术语几乎不重叠且无过渡 |
| `duplication` | 段落 8-gram 重叠、句子逐字重复 | 同一结论段落出现两次 |
| `conclusion_boundary` | 因果词、绝对化措辞、仅出现在结论的量值 | 相关性研究却写"导致" |

阈值（段落 ≥45 词、句子 ≥55 归一化字符、8-gram Jaccard ≥0.30、相邻段词集 Jaccard <0.05）与
字段定义见 `references/dimensions.md`。

## 3 Agent-first 增强路径

```
python3 <skill>/scripts/main.py probe     --input /input --work /app/work
python3 <skill>/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 <skill>/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 <skill>/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`probe` 写 `<work>/inventory.json`（文件、角色、哈希、是否识别出正文）。Agent 可读它并在
`<work>/draft.json` 里补充自己的判断，`build` 会把这些注记并入 `edit_plan.md` 与 `outline_after.md`：

```json
{
  "title": "人工审读草稿",
  "sections": [
    {"heading": "Introduction", "note": "研究问题句应落在第二段开头"},
    {"heading": "Conclusion", "note": "因果措辞需要收窄到关联"}
  ],
  "actions": [
    "先处理 P1 的结论收窄，再合并重复段落",
    "Results 与 Discussion 之间补一句过渡"
  ]
}
```

`draft.json` 缺失或损坏时按材料推断，不报错；每个子命令都会重跑完整流水线，分阶段调用与
单命令结果一致。

## 4 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `structural_review.json` | 六维结论、finding/action 全量、维度覆盖、逐字引文核验率、统计 |
| `edit_plan.md` | 按 P1–P3 排序的可执行修改计划，含定位符、引文、诊断、预期效果与风险 |
| `outline_after.md` | 当前结构与目标结构对照，或稿件缺失时给出目标稿件骨架 |
| `argument_map.json` | 研究问题句、主张-证据链、无证据链计数 |
| `consistency_report.md` | 文件清单、标题层级、重复句、跨文档术语、引用与条目计数 |
| `pending_human.json` | 需要作者补充或确认的缺口 |
| `result.json` | 契约回填、状态、来源、不确定性、修改记录、限制、错误 |

## 5 result.json 与契约回填

`result.json.output_contract` 逐键回填案例契约；顶层同时保留 `verified` / `unverified` /
`degradations`。无契约时使用下列默认结构（也是本文件的契约样例）：

```json
{
  "output_contract": {
    "unverified": "本次未能核验的内容及其原因",
    "verified": "本次实际核验的内容与计数",
    "degradations": "本次使用的降级路径说明"
  }
}
```

`case_id` 原样透传；`status` 取 `ok | partial | insufficient_evidence | input_error`，与材料实际
情况一致，不把包级审读写成正文审读。

## 6 降级与边界

| 场景 | 行为 |
|-|-|
| 输入包无正文 | 转为包级审读（标题、编号、重复句、术语），`unverified` 写明六个维度待审 |
| 材料为空/损坏/仅空壳标记 | 记录缺口到 `pending_human.json`，状态 `insufficient_evidence`，绝不编造正文 |
| 输入目录不存在或为空 | 状态 `input_error`，仍写出合法 `result.json` |
| 检测器异常 | 错误写入 `errors`，其余维度照常输出，退出码仍为 0 |

## 7 自检

`selfcheck` 校验：契约键齐全且非空、七个产物均 ≥40 字节、`case_id` 透传，并把结果写到
`<output>/selfcheck.json`。规则阈值与字段口径见 `references/dimensions.md`。

## 8 文件清单与维护

```
SKILL.md                     本文件：单命令入口、agent 路径、六维口径、契约、降级、自查
scripts/main.py              入口：run / probe / build / check / selfcheck
scripts/core.py              共享层：清洗、发现、文本模型、包级审计、契约回填、产物渲染
scripts/review.py            审读层：六维检测器、覆盖度、动作、流水线与自查
references/dimensions.md     定位符、六维触发条件、finding/action 字段与覆盖状态
README.md                    安装、用法、产物、限制与维护
SELFTEST.md                  eval_sim 与脚本级降级的自测记录
GITHUB_URL.txt               公开仓库与本挑战的目录
```

- 依赖：Python 3.9+ 标准库；无第三方包、无网络。包体 8 文件，单文件 ≤30KB，主脚本 ≤25KB。
- 版本 6.0.0；六维 id 与 finding/action 字段冻结，新增维度需同步 `DIMS`、检测器与本表。
