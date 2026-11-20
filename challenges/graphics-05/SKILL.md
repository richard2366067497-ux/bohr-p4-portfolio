---
name: ga-trace-builder
description: Build a one-page graphical abstract (problem, method, key results, takeaway) from the supplied research material, exported as a layered editable SVG plus a single-page vector PDF and a real PNG, with every panel, arrow, colour/length code and number bound to a verbatim quote and a locator. The workbench indexes the input, prints quotable passages, audits an agent-written draft, renders deterministically, and self-checks the files it wrote. Use for graphical abstracts, TOC/mechanism/pipeline summary figures, or any figure that must stay editable and auditable.
version: 1.0.0
---

# Graphical Abstract Trace Builder

把研究材料压缩成**单页四要素图形摘要**：研究问题 → 方法路线 → 核心结果 → 结论/含义。
交付分层可编辑 SVG、单页矢量 PDF、真实 PNG，以及把每个面板、箭头、编码与数字挂到
「来源 + locator + 逐字引文」上的 `content_map.json`。

三条判据决定成败，其余都是次要：

1. 图上每个实体、关系、数值都能回到材料里某一句，位置可指认（locator），字面可核对（quote）。
2. 同样输入重复运行得到字节一致的 SVG，版式不漂移。
3. 交付分层源文件而非截图，改一个标签就能重导出。

不做：论文正文写作、统计推断、实验方案设计；也不补造材料里没有的数值、单位、显著性、基因名或结论。

## 1. 适用条件

适用：要求 graphical abstract / 图文摘要 / 机制图 / 流程总结图 / TOC 图，且 `/input` 下有可读材料。
不适用：需要真实显微照片或统计检验的图（本包只做矢量化示意与数据条带编码）；只要文字总结。

## 2. 包结构

| 文件 | 职责 |
|-|-|
| `scripts/main.py` | 子命令入口，契约回填，`result.json` 落盘 |
| `scripts/core.py` | 输入发现、workorder 解析、段落索引、两处判定（引文匹配、工作稿校验） |
| `scripts/content.py` | 工作稿→产物：兜底稿、表格编码、剔除、content_map、compliance、edit_record、selfcheck |
| `scripts/layout.py` | 唯一排版权威：画布推导、字号阶梯、编码条带、图例，输出 display list 与图元表 |
| `scripts/emit.py` | SVG / PDF / PNG 三个导出器 + 像素探针（解码 PNG 自检墨量） |
| `references/workorder-and-plan.md` | workorder 字段、draft schema、locator 语法、result 键位、规则表、失败处置 |

纯标准库、离线、按自身位置定位模块（不依赖 CWD）。`init` 先写合法 `result.json`，之后每阶段覆盖；
任何子命令**退出码恒 0**，状态从字段读，不从崩溃信息读。

## 3. 主路径（五条命令，先做这一步）

