#!/usr/bin/env python3
"""v3.14.0 — หน้าจอจัดกริดอัตโนมัติ · เมนูซ้าย 3 แบบ · สัญลักษณ์สิทธิ์ · เริ่มค้นอัตโนมัติใน N วินาที
· ย่อโปรแกรม/ซ่อน Chrome ระหว่างค้น + กระดิ่งเมื่อเสร็จ · แก้วันที่ "ct 03 2026" · แก้ไข/ลบบันทึกโหมดทีละขั้น

เจ้าของสั่ง:
  "จัดเรียงกริดในส่วนหน้าโปรแกรมแต่ละหน้าแบบอัตโนมัติสวยงาม และแก้ไขสถานะเป็นเริ่มค้นอัตโนมัติ ใน .... วินาที
   (ผู้ใช้กำหนดเองได้ 3-30 วินาที และจำค่าที่กดเปลี่ยนไว้จนกว่าจะเปลี่ยนอีกครั้ง) เมื่อเริ่มค้น โปรแกรมจะย่อตัวซ่อนลง
   ก็ยังทำงานต่อเป็นปกติจนครบ ให้มีเสียงกระดิ่งเตือน (กดเปิด/ปิดได้ แต่ค่าเริ่มต้นคือเปิด) ฝั่งแถบเมนูซ้ายมือ
   สามารถ ซ่อนได้/แสดงได้/ตั้งออโต้เมื่อเอาเม้าไปชี้ได้ และในส่วนของสมาชิก ... ใช้เป็นสัญลักษณ์แสดงสถานะที่ได้รับสิทธิ์"
  "(บันทึกการทำงานโหมดทีละขั้น) สามารถแก้ไข/ลบทิ้งได้" — แก้ไขลบข้อมูล · แก้ชื่อบัญชีที่แสดง · ลบบางสเต็ปในชุด

ส่วนที่ไม่ต้องใช้เบราว์เซอร์ทดสอบผ่าน Flask test client · ส่วนหน้าจอทดสอบบน Chromium จริง (พอร์ต 8806)
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import wave
import zipfile
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v3140_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "data")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
os.environ["TZ"] = "Asia/Bangkok"
try:
    time.tzset()
except AttributeError:
    pass
from _app import APP, CHROME  # noqa: E402

from backend import server  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import engine  # noqa: E402
import worker  # noqa: E402

PORT = 8806
PASS = FAIL = 0
JS_ERRORS = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


# ---------------- ตัวจำลอง Chrome (CDP) ----------------
class FakeCDP:
    def __init__(self, win):
        self.win = win

    def send(self, method, params=None):
        self.win.calls.append((method, params))
        if method == "Browser.getWindowForTarget":
            return {"windowId": 7, "bounds": dict(self.win.bounds)}
        if method == "Browser.setWindowBounds":
            self.win.bounds.update(params["bounds"])
            return {}
        raise RuntimeError(method)

    def detach(self):
        pass


class FakeWin:
    def __init__(self):
        self.bounds = {"left": 10, "top": 20, "width": 1200, "height": 800, "windowState": "maximized"}
        self.calls = []


class FakeCtx:
    def __init__(self, win):
        self.win = win

    def new_cdp_session(self, page):
        return FakeCDP(self.win)


class FakePage:
    def __init__(self):
        self.win = FakeWin()
        self.context = FakeCtx(self.win)
        self.url = "https://crimes.example/bdasearch/#/bda/search/criteria/person"

    def screenshot(self, path):
        # PNG 1x1 ที่ถูกต้อง (ให้ <img> ในหน้าจอวาดได้จริง)
        Path(path).write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5d1b1"
            "c80000000049454e44ae426082"))

    def content(self):
        return "<html><body><script>window.__x=1</script>CRIMES</body></html>"


def make_recording(account, steps, finish=True):
    rec = engine.ManualRecorder(account=account)
    page = FakePage()
    for i in range(steps):
        rec.set_context(f"แถว {i + 2}")
        rec.step(page, f"สเต็ปที่ {i + 1}")
        rec.note(f"ผลสเต็ป {i + 1}")
    if finish:
        rec.finish(None)
    else:
        rec._flush()
    return rec


def login(c, u, p):
    r = c.post("/api/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.get_json()


def main():
    server.app.config["TESTING"] = True
    server._hub_kick = lambda *a, **k: None

    print("── ค่าตั้ง: เริ่มค้นอัตโนมัติใน N วินาที (ค่าเริ่มต้นเปิด 10 วิ) · ย่อโปรแกรม · กระดิ่ง ──")
    cfg = auth.load_config()
    check("เครื่องใหม่: เริ่มอัตโนมัติเปิด · 10 วินาที · ย่อโปรแกรมเมื่อเริ่มค้นเปิด · กระดิ่งเปิด",
          cfg.get("autostart_enabled") is True and cfg.get("autostart_delay_sec") == 10
          and cfg.get("hide_on_start") is True and cfg.get("done_bell") is True, str(cfg)[:300])
    # เครื่องรุ่นก่อน: config เก็บ autostart_enabled=False (ค่าเริ่มต้นเดิม) และไม่มีธงย้ายค่า
    old = dict(cfg)
    for k in ("autostart_v314", "autostart_delay_sec", "hide_on_start", "done_bell"):
        old.pop(k, None)
    old["autostart_enabled"] = False
    Path(server.config.CONFIG_PATH).write_text(json.dumps(old), encoding="utf-8")
    cfg = auth.load_config()
    disk = json.loads(Path(server.config.CONFIG_PATH).read_text(encoding="utf-8"))
    check("อัปเดตจากรุ่นก่อน (เคยปิดไว้ตามค่าเริ่มต้นเดิม) → เปิดให้ครั้งเดียว 10 วิ + บันทึกธงย้ายค่าลงไฟล์",
          cfg.get("autostart_enabled") is True and disk.get("autostart_v314") is True
          and disk.get("autostart_enabled") is True and disk.get("autostart_delay_sec") == 10, str(disk)[:200])
    auth.update_config(autostart_enabled=False)
    check("ผู้ใช้ปิดเองหลังย้ายค่า → เปิดโปรแกรมใหม่ยังปิดอยู่ (ไม่ย้ายค่าซ้ำ)",
          auth.load_config().get("autostart_enabled") is False)
    auth.update_config(autostart_enabled=True)

    c = server.app.test_client()
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน"})
    check("(เตรียม) สร้าง Super Admin", r.status_code == 200, str(r.get_json()))
    s = c.get("/api/settings").get_json()
    check("GET /api/settings: ส่ง autostart_delay_sec + ช่วง 3–30 + hide_on_start + done_bell",
          (s.get("autostart_delay_sec"), s.get("autostart_min"), s.get("autostart_max"),
           s.get("hide_on_start"), s.get("done_bell")) == (10, 3, 30, True, True), str(s)[:300])
    vals = []
    for v in (2, 45, "17", 12.4, "abc", None):
        c.post("/api/settings", json={"autostart_delay_sec": v})
        vals.append(c.get("/api/settings").get_json().get("autostart_delay_sec"))
    check("ตั้งวินาที: 2→3 · 45→30 · '17'→17 · 12.4→12 · ค่าเสีย→10 (ค่าเริ่มต้น)", vals == [3, 30, 17, 12, 10, 10], str(vals))
    c.post("/api/settings", json={"autostart_delay_sec": 14, "hide_on_start": False, "done_bell": False})
    s = c.get("/api/settings").get_json()
    check("ตั้ง 14 วิ · ปิดย่อโปรแกรม · ปิดกระดิ่ง → จำค่าไว้ใน config.json",
          (s.get("autostart_delay_sec"), s.get("hide_on_start"), s.get("done_bell")) == (14, False, False)
          and json.loads(Path(server.config.CONFIG_PATH).read_text(encoding="utf-8")).get("autostart_delay_sec") == 14)
    check("worker อ่านวินาทีจากค่าที่ตั้ง (ไม่มีค่าคงที่ฝังไว้)", worker.RunManager._autostart_sec() == 14)
    uid = db.create_user("somchai", "pass66", "สมชาย", "member")
    mc = server.app.test_client()
    login(mc, "somchai", "pass66")
    r = mc.post("/api/settings", json={"autostart_delay_sec": 8, "hide_on_start": True, "done_bell": True,
                                       "autostart_enabled": True})
    s = c.get("/api/settings").get_json()
    check("สมาชิกทั่วไปปรับค่าประจำเครื่องนี้ได้ (เหมือนความเร็วการค้น)",
          r.status_code == 200 and (s.get("autostart_delay_sec"), s.get("hide_on_start"), s.get("done_bell")) == (8, True, True),
          str(r.get_json()))

    print("\n── ย่อโปรแกรม/ซ่อน Chrome เมื่อเริ่มค้น · คืนหน้าต่างเมื่อจบ/ต้องให้ผู้ใช้ทำอะไร · กระดิ่ง ──")
    rings = []
    real_ring = worker.ring_bell
    worker.ring_bell = lambda: rings.append(1) or True
    m = worker.RunManager()
    ev = []
    m.ui_hook = ev.append
    page = FakePage()
    m._page = page
    m.state = "running"
    m._hide_for_run(page)
    b = page.win.bounds
    check("เริ่มค้น → Chrome เลื่อนออกนอกจอ (ไม่ย่อ — Chrome ที่ถูกย่อหยุดวาดหน้า) + ย่อโปรแกรม · hidden=True",
          m.hidden and b["left"] == worker.CHROME_HIDE_X and b["top"] == worker.CHROME_HIDE_Y
          and b["windowState"] == "normal" and ev == ["minimize"] and m.status()["hidden"] is True, f"{b} {ev}")
    check("ไม่มีคำสั่ง 'minimized' กับ Chrome เลย",
          not any(p and p.get("bounds", {}).get("windowState") == "minimized" for _, p in page.win.calls))
    check("บันทึกการทำงานบอกวิธีดู Chrome (ปุ่ม 👁)", any("👁" in ln for ln in m.log_lines), str(list(m.log_lines)[-2:]))
    m._hide_for_run(page)
    check("สั่งซ่อนซ้ำ → ไม่ทำซ้ำ", ev == ["minimize"])
    m._unhide(page, "done")
    b = page.win.bounds
    check("จบรอบ → Chrome กลับตำแหน่ง/ขนาดเดิม และกลับเป็นเต็มจอเหมือนเดิม · โปรแกรมเด้งกลับ (done)",
          not m.hidden and (b["left"], b["top"], b["width"], b["height"]) == (10, 20, 1200, 800)
          and b["windowState"] == "maximized" and ev == ["minimize", "done"], f"{b} {ev}")
    m._unhide(page, "done")
    check("ไม่ได้ซ่อนอยู่ก็ยังเรียกความสนใจได้ (done/attention) แต่ไม่แตะ Chrome",
          ev[-1] == "done" and len(ev) == 3)
    calls_before = len(page.win.calls)
    m._unhide(page, "restore")
    check("ไม่ได้ซ่อนอยู่ + restore → ไม่ทำอะไร", len(ev) == 3 and len(page.win.calls) == calls_before)

    auth.update_config(hide_on_start=False)
    m2 = worker.RunManager()
    ev2 = []
    m2.ui_hook = ev2.append
    p2 = FakePage()
    m2._hide_for_run(p2)
    check("ปิดสวิตช์ 'ย่อโปรแกรมเมื่อเริ่มค้น' → ไม่ซ่อน ไม่ย่อ", not m2.hidden and not ev2 and not p2.win.calls)
    m2.state = "running"
    m2._page = p2
    m2.request_window(False)
    m2._service_window()
    check("แต่ปุ่ม 🫥 บนแถบสถานะยังสั่งซ่อนได้ (force)", m2.hidden and ev2 == ["minimize"])
    m2.request_window(True)
    m2._service_window()
    check("ปุ่ม 👁 แสดง Chrome → คืนหน้าต่าง (restore) · คำขอถูกใช้ครั้งเดียว",
          not m2.hidden and ev2 == ["minimize", "restore"] and m2._win_request is None)
    m2.state = "paused"
    m2.request_window(False)
    m2._service_window()
    check("พักอยู่ → ไม่ซ่อน (ซ่อนได้เฉพาะตอนกำลังค้น)", not m2.hidden)
    auth.update_config(hide_on_start=True)
    m3 = worker.RunManager()
    m3.step_mode = True
    ev3 = []
    m3.ui_hook = ev3.append
    m3._hide_for_run(FakePage())
    check("โหมดทีละขั้น → ไม่ซ่อน (ต้องเห็นทุกสเต็ป)", not m3.hidden and not ev3)
    m4 = worker.RunManager()
    m4._chrome_window(None, True)
    check("Chrome ปิดไปแล้ว (page=None) → ไม่ล้ม", m4._chrome_window(None, False) is False)

    # พักเพราะต้องให้ผู้ใช้ทำอะไร (หลุดล็อกอิน) ระหว่างซ่อน → คืนหน้าต่าง + กระดิ่ง → ค้นต่อ → กลับไปซ่อน
    m5 = worker.RunManager()
    ev5 = []
    m5.ui_hook = ev5.append
    p5 = FakePage()
    m5._page = p5
    m5.state = "running"
    m5._hide_for_run(p5)
    auth.update_config(done_bell=True)
    rings.clear()
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("r", m5._pause_wait("auth")), daemon=True)
    th.start()
    for _ in range(50):
        if m5.state == "paused":
            break
        time.sleep(0.05)
    time.sleep(0.2)
    shown = not m5.hidden and p5.win.bounds["left"] == 10
    m5._resume_event.set()
    th.join(5)
    check("หลุดล็อกอินระหว่างซ่อน → Chrome+โปรแกรมเด้งกลับ (attention) + กระดิ่ง",
          shown and ev5[:2] == ["minimize", "attention"] and rings == [1], f"{ev5} rings={rings}")
    check("ค้นต่อ ▶ → กลับไปซ่อนเหมือนเดิม", out.get("r") is True and m5.hidden and ev5 == ["minimize", "attention", "minimize"],
          f"{ev5}")
    m6 = worker.RunManager()
    ev6 = []
    m6.ui_hook = ev6.append
    m6._page = FakePage()
    m6.state = "running"
    m6._hide_for_run(m6._page)
    rings.clear()
    th = threading.Thread(target=lambda: m6._pause_wait("manual"), daemon=True)
    th.start()
    time.sleep(0.4)
    m6._resume_event.set()
    th.join(5)
    check("กดพักเอง (manual) → ไม่เด้งหน้าต่าง ไม่มีกระดิ่ง", ev6 == ["minimize"] and not rings and m6.hidden, f"{ev6} {rings}")
    auth.update_config(done_bell=False)
    m7 = worker.RunManager()
    m7._page = FakePage()
    th = threading.Thread(target=lambda: m7._pause_wait("network"), daemon=True)
    engine_probe = engine.probe_online
    engine.probe_online = lambda timeout=4: True
    th.start()
    time.sleep(0.4)
    m7._resume_event.set()
    th.join(5)
    engine.probe_online = engine_probe
    check("ปิดกระดิ่ง → พักเพราะเน็ตหลุดก็ไม่มีเสียง", not rings)
    auth.update_config(done_bell=True)
    worker.ring_bell = real_ring
    wsrc = (APP / "backend" / "worker.py").read_text(encoding="utf-8")
    check("จบรอบสมบูรณ์ → คืนหน้าต่าง 'done' + กระดิ่งตามสวิตช์ · หยุด/ปิด Chrome → คืนหน้าต่างเฉย ๆ (ไม่มีกระดิ่ง)",
          '"done" if finished else "restore"' in wsrc and 'if finished and bool(_cfg_get("done_bell", True))' in wsrc,
          "")
    wav = worker._bell_wav()
    with wave.open(io.BytesIO(wav)) as w:
        info = (w.getnchannels(), w.getsampwidth(), w.getframerate(), round(w.getnframes() / w.getframerate(), 1))
    check("เสียงกระดิ่งสังเคราะห์ในหน่วยความจำเป็น WAV ที่ถูกต้อง (ไม่ต้องมีไฟล์เสียงในแพ็กเกจ)",
          wav[:4] == b"RIFF" and info == (1, 2, 22050, 1.4), str(info))
    check("ring_bell บนเครื่องที่ไม่มี winsound → เงียบ ไม่โยน exception", worker.ring_bell() is True)

    print("\n── หน้าต่างโปรแกรม (desktop.py) — ย่อ/คืน/กะพริบ ──")
    sys.path.insert(0, str(APP))
    import types
    if "webview" not in sys.modules:           # desktop.py import webview ตอนโหลด — เครื่องทดสอบไม่มี WebView2 (เหมือน test_boot)
        fake = types.ModuleType("webview")
        fake.settings, fake.windows = {}, []
        fake.create_window = fake.start = lambda *a, **k: None
        sys.modules["webview"] = fake
    import desktop
    desktop.CRASH_LOG = TEST_DATA / "crash.log"

    class Native:
        def __init__(self):
            self.WindowState = "Maximized"

    class Win:
        def __init__(self):
            self.native = Native()
            self.calls = []
            self._top = False

        def minimize(self):
            self.calls.append("minimize")
            self.native.WindowState = "Minimized"

        def restore(self):
            self.calls.append("restore")
            self.native.WindowState = "Normal"

        def maximize(self):
            self.calls.append("maximize")
            self.native.WindowState = "Maximized"

        @property
        def on_top(self):
            return self._top

        @on_top.setter
        def on_top(self, v):
            self.calls.append(f"on_top={v}")
            self._top = v

    w = Win()
    hook = desktop._make_ui_hook(w)
    hook("minimize")
    hook("done")
    check("ย่อจากเต็มจอ → ค้นเสร็จ: คืนเป็นเต็มจอเหมือนเดิม + ดันขึ้นหน้าสุด (ไม่หดเป็นหน้าต่างเล็ก)",
          w.calls == ["minimize", "maximize", "on_top=True", "on_top=False"], str(w.calls))
    w2 = Win()
    hook2 = desktop._make_ui_hook(w2)
    hook2("done")
    check("ไม่ได้ย่ออยู่ (เต็มจอ) → ไม่เรียก restore (WinForms จะหดหน้าต่าง) แค่ดันขึ้นหน้าสุด",
          "restore" not in w2.calls and "maximize" not in w2.calls and "on_top=True" in w2.calls, str(w2.calls))
    w3 = Win()
    w3.native.WindowState = "Normal"
    hook3 = desktop._make_ui_hook(w3)
    hook3("minimize")
    hook3("restore")
    check("ย่อจากหน้าต่างปกติ → ผู้ใช้กด 👁 → restore (ไม่ดันขึ้นหน้าสุดสำหรับ restore)",
          w3.calls == ["minimize", "restore"], str(w3.calls))
    desktop._flash_taskbar(w3)
    check("กะพริบ taskbar บนเครื่องที่ไม่ใช่ Windows → ไม่ล้ม", True)
    dsrc = (APP / "desktop.py").read_text(encoding="utf-8")
    check("desktop.py ผูก hook กับงานค้น (server.manager.ui_hook)", "server.manager.ui_hook = _make_ui_hook(" in dsrc)

    print("\n── /api/run/window (ปุ่ม 👁 บนแถบสถานะ) ──")
    anon = server.app.test_client()
    check("ไม่ได้ล็อกอิน → 401", anon.post("/api/run/window", json={"show": True}).status_code == 401)
    server.manager._win_request = None
    r = c.post("/api/run/window", json={"show": False})
    check("Super Admin สั่งซ่อน → ส่งคำขอให้ worker (ทำในเธรดงานค้น เพราะ Playwright ผูกเธรด)",
          r.status_code == 200 and server.manager._win_request == "hide", str(r.get_json()))
    server.manager.state, server.manager.current_user_id = "running", 999
    r = mc.post("/api/run/window", json={"show": True})
    check("สมาชิกที่ไม่ใช่เจ้าของรอบ → 403", r.status_code == 403 and server.manager._win_request == "hide")
    server.manager.current_user_id = uid
    r = mc.post("/api/run/window", json={"show": True})
    check("เจ้าของรอบ → สั่งแสดงได้", r.status_code == 200 and server.manager._win_request == "show")
    st = c.get("/api/status").get_json()
    check("สถานะรอบมี hidden + autostart_total (หน้าจอใช้วาดปุ่ม/วงแหวน)", "hidden" in st and "autostart_total" in st,
          str(sorted(st))[:200])
    server.manager.state, server.manager.current_user_id, server.manager._win_request = "idle", 0, None

    print("\n── แก้วันที่ 'ใช้งานล่าสุด' ในตารางสมาชิกทุกเครื่อง (\"ct 03 2026\") ──")
    T = server._hub_time_local
    cases = {
        "Sat Oct 03 2026 01:37:48 GMT+0700 (Indochina Time)": "2026-10-03T01:37:48",
        "Fri Oct 02 2026 18:37:48 GMT+0000 (Coordinated Universal Time)": "2026-10-03T01:37:48",
        "2026-10-02T18:37:48.000Z": "2026-10-03T01:37:48",
        "2026-10-03T01:37:48": "2026-10-03T01:37:48",
        "2026-10-03T01:37:48+07:00": "2026-10-03T01:37:48",
        "": "",
        "เมื่อวาน": "เมื่อวาน",
    }
    got = {k: T(k) for k in cases}
    check("ข้อความวันที่แบบ JS / ISO UTC / ISO ไม่มีเขตเวลา → ISO เวลาเครื่องนี้ · อ่านไม่ออก = คงเดิม",
          got == cases, json.dumps({k: v for k, v in got.items() if cases[k] != v}, ensure_ascii=False))
    check("received_at คงเขตเวลาไว้ (หน้าจอใช้คำนวณออนไลน์/ออฟไลน์)",
          T("Sat Oct 03 2026 01:37:48 GMT+0700 (Indochina Time)", keep_utc=True) == "2026-10-03T01:37:48+07:00"
          and T("2026-10-02T18:37:48.000Z", keep_utc=True) == "2026-10-02T18:37:48+00:00")
    auth.update_config(hub_url="https://script.google.com/macros/s/T3140/exec", hub_token="tok-3140", hub_enabled=True)
    real_board = server.hub.fetch_board
    server.hub.fetch_board = lambda url, tok, ym, **k: {"ok": True, "presence": [
        {"install_id": "abc12345", "uid": "3", "display_name": "JOJO", "app_version": "3.13.1",
         "last_seen": "Sat Oct 03 2026 01:37:48 GMT+0700 (Indochina Time)",
         "received_at": "Sat Oct 03 2026 01:38:02 GMT+0700 (Indochina Time)"}]}
    d = c.get("/api/hub/presence").get_json()
    server.hub.fetch_board = real_board
    auth.update_config(hub_enabled=False, hub_token="")
    row = (d.get("presence") or [{}])[0]
    check("/api/hub/presence: แถวที่ชีตแปลงเป็นวันที่แบบ JS → ISO ก่อนถึงหน้าจอ",
          row.get("last_seen") == "2026-10-03T01:37:48" and row.get("received_at") == "2026-10-03T01:38:02+07:00"
          and row.get("display_name") == "JOJO", str(row))
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    check("หน้าจอไม่ตัดสตริงเวลาตรง ๆ แล้ว (ใช้ fmtHubTime)",
          "fmtHubTime(r.last_seen)" in html and "fmtHubTime(r.received_at)" in html
          and '(r.last_seen||"").replace("T"," ").slice(5,16)' not in html)

    print("\n── บันทึกโหมดทีละขั้น: แก้ไข/ลบ (Super Admin · ลบต้องยืนยันรหัสผ่าน · ชุดที่กำลังบันทึกห้ามแตะ) ──")
    a = make_recording("acctA", 3)
    time.sleep(1.05)
    b = make_recording("acctB", 2)
    time.sleep(1.05)
    act = make_recording("acctLive", 1, finish=False)
    server.manager._recorder = act
    lst = c.get("/api/admin/recordings").get_json()
    names = [r["name"] for r in lst["recordings"]]
    check("รายการ 3 ชุด · ชุดที่กำลังบันทึกติดธง active",
          set(names) == {a.name, b.name, act.name} and lst.get("active") == act.name
          and [r["active"] for r in lst["recordings"] if r["name"] == act.name] == [True]
          and not any(r["active"] for r in lst["recordings"] if r["name"] != act.name), str(lst)[:300])
    denied = [mc.get("/api/admin/recordings").status_code,
              mc.get(f"/api/admin/recordings/{a.name}/steps").status_code,
              mc.get(f"/api/admin/recordings/{a.name}/file/step001.png").status_code,
              mc.post(f"/api/admin/recordings/{a.name}/rename", json={"account": "x"}).status_code,
              mc.delete(f"/api/admin/recordings/{a.name}", json={"code": "pass66"}).status_code,
              mc.post("/api/admin/recordings/delete-all", json={"code": "pass66"}).status_code,
              mc.post(f"/api/admin/recordings/{a.name}/steps/delete", json={"code": "pass66", "steps": [1]}).status_code]
    check("สมาชิกทั่วไปทำอะไรกับบันทึกไม่ได้เลย (403 ทุกทาง)", denied == [403] * 7, str(denied))

    st = c.get(f"/api/admin/recordings/{a.name}/steps").get_json()
    steps = st.get("steps") or []
    check("ดูสเต็ป: 3 สเต็ป ครบคำอธิบาย/บริบท/URL/ผล/ไฟล์ภาพ+HTML",
          [x["i"] for x in steps] == [1, 2, 3] and steps[0]["desc"] == "สเต็ปที่ 1" and steps[0]["context"] == "แถว 2"
          and steps[0]["notes"] == ["ผลสเต็ป 1"] and steps[0]["shot"] == "step001.png" and steps[0]["html"] == "step001.html"
          and st.get("active") is False, str(st)[:300])
    r = c.get(f"/api/admin/recordings/{a.name}/file/step002.png")
    check("ภาพหน้าจอของสเต็ป → image/png (nosniff)", r.status_code == 200 and r.mimetype == "image/png"
          and r.headers.get("X-Content-Type-Options") == "nosniff" and r.data[:4] == b"\x89PNG")
    r = c.get(f"/api/admin/recordings/{a.name}/file/step002.html")
    check("HTML ของสเต็ป → ไฟล์ดาวน์โหลดเท่านั้น (ไม่เรนเดอร์หน้าเว็บ CRIMES ใน origin ของโปรแกรม)",
          r.status_code == 200 and r.mimetype == "application/octet-stream"
          and "attachment" in r.headers.get("Content-Disposition", ""), f"{r.mimetype} {r.headers.get('Content-Disposition')}")
    bad = [c.get(f"/api/admin/recordings/{a.name}/file/{f}").status_code
           for f in ("steps.jsonl", "summary.json", "..%2Fsummary.json", "step1.png", "step001.exe", "step999.png")]
    bad += [c.get("/api/admin/recordings/manual_x/steps").status_code,
            c.get("/api/admin/recordings/..%2F..%2Fdata/steps").status_code,
            c.post("/api/admin/recordings/manual_20990101-000000/rename", json={"account": "x"}).status_code]
    check("ชื่อไฟล์/ชุดนอกรูปแบบ (traversal · ไฟล์อื่นในโฟลเดอร์ · ไม่มีอยู่) → 404 ทั้งหมด", bad == [404] * 9, str(bad))

    r = c.post(f"/api/admin/recordings/{a.name}/rename", json={"account": "  บัญชี   ใหม่ A  "})
    summ = json.loads((a.dir / "summary.json").read_text(encoding="utf-8"))
    check("แก้ชื่อบัญชีที่แสดง → summary.json เปลี่ยน (ตัดช่องว่างซ้ำ) · รายการแสดงชื่อใหม่",
          r.status_code == 200 and summ["account"] == "บัญชี ใหม่ A" and summ["steps"] == 3
          and any(x["account"] == "บัญชี ใหม่ A" for x in c.get("/api/admin/recordings").get_json()["recordings"]),
          str(r.get_json()))
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/admin/recordings/{a.name}/download").data))
    check("ไฟล์ .zip ที่ดาวน์โหลดมีชื่อบัญชีใหม่", json.loads(z.read(f"{a.name}/summary.json"))["account"] == "บัญชี ใหม่ A")
    r = c.post(f"/api/admin/recordings/{a.name}/rename", json={"account": "ก" * 200})
    check("ชื่อยาวเกิน → ตัดที่ 80 ตัว", r.status_code == 200 and r.get_json()["account"] == "ก" * 80)
    check("ไม่ส่งชื่อมา → 400", c.post(f"/api/admin/recordings/{a.name}/rename", json={}).status_code == 400)
    r = c.post(f"/api/admin/recordings/{act.name}/rename", json={"account": "x"})
    check("ชุดที่กำลังบันทึก → แก้ชื่อไม่ได้ (409)", r.status_code == 409)
    # ชุดค้างจากโปรแกรมปิดกลางคัน (ไม่มี summary.json)
    crashed = make_recording("acctCrash", 2, finish=False)
    r = c.post(f"/api/admin/recordings/{crashed.name}/rename", json={"account": "กู้คืน"})
    cs = json.loads((crashed.dir / "summary.json").read_text(encoding="utf-8"))
    check("ชุดค้าง (โปรแกรมปิดกลางคัน ไม่มี summary.json) → แก้ชื่อได้ สร้าง summary ให้พร้อมจำนวนสเต็ป",
          r.status_code == 200 and cs == {"name": crashed.name, "steps": 2, "account": "กู้คืน"}, str(cs))

    url = f"/api/admin/recordings/{a.name}/steps/delete"
    r1 = c.post(url, json={"steps": [2]})
    r2 = c.post(url, json={"steps": [2], "code": "wrong"})
    r3 = c.post(url, json={"code": "secret9"})
    check("ลบบางสเต็ป: ไม่ใส่รหัส → 400 · รหัสผิด → 403 · ไม่เลือกสเต็ป → 400 (ยังไม่ลบอะไร)",
          (r1.status_code, r2.status_code, r3.status_code) == (400, 403, 400)
          and (a.dir / "step002.png").exists(), f"{r1.status_code} {r2.status_code} {r3.status_code}")
    r = c.post(url, json={"steps": [2, "x", 99], "code": "secret9"})
    left = c.get(f"/api/admin/recordings/{a.name}/steps").get_json()["steps"]
    summ = json.loads((a.dir / "summary.json").read_text(encoding="utf-8"))
    check("ลบสเต็ป 2 → ภาพ/HTML ของสเต็ป 2 หาย · steps.jsonl เหลือ 1,3 (เลขเดิม) · summary 2 สเต็ป",
          r.status_code == 200 and r.get_json() == {"ok": True, "removed": 1, "left": 2}
          and [x["i"] for x in left] == [1, 3] and not (a.dir / "step002.png").exists()
          and not (a.dir / "step002.html").exists() and (a.dir / "step003.png").exists() and summ["steps"] == 2
          and summ["account"] == "ก" * 80, str(r.get_json()))
    check("รายการชุดแสดงจำนวนสเต็ปใหม่",
          [x["steps"] for x in c.get("/api/admin/recordings").get_json()["recordings"] if x["name"] == a.name] == [2])
    r = c.post(f"/api/admin/recordings/{act.name}/steps/delete", json={"steps": [1], "code": "secret9"})
    check("ชุดที่กำลังบันทึก → ลบสเต็ปไม่ได้ (409)", r.status_code == 409 and (act.dir / "step001.png").exists())

    r1 = c.delete(f"/api/admin/recordings/{b.name}", json={})
    r2 = c.delete(f"/api/admin/recordings/{b.name}", json={"code": "nope"})
    check("ลบทั้งชุด: ไม่ใส่รหัส → 400 · รหัสผิด → 403 · ยังอยู่", (r1.status_code, r2.status_code) == (400, 403)
          and b.dir.exists())
    r = c.delete(f"/api/admin/recordings/{b.name}", json={"code": "secret9"})
    check("รหัสถูก → ลบทั้งโฟลเดอร์", r.status_code == 200 and not b.dir.exists())
    r = c.delete(f"/api/admin/recordings/{act.name}", json={"code": "secret9"})
    check("ชุดที่กำลังบันทึก → ลบไม่ได้ (409)", r.status_code == 409 and act.dir.exists())
    r = c.delete(f"/api/admin/recordings/{b.name}", json={"code": "secret9"})
    check("ลบชุดที่ไม่มีแล้ว → 404", r.status_code == 404)
    r0 = c.post("/api/admin/recordings/delete-all", json={})
    r = c.post("/api/admin/recordings/delete-all", json={"code": "secret9"})
    rest = [x["name"] for x in c.get("/api/admin/recordings").get_json()["recordings"]]
    check("ลบทั้งหมด: ไม่ใส่รหัส → 400 · รหัสถูก → ลบทุกชุดยกเว้นชุดที่กำลังบันทึก",
          r0.status_code == 400 and r.get_json() == {"ok": True, "deleted": 2, "skipped": 1, "failed": 0}
          and rest == [act.name], f"{r.get_json()} {rest}")
    server.manager._recorder = None
    engine.delete_recording(act.name)        # รอบจบแล้ว — เก็บกวาดก่อนทดสอบหน้าจอ
    acts = [e["action"] for e in db.get_audit_log(limit=50)]
    check("ทุกการแก้/ลบลงบันทึกตรวจสอบ",
          all(x in acts for x in ("rename_recording", "delete_recording_steps", "delete_recording", "delete_all_recordings")),
          str(acts[:12]))
    check("ใส่รหัสผิดลงบันทึกตรวจสอบ (action_code_failed) และนับครั้งผิดร่วมกับงานอันตรายอื่น",
          "action_code_failed" in acts)
    db.reset_auth_fails(f"actcode:{c.get('/api/me').get_json()['id']}")   # หน้าจอจริงด้านล่างลองรหัสผิดอีกครั้ง

    print("\n── หน้าจอจริง (Chromium) — กริดอัตโนมัติ · เมนูซ้าย 3 แบบ · สัญลักษณ์สิทธิ์ · ⏱ N วินาที · แก้/ลบบันทึก ──")
    ui_checks(uid)


def ui_checks(member_uid):
    db.set_permissions(member_uid, {"view_team": True, "manage_billing": True})
    db.create_user("boss2", "secret9", "บอสสอง", "super_admin")
    rec1 = make_recording("acctUI", 3)
    time.sleep(1.05)
    rec2 = make_recording("acctUI2", 1)
    auth.update_config(autostart_enabled=True, autostart_delay_sec=10)
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
        ctx = browser.new_context(viewport={"width": 1280, "height": 860}, timezone_id="Asia/Bangkok")
        page = ctx.new_page()
        page.on("pageerror", lambda e: JS_ERRORS.append(f"pageerror: {e}"))
        page.on("console", lambda m: JS_ERRORS.append(f"console.error: {m.text}") if m.type == "error" else None)
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_selector("#authLoginForm", state="attached", timeout=15000)
        page.evaluate("()=>{ if(typeof showAuth==='function') showAuth('login'); }")
        page.fill("#authLoginUser", "admin1")
        page.fill("#authLoginPw", "secret9")
        page.click("#authLoginForm button[type=submit]")
        page.wait_for_selector("#screen-app:not(.hidden)", timeout=15000)
        check("เข้าสู่ระบบหน้าจอจริงได้", True)

        def goto(view):
            page.click(f'.nav-item[data-view="{view}"]')
            page.wait_for_timeout(450)

        def overflow():
            return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")

        # ---- กริดอัตโนมัติ: ไม่มีแถบเลื่อนแนวนอนทั้งหน้า ทุกหน้า ทุกความกว้าง ----
        views = ["dashboard", "run", "history", "members", "billing", "live", "audit", "settings"]
        bad = []
        for width in (1920, 1366, 1024, 960):
            page.set_viewport_size({"width": width, "height": 860})
            for v in views:
                goto(v)
                ov = overflow()
                if ov > 1:
                    bad.append(f"{v}@{width}:+{ov}px")
        check("ทุกหน้า × กว้าง 1920/1366/1024/960 — ไม่ล้นแนวนอน", not bad, str(bad))
        page.set_viewport_size({"width": 1920, "height": 900})
        goto("dashboard")
        page.wait_for_timeout(900)            # ไทล์แดชบอร์ดลอยเข้าแบบไล่จังหวะ — รอให้นิ่งก่อนวัดตำแหน่ง
        # จำนวนการ์ดในแถวแรกจริง (auto-fit ยุบแทร็กว่างเป็น 0px — นับจาก gridTemplateColumns ไม่ได้)
        per_row = lambda sel: page.evaluate("""s=>{const k=[...document.querySelectorAll(s)].filter(e=>e.offsetParent);
            if(!k.length) return 0; const t=k[0].getBoundingClientRect().top;
            return k.filter(e=>Math.abs(e.getBoundingClientRect().top-t)<2).length}""", sel)
        cols = per_row("#view-dashboard > .tiles > .tile")
        page.set_viewport_size({"width": 960, "height": 860})
        page.wait_for_timeout(300)
        cols_small = per_row("#view-dashboard > .tiles > .tile")
        check("ไทล์แดชบอร์ดจัดคอลัมน์ตามความกว้าง (จอกว้าง 4 · จอแคบน้อยลง)", cols == 4 and 1 <= cols_small < 4,
              f"{cols} {cols_small}")
        page.set_viewport_size({"width": 1366, "height": 860})
        goto("billing")
        bcols = per_row("#view-billing > .tiles > .tile")
        check("ไทล์หน้า Balance ไม่ตายตัว 3 คอลัมน์แล้ว (จัดเอง)", bcols == 3 and
              'style="grid-template-columns:repeat(3,1fr)"' not in page.content(), str(bcols))
        goto("settings")
        sg = page.evaluate("""()=>{const g=document.querySelector('#view-settings .set-grid');
            return g ? [getComputedStyle(g).display, getComputedStyle(g).gridTemplateColumns.split(' ').length,
                        g.querySelectorAll(':scope > .card').length] : null}""")
        check("หน้าตั้งค่าเป็นกริดการ์ด (2 คอลัมน์ที่ 1366px) รวมทุกการ์ดไว้ในกริดเดียว",
              sg and sg[0] == "grid" and per_row("#view-settings .set-grid > .card") == 2 and sg[2] >= 6, str(sg))

        # ---- เมนูซ้าย 3 แบบ ----
        sw = lambda: page.evaluate("Math.round(document.querySelector('.sidebar').getBoundingClientRect().width)")
        lbl_vis = lambda: page.evaluate("getComputedStyle(document.querySelector('.nav-item .lbl')).display !== 'none'")
        check("ค่าเริ่มต้น: แสดงเมนูเต็ม (240px) · ปุ่ม 📌 แสดง ติดสถานะ", sw() == 240 and lbl_vis()
              and page.eval_on_selector('#sideMode [data-side="show"]', "b=>b.classList.contains('on')"), str(sw()))
        page.click('#sideMode [data-side="mini"]')
        page.wait_for_timeout(300)
        main_x = page.evaluate("Math.round(document.querySelector('.main').getBoundingClientRect().left)")
        check("กด ◧ ซ่อน → เหลือแถบไอคอน 68px · ซ่อนชื่อเมนู · เนื้อหาขยายเต็ม", sw() == 68 and not lbl_vis() and main_x <= 70,
              f"{sw()} main_x={main_x}")
        page.hover('.nav-item[data-view="run"]')
        page.wait_for_timeout(300)
        check("โหมดซ่อน: ชี้เมาส์ก็ไม่กาง (กดไอคอนใช้งานได้ · ชี้ดูชื่อจาก tooltip)", sw() == 68
              and page.get_attribute('.nav-item[data-view="run"]', "title") == "อัปโหลด & ค้นหา")
        page.click('.nav-item[data-view="run"]')
        page.wait_for_timeout(300)
        check("โหมดซ่อน: กดไอคอนเปลี่ยนหน้าได้", page.is_visible("#view-run"))
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#screen-app:not(.hidden)", timeout=15000)
        page.wait_for_timeout(300)
        check("เปิดใหม่ → จำโหมดเดิม (ซ่อน)", sw() == 68 and page.evaluate("document.body.classList.contains('side-mini')"))
        page.click('#sideMode [data-side="auto"]')
        page.mouse.move(900, 400)
        page.wait_for_timeout(400)
        narrow = sw()
        page.hover('.nav-item[data-view="dashboard"]')
        page.wait_for_timeout(450)
        wide = sw()
        main_x2 = page.evaluate("Math.round(document.querySelector('.main').getBoundingClientRect().left)")
        lbl_on_hover = lbl_vis()
        page.mouse.move(900, 400)
        page.wait_for_timeout(450)
        check("✨ อัตโนมัติ: ปกติแถบไอคอน → ชี้เมาส์กางเต็ม (ลอยทับ ไม่ดันเนื้อหา) → เอาเมาส์ออกหุบเอง",
              narrow == 68 and wide == 240 and lbl_on_hover and main_x2 <= 70 and sw() == 68,
              f"{narrow} {wide} {main_x2} {sw()}")
        page.click('#sideMode [data-side="show"]')
        page.wait_for_timeout(300)
        check("📌 แสดง → กลับเป็นเมนูเต็ม", sw() == 240 and lbl_vis())

        # ---- ⏱ เริ่มค้นอัตโนมัติใน N วินาที ----
        goto("run")
        page.wait_for_timeout(500)
        check("หน้าอัปโหลดมีแถว '⏱ เริ่มค้นอัตโนมัติใน [N] วินาที' — ค่าเริ่มต้นเปิด 10",
              page.is_checked("#runAutoStart") and page.input_value("#runAutoSec") == "10"
              and "เริ่มค้นอัตโนมัติใน" in page.inner_text("#autoRow")
              and page.is_checked("#runHideOnStart") and page.is_checked("#runDoneBell"))
        page.click("#runAutoInc")
        page.click("#runAutoInc")
        page.wait_for_timeout(800)
        check("กด + สองครั้ง → 12 · บันทึกลงเครื่องทันที", page.input_value("#runAutoSec") == "12"
              and auth.load_config().get("autostart_delay_sec") == 12, str(auth.load_config().get("autostart_delay_sec")))
        page.fill("#runAutoSec", "45")
        page.press("#runAutoSec", "Enter")
        page.wait_for_timeout(800)
        check("พิมพ์ 45 → ตัดเป็น 30 (ช่วง 3–30)", page.input_value("#runAutoSec") == "30"
              and auth.load_config().get("autostart_delay_sec") == 30)
        page.fill("#runAutoSec", "1")
        page.press("#runAutoSec", "Enter")
        page.wait_for_timeout(800)
        check("พิมพ์ 1 → ตัดเป็น 3", page.input_value("#runAutoSec") == "3" and auth.load_config().get("autostart_delay_sec") == 3)
        for _ in range(3):
            page.click("#runAutoDec")
        page.wait_for_timeout(700)
        check("กด − ต่ำกว่า 3 ไม่ได้", page.input_value("#runAutoSec") == "3")
        page.uncheck("#runAutoStart")
        page.uncheck("#runDoneBell")
        page.wait_for_timeout(800)
        cfg = auth.load_config()
        check("ปิดสวิตช์เริ่มเอง/กระดิ่ง → จำค่า · แถววินาทีจางลง",
              cfg.get("autostart_enabled") is False and cfg.get("done_bell") is False
              and page.eval_on_selector("#autoRow", "e=>e.classList.contains('off')"))
        goto("settings")
        page.click("#view-settings .set-grid > .card:first-child > .card-h")
        page.wait_for_timeout(500)
        check("หน้าตั้งค่าแสดงค่าเดียวกัน (สวิตช์ปิด · 3 วินาที · กระดิ่งปิด)",
              not page.is_checked("#setAutoStart") and page.input_value("#setAutoSec") == "3"
              and not page.is_checked("#setDoneBell") and page.is_checked("#setHideOnStart"))
        page.check("#setAutoStart")
        page.fill("#setAutoSec", "20")
        page.press("#setAutoSec", "Enter")
        page.check("#setDoneBell")
        page.wait_for_timeout(800)
        cfg = auth.load_config()
        check("แก้ที่หน้าตั้งค่า → บันทึกทันทีเช่นกัน (เปิด · 20 วิ · กระดิ่งเปิด)",
              (cfg.get("autostart_enabled"), cfg.get("autostart_delay_sec"), cfg.get("done_bell")) == (True, 20, True))
        goto("run")
        page.wait_for_timeout(500)
        check("กลับหน้าอัปโหลด → เห็น 20 วิ (ค่าที่จำไว้)", page.input_value("#runAutoSec") == "20" and page.is_checked("#runAutoStart"))

        # ---- แถบสถานะ: ปุ่ม 👁 แสดง/ซ่อน Chrome + วงแหวนนับถอยหลังตามวินาทีที่ตั้ง ----
        mg = server.manager
        mg.state, mg.browser_open, mg.hidden, mg.current_user_id = "running", True, True, 0
        page.wait_for_function("!document.getElementById('btnWinToggle').classList.contains('hidden')", timeout=8000)
        check("กำลังค้น + Chrome ซ่อนอยู่ → ปุ่ม '👁 แสดง Chrome'", page.inner_text("#btnWinToggle").strip() == "👁 แสดง Chrome")
        page.click("#btnWinToggle")
        page.wait_for_timeout(500)
        check("กด 👁 → ส่งคำขอแสดงให้ worker", mg._win_request == "show")
        mg.hidden = False
        page.wait_for_function("document.getElementById('btnWinToggle').textContent.includes('ซ่อน')", timeout=8000)
        page.click("#btnWinToggle")
        page.wait_for_timeout(500)
        check("แสดงอยู่ → ปุ่มเป็น '🫥 ซ่อน Chrome' กดแล้วขอซ่อน", mg._win_request == "hide")
        mg.state, mg.autostart_in, mg.autostart_total = "awaiting_login", 15, 20
        page.wait_for_function("document.getElementById('rbPct').textContent === '15 วิ'", timeout=8000)
        dash = page.evaluate("parseFloat(document.getElementById('rbRingFill').style.strokeDashoffset)")
        check("รอเข้าสู่ระบบ: วงแหวนนับถอยหลังเต็มสเกลตามวินาทีที่ตั้ง (15/20 = 75%)", abs(dash - 251.2 * 0.25) < 1.5, str(dash))
        check("ปุ่มเริ่มบอกวินาทีที่เหลือ", "เริ่มเองใน 15 วิ" in page.inner_text("#btnConfirmLogin"))
        mg.state, mg.browser_open, mg.hidden, mg._win_request, mg.autostart_in, mg.autostart_total = "idle", False, False, None, 0, 0

        # ---- สัญลักษณ์สิทธิ์ในตารางสมาชิก ----
        goto("members")
        page.wait_for_selector("#memberList table", timeout=8000)
        row_m = page.locator("#memberList tr", has_text="somchai")
        on = row_m.locator(".pchip.on")
        titles = [on.nth(i).get_attribute("title") for i in range(on.count())]
        check("สมาชิกที่ได้ 2 สิทธิ์ → สัญลักษณ์สว่าง 2 อัน (ชี้ดูชื่อสิทธิ์ได้) จาก 7 ตำแหน่งคงที่",
              on.count() == 2 and row_m.locator(".pchip").count() == 7
              and any("ตั้งอัตราค่าบริการ" in (t or "") for t in titles), str(titles))
        check("Super Admin → 👑 ครบทุกข้อ",
              page.locator("#memberList tr", has_text="boss2").locator(".pchip.crown").inner_text().strip() == "👑 ครบทุกข้อ")
        check("มีคำอธิบายสัญลักษณ์ (legend) เหนือตาราง · ไม่ใช้ป้ายข้อความยาวแบบเดิม",
              page.locator("#memberList .plegend .pchip").count() == 8
              and page.locator("#memberList td .badge.b-amber", has_text="ตั้งอัตรา").count() == 0)

        # ---- fmtHubTime (ตาราง 'สมาชิกทุกเครื่อง') ----
        got = page.evaluate("""()=>[fmtHubTime('2026-10-03T01:37:48'),
            fmtHubTime('Sat Oct 03 2026 01:37:48 GMT+0700 (Indochina Time)'),
            fmtHubTime('2026-10-02T18:37:48.000Z'), fmtHubTime('2026-10-03T01:38:02+07:00'),
            fmtHubTime(''), fmtHubTime('เมื่อวาน')]""")
        check("เวลาในตารางสมาชิกทุกเครื่องแสดงเป็น '3 ต.ค. 69 01:37' (ไม่มี 'ct 03 2026' อีก)",
              got == ["3 ต.ค. 69 01:37"] * 3 + ["3 ต.ค. 69 01:38", "—", "เมื่อวาน"], str(got))

        # ---- บันทึกโหมดทีละขั้น: ✎ · 👁 ดู/ลบสเต็ป · 🗑 ลบ · ลบทั้งหมด ----
        goto("audit")
        page.wait_for_selector("#recTable table", timeout=8000)
        check("ตารางบันทึกมีปุ่ม ✎ / 👁 / ⬇ / 🗑 ทุกชุด + ปุ่ม 'ลบทั้งหมด'",
              page.locator("#recTable tbody tr").count() == 2 and page.locator("#recTable a", has_text=".zip").count() == 2 and page.locator("#recTable button", has_text="✎").count() == 2
              and page.locator("#recTable button", has_text="🗑 ลบ").count() == 2 and page.is_visible("#btnRecDeleteAll"))
        row1 = page.locator("#recTable tbody tr", has_text="acctUI2")
        row1.locator("button", has_text="✎").click()
        page.wait_for_selector("#recRenameModal:not(.hidden)")
        page.fill("#recRenameInput", "บัญชีที่แก้แล้ว")
        page.click("#btnRecRenameSave")
        page.wait_for_selector("#recRenameModal.hidden", state="attached", timeout=5000)
        page.wait_for_function("document.getElementById('recTable').textContent.includes('บัญชีที่แก้แล้ว')", timeout=5000)
        check("✎ แก้ชื่อบัญชีที่แสดง → ตารางและ summary.json เปลี่ยน",
              json.loads((rec2.dir / "summary.json").read_text(encoding="utf-8"))["account"] == "บัญชีที่แก้แล้ว")
        page.locator("#recTable tbody tr", has_text="acctUI").filter(has_not_text="แก้แล้ว").locator("button", has_text="ดู/ลบสเต็ป").click()
        page.wait_for_selector("#recStepsModal:not(.hidden) .rec-step", timeout=8000)
        page.wait_for_function("[...document.querySelectorAll('#recStepsList img.rec-thumb')].every(i=>i.complete && i.naturalWidth>0)",
                               timeout=8000)
        check("👁 เปิดดูสเต็ป: 3 สเต็ป พร้อมภาพย่อที่โหลดได้จริง + ลิงก์ HTML",
              page.locator("#recStepsList .rec-step").count() == 3 and page.locator("#recStepsList img.rec-thumb").count() == 3
              and page.locator("#recStepsList a", has_text="HTML").count() == 3)
        page.locator("#recStepsList img.rec-thumb").first.click()
        page.wait_for_selector("#recShotModal:not(.hidden)")
        check("กดภาพย่อ → ดูภาพขนาดใหญ่", "#1" in page.inner_text("#recShotCap"))
        page.click("#btnRecShotClose")
        check("ปุ่มลบสเต็ปปิดอยู่จนกว่าจะเลือก", page.is_disabled("#btnRecStepsDelete"))
        page.locator("#recStepsList .rec-chk").nth(1).check()
        check("เลือก 1 สเต็ป → ปุ่มบอกจำนวน", "(1)" in page.inner_text("#btnRecStepsDelete") and page.is_enabled("#btnRecStepsDelete"))
        page.click("#btnRecStepsDelete")
        page.wait_for_selector("#actPwModal:not(.hidden)", timeout=5000)
        z = page.evaluate("[getComputedStyle(document.getElementById('actPwModal')).zIndex, getComputedStyle(document.getElementById('recStepsModal')).zIndex]")
        check("ช่องยืนยันรหัสผ่านลอยอยู่เหนือหน้าต่างดูสเต็ป", int(z[0]) > int(z[1]), str(z))
        page.fill("#actPwInput", "secret9")
        page.click("#btnActPwOk")
        page.wait_for_function("document.querySelectorAll('#recStepsList .rec-step').length === 2", timeout=8000)
        steps_left = [json.loads(ln)["i"] for ln in (rec1.dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
        check("ยืนยันรหัสผ่าน → สเต็ป 2 ถูกลบ (ไฟล์ภาพหาย · เหลือ 1,3)", steps_left == [1, 3]
              and not (rec1.dir / "step002.png").exists() and any("ลบ 1 สเต็ป" in d for d in dialogs), str(steps_left))
        page.click("#btnRecStepsClose")
        page.locator("#recTable tbody tr", has_text="แก้แล้ว").locator("button", has_text="🗑 ลบ").click()
        page.wait_for_selector("#actPwModal:not(.hidden)", timeout=5000)
        page.fill("#actPwInput", "wrongpw")
        page.click("#btnActPwOk")
        page.wait_for_timeout(800)
        check("ลบทั้งชุดด้วยรหัสผิด → แจ้งเตือน ไม่ลบ", rec2.dir.exists() and any("รหัสผ่านไม่ถูกต้อง" in d for d in dialogs),
              str(dialogs[-2:]))
        page.locator("#recTable tbody tr", has_text="แก้แล้ว").locator("button", has_text="🗑 ลบ").click()
        page.wait_for_selector("#actPwModal:not(.hidden)", timeout=5000)
        page.fill("#actPwInput", "secret9")
        page.click("#btnActPwOk")
        page.wait_for_function("document.querySelectorAll('#recTable tbody tr').length === 1", timeout=8000)
        check("รหัสถูก → ชุดหายจากตารางและดิสก์", not rec2.dir.exists())
        page.click("#btnRecDeleteAll")
        page.wait_for_selector("#actPwModal:not(.hidden)", timeout=5000)
        page.fill("#actPwInput", "secret9")
        page.click("#btnActPwOk")
        page.wait_for_function("document.getElementById('recTable').textContent.includes('ยังไม่มีบันทึก')", timeout=8000)
        check("ลบทั้งหมด → ไม่เหลือชุดบันทึก · ปุ่มลบทั้งหมดหาย", not rec1.dir.exists() and not page.is_visible("#btnRecDeleteAll")
              and any("ลบแล้ว 1 ชุด" in d for d in dialogs), str(dialogs[-1:]))
        browser.close()
    # 401 ก่อนเข้าสู่ระบบ / 403 จากรหัสผิดที่ตั้งใจทดสอบ = สถานะ HTTP ที่คาดไว้ ไม่ใช่ JS error (เหมือน test_ui_smoke)
    real = [e for e in JS_ERRORS if "favicon" not in e and not ("Failed to load resource" in e and
            any(f"status of {c}" in e for c in (400, 401, 403, 409)))]
    check("ตลอดทั้งเส้นทางไม่มี JavaScript error", not real, str(real[:5]))


try:
    code = 1
    main()
    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    code = 1 if FAIL else 0
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
