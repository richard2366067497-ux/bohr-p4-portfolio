## 任务理解与判分要点

### 真正要交付什么

本任务要求提交一个**可被平台加载并实际运行的 Skill 包**，而不是三个案例的预制答案。Skill 运行后，对每个固定案例返回结构化结果：`result.json` 含 `case_id`、主结果、证据/来源定位、运行状态、不确定性。核心能力是“公式解析与数学推理”：从真实论文 PDF/XML 中识别公式、解释变量、说明推导、数值核验，并让每个关键结论都能回到原文位置。

评委实际看五件事：

1. **实际效果（40分）**：是否真的把公式图像/PDF/XML 转成可校验的 LaTeX 或等价结构，并交付变量表、推导说明、数值核验；符号、上下标、括号、希腊字母、单位是否一一对应；是否覆盖声明公式的完整信息；每个符号定义、每步推导、每次代入能否复跑。
2. **使用增益（25分）**：加载 Skill 后相比基础 Agent，质量是否提升、是否减少回原文找定义和手工比对、是否通过公平对照证明增益。
3. **创新增益（15分）**：是否形成基础 Agent 不具备的稳定能力，例如符号一致性约束、单位量纲检查、推导依赖图、数值复算闭环；是否有证据证明边界和价值。
4. **可靠体验（10分）**：调用是否顺畅、重复运行是否稳定、对模糊/截断/歧义/单位缺失/代入无解等异常是否诚实处置。
5. **生态贡献（10分）**：文档、脚本、模板、示例是否齐全可复用；是否沉淀可分享的公式案例或核验脚本。

### 常见失败模式：错误做法 → 正确做法

| 错误做法 | 正确做法 |
|---|---|
| 只贴一段 LaTeX，没有变量表、推导、核验 | 每个公式配套变量表、推导步骤、边界条件、数值复算或不可算说明 |
| 变量按常识猜测后写进变量表，不区分来源 | 每个符号给出原文 locator；区分“原文定义 / 上下文推断 / 常识补充”，推断项显式标记 |
| 推导只写“显然可得”“整理得” | 每步标明依据：引用公式编号、文字段落或数学规则；无法判断写 `insufficient_evidence` |
| 数值代入不复算，或只写最终结果 | 给出中间值、单位转换、相对偏差、成立范围；可复跑命令 |
| 把 C02 缺失的公式/数据填 0 或反推 | 报告 `partial` 或 `insufficient_evidence`，明确“材料未报告，无法复算” |
| 把 `source-formulas.xml` 当成线性化答案或推导 | 仅作为公式节点来源，仍需从原文核对符号、单位、定义位置 |
| 不保留页码/段落/公式编号 | 每个关键结论附 locator，如 `C01 PDF p.3 left col. para 2, Eq.(4)` |
| 运行状态只写 success，掩盖部分失败 | 如实写 `success / partial / insufficient_evidence / failed`，说明原因和可人工接管位置 |
| 用预制答案冒充运行结果 | Skill 必须从实际输入文件实时解析；示例输出必须标注“示例” |
| 忽略单位量纲，kJ 与 J 混用 | 所有数值代入前统一单位，给出量纲检查步骤 |
| 不检查上下标、希腊字母、括号层级 | 用符号一致性检查脚本逐项比对原文与 LaTeX |
| 输出不可复跑 | 保留输入文件路径、脚本命令、中间值 CSV、核验日志 |

## 求解框架

从输入材料到交付物，分六步。每步有冻结产物和门控条件，未通过门控不得进入下一步。

### Step 0：读取输入与资源清单

**输入**：`/input/case.json`、`/input/task.md`、`/input/artifacts/` 下的实际 PDF/XML；`environment/resources.yaml` 列出的工具与资源。

**动作**：读取 case_id、任务要求、材料路径；检查文件是否存在、可读；识别公式来源类型：C01/C03 有 `publisher-source.xml` 和 `source-formulas.xml`，C02 可能无公式表示。

**冻结产物**：`input_inventory.json`，含文件清单、可读性、公式节点数量、缺失项。

**门控**：所有必需文件路径有效；缺失项已记录；未假设材料内容。

