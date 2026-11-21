# 专家参考手册 —— 科研选题与创新性评估的五门判定

本手册是 research-topic-innovation-eval 的执行前必读方法论：它规定材料读取与规则定位口径、
五门判定的求解框架与门控、量化指标与公式、领域陷阱与单位、交付物形态与可核验方式，以及交付前的
防扣分自查表。执行时按 §2 逐步推进（前一步未冻结不进入下一步），产出后逐项过 §7 自查表。

---

## 1. 判分要点与错误做法

交付物不是一篇综述，而是四项**相互一致、可核验**的结构化判断：研究问题定义、已有工作比较、
创新点识别、可行性判断；每条判断都能回到材料的具体位置（`M#/p#`）。评分维度五档：实际效果 40、
使用增益 25、创新增益 15、可靠体验 10、生态贡献 10；其中实际效果拆为任务完成度、结果正确性、
完整性、可核验性。五门判定与四个交付切面的对应关系：

| 门 | 名称 | 回答的问题 | 题面交付项 | 本包产物 |
|-|-|-|-|-|
| G1 | worth_doing | 值得做吗 | 研究问题定义 | `decision_brief.md` 第 1–2 节 |
| G2 | nobody_done | 别人做到哪一步 | 已有工作比较 | `prior_art_alignment_matrix.csv` |
| G3 | can_do | 做得出来吗 | 可行性判断 | `assumption_register.json` |
| G4 | not_old_wine | 不是旧方案吗 | 创新点识别 | `gate_scorecard.json` 的 G4 条目 |
| G5 | downside | 失败会怎样 | 可行性判断（风险侧）+ 冲突证据 | `conflicts.json` |

常见失败模式逐条对照（错误做法 → 正确做法）：

| 错误做法 | 正确做法 |
|-|-|
| 把「检索不到」直接写成「尚无人研究」 | 区分「未检索到直接证据」与「已确认空白」，给出检索式、材料范围、时间窗 |
| 把方法上的旧方案当成新方法 | 建立比较矩阵，逐条比对任务、方法、数据、评价方式、结论 |
| 把应用场景迁移说成理论创新 | 明确创新类型：方法创新、数据创新、场景迁移、结论修正，并判定是否被覆盖 |
| 可行性只给一句「技术路线可行」 | 列出数据、算力、实验条件、时间窗口、人员能力等前提，每个前提有来源或标为假设 |
| 只报告支持性证据，忽略相反证据 | 登记冲突证据并说明取舍理由 |
| 结论无法回到文献位置 | 每条关键判断附 locator：文献 ID + 段落/表/图编号 |
| 输出长报告但无结构化字段 | 按输出契约逐键产出 `result.json`，含 case_id、status、sources、uncertainty、change_records |
| 按领域标签补造数据，不读实际文件 | 必须读取输入目录下的实际 PDF/JSON/Markdown，不依据错误的领域标签 |
| 运行失败不说明，硬凑完整结果 | 部分结果必须显式标识 limits，status 用 `partial` 或 `insufficient_evidence` |
| 直到最后才保存中间产物 | 每步冻结产物到 work 目录，尽早保存 partial 交付物 |

---

## 2. 求解框架与门控

从输入材料到交付物的八步流程，每步有冻结产物与门控条件，**前一步未冻结不进入下一步**。

| 步 | 操作 | 冻结产物 | 门控条件 |
|-|-|-|-|
| S0 读取输入与资源清单 | 读 case、task、`environment/resources.yaml`，确认 case_id、材料路径与约束 | `case_manifest.json`（含 case_id、材料清单、哈希、解析状态） | 至少一个材料成功解析；否则输出 `partial` 并标记原因 |
| S1 研究问题定义 | 把模糊设想拆成研究对象、关键变量、比较基线、预期结论、可证伪条件 | `problem_statement.json` | 五个字段齐全且可检验 |
| S2 检索与筛选 | 在**提供的材料范围内**检索（非开放网络），记录检索式、筛选标准、纳排理由 | `search_log.json` + `screening_table.csv` | 纳入文献数 ≥1，且每篇排除都有明确理由 |
| S3 证据提取与比较矩阵 | 逐篇提取文献 ID、任务、方法、数据、评价方式、结论、证据定位、相关度 | `prior_art_alignment_matrix.csv`、`evidence_index.jsonl` | 每行至少 5 个字段非空，关键判断有 locator |
| S4 创新点识别与边界划定 | 逐条与已有工作比对，判定类型（方法/数据/场景/结论修正）与覆盖状态 | `gate_scorecard.json` 的 G4 条目 | 每条创新点有对比文献或明确「未检索到直接证据」 |
| S5 可行性判断 | 核查数据、算力、实验条件、时间窗口、人员能力等前提 | `assumption_register.json`（含 kill criteria） | 每个前提有来源或标为假设；`unsupported` 存在时 G3 不得判 go |
| S6 综合结论与不确定性 | 汇总四项交付，区分材料事实、合理推断、无法确定，登记冲突与空白 | `decision_brief.md` + `uncertainty.json` | 每个产物带结构化记录，未命中引文写入 uncertainty |
| S7 输出与自检 | 写出全部产物与 `result.json`，运行自检 | `result.json`、`self_check.json` | 契约键逐键非空、所有 locator 可回溯、无 ERROR |

