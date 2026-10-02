#!/usr/bin/env python3
"""v3.13.0 — สิทธิ์ผู้ดูแลศูนย์กลางผูกกับบัญชี Superadmin (ไม่มี 🔑 ประจำเครื่อง) · ถอดคู่มือออกจากหน้าจอ

เจ้าของสั่ง: "ทุกเครื่องที่อัพเดทนี้ต้องไม่มี 🔑 หรือ ถอดรหัสผู้ดูแลออกจากทุกเครื่อง ผู้ดูแลจะผูกอยู่กับ User คือ Superadmin เท่านั้น
และ ลบคู่มือที่แสดงอยู่ออก ให้หมด"
  เครื่อง A = โปรเซสนี้ · เครื่อง B = โปรเซสแยก (_hub_machine.py) · ศูนย์กลาง = tools/hub_gas.js ตัวจริงบน Node (ไม่แตะศูนย์กลางจริง)
  • ซองรหัสผู้ดูแล: เข้า/ถอดด้วยรหัสผ่าน · รหัสผิด/ซองถูกแก้ = เปิดไม่ได้ · สุ่มใหม่ทุกครั้ง
  • อัปเดตเครื่องที่เคยมี 🔑 → config.json ไม่มีรหัสอีกทันที · Superadmin เข้าด้วยรหัสผ่านครั้งแรก = ผูกกับบัญชีให้เอง
  • ศูนย์กลาง/ไดเรกทอรีไม่มีรหัสผู้ดูแลแบบอ่านได้ที่ไหนเลย · เครื่องอื่นได้ซองไปกับไดเรกทอรี → Superadmin เข้าที่ไหนก็จัดการได้
  • เปลี่ยนรหัสผ่าน Superadmin → ซองเปิดด้วยรหัสใหม่ได้ทุกเครื่อง · ลดขั้น → ซองถูกทิ้ง · ซองเปิดไม่ได้ → บอกให้ผูกใหม่
  • สมาชิกแก้ชื่อที่แสดงของตัวเอง (ต้องลายเซ็นผู้ดูแล) → ปฏิเสธทันที ไม่ค้างรอให้ Superadmin เซ็นทีหลัง
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v3130_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "A")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "A_up")
from _app import APP  # noqa: E402

from backend import server  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = TEST_DATA / "hub_sheet.json"
TOKEN = "test-hub-token-v3130-abcdef"
ADMIN = "test-admin-token-v3130-Zq9#xY"      # ADMIN_TOKEN ในสคริปต์จำลอง
URL = "https://script.google.com/macros/s/TEST3130/exec"
VER = "3.13.0"
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def raw_post(payload, tok=TOKEN, admin_token=None):
    body = hub.encode_payload(payload).decode("ascii")
    param = {"sign": hub.sign(body.encode("utf-8"), tok)}
    if admin_token:
        param["asign"] = hub.sign(body.encode("utf-8"), admin_token)
    req = {"method": "POST", "body": body, "parameter": param}
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(req), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def fake_post(url, payload, tok, admin_token=None, timeout=None):
    return raw_post(payload, tok, admin_token)


def machine_b(cmds):
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / "B"), CRIMES_UPLOAD_DIR=str(TEST_DATA / "B_up"),
               PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / "B"), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(cmds), env=env, capture_output=True, text=True, timeout=240)
    if r.returncode:
        raise RuntimeError("machine B: " + r.stderr[-800:])
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def hub_members():
    res = hub.sync_members(URL, TOKEN, "probe", VER, [])
    return {m["username"]: m for m in res.get("members", [])}


def hub_env(username):
    try:
        return json.loads(hub_members()[username]["permissions"]).get(db.ADMIN_KEY_FIELD, "")
    except (KeyError, ValueError, TypeError):
        return ""


def main():
    print("── ซองรหัสผู้ดูแล (เข้ารหัสด้วยรหัสผ่าน) ──")
    env = auth.seal_admin_key(ADMIN, "secret9")
    check("เข้าซองแล้วถอดด้วยรหัสผ่านเดียวกันได้รหัสเดิม", auth.open_admin_key(env, "secret9") == ADMIN)
    check("ซองไม่มีรหัสจริงอยู่ในรูปอ่านได้ · รูปแบบ v1$รอบ$salt$nonce$ข้อมูล$MAC · ยาวไม่เกิน 400 ตัว",
          ADMIN not in env and env.startswith("v1$") and env.count("$") == 5 and len(env) < 400, env[:60])
    check("รหัสผ่านผิด → เปิดไม่ได้ (คืนค่าว่าง)", auth.open_admin_key(env, "secret8") == "")
    parts = env.split("$")
    flip = lambda h: ("0" if h[0] != "0" else "1") + h[1:]
    bad_ct = "$".join(parts[:4] + [flip(parts[4])] + parts[5:])
    bad_mac = "$".join(parts[:5] + [flip(parts[5])])
    low_iter = "$".join([parts[0], "1000"] + parts[2:])
    check("แก้ข้อมูลเข้ารหัส/MAC/ลดรอบ PBKDF2 → เปิดไม่ได้ทั้งหมด",
          auth.open_admin_key(bad_ct, "secret9") == "" and auth.open_admin_key(bad_mac, "secret9") == ""
          and auth.open_admin_key(low_iter, "secret9") == "")
    check("ซองเสีย/ไม่ใช่ซอง → ค่าว่าง ไม่ล้ม", all(auth.open_admin_key(x, "secret9") == "" for x in
                                                ("", None, "v1$x", "v2$200000$aa$bb$cc$dd", "ไทย$1$2$3$4$5", 12345)))
    check("เข้าซองซ้ำได้ผลต่างกันทุกครั้ง (salt/nonce สุ่มใหม่)", auth.seal_admin_key(ADMIN, "secret9") != env)
    check("รอบ PBKDF2 ของซอง ≥ รอบของแฮชรหัสผ่าน (เดาซองไม่ง่ายกว่าเดาแฮชที่ไดเรกทอรีมีอยู่แล้ว)",
          int(parts[1]) >= db._ITERATIONS)

    print("\n── เครื่อง A = เครื่องเจ้าของที่เคยมี 🔑 แล้วอัปเดตเป็น v3.13.0 ──")
    check("มี Node สำหรับรันสคริปต์ศูนย์กลางตัวจริง", shutil.which("node") is not None)
    server.hub._post = fake_post
    server._hub_kick = lambda *a, **k: None
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    code = hub.make_connect_code(URL, TOKEN)
    # เครื่องแรกขององค์กร (สคริปต์ตั้ง ADMIN_TOKEN แล้ว → ก้อนแรกต้องเซ็นผู้ดูแล) — ตั้งแบบไม่มีรหัสผู้ดูแล = Superadmin ค้างส่ง
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน", "hub_code": code})
    check("(เตรียม) ตั้งค่าเครื่องแรกโดยไม่มีรหัสผู้ดูแล → สำเร็จ แต่ Superadmin ยังไม่ขึ้นกลาง (ต้องลายเซ็นผู้ดูแล)",
          r.status_code == 200 and "admin1" not in hub_members() and db.count_pending_members() == 1, str(r.get_json()))
    c.post("/api/logout")
    # จำลอง config.json ของรุ่นก่อนที่ยังมี 🔑 แล้วเปิดโปรแกรมรุ่นนี้
    cfg = json.loads(Path(server.config.CONFIG_PATH).read_text(encoding="utf-8"))
    cfg["hub_admin_token"] = ADMIN
    Path(server.config.CONFIG_PATH).write_text(json.dumps(cfg), encoding="utf-8")
    auth.load_config()
    on_disk = Path(server.config.CONFIG_PATH).read_text(encoding="utf-8")
    check("เปิดรุ่นนี้ → config.json ไม่มี 🔑 อีกทันที (ไม่ต้องรอใครเข้าสู่ระบบ)",
          "hub_admin_token" not in on_disk and ADMIN not in on_disk)
    check("รหัสเดิมพักไว้ในหน่วยความจำของโปรเซสเท่านั้น รอผูกกับ Superadmin", auth.take_legacy_admin_token(peek=True) == ADMIN)
    st = c.post("/api/login", json={"username": "admin1", "password": "secret9"})
    hs = c.get("/api/hub/state").get_json()
    check("Superadmin เข้าด้วยรหัสผ่าน → ผูกรหัสเดิมกับบัญชีให้เอง · ใช้สิทธิ์ผู้ดูแลได้ทันที",
          st.status_code == 200 and hs.get("admin_bound") is True and hs.get("admin_unlocked") is True
          and hs.get("admin_legacy") is False and ADMIN not in json.dumps(hs), str(hs)[:240])
    hm = hub_members()
    check("ศูนย์กลางรับ Superadmin (ลายเซ็นผู้ดูแล) พร้อมซองในบัญชี · ไม่ค้างส่ง",
          "admin1" in hm and hub_env("admin1").startswith("v1$") and db.count_pending_members() == 0, str(hm.get("admin1"))[:200])
    check("รหัสหายจากหน่วยความจำ 'รอผูก' แล้ว (ผูกเสร็จ)", auth.take_legacy_admin_token(peek=True) == "")
    check("ไม่มีรหัสผู้ดูแลแบบอ่านได้ที่ไหนเลย: config.json · ฐานข้อมูลเครื่อง · ชีตศูนย์กลาง",
          ADMIN not in Path(server.config.CONFIG_PATH).read_text(encoding="utf-8")
          and ADMIN.encode() not in Path(server.config.DB_PATH).read_bytes()
          and ADMIN not in STATE.read_text(encoding="utf-8"))
    me = c.get("/api/me").get_json()
    check("/api/me: central_manager=True · admin_bound=True", me.get("central_manager") is True and me.get("admin_bound") is True)
    r = c.post("/api/admin/members", json={"username": "somchai", "password": "pass66", "display_name": "สมชาย", "role": "member"})
    res = server._members_sync_now("test")
    check("A: สร้างสมาชิก → ขึ้นกลางด้วยลายเซ็นผู้ดูแล", r.status_code == 200 and res.get("admin") is True
          and not res.get("rejected") and "somchai" in hub_members())

    print("\n── เครื่อง B (ไม่เคยมี 🔑) — Superadmin เข้าที่ไหนก็ได้สิทธิ์ ──")
    out = machine_b([
        {"op": "join", "code": code},
        {"op": "login", "u": "admin1", "p": "secret9", "as": "login1"},
        {"op": "hold", "as": "hold1"},
        {"op": "get", "path": "/api/hub/state", "as": "hs"},
        {"op": "password", "cur": "secret9", "new": "newsecret9"},
        {"op": "envelope", "u": "admin1", "as": "env_after"},
        {"op": "sync", "as": "sync_pw"},
        {"op": "config_file", "as": "cfg"},
    ])
    check("B: เข้าร่วม · admin1 เข้าด้วยรหัสผ่าน → ถือสิทธิ์ผู้ดูแลทันที",
          out["join"][0] == 200 and out["login1"][0] == 200 and out["hold1"] == "admin1"
          and out["hs"][1].get("admin_unlocked") is True, f"{out['login1']} {out['hold1']}")
    check("B: admin1 เปลี่ยนรหัสผ่าน → เข้าซองใหม่ด้วยรหัสใหม่ · ขึ้นกลางพร้อมแฮชใหม่ในแถวเดียวกัน (ลายเซ็นผู้ดูแล)",
          out["password"][0] == 200 and auth.open_admin_key(out["env_after"], "newsecret9") == ADMIN
          and auth.open_admin_key(out["env_after"], "secret9") == "" and out["sync_pw"]["ok"]
          and not out["sync_pw"]["rejected"] and out["sync_pw"]["admin"] is True, str(out["sync_pw"]))
    check("B: config.json ไม่มีรหัสผู้ดูแล", "hub_admin_token" not in out["cfg"] and ADMIN not in json.dumps(out["cfg"]))
    check("กลาง: ซองของ admin1 เป็นใบใหม่ (เปิดด้วยรหัสใหม่ได้)", auth.open_admin_key(hub_env("admin1"), "newsecret9") == ADMIN)

    print("\n── กลับมาที่ A: รหัสใหม่มาถึง → Superadmin เข้าด้วยรหัสใหม่ก็ยังจัดการได้ ──")
    res = server._members_sync_now("test")
    check("A: ซิงก์ → รหัสของ admin1 เปลี่ยนตามกลาง · ใบเดิมถูกตัด · สิทธิ์ที่ถอดไว้ (ซองเก่า) ใช้ไม่ได้แล้ว",
          db.get_user_by_username("admin1")["id"] in (res.get("summary") or {}).get("password_changed", [])
          and c.get("/api/me").status_code == 401 and server._admin_token() == "", str(res.get("summary")))
    check("A: รหัสเดิมเข้าไม่ได้", c.post("/api/login", json={"username": "admin1", "password": "secret9"}).status_code == 401)
    r = c.post("/api/login", json={"username": "admin1", "password": "newsecret9"})
    r2 = c.post("/api/admin/members", json={"username": "wichai", "password": "pass77", "display_name": "วิชัย", "role": "member"})
    res = server._members_sync_now("test")
    check("A: เข้าด้วยรหัสใหม่ → ถอดซองใหม่ได้ · สร้างสมาชิกขึ้นกลางได้", r.status_code == 200 and r2.status_code == 200
          and res.get("admin") is True and "wichai" in hub_members(), str(r2.get_json()))

    print("\n── ผูกด้วยมือ: Superadmin คนที่สอง ──")
    r = c.post("/api/admin/members", json={"username": "admin2", "password": "second9", "display_name": "แอดมิน 2", "role": "super_admin"})
    server._members_sync_now("test")
    a2 = server.app.test_client()
    a2.post("/api/login", json={"username": "admin2", "password": "second9"})
    r = a2.post("/api/admin/teams", json={"name": "ทีมทดสอบ", "member_ids": []})
    check("admin2 (ยังไม่ผูก) จัดทีมไม่ได้ → 403 need_bind พร้อมบอกที่ผูก", r.status_code == 403 and r.get_json().get("need_bind") is True
          and "Setting" in r.get_json().get("error", ""), str(r.get_json()))
    r = a2.post("/api/hub/admin/bind", json={"admin_token": ADMIN, "password": "wrong-pw"})
    check("ผูกด้วยรหัสผ่านผิด → 400 (ไม่ใช่ 401 ที่ทำให้หลุดจากระบบ) · ไม่มีซอง", r.status_code == 400 and not db.get_admin_envelope(db.get_user_by_username("admin2")["id"]))
    r = a2.post("/api/hub/admin/bind", json={"admin_token": "not-the-admin-token-123", "password": "second9"})
    check("ผูกด้วย ADMIN_TOKEN ผิด → 403 ศูนย์กลางไม่ยืนยัน · ถอยคืน ไม่มีซอง · ไม่ค้างส่ง",
          r.status_code == 403 and not db.get_admin_envelope(db.get_user_by_username("admin2")["id"])
          and db.count_pending_members() == 0 and "admin2" in hub_members() and not hub_env("admin2"), str(r.get_json()))
    r = a2.post("/api/hub/admin/bind", json={"admin_token": ADMIN, "password": "second9"})
    check("ผูกด้วยรหัสถูก → สำเร็จ · ซองขึ้นกลาง · admin2 จัดทีมได้", r.status_code == 200
          and hub_env("admin2").startswith("v1$")
          and a2.post("/api/admin/teams", json={"name": "ทีมทดสอบ", "member_ids": []}).status_code == 200, str(r.get_json()))
    uid1 = db.get_user_by_username("admin1")["id"]
    env1 = db.get_admin_envelope(uid1)
    c.put(f"/api/admin/members/{uid1}", json={"permissions": {"manage_members": True}})
    check("แก้สิทธิ์ของบัญชี Superadmin (set_permissions) → ซองยังอยู่ครบ", db.get_admin_envelope(uid1) == env1)
    uid2 = db.get_user_by_username("admin2")["id"]
    r = c.put(f"/api/admin/members/{uid2}", json={"role": "member"})
    server._members_sync_now("test")
    check("ลดขั้น admin2 เป็นสมาชิก → ซองถูกทิ้ง (ในเครื่อง + บนกลาง) · admin2 ไม่มีสิทธิ์ผู้ดูแลอีก",
          r.status_code == 200 and not db.get_admin_envelope(uid2) and not hub_env("admin2")
          and "_hub_admin" not in (db.get_user(uid2)["permissions"] or ""), str(r.get_json()))

    print("\n── ซองเปิดไม่ได้ (รหัสผ่านถูกตั้งจากทางที่ไม่ได้เข้าซองใหม่) → บอกให้ผูกใหม่ ไม่วนขอรหัสผ่าน ──")
    held = server._admin_token(uid1) == ADMIN
    # จำลองรหัสถูกเปลี่ยนจากเครื่องรุ่นเก่า (ไม่เข้าซองใหม่ — ซองในบัญชียังเป็นใบเดิม) ขณะ admin1 ยังถือสิทธิ์อยู่ที่เครื่องนี้
    db.change_user_password(uid1, "third999")
    check("รหัสผ่านเปลี่ยน (แม้ซองยังเป็นใบเดิม) → สิทธิ์ที่ถอดไว้ด้วยรหัสเดิมถูกปล่อยทันที (รีวิว Codex PR #41)",
          held and server._admin_token(uid1) == "" and server._admin_token() == "")
    r = c.post("/api/login", json={"username": "admin1", "password": "third999"})
    r2 = c.post("/api/admin/teams", json={"name": "ทีม X", "member_ids": []})
    check("เข้าได้ แต่ซองเดิมเปิดไม่ได้ → งานผู้ดูแลตอบ need_bind (ไม่ใช่ need_password ซ้ำ ๆ) · /api/me admin_stale=True",
          r.status_code == 200 and r2.status_code == 403 and r2.get_json().get("need_bind") is True
          and not r2.get_json().get("need_password") and c.get("/api/me").get_json().get("admin_stale") is True, str(r2.get_json()))
    r = c.post("/api/hub/admin/bind", json={"admin_token": ADMIN, "password": "third999"})
    check("ผูกใหม่ด้วย ADMIN_TOKEN + รหัสปัจจุบัน → ใช้ได้อีกครั้ง",
          r.status_code == 200 and c.post("/api/admin/teams", json={"name": "ทีม X", "member_ids": []}).status_code == 200, str(r.get_json()))

    print("\n── สมาชิกแก้ชื่อที่แสดงของตัวเอง (ต้องลายเซ็นผู้ดูแล) → ปฏิเสธทันที ไม่ค้างรอเซ็น ──")
    server._members_sync_now("test")
    sc = server.app.test_client()
    sc.post("/api/login", json={"username": "somchai", "password": "pass66"})
    pend0 = db.count_pending_members()
    r = sc.post("/api/settings", json={"display_name": "ชื่อใหม่ของฉัน"})
    check("สมาชิกเปลี่ยนชื่อที่แสดงขณะเชื่อมศูนย์กลาง → 403 · ชื่อไม่เปลี่ยน · ไม่มีอะไรค้างส่ง",
          r.status_code == 403 and db.get_user_by_username("somchai")["display_name"] == "สมชาย" and db.count_pending_members() == pend0,
          str(r.get_json()))
    r = sc.post("/api/settings", json={"display_name": "สมชาย", "search_speed": 3})
    check("ส่งชื่อเดิมมาพร้อมค่าอื่น (ฟอร์มตั้งค่า) → ผ่าน ไม่ติดธงส่ง", r.status_code == 200 and db.count_pending_members() == pend0, str(r.get_json()))
    r = c.post("/api/settings", json={"display_name": "แอดมินใหญ่"})
    check("Superadmin ที่ใช้สิทธิ์อยู่เปลี่ยนชื่อตัวเองได้", r.status_code == 200 and db.get_user(uid1)["display_name"] == "แอดมินใหญ่")

    print("\n── ออกจากระบบ = สิทธิ์ในเครื่องหายไป ──")
    c.post("/api/logout")
    check("หลัง Superadmin ออกจากระบบ ไม่มีใครถือสิทธิ์ผู้ดูแลในเครื่อง (ซิงก์เบื้องหลังเซ็นไม่ได้)", server._admin_token() == "")

    print("\n── รีวิว: การแก้ที่ไม่ได้ทำโดยผู้ถือสิทธิ์ ต้องไม่ถูกเซ็นทีหลัง ──")
    c.post("/api/login", json={"username": "admin1", "password": "third999"})
    server._members_sync_now("test")
    somchai = db.get_user_by_username("somchai")
    with db.signing(False):                         # จำลองการแก้ค้างจากรุ่นก่อน/ผู้จัดการ (ไม่ลงนาม)
        db.update_user(somchai["id"], display_name="แอบแก้ชื่อ", rate_per_name=99)
    check("(เตรียม) แถวค้างส่งที่ไม่ลงนาม: sync_signed=0", db.get_user(somchai["id"])["sync_signed"] == 0
          and db.get_user(somchai["id"])["sync_dirty"] == 1)
    res = server._members_sync_now("test")
    hm = hub_members()
    check("Superadmin ถือสิทธิ์อยู่ในเครื่องเดียวกัน → แถวนั้นไม่ถูกเซ็น (ส่งแบบไม่เซ็น ถูกปัดตก) → ของกลางทับ ไม่ค้าง",
          hm["somchai"]["display_name"] == "สมชาย" and db.get_user(somchai["id"])["display_name"] == "สมชาย"
          and db.get_user(somchai["id"])["sync_dirty"] == 0 and "somchai" in (res.get("summary") or {}).get("reverted", []),
          str(res.get("summary")))
    r = c.put(f"/api/admin/members/{somchai['id']}", json={"display_name": "สมชาย ใจดี"})
    res = server._members_sync_now("test")
    check("การแก้ของ Superadmin ผู้ถือสิทธิ์ (sync_signed=1) → เซ็นแล้วขึ้นกลาง", r.status_code == 200
          and hub_members()["somchai"]["display_name"] == "สมชาย ใจดี" and res.get("admin") is True, str(res.get("rejected")))
    r = c.put(f"/api/admin/members/{somchai['id']}", json={"display_name": None})
    check("ชื่อที่แสดง null → บันทึกเป็นค่าว่าง (ไม่ใช่ข้อความ 'None')", r.status_code == 200
          and db.get_user(somchai["id"])["display_name"] == "")
    server._members_sync_now("test")
    print("\n── รีวิว: ปิดศูนย์กลางชั่วคราว → ผู้จัดการแก้ → เปิดกลับ: ไม่ถูกเซ็น ──")
    r = c.post("/api/admin/members", json={"username": "mgr2", "password": "mgr22222", "display_name": "ผู้จัดการ 2",
                                           "role": "member", "permissions": {"manage_members": True}})
    server._members_sync_now("test")
    auth.update_config(hub_enabled=False)
    mg = server.app.test_client()
    mg.post("/api/login", json={"username": "mgr2", "password": "mgr22222"})
    r = mg.post("/api/admin/members", json={"username": "offhub", "password": "offhub12", "display_name": "นอกศูนย์"})
    check("(เตรียม) ศูนย์กลางปิด → ผู้จัดการสร้างสมาชิกในเครื่องได้ แต่จดว่า 'ไม่ลงนาม'",
          r.status_code == 200 and db.get_user_by_username("offhub")["sync_signed"] == 0, str(r.get_json()))
    auth.update_config(hub_enabled=True)
    res = server._members_sync_now("test")
    check("เปิดศูนย์กลางกลับ + Superadmin ถือสิทธิ์อยู่ → offhub ไม่ถูกเซ็นขึ้นกลาง (ค้างรอ Superadmin ยืนยันเอง)",
          "offhub" not in hub_members() and db.get_user_by_username("offhub")["sync_dirty"] == 1, str(res.get("rejected")))
    r = c.put(f"/api/admin/members/{db.get_user_by_username('offhub')['id']}", json={"display_name": "นอกศูนย์ (ยืนยันแล้ว)"})
    server._members_sync_now("test")
    check("Superadmin แก้แถวนั้นเอง (ยืนยัน) → ลงนามแล้วขึ้นกลาง", r.status_code == 200 and "offhub" in hub_members())
    mg.post("/api/logout")

    print("\n── รีวิว: ขอบเขตอื่น ๆ ──")
    r = c.post("/api/hub/admin/bind", json={"admin_token": "x" * 400, "password": "third999"})
    check("ADMIN_TOKEN ยาวผิดปกติ → ปฏิเสธ (ไม่ล้ม 500)", r.status_code == 403 and "ยาว" in r.get_json().get("error", ""), str(r.get_json()))
    with server._ADMIN_HOLD_LOCK:
        server._ADMIN_HOLDS[uid1]["seen"] = 0.0
    check("สิทธิ์ที่ถอดไว้ไม่มีความเคลื่อนไหวเกินกำหนด → ปล่อยทิ้ง (ลืมออกจากระบบ)", server._admin_token() == "")
    r = c.post("/api/password", json={"current": "third999", "new": "fourth999"})
    check("Superadmin เปลี่ยนรหัสผ่าน (ถอดซองด้วยรหัสเดิมได้) → สำเร็จ · ซองใหม่ใส่พร้อมรหัสใหม่",
          r.status_code == 200 and auth.open_admin_key(db.get_admin_envelope(uid1), "fourth999") == ADMIN, str(r.get_json()))
    exp = {m["username"]: m for m in db.export_members(signed=True)}
    check("แถวที่ค้างส่งมีทั้งแฮชใหม่และซองใหม่ในก้อนเดียว (ลงนามได้)",
          "admin1" in exp and auth.open_admin_key(json.loads(exp["admin1"]["permissions"])["_hub_admin"], "fourth999") == ADMIN)
    server._members_sync_now("test")
    c.post("/api/logout")
    uid3 = None
    with db.signing(True):
        uid3 = db.create_user("admin3", "third333", display_name="แอดมิน 3", role="super_admin")
    server._members_sync_now("test")
    a3 = server.app.test_client()
    a3.post("/api/login", json={"username": "admin3", "password": "third333"})
    r = a3.post("/api/password", json={"current": "third333", "new": "third444"})
    check("Superadmin ที่ยังไม่ผูก เปลี่ยนรหัสผ่านขณะเชื่อมศูนย์กลาง → 403 need_bind (ไม่เปลี่ยนในเครื่องแล้วค้าง)",
          r.status_code == 403 and r.get_json().get("need_bind") is True and db.verify_user("admin3", "third333"), str(r.get_json()))
    auth._LEGACY_ADMIN_TOKEN[0] = ADMIN             # จำลองรหัสเดิมของเครื่องที่ยังรอผูก
    a3.post("/api/logout")
    a3.post("/api/login", json={"username": "admin3", "password": "third333"})
    check("มี Superadmin หลายคน → ไม่ผูกรหัสเดิมของเครื่องให้ใครอัตโนมัติ (ต้องผูกเองที่ Setting)",
          not db.get_admin_envelope(uid3) and auth.take_legacy_admin_token(peek=True) == ADMIN)
    auth.take_legacy_admin_token()
    st = c.post("/api/login", json={"username": "admin1", "password": "fourth999"})
    me = c.get("/api/me").get_json()
    check("/api/me: admin_stale=False เมื่อเปิดซองได้", st.status_code == 200 and me.get("admin_stale") is False and me.get("central_manager") is True)
    check("เปลี่ยนรหัสผ่านของตัวเองแล้วยังถือสิทธิ์ต่อได้ (จำรหัสใหม่)",
          c.post("/api/password", json={"current": "fourth999", "new": "fifth999"}).status_code == 200
          and server._admin_token(uid1) == ADMIN)
    real_change = db.change_user_password

    def _remote_lands(uid, pw, admin_envelope=None):
        out = real_change(uid, pw, admin_envelope=admin_envelope)
        with db.signing(False):             # จังหวะเดียวกัน: ซิงก์เบื้องหลังนำรหัสผ่านที่ถูกเปลี่ยนจากเครื่องอื่นมาทับ
            real_change(uid, "remote999")
        return out
    db.change_user_password = _remote_lands
    try:
        r = c.post("/api/password", json={"current": "fifth999", "new": "sixth999"})
    finally:
        db.change_user_password = real_change
    check("รหัสผ่านจากเครื่องอื่นมาทับระหว่างเปลี่ยนรหัสเอง → สิทธิ์ไม่ถูกผูกกับรหัสของคนอื่น (ปล่อยทิ้ง) (รีวิว Codex PR #42)",
          r.status_code == 200 and server._admin_token(uid1) == "", str(r.get_json()))
    a3.post("/api/logout")
    c.post("/api/logout")

    print("\n── หน้าจอ ──")
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("ถอดคู่มือที่แสดงอยู่ออกหมด: ไม่มีปุ่ม 📖 · ไม่มีหน้าต่างคู่มือ · ไม่มี CSS/ตัวจัดการของคู่มือ",
          all(k not in html for k in ('id="btnManual"', 'id="manualModal"', "btnManualClose", "manual-sec", "manual-overlay", "คู่มือการใช้งาน")))
    check("ไม่มีช่อง 🔑 ประจำเครื่อง (ตั้งค่า/สมัคร) · มีสถานะ+ฟอร์มผูกสิทธิ์กับบัญชี Superadmin",
          all(k not in html for k in ('id="hubAdminToken"', 'id="btnHubAdminClear"', 'id="suHubAdmin"', "hub_admin_token"))
          and all(k in html for k in ('id="hubAdminBindForm"', "/api/hub/admin/bind", 'id="btnHubAdminUnlock"', "adminLockNote")))
    check("งานจัดสมาชิก/ทีม/กองกลางบนหน้าจอขอรหัสผ่านแล้วลองซ้ำให้เอง (withPasswordRetry)",
          all(k in html for k in ('withPasswordRetry(()=>api("/api/admin/members",{method:"POST"',
                                   'withPasswordRetry(()=>api("/api/admin/teams",{method:"POST"',
                                   'withPasswordRetry(()=>api("/api/admin/ledger",{method:"POST"')))
    src = (APP / "backend" / "server.py").read_text(encoding="utf-8") + (APP / "backend" / "auth.py").read_text(encoding="utf-8")
    check("โค้ดไม่อ่าน/เขียนรหัสผู้ดูแลจาก config อีก (ยกเว้นจุดถอดของรุ่นก่อนใน auth.load_config)",
          'cfg.get("hub_admin_token")' not in src and 'config().get("hub_admin_token")' not in src
          and "update_config(hub_admin_token" not in src and 'changes["hub_admin_token"]' not in src)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
