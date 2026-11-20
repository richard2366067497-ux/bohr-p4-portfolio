# rules.md — 编辑类型、守卫判据、工作稿与字段字典

本文件是 `claim-preserving-polish` 的规则来源。脚本里的词表逻辑与本文一致；两者冲突时以本文为准并修脚本，不要反过来放宽判据。

---

## 一、编辑类型词表（`changes[].type`）

取值：`grammar`、`syntax`、`agreement`、`tense`、`voice`、`article`、`preposition`、`word_choice`、`terminology`、`register`、`concision`、`cohesion`、`punctuation`、`spelling`、`capitalization`、`other`。
另有两个声明型取值：`restructure`（整段重排，需在 reason 说明为何必须）、`translate`（跨语言改写）。
类型必须与 reason 一致：reason 说的是主谓一致，type 就不能写 `restructure`。

---

## 二、最小编辑边界

| 判据 | 阈值/规则 | 判定码 |
|-|-|-|
| 字符相似度 | 单条改动与原文相似度 < 0.50，且无 `restructure`/`translate` 类型 → 回退 | `REWRITE_RISK` |
| 段落结构 | 不合并、不拆分段落；段落数与顺序不变 | `ANCHOR_MISS` / 覆盖缺口 |
| 标题 | 默认不改（除非标题本身有语法错误并在 `changes` 里说明） | `COVERAGE` |
| 冻结块 | 代码块、`$$…$$`、`\begin{equation}` 等整块不参与改写 | 只核符号守恒 |
| 新增内容 | 不得新增事实、数据、引用、结论；缺什么写进 `human_review.md` | `ATOM_ADDED`（软） |

改写优先顺序：**(1) 换词 → (2) 调短语语序 → (3) 拆/合句 → (4) 重写句子 → (5) 重写段落（基本不该发生）**。走到 (4) 就要有明确理由；走到 (5) 会被相似度判据挡下。

---

## 三、文体语域表

| genre | 人称 | 强度基线 | 禁止 | 中文版额外要求 |
|-|-|-|-|-|
| `journal` | 第三人称，We 可接受 | 结论按 3/2 级分层，不越级 | 宣传化形容（novel、remarkably）、绝对化 | 避免“众所周知”“极大地” |
| `abstract` | 省略框架语 | 与正文结论同强度，不得加强 | 新增方法细节、`In this paper` 堆叠 | 一句一信息，删“本文”复指 |
| `thesis` | 允许“我/本章” | 综述部分可 2 级，结论章按证据定 | 章节交叉引用改号 | 术语与目录一致 |
| `grant` | 以团队为主语 | 必要性可强，成果须与证据对齐 | 把“预期”写成“已实现” | “将”“拟”不得删 |
| `review_response` | 逐条对位审稿意见 | 回应强度不得高于证据 | 改页码/行号/引用编号 | 引用审稿人原话须逐字 |

语域清单（命中即应改，但**必须**保持强度）：

- 口语：`a lot of / kind of / we think / it is well known that / 很多 / 我们认为`
- 宣传：`novel / remarkable / excellent / significantly better（无统计支撑）/ 极大地 / 显著优于（无检验）`
- 绝对：`always / never / all / completely / 完全 / 必然 / 一律`（原文有则保留，没有则不得新增）
- 人称误用：方法段用 `we` 描述他人工作；结果段用 `I`（期刊体）
- 冗余名词化：`the implementation of the optimization of` → `optimizing`
- 逻辑连接词滥用：连续 3 句以上 `Moreover/Furthermore/In addition`

---

## 五、限定强度与否定判据

### 5.1 完整分级（摘录自 `assets/hedge_lexicon.json`）

| 级 | 英文标记（部分） | 中文标记（部分） |
|-|-|-|
| 4 assertive | demonstrate, proves, confirm, establishes, clearly, undoubtedly, always, never, conclusively, must | 证明、证实、确认、显然、毫无疑问、必然、总是、从不、完全 |
| 3 indicative | show, indicates, find, reveal, we conclude, likely, predominantly, primarily, mostly, consistently | 显示、表明、发现、揭示、很可能、主要、大多、一致地 |
| 2 possible | suggest, may, might, could, appear, seem, possibly, potential, presumably, tend to, in part, some, several | 提示、暗示、可能、或许、似乎、推测、倾向于、部分、某些、若干 |
| 1 associative | associated with, correlates with, linked to, co-occur, relationship between | 相关、关联、伴随、共变、有关 |
| 0 unresolved | cannot exclude, remains unclear, insufficient, not significant, no evidence, further work is needed | 无法排除、尚不清楚、证据不足、未显著、无证据 |

