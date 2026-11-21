# 论文转学术 PPT — 专家级参考手册

> 适用对象：通用 Agent 加载 Skill 后执行"论文→可讲、可核验、可编辑学术 PPT"任务。
> 版本：v1.0 | 适用运行时：Bohrium Agent + DeepSeek Harness
> 执行预算：64 model requests / 900 s / 16384 tokens per response

---

## 1. 任务理解与判分要点

### 1.1 真正要交付什么

本任务的交付物不是"一份 PPT 文件"，而是**一条从论文到可讲演示的完整、可复核转换链路**。评委最终看三件事：

| 核心判据 | 含义 | 对应分值权重 |
|----------|------|-------------|
| **主线成立** | PPT 的页序反映论文自身的贡献逻辑（问题→方法→关键证据→结论），而非按段落顺序搬运 | 实际效果 40 分中约 20 分 |
| **证据可溯** | 每一页的主张都能定位到论文中具体的图、表、章节或数据段落 | 实际效果 40 分中约 12 分 |
| **技术合规** | 在指定模板与软件版本中可打开、播放、编辑，导出 PDF 不崩版 | 实际效果 40 分中约 8 分 + 可靠体验 10 分 |

### 1.2 评委实际看什么

1. **主线 vs. 段落搬运**：翻开 PPT 第 2–4 页，如果内容是"摘要→引言→方法→结果"的段落切块，直接判低分。正确做法是提炼出论文的核心贡献（通常 1–3 个），围绕贡献组织页序。
2. **页级证据映射表**：每页是否有一行记录写明"本页引用 = 论文 Figure 3 + Section 4.2 第 2 段"。没有映射表 = 结果可核验性 0 分。
3. **数字/单位/方法名一致性**：PPT 上出现的每个数值必须与论文原文逐字一致，不允许四舍五入、单位换算不标注、方法缩写展开错误。
4. **模板合规**：标题字号、正文字号、配色、页脚是否在模板规定范围内，长标题是否正确换行而非溢出。
5. **讲解备注质量**：备注是否与页面内容互补（补充过渡逻辑、被问时的备用证据），而非重复页面文字。
6. **导出可核验**：是否同时提供 .pptx 源文件和 .pdf 导出件，且两者版式一致。

### 1.3 常见失败模式（错误→正确）

| # | 错误做法 | 正确做法 |
|---|---------|---------|
| F1 | 把 Abstract 整段贴进第 1 页 | 从 Abstract 提取 1 句话研究问题 + 1 句话核心发现，作为 Title 页副标题 |
| F2 | 按论文 Section 顺序线性排列 | 先画主线骨架（问题→贡献→证据链→结论），再填充页面 |
| F3 | 图表编号直接写"Fig.1"不标注来源 | 写"论文 Figure 1 (Section 3.1)"并在映射表记录页码 |
| F4 | 把示意图/流程图当实验数据展示 | 明确标注"示意图，来源：论文 Figure 2"与"实验数据，来源：论文 Figure 5" |
| F5 | 数值搬运中自动四舍五入（如 3.456→3.5） | 保留论文原始精度，必要时在备注中说明 |
| F6 | 长标题被文本框截断 | 检测标题字符数 > 模板阈值时自动换行或缩写，保留完整标题在备注 |
| F7 | 讲解备注 = 页面文字的复制 | 备注写"过渡语 + 本页关键点 + 被问时的补充证据" |
| F8 | 导出 PDF 时字体被替换 | 仅使用模板预定义字体族，导出前做字体嵌入检查 |
| F9 | 多图并列时图片重叠 | 按模板占位符数量分配图片位置，超出时分页或缩略图+备注引用 |
| F10 | 模板页脚/Logo 被覆盖 | 所有操作限于内容占位符，不触碰 master slide 元素 |
| F11 | 未处理 PDF 加密/图片型 PDF | 检测 PDF 是否可提取文字，不可提取时标记 status="partial" 并说明原因 |
| F12 | 页数超过限制仍继续添加 | 在大纲阶段就按页数上限分配各模块配额 |

