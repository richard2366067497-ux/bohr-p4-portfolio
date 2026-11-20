# research-frontier-event-timeline — 事件台账优先的前沿趋势分析（research-04 v6）

把一批科研材料整理成**有年份、可回链的有向事件台账**，再由台账派生年度分布、阶段划分、转折事件、
代表性工作与研究空白，产出可逐条复核的 `result.json` 与完整产物。核心约束：

- 每条事件必须有 `source_id` + `locator` + **逐字 quote**；年份缺失记 `unknown`，不猜。
- 趋势统计由台账聚合，**台账-统计守恒**可独立复算。
- 空白必须给"事件证据 + 检索范围 + 排除证据"，不把"没检索到"写成"全球空白"。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构，不写类型串/占位符。

## 安装

仅 Python 3.9+ 标准库，离线，无需第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py  scripts/core.py  scripts/derive.py  scripts/audit.py
  references/event-typology.md  references/draft-schema.md  references/rubric-map.md
  GITHUB_URL.txt  README.md  SELFTEST.md
```

## 用法

### 单命令（无草稿也产出完整产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描输入 → 建索引 → 事件台账（无 draft 时用规则化候选，标 auto/low）→ 年度统计/阶段/转折/空白
→ 时间线/趋势报告/证据矩阵/SVG → `result.json`（契约逐键回填 + case_id 透传）→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat/--ids）
# Agent 读材料、写 /app/work/draft.json
python3 scripts/main.py check      # 校验字段/quote 命中/统计守恒/阶段依据/空白证据
python3 scripts/main.py build      # 生成台账/时间线/派生/图/最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 主结果：契约顶层 + `output_contract` 逐键回填、case_id、status、sources、事件、统计、阶段/转折/空白、证据矩阵、coverage、limits、uncertainties、change_records |
| events/event_ledger.jsonl | 逐条事件台账（逐字原文，供复核） |
| events/event_sources.json | 来源登记、每源事件数、无事件原因、抽取规则 |
| timeline.md | 按年升序的时间线与阶段标记 |
| trend_report.md | 趋势分析报告（每条结论后带事件 id） |
| derived/trend_stats.json | 年度/类型/主题分布与增长（由台账重算） |
| derived/stage_division.json | 阶段划分与依据事件 |
| derived/turning_points.json | 转折事件与判定准则 |
| derived/gaps.json | 研究空白（含排除证据） |
| derived/representative_works.json | 各阶段代表作 |
| figures/timeline.svg | 事件时间线图 |
| figures/figure_specs.json | 图规格（数据源、字段映射） |

## 降级与边界

- 空输入 / 坏 JSON / 缺 case.json：仍写合法 `result.json`，`status=insufficient_evidence` 或 `partial`，**exit 0**。
- 无 draft：`all`/`build` 用规则化候选台账（auto/low），仍产出全部产物，缺口写入 `degradations`。
- 事件无年份：不猜测；阶段/转折/空白给诚实的 no-data 说明。
- 不做显著性检验；样本小（事件 ≤20 或来源 ≤10）时结论只能"提示性/初步"。
- 不联网、不安装工具、不臆造缺失数据。

## 维护

版本 1.2.0；契约键名冻结，规则判据集中在 `SKILL.md` 与 `references/`。
改了脚本必须重跑：`--help`、空 `/input`、坏 JSON（三者均 exit 0），并跑一次自测（见 SELFTEST.md）。
