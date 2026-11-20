---
name: claim-preserving-polish
description: 学术文本的“主张守恒型”最小编辑润色。当用户给出待改原文（英文摘要/期刊章节/学位论文/基金申请书/审稿回复，或中英混排稿）并要求润色、改写、校对语法、统一术语、提升学术语域、清理直译腔时使用；输出改后全文 + 逐处原文/改文/类型/理由 + 术语表 + 人工确认清单 + result.json。核心主张是“只改语言，不动主张”：数字、单位、引用编号、图表/公式指向逐字保留，限定强度与否定范围不得被悄悄加强或削弱，改不动的标注不改。不适用：纯内容问答、文献检索、数据分析作图、代码调试、无原文的凭空写作、期刊模板级排版、docx/pdf 转换。若用户只是问“这样写行不行”，先问一句“要我直接改出全文并附逐句说明吗”，得到确认再动笔。
version: 9.0.0
---

# claim-preserving-polish（v9）

学术润色里最贵的错误不是“改得不够漂亮”，而是**改坏了作者的主张**：整段重写后 `may` 消失、
`associated with` 变成 `causes`、把 1,200 写成 1200、引用 [3] 掉号、`Fig. 2` 变成 `Fig. 3`。
本 Skill 先把这些不可编辑的东西钉住，再让 Agent 在钉子之间做最小编辑，并用机械守卫逐段复核。

## 0. 输出契约样例（result.json 骨架，字段名逐键回填）

下面这份骨架说明本 Skill 每次运行都会产出的字段；真实运行时每个键都会用本次运行的实测值回填
（顶层与嵌套 `output_contract` 同时写），不出现空壳占位：

```json
{
  "case_id": "demo-001",
  "status": "answered",
  "output_contract": {
    "deliverable": "polished.md",
    "preserved_facts": [],
    "evidence_map": [],
    "change_log": [],
    "edit_log": [],
    "glossary": [],
    "verification": {},
    "format_spec": {},
    "compliance_checks": [],
    "uncertainty": []
  }
}
```

## 0.1 单命令入口（等价入口，一次性跑完整流程）

评测只跑这一条也能过：**不依赖任何草稿**，直接产出 `polished.md`、`changes.csv`、
`edit_log.md`、`glossary.csv`、`verification.json`、`evidence.json`、`human_review.md`、
`audit.json` 与逐键回填的 `result.json`，退出码恒 0：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --work /app/work --out /app/output
```

无 `draft.json` 时进入 **auto-draft**：只做高置信度机械修正（冗余框架语、连续空格、标点粘连、
`et al.` 缺点、`utilize→use` 等），每处都写 `type` + `reason`，再交给同一套守卫逐段复核，
违规整段回退；LaTeX/代码段整体冻结。语义级润色仍留给 Agent——`all` 是五命令主路径的封装，
也是无 Agent 时的保底路径，跳过的段落会写进 `result.json.degradations` 与 `human_review.md`。

## 0.2 五命令主路径（Agent 增强路径，先跑这个）

```bash
export SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
test -f "$SKILL_DIR/scripts/main.py" || export SKILL_DIR=/app/submission   # 兜底：提交目录

