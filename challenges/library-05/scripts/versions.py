"""reading-card-desk / versions.py - duplicate, alias and version consolidation."""
import re

from extract import norm

def _shingles(text, k=5, cap=4000):
    w = norm(text or '')[:40000].split()
    if len(w) < k:
        return set(w)
    return {' '.join(w[i:i + k]) for i in range(min(len(w) - k + 1, cap))}


def _clean_name_first(members):
    def rank(m):
        n = m.get('file') or ''
        return (1 if re.search(r'\(\d+\)|copy|副本|复制', n, re.I) else 0, len(n), n)
    return sorted(members, key=rank)[0]


def _jac(a, b):
    if not a or not b:
        return 0.
    return len(a & b) / float(len(a | b))


def _vrank(doc):
    name = (doc.get('file') or '') + ' ' + (doc.get('title') or '')
    copy = -1 if re.search(r'\(\d+\)|copy|副本|复制|~\$', name, re.I) else 0
    v = 0.
    for n in re.findall(r'v(?:er(?:sion)?)?[ _\-.]?(\d+)(?:[._](\d+))?', name, re.I):
        try:
            v = max(v, float(n[0]) + (float(n[1]) / 100. if n[1] else 0.))
        except Exception:
            pass
    fin = 1 if re.search(r'final|accepted|published|终稿|定稿|camera', name, re.I) else 0
    dr = -1 if re.search(r'draft|preprint|submitted|草稿|投稿', name, re.I) else 0
    noted = 1 if any(re.search(r'supersed|replaces|取代|替换|最新|current', n, re.I)
                     for n in doc.get('admin_notes', [])) else 0
    label = re.search(r'v(?:er(?:sion)?)?[ _\-.]?(\d+(?:[._]\d+)*)', name, re.I)
    return (v, fin + dr, noted, copy, doc.get('mtime') or 0), \
        (label.group(1).replace('_', '.') if label else None)


def group_versions(docs, aliases, version_notes):
    for d in docs:
        for n in version_notes:
            ref = norm(n.get('ref') or '')
            base = norm(d['file'])
            if ref and (ref == base or base.endswith(ref) or ref in base
                        or ref == norm(d.get('title') or '')):
                d.setdefault('admin_notes', []).append(n.get('note') or '')
                n['_doc'] = d['doc_id']
    pairs = []
    by_name = {}
    for d in docs:
        by_name.setdefault(norm(d['file'].split('/')[-1]), d)
        by_name.setdefault(norm(d['file']), d)
    for a in aliases:
        ca = norm(str(a.get('canonical') or ''))
        al = norm(str(a.get('alias') or ''))
        tgt = by_name.get(ca.split('/')[-1]) or by_name.get(ca)
        src = by_name.get(al.split('/')[-1]) or by_name.get(al)
        if tgt is not None and al:
            pairs.append({'alias': a.get('alias'), 'canonical': a.get('canonical'),
                          'alias_doc': src['doc_id'] if src else None,
                          'canonical_doc': tgt['doc_id'], 'source': 'case_declared'})
    groups = []
    for d in docs:
        hit = None
        for g in groups:
            h = g['members'][0]
            if d.get('sha256') and d.get('sha256') == h.get('sha256'):
                hit = g
                break
        if hit:
            hit['members'].append(d)
            hit['relation'] = 'exact_duplicate'
            keep = _clean_name_first(hit['members'])
            for mm in hit['members']:
                mm['dup_of'] = None if mm is keep else keep['doc_id']
        else:
            groups.append({'members': [d], 'relation': 'unique'})
    sh = {id(g): _shingles(' '.join(pg['text'] for pg in g['members'][0]['pages'])) for g in groups}
    merged = []
    def _same(a, b):
        if not a or not b:
            return False
        cont = len(a & b) / float(min(len(a), len(b)))
        return _jac(a, b) >= .82 or (cont >= .85 and min(len(a), len(b)) >= 12)

    for g in groups:
        tgt = None
        for m in merged:
            if _same(sh[id(g)], m[1]):
                tgt = m
                break
        if tgt:
            tgt[0]['members'].extend(g['members'])
            tgt[0]['relation'] = 'near_duplicate_version'
        else:
            merged.append([g, sh[id(g)]])
    out, recovery = [], []
    for i, (g, _s) in enumerate(merged):
        mem = g['members']
        ranked = sorted(mem, key=lambda d: _vrank(d)[0], reverse=True)
        canon = ranked[0]
        for d in mem:
            r, label = _vrank(d)
            d['work_id'] = 'w%d' % (i + 1)
            d['is_canonical'] = (d is canon)
            d['version_label'] = ('v%s' % label) if label else ('canonical' if d is canon else 'v0')
            d['source_version'] = d['version_label']
            if d.get('admin_notes'):
                d['version_note_source'] = 'case_declared'
        out.append({'work_id': 'w%d' % (i + 1), 'relation': g['relation'],
                    'canonical': canon['doc_id'], 'canonical_file': canon['file'],
                    'title': canon.get('title'), 'doi': canon.get('doi'),
                    'version_notes': [n for n in (canon.get('admin_notes') or [])],
                    'members': [{'doc_id': d['doc_id'], 'file': d['file'], 'sha256': d['sha256'],
                                 'version': d['version_label'], 'chars': d.get('chars'),
                                 'canonical': d['is_canonical']} for d in mem]})
    for g in out:
        for mm in g['members']:
            if not mm['canonical']:
                recovery.append({'action': 'use_canonical', 'instead_of': mm['file'],
                                 'use': g['canonical_file'], 'reason': g['relation'],
                                 'version': mm['version'], 'note': '不删除原件；仅在索引与卡片中指向 canonical',
                                 'work_id': g['work_id']})
        if len(g['members']) > 1:
            recovery.append({'action': 'merge_annotations', 'work_id': g['work_id'],
                             'members': [mm['file'] for mm in g['members']],
                             'rule': '同 work 内 quote_normalized 相同视为同一处批注，保留各 source_version'})
    for d in docs:
        base = d['file'].split('/')[-1]
        stem = re.sub(r'\s*[\(\[]\d+[\)\]]|[-_ ]?(copy|副本|复制)\b|\.(pdf|docx|md|txt|html?)$', '',
                      base, flags=re.I).strip()
        if stem and norm(stem) != norm(base):
            pairs.append({'alias': base, 'canonical': stem, 'alias_doc': d['doc_id'],
                          'canonical_doc': None, 'source': 'filename_normalization'})
    return docs, out, pairs, recovery


