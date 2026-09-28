/**
 * CRIMES AUTO — ศูนย์กลางรวมตัวเลข (Google Apps Script)
 *
 * รับ "ตัวเลขนับ" จากเครื่องลูกแต่ละเครื่องมาเก็บใน Google Sheet
 * ไม่มีข้อมูลประวัติ เลขบัตร ชื่อผู้ถูกค้น ผลคดี หรือชื่อไฟล์งาน ส่งมาที่นี่
 *
 * v3.2.0: เพิ่มชีต 'presence' — ใครใช้เวอร์ชันไหน/เห็นล่าสุดเมื่อไร (ชื่อที่แสดง · uid ·
 * เวอร์ชัน · เวลา) เพื่อให้ผู้ดูแลเห็นสมาชิกทุกเครื่องแบบเรียลไทม์ · โปรแกรมส่งก้อน
 * kind="presence" (ไม่มี rows) บ่อยกว่าก้อนตัวเลข — ก้อนนี้ต้องไม่ลบตัวเลขเดือนที่เก็บไว้
 *
 * v3.7.0: เพิ่มชีต 'members' — ไดเรกทอรีสมาชิกกลาง (เจ้าของโปรเจกต์อนุมัติ) ทุกเครื่องส่งสมาชิกที่ตนแก้
 * (ชื่อผู้ใช้ · ชื่อที่แสดง · บทบาท · สิทธิ์ · สถานะ · รหัสผ่านแบบแฮช+salt · อัตรา · เวลาแก้) มาเก็บที่นี่
 * แล้วรับไดเรกทอรีทั้งองค์กรกลับไป → สมาชิกเข้าได้ทุกเครื่องที่ติดตั้ง
 * ชีตนี้มีแฮชรหัสผ่าน (ไม่ใช่รหัสผ่านจริง แต่เดาออฟไลน์ได้ถ้าหลุด) — แชร์ไฟล์ Sheet นี้ให้เฉพาะผู้ดูแล
 * ก้อน kind="members" ต้องตอบ {ok, members:[...]} เสมอ — โปรแกรมใช้การมี members เป็นตัวบอกว่า
 * สคริปต์รุ่นใหม่แล้ว (รุ่นเก่าตอบ ok เฉย ๆ โปรแกรมจะเตือนให้อัปเดตสคริปต์)
 *
 * กติกาของไดเรกทอรี (ศูนย์กลางเป็นผู้ตัดสิน ไม่ใช่นาฬิกาของแต่ละเครื่อง):
 *  • ทุกแถวมีเลขรุ่น `rev` ที่ศูนย์กลางนับเอง (+1 ทุกครั้งที่รับการแก้) เครื่องลูกต้องส่ง rev ที่ตนเห็นล่าสุดมาด้วย
 *    ถ้าไม่ตรง = มีเครื่องอื่นแก้ไปก่อน → ปัดตก (reason "conflict") ของกลางชนะ เครื่องนั้นได้ของกลางกลับไปทับ
 *    (เวลาเครื่องเพี้ยน/เขตเวลาต่างกัน จึงไม่ทำให้การแก้ของใครถูกกลืนเงียบ ๆ)
 *  • การแก้ที่ "เปลี่ยนไดเรกทอรี" — สร้างคน · แก้บทบาท/สิทธิ์/สถานะ/ชื่อ/อัตรา · ลบ · ตั้งรหัสให้ Super Admin —
 *    ต้องเซ็นด้วย ADMIN_TOKEN (ลายเซ็นที่สอง `asign`) ซึ่งใส่เฉพาะในเครื่องของ Super Admin
 *    เครื่องที่มีแค่ HUB_TOKEN (ทุกเครื่องมี — อยู่ในรหัสเชื่อมต่อที่แจกสมาชิก) ทำได้แค่ดึงไดเรกทอรี และส่ง
 *    "รหัสผ่านใหม่ของสมาชิกธรรมดาที่มีอยู่แล้ว" (เปลี่ยนรหัสตัวเอง/ลืมรหัส) — ส่งอย่างอื่นมาจะถูกปัดตก (reason "auth")
 *    ข้อยกเว้นเดียว: ไดเรกทอรีว่างเปล่า = เครื่องแรกขององค์กรกำลังตั้งค่า รับได้ทั้งก้อน
 *  • ไม่รับการแก้ที่ทำให้ไม่เหลือ Super Admin ที่เปิดใช้งานเลย (reason "last_admin") — สองเครื่องปิดกันเองพร้อมกัน
 *    ก็ไม่ทำให้ทั้งองค์กรล็อกตัวเองออก
 *
 * v3.9.0: เพิ่มชีต 'ledger' — สมุดกองกลางกลาง (เจ้าของโปรเจกต์สั่ง "แสดงค่าเดียวกันทุกเครื่อง") ทุกเครื่องเห็นรายการ
 * รับ/จ่ายชุดเดียวกัน · ก้อน kind="ledger" ส่ง "รายการที่เครื่องนั้นเพิ่ม/ลบ" + after (rev สูงสุดที่เคยรับ) แล้วรับ
 * ส่วนต่าง (rev > after) กลับไป — ไม่ใช่ทั้งเล่มทุกรอบ
 *  • rev ของชีตนี้เป็นเลขเดียวทั้งเล่ม (+1 ทุกครั้งที่รับการแก้ใด ๆ) แต่ละแถวจดว่าถูกแก้ล่าสุดที่ rev ไหน
 *    เครื่องลูกส่ง rev ที่ตนเห็นของแถวนั้นมา ไม่ตรง = conflict ของกลางชนะ (เหมือนสมาชิก)
 *  • การเพิ่ม/ลบต้องเซ็นด้วย ADMIN_TOKEN (Super Admin เป็นผู้จัดการกองกลาง) — เครื่องที่มีแค่ HUB_TOKEN ดึงได้อย่างเดียว
 *    (ไม่มีข้อยกเว้นชีตว่างเหมือนสมาชิก: ตั้ง ADMIN_TOKEN ก่อน ไม่งั้นรายการจะ "รอส่ง" อยู่ที่เครื่องผู้ดูแล)
 *  • ลบ = แถวยังอยู่แต่ deleted=1 (ป้ายหลุมศพให้เครื่องอื่นลบตาม) · ยอดรับ/จ่ายของกระดาน (doGet) คิดจากชีตนี้
 *    (ของจริง ไม่ซ้ำ ไม่ค้าง) — โปรแกรม 3.9.0 ไม่ส่งยอดเงินมาในก้อน counts อีกแล้ว คอลัมน์ amount_* ในชีต counts จึงว่าง
 *  • เครื่องที่ส่ง after เกินกว่า rev สูงสุดของเล่มนี้ (เปลี่ยนศูนย์กลาง/ชีตถูกสร้างใหม่) ได้ทั้งเล่มกลับไป (full)
 *  • หมายเหตุเป็นข้อความที่ผู้ดูแลพิมพ์เอง — ห้ามพิมพ์เลขบัตร/ชื่อผู้ถูกค้น/ผลคดี
 *
 * ** หลังวางโค้ดรุ่นนี้ทับ ต้องอัปเดตการ Deploy ให้ใช้โค้ดใหม่ ด้วยวิธีนี้เท่านั้น: **
 *    Deploy → Manage deployments → (อันที่ใช้อยู่) ไอคอนดินสอ ✏ → Version: New version → Deploy
 *    ห้ามใช้ "New deployment" เพราะจะได้ URL /exec อันใหม่ เครื่องลูกทุกเครื่องจะยังคุยกับ
 *    สคริปต์ตัวเก่าและข้อมูลสถานะจะไม่เข้าโดยไม่มีใครรู้
 *
 * ── วิธีติดตั้ง ────────────────────────────────────────────────
 * 1. สร้าง Google Sheet ใหม่ 1 ไฟล์ (จะใช้เก็บข้อมูล)
 * 2. เมนู Extensions → Apps Script  แล้ววางโค้ดนี้ทับทั้งหมด
 * 3. แก้ HUB_TOKEN ข้างล่างเป็นรหัสลับของคุณเอง (สุ่มยาว ๆ อย่างน้อย 32 ตัว)
 *    และแก้ ADMIN_TOKEN เป็นรหัสอีกชุด (ต้องต่างจาก HUB_TOKEN) — ใส่รหัสนี้เฉพาะในเครื่องของ Super Admin ที่
 *    Setting → ศูนย์กลาง → "รหัสผู้ดูแลศูนย์กลาง" · ห้ามใส่ในรหัสเชื่อมต่อที่แจกสมาชิก
 * 4. กด Deploy → New deployment → เลือกชนิด "Web app"
 *      - Execute as        : Me
 *      - Who has access    : Anyone
 *    (ต้องเป็น Anyone เพราะโปรแกรมในเครื่องไม่ได้ล็อกอิน Google — ความปลอดภัย
 *     มาจากลายเซ็น HMAC ที่ตรวจในโค้ดนี้ ไม่ใช่จากการล็อกอิน)
 * 5. คัดลอก URL ที่ลงท้ายด้วย /exec ไปใส่ในโปรแกรมที่
 *      Setting → ศูนย์กลางรวมตัวเลข → URL   และใส่ HUB_TOKEN เดียวกันในช่องรหัสลับ
 *
 * ── ข้อควรรู้ ─────────────────────────────────────────────────
 * HUB_TOKEN ใช้ยืนยันว่า "ข้อมูลมาจากเครื่องขององค์กร" เท่านั้น
 * เครื่องลูกทุกเครื่องใช้รหัสเดียวกัน ผู้ใช้ที่เปิดไฟล์ config.json ในเครื่องตัวเองจะเห็นรหัสนี้
 * จึงกันคนนอกได้ แต่ไม่ได้กันคนในที่ตั้งใจส่งตัวเลขปลอมของตัวเอง
 * ถ้าต้องการกันกรณีนั้น ให้ดูคอลัมน์ install_id ในชีตประกอบเสมอ
 * ส่วน ADMIN_TOKEN คือสิ่งที่กันคนในไม่ให้ใช้รหัสร่วมนั้นตั้งตัวเองเป็น Super Admin หรือเปลี่ยนรหัสผ่านคนอื่นผ่านศูนย์กลาง
 * (คนที่เข้าถึงไฟล์ในเครื่องของ Super Admin ได้ ย่อมทำได้เท่า Super Admin ของเครื่องนั้นอยู่แล้ว — ขอบเขตเดิม)
 */

