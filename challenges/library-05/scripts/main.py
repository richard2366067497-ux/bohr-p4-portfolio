"""reading-card-desk / main.py - CLI: init / show / check / build / selfcheck."""
import argparse, json, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import extract as E          # noqa: E402
import library as L          # noqa: E402
import render as R           # noqa: E402
import gates as G            # noqa: E402

VERSION = E.VERSION
DEF_IN, DEF_OUT, DEF_WORK = '/input', '/app/output', '/app/work'


def _p(x, d):
    return Path(x or d)


def sd(work):
    return Path(work) / 'desk'


def idx_path(work):
    return sd(work) / 'index.json'


def log(msg):
    try:
        print(msg)
    except Exception:
        pass


def _dump(p, o):
    return E.J(p, o)


def bootstrap(args, status='partial', extra_degradations=None):
    """legal result.json before anything else (contract keys present, values null)."""
    try:
        case = {}
        cj = _p(args.input, DEF_IN) / 'case.json'
        if cj.exists():
            try:
                case = json.loads(cj.read_text(encoding='utf-8', errors='replace'))
            except Exception:
                case = {}
        case = case if isinstance(case, dict) else {}
        cid = str(case.get('case_id') or 'UNKNOWN-CASE')
        contract = case.get('output_contract') or case.get('outputContract') or {}
        contract = contract if isinstance(contract, dict) else {}
        vals = {k: None for k in ('cards', 'anchors', 'library', 'versions', 'retrieval', 'coverage',
                                  'provenance', 'graph', 'topics', 'skipped', 'recovery',
                                  'operations', 'changes', 'uncertainties', 'errors',
                                  'degradations', 'sources', 'method_notes', 'result', 'artifacts')}
        vals['case_id'] = cid
        vals['status'] = status
        res = R.build_result(cid, contract, vals, {
            'status': status, 'degradations': (extra_degradations or []) + [
                {'kind': 'bootstrap_partial', 'detail': '骨架结果：init 已落盘，等待解析与工作稿'}],
            'runtime': {'script': 'reading-card-desk', 'version': VERSION, 'stage': 'bootstrap'}})
        _dump(Path(args.output or DEF_OUT) / 'result.json', res)
        return res
    except Exception:
        return None


def ensure_index(args, force=False):
    """parse input -> index.json (cached). Returns (index, err)."""
    wp, op = _p(args.work, DEF_WORK), _p(args.output, DEF_OUT)
    ip = idx_path(wp)
    if ip.exists() and not force:
        try:
            return json.loads(ip.read_text(encoding='utf-8')), None
        except Exception:
            pass
    op.mkdir(parents=True, exist_ok=True)
    try:
        ctx = L.discover(_p(args.input, DEF_IN))
        lib = L.build_library(ctx)
        idx = L.index_view(lib)
        idx['params'] = {'input': str(_p(args.input, DEF_IN)), 'output': str(op),
                         'work': str(wp), 'script_version': VERSION}
        idx['errors'] = ctx.get('errors', []) + [
            {'kind': 'discovery', 'detail': d} for d in ctx.get('errors', [])]
        _dump(ip, idx)
        return idx, None
    except Exception as e:
        tb = traceback.format_exc()
        return {'case_id': 'UNKNOWN-CASE', 'documents': [], 'anchors': [], 'skipped': [],
                'groups': [], 'aliases': [], 'questions': [], 'topics': [], 'stats': {},
                'contract': {}, 'recovery': [], 'log': [], 'errors': [
                    {'kind': 'index_failed', 'detail': tb[-600:]}]}, e


def load_draft(work, explicit=None):
    cands = [Path(explicit)] if explicit else []
    cands += [Path(work) / 'draft.json', Path(work) / 'plan.json',
              Path(work) / 'desk' / 'draft.json', Path(work) / 'cards.json']
    for c in cands:
        try:
            if c and c.exists():
                d = json.loads(c.read_text(encoding='utf-8', errors='replace'))
                if isinstance(d, dict):
                    return d, str(c), None
                return None, str(c), 'draft_not_object'
        except Exception as e:
            return None, str(c), 'draft_invalid_json: %s' % str(e)[:120]
    return None, None, 'draft_missing'






