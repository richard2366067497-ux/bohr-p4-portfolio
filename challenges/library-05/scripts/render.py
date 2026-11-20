"""reading-card-desk / render.py - layer artifacts and result.json assembly."""
import json, re
from pathlib import Path

from extract import J, now, norm, VERSION

SCHEMA = {'cards': 'reading-card-desk/cards@1', 'anchors': 'reading-card-desk/anchors@1',
          'graph': 'reading-card-desk/graph@1', 'index': 'reading-card-desk/library@1',
          'prov': 'reading-card-desk/provenance@1'}
KINDS = ('question', 'method', 'result', 'conclusion', 'reusable', 'to_verify')
STRENGTHS = ('strong', 'moderate', 'weak')
RELATIONS = ('same_method', 'same_quote', 'explicit_citation', 'contradicts', 'extends',
             'same_dataset', 'same_entity')

CONTRACT_MAP = [
    ('case_id', 'case_id'), ('status', 'status'), ('card', 'cards'), ('卡片', 'cards'),
    ('knowledge', 'cards'), ('anchor', 'anchors'), ('批注', 'anchors'), ('annot', 'anchors'),
    ('highlight', 'anchors'), ('evidence', 'anchors'), ('证据', 'anchors'), ('quote', 'anchors'),
    ('duplicate', 'versions'), ('alias', 'versions'), ('别名', 'versions'), ('重复', 'versions'),
    ('version', 'versions'), ('版本', 'versions'),
    ('retriev', 'retrieval'), ('search', 'retrieval'), ('question', 'retrieval'),
    ('query', 'retrieval'), ('检索', 'retrieval'), ('问题', 'retrieval'), ('view', 'retrieval'),
    ('graph', 'graph'), ('topic', 'topics'), ('主题', 'topics'), ('关联', 'graph'), ('link', 'graph'),
    ('coverage', 'coverage'), ('覆盖', 'coverage'), ('stat', 'coverage'), ('count', 'coverage'),
    ('provenance', 'provenance'), ('hash', 'provenance'), ('溯源', 'provenance'),
    ('reproduc', 'provenance'), ('复跑', 'provenance'),
    ('uncertain', 'uncertainties'), ('不确定', 'uncertainties'), ('error', 'errors'),
    ('degrad', 'degradations'), ('降级', 'degradations'), ('skip', 'skipped'), ('跳过', 'skipped'),
    ('recovery', 'recovery'), ('恢复', 'recovery'), ('log', 'operations'), ('operation', 'operations'),
    ('操作', 'operations'), ('change', 'changes'), ('变更', 'changes'),
    ('source', 'sources'), ('来源', 'sources'), ('artifact', 'artifacts'), ('产物', 'artifacts'),
    ('method', 'method_notes'), ('方法', 'method_notes'), ('note', 'method_notes'),
    ('说明', 'method_notes'), ('index', 'library'), ('library', 'library'), ('inventory', 'library'),
    ('清单', 'library'), ('file', 'library'), ('metadata', 'library'), ('资料', 'library'),
    ('目录', 'library'), ('result', 'result'), ('主结果', 'result'), ('output', 'result'),
]


def map_contract_key(k):
    kl = str(k).lower()
    for pat, target in CONTRACT_MAP:
        if pat in kl:
            return target
    return None


STOP = {'the', 'and', 'for', 'was', 'were', 'with', 'that', 'this', 'from', 'how', 'many',
        'used', 'are', 'not', 'but', 'its', 'their', 'which', 'per', 'did', 'does', 'has',
        'have', 'had', 'you', 'our', 'they', 'than', 'then', 'into', 'about', 'can', 'may'}


def terms(s):
    n = norm(s or '')
    ws = set(re.findall(r'[a-z0-9]{2,}', n)) - STOP
    cjk = ''.join(re.findall(r'[\u4e00-\u9fff]', n))
    gr = {cjk[i:i + 2] for i in range(len(cjk) - 1)}
    return ws | gr


