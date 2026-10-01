#!/usr/bin/env python3
"""v3.10.0 — สมัครใช้งานเอง → Super Admin อนุมัติและให้สิทธิ์ · URL ศูนย์กลางฝังในโปรแกรม · เปิดครั้งแรกดึงไดเรกทอรีก่อน seed

ผู้ใช้สั่ง: "แก้ไขโครงสร้างระบบสมาชิก ให้เป็นการสมัครและได้รับการอนุญาตใช้งานและสิทธิ์จาก Superadmin เท่านั้น
            การติดตั้งเสร็จแล้ว ในหน้าการเข้าใช้งานให้มีปุ่มสมัครใช้งาน และใส่ URL กลางฝังไว้ …/exec"
  เครื่อง A = Super Admin (โปรเซสนี้) · เครื่อง B = เครื่องใหม่ (โปรเซสแยก) · ศูนย์กลาง = hub_gas.js ตัวจริงบน Node
  • B ยังไม่มีสมาชิก/รหัสลับ → หน้าเข้าสู่ระบบมีสมัครใช้งาน (ต้องกรอกรหัสเชื่อมต่อครั้งแรก) → คำขอขึ้นกลางด้วยรหัสร่วม (pending)
  • B ล็อกอินก่อนอนุมัติ → 403 'รออนุมัติ' (เฉพาะรหัสถูก) · A เห็นคำขอ (ป้ายบนเมนู) → อนุมัติพร้อมสิทธิ์ → B เข้าได้ทันที
  • ปฏิเสธ = ลบ → เครื่องผู้สมัครปิดใช้งาน · ศูนย์กลางไม่รับคำขอที่แอบใส่บทบาท/สิทธิ์/active · ผู้จัดการสมาชิกอนุมัติไม่ได้
  • URL ฝัง: config ใหม่/เก่าที่ว่าง → DEFAULT_HUB_URL · hub_seed.json จากชุดติดตั้ง → เชื่อมเอง
  • เปิดครั้งแรกกับ seed_account.json: องค์กรมีสมาชิกแล้ว → ไม่สร้าง Super Admin ซ้ำ · ติดต่อกลางไม่ได้ → เก็บ seed ไว้ก่อน
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v3100_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "A")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "A_up")
from _app import APP  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)
import config  # noqa: E402

# ไฟล์ seed ค้างจากการรันครั้งก่อนที่ล้ม (ทั้งคู่วางในโฟลเดอร์แอป) — ต้องเก็บกวาดก่อน import server (v3.10.0 server ใช้ตั้งแต่ import)
for _n in ("seed_account.json", config.HUB_SEED_FILE_NAME):
    (config.BASE_DIR / _n).unlink(missing_ok=True)

from backend import server  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = TEST_DATA / "hub_sheet.json"
TOKEN = "test-hub-token-0123456789"
ADMIN = "test-admin-token-9876543210"
URL = "https://script.google.com/macros/s/TEST/exec"
VER = "3.10.0"
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def raw_post(payload, tok=TOKEN, admin_token=None, script_admin=ADMIN, state=None):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    param = {"sign": hub.sign(body.encode("utf-8"), tok)}
    if admin_token:
        param["asign"] = hub.sign(body.encode("utf-8"), admin_token)
    req = {"method": "POST", "body": body, "parameter": param}
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(state or STATE), TOKEN, script_admin],
                       input=json.dumps(req), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def fake_post(url, payload, tok, admin_token=None):
    return raw_post(payload, tok, admin_token)


def machine_b(cmds, data="B"):
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / data), CRIMES_UPLOAD_DIR=str(TEST_DATA / (data + "_up")),
               PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / data), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(cmds), env=env, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise RuntimeError("machine B: " + r.stderr[-800:])
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def hub_members():
    res = hub.sync_members(URL, TOKEN, "probe", VER, [])
    return {m["username"]: m for m in res.get("members", [])}


def push_raw(rows, admin_token=None, install="raw"):
    return hub.sync_members(URL, TOKEN, install, VER, rows, admin_token=admin_token)


def main():
    check("มี Node สำหรับรันสคริปต์ศูนย์กลางตัวจริง", shutil.which("node") is not None)
    server.hub._post = fake_post
    server._hub_kick = lambda *a, **k: None
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    code = hub.make_connect_code(URL, TOKEN)

    print("── URL ศูนย์กลางฝังมากับโปรแกรม ──")
    check("config ใหม่มี hub_url = URL ที่ฝัง (ยังไม่เปิดใช้จนกว่าจะมีรหัสลับ)",
          auth._default_config()["hub_url"] == config.DEFAULT_HUB_URL and config.DEFAULT_HUB_URL.endswith("/exec")
          and auth.load_config().get("hub_url") == config.DEFAULT_HUB_URL and auth.load_config().get("hub_enabled") is False)
    auth.update_config(hub_url="")
    check("config รุ่นก่อนที่ URL ว่าง → เติม URL ที่ฝังให้ (ไม่แตะที่ตั้งเอง)", auth.load_config().get("hub_url") == config.DEFAULT_HUB_URL)
    st = c.get("/api/auth/state").get_json()
    check("auth/state: ยังไม่ตั้งค่า · hub ยังไม่เชื่อม (ไม่มีรหัสลับ) · สมัครต้องกรอกรหัสเชื่อมต่อ · บอก URL ฝัง",
          st["configured"] is False and st["hub"]["connected"] is False and st["register_needs_token"] is True
          and st["hub"]["default_url"] == config.DEFAULT_HUB_URL, str(st))

    print("\n── เครื่อง A: Super Admin (เครื่องแรก) ──")
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน", "hub_code": code, "hub_admin_token": ADMIN})
    check("สมัครเครื่องแรกพร้อมรหัสเชื่อมต่อ+รหัสผู้ดูแล → Super Admin ขึ้นกลาง", r.status_code == 200 and "admin1" in hub_members())
    c.post("/api/admin/members", json={"username": "manager", "password": "pass77", "display_name": "ผู้จัดการ", "role": "member",
                                       "permissions": {"manage_members": True}})
    check("(เตรียม) ผู้จัดการสมาชิก (ไม่ใช่ Super Admin) ขึ้นกลาง", server._members_sync_now("test").get("ok") and "manager" in hub_members())

    print("\n── เครื่อง B: ติดตั้งใหม่ ยังไม่มีอะไร → สมัครใช้งานจากหน้าเข้าสู่ระบบ ──")
    out = machine_b([
        {"op": "auth_state", "as": "st0"},
        {"op": "register", "u": "somchai", "p": "pass66", "name": "สมชาย", "as": "reg_nocode"},
        {"op": "register", "u": "somchai", "p": "pass66", "name": "สมชาย", "code": "CRIMES-HUB:zzz", "as": "reg_badcode"},
        {"op": "register", "u": "so", "p": "pass66", "code": code, "as": "reg_short"},
        {"op": "register", "u": "somchai", "p": "pass66", "p2": "other", "code": code, "as": "reg_mismatch"},
        {"op": "register", "u": "somchai", "p": "pass66", "name": "สมชาย", "code": code, "as": "reg_ok"},
        {"op": "auth_state", "as": "st1"},
        {"op": "register", "u": "somchai", "p": "pass66", "as": "reg_dup"},
        {"op": "login_full", "u": "somchai", "p": "pass66", "as": "login_pending"},
        {"op": "login_full", "u": "somchai", "p": "wrong", "as": "login_wrongpw"},
        {"op": "sync", "as": "sync0"}, {"op": "members", "as": "members0"},
    ])
    check("B: ยังไม่ตั้งค่า + ยังไม่มีรหัสลับ → หน้าเข้าสู่ระบบบอกให้กรอกรหัสเชื่อมต่อตอนสมัคร",
          out["st0"]["configured"] is False and out["st0"]["register_needs_token"] is True)
    check("B: สมัครโดยไม่ใส่รหัสเชื่อมต่อ → 400 need_hub_code · รหัสผิด → 400", out["reg_nocode"][0] == 400 and out["reg_nocode"][1].get("need_hub_code") is True
          and out["reg_badcode"][0] == 400, f"{out['reg_nocode']} {out['reg_badcode']}")
    check("B: ชื่อสั้น/รหัสไม่ตรง → 400", out["reg_short"][0] == 400 and out["reg_mismatch"][0] == 400)
    check("B: สมัครพร้อมรหัสเชื่อมต่อ → ok pending · เครื่องเชื่อมศูนย์กลาง + ได้ไดเรกทอรีทันที (ตรวจรหัสก่อนรับคำขอ)",
          out["reg_ok"][0] == 200 and out["reg_ok"][1].get("pending") is True and out["st1"]["hub"]["connected"] is True
          and out["st1"]["register_needs_token"] is False and out["st1"]["configured"] is True, str(out["st1"]))
    check("B: สมัครชื่อซ้ำ (คำขอเดิมยังรอ) → 400 'รอ Super Admin อนุมัติ'",
          out["reg_dup"][0] == 400 and "รอ Super Admin" in out["reg_dup"][1].get("error", ""), str(out["reg_dup"]))
    check("B: ล็อกอินก่อนอนุมัติ (รหัสถูก) → 403 'รออนุมัติ' · รหัสผิด → 401 ธรรมดา (ไม่เผยว่ามีคำขอ)",
          out["login_pending"][0] == 403 and out["login_pending"][1].get("pending") is True and "อนุมัติ" in out["login_pending"][1].get("error", "")
          and out["login_wrongpw"][0] == 401, f"{out['login_pending']} {out['login_wrongpw']}")
    hm = hub_members()
    check("B: ซิงก์ด้วยรหัสร่วม (ไม่มีรหัสผู้ดูแล) → กลางรับคำขอ pending=1 active=0 role=member ไม่มีสิทธิ์ · ไม่ค้าง",
          out["sync0"]["ok"] and not out["sync0"]["rejected"] and hm.get("somchai", {}).get("pending") == 1
          and hm["somchai"]["active"] == 0 and hm["somchai"]["role"] == "member" and hm["somchai"]["permissions"] in ("{}", "null"), str(out["sync0"]))
    mb = {m["username"]: m for m in out["members0"]}
    check("B: ได้ไดเรกทอรีทั้งองค์กรมาด้วย (admin1, manager) แต่ยังเข้าไม่ได้จนกว่าจะอนุมัติ", "admin1" in mb and "manager" in mb)

    print("\n── เครื่อง A: เห็นคำขอ → อนุมัติพร้อมสิทธิ์ ──")
    res = server._members_sync_now("test")
    s = res.get("summary") or {}
    check("A: ซิงก์ → คำขอ somchai มาถึง (summary.requests) pending=1 active=0",
          s.get("requests") == ["somchai"] and db.get_user_by_username("somchai")["pending"] == 1 and db.get_user_by_username("somchai")["active"] == 0, str(s))
    me = c.get("/api/me").get_json()
    check("A: /api/me บอก pending_requests=1 · auth/state บอก pending_users=1 · configured=True (คำขอไม่นับ)",
          me.get("pending_requests") == 1 and c.get("/api/auth/state").get_json().get("pending_users") == 1
          and db.has_any_user() and c.get("/api/auth/state").get_json()["configured"] is True, str(me.get("pending_requests")))
    sid = db.get_user_by_username("somchai")["id"]
    mc = server.app.test_client()
    mc.post("/api/login", json={"username": "manager", "password": "pass77"})
    check("ผู้จัดการสมาชิก (ไม่ใช่ Super Admin) อนุมัติ/แก้/ลบคำขอไม่ได้ (403)",
          mc.post(f"/api/admin/members/{sid}/approve", json={}).status_code == 403
          and mc.put(f"/api/admin/members/{sid}", json={"display_name": "x"}).status_code == 403
          and mc.delete(f"/api/admin/members/{sid}").status_code == 403)
    check("PUT active=1 บนคำขอ → 400 (ต้องใช้ปุ่มอนุมัติ)", c.put(f"/api/admin/members/{sid}", json={"active": True}).status_code == 400)
    r = c.post(f"/api/admin/members/{sid}/approve", json={"permissions": {"view_team": True}, "rate_per_name": 4, "display_name": "สมชาย ใจดี"})
    u = db.get_user_by_username("somchai")
    check("Super Admin อนุมัติ → pending=0 active=1 สิทธิ์/อัตรา/ชื่อตามที่กำหนด · audit member_approve",
          r.status_code == 200 and u["pending"] == 0 and u["active"] == 1 and db.get_permissions(sid).get("view_team") is True
          and u["rate_per_name"] == 4 and u["display_name"] == "สมชาย ใจดี"
          and any(a.get("action") == "member_approve" for a in db.get_audit_log(20)), r.get_data(as_text=True)[:120])
    check("อนุมัติซ้ำ → 400", c.post(f"/api/admin/members/{sid}/approve", json={}).status_code == 400)
    res = server._members_sync_now("test")
    hm = hub_members()
    check("A: ซิงก์ → กลางบันทึกการอนุมัติ (rev+1 · active=1 · pending=0 · สิทธิ์)", res.get("ok") and not res.get("rejected")
          and hm["somchai"]["pending"] == 0 and hm["somchai"]["active"] == 1 and "view_team" in hm["somchai"]["permissions"], str(res.get("rejected")))
    check("A: pending_requests กลับเป็น 0", c.get("/api/me").get_json().get("pending_requests") == 0)
    out = machine_b([{"op": "sync", "as": "sync1"}, {"op": "login_full", "u": "somchai", "p": "pass66", "as": "login_ok"},
                     {"op": "me"}, {"op": "auth_state"}])
    check("B: ซิงก์ → ได้อนุมัติ (summary.approved) → เข้าสู่ระบบด้วยชื่อ/รหัสที่ตั้งเองได้ · เครื่องถือว่าตั้งค่าแล้ว",
          out["sync1"]["summary"]["approved"] == ["somchai"] and out["login_ok"][0] == 200 and out["me"][1] == "somchai"
          and out["auth_state"]["configured"] is True, str(out["sync1"]["summary"]))

    print("\n── ปฏิเสธคำขอ ──")
    out = machine_b([{"op": "register", "u": "spammer", "p": "pass66", "as": "reg"}, {"op": "sync"}])
    check("B: สมัครอีกคน (เครื่องมีรหัสลับแล้ว ไม่ต้องกรอกรหัสเชื่อมต่อ) → ขึ้นกลาง", out["reg"][0] == 200 and hub_members().get("spammer", {}).get("pending") == 1)
    server._members_sync_now("test")
    spid = db.get_user_by_username("spammer")["id"]
    r = c.delete(f"/api/admin/members/{spid}")
    check("A: ปฏิเสธ (ลบ) → audit member_reject · ขึ้นกลางเป็นแถวลบ", r.status_code == 200 and any(a.get("action") == "member_reject" for a in db.get_audit_log(20))
          and server._members_sync_now("test").get("ok") and hub_members()["spammer"]["deleted"] == 1)
    out = machine_b([{"op": "sync"}, {"op": "login_full", "u": "spammer", "p": "pass66", "as": "login"}, {"op": "user", "u": "spammer"},
                     {"op": "clear_throttle"}, {"op": "register", "u": "spammer", "p": "pass66", "as": "reg_again"},
                     {"op": "register", "u": "spammer2", "p": "pass66", "as": "reg_more"}])
    check("B: คำขอที่ถูกปฏิเสธ → ปิดใช้งาน เข้าไม่ได้ (401 ธรรมดา) · สมัครชื่อเดิมซ้ำไม่ได้ (ให้ติดต่อ Super Admin)",
          out["login"][0] == 401 and out["user"]["active"] == 0 and out["sync"]["summary"]["deactivated"] == ["spammer"]
          and out["reg_again"][0] == 400 and "Super Admin" in out["reg_again"][1].get("error", ""), str(out))
    check("B: สมัครสำเร็จก็นับเข้าตัวหน่วงต่อเครื่อง (เกิน 4 ครั้ง → 429 กันสแปมคำขอ)", out["reg_more"][0] == 200)
    out = machine_b([{"op": "register", "u": f"spam{i}", "p": "pass66", "as": f"r{i}"} for i in range(4)])
    check("B: สมัครครั้งที่ 5 ในช่วงเดียวกัน → 429", [out[f"r{i}"][0] for i in range(4)] == [200, 200, 200, 429], str(out))

    print("\n── องค์กรมีสมาชิกแล้ว → เครื่องใหม่ตั้งตัวเองเป็น Super Admin ไม่ได้ (สิทธิ์ต้องมาจาก Super Admin เท่านั้น) ──")
    code = hub.make_connect_code(URL, TOKEN)
    out = machine_b([{"op": "register", "u": "gguest", "p": "pass66", "code": code, "as": "reg"},
                     {"op": "post", "path": "/api/setup", "json": {"username": "rogue", "password": "secret9", "password2": "secret9"}, "as": "own"},
                     {"op": "user", "u": "rogue"}, {"op": "auth_state"}], data="G")
    check("เครื่อง G (สมัครไว้): ได้ไดเรกทอรีมาแล้ว (configured) → /api/setup ถูกปิด (400) ไม่สร้างบัญชี rogue",
          out["reg"][0] == 200 and out["own"][0] == 400 and out["user"] is None
          and out["auth_state"]["configured"] is True, str(out["own"]))
    out = machine_b([{"op": "post", "path": "/api/setup", "json": {"username": "rogue", "password": "secret9", "password2": "secret9", "hub_code": code}, "as": "code"},
                     {"op": "post", "path": "/api/setup", "json": {"username": "rogue", "password": "secret9", "password2": "secret9", "hub_code": code,
                                                                  "hub_admin_token": "wrong-admin-token"}, "as": "badadm"},
                     {"op": "user", "u": "rogue"}, {"op": "auth_state"}], data="F")
    check("เครื่องใหม่ F: 'เครื่องแรกขององค์กร' + รหัสเชื่อมต่อ → 400 org_exists (รหัสผู้ดูแลผิดก็ไม่ผ่าน) · ยังไม่ผูกศูนย์กลาง ไม่สร้างบัญชี",
          out["code"][0] == 400 and out["code"][1].get("org_exists") is True and out["badadm"][0] == 400 and out["user"] is None
          and out["auth_state"]["hub"]["connected"] is False and "rogue" not in hub_members(), str(out))
    out = machine_b([{"op": "post", "path": "/api/setup", "json": {"username": "admin2", "password": "secret9", "password2": "secret9", "hub_code": code,
                                                                  "hub_admin_token": ADMIN}, "as": "adm"}, {"op": "user", "u": "admin2"}], data="F")
    check("เครื่องใหม่ F: ถือรหัสผู้ดูแลตัวจริง (Super Admin ขององค์กรเอง) → สร้างได้ · ขึ้นกลางเป็น super_admin",
          out["adm"][0] == 200 and out["user"] and out["user"]["role"] == "super_admin"
          and hub_members().get("admin2", {}).get("role") == "super_admin", str(out))

    print("\n── ศูนย์กลางรับเฉพาะ 'คำขอสมัคร' จากรหัสร่วม — แอบใส่อะไรเพิ่มไม่ได้ ──")
    base = {"display_name": "x", "password_hash": "ab" * 32, "salt": "cd" * 16, "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00", "deleted": 0, "rev": 0, "teams": "[]", "pending": 1, "active": 0, "role": "member", "permissions": "{}"}
    tries = [("ตั้งตัวเองเป็น super_admin", dict(base, username="evil1", role="super_admin")),
             ("แอบเปิดใช้งาน (active=1)", dict(base, username="evil2", active=1)),
             ("แอบใส่สิทธิ์", dict(base, username="evil3", permissions='{"manage_members":true}')),
             ("แอบใส่ทีม", dict(base, username="evil4", teams='[["ทีม A",null]]')),
             ("ไม่ pending (สร้างสมาชิกจริงตรง ๆ)", dict(base, username="evil5", pending=0)),
             ("แอบใส่อัตรา", dict(base, username="evil6", rate_per_name=9))]
    for label, row in tries:
        res = push_raw([row])
        check(f"รหัสร่วม: {label} → rejected auth", res.get("rejected") == [{"username": row["username"], "reason": "auth"}] and row["username"] not in hub_members(), str(res.get("rejected")))
    res = push_raw([dict(base, username="good1")])
    check("รหัสร่วม: คำขอสมัครที่ถูกต้อง → รับ (pending)", res.get("applied") == 1 and hub_members()["good1"]["pending"] == 1)
    res = push_raw([dict(hub_members()["good1"], pending=0, active=1)])
    check("รหัสร่วม: อนุมัติเอง (pending→0 active→1) → rejected auth", res.get("rejected") == [{"username": "good1", "reason": "auth"}] and hub_members()["good1"]["pending"] == 1)
    res = push_raw([dict(hub_members()["good1"], password_hash="ef" * 32, salt="12" * 16)])
    check("รหัสร่วม: เปลี่ยนรหัสของคำขอที่ยังไม่อนุมัติ → rejected auth (self-service เฉพาะสมาชิกที่อนุมัติแล้ว)",
          res.get("rejected") == [{"username": "good1", "reason": "auth"}])
    res = push_raw([dict(hub_members()["good1"], pending=0, active=1, permissions='{"view_team":true}')], admin_token=ADMIN)
    check("รหัสผู้ดูแล: อนุมัติได้", res.get("applied") == 1 and hub_members()["good1"]["active"] == 1 and hub_members()["good1"]["pending"] == 0)
    many = [dict(base, username=f"bulk{i:03d}") for i in range(205)]
    res = push_raw(many)
    reasons = {}
    for x in res.get("rejected", []):
        reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
    n_pending = sum(1 for m in hub_members().values() if m.get("pending") and not m.get("deleted"))
    check("จำกัดคำขอค้าง 200 → ส่วนเกินถูกปัดตก reason 'full' (กันคนนอกยิงคำขอปลอมจนชีตบวม)",
          reasons.get("full", 0) >= 5 and n_pending == 200, f"{reasons} pending={n_pending}")
    res = push_raw([dict(base, username="stale", pending=1)])
    check("เต็มแล้วคำขอใหม่ก็ full · โปรแกรมเก็บไว้ค้างส่ง (pending นับใน REJECT_REASONS)", res.get("rejected") == [{"username": "stale", "reason": "full"}] and "full" in hub.REJECT_REASONS)

    print("\n── เปิดโปรแกรมครั้งแรกกับไฟล์ seed จากชุดติดตั้ง ──")
    import hashlib
    seed_path = config.BASE_DIR / db.SEED_FILE_NAME
    hub_seed_path = config.BASE_DIR / config.HUB_SEED_FILE_NAME

    def write_seed():
        salt = "ab" * 16
        seed_path.write_text(json.dumps({"username": "Superadmin", "display_name": "Super Admin", "salt": salt,
                                         "password_hash": hashlib.pbkdf2_hmac("sha256", b"seed-pw-test", bytes.fromhex(salt), db._ITERATIONS).hex()}),
                             encoding="utf-8")

    # เครื่อง C: ติดตั้งใหม่ องค์กรมีสมาชิกแล้ว — hub_seed.json ให้รหัสลับ · seed_account.json ต้องไม่ถูกใช้
    write_seed()
    hub_seed_path.write_text(json.dumps({"token": TOKEN}), encoding="utf-8")
    out = machine_b([{"op": "auth_state"}, {"op": "members"}, {"op": "user", "u": "Superadmin"}], data="C")
    check("เครื่อง C: hub_seed.json → เชื่อมศูนย์กลางเอง · ดึงไดเรกทอรีมา (admin1 อยู่) · ไม่สร้าง 'Superadmin' จาก seed · ไฟล์ seed ทั้งสองถูกลบ",
          out["auth_state"]["hub"]["connected"] is True and out["auth_state"]["configured"] is True
          and any(m["username"] == "admin1" for m in out["members"]) and out["user"] is None
          and not seed_path.exists() and not hub_seed_path.exists(), str(out["auth_state"]))
    # เครื่อง D: ติดต่อศูนย์กลางไม่สำเร็จ (ศูนย์กลางจำลองไม่สนใจ URL — จึงจำลองด้วยรหัสลับผิด → ศูนย์กลางตอบ ok:false)
    write_seed()
    hub_seed_path.write_text(json.dumps({"token": "wrong-hub-token-000000"}), encoding="utf-8")
    out = machine_b([{"op": "auth_state"}, {"op": "user", "u": "Superadmin"}], data="D")
    check("เครื่อง D: ติดต่อศูนย์กลางไม่สำเร็จ → ยังไม่สร้างบัญชีเริ่มต้น (seed เก็บไว้รอบหน้า) · หน้าจอมีสมัครใช้งาน (hub connected)",
          out["user"] is None and seed_path.exists() and out["auth_state"]["hub"]["connected"] is True and out["auth_state"]["configured"] is False, str(out))
    seed_path.unlink(missing_ok=True)
    # เครื่องแรกขององค์กร (ศูนย์กลางว่าง) → seed สร้าง Super Admin ตามเดิม
    empty_state = TEST_DATA / "hub_empty.json"
    write_seed()
    hub_seed_path.write_text(json.dumps({"token": TOKEN}), encoding="utf-8")
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / "E"), CRIMES_UPLOAD_DIR=str(TEST_DATA / "E_up"), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / "E"), str(empty_state), TOKEN, ADMIN],
                       input=json.dumps([{"op": "user", "u": "Superadmin"}, {"op": "auth_state"}, {"op": "login_full", "u": "Superadmin", "p": "seed-pw-test"}]),
                       env=env, capture_output=True, text=True, timeout=180)
    out = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])
    check("เครื่องแรกขององค์กร (ศูนย์กลางว่าง): seed สร้าง Super Admin · เข้าด้วยรหัสเริ่มต้นได้ · ไฟล์ถูกลบ",
          out["user"] and out["user"]["role"] == "super_admin" and out["login_full"][0] == 200 and not seed_path.exists(), str(out))
    check("hub_seed.json เสีย → ลบทิ้ง ไม่เชื่อม", (hub_seed_path.write_text("{bad", encoding="utf-8") or True)
          and server._consume_hub_seed() is False and not hub_seed_path.exists())

    print("\n── ฝังรหัสลับ (เจ้าของสั่ง) · สวิตช์เริ่มอัตโนมัติ · จดจำการเข้าใช้งาน · อนุมัติเฉพาะเครื่องผู้จัดการ ──")
    src_cfg = (APP / "backend" / "config.py").read_text(encoding="utf-8")
    check("รหัสลับศูนย์กลางฝังใน config.py พร้อมช่องปิดสำหรับชุดทดสอบ (CRIMES_NO_DEFAULT_HUB)",
          "DEFAULT_HUB_TOKEN" in src_cfg and "CRIMES_NO_DEFAULT_HUB" in src_cfg)
    env2 = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / "tok"), CRIMES_UPLOAD_DIR=str(TEST_DATA / "tok_up"))
    env2.pop("CRIMES_NO_DEFAULT_HUB", None)
    code_py = ("import sys, json;"
               f"sys.path.insert(0, {json.dumps(str(APP))}); sys.path.insert(0, {json.dumps(str(APP / 'backend'))});"
               "import config, auth; cfg = auth.load_config();"
               "print(int(bool(config.DEFAULT_HUB_TOKEN) and len(config.DEFAULT_HUB_TOKEN) >= 16),"
               " int(cfg['hub_token'] == config.DEFAULT_HUB_TOKEN and cfg['hub_enabled'] is True"
               " and cfg['hub_url'] == config.DEFAULT_HUB_URL and int(cfg['hub_interval_min']) == 1));"
               # v3.10.1: เครื่องที่ยังชี้ URL เก่าขององค์กร → ย้ายไปตัวใหม่ให้เอง (รหัสลับคงเดิม)
               "auth.update_config(hub_url=config.OLD_HUB_URLS[0]);"
               "print(int(auth.load_config()['hub_url'] == config.DEFAULT_HUB_URL));"
               "auth.update_config(hub_url=config.OLD_HUB_URLS[-1]);"
               "print(int(auth.load_config()['hub_url'] == config.DEFAULT_HUB_URL));"
               # ศูนย์กลางอื่นที่ตั้งเอง — ห้ามแตะทั้ง URL และห้ามยัดรหัสฝังให้
               "auth.update_config(hub_url='https://script.google.com/macros/s/CUSTOM/exec', hub_token='my-own-token-123456');"
               "c2 = auth.load_config();"
               "print(int(c2['hub_url'].endswith('/CUSTOM/exec') and c2['hub_token'] == 'my-own-token-123456'))")
    r2 = subprocess.run([sys.executable, "-c", code_py], env=env2, capture_output=True, text=True, timeout=60)
    check("เครื่องจริง (ไม่มี env ทดสอบ): รหัสลับฝัง+ซิงก์ 1 นาที · URL เก่าทั้งสองถูกย้ายไปตัวใหม่ · URL ที่ตั้งเองไม่ถูกแตะ",
          r2.stdout.split() == ["1", "1", "1", "1", "1"], (r2.stdout + r2.stderr)[-300:])
    src_desk = (APP / "desktop.py").read_text(encoding="utf-8")
    check("จดจำการเข้าใช้งาน: หน้าต่างแอปไม่เปิดแบบ private (private_mode=False — คุกกี้ 30 วันอยู่ข้ามการปิดโปรแกรม)",
          "private_mode=False" in src_desk and "storage_path" in src_desk)
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าเข้าสู่ระบบจำชื่อผู้ใช้ล่าสุด + สถานะติ๊กจดจำ (localStorage — ไม่เก็บรหัสผ่าน)",
          "crimes_last_login_user" in html and "crimes_login_remember" in html and "prefillLogin" in html
          and "rgPw'" not in html.split("localStorage.setItem")[0][-200:])
    s0 = c.get("/api/settings").get_json()
    c.post("/api/settings", json={"autostart_enabled": True})
    s1 = c.get("/api/settings").get_json()
    c.post("/api/settings", json={"autostart_enabled": False})
    check("Setting: สวิตช์เริ่มอัตโนมัติ — ค่าเริ่มต้นปิด · เปิดแล้วจำค่า · ปิดกลับได้",
          s0.get("autostart_enabled") is False and s1.get("autostart_enabled") is True
          and c.get("/api/settings").get_json().get("autostart_enabled") is False, f"{s0.get('autostart_enabled')} {s1.get('autostart_enabled')}")
    # กติกาศูนย์กลางที่แข็งขึ้น (สคริปต์ 3.10.0)
    res = push_raw([dict(base, username="evil7", salt="ZZ" * 16)])
    check("รหัสร่วม: salt ไม่ใช่ hex → rejected auth (กันแถวที่ทำให้เครื่องอื่นล้มตอนเทียบรหัสผ่าน)",
          res.get("rejected") == [{"username": "evil7", "reason": "auth"}], str(res.get("rejected")))
    res = push_raw([dict(base, username="0123456", pending=0, active=1)], admin_token=ADMIN)
    check("ชื่อผู้ใช้ตัวเลขล้วน '0123456' ไม่ถูกชีตแปลงเป็นเลข (ศูนย์นำหน้าอยู่ครบ)",
          res.get("applied") == 1 and "0123456" in hub_members(), str(res))
    res = push_raw([dict(base, username="longname", display_name="ย" * 500, pending=0, active=1)], admin_token=ADMIN)
    check("ชื่อที่แสดงยาวผิดปกติถูกตัดที่ 80 ตัว (กันการเขียนชีตล้มทั้งใบ)",
          res.get("applied") == 1 and len(hub_members()["longname"]["display_name"]) == 80, str(res))
    check("แถวที่ active=1 ไม่มีทางค้าง pending (เครื่องผู้ดูแลรุ่นเก่าเปิดใช้งาน = อนุมัติ)",
          hub_members()["longname"]["pending"] == 0)
    # เพดานคำขอค้างในเครื่อง (กันสแปมเครื่องเดียว — ศูนย์กลางมีเพดาน 200 ของตัวเอง)
    for i in range(20):
        db.register_user(f"cap{i:02d}", "pass99")
    r = c.post("/api/register", json={"username": "capover", "password": "pass99", "password2": "pass99"})
    check("เครื่องเดียวมีคำขอค้างถึง 20 → สมัครเพิ่มไม่ได้ (400)", r.status_code == 400
          and "ค้าง" in (r.get_json() or {}).get("error", ""), str(r.get_json()))
    with db.get_conn() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE 'cap%'")
    # อนุมัติ/ปฏิเสธ = งานของเครื่องผู้จัดการ (มีรหัสผู้ดูแล) — เหมือนทีม/กองกลาง v3.9.1
    uid_g = db.register_user("gatecheck", "pass88")
    auth.update_config(hub_admin_token="")
    r = c.post(f"/api/admin/members/{uid_g}/approve", json={})
    rd = c.delete(f"/api/admin/members/{uid_g}")
    check("เครื่อง Super Admin ที่ไม่มีรหัสผู้ดูแล: อนุมัติ/ปฏิเสธคำขอไม่ได้ (403 need_admin_token)",
          r.status_code == 403 and (r.get_json() or {}).get("need_admin_token") is True
          and rd.status_code == 403 and (rd.get_json() or {}).get("need_admin_token") is True, f"{r.status_code} {rd.status_code}")
    auth.update_config(hub_admin_token=ADMIN)
    r = c.post(f"/api/admin/members/{uid_g}/approve", json={"role": "member"})
    check("ใส่รหัสผู้ดูแลแล้วอนุมัติได้ตามเดิม", r.status_code == 200 and db.get_user(uid_g)["active"] == 1, str(r.get_json()))
    # v3.10.0: ชีตว่าง + สคริปต์ตั้ง ADMIN_TOKEN แล้ว → ก้อนแรกต้องเซ็นผู้ดูแล (รีวิว Codex PR #36 —
    # รหัสร่วมสาธารณะห้ามใช้ยึดไดเรกทอรีที่เพิ่งถูกล้าง/สร้างใหม่) · สคริปต์ที่ยังไม่ตั้ง ADMIN_TOKEN รับแบบเดิม (test_v370 ครอบ)
    empty2 = TEST_DATA / "hub_empty2.json"
    first = dict(base, username="firstadmin", role="super_admin", active=1, pending=0)
    r_no = raw_post({"kind": "members", "install_id": "boot", "members": [first]}, state=empty2)
    r_ok = raw_post({"kind": "members", "install_id": "boot", "members": [first]}, admin_token=ADMIN, state=empty2)
    check("ชีตว่าง + สคริปต์มี ADMIN_TOKEN: ก้อนแรกด้วยรหัสร่วมล้วน → auth · เซ็นผู้ดูแล → รับ",
          r_no.get("rejected") == [{"username": "firstadmin", "reason": "auth"}] and r_ok.get("applied") == 1,
          f"{r_no.get('rejected')} {r_ok.get('applied')}")

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code_ = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
    for _n in ("seed_account.json", config.HUB_SEED_FILE_NAME):
        (config.BASE_DIR / _n).unlink(missing_ok=True)
sys.exit(code_)
