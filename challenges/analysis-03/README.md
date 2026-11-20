# analysis-03 · figure-spec-publisher（v6 修复包）

把科研数据表做成可投稿图件 + 可复核证据链的离线 Skill 包。**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

一条命令完成：输入盘点 → 数据表解析 → 描述统计 → 图型规格（含拒绝理由）→ 渲染 SVG →
写图注/绘图代码/审计/报告 → 回填 `output_contract` 全部键 → 写 `result.json`。

## 交付物（`/app/output`）

`figure_report.md`、`figure_specs.json`、`data_to_figure.json`、`stats.json`、
`cleaning_log.json`、`audit.json`、`captions.md`、`case_materials.json`、
`figures/overview.svg`、`figure_code.py`、`result.json`。

## 设计要点

- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）写入 `result.json.output_contract`
  与顶层同名键；`case_id` 原样透传。用例未声明契约时使用 SKILL.md 中的默认 6 键。
- **无占位符**：写出前统一清理 `待写/待补充/none/null/pending/N/A/TBD/<...>` 等令牌，
  无法直接映射的键写成诚实结构信封。
- **优雅降级**：空目录、坏 JSON、零字节文件都不会抛错；仍输出全部交付物与合法 `result.json`
  （`status=partial`/`failed`），并记录 `degradations` / `uncertainties` / `change_records`。
- **可复跑**：无网络、无时钟读取，同输入重复运行字节稳定。

## 目录

```
SKILL.md                         题面式技能说明（第一条即单命令入口）
README.md                        本文件
SELFTEST.md                      自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                   仓库地址
scripts/engine.py                全部逻辑（1 个文件，≤30KB）
references/figure-spec-rules.md  图件规格规则（数据口径、编码、导出）
```

修复点见 `SELFTEST.md`。
