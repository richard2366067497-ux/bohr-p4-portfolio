---
name: patent-search-dossier
description: 专利与技术文献检索 Skill：在有限授权来源内完成号码定位与主题检索，产出号码登记簿、案件档案（dossiers.md）、族图、法律状态来源表、许可闸门与边界日志；每条结论带来源种类、定位与查询日期，缺证据写 unknown，脚本兜底必出完整降级交付。
version: 1.0.0
---

# 专利与技术文献检索 · 案件档案（patent-search-dossier）

**一句话**：Agent 当检索员亲自读材料、写工作稿 `draft.json`；脚本负责索引、号码规范化、族/状态/许可的机械登记、证据逐字校验与成稿；脚本永远能交出一份最小但完整的档案。

适用：给定一批专利记录（著录项/影印件 OCR/合并页）、同族链接、对照技术文献与来源许可表，需要回答"这件专利保护什么、族里还有谁、现在什么状态、同主题还有谁在做、我有没有权展示"，并留下可复跑的检索与核验记录。
不适用：专利撰写、侵权判定、自由实施（FTO）结论、专利价值评估、法律意见；不绕过付费墙、不上传受限数据、不展示受限库原文。

## 0. 60 秒上手（五命令主路径，必须按序执行）

```bash
SK=${SKILL_DIR:-/skills/weekly-skill}          # 安装位置；本地自测可指向包根
python3 $SK/scripts/main.py init      # ① 建索引：解析 case.json/task.md，材料分诊、号码候选、族链接候选、许可候选；先写合法 partial result.json
python3 $SK/scripts/main.py show      # ② 打印带 locator 的原文与对象清单（号码表/族候选/状态行/许可行/文献行）
#   ③ 你（Agent）亲自读材料 → 写工作稿 /app/work/draft.json（§4）
python3 $SK/scripts/main.py check     # ④ 机械校验：契约键、号码规范化、状态三字段、引文逐字命中、许可分级、族口径、覆盖数
python3 $SK/scripts/main.py build     # ⑤ 由工作稿生成六件产物 + 最终 result.json（无条件 finalize，缺稿则兜底完整 partial）
python3 $SK/scripts/main.py selfcheck # ⑥ 复检：产物存在性/契约完整性/证据命中/确定性指纹
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
`build` 在没有 `draft.json` 时也会产出完整的最小档案（`status=partial`，`degradations` 逐条写明缺口），但这只值"完整但降级"的基础分：号码解析确认、族边证据、状态来源判定、许可分级、边界声明必须由你在工作稿里写。

参数：`--input/--output/--work`（默认 `/input`、`/app/output`、`/app/work`；也认 `INPUT_DIR`/`OUTPUT_DIR`/`WORK_DIR`）。默认路径不存在时自动回退到 `<cwd>/input`、`<cwd>/output`、`<cwd>/work`，因此本地拷一份最小输入即可直接跑。`show` 另有 `--id M2`、`--grep 权利要求`。

## 1. 一个案件必须回答的 5 件事

| # | 问题 | 产物落点 | 不允许的写法 |
|---|---|---|---|
| 1 | 这件专利保护什么？ | `dossiers.md` 著录项表 + `claims_versions[]` 逐字摘录 | 用自己的话概括权利要求当结论 |
| 2 | 它与同族其他成员什么关系？ | `family_graph.json`（edges + `link_type` + `evidence_locator`） | 把关键词命中的不同专利当同一族 |
| 3 | 现在是否有效？ | `status_provenance.csv`（`value`+`as_of`+`source_kind`+`needs_official_verification`） | 用转载页/摘要当登记依据；推断"已授权/已失效" |
| 4 | 同一主题还有谁在做？ | `technical_papers[]` + `candidates[]`（专利与技术文献分开计口径） | 专利文献与期刊文献混排成同一排序 |
| 5 | 我有没有权访问与展示？ | `license_gate.md`（绿/黄/红 + 可展示字段范围 + 降级方案） | 抓取需登录的商业库；展示受限库原文 |

判断做对不看查了多少库、抓了多少条，而看：结果是否只来自有授权的来源且标注库名/版本/查询日期；号码、同族与法律状态是否与材料登记对得上；过程能否被他人按记录复跑。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id`、`task_instruction`、`output_contract`，可选 `organizer_workorder`）+ `/input/task.md` + `/input/materials/**`（专利记录、影印件 OCR、WO 合并 OCR、同族链接、对照论文、来源许可表） |
| 工作区 | `/app/work`：`index.json`、`draft.json`、`draft.effective.json`、`check_report.json`、`self_check.json`、`run.log` |
| 产物 | `/app/output`：`result.json`（信封 + 契约回填）、`dossiers.md`（主产物，人可读）、`number_registry.json`、`family_graph.json`、`status_provenance.csv`、`license_gate.md`、`boundary_log.json`、`self_check.json` |
| 依赖 | Python 3.8+ 标准库；不联网；不依赖 CWD（`Path(__file__)` 定位脚本） |
| 退出码 | 恒 0；异常写入 `result.json.errors` / `degradations`，不抛栈给 Harness |
| 预算 | 64 次请求 / 900 秒 / 单次 16384 token；确定性重活全部交给脚本，模型只做理解与判断 |
| 幂等 | 同输入重复运行产物一致（`result.runtime` 与时间戳除外）；`selfcheck` 比对指纹 |

