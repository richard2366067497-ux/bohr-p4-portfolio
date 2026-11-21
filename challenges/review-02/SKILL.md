---
name: citation-fact-audit
description: Audit one research manuscript against its own materials - index the real files, locate every checkable claim verbatim, judge citation support, source reliability and evidence location, type every finding with severity and an executable revision, and deliver a report plus an annotated manuscript where each line carries a locator. Degrades honestly when the material cannot support a verdict.
license: MIT
---

# 引用与事实核验：论文质量审查

围绕一份稿件与它的材料做**可复核**的质量审查：逐条给出问题定位（locator）、逐字原文、判定依据、
严重度与修改建议；判定引用是**存在**还是**支持结论**；无法确认的条目标记待复核，绝不凭空补结论。

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 `references/expert_playbook.md`**，并按其检查表组织全部产出：

- **流程**：按其 §2 六步审查（索引→定位→三要素判定→分级→覆盖→交付）推进；前一步未冻结不进入下一步。
- **判定**：按其 §3 四级支持度与三要素决策顺序；按其 §4 严重度与 `verdict_type` 分级。
- **口径**：按其 §5 覆盖矩阵、误报抑制规则与容差；按其 §6 领域陷阱逐条排雷。
- **可追溯**：按其 §7 locator 与证据规则，报告里每个结论回到 `{材料}→{段落}→{逐字原文}`。
- **门控**：交付前逐项通过其 §8 自查表（18 项）；未过项记 `partial` 并写入不确定性。

## Output contract

`case.json -> output_contract` 的每个键都会原样回显到 `result.output_contract` 与结果顶层，并带上本次
产出的内容；无 case 契约时使用以下标准字段集（键名不新增、不改名）：

```json
{"output_contract": {"case_id": "string", "deliverable": "path", "evidence_map": "array", "change_log": "array", "coverage": "object", "status": "string"}}
```

## Draft shape（唯一由 Agent 写的文件）

Agent 可在运行前写 `work/draft.json`；脚本会重算每一条判定，不一致处保留为 `changes` 修正记录。
缺工作稿时脚本给出机械候选并全部标记待复核，不会伪造判定。

```json
{"case_id": "REPLACE_WITH_INPUT_CASE_ID", "summary": "", "claims": [{"claim_id": "C-01", "claim_text": "", "verdict": "undetermined"}], "citation_checks": [{"claim_id": "C-01", "claim_quote": "", "claim_locator": "", "claim_strength": "primary", "cited_source": {"label": "", "source_locator_if_available": ""}, "verdict": "undetermined", "semantics": {"direction_match": null, "numeric_match": null, "scope_match": null}, "rationale": "", "unresolved_reason": "未定位逐字原文", "human_check_needed": "打开 claim_locator 指向的段落，逐字填入 claim_quote 后重跑 check"}], "findings": [], "coverage": {}, "uncertainties": []}
```

`claim_quote` 必须逐字取自材料（NFKC + 去空白后仍须落在**单个**段落单元内）；`verdict` 取
`full_support | partial_support | no_support | undetermined`；`undetermined` 必填 `unresolved_reason`
与 `human_check_needed`。字段含义与同义映射见 `references/contract-and-playbook.md`。
## 单命令入口（一次性，无需 draft）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

一条命令建立索引、finalize（无工作稿时用机械候选并标待复核）、写全部交付物并自检，退出码 0。
`--input` / `--output` / `--work` 默认即 `/input`、`/app/output`、`/app/work`，也可显式传入。

## Agent 路径（同一引擎，可先写工作稿）

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`init` 建索引并提示候选；`show` 打印可定位材料与段落单元；`check` 校验工作稿；`build` 无条件 finalize；
`selfcheck` 重读已写交付物，数字漂移即 FAIL；`compare` 给出无门控基线与本包的对照。

## 交付物

`result.json`（契约回显 + `status`/`sources`/`uncertainties`/`change_records`/`limits`）、`citation_report.md`、
`manuscript.md`、`evidence.jsonl`、`index.json`、`run_manifest.json`。

## 判定与门控

六类 facet：citation / fact / statistics / logic / method / compliance，每类必须给出 checked 状态。
判定顺序固定：先看引文标记是否配对，再看三要素（方向、数值、范围），最后才谈严重度；`full_support`
要求三要素全 true，否则降为 `partial_support`/`no_support` 并记入 `changes`。严重度只有
critical / major / minor / suggestion。每次 `build` 都是 finalize：部分完成也要交出可复核结果并写清 limits。

## 降级与边界（记录，不隐藏）

缺工作稿、工作稿非法、变量无法解析、材料不可读、数值/引文无法配对、契约字段无法映射、写入失败，
一律写成 `degradations` 并保持 `partial`；`status` 只取 `completed` / `partial` / `input_error`。
绝不把未选中的候选当结论，绝不删材料行而不计数，绝不编造缺失的软件状态或数据。纯标准库、离线、
无时钟依赖；同一输入两次 `build` 输出字节一致。

## 自检清单（交付前逐项通过）

- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §8 的 18 项全部通过；未过项记 `partial` 并列入不确定性。
- [ ] 每条结论可回到材料原文（locator + 逐字 quote），quote 校验未命中即降级待复核。
- [ ] 六类 facet 均有覆盖状态，`coverage` 非空且与实际检查一致。
- [ ] 每条问题条目有 severity、severity_reason、evidence 与可执行 revision。
- [ ] 待复核条目写明 `unresolved_reason` 与 `human_check_needed`，不静默提升为 confirmed。
- [ ] `result.json` 含全部契约键与 `status`/`sources`/`uncertainties`/`change_records`/`limits`，无空壳占位符。
- [ ] 单命令入口 exit 0，且无工作稿时仍产出完整契约与全部交付物。
