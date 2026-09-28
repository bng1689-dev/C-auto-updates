#!/usr/bin/env python3
"""v3.2.0 — backend: กองกลาง=สมุดบันทึกล้วน · กราฟทีมเห็นเฉพาะทีมตัวเอง · เวอร์ชันรายคน ·
รหัสเชื่อมต่อ (สร้าง/แปลง/สมัครพร้อมเชื่อม) · payload presence ตาม whitelist · hook ไม่ยิงเน็ตเมื่อปิด"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v320_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA)
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "uploads")
from _app import APP, CHROME  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)
sys.path.insert(0, str(APP)); sys.path.insert(0, str(APP / "backend"))
from backend import db, hub, server  # noqa: E402
import config  # noqa: E402

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✓ {name}")
    else: FAIL += 1; print(f"  ✗ {name} {detail}")

def seed(uid, n, days_ago=0):
    ts = datetime.now() - timedelta(days=days_ago)
    with db.get_conn() as c:
        for i in range(n):
            c.execute("INSERT INTO searches(ts,ym,account,file,row,national_id,outcome,case_count,detail,user_id,id_hash,incomplete,attempt) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (ts.isoformat(timespec="seconds"), ts.strftime("%Y-%m"), "a", "s.xlsx", i+2, "x", "notfound", 0, "", uid, f"u{uid}d{days_ago}i{i}", 0, 1))

def main():
    server.app.config["TESTING"] = True
    sent = []
    server.hub._post = lambda url, payload, token: (sent.append(payload), {"ok": True})[1]   # ไม่ยิงเน็ตจริง

    admin = server.app.test_client(); m1 = server.app.test_client(); m2 = server.app.test_client()
    # ── สมัครพร้อมรหัสเชื่อมต่อ ──
    code = hub.make_connect_code("https://script.google.com/macros/s/abc/exec", "secret-token-123")
    check("รหัสเชื่อมต่อขึ้นต้น CRIMES-HUB:", code.startswith("CRIMES-HUB:"))
    check("แปลงกลับได้ url+token", hub.parse_connect_code(code) == ("https://script.google.com/macros/s/abc/exec", "secret-token-123"))
    check("รหัสเพี้ยน → None", hub.parse_connect_code("CRIMES-HUB:zzz") is None and hub.parse_connect_code("hello") is None)
    check("http:// ไม่รับ", hub.parse_connect_code(hub.make_connect_code("http://x/exec", "t")) is None)
    check("https ที่ไม่ใช่ Apps Script ไม่รับ (รหัสปลอมพาข้อมูลไปที่อื่นไม่ได้)",
          hub.parse_connect_code(hub.make_connect_code("https://evil.example.com/exec", "t")) is None)
    import base64 as _b
    bad = "CRIMES-HUB:" + _b.urlsafe_b64encode(b'["not","a","dict"]').decode().rstrip("=")
    check("JSON ที่ไม่ใช่ object → None ไม่ crash", hub.parse_connect_code(bad) is None)
    check("รหัสยาวผิดปกติ → None", hub.parse_connect_code("CRIMES-HUB:" + "A" * 5000) is None)
    r = admin.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                       "display_name": "Admin", "hub_code": "CRIMES-HUB:broken"})
    check("รหัสเชื่อมต่อผิด → สมัครไม่ผ่าน (400) ไม่สร้างบัญชีค้าง", r.status_code == 400 and not db.list_users())
    r = admin.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                       "display_name": "Admin", "hub_code": code})
    check("สมัครพร้อมรหัสเชื่อมต่อ → ok + hub_connected", r.status_code == 200 and r.get_json().get("hub_connected") is True)
    cfg = server.auth.load_config()
    check("config ถูกตั้ง: url/token/enabled/1 นาที", cfg.get("hub_url", "").endswith("/exec") and cfg.get("hub_token") == "secret-token-123"
          and cfg.get("hub_enabled") is True and int(cfg.get("hub_interval_min")) == 1)
    import time; time.sleep(0.4)
    check("ส่งสถานะ (presence) ทันทีหลังสมัคร", any(p.get("kind") == "presence" for p in sent), str([p.get("kind") for p in sent]))
    pres = next(p for p in sent if p.get("kind") == "presence")
    check("ก้อน presence ไม่มี rows (ศูนย์กลางจะไม่ลบตัวเลข)", "rows" not in pres)
    check("presence มีเฉพาะฟิลด์ที่อนุญาต", all(set(u) == set(hub.PRESENCE_FIELDS) for u in pres["users"]) and pres["users"])
    check("ไม่มี username/รหัสผ่านในก้อนที่ส่ง", "admin1" not in json.dumps(pres, ensure_ascii=False) and "secret9" not in json.dumps(pres))
    # สมาชิกที่ไม่ตั้งชื่อที่แสดง → ต้องไม่ถอยไปส่ง username
    admin.post("/api/admin/members", json={"username": "noname_user", "password": "pass66", "display_name": "", "role": "member"})
    pr = hub.collect_presence(); rows_now = hub.collect_rows(datetime.now().strftime("%Y-%m"))
    blob = json.dumps(pr, ensure_ascii=False) + json.dumps(rows_now, ensure_ascii=False)
    check("ไม่มีชื่อที่แสดง → ส่ง 'ผู้ใช้ #id' ไม่ใช่ชื่อล็อกอิน", "noname_user" not in blob and any(u["display_name"].startswith("ผู้ใช้ #") for u in pr))

    st = admin.get("/api/hub/state").get_json()
    check("hub/state บอก connected", st.get("connected") is True)
    r = admin.get("/api/hub/code")
    check("ออกรหัสเชื่อมต่อจากเครื่องแอดมินได้ (ตรงกับที่ใส่)", r.status_code == 200 and hub.parse_connect_code(r.get_json()["code"]) == hub.parse_connect_code(code))

    # ── สมาชิก + ทีม + เวอร์ชัน ──
    admin.post("/api/admin/members", json={"username": "somchai", "password": "pass66", "display_name": "สมชาย", "role": "member"})
    admin.post("/api/admin/members", json={"username": "wichai", "password": "pass66", "display_name": "วิชัย", "role": "member"})
    m1.post("/api/login", json={"username": "somchai", "password": "pass66"})
    m2.post("/api/login", json={"username": "wichai", "password": "pass66"})
    users = {u["username"]: u["id"] for u in db.list_users()}
    r = m1.get("/api/me")
    rows = {u["username"]: u for u in admin.get("/api/admin/members").get_json()}
    check("ตารางสมาชิกบอกเวอร์ชันที่แต่ละคนใช้", rows["somchai"].get("app_version") == config.APP_VERSION and rows["admin1"].get("app_version") == config.APP_VERSION)
    # v3.3.0: ด่านสิทธิ์ย้ายไปตรวจหลังอ่าน manifest (ต้องรู้ก่อนว่ารุ่นนั้นประกาศ open ไหม)
    # จึงต้องมี manifest ให้อ่านก่อน ถึงจะทดสอบด่านสิทธิ์ได้จริง
    import io as _io
    _mf = json.dumps({"version": "99.0.0", "url": "http://x/z.zip", "sha256": ""}).encode()

    class _FakeMF:
        def __enter__(self):
            return _io.BytesIO(_mf)

        def __exit__(self, *a):
            return False

    _orig_open = server.urllib.request.urlopen
    server.urllib.request.urlopen = lambda *a, **k: _FakeMF()
    r = m2.post("/api/update/apply")
    check("สมาชิกยังไม่ได้สิทธิ์อัปเดต → 403", r.status_code == 403
          and r.get_json().get("need_grant") is True, r.get_data(as_text=True)[:120])
    server.urllib.request.urlopen = _orig_open

    admin.post("/api/admin/teams", json={"name": "ทีม A", "member_ids": [users["admin1"], users["somchai"]]})
    admin.post("/api/admin/teams", json={"name": "ทีม B", "member_ids": [users["wichai"]]})
    seed(users["admin1"], 4); seed(users["somchai"], 2, 1); seed(users["wichai"], 9)
    mb = m1.get("/api/my/billing").get_json()
    check("สมาชิกเห็นเฉพาะทีมตัวเอง (ไม่เห็นทีม B)", [t["name"] for t in mb["teams"]] == ["ทีม A"], str([t["name"] for t in mb["teams"]]))
    check("ทีมมีข้อมูลกราฟรายวัน (daily) รวมทั้งทีม", len(mb["teams"][0].get("daily", [])) == 2 and sum(d["count"] for d in mb["teams"][0]["daily"]) == 6, str(mb["teams"][0].get("daily")))
    mb2 = m2.get("/api/my/billing").get_json()
    check("คนทีม B เห็นเฉพาะทีม B", [t["name"] for t in mb2["teams"]] == ["ทีม B"])

    # ── กองกลาง = สมุดบันทึกเท่านั้น ──
    before = len(sent)
    r = admin.post("/api/admin/ledger", json={"user_id": users["somchai"], "kind": "in", "amount": 250, "note": "x"})
    check("บันทึกรับ", r.status_code == 200)
    admin.post("/api/admin/ledger", json={"user_id": users["wichai"], "kind": "out", "amount": 40})
    time.sleep(0.4)
    check("บันทึกรับ/จ่าย → ส่งตัวเลขขึ้นศูนย์กลางทันที", any(p.get("kind") == "counts" for p in sent[before:]), str([p.get("kind") for p in sent[before:]]))
    cnt = next(p for p in sent[before:] if p.get("kind") == "counts")
    check("ก้อน counts มี users (สถานะ) มาด้วย และ rows ตาม whitelist", isinstance(cnt.get("users"), list) and all(set(r) == set(hub.ALLOWED_FIELDS) for r in cnt["rows"]))
    a = admin.get("/api/live/board").get_json()
    check("กองกลาง: ยอด = สมุดบันทึกล้วน (รับ 250 จ่าย 40 สุทธิ 210 · 2 รายการ) ไม่รวมผลค้น",
          a["totals"] == {"in": 250.0, "out": 40.0, "net": 210.0, "entries": 2}, str(a["totals"]))
    check("กราฟกองกลางรายวันจากสมุดบันทึก", a["daily"] and set(a["daily"][0]) == {"d", "in", "out"})
    b = m2.get("/api/live/board").get_json()
    check("v3.9.0: wichai (ทีม B คนเดียว) เห็นเฉพาะของตัวเอง — จ่าย 40 · 1 รายการ",
          b["totals"] == {"in": 0.0, "out": 40.0, "net": -40.0, "entries": 1} and b["scope"] == "team", str(b["totals"]))
    b1 = m1.get("/api/live/board").get_json()
    check("v3.9.0: somchai (ทีม A กับ admin1) เห็นของทีม — รับ 250 · 1 รายการ (ไม่เห็นของ wichai)",
          b1["totals"] == {"in": 250.0, "out": 0.0, "net": 250.0, "entries": 1}, str(b1["totals"]))
    check("รายคนในกองกลางมีเฉพาะคนที่มีรายการ (2 คน) และไม่มีคอลัมน์ผลค้น",
          len(a["rows"]) == 2 and all("count" not in r and "earned" not in r for r in a["rows"]))

    # ── รอบค้นจบ → ส่งทันที (จำลองผ่าน /api/status) ──
    before = len(sent)
    states = iter(["running", "running", "done", "done"])
    server.manager.status = lambda: {"state": next(states), "log": []}
    server._hub_kick_last["counts"] = 0.0
    for _ in range(4): admin.get("/api/status")
    time.sleep(0.4)
    check("รอบค้นจบ (running→done) → ส่งตัวเลขทันที ครั้งเดียว", sum(1 for p in sent[before:] if p.get("kind") == "counts") == 1, str([p.get("kind") for p in sent[before:]]))

    # ── ปิดศูนย์กลาง → hook ต้องเงียบ ──
    server.auth.update_config(hub_enabled=False)
    before = len(sent); server._hub_kick_last = {"presence": 0.0, "counts": 0.0}
    m1.post("/api/logout"); m1.post("/api/login", json={"username": "somchai", "password": "pass66"})
    time.sleep(0.3)
    check("ปิดศูนย์กลางแล้ว hook ไม่ส่งอะไร", len(sent) == before)
    r = admin.get("/api/hub/presence").get_json()
    check("presence ตอนปิด → บอกว่ายังไม่ได้เปิดใช้", r.get("ok") is False and "ยังไม่ได้เปิดใช้" in r.get("error", ""))

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0

try: code = main()
finally: shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
