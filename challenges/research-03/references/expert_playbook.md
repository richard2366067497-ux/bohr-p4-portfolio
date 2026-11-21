# 专家参考手册 —— 系统综述筛选与 PRISMA 流程

本手册是 systematic-review 的**执行前必读**方法论：它规定从研究问题拆解、检索式构造、纳排筛选、
质量评价到带证据回链结论的完整链路，以及每一步的冻结产物、量化口径、判定门控与自查清单。
执行时按本手册推进，产出后再逐项过 §7 自查表。

---

## 1 任务本质与判分要点

要交付的不是一篇「像综述」的文章，而是**一条可被他人复跑的系统性文献综述流程**：从研究问题拆解、
检索式构造、纳排筛选、质量评价到带证据回链的综述结论的完整链路，以及每一步的**冻结产物、判定记录
和可核验依据**。一个有经验的研究者拿到它，应能不额外追问即复核每一步。

高分要素（缺一即扣分）：

1. **链路完整性**：真正走完「问题拆解 → 检索式 → 纳排筛选 → 质量评价 → 证据回链结论」全流程，
   而不是只给一段总结。
2. **可执行性与真实性**：检索式能落到指定数据库与字段并命中领域核心文献；纳排判定符合事先写定的
   条款；引用的文献与元数据真实；综述论断被纳入证据支撑且不越界。
3. **可核验性**：检索式原文、检索日期与数据库、筛选记录、质量评价依据和引用定位能被他人复跑复核。
4. **增益可验证**：相比基础流程，在纳排一致性、证据回链质量、结论稳健性上有可证明的提升。
5. **可靠与异常处理**：不同主题、不同文献规模、不同数据库和重复运行下稳定产出；对检索为空、超时、
   全文不可得、术语歧义、纳排冲突、证据矛盾等有识别与处置。

| 关注点 | 判定标准 |
|--------|----------|
| 检索式可用性 | 含数据库、字段、布尔逻辑、同义词/受控词、时间与语言限制，且每段有意图 |
| 条款可判定性 | 每条纳排条款四要素齐全（对象 + 判据 + 阈值 + 轮次），排除理由与条款一一对应 |
| 证据可回链 | 每条论断给出 `[文献ID] 表/图/段落` 级 locator，且非空 |
| 评价可解释 | 每个维度判断附依据位置与总体等级，等级明确影响结论权重 |
| 异常诚实 | 检索为空、全文不可得、冲突证据分别记录，不用成功包装失败 |

## 2 常见失败模式（错误做法 → 正确做法）

| # | 错误做法 | 正确做法 |
|---|----------|----------|
| F1 | 检索式退化成一个关键词串，如 `perovskite stability additive` | 写出可执行布尔串：`(perovskite solar cell* OR PSC) AND (additive* OR dopant* OR "additive engineering") AND (stability OR degradation OR "long-term" OR T80) AND ("2015/01/01"[Date - Publication] : "2024/12/31"[Date - Publication])`，并注明数据库、字段、时间与语言限制 |
| F2 | 纳排标准在筛选途中被悄悄放宽（写「仅纳入 RCT」，遇到非随机但数据好的文献就纳入且不改标准） | 纳排条款化、版本化；需修改时记录版本号、时间、理由，并重新筛选已处理条目 |
| F3 | 排除理由缺失或前后矛盾（只写「排除」不写原因；同一文献两阶段理由不一致） | 每条排除记录有非空、可判定的理由，且与纳排条款一一对应；跨阶段一致或明确升级 |
| F4 | 质量评价只剩一句「质量较高」 | 逐条给出维度判断、依据位置（如「随机化：低风险，依据[文献7]方法部分第2段」）与总体等级，并说明它如何影响结论 |
| F5 | 综述论断找不到回链的原文位置（如「添加剂工程能显著提升稳定性」） | 给出可核验数值与定位：`碱金属添加剂（如 K+）在 85°C 热老化下将 T80 从 200h 提升至 800h（证据：[文献7] 表2；[文献9] Fig 3）` |
| F6 | 任务中断后无法定位是哪一步出错（中间结果全在内存） | 每步冻结产物到 `/app/work`，最终结果到 `/app/output`；用 `change_records` 记录版本、时间、修改内容 |
| F7 | 伪造数据或按案例标签假设文献内容，编造 DOI 与结论 | 实际读取 `/input/case.json` 与提供的材料；引用元数据必须来自真实输入；不确定时标注「无法确定」 |