## 3. 输入发现与材料分诊

`init` 递归扫 `/input`（跳过 `case.json` 自身、隐藏文件与 `__pycache__`），按扩展名 + 魔数（`%PDF`、`PK`）识别格式，JSON 一律 `utf-8-sig` 读（防 BOM）。材料按**内容特征多标签打分**分诊，不依赖文件名：

| 角色 | 触发特征（示例） | 用途 |
|---|---|---|
`patent_record` | patent / claims / assignee / IPC / filing / 申请人 / 权利要求 | 著录项与权利要求来源 |
`facsimile_ocr` | UNITED STATES PATENT / Kind Code / OCR / 影印 / 页码粘连 | 权利要求版本与 OCR 边界 |
`family_link` | family / 同族 / continuation / divisional / priority claim / related | 族边候选 |
`license` | license / permission / 许可 / 保密 / green / red / 允许展示 | 许可闸门 |
`paper` | DOI / arXiv / abstract / et al / journal / 参考文献 | 技术文献 |

同一材料可有多角色；`show` 打印角色与得分，Agent 据此决定引用位置。材料缺失、坏 JSON、无文本层都分别进 `degradations`，不静默假装成功。

## 4. 工作稿 `draft.json`（Agent 唯一必写文件）

完整字段字典见 `references/field-dictionary.md`；骨架：

```jsonc
{
  "query": {"kind": "number|topic|both", "statement": "检索式/检索意图", "targets": ["US10123456B2"],
            "scope": ["目标专利", "同族", "法律状态", "权利要求", "技术文献", "授权边界"], "excluded": []},
  "number_decisions": [{"raw": "US 10,123,456 B2", "norm": "US10123456B2", "doc_type": "us_grant",
                        "parse_status": "parsed", "decision": "confirm|reject|ambiguous", "note": "…"}],
  "patent_objects":  [{"patent_id": "P1", "number_norm": "US10123456B2", "title": "…", "assignee": "…",
                       "filing_date": "…", "priority_date": "…", "ipc": ["…"],
                       "screening": "include|exclude", "why": "…",
                       "evidence": [{"source_id": "M1", "locator": "p2", "quote": "逐字原文"}]}],
  "field_extraction": [{"patent_id": "P1", "field": "filing_date", "value": "2016-03-11",
                        "source_id": "M1", "locator": "p2", "quote": "…"}],
  "family_edges":    [{"from": "P1", "to": "P2", "link_type": "observed|shared_priority|continuation|divisional",
                       "family_scope": "simple|extended", "evidence_locator": "M3/p1", "quote": "…",
                       "claim_scope_note": "仅陈述可见证据"}],
  "status_entries":  [{"patent_id": "P1", "value": "unknown|granted|pending|expired|abandoned|withdrawn|rejected|not_in_force",
                       "as_of": "2026-11-18", "source_kind": "official_register|observed_link|facsimile_ocr|aggregator",
                       "source_id": "M2", "locator": "p1", "needs_official_verification": true, "note": "…"}],
  "claims_versions": [{"patent_id": "P1", "version": "v1", "quote": "…", "locator": "M2/p3",
                       "ocr_boundary": "none|页码粘连/权利要求截断的具体说明", "scope_explained": false}],
  "technical_papers": [{"paper_id": "T1", "title": "…", "doi": "10.xxxx/xxxx", "year": 2019,
                        "relevance": "high|medium|low", "why_relevant": "…", "source_id": "M5", "locator": "p1", "quote": "…"}],
  "license_decisions": [{"source_id": "M6", "source_name": "…", "tier": "green|yellow|red",
                         "display_scope": "可展示字段", "degrade_plan": "降级后仍可做什么",
                         "excluded_from_output": true, "reason": "…"}],
  "boundaries": [{"type": "legal_status_unknown|family_not_exhaustive|ocr_merged_page|claim_scope_unexplained|patent_vs_paper_scope|license_restricted|metadata_missing|coverage_gap",
                  "item": "…", "detail": "…", "impact": "结论在什么范围内成立"}],
  "conflicts": [{"item": "…", "sources": ["M1/p2", "M3/p1"], "handling": "保留两值并标 needs_official_verification"}],
  "gaps": [{"item": "…", "why": "材料未提供", "needed_by": "对外交付前"}],
  "status_note": "整体完成度与未完成部分的自我说明"
}
```

