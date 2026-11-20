---
name: literature-watch-desk
description: 主题文献订阅的增量追踪台。读取一个案例里的检索式、来源响应快照、上一次快照与入库状态，算出"本窗口相对上次真正的变化"（新增/版本更新/撤稿更正/延迟入库旧文/重复副本），由 Agent 逐条读原始记录并写下相关性判断与提醒取舍，最后产出人可读追踪简报、候选表、逐条决策轨迹与回填 output_contract 的 result.json。用于 latest-literature / 文献发现与追踪 / 定期检索订阅类案例。
version: 1.0.0
---

# 文献增量追踪台（Agent 主答 + 脚本辅助 + 兜底必成）

## 1. 这个 Skill 解决什么

一次主题检索能给出"有哪些文献"，但给不出"**相比上次，多了什么、变了什么、撤了什么、为什么这条不算新**"。本 Skill 把一次订阅的单个时间窗做成一条可复算的判断链：

```
订阅配置(检索式/来源/时区/节奏) → 窗口[start,end) → 各来源记录快照
   → 归一化(DOI/arXiv/标题) → 合并同一 work 的多来源副本与版本
   → 与上一次快照比对 → 每个 work 一个 op 判定 + 逐字证据
   → 提醒合并与抑制 → 追踪简报 / 候选表 / 决策轨迹 / result.json
```

**做**：输入发现、记录抽取与归一化、去重键与版本链合并、窗口与水位计算、新增/更新/撤稿/延迟入库/重复的机械分类、逐条证据定位、计数对账、提醒分组与抑制、可回放产物、契约回填。
**不做**：全文精读、写综述、替作者补元数据、把提醒措辞当科学结论、联网抓取（本 Skill 完全不联网，只读 `/input` 里已有的响应快照）。

追踪的对象是 **work（一篇文献实体）**，不是一个数据库行。所以"预印本先上线、正式版后上线"必须是同一条 work 的一次 `update`（before/after 双态），不是两条 `add`。

## 2. 五命令主路径（先看这段）

