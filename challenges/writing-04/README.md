# citation-ledger-sync — 参考文献与引用管理（writing-04, v7）

把一份真实稿件与一份真实文献库处理成一套可继续编辑、可逐条回溯的交付物：真实解析 → 逐对去重
（给出判据）→ 逐条引用匹配（带 `locator`+逐字 `quote`）→ 同一批规范记录同时渲染 **GB/T 7714-2015**
与 **APA 7th** → 写出 `verification.csv` / `claim_support.csv` / `changes.csv` 等与 `result.json`。

## 安装

无需第三方依赖（Python 3.9+ 标准库）。把本目录放到 `/skills/weekly-skill` 即可：

```
/skills/weekly-skill/
  SKILL.md
  scripts/{cite_engine.py,citelib.py,citerender.py}
  references/contract.md
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

单命令全流程（评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/scripts/cite_engine.py all --input /input --output /app/output --work /app/work
```

agent-first 路径：

```bash
python3 /skills/weekly-skill/scripts/cite_engine.py probe --input /input
python3 /skills/weekly-skill/scripts/cite_engine.py check --input /input --output /app/output
# Agent 依据 evidence/candidates 撰写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/cite_engine.py build --input /input --output /app/output --work /app/work
```

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

## 产物（写入 `--output`）

`result.json`、`manuscript.revised.md`、`references.gbt.md`、`references.apa.md`、
`references.deduped.json`、`citation_map.csv`、`dedup_decisions.csv`、`verification.csv`、
`claim_support.csv`、`changes.csv`、`audit.json`、`sources.json`、`uncertainty.json`、
`document_edit.json`、`inventory.json`。

## 示例（示意，非正式案例结果）

`/input` 含 `manuscript.md`（正文含 `[2]` 与 `\cite{chen2019cool}`）与 `lib.bib`（3 条，其中 2 条同 DOI）：

```bash
python3 /skills/weekly-skill/scripts/cite_engine.py all --input /input --output /app/output --work /app/work
# -> status=partial; 3 records -> 2 canonical (1 merge, reason "identical DOI: ...");
#    claim_support.csv 2 rows (matched); references.gbt.md / references.apa.md 各 2 条
```

## 限制

- 无网络：`verification.csv` 只做语法级核验，状态是 `clean|warn|error`，不冒充已联网核验。
- 不自动合并弱相似条目（只列 `manual_review`）；不删除“未被引用”的条目（记入 `uncertainty`）。
- 不新增材料外事实：无法匹配的键只记录，不虚构条目。

## 维护与版本策略

- 版本 3.0.0；语义化版本：契约键名冻结，主版本才改；新增判据/渲染 → 次版本；文案与阈值 → 修订号。
- 判据集中在 `references/contract.md`，脚本按此执行；改动后跑 `selftest` 与 `scripts/eval_sim.py`
  （rich/boundary × single/agent）见 `SELFTEST.md`。
