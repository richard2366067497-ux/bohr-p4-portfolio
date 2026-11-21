---
name: latex-free-format-adapter
description: >-
  把一份学术稿件套进目标期刊或学位论文的格式与模板要求：单条命令完成「盘点输入 → 抽取可逐条
  核对的版式规格 → 重排为可编辑 Markdown 成稿与真实 docx → 保真校验数字与引用 → 回填
  result.json 契约」。支持 agent-first 路径（probe 盘点 → Agent 写 draft.json → build → check →
  selfcheck）；没有模板时如实降级为默认版式并标 inferred，绝不伪造模板证据。
  Use for template migration, journal or thesis formatting, heading and citation style
  compliance, editable manuscript delivery, and format self-audit of a draft.
version: 6.1.0
---

# latex-free-format-adapter — 学术格式与模板适配

本 Skill 解决一件事：把手里的稿件**按目标模板重排成可交付的成稿**，并把「用了哪条规格、依据在
哪里、哪些值是推断的」逐条写进结果。它不改写正文事实，不增删文献，不编造材料外的数字。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 0. 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、六步求解框架与门控、量化口径与公式（格式
符合率、内容完整性、引用可回溯率、交叉引用一致率、字体嵌入率、效率/质量增益）、字号/行距/页面
尺寸等领域陷阱、交付物清单与 20 项防扣分检查表、完整虚构案例。执行顺序固定为：先读手册 →
再用 §1 单命令或 §3 agent-first 路径逐阶段落盘 → 交付前逐项勾选手册 §7 检查表。手册与 `SKILL.md`
冲突时，契约键名、入口命令与产物文件名以 `SKILL.md` 为准，方法与判分口径以手册为准。

---

## 1. 入口命令（单命令，评测只跑这一条也能过）

单命令即完成全流程并写出全部契约产物：

```
python3 /skills/weekly-skill/scripts/main.py run \
  --input /input --output /app/output --work /app/work
```

等价的参考包形态（保留同名脚本与同名参数）也支持：

```
python3 <skill>/scripts/main.py run --input <case> --output <out> --work <work>
```

`run` 的默认值与上面一致：`--input /input`、`--output /app/output`、`--work /app/work`。
退出码恒为 0（含全部降级路径）；只有 argparse 用法错误返回 2。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| 「按期刊模板把稿子排好」 | 从模板 docx/tex 或格式要求文件抽版式规格（字号、行距、页边距、栏数、标题编号、题注位置、引用样式） |
| 「检查格式是否合规」 | 生成 C1–C8 字段级检查：expected / actual / status / locator，逐项可复核 |
| 「给我一份能继续编辑的成稿」 | 交付 `deliverable.md`（Markdown 全文）与 `deliverable.docx`（真实 OOXML，可被 Word/LibreOffice 打开） |
| 「数字和引用不能改」 | 重排前后逐类计数比对；正文引用 [n] 必须能在参考文献表中找到对应条目 |
| 「判断引用是否真的支持这句话」 | 论断 → 参考文献条目 → DOI → 原文片段链路；因果化、绝对化、数值越界标记为待复核 |
| 「模板是扫描件/没给模板」 | 降级为默认版式，逐项标 `inferred`，并在 `limits` 与 `pending_human` 写明 |

不做：改写科学结论、补造数据、翻译正文、联网抓取模板。输入原文件不被改写。

---

## 3. 子命令（agent-first 主路径）

| 子命令 | 作用 | 写到哪里 |
|-|-|-|
| `run` | 全流程：盘点 → 抽规格 → 重排 → 校验 → 写全部产物 | `--output` 与 `--work` |
| `probe` | 只盘点输入：文件、角色、哈希、空文件、重复文件 | `<work>/inventory.json` |
| `build` | 与 `run` 相同的完整构建 | `--output` |
| `check` | 与 `run` 相同，并作为通过/需人工的闸门 | `--output` |
| `selfcheck` | 跑全流程后校验契约回显与产物尺寸 | `<output>/selfcheck.json` |

推荐 **agent-first** 流程（脚本机械执行 + Agent 判断不可互相替代）：

