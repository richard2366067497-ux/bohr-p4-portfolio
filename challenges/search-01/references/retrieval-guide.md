# 查询规划、去重与排序模板

本文件是 traceable-literature-retrieval 的可复用检索模板，配合 `references/expert_playbook.md`
的 §2 八步框架使用。全部为确定性规则，无网络、无外部模型。

## 1. 研究问题 → 概念组

把研究问题拆成若干**概念组**（对象 / 方法 / 主题 / 限制条件），每组收集：主术语、已验证同义词、
缩写、上下位概念。组内用 `OR`、组间用 `AND`：

```
Q1 = (对象术语 OR 对象同义词) AND (方法术语)
Q2 = Q1 AND (主题术语 OR 主题同义词)
```

每条查询记录 `query_id / query / intent / source`。`source` 取
`local_snapshot_replay`（本地快照重放）、`live_request`（实时请求）或 `manual_derivation`（人工推导），
三者不得混写。

## 2. 分轮召回与轮次收益

| 轮次 | 原始记录 | 新增唯一 | 其中新增相关 | 累计唯一 |
|---|---:|---:|---:|---:|
| Q1 | — | — | — | — |

- 轮次收益率同时报告 `new_relevant/raw_count` 与 `new_unique/raw_count`，
  防止把重复抓取当成覆盖提升。
- 失败轮次记录错误，不冒充空结果。

## 3. 去重与规范 ID

判重分层，按如下顺序取第一个命中的键：

1. 规范 DOI（去 `doi:` / resolver 前缀、trim、大小写归一，仅用于匹配）；
2. 来源原生 ID（同库内）；
3. 规范化标题 `nkey(title)`；
4. 版本关系（预印本 ↔ 正式版）用 `version_of` 表达，是否合并取决于任务口径。

每个合并簇记录规则、成员与保留理由；保留证据更全的一条，成员写入 `duplicate_of`。

## 4. 排序与同分处理

1. 先执行硬约束（对象不匹配、超范围年份等）直接排除，并记录依据；
2. 再按相关性等级降序；
3. 同等级按初排分降序；
4. 仍同分按规范 ID 升序。

排序规则必须可重复执行：同一快照、同一配置重跑，规范 ID 与排名完全一致。

## 5. 证据与状态

- 每条候选和每条排除都带 locator 与依据字段；locator 结构：
  `file + json_pointer + source_record_id + query_id`。
- 相关性判断另附 `evidence_field` 与短逐字引文。
- 状态枚举：`ok / partial / insufficient_evidence / input_error`，诚实取自产物。
- 空结果、接口失败、权限不足、材料缺失分别说明，不混为一谈。
