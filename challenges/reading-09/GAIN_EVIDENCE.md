# GAIN_EVIDENCE — reading-09 / paper-notes-structurer（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小语料上的对照证据，并映射到
官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（一篇 6 段小论文 + 2 个候选实现）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **套模板而非保结构** —— 输出"背景/方法/结果/结论"四段式，丢掉论文自己的章节与承接关系。
2. **无锚点** —— 关键笔记不给章节/段落/行定位符，读者无法回到原文核对。
3. **无逐字引文核验** —— 无法回答"这条引文真的在原文里吗"，改写过的话被当成原文。
4. **字段不齐、无诚实缺省** —— 研究问题/数据/方法条件/局限常被略过或凭印象补写。
5. **无契约回填** —— 不产出 `result.json`，契约键覆盖 0/9。
6. **无复现比对** —— 候选实现的数字与论文报告值不做对照，无法判断能否复现。
7. **无自检** —— 无命中率核验、无降级记录。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把论文正文去标题后整段拼成一篇通读摘要，不建骨架、不定位、不建卡片
import json, pathlib, re
p = json.loads(pathlib.Path("examples/params.json").read_text(encoding="utf-8"))
body = re.sub(r"^\s*\d+(\.\d+)*\.?\s*.*$", "", p["paper"], flags=re.M)
pathlib.Path("baseline_out").mkdir(exist_ok=True)
pathlib.Path("baseline_out/summary.md").write_text("综述：\n" + body.strip() + "\n", encoding="utf-8")
# 无 paper_card / note_units.jsonl / coverage.json / claims.json / result.json，无锚点、无逐字核验
```

模拟结果：产物 **1** 件、章节骨架 **0**、六字段卡片 **0/6**、锚点笔记 **0**、逐字命中 **0/0**、
复现比对 **0** 行、契约键 **0/9**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=answered`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **7** |
| 章节骨架（论文自身标题/编号小节） | **6**（`S0..S5`：`1. Research question` … `6. Limitations and future work`） |
| 六字段卡片 | **6/6 填满**（`card_ratio = 1.0`） |
| 锚点笔记 `note_units.jsonl` | **6** 条，逐字命中 **6/6**（`hit_rate = 1.0`） |
| 复现比对 `candidate_verdicts` | **4** 行（`candidate_a` 2/2 复现；`candidate_b` 1/2 复现，`macro_f1 delta=0.011`） |
| 契约键覆盖 | **9/9**（顶层 + `result.output_contract`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=9371df96db61df23`（剔除 `runtime`） |

关键产物：`notes.md`（章节骨架 + 带锚点卡片 + 锚点笔记 + 候选比对）/
`note_units.jsonl`（每行 `claim_id, field, anchor, quote, has_number, verbatim`）/
`paper_card.json`（六字段 value/anchor/quote/source_section + 命中统计）/ `coverage.json` /
`claims.json` / `run_log.txt`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件拼接摘要 | 7 件成套产物（骨架/卡片/笔记/覆盖/比对） | **实际效果（15 分）** |
| 结果正确性 | 数字与方法条件靠印象改写 | 引文逐字取自原文并按锚点核验（命中率 1.0） | **实际效果（15 分）** |
| 结果完整性 | 六字段缺研究问题/数据/条件/局限 | 六字段逐字段填或诚实 `not-reported` | **实际效果（5+5 分）** |
| 结果可核验性 | 无定位符、无逐字 | 每条笔记带 `S3 ¶2/L17` 锚点 + 逐字 quote + 命中率 | **实际效果（5 分）** |
| 使用增益 | 无对照、无复现判定 | `candidate_verdicts` 给出 delta 与「能否复现」判定 | **使用增益（25 分）** |
| 创新增益 | 套用四段式模板 | 骨架从论文自身标题长出，卡片按字段映射 + 锚点回链 | **创新增益（15 分）** |
| 可靠体验 | 无降级、无自检 | 坏输入诚实降级 `insufficient_evidence`，selfcheck 回链 | **可靠体验（10 分）** |
| 生态贡献 | 无文档、无模板 | README/SELFTEST/资源声明 + 3 个可复用模板 | **生态贡献（10 分）** |

**为什么这些差异对应 rubric**：实际效果＝「真的把一篇真实论文变成与章节对应、字段齐备、可继续使用的
笔记」；使用增益＝「同一论文、同一解析方式下，结构化与可核验性优于基线，且给出可复算的复现判定」；
创新增益＝「章节对齐、字段化、锚点回链的方法本身带来实质改进」；可靠体验＝「异常输入下仍产出可用的
诚实笔记」；生态贡献＝「说明、模板、示例可被他人直接复用」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 7 个文件；result.json.status=answered；
#       章节 6；card 6/6；anchors 6/6（hit_rate 1.0）；candidate_verdicts 4 行
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`9371df96db61df23`。
