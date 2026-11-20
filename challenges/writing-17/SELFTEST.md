# SELFTEST — mindmap-builder（writing-17 v6）

> **验证状态（诚实声明）**：本包创作所在的 Windows 主机没有可用的 Python 解释器（仅有 Windows Store
> 占位别名，无 WSL 发行版、无 Node），因此**未能在本机实际执行** `eval_sim.py`。下表“预期”是按
> `eval_sim.py` 的入口抽取 / 契约解析 / 审计规则逐条静态推演得到的，请在 Linux `python3.10` 上按下列
> 命令实跑确认（预期全部 PASS）。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-17 \
  --case work/p4/synth_cases/writing-17/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-17 \
  --case work/p4/synth_cases/writing-17/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-17 \
  --case work/p4/synth_cases/writing-17/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-17 \
  --case work/p4/synth_cases/writing-17/boundary --mode agent
```

## 预期结果（静态推演）

| 用例 | 模式 | 预期状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 5（init, show, check, build, selfcheck） | 5 |
| rich | agent | PASS | case.json:output_contract | 同上 5 键 | 5 |
| boundary | single | PASS | SKILL.md (json sample) | 13（5 + mindmap, nodes, edges, outline, summary, report, case_id, status） | 5 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 13 键 | 5 |

逐项检查（预期均 PASS）：

- `exit_code`：`all`（agent 模式 `all → init → check → build → selfcheck`）均 exit 0。
- `result_json`：合法 JSON，含 `output_contract` 与顶层同名键。
- `contract_echo`：rich 5 键 / boundary 13 键均覆盖（回填取 `case` 键 ∪ 内置规范键的并集）。
- `contract_values`：`init/show/check/build/selfcheck` 为含 `stage`/`status` 的非空 dict；`nodes`/`edges`
  为非空 list（至少根节点/边，空输入时根节点仍在）；`mindmap`→真实 `mindmap.json`、`outline`→`outline.json`、
  `report`→`report.md` 均为真实非空文件；无 empty/placeholder/missing-file。
- `deliverables`：`mindmap.json`、`mindmap.md`、`outline.json`、`report.md`、`result.json` 均存在且 >40 字节。
- `case_id`：`synth-rich-writing-17` / `synth-boundary-writing-17` 原样透传。
- `placeholder_sweep`：文本产物无占位符标记（`init` 内的 `ignore` 等字样不触发模式）。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为

- boundary（`output_contract=null`）：契约回退到 `SKILL.md` 的 JSON 样例（13 键），照常逐键回填。
- 空 `/input` / 无材料：仅根节点，`status=insufficient_evidence`，`degradations` 记录原因，exit 0。
- 坏 JSON / 缺 `case.json`：忽略并以材料自建，exit 0。
- 无标题材料：以文件名为根、正文句子生成叶子，仍产出全部 5 个产物。

## 产物清单

`result.json`、`mindmap.json`、`mindmap.md`、`outline.json`、`report.md`（共 5 个）。

依赖说明：`mindmap.md` 与 `report.md` 内容相同（同一导图正文 + 局限），各自独立写出。

> 以上为按源码推演的预期结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
