```
{
  "case_id": "case-000",
  "status": "success",
  "deliverable": "evidence_driven_draft.md",
  "preserved_facts": [{"value": "42", "unit": "%", "span": "42%"}],
  "evidence_map": [{"claim_id": "C001", "source_id": "D01", "locator": "materials/refs.txt [B0.S2] chars:0-80", "strength": "中"}],
  "change_log": [{"action": "assembled the draft from located material", "target": "evidence_driven_draft.md"}],
  "output_contract": {
    "case_id": "case-000",
    "deliverable": "evidence_driven_draft.md",
    "preserved_facts": [{"value": "42", "unit": "%", "span": "42%"}],
    "evidence_map": [{"claim_id": "C001", "source_id": "D01", "locator": "materials/refs.txt [B0.S2] chars:0-80", "strength": "中"}],
    "change_log": [{"action": "assembled the draft", "target": "evidence_driven_draft.md"}]
  }
}
```

# 证据产物结构 / Evidence artifact schema

本文件定义 `claims.json`、`evidence_table.json`、`result.json` 的字段约定。字段名稳定，便于他人独立回查与重跑。

## claims.json

| 字段 | 含义 |
|---|---|
| `case_id` | 输入案例标识（透传） |
| `language` | 成稿语言 `zh` / `en` |
| `mode` | `revise`（有草稿）或 `compose`（按题目组稿） |
| `count` | 论断条数 |
| `claims[]` | 论断数组 |
| `claims[].claim_id` | 论断编号，`C001` 起 |
| `claims[].text` | 论断原文 |
| `claims[].render` | 成稿中使用的版本（已做过度推断改写） |
| `claims[].type` | `causal` / `descriptive` |
| `claims[].location` | `draft:` 或 `compose:` 加材料定位 |

## evidence_table.json

| 字段 | 含义 |
|---|---|
| `schema` | 字段顺序说明 |
| `rows[].claim_id` | 对应论断 |
| `rows[].source_id` | 来源文件 ID（`D01`…），空串表示未匹配 |
| `rows[].locator` | `路径 [Bn.Sm] chars:a-b` |
| `rows[].quote` | 来源原文片段（逐字，取自材料） |
| `rows[].strength` | `高` / `中` / `低` / `不足` |
| `rows[].support_scope` | 该来源的研究设计类别 |
| `rows[].conflicts` | 与论断方向相左的同组来源定位 |
| `rows[].rationale` | 强度计算的文字依据 |
| `rows[].verified` | 引文是否在来源内逐字命中 |

## result.json（顶层）

`case_id`、`status`、`skill`、`skill_version`、`language`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`output_contract`、`outputs`、`metrics`、`sources`、`uncertainties`、`change_records`、`limits`、`human_review`、`degradations`、`errors`、`runtime`。

- `status` ∈ `success` / `partial` / `failed`。
- `output_contract`：逐键回填输入契约；契约给值的键保留其语义，给空值或仅给描述的键回填为真实值或真实文件。
- 五要素 `preserved_facts`、`evidence_map`、`change_log`、`uncertainties`、`limits` 恒为非空，保证即使降级也可复核。