### 5.2 判定表

| 情形 | 判定 | 严重度 |
|-|-|-|
| 改后等级 = 改前 | 通过 | — |
| 改后 > 改前 | `CLAIM_STRENGTHENED` | 硬 |
| 改后 < 改前 | `CLAIM_WEAKENED` | 硬 |
| 改前有限定词、改后一个都没有 | `HEDGE_DROPPED` | 硬 |
| 整体等级不变但主张内核词（may/might/could/suggest/indicate/associate…）被删 | `HEDGE_MARKER_DROPPED` | 硬 |
| 限定词消失但改文改成否定句 | `HEDGE_DROPPED_NEGATED` | 软（人工确认等价） |
| 改前无限定、改后新增 | `HEDGE_ADDED` | 软 |
| 已填 `hedge_override.reason` | `HEDGE_SHIFT_DECLARED` | 软 |
| 相关 → 因果 | `CAUSAL_UPGRADE` | 硬 |
| 因果 → 相关 | `CAUSAL_DOWNGRADE` | 软 |
| 否定标记数变化 | 英文 `NEGATION_SCOPE_CHANGED`；中文软提示 | 硬/软 |
| 新增绝对化表述 | `ABSOLUTE_ADDED` | 软 |

### 5.3 两点豁免

1. **指路句**：`Fig. 2 shows…`、`表 3 列出…`、`as shown in Table 1` 中的 show/present/display 是版式动词，脚本先掩掉再比较，不参与强度判定。
2. **翻译模式**：`mode=translate` 时不做逐词强度比对，只提示 `HEDGE_UNCHECKED_TRANSLATE` 并要求人工核对——中文“可能”对英文 `may/might/could` 无法靠词表定位。

### 5.4 `hedge_override` 的正确用法

```json
"hedge_override": {"from": 3, "to": 2, "reason": "审稿意见指出 n=3 不足以支持 show，作者已同意降为 suggest（对应审稿意见 R2-3）"}
```

只在**有外部依据**（审稿意见、作者指示、数据重算）时使用；用它来“放行自己改过头的句子”会在评审时暴露。

---

## 六、术语治理

### 6.1 锁定式

`glossary[].locked` 是改后全文唯一写法；`variants` 是要被消灭的异写。`build` 会对 `polished.md` 做回扫：

- `variants` 仍出现 → `TERM_DRIFT`（软，逐段定位）
- 缩写在长形式之前出现 → `ABBR_BEFORE_DEF`（软）

### 6.2 处理顺序

1. 若 `/input` 带术语表（文件名含 `glossary`/`terminolog`/`术语`），以它为准，冲突项写 `uncertainties`，不静默择一。
2. 否则按 `show` 的候选自己定；同一概念只留一条，`locked` 选**出现最多或首次定义**的写法。
3. 缩写首现规则：`全称 (缩写)` 一次，其后仅缩写；原文没有缩写就不要新增缩写。
4. 大小写与连字符属于术语的一部分：`residue-level attention` 与 `residue level attention` 是两个写法，必须统一。

### 6.3 跨章节漂移

标题/摘要/正文/图注之间最容易漂移。`build` 的 `terminology_sweep` 按段落顺序定位首次出现位置，`first_use` 写最早出现的段落 id。

---

## 七、工作稿 `draft.json` 字段字典

| 字段 | 类型 | 必填 | 说明 | 校验 |
|-|-|-|-|-|
| `case_id` | str | 否 | 与 `init` 一致便于核对 | 不一致只记 warnings |
| `task_understanding` | obj | 建议 | `genre`/`target_language`/`audience`/`must_do`/`must_protect` | 缺失不阻断 |
| `glossary[]` | array | 建议 | `concept`/`locked`/`variants`/`first_use`/`abbr`/`decision`/`note` | `variants` 回扫 |
| `items[]` | array | 核心 | 见下 | 逐条守卫 |
| `items[].paragraph_id` | str | 是 | 必须存在于 `segments.json` | 不存在 → `ANCHOR_UNKNOWN_PID` |
| `items[].before` | str | 是 | 逐字复制 `show` 原文（整段或整句） | 定位失败 → `ANCHOR_MISS` |
| `items[].after` | str | 是 | 改后文本；`null` 视为未改 | 空串 → `EMPTY_AFTER` |
| `items[].changes[]` | array | 文本有改动时必填 | `before_span`/`after_span`/`type`/`reason` | 缺 → `CHANGES_MISSING` |
| `items[].hedge_override` | obj\|null | 否 | `{from,to,reason}` | 缺则强度变化即回退 |
| `items[].segment_id` | str | 否 | 句级定位标签，如 `P002-S003` | 只用于显示 |
| `untouched[]` | array | 建议 | `{paragraph_id, reason}`：确实不需改的段落 | 缺失 → 覆盖缺口 |
| `uncertainties[]` | array | 建议 | `{paragraph_id, issue, options[], severity}` | 进 `harness` 复核清单 |
| `result_fields{}` | obj | 否 | 契约字段同名覆盖值（优先级最高） | 键名按去分隔符比较 |

