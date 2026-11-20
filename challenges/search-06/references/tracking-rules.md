# 追踪规则表（窗口 / 去重 / op 判定 / 来源适配 / 提醒抑制）

本文件是 `literature-watch-desk` 的**判定规则字典**。脚本里的实现与这里的表格一一对应；两者冲突时以本文件为准并同步改代码（见最后一节"维护契约"）。

所有规则只处理**元数据层**：标题、标识符、venue、日期、版本、类型、摘要片段。不做全文推断，不补造字段。

---

## 1. 时间轴：两条线，三个量

一条记录有两条时间线，混用会让"新"失真：

| 量 | 含义 | 常见来源字段 |
|---|---|---|
| `published` | 该文献**公开发表/上线**的日期（预印本、正式版各自一个） | `published`、`published-online`、`published-print`、`issued`、`firstPublicationDate`、`pubDate`、`year` |
| `indexed` | 该**来源**把这条记录收进库的时点 | `created.date-time`、`created.timestamp`、`firstIndexDate`、`indexed`、`imported_at`、`insertDate`、`date` |
| `version` | 版本号（预印本 v1/v2，或出版方的 revision） | `version`、`j`、`versionNumber`、arXiv 后缀 `vN` |

判定"新"用 `published`，判定"本窗口抓到了它"用 `indexed`。二者都缺时才退化为"无法判定"，写进 `uncertainty`，不默认成新。

### 1.1 日期解析与精度

认这些形态，其余不猜：

| 输入 | 解析为 | 精度 |
|---|---|---|
| `2024-03-12` | `2024-03-12` | day |
| `2024-03-12T09:30:00Z` | 折算到订阅时区后取日期 | day |
| `2024-03` | `2024-03` | month |
| `2024` | `2024` | year |
| `12 Mar 2024` / `Mar 12, 2024` | `2024-03-12` | day |
| `[[2024,3,12]]`（Crossref `date-parts`） | `2024-03-12` | day |

**精度不升级**：`2024-03` 不写成 `2024-03-01`。做窗口比较时，低精度日期按"该精度区间的最早一天"参与比较（`2024-03` → `2024-03-01`），并在 `uncertainty` 记录"边界归属存疑"，因为它可能落在窗口外。

### 1.2 时区

1. 订阅时区优先取 `case.json` 的 `timezone` / `tz` / `zone`；无则 `draft.subscription.timezone`；再无则 `UTC`。
2. 带偏移的 datetime 先折算到订阅时区再切日；不混用来源本地时区。
3. 简报必须写明时区，否则跨窗边界会被复核者读错。

### 1.3 窗口定义与来源优先级

窗口语义固定为**左闭右开** `[start, end)`。

`start` 候选（取最晚者，因为它代表"上次看到哪里"）：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | 状态源的 `watermark` / `last_sync` / `last_seen` / `cursor` 日期 | 最可信的水位 |
| 2 | `case.json` 的 `window.start` / `from` / `since` / `start_date` | 出题方给定 |
| 3 | `task.md` 正文里成对出现的日期中较早者 | 兜底，需在 basis 标注 `task-text` |
| 4 | 当前快照里最早的 `published` | 最后兜底，等于"全窗口" |

`end` 候选：`case.json` 的 `window.end` / `to` / `until` > `task.md` 日期对中较晚者 > 快照里最大日期 + 1 天。

`window.basis` 必须逐条列出用到的线索（如 `state:2024-03-01; case:end=2024-04-01`），这是"可回放"的一部分。窗口缺失或 `start >= end` 时 `check` 报 `window_missing` / `window_invalid`，产物照出但 `status=partial`。

### 1.4 连续性

一个订阅的多窗口应满足 `end[n] == start[n+1]`。本 Skill 一次只复算一个窗口，因此：

