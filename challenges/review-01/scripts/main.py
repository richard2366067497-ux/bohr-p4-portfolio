from __future__ import annotations
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import audit_core as core
import audit_leads as leads
import render as rnd
DEFAULT_INPUT = '/input'
DEFAULT_WORK = '/app/work'
DEFAULT_OUT = '/app/output'

def _pick_dir(explicit, env_key, candidates, fallback, make=False):
    cands = []
    if explicit:
        cands.append(explicit)
    env = os.environ.get(env_key)
    if env:
        cands.append(env)
    cands.extend(candidates)
    cands.append(fallback)
    for c in cands:
        p = Path(c).expanduser()
        try:
            if p.is_dir():
                return p.resolve()
        except Exception:
            continue
    if make:
        for c in cands:
            p = Path(c).expanduser()
            try:
                p.mkdir(parents=True, exist_ok=True)
                return p.resolve()
            except Exception:
                continue
    return Path(fallback)

def paths(args):
    inp = _pick_dir(getattr(args, 'input', None), 'AUDIT_INPUT', [DEFAULT_INPUT, str(ROOT / 'input'), str(Path.cwd() / 'input')], DEFAULT_INPUT)
    work = _pick_dir(getattr(args, 'work', None), 'AUDIT_WORK', [DEFAULT_WORK, str(ROOT / 'work'), str(Path.cwd() / 'work')], DEFAULT_WORK, make=True)
    out = _pick_dir(getattr(args, 'output', None), 'AUDIT_OUTPUT', [DEFAULT_OUT, str(ROOT / 'output'), str(Path.cwd() / 'output')], DEFAULT_OUT, make=True)
    return (inp, work, out)

def write_json(path, payload):
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, p)
        return True
    except Exception as exc:
        sys.stderr.write('[warn] write_json failed for %s: %s\n' % (p, exc))
        try:
            p.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            return True
        except Exception:
            return False

def load_json(path):
    p = Path(path)
    if not p.is_file():
        return (None, 'missing: %s' % p)
    try:
        raw = p.read_text(encoding='utf-8', errors='ignore')
    except Exception as exc:
        return (None, 'read_failed: %s' % exc)
    for candidate in (raw, raw.lstrip('\ufeff').strip()):
        try:
            return (json.loads(candidate), None)
        except Exception as exc:
            first = exc
    fixed = raw.lstrip('\ufeff')
    fixed = '\n'.join((l for l in fixed.splitlines() if not l.strip().startswith('//')))
    fixed = fixed.replace(',\n}', '\n}').replace(',\n]', '\n]').replace(',}', '}').replace(',]', ']')
    try:
        return (json.loads(fixed), 'repaired')
    except Exception:
        return (None, 'invalid_json: %s' % first)

def find_draft(work, out):
    for cand in (work / 'draft.json', work / 'plan.json', work / 'review.json', out / 'draft.json', Path('/app/work/draft.json')):
        try:
            if Path(cand).is_file():
                return Path(cand)
        except Exception:
            continue
    return None

def save_index(index, work):
    slim = {k: v for k, v in index.items() if k != 'candidates'}
    write_json(work / 'index.json', slim)
    write_json(work / 'candidates.json', {'rules_version': core.RULES_VERSION, 'candidates': index.get('candidates') or []})

def load_index(work, inp, args):
    idx, err = load_json(work / 'index.json')
    if isinstance(idx, dict) and idx.get('segments') is not None:
        cands, _ = load_json(work / 'candidates.json')
        idx['candidates'] = (cands or {}).get('candidates') or []
        return (idx, None)
    return build_index(inp, work, args, quiet=True)