def norm_draft(draft, lib):
    """defensively normalize the agent draft; never raises."""
    d = draft if isinstance(draft, dict) else {}
    anchor_idx = {a['anchor_id']: a for a in lib.get('anchors', [])}
    cards, ids = [], set()
    for i, c in enumerate(d.get('cards') or []):
        if not isinstance(c, dict):
            continue
        cid = str(c.get('card_id') or 'c%02d' % (i + 1))
        if cid in ids:
            cid = '%s-%d' % (cid, i + 1)
        ids.add(cid)
        aids = c.get('anchor_ids') or c.get('anchors') or []
        if isinstance(aids, str):
            aids = [aids]
        aids = [str(a) for a in aids if a]
        kind = str(c.get('kind') or 'to_verify').lower()
        if kind not in KINDS:
            kind = 'to_verify'
        st = str(c.get('strength') or '').lower()
        if st not in STRENGTHS:
            st = 'moderate' if aids else 'weak'
        status = str(c.get('status') or '').lower()
        cards.append({
            'card_id': cid, 'kind': kind, 'claim': (c.get('claim') or c.get('statement') or '').strip() or None,
            'anchor_ids': aids, 'source_version': c.get('source_version') or None,
            'strength': st, 'boundary': (c.get('boundary') or '').strip() or None,
            'reuse_hint': (c.get('reuse_hint') or '').strip() or None,
            'status': status if status in ('grounded', 'partial', 'unsupported') else None,
            'created_from': c.get('created_from') or 'agent_draft',
            'evidence_note': (c.get('evidence_note') or '').strip() or None,
            'counter_evidence': (c.get('counter_evidence') or '').strip() or None,
            'tags': c.get('tags') or [], 'topic': c.get('topic') or None,
            'missing': []})
    topics = []
    for t in (d.get('topics') or []):
        if isinstance(t, str):
            topics.append({'topic': t, 'card_ids': []})
        elif isinstance(t, dict):
            topics.append({'topic': str(t.get('topic') or t.get('name') or ''),
                           'card_ids': [str(x) for x in (t.get('card_ids') or [])]})
    edges = []
    for e in (d.get('topic_edges') or d.get('edges') or []):
        if not isinstance(e, dict):
            continue
        edges.append({'from': str(e.get('from') or e.get('source') or ''),
                      'to': str(e.get('to') or e.get('target') or ''),
                      'relation': str(e.get('relation') or 'same_quote'),
                      'basis': (e.get('basis') or '').strip(),
                      'confidence': e.get('confidence'),
                      'evidence_anchor_ids': e.get('evidence_anchor_ids') or []})
    qs = []
    for i, q in enumerate(d.get('questions') or []):
        if isinstance(q, str):
            qs.append({'question': q, 'card_ids': [], 'not_found_reason': None, 'id': 'q%d' % (i + 1)})
        elif isinstance(q, dict):
            qs.append({'id': str(q.get('id') or 'q%d' % (i + 1)),
                       'question': str(q.get('question') or q.get('query') or ''),
                       'card_ids': [str(x) for x in (q.get('card_ids') or [])],
                       'not_found_reason': q.get('not_found_reason')})
    return {'case_id': d.get('case_id'), 'cards': cards, 'topics': topics, 'edges': edges,
            'questions': qs, 'aliases': d.get('aliases') or [], 'skipped': d.get('skipped') or [],
            'notes': d.get('notes'), 'anchor_index': anchor_idx}


def _wl(p, lines):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in lines) + '\n',
                     encoding='utf-8')
        return True
    except Exception:
        return False


