"""reading-card-desk / extract.py - deterministic text & annotation extraction."""
import hashlib, json, re, zipfile, zlib
from datetime import datetime, timezone
from pathlib import Path

VERSION = '1.0.0'
SIZE_CAP = 40 * 1024 * 1024
PAGE_CAP = 400

TYPES = {'highlight', 'underline', 'strikethrough', 'margin_note', 'handwritten',
         'web_clip', 'word_comment', 'region_mark', 'stamp'}
COLORS = {'yellow': (1., 1., 0.), 'green': (0., 1., 0.), 'blue': (0., 0., 1.),
          'red': (1., 0., 0.), 'magenta': (1., 0., 1.), 'cyan': (0., 1., 1.),
          'orange': (1., .65, 0.), 'black': (0., 0., 0.), 'gray': (.5, .5, .5),
          'pink': (1., .6, .7), 'purple': (.5, 0., .5)}
DEFAULT_MEANING = {'yellow': '通用强调/关键结果', 'green': '方法或可复用步骤',
                   'blue': '背景与定义', 'red': '疑点/需核实', 'magenta': '结论',
                   'cyan': '数据与图表相关', 'orange': '待办/待查', 'pink': '作者自注',
                   'purple': '关联文献', 'black': '划线强调', 'gray': '弱相关'}
SUBTYPE_MAP = {'Highlight': 'highlight', 'Underline': 'underline', 'Squiggly': 'underline',
               'StrikeOut': 'strikethrough', 'Text': 'margin_note', 'FreeText': 'margin_note',
               'Ink': 'handwritten', 'Square': 'region_mark', 'Circle': 'region_mark',
               'Polygon': 'region_mark', 'Stamp': 'stamp', 'Caret': 'margin_note',
               'Line': 'region_mark'}


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def J(p, o, indent=1):
    try:
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        t = p.parent / (p.name + '.tmp')
        t.write_text(json.dumps(o, ensure_ascii=False, indent=indent), encoding='utf-8')
        t.replace(p)
        return True
    except Exception:
        return False


def sha256_file(p):
    h = hashlib.sha256()
    try:
        with open(p, 'rb') as f:
            for c in iter(lambda: f.read(1 << 18), b''):
                h.update(c)
        return h.hexdigest()
    except Exception:
        return None


_WS = set(' \t\r\n\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009'
          '\u200a\u200b\u202f\u205f\u3000\ufeff')


def norm_map(s):
    """normalize + index map back to the original string (used by quote checks)."""
    out, idx = [], []
    for i, ch in enumerate(s or ''):
        if ch == '\u00ad':
            continue
        if ch in _WS:
            if out and out[-1] != ' ':
                out.append(' ')
                idx.append(i)
            continue
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            ch = chr(o - 0xFEE0)
        elif ch in '\u2018\u2019':
            ch = "'"
        elif ch in '\u201c\u201d':
            ch = '"'
        elif ch in '\u2010\u2011\u2012\u2013\u2014\u2212':
            ch = '-'
        ch = ch.lower()
        if ch == ' ' and out and out[-1] == ' ':
            continue
        out.append(ch)
        idx.append(i)
    return ''.join(out), idx


def norm(s):
    return norm_map(s)[0]


def find_quotes(ntext, nquote, limit=3):
    res, start = [], 0
    if not nquote or not ntext:
        return res
    while len(res) < limit:
        j = ntext.find(nquote, start)
        if j < 0:
            break
        res.append((j, j + len(nquote)))
        start = j + 1
    return res


def fuzzy_quote(ntext, nquote):
    """locate by first/last 5 words; tolerates OCR noise inside the quote."""
    w = nquote.split()
    if len(w) < 6 or not ntext:
        return None
    head, tail = ' '.join(w[:5]), ' '.join(w[-5:])
    i = ntext.find(head)
    if i < 0:
        return None
    j = ntext.find(tail, i + len(head) - 3)
    return (i, j + len(tail)) if j >= 0 else None


def clean(s):
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]', ' ', s or '')
    return re.sub(r'[ \t]{2,}', ' ', s).strip()