def build_index(inp, work, args, quiet=False):
    case, cerr = load_json(inp / 'case.json')
    if not isinstance(case, dict):
        case = {}
    task = ''
    for name in ('task.md', 'task.txt', 'README.md'):
        try:
            if (inp / name).is_file():
                task = (inp / name).read_text(encoding='utf-8', errors='ignore')
                break
        except Exception:
            continue
    notes = []
    if cerr:
        notes.append('case_json:%s' % cerr)
    index = core.build_index(inp, case, task)
    index['notes'] = (index.get('notes') or []) + notes
    try:
        index['candidates'] = leads.scan(index)
    except Exception as exc:
        index['candidates'] = []
        index['notes'].append('scan_failed:%s' % exc)
    save_index(index, work)
    if not quiet:
        sys.stderr.write('[init] indexed %d documents / %d segments / %d leads\n' % (index['counts']['documents'], index['counts']['segments'], len(index['candidates'])))
    return (index, cerr)

def cmd_init(args):
    inp, work, out = paths(args)
    write_json(out / 'result.json', {'case_id': None, 'status': 'partial', 'task': 'manuscript_quality_audit', 'skill_version': core.VERSION, 'rules_version': core.RULES_VERSION, 'result': None, 'findings': [], 'coverage': {}, 'summary': '', 'sources': [], 'uncertainties': ['run_in_progress'], 'errors': [], 'degradations': ['preliminary_stub_written_by_init'], 'changes': [], 'runtime': {'stage': 'init'}})
    index, cerr = build_index(inp, work, args)
    rnd.finalize((inp, work, out), index, draft={}, stage='init')
    print('== INIT ==')
    print('input : %s' % inp)
    print('work  : %s' % work)
    print('output: %s' % out)
    print('documents: %d  segments: %d  leads: %d' % (index['counts']['documents'], index['counts']['segments'], len(index['candidates'])))
    for d in index['documents']:
        print('  %-3s %-22s role=%-14s fmt=%-9s p=%-3s seg=%-4s %s' % (d['doc_id'], d['rel'][:22], d['role'], d['parser'], d['pages'], d['segments'], ','.join(d['quality_flags']) or '-'))
    if index.get('gaps'):
        print('gaps: %d (see work/index.json)' % len(index['gaps']))
    print('\nNEXT:  python3 scripts/main.py show          # read the material with locators')
    print('       (write your own /app/work/draft.json)')
    print('       python3 scripts/main.py check && python3 scripts/main.py build')
    return 0

