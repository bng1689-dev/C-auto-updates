#!/usr/bin/env python3
"""สร้างชุดติดตั้งตัวเต็มของ CRIMES AUTO สำหรับ Windows 64-bit — อัตโนมัติทั้งชุด ไม่ต้องมีเครื่อง Windows ตอนสร้าง

    python tools/build_installer.py                 # ใช้แพ็กเกจรุ่นล่าสุดตาม update-manifest.json
    python tools/build_installer.py --skip-browsers  # ไม่ดาวน์โหลด Chromium (ทดสอบโครงสร้างเร็ว ๆ)

ผลลัพธ์: dist/CRIMES_AUTO_Setup_v<ver>/ + dist/CRIMES_AUTO_Setup_v<ver>.zip (+ .sha256)
    app/         โปรแกรมรุ่นล่าสุด (จาก zip อัปเดต · ตัดไฟล์ใน app/OBSOLETE.txt และ __pycache__ ออก)
    runtime/     Python embeddable + ไลบรารีทั้งหมด (wheels สำหรับ win_amd64 แตกลง Lib\\site-packages)
    browsers/    Chromium สำหรับ Windows ที่ Playwright รุ่นเดียวกับใน runtime ใช้ (ดาวน์โหลดด้วยตัว Playwright เอง)
    Install.ps1 · ติดตั้ง.bat · Uninstall.ps1 · ถอนการติดตั้ง.bat · icon.ico · install.json · seed_account.json · README

รหัสที่ต้องให้ตอนสร้าง (ไม่เก็บในรีโป — ใส่ทาง environment variable หรือพิมพ์ตอนถาม):
    CRIMES_INSTALL_PASSWORD   รหัสเริ่มติดตั้ง  → เก็บเป็นแฮช PBKDF2-SHA256 ใน install.json (Install.ps1 ตรวจ)
    CRIMES_SEED_PASSWORD      รหัสผ่านบัญชี Super Admin เริ่มต้น → เก็บเป็นแฮช pbkdf2 แบบเดียวกับโปรแกรม ใน seed_account.json
ในชุดติดตั้งและในรีโปจึงไม่มีรหัสจริงอยู่ที่ไหนเลย · ตัวตรวจท้ายสุดจะกวาดไฟล์ทั้งชุดเพื่อยืนยันอีกครั้ง

รุ่นของ Python/Playwright/ชื่อบัญชีเริ่มต้น อยู่ใน tools/installer/versions.json
"""
import argparse
import getpass
import hashlib
import importlib.metadata
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pkg import ROOT, PKG, latest_zip  # noqa: E402

HERE = Path(__file__).resolve().parent
TPL = HERE / "installer"
VERSIONS = json.loads((TPL / "versions.json").read_text(encoding="utf-8"))
ENV_GATE = "CRIMES_INSTALL_PASSWORD"
ENV_SEED = "CRIMES_SEED_PASSWORD"
ENV_HUB = "CRIMES_HUB_TOKEN"          # v3.10.0 (ไม่บังคับ): HUB_TOKEN ของศูนย์กลาง → hub_seed.json ให้เครื่องใหม่เชื่อมเอง
PRODUCT = "CRIMES AUTO"
PY_EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
# ไฟล์ที่ห้ามหลุดเข้าชุดติดตั้งเด็ดขาด (สคริปต์ศูนย์กลาง/เครื่องมือผู้ดูแล/กุญแจ)
FORBIDDEN_SECRETS = ("hub_gas", "keygen", "crimes_license_private")
FORBIDDEN = FORBIDDEN_SECRETS + (".key", "/tools/", "__pycache__", ".pyc")
SEED_FILE = "seed_account.json"
HUB_SEED_FILE = "hub_seed.json"
INSTALL_JSON = "install.json"


def log(msg=""):
    print(msg, flush=True)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ──────────────── ดาวน์โหลด (แคชใน dist/.cache · ทดสอบ monkeypatch ได้) ────────────────