_ENT = (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'"),
        ('&#39;', "'"), ('&nbsp;', ' '))


def _unesc(t):
    for a, b in _ENT:
        t = t.replace(a, b)
    return t


def dec(b):
    if b[:2] == b'\xfe\xff':
        try:
            return b[2:].decode('utf-16-be', 'replace')
        except Exception:
            return ''
    return b.decode('latin-1', 'replace')


def color_name(rgb):
    if not rgb:
        return None
    r, g, b = [float(x) for x in rgb[:3]]
    if max(r, g, b) > 1.01:
        r, g, b = r / 255., g / 255., b / 255.
    best, bd = None, 9.
    for name, (cr, cg, cb) in COLORS.items():
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < bd:
            best, bd = name, d
    if bd > .55:
        return 'custom(%0.2f,%0.2f,%0.2f)' % (r, g, b)
    return best


def text_quality(t):
    if not (t or '').strip():
        return 'empty'
    ok = sum(1 for ch in t if ch.isalnum() or ch in ' \n.,;:()[]/-%')
    return 'ok' if ok / max(1, len(t)) >= .75 else 'garbled'


def _objs(data):
    o = {}
    for m in re.finditer(rb'(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b', data):
        s = m.end()
        e = data.find(b'endobj', s)
        o[int(m.group(1))] = data[s:e if e > 0 else min(len(data), s + 400000)]
    return o


def _stream(body):
    i = body.find(b'stream')
    if i < 0:
        return None, body
    d = body[:i]
    j = i + 6
    if body[j:j + 2] == b'\r\n':
        j += 2
    elif body[j:j + 1] in (b'\n', b'\r'):
        j += 1
    k = body.find(b'endstream', j)
    return body[j:k if k > 0 else len(body)], d


def _inflate(raw, dct):
    if b'FlateDecode' not in dct:
        return raw
    for w in (15, -15, 47):
        try:
            return zlib.decompress(raw, w)
        except Exception:
            pass
    try:
        return zlib.decompressobj().decompress(raw)
    except Exception:
        return None


def _pages(objs):
    root = None
    for n, b in objs.items():
        if re.search(rb'/Type\s*/Catalog', b):
            m = re.search(rb'/Pages\s+(\d+)\s+\d+\s+R', b)
            if m:
                root = int(m.group(1))
                break
    order, seen = [], set()
    if root:
        stack = [root]
        while stack:
            n = stack.pop(0)
            if n in seen or n not in objs:
                continue
            seen.add(n)
            b = objs[n]
            m = re.search(rb'/Kids\s*\[(.*?)\]', b, re.S)
            if m:
                stack = [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', m.group(1))] + stack
            elif re.search(rb'/Type\s*/Page(?![a-zA-Z])', b):
                order.append(n)
    if not order:
        order = sorted(n for n, b in objs.items() if re.search(rb'/Type\s*/Page(?![a-zA-Z])', b))
    return order


def _tokens(s):
    i, n = 0, len(s)
    while i < n:
        c = s[i:i + 1]
        if c in b' \t\r\n\x00\x0c':
            i += 1
            continue
        if c == b'(':
            depth, j, buf = 1, i + 1, bytearray()
            while j < n and depth > 0:
                ch = s[j:j + 1]
                if ch == b'\\':
                    x = s[j + 1:j + 2]
                    mp = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b',
                          b'f': b'\f', b'(': b'(', b')': b')', b'\\': b'\\'}
                    if x in mp:
                        buf += mp[x]
                        j += 2
                        continue
                    k = 0
                    while k < 3 and j + 1 + k < n and s[j + 1 + k:j + 2 + k].isdigit():
                        k += 1
                    if k:
                        try:
                            buf.append(int(s[j + 1:j + 1 + k], 8) & 0xFF)
                        except Exception:
                            pass
                        j += 1 + k
                        continue
                    j += 2
                    continue
                if ch == b'(':
                    depth += 1
                    buf += ch
                elif ch == b')':
                    depth -= 1
                    if depth > 0:
                        buf += ch
                else:
                    buf += ch
                j += 1
            yield 'str', bytes(buf)
            i = j
            continue
        if c == b'<':
            if s[i + 1:i + 2] == b'<':
                yield 'dict', None
                i += 2
                continue
            j = s.find(b'>', i)
            if j < 0:
                i += 1
                continue
            hx = re.sub(rb'[^0-9A-Fa-f]', b'', s[i + 1:j])
            if len(hx) % 2:
                hx += b'0'
            try:
                yield 'str', bytes.fromhex(hx.decode())
            except Exception:
                pass
            i = j + 1
            continue
        if s[i:i + 2] == b'>>':
            i += 2
            continue
        if c == b'/':
            j = i + 1
            while j < n and s[j:j + 1] not in b' \t\r\n\x00\x0c/[]<>(){}':
                j += 1
            yield 'name', s[i + 1:j].decode('latin-1')
            i = j
            continue
        if c == b'[':
            yield 'as', None
            i += 1
            continue
        if c == b']':
            yield 'ae', None
            i += 1
            continue
        m = re.match(rb'[-+]?[0-9]*\.?[0-9]+', s[i:])
        if m:
            try:
                yield 'num', float(m.group(0))
            except Exception:
                pass
            i += m.end()
            continue
        m = re.match(rb"[A-Za-z'\"*][A-Za-z0-9'\"*]*", s[i:])
        if m:
            yield 'op', m.group(0).decode('latin-1')
            i += m.end()
            continue
        i += 1


