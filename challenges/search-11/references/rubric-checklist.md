# 评分点对照与复用清单（rubric-checklist.md）

配套 `patent-search-dossier` v1.0.0。用途：把题面评分维度逐条落到**可检查的字段与命令**，并把包做成他人可复用的查新流程。
本文件中的字段名与 `SKILL.md`、`scripts/` 一致；改动请同步三处。

## 1. 评分维度 → 落点 → 自查方法

| 维度（分值） | 评分点 | 本包落点 | 自查命令 / 字段 |
|---|---|---|---|
| 实际效果（40） | 任务完成度 15 | 号码检索与主题检索都能走通；六件产物齐全；`query.kind=both` 时两条线都有结果 | `build` 输出行；`result.counts` |
| | 结果正确性 15 | 号码 `norm` 与规则链可复核；状态不编造（unknown 如实）；引文逐字；族边有证据 | `check` R2/R3/R4/R6/R7；`number_registry.entries[].rules` |
| | 结果完整性 5 | 目标专利/同族/状态/权利要求/技术文献/许可六面 + 边界与遗漏 | `result.coverage._summary.facets_hit` ≥ 6/8 |
| | 结果可核验性 5 | 每条结论带 `source_id`+`locator`+`quote`；`show --id M#` 可回看原文 | `evidence_map[]`、`status_provenance.csv` |
| 使用增益（25） | 质量增益 15 | 号码规范化 + 状态三字段纪律 + 族口径显式化，减少"摘要即结论"的错误 | `dossiers.md` §2/§3 表 |
| | 效率增益 5 | 一条 `show` 拿到带 locator 的号码/族/状态/许可/文献候选；五命令一次成型 | `init` + `show` 输出 |
| | 增益可验证 5 | 同输入同口径可复跑：`selfcheck` 指纹一致，`runtime.input_fingerprint` 可对照 | `selfcheck` 的 `input_fingerprint_stable` |
| 创新增益（15） | 新增能力 5 | 号码规则链（含 PCT/国别推断）、族 `simple/extended`+`not_exhaustive`、许可绿黄红闸门、边界日志 | `number_registry.rules`、`family_graph.works`、`license_gate.md` |
| | 方法改进 5 | 状态 `as_of/source_kind/needs_official_verification` 三字段强制；OCR 容错证据核验（≥0.90 标 `ocr_tolerant`） | `check` R5/R6、`evidence_map[].match` |
| | 创新证据 5 | 降级链路可演示：缺稿/坏 JSON/空材料三例均 exit 0 且产物合法 | `result.degradations` |
| 可靠体验（10） | 调用易用 3 | 五命令主路径写在 `SKILL.md` §0；`--input/--output/--work` 与环境变量双通道 | `--help` |
| | 运行稳定 4 | 纯标准库、不联网、不依赖 CWD；异常捕获；退出码恒 0 | 三例降级测试 |
| | 异常处理 3 | 限流/鉴权/无命中/状态冲突/字段缺失/授权不足分别有处置（`SKILL.md` §12） | `errors[]`、`degradations[]`、`boundaries[]` |
| 生态贡献（10） | 文档完整性 3 | `SKILL.md` 用途/调用/契约/方法/边界/失败/自查齐；本文件与 `field-dictionary.md` 补口径 | 文件清单 |
| | 资源可复用 4 | 号码规范表、状态分级、许可模板、边界模板、检索式模板均可直接套用新案例 | `field-dictionary.md` §2–§8 |
| | 分享价值 3 | 一套可复制的"号码—族—状态—文献—许可"查新流程，含降级方案 | `SKILL.md` §1 五问 |

## 2. 交付前自查（逐条打勾）

1. `result.json` 的 `output_contract` 键与输入完全一致，`case_id` 对得上。
2. 六件产物非空：`dossiers.md`、`number_registry.json`、`family_graph.json`、`status_provenance.csv`、`license_gate.md`、`boundary_log.json`。
3. `check` 输出 `FIX 0`（或每条 error 都能解释为材料缺失）。
4. `counts.evidence_ratio` ≥ 0.9；`coverage._summary.facets_hit` ≥ 6。
5. 每个状态条目都有 `as_of` + `source_kind` + `needs_official_verification`；非官方来源一律 true。
6. 族边都带 `evidence_locator`；`family_graph.works[].not_exhaustive=true`。
7. red 来源没有出现在任何引文里；`license_gate.md` 列明被排除原因。
8. `boundaries` 覆盖实际触发类型（unknown 状态 / 族边 / OCR / 未解释范围 / 两类文献 / 受限来源）。
9. `gaps` 写清缺什么、何时补。
10. `selfcheck` 的 `checks` 全 true；不通过项有解释。

## 3. 复用方式（换一个案例只改输入）

| 想改什么 | 改哪里 | 不改什么 |
|---|---|---|
换案例材料 | 只换 `/input`（`case.json` + `materials/**`）；文件名任意，`init` 按内容分诊 | 脚本与 SKILL.md |
换契约字段 | 无需改包：`output_contract` 的键会按语义关键字自动映射（`main.py` 的 `CONTRACT_MAP`） | — |
换号码国别/格式 | 在 `scripts/registry.py` 的 `normalize_number()` 增规则，并在 `field-dictionary.md` §2 加一行 | 其余校验 |
换状态口径 | 改 `dossier.py` 的 `SOURCE_KINDS`/`STATUS_VALUES` 与 §3 表 | 渲染 |
换许可分级阈值 | 改 `registry.py` 的 `_tier()` 关键词与 §5 表 | 产物结构 |
换产物表头 | 改 `render.py` 的对应渲染函数与 `references/` 模板 | 契约键 |

## 4. 维护与已知边界

- 段落定位以空行/6 行切段（`registry.paras`），PDF 粗解析可能丢阅读顺序：重要引文先 `show --id` 回看。
- OCR 容错匹配用 3-gram 覆盖率 ≥0.90，可能把近似表述判为命中，结果标 `match=ocr_tolerant`，不等同官方核对。
- 许可分级基于关键词，材料措辞罕见时可能判 `None` → 按 yellow 处理并进 `gaps`，不静默放过。
- 不抓取任何网络资源；受限来源只登记不引用；不做侵权/FTO/价值判断，不提供法律意见。
- 号码推断（无国别）一律 `ambiguous`，不冒充确定号码；推断结果在 `rules` 里可追溯。

## 5. 最小示例（示例，非正式案例结果）

```bash
$ python3 scripts/main.py check --input ./input --output ./output --work ./work
== check == draft work/draft.json
号码 5 | 对象 3 | 族边 2 | 状态 3 | 权利要求 1 | 文献 1 | 许可 5 | 边界 7
证据 9/9 (100%) | 检索面 8/8 | PASS
$ python3 scripts/main.py build --input ./input --output ./output --work ./work
== build == ok | agent | dossiers.md 5.9 KB | 号码 5 | 族边 2 | 状态 3 | 文献 1 | 边界 7 | 契约 8/8
```

以上数字仅用于说明输出形态与接口，**不是任何正式案例的评测结果**。
