# latex-free-format-adapter — 学术格式与模板适配（writing-03）

把一个学术稿件包重排为可交付成稿：抽取可逐条核对的版式规格 → 重排为 Markdown 成稿与真实 docx →
校验数字/引用保真 → 回填 `result.json` 契约。纯 Python 标准库，不联网，不改写正文事实。

## 安装

把本目录放到 `/skills/weekly-skill` 即可，无需第三方依赖（Python 3.9+）：

```
/skills/weekly-skill/
  SKILL.md
  scripts/{main.py,core.py,adapter.py}
  references/format-spec.md
  references/expert_playbook.md  专家方法论（执行前必读：判分要点/公式/陷阱/检查表/案例）
  environment/resources.yaml     运行环境、入口命令、预算与依赖声明
  examples/                      最小可复跑样例（case.json + manuscript.md）
  GAIN_EVIDENCE.md               基线对照与使用增益说明（含确定性 baseline_sim）
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

单命令全流程（评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/scripts/main.py run \
  --input /input --output /app/output --work /app/work
```

默认值与上面一致。退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

agent-first 路径：

```bash
python3 <skill>/scripts/main.py probe     --input /input --output /app/output --work /app/work
# Agent 读 <work>/inventory.json，可选地写 <work>/draft.json
python3 <skill>/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 <skill>/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 <skill>/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`draft.json` 形状：`{"title": "…", "spec_overrides": {"body_font_size": "11 pt"}}`；缺省或损坏时
脚本按材料推断，不报错。

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `deliverable.md` | 可编辑的 Markdown 成稿全文 |
| `deliverable.docx` | 真实 OOXML 文档（styles、footer、sectPr 页边距齐全） |
| `format_spec.md` | 规格表：id / 取值 / 来源 / locator / 是否可回溯 |
| `style_map.json` | 规格 → OOXML 单位映射 |
| `fidelity_report.json` | 覆盖统计、事实保真明细、证据条数与待复核数 |
| `pending_human.json` | 需作者确认的缺口、冲突、推断项 |
| `result.json` | 契约回填 + 结构化结果 + 来源 + 不确定性 + 修改记录 + 限制 |

## 示例（示意，非正式案例结果）

输入：`manuscript.md`（正文，含 `[1]` 引用）、`references.md`（`[1] … doi:…`）、`source_A.md`
（含同一 DOI 的摘要）、`format_requirements.md`（`Body font size 11 pt`）。

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

示意结果：`format_spec.md` 的 `body_font_size` 显示 `11 pt`，来源为要求文件的行号与逐字 quote；
若没有要求文件，该行显示 `default profile` 且标记为推断。`result.json.status` 相应为 `ok` 或
`partial`，不会把推断版式写成已验证。

## 限制

- 不做正文改写、翻译或增删文献；只搬不改，量值与引用编号原样保留并计数核对。
- docx 模板只解析 `w:pgMar` / `w:sz` 等可读属性；扫描件模板读不到规格，降级为默认档。
- 证据链依赖参考文献条目中的 DOI 与包内原文片段；缺 DOI 时只判到 `source_not_found`，不猜来源。
- 版面视觉效果未与渲染样本比对，`limits` 中明确写出这一边界。

## 维护与版本策略

- 版本 6.1.0；契约键名冻结，新增规格项需同步 `DEFAULT_SPEC`、`EXTRACT`、`style_map()` 与
  `references/format-spec.md`。
- 改动后运行 `selfcheck` 和 `scripts/eval_sim.py`（rich/boundary × single/agent），见 `SELFTEST.md`。
- 预算与安全边界：完全离线、仅用 Python 标准库、只写 `--output` 与 `--work`，输入树从不改写；
  单文件 ≤30KB、主脚本（`scripts/main.py`）≤25KB，因此代码拆在 `core.py`（共享层）
  与 `adapter.py`（校验与流水线层）两个模块里。
- 执行前先读 `references/expert_playbook.md`，按其中的六步框架推进，交付前逐项通过其 §7 检查表。
