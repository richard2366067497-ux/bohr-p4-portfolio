from __future__ import annotations
import hashlib
import html
import importlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
import zipfile
import zlib
from pathlib import Path
VERSION = '1.0.0'
RULES_VERSION = '2026-11-18'
FACETS = ('struct', 'consistency', 'citation', 'method', 'statistics', 'logic', 'compliance')
FACET_LABEL = {'struct': '结构与完整性', 'consistency': '事实/数值一致性', 'citation': '引用支持', 'method': '方法设计', 'statistics': '统计报告', 'logic': '论证链', 'compliance': '学术规范'}
ISSUE_TYPES = ('fact_error', 'insufficient_evidence', 'reporting_gap', 'method_flaw', 'statistical_misreport', 'logic_gap', 'compliance', 'citation_unsupported', 'improvement')
SEVERITIES = ('critical', 'major', 'minor', 'suggestion')
VERDICTS = ('error', 'insufficient_evidence', 'compliance', 'suggestion', 'pending_review')
SEV_RANK = {'critical': 0, 'major': 1, 'minor': 2, 'suggestion': 3}
MAX_SEG_CHARS = 1200
MAX_DOC_BYTES = 12 * 1024 * 1024
MAX_SEGMENTS = 6000
TEXT_EXT = {'.txt', '.md', '.markdown', '.text', '.rst', '.tex', '.csv', '.tsv', '.json', '.jsonl', '.yaml', '.yml', '.bib', '.html', '.htm', '.xml', '.log'}
IMG_EXT = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.svg', '.webp'}
HEAD_WORDS = 'abstract|摘\\s*要|introduction|引\\s*言|前\\s*言|related\\s+work|相关工作|background|研究背景|materials?\\s+and\\s+methods?|methods?|methodology|实验方法|材料与方法|材料和方法|方\\s*法|results?|结\\s*果|discussion|讨\\s*论|conclusions?|结\\s*论|references?|参\\s*考\\s*文\\s*献|bibliography|acknowledg\\w*|致\\s*谢|funding|基\\s*金|appendix|附\\s*录|supplementary|data\\s+availability|数据可用性|author\\s+contributions|作者贡献|ethics|伦\\s*理|conflict\\s+of\\s+interest|利益冲突|limitations?|局\\s*限|supporting\\s+information'
HEAD = re.compile('^(?:(?:\\d+(?:\\.\\d+)*)[.)]?\\s+)?(?:' + HEAD_WORDS + ')\\b', re.I)
NUM_HEAD = re.compile('^\\d{1,2}(?:\\.\\d{1,2})*\\.?\\s+[\\u4e00-\\u9fffA-Z][^。！？.!?]{0,70}$')
_CANON = [('abstract', 'abstract|摘\\s*要'), ('introduction', 'introduction|引\\s*言|前\\s*言|related\\s+work|相关工作|background'), ('methods', 'method|材料与方法|材料和方法|实验方法|方\\s*法'), ('results', 'results?|结\\s*果'), ('discussion', 'discussion|讨\\s*论'), ('conclusion', 'conclusions?|结\\s*论'), ('references', 'references?|参\\s*考\\s*文\\s*献|bibliography'), ('ack', 'acknowledg|致\\s*谢'), ('appendix', 'appendix|附\\s*录|supplementary|supporting\\s+information'), ('availability', 'data\\s+availability|数据可用性|code\\s+availability'), ('ethics', 'ethics|伦\\s*理'), ('coi', 'conflict\\s+of\\s+interest|利益冲突'), ('funding', 'funding|基\\s*金'), ('limitations', 'limitations?|局\\s*限')]
_WS = re.compile('[ \\t\\u3000\\xa0]+')
_ALLWS = re.compile('\\s+')
NUMU = re.compile('(?<![\\w.])[-+]?(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?\\s?(?:%|‰|mg|kg|μg|ug|ng|g|mm|cm|km|nm|μm|µm|mL|ml|μL|uL|L|ms|min|h|Hz|kHz|MHz|eV|kJ|mol|mmol|kPa|MPa|GPa|Pa|°C|℃|K|倍|fold|例|名|人|只|株|份)?')