## 3 求解框架与门控（九步）

从输入材料到交付物的分步流程，每步有冻结产物与门控。所有中间产物写入 `/app/work`，最终结果写入
`/app/output`。**前一步未冻结不进入下一步。**

| 步骤 | 动作 | 冻结产物 | 门控（通过条件） |
|---|---|---|---|
| S1 输入解析 | 读取 `case.json`、`task.md`、材料文件；提取研究问题、已知核心文献、数据库范围、约束 | `input_summary.json` | 研究问题明确；输入文件路径有效；无缺失关键字段 |
| S2 问题结构化 | 将研究问题拆为可检索要素（PICO/PS）；识别同义词、受控词、术语歧义 | `research_question.json` | 每个要素有 ≥1 检索词；歧义已标注 |
| S3 检索式构造 | 写出可执行检索式，注明数据库、字段、布尔逻辑、时间/语言限制；说明每段意图 | `search_string.md` | 检索式可被数据库解析；字段标签正确；时间/语言限制明确 |
| S4 检索执行 | 若案例提供题录则导入，否则按检索式在指定数据库执行（或记录未执行原因） | `search_results.csv` | 命中条数记录；每条有唯一文献 ID；无重复 |
| S5 题录筛选 | 按纳排标准逐条判定，记录纳入/排除及理由 | `screening_title_abstract.csv` | 每条有判定结论；排除条目有非空理由；理由与条款对应 |
| S6 全文筛选 | 对题录纳入条目取全文（或摘要替代），逐条判定 | `screening_fulltext.csv` | 同上；全文不可得条目单独标注 |
| S7 质量评价 | 对纳入研究逐条评价，记录维度判断、依据位置、总体等级 | `quality_assessment.csv` | 每条有总体等级；每个维度判断有依据位置 |
| S8 证据综合 | 从证据表提取可比较字段，形成结论、冲突证据、研究空白 | `evidence_matrix.csv`、`synthesis.md` | 每条论断有 locator；冲突与空白明确；不越界 |
| S9 输出 result.json | 汇总所有字段，写入 `result.json` | `result.json` | 含所有 output_contract 字段；status 诚实；sources 完整；uncertainty 明确 |

**映射到本 Skill 产物**：S1–S2↔`criteria.json` 与 `report.md` 的研究问题与标准节；S3↔检索式意图（写入
报告与标准）；S4–S6↔`prisma_flow.json` 与 `screening_ledger.jsonl`；S7↔`appraisal.json`（五维）；
S8↔`report.md` 的结论/局限节与 `uncertainties`；S9↔`result.json` 的逐键回填。

**增量保存原则**：每完成一步立即写文件；用 `change_records` 记录每次修改。若某步失败，保留已完成步骤
的产物，并在 `status` 中说明失败位置与原因。

## 4 量化口径与公式（含数字示例）

| 指标 | 定义 | 公式 | 单位 | 可接受波动 |
|---|---|---|---|---|
| 检索式覆盖率 | 命中核心文献数占已知核心文献集的比例 | `覆盖率 = 命中核心文献数 / 已知核心文献总数 × 100%` | % | ≥ 80%（若案例提供核心集） |
| 纳排一致性 | 重复筛选或双人筛选一致条目数占抽检条目数的比例 | `一致性 = 一致条目数 / 抽检总条目数 × 100%` | % | ≥ 90% |
| 排除理由完整率 | 有非空排除理由的排除条目数占总排除条目数的比例 | `完整率 = 有理由排除条目数 / 总排除条目数 × 100%` | % | 100%（必须） |
| 证据回链率 | 有 locator 的综述论断数占总论断数的比例 | `回链率 = 有 locator 论断数 / 总论断数 × 100%` | % | 100%（必须） |
| 质量评价依据覆盖率 | 有依据位置的质量判断数占总质量判断数的比例 | `覆盖率 = 有依据位置判断数 / 总判断数 × 100%` | % | 100%（必须） |
| 可复算率 | 可复算步骤数占总步骤数的比例 | `可复算率 = 可复算步骤数 / 总步骤数 × 100%` | % | ≥ 80% |

