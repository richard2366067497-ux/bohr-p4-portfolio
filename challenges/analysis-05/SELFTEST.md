# SELFTEST — analysis-05 (sci-analysis-dag)

按顺序执行即可复核本包。全部步骤纯离线、确定；重复执行同一输入字节稳定。

## 1. 单命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
echo "exit=$?"
```

期望：`exit=0`；`/app/output/result.json` 是合法 JSON，且 `output_contract` 含全部契约键
（顶层同名回显），`case_id` 与 `/input/case.json` 一致。

## 2. 真实统计（自带数据）

```bash
mkdir -p /tmp/tin
printf 'group,yield_pct,temp_c,duration_min\nA,71.2,180,30\nA,72.5,182,31\nA,70.8,179,29\nA,73.1,183,32\nB,64.0,200,45\nB,63.2,198,44\nB,65.5,201,46\nB,62.8,199,45\nC,68.4,190,38\nC,69.9,191,39\nC,67.1,189,37\nC,68.8,192,38\n' > /tmp/tin/yields.csv
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/tin --output /tmp/tout --work /tmp/twork
```

期望（可复算）：

- `stats.json` 里 `one_way_anova`：F≈49.6602，p≈1.4e-5，η²≈0.9169；
- `pearson_r`：r≈−0.8962，p≈8e-5；
- `ols`：slope≈−1.9981，intercept≈326.42，R²≈0.8031；
- `cleaned/data_clean.csv` 12 行；`figures/figure_01.svg`、`figure_02.svg` 非空且每个 SVG 标签都带属性。

## 3. 幂等 / 字节稳定

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/tin --output /tmp/tout2 --work /tmp/twork2
diff -r /tmp/tout /tmp/tout2 && echo "byte-stable"
```

## 4. 空输入 / 坏输入仍需退出 0

```bash
mkdir -p /tmp/empty
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/empty --output /tmp/o3 --work /tmp/w3; echo "exit=$?"
printf '{ bad json' > /tmp/empty/case.json
python3 /skills/weekly-skill/scripts/main.py all --input /tmp/empty --output /tmp/o4 --work /tmp/w4; echo "exit=$?"
```

期望：两次都 `exit=0`，`result.json` 合法，`status=partial` / `input_error`，且
`uncertainties` 里有 `no_tabular_data`、`degradations` 里有 `case_json_unreadable`。

## 5. 分步复核

```bash
for c in init show check build selfcheck; do
  python3 /skills/weekly-skill/scripts/main.py $c --input /input --output /app/output --work /app/work; echo "$c=$?"
done
```

期望：6 个子命令都退出 0，且最后一个命令之后 `result.json` 仍完整。

## 6. 契约回填逐键检查

```bash
python3 - <<'PY'
import json,os
r=json.load(open('/app/output/result.json'))
oc=r['output_contract']
for k,v in oc.items():
    if isinstance(v,str) and ('/' in v or v.endswith(('.json','.csv','.md','.svg'))):
        assert os.path.isfile(os.path.join('/app/output',v)), (k,v)
    assert v not in (None,'',[],{}), (k,v)
print('contract ok:', sorted(oc))
PY
```
