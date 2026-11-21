# 最小调用示例（示例 · example）

> **本文件是示例，不是任何正式案例的结果，也不冒充正式案例结果。**
> 下面用一小段**虚构**材料演示接口与完整流程；正式运行时材料由平台 `/input` 提供。

## 1. 示例输入

`/input/materials/demo.md`（虚构材料，仅用于说明接口）：

```markdown
# Demo report

## Background
Particle counting is slow when done by hand and expensive at scale.

## Method
We combine a threshold step with a light shape model to speed up counting.

## Results
Throughput rises from 40 to 120 samples per hour. See Figure 1 for the curve.
```

`/input/case.json`：

```json
{"case_id": "demo-case", "language": "en", "output_contract": {"case_id": "string", "content_map": "string"}}
```

## 2. 调用

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work ; echo "exit=$?"
```

## 3. 示意输出（节选，标明为示例）

`/app/output/deck.md`：

```markdown
# Demo report

---

## Background
<!-- role: background -->
> Particle counting is slow when done by hand and expensive at scale.
- Particle counting is slow when done by hand and expensive at scale.
<!-- notes: Emphasise the cost driver, then point to the method page. -->
<!-- source: M01#s1 -->
```

`/app/output/content_map.json`（节选）：

```json
{"slides": [
  {"index": 2, "role": "background", "source_locator": "M01#s1",
   "evidence_quote": "Particle counting is slow when done by hand and expensive at scale.",
   "figure_refs": [], "origin": "M01#s1 (background)",
   "bullets": [{"text": "Particle counting is slow when done by hand and expensive at scale.",
                "quote": "Particle counting is slow when done by hand and expensive at scale.",
                "locator": "M01#s1#b1", "verified": true}]}
]}
```

`/app/output/result.json`（节选）：顶层键与嵌套 `output_contract` 同名同值，`case_id` 透传：

```json
{"case_id": "demo-case",
 "output_contract": {"case_id": "demo-case", "content_map": {"slides": "..."}, "...": "..."}}
```

## 4. 判读

- `exit=0`，`/app/output` 下出现全部交付物（见 SKILL.md「交付物」表）；
- `content_map.json` 每页都有 `source_locator` 与逐字 `evidence_quote`，`verified=true` 表示该句可在材料里逐字回查；
- `presentation.pptx` 可用 Office / PowerPoint 打开并逐页编辑，`presentation.pdf` 页数 = 幻灯片数；
- 换成真实论文运行同一路径即可；填好 `work/draft.json` 可让 agent 路径用人工挑选的页级主张覆盖自动抽取（未逐字命中的条目会被丢弃并记入 `exceptions`）。
