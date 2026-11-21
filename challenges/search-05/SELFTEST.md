# SELFTEST — search-05 / multi-db-joint-retrieval（v10）

自测对象：`scripts/eval_sim.py`（同仓库），模拟官方评测：安装本 Skill 到 `/skills/weekly-skill`，
投放 `work/p4/synth_cases/search-05/{rich,boundary}`，按 `SKILL.md` 记录的入口命令运行，
检查退出码、`result.json`、契约回显、产物、`case_id`、占位符扫描与
`status/sources/uncertainties/change_records/limits` 字段。

## 1. 评测组合结果（实测）

| 组合 | 契约来源 | 契约键 | 退出码 | 产物 | 占位符 | 结论 |
|---|---|---|---|---|---|---|
| rich / single | `case.json:output_contract` | 6 | 0 | 6/6 | 0 | **PASS** |
| rich / agent | `case.json:output_contract` | 6 | 0 | 6/6 | 0 | **PASS** |
| boundary / single | `SKILL.md (json sample)` | 6 | 0 | 6/6 | 0 | **PASS** |
| boundary / agent | `SKILL.md (json sample)` | 6 | 0 | 6/6 | 0 | **PASS** |

四组均 `failures=[]`、`warnings=[]`。

- `rich` 的 `output_contract` 为 6 键（`case_id / deliverable / evidence_map / change_log / coverage / status`），
  键名照抄，取值替换为真实值（`deliverable=report.md`、`evidence_map/change_log/coverage` 为非空结构）。
- `boundary` 的 `output_contract` 为 null，回退到 `SKILL.md` 的 JSON 契约样例（同 6 键），逐键非空回填。

## 2. 入口与降级路径

| 路径 | 命令 | 退出码 | 说明 |
|---|---|---|---|
| 单命令（评测入口） | `main.py --input /input --output /app/output --work /app/work` | 0 | 等价 `all`，写全部 6 个产物 |
| agent-first | `init → show → check → build → selfcheck` | 0（各步） | 每步都写合法产物 |
| 打包示例 | `main.py --input examples --output /tmp/out --work /tmp/work` | 0 | `status=answered`，2 库 / 4 记录 → 3 唯一 |
| 空语料 / 坏文件 | 空文件 + 坏 JSON + 10 字节文本 | 0 | `insufficient_evidence` + 缺口说明 |
| `case.json` 缺失 | 无 `case.json` | 0 | `case_id` 退回目录名，写 `degradations` |
| argparse 用法错误 | 非法子命令 | 2 | 唯一非 0 退出码 |

## 3. 确定性

同输入重跑两次，`result.json` / `coverage.json` / `dedup_report.json` 规范化后一致：
候选按「相关性降序、rid 升序」排序，组（`G001…`）与 locator（`D01#rN`）不随时间变化。

## 4. 复跑命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v10/search-05 --case work/p4/synth_cases/search-05/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/search-05 --case work/p4/synth_cases/search-05/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v10/search-05 --case work/p4/synth_cases/search-05/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/search-05 --case work/p4/synth_cases/search-05/boundary --mode agent
python3 -B work/p4/v10/search-05/scripts/main.py --input work/p4/v10/search-05/examples --output /tmp/out --work /tmp/work
```

## 5. 资源约束

- 文件数 12（≤ 14）；单文件 ≤ 30 KB；总字节 ≤ 150 KB。
- 纯标准库（`json`/`re`/`hashlib`/`argparse`），无网络、无第三方依赖、无符号链接。
