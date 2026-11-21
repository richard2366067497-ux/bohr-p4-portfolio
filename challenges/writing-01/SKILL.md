---
name: writing-01-section-drafting
description: 把一批科研材料（摘要/方法/结果段落、参数表、补充材料）整理成一篇可编辑的章节稿，并把每条论断回链到逐字的材料原句与「文件:行号」定位。支持一次性跑完的合并入口，也保留 init / show / check / build 分段入口供 Agent 先写草稿再由脚本核验；材料为空或损坏时如实记 insufficient_evidence，仍 exit 0 并写出合法 result.json。适用于论文初稿组装、方法/结果段改写、要点与原文对照核查。
version: 6.0.0
---

# writing-01 · 章节稿组装与逐句回链

本 Skill 只做一件事：**把材料里写过的句子，组织成一篇结构完整、每句可回查的章节稿**。
它不改数字、不补文献、不造图注；材料没写的，就写进「附录 缺口与待确认」。

安装根目录固定为 `/skills/weekly-skill`；脚本以 `__file__` 自定位，不依赖当前工作目录。

---

## 0. 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、求解框架（S1–S6）、量化口径与公式（论断
覆盖率 / 定位有效率 / 引用支持率 / 数值一致率）、领域知识、交付物清单与专家检查表、完整虚构
案例、交付前门控。执行顺序固定为：先读手册 → 再按手册求解框架逐阶段落盘冻结产物 →
交付前逐项勾选手册 §5 专家检查表。手册与 `SKILL.md` 冲突时，契约键名与入口命令以 `SKILL.md`
为准，方法与判分口径以手册为准。

---


## 1. 单命令入口（首条；评测入口，无 draft 时执行）

评测与日常使用都只需这一条，它会跑完整流程并落齐全部产物。**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` = `init` + `check` + `build` 的合并形态；三个路径参数都有同样的默认值，
退出码恒为 0。先写一份 partial `result.json`，结束时无条件覆盖为终版。

> 需要把「写什么」交给 Agent 时，改用第 3 节的四步入口；两条路径共用同一套判据与产物名。

---

## 2. 读什么、写什么

- 读 `/input/case.json`（可选）与 `/input` 下递归的全部材料：`md / txt / csv / tsv / json / docx`。
  `pdf` 仅识别文件头后跳过（不解析二进制），`png / jpg / xlsx / pptx` 等按二进制跳过。
- 产物固定为 `manuscript.md` 与 `result.json`（都落在 `--output`）；中间态写 `--work`。
- 章节顺序固定：摘要 → 1 引言 → 2 方法 → 3 结果 → 4 讨论 → 5 结论 → 参考文献 →
  数据可得性声明 → 附录。材料不足的章节保留标题并标注「材料未覆盖本节」，**不删章、不编内容**。

`case.json` 里只用到三样：`case_id`（原样透传）、`output_contract`（决定要回填的键）、
`source.title` / `title`（可选标题）。键名不认识也不报错。

---

## 3. Agent 优先路径（分段入口）

脚本负责发现、核验、成稿；Agent 负责「写哪些句子」。四步各自独立可重跑：

```
python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
```

```
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
```

```
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

`init` 建材料索引并打印每条材料的类型/字节/是否可读；`show` 可再列出带定位的证据句。
Agent 读完后把草稿写入 `/app/work/draft.json`（结构见 references/contract-and-locators.md），
`check` 会逐条核对引用是否在材料里逐字出现，`build` 再按同一口径成稿。

没有草稿时 `build` 仍可用：它按材料里可定位的句子自动分节组装，状态记为 `partial`。
草稿未命中材料的引用一律**拒收**，进入 `pending_human`，绝不混进正文。

---

## 4. 事实与定位

- `preserved_facts`：材料中含数字的原句（最多 30 条），字段为
  `fact_id / value_text / source_id / locator / verified`。
- `evidence_map`：正文里每条回链语句（最多 150 条），字段为
  `claim_id / section / quote / source_id / locator / verified`。
