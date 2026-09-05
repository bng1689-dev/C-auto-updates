#!/usr/bin/env python3
"""CRIMES AUTO — เครื่องมือออก KEY อนุญาตอัปเดต (สำหรับผู้ดูแลระบบเท่านั้น)

*** ห้ามนำไฟล์นี้และไฟล์กุญแจลับ ใส่ลงในชุดอัปเดตที่แจกจ่าย ***
ถ้ากุญแจลับหลุด ใครก็ออก KEY เองได้ และระบบอนุญาตอัปเดตจะหมดความหมายทันที

ใช้ Python มาตรฐานล้วน ไม่ต้องติดตั้งอะไรเพิ่ม (เหมือนตัวโปรแกรม)

วิธีใช้
───────
1) สร้างกุญแจครั้งแรก (ทำครั้งเดียว เก็บไฟล์ที่ได้ให้ดี):

       python tools/keygen.py init

   จะได้ไฟล์ crimes_license_private.json (กุญแจลับ — เก็บเป็นความลับ ห้ามส่งต่อ)
   และพิมพ์ "กุญแจสาธารณะ" ออกมา ให้นำไปวางในโปรแกรมที่
   Setting → KEY อนุญาตอัปเดต → กุญแจสาธารณะ  แล้วกดบันทึก

2) ออก KEY ให้สมาชิกรายคน:

       python tools/keygen.py issue --user somchai
       python tools/keygen.py issue --user somchai --install-id 3f9a2b...  --days 365

   ผู้ขอต้องแจ้ง "ชื่อผู้ใช้" และ (ถ้าจะผูกเครื่อง) "รหัสติดตั้ง" ซึ่งดูได้ที่
   Setting → KEY อนุญาตอัปเดต ในเครื่องของเขา

3) ตรวจ KEY ที่ออกไปแล้ว:

       python tools/keygen.py check --key "v1.xxx.yyy" --user somchai
"""
import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

# สูตรประกอบข้อความและตรวจลายเซ็นต้องตรงกับ backend/license.py เป๊ะ ๆ
# (สำเนาไว้ในไฟล์นี้เพราะเครื่องมือนี้ต้องรันแยกจากตัวโปรแกรมได้)
import base64
import binascii
import hashlib
import hmac

_SHA256_DER = binascii.unhexlify("3031300d060960864801650304020105000420")
PRIV_FILE = Path("crimes_license_private.json")


def b64url(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def emsa_pkcs1_v15(msg, emlen):
    t = _SHA256_DER + hashlib.sha256(msg).digest()
    if emlen < len(t) + 11:
        raise ValueError("กุญแจสั้นเกินไป")
    return b"\x00\x01" + b"\xff" * (emlen - len(t) - 3) + b"\x00" + t


def rsa_verify(n, e, msg, sig):
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    try:
        em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
        return hmac.compare_digest(em, emsa_pkcs1_v15(msg, k))
    except (ValueError, OverflowError):
        return False


# ──────────────── สร้างกุญแจ ────────────────

def _is_probable_prime(n, rounds=48):
    """Miller-Rabin — rounds สูงเพราะทำครั้งเดียวตอนสร้างกุญแจ ไม่ใช่เส้นทางที่ใช้บ่อย"""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits):
    while True:
        cand = secrets.randbits(bits) | (1 << (bits - 1)) | 1   # บังคับบิตบนสุดและเป็นเลขคี่
        if _is_probable_prime(cand):
            return cand


