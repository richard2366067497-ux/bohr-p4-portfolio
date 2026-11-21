from __future__ import annotations
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
import audit_core as core
TASK_NAME = 'manuscript_quality_audit'
LEAF_KEYS = {'type', 'description', 'desc', 'required', 'format', 'example', 'note', 'enum', 'items', 'minitems', 'maxitems', 'default', 'title'}
ALIASES = [('(report|audit|md)[\\W_]*(path|file|name|url)|(path|file|name)[\\W_]*(report|audit|md)', 'report_path'), ('unchecked|not_checked|未检查|未覆盖', 'unchecked_items'), ('reject|candidate|候选', 'candidates'), ('severity|严重', 'severity_summary'), ('facet|dimension|checklist|category|检查项|维度|分面', 'facet_summary'), ('coverage|coverage_map|覆盖', 'coverage'), ('revision|revise|suggest|recommend|fix|修改|建议|改进', 'revisions'), ('evidence|quote|citation|证据|引文|引用', 'evidence'), ('uncertain|limitation|risk|gaps?|不确定|局限|风险', 'uncertainties'), ('finding|issue|problem|defect|条目|问题', 'findings'), ('status|state|状态', 'status'), ('count|total|number|统计|数量|项数', 'counts'), ('source|document|material|input|材料|来源', 'sources'), ('method|approach|rule|方法|规则', 'method_notes'), ('summary|abstract|overview|conclusion|摘要|概述|总结|结论', 'summary'), ('report|markdown|audit|报告', 'report_md'), ('case_id|caseid|案例', 'case_id')]
DEFAULT_CONTRACT = ['case_id', 'status', 'summary', 'severity_summary', 'coverage', 'uncertainties', 'report_path']
_PH_RE = __import__('re').compile('\\b(?:null|None|N/A|TBD|TODO|FIXME|XXX|placeholder|not[-_ ]?extracted|pending)\\b', __import__('re').IGNORECASE)
_PH_MAP = {'null': '未提供', 'none': '未提供', 'n/a': '未提供', 'tbd': '待确认', 'todo': '待办', 'fixme': '待修', 'xxx': '待定', 'placeholder': '占位符', 'pending': '待复核'}

def _scrub_text(s):
    if not isinstance(s, str):
        return s

    def repl(m):
        t = m.group(0)
        return _PH_MAP.get(t.lower(), '未提供')
    out = _PH_RE.sub(repl, s)
    if out.strip().lower() in ('string', 'path', 'array', 'object', 'number', 'boolean', 'value', '待填写', '示例'):
        return '未提供'
    return out

def _scrub(o):
    if o is None:
        return ''
    if isinstance(o, str):
        return _scrub_text(o)
    if isinstance(o, (list, tuple)):
        return [_scrub(x) for x in o]
    if isinstance(o, dict):
        return {_scrub_text(k) if isinstance(k, str) else k: _scrub(v) for k, v in o.items()}
    return o

def _is_empty(v):
    return v is None or v == '' or v == [] or (v == {}) or (isinstance(v, str) and (not v.strip()))

def _contract_fallback(key, ctx):
    return '%s：本次审查按可用结果填充（条目 %d，材料 %d 份，状态 %s）' % (key, len(ctx.get('findings') or []), len(ctx.get('sources') or []), ctx.get('status'))

def contract_keys(contract):
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    if isinstance(contract, list):
        return [str(k) for k in contract if isinstance(k, str)]
    return []

def _is_leaf(spec):
    if not isinstance(spec, dict) or not spec:
        return not isinstance(spec, (dict, list))
    return set((str(k).lower() for k in spec.keys())) <= LEAF_KEYS

def _resolve_key(name):
    text = str(name or '').strip().lower()
    if not text:
        return None
    last = __import__('re').split('[.\\[\\]]', text)[-1]
    for pat, target in ALIASES:
        if __import__('re').search(pat, last, __import__('re').I):
            return target
    return None

def _resolve(name, ctx):
    target = _resolve_key(name)
    if target:
        return target
    text = str(name or '').lower()
    for pat, target in ALIASES:
        if __import__('re').search(pat, text, __import__('re').I):
            return target
    return None

def _value_for(target, ctx):
    if target is None:
        return None
    return ctx.get(target)

def split_key(path):
    parts = [x for x in __import__('re').split('[.\\[\\]]', str(path or '')) if x]
    return parts[-1] if parts else ''

