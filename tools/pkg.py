"""ตำแหน่งและการแตกแพ็กเกจ — ใช้ร่วมกันระหว่าง tools/release.py กับ tests/_app.py

โมดูลนี้ 'ไม่มีผลข้างเคียงตอน import' (ไม่แตกไฟล์ ไม่แตะ sys.path) — ผู้เรียกสั่งเอง
"""
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PKG = "CRIMES_AUTO_update"
STAMP = BUILD / ".extracted-from"
MANIFEST = ROOT / "update-manifest.json"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def latest_zip():
    """(path ของ zip รุ่นล่าสุดตาม manifest, เวอร์ชัน)"""
    mf = load_manifest()
    name = mf["url"].rsplit("/", 1)[-1]
    p = ROOT / name
    if not p.exists():
        raise SystemExit(f"ไม่พบแพ็กเกจ {name} ในรีโป (manifest ชี้ไปที่ไฟล์นี้)")
    return p, str(mf.get("version", ""))


def app_dir():
    return BUILD / PKG / "app"


def extract(force=False, quiet=False):
    """แตก zip รุ่นล่าสุดลง build/ — คืน path ของ app/
    ถ้า build/ มีอยู่แล้วและไม่ force → หยุดพร้อมข้อความ (ห้ามลบงานที่ยังไม่ปล่อยเงียบ ๆ)"""
    zp, ver = latest_zip()
    target = BUILD / PKG
    if target.exists():
        if not force:
            raise SystemExit(f"build/{PKG} มีอยู่แล้ว — ใช้ --force ถ้าต้องการแตกทับ (การแก้ไขในนั้นจะหาย)")
        shutil.rmtree(target)
    BUILD.mkdir(exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(BUILD)
    STAMP.write_text(zp.name, encoding="utf-8")
    if not quiet:
        print(f"แตก {zp.name} (v{ver}) → {target}")
    return target / "app"


def stamp():
    try:
        return STAMP.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
