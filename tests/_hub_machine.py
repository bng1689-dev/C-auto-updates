"""เครื่องจำลอง 'อีกเครื่องหนึ่ง' สำหรับ test_v370 — โปรเซสแยก ฐานข้อมูลของตัวเอง คุยกับศูนย์กลางจำลอง (Node) ใบเดียวกัน

    python _hub_machine.py <data_dir> <state_file> <token> [<script_admin_token>]
        (คำสั่งเป็น JSON list ทาง stdin · ตอบ JSON ทาง stdout)
    script_admin_token = ADMIN_TOKEN ที่ฝังในสคริปต์จำลอง (ไม่ใช่ของเครื่องนี้ — เครื่องนี้ใส่ผ่าน op set_admin_token)

ไม่ใช่ชุดทดสอบ — run_all ไม่รันไฟล์นี้ตรง ๆ"""
import json
import os
import subprocess
import sys
from pathlib import Path

data_dir, state_file, token = sys.argv[1:4]
script_admin = sys.argv[4] if len(sys.argv) > 4 else ""
os.environ["CRIMES_DATA_DIR"] = data_dir
os.environ["CRIMES_UPLOAD_DIR"] = str(Path(data_dir) / "up")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _app import APP  # noqa: E402,F401
from backend import server  # noqa: E402
import db  # noqa: E402
import hub  # noqa: E402


def fake_post(url, payload, tok, admin_token=None):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    param = {"sign": hub.sign(body.encode("utf-8"), tok)}
    if admin_token:
        param["asign"] = hub.sign(body.encode("utf-8"), admin_token)
    req = {"method": "POST", "body": body, "parameter": param}
    r = subprocess.run(["node", str(HERE / "gas_harness.js"), state_file, token, script_admin],
                       input=json.dumps(req), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("harness: " + r.stderr[-300:])
    return json.loads(r.stdout)


server.hub._post = fake_post
server._hub_kick = lambda *a, **k: None          # ซิงก์เมื่อสั่งเท่านั้น (ให้ผลทดสอบแน่นอน)
server.app.config["TESTING"] = True
c = server.app.test_client()


def uid_of(username):
    u = db.get_user_by_username(username)
    return u["id"] if u else None


out = {}
for cmd in json.loads(sys.stdin.read() or "[]"):
    op = cmd["op"]
    key = cmd.get("as", op)
    if op == "join":
        r = c.post("/api/setup/join", json={"hub_code": cmd["code"]})
        out[key] = [r.status_code, r.get_json()]
    elif op == "login":
        r = c.post("/api/login", json={"username": cmd["u"], "password": cmd["p"]})
        out[key] = [r.status_code, r.get_json()]
    elif op == "logout":
        out[key] = c.post("/api/logout").status_code
    elif op == "me":
        r = c.get("/api/me")
        out[key] = [r.status_code, (r.get_json() or {}).get("username")]
    elif op == "password":                       # เปลี่ยนรหัสผ่านของคนที่ล็อกอินอยู่ (ต้องรู้รหัสเดิม)
        r = c.post("/api/password", json={"current": cmd["cur"], "new": cmd["new"]})
        out[key] = [r.status_code, r.get_json()]
    elif op == "create":
        r = c.post("/api/admin/members", json={"username": cmd["u"], "password": cmd["p"],
                                               "display_name": cmd.get("name", ""), "role": cmd.get("role", "member")})
        out[key] = [r.status_code, r.get_json()]
    elif op == "update":
        r = c.put(f"/api/admin/members/{uid_of(cmd['u'])}", json=cmd["fields"])
        out[key] = [r.status_code, r.get_json()]
    elif op == "delete":
        r = c.delete(f"/api/admin/members/{uid_of(cmd['u'])}")
        out[key] = [r.status_code, r.get_json()]
    elif op == "set_admin_token":                # ใส่/ถอด 'รหัสผู้ดูแลศูนย์กลาง' ของเครื่องนี้
        server.auth.update_config(hub_admin_token=str(cmd.get("token") or ""))
        out[key] = True
    elif op == "touch":                          # จำลองนาฬิกาเครื่องเพี้ยน — ตั้ง updated_at ของคนนี้เป็นค่าที่กำหนด
        with db.get_conn() as conn:
            conn.execute("UPDATE users SET updated_at=?, sync_dirty=1 WHERE username=?", (cmd["at"], cmd["u"]))
        out[key] = True
    elif op == "sync":
        res = server._members_sync_now("test")
        out[key] = {"ok": bool(res.get("ok")), "error": res.get("error", ""), "summary": res.get("summary"),
                    "rejected": res.get("rejected"), "admin": res.get("admin")}
    elif op == "pending":
        out[key] = db.count_pending_members()
    elif op == "export":
        out[key] = db.export_members()
    elif op == "user":
        u = db.get_user_by_username(cmd["u"])
        out[key] = ({k: u.get(k) for k in ("display_name", "role", "active", "hub_rev", "sync_dirty", "updated_at")}
                    if u else None)
    elif op == "members":
        out[key] = [{"username": u["username"], "display_name": u["display_name"], "role": u["role"],
                     "active": u["active"]} for u in db.list_users()]
    elif op == "state":
        out[key] = c.get("/api/hub/members/state").get_json()
    elif op == "has_passcode":
        out[key] = db.has_passcode(uid_of(cmd["u"]))
    else:
        out[key] = f"unknown op {op}"
print(json.dumps(out, ensure_ascii=False))
