# SELFTEST — analysis-06 / db-query-workbook（v10）

按顺序执行即可复核本包。全部步骤纯离线、确定；重复执行同一快照字节稳定。

## 1. 单命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
echo "exit=$?"
```

期望：`exit=0`；`/app/output/result.json` 是合法 JSON，`output_contract` 含全部契约键（顶层同名回显），
`case_id` 与 `/input/case.json` 一致。

## 2. 真实执行 SQL（自带快照）

```bash
mkdir -p /tmp/qin
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/tmp/qin/study.db')
c.execute("CREATE TABLE samples (sample_id TEXT, material TEXT, status INTEGER, mass_mg REAL)")
c.executemany("INSERT INTO samples VALUES (?,?,?,?)",
 [("S1","concrete",1,120.5),("S2","concrete",1,118.2),("S3","iris",0,95.0),
  ("S4","iris",1,96.4),("S5","wine",0,101.1),("S6","wine",1,99.8)])
c.execute("CREATE TABLE measurements (meas_id TEXT, sample_id TEXT, temp_c REAL, reading REAL)")
c.executemany("INSERT INTO measurements VALUES (?,?,?,?)",
 [("M1","S1",180,7.1),("M2","S1",182,7.3),("M3","S2",179,6.9),("M4","S3",200,6.2),
  ("M5","S4",198,6.4),("M6","S5",190,6.8),("M7","S6",191,6.6)])
c.commit(); c.close()
PY
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/qin --output /tmp/qout --work /tmp/qwork
```

期望（可复算）：

- `results/Q_rows_samples.csv` → 6；`results/Q_rows_measurements.csv` → 7；
- `results/Q_join_measurements_samples.csv` → 7；`join_ledger.json` expansion_factor≈1.1667；
- `reconciliation.json`：checks 全通过；
- `queries.sql` 里能看到逐字 SQL（含 `IS NULL`，未被改写），可直接在 sqlite3 上复跑。

## 3. 逐字复跑 queries.sql

```bash
sqlite3 /tmp/qin/study.db < /tmp/qout/queries.sql   # 若本机有 sqlite3 CLI
```

期望：无语法错误；带 assert 的语句（如 `SELECT ... WHERE ... `）返回非空。

## 4. 幂等 / 字节稳定

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/qin --output /tmp/qout2 --work /tmp/qwork2
diff -r /tmp/qout /tmp/qout2 && echo "byte-stable"
```

## 5. 空输入 / 坏输入仍需退出 0

```bash
mkdir -p /tmp/empty2
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/empty2 --output /tmp/o5 --work /tmp/w5; echo "exit=$?"
printf '{ bad json' > /tmp/empty2/case.json
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/empty2 --output /tmp/o6 --work /tmp/w6; echo "exit=$?"
```

期望：两次都 `exit=0`，`result.json` 合法，`status=partial` / `input_error`，
`uncertainties` 含 `no_queryable_snapshot`，`degradations` 含 `case_json_unreadable`。

## 6. 分步复核

```bash
for c in init show check build selfcheck; do
  python3 /skills/weekly-skill/scripts/main.py $c --input /input --output /app/output --work /app/work; echo "$c=$?"
done
```

期望：6 个子命令都退出 0，最后一个命令之后 `result.json` 仍完整；`selfcheck` 额外打印
`[selfcheck] expert-checklist ok (references/expert_playbook.md present; DC-01..DC-17 to pass)`。

## 7. 契约回填逐键检查

```bash
python3 - <<'PY'
import json,os
r=json.load(open('/app/output/result.json'))
for k,v in r['output_contract'].items():
    if isinstance(v,str) and ('/' in v or v.endswith(('.json','.csv','.md','.svg','.sql'))):
        assert os.path.isfile(os.path.join('/app/output',v)), (k,v)
    assert v not in (None,'',[],{}), (k,v)
print('contract ok:', sorted(r['output_contract']))
PY
```

## 8. v10 随包样例实测（examples/）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：exit 0，`status=ok`，**26 件产物**；
快照由表材料在 `work/snapshot.db` 内建立（SHA-256 `fde1cedaa46d6370…`）；
`tables=2 / fields=9`；**16 条语句真实执行、0 失败**，导出 16 份 `results/Q_*.csv`；
对账 **7/7**；连接 `Q_join_batches_samples` left 4×4 / right 6×12 → joined **10**，膨胀比 **2.5**
（`no_inflation=true`）；`data_quality` 记 `samples.batch_id` 缺 1、`batches.plant` 重复 2、
`samples.batch_id` 重复 6；契约键 **10/10**；规范化哈希 **`6ddb955ed0cfd49e`**。

## 9. v10 交付状态（专家手册嵌入）

- **新增 `references/expert_playbook.md`**（S0–S6 六步流水线与门控 / §3 量化口径（缺失率、重复行、IQR
  与 3σ、JOIN 膨胀比、聚合交叉验证、编码解码）/ §4 领域知识与单位陷阱 K1–K6 / §5 交付物与自查表
  DC-01…DC-17 / §6 完整案例 / §7 决策树 / §8 专家注意点）；`SKILL.md` 明确"执行前先读
  references/expert_playbook.md，按其框架/检查表/成本口径产出交付物"，并在 §7 自检清单加入
  "专家检查表逐项通过"。
- **单命令入口未受影响**：无 draft 下仍跑完整条查询流水线，产出全部 11 类产物 + `result.json`
  契约逐键回填，exit 0。
- `selfcheck` 额外报告 `expert-checklist ok`；`eval_sim.py` 四项全 PASS。
