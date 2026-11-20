# reading-12 · extraction-table-auditor（v6 修复包）

把"别人从论文里抄下来的行"清洗成统计软件敢用的表，并留下一条能倒查回原文的证据链。
**纯标准库、无网络、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

一条命令完成：扫描输入（编码/体积/文本层）→ 识别行对象与列角色 → 单位换算与同义归一 →
重复/冲突候选分组 → 渲染清洗表与全部视图 → 回填 `output_contract` → 写 `result.json` →
占位符清理。

## 交付物（`/app/output`）

`cleaned.csv`、`change_log.csv`、`pending_review.csv`、`anomaly_report.md`、`rules.json`、
`field_mapping.json`、`unit_table.json`、`result.json`。

## 设计要点

- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）写入 `result.json.output_contract`
  与顶层同名键；用例未声明时使用 SKILL.md 中的默认 6 键。`case_id` 原样透传。
- **键映射**：`deliverable→cleaned.csv`、`evidence_map→sources(带 locator)`、
  `change_log→changes`（本输入无变更时给出诚实的聚合说明条目）、`coverage→result.coverage`。
- **不编造**：未知单位、无法解析的单元格、冲突行一律留空并进 `pending_review.csv`。
- **无占位符**：写出前统一清理 `待写/待补充/none/null/pending/N/A/TBD` 等令牌；过小的 JSON 补诚实说明。
- **用例自带词表**：字段词典/单位表优先读输入 `materials/` 里的用例版本，缺失时退化并记 `degradations`。
- **只读与幂等**：输入目录只读；`selfcheck` 两跑逐字节一致。

## 目录

```
SKILL.md                         技能说明（第一条即单命令入口）
README.md                        本文件
SELFTEST.md                      自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                   仓库地址
scripts/main.py                  CLI（all/init/show/check/build/selfcheck）
scripts/clean_engine.py          解析、单位、对象、分组、quote 校验
scripts/clean_flow.py            发现、字段解析、提案、合成
scripts/clean_report.py          校验、渲染、复算、确定性
```

修复点见 `SELFTEST.md`。
