# 使用增益证据 — reading-client v3.0.0

本文件说明本 Skill 相对「无 Skill 基线」的净改善，并给出可复跑的对照方式。
所有数字均为**本包确定性模拟**（`baseline_sim`）产出，**非官方评测分数**。

## 1. 对照设置

| 项 | 无 Skill 基线 | 本 Skill |
|---|---|---|
| 输入 | 同一 `--input` 材料目录 | 同一 `--input` 材料目录 |
| 行为 | Agent 直接作答，无锚点、无逐字引文、无 locator | 先锚段（`p{页}#para{序}` + 字符区间）再只从被锚句回答 |
| 产物 | 一段自由文本 | `result.json` + 12 件结构化产物（记录/金标/差异/版本/自查/日志/reader） |
| 可复核性 | 无法回查答案出自哪一段 | 每条 claim 带 `quote + locator + 字符区间` |

## 2. 可量化改善（同输入、同预算）

| 指标 | 基线 | 本 Skill | 改善来源 |
|---|---|---|---|
| 答案可定位率 | 0（自由文本） | 100%（每条带 locator 与字符区间） | 逐段锚定 + 引文闸门 |
| 引文逐字命中率 | 不可测 | 由 `qa_log` 逐条复核，失败即记 `degradation` | `quote_is_verbatim` 质检 |
| 产物齐备件数 | 1 | 12 | 七步闭环导出 |
| 空/坏输入退出码 | 不确定 | 恒 0 + 缺口报告 | 诚实降级路径 |
| 契约字段回填 | 无契约概念 | `output_contract` 逐键回填真实值、无空值 | 契约组装 |

`baseline_sim` 只统计「有无锚点/locator/逐字引文/契约回填」这类**结构可判定**的差异，
不对语义质量打分，因此不构成对基础 Agent 的分数断言。

## 3. 复跑方式

```bash
# 本 Skill（单命令，等价 build）
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
# 本地评测模拟器（rich/boundary × single/agent）
python scripts/eval_sim.py --pkg work/p4/v10/reading-05 \
  --case work/p4/synth_cases/reading-05/rich --mode single
```

结果记入 `SELFTEST.md`；四组组合均 PASS。

## 4. 声明

- 本包纯标准库、离线、确定性，不含外部模型与网络依赖。
- 以上增益为结构可判定项的确定性对照，**非**官方榜单对照，不得作为相对基础 Agent 的正式跑分引用。
