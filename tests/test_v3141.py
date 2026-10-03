#!/usr/bin/env python3
"""v3.14.1 — หน้าตั้งค่าขึ้น "ศูนย์กลางไม่รับ ADMIN_TOKEN" ทั้งที่ใช้งานได้ปกติ (เจ้าของรายงานพร้อมภาพหน้าจอ)

สาเหตุ: ซิงก์สมาชิกรอบที่ไม่มีแถวต้องเซ็นถูกส่งแบบไม่เซ็น (ออกแบบไว้ใน v3.13.0) ศูนย์กลางจึงตอบ admin=false
แล้วหน้าจอเอาค่านั้นมาตัดสินว่า "ศูนย์กลางไม่รับรหัส" · แก้: จดผลเฉพาะคำขอที่เซ็นจริง (ซิงก์สมาชิกก้อนที่ลงนาม ·
ซิงก์กองกลางที่มีรหัส) เป็น admin_rejected ใน /api/hub/state · ไม่รับจริง (ADMIN_TOKEN ในสคริปต์ถูกเปลี่ยน) ยังเตือนถูกต้อง
และผูกใหม่แล้วการแก้ที่ค้างส่งขึ้นกลางให้เอง — ศูนย์กลาง = tools/hub_gas.js ตัวจริงบน Node (ไม่แตะศูนย์กลางจริง)
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v3141_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "A")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "A_up")
from _app import APP  # noqa: E402

from backend import server  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = TEST_DATA / "hub_sheet.json"
TOKEN = "test-hub-token-v3141-abcdef"
ADMIN = ["test-admin-v3141-Kq#7!@x"]        # ADMIN_TOKEN ในสคริปต์จำลอง (เปลี่ยนได้กลางทาง)
URL = "https://script.google.com/macros/s/TEST3141/exec"
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
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(STATE), TOKEN, ADMIN[0]],
                       input=json.dumps({"method": "POST", "body": body, "parameter": param}),
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def hub_members():
    return {m["username"]: m for m in hub.sync_members(URL, TOKEN, "probe", "3.14.1", []).get("members", [])}


def main():
    server.hub._post = lambda url, payload, tok, admin_token=None, timeout=None: raw_post(payload, tok, admin_token)
    server._hub_kick = lambda *a, **k: None
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน", "hub_code": hub.make_connect_code(URL, TOKEN)})
    check("(เตรียม) ตั้งค่าเครื่องแรก + เชื่อมศูนย์กลาง", r.status_code == 200, str(r.get_json()))
    r = c.post("/api/hub/admin/bind", json={"admin_token": ADMIN[0], "password": "secret9"})
    check("(เตรียม) ผูก ADMIN_TOKEN กับบัญชี Superadmin", r.status_code == 200 and r.get_json().get("ok"), str(r.get_json()))

    print("── ภาพหน้าจอของเจ้าของ: ผูกแล้ว ใช้งานได้ แต่หน้าจอบอก 'ศูนย์กลางไม่รับ' ──")
    res = server._members_sync_now("manual")
    hs = c.get("/api/hub/state").get_json()
    check("ซิงก์รอบที่ไม่มีอะไรต้องเซ็น → ไม่นับเป็น 'ไม่รับรหัส' (admin=None ไม่ใช่ False)",
          res.get("ok") is True and res.get("admin") is None and (hs.get("members") or {}).get("admin") is None,
          f"{res.get('admin')} {(hs.get('members') or {}).get('admin')}")
    check("/api/hub/state: ยังถือสิทธิ์ผู้ดูแล · admin_rejected=False",
          hs.get("admin_unlocked") is True and hs.get("admin_rejected") is False, str({k: hs.get(k) for k in ("admin_unlocked", "admin_rejected")}))
    led = server._ledger_sync_now("manual")
    hs = c.get("/api/hub/state").get_json()
    check("ซิงก์กองกลาง (เซ็นทุกครั้งที่มีรหัส) ศูนย์กลางรับ → ยังใช้งานอยู่", led.get("ok") and led.get("admin") is True
          and hs.get("admin_unlocked") is True and hs.get("admin_rejected") is False)
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าจอตัดสิน 'ศูนย์กลางไม่รับ' จาก admin_rejected เท่านั้น (ไม่ดูผลซิงก์สมาชิกล่าสุดแล้ว)",
          "st.admin_bound && st.admin_rejected" in html and "m.admin === false && m.ok === true" not in html)

    print("\n── แก้สมาชิกได้จริง และขึ้นศูนย์กลาง ──")
    r = c.post("/api/admin/members", json={"username": "jojo", "password": "pass66", "display_name": "JOJO", "role": "member"})
    uid = r.get_json().get("id")
    server._members_sync_now("manual")
    r = c.put(f"/api/admin/members/{uid}", json={"permissions": {"view_team": True}, "display_name": "JOJO2"})
    res = server._members_sync_now("manual")
    hm = hub_members()
    check("สร้าง + แก้ชื่อ/สิทธิ์สมาชิก → ศูนย์กลางรับ (ลายเซ็นผู้ดูแล) ไม่ค้างส่ง",
          r.status_code == 200 and res.get("admin") is True and db.count_pending_members() == 0
          and hm.get("jojo", {}).get("display_name") == "JOJO2"
          and json.loads(hm["jojo"]["permissions"]).get("view_team") is True, str(hm.get("jojo"))[:200])
    hs = c.get("/api/hub/state").get_json()
    check("หลังซิงก์ที่เซ็นจริงและผ่าน → admin=True · ไม่มีธงไม่รับ",
          (hs.get("members") or {}).get("admin") is True and hs.get("admin_rejected") is False)

    print("\n── ADMIN_TOKEN ในสคริปต์ถูกเปลี่ยนจริง → เตือนถูกต้อง · ผูกใหม่แล้วการแก้ค้างขึ้นกลางเอง ──")
    old = ADMIN[0]
    ADMIN[0] = "changed-admin-v3141-ZZ!"
    r = c.put(f"/api/admin/members/{uid}", json={"permissions": {"view_team": True, "view_live": True}})
    res = server._members_sync_now("manual")
    hs = c.get("/api/hub/state").get_json()
    check("แก้สมาชิก → ศูนย์กลางปัดลายเซ็น → admin_rejected=True · ปล่อยสิทธิ์ · การแก้ค้างส่ง (ไม่หาย)",
          r.status_code == 200 and res.get("admin") is False and hs.get("admin_rejected") is True
          and hs.get("admin_unlocked") is False and db.count_pending_members() == 1, str({k: hs.get(k) for k in ("admin_rejected", "admin_unlocked")}))
    c.post("/api/auth/confirm-password", json={"password": "secret9"})
    hs = c.get("/api/hub/state").get_json()
    check("ยืนยันรหัสผ่านซ้ำไม่ช่วย — ยังบอก 'ศูนย์กลางไม่รับ' จนกว่าจะผูกใหม่", hs.get("admin_rejected") is True)
    r = c.post("/api/hub/admin/bind", json={"admin_token": old, "password": "secret9"})
    check("ผูกด้วยรหัสเก่า → ศูนย์กลางปฏิเสธตั้งแต่ตรวจ (ไม่เปลี่ยนอะไร)", r.status_code == 403
          and "ไม่ถูกต้อง" in (r.get_json() or {}).get("error", ""), str(r.get_json()))
    r = c.post("/api/hub/admin/bind", json={"admin_token": ADMIN[0], "password": "secret9"})
    hs = c.get("/api/hub/state").get_json()
    hm = hub_members()
    check("ผูกใหม่ด้วย ADMIN_TOKEN ปัจจุบัน → ธงหาย · ใช้งานได้ · การแก้ที่ค้างขึ้นกลางทันที",
          r.status_code == 200 and hs.get("admin_rejected") is False and hs.get("admin_unlocked") is True
          and db.count_pending_members() == 0 and json.loads(hm["jojo"]["permissions"]).get("view_live") is True,
          str({k: hs.get(k) for k in ("admin_rejected", "admin_unlocked")}))
    ADMIN[0] = "changed-again-v3141"
    led = server._ledger_sync_now("manual")
    hs = c.get("/api/hub/state").get_json()
    check("ซิงก์กองกลางที่เซ็นแล้วถูกปัด → จับได้ทุกรอบ (ไม่ต้องรอมีการแก้สมาชิก)",
          led.get("ok") and led.get("admin") is False and hs.get("admin_rejected") is True and hs.get("admin_unlocked") is False)
    check("ปุ่ม 'ยืนยันรหัสผ่านเพื่อใช้สิทธิ์' ซ่อนเมื่อศูนย์กลางไม่รับ (ช่วยไม่ได้ — ต้องผูกใหม่)",
          "!st.admin_rejected && (st.admin_bound || st.admin_legacy)" in html)

    print("\n── Codex P2 (PR #44): คำตอบ 'ไม่รับ' ที่มาช้าของคำขอที่เซ็นด้วยรหัสเก่า ต้องไม่ล้มการผูกใหม่ที่เพิ่งสำเร็จ ──")
    r = c.post("/api/hub/admin/bind", json={"admin_token": ADMIN[0], "password": "secret9"})
    check("(เตรียม) ผูกกับรหัสปัจจุบัน", r.status_code == 200 and c.get("/api/hub/state").get_json().get("admin_unlocked") is True)
    stale_tok = ADMIN[0]
    ADMIN[0] = "rotated-admin-v3141-RR!"            # เจ้าของเปลี่ยน ADMIN_TOKEN ในสคริปต์
    user = db.get_user(c.get("/api/me").get_json()["id"])
    real_post = server.hub._post
    state = {"armed": True}

    def racing_post(url, payload, tok, admin_token=None, timeout=None):
        # ซิงก์กองกลางเซ็นด้วยรหัสเก่าไปแล้ว — ระหว่างรอคำตอบ ผู้ใช้กดผูกใหม่ด้วยรหัสปัจจุบันสำเร็จ แล้วคำตอบ 'ไม่รับ' จึงมาถึง
        if state["armed"] and payload.get("kind") == "ledger" and admin_token == stale_tok:
            state["armed"] = False
            state["bind"] = server._admin_bind(user, ADMIN[0], "secret9", reason="test")
        return real_post(url, payload, tok, admin_token, timeout)
    server.hub._post = racing_post
    try:
        led = server._ledger_sync_now("manual")
    finally:
        server.hub._post = real_post
    hs = c.get("/api/hub/state").get_json()
    check("ผูกใหม่ระหว่างที่คำขอเก่ารอคำตอบ → สำเร็จ · คำตอบเก่า 'ไม่รับ' ถูกทิ้ง: ยังถือสิทธิ์ · ไม่ขึ้นธงไม่รับ",
          (state.get("bind") or {}).get("ok") is True and led.get("admin") is False
          and hs.get("admin_unlocked") is True and hs.get("admin_rejected") is False,
          str({"bind": state.get("bind"), "led_admin": led.get("admin"),
               "unlocked": hs.get("admin_unlocked"), "rejected": hs.get("admin_rejected")}))
    led = server._ledger_sync_now("manual")
    check("ซิงก์ถัดไปเซ็นด้วยรหัสใหม่ → ศูนย์กลางรับ", led.get("admin") is True
          and c.get("/api/hub/state").get_json().get("admin_rejected") is False)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
raise SystemExit(code)