```bash
python3 scripts/main.py init      # 发现输入 → 抽记录 → 归一化 → 去重合并 → 窗口/水位 → 机械 diff，并先写一份合法 partial result.json
python3 scripts/main.py show      # 打印窗口、来源覆盖、每个 work 的 before/after 与记录 locator，供逐字引用
#  ↓↓↓ 评审 Agent 亲自读材料，写工作稿 /app/work/draft.json ↓↓↓
python3 scripts/main.py check     # 机械校验：契约键、决策覆盖、quote 逐字命中、窗口归属、计数恒等、提醒规则
python3 scripts/main.py build     # 由工作稿生成 watch_brief.md + candidates.csv + decision_trail.jsonl + result.json（无条件 finalize）
python3 scripts/main.py selfcheck # 复检产物与契约，报告幂等指纹
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> `init` 给出的 `auto_op` 只是机械提示（按日期/版本字段算的初判），**相关性与是否提醒必须由你读完记录后写进 draft**。`build` 在没有工作稿时仍会产出完整但降级的交付（`status=partial` + `degradations` 写明缺口），那是兜底，不是正常路径。

推荐时间分配：`init`/`show` 约 3 成，读材料 + 写 draft 约 5 成，`check`/改稿/`build` 约 2 成。

## 3. 何时用 / 何时不用

**用**：案例给了研究问题或检索式 + 一批来源响应（Crossref / EuropePMC / 出版商 JSON / JSONL / CSV 导出）+ 某种"上次看到哪里"的状态信息，要求产出候选集、筛选依据、遗漏说明。
**不用**：只要单篇抽取（用单文档抽取类 Skill）；要求通读全文下结论；要求真的去联网抓新数据（本 Skill 离线，只复算已有快照）。

判据：输入里能同时找到 ①至少一条文献记录 ②一个时间窗或水位线索 → 用本 Skill。

## 4. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id` / `task_instruction` / `output_contract`）、`/input/task.md`、案例材料（任意层级） |
| 工作目录 | `/app/work`（`index.json`、`draft.json`） |
| 产物 | `/app/output/result.json` + `watch_brief.md` + `candidates.csv` + `decision_trail.jsonl` |
| 覆盖路径 | 三个命令都支持 `--input/--output/--work`，也认 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK`；默认值就是上表，不依赖 CWD |
| 依赖 | 仅 Python 3 标准库；不联网；不写 `/input` |
| 退出码 | **恒 0**；失败写进 `result.json` 的 `errors` / `degradations`，不靠退出码表达 |

`result.json` 顶层必须**原样回填** `output_contract` 的每个键（不改名、不漏键、不合并）。缺内容时按类型给 `null` / `[]` / `{}`，并把缺的键列进 `pending_human`，绝不留空键。信封字段：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`errors`、`degradations`、`sources`、`uncertainty`、`pending_human`、`changes`、`counts`、`fingerprints`、`runtime`。

## 5. 输入发现（按语义认，不按文件名猜）

`init` 递归扫 `/input`，用**内容特征**而不是名字给文件定型：

1. **case.json**：优先 `/input/case.json`，退化为任意 `*.json` 里带 `output_contract` 或 `case_id` 的那个。坏 JSON 记 `case_json_invalid` 继续找。
2. **记录源**：任意 JSON/JSONL/CSV 里能被识别为"文献记录列表"的结构——Crossref 的 `message.items`、EuropePMC 的 `resultList.result`、`payload.records`、顶层数组、JSONL 每行、CSV 表头含 title/doi 等。识别规则：dict 里同时有标题类键与 (标识类键 或 日期类键)。每个文件一个 `source_id`（`S1..Sn`，文件名去掉扩展名后附上，便于人读）。
3. **状态源（上一次快照/入库水位）**：文件名或内容出现 `previous`/`snapshot`/`import_state`/`state`/`watermark`/`last_sync`/`seen`/`cursor`/`baseline`/`manifest`。抽出已见标识集合与水位日期。
4. **版本/撤稿源**：`version`/`retraction`/`correction`/`update`/`erratum` 类文件或 `update-to`/`relation` 字段，用来支持 `update` 与 `retract` 判定。
5. **task.md**：读来理解研究问题与交付口径，绝不作为答案来源。
6. **PDF/DOCX 等全文**：可以登记为来源（`kinds=fulltext`）但不抽取内容；本 Skill 的判断依据是记录元数据与摘要，不是全文。

识别失败的文件记进 `degradations`（`unrecognized_material`），不猜内容。

## 6. 方法说明（每一步在做什么、为什么这样做）

### 6.1 归一化

- **DOI**：去 `https://doi.org/`、`doi:` 前缀，小写，去尾部标点与空白。`10.1000/ABC` 与 `https://doi.org/10.1000/abc` 是同一个。
- **arXiv**：从 DOI（`10.48550/arXiv.2401.01234`）、`id`/`eprint` 字段或 URL 抽编号，**去掉版本后缀 `v1/v2`**，版本号单独存 `version`。
- **标题指纹**：NFKC → 小写 → 去 HTML 标签与全部非字母数字（含中文、希腊字母保留）→ 取前 12 位 sha1。大小写、连字符、冒号、`&` 与 `and`、全半角差异都不影响。
- **日期**：认 `YYYY-MM-DD`、`YYYY-MM`、`YYYY`、`DD Mon YYYY`、`Mon DD, YYYY`、ISO datetime；带 `Z`/`+08:00` 的按声明时区折算到订阅时区再切日。**精度随原字段**记 `day|month|year`，不把 `2024-03` 升级成 `2024-03-01`。
- **双时间轴**：每条记录记 `published`（出版/在线日期）与 `indexed`（`created`/`firstIndexDate`/`date`/`imported_at`，即被该来源入库的时点）。这是本题的核心区分：**出版早于窗口、入库落在窗口内的旧文献是"延迟入库"，不是新发现**。

