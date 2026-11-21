# 文件库盘点与修复 · 专家方法论手册

本手册描述「文件库盘点与修复」任务的判分口径、求解框架、量化公式、错误模式、自查表与案例。它是产出质量的下限：命令接口见 SKILL.md，方法论以下文为准。核心原则：**落库可复核、关系按内容哈希判定、异常如实记录、过程可复跑**。

## 1. 交付本质与判分要点

本任务要求的不是「分类建议」，而是 `/app/output` 下**可复核的落库结果**：真实目录树、文件清单、元数据表、版本关系、操作日志、哈希与来源记录。复核者核对的是：

1. 文件是否真的被复制/移动到约定目录；
2. 元数据是否真实、有出处、可逐字段追溯；
3. 重复与版本关系是否按内容哈希（而非文件名）判定；
4. 跳过、冲突、无权限、损坏是否被诚实记录；
5. 他人能否按日志与命令复跑并得到一致结果。

| 维度 | 分值 | 关键证据 |
|---|---|---|
| 实际效果 | 40 | 目录树、元数据清单、哈希记录、版本链、操作日志 |
| 使用增益 | 25 | 相对基础流程的字段填充率、去重准确率、版本识别率提升，且有同输入对照 |
| 创新增益 | 15 | 内容哈希去重、模板驱动归位、批量字段映射、版本差异比对、归档包生成 |
| 可靠体验 | 10 | 调用顺畅、重复运行稳定、异常被识别与处置 |
| 生态贡献 | 10 | 文档、模板、字段字典、脚本、示例可复用 |

## 2. 求解框架（每步冻结产物 + 门控）

| 步骤 | 动作 | 冻结产物 | 门控通过条件 |
|---|---|---|---|
| 0 读取输入 | 读 case.json、task.md、materials 实际文件、environment/resources.yaml | `input_snapshot.json` | 已取得 case_id、规则、材料清单 |
| 1 盘点与权限 | 递归遍历，记录路径、大小、mtime、权限、类型；检测不可读/损坏 | `inventory.csv` | 每文件含 source_path、size_bytes、mtime、permissions、readable |
| 2 解析规则 | 从 task.md 提取目录层级、命名规则、元数据字段、版本策略、归档要求 | `rules.json` | 目录模板、字段字典、去重/版本策略已结构化 |
| 3 生成计划 | 为每个文件生成落库路径、去重判断、版本关系、跳过原因 | `plan.json` | 每文件有 action：copy/deduplicate/version/skip/conflict |
| 4 执行落库 | 复制/移动、算哈希、写元数据、重建版本链、记操作 | `operations.log`、`metadata.csv`、`version_graph.json` | 哈希一致率 100%，无未记录覆盖 |
| 5 生成清单证据 | 目录树、文件清单、哈希清单、来源定位、变更记录 | `manifest.json`、`tree.txt`、`checksums.sha256` | 每条有 locator 与逐字引用 |
| 6 自检复算 | 独立复算哈希、核对目录树、字段填充率、版本链 | `selfcheck.json` | 复算与主结果一致，差异已说明 |
| 7 输出契约 | 写含全部 output_contract 字段的 result.json，生成预览 | `result.json`、`previews/` | JSON 合法、case_id 正确、status 诚实 |

任何一步门控未过，不得进入下一步；时间不足时先保存部分结果并标记 `partial`。

## 3. 量化口径

| 指标 | 公式 | 合格线 |
|---|---|---|
| 文件覆盖率 | `(processed + skipped_recorded) / total_files × 100%` | ≥95%，未覆盖必须记录 |
| 哈希一致率 | `hash_matched / copied_files × 100%` | 必须 100% |
| 元数据字段填充率 | `filled_fields / total_required_fields × 100%` | ≥90%，缺失须有来源说明 |
| 去重准确率 | `correct_duplicate_pairs / actual_duplicate_pairs × 100%` | 必须 100% |
| 版本链完整率 | `complete_version_groups / actual_version_groups × 100%` | 必须 100% |
| 静默跳过率 | `unrecorded_skips / total_skips × 100%` | 必须 0% |
| 冲突记录率 | `recorded_conflicts / total_conflicts × 100%` | 必须 100% |
| 操作日志可复跑率 | `reproducible_steps / total_steps × 100%` | ≥90%，不可复算须说明 |
| 目录规范符合率 | `compliant_paths / total_dest_paths × 100%` | 必须 100% |

