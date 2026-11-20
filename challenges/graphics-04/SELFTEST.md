# SELFTEST · graphics-04（装置与工艺路线图，v6 忠实适配）

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

输入 `synth_cases/graphics-04/rich`（`case.json` 七键契约全为 null + `material.md` 549 B）：

| 项 | 实测值 |
|-|-|
| 结果 | `status=ok`，`case_id=synth-rich-graphics-04` |
| 抽到的结构 | 部件 4、连接 3、步骤 4，`coverage.verified_rate=1.0`（条目全部带定位符与逐字原文） |
| 定位符样例 | `S1:L5` → `进料储罐：1 个，出口接蠕动泵。` |
| 图例 | material（实线 #1f5fa8）、energy（虚线 #c1440e）——只列图上真用到的介质 |
| 可编辑母版 | `figure.svg` 6544 B，8 个图层、26 个 `<text>`，sha256 落盘 |
| 导出件 | `figure.pdf` 5496 B（矢量、1 页、MediaBox 1080×~410 pt）、`figure.png` 9889 B（1440×~547、96 dpi） |
| 模型 | `figure_model.json` 6621 B |
| 结果 | `result.json` 27136 B |
| 自检 | `compliance_checks.pass=true`，`failures=[]`（悬空连接 0、步骤号连续、id 覆盖全、图例一致、无越界、确定性 true） |
| 异常 | 5 条：`parts_from_material` / `connections_from_material` / `steps_from_material`（info）、`figure_kind_inferred`（minor）、`workorder_missing`（warn） |

## 3. 边界实测（boundary）

输入含坏 `case.json`、空 `empty.md`、只有 `[待写]` 的 `notes.txt`：

| 项 | 实测值 |
|-|-|
| 结果 | `status=insufficient_evidence`，退出码 0，五个产物仍在（`figure.svg` 1549 B 空框） |
| 自检 | `pass=false`，`failures=['no_drawable_entities']`（诚实报告，不编造装置） |
| 异常 | `figure_kind_inferred`、`workorder_missing`、`no_drawable_entities`（blocking） |
| 降级 | 坏 `case.json` 记 `case_json_unreadable`，读空的文件记 `material_unreadable`，不含占位符 |

## 4. 无网络/空/坏输入自检

`run` 每次自动跑两组子进程探针（`/app/work/self_check.json`）：
`_probe_empty`（空目录）与 `_probe_bad`（坏 case.json + 空材料 + `[待写]`），
两者都必须 `exit 0` 且 `result.json.output_contract` 非空——实测 `ok=true`。

## 5. 包体

| 文件 | 字节 |
|-|-|
| `SKILL.md` | 6453 |
| `README.md` | 3538 |
| `GITHUB_URL.txt` | 110 |
| `references/figure-spec.md` | 5140 |
| `scripts/main.py` | 19488 |
| `scripts/sheet.py` | 29632 |
| `scripts/draw.py` | 19789 |
| `SELFTEST.md`（本文件） | — |
| **合计** | **8 文件 / ≈87 KB** |

三个脚本各 ≤30 KB、纯标准库、无 `__pycache__`/`.pyc`、无第三方依赖、不依赖 CWD。

## 6. 与 p3 参考包的结构对应

| 参考包（work/ref/graphics-04） | 本包 | 对应关系 |
|-|-|-|
| `SKILL.md` | `SKILL.md` | 用途/调用/契约/异常，文本与结构重写 |
| `scripts/main.py` | `scripts/main.py` | 入口与流水线（重写；契约回填与信封在此） |
| `scripts/render.py` | `scripts/sheet.py` + `scripts/draw.py` | 拆成“材料→模型→画面”与“画布→三份导出”，文件名与职责均不同 |
| `references/figspec.md` | `references/figure-spec.md` | 图规格（工单、定位符、介质、自检） |
| `references/export-presets.md` | 合并进 `README.md` §产物 | 导出参数（内嵌矢量 PDF / 内置位图 PNG） |
| `references/failure-modes.md` | 合并进 `references/figure-spec.md` §8 | 失败与降级清单 |
| （新增） | `README.md` / `GITHUB_URL.txt` / `SELFTEST.md` | 使用说明、仓库地址、自测记录 |

参考包依赖外部渲染器（rsvg / soffice / pdftoppm）导出预览，本包改为内置导出器，
因此 rich 案例不再降级；这也是与参考包最大的实现差异。

## 7. 预期分

对照 `work/p4/ref/graphics-04/task.md` 的评分维度：实际效果（结构正确、可核验、四类产物齐全）、
使用增益（一条命令 + 带定位符的中间产物）、创新增益（实体—连接—步骤结构化表示 + 分层布局 + 内置导出校验）、
可靠体验（恒 0 退出、四格 PASS、缺料画空框）、生态贡献（规范、失败清单、示例与自测）。
预期与参考包量级相当或略高（参考 69）；未提交任何内容、未改动 `work/ref` 与 `work/p4` 其他目录。
