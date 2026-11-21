# figure-spec 规则表 · 字段字典 · 质量清单

`scripts/spec.py` 的校验常量与本文件一致；改判据须同步两处。

## 1. 工作稿 `/app/work/draft.json`

```json
{"case_id":"<透传>",
 "data_plan":{"source":"<文件/表>","missing":"<策略+理由>","outlier":"flag|drop(阈值)",
              "duplicate":"<策略>","rows_before":0,"rows_after":0,
              "assumption_checks":["…"],"conflicts":["…"]},
 "figure_specs":[{"figure_id":"Fig-1","question":"这张图回答什么",
   "data":{"source":"x.csv","filter":"none|field=v1,v2|field>3","aggregation":"组均值/分箱/相关矩阵",
           "x_field":"…","y_fields":["…"]},
   "chart":{"type":"bar|box|scatter|line|hist|heatmap","rationale":"为什么这个图型",
            "rejected_types":[{"type":"pie","why_not":"…"},{"type":"line","why_not":"…"}]},
   "encoding":{"x":"…","y":"…","color":"…|none","shape":"none","size":"equal","facet":"none",
               "scales":{"x":"linear|log","y":"linear|log"},"palette":"okabe-ito"},
   "stats":{"error_bar_type":"SD|SE|95%CI|none","error_bar_source":"按组 SD，分母 n-1，n=…",
            "test":"welch_t|anova|none","correction":"holm","alpha":0.05,"n_per_group":{}},
   "annotation":{"title":"…","x_label":"…","x_unit":"…","y_label":"…","y_unit":"…",
                 "legend":"…","caption":"…","panel":"A"},
   "export":{"format":"svg","width_mm":89,"dpi":300,"font_pt":7,
             "font_policy":"Arial/Helvetica; CJK: Noto Sans CJK SC",
             "colorblind_safe":true,"grayscale_safe":true}}],
 "claims":[{"field":"y","group_field":"g","group":"A","stat":"mean","value":0.0}],
 "evidence":[{"claim":"…","locator":"csv:/input/x.csv#c=y&r=5","quote":"逐字"}],
 "tables":[],"uncertainties":["…"]}
```

`claims` 由 `check` 回算（容差 max(1e-6, 0.5%)）；`evidence` 供逐字引用；`uncertainties` 进报告第 5 节与 `result.uncertainty`。

## 2. 字段字典（必填项由 `check` 硬校验）

| 字段 | 取值 / 约束 | 不填的后果 |
|-|-|-|
| `data.source` | 材料文件名/表名（可模糊匹配） | `data_source_missing` |
| `data.filter` | `none` / `field=v1,v2` / `field>3`（只执行可解析的过滤） | 记 `filter_unparsed` |
| `data.aggregation` | 组均值（按 X）/ 逐行值+拟合 / 分箱计数 / 相关矩阵 | `aggregation_missing` |
| `chart.type` | 六种之一 | `chart_type_unsupported` |
| `chart.rejected_types` | ≥2 条 `{type, why_not}` | `rejected_types_insufficient` |
| `stats.error_bar_type` | `SD`（默认）/`SE`/`95%CI`/`none` | `error_bar_undefined` |
| `stats.error_bar_source` | n、分母、按组还是整体 | `error_bar_source_missing` |
| `stats.test` | `welch_t`（2 组）/三组以上用两两 Welch + Holm | 不可算须写 `none` |
| `stats.n_per_group` | `{组名: n}`；留空时 build 回填实测值 | warn |
| `annotation.*` | 标题/轴标目/单位/图例/caption | 缺 caption 仅 warn（模板补全） |
| `export.width_mm` | 60–200（常用 89 单栏 / 120 1.5 栏 / 183 双栏） | 越界回落 89 |
| `export.dpi` | ≥300 | 回落 300 |
| `export.font_pt` | ≥7（单栏可读下限） | 回落 7 |
| `export.colorblind_safe`/`grayscale_safe` | 布尔声明 | warn |

## 3. 数据结构 × 分析目的 → 图型