**自洽示例**：输入 12 个文件（10 正常、1 无权限、1 损坏），复制 10、记录跳过 2 → 覆盖率 `(10+2)/12=100%`；哈希一致 `10/10=100%`；元数据 6 字段×10=60，填 54 → `90%`；实际 3 对重复全识别 → `100%`；1 组 3 版本完整 → `100%`；静默跳过 `0/2=0%`；冲突 `1/1=100%`；20 步中 19 可复算 → `95%`；落库路径全合规 → `100%`。

## 4. 错误做法 → 正确做法

| 错误做法 | 正确做法 |
|---|---|
| 只给建议不动手落库 | 实际创建目录、复制/移动文件、写清单 |
| 移动文件但不留哈希与日志 | 每个落库文件记录 SHA-256、源/目标路径、时间、操作类型 |
| 静默跳过无权限/损坏文件却报「全部完成」 | 跳过写入 failures/skipped，给原因与证据 |
| 同名直接覆盖致版本链断裂 | 先算内容哈希再决定去重/版本/冲突，禁止无记录覆盖 |
| 元数据靠文件名猜 | 每字段标 `source_field`（filename/content/sidecar/manual），无法确认填 null 并记不确定性 |
| 把未完成写成完成 | status 区分 completed/partial/failed，部分完成列限制 |
| 只有最终结果无中间证据 | 保留 operations.log、checksums.sha256、manifest.json |
| 中文/特殊字符文件名乱码或丢失 | 统一 UTF-8 NFC 路径，日志不省略不可见字符 |

## 5. 领域知识清单

**事实性陷阱**
1. 用文件名判断重复 → 必须用内容 SHA-256；同名不同内容不可去重。
2. 用 mtime 判断版本先后 → mtime 可能被复制重置，应结合哈希、版本号、日志或伴随表格。
3. 把二进制当文本读 → PDF/DOCX/XLSX/RAW/ZIP 按二进制处理，文本提取只用于元数据。
4. 忽略路径编码差异 → macOS NFD 与 Linux NFC 可能视同名为异名，统一 NFC。
5. 解压不防 Zip Slip → 检查路径穿越，禁止写出目标目录之外。
6. 哈希算法不当 → 用 SHA-256，不用 MD5/SHA-1 作唯一完整性证据。
7. 权限表示不一致 → 同时记录八进制（0644/0755）与符号（rw-r--r--）。
8. 时间戳混乱 → 统一 ISO 8601 UTC，本地时间标注时区。
9. 大小单位混淆 → 字节整数 + KiB/MiB/GiB（1024 进制），不混用 MB/MiB。
10. 元数据字段缺出处 → 每字段必须有 `source_field`，否则视为不可信。

**单位/量纲**：大小以 B 为基本单位（1 KiB=1024 B）；SHA-256 固定 64 位十六进制，截断须标「前 12 位」；时间统一 UTC；权限八进制 3/4 位；注意路径长度限制（255 B/组件，4096 B/路径）。

**依据要求**：若声明「按某标准归档」须给出标准名与版本（如 ISO 14721 OAIS）；若借鉴 Dublin Core/DataCite 须注明字段映射；任何「最佳实践」须有可复算记录支撑。

## 6. 防扣分自查表

