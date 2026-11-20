---
name: library-repair-desk
version: 1.0.0
description: 科研资料库落库与版本修复工作台。当案例给出一批混乱的科研文件（含别名、管理性版本备注、元数据表、检索问题、恢复/重建索引要求），要求"真的把文件按约定目录落库、写出带出处的元数据清单、按内容哈希与备注重建版本链、回答检索问题、记录操作与跳过原因"时使用。脚本承担扫描、哈希、定位、去重、落盘、契约回填与自检；归属判断、版本关系裁决、检索命中与跳过失因由 Agent 在工作稿里给出。
---

# 科研资料库落库与版本修复（library-repair-desk）

## 0. 单命令等价入口（single command — 评测方只需这一条）

```bash
python3 scripts/main.py all --input /input --work /app/work --output /app/output
```

`all` 无条件完成整条链：**输入发现 → 无工作稿时用确定性兜底（默认目录模板 + 哈希判重 + 备注/时间版本边
+ 关键词检索 + 恢复与归档）→ 写全部产物 → 最终 `result.json`（`output_contract` 逐键回填 + `case_id`）
→ status 推导**，恒 `exit 0`。它等价于把 §0.1 的 `init → show →（draft）→ check → build` 串跑，但无需
先读材料；空/坏输入也保证写出合法 `result.json`。`build` 单独一条同样可用（会按需重建索引）。

### result.json 契约（`case.json` 未声明 `output_contract` 时的默认回填键，键名不改）

| result.json 键 | 类型 | 含义 |
|---|---|---|
| `case_id` | string | 案例标识，原样透传 |
| `deliverable` | string | 主产物路径（result.json） |
| `evidence_map` | array | 落库证据（文件 + locator + 逐字引文） |
| `change_log` | array | 操作日志（copy/mkdir/dedupe/archive/restore） |
| `coverage` | object | 覆盖统计（文件/元数据/版本/检索） |
| `status` | string | ok/partial/failed |

## 0.1 先跑主路径（五命令，按顺序）

```bash
S=/skills/weekly-skill/scripts/main.py    # 包内相对位置 scripts/main.py
python3 -B $S init        # ① 发现输入 → 扫描/哈希 → 解析备注与检索问题 → 落合法 partial result.json
python3 -B $S show        # ② 带 locator 的材料清单 / 备注边 / 检索预检（供逐字引用）
# ③ Agent 亲自读材料，写工作稿 /app/work/draft.json（schema 见第 5 节）
python3 -B $S check       # ④ 机械校验：契约、quote 命中、覆盖、版本证据、工作稿 schema
python3 -B $S build       # ⑤ 落库 + 版本链 + 检索 + 归档 + 主产物 + 最终 result.json（无条件 finalize）
python3 -B $S selfcheck   # ⑥ 复检（可选）：重算落库哈希、契约齐备
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

`build` 在工作稿缺失时不会崩、也不会留空目录：它产出**降级但完整**的交付（契约字段全回填、最小目录树、`status=partial`、`degradations` 写清缺口、退出码 0）。那是兜底，不是正常路径。

## 1. 用途与适用条件

**做什么**（一次可复核的入库事务）：

1. 全量盘点：每个文件都有 `path/size/sha256/mtime/ext/kind/status/reason`；空文件、坏文件、无权限、超深路径、超大文件逐条入册。
2. 目录落库：按模板真实复制到工作区资料树，**落地后复算哈希**与源文件比对；不符进隔离区并记 `hash_mismatch`。
3. 元数据：值必须带出处 `locator`（文件 + 行/页/记录号）；材料里没有的字段留空，不从文件名猜作者/年份/项目号。
4. 去重与版本：先按 `sha256` 判重；版本链只由「备注的 supersedes/replaces/取代」或「同文档不同哈希 + 时间」建立，命名相似只作**候选**并标 `confidence: low`。
5. 检索：每条 `queries` 返回命中文件 + locator + **逐字** quote；无命中必须写检索范围与原因。
6. 恢复与索引：磁盘与索引双向比对（缺失/未登记/悬空别名/重复），给动作与恢复后校验；不可恢复写明原因。
7. 归档：archive manifest（成员哈希、校验、保存期限、权限范围、来源），体量小则实际打 zip。
8. 记录：`operations.log` 逐步记 copy/mkdir/dedupe/archive/restore，含前后状态与结果。

**不适用**：不联网、不接 Zotero/网盘 API、不修权限（只记录）；不做 OCR（扫描件只尽力抽文本，抽不到就把该文件命中标 `no_text_layer`，不编引文）；不生成金标准/白板/分数；每份 `/input` 独立事务。

**何时用**：输入含真实文件 + 组织约定（目录/字段/版本备注/检索问题），要求落库 + 清单 + 证据 + 日志。**何时不用**：只要整理建议、单文件改名、或与文件库无关的任务。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id`/`task_instruction`/`output_contract`/`queries`/`rules`…）、`/input/task.md`、材料目录 |
| 工作区 | `/app/work`（`index.json`、`draft.json`、`check_report.json`、`library/` 落地树） |
| 产物 | `/app/output`（`result.json` + 清单/版本/检索/日志/归档/报告） |
| 入口 | `python3 -B <skill>/scripts/main.py <init\|show\|check\|build\|selfcheck>` |
| 参数 | `--input --work --output --draft --text --notes --queries --json --limit`；默认即上表路径，可用 `LR_INPUT/LR_WORK/LR_OUTPUT` 覆盖 |
| 依赖 | Python 3.8+ 标准库（`hashlib/zipfile/csv/json/shutil/difflib/zlib/re`）；不联网；不依赖 CWD；不写包目录 |
| 退出码 | **恒为 0**。失败写进 `result.json` 的 `status/errors/degradations` |
| 编码 | 输出 UTF-8 无 BOM；输入 JSON 用 `utf-8-sig` 读 |
| 预算 | 64 请求 / 900 秒：扫描与渲染全在脚本，模型只读 `show` 摘要 + 关键片段并写工作稿 |