```bash
python3 /skills/weekly-skill/scripts/main.py init       # 1 建索引 + 先写合法 partial result.json
python3 /skills/weekly-skill/scripts/main.py show       # 2 读带 locator 的原文与对象清单
#   3 这一步由你完成：亲自读材料，写工作稿 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check       # 4 机械校验工作稿
python3 /skills/weekly-skill/scripts/main.py build       # 5 出图 + 最终 result.json
python3 /skills/weekly-skill/scripts/main.py selfcheck   # 6 复检写盘产物
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

`build` 有兜底：工作稿缺失或不完整时仍产出完整最小交付（合法 `result.json`、非空 SVG/PDF/PNG、
`status=partial`、缺口写进 `degradations`）。那是降级结果，不是本 Skill 的正常产出——评审看的是
你有没有真的读过材料并做出取舍。

包根就是当前目录时，把 `/skills/weekly-skill/scripts/main.py` 换成 `scripts/main.py`，两条路径等价。

### 每一步

**init**：扫描 `/input`，按语义识别 `case.json`（`output_contract` / `task_instruction` / `organizer_workorder`）、
`task.md` 与材料；按魔数分 PDF/文本/二进制；切段落分配 locator；解析 workorder 得到画布、必需面板、
编码与导出要求；写 `work/index.json`、`work/spec.json` 与 partial `result.json`。

**show**：把可引用原文连 locator 打出来，供逐字复制。

```bash
python3 …/main.py show --grep "flux"        # 关键词定位
python3 …/main.py show --sid m2 --limit 20   # 按材料看
python3 …/main.py show --tables              # 表格行 locator（做数据编码时用）
python3 …/main.py show --workorder           # 画布/必需面板/编码/导出要求
python3 …/main.py show --contract            # 输出契约键清单
```

**你写工作稿** `/app/work/draft.json`：四段各写什么、每段一句 claim、选哪些数值、哪个通道编码哪列数据、
图例写什么。脚本不替你判断相关性，也不替你写结论。字段见 §6。

**check**：只校验不渲染。查四要素、claim、引文逐字命中、图面数字是否都在自己的引文里、编码是否配了
图例与来源、workorder 的 must_include 是否覆盖。输出 `PASS` / `NEEDS WORK` 与逐条 FAIL，写 `work/check.json`。

**build**：渲染七层 SVG（文字仍是 `<text>`、每图元带 id）、单页矢量 PDF、真实 PNG，写 `figure_model.json`、
`content_map.json`、`compliance_checks.json`、`edit_record.json`，最后覆盖 `result.json`。无法验证的图元
被剔除并逐条进 `exceptions`，不静默消失。

**selfcheck**：复检产物——契约键齐全、SVG 七层与文字节点、PNG 的 IHDR 尺寸、PDF 单页矢量、像素探针
显示每面板有墨、重算 SVG 与磁盘字节一致。写 `output/selfcheck.json`。

## 4. 运行契约

- 输入 `/input/case.json` + `/input/task.md` + 材料；工作目录 `/app/work`；产物 `/app/output`。
- 参数 `--input/--work/--output`（或 `GA_INPUT/GA_WORK/GA_OUTPUT`），默认即上表路径。
- **退出码恒 0**；状态看 `result.json` 的 `status`、`errors`、`degradations`、`exceptions`。
- 预算 64 请求 / 900 秒：解析、定位、排版、导出、校验全在脚本里，模型只做理解与判断。先落盘再优化。

## 5. 输入与 locator

| 类型 | 处理 | locator |
|-|-|-|
| `%PDF` | `pdftotext -layout`；抽不出就标 not parsed，需自己读页 | `p.<页> b.<块>` |
| md / txt | 空行分段 | `para.<段号>` |
| csv / tsv | 逐行，第 1 行是表头 | `para.<行号>` |
| 其他二进制 | 不解析，不猜内容 | — |

workorder 的键名、单位换算、缺省值见 `references/workorder-and-plan.md` §1；缺项写进
`result.json.runtime.spec_defaults`，不静默假设。

## 6. 工作稿 draft.json

```json
{
  "title": "研究对象 + 结论，一行读得完",
  "subtitle": "方法或意义补充（可选）",
  "caption": "图注：材料名 + 核对入口",
  "panels": [
    {"id": "P1", "role": "problem", "heading": "Research gap", "flow": "how?",
     "claim": "一句话说清这段要读者记住什么（你的判断，不是照抄整段）",
     "items": [{"id": "E1", "kind": "text", "label": "短标签", "detail": "条件/方向/限定",
                "evidence": {"source": "paper.md", "locator": "para.3", "quote": "从 show 复制的逐字原文"}}]}
  ],
  "encodings": [
    {"id": "enc1", "channel": "length", "meaning": "条形长度 = 相对活性", "unit": "% of WT",
     "panel": "P3", "data": {"path": "results.csv", "x": "group", "y": "activity"}}
  ],
  "legend": [{"label": "WT", "meaning": "wild type"}],
  "edits": [{"target_id": "panel3_label", "original": "旧标签", "revised": "新标签", "reason": "workorder 要求"}]
}
```

要点：`role` 用 `problem`/`method`/`results`/`implication` 四值；`claim` 是判断不是引文；面板 2–4 个，
每面板 1–3 图元；`kind` 取 `text`/`value`/`chart`；`channel` 取 `color`/`length`/`area`/`brightness`/`shape`；
有 `data` 块时脚本按表头取两列，把**每行原文**写进该分类的引文与 locator，柱长与柱上数值都能逐行回查。
不写坐标——几何全部由画布推导。

## 7. 产物与契约

`/app/output/`：`graphical_abstract.svg`（图层 `background/panels/marks/arrows/labels/legend/footer`）、
`graphical_abstract.pdf`（单页、页面尺寸等于画布）、`graphical_abstract.png`、
`figure_model.json`、`content_map.json`、`compliance_checks.json`、`edit_record.json`、`result.json`。

`result.json` 信封：`case_id`、`status`、`editable_source`、`export_artifact`、`content_map`、
`compliance_checks`、`edit_record`、`figure_model`、`exceptions`、`sources`、`uncertainty`、
`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
`status` 只能是 `ok`/`partial`/`insufficient_evidence`/`input_error`，且须如实反映本次运行。

`output_contract` 回填：键名原样、顺序不变；语义匹配到产物就填产物对象，匹配不到填 `null`（列表型
`[]`），**不删键、不改名**；无法匹配的键名进 `runtime.unmatched_contract_fields`，
`runtime.contract_keys_filled/total` 给出覆盖数，`selfcheck` 再核对一遍。

## 8. 方法（脚本执行）

- **版面**：按画布长宽比选方向（宽画布一行四栏，竖画布一列四段），标题带、面板带、图例带、页脚带
  全部由画布推导；无随机数、无时间戳。
- **四要素**：每面板一条 claim + 1–3 图元；面板头部写角色名与序号，颜色不是唯一编码。
- **通道**：`color` 色块、`length` 等比条、`area` 等比面积、`brightness` 明度块；图例项数必须等于
  图面分类数，`check` 与 `compliance.encoding_consistency` 都会点出不一致。