### Step 1：公式识别与结构化

**动作**：从 PDF 或 XML 提取目标公式，输出 LaTeX 或等价结构化表达。对 XML 中的 MathML 节点，保留分式、上下标、来源 ID；对 PDF 图像，用 OCR/人工可读方式还原，并标记不确定字符。

**冻结产物**：`formulas.json`，每个公式含 `formula_id`、`latex`、`source_locator`、`confidence`、`raw_mathml_id`（如有）。

**门控**：每个公式有唯一编号或位置；上下标、括号层级、希腊字母与原文逐项比对通过；不确定字符已标记。

### Step 2：变量解释

**动作**：对每个公式中的每个符号，建立变量表。字段：符号、定义、单位、取值范围、首次定义位置、来源类型（原文定义/上下文推断/常识补充）。

**冻结产物**：`variables_table.md` 或 `variables.json`。

**门控**：每个变量至少有一个 locator 或显式标记为推断；单位与原文一致；无量纲量明确标注。

### Step 3：推导说明

**动作**：对关键推导拆成可检查步骤。每步标明：依据（公式编号/文字段落/数学规则）、假设、近似、边界条件、跨公式依赖。

**冻结产物**：`derivation.md`，含步骤列表、依赖图、假设清单。

**门控**：每步有依据或标记 `insufficient_evidence`；假设与边界条件不遗漏；跨公式引用可回溯。

### Step 4：数值核验

**动作**：对可计算公式，代入原文数值复算。统一单位，给出中间值、相对偏差、成立范围。对不可算公式，说明原因（缺数据、缺公式、符号歧义等）。

**冻结产物**：`verification.csv` 或 `verification.md`，含输入值、中间值、计算值、原文值、偏差、结论。

**门控**：所有数值有原文 locator；单位转换正确；偏差在可接受范围内或已解释；不可算项已报告 `partial`。

### Step 5：结果复核与输出

**动作**：汇总主结果、证据、不确定性、运行状态，生成 `result.json` 和可编辑产物（如 Markdown 表格、CSV、PDF/PNG 预览）。保留变更记录。

**冻结产物**：`/app/output/result.json`、`/app/output/` 下的可编辑文件及预览。

**门控**：`result.json` 含所有 `output_contract` 字段和 `case_id`；关键结论可回到原文；状态诚实；无预制答案。

## 专家方法与量化口径

### 关键指标定义

1. **公式还原准确率**  
   定义：`1 - (错误符号数 / 总符号数)`。  
   错误符号计数规则：上下标错位、括号缺失或错配、希腊字母替换（如 ν→v）、单位错位、分式线性化错误，各计 1 处；同一符号多处错误只计 1 处。  
   目标：100%。可接受波动：0 错误。因为公式解析要求一一对应，任何符号错误都直接影响正确性。

2. **变量定义覆盖率**  
   定义：`有原文 locator 的变量数 / 变量总数`。  
   目标：100%。推断项占比 ≤ 10%，且必须显式标记为“上下文推断”或“常识补充”，不得与原文定义混同。

3. **推导步骤可核验率**  
   定义：`有依据的推导步骤数 / 总推导步骤数`。  
   目标：100%。无法判断的步骤必须标记 `insufficient_evidence`，不计入“有依据”，但计入总步骤，因此该指标反映诚实度而非推导完整度。

4. **数值复算相对偏差**  
   定义：`|计算值 - 原文值| / |原文值| × 100%`。  
   可接受波动：≤ 0.5%，或原文有效数字末位 ±1 以内。若原文只给 2 位有效数字，偏差 ≤ 0.5% 通常可接受；若原文给 4 位有效数字，偏差应 ≤ 0.05%。

5. **单位一致性检查**  
   定义：对每个可计算公式，写出量纲方程，检查左右量纲是否一致。  
   示例：`E = h c / λ`，量纲 `J·s × m/s ÷ m = J`，通过。  
   若量纲不一致，必须报告 `unit_error`，不得强行复算。

### 计算示例（数字自洽）