def _items(stream):
    """content stream -> [{'x','y','w','h','text'}]; coordinates are approximate."""
    items, ops, arrs = [], [], []
    x = y = lx = ly = 0.
    fs, lead = 10., 0.

    def num(k, dv=0.):
        try:
            v = ops[k]
            return v if isinstance(v, float) else dv
        except Exception:
            return dv

    def emit(t):
        nonlocal x
        t = clean(t)
        if not t:
            return
        w = max(1., len(t) * fs * .5)
        items.append({'x': x, 'y': y, 'w': w, 'h': fs, 'text': t})
        x += w

    for kind, val in _tokens(stream):
        if kind == 'as':
            arrs.append([])
            continue
        if kind == 'ae':
            if arrs:
                ops.append(arrs.pop())
            continue
        if kind == 'dict':
            ops.append(val)
            continue
        if kind == 'name':
            ops.append(val)
            continue
        if arrs:
            arrs[-1].append(val)
            continue
        if kind in ('str', 'num'):
            ops.append(val)
            continue
        if val == 'BT':
            x = y = lx = ly = 0.
        elif val == 'Tf':
            fs = num(-1, 10.)
        elif val in ('Td', 'TD'):
            lx += num(-2)
            ly += num(-1)
            if val == 'TD':
                lead = -num(-1)
            x, y = lx, ly
        elif val == 'Tm':
            lx, ly = num(-2), num(-1)
            x, y = lx, ly
        elif val in ('T*', "'", '"'):
            ly -= lead or fs * 1.2
            x, y = lx, ly
            if val != 'T*' and ops and isinstance(ops[-1], bytes):
                emit(dec(ops[-1]))
        elif val == 'Tj':
            if ops and isinstance(ops[-1], bytes):
                emit(dec(ops[-1]))
        elif val == 'TJ':
            if ops and isinstance(ops[-1], list):
                buf = b''
                for it in ops[-1]:
                    if isinstance(it, bytes):
                        buf += it
                    elif isinstance(it, float) and it < -250:
                        buf += b' '
                emit(dec(buf))
        ops = []
    return items


def _mid(objs, body):
    m = re.search(rb'/MediaBox\s*\[\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)', body)
    try:
        return (float(m.group(1)) + float(m.group(3))) / 2., float(m.group(3)) - float(m.group(1))
    except Exception:
        return 306., 612.