def norm(s):
    s = unicodedata.normalize('NFKC', str(s or ''))
    s = s.replace('\xad', '').replace('’', "'").replace('‘', "'")
    s = s.replace('“', '"').replace('”', '"').replace('−', '-')
    s = re.sub('-\\s*\\n\\s*', '-', s)
    return _WS.sub(' ', s.replace('\r\n', '\n').replace('\r', '\n')).strip()

def squeeze(s):
    return _ALLWS.sub('', norm(s))

def sha256_file(p):
    h = hashlib.sha256()
    try:
        with open(p, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 16), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ''

def canon_section(name):
    s = norm(name).lower()
    for key, pat in _CANON:
        if re.search(pat, s, re.I):
            return key
    return 'other' if s else ''

def strip_deco(line):
    s = line.strip()
    s = re.sub('^\\#{1,6}\\s*', '', s)
    s = re.sub('^\\\\[a-zA-Z]+\\*?(?:\\[[^\\]]*\\])?\\{', '', s)
    s = re.sub('[*_`]+$', '', s).strip()
    return s.strip()

def is_heading(line):
    raw = line.strip()
    s = strip_deco(raw)
    if not s or len(s) > 90:
        return False
    if raw.startswith('#') or raw.startswith('\\section') or raw.startswith('\\subsection'):
        return True
    if re.search('[。．.！？]$', s):
        return False
    if len(s.split()) > 12 or len(s) > 70:
        return False
    return bool(HEAD.match(s) or NUM_HEAD.match(s))

def _read_text(p):
    data = p.read_bytes()
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            return (data.decode('utf-16'), 'utf-16')
        except (UnicodeDecodeError, UnicodeError):
            pass
    for enc in ('utf-8', 'gb18030', 'big5'):
        try:
            return (data.decode(enc), enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return (data.decode('utf-8', 'ignore'), 'utf-8-ignore')

def _docx_text(p):
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.endswith('document.xml')]
        if not names:
            return ''
        xml = z.read(names[0]).decode('utf-8', 'ignore')
    xml = re.sub('</w:p>', '\n\n', xml)
    xml = re.sub('<w:tab[^>]*/>', ' ', xml)
    xml = re.sub('<w:br[^>]*/>', '\n', xml)
    xml = re.sub('<[^>]+>', '', xml)
    return html.unescape(xml)

def _raw_pdf_streams(p):
    try:
        data = p.read_bytes()
    except Exception:
        return ''
    out, total = ([], 0)
    for m in re.finditer(b'stream\\r?\\n', data):
        start, end = (m.end(), data.find(b'endstream', m.end()))
        if end < 0:
            continue
        chunk = data[start:end]
        try:
            chunk = zlib.decompress(chunk)
        except Exception:
            pass
        for t in re.findall(b'\\((?:\\\\.|[^\\\\()]){1,400}\\)', chunk)[:2000]:
            s = re.sub(b'\\\\([()\\\\])', b'\\1', t[1:-1])
            piece = s.decode('latin-1', 'ignore')
            out.append(piece)
            total += len(piece)
        if total > 1500000:
            break
    return ' '.join(out)

def _pdf_text(p):
    if shutil.which('pdftotext'):
        try:
            r = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(p), '-'], capture_output=True, timeout=90)
            txt = r.stdout.decode('utf-8', 'ignore')
            if r.returncode == 0 and txt.strip():
                return (txt, 'pdftotext')
        except Exception:
            pass
    for mod in ('pypdf', 'PyPDF2'):
        try:
            m = importlib.import_module(mod)
            reader = m.PdfReader(str(p))
            pages = []
            for pg in reader.pages[:400]:
                try:
                    pages.append(pg.extract_text() or '')
                except Exception:
                    pages.append('')
            txt = '\x0c'.join(pages)
            if txt.strip():
                return (txt, mod)
        except Exception:
            continue
    try:
        m = importlib.import_module('pdfminer.high_level')
        txt = m.extract_text(str(p)) or ''
        if txt.strip():
            return (txt, 'pdfminer')
    except Exception:
        pass
    txt = _raw_pdf_streams(p)
    return (txt, 'raw_stream') if txt.strip() else ('', 'none')