---

## 2. 求解框架：分步流程与门控

整体流程分 **6 步**，每步有冻结产物和门控条件。未通过门控不进入下一步。

### Step 1：输入解析与可行性检查

- **输入**：`case.json` + `task.md` + 论文 PDF（或文本）+ 模板文件（.pptx）
- **操作**：
  1. 读取 `case.json` 提取 `case_id`、页数上限、模板路径、特殊约束
  2. 用 `parse_pdf` 提取论文全文（逐页文本）
  3. 用 python-pptx 读取模板的 layout 列表、占位符类型与数量
  4. 检查 PDF 是否可提取文字（文字密度 < 50 字/页 → 标记为图片型 PDF）
- **冻结产物**：`input_manifest.json`（论文页数、可提取文字量、模板 layout 列表、页数上限）
- **门控**：PDF 可解析 AND 模板可读取 → 通过；否则 status="partial"，记录原因

### Step 2：论文主线提取

- **输入**：论文全文（Step 1 产物）
- **操作**：
  1. 识别研究问题（通常在 Introduction 最后 1–2 段或 Abstract 第 1–2 句）
  2. 识别核心方法/贡献（通常在 Methods 开头或 Abstract 中间句）
  3. 识别关键证据（Results 中的主要 Figures/Tables，通常 3–6 个）
  4. 识别结论与限制（Discussion/Conclusion 段）
  5. 输出主线骨架：`[问题, 方法概述, 证据1, 证据2, ..., 证据N, 结论, 限制]`
- **冻结产物**：`narrative_backbone.json`（主线节点列表，每个节点含 source_locator）
- **门控**：主线节点数 ≥ 5 AND 每个节点有 source_locator → 通过

### Step 3：页结构设计与页数分配

- **输入**：`narrative_backbone.json` + 页数上限 + 模板 layout 列表
- **操作**：
  1. 按主线节点分配页面，每个主线节点至少 1 页
  2. 固定页面配额公式：
     - Title 页：1 页
     - 问题/背景：1–2 页
     - 方法概述：1–2 页
     - 关键证据：每个证据 1–2 页，总计占 40–60% 总页数
     - 结论与展望：1–2 页
     - 致谢/参考文献：0–1 页
  3. 为每页指定 layout（标题页、内容页、双栏页等）
  4. 每页写 1 句话主张（claim）+ 3–5 个要点（bullet points）
- **冻结产物**：`page_outline.json`（页号、layout、claim、bullets、evidence_refs）
- **门控**：总页数 ≤ 页数上限 AND 每页有 claim AND 每页有 evidence_refs → 通过

### Step 4：内容填充与证据映射

- **输入**：`page_outline.json` + 论文全文 + 模板
- **操作**：
  1. 逐页填充标题、要点文本（从论文对应段落提取/改写）
  2. 为每个要点标注论文来源（Figure X / Table Y / Section Z.W 第 N 段）
  3. 生成讲解备注（过渡语 + 关键点 + 补充证据）
  4. 检查数字/单位/方法名与论文原文一致
- **冻结产物**：`content_draft.json`（每页的标题、要点列表、备注、evidence_map）
- **门控**：每页所有要点有 evidence_ref AND 数字/单位一致性检查通过 → 通过

### Step 5：模板渲染与 PPTX 生成

- **输入**：`content_draft.json` + 模板 .pptx
- **操作**：
  1. 用 python-pptx 打开模板，按 page_outline 的 layout 添加 slide
  2. 填充占位符（标题→title placeholder，要点→body placeholder）
  3. 长标题检测：字符数 > 模板阈值时自动插入换行符
  4. 多图页：按占位符数量分配图片位置，超出部分放备注
  5. 写入讲解备注到 notes slide
  6. 不触碰 master slide 元素（页脚、Logo、配色）
- **冻结产物**：`presentation.pptx`（可编辑源文件）
- **门控**：文件可打开 AND slide 数 = page_outline 数 AND 无占位符溢出 → 通过

