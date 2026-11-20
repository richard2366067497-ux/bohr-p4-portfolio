# workflow.md — 主路径、工作稿 schema、locator 语法与失败处理

本文件是 `SKILL.md` 第 2–5 节的展开版，供使用者与 Agent 照做，不替代 SKILL.md。

## 1. 五命令的执行语义

| 命令 | 读什么 | 写什么 | 什么时候该跑 |
|---|---|---|---|
| `init` | `case.json`、`task.md`、`/input/**` 材料 | 先写合法 `result.json`（partial），再写 `work/source_index.json`、`work/draft_template.json`、`work/paths.json` | 每个案例第一件事 |
| `show` | `source_index.json` | 仅标准输出（块、locator、上下文、`--find` 命中） | 写工作稿之前，逐个 target 读原文 |
| `check` | `source_index.json` + `work/draft.json` | `work/check_report.json` | 写完工作稿、`build` 之前 |
| `build` | 索引 + 工作稿 | `result.json`、主产物、全部辅助产物、`versions/` | 校验通过后（无工作稿也会兜底产出） |
| `selfcheck` | 已写出的产物 | `out/self_check.json`，必要时把 `status` 降级并追加 `errors` | 回复用户之前 |

参数：`--input/--out/--work/--draft/--target/--find/--context/--limit/--page/--contract/--workorder/--list`。
环境变量 `INPUT_DIR/OUT_DIR/WORK_DIR` 等价；都不给时按 `/input`、`/app/output`、`/app/work`，
`/app` 不存在则回退 `./output`、`./work`（本地可跑）。

## 2. 材料如何被索引

1. 遍历 `/input/**`，跳过 `case*.json`、`task.md`、隐藏文件；材料数 >120 只取前 120 并记降级。
2. 类型由**扩展名 + 魔数**判定（`%PDF`、`PK` + `word/`/`xl/`），不信标签。
   md/txt/tex 直接读；docx 取段落文本（标题样式丢失，记为限制）；pdf 仅在系统有
   `pdftotext` 时抽取，否则 `degraded`；json 渲染成带 `<!-- id -->` 的块；csv 按行；
   xlsx/xls/doc/图片 → `skipped`，不猜测内容。
3. 每份材料保成 `lines`（原始行），块记录 `start/end` 行号与原文 `raw`。主产物按**行**
   重组，因此除插入的注记块外，作者原文逐行不变。
4. 段落 id 支持三种形态：独立标记行 `<!-- C01-P002 -->` / `[C01-P002]` / `{#C01-P002}`、
   段首内联 id（`J09-B007 The measured…`、`J09-B007 | text`）、JSON 字段 `paragraph_id`。
   写在标题前的 id 视为该节第一段的 id（`…-H`/`-SEC`/`-HEAD` 结尾者给标题本身）。

## 3. locator 语法

```
<相对路径> §<节号> <节标题> ¶<段号>           # 正文块
<相对路径> §<节号> <节标题> (heading)          # 标题块
<相对路径> §<节号> <节标题> ¶<段号> · <id>     # 该块带段落 id
```

- `§` 从 1 开始，每遇到标题 +1；`¶` 在该节内从 1 重新计数，标题记 `0`/`(heading)`。
- 解析顺序：完全匹配 → `·` 后的 id → `§/¶` + 路径后缀 → `(heading)` 唯一候选。
- 引文比较前归一：NFKC、弯引号→直引号、长短破折/减号→`-`、软连字符去除、NBSP→空格、
  连续空白压成一个。归一后仍要求逐字命中；命中失败**退回**，从不“调整”成成功。
- `find_quote` 的 `where` 字段区分 `block`（目标块内）、`other_block`（别的块里）、
  `cross_block`（跨块拼接才命中）、`not_found`。只有 `block` 才算合格锚点/定位一致。

## 4. 工作稿 schema（`/app/work/draft.json`）

```jsonc
{
  "case_id": "C01",
  "reading_notes": "读了哪些节、统领性问题（1-3 句，必填，帮助评审看到你真的读过）",
  "annotations": [
    {
      "target_id": "C01-P002",              // 必填，必须在该案例工单 target_ids 内
      "locator": "chapters/ch01.md §2 Materials and methods ¶3 · C01-P002",
      "anchor_quote": "该段中的一句逐字原文",   // 必填，必须命中该块
      "annotation": "2-4 句：确立了什么 / 依赖什么条件或局限 / 读者能得出什么",
      "evidence": [{"locator": "…", "quote": "材料中的逐字原文"}],
      "rationale": "为什么这条注记必要",
      "uncertainty": "本条无法从材料确认的点"
    }
  ],
  "findings": [
    {
      "category": "term|symbol|definition|numbering|citation|claim|unit",
      "severity": "high|medium|low",
      "locator_a": "…", "quote_a": "逐字原文",
      "locator_b": "…", "quote_b": "逐字原文（单点问题可省）",
      "statement": "冲突/不一致是什么（两边都写，不做裁决）",
      "decision_owner": "author|editor|human",
      "note": "建议作者如何确认"
    }
  ],
  "plan": {"chapters": [{"locator": "…", "role": "方法", "argument_task": "…", "evidence_needed": "…"}]},
  "pending_human": [{"item": "…", "reason": "…", "action": "…"}]
}
```

