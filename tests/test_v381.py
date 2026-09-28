#!/usr/bin/env python3
"""v3.8.1 — ตาม redirect ของ Apps Script ให้ถูกชนิด (ศูนย์กลางตอบ 405 ตอนซิงก์สมาชิก)

เหตุจริง: Apps Script ตอบ 302 จาก /exec ไปที่ script.googleusercontent.com (…/macros/echo) หลังสคริปต์ทำงานเสร็จ
โปรแกรมรุ่นก่อน 'คง POST + body' ไปที่นั่นทุกกรณี — Google ตอบ 405 Method Not Allowed ได้ → ซิงก์สมาชิกล้ม
  • ปลายทาง googleusercontent.com → ตามด้วย GET ไม่มี body · ปลายทาง script.google.com อื่น (เช่น /a/macros/<โดเมน>/)
    = ยังไม่ถึงสคริปต์ → คง POST + body
  • ที่รับผลตอบ 405 ต่อ GET → ขอผลด้วย POST ที่ URL นั้น **โดยไม่ยิง /exec ซ้ำ** (รีวิว PR #32: ยิงซ้ำ = สคริปต์ทำงานสองรอบ
    แถวสมาชิกที่เพิ่งรับกลายเป็น conflict) · ข้อผิดพลาดอื่นโยนต่อเหมือนเดิม · redirect วนเกิน 6 ครั้ง → หยุด
"""
import email.message
import http.server
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v381_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "data")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
from _app import APP  # noqa: E402,F401

import db  # noqa: E402
import hub  # noqa: E402

db.init_db()      # push(presence) อ่านรายชื่อผู้ใช้จากฐานข้อมูล
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


EXEC = "https://script.google.com/macros/s/AKfycbXYZ/exec"
ECHO = "https://script-lh.googleusercontent.com/macros/echo?user_content_key=K&lib=L"
DOMAIN = "https://script.google.com/a/macros/example.go.th/s/AKfycbXYZ/exec"
OK_JSON = b'{"ok":true,"kind":"members","members":[],"rejected":[],"admin":true,"admin_ready":true}'


class FakeOpen:
    """แทน hub._open — เล่นตามสคริปต์ทีละคำขอ · จดทุกคำขอ (method, url, body)"""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, req):
        self.calls.append((req.get_method(), req.full_url.split("?")[0], req.data))
        step = self.steps.pop(0)
        if isinstance(step, int):
            raise urllib.error.HTTPError(req.full_url, step, "err", email.message.Message(), io.BytesIO(b""))
        status, loc, body = step
        h = email.message.Message()
        if loc:
            h["Location"] = loc
        return status, h, body


def run(steps, fn=None):
    fake = FakeOpen(steps)
    hub._open = fake
    try:
        res = fn() if fn else hub._post(EXEC, {"kind": "members", "members": [{"username": "x"}]}, "tok", admin_token="adm")
        return res, fake.calls, None
    except Exception as e:  # noqa: BLE001
        return None, fake.calls, e


