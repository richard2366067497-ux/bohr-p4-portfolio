# 最小调用示例（示例，不是任何固定案例的答案）

本文件给一组"输入 → 调用 → 期望产物"的最小闭环，用来核对接口与完整使用流程；数值与结论均为构造示例。

## 1. 输入 `/input`

`case.json`：

```json
{
  "case_id": "demo-016",
  "task_instruction": "把结果段改写成面向产业合作方的 600 字简报，数字与图表引用必须逐字保留",
  "output_contract": {"dropped": "array", "retained": "array", "errors": "object"}
}
```

`materials/result.md`（节选）：

```
在 350 °C、30 min 条件下，比表面积达 142 m2/g，较基线 88.0% 的转化率提升到 91.2%（图 2，样本 n = 1,200）。
该关联在体外实验中成立，尚不能外推到临床。
```

## 2. 调用

```bash
python3 scripts/main.py all --input /input --work /app/work --output /app/output
```

Agent 增强路径：先 `init` 看候选必保留项与契约，再 `show` 逐字取原文，写 `/app/work/draft.json`，
然后 `check` → `build` → `selfcheck`。

## 3. 期望产物

| 文件 | 内容要点 |
|---|---|
| `deliverable.md` | 目标受众成稿：受众/体裁/篇幅写在第一节，正文按体裁骨架展开 |
| `retained_facts.json` | 必保留项逐条：`value` / `locator` / `quote` / 是否落进正文 |
| `diff_map.md` | 逐段对照（源文位置 → 成稿段落）、必保留项落点、删除与压缩理由、逐处修改 |
| `glossary.csv` | 术语/缩写 → 展开与统一用法，带源文 locator |
| `result.json` | 契约逐键回填（顶层 + `output_contract`）+ `fidelity_summary` 可复算指标 + 降级与人工确认项 |

`result.json` 关键片段（骨架示例）：

```json
{
  "case_id": "demo-016",
  "status": "ok",
  "output_contract": {"dropped": [], "retained": [], "errors": {"count": 0, "items": [], "note": "本次运行无阻塞错误"}}
}
```

期望自检：`selfcheck` 报「quote 全部逐字命中」「数值漂移为 0」「契约键齐全且同名」；`350 °C`、`30 min`、
`142 m2/g`、`91.2%`、`88.0%`、`1,200`、`图 2` 在成稿中逐字保留，`尚不能外推到临床` 这类限定不被加强。

## 4. 兜底行为（无工作稿时）

直接跑 `all` 时若 `/app/work/draft.json` 缺失，`build` 走**逐字抽取兜底稿**：产出全部五个文件、
`status=partial`、稿首标注「未完成受众改写」、`degradations` 记明原因，退出码仍为 0。
补齐 `draft.json` 后重跑 `check → build` 即可替换为真正的受众改写稿。
