# 目录规范、字段字典、命名与异常处置

本文件是脚本与工作稿共用的规则表。所有阈值在 `scripts/libscan.py` 顶部常量里，改动只需改一处。

## 1. 目录模板

默认模板：`{project}/{year}/{doc_type}/`

| 维度 | 取值来源（优先级） | 缺失时 |
|---|---|---|
| `project` | `case.json` 的 `rules` > 伴随表 `project` 列 > 正文项目号 | 落 `_unsorted/` |
| `year` | 同上 > 正文四位年份 > mtime 年（须标注 `year_from_mtime`） | 落 `_unsorted/` |
| `doc_type` | `rules` 映射表 > 伴随表 > 文件内容特征（标题/摘要/仪器报告） | 落 `_unsorted/` |

固定保留目录：

| 目录 | 用途 |
|---|---|
| `_unsorted/` | 归属判断缺失或证据不足的文件，**不静默丢弃** |
| `_quarantine/` | 损坏、不可读、哈希不符的文件；保留原字节供复核 |
| `_admin/` | 伴随表、清单、备注等管理性文件（如 `metadata.csv`、`version_notes.csv`） |
| `_admin/duplicates/` | 内容重复但保留了副本的文件（默认不复制，仅在计划里登记） |

`case.json` 若给出 `rules.directory_template` / `template` / `tree` / `pattern`，脚本优先采用，并在 `directory_plan.json` 的 `rule_source` 记为 `draft`，否则记 `fallback_unsorted`。

## 2. 命名规范化

- 删除复制标记：`副本`、`备份`、`copy`、`copy 2`、`(1)`；保留版本记号 `v2`、`rev3`、`_final`（它们是版本信息，不是噪声）。
- Unicode 统一 NFKC；去掉控制字符与首尾空格/点。
- 目标同名且**字节不同**时追加 `__vN`（N≥2），并记 `name_collision_avoided`；目标同名且**字节相同**时视为已落库（幂等重跑），记 `already_present_identical`。
- 永不覆盖既有文件。

## 3. 字段字典（`/app/output/field_dictionary.json` 同源）

| 字段 | 类型 | 定义 | 出处优先级 |
|---|---|---|---|
| `title` | string | 文档题名 | 伴随表 > 正文 > 文件名（文件名只作 `inferred`） |
| `author` | string[] | 作者/负责人 | 伴随表 > 正文署名 |
| `year` | integer | 年份 | 伴随表 > 正文 |
| `project` | string | 项目号/课题代号 | rules > 伴随表 > 正文 |
| `doc_type` | enum | 数据类型 | rules > 伴随表 > 正文 |
| `instrument` | string | 仪器型号 | 伴随表 > 正文 |
| `doi` | string | DOI | 伴随表 > 正文 |
| `keywords` | string[] | 关键词 | 伴随表 > 正文关键词段 |
| `version` | string | 版本记号 | 备注 > 文件名 |
| `status` | string | `superseded/current/draft/unknown` | 版本备注 |

**硬规则**：任何字段值必须带 `source`（`<相对路径>#<L行号|p页|r记录号>`）。从文件名推断的值只能标 `confidence: low` 且 `rule_id: inferred_from_filename`；作者、年份、项目号、仪器型号**不得**仅凭文件名填写。抽不到就写 `null` 或 `confidence: empty`，不编造。

## 4. 版本与重复判定

判定顺序（后者不得覆盖前者）：

1. `sha256` 相同 → **同一份内容**，归入 `duplicates`，不是版本差异。
2. 备注边 `<new> supersedes|replaces <old>`（含 `取代`/`替代`/`作废`）→ 版本边，`confidence: high`，`basis` 记 locator。
3. 别名边 `<alias> -> <canonical>` → 同一逻辑文档的改名/副本，`confidence: medium`。
4. 仅"文档键相似 + mtime 有序" → 候选边，`confidence: low`，必须同时写入 `uncertainties`，**不得**单独作为"谁替代谁"的结论。

