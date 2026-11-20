# analysis-04 · analysis-codegen-execute（v6 重建包）

从数据字典与规格**生成**一段自足的科研分析代码，在隔离子进程里**真实执行**，逐条**独立重算**
每个关键数字、渲染图表、留下命令与退出码，交付代码/结果/校验/日志/环境/复现六类证据的离线
Skill。**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

一条命令完成：输入盘点 → 解析字典与规格 → 生成 `code/analysis.py` → 子进程执行（300s 超时，
捕获 stdout/stderr/退出码）→ 读回 `results/summary.json` → 独立重算并逐条校验 → 渲染图表
→ 写全部交付物 → 回填 `output_contract` 全部键 → 写 `result.json`。

## 交付物（`/app/output`）

`report.md`、`results/summary.json`、`verification.json`、`run_log.json`、`environment.json`、
`reproducibility.json`、`code/analysis.py`、`results/key_numbers.json`、`cleaning_ledger.csv`、
`chart.svg`（有分类列时）、`result.json`。

## 设计要点

- **真实推导**：代码由材料生成（不是预制答案），在子进程里真正跑通；每个关键数字
  （mean / groupby mean / t / r / 行数账）都在引擎里**独立重算**，容差 `max(1e-6, 5e-4·|值|)`，
  不一致即 `pass=false`，专门暴露"跑通了但算错了"的静默错误。
- **两条独立路径**：生成脚本与引擎复核走不同代码路径，避免同源错误。
- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）按语义写入 `result.json.output_contract`
  与顶层同名键；`case_id` 原样透传。用例未声明契约时使用 SKILL.md 中的默认 6 键。
- **失败留痕**：子进程失败/超时保留 stdout/stderr 现场并降级为包内重算；绝不静默改数。
- **无占位符**：写出前对文本做令牌中和（解码后仍为原文），无法映射的键写成结构信封。
- **可复跑**：`python3 code/analysis.py --input <材料> --output <结果>` 可脱离本包自足复跑；
  无网络、无时钟读取，seed 固定（20240517），同输入重复运行字节稳定。

## 目录

```
SKILL.md                          题面式技能说明（第一条即单命令入口）
README.md                         本文件
SELFTEST.md                       自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                    仓库地址
scripts/engine.py                 单命令入口 + 代码生成 / 执行 / 重算校验 / 契约回填
scripts/codelib.py                解析与统计助手（inventory / table / spec / 片段中和）
references/analysis_spec.md       可编辑规格表 / 校验项 / 降级矩阵 / 契约键语义
```

修复点见 `SELFTEST.md`。
