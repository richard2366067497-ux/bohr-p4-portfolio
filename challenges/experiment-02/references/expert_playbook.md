# 专家参考手册 · 实验方案可行性评估（plan-feasibility-review）

> 本手册是本 Skill 的核心方法论基准：执行前必读。量化口径、七类检查项体系、定位符格式与
> 输出规范均以本手册为准。与 `SKILL.md` 的契约冲突时：契约键名以 `SKILL.md` 为准，方法/口径
> 以本手册为准。

---

## 1. 任务理解与判分要点

### 1.1 任务本质

本任务交付的是**一份结构化的实验方案可行性审查报告**，而非实验方案本身。核心工作是对给定
实验方案逐条核验七类约束（假设与变量、对照组、设备与材料、时间成本、参数范围、风险与异常、
伦理与安全），产出**可执行的结论**——即"可行""有条件可行（列明全部条件）"或"不可行（列明
阻断原因）"。

### 1.2 评委真正看的四件事

| 序号 | 评委关注点 | 对应评分项 | 满分 |
|------|-----------|-----------|------|
| 1 | 审查是否落到方案具体章节、参数和清单行 | 任务完成度 + 结果正确性 | 30 |
| 2 | 结论是否可执行（"有条件可行"写清全部条件） | 结果正确性 + 质量增益 | 20 |
| 3 | 同一方案换人复跑能否得到可比结论 | 结果可核验性 + 运行稳定性 | 9 |
| 4 | 是否把"方案没写"误当成"方案满足" | 结果完整性 + 异常处理 | 8 |

### 1.3 常见失败模式（错误做法 → 正确做法）

| # | 错误做法 | 正确做法 |
|---|---------|---------|
| F1 | 只评"技术路线是否合理"，不查设备/材料/时间约束 | 七类约束逐项核验，每项标注信息来源 |
| F2 | 方案未提及的设备默认为"已具备" | 方案未提及的设备标注为"信息缺失—需确认"，列入确认项 |
| F3 | 时间估算给一个总数（如"约 3 个月"），无拆分依据 | 按步骤拆分：设备占用 h×批次 + 等待周期 d + 检测周转 d，给出计算公式 |
| F4 | 风险只写"可能出现偏差，建议注意" | 风险写明触发条件、概率等级、降级路径和转人工节点 |
| F5 | 伦理审查写"需通过伦理审批"即止 | 明确审批层级（IRB/IACUC/IBC）、所需材料清单、预估审批周期 |
| F6 | 审查结论无原文定位，无法复核 | 每条判断附 locator：`[方案 section X.Y, 第Z段/表N, 第R行]` |
| F7 | 参数范围只写"参考文献"，不给出具体数值区间 | 给出参数区间、来源文献 DOI/页码、超出区间的后果 |
| F8 | 对照设计仅写"设置空白对照" | 明确对照组类型（阴性/阳性/溶剂/sham）、样本量、统计功效要求 |
| F9 | 输出仅一段文字总结 | 输出结构化 JSON + 可读 Markdown，含字段、状态码和证据链 |
| F10 | 对方案自相矛盾之处未识别 | 交叉核验：方法段参数 vs. 设备清单规格 vs. 时间表中工时，矛盾处标记 `[CONFLICT]` |

---

## 2. 求解框架：从输入到交付的分步流程

### 流程总览

```
输入(case.json + task.md + 附件)
  -> Step 1: 材料解析与结构化提取
  -> Step 2: 七类约束逐项审查
  -> Step 3: 交叉核验与冲突检测
  -> Step 4: 结论综合与条件清单
  -> Step 5: 输出组装与自核验
-> 输出(result.json + review_report.md + 附件)
```

> 映射到本 Skill：Step 1↔`evidence.json`（source_id/locator/quote）；Step 2↔`checks.json`
> 逐版本×逐类别状态台账；Step 3↔`risks.json` 与冲突项；Step 4↔`confirmations.json` 与结论；
> Step 5↔`feasibility_review.md`/`version_diff.md`/`result.json` 与自检。

### Step 1：材料解析与结构化提取