### Step 6：导出、核验与交付

- **输入**：`presentation.pptx`
- **操作**：
  1. 导出 PDF（如有 LibreOffice 则 soffice --convert-to pdf）
  2. 生成页级证据映射表（`evidence_mapping.json`）
  3. 生成 result.json（含 case_id、status、所有输出字段）
  4. 运行自查脚本（见第 6 节防扣分自查表）
- **冻结产物**：`presentation.pdf` + `evidence_mapping.json` + `result.json` + `self_check_report.json`
- **门控**：所有必需文件存在 AND 自查通过率 ≥ 80% → 通过

---

## 3. 专家方法与量化口径

### 3.1 关键指标定义

| 指标 | 定义 | 公式/口径 | 可接受范围 |
|------|------|----------|-----------|
| **主线覆盖率** | PPT 页序覆盖主线骨架节点的比例 | = 已覆盖节点数 / 主线总节点数 × 100% | ≥ 90% |
| **证据映射率** | 有明确论文来源标注的页面比例 | = 有 evidence_ref 的页数 / 总页数 × 100% | = 100%（Title/致谢页可豁免） |
| **数字一致性** | PPT 上出现的数值与论文原文一致的比例 | = 一致数值数 / 总数值数 × 100% | = 100% |
| **模板合规率** | 符合模板字号/配色/占位符规则的页面比例 | = 合规页数 / 总页数 × 100% | ≥ 95% |
| **备注覆盖率** | 有非空讲解备注的页面比例 | = 有备注的页数 / 总页数 × 100% | ≥ 90%（Title 页可豁免） |
| **备注非重复率** | 备注与页面文字不重复的比例 | = 1 − (备注与页面重复字符数 / 备注总字符数) | ≥ 70% |
| **页数合规** | 总页数是否在限制范围内 | = 实际页数 ≤ 页数上限 | True |
| **标题溢出率** | 标题超出占位符宽度的页面比例 | = 溢出页数 / 总页数 × 100% | = 0% |

### 3.2 页数分配计算公式

给定总页数上限 N（通常 15–25 页）：

```
Title 页 = 1
问题/背景页 = max(1, floor(N × 0.10))
方法页 = max(1, floor(N × 0.15))
证据页 = floor(N × 0.50)  # 核心，占 50%
结论页 = max(1, floor(N × 0.10))
其他页 = N - (Title + 问题 + 方法 + 证据 + 结论)  # 用于补充或致谢
```

**计算示例**：N = 20 页
- Title = 1
- 问题/背景 = floor(20 × 0.10) = 2
- 方法 = floor(20 × 0.15) = 3
- 证据 = floor(20 × 0.50) = 10
- 结论 = floor(20 × 0.10) = 2
- 其他 = 20 − (1+2+3+10+2) = 2
- 合计 = 1+2+3+10+2+2 = 20 ✓

### 3.3 标题溢出检测

```python
# 估算标题是否溢出（基于字符数和字号）
def check_title_overflow(title_text, placeholder_width_emu, font_size_pt):
    avg_char_width_pt = font_size_pt * 0.55  # 西文平均字符宽度近似
    est_width_pt = len(title_text) * avg_char_width_pt
    placeholder_width_pt = placeholder_width_emu / 12700  # EMU→pt
    return est_width_pt > placeholder_width_pt
```

当检测到溢出时：
1. 尝试在语义断点（逗号、连词）处插入换行
2. 若仍溢出，缩写非关键词（如 "Density Functional Theory" → "DFT"，前提是首次出现已展开）
3. 完整标题写入备注

### 3.4 备注生成规则

每页备注由三部分拼接，总长度控制在 80–200 字：

```
[过渡语] 从上一页的 XX 过渡到本页的 YY，一句话。
[关键点] 本页最重要的 1–2 个信息点，用口语化表达。
[备用证据] 如果被问到 ZZ，可以补充论文 Section A.B 中的 CC 数据。
```