跨门一致性硬规则：**总体判定不得高于最弱一门**（否则报 `E_DECISION_INCONSISTENT`）；
判 go 但存在 `unsupported` 前提报 `E_G3_GO`；`covered` 无 `covered_by`、`novel` 无边界、
矛盾证据未登记都报码并降级，不静默发布。门控失败只降级受影响的对象，不阻碍其余可交付部分。

---

## 3. 量化口径与公式

所有指标记入 work 层并复算，用于自检与报告。

- **证据覆盖率 EC** ＝ 已提取完整证据字段的文献数 / 纳入文献总数 × 100%，目标 **≥90%**；
  低于阈值标记 `partial` 并说明缺失字段。
- **可核验性比例 VR** ＝ 带 locator 的关键判断数 / 关键判断总数 × 100%，目标 **100%**；
  任何关键判断无 locator 即扣分。
- **冲突证据登记率 CRR** ＝ 已登记冲突证据条数 / 识别到的冲突证据条数 × 100%，目标 **100%**；
  漏登记一条即扣分。
- **新颖性保留率 NRR** ＝ not_covered 创新点条数 / 总创新点条数 × 100%。NRR 高不代表创新强，
  必须结合边界说明，仅作内部统计，不作唯一结论。
- **可行性前提来源率 FSR** ＝ 有来源的前提数 / 前提总数 × 100%，目标 **≥80%**；
  其余前提必须显式标为假设。
- **检索式可复现性 SR** ＝ 1 若检索式完整记录（材料范围、检索词、时间窗、筛选标准），否则 0，目标 **1**。

判定口径（与产物一致）：逐字命中率 = 已验证证据数 / 总证据数；**命中率 <80% → `status=partial`**；
`status=ok` 还要求零 ERROR；`global_claim` 必须为 false，材料级空白不升级为领域级断言。

**数字示例**：纳入 7 篇文献，6 篇证据字段完整 → EC = 6/7 = **85.7%** < 90%，需补全；
关键判断 10 条，9 条带 locator → VR = 9/10 = **90%**，需补 1 条；冲突证据 2 条，登记 2 条 →
CRR = **100%**；创新点 3 条（1 条 not_covered、1 条 partially_covered、1 条 covered）→
NRR = 1/3 = **33.3%**；可行性前提 5 个，4 个有来源 → FSR = **80%**；SR = **1**。
可接受波动：EC ≥90%，VR = 100%，CRR = 100%，FSR ≥80%，SR = 1；低于阈值必须标记 limits。

---

## 4. 领域陷阱与单位

**事实性错误高发点**

| 错误 | 正确 |
|-|-|
| 混淆「未检索到」与「不存在」 | 必须给出检索式、材料范围、时间窗，未检索到只能支撑 undetermined |
| 方法名称相同但任务不同视为同一工作 | 需比较任务、数据、评价方式 |
| 把场景迁移当作理论创新 | 需明确创新类型 |
| 忽略负面结果或冲突证据 | 必须登记并说明取舍 |
| 错误引用文献结论 | 逐字引用或准确定位，不得改写原意 |

**单位 / 量纲陷阱**（统一单位后再比较，否则结论不可靠）

- 比容量：`mAh/g` 与 `mAh/cm²` 不可直接比较。
- 电流密度：`mA/g` 与 `mA/cm²` 需换算。
- 循环稳定性：容量保持率 %，需注明循环圈数与电流密度。
- 库仑效率 %，需注明循环区间。
- 温度 `°C` 与 `K`；压力 `Pa` 与 `bar`；浓度 `mol/L` 与 `wt%`。
- 催化：TOF（h⁻¹）、TON（无量纲）、产率/选择性/转化率（%）。
- 数据量：样本数、重复次数、误差棒（标准差/标准误）。
- 数字溯源：材料未给依据的数值只能作「计划值」提示，不得当作实测。

**文献依据要求**

