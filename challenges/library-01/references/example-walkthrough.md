# 最小调用示例（示意，非正式案例结果）

> 下文输入、命令与输出均为**接口示意**，用于说明一次完整调用如何走完五步；数字来自一个自造的小样例，**不是**任何正式案例的答案或得分证据。

## 1. 示意输入

```
/input/case.json
/input/library/
    raw/2019/paperA.txt            # 含 Title/Author/Year/Project/DOI 与一句结果
    raw/2019/paperA_v2.txt         # 同文档修订版（不同哈希）
    raw/2020/instrument.pdf        # 仪器报告，一句 XRD 描述
    raw/2020/NCM811 最终版 (1).txt  # 与 v2 字节完全相同
    raw/2020/broken.pdf            # 扩展名是 pdf、内容不是 → 损坏
    raw/2020/empty.dat             # 0 字节
    metadata.csv  aliases.csv  version_notes.csv   # 伴随表：字段值、别名、版本备注
```

`case.json` 提供 `case_id`、`output_contract`（11 个键）、`library_root`、两条 `queries`、`rules.directory_template`、一组 `aliases`。

## 2. 五步命令

```bash
S=/skills/weekly-skill/scripts/main.py
python3 -B $S init
```

```
[init] input=/input roots=['library']
[init] files=9 status={'ok': 7, 'corrupt': 1, 'empty': 1} contract=11 keys queries=2
[init] notes: alias=3 version=1 unresolved=2 | dup_groups=1
[init]   non-ok corrupt   library/raw/2020/broken.pdf (magic_mismatch(expected=%PDF- got=b'not a'))
[init]   non-ok empty     library/raw/2020/empty.dat (zero_byte)
[init] partial result.json -> /app/output/result.json
```

```bash
python3 -B $S show --notes
```

```
[show] version edges (prev = superseded file, cur = newer file):
  V01 resolved  library/version_notes.csv#r2  prev='paperA.txt' cur='paperA_v2.txt'
[show] unresolved=2
  ! dangling_alias library/aliases.csv#r3 lost_scan.pdf -> missing.pdf
```

```bash
python3 -B $S show --text library/raw/2019/paperA_v2.txt
```

```
   7| The cell retained 86.2% capacity after 200 cycles at 1C (re-analysed).
```

Agent 此刻写 `/app/work/draft.json`：9 条 `files`、9 条 `organization_plan`、2 条 `metadata`、1 条 `versions`（`basis` 指向 `version_notes.csv#r2`）、1 条 `duplicates`、2 条 `queries`（引文逐字复制第 7 行）、2 条 `recovery`、3 条 `skipped`。

```bash
python3 -B $S check
```

```
[check] draft=draft.json found=True files=9 plan=9 metadata=2 versions=1 queries=2
[check] ready=True fixes=0 warns=0 -> /app/work/check_report.json
```

```bash
python3 -B $S build
```

```
[build] landed=8 verified=8 quarantined=0 dup_groups=1 chains=1 metadata=2 ops=14
[build] queries=2 hit=2 | not_landed=1 | archive members=8 zip=archive.zip
[build] status=ok contract=11/11 elapsed=3.2s -> /app/output/result.json
```

```bash
python3 -B $S selfcheck
```

```
[selfcheck] 11/11 ok | failed=- | hash_verified=8
[selfcheck] status=ok -> /app/output/self_check.json
```

## 3. 示意产物（节选）

```
library/
  + P-NCM811/
    + 2019/paper/          - paperA.txt  - paperA_v2.txt
    + 2020/instrument/     - instrument.pdf
    + _unsorted/           - empty.dat
  + _quarantine/           - broken.pdf
  + _admin/metadata/       - metadata.csv - aliases.csv - version_notes.csv
```

```jsonc
// version_chains.json
{"chain_id": "C01", "confidence": "high",
 "order": ["library/raw/2019/paperA.txt", "library/raw/2019/paperA_v2.txt"],
 "supersedes": "library/raw/2019/paperA_v2.txt",
 "basis": [{"basis": "note:supersedes:library/version_notes.csv#r2", "confidence": "high"}],
 "aliases": [{"path": "library/raw/2020/NCM811 最终版 (1).txt",
              "same_as": "library/raw/2019/paperA_v2.txt",
              "relation": "identical_bytes_alias"}],
 "diffs": [{"type": "text_line_diff", "lines_added": 4, "lines_removed": 0}]}
```

## 4. 同一个输入、没有工作稿时

```bash
python3 -B $S init && python3 -B $S build     # 没有 /app/work/draft.json
```

```
[build] status=partial contract=11/11
[build] degradations=draft_missing, plan_missing, files_not_landed,
        metadata_partly_from_sidecar, draft_versions_missing, query_answered_by_script
```

交付仍然完整（契约 11 键全回填、文件落库并校验哈希、备注驱动的版本链、关键词检索的逐字引文），但判断层缺失被如实写进 `degradations`，`status` 降级为 `partial`。这就是兜底路径的边界：**不空目录、不崩溃、不谎报**。
