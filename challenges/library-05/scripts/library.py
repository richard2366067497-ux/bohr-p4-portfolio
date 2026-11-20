"""reading-card-desk / library.py - library model: discovery, assembly, dedup,."""
import json, os, re
from pathlib import Path

import extract as E
from extract import (now, norm, norm_map, sha256_file, clean, text_quality, color_name,
                     pdf_parse, docx_parse, html_parse, text_parse, align_quad,
                     COLORS, SUBTYPE_MAP)
from versions import group_versions
from extract import legend_lookup, _hex, _parse_color

SCHEMA_INDEX = 'reading-card-desk/index@1'
SKIP_NAMES = {'task.md', 'case.json', 'output-contract.md', 'output_contract.md',
              'guide.md', 'submission.json', 'resources.yaml', 'manifest.json'}
SKIP_DIRS = {'environment', '__pycache__', '.git', '.ipynb_checkpoints', 'node_modules'}
ANN_KEYS = ('annotations', 'annots', 'items', 'records', 'data', 'highlights', 'notes')


def _pick(d, keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    low = {kk.lower(): vv for kk, vv in d.items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ''):
            return v
    return default


def _ann_list(o):
    if isinstance(o, list):
        return [x for x in o if isinstance(x, dict)]
    if isinstance(o, dict):
        for k in ANN_KEYS:
            if isinstance(o.get(k), list):
                return [x for x in o[k] if isinstance(x, dict)]
        out = []
        for k, v in o.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for x in v:
                    if isinstance(x, dict):
                        y = dict(x)
                        y.setdefault('file', k)
                        out.append(y)
        return out
    return []


def _kind_of(p, head):
    ext = p.suffix.lower()
    if head[:5] == b'%PDF-':
        return 'pdf'
    if head[:2] == b'PK':
        try:
            import zipfile
            with zipfile.ZipFile(p) as z:
                return 'docx' if 'word/document.xml' in z.namelist() else 'zip'
        except Exception:
            return 'zip'
    h = head[:4096].lower()
    if b'<html' in h or b'<!doctype html' in h or ext in ('.htm', '.html'):
        return 'html'
    if ext == '.json':
        return 'json'
    if ext in ('.md', '.markdown', '.txt', '.rst', '.tex', '.csv', '.tsv', '.yaml', '.yml'):
        return 'text'
    return 'text' if text_quality(E.dec(head)) != 'empty' else 'binary'


def scan_materials(inp):
    recs, seen = [], set()
    for root, dirs, files in os.walk(str(inp)):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
        for fn in sorted(files):
            p = Path(root) / fn
            if fn.lower() in SKIP_NAMES or fn.startswith('.') or fn.endswith(('.pyc', '.tmp')):
                continue
            try:
                rel = str(p.relative_to(inp))
            except Exception:
                rel = fn
            if rel in seen or len(recs) >= 300:
                continue
            seen.add(rel)
            try:
                st = p.stat()
                if st.st_size > E.SIZE_CAP:
                    recs.append({'path': str(p), 'rel': rel, 'kind': 'too_large', 'bytes': st.st_size,
                                 'sha256': None, 'readable': False, 'note': 'size_cap'})
                    continue
                with open(p, 'rb') as f:
                    head = f.read(4096)
                recs.append({'path': str(p), 'rel': rel, 'kind': _kind_of(p, head),
                             'bytes': st.st_size, 'mtime': int(st.st_mtime),
                             'sha256': sha256_file(p), 'readable': os.access(p, os.R_OK)})
            except OSError as e:
                recs.append({'path': str(p), 'rel': rel, 'kind': 'unreadable', 'bytes': 0,
                             'sha256': None, 'readable': False,
                             'note': 'errno:%s' % getattr(e, 'errno', '?')})
    return recs


def _salvage_case(raw):
    """salvage case_id and output_contract key names from a malformed case.json."""
    if not raw:
        return {}
    out = {}
    m = re.search(r'"case_id"\s*:\s*"([^"]+)"', raw)
    if m:
        out['case_id'] = m.group(1)
    m = re.search(r'"output_contract"\s*:\s*\{(.*)', raw, re.S)
    if m:
        keys, depth, seg = [], 0, m.group(1)
        for km in re.finditer(r'"([^"]{1,60})"\s*:', seg):
            k = km.group(1)
            if k not in keys and k not in ('output_contract',):
                keys.append(k)
            if len(keys) >= 40:
                break
        if keys:
            out['output_contract'] = {k: None for k in keys}
    return out


def _questions(qs):
    if isinstance(qs, dict):
        qs = [dict(v, id=k) if isinstance(v, dict) else {'id': k, 'question': v} for k, v in qs.items()]
    out = []
    for i, q in enumerate(qs if isinstance(qs, list) else []):
        if isinstance(q, str):
            out.append({'id': 'q%d' % (i + 1), 'question': q, 'topic': None})
        elif isinstance(q, dict):
            out.append({'id': str(_pick(q, ['id', 'qid', 'key'], 'q%d' % (i + 1))),
                        'question': str(_pick(q, ['question', 'query', 'text', 'q', 'search'], '')),
                        'topic': _pick(q, ['topic', 'tag', 'theme'], None)})
    return [q for q in out if q['question']]


def _aliases(al):
    out = []
    if isinstance(al, dict):
        return [{'alias': str(k), 'canonical': str(v)} for k, v in al.items()]
    for a in al if isinstance(al, list) else []:
        if isinstance(a, dict):
            out.append({'alias': str(_pick(a, ['alias', 'from', 'name'], '')),
                        'canonical': str(_pick(a, ['canonical', 'to', 'target'], ''))})
        elif isinstance(a, str) and '=' in a:
            k, v = a.split('=', 1)
            out.append({'alias': k.strip(), 'canonical': v.strip()})
    return [a for a in out if a['alias'] and a['canonical']]


def _notes(vn):
    if isinstance(vn, dict):
        return [{'ref': str(k), 'note': str(v)} for k, v in vn.items()]
    out = []
    for v in vn if isinstance(vn, list) else []:
        if isinstance(v, dict):
            out.append({'ref': str(_pick(v, ['file', 'doc', 'doc_id', 'ref', 'name'], '')),
                        'note': str(_pick(v, ['note', 'text', 'description', 'comment'], v))})
        elif isinstance(v, str):
            out.append({'ref': '', 'note': v})
    return out


def discover(inp):
    inp = Path(inp)
    ctx = {'input_dir': str(inp), 'case': {}, 'case_id': 'UNKNOWN-CASE', 'task': '',
           'contract': {}, 'questions': [], 'topics': [], 'aliases': [], 'version_notes': [],
           'legend': {}, 'errors': [], 'materials': []}
    for c in [inp / 'case.json'] + sorted(inp.rglob('case*.json'))[:3]:
        if not c.exists():
            continue
        raw = ''
        try:
            raw = c.read_text(encoding='utf-8', errors='replace')
            ctx['case'] = json.loads(raw)
            break
        except Exception as e:
            ctx['errors'].append({'kind': 'case_json_invalid',
                                  'detail': '%s: %s' % (c.name, str(e)[:120])})
            ctx['case'] = _salvage_case(raw)
            if ctx['case']:
                ctx['errors'].append({'kind': 'case_json_salvaged',
                                      'detail': 'JSON 非法，已抢救 case_id 与契约键名'})
            break
    case = ctx['case'] if isinstance(ctx['case'], dict) else {}
    ctx['case_id'] = str(_pick(case, ['case_id', 'caseId', 'id', 'case'], None) or 'UNKNOWN-CASE')
    ctx['task'] = str(_pick(case, ['task_instruction', 'instruction', 'task', 'question',
                                   'prompt'], '') or '')
    if not ctx['task']:
        for t in [inp / 'task.md'] + sorted(inp.glob('*task*.md'))[:2]:
            try:
                if t.exists():
                    ctx['task'] = t.read_text(encoding='utf-8', errors='replace')[:8000]
                    break
            except Exception:
                pass
    ct = _pick(case, ['output_contract', 'outputContract', 'contract'], {}) or {}
    ctx['contract'] = ct if isinstance(ct, dict) else {'value': ct}
    ctx['questions'] = _questions(_pick(case, ['questions', 'searches', 'queries',
                                               'retrieval_questions', 'tasks'], []))
    tp = _pick(case, ['topics', 'themes', 'labels'], [])
    ctx['topics'] = [t if isinstance(t, str) else str(_pick(t, ['topic', 'name', 'title'], t))
                     for t in tp] if isinstance(tp, list) else []
    ctx['aliases'] = _aliases(_pick(case, ['aliases', 'alias_map', 'alias'], []))
    ctx['version_notes'] = _notes(_pick(case, ['version_notes', 'administrative_notes',
                                               'version_relations'], []))
    lg = _pick(case, ['color_legend', 'legend', 'color_meanings'], {}) or {}
    ctx['legend'] = lg if isinstance(lg, dict) else {}
    ctx['materials'] = scan_materials(inp)
    if not ctx['materials']:
        ctx['errors'].append({'kind': 'no_material', 'detail': '未发现材料文件'})
    return ctx


def make_doc(rec, inp):
    p = Path(rec['path'])
    doc = {'doc_id': 'd' + (rec.get('sha256') or 'nohash')[:10], 'file': rec['rel'],
           'path': str(p), 'ext': p.suffix.lower(), 'kind': rec['kind'],
           'bytes': rec.get('bytes'), 'sha256': rec.get('sha256'), 'mtime': rec.get('mtime'),
           'readable': rec.get('readable', True), 'pages': [], 'paras': [], 'title': None,
           'authors': [], 'doi': None, 'year': None, 'text_layer': 'none', 'notes': [],
           'revisions': [], 'garbled_pages': 0, 'encrypted': False, 'annots_raw': []}
    if not doc['readable']:
        doc['notes'].append('permission_denied')
        return doc
    try:
        raw = p.read_bytes() if (doc['bytes'] or 0) <= E.SIZE_CAP else b''
    except OSError as e:
        doc['notes'].append('read_failed:errno%s' % getattr(e, 'errno', '?'))
        return doc
    try:
        if doc['kind'] == 'pdf':
            pr = pdf_parse(p, raw)
            doc['pages'] = pr['pages']
            doc['encrypted'] = pr['encrypted']
            doc['garbled_pages'] = pr['garbled_pages']
            doc['notes'] += pr['notes']
            if pr['encrypted']:
                doc['notes'].append('encrypted_pdf')
            doc['annots_raw'] = [{'source': 'pdf_annots', 'page': a['page'],
                                  'type': SUBTYPE_MAP[a['subtype']], 'subtype': a['subtype'],
                                  'note': a['note'], 'author': a['author'], 'created': a['created'],
                                  'rgb': a['color'], '_a': a} for a in pr['annots_raw']]
        elif doc['kind'] == 'docx':
            dr = docx_parse(p)
            doc['paras'] = dr['paras']
            doc['annots_raw'] = [dict(a, source='docx_inline', page=1) for a in dr['annots_raw']]
            doc['revisions'] = dr.get('revisions', [])
            doc['title'] = dr['meta'].get('title')
            doc['authors'] = [dr['meta']['author']] if dr['meta'].get('author') else []
            doc['notes'] += dr['notes']
            doc['pages'] = paras_to_pages(doc['paras'])
        elif doc['kind'] == 'html':
            hr = html_parse(p, raw.decode('utf-8', 'replace'))
            doc['paras'] = hr['paras']
            doc['annots_raw'] = [dict(a, source='html_inline', page=1) for a in hr['annots_raw']]
            doc['title'] = hr['meta'].get('title')
            doc['doi'] = hr['meta'].get('doi')
            doc['url'] = hr['meta'].get('url')
            doc['notes'] += hr['notes']
            doc['pages'] = paras_to_pages(doc['paras'])
        else:
            tr = text_parse(raw.decode('utf-8', 'replace'))
            doc['paras'] = tr['paras']
            doc['pages'] = paras_to_pages(doc['paras'])
    except Exception as e:
        doc['notes'].append('parse_failed:%s' % str(e)[:120])
    chars = sum(len(pg.get('text') or '') for pg in doc['pages'])
    doc['chars'], doc['pages_n'] = chars, len(doc['pages'])
    if doc['kind'] == 'pdf':
        if doc['encrypted']:
            doc['text_layer'] = 'encrypted'
        elif not chars:
            doc['text_layer'] = 'none'
        elif doc['garbled_pages'] >= max(1, doc['pages_n'] // 2):
            doc['text_layer'] = 'garbled'
        else:
            doc['text_layer'] = 'text'
    else:
        doc['text_layer'] = 'text' if chars else 'none'
    if not doc['title']:
        doc['title'] = _guess_title(doc)
    if not doc['doi']:
        doc['doi'] = _guess_doi(doc)
    doc['year'] = _guess_year(doc)
    return doc


def paras_to_pages(paras):
    text = '\n\n'.join(p['text'] for p in paras)
    nt, _ = norm_map(text)
    ps, cur = [], 0
    for p in paras:
        nseg = norm(p['text'])
        j = nt.find(nseg, cur)
        j = j if j >= 0 else cur
        ps.append({'pid': 'p1.%d' % (p['i'] + 1), 's': j, 'e': j + len(nseg),
                   'text': p['text'], 'col': 0})
        cur = max(cur, j + len(nseg))
    return [{'p': 1, 'printed': None, 'text': text, 'norm': nt, 'paras': ps, 'n_items': 0}]


def _guess_title(doc):
    for pg in doc['pages'][:1]:
        for pa in pg['paras'][:3]:
            if 8 <= len(pa['text']) <= 200:
                return pa['text']
    return None


def _guess_doi(doc):
    for pg in doc['pages'][:3]:
        m = re.search(r'\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]{4,}', pg['text'] or '')
        if m:
            return m.group(0).rstrip('.').rstrip(')')
    return None


def _guess_year(doc):
    for pg in doc['pages'][:2]:
        ys = re.findall(r'\b(19[6-9]\d|20[0-4]\d)\b', pg['text'] or '')
        if ys:
            return max(int(y) for y in ys)
    return None


def _page(doc, no):
    for pg in doc['pages']:
        if pg['p'] == no:
            return pg
    return doc['pages'][0] if doc['pages'] else None


def verify_quote(doc, quote, page_hint=None):
    nq = norm(quote or '')
    if not nq:
        return {'page': page_hint, 's': None, 'e': None, 'verified': False, 'grade': 'miss',
                'hits': 0, 'page_printed': None}
    order = ([page_hint] if page_hint else []) + [pg['p'] for pg in doc['pages'] if pg['p'] != page_hint]
    for pno in order:
        pg = _page(doc, pno)
        if not pg:
            continue
        hits = E.find_quotes(pg['norm'], nq)
        if hits:
            return {'page': pno, 'page_printed': pg.get('printed'), 's': hits[0][0],
                    'e': hits[0][1], 'verified': True, 'grade': 'exact', 'hits': len(hits)}
        fz = E.fuzzy_quote(pg['norm'], nq)
        if fz:
            return {'page': pno, 'page_printed': pg.get('printed'), 's': fz[0], 'e': fz[1],
                    'verified': True, 'grade': 'fuzzy', 'hits': 1}
    return {'page': page_hint or (doc['pages'][0]['p'] if doc['pages'] else None),
            'page_printed': (_page(doc, page_hint or 1) or {}).get('printed'),
            's': None, 'e': None, 'verified': False, 'grade': 'miss', 'hits': 0}


def _para(pg, s, e):
    if s is None or not pg:
        return None
    for pa in pg.get('paras', []):
        if pa['s'] <= s <= pa['e'] + 1:
            return pa
    return None


def _locator(page, para, s, e):
    pid = (para or {}).get('pid') or 'p?'
    if s is None or e is None:
        return 'p%s:%s' % (page, pid)
    return 'p%s:%s:c%d-c%d' % (page, pid, s, e)


def _ctx(pg, s, e, w=90):
    t = (pg or {}).get('text') or ''
    if s is None or not t:
        return None, None
    n = max(1, len((pg or {}).get('norm') or ''))
    sc = int(s / n * len(t))
    ec = int((e or s) / n * len(t))
    return clean(t[max(0, sc - w):sc]), clean(t[ec:ec + w])








def build_anchors(docs, exports, legend, log):
    anchors, orphans, seq, by = [], [], {}, {}
    for d in docs:
        by.setdefault(norm(d['file']), d)
        by.setdefault(norm(d['file'].split('/')[-1]), d)

    def finish(doc, item):
        pg = _page(doc, item.get('page_physical') or 1) or {}
        item['page_printed'] = item.get('page_printed') or pg.get('printed')
        pa = _para(pg, item.get('char_start'), item.get('char_end'))
        item['locator'] = _locator(item.get('page_physical'), pa, item.get('char_start'),
                                   item.get('char_end'))
        item['paragraph_id'] = (pa or {}).get('pid')
        item['context_before'], item['context_after'] = _ctx(pg, item.get('char_start'),
                                                             item.get('char_end'))
        item['color_meaning'], item['color_meaning_source'] = legend_lookup(
            legend, pg.get('text') or '', item.get('color'))
        k = (doc['doc_id'], item.get('page_physical') or 1)
        seq[k] = seq.get(k, 0) + 1
        item['anchor_id'] = 'a-%s-p%d-%02d' % ((doc.get('sha256') or 'nohash')[:8], k[1], seq[k])
        item.update({'doc_id': doc['doc_id'], 'file': doc['file'],
                     'file_sha256': doc.get('sha256'),
                     'source_version': doc.get('version_label') or 'canonical'})
        item.setdefault('sources', [])
        anchors.append(item)

    for d in docs:
        if d.get('dup_of'):
            continue
        for raw in d.get('annots_raw', []):
            try:
                item = {'type': raw.get('type') if raw.get('type') in E.TYPES else 'highlight',
                        'page_physical': raw.get('page') or 1, 'note': raw.get('note'),
                        'author': raw.get('author'), 'created': raw.get('created'),
                        'sources': [raw.get('source') or 'inline']}
                pdf = raw.get('source') == 'pdf_annots'
                if pdf:
                    a = raw['_a']
                    q, method, conf = align_quad(a)
                    item['region'] = {'quad': a.get('quad'), 'rect': a.get('rect')}
                    item['color'] = color_name(a.get('color')) if a.get('color') else 'yellow'
                    item['color_hex'] = _hex(a.get('color'))
                else:
                    q = raw.get('quote')
                    method = {'docx_highlight': 'docx_highlight', 'html_mark': 'html_mark'}.get(
                        raw.get('kind'), 'docx_comment')
                    conf = .9
                    col = (raw.get('color') or 'yellow').lower()
                    item['color'] = col if col in COLORS else 'custom'
                    item['color_hex'] = raw.get('color_hex')
                v = verify_quote(d, q, item['page_physical']) if q else {'verified': False}
                if v.get('verified'):
                    item.update({'page_physical': v['page'], 'page_printed': v.get('page_printed'),
                                 'char_start': v['s'], 'char_end': v['e'], 'quoted_text': q,
                                 'quote_verified': v['grade'], 'anchor_method': method,
                                 'anchor_confidence': conf})
                elif pdf and raw.get('note'):
                    item.update({'quoted_text': raw['note'], 'quote_verified': 'note_text_fallback',
                                 'anchor_confidence': .3, 'anchor_method': 'note_only',
                                 'quote_source': 'annotation_note'})
                else:
                    item.update({'quoted_text': q, 'quote_verified': 'unverified',
                                 'anchor_confidence': .35 if not pdf else .2,
                                 'anchor_method': 'note_only' if pdf else method})
                finish(d, item)
            except Exception as e:
                log.append({'kind': 'anchor_build_failed', 'file': d['file'], 'detail': str(e)[:160]})
    for rec in exports:
        for a in _ann_list(rec.get('data')):
            try:
                f = str(_pick(a, ['file', 'source', 'doc', 'document', 'path', 'filename',
                                 'source_file'], '') or '')
                d = by.get(norm(f)) or by.get(norm(f.split('/')[-1]))
                if d is None and f:
                    c = [x for x in docs if norm(f.split('/')[-1]).split('.')[0] in norm(x['file'])]
                    d = c[0] if len(c) == 1 else None
                if d is None:
                    orphans.append({'file': f or rec['file'], 'reason': 'orphan_annotation',
                                    'detail': '导出引用的文件不在库中（不猜归属）',
                                    'quote': str(_pick(a, ['quote', 'text', 'selected_text'],
                                                       ''))[:120]})
                    continue
                q = _pick(a, ['quote', 'text', 'selected_text', 'quoted_text', 'highlight', 'anchor'], '')
                pg = _pick(a, ['page', 'page_number', 'page_physical', 'p'], None)
                try:
                    pg = int(pg) if pg is not None else None
                except Exception:
                    pg = None
                ty = str(_pick(a, ['type', 'kind', 'annotation_type', 'category'],
                               'highlight')).lower()
                ty = {'strikeout': 'strikethrough', 'note': 'margin_note', 'comment': 'margin_note',
                      'ink': 'handwritten', 'clip': 'web_clip',
                      'region': 'region_mark'}.get(ty, ty)
                v = verify_quote(d, q, pg) if q else {'verified': False, 'page': pg}
                rgb = _parse_color(_pick(a, ['color', 'colour', 'highlight_color'], None))
                item = {'type': ty if ty in E.TYPES else 'highlight', 'quoted_text': q or None,
                        'page_physical': v.get('page') or pg or 1,
                        'page_printed': v.get('page_printed'), 'char_start': v.get('s'),
                        'char_end': v.get('e'),
                        'quote_verified': v.get('grade') if v.get('verified') else 'unverified',
                        'anchor_method': 'quote_search',
                        'anchor_confidence': .95 if v.get('verified') else (.3 if pg is None else .4),
                        'note': _pick(a, ['note', 'comment', 'content', 'body'], None),
                        'author': _pick(a, ['author', 'creator', 'user'], None),
                        'created': _pick(a, ['created', 'date', 'created_at', 'time'], None),
                        'tag': _pick(a, ['tag', 'tags', 'label'], None),
                        'sources': ['annotation_export'], 'export_file': rec['file'],
                        'color': color_name(rgb) if rgb else 'yellow', 'color_hex': _hex(rgb)}
                finish(d, item)
                cm = _pick(a, ['color_meaning', 'meaning', 'label_text'], None)
                if cm:
                    item['color_meaning'] = str(cm)
                    item['color_meaning_source'] = 'annotation_export'
            except Exception as e:
                log.append({'kind': 'export_annotation_failed', 'file': rec.get('file'),
                            'detail': str(e)[:160]})
    merged, seen = [], {}
    for a in anchors:
        q = norm(a.get('quoted_text') or '')
        k = (a['doc_id'], a.get('page_physical'), q, a.get('char_start')) if q else None
        if k is not None and k in seen:
            t = seen[k]
            t['sources'] = sorted(set(t.get('sources') or []) | set(a.get('sources') or []))
            if (a.get('anchor_confidence') or 0) > (t.get('anchor_confidence') or 0):
                t['anchor_method'] = a.get('anchor_method')
            t['anchor_confidence'] = max(t.get('anchor_confidence') or 0,
                                         a.get('anchor_confidence') or 0)
            t.setdefault('merged_from', []).append(a['anchor_id'])
            for f in ('note', 'tag', 'author', 'created'):
                if a.get(f) and not t.get(f):
                    t[f] = a[f]
            continue
        if k is not None:
            seen[k] = a
        merged.append(a)
    anchors = merged
    anchors.sort(key=lambda a: (a['doc_id'], a.get('page_physical') or 0,
                                a.get('char_start') if a.get('char_start') is not None else 10 ** 9,
                                a['type'], a['anchor_id']))
    by_q = {}
    for a in anchors:
        if a.get('quoted_text'):
            by_q.setdefault(norm(a['quoted_text'])[:160], []).append(a)
    for q, grp in by_q.items():
        if len(grp) > 1:
            ids = sorted(x['anchor_id'] for x in grp)
            for x in grp:
                x['duplicate_quote_group'] = ids[0]
                if len({g['doc_id'] for g in grp}) > 1:
                    x['cross_version_peer'] = [i for i in ids if i != x['anchor_id']]
    return anchors, orphans


def build_library(ctx):
    inp = Path(ctx['input_dir'])
    docs, exports, metadata, skipped, log = [], [], [], [], []
    for rec in ctx.get('materials', []):
        k = rec.get('kind')
        try:
            if k in ('pdf', 'docx', 'html', 'text'):
                docs.append(make_doc(rec, inp))
            elif k == 'json':
                try:
                    data = json.loads(Path(rec['path']).read_text(encoding='utf-8', errors='replace'))
                except Exception as e:
                    skipped.append({'file': rec['rel'], 'reason': 'bad_json', 'detail': str(e)[:160]})
                    continue
                lst = _ann_list(data)
                (exports if lst else metadata).append(
                    {'file': rec['rel'], 'data': data, 'count': len(lst)} if lst else
                    {'file': rec['rel'], 'data': data})
            elif k in ('too_large', 'unreadable', 'binary', 'zip'):
                skipped.append({'file': rec['rel'], 'reason': k,
                                'detail': '跳过：%s' % (rec.get('note') or k)})
        except Exception as e:
            skipped.append({'file': rec.get('rel'), 'reason': 'parse_failed', 'detail': str(e)[:200]})
            log.append({'kind': 'material_failed', 'file': rec.get('rel'), 'detail': str(e)[:200]})
    for d in docs:
        tl, f = d.get('text_layer'), d['file']
        if tl == 'encrypted':
            skipped.append({'file': f, 'reason': 'encrypted_pdf', 'detail': '加密：不抽正文/批注'})
        elif tl == 'none':
            skipped.append({'file': f, 'reason': 'no_text_layer',
                            'detail': '扫描件/无文本层：不造正文，需 OCR 或批注导出'})
        elif tl == 'garbled':
            skipped.append({'file': f, 'reason': 'garbled_text_layer',
                            'detail': 'CID/子集字体，仅引用逐字命中片段'})
        if not d.get('readable', True):
            skipped.append({'file': f, 'reason': 'permission_denied', 'detail': '不可读'})
        for n in d.get('notes', []):
            if n.endswith('_failed') or n.startswith('parse_failed'):
                log.append({'kind': 'doc_note', 'file': f, 'detail': n})
    seen_id = {}
    for d in docs:
        base = d['doc_id']
        if base in seen_id:
            seen_id[base] += 1
            d['doc_id'] = '%s-%s' % (base, chr(96 + seen_id[base]))
            d['same_content_as'] = base
        else:
            seen_id[base] = 1
            d['doc_id'] = base
    docs, groups, pairs, recovery = group_versions(docs, ctx.get('aliases', []),
                                                   ctx.get('version_notes', []))
    anchors, orphans = build_anchors(docs, exports, ctx.get('legend', {}), log)
    for a in anchors:
        if (a.get('anchor_confidence') or 0) < .5:
            skipped.append({'file': a['file'], 'reason': 'low_confidence', 'anchor_id': a['anchor_id'],
                            'detail': '置信度 %.2f（%s）' % (a['anchor_confidence'],
                                                          a.get('anchor_method'))})
        if a.get('quote_verified') == 'unverified':
            skipped.append({'file': a['file'], 'reason': 'quote_not_found', 'anchor_id': a['anchor_id'],
                            'detail': '未在该文件逐字命中，保留原样并标 unverified'})
    skipped += orphans
    st = {'docs_found': len(docs),
          'docs_processed': sum(1 for d in docs if d.get('text_layer') == 'text'),
          'pages': sum(d.get('pages_n') or 0 for d in docs), 'anchors': len(anchors),
          'anchors_verified': sum(1 for a in anchors if a.get('quote_verified') in ('exact', 'fuzzy')),
          'anchors_low_conf': sum(1 for a in anchors if (a.get('anchor_confidence') or 0) < .5),
          'annotation_exports': len(exports), 'metadata_files': len(metadata),
          'duplicates': sum(len(g['members']) - 1 for g in groups if g['relation'] == 'exact_duplicate'),
          'version_groups': sum(1 for g in groups if len(g['members']) > 1)}
    return {'schema': SCHEMA_INDEX, 'generated': now(), 'script_version': E.VERSION,
            'case_id': ctx.get('case_id'), 'task': ctx.get('task'),
            'contract': ctx.get('contract', {}), 'questions': ctx.get('questions', []),
            'topics': ctx.get('topics', []), 'aliases': pairs,
            'version_notes': ctx.get('version_notes', []), 'documents': docs,
            'groups': groups, 'anchors': anchors, 'skipped': skipped,
            'metadata': metadata, 'exports': [{'file': e['file'], 'count': e['count']} for e in exports],
            'recovery': recovery, 'stats': st, 'log': log, 'legend': ctx.get('legend', {})}


def index_view(lib):
    out = dict(lib)
    out['documents'] = [{k: v for k, v in d.items() if k not in ('annots_raw', 'paras')}
                        for d in lib['documents']]
    out['anchors'] = [{k: v for k, v in a.items()} for a in lib['anchors']]
    return out
