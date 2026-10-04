#!/bin/bash
# Ежедневное обновление дашборда: таблицы из Google → сборка → публикация.
# Публикуется в St-karta/bk-dashboard, страница закрыта паролем (protect.py).
# Секреты (ключ GitHub, пароль дашборда, адрес и ключ Google-скрипта) — в ../.private, в GitHub не попадают.
# Запуск: bash update.sh        (без публикации: NOPUSH=1 bash update.sh)
set -u
ENG="$(cd "$(dirname "$0")" && pwd)"; DASH="$(dirname "$ENG")"; PRIV="$DASH/.private"
REPO="$HOME/bkrepo_st"; REMOTE="git@github.com:St-karta/bk-dashboard.git"; LOG="$ENG/logs/$(date +%F_%H%M).log"; mkdir -p "$ENG/logs"
export GIT_SSH_COMMAND="ssh -i $PRIV/bkdash_st2 -o IdentitiesOnly=yes -o UserKnownHostsFile=$PRIV/known_hosts -o StrictHostKeyChecking=yes"
say(){ echo "$*" | tee -a "$LOG"; }
cd "$ENG" || exit 9
say "== $(date '+%d.%m.%Y %H:%M') обновление дашборда"

# 0. данные площадок: если задача сегодня сохранила ответы API в raw/<дата> — разбираем
RAWD="$ENG/raw/$(date +%F)"
if ls "$RAWD"/*.txt >/dev/null 2>&1; then
  rm -rf api.prev && cp -r api api.prev
  python3 api_ingest.py "$RAWD" 2>&1 | tee -a "$LOG"
else
  say "API: свежих ответов за сегодня нет — данные площадок прежние"
fi

# 1. таблицы
python3 fetch_sheets.py 2>&1 | tee -a "$LOG"; FETCH=${PIPESTATUS[0]}
[ "$FETCH" = 0 ] || say "! часть таблиц не скачалась — собираю на прошлых версиях"

# 2. сборка (старый результат сохраняем для сравнения)
cp -f records.json records.prev.json 2>/dev/null
if ! python3 build.py >> "$LOG" 2>&1; then say "СТОП: сборка упала, дашборд не публикую. Хвост лога:"; tail -15 "$LOG"; exit 2; fi
python3 mk.py >> "$LOG" 2>&1 || { say "СТОП: mk.py упал"; exit 3; }
grep -A5 "НЕ РАСКРЫТЫ" "$LOG" | head -8

# 3. проверка на здравый смысл: закрытые/текущие месяцы не должны прыгнуть больше чем на 30%
python3 - <<'PY' >> "$LOG" 2>&1 || { say "СТОП: цифры прыгнули подозрительно, не публикую:"; tail -6 "$LOG"; exit 4; }
import json,sys
def tot(f):
    try: R=json.load(open(f))['records']
    except Exception: return None
    t={}
    for r in R:
        w=r.get('w') or []
        t.setdefault(r['m'],[0,0])
        t[r['m']][0]+=sum(x[0] or 0 for x in w); t[r['m']][1]+=sum(x[1] or 0 for x in w)
    return t
a,b=tot('records.prev.json'),tot('records.json')
bad=[]
for m,(s,o) in (a or {}).items():
    s2,o2=b.get(m,[0,0])
    for n,x,y in (('расход',s,s2),('заказы',o,o2)):
        if x>1000 and abs(y-x)/x>0.3: bad.append('%s %s: было %s, стало %s'%(m,n,round(x),round(y)))
print('сверка с прошлой сборкой:', 'ок' if not bad else '; '.join(bad))
sys.exit(1 if bad else 0)
PY
grep -E "^20[0-9]{2}-[0-9]{2}: расход" "$LOG" | tail -2
SZ=$(wc -c < dashboard-influence.html); [ "$SZ" -gt 300000 ] || { say "СТОП: файл дашборда слишком маленький ($SZ байт)"; exit 5; }
cp dashboard-influence.html "$DASH/index.html"

# 4. публикация
[ "${NOPUSH:-0}" = 1 ] && { say "собрано, публикация пропущена (NOPUSH)"; exit 0; }
if [ ! -d "$REPO/.git" ]; then git clone -q --depth 1 "$REMOTE" "$REPO" >> "$LOG" 2>&1 || { say "СТОП: не смог скачать репозиторий"; exit 6; }; fi
cd "$REPO" && git pull -q --rebase >> "$LOG" 2>&1
python3 "$ENG/protect.py" "$ENG/dashboard-influence.html" "$ENG/index.locked.html" >> "$LOG" 2>&1 || { say "СТОП: не смог закрыть дашборд паролем — не публикую"; exit 8; }
cp "$ENG/index.locked.html" index.html
git -c user.name="BK dashboard" -c user.email="vetal.wellness@gmail.com" add index.html
if git diff --cached --quiet; then say "изменений нет, публиковать нечего"; exit 0; fi
git -c user.name="BK dashboard" -c user.email="vetal.wellness@gmail.com" commit -q -m "Автообновление $(date +%d.%m.%Y)" && git push -q origin HEAD >> "$LOG" 2>&1 \
  && say "опубликовано: $(git log --oneline -1)" || { say "СТОП: публикация не прошла"; tail -5 "$LOG"; exit 7; }
