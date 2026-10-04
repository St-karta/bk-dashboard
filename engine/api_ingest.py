"""Разбирает сохранённые ответы API площадок (raw/<дата>/*.txt) и обновляет api/*.json.
Правило: если для блока не хватает файла или он не разобрался — блок НЕ трогаем
(остаются прошлые цифры) и печатаем WARN. Нули из-за сбоя в дашборд не попадают.
Запуск: python3 api_ingest.py raw/ГГГГ-ММ-ДД"""
import sys, os, re, json, glob, datetime, calendar
from api_plan import widx, weeks

RAW = sys.argv[1] if len(sys.argv) > 1 else None
HERE = os.path.dirname(os.path.abspath(__file__)); API = os.path.join(HERE, 'api')
TODAY = datetime.date.fromisoformat(os.path.basename(os.path.normpath(RAW)))
WARN = []; DONE = []
def warn(s): WARN.append(s); print('WARN', s)

def rd(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p): return None
    t = open(p, encoding='utf-8').read().strip()
    if t.startswith('{') and '"result"' in t[:30]:
        try: t = json.loads(t)['result']
        except Exception: pass
    if re.search(r'\b429\b|подожди|Too Many|ошибк|Error', t[:300], re.I) and '▸' not in t and 'ИТОГО' not in t:
        warn('%s: похоже на ошибку площадки, не использую: %s' % (name, t[:120].replace('\n', ' '))); return None
    return t

def N(s):
    """'597 705' / '1 261' / '4.7' → число"""
    s = re.sub(r'[\s  ]', '', s).replace(',', '.')
    return float(s) if '.' in s else int(s)
NUM = r'(\d[\d \u00a0\u202f]*(?:[.,]\d+)?)'

def loadj(n):
    try: return json.load(open(os.path.join(API, n), encoding='utf-8'))
    except Exception: return {}
