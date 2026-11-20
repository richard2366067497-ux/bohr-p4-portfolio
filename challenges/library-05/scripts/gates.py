"""reading-card-desk / gates.py - the five gates (G1..G5) and gate-derived views."""
import extract as E
import render as R

GATES = ('G1_anchor', 'G2_card', 'G3_edge', 'G4_retrieval', 'G5_repro')
VERSION = E.VERSION


def log(msg):
    try:
        print(msg)
    except Exception:
        pass


def check_draft(idx, draft, has_draft=True, draft_err=None):
    anchors = idx.get('anchors', [])
    aidx = {a['anchor_id']: a for a in anchors}
    docs = {d['doc_id']: d for d in idx.get('documents', [])}
    errs, warns, gates = [], [], {}

    def rec(bucket, code, gate, detail, ref=None):
        bucket.append({'code': code, 'gate': gate, 'detail': detail, 'ref': ref})

    def err(code, gate, detail, ref=None):
        rec(errs, code, gate, detail, ref)

    def warn(code, gate, detail, ref=None):
        rec(warns, code, gate, detail, ref)

    g1 = 0
    for a in anchors:
        if not a.get('quoted_text'):
            err('A101', 'G1', '锚点缺 quoted_text', a['anchor_id'])
            g1 += 1
        if a.get('type') not in E.TYPES:
            err('A103', 'G1', '批注类型不在词典：%s' % a.get('type'), a['anchor_id'])
            g1 += 1
        if not a.get('page_physical') or not a.get('locator'):
            err('A104', 'G1', '缺 page_physical 或 locator', a['anchor_id'])
            g1 += 1
        q = E.norm(a.get('quoted_text') or '')
        if not q:
            continue
        hit = None
        for pg in (docs.get(a.get('doc_id')) or {}).get('pages') or []:
            if pg.get('p') == a.get('page_physical') and a.get('char_start') is not None:
                if E.norm((pg.get('norm') or '')[a['char_start']:a.get('char_end') or 0]) == q:
                    hit = pg['p']
                    break
            if q in (pg.get('norm') or ''):
                hit = pg['p']
                break
        if hit is None:
            a['quote_verified'] = 'unverified_after_check'
            err('A102', 'G1', 'quoted_text 未在该文件任何页逐字命中', a['anchor_id'])
            g1 += 1
        else:
            a['quote_verified'] = 'exact'
            if a.get('page_physical') != hit:
                a['page_physical'] = hit
                warn('A104', 'G1', '页码按逐字命中修正为 p%s' % hit, a['anchor_id'])
        if (a.get('anchor_confidence') or 0) < .5:
            warn('A105', 'G1', '低置信锚点 %.2f' % (a.get('anchor_confidence') or 0), a['anchor_id'])
    gates['G1_anchor'] = {'status': 'FAIL' if g1 else ('WARN' if warns else 'PASS'),
                          'anchors': len(anchors),
                          'verified': sum(1 for a in anchors if a.get('quote_verified') == 'exact'),
                          'low_confidence': sum(1 for a in anchors if (a.get('anchor_confidence') or 0) < .5)}

    cards = draft.get('cards', [])
    quotes = {E.norm(a.get('quoted_text') or '') for a in anchors if a.get('quoted_text')}
    if not cards:
        err('C201', 'G2', '工作稿没有卡片：%s' % (draft_err or 'cards=[]'))
    g2, order = 0, {'unsupported': 0, 'partial': 1, 'grounded': 2}
    for c in cards:
        miss = set(c.get('missing', []))
        if not c.get('claim'):
            miss.add('claim')
            err('C201', 'G2', '卡片缺 claim（判断）', c['card_id'])
            g2 += 1
        if not c.get('anchor_ids'):
            miss.add('anchor_ids')
            err('C201', 'G2', '卡片没有锚点', c['card_id'])
            g2 += 1
        for a in c.get('anchor_ids', []):
            if a not in aidx:
                miss.add('anchor:' + a)
                err('C205', 'G2', '引用了不存在的锚点 %s' % a, c['card_id'])
                g2 += 1
        cq = E.norm(c.get('claim') or '')
        if cq and (cq in quotes or len(cq) < 12):
            err('C203', 'G2', 'claim 等于原文摘抄或过短（须为判断）', c['card_id'])
            g2 += 1
        if not c.get('boundary') or not c.get('strength'):
            miss.update([x for x in ('boundary', 'strength') if not c.get(x)])
            err('C204', 'G2', '缺 boundary 或 strength', c['card_id'])
            g2 += 1
        verified = [a for a in c.get('anchor_ids', []) if aidx.get(a, {}).get('quote_verified') == 'exact']
        computed = ('grounded' if (c.get('claim') and verified and c.get('boundary') and c.get('strength'))
                    else ('unsupported' if not (verified and c.get('claim')) else 'partial'))
        agent = c.get('status') or computed
        c['status'] = agent if order.get(agent, 1) <= order.get(computed, 1) else computed
        c['missing'] = sorted(miss)
    gates['G2_card'] = {'status': 'FAIL' if g2 else 'PASS', 'cards': len(cards),
                        'grounded': sum(1 for c in cards if c.get('status') == 'grounded'),
                        'partial': sum(1 for c in cards if c.get('status') == 'partial'),
                        'unsupported': sum(1 for c in cards if c.get('status') == 'unsupported')}

    g = R.graph(draft, idx)
    g3 = 0
    for e in g.get('rejected_edges', []):
        err('E301', 'G3', '边被拒：%s（%s→%s）' % (e.get('reason'), e.get('from'), e.get('to')), e.get('from'))
        g3 += 1
    deg = {n['id']: n['degree'] for n in g['nodes']}
    for nid in g.get('over_connected', []):
        err('E302', 'G3', '过连接：%s 度数 %s > 6' % (nid, deg.get(nid, '?')), nid)
        g3 += 1
    for e in g.get('edges', []):
        if e['relation'] not in R.RELATIONS:
            err('E303', 'G3', '关系类型不在词典：%s' % e['relation'], e['from'])
            g3 += 1
    gates['G3_edge'] = {'status': 'FAIL' if g3 else 'PASS', 'edges': len(g.get('edges', [])),
                        'rejected': len(g.get('rejected_edges', []))}

    ret = R.retrieval(draft, idx, idx.get('questions', []))
    g4 = 0
    ids = {c['card_id'] for c in cards}
    if idx.get('questions') and not draft.get('questions'):
        warn('Q401', 'G4', '案例有 %d 个问题，工作稿未显式映射（已按词面自动检索）' % len(idx['questions']))
    for r in ret:
        for cid in r['hit_card_ids']:
            if cid not in ids:
                err('Q402', 'G4', '命中卡不存在：%s' % cid, r['id'])
                g4 += 1
        if not r['hits'] and not r.get('not_found_reason'):
            err('Q403', 'G4', '问题无命中且未写 not_found_reason', r['id'])
            g4 += 1
    gates['G4_retrieval'] = {'status': 'FAIL' if g4 else ('WARN' if idx.get('questions') and not draft.get('questions') else 'PASS'),
                             'questions': len(ret), 'hit': sum(1 for r in ret if r['hits'])}

    g5 = 0
    if not any(d.get('sha256') for d in idx.get('documents', [])):
        err('P501', 'G5', '没有任何输入哈希')
        g5 += 1
    if not VERSION:
        err('P502', 'G5', '缺脚本版本')
        g5 += 1
    gates['G5_repro'] = {'status': 'FAIL' if g5 else 'PASS', 'script_version': VERSION,
                         'hashed_inputs': sum(1 for d in idx.get('documents', []) if d.get('sha256'))}

    if not has_draft:
        warn('C201', 'G2', '工作稿缺失/不可用：%s' % (draft_err or 'draft_missing'))
    status = 'partial' if (errs or warns) else 'ok'
    if not anchors and not cards:
        status = 'partial'
    return {'status': status, 'errors': errs, 'warnings': warns, 'gates': gates,
            'cards': cards, 'retrieval': ret, 'graph': g, 'has_draft': has_draft,
            'draft_error': draft_err}

