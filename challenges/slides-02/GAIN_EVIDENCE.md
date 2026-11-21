# GAIN_EVIDENCE — slides-author（slides-02）

本文件记录本包相对「不加 Skill 的基础做法」的对照证据。两组的**输入、案例与评分脚本完全相同**
（`scripts/eval_sim.py`，rich / boundary × single / agent），因此差异可归因于本包本身。

## 1. 对照设置

| 项目 | 基础做法（无 Skill） | 本包（加载 Skill） |
|-|-|-|
| 调用 | 手工分步：读论文 → 写大纲 → 排版 → 导出 → 目视自检 | 一条命令 `all`（评测与人工同一条） |
| 页级证据 | 人工摘抄，定位容易漏 | 每页自动带材料 locator 并写入 `content_map.json` |
| 数字核对 | 人工回查 | 数字类要点先回原文 span 重新定位，找不到的数字不上页 |
| 导出与自检 | 人工导出 + 逐页目视 | 同一页计划导出 pptx / pdf / svg，并写 `compliance_checks.json` |
| 失败处理 | 中途报错即停 | 任何异常 `exit 0` 并写出诚实的结果文件 |

## 2. 可复现的使用增益

1. **调用次数**：单个案例上基础做法需要 5 个以上人工动作（读、写、排、导、查）；本包为 1 条命令。
2. **返工定位**：每条要点保留来源定位，返工时按页回查，而不是通读全文。
3. **交付完整性**：无 `work/draft.json` 时仍产出全套交付物与完整契约（实测见 `SELFTEST.md`）。
4. **可复跑**：同一输入重复运行结果一致（无网络、无时钟依赖的分支均固定）。

## 3. 创新证据

- **页级证据映射**：每页 `source` 定位 + `content_map.json`，页面内容可在原文中逐条复核；
- **数字白名单**：含数字的要点先回源定位再上页，来源中找不到的数字不打印；
- **模板继承**：复用目标模板的主题 / 母版并记录主题哈希，不覆盖母版；
- **自检与诚实降级**：`compliance_checks.json` 逐项留痕；空 / 坏输入记 `insufficient_evidence` 而非抛错。

## 4. 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-02 --case work/p4/synth_cases/slides-02/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-02 --case work/p4/synth_cases/slides-02/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-02 --case work/p4/synth_cases/slides-02/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-02 --case work/p4/synth_cases/slides-02/boundary --mode agent
```

实测结果与逐项检查见同目录 `SELFTEST.md`；结论以 eval_sim 报告的顶层 `status` 为准。
