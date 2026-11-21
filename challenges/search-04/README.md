# citation-trace — 引文追踪与关联文献发现（search-04 v10）

把一批文献材料整理成**可回链的引用网络**：从种子文献出发，沿引用关系（前向/后向）与关联信号
（共被引、文献耦合、作者/机构、数据集/任务）扩展，合并预印本/会议/期刊/增补版身份，
输出可追溯的候选、排序依据与遗漏说明。核心约束：

- 每条边保留 `locator` 与方向（cites / lists）；每条结果可独立复核。
- 缺字段如实记录（`gaps.json`）不猜补；快照外引用标为缺口，不编造。
- 契约逐键回填到 `result.json.output_contract` 与顶层同名键，`case_id` 原样透传；空集合给诚实非空结构。

## 执行前必读

先读 `references/expert_playbook.md`（专家参考手册），按其 **§2 八步框架**推进、按 **§3 量化口径**
计算、按 **§4 陷阱清单**排雷，交付前逐项通过 **§7 防扣分自查表**；任一项未过则 `status=partial`。

## 安装

仅 Python 3.9+ 标准库，离线，无第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/expert_playbook.md
  references/citation-contract.md
  environment/resources.yaml
  examples/case.json  examples/expected_output.json  examples/materials/sample-records.md
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
# Agent 读材料、写 /app/work/draft.json（seed + edges）
python3 -B scripts/main.py check      # 校验 draft 边的 source/target
python3 -B scripts/main.py build      # 组装网络/路径/缺口并定稿 result.json
python3 -B scripts/main.py selfcheck  # 复检产物
```

## 产物（写入 `--output`，共 6 个）

| 文件 | 内容 |
|-|-|
| result.json | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、seed、网络、路径、缺口、limits、uncertainty、change_records |
| citation_network.json | 节点（文献）与边（cites/lists） |
| edges.jsonl | 逐条边（source、target、kind、locator、marker） |
| traced_paths.json | 从种子出发的路径与深度 |
| gaps.json | 元数据缺口与越界引用 |
| report.md | 人类可读报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无引用边 / 无路径：`edges / paths / gaps` 给带 `status`/`note` 的诚实非空结构，`degradations` 记原因。
- 不联网、不查询外部引文库（Crossref/EuropePMC/OpenAlex）、不臆造元数据；结论限定在所给快照内。
- 唯一非 0 退出码是 argparse 用法错误（2）。

> 本包能力说明；本地评测脚本的复现命令与实测结果见 `SELFTEST.md`，增益口径见 `GAIN_EVIDENCE.md`。
