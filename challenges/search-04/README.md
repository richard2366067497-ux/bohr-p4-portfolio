# citation-trace — 引文追踪与引用网络（search-04 v6）

从种子文献出发，把所给快照中的文献记录与引用标记整理成**可回链的引用网络**，追踪前向/后向路径，
标注元数据缺口与快照外引用。核心约束：

- 每条边保留 `locator`（`M01#p2` / `M01#r1`），可独立复核。
- 缺失 DOI/年份/标题如实记录为 `gaps`，不猜测、不补造。
- 引用标记指向快照外时记为缺口，不当作已解析。
- 契约逐键回填 `output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构。

## 安装

仅 Python 3.9+ 标准库，离线。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/citation-contract.md
  GITHUB_URL.txt  README.md  SELFTEST.md
```

## 用法

### 单命令（评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

### 五命令

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show        # 打印带 locator 的段落（--grep/--limit）
python3 scripts/main.py check       # 校验 draft 边的 source/target
python3 scripts/main.py build       # 组装网络/路径/缺口并定稿 result.json
python3 scripts/main.py selfcheck   # 复检产物
```

## 产物（写入 `--output`）

`result.json`、`citation_network.json`、`edges.jsonl`、`traced_paths.json`、`gaps.json`、`report.md`。

| 文件 | 内容 |
|-|-|
| result.json | 顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、seed、网络、路径、缺口、limits、uncertainty、change_records |
| citation_network.json | 节点与边 |
| edges.jsonl | 逐条边 |
| traced_paths.json | 种子出发的路径与深度 |
| gaps.json | 元数据缺口与越界引用 |
| report.md | 报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无引用边：`edges/paths` 给带 `status`/`note` 的诚实非空结构。
- 不联网、不查询外部引文库；结论限定在所给快照内。

> 本地评测复现命令与（静态推演的）预期结果见 `SELFTEST.md`。
