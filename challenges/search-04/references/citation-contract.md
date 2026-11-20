# 引文追踪契约（search-04）

## 节点（papers）

| 字段 | 含义 |
|-|-|
| `rid` | 记录编号 `R001`…… |
| `locator` | 定位串 `M01#r2`（材料 M01 的第 2 条文献记录） |
| `title` / `authors` / `year` / `doi` | 逐字读取；缺失保留为空并记入 `gaps` |

## 边（edges）

| 字段 | 含义 |
|-|-|
| `source` | 引用方 locator（段落或文献记录） |
| `target` | 被引方 rid |
| `kind` | `cites`（正文引用标记）或 `lists`（参考文献条目） |
| `marker` | 触发边的原始标记（如 `[12]`、`(Author, 2019)`） |
| `locator` | 复核定位 |

## 路径（paths）

从 `seed` 出发，在被引方向上 BFS，记录 `path` 与 `depth`；有深度上限，避免在快照内无限展开。

## 缺口（gaps）

- 记录缺 `doi/year/title`：逐条列出 `missing_fields`。
- 正文引用标记指向快照外 rid：记为 `target_node` 缺口，不当作已解析。

## 诚实边界

不做外部引文库召回；不做引文影响力推断；元数据缺失如实记录；空/坏输入给 `insufficient_evidence`。
