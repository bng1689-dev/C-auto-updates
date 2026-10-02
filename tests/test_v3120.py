#!/usr/bin/env python3
"""v3.12.0/v3.12.1 — โหมดหน้าจอเดิม+เลือก 'บุคคล' หลังเข้าสู่ระบบ CRIMES · รหัสลบข้อมูล = รหัสผ่านสมาชิกเอง · ซิงก์ทันทีที่เปิดโปรแกรม

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

    print("\n── ขั้นตอนหลังเข้าสู่ระบบ CRIMES ตามภาพหน้าจอจริงของเจ้าของ (Chromium + เว็บจำลองแบบเดียวกัน) ──")
    port = free_port()
    mock_crimes.serve(port)
    MS = mock_crimes.STATE
    MS.update(logged_in=True, announce=True, new_ui=True, mode_confirm=True, mode_confirm_delay=300)
    url = f"http://127.0.0.1:{port}/bdasearch/#/bda/search/criteria/person"
    engine.SEARCH_URL = url
    engine.set_speed(5)
    NO_OP = {"ticked": False, "confirm": "", "person": False}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, headless=True,
                               args=["--disable-background-networking"])
        ctx = b.new_context()
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        check("หลังเข้าสู่ระบบ: เว็บพาไปโหมดใหม่ (#/iv/) แม้เปิด URL โหมดเดิม + มีกล่อง 'มีอะไรใหม่' (ภาพที่ 1-2)",
              "#/iv/" in page.url and page.locator("#ann").count() == 1, page.url)
        check("กับดัก: โหมดใหม่ก็มีช่อง #inputPid — is_new_ui ต้องบอกว่าเป็นโหมดใหม่ (ห้ามนับว่าถึงหน้าค้น)",
              engine._find_id_input_selector(page) is not None and engine.is_new_ui(page))
        notes = []
        engine._LAST_MODE_CLICK = 0.0
        r0 = engine.enter_classic_mode(page, note=notes.append)
        check("กล่อง 'มีอะไรใหม่' ยังเปิด → ยังไม่กดสวิตช์ (ทำตามลำดับ ① ก่อน ②)",
              r0 == NO_OP and engine.is_new_ui(page), str(r0))
        check("① ปิด 'มีอะไรใหม่' ด้วยปุ่ม 'เข้าใจแล้ว'",
              engine.dismiss_announcement(page, note=notes.append) and page.locator("#ann").count() == 0)
        engine._LAST_MODE_CLICK = 0.0
        r1 = engine.enter_classic_mode(page, note=notes.append)
        check("② กดสวิตช์ [โหมดหน้าจอ (เดิม/ใหม่)] + กด 'ยืนยัน' ในกล่องที่เด้งช้า (สวิตช์เด้งกลับจนกว่าจะยืนยัน)",
              r1["ticked"] and r1["confirm"] == "ยืนยัน", str(r1))
        check("   เว็บจำโหมดเดิมแล้ว + สวิตช์อยู่ตำแหน่งปิด (สีเทา)",
              page.evaluate("() => localStorage.getItem('uiMode')") == "classic"
              and page.evaluate("() => !document.getElementById('modeToggle').checked"))
        check("③ คลิกการ์ด 'บุคคล' ในหน้า 'ระบบสืบค้น' → หน้าสืบค้นบุคคล (ช่อง placeholder 'เลขบัตรประชาชน')",
              r1["person"] and "criteria/person" in page.url
              and page.locator('input[placeholder="เลขบัตรประชาชน"]').count() == 1, f"{r1} {page.url}")
        check("④ พร้อมค้น: เห็นช่องเลขบัตร และไม่ใช่โหมดใหม่",
              engine._find_id_input_selector(page) is not None and not engine.is_new_ui(page))
        check("บันทึกการทำงานบอกครบทุกขั้น (ปิดประกาศ · สวิตช์ · ยืนยัน · บุคคล)",
              all(any(k in m for m in notes) for k in ("ปิดกล่องประกาศ", "โหมดหน้าจอ", "'ยืนยัน'", "บุคคล")), str(notes))
        n_before = len(notes)
        r2 = engine.enter_classic_mode(page, note=notes.append)
        check("ถึงหน้าค้นแล้วเรียกซ้ำ = เงียบ ไม่แตะอะไร ไม่บันทึกอะไร", r2 == NO_OP and len(notes) == n_before, str(r2))

        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(600)
        check("รีโหลดหน้า: อยู่โหมดเดิมต่อ ไม่มีกล่อง 'มีอะไรใหม่' ซ้ำ (ภาพที่ 1 ไม่ขึ้นทุกครั้ง)",
              not engine.is_new_ui(page) and page.locator("#ann").count() == 0
              and engine.dismiss_announcement(page) is False)

        page.goto(url.replace("search/criteria/person", "home"))
        page.wait_for_timeout(500)
        r3 = engine.enter_classic_mode(page)
        check("หน้า 'ระบบสืบค้น': คลิกการ์ด 'บุคคล' ถูกใบ (ไม่ใช่ยานพาหนะ/ข้อมูลคดี/เมนู 'ระบบสืบค้นบุคคล')",
              r3["person"] and "criteria/person" in page.url, page.url)

        print("\n── เว็บพากลับโหมดใหม่กลางรอบค้น → สลับกลับก่อนค้นเสมอ ──")
        pid = "3100000000001"
        MS["cases"][pid] = [{"charge": "ลักทรัพย์", "year": "2560", "status": "ฟ้อง", "caseNo": "1/2560"}]
        page.evaluate("() => { localStorage.setItem('uiMode','new'); location.hash = '#/iv/search/main'; }")
        page.wait_for_timeout(500)
        engine._LAST_MODE_CLICK = 0.0
        notes2 = []
        cases = engine.search_one_id(page, pid, note=notes2.append, reason="ตรวจสอบข้อมูลทั่วไป")
        check("search_one_id สลับเป็นโหมดเดิมเองแล้วค้นสำเร็จ (ได้ 1 คดี · เว็บถูกค้น 1 ครั้ง)",
              isinstance(cases, list) and len(cases) == 1 and MS["hits"].get(pid) == 1
              and not engine.is_new_ui(page), f"{cases} hits={MS['hits'].get(pid)} {notes2[-3:]}")
        real_ecm = engine.enter_classic_mode
        engine.enter_classic_mode = lambda page, note=None: dict(NO_OP)   # จำลอง: สวิตช์ใช้ไม่ได้
        page.evaluate("() => { localStorage.setItem('uiMode','new'); location.hash = '#/iv/search/main'; }")
        page.wait_for_timeout(500)
        pid2 = "3100000000002"
        err = ""
        try:
            engine.search_one_id(page, pid2, reason="ตรวจสอบข้อมูลทั่วไป")
        except RuntimeError as e:
            err = str(e)
        finally:
            engine.enter_classic_mode = real_ecm
        check("สลับโหมดไม่สำเร็จ → ไม่ค้นในโหมดใหม่ (กัน 'ไม่พบคดี' ปลอม) · error ชัด ลองแถวนี้ใหม่ได้",
              "โหมดหน้าจอใหม่" in err and MS["hits"].get(pid2, 0) == 0
              and engine.classify_error(err) == "retry", err[:160])
        ctx.close()

        ctx3 = b.new_context()
        MS["logged_in"] = False
        p3 = ctx3.new_page()
        p3.goto(url, wait_until="domcontentloaded")
        p3.wait_for_timeout(700)
        check("หน้าเข้าสู่ระบบ: เงียบ ไม่แตะอะไร", engine.enter_classic_mode(p3) == NO_OP and engine.is_login_page(p3))
        MS["logged_in"] = True
        ctx3.close()

        print("\n── กรณีขอบของสวิตช์/กล่องยืนยัน (DOM จำลองตรง ๆ) ──")
        HEAD = '<div class="hdr"><span>[ โหมดหน้าจอ (เดิม/ใหม่) ] :</span> {sw}</div>'
        NB = ('<label class="toggle-label"><input type="checkbox" id="t" style="position:absolute;width:1px;height:1px;'
              'overflow:hidden;clip:rect(0 0 0 0)" {chk} onchange="{h}"><span class="toggle">sw</span></label>')
        p4 = b.new_page()
        p4.set_content(HEAD.format(sw=NB.format(chk="", h="")))
        engine._LAST_MODE_CLICK = 0.0
        check("สวิตช์ปิดอยู่แล้ว (โหมดเดิม) → ไม่กด เงียบ",
              engine.enter_classic_mode(p4) == NO_OP and not p4.evaluate("() => document.getElementById('t').checked"))
        p4.set_content(HEAD.format(sw=NB.format(chk="checked", h="")))
        engine._LAST_MODE_CLICK = 0.0
        r = engine.enter_classic_mode(p4)
        check("สวิตช์เปิด (โหมดใหม่) ไม่มีกล่องยืนยัน → กดครั้งเดียว เหลือสถานะปิด",
              r["ticked"] and not p4.evaluate("() => document.getElementById('t').checked"), str(r))
        p4.set_content('<button id="pageOk" onclick="window.__page=1">ยืนยัน</button>' + HEAD.format(sw=NB.format(
            chk="checked",
            h="this.checked=true;setTimeout(()=>{const d=document.createElement('div');d.setAttribute('role','dialog');"
              "d.innerHTML='เปลี่ยนโหมดหน้าจอ? <button id=no>ยกเลิก</button> <button id=ok>ตกลง</button>';"
              "document.body.appendChild(d);d.querySelector('#ok').onclick=()=>{window.__dlg=1;"
              "document.getElementById('t').checked=false;d.remove();};},200)")))
        engine._LAST_MODE_CLICK = 0.0
        r = engine.enter_classic_mode(p4)
        check("กล่องยืนยันเด้งช้า: กด 'ตกลง' ในกล่อง — ไม่กดปุ่ม 'ยืนยัน' ของหน้าข้างหลัง",
              r["confirm"] == "ตกลง" and p4.evaluate("() => [window.__dlg||0, window.__page||0]") == [1, 0]
              and not p4.evaluate("() => document.getElementById('t').checked"), str(r))
        p4.set_content(HEAD.format(sw='<div id="sw" role="switch" aria-checked="true" onclick="this.setAttribute('
                                      "'aria-checked', this.getAttribute('aria-checked')==='true'?'false':'true')\">"
                                      "sw</div>"))
        engine._LAST_MODE_CLICK = 0.0
        engine.enter_classic_mode(p4)
        check("สวิตช์แบบ custom (role=switch) เปิดอยู่ → กดให้ปิด",
              p4.evaluate("() => document.getElementById('sw').getAttribute('aria-checked')") == "false")
        engine._LAST_MODE_CLICK = 0.0
        check("สวิตช์ custom ปิดแล้ว → เรียกซ้ำไม่กดกลับ",
              engine.enter_classic_mode(p4) == NO_OP
              and p4.evaluate("() => document.getElementById('sw').getAttribute('aria-checked')") == "false")
        p4.set_content('<div role="dialog">แจ้งเตือนทั่วไป <button>ปิด</button></div>' + HEAD.format(
            sw=NB.format(chk="checked", h="")))
        engine._LAST_MODE_CLICK = 0.0
        check("มีกล่องโต้ตอบอื่นเปิดค้าง → ยังไม่กดสวิตช์ (ไม่กดซ้อนใต้กล่อง)",
              engine.enter_classic_mode(p4)["ticked"] is False and p4.evaluate("() => document.getElementById('t').checked"))
        p4.set_content('<label><input type="checkbox" id="c"> ใช้โหมดหน้าจอเดิม</label>')
        engine._LAST_MODE_CLICK = 0.0
        engine.enter_classic_mode(p4)
        check("แบบช่องติ๊ก 'ใช้โหมดหน้าจอเดิม' (ติ๊ก = โหมดเดิม) → ติ๊กให้",
              p4.evaluate("() => document.getElementById('c').checked"))
        p4.set_content(HEAD.format(sw=NB.format(chk="checked", h="this.checked=true")))   # สวิตช์ไม่ยอมเปลี่ยน
        engine._LAST_MODE_CLICK = 0.0
        engine.enter_classic_mode(p4)
        p4.evaluate("() => { window.__n = 0; document.getElementById('t').addEventListener('click', () => window.__n++); }")
        engine.enter_classic_mode(p4)
        check("สวิตช์ไม่ตอบสนอง → ไม่กดรัวทุกรอบตรวจ (เว้นอย่างน้อย 10 วิ)",
              p4.evaluate("() => window.__n") == 0, p4.evaluate("() => window.__n"))
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
