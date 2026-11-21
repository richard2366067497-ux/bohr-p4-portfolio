# GAIN_EVIDENCE — experiment-05 / experiment-interpretation-dossier（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。
>
> **两种入口的诚实差异**：单命令 `all`（无 draft）**不会**凭空产生「趋势陈述」与「异常档案」——
> 它只复算统计、索引规则/单位/阈值并给出可由规则自动抬起的候选（本样例 1 条 R1）。因此 `all`
> 在本样例上如实返回 `status=partial`（2 条降级：未声明趋势、未声明档案）。走五命令/`build`
> 并落 `/app/work/draft.json` 后为 `status=answered`。两者都产出全部产物且 exit 0。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`notes.md`：筛检规则 R1–R9、单位量纲字典、判据阈值；`readout.csv`：8 点时间序列，
含一个 148.3 mg/L 的离谱读数）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **只复述读数** —— "20 min 时有 148.3 mg/L，其余约 100"，无方法、无阈值、无幅度。
2. **无量化判据** —— 不区分 Z-score / 修正 z / IQR / Grubbs，不给阈值，不给 |z| 数值。
3. **无定位符** —— 结论不挂 `[文件:行号]`，无法回指原始读数行。
4. **无归因枚举** —— 直接断言"催化剂失活"，不做支持/排除证据，不标 A/B/C 强度。
5. **不复算统计** —— 中位数/MAD/修正 z 均未计算，无法被第二人复现。
6. **无产物与契约** —— 不写 `interpretation.md` / `dossier_index.json`，契约键覆盖 0/12。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：直接取最大值当异常，不做阈值、不做定位、不做归因
import csv, pathlib
rows = list(csv.DictReader(open("examples/readout.csv", encoding="utf-8")))
worst = max(rows, key=lambda r: float(r["phenol_mg_l"]))
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "advice.md").write_text(
    "t=%s min 的读数 %s mg/L 偏高，建议重测。\n" % (worst["time_min"], worst["phenol_mg_l"]),
    encoding="utf-8")
# 无 result.json、无 interpretation.md、无 dossier_index.json、无 thresholds.json、无 evidence.json
```

模拟结果：产物 **1** 件、规则索引 **0**、阈值常量 **0**、单位组 **0**、统计复算 **0**、
逐字证据 **0**、契约键 **0/12**。

---

## 2 加载本 Skill（真实运行）

### 2.1 单命令路径（`all`，无 draft；本样例 `status=partial`）

命令见 §4，实测 exit 0：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **9**（8 件 + `result.json`） |
| 物料 `files` | **3**（case.json / notes.md / readout.csv） |
| 规则索引 `rules` | **6**（R1、R2、R3、R3'、R5、R8'，每条带 locator + 逐字引文） |
| 判据阈值 `thresholds` | **7**（tol_default 0.05 / mad_scale 0.6745 / iqr_k 1.5 / modified_z_cut 3.5 / tol_cross_source / tol_recalibration / tol_calibration） |
| 单位与量纲 `units` | **6 组**（质量浓度 mg/L·g/L、时间 min·h、温度 °C·K、吸光度 AU、波长 nm、摩尔浓度 mol/L·mM） |
| 数值序列 `series` | **2**（`time_min` 8 值、`phenol_mg_l` 8 值） |
| 规则候选 `candidates` | **1**（R1 修正 z，`M03#L6`，severity **high**） |
| 统计自检 `checks` | **4/4 通过**（固定夹具 `[1,2,3,4,100]` 上 7 个定义全部复算一致） |
| 逐字证据 `evidence_stats` | verified **19 / total 19**，rate **1.0** |
| 契约键覆盖 | **12/12**（`id…input_error`，顶层 + `result.output_contract`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=738d10527bbf27e1` |

### 2.2 专家路径（`build` + draft；`status=answered`）

把 §4 的 `draft.json` 落到 `--work` 后运行 `build`（实测 exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| status | **answered** |
| 产物文件数 | **9**（8 件 + `result.json`；另有 `dossiers/anomaly-A-001.md`） |
| 趋势 `trends` | **1**（TR-01，locator `M03#L6`，quote `20,148.3`） |
| 异常档案 `dossiers` | **1**（A-001 · outlier · Cat-X t=20 min 通道 R3 · severity high · verdict confirmed · attribution data_quality · strength B） |
| 原因候选 `causes` | **1**（强度 **B**，含支持证据与排除证据） |
| 契约键覆盖 | **12/12**，占位符 **0** |
| `result.json` 规范化哈希 | `sha256=15fee2b8145dde03` |

关键产物：`interpretation.md`（八节：盘点/趋势/异常/原因/复核/后续/不确定性/方法）、
`dossier_index.json`（每档案的目标/严重度/裁决/归因/强度/locator）、`recompute.json`（固定夹具复算 +
逐序列统计 + 规则候选 + 一致性检查）、`thresholds.json`（阈值并置保留冲突）、`evidence.json`、
`inventory.json`、`uncertainties.json`、`method_notes.md`、`result.json`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件定性建议，无 `result.json` | 9 件成套产物（档案索引/复算/阈值/证据/盘点） | **完成度 / 完整性** |
| 判读正确性 | "取最大值"，无阈值 | R1 修正 z 命中，`M03#L6`，severity high；固定夹具 4/4 自检 | **正确性** |
| 证据可核验 | 无 locator / 无 quote | 19/19 逐字命中，每条结论挂 locator | **可核验性** |
| 契约回填 | 键覆盖 0/12 | 键覆盖 **12/12**（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 可能直接断言"催化剂失活" | 原因标 B 级并写支持+排除证据，`do_not_conclude` 显式禁止；缺失项记 `limits` | **正确性 / 可靠性** |
| 体系性 | 无统一定义，每次口径漂移 | 统计定义可复算、哈希稳定（`738d10527bbf27e1`） | **可靠性** |

**为什么对应 rubric**：完成度＝成套产物 + 契约回填；正确性＝规则筛检 + 阈值常量 + 固定夹具复算；
完整性＝盘点/趋势/档案/阈值/证据/方法齐备；可核验性＝来源 ID + locator + 逐字引文；使用增益＝同
输入下多维同时提升，且诚实区分 `all`（partial）与 `build`（answered）。

---

## 4 复现命令

```bash
# A. 单命令（评测入口；本样例 status=partial，如实记 2 条降级）
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；9 件产物；rules=6, thresholds=7, units=6, series=2, candidates=1(R1, M03#L6, high)
# checks 4/4；evidence 19/19 rate 1.0；契约 12/12；哈希 738d10527bbf27e1

# B. 专家路径（把 draft.json 落到 --work 再 build；status=answered）
python3 scripts/main.py build --input examples --output /tmp/out2 --work /tmp/work
# exit 0；9 件产物 + dossiers/anomaly-A-001.md；trends=1, dossiers=1(A-001, high), causes=1(B)
# 契约 12/12；哈希 15fee2b8145dde03
```

`/tmp/work/draft.json` 的最小形态见随包 `SELFTEST.md` §5。哈希复算：读 `result.json`，
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位。