**输入**：case.json（含 case_id、task_prompt、constraints）、task.md、附件（PDF/DOCX/表格）。

**操作**：
1. 读取 case.json，提取 `case_id`、`research_objective`、`candidate_plans[]`（若有多个候选方案）、`resource_inventory`（设备/材料清单）、`organizer_constraints`（组织方给定的资源/价格/排期合同）。
2. 对 PDF 附件使用 parse_pdf 提取文本；对表格提取行列数据。
3. 将方案文本按章节切分，建立章节索引：`{section_id, title, line_range, content}`。

**冻结产物**：`parsed_protocol.json` — 含章节索引、参数提取表、设备提及清单、材料提及清单。

**门控**：所有后续步骤的引用必须使用 `section_id` + 行号，禁止使用模糊描述。

### Step 2：七类约束逐项审查

对以下七类逐一执行，每类产出 `check_items[]`：

| 类别 | 检查项数量 | 核心检查内容 |
|------|-----------|-------------|
| C1 假设与变量 | 4-8 项 | 研究假设是否可检验、自变量/因变量是否明确、混淆变量是否识别 |
| C2 对照组 | 3-6 项 | 对照类型、样本量、随机化/盲法、统计功效 |
| C3 设备与材料 | 6-12 项 | 型号匹配、精度满足、耗材规格、供货状态（已具备/可外协/需采购/不具备） |
| C4 时间成本 | 4-8 项 | 按步骤工时拆分、设备排期、材料货期、检测周转 |
| C5 参数范围 | 4-8 项 | 参数区间、来源依据、容差分析、越界后果 |
| C6 风险与异常 | 4-8 项 | 故障场景、概率、降级路径、替代方案、转人工节点 |
| C7 伦理与安全 | 3-6 项 | 审批类型、所需材料、预估周期、危险试剂/生物安全等级 |

每项检查产出结构：

```json
{
  "item_id": "C3-04",
  "category": "C3",
  "check_point": "XRD 设备型号与方案要求匹配",
  "protocol_ref": "section 3.2 table 2, row 5",
  "finding": "方案要求 Cu Ka (lambda=1.5406 A)，清单中 Rigaku SmartLab 满足",
  "status": "PASS",
  "evidence": "resource_inventory.equipment[3].model = SmartLab 9kW",
  "action_required": "",
  "confidence": "high"
}
```

`status` 取 `PASS | FAIL | MISSING_INFO | CONFLICT | CONDITIONAL` 之一。

**冻结产物**：`check_results.json` — 全部检查项结果。

**门控**：`MISSING_INFO` 状态的检查项不得在结论中被默认为 PASS。

### Step 3：交叉核验与冲突检测

**操作**：
1. 方法段参数 vs. 设备能力：方案要求温度 1200 C，设备清单中炉子最高 1100 C -> 标记 `[CONFLICT]`。
2. 时间表 vs. 工时累计：各步骤工时之和 > 时间表总工期 -> 标记 `[CONFLICT]`。
3. 样本量 vs. 材料供给：方案要求 n=30，材料清单仅提供 20 份 -> 标记 `[CONFLICT]`。
4. 伦理审批周期 vs. 项目时间线：审批预估 8 周，项目启动在第 4 周 -> 标记 `[RISK]`。

**冻结产物**：`conflict_log.json`。

**门控**：任何 `CONFLICT` 必须在最终结论中被显式处理（解决或列为阻断项）。

### Step 4：结论综合与条件清单

**综合判定逻辑**：

```
若存在 status=FAIL 且无降级路径 -> 结论 = "NOT_FEASIBLE"
若存在 status=CONDITIONAL 或 MISSING_INFO -> 结论 = "CONDITIONALLY_FEASIBLE"
若全部 PASS -> 结论 = "FEASIBLE"
```

**条件清单**（仅 CONDITIONALLY_FEASIBLE 时生成）：

```json
{
  "conditions": [
    {
      "condition_id": "COND-01",
      "description": "需采购高温炉（最高 1300 C），预计货期 6-8 周",
      "blocking_items": ["C3-07"],
      "estimated_resolution_time": "8 weeks",
      "responsible_party": "课题组设备管理员"
    }
  ]
}
```

