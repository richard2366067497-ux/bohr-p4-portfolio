# SELFTEST — scientific-figure-parser (v6 · reading-02)

移植自 p3 `reading-02`；正文与实现重写。以下结果由 `scripts/eval_sim.py` 本地验收复现。

## 1. 验收矩阵（rich / boundary × single / agent）

命令：

```
python3 scripts/eval_sim.py --pkg work/p4/v6/reading-02 --case work/p4/synth_cases/reading-02/<rich|boundary> --mode <single|agent>
```

| 组合 | 结果 | fail | warn | 输出文件数 | 关键观察 |
|-|-|-|-|-|-|
| rich / single | PASS | 0 | 0 | 6 | `status=answered`，figures=1 tables=1 claims=11 points=960 errors=0 |
| rich / agent | PASS | 0 | 0 | 6 | 草稿合并后结论仍全部通过引文校验 |
| boundary / single | PASS | 0 | 0 | 5 | `status=insufficient_evidence`，`issue: json_unreadable` 记入 errors |
| boundary / agent | PASS | 0 | 0 | 5 | 坏材料仅影响可读项，其余流程照常 |

四组均 `exit 0`、`result.json` 合法、无占位符、产物齐全且非空壳。

## 2. 边界行为

| 场景 | 观察 |
|-|-|
| rich 材料 | `answered`；`digitized_series.csv` 960 点；`tables/T01.csv` 与 `tables.json` 同源 |
| boundary 材料（坏 JSON + 空文件 + 碎片笔记） | `insufficient_evidence` + 缺口清单，退出码 0 |
| `--input` 不存在 | `input_error` + 缺口报告，退出码 0 |

## 3. 契约来源

- rich/boundary 的 `case.json` 带 `output_contract`（6 键：`case_id/status/result/claims/uncertainties/figure_tables_digest`），
  以 `source=case.json:output_contract`、`echo_required=true` 回填；
- 缺契约时回退到 `SKILL.md` §5 的 ```json 示例形状，逐键给真实值；
- 任何路径都先过 `denull()`，输出中无 JSON `null`、无 `<...>` 标记。

## 4. 实现要点

- 纯标准库 PNG 解码（`zlib` 解 `IDAT` + 逐行反滤波 + 调色板展开），仅 8bit 非交错；
- 定标 `value = a·px + b` 最小二乘，`log` 轴先取 `log10` 拟合再还原；可用刻度 <2 放弃数字化；
- 每列命中像素取 y 均值，同时保留 `px/py` 与 `x/y`；
- 结论层按 `quote_type` 分流校验：`text` 归一字面比对、`json` 查 `table_id`、`visual` 比对图标识；
- 首遍即写合法 `result.json`，末尾无条件覆盖；致命异常兜底后仍写盘并 exit 0。