def main():
    real_open = hub._open
    try:
        print("── ชนิดของ redirect ──")
        res, calls, err = run([(302, ECHO, b""), (200, None, OK_JSON)])
        check("POST /exec → 302 ไป googleusercontent → ตามด้วย GET ไม่มี body → ได้ผล",
              err is None and res.get("ok") is True and [c[0] for c in calls] == ["POST", "GET"]
              and calls[0][1] == EXEC and calls[1][1] == ECHO.split("?")[0] and calls[1][2] is None, f"{calls} {err}")
        check("คำขอแรกมี body + ลายเซ็นทั้ง sign และ asign", calls[0][2] is not None and b"members" in calls[0][2])
        res, calls, err = run([(302, DOMAIN, b""), (302, ECHO, b""), (200, None, OK_JSON)])
        check("302 ไป script.google.com/a/macros/<โดเมน>/ (ยังไม่ถึงสคริปต์) → คง POST + body แล้วค่อย GET ที่รับผล",
              err is None and res.get("ok") is True and [c[0] for c in calls] == ["POST", "POST", "GET"]
              and calls[1][1] == DOMAIN and calls[1][2] == calls[0][2], f"{calls} {err}")
        res, calls, err = run([(302, "/macros/echo?k=1", b""), (302, ECHO, b""), (200, None, OK_JSON)])
        check("Location แบบสัมพัทธ์ถูกต่อกับ URL เดิม", err is None and calls[1][1] == "https://script.google.com/macros/echo", str(calls))

        print("\n── ที่รับผลไม่รับ GET (405) ──")
        res, calls, err = run([(302, ECHO, b""), 405, (200, None, OK_JSON)])
        check("GET ที่รับผลได้ 405 → POST ที่ URL เดิมนั้นพร้อม body → ได้ผล",
              err is None and res.get("ok") is True and [c[0] for c in calls] == ["POST", "GET", "POST"]
              and calls[2][1] == ECHO.split("?")[0] and calls[2][2] == calls[0][2], f"{calls} {err}")
        check("ไม่ยิง /exec ซ้ำ (สคริปต์ทำงานครั้งเดียว — แถวสมาชิกไม่กลายเป็น conflict)",
              sum(1 for c in calls if c[1] == EXEC) == 1)
        res, calls, err = run([(302, ECHO, b""), 405, 405])
        check("POST ที่รับผลก็ 405 → โยน HTTPError 405 ให้ผู้เรียก (ไม่วนซ้ำ ไม่ยิง /exec)",
              isinstance(err, urllib.error.HTTPError) and err.code == 405 and len(calls) == 3)

        print("\n── ข้อผิดพลาดอื่น ──")
        res, calls, err = run([500])
        check("500 ที่ /exec → โยนต่อเหมือนเดิม ไม่ลองซ้ำ", isinstance(err, urllib.error.HTTPError) and err.code == 500 and len(calls) == 1)
        res, calls, err = run([405])
        check("405 ที่ /exec เอง (ไม่ใช่ที่รับผล) → โยนต่อ ไม่ยิงซ้ำ", isinstance(err, urllib.error.HTTPError) and err.code == 405 and len(calls) == 1)
        res, calls, err = run([(302, ECHO, b"")] * 8)
        check("redirect วนเกิน 6 ครั้ง → หยุดพร้อม URLError", isinstance(err, urllib.error.URLError) and not isinstance(err, urllib.error.HTTPError) and len(calls) == 6)
        res, calls, err = run([(302, None, b"")])
        check("302 ไม่มี Location → URLError", isinstance(err, urllib.error.URLError))
        res, calls, err = run([(302, ECHO, b""), (200, None, b"<html>oops</html>")])
        check("คำตอบไม่ใช่ JSON → dict ok=False พร้อมข้อความ (ไม่โยน)", err is None and res.get("ok") is False and "JSON" in res.get("error", ""))

        print("\n── ผ่านฟังก์ชันจริงของโปรแกรม ──")
        res, calls, err = run([(302, ECHO, b""), 405, (200, None, OK_JSON)],
                              lambda: hub.sync_members(EXEC, "tok", "inst", "3.8.1", [{"username": "a", "rev": 0}], admin_token="adm"))
        check("sync_members → ok + members/rejected/admin ครบ ผ่านทางเดิน redirect เดียวกัน",
              err is None and res.get("ok") is True and res.get("members") == [] and res.get("admin") is True and res.get("sent") == 1, f"{res} {err}")
        res, calls, err = run([(302, ECHO, b""), (200, None, b'{"ok":true,"stored":0,"kind":"presence"}')],
                              lambda: hub.push(EXEC, "tok", "", "inst", "3.8.1", presence_only=True))
        check("push (presence) → ok", err is None and res.get("ok") is True, f"{res} {err}")
        res, calls, err = run([500], lambda: hub.push(EXEC, "tok", "", "inst", "3.8.1", presence_only=True))
        check("push ได้ 500 → คืน ok=False 'ศูนย์กลางตอบ 500' ไม่โยน exception", err is None and res.get("ok") is False and "500" in res.get("error", ""))
    finally:
        hub._open = real_open

    print("\n── urllib จริง: _open ไม่ตาม redirect เอง (เซิร์ฟเวอร์จำลองในเครื่อง) ──")
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            hits.append(("POST", self.path, body))
            if self.path.startswith("/exec"):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/echo?key=1")
                self.end_headers()
            else:
                out = b'{"ok":true,"kind":"members","members":[],"rejected":[],"admin":false,"admin_ready":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        def do_GET(self):
            hits.append(("GET", self.path, None))
            self.send_response(405)
            self.end_headers()

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_port}/exec"
        res = hub._post(base, {"kind": "members", "members": []}, "tok")
        # 127.0.0.1 ไม่ใช่ googleusercontent → หลัง 302 ยังคง POST (ทางของบัญชีองค์กร) และไม่ยิง /exec ซ้ำ
        check("urllib จริง: 302 ถูกคืนให้ตัวเดิน (ไม่ตามเอง) → POST ต่อไปที่ปลายทาง → ได้ JSON",
              res.get("ok") is True and [h[0] + " " + h[1].split("?")[0] for h in hits] == ["POST /exec", "POST /echo"], str(hits))
        check("body ที่ส่งต่อหลัง redirect เท่ากับต้นฉบับ (มี kind=members และ sign ใน query)", hits[1][2] == hits[0][2] and b'"kind":"members"' in hits[0][2])
    finally:
        srv.shutdown()

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