---

## 4. 领域知识清单

### 4.1 事实性错误高发区

| 类别 | 常见错误 | 正确做法 |
|------|---------|---------|
| **方法名** | 把 "DFT" 展开为 "Density Function Theory"（漏 s） | "Density Functional Theory" |
| **方法名** | 把 "XRD" 展开为大小写不一致的形式 | 统一用论文中的写法 |
| **数值精度** | 论文写 "3.45 ± 0.02 eV"，PPT 写 "3.5 eV" | 保留完整精度 "3.45 ± 0.02 eV" |
| **单位** | 把 "kJ/mol" 写成 "KJ/mol" 或 "kj/mol" | 严格按论文原文 |
| **图表类型** | 把 DFT 计算能带图标注为"实验测量" | 明确标注计算方法 |
| **作者归属** | 把对比文献的数据当成本文结果 | 标注"本文"vs."文献 [N]" |
| **化学式** | 把 "Li₂O" 写成 "Li2O" 丢失下标 | 在 PPT 中使用下标格式 |
| **温度单位** | 混用 K 和 °C 不标注 | 严格按论文，必要时标注换算 |
| **晶体结构** | 把空间群 "Fm-3m" 写成 "Fm3m" 丢失横线 | 保留论文原始符号 |

### 4.2 单位/量纲陷阱

1. **能量单位**：eV、kJ/mol、kcal/mol 之间不可混用，除非论文本身做了换算
2. **长度单位**：Å 和 nm 的换算（1 nm = 10 Å），PPT 中必须与论文一致
3. **压力单位**：GPa、MPa、kbar 之间的换算，不要自动转换
4. **浓度单位**：mol/L、M、mM 之间的关系，注意大小写
5. **角度单位**：2θ vs. θ 在 XRD 图中的区别，不要混淆

### 4.3 文献引用要求

- PPT 中出现的所有文献引用必须与论文 References 中的编号一致
- 不要把论文中的 "as shown in previous studies" 替换为具体的文献编号
- 对比数据必须标注来源："This work" vs. "Ref. [N]"

---

## 5. 高质量交付物清单

### 5.1 必需文件

| 文件 | 路径 | 内容 | 自证方式 |
|------|------|------|---------|
| 可编辑 PPTX | `/app/output/presentation.pptx` | 完整幻灯片，含备注 | python-pptx 可读取、slide 数正确 |
| 导出 PDF | `/app/output/presentation.pdf` | PPTX 的 PDF 导出 | 页数与 PPTX 一致 |
| 证据映射表 | `/app/output/evidence_mapping.json` | 每页的论文来源定位 | 每条记录含 slide_number, claim, source_type, source_locator |
| 运行结果 | `/app/output/result.json` | 结构化输出，含所有字段 | case_id 匹配、status 诚实 |
| 自查报告 | `/app/output/self_check_report.json` | 15 项自查结果 | 每项 pass/fail + 说明 |
| 主线骨架 | `/app/output/narrative_backbone.json` | 论文主线节点 | 每个节点有 source_locator |
| 页级大纲 | `/app/output/page_outline.json` | 页结构设计 | 每页有 claim + evidence_refs |

### 5.2 evidence_mapping.json 格式

```json
{
  "case_id": "case_001",
  "total_slides": 18,
  "mappings": [
    {
      "slide_number": 1,
      "claim": "研究问题：XX 材料在 YY 条件下的 ZZ 性能",
      "source_type": "abstract",
      "source_locator": "Abstract, sentences 1-2",
      "notes": "标题页"
    },
    {
      "slide_number": 5,
      "claim": "XRD 结果表明主相为 cubic perovskite",
      "source_type": "figure",
      "source_locator": "Figure 3a, Section 3.2 paragraph 1",
      "data_values": ["2θ = 23.1°, 32.8°, 46.5°"],
      "notes": "实验数据图，非示意图"
    }
  ]
}
```

### 5.3 result.json 格式

