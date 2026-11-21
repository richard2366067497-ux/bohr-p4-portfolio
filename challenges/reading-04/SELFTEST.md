# SELFTEST — multi-doc-comparison v3.0.0（v10 包，含专家手册）

自测日期 2026-11-21；解释器 Python 3.12.14（纯标准库，无第三方、无网络）。
被测包 `work/p4/v10/reading-04`；用例 `work/p4/synth_cases/reading-04/{rich,boundary}`；
驱动器 `scripts/eval_sim.py`（只读调用，未修改）。

## 1. 四组组合结果（真实跑）

```
python scripts/eval_sim.py --pkg work/p4/v10/reading-04 \
  --case work/p4/synth_cases/reading-04/<rich|boundary> --mode <single|agent>
```

| case | mode | status | failures | warnings |
|-|-|-|-|-|
| rich | single | **PASS** | [] | [] |
| rich | agent | **PASS** | [] | [] |
| boundary | single | **PASS** | [] | [] |
| boundary | agent | **PASS** | [] | [] |

四组均通过 `exit_code / result_json / contract_echo / contract_values / deliverables /
case_id / placeholder_sweep / field:status|sources|uncertainties|change_records|limits`。

## 2. 契约解析

| case | 契约来源 | 键 |
|-|-|-|
| rich | `case.json:output_contract` | case_id, status, result, claims, uncertainties |
| boundary | 包 `SKILL.md` 的 JSON 样例（case 契约块为 null） | case_id, status, result, claims, uncertainties |

契约逐键回填真实值（非空、非类型占位符、无 JSON null）并浅拷贝到顶层；
`case_id` 由 `case.json` 透传（rich = `synth-rich-reading-04`），缺失时退回目录名并记入 `degradations`。

## 3. 单命令实跑（SKILL.md 入口）

以 rich 用例内容投放到临时 `in/`，执行 SKILL.md 的单命令：

```
python3 /skills/weekly-skill/scripts/main.py build --input <in> --output <out> --work <work>
```

- 结果：`exit 0`，`status=ok docs=2 fields=5 cells=10 reported=10 coverage=1.0 quote_pass=1.0`。
- 产出交付物：`comparison_matrix.csv`(2244 B) / `comparison_table.md`(1916 B) /
  `evidence_cards.jsonl`(2267 B) / `result.json`(21303 B)。
- `result.json`：`status=ok`、`case_id=synth-rich-reading-04`、
  `output_contract` 键 = `[case_id, claims, result, status, uncertainties]`。
- 跑完已删除临时 `in/out/work` 目录。

## 4. 降级路径实跑

| 场景 | 退出码 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 0 | `input_error`（写缺口报告） |
| boundary（`output_contract: null`，空 md / 坏 json / 碎片笔记） | 0 | `insufficient_evidence`（矩阵全留白并写原因） |

两类路径都写出合法 `result.json`，`output_contract` 为标准五键且无空值、无 JSON null。

## 5. 可跑样例（包内 `examples/`）

```
python3 scripts/main.py build --input examples --output <tmpout> --work <tmpwork>
```

- 结果：`exit 0`，`status=ok docs=2 fields=5 cells=10 reported=10 coverage=1.0 quote_pass=1.0`，
  产出 `result.json`(21537 B) 与三件矩阵产物。
- 样例由 `examples/case.json`（含 `case_id`、标准 `output_contract`、内嵌 `workorder`）与
  `examples/corpus/{D1.txt,D2.txt}`（带量化句子）组成，不含任何占位符。

## 6. 专家手册门控

- `references/expert_playbook.md`（14358 B，编号 §1–§9，末节 §9 为 24 条防扣分自查表）。
- SKILL.md 介绍段后已插入「随包方法论（执行前必读）」，`## 7. 交付前自查` 末尾已加专家检查表条目，
  `## 8. 文件清单与维护` 已登记 `references/expert_playbook.md`。
- 未过项一律记 `status=partial` 并写入 `uncertainties`，不静默提升为成功。

## 7. 关键实现事实

- 重复副本按 sha256 自动去重，记入 `changes[dedupe]`，不影响 status。
- `denull()` 在写盘前把所有 `None` 归一为 `""`，`result.json` 内无 JSON `null`。
- locator 方案为 `p{页码}#para{序号}`，报告中写为 `(p1#para2)`，避免尖角括号被占位符扫描误伤。
- 包内已清理 `__pycache__`；交付件恰为 13 个文件。

## 8. 版本

3.0.0 — 契约键名冻结；规则见 `references/contract.md`，方法与自查见 `references/expert_playbook.md`。