`before` 匹配规则：先逐字匹配，失败则按“空白折叠”再试一次；两次都失败即判 `ANCHOR_MISS`（该条作废，段落保留原文）。

---

## 八、`result.json` 字段字典

### 8.1 信封字段（恒定输出）

核心字段（类型见括号）：`case_id`(str)、`status`(str: answered/partial/insufficient_evidence/input_error)、
`status_reason`(str)、`errors[]`、`degradations[]`、`uncertainties[]`、`pending_human[]`（含 options）、
`runtime{}`、`sources[]`（路径/字符数/sha256/用途）、`coverage{}` 与 `verification{}`
（paragraphs_total/editable/covered/changed/unchanged/needs_human/coverage_ratio）、`before_after_digest{}`、
`deliverables{}`、`terminology_sweep[]`、`limits[]`、`skill{}`（name/version）、`_contract_report[]`。

### 8.2 契约字段映射（`output_contract` → 载荷）

| 字段名命中的关键词（按最长匹配） | 载荷 |
|-|-|
| `polish/revised/rewrite/corrected/final/润色后/全文` | 改后全文（str） |
| `edit/change/revision/diff/modif/修改` | 修改记录数组（含 locator、type、reason、guard） |
| `glossar/terminolog/lexicon/术语` | 术语表数组 |
| `bilingual/parallel/translation/对照/译文` | 段落级 source/target 对照 |
| `verif/check/audit/coverage/metric/stat/校验/覆盖` | 覆盖率与检查摘要（obj） |
| `human/pending/confirm/manual/人工/待确认` | 人工确认条目 |
| `uncertain/ambigu/risk/flag/不确定` | 存疑条目 |
| `source/provenance/evidence/trace/来源/证据` | 材料来源与 sha256 |
| `limit/caveat/gap/限制/边界` | 能力边界 |
| `structure/section/outline/段落/结构` | 段落结构表 |
| `status/state/状态` | 状态字符串 |
| `note/comment/remark/备注` | 摘要说明 |
| `case_id/id` | 案例标识 |

映射不到的字段写 `null`，并在 `_contract_report` 标 `"resolved_as": "unmapped"`；不要为了“都有值”编造内容。

---

## 九、手工兜底：没有脚本时也要交付

若 python 不可用或脚本被环境阻断，按下列顺序手工产出（`degradations` 注明“未使用校验脚本”）：

1. `polished.md`：逐段最小编辑，数字/单位/引用/图表指向逐字照抄。
2. `changes.csv`：`change_id,paragraph_id,locator,type,before_span,after_span,reason,guard`，`guard` 填 `manual`。
3. `glossary.csv`：`term_id,concept,locked,variants,first_use,decision`。
4. `result.json` 最小骨架：

```json
{
  "polished_text": "<全文>",
  "edit_log": [{"paragraph_id": "P001", "type": "grammar", "before_span": "…", "after_span": "…", "reason": "…", "locator": "manuscript.md#P001[0:120]"}],
  "glossary": [],
  "uncertainty": [],
  "case_id": "<案例标识>",
  "status": "partial",
  "errors": [],
  "degradations": ["未使用校验脚本：原子守恒与限定强度为人工核对"],
  "pending_human": [],
  "coverage": {"paragraphs_total": 0, "covered": 0, "coverage_ratio": 0.0}
}
```

`status` 与 `coverage` 按实际填写；不确定就写 `partial`。

---

## 十、回归清单（改词表或改脚本后跑）

1. `python3 -m py_compile scripts/*.py` 全部通过。
2. 正路径：最小案例 `init → show → 写工作稿 → check（0 硬失败）→ build（契约全回填）→ selfcheck`。
3. 负路径 5 类各造一例，必须被拒并回退：改数字、加强限定、删引用、改公式、删否定；外加整段重写 → `REWRITE_RISK`。
4. 空输入 → `input_error`；坏 JSON → 记 `errors` 仍出产物；无工作稿 → `partial` 兜底。
5. 抽查 3 处修改的 `before_span` 能在原文找到、`after_span` 能在改文找到。
6. 抽查 3 个未改段落，确认 `untouched` 理由成立（已合规，不是漏改）。