def _blocks(items, mid):
    """column clustering -> lines -> paragraphs (two-column read column-first)."""
    if not items:
        return [], ''
    left = [t for t in items if t['x'] + t['w'] / 2 < mid - 3]
    right = [t for t in items if t['x'] + t['w'] / 2 >= mid - 3]
    two = len(left) >= 4 and len(right) >= 4 and len(items) * .55 >= min(len(left), len(right)) * 2
    paras = []
    for ci, col in enumerate([left, right] if two else [items]):
        if not col:
            continue
        buckets = {}
        for t in col:
            buckets.setdefault(round(t['y'] / 4.), []).append(t)
        lines = []
        for k in sorted(buckets, reverse=True):
            row = sorted(buckets[k], key=lambda t: t['x'])
            txt, prev = [], None
            for t in row:
                if prev is not None and t['x'] - (prev['x'] + prev['w']) > 18:
                    txt.append('  ')
                txt.append(t['text'])
                prev = t
            lines.append({'y': buckets[k][0]['y'], 'text': clean(' '.join(txt)),
                          'size': max(t['h'] for t in row)})
        cur, lasty, lastsz = [], None, 12.
        for ln in lines:
            if not ln['text']:
                continue
            if cur and lasty is not None and (lasty - ln['y']) > max(14., 1.85 * lastsz):
                paras.append({'col': ci, 'text': clean(' '.join(cur))})
                cur = []
            cur.append(ln['text'])
            lasty, lastsz = ln['y'], ln['size'] or 12.
        if cur:
            paras.append({'col': ci, 'text': clean(' '.join(cur))})
    return [p for p in paras if p['text']], clean('\n\n'.join(p['text'] for p in paras if p['text']))