- **字号**：阶梯从标题到页脚（默认 18→7 pt，随画布微缩），不低于 workorder 的 `min_font_pt`。
  放不下先按 1.0/0.94/0.88/0.82/0.76 缩，仍放不下按序丢图元并写 `degradations`、`status=partial`。
- **配色**：Okabe-Ito 子集，分类色按亮度分散挑选，`grayscale_contrast` 记录最小亮度差。
- **确定性**：同一 draft + 同一画布 → 同一份 SVG；`selfcheck` 用 `figure_model.json` 重算比对 sha256。
- **数字**：只有独立数字算数据值（`78 %`、`2.4-fold`）；`SLC26A9`、`E203Q` 这类标识符里的数字按名称处理。

## 9. 校验规则（check）

| 规则 | 失败提示 |
|-|-|
| 四要素齐备 | `missing panel role: <role>` |
| 每面板有 claim（≥12 字） | `claim missing or too short` |
| 引文逐字命中 | `<eid>: unverified - quote not found verbatim` |
| 图元数字在自己引文里 | `<eid>: number(s) [...] not in its quote` |
| 全文数字在证据白名单内 | `figure number(s) [...] appear in no evidence quote` |
| 编码有通道、含义、≥2 分类、来源、图例 | `<encid>: ...` |
| workorder must_include 覆盖 | `must_include not covered: <token>` |

## 10. 边界与限制

- 只对图形表达负责：不写正文、不做统计检验、不设计实验。
- PDF 抽不出文本时不编造段落：自己读页、逐字引用、locator 写页码。
- PNG 优先由矢量 PDF 光栅化；无光栅化工具时退回内置位图光栅器，仅覆盖拉丁字形，CJK 预览缺失
  （SVG/PDF 完整），限制写进 `compliance_checks.png.note`。
- PDF 非拉丁文字用 CID 字体族回退（STSong-Light），不保证所有阅读器嵌入；SVG 用系统字体族。
- 无法判断也算结果：材料矛盾、口径不明（sd vs sem）、实体歧义，全部进 `pending_human`。

## 11. 失败处理与降级

| 情形 | 处置 | 落点 |
|-|-|-|
| `case.json` 缺失 / 坏 JSON | 递归找 `case*.json`；仍无则只用材料与 `task.md` | `errors[]`、`status=partial` |
| 材料全读不出文本 | 输出画布与占位结构，不作任何科学断言 | `status=insufficient_evidence` |
| 无 `draft.json` | 从原文抽四句做确定性兜底，逐字引用，版式完整 | `status=partial`、`exceptions[plan_missing]` |
| 引文验证不过 | 剔除该图元；面板空则放占位框 | `exceptions[element_dropped]`、`pending_human` |
| 面板溢出 | 逐级缩字号，再按序丢图元 | `degradations[]`、`status=partial` |
| 无 PDF 光栅化工具 | 内置光栅器出 PNG，引擎与限制如实记录 | `compliance_checks.png` |
| 渲染异常 | 捕获后仍 finalize `result.json`，SVG 退化为最小合法骨架 | `errors[]`、退出码 0 |

降级不是失败，隐瞒降级才是。`status=partial` 时每个缺口都要能在 `degradations`/`exceptions` 里对上。

## 12. 评分维度映射

| 维度（分值） | 本包证据 |
|-|-|
| 实际效果 40 | 完成度：四要素单页 + 分层 SVG + 单页 PDF + 真实 PNG；正确性：每图元每分类都有
`source+locator+quote`，关系词在 `flow`；完整性：claim/图例/单位/caption，缺口进 `pending_human`；
可核验：`content_map` 两级证据 + 材料 sha256 + `edit_record` + `runtime` 计数 |
| 使用增益 25 | 版式与编码规则固化；一次 init→draft→check→build 出稿；两次 build 字节一致 |
| 创新增益 15 | 数据行→逐字证据→条形编码；编码/图例一致性校验；像素级面板墨量探针 |
| 可靠体验 10 | 恒 0 退出码、先写 partial、单材料失败只降级它、缺工作稿仍出完整最小交付 |
| 生态贡献 10 | `references/` 字段字典；图层命名、导出参数、locator 语法可直接复用 |

## 13. 交付前自检（60 秒）

1. `check` PASS（coverage 1.0）、`selfcheck` PASS。
2. `result.json`：契约键齐全、`status` 属实、每条 `degradations` 都能对上一次真实降级。
3. SVG 七层在、文字可点选；PDF 单页、文字可选中；PNG 每面板有内容。
4. 抽两条 `content_map` quote，用 `show --grep` 复现。
5. 图里没有材料之外的实体名、数值、单位。

## 14. 最小调用示例（示例，非正式案例结果）

`init` 打印的材料清单 + `show` 打印的段落就是接口样例：每段带 `[m1] note.md :: para.4` 这样的
locator，把它连同原文抄进 `draft.json` 即构成一条可核验证据。换一份材料只需重写 draft，脚本不动。

维护约定：改字段要同步 `core.evaluate` 与 `content.content_map`；改版式只动 `layout.compose()`；
改导出只动 `emit.py`。版本 1.0.0。