def cmd_init(args):
    wp, op = _p(args.work, DEF_WORK), _p(args.output, DEF_OUT)
    sd(wp).mkdir(parents=True, exist_ok=True)
    op.mkdir(parents=True, exist_ok=True)
    bootstrap(args)
    idx, e = ensure_index(args, force=True)
    if e:
        idx.setdefault('errors', []).append({'kind': 'index_failed', 'detail': str(e)[:200]})
    draft_raw, dpath, derr = load_draft(wp, args.draft)
    draft = R.norm_draft(draft_raw, idx)
    chk = G.check_draft(idx, draft, bool(draft_raw), derr)
    _dump(sd(wp) / 'check_report.json', chk)
    res = R.build_result(idx.get('case_id') or 'UNKNOWN-CASE', idx.get('contract') or {},
                         _payload(idx, chk, draft, None, [
                             {'kind': 'cards_pending_agent_draft',
                              'detail': '卡片需由评审 Agent 阅读材料后写入 draft.json 再 build'}]),
                         {'status': chk['status'], 'runtime': {
                             'script': 'reading-card-desk', 'version': VERSION,
                             'python': sys.version.split()[0], 'stage': 'init'}})
    _dump(op / 'result.json', res)
    log('init: case=%s docs=%d anchors=%d skipped=%d -> %s' % (
        idx.get('case_id'), idx.get('stats', {}).get('docs_found', 0),
        len(idx.get('anchors', [])), len(idx.get('skipped', [])), idx_path(wp)))
    if draft_raw:
        log('init: 已发现工作稿 %s（%d 卡）' % (dpath, len(draft_raw.get('cards') or [])))
    else:
        log('init: 未发现工作稿（%s）→ 下一步：show 读材料，写 %s' % (derr, wp / 'draft.json'))
    return 0




def _sources(idx):
    out = []
    for d in idx.get('documents', []):
        out.append({'source_id': d.get('doc_id'), 'path': d.get('file'), 'kind': d.get('kind'),
                    'bytes': d.get('bytes'), 'sha256': d.get('sha256')})
    for e in idx.get('exports', []):
        out.append({'source_id': e.get('file'), 'path': e.get('file'), 'kind': 'annotation_export',
                    'bytes': None, 'sha256': None})
    return out




def _payload(idx, chk, draft, rendered=None, degradations=None):
    rendered = rendered or {}
    cov = G.coverage(idx, chk)
    return {
        'case_id': idx.get('case_id'), 'status': chk['status'],
        'cards': draft.get('cards', []), 'anchors': idx.get('anchors', []),
        'library': _library_payload(idx),
        'versions': {'groups': idx.get('groups', []), 'aliases': idx.get('aliases', []),
                     'recovery': idx.get('recovery', [])},
        'retrieval': {'results': rendered.get('retrieval', []),
                      'questions_in_case': idx.get('questions', []),
                      'design': 'agent mapping 1.0 > lexical>=0.18 with claim bonus; hits carry matched_terms'},
        'coverage': cov, 'provenance': rendered.get('provenance') or {
            'script_version': VERSION, 'stage': 'init', 'inputs_hashed':
            sum(1 for d in idx.get('documents', []) if d.get('sha256'))},
        'graph': rendered.get('graph') or {'nodes': [], 'edges': []},
        'topics': idx.get('topics', []), 'skipped': idx.get('skipped', []),
        'recovery': idx.get('recovery', []),
        'operations': [{'step': 'init', 'detail': 'index'},
                       {'step': 'check', 'detail': chk['gates']}],
        'changes': [], 'uncertainties': G.uncertainties(idx, chk),
        'errors': chk['errors'] + idx.get('errors', []),
        'degradations': degradations or [], 'sources': _sources(idx),
        'method_notes': {'extractor': 'stdlib PDF content stream + /Annots quad->text; DOCX comments; HTML mark',
                         'anchor_rule': 'quote re-located on page; page/offset from the hit, not pdf_page±1',
                         'card_rule': 'agent judgment; grounded needs verified anchor+boundary+strength',
                         'version_rule': 'sha256 > containment>=0.85 > version rank',
                         'retrieval_rule': 'explicit mapping, else lexical>=0.18 with matched_terms'},
        'result': {'cards_grounded': [c for c in draft.get('cards', []) if c.get('status') == 'grounded'],
                   'cards_partial': [c for c in draft.get('cards', []) if c.get('status') == 'partial'],
                   'cards_unsupported': [c for c in draft.get('cards', []) if c.get('status') == 'unsupported'],
                   'coverage': cov, 'gates': chk['gates'], 'library_stats': idx.get('stats', {})},
        'artifacts': (rendered.get('artifacts') or []) + ['result.json']}