### 6.2 去重与版本链

同一 work 的多条记录用并查集合并，连接键是 `doi_norm` / `arxiv_base` / `title_fp` 中任意一个相同。合并后：

- `work_key`：优先"正式版 DOI"，无则 arXiv 号，无则 `title:<hash>`。这是稳定键，同一 work 跨窗口不变。
- 组内记录按 `version`、`published` 排序，**末位为当前代表**（latest representative），其余记为副本，写进 `duplicates`（含来源与 locator）——副本不产生提醒。
- 组内出现"venue/DOI/version 变化"或 `update-to` 关系 → 版本链信号，`auto_op=update`，并在 `show` 里打印 before/after。

### 6.3 窗口与水位

`start` 取下列线索里**最晚**的一个（都能在 `show` 里看到来源）：状态源里的水位日期、case.json 的窗口起点、记录的最早日期。
`end` 取 case.json 窗口终点；没有就取当前记录里最大的 `indexed`（归一化到订阅时区当日 23:59:59）。
窗口语义是**左闭右开** `[start, end)`，判定用 `published`（区分 new / late_index）与 `indexed`（区分是否本窗口被抓到）两条线。跨窗边界与延迟入库的补回写在 `coverage_notes`，不靠"窗口大概齐"。

### 6.4 每个 work 一个 op

| op | 含义 | 机械触发条件（`auto_op`） | 提醒默认 |
|---|---|---|---|
| `new` | 本窗口新出现且出版在窗口内 | 不在已见集 且 `published ∈ [start,end)` | 提醒 |
| `update` | 已见 work 的版本/venue/DOI/勘误变化，或组内出现新版本 | 组内版本链变化 或 已见但字段变 | 提醒（合并进一条） |
| `retract` | 撤稿/更正声明 | 撤稿源命中 或 `type` 含 retraction 或 `update-to` 指向 retraction | 提醒（最高优先） |
| `late_index` | 出版早于窗口、本窗口才入库 | 不在已见集 且 `published < start` 且 `indexed ∈ [start,end]` | **不提醒**，进简报补录区 |
| `seen` | 上次已见且无变化 | 在已见集 且无变化 | 不提醒 |
| `out_of_window` | 出版与入库都不在窗口内 | 其他 | 不提醒 |

`auto_op` 是脚本按字段算的初判；你要读记录确认，尤其：`type` 字段误标、撤稿声明本身被当成新论文、预印本与正式版被两个来源分别收录、日期只有年份精度导致边界歧义。

### 6.5 提醒抑制

提醒按 `op`+主题分组（同一天同来源的新发现合并成一条），抑制规则：重复副本、`seen`、`out_of_window`、`late_index`（改入补录）、相关性判为 `low` 且无方法学新意、同一 work 已在上一窗口提醒过（回执键去重）。每组给 `reason`，被抑制的也留一行 `suppress` 决策——**抑制要留痕，否则复核者无法区分"没发现"和"故意不推"**。

## 7. 输入输出契约

### 7.1 工作稿 `/app/work/draft.json`（Agent 亲自写，质量主体）

完整 schema 与字段字典见 `references/work-contract.md`。最小形态：