var HUB_TOKEN = 'เปลี่ยนรหัสนี้ก่อนใช้งานจริง';
// v3.7.0: รหัสผู้ดูแลศูนย์กลาง — เซ็นก้อน members ที่ "แก้ไดเรกทอรี" (ดูกติกาด้านบน) · ต้องต่างจาก HUB_TOKEN
// ยังเป็นค่าตั้งต้นอยู่ = ศูนย์กลางยังไม่รับการแก้ไดเรกทอรีจากเครื่องไหนเลย (โปรแกรมจะบอกผู้ดูแลให้มาตั้ง)
var ADMIN_TOKEN = 'เปลี่ยนรหัสผู้ดูแลนี้ก่อนใช้งานจริง';
var SHEET_NAME = 'counts';
var PRESENCE_SHEET = 'presence';
var MEMBERS_SHEET = 'members';
var MEMBER_COLS = ['username', 'display_name', 'role', 'permissions', 'active', 'password_hash', 'salt',
                   'rate_per_name', 'created_at', 'updated_at', 'deleted', 'rev', 'updated_by', 'received_at'];
// v3.9.0: สมุดกองกลางกลาง — origin = เครื่องที่บันทึกรายการ (ไม่เปลี่ยนแม้เครื่องอื่นลบ) · updated_by = เครื่องที่แก้ล่าสุด
var LEDGER_SHEET = 'ledger';
var LEDGER_COLS = ['gid', 'ts', 'ym', 'owner', 'kind', 'amount', 'note', 'created_by', 'deleted', 'rev',
                   'origin', 'updated_by', 'received_at'];