- 在 `coverage_notes` 里写明本窗口的 `[start, end)` 与上一窗口的衔接方式；
- 若状态源水位晚于窗口 `start`，说明中间存在**未覆盖间隙**，必须写进 `misses`（这正是"窗口漂移造成整段漏检"的典型成因）；
- 若水位早于窗口 `start`，属于**回溯补抓**，重复覆盖的条目会被去重键吸收，不产生二次提醒。

---

## 2. 去重：三把键，并查集合并

同一篇文献在不同来源里有四种常见变体：大小写/标点差异、DOI 与 arXiv 号并存、预印本与正式版、同文多源转载。合并靠"任一键相同即同一 work"。

### 2.1 键定义

| 键 | 归一化规则 | 例 |
|---|---|---|
| `doi` | 去 `https://doi.org/`、`dx.doi.org/`、`doi:` 前缀；小写；去尾部 `. , ; ) ]` 与空白；必须匹配 `^10\.\d{4,9}/\S+$` | `https://doi.org/10.1000/ABC.` → `10.1000/abc` |
| `arxiv` | 从 DOI（`10.48550/arXiv.2401.01234`）、`eprint`、`id`、URL 抽编号；**去版本后缀** `vN`，版本号单独存 | `arXiv:2401.01234v3` → `arxiv:2401.01234`，version=3 |
| `title_fp` | NFKC → 小写 → 去 HTML 标签 → 只留字母/数字/汉字/希腊字母 → sha1 前 12 位；归一化后长度 < 8 视为无效 | `Phase-Stable Wide-Bandgap Perovskites!` 与 `phase stable wide bandgap perovskites` 同指纹 |

### 2.2 合并与代表记录

1. 用并查集把所有记录按上述键合并成 work。
2. 组内排序：`(版本号, published, 是否正式版 DOI)`，末位为**代表记录**；正式版优先于 `10.48550/...` 预印本 DOI。
3. `work_key` = 代表记录的 DOI > arXiv 号 > `title:<指纹>`。**同一 work 跨窗口必须得到同一 work_key**，否则幂等会失效。
4. 组内非代表记录写入 `duplicates`（含 locator、来源、DOI、标题），它们**不产生提醒**，但要在简报里计数。
5. 组内 `published` 最早值记 `published_first`（首次公开），各来源 `indexed` 的最大值记 `indexed_max`（最晚被收录）。判定用这两个聚合量，展示用代表记录的原值。

### 2.3 何时不该合并

- 标题指纹相同但**作者与年份都不同**：可能是"同名不同文"（如系列综述第 1/2 篇）。若 `published` 相差超过 3 年，视为不同 work 并在 `uncertainty` 记录判断依据。
- 只有 `title_fp` 相同、双方 DOI 都非空且不同：多为"勘误 vs 原文"或"预印本 vs 正式版"，先按 `update` 处理并保留两组 DOI，不要强行合成一条记录。

---

## 3. op 判定矩阵

`auto_op` 由脚本算，`op` 由 Agent 判定。二者不一致时 `decision_trail.jsonl` 的 `op_differs_from_mechanical=true` 会留痕——这是有意设计的：机械规则会误判，人工复核必须可见。

| 优先级 | 条件 | op | 语义 | 默认提醒 |
|---|---|---|---|---|
| 1 | 类型含 retraction/withdrawal/expression of concern，或标题以 Retraction/Withdrawal 开头，或 `update-to` 指向撤稿 | `retract` | 该 work 被撤/被声明关切 | 是（最高优先，绕过摘要合并） |
| 2 | 已见（键命中上次快照）且 `change_signals` 非空 | `update` | 已见 work 的版本/venue/DOI/日期/类型变化 | 是（与同主题合并） |
| 3 | 未见且组内 `change_signals` 非空（预印本→正式版、版本递增、venue 变） | `update` | 同一 work 的新版本首次进入视野 | 是 |
| 4 | 未见 且 `published_first ∈ [start, end)` | `new` | 本窗口首次公开的新文献 | 是 |
| 5 | 未见 且 `published_first < start` 且 `indexed_max ∈ [start, end)` | `late_index` | 旧文新入库（数据库滞后） | **否**（进简报补录区） |
| 6 | 已见且 `change_signals` 为空 | `seen` | 上次已见、无变化 | 否 |
| 7 | 其余（出版与入库都落在窗口外、无可用日期） | `out_of_window` | 不属本窗口 | 否 |