def savej(n, d): json.dump(d, open(os.path.join(API, n), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def mweeks(mm, full=False):
    y, m = int(mm[:4]), int(mm[5:])
    upto = datetime.date(y, m, calendar.monthrange(y, m)[1])
    if not full: upto = min(upto, TODAY)
    return weeks(y, m, upto)

def months_in_raw():
    ms = set()
    for p in glob.glob(os.path.join(RAW, '*_20??-??*.txt')):
        m = re.search(r'_(20\d\d-\d\d)', os.path.basename(p)); ms.add(m.group(1))
    return sorted(ms)
MONTHS = months_in_raw()
CUR = TODAY.strftime('%Y-%m')

# ================= OZON: заказы =================
def oz_prod(name):
    n = name.lower()
    if 'аппликатор' in n: return 'appl'
    if 'активатор' in n: return 'pack2' if re.search(r'2\s*шт', n) else 'single'
    return None
def parse_oz_orders(t):
    r = dict(ship=0, ssum=0, cancel=0, delivered=0, single=[0, 0], pack2=[0, 0], appl=[0, 0])
    m = re.search(r'Отправлений:\s*' + NUM + r'\s*на\s*' + NUM, t)
    if not m:
        if re.search(r'Отправлений:\s*0|нет заказов|Заказов не', t, re.I): return r
        raise ValueError('нет строки «Отправлений»')
    r['ship'], r['ssum'] = N(m.group(1)), N(m.group(2))
    m = re.search(r'Отменено:\s*' + NUM, t); r['cancel'] = N(m.group(1)) if m else 0
    m = re.search(r'•\s*доставлен:\s*' + NUM, t); r['delivered'] = N(m.group(1)) if m else 0
    top = t.split('ТОП ТОВАРОВ:')[1].split('\n\n')[0] if 'ТОП ТОВАРОВ:' in t else ''
    for name, q, s in re.findall(r'•\s*(.+?):\s*' + NUM + r'\s*шт\.\s*на\s*' + NUM, top):
        p = oz_prod(name)
        if not p: warn('Ozon: незнакомый товар «%s» — не учтён' % name.strip()); continue
        r[p][0] += N(q); r[p][1] += N(s)
    return r

def do_oz_orders():
    D = loadj('ozon_orders.json')
    for mm in MONTHS:
        W = mweeks(mm, full=(mm != CUR))
        res = {}
        for i, a, b in W:
            t = rd('ozon_orders_%s_w%d.txt' % (mm, i + 1))
            if t is None: break
            try: res[i] = parse_oz_orders(t)
            except Exception as e: warn('ozon_orders %s нед.%d: %s' % (mm, i + 1, e)); break
        if len(res) != len(W):
            if any(os.path.exists(os.path.join(RAW, 'ozon_orders_%s_w%d.txt' % (mm, i + 1))) for i, _, _ in W):
                warn('Ozon заказы %s: не все недели — оставляю прошлые цифры' % mm)
            continue
        wk = []
        for i in range(5):
            x = res.get(i)
            if not x: wk.append(dict(qty=0, sum=0, delivered=0, appl_qty=0, appl_sum=0)); continue
            wk.append(dict(qty=x['single'][0] + x['pack2'][0], sum=x['single'][1] + x['pack2'][1],
                           delivered=x['delivered'], appl_qty=x['appl'][0], appl_sum=x['appl'][1]))
        S = lambda k, j: sum(x[k][j] for x in res.values())
        ship = sum(x['ship'] for x in res.values()) - S('appl', 0)
        tot = S('single', 1) + S('pack2', 1)
        old = D.get(mm) or {}
        D[mm] = dict(ship=ship, sum=tot, avg=round(tot / ship) if ship else 0,
                     cancel=sum(x['cancel'] for x in res.values()), delivered=sum(x['delivered'] for x in res.values()),
                     items=dict(single=dict(qty=S('single', 0), sum=S('single', 1)), pack2=dict(qty=S('pack2', 0), sum=S('pack2', 1))),
                     weeks=wk, note='снято автоматически %s' % TODAY.strftime('%d.%m.%Y'))
        DONE.append('Ozon заказы %s: %d позиций (было %s), доставлено %d' % (mm, sum(w['qty'] for w in wk),
                    sum(w.get('qty', 0) for w in old.get('weeks', [])) if old else '—', D[mm]['delivered']))
    savej('ozon_orders.json', D)

# ================= OZON: реклама =================
def parse_oz_ads(t):
    camps = []
    for blk in re.split(r'\n\s*▸\s*', t)[1:]:
        name = re.sub(r'\s*\(id \d+\)\s*$', '', blk.split('\n')[0]).strip()
        g = lambda rx: (N(re.search(rx, blk).group(1)) if re.search(rx, blk) else 0)
        camps.append(dict(name=name, spend=g(r'расход\s*' + NUM), orders=g(r'заказы\s*' + NUM),
                          sum=g(r'заказы\s*\d+\s*на\s*' + NUM), clicks=g(r'клики\s*' + NUM), shows=g(r'показы\s*' + NUM)))
    if not camps and 'ИТОГО' not in t: raise ValueError('нет кампаний и итога')
    return camps
def do_oz_ads():
    D = loadj('ozon_ads.json')
    mm = CUR; W = mweeks(mm); res = {}
    for i, a, b in W:
        t = rd('ozon_ads_%s_w%d.txt' % (mm, i + 1))
        if t is None: break
        try: res[i] = parse_oz_ads(t)
        except Exception as e: warn('ozon_ads %s нед.%d: %s' % (mm, i + 1, e)); break
    if len(res) != len(W): warn('Ozon реклама %s: не все недели — оставляю прошлые цифры' % mm); return
    wk = []; agg = {}
    for i in range(5):
        cs = res.get(i, [])
        wk.append(dict(spend=sum(c['spend'] for c in cs), orders=sum(c['orders'] for c in cs),
                       sum=sum(c['sum'] for c in cs), clicks=sum(c['clicks'] for c in cs)))
        for c in cs:
            a = agg.setdefault(c['name'], dict(name=c['name'], spend=0, orders=0, sum=0, clicks=0, shows=0))
            for k in ('spend', 'orders', 'sum', 'clicks', 'shows'): a[k] += c[k]
    camps = [dict((k, v) for k, v in c.items() if k != 'shows') for c in agg.values() if c['spend'] or c['orders']]
    T = lambda k: sum(w[k] for w in wk)
    D[mm] = dict(spend=T('spend'), orders=T('orders'), sum=T('sum'), clicks=T('clicks'),
                 shows=sum(c['shows'] for c in agg.values()), weeks=wk, campaigns=camps)
    DONE.append('Ozon реклама %s: расход %d ₽, заказов %d' % (mm, T('spend'), T('orders')))
    savej('ozon_ads.json', D)

# ================= OZON: UTM =================
def parse_utm(t):
    out = {}
    for blk in re.split(r'\n\s*▸\s*', t)[1:]:
        name = blk.split('\n')[0].strip()
        if name == '(не указано)': continue
        g = lambda rx: (N(re.search(rx, blk).group(1)) if re.search(rx, blk) else 0)
        out[name] = dict(s=g(r'сессии\s*' + NUM), c=g(r'карточка\s*' + NUM), cart=g(r'корзина\s*' + NUM),
                         o_sess=g(r'заказы:\s*' + NUM + r'\s*в сессии'), o_attr=g(r'/\s*' + NUM + r'\s*с учётом'),
                         sum=g(r'сумма \(окно атрибуции\):\s*' + NUM))
    if 'ИТОГО' not in t: raise ValueError('нет строки ИТОГО — ответ неполный')
    return out
def do_utm():
    mm = CUR
    U = loadj('ozon_utm.json'); Dp = loadj('ozon_utm_deep.json')
    for g in ('campaign', 'content', 'term'):
        t = rd('ozon_utm_%s_%s.txt' % (mm, g))
        if t is None: warn('UTM %s %s: файла нет — оставляю прошлые цифры' % (mm, g)); continue
        try: d = parse_utm(t)
        except Exception as e: warn('UTM %s %s: %s' % (mm, g, e)); continue
        if g == 'campaign': U[mm] = d
        else: Dp.setdefault(g, {})[mm] = d
        if g == 'campaign':
            DONE.append('UTM %s: %d кампаний, заказов (окно) %d на %d ₽' % (mm, len(d), sum(x['o_attr'] for x in d.values()), sum(x['sum'] for x in d.values())))
    U['_note'] = 'обновлено автоматически %s' % TODAY.strftime('%d.%m.%Y')
    savej('ozon_utm.json', U); savej('ozon_utm_deep.json', Dp)

# ================= WB: воронка =================
def parse_wb_funnel(t):
    out = {}
    for blk in re.split(r'\n\s*▸\s*', t)[1:]:
        head = blk.split('\n')[0]
        prod = 'appl' if re.search(r'applik|аппликатор', head, re.I) else 'atf'
        g = lambda rx: (N(re.search(rx, blk).group(1)) if re.search(rx, blk) else 0)
        a = out.setdefault(prod, dict(orders=0, sum=0, buyouts=0, buysum=0, clicks=0, rating=None))
        a['orders'] += g(r'заказы\s*' + NUM); a['sum'] += g(r'заказы\s*\d+\s*на\s*' + NUM)
        a['buyouts'] += g(r'ВЫКУПЛЕНО\s*' + NUM); a['buysum'] += g(r'ВЫКУПЛЕНО\s*\d+\s*на\s*' + NUM)
        a['clicks'] += g(r'переходы\s*' + NUM)
        m = re.search(r'рейтинг\s*(\d[.,]\d)', blk)
        if m and a['rating'] is None: a['rating'] = float(m.group(1).replace(',', '.'))
    if not out: raise ValueError('нет товаров')
    return out
def parse_wb_byday(t):
    return {d: N(o) for d, o in re.findall(r'(\d{4}-\d\d-\d\d):.*?заказы\s*' + NUM, t)}
def do_wb_funnel():
    D = loadj('wb_funnel.json')
    t = rd('wb_funnel_byday.txt'); days = {}
    if t:
        try: days = parse_wb_byday(t)
        except Exception as e: warn('WB по дням: %s' % e)
    for d, o in days.items():
        D.setdefault(d[:7], {}).setdefault('_days', {})[d] = o
    for mm in MONTHS:
        t = rd('wb_funnel_%s.txt' % mm)
        if t is None: continue
        try: P = parse_wb_funnel(t)
        except Exception as e: warn('WB воронка %s: %s' % (mm, e)); continue
        old = D.get(mm) or {}
        dd = old.get('_days', {})
        y, m = int(mm[:4]), int(mm[5:])
        last = TODAY.day if mm == CUR else calendar.monthrange(y, m)[1]
        if mm == CUR or not any(isinstance(v, dict) and v.get('weeks') for k, v in old.items() if k != '_days'):
            # недели: известные дни — как есть, неизвестные — поровну из остатка
            known = {d: o for d, o in dd.items() if d[:7] == mm and int(d[8:]) <= last}
            tot = sum(v['orders'] for v in P.values())
            miss = [k for k in range(1, last + 1) if '%s-%02d' % (mm, k) not in known]
            rest = max(0, tot - sum(known.values())); per = rest / len(miss) if miss else 0
            wks = [0.0] * 5
            for k in range(1, last + 1):
                ds = '%s-%02d' % (mm, k); wks[widx(datetime.date(y, m, k))] += known.get(ds, per)
            wks = [round(x) for x in wks]
            if len(miss) > 2: warn('WB %s: нет разбивки по дням за %d дн. — разнесено поровну' % (mm, len(miss)))
        else:
            wks = None
        new = {'_days': dd}
        for prod, a in P.items():
            w = wks if wks is not None else (old.get(prod) or {}).get('weeks') or [a['orders'], 0, 0, 0, 0]
            new[prod] = dict(a, weeks=w)
        D[mm] = new
        DONE.append('WB воронка %s: заказов %s, выкупов %s' % (mm, '/'.join(str(v['orders']) for v in P.values()), '/'.join(str(v['buyouts']) for v in P.values())))
    savej('wb_funnel.json', D)
    return {p: a.get('rating') for p, a in (D.get(CUR) or {}).items() if isinstance(a, dict) and a.get('rating')}

# ================= WB: реклама =================
def do_wb_ads():
    mm = CUR; t = rd('wb_ads_%s.txt' % mm)
    if t is None: warn('WB реклама %s: файла нет — оставляю прошлые цифры' % mm); return
    try:
        camps = []; cancel = 0
        for blk in re.split(r'\n\s*▸\s*', t)[1:]:
            name = re.sub(r'\s*\(id \d+\)\s*$', '', blk.split('\n')[0]).strip()
            g = lambda rx: (N(re.search(rx, blk).group(1)) if re.search(rx, blk) else 0)
            c = dict(name=name, spend=g(r'расход\s*' + NUM), orders=g(r'заказы\s*' + NUM), sum=g(r'заказов на\s*' + NUM),
                     clicks=g(r'клики\s*' + NUM), shows=g(r'показы\s*' + NUM))
            cancel += g(r'отменено:\s*' + NUM)
            if c['spend'] or c['orders']: camps.append(c)
        if 'ИТОГО' not in t: raise ValueError('нет ИТОГО')
    except Exception as e: warn('WB реклама %s: %s' % (mm, e)); return
    D = loadj('wb_ads.json'); T = lambda k: sum(c[k] for c in camps)
    D[mm] = dict(spend=T('spend'), orders=T('orders'), sum=T('sum'), clicks=T('clicks'), shows=T('shows'), cancel=cancel, campaigns=camps)
    DONE.append('WB реклама %s: расход %d ₽, заказов %d' % (mm, T('spend'), T('orders')))
    savej('wb_ads.json', D)

# ================= АВИТО =================
def parse_av_orders(t):
    m = re.search(r'Заказов:\s*' + NUM + r'(?:\s*на\s*' + NUM + ')?', t)
    if not m: raise ValueError('нет строки «Заказов»')
    r = dict(orders=N(m.group(1)), sum=N(m.group(2)) if m.group(2) else 0, buy=0, buysum=0, cancel=0, transit=0)
    for st, q, s in re.findall(r'•\s*([a-z_]+):\s*' + NUM + r'(?:\s*на\s*' + NUM + ')?', t):
        q = N(q); s = N(s) if s else 0
        if st in ('delivered', 'closed'): r['buy'] += q; r['buysum'] += s
        elif st in ('canceled', 'cancelled'): r['cancel'] += q
        else: r['transit'] += q
    return r
def do_avito():
    D = loadj('avito.json')
    for mm in MONTHS:
        per = D.setdefault(mm, {}); A = per.setdefault('atf', {})
        W0 = A.get('weeks') or [dict(shows=0, views=0, contacts=0, spend=0, orders=0, sum=0, buy=0, buysum=0, cancel=0, transit=0) for _ in range(5)]
        W = [dict(x) for x in W0]
        # показы/просмотры/контакты/расход — только текущий месяц, по дням
        if mm == CUR:
            t = rd('avito_stats_%s_byday.txt' % mm)
            if t is None: warn('Авито статистика %s: файла нет — оставляю прошлые цифры' % mm)
            else:
                rows = re.findall(r'(\d{4}-\d\d-\d\d):\s*показы\s*' + NUM + r'.*?просмотры\s*' + NUM + r'.*?контакты\s*' + NUM + r'.*?расход\s*' + NUM, t)
                if not rows and 'Всего строк: 0' not in t: warn('Авито статистика %s: не разобралась' % mm)
                else:
                    for x in W:
                        for k in ('shows', 'views', 'contacts', 'spend'): x[k] = 0
                    for d, sh, vw, ct, sp in rows:
                        i = widx(datetime.date.fromisoformat(d))
                        W[i]['shows'] += N(sh); W[i]['views'] += N(vw); W[i]['contacts'] += N(ct); W[i]['spend'] += N(sp)
                    A['msgs'] = sum(x['contacts'] for x in W); A.setdefault('calls', 0)
        wk = mweeks(mm, full=(mm != CUR)); res = {}
        for i, a, b in wk:
            t = rd('avito_orders_%s_w%d.txt' % (mm, i + 1))
            if t is None: break
            try: res[i] = parse_av_orders(t)
            except Exception as e: warn('Авито заказы %s нед.%d: %s' % (mm, i + 1, e)); break
        if len(res) == len(wk):
            for i in range(5):
                x = res.get(i, dict(orders=0, sum=0, buy=0, buysum=0, cancel=0, transit=0))
                W[i].update(x)
            DONE.append('Авито %s: заказов %d, выкуплено %d, расход %d ₽' % (mm, sum(x['orders'] for x in W), sum(x['buy'] for x in W), sum(x['spend'] for x in W)))
        elif any(os.path.exists(os.path.join(RAW, 'avito_orders_%s_w%d.txt' % (mm, i + 1))) for i, _, _ in wk):
            warn('Авито заказы %s: не все недели — оставляю прошлые цифры' % mm)
        A['weeks'] = W; A.setdefault('selfbuy', [0] * 5); A.setdefault('selfbuy_sum', [0] * 5)
        A['note'] = 'обновлено автоматически %s' % TODAY.strftime('%d.%m.%Y')
    savej('avito.json', D)

# ================= РЕЙТИНГ =================
def do_rating(wbr):
    R = loadj('rating.json'); t = rd('ozon_rating.txt')
    oz = None; content = {}
    if t:
        m = re.search(r'Оценка товаров:\s*(\d[.,]\d+)', t); oz = float(m.group(1).replace(',', '.')) if m else None
        for name, v in re.findall(r'•\s*(.+?)\s*\(sku \d+\):\s*(\d+(?:[.,]\d+)?)\s*из 100', t):
            p = oz_prod(name); key = {'single': 'Активатор 250 мл', 'pack2': 'Активатор 250 мл 2 шт', 'appl': 'Аппликатор Ермакова'}.get(p)
            if key: content[key] = float(v.replace(',', '.'))
    else: warn('рейтинг Ozon: файла нет')
    prev = R.get('Ozon') or {}
    ozd = {'atf': oz} if oz else prev
    wbd = {k: v for k, v in wbr.items()} or (R.get('Wildberries') or {})
    av = (loadj('avito.json').get('rating') or {}).get('seller')
    R.update({'date': TODAY.isoformat(), 'month': CUR, 'week_index': widx(TODAY), 'Ozon': ozd, 'Wildberries': wbd})
    if av: R['Авито'] = {'atf': av}
    if content: R['content'] = content
    H = [h for h in R.get('history', []) if h.get('date') != TODAY.isoformat()]
    H.append({'date': TODAY.isoformat(), 'Ozon': ozd, 'Wildberries': wbd, **({'Авито': {'atf': av}} if av else {})})
    R['history'] = H
    savej('rating.json', R)

if __name__ == '__main__':
    if not RAW or not os.path.isdir(RAW): sys.exit('нет папки с ответами: %s' % RAW)
    print('Разбираю', RAW, '— месяцы:', ', '.join(MONTHS) or '—')
    for f in (do_oz_orders, do_oz_ads, do_utm, do_wb_ads, do_avito):
        try: f()
        except Exception as e: warn('%s упал: %s' % (f.__name__, e))
    try: wbr = do_wb_funnel()
    except Exception as e: warn('do_wb_funnel упал: %s' % e); wbr = {}
    try: do_rating(wbr)
    except Exception as e: warn('рейтинг: %s' % e)
    print('\n'.join('ok  ' + s for s in DONE))
    print('API: обновлено блоков %d, предупреждений %d' % (len(DONE), len(WARN)))
    sys.exit(0)
