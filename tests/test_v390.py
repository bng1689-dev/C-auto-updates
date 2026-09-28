#!/usr/bin/env python3
"""v3.9.0 — สมุดกองกลางกลาง: ทุกเครื่องเห็นรายการรับ/จ่ายชุดเดียวกันผ่านสคริปต์ศูนย์กลางตัวจริง (Node)

ผู้ใช้สั่ง: "ให้แสดงค่าเดียวกันทุกเครื่อง แต่สิทธิ์การแก้ไข Super Admin เป็นผู้จัดการ และการตั้งค่าศูนย์กลางรวมตัวเลข
            เมื่อตั้งค่าแล้วให้จำค่าและซิงค์เองแบบออโต้ หน้าสมาชิกจะเห็นของตัวเองและทีมเท่านั้น"
  เครื่อง A = โปรเซสนี้ · เครื่อง B = โปรเซสแยก (_hub_machine.py) · ศูนย์กลาง = tools/hub_gas.js ตัวจริงบน tests/gas_harness.js
  • รายการที่ Super Admin บันทึกที่ A → ขึ้นชีต ledger (ชื่อผู้ใช้เจ้าของ · จำนวน · หมายเหตุ) → B เข้าร่วมแล้วเห็นชุดเดียวกัน
  • Super Admin เท่านั้นที่บันทึก/ลบได้ (สมาชิก 403) · เครื่องที่ไม่มีรหัสผู้ดูแล → ค้างส่ง (auth) จนกว่าจะใส่
  • สมาชิกเห็นยอด/รายคน/รายการเฉพาะของตัวเองและทีม · Super Admin (หรือสิทธิ์ 'ดูกองกลางทั้งองค์กร') เห็นทั้งหมด
  • ลบที่เครื่องหนึ่ง = หายทุกเครื่อง (ป้ายหลุมศพ) · ยังไม่เคยขึ้นกลาง = ลบทิ้งจริงไม่ต้องส่ง · conflict ของกลางชนะ
  • รหัสร่วม (HUB_TOKEN) แก้สมุดไม่ได้ · รูปแบบผิดถูกปัดตก · สคริปต์รุ่นเก่า → เตือน · ดึงเฉพาะส่วนต่าง (ไม่ใช่ทั้งเล่มทุกรอบ)
  • ก้อน counts นับยอดเฉพาะรายการที่เครื่องนั้นบันทึกเอง (ไม่ซ้ำกันทุกเครื่อง)
  • ตั้งค่าศูนย์กลาง: มี URL + รหัสลับ = เปิดใช้ทันที · ปิดได้ด้วย enabled=false · ปุ่มซิงก์เดี๋ยวนี้ทำครบสามอย่าง
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v390_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "A")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "A_up")
from _app import APP  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)

from backend import server  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = TEST_DATA / "hub_sheet.json"
TOKEN = "test-hub-token-0123456789"
ADMIN = "test-admin-token-9876543210"
URL = "https://script.google.com/macros/s/TEST/exec"
VER = "3.9.0"
YM = datetime.now().strftime("%Y-%m")
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
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
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
    return raw_post(payload, tok, admin_token)


def machine_b(cmds):
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / "B"), CRIMES_UPLOAD_DIR=str(TEST_DATA / "B_up"),
               PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / "B"), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(cmds), env=env, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise RuntimeError("machine B: " + r.stderr[-800:])
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def hub_ledger():
    """อ่านสมุดบนกลางทั้งเล่ม (after=0 · ไม่ส่งอะไร) → {gid: row}"""
    res = hub.sync_ledger(URL, TOKEN, "probe", VER, [], after=0)
    return {e["gid"]: e for e in res.get("entries", [])}


def push_raw(entries, admin_token=ADMIN, install="raw", after=0):
    return hub.sync_ledger(URL, TOKEN, install, VER, entries, after=after, admin_token=admin_token)


def board_raw(ym=YM):
    """กระดานของศูนย์กลาง (doGet) — ยอดเงินต้องมาจากชีต ledger ไม่ใช่ตัวเลขที่เครื่องรายงาน"""
    req = {"method": "GET", "parameter": {"ym": ym, "sign": hub.sign(f"board:{ym}".encode("utf-8"), TOKEN)}}
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(req), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def local_rows():
    with db.get_conn() as c:
        return {r["gid"]: dict(r) for r in c.execute("SELECT * FROM ledger ORDER BY id").fetchall()}


def main():
    check("มี Node สำหรับรันสคริปต์ศูนย์กลางตัวจริง", shutil.which("node") is not None)
    server.hub._post = fake_post
    server._hub_kick = lambda *a, **k: None          # ซิงก์เมื่อสั่งเท่านั้น
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    code = hub.make_connect_code(URL, TOKEN)

    print("── เครื่อง A: Super Admin ตั้งค่า + สมาชิก + ทีม ──")
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน", "hub_code": code, "hub_admin_token": ADMIN})
    check("สมัครเครื่องแรกพร้อมรหัสเชื่อมต่อ+รหัสผู้ดูแล", r.status_code == 200 and r.get_json().get("hub_connected"))
    check("ซิงก์สมุดกองกลางตอนตั้งค่า (ว่างเปล่า) สำเร็จ", server._ledger_last.get("ok") is True and server._ledger_last.get("reason") == "setup", str(server._ledger_last))
    c.post("/api/admin/members", json={"username": "somchai", "password": "pass66", "display_name": "สมชาย", "role": "member"})
    c.post("/api/admin/members", json={"username": "wichai", "password": "pass77", "display_name": "วิชัย", "role": "member"})
    users = {u["username"]: u["id"] for u in db.list_users()}
    r = c.post("/api/admin/teams", json={"name": "ทีม A", "member_ids": [users["admin1"], users["somchai"]]})
    check("(เตรียม) สมาชิก 2 คน + ทีม A (admin1, somchai) · wichai ไม่มีทีม", r.status_code == 200 and len(users) == 3)
    check("(เตรียม) สมาชิกขึ้นกลาง", server._members_sync_now("test").get("ok") and db.count_pending_members() == 0)
    install_a = server.auth.load_config().get("install_id", "")

    print("\n── A บันทึกรายการ → ขึ้นชีต ledger ──")
    r1 = c.post("/api/admin/ledger", json={"user_id": users["somchai"], "kind": "in", "amount": 100, "note": "ค่าอินเทอร์เน็ต"})
    r2 = c.post("/api/admin/ledger", json={"user_id": users["wichai"], "kind": "out", "amount": 40})
    r3 = c.post("/api/admin/ledger", json={"user_id": users["admin1"], "kind": "in", "amount": 250.5})
    check("บันทึก 3 รายการ", all(x.status_code == 200 for x in (r1, r2, r3)))
    exp = db.export_ledger()
    check("ก้อนที่ส่ง: 3 รายการ เฉพาะฟิลด์ที่อนุญาต · เจ้าของเป็นชื่อผู้ใช้ · gid ไม่ซ้ำ · rev=0",
          len(exp) == 3 and all(set(e) == set(hub.LEDGER_FIELDS) for e in exp) and {e["owner"] for e in exp} == {"somchai", "wichai", "admin1"}
          and len({e["gid"] for e in exp}) == 3 and all(e["rev"] == 0 for e in exp) and exp[0]["created_by"] == "admin1", str(exp)[:300])
    check("ก้อนที่ส่งไม่มี user_id ของเครื่อง (ผูกข้ามเครื่องไม่ได้)", all("user_id" not in e and "id" not in e for e in exp))
    res = server._ledger_sync_now("test")
    check("ซิงก์ A → กลางรับ 3 · ไม่ปัดตก · admin=True · ไม่ค้าง",
          res.get("ok") and res.get("applied") == 3 and not res.get("rejected") and res.get("admin") is True and db.count_pending_ledger() == 0, str(res)[:300])
    hl = hub_ledger()
    g_in100 = next(e for e in exp if e["owner"] == "somchai")["gid"]
    g_out40 = next(e for e in exp if e["owner"] == "wichai")["gid"]
    check("กลาง: 3 รายการ rev 1..3 · หมายเหตุ/จำนวนตรง · origin = เครื่อง A",
          len(hl) == 3 and sorted(e["rev"] for e in hl.values()) == [1, 2, 3] and hl[g_in100]["note"] == "ค่าอินเทอร์เน็ต"
          and hl[g_in100]["amount"] == 100 and hl[g_out40]["kind"] == "out" and all(e["origin"] == install_a for e in hl.values()), str(hl)[:300])
    lr = local_rows()
    check("A: หลังกลางรับ rev ในเครื่องตรงกับกลาง · sync_dirty=0 · ส่งรอบหน้าว่าง",
          all(lr[g]["hub_rev"] == hl[g]["rev"] and lr[g]["sync_dirty"] == 0 for g in hl) and db.export_ledger() == []
          and int(db.get_meta(server.LEDGER_SEQ_KEY)) == 3)
    res = server._ledger_sync_now("test")
    check("ซิงก์ซ้ำโดยไม่มีอะไรเปลี่ยน → กลางตอบส่วนต่างว่าง (ไม่ส่งทั้งเล่มทุกรอบ)",
          res.get("ok") and res.get("applied") == 0 and res.get("entries") == [] and server._ledger_last.get("count") == 0, str(res)[:200])

    print("\n── เงินไม่ไปทางก้อน counts อีกแล้ว — กระดานศูนย์กลางคิดยอดจากชีต ledger ──")
    payload = hub.build_payload(YM, install_a, VER)
    check("ก้อน counts ไม่มี amount_in/amount_out (ยอดที่เครื่องรายงานจะค้างหลังเครื่องอื่นลบ — ตัดออกทั้งทาง)",
          "amount_in" not in hub.ALLOWED_FIELDS and all("amount_in" not in r and "amount_out" not in r for r in payload["rows"]))
    bd = board_raw()
    check("กระดาน (doGet): ยอดรวมจากชีต ledger — รับ 350.5 จ่าย 40 · แยกรายคนด้วยชื่อที่แสดงจากไดเรกทอรี + เครื่องที่บันทึก",
          bd.get("ok") and bd["totals"]["amount_in"] == 350.5 and bd["totals"]["amount_out"] == 40 and bd["totals"]["net"] == 310.5
          and {(r["display_name"], r["install_id"], r["amount_in"], r["amount_out"]) for r in bd["rows"]}
          == {("สมชาย", install_a, 100, 0), ("วิชัย", install_a, 0, 40), ("แอดมิน", install_a, 250.5, 0)}, str(bd)[:400])

    print("\n── เครื่อง B เข้าร่วม → เห็นสมุดเล่มเดียวกัน · สมาชิกเห็นเฉพาะตัวเองและทีม ──")
    out = machine_b([
        {"op": "join", "code": code},
        {"op": "ledger", "as": "ledger0"},
        {"op": "login", "u": "admin1", "p": "secret9", "as": "login_admin"},
        {"op": "board", "as": "board_admin"},
        {"op": "logout"},
        {"op": "login", "u": "wichai", "p": "pass77", "as": "login_wichai"},
        {"op": "board", "as": "board_wichai"},
        {"op": "ledger_add", "u": "wichai", "kind": "in", "amount": 5, "as": "member_add"},
        {"op": "logout"},
    ])
    j = out["join"]
    check("B เข้าร่วม → ok", j[0] == 200 and j[1].get("members") == 3, str(j))
    lb = {r["gid"]: r for r in out["ledger0"]}
    check("B: ได้สมุด 3 รายการทันทีตอนเข้าร่วม · ผูกเจ้าของเป็น user_id ของ B (ไม่ใช่ 0) · ไม่ค้างส่ง · origin=A",
          set(lb) == set(hl) and all(r["user_id"] > 0 and r["sync_dirty"] == 0 and r["hub_rev"] == hl[g]["rev"] and r["origin"] == install_a
                                      for g, r in lb.items()), str(lb)[:300])
    ba = out["board_admin"][1]
    check("B: Super Admin เห็นทั้งองค์กร — รับ 350.5 จ่าย 40 สุทธิ 310.5 · 3 รายการ · scope=all · แก้ได้",
          ba["totals"] == {"in": 350.5, "out": 40.0, "net": 310.5, "entries": 3} and ba["scope"] == "all" and ba["can_edit"] is True
          and len(ba["rows"]) == 3 and len(ba["entries"]) == 3 and ba["hub"]["enabled"] is True, str(ba)[:300])
    bw = out["board_wichai"][1]
    check("B: wichai (ไม่มีทีม) เห็นเฉพาะของตัวเอง — จ่าย 40 · 1 รายการ · scope=team · แก้ไม่ได้",
          bw["totals"] == {"in": 0.0, "out": 40.0, "net": -40.0, "entries": 1} and bw["scope"] == "team" and bw["can_edit"] is False
          and [r["username"] for r in bw["rows"]] == ["wichai"] and len(bw["entries"]) == 1 and len(bw["daily"]) == 1, str(bw)[:300])
    check("B: สมาชิกบันทึกรายการไม่ได้ (403 — Super Admin เป็นผู้จัดการ)", out["member_add"][0] == 403, str(out["member_add"]))

    print("\n── A: สมาชิกในทีมเห็นของทีม · สิทธิ์ 'ดูกองกลางทั้งองค์กร' ──")
    sc = server.app.test_client()
    sc.post("/api/login", json={"username": "somchai", "password": "pass66"})
    b = sc.get("/api/live/board").get_json()
    check("A: somchai (ทีม A กับ admin1) เห็นของตัวเอง+admin1 — รับ 350.5 · 2 รายการ · ไม่เห็นของ wichai",
          b["totals"] == {"in": 350.5, "out": 0.0, "net": 350.5, "entries": 2} and {r["username"] for r in b["rows"]} == {"somchai", "admin1"}
          and all(e["username"] != "wichai" for e in b["entries"]) and b["scope"] == "team", str(b["totals"]))
    check("A: สมาชิกลบรายการไม่ได้ (403)", sc.delete(f"/api/admin/ledger/{r1.get_json()['id']}").status_code == 403)
    c.put(f"/api/admin/members/{users['wichai']}", json={"permissions": {"view_live": True}})
    wc = server.app.test_client()
    wc.post("/api/login", json={"username": "wichai", "password": "pass77"})
    b = wc.get("/api/live/board").get_json()
    check("A: wichai ได้สิทธิ์ 'ดูกองกลางทั้งองค์กร' → เห็นทั้งหมด (scope=all) แต่ยังแก้ไม่ได้",
          b["scope"] == "all" and b["totals"]["entries"] == 3 and b["can_edit"] is False, str(b["totals"]))
    c.put(f"/api/admin/members/{users['wichai']}", json={"permissions": {}})

    print("\n── B (Super Admin แต่ไม่มีรหัสผู้ดูแล) บันทึก → ค้างส่ง จนใส่รหัส ──")
    out = machine_b([
        {"op": "login", "u": "admin1", "p": "secret9"},
        {"op": "ledger_add", "u": "somchai", "kind": "out", "amount": 30, "note": "ค่ากาแฟ"},
        {"op": "ledger_sync", "as": "sync_noadmin"}, {"op": "ledger_pending", "as": "pending_noadmin"},
        {"op": "ledger_state", "as": "state_noadmin"},
    ])
    check("B: บันทึกในเครื่องได้ (Super Admin) · ซิงก์โดยไม่มีรหัสผู้ดูแล → rejected auth · ค้าง 1",
          out["ledger_add"][0] == 200 and out["sync_noadmin"]["ok"] and [x["reason"] for x in out["sync_noadmin"]["rejected"]] == ["auth"]
          and out["pending_noadmin"] == 1, str(out["sync_noadmin"]))
    check("B: แถบสถานะบอก 'รอส่ง 1' พร้อมเหตุผลให้ใส่รหัสผู้ดูแล",
          out["state_noadmin"].get("pending") == 1 and "รหัสผู้ดูแล" in out["state_noadmin"].get("hint", ""), str(out["state_noadmin"]))
    check("กลาง: ยังไม่มีรายการ 30 · A ซิงก์แล้วก็ไม่ได้อะไรมา", len(hub_ledger()) == 3 and server._ledger_sync_now("test").get("entries") == [])
    out = machine_b([
        {"op": "set_admin_token", "token": ADMIN},
        {"op": "ledger_sync", "as": "sync_admin"}, {"op": "ledger_pending", "as": "pending_admin"},
        {"op": "ledger"},
    ])
    g_out30 = next(r["gid"] for r in out["ledger"] if r["amount"] == 30)
    check("B: ใส่รหัสผู้ดูแลแล้วซิงก์ → กลางรับ ไม่ค้าง · origin = เครื่อง B",
          out["sync_admin"]["ok"] and not out["sync_admin"]["rejected"] and out["pending_admin"] == 0
          and hub_ledger().get(g_out30, {}).get("rev") == 4 and hub_ledger()[g_out30]["origin"] not in ("", install_a), str(out["sync_admin"]))
    res = server._ledger_sync_now("test")
    b = c.get("/api/live/board").get_json()
    check("A: ซิงก์แล้วได้รายการจาก B มา (สร้าง 1 · หมายเหตุ 'ค่ากาแฟ' · เจ้าของ somchai) → จ่ายรวม 70",
          (res.get("summary") or {}).get("created") == [g_out30] and b["totals"]["out"] == 70.0
          and any(e["note"] == "ค่ากาแฟ" and e["username"] == "somchai" for e in b["entries"]), str(res.get("summary")))
    bd = board_raw()
    check("กระดานศูนย์กลาง: รายการของ B ขึ้นเป็นแถวของเครื่อง B · จ่ายรวม 70",
          bd["totals"]["amount_out"] == 70 and any(r["display_name"] == "สมชาย" and r["install_id"] != install_a and r["amount_out"] == 30 for r in bd["rows"]), str(bd)[:400])

    print("\n── B ลบรายการที่ A บันทึก → กระดานศูนย์กลางลดทันที โดย A ไม่ต้องส่งอะไรอีก ──")
    out = machine_b([{"op": "login", "u": "admin1", "p": "secret9"}, {"op": "ledger_del", "gid": g_out40}, {"op": "ledger_sync"}])
    bd = board_raw()
    check("B ลบ 40 ของ wichai (origin=A) แล้วซิงก์ → กระดาน: จ่ายรวม 30 ทันที (ไม่ค้าง 40 ที่ A เคยรายงาน)",
          out["ledger_del"][0] == 200 and out["ledger_sync"]["ok"] and not out["ledger_sync"]["rejected"]
          and bd["totals"]["amount_out"] == 30 and not any(r["display_name"] == "วิชัย" and r["amount_out"] for r in bd["rows"]), str(bd["totals"]))
    res = server._ledger_sync_now("test")
    check("A: ได้ป้ายหลุมศพมา → รายการหายจากยอดของ A ด้วย", (res.get("summary") or {}).get("deleted") == [g_out40]
          and c.get("/api/live/board").get_json()["totals"]["out"] == 30.0, str(res.get("summary")))

    print("\n── ลบที่ A → หายที่ B · ลบก่อนเคยขึ้นกลาง = ทิ้งจริง ──")
    lid = local_rows()[g_in100]["id"]
    check("A: ลบรายการ 100 (กลางรู้จักแล้ว) → เก็บเป็นป้ายหลุมศพ deleted=1 รอส่ง",
          c.delete(f"/api/admin/ledger/{lid}").status_code == 200 and local_rows()[g_in100]["deleted"] == 1 and local_rows()[g_in100]["sync_dirty"] == 1)
    b = c.get("/api/live/board").get_json()
    check("A: ยอด/รายการ/กราฟไม่นับที่ลบแล้ว (รับ 250.5 · 2 รายการ)",
          b["totals"] == {"in": 250.5, "out": 30.0, "net": 220.5, "entries": 2} and all(e["gid"] != g_in100 for e in b["entries"]), str(b["totals"]))
    res = server._ledger_sync_now("test")
    check("A: ซิงก์ → กลางจดว่าลบ (rev เพิ่ม) · ไม่ค้าง", res.get("ok") and res.get("applied") == 1 and hub_ledger()[g_in100]["deleted"] == 1 and db.count_pending_ledger() == 0)
    check("A: ลบซ้ำ → 404", c.delete(f"/api/admin/ledger/{lid}").status_code == 404)
    out = machine_b([{"op": "ledger_sync"}, {"op": "login", "u": "admin1", "p": "secret9"}, {"op": "board"}, {"op": "ledger"}])
    check("B: ซิงก์ → รายการ 100 ถูกลบตาม (summary.deleted) · ยอดตรงกับ A",
          out["ledger_sync"]["summary"]["deleted"] == [g_in100] and out["board"][1]["totals"] == {"in": 250.5, "out": 30.0, "net": 220.5, "entries": 2}, str(out["ledger_sync"]["summary"]))
    r = c.post("/api/admin/ledger", json={"user_id": users["admin1"], "kind": "in", "amount": 7})
    tmp = r.get_json()["id"]
    check("A: บันทึกแล้วลบทันที (ยังไม่เคยขึ้นกลาง) → หายจากเครื่องจริง ไม่ค้างส่ง",
          c.delete(f"/api/admin/ledger/{tmp}").status_code == 200 and all(rw["id"] != tmp for rw in local_rows().values()) and db.export_ledger() == [])
    check("กลาง: ไม่รู้จักรายการนั้นเลย", len(hub_ledger()) == 4)

    print("\n── ลำดับตัดสินโดยศูนย์กลาง (rev) · รหัสร่วมแก้ไม่ได้ · รูปแบบผิด ──")
    g_in250 = next(g for g, e in hub_ledger().items() if e["owner"] == "admin1" and not e["deleted"])
    cur = hub_ledger()[g_in250]
    res = push_raw([dict(cur, amount=999, rev=cur["rev"] - 1)])
    check("rev เก่า → rejected conflict · กลางไม่เปลี่ยน · ตอบรายการรุ่นปัจจุบันกลับมาให้ทับ",
          res.get("rejected") == [{"gid": g_in250, "reason": "conflict"}] and hub_ledger()[g_in250]["amount"] == 250.5
          and any(e["gid"] == g_in250 and e["amount"] == 250.5 for e in res.get("entries", [])), str(res)[:200])
    res = push_raw([{"gid": "shared-token-entry", "ts": "2026-01-01T00:00:00", "ym": "2026-01", "owner": "somchai", "kind": "in", "amount": 1, "note": "", "created_by": "x", "deleted": 0, "rev": 0}], admin_token=None)
    check("รหัสร่วม (ไม่มีรหัสผู้ดูแล) เพิ่มรายการ → rejected auth", res.get("rejected") == [{"gid": "shared-token-entry", "reason": "auth"}] and "shared-token-entry" not in hub_ledger())
    res = push_raw([dict(cur, deleted=1)], admin_token=None)
    check("รหัสร่วมลบรายการ → rejected auth", res.get("rejected") == [{"gid": g_in250, "reason": "auth"}] and hub_ledger()[g_in250]["deleted"] == 0)
    res = push_raw([dict(cur, amount=1)], admin_token="wrong-admin-token-xxxxxxxx")
    check("รหัสผู้ดูแลผิด → admin=False · rejected auth", res.get("admin") is False and res.get("rejected") == [{"gid": g_in250, "reason": "auth"}])
    res = push_raw([{"gid": "bad-1", "ts": "", "ym": "2026-01", "owner": "x", "kind": "in", "amount": 0, "rev": 0},
                    {"gid": "bad-2", "ts": "", "ym": "2026-01", "owner": "x", "kind": "gift", "amount": 5, "rev": 0},
                    {"gid": "bad-3", "ts": "", "ym": "jan", "owner": "x", "kind": "in", "amount": 5, "rev": 0}])
    check("จำนวน 0 · ประเภทแปลก · เดือนผิดรูป → rejected invalid ทั้งหมด",
          sorted(x["reason"] for x in res.get("rejected", [])) == ["invalid"] * 3 and len(hub_ledger()) == 4, str(res.get("rejected")))
    body = hub.build_ledger_payload("raw", VER, [dict(cur, amount=1)], after=0)
    res = raw_post(body, admin_token=ADMIN, script_admin="")
    check("สคริปต์ยังไม่ตั้ง ADMIN_TOKEN → admin_ready=False ปัดตกทั้งที่ลายเซ็นถูก", res.get("admin_ready") is False and res.get("rejected") == [{"gid": g_in250, "reason": "auth"}])
    res = push_raw([], after=2)
    check("after=2 → ได้เฉพาะรายการที่ rev>2 (ส่วนต่าง) · seq = rev สูงสุด · ไม่ใช่ full",
          all(e["rev"] > 2 for e in res["entries"]) and len(res["entries"]) == 4 and res["seq"] == 6 and res["full"] is False, str(res)[:200])

    print("\n── เลข rev ค้างจากศูนย์กลางเก่า (รีวิว PR #33) ──")
    res = push_raw([], after=999)
    check("after เกินกว่าที่กลางเคยนับ → กลางส่งทั้งเล่ม (full=True · ครบ 4 รายการ) · seq=6",
          res["full"] is True and len(res["entries"]) == 4 and res["seq"] == 6, str(res)[:200])
    db.set_meta(server.LEDGER_SEQ_KEY, 999)
    res = server._ledger_sync_now("test")
    check("A จำเลข 999 อยู่ → ซิงก์แล้วจดเลขจริงของกลาง (6) แม้ต่ำกว่าเดิม · ไม่มีอะไรถูกติดธงส่งใหม่ (ทุกรายการยังอยู่บนกลาง)",
          res.get("ok") and int(db.get_meta(server.LEDGER_SEQ_KEY)) == 6 and (res.get("summary") or {}).get("reflagged") == []
          and db.count_pending_ledger() == 0, f"{db.get_meta(server.LEDGER_SEQ_KEY)} {res.get('summary')}")
    r = c.post("/api/hub/config", json={"url": "https://script.google.com/macros/s/OTHER/exec"})
    check("เปลี่ยน URL ศูนย์กลาง → ลืมเลขที่จำ (0)", r.status_code == 200 and int(db.get_meta(server.LEDGER_SEQ_KEY)) == 0)
    c.post("/api/hub/config", json={"url": URL})            # กลับมาเล่มเดิม (นับเป็นเปลี่ยนอีกครั้ง → 0)
    db.set_meta(server.LEDGER_SEQ_KEY, 6)
    r = c.post("/api/hub/config", json={"url": URL, "interval_min": 2})
    check("บันทึกตั้งค่าโดย URL เท่าเดิม → เลขไม่ถูกลืม", r.status_code == 200 and int(db.get_meta(server.LEDGER_SEQ_KEY)) == 6)
    # ชีต ledger ถูกสร้างใหม่ (ว่าง) — เหมือนผู้ดูแลตั้งศูนย์กลางใหม่: รายการที่ A เคยซิงก์ต้องถูกส่งขึ้นใหม่ ไม่ใช่หายไปเฉย ๆ
    st = json.loads(STATE.read_text(encoding="utf-8"))
    st["sheets"].pop("ledger", None)
    STATE.write_text(json.dumps(st), encoding="utf-8")
    n_live = len([rw for rw in local_rows().values() if not rw["deleted"]])
    res = server._ledger_sync_now("test")
    s = res.get("summary") or {}
    check("ชีตว่าง (กลางเป็นคนละเล่ม) → รายการที่เคยซิงก์ถูกติดธงส่งใหม่ (ป้ายหลุมศพเก่าทิ้ง) · เลขจด 0",
          res.get("ok") and res.get("full") is True and len(s.get("reflagged", [])) == n_live and db.count_pending_ledger() == n_live
          and int(db.get_meta(server.LEDGER_SEQ_KEY)) == 0 and all(rw["deleted"] == 0 for rw in local_rows().values()), str(s))
    res = server._ledger_sync_now("test")
    check("รอบถัดไป → ขึ้นกลางเล่มใหม่ครบ ไม่ค้าง", res.get("ok") and res.get("applied") == n_live and db.count_pending_ledger() == 0
          and len(hub_ledger()) == n_live, str(res)[:200])

    print("\n── สคริปต์รุ่นเก่า · รายการเก่าก่อน 3.9.0 ──")
    real_post = server.hub._post
    server.hub._post = lambda u, p, t, admin_token=None: {"ok": True, "stored": 0, "kind": "ledger"}
    res = hub.sync_ledger(URL, TOKEN, "x", VER, [])
    check("ตอบ ok แต่ไม่มี entries → บอกให้อัปเดต hub_gas.js (ไม่เงียบ)", res.get("ok") is False and "รุ่นเก่า" in res.get("error", ""), str(res))
    server.hub._post = real_post
    with db.get_conn() as conn:   # แถวแบบรุ่นก่อน (ไม่มี gid/owner) — เช่นจากฐานข้อมูลเดิม
        conn.execute("INSERT INTO ledger(ts,ym,user_id,kind,amount,note,created_by) VALUES(?,?,?,?,?,?,?)",
                     (datetime.now().isoformat(timespec="seconds"), YM, users["admin1"], "in", 12.0, "เก่า", users["admin1"]))
    exp = db.export_ledger()
    check("รายการเก่าที่ไม่มี gid/owner → ใส่ให้เองและถูกส่งเป็นรายการใหม่ (owner=admin1)",
          len(exp) == 1 and exp[0]["gid"] and exp[0]["owner"] == "admin1" and exp[0]["amount"] == 12.0, str(exp))
    res = server._ledger_sync_now("test")
    check("→ ขึ้นกลางได้", res.get("ok") and res.get("applied") == 1 and db.count_pending_ledger() == 0)

    print("\n── ตั้งค่าศูนย์กลาง: ตั้งแล้วจำค่าและเปิดเอง · ปิดได้ · ปุ่มซิงก์ทำครบ ──")
    server.auth.update_config(hub_enabled=False)
    r = c.post("/api/hub/config", json={"url": URL, "interval_min": 1})
    cfg = server.auth.load_config()
    check("บันทึก URL (มีรหัสลับอยู่แล้ว) โดยไม่ส่ง enabled → เปิดใช้เอง", r.status_code == 200 and cfg.get("hub_enabled") is True, r.get_data(as_text=True)[:120])
    r = c.post("/api/hub/config", json={"enabled": False})
    check("enabled=false ชัด ๆ → ปิด (URL/รหัสยังจำอยู่)", r.status_code == 200 and server.auth.load_config().get("hub_enabled") is False and server.auth.load_config().get("hub_url") == URL)
    r = c.post("/api/hub/config", json={"url": "", "interval_min": 1})
    check("URL ว่าง → ไม่เปิด", server.auth.load_config().get("hub_enabled") is False)
    r = c.post("/api/hub/config", json={"url": URL, "token": TOKEN})
    check("ใส่ URL+รหัสลับ → เปิดเองอีกครั้ง", server.auth.load_config().get("hub_enabled") is True)
    r = c.post("/api/hub/push", json={})
    j = r.get_json()
    check("ซิงก์เดี๋ยวนี้ → ส่งตัวเลข + สมาชิก + สมุดกองกลาง ในคำขอเดียว",
          r.status_code == 200 and j.get("ok") and j.get("members", {}).get("ok") is True and j.get("ledger", {}).get("ok") is True, str(j)[:200])
    r = c.post("/api/hub/ledger/sync")
    check("ปุ่มซิงก์บนหน้ากองกลาง → ok + สรุป", r.status_code == 200 and r.get_json().get("ok") is True and "summary" in r.get_json())
    check("สมาชิกกดปุ่มซิงก์ไม่ได้ (403) แต่ขอดึงเบื้องหลังได้", sc.post("/api/hub/ledger/sync").status_code == 403 and sc.post("/api/hub/ledger/pull").get_json().get("enabled") is True)
    st = c.get("/api/hub/state").get_json()
    check("hub/state มีผลซิงก์สมุดกองกลาง + รายการฟิลด์", st.get("ledger", {}).get("ok") is True and st.get("ledger_fields") == list(hub.LEDGER_FIELDS))
    check("ไม่มี endpoint กระดานจากศูนย์กลางแบบเก่าแล้ว (หน้ากองกลางไม่ยิงศูนย์กลางทุก 8 วิ)", c.get("/api/hub/board").status_code == 404)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code_ = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code_)
