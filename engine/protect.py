"""Закрывает дашборд паролем: шифрует готовую страницу (AES-256-GCM, ключ из пароля через
PBKDF2-SHA256) и кладёт её внутрь страницы-замка. Без пароля в файле только шифр.
Пароль и «соль» — в Дашборд/.private/dash_pass.json (в GitHub не попадают).
Запуск: python3 protect.py вход.html выход.html"""
import sys, os, json, base64, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITER = 250000
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, '..', '.private', 'dash_pass.json')

def main(src, dst):
    c = json.load(open(CFG))
    salt = base64.b64decode(c['salt'])
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(c['password'].encode())
    iv = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(iv, open(src, 'rb').read(), None)
    b = lambda x: base64.b64encode(x).decode()
    page = LOCK.replace('__SALT__', b(salt)).replace('__IV__', b(iv)).replace('__ITER__', str(ITER)).replace('__CT__', b(ct))
    open(dst, 'w', encoding='utf-8').write(page)
    print('закрыто паролем: %s (%d КБ)' % (dst, len(page) // 1024))

LOCK = r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>Дашборд — вход</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1d2330;--mut:#6b7385;--ac:#2f6fed;--bd:#dfe3ea;--er:#c62828}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2129;--tx:#e8ebf1;--mut:#9aa3b2;--ac:#6b9bff;--bd:#2e3440;--er:#ff6b6b}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:var(--bg);color:var(--tx);font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;padding:16px}
.c{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:28px 24px;width:100%;max-width:360px}
h1{font-size:18px;margin:0 0 4px}p{margin:0 0 18px;color:var(--mut);font-size:13px}
input[type=password]{width:100%;padding:11px 12px;font-size:16px;border:1px solid var(--bd);border-radius:9px;background:transparent;color:var(--tx)}
label{display:flex;gap:8px;align-items:center;margin:12px 0 16px;font-size:13px;color:var(--mut)}
button{width:100%;padding:11px;font-size:15px;border:0;border-radius:9px;background:var(--ac);color:#fff;cursor:pointer}
button:disabled{opacity:.6}.e{color:var(--er);font-size:13px;min-height:18px;margin-top:10px}
</style></head><body>
<form class="c" id="f" autocomplete="on">
<h1>Дашборд инфлюенс-маркетинга</h1><p>Доступ по паролю</p>
<input type="text" name="username" value="bk-dashboard" autocomplete="username" hidden>
<input type="password" id="p" autocomplete="current-password" placeholder="Пароль" autofocus>
<label><input type="checkbox" id="r" checked> Запомнить на этом устройстве</label>
<button id="b">Открыть</button><div class="e" id="e"></div>
</form>
<script>
const S='__SALT__',IV='__IV__',IT=__ITER__,CT='__CT__',LK='bkdash-key-'+S;
const u=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function open_(raw){
  const k=await crypto.subtle.importKey('raw',raw,'AES-GCM',false,['decrypt']);
  const d=await crypto.subtle.decrypt({name:'AES-GCM',iv:u(IV)},k,u(CT));
  const h=new TextDecoder().decode(d);document.open();document.write(h);document.close();
}
async function derive(pw){
  const m=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',salt:u(S),iterations:IT,hash:'SHA-256'},m,256));
}
window.addEventListener('load',()=>setTimeout(async()=>{let s=null;try{s=localStorage.getItem(LK)}catch(e){}
  if(s){try{await open_(u(s));return}catch(e){try{localStorage.removeItem(LK)}catch(_){}}}},0));
document.getElementById('f').addEventListener('submit',async ev=>{ev.preventDefault();
  const b=document.getElementById('b'),e=document.getElementById('e');b.disabled=true;e.textContent='';
  try{const raw=await derive(document.getElementById('p').value);
    if(document.getElementById('r').checked){try{localStorage.setItem(LK,btoa(String.fromCharCode(...raw)))}catch(_){}}
    await open_(raw);
  }catch(x){e.textContent='Неверный пароль';b.disabled=false}});
</script></body></html>'''

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
