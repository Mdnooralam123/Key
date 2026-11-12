#!/usr/bin/env python3
# KHAN / Maya License Server - single-file edition
# Python standard library only. Persistent SQLite database; no Redis required.
# Run: python app.py

import os, json, time, sqlite3, secrets, string, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('DB_PATH', str(APP_DIR / 'maya_license.db')))
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'khan123')
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '8000'))
TRIAL_MS = 10 * 60 * 1000
DAY_MS = 86400000
_db_lock = threading.RLock()


def db():
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS devices (hwid TEXT PRIMARY KEY, created_at INTEGER NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, data TEXT NOT NULL)''')


def kv_get(key, default=None):
    with _db_lock, db() as con:
        row = con.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
        if not row: return default
        try: return json.loads(row['value'])
        except Exception: return row['value']


def kv_set(key, value):
    raw = json.dumps(value, separators=(',', ':'))
    with _db_lock, db() as con:
        con.execute('INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, raw))


def kv_incr(key, amount):
    with _db_lock, db() as con:
        row = con.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
        try: current = int(json.loads(row['value'])) if row else 0
        except Exception: current = 0
        current += int(amount)
        con.execute('INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(current)))
        return current


def remember(hwid):
    with _db_lock, db() as con:
        con.execute('INSERT OR IGNORE INTO devices(hwid,created_at) VALUES(?,?)', (hwid, int(time.time()*1000)))


def valid_hwid(h):
    return isinstance(h, str) and 8 <= len(h) <= 128 and all(c.isalnum() or c in '_-' for c in h) and h.isascii()


def get_device(hwid): return kv_get('dev:' + hwid, {}) or {}
def set_device(hwid, data): kv_set('dev:' + hwid, data)
def get_trial(hwid): return int(kv_get('trial:' + hwid, 0) or 0)


def device_status(hwid):
    dev = get_device(hwid)
    used = get_trial(hwid)
    premium, typ, remaining = False, '', ''
    now = int(time.time()*1000)
    if dev.get('premium') and not dev.get('revoked'):
        if dev.get('type') == 'lifetime': premium, typ, remaining = True, 'lifetime', 'Lifetime'
        elif dev.get('expires_at') and now < int(dev['expires_at']):
            premium, typ = True, dev.get('type') or 'premium'
            remaining = str((int(dev['expires_at']) - now + DAY_MS - 1)//DAY_MS) + ' din'
    return {'premium': premium, 'type': typ, 'remaining': remaining,
            'left_ms': 999999999 if premium else max(0, TRIAL_MS-used),
            'used_ms': used, 'hwid': hwid}


def make_key():
    alphabet = string.ascii_uppercase + string.digits
    part = lambda: ''.join(secrets.choice(alphabet) for _ in range(4))
    return f'KHAN-{part()}-{part()}-{part()}'


def json_response(handler, code, data):
    raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(raw)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type, x-admin-token')
    handler.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    handler.end_headers()
    handler.wfile.write(raw)


ADMIN_HTML = r'''<!DOCTYPE html><html lang="hi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Maya Admin</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:16px;background:#f4f7fb;color:#12305a}h1{font-size:22px}.c{background:#fff;border-radius:16px;padding:18px;margin-bottom:14px;box-shadow:0 2px 8px #0001}h3{margin-top:8px}input,select,textarea{width:100%;padding:12px;margin:5px 0;border:1px solid #b4ccea;border-radius:10px;font-size:16px}button{padding:12px 16px;border:0;border-radius:10px;background:#0a9df0;color:#fff;font-weight:700;margin:5px 5px 5px 0;font-size:15px}button.r{background:#c62828}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#0d1533;color:#cfe0ff;padding:14px;border-radius:12px;max-height:280px;overflow:auto}.muted{color:#60738c;font-size:13px}
</style></head><body>
<h1>🛠 Maya Admin</h1>
<div class="c"><h3>Admin connection</h3><div class="muted">Ye panel isi server se connected hai. Koi base URL enter karne ki zaroorat nahi.</div><label>Admin token</label><input id="tok" type="password" placeholder="Admin token"><button onclick="saveTok()">Token save karo</button><span id="authst" class="muted"></span></div>
<div class="c"><h3>Naya key banao</h3><select id="kt"><option value="lifetime">Lifetime (hamesha)</option><option value="yearly">Yearly (365 din)</option><option value="monthly">Monthly (30 din)</option></select><input id="kk" placeholder="Custom key (khaali = auto)"><button onclick="mkKey()">Key banao</button><pre id="kout"></pre><button onclick="listKeys()">Saari keys dekho</button><pre id="klist"></pre></div>
<div class="c"><h3>Devices (HWID)</h3><button onclick="listDev()">Devices load karo</button><pre id="dlist"></pre><input id="dh" placeholder="HWID (list se copy karo)"><input id="dd" type="number" placeholder="Din (grant ke liye)" value="30"><button onclick="devAct('grant_days')">Premium do (din)</button><button onclick="devAct('reset_trial')">Trial reset</button><button class="r" onclick="devAct('revoke')">Band karo</button><button onclick="devAct('unrevoke')">Wapas chalu</button><pre id="dout"></pre></div>
<div class="c"><h3>APK update bhejo</h3><input id="uv" type="number" placeholder="Version number (jaise 34)"><input id="ua" placeholder="APK link (https://...apk)"><textarea id="un" placeholder="Kya naya hai"></textarea><button onclick="pushUpd()">Update bhejo</button><pre id="uout"></pre><button onclick="loadUpd()">Current update dekho</button></div>
<div class="c"><button onclick="health()">Server / database check</button><pre id="healthout"></pre></div>
<script>
const T=()=>localStorage.getItem('mtok')||'';
function saveTok(){localStorage.setItem('mtok',document.getElementById('tok').value.trim());document.getElementById('authst').textContent='Saved';health()}
async function api(path,opt={}){let r;try{r=await fetch(path,Object.assign({headers:{'Content-Type':'application/json','x-admin-token':T()}},opt));}catch(e){return {ok:false,message:'Network: '+e.message}}try{return await r.json()}catch(e){return {ok:false,message:'Server ne JSON nahi diya'}}}
async function mkKey(){const b={type:document.getElementById('kt').value};const k=document.getElementById('kk').value.trim();if(k)b.key=k;document.getElementById('kout').textContent=JSON.stringify(await api('/api/admin/key',{method:'POST',body:JSON.stringify(b)}),null,2)}
async function listKeys(){document.getElementById('klist').textContent=JSON.stringify(await api('/api/admin/keys'),null,2)}
async function listDev(){document.getElementById('dlist').textContent=JSON.stringify(await api('/api/admin/devices'),null,2)}
async function devAct(a){document.getElementById('dout').textContent=JSON.stringify(await api('/api/admin/device',{method:'POST',body:JSON.stringify({hwid:document.getElementById('dh').value.trim(),action:a,days:Number(document.getElementById('dd').value)||30})}),null,2)}
async function pushUpd(){document.getElementById('uout').textContent=JSON.stringify(await api('/api/admin/update',{method:'POST',body:JSON.stringify({version:Number(document.getElementById('uv').value),apk_url:document.getElementById('ua').value.trim(),notes:document.getElementById('un').value.trim()})}),null,2)}
async function loadUpd(){document.getElementById('uout').textContent=JSON.stringify(await api('/api/update'),null,2)}
async function health(){document.getElementById('healthout').textContent=JSON.stringify(await api('/api/health'),null,2)}
document.getElementById('tok').value=T();
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = 'MayaLicenseServer/1.0'

    def log_message(self, fmt, *args):
        print('[%s] %s' % (self.log_date_time_string(), fmt % args))

    def send_html(self, html):
        raw = html.encode('utf-8')
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def body_json(self):
        try:
            n = int(self.headers.get('Content-Length','0'))
            if n > 1024*1024: return {}
            return json.loads(self.rfile.read(n).decode('utf-8') or '{}') if n else {}
        except Exception: return {}

    def admin(self): return bool(ADMIN_TOKEN) and self.headers.get('x-admin-token','') == ADMIN_TOKEN

    def require_admin(self):
        if not self.admin():
            json_response(self,401,{'ok':False,'message':'admin token galat'})
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Headers','Content-Type, x-admin-token')
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.end_headers()

    def do_GET(self):
        u=urlparse(self.path); path=u.path.rstrip('/') or '/'; q=parse_qs(u.query)
        if path in ('/','/admin','/admin.html'):
            return self.send_html(ADMIN_HTML)
        if path == '/api/health':
            return json_response(self,200,{'ok':True,'database':'sqlite','database_file':DB_PATH.name,'admin_token_configured':bool(ADMIN_TOKEN)})
        try:
            if path == '/api/status':
                hwid=(q.get('hwid') or [''])[0]
                if not valid_hwid(hwid): return json_response(self,400,{'ok':False,'message':'hwid galat'})
                remember(hwid); return json_response(self,200,dict({'ok':True},**device_status(hwid)))
            if path == '/api/check' or path == '/check':
                key=(q.get('key') or [''])[0].strip().upper(); hwid=(q.get('hwid') or [''])[0]
                rec=kv_get('key:'+key) if key else None
                if not rec: return json_response(self,200,{'valid':False,'status':'fail','message':'Key galat hai','real':False})
                if rec.get('bound') and hwid and rec['bound'] != hwid:
                    return json_response(self,200,{'valid':False,'status':'fail','message':'Key kisi aur device par lock hai','real':True})
                st=device_status(hwid) if valid_hwid(hwid) else {'premium':False,'remaining':''}
                expired=bool(rec.get('expires_at') and int(time.time()*1000)>int(rec['expires_at']))
                return json_response(self,200,{'valid':not expired and not rec.get('revoked'),'status':'success' if not expired and not rec.get('revoked') else 'fail','real':True,'expired':expired,'type':rec.get('type'),'remaining':'Lifetime' if rec.get('type')=='lifetime' else st.get('remaining',''),'message':'Key valid hai' if not expired else 'Key expire ho chuki hai'})
            if path == '/api/update':
                return json_response(self,200,kv_get('cfg:update',{'version':0,'apk_url':'','notes':''}))
            if path == '/api/admin/keys':
                if not self.require_admin(): return
                with _db_lock, db() as con: rows=con.execute('SELECT key,data FROM keys ORDER BY rowid DESC LIMIT 200').fetchall()
                out=[]
                for row in rows:
                    try: out.append(dict({'key':row['key']},**json.loads(row['data'])))
                    except Exception: pass
                return json_response(self,200,{'ok':True,'keys':out})
            if path == '/api/admin/devices':
                if not self.require_admin(): return
                with _db_lock, db() as con: hs=[r['hwid'] for r in con.execute('SELECT hwid FROM devices ORDER BY created_at DESC LIMIT 300').fetchall()]
                out=[]
                for h in hs:
                    st=device_status(h); dev=get_device(h)
                    out.append({'hwid':h,'premium':st['premium'],'type':st['type'],'remaining':st['remaining'],'used_min':round(st['used_ms']/60000,1),'key':dev.get('key',''),'revoked':bool(dev.get('revoked'))})
                return json_response(self,200,{'ok':True,'devices':out})
            return json_response(self,404,{'ok':False,'message':'route nahi mila'})
        except Exception as e:
            return json_response(self,500,{'ok':False,'message':'server error: '+str(e)})

    def do_POST(self):
        path=urlparse(self.path).path.rstrip('/')
        b=self.body_json()
        try:
            if path == '/api/activate':
                hwid=b.get('hwid'); key=str(b.get('key') or '').strip().upper()
                if not valid_hwid(hwid): return json_response(self,400,{'ok':False,'message':'hwid galat'})
                rec=kv_get('key:'+key) if key else None
                if not rec or rec.get('revoked'): return json_response(self,200,{'ok':False,'message':'Key galat hai ya band ho chuki hai'})
                if rec.get('bound') and rec['bound'] != hwid: return json_response(self,200,{'ok':False,'message':'Ye key kisi aur device par lock hai'})
                if rec.get('expires_at') and int(time.time()*1000)>int(rec['expires_at']): return json_response(self,200,{'ok':False,'message':'Ye key expire ho chuki hai'})
                rec['bound']=hwid; rec['bound_at']=rec.get('bound_at') or int(time.time()*1000); kv_set('key:'+key,rec)
                with _db_lock, db() as con: con.execute('UPDATE keys SET data=? WHERE key=?',(json.dumps(rec),key))
                dev={'premium':True,'revoked':False,'type':rec.get('type'),'key':key,'expires_at':None if rec.get('type')=='lifetime' else (rec.get('expires_at') or int(time.time()*1000)+int(rec.get('days') or 30)*DAY_MS)}
                set_device(hwid,dev); remember(hwid)
                return json_response(self,200,dict({'ok':True,'message':'Premium chalu ho gaya'},**device_status(hwid)))
            if path == '/api/tick':
                hwid=b.get('hwid')
                if not valid_hwid(hwid): return json_response(self,400,{'ok':False,'message':'hwid galat'})
                remember(hwid); ms=max(0,min(int(float(b.get('ms') or 0)),30000)); st=device_status(hwid)
                if not st['premium'] and ms>0: kv_incr('trial:'+hwid,ms)
                return json_response(self,200,dict({'ok':True},**device_status(hwid)))
            if path == '/api/admin/key':
                if not self.require_admin(): return
                key=str(b.get('key') or make_key()).strip().upper()
                if not key or len(key)>100: return json_response(self,400,{'ok':False,'message':'custom key galat'})
                typ=b.get('type') or 'lifetime'
                if typ not in ('lifetime','yearly','monthly'): return json_response(self,400,{'ok':False,'message':'key type galat'})
                days=int(b.get('days') or (365 if typ=='yearly' else 30)); rec={'type':typ,'days':days,'bound':None,'revoked':False,'created_at':int(time.time()*1000)}
                kv_set('key:'+key,rec)
                with _db_lock, db() as con: con.execute('INSERT INTO keys(key,data) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data',(key,json.dumps(rec)))
                return json_response(self,200,{'ok':True,'key':key,'rec':rec})
            if path == '/api/admin/device':
                if not self.require_admin(): return
                hwid=b.get('hwid'); action=b.get('action')
                if not valid_hwid(hwid): return json_response(self,400,{'ok':False,'message':'hwid galat'})
                dev=get_device(hwid)
                if action=='reset_trial': kv_set('trial:'+hwid,0)
                elif action=='grant_days':
                    base=max(int(dev.get('expires_at') or 0),int(time.time()*1000)); dev.update({'premium':True,'revoked':False,'type':dev.get('type') or 'manual','expires_at':base+(int(b.get('days') or 30)*DAY_MS)}); set_device(hwid,dev); remember(hwid)
                elif action=='revoke': dev.update({'revoked':True,'premium':False}); set_device(hwid,dev)
                elif action=='unrevoke': dev.update({'revoked':False}); set_device(hwid,dev)
                else: return json_response(self,400,{'ok':False,'message':'action galat'})
                return json_response(self,200,{'ok':True})
            if path == '/api/admin/update':
                if not self.require_admin(): return
                u={'version':int(b.get('version') or 0),'apk_url':str(b.get('apk_url') or ''),'notes':str(b.get('notes') or '')}
                kv_set('cfg:update',u); return json_response(self,200,{'ok':True,'update':u})
            return json_response(self,404,{'ok':False,'message':'route nahi mila'})
        except Exception as e:
            return json_response(self,500,{'ok':False,'message':'server error: '+str(e)})


def main():
    init_db()
    print('\nKHAN / Maya License Server started')
    print(f'Admin panel: http://127.0.0.1:{PORT}/admin.html')
    print(f'Admin token: {ADMIN_TOKEN}')
    print(f'SQLite database: {DB_PATH}')
    print('Stop server: CTRL+C\n')
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nServer stopped.')
    finally: server.server_close()

if __name__ == '__main__': main()
