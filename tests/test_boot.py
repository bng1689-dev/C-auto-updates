#!/usr/bin/env python3
"""v3.2.0 — ทดสอบลำดับการเปิดโปรแกรม (สาเหตุ 'จอขาวค้าง' บน Windows)

จำลอง 4 สถานการณ์จริงโดยไม่ต้องมี Windows/WebView2:
  1. เซิร์ฟเวอร์ปกติ                → เปิดหน้าต่างได้
  2. พอร์ตเปิดแต่แอปข้างในค้าง      → ต้องขึ้นข้อความบอกเหตุ ไม่ใช่เปิดจอขาว
  3. มีโปรเซสเก่าค้างยึดพอร์ตไว้     → ต้องขึ้นข้อความให้ปิดจาก Task Manager
  4. หน้าต่างไม่โหลดใน 30 วิ         → watchdog เด้งเบราว์เซอร์แทน + เขียน crash.log
"""
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_boot_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA)
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "uploads")

from _app import APP, CHROME  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "backend"))

# desktop.py import webview ตอนโหลดโมดูล — ใส่ตัวปลอมไว้ก่อน (เครื่องทดสอบไม่มี WebView2)
fake_webview = types.ModuleType("webview")
fake_webview.settings = {}
fake_webview.windows = []
fake_webview.create_window = lambda *a, **k: None
fake_webview.start = lambda *a, **k: None
sys.modules["webview"] = fake_webview

import desktop  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


class Recorder:
    """ดัก _fatal เพื่อดูว่าโปรแกรมแจ้งเหตุอะไรแทนที่จะปล่อยจอขาว"""
    def __init__(self):
        self.calls = []

    def __call__(self, stage, exc):
        self.calls.append((stage, str(exc)))
        raise SystemExit(1)


def _serve_real():
    """เซิร์ฟเวอร์จริงบนพอร์ตทดสอบ"""
    from waitress import serve
    from backend import server as srv
    serve(srv.app, host=desktop.HOST, port=desktop.PORT, threads=4)


def _dead_socket_server(stop):
    """พอร์ตเปิด แต่ไม่ตอบอะไรเลย = อาการ 'โปรเซสเก่าค้าง' ที่ทำให้จอขาว"""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((desktop.HOST, desktop.PORT))
    s.listen(8)
    conns = []
    s.settimeout(0.3)
    while not stop.is_set():
        try:
            conns.append(s.accept()[0])     # รับการเชื่อมต่อแล้วเงียบ ไม่ตอบ HTTP
        except OSError:
            pass
    for c in conns:
        c.close()
    s.close()


def main():
    desktop.PORT = 8799                     # พอร์ตแยกสำหรับทดสอบ
    desktop.CRASH_LOG = TEST_DATA / "crash.log"

    # ── 1) ยังไม่มีอะไรเปิดอยู่ ──
    check("พอร์ตว่าง → _port_open เป็นเท็จ", desktop._port_open(0.3) is False)
    check("ยังไม่มีเซิร์ฟเวอร์ → _http_ready เป็นเท็จ", desktop._http_ready(1) is False)

    # ── 2) พอร์ตเปิดแต่ไม่ตอบ HTTP (โปรเซสเก่าค้าง) ──
    stop = threading.Event()
    t = threading.Thread(target=_dead_socket_server, args=(stop,), daemon=True)
    t.start()
    time.sleep(0.5)
    check("โปรเซสค้าง: พอร์ตเปิดอยู่จริง", desktop._port_open(1) is True)
    check("โปรเซสค้าง: _http_ready ต้องเป็นเท็จ (เดิมเช็คแค่พอร์ตเลยหลุด)",
          desktop._http_ready(1) is False)

    rec = Recorder()
    orig_fatal = desktop._fatal
    desktop._fatal = rec
    try:
        desktop.main()
    except SystemExit:
        pass
    desktop._fatal = orig_fatal
    check("โปรเซสค้าง → แจ้งเหตุแทนการเปิดจอขาว", len(rec.calls) == 1, str(rec.calls))
    if rec.calls:
        stage, msg = rec.calls[0]
        check("ข้อความบอกว่าพอร์ตถูกยึดและไม่ตอบสนอง",
              "ไม่ตอบสนอง" in msg and str(desktop.PORT) in msg, msg[:120])
        check("ข้อความบอกวิธีแก้ (Task Manager + ชื่อโปรเซส)",
              "Task Manager" in msg and "pythonw.exe" in msg and "msedgewebview2.exe" in msg,
              msg[:160])
    stop.set()
    t.join(timeout=3)
    time.sleep(0.4)

    # ── 3) เซิร์ฟเวอร์จริงทำงาน ──
    threading.Thread(target=_serve_real, daemon=True).start()
    check("เซิร์ฟเวอร์จริงพร้อมใช้งาน (_wait_ready ผ่าน)", desktop._wait_ready(20) is True)
    check("_http_ready ตอบจริงแล้ว", desktop._http_ready(2) is True)

    opened = []
    fake_webview.create_window = lambda *a, **k: types.SimpleNamespace(
        events=types.SimpleNamespace(shown=_Ev(), loaded=_Ev()))
    fake_webview.start = lambda *a, **k: opened.append(True)
    rec2 = Recorder()
    desktop._fatal = rec2
    try:
        desktop.main()
    except SystemExit:
        pass
    desktop._fatal = orig_fatal
    check("เซิร์ฟเวอร์ปกติ → เปิดหน้าต่างได้ ไม่มีการแจ้งเหตุ",
          opened == [True] and not rec2.calls, str(rec2.calls))

    # ── 4) watchdog: หน้าต่างไม่โหลด ──
    desktop.WATCHDOG_SEC = 1
    browsed = []
    win = types.SimpleNamespace(events=types.SimpleNamespace(shown=_Ev(), loaded=_Ev()))
    import webbrowser
    orig_open = webbrowser.open
    webbrowser.open = lambda u: browsed.append(u)
    desktop._start_load_watchdog(win, "http://127.0.0.1:8799")
    time.sleep(1.8)
    check("หน้าไม่โหลดใน 30 วิ → เปิดเบราว์เซอร์แทน", browsed == ["http://127.0.0.1:8799"],
          str(browsed))
    log = (TEST_DATA / "crash.log").read_text(encoding="utf-8") if (TEST_DATA / "crash.log").exists() else ""
    check("บันทึกเหตุลง crash.log", "หน้าต่างแอปไม่โหลด" in log, log[-160:])

    # โหลดสำเร็จ → ต้องไม่เด้งอะไร
    browsed.clear()
    win2 = types.SimpleNamespace(events=types.SimpleNamespace(shown=_Ev(), loaded=_Ev()))
    desktop._start_load_watchdog(win2, "http://127.0.0.1:8799")
    win2.events.loaded.fire()
    time.sleep(1.8)
    check("หน้าโหลดสำเร็จ → watchdog เงียบ", browsed == [], str(browsed))
    webbrowser.open = orig_open

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


class _Ev:
    """เลียนแบบ event ของ pywebview: ใช้ += ผูก callback ได้"""
    def __init__(self):
        self.cbs = []

    def __iadd__(self, cb):
        self.cbs.append(cb)
        return self

    def fire(self):
        for cb in self.cbs:
            cb()


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