def cmd_show(args):
    wp = _p(args.work, DEF_WORK)
    idx, e = ensure_index(args, force=args.reindex)
    if e:
        log('show: index 构建失败（%s），仅打印空清单' % str(e)[:120])
    sec = args.section or ('anchor' if args.anchor else 'overview')
    lim = int(args.limit or 40)
    if args.anchor:
        a = next((x for x in idx.get('anchors', []) if x['anchor_id'] == args.anchor), None)
        if not a:
            log('show: 未找到锚点 %s' % args.anchor)
            return 0
        sec = 'anchor'
    if sec == 'overview':
        st = idx.get('stats', {})
        log('case_id: %s' % idx.get('case_id'))
        log('task: %s' % (idx.get('task') or '')[:300].replace('\n', ' '))
        log('contract keys: %s' % ', '.join((idx.get('contract') or {}).keys()))
        log('docs=%s processed=%s pages=%s anchors=%s verified=%s low_conf=%s skipped=%s' % (
            st.get('docs_found'), st.get('docs_processed'), st.get('pages'), st.get('anchors'),
            st.get('anchors_verified'), st.get('anchors_low_conf'), len(idx.get('skipped', []))))
        gs = {' | '.join('%s(%s)' % (m['file'], m['version']) for m in g['members']): g['relation']
              for g in idx.get('groups', []) if len(g['members']) > 1}
        for k, v in list(gs.items())[:10]:
            log('version group [%s]: %s' % (v, k))
        log('questions: %s' % (', '.join(q['question'][:70] for q in idx.get('questions', [])) or '（无）'))
        log('next: show --section anchors | show --anchor <id> | 写 %s 后 check/build' % (wp / 'draft.json'))
    elif sec == 'docs':
        for d in idx.get('documents', [])[:lim]:
            log('- %s [%s] %s p%s c%s layer=%s ver=%s canon=%s sha=%s' % (
                d.get('file'), d.get('kind'), (d.get('title') or '')[:60], d.get('pages_n'),
                d.get('chars'), d.get('text_layer'), d.get('version_label'),
                'Y' if d.get('is_canonical') else 'n', (d.get('sha256') or '')[:12]))
            if d.get('admin_notes'):
                log('    version notes: %s' % '; '.join(d['admin_notes'])[:200])
    elif sec in ('anchors', 'cards-candidates'):
        for a in idx.get('anchors', [])[:lim]:
            log('%s %s p%s(%s) %s conf=%.2f %s' % (
                a['anchor_id'], a.get('type'), a.get('page_physical'), a.get('page_printed'),
                a.get('locator'), a.get('anchor_confidence') or 0, a.get('file')))
            log('    quote: %s' % (a.get('quoted_text') or '（无原文）')[:220])
            if a.get('note'):
                log('    note : %s' % a['note'][:160])
            log('    color: %s (%s / %s) ver=%s' % (a.get('color'), a.get('color_meaning'),
                                                   a.get('color_meaning_source'), a.get('source_version')))
    elif sec == 'anchor':
        a = next((x for x in idx.get('anchors', []) if x['anchor_id'] == (args.anchor or '')), None)
        if not a:
            log('show: 未找到锚点')
            return 0
        doc = next((d for d in idx.get('documents', []) if d['doc_id'] == a.get('doc_id')), {})
        log('%s  %s  %s  ver=%s  method=%s conf=%.2f verified=%s' % (
            a['anchor_id'], a.get('file'), a.get('locator'), a.get('source_version'),
            a.get('anchor_method'), a.get('anchor_confidence') or 0, a.get('quote_verified')))
        log('quote: %s' % (a.get('quoted_text') or '（无）'))
        log('color: %s = %s (%s)  type=%s' % (a.get('color'), a.get('color_meaning'),
                                              a.get('color_meaning_source'), a.get('type')))
        if a.get('note'):
            log('annotation note: %s' % a['note'])
        pg = next((p for p in (doc.get('pages') or []) if p.get('p') == a.get('page_physical')), None)
        if pg:
            log('--- page %s full text (normalized offsets in brackets) ---' % pg.get('p'))
            c = a.get('char_start') or 0
            t = pg.get('text') or ''
            n = max(1, len(pg.get('norm') or ''))
            pos = int(c / n * len(t))
            log(t[max(0, pos - 700):pos + 700])
    elif sec == 'questions':
        for q in idx.get('questions', []):
            log('- %s: %s' % (q.get('id'), q.get('question')))
        for t in idx.get('topics', []):
            log('  topic: %s' % t)
    elif sec == 'gaps':
        for s in idx.get('skipped', [])[:lim]:
            log('- %s [%s] %s' % (s.get('file'), s.get('reason'), (s.get('detail') or '')[:160]))
    else:
        log('show: 未知 section %s' % sec)
    return 0


