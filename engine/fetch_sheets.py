"""Скачивает таблицы менеджеров из Google через скрипт «BK dashboard export».
Адрес и ключ — в Дашборд/.private/gs.json (НЕ в GitHub). Файлы кладёт в src/."""
import json, urllib.request, base64, os, sys, datetime, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
CFG  = os.path.join(HERE, '..', '.private', 'gs.json')
NAMES = {'elena': 'elena.xlsx', 'maria': 'maria.xlsm', 'anastasia': 'anastasia.xlsx'}
c = json.load(open(CFG))
src = os.path.join(HERE, 'src'); os.makedirs(src, exist_ok=True)
bad = []
for f, name in NAMES.items():
    try:
        b = urllib.request.urlopen(c['url'] + '?f=' + f + '&key=' + c['key'], timeout=180).read()
        d = json.loads(b); raw = base64.b64decode(d['b64'])
        if len(raw) < 5000 or raw[:2] != b'PK': raise ValueError('не похоже на таблицу (%d байт)' % len(raw))
        p = os.path.join(src, name); tmp = p + '.tmp'
        open(tmp, 'wb').write(raw); os.replace(tmp, p)
        t = datetime.datetime.strptime(d['modified'][:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
        os.utime(p, (t, t))
        print('ok  %-10s %s  правка %s  %d КБ' % (f, d['name'], d['modified'][:16].replace('T', ' '), len(raw) // 1024))
    except Exception as e:
        bad.append(f); print('ERR %-10s %s — оставляю прошлую версию файла' % (f, str(e)[:200]))
sys.exit(1 if bad else 0)