/** ข้อความเวลาแบบ ISO — Sheet อาจแปลงข้อความวันที่เป็น Date ให้เอง ต้องคืนกลับเป็นข้อความรูปเดิมก่อนเทียบ */
function _isoText(v) {
  if (v instanceof Date && !isNaN(v)) {
    var p = function (n) { return ('0' + n).slice(-2); };
    return v.getFullYear() + '-' + p(v.getMonth() + 1) + '-' + p(v.getDate()) + 'T'
      + p(v.getHours()) + ':' + p(v.getMinutes()) + ':' + p(v.getSeconds());
  }
  return String(v == null ? '' : v);
}

function _membersSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(MEMBERS_SHEET);
  if (!sh) {
    sh = ss.insertSheet(MEMBERS_SHEET);
    sh.appendRow(MEMBER_COLS);
    sh.setFrozenRows(1);
  }
  return sh;
}

function _readMembers(sh) {
  var last = sh.getLastRow();
  var vals = last >= 2 ? sh.getRange(2, 1, last - 1, MEMBER_COLS.length).getValues() : [];
  var map = {};
  vals.forEach(function (v) {
    var u = String(v[0] == null ? '' : v[0]).trim();
    if (!u) return;
    map[u] = { username: u, display_name: String(v[1] == null ? '' : v[1]),
               role: String(v[2] || 'member'), permissions: String(v[3] || '{}'),
               active: Number(v[4]) ? 1 : 0, password_hash: String(v[5] == null ? '' : v[5]),
               salt: String(v[6] == null ? '' : v[6]),
               rate_per_name: (v[7] === '' || v[7] == null) ? null : Number(v[7]),
               created_at: _isoText(v[8]), updated_at: _isoText(v[9]), deleted: Number(v[10]) ? 1 : 0,
               rev: Number(v[11]) || 0,
               updated_by: String(v[12] == null ? '' : v[12]), received_at: _isoText(v[13]) };
  });
  return map;
}

/** แถวที่เครื่องลูกส่งมา → รูปแบบมาตรฐานเดียวกับที่เก็บ (บทบาทมีแค่ 2 ค่า · ตัวเลข/ข้อความสะอาด) */
function _memberCandidate(m, u, cur, nowText) {
  var upd = _isoText(m.updated_at) || nowText;
  return {
    username: u, display_name: String(m.display_name == null ? '' : m.display_name),
    role: (m.role === 'super_admin') ? 'super_admin' : 'member',
    permissions: (typeof m.permissions === 'string') ? m.permissions : JSON.stringify(m.permissions || {}),
    active: Number(m.active) ? 1 : 0,
    password_hash: String(m.password_hash == null ? '' : m.password_hash),
    salt: String(m.salt == null ? '' : m.salt),
    rate_per_name: (m.rate_per_name === '' || m.rate_per_name == null) ? null : Number(m.rate_per_name),
    created_at: _isoText(m.created_at) || (cur && cur.created_at) || upd,
    updated_at: upd, deleted: Number(m.deleted) ? 1 : 0
  };
}