写作纪律：`quote` 从 `show` 打印的原文逐字复制（含 OCR 噪声符号也算），**不得改写原文凑通过**；判断（是否同一族、相关性高低、许可分级、边界影响）必须写成你的结论并给依据；材料没有的一律 `unknown`/`null`，不推断。

## 5. 号码格式规范与解析规则

脚本确定性规范化（`number_registry.json` 保留 `raw → norm` 与命中规则链，可逐条复核）：

| 输入样式 | `norm` | `doc_type` | 关键规则 |
|---|---|---|---|
`US 10,123,456 B2` / `US10123456B2` | `US10123456B2` | us_grant | 去分隔符 → 国别前缀 → 尾部 kind code → 7–8 位序号 |
`US 2017/0123456 A1` | `US20170123456A1` | us_publication | 11 位且以 19/20 开头 → 年份 4 位 + 序号 7 位 |
`US 15/234,567` | `US15234567` | us_application | 含 `/` → 申请号（系列码 + 6 位序号） |
`WO 2018/123456 A1` / `WO2018123456` | `WO2018123456A1` | pct_publication | `WO` + 4 位年份 + 6–7 位序号 |
`EP 3 456 789 A1` / `CN 110123456 A` | `EP3456789A1` / `CN110123456A` | ep_publication / cn_application | 国别 + 序号（长度决定类型） |
`10,123,456`（无国别） | `US10123456`（推断） | us_grant | 规则标 `inferred_country:US`，`parse_status=ambiguous` |

- 公开号、申请号、授权号、优先权号**不得混用**：同一数字不同号码类型分别登记。
- 无法解析时保留原串、`parse_status=unparsed`，写进 `boundaries`（`metadata_missing`），不猜。
- `check` 会重算每个 `raw` 的规范化结果；`draft` 里的 `norm` 与脚本不一致 → 直接报错。

## 6. 同族归并口径

| 口径 | 判据 | 输出 |
|---|---|---|
`simple` | 同优先权（材料给出相同 priority 号/日期） | 可推定同一简单族 |
`extended` | 仅 observed 链接（续案/分案/指定国成员等可见记录） | 归为一组但**不推定权利要求等同** |
`not_exhaustive` | 任何情况都为 `true` | 族图每 work 显式声明"本族可能不完整" |

- 每条边必须有 `evidence_locator` + 逐字 `quote`；没有证据的边不许出现。
- 族内权利要求范围是否一致，只按可见证据陈述（`claim_scope_note`），不做等同推定。
- 关键词命中 ≠ 同族：号码不同的两件专利默认不同族，除非材料给出链接。

