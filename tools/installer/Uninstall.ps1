<#
  Uninstall.ps1 — ถอนการติดตั้ง CRIMES AUTO แบบถอนรากถอนโคน
  ลบ: โปรแกรม · Python runtime · Chromium · ฐานข้อมูล/บัญชี/ประวัติ/ไฟล์อัปโหลด · แคชหน้าต่างโปรแกรม (webview-data ในโฟลเดอร์ติดตั้ง)
       · ทางลัด · รายการใน Add/Remove Programs · โปรไฟล์ Chrome ของโปรแกรม (%USERPROFILE%\.crimes_auto_profile) · ไฟล์ชั่วคราวจากการอัปเดต
  -Silent   = ไม่ถามยืนยัน (ใช้จาก Add/Remove Programs แบบเงียบ)
  -KeepData = สำรองฐานข้อมูล/ไฟล์อัปโหลดไว้ที่เดสก์ท็อปก่อนลบ — สำรองไม่สำเร็จ = ยกเลิกทั้งหมด ไม่ลบอะไร

  สร้างโดย tools/build_installer.py — แก้ต้นฉบับที่ tools/installer/Uninstall.ps1 เท่านั้น
#>
param([switch]$Silent, [switch]$KeepData)
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$Install = Join-Path $env:LOCALAPPDATA "CRIMES-AUTO"
$AppName = "CRIMES AUTO"
function Finish($code) { if (-not $Silent) { Read-Host "กด Enter เพื่อปิด" | Out-Null }; exit $code }

Write-Host ""
Write-Host "============================================"
Write-Host "   ถอนการติดตั้ง $AppName (ลบทั้งหมด)"
Write-Host "============================================"
Write-Host "จะลบ: โปรแกรม · Python runtime · Chromium · ฐานข้อมูล บัญชี ประวัติ ไฟล์อัปโหลด"
Write-Host "       · ทางลัด · รายการใน Add/Remove Programs · โปรไฟล์ Chrome ของโปรแกรม · ไฟล์ชั่วคราวจากการอัปเดต"
Write-Host "ตำแหน่ง: $Install"
Write-Host ""
$legacy = "C:\Crimes-Automate"
$hasLegacy = (Test-Path (Join-Path $legacy "app\backend\server.py"))
if (-not $Silent) {
    $ans = Read-Host "พิมพ์ YES (ตัวใหญ่) เพื่อยืนยันการลบทั้งหมด"
    if ($ans -ne "YES") { Write-Host "ยกเลิก — ไม่มีอะไรถูกลบ"; Finish 0 }
    if (-not $KeepData -and (Test-Path (Join-Path $Install "app\backend\data\data.db"))) {
        $k = Read-Host "สำรองฐานข้อมูล (บัญชี/ประวัติ) และไฟล์อัปโหลดไว้ที่เดสก์ท็อปก่อนลบไหม? (Y/N)"
        if ($k -match '^[Yy]') { $KeepData = $true }
    }
    if ($hasLegacy) {
        $l = Read-Host "พบการติดตั้งแบบเก่าที่ $legacy — ลบด้วยไหม? (Y/N)"
        if ($l -notmatch '^[Yy]') { $hasLegacy = $false }
    }
} else { $hasLegacy = $false }

