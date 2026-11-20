# 清洗规则与问题码（可编辑）

## 1. 问题码

| 码 | 含义 | 改值 |
|---|---|---|
| MISSING_BLANK | 单元格为空或仅空白 | 否 |
| MISSING_CODE | 命中字典/工单声明的缺失码 | 否 |
| BELOW_LOD | 低于检出限，不等于 0 | 否 |
| NON_NUMERIC | 数值型字段出现无法解析的文本 | 否 |
| INVALID_TOKEN | 命中无效码（#DIV/0!、err…） | 否 |
| OUT_OF_RANGE | 超出字典物理上下限 | 否 |
| OUTLIER | IQR/MAD 双侧栅栏诊断出的异常 | 否 |
| UNIT_CONVERTED | 按注册表完成单位换算 | 可逆 |
| DUP_DROPPED | 主键重复的次要行，隔离保留 | 不删行 |
| NO_USABLE_VALUE | 整行所有实质字段均不可用 | 否 |

## 2. 异常值判定

- **IQR**：栅栏 `[Q1 − 1.5·IQR, Q3 + 1.5·IQR]`。
- **MAD**：稳健离差 `|x − median| > 3.0·MAD`。
- **物理上下限**：来自字典 `valid_range`（`0-2000`、`>=0`、`<=100`、`0..50`）。
- 阈值 `IQR_K` / `MAD_K` 定义在 `scripts/engine.py`，可调整；越界与异常一律只标记。

## 3. 重复记录

可比较列（去除元列后）取值全等的行视为重复：保留首个出现，其余行 `status=quarantined`、
flags 记 `DUP_DROPPED`，**不删除**，供人工复核。

## 4. 单位换算

`units` 注册表给出 `单位 -> [量纲, 到基准的因子, 偏移]`；换算前先经 `unit_aliases` 归一
（如 `μg/ml -> ug/ml`）。仅当量纲一致时换算，账本记录 `{from, to, factor, source_value}` 与逆映射。

## 5. QC 不变式

逐条核验并在报告中给出证据：行数守恒、动作与账本一致、报告数字可回算、源文件 sha256 不变、
被标记的字段值未被替换。

## 6. 降级

无表 / 坏 JSON / 空文件：记入 `uncertainties`，`cleaned_table.csv` 写空表状态行，退出码仍为 0。
