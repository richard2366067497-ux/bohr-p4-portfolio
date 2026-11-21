import json, re
from datetime import datetime, timezone
from pathlib import Path
import core as C
import derive as D
DEFAULT_CONTRACT = ['research_summary', 'events', 'trend_stats', 'stage_division', 'turning_points', 'gaps', 'evidence_matrix', 'uncertainty']
ALIAS = [('event_ledger', 'events'), ('event', 'events'), ('timeline', 'events'), ('trend', 'trend_stats'), ('annual', 'trend_stats'), ('year', 'trend_stats'), ('distribution', 'trend_stats'), ('statistic', 'trend_stats'), ('stage', 'stage_division'), ('phase', 'stage_division'), ('epoch', 'stage_division'), ('turning', 'turning_points'), ('inflection', 'turning_points'), ('breakpoint', 'turning_points'), ('milestone', 'turning_points'), ('gap', 'gaps'), ('blank', 'gaps'), ('openquestion', 'gaps'), ('opportunit', 'gaps'), ('represent', 'representative_works'), ('seminal', 'representative_works'), ('landmark', 'representative_works'), ('keypaper', 'representative_works'), ('classic', 'representative_works'), ('evidence', 'evidence_matrix'), ('matrix', 'evidence_matrix'), ('citation', 'evidence_matrix'), ('uncertain', 'uncertainty'), ('limitation', 'uncertainty'), ('caveat', 'uncertainty'), ('risk', 'uncertainty'), ('conflict', 'conflicts'), ('method', 'method_notes'), ('protocol', 'method_notes'), ('reproduc', 'method_notes'), ('coverage', 'coverage'), ('completeness', 'coverage'), ('change', 'change_log'), ('version', 'change_log'), ('question', 'research_question'), ('topic', 'research_question'), ('objective', 'research_question'), ('summary', 'research_summary'), ('report', 'research_summary'), ('review', 'research_summary'), ('narrative', 'research_summary'), ('conclusion', 'research_summary'), ('source', 'sources'), ('corpus', 'sources'), ('material', 'sources'), ('reference', 'sources'), ('status', 'status'), ('case', 'case_id')]

def contract_fields(contract):
    out = []
    if isinstance(contract, dict):
        out = [str(k) for k in contract.keys()]
    elif isinstance(contract, list):
        for x in contract:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for k in ('name', 'field', 'key', 'id'):
                    if isinstance(x.get(k), str):
                        out.append(x[k])
                        break
    return [f for f in dict.fromkeys(out) if f and f.lower() not in ('type', 'description', 'required', 'note')]

def contract_of(idx):
    c = (idx or {}).get('output_contract')
    if isinstance(c, dict) and c:
        return c
    if isinstance(c, list) and c:
        return c
    return DEFAULT_CONTRACT

def fill_contract(contract, vals):
    fields = contract_fields(contract)
    res, rep = ({}, {'fields': fields, 'filled': [], 'null_fields': [], 'unknown_fields': []})
    for f in fields:
        key = re.sub('[^a-z0-9]', '', f.lower())
        hit = f if f in vals else key if key in vals else None
        if hit is None:
            for pat, target in ALIAS:
                if pat in key and target in vals:
                    hit = target
                    break
        if hit is None:
            res[f] = None
            rep['unknown_fields'].append(f)
            rep['null_fields'].append(f)
        else:
            res[f] = vals[hit]
            (rep['null_fields'] if vals[hit] in (None, [], {}, '') else rep['filled']).append(f)
    return (res, rep)

def run_selfcheck(out, wrk):

    def rj(p, d=None):
        try:
            return json.loads(Path(p).read_text(encoding='utf-8-sig'))
        except Exception:
            return d
    out, wrk = (Path(out), Path(wrk))
    res = rj(out / 'result.json', {}) or {}
    lines, fails = ([], [])

    def ck(name, ok, detail=''):
        lines.append('%s %-26s %s' % ('PASS' if ok else 'FAIL', name, detail))
        if not ok:
            fails.append(name)
    ck('result.json 可解析', bool(res), 'keys=%d' % len(res))
    ck('case_id 存在', bool(res.get('case_id')), str(res.get('case_id')))
    ck('status 合法', res.get('status') in ('ok', 'partial', 'insufficient_evidence', 'input_error'), str(res.get('status')))
    contract = contract_of(rj(wrk / 'index.json', {}) or {})
    miss = [f for f in contract_fields(contract) if f not in res]
    ck('契约字段齐全', not miss, '缺失=%s' % miss if miss else '%d 字段' % len(contract_fields(contract)))
    ledger = []
    lp = out / 'events' / 'event_ledger.jsonl'
    if lp.is_file():
        for line in lp.read_text(encoding='utf-8').splitlines():
            if line.strip():
                try:
                    ledger.append(json.loads(line))
                except Exception:
                    fails.append('ledger_line_unparsable')
    empty_ok = res.get('status') in ('insufficient_evidence', 'input_error')
    ck('台账可解析', bool(ledger) or empty_ok, '%d 条' % len(ledger))
    st = rj(out / 'derived' / 'trend_stats.json', {}) or {}
    rec = D.compute_stats([{'year': e.get('year'), 'event_type': e.get('event_type'), 'theme_id': e.get('theme_id')} for e in ledger])
    ck('台账-统计守恒', rec.get('by_year') == st.get('by_year'), '重算 %s vs 产物 %s' % (rec.get('by_year'), st.get('by_year')))
    ck('result.events=台账', len(res.get('events') or []) == len(ledger), '%d/%d' % (len(res.get('events') or []), len(ledger)))
    bad = [e.get('event_id') for e in ledger if not str(e.get('quote') or '').strip() or not str(e.get('locator') or '').strip()]
    ck('locator+quote 齐备', not bad, '缺=%s' % bad[:4] if bad else '')
    for f, mn in (('timeline.md', 200), ('trend_report.md', 200), ('figures/timeline.svg', 100), ('figures/figure_specs.json', 2), ('derived/stage_division.json', 2), ('derived/turning_points.json', 2), ('derived/gaps.json', 2)):
        p = out / f
        ck('产物非空 %s' % f, p.is_file() and p.stat().st_size > mn, '%d bytes' % (p.stat().st_size if p.is_file() else 0))
    idx = rj(wrk / 'index.json', {}) or {}
    if ledger and idx.get('paragraphs'):
        pm = {p['locator']: p['text'] for p in idx['paragraphs']}
        bad = []
        for e in ledger:
            t = pm.get(str(e.get('locator')))
            if t is None or C.norm(str(e.get('quote') or '')) not in C.norm(t):
                bad.append(e.get('event_id'))
        ck('quote 逐字命中', not bad, '未命中=%s' % bad[:5] if bad else '%d 条' % len(ledger))
    res.setdefault('self_check', {})['selfcheck'] = {'lines': lines, 'fails': fails, 'at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    try:
        (out / 'result.json').write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    return (lines, fails, res)
