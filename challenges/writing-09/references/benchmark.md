# 与基线对照：怎么读 metrics.json（references/benchmark.md）

`metrics.json` 是本包唯一的"打分文件"，但它不是平台分数，而是**本包自设的守卫线**。这里说明每一行
怎么来的、怎么复算、以及它**不能**证明什么。

## 1 复算方式

每次 `run` 都会写 `metrics.json`。它的 `baseline_checks` 每行三件东西：

- `metric`：指标名；
- `measured`：本次运行实测值（从成稿、results_map.json、evidence_map.json 算出）；
- `baseline`：本包声明的阈值；`ok` 为该项是否达标；`pass` 是所有行取与。

复算示例（不重跑模型）：

```bash
python3 -c "import json;d=json.load(open('output/metrics.json'));print(d['pass'],[c['metric'] for c in d['baseline_checks']])"
python3 -c "import json;r=json.load(open('output/result.json'));print(len(r['preserved_facts']),r['metrics']['readouts'])"
```

## 2 阈值与来源

- **readout_unit_ratio ≥0.90**：读数必须带单位才可复现；低于 0.90 说明抽取有系统性遗漏。
- **evidence_links_with_locator == 文献链接数**：讨论里每条文献论断都要能定位到片段，否则退回人工确认。
- **causal_phrases_in_deliverable ==0**：关联写成因果是本任务最典型的失分点，用 `C.overclaim` 词表清零。
- **preserved_facts ≥ 读数数**：必保留项覆盖率；缺项说明有读数在成稿中丢失。
- **contract_keys_filled ≥1**：契约回填完整性。

## 3 基线对照怎么写（给评审的复算配方）

```text
基线（无 Skill）：同一 /input，人工读材料 → 手写结果段/讨论段。
本包            ：1 条命令，产物 8 件，metrics.json.pass 可复算。
可比项          ：单位保留率、证据定位率、因果措辞数、契约键数、占位符数（本包均为机器判定）。
不可比项        ：文笔、论证深度、文献选择质量（本包不声称，转人工）。
```

## 4 边界（诚实声明）

- 阈值是守卫线，不是平台评分；`pass=true` 只说明"没改坏、没漏项"，不说明"写得最好"。
- 合成案例 ≠ 官方固定案例；用 `work/p4/synth_cases/writing-09/{rich,boundary}` 复跑时，
  boundary 无读数，分母为 0 的项按"不适用即通过"处理。
- 位图与扫描件的读数**机器无法判定**，一律转人工确认，不计入 `metrics.json`。