def fetch(url, dest):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        log(f"  · ใช้ไฟล์ที่ดาวน์โหลดไว้แล้ว: {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log(f"  · ดาวน์โหลด {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "CRIMES-AUTO-build"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, 0.0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and time.time() - last > 3:
                log(f"    {got * 100 // total:3d}% ของ {total / 1e6:,.0f} MB")
                last = time.time()
    tmp.replace(dest)
    return dest


def pip_download(args, cwd=None):
    """เรียก pip ของ Python ที่รันสคริปต์นี้ — คืน (returncode, output)"""
    cmd = [sys.executable, "-m", "pip", "download", "--disable-pip-version-check", "-q"] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.returncode, (r.stdout + r.stderr)


def run_playwright_install(browsers_dir):
    """ให้ Playwright (รุ่นเดียวกับที่ใส่ใน runtime) ดาวน์โหลด Chromium สำหรับ Windows ด้วยตัวเอง —
    ได้โครงสร้างโฟลเดอร์/ไฟล์ INSTALLATION_COMPLETE ตรงตามที่มันจะหาบนเครื่องผู้ใช้ทุกประการ
    (บนเครื่องที่ไม่ใช่ Windows ใช้ PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=win64 · ไม่เอา headless shell — โปรแกรมเปิดแบบมีหน้าต่างเสมอ)"""
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(browsers_dir), PLAYWRIGHT_HOST_PLATFORM_OVERRIDE="win64")
    cmd = [sys.executable, "-m", "playwright", "install", "chromium", "--no-shell"]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ดาวน์โหลด Chromium ไม่สำเร็จ:\n" + (r.stdout + r.stderr)[-1500:])
    return r.stdout


# ──────────────── รหัสผ่าน → แฮช (ไม่มีรหัสจริงออกจากฟังก์ชันนี้) ────────────────
def app_pbkdf2_iterations(app_dir):
    """อ่าน _ITERATIONS จาก db.py ของแพ็กเกจ — แฮชบัญชีเริ่มต้นต้องคำนวณด้วยรอบเดียวกับที่โปรแกรมใช้ตรวจ"""
    src = (Path(app_dir) / "backend" / "db.py").read_text(encoding="utf-8")
    m = re.search(r"^_ITERATIONS\s*=\s*([\d_]+)", src, re.M)
    if not m:
        sys.exit("หา _ITERATIONS ใน backend/db.py ไม่พบ")
    return int(m.group(1).replace("_", ""))


def pbkdf2_hex(password, salt_hex, iterations):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()


def get_secret(env_name, prompt, file_path=None):
    """รหัสจาก env → ไฟล์ (--*-file) → พิมพ์ตอนถาม (ถ้ามีคอนโซล) · ไม่พบ = หยุดพร้อมบอกวิธี"""
    val = os.environ.get(env_name, "")
    if not val and file_path:
        val = Path(file_path).read_text(encoding="utf-8").strip()
    if not val and sys.stdin.isatty():
        val = getpass.getpass(prompt + ": ")
    val = val.strip()
    if len(val) < 6:
        sys.exit(f"ต้องระบุ {env_name} (อย่างน้อย 6 ตัว) ทาง environment variable หรือพิมพ์ตอนถาม — "
                 "ห้ามเขียนรหัสลงไฟล์ในรีโป")
    return val


# ──────────────── ขั้นตอนประกอบชุด ────────────────
def stage_app(zip_path, dist, version):
    """app/ จากแพ็กเกจอัปเดตรุ่นล่าสุด — ตัดไฟล์ที่เลิกใช้ (app/OBSOLETE.txt) และแคชออก"""
    app = dist / "app"
    if app.exists():
        shutil.rmtree(app)
    prefix = f"{PKG}/app/"
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        obsolete = set()
        if prefix + "OBSOLETE.txt" in names:
            for line in z.read(prefix + "OBSOLETE.txt").decode("utf-8").splitlines():
                line = line.strip().replace("\\", "/")
                if line and not line.startswith("#"):
                    obsolete.add(line)
        n = 0
        for name in names:
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            rel = name[len(prefix):]
            if "__pycache__" in rel or rel.endswith(".pyc") or rel in obsolete:
                continue
            target = app / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
            n += 1
    got = (app / "VERSION").read_text(encoding="utf-8").strip()
    if got != version:
        sys.exit(f"app/VERSION ในแพ็กเกจ = {got} ไม่ตรงกับ manifest ({version})")
    log(f"  ✓ app/ {n} ไฟล์ (v{got}) · ตัดไฟล์ที่เลิกใช้: {', '.join(sorted(obsolete)) or '-'}")
    return app


def _patch_pth(runtime):
    pth = next(runtime.glob("python*._pth"), None)
    if not pth:
        sys.exit("ไม่พบไฟล์ python*._pth ใน embeddable zip")
    # embeddable มาพร้อม '#import site' และไม่รู้จัก site-packages — ต้องเปิดทั้งสองอย่างให้ไลบรารีที่แตกไว้ถูก import ได้
    keep = []
    for line in pth.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s == "import site":
            continue
        keep.append(s)
    if "Lib\\site-packages" not in keep:
        keep.append("Lib\\site-packages")
    keep.append("import site")
    pth.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return pth


def sdist_to_wheel(sdist_path, out_dir):
    """แปลง sdist ของแพ็กเกจ pure-Python ที่ไม่มี setup.py (เช่น proxy_tools ที่ pywebview ต้องใช้) เป็น wheel แบบง่าย
    — แค่ย้ายโฟลเดอร์แพ็กเกจ + METADATA จาก PKG-INFO · ใช้ได้เพราะไม่มีโค้ดคอมไพล์/ไม่มีสคริปต์"""
    with tarfile.open(sdist_path) as t:
        members = t.getmembers()
        top = members[0].name.split("/")[0]
        pkginfo = t.extractfile(f"{top}/PKG-INFO").read().decode("utf-8", "replace")
        m_name = re.search(r"^Name:\s*(.+)$", pkginfo, re.M)
        m_ver = re.search(r"^Version:\s*(.+)$", pkginfo, re.M)
        name, ver = m_name.group(1).strip(), m_ver.group(1).strip()
        try:
            top_levels = t.extractfile(f"{top}/{name}.egg-info/top_level.txt").read().decode().split()
        except KeyError:
            top_levels = [name.replace("-", "_")]
        wheel_name = f"{name.replace('-', '_')}-{ver}-py3-none-any.whl"
        out = Path(out_dir) / wheel_name
        distinfo = f"{name.replace('-', '_')}-{ver}.dist-info"
        record = []
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
            for m in members:
                parts = m.name.split("/")[1:]
                if not m.isfile() or not parts or parts[0] not in top_levels or parts[-1].endswith(".pyc"):
                    continue
                arc = "/".join(parts)
                w.writestr(arc, t.extractfile(m).read())
                record.append(arc)
            w.writestr(f"{distinfo}/METADATA", pkginfo)
            w.writestr(f"{distinfo}/WHEEL", "Wheel-Version: 1.0\nGenerator: crimes-build-installer\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
            w.writestr(f"{distinfo}/top_level.txt", "\n".join(top_levels) + "\n")
            w.writestr(f"{distinfo}/RECORD", "".join(f"{r},,\n" for r in record + [f"{distinfo}/METADATA", f"{distinfo}/WHEEL"]))
    return out


def download_wheels(requirements, wheels_dir, pyver):
    """wheels ทั้งหมดสำหรับ Windows 64-bit / Python รุ่นที่ใช้ (pip download ข้ามแพลตฟอร์ม · ปักรุ่น playwright)"""
    wheels_dir = Path(wheels_dir)
    wheels_dir.mkdir(parents=True, exist_ok=True)
    pyxy = ".".join(pyver.split(".")[:2])
    constraints = wheels_dir / "constraints.txt"
    constraints.write_text(f"playwright=={VERSIONS['playwright']}\n", encoding="utf-8")
    # แพ็กเกจ pure-Python ที่มีแต่ sdist → ทำ wheel เองก่อน (pip download แบบ --only-binary จะได้เจอใน --find-links)
    for name in VERSIONS.get("pure_sdists", []):
        if list(wheels_dir.glob(f"{name.replace('-', '_')}-*.whl")):
            continue
        tmp = wheels_dir / "_sdist"
        tmp.mkdir(exist_ok=True)
        rc, out = pip_download(["--no-deps", "--no-binary", ":all:", "-d", str(tmp), name])
        if rc:
            sys.exit(f"ดาวน์โหลด sdist ของ {name} ไม่สำเร็จ:\n{out[-800:]}")
        for sd in tmp.glob(f"{name.replace('-', '_')}-*.tar.gz"):
            sdist_to_wheel(sd, wheels_dir)
        shutil.rmtree(tmp, ignore_errors=True)
    rc, out = pip_download(["--platform", "win_amd64", "--python-version", pyxy, "--only-binary=:all:",
                            "--find-links", str(wheels_dir), "-c", str(constraints),
                            "-d", str(wheels_dir), "-r", str(requirements)])
    if rc:
        sys.exit(f"ดาวน์โหลด wheels ไม่สำเร็จ:\n{out[-1500:]}")
    wheels = sorted(wheels_dir.glob("*.whl"))
    if not wheels:
        sys.exit("ไม่ได้ wheel สักไฟล์")
    return wheels


def unpack_wheel(whl, site_packages, runtime):
    """แตก wheel ลง site-packages (เท่ากับ pip install --target แบบไม่มีสคริปต์) — .data/purelib|platlib → site-packages"""
    with zipfile.ZipFile(whl) as z:
        for info in z.infolist():
            if info.is_dir() or "__pycache__" in info.filename:
                continue
            parts = info.filename.split("/")
            dest_root = site_packages
            if len(parts) > 1 and parts[0].endswith(".data"):
                kind = parts[1] if len(parts) > 2 else ""
                if kind in ("purelib", "platlib"):
                    parts = parts[2:]
                elif kind == "scripts":
                    dest_root, parts = runtime / "Scripts", parts[2:]
                else:
                    continue
            target = dest_root.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def stage_runtime(dist, cache, requirements, skip=False):
    """runtime/ = Python embeddable (win64) + ไลบรารีทั้งหมดของโปรแกรม"""
    runtime = dist / "runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    pyver = VERSIONS["python"]
    if skip:
        (runtime / "python.exe").write_bytes(b"")
        (runtime / "pythonw.exe").write_bytes(b"")
        (runtime / "Lib" / "site-packages").mkdir(parents=True)
        log("  ! ข้าม runtime (--skip-runtime) — ชุดนี้ใช้ติดตั้งจริงไม่ได้")
        return runtime, []
    zp = fetch(PY_EMBED_URL.format(v=pyver), cache / f"python-{pyver}-embed-amd64.zip")
    with zipfile.ZipFile(zp) as z:
        z.extractall(runtime)
    _patch_pth(runtime)
    site = runtime / "Lib" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    wheels = download_wheels(requirements, cache / f"wheels-py{pyver}", pyver)
    for w in wheels:
        unpack_wheel(w, site, runtime)
    (runtime / "INSTALLED.txt").write_text(
        f"python-{pyver}-embed-amd64\n" + "".join(w.name + "\n" for w in wheels), encoding="utf-8")
    log(f"  ✓ runtime/ Python {pyver} + {len(wheels)} wheels: " + ", ".join(w.name.split('-')[0] for w in wheels))
    return runtime, wheels


def wheel_browsers_json(wheels):
    """browsers.json ของ playwright wheel ที่ใส่ใน runtime — บอก revision ของ Chromium ที่รุ่นนั้นต้องใช้"""
    for w in wheels:
        if w.name.startswith("playwright-"):
            with zipfile.ZipFile(w) as z:
                return json.loads(z.read("playwright/driver/package/browsers.json"))
    return None


def stage_browsers(dist, wheels, skip=False):
    """browsers/ = Chromium (Windows) ที่ Playwright รุ่นใน runtime ต้องการ — ดาวน์โหลดด้วยตัว Playwright เอง"""
    browsers = dist / "browsers"
    if browsers.exists():
        shutil.rmtree(browsers)
    browsers.mkdir(parents=True)
    want = VERSIONS["playwright"]
    try:
        local = importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        local = ""
    if skip:
        (browsers / "SKIPPED.txt").write_text("--skip-browsers\n", encoding="utf-8")
        log("  ! ข้าม browsers (--skip-browsers) — ชุดนี้ใช้ติดตั้งจริงไม่ได้")
        return browsers, ""
    if local != want:
        sys.exit(f"Playwright ในเครื่องที่ build คือ {local or 'ไม่มี'} แต่ชุดติดตั้งใช้ {want} — รัน: pip install playwright=={want}")
    run_playwright_install(browsers)
    shutil.rmtree(browsers / ".links", ignore_errors=True)
    exe = next(browsers.glob("chromium-*/chrome-win64/chrome.exe"), None)
    if not exe:
        sys.exit("ไม่พบ chrome.exe ใน browsers/ หลังดาวน์โหลด")
    rev = exe.parent.parent.name.split("-", 1)[1]
    bj = wheel_browsers_json(wheels) if wheels else None
    if bj:
        want_rev = next((b["revision"] for b in bj["browsers"] if b["name"] == "chromium"), None)
        if want_rev and str(want_rev) != rev:
            sys.exit(f"Chromium ที่ดาวน์โหลด (rev {rev}) ไม่ตรงกับที่ playwright wheel ต้องใช้ (rev {want_rev})")
    for extra in browsers.glob("chromium_headless_shell-*"):
        shutil.rmtree(extra, ignore_errors=True)       # ไม่ใช้ (โปรแกรมเปิดแบบมีหน้าต่างเสมอ) — ประหยัด ~250 MB
    log(f"  ✓ browsers/ Chromium rev {rev} ({exe.relative_to(browsers)})")
    return browsers, rev


# ──────────────── ไอคอน (PNG ใน ICO — ไม่ต้องใช้ไลบรารีภาพ) ────────────────
def _png(width, height, rows):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _render_icon(size, ss=3):
    """โล่ไล่สี (ฟ้า→ม่วง→ชมพู ตามแบรนด์ในหน้าจอ) + วงแหวนลายนิ้วมือสีขาว · เรนเดอร์ใหญ่แล้วย่อ (ลบรอยหยัก)"""
    big = size * ss
    pal = [(0, 229, 255), (138, 43, 226), (255, 45, 149)]

    def grad(t):
        t = min(max(t, 0.0), 1.0) * 2
        i = 0 if t < 1 else 1
        f = t - i
        a, b = pal[i], pal[i + 1]
        return tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))

    def inside_shield(x, y):      # x,y ใน [0,1]
        if y < 0.12 or y > 0.96:
            return False
        w = 0.40 if y < 0.55 else 0.40 * (1 - ((y - 0.55) / 0.41) ** 1.6)
        return abs(x - 0.5) <= w and (y > 0.16 or abs(x - 0.5) <= 0.40 - (0.16 - y) * 2)

    def ring(x, y, r_in, r_out, cx=0.5, cy=0.5):
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        return r_in <= d <= r_out and not (x > cx and abs(y - cy) < 0.055)   # เว้นช่องด้านขวา = ลายนิ้วมือ

    acc = [[[0, 0, 0, 0] for _ in range(size)] for _ in range(size)]
    for py in range(big):
        y = (py + 0.5) / big
        for px in range(big):
            x = (px + 0.5) / big
            if not inside_shield(x, y):
                continue
            col = grad((y - 0.12) / 0.84)
            a = 255
            edge = 0.40 - abs(x - 0.5)
            if edge < 0.03 or y > 0.90:
                col = tuple(int(c * 0.75) for c in col)
            if ring(x, y, 0.27, 0.32) or ring(x, y, 0.17, 0.215) or ((x - 0.5) ** 2 + (y - 0.5) ** 2) ** 0.5 < 0.09:
                col = (255, 255, 255)
            cell = acc[py // ss][px // ss]
            cell[0] += col[0]; cell[1] += col[1]; cell[2] += col[2]; cell[3] += a
    rows = []
    n = ss * ss
    for row in acc:
        out = bytearray()
        for r, g, b, a in row:
            if a == 0:
                out += b"\x00\x00\x00\x00"
            else:
                cov = a // 255
                out += bytes((r // cov, g // cov, b // cov, a // n))
        rows.append(out)
    return _png(size, size, rows)


def write_icon(path, sizes=(256, 48, 32, 16)):
    images = [(s, _render_icon(s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for s, png in images:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    Path(path).write_bytes(header + entries + blobs)


# ──────────────── ไฟล์ประกอบ + ตรวจท้ายสุด ────────────────
def copy_templates(dist):
    """สคริปต์ติดตั้ง/ถอน (UTF-8 พร้อม BOM — PowerShell 5.1 ถึงอ่านภาษาไทยถูก) + .bat ทั้งชื่อไทยและอังกฤษ"""
    for ps in ("Install.ps1", "Uninstall.ps1"):
        text = (TPL / ps).read_text(encoding="utf-8-sig")
        (dist / ps).write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    for th, en in (("ติดตั้ง.bat", "Install.bat"), ("ถอนการติดตั้ง.bat", "Uninstall.bat")):
        text = (TPL / th).read_text(encoding="utf-8").replace("\n", "\r\n")
        (dist / th).write_text(text, encoding="utf-8", newline="")
        (dist / en).write_text(text, encoding="utf-8", newline="")
    (dist / "README-ติดตั้ง.txt").write_bytes(
        b"\xef\xbb\xbf" + (TPL / "README-ติดตั้ง.txt").read_text(encoding="utf-8-sig").replace("\n", "\r\n").encode("utf-8"))


def write_meta(dist, version, gate_pw, seed_pw, app_iter, pyver, chromium_rev, hub_token=""):
    gate_salt = secrets.token_hex(16)
    seed_salt = secrets.token_hex(16)
    meta = {
        "product": PRODUCT, "version": version, "built_at": datetime.now().isoformat(timespec="seconds"),
        "python": pyver, "playwright": VERSIONS["playwright"], "chromium_revision": chromium_rev,
        "install_dir": "%LOCALAPPDATA%\\CRIMES-AUTO",
        "gate": {"algo": "pbkdf2_sha256", "iterations": int(VERSIONS["gate_iterations"]), "salt": gate_salt,
                 "hash": pbkdf2_hex(gate_pw, gate_salt, int(VERSIONS["gate_iterations"]))},
        "seed_username": VERSIONS["seed_username"],
    }
    (dist / INSTALL_JSON).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    seed = {
        "username": VERSIONS["seed_username"], "display_name": VERSIONS.get("seed_display_name", VERSIONS["seed_username"]),
        "password_hash": pbkdf2_hex(seed_pw, seed_salt, app_iter), "salt": seed_salt, "iterations": app_iter,
        "note": "บัญชี Super Admin เริ่มต้นจากชุดติดตั้ง — โปรแกรมใช้ไฟล์นี้ตอนเปิดครั้งแรกที่ยังไม่มีผู้ใช้ แล้วลบทิ้งทันที",
    }
    (dist / SEED_FILE).write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if hub_token:
        # v3.10.0: รหัสลับศูนย์กลาง (HUB_TOKEN) — เท่ากับรหัสเชื่อมต่อที่แจกสมาชิกอยู่แล้ว (ไม่ใช่ ADMIN_TOKEN) · URL ใช้ที่ฝังในโปรแกรม
        # โปรแกรมอ่านตอนเปิดครั้งแรกแล้วลบไฟล์ทันที · ชุดติดตั้งที่มีไฟล์นี้ต้องแจกเฉพาะคนในหน่วยงาน
        (dist / HUB_SEED_FILE).write_text(json.dumps({"token": hub_token,
            "note": "รหัสลับศูนย์กลางจากชุดติดตั้ง — โปรแกรมใช้ตอนเปิดครั้งแรกแล้วลบทิ้ง"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        meta["hub_seed"] = True
        (dist / INSTALL_JSON).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def self_check(dist, version, secrets_plain, full):
    """ด่านตรวจก่อนปล่อย: ไฟล์ครบ · ไม่มีไฟล์ต้องห้าม · ไม่มีรหัสจริงเป็นข้อความธรรมดาในไฟล์ใดของชุด"""
    problems = []
    need = ["app/VERSION", "app/desktop.py", "app/backend/server.py", "app/backend/db.py", "app/frontend/index.html",
            "Install.ps1", "Uninstall.ps1", "ติดตั้ง.bat", "ถอนการติดตั้ง.bat", "Install.bat", "Uninstall.bat",
            "icon.ico", INSTALL_JSON, SEED_FILE, "README-ติดตั้ง.txt", "runtime/python.exe", "runtime/pythonw.exe"]
    if full:
        need += ["runtime/Lib/site-packages/flask/__init__.py", "runtime/Lib/site-packages/waitress/__init__.py",
                 "runtime/Lib/site-packages/webview/__init__.py", "runtime/Lib/site-packages/playwright/__init__.py",
                 "runtime/Lib/site-packages/playwright/driver/node.exe", "runtime/Lib/site-packages/openpyxl/__init__.py",
                 "runtime/Lib/site-packages/pythonnet/__init__.py", "runtime/Lib/site-packages/proxy_tools/__init__.py"]
    for rel in need:
        if not (dist / rel).exists():
            problems.append(f"ไม่พบ {rel}")
    if full and not list(dist.glob("browsers/chromium-*/chrome-win64/chrome.exe")):
        problems.append("ไม่พบ browsers/chromium-*/chrome-win64/chrome.exe")
    if (dist / "app" / "VERSION").exists() and (dist / "app" / "VERSION").read_text(encoding="utf-8").strip() != version:
        problems.append("app/VERSION ไม่ตรงรุ่น")
    for p in dist.rglob("*"):
        rel = "/" + p.relative_to(dist).as_posix()
        third_party = p.relative_to(dist).parts[0] in ("runtime", "browsers")   # ไลบรารี/เบราว์เซอร์มีโฟลเดอร์ tools/ ของตัวเอง
        rules = FORBIDDEN_SECRETS if third_party else FORBIDDEN
        if any(f in rel for f in rules):
            problems.append(f"ไฟล์ต้องห้าม: {rel}")
    if (dist / "app" / "backend" / "licensekey.py").exists():
        problems.append("app/backend/licensekey.py ยังอยู่ (ต้องถูกตัดออกตาม OBSOLETE.txt)")
    for ps in ("Install.ps1", "Uninstall.ps1"):
        if not (dist / ps).read_bytes().startswith(b"\xef\xbb\xbf"):
            problems.append(f"{ps} ไม่มี BOM (PowerShell 5.1 จะอ่านภาษาไทยเพี้ยน)")
    # กวาดหารหัสจริง — ทุกไฟล์ที่ไม่ใช่ไบนารีขนาดใหญ่ (ไม่รวมตัว Chromium/Python เอง)
    # (ชื่อ, needle) — ชื่อบอกว่ารหัสไหนหลุด และให้ยกเว้นรายรหัสได้ (hub token ฝังใน config.py โดยตั้งใจ)
    needles = [(name, s.encode("utf-8")) for name, s in zip(("gate", "seed", "hub"), secrets_plain) if s]
    for p in dist.rglob("*"):
        if not p.is_file() or p.stat().st_size > 5_000_000:
            continue
        top = p.relative_to(dist).parts[0]
        if top in ("browsers",) or (top == "runtime" and p.suffix.lower() in (".dll", ".pyd", ".exe", ".zip", ".node")):
            continue
        if p.name == HUB_SEED_FILE:
            continue                                # รหัสลับศูนย์กลางอยู่ในไฟล์นี้โดยตั้งใจ (เท่ากับรหัสเชื่อมต่อ) — ห้ามอยู่ที่อื่น
        data = p.read_bytes()
        for name, nd in needles:
            if nd in data:
                # v3.10.0: เจ้าของโปรเจกต์สั่ง "ฝัง HUB_TOKEN" ใน app/backend/config.py — ผู้ดูแลที่ตั้ง
                # CRIMES_HUB_TOKEN เป็นรหัสเดียวกับที่ฝังต้องไม่ถูกตีตก (รหัสอื่นหลุดที่ไหนก็ตีตกเหมือนเดิม)
                if name == "hub" and p.relative_to(dist).as_posix() == "app/backend/config.py":
                    continue
                problems.append(f"พบรหัสเป็นข้อความธรรมดาใน {p.relative_to(dist).as_posix()}")
    meta = json.loads((dist / INSTALL_JSON).read_text(encoding="utf-8"))
    seed = json.loads((dist / SEED_FILE).read_text(encoding="utf-8"))
    for label, h in (("install.json gate.hash", meta["gate"]["hash"]), ("seed password_hash", seed["password_hash"])):
        if not re.fullmatch(r"[0-9a-f]{64}", h):
            problems.append(f"{label} ไม่ใช่แฮช sha256 hex")
    if problems:
        sys.exit("ด่านตรวจชุดติดตั้งไม่ผ่าน:\n  - " + "\n  - ".join(problems))
    log("  ✓ ด่านตรวจผ่าน: ไฟล์ครบ · ไม่มีไฟล์ต้องห้าม · ไม่มีรหัสเป็นข้อความธรรมดาในชุด")


def make_zip(dist):
    out = dist.parent / (dist.name + ".zip")        # ไม่ใช้ with_suffix — ชื่อมีจุดของเลขรุ่นอยู่
    if out.exists():
        out.unlink()
    log(f"  · บีบอัด {out.name} …")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(dist.rglob("*")):
            if p.is_file():
                z.write(p, arcname=f"{dist.name}/{p.relative_to(dist).as_posix()}")
    digest = sha256_file(out)
    (dist.parent / (dist.name + ".sha256")).write_text(f"{digest} *{out.name}\n", encoding="utf-8")
    return out, digest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"), help="โฟลเดอร์ผลลัพธ์ (ค่าเริ่มต้น dist/ — ไม่ขึ้น git)")
    ap.add_argument("--skip-browsers", action="store_true", help="ไม่ดาวน์โหลด Chromium (ทดสอบโครงสร้าง)")
    ap.add_argument("--skip-runtime", action="store_true", help="ไม่ดาวน์โหลด Python/wheels (ทดสอบโครงสร้าง)")
    ap.add_argument("--no-zip", action="store_true", help="ไม่บีบอัดเป็น zip")
    ap.add_argument("--gate-password-file", help="อ่านรหัสเริ่มติดตั้งจากไฟล์นอกรีโป (แทน env)")
    ap.add_argument("--seed-password-file", help="อ่านรหัสบัญชีเริ่มต้นจากไฟล์นอกรีโป (แทน env)")
    ap.add_argument("--hub-token-file", help="v3.10.0 (ไม่บังคับ): อ่าน HUB_TOKEN ของศูนย์กลางจากไฟล์นอกรีโป → ฝัง hub_seed.json")
    args = ap.parse_args(argv)

    zip_path, version = latest_zip()
    log(f"CRIMES AUTO — สร้างชุดติดตั้งตัวเต็ม v{version} จาก {zip_path.name}")
    gate_pw = get_secret(ENV_GATE, "รหัสเริ่มติดตั้ง", args.gate_password_file)
    seed_pw = get_secret(ENV_SEED, f"รหัสผ่านบัญชี {VERSIONS['seed_username']} เริ่มต้น", args.seed_password_file)
    hub_token = os.environ.get(ENV_HUB, "").strip()
    if not hub_token and args.hub_token_file:
        hub_token = Path(args.hub_token_file).read_text(encoding="utf-8").strip()
    if hub_token and len(hub_token) < 8:
        sys.exit(f"{ENV_HUB} สั้นเกินไป (อย่างน้อย 8 ตัว)")

    out_root = Path(args.out)
    dist = out_root / f"CRIMES_AUTO_Setup_v{version}"
    cache = out_root / ".cache"
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=True)

    log("① app/")
    app = stage_app(zip_path, dist, version)
    app_iter = app_pbkdf2_iterations(app)
    log("② runtime/")
    runtime, wheels = stage_runtime(dist, cache, app / "requirements.txt", skip=args.skip_runtime)
    log("③ browsers/")
    _browsers, rev = stage_browsers(dist, wheels, skip=args.skip_browsers)
    log("④ สคริปต์ติดตั้ง/ถอน · ไอคอน · ข้อมูลการติดตั้ง")
    copy_templates(dist)
    write_icon(dist / "icon.ico")
    write_meta(dist, version, gate_pw, seed_pw, app_iter, VERSIONS["python"], rev, hub_token=hub_token)
    full = not (args.skip_browsers or args.skip_runtime)
    self_check(dist, version, [gate_pw, seed_pw, hub_token], full)
    log("  · " + ("ฝังรหัสลับศูนย์กลาง (hub_seed.json) — เครื่องใหม่เชื่อมศูนย์กลางเองแล้วกด 'สมัครใช้งาน' ได้เลย" if hub_token
                  else "ไม่ได้ฝังรหัสลับศูนย์กลาง (ตั้ง CRIMES_HUB_TOKEN ถ้าต้องการ) — ผู้สมัครต้องกรอกรหัสเชื่อมต่อครั้งแรก"))
    del gate_pw, seed_pw, hub_token
    size = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    log(f"✓ {dist} ({size / 1e6:,.0f} MB){'' if full else ' — ชุดทดสอบโครงสร้าง ไม่ใช่ชุดติดตั้งจริง'}")
    if not args.no_zip:
        out, digest = make_zip(dist)
        log(f"✓ {out.name} ({out.stat().st_size / 1e6:,.0f} MB) sha256 {digest}")
    log("ถัดไป: ส่ง zip ให้เครื่องปลายทาง → แตก → ดับเบิลคลิก ติดตั้ง.bat → ใส่รหัสเริ่มติดตั้ง")
    return 0


if __name__ == "__main__":
    sys.exit(main())
