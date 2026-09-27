#!/usr/bin/env python3
"""v3.4.0 — ทดสอบตัวปิดกล่องประกาศ 'มีอะไรใหม่' ของเว็บ CRIMES

ใช้ Chromium จริงกับ DOM ที่จำลองตามภาพหน้าจอที่ผู้ใช้ส่งมา (หัวข้อ 'มีอะไรใหม่',
เวอร์ชัน 2.1.5, รายการฟีเจอร์, ปุ่ม 'เข้าใจแล้ว', ปุ่มกากบาท) แล้วตรวจว่า:
  * ปิดด้วยปุ่ม 'เข้าใจแล้ว' ได้จริง (เว็บจะได้จำว่าอ่านแล้ว ไม่เด้งซ้ำ)
  * ถ้ามีแต่กากบาท ก็ปิดได้
  * ไม่มีกล่อง → ไม่ทำอะไร และต้องไม่ error
  * ห้ามไปกดปุ่มชื่อคล้ายกันที่อยู่นอกกล่อง (เช่นปุ่มบนหน้าค้นหาปกติ)
  * ปิดแล้วช่องกรอกเลขบัตรที่เคยถูกบังกดได้จริง
"""
import sys
from pathlib import Path

from _app import APP, CHROME  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "backend"))

import engine  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


MODAL = """
<div id="overlay" style="position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:99">
  <div id="box" style="background:#fff;max-width:900px;margin:40px auto;padding:24px">
    <div style="display:flex;justify-content:space-between">
      <div>
        <div style="color:#64748b">อัปเดตล่าสุด</div>
        <h1>มีอะไรใหม่</h1>
        <p>2.1.5 (Updated: 12 September 2026)</p>
      </div>
      <button id="xbtn" aria-label="close">✕</button>
    </div>
    <div><b>ดูคนก่อนหน้าและคนถัดไป</b><p>ย้อนดูบุคคลที่ค้นหาไว้ได้</p></div>
    <div><b>อัปเดตข้อมูลล่าสุด</b><p>กดเพื่อเรียก API ใหม่ทั้งหมด</p></div>
    <div><b>ดึงข้อมูลเฉพาะส่วนที่ขาด</b><p>หลังรีเฟรช สามารถดึงข้อมูลประจำวันได้</p></div>
    <div><b>ดูภาพขนาดใหญ่</b><p>กดที่รูปภาพบุคคลเพื่อเปิดดูภาพขนาดใหญ่</p></div>
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span>ระบบจะแสดงข้อความนี้อัตโนมัติเพียงครั้งเดียวต่อเวอร์ชัน</span>
      <button id="okbtn">เข้าใจแล้ว</button>
    </div>
  </div>
</div>
"""

PAGE = """
<html><body>
  <h2>ค้นหาบุคคล</h2>
  <input id="inputPid" placeholder="เลขบัตรประชาชน">
  <button id="pageOk" onclick="window.__pageOk=(window.__pageOk||0)+1">ตกลง</button>
  <div id="slot"></div>
</body></html>
"""


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, headless=True,
                               args=["--disable-background-networking"])
        page = b.new_page()

        # 1) ไม่มีกล่อง → เงียบ ไม่ error
        page.set_content(PAGE)
        check("ไม่มีกล่องประกาศ → คืน False และไม่ error",
              engine.dismiss_announcement(page) is False)
        check("ไม่ไปกดปุ่มชื่อคล้ายกันบนหน้าปกติ",
              page.evaluate("() => window.__pageOk || 0") == 0)

        # 2) มีกล่องเต็มรูปแบบตามภาพ → ต้องกด 'เข้าใจแล้ว'
        page.set_content(PAGE)
        page.evaluate("(html) => { document.getElementById('slot').innerHTML = html; "
                      "window.__ok = 0; document.getElementById('okbtn')"
                      ".addEventListener('click', () => { window.__ok = 1; "
                      "document.getElementById('overlay').remove(); }); }", MODAL)
        notes = []
        check("ปิดกล่อง 'มีอะไรใหม่' ได้",
              engine.dismiss_announcement(page, note=notes.append) is True)
        check("กดปุ่ม 'เข้าใจแล้ว' จริง (ไม่ใช่ซ่อนทิ้ง)",
              page.evaluate("() => window.__ok") == 1)
        check("ไม่ไปกดปุ่ม 'ตกลง' ที่อยู่นอกกล่อง",
              page.evaluate("() => window.__pageOk || 0") == 0)
        check("กล่องหายไปจากหน้าจริง", page.locator("#overlay").count() == 0)
        check("รายงานให้ผู้ใช้เห็นในบันทึกการทำงาน",
              any("ปิดกล่องประกาศ" in m for m in notes), str(notes))

        # 3) ช่องกรอกเลขบัตรที่เคยถูกบัง กดได้จริงหลังปิด
        check("หลังปิดแล้วหา/กดช่องเลขบัตรได้",
              engine._find_id_input_selector(page) == "#inputPid")
        page.click("#inputPid")
        page.fill("#inputPid", "1234567890123")
        check("พิมพ์ลงช่องเลขบัตรได้", page.input_value("#inputPid") == "1234567890123")

        # 4) กล่องที่มีแต่ปุ่มกากบาท
        page.set_content(PAGE)
        page.evaluate("""() => {
          document.getElementById('slot').innerHTML =
            `<div id="overlay" style="position:fixed;inset:0;background:#0006">
               <div><h1>มีอะไรใหม่</h1><p>2.1.5</p>
               <button id="xbtn" aria-label="close">✕</button></div></div>`;
          document.getElementById('xbtn').addEventListener('click',
            () => document.getElementById('overlay').remove());
        }""")
        check("มีแต่กากบาท → ปิดได้", engine.dismiss_announcement(page) is True)
        check("กล่องหายไปจริง", page.locator("#overlay").count() == 0)

        # 5) เรียกซ้ำตอนไม่มีกล่องแล้ว → ไม่พัง
        check("เรียกซ้ำหลังปิดแล้ว → False เงียบ ๆ",
              engine.dismiss_announcement(page) is False)

        b.close()
    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


sys.exit(main())