def read_document(p):
    ext = p.suffix.lower()
    try:
        if ext == '.docx':
            return (_docx_text(p), 'docx-xml', '')
        if ext == '.pdf':
            txt, how = _pdf_text(p)
            note = '' if txt.strip() else 'pdf_no_text_layer: 需 OCR 或渲染读页'
            return (txt, how, note)
        if ext in TEXT_EXT or ext == '':
            txt, enc = _read_text(p)
            if ext in ('.html', '.htm', '.xml'):
                txt = html.unescape(re.sub('<(script|style)[^>]*>.*?</\\1>', ' ', txt, flags=re.S | re.I))
                txt = re.sub('<[^>]+>', ' ', txt)
            return (txt, 'text:' + enc, '')
        if ext in IMG_EXT:
            return ('', 'image-skip', 'image_material: 只登记，不猜像素内容，需人工读图')
        return (_read_text(p)[0], 'raw-bytes', '')
    except Exception as exc:
        return ('', 'error', '%s: %s' % (type(exc).__name__, exc))

def quality_flag(text):
    flags = []
    n = len(text)
    if n < 400:
        flags.append('very_short')
    cjk = len(re.findall('[\\u4e00-\\u9fff]', text))
    alnum = len(re.findall('[A-Za-z0-9]', text))
    if n > 2000 and (cjk + alnum) / float(n) < 0.35:
        flags.append('low_text_signal')
    if re.search('\\(cid:\\d+\\)', text):
        flags.append('cid_glyphs')
    if n and text.count('�') / float(n) > 0.01:
        flags.append('replacement_chars')
    return flags

def _join_lines(lines):
    out = ''
    for ln in lines:
        ln = ln.rstrip()
        if not ln:
            continue
        if not out:
            out = ln
            continue
        prev, nxt = (out[-1], ln[:1])
        if prev in '-—' and (not out.endswith('--')):
            out = out[:-1] + ln
        elif re.match('[\\u4e00-\\u9fff。，、；：）】”]', prev) or re.match('[\\u4e00-\\u9fff（【“]', nxt) or prev in '(（[【':
            out += ln
        elif re.match('[a-z,;:)\\]]', nxt):
            out += ' ' + ln
        else:
            out += ' ' + ln
    return norm(out)

def _chunk(text):
    if len(text) <= MAX_SEG_CHARS:
        return [text]
    parts, buf = ([], '')
    for sent in re.split('(?<=[。！？.!?])\\s+', text):
        if not sent:
            continue
        if buf and len(buf) + len(sent) + 1 > MAX_SEG_CHARS:
            parts.append(buf.strip())
            buf = sent
        else:
            buf = (buf + ' ' + sent).strip()
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text[:MAX_SEG_CHARS]]

def parse_document(text):
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return []
    pages = text.split('\x0c') if '\x0c' in text else [text]
    blocks, section = ([], '')
    for pno, page in enumerate(pages, 1):
        cur, items = ([], [])
        for raw in page.split('\n'):
            s = raw.strip()
            if not s:
                if cur:
                    items.append(cur)
                    cur = []
                continue
            if is_heading(s):
                if cur:
                    items.append(cur)
                    cur = []
                items.append(['__H__', s])
                continue
            cur.append(raw)
        if cur:
            items.append(cur)
        for it in items:
            if it and it[0] == '__H__':
                section = norm(strip_deco(it[1]))
                continue
            body = _join_lines(it)
            if body:
                blocks.append((pno, section, body))
    return blocks

