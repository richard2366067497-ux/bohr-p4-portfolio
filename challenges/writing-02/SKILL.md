---
name: academic-language-polish
description: >-
  逐句学术语言润色：单条命令即完成「读取材料 → 识别语言 → 选择成稿 → 逐句最小改动 →
  保护原子与限定词闸门 → 术语/缩写/格式合规审查 → 交付 润色稿 + 修改记录 + 逐句覆盖 +
  术语表 + 保留事实清单 + 证据映射 + 契约回填的 result.json」。支持 agent-first 双路径
  （Agent 读审查报告并写修改草稿 → check → build）；数字、单位、引用、交叉引用、公式与
  DOI/URL 逐条比对，限定词强度不得削弱或拔高；材料不足时如实记 partial 并交付缺口报告，
  绝不编造文献、统计量或图表。Use for academic proofreading, sentence-level editing,
  terminology consistency, hedging/claim strength, bilingual terminology and
  journal-format compliance checks on manuscripts.
version: 2.1.0
---

# academic-language-polish — 学术语言润色

本 Skill 做一件事的两面：**把句子改对**，并**用证据证明事实没被改掉**。它不整段重写、
不替换数据、不替作者编造引用；每条改动都带 `原文 / 改文 / 理由 / locator`，每条建议都
指出是哪一句、哪一份材料的哪一行触发的。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 0. 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：判分要点与评委维度、错误做法→正确做法、六步求解框架、量化口径与公式（编辑距离
D/E、术语一致率、限定词/数据保持率、来源映射与说明完整率）、领域陷阱、交付物与 locator 口径、
20 项防扣分检查表、完整虚构案例。执行顺序固定为：先读手册 → 再按 §2 流程逐阶段落盘冻结产物 →
交付前逐项勾选手册 §7 检查表。手册与 `SKILL.md` 冲突时，契约键名、入口命令与产物文件名以
`SKILL.md` 为准，方法与判分口径以手册为准。

---

## 1. 入口命令（第一条，必须先看）

单命令即可产出完整契约与全部关键产物（评测只跑这一条也能过）：

```
python3 /skills/weekly-skill/scripts/main.py build \
  --input /input --out /app/output --work /app/work
```

`build` 默认值即 `--input /input`、`--out /app/output`、`--work /app/work`。它按顺序：

1. 读取 `--input` 下的全部材料（md/txt/tex/bib/csv/html 直接读；docx/xlsx/pdf 报为
   `unparsed_material` 而不是猜内容）；
2. 识别语言（中文/英文占比）并**选择成稿**：按角色、标题结构（`#`/`Abstract`/`\section`）、
   篇幅、引用密度打分，阈值不足则不硬选，改出缺口报告；
3. 逐句切分，给出 `path:行:列` 的稳定 locator（代码块、公式块、表格、参考文献条目、
   引用块整段冻结不切）；
4. 对每句跑**可自动应用**的高精度规则（§4），应用前后比对保护原子与限定词强度（§5），
   任一不守恒就整句回滚并记为“仅报告”；
5. 再跑**只建议不应用**的语域/过强论断/冗词规则，以及统计量与超范围结论审查（§4、§7）；
6. 扫描术语一致性与缩写首次定义（§6），比对格式要求与模板（§7）；
7. 写出全部产物（§8），并把 `output_contract` 逐键回填进 `result.json`。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “帮我把这段摘要润色成学术语气” | 逐句最小改动 + 逐句建议（原文/改文/理由/locator） |
| “别把 95% 改成 98%，别动引用” | 数字/单位/引用/交叉引用/公式/URL 逐条比对，漂移即回滚 |
| “我的结论是不是说太满了” | 绝对化/最高级/因果动词的过强论断审查，给出保守改写建议 |
| “术语在全篇是否一致” | 双语术语表 + 变体检测 + 首次出现位置；拉丁缩写首次定义检查 |
| “统计显著但没有检验量” | 与 `p < 0.05`/CI/统计量比对，缺什么指出什么 |
| “投稿格式对不对” | 字体/字号/行距/栏数/边距/图表注/参考文献体例逐条与模板比对 |
| “改了哪里、为什么改” | `changes.json`/`changes.csv`/`coverage.json`/`preserved_facts.json` 全量记录 |
| “材料不全怎么办” | 如实 `partial` + 缺口报告，列出需要作者补充的内容 |

不适用：整段代写、把中文稿凭空翻译成英文长文、补造参考文献或统计结果、渲染 docx/PDF 版式。

---

## 3. 子命令与 agent-first 双路径

| 子命令 | 作用 | 关键参数 |
|-|-|-|
| `build` | 全流程：发现→选择→逐句润色→审查→写全部产物与 `result.json` | `--input --out --work` |
| `lint` | 只做静态审查，写 `lint_report.json`（材料清单 + 发现项） | 同上 |
| `check` | 闸门：重跑全流程并逐项核对产物与契约形状 | 同上 |
| `selfcheck` | 跑全流程后校验契约键是否齐全非空，写自检报告 | 同上 |

推荐 **agent-first** 流程（脚本负责规则与证据，Agent 负责判断与措辞，二者不可互替）：

