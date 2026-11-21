---
name: deep-research-evidence-map
description: 深度研究文献综述与证据图谱 —— 把模糊科研问题拆成可检索子问题，逐条取回证据，综合成带来源定位的结论与证据矩阵，产出契约化 result.json。用于文献综述、证据回链、冲突识别与研究空白分析的任务。
version: 10.0.0
license: MIT
---

# deep-research-evidence-map · 深度研究文献综述与证据图谱

走完一条**可复核的研究路径**：问题拆解 → 检索规划 → 证据采集 → 证据综合 → 交付打包。评委只看三件事：子问题拆解质量、结论回链率、路径可复跑性。

## 执行前必读（强制）

**执行前先阅读 `references/expert_playbook.md`，按其中专家检查表逐项产出。** 手册给出判分要点、P1–P6 必覆盖要点、F1–F10 错误模式、S1–S5 流水线、量化公式、证据强度分级、20 项自查表与完整案例，是质量下限；本文件只描述接口与契约。

## 交付物与输出契约

向 `/app/output/` 写 `result.json`，并把契约键**原样**回填 `result.json.output_contract`：

```json
{
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "evidence_map": "array",
    "change_log": "array",
    "coverage": "object",
    "status": "string"
  }
}
```

`case.json` 给出 `output_contract` 时以它为准。主要产物：`result.json`、`research_plan.json`、`evidence_matrix.csv`、`synthesis.json`、`coverage.json`、`report.md`。

## Agent 路径（五命令）

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --output /app/output
```

- `init`：索引材料，写合法 partial `result.json`。
- `show`：打印来源/记录/段落（可加 `--doc --paras --records --contract`）。
- `check`：校验 `/app/work/draft.json`（无则按规则表补齐）。
- `build`：渲染证据矩阵、综合结论、覆盖与报告，写最终 `result.json`（无 draft 也可跑）。
- `selfcheck`：复验产物与契约完整性。退出码恒 0，异常写入 errors/degradations。

## 单命令等价入口（single command — one shot，无 draft）

一条命令跑完 init→build→selfcheck，直接产出完整契约与全部交付物：

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
```

## 规则与约束

- 子问题 ≥3 且有依赖关系（无环）；每子问题 ≥1 检索式并记命中数。
- 证据表每行有 `source_id + locator`（页/段/表/图号）；每条结论引用 `evidence_ids`。
- 冲突显式列双方证据并分析差异来源；研究空白具体到子问题与条件。
- 仅标准库；不联网；失败步骤标 `status=failed` 并记降级策略，不静默跳过。

## 自检清单

- [ ] `result.json` 有效，`output_contract` 含全部契约键且非空
- [ ] 路径键指向真实非空产物
- [ ] P1 子问题树 ≥3 且无环；P2 每子问题有检索式与命中数
- [ ] P3 证据行有 source_id+locator；P4 冲突 ≥1 对（若存在）
- [ ] P5 每结论有 evidence_ids；P6 空白具体
- [ ] 工具调用失败有降级记录，不编造
- [ ] **专家检查表逐项通过**（`references/expert_playbook.md` §6）
