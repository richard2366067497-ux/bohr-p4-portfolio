# latex-edit-build-verify (writing-12, v7)

LaTeX 写作与编译：**静态体检 → 最小可逆修复 → 真实构建 → 日志归因 → 交付可编辑工程**。
纯 Python 标准库、离线、确定性；每次运行 exit 0 并留下合法 `result.json`。

## 安装

把本目录放到 `/skills/weekly-skill`（DeepSeek Harness 的约定安装根）；脚本用 `__file__`
自定位，不依赖当前目录。

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/latex_build.py build \
    --input /input --output /app/output --work /app/work --engine pdflatex
```

无 `.tex` 输入时，会从 `case.json`/`task.md`/材料确定性起一份可编辑 `main.tex`；
有 `latexmk`（或直接引擎）时尝试真实构建，产出合法 PDF（头 `%PDF-`）才交付。

## Agent-first 路径

```bash
python3 /skills/weekly-skill/scripts/latex_build.py lint  --input /input --output /app/output --work /app/work
# Agent 读 /app/output/lint_report.json，按需写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/latex_build.py fix   --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/latex_build.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/latex_build.py selfcheck --input /input --output /app/output --work /app/work
```

## 子命令

| 子命令 | 作用 |
|---|---|
| `build` | 全链：发现 → 体检 → 修复 → 构建 → 归因 → 写产物 |
| `lint` | 只做静态体检，写 `lint_report.json`（不调用引擎） |
| `fix` | 应用可逆修复（含 `draft.json`），写 `fixes.json` |
| `check` | 全链 + 「通过/需人工」闸门，写全部产物与 `checks` |
| `selfcheck` | 校验结果契约形状，写 `selfcheck.json` |

## 产物（写入 `--output`）

`main.tex`（修复后可编辑根文件）· `source/`（工程树副本）· `main.pdf`（编译成功时）·
`diff.patch`（输入→`main.tex` 统一 diff）· `lint_report.json` · `fixes.json` · `build.json` ·
`log-check.json` · `packages.md`（宏包说明 + 固定编译命令）· `comparison_report.md`
（对照实验记录：基础 Agent vs 加载本 Skill 的**确定性自评表**，明确标注非官方 A/B）· `compile.sh` · `result.json`。

## 依赖

Python 3.9+；`build/check/fix/selfcheck` 需要 `latexmk` 或直接引擎（`pdflatex`/`xelatex`/`lualatex`）；
中文稿需 `xelatex` + `ctex`/`xeCJK` + CJK 字体。缺引擎时 `status=partial`、`build.status=missing_tool`，
并在 `limits` 给出可执行的复现命令——**未验证 ≠ 通过**。

## 诚实规则

- `success`：真实构建出合法 PDF，且无 error 级诊断、无 `unresolved_*`、无 `duplicate_label`。
- `partial`：源码已体检/修复（或已按材料起稿）但未取得可用构建（缺引擎/超时/仅静态）。
- `failed`：找不到根 `.tex` 且无法起稿，或构建产生 error 级诊断 / 无合法 PDF。

详见 `SKILL.md` 与 `references/checks.md`。
