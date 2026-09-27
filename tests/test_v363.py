#!/usr/bin/env python3
"""v3.6.3 — กู้รหัสผ่าน Super Admin ด้วยไฟล์บนเครื่อง (ไม่เปิดเบราว์เซอร์)

ผู้ใช้รายงาน "Super Admin รหัสผิด" หลังอัปเดต — เดิมโปรแกรมไม่มีทางกู้รหัส Super Admin เลย
(ผู้ได้รับมอบสิทธิ์จัดการสมาชิกรีเซ็ตรหัสของผู้มีสิทธิ์พิเศษไม่ได้ · ทางเดียวคือลบ data.db)
  • /api/auth/recovery: ไม่มีไฟล์ → ready=False ไม่ส่งรายชื่อ · มีไฟล์ → ready=True + รายชื่อ Super Admin
  • /api/auth/recovery/reset: ไม่มีไฟล์ → 403 · ชื่อไม่ใช่ Super Admin → 400 · รหัสสั้น/ไม่ตรง → 400 (ไฟล์ยังอยู่)
    · สำเร็จ → ตั้งรหัสใหม่ · ลบไฟล์ · เข้าสู่ระบบให้เลย · เพิกถอน PASSCODE · ล้างล็อกกรอกผิด · เปิดบัญชีที่ถูกปิด
  • เปิดจากเครื่องอื่น (Host/REMOTE_ADDR ไม่ใช่เครื่องนี้) → 403 ทั้งสอง endpoint
  • หน้าจอ: กล่องกู้รหัส + ลิงก์ 'ลืมรหัสผ่าน' + คำอธิบายใต้ช่อง PASSCODE ว่าไม่ใช่รหัสผ่าน
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v363_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "data")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
from _app import APP  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)

from backend import server  # noqa: E402
import db  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def main():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    RF = server.RECOVERY_FILE
    c.post("/api/setup", json={"username": "admin1", "password": "secret9",
                               "password2": "secret9", "display_name": "Admin"})
    c.post("/api/admin/members", json={"username": "member9", "password": "pass66",
                                       "display_name": "สมาชิก", "role": "member"})
    c.post("/api/auth/passcode/set", json={"password": "secret9", "passcode": "24681357", "passcode2": "24681357"})
    c.post("/api/logout")

    print("── ยังไม่มีไฟล์กู้ ──")
    j = c.get("/api/auth/recovery").get_json()
    check("ไม่มีไฟล์ → ready=False และไม่ส่งรายชื่อบัญชี", j["ready"] is False and j["admins"] == [], str(j))
    check("บอกตำแหน่งไฟล์ที่ต้องสร้าง", j["file"].endswith("reset-superadmin.txt") and str(TEST_DATA) in j["file"], j["file"])
    r = c.post("/api/auth/recovery/reset", json={"username": "admin1", "password": "newpass1", "password2": "newpass1"})
    check("ไม่มีไฟล์ → รีเซ็ตไม่ได้ (403)", r.status_code == 403 and "reset-superadmin.txt" in r.get_json()["error"], str(r.get_json()))
    check("รหัสเดิมยังใช้ได้อยู่", c.post("/api/login", json={"username": "admin1", "password": "secret9"}).status_code == 200)
    c.post("/api/logout")

    print("\n── มีไฟล์กู้ ──")
    # ล็อกจากการกรอกผิดหลายครั้ง (เหมือนผู้ใช้ลองรหัสซ้ำ ๆ) — การกู้ต้องล้างให้
    for _ in range(db.AUTH_FAIL_GRACE + 2):
        c.post("/api/login", json={"username": "admin1", "password": "wrong"})
    check("(เตรียม) บัญชีถูกล็อกจากการกรอกผิด", db.auth_lock_remaining("login:admin1") > 0)
    RF.write_text("", encoding="utf-8")
    j = c.get("/api/auth/recovery").get_json()
    check("มีไฟล์ → ready=True และรายชื่อมีเฉพาะ Super Admin", j["ready"] is True and j["admins"] == ["admin1"], str(j))
    r = c.post("/api/auth/recovery/reset", json={"username": "member9", "password": "newpass1", "password2": "newpass1"})
    check("ชื่อสมาชิกธรรมดา → 400", r.status_code == 400 and "Super Admin" in r.get_json()["error"], str(r.get_json()))
    r = c.post("/api/auth/recovery/reset", json={"username": "admin1", "password": "new", "password2": "new"})
    check("รหัสสั้นเกิน → 400", r.status_code == 400)
    r = c.post("/api/auth/recovery/reset", json={"username": "admin1", "password": "newpass1", "password2": "newpass2"})
    check("สองช่องไม่ตรง → 400", r.status_code == 400 and "ไม่ตรงกัน" in r.get_json()["error"])
    check("ไฟล์ยังอยู่หลังคำขอที่ไม่ผ่าน", RF.exists())

    print("\n── เปิดจากเครื่องอื่น ──")
    r = c.get("/api/auth/recovery", headers={"Host": "192.168.1.9:8770"})
    check("Host ไม่ใช่เครื่องนี้ → 403", r.status_code == 403, str(r.status_code))
    r = c.post("/api/auth/recovery/reset", json={"username": "admin1", "password": "newpass1", "password2": "newpass1"},
               environ_base={"REMOTE_ADDR": "192.168.1.9"})
    check("REMOTE_ADDR ไม่ใช่เครื่องนี้ → 403 และไฟล์ยังอยู่", r.status_code == 403 and RF.exists(), str(r.status_code))

    print("\n── กู้สำเร็จ ──")
    r = c.post("/api/auth/recovery/reset", json={"username": "admin1", "password": "newpass1", "password2": "newpass1"})
    j = r.get_json()
    check("ตั้งรหัสใหม่สำเร็จ", r.status_code == 200 and j.get("ok") is True and j.get("username") == "admin1", str(j))
    check("ไฟล์กู้ถูกลบทันที", not RF.exists())
    me = c.get("/api/me")
    check("เข้าสู่ระบบให้เลยด้วยบัญชีนั้น", me.status_code == 200 and me.get_json()["username"] == "admin1")
    check("PASSCODE ของบัญชีถูกเพิกถอน", db.has_passcode(1) is False)
    check("ล็อกจากการกรอกผิดถูกล้าง", db.auth_lock_remaining("login:admin1") == 0)
    c.post("/api/logout")
    check("รหัสเดิมใช้ไม่ได้แล้ว", c.post("/api/login", json={"username": "admin1", "password": "secret9"}).status_code == 401)
    check("รหัสใหม่ใช้ได้", c.post("/api/login", json={"username": "admin1", "password": "newpass1"}).status_code == 200)
    c.post("/api/logout")
    check("ไม่มีไฟล์แล้ว → รีเซ็ตซ้ำไม่ได้", c.post("/api/auth/recovery/reset", json={
        "username": "admin1", "password": "x123456", "password2": "x123456"}).status_code == 403)

    print("\n── บัญชีที่ถูกปิดใช้งาน ──")
    with db.get_conn() as conn:
        conn.execute("UPDATE users SET active=0 WHERE id=1")
    check("(เตรียม) บัญชีถูกปิด → เข้าไม่ได้", c.post("/api/login", json={"username": "admin1", "password": "newpass1"}).status_code == 401)
    RF.write_text("", encoding="utf-8")
    r = c.post("/api/auth/recovery/reset", json={"username": "admin1", "password": "newpass2", "password2": "newpass2"})
    check("กู้แล้วบัญชีถูกเปิดใช้งานกลับ", r.status_code == 200 and db.get_user(1)["active"] == 1, str(r.get_json()))
    c.post("/api/logout")
    check("เข้าด้วยรหัสใหม่ได้", c.post("/api/login", json={"username": "admin1", "password": "newpass2"}).status_code == 200)

    print("\n── หน้าจอ ──")
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("มีกล่องกู้รหัสและลิงก์ 'ลืมรหัสผ่าน Super Admin?'",
          all(k in html for k in ('id="authRecoverBox"', 'id="authForgotLink"', 'id="authRecoverForm"',
                                  "ลืมรหัสผ่าน Super Admin?", "reset-superadmin.txt", "function checkRecovery")))
    check("ใต้ช่อง PASSCODE บอกว่าไม่ใช่รหัสผ่าน", "ไม่ใช่รหัสผ่าน" in html and "🔑 รหัสผ่าน" in html)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
