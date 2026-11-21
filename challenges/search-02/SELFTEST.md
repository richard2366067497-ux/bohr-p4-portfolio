# SELFTEST — search-02 / rq-driven-retrieval（v10）

自测对象：`scripts/eval_sim.py`（同仓库），模拟官方评测：安装本 Skill 到 `/skills/weekly-skill`，
投放 `work/p4/synth_cases/search-02/{rich,boundary}`，按 `SKILL.md` 记录的入口命令运行，
检查退出码、`result.json`、契约回显、产物、`case_id`、占位符扫描与
`status/sources/uncertainties/change_records/limits` 字段。

## 1. 评测组合结果（实测）

| 组合 | 契约来源 | 契约键 | 退出码 | 产物 | 占位符 | 结论 |
|---|---|---|---|---|---|---|
| rich / single | `case.json:output_contract` | 16 | 0 | 8/8 | 0 | **PASS** |
| rich / agent | `case.json:output_contract` | 16 | 0 | 8/8 | 0 | **PASS** |
| boundary / single | `SKILL.md (json sample)` | 25 | 0 | 8/8 | 0 | **PASS** |
| boundary / agent | `SKILL.md (json sample)` | 25 | 0 | 8/8 | 0 | **PASS** |

四组均 `failures=[]`、`warnings=[]`。

- `rich` 的 `output_contract` 为 16 键（`contract_overrides / id / type / other / text / queries /
  depends_on / priority / required / rid / subquestion_ids / decision / relevance / quote / locator /
  reason`），逐键非空回填。
- `boundary` 的 `output_contract` 为 null，回退到 `SKILL.md` 的 JSON 契约样例（25 键，含
  `subquestions / candidates / evidence / coverage / search_log / stop_decision / report`），逐键非空回填。

## 2. 入口与降级路径

| 路径 | 命令 | 退出码 | 说明 |
|---|---|---|---|
| 单命令（评测入口） | `main.py --input /input --output /app/output --work /app/work` | 0 | 等价 `all`，写全部 8 个产物 |
| agent-first | `init → show → check → build → selfcheck` | 0（各步） | 每步都写合法产物 |
| 打包示例 | `main.py --input examples --output /tmp/out --work /tmp/work` | 0 | `status=answered`，1 子问题 / 4 候选入选 |
| 空语料 / 坏文件 | 空文件 + 坏 JSON + 10 字节文本 | 0 | `insufficient_evidence` + 缺口说明 |
| `case.json` 缺失 | 无 `case.json` | 0 | `case_id` 退回目录名，写 `degradations` |
| argparse 用法错误 | 非法子命令 | 2 | 唯一非 0 退出码 |

## 3. 确定性

同输入重跑两次，`result.json` / `coverage.json` / `candidates.jsonl` 规范化后一致：
候选按「相关性降序、rid 升序」排序，locator（`M01#rN`）与契约键不随时间变化。

## 4. 复跑命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v10/search-02 --case work/p4/synth_cases/search-02/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/search-02 --case work/p4/synth_cases/search-02/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v10/search-02 --case work/p4/synth_cases/search-02/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/search-02 --case work/p4/synth_cases/search-02/boundary --mode agent
python3 -B work/p4/v10/search-02/scripts/main.py --input work/p4/v10/search-02/examples --output /tmp/out --work /tmp/work
```

## 5. 资源约束

- 文件数 12（≤ 14）；单文件最大 `scripts/main.py` ~30 KB（≤ 30 KB）；总字节 ≤ 150 KB。
- 纯标准库（`json`/`re`/`hashlib`/`argparse`），无网络、无第三方依赖、无符号链接。
