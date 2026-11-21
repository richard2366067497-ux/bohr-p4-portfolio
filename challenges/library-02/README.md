# research-file-locator（library-02）

在科研文件库（PDF / Word / Excel / PPT / 扫描件 / 重名副本 / 多版本）上做**章节级定位检索**：
脚本完成切分、编码判定、别名与同义扩展、哈希去重与版本链识别、硬过滤执行与页码映射，并预填
逐 query 候选引文；Agent 只需复核裁决，脚本再逐字校验引文与 locator，产出可独立复核的引文、
页码与操作日志，并把 `output_contract` 十键回填进 `result.json` 顶层与嵌套。

## 快速开始

```bash
python3 -B scripts/main.py all --input /input --out /app/output --work /app/work
```

- 安装位置 `/skills/weekly-skill/`，入口 `scripts/main.py`；单命令 `all` = `init` + `build` + `selfcheck`，恒 exit 0，先写合法 partial `result.json`。
- Agent 增强路径：`init` → `show` →（写 `work/draft.json`）→ `check` → `build` → `selfcheck`。

## 命令

| 命令 | 作用 |
|---|---|
| `all` | 全管道（默认）；无工作稿也产出完整降级结果 |
| `init` | 建索引，生成 `work/draft.candidates.json`（逐 query 预填候选引文/过滤状态） |
| `show` | 打印候选清单与原文片段（`--doc`/`--grep`/`--limit`/`--full`） |
| `check` | 机械门禁：契约键、逐字引文、locator 回链、过滤执行、覆盖完整性 |
| `build` | 由 `work/draft.json` 生成全部交付物与最终 `result.json` |
| `selfcheck` | 复检并生成异常样本（加密/扫描件/损坏/空/legacy/权限/重名副本）自检报告 |
| `fixtures` | 单独运行异常样本自检 |

## 目录与产物

- 输入 `/input`：`case.json`（`case_id`/`materials_root`/`output_contract`/`queries`/`filters`）、可选 `task.md`、`materials/` 库根。
- 输出 `/app/output`：`result.json`、`index.json`、`answers.json`、`hits.jsonl`、`dedupe.json`、`failures.json`、`filters_log.json`、`location_report.md`、`verify_report.json`。
- 工作 `/app/work`：`draft.candidates.json`、`draft.template.json`、`queries.json`、`filters_ledger.json`、`fixtures/`、`fixtures_report.json`、`check_report.json`、`selfcheck_report.json`、`run.log`。

## 依赖与兼容

纯 Python 3 标准库（`zipfile`/`zlib`/`re`/`json`/`hashlib`），不联网、不需 pip、不依赖 CWD。PDF 文本层与 `/PageLabels` 用内置解析器直读，OOXML 走 zip + XML 直读。退出码恒为 0，失败信息写进 `result.json` 的 `errors`/`degradations`。

## 许可

本包为玻尔产品周赛（Bohr P4）参赛作品，以 MIT 许可发布：可自由复制、修改、再分发，保留版权声明即可。题集、目录模板与元数据字段规范（`SKILL.md §4`）可被他人直接复用。