**冻结产物**：`conclusion.json`（本 Skill 落地为 `result.json` 的结论/待确认段 + `confirmations.json`）。

### Step 5：输出组装与自核验

**输出文件清单**（映射到本 Skill 的 `--output`）：
1. `result.json` — 主结果文件，含全部契约字段。
2. `feasibility_review.md` — 可读审查报告（即手册所称 review_report.md）。
3. `checks.json` — 完整检查项明细（逐版本 × 逐类别状态码）。

**自核验伪代码**：

```python
for item in check_results:
    assert item["protocol_ref"] is not None
    if item["status"] == "MISSING_INFO":
        assert item["item_id"] not in conclusion["passed_items"]
for conflict in conflict_log:
    assert conflict["conflict_id"] in conclusion["addressed_conflicts"]
assert abs(time_total - sum(step_hours)) < 0.5
```

**门控**：自核验全部通过后方可输出。

---

## 3. 专家方法与量化口径

### 3.1 时间估算方法

**公式**：

```
T_total = SUM(T_setup_i + T_run_i * N_batch_i + T_wait_i + T_QC_i) + T_procurement + T_approval
```

其中：
- `T_setup_i`：第 i 步设备调试时间（h）
- `T_run_i`：单批次运行时间（h）
- `N_batch_i`：批次数 = ceil(样本量 / 单批处理量)
- `T_wait_i`：步骤间等待/冷却/平衡时间（h）
- `T_QC_i`：质检时间（h）
- `T_procurement`：采购货期中最长者（d）
- `T_approval`：审批周期（d）

**示例**：方案要求合成 30 个样品，每炉处理 5 个，单炉运行 8h，调试 2h，QC 1h/批。

```
N_batch = ceil(30/5) = 6
T_synthesis = (2 + 8*6 + 1*6) = 2 + 48 + 6 = 56 h = 7 个工作日
```

> 本 Skill 中时长以步骤行求和写进 `estimate.json`（步骤行之和 = 单次时长），并做算术自检。

### 3.2 样本量估算

**统计功效法**（适用于对照实验）：

```
n_per_group = 2 * ((Z_alpha/2 + Z_beta) / delta)^2 * sigma^2
```

- alpha = 0.05（双侧），Z_alpha/2 = 1.96
- beta = 0.20（功效 80%），Z_beta = 0.842
- delta = 最小可检测效应量
- sigma = 标准差估计

**示例**：delta = 0.5*sigma（中等效应量）

```
n = 2 * ((1.96 + 0.842) / 0.5)^2 * 1 = 2 * (5.604)^2 = 2 * 31.4 = 62.8 -> 63/组
```

若方案写 n=10/组，审查意见：样本量不足以检测中等效应量（需 63/组），需专家确认 delta 和 sigma
的估计来源。

### 3.3 设备能力匹配度

| 项目 | PASS | CONDITIONAL | FAIL |
|------|------|-------------|------|
| 量程覆盖 | 设备量程 >= 方案参数范围*1.2 | 设备量程 >= 方案参数范围 | 设备量程 < 方案参数范围 |
| 精度/分辨率 | 设备精度 <= 方案要求精度 | 设备精度在方案要求 1-2 倍内 | 设备精度 > 方案要求 2 倍 |
| 附件兼容 | 所需附件全部在清单中 | 附件需额外采购但有货 | 附件不可获得 |

### 3.4 风险等级量化

| 等级 | 概率 | 影响 | 处置要求 |
|------|------|------|---------|
| R1-低 | <5% | 可忽略 | 记录即可 |
| R2-中 | 5-20% | 延误 1-2 周 | 需有降级路径 |
| R3-高 | 20-50% | 延误 >2 周或数据作废 | 需有替代方案 + 触发条件 |
| R4-关键 | >50% | 项目无法继续 | 阻断项，需解决后方可启动 |

### 3.5 伦理审批周期参考

