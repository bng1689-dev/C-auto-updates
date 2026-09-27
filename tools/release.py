#!/usr/bin/env python3
"""เครื่องมือปล่อยรุ่น CRIMES AUTO — แตกแพ็กเกจ / สร้าง zip + manifest / ตรวจของที่ขึ้นออนไลน์

ขั้นตอนปล่อยรุ่นใหม่ (ทำตามลำดับ):
  1. python tools/release.py extract            แตก zip รุ่นล่าสุดลง build/ (ครั้งแรก หรือ --force)
  2. แก้โค้ดใน build/CRIMES_AUTO_update/app/...
  3. python tests/run_all.py                    ต้องผ่านทั้งหมด (ทดสอบกับทรีใน build/)
  4. python tools/release.py build --version 3.6.0 --notes "เวอร์ชัน 3.6.0 — ..." [--open]
       → CRIMES_AUTO_update_v3.6.0.zip + update-manifest.json + รายการใน CHANGELOG.md
  5. python tests/run_all.py --quick            รอบยืนยันสั้น ๆ หลังเลขรุ่นเปลี่ยน
  6. git add / commit / push → เปิด PR → merge เข้า main
  7. python tools/release.py verify             ดาวน์โหลดของจริงจาก GitHub มาตรวจ sha256

กติกาของแพ็กเกจ (สคริปต์บังคับให้):
  • สร้างจาก zip รุ่นก่อน แทนเฉพาะไฟล์ที่เปลี่ยน — รายการไฟล์ต้องเท่าเดิม (กันไฟล์หายเหมือน v2.9.2)
  • ต้องไม่มี tools/ หรือไฟล์ผู้ดูแล (hub_gas.js, กุญแจ) หลุดเข้าไป
  • ทุกไฟล์ .py ต้อง compile ผ่าน · ฟังก์ชันแกนของหน้าแรกต้องอยู่ครบ
  • เลขรุ่นต้องใหม่กว่ารุ่นปัจจุบัน
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pkg import ROOT, PKG, MANIFEST, load_manifest, extract as pkg_extract  # noqa: E402

CHANGELOG = ROOT / "CHANGELOG.md"
RAW_BASE = "https://raw.githubusercontent.com/bng1689-dev/C-auto-updates/main/"
FORBIDDEN = ("tools/", "keygen", "hub_gas", "crimes_license_private", ".key", "__pycache__", ".pyc")

# ฟังก์ชันที่ 'ต้องมี' ในแพ็กเกจ — หายไปเมื่อไหร่โปรแกรมเปิดมาเป็นหน้าดำ/เริ่มรอบไม่ได้ (เคยเกิดจริง v2.9.2)
CORE_HTML = ("function showApp", "function checkAuth", "function showAuth", "function bootApp",
             "function startPolling", "function updateBanner", "function loadQueue", "function renderQueue")
CORE_ENGINE = ("def normalize_id", "def scan_progress", "def search_one_id", "def dismiss_announcement",
               "def apply_row_review")
CORE_WORKER = ("def _await_login", "def _prepare_rows", "def _retry_error_rows", "class RunManager")
CORE_SERVER = ("/api/queue/prune", "/api/run/start", "/api/status", "def _job_progress")


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def cmd_extract(args):
    pkg_extract(force=args.force)


def _validate_package(path, expected_names, new):
    """ด่านตรวจแพ็กเกจ — คืนรายการไฟล์ใน zip · โยน AssertionError/SyntaxError เมื่อไม่ผ่าน"""
    with zipfile.ZipFile(path) as z:
        got = [i.filename for i in z.infolist()]
        assert got == expected_names, "รายการไฟล์ไม่ตรงกับรุ่นก่อน (+ไฟล์ใหม่ที่อนุญาต)"
        bad = [n for n in got for f in FORBIDDEN if f in n]
        assert not bad, f"มีไฟล์ต้องห้ามในแพ็กเกจ: {bad}"
        assert z.read(f"{PKG}/app/VERSION").decode().strip() == new
        html = z.read(f"{PKG}/app/frontend/index.html").decode("utf-8")
        eng = z.read(f"{PKG}/app/backend/engine.py").decode("utf-8")
        wk = z.read(f"{PKG}/app/backend/worker.py").decode("utf-8")
        srv = z.read(f"{PKG}/app/backend/server.py").decode("utf-8")
        for group, text, label in ((CORE_HTML, html, "index.html"), (CORE_ENGINE, eng, "engine.py"),
                                   (CORE_WORKER, wk, "worker.py"), (CORE_SERVER, srv, "server.py")):
            missing = [fn for fn in group if fn not in text]
            assert not missing, f"{label} ขาดฟังก์ชันแกน: {missing}"
        for n in got:
            if n.endswith(".py"):
                compile(z.read(n).decode("utf-8"), n, "exec")
    return got


def cmd_build(args):
    mf = load_manifest()
    cur = str(mf.get("version", "0"))
    new = args.version.strip().lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", new):
        sys.exit(f"เลขรุ่นต้องเป็น X.Y.Z (ได้ {new!r})")
    if vtuple(new) <= vtuple(cur):
        sys.exit(f"เลขรุ่น {new} ต้องใหม่กว่ารุ่นปัจจุบัน {cur}")
    prev_zip = ROOT / mf["url"].rsplit("/", 1)[-1]
    if not prev_zip.exists():
        sys.exit(f"ไม่พบ zip รุ่นก่อน {prev_zip.name}")
    tree = ROOT / "build" / PKG
    app = tree / "app"
    if not app.is_dir():
        sys.exit("ยังไม่มี build/ — รัน: python tools/release.py extract")
    (app / "VERSION").write_text(new, encoding="utf-8")

    out_zip = ROOT / f"{PKG}_v{new}.zip"
    if out_zip.exists() and not args.overwrite:
        sys.exit(f"{out_zip.name} มีอยู่แล้ว (ใช้ --overwrite ถ้าตั้งใจสร้างทับ)")
    # v3.6.1: เขียนลงไฟล์ชั่วคราวก่อน ผ่านด่านตรวจครบแล้วค่อยเปลี่ยนชื่อเป็น zip จริง — เดิมไฟล์ต้องห้าม
    # (เช่น hub_gas.js) ที่หลุดเข้า build/ ถูกเขียนลง zip ชื่อจริงก่อนด่านตรวจจะปฏิเสธ แล้ว zip นั้นค้างอยู่
    # ในรีโป (git add -A กวาดขึ้นไปได้) และขวางการ build ครั้งถัดไปจนกว่าจะลบเอง
    part = out_zip.with_name(out_zip.name + ".part")

    changed, added = [], []
    with zipfile.ZipFile(prev_zip) as zin:
        names = [i.filename for i in zin.infolist()]
        # ไฟล์ใหม่ใน build/ ที่ไม่มีในแพ็กเกจรุ่นก่อน — ต้องตั้งใจเพิ่มเท่านั้น (--allow-new-files)
        extra_local = sorted(
            p.relative_to(ROOT / "build").as_posix() for p in tree.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
            and p.relative_to(ROOT / "build").as_posix() not in names)
        if extra_local and not args.allow_new_files:
            sys.exit("ไฟล์ใหม่ใน build/ ที่ไม่ได้อยู่ในแพ็กเกจรุ่นก่อน: " + ", ".join(extra_local)
                     + "\n   ถ้าตั้งใจเพิ่มไฟล์ใหม่จริง ใช้ --allow-new-files (จะถูกใส่ลง zip และตรวจเหมือนไฟล์อื่น)")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if not info.is_dir():
                    local = ROOT / "build" / info.filename
                    if local.exists():
                        new_bytes = local.read_bytes()
                        if new_bytes != data:
                            changed.append(info.filename)
                            data = new_bytes
                    else:
                        print(f"  ! ไม่พบ {info.filename} ใน build/ — ใช้ของรุ่นก่อน")
                zout.writestr(info, data)
            # v3.6.1: --allow-new-files ต้องใส่ไฟล์ใหม่ลง zip จริง (เดิมแค่เตือนแล้วปล่อยผ่าน → แพ็กเกจขาดไฟล์
            # ทั้งที่ manifest/sha256 ออกมาสวยงาม — โปรแกรม import ไม่เจอหลังอัปเดต)
            for rel in extra_local:
                zout.write(ROOT / "build" / rel, arcname=rel)
                added.append(rel)
                print(f"  + เพิ่มไฟล์ใหม่ {rel}")
    # ---- ด่านตรวจแพ็กเกจ (บนไฟล์ชั่วคราว) — ไม่ผ่านข้อไหน ไฟล์ชั่วคราวถูกลบ ไม่มี zip ค้าง ----
    try:
        if f"{PKG}/app/VERSION" not in changed:
            sys.exit("VERSION ไม่เปลี่ยน — ผิดปกติ")
        got = _validate_package(part, names + added, new)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(out_zip)

    digest = sha256(out_zip)
    notes = args.notes.strip() if args.notes else f"เวอร์ชัน {new}"
    mf_new = {"version": new, "url": RAW_BASE + out_zip.name, "sha256": digest,
              "open": bool(args.open), "notes": notes}
    MANIFEST.write_text(json.dumps(mf_new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- เติมรายการใน CHANGELOG.md ----
    try:
        import datetime
        from changelog import format_entry, HEADER
        entry = format_entry(new, datetime.date.today().isoformat(), notes, bool(args.open))
        body = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else HEADER + "\n"
        head, sep, rest = body.partition("\n## ")
        CHANGELOG.write_text(head.rstrip("\n") + "\n\n" + entry + ("\n## " + rest if sep else ""),
                             encoding="utf-8")
    except Exception as e:      # บันทึกการเปลี่ยนแปลงพลาดไม่ควรทำให้การปล่อยรุ่นล้ม
        print(f"  ! เติม CHANGELOG.md ไม่สำเร็จ: {e}")

    print(f"✓ {out_zip.name}  ({out_zip.stat().st_size:,} ไบต์ · {len(got)} รายการ)")
    print(f"  sha256: {digest}")
    print(f"  ไฟล์ที่เปลี่ยนจาก v{cur}: " + ", ".join(n.split("/", 1)[1] for n in changed))
    if added:
        print("  ไฟล์ใหม่ที่เพิ่มเข้าแพ็กเกจ: " + ", ".join(n.split("/", 1)[1] for n in added))
    print(f"  manifest: v{new} · open={bool(args.open)}")
    print("ถัดไป: python tests/run_all.py --quick → git add -A → commit → push → PR → merge → release.py verify")


def cmd_verify(args):
    """ตรวจ 'ของที่ผู้ใช้ปลายทางจะได้รับจริง' — manifest ออนไลน์ต้องตรงกับในเครื่องทุกช่อง และ zip ที่
    manifest ออนไลน์ชี้ต้องมี sha256 ตรงกับที่ประกาศ (v3.6.1 — เดิมดาวน์โหลด zip ตาม URL ในเครื่องมาเทียบ
    จึงบอก ✓ ได้ทั้งที่ manifest ออนไลน์ยังเป็นรุ่นเก่า หรือชี้ URL/sha256 ผิด)"""
    mf = load_manifest()
    print(f"manifest ในเครื่อง: v{mf['version']}")
    live_mf = json.loads(urllib.request.urlopen(RAW_BASE + "update-manifest.json", timeout=30).read())
    print(f"manifest ออนไลน์:  v{live_mf.get('version')}")
    diff = [k for k in ("version", "url", "sha256", "open") if live_mf.get(k) != mf.get(k)]
    for k in diff:
        print(f"  ✗ {k}: ออนไลน์={live_mf.get(k)!r}  ในเครื่อง={mf.get(k)!r}")
    if diff:
        print("  (ยังไม่ merge หรือแคช CDN ของ GitHub ~5 นาที — รอสักครู่แล้วรันใหม่)")
    url = live_mf.get("url") or mf["url"]
    live = hashlib.sha256(urllib.request.urlopen(url, timeout=120).read()).hexdigest()
    local_zip = ROOT / mf["url"].rsplit("/", 1)[-1]
    local = sha256(local_zip) if local_zip.exists() else None
    print(f"zip ที่ manifest ออนไลน์ชี้ sha256 : {live}")
    print(f"sha256 ที่ manifest ออนไลน์ประกาศ  : {live_mf.get('sha256')}")
    print(f"zip ในเครื่อง                     : {local or '(ไม่มีไฟล์)'}")
    ok = not diff and live == live_mf.get("sha256") == mf["sha256"] == (local or live)
    print("✓ ตรงกันทั้งหมด" if ok else "✗ ไม่ตรง — ห้ามให้ผู้ใช้อัปเดตจนกว่าจะแก้")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="แตก zip รุ่นล่าสุดลง build/")
    e.add_argument("--force", action="store_true", help="แตกทับ build/ ที่มีอยู่ (การแก้ไขในนั้นหาย)")
    b = sub.add_parser("build", help="สร้าง zip รุ่นใหม่ + manifest จาก build/")
    b.add_argument("--version", required=True)
    b.add_argument("--notes", default="", help="บันทึกรุ่นสำหรับ manifest (คั่นหัวข้อด้วย ' · ')")
    b.add_argument("--open", action="store_true", help="เปิดให้ทุกเครื่องอัปเดตรุ่นนี้โดยไม่ต้องได้รับสิทธิ์")
    b.add_argument("--overwrite", action="store_true")
    b.add_argument("--allow-new-files", action="store_true")
    sub.add_parser("verify", help="ดาวน์โหลด manifest+zip จาก GitHub มาตรวจ sha256")
    args = ap.parse_args()
    return {"extract": cmd_extract, "build": cmd_build, "verify": cmd_verify}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