def _annots(objs, body):
    out = []
    m = re.search(rb'/Annots\s*(\[.*?\]|\d+\s+\d+\s+R)', body, re.S)
    if not m:
        return out
    seg = m.group(1)
    refs = [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', seg)]
    for r in refs:
        if r in objs:
            out.append(objs[r])
    if not refs:
        out += re.findall(rb'<<(.*?)>>', seg, re.S)
    return out


def _arr(b, key):
    m = re.search(rb'/' + key + rb'\s*\[([^\]]*)\]', b, re.S)
    if not m:
        return None
    v = [float(x) for x in re.findall(rb'[-+]?[0-9]*\.?[0-9]+', m.group(1))]
    return v or None


def _pstr(b, key):
    m = re.search(rb'/' + key + rb'\s*<([0-9A-Fa-f\s]+)>', b)
    if m and not re.search(rb'/' + key + rb'\s*\(', b):
        try:
            return dec(bytes.fromhex(re.sub(rb'\s', b'', m.group(1)).decode()))
        except Exception:
            return None
    m = re.search(rb'/' + key + rb'\s*\(', b)
    if not m:
        return None
    j, depth, buf = m.end() - 1, 0, bytearray()
    while j < len(b):
        ch = b[j:j + 1]
        if ch == b'\\':
            buf += b[j:j + 2]
            j += 2
            continue
        if ch == b'(':
            depth += 1
            if depth > 1:
                buf += ch
        elif ch == b')':
            depth -= 1
            if depth == 0:
                break
            buf += ch
        else:
            buf += ch
        j += 1
    return clean(dec(bytes(buf)).replace('\\n', ' ').replace('\\r', ' ')) or None


def pdf_parse(path, data):
    res = {'pages': [], 'annots_raw': [], 'encrypted': False, 'notes': [], 'garbled_pages': 0}
    tail = data[-8192:] if len(data) > 8192 else data
    if b'/Encrypt' in tail or b'/Encrypt' in data[:4096]:
        res['encrypted'] = True
    objs = _objs(data)
    if not objs:
        res['notes'].append('no_objects')
        return res
    pages = _pages(objs)
    if not pages:
        res['notes'].append('no_pages')
        return res
    for pi, pn in enumerate(pages[:PAGE_CAP]):
        body = objs[pn]
        m = re.search(rb'/Contents\s*(\[.*?\]|\d+\s+\d+\s+R)', body, re.S)
        cids = [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', m.group(1))] if m else []
        items = []
        for cid in cids[:24]:
            if cid not in objs:
                continue
            raw, dct = _stream(objs[cid])
            if raw is None:
                continue
            d = _inflate(raw, dct)
            if d:
                items += _items(d)
        mid, _w = _mid(objs, body)
        paras, ptext = _blocks(items, mid)
        if text_quality(ptext) == 'garbled':
            res['garbled_pages'] += 1
        nt, _ = norm_map(ptext)
        ps, cur = [], 0
        for k, pa in enumerate(paras):
            nseg = norm(pa['text'])
            j = nt.find(nseg, cur)
            j = j if j >= 0 else cur
            ps.append({'pid': 'p%d.%d' % (pi + 1, k + 1), 's': j, 'e': j + len(nseg),
                       'text': pa['text'], 'col': pa['col']})
            cur = max(cur, j + len(nseg))
        res['pages'].append({'p': pi + 1, 'printed': _printed(paras), 'text': ptext,
                             'norm': nt, 'paras': ps, 'n_items': len(items)})
        for ab in _annots(objs, body):
            sub = re.search(rb'/Subtype\s*/([A-Za-z]+)', ab)
            if not sub or sub.group(1).decode() not in SUBTYPE_MAP:
                continue
            res['annots_raw'].append({'subtype': sub.group(1).decode(), 'page': pi + 1,
                                      'quad': _arr(ab, b'QuadPoints'), 'rect': _arr(ab, b'Rect'),
                                      'color': _arr(ab, b'C'), 'note': _pstr(ab, b'Contents'),
                                      'author': _pstr(ab, b'T'), 'created': _pstr(ab, b'M'),
                                      'items': items, 'printed': res['pages'][-1]['printed']})
    return res


def _printed(paras):
    for pa in (paras[:1] + paras[-1:]):
        m = re.match(r'^\s*[-–—]?\s*(?:page\s*)?(\d{1,4})\s*(?:/\s*\d{1,4})?\s*[-–—]?\s*$',
                     pa['text'], re.I)
        if m:
            return int(m.group(1))
    return None


def align_quad(annot):
    """quad/rect -> overlapping text items -> verbatim quote, else nearest line."""
    quad, rect = annot.get('quad'), annot.get('rect')
    items = annot.get('items') or []
    xs, ys = [], []
    if quad and len(quad) >= 4:
        xs, ys = quad[0::2], quad[1::2]
    elif rect and len(rect) >= 4:
        xs, ys = [rect[0], rect[2]], [rect[1], rect[3]]
    if not xs:
        return None, 'note_only', .3
    x0, x1, y0, y1 = min(xs) - 2, max(xs) + 2, min(ys) - 2, max(ys) + 2
    hit = [t for t in items if t['x'] + t['w'] >= x0 and t['x'] <= x1
           and t['y'] + t['h'] >= y0 and t['y'] <= y1]
    if hit:
        hit.sort(key=lambda t: (-round(t['y'], 1), t['x']))
        q = clean(' '.join(t['text'] for t in hit))
        if q:
            return q, ('pdf_annots_quad' if quad else 'pdf_annots_rect'), .92 if quad else .85
    mid_y = (y0 + y1) / 2.
    near = sorted(items, key=lambda t: abs(t['y'] - mid_y))
    if near and abs(near[0]['y'] - mid_y) <= 30:
        return clean(near[0]['text']), 'nearest_line', .5
    return None, 'note_only', .3


def docx_parse(path):
    out = {'paras': [], 'annots_raw': [], 'notes': [], 'meta': {}, 'revisions': []}
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        out['notes'].append('docx_open_failed')
        return out
    names = set(z.namelist())
    try:
        doc = z.read('word/document.xml').decode('utf-8', 'replace')
    except Exception:
        out['notes'].append('docx_no_document')
        return out

    unesc = _unesc
    if 'docProps/core.xml' in names:
        try:
            core = z.read('docProps/core.xml').decode('utf-8', 'replace')
            tm = re.search(r'<dc:title>(.*?)</dc:title>', core, re.S)
            au = re.search(r'<dc:creator>(.*?)</dc:creator>', core, re.S)
            out['meta']['title'] = unesc(clean(tm.group(1))) if tm else None
            out['meta']['author'] = unesc(clean(au.group(1))) if au else None
        except Exception:
            pass
    for i, px in enumerate(re.findall(r'<w:p\b.*?</w:p>', doc, re.S)):
        runs = re.findall(r'<w:r\b.*?</w:r>', px, re.S)
        txt = unesc(clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', px, re.S))))
        st = re.search(r'<w:pStyle w:val="([^"]+)"', px)
        if txt:
            out['paras'].append({'i': i, 'text': txt, 'style': st.group(1) if st else None})
        for rx in runs:
            hi = re.search(r'<w:highlight w:val="([^"]+)"', rx)
            shd = re.search(r'<w:shd[^>]*w:fill="([0-9A-Fa-f]{6})"', rx)
            rt = unesc(clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', rx, re.S))))
            if not rt:
                continue
            if hi and hi.group(1).lower() != 'none':
                out['annots_raw'].append({'kind': 'docx_highlight', 'para': i, 'quote': rt,
                                          'color': hi.group(1).lower(), 'type': 'highlight'})
            elif shd and shd.group(1).lower() not in ('ffffff', 'auto', '000000'):
                out['annots_raw'].append({'kind': 'docx_highlight', 'para': i, 'quote': rt,
                                          'color_hex': '#' + shd.group(1).upper(), 'type': 'highlight'})
        for ins in re.findall(r'<w:ins\b.*?</w:ins>', px, re.S):
            t = clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', ins, re.S)))
            if t:
                out['revisions'].append({'kind': 'insertion', 'para': i, 'text': t})
        for dl in re.findall(r'<w:del\b.*?</w:del>', px, re.S):
            t = clean(''.join(re.findall(r'<w:delText[^>]*>(.*?)</w:delText>', dl, re.S)))
            if t:
                out['revisions'].append({'kind': 'deletion', 'para': i, 'text': t})
    if 'word/comments.xml' in names:
        try:
            cx = z.read('word/comments.xml').decode('utf-8', 'replace')
            for cm in re.findall(r'<w:comment\b.*?</w:comment>', cx, re.S):
                cid = re.search(r'w:id="(\d+)"', cm)
                if not cid:
                    continue
                au = re.search(r'w:author="([^"]*)"', cm)
                dt = re.search(r'w:date="([^"]*)"', cm)
                note = unesc(clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', cm, re.S))))
                sm = re.search(r'<w:commentRangeStart w:id="%s"\s*/>' % cid.group(1), doc)
                em = re.search(r'<w:commentRangeEnd w:id="%s"\s*/>' % cid.group(1), doc)
                if not (sm and em and em.start() > sm.start()):
                    continue
                seg = doc[sm.end():em.start()]
                q = unesc(clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', seg, re.S))))
                if q:
                    out['annots_raw'].append({'kind': 'docx_comment', 'para': doc[:sm.start()].count('<w:p '),
                                              'quote': q, 'note': note,
                                              'author': au.group(1) if au else None,
                                              'created': dt.group(1) if dt else None,
                                              'type': 'word_comment'})
        except Exception:
            out['notes'].append('docx_comments_failed')
    return out


def html_parse(path, text):
    out = {'paras': [], 'annots_raw': [], 'notes': [], 'meta': {}}
    body = re.sub(r'<(script|style)\b.*?</\1>', ' ', text, flags=re.S | re.I)
    tm = re.search(r'<title[^>]*>(.*?)</title>', body, re.S | re.I)
    if tm:
        out['meta']['title'] = clean(re.sub(r'<[^>]+>', '', tm.group(1)))
    am = re.search(r'<meta[^>]+(?:name|property)=["\'](?:citation_doi|dc.identifier|doi)["\']'
                   r'[^>]+content=["\']([^"\']+)', body, re.I)
    if am:
        out['meta']['doi'] = am.group(1)
    um = (re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', body, re.I)
          or re.search(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)', body, re.I))
    if um:
        out['meta']['url'] = um.group(1)

    unesc = _unesc

    for m in re.finditer(r'<mark\b([^>]*)>(.*?)</mark>', body, re.S | re.I):
        q = clean(re.sub(r'<[^>]+>', ' ', m.group(2)))
        if q:
            cm = (re.search(r'data-color=["\']([^"\']+)', m.group(1))
                  or re.search(r'class=["\']([^"\']+)', m.group(1)))
            out['annots_raw'].append({'kind': 'html_mark', 'quote': unesc(q),
                                      'color': (cm.group(1).split()[0] if cm else 'yellow'),
                                      'type': 'highlight'})
    for m in re.finditer(r'<(\w+)\b([^>]*data-annotation[^>]*)>(.*?)</\1>', body, re.S | re.I):
        q = clean(re.sub(r'<[^>]+>', ' ', m.group(3)))
        ty = re.search(r'data-annotation=["\']([^"\']+)', m.group(2))
        nt = re.search(r'data-note=["\']([^"\']+)', m.group(2))
        cm = re.search(r'data-color=["\']([^"\']+)', m.group(2))
        if q:
            out['annots_raw'].append({'kind': 'html_mark', 'quote': unesc(q),
                                      'color': cm.group(1) if cm else 'yellow',
                                      'type': (ty.group(1) if ty else 'highlight'),
                                      'note': nt.group(1) if nt else None})
    acc = ''
    for m in re.finditer(r'<(p|li|h[1-6]|blockquote|td|div|mark|span|section)\b[^>]*>(.*?)</\1>',
                         body, re.S | re.I):
        t = unesc(clean(re.sub(r'<[^>]+>', ' ', m.group(2))))
        if len(t) < 2 or norm(t) in acc:
            continue
        acc += ' ' + norm(t)
        out['paras'].append({'i': len(out['paras']), 'text': t, 'style': m.group(1).lower()})
    if not out['paras']:
        out['notes'].append('html_no_paragraphs')
    return out


def text_parse(text):
    paras = []
    for blk in re.split(r'\n\s*\n', (text or '').replace('\r', '')):
        t = clean(blk)
        if t:
            paras.append({'i': len(paras), 'text': t, 'style': None})
    return {'paras': paras, 'annots_raw': [], 'notes': [], 'meta': {}}


def legend_lookup(legend, doc_text, color):
    if not color:
        return None, 'none'
    cl = norm(color)
    for k, v in (legend or {}).items():
        if norm(str(k)) == cl:
            return str(v), 'case_declared_legend'
    for line in (doc_text or '').split('\n')[:200]:
        m = re.match(r'^\s*([A-Za-z\u4e00-\u9fa5]{2,12})\s*[:：=\-–]\s*(.{2,60})$', line.strip())
        if m and norm(m.group(1)) == cl:
            return m.group(2).strip(), 'document_legend'
    if re.search(r'(图例|legend|标注约定|color key)', doc_text or '', re.I):
        for seg in re.split(r'[;；,，\n]', doc_text):
            if cl in norm(seg) and 4 <= len(seg) <= 80:
                return clean(seg), 'document_legend'
    return DEFAULT_MEANING.get(color, '未定义（需人工确认）'), 'default_convention'


def _hex(rgb):
    if not rgb:
        return None
    try:
        r, g, b = [float(x) for x in rgb[:3]]
        if max(r, g, b) > 1.01:
            return '#%02X%02X%02X' % (int(r), int(g), int(b))
        return '#%02X%02X%02X' % (int(r * 255), int(g * 255), int(b * 255))
    except Exception:
        return None


def _parse_color(c):
    s = str(c or '').strip()
    if s.startswith('#'):
        try:
            h = s[1:]
            return [int(h[i:i + 2], 16) / 255. for i in (0, 2, 4)]
        except Exception:
            return None
    if ',' in s:
        try:
            return [float(x) / 255. if float(x) > 1 else float(x) for x in s.split(',')[:3]]
        except Exception:
            return None
    return COLORS.get(s.lower())