| 审批类型 | 典型周期 | 所需材料 |
|----------|---------|---------|
| IRB（人体样本/数据） | 4-12 周 | 知情同意书、研究方案、PI 简历、伦理培训证书 |
| IACUC（动物实验） | 4-8 周 | 动物使用方案、3R 论证、人员培训记录 |
| IBC（重组 DNA/生物危害） | 2-6 周 | 风险评估表、BSL 等级确认、废物处置方案 |
| 危化品使用审批 | 1-4 周 | MSDS、存储方案、应急预案、使用登记 |

---

## 4. 领域知识清单

### 4.1 常见事实性错误

| # | 错误 | 正确 |
|---|------|------|
| K1 | 将 SEM 和 TEM 混用（"用 SEM 观察晶格条纹"） | 晶格条纹需 TEM（分辨率 <0.2 nm），SEM 分辨率通常 1-10 nm |
| K2 | XRD Cu Ka 波长写成 1.5418 A（加权平均，非 Ka1） | Cu Ka1 = 1.5406 A；Cu Ka（加权平均）= 1.5418 A，需明确使用哪个 |
| K3 | 将"分析纯"与"色谱纯"混为一谈 | 分析纯（AR）纯度 >=99.5%，色谱纯（HPLC）纯度 >=99.9% 且 UV 吸收低 |
| K4 | 手套箱水氧指标写"<1 ppm"但无净化系统说明 | 需注明催化剂类型（铜触媒/分子筛）、再生周期 |
| K5 | 马弗炉最高温度 = 长期使用温度 | 最高温度通常仅可短时（<1h）使用，长期工作温度应低 100-200 C |
| K6 | 将细胞培养"代次"与"传代次数"混淆 | P5 表示第 5 代，但可能已经历 >5 次传代（取决于初始接种比） |
| K7 | BET 比表面积测试前未注明脱气条件 | 必须注明脱气温度、时间、真空度（如 200 C/6h/10^-3 Pa） |
| K8 | 将"室温"等同于 25 C | 室温范围 15-30 C，对温度敏感实验需恒温控制 |

### 4.2 单位与量纲陷阱

| 陷阱 | 说明 |
|------|------|
| rpm vs. rcf | 离心条件应标明 xg（rcf），不同转子 rpm 对应不同 rcf：rcf = 1.118e-5 * r(mm) * rpm^2 |
| mol/L vs. wt% | 溶液浓度换算需密度，浓硫酸 98 wt% = 18.4 mol/L（rho=1.84 g/mL） |
| sccm vs. mL/min | sccm 是标准状态（0 C, 1atm）下的体积流量，与实际 mL/min 不同 |
| W vs. W/cm2 | 激光功率（W）与功率密度（W/cm2）差 2-4 个量级 |
| Pa vs. Torr vs. mbar | 1 atm = 101325 Pa = 760 Torr = 1013.25 mbar |
| mg/mL vs. mg/L (ppm) | 浓度差 1000 倍，光催化/环境检测中易混淆 |

### 4.3 文献依据要求

- 参数范围引用文献时，必须给出 DOI 或期刊卷期页码，不可仅写"参考文献 [X]"。
- 若方案引用综述而非原始方法文献，需标注"二次引用，原始方法见 [原始文献]"。
- 对于设备参数（如检测限、线性范围），优先引用设备厂商技术手册而非文献值。
- 对组织方给定的约束（价格/排期/资源合同），直接引用 `[组织方约束 constraints.{key}]`，不需额外文献。

---

## 5. 高质量交付物清单

### 5.1 必须交付的文件（映射到本 Skill 的产物）

| 文件 | 内容 | 自证可核验方法 |
|------|------|--------------|
| `result.json` | 结构化主结果，含 case_id、conclusion、check_items、conditions、conflicts | 每条 check_item 含 `protocol_ref`（locator）和 `evidence`（引用原文或清单字段） |
| `feasibility_review.md` | 可读审查报告，含执行摘要、逐类审查表、条件清单、风险矩阵 | 每条判断可追溯到 result.json 中的 item_id |
| `checks.json` | 全量检查项明细，便于第三方复核 | 含 item_id, category, check_point, status, protocol_ref, evidence, action_required |
| `estimate.json` | 时间估算拆分表 | 含每步公式、参数来源、计算过程，可独立复算 |
| `confirmations.json` | 审查过程待确认与变更记录 | 含 timestamp/内容/原因，或待关闭的确认项 |

