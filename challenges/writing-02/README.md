# academic-language-polish — 学术语言润色（writing-02）

逐句学术语言润色：一条命令完成「读取材料 → 识别语言 → 选择成稿 → 逐句最小改动 →
保护原子与限定词闸门 → 术语/缩写/格式合规审查 → 交付 润色稿 + 修改记录 + 逐句覆盖 +
术语表 + 保留事实清单 + 证据映射 + 契约回填的 `result.json`」。

核心主张：**改语言，不改事实**。数字、单位、引用、交叉引用、公式与 DOI/URL 逐条比对，
多重集不相等就整句回滚；限定词强度不得削弱（删弱词）或拔高（加断言词）。

## 安装

无需第三方依赖（Python 3.9+ 标准库）。把本目录放到 `/skills/weekly-skill` 即可：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py            入口：build / lint / check / selfcheck
  scripts/polish_core.py     读取、切句与 locator、保护原子、限定词、规则、术语、语言识别
  scripts/review.py          审查层：静态发现项、格式合规、建议规则、缺口报告
  environment/resources.yaml 资源与预算声明
  README.md  GITHUB_URL.txt  SELFTEST.md
```

脚本用 `__file__` 自定位，不依赖当前工作目录。

## 用法

单命令全流程（评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/scripts/main.py build \
  --input /input --out /app/output --work /app/work
```

默认值即 `--input /input`、`--out /app/output`、`--work /app/work`。它读入 `case.json` 与
全部材料，选出成稿，逐句应用可自动化的最小改动、给出建议，再做术语/缩写/格式审查，
最后写出全部产物并把 `output_contract` 逐键回填进 `result.json`。

其他入口：

```bash
python3 <skill>/scripts/main.py lint      --input /input --out /app/output --work /app/work
python3 <skill>/scripts/main.py check     --input /input --out /app/output --work /app/work
python3 <skill>/scripts/main.py selfcheck --input /input --out /app/output --work /app/work
```

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

### agent-first 路径

脚本负责确定性规则与证据，Agent 负责判断与措辞，二者不可互替：

```bash
python3 <skill>/scripts/main.py lint  --input /input --out /app/output --work /app/work
# Agent 读 /app/output/lint_report.json 与 coverage.json，写 /app/work/draft.json
python3 <skill>/scripts/main.py check --input /input --out /app/output --work /app/work
python3 <skill>/scripts/main.py build --input /input --out /app/output --work /app/work
python3 <skill>/scripts/main.py selfcheck --input /input --out /app/output --work /app/work
```

`draft.json` 形状：`{"edits": [{"sid", "before", "after", "reason"}]}`。
应用草稿有三条硬约束——`sid` 必须存在、`before` 必须是该句逐字子串、改后仍须通过
保护原子与限定词闸门；任一不满足就跳过并记入 `limits`。缺省或坏 JSON 一律回退到确定性
结果，不报错。

## 产物（写入 `--out`）

| 文件 | 内容 |
|-|-|
| `polished.md` | **润色后的成稿**（只含已应用的最小改动；未找到成稿时是缺口报告） |
| `changes.json` | 修改/建议清单：`{counts, entries[{sid,locator,type,rule,applied,before,after,reason,source}]}` |
| `changes.csv` | 同一清单的 CSV 版，便于表格复核 |
| `coverage.json` | 逐句覆盖：每句 applied/suggested 计数、处理动作、locator |
| `glossary.json` | 双语术语表、出现形态、首次位置、变体与缩写提示 |
| `preserved_facts.json` | 逐句保护原子、限定词画像与守恒闸门结果 |
| `evidence_map.json` | 逐句到材料、行号、字节区间的映射（含 sha256） |
| `lint_report.json` | 静态审查 `{status, counts, findings[], compliance[]}` |
| `result.json` | 契约回填 + 结构化结果 |

`--work` 下另有 `draft.json`（若提供）与 `run_report.json`（本轮摘要与产物字节数）。

## 示例（示意，非正式案例结果）

输入 `manuscript.md`：

```
The catalyst showed the best activity at 300 °C, with a BET area of 210 m2/g.
```

示意输出（`status=success`）：

- `polished.md`：`210 m2/g` → `210 m²/g`（U01，applied）；
- `changes.json`：同时给出 `claim_strength`（“the best” 建议弱化为实验条件下的表述）与
  可核验的 `before/after/reason/locator`；
- `preserved_facts.json`：`300`、`°C`、`210`、`m²/g` 原子守恒，`conserved=true`。

未找到成稿时 `status=partial`，`polished.md` 是一份**缺口报告**（列出需要作者补充的材料），
而不是空白文件。

## 限制

- 不整段代写、不做中英互译长文、不补造参考文献或统计结果、不渲染 docx/PDF 版式。
- docx/xlsx/pdf 材料报 `unparsed_material` 并说明原因，不猜正文。
- 超出证据的过强论断（最高级/绝对化）与“声称显著但缺检验量”只报告（`applied=false`），
  由作者确认；规则不改结论方向。
- 格式合规格与模板都没有对应设置时写 `not_verifiable` 并说明原因，不臆测。

## 维护与版本策略

- 版本 2.0.0；遵循语义化版本：契约键名冻结 → 主版本变更才动；新增规则 → 次版本；
  阈值与文案 → 修订号。
- 规则目录、闸门口径与契约口径集中在 `SKILL.md`，是唯一的规则真相来源；脚本按此执行。
- 每次改动后跑 `selfcheck` 与 `scripts/eval_sim.py`（rich/boundary × single/agent），
  结果记入 `SELFTEST.md`。