def cmd_show(args):
    inp, work, out = paths(args)
    index, _ = load_index(work, inp, args)
    segs = index['segments']
    if args.contract:
        print('== OUTPUT CONTRACT (verbatim keys to be back-filled) ==')
        print(json.dumps(index.get('output_contract'), ensure_ascii=False, indent=2))
        return 0
    if args.seg:
        for s in segs:
            if s['uid'] == args.seg:
                print('[%s]\n%s' % (s['locator'], s['text']))
                return 0
        print('segment %s not found; run `show --outline`' % args.seg)
        return 0
    if args.leads:
        cands = [c for c in index.get('candidates') or [] if not args.facet or c['facet'] == args.facet]
        print('== LEADS (%d) -- confirm, refine or reject each one in draft.json ==' % len(cands))
        for c in cands[:args.limit]:
            print('\n%s [%s/%s] %s  sev_hint=%s' % (c['candidate_id'], c['facet'], c['rule'], c['locator'], c['severity']))
            print('  quote: %s' % c['quote'][:220])
            print('  why  : %s' % c['why'])
            print('  ask  : %s' % c['ask'])
        return 0
    if args.numbers:
        aggs = index['aggs']
        shared = [r for r in aggs['numbers'] if len(r['uids']) >= 2]
        print('== NUMERIC OBJECTS ==  n=%d  shared=%d' % (len(aggs['numbers']), len(shared)))
        rows = shared or aggs['numbers']
        if not shared:
            print('  （没有跨段重复出现的数值；下列为单次出现的数值对象，供核对摘要/表格口径）')
        for rec in rows[:args.limit]:
            print('  %-12s sections=%-24s hits=%d %s' % (rec['token'], ','.join(rec['canons'])[:24] or '-', len(rec['uids']), ','.join(rec['uids'][:3])))
        return 0
    if args.citations:
        aggs = index['aggs']
        print('== CITATION OBJECTS ==  markers=%d  reference_entries=%d  reference_count=%d' % (len(aggs['citations']), aggs['reference_entries'], aggs['reference_count']))
        for c in aggs['citations'][:args.limit]:
            print('  %-14s %-12s %s' % (c['style'], c['raw'][:12], c['uid']))
        return 0
    if args.outline:
        print('== OUTLINE ==')
        for s in index['aggs']['sections']:
            print('  %-3s %-14s segs=%-4d first=%s' % (s['doc_id'], s['canon'], s['segments'], s['first_index']))
        return 0
    if args.grep or args.section or args.doc or args.page:
        picked = segs
        if args.doc:
            picked = [s for s in picked if s['doc_id'] == args.doc]
        if args.section:
            want = core.canon_section(args.section) or args.section.lower()
            picked = [s for s in picked if want in (s['canon'], s['section'].lower()) or args.section.lower() in s['text'].lower()[:400]]
        if args.page:
            picked = [s for s in picked if s['page'] == int(args.page)]
        if args.grep:
            import re as _re
            try:
                rx = _re.compile(args.grep, _re.I)
            except Exception:
                rx = None
            picked = [s for s in picked if (rx.search(s['text']) if rx else args.grep in s['text'])]
        print('== MATERIAL (%d segments shown of %d) ==' % (min(len(picked), args.limit), len(picked)))
        for s in picked[:args.limit]:
            print('\n[%s]\n%s' % (s['locator'], s['text'][:args.chars]))
        if not picked:
            print('no segment matched; try `show --outline` or `show --doc D1`')
        return 0
    print('== CASE ==')
    print('case_id  : %s' % index.get('case_id'))
    print('docs/segs: %s / %s' % (index['counts']['documents'], index['counts']['segments']))
    contract = index.get('output_contract')
    keys = rnd.contract_keys(contract)
    print('contract : %d keys -> %s' % (len(keys), ', '.join(keys) or '(none)'))
    print('\n== OUTLINE ==')
    for s in index['aggs']['sections'][:40]:
        print('  %-3s %-14s segs=%-4d' % (s['doc_id'], s['canon'], s['segments']))
    print('\n== LEADS BY FACET ==')
    counts = {}
    for c in index.get('candidates') or []:
        counts[c['facet']] = counts.get(c['facet'], 0) + 1
    for f in core.FACETS:
        print('  %-12s %2d  %s' % (f, counts.get(f, 0), core.FACET_LABEL[f]))
    print('\n== READ WITH LOCATORS ==')
    print('  show --doc D1 --limit 40         # 逐段读正文（每段带 locator）')
    print('  show --section results           # 只读某章')
    print('  show --seg D1-p3-s12             # 读单段')
    print('  show --leads [--facet citation]  # 看候选线索及需回答的问题')
    print('  show --numbers / --citations     # 数值与引文对象表')
    print('  show --contract                  # 契约原文')
    print('\nQuote strings must be copied verbatim from the text above.')
    return 0

