"""ตัวช่วยของชุดทดสอบ — ชี้ไปที่ 'โค้ดแอปที่แตกจากแพ็กเกจรุ่นล่าสุด' ในโฟลเดอร์ build/

ชุดทดสอบทั้งหมดทดสอบกับไบต์ที่แจกให้ผู้ใช้จริง (zip ตาม update-manifest.json) ไม่ใช่โค้ดลอย ๆ

ลำดับการหาโค้ดแอป:
  1. env CRIMES_APP_DIR   — ชี้ไปที่โฟลเดอร์ app/ ใดก็ได้ (เช่นทรีที่กำลังแก้อยู่)
  2. <repo>/build/CRIMES_AUTO_update/app
       ถ้ายังไม่มี → แตกจาก zip รุ่นล่าสุดให้เองครั้งเดียว
       ถ้ามีอยู่แล้ว → ใช้ทรีเดิมเสมอ (อาจมีการแก้ไขที่ยังไม่ปล่อยอยู่ ห้ามลบทิ้งเอง)
       ต้องการแตกใหม่จากแพ็กเกจ: python tools/release.py extract --force

ใช้ในไฟล์ทดสอบ:  from _app import APP, CHROME
  APP    = Path ของโฟลเดอร์ app/ (ถูกใส่ใน sys.path ให้แล้ว ทั้ง app/ และ app/backend/)
  CHROME = พาธ Chromium สำหรับ Playwright หรือ None = ใช้ตัวที่ playwright install ไว้
"""
import glob
import os
import sys
from pathlib import Path

# v3.10.0: รหัสลับศูนย์กลางฝังในโปรแกรม (config.DEFAULT_HUB_TOKEN) ทำให้เครื่องจริง "เชื่อมศูนย์กลาง" ตั้งแต่ติดตั้ง
# ชุดทดสอบห้ามยิงศูนย์กลางจริงเด็ดขาด → ปิดค่าฝังนี้ก่อน import โค้ดแอปเสมอ (ไฟล์นี้คือด่านแรกของทุกไฟล์ทดสอบ)
# ไฟล์ทดสอบที่ต้องการทดลองพฤติกรรม 'ฝังรหัส' ให้ตั้ง config/token เองกับศูนย์กลางจำลอง
os.environ.setdefault("CRIMES_NO_DEFAULT_HUB", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pkg  # noqa: E402  (ตำแหน่ง/การแตกแพ็กเกจ — ใช้ร่วมกับ tools/release.py)


def ensure_app():
    env = os.environ.get("CRIMES_APP_DIR")
    if env:
        p = Path(env).resolve()
        if not (p / "backend").is_dir():
            raise SystemExit(f"CRIMES_APP_DIR={p} ไม่ใช่โฟลเดอร์ app/ (ไม่มี backend/)")
        return p
    app = pkg.app_dir()
    if app.exists():
        zp, _ = pkg.latest_zip()
        st = pkg.stamp()
        if st and st != zp.name:
            print(f"[tests] หมายเหตุ: build/ แตกมาจาก {st} แต่รุ่นล่าสุดคือ {zp.name} "
                  "— ใช้ทรีเดิมต่อ (แตกใหม่: python tools/release.py extract --force)",
                  file=sys.stderr)
        return app
    return pkg.extract()


APP = ensure_app()
for _p in (str(APP), str(APP / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _chrome():
    c = os.environ.get("CRIMES_TEST_CHROME")
    if c:
        return c
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return hits[-1] if hits else None     # None = Chromium ที่ playwright install ไว้


CHROME = _chrome()