- 每条关键判断必须回到具体文献位置（作者、年份、段落/表/图），关键判断 100% 带 locator。
- 引用原文时用引号，标注页码或段落号；改写过、找不到的句子判 `quote_not_found` 并失去证据资格。
- 不得使用二手综述作为唯一证据，需追溯到原始研究。
- 材料事实必须有来源；推断需标注「推断」；无法确定需标注「无法确定」。

---

## 5. 交付物与可核验方式

运行时产物（写入 `--output`）：

| 文件 | 必需内容 | 可核验方式 |
|-|-|-|
| `result.json` | 契约键（顶层 + `output_contract`）、case_id、status、sources、uncertainty、change_records | `python -m json.tool` 解析通过，契约键逐键非空 |
| `decision_brief.md` | 四交付 ↔ 五门、逐门 verdict 与阈值、矩阵、前提、冲突、限范围空白、附录 A–C | 结论逐条回指 locator 与逐字引文 |
| `gate_scorecard.json` | G1–G5 的 verdict、conditions、evidence_ids、残余风险、pivot、规则与阈值原话 | 每门可回到 `M#/p#` |
| `prior_art_alignment_matrix.csv` | 一行一主张的长表，材料未给写「材料未给」 | 每行有 claim_id、locator、四维比较字段 |
| `assumption_register.json` | 可行性前提的 state（source/assumed/unsupported）与 kill criteria | 状态分布可复算 |
| `evidence_index.jsonl` | 每行一条：locator、逐字引文、match、verified | 按 locator 回到原文逐字核对 |
| `conflicts.json` | 相反证据两侧原话与取舍；无冲突时写限范围的 `no_contrary_found` | 两侧均带 locator |
| `coverage.json` | 六类覆盖检查、计数与 verdict 统计 | 命中率与门数一致 |
| `self_check.json` | 产物齐全、契约回填、证据命中与未清零 `E_*` | 未达标输出 attention 与缺失清单 |
| `change_log.json` / `search_log.json` / `uncertainty.json` / `gain_evidence.json` / `run_log.txt` | 降级记录、检索式与筛选标准、未命中项与未决区、增益条目、逐材料解析状态 | 逐步可复核 |
| `evidence/sources_snapshot.json` | 对象表的别名、重复与版本标记（retract/预印本/修订版） | 未解析记录如实列出 |

随包可复用资源：`references/expert_playbook.md`（本文档，方法论与自查表）、`README.md`（规则锚点表）、
`SELFTEST.md`（基准与增益测量协议）、`templates/deliverable_templates.md`（矩阵与证据表骨架）、
`examples/case.json`（内联最小示例）、`environment/resources.yaml`（入口与运行时声明）。

复算与自检入口：

```bash
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare  --input /input --output /app/output --work /app/work
```

`selfcheck` 逐项核对产物齐全与契约回填；`compare` 把「基线散文 vs 结构化判定」写到
work 目录的 `compare_report.json`。`result.json` 规范化哈希＝删除环境相关键 `runtime` 与
`artifacts` 后 `sort_keys` 紧凑序列化取 `sha256` 前 16 位，任何评审者可独立复算。

---

## 6. 完整虚构案例（全部虚构，禁止复用为正式答案）

**案例 ID**：`case_001`。**研究设想**：通过氮掺杂 MXene 表面改性提升锂离子电池负极循环稳定性。
**输入材料**：9 篇 PDF（paper_01 至 paper_09），时间窗 2018–2024，证据范围限定为 provided_papers。

`/input/case.json`：

```json
{
  "case_id": "case_001",
  "task": "评估以下研究设想的创新性与可行性：通过氮掺杂MXene表面改性提升锂离子电池负极循环稳定性。",
  "materials": ["/input/papers/paper_01.pdf", "paper_02.pdf", "paper_09.pdf"],
  "constraints": {"time_window": "2018-2024", "evidence_scope": "provided_papers"}
}
```

**关键中间量**

- 检索式：在 9 篇 PDF 中检索 `MXene AND nitrogen doping AND lithium ion battery AND cycling stability`。
- 筛选标准：纳入研究性论文；排除综述、会议摘要、非锂电应用。结果：9 篇中纳入 7 篇，
  排除 paper_02（综述）与 paper_08（非锂电应用）。
- 证据矩阵：7 行，字段完整 6 行，paper_07 缺评价方式 → EC = 6/7 = **85.7%**。
- 关键判断 10 条，9 条带 locator → VR = **90%**。
- 冲突证据 2 条：paper_04 报告氮掺杂降低导电性，paper_06 报告无显著提升；登记 2 条 → CRR = **100%**。
- 创新点 3 条：① 氮掺杂 MXene 表面改性方法（方法创新）→ 与 paper_03 比对，已被报道，状态 `covered`；
  ② 特定氮掺杂比例优化（数据创新）→ paper_05 报道不同比例，状态 `partially_covered`；
  ③ 应用于高倍率长循环场景（场景迁移）→ 未检索到直接证据，状态 `not_covered`。NRR = 1/3 = **33.3%**。
