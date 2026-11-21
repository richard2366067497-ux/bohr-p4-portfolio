---
name: traceable-literature-retrieval
description: >-
  Turn a research question plus a supplied snapshot into a traceable literature
  candidate set: plan queries from the question, index every material with a
  source_id#n locator, parse structured records (json/jsonl/csv/tsv) and quotable
  prose lines, deduplicate by DOI then normalised title, score each candidate by
  keyword overlap, split included from screened-out with a stated basis, and keep
  both the ranked shortlist and the omissions. answer at least three real queries,
  echo every output_contract key the case declares (never a type placeholder),
  and report what the snapshot could not support instead of inventing literature
  or identifiers. Use when a task asks for 学术文献检索 / 文献筛选 / 候选召回与排序 /
  来源可追溯 with a reproducible path. Pure standard library, offline, deterministic.
version: 1.0.0
---

# traceable-literature-retrieval — 可追溯文献检索

一句话：**先把每条候选钉在来源 locator 上，再只交付能被独立复核的候选集。**

它不编造文献、不虚构 DOI、不声称覆盖远程数据库。每条候选都带
`object_id / source_id / locator / DOI / 相关性分值`；每条筛选决定都有依据；
空结果、缺元数据与接口异常分别说明，绝不补造。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__`/参数自定位，不依赖当前目录。

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 八步框架（含门控）** 推进——输入登记 → 材料解析与定位 → 问题与检索范围
  → 查询规划 → 候选召回与去重 → 相关性判定与排序 → 证据与状态组装 → 提前保存并验证；前一步未冻结不进入下一步。
- **口径**：按其 **§3 量化口径** 计算 `P@k / Recall@k / nDCG@k / 元数据准确率 / 溯源完整率`，
  每条候选的相关性依据必须可回查；不得用自述替代可核验记录。
- **陷阱**：按其 **§4 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）；不得把文件名、题面标签或共现当作证据。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties` / `missing`，绝不静默提升为完整成功。

---

## 1. 单命令（等价入口，one-shot，评测入口）

单命令即可跑完整条闭环并产出全部产物（评测只跑这一条也能过）：

```
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

该命令等价于 `main.py all`，按顺序执行：

1. **scan**：发现 `--input` 下全部材料（`case.json` / `task.md` 除外），登记 kind / bytes / sha1 / parse_status；
2. **parse**：结构化材料（json / jsonl / csv / tsv）抽 `records`，长文本材料抽可复核的 `lines`，
   每条记录得到 `source_id#n` locator；
3. **plan**：从研究问题（`case.json` 或 `task.md`）构造查询计划（多轮 AND / OR 组合）；
4. **dedup**：按规范 DOI，其次按规范化标题去重，保留证据更全的一条并记录 `duplicate_of`；
5. **screen**：按与研究问题的关键词重叠度打分，`include` / `exclude` 各自带依据；
6. **save**：写出 candidates / queries / screening / coverage / report；
7. **verify**：审计契约键、候选 locator、查询计划与 status 枚举。

任意阶段抛异常都会兜底写出合法 `result.json` 并 exit 0。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “围绕这个问题找相关文献” | 查询规划 + 候选召回 + 相关性依据 |
| “哪些被筛掉了、为什么” | `screening.json` 保留每条被排除的候选与依据 |
| “这些文献哪来的、能不能复核” | 每条候选带 `source_id#n` locator 与 DOI |
| “有没有遗漏关键文献” | `missing[]` 如实列出未覆盖项，不谎称全覆盖 |
| “材料是空的 / 坏的 / 只有笔记” | `insufficient_evidence` / `input_error` + 缺口说明 |

不适用：单篇论文精读、全文解析、写作润色、替代同行评议、声称远程数据库的全量覆盖。

---

## 3. 子命令与 agent-first 双路径

| 子命令 | 作用 |
|-|-|
| `all` | 全流程（默认）：scan→parse→plan→dedup→screen→save→verify，并写增益对照 |
| `init` | 建索引、写工作稿骨架与一份合法 partial，便于增量完善 |
| `show` | 打印研究问题、查询计划、材料清单与候选（带 locator） |
| `check` | 重跑判定，报告入选 / 排除 / 记录数与 PASS / DEGRADED |
| `build` | 由当前输入生成六件产物 + 最终 `result.json` |
| `selfcheck` | 复检：产物存在性、契约完整性、status |
| `compare` | 写 base-vs-skill 的确定性结构对照（非官方分数） |

每个会写盘子命令都写出一份完整 `result.json`，评测跑哪一条都拿得到完整契约。

推荐 **agent-first** 流程（脚本负责取文与证据，Agent 负责判读与措辞）：

```
# 1) 建索引与工作稿骨架
python3 -B /skills/weekly-skill/scripts/main.py init   --input /input --output /app/output --work /app/work
# 2) Agent 读材料与 locator
python3 -B /skills/weekly-skill/scripts/main.py show   --input /input --work /app/work
# 3) 闸门：机械校验契约键、去重与状态
python3 -B /skills/weekly-skill/scripts/main.py check  --input /input --output /app/output --work /app/work
# 4) 生成产物与最终结果
python3 -B /skills/weekly-skill/scripts/main.py build  --input /input --output /app/output --work /app/work
# 5) 交付前自查
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
# 6) 确定性结构对照（可选）
python3 -B /skills/weekly-skill/scripts/main.py compare --input /input --output /app/output --work /app/work
```