def build_index(input_dir, case, task_text):
    input_dir = Path(input_dir)
    docs, segments, notes, gaps = ([], [], [], [])
    files = []
    try:
        files = sorted([p for p in input_dir.rglob('*') if p.is_file() and (not p.name.startswith('.'))])
    except Exception as exc:
        notes.append('scan_failed: %s' % exc)
    text_docs = []
    for p in files[:400]:
        rel = str(p.relative_to(input_dir))
        if p.name in ('case.json', 'task.md'):
            continue
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        if size > MAX_DOC_BYTES:
            gaps.append({'path': rel, 'reason': 'file_too_large', 'bytes': size})
            continue
        if p.suffix.lower() in IMG_EXT:
            gaps.append({'path': rel, 'reason': 'image_material_not_read_as_text', 'bytes': size})
            continue
        txt, how, note = read_document(p)
        if note:
            gaps.append({'path': rel, 'reason': note, 'bytes': size})
        if not (txt or '').strip():
            if not note:
                gaps.append({'path': rel, 'reason': 'no_extractable_text', 'bytes': size})
            continue
        text_docs.append((p, rel, size, txt, how))
    biggest = max(text_docs, key=lambda t: len(t[3]))[1] if text_docs else ''
    for p, rel, size, txt, how in text_docs:
        low = rel.lower()
        if re.search('response|rebuttal|回复|答复|cover.?letter', low):
            role = 'response_letter'
        elif re.search('\\.bib$|references?[/_.]|参考', low):
            role = 'bibliography'
        elif re.search('supp|appendix|附录|si[_.]', low):
            role = 'supplement'
        elif rel == biggest:
            role = 'manuscript'
        else:
            role = 'supporting'
        docs.append({'doc_id': '', 'path': str(p), 'rel': rel, 'fmt': p.suffix.lower().lstrip('.'), 'role': role, 'bytes': size, 'sha256': sha256_file(p), 'parser': how, 'chars': len(txt), 'segments': 0, 'pages': txt.count('\x0c') + 1, 'quality_flags': quality_flag(txt)})
        idx_doc = len(docs) - 1
        for pno, sec, body in parse_document(txt):
            for part in _chunk(body):
                if len(segments) >= MAX_SEGMENTS:
                    notes.append('segment_cap_reached')
                    break
                segments.append({'uid': '', 'doc_id': 'D%d' % (idx_doc + 1), 'page': pno, 'section': sec, 'canon': canon_section(sec), 'para': 0, 'locator': '', 'text': part})
        docs[idx_doc]['doc_id'] = 'D%d' % (idx_doc + 1)
    counters, running = ({}, {})
    for seg in segments:
        key = (seg['doc_id'], seg['canon'], seg['page'])
        counters[key] = counters.get(key, 0) + 1
        seg['para'] = counters[key]
        running[seg['doc_id']] = running.get(seg['doc_id'], 0) + 1
        seg['uid'] = '%s-p%d-s%d' % (seg['doc_id'], seg['page'], running[seg['doc_id']])
        loc = '%s p.%d ¶%d' % (seg['doc_id'], seg['page'], seg['para'])
        if seg['section']:
            loc += ' §' + seg['section'][:48]
        seg['locator'] = loc
        docs[int(seg['doc_id'][1:]) - 1]['segments'] += 1
    index = {'version': VERSION, 'rules_version': RULES_VERSION, 'case_id': (case or {}).get('case_id') or (case or {}).get('id'), 'task_instruction': (case or {}).get('task_instruction') or (task_text or '')[:4000], 'output_contract': (case or {}).get('output_contract'), 'case_keys': sorted([k for k in (case or {}).keys()]) if isinstance(case, dict) else [], 'documents': docs, 'segments': segments, 'gaps': gaps, 'notes': notes, 'input_dir': str(input_dir), 'counts': {'documents': len(docs), 'segments': len(segments), 'chars': sum((d['chars'] for d in docs))}}
    index['aggs'] = aggregate(index)
    return index

