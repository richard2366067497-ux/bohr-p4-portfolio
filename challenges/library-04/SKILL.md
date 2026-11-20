---
name: kb-library-docket
description: 把科研知识库存成可复核的问答卷宗：先登记每个文件（哈希/类型/权限/元数据）、判定重复副本与版本家族，再对每个问题立案、逐争点举证（exhibit 带 doc_id+version+页/段 locator+逐字引文）、登记反证、给出五档裁决与缺证说明，输出检索范围、修复操作记录与 result.json（原样回填 output_contract）。用于 library/knowledge-base 整理、版本关系维护与带来源引用问答类 workorder。
version: 1.0.0
---

# 科研知识库整理与带引用问答：问答卷宗（Agent 主答 + 脚本辅助 + 兜底必成）

本 Skill 把"整理文件、也保留版本关系"和"带来源引用的问答"合成一条主线：**资料登记（谁是谁、哪版是哪版）→ 问题立案（拆争点）→ 举证（逐字引文 + locator）→ 反证 → 裁决 → 缺证与检索范围 → 修复操作记录**。

## 0. 先跑这五条（主路径，评审 Harness 按此执行）

```bash
python3 -B scripts/main.py init       # 扫输入：文件登记+哈希+抽取+重复/版本家族+问题清单，先落合法 partial result.json
python3 -B scripts/main.py show       # 打印带 locator 的登记表/原文/候选证据（--doc / --query / --emit / --template）
#   ↓ 评审 Agent 亲自读材料，写工作稿 /app/work/draft.json（可用 show --template 生成骨架）
python3 -B scripts/main.py check      # 机械校验：契约字段、quote 逐字命中、locator 对位、exhibit 守恒、裁决有据、覆盖数
python3 -B scripts/main.py build      # 由工作稿生成卷宗+登记表+版本证人+report.md+最终 result.json（无条件 finalize）
python3 -B scripts/main.py selfcheck  # 复检产物（可选，但建议跑）
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
`init` 只做确定性的登记与切分，`show` 只做定位与候选召回；"这段材料支持哪句话""哪一版才作数""证据够不够"必须由你在 `draft.json` 里写。`build` 的兜底是"完整但降级"（status=partial + degradations），不是答案。

## 1. 用途与适用条件

**适用**：输入是一个科研资料库（多文件、多格式、含重复副本与历史版本、可能带一份管理性版本说明/README），任务是"整理资料 + 维护版本关系 + 回答若干带来源引用的问题"。

**典型触发**：`case.json` 里有 `questions`/`queries`/`searches` 或 `task_instruction` 要求"整理/盘点/去重/版本/引用/出处"；材料目录里出现 `library/`、`files/`、`artifacts/`、`docs/`。

**不适用**：开放网络检索（本 Skill 不联网）、只做单文档摘要、只做文献综述写作、需要 Zotero/数据库账号的在线同步。这些情况请按结果说明"超出范围"，不要伪装完成。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `output_contract`、`task_instruction`）+ `/input/task.md` + 材料文件 |
| 工作目录 | `/app/work`（`index.json`、`draft.json`、`check_report.json`） |
| 产物目录 | `/app/output`（`result.json` 及卷宗产物） |
| 路径覆盖 | `--input/--output/--work` 或环境变量 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK`；不依赖 CWD（脚本按 `Path(__file__)` 定位） |
| 依赖 | 仅 Python 3 标准库；PDF 优先 `pdftotext`（若存在），否则内置 zlib 流解析；无网络 |
| 退出码 | 恒为 0（任何异常都写进 `errors` 并保留合法 `result.json`） |
| 预算 | 64 次模型请求 / 900 秒 / 单次 16384 token：检索、切分、哈希、校验、渲染交脚本，模型只做判断与写作 |

`result.json` 必须**原样回填** `output_contract` 的每个字段：键名不改、键不丢、缺值用 `null`/`[]`；另带信封字段 `case_id`、`status`(ok|partial|failed)、`sources`、`errors`、`degradations`、`uncertainty`、`changes`、`runtime`。

## 3. 输入发现（按语义识别，不假设键名）

`init` 依次尝试：