var _PROTECTED = ['display_name', 'role', 'permissions', 'active', 'rate_per_name', 'deleted'];
function _sameFields(a, b, fields) {
  for (var i = 0; i < fields.length; i++) {
    var k = fields[i];
    if (String(a[k] == null ? '' : a[k]) !== String(b[k] == null ? '' : b[k])) return false;
  }
  return true;
}
function _sameContent(a, b) { return _sameFields(a, b, _PROTECTED.concat(['password_hash', 'salt'])); }
function _isActiveAdmin(r) { return !!r && r.role === 'super_admin' && !!r.active && !r.deleted; }
function _otherActiveAdmins(map, except) {
  return Object.keys(map).filter(function (k) { return k !== except && _isActiveAdmin(map[k]); }).length;
}

/** v3.7.0: รับแถวที่เครื่องลูกแก้ → ตรวจ rev / สิทธิ์ / Super Admin คนสุดท้าย → คืนทั้งไดเรกทอรี + รายการที่ปัดตก
 *  isAdmin = ก้อนนี้เซ็นด้วย ADMIN_TOKEN ถูกต้อง (เครื่องของ Super Admin) */
function _syncMembers(installId, incoming, now, isAdmin) {
  var sh = _membersSheet();
  var map = _readMembers(sh);
  var bootstrap = Object.keys(map).length === 0;      // ไดเรกทอรีว่าง = เครื่องแรกขององค์กรกำลังตั้งค่า
  var nowText = _isoText(now);
  var applied = 0, rejected = [];
  (incoming || []).forEach(function (m) {
    if (!m || typeof m !== 'object') return;
    var u = String(m.username == null ? '' : m.username).trim();
    if (!u || u.length > 64) return;
    var cur = map[u] || null;
    var cand = _memberCandidate(m, u, cur, nowText);
    var base = Number(m.rev) || 0;
    // เลขรุ่นที่เครื่องลูกเห็นล่าสุดต้องตรงกับของกลาง — ไม่ตรง = มีเครื่องอื่นแก้ไปก่อน → ของกลางชนะ (ไม่ดูนาฬิกาใคร)
    if (cur && base !== cur.rev) { rejected.push({ username: u, reason: 'conflict' }); return; }
    if (cur && _sameContent(cur, cand)) return;        // ไม่มีอะไรเปลี่ยน — ไม่เพิ่มรุ่น
    if (!isAdmin && !bootstrap) {
      // ไม่มีรหัสผู้ดูแล: รับเฉพาะ "รหัสผ่านใหม่ของสมาชิกธรรมดาที่มีอยู่แล้ว" (เปลี่ยนรหัสตัวเอง/ลืมรหัส)
      // สร้างคน · แก้บทบาท/สิทธิ์/สถานะ/ชื่อ/อัตรา · ลบ · แตะ Super Admin → ต้องมี ADMIN_TOKEN
      var selfService = !!cur && !cur.deleted && cur.role !== 'super_admin' && !cand.deleted
        && _sameFields(cur, cand, _PROTECTED) && !!cand.password_hash && !!cand.salt;
      if (!selfService) { rejected.push({ username: u, reason: 'auth' }); return; }
    }
    // ห้ามทำให้ไม่เหลือ Super Admin ที่เปิดใช้งานเลย
    if (_isActiveAdmin(cur) && !_isActiveAdmin(cand) && _otherActiveAdmins(map, u) === 0) {
      rejected.push({ username: u, reason: 'last_admin' }); return;
    }
    cand.rev = cur ? cur.rev + 1 : 1;
    cand.updated_by = String(installId == null ? '' : installId);
    cand.received_at = nowText;
    map[u] = cand;
    applied++;
  });
  var all = Object.keys(map).sort().map(function (k) { return map[k]; });
  if (applied) {
    // เวลาเก็บเป็นข้อความเสมอ (นำหน้าด้วย ' กัน Sheet แปลงเป็น Date)
    var out = all.map(function (r) {
      return [_safeStr(r.username), _safeStr(r.display_name), r.role, _safeStr(r.permissions), r.active,
              r.password_hash, r.salt, r.rate_per_name == null ? '' : r.rate_per_name,
              "'" + r.created_at, "'" + r.updated_at, r.deleted, r.rev, r.updated_by, "'" + r.received_at];
    });
    var last = sh.getLastRow();
    if (last >= 2) sh.getRange(2, 1, last - 1, MEMBER_COLS.length).clearContent();
    if (out.length) sh.getRange(2, 1, out.length, MEMBER_COLS.length).setValues(out);
  }
  return {
    applied: applied, rejected: rejected,
    members: all.map(function (r) {
      return { username: r.username, display_name: r.display_name, role: r.role, permissions: r.permissions,
               active: r.active, password_hash: r.password_hash, salt: r.salt, rate_per_name: r.rate_per_name,
               created_at: r.created_at, updated_at: r.updated_at, deleted: r.deleted, rev: r.rev };
    })
  };
}

