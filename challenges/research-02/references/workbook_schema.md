# 工作稿与产物 schema（outline-slot-review v1.0.0）

本文件是字段字典：`/app/work/draft.json`（你写）→ `/app/output/*`（脚本生成）→ `result.json`（契约回填）。
字段名可少量兼容别名（脚本会归一），但**建议照本文件写**，避免歧义。

## 1. 定位符（locator）

```
<相对输入根的路径>#B<块号>S<句号>@<起始字符>-<结束字符>
例：sources/S01_trial.md#B5S1@455-588
```

- 块 = 以空行分隔的段落；句 = 块内按 `。！？!?` 与英文 `. ` 切分。
- 字符偏移相对该文件的完整文本（含换行），可被任何编辑器独立回查。
- locator 可由 `show --source Sxx` 直接复制；只在同一份材料的文本未被改动时有效。

## 2. `draft.json`（工作稿，由 Agent 亲自写）

```json
{
  "case_id": "与 case.json 一致",
  "research_question": "一句话研究问题",
  "protocol": {"scope": "检索范围", "time_window": "2015-2024", "languages": ["en","zh"],
               "criteria_frozen": true, "amendments": []},
  "outline_basis": "为什么这样分节（基于文献分布的哪条事实）",
  "criteria": [ {"criterion_id":"IC1","type":"include","statement":"...","judge_rule":"...","priority":1,"stage":"title_abstract"} ],
  "screening": [ {"record_id":"R01","source_id":"S01","stage":"title_abstract","decision":"include",
                  "criterion_ids":["IC1"],"reason":"...","locator":"..."} ],
  "outline": [ {"sec_id":"SEC1","heading":"...","purpose":"本节要回答什么","section_label":"benefit",
                "lead":"可选：节首导语","lead_slot_ids":["SL1"],
                "slots":[{"slot_id":"SL1","claim_prompt":"该槽位要填的论断","required_evidence":"需要什么证据","section_label":"benefit"}]} ],
  "slots": [ {"slot_id":"SL1","state":"filled","claim":"一句论断","strength":"moderate","polarity":"supports",
              "conflicts_with":["SL3"],
              "evidence_refs":[{"source_id":"S01","locator":"sources/S01_trial.md#B5S1@455-588","quote":"逐字原句"}]},
             {"slot_id":"SL4","state":"gap","gap_reason":"...","gap_type":"retrieval_gap",
              "search_scope":"数据库+检索式+年份","missing_evidence":"具体缺什么数据"} ],
  "method_notes": {"strength_rule":"...","render_rule":"...","theme_rule":"..."}
}
```

### 2.1 字段字典

| 字段 | 取值 | 判据 |
|---|---|---|
| `criteria[].type` | `include` / `exclude` | 至少各 1 条；`exclude` 优先于 `include` 判定 |
| `criteria[].judge_rule` | 可机械判定的语句 | 写"出现指标 X 且为成人"这种能落到文本的判据，不写"高质量"这类主观词 |
| `criteria[].stage` | `title_abstract` / `full_text` | 两阶段筛选：先题录后全文 |
| `screening[].decision` | `include` / `exclude` / `pending` | `exclude`/`pending` 必须挂 `criterion_ids` 与 `reason` |
| `screening[].locator` | locator 或题录标识 | 用于回查该判定依据的原文位置 |
| `outline[].purpose` | 一句话 | 说明该节服务于研究问题的哪一面 |
| `outline[].lead_slot_ids` | 槽位 id 列表 | 有 `lead` 就必须有；否则草稿出现无回链句 |
| `slots[].state` | `filled` / `gap` | 只有这两态；"不知道但写了"不允许 |
| `slots[].claim` | 一句可判定命题 | 不写结论性空话；不引入材料外的数字 |
| `slots[].strength` | `strong` / `moderate` / `weak` | 受 §3 判据约束，超标会被下调并记录 |
| `slots[].polarity` | `supports` / `counter` | `counter` 会在草稿中以"与此相反"另起段 |
| `slots[].conflicts_with` | 槽位 id 列表 | 结论相反的槽位互指；build 自动补对称 |
| `evidence_refs[].quote` | 逐字原文 | 必须能在 `source_id` 文本中找到；改写即视为不通过 |
| `gap_type` | `retrieval_gap` / `unresolved_conflict` / `method_limitation` / `scope_limit` | 只允许这四类 |
| `search_scope` | 数据库 + 检索式 + 年份 | 缺检索范围的缺口不可复核 |

## 3. 强度判据（脚本复算，用于校验自评）

`score = 最佳设计分 + (独立来源≥2 ? 1 : 0) − (存在冲突 ? 1 : 0)`

