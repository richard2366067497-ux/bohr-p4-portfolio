# 最小可跑示例

一组最小输入、调用方式与示意输出，用于在无真实语料时核对技能行为。

## 1. 准备输入

```text
/input/case.json
{"case_id": "demo-qa-01", "paper_id": "D1", "material_version": "v1"}

/input/comparison-workorder.json
{"research_question": "染料初始浓度与 pH 如何影响光催化去除率？"}

/input/corpus/D1.txt
Methylene blue removal by TiO2 photocatalysis

After 120 min at pH 3, the removal efficiency reached 95%. Increasing the
solution pH to 9 lowered the removal efficiency to 61%.
```

## 2. 调用

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 3. 示意输出（`/app/output/result.json` 节选）

```json
{
  "case_id": "demo-qa-01",
  "status": "answered",
  "answers": [
    {
      "question_id": "RQ1",
      "question": "染料初始浓度与 pH 如何影响光催化去除率？",
      "status": "answered",
      "answer": "依据可定位段落，共 2 条证据支持如下回答：[corpus/D1.txt#p2] ... [corpus/D1.txt#p2] ...",
      "conditions": ["仅依据 corpus/D1.txt 的记载，不外推"],
      "evidence": [
        {"paragraph_id": "corpus/D1.txt#p2", "score": 0.62, "quote": "After 120 min at pH 3, the removal efficiency reached 95%."}
      ]
    }
  ],
  "coverage": {"documents": [{"document": "corpus/D1.txt", "paragraphs": 2}], "read": ["corpus/D1.txt#p1", "corpus/D1.txt#p2"]}
}
```

## 4. 边界示例

材料只有空文件或坏 JSON 时，`status` 变为 `insufficient_evidence`/`input_error`，回答中列出
「缺少可定位证据」，退出码仍为 0。