/** ข้อความที่ผู้ใช้ตั้งเอง (เช่น ชื่อที่แสดง) ต้องไม่กลายเป็นสูตรใน Sheet */
function _safeStr(v) {
  var s = String(v == null ? '' : v);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

// ──────────────── v3.9.0: สมุดกองกลางกลาง ────────────────
/** เดือน 'YYYY-MM' — Sheet อาจแปลงข้อความนี้เป็น Date ให้เอง ต้องคืนกลับเป็นข้อความรูปเดิม */
function _ymText(v) {
  if (v instanceof Date && !isNaN(v)) return v.getFullYear() + '-' + ('0' + (v.getMonth() + 1)).slice(-2);
  return String(v == null ? '' : v).slice(0, 7);
}

function _ledgerSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(LEDGER_SHEET);
  if (!sh) {
    sh = ss.insertSheet(LEDGER_SHEET);
    sh.appendRow(LEDGER_COLS);
    sh.setFrozenRows(1);
  }
  return sh;
}

function _readLedger(sh) {
  var last = sh.getLastRow();
  var vals = last >= 2 ? sh.getRange(2, 1, last - 1, LEDGER_COLS.length).getValues() : [];
  var map = {};
  vals.forEach(function (v) {
    var g = String(v[0] == null ? '' : v[0]).trim();
    if (!g) return;
    map[g] = { gid: g, ts: _isoText(v[1]), ym: _ymText(v[2]), owner: String(v[3] == null ? '' : v[3]),
               kind: String(v[4] || ''), amount: Number(v[5]) || 0, note: String(v[6] == null ? '' : v[6]),
               created_by: String(v[7] == null ? '' : v[7]), deleted: Number(v[8]) ? 1 : 0, rev: Number(v[9]) || 0,
               origin: String(v[10] == null ? '' : v[10]), updated_by: String(v[11] == null ? '' : v[11]),
               received_at: _isoText(v[12]) };
  });
  return map;
}

/** แถวที่เครื่องลูกส่งมา → รูปแบบมาตรฐาน · คืน null ถ้ารูปแบบใช้ไม่ได้ (ประเภท/จำนวน/เดือน) */
function _ledgerCandidate(m, gid, cur, nowText) {
  var kind = (m.kind === 'in' || m.kind === 'out') ? m.kind : '';
  var amount = Math.round((Number(m.amount) || 0) * 100) / 100;
  var ts = _isoText(m.ts).slice(0, 19) || (cur && cur.ts) || nowText;
  var ym = _ymText(m.ym) || ts.slice(0, 7);
  if (!kind || !(amount > 0) || !isFinite(amount) || !/^\d{4}-\d{2}$/.test(ym)) return null;
  return {
    gid: gid, ts: ts, ym: ym, owner: String(m.owner == null ? '' : m.owner).slice(0, 64), kind: kind, amount: amount,
    note: String(m.note == null ? '' : m.note).slice(0, 300),
    created_by: String(m.created_by == null ? '' : m.created_by).slice(0, 64) || (cur && cur.created_by) || '',
    deleted: Number(m.deleted) ? 1 : 0
  };
}
var _LEDGER_CONTENT = ['ts', 'ym', 'owner', 'kind', 'amount', 'note', 'deleted'];

/** v3.9.0: รับรายการที่เครื่องลูกเพิ่ม/ลบ → ตรวจ rev / สิทธิ์ → คืนส่วนต่าง (rev > after) + รายการที่เครื่องนั้นเพิ่งส่ง
 *  isAdmin = ก้อนนี้เซ็นด้วย ADMIN_TOKEN ถูกต้อง · ไม่ใช่ = ดึงได้อย่างเดียว (ทุกการแก้ถูกปัดตก reason "auth") */
