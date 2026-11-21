import json, re
from collections import Counter, defaultdict
from pathlib import Path
from core import EVENT_TYPES, YEAR_SOURCES, GAP_TYPES, LIFECYCLES, CRITERIA, norm

def compute_stats(ev):
    by_year, by_type, theme_year, theme_type = (Counter(), Counter(), defaultdict(Counter), defaultdict(Counter))
    bad_year = 0
    for e in ev:
        y = e.get('year')
        if not (isinstance(y, int) and 1800 <= y <= 2100):
            bad_year += 1
            continue
        by_year[str(y)] += 1
        by_type[str(e.get('event_type'))] += 1
        t = e.get('theme_id') or 'unassigned'
        theme_year[t][str(y)] += 1
        theme_type[t][str(e.get('event_type'))] += 1
    years = sorted((int(k) for k in by_year))
    growth = []
    for a, b in zip(years, years[1:]):
        da, db = (by_year[str(a)], by_year[str(b)])
        growth.append({'from': a, 'to': b, 'delta': db - da, 'ratio': round(db / da, 2) if da else None})
    total = sum(by_year.values())
    peak = max(by_year.items(), key=lambda kv: (kv[1], int(kv[0])))[0] if by_year else None
    mismatch = None
    if total != len([e for e in ev if isinstance(e.get('year'), int)]):
        mismatch = '年度求和 %d ≠ 台账有效年份条数 %d' % (total, len([e for e in ev if isinstance(e.get('year'), int)]))
    multi = sum((1 for t, c in theme_year.items() if len(c) >= 2))
    return {'by_year': dict(sorted(by_year.items(), key=lambda kv: int(kv[0]))), 'by_type': dict(by_type.most_common()), 'by_theme_year': {k: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for k, v in theme_year.items()}, 'by_theme_type': {k: dict(v.most_common()) for k, v in theme_type.items()}, 'growth': growth, 'peak_year': int(peak) if peak else None, 'span': [years[0], years[-1]] if years else None, 'events_dated': total, 'events_undated': bad_year, 'themes_with_multi_year': multi, 'mismatch': mismatch, 'recomputed_by': 'derive.compute_stats(event_ledger)'}

def coverage(idx, ev, stats):
    srcs = idx.get('sources', [])
    years = sorted({e['year'] for e in ev if isinstance(e.get('year'), int)})
    return {'sources_expected': len(srcs), 'sources_read': sum((1 for s in srcs if s.get('chars', 0) > 0)), 'sources_with_year': sum((1 for s in srcs if s.get('year'))), 'events': len(ev), 'events_dated': len([e for e in ev if isinstance(e.get('year'), int)]), 'years_covered': years, 'year_span': [years[0], years[-1]] if years else None, 'themes': sorted({str(e.get('theme_id') or 'unassigned') for e in ev}), 'event_types_covered': sorted({str(e.get('event_type')) for e in ev}), 'event_type_coverage': '%d/%d' % (len({e.get('event_type') for e in ev} & set(EVENT_TYPES)), len(EVENT_TYPES)), 'small_sample': bool(len(ev) <= 20 or len(srcs) <= 10), 'unreadable_sources': [s['source_id'] for s in srcs if s.get('chars', 0) == 0]}

