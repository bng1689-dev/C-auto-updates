#!/usr/bin/env python3
"""v3.12.0 — โหมดหน้าจอเดิม+เลือก 'บุคคล' หลังเข้าสู่ระบบ CRIMES · รหัสลบข้อมูล = รหัสผ่านสมาชิกเอง · ซิงก์ทันทีที่เปิดโปรแกรม

เจ้าของสั่ง: "เมื่อ login เข้าระบบ Crimes ได้แล้ว ให้ติ๊ก 'ใช้โหมดหน้าจอเดิม' แล้วกดยืนยันหรือตกลง
            เข้าแล้วให้เลือกบุคคล จากนั้นเริ่มทำงานต่อ · รหัสยืนยันลบข้อมูลให้ใช้รหัสเดียวกับที่สมาชิกตั้งเอง
            และเปลี่ยนตามเมื่อเปลี่ยนรหัส · ให้เริ่มซิงก์ข้อมูลตั้งแต่เปิดโปรแกรมแบบอัตโนมัติ"
  • engine.enter_classic_mode: ติ๊ก+ยืนยันบนกล่องจริง (Chromium + เว็บ CRIMES จำลอง) · เลือก 'บุคคล' ถูกตัว
    (มี 'นิติบุคคล' หลอก) · จำโหมดแล้วรีโหลด = เหลือแค่เลือกหมวด · เว็บรุ่นเดิม/หน้าเข้าสู่ระบบ = เงียบ ไม่แตะอะไร
  • การยืนยันงานอันตราย (ล้างประวัติทั้งระบบ/ล้างทั้งหมด/แก้ไขจำนวน/แก้ยอดเงิน) ใช้รหัสผ่านของคนที่ล็อกอิน:
    ผิด = 403+นับครั้ง · ถูก = ผ่าน · เปลี่ยนรหัสผ่านแล้วรหัสเก่าใช้ไม่ได้ทันที · endpoint ตั้งรหัสแยกถูกถอด (404)
  • _hub_worker ซิงก์รอบแรก 'ก่อน' เข้ารอบหลับ — เปิดโปรแกรมแล้วออนไลน์บนศูนย์กลางทันที
"""
import socket
import sys
import tempfile
import threading
import os
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v3120_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA / "d")
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "up")
from _app import APP, CHROME  # noqa: E402
import config  # noqa: E402

for _n in ("seed_account.json", config.HUB_SEED_FILE_NAME):
    (config.BASE_DIR / _n).unlink(missing_ok=True)