def cmd_check(args):
    inp, work, out = paths(args)
    index, _ = load_index(work, inp, args)
    draft_path = find_draft(work, out)
    draft, derr = load_json(draft_path) if draft_path else (None, 'draft.json not found')
    draft = draft if isinstance(draft, dict) else {}
    raw_findings = draft.get('findings') or []
    findings, issues = core.normalize_findings(index, raw_findings)
    rejected = draft.get('rejected_candidates') or []
    rej_ids = set()
    for r in rejected if isinstance(rejected, list) else []:
        if isinstance(r, dict) and r.get('candidate_id'):
            rej_ids.add(str(r['candidate_id']))
        elif isinstance(r, str):
            rej_ids.add(r)
    used = set()
    for f in findings:
        used.update(f.get('candidate_ids') or [])
    cand_ids = [c['candidate_id'] for c in index.get('candidates') or []]
    untriaged = [c for c in cand_ids if c not in used and c not in rej_ids]
    unknown = sorted([c for c in used if c not in cand_ids])
    coverage = rnd.build_coverage(index, findings, draft)
    keys = rnd.contract_keys(index.get('output_contract'))
    blocking = [i for i in issues if i['level'] == 'error']
    verified = [f for f in findings if f.get('quote_verified')]
    report = {'draft_path': str(draft_path) if draft_path else None, 'draft_error': derr, 'findings_total': len(raw_findings), 'findings_kept': len(findings), 'findings_verified': len(verified), 'findings_downgraded': len(findings) - len(verified), 'issues': issues, 'candidates_total': len(cand_ids), 'candidates_triaged': len([c for c in cand_ids if c in used or c in rej_ids]), 'candidates_rejected': len([c for c in rej_ids if c in cand_ids]), 'untriaged': untriaged, 'unknown_candidate_ids': unknown, 'contract_keys': keys, 'coverage_missing': [f for f in core.FACETS if not coverage.get(f)], 'ready': bool(findings) and (not blocking)}
    write_json(work / 'check_report.json', report)
    print('== CHECK ==')
    if not draft_path:
        print('[FAIL] no draft found (looked for work/draft.json, work/plan.json, output/draft.json)')
    elif derr and derr != 'repaired':
        print('[FAIL] draft load: %s' % derr)
    else:
        print('[PASS] draft loaded: %s (%d findings%s)' % (draft_path, len(raw_findings), '' if derr != 'repaired' else ', JSON repaired'))
    for f in findings[:200]:
        flag = 'PASS' if f.get('quote_verified') else 'FAIL'
        print('[%s] %s %-11s %-9s quote %s -> %s' % (flag, f['finding_id'], f['facet'], f['severity'], 'verified' if f.get('quote_verified') else 'NOT FOUND (will be pending_review)', f['location'].get('locator') or '-'))
    for i in issues[:40]:
        print('[%s] %s: %s' % (i['level'].upper()[:4], i['code'], i['detail']))
    print('--')
    print('findings kept=%d verified=%d downgraded=%d | candidates=%d triaged=%d rejected=%d untriaged=%d' % (len(findings), len(verified), len(findings) - len(verified), len(cand_ids), report['candidates_triaged'], report['candidates_rejected'], len(untriaged)))
    if untriaged:
        print('[WARN] untriaged leads: %s (confirm as finding, or list in draft.rejected_candidates with a reason -- silent skips are recorded as coverage gaps)' % ', '.join(untriaged[:12]))
    if unknown:
        print('[WARN] findings cite unknown candidate_ids: %s' % ', '.join(unknown[:8]))
    print('coverage: %d/%d facets filled | contract keys: %d' % (len([f for f in core.FACETS if coverage.get(f)]), len(core.FACETS), len(keys)))
    print('NEXT: python3 scripts/main.py build   (build finalizes even if this check failed)')
    return 0

def cmd_build(args):
    inp, work, out = paths(args)
    index, _ = load_index(work, inp, args)
    draft_path = find_draft(work, out)
    draft, derr = load_json(draft_path) if draft_path else (None, 'draft.json not found')
    if draft_path and derr and (derr != 'repaired'):
        sys.stderr.write('[warn] draft %s: %s -> fallback path\n' % (draft_path, derr))
        draft = {}
    elif not isinstance(draft, dict):
        draft = {}
    summary = rnd.finalize((inp, work, out), index, draft=draft, stage='build')
    print('== BUILD ==')
    print('draft    : %s' % (draft_path or '(none -> fallback)'))
    print('findings : %d' % len(summary['findings']))
    print('status   : %s' % summary['status'])
    for d in summary['degradations']:
        print('[DEGRADE] %s' % d)
    print('result   : %s' % (out / 'result.json'))
    print('product  : %s' % (out / 'audit_report.md'))
    print('NEXT: python3 scripts/main.py selfcheck   (optional re-validation)')
    return 0