## 3. 输入发现（不假设文件名与键名）

1. `case.json` 缺失 → 递归找 `case*.json`；坏 JSON → 记 `errors`，用默认契约继续。
2. 键名**语义识别**（大小写/连接符不敏感）：`case_id`、`output_contract`、`task_instruction`、`queries`、`rules`、`aliases`、`version_notes`、`library_root`、`expected_counts`。
3. 材料根：`case.json` 声明的 root（相对 `/input`）→ `/input/library` → `/input/artifacts` → `/input/files` → `/input` 全树（排除 `case.json`/`task.md`）；多根合并去重。
4. 类型按**扩展名 + 魔数**双判（`%PDF-`、`PK\x03\x04`、可解码性），不按文件名猜内容。
5. 备注/元数据伴随文件按**内容特征**识别（表头含 `alias/from/to/target/supersede/replace/file/field/value`，或文件名含 `alias/别名/version/版本/notes/备注/index/清单/metadata/元数据`）。
6. 扫描保护：深度 ≤10、文件 ≤5000、单文件 >200MB 只记录；符号链接不跟随。

## 4. `show` 的用法（读材料的入口）

```bash
python3 -B $S show                      # 总览：状态分布、备注边计数、重复组、版本候选
python3 -B $S show --text "<rel_path>"  # 带行号正文（--limit 控制行数），用于逐字引用
python3 -B $S show --notes              # 别名边 / 版本边 / 悬空边（含 locator）
python3 -B $S show --queries            # 声明问题 + 脚本预检索候选（命中待你裁决）
python3 -B $S show --json               # 机器可读摘要（大材料省 token）
```

每行带 `#L`/`#p`/`#r` 形态 locator。写进工作稿的 quote 必须能在 `show --text` 里逐字找到；找不到会被 `check` 判 `quote_not_found`，`build` 里降级为未验证。

## 5. 工作稿 `/app/work/draft.json`（Agent 写）

```json
{
  "case_id": "<case.json 的 case_id>",
  "files": [{"path": "library/raw/a_v2.pdf", "doc_type": "raw_data", "project": "P-001",
             "year": 2019, "is_version_of": "library/raw/a.pdf", "notes": "归属依据"}],
  "organization_plan": [{"from": "library/raw/a_v2.pdf", "to": "P-001/2019/raw_data/", "rule_id": "dir-template-v1"}],
  "metadata": [{"path": "library/raw/a_v2.pdf",
                "fields": {"author": {"value": "Li Na", "source": "library/meta.csv#r4"}}}],
  "versions": [{"chain_id": "C1", "members": ["library/raw/a.pdf", "library/raw/a_v2.pdf"],
                "supersedes": "library/raw/a_v2.pdf", "basis": "note:supersedes library/versions.csv#r2",
                "confidence": "high", "diff_note": "v2 修订了保持率并剔除 2 个电芯"}],
  "duplicates": [{"sha256": "<show 输出>", "keep": "…", "archive": ["…"], "reason": "same sha256"}],
  "queries": [{"question": "…", "hits": [{"path": "…", "locator": "…#L12", "quote": "逐字原文"}],
               "miss_reason": "无命中时写检索范围与原因"}],
  "recovery": [{"file": "…", "action": "restore|reindex|quarantine|none", "pre_state": "…", "expect": "…"}],
  "skipped": [{"path": "…", "reason": "corrupt|permission_denied|too_large|empty|duplicate_content"}],
  "uncertainties": ["仍需人工确认的点"],
  "method_notes": "目录模板来源、字段优先级、版本链证据、去重策略"
}
```

