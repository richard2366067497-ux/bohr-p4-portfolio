# 工作稿 `draft.json` 字段字典（v1.0.0）

工作稿是 **Agent 唯一必写文件**，路径 `/app/work/draft.json`（也可 `gate_draft.json`）。
脚本只读不写；`build` 会把它与兜底骨架合并成 `/app/work/draft.effective.json` 再渲染。
所有 `quote` 必须**逐字**来自 `show` 打印出的原文（含标点）；改写过的句子会被判 `quote_not_found` 并失去证据资格。

## 0. 顶层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | str | 否 | 与 case.json 一致；缺省由脚本回填 |
| `proposal_title` | str | 否 | 简报标题；缺省用 case.json 的 `title` |
| `question` | obj | **是** | §1 |
| `search_protocol` | obj | 是 | §2，缺则 `W_SEARCH_*` |
| `gates` | list | **是** | §3，必须 G1–G5 各一 |
| `matrix` | list | **是** | §4，长表行 |
| `novelty` | list | **是** | §5 |
| `assumptions` | list | **是** | §6，≥3 条、≥3 类 |
| `claims` | list | 是 | §7，gate 的 `evidence_ids` 指向这里 |
| `conflicts` | list | 二选一 | §8；无冲突时用 `no_contrary_found` 说明范围 |
| `research_gap` | obj | **是** | §9 |
| `decision` | obj | **是** | §10 |
| `change_log` | list | 否 | §11 |

## 1. `question`（G1 的输入）

```jsonc
{
  "problem_statement": "在<对象>上，<变量>相对<基线>能否达到<预期>？（含条件与量纲）",
  "object": "研究对象（材料/体系/样本）",
  "variables": ["自变量", "因变量（带量纲）", "控制变量"],
  "baseline": "比较基线（对照组或用文献值并给编号）",
  "expected": "预期结论（可测量的阈值）",
  "falsification": ["F1：若<观测>出现（含批次/条件），则设想被否定"],
  "vague_replaced": [{"vague": "显著提升", "measurable": "在<条件下><指标>≥<阈值>"}],
  "untestable": ["现有条件下无法判定的部分，明确标出而不是假装能测"]
}
```

判定要点：`object/variables/baseline/expected` 四项缺一即 `E_G1_SPLIT`；`falsification` 空即 `E_G1_FALSIFY`；
`problem_statement` 含模糊措辞（见 `gate-rules.md` 词表）而 `vague_replaced` 空 → `W_G1_VAGUE`。

## 2. `search_protocol`（检索覆盖的可复核记录）

```jsonc
{
  "queries": ["检索式/关键词组合"],
  "windows": "2020-01 至 2024-12（说明是材料范围还是在线检索）",
  "inclusion": ["纳入标准"], "exclusion": ["排除标准"],
  "screened": 10,
  "excluded": [{"record_id": "R4", "reason": "编号在对象表中无对应来源"}]
}
```
`screened` 是**记录级**条数，应与索引的 `counts.records` 相容；不一致要在简报里解释，不要抹平。

## 3. `gates`（五门记分卡，顺序 G1→G5）

```jsonc
{
  "gate_id": "G3", "name": "can_do",
  "question": "做得出来吗：数据/算力/实验/时间/人员/伦理前提是否成立",
  "verdict": "go | conditional | no_go",
  "conditions": ["成立所需条件（conditional/no_go 必填）"],
  "evidence_ids": ["C3"],
  "residual_risks": ["即使通过仍存在的风险"],
  "pivot_if_no_go": "不通过时改做什么（conditional/no_go 必填）",
  "rationale": "一句判定理由，需与证据一致"
}
```
`evidence_ids` 指向 `claims[].claim_id`，且该 claim 至少有一条 `verified` 证据，否则 `E_GATE_BADEVID`。
跨门一致性硬规则：任一 gate 为 `no_go` 时 `decision.overall` 不得为 `go`；存在 `conditional` 时总判定须为 `conditional` 或更低。

## 4. `matrix`（对齐矩阵长表，一 claim × 一 nearest work 一行）

| 字段 | 取值 | 说明 |
|---|---|---|
| `claim_id` | C1… | 与 `claims`/`novelty` 对齐 |
| `source_id` | S1…（或 M#） | 必须在对象表内，否则 `E_G2_FAKE`（疑似编造文献） |
| `task` `method` `data` `evaluation` | str | 四维比较字段；材料未给就写“材料未给”，不要补猜 |
| `overlap` | `method\|data\|scenario\|conclusion\|none` | 与设想重叠的维度 |
| `comparison_status` | `comparable\|not_comparable` | 是否可直接比较 |
| `cannot_compare_reason` | str | `not_comparable` 必填（`E_G2_REASON`） |
| `boundary_note` | str | **边界差别**：设想与该工作到底哪里不同 |
| `locator` | `M3/p2` 或 `S1/abstract` | 供独立复核 |

## 5. `novelty`（创新类型学与覆盖判定）

