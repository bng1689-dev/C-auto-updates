#!/usr/bin/env python3
"""v3.9.1 — "ทีมจัดที่เครื่อง Super Admin ครั้งเดียว มีผลทุกเครื่อง (เครื่องอื่นแก้ไม่ได้)"

เครื่องผู้จัดการ = เชื่อมศูนย์กลางแล้วและมี 'รหัสผู้ดูแลศูนย์กลาง' (หรือยังไม่เชื่อมศูนย์กลาง = เครื่องเดี่ยว)
  • จัดทีม (สร้าง/แก้/ลบ) และบันทึก/ลบรายการกองกลาง ทำได้เฉพาะเครื่องผู้จัดการ — เครื่องอื่นได้ 403 need_admin_token (ไม่ใช่ 'ค้างส่ง')
  • เครื่องเดี่ยว (ไม่เชื่อมศูนย์กลาง) จัดเองได้ตามปกติ · /api/me บอก central_manager ให้หน้าจอซ่อนปุ่ม · กองกลางบอก can_edit/manager
  • สิทธิ์เดิมยังบังคับก่อน: สมาชิกไม่มีสิทธิ์จัดทีม → 403 เรื่องสิทธิ์ · สมาชิกที่ได้สิทธิ์จัดทีมบนเครื่องผู้จัดการ → ทำได้
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v391_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "data")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
from _app import APP  # noqa: E402,F401

from backend import server  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

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


def main():
    server.app.config["TESTING"] = True
    server._hub_kick = lambda *a, **k: None
    server.hub._post = lambda url, payload, token, admin_token=None: {"ok": True, "kind": payload.get("kind"), "members": [], "entries": [], "seq": 0}
    admin = server.app.test_client()
    admin.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9", "display_name": "Admin"})
    admin.post("/api/admin/members", json={"username": "somchai", "password": "pass66", "display_name": "สมชาย", "role": "member"})
    admin.post("/api/admin/members", json={"username": "lead", "password": "pass77", "display_name": "หัวหน้า", "role": "member",
                                           "permissions": {"manage_teams": True}})
    users = {u["username"]: u["id"] for u in db.list_users()}

    print("── เครื่องเดี่ยว (ยังไม่เชื่อมศูนย์กลาง) จัดเองได้ ──")
    me = admin.get("/api/me").get_json()
    check("/api/me: central_manager=True", me.get("central_manager") is True, str(me))
    r = admin.post("/api/admin/teams", json={"name": "ทีม A", "member_ids": [users["somchai"]]})
    check("สร้างทีมได้", r.status_code == 200, r.get_data(as_text=True)[:120])
    tid = r.get_json()["id"]
    check("แก้/ลบทีมได้", admin.put(f"/api/admin/teams/{tid}", json={"rate_per_name": 3}).status_code == 200)
    r = admin.post("/api/admin/ledger", json={"user_id": users["somchai"], "kind": "in", "amount": 10})
    check("บันทึกกองกลางได้ · หน้ากองกลาง can_edit/manager = True", r.status_code == 200
          and admin.get("/api/live/board").get_json()["can_edit"] is True and admin.get("/api/live/board").get_json()["manager"] is True)
    lid = r.get_json()["id"]

    print("\n── เชื่อมศูนย์กลางแล้ว แต่ Superadmin ยังไม่ได้ผูกสิทธิ์ผู้ดูแล → ดูได้อย่างเดียว ──")
    server.auth.update_config(hub_url=URL, hub_token="tok", hub_enabled=True)
    pending_before = db.count_pending_ledger()      # รายการที่บันทึกตอนเครื่องเดี่ยว รอส่งอยู่แล้ว 1 (ปกติ)
    me = admin.get("/api/me").get_json()
    check("/api/me: central_manager=False", me.get("central_manager") is False)
    r = admin.post("/api/admin/teams", json={"name": "ทีม B", "member_ids": []})
    check("สร้างทีม → 403 need_admin_token พร้อมข้อความบอกให้ผูกสิทธิ์ผู้ดูแลกับบัญชี Superadmin",
          r.status_code == 403 and r.get_json().get("need_admin_token") is True and r.get_json().get("need_bind") is True
          and "สิทธิ์ผู้ดูแล" in r.get_json().get("error", ""), r.get_data(as_text=True)[:160])
    check("แก้ทีม → 403", admin.put(f"/api/admin/teams/{tid}", json={"member_ids": []}).status_code == 403)
    check("ลบทีม → 403 (ทีมยังอยู่)", admin.delete(f"/api/admin/teams/{tid}").status_code == 403 and db.get_team(tid) is not None)
    check("บันทึกกองกลาง → 403 · ลบรายการ → 403 (รายการยังอยู่)",
          admin.post("/api/admin/ledger", json={"user_id": users["somchai"], "kind": "out", "amount": 1}).status_code == 403
          and admin.delete(f"/api/admin/ledger/{lid}").status_code == 403 and db.list_ledger(db.ledger_months()[0])[0]["id"] == lid)
    b = admin.get("/api/live/board").get_json()
    check("หน้ากองกลาง: can_edit=False · manager=False (แต่ยังเห็นทั้งองค์กร)", b["can_edit"] is False and b["manager"] is False and b["scope"] == "all")
    check("ความพยายามที่ถูกห้ามไม่ทำให้มีอะไรค้างส่งเพิ่ม (ห้ามตั้งแต่ต้น ไม่ใช่ 'ค้าง')", db.count_pending_ledger() == pending_before)
    check("อ่านทีมได้ตามปกติ", admin.get("/api/admin/teams").status_code == 200)
    lead = server.app.test_client()
    lead.post("/api/login", json={"username": "lead", "password": "pass77"})
    check("สมาชิกที่มีสิทธิ์จัดทีม → 403 เช่นกัน", lead.post("/api/admin/teams", json={"name": "x"}).status_code == 403)

    print("\n── v3.13.0: Superadmin ผูก+ใช้สิทธิ์ผู้ดูแล → จัดได้ (ผูกกับบัญชี ไม่ใช่เครื่อง) ──")
    from _app import grant_hub_admin
    grant_hub_admin("admin1", "secret9", "admin-token-xyz-12345")
    check("/api/me: central_manager=True", admin.get("/api/me").get_json().get("central_manager") is True)
    check("สร้าง/แก้ทีมได้ · บันทึก/ลบกองกลางได้",
          admin.post("/api/admin/teams", json={"name": "ทีม B", "member_ids": []}).status_code == 200
          and admin.put(f"/api/admin/teams/{tid}", json={"member_ids": [users["somchai"], users["admin1"]]}).status_code == 200
          and admin.post("/api/admin/ledger", json={"user_id": users["somchai"], "kind": "out", "amount": 1}).status_code == 200
          and admin.delete(f"/api/admin/ledger/{lid}").status_code == 200)
    check("v3.13.0: สมาชิกที่มีสิทธิ์จัดทีม แม้อยู่เครื่องเดียวกับ Superadmin ที่ใช้สิทธิ์อยู่ → 403 (สิทธิ์ผู้ดูแลเป็นของ Superadmin เท่านั้น)",
          lead.post("/api/admin/teams", json={"name": "ทีม C", "member_ids": []}).status_code == 403)
    sc = server.app.test_client()
    sc.post("/api/login", json={"username": "somchai", "password": "pass66"})
    check("สมาชิกไม่มีสิทธิ์ → 403 เรื่องสิทธิ์ (ตรวจก่อนเรื่องเครื่อง) · บันทึกกองกลาง 403",
          "สิทธิ์" in sc.post("/api/admin/teams", json={"name": "y"}).get_json().get("error", "")
          and sc.post("/api/admin/ledger", json={"user_id": users["somchai"], "kind": "in", "amount": 1}).status_code == 403)

    print("\n── ปิดการเชื่อมต่อ → กลับเป็นเครื่องเดี่ยว ──")
    server.auth.update_config(hub_enabled=False)
    check("ปิดศูนย์กลางแล้วจัดเองได้อีก", admin.get("/api/me").get_json().get("central_manager") is True
          and admin.post("/api/admin/teams", json={"name": "ทีม D", "member_ids": []}).status_code == 200)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code_ = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code_)
