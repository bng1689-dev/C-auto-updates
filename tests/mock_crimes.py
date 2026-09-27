"""เว็บ CRIMES จำลอง (สำหรับทดสอบทั้งระบบแบบ end-to-end)

จำลองพฤติกรรมที่ engine ต้องรับมือจริง:
  • หน้าเข้าสู่ระบบ (มีช่องรหัสผ่าน) → เข้าสู่ระบบแล้วค่อยเด้งไปหน้าค้นหา
  • กล่อง 'มีอะไรใหม่' ครอบทั้งหน้า (หัวข้อบนสุด ปุ่ม 'เข้าใจแล้ว' ล่างสุด คนละกิ่ง)
  • หน้าค้นหาเป็น SPA URL เดิม — ผลของคนก่อนหน้าค้างบนหน้าจนกว่าคำตอบใหม่จะมา (หน่วงได้)
  • ป๊อบอัพระบุเหตุผล + ปุ่ม 'ยืนยันค้นหา' · ตาราง → หน้ารายละเอียด → 'ย้อนกลับ'
  • ฉีดความผิดพลาดได้: HTTP 500 ครั้งแรกของเลขที่กำหนด / ป๊อบอัพค้างครั้งแรก
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

STATE = {
    "logged_in": False,
    "announce": True,
    "delay": 0.0,              # หน่วงคำตอบการค้น (วินาที)
    "fail_http": {},           # pid -> จำนวนครั้งแรกที่ตอบ 500
    "stuck": [],               # pid ที่ป๊อบอัพยืนยันค้างครั้งแรก
    "cases": {},               # pid -> [ {charge, year, status, caseNo} ]
    "hits": {},                # pid -> จำนวนครั้งที่ถูกค้น
}
LOCK = threading.Lock()

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>CRIMES (mock)</title>
<style>
body{font-family:sans-serif;margin:0} .bar{padding:8px;background:#123;color:#fff}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:50}
.box{background:#fff;width:520px;padding:0;border-radius:8px}
.box .head{background:#1d4ed8;color:#fff;padding:14px}.box .body{padding:14px;height:120px}
.box .foot{padding:12px;text-align:right}
.color-yellow-hard{display:inline-block;background:#fc0;padding:8px 20px;cursor:pointer}
.popup{position:fixed;left:30%;top:30%;background:#fff;border:2px solid #333;padding:16px;z-index:40}
table{border-collapse:collapse} td,th{border:1px solid #999;padding:4px}
</style></head><body>
<div class="bar">ระบบสืบค้น (จำลอง) · <span id="who"></span></div>
<div id="app"></div>
<script>
const S = {results:null, count:null, pid:"", cfg:{stuck:[]}, stuckUsed:{}, detail:null};
async function cfg(){ try{ S.cfg = await (await fetch('/api/config')).json(); }catch(e){} }
function esc(s){return (s??'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
async function session(){ try{ return (await (await fetch('/api/session')).json()).logged_in; }catch(e){ return false; } }
function renderLogin(){
  document.getElementById('who').textContent='';
  app.innerHTML = '<h3>เข้าสู่ระบบ</h3><input placeholder="ชื่อผู้ใช้"> <input type="password" placeholder="รหัสผ่าน"> <button>เข้าสู่ระบบ</button>';
}
function renderCriteria(){
  document.getElementById('who').textContent='ชื่อ : ร.ต.อ.ทดสอบ ระบบ';
  let h = '<div><input id="inputPid" placeholder="เลขบัตรประชาชน" maxlength="13"></div>'
    + '<div><nb-checkbox><label><input type="checkbox" checked> <span>คดีจราจร</span></label></nb-checkbox> '
    + '<nb-checkbox><label><input type="checkbox"> <span>คดีอาญา</span></label></nb-checkbox></div>'
    + '<div class="color-yellow-hard" id="btnSearch">ค้นหา</div><div id="res"></div><div id="pop"></div>';
  app.innerHTML = h;
  document.getElementById('btnSearch').onclick = openPopup;
  renderResults();
  if(S.cfg.announce && !localStorage.getItem('ann215') && !document.getElementById('ann')) renderAnnounce();
}
function renderAnnounce(){
  const d = document.createElement('div'); d.className='overlay'; d.id='ann';
  d.innerHTML = '<div class="box"><div class="head"><b>มีอะไรใหม่</b> <span>เวอร์ชัน 2.1.5</span><button class="close" aria-label="close">✕</button></div>'
    + '<div class="body">ปรับปรุงหน้าค้นหา ...</div><div class="foot"><button id="annOk">เข้าใจแล้ว</button></div></div>';
  document.body.appendChild(d);
  d.querySelector('#annOk').onclick = ()=>{ localStorage.setItem('ann215','1'); d.remove(); };
  d.querySelector('.close').onclick = ()=>{ d.remove(); };
}
function renderResults(){
  const el = document.getElementById('res'); if(!el) return;
  if(S.count===null){ el.innerHTML=''; return; }
  let h = '<div>คดีอาญา ('+S.count+' รายการ)</div>';
  if(S.results && S.results.length){
    h += '<table><tr><th>เลขบัตร</th><th>ชื่อ</th><th>เพศ</th><th>อายุ</th><th>เลขคดี</th><th>สถานะ</th><th>สถานี</th></tr>';
    S.results.forEach((c,i)=>{ h += '<tr><td><label data-i="'+i+'">'+esc(S.pid)+'</label></td><td>นาย ก</td><td>ช</td><td>30</td><td>'+esc(c.caseNo)+'</td><td>'+esc(c.status)+'</td><td>สภ.จำลอง</td></tr>'; });
    h += '</table>';
  }
  el.innerHTML = h;
  el.querySelectorAll('label[data-i]').forEach(l=>l.onclick=()=>{ S.detail=+l.dataset.i; location.hash='#/bda/search/detail'; });
}
function openPopup(){
  const pid = document.getElementById('inputPid').value.trim();
  const pop = document.getElementById('pop');
  pop.innerHTML = '<div class="popup">โปรดระบุเหตุผลที่สืบค้นข้อมูล<br>'
    + '<nb-checkbox><label><input type="checkbox" id="rchk"> <span>ตรวจสอบทั่วไป</span></label></nb-checkbox><br>'
    + '<input placeholder="ระบุเหตุผล..." id="rtxt"><br><button id="rok">ยืนยันค้นหา</button></div>';
  document.getElementById('rok').onclick = ()=>confirmSearch(pid);
}
async function confirmSearch(pid){
  if(!document.getElementById('rchk').checked || !document.getElementById('rtxt').value) return;
  if((S.cfg.stuck||[]).includes(pid) && !S.stuckUsed[pid]){ S.stuckUsed[pid]=1; return; }  // ป๊อบอัพค้าง
  document.getElementById('pop').innerHTML='';
  let r;
  try{ r = await fetch('/api/search?pid='+encodeURIComponent(pid)); }catch(e){ return; }
  if(!r.ok){ return; }                       // เว็บตอบผิดพลาด: ผลเก่ายังค้างบนหน้า
  const d = await r.json();
  S.pid = pid; S.results = d.cases; S.count = d.cases.length;
  renderResults();
}
function renderDetail(){
  const c = (S.results||[])[S.detail]||{};
  const vals = [c.caseNo, 'สภ.จำลอง', 'x', c.year||'', c.charge||'', 'นาย ก', S.pid, c.status];
  app.innerHTML = vals.map(v=>'<input type="text" value="'+esc(v)+'">').join('<br>')
    + '<br><button id="back">ย้อนกลับ</button>';
  document.getElementById('back').onclick = ()=>{ location.hash='#/bda/search/criteria/person'; };
}
async function route(){
  const h = location.hash;
  if(h.includes('login')){
    renderLogin();
    const t = setInterval(async()=>{ if(await session()){ clearInterval(t); location.hash='#/bda/search/criteria/person'; } }, 400);
    return;
  }
  if(!(await session())){ location.hash = '#/login'; return; }
  if(h.includes('detail')) renderDetail(); else renderCriteria();
}
window.addEventListener('hashchange', route);
cfg().then(route);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith("/bdasearch"):
            b = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if u.path == "/api/session":
            return self._json({"logged_in": STATE["logged_in"]})
        if u.path == "/api/config":
            return self._json({"announce": STATE["announce"], "stuck": STATE["stuck"]})
        if u.path == "/api/search":
            pid = (q.get("pid") or [""])[0]
            with LOCK:
                STATE["hits"][pid] = STATE["hits"].get(pid, 0) + 1
                n = STATE["fail_http"].get(pid, 0)
                if n > 0:
                    STATE["fail_http"][pid] = n - 1
                    fail = True
                else:
                    fail = False
            if STATE["delay"]:
                time.sleep(STATE["delay"])
            if fail:
                return self._json({"error": "server"}, 500)
            return self._json({"cases": STATE["cases"].get(pid, [])})
        self.send_response(404)
        self.end_headers()


def serve(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
