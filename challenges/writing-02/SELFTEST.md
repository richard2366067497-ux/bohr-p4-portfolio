# SELFTEST.md — v6 自测记录

包：`work/p4/v6/writing-02` · 引擎 `academic-language-polish/2.0.0` · 纯标准库。
评测模拟器：`work/p4/scripts/eval_sim.py`（本机用 DSH 内置 Python 3.12.14 运行）。

## 0. 运行环境

```
$PY = D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe
> python scripts/eval_sim.py --pkg work/p4/v6/writing-02 --case work/p4/synth_cases/writing-02/<rich|boundary> --mode <single|agent>
```

## 1. 单命令入口（SKILL.md 第一条命令）

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --out /app/output --work /app/work
```

`eval_sim` 解析结果：`entry.kind = single-command`，`entry.cmd` 逐字如上（上下文含“单命令”）。

## 2. 结果（四组组合全 PASS，failures=[] warnings=[]）

| 用例 | 模式 | status | eval_sim | failures | warnings | 契约来源 |
|---|---|---|---|---|---|---|
| `synth_cases/writing-02/rich` | single | **PASS** | success | [] | [] | `case.json:output_contract`（7 键 + case_id） |
| `synth_cases/writing-02/boundary` | single | **PASS** | partial | [] | [] | `SKILL.md (json sample)`（8 键） |
| `synth_cases/writing-02/rich` | agent | **PASS** | success | [] | [] | `case.json:output_contract` |
| `synth_cases/writing-02/boundary` | agent | **PASS** | partial | [] | [] | `SKILL.md (json sample)` |

四组逐项检查全部 PASS：

```
exit_code PASS · result_json PASS · contract_echo PASS · deliverables PASS (9 交付物) ·
case_id PASS · placeholder_sweep PASS ·
field:status/sources/uncertainties/change_records/limits PASS
```

### rich（single & agent）

稿件 `manuscript.md` 856B，附 `format_requirements.md` 364B 与 `template.tex` 388B。引擎产出 9 个
交付物，`status=success`，`summary=polished 7 sentence(s) of manuscript.md: 1 mechanical edit(s)
applied, 3 review suggestion(s), 1 finding(s) left for author confirmation`。

真实处理（非占位）：

- **applied 1 条**：`S0005 U01` `210 m2/g` → `210 m²/g`（面积单位上标），且 `preserved_facts`
  显示该句原子守恒（`210`、`m²/g` 多重集相等，`conserved=true`）。
- **reported 3 条**（`applied=false`，等作者确认）：`S0001 statistic_missing`（“统计显著性”缺检验量）、
  `S0007 claim_strength`（“最佳”→“在实验条件下表现最好”）、`manuscript abstract_keywords`
  （摘要无关键词行，用正文真实术语生成候选关键词）。
- **compliance K01–K12**：把 `format_requirements.md` 的规格逐条与 `template.tex` 的真实设置比对，
  产出 match/mismatch 混合结论（如 `K01 mismatch`、`K02 match`、`K10 mismatch`），每条带 spec 来源行号。
- **内部 checks C1–C8 全 pass**；`uncertainties` 1 条、`limits` 4 条；`output_contract` 8 键
  （7 契约键 + `case_id`）逐个给真实值，无 `string`/`object` 类型占位符。

### boundary（single & agent）

输入 `case.json.output_contract = null`、`materials/empty.md`(0B)、`materials/broken.json`(坏 JSON)、
`materials/notes.txt`(10B)。契约从 `SKILL.md` 的 `json` 样例解析为同一 8 键。

- `status=partial`，`summary=no manuscript text could be selected from 3 material(s); a gap report
  lists what the author must supply`；exit 0。
- `polished.md` 是**缺口报告**（列出已读材料 + 需作者补充的正文/参考文献/格式要求），非空白文件。
- 8 个契约键全部非空且有真实值：`deliverable.role="gap report (no manuscript supplied)"`、
  `preserved_facts` 记 `status="no sentence-level manuscript text was available"`、
  `format_spec=F00 "no format specification document was supplied"`、
  `compliance_checks=K00 … status="not_verifiable"` 等；`custom_unknown_field` 逐字回显并说明来源。
- `placeholder_sweep` PASS（9 个输出文件无 `[待写]`/`null`/`TBD` 等占位串）。

### agent 模式执行计划（两用例一致）

`eval_sim` 注入 `draft.json` 后按 SKILL.md 记录的文档命令链运行：

```
WRITE draft.json (empty — 无打包样例) → build → lint → check → selfcheck
```

五步 code 全 0；末态仍保留全部 9 个交付物与一个合法 `result.json`（`output_file_count=10`，
多出的是 `selfcheck.json`；`work_file_count=2`：`draft.json` + `run_report.json`）。

## 3. 额外功能自测

重复跑同一 rich 输入两次（`build --out o1/o2`）：两份 `result.json` 除 `runtime.seconds`（墙钟）
外**逐字节等价**（`equal modulo runtime.seconds: True`），`runtime={skill, python:"3.12.14",
budget_seconds:900}`，不读时钟、不联网、不调外部模型。

## 4. 自测中发现并已修的问题

1. **E07 冠词重复**（“aa study”）→ 改为前瞻匹配，`_an` 只返回冠词本身。
2. **E10 数字-单位空格不触发** → 由矛盾的后顾改为 `(数字)(单位)` 捕获 + `r"\1 \2"`。
3. **`atoms_hold` 误拒合法空格编辑** → 归一化空白后按多重集比较，放宽 `_NUM` 尾部 `(?![0-9])`。
4. **Z04 替换吞掉单位** → 由 `r" \1"` 改为 `r"\1 \2"`。
5. **英/中规则双触发** → 增加 `_rule_applies` 按 CJK 占比分语言闸门。
6. **`deep_clean` 误改字典键**（`path`→`item`）→ 不再净化键名，只净化值。
7. **格式合规错判**（GB/T 行落入“字号”分支、字体误判 match、把标题当规格、表注朝向反了）
   → 重排分支优先级、按子句切分去重、字体池按 CJKmainfont/mainfont 精确取值、修正表注 above/below 逻辑、跳过 `#` 行。
8. **交叉引用误报**（`fig1.png` 被当 `Fig.1`、`表 1` 重复）→ `CAPTION` 加 `re.M`、加文件名守卫、去重。
9. **单文件 30KB 上限** → 把入口拆成 `main.py` + `polish_core.py` + `review.py`，`polish_core.py` 精确压到 29,939B。

## 5. 包清单

```
SKILL.md                   14806 B
README.md                   5564 B
SELFTEST.md                 <this file>
GITHUB_URL.txt               108 B
environment/resources.yaml  1427 B
scripts/main.py            26474 B
scripts/polish_core.py     29939 B
scripts/review.py          18187 B
```

8 个文件、合计约 101.5 KB（≤8 文件、≤150KB、单文件 ≤30000B、纯标准库、无网络）。
