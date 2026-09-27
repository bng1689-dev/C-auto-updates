#!/usr/bin/env python3
"""ตัวสร้างชุดติดตั้งตัวเต็ม (tools/build_installer.py) — ทดสอบกับแพ็กเกจจำลอง ไม่แตะเครือข่าย/รีโปจริง

  • โครงสร้างชุดครบ (app/ runtime/ browsers/ สคริปต์ ไอคอน install.json seed_account.json)
  • รหัสเริ่มติดตั้ง/รหัสบัญชีเริ่มต้น: อยู่เป็นแฮชเท่านั้น ตรวจได้จริง (PBKDF2) · ไม่มีข้อความรหัสในไฟล์ใดของชุด
  • ไฟล์ที่เลิกใช้ (OBSOLETE.txt) ไม่ถูกใส่ในชุด · ไฟล์ต้องห้ามไม่หลุด · PowerShell มี BOM · .bat ทั้งชื่อไทย/อังกฤษ
  • ชิ้นส่วน: sdist → wheel · แตก wheel (.data/purelib) · แก้ python._pth · ด่านตรวจจับรหัสที่หลุดเป็นข้อความ
"""
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_installer as bi  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="crimes_installer_"))
PKG = bi.PKG
GATE = "unit-test-gate-pw"        # รหัสทดสอบ — ไม่ใช่รหัสจริง
SEED = "unit-test-seed-pw"
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def make_fake_package():
    files = {
        "app/VERSION": "5.0.0",
        "app/requirements.txt": "flask\nwaitress\npywebview\npythonnet\nplaywright\nopenpyxl\n",
        "app/OBSOLETE.txt": "# เลิกใช้\nbackend/licensekey.py\n",
        "app/desktop.py": "print('desktop')\n",
        "app/frontend/index.html": "<html></html>",
        "app/backend/server.py": "# server\n",
        "app/backend/db.py": "_ITERATIONS = 200_000\n",
        "app/backend/licensekey.py": "# dead\n",
        "app/backend/__pycache__/db.cpython-311.pyc": "junk",
        "Update.ps1": "# updater",
    }
    zp = TMP / f"{PKG}_v5.0.0.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for name, text in files.items():
            z.writestr(f"{PKG}/{name}", text)
    return zp


def fake_wheel(wheels_dir, name, version, entries, tag="py3-none-any"):
    p = wheels_dir / f"{name}-{version}-{tag}.whl"
    with zipfile.ZipFile(p, "w") as z:
        for arc, data in entries.items():
            z.writestr(arc, data)
        z.writestr(f"{name}-{version}.dist-info/METADATA", f"Name: {name}\nVersion: {version}\n")
    return p


def fake_download_wheels(requirements, wheels_dir, pyver):
    wheels_dir = Path(wheels_dir)
    wheels_dir.mkdir(parents=True, exist_ok=True)
    local_pw = importlib.metadata.version("playwright")
    bj = json.dumps({"browsers": [{"name": "chromium", "revision": "1234"}]})
    out = [
        fake_wheel(wheels_dir, "flask", "3.1.0", {"flask/__init__.py": "x"}),
        fake_wheel(wheels_dir, "waitress", "3.0.0", {"waitress/__init__.py": "x"}),
        fake_wheel(wheels_dir, "pywebview", "6.2.1", {"webview/__init__.py": "x"}),
        fake_wheel(wheels_dir, "pythonnet", "3.1.0", {"pythonnet/__init__.py": "x", "pythonnet/runtime/Python.Runtime.dll": "bin"}, "cp311-none-win_amd64"),
        fake_wheel(wheels_dir, "playwright", local_pw, {"playwright/__init__.py": "x", "playwright/driver/node.exe": "bin",
                                                         "playwright/driver/package/browsers.json": bj}, "py3-none-win_amd64"),
        fake_wheel(wheels_dir, "openpyxl", "3.1.5", {"openpyxl/__init__.py": "x"}),
        fake_wheel(wheels_dir, "proxy_tools", "0.1.0", {"proxy_tools/__init__.py": "x"}),
        # แพ็กเกจแบบ .data/purelib + สคริปต์ — ต้องลงถูกที่
        fake_wheel(wheels_dir, "oddpkg", "1.0", {"oddpkg-1.0.data/purelib/oddpkg/__init__.py": "x",
                                                 "oddpkg-1.0.data/scripts/odd.exe": "bin"}),
    ]
    return sorted(out)


def fake_fetch(url, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    assert "python-" in url and "embed-amd64" in url, url
    with zipfile.ZipFile(dest, "w") as z:
        z.writestr("python.exe", "exe")
        z.writestr("pythonw.exe", "exe")
        z.writestr("python311.dll", "dll")
        z.writestr("python311.zip", "zip")
        z.writestr("python311._pth", "python311.zip\n.\n\n# Uncomment to run site.main() automatically\n#import site\n")
    return dest


def fake_playwright_install(browsers_dir):
    d = Path(browsers_dir) / "chromium-1234" / "chrome-win64"
    d.mkdir(parents=True)
    (d / "chrome.exe").write_text("exe")
    (Path(browsers_dir) / "chromium-1234" / "INSTALLATION_COMPLETE").write_text("")
    (Path(browsers_dir) / "chromium_headless_shell-1234").mkdir()
    (Path(browsers_dir) / ".links").mkdir()
    return "ok"


def pbkdf2(pw, salt_hex, it):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), it).hex()


