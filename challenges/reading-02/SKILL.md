---
name: figure-data-extractor
version: 3.0.0
description: >-
  Read a scientific figure and its tables into structured, unit-carrying data that
  stays traceable: recover axis type (linear/log), tick origin and interval, units and
  the legend-to-series mapping; calibrate pixels to data coordinates from the tick
  positions and digitize each curve by colour matching; copy table cells verbatim and
  take the unit from the column header; give every value and every conclusion a locator
  (table_id / json_pointer / bbox_px) plus a quote, and separate "read directly" from
  "inferred" and "undetermined". Use when a task asks for 科研图表解析 / 曲线数据提取 /
  坐标轴与单位识别 / 图表结构化 with a reproducible reading path. Pure standard library,
  offline, deterministic.
---

# figure-data-extractor

A chart must be read into numbers you can check, not into a paragraph. This skill keeps the
figure's own geometry (axis type, ticks, units, legend), calibrates pixels to data coordinates,
digitizes each series by colour, copies table cells verbatim, and anchors every value and claim to
a locator. Anything the figure does not report stays `undetermined`; nothing is invented.

---

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按手册的求解框架（含每步冻结产物与门控）推进；前一步未冻结不进入下一步。
- **口径**：按手册的字段、单位与公式口径逐项核验；原值、原单位与换算值分开保存，不跨来源补值。
- **陷阱**：按手册的领域陷阱清单逐条排雷（错误做法 → 正确做法）。
- **门控**：交付前逐项通过手册 **§9 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为成功。

---

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its
`output_contract` object; `case_id` is passed through unchanged. When the case supplies its
own `output_contract`, those keys are used instead and each is filled the same way (an
artifact-like key resolves to the written file, any other key gets a real derived value).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "answered | partial | insufficient_evidence | input_error",
    "result": "readings.md",
    "figures": "figure_structure.json",
    "digitized_series": "digitized_series.csv",
    "tables": "tables.json",
    "evidence_map": "evidence_map.json",
    "claims": "the locator-anchored claims",
    "uncertainties": "what the reading could not ground",
    "coverage": "coverage.json"
  }
}
```

## 1. Draft schema (JSON, optional)

An agent may fill `/app/work/draft.json` with its own reading of the figure; `build` merges it for
provenance, and the deterministic extractor still runs regardless, so a thin draft cannot turn an
unreadable figure into a fabricated number.

```json
{
  "case_id": "",
  "figures": [],
  "tables": [],
  "claims": [],
  "uncertainties": []
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete
`result.json`, and exits 0:

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. agent-first 增强路径（可选，质量更高）

List the material with locators, fill the draft above, then check it before `build` merges it:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints each source line with a `M02/p9` locator; `check` reports whether grounded figure,
table and claim items exist; `compare` writes a base-vs-skill contrast to `/app/work/compare_report.json`.

## 4. Pipeline

1. Index every file under `/input` with its kind, size and parse status (`parsed` /
   `empty-file` / `placeholder-only` / `image-ok` / `unparsed-binary`).
2. Read the figure-geometry sidecar (a JSON material with a `figures` map) and the table material
   (a JSON material with `tables`); a combined `{material, readings}` file is accepted.
3. Build a pixel-to-data calibration per axis from the tick pixel positions and tick labels,
   honouring `linear` and `log` scale.
4. Decode the figure PNG (stdlib zlib un-filter) and digitize each series by colour matching,
   mapping every matched pixel column through the calibration into data coordinates.
5. Copy table cells verbatim from the material; the column header carries the unit.
6. Anchor every claim to a locator and verify each text quote verbatim against the material text.
7. Compute coverage (figures, tables, series, digitized points, anchor hit rate) and write artifacts.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, digest, claims, sources, uncertainties, change_records, artifacts |
| `readings.md` | per-figure geometry + digitized counts + tables + locator-anchored claims |
| `figure_structure.json` | axes (label/unit/scale/ticks), legend, elements, series, digitized counts, digitize note |
| `digitized_series.csv` | one row per digitized point: series, x, y, x_px, y_px |
| `tables.json` | every table (id, caption, columns, rows) copied verbatim |
| `evidence_map.json` | per-claim locator, quote, quote_type, read_basis, verbatim flag |
| `coverage.json` | figures, tables, claims, series, digitized points, anchor hit rate |
| `run_log.txt` | per-material parse status and the stage counts |

## 6. Degradation rules

- No figure geometry, table or claim → `status=insufficient_evidence`; every artifact carries a
  structured no-data record naming the searched locations; exit 0.
- A figure with no decodable image (or a palette/16-bit PNG) → geometry is still reported from the
  sidecar and `digitize_note` records why the curve was not pixel-digitized; `status=partial`.
- A text quote that does not match the material → reported `verbatim=false` rather than passed as
  grounded; a visual quote (`quote_type=visual`) anchors to a `bbox_px`, never to text.
- Empty / binary / placeholder-only file → recorded with its parse status, never quoted.
- No network, no third-party package, no invented numbers.

## 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 `null`。
- [ ] 每条 claim / 结论都带 `locator`（页码/图号/子图/坐标轴/数据点）与逐字引用。
- [ ] 区分“图中直接可读 / 合理推断 / 无法确定”，缺失项如实记 `partial`，不构造数据。
- [ ] 空输入 / 全是坏文件两条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为成功。

## 文件清单与维护

- `SKILL.md` — 本文件：入口、契约、口径、降级、自查
- `scripts/main.py` — 单命令入口与流程编排、契约组装
- `references/expert_playbook.md` — 专家参考手册（执行前必读）
- `environment/resources.yaml` — 资源入口声明
- `templates/` — 结果契约与笔记模板
- `examples/` — 最小可跑样例
- `README.md` / `SELFTEST.md` / `GAIN_EVIDENCE.md` / `GITHUB_URL.txt`
- 依赖：Python 3.9+ 标准库；无第三方、无网络、无外部模型。