def _ref_entries(index):
    entries = []
    for seg in index['segments']:
        if seg['canon'] not in ('references', 'other'):
            continue
        if seg['canon'] != 'references' and (not re.match('^\\s*\\[?\\d{1,3}\\]?[.)]\\s', seg['text'])):
            continue
        entries.append(seg)
    return entries

def aggregate(index):
    segs = index['segments']
    sections = {}
    for i, seg in enumerate(segs):
        if not seg['canon']:
            continue
        s = sections.setdefault((seg['doc_id'], seg['canon']), {'doc_id': seg['doc_id'], 'canon': seg['canon'], 'name': seg['section'], 'first_index': i, 'segments': 0})
        s['segments'] += 1
    nums = {}
    for seg in segs:
        for m in NUMU.finditer(seg['text']):
            tok = norm(m.group(0)).replace(' ', '')
            if len(tok) < 2 or re.match('^\\d{4}$', tok):
                continue
            rec = nums.setdefault(tok, {'token': tok, 'uids': [], 'canons': []})
            if seg['uid'] not in rec['uids']:
                rec['uids'].append(seg['uid'])
            if seg['canon'] and seg['canon'] not in rec['canons']:
                rec['canons'].append(seg['canon'])
    cites = []
    for seg in segs:
        if seg['canon'] in ('references', 'bibliography'):
            continue
        for m in re.finditer('\\[(\\d{1,3}(?:\\s*[-,–]\\s*\\d{1,3})*)\\]', seg['text']):
            cites.append({'uid': seg['uid'], 'raw': m.group(0), 'style': 'numeric'})
        for m in re.finditer('([A-Z][A-Za-z\\-]{2,})\\s*(?:et\\s+al\\.?|等)?[,，]?\\s*\\(?((?:19|20)\\d{2})(?=\\s*[，,；;）)\\]等]|\\s*$|\\.\\s*$)', seg['text']):
            if m.group(1).lower() in ('figure', 'fig', 'table', 'eq', 'equation', 'section'):
                continue
            cites.append({'uid': seg['uid'], 'raw': m.group(0), 'style': 'author-year'})
    refs = _ref_entries(index)
    n_refs = 0
    for seg in refs:
        n_refs += len(re.findall('\\[\\s*\\d{1,3}\\s*\\]', seg['text']))
        n_refs += len(re.findall('(?m)^\\s*\\d{1,3}[.)]\\s', seg['text']))
    if n_refs == 0:
        n_refs = len(refs)
    return {'sections': sorted(sections.values(), key=lambda s: (s['doc_id'], s['first_index'])), 'numbers': sorted(nums.values(), key=lambda n: n['token']), 'citations': cites, 'reference_entries': len(refs), 'reference_count': n_refs}
_MATCH_CACHE = {}

def _prepare(index):
    key = id(index)
    if key in _MATCH_CACHE:
        return _MATCH_CACHE[key]
    per_doc = []
    for doc in index['documents']:
        segs = [s for s in index['segments'] if s['doc_id'] == doc['doc_id']]
        if not segs:
            continue
        pieces, spans, pos = ([], [], 0)
        for s in segs:
            t = squeeze(s['text'])
            spans.append((pos, pos + len(t), s))
            pieces.append(t)
            pos += len(t)
        per_doc.append((doc, ''.join(pieces), spans))
    _MATCH_CACHE[key] = per_doc
    return per_doc

def locate(index, quote, max_hits=6):
    q = squeeze(quote)
    hits = []
    if len(q) < 2:
        return hits
    for doc, full, spans in _prepare(index):
        start = 0
        while True:
            i = full.find(q, start)
            if i < 0:
                break
            for a, b, seg in spans:
                if a <= i < b or i < a < i + len(q):
                    if seg not in hits:
                        hits.append(seg)
                    break
            start = i + max(1, len(q))
            if len(hits) >= max_hits:
                return hits
    return hits

def quote_ok(index, quote):
    return bool(locate(index, quote, max_hits=1))