## 7. 法律状态来源分级与 `as_of` 纪律

| `source_kind` | 含义 | 允许的结论强度 |
|---|---|---|
`official_register` | 官方登记（材料中的官方登记页/官方抄录） | 可直接陈述，仍需 `as_of` |
`facsimile_ocr` | 影印件 OCR（可能缺页/粘连） | 仅作历史快照，必须 `needs_official_verification=true` |
`observed_link` | 观察到的链接页面/二手页面 | 仅作线索，不得当登记 |
`aggregator` | 聚合站/转载 | 仅作线索，`confidence=low` |

规则（脚本强制）：非 `official_register` 来源的状态值 `needs_official_verification` 必须为 `true`；材料没有官方状态时 `value=unknown`，**绝不推断"已授权/已失效"**；`as_of` 用 ISO 日期，写查询日或材料标注日；同一专利出现两个不同状态 → 进 `conflicts` 与 `boundaries`，不擅自二选一。

## 8. 许可闸门（绿/黄/红）

| 分级 | 判据 | 可做 | 降级方案 |
|---|---|---|---|
`green` | 材料明确允许检索与展示 | 引用原文、展示字段 | — |
`yellow` | 允许内部使用/有限展示 | 引用结论与字段名，引用片段 ≤ 材料允许长度 | 只给字段摘要 + 定位，不给长段原文 |
`red` | 需登录/受限/保密/未授权 | **不得抓取、不得展示原文** | 只记录"已排除 + 原因 + 需要的授权"，主结果不出现其文本 |

`license_gate.md` 必须逐源登记：库名、版本、查询日期、`tier`、可展示字段范围、留存期限（若材料给出）、降级方案。`check` 会验证 red 来源没有出现在 `patent_objects/claims_versions/technical_papers` 的引用里。

## 9. 边界声明与风险分级

`boundaries[]` 至少覆盖实际存在的类别，每类写清"结论在什么范围内成立"：

| type | 何时必须写 |
|---|---|
`legal_status_unknown` | 任一专利状态为 `unknown` |
`family_not_exhaustive` | 存在族边（观察到的族可能不完整） |
`ocr_merged_page` | 材料含影印件/合并页 OCR，摘录可能跨页或截断 |
`claim_scope_unexplained` | 只摘录了权利要求，未做范围解释（本题不做侵权/范围判断） |
`patent_vs_paper_scope` | 同时检索专利与技术文献（两者口径不同，不可混排同一排序） |
`license_restricted` | 存在 yellow/red 来源或字段被降级 |
`metadata_missing` / `coverage_gap` | 字段缺失 / 检索面未覆盖 |

风险分级：每条结论标证据强度（`official_register`+逐字命中 = 强；`observed_link`/聚合站/OCR 容错命中 = 弱）并给人工复核建议。

## 10. 输出契约：`result.json` 字段回填

`build` 原样回填 `output_contract` 的**每个键**（不改名、不漏键，缺值 `null`/`[]`），同时镜像到顶层，并附信封字段：

| 契约键语义（含中英关键词） | 回填内容 |
|---|---|
`number`/`公开号`/`专利号` | `number_registry` 列表 |
`family`/`族` | `family_graph`（nodes/edges/scope/not_exhaustive） |
`status`/`legal`/`法律状态` | `status_provenance` 列表 |
`claim`/`权利` | `claims_versions` 列表 |
`paper`/`literature`/`文献` | `technical_papers` 列表 |
`license`/`permission`/`许可`/`授权` | `license_gate` 对象 |
`boundary`/`遗漏`/`uncertain` | `boundary_log` 列表 |
`candidate`/`result`/`候选` | `candidates` 列表（含 include/exclude 与排序依据） |
`query`/`检索式` | `queries` 列表 |
`evidence`/`source`/`provenance`/`定位` | `evidence_map`（source_id + locator + quote + 命中状态） |
`coverage` | `coverage` 对象（8 个检索面命中/应有） |
`risk` | `risk_register` 列表 |
`summary`/`conclusion` | `summary` 字符串（只写在材料范围内的结论） |
其他未知键 | `null`（键保留），并在 `assumptions` 注明"契约键语义未识别" |

