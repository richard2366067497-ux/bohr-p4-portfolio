# draft.json schema 与字段字典（v1.0.0）

> 本文件所有 JSON 片段均为**示例**（自造夹具），不是任何正式案例的答案。
> 工作稿路径：`/app/work/draft.json`（也接受 `/app/work/plan.json`，或 `--draft <path>`）。

## 1. 顶层结构

```json
{
  "schema": "screening-draft/1",
  "protocol": {
    "criteria_version": "v2",
    "reviewers": ["A", "B"],
    "criteria": [{"id": "C1", "kind": "include", "text": "仅在材料没有给出标准时使用"}],
    "query_strings": [
      {"id": "Q1", "database": "PubMed",
       "query": "(telemonitoring[tiab]) AND heart failure[tiab]",
       "fields": "tiab", "limits": "2010-2025; English, Chinese",
       "searched_on": "2025-06-01", "criterion_ids": ["I1", "I2", "E3"]}
    ]
  },
  "dedup_decisions": [
    {"group_id": "D01", "decision": "merge", "representative": "R003",
     "evidence": "同一 DOI 10.1000/xyz；副标题差异仅为预印本标注"}
  ],
  "decisions": [
    {"record_id": "R004", "phase": "title_abstract", "reviewer": "A", "label": "exclude",
     "reason_code": "EX-DES", "criterion_id": "E2",
     "evidence_quote": "This narrative review summarises", "locator": "R004@abstract",
     "confidence": 0.86, "note": "", "criteria_version": "v2", "rejudged_from": ""}
  ],
  "conflict_resolutions": [
    {"record_id": "R007", "type": "direction_conflict", "verdict": "include",
     "reason_code": "IN-DES", "basis_criterion_id": "I1",
     "basis_quote": "randomised controlled trial", "basis_locator": "R007@abstract",
     "rationale": "摘要明确为随机对照试验，符合 I1", "needs_human": false}
  ],
  "gaps": [
    {"item": "R020 full text", "reason": "abstract 为空，需全文", "kind": "missing_abstract"}
  ],
  "status_note": "一句话说明本轮做到哪、缺什么"
}
```

## 2. 字段字典

### protocol

| 字段 | 必填 | 说明 |
|---|---|---|
| `criteria_version` | 是 | 必须取自 `show` 列出的版本（`v1`/`v2`…）；材料没有给标准时才用 `protocol.criteria` 自定义 |
| `reviewers` | 建议 | 参与独立判断的标注者名；与 `decisions[].reviewer` 取值一致 |
| `criteria` | 否 | 材料缺标准时的兜底标准表，`id` 自定（如 `C1`）；一旦材料有标准，脚本会标 `criteria_shadowed` 警告 |
| `query_strings` | 建议 | 检索式：库、字段、限定、检索日期、对应 criterion_id；写清与纳入标准的对应关系 |

### dedup_decisions

| 字段 | 取值 | 说明 |
|---|---|---|
| `group_id` | `D01`… | 来自 `show` 的候选组编号 |
| `decision` | `merge` / `keep_separate` | 合并必须给 `representative`；分开要能说明为什么不是同一研究 |
| `representative` | `R###` | 必须在组内；合并后其余记录计入 `duplicates_removed` |
| `evidence` | 文本 | 合并依据（DOI 相同 / 预印本–正式版 / 标题仅差标点）；不得只写"重复" |

### decisions（核心）

| 字段 | 必填 | 说明 |
|---|---|---|
| `record_id` | 是 | `R###`，也接受 native id / DOI / 完整标题（脚本会解析并回写 `R###`） |
| `phase` | 是 | `title_abstract`（默认）/ `fulltext`（仅在材料确实提供全文或全文标注时） |
| `reviewer` | 是 | `A` / `B` / `arbiter` / 真实标注者名 |
| `label` | 是 | `include` / `exclude` / `pending` |
| `reason_code` | 是 | 必须来自 `reason_codes.json`，且与 label 同族（IN-↔include，EX-↔exclude，P-↔pending） |
| `criterion_id` | 建议 | 当前版本的 `I#`/`E#`；引用不存在或旧版本的条目会被 check 拦下 |
| `evidence_quote` | 是（include/exclude） | 题录字段中的逐字片段；空白会被归一化后比对 |
| `locator` | 否 | `R###@title` / `R###@abstract`；脚本会改写成 `R###@field[start:end]` |
| `confidence` | 否 | 0–1，仅供人工排序复核，不参与任何自动裁决 |
| `note` | 否 | 边界说明（如"仅摘要可判"） |
| `criteria_version` | 否 | 缺省取 `protocol.criteria_version`；跨版本判定必须显式写 |
| `rejudged_from` | 否 | 标准升级后重判时写旧版本号，例如 `v1` |