**案例**：阿伦尼乌斯方程 `k = A exp(-Ea/(R T))`。  
原文给出：`A = 2.5×10^13 s^-1`（p.4 Table 1），`Ea = 85 kJ/mol`（p.4 text），`T = 350 K`（p.5 experimental），`R = 8.314 J/(mol·K)`（p.3 Nomenclature）。  
单位转换：`Ea = 85 kJ/mol = 85000 J/mol`。  
中间量：`-Ea/(R T) = -85000 / (8.314 × 350) = -85000 / 2909.9 = -29.21`。  
`exp(-29.21) = 2.03×10^-13`。  
计算值：`k = 2.5×10^13 × 2.03×10^-13 = 5.075 s^-1`。  
原文报告 `k = 5.1 s^-1`（p.5 Table 2）。  
相对偏差：`|5.075 - 5.1| / 5.1 × 100% = 0.49%`。  
结论：在原文 2 位有效数字末位 ±1 范围内，复算通过。

## 领域知识清单

### 容易犯的事实性错误

- 把数学符号按常识解释，不看原文定义。例如 `T_c` 可能是临界温度、居里温度或冷端温度，必须回到原文。
- 混淆变量与常量。例如 `R` 可能是理想气体常数、电阻或反应速率，必须查原文 Nomenclature。
- 忽略下标含义。`x_i` 与 `x^i` 不同；`ρ` 与 `p` 不同；`ν`（nu）与 `v` 不同；`ω` 与 `w` 不同。
- 把无量纲数当成有量纲量。例如雷诺数 `Re`、普朗特数 `Pr` 无量纲，不应写单位。
- 忽略分段函数的条件。例如 `f(x) = { x^2, x≥0; -x^2, x<0 }`，必须保留分段条件。
- 矩阵/向量转置、共轭、厄米共轭符号错位。`A^T`、`A^*`、`A^†` 不可混用。
- 公式编号引用错误。推导中引用 `Eq.(4)` 实际是 `Eq.(5)`，导致证据链断裂。

### 单位/量纲陷阱

- 能量单位：`J`、`kJ`、`eV`、`kcal/mol`。转换：`1 eV = 1.602×10^-19 J`；`1 kcal/mol = 4.184 kJ/mol`。
- 温度：`K` 与 `°C` 不可混用。热力学公式通常用 `K`；温差 `ΔT` 两者数值相同，但绝对温度必须用 `K`。
- 压力：`Pa`、`bar`、`atm`、`Torr`。`1 atm = 101325 Pa = 1.01325 bar = 760 Torr`。
- 浓度：`mol/L` 与 `mol/m^3` 相差 1000 倍。
- 频率：`Hz` 与 `rad/s` 相差 `2π`。
- 电导率、热导率等复合单位，必须写出完整量纲方程检查。

### 文献依据要求

- 每个符号定义必须有原文位置：页码、段落、公式编号、表格编号或 Nomenclature 条目。
- 推导步骤必须引用原文公式编号或文字段落；纯数学变换可引用标准规则，但需说明。
- 数值代入必须使用原文报告的数据，不得从外部数据库或常识补值。
- 材料未报告的对象，必须写 `insufficient_evidence`，不得反推、填 0 或假设典型值。
- C02 若无公式表示、逐条预测或可复算原始数据，则相关推导/复算必须报告 `partial` 或 `insufficient_evidence`，不得编造公式或数据。

## 高质量交付物清单

### Skill 包内文件

| 文件 | 内容要求 | 自证可核验方式 |
|---|---|---|
| `SKILL.md` | YAML frontmatter 含 `name`、`description`；写清用途、适用条件、调用方式、输入输出、异常处理 | 平台能据此加载并执行；描述与提交版本一致 |
| `scripts/` | 实际依赖的脚本，如 `extract_formula.py`、`validate_units.py`、`verify_numeric.py` | 每个脚本有 `--help`；路径相对；无个人文件依赖 |
| `resources/` | 模板、词表、符号约定、单位转换表等 | 文件 UTF-8；总大小 ≤ 2MB；无 symlinks |
| `README.md` 或 `docs/` | 完整调用步骤、输入输出解释、关键方法、适用场景、限制、失败处理、自查方法 | 他人或 Agent 可按说明独立使用 |
| `examples/` | 至少一组输入、调用方式和示意输出，标注“示例” | 示例输出不冒充正式案例结果 |
| `GITHUB_URL.txt` | 第一行 GitHub 链接；如需指定文件，第二行写相对路径 | 未登录 GitHub 浏览器可打开 |