| 设计 | 分值 | | 分档 | 阈值 |
|---|---|---|---|---|
| 系统综述/荟萃、指南/共识、RCT | 3.0 | | strong | ≥3.8 |
| 队列、病例对照 | 2.0 | | moderate | 1.8–3.7 |
| 横断面、调查 | 1.5 | | weak | <1.8 |
| 叙述综述、预印本、体外/动物、未标明 | 1.0 | | 封顶 | 仅摘要或预印本 → ≤ moderate（2.4） |
| 病例报告 | 0.5 | | | |

自评高于判据 → `check` 报 `Q107`，`build` 下调并写入 `changes`；自评低于判据保留（保守允许）。

## 4. 产物清单（`/app/output`）

| 文件 | 内容 | 用途 |
|---|---|---|
| `draft.md` | 主产物：由已填槽位渲染的综述草稿 | 每段末尾 `[SLx]` 回链槽位，`[Sxx]` 为引文来源 |
| `outline/skeleton.json` | 节→槽位骨架（含 purpose、lead_slot_ids） | 结构可复核 |
| `slots/filled.jsonl` | 已填槽位：claim、strength、polarity、conflicts_with、evidence_refs | 证据表 |
| `slots/gaps.jsonl` | 缺口：gap_type、gap_reason、search_scope、missing_evidence | 空白可复核 |
| `screening/criteria.json` | 先冻结的纳排条款 + protocol | 标准先于筛选的证据 |
| `screening/screening_log.jsonl` | 逐条记录决策与理由 | 筛选留痕 |
| `screening/check_report.json` | 最后一次校验的完整问题清单 | 排错入口 |
| `gap_report.json` | 缺口汇总 + 研究空白（由缺口字段推导）+ 套话标记 | 空白有据 |
| `coverage.json` | 覆盖统计：纳入/排除/重复/槽位/已填/覆盖率/引文数 | 增益可量化 |
| `changes.json` | 构建期修补记录（引文纠正、强度下调、冲突对称、槽位转缺口） | 变更可追溯 |
| `selfcheck.json` | 独立复检结果 | 交付前闸门 |
| `result.json` | 契约回填 + 信封 | 平台读取 |

## 5. `result.json` 结构与契约回填

```json
{
  "<output_contract 的每个键>": "按语义回填：散文类→draft.md 全文；表类→槽位/筛选/缺口行；统计类→coverage；状态类→status",
  "case_id": "原样", "status": "ok|partial|input_error", "skill": "outline-slot-review", "skill_version": "1.0.0",
  "contract_map": {"<契约键>": "<对应产物相对路径>"},
  "artifacts": {"draft": "draft.md", "outline": "...", "slots_filled": "...", "slots_gaps": "..."},
  "sources": [{"source_id","path","kind","bytes","sha256","read_method","abstract_only","chars","sentences","meta"}],
  "metrics": {"...": "同 coverage.json"},
  "uncertainty": ["..."], "changes": [{"target","action","before","after","reason"}],
  "degradations": [{"stage","type","detail"}], "errors": [{"stage","type","detail"}],
  "runtime": {"script","version","python","seconds","network":"disabled","commands":[...]}
}
```

回填规则（`scripts/rules.py` 的 `FIELDS`）：

| 契约键命中词 | 回填内容 | 产物 |
|---|---|---|
| `criteria`、`标准` | 条款列表 | `screening/criteria.json` |
| `screen`、`筛`、`纳排`、`prisma` | 筛选行列表 | `screening/screening_log.jsonl` |
| `outline`、`提纲`、`section` | 节列表（sec_id/heading/purpose/slot_ids） | `outline/skeleton.json` |
| `slot`、`evidence`、`matrix`、`证据` | 已填槽位行（含 quote/locator/strength） | `slots/filled.jsonl` |
| `gap`、`空白`、`缺口` | 缺口行 | `slots/gaps.jsonl` |
| `coverage`、`metrics?`、`stats?`、`覆盖` | 覆盖统计对象 | `coverage.json` |
| `draft`、`review`、`综述`、`草稿` | 草稿全文（字符串） | `draft.md` |
| `source`、`reference`、`文献` | 来源清单 | `result.json#sources` |
| `uncertain`、`conflict`、`不确定`、`冲突` | 不确定性条目 | `result.json#uncertainty` |
| `change`、`版本` | 修补记录 | `changes.json` |
| `status`、`状态` | 运行状态 | — |
| `case_id` | 原样 case_id | — |

未被任何规则命中的契约键：保留键名、值写 `null`，并在 `degradations` 记录 `unmapped_field`；
**不删除键、不改键名**。键序按 contract 原序，信封字段在其后 `setdefault` 补齐。
