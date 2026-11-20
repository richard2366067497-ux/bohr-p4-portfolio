# SELFTEST — figure-data-extractor（reading-02 v9）

本文件记录 **2026-11-20** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带语料的本地功能用例。所有评测均为
**PASS（0 WARN，0 FAIL）**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v9/reading-02 \
  --case work/p4/synth_cases/reading-02/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-02 \
  --case work/p4/synth_cases/reading-02/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/reading-02 \
  --case work/p4/synth_cases/reading-02/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-02 \
  --case work/p4/synth_cases/reading-02/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | result.status |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 6 键（case_id, status, result, claims, uncertainties, figure_tables_digest） | 9 | answered |
| rich | agent | PASS | case.json:output_contract | 同上 6 键 | 9 | answered |
| boundary | single | PASS | SKILL.md (json sample) | 10 键（case_id, status, result, figures, digitized_series, tables, evidence_map, claims, uncertainties, coverage） | 8 | insufficient_evidence |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 10 键 | 8 | insufficient_evidence |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

> rich 用例的材料是一张双系列折线图（`fig1.png`，红=A、蓝=B）+ 几何 sidecar（`readings.json`）
> + 表 `T01`：轴标定成功（x: 0–8 mm，y: 0–100 N），逐列颜色匹配得到 **81** 个数字化点，
> 两条文本引文逐字命中 **2/2**，视觉引文锚定 `bbox_px`，`status=answered`。
> boundary 用例（空文件 + 坏 JSON + 占位文本）无图形几何/表/claim，诚实降级为
> `insufficient_evidence`，产物全部带结构化 no-data 记录。

## 功能用例（本地，验证「真实标定 + 颜色数字化 + 逐字回链」而非模板）

`examples/`（`case.json` + `params.json` + `fig1.png`）复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：

- exit 0，`result.json.status = answered`，产物 **9** 文件（含 `tables/T01.csv`）。
- 图形 1 张、表 1 张、系列 2 条；轴标定 x: 0–8 mm（线性）、y: 0–100 N（线性）。
- `digitized_series.csv`：**81** 点（A 39 点 0.0→8.0 mm，y 99.65→~0；B 42 点），
  每个点带 `x_px, y_px` 与颜色匹配说明。
- 文本引文逐字命中 **2/2**（`anchor_hit_rate = 1.0`）；`c03` 为视觉引文，`verbatim=false` 且带 `bbox_px`。
- 契约键 **10/10** 逐键回填；占位符扫描 **0**。
- 规范化哈希（`result.json` 删除 `runtime` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`808a12c84e60d762`**。

## 边界行为核对（异常处理）

- `boundary`（空文件 + 坏 JSON + 占位文本）：无图形几何/表/claim，`status=insufficient_evidence`；
  `readings.md`/`figure_structure.json`/`tables.json`/`evidence_map.json`/`coverage.json`/
  `digitized_series.csv` 用带原因的诚实 no-data 结构（CSV 也写一条说明行而非空文件）。
- 坏 JSON（`broken.json`）：`parse_status=parsed` 但解析失败 → 不作素材，不被引用。
- 占位文本（`notes.txt`）：`parse_status=placeholder-only`，跳过且净化，不出现在任何产物。
- 指令文件（`task.md`）：显式排除在图形/表格来源之外。
- 无坐标刻度 / 无量测图（tick 缺失）：`calibrate` 返回空 → 记 `digitize_note`，曲线不数字化，
  `status=partial`（图/表/claim 仍照报）。
- 图像被裁剪 / 图例缺失 / 单位不明 / 图像过曝 / 曲线重叠：颜色匹配失败或越界像素列被跳过，
  不误报数值；冲突单位与不可判定项写入 `uncertainties`。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`；顶层异常也保全 `result.json`。
- 无 `draft.json`：`build`/`all` 使用确定性抽取规则，仍产出全部产物；`draft_used=false`。

## 产物清单（每次运行写入 --output）

result.json、readings.md、figure_structure.json、digitized_series.csv、tables.json、evidence_map.json、
coverage.json、run_log.txt（+ 每张表一份 tables/<id>.csv）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