```json
{
  "case_id": "case_001",
  "status": "completed",
  "output_files": {
    "pptx": "presentation.pptx",
    "pdf": "presentation.pdf",
    "evidence_mapping": "evidence_mapping.json"
  },
  "metrics": {
    "total_slides": 18,
    "max_slides_allowed": 20,
    "narrative_coverage_pct": 100.0,
    "evidence_mapping_pct": 100.0,
    "numerical_consistency_pct": 100.0,
    "template_compliance_pct": 100.0,
    "notes_coverage_pct": 94.4,
    "self_check_pass_rate_pct": 93.3
  },
  "uncertainty": [],
  "change_log": [
    {"step": "input_parse", "status": "ok", "detail": "PDF 12 pages, 8 figures detected"},
    {"step": "narrative_extract", "status": "ok", "detail": "7 backbone nodes"},
    {"step": "page_design", "status": "ok", "detail": "18 slides allocated"},
    {"step": "content_fill", "status": "ok", "detail": "all evidence mapped"},
    {"step": "render", "status": "ok", "detail": "PPTX + PDF generated"},
    {"step": "self_check", "status": "ok", "detail": "14/15 passed"}
  ]
}
```

---

## 6. 防扣分自查表（15 项）

在最终交付前逐项检查，每项标记 pass/fail 并记录说明：

| # | 自查项 | 检查方法 | 判定标准 |
|---|--------|---------|---------|
| 1 | PPTX 文件可打开 | python-pptx 读取无异常 | 无 IOError |
| 2 | PDF 文件可打开 | PyMuPDF 读取无异常 | 无 IOError |
| 3 | Slide 数 = 大纲数 | len(prs.slides) == len(page_outline) | 相等 |
| 4 | Slide 数 ≤ 页数上限 | len(prs.slides) <= case.max_slides | ≤ |
| 5 | 每页有标题 | 检查 title placeholder 非空 | 非空 |
| 6 | 标题无溢出 | 运行 check_title_overflow | 全部 False |
| 7 | 每页有 evidence_ref | 检查 evidence_mapping 覆盖 | 豁免页外全覆盖 |
| 8 | 数值与论文一致 | 逐页比对 PPT 数值与论文原文 | 100% 一致 |
| 9 | 单位与论文一致 | 逐页比对单位字符串 | 100% 一致 |
| 10 | 方法名拼写正确 | 对照论文 Methods 段 | 无拼写差异 |
| 11 | 图表类型标注正确 | 区分示意图 vs. 实验数据图 | 无混淆 |
| 12 | 讲解备注非空 | 检查 notes slide | ≥ 90% 页面有备注 |
| 13 | 备注与页面不重复 | 计算备注非重复率 | ≥ 70% |
| 14 | 模板配色/页脚未被修改 | 比对 master slide 属性 | 无变化 |
| 15 | 字体族在模板范围内 | 检查所有 text run 的 font name | 属于模板预定义集合 |

**自查脚本伪代码**：

```python
from pptx import Presentation
import json, fitz  # PyMuPDF

def self_check(pptx_path, pdf_path, outline, mapping, template_fonts, max_slides):
    prs = Presentation(pptx_path)
    doc = fitz.open(pdf_path)
    results = []

    # 1. PPTX 可打开 → 已通过（到这里说明成功）
    results.append({"item": 1, "pass": True, "detail": "PPTX opened"})

    # 2. PDF 可打开
    results.append({"item": 2, "pass": True, "detail": f"PDF {doc.page_count} pages"})

    # 3. Slide 数 = 大纲数
    n_slides = len(prs.slides)
    results.append({"item": 3, "pass": n_slides == len(outline),
                    "detail": f"{n_slides} vs {len(outline)}"})

    # 4. Slide 数 ≤ 上限
    results.append({"item": 4, "pass": n_slides <= max_slides,
                    "detail": f"{n_slides} <= {max_slides}"})

    # 5-6. 标题检查
    for i, slide in enumerate(prs.slides):
        title = slide.shapes.title.text if slide.shapes.title else ""
        # ... check non-empty and no overflow

    # 7-15. 类似逐项检查 ...
    return results
```

