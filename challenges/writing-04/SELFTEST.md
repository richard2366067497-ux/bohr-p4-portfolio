# SELFTEST — 自测记录（writing-04 v10）

包：`work/p4/v10/writing-04` · 引擎 `citation-ledger-sync/3.1.0` · 纯标准库、离线、确定性。
评测模拟器：`scripts/eval_sim.py`。
解释器：`D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe`（Python 3.12.14）。
随包新增专家方法论 `references/expert_playbook.md`，SKILL.md「执行前必读」要求按其检查表产出。

## 一、eval_sim（rich/boundary × single/agent，本地门禁）

```
python scripts/eval_sim.py --pkg work/p4/v9/writing-04 \
    --case work/p4/synth_cases/writing-04/<rich|boundary> --mode <single|agent>
```

| 案例 | 模式 | 结果 | 契约来源 |
|---|---|---|---|
| rich | single | **PASS** | `case.json:output_contract`（8 键） |
| rich | agent | **PASS** | `case.json:output_contract`（8 键） |
| boundary | single | **PASS** | `SKILL.md (json sample)`（8 键） |
| boundary | agent | **PASS** | `SKILL.md (json sample)`（8 键） |

四组全过，无 `WARN`、无 `suggestions`。逐项检查均为 PASS：`exit_code`、`result_json`、
`contract_echo`、`deliverables`、`case_id`、`placeholder_sweep`、`field:status`、`field:sources`、
`field:uncertainties`、`field:change_records`、`field:limits`。

- rich：稿件 `C01_chapters.md`（4 段，无引文、无文献库）→ 引擎产出 16 个文件；契约 8 键用
  诚实信封（`references`/`key_to_number`/`duplicates`/`unknown_keys`）或真实数组（`sources`/`uncertainty`/
  `change_records`）回填；`status=partial`，exit 0，无占位符。
- boundary：`case.json.output_contract=null`、`empty.md`(0B)、`broken.json`(坏 JSON)、
  `notes.txt=`标记行 → 契约从 `SKILL.md` 的 json 样例解析为同一 8 键；引擎 exit 0，写合法 `result.json`
  （`status=partial`，`limits`/`uncertainty` 说明原因），交付物齐全。

agent 模式命令链 `all → probe → draft → check → build` 全程 exit 0，末态保留全部交付物与 `result.json`。

## 二、算法自测（`selftest`，内存合成语料）

```
python work/p4/v9/writing-04/scripts/cite_engine.py selftest
```

结果（`ok=true`，exit 0）：解析 BibTeX 3 条 → 去重规范 2 组（1 组合并，判据 `identical DOI`）→
GB/T 与 APA 各渲染 1 条 → claim 匹配 2 条。关键断言 `parsed=3 / groups=2 / merges=1 / claims>=1`
全部成立，证明去重、双格式渲染与引用匹配是**真实算法**而非模板。

## 三、端到端真实处理自测（`work/p4/v7/_scratch/full`）

输入：`manuscript.md`（含 `[2]`、`\cite{chen2019cool}`、悬空 `[9]`）+ `lib.bib`（3 条，其中 2 条同 DOI）。

```
python work/p4/v9/writing-04/scripts/cite_engine.py all \
    --input work/p4/v7/_scratch/full --output <out> --work <work>
python work/p4/v9/writing-04/scripts/cite_engine.py check --input ... --output <out>
```

观察到的真实行为：

- 解析 3 → 规范 2；`dedup_decisions.csv`：`chen2019cool/chen2019cool_b` 判 `merge`，置信度 `0.99`，
  理由 “identical DOI: 10.1017/jmr.2019.101”。
- `verification.csv`：`chen2019cool` = `clean`；`smith2020fill` = `error`（DOI 用示例前缀 `10.1234/`）。
- `claim_support.csv` 2 行：`The fill compositing technique ... [2].` → `smith2020fill`（`matched`, score 0.60,
  shared `compositing|fill|parts`）；`Cooling rate ... \cite{chen2019cool}` → `chen2019cool`（`matched`）。
- `references.gbt.md` 与 `references.apa.md` 各 2 条，字段一致、风格不同。
- `changes.csv`：`merge` + `format` 行，均带 `locator` 与逐字 `quote`。
- `check`：`{"ok": true, "problems": []}`（契约键齐、编号唯一、改动可溯）。

