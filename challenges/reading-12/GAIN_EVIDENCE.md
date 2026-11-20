# GAIN_EVIDENCE — reading-12 / extraction-table-cleaner（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一张脏提取表上的对照证据，并映射到
官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**（见 `SELFTEST.md`），可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。对照的公平性在于：两组使用**同一**输入（`examples/records.json` +
> `examples/params.json`）、**同一**任务（把脏提取表洗成可核验的标准化表并给证据）与**同一**评估口径（§3）。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（22 行脏批次）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **只搬运不裁决** —— 把 22 行原样贴成 CSV，重复行仍是两行、冲突值并列却无标记。
2. **单位靠目测** —— 把 M / mM / uM 混在一列，或把 `1,500` 读成 `1.5`、把 `1.49e6` 读成 `1490000`；
   换算不留 before/factor/offset，无法复核。
3. **误差被揉进值** —— `1.50 ± 0.02` 取中位数当值，误差丢失；`°C→K` 时把 273.15 也算进误差。
4. **名字模糊合并** —— 凭相似度把 `table salt` 与 `sodium chloride` 直接并成一类却无同义来源；
   或无依据地把缺单位的 `36` 当无量纲。
5. **无 locator / 无规则链** —— 每个改动不给 `row_id`+`rule_id`+`source_locator`，不可复核。
6. **不区分可读/推断/无法确定** —— 缺失的 `n/a` 被写成 `0`，未知单位被当成同量纲硬换。
7. **无契约回填** —— 不产出 `result.json`，契约键覆盖 0/6。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：按顺序把每行拼成 CSV，不做单位换算、不改名、不分重复/冲突
import json, csv, pathlib
recs = json.loads(pathlib.Path("examples/records.json").read_text(encoding="utf-8"))["records"]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
with open("baseline_out/cleaned.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    for r in recs:
        w.writerow([r.get("row_id", ""), r.get("substance", ""), list(r.values())[-1]])
# 无 change_log.csv / pending_review.csv / evidence_map.json / result.json，
# 无单位换算台账、无同义归一、无判断键分组、无 locator
```

模拟结果：产物 **1** 件、单位换算 **0**、同义归一 **0**、重复合并 **0**、冲突标记 **0**、
挂起行 **0**、locator 证据 **0**、契约键 **0/6**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=partial`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **11** |
| 记录进 / 行出 | **22 / 22** |
| 单位换算行（可复算台账） | **4**（M→mM、uM→mM、K→C、mg→g） |
| 同义归一（精确命中才改） | **20**（table salt/sodium chloride→NaCl、potassium chloride→KCl、melting point→melting_point） |
| 变更总数 `change_log.csv` | **24**（含 4 次换算） |
| 重复合并 `merged_duplicate` | **1**（`duplicate_of=P1-01`） |
| 重复实验 `replicate`（保留不平均） | **9** |
| 冲突 `conflict`（双方保留并挂起） | **4** |
| 挂起待复核 `pending_review.csv` | **9**（未知/歧义/缺失单位 + 不可解析 + 缺失 + 冲突） |
| 未映射列 `unmapped_columns` | **0** |
| 契约键覆盖 | **6/6**（顶层 + `output_contract`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=1228dc54cbe7b180`（剔除 `runtime`） |

关键产物：`cleaned.csv`（角色解析后的标准表，含 `judgment_key`/`status`/`rule_ids`）/
`change_log.csv`（before/factor/offset/after/precision/rule_id/formula/locator）/
`pending_review.csv`（reason_code + reason + suggested_action + locator）/`evidence_map.json`
（每条变更与每个挂起行的 `row_id`+`rule_id`+`source_locator`）/`coverage.json`（分桶计数）。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件原样搬运 CSV | 11 件成套产物（标准表/变更台账/挂起/证据/覆盖） | **实际效果（15 分）** |
| 结果正确性 | 单位靠目测、千分位/科学计数易错 | 逐格解析 + 同量纲换算，`1,500`→1500 mM、`1.49e6 uM`→1490 mM | **实际效果（15 分）** |
| 结果完整性 | 漏重复/重复实验/冲突，或把 `n/a` 写成 0 | 判断键分组三分（1 合并 / 9 重复实验 / 4 冲突），缺失留空 | **实际效果（5+5 分）** |
| 结果可核验性 | 无 locator、无规则链 | 每条变更与挂起行带 `row_id`+`rule_id`+`source_locator`，换算可逐步复算 | **实际效果（5 分）** |
| 使用增益 | 无对照、无法复核 | `compare_report.json` 给「基线搬运 vs 规则链」的可核验差；同输入同口径（§1） | **使用增益（25 分）** |
| 创新增益 | 直接目测换算 | 判断键分组 + 可复算换算台账 + 误差只缩放不加偏移 + 多数标签归一（README §9，含价值边界） | **创新增益（15 分）** |
| 可靠体验 | 无降级、无自检 | 空/坏/占位 → `insufficient_evidence`；不可解析/未知单位 → `partial` 挂起，记原因/建议动作；`SELFTEST.md` 有证据 | **可靠体验（10 分）** |
| 生态贡献 | 无文档、无模板 | README/SELFTEST + 契约骨架 + 示例脏批次 + 字段口径，可换成新批次复跑 | **生态贡献（10 分）** |

**为什么这些差异对应 rubric**：实际效果＝「真的把一张脏提取表洗成与判定键对应、可继续统计的数值」；
使用增益＝「同一输入、同一口径下，可核验性与可复算性优于基线，且给出可复算差」；创新增益＝「判断键分组、
换算台账、误差口径的方法本身带来实质改进并给出边界」；可靠体验＝「异常输入下仍产出可用的诚实清洗结果」；
生态贡献＝「说明、模板、示例可被他人直接复用」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 11 个文件；result.json.status=partial；
#       记录 22 进 22 出；换算 4；重复合并 1；重复实验 9；冲突 4；挂起 9；未映射列 0
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`1228dc54cbe7b180`。