### 3.1 `change_signals` 的判定口径

| 信号 | 触发 | 备注 |
|---|---|---|
| `preprint_to_version_of_record` | 组内既有 `10.48550/arxiv.*` 的 DOI，又有非 arXiv 的出版方 DOI | 最典型的"更新而非新增" |
| `venue_changed` | 组内或与基线相比 venue 不同 | 忽略 `S1`/`crossref`/`europepmc`/`ppr` 这类来源标签，它们不是 venue |
| `version_bumped` | 版本号不同 | arXiv `v1→v2` 常意味着内容修订 |
| `date_changed` | 与基线相比 `published` 不同 | 可能是"在线先发→正式卷期" |
| `type_changed` | 类型变化 | 如 `preprint → journal-article` |
| `doi_changed` | 与基线相比 DOI 不同但键仍相连 | 预印本 DOI → 正式版 DOI |
| `correction_notice` | 组内出现 correction/erratum/corrigendum | 处理为 `update`（不是 `retract`） |

### 3.2 常见误判与纠正

| 现象 | 机械结果 | 应做的判断 |
|---|---|---|
| 撤稿声明本身被当成新论文 | `new` | 改 `retract`，并把被撤的原文放进 `before` |
| 预印本与正式版分属两个来源 | 两条 `new` | 合并成一条 `update`，`before=预印本` |
| 老文献本窗口才入库 | `new` | 改 `late_index`，不提醒 |
| 只有年份精度、跨窗口边界 | 视实现落入 `new`/`out_of_window` | 在 `uncertainty` 写明，`why` 说明取舍 |
| 同一文被两个来源转载且 DOI 写法不同 | 两条记录 | 去重键吸收；若 DOI 确实不同，保留两条并说明 |

---

## 4. 来源适配表

`init` 按**内容特征**识别记录列表，不按文件名猜。新增来源类型时在此登记字段别名。

| 来源形态 | 记录所在路径 | 标识符 | 日期 | venue | 备注 |
|---|---|---|---|---|---|
| Crossref REST | `message.items[]` | `DOI` | `published.date-parts`（+ `created.date-time` 作 indexed） | `container-title` | `type` 含 `retraction` 时立即判 retract；`update-to` 指向被撤记录 |
| EuropePMC | `resultList.result[]` | `doi` / `id` | `firstPublicationDate` | `journalTitle`（**不要用 `source`，那是库标识 MED/PPR**） | `pubType=preprint` 常与 Crossref 正式版合并 |
| 出版商 JSON | 顶层数组或 `payload.records[]` | `doi` / `identifier` | `published` / `online_date` | `journal` / `publication` | 字段名不统一，靠别名表吸收 |
| 导出 JSONL | 每行一个对象 | 任意 | 任意 | 任意 | 坏行跳过并记 `degradations`，不中断 |
| CSV/TSV | 表头含 title+doi/date 列 | `doi` 列 | `date`/`published` 列 | `journal` 列 | 分隔符自动识别 `, ; \t` |
| 上次快照 / `import_state` | `previous_snapshot[]`、`seen_ids[]`、`works[]` | DOI/arXiv 列表 | `watermark`/`last_sync` | — | 只作基线与水位，**不进候选池** |
| 撤稿/版本记录 | 任意含 `retraction`/`correction`/`version` 的文件 | DOI | 通知日期 | — | 用于 retract/update 证据 |

识别失败的容器（PDF/DOCX/ZIP/未知）登记为 `role=fulltext|unknown`、`status=not_parsed` 并记 `degradations`；本 Skill 不从全文抽事实。