def cmd_check(args):
    wp = _p(args.work, DEF_WORK)
    idx, e = ensure_index(args, force=args.reindex)
    draft_raw, dpath, derr = load_draft(wp, args.draft)
    draft = R.norm_draft(draft_raw, idx)
    chk = G.check_draft(idx, draft, bool(draft_raw), derr)
    chk['draft_path'] = dpath
    _dump(sd(wp) / 'check_report.json', chk)
    G.print_check(chk)
    if not draft_raw:
        log('check: 无工作稿 → build 只出 anchor-only 降级交付(partial)。先写 %s' % (wp / 'draft.json'))
    return 0


def cmd_build(args):
    wp, op = _p(args.work, DEF_WORK), _p(args.output, DEF_OUT)
    op.mkdir(parents=True, exist_ok=True)
    bootstrap(args, 'partial', [{'kind': 'build_started', 'detail': '正在组装四层产物'}])
    idx, e = ensure_index(args, force=args.reindex)
    draft_raw, dpath, derr = load_draft(wp, args.draft)
    draft = R.norm_draft(draft_raw, idx)
    chk = G.check_draft(idx, draft, bool(draft_raw), derr)
    deg = []
    if not draft_raw:
        draft = _fallback_draft(idx)
        chk = G.check_draft(idx, draft, False, derr)
        deg.append({'kind': 'draft_missing',
                    'detail': '未找到工作稿（%s）：卡片为 anchor-only 占位（claim=null, '
                              'status=unsupported），检索视图只给未命中原因' % derr})
    elif not draft['cards']:
        deg.append({'kind': 'draft_empty_cards', 'detail': '工作稿存在但没有有效卡片'})
    if chk['errors']:
        deg.append({'kind': 'check_errors', 'detail': '%d 项未通过，逐条见 result.errors'
                                                  % len(chk['errors'])})
    cov = G.coverage(idx, chk)
    rendered = R.write_all(op, wp, idx, draft, chk, {
        'params': {'input': str(_p(args.input, DEF_IN)), 'threshold_retrieval': 0.18,
                   'containment_version': 0.85, 'page_cap': E.PAGE_CAP},
        'coverage': cov,
        'determinism': {'checked': False, 'note': 'selfcheck 可验证锚点 ID 与逐字复核稳定性'}})
    status = 'partial' if (deg or chk['status'] != 'ok' or not idx.get('documents')) else 'ok'
    vals = _payload(idx, chk, draft, rendered, deg)
    vals['status'] = status
    env = {'status': status, 'degradations': deg, 'sources': vals['sources'],
           'errors': vals['errors'], 'uncertainties': vals['uncertainties'],
           'runtime': {'script': 'reading-card-desk', 'version': VERSION,
                       'python': sys.version.split()[0], 'stage': 'build',
                       'budget': {'model_requests': 64, 'seconds': 900, 'tokens_per_response': 16384}}}
    res = R.build_result(idx.get('case_id') or 'UNKNOWN-CASE', idx.get('contract') or {}, vals, env)
    for k in res.get('_contract_unmapped') or []:
        res.setdefault('degradations', []).append({
            'kind': 'contract_field_unmapped:%s' % k,
            'detail': '该契约键无法语义映射，按约定保留键名并给 null'})
    if res.get('degradations') and res.get('status') == 'ok':
        res['status'] = 'partial'
    _dump(op / 'result.json', res)
    log('build: status=%s cards=%d (grounded=%d) anchors=%d artifacts=%d -> %s' % (
        res.get('status'), len(draft['cards']),
        sum(1 for c in draft['cards'] if c.get('status') == 'grounded'),
        len(idx.get('anchors', [])), len(rendered['artifacts']), op / 'result.json'))
    for a in rendered['artifacts']:
        log('  + %s' % a)
    if not draft_raw:
        log('build: 这是未读材料的降级交付(draft_missing)。按 SKILL.md：先 show 读原文、写工作稿、再 build。')
    return 0