1. `case.json`（找不到则任意 `*.json`）；`case_id` 候选键：`case_id`/`id`/`case`/`task_id`；契约候选键：`output_contract`/`contract`/`output_spec`/`deliverables`；指令候选键：`task_instruction`/`instruction`/`prompt`/`task`。
2. 问题候选键：`questions`/`queries`/`qa`/`questions_list`/`searches`/`asks`（元素可为字符串或含 `question`/`q`/`text`/`query` 的对象）。若无结构化问题，从 `task_instruction` 与 `task.md` 中抽取带问号的句子作**派生问题**，在 `degradations` 标注 `derived_questions`。
3. 材料：递归扫 `/input/**`，跳过 `case.json`、`task.md`、脚本自身与明显的工作稿；按**扩展名 + 魔数**识别（`%PDF`→pdf、`PK`+`word/`→docx、`PK`+`xl/`→xlsx、`PK`+`ppt/`→pptx、其余按文本多编码探测），不靠文件名猜内容。
4. 材料根候选：`library_root`/`library`/`files`/`documents`/`materials` → `/input/library`、`/input/files`、`/input/artifacts` → 兜底全树。回落动作写进 `degradations`。

## 4. 主流程：卷宗六步（你来做判断）

### 4.1 立案：问题 → 争点
每个问题拆 1–5 个**可判定**争点（issue）：一个争点只问一件事，能被 1–3 条引文支持或推翻。事实型拆"事实+数值"；比较型拆"各自取值+可比性"；溯源型（哪一版）拆"版本身份+版本差异"；存在性型拆"是否有依据+依据在哪"。

### 4.2 举证：exhibit 登记
每条 exhibit 必须给：`exhibit_id`（E1…，全库唯一）、`doc_id`、`version`（该 doc 在登记表里的版本号）、`locator`（`show` 打印的形式，如 `p3#para7`、`t1#row5`、`sl2#para3`）、`quote`（**逐字复制**，不改写、不翻译、不拼接）、`kind`（fact|number|method|conclusion|metadata|version_note）、`polarity`（support|counter）。

`show --query "关键词" --emit` 直接打印现成 exhibit JSON（引文是该段落中命中关键词的原文句子），可粘贴后改 `polarity`/`kind`；`quote` 仍须逐字保留。

### 4.3 反证：counter-exhibit
与该争点结论相反、或来自另一版本的相反陈述，必须登记为 `polarity: "counter"` 并挂在**同一争点**下。没登记反证而事实上有冲突，视为遗漏（`check` 会用跨文档相反数值对比提示你）。

### 4.4 裁决：五档枚举
| verdict | 含义 | 硬性条件 |
|---|---|---|
| `supported` | 证据支持 | ≥1 positive exhibit；若存在 counter 则必须给出取舍理由，否则改判 `contradicted_with_reason` |
| `contradicted` | 证据推翻该命题 | ≥1 counter exhibit，且理由指向该反证（命题写“X 为 40 例”而原文写 52 例即属此类） |
| `contradicted_with_reason` | 有不一致但有理由采用其中一方 | counter + `reasoning` 明确取舍（版本更新/条件不同/口径不同） |
| `insufficient` | 现有材料不足以判定 | 必填 `missing_evidence`（缺哪类证据）+ `search_scope`（查了哪些文件/关键词/同义词） |
| `out_of_scope` | 问题超出该知识库范围 | 同 insufficient 的两项，并说明"本库不含该主题" |

裁决只能引用**已登记**的 exhibit；引用不存在的编号即 `check` 报 `exhibit_undefined`。

**`issue_text` 必须写成一句可判定的命题**，裁决针对该命题而非问题本身：问“两版是否一致”时，命题写“v1 与 v2 的 sample size 不一致（v1=40，v2=52）”，裁决 `supported`；不要写成“是否一致”再判 `contradicted`。

`insufficient` 时建议把“检索到的最接近证据”登记在 `positive_exhibits`（用来说明材料覆盖了什么、还缺什么），否则评审无法确认你真的查过。`conflicts` 为空是合法结论（未发现相反陈述），不必凑条目。

### 4.5 缺证与检索范围
`search_scope[qid] = {files:[...], keywords:[...], synonyms:[...], chunks_scanned:N, not_found_note:"..."}`。"没有依据"的答案必须写成"缺什么证据 + 在什么范围没找到"，不能只写"未找到"。