---

## 5. 提醒合并与抑制

提醒的目标是"低噪声、高信息密度"，不是"发得多"。

### 5.1 合并

| 规则 | 做法 |
|---|---|
| 同主题同窗口 | 一个 `new`/`update` 主题只出一条摘要（`delivery=digest`） |
| 撤稿单独成组 | `delivery=immediate`，不受摘要节奏限制 |
| 同 work 多变更 | 只提醒一次，变更字段在 `before/after` 里列全，不做成两条 |
| 同来源同批次 | 合并为一条，保留 `sources` 计数 |

### 5.2 抑制（必须留痕）

| 抑制对象 | 理由码 | 去向 |
|---|---|---|
| 重复副本（同一 work 的非代表记录） | `duplicate_copy` | 简报计数 |
| `late_index` | `late_index_backfill` | 简报补录区 |
| `seen` | `already_seen` | 简报计数 |
| `out_of_window` | `outside_window` | 不展示明细，只计数 |
| 相关性 `low` 且无方法学新意 | `low_relevance` | 简报"已筛除"，保留 `why` |
| 上一窗口已提醒过（回执键命中） | `already_delivered` | 幂等记录 |

任何 `op ∈ {new, update, retract}` 却 `alert=false` 的决策，**必须**给 `suppress_reason`；`check` 会报 `suppress_unexplained`。抑制不留痕会让复核者无法区分"没发现"和"故意不推"。

### 5.3 幂等

- `input_fp`：输入目录所有文件的 `相对路径:内容哈希` 按名排序后拼接的 sha256。
- `decisions_fp`：每行 `[work_key, op, relevance, why]` 的规范化 JSON 的 sha256。
- 两者都与上次 `build_state.json` 相同 → `changes` 追加 `rerun_same_input: already_delivered=true`，**不产生第二次推送**。

---

## 6. 失败与重试（离线版）

本 Skill 不联网，因此"限流/超时"表现为**输入里已经留下的失败痕迹**：

| 痕迹 | 处置 |
|---|---|
| 来源文件含 `status: 429/500`、`error`、空 `items` | 该来源 `status=failed/empty`，记 `degradations` + `misses`，其他来源照常 |
| JSON 解析失败 | 该文件 `status=failed`，其余继续；整体仍 exit 0 |
| 字段缺失（DOI/日期/标题） | 逐级降级：DOI→arXiv→标题指纹；日期缺失→不参与窗口判定并写 `uncertainty` |
| 同一输入重跑 | 幂等：产物重写、指纹相同、`already_delivered=true` |

重跑不产生二次推送的前提是 `work_key` 稳定——这也是第 2.2 节强调"跨窗口必须同键"的原因。

---

## 7. 计数恒等式

`result.json.counts` 必须满足：

```
records_total − works_total = duplicate_records        # 恒等式 1：副本计数
works_total = new + update + retract + late_index + seen + out_of_window   # 恒等式 2：op 完备
alerted ≤ new + update + retract                        # 恒等式 3：提醒上界
```

`check`/`selfcheck` 逐条验证，任一不成立即报 `counts_identity_failed`。这三条是"结果完整性"最便宜的自证方式：数目对不上，说明有 work 没被判定。

---

## 8. 维护契约

改规则时必须三处同步，否则包内行为会不一致：

1. 本文件的表格；
2. `scripts/core.py` 里的 `classify()` / `group_works()` / 常量（`OPS`、`RETRACT_TYPES`、`VENUE_ORDER`）；
3. `scripts/desk.py` 里的 `validate()` 枚举校验与 `references/work-contract.md` 的枚举说明。

新增来源类型：在 `core.py` 的字段别名集合（`TITLE`/`DOI`/`ARX`/`VENUE`/`PUB`/`IDX`/`TYPE`/`VER`）加别名，并在第 4 节表格登记一行。
