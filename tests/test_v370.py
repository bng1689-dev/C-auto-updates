#!/usr/bin/env python3
"""v3.7.0 — ไดเรกทอรีสมาชิกกลาง: 2 เครื่องซิงก์สมาชิกผ่านสคริปต์ศูนย์กลางตัวจริง (tools/hub_gas.js รันบน Node)

ผู้ใช้สั่ง: "เชื่อมให้ฐานข้อมูลสมาชิกออนไลน์อยู่ในหลังบ้านด้วยกัน ลิงก์กันทั้งหมดทุกเครื่องที่ติดตั้งโปรเจกนี้"
  เครื่อง A = โปรเซสนี้ · เครื่อง B = โปรเซสแยก (_hub_machine.py) ฐานข้อมูลคนละชุด · ศูนย์กลาง = hub_gas.js ตัวจริง
  ผ่าน tests/gas_harness.js (จำลอง SpreadsheetApp เก็บลงไฟล์ JSON ใบเดียวกัน)
  • เครื่องแรกสมัครพร้อมรหัสเชื่อมต่อ → Super Admin ขึ้นไดเรกทอรีกลาง · เครื่องเพิ่มเติม 'เข้าร่วม' ดึงสมาชิกมาแล้วเข้าด้วยบัญชีเดิม
  • สร้าง/แก้/ตั้งรหัส/ลบ ที่เครื่องไหน อีกเครื่องเห็นหลังซิงก์ · รหัสเปลี่ยนจากเครื่องอื่น → ตัด session + ยกเลิก PASSCODE
  • แก้ล่าสุดชนะ · ป้ายหลุมศพกันสร้างซ้ำ · ลบที่เครื่องหนึ่ง = ปิดใช้งานที่อีกเครื่อง (ไม่ลบประวัติ)
  • ล็อกอินไม่ผ่านแล้วซิงก์อัตโนมัติ (บัญชีที่เพิ่งสร้างจากเครื่องอื่นเข้าได้ทันที) · สคริปต์รุ่นเก่า → เตือนให้อัปเดต
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v370_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "A")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "A_up")
from _app import APP  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)

from backend import server  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = TEST_DATA / "hub_sheet.json"
TOKEN = "test-hub-token-0123456789"
URL = "https://script.google.com/macros/s/TEST/exec"
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def fake_post(url, payload, tok):
    """แทน hub._post — ส่งก้อนที่เซ็นแล้วเข้า hub_gas.js ตัวจริงบน Node (Sheet = ไฟล์ JSON ร่วมกับเครื่อง B)"""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    req = {"method": "POST", "body": body, "parameter": {"sign": hub.sign(body.encode("utf-8"), tok)}}
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(STATE), TOKEN],
                       input=json.dumps(req), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def machine_b(cmds):
    """สั่งเครื่อง B (โปรเซสแยก ฐานข้อมูลของตัวเอง) ทำงานตามลำดับ แล้วคืนผลเป็น dict"""
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / "B"), CRIMES_UPLOAD_DIR=str(TEST_DATA / "B_up"),
               PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / "B"), str(STATE), TOKEN],
                       input=json.dumps(cmds), env=env, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise RuntimeError("machine B: " + r.stderr[-800:])
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def hub_members():
    """อ่านไดเรกทอรีกลางตรง ๆ (ก้อน members ว่าง = ดึงอย่างเดียว)"""
    res = hub.sync_members(URL, TOKEN, "probe", "3.7.0", [])
    return {m["username"]: m for m in res.get("members", [])}


def main():
    check("มี Node สำหรับรันสคริปต์ศูนย์กลางตัวจริง", shutil.which("node") is not None)
    server.hub._post = fake_post
    server._hub_kick = lambda *a, **k: None          # ซิงก์เมื่อสั่งเท่านั้น (ให้ผลทดสอบแน่นอน)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    code = hub.make_connect_code(URL, TOKEN)

    print("── เครื่องแรกขององค์กร ──")
    r = c.post("/api/setup/join", json={"hub_code": code})
    check("เข้าร่วมก่อนมีสมาชิกในศูนย์กลาง → 400 บอกให้เครื่องแรกสร้าง Super Admin ก่อน",
          r.status_code == 400 and "ยังไม่มีสมาชิก" in r.get_json()["error"], r.get_data(as_text=True)[:160])
    check("รหัสเชื่อมต่อผิด → 400", c.post("/api/setup/join", json={"hub_code": "CRIMES-HUB:zzz"}).status_code == 400)
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน", "hub_code": code})
    check("สมัครเครื่องแรกพร้อมรหัสเชื่อมต่อ → ok + เชื่อมศูนย์กลาง", r.status_code == 200 and r.get_json().get("hub_connected"))
    last = server._members_last
    check("ซิงก์ไดเรกทอรีทันทีตอนสมัคร (reason=setup) สำเร็จ", last.get("ok") is True and last.get("reason") == "setup", str(last))
    hm = hub_members()
    check("Super Admin คนแรกอยู่บนไดเรกทอรีกลางแล้ว (แฮชรหัสผ่าน ไม่ใช่รหัสจริง)",
          "admin1" in hm and hm["admin1"]["role"] == "super_admin" and len(hm["admin1"]["password_hash"]) == 64
          and "secret9" not in json.dumps(hm, ensure_ascii=False), str(hm.keys()))
    check("ตั้งค่าแล้ว → เข้าร่วมซ้ำไม่ได้ (400)", c.post("/api/setup/join", json={"hub_code": code}).status_code == 400)

    print("\n── สคริปต์ศูนย์กลางรุ่นเก่า ──")
    real_post = server.hub._post
    server.hub._post = lambda u, p, t: {"ok": True, "stored": 0, "kind": "members"}
    res = hub.sync_members(URL, TOKEN, "x", "3.7.0", [])
    check("ตอบ ok แต่ไม่มี members → บอกให้อัปเดต hub_gas.js (ไม่เงียบ)", res.get("ok") is False and "รุ่นเก่า" in res.get("error", ""), str(res))
    server.hub._post = real_post

    print("\n── เครื่อง A สร้างสมาชิก → ขึ้นกลาง ──")
    r = c.post("/api/admin/members", json={"username": "somchai", "password": "pass66", "display_name": "สมชาย", "role": "member"})
    check("สร้าง somchai บน A", r.status_code == 200, r.get_data(as_text=True)[:120])
    sc = server.app.test_client()
    sc.post("/api/login", json={"username": "somchai", "password": "pass66"})
    sc.post("/api/auth/passcode/set", json={"password": "pass66", "passcode": "24681357", "passcode2": "24681357"})
    somchai_id = db.get_user_by_username("somchai")["id"]
    check("(เตรียม) somchai เปิด session + ตั้ง PASSCODE บน A", sc.get("/api/me").status_code == 200 and db.has_passcode(somchai_id))
    exp = {m["username"]: m for m in db.export_members()}
    check("ก้อนที่ส่งมีเฉพาะฟิลด์ที่อนุญาต ไม่มี PASSCODE/last_seen", set(exp["somchai"]) == set(hub.MEMBER_FIELDS)
          and "passcode" not in json.dumps(exp))
    res = server._members_sync_now("test")
    check("ซิงก์ A สำเร็จ", res.get("ok") is True, str(res.get("error")))
    check("somchai อยู่บนไดเรกทอรีกลาง", "somchai" in hub_members())

    print("\n── เครื่อง B เข้าร่วม (ไม่สร้าง Super Admin ซ้ำ) ──")
    out = machine_b([
        {"op": "join", "code": code},
        {"op": "login", "u": "somchai", "p": "pass66", "as": "login_somchai"},
        {"op": "logout"},
        {"op": "login", "u": "admin1", "p": "secret9", "as": "login_admin"},
        {"op": "create", "u": "wichai", "p": "pass77", "name": "วิชัย"},
        {"op": "update", "u": "somchai", "fields": {"password": "newpass6", "display_name": "สมชาย ใหม่"}},
        {"op": "sync"},
        {"op": "members"},
        {"op": "state"},
    ])
    j = out["join"]
    check("B เข้าร่วม → ok ดึงสมาชิก 2 คน, Super Admin คือ admin1", j[0] == 200 and j[1].get("members") == 2 and j[1].get("admins") == ["admin1"], str(j))
    check("B: somchai เข้าด้วยรหัสเดิมได้ (แฮชจาก A ใช้ได้ที่ B)", out["login_somchai"][0] == 200, str(out["login_somchai"]))
    check("B: admin1 ของ A เข้าที่ B ได้", out["login_admin"][0] == 200, str(out["login_admin"]))
    check("B: สร้าง wichai + ตั้งรหัสใหม่/ชื่อใหม่ให้ somchai", out["create"][0] == 200 and out["update"][0] == 200, f"{out['create']} {out['update']}")
    check("B: ซิงก์สำเร็จ", out["sync"]["ok"] is True, str(out["sync"]))
    check("B: สถานะซิงก์บนหน้าสมาชิกบอกจำนวนสมาชิกทั้งองค์กร 3 คน",
          out["state"].get("enabled") is True and out["state"]["last"].get("count") == 3, str(out["state"]))

    print("\n── เครื่อง A ซิงก์ → เห็นของ B ──")
    res = server._members_sync_now("test")
    s = res.get("summary") or {}
    check("A: สร้าง wichai · ปรับ somchai · รหัส somchai เปลี่ยน", s.get("created") == ["wichai"] and "somchai" in s.get("updated", [])
          and somchai_id in s.get("password_changed", []), str(s))
    check("A: session เดิมของ somchai ถูกตัด (รหัสถูกเปลี่ยนจากเครื่องอื่น)", sc.get("/api/me").status_code == 401)
    check("A: PASSCODE ของ somchai บน A ถูกยกเลิก", db.has_passcode(somchai_id) is False)
    check("A: ชื่อที่แสดงใหม่มาถึง", db.get_user(somchai_id)["display_name"] == "สมชาย ใหม่")
    check("A: รหัสเดิมของ somchai ใช้ไม่ได้ รหัสใหม่ใช้ได้",
          sc.post("/api/login", json={"username": "somchai", "password": "pass66"}).status_code == 401
          and sc.post("/api/login", json={"username": "somchai", "password": "newpass6"}).status_code == 200)
    sc.post("/api/logout")
    wc = server.app.test_client()
    check("A: wichai (สร้างที่ B) เข้าที่ A ได้", wc.post("/api/login", json={"username": "wichai", "password": "pass77"}).status_code == 200)
    wc.post("/api/logout")

    print("\n── ล็อกอินไม่ผ่านแล้วซิงก์อัตโนมัติ ──")
    out = machine_b([{"op": "login", "u": "admin1", "p": "secret9"},
                     {"op": "create", "u": "late", "p": "late1234", "name": "มาสาย"}, {"op": "sync"}])
    check("(เตรียม) B สร้าง late และซิงก์แล้ว", out["create"][0] == 200 and out["sync"]["ok"])
    server._members_sync_ts = 0.0
    lc = server.app.test_client()
    r = lc.post("/api/login", json={"username": "late", "password": "late1234"})
    check("A: บัญชีที่เพิ่งสร้างจากเครื่องอื่น เข้าได้ทันทีโดยไม่ต้องรอรอบซิงก์", r.status_code == 200 and server._members_last.get("reason") == "login", str(r.get_json()))
    lc.post("/api/logout")
    server._members_sync_ts = 0.0
    r = lc.post("/api/login", json={"username": "nobody", "password": "x"})
    check("A: ชื่อที่ไม่มีจริง → ยัง 401 (ซิงก์แล้วก็ไม่พบ)", r.status_code == 401)

    print("\n── ลบที่ A → ปิดใช้งานที่ B (ไม่ลบประวัติ) · ป้ายหลุมศพกันสร้างซ้ำ ──")
    admin = server.app.test_client()
    admin.post("/api/login", json={"username": "admin1", "password": "secret9"})
    wid = db.get_user_by_username("wichai")["id"]
    check("A: ลบ wichai", admin.delete(f"/api/admin/members/{wid}").status_code == 200)
    exp = {m["username"]: m for m in db.export_members()}
    check("ก้อนที่ส่งมี wichai เป็นป้ายหลุมศพ (deleted=1) ไม่ใช่แถวบัญชี", exp["wichai"]["deleted"] == 1 and not exp["wichai"]["password_hash"])
    check("A: ซิงก์หลังลบ", server._members_sync_now("test").get("ok") is True)
    out = machine_b([{"op": "sync"}, {"op": "members"}, {"op": "login", "u": "wichai", "p": "pass77"}])
    mb = {m["username"]: m for m in out["members"]}
    check("B: wichai ถูกปิดใช้งาน (ยังอยู่ในรายชื่อ ไม่ถูกลบ) และเข้าไม่ได้",
          mb.get("wichai", {}).get("active") == 0 and out["login"][0] == 401 and out["sync"]["summary"]["deactivated"] == ["wichai"], str(out))
    check("A: ซิงก์อีกรอบ wichai ไม่ถูกสร้างกลับมา (ป้ายหลุมศพชนะ)",
          server._members_sync_now("test").get("ok") and db.get_user_by_username("wichai") is None)

    print("\n── แก้ล่าสุดชนะ ──")
    ancient = dict(hub_members()["somchai"], display_name="ANCIENT", updated_at="2000-01-01T00:00:00")
    res = hub.sync_members(URL, TOKEN, "old-machine", "3.7.0", [ancient])
    check("แถวเก่ากว่าถูกศูนย์กลางปัดตก", res.get("applied") == 0 and hub_members()["somchai"]["display_name"] == "สมชาย ใหม่")
    check("apply_remote_members: แถวเก่ากว่าไม่ทับของเรา",
          db.apply_remote_members([ancient])["updated"] == [] and db.get_user(somchai_id)["display_name"] == "สมชาย ใหม่")
    s = db.apply_remote_members([{"username": "nohash", "role": "member", "updated_at": "2030-01-01T00:00:00"},
                                 {"username": "weird", "role": "god", "permissions": {"view_team": True, "bogus": True},
                                  "password_hash": "aa" * 32, "salt": "bb" * 16, "active": "1", "updated_at": "2030-01-01T00:00:00"}])
    w = db.get_user_by_username("weird")
    check("แถวไม่มีแฮช → ข้าม · บทบาทแปลก → member · สิทธิ์ dict → เก็บเฉพาะคีย์ที่รู้จัก",
          s["created"] == ["weird"] and db.get_user_by_username("nohash") is None and w["role"] == "member"
          and json.loads(w["permissions"]) == {"view_team": True}, str(s))

    print("\n── endpoint หน้าสมาชิก ──")
    st = admin.get("/api/hub/members/state").get_json()
    check("สถานะซิงก์: เปิดอยู่ + รอบล่าสุดสำเร็จ", st.get("enabled") is True and st["last"].get("ok") is True, str(st))
    r = admin.post("/api/hub/members/sync")
    check("ปุ่มซิงก์เดี๋ยวนี้ → ok + สรุป", r.status_code == 200 and r.get_json().get("ok") is True and "summary" in r.get_json(), r.get_data(as_text=True)[:160])
    hs = admin.get("/api/hub/state").get_json()
    check("หน้าตั้งค่าศูนย์กลางเห็นผลซิงก์สมาชิกและรายการฟิลด์ที่ส่ง", hs.get("members", {}).get("ok") is True and hs.get("member_fields") == list(hub.MEMBER_FIELDS))
    mc = server.app.test_client()
    mc.post("/api/login", json={"username": "somchai", "password": "newpass6"})
    check("สมาชิกธรรมดาเรียกซิงก์ไม่ได้ (403)", mc.post("/api/hub/members/sync").status_code == 403)

    print("\n── หน้าจอ ──")
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าตั้งค่ามีโหมด 'เครื่องแรก/เครื่องเพิ่มเติม' + ฟอร์มเข้าร่วม",
          all(k in html for k in ('id="setupModeBar"', 'id="authJoinForm"', 'id="joinHubCode"', "/api/setup/join")))
    check("หน้าสมาชิกมีแถบสถานะซิงก์ + ปุ่มซิงก์เดี๋ยวนี้",
          all(k in html for k in ('id="memberSyncBar"', 'id="btnMemberSync"', "/api/hub/members/state", "/api/hub/members/sync")))
    gas = (HERE.parent / "tools" / "hub_gas.js").read_text(encoding="utf-8")
    check("hub_gas.js มีชีต members และคำเตือนวิธี Deploy", "MEMBERS_SHEET" in gas and "_syncMembers" in gas and "New version" in gas)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