def suggest_stages(ev):
    years = sorted({e['year'] for e in ev if isinstance(e.get('year'), int)})
    if not years:
        return []
    if len(years) <= 2:
        return [{'stage_id': 'G1', 'label': '%d–%d（全期，样本不足未细分）' % (years[0], years[-1]), 'year_range': [years[0], years[-1]], 'basis_event_ids': [e['event_id'] for e in ev if isinstance(e.get('year'), int)][:5], 'lifecycle': 'emerging' if len(ev) <= 6 else 'consolidating', 'rationale': '事件跨年数 ≤2，任何切分都无统计支撑；仅在类型构成显著变化时再细分。'}]
    mid = years[len(years) // 2]
    a = [e for e in ev if isinstance(e.get('year'), int) and e['year'] < mid]
    b = [e for e in ev if isinstance(e.get('year'), int) and e['year'] >= mid]
    out = []
    for i, (grp, lo, hi) in enumerate(((a, years[0], mid - 1), (b, mid, years[-1])), 1):
        if not grp:
            continue
        out.append({'stage_id': 'G%d' % i, 'label': '%d–%d' % (lo, hi), 'year_range': [lo, hi], 'basis_event_ids': [e['event_id'] for e in grp[:3]], 'lifecycle': 'emerging' if i == 1 else 'consolidating', 'rationale': '脚本按年份中位数切分的候选，需用事件类型构成/主题首现代替'})
    return out

def derive_turnings(ev):
    out, seen = ([], set())
    by_year = defaultdict(list)
    for e in ev:
        if isinstance(e.get('year'), int):
            by_year[e['year']].append(e)
    first_type = {}
    for e in sorted([x for x in ev if isinstance(x.get('year'), int)], key=lambda x: x['year']):
        t = e.get('event_type')
        if t not in first_type:
            first_type[t] = e
            out.append({'turning_id': '', 'event_ids': [e.get('event_id')], 'criteria_hit': 'first_of_type', 'why_turning': '%s 类型首次出现在 %s 年（%s）' % (t, e['year'], e.get('statement', '')[:80]), 'auto': True})
    th_first, th_last = ({}, {})
    for e in sorted([x for x in ev if isinstance(x.get('year'), int)], key=lambda x: x['year']):
        t = e.get('theme_id') or 'unassigned'
        th_first.setdefault(t, e)
        th_last[t] = e
    for t, e in th_first.items():
        if t not in seen:
            seen.add(t)
            out.append({'turning_id': '', 'event_ids': [e.get('event_id')], 'criteria_hit': 'theme_birth', 'why_turning': '主题 %s 首现于 %s 年' % (t, e['year']), 'auto': True})
    ts = sorted(by_year)
    for a, b in zip(ts, ts[1:]):
        da, db = (len(by_year[a]), len(by_year[b]))
        if len(ev) >= 8 and (db >= 2 * da and db - da >= 2 or (da >= 2 * db and da - db >= 2)):
            out.append({'turning_id': '', 'event_ids': [x.get('event_id') for x in by_year[b][:3]], 'criteria_hit': 'density_jump', 'why_turning': '%d→%d 年事件数 %d→%d' % (a, b, da, db), 'auto': True})
    for i, t in enumerate(out, 1):
        t['turning_id'] = 'P%d' % i
    return out[:12]

def representative(ev, turns, stages):
    srcs = {}
    for t in turns:
        for eid in t.get('event_ids') or []:
            for e in ev:
                if str(e.get('event_id')) == str(eid):
                    srcs.setdefault(e.get('source_id'), {'source_id': e.get('source_id'), 'basis': 'turning_event', 'criteria_hit': t.get('criteria_hit'), 'event_ids': [eid], 'year': e.get('year'), 'why': t.get('why_turning', '')})
    out = list(srcs.values())
    covered = set()
    for s in stages:
        yr = s.get('year_range') or []
        hit = [r for r in out if isinstance(r.get('year'), int) and len(yr) == 2 and (yr[0] <= r['year'] <= yr[1])]
        if not hit:
            cand = [e for e in ev if isinstance(e.get('year'), int) and len(yr) == 2 and (yr[0] <= e['year'] <= yr[1])]
            if cand:
                e = sorted(cand, key=lambda x: x['year'])[0]
                out.append({'source_id': e.get('source_id'), 'basis': 'stage_first_event', 'criteria_hit': 'stage_first_event', 'event_ids': [e.get('event_id')], 'year': e.get('year'), 'why': '阶段 %s 无转折事件，取该阶段最早事件兜底' % s.get('stage_id')})
        covered.add(s.get('stage_id'))
    return out

def derive_gaps(ev, stats):
    out, by_theme = ([], defaultdict(list))
    for e in ev:
        by_theme[e.get('theme_id') or 'unassigned'].append(e)
    for t, es in sorted(by_theme.items()):
        prop = [e for e in es if e.get('event_type') == 'proposal']
        val = [e for e in es if e.get('event_type') in ('validation', 'refutation')]
        if prop and (not val):
            out.append({'gap_id': '', 'gap_type': 'missing_validation', 'description': '主题 %s 有提出（%s）但材料内无验证/反驳事件' % (t, ', '.join((str(e.get('event_id')) for e in prop[:3]))), 'events_evidence': [e.get('event_id') for e in prop[:3]], 'search_scope': '待补：在本批材料与给定检索式范围内对 %s 检索验证类动词' % t, 'exclusion_evidence': '', 'auto': True})
        ys = sorted([e['year'] for e in es if isinstance(e.get('year'), int)])
        if len(ys) >= 2 and stats.get('peak_year') and (ys[-1] < stats['peak_year'] - 1):
            out.append({'gap_id': '', 'gap_type': 'stalled_theme', 'description': '主题 %s 最后事件在 %s 年，此后 %d 年无事件' % (t, ys[-1], stats['peak_year'] - ys[-1]), 'events_evidence': [e.get('event_id') for e in es if e.get('year') == ys[-1]][:2], 'search_scope': '待补：检索 %s–%s 年该主题' % (ys[-1] + 1, stats['peak_year']), 'exclusion_evidence': '', 'auto': True})
        ref = [e for e in es if e.get('event_type') == 'refutation']
        if ref and val:
            out.append({'gap_id': '', 'gap_type': 'unresolved_conflict', 'description': '主题 %s 存在验证与反驳并存，结论未定' % t, 'events_evidence': [ref[0].get('event_id')] + [v.get('event_id') for v in val[:2]], 'search_scope': '待补：检索后续是否有复现或调节变量研究', 'exclusion_evidence': '', 'auto': True})
    for i, g in enumerate(out, 1):
        g['gap_id'] = 'N%d' % i
    return out[:8]

def stage_table(ev, stages):
    rows = []
    for s in stages:
        yr = s.get('year_range') or [None, None]
        es = [e for e in ev if isinstance(e.get('year'), int) and isinstance(yr[0], int) and (yr[0] <= e['year'] <= yr[1])]
        rows.append({'stage_id': s.get('stage_id'), 'label': s.get('label'), 'year_range': yr, 'lifecycle': s.get('lifecycle'), 'events': len(es), 'by_type': dict(Counter((str(e.get('event_type')) for e in es))), 'basis_event_ids': s.get('basis_event_ids') or [], 'rationale': s.get('rationale', '')})
    return rows
COLORS = {'proposal': '#1f77b4', 'validation': '#2ca02c', 'refutation': '#d62728', 'method_introduced': '#9467bd', 'merged': '#8c564b', 'split': '#e377c2', 'declined': '#7f7f7f', 'application_transfer': '#ff7f0e'}

def ledger_jsonl(ev):
    keys = ['event_id', 'year', 'year_source', 'event_type', 'statement', 'source_id', 'locator', 'quote', 'theme_id', 'method', 'object', 'confidence', 'auto', 'reviewed']
    out = []
    for e in ev:
        row = {k: e.get(k) for k in keys if k in e or k in ('auto', 'reviewed')}
        row['case_evidence'] = '%s@%s' % (e.get('source_id'), e.get('locator'))
        out.append(json.dumps(row, ensure_ascii=False, sort_keys=False))
    return '\n'.join(out) + ('\n' if out else '')

def evidence_matrix(ev, idx):
    names = {s['source_id']: s for s in idx.get('sources', [])}
    rows = []
    for e in sorted(ev, key=lambda x: (x.get('year') or 0, str(x.get('event_id')))):
        s = names.get(str(e.get('source_id')), {})
        rows.append({'event_id': e.get('event_id'), 'year': e.get('year'), 'year_source': e.get('year_source'), 'event_type': e.get('event_type'), 'theme_id': e.get('theme_id'), 'method': e.get('method'), 'object': e.get('object'), 'confidence': e.get('confidence'), 'source_id': e.get('source_id'), 'source_title': s.get('title'), 'venue': s.get('venue'), 'locator': e.get('locator'), 'quote': e.get('quote'), 'statement': e.get('statement')})
    return rows

def render_timeline(idx, d, ev, stats, stages, turns, gaps, reps, report, status):
    L = []
    cov = report.get('coverage') or {}
    mn = d.get('method_notes') or {}
    L.append('# 事件时间线 · %s' % idx.get('case_id'))
    L.append('')
    L.append('研究问题：%s' % (d.get('research_question') or idx.get('research_question') or '（未给出）'))
    L.append('')
    L.append('| 项 | 值 |')
    L.append('|---|---|')
    L.append('| 语料来源 | %d 份（可读 %d） |' % (cov.get('sources_expected', 0), cov.get('sources_read', 0)))
    L.append('| 事件 | %d 条（有年份 %d） |' % (cov.get('events', 0), cov.get('events_dated', 0)))
    L.append('| 年份跨度 | %s |' % (cov.get('year_span') or '无可用年份'))
    L.append('| 主题 | %s |' % (', '.join(cov.get('themes') or []) or '-'))
    L.append('| 事件类型覆盖 | %s |' % cov.get('event_type_coverage', '-'))
    L.append('| 阶段 / 转折 / 空白 | %d / %d / %d |' % (len(stages), len(turns), len(gaps)))
    L.append('| 小样本 | %s |' % ('是（结论为提示性）' if cov.get('small_sample') else '否'))
    L.append('| status | %s |' % status)
    L.append('')
    L.append('## 1. 口径')
    L.append('')
    L.append('- 年份口径：%s' % (mn.get('year_basis') or '未说明（默认见刊年 published 为主口径）'))
    L.append('- 主题归并：%s' % (mn.get('theme_merge_rules') or '未说明'))
    L.append('- 阶段依据：%s' % (mn.get('stage_basis') or '见各阶段 basis_event_ids'))
    L.append('- 空白判据：%s' % (mn.get('gap_criteria') or '事件类型缺口 + 检索范围 + 排除证据'))
    L.append('')
    L.append('## 2. 时间线')
    L.append('')
    if not ev:
        L.append('> 台账为空：本次未抽取到事件（材料不可读或未完成事件判定）。降级记录见 result.json.degradations。')
    by_year = defaultdict(list)
    for e in ev:
        by_year[e.get('year')].append(e)
    bnd = {}
    for s in stages:
        yr = s.get('year_range') or []
        if len(yr) == 2:
            bnd.setdefault(yr[0], []).append('进入阶段 %s（%s）' % (s.get('stage_id'), s.get('label')))
    turn_at = defaultdict(list)
    for t in turns:
        for eid in t.get('event_ids') or []:
            turn_at[str(eid)].append(t.get('turning_id'))
    for y in sorted([k for k in by_year if isinstance(k, int)]) + ([None] if None in by_year else []):
        L.append('### %s' % (y if y is not None else '年份缺失（不参与统计）'))
        L.append('')
        for note in bnd.get(y, []):
            L.append('**阶段边界** ▶ %s' % note)
            L.append('')
        for e in sorted(by_year[y], key=lambda x: str(x.get('event_id'))):
            tid = ','.join(turn_at.get(str(e.get('event_id')), []))
            L.append('- **%s** `%s` · %s · 主题 %s · 置信 %s%s' % (e.get('event_id'), e.get('event_type'), e.get('locator'), e.get('theme_id') or '-', e.get('confidence') or '-', ' · 转折 ' + tid if tid else ''))
            L.append('  - %s' % (e.get('statement') or ''))
            L.append('  - 原文：> %s' % re.sub('\\s+', ' ', str(e.get('quote') or ''))[:300])
        L.append('')
    L.append('## 3. 阶段划分')
    L.append('')
    L.append('| 阶段 | 年份 | 事件数 | 类型构成 | 生命周期 | 依据事件 |')
    L.append('|---|---|---|---|---|---|')
    for s in stages:
        L.append('| %s %s | %s–%s | %s | %s | %s | %s |' % (s.get('stage_id'), s.get('label'), (s.get('year_range') or ['?', '?'])[0], (s.get('year_range') or ['?', '?'])[1], s.get('events', ''), ', '.join(('%s:%s' % kv for kv in (s.get('by_type') or {}).items())) or '-', s.get('lifecycle') or '-', ', '.join((str(x) for x in s.get('basis_event_ids') or [])) or '-'))
    L.append('')
    for s in stages:
        if s.get('rationale'):
            L.append('- **%s**：%s' % (s.get('stage_id'), s.get('rationale')))
    L.append('')
    L.append('## 4. 转折事件与代表作')
    L.append('')
    if not turns:
        L.append('> 未标注转折事件（无 criteria 命中）。')
    for t in turns:
        L.append('- **%s** [%s] 事件 %s — %s' % (t.get('turning_id'), t.get('criteria_hit'), ', '.join((str(x) for x in t.get('event_ids') or [])), t.get('why_turning')))
    L.append('')
    if reps:
        L.append('| 代表作 | 年份 | 入选口径 | 事件 | 理由 |')
        L.append('|---|---|---|---|---|')
        for r in reps:
            L.append('| %s | %s | %s | %s | %s |' % (r.get('source_id'), r.get('year'), r.get('basis'), ', '.join((str(x) for x in r.get('event_ids') or [])), str(r.get('why') or '')[:120]))
    L.append('')
    L.append('## 5. 研究空白')
    L.append('')
    if not gaps:
        L.append('> 未登记空白（不等于领域无空白；本轮未给出排除证据）。')
    for g in gaps:
        L.append('### %s `%s`' % (g.get('gap_id'), g.get('gap_type')))
        L.append('')
        L.append('- 描述：%s' % g.get('description'))
        L.append('- 事件证据：%s' % ', '.join((str(x) for x in g.get('events_evidence') or [])))
        L.append('- 检索范围：%s' % (g.get('search_scope') or '未填'))
        L.append('- 排除证据：%s' % (g.get('exclusion_evidence') or '未填（不能排除检索遗漏）'))
        L.append('')
    L.append('## 6. 覆盖、冲突与限制')
    L.append('')
    L.append('- 覆盖：%s' % json.dumps(cov, ensure_ascii=False))
    for u in d.get('uncertainties') or []:
        L.append('- 不确定：%s' % u)
    for u in (report.get('hints') or [])[:8]:
        L.append('- 提示：%s' % u)
    L.append('')
    L.append('_台账为唯一事实源；本文件与 derived/*.json、figures/timeline.svg 均由 `scripts/main.py build` 从 events/event_ledger.jsonl 生成，可复算。_')
    return '\n'.join(L) + '\n'

def render_report(idx, d, ev, stats, stages, turns, gaps, reps, cov, status, degr):
    L = ['# 研究前沿与趋势分析 · %s' % idx.get('case_id'), '']
    L.append('**研究问题**：%s' % (d.get('research_question') or idx.get('research_question') or '（未给出）'))
    L.append('')
    L.append('**数据基础**：%d 份材料、%d 条带年份事件、跨度 %s；status=%s%s' % (cov.get('sources_expected', 0), cov.get('events_dated', 0), cov.get('year_span') or '无', status, '；**小样本（提示性结论）**' if cov.get('small_sample') else ''))
    L.append('')
    L.append('## 1. 结论摘要')
    L.append('')
    concl = d.get('conclusions') or []
    if concl:
        for c in concl:
            if isinstance(c, dict):
                L.append('- %s（依据：%s；强度：%s）' % (c.get('text'), ', '.join((str(x) for x in c.get('event_ids') or [])) or '-', c.get('strength') or '-'))
            else:
                L.append('- %s' % c)
    elif ev:
        L.append('- 台账共 %d 条事件，覆盖 %d 个年份；峰值年 %s。' % (cov.get('events', 0), len(cov.get('years_covered') or []), stats.get('peak_year')))
        L.append('- 未填写 conclusions：本摘要仅陈述可复算计数，不含推断。')
    else:
        L.append('- 无可用事件，未形成趋势结论。')
    L.append('')
    L.append('## 2. 年度分布（由台账聚合，可复算）')
    L.append('')
    L.append('| 年份 | 事件数 | 类型构成 |')
    L.append('|---|---|---|')
    for y, n in (stats.get('by_year') or {}).items():
        ty = [e for e in ev if str(e.get('year')) == str(y)]
        c = Counter((str(x.get('event_type')) for x in ty))
        L.append('| %s | %d | %s |' % (y, n, ', '.join(('%s:%d' % kv for kv in c.most_common()))))
    if not stats.get('by_year'):
        L.append('| - | 0 | - |')
    L.append('')
    if stats.get('growth'):
        L.append('相邻年变化：' + '；'.join(('%s→%s %+d' % (g['from'], g['to'], g['delta']) for g in stats['growth'])))
        L.append('')
        L.append('> 增长率仅在事件数 ≥8 且年份完整时用于判断拐点；本批样本 %d 条，%s' % (cov.get('events', 0), '不足以判定拐点，仅提示性描述。' if cov.get('small_sample') else '满足最低计数门槛。'))
        L.append('')
    L.append('## 3. 主题演化')
    L.append('')
    L.append('| 主题 | 年份分布 | 类型构成 |')
    L.append('|---|---|---|')
    for t, yr in (stats.get('by_theme_year') or {}).items():
        L.append('| %s | %s | %s |' % (t, ', '.join(('%s:%d' % kv for kv in yr.items())), ', '.join(('%s:%d' % kv for kv in (stats.get('by_theme_type') or {}).get(t, {}).items()))))
    if not stats.get('by_theme_year'):
        L.append('| - | - | - |')
    L.append('')
    for s in stages:
        L.append('- **%s %s**（%s–%s，%s）：%s' % (s.get('stage_id'), s.get('label'), (s.get('year_range') or ['?', '?'])[0], (s.get('year_range') or ['?', '?'])[1], s.get('lifecycle'), s.get('rationale')))
    L.append('')
    L.append('## 4. 转折点')
    L.append('')
    if not turns:
        L.append('未识别到满足 criteria 的转折事件。')
    for t in turns:
        L.append('- **%s**（%s）：%s —— 事件 %s' % (t.get('turning_id'), t.get('criteria_hit'), t.get('why_turning'), ', '.join((str(x) for x in t.get('event_ids') or []))))
    L.append('')
    L.append('## 5. 代表性工作（按转折口径，非按总被引）')
    L.append('')
    L.append('| 来源 | 年份 | 口径 | 事件 | 理由 |')
    L.append('|---|---|---|---|---|')
    for r in reps:
        L.append('| %s | %s | %s | %s | %s |' % (r.get('source_id'), r.get('year'), r.get('basis'), ', '.join((str(x) for x in r.get('event_ids') or [])), str(r.get('why') or '')[:100]))
    if not reps:
        L.append('| - | - | - | - | 无转折事件，未指定代表作 |')
    L.append('')
    L.append('## 6. 研究空白（附排除证据）')
    L.append('')
    if not gaps:
        L.append('未登记空白条目；如需结论须补检索范围与排除证据。')
    for g in gaps:
        L.append('### %s `%s`' % (g.get('gap_id'), g.get('gap_type')))
        L.append('- 描述：%s' % g.get('description'))
        L.append('- 事件证据：%s' % ', '.join((str(x) for x in g.get('events_evidence') or [])))
        L.append('- 检索范围：%s' % (g.get('search_scope') or '未填'))
        L.append('- 排除证据：%s' % (g.get('exclusion_evidence') or '未填'))
        L.append('')
    L.append('## 7. 方法、口径与复算')
    L.append('')
    for k in ('year_basis', 'theme_merge_rules', 'stage_basis', 'gap_criteria', 'small_sample_rule'):
        if (d.get('method_notes') or {}).get(k):
            L.append('- **%s**：%s' % (k, d['method_notes'][k]))
    L.append('- 事件类型学：8 类固定枚举（proposal/validation/refutation/method_introduced/merged/split/declined/application_transfer）')
    L.append('- 复算路径：`events/event_ledger.jsonl` → `derived/trend_stats.json`（`python3 scripts/main.py selfcheck` 重算比对）')
    L.append('')
    L.append('## 8. 限制与不确定')
    L.append('')
    for u in d.get('uncertainties') or []:
        L.append('- %s' % u)
    for u in d.get('pending_human') or []:
        L.append('- 待人工：%s' % u)
    if degr:
        for g in degr:
            L.append('- 降级：%s' % g)
    L.append('- 本节结论仅覆盖所给材料的年份与主题范围，不外推到全领域；未做显著性检验。')
    L.append('')
    return '\n'.join(L) + '\n'

def render_svg(ev, stages, path):
    dated = [e for e in ev if isinstance(e.get('year'), int)]
    W, H0 = (980, 120)
    themes = sorted({str(e.get('theme_id') or 'unassigned') for e in dated}) or ['unassigned']
    lanes = len(themes)
    H = H0 + lanes * 56
    if not dated:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="140"><rect width="100%%" height="100%%" fill="#fff"/><text x="24" y="70" font-family="sans-serif" font-size="16" fill="#666">无带年份事件：时间线为空（见 result.json.degradations）</text></svg>' % W
        Path(path).write_text(svg, encoding='utf-8')
        return {'years': [], 'lanes': themes, 'dots': 0}
    y0, y1 = (min((e['year'] for e in dated)), max((e['year'] for e in dated)))
    if y1 == y0:
        y1 = y0 + 1
    LEFT, RIGHT = (150, 40)

    def x(y):
        return LEFT + (y - y0) / float(y1 - y0) * (W - LEFT - RIGHT)
    P = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="sans-serif">' % (W, H, W, H), '<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H), '<text x="%d" y="28" font-size="16" font-weight="bold" fill="#222">Event timeline (%d events, %d–%d)</text>' % (LEFT, len(dated), y0, y1)]
    for i, s in enumerate(stages):
        yr = s.get('year_range') or []
        if len(yr) != 2 or not all((isinstance(v, int) for v in yr)):
            continue
        xa, xb = (x(max(yr[0], y0)), x(min(yr[1], y1)))
        P.append('<rect x="%.1f" y="46" width="%.1f" height="%d" fill="%s"/>' % (xa, max(xb - xa, 2), H - 90, '#f2f4f8' if i % 2 == 0 else '#e8edf5'))
        P.append('<text x="%.1f" y="60" font-size="10" fill="#556">%s %s</text>' % (xa + 3, s.get('stage_id'), str(s.get('label') or '')[:22]))
    for y in range(y0, y1 + 1):
        xx = x(y)
        P.append('<line x1="%.1f" y1="66" x2="%.1f" y2="%d" stroke="#dfe3ea" stroke-width="1"/>' % (xx, xx, H - 34))
        P.append('<text x="%.1f" y="%d" font-size="10" fill="#667" text-anchor="middle">%d</text>' % (xx, H - 18, y))
    for i, t in enumerate(themes):
        yy = 86 + i * 56
        P.append('<text x="10" y="%d" font-size="11" fill="#333">%s</text>' % (yy + 4, t[:18]))
        P.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#e6e9ef" stroke-width="1"/>' % (LEFT, yy, W - RIGHT, yy))
        for e in sorted([d for d in dated if str(d.get('theme_id') or 'unassigned') == t], key=lambda z: z['year']):
            xx = x(e['year'])
            c = COLORS.get(str(e.get('event_type')), '#444')
            P.append('<circle cx="%.1f" cy="%d" r="6" fill="%s" fill-opacity="0.85" stroke="#fff" stroke-width="1"/>' % (xx, yy, c))
            P.append('<!-- %s | %s | %s | %s -->' % (e.get('event_id'), e.get('year'), e.get('event_type'), str(e.get('statement') or '')[:90].replace('<', '&lt;').replace('>', '&gt;')))
            P.append('<text x="%.1f" y="%d" font-size="8" fill="#444" text-anchor="middle">%s</text>' % (xx, yy - 10, e.get('event_id')))
    lx = LEFT
    ly = H - 44
    for k, c in COLORS.items():
        if k not in {str(e.get('event_type')) for e in dated}:
            continue
        P.append('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (lx, ly, c))
        P.append('<text x="%d" y="%d" font-size="9" fill="#555">%s</text>' % (lx + 8, ly + 3, k))
        lx += 34 + 6 * len(k)
    P.append('</svg>')
    Path(path).write_text('\n'.join(P), encoding='utf-8')
    return {'years': [y0, y1], 'lanes': themes, 'dots': len(dated)}

def figure_specs(words):
    return {'figures': [{'file': 'figures/timeline.svg', 'format': 'svg', 'kind': 'event_timeline', 'data_source': 'events/event_ledger.jsonl', 'fields': {'x': 'year', 'lane': 'theme_id', 'color': 'event_type', 'label': 'event_id', 'band': 'derived/stage_division.json:year_range'}, 'encoding': {'color_map': COLORS, 'lane_order': words.get('lanes', [])}, 'scale': {'x': 'linear_year', 'dots': words.get('dots', 0)}, 'redraw': 'python3 scripts/main.py build', 'note': 'SVG 由台账逐条绘制，可与台账逐点核对；无外部数据注入。'}]}