function _syncLedger(installId, incoming, after, now, isAdmin) {
  var sh = _ledgerSheet();
  var map = _readLedger(sh);
  var maxRev = 0;
  Object.keys(map).forEach(function (k) { if (map[k].rev > maxRev) maxRev = map[k].rev; });
  // after เกินกว่าที่เล่มนี้เคยนับ = เครื่องนั้นจำเลขจากศูนย์กลางเก่า/ชีตที่ถูกสร้างใหม่ → ส่งทั้งเล่ม (full) ไม่งั้นมันจะไม่ได้อะไรเลย
  // จนกว่า rev จะไล่ทันเลขเก่า (รีวิว PR #33)
  var full = !(after > 0) || after > maxRev;
  if (full) after = 0;
  var nowText = _isoText(now);
  var applied = 0, rejected = [], touched = {};
  (incoming || []).forEach(function (m) {
    if (!m || typeof m !== 'object') return;
    var g = String(m.gid == null ? '' : m.gid).trim();
    if (!g || g.length > 64) return;
    var cur = map[g] || null;
    if (cur) touched[g] = true;
    var cand = _ledgerCandidate(m, g, cur, nowText);
    if (!cand) { rejected.push({ gid: g, reason: 'invalid' }); return; }
    var base = Number(m.rev) || 0;
    if (cur && base !== cur.rev) { rejected.push({ gid: g, reason: 'conflict' }); return; }
    if (cur && _sameFields(cur, cand, _LEDGER_CONTENT)) return;      // ไม่มีอะไรเปลี่ยน
    if (!isAdmin) { rejected.push({ gid: g, reason: 'auth' }); return; }
    if (!cur && cand.deleted) return;                                   // ลบสิ่งที่กลางไม่เคยมี — ไม่ต้องเก็บ
    cand.rev = ++maxRev;
    cand.origin = cur ? cur.origin : String(installId == null ? '' : installId);
    cand.updated_by = String(installId == null ? '' : installId);
    cand.received_at = nowText;
    map[g] = cand;
    touched[g] = true;
    applied++;
  });
  if (applied) {
    var out = Object.keys(map).sort(function (a, b) { return map[a].rev - map[b].rev; }).map(function (k) {
      var r = map[k];
      return [_safeStr(r.gid), "'" + r.ts, "'" + r.ym, _safeStr(r.owner), r.kind, r.amount, _safeStr(r.note),
              _safeStr(r.created_by), r.deleted, r.rev, _safeStr(r.origin), _safeStr(r.updated_by), "'" + r.received_at];
    });
    var last = sh.getLastRow();
    if (last >= 2) sh.getRange(2, 1, last - 1, LEDGER_COLS.length).clearContent();
    if (out.length) sh.getRange(2, 1, out.length, LEDGER_COLS.length).setValues(out);
  }
  var entries = Object.keys(map).filter(function (k) { return map[k].rev > after || touched[k]; })
    .sort(function (a, b) { return map[a].rev - map[b].rev; })
    .map(function (k) {
      var r = map[k];
      return { gid: r.gid, ts: r.ts, ym: r.ym, owner: r.owner, kind: r.kind, amount: r.amount, note: r.note,
               created_by: r.created_by, deleted: r.deleted, rev: r.rev, origin: r.origin };
    });
  return { applied: applied, rejected: rejected, entries: entries, seq: maxRev, full: full };
}

/** v3.9.0: ยอดรับ/จ่ายของกระดาน (doGet) มาจากชีต ledger ที่เป็นของจริง — ไม่ใช่ตัวเลขที่แต่ละเครื่องรายงานในชีต counts
 *  (เครื่อง A บันทึก แล้วเครื่อง B ลบ → ยอดที่ A เคยรายงานจะค้างในชีต counts จน A ส่งใหม่ ถ้า A ไม่กลับมาก็ค้างตลอด — รีวิว PR #33)
 *  คืน {byKey: {'origin|display_name': {amount_in, amount_out}}, totals: {amount_in, amount_out}} · ชื่อที่แสดงหาจากชีต members */
function _ledgerAmounts(ym) {
  var map = _readLedger(_ledgerSheet());
  var names = {};
  var msh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MEMBERS_SHEET);
  if (msh) {
    var mm = _readMembers(msh);
    Object.keys(mm).forEach(function (u) { if (mm[u].display_name) names[u] = mm[u].display_name; });
  }
  var byKey = {}, totals = { amount_in: 0, amount_out: 0 };
  Object.keys(map).forEach(function (g) {
    var r = map[g];
    if (r.deleted || (ym && r.ym !== ym)) return;
    var key = r.origin + '|' + (names[r.owner] || r.owner || '');
    var p = byKey[key] || (byKey[key] = { install_id: r.origin, display_name: names[r.owner] || r.owner || '', amount_in: 0, amount_out: 0 });
    var f = r.kind === 'out' ? 'amount_out' : 'amount_in';
    p[f] = Math.round((p[f] + r.amount) * 100) / 100;
    totals[f] = Math.round((totals[f] + r.amount) * 100) / 100;
  });
  return { byKey: byKey, totals: totals };
}

function _presenceSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(PRESENCE_SHEET);
  if (!sh) {
    sh = ss.insertSheet(PRESENCE_SHEET);
    sh.appendRow(['received_at', 'install_id', 'uid', 'display_name', 'app_version', 'last_seen']);
    sh.setFrozenRows(1);
  }
  return sh;
}

/** อัปเดตสถานะรายคนของเครื่องนี้ (แทนที่แถวเดิมของ install_id|uid ถ้ามี) */
function _upsertPresence(installId, appVersion, users, now) {
  var sh = _presenceSheet();
  var last = sh.getLastRow();
  var vals = last >= 2 ? sh.getRange(2, 1, last - 1, 6).getValues() : [];
  // แทนที่รายชื่อของเครื่องนี้ทั้งชุด — คนที่ถูกลบ/ปิดใช้งานแล้วจะหายจากศูนย์กลางด้วย
  var keep = vals.filter(function (v) { return String(v[1]) !== String(installId); });
  var fresh = users.map(function (u) {
    return [now, String(installId), String(u.uid), _safeStr(u.display_name),
            _safeStr(u.app_version || appVersion), _safeStr(u.last_seen)];
  });
  var out = keep.concat(fresh);
  if (vals.length) sh.getRange(2, 1, vals.length, 6).clearContent();
  if (out.length) sh.getRange(2, 1, out.length, 6).setValues(out);
}

