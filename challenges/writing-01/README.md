# writing-01 · 章节稿组装与逐句回链（v6 忠实适配）

输入一批科研材料 → 输出一篇可编辑的章节稿 `manuscript.md` 与契约齐全的 `result.json`。
正文里的每条回链语句都能在材料里找到**逐字原句**与 `文件:行号` 定位；材料没写的，
只会出现在「附录 缺口与待确认」，不会被编出来。

## 安装

纯 Python 3.9+ 标准库，无网络、无第三方包。把目录放到 `/skills/weekly-skill`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/contract-and-locators.md
  environment/resources.yaml
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

一次性跑完（评测只跑这一条也能通过）：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

默认 `--input /input`、`--output /app/output`、`--work /app/work`；退出码恒为 0。

Agent 优先路径（四步，可分别重跑）：

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# Agent 读 init 的清单后，把草稿写入 /app/work/draft.json（结构见 references/contract-and-locators.md）
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

没有草稿也能直接 `build`：脚本按材料里可定位的句子自动分节组装，状态记 `partial`。
草稿里未命中材料的引用一律拒收并记入 `pending_human`。

## 最小可运行示例

`/input` 只需要一份材料（`case.json` 可选）：

```
/input/case.json                 {"case_id": "demo-1"}
/input/materials/paper.md        若干段落，含数字与结论句
```

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
# built manuscript.md | status=ok sections=9 evidence=12 h2=9 chars=1655
```

## 判分口径与限制

- 引用成立与否，只看去空白后的子串是否出现在材料里；不猜同义改写，人工认可的等价改写可能被低估，
  因此每条证据都带命中项与定位，便于人工复核。
- 不解析 PDF 二进制、不读图片内数值、不生成材料外的数值或文献。
- 只有空文件或模板标记（如 `[待写]`）时，记 `insufficient_evidence` 并在 `degradations` 写明缺口。

## 维护

改动后跑：空输入、坏 JSON 两种探针（`work/self_check.json`），以及
`scripts/eval_sim.py` 的 rich/boundary × single/agent 四格，记录进 `SELFTEST.md`。
