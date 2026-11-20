# literature-knowledge-graph — reading-14 (v9)

把一个小型论文语料读成**可核验的文献知识图谱**：每个实体/关系都带自己的
`source_id#paragraph_id` locator 与逐字引文；候选节点/关系必须能在原文**逐字命中**才被保留，
否则以原因记入 `uncertainty.json`；跨文献同名只在「归一化 surface + 类型一致」时合并并记录依据，
泛化术语（如 `accuracy`）在不同取值/条件下**拒绝合并**并记为冲突；至少执行 3 条真实查询；
不可读文件（空/二进制/占位）只记 `parse_status`，永不引用。纯标准库、离线、确定性。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 draft，也会写出**全部**产物与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M02/p7 定位符读原文，按需填 /app/work/draft.json（照抄 init 生成的骨架）
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`compare` 把「基线散文 vs 本 Skill 结构化图谱」的对照写到 `/app/work/compare_report.json`。

## 3. 产物

写入 `--output`：`result.json`、`graph.json`、`annotations.jsonl`、`query_results.json`、
`queries.md`、`alignment_report.json`、`conflicts.json`、`sources.json`、`uncertainty.json`、
`change_log.json`、`coverage.json`、`self_check.json`、`run_log.txt`。
`result.json` 的 `output_contract` 键**同时**出现在顶层与 `output_contract` 对象内，`case_id` 原样透传。

## 4. 契约键

默认键（当 `case.json` 未给 `output_contract` 时）：
`case_id, status, graph, merges, conflicts, queries, sources, uncertainty, change_records`。
若 `/input/case.json` 自带 `output_contract`，则**以它为准**逐键回填：指向产物的键解析为真实文件路径，
其余键给出真实派生值。`status ∈ {answered, partial, insufficient_evidence, input_error}`。

## 5. 输入约定

- **语料清单**：JSON 的 `documents`（source_id、doi、title、authors、license、content_sha256）。
- **段落材料**：JSON 的 `source_id` + `paragraphs`（paragraph_id、section、text），可多份。
- **候选图（可选）**：JSON 的 `nodes`（local_id、source_id、paragraph_id、surface、type、aliases、evidence、attributes）
  与 `edges`（source_local、target_local、relation、source_id、paragraph_id、evidence、conditions）。
- **查询**：JSON 的 `queries`（query_id、type、surface），type ∈ find_surface/outgoing/incoming/conflicts。
- 不可用文件（二进制/空/占位）只记录 `parse_status`，永不引用。

## 6. 目录

```
SKILL.md                              # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
scripts/main.py                       # CLI 入口：all / init / show / check / build / selfcheck / compare
scripts/kglib.py                      # 引擎：扫描 / 逐字 grounding / 别名对齐 / 查询 / 产物（仅标准库）
environment/resources.yaml            # 资源入口声明：入口命令、路径、输入约定、契约、运行时
templates/result_contract.json        # 可复用契约骨架
templates/knowledge_graph_template.json  # 可复用的节点/边/查询骨架（含 locator 与引文字段）
examples/case.json  examples/params.json # 自带示例：两份合成段落 + 候选图 + 查询
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 7. 字段与口径（field contract）

| 字段 | 定义 | 口径/边界 |
|-|-|-|
| locator | `source_id#paragraph_id`（如 `primary#p1`） | 每条节点/边**自带** locator；解析失败即拒绝该候选 |
| evidence | 原文一句**逐字**引文 | 必须在 locator 段落中逐字命中，否则拒绝并记原因 |
| concept_id | 对齐后的概念 id（`C-<normalised surface>`） | 同 surface+同 type 才合并；否则各自独立 |
| merge.basis | 合并依据 | 写明归一化 surface、类型、来源数与共享别名 |
| conflict | 跨文献冲突 | 泛化术语取值/条件分歧 → 记冲突，不合并为一个结论 |
| query.status | `answered` / `no_match` | 无命中时如实写 `no_match` 与 undetermined 说明 |
| unit/条件 | 关系 `conditions`、属性 | 保留原文条件（如样本量、split），不臆造 |

## 8. 基准用例与评分口径（benchmark + scoring，可复用）

- `examples/`（`case.json` + `params.json`）：两份合成段落 + 一个候选图 + 3 条查询，是**示例**，不是正式案例结果。
- 评分维度映射（对应官方五维）：
  - 实际效果：`graph.json` + `annotations.jsonl` + `query_results.json` + `alignment_report.json` +
    `conflicts.json` 覆盖实体/关系/别名合并/冲突/查询；每条带 locator 与逐字引文。
  - 使用增益：`compare_report.json` 给出「基线散文 vs 本 Skill 结构化图谱」的可核验差；详见 `GAIN_EVIDENCE.md`。
  - 创新增益：逐字 grounding + 拒绝合并 + 泛化术语冲突分离（见 §9）。
  - 可靠体验：空/坏/占位输入诚实降级为 `insufficient_evidence`；未命中候选记原因；`SELFTEST.md` 有稳定性证据。
  - 生态贡献：SKILL.md、模板、示例、字段口径齐全，可换成新语料复跑。

## 9. 方法与新增能力（innovation）

(a) **逐字 grounding**：节点/边必须带 `source_id#paragraph_id` 与逐字引文，解析失败即拒绝；
(b) **别名对齐与拒绝**：只在归一化 surface + 类型一致时合并，同 surface 多类型则拒绝；
(c) **冲突分离**：泛化术语（accuracy 等）在不同取值/条件下不合并为一个结论，按来源并列报告；
(d) **真实查询**：find_surface / outgoing / incoming / conflicts 四类查询返回子图与 undetermined。
**价值边界**：只做字面 surface+type 对齐，不做语义蕴含；同名不等同于同一样本/模型/条件；
材料未写明的关系方向不臆造。

## 10. 降级与诚实性

- 无可 grounding 的节点/边 → `status=insufficient_evidence`；每个产物带结构化 no-data 记录并说明检索位置；exit 0。
- 候选的段落/引文/surface 不匹配 → 拒绝并记原因到 `uncertainty.json`，绝不保留为节点。
- 未命中查询 → 如实写 `no_match` 与 undetermined，不编造子图。
- 无网络、无第三方依赖、不编造文献与数字。

## 11. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟、结果确定性可复现。详见 `environment/resources.yaml`。
