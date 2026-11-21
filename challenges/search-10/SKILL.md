# search-10 · 术语表驱动的跨语种 known-item 检索（cross-lingual search）

给定材料（问题 + 内置术语表 + 视图/版本文件），把「概念 → 各语种写法 → 逐语种查询式 → 命中证据
→ work 级去重」做成**可独立复核**的固化产物。关键约束：

- 每个概念锚点、每条术语对齐、每条命中都必须带 `locator`（`materials/x.md#L20`）与**逐字引文**；
- 材料没有的概念写 `not-in-glossary` 并进 `pending_human`，**绝不臆造译法**；
- 同一 work 的原文 / 全译 / 摘要版 / 副本**去重后**才计数，`abstract_only` 不作为正文命中证据。

## 契约（output_contract）

`case.json` 给出 `output_contract` 时以它为准；否则用下列内建键（边界用例同样输出这套键）。
每个键在 `result.json` 顶层与嵌套 `output_contract` 对象里各回填一次，两处完全一致：

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

## 单命令（one-shot，评测入口）

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
```

- 一条命令走完：扫描材料 → 解析内置术语表 → 检出材料**实际陈述**的概念锚点 → 生成逐语种查询式
  → 跨语种术语对齐 → 视图台账与去重 → 命中卡 / misses → 增益指标 → 落盘。
- **无 `draft.json` 也照常跑完**：仍产出完整契约、全部交付物与 `result.json`，`exit 0`。
- 不调用任何翻译接口；`translation_service` 字段写明 `none (offline-builtin-glossary)`。

## 分步命令（agent 增强路径）

```bash
python3 scripts/main.py init  --input /input --output /app/output --work /app/work
python3 scripts/main.py show  --input /input --lang pt
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output --work /app/work
```

- `init` 建索引、写 `work/draft.skeleton.json` 与部分 `result.json`（`status=drafting`）。
- `show` 按语种/关键词打印「概念 → 术语 → 定位符」，便于人工写 `work/draft.json`。
- `check` 机械校验 D0–D8 / K1–K4：每题是否有语种与目标语种、视图是否可解析、match 是否带逐字
  quote、quote 是否**逐字命中**材料、去重口径是否与脚本一致；报告写入 `work/check_report.json`，
  永远 `exit 0`。
- `build` 用 `work/draft.json`（若存在）+ 规则抽取正式成稿；`all` = `build` + `selfcheck`。

## 交付物（每次运行写入 --output）

| 文件 | 内容 |
|-|-|
| `result.json` | 顶层 + 嵌套 `output_contract` 契约回填、`coverage`、`gain_metrics`、`metrics`、`term_alignment`、`views`、`answer_cards` |
| `search_report.md` | 主报告：目标/语种路由、逐语种查询式、术语对齐表、视图台账、命中与缺口 |
| `lang_queries.md` | 逐语种查询式（含查询模板与回译校验规则），供人复核与复用 |
| `query_plan.json` | 机读查询计划（concept × language），每条带 basis 与 locator |
| `glossary_index.json` | 术语表索引，含**来源 / 许可 / 版本 / 翻译服务**说明 |
| `answer_cards.json` | 每题命中卡或 misses（不写空壳） |
| `reconciliation.md` | 对账与去重口径（views / distinct_works / duplicates） |
| `check_report.json` | 机械校验报告（D/K 项） |
| `evidence.json` | 每条事实的 locator、逐字引文与命中统计 |
| `baseline_comparison.md` | 与朴素基线的对照（诚实声明：基线为确定性模拟） |

## 翻译服务与版本

本包**离线运行**，不接入任何翻译服务，因此：

- `translation_service = {name: none, version: offline-builtin-glossary}`；
- 术语对齐只来自内置术语表 `builtin:<cid>`，每个写法都能回查到术语表行；
- 若未来接入翻译接口：接口失败/限额时**降级为内置术语表**并把该概念写入 `pending_human`，
  绝不把接口直译结果当作术语对应的最终结论（见 `templates/query_templates.md` 的降级分支）。

## 术语表来源、许可与版本

术语表由材料内 `glossary.md` 的 `tsv` 代码块提供，脚本从文件头解析并写进
`glossary_index.json` 的 `source` / `license` / `version` 字段；本包内置默认值
`version = builtin-1`、许可 `MIT`、来源「作者自编通用科研方法学词汇」。术语表只覆盖**概念级**对齐，
人名/机构/期刊/疾病亚型等专名靠 `DOI / 引号短语 / 作者姓 / 年份` 四个专名锚点匹配。

## 异常与降级（可靠体验）

| 情形 | 处置 |
|-|-|
| 术语表无该概念 | 写 `not-in-glossary` → `pending_human`，不臆造译法 |
| 语种不确定 | 声明元数据 > 文件名标记 > 停用词比值检测；冲突时以声明为准并记入 `basis` |
| 翻译服务不可用/限额 | 离线内置表；未来接入时降级并记 `pending_human` |
| 原文不可得（仅摘要） | `abstract_only` 入台账但不作正文命中证据 |
| 原文与译文版本冲突 | `preprint`/`erratum` 与正式版冲突写 `uncertainties` |
| 材料无题面 / 无视图 | 如实 `partial` / `insufficient_evidence`，不伪造命中卡 |
| 坏 JSON / 空文件 | 登记 `degradations`，仍写合法 `result.json`，`exit 0` |

## top_fix → 实现

| top_fix | 实现 |
|-|-|
| 逐语种查询式固化 | `build` 输出 `lang_queries.md` + `query_plan.json`；模板与规则见 `templates/query_templates.md` |
| 增益指标 + `gain_metrics` | `result.gain_metrics`（非英语语种数、术语对齐对数、翻译调用 0 次、人工核对条数、命中率）+ `baseline_comparison.md` |
| 自动 draft 生成 | `build` 缺稿时由术语表 + 视图指纹直接产出高置信候选，不依赖人工写 `draft.json` |
| 题集 / 案例 | `templates/query_templates.md` 内含 3 个跨语种案例与评测题；`examples/` 提供可复跑 fixture |
| 术语表来源/许可/版本 | `glossary_index.json` 四字段 + 本文件「术语表来源、许可与版本」+ 翻译服务说明 |
| GITHUB_URL 校验 | `GITHUB_URL.txt` 指向 `challenges/search-10`，与作品目录一致 |
