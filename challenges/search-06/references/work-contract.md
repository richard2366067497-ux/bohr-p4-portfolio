# 工作稿与产物契约（draft.json / locator / result.json）

本文件规定的都是**机器可校验**的东西：字段名、枚举值、locator 格式、信封字段、契约回填规则。判断类内容（相关性、取舍、抑制理由）由 Agent 写，格式由本文件约束。

---

## 1. 数据流

```
/input/case.json ─┐
/input/task.md  ──┼─→ init ──→ /app/work/index.json（记录、work、窗口、基线）
/input/materials ─┘                    │
                                       ├─→ show（人读：窗口/覆盖/before-after/locator）
                                       │
                    Agent 阅读 ──→ /app/work/draft.json（判断）
                                       │
                            check（机械校验）─→ build ─→ /app/output/*
```

`index.json` 是脚本的中间状态，**不要手改**；要改判断就改 `draft.json`。

---

## 2. `draft.json` 完整 schema

```json
{
  "subscription": {
    "query": "订阅的检索式或研究问题（原样，不改写）",
    "sources": ["S1", "S2"],
    "timezone": "UTC",
    "cadence": "weekly|monthly|manual",
    "notes": "订阅意图、纳入/排除口径的自由文本"
  },
  "window": {
    "start": "2024-03-01",
    "end": "2024-04-01",
    "timezone": "UTC",
    "basis": "import_state.watermark=2024-03-01 (S1) + case.json window_end"
  },
  "dedup_rules": {
    "keys": ["doi", "arxiv", "title_fp"],
    "normalization": "DOI 小写去前缀；arXiv 去 vN；标题 NFKC + 字母数字 sha1(12)"
  },
  "decisions": [
    {
      "work_key": "doi:10.1016/j.joule.2024.03.001",
      "op": "new",
      "relevance": "high",
      "why": "为什么这条与订阅相关 / 为什么归为这个 op（一句话，可复核）",
      "evidence": {
        "source_id": "S2",
        "locator": "S2#r1.title",
        "quote": "逐字复制的记录字段文本"
      },
      "alert": true,
      "alert_group": "G1",
      "suppress_reason": ""
    }
  ],
  "alert_groups": [
    {"group_id": "G1", "title": "窗口内新增与版本更新", "members": ["doi:..."],
     "delivery": "digest|immediate", "merge_reason": "为什么合并成一条"}
  ],
  "coverage_notes": ["某来源只覆盖窗口后段，前段由另一来源支撑"],
  "misses": ["某来源 429 无 payload；该来源本窗口缺失"],
  "uncertainty": ["两条记录仅年份精度，边界归属存疑"],
  "status_note": "一句话总结完成到哪一步"
}
```

### 2.1 字段字典

| 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|
| `subscription.query` | string | 建议 | 原样取 `case.json`/`task.md` 的检索式，不改写成自己的话 |
| `subscription.sources` | string[] | 否 | 用 `init` 给的 `S1..Sn`；写来源名会与产物对不上 |
| `window.start` / `end` | `YYYY-MM-DD` | 是 | 左闭右开；`start < end`；通常等于 `index.json.window`，不一致时 `check` 不报错但简报以 draft 为准 |
| `window.basis` | string | 是 | 逐条列出线索来源，用于复算 |
| `dedup_rules.keys` | string[] | 否 | 缺省 `["doi","arxiv","title_fp"]` |
| `decisions` | object[] | 是 | **必须覆盖 `show` 列出的每一个 `work_key`**，少一个报 `decision_missing` |
| `decisions[].op` | enum | 是 | `new` \| `update` \| `retract` \| `late_index` \| `seen` \| `out_of_window` |
| `decisions[].relevance` | enum | 是 | `high` \| `medium` \| `low`；留空降级为 `unreviewed`（产物可出，但 `selfcheck` 报 mechanical） |
| `decisions[].why` | string | 是 | 相关性依据 + op 依据；不许只写"相关" |
| `decisions[].evidence.source_id` | string | 是 | `S<n>` |
| `decisions[].evidence.locator` | string | 是 | `S<n>#r<m>` 或 `S<n>#r<m>.<field>`，见第 3 节 |
| `decisions[].evidence.quote` | string | 是 | **逐字**取自该记录；改写即 `quote_not_found` |
| `decisions[].alert` | bool | 是 | `op ∈ {new,update,retract}` 时为 `false` 必须给 `suppress_reason` |
| `decisions[].alert_group` | string | 建议 | 必须存在于 `alert_groups[].group_id` |
| `decisions[].suppress_reason` | string | 条件 | 抑制理由，建议带理由码，如 `late_index_backfill: published 2019, indexed 2024-03` |
| `alert_groups[].members` | string[] | 是 | 元素是 `work_key`，且这些 work 的 `alert=true` |
| `coverage_notes` / `misses` / `uncertainty` | string[] | 建议 | `misses` 写"缺什么"，`uncertainty` 写"哪里不确定"，两者不可混用 |

