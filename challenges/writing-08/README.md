# writing-08 · 方法与实验章节写作（证据门控版）v10

把散落在配置、日志、代码、论文片段里的实验材料整理成可执行的方法与实验章节，逐条带来源定位，
缺口交作者确认；中英文自适应，纯标准库，离线。

## 快速开始

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

退出码恒为 0。无 `draft.json` 时由 `build` 从 init 台账确定性抽取生成实质工作稿（逐字 quote +
locator），并把 `AUTO_EXTRACT` 记入 `gaps` 与 `degradations`。

## 目录

- `SKILL.md`：技能说明、契约、执行前必读与自检清单。
- `references/expert_playbook.md`：专家方法论（判分要点 / 六步框架 / 公式 / 检查表 / 案例）。
- `references/guide.md`：工作稿 `draft.json` schema、模板、失败模式。
- `scripts/`：引擎（engine/flow 各自双文件分片）+ 入口 `main.py`。
- `environment/resources.yaml`：入口、运行时、预算与必需产物；`examples/case.json`：虚构演示输入。
- `SELFTEST.md` / `GAIN_EVIDENCE.md`：自测记录与可核验增益证据。

## v10 变更

内嵌专家手册；脚本按 30KB 单文件上限切分为 `engine.py`+`engine_tail.py`、`flow.py`+`flow_tail.py`，
行为不变；`GITHUB_URL.txt` 更正为 `richard2366067497-ux` 仓库地址；新增 README、GAIN_EVIDENCE 与
`examples/`。单命令实跑 exit 0；`scripts/eval_sim.py` 四格全 PASS（详见 `SELFTEST.md`）。