### 每个案例运行后输出

| 文件 | 内容要求 | 自证可核验方式 |
|---|---|---|
| `result.json` | 含 `case_id`、`status`、`main_result`、`evidence`、`uncertainty`、`change_record` 等所有 `output_contract` 字段 | 字段完整；状态诚实；关键结论有 locator |
| `variables_table.md` | 变量表，每个符号有定义、单位、范围、locator、来源类型 | 每个变量可指回原文位置 |
| `derivation.md` | 推导步骤、假设、边界条件、依赖图 | 每步有依据或标记 `insufficient_evidence` |
| `verification.csv` | 数值复算输入值、中间值、计算值、原文值、偏差、结论 | 可复跑；中间值完整 |
| `preview/` | 可编辑 Office/slide/diagram 的 PDF/PNG 预览 | 评审可直接查看，无需打开源文件 |

## 防扣分自查表

- [ ] 每个公式有唯一编号或位置 locator
- [ ] 每个变量有原文定义 locator 或显式标记为推断
- [ ] 上下标、括号层级、希腊字母与原文逐项比对通过
- [ ] 单位与量纲检查通过，无 kJ/J 混用
- [ ] 推导每步有依据或标记 `insufficient_evidence`
- [ ] 数值复算有中间值、相对偏差、成立范围
- [ ] 缺失对象报告 `partial` 或 `insufficient_evidence`，未填 0 或反推
- [ ] `result.json` 含所有 `output_contract` 字段和 `case_id`
- [ ] 运行状态诚实：`success / partial / insufficient_evidence / failed` 与实际情况一致
- [ ] 未使用预制答案或预生成正式输出
- [ ] 文件路径有效，无个人文件依赖，无 symlinks
- [ ] 资源文件 UTF-8，≤50 个，每个 ≤500KB，总 ≤2MB
- [ ] 示例输出标注为“示例”，不冒充正式案例结果
- [ ] GitHub 链接有效，未登录可打开，指向本题作品
- [ ] 异常处理说明清晰：模糊、截断、歧义、单位缺失、代入无解、权限不足
- [ ] 可编辑产物有 PDF/PNG 预览
- [ ] 不编造 benchmark 分数、模型版本、运行时间
- [ ] 保留变更记录，说明哪些是后续改进
- [ ] 关键结论可回到原文：页码、段落、公式编号、表格编号
- [ ] 对 C01/C03 的 XML 公式节点，保留 MathML 分式、上下标和来源 ID；对 C02 缺失分支如实报告

## 一个完整虚构案例演示

> 以下为虚构案例，仅用于演示流程和数字复算，不代表任何真实论文或正式测试案例。

### 输入

`/input/case.json`:
```json
{
  "case_id": "C01-demo",
  "task": "解析论文中的阿伦尼乌斯方程，给出 LaTeX、变量表、推导说明和数值核验。",
  "materials": {
    "pdf": "/input/artifacts/paper.pdf",
    "publisher_source_xml": "/input/artifacts/publisher-source.xml",
    "source_formulas_xml": "/input/artifacts/source-formulas.xml"
  }
}
```

`/input/task.md` 要求：识别 Eq.(4) 的公式，解释所有符号，复算原文报告的速率常数。

### 关键中间量

**Step 1 公式识别**：从 `source-formulas.xml` 找到公式节点 `id="eq4"`，MathML 还原为 LaTeX：
`k = A \exp\left(-\frac{E_a}{R T}\right)`
来源 locator：`C01-demo PDF p.4 right col. Eq.(4)`；`source-formulas.xml id="eq4"`。

**Step 2 变量表**：

