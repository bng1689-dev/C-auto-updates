#!/usr/bin/env python3
"""v3.8.0 — ชุดติดตั้งตัวเต็ม: บัญชีเริ่มต้นจากไฟล์ seed (แฮชเท่านั้น) · ป้ายเตือนเปลี่ยนรหัส · ลบไฟล์ที่เลิกใช้ตอนอัปเดต

ผู้ใช้สั่ง: "ไม่ต้องสร้างรหัสแรก ให้ใช้ User/Pass ที่กำหนด โดยไม่ทิ้งร่องรอยรหัสในเอกสารของโปรเจค รหัสเปลี่ยนได้ภายหลัง
            · เคลียร์ไฟล์ที่ไม่จำเป็นอีกต่อไปทิ้ง"
  • seed_account.json (username + pbkdf2 hash + salt) → เปิดครั้งแรกที่ยังไม่มีผู้ใช้ = สร้าง Super Admin ให้ แล้วลบไฟล์ทันที
  • มีผู้ใช้อยู่แล้ว/ไฟล์เสีย → ไม่แตะฐานข้อมูล แต่ลบไฟล์เช่นกัน · แฮชไม่ถูกต้อง → ปฏิเสธ
  • /api/me บอก seed_password=true จนกว่าจะเปลี่ยนรหัส (ทางไหนก็ได้) · หน้าจอมีป้ายเตือน + ปุ่มไปเปลี่ยนรหัส
  • ตัวอัปเดตในโปรแกรมลบไฟล์ตาม app/OBSOLETE.txt (ไม่แตะ data/uploads · กัน ..) · licensekey.py อยู่ในรายการ
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v380_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "data")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
from _app import APP  # noqa: E402

from backend import server  # noqa: E402
import config  # noqa: E402
import db  # noqa: E402

PASS = FAIL = 0
SEED_PW = "test-seed-pw-not-real"       # รหัสทดสอบ — ไม่ใช่รหัสจริงของชุดติดตั้ง


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def seed_file(username="Superadmin", password=SEED_PW, **extra):
    salt = "ab" * 16
    data = {"username": username, "display_name": "Super Admin", "salt": salt,
            "password_hash": hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), db._ITERATIONS).hex()}
    data.update(extra)
    p = config.BASE_DIR / db.SEED_FILE_NAME
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def main():
    server.app.config["TESTING"] = True
    server._hub_kick = lambda *a, **k: None
    c = server.app.test_client()

    print("── seed ตอนยังไม่มีผู้ใช้ ──")
    p = seed_file()
    res = db.seed_first_user(p)
    u = db.get_user_by_username("Superadmin")
    check("สร้าง Super Admin จากไฟล์ seed", res.get("seeded") is True and u and u["role"] == "super_admin" and u["display_name"] == "Super Admin", str(res))
    check("ไฟล์ seed ถูกลบทันทีหลังใช้", not p.exists())
    check("ระบบถือว่าตั้งค่าแล้ว (ไม่ต้องสมัคร)", c.get("/api/auth/state").get_json().get("configured") is True)
    r = c.post("/api/login", json={"username": "Superadmin", "password": SEED_PW})
    check("เข้าด้วยรหัสเริ่มต้นได้", r.status_code == 200, r.get_data(as_text=True)[:120])
    me = c.get("/api/me").get_json()
    check("/api/me บอกว่ายังใช้รหัสเริ่มต้น (seed_password=true)", me.get("seed_password") is True and me.get("role") == "super_admin", str(me))
    check("มีรายการ audit seed_superadmin", any(a.get("action") == "seed_superadmin" for a in db.get_audit_log(50)))
    r = c.post("/api/password", json={"current": SEED_PW, "new": "my-own-pass9"})
    me2 = c.get("/api/me").get_json()
    check("เปลี่ยนรหัสแล้ว → seed_password=false (ป้ายเตือนหาย)", r.status_code == 200 and me2.get("seed_password") is False, str(me2))
    check("รหัสเริ่มต้นใช้ไม่ได้อีก · รหัสใหม่ใช้ได้", server.app.test_client().post("/api/login", json={"username": "Superadmin", "password": SEED_PW}).status_code == 401
          and server.app.test_client().post("/api/login", json={"username": "Superadmin", "password": "my-own-pass9"}).status_code == 200)

    print("\n── seed เมื่อมีผู้ใช้อยู่แล้ว / ไฟล์ไม่ถูกต้อง ──")
    p = seed_file(username="Intruder")
    res = db.seed_first_user(p)
    check("มีผู้ใช้อยู่แล้ว → ไม่สร้างเพิ่ม แต่ลบไฟล์ทิ้ง", res.get("reason") == "has_users" and not p.exists() and db.get_user_by_username("Intruder") is None, str(res))
    with db.get_conn() as conn:
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM meta WHERE k=?", (db.SEED_META_KEY,))
    p = seed_file(password_hash="zz" * 32)
    res = db.seed_first_user(p)
    check("แฮชไม่ใช่ hex → ปฏิเสธ + ลบไฟล์", res.get("reason") == "invalid" and not p.exists() and db.get_user_by_username("Superadmin") is None, str(res))
    p = config.BASE_DIR / db.SEED_FILE_NAME
    p.write_text("{not json", encoding="utf-8")
    res = db.seed_first_user(p)
    check("ไฟล์เสีย → ปฏิเสธ + ลบไฟล์ · ไม่ล้ม", res.get("reason") == "invalid" and not p.exists())
    check("ไม่มีไฟล์ → no_file (ไม่ล้ม)", db.seed_first_user(p).get("reason") == "no_file")
    p = seed_file(username="ab")
    check("ชื่อสั้นกว่า 3 → ปฏิเสธ", db.seed_first_user(p).get("reason") == "invalid" and not p.exists())
    p = seed_file()
    check("(กลับมา) seed ได้อีกเมื่อไม่มีผู้ใช้", db.seed_first_user(p).get("seeded") is True)
    check("password_is_seed เทียบแฮชในตาราง meta", db.password_is_seed(db.get_user_by_username("Superadmin")) is True and db.password_is_seed(None) is False)
    check("ตอนโปรแกรมเริ่ม server เรียก seed ไว้แล้ว (มีโค้ดใน server.py)", "seed_first_user" in (APP / "backend" / "server.py").read_text(encoding="utf-8"))

    print("\n── ลบไฟล์ที่เลิกใช้ตอนอัปเดต (app/OBSOLETE.txt) ──")
    obs = (APP / "OBSOLETE.txt").read_text(encoding="utf-8")
    check("แพ็กเกจมี app/OBSOLETE.txt และระบุ backend/licensekey.py", "backend/licensekey.py" in obs)
    src = TEST_DATA / "src_app"
    dest = TEST_DATA / "dest_app"
    for d in (src / "backend", dest / "backend" / "data", dest / "backend" / "uploads"):
        d.mkdir(parents=True, exist_ok=True)
    (src / "VERSION").write_text("9.9.9")
    (src / "backend" / "server.py").write_text("# new")
    (src / "OBSOLETE.txt").write_text("# comment\nbackend/old_module.py\n../../etc/passwd\nbackend/data/data.db\nuploads/x.xlsx\nbackend/missing.py\n")
    (dest / "backend" / "old_module.py").write_text("old")
    (dest / "backend" / "server.py").write_text("# old")
    (dest / "backend" / "data" / "data.db").write_text("DB")
    (dest / "uploads").mkdir(exist_ok=True)
    (dest / "uploads" / "x.xlsx").write_text("X")
    pyc = dest / "backend" / "__pycache__"
    pyc.mkdir()
    (pyc / "old_module.cpython-311.pyc").write_text("pyc")
    removed = server._remove_obsolete_files(src, dest)
    check("ลบเฉพาะไฟล์ในรายการ · ข้าม .. · ไม่แตะ data/uploads · ไฟล์ที่ไม่มีก็ข้าม",
          removed == ["backend/old_module.py"] and not (dest / "backend" / "old_module.py").exists()
          and (dest / "backend" / "data" / "data.db").exists() and (dest / "uploads" / "x.xlsx").exists(), str(removed))
    check("ลบ .pyc ของไฟล์นั้นด้วย", not (pyc / "old_module.cpython-311.pyc").exists())
    zp = TEST_DATA / "upd.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for f in src.rglob("*"):
            if f.is_file():
                z.write(f, "CRIMES_AUTO_update/app/" + f.relative_to(src).as_posix())
    (dest / "backend" / "old_module.py").write_text("old again")
    ver = server._apply_update_from_zip(zp, dest)
    check("_apply_update_from_zip ก๊อปทับแล้วลบไฟล์ที่เลิกใช้ · ข้อมูลเดิมอยู่",
          ver == "9.9.9" and (dest / "backend" / "server.py").read_text() == "# new" and not (dest / "backend" / "old_module.py").exists()
          and (dest / "backend" / "data" / "data.db").read_text() == "DB")

    print("\n── หน้าจอ ──")
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("มีป้ายเตือนรหัสเริ่มต้น + ปุ่มไปเปลี่ยนรหัส + ซ่อนหลังเปลี่ยนรหัส",
          all(k in html for k in ('id="seedPwNotify"', "function showSeedPwNotify", "seed_password", 'id="seedPwGo"', "showSeedPwNotify(ME)")))
    check("Update.ps1 ในแพ็กเกจลบไฟล์ตาม OBSOLETE.txt", "OBSOLETE.txt" in (APP.parent / "Update.ps1").read_text(encoding="utf-8-sig"))

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