```json
{
  "subscription": {"query": "…", "sources": ["S1", "S2"], "timezone": "UTC", "cadence": "weekly"},
  "window": {"start": "2024-03-01", "end": "2024-04-01", "timezone": "UTC",
             "basis": "watermark from S9 import_state + case.json window_end"},
  "dedup_rules": {"keys": ["doi", "arxiv", "title_fp"], "normalization": "…"},
  "decisions": [
    {"work_key": "doi:10.1000/xyz", "op": "new", "relevance": "high",
     "why": "直接研究该问题的对照实验，样本量与方法匹配订阅意图",
     "evidence": {"source_id": "S1", "locator": "S1#r12.title",
                  "quote": "Exact title text as it appears in the record"},
     "alert": true, "alert_group": "G1", "suppress_reason": ""}
  ],
  "alert_groups": [{"group_id": "G1", "title": "本周新增", "members": ["doi:10.1000/xyz"], "delivery": "digest"}],
  "coverage_notes": ["S2 只覆盖 2024-03 之后，窗口前段由 S1 支撑"],
  "misses": ["S3 返回 429 无 payload，本窗口该来源缺失"],
  "uncertainty": ["两条记录仅年份精度，边界归属存疑"],
  "status_note": "已覆盖 2/3 来源，S3 缺失已记录"
}
```

硬规则：`decisions` 必须覆盖 `show` 列出的**每一个 work_key**；`evidence.quote` 必须能在该 locator 指向的记录里逐字找到；`op`/`relevance` 用枚举值；不确定的写进 `uncertainty` 而不是猜。

### 7.2 产物（都在 `/app/output`）

| 文件 | 内容 | 复核者拿它做什么 |
|---|---|---|
| `watch_brief.md` | 订阅配置、窗口与水位、来源覆盖表、新增区、版本更新区、撤稿区、补录区、抑制说明、遗漏与不确定、复算步骤 | 人 5 分钟看懂"这周该看什么、为什么" |
| `candidates.csv` | 每行一个 work：`work_key, op, title, doi, arxiv_id, venue, published, indexed, version, sources, n_records, relevance, alert, alert_group, evidence_locator, evidence_quote, why` | 排序/筛选结果，可直接进表格工具 |
| `decision_trail.jsonl` | 每条决策一行：op、判据、before/after、locator、quote、抑制理由、时间戳 | 逐条回放"为什么算新/为什么压住" |
| `result.json` | 契约键全量回填 + 信封字段 + `counts` 对账 + `fingerprints` | 机器读；`counts` 恒等式自证完整 |

`counts` 恒等式（`check`/`selfcheck` 会验）：

```
records_total − works_total = duplicate_records
works_total = new + update + retract + late_index + seen + out_of_window
alerted = Σ alert_groups.members （≤ new + update + retract）
```

## 8. 边界与限制

- **不联网、不补数**：来源缺失就写"该来源本窗口缺失"，不用别处数据填。绝不虚构 DOI、作者、期刊、日期。
- **只做元数据层判断**：相关性依据限于标题/摘要/venue/日期等记录字段；摘要缺失时明确写"仅标题可判，相关性置信度低"。
- **精度不升级**：`2024-03` 不被当成 `2024-03-01`；年份精度跨窗口的条目进 `uncertainty`。
- **时区**：默认按 case.json 声明的时区（无则 UTC），全部日期先折算再切日；不混用来源本地时区。
- **提醒不是结论**：简报只陈述"这条是新出现的记录及其字段"，不做科学判断。
- **单案例单窗口**：一次运行复算一个窗口。多窗口连跑靠外部调度重复调用，`fingerprints` 保证同输入重跑幂等（不产生二次推送）。

## 9. 失败处理与降级

| 情况 | 处置 | 结果 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 记 `errors`，case_id 用目录名兜底，契约键为空集也照写合法 result.json | `input_error` 或 `partial` |
| 无任何可识别记录 | 三件产物仍生成（空表 + 说明），简报写明"未发现可用记录" | `insufficient_evidence` |
| 某来源返回 429/空 payload/改版 | 该来源标 `status=failed/empty`，进 `degradations` + `misses`，其他来源照常 | `partial` |
| 记录缺 DOI | 退 arXiv 号再退标题指纹；键里体现 `title:`，简报标注"仅标题指纹可去重" | `partial` |
| 记录缺日期 | 不参与窗口判定，进 `uncertainty`，`op` 由你判断并说明 | `partial` |
| draft 缺失/坏 JSON/超时未写 | `build` 用 `auto_op` 生成降级交付：三件产物齐全、契约全键回填、`status=partial`、`degradations` 列明"未复核"、每条 `relevance=unreviewed`、`why` 标注为机械初判 | `partial`，退出码 0 |
| 单条决策引用了不存在的 work_key 或 quote 找不到 | `check` 报 `FIX [...]`；`build` 不中断，该条降级为 `unverified` 并在轨迹里留痕 | `partial` |
| 任何未捕获异常 | 顶层捕获，重写 partial result.json，stderr 打摘要 | 退出码 0 |