| 符号 | 定义 | 单位 | 取值 | 首次定义位置 | 来源类型 |
|---|---|---|---|---|---|
| k | 速率常数 | s^-1 | 5.1（原文报告） | p.5 Table 2 | 原文定义 |
| A | 指前因子 | s^-1 | 2.5×10^13 | p.4 Table 1 | 原文定义 |
| E_a | 活化能 | kJ/mol | 85 | p.4 text | 原文定义 |
| R | 摩尔气体常数 | J/(mol·K) | 8.314 | p.3 Nomenclature | 原文定义 |
| T | 反应温度 | K | 350 | p.5 experimental | 原文定义 |

**Step 3 推导说明**：
- 步骤 1：对 Eq.(4) 两边取自然对数，得 `ln k = ln A - E_a/(R T)`。依据：对数运算规则。
- 步骤 2：代入原文数值。依据：p.4 Table 1、p.4 text、p.5 experimental、p.3 Nomenclature。
- 步骤 3：单位转换 `E_a = 85 kJ/mol = 85000 J/mol`。依据：SI 单位制。
- 步骤 4：计算指数项 `-E_a/(R T) = -85000 / (8.314 × 350) = -29.21`。
- 步骤 5：计算 `exp(-29.21) = 2.03×10^-13`。
- 步骤 6：计算 `k = 2.5×10^13 × 2.03×10^-13 = 5.075 s^-1`。
- 假设与边界：Arrhenius 方程适用；温度恒定 350 K；指前因子与活化能不随温度变化。

**Step 4 数值核验**：
- 计算值：`k_calc = 5.075 s^-1`
- 原文值：`k_ref = 5.1 s^-1`（p.5 Table 2）
- 相对偏差：`|5.075 - 5.1| / 5.1 × 100% = 0.49%`
- 结论：在原文 2 位有效数字末位 ±1 范围内，复算通过。

### 输出

`/app/output/result.json` 片段：
```json
{
  "case_id": "C01-demo",
  "status": "success",
  "main_result": {
    "formula_id": "eq4",
    "latex": "k = A \\exp\\left(-\\frac{E_a}{R T}\\right)",
    "variables": [
      {"symbol": "k", "definition": "rate constant", "unit": "s^-1", "value": "5.1", "locator": "p.5 Table 2", "source_type": "original"},
      {"symbol": "A", "definition": "pre-exponential factor", "unit": "s^-1", "value": "2.5e13", "locator": "p.4 Table 1", "source_type": "original"},
      {"symbol": "E_a", "definition": "activation energy", "unit": "kJ/mol", "value": "85", "locator": "p.4 text", "source_type": "original"},
      {"symbol": "R", "definition": "molar gas constant", "unit": "J/(mol·K)", "value": "8.314", "locator": "p.3 Nomenclature", "source_type": "original"},
      {"symbol": "T", "definition": "reaction temperature", "unit": "K", "value": "350", "locator": "p.5 experimental", "source_type": "original"}
    ],
    "derivation_steps": [
      {"step": 1, "action": "take natural logarithm", "basis": "logarithm rule"},
      {"step": 2, "action": "substitute values", "basis": "p.4 Table 1, p.4 text, p.5 experimental, p.3 Nomenclature"},
      {"step": 3, "action": "convert E_a to J/mol", "basis": "SI unit conversion"},
      {"step": 4, "action": "compute exponent", "intermediate": "-29.21"},
      {"step": 5, "action": "compute exp", "intermediate": "2.03e-13"},
      {"step": 6, "action": "compute k", "intermediate": "5.075 s^-1"}
    ],
    "verification": {
      "calc_value": "5.075 s^-1",
      "ref_value": "5.1 s^-1",
      "relative_error_pct": 0.49,
      "acceptable": true,
      "note": "within last digit of 2 significant figures"
    }
  },
  "evidence": {
    "formula_locator": "C01-demo PDF p.4 right col. Eq.(4); source-formulas.xml id=eq4",
    "variable_locators": ["p.5 Table 2", "p.4 Table 1", "p.4 text", "p.3 Nomenclature", "p.5 experimental"]
  },
  "uncertainty": "原文有效数字 2 位，偏差 0.49% 可接受；无未报告项。",
  "change_record": ["initial extraction", "unit check passed", "numeric verification passed"]
}
```

同时输出 `variables_table.md`、`derivation.md`、`verification.csv` 和 `preview/result.pdf`。所有文件均可回到原文 locator 复核。
