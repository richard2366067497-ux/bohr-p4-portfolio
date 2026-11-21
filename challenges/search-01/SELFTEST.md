# SELFTEST — search-01 / traceable-literature-retrieval

自测对象：`scripts/eval_sim.py`（同仓库），模拟官方评测：安装本 Skill 到
`/skills/weekly-skill`，投放 `work/p4/synth_cases/search-01/{rich,boundary}`，
按 `SKILL.md` 记录的入口命令运行，检查退出码、`result.json`、契约回显、产物、`case_id`、
占位符扫描与 status/sources/uncertainties/change_records/limits 字段。

## 1. 评测组合结果

| 组合 | 契约来源 | 契约键 | 退出码 | 产物 | 占位符 | 结论 |
|---|---|---|---|---|---|---|
| rich / single | `case.json:output_contract` | 8 | 0 | 7/7 | 0 | **PASS** |
| boundary / single | `SKILL.md (json sample)` | 9 | 0 | 7/7 | 0 | **PASS** |
| rich / agent | `case.json:output_contract` | 8 | 0 | 7/7 | 0 | **PASS** |
| boundary / agent | `SKILL.md (json sample)` | 9 | 0 | 7/7 | 0 | **PASS** |

四组均 `failures=[]`、`warnings=[]`、`suggestions=[]`。

- `rich` 的 `output_contract` 为 8 键（`expected_output / task_instruction / description /
  authorname / print_date / case_id / candidates / queries`），逐键非空回填。
- `boundary` 的 `output_contract` 为 null，回退到 `SKILL.md` 的 9 键标准契约并逐键回填。

## 2. 入口与降级路径

| 路径 | 命令 | 退出码 | 说明 |
|---|---|---|---|
| 单命令（评测入口） | `main.py --input /input --output /app/output --work /app/work` | 0 | 等价 `all`，写全部产物 |
| agent-first | `init → show → check → build → selfcheck → compare` | 0（各步） | 每步都写合法产物 |
| 打包示例 | `main.py --input examples --output /tmp/out --work /tmp/work` | 0 | `status=answered`，2 候选 / 1 排除 |
| 空语料 / 坏文件 | material 为 empty / 坏 JSON | 0 | `insufficient_evidence` + 缺口说明 |
| `case.json` 缺失 | 无 `case.json` | 0 | `case_id` 退回目录名，写 `degradations` |
| argparse 用法错误 | 非法子命令 | 2 | 唯一非 0 退出码 |

## 3. 确定性

同输入重跑两次，`result.json` / `coverage.json` / `candidates.jsonl` 规范化后一致：
候选按「相关性分值降序、object_id 升序」排序，规范 ID（`O0001…`）与排名不随时间变化。

## 4. 复跑命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v10/search-01 --case work/p4/synth_cases/search-01/rich --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/search-01 --case work/p4/synth_cases/search-01/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/search-01 --case work/p4/synth_cases/search-01/rich --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v10/search-01 --case work/p4/synth_cases/search-01/boundary --mode agent
python3 -B work/p4/v10/search-01/scripts/main.py --input work/p4/v10/search-01/examples \
  --output /tmp/out --work /tmp/work
```

## 5. 资源约束

- 文件数 12（≤ 14）；单文件最大 ~29.8 KB（≤ 30 KB）；总字节约 96 KB（≤ 150 KB）。
- 纯标准库（`json`/`re`/`csv`/`hashlib`/`argparse`），无网络、无第三方依赖、无符号链接。
