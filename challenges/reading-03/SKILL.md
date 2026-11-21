---
name: sci-lit-bilingual-audit
description: 科研文献段落级中英对照 + 术语锁定 + 机械核验；纯标准库、离线、确定性。
version: 3.0.0
---

# sci-lit-bilingual-audit — 科研文献双语对照与机械核验 Skill

把一篇（或一个明确段落区间）的英文科研文献做成**段落级中英对照 + 术语表 + 核验记录**：每段可指回原文页码/段号，
关键结论带逐字证据，译不准的部分显式标注。纯标准库、离线、确定性；**译文由 Agent 写进工作稿**，脚本负责
切段、抽取、保护、核验、取证。

| 题面要求 | 做法 | 可核验产物 |
|-|-|-|
| 术语稳 | quote 逐字命中才 locked，全篇回扫并统计一致率 | `glossary.json`、`glossary_summary` |
| 段落全 | R1–R7 切段 + 跨页续段 + 要素型段落单独成段 | `paragraph_pairs.jsonl`、`elements` |
| 关系准 | 数字/单位/引用/图表编号/公式号保护性 span；否定与限定逐句核对 | `audit_summary.rates`、`audit_report.json` |
| 可核验 | 每段 locator + 证据 quote + 依据 basis + 未译/不确定标注 | `result.json.evidence`、`bilingual_review.md` |

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按手册的求解框架（含每步冻结产物与门控）推进；前一步未冻结不进入下一步。
- **口径**：按手册的术语、对齐与公式口径逐项核验；原值与原单位保留，不跨段补译、不擅自改写。
- **陷阱**：按手册的领域陷阱清单逐条排雷（错误做法 → 正确做法）。
- **门控**：交付前逐项通过手册 **§9 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为成功。

---

## 1 输入与边界

`/input` 下：`case.json`（`case_id`/`language`/`target_language`/可选 `output_contract`/可选内嵌 `paper_text`）、
`task.md`、`materials/`（`.txt .md .html .htm .docx .json` 与**有文本层的** `.pdf`）。

- PDF 只读文本层（内置解 FlateDecode）；扫描件/图片公式**无 OCR**，只记 degraded，不产出假正文
- 不调用外部二进制、不联网、不调用模型；没有工作稿就没有译文（`status=insufficient_evidence`），绝不编造
- 语义质量（通顺度、措辞、译名是否最优）不在机械核验范围内，只进 `human_review`

## 2 输出契约

`result.json` 顶层：`case_id / status / skill / task_understanding / sources / summary / claims / uncertainties /
change_records / limits / degradations / errors / human_review / outputs / coverage / elements / glossary_summary /
audit_summary / evidence / runtime / output_contract`。

- `output_contract`：把输入契约键**原样逐键回显**（不重命名/合并/丢键）；没给契约时回显默认键。取值一律非空非占位，
  路径型取值必须指向真实非空文件
- `status`：`answered`（全覆盖且无 fail）｜`partial`｜`insufficient_evidence`｜`input_error`
- `sources / uncertainties / change_records / limits` 恒非空（无不确定项也写一条 `kind=clean`）

契约回显形态（示意，取值来自真实运行）：

```json
{
  "case_id": "example-reading-03-osc",
  "status": "answered",
  "output_contract": {
    "case_id": "example-reading-03-osc",
    "status": "answered",
    "result": {"summary": "17 段全部已有译文，机械核验 0 fail", "pairs": 17},
    "claims": [{"sid": "S003", "locator": "p1:S003", "quote": "the germination rate decreased from 92.4 %"}],
    "uncertainties": [{"sid": "", "kind": "clean", "detail": "本次未检出未决不确定性；仍建议人工通读术语与语气"}]
  }
}
```

产物（写到 `--output`，默认 `/app/output`）：`result.json`（契约+断言+变更+局限+runtime）、
`paragraph_pairs.jsonl`（逐段 `sid/locator/page/type/section/source/target/target_status/protected_spans/terms/uncertain/notes/basis`）、
`audit_report.json`（逐项 check 结论 + 一致率/覆盖/span 缺口）、`glossary.json`（locked/proposed/candidate + quote + 出现段）、
`bilingual_review.md`（人读视图）、`run_log.txt`（运行日志与分阶段计时）。