# ---- ปิดโปรแกรมที่กำลังทำงาน ----
Write-Host "  - ปิดโปรแกรมที่กำลังทำงาน (ถ้ามี)..."
try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        (($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and ($_.CommandLine -match 'CRIMES-AUTO' -or $_.CommandLine -match 'Crimes-Automate')) -or
        ($_.Name -eq 'chrome.exe' -and $_.CommandLine -match 'crimes_auto_profile') -or
        ($_.Name -eq 'msedgewebview2.exe' -and $_.CommandLine -match 'CRIMES-AUTO')
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Milliseconds 1500

# ---- สำรองข้อมูล (ถ้าขอ) — สำรองไม่สำเร็จ = หยุดทันที ห้ามลบอะไรทั้งสิ้น (ดิสก์เต็ม/สิทธิ์ไม่พอ ไม่ใช่เหตุให้ข้อมูลหาย) ----
if ($KeepData) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dst = Join-Path ([Environment]::GetFolderPath("Desktop")) ("CRIMES-AUTO-backup-" + $stamp)
    $backupOk = $true
    foreach ($sub in @("app\backend\data", "app\backend\uploads")) {
        $src = Join-Path $Install $sub
        if (-not (Test-Path $src)) { continue }
        $to = Join-Path $dst (Split-Path $sub -Leaf)
        robocopy $src $to /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP > $null
        $rc = $LASTEXITCODE
        if ($rc -ge 8) { Write-Host "  ! สำรอง $sub ไม่สำเร็จ (robocopy code $rc)" -ForegroundColor Red; $backupOk = $false }
    }
    $dbSrc = Join-Path $Install "app\backend\data\data.db"
    $dbDst = Join-Path $dst "data\data.db"
    if ((Test-Path $dbSrc) -and (-not (Test-Path $dbDst) -or ((Get-Item $dbSrc).Length -ne (Get-Item $dbDst).Length))) {
        Write-Host "  ! สำเนา data.db ไม่ครบ" -ForegroundColor Red; $backupOk = $false
    }
    if (-not $backupOk) {
        Write-Host "[X] สำรองข้อมูลไม่สำเร็จ — ยกเลิกการถอนการติดตั้ง ไม่มีอะไรถูกลบ (ตรวจพื้นที่ดิสก์/สิทธิ์ที่เดสก์ท็อป แล้วลองใหม่)" -ForegroundColor Red
        Finish 1
    }
    Write-Host "  - สำรองข้อมูลไว้ที่: $dst"
}

# ---- ทางลัด + รายการใน Add/Remove Programs ----
Write-Host "  - ลบทางลัดและรายการใน Add/Remove Programs..."
$desk = [Environment]::GetFolderPath("Desktop")
$startDir = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
foreach ($p in @((Join-Path $desk "$AppName.lnk"), $startDir,
                 (Join-Path ([Environment]::GetFolderPath("Programs")) "$AppName.lnk"))) {
    if (Test-Path $p) { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue }
}
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CRIMES-AUTO" -Recurse -Force -ErrorAction SilentlyContinue

# ---- ลบโฟลเดอร์ (ลองซ้ำ กันไฟล์ถูกล็อกชั่วคราว) — ออกจากโฟลเดอร์ก่อน เพราะสคริปต์นี้อยู่ข้างในนั้น ----
Set-Location $env:TEMP
function Remove-Tree($p) {
    if (-not (Test-Path -LiteralPath $p)) { return }
    for ($i = 1; $i -le 3; $i++) {
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $p)) { Write-Host "  - ลบแล้ว: $p"; return }
        Start-Sleep -Seconds 2
    }
    Write-Host "  ! ลบไม่หมด: $p (ปิดโปรแกรมที่ค้างอยู่ แล้วลบโฟลเดอร์นี้เองได้)" -ForegroundColor Yellow
}
# แคชหน้าต่างโปรแกรม (WebView2) อยู่ที่ $Install\webview-data ตั้งแต่ v3.8.0 — หายไปพร้อมโฟลเดอร์ติดตั้ง
# (ไม่แตะ %LOCALAPPDATA%\pywebview ซึ่งเป็นที่เก็บกลางที่โปรแกรม pywebview อื่นบนเครื่องอาจใช้ร่วมกัน)
Remove-Tree $Install
Remove-Tree (Join-Path $env:USERPROFILE ".crimes_auto_profile")
Get-ChildItem $env:TEMP -Directory -Filter "crimes_upd_*" -ErrorAction SilentlyContinue | ForEach-Object { Remove-Tree $_.FullName }
Get-ChildItem $env:TEMP -Directory -Filter "crimes_test_*" -ErrorAction SilentlyContinue | ForEach-Object { Remove-Tree $_.FullName }
Remove-Item (Join-Path $env:TEMP "CRIMES-AUTO-install.log") -Force -ErrorAction SilentlyContinue
if ($hasLegacy) { Remove-Tree $legacy }

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "   [OK] ถอนการติดตั้ง $AppName เรียบร้อย" -ForegroundColor Green
if ($KeepData) { Write-Host "   สำเนาข้อมูลอยู่บนเดสก์ท็อป (โฟลเดอร์ CRIMES-AUTO-backup-…)" -ForegroundColor Green }
Write-Host "============================================" -ForegroundColor Green
Finish 0
