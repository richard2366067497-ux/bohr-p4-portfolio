# scientific-figure-parser (v6 · reading-02)

把一张科研图里的曲线读成数、把原表里的格子读成据，并让**每条结论都留下出处**。
本包是 p3 `reading-02` 的忠实移植：入口命令、产物名、`result.json` 字段与契约回填方式保持一致，
正文与实现全部重写，不逐字复用。

## 安装

```
/skills/weekly-skill/
├── SKILL.md
├── scripts/main.py
├── scripts/figurekit.py
├── references/contract.md
├── environment/resources.yaml
├── README.md
├── SELFTEST.md
└── GITHUB_URL.txt
```

只依赖 Python 3.9+ 标准库（`zlib/struct/csv/json/re/hashlib/pathlib`），无第三方包、无网络、无外部模型。
脚本用 `Path(__file__)` 自定位，与当前工作目录无关。

## 用法（单命令全流程）

```
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

`build` 一步做完：发现材料 → 纯标准库解码 PNG → 双轴最小二乘定标 → 按颜色数字化曲线 →
逐列读表 → 逐条立结论（带引文与定位）→ 写出全部产物并把 `output_contract` 逐键回填。
默认值即 `--input /input --output /app/output --work /app/work`。

其它子命令（各自也会重写一份完整 `result.json`）：

| 子命令 | 作用 |
|-|-|
| `build` | 全流程并写产物 |
| `show` | 打印图表/表格/结论清单与引用锚点 |
| `check` | 重跑流程并合并 `work/draft.json`，逐条校验引文 |
| `selfcheck` | 重跑流程并审计 `output_contract` 键是否齐全非空 |

## Agent-first 增益路径

```
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --output /app/output --work /app/work
# Agent 读 figure_structure.json / digitized_series.csv，写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`draft.json` 里给 `claims`，每条须带 `evidence.quote` 与 `source_id`。合并时按 `claim_id` 覆盖同名
确定性结论；引文不过关的条目一律丢弃并计入 `degradations`——Agent 的判读不能绕过取证要求。
缺省或坏 JSON 的草稿自动回退到确定性结果，不报错。

## 产物（`--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 契约回填 + 结构化结果 |
| `figure_structure.json` | 每张图的 caption/axes/legend/series/calibration/digitized |
| `digitized_series.csv` | 数字化长表 `figure_id,panel,series,px,py,x,y,unit_x,unit_y` |
| `tables.json` | 表格结构与摘要（含 `tables/<id>.csv` 逐表副本） |
| `figure_tables_digest.md` | 图表摘要报告 |

## 诚实边界

- 可用刻度少于两个 → 放弃数字化并记 `degradation`，不外推；
- 某序列容差内零命中 → `status: no_pixels` + 降级，不填补；
- PNG 解码失败 / 非 8bit / 交错 → 只保留结构并记降级；
- 引文不在任何材料里 → `error` 级 → 状态降为 `partial`；
- 空输入或坏 JSON → 仍写出合法 `result.json`，退出码恒 0。

## 维护

改动字段名时同步 `references/contract.md` 与 `SKILL.md` 的契约示例；每次改动重跑四组
`eval_sim`（rich/boundary × single/agent）并把结果记入 `SELFTEST.md`。
