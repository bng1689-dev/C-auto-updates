/**
 * CRIMES AUTO — ศูนย์กลางรวมตัวเลข (Google Apps Script)
 *
 * รับ "ตัวเลขนับ" จากเครื่องลูกแต่ละเครื่องมาเก็บใน Google Sheet
 * ไม่มีข้อมูลประวัติ เลขบัตร ชื่อผู้ถูกค้น ผลคดี หรือชื่อไฟล์งาน ส่งมาที่นี่
 *
 * v3.2.0: เพิ่มชีต 'presence' — ใครใช้เวอร์ชันไหน/เห็นล่าสุดเมื่อไร (ชื่อที่แสดง · uid ·
 * เวอร์ชัน · เวลา) เพื่อให้ผู้ดูแลเห็นสมาชิกทุกเครื่องแบบเรียลไทม์ · โปรแกรมส่งก้อน
 * kind="presence" (ไม่มี rows) บ่อยกว่าก้อนตัวเลข — ก้อนนี้ต้องไม่ลบตัวเลขเดือนที่เก็บไว้
 * ** ต้อง Deploy ใหม่ (New deployment) หลังวางโค้ดรุ่นนี้ ไม่งั้นเครื่องลูกยังคุยกับโค้ดเก่า **
 *
 * ── วิธีติดตั้ง ────────────────────────────────────────────────
 * 1. สร้าง Google Sheet ใหม่ 1 ไฟล์ (จะใช้เก็บข้อมูล)
 * 2. เมนู Extensions → Apps Script  แล้ววางโค้ดนี้ทับทั้งหมด
 * 3. แก้ HUB_TOKEN ข้างล่างเป็นรหัสลับของคุณเอง (สุ่มยาว ๆ อย่างน้อย 32 ตัว)
 * 4. กด Deploy → New deployment → เลือกชนิด "Web app"
 *      - Execute as        : Me
 *      - Who has access    : Anyone
 *    (ต้องเป็น Anyone เพราะโปรแกรมในเครื่องไม่ได้ล็อกอิน Google — ความปลอดภัย
 *     มาจากลายเซ็น HMAC ที่ตรวจในโค้ดนี้ ไม่ใช่จากการล็อกอิน)
 * 5. คัดลอก URL ที่ลงท้ายด้วย /exec ไปใส่ในโปรแกรมที่
 *      Setting → ศูนย์กลางรวมตัวเลข → URL   และใส่ HUB_TOKEN เดียวกันในช่องรหัสลับ
 *
 * ── ข้อควรรู้ ─────────────────────────────────────────────────
 * รหัสลับนี้ใช้ยืนยันว่า "ข้อมูลมาจากเครื่องขององค์กร" เท่านั้น
 * เครื่องลูกทุกเครื่องใช้รหัสเดียวกัน ผู้ใช้ที่เปิดไฟล์ config.json ในเครื่องตัวเองจะเห็นรหัสนี้
 * จึงกันคนนอกได้ แต่ไม่ได้กันคนในที่ตั้งใจส่งตัวเลขปลอมของตัวเอง
 * ถ้าต้องการกันกรณีนั้น ให้ดูคอลัมน์ install_id ในชีตประกอบเสมอ
 */

var HUB_TOKEN = 'เปลี่ยนรหัสนี้ก่อนใช้งานจริง';
var SHEET_NAME = 'counts';
var PRESENCE_SHEET = 'presence';

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
  var byKey = {};
  vals.forEach(function (v) { byKey[String(v[1]) + '|' + String(v[2])] = v; });
  users.forEach(function (u) {
    byKey[String(installId) + '|' + String(u.uid)] =
      [now, String(installId), String(u.uid), String(u.display_name || ''),
       String(u.app_version || appVersion || ''), String(u.last_seen || '')];
  });
  var out = Object.keys(byKey).map(function (k) { return byKey[k]; });
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

function _sign(text) {
  var raw = Utilities.computeHmacSha256Signature(text, HUB_TOKEN);
  return raw.map(function (b) {
    return ('0' + (b & 0xff).toString(16)).slice(-2);
  }).join('');
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

/** รับข้อมูลจากเครื่องลูก */
function doPost(e) {
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
                  r.display_name, r.searches, r.found, r.notfound, r.error,
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
        var f = ['searches', 'found', 'notfound', 'error', 'files', 'amount_in', 'amount_out'];
        var idx = [7, 8, 9, 10, 11, 12, 13];
        for (var k = 0; k < f.length; k++) {
          var n = Number(v[idx[k]]) || 0;
          p[f[k]] += n; totals[f[k]] += n;
        }
      }
    }
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