- 可行性前提 5 个：数据可得性（来源 paper_03）、实验条件（来源 paper_03 方法可重复）为 `source`；
  算力（需 DFT）、时间窗口（6 个月）、人员能力为 `assumed` → FSR = 2/5 = **40%**。
- SR = **1**（检索式完整记录）。

`/app/output/result.json` 片段：

```json
{
  "case_id": "case_001",
  "status": "partial",
  "deliverable": "decision_brief.md",
  "evidence_map": "evidence_index.jsonl",
  "change_log": "change_log.json",
  "coverage": "coverage.json",
  "sources": ["paper_01", "paper_03", "paper_04", "paper_05", "paper_06", "paper_07", "paper_09"],
  "uncertainty": {
    "conflicts": ["paper_04 报告氮掺杂降低导电性", "paper_06 报告无显著提升"],
    "gaps": ["高倍率长循环场景无直接证据"],
    "unverifiable": ["算力、时间窗口、人员能力为假设"]
  },
  "change_records": [{"step": "S3", "action": "补全 paper_07 评价方式字段", "reason": "字段缺失导致 EC 未达阈值"}],
  "main_result": {
    "problem_statement": "研究对象=MXene负极；关键变量=氮掺杂比例；比较基线=未掺杂MXene；预期结论=氮掺杂提升循环稳定性；可证伪条件=1000圈容量保持率无显著差异则否定。",
    "novelty": "方法创新已被覆盖；数据创新部分覆盖；场景迁移未覆盖。",
    "feasibility": "数据与实验条件有来源；算力、时间、人员为假设，存在风险。",
    "overall_verdict": "conditional"
  }
}
```

对齐矩阵示例行：

```csv
claim_id,source_id,source_locator,task,method,data,evaluation,overlap,comparison_status,boundary_note
"C1","paper_03","M1/p2","氮掺杂MXene负极","水热法+氮掺杂","1 A/g下500 mAh/g","循环稳定性","full","comparable","与既有工作实质重复，不足以支撑方法创新"
```

综合结论摘要：**事实**——paper_03 报道氮掺杂 MXene 在 1 A/g 下 500 mAh/g、1000 圈容量保持率 85%；
**推断**——氮掺杂比例优化可能进一步提升稳定性（基于 paper_05 趋势）；**无法确定**——高倍率长循环
场景无直接证据。自检输出：`EC=85.7% (partial) / VR=90% (partial) / CRR=100% (pass) /
NRR=33.3% (info) / FSR=40% (partial) / SR=1 (pass)`，故整体判为 `partial` 并说明未达阈值的 limits。

---

## 7. 防扣分自查表（交付前逐项通过）

- [ ] C01 是否读取了实际输入文件而非依赖领域标签？
- [ ] C02 `result.json` 是否含 `case_id` 与全部契约字段，且逐键非空？
- [ ] C03 四项交付（问题定义、已有工作比较、创新点识别、可行性判断）是否齐全且相互一致？
- [ ] C04 每条关键判断是否有 locator（文献 ID + 段落/表/图）？
- [ ] C05 是否区分了材料事实、合理推断、无法确定？
- [ ] C06 是否登记了冲突证据并说明取舍？
- [ ] C07 是否记录了检索式、筛选标准、纳排理由？
- [ ] C08 每条创新点是否判定覆盖状态并给出对比文献？
- [ ] C09 可行性每个前提是否标注来源或假设？
- [ ] C10 是否统一了单位/量纲后再比较？
- [ ] C11 是否避免了「检索不到=尚无人研究」的错误？
- [ ] C12 是否避免了把场景迁移当理论创新？
- [ ] C13 是否尽早保存了 partial 交付物与中间产物？
- [ ] C14 是否处理了检索为空、文献过少、证据冲突等异常？
- [ ] C15 是否提供了可复现的脚本、模板与复算命令？
- [ ] C16 是否在输出中包含不确定性、偏倚、空白，并限定范围？
- [ ] C17 所有产物是否有可核验形态（人读简报 + 结构化 JSON/CSV，互相一致）？
- [ ] C18 是否在包根目录放置 `GITHUB_URL.txt`，首行为链接、次行为仓库子路径？
- [ ] C19 是否不依赖未说明的个人文件或手工操作？
- [ ] C20 是否写清异常处理与失败处理（空/坏/占位输入 → `insufficient_evidence`，exit 0）？

**门控**：以上任一项未通过，`status` 记为 `partial` 并把未决项写入 `uncertainty`，
绝不静默提升为完整成功。
