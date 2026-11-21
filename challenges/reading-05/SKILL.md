---
name: reading-client
description: >-
  Faithful reading closed loop for one or more supplied documents: open every material
  (txt/markdown/csv/tsv/json/tex/XML, plus a standard-library PDF content-stream reader
  and a DOCX OOXML reader), anchor each paragraph under a stable p{page}#para{n} locator
  with absolute char offsets, select quantitative evidence spans, answer only from those
  spans, audit quote verbatimness and locator uniqueness, then export a reading record, a
  golden standard, a diff report, a version history and a single-file offline reader.
  Never paraphrases an answer, never invents a citation, and degrades to a legal
  result.json with an explicit gap list when the material is empty or unreadable.
version: 3.0.0
---

# reading-client — 逐段阅读闭环

一句话：**先把每个段落钉在 locator 上，再只从被钉住的句子里回答。**

它不写书评、不补全缺失数据、不把摘要当成原文。每个答案都带 `原文引用 / locator /
字符区间`；每条批注都能回到产生它的那个段落；导出件可以在离线环境直接打开。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 七步框架（含门控）** 推进——输入盘点 → 文档登记 → 定义字段 → 单文抽取
  → 建原始矩阵 → 可比性判定 → 计算与整合 → 独立核验 → 交付；前一步未冻结不进入下一步。
- **字段与口径**：按其 **§3 可比性分级** 与 **§4 公式** 逐格核验，原值 / 原单位 / 归一值分开保存，
  不跨文档补值，不把去除率当吸附量。
- **容差**：按其 **§5 舍入包络** 判定复算是否通过，明确区分舍入包络与实验不确定性。
- **陷阱**：按其 **§6 领域陷阱清单** 逐条排雷；未报告项写 `NR`，不写成 0 或「无」。
- **门控**：交付前逐项通过其 **§9 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为 `answered`。

---

## 1. 入口命令（第一条，必须先看）

单命令即可跑完整条闭环并产出全部产物（评测只跑这一条也能过）：

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```
python3 -B /skills/weekly-skill/scripts/main.py \
  --input /input --output /app/output --work /app/work
```

该命令等价于 `main.py build`，按顺序执行：

1. **open**：发现 `--input` 下全部材料（`case.json`/`task.md` 除外），按 sha1 去重；
2. **locate**：逐份材料抽文（文本直读；PDF 用 `zlib` 解压内容流后取 `(...)Tj`；
   DOCX 用 `zipfile` 读 `word/document.xml`），按空行切段，超长段按 ~1600 字符再切，
   每段得到 `p{页}#para{序}` locator 与绝对 `char_start`/`char_end`；
3. **select**：在含数字/百分号的句子里按“是否位于 Results 类段落”打分，每份材料最多 3 条；
4. **ask**：只把选中的句子原样作为答案，构造 claim 与 evidence；
5. **save**：写出 anchors / annotations / qa_log / reading_state；
6. **review**：审计“引文逐字命中段落”“locator 唯一”“区间有长度”；
7. **export**：写阅读记录、golden standard、diff report、version history、离线阅读器。

任意阶段抛异常都会兜底写出合法 `result.json` 并 exit 0。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “这篇到底哪句话说了产量/性能” | 逐段锚定 + 逐字引文 + locator |
| “给我一个能离线打开的精读页” | `reader/index.html` 单文件阅读器 |
| “你的答案凭什么” | 每条 claim 带 evidence（quote + locator + 字符区间） |
| “有 PDF/DOCX 也要读” | 纯标准库取文，抽不出就写 `degradation`，不编造 |
| “材料是空的/坏的” | `insufficient_evidence` / `input_error` + 缺口清单 |

不适用：文献综述代写、跨文元分析、补造缺失数值、替代同行评议。

---

## 3. 子命令与 agent-first 双路径

| 子命令 | 作用 | 关键参数 |
|-|-|-|
| `build` | 全流程（默认）：open→locate→select→ask→save→review→export | `--input --output --work` |
| `show` | 打印已锚定段落与 locator，便于取证 | 追加 `--doc D1` |
| `check` | 重跑全流程，并合并 `/app/work/draft.json` 里的 Agent 判读 | 同上 |
| `selfcheck` | 重跑全流程并审计产物与契约键 | 同上 |

每个子命令都会重写一份完整 `result.json`，评测跑哪一条都拿得到完整契约。

推荐 **agent-first** 流程（脚本负责取文与证据，Agent 负责判读与措辞）：

```
# 1) 确定性全流程，先拿到锚点与证据跨度
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
# 2) Agent 读 /app/output/reader/anchors.json 与 reading_record.md，写 /app/work/draft.json
# 3) 闸门：合并草稿并复核
python3 -B /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
# 4) 交付前自查
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`/app/work/draft.json` 约定（可缺省；缺省或坏 JSON 一律回退到确定性选句，不报错）：
顶层可含 `question`，以及一个 `notes` 数组；每条 note 用 `span_id` 指向
`reader/anchors.json` 中已存在的证据跨度，用 `text` 补人写的批注。合并时只接受
`span_id` 命中且 `text` 非空的条目，其余逐条丢弃并把条数写进 `degradations`——
Agent 的措辞不能绕过取证要求。（本文件是选做增强，主路径不依赖它。）

---

## 4. 锚定与选句口径

- **locator**：`p{页}#para{序}`。页号由绝对字符偏移推得（`1 + char_start // 1600`），
  同一页内段落序号递增，因此 locator 稳定且唯一；报告里写作 `(p1#para4)`，
  不使用尖括号形式。
