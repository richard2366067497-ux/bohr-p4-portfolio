# 草稿结构、结果字段与定位规则（v6.0.0）

本文件是 `scripts/main.py` 的字段参考。凡是「没有内容」的地方，写一条结构化说明条目，
不要留空串或空数组——空值在评测里会被当作未回填。

## 1. `/app/work/draft.json`（可选，Agent 写）

下面用 `text` 代码块给出结构，方便照抄；它不是样例数据，也不含可发布内容。

```text
{
  "title": "可选；缺省时脚本从材料的一级标题或 case.source.title 推定",
  "sections": [
    {
      "heading": "2 方法",
      "paragraphs": [
        {
          "text": "只改表达、不改事实的一段正文",
          "quotes": [
            {"quote": "材料里逐字出现的一句原话",
             "locator": "paper.md:L9",
             "source_id": "M01"}
          ]
        }
      ]
    }
  ],
  "facts": [
    {"quote": "含数值的材料原句", "locator": "paper.md:L13"}
  ]
}
```

- `paragraphs` 可以直接是字符串；`quotes` 也可以是纯字符串（此时按"全材料"校验）。
- 校验口径：去掉全部空白后，`quote` 需是某份材料文本的子串；否则**拒收**，
  写入 `pending_human`，且不进入 `evidence_map`。
- 草稿上限 8MB；未知键忽略；坏 JSON 视为没有草稿（不影响 `build`）。

## 2. `result.json` 字段

| 字段 | 含义 |
|-|-|
| `output_contract` | 逐键回填；键名来自输入 contract，缺省时用 `case_id/deliverable/preserved_facts/evidence_map/change_log` |
| `case_id` | 输入案例标识，缺失时为空串并在 `errors` 记为缺省 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | 固定为 `manuscript.md` |
| `preserved_facts` | 含数字原句，≤30，`{fact_id,value_text,source_id,locator,verified}` |
| `evidence_map` | 正文回链，≤150，`{claim_id,section,quote,source_id,locator,verified}` |
| `change_log` / `changes` / `change_records` | 每节动作（`use_agent_section` / `assemble_from_source`）与末条 `finalize` |
| `sources` | `{id,path,kind,bytes,chars,readable,note}` |
| `uncertainty` / `uncertainties` | 组装方式、定位精度、未解析 PDF 等声明 |
| `pending_human` | `{item,reason,action}`：跳过/拒收/缺章 |
| `errors` | 输入级错误（`input_dir_missing`、`case_json_missing` 等） |
| `degradations` | `{code,path[,detail]}`，对应 SKILL.md 第 6 节 |
| `limits` | 能力边界声明 |
| `coverage` | 材料数/可读数/事实数/回链数/拒收数/H2 数/字符数 |
| `runtime` | 开始时间、耗时、Python 版本、输入与输出根 |

## 3. 定位符

`相对路径:L行号`。文本按原始行号；docx 按 `</w:p>` 切段后的行；JSON 材料按
`json.dumps(..., indent=1)` 展平后的行。跨行拆句可能带来 ±1 行偏移，属正常范围。

## 4. 状态判定

- `input_error`：输入目录不存在，或触发兜底分支；
- `insufficient_evidence`：没有可用材料，或没有任何可回链的证据句；
- `ok`：证据句 ≥5 且零拒收；
- `partial`：其余情况（含有产物但有拒收）。