**计算示例（数字自洽）**：某案例检索命中 342 条；题录筛选排除 210 条、纳入 132 条；全文筛选排除
120 条、纳入 12 条。

- **排除理由完整率**：排除总数 = 210 + 120 = 330；有理由排除条目数 = 330；`330 / 330 × 100% = 100%`。
- **纳排一致性**：抽检 20 条（题录 10 + 全文 10），一致 19 条；`19 / 20 × 100% = 95%`。
- **质量评价依据覆盖率**：纳入 12 条 × 4 维 = 48 个判断，均有依据位置；`48 / 48 × 100% = 100%`。
- **证据回链率**：综述共 3 条论断，3 条有 locator；`3 / 3 × 100% = 100%`。
- **可复算率**：9 个步骤中 8 个可复算（检索执行若依赖外部数据库可能不可复算，但可提供检索式与日期）；
  `8 / 9 × 100% = 88.9%`。

**PRISMA 守恒等式**（脚本派生，不符即报错）：`identified = screened_title_abstract + not_screened`；
`excluded = excluded_title_abstract + excluded_full_text`；`included ⊆ full_text_assessed`。

## 5 领域陷阱与单位

本领域容易犯的事实性错误：

1. **混淆文献类型**：把系统综述/meta 分析当作原始研究纳入；把会议摘要当作全文；把预印本当同行评议文献。
   **正确**：纳排标准明确「仅纳入同行评议的原始研究；系统综述用于背景但纳入主要分析时单列」。
2. **错误领域标签**：按案例文件名或标签假设文献内容，不读实际材料。**正确**：实际读取 `/input` 下的
   材料并提取真实元数据；不确定时标注「无法确定」。
3. **效应量单位混淆**：HR（风险比）、RR（相对危险度）、OR（比值比）不可互换；时间单位（月 vs 年）
   不可混用。**正确**：在证据表明确效应量类型与单位，如 `T80 = 800 h（85°C，N₂ 氛围）`。
4. **浓度/温度单位陷阱**：mM vs μM、°C vs K、mol% vs wt% 不可混用。**正确**：统一单位并注明原始单位。
5. **样本量单位**：例（患者数） vs 人年（随访时间×人数）不可混用。**正确**：分别记录样本量与随访时间。

文献依据要求：

- 每条论断必须指向具体文献的**段落、表格或图**，不能只给作者与年份。格式：`[文献ID] 表2/Fig 3/第4段`。
- 引用元数据必须真实，不得编造 DOI、期刊、年份；输入未提供时标注「来源未提供」。
- 区分**材料事实**（原文明确陈述）、**合理推断**（基于原文数据的逻辑延伸）与**无法确定**（证据不足），
  在 `uncertainty` 中标注。

## 6 交付物与可核验方式

| 文件 | 内容 | 自证可核验方式 |
|---|---|---|
| `templates/search_string_template.md` | 检索式模板 | 含数据库、字段、布尔逻辑、时间/语言限制 |
| `templates/screening_log_template.csv` | 筛选记录模板 | 列：文献ID、阶段、判定、排除理由、判定人、时间 |
| `templates/evidence_matrix_template.csv` | 证据表模板 | 列：文献ID、比较字段、数值、单位、locator |
| `templates/quality_assessment_template.csv` | 质量评价量表模板 | 列：文献ID、维度、判断、依据位置、总体等级 |
| `README.md` | 使用说明、依赖、配置、示例、限制 | 说明如何复跑 |
| `GITHUB_URL.txt` | GitHub 链接 | 根目录放置，第一行链接 |
| `/app/output/result.json` | 逐键回填的最终结果 | `result.json` 含所有 output_contract 字段 |
| `/app/output/prisma_flow.json` | PRISMA 计数 | 与 `screening_ledger.jsonl` 逐条对账 |
| `/app/output/screening_ledger.jsonl` | 逐题筛选台账 | 每行含 rid、locator、ta_decision、full_text 与理由 |
| `/app/output/appraisal.json` | 纳入研究五维质量评价 | 每维含 assessed/status/note，非空 |
| `/app/output/criteria.json` | 纳入/排除标准与关键词 | 每个排除条目可回指一条条款 |
| `/app/output/report.md` | 人读报告 | PRISMA 计数、标准、台账摘要、评价、局限互相对账 |

