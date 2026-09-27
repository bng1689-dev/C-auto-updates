#!/usr/bin/env python3
"""เครื่องมือปล่อยรุ่น (tools/release.py) — ทดสอบกับรีโปจำลองในโฟลเดอร์ชั่วคราว ไม่แตะรีโปจริง/เครือข่าย

ข้อค้นพบจากรีวิว PR #23:
  • build --allow-new-files เดิมแค่เตือนแล้วปล่อยผ่าน → zip ขาดไฟล์ใหม่ทั้งที่ manifest/sha256 ออกมาสวยงาม
    (โปรแกรม import ไม่เจอหลังอัปเดต) — ต้องใส่ไฟล์ใหม่ลง zip จริงและตรวจเหมือนไฟล์อื่น
  • verify เดิมดาวน์โหลด zip ตาม URL ใน manifest 'ในเครื่อง' มาเทียบ → บอก ✓ ได้ทั้งที่ manifest ออนไลน์
    ยังเป็นรุ่นเก่า หรือชี้ URL/sha256 ผิด — ต้องเทียบ manifest ออนไลน์ทุกช่องและ zip ที่มันชี้
"""
import hashlib
import io
import json
import shutil
import sys
import tempfile
import types
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pkg  # noqa: E402
import release  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="crimes_tools_"))
PKG = pkg.PKG
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


# แพ็กเกจจำลองขั้นต่ำที่ผ่านด่านตรวจ 'ฟังก์ชันแกน' ของ release.py
FILES = {
    f"{PKG}/app/VERSION": "1.0.0",
    f"{PKG}/app/frontend/index.html": "<script>" + "\n".join(f"{fn}(){{}}" for fn in release.CORE_HTML) + "</script>",
    f"{PKG}/app/backend/engine.py": "\n".join(f"{fn}(): pass" for fn in release.CORE_ENGINE) + "\n",
    f"{PKG}/app/backend/worker.py": "\n".join(
        (f"{fn}: pass" if fn.startswith("class") else f"{fn}(): pass") for fn in release.CORE_WORKER) + "\n",
    f"{PKG}/app/backend/server.py": "ROUTES = " + repr(list(release.CORE_SERVER)) + "\ndef _job_progress(): pass\n",
}


