---
name: rq-driven-retrieval
description: >-
  Research-question-driven literature retrieval. Decompose a composite research
  question into a structured, evidence-typed sub-question list, plan a multi-round
  query sequence with term expansion and dependencies, screen and rank candidate
  records with a reproducible basis, keep a verbatim evidence ledger and a coverage
  / stop decision, and echo every output_contract key the case declares (never a
  type placeholder). Single-command entry all is equivalent to the init/show/check/
  build/selfcheck workflow; pure standard library, offline, deterministic, exit 0
  even on empty or corrupt input. Use when a task asks for 科研问题驱动检索 / 问题拆解
  / 查询规划 / 术语扩展 / 多轮检索 / 停止判断 with a traceable path.
version: 1.0.0
---

# rq-driven-retrieval — 科研问题驱动检索（search-02 v10）

一句话：**先把复合科研问题拆成可检索、可复核、可复现的子问题，再只交付能被独立复核的证据集。**

它把一个复合问题变成一条可回链的检索链：
问题拆解 → 查询规划（含依赖 / 优先级 / 术语扩展）→ 多轮候选筛选 → 证据台账 →
覆盖度 → 停止判断 → 报告 + `result.json`。不编造文献，不虚构 DOI，不声称覆盖远程数据库。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` / 参数自定位，不依赖当前目录。

---

单命令评测入口：

```bash
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 七步框架（含门控）** 推进——输入解析 → 子问题拆解 → 查询规划 →
  多轮检索 → 筛选与排序 → 停止判断 → 输出打包；前一步未冻结不进入下一步。
- **口径**：按其 **§3 量化口径** 计算子问题覆盖率 / 查询有效率 / 术语扩展增益 / 边际收益 /
  证据充分性 / 相关性评分 / 可核验性，每条候选的相关性依据必须可回查；不用自述替代可核验记录。
- **陷阱**：按其 **§4 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）；不得把文件名、题面标签或
  共现当作证据，不得猜补元数据。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainty` / `missing`，绝不静默提升为完整成功。

---

## 1. 单命令（single command，等价入口，评测入口）

该命令等价于 `main.py all`，按顺序执行：

1. **scan**：发现 `--input` 下全部材料（`case.json` / `task.md` 除外），登记 kind / bytes / sha1 / parse_status；
2. **decompose**：从研究问题（`case.json` 或 `task.md`）提取对象 / 机制 / 方法 / 时间范围 / 证据要求，
   拆成 3–6 个证据类型明确的子问题（含 queries / depends_on / priority / required）；
3. **plan**：为子问题规划前置 / 并行 / 依赖 / 补充查询，含术语扩展表与预计轮次；
4. **screen**：对候选记录规则化去重、计相关性评分、给出入选 / 排除决定与依据；
5. **ledger**：为每条入选候选保留逐字 quote + `locator`（`source_id#n`）证据台账；
6. **coverage/stop**：计算子问题覆盖率与边际收益，给出停止判据（saturated / low_marginal_gain / needs_human）；
7. **save/verify**：写出全部产物 + `result.json`（契约逐键回填 + `case_id` 透传）→ 占位符净化 → exit 0。

无需 `draft.json`；空输入、坏 JSON、缺 `case.json` 同样 exit 0 并写合法 `result.json`。

---

## 2. 五命令工作流（等价入口，Agent 深读时质量更高）

```
python3 -B /skills/weekly-skill/scripts/main.py init       # 扫描输入、写 partial result.json 与 draft 骨架
python3 -B /skills/weekly-skill/scripts/main.py show       # 打印带 locator 的段落 / 候选记录（--grep/--limit/--sources）
python3 -B /skills/weekly-skill/scripts/main.py check      # 校验 draft 子问题 / 筛选决策 / rid 合法性
python3 -B /skills/weekly-skill/scripts/main.py build      # 组装产物并定稿 result.json
python3 -B /skills/weekly-skill/scripts/main.py selfcheck  # 复检产物一致性与非空
```

五条命令与 `all` 共用同一引擎；`all` ≈ `init` + 自动候选 + `build` + `selfcheck`。
全局参数 `--input / --output / --work` 可放在子命令前或后（也可用环境变量 `SKILL_INPUT` 等）。

---

## 3. result.json 约定（片段示例，键名冻结）