---

## 7. 完整虚构案例演示

### 7.1 输入

- **论文**：虚构论文 "Enhanced Thermoelectric Performance of SnSe via Na Doping"
  - 8 页，3 个 Figures，2 个 Tables
  - 核心贡献：Na 掺杂使 SnSe 的 ZT 值从 0.8 提升至 1.4（773 K）
  - 关键证据：Figure 2（XRD 图谱）、Figure 3（ZT vs. T 曲线）、Table 1（电输运参数）
- **模板**：学术会议模板，2 种 layout（Title、Content），字体 Arial/Noto Sans
- **约束**：最多 15 页

### 7.2 关键中间量

**Step 1 — 输入解析**：
```json
{
  "pdf_pages": 8,
  "extractable_chars": 6200,
  "figures_detected": 3,
  "tables_detected": 2,
  "template_layouts": ["Title", "Content"],
  "max_slides": 15
}
```

**Step 2 — 主线骨架**：
```json
[
  {"node": 1, "type": "problem", "label": "SnSe 热电材料 ZT 值受限",
   "source": "Introduction para 3"},
  {"node": 2, "type": "method", "label": "Na 掺杂策略（0–8% mol）",
   "source": "Section 2.1"},
  {"node": 3, "type": "evidence", "label": "XRD 确认单相 orthorhombic 结构",
   "source": "Figure 2, Section 3.1"},
  {"node": 4, "type": "evidence", "label": "电导率随 Na 含量提升 3.2 倍",
   "source": "Table 1, Section 3.2"},
  {"node": 5, "type": "evidence", "label": "ZT 峰值 1.4 at 773 K（x=0.04）",
   "source": "Figure 3, Section 3.3"},
  {"node": 6, "type": "conclusion", "label": "Na 掺杂是提升 SnSe 热电性能的有效途径",
   "source": "Conclusion para 1"},
  {"node": 7, "type": "limitation", "label": "高 Na 含量（>6%）出现杂相",
   "source": "Section 3.1 para 2"}
]
```
主线节点数 = 7 ≥ 5 ✓，全部有 source_locator ✓ → 门控通过

**Step 3 — 页数分配**（N = 15）：
```
Title = 1
问题/背景 = floor(15 × 0.10) = 1 → 调整为 2（需覆盖问题 + 背景）
方法 = floor(15 × 0.15) = 2
证据 = floor(15 × 0.50) = 7（3 个证据节点各 2 页 + 1 页综合对比）
结论 = floor(15 × 0.10) = 1
其他 = 15 − (1+2+2+7+1) = 2（限制 + 致谢）
合计 = 1+2+2+7+1+2 = 15 ✓
```

**Step 4 — 内容填充示例（第 7 页）**：
```json
{
  "slide_number": 7,
  "layout": "Content",
  "title": "ZT 峰值达 1.4（773 K, x = 0.04）",
  "bullets": [
    "ZT 值从纯 SnSe 的 0.8 提升至 Na₀.₀₄Sn₀.₉₆Se 的 1.4",
    "提升幅度 ≈ 75%，归因于载流子浓度优化",
    "最佳掺杂浓度 x = 0.04，超过后 ZT 下降"
  ],
  "evidence_refs": [
    {"type": "figure", "locator": "Figure 3b", "note": "实验数据，非计算"},
    {"type": "text", "locator": "Section 3.3, paragraph 2"}
  ],
  "notes": "【过渡】从电输运参数过渡到综合热电性能。【关键点】ZT 1.4 是本文最核心的数据点，强调 773 K 是中温区间的实用温度。【备用】如果被问到与其他热电材料对比，可引用论文 Discussion 中提到的 PbTe (ZT≈1.8) 和 Bi₂Te₃ (ZT≈1.0)。"
}
```

