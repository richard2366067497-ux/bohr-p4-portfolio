# SELFTEST — latex-free-format-adapter（writing-03）

记录本包的自测结果：一键入口、脚本级降级路径、产物字节区间与已知边界。
所有命令用 `python3 <pkg>/scripts/main.py …`；退出码恒为 0（仅 argparse 用法错误为 2）。

## 1. 一键复现

```
# 完整流水线（rich 案例）
python3 <pkg>/scripts/main.py run --input <case>/rich --output /tmp/out --work /tmp/wk

# 边界案例（材料损坏/空文件/无模板）
python3 <pkg>/scripts/main.py run --input <case>/boundary --output /tmp/out --work /tmp/wk

# 阶段化：盘点 → 构建 → 校验 → 自查
python3 <pkg>/scripts/main.py probe     --input <case>/rich --work /tmp/wk
python3 <pkg>/scripts/main.py build     --input <case>/rich --output /tmp/out --work /tmp/wk
python3 <pkg>/scripts/main.py check     --input <case>/rich --output /tmp/out --work /tmp/wk
python3 <pkg>/scripts/main.py selfcheck --input <case>/rich --output /tmp/out --work /tmp/wk
```

## 2. eval_sim 矩阵

`scripts/eval_sim.py --pkg <pkg> --case <synth_cases/writing-03/{rich,boundary}> --mode {single,agent}`
四条组合的结果：

| 案例 | 模式 | status | failures | warnings | 非 PASS 检查 | 入口识别 |
|-|-|-|-|-|-|-|
| rich | single | PASS | 0 | 0 | 0 | single-command |
| rich | agent | PASS | 0 | 0 | 0 | single-command |
| boundary | single | PASS | 0 | 0 | 0 | single-command |
| boundary | agent | PASS | 0 | 0 | 0 | single-command |

- 契约来源：rich 案例取 `case.json:output_contract`；boundary 取 `SKILL.md (json sample)`，
  回填键为 `case_id / deliverable / preserved_facts / evidence_map / change_log`。
- 全部检查项 PASS：`exit_code`、`result_json`、`contract_echo`、`deliverables`、`case_id`、
  `placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 3. 脚本级降级路径

| 场景 | 命令要点 | 观察结果 |
|-|-|-|
| 空输入目录 | `run --input <empty>` | exit 0；`status=input_error`；`result.json` 合法且 5 个契约键齐全 |
| 无 case.json（只有稿件） | `run --input <materials-only>` | exit 0；`status=partial`；`errors[0].stage=case`；键回落到默认契约 |
| 阶段化自查 | `selfcheck` | 打印 `{"status": "pass", "missing": [], "empty": []}` |
| 盘点 | `probe` | 写出 `<work>/inventory.json`，stdout 为文件数与角色计数 |

## 4. 产物字节区间（rich / boundary 实测）

| 文件 | rich | boundary |
|-|-|-|
| `deliverable.md` | 657 | 1584 |
| `deliverable.docx` | 2649 | 2910 |
| `format_spec.md` | 1032 | 1032 |
| `style_map.json` | 1973 | 1973 |
| `fidelity_report.json` | 1162 | 438 |
| `pending_human.json` | 487 | 881 |
| `result.json` | 19318 | 13317 |

- rich `status=partial`（材料包不含模板与格式要求文件，规格项标为推断）；
  boundary `status=insufficient_evidence`（无可用正文，降级为缺口报告）。
- `result.json` 内含 `sources / uncertainties / change_records / limits / errors / degradations`，
  且在 `output_contract` 中逐键回填，无占位符。

## 5. 已知边界

- docx 只解析 `w:pgMar` / `w:sz` 等可读属性；扫描件模板读不到规格，回落到默认档。
- 证据链依赖参考文献的 DOI 与包内原文片段；缺 DOI 时只判到 `source_not_found`。
- 版面视觉效果未与渲染样本比对，`limits` 中明写该边界。
- 输入含 UTF-8 BOM 时按 `utf-8-sig` 读取，BOM 不进入正文或定位符。
