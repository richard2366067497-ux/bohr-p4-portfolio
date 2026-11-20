# 自测记录 · analysis-01 field-contract-cleaner（v6）

## 1. 入口与运行

单命令（也是评测器的等价入口）：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 纯标准库（argparse/csv/hashlib/json/re/sqlite3/sys/traceback/pathlib），无网络、无时钟读取；
- 退出码恒 0：空输入 / 坏 JSON / 零字节文件 / 无可解析表都不抛错，仍写合法 `result.json`。

## 2. eval_sim 结果（`scripts/eval_sim.py`）

| case | mode | status | 关键检查 |
|---|---|---|---|
| rich (synth-rich-analysis-01) | single | **PASS** | exit 0；result.json 合法；11/11 契约键回填；7 交付物齐全；case_id 透传；placeholder_sweep 干净 |
| rich | agent | **PASS** | 同上（agent 路径等价于 single，因为唯一 fenced 命令即 `all`） |
| boundary (synth-boundary-analysis-01) | single | **PASS** | 6 契约键（由 SKILL.md 样例解析）全回填；8 输出文件 ≥40B |
| boundary | agent | **PASS** | 同上 |

命令：

```bash
python scripts/eval_sim.py --pkg work/p4/v6/analysis-01 \
    --case work/p4/synth_cases/analysis-01/rich   --mode single
# rich/agent、boundary/single、boundary/agent 同法
```

## 3. 真实推导示例（rich，无数据表 → 由材料推导）

引擎对材料逐项计数，每条带 locator，写入 `result.json.derivations` 与报告 §5：

| 推导 | 值 | locator |
|---|---|---|
| 缺失码词表大小 | 15（`rules.json#missing_tokens`） | 规则文件键 |
| 单位注册表大小 | 解析自 `units` 键的真实条目数 | `<rules>#units` |
| 禁止动作（改值）条数 | 解析自 `forbidden_actions` | `<rules>#forbidden_actions` |
| 问题码定义数 | 解析自 `flag_codes` | `<rules>#flag_codes` |
| 字典字段行数 | markdown 表逐行解析 | `material markdown tables` |
| 行数守恒 | `raw_rows == kept+marked+quarantined` | `reconciliation.json` |

字段契约 `field_contract.json` 为每个字段保留 `basis`（`<file>#L<n>` 或 `<file>#col:<field>`），
报告 §2 与清洗表可回算。

## 4. 契约回填与占位符

- `result.json.output_contract` 含用例声明的**全部**键（rich 11 键，含名为 `none` 的键与
  `missing_tokens` 中的 `na/n/a/null` 令牌），同时顶层同名回填；`case_id` 原样透传。
- 写出前对 JSON 文本做令牌中和（unicode 转义，解码后仍为原文）：原始词表 `-999`、`NA`、
  `N/A`、`None` 等值保真，而文件正文不含占位符令牌；`eval_sim` placeholder_sweep 全部干净。

## 5. 打包规格

| 文件 | bytes |
|---|---|
| SKILL.md | 6192 |
| README.md | ~2500 |
| SELFTEST.md | 本文件 |
| GITHUB_URL.txt | 110 |
| scripts/engine.py | 21475（≤30KB） |
| scripts/cleanlib.py | 13638（≤30KB） |
| references/cleaning-rules.md | 4007 |

合计 7 个文件、约 50KB（≤8 文件 / ≤150KB）。