数值校验：
- 论文原文："The ZT value reaches a maximum of 1.4 at 773 K for x = 0.04" → PPT 写 "1.4 at 773 K, x = 0.04" ✓
- 论文原文："an enhancement of approximately 75%" → PPT 写 "≈ 75%" ✓
- 化学式 Na₀.₀₄Sn₀.₉₆Se：与论文 Table 1 一致 ✓

### 7.3 最终输出

**文件清单**：
```
/app/output/
├── presentation.pptx      (15 slides, 可编辑)
├── presentation.pdf        (15 pages, 导出件)
├── evidence_mapping.json   (15 条映射记录)
├── narrative_backbone.json (7 个主线节点)
├── page_outline.json       (15 页大纲)
├── content_draft.json      (15 页完整内容)
├── result.json             (结构化结果)
└── self_check_report.json  (15 项自查)
```

**result.json 摘要**：
```json
{
  "case_id": "thermoelectric_snse_001",
  "status": "completed",
  "metrics": {
    "total_slides": 15,
    "max_slides_allowed": 15,
    "narrative_coverage_pct": 100.0,
    "evidence_mapping_pct": 100.0,
    "numerical_consistency_pct": 100.0,
    "template_compliance_pct": 100.0,
    "notes_coverage_pct": 93.3,
    "notes_non_repeat_rate_pct": 82.0,
    "self_check_pass_rate_pct": 100.0
  },
  "change_log": [
    {"step": "input_parse", "status": "ok"},
    {"step": "narrative_extract", "status": "ok", "detail": "7 nodes"},
    {"step": "page_design", "status": "ok", "detail": "15 slides"},
    {"step": "content_fill", "status": "ok"},
    {"step": "render", "status": "ok"},
    {"step": "self_check", "status": "ok", "detail": "15/15 passed"}
  ]
}
```

---

## 附录 A：异常处理决策树

```
PDF 解析失败？
├── 图片型 PDF → status="partial", 尝试 OCR（如有 tesseract），标注哪些页不可提取
├── 加密 PDF → status="failed", 记录 "PDF is encrypted"
└── 空文件 → status="failed", 记录 "Empty PDF"

模板无可用 layout？
├── 仅有 1 种 layout → 全部使用该 layout，在备注中标注"受限于模板"
└── 模板损坏 → status="failed", 记录 "Template corrupt"

页数超限？
├── 合并低优先级页面（致谢+参考文献合并）
├── 将支撑性证据移至备注引用
└── 仍超限 → 按优先级截断，status="partial", 记录截断原因

论文图表无法提取（嵌入式图片）？
├── 标注"图表位置：Figure X, page Y"
├── 在 PPT 中放置占位文本框"[此处插入论文 Figure X]"
└── 在 evidence_mapping 中记录 source_type="figure_unextractable"
```

## 附录 B：python-pptx 操作要点速查

| 操作 | 代码片段 | 注意事项 |
|------|---------|---------|
| 打开模板 | `prs = Presentation(template_path)` | 不要用空白 Presentation |
| 获取 layouts | `layouts = prs.slide_layouts` | 索引从 0 开始 |
| 添加 slide | `slide = prs.slides.add_slide(layout)` | 指定 layout 对象 |
| 填标题 | `slide.shapes.title.text = "..."` | 先检查 title 是否存在 |
| 填正文 | `slide.placeholders[1].text_frame.text = "..."` | 索引 1 通常是 body |
| 加备注 | `slide.notes_slide.notes_text_frame.text = "..."` | 自动创建 notes slide |
| 保存 | `prs.save(output_path)` | 原子写入：先写临时文件再 rename |
| 读字体 | `run.font.name` | 遍历所有 paragraph.runs |

---

> **使用提示**：本手册指导 Agent 完成论文→PPT 转换的全部步骤。执行时严格按 Step 1–6 顺序推进，每步通过门控后再进入下一步。遇到异常按附录 A 决策树处理。最终交付物必须包含全部 8 个文件，且自查通过率 ≥ 80%。
