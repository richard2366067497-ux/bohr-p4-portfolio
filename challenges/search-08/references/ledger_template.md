# 流程台账 / 仲裁卷宗 / 闭合审计：模板与定义（v1.0.0）

> 下表的数字来自自造夹具，仅演示形状；正式运行时由脚本从本轮输入与判定卡重算。

## 1. PRISMA 式流程台账 `flow_ledger.md`

```
# Flow ledger - case <case_id>

- criteria version: `v2` (source=materials, fingerprint=<sha1:12>)
- pipeline v1.0.0 | draft: /app/work/draft.json
- research question: <case 的研究问题>

## 1. Flow (PRISMA style)

| # | stage | n | basis (file / field) | independently checkable by |
|---|---|---|---|---|
| 1 | identified | 8 | materials/records.jsonl (8 rows) | index.json records[] |
| 2 | duplicates_removed | 1 | D01(R001,R002) | index.json clusters[] + draft dedup_decisions[] |
| 3 | screened | 7 | identified - duplicates_removed | identity E1 |
| 4 | excluded | 4 | decision_cards.jsonl label=exclude | per-card locator |
| 5 | included | 2 | decision_cards.jsonl label=include | per-card locator |
| 6 | pending | 1 | P-ABS / P-CONFLICT / P-NODRAFT | per-card reason_code |
| 7 | conflicts_total | 2 | arbitration_docket.md | docket sections |
| 8 | arbitrated | 2 | docket verdict != pending | docket basis |
| 9 | conflicts_open | 0 | docket pending entries | pending_human |
```

每一级都必须写出**依据的文件/字段**与**复核方式**；只给数字、不给依据的台账不构成证据链。

## 2. 恒等式定义

| id | 等式 | 含义 | 不成立时说明什么 |
|---|---|---|---|
| E1 | `identified - duplicates_removed = screened` | 去重前后条目数守恒 | 合并组成员/代表记录不一致，或去重未登记 |
| E2 | `screened = included + excluded + pending` | 每条进入筛选的记录都有归宿 | 存在未判定或重复计数 |
| E3 | `conflicts_total = arbitrated + conflicts_open` | 分歧要么裁决要么挂起 | 分歧被静默丢弃 |
| E4 | `pending = conflicts_open + awaiting_info` | pending 的来源可拆解 | pending 被当成垃圾筐 |
| E5 | `studies_with_cards = screened` | 每个 study 至少一张判定卡 | 覆盖率不足（降级运行会 FAIL） |

`diff != 0` 时**不许改数**，要在台账里写明差值来源（例如"2 条记录无判定，已计入 pending，原因见 pending_human"）。

## 3. 理由码分布表（台账 §3）

```
| reason_code | n | criterion | gloss |
|---|---|---|---|
| IN-DES | 2 | I4 | 研究设计符合纳入的设计类型 |
| EX-POP | 1 | E1 | 研究对象或人群不符 |
| P-ABS  | 1 | -  | 摘要缺失或信息不足，需取全文后再判 |
```

用途：复核者一眼能看出"排除是否集中在某一个理由上"（例如 90% 都用 EX-DES 通常意味着标准没落地或检索式太宽）。

## 4. 仲裁卷宗 `arbitration_docket.md`

每条分歧一页，字段固定：

```
## Docket 1 - S06 / R007 - `direction_conflict`

| reviewer | label | reason_code | criterion | evidence (verbatim) | locator |
|---|---|---|---|---|---|
| A | include | IN-DES | I4 | <逐字片段，来自该记录摘要> | R007@abstract[0:62] |
| B | exclude | EX-DES | E2 | - | - |

- divergence: 一方纳入、一方排除：实质性分歧，必须给出仲裁结论与判据原文
- verdict: **include**
- basis: criterion `I4` + <支持裁决的逐字片段> (R007@abstract)
- rationale: <为什么这一方符合 criterion 原文；引用摘要中的设计与结局>
```

四种分歧类型与处置：

| 类型 | 触发条件 | 处置要求 |
|---|---|---|
| `direction_conflict` | 一方 include、一方 exclude | 必须裁决；裁决必须引用 criterion + 逐字证据 |
| `reason_conflict` | 标签相同、理由码不同 | 定一个主理由码，说明另一码为何不采纳（影响排除分布） |
| `version_conflict` | 两行绑定不同 `criteria_version` | 先定现行版本，再对旧判定写 `rejudged_from` |
| `boundary_conflict` | 至少一方 pending，或证据不足 | 补齐信息（全文/语种/更明确片段）或保持 pending 并写未决原因 |

## 5. 闭合审计 `audit_closure.json`

```json
{
  "case_id": "<case>",
  "criteria": {"version": "v2", "source": "materials", "fingerprint": "5e33538d3b2d",
               "available": ["v1", "v2"]},
  "equations": [{"id": "E1", "equation": "identified - duplicates_removed = screened",
                 "left": 7, "right": 7, "diff": 0, "status": "PASS"}],
  "counts": {"identified": 8, "duplicates_removed": 1, "screened": 7,
             "included": 2, "excluded": 4, "pending": 1,
             "conflicts_total": 2, "arbitrated": 2, "conflicts_open": 0,
             "coverage": 1.0, "quote_hit_rate": 1.0},
  "reason_codes": [{"reason_code": "IN-DES", "count": 2, "criterion_id": "I4", "gloss": "..."}],
  "anomalies": [{"record_id": "R006", "flag": "mojibake"}],
  "issues": [{"kind": "dedup_undecided", "detail": "D03 (R011,R012)"}],
  "coverage": {"screened": 7, "with_cards": 7, "quote_checked": 3, "quote_hit": 3},
  "cards_by_source": {"agent": 3, "input_labels": 8, "fallback": 0}
}
```

`cards_by_source` 直接暴露降级程度：`fallback > 0` 说明有记录没有被真正判定过。

## 6. 可复现性

同一 `/input` + 同一 `/app/work/draft.json`：

- `decision_cards.jsonl`、`flow_ledger.md`、`audit_closure.json` 逐字节一致（无时间戳）；
- `result.json` 的 `counts`、`status` 一致，仅 `runtime` 段每次不同。

复现命令（示例）：

```bash
python3 scripts/main.py build --input /input --output /tmp/o1 --work /app/work
python3 scripts/main.py build --input /input --output /tmp/o2 --work /app/work
diff <(sort /tmp/o1/decision_cards.jsonl) <(sort /tmp/o2/decision_cards.jsonl) && echo "reproducible"
```