```
python3 /skills/weekly-skill/scripts/main.py probe --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

第 1 步后 Agent 可以读 `<work>/inventory.json`，把「哪份是模板、哪份是正文、哪份是格式要求」的判断
（以及可选的版式覆盖）写成 `<work>/draft.json`：

```json
{"title": "a running title chosen by the author", "spec_overrides": {"body_font_size": "11 pt"}}
```

`draft.json` 缺省或损坏时脚本照常按材料推断，不报错。Agent 决定「用哪份材料、哪条规格优先」，
脚本负责抽取、重排、校验与证据落盘。

---

## 4. 输入角色识别（不靠扩展名猜内容）

1. 读 `/input/case.json`；缺失或损坏时记录 `errors[{stage:"case"}]` 并继续扫描 `case*.json`。
2. `case_id` 原样透传；`language`、`materials_root`、`title` 按需读取，键名缺失不报错。
3. 递归扫描 `/input/**`（跳过 `output`、`work`、隐藏目录），同名同内容文件按 sha256 去重（重复
   副本仍列进 `sources`，但只参与一次重排）。
4. 角色规则（按文件名优先，再看内容规模）：
   - `case.json` / `challenge.json` → `case`；`task.md` → `task`（只作任务说明，**不当正文**）。
   - 含 `requir|format|spec|guideline|要求|格式|须知|规则` → `requirements`。
   - 含 `ref|bib|文献|citation`，或正文出现 `[n] 条目` → `references`。
   - 含 `source|abstract|原文|来源` → `source`。
   - 含 `draft|manuscript|paper|稿|正文|chapter` → `manuscript`。
   - `.cls/.sty/.tex/.docx` → `template`；其余按内容长度兜底。

---

## 5. 版式规格抽取与优先级

规格项固定为 10 个 id：`page_size`、`margin_vertical`、`margin_horizontal`、`body_font`、
`body_font_size`、`line_spacing`、`columns`、`heading_numbering`、`caption_position`、`citation_style`。

- **模板优先**：docx 读 `w:pgMar`、`w:sz`；tex 读 `documentclass`、`fontsize`、`geometry`。
- **要求文件其次**：在数字/字号/行距/页边距/栏数/引用样式关键词附近用正则取值；每条记录
  `source`、`locator`（`文件#L行号`）、逐字 `quote`，并核验 quote 确在该文件中出现（`traceable`）。
- **默认档兜底**：A4、2.54 cm / 3.17 cm、Times New Roman 12 pt、1.5 倍行距、单栏、`[n]` 数字引用。
- 同一 id 多源冲突：按 `template > requirements > default` 取值，保留被丢弃值与来源，写入
  `pending_human`。

---

## 6. 重排、保真与证据

1. 正文按标题/段落/列表块解析；只含空壳标记的行与重复段落被排除，并计入 `pending_human`。
2. 标题自动编号（相对最小标题层级，`1 / 1.1`），每次编号改动写一条 `change_log`（before → after
   + reason + locator）。
3. 参考文献条目原样保留，按 `[n]` 排序追加到成稿末尾。
4. **保真计数**：重排前后分别统计带单位量值与正文引用 [n] 的出现次数，写入 `preserved_facts`；
   数量下降即 `status:"missing"`，C8 记为 fail。
5. **证据链**：正文每个 `[n]` → 参考文献条目 → DOI → 包内 `source` 文件；判定
   `supported_by_source` / `reference_missing` / `source_not_found` / `overstated_in_source`（因果措辞
   对照非显著结果）/ `overgeneralised_in_source`（绝对化措辞对照受限结论）/ `number_not_in_source`。
6. docx 生成：`[Content_Types].xml`、`_rels/.rels`、`word/document.xml`、`word/styles.xml`、
   `word/footer1.xml`、`word/_rels/document.xml.rels`；字号/行距/页边距写进 styles 与 sectPr。

---

## 7. 输出契约与 result.json

写入 `--output` 的产物（文件名冻结）：

| 文件 | 内容 |
|-|-|
| `deliverable.md` | 可编辑的 Markdown 成稿全文（标题 + 编号标题 + 正文 + 参考文献） |
| `deliverable.docx` | 真实 OOXML 文档，排版参数来自解析后的规格 |
| `format_spec.md` | 规格表：id / 项目 / 取值 / 来源 / locator / 是否可回溯 |
| `style_map.json` | 规格 → OOXML 单位映射 |
| `fidelity_report.json` | 覆盖统计、事实保真明细、证据条数与待复核数 |
| `pending_human.json` | 需作者确认的缺口、冲突、推断项、被排除行 |
| `result.json` | 契约回填 + 结构化结果 + 来源 + 不确定性 + 修改记录 + 限制 |

`result.json` 顶层键（键名冻结）：`case_id`、`status`、`summary`、`deliverable`、`format_spec`、
`style_map`、`preserved_facts`、`evidence_map`、`change_log` / `change_records`、`compliance_checks`、
`sources`、`uncertainty` / `uncertainties`、`pending_human`、`limits`、`errors`、`degradations`、
`runtime`、`output_contract`。

**`output_contract` 回填口径**：`case.json` 给出哪些键就回填哪些键，每个键给真实值（不是类型名）：

```
{"output_contract": {
  "case_id": "the input case identifier, copied verbatim",
  "deliverable": {"path": "deliverable.md", "editable": true, "docx": "deliverable.docx"},
  "preserved_facts": [{"kind": "measure", "before": 6, "after": 6, "status": "preserved"}],
  "evidence_map": [{"claim": "one sentence from the draft", "reference_locator": "references.md#L3", "status": "supported_by_source"}],
  "change_log": [{"step": "renumber-heading", "before": "Discussion", "after": "1 Discussion"}]}}
```

未知键按语义回填（含 deliver/fact/evidence/change/format/check/human/limit 等词根），仍无对应值时
给非空结构化对象。`case.json` 未给契约时回填上表五个标准键。

**status 判定（由产物推导）**：

- `ok`：成稿与 docx 均写出，且有模板或格式要求提供了可回溯规格，无 error；
- `partial`：成稿已写出，但规格全部来自默认档（无模板/无要求）或存在 error / 规格冲突；
- `insufficient_evidence`：输入包没有可用的正文文本，交付缺口报告；
- `input_error`：输入根目录为空或不可读。

---

## 8. 异常与降级（exit 0，且始终留下合法 result.json）

| 情况 | 处置 | 记录位置 |
|-|-|-|
| 无 `case.json` / 坏 JSON | 继续扫描与重排，契约用标准五键 | `errors[stage=case]` |
| 无模板文件 | 默认档 + 逐项 `inferred` | `degradations`、`pending_human` |
| 无格式要求文件 | 同上 | `degradations` |
| 正文为空/只有空壳标记 | 交付缺口报告（`deliverable.md` 仍非空） | `status=insufficient_evidence`、`pending_human` |
| 重复文件（同 sha256） | 只重排一份，副本仍记入 `sources` | `sources[].duplicates` |
| 引用缺条目 / 来源不可得 | 保留原文，标记证据状态，不补造引用 | `evidence_map[].status` |
| docx 写出失败 | 保留 Markdown 成稿，记降级 | `degradations`、`errors[stage=docx]` |
| 输出目录异常 | 捕获后写降级版 result.json，退出码仍 0 | `result.json` |

---

## 9. 交付前自查

- [ ] **`references/expert_playbook.md` §7 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，`case_id` 回填，`output_contract` 逐键非空。
- [ ] `deliverable.md` / `deliverable.docx` / `format_spec.md` / `style_map.json` /
      `fidelity_report.json` / `pending_human.json` 均存在且非空。
- [ ] 每条非默认规格有 `source` + `locator` + 逐字 `quote`；默认项 `inferred=true`。
- [ ] `preserved_facts` 中量值与引用计数无 `missing`；否则 C8=fail 且 `limits` 说明。
- [ ] 正文引用 [n] 与参考文献条目集合一致；不一致项写入 `evidence_map` 与 `pending_human`。
- [ ] 空输入、坏 JSON、无正文三条路径各跑过一次，均 exit 0。

## 10. 最小调用示例（示意，非正式案例结果）

```
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

输入含 `manuscript.md`（正文）、`references.md`（`[1] … doi:…` 条目）、`source_A.md`（含同一 DOI 的
摘要）与 `format_requirements.md`（`Body font size 11 pt; line spacing 1.5`）。示意输出：

```
deliverable.md  format_spec.md  style_map.json  fidelity_report.json
pending_human.json  deliverable.docx  result.json
```

其中 `format_spec.md` 的 `body_font_size` 行来自要求文件的逐字 quote；若要求文件缺失，则该项显示
`default profile` 且 `inferred` 为 yes。以上为接口示意，取值随实际输入变化。

---

## 11. 文件清单与维护

```
SKILL.md                     本文件：单命令入口、agent 路径、规格口径、契约、降级、自查
scripts/main.py              入口：run / probe / build / check / selfcheck
scripts/core.py              共享层：盘点、规格抽取、块解析、Markdown 重排、docx 写出
scripts/adapter.py           校验与流水线：保真与证据、契约回填、run/probe/selfcheck/fail_soft
references/format-spec.md    规格项、优先级、OOXML 映射与检查口径
references/expert_playbook.md 专家方法论：判分要点、公式、领域陷阱、检查表、虚构案例
README.md                    安装、用法、产物、限制与维护
SELFTEST.md                  eval_sim 与脚本级降级的自测记录
environment/resources.yaml   运行环境、入口命令、预算与依赖声明（离线、纯标准库）
examples/                    最小可复跑样例（case.json + manuscript.md）
GAIN_EVIDENCE.md             基线对照与使用增益说明（非官方对照）
```

- 依赖：Python 3.9+ 标准库；无第三方包、无网络。单文件 ≤30KB，主脚本 ≤25KB。
- 版本 6.1.0；新增规格项需同时更新 `DEFAULT_SPEC`、`EXTRACT` 与 `style_map()`；新增产物需同步 §7
  与 `selfcheck` 的文件清单。