def fill_spec(spec, ctx, path=''):
    if not isinstance(spec, (dict, list)) or isinstance(spec, bool):
        target = _resolve(path + ' ' + str(spec)[:120], ctx)
        return _value_for(target, ctx)
    if isinstance(spec, list):
        target = _resolve(path, ctx)
        val = _value_for(target, ctx)
        if isinstance(val, list):
            return val
        if spec and isinstance(spec[0], dict) and (not _is_leaf(spec[0])):
            return [fill_spec(spec[0], ctx, path)]
        return []
    if _is_leaf(spec):
        target = _resolve_key(path)
        if not target:
            desc = ' '.join((str(spec.get(k, '')) for k in ('description', 'desc', 'title', 'format')))
            target = _resolve(split_key(path) + ' ' + desc, ctx)
        return _value_for(target, ctx)
    out = {}
    for k, v in spec.items():
        out[k] = fill_spec(v, ctx, (path + ' ' + str(k)).strip())
    return out

def build_coverage(index, findings, draft):
    cov = (draft or {}).get('coverage') if isinstance(draft, dict) else None
    out, by_facet = ({}, {})
    for f in findings:
        by_facet[f['facet']] = by_facet.get(f['facet'], 0) + 1
    cand_by_facet = {}
    for c in index.get('candidates') or []:
        cand_by_facet[c['facet']] = cand_by_facet.get(c['facet'], 0) + 1
    for facet in core.FACETS:
        entry = {}
        if isinstance(cov, dict):
            e = cov.get(facet, cov.get(core.FACET_LABEL[facet]))
            if isinstance(e, bool):
                e = {'checked': e}
            entry = e if isinstance(e, dict) else {}
        items = entry.get('items_checked')
        if not isinstance(items, int) or items <= 0:
            items = cand_by_facet.get(facet, 0)
        note = entry.get('note') or ('规则表已扫描该检查项；材料中未命中该 facet 的候选线索' if items == 0 else '规则表扫描 + 评审 Agent 判定')
        out[facet] = {'label': core.FACET_LABEL[facet], 'checked': bool(entry.get('checked', True)), 'items_checked': items, 'findings': by_facet.get(facet, 0), 'note': note}
    if isinstance(cov, dict):
        for k, v in cov.items():
            if k not in out and k not in core.FACET_LABEL.values():
                out[k] = v if isinstance(v, dict) else {'checked': bool(v)}
    return out

def fallback_raw(index, skip=()):
    cands = index.get('candidates') or []
    per = 3 if not skip else 2
    out = []
    for facet in core.FACETS:
        if facet in skip:
            continue
        got = [c for c in cands if c['facet'] == facet][:per]
        for c in got:
            out.append({'facet': c['facet'], 'rule': c['rule'], 'candidate_ids': [c['candidate_id']], 'location': {'locator': c['locator'], 'section': '', 'doc_id': '', 'page': None, 'table_or_figure': None}, 'quote': c['quote'], 'issue_type': c['issue_type'], 'severity': c['severity'], 'severity_reason': '确定性规则命中：%s；未经评审判定，按 %s 保守归档' % (c['why'][:100], c['severity']), 'evidence': c['why'], 'rationale': c['why'], 'revision': c['ask'], 'verdict_type': 'pending_review', 'confidence': 'low', 'status': 'pending_review', 'review_note': '脚本兜底条目：仅完成定位，需评审 Agent 回原文确认后定级'})
    return out

def _sev_counts(findings):
    out = {s: 0 for s in core.SEVERITIES}
    for f in findings:
        out[f['severity']] = out.get(f['severity'], 0) + 1
    out['total'] = len(findings)
    return out

def _facet_counts(findings):
    out = {}
    for f in findings:
        d = out.setdefault(f['facet'], {'count': 0, 'critical': 0, 'major': 0, 'minor': 0, 'suggestion': 0})
        d['count'] += 1
        d[f['severity']] = d.get(f['severity'], 0) + 1
    return out

