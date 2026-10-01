#!/usr/bin/env node
/**
 * รัน tools/hub_gas.js (สคริปต์ศูนย์กลางตัวจริง) นอก Google — จำลอง SpreadsheetApp/Utilities/LockService/ContentService
 * แผ่นงานเก็บในไฟล์ JSON (argv[2]) จึงเรียกซ้ำหลายครั้งได้เหมือนคุยกับ Sheet ใบเดิม (หลายเครื่องใช้ร่วมกัน)
 *
 *   echo '{"method":"POST","body":"...","parameter":{"sign":"...","asign":"..."}}' | node gas_harness.js state.json TOKEN [ADMIN_TOKEN]
 *   → พิมพ์ JSON ที่ doPost/doGet ตอบ   (ไม่ให้ ADMIN_TOKEN = สคริปต์ยังใช้ค่าตั้งต้น → ไม่รับลายเซ็นผู้ดูแล)
 *
 * ใช้เฉพาะในชุดทดสอบ (tests/test_v370.py) — ไม่ได้ส่งไปกับแพ็กเกจ
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const crypto = require('crypto');
const path = require('path');

const stateFile = process.argv[2];
const token = process.argv[3] || 'test-token';
const adminToken = process.argv[4] || '';
// ล็อกไฟล์แทน LockService ของ Google — หลายเครื่อง (หลายโปรเซส) เรียกพร้อมกันต้องอ่าน-เขียน Sheet ทีละคน
const lockPath = stateFile + '.lock';
const t0 = Date.now();
for (;;) {
  try { fs.writeFileSync(lockPath, String(process.pid), { flag: 'wx' }); break; }
  catch (e) {
    if (Date.now() - t0 > 20000) { console.error('gas_harness: lock timeout'); process.exit(2); }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 25);
  }
}
process.on('exit', () => { try { fs.unlinkSync(lockPath); } catch (e) { /* ignore */ } });
let state = { sheets: {} };
try { state = JSON.parse(fs.readFileSync(stateFile, 'utf8')); } catch (e) { /* ยังไม่มีไฟล์ = Sheet ว่าง */ }

class Range {
  constructor(sheet, row, col, rows, cols) { Object.assign(this, { sheet, row, col, rows, cols }); }
  getValues() {
    const out = [];
    for (let r = 0; r < this.rows; r++) {
      const line = this.sheet.rows[this.row - 1 + r] || [];
      const vals = [];
      for (let c = 0; c < this.cols; c++) vals.push(line[this.col - 1 + c] === undefined ? '' : line[this.col - 1 + c]);
      out.push(vals);
    }
    return out;
  }
  setValues(vals) {
    for (let r = 0; r < vals.length; r++) {
      const idx = this.row - 1 + r;
      while (this.sheet.rows.length <= idx) this.sheet.rows.push([]);
      const line = this.sheet.rows[idx];
      for (let c = 0; c < vals[r].length; c++) {
        let v = vals[r][c];
        // Google Sheets: ค่าข้อความที่ขึ้นต้นด้วย ' = บังคับเป็นข้อความ และไม่เก็บตัว ' ไว้
        if (typeof v === 'string' && v.startsWith("'")) v = v.slice(1);
        line[this.col - 1 + c] = v;
      }
    }
  }
  clearContent() {
    for (let r = 0; r < this.rows; r++) {
      const idx = this.row - 1 + r;
      if (this.sheet.rows[idx]) for (let c = 0; c < this.cols; c++) this.sheet.rows[idx][this.col - 1 + c] = '';
    }
    // แถวว่างท้ายแผ่นไม่นับเป็น 'แถวที่มีข้อมูล' เหมือน Sheet จริง
    while (this.sheet.rows.length && this.sheet.rows[this.sheet.rows.length - 1].every(x => x === '' || x === undefined)) this.sheet.rows.pop();
  }
}
class Sheet {
  constructor(name, data) { this.name = name; this.rows = data.rows || []; this.frozen = data.frozen || 0; }
  appendRow(vals) {
    // Google Sheets: ' นำหน้า = บังคับข้อความ และไม่เก็บตัว ' ไว้ (เหมือน setValues ข้างบน)
    this.rows.push(vals.map(v => (typeof v === 'string' && v.startsWith("'")) ? v.slice(1) : v));
  }
  setFrozenRows(n) { this.frozen = n; }
  getLastRow() { return this.rows.length; }
  getLastColumn() { return this.rows.reduce((m, r) => Math.max(m, r.length), 0); }
  getRange(row, col, rows, cols) { return new Range(this, row, col, rows, cols); }
  toJSON() { return { rows: this.rows, frozen: this.frozen }; }
}
const sheets = {};
for (const [n, d] of Object.entries(state.sheets || {})) sheets[n] = new Sheet(n, d);
const ss = {
  getSheetByName: n => sheets[n] || null,
  insertSheet: n => { sheets[n] = new Sheet(n, {}); return sheets[n]; },
};

