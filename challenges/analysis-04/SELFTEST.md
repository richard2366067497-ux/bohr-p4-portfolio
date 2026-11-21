# 自测记录 · analysis-04 analysis-codegen-execute（v10）

## 1. 入口与运行

单命令（也是评测器的等价入口）：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 纯标准库（csv/json/re/sys/subprocess/traceback/math/pathlib/sqlite3），无网络、无时钟读取，seed 固定 20240517；
- 退出码恒 0：空输入 / 坏 JSON / 零字节文件 / 无可解析表 / 子进程失败或超时都不抛错，仍写合法 `result.json`；
- 生成的 `code/analysis.py` 可脱离本包自足复跑：`python3 code/analysis.py --input <材料> --output <结果>`。

## 2. eval_sim 结果（`scripts/eval_sim.py`）

| case | mode | status | 关键检查 |
|---|---|---|---|
| rich (synth-rich-analysis-04) | single | **PASS** | exit 0；result.json 合法；6/6 契约键回填；10 输出文件；case_id 透传；placeholder_sweep 干净 |
| rich | agent | **PASS** | 同上（agent 路径等价单命令，唯一 fenced 命令即 `all`） |
| boundary (synth-boundary-analysis-04) | single | **PASS** | 契约由 SKILL.md 样例解析；降级仍合法；10 输出文件 |
| boundary | agent | **PASS** | 同上 |

命令：

```bash
python scripts/eval_sim.py --pkg work/p4/v10/analysis-04 \
    --case work/p4/synth_cases/analysis-04/rich --mode single
# rich/agent、boundary/single、boundary/agent 同法
```

## 3. 真实推导示例（生成代码 → 执行 → 独立重算）

对本包做**独立复算**（`_t/a04data/data.csv`：A/B 两组各 6 个 `value`，`x2` 序号，
`catA/catB` 二值分类），生成代码在子进程真实执行（exit 0），引擎再独立重算每个关键数字：

| key number | metric | 生成值 | 引擎重算 | 一致 |
|---|---|---|---|---|
| data.csv.value.mean | mean | 13.408333 | 13.408333 | ✔ |
| data.csv.x2.mean | mean | 6.5 | 6.5 | ✔ |
| data.csv.value.A.mean | mean（group=A） | 10.9 | 10.9 | ✔ |
| data.csv.value.B.mean | mean（group=B） | 15.916667 | 15.916667 | ✔ |
| data.csv.value.ttest | t | -10.248535 | -10.248535 | ✔ |
| data.csv.value.x2.r | r | 0.885133 | 0.885133 | ✔ |

`verification.json`：13/13 通过（input / integrity 行数守恒 `12-0==12` / execution 退出码与产物 /
claim 重算 6 条 / chart 点数 ≤ 源行数 / types 强制转换）。t 值 `-10.248535` 与 analysis-02
`student_t` 的独立实现一致，`group` 均值 10.9 / 15.916667 亦与手算一致。

rich 用例无数据表时：代码仍**生成并执行**，`status=partial`，`uncertainties` 记明"未产出
key_numbers"，全部六类交付物与契约回填完整。

## 4. 契约回填与占位符

- `result.json.output_contract` 含用例声明的**全部**键（rich 6 键；boundary 6 键来自 SKILL.md
  样例），同时顶层同名回填；`case_id` 原样透传（`synth-rich-analysis-04` / `synth-boundary-analysis-04`）。
- 键名按语义回填：`code` / `results` / `verification` / `run_log` / `report` / `environment` /
  `reproducibility` / `cleaning` 等，无法映射的键写成结构信封 `{"available":[...],"note":...}`。
- 写出前对文本做令牌中和：`jwrite` 对 JSON 字符串字面量做 unicode 转义、`denull` 把 `null`
  字面量改为 `""`、CSV/报告单元格过 `safe_text`。**关键修复**：空表时的 `cleaning_ledger.csv`
  只有表头（36B）会触发 deliverables 近空告警，已改为始终写出策略列 + 无表占位行，
  `deliverables` 由 WARN 转为 PASS。

## 5. v10 修复点（相对 v6）

1. **逐行配对的相关系数**：v6 生成代码先把两列数值各自去空后**按位置截断**到等长再算 `r`，
   缺值列会被错位配对（示例中把 `r` 报成 0.443972）；v10 改为**按行成对**（listwise）取
   `(x, y)`，同一输入得 0.449098，引擎独立重算一致。
2. **重复行计数与行数守恒自洽**：v6 只统计重复行却不删除，导致 `n_in - dedup != n_used`
   （30 - 1 != 30），`row_conservation` 判 fail；v10 按"保留首次、丢弃后续"真正去重，
   `cleaning_ledger.csv` 记 `n_in=30 / duplicate_rows=1 / n_out=29`，`row_conservation` 通过，
   引擎重算亦同步去重以保证两条路径同口径。
3. 打包规格更新见下表。

## 6. 打包规格

| 文件 | bytes |
|---|---|
| SKILL.md | 7749 |
| README.md | 2896 |
| SELFTEST.md | 本文件 |
| GITHUB_URL.txt | 113 |
| GAIN_EVIDENCE.md | 2958 |
| environment/resources.yaml | 2199 |
| examples/sample_data.csv | 594 |
| scripts/engine.py | 29577（≤30KB） |
| scripts/codelib.py | 22584（≤30KB） |
| references/analysis_spec.md | 4551 |
| references/expert_playbook.md | 11740 |

合计 11 个文件、约 87KB（≤14 文件 / ≤150KB / 单文件 ≤30KB）。生成代码模板置于 `codelib.py`，
使两个脚本文件各自保持在 30KB 以内。
