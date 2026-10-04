"""Печатает список запросов к API площадок на сегодня: какой инструмент, с какими
параметрами и в какой файл сохранить ответ. Используется ежедневной задачей.
Запуск: python3 api_plan.py [ГГГГ-ММ-ДД]   → печатает план и raw-папку дня."""
import sys, datetime, calendar, json, os

def widx(d):
    dd = d.day
    if d.year == 2026 and d.month == 8: return 0 if dd <= 9 else 1 if dd <= 16 else 2 if dd <= 23 else 3 if dd <= 30 else 4
    if d.year == 2026 and d.month == 9: return 0 if dd <= 6 else 1 if dd <= 13 else 2 if dd <= 20 else 3 if dd <= 27 else 4
    return 0 if dd <= 7 else 1 if dd <= 14 else 2 if dd <= 21 else 3 if dd <= 28 else 4

def weeks(y, m, upto):
    """недели дашборда месяца, начавшиеся не позже upto: [(i, d_from, d_to)]"""
    last = calendar.monthrange(y, m)[1]
    out = {}
    for day in range(1, last + 1):
        d = datetime.date(y, m, day)
        if d > upto: break
        i = widx(d)
        out.setdefault(i, [d, d])[1] = d
    return [(i, a, b) for i, (a, b) in sorted(out.items())]

def plan(today):
    y, m = today.year, today.month
    mm = '%04d-%02d' % (y, m)
    first = datetime.date(y, m, 1)
    f = lambda d: d.strftime('%Y-%m-%d')
    P = []
    add = lambda tool, args, file: P.append(dict(tool=tool, args=args, file=file))
    W = weeks(y, m, today)
    # --- Ozon (лимиты щедрые) ---
    for i, a, b in W: add('ozon_orders', dict(date_from=f(a), date_to=f(b)), 'ozon_orders_%s_w%d.txt' % (mm, i + 1))
    for i, a, b in W: add('ozon_ads_stats', dict(date_from=f(a), date_to=f(b)), 'ozon_ads_%s_w%d.txt' % (mm, i + 1))
    for g in ('campaign', 'content', 'term'):
        add('ozon_utm', dict(date_from=f(first), date_to=f(today), group_by=g), 'ozon_utm_%s_%s.txt' % (mm, g))
    add('ozon_rating', {}, 'ozon_rating.txt')
    # --- WB: строго по одному, между двумя «Аналитиками» пауза ---
    add('wb_funnel', dict(date_from=f(first), date_to=f(today)), 'wb_funnel_%s.txt' % mm)
    add('wb_ads_stats', dict(date_from=f(first), date_to=f(today)), 'wb_ads_%s.txt' % mm)
    add('PAUSE', dict(seconds=65), '')
    # по дням — только последние 7 дней (больший период WB не отдаёт); дни копятся в wb_funnel.json
    add('wb_funnel', dict(date_from=f(today - datetime.timedelta(days=6)), date_to=f(today), by_day=True), 'wb_funnel_byday.txt')
    # --- Авито ---
    add('avito_stats', dict(date_from=f(first), date_to=f(today), group_by='day'), 'avito_stats_%s_byday.txt' % mm)
    for i, a, b in W: add('avito_orders', dict(date_from=f(a), date_to=f(b)), 'avito_orders_%s_w%d.txt' % (mm, i + 1))
    # --- прошлый месяц: первые 10 дней досчитываем доставки/выкупы ---
    if today.day <= 10:
        py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
        pmm = '%04d-%02d' % (py, pm)
        PW = weeks(py, pm, datetime.date(py, pm, calendar.monthrange(py, pm)[1]))
        for i, a, b in PW: add('ozon_orders', dict(date_from=f(a), date_to=f(b)), 'ozon_orders_%s_w%d.txt' % (pmm, i + 1))
        for i, a, b in PW: add('avito_orders', dict(date_from=f(a), date_to=f(b)), 'avito_orders_%s_w%d.txt' % (pmm, i + 1))
        add('PAUSE', dict(seconds=65), '')
        add('wb_funnel', dict(date_from=f(PW[0][1]), date_to=f(PW[-1][2])), 'wb_funnel_%s.txt' % pmm)
    return P

if __name__ == '__main__':
    import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    today = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    raw = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw', today.isoformat())
    P = plan(today)
    print('RAW_DIR=' + raw)
    print('Запросов: %d. Каждый ответ сохранить ТЕКСТОМ (содержимое поля result, как есть) в RAW_DIR/<файл>.' % sum(1 for p in P if p['tool'] != 'PAUSE'))
    for n, p in enumerate(P, 1):
        if p['tool'] == 'PAUSE':
            print('%2d. ПАУЗА %d сек (device_bash: sleep %d) — лимит WB' % (n, p['args']['seconds'], p['args']['seconds']))
        else:
            print('%2d. %-15s %-80s → %s' % (n, p['tool'], json.dumps(p['args'], ensure_ascii=False), p['file']))