def best_sentence(seg, cue, max_len=300):
    import re as _re
    text = seg.get('text') or ''
    if len(text) <= max_len and (not cue):
        return text
    sents = [x.strip() for x in _re.split('(?<=[。！？.!?])\\s+', text) if x.strip()]
    if not sents:
        return text[:max_len]
    if cue:
        try:
            rx = _re.compile(cue, _re.I)
            for s in sents:
                if rx.search(s) and len(s) <= max_len:
                    return s
            for s in sents:
                if rx.search(s):
                    return s[:max_len]
        except Exception:
            pass
    mid = [s for s in sents if 24 <= len(s) <= max_len]
    if mid:
        return max(mid, key=len)
    short = [s for s in sents if len(s) <= max_len]
    if short:
        return max(short, key=len)
    return sents[0][:max_len]

def numbers_in(text):
    out = []
    for m in NUMU.finditer(norm(text)):
        tok = m.group(0).replace(' ', '')
        if re.match('^[-+]?\\d', tok) and tok not in out:
            out.append(tok)
    return out

def blank_finding():
    return {'finding_id': '', 'facet': '', 'rule': '', 'candidate_ids': [], 'location': {'doc_id': '', 'section': '', 'locator': '', 'page': None, 'table_or_figure': None}, 'quote': '', 'quote_verified': False, 'quote_match': '', 'issue_type': '', 'severity': '', 'severity_reason': '', 'evidence': '', 'rationale': '', 'revision': '', 'verdict_type': '', 'confidence': 'medium', 'status': 'confirmed', 'review_note': ''}