工作目录（默认 `/app/work`）：`work/index.json`（切段与 span）、`work/draft.json`（Agent 工作稿）、
`work/check_report.json`、`work/selfcheck_report.json`、`work/compare_report.json`。

## 3 工作稿格式

Agent 只需填 `segments[].target` 与 `glossary[]`，其余交给脚本：

```json
{
  "case_id": "example-reading-03-osc",
  "task_understanding": "按语义切段做中英对照；术语按术语表锁定；数字/单位/引用编号/公式号按原文保留",
  "segments": [
    {"sid": "S001", "target": "氯化钠对种子萌发的剂量-反应建模", "uncertain": false,
     "notes": "标题：dose-response 按术语表锁定为「剂量-反应」", "basis": "逐段对照翻译；数字与引用编号按原文保留"}
  ],
  "glossary": [
    {"term": "germination rate", "target": "萌发率", "sid": "S003",
     "quote": "the germination rate decreased from 92.4 %", "basis": "术语表锁定：quote 在原文逐字命中"}
  ],
  "result_fields": {}
}
```

规则（都进核验）：`sid` 必须来自 `work/index.json`（自造段号 fail，漏段 warn）；`quote` 必须逐字命中（改写/回译即 fail，
术语不 locked）；未译段 `target` 留空 + `uncertain=true` + `notes` 写明原因，**禁止**写 `TBD`/`待写`/`...` 之类占位；
建议每段写 `basis`（译法依据，进 `evidence`）；数字/单位/`[1]`/`(1)`/`Fig. 1`/`Table 1` 一律按原文保留（多重集比对，少一个即 fail）。

## 4 段号与要素类型

- `sid = p{页}:S{序号}`，`locator` 形如 `p1:S003`；跨页续段带 `bridged=true` 与 `pages=[p1,p2]`
- `type`：`heading`（题名/标题）、`body`（正文）、`caption_figure`/`caption_table`（图/表题注）、
  `table_header`/`table_row`（表头/数据行，纯数值行按惯例保留原样）、`formula`（公式与编号）、`reference`（文献条目）
- 切段规则 R1–R7：空行断段 / 句末兜底 / 连字符拼接 / 跨页续段 / 页眉页脚丢弃 / 双栏投影切分 / 标题自成块

## 5 核验项

`audit_report.json` 的 check：`sid_integrity`、`source_verbatim`、`coverage`、`element_coverage`、`glossary_quote`、
`glossary_drift`、`glossary_lock`、`protected_numbers`、`citations`、`figure_table_refs`、`equation_tags`、`negation`、
`hedge`、`target_language`、`placeholder_policy`、`repeated_target`、`contract_fields`。判据/阈值/修法见
`references/checks_spec.md`（同文件含术语表模板与题集/评分表模板）。`fail>0` 时 `status` 最高只到 `partial`，
工作稿自报更高状态会被降级并记 `degradations`。

## 6 运行方式（Agent 流程）

先 `init` 拿切段与骨架 → 按批填译文 → `check` 看缺口 → `build` 出产物 → `selfcheck` 自检 → `compare` 出对照指标。
长文按批推进，每批写完就 `build` 一次，中途停止也能留下合法的完整产物。

```bash
python scripts/main.py init --input /input --output /app/output --work /app/work
python scripts/main.py show --sids S001-S008 --input /input --output /app/output --work /app/work
python scripts/main.py check --input /input --output /app/output --work /app/work
python scripts/main.py build --input /input --output /app/output --work /app/work
python scripts/main.py selfcheck --input /input --output /app/output --work /app/work
python scripts/main.py compare --input /input --output /app/output --work /app/work
```