### 5.2 result.json 字段规范

```json
{
  "case_id": "string (required)",
  "conclusion": "FEASIBLE | CONDITIONALLY_FEASIBLE | NOT_FEASIBLE",
  "summary": "string, <=200 chars",
  "check_items": [],
  "conditions": [],
  "conflicts": [],
  "time_breakdown": {},
  "risk_matrix": [],
  "ethics_path": {},
  "missing_info": [],
  "expert_confirmation_required": []
}
```

### 5.3 定位器（Locator）格式规范

```
[方案 section {section_id}, {paragraph/table/figure}{number}, line {line}]
[资源清单 {table_name}.{row_id}.{field}]
[组织方约束 constraints.{key}]
```

示例：
- `[方案 section 3.2, table 2, line 5]` — 指向方案第 3.2 节表 2 第 5 行
- `[资源清单 equipment.3.model]` — 指向设备清单第 3 条的型号字段
- `[组织方约束 pricing.reagent_NaOH]` — 指向组织方给定的 NaOH 价格约束

---

## 6. 防扣分自查表（专家检查表）

以下 18 项逐条勾选，全部通过后方可提交：

- [ ] **S01** 每条审查判断都有 locator 指向方案原文或资源清单具体位置
- [ ] **S02** `MISSING_INFO` 状态的检查项未被默认为 PASS
- [ ] **S03** 所有 `CONFLICT` 都在结论中被显式处理（解决或列为阻断项）
- [ ] **S04** 时间估算按步骤拆分，非单一总数
- [ ] **S05** 时间估算公式中每个参数都标注了来源（设备手册/SOP/经验值/组织方约束）
- [ ] **S06** 样本量估算给出了统计依据（功效分析或经验法则），非"参考同类研究"
- [ ] **S07** 设备匹配检查区分了"已具备/可外协/需采购/不具备"四种状态
- [ ] **S08** 风险项包含触发条件、概率等级、降级路径三个要素
- [ ] **S09** 伦理审查明确了审批类型、所需材料清单、预估周期
- [ ] **S10** 参数范围给出了具体数值区间（非"适当范围"），并标注来源
- [ ] **S11** 对照组设计明确了类型、样本量、统计功效要求
- [ ] **S12** 方案未提及的信息被显式标记为"方案未涉及"，未被默认满足
- [ ] **S13** 结论为"有条件可行"时，条件清单完整（每个条件含描述、关联检查项、预估解决时间）
- [ ] **S14** result.json 含 case_id、run_metadata、input_hash
- [ ] **S15** 输出文件可通过自核验脚本（Step 5）全部检查
- [ ] **S16** 未发现将"方案没写"误判为"方案满足"的情况
- [ ] **S17** 参数单位已统一（rpm/rcf、Pa/Torr、mol/L/wt% 等已换算）
- [ ] **S18** 方案内部自相矛盾之处（方法段 vs. 设备清单 vs. 时间表）已被识别并标记

---

## 7. 完整案例演示：溶胶-凝胶法 TiO2 光催化方案可行性审查

### 7.1 输入

**case_id**: `demo-case-001`

**研究目标**：通过溶胶-凝胶法合成 TiO2 纳米颗粒，研究煅烧温度（400-800 C）对光催化降解亚甲基蓝效率的影响。

**方案摘要**：
- section 2.1 原料：钛酸四丁酯（TBOT, AR 级）、无水乙醇、去离子水、HCl（0.1M）
- section 2.2 合成：TBOT:EtOH:H2O = 1:4:2（摩尔比），60 C 搅拌 2h，陈化 24h
- section 2.3 煅烧：400/500/600/700/800 C 各 2h，升温速率 5 C/min
- section 2.4 表征：XRD（Cu Ka, 10-80 deg, 0.02 deg/step）、SEM、UV-Vis DRS
- section 2.5 光催化：10 mg 催化剂 + 50 mL MB 溶液（10 mg/L），300W Xe 灯，每 15 min 取样测 UV-Vis
- section 3.1 对照：无催化剂空白对照
- section 3.2 每组 3 个平行样

