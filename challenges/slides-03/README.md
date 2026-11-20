# slides-author — 学术幻灯片制作（slides-03 v6）

把论文材料整理成**可编辑、可渲染、可复核**的学术幻灯片：大纲 → slide_plan → content_map →
逐条合规检查 → 可编辑源 `deck.md` + 真实渲染 `deck.html`/`deck.pdf` + 矢量预览 `preview.svg`。
核心约束：

- 每页、每个要点都有材料 `locator`；数字类结论回源逐字核对（`coverage.quotes_checked`）。
- `editable_source` / `export_artifact` / `content_map` / `compliance_checks` 均是**真实文件/结构**，不是占位。
- 无外部图片时在 `exceptions` 中如实说明，不臆造图表；不联网、不嵌入未提供素材。
- 契约逐键回填 `output_contract` 与顶层同名键，`case_id` 原样透传；空/坏输入仍 exit 0。

## 安装

仅 Python 3.9+ 标准库，离线。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/slides-spec.md
  GITHUB_URL.txt  README.md  SELFTEST.md
```

## 用法

### 单命令（评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

### 五命令

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show        # 打印材料行与 locator（--grep/--limit）
python3 scripts/main.py check       # 校验 draft slide 的 title/source/bullets
python3 scripts/main.py build       # 生成 deck 与最终 result.json
python3 scripts/main.py selfcheck   # 复检产物
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、slide_plan、content_map、compliance_checks、exceptions、coverage、limits、uncertainty、change_records |
| deck.md | 可编辑源（`---` 分隔，逐页要点 + 来源注释） |
| deck.html | 导出（可直接浏览） |
| deck.pdf | 真实渲染的 PDF（逐页，可打开） |
| preview.svg | 矢量预览 |
| slide_plan.json | 幻灯片计划 |
| content_map.json | 每页到材料的映射 |
| compliance_checks.json | 合规检查 |
| report.md | 报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：生成一张诚实、无占位符的幻灯片与合法 `result.json`。
- 无材料文本：`degradations` 记录原因，`exceptions` 说明未嵌入图表。
- PDF/SVG 只含文本与矢量，不含外部图片；不做翻译，保留源语言。

> 本地评测复现命令与（静态推演的）预期结果见 `SELFTEST.md`。
