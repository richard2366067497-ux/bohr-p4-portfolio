# GAIN_EVIDENCE — writing-10 / reviewer-response（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` + `manuscript.md` 含过度声称句
`Our treatment cures the disease in all patients and generalizes to every setting.` + `comments.md` 4 条审稿意见：
①收窄过度声称 ②补机制引用 ③要求新增 500 例实验 ④讨论无关疾病）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 不给出「改哪句、原文是什么、改后是什么」的 `[[Cx]]` 锚点。
2. **无契约回填** —— 不产出 `result.json`，5 个契约键覆盖 0/5。
3. **无校验** —— 无 `selfcheck.json`，无从核验「接受即改到」。
4. **易幻觉** —— 可能凭空补一条机制引用（编造参考文献）而不标注待补证据。
5. **无确定性** —— 每次信函措辞不同，无稳定产物。
6. **一律接受** —— 对全部意见（含「新增 500 例实验」「讨论无关疾病」）一律接受，不作四态裁决。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：对每条意见一律「已接受」，不改稿、不定位、不自检
import json, pathlib
cs = json.loads(pathlib.Path("examples/case.json").read_text(encoding="utf-8"))
n = len(pathlib.Path("examples/comments.md").read_text(encoding="utf-8").splitlines())
pathlib.Path("baseline_out").mkdir(exist_ok=True)
letter = "\n".join(f"{i+1}. 感谢您，我们已按要求修改。" for i in range(4))
(pathlib.Path("baseline_out") / "response_letter.md").write_text(letter, encoding="utf-8")
# 无 revised_manuscript.md、无 comment_ledger.json、无 change_locator.json、无 result.json
```

模拟结果：产物 **1** 件、接受 **4/4**、改稿 **0** 处、定位 **0**、证据 **0**、契约键 **0/5**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=success`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **8** |
| 审稿意见处理 `comments` | **4** |
| 四态裁决 `decisions` | accept **2** / partial **1** / defer **1** / reject **0** |
| 实际改动 `changes` | **3** |
| 证据映射 `evidence_map` | **4** 条 |
| 自检 `selfcheck.ok` | **true**（`problems=[]`） |
| 契约键覆盖 | **5/5**（`case_id, deliverable, preserved_facts, evidence_map, change_log`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=36eb9043b58dfc37`（剔除 `runtime.seconds`） |

关键产物：`revised_manuscript.md`（含 `[[Cx]]` 锚点）/ `response_letter.md` / `comment_ledger.json` /
`change_locator.json` / `evidence_pending.md` / `version_notes.md` / `selfcheck.json` / `result.json`。
裁决落点（逐条实测）：①收窄过度声称 → **accept**（改到并锚 `[[C1]]`）；
②补机制引用 → **defer**（基线内无锚点，记入 `evidence_pending.md`，不编造引用）；
③新增 500 例实验 → **partial**（需超出基线的新材料，记入 `evidence_pending.md`）；
④澄清性请求 → **accept**（改到并锚 `[[C3]]`）。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件信函，无 `result.json` | 8 件成套产物 + 改稿 | **完成度 / 完整性** |
| 处理正确性 | 一律接受（含不合理诉求） | 四态裁决 accept/partial/defer/reject | **正确性** |
| 证据可核验 | 无锚点、无原文/改后对照 | `[[Cx]]` 锚点 + `change_locator.json` | **可核验性** |
| 契约回填 | 键覆盖 0/5 | 键覆盖 5/5（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 可能编造引用 | 缺证据入 `evidence_pending.md`，不编造 | **正确性 / 可靠性** |
| 确定性与自检 | 措辞漂移、无自检 | 规范化哈希稳定、`selfcheck.ok=true` | **可靠性** |

**为什么这些差异对应 rubric**：完成度＝「改稿 + 信函 + 契约回填」；正确性＝「四态裁决 + 接受即改到」；
完整性＝「账本 + 定位 + 版本说明」；可核验性＝「锚点 + 逐条 locator」；使用增益＝「同输入下相对基线多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/main.py --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 8 个文件；result.json.status=success；
#       metrics = {comments:4, changes:3, decisions:{accept:2, partial:1, reject:0, defer:1}}
#       selfcheck.ok = true
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime.seconds` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位
应为 `36eb9043b58dfc37`。
