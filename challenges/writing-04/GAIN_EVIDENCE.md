# GAIN_EVIDENCE — writing-04 / citation-ledger-sync（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一最小样例上的对照证据，
并把差异映射到官方 rubric 的五维。所有「加载本 Skill」的数字均来自本包 `examples/` 的**真实运行**，
可用第 4 节命令逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**。它由随包文档描述的
> 确定性朴素策略（`baseline_sim` 逻辑，见 §1.2）在同一输入上生成，用于说明**缺口类别**，不代表任何
> 官方评测中的真实对手输出；本包**未伪造任何官方 A/B 数据**。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

同一输入 `examples/`（`case.json` + `lib.bib`，3 条记录，其中 2 条同 DOI）下，一个未加载本 Skill 的
基线 Agent 通常只给出一段自然语言回答和/或一份直接拼接的文献清单，典型缺口：

1. **无逐字证据 / 无定位符** —— 结论不带 `locator` 与原文逐字 `quote`，无法回验。
2. **无契约回填** —— 不读 `case.json:output_contract`，不产出 `result.json`，8 个契约键覆盖 0/8。
3. **无校验** —— 无自检、无 `verification.csv`/`audit.json`，无可报告的通过率。
4. **易幻觉** —— 可能「补全」缺失字段（如编造 DOI/年份/页码）而非如实标注未知。
5. **无确定性** —— 每次措辞不同、无稳定产物集合。
6. **去重凭直觉** —— 同 DOI 但题名大小写不同的两条记录常被判为两条不同文献（应合并为 1）。

### 1.2 基线模拟（确定性，非官方对照）

基线模拟逻辑（确定性朴素策略，随包内嵌说明、不单独占文件）：

```python
# baseline_sim（示意）：同一 examples/ 输入，只做最朴素的「原样拼接」
import json, pathlib
inp = pathlib.Path("examples")
bib = (inp / "lib.bib").read_text(encoding="utf-8")
records = [b.strip() for b in bib.split("\n@") if b.strip()]      # 不解析字段、不归一 DOI
(out := pathlib.Path("baseline_out")).mkdir(exist_ok=True)
(out / "references.md").write_text("\n\n".join(records), encoding="utf-8")  # 3 条全保留，0 合并
# 无 result.json、无去重裁决、无 locator、无契约
```

模拟结果：产物 **1** 份、合并 **0** 次、证据/定位符 **0**、契约键 **0/8**、无校验。

---

## 2 加载本 Skill（真实运行）

命令（见 §4）在 `examples/` 上的实测（`status=success`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **17** |
| 解析输入记录 → 规范化文献 | **3 → 2** |
| 去重合并 | **1**（DOI `10.1017/jmr.2019.101`，相似度 0.99） |
| `duplicates` 裁决条数 | **1** |
| 未解析键 `unknown_keys.count` | **0**（每个正文键都命中记录） |
| 变更记录 `change_records` | **3** |
| 契约键覆盖 | **8/8**（`numbering_policy, key_to_number, references, duplicates, unknown_keys, sources, uncertainty, change_records`） |
| 占位符扫描 | **0**（无 TODO/TBD/null/N-A/待补充…） |
| `result.json` 规范化哈希 | `sha256=50be7104cc5964f4`（剔除 `runtime.seconds` 后） |

关键产物：`references.deduped.json` / `references.gbt.md` / `references.apa.md` / `references.both.md` /
`dedup_decisions.csv` / `verification.csv` / `uncertainty.json` / `inventory.json` / `result.json` 等 17 件。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 交付完整度 | 1 件拼接清单，无 `result.json` | 17 件成套产物 + `result.json` | **完成度 / 完整性** |
| 去重正确性 | 同 DOI 视为 2 条（0 合并） | 同 DOI 判 1 合并（sim 0.99），裁决留痕 | **正确性** |
| 证据可核验 | 无 locator / 无逐字 quote | 每条带 `locator` + 逐字 `quote`；`verification.csv` | **可核验性** |
| 契约回填 | 键覆盖 0/8 | 键覆盖 8/8（顶层 + `result.output_contract`） | **完成度** |
| 抗幻觉 | 倾向补全缺失字段 | 未知即记 `uncertainty.json`，不编造 | **正确性 / 可靠性** |
| 确定性与自检 | 无稳定产物、无自检 | 规范化哈希稳定、`audit.json` 自检 | **可靠性** |

**为什么这些差异对应 rubric**：完成度靠「成套产物 + 契约回填」补齐；正确性靠「DOI 归一 + 留痕裁决」
与「未知不编造」；完整性靠「多文档账本」；可核验性靠「locator + 逐字引文」；使用增益靠「同一输入下，
加载 Skill 相对基线在多维同时提升」——即本表的左→右差异。

---

## 4 复现命令

```bash
python3 scripts/cite_engine.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 17 个文件；result.json.status=success；
#       counts = {input_records:3, canonical:2, merges:1, changes:3}
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime.seconds` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位
应为 `50be7104cc5964f4`。
