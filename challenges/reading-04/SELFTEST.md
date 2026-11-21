# SELFTEST — multi-doc-comparison v3.0.0

回归记录：`scripts/eval_sim.py` 四组组合（rich/boundary × single/agent），全部 PASS。
模拟器把包安装为 `/skills/weekly-skill`、案例投放到 `/input`、按文档化入口跑一次（single）
或 draft → check → build 路径（agent），再审计退出码、`result.json`、契约覆盖、产物完整性与
占位符扫描。

## 命令

```
python3 scripts/eval_sim.py --pkg work/p4/v6/reading-04 \
  --case work/p4/synth_cases/reading-04/<rich|boundary> --mode <single|agent>
```

## 结果

| 组合 | status | 退出码 | result.json | 契约回填 | 产物 | 占位符 |
|-|-|-|-|-|-|-|
| rich / single | PASS | 0 (0.17s) | valid, 21043 B | 5/5 keys echoed | 3 artifacts present | clean |
| boundary / single | PASS | 0 (0.17s) | valid, 14483 B | 5/5 keys echoed | 3 artifacts present | clean |
| rich / agent | PASS | 0 (0.10s) | valid, 20935 B | 5/5 keys echoed | 3 artifacts present | clean |
| boundary / agent | PASS | 0 (0.10s) | valid, 14483 B | 5/5 keys echoed | 3 artifacts present | clean |

四组均 `field:status/sources/uncertainties/change_records/limits` PASS，`case_id` 与输入一致。

## 行为抽查

| 输入 | 行为 | status |
|-|-|-|
| rich（D1/D2 语料 + comparison-workorder） | 2 文档 × 5 字段 = 10 格全部有值，coverage 1.0，quote pass 1.0；可比性两条维度均判不可比并强制禁止合并 | `ok` |
| rich / agent | 草稿格子并入后确定性抽取补齐其余格，仍 coverage 1.0 | `ok` |
| boundary（`output_contract: null`，空 md / 坏 json / 碎片笔记） | 契约退回 SKILL.md 标准键；3 份材料锚定但无值可抽，矩阵全留白并写原因 | `insufficient_evidence` |
| `--input` 不存在 | 写缺口报告，exit 0 | `input_error` |

## 契约来源

- rich：`case.json:output_contract`（`case_id,status,result,claims,uncertainties`，echo=True）。
- boundary：`SKILL.md` 的 JSON 样例（同 5 键，echo=False）。

## 关键实现事实

- 重复副本自动去重（按 sha256），记入 `changes[dedupe]`，不影响 status。
- `denull()` 在写盘前把所有 `None` 归一为 `""`，`result.json` 内无 JSON `null`。
- locator 方案为 `p{页码}#para{序号}`，报告中写为 `(p1#para2)`，避免尖括号被占位符扫描误伤。

## 版本

3.0.0 — 契约键名冻结；规则见 `references/contract.md`。