def retrieval(draft, lib, questions):
    """question -> cards via claim/quote/tag terms; explicit agent mapping wins."""
    out = []
    agent = {q['question']: q for q in draft.get('questions', []) if q.get('question')}
    for i, q in enumerate(questions):
        text = q.get('question') or ''
        qt = terms(text) | terms(q.get('topic') or '')
        hits = []
        if text in agent and agent[text].get('card_ids'):
            for cid in agent[text]['card_ids']:
                card = next((c for c in draft['cards'] if c['card_id'] == cid), None)
                if card:
                    hits.append({'card_id': cid, 'score': 1.0, 'matched_terms': [],
                                 'via': 'agent_mapping'})
        for c in draft['cards']:
            quoted = ' '.join((draft['anchor_index'].get(a, {}).get('quoted_text') or '')
                              for a in c['anchor_ids'])
            ct = terms(c['claim']) | terms(' '.join(map(str, c['tags']))) | terms(c['topic']) | terms(quoted)
            inter = qt & ct
            if not inter or not qt:
                continue
            sc = len(inter) / float(max(4, min(len(qt), 24)))
            if c['claim'] and (terms(c['claim']) & qt):
                sc += 0.15
            if sc >= 0.18 and not any(h['card_id'] == c['card_id'] for h in hits):
                hits.append({'card_id': c['card_id'], 'score': round(min(sc, 1.0), 3),
                             'matched_terms': sorted(inter)[:8], 'via': 'lexical'})
        hits.sort(key=lambda h: -h['score'])
        nfreason = agent.get(text, {}).get('not_found_reason')
        if not hits and not nfreason:
            nfreason = '库内卡片未覆盖该问题：建议回到 show 输出的锚点里补充 to_verify 卡，或标记为库外问题'
        out.append({'id': q.get('id') or 'q%d' % (i + 1), 'question': text, 'hits': hits[:5],
                    'hit_card_ids': [h['card_id'] for h in hits[:5]],
                    'not_found_reason': None if hits else nfreason,
                    'recall_note': 'lexical+agent mapping；术语重合不足以证明语义相关，命中需人工/引用复核'})
    return out


def graph(draft, lib):
    deg = {}
    nodes = [{'id': c['card_id'], 'type': 'card', 'kind': c['kind'], 'label': (c['claim'] or '')[:80],
              'status': c['status']} for c in draft['cards']]
    ids = {n['id'] for n in nodes}
    ok_edges, rejected = [], []
    for e in draft['edges']:
        if e['from'] not in ids or e['to'] not in ids:
            rejected.append(dict(e, reason='endpoint_missing'))
            continue
        if not e['basis'] or len(e['basis']) < 4:
            rejected.append(dict(e, reason='basis_missing'))
            continue
        deg[e['from']] = deg.get(e['from'], 0) + 1
        deg[e['to']] = deg.get(e['to'], 0) + 1
        ok_edges.append({'from': e['from'], 'to': e['to'],
                         'relation': e['relation'] if e['relation'] in RELATIONS else 'same_quote',
                         'basis': e['basis'], 'confidence': e['confidence'],
                         'evidence_anchor_ids': e['evidence_anchor_ids'], 'directed': False})
    for t in draft['topics']:
        if not t['topic']:
            continue
        tid = 't:' + t['topic']
        nodes.append({'id': tid, 'type': 'topic', 'kind': 'topic', 'label': t['topic'], 'status': 'topic'})
        ids.add(tid)
        for cid in t['card_ids']:
            if cid in ids:
                ok_edges.append({'from': cid, 'to': tid, 'relation': 'same_entity',
                                 'basis': '卡片的主题归属由工作稿显式声明（topic 字段或 topics[].card_ids）',
                                 'confidence': 0.9, 'evidence_anchor_ids': [], 'directed': False})
                deg[cid] = deg.get(cid, 0) + 1
    for n in nodes:
        n['degree'] = deg.get(n['id'], 0)
    over = [n['id'] for n in nodes if n['degree'] > 6]
    return {'schema': SCHEMA['graph'], 'nodes': nodes, 'edges': ok_edges, 'rejected_edges': rejected,
            'over_connected': over,
            'stats': {'nodes': len(nodes), 'edges': len(ok_edges),
                      'avg_degree': round(sum(n['degree'] for n in nodes) / float(max(1, len(nodes))), 3),
                      'max_degree': max([n['degree'] for n in nodes] or [0])}}


