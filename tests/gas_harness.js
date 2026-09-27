#!/usr/bin/env node
/**
 * รัน tools/hub_gas.js (สคริปต์ศูนย์กลางตัวจริง) นอก Google — จำลอง SpreadsheetApp/Utilities/LockService/ContentService
 * แผ่นงานเก็บในไฟล์ JSON (argv[2]) จึงเรียกซ้ำหลายครั้งได้เหมือนคุยกับ Sheet ใบเดิม (หลายเครื่องใช้ร่วมกัน)
 *
 *   echo '{"method":"POST","body":"...","parameter":{"sign":"..."}}' | node gas_harness.js state.json TOKEN
 *   → พิมพ์ JSON ที่ doPost/doGet ตอบ
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
  appendRow(vals) { this.rows.push(vals.slice()); }
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
const sandbox = {
  SpreadsheetApp: { getActiveSpreadsheet: () => ss },
  Utilities: {
    computeHmacSha256Signature: (text, key) => {
      const raw = crypto.createHmac('sha256', Buffer.from(String(key), 'utf8')).update(Buffer.from(String(text), 'utf8')).digest();
      return Array.from(raw).map(b => (b > 127 ? b - 256 : b));   // Apps Script คืน byte[] แบบมีเครื่องหมาย
    },
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
vm.runInContext(src, sandbox, { filename: 'hub_gas.js' });

const req = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
const e = { parameter: req.parameter || {}, postData: { contents: req.body || '' } };
const out = req.method === 'GET' ? sandbox.doGet(e) : sandbox.doPost(e);
state.sheets = {};
for (const [n, s] of Object.entries(sheets)) state.sheets[n] = s.toJSON();
fs.writeFileSync(stateFile, JSON.stringify(state));
process.stdout.write(out._s);