```
# 1) 先看审查结果：发现项、格式比对、术语表
python3 /skills/weekly-skill/scripts/main.py lint  --input /input --out /app/output --work /app/work
# 2) Agent 读 /app/output/lint_report.json 与 /app/output/coverage.json，写 /app/work/draft.json
# 3) 闸门：应用草稿并重跑全流程
python3 /skills/weekly-skill/scripts/main.py check --input /input --out /app/output --work /app/work
# 4) 再跑一次确定性全流程，确认结果可复现
python3 /skills/weekly-skill/scripts/main.py build --input /input --out /app/output --work /app/work
# 5) 自检契约形状
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --out /app/output --work /app/work
```

`/app/work/draft.json` 约定（可缺省；缺省或坏 JSON 一律回退到确定性结果，不报错）：

```json
{"edits": [{"sid": "S0007", "before": "300 °C 为最佳反应温度。",
            "after": "300 °C 在实验温度范围内表现最好。",
            "reason": "the superlative claim is stronger than the shown evidence"}]}
```

应用草稿的三条硬约束：`sid` 必须存在；`before` 必须是该句的**逐字子串**；改后仍须通过
保护原子与限定词闸门。任何一条不满足就跳过，并在 `result.json.limits` 里写明跳过条数——
Agent 的建议不能绕过事实守恒。

---

## 4. 规则目录（应用面 / 建议面）

**应用面**（`applied: true`，可回滚）：`E01` 连续空格、`E02` 标点前空格、`E03` 逗号后空格、
`E04` 句末句点后空格、`E05` `et al/i.e/e.g` 缺句点、`E06` 高频拼写错误、`E07` a/an 与读音、
`E08` 复数主谓一致、`E09` 单数主谓一致、`E10` 数字与单位空格、`U01` 面积/体积单位上标
（`m2/g → m²/g`）、`Z01` 中文半角标点→全角、`Z02` 重复标点、`Z03` 中文标点前空格、
`Z04` 中文语境数字与单位空格、`Z05` 重复虚词。

**建议面**（`applied: false`，等作者确认）：`S01` 口语/推广语气、`S02` 过强论断、
`S03` 冗词（`in order to` 等）、`S04` 名词化堆叠、`S05` `由于…的原因`、`S06` `通过…的方法`，
以及两条审查型建议：`claim_strength`（最高级/绝对化措辞）、`statistic_missing`（声称显著但
缺检验量）。规则只改语言，不改结论方向。

---

## 5. 保护原子与限定词闸门

每次应用前，对**原句与改后句**分别抽取并比对：

| 类别 | 例 |
|-|-|
| 引用 | `[1]`、`[2-3]`、`\cite{...}`、`\ref{...}` |
| 交叉引用 | `图 1`、`表 1`、`Fig. 2`、`Table 3`、`Eq. 4` |
| 数值/单位 | `300`、`95%`、`0.1`、`°C`、`mg`、`m2/g`、`mL/min` |
| 公式/DOI/URL | `$E=mc^2$`、`10.xxxx/...`、`https://...` |

比对为**多重集相等**（同值同数），空白与上标数字（`²`↔`2`）归一后比较。
限定词闸门另外要求：**不得新增强断言词**（prove/confirm/determine/always…），
**不得删去弱限定词**（may/might/suggest/appear…）。任一不满足 → 整句放弃本次自动改动，
记为仅报告，并在 `preserved_facts.json` 的 `guards` 里留下原因。

---

## 6. 术语与缩写

- 双语种子表覆盖催化/材料/统计常用概念（催化剂 catalyst、转化率 conversion、比表面积 SSA、
  反应压力、载气流速、选择性、产率、机理、动力学、TEM/SEM/XRD…），并解析材料中自带的
  术语表（csv/tsv 两列或 JSON `terms`）。
- 每条术语给 `first_use` 位置、命中次数、出现形态；发现变体（如 `收率` 与 `产率`）记
  `variant_used`，仅在“去空格/连字符后与规范形一致”时才给出规范化建议。
- 全大写缩写给出“首次使用未见全称定义”的提示，位置精确到句。

---

## 7. 格式合规（format_spec / compliance_checks）

从约束文档逐条抽取规格（字体、字号、行距、栏数、边距、图表注位置、参考文献体例），
再与 `.tex` 模板的真实设置逐项比对：`\setmainfont` / `\setCJKmainfont`、`\documentclass`
选项、`geometry` 边距、`\onehalfspacing`、`\captionsetup`、`\bibliographystyle`。
每条给出 `status`（`match` / `mismatch` / `not_verifiable`）、`observed`、`reason` 与来源行号。
规格文档与模板都没有时，写 `not_verifiable` 并说明原因，不臆测。

---

## 8. 输出契约

