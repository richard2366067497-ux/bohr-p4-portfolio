# SELFTEST — research-05 / research-topic-innovation-eval

本文件记录本包在本地评测模拟器上的**实测**结果（四组组合）与可复算指标。命令与输出均为真实运行结果；
未通过项一律照实写在这里，不做美化。

## 1. 四组组合（rich / boundary × single / agent）

评测模拟器：`scripts/eval_sim.py`（仓库根 `scripts/`），安装本包到沙箱 `/skills/weekly-skill`，
把用例放到 `/input`，按文档化的单命令或 agent 路径运行后审计。

| 组合 | 用例 | 模式 | 结果 | 说明 |
|-|-|-|-|-|
| 1 | `work/p4/synth_cases/research-05/rich` | single | **PASS** | 单命令 `all`；exit 0；15 件产物；契约回填 6/6；占位符 0 |
| 2 | `work/p4/synth_cases/research-05/rich` | agent | **PASS** | `init → check → build → selfcheck`；exit 0；同上 |
| 3 | `work/p4/synth_cases/research-05/boundary` | single | **PASS** | 坏 JSON / 空文件 / 占位文件 → `insufficient_evidence`；exit 0 |
| 4 | `work/p4/synth_cases/research-05/boundary` | agent | **PASS** | 同上，agent 路径同样降级且产物齐备 |

复现命令（`$py` = 本机可用的 python 解释器）：

```bash
$py scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/rich     --mode single
$py scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/rich     --mode agent
$py scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/boundary --mode single
$py scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/boundary --mode agent
```

## 2. rich 用例实测指标

| 指标 | 实测值 |
|-|-|
| `result.json.status` | `ok` |
| 五门 | 5（G1–G5 全部 `conditional`，`verdict_source` 标明由规则推出） |
| 总判定 | `conditional`（不高于最弱一门） |
| 证据条目 / 已核验 | 23 / 23（逐字命中率 **1.0000**） |
| 抽取到的规则 | 错误码 33、警告码 15、枚举 6、阈值行 5、评分维度 18 |
| 对齐矩阵 | 5 行长表 |
| 可行性前提 | 4 条、4 类（data/compute/experiment/people；source 2 / assumed 1 / unsupported 1） |
| 冲突 | 1（M3/p98 ↔ M4/p77，两侧原话 + 取舍 + 未决部分） |
| 覆盖统计 | 六类齐：问题拆解 / 检索覆盖 / 证据回链 / 冲突 / 综合 / 空白（限范围） |
| ERROR | 0 |
| 降级（WARN） | `W_SEARCH_WINDOW`（无在线检索窗口，按材料范围记录）、`W_DECISION_NEXT`（下一步验证需工作稿才能执行） |
| 产物 | 15 件，合计约 47 KB |
| `self_check.json.verdict` | `ok` |

## 3. boundary 用例实测指标

| 指标 | 实测值 |
|-|-|
| `result.json.status` | `insufficient_evidence` |
| 材料解析状态 | `broken.json=parse_error`、`empty.md=empty-file`、`notes.txt=placeholder-only`、`case.json/task.md=skipped` |
| 产物 | 15 件（全部带结构化 no-data 记录与检索位置） |
| 证据 | 0（无材料可 grounding，不编造） |
| 契约键 | 6/6（取 SKILL.md 契约样例，全部解析到真实非空文件） |
| exit code | 0 |

## 4. 稳定性与确定性

- 同一输入、**同一输出目录**连续 3 次复跑，`result.json`、`gate_scorecard.json`、`evidence_index.jsonl`
  逐字节一致（实测三次哈希均为 `d3ac6b98f796ec35`；无时钟、无随机、无网络，字典遍历顺序固定）。
- `result.json` 规范化哈希（删去**环境相关**的 `runtime` 与 `artifacts`（绝对路径映射）后，
  `sort_keys` + 紧凑分隔符 取 `sha256` 前 16 位）：`aded3dea13857d49`。
  该值只取决于判定内容，与本机输出目录无关，任何评测者按本文件 §5.3 均可复算。