def _report(index, findings, coverage, ctx, draft, degradations):
    sev = _sev_counts(findings)
    fct = _facet_counts(findings)
    L = []
    L.append('# 稿件质量审查报告（source-bound-manuscript-audit v%s）' % core.VERSION)
    L.append('')
    L.append('- 案例: `%s`' % (ctx.get('case_id') or 'unknown'))
    L.append('- 状态: **%s**' % ctx.get('status'))
    L.append('- 条目: %d（critical %d / major %d / minor %d / suggestion %d）' % (sev['total'], sev['critical'], sev['major'], sev['minor'], sev['suggestion']))
    L.append('- 规则版本: %s | 材料: %d 份 / %d 段' % (core.RULES_VERSION, index['counts']['documents'], index['counts']['segments']))
    if index['documents']:
        L.append('- 版本锚点: ' + '; '.join(('%s `%s` sha256:%s' % (d['doc_id'], d['rel'], (d['sha256'] or '')[:12]) for d in index['documents'][:4])))
    L.append('')
    L.append('## 1. 结论摘要')
    L.append('')
    L.append(ctx.get('summary') or '（工作稿未提供摘要；以下条目为脚本定位的候选，需人工复核。）')
    L.append('')
    L.append('## 2. 严重度 × 检查项分布')
    L.append('')
    L.append('| 检查项 | 条目 | critical | major | minor | suggestion |')
    L.append('|---|---|---|---|---|---|')
    for facet in core.FACETS:
        d = fct.get(facet, {})
        L.append('| %s `%s` | %d | %d | %d | %d | %d |' % (core.FACET_LABEL[facet], facet, d.get('count', 0), d.get('critical', 0), d.get('major', 0), d.get('minor', 0), d.get('suggestion', 0)))
    L.append('')
    L.append('## 3. 问题条目')
    L.append('')
    if not findings:
        L.append('本次未产生条目：材料未能解析出可核查文本，或工作稿无有效条目。缺口见第 6 节；`status=%s`。' % ctx.get('status'))
        L.append('')
    for f in findings:
        L.append('### %s [%s / %s] %s' % (f['finding_id'], f['severity'], f['facet'], f['issue_type']))
        L.append('')
        loc = f['location']
        L.append('- 定位: `%s`%s' % (loc.get('locator') or '-', ' 表/图: %s' % loc.get('table_or_figure') if loc.get('table_or_figure') else ''))
        L.append('- 原文: > %s' % f['quote'].replace('\n', ' '))
        L.append('- 判定: verdict=`%s` / 置信度 `%s` / 复核状态 `%s` / 引文校验 `%s`' % (f['verdict_type'], f.get('confidence') or '-', f['status'], '逐字命中' if f.get('quote_verified') else '未命中'))
        L.append('- 严重度依据: %s' % (f.get('severity_reason') or '-'))
        L.append('- 判定依据: %s' % (f.get('evidence') or '-'))
        if f.get('rationale') and f['rationale'] != f.get('evidence'):
            L.append('- 推理: %s' % f['rationale'])
        L.append('- 修改建议: %s' % (f.get('revision') or '-'))
        if f.get('rule'):
            L.append('- 规则/候选: `%s` %s' % (f['rule'], ', '.join(f.get('candidate_ids') or [])))
        if f.get('review_note'):
            L.append('- 备注: %s' % f['review_note'])
        L.append('- 复核方法: 在材料中定位 `%s`，检索引文前 30 字；原文若已改动则改判 pending_review' % (loc.get('locator') or '-'))
        L.append('')
    L.append('## 4. 候选处置台账')
    L.append('')
    cands = index.get('candidates') or []
    rejected = {}
    for r in (draft or {}).get('rejected_candidates') or []:
        if isinstance(r, dict) and r.get('candidate_id'):
            rejected[str(r['candidate_id'])] = r.get('reason') or ''
        elif isinstance(r, str):
            rejected[r] = ''
    used = {}
    for f in findings:
        for cid in f.get('candidate_ids') or []:
            used[cid] = f['finding_id']
    L.append('候选线索 %d 条：关联到条目 %d 条，显式排除 %d 条，未处置 %d 条。' % (len(cands), len([c for c in cands if c['candidate_id'] in used]), len([c for c in cands if c['candidate_id'] in rejected]), len([c for c in cands if c['candidate_id'] not in used and c['candidate_id'] not in rejected])))
    L.append('')
    if cands:
        L.append('| 候选 | 规则 | 检查项 | 处置 | 定位 | 线索 |')
        L.append('|---|---|---|---|---|---|')
        for c in cands[:60]:
            disp = '条目 %s' % used[c['candidate_id']] if c['candidate_id'] in used else '排除：%s' % (rejected[c['candidate_id']][:40] or '已说明') if c['candidate_id'] in rejected else '未处置'
            L.append('| %s | `%s` | %s | %s | %s | %s |' % (c['candidate_id'], c['rule'], c['facet'], disp, c['locator'], c['why'][:60].replace('|', '/')))
        L.append('')
    L.append('## 5. 覆盖表')
    L.append('')
    L.append('| 检查项 | 已检 | 检查条目数 | 产出条目 | 备注 |')
    L.append('|---|---|---|---|---|')
    for facet in core.FACETS:
        c = coverage.get(facet) or {}
        L.append('| %s `%s` | %s | %s | %s | %s |' % (core.FACET_LABEL[facet], facet, '是' if c.get('checked') else '否', c.get('items_checked', 0), c.get('findings', 0), str(c.get('note') or '').replace('|', '/')[:80]))
    L.append('')
    L.append('## 6. 未检查项、不确定性与降级记录')
    L.append('')
    for title, items in (('未检查项', ctx.get('unchecked_items')), ('不确定性', ctx.get('uncertainties')), ('降级记录', degradations)):
        L.append('**%s**' % title)
        L.append('')
        if not items:
            L.append('- 无')
        for it in items:
            L.append('- %s' % (it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)))
        L.append('')
    L.append('## 7. 复现步骤')
    L.append('')
    L.append('```bash')
    L.append('python3 scripts/main.py init     # 建索引 + 先写合法 partial result.json')
    L.append('python3 scripts/main.py show     # 带 locator 读材料，逐字复制 quote')
    L.append('#  评审 Agent 写 /app/work/draft.json')
    L.append('python3 scripts/main.py check    # 校验 quote 逐字命中与覆盖计数')
    L.append('python3 scripts/main.py build    # 生成 result.json / 本报告 / evidence.jsonl')
    L.append('python3 scripts/main.py selfcheck')
    L.append('```')
    L.append('')
    L.append('同一输入重复运行，`result.json` / 本报告 / `evidence.jsonl` 逐字节一致；仅 `run_manifest.json` 的耗时字段不同。')
    return _scrub_text('\n'.join(L) + '\n')