def main():
    zp = make_fake_package()
    bi.latest_zip = lambda: (zp, "5.0.0")
    bi.fetch = fake_fetch
    bi.download_wheels = fake_download_wheels
    bi.run_playwright_install = fake_playwright_install
    bi.VERSIONS = dict(bi.VERSIONS, playwright=importlib.metadata.version("playwright"))
    os.environ[bi.ENV_GATE] = GATE
    os.environ[bi.ENV_SEED] = SEED
    out = TMP / "dist"

    print("── สร้างชุดเต็ม (จำลองการดาวน์โหลด) ──")
    rc = bi.main(["--out", str(out)])
    dist = out / "CRIMES_AUTO_Setup_v5.0.0"
    check("build สำเร็จ", rc == 0 and dist.is_dir())
    check("app/ มาจาก zip · ไม่มี licensekey.py (OBSOLETE) · ไม่มี __pycache__ · ไม่มี Update.ps1 (ไม่ใช่ของชุดเต็ม)",
          (dist / "app" / "backend" / "server.py").exists() and not (dist / "app" / "backend" / "licensekey.py").exists()
          and not list((dist / "app").rglob("__pycache__")) and not (dist / "Update.ps1").exists())
    site = dist / "runtime" / "Lib" / "site-packages"
    check("runtime/: python.exe · pythonw.exe · ไลบรารีแตกลง site-packages · .data/purelib ลงถูกที่ · สคริปต์ไป Scripts",
          (dist / "runtime" / "pythonw.exe").exists() and (site / "flask" / "__init__.py").exists()
          and (site / "playwright" / "driver" / "node.exe").exists() and (site / "oddpkg" / "__init__.py").exists()
          and (dist / "runtime" / "Scripts" / "odd.exe").exists() and not (site / "oddpkg-1.0.data").exists())
    pth = (dist / "runtime" / "python311._pth").read_text(encoding="utf-8").splitlines()
    check("python311._pth เปิด site-packages + import site", pth == ["python311.zip", ".", "Lib\\site-packages", "import site"], str(pth))
    check("browsers/: chromium-1234/chrome-win64/chrome.exe · ไม่มี .links · ไม่มี headless shell",
          (dist / "browsers" / "chromium-1234" / "chrome-win64" / "chrome.exe").exists()
          and not (dist / "browsers" / ".links").exists() and not (dist / "browsers" / "chromium_headless_shell-1234").exists())
    names = {p.name for p in dist.iterdir()}
    check("สคริปต์/ไฟล์ประกอบครบ", {"Install.ps1", "Uninstall.ps1", "ติดตั้ง.bat", "Install.bat", "ถอนการติดตั้ง.bat", "Uninstall.bat",
                                   "icon.ico", "install.json", "seed_account.json", "README-ติดตั้ง.txt"} <= names, str(names))
    check("PowerShell มี BOM + CRLF", (dist / "Install.ps1").read_bytes().startswith(b"\xef\xbb\xbf") and b"\r\n" in (dist / "Uninstall.ps1").read_bytes())
    ico = (dist / "icon.ico").read_bytes()
    check("icon.ico เป็น ICO ที่มี 4 ขนาด และภาพเป็น PNG", ico[:6] == b"\x00\x00\x01\x00\x04\x00" and ico.count(b"\x89PNG") == 4)

    print("\n── รหัส: เก็บเป็นแฮชเท่านั้น ตรวจได้จริง ──")
    meta = json.loads((dist / "install.json").read_text(encoding="utf-8"))
    g = meta["gate"]
    check("install.json: แฮชรหัสเริ่มติดตั้งตรวจกับรหัสจริงได้ · รหัสผิดไม่ผ่าน",
          g["algo"] == "pbkdf2_sha256" and pbkdf2(GATE, g["salt"], g["iterations"]) == g["hash"] and pbkdf2("wrong", g["salt"], g["iterations"]) != g["hash"])
    seed = json.loads((dist / "seed_account.json").read_text(encoding="utf-8"))
    check("seed_account.json: ชื่อผู้ใช้ตาม versions.json · แฮชคำนวณด้วยรอบเดียวกับโปรแกรม (200000)",
          seed["username"] == bi.VERSIONS["seed_username"] and seed["iterations"] == 200000
          and pbkdf2(SEED, seed["salt"], 200000) == seed["password_hash"])
    leaks = []
    for p in dist.rglob("*"):
        if p.is_file():
            data = p.read_bytes()
            if GATE.encode() in data or SEED.encode() in data:
                leaks.append(p.name)
    check("ไม่มีรหัสเป็นข้อความธรรมดาในไฟล์ใดของชุด", leaks == [], str(leaks))
    check("แฮชในชุดไม่ซ้ำกันระหว่างสองรหัส (คนละ salt)", g["hash"] != seed["password_hash"] and g["salt"] != seed["salt"])
    check("ไม่มี zip เมื่อไม่สั่ง (--no-zip ไม่ได้ใช้ → มี zip)", (out / "CRIMES_AUTO_Setup_v5.0.0.zip").exists()
          and (out / "CRIMES_AUTO_Setup_v5.0.0.sha256").read_text().split()[0] == hashlib.sha256((out / "CRIMES_AUTO_Setup_v5.0.0.zip").read_bytes()).hexdigest())
    with zipfile.ZipFile(out / "CRIMES_AUTO_Setup_v5.0.0.zip") as z:
        zn = z.namelist()
    check("zip มีโฟลเดอร์ชั้นบนชื่อชุด และไฟล์ชื่อไทยอยู่ครบ", all(n.startswith("CRIMES_AUTO_Setup_v5.0.0/") for n in zn)
          and "CRIMES_AUTO_Setup_v5.0.0/ติดตั้ง.bat" in zn)

    print("\n── ด่านตรวจ ──")
    (dist / "app" / "notes.txt").write_text("รหัสคือ " + GATE, encoding="utf-8")
    try:
        bi.self_check(dist, "5.0.0", [GATE, SEED], True)
        res = "passed"
    except SystemExit as e:
        res = str(e)
    check("รหัสหลุดเป็นข้อความในไฟล์ใดของชุด → ด่านตรวจไม่ผ่านและบอกไฟล์", "notes.txt" in res, res)
    (dist / "app" / "notes.txt").unlink()
    (dist / "app" / "hub_gas.js").write_text("// secret", encoding="utf-8")
    try:
        bi.self_check(dist, "5.0.0", [GATE, SEED], True)
        res = "passed"
    except SystemExit as e:
        res = str(e)
    check("ไฟล์ต้องห้ามหลุดเข้าชุด → ไม่ผ่าน", "hub_gas" in res, res)
    (dist / "app" / "hub_gas.js").unlink()
    os.environ[bi.ENV_GATE] = "short"
    try:
        bi.main(["--out", str(TMP / "dist2"), "--no-zip", "--skip-browsers", "--skip-runtime"])
        res = "ok"
    except SystemExit as e:
        res = str(e)
    check("รหัสสั้นกว่า 6 ตัว/ไม่ให้รหัส → หยุด ไม่สร้างชุด", bi.ENV_GATE in res and not (TMP / "dist2" / "CRIMES_AUTO_Setup_v5.0.0" / "install.json").exists(), res)
    os.environ[bi.ENV_GATE] = GATE

    print("\n── ชิ้นส่วน ──")
    sd = TMP / "proxy_tools-0.1.0.tar.gz"
    with tarfile.open(sd, "w:gz") as t:
        for name, text in {"proxy_tools-0.1.0/PKG-INFO": "Name: proxy_tools\nVersion: 0.1.0\n",
                           "proxy_tools-0.1.0/proxy_tools/__init__.py": "def proxy(): pass\n",
                           "proxy_tools-0.1.0/proxy_tools.egg-info/top_level.txt": "proxy_tools\n",
                           "proxy_tools-0.1.0/setup.cfg": "x"}.items():
            b = text.encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(b)
            t.addfile(ti, io.BytesIO(b))
    w = bi.sdist_to_wheel(sd, TMP)
    with zipfile.ZipFile(w) as z:
        wn = z.namelist()
    check("sdist ที่ไม่มี setup.py → wheel แบบ pure (แพ็กเกจ + METADATA/WHEEL/RECORD เท่านั้น)",
          w.name == "proxy_tools-0.1.0-py3-none-any.whl" and "proxy_tools/__init__.py" in wn
          and "proxy_tools-0.1.0.dist-info/METADATA" in wn and "setup.cfg" not in wn, str(wn))
    check("ไฟล์ต้นฉบับ Install.ps1/Uninstall.ps1 มีขั้นตอนสำคัญครบ",
          all(k in (bi.TPL / "Install.ps1").read_text(encoding="utf-8-sig") for k in
              ("Rfc2898DeriveBytes", "OBSOLETE.txt", "Uninstall\\CRIMES-AUTO", "seed_account.json", "/MIR", "runtime-ok", "-Silent"))
          and all(k in (bi.TPL / "Uninstall.ps1").read_text(encoding="utf-8-sig") for k in
                  (".crimes_auto_profile", "crimes_upd_", "Uninstall\\CRIMES-AUTO", "Remove-Tree $Install", "KeepData")))
    check("workflow สร้างชุดติดตั้งใช้ secrets ไม่ใช่ค่าคงที่", "secrets.INSTALLER_GATE_PASSWORD" in (ROOT / ".github" / "workflows" / "installer.yml").read_text(encoding="utf-8"))
    check("dist/ อยู่ใน .gitignore", "dist/" in (ROOT / ".gitignore").read_text(encoding="utf-8"))

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TMP, ignore_errors=True)
sys.exit(code)