`init` 不覆盖已有工作稿（续跑安全）；`show` 只看不改（`--sids` 支持 `S001-S008` 区间）；`check` 恒退出 0
（失败项在 `work/check_report.json` 里）；`selfcheck` 在 `work/_selfcheck` 空跑并逐项自检（含降级场景与占位符扫描）；
`compare` 输出"基线搬运 vs 本 Skill"的可核验差异。所有子命令接受 `--input/--output/--work`，异常不非零退出。

## 7 降级与限制

- 输入目录不存在/无可用材料：仍出完整契约与 6 个产物，`status=insufficient_evidence`（`errors`/`degradations` 记录）
- 只有占位符或空白页：整页判不可用并跳过（`placeholder_or_empty_pages_dropped`），不当作素材
- `case.json` 损坏：字面抢救 `case_id` 与契约键名（`case_json_salvaged`），不编造取值
- PDF 无文本层/加密、文本层质量差：记降级或 `text_layer_quality`，提示人工复核
- 工作稿段号对不上索引：按无工作稿处理（`draft_sids_match_zero_segments`），不臆造译文
- 译文缺失/术语未锁定/数字少写：记 fail/warn 并列进 `human_review`（每条带"怎么修"）

## 8 创新点与价值边界

术语表强制约束与全篇回填（逐字命中才锁定、每个出现段必须同名）、跨页跨栏续段（R4/R6 + `bridged`）、保护性 span
（数字/单位/引用/图表编号/公式号按多重集比对）、关系核验（否定/限定逐句核对）、自检与对照（可重复运行、可回退）。
价值边界：不判断译文好坏、不做 OCR、不代译、不联网。与基础 Agent 的失败案例与对照见包内 GAIN_EVIDENCE.md，
自检与示意输出见包内 SELFTEST.md。

## 9 生态与复用

分段规则、要素类型、术语表格式、核验口径全在 `references/checks_spec.md`（含术语表模板与题集/评分表模板），
可直接搬到新学科：换 `materials/` → `init` 看 `type` 分布 → 建术语表 → 分批填译文 → `check` 修缺口 → `build`。
`examples/` 内是最小可跑用例（内嵌论文节选 + 工作稿示例），照抄格式即可上手。

## 10 维护

`skill.version` 与变更记录写进 `result.json`；改脚本后先跑 `selfcheck`（含降级场景自检），再跑 `compare` 确认指标未回退；
锁定术语可搬进新用例的 `draft.json.glossary` 继承译名。

## 11 单命令入口（等价入口）

一次跑完全流程（无工作稿也产出完整契约与全部 6 个产物，退出码恒为 0）：

```bash
python scripts/main.py all --input /input --output /app/output --work /app/work
```

## 12 交付前自查

- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为成功。

## 13 文件清单（13 个）

| 文件 | 作用 |
|-|-|
| SKILL.md | 主文档：契约、工作稿格式、子命令、降级矩阵、创新点 |
| README.md | 上手、依赖、输入、约定速查 |
| SELFTEST.md | 自检记录 + 缺陷注入复现 + 示意输出节选 |
| GAIN_EVIDENCE.md | 增益证据：基线失败案例、对照指标、效率口径、价值边界 |
| GITHUB_URL.txt | 公开作品链接（两行） |
| references/checks_spec.md | 核验项规格 + 术语表模板 + 题集/评分表模板 |
| references/expert_playbook.md | 专家参考手册：任务本质、求解框架与门控、口径公式、陷阱清单、案例、§9 自查表 |
| environment/resources.yaml | 运行环境与资源声明：单命令入口、路径约定、预算、依赖、无网络、纯标准库 |
| examples/case.json | 最小用例（内嵌论文节选 + 5 键契约） |
| scripts/core.py | 材料发现、PDF/HTML/DOCX 提取、R1–R7 切段、保护性 span、术语候选 |
| scripts/audit.py | 机械核验引擎（17 类 check）与状态推导 |
| scripts/report.py | 结果装配、报告渲染、工作稿读写与契约键归一 |
| scripts/main.py | 命令行入口（all/init/show/check/build/selfcheck/compare） |