| 数据结构 | 比较 | 分布 | 相关 | 趋势 | 构成 |
|-|-|-|-|-|-|
| 分类 × 连续 | **柱状（均值+误差线）** | **箱线图** | — | — | 100% 堆叠柱（本包不画，改用柱状+说明） |
| 连续 × 连续 | — | 直方图（单变量） | **散点+OLS**（报 r、p、n） | 折线（有序 x） | — |
| 时间 × 连续 | — | — | — | **折线**（x 按时间排序） | — |
| ≥3 连续 | — | 直方图/箱线 | **相关热图**（r 标注 + 限幅色标） | — | — |

**拒绝规则（写进 `rejected_types`）**：饼图（角度不可读）；时间轴并列柱（切断趋势）；双轴（量纲不同应双面板）；面积/角度编码（夸大差异）；3D（透视伪影）；>8 类不分面；线性量级用对数轴（除非跨 ≥100 倍）。

## 4. 编码与可读性

位置/长度（柱高、点位置）承担定量比较；颜色只承担类别（热图除外）。调色板 `okabe-ito`：`#0072B2 #E69F00 #009E73 #CC79A7 #56B4E9 #D55E00 #F0E442 #525252`；灰度安全以**最差成对亮度差 ≥10%** 判定（`audit.readability`），不足时加形状/纹理/明度交替。单栏 89 mm：正文 ≥7 pt、线宽 0.5–1.0 pt、网格 `#e2e2e2`、留白 ≥3 mm、类别 >5 时 x 标签旋转 35°。柱状图基线 0；截断须在图注写明；对数轴刻度 1/2/5×10ᵏ。

## 5. 统计口径

| 量 | 定义 | 备注 |
|-|-|-|
| SD | 样本标准差，分母 n−1 | 默认误差线 |
| SE | SD/√n | 与 SD 不可混画 |
| 95%CI | t₀.₉₇₅(n−1)·SE | n≥30 用 1.96；小样本查表 |
| Welch t | 不等方差 t 检验 | 组内 n≥3 |
| Holm | 逐步校正 | 两两比较 >1 对时 |
| Pearson r / OLS | 完整配对样本 | 报 r、p、n |

## 6. 导出规格

SVG 为矢量主交付，文字是真实 `<text>`（不转路径），`font-family` 含 CJK 回退链；PNG ≥300 dpi，像素 = `width_mm/25.4×dpi`（±3 px），由系统 `rsvg-convert`/`convert` 生成，缺失则记 `png_preview_unavailable`；画布 89/120/183 mm 栏宽，高度按内容自适应并在报告给出毫米值；`figures[].sha256_svg` + `figure_code.py` 复跑，同规格两次渲染 sha 必须一致。

## 7. 质量清单（提交前自检）

- [ ] `figure_report.md` 五节齐全：数据口径 / 图件清单 / 数据→图元素映射 / 统计检验 / 局限。
- [ ] 每图有 `rejected_types` ≥2 条理由、误差线口径、检验方法、`n_per_group`。
- [ ] 图注含 `n`、误差线定义、单位、检验 p（`cap_cover` 4/4）。
- [ ] `data_to_figure.json` 每元素 `verified=true`；不符项进 `pending_human`。
- [ ] `audit.json`：`type_match=ok`、`layout.ok=true`、`readability` 记录最差 ΔL。
- [ ] `result.json` 契约键 = 源 `output_contract` 键；未映射键已记 `contract_key_unmapped:<key>`。
- [ ] `status=ok` 仅当工作稿存在且无 spec 级 error；否则 `partial` 且 `limits` 说明缺口。

## 8. 评分维度 → 包内落点

| 维度 | 落点 |
|--|--|
| 实际效果 | 真实 SVG+PNG、图注、代码；`data_to_figure.json` 元素账本；`audit.json` 结构/误差线/导出/版式检查 |
| 使用增益 | `init→show→check→build` 固定清洗/统计/渲染/校验；`check` 前置拦截错误规格；`selfcheck` 复检 27 项 |
| 创新增益 | 规格-审计耦合（拒绝理由/误差线口径为必填）、元素级独立回算、最差亮度差灰度检查、文字越界/重叠的版式审计、字节级可复现渲染 |
| 可靠体验 | exit 0、partial 先行、坏 JSON/空目录/缺表/缺渲染器均降级不崩；`--input/--output/--work` 兼容 |
| 生态贡献 | 本规则表 + SKILL.md 调用契约 + `figure_code.py` 可复用渲染脚本 + 六图型模板 |
