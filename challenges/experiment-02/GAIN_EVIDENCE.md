# GAIN_EVIDENCE — experiment-02 / plan-feasibility-review（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` + `resources.json`：2 设备（1 已具备 / 1 需采购）、1 耗材（单价 120×2）、
1 机时（日费 200，窗口 3 天）、预算 500、1 参数域 temperature 60–180、1 约束 temperature ≤ 160、
3 个候选方案版本）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 不给 `locator`（如 `M02/$.resources.equipment[1]`）与原文逐字 `quote`。
2. **无契约回填** —— 不产出 `result.json`，11 个契约键覆盖 0/11。
3. **无结构判定** —— 不逐版本 × 逐七类给状态，只给一句"方案基本可行"。
4. **易幻觉 / 误判"未声明=满足"** —— 把材料没写的样本量、伦理审批默认当作"已满足"。
5. **无行级时长/成本** —— 给一个总时长/总成本，不按步骤行、不按成本行拆开，无法复算。
6. **无算术自检 / 无确定性** —— 无步骤行之和=时长、成本行之和=单次成本、预算上限、版本数等自检。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：只给一句定性结论，不逐版本、不逐类别、不做行级成本
import json, pathlib
p = json.loads(pathlib.Path("examples/resources.json").read_text(encoding="utf-8"))
vers = [v["version"] for v in p["versions"]]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "review.md").write_text(
    "候选方案 " + ", ".join(vers) + " 看起来可行，建议按方案执行。\n", encoding="utf-8")
# 无 checks.json、无 estimate.json、无 risks.json、无 confirmations.json、
# 无 evidence.json、无 version_diff.md、无 result.json
```

模拟结果：产物 **1** 件、逐版本判定 **0**、逐类别状态 **0**、行级成本行 **0**、逐字证据 **0**、
契约键 **0/11**、无算术自检、无"未声明"保留。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=partial`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **8**（feasibility_review.md / checks.json / estimate.json / risks.json / confirmations.json / evidence.json / version_diff.md / result.json） |
| 逐字证据 `evidence_stats` | verified **11** / total **11** / rate **1.0** |
| 资源四态映射 | 设备 **2**（centrifuge=已具备 / sequencer=需采购）、耗材 **1**（kit 单价 120、用量 2、货期 5d）、机时 **1**（sequencer slot 日费 200、窗口 3d） |
| 参数域 | **1**（temperature 60–180，unit C） |
| 显式约束 | **1**（temperature ≤ 160，带 locator+quote） |
| 候选版本 | **3**（v1/v2/v3），逐版本 × 七类逐项判定 |
| 阻断判定 | v2 的 `参数范围` 判为 **blocked**（temperature=190 越域） |
| 排序与胜出 | ranked **v1, v3, v2**；winner **v1** |
| 契约键覆盖 | **11/11**（case, case_id, plan, equipment, material, booking, budget, domains, approval, source, task） |
| 未声明保留 | 样本量、伦理审批如实标为 **未声明**（列入 `confirmations`），未默认满足 |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=f64e0570868a45b2`（剔除 `runtime`） |

关键产物：`checks.json`（逐版本 × 逐类别状态台账）/`estimate.json`（时长与成本公式与逐版本估算）/
`risks.json`/`confirmations.json`/`evidence.json`/`version_diff.md`/`result.json`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件定性结论，无 `result.json` | 8 件成套产物（台账/估算/风险/确认/证据/对比） | **完成度 / 完整性** |
| 判定正确性 | 一句"基本可行" | 逐版本 × 七类状态；越域版本如实判 blocked | **正确性** |
| 证据可核验 | 无 locator / 无 quote | 11 条证据、11 条逐字命中（rate 1.0） | **可核验性** |
| 契约回填 | 键覆盖 0/11 | 键覆盖 11/11（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 可能把"未声明"当"满足" | 样本量/审批如实标"未声明"并入确认清单 | **完整性 / 可靠性** |
| 确定性与自检 | 每次结论漂移 | 规范化哈希稳定、行级成本自洽 | **可靠性** |

**为什么这些差异对应 rubric**：完成度＝「成套产物 + 契约回填」；正确性＝「逐版本 × 七类状态 +
越界如实标注 blocked」；完整性＝「资源四态 + 参数域 + 约束 + 确认清单 + 证据」；可核验性＝
「locator + 逐字引文 + 命中率」；使用增益＝「同输入下相对基线在多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 8 个文件；result.json.status=partial；
#       versions=3（v2 参数范围 blocked）；ranked=v1,v3,v2；winner=v1；
#       evidence_stats = {verified:11, total:11, rate:1.0}
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime` 段后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位
应为 `f64e0570868a45b2`。