### 2.2 枚举不全时的降级

| 情况 | 行为 |
|---|---|
| `op` 非法 | 保留机械 `auto_op`，记 `degradations`，轨迹里 `op_differs_from_mechanical=true` |
| `relevance` 缺失/非法 | 置 `unreviewed`，`check` 记 warning，`selfcheck` 报 `trail.reviewed` FAIL |
| `evidence.quote` 缺失 | `quote_verified=false`，轨迹留痕，`check` 记 `quote_missing` warning |
| `work_key` 不在快照里 | 该决策被忽略，记 `unknown_work_key` |
| 整个 draft 缺失 | 全部按机械结果出，`status=partial`，`degradations` 写明"未复核" |

---

## 3. locator 规范

| 形式 | 指向 | 例 |
|---|---|---|
| `S3#r7` | 第 3 个来源文件的第 7 条记录（1 起） | `S3#r7` |
| `S3#r7.title` | 该记录的标题字段 | `S3#r7.container-title` |
| `S3#r7.doi` | 该记录的 DOI 字段 | — |

规则：

1. `S<n>` 由 `init` 分配，与 `index.json.sources[].source_id` 一致；文件名只是辅助，**不要用文件名当 locator**。
2. 引文校验把 `quote` 与整条记录的所有字段文本比对（NFKC + 去空白 + 去标点差异），因此引文可以跨字段但必须逐字。
3 quote 太短（< 4 个字符）视为无效，避免"用 `2024` 凑证据"。
4. 找不到引文时**不要**改成"近义改写"，应换成记录里真实存在的片段，或把该条降级为 `uncertainty`。

---

## 4. `result.json` 信封

```json
{
  "<output_contract 的每个键>": "...",
  "case_id": "smoke-01",
  "status": "ok|partial|insufficient_evidence|input_error",
  "sources": [{"source_id": "S1", "file": "materials/x.json", "role": "state|records|retract|version|fulltext|note",
               "kind": "table|binary|text", "n_records": 3, "status": "ok|empty|failed|not_parsed", "note": ""}],
  "uncertainty": ["..."],
  "pending_human": ["..."],
  "errors": [{"code": "quote_not_found", "where": "doi:...", "detail": "..."}],
  "degradations": ["..."],
  "changes": [{"step": "build", "artifacts": [...], "reviewed": 4, "mechanical_fallback": 0}],
  "counts": {"records_total": 6, "works_total": 4, "duplicate_records": 2,
             "new": 1, "update": 1, "retract": 1, "late_index": 1, "seen": 0, "out_of_window": 0,
             "alerted": 3, "identity_1": true, "identity_2": true, "identity_3": true},
  "fingerprints": {"input": "sha256[:32]", "decisions": "sha256[:32]", "skill": "literature-watch-desk 1.0.0"},
  "runtime": {"skill": "...", "stage": "build", "seconds": 0.12,
              "contract_keys": 9, "unfilled_contract": "none|['k1','k2']"}
}
```

### 4.1 契约回填规则

1. **先按同名键取**：`output_contract` 的键与内部产物同名时直接用。
2. 否则按**关键词映射**（`desk.fill_contract` 的 `FILL` 表，按顺序匹配）：

| 契约键像 | 回填内容 |
|---|---|
| `candidate*/paper*/record*/item*/article*/literature*/work*` | 候选表（每 work 一行，含 op/relevance/evidence） |
| `rank*/priorit*/order*/sort*/top*` | 与候选表同序的排序结果 |
| `screen*/filter*/relevan*/inclusion*/criteri*/decision*` | 逐条筛选依据（work_key/op/relevance/why） |
| `evidence*/quote*/locator*/provenance*/trace*/justif*/audit*` | 决策轨迹（before/after + locator + quote） |
| `query*/search*/strategy*/express*/keyword*` | 订阅检索式 |
| `window*/period*/date_range*/time_range*/interval*/snapshot*` | 窗口对象（start/end/timezone/basis） |
| `source*/database*/coverage*/provider*` | 来源清单与状态 |
| `dedup*/duplicate*/merge*/normaliz*/canonical*` | 去重键与归一化规则 |
| `retract*/withdraw*/correction*/erratum*` | 撤稿类条目 |
| `version*/revision*/update*` | 版本更新类条目 |
| `alert*/notif*/digest*/deliver*/remind*` | 提醒组 |
| `miss*/gap*/omit*/missing*/absent*` | 遗漏与缺口 |
| `status*/progress*/state*` | 状态说明 |
| `uncertain*/limitation*/risk*/caveat*` | 不确定与限制 |
| `count*/stat*/metric*/number*` | 计数对象 |
| `method*/process*/workflow*/procedur*` | 方法说明 |
| `artifact*/file*/deliverable*` | 产物清单 |
| `change*/log*/history*/run*` | 变更记录 |
| `brief*/report*/markdown*/narrative*/summary*/conclusion*/finding*` | 简报全文 |
3. 仍未命中 → 按契约声明类型给空值（`array`→`[]`、`object`→`{}`、`string`→`null`），并把键名写入 `pending_human` 与 `runtime.unfilled_contract`。
4. **键名永不改名、永不删除**；`output_contract` 是 dict 时按其键，是 list 时按其中的 `name`/`key`/`field`。

