#!/usr/bin/env python3
"""สร้าง CHANGELOG.md จากประวัติของ update-manifest.json ใน git (แหล่งความจริงของบันทึกแต่ละรุ่น)

    python tools/changelog.py          # เขียนทับ CHANGELOG.md ทั้งไฟล์จากประวัติ git
    python tools/changelog.py --print  # แสดงอย่างเดียว

ปกติ tools/release.py จะเติมรายการของรุ่นใหม่ให้เองตอน build — สคริปต์นี้ไว้สร้างใหม่ทั้งไฟล์
(เช่นย้อนหลัง หรือถ้าไฟล์เพี้ยน) · รุ่นเดียวกันที่ถูก commit หลายครั้ง ใช้บันทึกจาก commit ล่าสุด
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "CHANGELOG.md"
HEADER = """# บันทึกการเปลี่ยนแปลง — CRIMES AUTO

รุ่นล่าสุดอยู่บนสุด · วันที่คือวันที่ commit ปล่อยรุ่น · 🔓 = รุ่นที่ manifest ประกาศ `open: true`
(ทุกเครื่องอัปเดตได้โดยไม่ต้องได้รับสิทธิ์) · สร้างจากประวัติ `update-manifest.json` ด้วย `tools/changelog.py`
"""


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def split_notes(body):
    """แยกหัวข้อที่คั่นด้วย ' · ' — แต่ไม่แยกตัวคั่นที่อยู่ในวงเล็บ
    เช่น 'รวมทุกอย่างของ v3.5.0 (ก · ข · ค)' ต้องเป็นหัวข้อเดียว"""
    parts, buf, depth = [], "", 0
    i = 0
    while i < len(body):
        ch = body[i]
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if depth == 0 and body.startswith(" · ", i):
            parts.append(buf.strip())
            buf, i = "", i + 3
            continue
        buf += ch
        i += 1
    parts.append(buf.strip())
    return [p for p in parts if p]


def format_entry(version, date, notes, open_flag=False):
    """ข้อความ Markdown ของรุ่นเดียว — แยกบันทึกที่คั่นด้วย ' · ' เป็นรายการ"""
    body = str(notes or "").strip()
    body = re.sub(r"^เวอร์ชัน\s*[\d.]+\s*[—-]\s*", "", body)     # ตัดคำนำหน้า 'เวอร์ชัน x.y.z —'
    parts = split_notes(body)
    lines = [f"## v{version} — {date}" + (" 🔓" if open_flag else ""), ""]
    lines += [f"- {p}" for p in parts] or ["- (ไม่มีบันทึก)"]
    return "\n".join(lines) + "\n"


def history():
    """[(version, date, notes, open)] เรียงจากใหม่ไปเก่า — รุ่นละหนึ่งรายการ"""
    log = subprocess.run(["git", "log", "--format=%h %ad", "--date=short", "--", "update-manifest.json"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    seen, out = set(), []
    for line in log:
        if not line.strip():
            continue
        sha, date = line.split()
        raw = subprocess.run(["git", "show", f"{sha}:update-manifest.json"], cwd=ROOT,
                             capture_output=True, text=True).stdout
        try:
            d = json.loads(raw)
        except Exception:
            continue
        ver = str(d.get("version", "")).strip()
        if not ver or ver in seen:
            continue
        seen.add(ver)
        out.append((ver, date, d.get("notes", ""), bool(d.get("open"))))
    out.sort(key=lambda r: vtuple(r[0]), reverse=True)
    return out


def render():
    return HEADER + "\n" + "\n".join(format_entry(*r[:3], open_flag=r[3]) for r in history())


if __name__ == "__main__":
    text = render()
    if "--print" in sys.argv:
        print(text)
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"เขียน {OUT.name} แล้ว ({text.count(chr(10))} บรรทัด · {len(history())} รุ่น)")
