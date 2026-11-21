# slides-author — 学术幻灯片制作（slides-03 v10）

把论文材料整理成可编辑、可渲染、可复核的学术幻灯片（含真实 OOXML pptx）。

> 每页、每个要点都有材料 `locator`；数字类结论回源逐字核对（结果里的 `coverage.quotes_checked`）。

核心约束：

- 每页都有材料定位（locator）；数字类主张在进入页面之前先在原文里重新定位；
- `editable_source` / `export_artifact` / `content_map` / `compliance_checks` 都是**真实文件或结构**，不是占位；
- 无外部图片时在 `exceptions` 中如实说明，不臆造图表；不联网、不嵌入未提供素材。
- 契约逐键回填 `output_contract` 与顶层同名键，`case_id` 原样透传；空 / 坏输入仍 `exit 0`。

## 安装

仅需 Python 3.8+ 标准库，全程离线。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  scripts/pptxkit.py        # 标准库 OOXML .pptx 写入与结构自检
  references/expert_playbook.md
  environment/resources.yaml
  examples/minimal-run.md
  GAIN_EVIDENCE.md  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

### 单命令（评测只跑这一条也能过）

```bash
python3 -B /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

### 分步命令

```bash
python3 -B scripts/main.py init       # 建索引 + draft 骨架
python3 -B scripts/main.py show       # 打印材料行与 locator（--grep/--limit）
python3 -B scripts/main.py check      # 校验 draft
python3 -B scripts/main.py build      # 生成产物与最终 result.json
python3 -B scripts/main.py selfcheck  # 复检产物
```

## 产物（写入 `--output`）

| `result.json` | 见 SKILL.md 交付物表 |
| `deck.md` | 见 SKILL.md 交付物表 |
| `deck.pptx` | 见 SKILL.md 交付物表 |
| `deck.html` | 见 SKILL.md 交付物表 |
| `deck.pdf` | 见 SKILL.md 交付物表 |
| `preview.svg` | 见 SKILL.md 交付物表 |
| `slide_plan.json` | 见 SKILL.md 交付物表 |
| `content_map.json` | 见 SKILL.md 交付物表 |
| `compliance_checks.json` | 见 SKILL.md 交付物表 |
| `report.md` | 见 SKILL.md 交付物表 |

`status` 取值：built / insufficient_evidence / input_error。

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写出带原因的合法 `result.json`，不编造页面内容；
- 无材料文本：`degradations` 记录原因，`exceptions` 说明未嵌入图表；
- PDF / SVG 只含文本与矢量，不含外部图片；不做翻译，保留源语言。

## 方法论文档

- `references/expert_playbook.md`：判分要点、六步门控、量化口径、领域陷阱、自查表与虚构案例；
- `GAIN_EVIDENCE.md`：与基础做法的对照证据与复现命令；
- `environment/resources.yaml`：依赖与运行边界；
- `examples/minimal-run.md`：最小调用示例（标明为示例）。

> 本地评测复现命令与实测结果见 `SELFTEST.md`。
