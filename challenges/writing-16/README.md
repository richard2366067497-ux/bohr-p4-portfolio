# source-faithful-retargeting（v10）— 安装、调用与自检

把一份科研事实底稿改写成「目标读者读得懂、原作者接得住、每条事实找得到来源」的成稿，并交付可
逐段复核的记录。**执行前先读 `references/expert_playbook.md`（专家方法论与检查表）。**

## 1. 安装与运行

安装位置 `/skills/weekly-skill`（Harness 挂载点），提交目录 `/app/submission` 为兜底；一律用
**绝对路径**调用（cwd 不保证是 Skill 根目录）；仅依赖 Python 3 标准库，离线、不联网、不写输入
目录；退出码**恒为 0**，异常写入 `result.json.errors`，已产出文件保留。

单命令（等价入口，评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --work /app/work --output /app/output
python3 scripts/main.py all --input /input --work /app/work --output /app/output   # 包内相对写法
```

五命令主路径（Agent 增强路径）：

```bash
python3 /skills/weekly-skill/scripts/main.py init      # 扫输入、建索引、写合法 partial result.json
python3 /skills/weekly-skill/scripts/main.py show      # 打印带 locator 的原文，供逐字引用
#   ↓ 你（Agent）亲自读材料，写 /app/work/draft.json（正文真写，不是提纲）
python3 /skills/weekly-skill/scripts/main.py check     # 机械校验：契约/引文/数字/覆盖/术语/强度/篇幅
python3 /skills/weekly-skill/scripts/main.py build     # 生成 deliverable.md + 附表 + 最终 result.json
python3 /skills/weekly-skill/scripts/main.py selfcheck # 复检产物：契约键、可复算指标、文件
```

## 2. 环境与资源

- 无外部数据：受众矩阵、体裁骨架、强度词表在 `references/*.md`；运行环境与依赖声明见
  `environment/resources.yaml`。
- 环境变量 `SKILL_INPUT` / `SKILL_WORK` / `SKILL_OUTPUT` 可覆盖默认目录（与 `--input/--work/--output` 等价）。
- 输出目录不可写时自动退到包旁的 `work/`、`output/`，并把该降级写进 `degradations`。
- 支持 `.md .txt .json .csv .tsv .tex .rst .bib` 文本，以及 PDF/DOCX/XLSX/图片的可用文本层；
  解析不了的类型只降级、不报错，并记入 `degradations` 与 `sources`。

## 3. 自检（SELFTEST，可复算）

```bash
python3 scripts/main.py all --input /input --work /app/work --output /app/output   # 退出码 0，五个产物齐全
python3 scripts/main.py selfcheck --input /input --work /app/work --output /app/output  # PASS 覆盖契约/引文/漂移/篇幅
python3 scripts/main.py --help                                                      # 退出码 0，列出 all/init/show/check/build/selfcheck
```

本地 `scripts/eval_sim.py` 对照复算（rich / boundary × single / agent 四组合），完整记录见 `SELFTEST.md`：

```bash
python scripts/eval_sim.py --pkg work/p4/v10/writing-16 --case work/p4/synth_cases/writing-16/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/writing-16 --case work/p4/synth_cases/writing-16/boundary --mode agent
```

## 4. 已知边界

- 不做统计推断、不补源文之外的数据、不代写结论；缺口进 `uncertainty` / `open_questions`。
- 兜底稿（无工作稿）只做逐字抽取，`status=partial`，稿首明确标注「未完成受众改写」。
- 机械守卫用词表+正则，能证明“数字/单位/引用没丢、强度没漂移”，不能证明“文笔最好”；语义质量
  仍由人工/平台对照。
- 参考 `GAIN_EVIDENCE.md`（增益对照与运行记录）、`references/expert_playbook.md`（评分口径、框架
  与检查表；旧 `acceptance-rubric.md` 已并入其中）。
