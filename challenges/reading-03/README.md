# reading-03 · sci-lit-bilingual-audit（v10 包）

科研文献**双语对照 + 术语锁定 + 机械核验** Skill：给定英文文献（或明确段落区间），产出段落级中英对照 + 术语表 + 核验记录，
每段可指回原文页码/段号，关键结论带逐字证据，译不准的显式标注。纯标准库、离线、确定性；**译文由 Agent 写进工作稿**，
脚本负责切段、抽取、保护、核验、取证。执行前请先读 `references/expert_playbook.md`。

## 1 一分钟上手

```bash
# 只跑一次、无需工作稿（也产出完整契约与 6 个产物，退出码 0）
python scripts/main.py all --input /input --output /app/output --work /app/work

# 跑包内最小示例
python scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

产物（`--output`，默认 `/app/output`）：`result.json`、`paragraph_pairs.jsonl`、`audit_report.json`、`glossary.json`、
`bilingual_review.md`、`run_log.txt`。

## 2 Agent 增强流程

```bash
python scripts/main.py init   --input /input --output /app/output --work /app/work   # 切段 + 工作稿骨架
python scripts/main.py show   --sids S001-S008 --input /input --output /app/output --work /app/work
# 把 work/draft.json 每个 segment 的 target 填成译文，并补齐 glossary
python scripts/main.py check  --input /input --output /app/output --work /app/work   # 看缺口（恒 exit 0）
python scripts/main.py build  --input /input --output /app/output --work /app/work   # 出产物（可反复跑）
python scripts/main.py selfcheck --input /input --output /app/output --work /app/work   # 自检（含降级场景）
python scripts/main.py compare  --input /input --output /app/output --work /app/work   # 对照指标
```

长文按批推进：`show --sids` → 填译文 → `build`；每批都留下合法的完整产物。`init` 不覆盖已有工作稿（续跑安全）。

## 3 依赖与运行条件

- Python 3.8+（验证用 3.12），**只用标准库**（`re/json/os/sys/zipfile/zlib/html/argparse/time`）
- **不联网、不调模型、不需要 key、不调外部二进制**；离线、确定性
- 支持 `.txt .md .markdown .html .htm .docx .json` 与**有文本层的** `.pdf`；**不做 OCR**（扫描件只记降级）
- 运行环境与预算详见 `environment/resources.yaml`

## 4 输入与约定速查

```
/input/case.json     case_id / language / target_language / output_contract（可选）
/input/task.md       题面（只读）
/input/materials/*   正文材料（可多文件多页）
```

契约键逐键原样回显到 `result.json.output_contract`；未给契约时用默认键（`case_id / status / result / claims / uncertainties`）。

- 段号 `sid = p{页}:S{序号}`，`locator` 形如 `p1:S003`；跨页续段带 `bridged=true`
- 要素类型：`heading / body / caption_figure / caption_table / table_header / table_row / formula / reference`
- 切段 R1–R7：空行断段 / 句末兜底 / 连字符拼接 / 跨页续段 / 页眉页脚丢弃 / 双栏投影切分 / 标题自成块
- 术语表：`quote` 在原文逐字命中才 `locked`，locked 术语全篇同名
- 未译标注：`target` 留空 + `uncertain=true` + `notes` 写原因；禁止 `TBD`/`待写`/`...` 占位
- 数字与标记：数字、单位、`[1]`、`(1)`、`Fig. 1`、`Table 1` 按原文保留（多重集比对）

详见包内 SKILL.md 与 `references/checks_spec.md`（核验口径 + 术语表模板 + 题集/评分表模板）。

## 5 限制与维护

- 机械核验只覆盖结构、数字/单位、引用/图表编号、公式号、术语一致性、否定与限定关系、可定位性；通顺度与措辞进
  `human_review` 交人工；极端排版（表格套表格、脚注混排）的切段保守处理并记 `warnings`
- 术语可长期维护：把 `glossary.json` 中 `locked` 条目搬进新用例的 `draft.json.glossary` 即继承译名
- 改脚本后先跑 `selfcheck`（含降级场景自检），再跑 `compare` 确认指标未回退
