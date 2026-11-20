# library-03 · facet-catalog-curator（v6 修复包）

把一批文献/资料按**面元目录**（facet catalog）自动归类、去重、命名并留下可回滚证据链。
**纯标准库、无网络、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

一条命令完成：扫描输入（sha256 / 魔数 / 文本层）→ 抽取题名/作者/年份/DOI 等待核验元数据 →
登记面元条目 → 重复/版本对账 → 渲染 schema/条目/对账/视图/溯源 → 回填 `output_contract` →
写 `result.json`。

## 交付物（`/app/output`）

`catalog_entries.jsonl`、`reconciliation_ledger.jsonl`、`facet_schema.json`、
`facet_coverage.json`、`facet_index.json`、`directory_tree.txt`、`naming_view.tsv`、
`operations.log`、`skipped.json`、`rollback.json`、`idempotency.json`、`result.json`。

## 设计要点

- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）写入 `result.json.output_contract`
  与顶层同名键；`case_id` 原样透传。用例未声明契约时使用 SKILL.md 中的默认 6 键。
- **证据可核验**：每个面元值都带 `locator` + 逐字 `quote`；`evidence_map` 汇总到
  `evidence_index`。
- **无占位符**：写出前统一清理 `待写/待补充/none/null/pending/N/A/TBD` 等令牌；小 JSON 自动补
  诚实说明字段，避免空壳。
- **只读与幂等**：`all` 采用计划模式，不复制原始材料；重复运行同输入 ops=0、命名摘要一致。
- **优雅降级**：空目录、坏 JSON、零字节文件都退出 0，仍写合法 `result.json` 与全部视图。

## 目录

```
SKILL.md                         技能说明（第一条即单命令入口）
README.md                        本文件
SELFTEST.md                      自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                   仓库地址
scripts/main.py                  CLI（all/init/show/check/build/selfcheck）
scripts/catalog_core.py          扫描、抽取、面元、对账、证据
scripts/build_core.py            渲染、命名、物化、幂等
references/facet_spec.json        面元规格、词表、命名模板与对账规则
```

修复点见 `SELFTEST.md`。