def make_repo():
    zp = TMP / f"{PKG}_v1.0.0.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in FILES.items():
            z.writestr(name, text)
    mf = {"version": "1.0.0", "url": release.RAW_BASE + zp.name,
          "sha256": hashlib.sha256(zp.read_bytes()).hexdigest(), "open": False, "notes": "เวอร์ชัน 1.0.0"}
    (TMP / "update-manifest.json").write_text(json.dumps(mf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (TMP / "CHANGELOG.md").write_text("# บันทึกการเปลี่ยนแปลง\n", encoding="utf-8")
    with zipfile.ZipFile(zp) as z:
        z.extractall(TMP / "build")
    # ชี้เครื่องมือมาที่รีโปจำลอง (release.py ใช้ค่าคงที่ระดับโมดูล · load_manifest อ่าน pkg.MANIFEST)
    release.ROOT = TMP
    release.MANIFEST = pkg.MANIFEST = TMP / "update-manifest.json"
    release.CHANGELOG = TMP / "CHANGELOG.md"


def build(version, allow=False):
    args = types.SimpleNamespace(version=version, notes=f"เวอร์ชัน {version} — ทดสอบ", open=False,
                                 overwrite=False, allow_new_files=allow)
    try:
        release.cmd_build(args)
        return "ok"
    except SystemExit as e:
        return f"exit: {e}"
    except AssertionError as e:
        return f"assert: {e}"


def serve(mapping):
    """แทน urllib.request.urlopen — ตอบตาม 'ท้าย URL' ที่กำหนด (ไม่มีเครือข่ายจริง)"""
    def fake(url, timeout=None):
        for suffix, body in mapping.items():
            if url.endswith(suffix):
                return io.BytesIO(body)
        raise AssertionError("URL ที่ไม่คาดคิด: " + url)
    return fake


def verify_with(live_manifest, zips):
    mapping = {"update-manifest.json": json.dumps(live_manifest).encode("utf-8")}
    mapping.update(zips)
    real = urllib.request.urlopen
    urllib.request.urlopen = serve(mapping)
    try:
        return release.cmd_verify(None)
    finally:
        urllib.request.urlopen = real


def main():
    make_repo()
    app = TMP / "build" / PKG / "app"

    print("── build: ไฟล์ใหม่ ──")
    (app / "backend" / "newmod.py").write_text("X = 1\n", encoding="utf-8")
    res = build("1.0.1")
    check("มีไฟล์ใหม่แต่ไม่สั่ง --allow-new-files → หยุด และไม่ทิ้ง zip ครึ่ง ๆ",
          res.startswith("exit") and "newmod.py" in res and not (TMP / f"{PKG}_v1.0.1.zip").exists(), res)
    res = build("1.0.1", allow=True)
    out = TMP / f"{PKG}_v1.0.1.zip"
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        newmod = z.read(f"{PKG}/app/backend/newmod.py").decode() if f"{PKG}/app/backend/newmod.py" in names else ""
    check("--allow-new-files → ไฟล์ใหม่อยู่ใน zip จริง", res == "ok" and newmod == "X = 1\n", f"{res} {names}")
    check("ไฟล์เดิมยังครบทุกรายการ", all(n in names for n in FILES))
    mf = json.loads((TMP / "update-manifest.json").read_text(encoding="utf-8"))
    check("manifest ชี้รุ่นใหม่และ sha256 ตรงกับ zip ที่มีไฟล์ใหม่",
          mf["version"] == "1.0.1" and mf["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest())
    check("CHANGELOG ได้รายการรุ่นใหม่", "1.0.1" in (TMP / "CHANGELOG.md").read_text(encoding="utf-8"))

    print("\n── build: ไฟล์ต้องห้าม ──")
    bad = app / "hub_gas.js"
    bad.write_text("// secret", encoding="utf-8")
    res = build("1.0.2", allow=True)
    check("ไฟล์ผู้ดูแลหลุดเข้า build/ → ด่านตรวจไม่ให้ผ่านแม้สั่ง --allow-new-files",
          res.startswith("assert") and "ต้องห้าม" in res, res)
    # ต้องไม่ทิ้ง zip ที่มีไฟล์ลับไว้ในรีโป (git add -A จะกวาดขึ้นไป) และไม่ทิ้งไฟล์ชั่วคราว
    leftovers = [p.name for p in TMP.iterdir() if p.name.endswith(".zip") or p.name.endswith(".part")]
    check("build ที่ไม่ผ่านด่านตรวจ ไม่ทิ้ง zip/ไฟล์ชั่วคราวไว้",
          f"{PKG}_v1.0.2.zip" not in leftovers and not any(n.endswith(".part") for n in leftovers), str(leftovers))
    bad.unlink()
    check("manifest ยังชี้รุ่นเดิม (1.0.1) เมื่อ build ไม่ผ่าน",
          json.loads((TMP / "update-manifest.json").read_text(encoding="utf-8"))["version"] == "1.0.1")

    print("\n── verify: เทียบของออนไลน์จริง ──")
    mf = json.loads((TMP / "update-manifest.json").read_text(encoding="utf-8"))
    old_zip = TMP / f"{PKG}_v1.0.0.zip"
    zips = {out.name: out.read_bytes(), old_zip.name: old_zip.read_bytes()}
    check("ออนไลน์ตรงกับในเครื่องทุกช่อง → ผ่าน", verify_with(mf, zips) == 0)
    stale = {"version": "1.0.0", "url": release.RAW_BASE + old_zip.name,
             "sha256": hashlib.sha256(old_zip.read_bytes()).hexdigest(), "open": False, "notes": "เก่า"}
    check("manifest ออนไลน์ยังเป็นรุ่นเก่า (แม้ zip ใหม่ดาวน์โหลดได้) → ไม่ผ่าน", verify_with(stale, zips) == 1)
    wrong = dict(mf, sha256="0" * 64)
    check("manifest ออนไลน์ประกาศ sha256 ผิด → ไม่ผ่าน", verify_with(wrong, zips) == 1)
    tampered = dict(zips)
    tampered[out.name] = b"not the same bytes"
    check("zip ออนไลน์ถูกแก้ (sha ไม่ตรงที่ประกาศ) → ไม่ผ่าน", verify_with(mf, tampered) == 1)

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(code)
