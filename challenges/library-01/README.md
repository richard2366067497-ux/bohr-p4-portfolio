# library-repair-desk · 文件库盘点与修复

面向「文件库盘点与修复」任务的 Skill 包。核心脚本只使用 Python 标准库，输入 `/input`，输出 `/app/output`，中间态放 `/app/work`，退出码恒为 0（问题写入 result.json 的 errors/degradations）。

## 快速开始

单命令（一次跑完，无 draft）：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

分步（Agent 路径）：`init → show → (draft) → check → build → selfcheck`。

## 输入 / 输出

- 输入：`/input/case.json`、`/input/task.md`、`/input/materials/`。
- 输出：`/app/output/result.json`（含 `output_contract` 原样回填）+ 全部交付物：inventory.csv、operations.log、report.md、duplicates.json、version_chains.json、result.json。
- 契约键：`case_id, deliverable, evidence_map, change_log, coverage, status`（case.json 提供 `output_contract` 时以其为准）。

## 方法论

执行前阅读 `references/expert_playbook.md`，按其中检查表逐项产出。量化目标：文件覆盖率 ≥95%；哈希一致率 =100%；元数据字段填充率 ≥90%；去重准确率 =100%；版本链完整率 =100%；静默跳过率 =0%；操作日志可复跑率 ≥90%；目录规范符合率 =100%。

## 依赖与限制

- 仅标准库；不联网；不访问作者私有路径。
- 预算：≤64 次模型请求、≤900 秒、≤16384 tokens/响应。
- 材料缺失/损坏/无权限时如实降级为 `partial`，不伪造结果。

## 文件结构

```
SKILL.md                 命令接口与契约
references/expert_playbook.md  专家方法论（判分/公式/检查表/案例）
scripts/                 主入口与内核（纯标准库）
environment/resources.yaml     资源清单
examples/minimal.md      最小调用示例（示意输出，非正式结果）
SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```
