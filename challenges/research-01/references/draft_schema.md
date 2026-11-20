# 工作稿 schema、字段字典与错误码（research-01）

本文件是 `scripts/main.py check` 的规范来源。改判据先改这里，再改 `scripts/check.py`。

## 1. 工作稿位置与整体结构

- 路径：`<work>/draft.json`（官方运行时为 `/app/work/draft.json`）；
- 编码：UTF-8；JSON 对象；允许只写部分章节；
- 键名兼容：`sub_questions`/`questions`/`decomposition`/`question_tree`、
  `search_log`/`search_steps`/`tool_log`/`tool_calls`、
  `findings`/`finding_cards`/`cards`、
  `synthesis`/`synthesis_claims`/`memo`/`conclusions`、
  `open_questions`/`gaps`/`research_gaps` 均可识别（`check.py: ALIASES`）。

```json
{"case_id": "…", "brief": {…}, "search_log": [ … ], "findings": [ … ],
 "synthesis": [ … ], "open_questions": [ … ]}
```

## 2. `brief.sub_questions[]` 字段字典

| 字段 | 必填 | 取值/说明 | check |
|---|---|---|---|
| `sq_id` | 是 | `SQ1…`，全文唯一 | 缺失则自动编号 |
| `text` | 是 | 可独立检索的一句话，含对象与限定 | `C201` |
| `object` | 是 | 研究对象（病种/系统/机制） | `C201` |
| `mechanism` | 是 | 机制、通路或因果假设 | `C201` |
| `method` | 是 | 允许的方法学类型（RCT/队列/诊断准确性…） | `C201` |
| `time_scope` | 是 | 时间或文献年限范围 | `C201` |
| `comparison` | 是 | 比较关系；无则写「无」 | `C201` |
| `evidence_requirement` | 是 | **什么样的一段材料算答上**（判断覆盖的唯一依据） | `C201` |
| `depends_on` | 否 | 前置 `sq_id` 数组 | 渲染排序 |
| `layer` | 是 | `what`（是什么）/`how_far`（做到哪）/`why`（为什么）/`what_missing`（还缺什么） | `C203` |

## 3. `search_log[]`

| 字段 | 必填 | 说明 |
|---|---|---|
| `step_id` | 是 | `S1…`，唯一（`C215` 重复告警） |
| `action` | 是 | `search` / `read` / `extract` / `calc` |
| `target` | 是 | 材料 id（`src-3`）或相对路径 |
| `params` | 是 | 检索式或参数，够别人重放 |
| `result_summary` | 是 | 命中了什么（不是「已处理」） |
| `hits` | 是 | 实际命中的材料 id 数组 |
| `status` | 是 | `ok` / `failed` / `retried`；失败步保留 |
| `retry_count` | 否 | 重试次数 |

## 4. `findings[]`（发现卡）

| 字段 | 必填 | 取值 | check |
|---|---|---|---|
| `finding_id` | 是 | `F001…`，唯一 | `C215` |
| `statement` | 是 | 一句话结论，不得超出 `scope` | `C212` |
| `type` | 是 | `material_fact`（材料直述）/`inference`（跨材料推断）/`undetermined`（无法确定） | `C217` |
| `confidence` | 是 | `high`/`medium`/`low` | `C217` |
| `support` | 是 | 至少 1 条；`undetermined` 可空 | `C210` |
| `counter` | 否 | 反证数组，格式同 support | `C213` |
| `scope` | 是 | 适用对象/条件/时间边界 | `C212` |
| `sub_question_id` | 是 | 必须已在简报登记 | `C216` |
| `status` | 是 | `established`/`provisional`/`contested`/`undetermined` | `C217` |

`support[]` / `counter[]` 元素：

| 字段 | 必填 | 说明 |
|---|---|---|
| `source_id` | 是 | `show` 打印的材料 id；写错会按命中位置回改并记 `R211` |
| `locator` | 是 | `<rel>#B<块>.S<句> chars:<start>-<end>`；写错会回改（`R211`） |
| `quote` | 是 | **逐字**原文，不翻译、不合并两句、不改标点数字 |

## 5. `synthesis[]`

| 字段 | 必填 | 说明 | check |
|---|---|---|---|
| `paragraph` | 是 | 段落正文，引用写成 `[F003]` | `C220`（引用未登记卡）、`C222`（绝对措辞）、`C224`（无引用） |
| `finding_ids` | 建议 | 与正文 `[Fxxx]` 一致；不一致时取并集校验 | `C220` |
| `strength_note` | 是 | `established`/`provisional`/`contested`/`undetermined`，不得高于所引卡最高状态 | `C221` |

