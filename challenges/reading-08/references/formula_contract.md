# formula_contract — result 键、映射表与核验状态口径

本文件冻结 `result.json` 的结构、MathML→LaTeX 映射、符号出处类型与数值核验状态。

## 1. `result` 子结构

| 键 | 内容 |
|-|-|
| `formulas[]` | `formula_id / label / latex / mathml_id / structure / structure_summary / symbols[] / locator / quote / quote_locator / quote_kind / quote_verified` |
| `variables[]` | 符号台账（见 §3） |
| `derivations[]` | 推导步骤：`step_id / rule / formula_id / expression / inputs[] / result / quote / locator / verified` |
| `numeric_checks[]` | 数值核验（见 §4） |
| `indicator_checks[]` | 印刷指标：`value / units / label / quote / locator` |
| `coverage` | 公式数、符号数、已定义符号数、推导数、指标数、三类核验计数 |
| `missing_objects[]` | 缺口清单：`object / id / reason`（+ 符号的 `definition_source`、核验的 `missing_symbols`） |
| `notes` | 方法与口径的一句话说明（字符串，永不为空） |
| `method` | 映射表名、出处类型枚举、核验状态枚举 |

## 2. MathML → LaTeX 映射表

| MathML | LaTeX | 说明 |
|-|-|-|
| `mi` / `mn` / `mo` | 其文本 | 希腊字母转 `\alpha`/`\beta`/`\gamma` 等 |
| `mtext` | `\text{...}` | 文本节点 |
| `mrow` / `math` / `mstyle` | 依次拼接 | 不引入括号 |
| `msup` | `base^{sup}` | 上标 |
| `msub` | `base_{sub}` | 下标 |
| `msubsup` | `base_{sub}^{sup}` | 同时上下标 |
| `mfrac` | `\frac{num}{den}` | 分数 |
| `msqrt` | `\sqrt{arg}` | 平方根 |
| `mroot` | `\sqrt[deg]{arg}` | 一般根 |
| `mfenced` | `\left( ... \right)` | open/close 取自属性 |
| `mover` / `munder` | `\overset{}{}` / `\underset{}{}` | 上下叠加 |
| `mtable` / `mtr` / `mtd` | `\begin{array}{l}...\end{array}` | 简单表格 |
| `mphantom` / `mpadded` / `semantics` | 拼接子节点 | 语义包装 |
| `annotation` / `annotation-xml` | 空串 | 不复制原始标注 |

未知标签只拼接子节点，绝不吞内容、绝不改写运算符。

## 3. 符号台账逐键语义

| 键 | 语义 |
|-|-|
| `symbol_id` | `v01`、`v02`……按出现顺序 |
| `latex` | 台账里的规范写法（`N_{0}^{2}`、`k`、`\alpha`） |
| `plain` | 基符号字符（`N`、`k`、`α`） |
| `formula_ids` | 该符号出现于哪些公式 |
| `role` | `constant`（如 `e`）/ `parameter`（有印刷值）/ `variable`（无值） |
| `definition_source` | `paper_defined` / `context_inferred` / `common_knowledge` |
| `definition` / `definition_quote` / `definition_locator` | 定义文本与其逐字出处 |
| `value` / `units` / `value_quote` / `value_locator` | 印刷取值与其逐字出处 |

出处类型判定：

1. 段落里有 `X is ...` 定义句 → `paper_defined`；
2. 只有 `X = 值 单位` 赋值、没有定义 → `context_inferred`；
3. 材料完全没有该符号 → `common_knowledge`（步骤与结论都据此标注）。

## 4. 数值核验状态

| status | 条件 | 语义 |
|-|-|-|
| `computed` | 公式所有符号都有印刷值 | 仅代入印刷值，不做单位换算 |
| `not_computable` | 至少一个符号没有印刷值 | `missing_symbols` 列出缺值符号，绝不猜 |
| `example_only` | 源里没有任何数值 | 用单位示意值探路，明确标注不是测量 |

`numeric_checks[]` 每条含 `formula_id / latex / status / assignments / missing_symbols /
probe / result / verification`。

## 5. locator 方案

| 对象 | 形式 | 例 |
|-|-|-|
| 公式 | `{文件}#{formula_id}` | `source-formulas.xml#fd-1` |
| 定义/赋值句 | `{文件}#p{段序}` | `source-formulas.xml#p1` |
| 指标/推导句 | `{文件}#L{行号}` | `paper-notes.txt#L1` |
| 任务文件句子 | `task.md#char{起}-char{止}` | `task.md#char3932-char3991` |

不使用尖括号包裹 locator，避免被交付扫描误判为未填写片段。

## 6. 不变量

- 公式只做映射还原，不做代数改写、不化简、不约分。
- 符号定义只取材料明写的句子；推断出来的取值与通用符号必须分别标注。
- 核验只代入材料里印出的值；缺值一律 `not_computable`，示意值一律 `example_only`。
- 输出件中不出现未填写的模板标记；空值以空串或结构化说明表达。