def normalize_findings(index, draft_findings):
    issues, out = ([], [])
    if not isinstance(draft_findings, list):
        return (out, [{'level': 'error', 'code': 'findings_not_list', 'detail': 'draft.findings 不是数组，已忽略'}])
    seen = {}
    order = {d['doc_id']: i for i, d in enumerate(index['documents'])}
    for n, raw in enumerate(draft_findings, 1):
        if not isinstance(raw, dict):
            issues.append({'level': 'error', 'code': 'finding_not_object', 'detail': '第 %d 条不是对象' % n})
            continue
        f = blank_finding()
        f.update({k: v for k, v in raw.items() if k in f})
        loc = raw.get('location') if isinstance(raw.get('location'), dict) else {}
        f['location'] = {**blank_finding()['location'], **loc}
        f['facet'] = str(f.get('facet') or '').strip().lower()
        if f['facet'] not in FACETS:
            issues.append({'level': 'warning', 'code': 'facet_invalid', 'detail': '第 %d 条 facet=%r 非法，已归入 struct' % (n, f['facet'])})
            f['facet'] = 'struct' if not f['facet'] else 'other'
            if f['facet'] == 'other':
                f['facet'] = 'struct'
        for key, allowed, default in (('severity', SEVERITIES, 'minor'), ('verdict_type', VERDICTS, 'pending_review')):
            v = str(f.get(key) or '').strip().lower()
            if v not in allowed:
                if v:
                    issues.append({'level': 'warning', 'code': key + '_invalid', 'detail': '第 %d 条 %s=%r 非法，置 %s' % (n, key, v, default)})
                v = default
            f[key] = v
        it = str(f.get('issue_type') or '').strip().lower()
        if it not in ISSUE_TYPES:
            it = {'error': 'fact_error', 'insufficient_evidence': 'insufficient_evidence', 'compliance': 'compliance', 'suggestion': 'improvement', 'pending_review': 'insufficient_evidence'}.get(f['verdict_type'], 'improvement')
            if f.get('issue_type'):
                issues.append({'level': 'warning', 'code': 'issue_type_invalid', 'detail': '第 %d 条 issue_type 非法，按 verdict 推为 %s' % (n, it)})
        f['issue_type'] = it
        if f['verdict_type'] == 'pending_review':
            f['status'] = 'pending_review'
        f['status'] = 'pending_review' if str(f.get('status')) == 'pending_review' else 'confirmed'
        quote = norm(f.get('quote'))
        f['quote'] = quote[:600]
        if not quote:
            issues.append({'level': 'error', 'code': 'quote_missing', 'detail': '第 %d 条没有 quote，已剔除' % n})
            continue
        hits = locate(index, quote, max_hits=3)
        if hits:
            f['quote_verified'] = True
            seg = hits[0]
            f['quote_match'] = seg['uid']
            if not f['location'].get('locator'):
                f['location']['locator'] = seg['locator']
            f['location']['doc_id'] = f['location'].get('doc_id') or seg['doc_id']
            f['location']['page'] = f['location'].get('page') or seg['page']
            f['location']['section'] = f['location'].get('section') or seg['section']
        else:
            f['quote_verified'] = False
            f['status'] = 'pending_review'
            f['verdict_type'] = 'pending_review'
            f['confidence'] = 'low'
            f['review_note'] = (f.get('review_note') or '') + ' [auto] quote 未能在材料中逐字命中，降级为 pending_review'
            issues.append({'level': 'error', 'code': 'quote_not_found', 'detail': '第 %d 条 quote 未逐字命中：%s' % (n, quote[:60])})
        if not f['location'].get('locator'):
            f['location']['locator'] = '未定位'
            issues.append({'level': 'warning', 'code': 'locator_missing', 'detail': '第 %d 条无 locator 且未能自动定位' % n})
        for key, minlen, code in (('severity_reason', 6, 'severity_reason_short'), ('revision', 8, 'revision_short'), ('evidence', 4, 'evidence_short')):
            if len(str(f.get(key) or '')) < minlen:
                issues.append({'level': 'warning', 'code': code, 'detail': '第 %d 条 %s 过短或缺失' % (n, key)})
                if not f.get(key):
                    f[key] = '' if key == 'severity_reason' else f.get(key, '')
        if not f.get('rationale'):
            f['rationale'] = f.get('evidence') or ''
        if isinstance(f.get('candidate_ids'), str):
            f['candidate_ids'] = [f['candidate_ids']]
        f['candidate_ids'] = [str(c) for c in f.get('candidate_ids') or []]
        key = (f['facet'], squeeze(quote)[:160])
        if key in seen:
            issues.append({'level': 'warning', 'code': 'duplicate_finding', 'detail': '第 %d 条与第 %d 条重复，已合并' % (n, seen[key])})
            continue
        seen[key] = n
        out.append(f)
    out.sort(key=lambda f: (FACETS.index(f['facet']) if f['facet'] in FACETS else 9, order.get(f['location'].get('doc_id'), 99), f['location'].get('page') or 0, SEV_RANK.get(f['severity'], 9), squeeze(f['quote'])[:60]))
    for i, f in enumerate(out, 1):
        f['finding_id'] = 'F-%03d' % i
    return (out, issues)

def pin(index, rule, quote_hint=None, facet=None, severity=None, issue_type=None, ask_note=''):
    cands = index.get('candidates') or []
    for c in cands:
        if c['rule'] != rule:
            continue
        if facet and c['facet'] != facet:
            continue
        if quote_hint and squeeze(quote_hint) not in squeeze(c['quote']):
            continue
        return {'facet': c['facet'], 'rule': c['rule'], 'candidate_ids': [c['candidate_id']], 'location': {'locator': c['locator'], 'section': '', 'doc_id': '', 'page': None, 'table_or_figure': None}, 'quote': c['quote'], 'issue_type': issue_type or c['issue_type'], 'severity': severity or c['severity'], 'severity_reason': '脚本候选：%s（未经人工判定，按保守档处理）' % c['why'][:120], 'evidence': c['why'], 'rationale': c['why'] + ' ' + ask_note, 'revision': c['ask'], 'verdict_type': 'pending_review', 'confidence': 'low', 'status': 'pending_review', 'review_note': '自动兜底：仅定位到候选，未经评审 Agent 判定'}
    return None