- `locator` 统一写成 `相对路径:L行号`；docx 按抽出的段落行计，json 材料按展平后的行计。
- 判定引用是否成立，只看去掉空白后的**子串**是否出现在某份材料里；不做同义替换猜测。

---

## 5. 结果契约

`result.json` 的键名冻结为：`case_id`、`status`、`deliverable`、`preserved_facts`、
`evidence_map`、`change_log`、`output_contract`、`sources`、`uncertainty`、`uncertainties`、
`pending_human`、`errors`、`degradations`、`changes`、`change_records`、`limits`、`coverage`、
`runtime`。

输入给了 `output_contract` 时，逐键回填；没给时按下面的五个标准键回填（与本节示例一致）：

```json
{"output_contract": {
  "case_id": "案例标识，原样透传",
  "deliverable": "manuscript.md",
  "preserved_facts": [{"fact_id": "F01", "value_text": "含数值的材料原句", "source_id": "M01", "locator": "p.md:L9", "verified": true}],
  "evidence_map": [{"claim_id": "C001", "section": "2 方法", "quote": "材料逐字原句", "source_id": "M01", "locator": "p.md:L9", "verified": true}],
  "change_log": [{"action": "finalize", "status": "ok", "deliverable": "manuscript.md", "sections": 9, "evidence": 12}]}}
```

规则：每个契约键都写进 `output_contract`，同时在顶层保留同名副本；`case_id` 一律原样透传；
契约值不得是 `null`、空串或空数组——无内容时写一条说明「无」的**结构化条目**（如
`{"value_text": "材料未提供含数值原句", "verified": false}`），而不是留空。

`status` 取值：`ok`（证据 ≥5 条且零拒收）、`partial`（有产物但证据不足或存在拒收）、
`insufficient_evidence`（没有可用正文）、`input_error`（致命异常兜底）。

---

## 6. 降级与兜底

| 情形 | 处置 | 记录位置 |
|-|-|-|
| 输入目录不存在 | 返回 `input_error`，仍写合法 result.json | `errors` |
| 只有空文件 / 模板标记（如 `[待写]`） | 不当作证据，跳过 | `degradations` |
| 坏 JSON 材料 | 记 `json_parse_failed`，正文不可用 | `degradations` |
| PDF / 图片 / xlsx / pptx | 跳过二进制，提示补文本 | `pending_human` + `degradations` |
| 单文件 >2MB | 读前 2MB | `file_truncated` |
| 材料不足以支撑某章 | 保留标题 + 「材料未覆盖本节」 | 正文附录 |
| 草稿引用未命中材料 | 拒收该引用 | `pending_human` + 附录 |
| 输出目录不可写 | 回落到 `--work` | `output_dir_fallback` |
| 未捕获异常 | 写最小合法 result.json，退出码仍 0 | `errors: fatal:*` |

---

## 7. 自检

每一次 `run/build` 之后：

- **`references/expert_playbook.md` §5 专家检查表逐项通过**（未通过项先修复再交付）；
- `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键齐全且无空值；
- `manuscript.md` 至少 5 个二级标题，且每个证据句都带 `文件:行号`；
- 空目录与坏 JSON 两个探针各自 exit 0 且写出合法 result.json（结果写入 `work/self_check.json`）；
- 重复运行同一输入，除 `runtime.elapsed_s` 外产物内容一致。

## 8. 文件清单

```
SKILL.md                              本说明
scripts/main.py                       入口与内核：init / show / check / build / run
references/expert_playbook.md         专家方法论：判分要点、公式、检查表、虚构案例
references/contract-and-locators.md   草稿结构、result 字段、定位与状态判定
README.md                             安装、最小示例、限制
SELFTEST.md                           空/坏输入与四格评测记录
GITHUB_URL.txt                        仓库位置
environment/resources.yaml            资源与预算声明
```

依赖：Python 3.9+ 标准库；离线；不启动外部服务。
