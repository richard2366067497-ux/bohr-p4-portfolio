# 使用增益证据 —— multi-doc-comparison v3.0.0

本文件说明本 Skill 相对「无 Skill 基线」的净改善，并给出可复跑的对照方式。
**这里的所有数字都是本包确定性 `baseline_sim` 对照（无 Skill vs 有 Skill）的观测口径，
不是官方跑分，也不对语义质量打分；未实际取得的分数一律不给。**

## 1. 对照设置

| 项 | 无 Skill 基线 | 本 Skill |
|---|---|---|
| 输入 | 同一 `--input` 材料目录（工单 + 语料） | 同一 `--input` 材料目录 |
| 行为 | Agent 直接作答，无锚点、无逐字引文、无 locator | 先锚段（`p{页}#para{序}`）再只从被锚句取值 |
| 产物 | 一段自由文本 | `result.json` + `comparison_matrix.csv` + `comparison_table.md` + `evidence_cards.jsonl` |
| 可复核性 | 无法回查结论出自哪一段 | 每个已报告格子带 `quote + locator` |
| 不可比处理 | 常被直接合并成一句结论 | 逐维度判可比性，命中禁止合并项即分层保留 |

`baseline_sim` 只统计「有无锚点 / locator / 逐字引文 / 契约回填 / 禁止合并是否强制」这类
**结构可判定**的差异，不对语义正确率、科学结论对错打分，因此不构成对基础 Agent 的分数断言。

## 2. 可量化改善（同输入、同预算）

| 指标 | 基线 | 本 Skill | 改善来源 |
|---|---|---|---|
| 答案可定位率 | 0（自由文本） | 每个已报告格子带 locator | 逐段锚定 + 引文闸门 |
| 引文逐字命中率 | 不可测 | 由 `quote_pass_rate` 逐条复核，失败即记 `errors[quote_not_found]` | `find_quote` 校验 |
| 产物齐备件数 | 1 | 4（matrix / table / cards / result） | 七步闭环导出 |
| 禁止合并且未合并 | 不确定 | 命中 `forbidden_pooling` 一律不给合并值 | 可比性维度检验 |
| 空/坏输入退出码 | 不确定 | 恒 0 + 缺口报告 | 诚实降级路径 |
| 契约回填 | 无契约概念 | `output_contract` 逐键回填真实值、无空值、无 JSON null | 契约组装 `denull()` |

## 3. 对照口径（本案）

以 rich 用例（D1/D2 语料 + comparison-workorder）为同输入对照，可观察的结构差异为：

- **读原文耗时**：基线需人工把两篇语料读一遍再凭记忆作答；本 Skill 一次性锚定全部段落并输出
  带 locator 的矩阵，人工只需按 locator 抽查引文。
- **人工核对条目**：基线无法枚举待核对项；本 Skill 的 `pending_human` 与 `evidence_cards.jsonl`
  把每个已报告格子列为一条可回读证据，核对项从「整段重读」降为「逐条引文比对」。
- **返工次数**：基线若发现结论无出处需整段重写；本 Skill 任引文缺出处即在 `errors` 记
  `quote_not_found` 并降级 `status=partial`，返工定位到单个格子。

以上为定性口径；未对任意一方的耗时或正确率给出编造的具体分数。

## 4. 复跑方式

```bash
# 本 Skill（单命令，等价 build）
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
# 本地评测模拟器（rich/boundary × single/agent）
python scripts/eval_sim.py --pkg work/p4/v10/reading-04 \
  --case work/p4/synth_cases/reading-04/rich --mode single
```

结果记入 `SELFTEST.md`；四组组合均 PASS。

## 5. 声明

- 本包纯标准库、离线、确定性，不含外部模型与网络依赖。
- 以上增益为结构可判定项的确定性对照，**非**官方榜单对照，不得作为相对基础 Agent 的正式跑分引用。
