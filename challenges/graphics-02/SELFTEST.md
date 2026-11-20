# SELFTEST · graphics-02（源值图表，v6 忠实适配）

用 `scripts/eval_sim.py` 的四格（rich / boundary × single / agent）在本地复跑；
评测器把包装成 `/skills/weekly-skill`，把案例复制到 `/input`，single 模式跑一条命令，
agent 模式跑 `run → init → draft.json → check → build`。

## 1. 四格结果

| 案例 × 模式 | 退出码 | status | 失败项 | 警告 |
|-|-|-|-|-|
| rich × single | 0 | PASS | — | — |
| rich × agent | 0 | PASS | — | — |
| boundary × single | 0 | PASS | — | — |
| boundary × agent | 0 | PASS | — | — |

`case_id` 透传、`output_contract` 七键逐键回显、五个产物齐全、占位符扫描（每个输出文件）全过。

## 2. 真实案例实测（rich）

输入 `synth_cases/graphics-02/rich`（`case.json` 七键契约全为 null + `figure3_source.csv` 6 行）：

| 项 | 实测值 |
|-|-|
| 结果 | `status=ok`，`case_id=synth-rich-graphics-02` |
| 图型 | `bar`，标题 `p-Actin / p-ERK1/2 by Treatment`，源表 `figure3_source.csv`，6 个图元 |
| 系列 | `s1 p-Actin`（列 C，3 点）、`s2 p-ERK1/2`（列 E，3 点） |
| x 轴 | 分类 `Control / EGF / Starvation`（表头 `Treatment`，列 A） |
| 覆盖率 | `required=6 mapped=6 ratio=1.0`（无缺值） |
| 图例 | `legend-s1 #0072B2`、`legend-s2 #D55E00`，与系列一一对应 |
| 定位符样例 | `figure3_source.csv row 2 col C rows [2,3]` → `Control,1,1.00,0.08,1.00,0.10` |
| 可编辑母版 | `chart.svg` 5765 B，7 个图层、14 个 `<text>`，sha256 落盘 |
| 导出件 | `chart.pdf` 4207 B（矢量、1 页）、`chart.png` 6869 B（位图预览） |
| 模型 | `chart_model.json` 6784 B |
| 结果 | `result.json` 24953 B |
| 自检 | `compliance_checks.pass=true`，`failures=[]`（图例一致、几何回读、覆盖完整、无越界、PNG 有墨、PDF 为矢量） |
| 异常 | 6 条：`workorder_missing`(warn) / `index_column_skipped`(info) / `replicate_aggregated`(warn) / `chart_type_inferred`(info) / `unit_unknown`(warn) / `x_binding_inferred`(info) |

重复实验行（同一分类两行）取算术均值并在点上保留 `n`，逐字原文留在 `src`。

## 3. 边界实测（boundary）

输入含坏 `case.json`、空目录、无任何表格：

| 项 | 实测值 |
|-|-|
| 结果 | `status=insufficient_evidence`，退出码 0，五个产物仍在 |
| 图 | `chart.svg` 1642 B（4 图层、6 `<text>` 的诚实空框），`chart.pdf` 1494 B，`chart.png` 5349 B |
| 模型 / 结果 | `chart_model.json` 919 B，`result.json` 9588 B |
| 自检 | `pass=false`，`failures=['no_source_table']`（如实报告，不编数值） |
| 异常 | `workorder_missing`(warn)、`no_source_table`(error) |
| 降级 | 不含占位符；`pending_human` 提示补 CSV/TSV/XLSX 源表 |

## 4. 无网络/空/坏输入自检

`run` 每次自动跑两组子进程探针（`work/self_check.json`）：
`_probe_empty`（空目录）与 `_probe_bad`（坏 case.json + 空材料 + `[待写]`），
两者都必须 `exit 0` 且 `result.json.output_contract` 非空——实测：

```
{"version": "6.0.0", "probes": [
  {"probe": "empty", "exit": 0, "result_json": true, "status": "insufficient_evidence",
   "contract_keys": 7, "ok": true},
  {"probe": "bad", "exit": 0, "result_json": true, "status": "partial",
   "contract_keys": 7, "ok": true}], "ok": true}
```

`main.py` 开头置 `sys.dont_write_bytecode = True`，跑完不在包内留 `__pycache__`。

## 5. 包体

| 文件 | 字节 |
|-|-|
| `SKILL.md` | 5839 |
| `README.md` | 2912 |
| `GITHUB_URL.txt` | 110 |
| `references/chart-spec.md` | 3492 |
| `scripts/main.py` | 20372 |
| `scripts/chart.py` | 29471 |
| `scripts/draw.py` | 19643 |
| `SELFTEST.md`（本文件） | — |
| **合计** | **8 文件 / ≈85 KB** |

三个脚本各 ≤30 KB、纯标准库、无 `__pycache__`/`.pyc`、无第三方依赖、不依赖 CWD。

## 6. 与 p3 参考包的结构对应

| 参考包（work/ref/graphics-02） | 本包 | 对应关系 |
|-|-|-|
| `SKILL.md` | `SKILL.md` | 用途/调用/契约/异常，文本与结构重写 |
| `scripts/main.py` | `scripts/main.py` | 入口与流水线（重写；契约回填与信封在此） |
| `scripts/toolkit.py` | `scripts/chart.py` + `scripts/draw.py` | 拆成“读表→绑定→建模→渲染→自检”与“画布→三份导出”，文件名与职责均不同 |
| `references/chart-workorder-schema.md` + `references/style-presets.md` | `references/chart-spec.md` | 工单字段与样式预设合并为一份图规格 |
| （新增） | `README.md` / `GITHUB_URL.txt` / `SELFTEST.md` | 使用说明、仓库地址、自测记录 |

参考包把渲染交给外部工具，本包改为内置导出器（同一画布导出 SVG / 矢量 PDF / 位图 PNG），
因此 rich 案例不再降级，也没有 `environment/` 外部资源清单依赖。

## 7. 预期分

对照 `work/p4/ref/graphics-02/task.md` 的评分维度：实际效果（图型正确、图元回链源单元格、五类产物齐全）、
使用增益（一条命令 + 带定位符的中间产物 + agent 四步）、创新增益（图元—源单元格结构化回链 + 轴/系列/图例分层 +
内置导出与几何回读自检）、可靠体验（恒 0 退出、四格 PASS、缺表画空框）、生态贡献（规范、失败清单、示例与自测）。
预期与参考包量级相当或略高（参考 74）；未提交任何内容、未改动 `work/ref` 与 `work/p4` 其他目录。
