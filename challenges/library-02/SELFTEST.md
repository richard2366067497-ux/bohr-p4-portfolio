# SELFTEST.md

自检不依赖任何外部依赖：`selfcheck` 自行在 `work/` 下生成异常样本并把公开索引路径重跑一遍，
结果写 `work/fixtures_report.json` 与 `output/verify_report.json`。

## 一、一键自检

```bash
python3 -B scripts/main.py all --input /input --out /app/output --work /app/work
python3 scripts/main.py selfcheck --input /input --out /app/output --work /app/work
```

期望：`[selfcheck] status=... ok=True fails=[] ... fixtures=True`，exit 0。

## 二、断言清单

| 断言 | 判据 | 失败表现 |
|---|---|---|
| 契约键顶层回填 | `result.json` 顶层含 `output_contract` 全部十键 | `fails` 出现 `contract:顶层缺键` |
| 契约键嵌套回填 | `result.json → output_contract` 十键齐 | `fails` 出现 `contract:嵌套缺键` |
| 键值为实质投影 | 每键非空 dict（含 `source`/`field`/`rows`） | 键值被判 empty |
| 产物齐全 | 9 个交付物存在且非空 | `artifacts:缺 <name>` |
| 逐字引文 | `quote` 与索引段落按空白归一后完全一致 | `quote:<原因>` 进 `rejected_evidence` |
| locator 回链 | `path`/`paragraph_id`/页码与索引一致且段落可复得 | 同上 |
| `uncertainties` 非空 | Agent 与脚本都能列出不确定项 | `fails` 出现 `uncertainties:空` |
| 失败/降级如实 | `errors`/`degradations`/`failures.json` 与实况一致 | `fails` 出现 `degrade:*` |
| 重复运行一致 | 两次运行 `index_digest` 相同 | `fails` 出现 `digest:漂移` |

## 三、异常样本（运行时生成，不需随包分发）

`fixtures_run()` 在 `work/fixtures/` 写入 8 个样本并逐项核对索引状态：

| 样本 | 期望状态 |
|---|---|
| `encrypted.pdf`（带 `/Encrypt`） | `encrypted` |
| `scan_only.pdf`（无文本层） | `no_text_layer` |
| `legacy.doc`（OLE 头） | `unsupported_legacy` |
| `broken.docx`（伪 zip） | `corrupt` |
| `empty.md`（0 字节） | `empty_file` |
| `denied/private.md`（声明权限拒绝） | `permission_denied` |
| `dup_a/run-notes.md` + `dup_b/run-notes.md`（同哈希） | 两者 `ok`，并入 `identical_copy` 组且其一进 `excluded_evidence` |

结果写 `work/fixtures_report.json`（`all_expected=true`、`duplicate_ok=true`）。

## 四、人工复核

1. `output/answers.json`：抽查 `evidence[].quote` 能否在 `output/index.json` 对应段落中找到逐字原文。
2. `output/location_report.md`：核对 locator 的页码与段落号；无固定页容器应显示 `not_applicable`。
3. 各 answer 内的 `rejected_evidence`：确认过滤被严格执行（`violates_filters`）且未放宽。
4. `output/failures.json` 与 `filters_log.json`：确认跳过/失败/冲突被记录而非写成成功。

## 五、常见问题

- `fails` 非空：看 `output/selfcheck_report.json` 的 `fails` 列表，按上表定位。
- `fixtures=False`：多为新增格式分支未设置状态码，检查 `extract.py` 的状态返回。
- 引文被判不一致：句中空白/换行已归一，仍不一致说明引文被改写（不得改写原文）。
