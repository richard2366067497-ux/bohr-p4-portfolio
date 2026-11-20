# 方法与产物结构 / Method, schema and runbook

## 目的

把"写作"从自由发挥变成可核对的三段交付：**论断清单 → 证据表 → 成稿**。每一条实质句都应能回答三个问题：依据在哪一段（locator）、依据有多强（strength）、哪里还不确定（uncertainty）。

## 一次运行的步骤

1. **读取**：递归读取输入目录下的文本、表格、JSON 与 Office 文件；坏文件与二进制只登记缺口，不阻断。
2. **切分**：按段落/句子切成带定位的单元；每单元记录 `路径 [Bn.Sm] chars:a-b`。
3. **论断**：若有草稿则逐句取论断；否则按与任务说明的相似度从材料里挑实质句。
4. **匹配**：论断与非本文件的材料单元做词元余弦相似度匹配，取最高 3 条；数字命中加权。
5. **判强**：四因子合成证据强度（见下）。
6. **改写**：强度不足却使用因果措辞的句子，降级为相关性表述并记录。
7. **渲染**：生成带 [n] 标记与限定语的成稿，附证据边界与参考文献。
8. **回填**：`result.json` 逐键回填 `output_contract`，并写五要素与 `limits`。

## 证据强度四因子

| 因子 | 取值 | 说明 |
|---|---|---|
| 研究设计 | 系统综述/元分析 5.0；随机对照 4.5；队列 3.5；病例对照 3.0；横断面 2.5；综述 2.0；病例报告 1.5；体外/动物 1.5；预印本 1.0；未明 1.0 | 越高越接近因果级证据 |
| 样本量 | ≥1000 得 2.0，≥300 得 1.5，≥100 得 1.0，≥30 得 0.5，否则 0 | 从正文 `n=…` 或"XX 例/受试者"读取 |
| 独立来源数 | 每多一个独立来源 +0.6，封顶 +1.2 | 单来源不给共识加分 |
| 冲突惩罚 | 有方向相反的证据 −1.5 | 冲突保留，不合并 |

合成分数 `score = 设计×1.05 + 样本量分 + 来源加分 − 冲突惩罚`：

- `score ≥ 5.5` → 高
- `3.5 ≤ score < 5.5` → 中
- `1.5 ≤ score < 3.5` → 低
- `score < 1.5` → 不足

成稿措辞与等级对应：高→"多项证据一致表明"，中→"现有研究提示"，低→"初步证据提示"，不足→"材料尚不足以判断"。

## 过度推断改写

- `causes / caused / leads to / results in` → `is associated with`
- `导致 / 造成 / 引起` → `与…相关`
- `proves / 证明 / 证实` → `supports / 提示`

只改写措辞，不改变被引用的数字与结论方向；每次改写记入 `change_log`。

## 产物结构 / Evidence artifact schema

本包定义 `claims.json`、`evidence_table.json`、`result.json` 的字段约定。字段名稳定，便于他人独立回查与重跑。默认契约键（`case.json` 未给 `output_contract` 时回落到此，取自下方 JSON 样例的 `output_contract`）：

```
{
  "case_id": "case-000",
  "status": "success",
  "deliverable": "evidence_driven_draft.md",
  "preserved_facts": [{"value": "42", "unit": "%", "span": "42%"}],
  "evidence_map": [{"claim_id": "C001", "source_id": "D01", "locator": "materials/refs.txt [B0.S2] chars:0-80", "strength": "中"}],
  "change_log": [{"action": "assembled the draft from located material", "target": "evidence_driven_draft.md"}],
  "output_contract": {
    "case_id": "case-000",
    "deliverable": "evidence_driven_draft.md",
    "preserved_facts": [{"value": "42", "unit": "%", "span": "42%"}],
    "evidence_map": [{"claim_id": "C001", "source_id": "D01", "locator": "materials/refs.txt [B0.S2] chars:0-80", "strength": "中"}],
    "change_log": [{"action": "assembled the draft", "target": "evidence_driven_draft.md"}]
  }
}
```

### claims.json

| 字段 | 含义 |
|---|---|
| `case_id` | 输入案例标识（透传） |
| `language` | 成稿语言 `zh` / `en` |
| `mode` | `revise`（有草稿）或 `compose`（按题目组稿） |
| `count` | 论断条数 |
| `claims[]` | 论断数组 |
| `claims[].claim_id` | 论断编号，`C001` 起 |
| `claims[].text` | 论断原文 |
| `claims[].render` | 成稿中使用的版本（已做过度推断改写） |
| `claims[].type` | `causal` / `descriptive` |
| `claims[].location` | `draft:` 或 `compose:` 加材料定位 |

### evidence_table.json

| 字段 | 含义 |
|---|---|
| `schema` | 字段顺序说明 |
| `rows[].claim_id` | 对应论断 |
| `rows[].source_id` | 来源文件 ID（`D01`…），空串表示未匹配 |
| `rows[].locator` | `路径 [Bn.Sm] chars:a-b` |
| `rows[].quote` | 来源原文片段（逐字，取自材料） |
| `rows[].strength` | `高` / `中` / `低` / `不足` |
| `rows[].support_scope` | 该来源的研究设计类别 |
| `rows[].conflicts` | 与论断方向相左的同组来源定位 |
| `rows[].rationale` | 强度计算的文字依据 |
| `rows[].verified` | 引文是否在来源内逐字命中 |

### result.json（顶层）

`case_id`、`status`、`skill`、`skill_version`、`language`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`output_contract`、`outputs`、`metrics`、`sources`、`uncertainties`、`change_records`、`limits`、`human_review`、`degradations`、`errors`、`runtime`。

- `status` ∈ `success` / `partial` / `failed`。
- `output_contract`：逐键回填输入契约；契约给值的键保留其语义，给空值或仅给描述的键回填为真实值或真实文件。
- 五要素 `preserved_facts`、`evidence_map`、`change_log`、`uncertainties`、`limits` 恒为非空，保证即使降级也可复核。

## 运行与自查

```text
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

自查：`verification.json` 给出论断数、来源数、引文逐字命中数；`reference_check.md` 给出著录完整度。任何一步失败都会写出带 `limits` 的降级 `result.json`，退出码恒为 0。

## 适用范围与限制

- 适用：需要证据可回溯的学术写作、改稿、引用与不确定性表达。
- 限制：离线，不联网核验文献真实性；PDF 正文需外部解析器；不做单位换算；强度为启发式分级，最终以人工复核为准。