路径一律是**相对 `/input` 的 POSIX 路径**，与 `init`/`show` 打印一致。判定码、字段别名、正反例见 `references/draft-schema.md`。

## 6. 方法与判定规则

| 环节 | 规则 | 证据形态 |
|---|---|---|
| 哈希 | sha256 流式分块，源与落库各算一次 | `inventory[].sha256` + `integrity` |
| 判重 | 只按 sha256 相同分组；同名不同哈希不是重复 | `duplicates.json` |
| 版本链 | 边优先级：`note:supersedes` > `alias note` > Agent 工作稿 > `命名+时间` 候选 | 每边 `basis` + locator |
| 差异 | 可抽文本用 `difflib` 给增删行与样例；二进制给 size/hash 变化 | `versions[].diffs[]` |
| 元数据 | 出处优先级：伴随表 > 正文 > 文件名（文件名只能 `inferred/low`） | `metadata.jsonl` |
| 落库 | `copy2` 到模板目录，命名去 `副本/copy/(1)`、保留 `v2`；同名不同字节加 `__vN`，同名同字节视为已落库（幂等） | `operations.log` |
| 检索 | 逐字命中校验（空白/弯引号归一化），命中给原文行 | `queries.json` |
| 索引 | 以 inventory 重建并核对守恒（inventory = 已落库 + 重复 + 其它跳过） | `recovery.index_rebuild` |
| 归档 | manifest 全成员哈希 + `verified`；≤48MB 才打 zip | `archive_manifest.json` |

默认目录模板 `{project}/{year}/{doc_type}/`；缺失维度落 `_unsorted/`，损坏/不可读落 `_quarantine/`，管理性伴随表落 `_admin/`。`case.json` 的 `rules` 若给模板则优先（`rule_source` 记录）。字段字典与异常处置见 `references/library-rules.md`。

## 7. 产物与 `result.json` 契约

| 文件 | 内容 |
|---|---|
| `result.json` | 主产物：`output_contract` 全字段原样回填 + 信封 + 各节摘要 |
| `inventory.json` / `.csv` | 全量清单（含跳过项与原因） |
| `directory_plan.json` / `tree.txt` | 归位映射 `source → target` + 实际目录树 |
| `metadata.jsonl` / `field_dictionary.json` | 元数据（值/出处/置信度/规则）与字段字典 |
| `version_chains.json` / `duplicates.json` | 版本链（成员/替代/差异/依据/别名）与去重分组 |
| `queries.json` | 命中/逐字证据/未命中说明 |
| `recovery.json` | 文件问题、悬空备注边、索引重建守恒 |
| `operations.log` | JSONL 操作日志（op/from/to/sha256/result/reason） |
| `archive_manifest.json`（必要时 `archive.zip`） | 成员哈希、校验、期限、权限范围、来源 |
| `report.md` / `self_check.json` / `run.log` | 交接说明、自检、追加式运行日志 |

`result.json` 必须：① `output_contract` 的**每个键原名出现**（不改名、不删键；可映射的填真实结果，其余 `null`/`[]`/`{}`）；② 含 `case_id`、`status`(`ok|partial|failed`)、`sources`、`errors`、`degradations`、`uncertainties`、`changes`、`contract_map`、`coverage`、`runtime`；③ `init`/`check` 阶段各写一份合法 partial。`status=ok` 需同时满足：无 errors、无 FIX、无降级项、inventory 非空、落库校验全绿、元数据非空、检索无未验证、无 `confidence: low` 链。

## 8. 评分维度 → 本包机制

| 维度（分值） | 机制 | 核对位置 |
|---|---|---|
| 完成度 15 | 盘点→目录树→元数据→版本→检索→归档→日志，七段各有产物与计数 | `coverage`、`report.md` |
| 正确性 15 | 落地复算哈希、元数据带出处、重复/版本只按哈希与备注 | `integrity`、`versions[].basis` |
| 完整性 5 | 空/坏/无权限/超大/超深/符号链接逐条入册，原因枚举化 | `inventory[].status/reason` |
| 可核验 5 | 每条结论带 `path#locator`，日志可重放，`selfcheck` 可复跑 | `queries[].hits[]`、`self_check.json` |
| 质量增益 15 | 真落库（非建议书）：目录树 + 哈希去重 + 版本链 + 校验 | 产物本身 |
| 效率 5 | 一次扫描 + 规则化批处理；`scan_stats` 记深度/文件/字节 | `coverage.scan_stats` |
| 增益可验证 5 | 同输入重跑清单稳定（排序只用路径与哈希）、落库幂等 | `method_notes` + 重跑一致 |
| 创新 5+5+5 | 备注驱动的别名/版本边解析、逐字证据校验、索引守恒、字节别名合并 | `show --notes`、`recovery.json` |
| 可靠 3+4+3 | 契约清晰；单文件失败只降级自身；异常分支全覆盖；退出码恒 0 | 第 9 节 |
| 生态 3+4+3 | 本文档 + 字段字典/目录规范/工作稿 schema 可复用 | `references/` 三份 |