def print_check(chk, quiet=False):
    if quiet:
        return
    log('check: status=%s  errors=%d warnings=%d' % (chk['status'], len(chk['errors']),
                                                     len(chk['warnings'])))
    for gname in GATES:
        g = chk['gates'].get(gname, {})
        extra = ' '.join('%s=%s' % (k, v) for k, v in g.items() if k != 'status')
        log('  [%s] %-10s %s' % (gname.split('_')[0], g.get('status', '?'), extra))
    seen = set()
    for e in chk['errors'][:40]:
        k = (e['code'], e['detail'])
        if k in seen:
            continue
        seen.add(k)
        log('  ! %s %s (%s)' % (e['code'], e['detail'], e['ref']))
    for w in chk['warnings'][:12]:
        log('  ~ %s %s' % (w['code'], w['detail']))

def coverage(idx, chk):
    st = idx.get('stats', {})
    cards = chk.get('cards', [])
    return {'docs_expected': st.get('docs_found', 0), 'docs_processed': st.get('docs_processed', 0),
            'docs_skipped': len({s.get('file') for s in idx.get('skipped', [])}),
            'pages': st.get('pages', 0), 'anchors_extracted': len(idx.get('anchors', [])),
            'anchors_verified': st.get('anchors_verified', 0),
            'anchors_low_confidence': st.get('anchors_low_conf', 0),
            'cards_total': len(cards),
            'cards_grounded': sum(1 for c in cards if c.get('status') == 'grounded'),
            'cards_partial': sum(1 for c in cards if c.get('status') == 'partial'),
            'cards_unsupported': sum(1 for c in cards if c.get('status') == 'unsupported'),
            'questions': len(idx.get('questions', [])),
            'questions_hit': len(chk.get('retrieval', [])),
            'duplicate_files': st.get('duplicates', 0),
            'version_groups': st.get('version_groups', 0),
            'annotation_exports': st.get('annotation_exports', 0)}

def uncertainties(idx, chk):
    out = []
    for s in idx.get('skipped', []):
        out.append({'kind': s.get('reason'), 'file': s.get('file'), 'detail': s.get('detail'),
                    'action_required': 'none' if s.get('reason') in ('low_confidence',) else
                    '补充可读文本/批注导出，或由人确认该文件可忽略'})
    for c in chk.get('cards', []):
        if c.get('status') in ('partial', 'unsupported'):
            out.append({'kind': 'card_%s' % c.get('status'), 'card_id': c.get('card_id'),
                        'detail': '缺 %s' % ','.join(c.get('missing') or ['证据/边界']) if c.get('missing')
                        else '证据未全部通过逐字校验'})
    for c in chk.get('cards', []):
        if c.get('counter_evidence'):
            out.append({'kind': 'conflict_declared', 'card_id': c.get('card_id'),
                        'detail': c['counter_evidence']})
    return out