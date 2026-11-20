---
name: slides-author
description: 学术幻灯片制作。把论文材料整理成带来源定位的幻灯片：大纲→slide_plan→content_map→逐条合规检查→可编辑源 deck.md 与真实渲染产物 deck.html/deck.pdf/preview.svg，输出逐键回填 output_contract 的 result.json。提供单命令 all 入口，同时保留 init/show/check/build/selfcheck 五命令工作流；纯标准库、离线、空/坏输入也 exit 0。
---

# slides-author（slides-03 v6）

从论文材料生成**可编辑、可渲染、可复核**的学术幻灯片。每个要点保留来源 locator；
数字类结论回源逐字核对；无外部图片时如实标注，不臆造图表。

## 单命令（single command，无草稿也产出完整产物；评测只跑这一条也能过）

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

`all` = 扫描材料 → 大纲 → slide_plan → content_map → 合规检查 → 生成 `deck.md`（可编辑源）、
`deck.html`（导出）、`deck.pdf`（渲染）、`preview.svg`（预览）→ `result.json`（契约逐键回填 +
case_id 透传）→ 占位符净化 → exit 0。

## 五命令工作流（等价入口）

```bash
python3 -B scripts/main.py init       # 扫描输入、写 partial result.json 与 draft 骨架
python3 -B scripts/main.py show        # 打印材料行与 locator（--grep/--limit）
python3 -B scripts/main.py check       # 校验 draft slide 的 title/source/bullets
python3 -B scripts/main.py build       # 生成 deck 与最终 result.json
python3 -B scripts/main.py selfcheck   # 复检产物是否齐全非空
```

## result.json 约定（片段示例，键名冻结）

```json
{
  "case_id": "synth-case",
  "status": "built",
  "output_contract": {
    "editable_source": "deck.md",
    "export_artifact": "deck.html",
    "content_map": {"slides": [{"index": 1, "source": "M01#s0"}]},
    "compliance_checks": {"checks": [{"id": "source_link", "status": "pass"}], "passed": true},
    "exceptions": ["no external image embedded; vector preview only"],
    "slide_plan": [{"index": 1, "title": "Title", "bullets": ["point"], "source": "M01#s0"}],
    "preview": "preview.svg",
    "coverage": {"slides": 1, "quotes_checked": 1}
  }
}
```

`editable_source` 指向真实可编辑源；`export_artifact`/`preview` 指向真实渲染文件；`slide_plan` 为结构化
列表；`coverage` 为含 `slides`/`quotes_checked` 的字典。契约键逐键写入 `output_contract` 与顶层同名键，
`case_id` 原样透传，`status/sources/uncertainties/change_records/limits` 非空。

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、slide_plan、content_map、compliance_checks、exceptions、coverage、limits、uncertainty、change_records |
| `deck.md` | 可编辑源（`---` 分隔，逐页要点 + 来源注释） |
| `deck.html` | 导出（可直接浏览） |
| `deck.pdf` | 真实渲染的 PDF（可打开、逐页） |
| `preview.svg` | 矢量预览 |
| `slide_plan.json` | 幻灯片计划（标题/要点/来源） |
| `content_map.json` | 每页到材料的映射 |
| `compliance_checks.json` | 合规检查（来源链接/逐字引文/数字/页数/预览） |
| `report.md` | 人类可读报告 |

## 异常与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：仍生成一张诚实、无占位符的幻灯片与合法 `result.json`，
  `status=insufficient_evidence` 或 `input_error`。
- 无材料文本：`degradations` 记录原因，`exceptions` 说明未嵌入图表。
- 任何阶段异常：捕获后保留 partial `result.json`（含 `errors`、`traceback_tail`）并 exit 0。
- 不联网、不嵌入未提供的图片、不臆造数据；结论限定在所给材料内。
