# GAIN_EVIDENCE — writing-06 / paper-structure-logic-review（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` + `manuscript.md`：含一段被逐字重复的 Results 段，结论句
`The cooling rate causes the observed improvement in weld quality in every case.` 为相关性研究却写因果/绝对化）
下，未加载本 Skill 的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 不给 `C01-P002-S03` 形式定位符与正文逐字引文。
2. **无契约回填** —— 不产出 `result.json`，3 个契约键覆盖 0/3。
3. **无校验** —— 无一致性报告、无自检通过率。
4. **易幻觉** —— 可能编造「Methods 缺失」等稿件中并不存在的缺陷。
5. **无确定性** —— 每次评语措辞不同，无稳定产物。
6. **无可执行建议** —— 只给「建议加强逻辑」等泛泛评语，无 move/merge/narrow 等可执行动作。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：只对稿件给一句通用评语，不做六维检测
import pathlib
ms = pathlib.Path("examples/manuscript.md").read_text(encoding="utf-8")
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "review.md").write_text(
    f"稿件共 {len(ms.splitlines())} 行，整体结构基本清晰，建议加强段落衔接与结论边界。\n",
    encoding="utf-8")
# 无 structural_review.json、无定位符、无 edit_plan、无 result.json
```

模拟结果：产物 **1** 件、具名维度发现 **0** 条、可执行动作 **0** 条、契约键 **0/3**、无校验。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=ok`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **7** |
| 六维具名发现 `findings` | **2**（`duplication`=medium，`conclusion_boundary`=high） |
| 可执行动作 `actions` | **2** |
| 逐字重复句 `duplicate_sentences` | **1** |
| 结构统计 | 章节 **6** / 段落 **11** |
| 契约键覆盖 | **3/3**（`unverified, verified, degradations`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=a52a2c074b730131`（剔除 `runtime.seconds`） |

关键产物：`structural_review.json` / `edit_plan.md` / `outline_after.md` / `argument_map.json` /
`consistency_report.md` / `pending_human.json` / `result.json`。每条发现带 `C01-P002-S03` 定位符与逐字引文；
`duplication` 命中逐字重复句，`conclusion_boundary` 命中「corr=True 且 ctrl=False」下的因果/绝对化措辞。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件泛评，无 `result.json` | 7 件成套产物 + `result.json` | **完成度 / 完整性** |
| 审读正确性 | 泛泛评语，可能编造缺陷 | 2 条具名发现，均可回验原文 | **正确性** |
| 证据可核验 | 无定位符、无引文 | 每发现带定位符 + 逐字 quote | **可核验性** |
| 契约回填 | 键覆盖 0/3 | 键覆盖 3/3（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 易臆造不存在的问题 | 阈值触发才报，弱证据入 `pending_human` | **正确性 / 可靠性** |
| 确定性与自检 | 措辞漂移、无自检 | 规范化哈希稳定、一致性报告 | **可靠性** |

**为什么这些差异对应 rubric**：完成度＝「成套产物 + 契约回填」；正确性＝「具名维度 + 阈值触发 + 可回验」；
完整性＝「审读 + 计划 + 一致性报告」；可核验性＝「定位符 + 逐字引文」；使用增益＝「同输入下相对基线多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/main.py run --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 7 个文件；result.json.status=ok；
#       metrics = {chapters:6, paragraphs:11, findings:2, actions:2, duplicate_sentences:1}
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime.seconds` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位
应为 `a52a2c074b730131`。
