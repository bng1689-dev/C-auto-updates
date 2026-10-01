#!/usr/bin/env python3
"""v3.7.0 — ไดเรกทอรีสมาชิกกลาง: 2 เครื่องซิงก์สมาชิกผ่านสคริปต์ศูนย์กลางตัวจริง (tools/hub_gas.js รันบน Node)

ผู้ใช้สั่ง: "เชื่อมให้ฐานข้อมูลสมาชิกออนไลน์อยู่ในหลังบ้านด้วยกัน ลิงก์กันทั้งหมดทุกเครื่องที่ติดตั้งโปรเจกนี้"
  เครื่อง A = โปรเซสนี้ · เครื่อง B = โปรเซสแยก (_hub_machine.py) ฐานข้อมูลคนละชุด · ศูนย์กลาง = hub_gas.js ตัวจริง
  ผ่าน tests/gas_harness.js (จำลอง SpreadsheetApp เก็บลงไฟล์ JSON ใบเดียวกัน)
  • เครื่องแรกสมัครพร้อมรหัสเชื่อมต่อ (+รหัสผู้ดูแล) → Super Admin ขึ้นไดเรกทอรีกลาง · เครื่องเพิ่มเติม 'เข้าร่วม' ดึงสมาชิกมา
  • เครื่องที่มีแค่รหัสเชื่อมต่อ (สมาชิก): เปลี่ยนรหัสตัวเองขึ้นกลางได้ · สร้าง/แก้คนอื่นถูกปัดตก ค้างไว้จนใส่รหัสผู้ดูแล
  • รหัสร่วม (HUB_TOKEN) ตั้งตัวเองเป็น Super Admin / เปลี่ยนรหัสคนอื่น / แก้ด้วยรหัสผู้ดูแลผิด → ศูนย์กลางปัดตก
  • ศูนย์กลางไม่ยอมให้ไม่เหลือ Super Admin ที่เปิดใช้งาน (สองเครื่องปิดกันเองพร้อมกัน → เหลืออย่างน้อยหนึ่ง)
  • ลำดับการแก้ตัดสินด้วยเลขรุ่น (rev) ของศูนย์กลาง ไม่ใช่นาฬิกาเครื่อง — เครื่องที่นาฬิกาอยู่ปี 2099 ก็ไม่ชนะ
  • รหัสเปลี่ยนจากเครื่องอื่น → ตัด session + ยกเลิก PASSCODE · ลบที่เครื่องหนึ่ง = ปิดใช้งานที่อีกเครื่อง (ไม่ลบประวัติ)
  • ล็อกอินไม่ผ่านแล้วซิงก์อัตโนมัติ · สคริปต์รุ่นเก่า → เตือนให้อัปเดต
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
ADMIN = "test-admin-token-9876543210"        # ADMIN_TOKEN ในสคริปต์จำลอง = รหัสผู้ดูแลศูนย์กลาง
URL = "https://script.google.com/macros/s/TEST/exec"
VER = "3.7.0"
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def raw_post(payload, tok=TOKEN, admin_token=None, script_admin=ADMIN):
    """ยิงก้อนที่เซ็นแล้วเข้า hub_gas.js ตัวจริงบน Node (Sheet = ไฟล์ JSON ร่วมกับเครื่อง B)"""
    body = hub.encode_payload(payload).decode("ascii")   # ก้อนจริงเป็น ASCII ล้วน (v3.10.2 — ดู hub.encode_payload)
    param = {"sign": hub.sign(body.encode("utf-8"), tok)}
    if admin_token:
        param["asign"] = hub.sign(body.encode("utf-8"), admin_token)
    req = {"method": "POST", "body": body, "parameter": param}
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(STATE), TOKEN, script_admin],
                       input=json.dumps(req), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def fake_post(url, payload, tok, admin_token=None):
    """แทน hub._post ของเครื่อง A"""
    return raw_post(payload, tok, admin_token)


def machine_b(cmds):
    """สั่งเครื่อง B (โปรเซสแยก ฐานข้อมูลของตัวเอง) ทำงานตามลำดับ แล้วคืนผลเป็น dict"""
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / "B"), CRIMES_UPLOAD_DIR=str(TEST_DATA / "B_up"),
               PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / "B"), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(cmds), env=env, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise RuntimeError("machine B: " + r.stderr[-800:])
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def hub_members():
    """อ่านไดเรกทอรีกลางตรง ๆ (ก้อน members ว่าง = ดึงอย่างเดียว)"""
    res = hub.sync_members(URL, TOKEN, "probe", VER, [])
    return {m["username"]: m for m in res.get("members", [])}


def push_raw(rows, admin_token=ADMIN, install="raw"):
    """ส่งแถวขึ้นกลางตรง ๆ (เหมือนเครื่องที่ประกอบก้อนเอง) — คืนผลจาก hub.sync_members"""
    return hub.sync_members(URL, TOKEN, install, VER, rows, admin_token=admin_token)


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
                                   "display_name": "แอดมิน", "hub_code": code, "hub_admin_token": ADMIN})
    check("สมัครเครื่องแรกพร้อมรหัสเชื่อมต่อ+รหัสผู้ดูแล → ok + เชื่อมศูนย์กลาง", r.status_code == 200 and r.get_json().get("hub_connected"))
    last = server._members_last
    check("ซิงก์ไดเรกทอรีทันทีตอนสมัคร (reason=setup) สำเร็จ ไม่มีรายการค้าง",
          last.get("ok") is True and last.get("reason") == "setup" and last.get("pending") == 0 and last.get("admin") is True, str(last))
    hm = hub_members()
    check("Super Admin คนแรกอยู่บนไดเรกทอรีกลางแล้ว rev=1 (แฮชรหัสผ่าน ไม่ใช่รหัสจริง)",
          "admin1" in hm and hm["admin1"]["role"] == "super_admin" and hm["admin1"]["rev"] == 1
          and len(hm["admin1"]["password_hash"]) == 64 and "secret9" not in json.dumps(hm, ensure_ascii=False), str(hm))
    check("หลังกลางรับแล้ว ไม่มีแถวค้างส่ง (ส่งเฉพาะที่แก้) · rev ในเครื่องตรงกับกลาง",
          db.export_members() == [] and db.get_user_by_username("admin1")["hub_rev"] == 1 and db.count_pending_members() == 0)
    check("ตั้งค่าแล้ว → เข้าร่วมซ้ำไม่ได้ (400)", c.post("/api/setup/join", json={"hub_code": code}).status_code == 400)

    print("\n── สคริปต์ศูนย์กลางรุ่นเก่า ──")
    real_post = server.hub._post
    server.hub._post = lambda u, p, t, admin_token=None: {"ok": True, "stored": 0, "kind": "members"}
    res = hub.sync_members(URL, TOKEN, "x", VER, [])
    check("ตอบ ok แต่ไม่มี members → บอกให้อัปเดต hub_gas.js (ไม่เงียบ)", res.get("ok") is False and "รุ่นเก่า" in res.get("error", ""), str(res))
    server.hub._post = real_post

    print("\n── เครื่อง A (มีรหัสผู้ดูแล) สร้างสมาชิก → ขึ้นกลาง ──")
    r = c.post("/api/admin/members", json={"username": "somchai", "password": "pass66", "display_name": "สมชาย", "role": "member"})
    check("สร้าง somchai บน A", r.status_code == 200, r.get_data(as_text=True)[:120])
    sc = server.app.test_client()
    sc.post("/api/login", json={"username": "somchai", "password": "pass66"})
    sc.post("/api/auth/passcode/set", json={"password": "pass66", "passcode": "24681357", "passcode2": "24681357"})
    somchai_id = db.get_user_by_username("somchai")["id"]
    check("(เตรียม) somchai เปิด session + ตั้ง PASSCODE บน A", sc.get("/api/me").status_code == 200 and db.has_passcode(somchai_id))
    exp = {m["username"]: m for m in db.export_members()}
    check("ก้อนที่ส่งมีเฉพาะคนที่แก้ (somchai) และเฉพาะฟิลด์ที่อนุญาต ไม่มี PASSCODE/last_seen",
          list(exp) == ["somchai"] and set(exp["somchai"]) == set(hub.MEMBER_FIELDS) and "passcode" not in json.dumps(exp))
    res = server._members_sync_now("test")
    check("ซิงก์ A สำเร็จ", res.get("ok") is True and not res.get("rejected"), str(res.get("error")))
    check("somchai อยู่บนไดเรกทอรีกลาง rev=1", hub_members().get("somchai", {}).get("rev") == 1)

    print("\n── เครื่อง B เข้าร่วมแบบเครื่องสมาชิก (ไม่มีรหัสผู้ดูแล) ──")
    out = machine_b([
        {"op": "join", "code": code},
        {"op": "login", "u": "somchai", "p": "pass66", "as": "login_somchai"},
        {"op": "password", "cur": "pass66", "new": "newpass6"},
        {"op": "logout"},
        {"op": "sync", "as": "sync_pw"}, {"op": "pending", "as": "pending_pw"},
        {"op": "login", "u": "admin1", "p": "secret9", "as": "login_admin"},
        {"op": "create", "u": "wichai", "p": "pass77", "name": "วิชัย"},
        {"op": "update", "u": "somchai", "fields": {"display_name": "สมชาย ใหม่"}},
        {"op": "sync", "as": "sync_admin"}, {"op": "pending", "as": "pending_admin"},
        {"op": "members"}, {"op": "state"},
    ])
    j = out["join"]
    check("B เข้าร่วม → ok ดึงสมาชิก 2 คน, Super Admin คือ admin1", j[0] == 200 and j[1].get("members") == 2 and j[1].get("admins") == ["admin1"], str(j))
    check("B: somchai เข้าด้วยรหัสเดิมได้ (แฮชจาก A ใช้ได้ที่ B)", out["login_somchai"][0] == 200, str(out["login_somchai"]))
    check("B: somchai เปลี่ยนรหัสตัวเอง → ขึ้นกลางได้แม้ไม่มีรหัสผู้ดูแล (ไม่ค้าง)",
          out["password"][0] == 200 and out["sync_pw"]["ok"] and not out["sync_pw"]["rejected"] and out["pending_pw"] == 0, str(out["sync_pw"]))
    check("กลาง: somchai rev=2 (รหัสเปลี่ยน) แต่ยังเป็น member", hub_members()["somchai"]["rev"] == 2 and hub_members()["somchai"]["role"] == "member")
    check("B: admin1 ของ A เข้าที่ B ได้ · สร้าง wichai/แก้ชื่อ somchai ในเครื่องได้",
          out["login_admin"][0] == 200 and out["create"][0] == 200 and out["update"][0] == 200, f"{out['login_admin']} {out['create']} {out['update']}")
    rej = {x["username"]: x["reason"] for x in (out["sync_admin"]["rejected"] or [])}
    check("B: ไม่มีรหัสผู้ดูแล → กลางปัดตกการสร้าง wichai และแก้ชื่อ somchai (reason=auth) ค้าง 2 รายการ",
          out["sync_admin"]["ok"] and rej == {"wichai": "auth", "somchai": "auth"} and out["pending_admin"] == 2, str(out["sync_admin"]))
    st = out["state"]
    check("B: แถบสถานะบอก 'รอส่ง 2' พร้อมคำอธิบายให้ใส่รหัสผู้ดูแล",
          st["last"].get("pending") == 2 and "รหัสผู้ดูแล" in st["last"].get("hint", "") and st["last"].get("admin") is False, str(st))
    hm = hub_members()
    check("กลาง: ยังไม่มี wichai · ชื่อ somchai ยังเป็นของเดิม", "wichai" not in hm and hm["somchai"]["display_name"] == "สมชาย")
    mb = {m["username"]: m for m in out["members"]}
    check("B: ในเครื่องยังมี wichai และชื่อใหม่ (ค้างไว้ ไม่หาย)", "wichai" in mb and mb["somchai"]["display_name"] == "สมชาย ใหม่")

    print("\n── เครื่อง A ซิงก์ → ได้รหัสใหม่ของ somchai · ของที่ B ถูกปัดตกไม่มาถึง ──")
    res = server._members_sync_now("test")
    s = res.get("summary") or {}
    check("A: ปรับ somchai · รหัสเปลี่ยน · ไม่มี wichai", "somchai" in s.get("updated", []) and somchai_id in s.get("password_changed", [])
          and s.get("created") == [], str(s))
    check("A: session เดิมของ somchai ถูกตัด (รหัสถูกเปลี่ยนจากเครื่องอื่น)", sc.get("/api/me").status_code == 401)
    check("A: PASSCODE ของ somchai บน A ถูกยกเลิก", db.has_passcode(somchai_id) is False)
    check("A: ชื่อที่แสดงยังเป็นของเดิม (การแก้ที่ไม่มีรหัสผู้ดูแลไม่ขึ้นกลาง)", db.get_user(somchai_id)["display_name"] == "สมชาย")
    check("A: รหัสเดิมของ somchai ใช้ไม่ได้ รหัสใหม่ใช้ได้",
          sc.post("/api/login", json={"username": "somchai", "password": "pass66"}).status_code == 401
          and sc.post("/api/login", json={"username": "somchai", "password": "newpass6"}).status_code == 200)
    sc.post("/api/logout")

    print("\n── B ใส่รหัสผู้ดูแล → รายการที่ค้างขึ้นกลาง ──")
    out = machine_b([{"op": "set_admin_token", "token": ADMIN}, {"op": "sync"}, {"op": "pending"}, {"op": "state"}])
    check("B: ใส่รหัสผู้ดูแลแล้วซิงก์ → กลางรับหมด ไม่ค้าง",
          out["sync"]["ok"] and not out["sync"]["rejected"] and out["sync"]["admin"] is True and out["pending"] == 0, str(out["sync"]))
    hm = hub_members()
    check("กลาง: มี wichai rev=1 · somchai ชื่อใหม่ rev=3", hm.get("wichai", {}).get("rev") == 1 and hm["somchai"]["display_name"] == "สมชาย ใหม่" and hm["somchai"]["rev"] == 3, str(hm.get("somchai")))
    res = server._members_sync_now("test")
    s = res.get("summary") or {}
    check("A: สร้าง wichai · ชื่อใหม่ของ somchai มาถึง", s.get("created") == ["wichai"] and db.get_user(somchai_id)["display_name"] == "สมชาย ใหม่", str(s))
    wc = server.app.test_client()
    check("A: wichai (สร้างที่ B) เข้าที่ A ได้", wc.post("/api/login", json={"username": "wichai", "password": "pass77"}).status_code == 200)
    wc.post("/api/logout")

    print("\n── ล็อกอินไม่ผ่านแล้วซิงก์อัตโนมัติ ──")
    out = machine_b([{"op": "login", "u": "admin1", "p": "secret9"},
                     {"op": "create", "u": "late", "p": "late1234", "name": "มาสาย"}, {"op": "sync"}])
    check("(เตรียม) B สร้าง late และซิงก์แล้ว", out["create"][0] == 200 and out["sync"]["ok"] and not out["sync"]["rejected"])
    server._members_sync_ts = 0.0
    lc = server.app.test_client()
    r = lc.post("/api/login", json={"username": "late", "password": "late1234"})
    check("A: บัญชีที่เพิ่งสร้างจากเครื่องอื่น เข้าได้ทันทีโดยไม่ต้องรอรอบซิงก์", r.status_code == 200 and server._members_last.get("reason") == "login", str(r.get_json()))
    lc.post("/api/logout")
    server._members_sync_ts = 0.0
    r = lc.post("/api/login", json={"username": "nobody", "password": "x"})
    check("A: ชื่อที่ไม่มีจริง → ยัง 401 (ซิงก์แล้วก็ไม่พบ)", r.status_code == 401)

    print("\n── ใช้รหัสร่วม (HUB_TOKEN) ยกระดับตัวเอง/เปลี่ยนรหัสคนอื่น → ศูนย์กลางปัดตก ──")
    hm = hub_members()
    esc = dict(hm["somchai"], role="super_admin")
    res = push_raw([esc], admin_token=None)
    check("ตั้งตัวเองเป็น super_admin ด้วยรหัสร่วม → rejected auth · กลางยังเป็น member",
          res.get("applied") == 0 and res.get("rejected") == [{"username": "somchai", "reason": "auth"}]
          and hub_members()["somchai"]["role"] == "member", str(res))
    steal = dict(hm["admin1"], password_hash="ab" * 32, salt="cd" * 16)
    res = push_raw([steal], admin_token=None)
    check("เปลี่ยนรหัสผ่านของ Super Admin ด้วยรหัสร่วม → rejected auth",
          res.get("rejected") == [{"username": "admin1", "reason": "auth"}] and hub_members()["admin1"]["password_hash"] == hm["admin1"]["password_hash"])
    res = push_raw([dict(hm["somchai"], display_name="HACK", active=0)], admin_token=None)
    check("ปิดใช้งาน/เปลี่ยนชื่อสมาชิกอื่นด้วยรหัสร่วม → rejected auth", res.get("rejected") == [{"username": "somchai", "reason": "auth"}])
    res = push_raw([{"username": "ghost", "role": "member", "password_hash": "aa" * 32, "salt": "bb" * 16, "active": 1, "rev": 0}], admin_token=None)
    check("สร้างคนใหม่ด้วยรหัสร่วม (กลางไม่ว่างแล้ว) → rejected auth", res.get("rejected") == [{"username": "ghost", "reason": "auth"}] and "ghost" not in hub_members())
    res = push_raw([esc], admin_token="wrong-admin-token-xxxxxxxx")
    check("รหัสผู้ดูแลผิด → เท่ากับไม่มี (admin=False · rejected auth)", res.get("admin") is False and res.get("rejected") == [{"username": "somchai", "reason": "auth"}])
    # สคริปต์ที่ผู้ดูแลลืมตั้ง ADMIN_TOKEN (ยังเป็นค่าตั้งต้น) — ไม่รับลายเซ็นผู้ดูแลเลย และบอกให้รู้
    body = hub.build_members_payload("raw", VER, [esc])
    res = raw_post(body, admin_token=ADMIN, script_admin="")
    check("สคริปต์ยังไม่ตั้ง ADMIN_TOKEN → admin_ready=False ปัดตกทั้งที่ลายเซ็นถูก", res.get("admin_ready") is False and res.get("admin") is False
          and res.get("rejected") == [{"username": "somchai", "reason": "auth"}], str(res)[:200])
    res = push_raw([dict(hm["somchai"], display_name="STALE", rev=1)])
    check("rev เก่า (มีคนแก้ไปก่อน) → rejected conflict แม้มีรหัสผู้ดูแล · กลางไม่เปลี่ยน",
          res.get("rejected") == [{"username": "somchai", "reason": "conflict"}] and hub_members()["somchai"]["display_name"] == "สมชาย ใหม่")

    print("\n── ศูนย์กลางไม่ยอมให้ไม่เหลือ Super Admin ──")
    hm = hub_members()
    res = push_raw([dict(hm["admin1"], active=0)])
    check("ปิด Super Admin คนเดียวที่มี → rejected last_admin", res.get("rejected") == [{"username": "admin1", "reason": "last_admin"}] and hub_members()["admin1"]["active"] == 1)
    r = c.post("/api/admin/members", json={"username": "admin2", "password": "second9", "display_name": "แอดมิน 2", "role": "super_admin"})
    check("A: สร้าง admin2 (super_admin) → ขึ้นกลาง", r.status_code == 200 and server._members_sync_now("test").get("ok") and hub_members().get("admin2", {}).get("role") == "super_admin")
    hm = hub_members()
    r1 = push_raw([dict(hm["admin2"], active=0)], install="machine-X")
    r2 = push_raw([dict(hm["admin1"], active=0)], install="machine-Y")
    check("สองเครื่องปิดกันเอง: คนแรกสำเร็จ คนหลังถูกปัดตก → เหลือ Super Admin เสมอ",
          r1.get("applied") == 1 and r2.get("rejected") == [{"username": "admin1", "reason": "last_admin"}]
          and hub_members()["admin1"]["active"] == 1 and hub_members()["admin2"]["active"] == 0, f"{r1.get('rejected')} {r2.get('rejected')}")
    res = server._members_sync_now("test")
    check("A: admin2 ถูกปิดตามกลาง · admin1 ยังใช้งานได้", "admin2" in (res.get("summary") or {}).get("updated", [])
          and db.get_user_by_username("admin2")["active"] == 0 and db.count_super_admins() == 1)
    res = push_raw([dict(hub_members()["admin2"], active=1)])
    check("(คืนค่า) เปิด admin2 กลับ", res.get("applied") == 1)

    print("\n── ลบที่ A → ปิดใช้งานที่ B (ไม่ลบประวัติ) · ป้ายหลุมศพกันสร้างซ้ำ · สร้างซ้ำหลังลบต่อ rev เดิม ──")
    admin = server.app.test_client()
    admin.post("/api/login", json={"username": "admin1", "password": "secret9"})
    wid = db.get_user_by_username("wichai")["id"]
    wrev = db.get_user_by_username("wichai")["hub_rev"]
    check("A: ลบ wichai", admin.delete(f"/api/admin/members/{wid}").status_code == 200)
    exp = {m["username"]: m for m in db.export_members()}
    check("ก้อนที่ส่งมี wichai เป็นป้ายหลุมศพ (deleted=1, rev เดิม) ไม่ใช่แถวบัญชี",
          list(exp) == ["wichai"] and exp["wichai"]["deleted"] == 1 and not exp["wichai"]["password_hash"] and exp["wichai"]["rev"] == wrev, str(exp))
    check("A: ซิงก์หลังลบ → กลางจดว่าลบ", server._members_sync_now("test").get("ok") is True and hub_members()["wichai"]["deleted"] == 1)
    out = machine_b([{"op": "sync"}, {"op": "members"}, {"op": "login", "u": "wichai", "p": "pass77"}])
    mb = {m["username"]: m for m in out["members"]}
    check("B: wichai ถูกปิดใช้งาน (ยังอยู่ในรายชื่อ ไม่ถูกลบ) และเข้าไม่ได้",
          mb.get("wichai", {}).get("active") == 0 and out["login"][0] == 401 and out["sync"]["summary"]["deactivated"] == ["wichai"], str(out))
    check("A: ซิงก์อีกรอบ wichai ไม่ถูกสร้างกลับมา (ป้ายหลุมศพ)",
          server._members_sync_now("test").get("ok") and db.get_user_by_username("wichai") is None)
    r = admin.post("/api/admin/members", json={"username": "wichai", "password": "again88", "display_name": "วิชัย กลับมา", "role": "member"})
    res = server._members_sync_now("test")
    check("A: สร้าง wichai ใหม่หลังลบ → ต่อจาก rev ของป้ายหลุมศพ กลางรับ (ไม่ conflict)",
          r.status_code == 200 and res.get("ok") and not res.get("rejected") and hub_members()["wichai"]["deleted"] == 0, str(res.get("rejected")))
    out = machine_b([{"op": "sync"}, {"op": "user", "u": "wichai"}, {"op": "login", "u": "wichai", "p": "again88"}])
    check("B: wichai กลับมาใช้งานได้ด้วยรหัสใหม่", out["user"]["active"] == 1 and out["login"][0] == 200, str(out))

    print("\n── ลำดับตัดสินโดยศูนย์กลาง (rev) ไม่ใช่นาฬิกาเครื่อง ──")
    out = machine_b([{"op": "login", "u": "admin1", "p": "secret9"},
                     {"op": "update", "u": "somchai", "fields": {"display_name": "ชื่อจาก B"}},
                     {"op": "touch", "u": "somchai", "at": "2099-12-31T23:59:59"}])
    check("(เตรียม) B แก้ชื่อ somchai แต่ยังไม่ซิงก์ · นาฬิกา B อยู่ปี 2099", out["update"][0] == 200 and out["touch"])
    check("A: แก้ชื่อ somchai แล้วซิงก์ก่อน → กลางรับของ A",
          admin.put(f"/api/admin/members/{somchai_id}", json={"display_name": "ชื่อจาก A"}).status_code == 200
          and server._members_sync_now("test").get("ok") and hub_members()["somchai"]["display_name"] == "ชื่อจาก A")
    out = machine_b([{"op": "sync"}, {"op": "user", "u": "somchai"}, {"op": "pending"}])
    check("B: ซิงก์ทีหลัง → conflict ของกลางชนะ แม้เวลาเครื่อง B 'ใหม่กว่า' · ของ B ถูกทับและไม่ค้าง",
          out["sync"]["rejected"] == [{"username": "somchai", "reason": "conflict"}] and out["sync"]["summary"]["reverted"] == ["somchai"]
          and out["user"]["display_name"] == "ชื่อจาก A" and out["pending"] == 0, str(out))
    hm = hub_members()
    check("กลาง: somchai ชื่อจาก A · rev เพิ่มทีละ 1 ตามจำนวนครั้งที่รับจริง", hm["somchai"]["display_name"] == "ชื่อจาก A" and hm["somchai"]["rev"] == 4, str(hm["somchai"]))

    print("\n── endpoint หน้าสมาชิก / ตั้งค่า ──")
    st = admin.get("/api/hub/members/state").get_json()
    check("สถานะซิงก์: เปิดอยู่ + รอบล่าสุดสำเร็จ + ไม่ค้าง", st.get("enabled") is True and st["last"].get("ok") is True and st["last"].get("pending") == 0, str(st))
    r = admin.post("/api/hub/members/sync")
    check("ปุ่มซิงก์เดี๋ยวนี้ → ok + สรุป", r.status_code == 200 and r.get_json().get("ok") is True and "summary" in r.get_json(), r.get_data(as_text=True)[:160])
    hs = admin.get("/api/hub/state").get_json()
    check("หน้าตั้งค่าเห็นผลซิงก์ · รายการฟิลด์ที่ส่ง (มี rev) · เครื่องนี้มีรหัสผู้ดูแล (ไม่ส่งค่าจริงกลับมา)",
          hs.get("members", {}).get("ok") is True and hs.get("member_fields") == list(hub.MEMBER_FIELDS) and "rev" in hs["member_fields"]
          and hs.get("has_admin_token") is True and ADMIN not in json.dumps(hs), str(hs)[:200])
    r = admin.post("/api/hub/config", json={"admin_token": ""})
    check("ถอดรหัสผู้ดูแลออกจากเครื่อง → has_admin_token=False", r.status_code == 200 and admin.get("/api/hub/state").get_json().get("has_admin_token") is False)
    r = admin.put(f"/api/admin/members/{somchai_id}", json={"display_name": "ชื่อ A2"})
    res = server._members_sync_now("test")
    check("A ไม่มีรหัสผู้ดูแลแล้ว → แก้ชื่อค้างส่ง + คำอธิบาย", res.get("rejected") == [{"username": "somchai", "reason": "auth"}]
          and server._members_last["pending"] == 1 and "รหัสผู้ดูแล" in server._members_last["hint"], str(server._members_last))
    r = admin.post("/api/hub/config", json={"admin_token": ADMIN})
    res = server._members_sync_now("test")
    check("ใส่รหัสผู้ดูแลกลับ → รายการค้างขึ้นกลาง", r.status_code == 200 and res.get("ok") and not res.get("rejected")
          and server._members_last["pending"] == 0 and hub_members()["somchai"]["display_name"] == "ชื่อ A2")
    mc = server.app.test_client()
    mc.post("/api/login", json={"username": "somchai", "password": "newpass6"})
    check("สมาชิกธรรมดาเรียกซิงก์ไม่ได้ (403)", mc.post("/api/hub/members/sync").status_code == 403)
    check("สมาชิกธรรมดาใส่รหัสผู้ดูแลไม่ได้ (403)", mc.post("/api/hub/config", json={"admin_token": "x"}).status_code == 403)

    print("\n── ความทนทานของ apply_remote_members ──")
    s = db.apply_remote_members([{"username": "nohash", "role": "member", "rev": 1},
                                 {"username": "weird", "role": "god", "permissions": {"view_team": True, "bogus": True},
                                  "password_hash": "aa" * 32, "salt": "bb" * 16, "active": "1", "rev": "7"}])
    w = db.get_user_by_username("weird")
    check("แถวไม่มีแฮช → ข้าม · บทบาทแปลก → member · สิทธิ์ dict → เก็บเฉพาะคีย์ที่รู้จัก · rev ข้อความ → ตัวเลข",
          s["created"] == ["weird"] and db.get_user_by_username("nohash") is None and w["role"] == "member"
          and json.loads(w["permissions"]) == {"view_team": True} and w["hub_rev"] == 7 and w["sync_dirty"] == 0, str(s))
    admin2_id = db.get_user_by_username("admin2")["id"]
    db.update_user(admin2_id, active=0)                 # ให้เครื่องนี้เหลือ Super Admin ที่เปิดใช้งานคนเดียว
    s = db.apply_remote_members([{"username": "admin1", "role": "member", "active": 1, "rev": 99,
                                  "password_hash": "aa" * 32, "salt": "bb" * 16}])
    check("ไดเรกทอรีที่ไม่มี Super Admin คนอื่นจะลดขั้น Super Admin คนสุดท้ายของเครื่องไม่ได้ (skipped)",
          s["skipped"] == ["admin1"] and db.get_user_by_username("admin1")["role"] == "super_admin", str(s))
    db.update_user(admin2_id, active=1)

    print("\n── หน้าจอ ──")
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าตั้งค่ามีโหมด 'เครื่องแรก/เครื่องเพิ่มเติม' + ฟอร์มเข้าร่วม + ช่องรหัสผู้ดูแลตอนสมัคร",
          all(k in html for k in ('id="setupModeBar"', 'id="authJoinForm"', 'id="joinHubCode"', "/api/setup/join", 'id="suHubAdmin"', "hub_admin_token")))
    check("หน้าสมาชิกมีแถบสถานะซิงก์ + ปุ่มซิงก์เดี๋ยวนี้ + แสดงรายการรอส่ง",
          all(k in html for k in ('id="memberSyncBar"', 'id="btnMemberSync"', "/api/hub/members/state", "/api/hub/members/sync", "รอส่ง")))
    check("หน้าตั้งค่าศูนย์กลางมีช่องรหัสผู้ดูแล + ปุ่มถอด", all(k in html for k in ('id="hubAdminToken"', 'id="btnHubAdminClear"', "admin_token")))
    gas = (HERE.parent / "tools" / "hub_gas.js").read_text(encoding="utf-8")
    check("hub_gas.js มีชีต members · ADMIN_TOKEN · rev · กติกา last_admin/conflict/auth · คำเตือนวิธี Deploy",
          all(k in gas for k in ("MEMBERS_SHEET", "_syncMembers", "ADMIN_TOKEN", "'rev'", "last_admin", "conflict", "'auth'", "New version")))

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
