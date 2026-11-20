# result.json 字段字典、契约回填与三指针语法

本文件回答三件事：`result.json` 里有什么、`output_contract` 的字段怎么保证一个不漏、
每条分数怎么顺三指针追回原始输出。实现见 `scripts/litio.py`（`fill_contract` / `shell` / `prep` /
`save` / `resolve_ref` 的调用方）与 `scripts/ledger.py`。

## 1. 信封字段（恒存在）

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | str/null | 来自 `case.json` 的语义识别（`case_id`/`caseId`/`task_id`/`sample_id`/`id`） |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `stage` | str | 最后落盘阶段：`init`/`show`/`check`/`build`/`selfcheck`/`<verb>/error` |
| `skill` | obj | `{name, version}` |
| `sources[]` | array | 材料清单：`id/name/path/kind/bytes/sha1/paragraphs/chars/status/method/note/native_ids` |
| `outputs{}` | obj | 十件产物的相对路径（`result.json` + `benchmark/*`） |
| `benchmark{}` | obj | `mode`、`n_items`、`set_id`、`set_version`、`n_rejected`、逐题分数映射 |
| `anchors{}` | obj | `{n, verified}`，明细在 `benchmark/anchors.json` |
| `scoring{}` | obj | `{aggregate, closure}`，明细在 `benchmark/scores.csv` 与 `scoring_records.json` |
| `coverage_matrix{}` | obj | 六轴状态 + `verdict` |
| `calibration{}` | obj | 探针校准：`n_probes/n_agree/n_disagree/agreement` |
| `version_record{}` | obj | 版本三元组 + 可比性判定 |
| `failures[]` | array | 失败样例（与 `benchmark/failures.md` 同源） |
| `uncertainty[]` | array | 明确的不可判断项与降级 |
| `pending_human[]` | array | 需人工接管的条目 |
| `errors[]` | array | `{stage, item?, error, traceback?}` |
| `degradations[]` | array | `{item/material, issue, action}` |
| `changes[]` | array | `{what, mode?, why}` |
| `technical_synthetic{}` | obj | `{present, not_a_dsh_score, kind, scored, sources, note}` |
| `runtime{}` | obj | 版本、python、时间、三根目录、argv、`self_audit`、`selfcheck` |
| `contract_fields_present[]` | array | 契约声明的字段名（原序） |
| `contract_echo` | obj/array | 契约原文 |
| `contract_fill{}` | obj | `{字段: {filled: bool, from: 匹配方式}}` |

## 2. 契约回填规则（一个键都不许丢）

1. `output_contract` 的键**全部出现在顶层**，键名逐字保留（不改名、不加前缀、不排序丢失）；
2. 匹配顺序：**精确同名 → 语义映射表 → 契约镜像（同形空结构）→ 占位**；
3. 占位规则：复数/列表型键给 `[]`，其余给 `null`；绝不整键消失；
4. `contract_fill` 逐键记录用了哪种匹配，`from` 取值 `exact` / `semantic:<ctx>` /
   `contract_mirror` / `placeholder`——一眼看出哪个字段是真空缺；
5. `contract_fields_present` 保留声明顺序，供核对“有没有漏键”。

语义映射表（`scripts/litio.py: CTX_MAP`，按关键词就近匹配）：

| 契约键含 | 回填值 |
|---|---|
| `status` / `state` | 运行状态 |
| `result` / `final_result` | 题集元信息 + 题卡 + 分数映射 + 汇总 + 面板路径 |
| `claim` / `finding` / `conclusion` | 锚点式结论（`{claim, item_id, locator, quote, verified}`） |
| `uncertaint` / `caveat` | 不确定性数组 |
| `anchor` / `evidence` / `quote` / `locator` | 锚点表 `{n, n_verified, anchors}` |
| `score` / `scoring` / `rubric` / `panel` / `metric` | 评分汇总（分布、均值、按 agent/题型） |
| `failure` / `reject` / `issue` | 失败样例数组 |
| `version` / `diff` / `compar` / `history` | 版本记录 + 可比性 |
| `item` / `card` / `question` / `task` / `answer` | 题卡集合 |
| `coverage` / `completeness` | 六轴覆盖矩阵 |
| `source` / `material` / `document` | 材料清单 |
| `output` / `artifact` / `path` | 产物路径表 |
| `checker` / `synthetic` | 技术性合成日志声明 |

