# mindmap-builder — 思维导图构建（writing-17 v6）

把材料整理成一张**可追溯的思维导图**：先建索引（材料 / 标题 / 小节），再推导大纲
（root + branches），为每个分支挂上带 `locator` 的叶子摘录，最后输出结构化 `mindmap.json`、
人读 `mindmap.md`、大纲 `outline.json` 与报告。契约的五个键 `init / show / check / build /
selfcheck` 对应五个阶段的结构化摘记，逐键回填进 `result.json`。

核心约束：

- 每个分支/叶子都有来源 `locator`（如 `M01#s3`）；不引入材料外的内容。
- 契约五个键始终是非空结构化 dict（`stage/status/...`），不是占位符。
- 空/坏输入仍 exit 0，只保留根节点并写明降级原因，不臆造分支。

## 安装

仅 Python 3.9+ 标准库，离线。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/mindmap-spec.md
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
python3 scripts/main.py init        # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show        # 打印小节与 locator（--grep/--limit）
python3 scripts/main.py check       # 校验 outline 的分支与来源
python3 scripts/main.py build       # 生成思维导图与最终 result.json
python3 scripts/main.py selfcheck   # 复检产物
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 顶层契约键 + `output_contract` 逐键回填、case_id、status、nodes、edges、outline、report、limits、uncertainties、change_records |
| mindmap.json | 结构化图（root / nodes / edges / case_id） |
| mindmap.md | 人读导图（分支 + 叶子 + 来源） |
| outline.json | 根与分支大纲 |
| report.md | 报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：产出诚实的根节点导图与合法 `result.json`。
- 无标题材料：以文件名为根，正文句子生成叶子。
- 不联网、不臆造图片；导图以结构化 JSON 与人读 Markdown 交付。

> 本地评测复现命令与（静态推演的）预期结果见 `SELFTEST.md`。
