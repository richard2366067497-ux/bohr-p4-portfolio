# paper-structure-logic-review — 论文结构与逻辑优化（writing-06）

对一份学术稿件做**六维结构审读**：章节结构、研究问题一致性、论证链、段落关系、重复与结论边界。
每条结论都落在 `C01-P002-S03` 定位符上并附正文逐字引文，每条建议都可执行（move / merge /
split / narrow / delete / insert），附预期效果与风险。纯 Python 标准库，不联网，不改写正文事实。

## 安装

放到 `/skills/weekly-skill` 即可，无第三方依赖（Python 3.9+）：

```
/skills/weekly-skill/
  SKILL.md
  scripts/{main.py,core.py,review.py}
  references/dimensions.md
  environment/resources.yaml
  examples/{case.json,manuscript.md}
  README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 用法

单命令全流程（评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/scripts/main.py run \
  --input /input --output /app/output --work /app/work
```

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

agent-first 路径：

```bash
python3 <skill>/scripts/main.py probe     --input /input --work /app/work
# Agent 读 <work>/inventory.json，可选地写 <work>/draft.json
python3 <skill>/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 <skill>/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 <skill>/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`draft.json` 形状：`{"title": "…", "sections": [{"heading": "…", "note": "…"}], "actions": ["…"]}`；
缺省或损坏时脚本按材料自行推断，不报错。每个子命令都会重跑完整流水线，分阶段与单命令结果一致。

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `structural_review.json` | 六维 findings/actions、维度覆盖、引文核验率、统计、包级审计 |
| `edit_plan.md` | 按 P1–P3 排序的修改计划：定位符、引文、诊断、证据、预期效果、风险 |
| `outline_after.md` | 当前结构 → 目标结构；无正文时给出应补齐的稿件骨架 |
| `argument_map.json` | 研究问题句、主张-证据链、无证据链计数 |
| `consistency_report.md` | 文件清单、标题层级、重复句、跨文档术语、引用与条目计数 |
| `pending_human.json` | 需作者补充或确认的缺口 |
| `semantic_audit.json` | 语义审读协议：机械预筛候选句（locator + 逐字引文）、固定提示词、四维度与判定取值、记录模式 |
| `metrics.json` | 与包内声明阈值的基线对照，逐项可从其它产物复算 |
| `result.json` | 契约回填 + 状态 + 来源 + 不确定性 + 修改记录 + 限制 + 错误 |

离线自测（不联网、无第三方包，退出码 0）：

```bash
python3 <skill>/scripts/main.py selftest
# 覆盖：PDF/DOCX 文本层、损坏件降级、契约回填、产物齐全、引文核验、占位符扫描、语义审读协议、基线指标
```

材料支持：`.md .txt .rst .tex .json .csv`，以及 **PDF 文本层**（FlateDecode + 字面串）与
**DOCX**（`word/document.xml`）；解析不了的二进制/扫描件只清点、不编造，文件名写入 `degradations`。

## 示例（示意，非正式案例结果）

输入：`case.json`、`manuscript.md`（含 `[1]` 引用与结论段）、`references.md`、`rules.md`
（写作规范）。运行：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

示意结果：`structural_review.json` 的 `findings` 里，结论段的因果句被标为
`conclusion_boundary`（`operation=narrow`），并给出定位符与逐字引文；`edit_plan.md` 把这条列为
P1；若正文引用 `[7]` 在参考文献里没有条目，`argument_chain` 会再报一条。整包只有写作规范、没有
正文时，状态为 `partial`，六维标为 `not_assessed`，`unverified` 写明缺口，不会把包级审计写成正文审读。

## 限制

- 只做结构与措辞判断，不判断结论在科学上是否成立，也不改写正文。
- 引文必须能在正文里逐字命中，命中不了的候选结论直接丢弃（核验率记录在 `grounding`）。
- 无正文时降级为包级审计（标题、编号、重复句、术语），六个维度标为未审。
- 每条修改建议都有风险说明，机械执行仍可能改变原意。

## 维护与版本策略

- 版本 9.0.0；六维 id 与 finding/action 字段冻结，新增维度需同步 `DIMS`、检测器与
  `references/dimensions.md`。
- 改动后运行 `selftest`、`selfcheck` 与 `scripts/eval_sim.py`（rich/boundary × single/agent），见 `SELFTEST.md`。
- 预算与安全边界：完全离线、仅用 Python 标准库、只写 `--output` 与 `--work`，输入树从不改写；
  包体 12 文件、单文件 ≤30KB、主脚本（`scripts/main.py`）≤25KB，因此代码拆在 `core.py`（共享层）
  与 `review.py`（审读层）两个模块里。
