#!/usr/bin/env python3
"""v3.8.1 — ตาม redirect ของ Apps Script ให้ถูกชนิด (ศูนย์กลางตอบ 405 ตอนซิงก์สมาชิก)

เหตุจริง: Apps Script ตอบ 302 จาก /exec ไปที่ script.googleusercontent.com (…/macros/echo) หลังสคริปต์ทำงานเสร็จ
โปรแกรมรุ่นก่อน 'คง POST + body' ไปที่นั่นทุกกรณี — Google ตอบ 405 Method Not Allowed ได้ → ซิงก์สมาชิกล้ม
  • ปลายทาง googleusercontent.com → ตามด้วย GET ไม่มี body (มาตรฐาน) · ปลายทาง script.google.com อื่น (เช่น /a/macros/<โดเมน>/)
    = ยังไม่ถึงสคริปต์ → คง POST + body
  • ถ้าแบบใหม่ถูกปฏิเสธ 405 → ลองแบบเดิม (คง POST ทุกกรณี) อีกครั้งเดียว · ข้อผิดพลาดอื่นโยนต่อเหมือนเดิม
"""
import email.message
import io
import json
import os
import shutil
import sys
import tempfile
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


BODY = b'{"kind":"members"}'
EXEC = "https://script.google.com/macros/s/AKfycbXYZ/exec?sign=abc&asign=def"
ECHO = "https://script-lh.googleusercontent.com/macros/echo?user_content_key=K&lib=L"
DOMAIN = "https://script.google.com/a/macros/example.go.th/s/AKfycbXYZ/exec?sign=abc&asign=def"


def redirect(handler_cls, newurl, method="POST"):
    req = urllib.request.Request(EXEC, data=BODY if method == "POST" else None, method=method,
                                 headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": "CRIMES-AUTO-Hub"})
    hdr = email.message.Message()
    hdr["Location"] = newurl
    return handler_cls().redirect_request(req, io.BytesIO(b""), 302, "Found", hdr, newurl)


def main():
    print("── ชนิดของ redirect ──")
    r = redirect(hub._KeepPostRedirect, ECHO)
    check("302 ไป googleusercontent (ที่รับผลหลังสคริปต์ทำงานแล้ว) → ตามด้วย GET ไม่มี body",
          r is not None and r.get_method() == "GET" and r.data is None and r.full_url == ECHO, f"{r and r.get_method()} {r and r.data}")
    r = redirect(hub._KeepPostRedirect, DOMAIN)
    check("302 ไป script.google.com/a/macros/<โดเมน>/ (ยังไม่ถึงสคริปต์) → คง POST + body + header เดิม",
          r is not None and r.get_method() == "POST" and r.data == BODY and r.full_url == DOMAIN
          and r.get_header("Content-type", "").startswith("text/plain"), f"{r and r.get_method()}")
    r = redirect(hub._AlwaysPostRedirect, ECHO)
    check("แผนสำรอง (_AlwaysPostRedirect) คง POST + body แม้ไป googleusercontent",
          r is not None and r.get_method() == "POST" and r.data == BODY)
    r = redirect(hub._KeepPostRedirect, ECHO, method="GET")
    check("คำขอ GET (กระดานรวม) redirect ตามปกติ", r is not None and r.get_method() == "GET")

    print("\n── _post: แผนสำรองเมื่อได้ 405 ──")
    calls = []

    class _Resp:
        def __init__(self, raw):
            self.raw = raw

        def read(self):
            return self.raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_build_opener(handler):
        class _Opener:
            def open(self, req, timeout=None):
                calls.append((handler, req.get_method(), req.data))
                if handler is hub._KeepPostRedirect and len(calls) == 1:
                    raise urllib.error.HTTPError(req.full_url, 405, "Method Not Allowed", email.message.Message(), io.BytesIO(b""))
                return _Resp(b'{"ok":true,"kind":"members","members":[],"rejected":[],"admin":true,"admin_ready":true}')
        return _Opener()

    real = urllib.request.build_opener
    hub.urllib.request.build_opener = fake_build_opener
    try:
        res = hub._post("https://script.google.com/macros/s/X/exec", {"kind": "members", "members": []}, "tok", admin_token="adm")
        check("405 จากแบบใหม่ → ลองแบบเดิม (คง POST ทุกกรณี) อีกครั้งแล้วได้ผล",
              res.get("ok") is True and len(calls) == 2 and calls[0][0] is hub._KeepPostRedirect
              and calls[1][0] is hub._AlwaysPostRedirect and calls[1][1] == "POST" and calls[1][2] == calls[0][2], str(calls))
        check("ทั้งสองครั้งส่ง body เดียวกันและมี asign ในคำขอ", calls[0][2] == calls[1][2] and b"members" in calls[0][2])
        calls.clear()

        def fake_build_opener_500(handler):
            class _Opener:
                def open(self, req, timeout=None):
                    calls.append(handler)
                    raise urllib.error.HTTPError(req.full_url, 500, "Server Error", email.message.Message(), io.BytesIO(b""))
            return _Opener()
        hub.urllib.request.build_opener = fake_build_opener_500
        try:
            hub._post("https://script.google.com/macros/s/X/exec", {"kind": "presence"}, "tok")
            raised = None
        except urllib.error.HTTPError as e:
            raised = e.code
        check("ข้อผิดพลาดอื่น (500) โยนต่อเหมือนเดิม ไม่ลองซ้ำ", raised == 500 and len(calls) == 1)
        hub.urllib.request.build_opener = fake_build_opener
        calls.clear()
        res = hub.sync_members("https://script.google.com/macros/s/X/exec", "tok", "inst", "3.8.1", [], admin_token="adm")
        check("sync_members ผ่านทางเดียวกัน → ok + members (แผนสำรองทำงานอัตโนมัติ)",
              res.get("ok") is True and res.get("members") == [] and res.get("admin") is True and len(calls) == 2, str(res))
        calls.clear()
        res = hub.push("https://script.google.com/macros/s/X/exec", "tok", "", "inst", "3.8.1", presence_only=True)
        check("push (presence) ก็ได้แผนสำรองเดียวกัน — คืน ok ไม่โยน exception", res.get("ok") is True and len(calls) == 2, str(res))
    finally:
        hub.urllib.request.build_opener = real

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
