# README — search-07 · 检索覆盖与漏检闭环审计

## 这是什么

给定「研究问题 + 综述/指南/专家清单 + 检索结果与查询日志」，把一次检索覆盖审计做成**可独立复核**的
固化产物：冻结参考集、逐条命中台账、覆盖率与遗漏率、漏检归因、补检计划与边际收益、复算轨迹。

执行前先读 `references/expert_playbook.md`，产出后按其 §7 检查表逐项自检。

核心约束：

- 覆盖率**分母是冻结的参考集有效条目**（不是检索结果），分子是逐条比对后的命中数；
- 每条漏检带 `query_id` / 字段 / 时间窗 / 来源 / locator / 逐字引用；
- 撤稿 / 重复 / 无全文 / 标识冲突单独标注理由，不静默计入分母；
- 补检针对漏检类别设计，新增命中不与初始命中重复；边际收益为 0 则停止。

## 快速开始

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
```

`/app/output` 会得到 `result.json` + 七类中间产物。没有 `draft.json` 也能跑完，`exit 0`。

自带 fixture 复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

## 三种用法

1. **单命令**（推荐，评测入口）：`all`。
2. **人机协作**：`init` → 看 `show` 输出并可选写 `work/draft.json` → `check` → `build`。
3. **例行复检 / 对照**：`selfcheck` 重新核对产物与契约回填；`compare` 产出与朴素基线的结构对照。

## 判定口径

- 命中规则：L1 标识符精确（DOI/PMID）→ L2 标题相似度 ≥ 0.92 且作者或年份相符 →
  L3 0.80–0.92 标 `needs_review` 交人工裁决。规则先冻结再比对。
- 分母策略：`dedup_exclude_unavailable`（默认）/ `dedup_only` / `all`，用 `--policy` 切换。
- 漏检类别：`query_term_missing`、`field_too_narrow`、`time_window_cut`、`source_not_indexed`、
  `ref_record_anomaly`、`ranking_depth`。
- 状态：覆盖 ≥ 0.5 且无遗漏 → `ok`；有遗漏或材料不足 → `partial`；无参考集 → `insufficient_evidence`；空输入 → `input_error`。

## 目录

```
scripts/main.py               命令入口（all/init/show/check/build/selfcheck/compare）
references/expert_playbook.md 专家方法论：框架/口径/陷阱/检查表（执行前必读）
SKILL.md                      契约、单命令、分步命令、异常处置、自查、top_fix 映射
SELFTEST.md                   本地评测记录（4 组 eval_sim 全 PASS）
GAIN_EVIDENCE.md              与朴素基线的对照（诚实声明：基线为确定性模拟）
environment/resources.yaml    运行时契约
examples/                     自包含 smoke fixture（case.json + materials/refset|queries|retrieved）
```

## 依赖与边界

纯标准库、离线、无第三方包、确定性（时间戳不参与判等）。空 `/input`、坏 JSON、材料无参考集时
仍写合法 `result.json`（`status=input_error` / `insufficient_evidence`）并 `exit 0`。
