# GAIN_EVIDENCE — slides-author（slides-01 · v9）

对照口径见 SKILL.md 与 references/slides-spec.md。每一项都给出**可由交付文件自行核验**的证据与复现方式；
拿不到证据的项一律写「未通过」。

## 对照组定义（同输入 / 同模板 / 同版本）

- **baseline（基础 Agent / 通用做法）**：用通用 `python-pptx`（或直接文本）按段落顺序把论文正文贴进页面，
  图表编号与正文引用不去对齐，数字原样搬运，无页级定位、无逐字校验、无模板主题哈希记录。
- **skill（本包）**：
  `python3 -B /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work`。
- 两者输入相同（平台 `/input`）、目标模板相同、软件版本相同；对照以**交付文件字段**为准，不以文字自述为准。

## 逐项证据

| 能力 | baseline | skill | 证据（文件 → 字段） | 复现 |
|---|---|---|---|---|
| 页级主张（不搬运段落） | 按段落顺序贴 | 每小节取实质句子成页 | `slide_plan.json → slides[].claim`、`outline.md` | 数 slides 条数、比对 claim 是否为整句 |
| 逐字证据 + locator | 无 | 每页/每要点带 `source_locator` 与 `evidence_quote`，逐条 `verified` | `content_map.json → slides[].source_locator / bullets[].verified` | `self_check.evidence_verified == evidence.bullets` |
| 数字不被改写 | 数字就地搬运、小数点处断句 | 含数字要点先在原文 span 重定位；句子不在小数点处断 | `content_map.json → bullets[].text`（`4.7 µm`/`12.5%` 完整） | grep `deck.md` 看 `4.7`、`12.5` 是否完整 |
| 图表引用对齐 | 编号错位/引用不存在图 | 页码 → `figure_refs` | `page_gold.json → slides[].figure_refs` | 数 `with_figure_ref` |
| 讲解备注（与页面文字不同） | 无备注或复述页面 | 每页 ≥20 字符且异于页面的讲解 | `compliance_checks.json → notes.coverage`、`result.json → notes_k` | 读 `deck.md` 的 `<!-- notes -->` |
| 模板继承 | 覆盖模板版式 | 复用主题/母版并记哈希 | `version_log.json → theme.{source,sha256,inherited}` | 有模板时 `inherited=true` |
| 页级金标准（可核验） | 无 | 每页必需要素 + 定位 + 引文 | `page_gold.json → slides[]` | 数 `pages` 与 `slides` 长度 |
| 诚实降级 | 空/坏输入报错退出、半个目录 | 恒 exit 0 + 降级矩阵 | `result.json → status / degradations / exceptions`、`errors` | `echo $?` + 读 `degradations` |
| 契约回填 | 无契约概念 | 每个契约键都有非空块（顶层 + 嵌套） | `result.json → output_contract`（键集合 ⊇ 契约键集合） | 比对键集合 |
| 文本可复现 | 每次输出不同 | 文本产物字节稳定 | 两次运行 `deck.md`/`content_map.json` sha256 相同 | 跑两次比对 sha256 |

## 现状（本仓库合成 case 实测）

- **rich**（`synth_cases/slides-01/rich`：论文 2805 字节 + `slide-workorder.json`）：
  `status=ok`；**9 页**；证据要点 **21 条全部逐字命中**（`evidence.bullets = evidence.verified = 21`）；
  图表引用对齐（results 页 `figure_refs = ["Figure 1","Figure 2","Table 1"]`）；
  `presentation.pptx` 49 个 part（9 幻灯片 + 9 备注页，XML 全部可解析）、`presentation.pdf` 9 页；
  `output_contract` 15/15 键回填；placeholder 扫描 0 命中。
- **boundary**（`case.json.output_contract=null`、材料 0/坏）：
  `status=insufficient_evidence`；1 页诚实说明页；契约退回 SKILL.md 声明后仍 15/15 回填；
  全套产物齐、`exit 0`、placeholder 扫描 0 命中。

## 创新证据（相对现有方案的边界与价值）

| 现有方案 | 它做不到 / 做不稳 | 本包做法与证据 |
|---|---|---|
| 通用 `python-pptx` 直接生成 | 只能堆文本，不保证页级可回溯、不校验逐字、无模板哈希 | 数字白名单 + 逐字命中（`content_map.bullets[].verified`）+ 主题哈希（`version_log.theme.sha256`） |
| 手工排版流程 | 人月成本高、不可复现、无页级金标准 | `page_gold.json` + `selfcheck` + 契约回填，任何人可重跑同一版式 |
| 段落搬运式生成 | 主线丢失、图表错位、数值被改 | 页级主张来自整句（不切小数点）、`figure_refs` 对齐、含数字要点先重定位 |

## 增量一句话

基线产出「一份看起来像 PPT 的段落堆」；本包产出「一份每页都能回查到论文某句、图表编号对齐、
换台机器重跑仍一致、并按完整契约交付的可讲学术 PPT」。