**设备清单**：

| 编号 | 设备 | 型号 | 关键参数 |
|------|------|------|---------|
| E1 | 马弗炉 | Nabertherm LHT 03/17 | 最高 1700 C，炉膛 3L |
| E2 | XRD | Bruker D8 Advance | Cu Ka, 2theta 5-160 deg |
| E3 | SEM | — | 未列入清单 |
| E4 | UV-Vis | Shimadzu UV-2600 | 190-1400 nm |
| E5 | 磁力搅拌器 | IKA RCT | 最高 310 C, 1500 rpm |

**组织方资源约束**：马弗炉排期需提前 2 周预约，每周可用 3 天。

### 7.2 关键中间量计算

**C4 时间估算**：

```
合成：搅拌 2h + 陈化 24h = 26h/批
干燥：100 C 烘箱 12h
煅烧：5 个温度 * (升温 + 保温)
  400 C: (400-25)/5 + 120 = 75 + 120 = 195 min
  500 C: (500-25)/5 + 120 = 95 + 120 = 215 min
  600 C: (600-25)/5 + 120 = 115 + 120 = 235 min
  700 C: (700-25)/5 + 120 = 135 + 120 = 255 min
  800 C: (800-25)/5 + 120 = 155 + 120 = 275 min
  平均 = (195+215+235+255+275)/5 = 235 min/组
  5 组 * 235 min = 1175 min = 19.58 h
  马弗炉每周可用 3 天(24h)，需 1 周完成煅烧
表征：XRD 每个样品 1h * 5 = 5h
  SEM：需外协，周转 2 周
  UV-Vis DRS：每个 30min * 5 = 2.5h
光催化：每组 (5 个时间点 * 15min + 准备 30min) = 105 min = 1.75h
  5 温度 * 1.75h * 3 平行 = 26.25 h

T_total_work = 26 + 12 + 19.58 + 5 + 2.5 + 26.25 = 91.33 h = 11.4 工作日
T_total_calendar = 11.4 工作日 + 14d SEM外协 + 14d 马弗炉预约 = 约 7 周
```

**C2 样本量检查**：

```
每组 n=3 平行样。
假设光催化降解率 sigma = 8%（文献经验值），delta = 15%（400 vs. 800 C 预期差异）：
标准化效应量 d = delta/sigma = 15/8 = 1.875
n = 2 * ((1.96 + 0.842) / 1.875)^2 = 2 * (2.802/1.875)^2 = 2 * (1.494)^2 = 2 * 2.233 = 4.47
需 n=5/组
方案 n=3 不足以达到 80% 功效（实际功效约 48%）。
```

### 7.3 输出（result.json 节选）