function _sheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(['received_at', 'install_id', 'app_version', 'ym', 'date', 'uid',
                  'display_name', 'searches', 'found', 'notfound', 'error',
                  'files', 'amount_in', 'amount_out']);
    sh.setFrozenRows(1);
  }
  return sh;
}

function _signWith(text, key) {
  var raw = Utilities.computeHmacSha256Signature(text, key);
  return raw.map(function (b) {
    return ('0' + (b & 0xff).toString(16)).slice(-2);
  }).join('');
}
function _sign(text) { return _signWith(text, HUB_TOKEN); }

/** ADMIN_TOKEN ถูกตั้งแล้วหรือยัง — ค่าตั้งต้น หรือซ้ำกับ HUB_TOKEN = ยังไม่ตั้ง (ไม่รับลายเซ็นผู้ดูแลเลย) */
function _adminReady() {
  return ADMIN_TOKEN !== 'เปลี่ยนรหัสผู้ดูแลนี้ก่อนใช้งานจริง' && ADMIN_TOKEN !== HUB_TOKEN && ADMIN_TOKEN.length >= 8;
}

/** เทียบแบบไม่หลุดข้อมูลจากเวลาที่ใช้เปรียบเทียบ */
function _safeEqual(a, b) {
  a = String(a || ''); b = String(b || '');
  if (a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/** กันสองเครื่องเขียนชีตพร้อมกันแล้วข้อมูลหาย (อ่าน-ล้าง-เขียนทับ ต้องทำทีละคน)
 *  รอได้สูงสุด 25 วิ แล้วค่อยยอมแพ้ — ฝั่งเครื่องลูกส่งใหม่รอบหน้าอยู่แล้ว */
function _withLock(fn) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(25000)) return _json({ ok: false, error: 'ศูนย์กลางกำลังยุ่ง ลองใหม่อีกครั้ง' });
  try { return fn(); } finally { lock.releaseLock(); }
}

/** รับข้อมูลจากเครื่องลูก */
function doPost(e) {
  return _withLock(function () { return _doPostLocked(e); });
}

function _doPostLocked(e) {
  try {
    var body = (e && e.postData && e.postData.contents) || '';
    // ลายเซ็นมากับ query string เพราะ Apps Script อ่าน HTTP header ที่ผู้เรียกกำหนดเองไม่ได้
    var sig = (e && e.parameter && e.parameter.sign) || '';
    if (!_safeEqual(sig, _sign(body))) {
      return _json({ ok: false, error: 'ลายเซ็นไม่ถูกต้อง' });
    }
    var data = JSON.parse(body);
    var now = new Date();
    var stored = 0;

    // ลายเซ็นที่สอง (asign) ด้วย ADMIN_TOKEN = เครื่องของ Super Admin → แก้ไดเรกทอรี/สมุดกองกลางได้
    var asig = (e && e.parameter && e.parameter.asign) || '';
    var adminReady = _adminReady();
    var isAdmin = adminReady && !!asig && _safeEqual(asig, _signWith(body, ADMIN_TOKEN));

    // v3.7.0: ไดเรกทอรีสมาชิกกลาง — ก้อนนี้ไม่มี rows/users จึงไม่แตะตัวเลขและสถานะ
    if (data.kind === 'members' && Array.isArray(data.members)) {
      var ms = _syncMembers(data.install_id, data.members, now, isAdmin);
      return _json({ ok: true, kind: 'members', applied: ms.applied, rejected: ms.rejected,
                     admin: isAdmin, admin_ready: adminReady, members: ms.members });
    }
    // v3.9.0: สมุดกองกลางกลาง — ตอบส่วนต่างตั้งแต่ rev ที่เครื่องนั้นเคยรับ (after) + รายการที่มันเพิ่งส่ง
    if (data.kind === 'ledger' && Array.isArray(data.entries)) {
      var ls = _syncLedger(data.install_id, data.entries, Number(data.after) || 0, now, isAdmin);
      return _json({ ok: true, kind: 'ledger', applied: ls.applied, rejected: ls.rejected,
                     admin: isAdmin, admin_ready: adminReady, entries: ls.entries, seq: ls.seq, full: ls.full });
    }

    // ตัวเลขรายเดือน: เฉพาะเมื่อก้อนนี้มี rows เป็นอาร์เรย์จริง ๆ
    // (ก้อน presence ไม่มี rows — ต้องไม่ไปลบตัวเลขที่เก็บไว้)
    if (Array.isArray(data.rows) && data.ym) {
      var rows = data.rows;
      var sh = _sheet();
      // ส่งซ้ำเดือนเดิมจากเครื่องเดิม = แทนที่ของเก่า ไม่ใช่เพิ่มซ้ำ
      _deleteExisting(sh, data.install_id, data.ym);
      if (rows.length) {
        var out = rows.map(function (r) {
          return [now, data.install_id, data.app_version, data.ym, r.date, r.uid,
                  _safeStr(r.display_name), r.searches, r.found, r.notfound, r.error,
                  r.files, r.amount_in, r.amount_out];
        });
        sh.getRange(sh.getLastRow() + 1, 1, out.length, out[0].length).setValues(out);
      }
      stored = rows.length;
    }
    // สถานะสมาชิก (v3.2.0): มากับทั้งก้อนตัวเลขและก้อน presence
    if (Array.isArray(data.users)) {
      _upsertPresence(data.install_id, data.app_version, data.users, now);
    }
    return _json({ ok: true, stored: stored, kind: data.kind || 'counts' });
  } catch (err) {
    return _json({ ok: false, error: String(err).slice(0, 200) });
  }
}