def _md_escape(s):
    return (str(s or '')).replace('|', '\\|').replace('\n', ' ')


def write_all(out, work, lib, draft, check, prov_extra=None):
    out = Path(out)
    arts, anchors, cards = [], lib.get('anchors', []), draft.get('cards', [])
    qs = lib.get('questions', [])
    ret, g = retrieval(draft, lib, qs), graph(draft, lib)

    def rel(p):
        try:
            return str(Path(p).relative_to(out))
        except Exception:
            return str(p)

    rows = []
    for c in cards:
        c['status'] = c.get('status') or ('grounded' if (c['claim'] and c['anchor_ids'] and c['boundary']) else 'partial')
        row = {k: v for k, v in c.items() if k != 'missing'}
        row['schema'] = SCHEMA['cards']
        row['anchor_refs'] = [{'anchor_id': a, 'file': draft['anchor_index'].get(a, {}).get('file'),
                               'locator': draft['anchor_index'].get(a, {}).get('locator'),
                               'quoted_text': draft['anchor_index'].get(a, {}).get('quoted_text')}
                              for a in c['anchor_ids']]
        rows.append(row)
    for path, data in ((out / 'cards' / 'knowledge_cards.jsonl', rows),
                       (out / 'anchors' / 'anchor_ledger.jsonl',
                        [dict(a, schema=SCHEMA['anchors']) for a in anchors])):
        if _wl(path, data):
            arts.append(rel(path))
    J(out / 'views' / 'topic_graph.json', g)
    arts.append(rel(out / 'views' / 'topic_graph.json'))
    ti = {'schema': SCHEMA['graph'], 'by_kind': {}, 'by_tag': {}, 'by_doc': {}, 'by_anchor': {}, 'by_topic': {}}
    for c in cards:
        ti['by_kind'].setdefault(c['kind'], []).append(c['card_id'])
        for t in (c['tags'] or []):
            ti['by_tag'].setdefault(str(t), []).append(c['card_id'])
        if c.get('topic'):
            ti['by_topic'].setdefault(c['topic'], []).append(c['card_id'])
        for a in c['anchor_ids']:
            ti['by_anchor'].setdefault(a, []).append(c['card_id'])
            d = draft['anchor_index'].get(a, {}).get('doc_id')
            if d and c['card_id'] not in ti['by_doc'].setdefault(d, []):
                ti['by_doc'][d].append(c['card_id'])
    for t in draft['topics']:
        ti['by_topic'].setdefault(t['topic'], []).extend(t['card_ids'])
    J(out / 'views' / 'topic_index.json', ti)
    arts.append(rel(out / 'views' / 'topic_index.json'))

    J(out / 'library_index.json', {'schema': SCHEMA['index'], 'generated': lib.get('generated'),
                                   'case_id': lib.get('case_id'), 'stats': lib.get('stats'),
                                   'documents': [_doc_view(d) for d in lib.get('documents', [])],
                                   'groups': lib.get('groups', []), 'aliases': lib.get('aliases', []),
                                   'version_notes': lib.get('version_notes', []),
                                   'annotation_exports': lib.get('exports', []),
                                   'metadata_files': [m.get('file') for m in lib.get('metadata', [])],
                                   'permissions': [{'file': d['file'], 'readable': d.get('readable', True)}
                                                   for d in lib.get('documents', [])]})
    arts.append(rel(out / 'library_index.json'))

    L = ['# 检索视图：问题 → 知识卡 → 锚点', '',
         '> %s · 脚本 %s · 案例 `%s`' % (now(), VERSION, lib.get('case_id')), '',
         '命中依据：工作稿显式映射(1.0)优先，其余按词面重合+claim 加成打分(阈值 0.18)；',
         '词面重合只是"值得看"的线索，不构成语义相关证明，每条命中给出可回查定位。', '']
    if not qs:
        L += ['## 案例未提供问题', '', '只列出按主题的可检索入口：', '']
        L += ['- 主题 **%s** → %s' % (t['topic'], ', '.join(t['card_ids']) or '（无卡）')
              for t in draft['topics']] or ['- （工作稿未声明主题）']
    for r in ret:
        L += ['## %s. %s' % (r['id'], r['question'] or '（空问题）'), '']
        if not r['hits']:
            L += ['**未命中**。原因：%s' % (r['not_found_reason'] or '未说明'), '']
            continue
        L += ['| 卡 | 分数 | 依据 | 卡片判断 |', '|---|---|---|---|']
        for h in r['hits']:
            c = next((x for x in cards if x['card_id'] == h['card_id']), {})
            L.append('| %s | %.3f | %s | %s |' % (h['card_id'], h['score'],
                     h['via'] + ('' if not h['matched_terms'] else ':' + ','.join(h['matched_terms'])),
                     _md_escape((c.get('claim') or '')[:90])))
        L.append('')
        for h in r['hits'][:3]:
            c = next((x for x in cards if x['card_id'] == h['card_id']), {})
            for a in c.get('anchor_ids', [])[:2]:
                an = draft['anchor_index'].get(a, {})
                L.append('- `%s` → %s · %s · 「%s」' % (a, an.get('file'), an.get('locator'),
                          _md_escape((an.get('quoted_text') or '')[:110])))
        L.append('')
    L += ['## 召回不足与误召回的处理', '',
          '- 召回不足：未命中问题写 `to_verify` 卡并在 `not_found_reason` 说明缺什么材料；',
          '- 误召回：`boundary` 写适用条件，`matched_terms` 供人判断是否词面撞车；',
          '- 单一术语重合不建图边（见 rejected_edges）。', '']
    (out / 'views').mkdir(parents=True, exist_ok=True)
    (out / 'views' / 'retrieval_view.md').write_text('\n'.join(L), encoding='utf-8')
    arts.append(rel(out / 'views' / 'retrieval_view.md'))

    D = ['# 知识卡工作台 · %s' % lib.get('case_id'), '',
         '- %s（脚本 %s）｜资料 %d 篇（解析 %d）· 页 %d · 锚点 %d（逐字命中 %d）· 卡 %d' % (
             now(), VERSION, lib['stats'].get('docs_found', 0), lib['stats'].get('docs_processed', 0),
             lib['stats'].get('pages', 0), lib['stats'].get('anchors', 0),
             lib['stats'].get('anchors_verified', 0), len(cards)),
         '- 状态：**%s**（缺口见文末与 `provenance/skipped.json`）' % check.get('status', 'partial'), '',
         '## 1. 卡片总表', '', '| 卡 | 类型 | 判断 | 强度 | 锚点 | 状态 |', '|---|---|---|---|---|---|']
    D += ['| %s | %s | %s | %s | %d | %s |' % (c['card_id'], c['kind'],
          _md_escape((c['claim'] or '（无判断）')[:100]), c['strength'], len(c['anchor_ids']), c['status'])
          for c in cards]
    D += ['', '## 2. 卡片明细与原文锚点', '']
    for c in cards:
        D += ['### %s · %s' % (c['card_id'], c['kind']), '',
              '**判断**：%s' % (c['claim'] or '（未填写判断）'), '',
              '- 强度 %s ｜ 状态 %s ｜ 边界：%s' % (c['strength'], c['status'], c['boundary'] or '未声明'),
              '- 复用：%s' % (c['reuse_hint'] or '未声明')]
        for f, lab in (('counter_evidence', '反向'), ('evidence_note', '证据')):
            if c.get(f):
                D.append('- %s：%s' % (lab, c[f]))
        for a in c['anchor_ids']:
            an = draft['anchor_index'].get(a, {})
            D += ['  - `%s` %s · %s · %s/%s · %s（%s，%s）' % (
                a, an.get('file'), an.get('locator'), an.get('type'), an.get('source_version'),
                an.get('color'), an.get('color_meaning'), an.get('color_meaning_source')),
                '    > 「%s」' % _md_escape((an.get('quoted_text') or '（无原文）')[:240])]
            if an.get('note'):
                D.append('    > 批注：%s' % _md_escape(an['note'][:180]))
        D.append('')
    D += ['## 3. 资料清单与版本关系', '', '| 文件 | 类型 | 页/字符 | 版本 | canon | 文本层 |', '|---|---|---|---|---|---|']
    D += ['| %s | %s | %s/%s | %s | %s | %s |' % (d['file'], d.get('kind'), d.get('pages_n'),
          d.get('chars'), d.get('version_label'), 'Y' if d.get('is_canonical') else '',
          d.get('text_layer')) for d in lib.get('documents', [])]
    for g2 in lib.get('groups', []):
        if len(g2['members']) > 1:
            D += ['', '- **%s**（%s）：canonical = `%s`；成员 %s' % (
                g2['work_id'], g2['relation'], g2['canonical_file'],
                ', '.join('%s(%s)' % (m['file'], m['version']) for m in g2['members']))]
    D += ['', '## 4. 跳过与降级', '']
    D += ['- `%s` — %s：%s' % (s.get('file'), s.get('reason'), s.get('detail'))
          for s in lib.get('skipped', [])[:80]] or ['- 无']
    D += ['', '## 5. 复核方式', '',
          '1. `show --anchor <id>` 打印该锚点所在页原文；',
          '2. 卡片判断须能追到上列引文；判断由工作稿作者写下，非脚本生成；',
          '3. `provenance/provenance.json` 给出输入哈希与版本，可复跑比对。', '']
    (out / 'card_desk.md').write_text('\n'.join(D), encoding='utf-8')
    arts.append(rel(out / 'card_desk.md'))

    inputs = [{'file': d['file'], 'sha256': d.get('sha256'), 'bytes': d.get('bytes'),
               'kind': d.get('kind'), 'readable': d.get('readable', True)}
              for d in lib.get('documents', [])]
    inputs += [{'file': m.get('file'), 'sha256': None, 'bytes': None, 'kind': 'annotation_export'}
               for m in lib.get('exports', [])]
    prov = {'schema': SCHEMA['prov'], 'generated': now(), 'script_version': VERSION,
            'schema_version': 1, 'case_id': lib.get('case_id'), 'inputs': inputs,
            'input_count': len(inputs), 'params': (prov_extra or {}).get('params', {}),
            'anchor_id_rule': 'a-<sha256[:8]>-p<page>-<ordinal per page>（内容定址，可跨机复跑）',
            'counts': lib.get('stats', {}), 'coverage': (prov_extra or {}).get('coverage', {}),
            'gate_results': check.get('gates', {}),
            'determinism': (prov_extra or {}).get('determinism', {'checked': False})}
    J(out / 'provenance' / 'provenance.json', prov)
    arts.append(rel(out / 'provenance' / 'provenance.json'))
    J(out / 'provenance' / 'skipped.json',
      {'schema': SCHEMA['prov'], 'items': lib.get('skipped', []),
       'counts': {r: sum(1 for s in lib.get('skipped', []) if s.get('reason') == r)
                  for r in sorted({s.get('reason') for s in lib.get('skipped', [])})}})
    arts.append(rel(out / 'provenance' / 'skipped.json'))
    _wl(out / 'provenance' / 'operation_log.jsonl',
        [{'ts': now(), 'step': 'parse', 'detail': l} for l in lib.get('log', [])] +
        [{'ts': now(), 'step': 'index', 'detail': {'docs': lib['stats'].get('docs_found'),
                                                   'anchors': lib['stats'].get('anchors')}},
         {'ts': now(), 'step': 'check', 'detail': {'status': check.get('status'),
                                                   'errors': len(check.get('errors', []))}},
         {'ts': now(), 'step': 'render', 'detail': {'artifacts': len(arts)}}])
    arts.append(rel(out / 'provenance' / 'operation_log.jsonl'))
    _wl(out / 'provenance' / 'recovery_log.jsonl',
        [dict(r, ts=now()) for r in lib.get('recovery', [])] +
        [dict(a, ts=now(), action='alias_resolved') for a in lib.get('aliases', [])] +
        [{'ts': now(), 'action': 'skip_recorded', 'file': s.get('file'), 'reason': s.get('reason')}
         for s in lib.get('skipped', [])])
    arts.append(rel(out / 'provenance' / 'recovery_log.jsonl'))
    return {'artifacts': sorted(set(arts)), 'retrieval': ret, 'graph': g, 'provenance': prov}


