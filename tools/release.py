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

    changed, extra_local = [], []
    with zipfile.ZipFile(prev_zip) as zin:
        names = [i.filename for i in zin.infolist()]
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zout:
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
    # ไฟล์ใหม่ใน build/ ที่ไม่มีในแพ็กเกจรุ่นก่อน — ต้องตั้งใจเพิ่มเท่านั้น
    for p in tree.rglob("*"):
        if p.is_file():
            rel = p.relative_to(ROOT / "build").as_posix()
            if rel not in names and "__pycache__" not in rel and not rel.endswith(".pyc"):
                extra_local.append(rel)
    if extra_local:
        msg = "ไฟล์ใหม่ใน build/ ที่ไม่ได้อยู่ในแพ็กเกจ (ไม่ถูกรวม): " + ", ".join(extra_local)
        if args.allow_new_files:
            print("  ! " + msg)
        else:
            out_zip.unlink(missing_ok=True)
            sys.exit(msg + "\n   ถ้าตั้งใจเพิ่มไฟล์ใหม่จริง ใช้ --allow-new-files (ไฟล์ใหม่ยังต้องใส่ zip เอง)")
    if f"{PKG}/app/VERSION" not in changed:
        out_zip.unlink(missing_ok=True)
        sys.exit("VERSION ไม่เปลี่ยน — ผิดปกติ")

    # ---- ด่านตรวจแพ็กเกจ ----
    with zipfile.ZipFile(out_zip) as z:
        got = [i.filename for i in z.infolist()]
        assert got == names, "รายการไฟล์ไม่ตรงกับรุ่นก่อน"
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
    print(f"  manifest: v{new} · open={bool(args.open)}")
    print("ถัดไป: python tests/run_all.py --quick → git add -A → commit → push → PR → merge → release.py verify")


def cmd_verify(args):
    mf = load_manifest()
    ver = mf["version"]
    print(f"manifest ในเครื่อง: v{ver}")
    live_mf = json.loads(urllib.request.urlopen(RAW_BASE + "update-manifest.json", timeout=30).read())
    print(f"manifest ออนไลน์:  v{live_mf.get('version')}"
          + ("" if live_mf.get("version") == ver else "   ← ยังไม่ตรง (แคช CDN ของ GitHub ~5 นาที หรือยังไม่ merge)"))
    local_zip = ROOT / mf["url"].rsplit("/", 1)[-1]
    data = urllib.request.urlopen(mf["url"], timeout=120).read()
    live = hashlib.sha256(data).hexdigest()
    print(f"zip ออนไลน์ sha256: {live}")
    print(f"zip ในเครื่อง      : {sha256(local_zip) if local_zip.exists() else '(ไม่มีไฟล์)'}")
    print(f"manifest sha256    : {mf['sha256']}")
    ok = live == mf["sha256"] == (sha256(local_zip) if local_zip.exists() else live)
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
