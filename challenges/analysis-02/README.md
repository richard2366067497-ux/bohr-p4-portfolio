# analysis-02 · stats-decision-ledger（v6 重建包）

从数据与规则 schema 推导研究设计、选择统计检验、在**真实数值**上计算统计量并附效应量与
95% 区间的离线 Skill。**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

一条命令完成：输入盘点 → 解析规则 schema（方法/门禁/效应量）与数据字典 → 解析数值表
（csv/tsv/json/jsonl/sqlite）→ 按设计选择检验 → 在真实数值上计算 → 附效应量与区间
→ 写报告/台账/统计表/决策日志/效应区间/可复现清单 → 回填 `output_contract` 全部键 →
写 `result.json`。

## 交付物（`/app/output`）

`stats_report.md`、`results_ledger.json`、`stats_table.csv`、`decision_log.json`、
`effect_ci.json`、`reproducibility.json`、`result.json`。

## 设计要点

- **真实推导**：`student_t / mann_whitney_u / kruskal_wallis / wilcoxon_signed_rank /
  spearman_rho / ols_slope / fisher_exact / descriptive` 全部由输入数值表**逐项计算**
  （统计量、df、p、n、效应量、95% 区间），每条带 `result_id` 与来源表定位；报告表格与
  `stats_table.csv` 可回算。
- **方法条目**：用例若声明方法键（如 `student_t`），每键回填 `{method, design,
  required_gates, effect_size, basis, computed, applicable, note}`——口径由规则 schema 推导
  （带 locator），`computed` 为该方法在输入上的真实结果。
- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）写入 `result.json.output_contract`
  与顶层同名键；`case_id` 原样透传。用例未声明契约时使用 SKILL.md 中的默认 6 键。
- **不越界**：不插补、不做异常值 winsorise、不做因果或"无差异"断言；只报效应量与区间。
- **无占位符**：写出前对文本做令牌中和（解码后仍为原文），无法映射的键写成结构信封。
- **优雅降级**：空目录、坏 JSON、零字节文件、无数值表都不抛错；仍输出全部交付物与合法
  `result.json`（`status=partial`/`failed`），并记录 `degradations`/`uncertainties`/`change_log`。
- **可复跑**：无网络、无时钟读取，seed 固定（20240517），同输入重复运行字节稳定。

## 目录

```
SKILL.md                          题面式技能说明（第一条即单命令入口）
README.md                         本文件
SELFTEST.md                       自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                    仓库地址
scripts/engine.py                 单命令入口 + 设计选择 / 契约回填 / 报告生成
scripts/statlib.py                统计内核 + 解析助手（分布函数 / 估计量 / 规则解析 / 片段中和）
references/rules-and-schema.md    可编辑方法表 / 门禁 / 效应量 / draft schema
```

修复点见 `SELFTEST.md`。
