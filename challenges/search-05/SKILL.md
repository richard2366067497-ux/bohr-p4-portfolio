---
name: multi-db-joint-retrieval
description: >-
  Multi-database joint retrieval. Retrieve and screen literature for a research
  question across several snapshot databases, normalize fields (missing vs unknown),
  deduplicate by DOI-exact then fuzzy key, merge duplicate versions with documented
  priority rules, compare coverage across databases, keep an evidence map with
  locators and verbatim quotes, and echo every output_contract key the case declares
  (never a type placeholder). Single-command entry all is equivalent to the
  init/show/check/build/selfcheck workflow; pure standard library, offline,
  deterministic, exit 0 even on empty or corrupt input. Use when a task asks for
  多数据库联合检索 / 去重与合并 / 字段规范化 / 覆盖度对照 / 筛选依据留痕.
version: 1.0.0
---

# multi-db-joint-retrieval — 多数据库联合检索（search-05 v10）

一句话：**把多个快照库的检索结果规范化、去重合并、对照覆盖，只交付能被独立复核的证据图。**

它把“联合检索”变成一条可回链的流水线：
解析 → 库编排 → 字段规范化 → 去重（DOI 精确 + 模糊键）→ 合并（字段优先级）→ 覆盖度对照 →
证据图 → 报告 + `result.json`。不编造文献，不虚构 DOI，不声称覆盖远程数据库。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` / 参数自定位，不依赖当前目录。

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 七步流水线（含门控）** 推进——输入解析 → 库编排 → 字段规范化 →
  去重 → 合并 → 覆盖度对照 → 输出打包；前一步未冻结不进入下一步。
- **口径**：按其 **§3 量化口径** 计算 N_raw / N_unique / 去重率 / 字段覆盖率 C_f / 可追溯率 T（目标 100%）/
  字段冲突解决率 / 单源率，每条候选的取舍依据必须可回查。
- **陷阱**：按其 **§4 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）；不得把“字段缺失”写成未知、
  不得把不同库的同名记录直接当重复、不得把共现当证据。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainty` / `missing`，绝不静默提升为完整成功。

---

## 1. 单命令（single command，等价入口，评测入口）

```
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

该命令等价于 `main.py all`，按顺序执行：

1. **parse**：发现 `--input` 下全部材料（`case.json` / `task.md` 除外），识别研究问题与库清单；
2. **normalize**：按库抽取文献记录，字段规范化（缺失 ≠ 未知），登记 `source_id#n` locator；
3. **dedup**：先 DOI 精确判重，再按 `norm_title|first_author_surname|year` 模糊判重；
4. **merge**：同类记录合并，按字段优先级补齐，保留合并依据；
5. **coverage**：计算去重率、字段覆盖率、单源率与子问题覆盖；
6. **evidence_map**：为每个子问题保留 `locator` + 逐字 quote 的证据图；
7. **save/verify**：写出全部产物 + `result.json`（契约逐键回填 + `case_id` 透传）→ 占位符净化 → exit 0。

无需 `draft.json`；空输入、坏 JSON、缺 `case.json` 同样 exit 0 并写合法 `result.json`。

---

## 2. 五命令工作流（等价入口，Agent 深读时质量更高）

```
python3 -B /skills/weekly-skill/scripts/main.py init       # 扫描输入、写 partial result.json 与 draft 骨架
python3 -B /skills/weekly-skill/scripts/main.py show       # 打印带 locator 的段落 / 记录（--grep/--limit）
python3 -B /skills/weekly-skill/scripts/main.py check      # 校验 draft 子问题 / 决策 / rid 合法性
python3 -B /skills/weekly-skill/scripts/main.py build      # 组装产物并定稿 result.json
python3 -B /skills/weekly-skill/scripts/main.py selfcheck  # 复检产物一致性与非空
```

五条命令与 `all` 共用同一引擎；全局参数 `--input / --output / --work` 可放子命令前或后。

---

## 3. result.json 约定（片段示例，键名冻结）