信封：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`skill{name,version}`、`deliverable{path,format,chars,sections}`、`sources[]`、`errors[]`、`degradations[]`、`assumptions[]`、`conflicts[]`、`gaps[]`、`counts{}`、`coverage{}`、`runtime{input_fingerprint,started_at,finished_at,elapsed_s,python,skill_version}`。

## 11. `check` 判什么（R1–R13）

| 编号 | 判据 | 级别 |
|---|---|---|
R1 | 检索意图与 `targets` 完备（number 查询的 target 必须能规范化） | error |
R2 | `norm` 与脚本规范化一致；`parse_status` 与被解析结果一致 | error |
R3 | `patent_objects` 的 `number_norm` 能在材料中定位到原始串（防编造号码） | error |
R4 | 每条引用 `quote` 逐字命中（OCR 容忍 ≥0.90 记 warning）；`locator` 与命中段一致 | error / warning |
R5 | `status_entries` 三字段纪律（`as_of` + `source_kind` + `needs_official_verification`）与来源分级一致 | error |
R6 | 状态值枚举合法；非官方来源不得给出确定状态 | error |
R7 | `family_edges` 的 `link_type`/`family_scope` 合法且有 `evidence_locator` | error |
R8 | `claims_versions` 有 `ocr_boundary` 声明（无边界写 `none`） | warning |
R9 | 材料含 `paper` 角色时 `technical_papers` 不得为空 | error |
R10 | `license_decisions` 覆盖所有 `license` 角色材料；red 来源未进入主结果引用 | error |
R11 | `boundaries` 覆盖实际存在的类别（§9 触发条件） | error |
R12 | 覆盖率 < 5/8 个检索面 | warning（并降 `status=partial`） |
R13 | 同一专利状态值冲突未登记 | error |

`check` 只报告不改稿；命中统计与错误清单写入 `work/check_report.json`，`build` 会重算同一套规则。没有工作稿时 `check` 会用索引兜底跑一遍并显式提示"不代表你已完成阅读与判断"。

## 12. 降级与失败处理

| 情况 | 处理 | 结果 |
|---|---|---|
`case.json` 缺失/坏 JSON | 递归搜 `case*.json`/`input*.json`；仍失败则记 `errors`，按材料继续 | 继续产出 |
`output_contract` 缺失 | 按 `task_instruction` 关键词给出默认键集 | 继续产出 |
材料缺失（无 `/input/materials`） | 仍写合法 `result.json` + 占位档案 | `status=partial`，`degradations` 写明 |
PDF 无文本层 | `pdftotext` → `pdf-text-tool` → PyMuPDF → pdfminer → 标准库粗解析；只降级该材料 | 该源标 `text_layer_missing` |
图片材料 | 不 OCR、不猜内容 | 写 `no_ocr` 进 `degradations` |
OCR 噪声/合并页 | 引文允许 ≥0.90 容错命中并标 `ocr_tolerant`；权利要求截断写 `ocr_boundary` | 主结果标注 |
状态冲突/字段缺失 | 保留多值 + `needs_official_verification`；缺失进 `gaps` | 不二选一 |
无工作稿/工作稿不完整 | 用索引兜底生成完整最小档案 | `status=partial`，`draft_source=fallback` |
任何未捕获异常 | `try/except` 包住每个命令，异常进 `errors` | 退出码 0 |

## 13. 自查清单（交付前逐条过）

- [ ] `result.json` 存在、`output_contract` 键一个不少，`case_id` 与输入一致。
- [ ] 六件产物齐全且非空：`dossiers.md`、`number_registry.json`、`family_graph.json`、`status_provenance.csv`、`license_gate.md`、`boundary_log.json`。
- [ ] 每个号码有 `raw→norm` 与规则链；无编造号码（R3 通过）。
- [ ] 每条结论有 `source_id` + `locator` + 逐字 `quote`；`check` 命中率 ≥0.9。
- [ ] 状态条目三字段齐全，`unknown` 未被写成 `granted/expired`。
- [ ] 族边都带证据定位，`not_exhaustive=true` 已声明。
- [ ] red/yellow 来源的降级方案写清，受限原文未出现在主结果。
- [ ] `boundaries` 覆盖 §9 实际触发的类别；`gaps` 写清缺什么、何时补。
- [ ] `status` 与实际完成度一致；`degradations` 与运行实况一致。
- [ ] 重跑一次产物一致（`selfcheck` 指纹比对）。

