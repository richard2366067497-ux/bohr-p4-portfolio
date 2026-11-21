# GAIN_EVIDENCE — writing-01 / writing-01-section-drafting（使用增益证据）

本文给出「不加载本 Skill 的基线」与「加载本 Skill」在**同一最小样例**（本包 `examples/`）上的对照，
并把差异映射到官方 rubric 的五维（实际效果 / 使用增益 / 创新增益 / 可靠体验 / 生态贡献）。
所有「加载本 Skill」的数字均来自本包 `examples/` 的真实运行，命令见 §4 可逐字复现。

> **诚实声明**：本文「基线（无 Skill）」一行为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，
> 不代表任何官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线（无 Skill）

### 1.1 典型输出与缺口

同一输入 `examples/`（`materials/draft.md`，含数字的方法/结果句）下，一个未加载本 Skill 的基线
通常把材料**原样拼接**成一段文本、或写一段自然语言回答，典型缺口：

1. **无逐字证据 / 无定位** —— 结论不带 `locator`（`文件:L行号`）与逐字 `quote`，无法回查。
2. **无契约回填** —— 不读 `case.json:output_contract`，不产出 `result.json`（契约键覆盖 0/5）。
3. **无分节** —— 不按「摘要→引言→方法→结果→讨论→结论→参考文献」结构成稿，不保留缺口章节。
4. **易幻觉** —— 可能「补全」材料外的数值、文献或图注，而非如实标注未知。
5. **无确定性** —— 每次措辞不同、无稳定产物集合、无自检。
6. **无回链账本** —— 数值原句与正文语句不建立 `preserved_facts` / `evidence_map` 映射。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意，随包内嵌说明、不单独占文件）：同一 examples/ 输入，只做「原样拼接」。
from pathlib import Path
inp = Path("examples/materials")
draft = (inp / "draft.md").read_text(encoding="utf-8")
(out := Path("baseline_out")).mkdir(exist_ok=True)
(out / "manuscript.md").write_text(draft, encoding="utf-8")   # 不切节、不分级、不回链
# 无 result.json、无 preserved_facts、无 evidence_map、无 locator、无契约、无自检
```

模拟结果：文件数 **1**、证据行 **0**、带定位的行 **0**、契约键覆盖 **0/5**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=ok`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **2**（`manuscript.md` + `result.json`） |
| 材料数 materials / 可读 readable | **1 / 1** |
| 含数值原句 preserved_facts | **4**（每条带 `source_id` + `locator`，`verified=true`） |
| 回链语句 evidence_map | **5**（每条带 `section`/`quote`/`locator`，`verified=true`） |
| 逐字命中 quotes_verified / 拒收 quotes_rejected | **5 / 0**（命中率 1.0） |
| manuscript.md 二级标题 h2_headings | **9** |
| 正文字数 chars | **933** |
| 待人工确认 pending_human | **0** |
| 契约键覆盖 | **5/5**（`case_id, deliverable, preserved_facts, evidence_map, change_log`） |
| 占位符扫描 | **0**（无 TODO / TBD / null / 待写 …） |

关键产物：`manuscript.md`（分节稿，证据句带 `文件:L行号`）、`result.json`（顶层与 `output_contract`
同名键齐全、`case_id=example-writing-01` 原样透传、`coverage` 计数字段）。

同一命令在较大输入（`synth_cases/writing-01/rich`，8 份材料）上实测：`materials=8`、
`facts=30`、`quotes_verified=29`、`quotes_rejected=0`、`status=ok`，规模随材料线性增长而口径不变。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件拼接文本，无 `result.json` | 2 件成套产物 + 契约齐全 | **实际效果 / 使用增益** |
| 证据可核验 | 无 locator / 无逐字 quote | 每行 `locator`(`文件:L行号`) + 逐字 `quote` | **实际效果 / 可靠体验** |
| 结构正确性 | 平铺，不分节 | 固定 9 个二级标题层级，缺口章节保留 | **实际效果** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + `output_contract`） | **实际效果 / 生态贡献** |
| 抗幻觉 | 倾向补全缺失字段 | 未匹配即记缺口，不编造 | **可靠体验** |
| 确定性与自检 | 无稳定产物、无自检 | 离线确定性；重复运行除时间戳外一致 | **可靠体验** |
| 可复用性 | 一次性回答 | 单命令 + init/show/check/build 分段入口 | **使用增益 / 生态贡献** |

**为什么这些差异对应 rubric**：实际效果靠「分节稿 + 逐行回链」直接可读可查；使用增益靠「一条命令
产出成套产物、Agent 可选草稿」；创新增益靠「论断↔逐字原句↔行号」的机械回链账本；可靠体验靠
「未匹配不编造 + 确定性重跑」；生态贡献靠「契约逐键回填 + 纯标准库离线」，便于平台与第三方接入。

---

## 4 复现命令

```bash
# 在包根目录执行（示例用本机 python；平台为 python3）
python -X utf8 scripts/main.py run --input examples --output /tmp/w01out --work /tmp/w01work
# 期望：exit 0；/tmp/w01out 下 2 个文件；result.json.status=ok
#       coverage = {materials:1, readable:1, facts:4, quotes_verified:5,
#                   quotes_rejected:0, h2_headings:9, chars:933}
```

四格评测仿真（rich/boundary × single/agent，均 PASS）：

```bash
for c in rich boundary; do for m in single agent; do
  python -X utf8 scripts/eval_sim.py --pkg work/p4/v10/writing-01 \
    --case work/p4/synth_cases/writing-01/$c --mode $m
done; done
```