```
{
  "case_id": "synth-case",
  "status": "answered",
  "output_contract": {
    "case_id": "synth-case",
    "status": "answered",
    "deliverable": "report.md",
    "evidence_map": [{"subquestion_id": "SQ1", "subquestion": "text", "records": [{"rid": "R001", "locator": "D01#r1", "source_db": "crossref", "quote": "verbatim span"}]}],
    "change_log": [{"at": "1970-01-01T00:00:00+00:00", "step": "parse", "note": "read the supplied materials"}],
    "coverage": {"n_raw": 5, "n_unique": 4, "dedup_rate": 0.2, "field_coverage": {"doi": 1.0, "year": 1.0, "title": 1.0}, "coverage_rate": 1.0}
  }
}
```

**契约回填**：case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层；不给时回填标准键。
任何键都写真实值，绝不写 `string` / `path` / `array` / `object` 类型占位符，也不写 JSON `null`；
路径键指向真实非空文件；`case_id` 原样透传；`status` 取 `answered / partial / insufficient_evidence / input_error` 之一，
并给非空 `sources / uncertainty / change_records / limits`。

---

## 4. 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、databases、sources、候选、证据图、去重/合并、覆盖度、change_log、limits、uncertainty |
| `candidates.jsonl` | 逐条候选（rid、source_db、locator、relevance、decision、basis、quote） |
| `evidence_map.json` | 每个子问题的证据图（locator + 逐字 quote） |
| `dedup_report.json` | 去重组与合并日志（依据可回查） |
| `coverage.json` | N_raw / N_unique / 去重率 / 字段覆盖率 / 单源率 / 子问题覆盖 |
| `report.md` | 人类可读报告（库、筛选、覆盖、限制） |

---

## 5. 输入

- `--input`（默认 `/input`）：`case.json`（可含 `case_id`、`research_question`、`output_contract`）与任意
  UTF-8 文本材料（每个材料视为一个“库”，其文件名即库名）。`task.md` 用于推断研究问题。
- 无 `case.json` 时按材料文本推断问题；无材料时给诚实的空候选与 `insufficient_evidence`。

---

## 6. 异常与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`，不编造文献。
- 无可解析记录：候选与证据图给带说明的诚实空结构，`degradations` 记录原因。
- 未知单位 / 无 DOI / 无摘要：保留原值并记入 `uncertainty`，不猜测补全。
- 任何阶段异常：捕获后保留 partial `result.json`（含 `errors`、`traceback_tail`）并 exit 0。
- 不联网、不安装工具、不臆造元数据；结论限定在“所给快照内”，不宣称全局召回。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] `deliverable` 指向真实非空文件；`evidence_map / change_log / coverage` 为非空 array/object。
- [ ] 每条候选带 `source_id#n` locator 与相关性依据；被排除项与遗漏项都有原因。
- [ ] 去重先 DOI 精确、再模糊键；合并保留依据、可回查（`dedup_report.json`）。
- [ ] 字段缺失与“未知”区分；不猜补 DOI / 年份 / 作者。
- [ ] 覆盖度给出 N_raw / N_unique / 去重率 / 字段覆盖率 / 单源率与理由。
- [ ] 空语料 / 坏文件 / 无候选三条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] 两次运行按稳定键排序后结果一致，时间戳不参与判等。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainty` / `missing`，绝不静默提升为完整成功。

---

## 8. 文件清单与维护

```
SKILL.md                        本文件：入口、双路径、口径、契约、降级、自查
scripts/main.py                 入口：all / init / show / check / build / selfcheck
references/expert_playbook.md   专家参考手册：七步流水线/量化口径/陷阱/交付物/自查表（执行前必读）
environment/resources.yaml      资源入口声明（命令、路径、无网络、纯标准库）
examples/case.json              最小可复跑样例：case_id + research_question + output_contract
examples/expected_output.json   示意输出（标明为虚构示例）
examples/materials/             多库演示快照（两个“库”文件）
README.md / SELFTEST.md / GAIN_EVIDENCE.md / GITHUB_URL.txt
```

- 依赖：Python 3.9+ 标准库（`json`/`re`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 1.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
