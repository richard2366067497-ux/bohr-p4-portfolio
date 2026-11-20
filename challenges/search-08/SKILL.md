---
name: systematic-screening-ledger
description: 把一批题录走完系统性文献检索的完整链路——检索协议 → 去重聚类 → 标题/摘要纳排 → 双评审独立判定 → 分歧仲裁 → 计数闭合审计，产出可被第三人逐条复核的流程台账（PRISMA 式）、判定卡（含理由码、criterion_id 与逐字证据定位）、仲裁卷宗与闭合审计，并原样回填 output_contract 生成 result.json。Use when asked to screen/deduplicate a bibliographic export against inclusion and exclusion criteria, to arbitrate two reviewers' disagreements, to build a PRISMA-style screening flow with traceable counts, or to audit whether a systematic review's record counts close.
version: 1.0.0
---

# 系统性文献检索与纳排筛选 · 流程台账 + 判定卡 + 仲裁卷宗 + 闭合审计

## 0. 60 秒上手：五命令主路径（先读这一节）

```bash
python3 scripts/main.py init       # 建立题录索引：解析 case.json / output_contract / task.md / materials，
                                   # 去重预聚类、抽取标准版本与已有评审标签，先写一份合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的题录、重复组、标准版本表、已有标签、异常记录
#   ↓ 评审 Agent 亲自读 show 的输出（必要时直接读 materials 原文），把判断写进 /app/work/draft.json
python3 scripts/main.py check      # 机械校验：契约键、理由码存在性、quote 逐字命中、覆盖率、恒等式
python3 scripts/main.py build      # 由工作稿生成 流程台账 / 判定卡 / 仲裁卷宗 / 闭合审计 + 最终 result.json
python3 scripts/main.py selfcheck  # 复检已落盘产物（可反复运行，不修改产物）
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> `init/show` 提供的是**原料与坐标**（哪条记录在第几行、title/abstract 原文、标准第几条、两位评审各自怎么标），
> 而不是结论。`build` 在缺少工作稿时只会产出一份**诚实降级**的完整骨架（全部 pending），
> 拿不到"逐条判定 + 仲裁 + 闭合"的实质分。

命令参数（都有默认值，Harness 直接跑即可）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | `/input` | 含 `case.json`、`task.md`、`materials/**` |
| `--output` | `/app/output` | 主产物与 `result.json` 落盘处 |
| `--work` | `/app/work` | 索引、检查报告与工作稿所在处 |
| `--draft` | 自动探测 | 显式指定工作稿路径 |

## 1. 用途与适用条件

**做什么**：给定一份有限题录快照（数据库导出/去重前的混合批），把它按下述五道关口走完，产出"每个数字都能被逐级对上、每条判定都能回到理由码与原文片段"的筛选包。

**适用**：系统综述 / 范围综述 / 指南证据更新的题录筛选阶段；两位标注者的独立判断与仲裁；对已有筛选流程做计数闭合审计。

**不适用（明确越界，必须在产物里说明）**：不做全文精读质量评价、不做数据提取与统计分析、不写论文正文、不做偏倚风险评估、不声称"完成全球检索"或"已完成人工复核"。本包只处理**输入快照内**的记录；未提供全文、未提供第二评审、未提供标准时，如实标注缺口，不补造文献、不虚构标签。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 入口 | `python3 scripts/main.py <init|show|check|build|selfcheck>` |
| 依赖 | 仅 Python 3 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve()` 定位） |
| 退出码 | **恒为 0**（含输入缺失、坏 JSON、无题录）；异常写入 `result.json` 的 `errors`/`degradations` |
| 第一落盘 | 任何实质处理前先写合法 partial `result.json`，结束时无条件覆盖为 final |
| 预算 | 64 次模型请求 / 900 秒 / 单响应 16384 token：确定性重活（解析、定位、比对、计数、渲染）交给脚本 |
| 产物目录 | `/app/output`；工作稿与索引在 `/app/work` |

## 3. 输入发现（语义识别，不硬编码键名）

1. 读 `/input/case.json`（或递归找 `*case*.json`）；坏 JSON 记 `errors` 后继续扫描，不中断。
2. 保留 `case_id`、`output_contract` 原样；再按语义取 `task_instruction` / `research_question` / `criteria` / `limits`。
3. 递归扫描 `materials/**`（以及 `/input` 根下其他文件），按**内容**而非文件名判角色：
   - **题录**：`.jsonl` / `.json` / `.csv`，每行含 title/abstract/doi/year 类字段；也接受纯文本题录块。
   - **纳排标准**：含"纳入 / 排除 / inclusion / exclusion / eligibility"标题或 `I1.` `E2.` 编号的文档，可能有多版本（v1/v2）。
   - **评审标签**：含 reviewer/标注者 + label/结论 两列的文件（半行以上带评审人即判为标签文件）。
   - **检索式/协议**：含"检索式 / search string / PubMed / 数据库"的文档。
4. PDF/图片/表格未解析的只登记路径，在 `uncertainty` 里列缺口，不猜内容。

## 4. 主流程：一条记录要走完的五道关口

| 关口 | 谁做 | 落在哪 | 判定不了怎么办 |
|---|---|---|---|
| ① 版本 | 脚本给 fingerprint，Agent 选版本 | `protocol.criteria_version` | 多版本并存 → `version_conflict`，旧判定带 `rejudged_from` |
| ② 去重 | 脚本给候选组，**Agent 定合并/分开** | `dedup_decisions[]` | 证据不足 → `decision=keep_separate` + 说明 |
| ③ 判定 | **Agent 逐条判** | `decisions[]`（label × phase × reviewer） | 摘要不足 → `label=pending` + `P-ABS` |
| ④ 仲裁 | 脚本列分歧，Agent 裁决 | `conflict_resolutions[]` | 裁不了 → `verdict=pending` + 未决原因 |
| ⑤ 闭合 | 脚本算恒等式 | `flow_ledger.md` / `audit_closure.json` | 差值非 0 → 台账里标红并给差距来源 |

**阶段（phase）**：`title_abstract` 为必做；`fulltext` 仅在材料真的给了全文/全文标注时才写（没有全文却写 fulltext 判定，会被 check 标为 `phase_unsupported`）。

## 5. 工作稿 `draft.json`（Agent 必须亲自写）

写到 `/app/work/draft.json`（也接受 `/app/work/plan.json`）。完整 schema 与字段字典见 `references/draft_schema.md`，最小形状：

```json
{
  "schema": "screening-draft/1",
  "protocol": {
    "criteria_version": "v2",
    "reviewers": ["A", "B"],
    "query_strings": [{"id": "Q1", "database": "PubMed", "query": "\"heart failure\" AND telemonitoring",
                       "fields": "tiab", "limits": "2015-2025; English", "searched_on": "2025-06-01",
                       "criterion_ids": ["I1", "E1"]}]
  },
  "dedup_decisions": [
    {"group_id": "D01", "decision": "merge", "representative": "R003",
     "evidence": "两条记录 DOI 相同 10.1000/xyz；标题差异仅为副标题与预印本标注"}
  ],
  "decisions": [
    {"record_id": "R004", "phase": "title_abstract", "reviewer": "A", "label": "exclude",
     "reason_code": "EX-DES", "criterion_id": "E2",
     "evidence_quote": "This narrative review summarises", "locator": "R004@abstract",
     "confidence": 0.86, "note": ""}
  ],
  "conflict_resolutions": [
    {"record_id": "R007", "type": "direction_conflict", "verdict": "include",
     "reason_code": "IN-DES", "basis_criterion_id": "I1",
     "basis_quote": "randomised controlled trial", "basis_locator": "R007@abstract",
     "rationale": "摘要明确为随机对照试验，符合 I1 的设计要求", "needs_human": false}
  ],
  "gaps": [{"item": "R020 摘要", "reason": "abstract 字段为空，只能待全文", "kind": "missing_abstract"}],
  "status_note": "一句话说明本轮做到哪、缺什么"
}
```

写入规则：

- **`evidence_quote` 必须是题录字段里的逐字片段**（可跨行，空白会被归一化后比对）。脚本会把它改写成带字符区间的规范 locator `R004@abstract[118:170]`，第三人可独立定位。命中失败 → 该卡标 `evidence_hit=false`、写入 `degradations: quote_miss` 与 `pending_human`、`status` 降为 partial（判定本身不被脚本篡改），**不允许改原文凑命中**。
- `criterion_id` 必须指向**当前版本**的标准条目（`show` 会列出 `I1/E1…`）；指向不存在或旧版本的条目会被 check 拦下。
- `reason_code` 只能取自 `references/reason_codes.json` 的字典（`IN-*` / `EX-*` / `P-*`），且必须与 `label` 同族。
- 一条记录一位评审一行；`reviewer` 用 `A`/`B`/`arbiter` 或真实标注者名。**同一记录同一评审重复写多行是错误**（check 报 `duplicate_card`）。
- 判不了就写 `pending` + 说明需要什么信息，绝不写一个看起来合理但没有依据的 include/exclude。

## 6. 纳排判据与理由码

标准表来自材料（`I1…/E1…`）；理由是**字典驱动**的，不允许自由文本造码：

| 族 | 码 | 含义 |
|---|---|---|
| IN | `IN-POP` `IN-INT` `IN-DES` `IN-OUT` `IN-CON` | 人群 / 干预暴露 / 设计 / 结局 / 情境 与问题一致 |
| EX | `EX-POP` `EX-INT` `EX-DES` `EX-OUT` `EX-LANG` `EX-DUP` `EX-DATE` `EX-SETTING` `EX-FULLTEXT` | 对应的排除理由（含语种、重复记录、时间、情境、全文不可得） |
| P | `P-ABS` `P-LANG` `P-CONFLICT` `P-VERSION` `P-NODRAFT` | 摘要不足 / 语种待定 / 分歧未决 / 版本变更待回溯 / 无工作稿的降级占位 |

完整字典（含中英释义与判据提示）见 `references/reason_codes.json`；`IN-*` 只允许配 `include`，`EX-*` 只允许配 `exclude`，`P-*` 只允许配 `pending`。

## 7. 双人独立判断、分歧类型与仲裁规则

1. **独立**：A、B 各自对同一条记录写一行 `decisions`，不得互看（本包不合并两人的判断，只比对）。
2. **分类**（脚本按证据机械分类，Agent 可覆盖）：
   - `direction_conflict`：一个 include、一个 exclude —— 最实质性，必须给仲裁结论。
   - `reason_conflict`：都排除但理由码不同 —— 影响排除理由分布，需定一个主码。
   - `version_conflict`：两行绑定的 `criteria_version` 不同 —— 必须先确定现行版本，再对旧判定输出 `rejudged_from`。
   - `boundary_conflict`：一方 pending 或证据不足（摘要空/仅题名）。
3. **仲裁规则**：裁决必须引用 **criterion 原文 id + 支持该裁决的逐字证据片段**；不得用"多数票"或"取平均"掩盖分歧。
4. **裁不了**：`verdict=pending` + `rationale` 写清缺什么（全文？语种确认？标准未覆盖该情形？），并进 `pending_human`。

## 8. 计数恒等式与闭合要求

`flow_ledger.md` 与 `audit_closure.json` 必须同时成立：

```
E1  identified − duplicates_removed            = screened
E2  screened                                    = included + excluded + pending
E3  conflicts_total                             = arbitrated + conflicts_open
E4  pending                                     = conflicts_open + awaiting_info
E5  decision_cards(study 去重后) ≥ screened      = 覆盖（每个 study 至少一张 title_abstract 卡）
```

每条恒等式输出 `left / right / diff / status`。`diff != 0` 时台账写明差值来源（例如"2 条记录未给判定，已计入 pending"），不得悄悄改数。

## 9. 产物与 `result.json`

| 文件 | 内容 | 复核方式 |
|---|---|---|
| `flow_ledger.md` | PRISMA 式流程台账：每级计数 + 依据文件/字段 + 恒等式表 + 排除理由分布 | 任何人可对着 `decision_cards.jsonl` 复算 |
| `decision_cards.jsonl` | 每记录×阶段×评审一行，含 label / reason_code / criterion_id / 逐字 quote / 规范 locator / 版本 | 逐行 grep 原文 |
| `arbitration_docket.md` | 每条分歧一页：双方标签与理由、分歧类型、证据对照、裁决与依据、未决原因 | 对照两张卡 |
| `audit_closure.json` | 恒等式、理由码使用统计、标准 fingerprint、异常记录清单、覆盖率 | 机器可读，可直接断言 |
| `result.json` | `output_contract` 全键回填 + 信封字段 | 见下 |

`result.json`：

- **原样回填 `output_contract` 的全部键**：键名不改、不删、不漏；语义可映射的填真实内容，无法映射的按声明类型填空值（`[]`/`null`/`{}`/`""`），并在 `contract_unmapped` 里列出。
- 信封：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`counts`、`sources`、`artifacts`（含字节数与 sha1）、`evidence_map`、`verification`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`assumptions`、`runtime`、`output_contract_echo`。

## 10. 边界情形与降级链

| 情形 | 处置 | 标记 |
|---|---|---|
| 无 `draft.json` | build 仍产四件套：全部 study 记为 `pending`，台账给 identified/duplicates/screened，恒等式照算 | `degradations: draft_missing`，`status=partial` |
| 工作稿部分记录 | 已写判定全部落卡，未覆盖记录 `P-NODRAFT` 占位，覆盖率写进 counts | `partial_coverage` |
| quote 未命中 | 该卡降为 `pending` + `P-CONFLICT`，记 `quote_miss` | 计入 `verification.quote_hit_rate` |
| 题录为空/找不到 | 四件套给空骨架 + 说明，`insufficient_evidence` | `records_missing` |
| 坏 JSON / 文件不可读 | 记 `errors`，其余文件继续 | 不中断 |
| 摘要为空 / 缺 DOI / 乱码 | 记录级 `flags`，判定可给 `P-ABS`，不因单条崩掉 | `anomalies[]` |
| 多版本标准 | 台账标出现行版本，旧判定 `rejudged_from` | `version_conflict` |
| 两位评审僵持 | `verdict=pending`，进 `pending_human`，不硬定 | `conflict_open` |
| 编号/记录重复 | 每人每记录只留一张卡，多余报 `duplicate_card` | check 拦截 |

## 11. 自查

```bash
python3 scripts/main.py check      # 工作稿机械校验（不落主产物）
python3 scripts/main.py selfcheck  # 已落盘产物复检
```

`check` 关注：记录可解析、label/phase/reviewer 合法、reason_code 在字典内并与 label 同族、criterion_id 在当前版本存在、quote 逐字命中、覆盖率、重复卡、仲裁条目是否引用了判据、恒等式是否成立。
`selfcheck` 关注：`result.json` 是否覆盖 `output_contract` 全部键、四件套是否非空、`decision_cards.jsonl` 是否可逐行解析、台账恒等式 diff 是否为 0、`status` 与降级是否自洽。

取向：**宁可 partial 且诚实，不要 ok 而不可核验**。

## 12. 最小调用示例（示例，非任何正式案例的结果）

```bash
mkdir -p /tmp/demo/materials
cat > /tmp/demo/case.json <<'J'
{"case_id": "DEMO-1", "task_instruction": "screen records",
 "output_contract": {"screening_records": "array", "flow_counts": "object", "evidence": "array"}}
J
python3 scripts/main.py init  --input /tmp/demo --output /tmp/demo/out --work /tmp/demo/work
python3 scripts/main.py show  --input /tmp/demo --output /tmp/demo/out --work /tmp/demo/work
# 写 /tmp/demo/work/draft.json（2 条 include、1 条 exclude、1 条 pending）
python3 scripts/main.py check --input /tmp/demo --output /tmp/demo/out --work /tmp/demo/work
python3 scripts/main.py build --input /tmp/demo --output /tmp/demo/out --work /tmp/demo/work
python3 scripts/main.py selfcheck --input /tmp/demo --output /tmp/demo/out --work /tmp/demo/work
```

示意输出（**示例，自造夹具**）：`counts = {identified: 4, duplicates_removed: 1, screened: 3, included: 2, excluded: 0, pending: 1}`，`status = partial`（1 条摘要不足）。数字仅演示接口形状。

## 13. 文件清单与维护

```
SKILL.md                     元数据 + 本手册
scripts/main.py              五命令、输入发现与索引装配、show
scripts/ingest.py            题录/标准/标签解析、语义字段映射、去重预聚类、异常标记
scripts/screen.py            判定卡、去重裁决、冲突分类、最终标签、产物装配
scripts/report.py            台账/卷宗渲染、契约回填与类型对齐、降级 blank、自查
references/reason_codes.json 理由码字典、字段同义词、分歧类型、判据提示
references/draft_schema.md   draft.json 完整 schema、字段字典、反例
references/ledger_template.md 台账/卷宗模板与恒等式定义
```

- 版本 1.0.0。新增理由码、字段同义词只改 `references/reason_codes.json`，不动脚本。
- 改脚本后必跑 §11 两条命令 + 一次最小夹具回归（`init → 写 draft → check → build`）。
- 维护边界：本包只处理输入快照；不做联网检索、不做全文质量评价、不替代研究者做最终科学判断。
