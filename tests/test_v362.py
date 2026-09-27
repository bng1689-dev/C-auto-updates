#!/usr/bin/env python3
"""v3.6.2 — เริ่มค้นเองหลังตรวจพบว่าเข้าสู่ระบบแล้ว: นับถอยหลัง 30 วินาที (เดิม 10) — ไม่เปิดเบราว์เซอร์

  • ค่าคงที่ AUTOSTART_SEC = 30 และข้อความแจ้ง/หน้าจอดึงตัวเลขจากค่านี้ (ไม่มีเลข 10 ฝังไว้)
  • _await_login นับถอยหลังครบ 30 วิจริงก่อนเริ่มเอง (จำลองนาฬิกา — ไม่ต้องรอจริง) และเริ่มทันทีเมื่อกดปุ่ม
"""
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v362_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "data")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
from _app import APP  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)

import engine  # noqa: E402
import worker  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


class FakePage:
    def wait_for_timeout(self, ms):
        pass

    def is_closed(self):
        return False


class FakeCtx:
    def close(self):
        pass


def run_await_login(press_start_at=None):
    """รัน _await_login กับหน้าเว็บจำลองที่ 'เข้าสู่ระบบแล้ว' ตั้งแต่แรก โดยเดินนาฬิกาเองทีละ 1 วิ
    คืน (จำนวนวินาทีจำลองที่ผ่านไป, บันทึกการทำงาน, ค่าสูงสุดของ autostart_in ที่เห็น)"""
    m = worker.RunManager()
    m._login_event.clear()
    page, ctx = FakePage(), FakeCtx()
    clock = {"t": 1000.0, "ticks": 0, "max_left": 0}
    real_time, real_find, real_login, real_live = worker.time.time, engine._find_id_input_selector, \
        engine.is_login_page, m._live_page

    def fake_time():
        clock["ticks"] += 1
        clock["t"] += 1.0
        clock["max_left"] = max(clock["max_left"], m.autostart_in)
        if press_start_at is not None and clock["ticks"] >= press_start_at:
            m._login_event.set()          # ผู้ใช้กด 'เริ่มค้นหา' ระหว่างนับถอยหลัง
        return clock["t"]

    worker.time.time = fake_time
    engine._find_id_input_selector = lambda p: "#id"
    engine.is_login_page = lambda p: False
    m._live_page = lambda c, p: p
    try:
        out = m._await_login(ctx, page)
    finally:
        worker.time.time = real_time
        engine._find_id_input_selector = real_find
        engine.is_login_page = real_login
        m._live_page = real_live
    return out is page, clock, list(m.log_lines)


def main():
    print("── ค่าคงที่และข้อความ ──")
    check("นับถอยหลังเริ่มเอง 30 วินาที", worker.RunManager.AUTOSTART_SEC == 30, str(worker.RunManager.AUTOSTART_SEC))
    src = (APP / "backend" / "worker.py").read_text(encoding="utf-8")
    check("ข้อความแจ้งดึงตัวเลขจากค่าคงที่ ไม่มี '10 วินาที' ฝังไว้",
          "{self.AUTOSTART_SEC} วินาที" in src and not re.search(r"\b10 วินาที", src))
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าจอแสดงตัวเลขจากสถานะ (autostart_in) ทั้งปุ่ม/ขั้นตอน/วงแหวน — ไม่มีเลขตายตัว",
          html.count("s.autostart_in") >= 4 and "10 วิ" not in html, str(html.count("s.autostart_in")))

    print("\n── นับถอยหลังจริง (นาฬิกาจำลอง) ──")
    ok, clock, log = run_await_login()
    check("ตรวจพบเข้าสู่ระบบ → บันทึกว่าจะเริ่มเองใน 30 วินาที",
          any("จะเริ่มค้นเองใน 30 วินาที" in ln for ln in log), str(log[-3:]))
    check("เริ่มเองหลังผ่านไป ≈30 วิ (ไม่ใช่ 10)", ok and 30 <= clock["ticks"] <= 40, f"ticks={clock['ticks']}")
    check("ตัวนับถอยหลังเริ่มที่ 30 ให้หน้าจอวาดวงแหวน", clock["max_left"] == 30, str(clock["max_left"]))
    check("ถึงเวลาแล้วบันทึก '▶ เริ่มค้นอัตโนมัติ'", any("▶ เริ่มค้นอัตโนมัติ" in ln for ln in log))

    ok, clock, log = run_await_login(press_start_at=5)
    check("กด 'เริ่มค้นหา' ระหว่างนับ → เริ่มทันที ไม่รอครบ 30", ok and clock["ticks"] < 15, f"ticks={clock['ticks']}")

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