## 四、确定性

- 纯标准库、无网络、无时钟读取；`result.json.runtime={mode:offline-deterministic, network:false}`。
- 同一输入重复运行，交付物字节稳定。

## 五、包清单（v10）

```
SKILL.md                      12841 B
README.md                      3376 B
SELFTEST.md                   <this file>
GITHUB_URL.txt                  112 B
GAIN_EVIDENCE.md               5252 B
environment/resources.yaml     2922 B
examples/case.json              314 B
examples/lib.bib                760 B
references/contract.md         5646 B
references/expert_playbook.md 15991 B
scripts/cite_engine.py        29904 B   （整理模块 docstring 后 < 30000 B）
scripts/citelib.py            24926 B
scripts/citerender.py          6837 B
```

13 个文件、合计 116,448 B（≤14 文件、≤150KB、单文件 ≤30000 B、纯标准库）。

## 五之二、v10 复跑结果

`eval_sim.py` 四组组合（`work/p4/v10/writing-04` × {rich,boundary} × {single,agent}）全 **PASS**，
`failures=[] warnings=[]`；契约来源：rich `case.json:output_contract`（8 键）、boundary
`SKILL.md (json sample)`（同 8 键）。

单命令实跑（输入 `examples/`）：`exit 0`，`status=success`，17 个产物，契约 8/8 回填。
`__pycache__` 已清理。

相对 v9 的差异：新增 `references/expert_playbook.md`（判分要点/公式/GB·T 陷阱/检查表/虚构案例）；
`cite_engine.py` 由 30,333 B 压到 29,904 B；版本 3.0.0 → 3.1.0。

相对 v6 的设计差异见下。

## 六、相对 v6 的设计差异

| 维度 | v6（citation-ledger-sync/2.0.0） | v7（3.0.0） |
|---|---|---|
| 脚本形态 | 4 个脚本（citelib/citecore/citerender/cite_engine），合计 ~119KB | **3 个脚本**（citelib/citerender/cite_engine），合计 ~62KB |
| 入口 | `cite_engine.py run` | `cite_engine.py all`（单命令等价入口，agent 路径 `probe`→`check`→`build`） |
| 双格式 | 单目标风格 + `--style` | 同一批记录**同时**输出 `references.gbt.md` 与 `references.apa.md` 供对拍 |
| 去重理由 | 见 dedup_decisions | `reasons` 逐条写清判据文本（DOI/题名/作者年/相似度数值） |
| 引用匹配 | claim_support.csv | 增加每行 `locator`（`L行:C列`/`C偏移`）+ 逐字 `quote` |
| 契约回填 | 顶层 + 结构位 | 同样双层；空集合一律用诚实信封（`kind/items/count/note`） |
| 自证 | 无内置算法断言 | 新增 `selftest` 子命令，对内存语料断言去重/渲染/匹配确实生效 |

## v8 复跑与关键数字（examples/）

新增随包最小样例 `examples/`（`case.json` + `lib.bib`，3 条记录、2 条同 DOI），可被评审直接复跑：

```bash
python3 scripts/cite_engine.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：

- exit 0，`result.json.status = success`，产物 **17** 文件。
- `counts = {input_records: 3, canonical: 2, merges: 1, changes: 3}`；`duplicates` 1 条
  （DOI `10.1017/jmr.2019.101`，confidence 0.99）；`unknown_keys.count = 0`；契约键 **8/8**；占位符 0。
- 规范化哈希（`result.json` 删除 `runtime.seconds` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`50be7104cc5964f4`**。
- `scripts/eval_sim.py` rich/boundary × single/agent 四项全 **PASS**（契约键 8/8）。


## v9 交付状态

- GITHUB_URL.txt 两行（公开仓库 + challenges/writing-04），补齐官方 5 分公开链接加分。
- 随包生态齐备：examples/（case.json + lib.bib，可复跑）、environment/resources.yaml、README.md、
  GAIN_EVIDENCE.md（含确定性 aseline_sim 诚实对照）、SELFTEST.md。
- scripts/eval_sim.py rich/boundary × single/agent 四项全 **PASS**（契约键 8/8，placeholder_sweep 干净）。