```jsonc
{"claim_id": "C1", "type": "method | data | scenario_transfer | conclusion_correction",
 "verdict": "covered | novel | undetermined",
 "covered_by": ["S1"],            // verdict=covered 必填
 "boundary": "与最近工作的具体差别",  // verdict=novel 必填
 "rationale": "判定依据",
 "evidence": [{"source_id": "S1", "locator": "M3/p2", "quote": "逐字原文"}]}
```
- `covered`：已有工作做过同一件事（方法/数据/场景/结论四类之一）。
- `scenario_transfer` 只算**迁移**，不算理论创新；`conclusion_correction` 必须指出被修正的结论。
- `undetermined`：材料不足以判定。**不允许**用“检索不到”“无人研究”支撑 `novel`（`E_G4_FALSE_NOVEL`）。

## 6. `assumptions`（可行性前提登记，G3 的输入）

```jsonc
{"id": "A2", "statement": "实验室具备 1550 nm 光源与校准探测器",
 "category": "data | compute | experiment | time | people | ethics",
 "state": "source | assumed | unsupported",
 "source_locator": "M3/p4",          // state=source 需可核验证据，否则 E_G3_UNSOURCED
 "kill_criteria": "出现什么信号就放弃（可判定）",
 "validation_experiment": "用什么最小实验把它变成 source",
 "evidence": [{"source_id": "S1", "locator": "M3/p4", "quote": "逐字原文"}]}
```
`state` 三分是本题的核心口径：`source` 有材料出处、`assumed` 合理但未验证、`unsupported` 无支撑（它存在时 G3 不能判 `go`）。

## 7. `claims`（证据回链的锚点）

```jsonc
{"claim_id": "C4", "text": "氯化物单独作用可能不带来暗电流收益",
 "type": "novelty | feasibility | gap",
 "evidence": [{"source_id": "S2", "locator": "M4/p3", "quote": "逐字原文", "polarity": "support | contradict"}]}
```
`polarity=contradict` 的证据必须出现在 `conflicts` 里（`E_CONFLICT_UNLOGGED`）。

## 8. `conflicts` / `no_contrary_found`

```jsonc
{"topic": "冲突主题",
 "support": [{"source_id": "S1", "locator": "M3/p2", "quote": "…"}],
 "contradict": [{"source_id": "S2", "locator": "M4/p3", "quote": "…"}],
 "resolution": "为什么两者可以不互否 / 如何取舍",
 "impact_on_decision": "对哪一门、把结论从什么改成什么"}
```
确实没有相反证据时，写 `"no_contrary_found": "在<范围>内未检索到相反结论；这不等于不存在"`。
两者都空 → `E_CONFLICT_SILENT`（只报支持证据视为失败）。

## 9. `research_gap`

```jsonc
{"statement": "在本材料范围内未见……（限范围表述）",
 "scope": "本材料与本次纳排范围",
 "basis": [{"source_id": "S1", "locator": "M3/p4", "quote": "…"}],
 "global_claim": false}
```
`global_claim` 必须为 `false`（`E_GAP_GLOBAL`）：材料级空白不能升级为领域级断言。

## 10. `decision`

```jsonc
{"overall": "go | conditional | no_go",
 "summary": "一句话：创新落在哪、缺什么、能否立项",
 "conditions": ["把 conditional 变 go 的条件"],
 "next_validation": [{"step": "动作", "evidence_needed": "要拿到的证据", "gate": "G3"}]}
```

## 11. `change_log`

```jsonc
[{"action": "降级", "target": "G3", "reason": "1550 nm 光源前提 unsupported",
  "before": "go", "after": "conditional"}]
```

## 12. 最小可用工作稿（示例数据，**不是任何案例的答案**）

```jsonc
{"question": {"problem_statement": "在<体系>上，<处理>相对<基线>能否把<指标>降到<阈值>？",
              "object": "<体系>", "variables": ["<处理>", "<指标>"],
              "baseline": "<对照>", "expected": "<阈值>", "falsification": ["F1：若<观测>则否定"]},
 "search_protocol": {"queries": ["<关键词>"], "windows": "<时间窗>", "screened": 10},
 "gates": [{"gate_id": "G1", "verdict": "conditional", "conditions": ["<条件>"],
            "evidence_ids": ["C1"], "pivot_if_no_go": "<改法>"}],
 "matrix": [{"claim_id": "C1", "source_id": "S1", "task": "…", "method": "…", "data": "…",
             "evaluation": "…", "overlap": "method", "comparison_status": "comparable",
             "boundary_note": "…", "locator": "M1/p2"}],
 "novelty": [{"claim_id": "C1", "type": "method", "verdict": "covered", "covered_by": ["S1"],
              "evidence": [{"source_id": "S1", "locator": "M1/p2", "quote": "<逐字>"}]}],
 "assumptions": [{"id": "A1", "statement": "…", "category": "data", "state": "assumed",
                  "kill_criteria": "…", "validation_experiment": "…"}],
 "claims": [{"claim_id": "C1", "text": "…", "evidence": [{"source_id": "S1", "locator": "M1/p2", "quote": "<逐字>"}]}],
 "no_contrary_found": "在<范围>内未检索到相反结论",
 "research_gap": {"statement": "…", "scope": "本材料范围", "basis": [], "global_claim": false},
 "decision": {"overall": "conditional", "summary": "…", "conditions": ["…"]}}
```

## 13. 只写 `draft.md` 的情况

若只写了叙事版 `/app/work/draft.md`，脚本按 `##` 标题里的「问题/比较/可行/创新/风险」把段落归到 G1–G5，
其余结构化字段一律用兜底补齐，`status` 必为 `partial`。这只是应急路径，不能替代 `draft.json`。
