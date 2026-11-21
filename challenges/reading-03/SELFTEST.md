# SELFTEST — sci-lit-bilingual-audit（reading-03 v10）

**2026-11-21** 实测（Windows + Python 3.12.14；评测器：仓库根 `scripts/eval_sim.py`，本地仿真沙箱，纯标准库）。

## 1 评测结论：4/4 PASS（0 FAIL、0 WARN）

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | **PASS** | case.json:output_contract | 5 键 | 6 |
| rich | agent | **PASS** | case.json:output_contract | 5 键 | 6 |
| boundary | single | **PASS** | SKILL.md (json sample) | 5 键 | 6 |
| boundary | agent | **PASS** | SKILL.md (json sample) | 5 键 | 6 |

契约键均为 `case_id, status, result, claims, uncertainties`。逐项 PASS：`exit_code`、`result_json`、`contract_echo`、
`contract_values`、`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

复现（`$PY` 为 Python 解释器路径）：

```bash
python scripts/eval_sim.py --pkg work/p4/v10/reading-03 --case work/p4/synth_cases/reading-03/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/reading-03 --case work/p4/synth_cases/reading-03/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/reading-03 --case work/p4/synth_cases/reading-03/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/reading-03 --case work/p4/synth_cases/reading-03/boundary --mode agent
```

agent 模式执行 7 步（退出码全 0）：`init` → 写入 SKILL.md 内示例工作稿 → `check` → `build` → `selfcheck` → `compare`
→ `all`（单命令入口排最后，重新装配出完整产物集）。

## 2 单命令入口实跑

`python scripts/main.py all --input <rich> --output <out> --work <work>` → **exit 0**，写出 `result.json` 与全部
5 个附件（`paragraph_pairs.jsonl`、`audit_report.json`、`glossary.json`、`bilingual_review.md`、`run_log.txt`，共 6 产物）。
rich 用例无 `materials/`，故 `status=insufficient_evidence`——仍产出完整契约与全部产物，不崩溃、不非零退出。

## 3 降级路径实测

| 场景（真实构造） | 结果 |
|-|-|
| boundary 用例：空 `empty.md` + 坏 `broken.json` + 极短 `notes.txt` | 退出码 0；`status=insufficient_evidence`；仍产出 **6 个非空、无占位符**的产物，契约键全回显 |
| 输入目录不存在/无可用材料 | 出完整契约与 6 产物，`errors`/`degradations` 记录 |
| 只有占位符的页/空白页 | 整页判不可用并跳过（`placeholder_or_empty_pages_dropped`） |
| `case.json` 损坏 | 字面抢救 `case_id` 与契约键名（`case_json_salvaged`），不编造取值 |
| 工作稿段号与索引对不上 | 按无工作稿处理（`draft_sids_match_zero_segments`），不臆造译文 |

## 4 确定性复现

同输入连跑两次：`paragraph_pairs.jsonl`、`audit_report.json`、`glossary.json`、`bilingual_review.md` **逐字节一致**
（SHA1 相同）；`result.json` 除 `runtime` 与 `change_records[].seconds` 计时字段外逐值一致；`run_log.txt` 只差秒数。

## 5 包内功能用例（`examples/`）

`python scripts/main.py all --input examples --output <out> --work <work>` → 退出码 0、`segments=17`、16 项 check
（pass 11 / fail 2 / warn 1 / skip 2）；`by_type` = body 4、caption_figure 1、caption_table 1、formula 1、heading 5、
reference 2、table_row 3，候选术语 40 条。包内仅内嵌论文节选与其契约，**译文由 Agent 写入 `work/draft.json`**（示例骨架
见 SKILL.md §3）；未写工作稿时该用例 `status=partial`、`translated=0`，属预期降级，非缺陷。

## 6 自检覆盖不到的（诚实声明）

- **语义质量**：通顺度、措辞、译名是否最优——机械核验不判断，只列 `human_review`
- **扫描件 OCR**：无文本层 PDF 一律降级（不内置 OCR，也不假装识别）
- **极端排版**：表格套表格、脚注混排、图文混排的切段需人工确认（记 `warnings`）
- **术语该不该进表**：候选按频次与形态排序给出，是否锁定由人/Agent 决定