def _doc_view(d):
    return {'doc_id': d.get('doc_id'), 'file': d.get('file'), 'kind': d.get('kind'),
            'ext': d.get('ext'), 'bytes': d.get('bytes'), 'sha256': d.get('sha256'),
            'pages': d.get('pages_n'), 'chars': d.get('chars'), 'text_layer': d.get('text_layer'),
            'title': d.get('title'), 'authors': d.get('authors'), 'doi': d.get('doi'),
            'year': d.get('year'), 'mtime': d.get('mtime'), 'readable': d.get('readable'),
            'work_id': d.get('work_id'), 'version': d.get('version_label'),
            'is_canonical': d.get('is_canonical'), 'version_notes': d.get('admin_notes') or [],
            'revisions': len(d.get('revisions') or []),
            'annotation_candidates': len(d.get('annots_raw') or []),
            'url': d.get('url')}


def build_result(case_id, contract, vals, env):
    """backfill every contract key (never rename, never drop) + envelope."""
    res = {}
    unmapped = []
    if not contract:
        for k in ('cards', 'anchors', 'library', 'versions', 'retrieval', 'coverage', 'graph',
                  'topics', 'skipped', 'recovery', 'operations', 'provenance'):
            res[k] = vals.get(k)
    for k in (contract or {}).keys():
        tgt = map_contract_key(k)
        if tgt is None:
            res[k] = None
            unmapped.append(k)
        else:
            res[k] = vals.get(tgt)
    for k, v in (env or {}).items():
        res.setdefault(k, v)
    for k in ('result', 'cards', 'anchors', 'library', 'versions', 'retrieval', 'coverage',
              'graph', 'topics', 'skipped', 'recovery', 'operations', 'provenance',
              'artifacts', 'method_notes'):
        if res.get(k) is None and vals.get(k) is not None:
            res[k] = vals.get(k)
    for k in ('case_id', 'status', 'result', 'sources', 'errors', 'degradations',
              'uncertainties', 'changes', 'runtime'):
        res.setdefault(k, [] if k in ('sources', 'errors', 'degradations', 'uncertainties', 'changes') else None)
    if isinstance(res.get('result'), dict):
        res['result'].setdefault('gates', (res.get('provenance') or {}).get('gate_results'))
    for k in ('sources', 'errors', 'degradations', 'uncertainties', 'changes', 'skipped'):
        v = res.get(k)
        if isinstance(v, list):
            out = []
            for x in v:
                if not isinstance(x, dict):
                    out.append({'kind': 'note', 'detail': str(x)[:300]})
                    continue
                if 'kind' not in x:
                    x = dict(x, kind=x.get('code') or x.get('reason') or 'note')
                out.append(x)
            res[k] = out
        elif v is None:
            res[k] = []
    res['case_id'] = case_id
    res['_contract_keys'] = list((contract or {}).keys())
    res['_contract_unmapped'] = unmapped
    return res
