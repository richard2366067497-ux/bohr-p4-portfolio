# SELFTEST — figure-data-extractor（reading-02 v10）

本文件记录 **2026-11-21** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一次按 SKILL.md 单命令入口的实跑。所有评测均为
**PASS（0 WARN，0 FAIL）**。

## 复现命令

`$PY` 指本机 Python 解释器（`D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe`）；
在仓库根目录执行：

```powershell
& $PY scripts\eval_sim.py --pkg work\p4\v10\reading-02 --case work\p4\synth_cases\reading-02\rich     --mode single --out work\p4\eval_sim\_runs\v10_reading-02__rich__single     --json-out work\p4\eval_sim\_runs\v10_reading-02__rich__single\report.json
& $PY scripts\eval_sim.py --pkg work\p4\v10\reading-02 --case work\p4\synth_cases\reading-02\rich     --mode agent  --out work\p4\eval_sim\_runs\v10_reading-02__rich__agent      --json-out work\p4\eval_sim\_runs\v10_reading-02__rich__agent\report.json
& $PY scripts\eval_sim.py --pkg work\p4\v10\reading-02 --case work\p4\synth_cases\reading-02\boundary --mode single --out work\p4\eval_sim\_runs\v10_reading-02__boundary__single --json-out work\p4\eval_sim\_runs\v10_reading-02__boundary__single\report.json
& $PY scripts\eval_sim.py --pkg work\p4\v10\reading-02 --case work\p4\synth_cases\reading-02\boundary --mode agent  --out work\p4\eval_sim\_runs\v10_reading-02__boundary__agent  --json-out work\p4\eval_sim\_runs\v10_reading-02__boundary__agent\report.json
```

结果读取（避免 PowerShell 中文路径编码问题）：

```powershell
& $PY -c "import json;d=json.load(open(r'<report.json>',encoding='utf-8'));print(d['status'],d['failures'],d['warnings'])"
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | result.status |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 6 键（case_id, status, result, claims, uncertainties, figure_tables_digest） | 9 | answered |
| rich | agent | PASS | case.json:output_contract | 同上 6 键 | 9 | answered |
| boundary | single | PASS | SKILL.md (json sample) | 10 键（case_id, status, result, figures, digitized_series, tables, evidence_map, claims, uncertainties, coverage） | 8 | insufficient_evidence |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 10 键 | 8 | insufficient_evidence |

四组的 `failures` 与 `warnings` 均为空。逐项检查（每组均 PASS）：`exit_code`、`result_json`、
`contract_echo`、`contract_values`、`deliverables`、`case_id`、`placeholder_sweep`、
`field:{status,sources,uncertainties,change_records,limits}`。

> rich 用例是一张双系列折线图（`fig1.md`，红=A、蓝=B）+ 几何 sidecar + 表 `T01`：轴标定成功
> （x: 0–8 mm，y: 0–100 N），逐列颜色匹配得到 **81** 个数字化点；两条文本引文逐字命中 **2/2**，
> 视觉引文锚定 `bbox_px`，`status=answered`，`anchor_hit_rate=1.0`。
> boundary 用例（空文件 + 坏 JSON + 占位文本）无图形几何/表/claim，诚实降级为
> `insufficient_evidence`；`degradations` 明确记录无 sidecar、无图像、无表格三项缺口，产物全部带
> 结构化 no-data 记录。

## 单命令实跑（SKILL.md 入口）

按 SKILL.md 文档的单命令入口，在包内临时目录 `_smoke\{in,out,work}` 用 rich 用例内容实跑：

```powershell
& $PY work\p4\v10\reading-02\scripts\main.py all --input work\p4\v10\reading-02\_smoke\in --output work\p4\v10\reading-02\_smoke\out --work work\p4\v10\reading-02\_smoke\work
```

结果：**exit 0**；`result.json.status=answered`，`case_id=synth-rich-reading-02`，6 个契约键全部回填；
输出 **9** 个文件：`result.json`、`readings.md`、`figure_structure.json`、`digitized_series.csv`、
`tables.json`、`evidence_map.json`、`coverage.json`、`run_log.txt`、`tables/T01.csv`。
运行结束后 `_smoke` 已删除。

## 包内方法论的生效路径

- `SKILL.md` 在第一个编号小节前插入“随包方法论”，要求执行前阅读 `references/expert_playbook.md`，
  按 §2 的冻结产物与门控推进、按 §6 排雷、按 §9 自查表门控。
- `references/expert_playbook.md` 含 9 个编号章节，末节 `## 9. 防扣分自查表` 共 **20** 条可勾选清单
  （≥15 条要求）；含完整虚构案例 `demo-plot-03`，其像素、标定斜率、数据点、表值与容差可独立复算。
- `SKILL.md` 末尾新增“交付前自查”与“文件清单与维护”，frontmatter `version: 3.0.0`。

## 边界行为核对（异常处理）

- `boundary`（空文件 + 坏 JSON + 占位文本）：无图形几何/表/claim，`status=insufficient_evidence`；
  `readings.md`/`figure_structure.json`/`tables.json`/`evidence_map.json`/`coverage.json`/
  `digitized_series.csv` 用带原因的诚实 no-data 结构（CSV 也写一条说明行而非空文件）。
- 坏 JSON（`broken.json`）：解析失败 → 不作素材，不被引用。
- 占位文本（`notes.txt`）：`parse_status=placeholder-only`，跳过且净化，不出现在任何产物。
- 指令文件（`task.md`）：显式排除在图形/表格来源之外。
- 无坐标刻度 / 无量测图（tick 缺失）：标定失败 → 记 `digitize_note`，曲线不数字化，
  `status=partial`（图/表/claim 仍照报）。
- 图像被裁剪 / 图例缺失 / 单位不明 / 图像过曝 / 曲线重叠：颜色匹配失败或越界像素列被跳过，
  不误报数值；冲突单位与不可判定项写入 `uncertainties`。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`；顶层异常也保全 `result.json`。
- 无 `draft.json`：`build`/`all` 使用确定性抽取规则，仍产出全部产物；`draft_used=false`。

## 产物清单（每次运行写入 --output）

result.json、readings.md、figure_structure.json、digitized_series.csv、tables.json、evidence_map.json、
coverage.json、run_log.txt（+ 每张表一份 tables/<id>.csv）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
