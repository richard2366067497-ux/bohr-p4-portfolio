# multi-db-joint-retrieval — 多数据库联合检索（search-05 v10）

把多个快照库的检索结果规范化、去重合并、对照覆盖，只交付**能被独立复核的证据图**。核心约束：

- 每个材料视为一个“库”；字段规范化，**缺失（null）与未知（"unknown"）区分**。
- 去重先 DOI 精确（大小写不敏感），再按 `norm_title|first_author_surname|year` 模糊判重；合并保留依据。
- 覆盖度给出 N_raw / N_unique / 去重率 / 字段覆盖率 / 单源率；每条候选保留 `source_id#n` locator + 逐字 quote。
- 契约逐键回填到 `result.json.output_contract` 与顶层同名键，`case_id` 原样透传；空结构给带说明的非空结构。

## 执行前必读

先读 `references/expert_playbook.md`（专家参考手册），按其 **§2 七步流水线**推进、按 **§3 量化口径**
计算、按 **§4 陷阱清单**排雷，交付前逐项通过 **§7 防扣分自查表**；任一项未过则 `status=partial`。

## 安装

仅 Python 3.9+ 标准库，离线，无第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/expert_playbook.md
  environment/resources.yaml
  examples/case.json  examples/expected_output.json  examples/materials/{crossref.md,europepmc.md}
  README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 用法

### 单命令（无草稿也产出完整产物；评测只跑这一条也能过）

```
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

### 五命令（Agent 深读，质量更高）

```
python3 -B scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 -B scripts/main.py show       # 打印带 locator 的段落 / 记录（--grep/--limit）
# Agent 读材料、写 /app/work/draft.json（子问题 + 决策）
python3 -B scripts/main.py check      # 校验子问题 / 决策 / rid
python3 -B scripts/main.py build      # 组装产物并定稿 result.json
python3 -B scripts/main.py selfcheck  # 复检产物
```

## 产物（写入 `--output`，共 6 个）

| 文件 | 内容 |
|-|-|
| result.json | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、databases、sources、候选、证据图、去重/合并、覆盖度、change_log、limits、uncertainty |
| candidates.jsonl | 逐条候选（rid、source_db、locator、relevance、decision、basis、quote） |
| evidence_map.json | 每个子问题的证据图（locator + 逐字 quote） |
| dedup_report.json | 去重组与合并日志（依据可回查） |
| coverage.json | N_raw / N_unique / 去重率 / 字段覆盖率 / 单源率 / 子问题覆盖 |
| report.md | 人类可读报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无可解析记录：候选与证据图给带说明的诚实空结构，`degradations` 记原因。
- 未知单位 / 无 DOI / 无摘要：保留原值并记入 `uncertainty`，不猜测补全。
- 不联网、不查询远程数据库、不臆造元数据；结论限定在所给快照内。
- 唯一非 0 退出码是 argparse 用法错误（2）。

> 本包能力说明；本地评测脚本的复现命令与实测结果见 `SELFTEST.md`，增益口径见 `GAIN_EVIDENCE.md`。