`result.json` 至少包含以下字段（`case_id` 原样透传，`status` 取诚实状态值）：

```json
{
  "case_id": "case_001",
  "status": "completed",
  "sources": ["input/case.json", "input/materials/records.md"],
  "main_result": {
    "research_question": "研究问题复述",
    "search_string": "可执行布尔检索式",
    "included_studies": 12,
    "excluded_studies": 330,
    "synthesis_conclusions": [
      {"claim": "一条可检验的结论", "locator": "[文献7] 表2", "type": "fact"}
    ],
    "conflicts": ["两条证据效应方向不一致"],
    "gaps": ["缺乏某亚组数据"]
  },
  "evidence_matrix": "evidence_matrix.csv",
  "uncertainty": {
    "conflicts": "冲突证据说明",
    "biases": "偏倚风险说明",
    "gaps": "研究空白说明",
    "undetermined": "无法确定项说明"
  },
  "change_records": [
    {"time": "step", "action": "excluded 210 records at title/abstract", "reason": "条款 C4/C5/C6"}
  ]
}
```

自证可核验：

- **locator**：每条论断与每个质量判断都提供 `[文献ID] 表/图/段落`。
- **逐字引用**：在证据表中提供原文摘录列，如 `原文摘录："The T80 lifetime increased from 200 h to 800 h upon addition of 5 mol% K+"`。
- **复算命令**：提供命令或脚本重算计数与一致性，如 `python scripts/main.py all --input /input --output /app/output --work /app/work`，
  再读 `prisma_flow.json` 与 `screening_ledger.jsonl` 对账。

## 7 防扣分自查表（交付前逐项通过）

1. ☐ 检索式是否包含数据库、字段、布尔逻辑、同义词/受控词、时间与语言限制？
2. ☐ 检索式是否可执行，且每段意图有说明？
3. ☐ 纳排标准是否条款化、可判定，且版本化？
4. ☐ 筛选记录是否每条有判定结论，排除条目有非空理由？
5. ☐ 排除理由是否与纳排条款一一对应，无前后矛盾？
6. ☐ 质量评价是否逐条给出维度判断、依据位置、总体等级？
7. ☐ 质量等级是否影响后续结论（如低质量研究仅用于敏感性分析）？
8. ☐ 综述每条论断是否有 locator（`[文献ID] 表/图/段落`）？
9. ☐ 是否区分材料事实、合理推断、无法确定？
10. ☐ 是否记录冲突证据和研究空白？
11. ☐ 是否保留版本和修改记录（`change_records`）？
12. ☐ 是否处理检索为空、数据库超时、全文不可得、术语歧义、纳排冲突、证据矛盾等异常？
13. ☐ 是否使用真实文献元数据，不编造 DOI、期刊、年份？
14. ☐ 是否在 `/app/output` 下保存最终结果，且 `result.json` 包含所有 output_contract 字段？
15. ☐ 是否诚实标注 `status` 和不确定性，不掩盖失败？
16. ☐ 是否提供可复算命令或脚本？
17. ☐ 是否在根目录放置 `GITHUB_URL.txt`，且链接有效？
18. ☐ 是否避免预制答案，所有结果来自实际运行？
19. ☐ 是否控制文件大小和数量（≤50 个 UTF-8 文本文件，每个 ≤500KB，总计 ≤2MB）？
20. ☐ 是否在 64 请求、900 秒、16384 tokens/响应预算内完成，并保存部分结果？

## 8 完整虚构案例演示

> 以下为虚构演示，数字自洽，用于说明流程；实际运行必须基于真实输入。

**输入**（`case.json`）：

```json
{
  "case_id": "case_demo_001",
  "research_question": "在钙钛矿太阳能电池中，添加剂工程对长期稳定性的影响是什么？",
  "known_core_papers": ["paper_7.pdf", "paper_9.pdf", "paper_11.pdf"],
  "database": "Web of Science Core Collection",
  "time_range": "2015-01-01 to 2024-12-31",
  "language": "English"
}
```

**关键中间量**

- S2 问题结构化（PICO）：P 钙钛矿太阳能电池（perovskite solar cell, PSC）；I 添加剂工程
  （additive engineering, dopant, additive）；C 无添加剂或不同添加剂；O 长期稳定性
  （long-term stability, degradation, T80 lifetime）。