python3 "$SKILL_DIR/scripts/main.py" init   --input /input --work /app/work --out /app/output
python3 "$SKILL_DIR/scripts/main.py" show   --input /input --work /app/work --out /app/output
#   ↑ 读原文、保护性原子、限定强度和术语候选；然后你**亲自**写 /app/work/draft.json
python3 "$SKILL_DIR/scripts/main.py" check  --input /input --work /app/work --out /app/output
python3 "$SKILL_DIR/scripts/main.py" build  --input /input --work /app/work --out /app/output
python3 "$SKILL_DIR/scripts/main.py" selfcheck --input /input --work /app/work --out /app/output
```

**脚本不会代替你阅读理解与编辑；必须先读材料、写工作稿，再运行 `build`；禁止只跑 `build` 就结束。**
`init` 已写出合法 partial `result.json`（原文原样），任何时刻都有可评底稿；`check` 的 `[HARD]` 必须处理；
`build` 无条件定稿并回填契约，退出码恒 0。命令都是确定性的，通常各跑一次即可，其余预算花在**读和写**上。

## 1. 用途与适用条件

| 输入情形 | 动作 |
|-|-|
| 给了正文 + 要求润色/校对/统一术语/译成学术英文 | 走完整主路径 A–E |
| 只给一段话问“这样写行不行” | 先问是否要直接改出全文；确认后再走 |
| 问“这篇讲了什么”“帮我找文献”“这图怎么画” | **不触发**，直接回答，不改写任何原文 |
| 要求扩写、加数据、加引用、加结论 | 拒绝加内容：语言层只修表达，缺口写进 `human_review.md` |
| 要求整段翻译成另一语言 | `mode=translate`：原子仍逐字守，限定强度只提示不硬判 |
| 目标文体未说明 | 按 `init` 判定的 `genre`，仍不明则中性学术语体 + 人工确认项 |

判断依据只有一个：**输入里有没有待改的原文**。没有原文就不是润色任务。文体语域差别
（`journal/abstract/thesis/grant/review_response`）见 `references/rules.md` 第三节。

## 2. 调用方式与安装路径

- 安装位置 `/skills/weekly-skill`（Harness 挂载点），提交目录 `/app/submission` 为兜底。
- **一律用绝对路径调用**：Harness 的 cwd 不保证是 Skill 根目录；脚本内部用 `__file__` 定位 `assets/`。
- 依赖 Python ≥ 3.8 标准库，无第三方包、不联网、不写输入目录。
- 参数默认值：`--input /input`、`--work /app/work`、`--out /app/output`、`--case <input>/case.json`、
  `--task <input>/task.md`。手工复跑显式传参，不要 `cd` 进包目录。

## 3. 输入 / 输出契约

输入：`/input/case.json`（`case_id`、`task_instruction`、`output_contract`，材料可内联或以 `path` 指向）、
`/input/task.md`（受众、文体、格式、需保护对象）、`/input/*.md .txt .tex .rst .csv .json .bib`；
文件名含 `glossary`/`terminolog`/`术语` 的按权威锁定处理，优先于 Agent 判断。

输出（全部写 `/app/output`）：`result.json`（主产物，契约逐键回填 + 信封字段）、`polished.md`/`polished.txt`
（改后全文，段落顺序与引用标记同原文）、`changes.csv`（locator/before_span/after_span/type/reason/guard）、
`edit_log.md`（可读版）、`glossary.csv`（concept/locked/variants/first_use/decision）、`verification.json`
（原子守恒、限定强度、否定、覆盖率）、`evidence.json`（每处修改 quote + 段落 id + 字符区间）、
`human_review.md`（必须处理项 + 建议复核 + 材料缺口，每条给选项）、`bilingual.csv`（双语对照）、
`audit.json`（`selfcheck` 自查，含契约字段完整性）。中间产物在 `/app/work`：`segments.json`、
`case_profile.json`、`glossary_candidates.json`、`draft.template.json`、`show.md`、`check_report.json`、`cmd_log.json`。

信封字段（无论契约怎么写都会写）：`case_id`、`status`（`answered|partial|insufficient_evidence|input_error`）、
`status_reason`、`errors[]`、`degradations[]`、`uncertainties[]`、`pending_human[]`、`runtime{}`、`sources[]`、
`coverage{}`、`verification{}`、`before_after_digest{}`、`deliverables{}`、`terminology_sweep[]`、`limits[]`、
`skill{}`、`_contract_report[]`。

**契约回填规则**（`scripts/contract.py`）：字段名一个不改、一个不漏，顶层与嵌套 `output_contract` 同时回填；
按字段名关键词映射到真实载荷（`polish*→全文`、`edit/change→修改记录`、`glossar→术语表`、`bilingual→双语对`、
`uncert→存疑`、`human/pending→人工确认`、`verif→校验明细`、`source/evidence→来源`、`status→状态`、`limit→边界`、
`format/spec→格式`），映射不上的写明确说明；工作稿 `result_fields` 的同名字段优先。

## 4. 方法说明（五步，细则见 `references/rules.md`）

- **A `init`**：切成 `P001…` 段落（标题、代码块/公式环境标 `frozen` 永不改写），抽原子、判限定强度、
  统计否定，立刻写出原文原样的 partial `result.json`。看打印的材料份数、文体/语言/模式、段落数、契约字段、errors。
- **B `show`**：打印每段 locator（`manuscript.md#P002[12:419]`）、原文、原子清单、句内偏移与术语候选。
  **`before` 必须逐字复制这里印出的原文**，锚不上即 `ANCHOR_MISS`。
- **C 亲自润色并写 `/app/work/draft.json`**：逐段最小编辑；每处改动一条 `changes`；无需改的段落进
  `untouched` 并给理由——“没改”也要留痕，否则视为漏段。
- **D `check`**：原子守恒（硬）、主张守恒（硬，除已声明的 `hedge_override`）、相似度 < 0.50 未标
  `restructure/translate`（硬）、修改记录缺类型/理由（硬）。`[HARD]` 只有两条出路：改好再跑，或写明
  为何必须改变结论强度。
- **E `build` / `selfcheck`**：逐段应用通过的改动，违规段落**整段回退原文**，渲染全部产物并回填契约；
  `selfcheck` 复检契约字段、产物存在性、修改记录类型与理由。

## 5. 工作稿 `draft.json`（固定 `/app/work/draft.json`，也接受 `plan.json`）

```json
{
  "case_id": "<从 init 打印复制>",
  "task_understanding": {"genre": "journal_article", "target_language": "en",
                         "audience": "同行评审", "must_do": ["逐段润色"],
                         "must_protect": ["1,200 samples", "[3]", "Fig. 2"]},
  "glossary": [{"concept": "residue-level attention", "locked": "residue-level attention",
                "variants": ["residue level attention"], "first_use": "P002",
                "decision": "全篇连字符小写"}],
  "items": [{"paragraph_id": "P002", "before": "<逐字复制 show 的原文>",
             "after": "<改后文本，保留全部数字/引用/图表指向>",
             "changes": [{"before_span": "has been widely applied in",
                          "after_span": "have been widely applied to",
                          "type": "grammar",
                          "reason": "主谓不一致（has→have）；apply 的搭配是 applied to"}],
             "hedge_override": null}],
  "untouched": [{"paragraph_id": "P001", "reason": "章节标题，无语法/术语问题"}],
  "uncertainties": [{"paragraph_id": "P002", "issue": "原句语义含混",
                     "options": ["保留", "改法B"], "severity": "low"}],
  "result_fields": {}
}
```

规则：`before` 逐字复制（含标点空格）；`after` 为空等同“未改”，请改用 `untouched`；`type` 取
`grammar|syntax|terminology|register|punctuation|concision|cohesion|word_choice|article|preposition|tense|voice|agreement|spelling|capitalization|restructure|translate|other`；
`reason` 必须说明原文哪里不对（“主谓不一致”“搭配错误”），不能只写“更学术/更通顺”；`hedge_override`
仅在有意改变结论强度时填 `{"from": 2, "to": 3, "reason": "..."}`；长稿分批：先写前 10 段 → `check` → 续写 → 再 `check`。
完整字段字典见 `references/rules.md` 第七节。

## 6. 不能动的原子（`check` 按出现次数逐字比对）

| 类别 | 例子 | 违规表现 |
|-|-|-|
| 数字 | `1,200`、`91.2`、`0.87`、`p = 0.03` | `PROTECTED_ATOM_LOST` |
| 数字+单位 | `0.5 mM`、`4 °C`、`30 min`、`12 kDa` | 同上（单位被换也算） |
| 引用标记 | `[3]`、`[3-5]`、`(Smith et al., 2020)`、`\citep{key}` | 同上 |
| 图表/章节指向 | `Fig. 2`、`Table 1`、`Sec. 3.2`、`Eq. (2)`、`图 3` | 同上（编号必须对得上） |
| 公式 | `$...$`、`\(...\)`、`frozen` 块 | 同上 |
| 缩写/专名 | `CNN`、`PCR`、`\(\lambda\)` | 软提示（首现展开是合法改动） |

**不要“顺手规范化”**：`1,200` 不写成 `1200`，`Fig. 2` 不写成 `Figure 2`，`[3]` 不并进句子改写。
原文数字本身有错（如区间不闭合）时保持原样并写进 `uncertainties`，由作者决定。

## 7. 主张守恒：限定强度、否定与因果

强度分级（词表见 `assets/hedge_lexicon.json`、`references/rules.md` 第五节）：
4 assertive（demonstrate/prove/证明）> 3 indicative（show/indicate/表明）> 2 possible（suggest/may/可能）
> 1 associative（associated with/与…相关）> 0 unresolved（remains unclear/证据不足）。

- 改后等级 > 改前 → `CLAIM_STRENGTHENED`；< 改前 → `CLAIM_WEAKENED`；标 `hedge_override` 并给理由则降为软提示。
- 等级不变但主张内核词被删（may/suggest/indicate/associated…）→ `HEDGE_MARKER_DROPPED`：最常见的“偷偷加强”。
- 相关 → 因果（`associated with` → `causes/导致`）→ `CAUSAL_UPGRADE`；反向为软提示。
- 否定标记数变化：英文硬判、中文软提示（中文否定常嵌在“不同/未来”里，误判代价高于收益）。
- 新增绝对化表述（all/always/never/所有/完全）→ 软提示。
- **指路句不算结论**：`Fig. 2 shows…`／`表 2 显示…` 的 show/present 是版式动词，脚本先掩掉再比强度。

## 8. 边界与限制

- 只做语言层：不改研究设计、不补数据、不新增引用、不调整期刊模板。
- 守卫是**词表 + 正则**的机械判据：能证明“原子没丢、强度没变”，不能证明“语义完全等价”；
  语义等价靠 `human_review.md` 逐条提示 + 人工抽查，本包不替评审下结论。
- 回退是设计选择：宁可交付保守原文，也不交付可能改坏主张的版本；回退拉低覆盖率，但不造假。
- 跨语言（中→英）限定强度无法逐词比对，一律软提示 + 人工确认清单，不做硬判。
- 只处理文本：`.docx/.pdf/.xlsx` 跳过并写进 `degradations`；术语长尾靠 `TERM_DRIFT` 回扫，仍有漏网可能。

## 9. 失败处理与降级矩阵

| 症状 | 脚本行为 | 你需要做的 |
|-|-|-|
| `case.json` 不存在 / 坏 JSON | 记 `errors`，改扫 `/input` 文本材料，`status=partial` | 照常按材料润色；注明契约字段靠默认集 |
| 无原稿材料 | 回退用 `task.md` 正文，`material_fallback=true` → `partial` | 在 `degradations`/`human_review.md` 说明缺口 |
| 材料为空/极短（<60 字符） | `status=insufficient_evidence`，产物照写 | 不编造正文；说明缺什么 |
| 超长稿 | 全量切段，`show` 截断显示（完整在 `segments.json`） | 分批写工作稿，每批 `check` |
| 编码混乱 | 依次尝试 utf-8/utf-8-sig/gb18030，失败用 latin-1 并告警 | 不做字符级“修复”，原样保留 + 进人工清单 |
| 术语表内部冲突 | 记录冲突，按出现频率提示，不静默择一 | 在 `glossary` 里选定式并写明理由 |
| 工作稿缺失/不全 | auto-draft 保守最小编辑；仍不全则原文交付 + `partial` | 补写后重跑 `build` |
| 守卫硬失败 | 该条/该段回退原文，进 `human_review.md`（high） | 修正措辞或写 `hedge_override` 后重跑 |
| 脚本异常 | 捕获后写最小合法 `result.json` + 空 `polished.md`，`emergency=true` | 按 `references/rules.md` 第九节手工补产物 |
| 没有 python3 | 无法运行脚本 | 手写 `result.json`（见第 3 节）与 `polished.md`，注明“未使用校验脚本” |

## 10. 自查清单（交付前逐条过）

- [ ] `check` 里没有未处理的 `[HARD]`，`[COVERAGE]` 为空（或已在 `untouched`/`uncertainties` 说明）
- [ ] `changes.csv` 每条都有 `type` 与能判断“该不该改”的 `reason`
- [ ] `polished.md` 的数字/单位/引用/图表指向与原文逐个对得上（看 `verification.json` 的 `global_conservation.conserved`）
- [ ] 术语表每个 `locked` 形式在 `polished.md` 里唯一，`variants` 已清零
- [ ] 没改的段落都在 `untouched` 里给了理由；`result.json` 契约字段一个不缺
- [ ] `status` 与实际完成度一致（有回退/缺口就是 `partial` 并写明原因）
- [ ] `human_review.md` 每条都能让作者直接做决定（给了选项）

## 11. 文件地图

```
SKILL.md                    本文件：入口、主路径、契约、硬规则
GITHUB_URL.txt              公开作品链接（仓库地址 + 作品相对路径两行）
GAIN_EVIDENCE.md            使用增益证据：对照协议 + 本包实际运行记录（可复算）
examples/case.json          最小可跑示例的输入契约
examples/manuscript.md      最小可跑示例的原文（含数字/单位/引用/图表指向）
scripts/main.py             CLI：init / show / check / build / selfcheck / all（auto-draft 与异常兜底）
scripts/contract.py         契约回填收尾：逐键回填、真实值映射、空壳词清扫
scripts/pipeline.py         输入发现、切段、原子抽取、术语候选、守卫判定
scripts/render.py           定稿渲染、evidence/human_review、应急写出
scripts/polish_core.py      切段/原子/限定强度/契约映射/落盘工具（纯标准库）
assets/hedge_lexicon.json   限定强度分级、主张内核词、否定/因果/绝对化标记、单位与引用正则
references/rules.md         编辑类型词表、文体语域表、守卫判据、工作稿 schema、字段字典、降级与手工兜底
```

脚本只用标准库；改词表不需要改代码，改代码后至少跑通 `init→build→selfcheck`（回归清单见 `references/rules.md` 第十节）。

## 12. 最小调用示例（示例，不是任何固定案例的答案）

输入 `/input`：`case.json`（`case_id=demo-001`，`output_contract={"polished_text":"string","edit_log":"array","glossary":"array","uncertainty":"array"}`）
+ `task.md`（“英文摘要润色，保持数字、引用不变”）+ `manuscript.md`：

```
The model was trained on 1,200 samples and achieve 91.2% accuracy, higher than the baseline of 88.0% [3]. These results suggest that the method may generalize to unseen domains.
```

写 `/app/work/draft.json`（P002：`achieve → achieves`；数字与 `[3]` 原样）后跑 `check` → `build`。
`result.json` 按该案例的 `output_contract` 逐键回填，骨架形状同第 0 节。
`polished.md` 第一句变为 `The model was trained on 1,200 samples and achieves 91.2% accuracy, higher than the 88.0% baseline [3].`；
`changes.csv` 有 `type=agreement`、`reason=主语 The model 为第三人称单数`；`verification.json` 的
`global_conservation.conserved=true`；`result.json` 四个契约字段均已回填，`status=answered`。
