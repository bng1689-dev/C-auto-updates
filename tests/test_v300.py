#!/usr/bin/env python3
"""v3.0.0 — ทดสอบ backend: คำขออนุมัติอัปเดต · PASSCODE เลือกผู้ใช้ (throttle รายคน) ·
ตัวเก็บกวาดหลังอัปเดต (ไฟล์ขยะ + ความเชื่อมโยงข้อมูลสมาชิก) · สถานะออนไลน์"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v300_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA)
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "uploads")

from _app import APP, CHROME  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "backend"))

from backend import db, engine, server  # noqa: E402
import config  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


class FakeManifest:
    """แทน urllib.request.urlopen — คืน manifest ปลอมเวอร์ชัน 99.0.0"""
    def __init__(self, *a, **k):
        self.data = json.dumps({"version": "99.0.0", "url": "http://x/z.zip",
                                "sha256": "", "notes": "test"}).encode()

    def __enter__(self):
        return io.BytesIO(self.data)

    def __exit__(self, *a):
        return False


def main():
    server.app.config["TESTING"] = True
    admin = server.app.test_client()
    member = server.app.test_client()

    r = admin.post("/api/setup", json={"username": "admin1", "password": "secret9",
                                       "password2": "secret9", "display_name": "Admin"})
    check("สร้าง super admin", r.status_code == 200)
    r = admin.post("/api/admin/members", json={"username": "somchai", "password": "pass66",
                                               "display_name": "สมชาย", "role": "member"})
    check("สร้างสมาชิก", r.status_code == 200, r.get_data(as_text=True))
    r = member.post("/api/login", json={"username": "somchai", "password": "pass66"})
    check("สมาชิกล็อกอิน", r.status_code == 200)

    # ── v3.1.0: สิทธิ์อัปเดตติ๊กรายคน (แทน KEY + ระบบขออนุมัติ) ──
    server.urllib.request.urlopen = lambda *a, **k: FakeManifest()

    v = member.get("/api/version").get_json()
    check("สมาชิกไม่มีสิทธิ์ → ไม่แจ้งเตือน ไม่ให้กด",
          v["update_available"] and not v["can_apply"] and not v["notify"])
    r = member.post("/api/update/apply")
    check("ไม่มีสิทธิ์ → apply ถูกปฏิเสธ (403 need_grant)",
          r.status_code == 403 and r.get_json().get("need_grant") is True,
          r.get_data(as_text=True))

    members = admin.get("/api/admin/members").get_json()
    m_uid = next(u["id"] for u in members if u["username"] == "somchai")
    r = admin.put(f"/api/admin/members/{m_uid}",
                  json={"permissions": {"update_app": True}})
    check("แอดมินติ๊กสิทธิ์ 'อัปเดตโปรแกรม' ให้สมาชิก", r.status_code == 200,
          r.get_data(as_text=True))

    v = member.get("/api/version").get_json()
    check("ได้สิทธิ์แล้ว → แจ้งเตือน+กดได้", v["can_apply"] and v["notify"])
    r = member.post("/api/update/apply")
    check("ได้สิทธิ์แล้ว → ผ่านด่าน (ไปตายที่ zip ปลอม ไม่ใช่ 403)",
          r.status_code != 403, f"got {r.status_code}")

    v = admin.get("/api/version").get_json()
    check("แอดมิน can_apply เสมอ", v["can_apply"] and v["notify"])
    r = member.post("/api/update/request", json={"version": "99.0.0"})
    check("endpoint ขออนุมัติแบบเก่าถูกถอดแล้ว (404)", r.status_code == 404)
    r = admin.get("/api/update/requests")
    check("endpoint รายการคำขอแบบเก่าถูกถอดแล้ว (404)", r.status_code == 404)
    r = admin.get("/api/license/state")
    check("endpoint KEY ถูกถอดแล้ว (404)", r.status_code == 404)

    # ── PASSCODE เลือกผู้ใช้ + throttle รายคน ──
    r = admin.post("/api/auth/passcode/set",
                   json={"password": "secret9", "passcode": "24681357", "passcode2": "24681357"})
    check("แอดมินตั้ง PASSCODE", r.status_code == 200, r.get_data(as_text=True))
    r = member.post("/api/auth/passcode/set",
                    json={"password": "pass66", "passcode": "13572468", "passcode2": "13572468"})
    check("สมาชิกตั้ง PASSCODE", r.status_code == 200)

    fresh = server.app.test_client()
    d = fresh.get("/api/auth/users").get_json()
    check("รายชื่อผู้ใช้ที่มี PASSCODE ครบ 2 คน", len(d["users"]) == 2)
    check("ไม่หลุด username/บทบาท", all(set(u) == {"id", "name", "locked_seconds"}
                                        for u in d["users"]))
    uid_admin = d["users"][0]["id"]
    uid_member = d["users"][1]["id"]

    r = fresh.post("/api/auth/passcode", json={"user_id": uid_member, "passcode": "13572468"})
    check("เลือก user แล้วใส่ PASSCODE ของคนนั้น → เข้าได้", r.status_code == 200)
    me = fresh.get("/api/me").get_json()
    check("ได้ session ของคนที่เลือกจริง", me.get("username") == "somchai")
    fresh.post("/api/logout")

    r = fresh.post("/api/auth/passcode", json={"user_id": uid_member, "passcode": "24681357"})
    check("ใช้ PASSCODE ของคนอื่นไม่เข้า", r.status_code == 401)
    for _ in range(4):
        fresh.post("/api/auth/passcode", json={"user_id": uid_member, "passcode": "00000009"})
    r = fresh.post("/api/auth/passcode", json={"user_id": uid_member, "passcode": "13572468"})
    check("เดาผิดหลายครั้ง → คนนั้นถูกล็อก", r.status_code == 429)
    r = fresh.post("/api/auth/passcode", json={"user_id": uid_admin, "passcode": "24681357"})
    check("ล็อกรายคน — คนอื่นยังปลดล็อกได้ปกติ", r.status_code == 200,
          r.get_data(as_text=True))
    fresh.post("/api/logout")

    # ── สถานะออนไลน์ ──
    rows = admin.get("/api/admin/members").get_json()
    by = {u["username"]: u for u in rows}
    check("แอดมิน (เพิ่งใช้งาน) ขึ้นออนไลน์", by["admin1"]["online"] is True)
    check("แถวสมาชิกมี last_seen ให้แสดง", "last_seen" in by["somchai"])

    # ── ตัวเก็บกวาดหลังอัปเดต ──
    pyc = APP / "backend" / "__pycache__"
    pyc.mkdir(exist_ok=True)
    (pyc / "junk.pyc").write_bytes(b"x")
    for i in range(5):
        (config.DATA_DIR / f"data.backup-2026010{i}-000000.db").write_bytes(b"bk")
    old_up = config.UPLOAD_DIR / "1"
    old_up.mkdir(parents=True, exist_ok=True)
    orphan = old_up / "orphan.xlsx"
    orphan.write_bytes(b"zz")
    os.utime(orphan, (time.time() - 8 * 86400, time.time() - 8 * 86400))
    keep = old_up / "in_queue.xlsx"
    keep.write_bytes(b"zz")
    os.utime(keep, (time.time() - 8 * 86400, time.time() - 8 * 86400))
    engine.save_queue([{"id": "k1", "path": str(keep), "user_id": 1}])
    with db.get_conn() as c:   # แถวทีมกำพร้า (อ้างทีม/สมาชิกที่ไม่มีจริง)
        c.execute("INSERT INTO team_members(team_id,user_id) VALUES(999,999)")

    db.set_meta("maint_version", "")   # บังคับให้ถือว่าเพิ่งอัปเดตเวอร์ชัน
    server._post_update_maintenance()

    check("ลบ __pycache__ แล้ว", not pyc.exists())
    baks = sorted(config.DATA_DIR.glob("data.backup-*.db"))
    check("สำรองฐานข้อมูลเหลือ 3 ชุดล่าสุด", len(baks) == 3, str(baks))
    check("ไฟล์อัปโหลดกำพร้าเก่าถูกลบ", not orphan.exists())
    check("ไฟล์ที่ยังอยู่ในคิวไม่ถูกแตะ", keep.exists())
    with db.get_conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM team_members WHERE team_id=999").fetchone()["n"]
    check("แถวทีมกำพร้าถูกล้าง", n == 0)
    check("จดเวอร์ชันที่เก็บกวาดแล้ว", db.get_meta("maint_version") == config.APP_VERSION)
    before = db.get_meta("maint_version")
    server._post_update_maintenance()   # รันซ้ำเวอร์ชันเดิม = ไม่ทำอะไร
    check("ไม่เก็บกวาดซ้ำถ้าเวอร์ชันไม่เปลี่ยน", db.get_meta("maint_version") == before)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
