# field-extraction v3.0.0

忠实适配自 P3 `reading-06` 参考包（参考分 64）：保留其**两段式语义**
（`prepare` 出骨架 / `finalize|run` 落位出产物）、**入口**（`scripts/extract.py --input /input
--output /app/output`）、**产物名**（`result.json`、`fields.csv`）与**result 字段**
（`result.fields[]` 逐字段记录、`coverage`、`field_dictionary`、
`case_id/status/claims/uncertainties/sources/change_records/limits`），
实现与文本全部重写。

## 安装

把本目录整体放到 `/skills/weekly-skill` 即可。入口脚本用 `__file__` 自定位，
不依赖当前目录，也不需要安装第三方包。

## 用法

```bash
# 单命令全流程
python3 -B /skills/weekly-skill/scripts/extract.py --stage run \
  --input /input --output /app/output --work /app/work

# agent-first：prepare 出骨架 -> Agent 写 draft.json -> finalize 合并 -> selfcheck 自查
python3 -B /skills/weekly-skill/scripts/extract.py --stage prepare   --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/extract.py --stage finalize  --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/extract.py --stage selfcheck --input /input --output /app/output --work /app/work
```

## 产物

| 产物 | 说明 |
|-|-|
| `result.json` | 契约逐键回填 + `result.fields[]` / `coverage` / `corpus`；`case_id` 透传；无 JSON null |
| `fields.csv` | 逐字段表（值 / 单位 / 条件 / 引文 / locator / 状态 / claim_type） |
| `work/corpus_index.json` | 段落、表格、单元格、行、字典的完整索引 |
| `work/draft.json` | prepare 生成的字段骨架，或 Agent 提供的判读 |

## 设计要点

- **只用标准库**：`csv`/`json`/`re`/`hashlib`/`argparse`。
- **索引即可追溯**：段落 `id#anchor`、单元格 `id#table:r{行}c{列}`、定义 `id#field:{id}`。
- **逐字闸门**：`quote` 必须逐字命中索引；命中不了就撤回值并记为 `extraction_failed`。
- **四类状态**：`reported` / `not_reported` / `source_conflict` / `extraction_failed`，各带证据。
- **不换算、不补造**：单位原样取自列头；未印的值只记缺口。
- **诚实降级**：空目录 → `input_error`；有材料但无字典 → `insufficient_evidence`；
  部分落位 → `partial`；全部落位 → `ok`。三条路径都写合法 `result.json` 并 exit 0。

## 限制

- 不做单位换算，也不计算 dispersion / 标准误。
- 不做跨文合并：同一字段只按索引里最先命中的读数落位，冲突时改判 `source_conflict`。
- 列头/行标签匹配是确定性包含匹配，改写过的表头可能匹配不上，此时如实判未落位。
- 只读取材料本身，不联网、不调用外部模型。

## 维护

- 契约键名冻结；新增键走次版本，阈值与文案走修订号。
- 改动后至少跑：`extract.py --stage selfcheck` + `scripts/eval_sim.py` 的
  rich/boundary × single/agent 四组组合，并把结果记入 `SELFTEST.md`。
- 资源与命令声明见 `environment/resources.yaml`；状态口径见 `references/extraction_rules.md`。
