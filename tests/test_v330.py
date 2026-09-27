#!/usr/bin/env python3
"""v3.3.0 — ทดสอบ backend: ประวัติแยกรายบุคคล · รุ่นที่ manifest ประกาศ open=true
เปิดให้ทุกคนอัปเดตรอบเดียว แล้วรุ่นถัดไปกลับมาบังคับสิทธิ์เอง"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TEST_DATA = Path(tempfile.mkdtemp(prefix="crimes_test_v330_"))
os.environ["CRIMES_DATA_DIR"] = str(TEST_DATA)
os.environ["CRIMES_UPLOAD_DIR"] = str(TEST_DATA / "uploads")
from _app import APP, CHROME  # noqa: E402  (โค้ดแอปจาก build/ = แพ็กเกจรุ่นล่าสุด)
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "backend"))
from backend import db, server  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


MANIFEST = {"version": "99.0.0", "url": "http://x/z.zip", "sha256": "", "notes": ""}


class FakeManifest:
    def __enter__(self):
        return io.BytesIO(json.dumps(MANIFEST).encode())

    def __exit__(self, *a):
        return False


def seed(uid, n, account="a"):
    now = datetime.now()
    with db.get_conn() as c:
        for i in range(n):
            c.execute(
                "INSERT INTO searches(ts,ym,account,file,row,national_id,outcome,"
                "case_count,detail,user_id,id_hash,incomplete,attempt) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now.isoformat(timespec="seconds"), now.strftime("%Y-%m"), account,
                 f"{account}.xlsx", i + 2, "1-23xx-xxxxx-xx-1", "notfound", 0, "",
                 uid, f"u{uid}i{i}", 0, 1))


def main():
    server.app.config["TESTING"] = True
    admin = server.app.test_client()
    m1 = server.app.test_client()      # ในทีมกับแอดมิน + มีสิทธิ์ดูทีม
    m2 = server.app.test_client()      # นอกทีม

    admin.post("/api/setup", json={"username": "admin1", "password": "secret9",
                                   "password2": "secret9", "display_name": "หัวหน้า"})
    admin.post("/api/admin/members", json={"username": "somchai", "password": "pass66",
                                           "display_name": "สมชาย", "role": "member"})
    admin.post("/api/admin/members", json={"username": "wichai", "password": "pass66",
                                           "display_name": "วิชัย", "role": "member"})
    m1.post("/api/login", json={"username": "somchai", "password": "pass66"})
    m2.post("/api/login", json={"username": "wichai", "password": "pass66"})
    users = {u["username"]: u["id"] for u in db.list_users()}
    seed(users["admin1"], 4, "acctA")
    seed(users["somchai"], 3, "acctB")
    seed(users["wichai"], 5, "acctC")

    # ── ประวัติ: ค่าเริ่มต้นต้องเป็น "ของตัวเองเท่านั้น" ──
    r = m2.get("/api/recent").get_json()
    check("สมาชิกเห็นประวัติเฉพาะของตัวเอง (5 แถว)", len(r["searches"]) == 5, str(len(r["searches"])))
    check("ทุกแถวเป็นของตัวเองจริง",
          all(x["user_id"] == users["wichai"] for x in r["searches"]))
    ra = admin.get("/api/recent").get_json()
    check("แอดมินก็เห็นเฉพาะของตัวเองเป็นค่าเริ่มต้น (ไม่กองรวมกันแล้ว)",
          len(ra["searches"]) == 4 and all(x["user_id"] == users["admin1"] for x in ra["searches"]),
          str(len(ra["searches"])))
    check("ทุกแถวติดชื่อเจ้าของมาด้วย", all(x.get("owner") for x in ra["searches"]))

    # ── มุมมองรวม: รวมมาแต่ยังแยกเป็นรายบุคคล ──
    ral = admin.get("/api/recent?uid=all").get_json()
    check("แอดมินเลือก 'ทั้งทีม' → รวมครบ 12 แถว", len(ral["searches"]) == 12, str(len(ral["searches"])))
    owners = {x["owner"] for x in ral["searches"]}
    check("แยกเป็นรายบุคคล: ชื่อครบทั้ง 3 คน",
          owners == {"หัวหน้า", "สมชาย", "วิชัย"}, str(owners))
    check("รายชื่อให้เลือกครบ 3 คน", len(ral["people"]) == 3 and ral["can_all"] is True)

    # ── เลือกดูของคนอื่นเฉพาะเท่าที่มีสิทธิ์ ──
    r = admin.get(f"/api/recent?uid={users['somchai']}").get_json()
    check("แอดมินเลือกดูของสมชายได้", len(r["searches"]) == 3
          and all(x["user_id"] == users["somchai"] for x in r["searches"]))
    r = m2.get(f"/api/recent?uid={users['somchai']}").get_json()
    check("สมาชิกแอบดูของคนนอกขอบเขตไม่ได้ (ถอยมาที่ของตัวเอง)",
          len(r["searches"]) == 5 and all(x["user_id"] == users["wichai"] for x in r["searches"]))
    r = m2.get("/api/recent?uid=all").get_json()
    check("สมาชิกไม่มีทีม เลือก all ก็ยังเห็นแต่ของตัวเอง", len(r["searches"]) == 5)
    check("สมาชิกไม่มีทีม → ไม่มีตัวเลือกคนอื่น", r["can_all"] is False and len(r["people"]) == 1)

    # ทีม: somchai + admin1 และให้สิทธิ์ดูทีม
    admin.post("/api/admin/teams", json={"name": "ทีม A",
                                         "member_ids": [users["admin1"], users["somchai"]]})
    admin.put(f"/api/admin/members/{users['somchai']}",
              json={"permissions": {"view_team": True}})
    r = m1.get("/api/recent").get_json()
    check("สมาชิกมีสิทธิ์ดูทีม: ค่าเริ่มต้นยังเป็นของตัวเอง (3 แถว)", len(r["searches"]) == 3)
    r = m1.get("/api/recent?uid=all").get_json()
    check("เลือกทั้งทีม → เห็นของตัวเอง+เพื่อนร่วมทีม (7 แถว)", len(r["searches"]) == 7,
          str(len(r["searches"])))
    check("ไม่มีข้อมูลคนนอกทีมปนมา",
          all(x["user_id"] in (users["admin1"], users["somchai"]) for x in r["searches"]))
    r = m1.get(f"/api/recent?uid={users['wichai']}").get_json()
    check("เลือกดูคนนอกทีมไม่ได้ (ถอยมาที่ของตัวเอง)", len(r["searches"]) == 3)

    # ── รุ่นเปิดให้ทุกคนอัปเดต ──
    server.urllib.request.urlopen = lambda *a, **k: FakeManifest()
    MANIFEST.pop("open", None)
    v = m2.get("/api/version").get_json()
    check("รุ่นปกติ: สมาชิกไม่มีสิทธิ์ → ไม่แจ้งเตือน ไม่ให้กด",
          v["update_available"] and not v["can_apply"] and not v["notify"] and not v.get("open"))
    r = m2.post("/api/update/apply")
    check("รุ่นปกติ: apply ถูกปฏิเสธ (403)", r.status_code == 403
          and r.get_json().get("need_grant") is True)

    MANIFEST["open"] = True
    v = m2.get("/api/version").get_json()
    check("รุ่น open: สมาชิกทุกคนเห็นแจ้งเตือนและกดได้",
          v["can_apply"] and v["notify"] and v["open"] is True)
    r = m2.post("/api/update/apply")
    check("รุ่น open: ผ่านด่านสิทธิ์ (ไปตายที่ zip ปลอม ไม่ใช่ 403)",
          r.status_code != 403, f"got {r.status_code}")

    MANIFEST.pop("open")
    v = m2.get("/api/version").get_json()
    check("รุ่นถัดไปที่ไม่ประกาศ open → กลับมาบังคับสิทธิ์เอง",
          not v["can_apply"] and not v["notify"])
    v = admin.get("/api/version").get_json()
    check("แอดมินอัปเดตได้เสมอไม่ว่ารุ่นไหน", v["can_apply"] and v["notify"])

    print(f"\nผล: ผ่าน {PASS} · ตก {FAIL}")
    return 1 if FAIL else 0


try:
    code = main()
finally:
    shutil.rmtree(TEST_DATA, ignore_errors=True)
sys.exit(code)