### 4.6 版本证人
同一资料存在多版本时，逐版本记录它主张了什么（`field_or_claim` + `statement` + `locator` + `exhibit_id`），并列出 `conflicts_between_versions`。回答"哪一版怎么说"必须带 `version`，不允许把 v1 的数值安到 v2 上。

### 4.7 资料整理与修复操作
`library.documents` 给每个文件定 `role`（authoritative|superseded|duplicate|supplementary|unreadable|unrelated）、`version`、`version_rank`、`metadata`；`library.duplicates` 给保留/剔除及依据（哈希一致或文本相似度）；`library.repair_actions` 记录可执行的整理动作（`op` 取 rename|move|dedupe|tag|relink|flag|quarantine，含 `target`、`to`、`reason`、`evidence`），使他人能照记录复跑。

## 5. 工作稿 `draft.json`（唯一工作稿，你写）

先用 `show --template` 生成骨架（doc_id、family、版本候选、问题已预填），只补判断字段。

```json
{"case_id":"...",
 "library":{"documents":[{"doc_id":"D1","family_id":"F1","version":"v1","version_rank":1,
     "role":"superseded","title":"...","metadata":{"authors":"","year":"","doi":"","venue":""},"notes":""}],
   "families":[{"family_id":"F1","canonical_doc":"D2","members":["D1","D2"],"basis":"文件名 _v2 + 文本相似度 0.97"}],
   "duplicates":[{"keep":"D2","drop":["D4"],"basis":"sha256 相同"}],
   "repair_actions":[{"action_id":"A1","op":"dedupe","target":"D4","to":"","reason":"与 D2 字节一致","evidence":["E7"]}]},
 "questions":[{"qid":"Q1","question":"...","answer_draft":"逐句带 [E#] 的答案",
   "issues":[{"issue_id":"Q1-I1","issue_text":"...","verdict":"supported",
     "positive_exhibits":["E1"],"counter_exhibits":[],"missing_evidence":"","reasoning":"..."}]}],
 "exhibits":[{"exhibit_id":"E1","doc_id":"D1","version":"v1","locator":"p2#para5",
   "page_printed":"12","page_physical":"2","section":"Methods","quote":"逐字引文",
   "kind":"number","polarity":"support"}],
 "version_witness":[{"family_id":"F1","versions":[{"doc_id":"D1","version":"v1",
   "claims":[{"field_or_claim":"sample_size","statement":"n=40","locator":"p2#para5","exhibit_id":"E1"}]}],
   "conflicts_between_versions":[{"claim":"sample_size","v_a":{"doc_id":"D1","statement":"n=40"},
   "v_b":{"doc_id":"D2","statement":"n=52"},"likely_cause":"v2 补做样本"}]}],
 "search_scope":{"Q1":{"files":["D1","D2"],"keywords":["sample size"],"synonyms":["n","例数"],"chunks_scanned":24,"not_found_note":""}},
 "conflicts":[{"conflict_id":"X1","topic":"...","side_a":{"doc_id":"D1","exhibit_id":"E1","statement":"..."},
   "side_b":{"doc_id":"D2","exhibit_id":"E2","statement":"..."},"likely_cause":"version|condition|method|unknown",
   "handling":"不取平均，按版本分层报告"}],
 "limitations":["..."],"uncertainty":["..."]}
```

字段可省（`page_printed`/`section`/`metadata.*` 等），但 `exhibits[].{doc_id,locator,quote}`、`issues[].{verdict}`、`search_scope` 在 `insufficient`/`out_of_scope` 时不可省。完整字段字典见 `references/draft-schema.md`。

## 6. 产物与 `result.json` 契约

| 文件（`/app/output`） | 内容 |
|---|---|
| `result.json` | `output_contract` 全字段回填 + 信封（`case_id/status/sources/errors/degradations/uncertainty/changes/runtime`） |
| `report.md` | 主产物：盘点（类型/元数据/目录层级/重复/版本差异/权限与来源六维）、版本家族、逐问题卷宗、覆盖统计、降级与复跑步骤 |
| `library_index.json` / `library_index.csv` | 文件登记：doc_id、路径、类型、字节、sha256、可读性、权限位、块数、段数、family、version、role、元数据提示 |
| `exhibits/exhibit_register.jsonl` | 证据登记册：每条含 doc_id/version/locator/quote/kind/polarity/核对状态 |
| `dockets/<QID>/verdict.md` | 单问题卷宗：答案、争点裁决表、支持/反证引文、缺证与检索范围 |
| `version_witness.json` | 版本证人表：各版主张 + 版本间冲突 |
| `conflicts.json` | 跨文档/跨版本相反陈述（双方 exhibit + 可能原因，不取平均） |
| `repair_log.json` | 整理动作与恢复记录（可逆性、依据、执行序） |
| `search_scope.json` | 每题检索范围与缺证说明 |