- S3 检索式：`(perovskite solar cell* OR PSC) AND (additive* OR dopant* OR "additive engineering") AND (stability OR degradation OR "long-term" OR T80) AND ("2015/01/01"[Date - Publication] : "2024/12/31"[Date - Publication])`；
  数据库 Web of Science Core Collection；字段 Topic；语言 English。
- S4 检索命中 342 条。
- S5 题录筛选排除 210 条（重复 15、不相关 120、非英文 5、会议摘要 30、综述 40），纳入 132 条。
- S6 全文筛选排除 120 条（无全文 10、无稳定性数据 20、非原始研究 15、数据重复发表 5、其他 70），纳入 12 条。
- S7 质量评价：12 条纳入研究，每条 4 维（随机化、盲法、数据完整性、报告质量），总分 0–4；平均 3.2，
  其中 2 条为低质量（总分 ≤2），仅用于敏感性分析。
- S8 证据综合，提取字段：添加剂类型、浓度、器件结构、初始效率、衰减后效率、T80、测试条件（温度、湿度、
  光照）。形成 3 条论断：
  1. **事实**：碱金属添加剂（如 K+）在 85°C 热老化下将 T80 从 200h 提升至 800h。Locator：`[文献7] 表2；[文献9] Fig 3`。
  2. **事实**：高浓度添加剂（>5 mol%）导致相分离，降低稳定性。Locator：`[文献4] 第4段`。
  3. **冲突**：关于湿度稳定性，文献2 显示改善，文献11 显示无显著差异。Locator：`[文献2] 表1；[文献11] Fig 2`。

**量化指标计算**：排除理由完整率 `330 / 330 × 100% = 100%`；纳排一致性抽检 20 条、一致 19 条 = `95%`；
质量评价依据覆盖率 `48 / 48 × 100% = 100%`；证据回链率 `3 / 3 × 100% = 100%`；可复算率 `8 / 9 × 100% = 88.9%`。

**输出**（`result.json` 摘要）：

```json
{
  "case_id": "case_demo_001",
  "status": "completed",
  "sources": ["input/case.json", "input/materials/paper_7.pdf"],
  "main_result": {
    "research_question": "在钙钛矿太阳能电池中，添加剂工程对长期稳定性的影响是什么？",
    "search_string": "(perovskite solar cell* OR PSC) AND (additive* OR dopant* OR \"additive engineering\") AND (stability OR degradation OR \"long-term\" OR T80) AND (\"2015/01/01\"[Date - Publication] : \"2024/12/31\"[Date - Publication])",
    "included_studies": 12,
    "excluded_studies": 330,
    "synthesis_conclusions": [
      {"claim": "碱金属添加剂（如 K+）在 85°C 热老化下将 T80 从 200h 提升至 800h", "locator": "[文献7] 表2；[文献9] Fig 3", "type": "fact"},
      {"claim": "高浓度添加剂（>5 mol%）导致相分离，降低稳定性", "locator": "[文献4] 第4段", "type": "fact"},
      {"claim": "关于湿度稳定性，文献2 显示改善，文献11 显示无显著差异", "locator": "[文献2] 表1；[文献11] Fig 2", "type": "conflict"}
    ],
    "conflicts": ["湿度稳定性结论不一致"],
    "gaps": ["缺乏柔性器件数据", "缺乏大面积模组数据"]
  },
  "evidence_matrix": "evidence_matrix.csv",
  "uncertainty": {
    "conflicts": "文献2 与文献11 关于湿度稳定性结论不一致",
    "biases": "2 条低质量研究仅用于敏感性分析",
    "gaps": "缺乏柔性器件和大面积模组数据",
    "undetermined": "添加剂作用机理尚不明确"
  },
  "change_records": [
    {"time": "step", "action": "excluded 210 records at title/abstract", "reason": "duplicates, irrelevant, non-English, conference abstracts, reviews"},
    {"time": "step", "action": "excluded 120 records at full text", "reason": "no full text, no stability data, non-original, duplicate data"}
  ]
}
```

此演示中所有数字可复算，所有论断可回链，所有排除有理由，满足 §1 的高分要素与 §7 的全部自查项。