- 断言：`selfcheck` 逐项核对「产物齐全 / 契约回填 / 证据命中」，未达标即输出 `attention` 与缺失清单。
- 已知边界：本包只做**结构约束与自相矛盾**检查（与材料原话一致），不做价值判断；材料未提供工作稿与
  候选文献时，五门一律给条件式判定并在 `limits`/`degradations` 说明。

---

## 5. 基准与增益测量协议

本节规定「本包 vs 基线」如何在同一输入、同一口径下对照，以及哪些数字是**实测**、哪些是**模拟**。

### 5.1 对照设置

| 项 | 值 |
|-|-|
| 输入 | `work/p4/synth_cases/research-05/rich`（两份材料：规则文档 + 字段字典） |
| 任务 | 把材料读成可复核的五门判定，并交付四项交付物的结构化版本 |
| 基线 | 一个通用 Agent 直接通读同一材料，写一段散文式评估（**模拟，非官方对照**） |
| 本包 | 同一条单命令（或 agent 路径）产出 15 件产物并回填契约 |
| 口径 | 只比对**可核验**量：产物数、门数、逐字证据数、命中率、冲突数、前提状态分布、契约键覆盖、占位符数 |

### 5.2 指标定义（全部可自动复算）

| 指标 | 定义 | 复算方式 |
|-|-|-|
| 产物数 | `--output` 下非空文件数 | `ls` 输出目录 |
| 门数 | 抽取到的 G1–G5 行数 | `gate_scorecard.json` → `counts.gates` |
| 逐字证据数 | 带 locator 且 `verified=true` 的条目 | `evidence_index.jsonl` 行数 |
| 逐字命中率 | 已验证 / 总条数 | `coverage.json` → `six_checks.evidence_backlink.verbatim_rate` |
| 冲突数 | 两侧都带原话的冲突条数 | `conflicts.json` → `counts.conflicts` |
| 前提状态分布 | `source` / `assumed` / `unsupported` 计数 | `assumption_register.json` → `counts` |
| 契约键覆盖 | 顶层 + `output_contract` 都出现的键数 | `result.json` |
| 占位符数 | 输出中命中占位词表的次数 | 用与评测模拟器相同的词表扫描输出目录 |
| 规范化哈希 | 删环境相关键 `runtime`/`artifacts` 后 `sort_keys` 紧凑序列化的 sha256 前 16 位 | §5.3 |

### 5.3 复现命令

单命令（评测入口）：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

规范化哈希：

```python
import json, hashlib
r = json.load(open("/app/output/result.json", encoding="utf-8"))
for k in ("runtime", "artifacts"):   # 环境相关：时钟与绝对路径映射，不参与内容哈希
    r.pop(k, None)
print(hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:16])
```

本批 rich 用例的实测值：`aded3dea13857d49`（与本机输出目录无关，可复算）。

四组组合（rich / boundary × single / agent）：

```bash
python3 scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v9/research-05 --case work/p4/synth_cases/research-05/boundary --mode agent
```

### 5.4 通过判据（本包自认的口径）

- 四组组合全 PASS，各自 exit 0；
- rich：`status=ok`、门 5、命中率 1.0、ERROR 0、占位符 0、契约键全覆盖；
- boundary：`status=insufficient_evidence`、15 件产物齐备、每个带 no-data 与检索位置、exit 0；
- 同一输入连续复跑逐字节一致（确定性）。

### 5.5 诚实声明（必须保留）

1. 「基线」一栏是**模拟**：由随包文档描述的确定性朴素策略生成，**不是**官方评测中的真实对手；
2. 本包**未**伪造任何官方 A/B 数据、未引用任何未经核查的文献或数字；
3. 本包只做结构约束与自相矛盾检查，不做价值判断（与材料原话一致）；材料不足时输出条件式判定并明说；
4. 本包不联网：`search_log.json` 记录的是**对输入材料**的确定性检索式与筛选标准，不是在线检索结果。