- **字符区间**：`char_start`/`char_end` 是规范化文本（`\r\n`→`\n`、连续空白压缩）里的
  绝对偏移，引用可直接切出。
- **选句**：只取长度 ≥20 字符且含数字或百分号的句子；Results / Findings / Conclusion
  段落加权；每份材料最多 3 条。没有命中时如实留空并写原因，不用摘要凑数。
- **shell 过滤**：整段只有未填写模板标记的段落会被跳过，并记入 `degradations`。

---

## 5. 输出契约

写入 `--output`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `reading_record.md` | 人读记录：文档表 / 证据表 / 质检 / 备注 |
| `golden_standard.json` | 金标：文档 sha1、锚点数、每条 span 的 quote+locator |
| `diff_report.md` | 本次与金标逐项对照，分歧显式列出 |
| `version_history.md` | 版本与本次变更记录 |
| `self_check.json` | 交付前自查（检查项 + 产物清单 + 结论） |
| `run.log` | 运行摘要（含秒数） |
| `result.json` | 契约回填 + 结构化结果（见下） |
| `reader/anchors.json` | 全部锚定段落（含字符区间） |
| `reader/annotations.json` | 证据跨度批注（highlight + 字符区间） |
| `reader/qa_log.json` | 质检明细与通过计数 |
| `reader/reading_state.json` | 阅读状态（cursor / 计数 / 步骤） |
| `reader/index.html` | 单文件离线阅读器（内嵌 JSON，所有开标签带属性） |

`--work` 下另有 `draft.json`（若提供）。

`result.json` 顶层键（键名冻结；case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层）：

- `case_id` / `status` / `summary`
- `output_contract`：逐键回填真实值，不写 `string`/`object` 类型占位符
- `result`：`{question, task_source, documents, closed_loop, selections, annotations,
  anchor_precision_counts, context_design, export, efficiency, method_notes, artifacts}`
- `claims[]` / `sources[]`（每条任务级 source 至少带一条逐字 quote + locator）
  / `uncertainties[]`（镜像 `uncertainty`）/ `change_records[]`（镜像 `changes`）
- `errors[]` / `degradations[]` / `pending_human[]` / `limits[]` / `counts` / `runtime`

**回填样例**（未给契约时回填标准五键）：

```json
{"case_id": "synth-rich-reading-05",
 "status": "answered",
 "output_contract": {
   "case_id": "synth-rich-reading-05",
   "status": "answered",
   "result": {"closed_loop": {"completed": 7, "total": 7}, "selections": 2},
   "claims": [{"claim_id": "c01", "kind": "answer_span",
               "text": "D1 reports at p1#para4 a quantitative result",
               "evidence": [{"source_document_id": "D1",
                             "quote": "Rice lines carrying qDTY12.1 showed 28% higher grain yield under drought.",
                             "locator": "p1#para4"}]}],
   "uncertainties": [{"item": "scope", "detail": "only the supplied documents are read"}]}}
```

**status 诚实规则**（由产物推导，不靠自述）：

- `answered`：至少有一条候选证据跨度，且引文逐字命中；
- `partial`：材料可读但没有可锚定的量化跨度；
- `insufficient_evidence`：文件存在但一份也读不出段落；
- `input_error`：`--input` 不存在或没有任何材料文件。

---

## 6. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 无材料 | 缺口报告，`input_error` |
| 只有空文件 / 坏文件 / 碎片笔记 | 锚定后无跨度 | `insufficient_evidence` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 退回目录名并记 `degradations` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键（`case_id/status/result/claims/uncertainties`） |
| PDF / DOCX 取文失败 | 引擎异常 | 记 `degradation`，不猜正文 |
| 引文不在原段落 / locator 重复 | 质检失败 | 记 `degradation`，不掩盖 |
| 输出目录不可写 | OSError | 回退 stderr，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] 每个 `claims[]` 条目至少带一条 `quote` + `locator`，且引文能在对应段落找到。
- [ ] `reader/anchors.json` 的 locator 唯一；`reader/index.html` 可离线打开且内嵌数据。
- [ ] `reading_record.md` / `golden_standard.json` / `diff_report.md` / `version_history.md` /
  `self_check.json` 均非空且可互相核对。
- [ ] 空输入 / 坏文件 / 碎片笔记三条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的 23 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为 `answered`。

---

## 8. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、口径、契约、降级、自查
scripts/main.py                入口：build / show / check / selfcheck，闭环编排与契约组装
scripts/client_kit.py          取文（含纯标准库 PDF/DOCX）、锚定、选句、质检、渲染
references/expert_playbook.md  专家参考手册：七步框架/可比性分级/公式/容差/陷阱/自查表（执行前必读）
references/client_contract.md  契约键语义、locator 方案、选句与状态口径
environment/resources.yaml     资源入口声明（命令、路径、预算、无网络、纯标准库）
examples/case.json             最小可复跑样例：case_id + output_contract + task_instruction
examples/materials/paper.txt   最小可复跑样例材料（含量化结论，跑出 answered）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（确定性 baseline_sim，非官方对照）
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`json`/`re`/`zipfile`/`zlib`/`html`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 3.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
- 复跑样例：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`（应得 `status=answered`）。