```json
{
  "case_id": "demo-case-001",
  "conclusion": "CONDITIONALLY_FEASIBLE",
  "summary": "合成路线和设备匹配性良好，煅烧温度在马弗炉能力范围内。主要条件：(1) SEM 需外协或补充设备信息；(2) 平行样数从 3 增至 5 以满足统计功效；(3) 马弗炉排期需提前 2 周预约。",
  "check_items": [
    {
      "item_id": "C3-01",
      "category": "C3",
      "check_point": "马弗炉温度覆盖方案要求 400-800 C",
      "protocol_ref": "[方案 section 2.3]",
      "finding": "设备 E1 最高 1700 C，长期工作温度 <=1500 C，覆盖 800 C 且有余量（800*1.2=960 < 1500）",
      "status": "PASS",
      "evidence": "[资源清单 equipment.1.max_temp = 1700]",
      "action_required": "",
      "confidence": "high"
    },
    {
      "item_id": "C3-02",
      "category": "C3",
      "check_point": "SEM 设备可用性",
      "protocol_ref": "[方案 section 2.4]",
      "finding": "方案要求 SEM 表征，但设备清单中 E3 未列入具体型号和参数",
      "status": "MISSING_INFO",
      "evidence": "[资源清单 equipment.3.model = 未声明]",
      "action_required": "确认 SEM 设备型号、分辨率、是否需外协",
      "confidence": "high"
    },
    {
      "item_id": "C2-01",
      "category": "C2",
      "check_point": "平行样数满足统计功效",
      "protocol_ref": "[方案 section 3.2]",
      "finding": "n=3/组，功效分析显示需 n=5/组（delta=15%, sigma=8%, alpha=0.05, power=0.80）",
      "status": "FAIL",
      "evidence": "计算过程见 time_breakdown power_analysis 段",
      "action_required": "将平行样数增至 5，或专家确认 delta 和 sigma 的估计来源",
      "confidence": "medium"
    },
    {
      "item_id": "C2-02",
      "category": "C2",
      "check_point": "空白对照设置",
      "protocol_ref": "[方案 section 3.1, line 1]",
      "finding": "已设置无催化剂空白对照，可排除 MB 自降解和光解贡献",
      "status": "PASS",
      "evidence": "[方案 section 3.1, line 1]",
      "action_required": "",
      "confidence": "high"
    },
    {
      "item_id": "C5-01",
      "category": "C5",
      "check_point": "煅烧升温速率依据",
      "protocol_ref": "[方案 section 2.3]",
      "finding": "升温速率 5 C/min 在文献常见范围 2-10 C/min 内，但方案未给出引用来源",
      "status": "CONDITIONAL",
      "evidence": "方案未引用文献",
      "action_required": "补充升温速率的文献依据，或确认 5 C/min 对产物晶型的影响已评估",
      "confidence": "medium"
    }
  ],
  "conditions": [
    {
      "condition_id": "COND-01",
      "description": "确认 SEM 设备可用性（自有或外协），若外协需纳入 2 周周转时间",
      "blocking_items": ["C3-02"],
      "estimated_resolution_time": "1-2 weeks",
      "responsible_party": "课题组设备管理员"
    },
    {
      "condition_id": "COND-02",
      "description": "平行样数从 3 增至 5（或专家论证 n=3 的统计依据）",
      "blocking_items": ["C2-01"],
      "estimated_resolution_time": "方案修改 1d + 额外实验约 3d",
      "responsible_party": "PI 确认"
    }
  ],
  "conflicts": [],
  "missing_info": [
    "SEM 设备型号与参数",
    "煅烧升温速率的文献依据",
    "TBOT 供应商与货期",
    "Xe 灯型号与光强均匀性参数"
  ],
  "expert_confirmation_required": [
    "n=3 平行样是否可接受（需提供 delta 和 sigma 的领域经验估计）",
    "5 C/min 升温速率对锐钛矿/金红石比例的影响是否已评估"
  ],
  "risk_matrix": [
    {
      "risk_id": "R-01",
      "description": "马弗炉排期冲突导致煅烧延后",
      "probability": "R2-中 (15%)",
      "impact": "延误 1-2 周",
      "mitigation": "提前 3 周预约，备选外校马弗炉"
    },
    {
      "risk_id": "R-02",
      "description": "TBOT 水解速率受环境湿度影响，批次间差异",
      "probability": "R2-中 (10%)",
      "impact": "溶胶凝胶时间偏差 +-20%",
      "mitigation": "在手套箱或干燥间操作，记录湿度"
    }
  ]
}
```

### 7.4 数字自核验

| 检查 | 计算 | 结果 |
|------|------|------|
| 煅烧平均时间 | (195+215+235+255+275)/5 = 235 min | 与 time_breakdown 一致 |
| 煅烧总时间 | 5 * 235 = 1175 min = 19.58h | 一致 |
| 光催化总时间 | 5 * 3 * 1.75 = 26.25h | 一致 |
| 总工时 | 26+12+19.58+5+2.5+26.25 = 91.33h = 11.4 工作日 | 一致 |
| 总周期 | 11.4 工作日 + 14d SEM + 14d 预约 = 约 7 周 | 一致 |
| 功效分析 | n = 2*(2.802/1.875)^2 = 2*2.233 = 4.47 -> 5 | 一致 |
| 设备余量 | 800*1.2 = 960 < 1500（长期工作温度） | PASS 判定正确 |

---

> **交付前门控**：用第 6 节专家检查表（S01–S18）逐项核验，全部通过后方可交付。