写入 `--out`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `polished.md` | **润色后的成稿**（只含已应用的最小改动；未找到成稿时为缺口报告） |
| `changes.json` | 修改/建议清单 `{counts, entries[{sid, locator, type, rule, applied, before, after, reason, source}]}` |
| `changes.csv` | 同一清单的 CSV 版，便于表格复核 |
| `coverage.json` | 逐句覆盖：每句的 applied/suggested 计数、处理动作、locator |
| `glossary.json` | 双语术语表、出现形态、首次位置、变体与缩写提示 |
| `preserved_facts.json` | 逐句保护原子、限定词画像与守恒闸门结果 |
| `evidence_map.json` | 逐句到材料、行号、字节区间的映射（含 sha256） |
| `lint_report.json` | 静态审查 `{status, counts, findings[], compliance[]}` |
| `result.json` | 契约回填 + 结构化结果（见下） |

`--work` 下另有 `draft.json`（若提供）与 `run_report.json`（本轮摘要与产物字节数）。

`result.json` 顶层键（键名冻结）：

- `case_id` / `status` / `summary`
- `output_contract`：`case.json.output_contract` 逐键回填，并把每个键浅拷贝到顶层
- `changes[]`、`diagnostics[]`、`checks[]`、`coverage[]`
- `sources[]`、`uncertainties[]`、`limits[]`、`change_records[]`
- `inputs`：`{root, case_file, contract_source, case_keys, language_declared, language_detected, materials[]}`
- `runtime`：`{skill, python, seconds, budget_seconds}`

**回填口径**：case 给几个键就回填几个键，**每个键给真实值**，不写 `string`/`object`
这类类型占位符；未定义的键也给结构化非空值。未给契约时回填标准键：

```json
{"case_id": "the input case_id",
 "status": "success | partial | failed",
 "output_contract": {
   "case_id": "the input case_id, echoed verbatim",
   "deliverable": {"path": "polished.md", "role": "polished manuscript", "editable": true},
   "preserved_facts": [{"sid": "S0005", "locator": "manuscript.md:L11:C1", "conserved": true}],
   "evidence_map": [{"sid": "S0005", "locator": "manuscript.md:L11:C1", "source": "manuscript.md"}],
   "change_log": [{"sid": "S0005", "type": "unit_format", "before": "m2", "after": "m²", "applied": true}],
   "format_spec": [{"id": "F01", "requirement": "body text 10.5pt, 1.5 line spacing"}],
   "compliance_checks": [{"id": "K03", "status": "mismatch", "requirement": "10.5pt",
                          "observed": "documentclass options [11pt,onecolumn]"}],
   "custom_unknown_field": {"kind": "unrecognised contract field", "resolved": "echoed verbatim"}
 }}
```

**status 诚实规则**（由产物推导，不靠自述）：

- `success`：找到成稿、写出润色稿，且无 error 级一致性缺陷（warning 级发现项留在
  `uncertainties`/`limits` 里等作者确认）；
- `partial`：未找到成稿（交付缺口报告），或存在无法在不编造事实的前提下修复的 error 级缺陷；
- `failed`：输入不可读、内部异常导致没有任何可信产物（仍写出合法 `result.json`）。

---

## 9. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| 只有空文件/坏 JSON/碎片笔记 | 无成稿通过选择阈值 | 不失败：写缺口报告，`partial` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 回填空串并记 `limits` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键，来源记 `inputs.contract_source` |
| docx/xlsx/pdf 材料 | 非文本方法 | 报 `unparsed_material`，不猜正文 |
| 引用编号在参考文献表中不存在 | 编号差集非空 | `error` 级发现项 → `partial` |
| 自动改动会破坏原子或限定词 | 闸门比对失败 | 整句回滚，记入 `guards` 与 `limits` |
| 草稿 anchor 不在原句 | 逐字子串校验 | 跳过该条并累计条数，不报错 |
| 输出目录不可写 | OSError | 回退 stderr，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 10. 交付前自查

- [ ] **`references/expert_playbook.md` §7 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符。
- [ ] `polished.md` 非空；未找到成稿时是缺口报告而不是空白文件。
- [ ] `changes.json`/`changes.csv`/`coverage.json`/`glossary.json`/`preserved_facts.json`/
      `evidence_map.json`/`lint_report.json` 结构合法且互相可对照。
- [ ] 每条 applied 改动都有 `before`/`after`/`reason`/`locator`；每条建议都 `applied: false`。
- [ ] `preserved_facts.json` 中所有句子的 `conserved` 为真，或附有明确的不守恒说明。
- [ ] 空输入 / 坏 JSON / 无可读成稿三条路径各跑过一次，均 exit 0 且有缺口报告。

---

## 11. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、规则目录、闸门、契约、降级、自查
references/expert_playbook.md  专家方法论：判分要点、公式、领域陷阱、检查表、虚构案例
scripts/main.py                入口：build / lint / check / selfcheck，产物与契约组装
scripts/polish_core.py         读取、切句与 locator、保护原子、限定词、规则、术语、语言识别
scripts/review.py              审查层：静态发现项、格式合规、建议规则、缺口报告
environment/resources.yaml     资源入口声明（命令、路径、预算、无网络、纯标准库）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`csv`/`json`/`re`/`hashlib`/`os`）；无第三方包、无网络、无外部模型。
- 版本 2.1.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号；随包专家方法论见
  `references/expert_playbook.md`。
- 每次改动后跑 `selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
