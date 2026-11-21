---
name: paper-notes-structurer
version: 1.0.0
description: >-
  Turn a real paper into structured, reusable reading notes: rebuild the paper's
  OWN section skeleton (not a generic Introduction/Methods template), fill a
  six-field card (research question, data, method conditions, main findings,
  conclusion, limitations) with a value + anchor + verbatim quote per field, emit
  machine-readable note units each carrying an S-section / paragraph / line anchor,
  verify every quote against the paper text, and compare candidate reproduction
  numbers against the reported ones. Use when a task asks for 文献总结 / 结构化笔记 /
  论文卡片 / 锚点回链 / 科研阅读 with reproducible evidence. Pure standard library,
  offline, deterministic.
---

# paper-notes-structurer

Notes must answer *and* show their grounds. This skill keeps the paper's own structure,
writes a card whose every field carries an anchor and a verbatim quote, stores each note as
a machine-readable unit with a `S3 ¶2/L17` locator, and re-checks every quote at its anchor.
Fields the paper does not report stay `not-reported`; nothing is invented.

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its
`output_contract` object; `case_id` is passed through unchanged. When the case supplies its
own `output_contract`, those keys are used instead and each is filled the same way (an
artifact-like key resolves to the written file, any other key gets a real derived value).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "answered | partial | insufficient_evidence | input_error",
    "result": "notes.md",
    "notes": "notes.md",
    "note_units": "note_units.jsonl",
    "paper_card": "paper_card.json",
    "coverage": "coverage.json",
    "claims": "the anchored note units",
    "uncertainties": "what the notes could not ground"
  }
}
```

## 1. Draft schema (JSON, optional)

An agent may fill `/app/work/draft.json` with the paper's own section list and one claim per
card field; `build` merges it, and the deterministic extractor still runs regardless, so a
thin draft cannot turn an unreadable paper into a fabricated note.

```json
{
  "case_id": "",
  "sections": [],
  "claims": [],
  "unknown_fields": [],
  "change_log": []
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete
`result.json`, and exits 0:

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. agent-first 增强路径（可选，质量更高）

List the source with locators, fill the draft above, then check it before `build` merges it:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints each source line with its `M02/p9` locator so the agent can quote it; `check`
reports whether the notes carry anchors; `compare` writes a base-vs-skill contrast to
`/app/work/compare_report.json`.

## 4. Pipeline

1. Index every file under `/input` with its kind, size and parse status (`parsed` /
   `empty-file` / `placeholder-only` / `unparsed-binary`).
2. Read the paper (an explicit `paper` field, else the largest prose file that is not an
   instruction or metadata file).
3. Split it on its own headings and numbered sections into `S0..Sn`, each paragraph getting
   an anchor `S1 ¶2/L5`.
4. Fill the six-field card from the sections whose headings match each field, else mark the
   field `not-reported`.
5. Emit each key sentence as a note unit with its anchor, field and verbatim quote; verify
   the quote against the paper text.
6. Parse candidate implementation metrics (a `candidates` JSON list, or a python script that
   assigns a `metrics` dict) and compare them against the reported numbers.
7. Compute coverage (sections, card fields known, anchor hit rate) and write the artifacts.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, sections, paper_card, candidate_verdicts, sources, uncertainties, change_records, artifacts |
| `notes.md` | section skeleton + six-field card (with anchors) + anchored notes + candidate comparison |
| `note_units.jsonl` | one JSON object per note: claim_id, field, text, anchor, quote, has_number, verbatim |
| `paper_card.json` | the six fields with value/anchor/quote/source_section + anchor stats |
| `coverage.json` | sections, card fields known, card_ratio, anchor_hit_rate |
| `claims.json` | the note units plus candidate verdict rows |
| `run_log.txt` | per-material parse status and the stage counts |

## 6. Degradation rules

- No readable paper text → `status=insufficient_evidence`, every artifact carries a
  structured no-data record naming the searched locations; exit 0.
- Binary / empty / placeholder-only file → recorded with its parse status, never quoted.
- Paper with one block and no headings → skip the skeleton, still fill what the card can and
  report the rest `not-reported`; `status=partial`.
- A quote that does not match the paper text is reported `verbatim=false` rather than passed
  as grounded.
- No network, no third-party package, no invented numbers.

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
