# 可复用授权核验清单（licence checklist）

配套 `patent-search-dossier` v1.0.0。本清单用于给每个数据来源做**绿/黄/红**依赖分级，并落成
`license_gate.md` 的一个表行；口径与 `scripts/kglib.py` 的 `licence_entries()` 一致。

## 1. 分级判据与降级方案

| 分级 | 判据 | 可做 | 降级方案（可直接抄） |
|-|-|-|-|
| `green` | 材料明确允许检索与展示 | 引用原文、展示字段 | — |
| `yellow` | 内部使用/有限展示/未声明 | 引用结论与字段名 | 「仅给结论 + source_id/locator，不给长段原文」 |
| `red` | 需登录/受限/保密/禁止再分发 | 仅登记已排除 | 「不抓取、不引用；记录已排除原因与所需授权」 |

**默认纪律**：材料**未声明许可** → 按 `yellow` 处理，并写入 `gaps`（`why = 来源许可未声明`）。
`red` 来源的原文一律不进主结果，只在 `license_gate.md` 登记原因。

## 2. 逐来源核验清单（每条打勾）

1. 来源名称与库名/版本是否写清（`source_name`）？
2. 是否声明了允许检索与允许展示的范围（`display_scope`）？
3. 分级落在哪一档（`green` / `yellow` / `red`）？判据是哪一句？
4. 若为 yellow：降级方案是否写明「只给结论 + locator」？
5. 若为 red：是否已排除出主结果（`excluded_from_output=true`）并写明所需授权？
6. 是否需要登录/付费墙？若是，是否**没有**尝试抓取？
7. 是否有留存期限或保密要求？是否写入 `boundaries`（`license_restricted`）？
8. 是否有转载页/聚合站被当成官方依据？若有，状态一律降级为线索级并 `needs_official_verification=true`。

## 3. 边界类型字典（`boundaries[].type`，可直接引用）

| type | 触发条件 | 示例句（可直接改写） |
|-|-|-|
| `legal_status_unknown` | 任一状态为 unknown | 「材料未提供官方登记页，状态保持 unknown，不得用于有效性判断。」 |
| `family_not_exhaustive` | 存在族边 | 「仅观察到 N 条链接，族可能不完整。」 |
| `ocr_merged_page` | 材料含影印件/合并页 | 「第 4/5 页 OCR 合并，claim 4 截断，未纳入摘录。」 |
| `claim_scope_unexplained` | 只摘录未解释 | 「仅摘录权利要求原文，未做范围解释或等同判断。」 |
| `patent_vs_paper_scope` | 同时检索专利与文献 | 「专利按号码/族定位，文献按 DOI/主题匹配，未混排排序。」 |
| `license_restricted` | 存在 yellow/red | 「商业库导出行标注禁止再分发，未抓取未引用。」 |
| `metadata_missing` | 字段缺失 | 「EP 成员缺生效国与审查状态字段。」 |
| `coverage_gap` | 检索面未覆盖 | 「未获得完整同族表，族结论限于 observed 范围。」 |

## 4. 法律状态来源分级（`status_provenance.csv` 的 `source_kind`）

| `source_kind` | 含义 | 结论强度 | 强制字段 |
|-|-|-|-|
| `official_register` | 官方登记页/官方抄录 | 可直接陈述（仍需 `as_of`） | `as_of`、`source_id`、`locator` |
| `facsimile_ocr` | 影印件 OCR | 仅历史快照 | `needs_official_verification=true` |
| `observed_link` | 观察到的链接页/二手页 | 仅线索 | `needs_official_verification=true` |
| `aggregator` | 聚合站/转载 | 仅线索，`confidence=low` | `needs_official_verification=true` |

状态取值枚举：`unknown / granted / pending / expired / abandoned / withdrawn / rejected / not_in_force / revoked`。
纪律：① 无官方登记 → `unknown`，不得推断「已授权/已失效」；② `as_of` 用查询日或材料标注日；
③ 同一专利出现两个状态 → 写 `conflicts[]` 并进 `boundaries`，不擅自二选一；
④ 影印件上的授权公告日期只说明当年授权公告，不等于现行有效性。

## 5. 交付前自查（逐条打勾）

1. `license_gate.md` 每个来源都有分级、可展示范围与降级方案。
2. red 来源没有出现在任何引文里；yellow 来源只给结论与定位。
3. `gaps` 里写清了未声明许可的来源与补齐时机。
4. 状态行都有 `as_of` + `source_kind` + `needs_official_verification`；非官方来源恒 true。
5. `boundaries` 覆盖实际触发的类型，且 ≥3 条。
6. 没有把转载页/聚合站当官方登记依据。
