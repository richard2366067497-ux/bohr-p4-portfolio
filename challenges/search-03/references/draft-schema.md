# 工作稿 schema 与字段字典

工作稿是 Agent 的判断载体：`/app/work/draft.json`（或 `draft-01.json`、`draft-02.json`…，按文件名字典序
合并，同 `record_id` 后者覆盖前者）。`draft.template.json` 由 `init` 生成，含全部候选骨架，直接复制改名即可。

## 1. 最小可用样例

```json
{
  "case_id": "case-xxx",
  "research_question": "用自己的话写清对象/方法/时间窗",
  "criteria_used": [
    {"rule_id": "R2", "text": "研究对象须为……", "source_locator": "case.json#/screening_criteria"}
  ],
  "records": [
    {"record_id": "10.1000/abc",
     "label": "keep", "relevance": "direct", "score": 0.86,
     "criteria_hit": ["R1", "R2", "R3", "R4", "R6"],
     "criteria_violated": [],
     "evidence_quote": "摘要里逐字存在的一句话，含数值或结论",
     "evidence_locator": "materials/candidates.json#/candidates/3/abstract",
     "confidence": "high",
     "rationale": "一句话：命中哪条条件、为什么不是间接相关",
     "duplicate_of": null,
     "flags": []}
  ],
  "conflicts": [],
  "uncertainties": []
}
```

## 2. 字段字典

| 字段 | 类型 | 必填 | 取值范围 | 说明 |
|---|---|---|---|---|
| `case_id` | string | 建议 | 与输入一致 | 不一致不报错，但会在 `changes` 留痕 |
| `research_question` | string | 建议 | ≤400 字 | 复述问题，脚本用它补 `criteria.agent_research_question` |
| `criteria_used[]` | array | 建议 | `{rule_id,text,source_locator}` | 你实际用的口径；`rule_id` 只认 R1–R12 |
| `records[]` | array | **是** | 见下 | 必须覆盖候选集全部 `record_id` |
| `records[].record_id` | string | **是** | 与 `init` 输出一致 | 不存在于候选集的 id 会被丢弃并报错 |
| `records[].label` | string | **是** | `keep` / `maybe` / `exclude` | 其它值 → `bad_enum` |
| `records[].relevance` | string | **是** | `direct` / `indirect` / `none` | 其它值 → `bad_enum` |
| `records[].score` | number | 建议 | 0–1 | 越界被裁剪并在 `check` 报 `score_out_of_range` |
| `records[].criteria_hit` | string[] | 建议 | R1–R12 | 命中/支撑该判定的规则 |
| `records[].criteria_violated` | string[] | 可选 | R1–R12 | 命中的排除/不满足项 |
| `records[].evidence_quote` | string | **强烈建议** | 20–200 字 | 必须是该记录题名/摘要/关键词中**逐字存在**的片段 |
| `records[].evidence_locator` | string | 建议 | `file#/pointer` | 与 `init` 给的 locator 一致最稳 |
| `records[].confidence` | string | 建议 | `high` / `medium` / `low` | 缺省取规则通道的置信度 |
| `records[].rationale` | string | 建议 | ≤600 字 | 写清命中条件与边界，便于复核 |
| `records[].duplicate_of` | string\|null | 可选 | 另一 `record_id` | 仅用于重复/版本变体 |
| `records[].flags` | string[] | 可选 | 自由文本 | 常用：`abstract_missing`、`review`、`retraction`、`preprint`、`cross_language` |
| `conflicts[]` | array | 可选 | 自由结构 | 你发现的冲突，合并进 `conflicts.json` |
| `uncertainties[]` | array | 可选 | `{record_id,issue,action}` | 进 `result.uncertainties` |

## 3. 分批与续写

上下文紧张时按页处理，多文件写入：

```bash
python3 scripts/main.py show --page 2 --page-size 15
# 写 draft-02.json，只放本页 15 条；build 时按 draft.json -> draft-01.json -> draft-02.json 合并
```

`show --picks` 只列尚未写入工作稿的记录，适合补漏。

## 4. `check` 的判定规则（错误会拦住可核验性）

| 检查 | 级别 | 触发 |
|---|---|---|
| `unknown_record_id` | error | draft 里的 id 不在候选集 |
| `missing_judgement` | error | 候选没被判定（build 会兜底） |
| `bad_enum` | error | label/relevance/confidence 取值非法 |
| `score_out_of_range` / `score_not_number` | error | score 非法 |
| `bad_rule_id` | error | criteria_hit 出现 R1–R12 之外的 ID |
| `quote_not_found` | error | `evidence_quote` 不能在该记录原文中逐字定位 |
| `duplicate_target_unknown` | warn | `duplicate_of` 指向不存在的 id |
| `quote_missing` | warn | 没写引证 |
| `no_rule_cited` | warn | 既无 `criteria_hit` 也无 `criteria_violated` |
| `keep_with_low_score` / `keep_but_none` | warn | 标签与分数/相关性自相矛盾 |
| `fewer_than_k` | warn | `keep+maybe < k`，排名区可能不足 |

`check` 退出码恒 0，但会打印 `PASS` 或 `FIX n error(s)`；`build` 不会因检查失败而中断，
它会把不合格的判定降级（见下）并记录 `degradations`。

## 5. `build` 的补全与降级

draft 缺 `label/relevance/score/confidence` → 规则通道补齐；`evidence_quote` 缺失 → 用规则通道挑的原句；
写了但逐字不命中 → `flags += quote_unverified`、`label` 降 `maybe`、`confidence=low`、`score≤0.5`、进
`pending_human`；双通道差 ≥1 层且引证不可核验 → 降 `maybe`（R12）；完全没有 draft → 全走规则通道，
`source=rule_fallback`、`status=partial`、记 `no_agent_draft_rule_fallback`。

## 6. `result.json` 顶层字段

信封字段（始终存在）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `case_id` | string | 原样保留输入 case_id |
| `status` | string | `answered` / `partial` / `insufficient_evidence` / `input_error`（**永远是字符串**） |
| `task` / `skill_version` | string | 固定标识与版本 |
| `errors[]` | array | 解析/判定/输入的异常，含 `stage`、`issue`、`detail` |
| `degradations[]` | array | 降级项（未写工作稿、引证不可核验、语言不桥接、契约字段空填……） |
| `assumptions[]` | array | 口径假设（facet 未给出、k 不足、跨语言等） |
| `warnings[]` | array | 非阻断提醒 |
| `sources[]` | array | 扫描到的材料与解析方式（`path`/`kind`/`records`） |
| `queries[]` | array | 输入中的检索式（若提供） |
| `uncertainties[]` / `pending_human[]` | array | 需人工处理的点，含 `action` |
| `changes[]` | array | 本次运行做了什么（构建记录） |
| `runtime` | object | 版本、耗时、输入路径、是否 finished |
| `result` | object | 完整结构化结果：`screening`、`ranking`、`coverage`、`conflicts`、`criteria`、`method_notes`、`report_md`、`artifacts` |

`output_contract` 声明的每个键都会**原样**出现在顶层（键名不改、不遗漏）；无对应内容时按声明类型
填空（`[]` / `{}` / `""` / `null`），并在 `degradations` 记 `contract_field_filled_empty`。
`status` 键始终回填枚举字符串，统计信息只进 `coverage`，绝不覆盖 `status`。