排序键：`(mtime, 版本记号数值, 路径)`；`final/定稿/最终` 视为该文档的最高版本。差异 `diffs[]` 对可抽文本的成员给 `lines_added/lines_removed/ratio` 与至多 3 条新增行样例（带 locator），二进制只给 `size_delta` 与哈希变化。

## 5. 扫描与容量阈值

| 常量 | 值 | 触发后的行为 |
|---|---|---|
| `MAX_DEPTH` | 10 层 | 更深的目录记 `max_depth_exceeded`，不入册 |
| `MAX_FILES` | 5000 | 截断扫描并记 `truncated=true` |
| `HASH_LIMIT` | 200 MB | `status=too_large`，不哈希、不落库，目标路径仍规划 |
| `COPY_LIMIT` | 64 MB | 不复制，记 `exceeds_copy_limit` |
| `ZIP_LIMIT` | 48 MB | 不打包，仍写 `archive_manifest.json` |
| 文本上限 | 240k 字符 / 6000 行 | 超出记 `truncated_at_6000`，检索只在该窗口内声明命中 |

## 6. 文件状态与原因（`inventory[].status/reason`）

| status | reason 示例 | 处理 |
|---|---|---|
| `ok` | `null` / `perm_note:no_read_bits_but_readable` | 正常入库 |
| `empty` | `zero_byte` | 入库（0 字节 sha256 已知），进 `recovery.issues` |
| `corrupt` | `magic_mismatch(expected=%PDF- got=b'...')`、`bad_zip:BadZipFile`、`binary_bytes_in_text_file` | 入 `_quarantine/`，不进检索 |
| `unreadable` | `PermissionError`、`IsADirectoryError` | 记录，不落库 |
| `too_large` | `size_gt_200MB` | 记录，不落库 |
| `symlink` | `symlink_not_followed` | 不跟随、不复制，防止越界 |

## 7. 异常分支处置

| 情形 | 处置 | `result.json` 体现 |
|---|---|---|
| 上传中断/半截文件 | 大小与扩展名不符、魔数不符 → `corrupt`，隔离 | `degradations: hash_mismatch_quarantined` 或 `inventory.status` |
| 权限不足 | `unreadable` + 原样记录 mode | `skipped[].reason=permission_denied/unreadable` |
| 重名冲突 | 不覆盖，`__vN` 或幂等跳过 | `degradations: name_collision_avoided` |
| 哈希不符 | 落 `_quarantine/`，操作日志 `result=failed` + `reason=hash_mismatch` | `degradations: hash_mismatch_quarantined` |
| 元数据缺失 | 字段留空 + `confidence: empty` | `coverage.metadata_fields_filled` |
| 存储空间不足 | 停止后续复制，已落地保留 | `degradations: insufficient_space` |
| 备注边悬空 | 不建链，进 `recovery.issues` | `degradations: dangling_alias/dangling_version` |
| 备份不可用 | `restore` 不执行，写明原因 | `degradations: restore_not_executed` |

## 8. 复跑方法（可核验性）

```bash
rm -rf /app/work/library            # 可选：从零复现
python3 -B scripts/main.py init && python3 -B scripts/main.py build --draft /app/work/draft.json
python3 -B scripts/main.py selfcheck
```

- `inventory.json`、`duplicates.json`、`version_chains.json` 的排序只用路径与哈希，不含时间戳 → 同输入两次运行结果字节可比。
- 落库幂等：目标已存在且哈希相同时不再复制（`already_present_identical`），因此重复运行不会产生 `__vN` 尾巴。
- `self_check.json` 的 `SC-06` 会重算每个落库副本的 sha256 与源文件比对；`SC-02` 校验契约键齐全。
- `archive.zip` 若生成，`archive_manifest.json.members[].sha256` 可逐一与 `inventory` 对照。