契约字段按语义映射：`index|inventory|manifest|library|file_list|catalog`→登记表；`duplicate|dedup`→重复组；`version|revision|history|supersede|lineage`→版本家族/证人；`metadata`→元数据表；`permission|access|source|provenance`→权限与来源；`answer|qa|question|finding|result`→问答卷宗；`evidence|quote|citation|exhibit`→证据登记；`conflict`→冲突；`not_found|missing|gap|unsupported`→缺证；`skip|fail|error|recover|repair|action|log`→整理与恢复记录；`coverage|stat|count|summary_metric`→覆盖统计；`summary|report|narrative`→report 摘要；`method|repro|procedure`→方法说明。类型冲突时按契约声明强制（list/dict/str），并在 `errors` 记 `contract_type_coerced`。

## 7. `check` 错误码 → 修法

| 码 | 含义 | 修法 |
|---|---|---|
| `no_draft` | 无 draft.json | `show --template` 生成骨架后填写 |
| `draft_json_invalid` | JSON 坏 | 修 JSON（去掉尾逗号/注释） |
| `empty_draft_sections` | 既无 exhibits 也无 questions | 至少产出一个问题的争点 |
| `case_json_repaired`（init） | case.json 残缺，脚本救回首个 JSON 对象 | 核对回填的契约键是否完整 |
| `no_materials`（build） | 输入目录无可用材料 | 说明库为空，不编造清单 |
| `contract_type_coerced`（build） | 回填类型与契约声明不一致 | 已按声明强制转换，检查内容是否走错字段 |
| `exhibit_undefined` | 裁决/冲突/版本证人引用了未登记 exhibit | 先在 `exhibits` 登记，再引用 |
| `exhibit_duplicate_id` | exhibit_id 重复 | 改唯一编号 |
| `quote_not_found` | 引文不逐字存在 | 从 `show --doc`/`--emit` 复制 |
| `locator_mismatch` | 该段没有这句引文 | 改成报错给出的真实 locator |
| `locator_missing` | 无 locator | 补 `show` 打印的定位 |
| `version_mismatch` | 版本与登记表不一致 | 对齐登记表 |
| `doc_unknown` | 引用了不存在的 doc_id | 用登记表编号 |
| `verdict_invalid` | 裁决枚举外 | supported/contradicted/contradicted_with_reason/insufficient/out_of_scope |
| `supported_without_evidence` / `contradicted_without_counter` | 裁决与证据不配 | 补 exhibit 或改判 |
| `counter_ignored` | 有反证却判 supported | 改 `contradicted_with_reason` + reasoning |
| `insufficient_no_scope` | 缺证缺检索范围 | 补 `missing_evidence` + `search_scope[qid]` |
| `orphan_exhibit` | 登记了但没被任何地方引用 | 引用或删除（提示级） |
| `dedupe_unsupported` | 去重缺乏依据 | 按哈希/相似度改正 |
| `unaddressed_duplicate` | 存在重复组未处置 | 在 `duplicates` 里给 keep/drop |
| `unreadable_unflagged` | 不可读文件未说明 | 标 `role: unreadable` |
| `number_unanchored` | 数值无引文支撑 | 补引文或改数值 |
| `question_missing` | 输入问题未在 draft 出现 | 补 qid |
| `contract_key_missing` | 契约字段未回填 | 看 `unfilled contract` |

`check` 不修改你的稿子，只打印 `FIX [...]` 列表与计数；按行改完再跑一次。

## 8. 异常与降级（一律 exit 0）

