#!/usr/bin/env python3
"""v3.6.2/v3.10.0/v3.14.0 — เริ่มค้นเองหลังตรวจพบว่าเข้าสู่ระบบแล้ว — ไม่เปิดเบราว์เซอร์

  • v3.10.0: เป็นสวิตช์ (autostart_enabled) · ปิดอยู่ = ตรวจพบว่าเข้าสู่ระบบแล้วก็ไม่นับถอยหลัง รอกดปุ่มเท่านั้น
  • v3.14.0: เจ้าของสั่ง "แก้ไขสถานะเป็นเริ่มค้นอัตโนมัติใน .... วินาที (ผู้ใช้กำหนดเองได้ 3–30 วินาที และจำค่าไว้)"
    → ค่าเริ่มต้นเปิด นับ 10 วินาที · ตั้งได้ 3–30 (นอกช่วง = ตัดเข้าช่วง) · ข้อความ/หน้าจอดึงตัวเลขจากค่าที่ตั้ง ไม่มีเลขฝังไว้
  • _await_login นับครบตามที่ตั้งจริงก่อนเริ่มเอง (จำลองนาฬิกา) และเริ่มทันทีเมื่อกดปุ่ม
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

import auth  # noqa: E402
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
    print("── ค่าเริ่มต้นและข้อความ ──")
    check("v3.14.0: ค่าเริ่มต้นนับถอยหลัง 10 วินาที · ตั้งได้ 3–30",
          (auth.AUTOSTART_DEFAULT_SEC, auth.AUTOSTART_MIN_SEC, auth.AUTOSTART_MAX_SEC) == (10, 3, 30)
          and not hasattr(worker.RunManager, "AUTOSTART_SEC"))
    check("ตัดค่าเข้าช่วง 3–30: 1→3 · 99→30 · '12'→12 · 7.6→8 · ค่าเสีย→10",
          [auth.clamp_autostart_sec(v) for v in (1, 99, "12", 7.6, "x", None)] == [3, 30, 12, 8, 10, 10])
    src = (APP / "backend" / "worker.py").read_text(encoding="utf-8")
    check("ข้อความแจ้งดึงตัวเลขจากค่าที่ตั้ง ไม่มี 'NN วินาที' ฝังไว้",
          "{secs} วินาที" in src and "{self._autostart_sec()} วินาที" in src
          and not re.search(r"\b(10|30) วินาที", src))
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าจอแสดงตัวเลขจากสถานะ (autostart_in) ทั้งปุ่ม/ขั้นตอน/วงแหวน — ไม่มีเลขตายตัว",
          html.count("s.autostart_in") >= 4 and "10 วิ" not in html,
          str(html.count("s.autostart_in")))
    check("v3.14.0: config เริ่มต้น: autostart_enabled=True · 10 วินาที",
          auth.load_config().get("autostart_enabled") is True and auth.load_config().get("autostart_delay_sec") == 10,
          str(auth.load_config()))

    print("\n── สวิตช์ปิด → ไม่นับถอยหลัง ──")
    auth.update_config(autostart_enabled=False)
    ok, clock, log = run_await_login(press_start_at=8)
    check("ปิดอยู่: ตรวจพบเข้าสู่ระบบแล้วก็ไม่นับถอยหลัง (autostart_in คงเป็น 0) · บันทึกบอกว่าปิดอยู่",
          ok and clock["max_left"] == 0 and any("การเริ่มอัตโนมัติปิดอยู่" in ln for ln in log), str(log[-3:]))
    check("ปิดอยู่: กด 'เริ่มค้นหา' แล้วเริ่มได้ตามปกติ", ok and clock["ticks"] < 15, f"ticks={clock['ticks']}")
    check("หน้าตั้งค่ามีสวิตช์ (setAutoStart) และส่งค่าไปบันทึก",
          'id="setAutoStart"' in html and "autostart_enabled" in html)

    print("\n── เปิดสวิตช์ → นับถอยหลังจริงตามวินาทีที่ตั้ง (นาฬิกาจำลอง) ──")
    auth.update_config(autostart_enabled=True)
    for secs in (10, 25, 3):
        auth.update_config(autostart_delay_sec=secs)
        ok, clock, log = run_await_login()
        check(f"ตั้ง {secs} วิ: บันทึกว่าจะเริ่มเองใน {secs} วินาที",
              any(f"จะเริ่มค้นเองใน {secs} วินาที" in ln for ln in log), str(log[-3:]))
        check(f"ตั้ง {secs} วิ: เริ่มเองหลังผ่านไป ≈{secs} วิ", ok and secs <= clock["ticks"] <= secs + 10,
              f"ticks={clock['ticks']}")
        check(f"ตั้ง {secs} วิ: ตัวนับเริ่มที่ {secs} ให้หน้าจอวาดวงแหวน", clock["max_left"] == secs, str(clock["max_left"]))
    check("ถึงเวลาแล้วบันทึก '▶ เริ่มค้นอัตโนมัติ'", any("▶ เริ่มค้นอัตโนมัติ" in ln for ln in log))
    auth.update_config(autostart_delay_sec=99)          # ไฟล์ config ถูกแก้มือเกินช่วง → ใช้ 30
    ok, clock, log = run_await_login()
    check("ค่าใน config เกินช่วง (99) → นับ 30", clock["max_left"] == 30 and any("ใน 30 วินาที" in ln for ln in log),
          str(clock["max_left"]))

    auth.update_config(autostart_delay_sec=20)
    ok, clock, log = run_await_login(press_start_at=5)
    check("กด 'เริ่มค้นหา' ระหว่างนับ → เริ่มทันที ไม่รอครบ", ok and clock["ticks"] < 15, f"ticks={clock['ticks']}")

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