`plan.json` 亦可；`draft.json` 优先。别名容忍：`text`→`annotation`、`anchor`/`original_quote`
→`anchor_quote`、`target`→`target_id`。`init` 生成的 `draft_template.json` 每个 target 已带
真实 locator 与真实锚点句，只需补正文与发现。

## 5. 验收规则（`check` 与 `build` 用同一个校验器）

| 编号 | 规则 | 级别 |
|---|---|---|
| A1 | `target_id` 在工单 target_ids 内 | high（不在→reject） |
| A2 | target 能在索引里定位 | high |
| A3 | `anchor_quote` 在**被定位块内**逐字命中 | high |
| A4 | 给了 `locator` 时必须解析到同一块 | high |
| A5 | 注记 ≥60 字（<25 字为 high） | warn/high |
| A6 | 注记不得引入材料中不存在的数字（章节/图/表编号等引用型数字豁免） | high |
| A7 | 注记与材料语汇有足够重叠（≥5 个英文术语时计算，<0.40 报警） | warn |
| A8 | 同一 target 不重复 | warn |
| A9 | 每条 evidence 的 quote 命中材料，且落在其 locator 内 | high |
| F1 | `category` 属七类之一 | high |
| F2 | `quote_a`/`quote_b` 逐字命中，且落在对应 locator 内 | high |
| F3 | `statement` ≥15 字 | warn |
| F4 | `severity` ∈ high/medium/low | warn |

`build` 只接受 `accept` 与 `warn`；`reject` 进 `operation_receipts.rejects` 并给原因，
原稿状态不变；该 target 若还没有别的注记，则用**确定性兜底注记**补齐（标记
`generated_by: deterministic_fallback`、`needs_review: true`），`status` 降为 `partial`。

## 6. build 的产物与不变量

主产物：`revised_manuscript.md`（`<!-- source: rel -->` 分段，注记以 `> **〔EA-xx …〕**`
块插入）、`revised_chapters/<材料名>.md`。
辅助：`revision_records.json`、`operation_receipts.json`、`evidence_map.json`、
`change_log.json`、`preserved_facts.json`、`pending_human.json`、`consistency_report.md`、
`consistency_tables.json`、`coverage_matrix.json`、`versions/{v1_original.md,v2_revised.md,
diff_v1_v2.patch,rollback_check.json}`、`preview.html`、`export_preview.pdf`、
`run_manifest.json`、`result.json`。

不变量（`build` 复算，`selfcheck` 再复算一次）：

1. 去掉注记块后的正文与 v1 **归一哈希相同**（`rollback_equals_v1`）；
2. 用同一 placements 重新 assembly 与 v2 哈希相同（`reapply_equals_v2`）；
3. `preserved_facts` 每块 `preserved=true`（逐块归一子串比对，不是声明）；
4. `evidence_map` 每条 `verbatim=true`（重新绑定引文后计算）；
5. 四类受控无效操作全部被同一校验器拒绝，且产物哈希在探针前后不变。

## 7. 失败处理

| 情形 | status | 行为 |
|---|---|---|
| 无 `/input` 或无 case JSON | `input_error` / `insufficient_evidence` | 合法 result.json，`errors` 说明，退出 0 |
| case JSON 损坏 | `partial` | 尽力用正则救回 `case_id`，材料照常索引，错误入账 |
| 某材料读不出 | `partial` | 该材料 `unreadable/degraded/skipped`，其余继续 |
| PDF 无文本层 | `partial` | 记降级，不臆造文字 |
| 目标 id 找不到 | `partial` | `pending_human` + 动作，不编注记 |
| 无工作稿 | `partial` | 全量兜底注记 + `degradations` 逐条列出 |
| 引文不命中/定位不一致 | `partial` | 该条 reject + 原因，原文不变 |
| 脚本异常 | 保持原状态 | 日志 + `errors` 追加，退出 0，重跑 `build` 即可 |

## 8. 分工与维护

- `scripts/ledger.py`：解析、索引、locator、引文绑定、重组、保真清单、材料发现。
- `scripts/audit.py`：六类台账、影响回链、工作稿校验、契约回填。
- `scripts/emit.py`：由索引 + 工作稿生成交付物与回执（含兜底与失效探针）。
- `scripts/render.py`：一致性报告、HTML/PDF 预览、diff。
- `scripts/main.py`：五个子命令与 result.json 信封。
- 修改顺序：先改 `references/checks.md` 的口径 → 再改对应模块 → 跑 `init/check/build/selfcheck`
  → 确认 `revised_manuscript.md` 哈希稳定。