| 情况 | 处置 |
|---|---|
| 输入目录为空 / 无 case.json | 写合法 `result.json`（契约字段全给空值，`status=partial`），`errors` 记 `input_missing` |
| case.json 坏 JSON | 记 `case_json_invalid`，仍按空契约出结果，`status=partial` |
| PDF 扫描件无文本层 | 该 doc `role=unreadable`、`degradations` 记 `no_text_layer`，**不猜内容**；相关问题判 `insufficient` 并写缺"可读文本层/OCR" |
| 权限不足/读失败 | `readable=false` + `permission_denied` 降级，列入 `repair_actions` 的 `flag`/`quarantine` |
| 无 `pdftotext` | 内置 zlib 解析兜底，locator 为 `s1..sN` 块号并在降级里说明"页号不权威" |
| 重复副本 | 按 sha256/相似度入 `duplicates`，保留权威版，剔除项只记录不动原文件 |
| 版本冲突 | 入 `version_witness.conflicts_between_versions` 与 `conflicts.json`，分层报告 |
| 材料互相矛盾 | 双方 exhibit 都登记，裁决 `contradicted_with_reason` 或 `insufficient`，不取平均 |
| draft 缺失 / 不完整 | `build` 仍出完整最小交付：登记表/版本家族/修复记录（真实数据）+ 每题 `insufficient` 卷宗 + `status=partial` + `degradations` 列缺口 |
| 契约字段无对应内容 | 回填空值并在 `degradations`/`pending_human` 说明，不编造 |

## 9. 边界与限制

- 只处理 `/input` 内材料；不联网、不连 Zotero/数据库。
- 文本层抽取依赖 PDF 结构；无文本层 = 无内容可引，只能报缺。
- 版本号最终由你判断：脚本给"哈希相同/文本相似/文件名版本标记/管理性说明提及"四类线索，不替你定权威版。
- 表格类 locator 到行（`t1#row12`），不保证到列；引用表格数值时把关键短语一起抄进 `quote`。
- 单一案例的结论不外推到其他知识库；`metadata` 提示是启发式（标题/年份/DOI 正则），以原文为准。

## 10. 自查清单（交付前）

1. `build` 输出 `unfilled contract: none`；`result.json` 可解析且 `case_id` 与输入一致。
2. 每个 `quote` 都能在该 doc 里逐字找到（`check` 的 `quote_pass_rate` = 1.0）；`locator_mismatch`=0。
3. 每条裁决都有 exhibit；`supported` 无未处置反证；`insufficient` 都有检索范围。
4. 六维齐全：文件类型、元数据字段、目录层级、重复文件、版本差异、权限与来源。
5. 重复组都已处置；不可读文件都已标注；版本相关答案都带 `version`。
6. 答案中每个数值都能落到被引引文（`number_unanchored`=0）。
7. 换人复跑：`init → show --query → check` 能复现同一条引文与裁决。

## 11. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py init  --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py show  --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py show  --query "sample size" --emit --work ./demo/work > cands.json
python3 -B scripts/main.py show  --template --work ./demo/work     # 生成 draft 骨架
# Agent 读材料、填 draft.json
python3 -B scripts/main.py check --work ./demo/work
python3 -B scripts/main.py build --input ./demo/input --output ./demo/output --work ./demo/work
```

示意输出（示例，非正式案例结果）：`status=partial docs=3 families=2 dup_groups=1 questions=3 exhibits=6 verdicts={supported:2,insufficient:1} quote_pass=1.0`，`report.md` 含 3 行登记 + 1 组版本家族 + 2 个可答问题与 1 个缺证问题（缺"可读文本层"）。

## 12. 文件与维护

```
SKILL.md                         本文件（用途/流程/契约/错误码/降级）
scripts/main.py                  CLI：init / show / check / build / selfcheck（编排与契约回填）
scripts/lib_index.py             发现、抽取、哈希、重复/版本家族、管理性版本说明解析、检索
scripts/lib_check.py             草稿校验（引文/locator/裁决/守恒/数值锚定）与产物渲染
scripts/lib_contract.py          output_contract 枚举/类型回填/兜底工作稿
references/workflow-rules.md     裁决判据、版本与去重规则、错误码表、降级表
references/draft-schema.md        draft.json 字段字典、exhibit 规范、契约映射表
references/example.md            一次完整走查（示例数据，非正式答案）
```

维护：材料格式新增 → 在 `lib_index.extract` 加分派；契约出现新字段 → 在 `lib_contract.CONTRACT_MAP` 加语义正则；改判据 → 同步 `references/workflow-rules.md` 与 `check` 的码表。版本 1.0.0。