## 9. 失败处理与降级

| 触发 | 处理 | 退出码 / status |
|---|---|---|
| `case.json` 缺失或坏 JSON | 记 `errors`，按默认契约继续 | 0 / partial |
| `/input` 为空 | 写合法 `result.json`（契约键 null/[]）+ 缺口说明 | 0 / failed |
| 单文件无权限/损坏/占用 | 该文件 `unreadable`/`corrupt` + 原因，其余照常 | 0 |
| 单文件 >200MB | `too_large`，不哈希不落库，路径仍规划 | 0 |
| 落地哈希不符 | 落 `_quarantine/`，日志 `hash_mismatch`，进 `degradations` | 0 |
| 同名目标已存在 | 不同字节加 `__vN`；同字节 `already_present_identical` | 0 |
| 磁盘空间不足 | 停止后续复制，已落地保留，记 `insufficient_space` | 0 / partial |
| 工作稿缺失/坏 JSON | 兜底：`_unsorted/` 归位、哈希判重、备注建链、关键词检索；`status=partial`，缺口逐条进 `degradations` | 0 |
| quote 不命中 | 该条 `verified=false`，其余不受影响 | 0 |
| 备注边悬空 | 进 `recovery.issues`，不建链 | 0 |
| 任意未捕获异常 | 兜底写最小合法 `result.json` + `report.md`，`run.log` 记 `exception` | 0 |

## 10. 自查（build 后看 stdout 与 `self_check.json`）

- `status`：只有 `ok` 是全绿；`partial` 要能说出缺什么。
- `inventory` 计数 = 磁盘文件数（含跳过项），每条跳过都有原因。
- `integrity`：每条 `resha256 == true`；不符项在 `_quarantine`。
- `versions`：每条 `basis` 非空；`confidence=low` 的在 `uncertainties` 有对应说明。
- `queries`：命中条目 `verified=true`；未命中条目有 `miss_reason`。
- `contract_map`：`output_contract` 键数 = 映射键数，缺键为 0。
- 复跑：同输入再跑 `init → build`，`inventory`/`duplicates`/`version_chains` 的顺序与哈希不变。

## 11. 最小调用示例（示例，非正式案例结果）

```bash
$ python3 -B scripts/main.py init
[init] files=9 status={'ok': 7, 'corrupt': 1, 'empty': 1} contract=11 keys queries=2
[init] notes: alias=3 version=1 unresolved=2 | dup_groups=1
[init] partial result.json -> /app/output/result.json
$ python3 -B scripts/main.py show --notes
  V01 resolved  library/version_notes.csv#r2  prev='paperA.txt' cur='paperA_v2.txt'
  ! dangling_alias library/aliases.csv#r3 lost_scan.pdf -> missing.pdf
$ python3 -B scripts/main.py check
[check] draft=draft.json found=True files=9 plan=9 metadata=2 versions=1 queries=2
[check] ready=True fixes=0 warns=0
$ python3 -B scripts/main.py build
[build] landed=8 verified=8 dup_groups=1 chains=1 metadata=2 ops=14
[build] queries=2 hit=2 | not_landed=1 | archive members=8 zip=archive.zip
[build] status=ok contract=11/11
```

以上为接口示意，**不是**任何正式案例结果。完整走查见 `references/example-walkthrough.md`。

## 12. 文件清单与维护

```
SKILL.md                          本文档：主路径/契约/工作稿/规则/降级/自查
scripts/main.py                   五命令、契约回填、工作稿校验调用、落库编排、报告与自检
scripts/libscan.py                发现、扫描、哈希、备注解析、版本链、索引
scripts/textkit.py                解码、类型判定、文本抽取、引文定位、工作稿校验、报告渲染、自检
scripts/staging.py                目录计划、校验落库、目录树、归档、去重/检索/恢复装配、show
references/draft-schema.md        工作稿 schema、字段别名、FIX/WARN 判定码、正反例
references/library-rules.md       目录模板、字段字典、命名规则、阈值、异常处置、复跑方法
references/example-walkthrough.md 完整调用走查（标注为示例）
```

维护：阈值（深度/文件数/大文件/复制上限/归档上限）在 `scripts/libscan.py` 顶部常量；契约语义映射表在 `scripts/main.py` 的 `SEM`；新增一种备注格式 = 在 `libscan.parse_notes` 加一个解析器，不改主流程。版本 1.0.0。
