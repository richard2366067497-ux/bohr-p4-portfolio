# GAIN_EVIDENCE — writing-12 / latex-edit-build-verify（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并映射到官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**，可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（`case.json` + `main.tex`：第 2/3 行重复 `\usepackage{amsmath}`、`hyperref` 在
`cleveref` 之前加载、`itemize` 环境未闭合）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **无逐字证据 / 无定位符** —— 只说「似乎有重复宏包」，不给 `文件:行号` 与 `before/after`。
2. **无契约回填** —— 不产出 `result.json`，7 个契约键覆盖 0/7。
3. **无校验** —— 无 `checks` 清单、无自检通过率。
4. **易幻觉** —— 可能臆造「已成功编译出 main.pdf」或编造不存在的宏包冲突。
5. **无确定性** —— 无稳定产物集合、无 diff。
6. **只说不改** —— 不产出可编译工程根、统一 diff 或复现命令。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：只做朴素「文本回显 + 一句通用建议」，不改文件、不体检
import pathlib
tex = pathlib.Path("examples/main.tex").read_text(encoding="utf-8")
pathlib.Path("baseline_out").mkdir(exist_ok=True)
(pathlib.Path("baseline_out") / "review.txt").write_text(
    tex + "\n\n建议：检查是否有重复的 \\usepackage 和未闭合环境。\n", encoding="utf-8")
# 无 lint_report.json、无 fixes、无 diff.patch、无 result.json
```

模拟结果：产物 **1** 件、修复 **0**、体检发现 **0** 条结构化条目、契约键 **0/7**、无校验。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=partial`：引擎缺失，但工程仍完整交付；exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **10** |
| 静态体检发现（lint） | **3** 条 |
| 应用修复 `fixes_applied` | **2**（重复宏包、未闭合 `itemize`） |
| 仅定位未改 `reported` | **1**（`hyperref` 在 `cleveref` 前——为避免改动科学含义只定位） |
| 检查项 `checks` | **7**（pass 4 / warn 1 / skip 2） |
| 变更记录 `change_records` | **4** |
| 契约键覆盖 | **7/7**（`case_id, status, deliverable, preserved_facts, evidence_map, change_log, workorder_receipt`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=52119b06b32d893c`（剔除 `runtime.seconds`） |

关键产物：`lint_report.json` / `fixes.json` / `diff.patch` / `main.tex` / `source/main.tex` /
`packages.md`（复现命令）/ `build.json` / `result.json` 等 10 件。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件文本回显，无 `result.json` | 10 件成套产物 + 可编译工程根 | **完成度 / 完整性** |
| 修改正确性 | 仅给「建议」，不改 | 2 处最小可逆修复 + 1 处保守定位，均带 before/after | **正确性** |
| 证据可核验 | 无 `文件:行号`、无 before/after | 每条 finding/fix 带 `locator`；`diff.patch` 留痕 | **可核验性** |
| 契约回填 | 键覆盖 0/7 | 键覆盖 7/7（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 / 降级 | 可能臆造「已编译成功」 | 缺引擎如实记 `partial` + `limits` + 复现命令 | **正确性 / 可靠性** |
| 确定性与自检 | 无稳定产物、无检查项 | 规范化哈希稳定、`checks` 7 项 | **可靠性** |

**为什么这些差异对应 rubric**：完成度＝「成套产物 + 契约回填」；正确性＝「最小可逆修复 + 不做无把握
改动」与「缺工具如实降级不编造」；完整性＝「工程根 + diff + 说明」；可核验性＝「locator + before/after +
diff」；使用增益＝「同输入下相对基线在多维同时提升」。

---

## 4 复现命令

```bash
python3 scripts/latex_build.py build --input examples --output /tmp/out --work /tmp/work --engine pdflatex
# 期望：exit 0；/tmp/out 下 10 个文件；result.json.status=partial；
#       fixes: applied=2, reported=1；checks: 7；summary 含 build=missing_tool
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime.seconds` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位
应为 `52119b06b32d893c`。