/** ลบข้อมูลชุดเดิมของ (เครื่อง, เดือน) นี้ ก่อนเขียนชุดใหม่ทับ
 *  อ่านทั้งแผ่นมากรองในหน่วยความจำแล้วเขียนกลับครั้งเดียว — เร็วกว่าเรียก deleteRow ทีละแถว
 *  ซึ่งยิง API หนึ่งครั้งต่อแถวและช้ามากเมื่อชีตโตขึ้น */
function _deleteExisting(sh, installId, ym) {
  var last = sh.getLastRow();
  if (last < 2) return;
  var width = sh.getLastColumn();
  var vals = sh.getRange(2, 1, last - 1, width).getValues();
  var keep = vals.filter(function (v) {
    return !(String(v[1]) === String(installId) && String(v[3]) === String(ym));
  });
  if (keep.length === vals.length) return;          // ไม่มีอะไรต้องลบ
  sh.getRange(2, 1, vals.length, width).clearContent();
  if (keep.length) sh.getRange(2, 1, keep.length, width).setValues(keep);
}

/** คืนยอดรวมของทุกเครื่อง ให้โปรแกรมดึงไปแสดงบนกระดาน */
function doGet(e) {
  return _withLock(function () { return _doGetLocked(e); });
}

function _doGetLocked(e) {
  try {
    var ym = (e && e.parameter && e.parameter.ym) || '';
    var sig = (e && e.parameter && e.parameter.sign) || '';
    if (!_safeEqual(sig, _sign('board:' + ym))) {
      return _json({ ok: false, error: 'ลายเซ็นไม่ถูกต้อง' });
    }
    var sh = _sheet();
    var last = sh.getLastRow();
    var byPerson = {}, totals = { searches: 0, found: 0, notfound: 0, error: 0,
                                  files: 0, amount_in: 0, amount_out: 0 };
    if (last >= 2) {
      var vals = sh.getRange(2, 1, last - 1, 14).getValues();
      for (var i = 0; i < vals.length; i++) {
        var v = vals[i];
        if (ym && String(v[3]) !== ym) continue;
        var key = String(v[1]) + '|' + String(v[6]);       // install_id | display_name
        var p = byPerson[key] || (byPerson[key] = {
          install_id: String(v[1]), display_name: String(v[6]),
          searches: 0, found: 0, notfound: 0, error: 0,
          files: 0, amount_in: 0, amount_out: 0
        });
        // v3.9.0: ยอดเงินไม่อ่านจากชีต counts อีกแล้ว (ดู _ledgerAmounts) — คอลัมน์ amount_* ในชีตนี้เป็นของรุ่นก่อน
        var f = ['searches', 'found', 'notfound', 'error', 'files'];
        var idx = [7, 8, 9, 10, 11];
        for (var k = 0; k < f.length; k++) {
          var n = Number(v[idx[k]]) || 0;
          p[f[k]] += n; totals[f[k]] += n;
        }
      }
    }
    var la = _ledgerAmounts(ym);
    Object.keys(la.byKey).forEach(function (key) {
      var a = la.byKey[key];
      var q = byPerson[key] || (byPerson[key] = {
        install_id: a.install_id, display_name: a.display_name,
        searches: 0, found: 0, notfound: 0, error: 0, files: 0, amount_in: 0, amount_out: 0
      });
      q.amount_in = a.amount_in; q.amount_out = a.amount_out;
    });
    totals.amount_in = la.totals.amount_in; totals.amount_out = la.totals.amount_out;
    var rows = Object.keys(byPerson).map(function (k) { return byPerson[k]; });
    rows.forEach(function (r) { r.net = Math.round((r.amount_in - r.amount_out) * 100) / 100; });
    rows.sort(function (a, b) { return b.searches - a.searches; });
    totals.net = Math.round((totals.amount_in - totals.amount_out) * 100) / 100;
    // v3.2.0: สถานะสมาชิกทุกเครื่อง
    var psh = _presenceSheet();
    var plast = psh.getLastRow();
    var presence = plast >= 2 ? psh.getRange(2, 1, plast - 1, 6).getValues().map(function (v) {
      var ra = v[0];
      return { received_at: (ra && ra.toISOString) ? ra.toISOString() : String(ra || ''),
               install_id: String(v[1]), uid: String(v[2]), display_name: String(v[3]),
               app_version: String(v[4]), last_seen: String(v[5]) };
    }) : [];
    presence.sort(function (a, b) { return (b.received_at > a.received_at) ? 1 : -1; });
    return _json({ ok: true, ym: ym, rows: rows, totals: totals, presence: presence });
  } catch (err) {
    return _json({ ok: false, error: String(err).slice(0, 200) });
  }
}
