#!/usr/bin/env python3
"""v3.15.0 — สมาชิกทุกเครื่อง: Superadmin ตั้งสิทธิ์ได้ทุกแถว · บัญชีที่มีแค่ในเครื่องอื่นส่งคำขอสมัครเอง

เจ้าของสั่ง (กรอบเขียว 'สมาชิกทุกเครื่อง'): ให้ Superadmin แก้สิทธิ์ได้ทุกแถวแม้เครื่องนั้นออฟไลน์ — เครื่องนั้นออนไลน์แล้วรับเอง
  ปัญหาเดิม: JOJO/LIPCUP สร้างในเครื่องอื่นโดยไม่มีลายเซ็นผู้ดูแล → ศูนย์กลางปัดตก 'auth' ทุกรอบ ค้างอยู่เครื่องเดียวตลอดไป
  (Superadmin มองเห็นแค่ชื่อในตารางสถานะ แก้อะไรไม่ได้)
  เครื่อง A = Superadmin ที่ผูกสิทธิ์ผู้ดูแล (โปรเซสนี้) · เครื่อง B = เครื่องเดี่ยวที่มาเชื่อมทีหลัง (โปรเซสแยก)
  ศูนย์กลาง = tools/hub_gas.js รุ่นที่เจ้าของใช้อยู่ (3.10.0 — ไม่ต้อง deploy ใหม่) บน Node · ไม่แตะศูนย์กลางจริง
  • B ซิงก์ → บัญชีที่มีแค่ใน B ขึ้นเป็นคำขอสมัคร (แฮชจริง ไม่มีสิทธิ์) · ใน B ยังใช้งานได้ตามเดิมระหว่างรอ
  • A อนุมัติพร้อมบทบาท/สิทธิ์ (B ออฟไลน์อยู่) → B ออนไลน์ซิงก์แล้วได้ตามนั้น · ปฏิเสธ → B ปิดบัญชีนั้น
  • เปลี่ยนรหัสผ่านใน B ระหว่างรอ → คงรหัสใหม่ · อนุมัติที่เครื่อง B เองได้ (Superadmin เข้าที่ B)
  • สถานะสมาชิก (presence) ส่งชื่อผู้ใช้เฉพาะคนที่อยู่ในไดเรกทอรีแล้ว ("u:<ชื่อ>") — บัญชีในเครื่องล้วนยังเป็นเลขลำดับ
  • หน้าจอ: ตาราง 'สมาชิกทุกเครื่อง' รวมแถวรายคน + ปุ่มแก้ไข/อนุมัติ (Chromium จริง พอร์ต 8807)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v3150_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "A")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "A_up")
from _app import APP, CHROME  # noqa: E402  (CHROME = None → ตัวที่ playwright install ไว้ เช่นบน CI)

from backend import server  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = TEST_DATA / "hub_sheet.json"
TOKEN = "test-hub-token-v3150-abcdef"
ADMIN = "test-admin-v3150-Kq#7!@x"           # ADMIN_TOKEN ในสคริปต์จำลอง
URL = "https://script.google.com/macros/s/TEST3150/exec"
CODE = hub.make_connect_code(URL, TOKEN)
PORT = 8807
JS_ERRORS = []
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
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), str(STATE), TOKEN, ADMIN],
                       input=json.dumps({"method": "POST", "body": body, "parameter": param}),
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


def hub_members():
    return {m["username"]: m for m in hub.sync_members(URL, TOKEN, "probe", "3.15.0", []).get("members", [])}


def machine_b(cmds, data="B"):
    env = dict(os.environ, CRIMES_DATA_DIR=str(TEST_DATA / data), CRIMES_UPLOAD_DIR=str(TEST_DATA / (data + "_up")),
               PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "_hub_machine.py"), str(TEST_DATA / data), str(STATE), TOKEN, ADMIN],
                       input=json.dumps(cmds), env=env, capture_output=True, text=True, timeout=240)
    if r.returncode:
        raise RuntimeError("machine B: " + r.stderr[-800:])
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def perms_of(m):
    try:
        p = json.loads(m.get("permissions") or "{}") if isinstance(m.get("permissions"), str) else (m.get("permissions") or {})
    except ValueError:
        p = {}
    return {k for k, v in p.items() if v}


def main():
    server.hub._post = lambda url, payload, tok, admin_token=None, timeout=None: raw_post(payload, tok, admin_token)
    server._hub_kick = lambda *a, **k: None
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    r = c.post("/api/setup", json={"username": "boss", "password": "secret9", "password2": "secret9",
                                   "display_name": "บอส", "hub_code": CODE})
    check("(เตรียม) เครื่อง A: Superadmin + เชื่อมศูนย์กลาง", r.status_code == 200, str(r.get_json()))
    r = c.post("/api/hub/admin/bind", json={"admin_token": ADMIN, "password": "secret9"})
    check("(เตรียม) เครื่อง A: ผูก ADMIN_TOKEN กับบัญชี Superadmin", r.status_code == 200, str(r.get_json()))
    r = c.post("/api/admin/members", json={"username": "alice", "password": "alice99", "display_name": "อลิซ"})
    server._members_sync_now("manual")
    check("(เตรียม) ไดเรกทอรีกลางมี boss + alice", set(hub_members()) == {"boss", "alice"}, str(list(hub_members())))

    print("── เครื่อง B: ใช้แบบเครื่องเดี่ยวมาก่อน มีบัญชีในเครื่อง (JOJO/LIPCUP แบบที่เจ้าของเจอ) ──")
    b = machine_b([
        {"op": "setup_local", "u": "bossb", "p": "bossb99", "name": "บอส B"},
        {"op": "create", "u": "jojo", "p": "jojo111", "name": "JOJO", "as": "c1"},
        {"op": "post", "path": "/api/admin/members", "as": "c2",
         "json": {"username": "lipcup", "password": "lip2222", "display_name": "LIPCUP",
                  "permissions": {"view_team": True}}},
        {"op": "create", "u": "temp9", "p": "temp999", "name": "ชั่วคราว", "as": "c3"},
        {"op": "presence_rows", "as": "pres0"},
        {"op": "connect", "code": CODE},
        {"op": "sync", "as": "s1"},
        {"op": "user_full", "u": "jojo", "as": "jojo"},
        {"op": "user_full", "u": "lipcup", "as": "lipcup"},
        {"op": "user_full", "u": "bossb", "as": "bossb"},
        {"op": "pending", "as": "pend"},
        {"op": "export", "as": "exp"},
        {"op": "presence_rows", "as": "pres1"},
        {"op": "state", "as": "state"},
    ])
    check("(เตรียม) B ตั้งค่าเครื่องเดี่ยว + สร้าง 3 บัญชีได้ (ยังไม่เชื่อมศูนย์กลาง)",
          b["setup_local"][0] == 200 and b["c1"][0] == 200 and b["c2"][0] == 200 and b["c3"][0] == 200,
          str([b["setup_local"], b["c1"], b["c2"], b["c3"]])[:300])
    check("ก่อนเชื่อม: สถานะสมาชิกส่งเป็นเลขลำดับในเครื่อง (ชื่อผู้ใช้ยังไม่ออกจากเครื่อง)",
          all(isinstance(p["uid"], int) for p in b["pres0"]) and len(b["pres0"]) == 4, str(b["pres0"]))
    check("เชื่อมศูนย์กลางทีหลังได้ (วางรหัสเชื่อมต่อ)", b["connect"][0] == 200, str(b["connect"]))
    s1 = b["s1"]
    hm = hub_members()
    check("ซิงก์แรกหลังเชื่อม: ศูนย์กลางรับทุกบัญชีในเครื่อง B เป็นคำขอสมัครในรอบเดียว (ไม่ค้าง 'auth' แบบเดิม)",
          s1["ok"] and not [x for x in (s1["rejected"] or []) if x.get("reason") == "auth"]
          and {"jojo", "lipcup", "temp9", "bossb"} <= set(hm), str(s1)[:400])
    check("summary.requested บอกชื่อที่ส่งคำขอ", set((s1["summary"] or {}).get("requested") or []) ==
          {"jojo", "lipcup", "temp9", "bossb"}, str((s1["summary"] or {}).get("requested")))
    req_ok = all(_truthy(hm[u].get("pending")) and not _truthy(hm[u].get("active")) and hm[u].get("role") == "member"
                 and not perms_of(hm[u]) and len(str(hm[u].get("password_hash") or "")) == 64
                 for u in ("jojo", "lipcup", "temp9", "bossb"))
    check("บนศูนย์กลาง: เป็นคำขอแบบที่สคริปต์ 3.10.0 รับ (pending · ปิดอยู่ · member · ไม่มีสิทธิ์ · แฮชจริง)",
          req_ok, str({u: {k: hm[u].get(k) for k in ("pending", "active", "role", "permissions")} for u in ("jojo", "lipcup")}))
    check("แฮชบนศูนย์กลาง = แฮชในเครื่อง B (ไม่ต้องตั้งรหัสใหม่)",
          str(hm["jojo"]["password_hash"])[-8:] == b["jojo"]["pw_tail"])
    check("คำขอไม่ติดบทบาท/สิทธิ์จากเครื่อง B (bossb ไม่กลายเป็น Superadmin ขององค์กร · LIPCUP ไม่มี 👪 บนกลาง)",
          hm["bossb"]["role"] == "member" and not perms_of(hm["lipcup"]))
    j = b["jojo"]
    check("ใน B ระหว่างรอ: ยังใช้งานได้ตามเดิม (active · ไม่ใช่ pending) · ธง join_req · จด rev ของคำขอ",
          j["active"] == 1 and j["pending"] == 0 and j["join_req"] == 1 and j["hub_rev"] > 0 and j["sync_dirty"] == 0, str(j))
    check("ใน B ระหว่างรอ: สิทธิ์/บทบาทเดิมในเครื่องไม่ถูกลบ (LIPCUP ยังมี 👪 · bossb ยังเป็น Superadmin ของเครื่อง)",
          b["lipcup"]["permissions"].get("view_team") is True and b["bossb"]["role"] == "super_admin", str(b["lipcup"]))
    check("ไม่ขึ้น 'รอส่ง' ค้างตลอดไปแล้ว (คำขอไม่นับเป็นรายการค้างส่ง) · ไม่ส่งซ้ำ",
          b["pend"] == 0 and not b["exp"], str(b["pend"]) + str(b["exp"])[:200])
    check("/api/hub/members/state บอกจำนวนที่ส่งคำขอ", (b["state"].get("last") or {}).get("requested") == 4,
          str(b["state"].get("last"))[:300])
    pres = {p["display_name"]: p["uid"] for p in b["pres1"]}
    check("หลังส่งคำขอ: สถานะสมาชิกใช้ 'u:<ชื่อผู้ใช้>' (ศูนย์กลางรู้จักชื่อนี้แล้ว — จับคู่กับไดเรกทอรีได้)",
          pres.get("JOJO") == "u:jojo" and pres.get("LIPCUP") == "u:lipcup" and pres.get("บอส") == "u:boss", str(pres))

    rev_jojo = hm["jojo"]["rev"]
    b = machine_b([
        {"op": "login", "u": "jojo", "p": "jojo111"},
        {"op": "password", "cur": "jojo111", "new": "jojo222new"},
        {"op": "logout"},
        {"op": "login", "u": "bossb", "p": "bossb99", "as": "login_b"},
        {"op": "update", "u": "lipcup", "fields": {"display_name": "แก้เอง"}, "as": "upd"},
        {"op": "sync", "as": "s2"},
        {"op": "user_full", "u": "jojo", "as": "jojo"},
        {"op": "pending", "as": "pend"},
    ])
    check("ระหว่างรอ: JOJO เข้าสู่ระบบใน B ได้ + เปลี่ยนรหัสผ่านตัวเองได้", b["login"][0] == 200 and b["password"][0] == 200,
          str([b["login"], b["password"]]))
    check("ระหว่างรอ: แก้บัญชีที่ส่งคำขอแล้วไม่ได้ (400 · บอกให้อนุมัติ) — ค่ามาจาก Superadmin เท่านั้น",
          b["upd"][0] == 400 and (b["upd"][1] or {}).get("join_req") is True, str(b["upd"]))
    check("รหัสใหม่ระหว่างรอไม่ถูกส่งซ้ำเป็นคำขอใหม่ (rev บนกลางเท่าเดิม) และไม่ค้าง 'รอส่ง'",
          hub_members()["jojo"]["rev"] == rev_jojo and b["pend"] == 0, str(b["pend"]))
    jojo_tail_new = b["jojo"]["pw_tail"]

    print("\n── Codex P1 (PR #45): เครื่อง D มีบัญชีในเครื่องชื่อ 'lipcup' ซ้ำกับคำขอที่ B ส่งไว้ ──")
    lip_hub_hash = hub_members()["lipcup"]["password_hash"]
    d = machine_b([
        {"op": "setup_local", "u": "ownerd", "p": "ownerd99", "name": "เจ้าของ D"},
        {"op": "create", "u": "lipcup", "p": "dlip999", "name": "LIP (D)"},
        {"op": "connect", "code": CODE},
        {"op": "sync", "as": "s1"},
        {"op": "user_full", "u": "lipcup", "as": "lip"},
        {"op": "pending", "as": "pend"},
        {"op": "logout"},
        {"op": "login", "u": "lipcup", "p": "dlip999", "as": "login_lip"},
        {"op": "logout", "as": "lo2"},
        {"op": "login", "u": "boss", "p": "secret9", "as": "login_boss"},
        {"op": "approve", "u": "lipcup", "fields": {"role": "member"}, "as": "ap"},
    ], data="D")
    hm = hub_members()
    check("D: บัญชีในเครื่องชื่อซ้ำกับคำขอของ B ไม่ถูกทับ — ยังเปิดใช้งาน · แฮชของ D เอง · เข้าสู่ระบบได้ระหว่างรอ",
          d["lip"]["active"] == 1 and d["lip"]["pending"] == 0 and d["lip"]["join_req"] == 2
          and d["login_lip"][0] == 200, str([d["lip"], d["login_lip"]])[:300])
    check("D: คำขอของ B บนศูนย์กลางไม่ถูกเครื่อง D ทับ (แฮชเดิม) · ไม่ค้าง 'รอส่ง'",
          hm["lipcup"]["password_hash"] == lip_hub_hash and _truthy(hm["lipcup"]["pending"]) and d["pend"] == 0,
          str(d["pend"]))
    check("D: อนุมัติชื่อซ้ำที่เครื่อง D ไม่ได้ (จะส่งรหัสของ D ทับคำขอของ B) → 400",
          d["login_boss"][0] == 200 and d["ap"][0] == 400 and (d["ap"][1] or {}).get("join_req") is True, str(d["ap"]))

    print("\n── เครื่อง A (B ออฟไลน์): เห็นคำขอ → อนุมัติพร้อมสิทธิ์ · ปฏิเสธ · แก้ต่อได้ ──")
    server._members_sync_now("manual")
    lst = {m["username"]: m for m in c.get("/api/admin/members").get_json()}
    check("A เห็นบัญชีจาก B เป็นคำขอรออนุมัติ", all(lst.get(u, {}).get("pending") for u in ("jojo", "lipcup", "temp9", "bossb")),
          str({u: lst.get(u, {}).get("pending") for u in ("jojo", "lipcup", "temp9", "bossb")}))
    r = c.post(f"/api/admin/members/{lst['jojo']['id']}/approve",
               json={"role": "member", "display_name": "JOJO", "permissions": {"view_team": True, "view_live": True}})
    check("A อนุมัติ JOJO พร้อมสิทธิ์ 👪📡", r.status_code == 200, str(r.get_json()))
    r = c.delete(f"/api/admin/members/{lst['temp9']['id']}")
    check("A ปฏิเสธ temp9", r.status_code == 200, str(r.get_json()))
    res = server._members_sync_now("manual")
    r = c.put(f"/api/admin/members/{lst['jojo']['id']}", json={"display_name": "JOJO-A",
                                                                 "permissions": {"view_team": True, "view_live": True,
                                                                                 "manage_billing": True}})
    res2 = server._members_sync_now("manual")
    hm = hub_members()
    check("ผลอนุมัติ + การแก้สิทธิ์ต่อขึ้นศูนย์กลาง (เครื่อง B ยังออฟไลน์)",
          res.get("ok") and res2.get("ok") and r.status_code == 200 and not _truthy(hm["jojo"]["pending"])
          and _truthy(hm["jojo"]["active"]) and perms_of(hm["jojo"]) == {"view_team", "view_live", "manage_billing"}
          and hm["jojo"]["display_name"] == "JOJO-A" and _truthy(hm["temp9"].get("deleted")), str(hm["jojo"])[:300])

    print("\n── เครื่อง B กลับมาออนไลน์ → ได้ค่าที่ Superadmin ตั้งเอง ──")
    b = machine_b([
        {"op": "sync", "as": "s3"},
        {"op": "user_full", "u": "jojo", "as": "jojo"},
        {"op": "user_full", "u": "temp9", "as": "temp9"},
        {"op": "user_full", "u": "lipcup", "as": "lipcup"},
        {"op": "pending", "as": "pend"},
        {"op": "sync", "as": "s4"},
        {"op": "pending", "as": "pend2"},
        {"op": "login_full", "u": "temp9", "p": "temp999", "as": "login_t9"},
        {"op": "login", "u": "jojo", "p": "jojo111", "as": "login_old"},
        {"op": "login", "u": "jojo", "p": "jojo222new", "as": "login_new"},
        {"op": "me", "as": "me_j"},
    ])
    s3 = b["s3"]["summary"] or {}
    check("summary.decided บอกบัญชีที่ Superadmin ตัดสินแล้ว", {"jojo", "temp9"} <= set(s3.get("decided") or []),
          str(s3.get("decided")))
    j = b["jojo"]
    check("JOJO ใน B: เปิดใช้งาน · บทบาท/สิทธิ์/ชื่อตามที่ Superadmin ตั้ง · หลุดธงรอ",
          j["active"] == 1 and j["pending"] == 0 and j["join_req"] == 0 and j["role"] == "member"
          and {k for k, v in j["permissions"].items() if v} == {"view_team", "view_live", "manage_billing"}
          and j["display_name"] == "JOJO-A", str(j))
    hm = hub_members()
    check("รหัสผ่านที่ JOJO เปลี่ยนระหว่างรอยังอยู่ (ไม่ถูกแฮชเก่าบนกลางทับ) และขึ้นศูนย์กลางในซิงก์รอบเดียวกัน"
          " ('เปลี่ยนรหัสตัวเอง' ไม่ต้องลายเซ็น) · ไม่ค้างส่ง",
          j["pw_tail"] == jojo_tail_new and b["pend"] == 0 and str(hm["jojo"]["password_hash"])[-8:] == jojo_tail_new,
          str(b["pend"]))
    check("ซิงก์รอบถัดไปไม่มีอะไรค้าง", b["s4"]["ok"] and b["pend2"] == 0, str(b["s4"])[:300])
    check("JOJO เข้าด้วยรหัสใหม่ได้ · รหัสเดิมใช้ไม่ได้", b["login_new"][0] == 200 and b["login_old"][0] != 200
          and b["me_j"][1] == "jojo", str([b["login_old"][0], b["login_new"]]))
    check("temp9 ที่ถูกปฏิเสธ: ปิดใช้งานใน B · เข้าสู่ระบบไม่ได้",
          (b["temp9"] is None or b["temp9"]["active"] == 0) and b["login_t9"][0] != 200, str([b["temp9"], b["login_t9"]]))
    check("LIPCUP ที่ยังไม่ตัดสิน: ยังรออยู่ ใช้งานในเครื่องได้ (ไม่โดนอะไร)",
          b["lipcup"]["join_req"] == 1 and b["lipcup"]["active"] == 1, str(b["lipcup"]))
    server._members_sync_now("manual")
    check("A ได้รหัสใหม่ของ JOJO ด้วย (แฮชตรงกันทุกเครื่อง)",
          db.get_user_by_username("jojo")["password_hash"][-8:] == jojo_tail_new)

    print("\n── อนุมัติที่เครื่อง B เอง: Superadmin เข้าสู่ระบบที่ B แล้วกดอนุมัติ ──")
    b = machine_b([
        {"op": "login", "u": "bossb", "p": "bossb99", "as": "login_b"},
        {"op": "approve", "u": "lipcup", "fields": {"role": "member", "permissions": {"view_live": True}}, "as": "ap_b"},
        {"op": "logout"},
        {"op": "login", "u": "boss", "p": "secret9", "as": "login_boss"},
        {"op": "hold", "as": "hold"},
        {"op": "list_api", "as": "lst"},
        {"op": "approve", "u": "lipcup", "fields": {"role": "member", "display_name": "LIPCUP",
                                                    "permissions": {"view_live": True}}, "as": "ap"},
        {"op": "sync", "as": "s5"},
        {"op": "user_full", "u": "lipcup", "as": "lipcup"},
    ])
    check("Superadmin ประจำเครื่อง B (ยังเป็นคำขอ ไม่ถือสิทธิ์ผู้ดูแล) อนุมัติไม่ได้",
          b["login_b"][0] == 200 and b["ap_b"][0] in (403, 423), str(b["ap_b"]))
    lst_b = b["lst"][1] if isinstance(b["lst"], list) and isinstance(b["lst"][1], list) else []
    lip = {m["username"]: m for m in lst_b}.get("lipcup") or {}
    check("/api/admin/members บอก join_req ให้หน้าจอ (แถวรออนุมัติจากศูนย์กลาง)", lip.get("join_req") == 1, str(lip)[:200])
    check("Superadmin ขององค์กรเข้าที่ B → ถือสิทธิ์ผู้ดูแล → อนุมัติบัญชีในเครื่องนี้ได้",
          b["login_boss"][0] == 200 and b["hold"] == "boss" and b["ap"][0] == 200, str([b["hold"], b["ap"]]))
    hm = hub_members()
    check("ผลอนุมัติจาก B ขึ้นศูนย์กลาง (ลายเซ็นผู้ดูแล) · B ได้ค่าตามที่ตั้ง",
          b["s5"]["ok"] and not _truthy(hm["lipcup"]["pending"]) and _truthy(hm["lipcup"]["active"])
          and perms_of(hm["lipcup"]) == {"view_live"} and b["lipcup"]["join_req"] == 0
          and b["lipcup"]["permissions"] == {k: k == "view_live" for k in b["lipcup"]["permissions"]}
          and str(hm["lipcup"]["password_hash"])[-8:] == b["lipcup"]["pw_tail"], str([hm["lipcup"], b["lipcup"]])[:400])

    d = machine_b([
        {"op": "sync", "as": "s"},
        {"op": "user_full", "u": "lipcup", "as": "lip"},
        {"op": "login", "u": "lipcup", "p": "dlip999", "as": "login_d"},
        {"op": "login", "u": "lipcup", "p": "lip2222", "as": "login_b"},
    ], data="D")
    check("D หลังอนุมัติ: ได้ค่าและรหัสผ่านตามคำขอที่ Superadmin อนุมัติ (ของ B) — รหัสของ D ใช้ไม่ได้ (กันยึดบัญชีผู้ขอ)",
          d["lip"]["join_req"] == 0 and d["lip"]["active"] == 1 and d["lip"]["permissions"].get("view_live") is True
          and d["lip"]["pw_tail"] == str(hub_members()["lipcup"]["password_hash"])[-8:]
          and d["login_d"][0] != 200 and d["login_b"][0] == 200, str([d["lip"], d["login_d"][0], d["login_b"][0]]))

    print("\n── บทบาทมาจาก Superadmin: อนุมัติ bossb เป็นสมาชิกธรรมดา ──")
    server._members_sync_now("manual")
    bid = db.get_user_by_username("bossb")["id"]
    r = c.post(f"/api/admin/members/{bid}/approve", json={"role": "member", "permissions": {"view_team": True}})
    server._members_sync_now("manual")
    b = machine_b([{"op": "sync"}, {"op": "user_full", "u": "bossb", "as": "bossb"},
                   {"op": "login", "u": "bossb", "p": "bossb99", "as": "login_b"}])
    check("bossb ใน B กลายเป็นสมาชิกตามที่อนุมัติ (Superadmin ประจำเครื่องเดิมไม่คงอยู่) · ยังเข้าใช้ได้",
          r.status_code == 200 and b["bossb"]["role"] == "member" and b["bossb"]["join_req"] == 0
          and b["bossb"]["active"] == 1 and b["login_b"][0] == 200, str(b["bossb"]))

    print("\n── เจ้าขององค์กรเองตั้งเครื่อง C แบบเครื่องเดี่ยวก่อน → เชื่อม (กลายเป็นคำขอ) → ผูก ADMIN_TOKEN ได้ ──")
    cc = machine_b([
        {"op": "setup_local", "u": "ownerc", "p": "ownerc99", "name": "เจ้าของ C"},
        {"op": "connect", "code": CODE},
        {"op": "sync", "as": "s1"},
        {"op": "user_full", "u": "ownerc", "as": "before"},
        {"op": "bind", "token": ADMIN, "p": "ownerc99"},
        {"op": "user_full", "u": "ownerc", "as": "after"},
        {"op": "hold", "as": "hold"},
    ], data="C")
    hm = hub_members()
    check("C: Superadmin ของเครื่องเดี่ยวส่งเป็นคำขอเมื่อองค์กรมี Superadmin แล้ว", cc["before"]["join_req"] == 1
          and "ownerc" in ((cc["s1"]["summary"] or {}).get("requested") or []), str(cc["before"]))
    check("C: ผูก ADMIN_TOKEN ตัวจริงกับบัญชีที่ยังเป็นคำขอได้ → ศูนย์กลางรับเป็น Superadmin (ลายเซ็นแทนการอนุมัติ)",
          cc["bind"][0] == 200 and cc["hold"] == "ownerc" and cc["after"]["join_req"] == 0
          and cc["after"]["role"] == "super_admin" and hm["ownerc"]["role"] == "super_admin"
          and not _truthy(hm["ownerc"]["pending"]) and _truthy(hm["ownerc"]["active"]),
          str([cc["bind"], cc["after"], {k: hm["ownerc"].get(k) for k in ("role", "pending", "active")}])[:500])

    print("\n── คำขอหายจากศูนย์กลาง (ชีตถูกล้าง) → ส่งเป็นคำขอใหม่ ไม่ค้างตลอดไป ──")
    uid = db.create_user("ghost7", "ghost77", display_name="ผี")
    with db.get_conn() as conn:
        # ค้างส่งรหัสใหม่ของเจ้าของอยู่ด้วย (sync_dirty=1) — ต้องไม่ค้างตลอดไป
        conn.execute("UPDATE users SET join_req=1, hub_rev=9, sync_dirty=1, sync_signed=1 WHERE id=?", (uid,))
    db.apply_remote_members(list(hub_members().values()), full_directory=True)
    ex = [x for x in db.export_members(signed=False, as_requests=True) if x["username"] == "ghost7"]
    check("แถวที่กลางไม่มีแล้ว: หลุดธงรอ · ส่งใหม่เป็นคำขอ (ไม่ใช่แถวลงนาม)",
          len(ex) == 1 and ex[0]["pending"] == 1 and ex[0]["rev"] == 0 and ex[0]["role"] == "member", str(ex))
    with db.get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (uid,))

    print("\n── กรอบเขียว 'สมาชิกทุกเครื่อง' บนหน้าจอจริง (Chromium) ──")
    ui_checks()

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


def _truthy(v):
    return v not in (None, "", 0, "0", False, "false", "FALSE")


def ui_checks():
    me_install = server.auth.load_config().get("install_id", "")
    # สถานะสมาชิกจากศูนย์กลาง (ปลอมเฉพาะส่วนนี้ — ไดเรกทอรีในเครื่อง A มาจากซิงก์จริงข้างบน)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    old = "2026-01-02T03:04:05Z"
    presence = [
        {"install_id": me_install, "uid": "u:boss", "display_name": "บอส", "app_version": "3.15.0",
         "last_seen": now, "received_at": now},
        {"install_id": "B-inst-0001", "uid": "u:jojo", "display_name": "JOJO-A", "app_version": "3.15.0",
         "last_seen": old, "received_at": old},
        {"install_id": "C-inst-0002", "uid": "u:jojo", "display_name": "JOJO-A", "app_version": "3.14.1",
         "last_seen": now, "received_at": now},
        {"install_id": "B-inst-0001", "uid": "u:bossb", "display_name": "บอส B", "app_version": "3.15.0",
         "last_seen": old, "received_at": old},
        {"install_id": "D-inst-0003", "uid": 3, "display_name": "MOMO", "app_version": "3.14.1",
         "last_seen": old, "received_at": old},
        {"install_id": "B-inst-0001", "uid": "u:newreq", "display_name": "คนใหม่", "app_version": "3.15.0",
         "last_seen": old, "received_at": old},
    ]
    server.hub.fetch_board = lambda url, token, ym: {"ok": True, "presence": presence, "rows": [], "totals": {}}
    # คำขอรออนุมัติที่ยังมีอยู่บนกลาง (ให้มีปุ่ม 'อนุมัติ' ในตาราง) — ส่งจาก 'เครื่อง B' ด้วยรหัสร่วมอย่างเดียว
    salt = "ab" * 16
    raw_post(hub.build_members_payload("B-inst-0001", "3.15.0", [
        {"username": "newreq", "display_name": "คนใหม่", "role": "member", "permissions": "{}",
         "active": 0, "pending": 1, "password_hash": "c" * 64, "salt": salt, "rate_per_name": None,
         "teams": "[]", "rev": 0, "deleted": 0, "created_at": "", "updated_at": ""}]))
    server._members_sync_now("manual")
    server.app.config["TESTING"] = False
    th = threading.Thread(target=lambda: server.app.run(port=PORT, threaded=True, use_reloader=False), daemon=True)
    th.start()
    time.sleep(1.2)
    from playwright.sync_api import sync_playwright
    base = f"http://127.0.0.1:{PORT}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True,
                                     args=["--disable-background-networking", "--disable-component-update",
                                           "--no-first-run", "--no-default-browser-check"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, timezone_id="Asia/Bangkok")
        page = ctx.new_page()
        page.on("pageerror", lambda e: JS_ERRORS.append(f"pageerror: {e}"))
        page.on("console", lambda m: JS_ERRORS.append(f"console.error: {m.text}") if m.type == "error" else None)
        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_selector("#authLoginForm", state="attached", timeout=15000)
        page.evaluate("()=>{ if(typeof showAuth==='function') showAuth('login'); }")
        page.fill("#authLoginUser", "boss")
        page.fill("#authLoginPw", "secret9")
        page.click("#authLoginForm button[type=submit]")
        page.wait_for_selector("#screen-app:not(.hidden)", timeout=15000)
        page.click('.nav-item[data-view="members"]')
        page.wait_for_selector("#presenceList table", timeout=15000)
        page.wait_for_timeout(400)
        rows = page.evaluate("""()=>[...document.querySelectorAll('#presenceList tbody tr')].map(tr=>({
            key: tr.dataset.pkey || '', text: tr.innerText, machines: tr.querySelectorAll('.pmach').length,
            edit: !!tr.querySelector('button[data-act=edit]'), approve: !!tr.querySelector('button[data-act=approve]'),
            chips: tr.querySelectorAll('.pchip').length, crown: !!tr.querySelector('.pchip.crown')}))""")
        by = {r["key"]: r for r in rows}
        check("รวมแถวรายคน: JOJO ใช้ 2 เครื่อง = แถวเดียว แสดง 2 เครื่อง", by.get("u:jojo", {}).get("machines") == 2
              and sum(1 for r in rows if r["key"] == "u:jojo") == 1, str(rows)[:500])
        check("แถวสมาชิกในไดเรกทอรี: ปุ่ม 'แก้ไข' + สัญลักษณ์สิทธิ์ (ตั้งสิทธิ์ได้แม้เครื่องนั้นออฟไลน์)",
              by.get("u:jojo", {}).get("edit") and by["u:jojo"]["chips"] >= 7 and not by["u:jojo"]["approve"], str(by.get("u:jojo")))
        check("Superadmin แสดง 👑 ครบทุกข้อ", by.get("u:boss", {}).get("crown") is True, str(by.get("u:boss")))
        check("คำขอที่ยังรอ: ปุ่ม 'อนุมัติ' ในแถว (ไม่ใช่ 'แก้ไข')", by.get("u:newreq", {}).get("approve")
              and not by["u:newreq"]["edit"] and "รออนุมัติ" in by["u:newreq"]["text"], str(by.get("u:newreq")))
        local = [r for r in rows if r["key"].startswith("local:")]
        check("บัญชีที่มีแค่ในเครื่องนั้น (รุ่นเก่า): ป้ายบอกว่าจะส่งคำขอเองเมื่ออัปเดตเป็น 3.15.0 · ไม่มีปุ่มแก้",
              len(local) == 1 and "3.15.0" in local[0]["text"] and not local[0]["edit"] and not local[0]["approve"],
              str(local))
        check("หัวกรอบบอกว่าแก้แล้วมีผลเมื่อเครื่องนั้นออนไลน์",
              "ออนไลน์" in page.inner_text("#presenceCard") and "ซิงก์" in page.inner_text("#presenceCard"))
        page.click('#presenceList tr[data-pkey="u:jojo"] button[data-act=edit]')
        page.wait_for_selector("#memberModal:not(.hidden)", timeout=5000)
        title = page.inner_text("#memberModalTitle")
        checked = page.evaluate("()=>[...document.querySelectorAll('#mPermChecks input:checked')].map(c=>c.value).sort()")
        check("กด 'แก้ไข' จากแถวสถานะ → เปิดกล่องแก้ไขสมาชิกคนนั้นพร้อมสิทธิ์ปัจจุบัน",
              "jojo" in title and checked == ["manage_billing", "view_live", "view_team"], f"{title} {checked}")
        page.evaluate("()=>{ const c=[...document.querySelectorAll('#mPermChecks input')].find(x=>x.value==='view_audit'); c.checked=true; }")
        page.click("#btnMemberSave")
        page.wait_for_selector("#memberModal", state="hidden", timeout=8000)
        page.wait_for_timeout(300)
        check("บันทึกจากกล่องนั้น → สิทธิ์เปลี่ยนในเครื่อง + ค้างส่งขึ้นศูนย์กลาง (เครื่องนั้นได้เมื่อออนไลน์)",
              db.get_permissions(db.get_user_by_username("jojo")["id"]).get("view_audit") is True
              and db.count_pending_members() >= 1)
        page.click('#presenceList tr[data-pkey="u:newreq"] button[data-act=approve]')
        page.wait_for_selector("#memberModal:not(.hidden)", timeout=5000)
        check("กด 'อนุมัติ' จากแถวสถานะ → เปิดกล่องอนุมัติคำขอ", "อนุมัติ" in page.inner_text("#memberModalTitle"))
        page.click("#btnMemberCancel")
        page.wait_for_timeout(200)
        # ตารางสมาชิกหลัก: แถว join_req (บัญชีในเครื่องนี้ที่ส่งคำขอแล้ว) มีป้าย + ไม่มีปุ่มแก้ไข
        uid = db.create_user("waitme", "waitme9", display_name="รออยู่")
        with db.get_conn() as conn:
            conn.execute("UPDATE users SET join_req=1, hub_rev=3, sync_dirty=0 WHERE id=?", (uid,))
        page.evaluate("()=>loadMembers()")
        page.wait_for_timeout(800)
        info = page.evaluate("""id=>{ const b=[...document.querySelectorAll('#memberList button')].filter(x=>(x.getAttribute('onclick')||'').includes('('+id));
            const tr=b.length? b[0].closest('tr') : null;
            return {text: tr? tr.innerText : '', edit: b.some(x=>(x.getAttribute('onclick')||'').startsWith('editMember')),
                    approve: b.some(x=>(x.getAttribute('onclick')||'').startsWith('approveMember')),
                    pend: document.querySelector('#pendingList') ? document.querySelector('#pendingList').innerText : ''}; }""", uid)
        check("ตารางสมาชิก: บัญชีในเครื่องที่ส่งคำขอแล้ว → ป้ายรออนุมัติ · ปุ่มอนุมัติแทนแก้ไข · อยู่ในกล่องคำขอด้วย",
              "รออนุมัติ" in info["text"] and info["approve"] and not info["edit"] and "waitme" in info["pend"], str(info))
        with db.get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
        # 401 ก่อนเข้าสู่ระบบ = สถานะ HTTP ที่คาดไว้ ไม่ใช่ JS error (เหมือน test_ui_smoke/test_v3140)
        real = [e for e in JS_ERRORS if "favicon" not in e and not ("Failed to load resource" in e and
                any(f"status of {c}" in e for c in (400, 401, 403, 409)))]
        check("ไม่มี JS error บนหน้าสมาชิก", not real, str(real[:3]))
        browser.close()


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
raise SystemExit(code)