### conflict_resolutions

| 字段 | 必填 | 说明 |
|---|---|---|
| `record_id` | 是 | 分歧所在记录（代表记录即可） |
| `type` | 建议 | `direction_conflict` / `reason_conflict` / `version_conflict` / `boundary_conflict`；脚本会按证据重算并在卷宗中给出 |
| `verdict` | 是 | `include` / `exclude` / `pending`；`pending` 表示裁不了，必须写清缺什么 |
| `reason_code` | 建议 | 裁决后的主理由码 |
| `basis_criterion_id` | 是（非 pending） | 裁决依据的标准条目 |
| `basis_quote` | 建议 | 支持裁决的逐字片段 |
| `rationale` | 是 | 为什么这一方成立；禁止"多数票""取平均" |
| `needs_human` | 否 | `true` 时该分歧保持 open，进 `pending_human` |

### gaps

| 字段 | 说明 |
|---|---|
| `item` | 缺什么（记录号 / 字段 / 文件） |
| `reason` | 为什么无法补齐 |
| `kind` | `missing_abstract` / `missing_fulltext` / `missing_criteria` / `unreadable_file` / `other` |

## 3. 校验规则（`check` 会逐条打印）

| 检查 | 失败后果 |
|---|---|
| `C0` 工作稿存在且非空 | 直接判"无工作稿"，build 走降级 |
| `C2` 版本在材料版本表内 | 判 fail；`criterion_id` 也随之失效 |
| `C3` label ∈ {include, exclude, pending} | fail，该卡不计入 |
| `C4` reason_code 存在且与 label 同族 | fail；`C4b` 缺理由码为 warn |
| `C5` criterion_id 存在于当前版本 | 材料无标准时降为 warn |
| `C6` quote 逐字命中 | fail，并计入 `quote_hit_rate` |
| `C7` 覆盖率 = 1.0 | fail，列出未覆盖记录 |
| `C8` 同一 (记录, 阶段, 评审) 不重复 | fail，重复行被丢弃并登记 |
| `C9` 每个重复候选组有裁决 | warn |
| `C10` 每条分歧有非 pending 裁决 | warn；`C10b` 裁决无依据为 warn |
| `C12` `identified - dup = included + excluded + pending` | fail |
| `C13` 异常记录（缺摘要/乱码/缺 DOI）都有卡 | warn |

## 4. 反例（都会被 check 拦下）

```json
{"record_id": "R004", "label": "exclude", "reason_code": "not relevant"}          // 自由文本理由码
{"record_id": "R004", "label": "include", "reason_code": "EX-DES"}                // 理由码与标签不同族
{"record_id": "R004", "label": "exclude", "criterion_id": "E9"}                    // 标准表里没有 E9
{"record_id": "R004", "label": "exclude", "evidence_quote": "本文不相关"}          // 非逐字，且中文改写
{"record_id": "R004", "reviewer": "A", "label": "exclude"}                         // 缺 reason_code（warn）
{"record_id": "R004", "reviewer": "A", "label": "exclude", "reason_code": "EX-DES"} // 缺 quote（status→partial）
```

## 5. 写作纪律

1. **一条记录一位评审一行**；同一评审对同一记录写两行是错误，不是"补充说明"。
2. **不要替材料里的 A/B 再写一遍**：材料已给标签的记录会自动转成卡；你只需补未标注记录，并给分歧写 `conflict_resolutions`。
3. **判不了就 pending**：`P-ABS`（摘要不足）、`P-LANG`（语种待定）、`P-CONFLICT`（分歧未决）、`P-VERSION`（版本变更）。凭题名猜 include/exclude 会直接拉低正确性分。
4. **数字不上调**：`counts` 由脚本从卡片重算，写死的数字不会生效；要让筛选数变，只能改卡片。