def _fallback_draft(idx):
    """anchor-only placeholders: honest, no invented judgment."""
    cards, seen = [], {}
    for a in idx.get('anchors', []):
        if not a.get('quoted_text') or a.get('quote_verified') not in ('exact', 'unverified_after_check'):
            continue
        doc = a.get('doc_id')
        if seen.get(doc, 0) >= 3:
            continue
        seen[doc] = seen.get(doc, 0) + 1
        cards.append({'card_id': 's%02d' % (len(cards) + 1), 'kind': 'to_verify', 'claim': None,
                      'anchor_ids': [a['anchor_id']], 'source_version': a.get('source_version'),
                      'strength': 'weak', 'boundary': None, 'reuse_hint': None,
                      'status': 'unsupported', 'created_from': 'fallback_anchor_only',
                      'evidence_note': None, 'counter_evidence': None, 'tags': [], 'topic': None,
                      'missing': ['claim', 'boundary', 'judgment']})
        if len(cards) >= 12:
            break
    return {'case_id': idx.get('case_id'), 'cards': cards, 'topics': [], 'edges': [],
            'questions': [], 'aliases': [], 'skipped': [], 'notes': 'fallback', 'anchor_index': {}}


def _library_payload(idx):
    return {'stats': idx.get('stats', {}),
            'documents': [{k: v for k, v in R._doc_view(d).items()} for d in idx.get('documents', [])],
            'groups': idx.get('groups', []), 'aliases': idx.get('aliases', []),
            'annotation_exports': idx.get('exports', []),
            'skipped_count': len(idx.get('skipped', []))}


