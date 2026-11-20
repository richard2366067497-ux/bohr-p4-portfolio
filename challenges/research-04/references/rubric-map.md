# 评分维度 → 产物 / 检查项映射，与复用指南

本文件把题面五维 rubric 落成可检查的对象，便于评审逐项核对，也便于他人改造成新领域版本。

## 1. 实际效果（40 分）

| 评分点 | 本包的对应产物 | 可复核方式 |
|---|---|---|
| 任务完成度 15 | `events/event_ledger.jsonl`、`timeline.md`、`derived/{trend_stats,stage_division,turning_points,gaps}.json`、`trend_report.md` | 四类产物在 `result.json.deliverable` 中逐项列出；`selfcheck` 检查每份非空 |
| 结果正确性 15 | 事件的 `quote`+`locator`；`year`+`year_source`；`statement` 不含评价；统计由台账聚合 | `check` 的 `QUOTE_MISS`/`LOC_MISS`/`QUOTE_NOT_IN_LOCATOR`/`EV_STATEMENT_EVALUATIVE`；`selfcheck` 的"台账-统计守恒" |
| 结果完整性 5 | 年份跨度、主题层级（`theme_id` 多值）、各阶段代表作（`representative_works` 覆盖每阶段）、空白类型（五类枚举） | `result.json.coverage`（`years_covered`、`themes`、`event_type_coverage`、`small_sample`）；`REP_STAGE_UNCOVERED` 提示 |
| 结果可核验性 5 | 检索/纳排说明（`events/event_sources.json`，含 `no_event_reason`）、年份口径（`method_notes.year_basis`）、主题归并（`theme_merge_rules`）、统计表、结论→事件 id 回链 | 任一结论可在台账中按 `event_id` 找到 `source_id`+`locator`+`quote`；`figure_specs.json` 声明图的数据列与重绘命令 |

## 2. 使用增益（25 分）

| 评分点 | 本包的对应 | 相对"基础 Agent"的差异 |
|---|---|---|
| 质量增益 15 | 事件类型学 + 转折 criteria + 空白判据（含排除证据） | 基础 Agent 通常输出"前 N 条 = 前沿"；本包强制输出类型构成、阶段依据、缺口结构 |
| 效率增益 5 | `init` 一次完成材料登记/切段/年份初判；`build` 一次完成台账+统计+三份派生+SVG+信封 | 省去手工补年份、手写统计表、重复核对引文；`runtime.counts` 记录来源/事件/阶段数 |
| 增益可验证性 5 | `selfcheck` 的 16 项磁盘复检；`change_log`；`runtime.files` 字节数 | 任何人可重跑 `check`/`selfcheck` 得到与提交一致的数字 |

> 注意：公平对照（对照白板）由平台生成，本包不自造分数、不声称"提升 X%"。

## 3. 创新增益（15 分）

| 评分点 | 实现 | 证据 |
|---|---|---|
| 新增能力 5 | **event-first**：统计是台账的派生视图，不是起点 | `derived/trend_stats.json.recomputed_by = derive.compute_stats(event_ledger)`；`selfcheck` 重算比对 |
| 方法改进 5 | ①台账-统计守恒 ②转折事件作为代表作口径（避免高被引排序）③空白由事件类型缺口推导（`missing_validation`/`stalled_theme`/`no_transfer`/`unresolved_conflict`/`retrieval_gap`）④事件类型时序一致性（`CHRONO_CONFLICT`） | 对应 `core.validate` 的检查分支与 `derive.derive_turnings`/`derive_gaps` |
| 创新证据 5 | 同一批材料下"按年计数"与"按事件类型计数"给出不同结论（例：2020 年事件数 4，但其中 2 条是 `declined`/`split`，说明该年不是"产出高峰"而是"路线分化"） | 报告第 2 节年度表 + 第 3 节主题演化表并列呈现计数与类型构成 |

## 4. 可靠体验（10 分）

| 评分点 | 实现 |
|---|---|
| 调用与易用性 3 | 五命令固定入口；`init` 打印语料表与下一步命令；`show` 支持 `--sources/--mat/--ids/--grep/--limit` |
| 运行稳定性 4 | 恒 exit 0；`init` 第一步即写合法 partial `result.json`；单文件解析失败不影响其余；重复 `build` 幂等 |
| 异常处理 3 | 缺 `case.json`→递归找契约 JSON→内置默认契约；空输入/无材料→`insufficient_evidence`；坏 JSON→降级并记录；缺 `draft`→规则化兜底台账（`auto/low`）+ `degradations` |

## 5. 生态贡献（10 分）

| 评分点 | 实现 |
|---|---|
| 文档完整性 3 | `SKILL.md`（用途/契约/五步/降级/自查/示例）+ 本目录三份 references（类型学、字段字典、评分映射） |
| 资源可复用性 4 | 事件类型学与判据表可跨领域复用；`scripts/core.py` 解析器支持 PDF/DOCX/XLSX/MD/JSON/JSONL/CSV；换领域不改代码 |
| 分享推广价值 3 | 五步方法（年份归一→事件抽取→时间线→派生→空白）可作为"趋势分析"类任务的通用骨架；`figure_specs.json` 让图可重绘 |

## 6. 反模式清单（提交前自查）

- [ ] 报告里出现"重要突破/里程碑/显著上升"等无证据或小样本强断言（`CLAIM_OVERREACH`）。
- [ ] 按年计数被当成"热度"，未给类型构成。
- [ ] 代表作按总被引或按"最先读到"选取，无 `criteria_hit`。
- [ ] 空白条目缺 `exclusion_evidence`，实质是检索遗漏。
- [ ] 统计表与台账不一致（手工改过数字）。
- [ ] `result.json` 的契约字段被改名/嵌套（`contract_fill.null_fields` 非空且未解释）。
- [ ] 事件 `quote` 经过翻译或拼接。

## 7. 换领域复用指南

1. **不改代码**：材料放进 `/input`（任意子目录），`init` 按扩展名+魔数识别、自动切段编号。
2. **改类型学**：若领域事件类型不同（如临床研究的"入组/随访/终点达成"），改 `scripts/core.py` 的 `EVENT_TYPES`+`CUES`，并同步本目录 `event-typology.md` §2/§3（两处必须一致）。
3. **改判据**：阶段依据、转折 criteria、空白判据在 `derive.py`（机械候选）与 Agent 工作稿（最终判定）两层；只改文档不改代码也能生效，因为 criterion 值最终由工作稿给定。
4. **改阈值**：小样本阈值 `<=20 事件 / <=10 来源` 在 `derive.coverage`；放宽会降低对强断言词的拦截力度。
5. **回归**：任何改动后必须重跑（a）`--help`（b）空 `/input`（c）坏 `case.json`（d）完整最小案例，四项均 exit 0 且 `result.json` 合法。

## 8. 版本与维护

- 版本 1.0.0。脚本仅标准库，无网络请求，无外部服务、无字体依赖（SVG 用系统 sans-serif）。
- 已知限制：SVG 是静态图（无交互）；PDF 内置解析为 `builtin-pdf-lowconf` 质量，复杂版式需 `pdftotext`；不做 OCR，图片材料只登记不解析。
- 变更记录写在 `result.json.change_log`（含 draft 的 `sha256_16`、事件数、是否兜底、status），便于对齐"提交版本"与"运行版本"。
