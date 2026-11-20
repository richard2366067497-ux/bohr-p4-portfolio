# extraction-table-cleaner — reading-12 (v9)

把一张**脏的文献提取表**洗成**可复核的标准化表**：按字段字典把每一列解析到角色（行号、来源、定位、
指标、材料、数值、单位），逐格解析数字 / 科学计数 / 千分位 / `±` 误差 / `a to b` 区间 / 缺失标记，
只在**同一量纲内**做单位换算并记录 `before × factor + offset = after`，仅在**精确同义命中**时归一材料名，
用「判断键（来源+条件+指标+材料）」判定重复 / 重复实验 / 冲突，而不是按行号或先后顺序。每一个被改动的值、
每一个被挂起的行，都带 `row_id + rule_id + source_locator` 回链到输入；来源没有写的，留空而不臆造。
纯标准库、离线、确定性。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 draft，也会写出**全部**产物与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M02/p9 定位符读原表，按需填 /app/work/draft.json（照抄 init 生成的骨架）
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`compare` 把「基线 vs 加载 Skill」的对照写到 `/app/work/compare_report.json`。

## 3. 产物

写入 `--output`：`result.json`、`cleaned.csv`、`change_log.csv`、`pending_review.csv`、`anomaly_report.md`、
`rules.json`、`field_mapping.json`、`unit_table.json`、`evidence_map.json`、`coverage.json`、`run_log.txt`。
`result.json` 的 `output_contract` 键**同时**出现在顶层与 `output_contract` 对象内，`case_id` 原样透传。

## 4. 契约键

默认键（当 `case.json` 未给 `output_contract` 时）：
`case_id, status, deliverable, evidence_map, change_log, coverage`。
若 `/input/case.json` 自带 `output_contract`，则**以它为准**逐键回填：指向产物的键解析为真实文件路径
（如 `deliverable` → `cleaned.csv`、`coverage` → `coverage.json`），数组/对象键给出真实条目
（`evidence_map` 给每条变更与挂起行、`change_log` 给逐次换算明细）。`status ∈ {answered, partial,
insufficient_evidence, input_error}`。

## 5. 输入约定

- **字段字典**：一个 JSON 材料的 `roles`（角色 → 列名 token）、`synonyms`（角色 → {原名 → 规范名}）、
  `target_fields`、`missing_tokens`。
- **规则目录**：一个 JSON 材料的 `rules`（rule_id、priority、applies_to、owner、human_gate、condition、
  transform、failure_mode）与 `tolerance`（如 `replicate_relative_spread`）。
- **单位表**：一个 JSON 材料的 `prefixes`、`units`（dim、scale、offset、aliases）、`canonical`、
  `unknown_tokens`、`ambiguous_tokens`。
- **提取记录**：一个 JSON 材料的 `records` / `rows` / `measurements` / 裸 JSON 数组，或 JSONL；
  每个对象是一行源提取记录。也接受 `{field_dictionary, rule_catalog, unit_table, records}` 合并式文件。
- 不可用文件（二进制/空/占位）只记录 `parse_status`，永不引用。

## 6. 目录

```
SKILL.md                              # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
scripts/main.py                       # CLI：all / init / show / check / build / selfcheck / compare
scripts/engine.py                     # 清洗引擎：扫描 / 分类 / 解析 / 换算 / 分组（由 main.py 导入）
environment/resources.yaml            # 资源入口声明：入口命令、路径、输入约定、契约、运行时
examples/case.json  examples/params.json  examples/records.json   # 自带示例：脏迷你批次 + 字典
templates/result_contract.json        # 可复用契约骨架
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 7. 字段口径与判定定义（field contract）

| 字段 | 定义 | 误差/边界口径 |
|-|-|-|
| `value` / `value_low` / `value_high` | 逐格解析后的数值；区间拆成 low/high，点值留空 | 不把区间中点当作实测点 |
| `value_err` | `±` / `+/-` 后的误差，单独成列 | 误差只按 scale 缩放，**绝不**加 offset |
| `unit` | 目标单位（每个「字段+量纲」取多数标签） | 未知/歧义/缺失单位一律挂起，不猜量纲 |
| `original_value` / `original_unit` | 源单元格原文与其单位，逐字保留 | 换算前的值必须可回读 |
| `judgment_key` | `来源 \\|\\| 条件 \| 指标 \| 材料` | 分组看判断键，不看行序 |
| `status` | `ok / missing / needs_review / merged_duplicate / replicate / conflict` | 冲突双方都保留并挂起 |
| `source_locator` | 源行的页/表定位，逐字透传 | 变更与挂起行都必须带 locator |

## 8. 基准用例与评分口径（benchmark + scoring，可复用）

- `examples/`（`case.json` + `params.json` + `records.json`）：22 行脏批次（重复、重复实验、冲突、
  单位混用、区间、`±`、未知/歧义/缺失单位、派生 id），是**示例**，不是正式案例结果。
- 评分维度映射（对应官方五维）：
  - 实际效果：`cleaned.csv` + `change_log.csv` + `pending_review.csv` + `evidence_map.json` 覆盖
    角色解析/数值解析/单位换算/同义归一/重复合并/重复实验/冲突裁决；每值带 locator 与规则链。
  - 使用增益：`compare_report.json` 给「基线贴表 + 目测换单位 vs 本 Skill 逐行规则链」的可核验差；见 `GAIN_EVIDENCE.md`。
  - 创新增益：判断键分组（重复/重复实验/冲突三分）、`before × factor + offset` 变更台账、误差只缩放不加偏移（见 §9）。
  - 可靠体验：空/坏/占位输入诚实降级为 `insufficient_evidence`；无法解析的格挂起为 `partial`；`SELFTEST.md` 有稳定性证据。
  - 生态贡献：SKILL.md、模板、示例、字段口径齐全，可换成新批次复跑。

## 9. 方法与新增能力（innovation）

相对「让基础 Agent 直接把表抄成 CSV」的通用方案，本 Skill 提供可复算的新增能力：
(a) **判断键分组**：以 `来源|条件|指标|材料` 建组，组内不在容差内的分歧判为 `conflict`（双方保留并挂起），
    容差内判为 `replicate`（逐条保留、不取平均），完全相同的判为 `merged_duplicate`（保留首条、链接 `duplicate_of`）；
(b) **可复算换算台账**：每次换一行 `before / factor / offset / after / precision / formula`，可逐步复算；
(c) **误差口径**：误差只随 scale 缩放、不加 offset（`°C→K` 这类偏移绝不作用到误差上）；
(d) **多数标签归一**：同一「字段+量纲」按出现次数选目标单位，而不是按规则目录里写的规范单位硬套。
**价值边界**：质量↔物质的量之间缺少摩尔质量时，判为 `dimension_mismatch` 并挂起而非硬换；
名字只在**精确同义**命中时归一，近似拼写不合并（避免把两种物质并成一类）。

## 10. 降级与诚实性

- 没有提取记录，或既无字段字典又无单位表 → `status=insufficient_evidence`；每个产物带结构化
  no-data 记录并说明检索位置；exit 0。
- 部分值无法解析（未知/歧义单位、文本格、量纲不符）→ `status=partial`，受影响行**挂起**而非猜值。
- 冲突组保留双方并挂起；一次换算从不裁决科学分歧。
- 名字只在精确同义命中时归一；近似匹配原样保留。
- 空 / 二进制 / 仅占位文件 → 记录其 `parse_status`，永不引用。
- 无网络、无第三方依赖、不编造数字。

## 11. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟、结果确定性可复现。详见 `environment/resources.yaml`。