```
{
  "case_id": "synth-case",
  "status": "partial",
  "output_contract": {
    "contract_overrides": {"note": "agent overrides if any"},
    "id": "SQ1",
    "type": "mechanism",
    "other": "additional structured notes for this key",
    "text": "the sub-question text",
    "queries": ["planned query"],
    "depends_on": ["SQ0"],
    "priority": 1,
    "required": true,
    "rid": "R001",
    "subquestion_ids": ["SQ1"],
    "decision": "include",
    "relevance": 0.5,
    "quote": "verbatim supporting span",
    "locator": "M01#p1",
    "reason": "why this decision was made",
    "subquestions": [{"id": "SQ1", "text": "sub-question"}],
    "candidates": [{"rid": "R001", "decision": "include"}],
    "evidence": [{"rid": "R001", "verified": true}],
    "coverage": {"required_total": 1, "covered": 1},
    "search_log": {"n_queries": 1, "rounds": 1},
    "stop_decision": [{"stop": "saturated"}],
    "report": "report.md",
    "case_id": "synth-case",
    "status": "partial"
  }
}
```

**契约回填**：case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层；不给时回填标准键。
任何键都写真实值，绝不写 `string` / `object` 类型占位符，也不写 JSON `null`；路径键指向真实非空文件；
`case_id` 原样透传；`status` 取 `answered / partial / insufficient_evidence / input_error` 之一并给
非空 `sources`、`uncertainty`、`change_records`、`limits`。

---

## 4. 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、子问题、候选、证据、覆盖度、停止判断、limits、uncertainty、change_records |
| `subquestions.json` | 结构化子问题（含 queries / depends_on / priority / required） |
| `candidates.jsonl` | 逐条候选记录（rid、locator、relevance、decision、basis、quote） |
| `evidence_ledger.json` | 证据台账（逐字 quote + locator + verified 标记） |
| `coverage.json` | 每个子问题的证据覆盖状态与覆盖率 |
| `stop_decision.json` | 每个子问题的停止判据（saturated / low_marginal_gain / needs_human） |
| `search_log.json` | 查询数量、轮次、零产出子问题、检索范围声明 |
| `report.md` | 人类可读报告（子问题、筛选摘要、覆盖与停止、证据与限制） |

---

## 5. 输入

- `--input`（默认 `/input`）：`case.json`（可含 `case_id`、`output_contract`、`research_question`）与任意
  UTF-8 文本材料（`.md/.txt/.json/.tex/.csv/...`）。`task.md` 用于推断研究问题。
- 无 `case.json` 时按材料文本推断问题；无材料时给诚实的空候选与 `insufficient_evidence`。

---

## 6. 异常与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`，不编造文献。
- 无可解析文献记录：`candidates` 给带说明的诚实空结构，`degradations` 记录原因。
- 未知单位 / 无 DOI / 无摘要：保留原值并记入 `uncertainty`，不猜测补全。
- 任何阶段异常：捕获后保留 partial `result.json`（含 `errors`、`traceback_tail`）并 exit 0。
- 不联网、不安装工具、不臆造元数据；检索结论限定在“所给快照内”，不宣称全局召回。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] 每个核心子问题可独立形成查询式；核心子问题覆盖原问题全部关键要素；子问题数 ≤ 6。
- [ ] 每条候选带 `source_id#n` locator 与相关性依据；被排除项与遗漏项都有原因。
- [ ] 停止判断给出理由、阈值、实际边际收益与是否转人工。
- [ ] 空语料 / 坏文件 / 无候选三条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] 两次运行按稳定键排序后结果一致，时间戳不参与判等。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainty` / `missing`，绝不静默提升为完整成功。

---

## 8. 文件清单与维护

```
SKILL.md                        本文件：入口、双路径、口径、契约、降级、自查
scripts/main.py                 入口：all / init / show / check / build / selfcheck
references/expert_playbook.md   专家参考手册：七步框架/量化口径/陷阱/交付物/自查表（执行前必读）
references/retrieval-contract.md 契约与 locator 的可复用约定
environment/resources.yaml      资源入口声明（命令、路径、无网络、纯标准库）
examples/case.json              最小可复跑样例：case_id + output_contract + research_question
examples/expected_output.json   示意输出（标明为虚构示例）
README.md                       安装、用法、产物、限制、维护
SELFTEST.md                     自测记录：eval_sim rich/boundary × single/agent
GAIN_EVIDENCE.md                无 Skill 基线与使用增益证据（确定性 baseline_sim，非官方对照）
GITHUB_URL.txt                  仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`json`/`re`/`csv`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 1.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
- 复跑样例：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`。
