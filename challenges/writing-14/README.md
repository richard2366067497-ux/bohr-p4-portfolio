# sci-mindmap-builder — 材料 → 可核验思维导图（writing-14）

把一批科研材料变成**一张可编辑、可核验的分层思维导图**：中心主题、主分支、要点节点、跨分支关系、
来源映射、数字台账，一次落盘到 `/app/output`，并把 `output_contract` 逐键回填进 `result.json`；
随产物落盘五项可核验资产（金标准、对照报告、版本记录、自检、日志）。

## 安装

纯 Python 3.9+ 标准库，无网络、无第三方包。把目录放到 `/skills/weekly-skill`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py        # 入口：init / show / check / build / run
  scripts/verify.py      # 确定性内核：发现、单元抽取、工作稿归一化、证据核验、结构校验、契约
  scripts/render.py      # 渲染与资产层：布局、SVG/PNG、来源映射、金标准、对照、版本、自检
  environment/resources.yaml
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

单命令全流程（评测只跑这一条也能通过）：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

默认 `--input /input`、`--output /app/output`、`--work /app/work`。退出码恒为 0；
`run` 内部等价于 `init → check → build`，任一步写入的 `result.json` 都会被最终版本覆盖。
加 `--no-probe` 可跳过空输入/坏输入子进程探针（`self_check.json` 会显式标注未探测）。

### agent-first 路径

脚本负责机械判定与落盘，Agent 负责把图长出来：

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show  --work /app/work --material M1 --start 1 --limit 20
# Agent 编辑 /app/work/mindmap.json（theme / nodes / edges），每个节点都要有 material + locator + quote
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

工作稿缺失或全无效时，`build` 回退到确定性抽取（一小节一个分支、每分支最多 3 个要点、
一条语料支撑的 support 关系），并把回退写进 `degradations`。

## 最小可运行示例

`/input` 只需一个材料文件（`case.json` 可选）：

```
/input/case.json            {"case_id": "demo-1", "language": "zh"}
/input/paper.md            五个小节：研究问题 / 方法与材料 / 结果 / 结论 / 局限与风险；
                           结果段含 30、80、0.2、12%、4% 等数值。
```

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出（本包自测时真实得到，示例而非正式案例结果）：

```
== run | status=ok | nodes=16 | edges=1 | depth=2 | self_check=pass
```

产物：`mindmap.svg`、`mindmap.json`、`content_map.json`、`mindmap.png`、`structure.md`、
`golden_standard.json`、`diff_report.md`、`version_history.md`、`run.log`、`self_check.json`、`result.json`。
空输入或坏 JSON 时 `status=insufficient_evidence`，`result.json` 仍合法、exit 0。

## 判分口径

- 每个节点至少一条 evidence：`material + locator + 逐字 quote`，NFKC 归一后仍命中才算 verified。
- 层级由 `parent` 推出，深度 ≤ 4；同一父节点下 2–5 个子节点；同级标签去重。
- 跨分支关系只用 9 类方向语义（`cause`/`contrast`/`support`/`conflict`/`sequence`/`depends`/
  `cite`/`example`/`definition`），无 quote 支撑的关系直接丢弃并记录。
- 节点里的数字必须能在材料或该节点 quote 中找到，逐条进 `preserved_facts` 台账。
- `diff_report.md` 与 `self_check.json` 的计数由脚本确定计算，重跑 `build` 应复现同一结果。

## 限制

- 不联网、不调用外部模型；节点匹配为确定性规则，人工认可的等价改写可能被判未命中，
  逐条证据会列出命中情况便于复核。
- 图片材料只登记存在性、不做 OCR；PDF 优先 `pdftotext` 取文本层，缺失时用内置解流兜底，
  扫描件仍不可读（记 `degradations`）。
- `mindmap.png` 由标准库绘制几何缩略（标签文字在 SVG/JSON 中）；需要带字预览请用
  `rsvg-convert` / `inkscape` 从 SVG 转换。

## 维护与版本策略

- 版本 2.0.0：契约键名冻结，主版本才改；新增检查/关系类型 → 次版本；文案与阈值 → 修订号。
- 改 schema 需同步 `scripts/verify.py` 的 `normalize_model` / `validate` 与 `SKILL.md` 的规则句
  （`golden_standard.json` 的 `source` 逐条指回行号）。
- 改动后跑一次空输入与坏输入，再用 `scripts/eval_sim.py` 跑 rich/boundary × single/agent，
  记录在 `SELFTEST.md`。