def cmd_selfcheck(args):
    inp, work, out = paths(args)
    res, err = load_json(out / 'result.json')
    index, _ = load_index(work, inp, args)
    print('== SELFCHECK ==')
    if not isinstance(res, dict):
        print('[FAIL] result.json unreadable: %s' % err)
        return 0
    ok = True
    contract = index.get('output_contract') or (res.get('output_contract') if isinstance(res.get('output_contract'), dict) else None)
    keys = rnd.contract_keys(contract)
    missing = [k for k in keys if k not in res]
    if missing:
        ok = False
        print('[FAIL] contract keys missing: %s' % ', '.join(missing))
    else:
        print('[PASS] contract keys present: %d' % len(keys))
    print('[%s] case_id: %r' % ('PASS' if res.get('case_id') is not None else 'WARN', res.get('case_id')))
    print('[%s] status: %r' % ('PASS' if res.get('status') in ('ok', 'partial', 'input_error', 'failed') else 'FAIL', res.get('status')))
    findings = res.get('findings') or []
    bad = [f for f in findings if not core.quote_ok(index, f.get('quote', ''))]
    print('[%s] findings=%d quote-verified=%d' % ('PASS' if findings and (not bad) else 'FAIL', len(findings), len(findings) - len(bad)))
    if bad:
        ok = False
        print('      unverified: %s' % ', '.join((f.get('finding_id', '?') for f in bad[:10])))
    cov = res.get('coverage') or {}
    print('[%s] coverage facets: %d/%d' % ('PASS' if len(cov) >= len(core.FACETS) else 'WARN', len(cov), len(core.FACETS)))
    for name in ('audit_report.md', 'evidence.jsonl', 'run_manifest.json'):
        p = out / name
        size = p.stat().st_size if p.is_file() else 0
        good = size > 0
        ok = ok and good
        print('[%s] %s (%d bytes)' % ('PASS' if good else 'FAIL', name, size))
    print('[%s] overall' % ('PASS' if ok else 'FAIL'))
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(prog='main.py', description='manuscript quality audit skill')
    sub = ap.add_subparsers(dest='cmd')
    for name in ('init', 'check', 'build', 'selfcheck'):
        p = sub.add_parser(name)
        p.add_argument('--input')
        p.add_argument('--work')
        p.add_argument('--output')
    p = sub.add_parser('show')
    p.add_argument('--input')
    p.add_argument('--work')
    p.add_argument('--output')
    p.add_argument('--outline', action='store_true')
    p.add_argument('--doc')
    p.add_argument('--section')
    p.add_argument('--page', type=int)
    p.add_argument('--seg')
    p.add_argument('--grep')
    p.add_argument('--leads', action='store_true')
    p.add_argument('--numbers', action='store_true')
    p.add_argument('--citations', action='store_true')
    p.add_argument('--contract', action='store_true')
    p.add_argument('--facet')
    p.add_argument('--limit', type=int, default=40)
    p.add_argument('--chars', type=int, default=1200)
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    handler = {'init': cmd_init, 'show': cmd_show, 'check': cmd_check, 'build': cmd_build, 'selfcheck': cmd_selfcheck}[args.cmd]
    try:
        handler(args)
    except Exception as exc:
        sys.stderr.write('[error] %s: %s\n%s\n' % (type(exc).__name__, exc, traceback.format_exc(limit=4)))
        try:
            inp, work, out = paths(args)
            res, _ = load_json(out / 'result.json')
            if not isinstance(res, dict):
                write_json(out / 'result.json', {'case_id': None, 'status': 'failed', 'errors': [{'stage': args.cmd, 'detail': str(exc)[:400]}], 'findings': [], 'coverage': {}, 'degradations': ['crash_in_%s' % args.cmd]})
        except Exception:
            pass
    return 0
if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        traceback.print_exc(limit=2)
    sys.exit(0)