## 14. 最小调用示例（示例，非任何正式案例结果）

```bash
$ python3 scripts/main.py init --input ./input --output ./output --work ./work
== init v1.0.0 == case ./input/case.json | contract number_registry,family,status,license | materials 5 | numbers 9 | families 2
  M1  materials/patent_records.md      text    patent_record(0.9)          1841字  6段
  M2  materials/us1234567b2_ocr.txt    text    facsimile_ocr(0.8)           902字  4段
  M3  materials/family_links.csv       text    family_link(0.9)             210字  3段
  M4  materials/license_table.md       text    license(0.9)                 260字  4段
  M5  materials/paper_abstract.txt     text    paper(0.7)                   540字  2段
NEXT: write ./work/draft.json then check then build
$ python3 scripts/main.py check
== check == draft work/draft.json | numbers 9/9 | status 3/3 | evidence 11/12 (0.92) | facets 7/8 | FIX 0
$ python3 scripts/main.py build
== build == ok | agent | dossiers.md 6.4 KB | numbers 9 | edges 2 | status 3 | papers 1 | boundaries 5 | contract 4/4
$ python3 scripts/main.py selfcheck
== selfcheck == PASS | contract 4/4 | artifacts 6/6 | evidence 0.92 | fingerprint e3b0c442...
```

以上数字仅示意接口与输出形态，**不是任何正式案例的评测结果**。

## 15. 评分维度落点

| 评分维度 | 本包落点 |
|---|---|
实际效果（40） | 号码/主题两类检索都能走通；号码规范化与规则链可复核；族边与状态都带来源；六件产物 + 契约全键回填 |
使用增益（25） | 一次 `show` 拿到带 locator 的对象清单；登记簿/族图/来源表/闸门/边界日志一次成型，减少跨库切换与重复核对；同输入同口径可复跑 |
创新增益（15） | 号码解析规则链 + 族口径（simple/extended + not_exhaustive）+ 状态三字段纪律 + 许可闸门降级 + 边界日志 + OCR 容错证据核验 |
可靠体验（10） | 五命令主路径；恒 exit 0；缺稿/坏 JSON/空输入/受限来源四类降级；`selfcheck` 指纹复检 |
生态贡献（10） | 本说明 + `references/field-dictionary.md`（字段字典/号码规范/状态分级/许可模板）+ `references/rubric-checklist.md`（评分点对照与复用清单）+ 纯标准库脚本 |

## 16. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
`SKILL.md` | 本说明（手册与契约） |
`scripts/main.py` | 五命令、契约回填、finalize、运行日志、路径兼容 |
`scripts/registry.py` | 材料发现与分诊、号码规范化、候选提取、族/状态/许可候选、覆盖率、指纹 |
`scripts/dossier.py` | 工作稿装载与兜底、R1–R13 校验、六件产物渲染、selfcheck |
`references/field-dictionary.md` | 字段字典（工作稿/产物/`result.json`）、号码规范表、状态分级、许可模板、边界模板 |
`references/rubric-checklist.md` | 评分维度 → 检查项对照表、复用与分享清单、维护指引 |

版本 1.0.0。改契约映射改 `main.py` 的 `CONTRACT_MAP`；改校验改 `dossier.py` 的 `check()`；改号码规则改 `registry.py` 的 `normalize_number()`；改表头/文案改 `render.py` 与 `references/field-dictionary.md`。四个脚本均纯标准库、互不依赖外部包、支持 `--help`。

**已知边界**：定位以"段"为单位（空行分隔），PDF 粗解析可能丢失阅读顺序，重要引文先用 `show` 回看；OCR 容错命中会标 `ocr_tolerant` 但不等同官方核对；许可分级依据材料声明，材料未声明时给 `yellow` 并进 `gaps`；本包不做侵权/FTO/价值判断。