def cmd_selfcheck(args):
    wp, op = _p(args.work, DEF_WORK), _p(args.output, DEF_OUT)
    idx, e = ensure_index(args, force=False)
    fresh, e2 = ensure_index(args, force=True)
    ids_now = [a['anchor_id'] for a in idx.get('anchors', [])]
    ids_new = [a['anchor_id'] for a in fresh.get('anchors', [])]
    stable = ids_now == ids_new
    draft_raw, dpath, derr = load_draft(wp, args.draft)
    draft = R.norm_draft(draft_raw, idx)
    chk = G.check_draft(idx, draft, bool(draft_raw), derr)
    docs = {d['doc_id']: d for d in idx.get('documents', [])}
    recheck, bad = 0, []
    for a in idx.get('anchors', []):
        q = E.norm(a.get('quoted_text') or '')
        if not q:
            continue
        recheck += 1
        pg = next((p for p in (docs.get(a.get('doc_id')) or {}).get('pages', [])
                   if p.get('p') == a.get('page_physical')), None)
        if not pg or q not in (pg.get('norm') or ''):
            bad.append(a['anchor_id'])
    out = op / 'result.json'
    contract_keys, unmapped, present = [], [], []
    try:
        cur = json.loads(out.read_text(encoding='utf-8'))
        contract_keys = cur.get('_contract_keys') or []
        unmapped = cur.get('_contract_unmapped') or []
        present = [k for k in contract_keys if k in cur]
    except Exception:
        cur = {}
    sc = {'schema': 'reading-card-desk/selfcheck@1', 'generated': E.now(),
          'script_version': VERSION,
          'anchor_ids_stable': stable, 'anchors_compared': len(ids_now),
          'quotes_rechecked': recheck, 'quote_failures': bad,
          'contract_keys': len(contract_keys), 'contract_present': len(present),
          'contract_unmapped': unmapped,
          'result_status': cur.get('status'), 'result_exists': bool(cur),
          'gate_status': {k: v.get('status') for k, v in chk['gates'].items()},
          'overall': 'fail' if (bad or not stable or (contract_keys and len(present) < len(contract_keys)))
                     else 'pass'}
    op.mkdir(parents=True, exist_ok=True)
    (op / 'provenance').mkdir(parents=True, exist_ok=True)
    _dump(op / 'provenance' / 'self_check.json', sc)
    if cur:
        try:
            cur.setdefault('provenance', {})
            if isinstance(cur['provenance'], dict):
                cur['provenance']['determinism'] = {'checked': True, 'anchor_ids_stable': stable,
                                                    'anchors_compared': len(ids_now)}
            cur['self_check'] = {'overall': sc['overall'], 'quote_failures': len(bad),
                                 'anchor_ids_stable': stable,
                                 'contract_present': '%d/%d' % (len(present), len(contract_keys))}
            _dump(out, cur)
        except Exception:
            pass
    log('selfcheck: overall=%s anchor_ids_stable=%s quotes=%d failures=%d contract=%d/%d unmapped=%s'
        % (sc['overall'], stable, recheck, len(bad), len(present), len(contract_keys),
           unmapped or 'none'))
    if bad:
        log('  ! 复核失败锚点: %s' % ', '.join(bad[:8]))
    if not stable:
        log('  ! 锚点 ID 在两次索引间不稳定：检查文件顺序/哈希，勿提交该运行')
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog='reading-card-desk',
                                 description='knowledge-card desk for reading annotation libraries')
    ap.add_argument('cmd', nargs='?', default='', choices=['', 'init', 'show', 'check', 'build',
                                                           'selfcheck', 'run'])
    ap.add_argument('--input', default=DEF_IN)
    ap.add_argument('--output', default=DEF_OUT)
    ap.add_argument('--work', default=DEF_WORK)
    ap.add_argument('--draft', default=None, help='draft json path (default: <work>/draft.json)')
    ap.add_argument('--section', default=None,
                    help='show section: overview|docs|anchors|questions|gaps|anchor')
    ap.add_argument('--anchor', default=None, help='show one anchor with its page text')
    ap.add_argument('--limit', type=int, default=40)
    ap.add_argument('--reindex', action='store_true', help='ignore cached index.json')
    ap.add_argument('--quiet', action='store_true')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    t0 = time.time()
    try:
        if args.cmd in ('init',):
            rc = cmd_init(args)
        elif args.cmd == 'show':
            rc = cmd_show(args)
        elif args.cmd == 'check':
            rc = cmd_check(args)
        elif args.cmd == 'build':
            rc = cmd_build(args)
        elif args.cmd == 'selfcheck':
            rc = cmd_selfcheck(args)
        elif args.cmd == 'run':
            cmd_init(args)
            rc = cmd_build(args)
        else:
            log('usage: main.py {init|show|check|build|selfcheck} [--input /input] '
                '[--output /app/output] [--work /app/work]')
            log('main path: init -> show -> (write draft.json) -> check -> build -> selfcheck')
            log('脚本不会代替你阅读理解：必须先读材料、写工作稿，再 build。')
            rc = 0
        return rc or 0
    except Exception:
        tb = traceback.format_exc()
        try:
            bootstrap(args, 'partial', [{'kind': 'uncaught_exception', 'detail': tb[-800:]}])
        except Exception:
            pass
        log('main: 捕获异常（退出码仍为 0）：%s' % tb.splitlines()[-1][:300])
        return 0


if __name__ == '__main__':
    try:
        rc = main(sys.argv[1:])
    except SystemExit:
        rc = 0
    except Exception:
        rc = 0
    sys.exit(0)