### 4.2 status 语义

| 值 | 含义 | 判定 |
|---|---|---|
| `ok` | 全部 work 有人工决策、引文校验通过、契约无空缺 | 默认目标 |
| `partial` | 有机械兜底、有 `check` 错误、契约有空缺或来源有失败 | 可接受的降级 |
| `insufficient_evidence` | 没有可用记录/没有可判定的 work | 空窗口、材料不可解析 |
| `input_error` | 输入目录或 `case.json` 不可用 | 最底层降级 |

---

## 5. 产物字段字典

### `candidates.csv`（每 work 一行）

| 列 | 说明 |
|---|---|
| `work_key` | 稳定键，跨窗口不变 |
| `op` | 六种之一 |
| `title` / `doi` / `arxiv_id` / `venue` | 代表记录的元数据 |
| `published` / `published_prec` | 代表记录出版日期与精度（`day\|month\|year`） |
| `indexed` | 各来源中的最晚入库时间 |
| `version` | 版本号/版本串 |
| `sources` / `n_records` | 覆盖该 work 的来源与原始记录数 |
| `relevance` / `alert` / `alert_group` | Agent 的判断与提醒归属 |
| `suppress_reason` | 抑制理由（未抑制为空） |
| `evidence_locator` / `evidence_quote` | 逐字证据 |
| `why` | 筛选依据 |
| `verified` | 引文是否命中（`true/false`） |

### `decision_trail.jsonl`（每 work 一行，追加型）

关键字段：`ts`、`case_id`、`work_key`、`op`、`auto_op`、`op_differs_from_mechanical`、`before`（基线记录）、`after`（代表记录）、`change_signals`、`duplicates`、`decision{relevance,why,alert,alert_group,suppress_reason}`、`evidence`、`quote_verified`、`mechanical_reasons`、`reviewed`。

`before=null` 表示该 work 在上一快照不存在；非空时必须能解释 `update`/`retract` 的差异来源。

### `watch_brief.md`

固定章节：订阅与窗口 → 来源覆盖 → 新增 → 版本更新 → 撤稿 → 延迟入库 → 已见/窗口外计数 → 提醒投递 → 遗漏与不确定 → 复算步骤。每条条目都带 `work_key`、locator 与逐字引文，便于人复核。

---

## 6. 最小可用 draft 示例（示例，非正式案例结果）

```json
{
  "subscription": {"query": "perovskite tandem stability", "sources": ["S1", "S2"], "timezone": "UTC"},
  "window": {"start": "2024-03-01", "end": "2024-04-01", "timezone": "UTC", "basis": "S1 watermark"},
  "decisions": [
    {"work_key": "doi:10.1016/j.joule.2024.03.001", "op": "new", "relevance": "high",
     "why": "直接研究订阅问题的对照实验，且出版日期落在窗口内",
     "evidence": {"source_id": "S2", "locator": "S2#r1.title", "quote": "<记录标题原文>"},
     "alert": true, "alert_group": "G1"}
  ],
  "alert_groups": [{"group_id": "G1", "title": "窗口内新增", "members": ["doi:10.1016/j.joule.2024.03.001"], "delivery": "digest"}]
}
```

这份草稿能通过 `check`，但只覆盖 1 个 work；真实案例必须覆盖全部 `work_key`。

---

## 7. 交付前自查

1. `python3 scripts/main.py check` → `errors=0`，`coverage.ratio=1.0`，`quote_hit_rate=1.0`。
2. `python3 scripts/main.py selfcheck` → 全部 PASS。
3. 抽 3 条决策，人工核对 `quote` 是否真的出现在 `S<n>#r<m>` 指向的记录里（不要信任自己的记忆）。
4. `result.json` 的 `runtime.unfilled_contract` 为 `none`；`counts` 三条恒等式为 `true`。
5. 简报里每个来源都有一行；失败来源在 `degradations` 与 `misses` 双处可查。
