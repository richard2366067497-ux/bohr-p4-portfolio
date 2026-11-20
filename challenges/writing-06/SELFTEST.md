# SELFTEST — paper-structure-logic-review（writing-06）

记录本包的自测结果：一键入口、脚本级降级路径、产物字节区间与已知边界。
所有命令用 `python3 <pkg>/scripts/main.py …`；退出码恒为 0（仅 argparse 用法错误为 2）。

## 1. 一键复现

```
# 完整流水线（rich 材料包：只有写作规范，无正文）
python3 <pkg>/scripts/main.py run --input <case>/rich --output /tmp/out --work /tmp/wk

# 边界案例（材料损坏/空文件）
python3 <pkg>/scripts/main.py run --input <case>/boundary --output /tmp/out --work /tmp/wk

# 带正文的稿件（六维逐条诊断）
python3 <pkg>/scripts/main.py run --input <manuscript-dir> --output /tmp/out --work /tmp/wk

# 阶段化：盘点 → 构建 → 校验 → 自查
python3 <pkg>/scripts/main.py probe     --input /input --work /tmp/wk
python3 <pkg>/scripts/main.py build     --input /input --output /tmp/out --work /tmp/wk
python3 <pkg>/scripts/main.py check     --input /input --output /tmp/out --work /tmp/wk
python3 <pkg>/scripts/main.py selfcheck --input /input --output /tmp/out --work /tmp/wk
```

## 2. eval_sim 矩阵

`scripts/eval_sim.py --pkg <pkg> --case <synth_cases/writing-06/{rich,boundary}> --mode {single,agent}`
四条组合的结果：

| 案例 | 模式 | status | failures | warnings | 非 PASS 检查 | 入口识别 |
|-|-|-|-|-|-|-|
| rich | single | PASS | 0 | 0 | 0 | single-command |
| rich | agent | PASS | 0 | 0 | 0 | single-command |
| boundary | single | PASS | 0 | 0 | 0 | single-command |
| boundary | agent | PASS | 0 | 0 | 0 | single-command |

- 契约来源：rich 案例取 `case.json:output_contract`；boundary 取 `SKILL.md (json sample)`，
  回填键为 `unverified / verified / degradations`。
- 全部检查项 PASS：`exit_code`、`result_json`、`contract_echo`、`deliverables`、`case_id`、
  `placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 3. 脚本级降级路径

| 场景 | 命令要点 | 观察结果 |
|-|-|-|
| 空输入目录 | `run --input <empty>` | exit 0；`status=input_error`；`result.json` 合法且契约键齐全 |
| 只有写作规范、无正文 | `run --input <rules-only>` | `status=partial`；六维标为 `not_assessed`；仍给出包级审计（标题/编号/重复句/术语） |
| 无 case.json（只有稿件） | `run --input <manuscript-only>` | exit 0；`status=partial`；`errors[0].stage=case` |
| 稿件六维诊断 | `run --input <manuscript>` | 命中 `section_structure / duplication / conclusion_boundary` 三条 finding，引文核验率 1.0 |
| 阶段化自查 | `selfcheck` | 打印 `{"status": "pass", "missing": [], "empty": []}` |
| 盘点 | `probe` | 写出 `<work>/inventory.json`，stdout 为文件数与角色计数 |

## 4. 产物字节区间（rich / boundary 实测）

| 文件 | rich | boundary |
|-|-|-|
| `structural_review.json` | 8701 | 2272 |
| `edit_plan.md` | 864 | 944 |
| `outline_after.md` | 1289 | 654 |
| `argument_map.json` | 196 | 196 |
| `consistency_report.md` | 1547 | 516 |
| `pending_human.json` | 433 | 568 |
| `result.json` | 5016 | 5618 |

- rich / boundary 均为 `status=partial`：材料包不含正文，六维未审，降级为包级审计而非正文审读。
- 稿件案例：`structural_review.json` 的 `grounding.hit_rate = 1.0`（3 条引文逐字命中），
  `result.json` 在 `output_contract` 中逐键回填，无占位符。

## 5. 已知边界

- 只判结构与措辞，不判断结论在科学上是否成立，也不改写正文。
- 引文必须能在正文逐字命中，命中不了的候选结论直接丢弃；核验率记录在 `grounding`。
- 无正文时降级为包级审计，六个维度标为 `not_assessed`，不把包级审计写成正文审读。
- 每条建议都附风险说明；机械执行仍可能改变原意。
- 输入含 UTF-8 BOM 时按 `utf-8-sig` 读取，BOM 不进入定位符或引文。
