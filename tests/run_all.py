#!/usr/bin/env python3
"""รันชุดทดสอบทั้งหมดของ CRIMES AUTO แล้วสรุปเป็นตาราง — ออกรหัส 1 ถ้ามีข้อใดตก

    python tests/run_all.py            # ทั้งหมด (ต้องมี Chromium: python -m playwright install chromium)
    python tests/run_all.py --quick    # เฉพาะชุดที่ไม่เปิดเบราว์เซอร์ (~1 นาที)
    python tests/run_all.py --only v350 e2e

แต่ละไฟล์รันเป็นโปรเซสแยก (ฐานข้อมูล/โฟลเดอร์ชั่วคราวของตัวเอง ไม่ปนกัน) และรันทีละไฟล์
เพราะบางชุดผูกพอร์ตตายตัว (8791 · 8797 · 8799 · 8801/8802 · 8806)
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# ลำดับ: เร็ว/ไม่ใช้เบราว์เซอร์ก่อน แล้วค่อยชุดเบราว์เซอร์ (ช้ากว่า)
SUITES = [
    # (ไฟล์, ใช้เบราว์เซอร์ไหม, คำอธิบาย)
    ("test_v2100.py", False, "เหตุผลการค้นตอนกดเริ่ม"),
    ("test_v300.py", False, "ขออนุมัติอัปเดต · เก็บกวาดหลังอัปเดต · แท็บสมาชิก"),
    ("test_v310.py", False, "กองกลาง · Balance ตามสิทธิ์ · สิทธิ์อัปเดตรายคน"),
    ("test_v320.py", False, "เชื่อมข้อมูลเรียลไทม์ · รหัสเชื่อมต่อ · presence"),
    ("test_v330.py", False, "ประวัติแยกรายบุคคล · รุ่น open"),
    ("test_v350.py", False, "ตัวอ่านเลขบัตร · จัดกลุ่ม error · ความคืบหน้าจากไฟล์ · คิว"),
    ("test_v351.py", False, "พบคดีแต่ไม่มีข้อหา → เหลืองทั้งแถว"),
    ("test_v360.py", False, "เขียนผลคอลัมน์ F เท่านั้น · แถบสถานะโฉมใหม่"),
    ("test_v361.py", False, "เลขบัตรอยู่ F (ช่องผล) ต้องถูกปฏิเสธ · ETA เริ่มนับใหม่หลังพัก"),
    ("test_v362.py", False, "เริ่มค้นเองหลังเข้าสู่ระบบ: ค่าเริ่มต้นเปิด 10 วิ · ตั้งได้ 3–30 (v3.14.0) · ปิดแล้วรอกดปุ่ม"),
    ("test_v364.py", False, "ลืมรหัสผ่าน (สมาชิก) ยืนยันด้วยชื่อที่ใช้เข้าเว็บ CRIMES · ยกเลิกทางกู้ Super Admin"),
    ("test_v370.py", False, "ไดเรกทอรีสมาชิกกลาง: 2 เครื่องซิงก์ผ่านสคริปต์ศูนย์กลางตัวจริง (Node)"),
    ("test_v380.py", False, "ชุดติดตั้งตัวเต็ม: บัญชีเริ่มต้นจากไฟล์ seed · ป้ายเตือนเปลี่ยนรหัส · ลบไฟล์ที่เลิกใช้"),
    ("test_v381.py", False, "ตาม redirect ของ Apps Script ให้ถูกชนิด (405 ตอนซิงก์สมาชิก) + แผนสำรอง"),
    ("test_v390.py", False, "สมุดกองกลางกลาง: 2 เครื่องเห็นรายการชุดเดียวกัน · Super Admin จัดการ · สมาชิกเห็นตัวเอง+ทีม"),
    ("test_v391.py", False, "จัดทีม/บันทึกกองกลางได้เฉพาะเครื่อง Super Admin ที่มีรหัสผู้ดูแล (เครื่องอื่นดูอย่างเดียว)"),
    ("test_v3100.py", False, "สมัครใช้งานเอง → Super Admin อนุมัติ · URL+รหัสลับฝัง · จดจำการเข้าใช้งาน · ดึงไดเรกทอรีก่อน seed"),
    ("test_v3110.py", False, "ยืนยันผลการค้นตามจำนวนแถว · ส่งไฟล์ผลขึ้น Google Drive ผ่านศูนย์กลาง (Superadmin ตั้งค่า)"),
    ("test_boot.py", False, "การเปิดโปรแกรม (desktop.py) — จอขาว/พอร์ตค้าง"),
    ("test_tools.py", False, "เครื่องมือปล่อยรุ่น: build --allow-new-files/--remove · verify เทียบ manifest ออนไลน์"),
    ("test_installer.py", False, "ตัวสร้างชุดติดตั้งตัวเต็ม (build_installer.py) กับแพ็กเกจจำลอง"),
    ("test_v3120.py", True, "โหมดหน้าจอเดิม+เลือก 'บุคคล' หลัง login CRIMES · รหัสลบข้อมูล=รหัสผ่านสมาชิก · ซิงก์ทันทีที่เปิด"),
    ("test_v3130.py", False, "สิทธิ์ผู้ดูแลศูนย์กลางผูกกับบัญชี Superadmin (ไม่มี 🔑 ในเครื่อง) · ถอดคู่มือออกจากหน้าจอ"),
    ("test_v3140.py", True, "กริดอัตโนมัติ · เมนูซ้าย 3 แบบ · สัญลักษณ์สิทธิ์ · เริ่มค้นใน N วิ · ย่อโปรแกรม+กระดิ่ง · แก้/ลบบันทึกทีละขั้น"),
    ("test_v3141.py", False, "ศูนย์กลางไม่รับ ADMIN_TOKEN: เตือนเฉพาะเมื่อคำขอที่เซ็นจริงถูกปัด · ผูกใหม่แล้วการแก้ค้างขึ้นกลาง"),
    ("test_v3150.py", False, "สมาชิกทุกเครื่อง: บัญชีในเครื่องอื่นส่งคำขอสมัครเอง → Superadmin อนุมัติ/ตั้งสิทธิ์ได้แม้เครื่องนั้นออฟไลน์ · ตารางรวมรายคน"),
    ("test_announce.py", True, "ปิดกล่อง 'มีอะไรใหม่' ของเว็บ CRIMES"),
    ("test_runbar.py", True, "แถบสถานะ/ปุ่มควบคุมรอบค้น + เข้าสู่ระบบใหม่"),
    ("test_ui_smoke.py", True, "ไล่ครบทุกเมนูบน Chromium จริง ต้องไม่มี JS error"),
    ("test_e2e.py", True, "ทั้งระบบ: worker จริง + เว็บ CRIMES จำลอง"),
]
RESULT_RE = re.compile(r"ผล: ผ่าน (\d+) · ตก (\d+)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="ข้ามชุดที่ต้องใช้เบราว์เซอร์")
    ap.add_argument("--only", nargs="*", default=None, help="รันเฉพาะไฟล์ที่ชื่อมีคำนี้")
    ap.add_argument("--timeout", type=int, default=900, help="วินาทีต่อไฟล์")
    args = ap.parse_args()

    picked = []
    for name, browser, desc in SUITES:
        if args.quick and browser:
            continue
        if args.only and not any(k in name for k in args.only):
            continue
        picked.append((name, browser, desc))
    if not picked:
        print("ไม่มีชุดทดสอบตรงเงื่อนไข")
        return 2

    rows = []
    total_pass = total_fail = 0
    for name, browser, desc in picked:
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                   CRIMES_UPLOAD_DIR=tempfile.mkdtemp(prefix="crimes_up_"))
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(HERE / name)], env=env, cwd=str(HERE),
                               capture_output=True, text=True, timeout=args.timeout)
            out = (r.stdout or "") + (r.stderr or "")
            code = r.returncode
        except subprocess.TimeoutExpired as e:
            out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\n[หมดเวลา]"
            code = 124
        secs = time.time() - t0
        m = RESULT_RE.findall(out)
        p, f = (int(m[-1][0]), int(m[-1][1])) if m else (0, 0)
        ok = code == 0 and f == 0 and m
        total_pass += p
        total_fail += f if m else 0
        status = "✓" if ok else "✗"
        rows.append((status, name, p, f, secs, desc))
        print(f"{status} {name:20s} ผ่าน {p:3d} · ตก {f:2d} · {secs:5.0f}s  — {desc}", flush=True)
        if not ok:
            fails = [ln for ln in out.splitlines() if "✗" in ln or "Traceback" in ln or "Error" in ln]
            for ln in fails[:12]:
                print("     " + ln.strip()[:160])
            if not m:
                # ล้มก่อนจบ (เช่นรอ selector ไม่ทัน) — โชว์ท้ายบันทึกเพื่อให้รู้ว่าตกที่ข้อไหน/บรรทัดไหน (CI ดูได้เลย)
                print("     (ไม่มีบรรทัดสรุปผล — โปรเซสล้มก่อนจบ; ท้ายบันทึกของไฟล์นี้:)")
                for ln in [x for x in out.splitlines() if x.strip()][-25:]:
                    print("     │ " + ln.rstrip()[:200])
    bad = [r for r in rows if r[0] == "✗"]
    print(f"\nรวม: ผ่าน {total_pass} · ตก {total_fail} · ไฟล์ที่มีปัญหา {len(bad)}/{len(rows)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