`/app/work` 下另有 `index.json`（材料与查询快照）、`check_report.json`，
以及 `init` 写出的 `draft.skeleton.json`（选做；主路径不依赖它）。

---

## 4. 检索与判定口径

- **locator**：结构化记录为 `{source_id}#{序号}`，长文本行为 `{source_id}#L{行号}`；不使用虚造页码。
- **去重键**：规范 DOI 优先，其次 `nkey(title)`；被合并成员写入保留者的 `duplicate_of`。
- **相关性**：`score = |问题关键词 ∩ (标题+摘要+期刊)| / |问题关键词|`（无问题文本时取 1.0），
  排序按 score 降序、object_id 升序，保证确定性。
- **状态**：`answered`（有入选候选）/ `insufficient_evidence`（材料存在但无候选）/
  `input_error`（无材料）；`missing[]` 与 `uncertainty[]` 分别记录遗漏与不确定。

---

## 5. 输出契约

写入 `--output`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `result.json` | 契约回填 + 结构化结果（见下） |
| `candidates.jsonl` | 入选候选，逐行含 object_id / locator / DOI / 相关性分值 |
| `queries.jsonl` | 查询计划，逐行含 query_id / query / intent |
| `screening.json` | 被排除候选与遗漏项，逐条带依据 |
| `coverage.json` | 覆盖计数（候选数、去重后、来源数、可引行数、范围说明） |
| `report.md` | 人读报告：问题 / 查询计划 / 候选表 / 排除表 / 覆盖 / 遗漏与不确定 |
| `selfcheck.json` | 交付前自查（检查项 + 结论） |
| `run_log.txt` | 运行摘要 |
| `gain_report.json` / `gain_report.md` | 确定性结构对照（非官方分数） |

**契约回填**：case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层；
不给时回填标准键。任何键都写真实值，绝不写 `string`/`object` 类型占位符，也不写 JSON `null`；
列表为空时写 `{"count": 0, "items": [], "note": "..."}` 形式的诚实空值包裹。

**回填样例**（虚构，仅示意）：

```json
{"case_id": "demo-search",
 "status": "answered",
 "output_contract": {
   "case_id": "demo-search",
   "status": "answered",
   "candidates": [{"object_id": "O0001", "locator": "M01#1",
                   "title": "Demo study of query planning", "doi": "10.0000/demo.1",
                   "relevance": {"score": 0.67, "basis": "keyword overlap with the research question"}}],
   "queries": [{"query_id": "Q1", "query": "\"query planning\" AND \"recall\"",
                "intent": "core concepts co-occur", "source": "local_snapshot_replay"}],
   "coverage": {"candidates_found": 1, "distinct_after_dedup": 1, "sources_indexed": 1,
                "quotable_lines": 0, "scope_note": "scoped to the supplied snapshot; no live remote coverage is claimed"},
   "missing": [{"item": "key reference", "reason": "the supplied snapshot did not include it"}],
   "sources": [{"id": "M01", "name": "materials/sample-records.json", "kind": "json",
                "parse_status": "parsed", "records": 1, "lines": 0}],
   "uncertainty": ["only the supplied snapshot was searched; remote coverage is not claimed"],
   "change_records": [{"step": 1, "action": "scan", "result": "1 file(s) indexed"}]},
 "candidates": ["see output_contract.candidates"],
 "queries": ["see output_contract.queries"]}
```

---

## 6. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 无材料 | 缺口报告，`input_error` |
| 只有空文件 / 坏 JSON / 短笔记 | 无可筛选记录 | `insufficient_evidence` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 退回目录名并记 `degradations` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键（`case_id/status/candidates/queries/coverage/missing/sources/uncertainty/change_records`） |
| 未知单位 / 无 DOI / 无摘要 | 解析不足 | 保留原值并记入 `uncertainty`，不猜测补全 |
| 输出目录不可写 | OSError | 走兜底 `input_error` 产物，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] 每条候选带 `source_id#n` locator 与相关性依据；被排除项与遗漏项都有原因。
- [ ] `queries.jsonl` / `screening.json` / `coverage.json` 均非空且可互相核对。
- [ ] 空语料 / 坏文件 / 无候选三条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] 两次运行按稳定键排序后结果一致，时间戳不参与判等。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的 24 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties` / `missing`，绝不静默提升为完整成功。

---

## 8. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、口径、契约、降级、自查
scripts/main.py                入口：all / init / show / check / build / selfcheck / compare
references/expert_playbook.md  专家参考手册：八步框架/量化口径/陷阱/交付物/自查表（执行前必读）
references/retrieval-guide.md  查询规划、去重与排序的可复用模板
environment/resources.yaml     资源入口声明（命令、路径、无网络、纯标准库）
examples/case.json             最小可复跑样例：case_id + output_contract + research_question
examples/materials/sample-records.json  最小可复跑样例材料（含候选，跑出 answered）
examples/expected_output.json  示意输出（标明为虚构示例）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GAIN_EVIDENCE.md               无 Skill 基线与使用增益证据（确定性 baseline_sim，非官方对照）
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`json`/`re`/`csv`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 1.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
- 复跑样例：`python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work`（应得 `status=answered`）。