## 3. 三指针语法与闭包

`benchmark/scores.csv` 每行三个指针，`selfcheck` 逐行解析，输出 `closure_rate`：

| 指针 | 指向 | 本包取值示例 |
|---|---|---|
| `raw_output_ref` | 被评文本原文 | `benchmark/raw_outputs.json#/items/3/text` |
| `config_ref` | 本次运行配置 | `benchmark/run_config.json#/run_config_hash` |
| `scoring_record_ref` | 评分记录（含规则、覆盖率、依据） | `benchmark/scoring_records.json#/records/3` |

指针语法（`scripts/core.py: resolve_ref`）：

```
<相对路径>#/a/b/0       JSON Pointer（~1 → /，~0 → ~）
<相对路径>#row=N        CSV 第 N 数据行（1 起，含表头偏移）
<相对路径>#L3-L9        文本行区间
<相对路径>              只校验文件存在
```

解析失败不静默：写入 `scoring.closure.failures`（行号 + 字段 + 原因），并把该行计入
“不可追”集合；`coverage_matrix.raw_output_retention` 同步下降，`selfcheck` 报 FAIL。

## 4. 运行契约（官方 Harness）

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`output_contract`、`task_instruction` 等）+ `/input/task.md` + 材料 |
| 工作 | `/app/work`：`index.json`、`workorder.json`、`draft.json`、`check_report.json`、`selfcheck.json` |
| 输出 | `/app/output/result.json` + `/app/output/benchmark/`（9 件） |
| 退出码 | 恒 0；异常写 `errors[].traceback` 并落合法 partial `result.json` |
| 依赖 | Python 3 标准库；不联网；路径由 `Path(__file__)` 推导，与 CWD 无关 |
| 路径覆盖 | `--input/--output/--work` 或 `LITREAD_INPUT/LITREAD_OUTPUT/LITREAD_WORK`（子命令前后均可写） |
| 预算 | 64 次请求 / 900 秒 / 单响应 16384 token；`init` 一跑即落合法 partial |

## 5. 产物清单（`/app/output/benchmark/`）

| 文件 | 内容 | 谁读 |
|---|---|---|
| `cards.json` | 题集快照：`items[]`、`rejected[]`、`workorder_coverage[]`、版本四元组、`item_ids_sha1` | 复核人、下一版 |
| `anchors.json` | 引文抽查表：`material/locator/native_id/page/quote/verified/match` | 抽查引文 |
| `raw_outputs.json` | 被评原文（探针答案 + 候选输出，逐字留存） | 追分 |
| `scoring_records.json` | 每条记录：`score/status/coverage/basis/rule/expected/agreement` | 判分依据 |
| `scores.csv` | 逐行台账 + 三指针 | 汇总、复算 |
| `run_config.json` | 口径、阈值、匹配方式、预算、权限、`run_config_hash` | 复现 |
| `panel.md` | 材料/题卡/得分/分布/六轴矩阵/校准/版本 | 汇报 |
| `failures.md` | 失败样例 + 下一版专项题建议 | 改进 |
| `version_diff.json` | 当前版本、历史、可比/不可比判定、规则 | 版本对比 |

## 6. 状态判定

```
input_error           ⇐ 无材料
insufficient_evidence ⇐ 有材料但无可用段落
ok                    ⇐ 全 agent-authored、无 error、无拒收、六轴无缺、校准全对
partial               ⇐ 其余（含 fallback、被拒卡、校准不一致、六轴有 partial）
```

`status=partial` 不是失败：它表示“交付完整但已知降级”，降级原因同时写在 `degradations`
（机器）与 `panel.md §6`（人读）里。

## 7. 版本与维护

- 改评分口径 → 升 `scale_version`（`scripts/ledger.py: run_config`），旧分数自动判为
  `incomparable`，必须按新口径重算才可比；
- 改题卡集合 → 升 `set_meta.version`；`item_ids_sha1` 会同时写进 `cards.json` 与
  `version_diff.current`，供“只对交集题比”；
- 改运行条件（权限/预算/模型）→ `run_config_hash` 变，历史分数标记不可比；
- 包内文件改动后重跑 `init → show → check → build → selfcheck`，确认 `closure_rate=1.0`、
  `calibration.agreement=1.0`、`coverage_matrix.n_missing=0`。