1. ☐ 实际创建目录并复制/移动文件，而非只给建议
2. ☐ 每个落库文件记录 SHA-256
3. ☐ 每个落库文件记录源路径与目标路径
4. ☐ 每个元数据字段标注 `source_field`
5. ☐ 跳过/无权限/损坏文件进入 failures 或 skipped
6. ☐ 无静默跳过
7. ☐ 无同名覆盖导致版本链断裂
8. ☐ 重复判断基于内容哈希而非文件名
9. ☐ 版本关系基于内容哈希与可靠时间戳
10. ☐ 所有冲突被记录并给出处置
11. ☐ result.json 含 case_id、status、sources、uncertainty、change_records
12. ☐ status 诚实区分 completed/partial/failed
13. ☐ 提供 operations.log 且可据以复跑
14. ☐ 提供 checksums.sha256 且可 `sha256sum -c` 验证
15. ☐ 目录树与模板一致，无多余/缺失目录
16. ☐ 元数据填充率 ≥90%，缺失有说明
17. ☐ 去重准确率 100%
18. ☐ 版本链完整率 100%
19. ☐ 日志可复跑率 ≥90%，不可复算已说明
20. ☐ 可编辑产物（DOCX/XLSX/PPTX）有 PDF/PNG 预览
21. ☐ 未编造正式案例、白板或预生成答案
22. ☐ GITHUB_URL.txt 置于根目录，链接有效且免登录
23. ☐ 资源 ≤50 个文本文件、≤500KB/个、≤2MB 总量、无 symlinks
24. ☐ 最小示例标明「示例」，不冒充正式结果

## 7. 完整虚构案例（输入 → 中间量 → 输出）

> 虚构演示，仅说明流程与数字自洽，不代表任何正式案例。

**输入**：`case.json` 要求按 `library/<project>/<year>/<data_type>/` 组织；必填字段 `file_id, source_path, dest_path, sha256, size_bytes, mtime, project, year, data_type, version_of, derived_from, permissions, source_field`；内容哈希相同为重复，`v1/v2/_copy` 同逻辑文件重建版本链。materials 共 12 个文件：`data.csv` 与 `data_copy.csv` 同内容（2,306,048 B）、`data_v1.csv`(2,211,840) / `data_v2.csv`(2,412,544) 与之成链、`notes.pdf` 与 `notes（副本）.pdf` 同内容、`analysis_2021.docx` 与 `_backup` 同内容、`仪器原始数据.raw` 与 `_已改名.raw` 同内容、`no_access.dat` 无权限、`broken.zip` 损坏。

**关键中间量**
- 哈希（前 12 位）：data/data_copy=`a3f2c9d1e4b5`；data_v1=`c1d2e3f4a5b6`；data_v2=`b7e8f0a1c2d3`；notes 两件=`d4e5f6a7b8c9`；analysis 两件=`e7f8a9b0c1d2`；仪器两件=`f0a1b2c3d4e5`。
- 重复对 4 对（data、notes、analysis、仪器）；去重准确率 4/4=100%。演示若只列 3 对则须修正为 4 对。
- 版本链 1 组三版：`data_v1 → data_v2 → data.csv`，哈希不同、大小递增、文件名含版本号。
- 跳过 2 个：`no_access.dat`（PermissionError，reason=permission_denied）、`broken.zip`（BadZipFile，reason=corrupt_file）。

**输出**：目录含 result.json、manifest.json、metadata.csv、version_graph.json、operations.log、checksums.sha256、tree.txt、previews/。result.json 关键字段：

```json
{
  "case_id": "CASE-2024-001",
  "status": "completed",
  "results": {"total_files": 12, "processed": 10, "skipped": 2, "duplicate_pairs": 4,
              "version_groups": 1, "hash_match_rate": 1.0, "metadata_fill_rate": 0.90,
              "duplicate_accuracy": 1.0, "version_chain_completeness": 1.0,
              "silent_skip_rate": 0.0, "conflict_record_rate": 1.0, "log_reproducibility": 0.95},
  "evidence": {"manifest": "manifest.json", "operations_log": "operations.log",
               "checksums": "checksums.sha256", "tree": "tree.txt"},
  "failures": [
    {"file": "restricted/no_access.dat", "reason": "permission_denied", "recorded": true},
    {"file": "corrupt/broken.zip", "reason": "corrupt_file", "recorded": true}
  ]
}
```

metadata.csv 每行含 `source_field`（如 filename），version_graph.json 每组含 `relationships` 的 replaces 边。复算：`sha256sum -c checksums.sha256`；`find library -type f | sort` 与 tree.txt 比对；用 csv 复算字段填充率。所有数字须与 result.json 一致。
