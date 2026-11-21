---
name: citation-trace
description: >-
  Citation tracing / citation-network tracing. From a seed paper, build a citation
  network out of the supplied snapshot, run backward and forward tracing, merge
  preprint / conference / journal identities of the same work, trace depth-limited
  paths, record metadata gaps and out-of-snapshot citations, and echo every
  output_contract key the case declares (never a type placeholder). Single-command
  all entry plus the init/show/check/build/selfcheck workflow; pure standard library,
  offline, deterministic, exit 0 even on empty or corrupt input. Use when a task asks
  for 引文追踪 / 引用网络 / 前后向扩展 / 关联文献发现 / 身份合并 / 路径解释.
version: 1.0.0
---

# citation-trace（search-04 v10）

把一批文献材料整理成**可回链的引用网络**，从种子文献出发追踪前向 / 后向路径，合并同名不同版，
指出元数据缺口与快照外引用。核心约束：每条边保留 `locator`；缺字段如实记录不猜；不宣称全局引文索引。

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 八步框架（含门控）** 推进——读取输入 → 种子身份规范化 → 后向追踪 → 前向追踪 →
  关联发现 → 身份合并 → 排序筛选 → 路径与网络 → 打包；前一步未冻结不进入下一步。
- **口径**：按其 **§3 量化口径** 计算后向覆盖率 / 前向召回率 / 关联精确率与召回率 / 身份合并准确率 /
  路径可信度 / 去重键（`norm_title|first_author_surname|year`），排序得分
  `0.5×引用强度 + 0.3×关联信号 + 0.2×证据可信度`，每条结果必须可回查。
- **陷阱**：按其 **§4 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）；不得把高被引当高相关、
  不得把预印本与期刊版当两篇、不得把文件名或共现当作引用证据。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainty` / `missing`，绝不静默提升为完整成功。

---

## 1. 单命令（single command，等价入口，评测入口）

```
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

该命令等价于 `all`：扫描材料 → 识别文献记录与引用标记 → 建节点 / 边 → 从种子追踪路径 →
缺口 → 报告 + `result.json`（契约逐键回填 + `case_id` 透传）→ 占位符净化 → exit 0。
无需 `draft.json`；空输入、坏 JSON、缺 `case.json` 同样 exit 0 并写合法 `result.json`。

---

## 2. 五命令工作流（等价入口）

```
python3 -B /skills/weekly-skill/scripts/main.py init       # 扫描输入、写 partial result.json 与 draft 骨架
python3 -B /skills/weekly-skill/scripts/main.py show       # 打印带 locator 的段落 / 文献记录（--grep/--limit）
python3 -B /skills/weekly-skill/scripts/main.py check      # 校验 draft 边的 source/target
python3 -B /skills/weekly-skill/scripts/main.py build      # 组装网络/路径/缺口并定稿 result.json
python3 -B /skills/weekly-skill/scripts/main.py selfcheck  # 复检产物一致性
```

五条命令与 `all` 共用同一引擎；全局参数 `--input / --output / --work` 可放子命令前或后。

---

## 3. result.json 约定（片段示例，键名冻结）

```
{
  "case_id": "synth-case",
  "status": "traced",
  "output_contract": {
    "case_id": "synth-case",
    "status": "traced",
    "seed": "M01#r1",
    "citations": 3,
    "edges": [{"source": "M01#p2", "target": "R001", "kind": "cites", "locator": "M01#p2"}],
    "paths": [{"from": "M01#r1", "path": ["M01#r1", "R001"], "depth": 1}],
    "gaps": [{"rid": "R002", "missing_fields": ["doi"], "note": "metadata incomplete in the supplied snapshot; not fabricated"}],
    "network": {"nodes": [{"rid": "R001"}], "edges": []},
    "summary": "nodes 1, edges 1, traced paths 1, gaps 1",
    "report": "report.md",
    "show": {"command": "show", "purpose": "list locator-addressable paragraphs and detected records"},
    "build": {"command": "build", "purpose": "assemble network, paths, gaps and final result"}
  }
}
```

契约键逐键写入 `result.json.output_contract`，并在顶层放同名键；`case_id` 原样透传；`status` 非空；
`sources / uncertainties / change_records / limits` 非空；路径键指向真实非空文件；空集合给带说明的非空结构。

---

## 4. 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、seed、网络、路径、缺口、limits、uncertainty、change_records |
| `citation_network.json` | 节点（文献）与边（cites/lists） |
| `edges.jsonl` | 逐条边（source、target、kind、locator、marker） |
| `traced_paths.json` | 从种子出发的路径与深度 |
| `gaps.json` | 元数据缺口与越界引用 |
| `report.md` | 人类可读报告 |

---

## 5. 输入

- `--input`（默认 `/input`）：`case.json`（可含 `case_id`、`seed`、`output_contract`）与任意 UTF-8 文本材料。
- 文献记录由「含年份的参考文献行」识别，带 `rid` 与 `M01#rN` locator；引用标记 `[n]` / `(Author, 2020)`
  建边；无记录时给诚实的空网络与 `insufficient_evidence`。

---

## 6. 异常与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无引用边 / 无路径：`edges / paths / gaps` 给带 `status`/`note` 的诚实非空结构，`degradations` 记录原因。
- 任何阶段异常：捕获后保留 partial `result.json`（含 `errors`、`traceback_tail`）并 exit 0。
- 不联网、不查询外部引文库、不臆造元数据；结论限定在所给快照内。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] 明确引用方向（前向 / 后向），每条边有 `locator` 与数据源依据。
- [ ] 多层级扩展设停止判据（层级 ≤ 3、每层新增相关比例 < 10% 时停止）。
- [ ] 身份合并保留合并证据（DOI 相同 / 标题相似 / 作者年份匹配）；撤稿与更正单独标记。
- [ ] 每条结果带来源定位（DOI/URL/`source_id#n`）；缺字段如实记录、不猜补。
- [ ] 空结果 / 权限 / 歧义 / 限流等异常有明确处置说明。
- [ ] 空语料 / 坏文件 / 无引用边三条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] 两次运行按稳定键排序后结果一致，时间戳不参与判等。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainty` / `missing`，绝不静默提升为完整成功。

---

## 8. 文件清单与维护

```
SKILL.md                        本文件：入口、双路径、口径、契约、降级、自查
scripts/main.py                 入口：all / init / show / check / build / selfcheck
references/expert_playbook.md   专家参考手册：八步框架/量化口径/陷阱/交付物/自查表（执行前必读）
references/citation-contract.md 契约与 locator 的可复用约定
environment/resources.yaml      资源入口声明（命令、路径、无网络、纯标准库）
examples/case.json              最小可复跑样例：case_id + seed + output_contract
examples/expected_output.json   示意输出（标明为虚构示例）
examples/materials/sample-records.md  含文献记录与引用标记的演示快照
README.md / SELFTEST.md / GAIN_EVIDENCE.md / GITHUB_URL.txt
```

- 依赖：Python 3.9+ 标准库（`json`/`re`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 1.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
