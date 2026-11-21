# SELFTEST · annotation-ledger

使用 `scripts/eval_sim.py` 在 rich / boundary × single / agent 四种组合下模拟官方评测。

## 四组合结果

| 案例 | 模式 | 结果 | 说明 |
|---|---|---|---|
| rich | single | PASS | 单命令直跑，契约与交付物齐全 |
| rich | agent | PASS | 五命令分步 + draft 回退，产物一致 |
| boundary | single | PASS | 空/损坏材料仍出合法 partial 结果 |
| boundary | agent | PASS | 异常材料下分步流程不中断 |

判定口径：退出码 0；`result.json` 合法并含 `output_contract` 全部键；路径键指向真实非空产物；无占位符残留；`case_id` 一致。

## 单命令实跑

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
echo $?   # 0
```

## 专家门控

- [ ] 已阅读 `references/expert_playbook.md`
- [ ] 专家检查表逐项通过
- [ ] 量化目标达标：锚点准确率 ≥95%；类型召回率 ≥90%；笔记支撑率 =100%；关联精确率 ≥90%；检索命中率 ≥80%；可复跑率 =100%
