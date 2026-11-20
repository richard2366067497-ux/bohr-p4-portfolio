# SELFTEST — writing-09-results-discussion

本包的自测记录：单命令入口、离线自测、eval_sim 矩阵、降级路径与产物字节。退出码恒为 0。

## 1 一键复现

```bash
python3 scripts/main.py --selftest                                                    # 离线自测 19 项
python3 scripts/main.py --input <case>/rich     --output /tmp/out --work /tmp/wk      # 单命令
python3 scripts/main.py --input <case>/boundary --output /tmp/out --work /tmp/wk      # 边界材料
python3 scripts/main.py --version                                                     # 版本
```

## 2 eval_sim 矩阵

`scripts/eval_sim.py --pkg <pkg> --case work/p4/synth_cases/writing-09/{rich,boundary} --mode {single,agent}`：

| 案例 | 模式 | status | 契约来源 / 键数 | 产物 | 非 PASS 检查 |
|-|-|-|-|-|-|
| rich | single | PASS | `case.json:output_contract` 5/5 | 8 | 0 |
| rich | agent | PASS | `case.json:output_contract` 5/5 | 8 | 0 |
| boundary | single | PASS | `references/schema.md` JSON 样例 5/5 | 8 | 0 |
| boundary | agent | PASS | `references/schema.md` JSON 样例 5/5 | 8 | 0 |

检查项全 PASS：`exit_code`、`result_json`、`contract_echo`、`contract_values`、`deliverables`、
`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 3 离线自测（`--selftest`，19 项）

| 组 | 覆盖项 |
|-|-|
| 解析 | `pdf_text_layer`、`png_header`、`broken_json_degraded` |
| 流水线 | `exit_status`、`contract_filled`、8 个 `artifact:*`、`svg_preview_has_text` |
| 图像材料 | `bitmap_inventoried`、`png_manual_confirm` |
| 指标与清洁 | `baseline_metrics`、`no_causal_wording`、`no_placeholder_tokens` |

一次实测输出：`SELFTEST PASS (19 checks)`，退出码 0。

## 4 降级路径

| 场景 | 观察结果 |
|-|-|
| 无材料 | exit 0；`status=failed`；仍写 `manuscript.md` + `result.json`（`limits` 非空） |
| 材料无读数 | `status=partial`；Results 只写缺口；`human_review` 提示人工确认读数 |
| 坏 JSON | `degradations` 记 `json_parse_failed`；其余材料照常处理 |
| 位图图 | `degradations` 记 `bitmap_needs_manual_read`（含尺寸）；`human_review` 加人工读数项 |
| 扫描 PDF（无文本层） | `degradations` 记 `no_text_layer`；提示手工录入数值 |
| 输出目录不可写 | 回退到 cwd 下 `output/` |

## 5 产物字节（rich / boundary 实测）

rich：8 件产物，`manuscript.md` 与 `preview.svg` 均非空，`metrics.json.pass=true`。
boundary：8 件产物，`status=partial`，`degradations` 记 1 条坏文件，`result.json` 契约键齐全。
两者 `placeholder_sweep` 均为 0。