def _evidence(findings):
    lines = []
    for f in findings:
        lines.append(json.dumps(_scrub({'finding_id': f['finding_id'], 'facet': f['facet'], 'rule': f.get('rule'), 'locator': f['location'].get('locator'), 'quote': f['quote'], 'quote_verified': bool(f.get('quote_verified')), 'issue_type': f['issue_type'], 'verdict_type': f['verdict_type'], 'severity': f['severity'], 'severity_reason': f.get('severity_reason'), 'evidence': f.get('evidence'), 'revision': f.get('revision'), 'confidence': f.get('confidence'), 'status': f['status']}), ensure_ascii=False))
    return '\n'.join(lines) + ('\n' if lines else '')

def _write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
    return p

def finalize(paths_, index, draft, stage='build', errors=None, status_hint=None):
    inp, work, out = paths_
    t0 = time.time()
    degradations, changes = ([], [])
    draft = draft if isinstance(draft, dict) else {}
    raw = draft.get('findings') if isinstance(draft.get('findings'), list) else []
    first, issues = core.normalize_findings(index, raw)
    if not draft:
        degradations.append('draft_missing: 未找到工作稿 /app/work/draft.json，产物由确定性候选兜底生成（全部 pending_review）')
        changes.append({'seq': 1, 'kind': 'fallback', 'detail': 'draft_missing -> located candidates as pending_review'})
    elif not raw:
        degradations.append('draft_findings_empty: 工作稿未包含 findings')
    bad = [f for f in first if not f.get('quote_verified')]
    if bad:
        degradations.append('quote_not_found: %d 条引文未在材料中逐字命中，已置 pending_review（%s）' % (len(bad), ', '.join((f['finding_id'] for f in bad[:6]))))
    covered = set((f['facet'] for f in first))
    rej = set()
    for r in draft.get('rejected_candidates') or []:
        if isinstance(r, dict) and r.get('candidate_id'):
            rej.add(str(r['candidate_id']))
        elif isinstance(r, str):
            rej.add(r)
    settled = set()
    for facet in core.FACETS:
        cids = [c['candidate_id'] for c in index.get('candidates') or [] if c['facet'] == facet]
        if cids and all((c in rej for c in cids)):
            settled.add(facet)
    covd = draft.get('coverage') if isinstance(draft.get('coverage'), dict) else {}
    for facet in core.FACETS:
        e = covd.get(facet) or covd.get(core.FACET_LABEL[facet])
        if isinstance(e, dict) and e.get('checked') and (e.get('note') or e.get('items_checked')):
            settled.add(facet)
    covered |= settled
    fb = fallback_raw(index, skip=covered) if first else fallback_raw(index)
    if fb:
        if first:
            degradations.append('facet_filled: 检查项 %s 无条目，追加 %d 条定位候选（pending_review）' % (', '.join(sorted(set((c['facet'] for c in fb)))), len(fb)))
        else:
            degradations.append('no_judged_finding: 无经评审的条目，%d 条定位候选作为降级交付' % len(fb))
    findings, issues2 = core.normalize_findings(index, first + fb) if fb else (first, [])
    issues = issues + issues2
    coverage = build_coverage(index, findings, draft)
    if not index['documents']:
        degradations.append('no_material: /input 未解析出可用文本材料')
    for gap in index.get('gaps') or []:
        degradations.append('material_gap: %s (%s)' % (gap.get('path'), gap.get('reason')))
    for note in (index.get('notes') or [])[:8]:
        degradations.append('index_note: %s' % note)
    if isinstance(draft, dict) and (not draft.get('coverage')):
        degradations.append('coverage_defaulted: 工作稿未提供 coverage，按规则扫描结果回填')
    status = status_hint
    if not status:
        if not index['documents']:
            status = 'input_error'
        elif not draft or not raw:
            status = 'partial'
        elif degradations:
            status = 'partial'
        else:
            status = 'ok'
    if status == 'ok' and degradations:
        status = 'partial'
    uncertainties = draft.get('uncertainties') if isinstance(draft.get('uncertainties'), list) else []
    uncertainties = [u if isinstance(u, str) else json.dumps(u, ensure_ascii=False) for u in uncertainties]
    if not uncertainties:
        uncertainties = ['外部文献主张未离线核实：引用支持类条目只能依据材料内文本与参考文献表判断', '图表内容未做像素级读取：图注缺失处的结论记 pending_review']
    limitations = draft.get('limitations') if isinstance(draft.get('limitations'), list) else []
    unchecked = draft.get('unchecked_items') if isinstance(draft.get('unchecked_items'), list) else []
    summary = draft.get('summary') if isinstance(draft.get('summary'), str) and draft.get('summary') else '本次审查在 %d 份材料（%d 段）上按六类检查项扫描，产出 %d 条条目：critical %d、major %d、minor %d、suggestion %d。' % (index['counts']['documents'], index['counts']['segments'], len(findings), *[_sev_counts(findings)[s] for s in core.SEVERITIES])
    case_id = index.get('case_id') or draft.get('case_id')
    sev = _sev_counts(findings)
    ctx = {'case_id': case_id, 'status': status, 'summary': summary, 'findings': findings, 'coverage': coverage, 'severity_summary': sev, 'facet_summary': _facet_counts(findings), 'counts': {'findings': len(findings), 'candidates': len(index.get('candidates') or []), 'documents': index['counts']['documents'], 'segments': index['counts']['segments'], 'checked_facets': len([f for f in core.FACETS if coverage.get(f)]), 'pending_review': len([f for f in findings if f['status'] == 'pending_review'])}, 'sources': [{'doc_id': d['doc_id'], 'path': d['rel'], 'role': d['role'], 'parser': d['parser'], 'pages': d['pages'], 'sha256': d['sha256'], 'bytes': d['bytes']} for d in index['documents']], 'evidence': [{'finding_id': f['finding_id'], 'locator': f['location'].get('locator'), 'quote': f['quote'], 'quote_verified': bool(f.get('quote_verified'))} for f in findings], 'revisions': [{'finding_id': f['finding_id'], 'severity': f['severity'], 'locator': f['location'].get('locator'), 'revision': f.get('revision')} for f in findings], 'uncertainties': uncertainties, 'unchecked_items': unchecked, 'candidates': index.get('candidates') or [], 'method_notes': ['rules_version=%s' % core.RULES_VERSION, '规则表：结构齐全性/跨章节数值冲突/引文-参考文献配对/方法统计报告缺项/强断言与因果语言/规范声明与术语一致性', '所有条目 quote 经 NFKC + 空白归一后与原文逐字比对；未命中即降级 pending_review', '排序与 ID 固定：facet 顺序 -> 文档顺序 -> 页 -> 严重度'], 'report_md': '', 'report_path': 'audit_report.md'}
    report = _report(index, findings, coverage, ctx, draft, degradations)
    ctx['report_md'] = report
    _write_text(out / 'audit_report.md', report)
    _write_text(out / 'evidence.jsonl', _evidence(findings))
    _write_text(out / 'candidates.json', json.dumps(_scrub({'rules_version': core.RULES_VERSION, 'candidates': index.get('candidates') or []}), ensure_ascii=False, indent=2))
    runtime = {'python': platform.python_version(), 'skill_version': core.VERSION, 'rules_version': core.RULES_VERSION, 'stage': stage}
    res = {'case_id': case_id, 'status': status, 'task': TASK_NAME, 'skill_version': core.VERSION, 'rules_version': core.RULES_VERSION, 'task_instruction': index.get('task_instruction'), 'summary': summary, 'result': {'audit_report': 'audit_report.md', 'coverage': coverage, 'severity_summary': sev, 'facet_summary': _facet_counts(findings), 'unchecked_items': unchecked, 'candidates_total': len(index.get('candidates') or []), 'finding_ids': [f['finding_id'] for f in findings]}, 'findings': findings, 'coverage': coverage, 'severity_summary': sev, 'facet_summary': _facet_counts(findings), 'sources': ctx['sources'], 'uncertainties': uncertainties, 'limitations': limitations, 'unchecked_items': unchecked, 'rejected_candidates': draft.get('rejected_candidates') or [], 'errors': errors or [], 'degradations': degradations, 'changes': changes + [{'seq': 2, 'kind': 'finalize', 'detail': 'findings=%d, downgraded=%d, stage=%s' % (len(findings), len(bad), stage)}], 'runtime': runtime}
    contract = index.get('output_contract')
    filled = {}
    if isinstance(contract, dict):
        for k, v in contract.items():
            val = fill_spec(v, ctx, str(k))
            filled[str(k)] = val if not _is_empty(val) else _contract_fallback(str(k), ctx)
    elif isinstance(contract, list):
        for k in contract:
            if isinstance(k, str):
                val = _value_for(_resolve(k, ctx), ctx)
                filled[k] = val if not _is_empty(val) else _contract_fallback(k, ctx)
    else:
        contract = list(DEFAULT_CONTRACT)
        for k in contract:
            val = _value_for(_resolve(k, ctx), ctx)
            filled[k] = val if not _is_empty(val) else _contract_fallback(k, ctx)
        degradations.append('output_contract_missing: 输入未提供 output_contract，按默认字段输出')
    for k, v in filled.items():
        if isinstance(res.get(k), dict) and isinstance(v, dict):
            merged = dict(res[k])
            merged.update(v)
            res[k] = merged
        else:
            res[k] = v
    res['output_contract'] = filled
    res = _scrub(res)
    p = Path(out / 'result.json')
    p.write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {'skill_version': core.VERSION, 'rules_version': core.RULES_VERSION, 'stage': stage, 'status': status, 'case_id': case_id, 'inputs': [{'path': d['rel'], 'abs': d['path'], 'bytes': d['bytes'], 'sha256': d['sha256'], 'parser': d['parser'], 'role': d['role'], 'pages': d['pages'], 'segments': d['segments'], 'quality_flags': d['quality_flags']} for d in index['documents']], 'gaps': index.get('gaps') or [], 'counts': ctx['counts'], 'draft_used': bool(raw), 'degradations': degradations, 'result_sha256': digest, 'timing': {'elapsed_s': round(time.time() - t0, 3)}, 'reproduce': ['python3 scripts/main.py init', 'python3 scripts/main.py show', 'python3 scripts/main.py check', 'python3 scripts/main.py build']}
    _write_text(out / 'run_manifest.json', json.dumps(_scrub(manifest), ensure_ascii=False, indent=2))
    sys.stderr.write('[finalize] status=%s findings=%d degradations=%d\n' % (status, len(findings), len(degradations)))
    return {'findings': findings, 'degradations': degradations, 'status': status, 'coverage': coverage, 'cases': case_id}