`build` 永远 finalize：先写 partial，再写产物，最后写终态 result.json；三步都包在 try 里，任一步失败不会让 `/app/output` 空着。

## 10. 自查清单（交付前）

1. `result.json` 的 `runtime.unfilled_contract` 为 `none`；每个契约键都能在产物里找到对应内容。
2. `counts` 三条恒等式成立（`selfcheck` 会打印 PASS/FAIL）。
3. 抽 3 条决策跑 `python3 scripts/main.py check`，看 `quote_hit_rate=1.0`；没有一条 `evidence.quote` 是改写来的。
4. 每个来源都在 `watch_brief.md` 的覆盖表里有一行（`records / in_window / failed`），失败来源写清原因。
5. 有 `retract` 决策时，`before` 与撤稿依据都在轨迹里；有 `update` 决策时，`before→after` 的字段差异明确（不是"感觉更新了"）。
6. 抑制项数量与 `suppress_reason` 数量一致；`alerted` 不为 0 也不刷屏（同主题同窗一般 1–3 组）。
7. 重跑一次 `build`：`fingerprints.decisions` 不变，`changes` 里出现 `rerun_same_input`。

## 11. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py init --input ./demo/input --output ./demo/output --work ./demo/work
python3 scripts/main.py show --input ./demo/input --work ./demo/work --work-key doi:10.1000/xyz
# Agent 读 show 输出 → 写 ./demo/work/draft.json
python3 scripts/main.py check --input ./demo/input --work ./demo/work
python3 scripts/main.py build --input ./demo/input --output ./demo/output --work ./demo/work
```

示意输出（示例）：`status=partial records=7 works=5 new=1 update=1 retract=1 late_index=1 seen=1 duplicates=2 alerted=3 contract=8/8`。
含义：7 条原始记录合并成 5 个 work（2 条重复副本被合并），窗口内 1 条新增、1 条预印本转正式版更新、1 条撤稿、1 条延迟入库旧文（不提醒）、1 条已见无变化；3 条进入 1–3 个提醒组；契约 8 个键全部回填。

## 12. 文件与维护

```
SKILL.md                        本文件（用途/主路径/契约/方法/边界/降级/自查）
scripts/main.py                 五个子命令入口与编排（init / show / build / selfcheck）
scripts/core.py                 记录抽取、归一化、去重合并、窗口计算、op 机械判定
scripts/desk.py                 输入发现、决策合并、机械校验（check）、提示组装、契约回填
scripts/render.py               简报 / 候选表 / 决策轨迹的确定性渲染
references/tracking-rules.md    时间轴规则、去重键规则、op 判定矩阵、来源适配表、提醒抑制、计数恒等式
references/work-contract.md     draft schema、字段字典、locator 规范、result 信封、契约回填映射
```

四个脚本无第三方依赖，全部只用标准库；入口永远是 `scripts/main.py`，其余模块由它导入，不单独调用。总代码量约 77KB，正常运行一次单案例消耗 < 1 秒、0 次模型调用。

版本 1.0.0。维护方式：新增来源类型 → 在 `core.py` 的 `SRC_HINTS` 加字段别名，并在 `tracking-rules.md` 的来源适配表登记；新增 op 类型 → 同时改 `OPS`、`tracking-rules.md` 判定矩阵与 `check` 的枚举校验（三处必须一致）。