def cmd_init(args):
    if PRIV_FILE.exists() and not args.force:
        print(f"มีไฟล์ {PRIV_FILE} อยู่แล้ว — ใช้ --force ถ้าต้องการสร้างทับ")
        print("คำเตือน: สร้างทับแล้ว KEY ทุกใบที่ออกไปก่อนหน้าจะใช้ไม่ได้ทันที")
        return 1
    bits = args.bits
    print(f"กำลังสร้างกุญแจ RSA {bits} บิต (ใช้เวลาสักครู่)...")
    e = 65537
    while True:
        p = _gen_prime(bits // 2)
        q = _gen_prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        d = pow(e, -1, phi)
        break
    PRIV_FILE.write_text(json.dumps({"n": str(n), "e": e, "d": str(d)}, indent=2), encoding="utf-8")
    try:
        PRIV_FILE.chmod(0o600)
    except OSError:
        pass
    print(f"\n✓ บันทึกกุญแจลับไว้ที่ {PRIV_FILE.resolve()}")
    print("  *** เก็บไฟล์นี้เป็นความลับ ห้ามส่งต่อ ห้าม commit ขึ้น git ***\n")
    print("นำ 'กุญแจสาธารณะ' ข้างล่างนี้ไปวางในโปรแกรม:")
    print("  Setting → KEY อนุญาตอัปเดต → กุญแจสาธารณะ\n")
    print(json.dumps({"n": str(n), "e": e}, indent=2))
    return 0


def _load_priv():
    if not PRIV_FILE.exists():
        print(f"ไม่พบ {PRIV_FILE} — รัน 'python tools/keygen.py init' ก่อน")
        sys.exit(1)
    k = json.loads(PRIV_FILE.read_text(encoding="utf-8"))
    return int(k["n"]), int(k["e"]), int(k["d"])


def cmd_issue(args):
    n, e, d = _load_priv()
    payload = {"u": args.user}
    if args.install_id:
        payload["m"] = args.install_id
    if args.days:
        payload["exp"] = (datetime.now() + timedelta(days=args.days)).isoformat(timespec="seconds")
    if args.note:
        payload["note"] = args.note
    payload["iat"] = datetime.now().isoformat(timespec="seconds")

    payload_b64 = b64url(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8"))
    k = (n.bit_length() + 7) // 8
    em = emsa_pkcs1_v15(payload_b64.encode("ascii"), k)
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
    key = f"v1.{payload_b64}.{b64url(sig)}"

    assert rsa_verify(n, e, payload_b64.encode("ascii"), sig), "ตรวจย้อนกลับไม่ผ่าน"

    print("ออก KEY สำเร็จ")
    print(f"  ผู้ใช้      : {args.user}")
    print(f"  ผูกเครื่อง  : {args.install_id or '(ไม่ผูก — ใช้ได้ทุกเครื่องของผู้ใช้คนนี้)'}")
    print(f"  หมดอายุ     : {payload.get('exp', '(ไม่มีวันหมดอายุ)')}")
    print("\nคัดลอกบรรทัดล่างนี้ให้ผู้ใช้ ไปวางที่ Setting → KEY อนุญาตอัปเดต:\n")
    print(key)
    if args.out:
        Path(args.out).write_text(key + "\n", encoding="utf-8")
        print(f"\n(บันทึกลงไฟล์ {args.out} ด้วยแล้ว)")
    return 0


def cmd_check(args):
    n, e, _d = _load_priv()
    s = "".join(args.key.split())
    if not s.startswith("v1."):
        print("✕ รูปแบบ KEY ไม่ถูกต้อง")
        return 1
    parts = s[3:].split(".")
    if len(parts) != 2:
        print("✕ รูปแบบ KEY ไม่ถูกต้อง")
        return 1
    pad = "=" * (-len(parts[0]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(parts[0] + pad).decode("utf-8"))
    pad = "=" * (-len(parts[1]) % 4)
    sig = base64.urlsafe_b64decode(parts[1] + pad)
    ok = rsa_verify(n, e, parts[0].encode("ascii"), sig)
    print(("✓ ลายเซ็นถูกต้อง" if ok else "✕ ลายเซ็นไม่ถูกต้อง"))
    print("payload:", json.dumps(payload, ensure_ascii=False, indent=2))
    if args.user and payload.get("u") != args.user:
        print(f"✕ KEY นี้ออกให้ '{payload.get('u')}' ไม่ใช่ '{args.user}'")
        return 1
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="ออก KEY อนุญาตอัปเดตของ CRIMES AUTO")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="สร้างกุญแจลับ/สาธารณะครั้งแรก")
    p.add_argument("--bits", type=int, default=2048)
    p.add_argument("--force", action="store_true", help="สร้างทับของเดิม (KEY เก่าจะใช้ไม่ได้)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("issue", help="ออก KEY ให้ผู้ใช้หนึ่งคน")
    p.add_argument("--user", required=True, help="ชื่อผู้ใช้ในโปรแกรม")
    p.add_argument("--install-id", default="", help="รหัสติดตั้งของเครื่องนั้น (ถ้าจะผูกเครื่อง)")
    p.add_argument("--days", type=int, default=0, help="อายุ KEY เป็นวัน (0 = ไม่หมดอายุ)")
    p.add_argument("--note", default="", help="หมายเหตุ")
    p.add_argument("--out", default="", help="บันทึก KEY ลงไฟล์ด้วย")
    p.set_defaults(func=cmd_issue)

    p = sub.add_parser("check", help="ตรวจ KEY ที่ออกไปแล้ว")
    p.add_argument("--key", required=True)
    p.add_argument("--user", default="")
    p.set_defaults(func=cmd_check)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