from backend import server  # noqa: E402
import db  # noqa: E402
import engine  # noqa: E402
import mock_crimes  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    server.hub._post = lambda *a, **k: {"ok": True}
    server._hub_kick = lambda *a, **k: None
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    print("── การยืนยันงานอันตราย = รหัสผ่านของสมาชิกเอง ──")
    r = c.post("/api/setup", json={"username": "admin1", "password": "secret9", "password2": "secret9",
                                   "display_name": "แอดมิน"})
    check("(เตรียม) ตั้ง Super Admin", r.status_code == 200, str(r.get_json()))
    c.post("/api/admin/members", json={"username": "worker1", "password": "pass66", "display_name": "คนงาน",
                                       "role": "member"})
    r = c.get("/api/action-code/state")
    check("สถานะรหัสยืนยัน: มีเสมอ (คือรหัสผ่านผู้ใช้เอง)", r.get_json().get("has_code") is True
          and r.get_json().get("mode") == "password", str(r.get_json()))
    r = c.post("/api/admin/action-code", json={"code": "1234"})
    check("endpoint ตั้งรหัสยืนยันแยก ถูกถอดแล้ว (404)", r.status_code == 404)

    r = c.post("/api/clear/searches")
    check("Super Admin ล้างทั้งระบบโดยไม่ใส่รหัส → 400 บอกให้ใส่รหัสผ่าน",
          r.status_code == 400 and "รหัสผ่าน" in r.get_json()["error"], str(r.get_json()))
    r = c.post("/api/clear/searches", json={"code": "wrong-pass"})
    check("รหัสผ่านผิด → 403", r.status_code == 403 and "ไม่ถูกต้อง" in r.get_json()["error"])
    status_seen = [r.status_code]
    for _ in range(8):
        r = c.post("/api/clear/searches", json={"code": "wrong-pass"})
        status_seen.append(r.status_code)
        if r.status_code == 429:
            break
    check("เดารหัสผ่านซ้ำ ๆ → ถูกล็อกชั่วคราว (429)", 429 in status_seen, str(status_seen))
    with db.get_conn() as conn:
        conn.execute("DELETE FROM auth_throttle")
    r = c.post("/api/clear/searches", json={"code": "secret9"})
    check("รหัสผ่านถูก → ล้างทั้งระบบได้", r.status_code == 200 and r.get_json().get("scope") == "all",
          str(r.get_json()))

    r = c.post("/api/admin/summary/adjust", json={"ym": "2026-10", "total": 5, "found": 3, "notfound": 2,
                                                  "error": 0, "cases": 4, "note": "x", "code": "secret9"})
    check("แก้ไขจำนวน (summary) ด้วยรหัสผ่านตัวเอง → ผ่าน", r.status_code == 200, str(r.get_json()))
    uid_w = db.get_user_by_username("worker1")["id"]
    r = c.post(f"/api/admin/billing/adjust/{uid_w}", json={"ym": "2026-10", "adj_count": 2,
                                                           "adj_amount": 20, "note": "", "code": "secret9"})
    check("แก้ยอดเงิน (billing) ด้วยรหัสผ่านตัวเอง → ผ่าน", r.status_code == 200, str(r.get_json()))

    print("\n── เปลี่ยนรหัสผ่าน → รหัสยืนยันเปลี่ยนตามทันที ──")
    r = c.post("/api/password", json={"current": "secret9", "new": "newsecret7"})
    check("(เตรียม) เปลี่ยนรหัสผ่าน admin1", r.status_code == 200, str(r.get_json()))
    r = c.post("/api/clear/searches", json={"code": "secret9"})
    check("รหัสเก่าใช้ยืนยันไม่ได้แล้ว (403)", r.status_code == 403)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM auth_throttle")
    r = c.post("/api/clear/all", json={"code": "newsecret7"})
    check("รหัสใหม่ใช้ได้ทันที — ล้างทั้งหมดผ่าน", r.status_code == 200 and r.get_json().get("ok"),
          str(r.get_json()))
    # เซสชันที่ปลดล็อกด้วย PASSCODE: ต้องกรอกรหัสผ่านแค่ครั้งเดียวในช่องยืนยัน (รีวิว PR #40 —
    # เดิมติด fresh_auth ซ้อน ทำให้เด้งขอรหัสผ่านอีกรอบทั้งที่เพิ่งพิมพ์ไปแล้ว)
    with c.session_transaction() as s:
        s["auth_method"] = "passcode"
    r = c.post("/api/clear/all", json={"code": "newsecret7"})
    check("เซสชัน PASSCODE: ล้างทั้งหมดด้วยรหัสผ่านครั้งเดียว ไม่เด้ง need_password ซ้ำ",
          r.status_code == 200 and r.get_json().get("ok"), str(r.get_json()))
    r = c.post("/api/clear/all", json={"code": "ผิดแน่นอน"})
    check("เซสชัน PASSCODE: รหัสผิดยังถูกปัดตามปกติ (403)", r.status_code == 403, str(r.get_json()))
    with db.get_conn() as conn:
        conn.execute("DELETE FROM auth_throttle")
    with c.session_transaction() as s:
        s["auth_method"] = "password"

    print("\n── เปลี่ยนรหัสผ่านแล้ว ตัวนับครั้งผิดของรหัสยืนยันต้องหายด้วย (รีวิว PR #40) ──")
    for _ in range(8):
        r = c.post("/api/clear/searches", json={"code": "wrong-again"})
        if r.status_code == 429:
            break
    check("(เตรียม) ใส่รหัสผิดจนช่องยืนยันถูกล็อก", r.status_code == 429, str(r.status_code))
    r = c.post("/api/password", json={"current": "newsecret7", "new": "third-pass9"})
    check("(เตรียม) เปลี่ยนรหัสผ่านอีกครั้ง", r.status_code == 200, str(r.get_json()))
    r = c.post("/api/clear/searches", json={"code": "third-pass9"})
    check("หลังเปลี่ยนรหัส: รหัสใหม่ใช้ยืนยันได้ทันที ไม่ติดล็อกของรหัสเก่า",
          r.status_code == 200, f"{r.status_code} {r.get_json()}")

    print("\n── สมาชิกธรรมดา: ล้างของตัวเองไม่ต้องใส่รหัส (ขอบเขตแคบ) ──")
    cw = server.app.test_client()
    r = cw.post("/api/login", json={"username": "worker1", "password": "pass66"})
    check("worker1 เข้าระบบ", r.status_code == 200)
    r = cw.post("/api/clear/searches")
    check("สมาชิกล้างเฉพาะของตัวเอง → ไม่ต้องใส่รหัส", r.status_code == 200 and r.get_json().get("scope") == "self")

    print("\n── ซิงก์ทันทีที่เปิดโปรแกรม (_hub_worker ส่งก่อนหลับ) ──")
    server.auth.update_config(hub_url="https://script.google.com/macros/s/X/exec",
                              hub_token="t", hub_enabled=True, hub_interval_min=1)
    calls = []
    real = (server._hub_push_now, server._members_sync_now, server._ledger_sync_now, server.time.sleep)
    server._hub_push_now = lambda *a, **k: calls.append("push") or {"ok": True}
    server._members_sync_now = lambda *a, **k: calls.append("members") or {"ok": True}
    server._ledger_sync_now = lambda *a, **k: calls.append("ledger") or {"ok": True}

    def fake_sleep(s):
        calls.append("sleep")
        raise RuntimeError("จบรอบทดสอบ")
    server.time.sleep = fake_sleep
    t = threading.Thread(target=server._hub_worker, daemon=True)
    t.start()
    t.join(5)
    server._hub_push_now, server._members_sync_now, server._ledger_sync_now, server.time.sleep = real
    check("เปิดโปรแกรม = ซิงก์ครบสามอย่าง 'ก่อน' เข้ารอบหลับรอบแรก",
          calls == ["push", "members", "ledger", "sleep"], str(calls))

    # ตัวซิงก์ตอนเปิดถือล็อกสมาชิกอยู่ → ล็อกอินช่วงนั้นต้อง 'รอ' ไม่ใช่ถือว่าเสร็จ (รีวิว PR #40)
    import time as _t
    server._members_lock.acquire()
    threading.Thread(target=lambda: (_t.sleep(0.8), server._members_lock.release()), daemon=True).start()
    t0 = _t.time()
    res = server._members_sync_or_wait("login", wait_s=5)
    waited = _t.time() - t0
    check("มีการซิงก์ค้างอยู่ → ตัวช่วยล็อกอินรอจนรอบนั้นเสร็จ (ไม่เกินเพดาน)",
          "กำลังซิงก์" in str(res.get("error")) and 0.6 <= waited < 4.0, f"{res} waited={waited:.2f}")
    check("ล็อกอินใช้ตัวช่วยที่รอ (ทั้งสองจุดใน api_login)",
          (Path(server.__file__).read_text(encoding="utf-8").split("def api_login")[1]
           .split("\ndef ")[0].count("_members_sync_or_wait(\"login\")")) == 2)
    server.auth.update_config(hub_enabled=False)

    print("\n── โหมดหน้าจอเดิม + เลือก 'บุคคล' (Chromium + เว็บ CRIMES จำลอง) ──")
    port = free_port()
    mock_crimes.serve(port)
    mock_crimes.STATE["logged_in"] = True
    mock_crimes.STATE["announce"] = False          # แยกเรื่อง — กล่องประกาศมีชุดทดสอบของตัวเอง
    url = f"http://127.0.0.1:{port}/bdasearch/#/bda/search/criteria/person"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, headless=True,
                               args=["--disable-background-networking"])
        ctx = b.new_context()
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        check("หลังเข้าสู่ระบบ: เว็บถามรูปแบบหน้าจอ (ยังไม่มีช่องเลขบัตร)",
              page.locator("#classicChk").count() == 1 and page.locator("#inputPid").count() == 0)
        notes = []
        ec = engine.enter_classic_mode(page, note=notes.append)
        check("ติ๊ก 'ใช้โหมดหน้าจอเดิม' + กดยืนยันให้เอง", ec["ticked"] is True, str(ec))
        check("เว็บจำโหมดเดิมแล้ว (localStorage)",
              page.evaluate("() => localStorage.getItem('classicMode')") == "1")
        for _ in range(3):
            if page.locator("#inputPid").count():
                break
            page.wait_for_timeout(400)
            ec2 = engine.enter_classic_mode(page, note=notes.append)
        check("เลือกหมวด 'บุคคล' แล้วถึงหน้าค้น (ช่องเลขบัตรโผล่)",
              page.locator("#inputPid").count() == 1,
              page.inner_text("body")[:200])
        check("เลือกถูกตัว — ไม่ใช่ 'นิติบุคคล' (หมวดบุคคลเท่านั้นที่พาไปหน้าค้น)",
              page.evaluate("() => S.person === true"))
        check("รายงานขั้นที่ทำในบันทึกการทำงาน",
              any("ใช้โหมดหน้าจอเดิม" in m for m in notes) and any("บุคคล" in m for m in notes), str(notes))
        ec3 = engine.enter_classic_mode(page, note=notes.append)
        check("ถึงหน้าค้นแล้วเรียกซ้ำ = เงียบ ไม่แตะอะไร", ec3 == {"ticked": False, "person": False}
              and page.locator("#inputPid").count() == 1, str(ec3))

        # รีโหลดหน้า (จำโหมดแล้ว) → เหลือหน้าเลือกหมวด — ทางกู้ของ search_one_id ต้องผ่านเอง
        # (goto ไป URL เดิมเป๊ะของ SPA ไม่นับเป็นโหลดใหม่ — ต้อง reload จริง สถานะในหน้า (S.person) จึงหาย)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        check("รีโหลด: ข้ามกล่องถามโหมด (จำไว้แล้ว) เหลือหน้าเลือกหมวด",
              page.locator("#classicChk").count() == 0 and page.locator("#inputPid").count() == 0
              and "เลือกประเภทการค้นหา" in page.inner_text("body"))
        ec4 = engine.enter_classic_mode(page)
        page.wait_for_timeout(300)
        check("หลังรีโหลด: คลิก 'บุคคล' รอบเดียวถึงหน้าค้น",
              ec4["person"] is True and page.locator("#inputPid").count() == 1, str(ec4))

        # เว็บรุ่นเดิม (ไม่มีหน้าคั่น) → ฟังก์ชันต้องเงียบสนิท
        mock_crimes.STATE["classic_prompt"] = False
        ctx2 = b.new_context()
        p2 = ctx2.new_page()
        p2.goto(url, wait_until="domcontentloaded")
        p2.wait_for_timeout(700)
        check("เว็บรุ่นเดิม: ถึงหน้าค้นตรง ๆ", p2.locator("#inputPid").count() == 1)
        ec5 = engine.enter_classic_mode(p2)
        check("เว็บรุ่นเดิม: เรียกแล้วเงียบ ไม่คลิกอะไร", ec5 == {"ticked": False, "person": False}
              and p2.locator("#inputPid").count() == 1)
        ctx2.close()

        # หน้าเข้าสู่ระบบ → เงียบเช่นกัน (ยังไม่ login ไม่มีอะไรให้ติ๊ก)
        mock_crimes.STATE["classic_prompt"] = True
        mock_crimes.STATE["logged_in"] = False
        ctx3 = b.new_context()
        p3 = ctx3.new_page()
        p3.goto(url, wait_until="domcontentloaded")
        p3.wait_for_timeout(700)
        ec6 = engine.enter_classic_mode(p3)
        check("หน้าเข้าสู่ระบบ: เงียบ ไม่แตะอะไร", ec6 == {"ticked": False, "person": False}
              and engine.is_login_page(p3))
        ctx3.close()

        print("\n── กรณีขอบจากรีวิว PR #40 (DOM จำลองตรง ๆ บน Chromium) ──")
        p4 = b.new_page()
        # (1) ปุ่ม 'ยืนยัน' ของหน้าข้างหลังกล่อง vs ปุ่ม 'ตกลง' ของกล่องเอง (โครงแบบ Nebular overlay ใน nb-layout)
        p4.set_content("""<html><body><div id="layout">
          <form><input id="pageField"><button type="button" id="pageOk"
            onclick="window.__page=(window.__page||0)+1">ยืนยัน</button></form>
          <div id="ov" style="position:fixed;inset:0;background:#0006"><div id="dlg" style="background:#fff;margin:60px;padding:20px">
            <label><input type="checkbox" id="cc"> <span>ใช้โหมดหน้าจอเดิม</span></label>
            <div><button type="button" id="dlgOk" onclick="window.__dlg=(window.__dlg||0)+1">ตกลง</button></div>
          </div></div></div></body></html>""")
        r1 = engine.enter_classic_mode(p4)
        check("กดปุ่ม 'ตกลง' ของกล่องเอง ไม่ใช่ปุ่ม 'ยืนยัน' ของหน้าข้างหลัง",
              r1.get("ticked") and p4.evaluate("() => [window.__dlg||0, window.__page||0]") == [1, 0]
              and p4.evaluate("() => document.getElementById('cc').checked"), str(r1))
        # (2) ติ๊กอยู่แล้ว + ไม่มีปุ่มที่ตรง → ต้องเงียบ (ไม่รายงานว่าทำ ไม่บันทึกซ้ำทุกรอบตรวจ)
        p4.set_content("""<html><body><div><label><input type="checkbox" id="cc" checked>
          <span>ใช้โหมดหน้าจอเดิม</span></label><button>ยืนยันการเปลี่ยนแปลง</button></div></body></html>""")
        notes2 = []
        r2 = [engine.enter_classic_mode(p4, note=notes2.append) for _ in range(3)]
        check("ติ๊กอยู่แล้ว+ไม่เจอปุ่ม → ไม่รายงาน ไม่บันทึกซ้ำ (3 รอบ = 0 บรรทัด)",
              all(x == {"ticked": False, "person": False} for x in r2) and notes2 == []
              and p4.evaluate("() => document.getElementById('cc').checked"), f"{r2} {notes2}")
        # (3) ช่องติ๊กแบบ custom (role=checkbox) ที่ติ๊กอยู่แล้ว → ห้ามคลิกจนกลายเป็นติ๊กออก
        p4.set_content("""<html><body><div id="d"><div id="cb" role="checkbox" aria-checked="true"
            onclick="this.setAttribute('aria-checked', this.getAttribute('aria-checked')==='true'?'false':'true')">
            <span>ใช้โหมดหน้าจอเดิม</span></div>
          <button onclick="window.__mode=document.getElementById('cb').getAttribute('aria-checked')">ยืนยัน</button></div></body></html>""")
        r3 = engine.enter_classic_mode(p4)
        check("custom checkbox ที่ติ๊กอยู่แล้ว: ไม่สลับออก และยืนยันด้วยโหมดเดิม",
              p4.evaluate("() => document.getElementById('cb').getAttribute('aria-checked')") == "true"
              and p4.evaluate("() => window.__mode") == "true", str(r3))
        # (4) label[for] — กล่องเดียวกันมีช่อง 'ไม่ต้องแสดงอีก' อยู่ก่อน ต้องติ๊กช่องของโหมดเดิมเท่านั้น
        p4.set_content("""<html><body><div><input id="dont" type="checkbox"><label for="dont">ไม่ต้องแสดงข้อความนี้อีก</label>
          <input id="classic" type="checkbox"><label for="classic">ใช้โหมดหน้าจอเดิม</label></div>
          <button>ยืนยัน</button></body></html>""")
        engine.enter_classic_mode(p4)
        check("label[for]: ติ๊กช่องของ 'ใช้โหมดหน้าจอเดิม' เท่านั้น ไม่ไปติ๊กช่องอื่นในกล่อง",
              p4.evaluate("() => [document.getElementById('classic').checked, document.getElementById('dont').checked]")
              == [True, False])
        p4.close()
        b.close()

    print("\n── แหล่งที่มา/การเดินสายในโปรแกรม ──")
    app_backend = Path(engine.__file__).resolve().parent
    worker_src = (app_backend / "worker.py").read_text(encoding="utf-8")
    html_src = (app_backend.parent / "frontend" / "index.html").read_text(encoding="utf-8")
    check("ขั้นรอเข้าสู่ระบบจัดการหน้าคั่นเอง (ตรวจพบ login ได้แม้ช่องเลขบัตรยังไม่โผล่)",
          worker_src.count("enter_classic_mode") >= 2)
    check("ทางกู้ใน search_one_id ก็เรียกหน้าคั่น (หลังรีโหลด/เด้งกลับ)",
          "enter_classic_mode" in (app_backend / "engine.py").read_text(encoding="utf-8").split("def search_one_id")[1][:3000])
    check("หน้าเว็บ: ไม่มีการ์ดตั้งรหัสยืนยันแยกแล้ว · ล้างทั้งหมดใช้รหัสผ่านของผู้ใช้",
          "newActionCode" not in html_src and "ใส่รหัสผ่านของคุณเพื่อยืนยัน" in html_src)
    cs_src = html_src.split("async function clearSearches")[1].split("\n}\n")[0]
    check("ล้างทั้งระบบขอรหัสผ่านในช่องปิดบัง (ไม่ใช้ prompt() ที่โชว์รหัสบนจอ — รีวิว PR #40)",
          "prompt(" not in cs_src and "askActionPassword(" in cs_src
          and 'id="actPwInput" class="field" type="password"' in html_src)
    check("นับถอยหลังเริ่มเองใช้เวลาหลังตรวจหน้าคั่น (ช่วงกด 'หยุด' ได้ครบ 30 วิ)",
          "now = time.time()" in worker_src.split("enter_classic_mode(page, note=self._log)")[1][:900])

    print(f"\n==== ผล: ผ่าน {PASS} · ตก {FAIL} ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    code = main()
    import shutil
    shutil.rmtree(TEST_DATA, ignore_errors=True)
    sys.exit(code)
