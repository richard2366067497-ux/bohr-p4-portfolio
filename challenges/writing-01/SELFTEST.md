# SELFTEST · writing-01（v6 忠实适配）

复现命令（在仓库根目录执行）：

```bash
python scripts/eval_sim.py --pkg work/p4/v6/writing-01 --case work/p4/synth_cases/writing-01/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v6/writing-01 --case work/p4/synth_cases/writing-01/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v6/writing-01 --case work/p4/synth_cases/writing-01/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v6/writing-01 --case work/p4/synth_cases/writing-01/boundary --mode agent
```

## 四格结果（本机实测）

| 用例 | 模式 | 结果 | 契约回填 |
|-|-|-|-|
| rich | single | PASS | `case_id, deliverable, preserved_facts, evidence_map, change_log` |
| rich | agent | PASS | 同上 |
| boundary | single | PASS | 同上（键来自 SKILL.md §5 样例，echo=False） |
| boundary | agent | PASS | 同上 |

四格均无 WARN/FAIL 项（`exit_code / result_json / contract_echo / contract_values /
deliverables / case_id / placeholder_sweep / field:*` 全 PASS）。

## 产物快照

| 用例 | status | 材料数 | 证据句 | manuscript.md | result.json |
|-|-|-|-|-|-|
| rich | `ok` | 8 | 29 | 5000 B | 38127 B |
| boundary | `insufficient_evidence` | 3（0 可读） | 0 | 缺口附录版 | 合法 JSON，逐键给出“材料未提供”的结构化条目 |

- rich 的 `output_contract` 每键值均来自真实证据（含 `source_id` 与 `文件:行号`）。
- boundary 无 `output_contract` 输入，脚本回退到 SKILL.md §5 的五键样例，仍逐键填非空条目，
  不伪造数据。

## 内建探针（`build`/`run` 自动跑，写入 `work/self_check.json`）

| 探针 | 期望 | 实测 |
|-|-|-|
| C1 空目录 | exit 0 + 合法 result.json + `insufficient_evidence` | 通过 |
| C2 坏 JSON 材料 | exit 0 + `json_parse_failed` 降级，其余材料照常 | 通过 |
| C3 模板标记 `[待写]` | 被剪除并记入 `degradations`，不进入正文 | 通过 |
| C4 契约键缺失 | 回退五键样例，逐键非空 | 通过 |

## 包体检查

- 文件数 **7**（上限 8）：`SKILL.md` 7327 / `README.md` 2673 / `GITHUB_URL.txt` 108 /
  `references/contract-and-locators.md` 3124 / `environment/resources.yaml` 1324 /
  `scripts/main.py` 28669 / `SELFTEST.md`（本文件，≈3.6 KB）
- 总字节 **≈46 KB**（上限 150 KB）
- 最大单文件 `scripts/main.py` **28669 B**（上限 30 KB）
- 纯标准库：仅 `argparse / json / os / re / sys / time / zipfile / subprocess / datetime`
- 无网络、无写 `shell`、写范围仅 `--output` 与 `--work`

## 与 p3 参考包的结构对应

| p3 `work/ref/writing-01/` | v6 `work/p4/v6/writing-01/` | 说明 |
|-|-|-|
| `SKILL.md`（init/show/check/build） | `SKILL.md`（首条 `run` 单命令 + init/show/check/build） | 子命令名保留，新增一次性入口 |
| `references/schema.md` | `references/contract-and-locators.md` | 重写为草稿结构 + 定位规则 + 状态规则 |
| `scripts/main.py`（`SE`/`scan`/`sents`/`assemble`/`render`） | `scripts/main.py`（`SECTIONS`/`route_sections`/`verify_quote`/`assemble`/`build_result`） | 同名入口与函数职责对应，实现重写 |
| 产物 `manuscript.md` + `result.json` | 同 | 名称保留 |
| 结果字段 `case_id/deliverable/preserved_facts/evidence_map/change_log/status/sources/uncertainty/pending_human/errors/degradations/changes/coverage/runtime` | 同，并补 `uncertainties/change_records/limits/output_contract` | 字段超集 |
| （新增） | `README.md` / `SELFTEST.md` / `GITHUB_URL.txt` / `environment/resources.yaml` | 使用说明、自测记录、仓库地址、资源与入口声明 |