强度秩：`established(3) > provisional(2) > contested(1) > undetermined(0)`。绝对措辞黑名单：证明/证实/确证/确凿/毫无疑问/proves/proven/confirms/definitively。

## 6. `open_questions[]`

| 字段 | 必填 | 取值 |
|---|---|---|
| `oq_id` | 是 | `OQ1…` |
| `description` | 是 | 缺口是什么 |
| `type` | 是 | `retrieval_gap` / `unresolved_conflict` / `method_limitation` / `scope_limit`（`C240`） |
| `basis` | 是 | 依据：哪条检索、哪份材料的哪处缺失 |

## 7. 错误码表

| 码 | 级别 | 含义 | 处置 |
|---|---|---|---|
| `C201` | FIX | 子问题缺必填字段 | 补齐七字段 |
| `C202` | WARN | 子问题 < 4 条 | 按对象/机制/方法/时间/比较补拆 |
| `C203` | WARN | 四层不齐或 layer 取值非法 | 覆盖 four layers |
| `C210` | FIX | 卡片无 support | 从 `show` 抄逐字句 |
| `C211` | FIX | quote 非逐字命中 | 回原文重抄；卡片自动降为 provisional/low |
| `C212` | FIX | 缺 statement/scope/confidence/status | 补齐 |
| `C213` | FIX | 有 counter 却标 established | 改 provisional/contested 或进 05 |
| `C214` | FIX/WARN | 支持项缺 quote/source_id/locator | 补全 |
| `C215` | FIX/WARN | finding_id 或 step_id 重复 | 重编号 |
| `C216` | FIX | 指向未登记子问题 | 改 id 或补子问题 |
| `C217` | FIX | 枚举外取值 | 按第 4 节词表 |
| `C220` | FIX | 备忘录引用未登记卡 | 只引已登记编号 |
| `C221` | FIX | 段落强度高于所引卡 | 下调措辞 |
| `C222` | FIX | 绝对措辞越级 | 改「提示/关联/尚不能确定」 |
| `C224` | FIX | 段落未引用任何发现卡 | 句末加 `[Fxxx]` |
| `C223` | INFO | 卡片未被引用 | 合并或补段 |
| `C230` | WARN | 子问题无卡覆盖 | 补卡或在 05 写 retrieval_gap |
| `C231` | WARN | 子问题仅单一来源 | 补第二来源或降置信度 |
| `C240` | FIX/WARN | 未决问题类型非法/缺 basis | 按四型改写 |
| `C241` | WARN | 有未覆盖子问题但没有 retrieval_gap | 补一条 |
| `C250` | WARN | 检索日志为空/缺 action | 补步骤 |
| `C251` | WARN | 证据来源不在任何步骤 hits 里 | 补 read 记录 |
| `R211` | REPAIR | locator 与命中位置不符，已自动回改 | 记入 `changes[]`，不阻断 |

## 8. 最小工作稿（可直接改，示例数据）

```json
{
  "case_id": "demo-1",
  "brief": {
    "question": "问题复述",
    "scope": "纳入范围",
    "inclusion": ["判据"], "exclusion": ["判据"], "stop_rules": ["停止条件"],
    "sub_questions": [
      {"sq_id": "SQ1", "text": "子问题一", "object": "对象", "mechanism": "机制",
       "method": "方法", "time_scope": "2015-2024", "comparison": "无",
       "evidence_requirement": "给出数值的原文句", "depends_on": [], "layer": "what"}
    ]
  },
  "search_log": [
    {"step_id": "S1", "action": "read", "target": "src-1", "params": "read_method=pdftotext",
     "result_summary": "读到 3 段方法与结果", "hits": ["src-1"], "status": "ok", "retry_count": 0}
  ],
  "findings": [
    {"finding_id": "F001", "statement": "结论一句话", "type": "material_fact",
     "confidence": "medium",
     "support": [{"source_id": "src-1", "locator": "src.md#B2.S1 chars:40-96",
                  "quote": "从 show 输出逐字复制的一句话。"}],
     "counter": [], "scope": "适用条件", "sub_question_id": "SQ1", "status": "established"}
  ],
  "synthesis": [
    {"paragraph": "综合一句 [F001]。", "finding_ids": ["F001"], "strength_note": "provisional"}
  ],
  "open_questions": [
    {"oq_id": "OQ1", "description": "缺口", "type": "retrieval_gap", "basis": "依据"}
  ]
}
```

> 上面是**格式示例**，其中的 quote 必须替换为你在当前案例 `show` 输出里看到的真实句子，否则 `C211`。
