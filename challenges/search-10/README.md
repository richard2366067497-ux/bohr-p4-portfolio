# README — search-10 · 术语表驱动的跨语种 known-item 检索

## 这是什么

给定「问题 + 内置跨语种术语表 + 视图/版本文件」，把一次跨语种 known-item 检索做成**可独立复核**的
固化产物：概念锚点、逐语种查询式、跨语种术语对齐、视图台账与 work 级去重、命中卡/misses。

执行前先读 `references/expert_playbook.md`，产出后按其 §7 检查表逐项自检。

核心约束：

- 每个概念、每条术语对齐、每条命中都带 `locator`（`materials/x.md#L20`）与**逐字引文**；
- 术语表未收录的概念写 `not-in-glossary` → `pending_human`，**绝不臆造译法**；
- 同一 work 的原文 / 全译 / 摘要版 / 副本**去重后**才计数；`abstract_only` 不作正文命中证据；
- 离线运行，`translation_service = offline-builtin-glossary (no API call)`。

## 快速开始

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
```

`/app/output` 会得到 `result.json` + 9 个交付物。没有 `draft.json` 也能跑完（走术语表驱动的
规则抽取），`exit 0`。

## 三种用法

1. **单命令**（推荐，评测入口）：`all`。
2. **人机协作**：`init` → 看 `show --lang pt` 输出并写 `work/draft.json` → `check`（D0–D8 / K1–K4）→ `build`。
3. **例行复检**：`selfcheck` 重新核对产物齐全、契约回填、无 near-empty 文件。

## 判定口径

- 语种：材料声明的元数据 > 文件名语言标记 > 停用词比值检测；冲突时以声明为准并记入 `basis`。
- 版本：`original` / `publisher_translation` / `abstract_only` / `duplicate` / `preprint` / `erratum` / `undetermined`。
- 去重：内容指纹相同即 `duplicate`，只入台账不计数；命中数只看 `distinct_works`。
- 状态：全部题都有命中卡 → `answered`；有缺口 → `partial`；无术语表/无视图/无题面 → `insufficient_evidence`。

## 目录

```
scripts/main.py      命令入口（all/init/show/check/build/selfcheck）
scripts/core.py      扫描 → 术语表 → 概念锚点 → 查询式 → 术语对齐 → 视图去重 → 卡片 → 增益
scripts/render.py    人读/机读产物渲染 + 校验报告 + 降级说明
references/expert_playbook.md  专家方法论：十步框架/量化口径/陷阱/检查表（执行前必读）
SKILL.md             契约、单命令、分步命令、异常处置、自查、top_fix 映射
SELFTEST.md          本地评测记录（4 组 eval_sim 全 PASS）
GAIN_EVIDENCE.md     与朴素基线的对照（诚实声明：基线为确定性模拟）
environment/resources.yaml  运行时契约
examples/            自包含 smoke fixture（case.json / draft.json）
templates/query_templates.md  查询模板 + 术语扩展规则 + 题集 + 3 个跨语种案例
```

## 依赖与边界

纯标准库、离线、无第三方包。空 `/input`、坏 JSON、材料为空时仍写合法 `result.json`
（`status=input_error` / `insufficient_evidence`）并 `exit 0`。