// v3.11.0: Drive จำลอง — โฟลเดอร์/ไฟล์เก็บใน state (ไฟล์เก็บเฉพาะ ชื่อ·ขนาด·sha256 พอให้เทสต์ตรวจ ไม่เก็บเนื้อ)
const drive = state.drive || (state.drive = { seq: 0, folders: {} });
function driveFolder(id) {
  const f = drive.folders[id];
  return {
    getId: () => id,
    getName: () => f.name,
    getUrl: () => 'https://drive.google.com/drive/folders/' + id,
    isTrashed: () => false,
    createFile: (blob) => {
      const bytes = Buffer.from((blob.getBytes() || []).map(b => b & 0xff));
      const file = { id: 'file' + (++drive.seq), name: blob.getName() || 'file',
                     size: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
      f.files.push(file);
      return { getId: () => file.id, getName: () => file.name, getSize: () => file.size,
               getUrl: () => 'https://drive.google.com/file/d/' + file.id };
    },
  };
}
const DriveApp = {
  getFolderById: (id) => {
    if (!drive.folders[id]) throw new Error('harness: ไม่พบโฟลเดอร์ ' + id);
    return driveFolder(id);
  },
  getFoldersByName: (name) => {
    const ids = Object.keys(drive.folders).filter(i => drive.folders[i].name === String(name));
    let i = 0;
    return { hasNext: () => i < ids.length, next: () => driveFolder(ids[i++]) };
  },
  createFolder: (name) => {
    const id = 'fld' + (++drive.seq);
    drive.folders[id] = { name: String(name), files: [] };
    return driveFolder(id);
  },
};
const sandbox = {
  SpreadsheetApp: { getActiveSpreadsheet: () => ss },
  DriveApp,
  Utilities: {
    // v3.10.2: เลียนข้อจำกัดจริงของ Apps Script — ตัวแปรแบบ "สตริง" เพี้ยนกับอักขระนอก ASCII (เคยทำให้ตัวจำลองนี้
    // เขียวทั้งที่ของจริงตอบ 'ลายเซ็นไม่ถูกต้อง') → สตริงนอก ASCII = โยนทิ้งให้เทสต์ตกดัง ๆ · ทางที่ถูกคือส่ง byte[]
    computeHmacSha256Signature: (value, key) => {
      const toBuf = (v, what) => {
        if (Array.isArray(v)) return Buffer.from(v.map(b => b & 0xff));           // byte[] (จาก newBlob().getBytes())
        const s = String(v);
        if (/[^\x00-\x7F]/.test(s)) {
          throw new Error('harness: HMAC แบบสตริงของ Apps Script เพี้ยนกับอักขระนอก ASCII (' + what +
                          ') — สคริปต์ต้องใช้ Utilities.newBlob(...).getBytes() และโปรแกรมต้องส่งก้อน ASCII ล้วน');
        }
        return Buffer.from(s, 'utf8');
      };
      const raw = crypto.createHmac('sha256', toBuf(key, 'key')).update(toBuf(value, 'value')).digest();
      return Array.from(raw).map(b => (b > 127 ? b - 256 : b));   // Apps Script คืน byte[] แบบมีเครื่องหมาย
    },
    // v3.11.0: newBlob รับได้ทั้งข้อความ (เซ็นลายเซ็น) และ byte[]+ชนิด+ชื่อ (ไฟล์อัปโหลดขึ้นไดรฟ์)
    newBlob: (data, contentType, name) => ({
      getBytes: () => Array.isArray(data)
        ? data.map(b => (b > 127 ? b - 256 : b))
        : Array.from(Buffer.from(String(data), 'utf8')).map(b => (b > 127 ? b - 256 : b)),
      getContentType: () => contentType || '',
      getName: () => name || '',
    }),
    base64Decode: (s) => Array.from(Buffer.from(String(s), 'base64')).map(b => (b > 127 ? b - 256 : b)),
  },
  LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
  ContentService: {
    MimeType: { JSON: 'json' },
    createTextOutput: s => ({ _s: s, setMimeType() { return this; } }),
  },
  JSON, Date, Array, Object, Number, String, Math, isNaN, console,
};
vm.createContext(sandbox);
let src = fs.readFileSync(path.join(__dirname, '..', 'tools', 'hub_gas.js'), 'utf8');
src = src.replace(/var HUB_TOKEN = '[^']*';/, "var HUB_TOKEN = " + JSON.stringify(token) + ";");
if (adminToken) src = src.replace(/var ADMIN_TOKEN = '[^']*';/, "var ADMIN_TOKEN = " + JSON.stringify(adminToken) + ";");
vm.runInContext(src, sandbox, { filename: 'hub_gas.js' });

const req = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
const e = { parameter: req.parameter || {}, postData: { contents: req.body || '' } };
const out = req.method === 'GET' ? sandbox.doGet(e) : sandbox.doPost(e);
state.sheets = {};
for (const [n, s] of Object.entries(sheets)) state.sheets[n] = s.toJSON();
fs.writeFileSync(stateFile, JSON.stringify(state));
process.stdout.write(out._s);
