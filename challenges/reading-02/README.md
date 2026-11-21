# figure-data-extractor — reading-02 (v10)

把一张科研图（含原表）读成**可核验的结构化数据**：还原坐标轴类型（线性/对数）、刻度起点与间隔、
单位量级；从刻度像素位置标定「像素→数据坐标」；按**颜色匹配**把每条曲线数字化；表头给出单位、
单元格逐字抄录；每个数值与结论都带 **locator**（`table_id` / `json_pointer` / `bbox_px`）与引文，
并区分「直接可读 / 视觉定位 / 无法确定」。纯标准库、离线、确定性。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 draft，也会写出**全部**产物与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M02/p9 定位符读原文，按需填 /app/work/draft.json（照抄 init 生成的骨架）
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`compare` 把「基线 vs 加载 Skill」的对照写到 `/app/work/compare_report.json`。

## 3. 产物

写入 `--output`：`result.json`、`readings.md`、`figure_structure.json`、`digitized_series.csv`、
`tables.json`、`evidence_map.json`、`coverage.json`、`run_log.txt`，以及 `tables/<id>.csv`（每张表一份）。
`result.json` 的 `output_contract` 键**同时**出现在顶层与 `output_contract` 对象内，`case_id` 原样透传。

## 4. 契约键

默认键（当 `case.json` 未给 `output_contract` 时）：
`case_id, status, result, figures, digitized_series, tables, evidence_map, claims, uncertainties, coverage`。
若 `/input/case.json` 自带 `output_contract`，则**以它为准**逐键回填：指向产物的键解析为真实文件路径，
其余键给出真实派生值（如 `claims` 给出带 locator 的条目、`figure_tables_digest` 给出图/表/系列/D 点摘要）。
`status ∈ {answered, partial, insufficient_evidence, input_error}`。

## 5. 输入约定

- **图形几何 sidecar**：一个 JSON 材料的 `figures` 映射，给出 `axes`（label、unit、scale、`tick_px`、
  `tick_labels`）、`legend`、`elements`、`series`（name、rgb、tol）。也接受 `{material, readings}` 合并式文件。
- **表格材料**：一个 JSON 材料的 `paragraphs` + `tables`（table_id、caption、columns、rows）；单元格逐字抄录。
- **图像**：图形名对应的 PNG；标准库解 PNG（8-bit 真彩/灰度，非隔行）后逐列颜色匹配。
- 不可用文件（二进制/空/占位）只记录 `parse_status`，永不引用。

## 6. 目录

```
SKILL.md                              # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
references/expert_playbook.md         # 专家参考手册：方法、口径、陷阱、虚构案例、防扣分自查表
scripts/main.py                       # 单文件 CLI：all / init / show / check / build / selfcheck / compare
environment/resources.yaml            # 资源入口声明：入口命令、路径、输入约定、契约、运行时
examples/case.json  examples/params.json  examples/fig1.png   # 自带示例：一图一表 + 几何 sidecar
templates/result_contract.json        # 可复用契约骨架
templates/reading_notes_template.md   # 可复用读数记录模板
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 7. 误差口径与字段定义（field contract）

| 字段 | 定义 | 误差/边界口径 |
|-|-|-|
| 数值 | 表单元格逐字抄，或曲线上像素列经标定后取中位 y | 不给误差线的系列不臆造误差；`±`/SD 原样保留 |
| 单位 | 取列表头/轴标签的单位；不把 mV 当 V、不把对数轴当线性轴 | 单位缺失或与表头冲突则记入 `uncertainties` |
| 坐标轴类型 | `linear` / `log`，由 sidecar 声明并在标定中执行 | 对数轴取 log10 后再线性插值 |
| locator | `json_pointer`（表）/ `bbox_px`（视觉）/ `table_id`、`panel` | 文本引文必须**逐字命中**；视觉引文锚定 bbox |

## 8. 基准用例与评分口径（benchmark + scoring，可复用）

- `examples/`（`case.json` + `params.json` + `fig1.png`）：一图两系列 + 一表，是**示例**，不是正式案例结果。
- 评分维度映射（对应官方五维）：
  - 实际效果：`readings.md` + `figure_structure.json` + `digitized_series.csv` + `tables.json` 覆盖
    坐标轴/刻度/单位/图例/系列/数据点/误差线/显著性/比例尺/子图编号；`evidence_map.json` 给每值一个 locator 与逐字引文。
  - 使用增益：`compare_report.json` 给出「基线散文 vs 本 Skill 结构化条目」的可核验差；详见 `GAIN_EVIDENCE.md`。
  - 创新增益：像素→数据坐标标定、颜色匹配曲线数字化、图例↔系列匹配、文字↔视觉双通道引文核验（见 §9）。
  - 可靠体验：空/坏/占位输入诚实降级为 `insufficient_evidence`；无图或无 sidecar 降级为 `partial` 并记原因；`SELFTEST.md` 有稳定性证据。
  - 生态贡献：SKILL.md、模板、示例、误差口径齐全，可换成新图复跑。

## 9. 方法与新增能力（innovation）

相对「让基础 Agent 直接读图」的通用方案，本 Skill 提供可复算的新增能力：
(a) **轴标定**：由 `tick_px`+`tick_labels` 现算线性/对数映射，而非目测读点；
(b) **曲线数字化**：解 PNG 后逐像素列颜色匹配，落成 CSV；
(c) **图例↔系列匹配**：以 rgb 指纹绑定图例条目与曲线颜色；
(d) **双通道引文核验**：文本引文逐字校验（`verbatim`），视觉引文锚定 `bbox_px`。
**价值边界**：颜色接近或与轴/网格同色的重叠曲线难以分离；调色板/16-bit/隔行 PNG 不解（记 `digitize_note` 并降级为 `partial`）。

## 10. 降级与诚实性

- 无图形几何、无表、无 claim → `status=insufficient_evidence`；每个产物带结构化 no-data 记录并说明检索位置；exit 0。
- 无图或无 sidecar 时可数字化失败 → 记 `digitize_note`，`status=partial`。
- 引文与材料不匹配 → 记 `verbatim=false`，不当作有据可依。
- 无网络、无第三方依赖、不编造数字。

## 11. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟、结果确定性可复现。详见 `environment/resources.yaml`。
