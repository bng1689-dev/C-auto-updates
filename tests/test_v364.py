#!/usr/bin/env python3
"""v3.6.4 — ลืมรหัสผ่าน (สมาชิก) ยืนยันตัวตนด้วยชื่อที่ใช้เข้าเว็บ CRIMES · ยกเลิกทางกู้รหัส Super Admin (ไม่เปิดเบราว์เซอร์)

ผู้ใช้สั่ง: "ยกเลิกลืมรหัส Superadmin แต่ให้สมาชิกกดลืมรหัสได้ ยืนยันความถูกต้องดูชื่อที่ใช้ login CRIMES
ถ้าตรงกัน อนุญาตให้รีเซ็ตรหัสเข้าใหม่ได้"
  • /api/auth/forgot: ชื่อ CRIMES ตรงกับที่จดไว้จากรอบค้น (runs/searches ของคนนั้น ไม่สนตัวพิมพ์/ช่องว่าง) → ตั้งรหัสใหม่
    · เข้าสู่ระบบให้เลย · PASSCODE ถูกเพิกถอน · ล็อกกรอกผิดถูกล้าง
  • ไม่ผ่าน: ชื่อ CRIMES ไม่ตรง / ไม่มีบัญชี / Super Admin / บัญชีถูกปิด → 401 ข้อความกลาง ๆ + นับเป็นกรอกผิด (ล็อกได้)
    · ยังไม่เคยค้น → 400 บอกให้ Super Admin ตั้งให้ · รหัสสั้น/ไม่ตรง → 400 · เปิดจากเครื่องอื่น → 403
  • ทางกู้ Super Admin ด้วยไฟล์ (v3.6.3) ถูกถอดออกหมด: endpoint 404 · ไม่มีฟังก์ชัน/ข้อความในหน้าจอ
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v364_"))
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


def forgot(c, username, crimes, pw="newpass9", pw2=None, **kw):
    r = c.post("/api/auth/forgot", json={"username": username, "crimes_account": crimes,
                                         "password": pw, "password2": pw if pw2 is None else pw2}, **kw)
    return r.status_code, (r.get_json() or {})


def main():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    c.post("/api/setup", json={"username": "admin1", "password": "secret9",
                               "password2": "secret9", "display_name": "Admin"})
    for u, n in (("member9", "สมชาย"), ("member8", "สมหญิง"), ("member7", "สมศรี")):
        c.post("/api/admin/members", json={"username": u, "password": "pass66", "display_name": n, "role": "member"})
    users = {u["username"]: u for u in db.list_users()}
    m9, m8, m7 = users["member9"]["id"], users["member8"]["id"], users["member7"]["id"]
    # โปรแกรมจดชื่อบัญชี CRIMES ของแต่ละคนจากรอบค้น (runs) และผลค้น (searches) — member8 ไม่เคยค้น
    db.start_run("Somchai.C", 1, user_id=m9)
    with db.get_conn() as conn:
        conn.execute("INSERT INTO searches(ts,ym,account,file,row,national_id,outcome,case_count,detail,user_id,"
                     "id_hash,incomplete,attempt) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (datetime.now().isoformat(timespec="seconds"), datetime.now().strftime("%Y-%m"),
                      "somchai.alt", "a.xlsx", 2, "1-23xx-xxxxx-xx-1", "found", 1, "", m9, "h1", 0, 1))
        conn.execute("INSERT INTO searches(ts,ym,account,file,row,national_id,outcome,case_count,detail,user_id,"
                     "id_hash,incomplete,attempt) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (datetime.now().isoformat(timespec="seconds"), datetime.now().strftime("%Y-%m"),
                      "somsri.x", "b.xlsx", 2, "1-23xx-xxxxx-xx-2", "notfound", 0, "", m7, "h2", 0, 1))
    db.start_run("AdminCrimes", 1, user_id=1)
    # member9 ตั้ง PASSCODE ไว้ — ตั้งรหัสใหม่ต้องเพิกถอน
    mc = server.app.test_client()
    mc.post("/api/login", json={"username": "member9", "password": "pass66"})
    mc.post("/api/auth/passcode/set", json={"password": "pass66", "passcode": "24681357", "passcode2": "24681357"})
    mc.post("/api/logout")
    c.post("/api/logout")

    print("── ชื่อบัญชี CRIMES ที่จดไว้ ──")
    check("รวมจากรอบค้นและผลค้น ไม่ซ้ำ", db.crimes_accounts_for_user(m9) == ["Somchai.C", "somchai.alt"],
          str(db.crimes_accounts_for_user(m9)))
    check("คนที่ไม่เคยค้น → ว่าง", db.crimes_accounts_for_user(m8) == [])

    print("\n── ไม่ผ่าน ──")
    st, j = forgot(c, "member9", "someone.else")
    check("ชื่อ CRIMES ไม่ตรง → 401 ข้อความกลาง ๆ", st == 401 and "ไม่ตรง" in j.get("error", ""), f"{st} {j}")
    check("รหัสเดิมยังใช้ได้", c.post("/api/login", json={"username": "member9", "password": "pass66"}).status_code == 200)
    c.post("/api/logout")
    st, j = forgot(c, "nobody", "Somchai.C")
    check("ไม่มีบัญชีนี้ → 401 ข้อความเดียวกัน (ไม่บอกว่าบัญชีมีไหม)", st == 401 and j.get("error") == server._FORGOT_FAIL, f"{st} {j}")
    st, j = forgot(c, "admin1", "AdminCrimes")
    check("Super Admin ใช้ทางนี้ไม่ได้ แม้ชื่อ CRIMES ตรง → 401", st == 401 and j.get("error") == server._FORGOT_FAIL, f"{st} {j}")
    check("รหัส Super Admin ไม่ถูกแตะ", c.post("/api/login", json={"username": "admin1", "password": "secret9"}).status_code == 200)
    c.post("/api/logout")
    st, j = forgot(c, "member8", "anything")
    check("สมาชิกที่ยังไม่เคยค้น → 400 บอกให้ Super Admin ตั้งให้", st == 400 and "Super Admin" in j.get("error", ""), f"{st} {j}")
    st, j = forgot(c, "member9", "Somchai.C", pw="abc")
    check("รหัสสั้นเกิน → 400", st == 400)
    st, j = forgot(c, "member9", "Somchai.C", pw="newpass9", pw2="newpass8")
    check("สองช่องไม่ตรง → 400", st == 400 and "ไม่ตรงกัน" in j.get("error", ""))
    st, j = forgot(c, "member9", "")
    check("ไม่กรอกชื่อ CRIMES → 400", st == 400)
    with db.get_conn() as conn:
        conn.execute("UPDATE users SET active=0 WHERE id=?", (m7,))
    st, j = forgot(c, "member7", "somsri.x")
    check("บัญชีที่ถูกปิด → 401 และไม่เปิดตัวเองกลับ", st == 401 and db.get_user(m7)["active"] == 0, f"{st} {j}")
    st, j = forgot(c, "member9", "Somchai.C", headers={"Host": "192.168.1.9:8770"})
    check("เปิดจากเครื่องอื่น (Host) → 403", st == 403, str(st))
    st, j = forgot(c, "member9", "Somchai.C", environ_base={"REMOTE_ADDR": "192.168.1.9"})
    check("เปิดจากเครื่องอื่น (REMOTE_ADDR) → 403", st == 403, str(st))

    print("\n── หน่วงการเดา ──")
    db.reset_auth_fails("forgot:member9")
    last = None
    for _ in range(db.AUTH_FAIL_GRACE + 1):
        last = forgot(c, "member9", "wrong.name")
    st, j = forgot(c, "member9", "Somchai.C")
    check("เดาผิดหลายครั้ง → ถูกล็อกแม้ครั้งถัดไปจะถูก (429)", st == 429 and j.get("locked_seconds", 0) > 0, f"{last} → {st} {j}")
    db.reset_auth_fails("forgot:member9")

    print("\n── ผ่าน ──")
    for _ in range(3):      # ล็อกจากการเดารหัสผ่านตอนล็อกอินก็ต้องถูกล้างเมื่อตั้งรหัสใหม่
        c.post("/api/login", json={"username": "member9", "password": "wrong"})
    st, j = forgot(c, "member9", "  SOMCHAI.c ")
    check("ชื่อ CRIMES ตรง (ไม่สนตัวพิมพ์/ช่องว่าง) → ตั้งรหัสใหม่สำเร็จ", st == 200 and j.get("ok") is True, f"{st} {j}")
    me = c.get("/api/me")
    check("เข้าสู่ระบบให้เลยเป็นสมาชิกคนนั้น", me.status_code == 200 and me.get_json()["username"] == "member9")
    check("PASSCODE ของบัญชีถูกเพิกถอน", db.has_passcode(m9) is False)
    check("ล็อกจากการเดารหัสตอนล็อกอินถูกล้าง", db.auth_lock_remaining("login:member9") == 0)
    c.post("/api/logout")
    check("รหัสเดิมใช้ไม่ได้แล้ว", c.post("/api/login", json={"username": "member9", "password": "pass66"}).status_code == 401)
    check("รหัสใหม่ใช้ได้", c.post("/api/login", json={"username": "member9", "password": "newpass9"}).status_code == 200)
    c.post("/api/logout")
    st, j = forgot(c, "member9", "somchai.alt", pw="another1")
    check("ชื่อ CRIMES อีกชื่อที่เคยใช้ก็ยืนยันได้", st == 200)
    c.post("/api/logout")
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) n FROM audit_log WHERE action IN ('forgot_password_reset','forgot_password_failed')").fetchone()["n"]
    check("มีรายการในบันทึกการตรวจสอบ", n >= 3, str(n))

    print("\n── ทางกู้ Super Admin (v3.6.3) ถูกถอดออกหมด ──")
    check("endpoint เดิมไม่มีแล้ว (404)", c.get("/api/auth/recovery").status_code == 404
          and c.post("/api/auth/recovery/reset", json={}).status_code == 404)
    check("ไม่มีฟังก์ชัน/ไฟล์กู้ในโค้ด", not hasattr(db, "recover_password") and not hasattr(server, "RECOVERY_FILE"))
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าจอไม่มีกล่องกู้ Super Admin แล้ว", "reset-superadmin" not in html and 'id="authRecoverBox"' not in html)

    print("\n── หน้าจอ ──")
    check("มีลิงก์ 'ลืมรหัสผ่าน?' + ฟอร์มยืนยันด้วยชื่อ CRIMES + ปุ่มกลับ",
          all(k in html for k in ('id="authForgotBox"', 'id="authForgotLink"', 'id="fgCrimes"', 'id="btnForgotBack"',
                                  "ชื่อที่ใช้เข้าเว็บ CRIMES", "function showForgot", "/api/auth/forgot")))
    check("ใต้ช่อง PASSCODE ยังบอกว่าไม่ใช่รหัสผ่าน", "ไม่ใช่รหัสผ่าน" in html and "🔑 รหัสผ่าน" in html)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
