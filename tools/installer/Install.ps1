<#
  Install.ps1 — ติดตั้ง/อัปเกรด CRIMES AUTO ตัวเต็ม (Python runtime + Chromium + โปรแกรม) ลง %LOCALAPPDATA%\CRIMES-AUTO
  เรียกผ่าน ติดตั้ง.bat (ดับเบิลคลิก) · ต้องใส่ "รหัสเริ่มติดตั้ง" — ตรวจด้วยแฮช PBKDF2-SHA256 ใน install.json
  (ในชุดติดตั้งไม่มีรหัสจริงอยู่ที่ไหนเลย มีแต่แฮช) · ไม่ต้องใช้สิทธิ์ผู้ดูแลเครื่อง (ติดตั้งในโปรไฟล์ผู้ใช้)

  ติดตั้งแบบไม่ถามอะไรเลย (สำหรับติดตั้งหลายเครื่อง):
      powershell -NoProfile -ExecutionPolicy Bypass -File Install.ps1 -Password <รหัสเริ่มติดตั้ง> -Silent
  ตัวเลือก: -NoShortcut (ไม่สร้างทางลัด) · -NoLaunch (ไม่เปิดโปรแกรมหลังติดตั้ง)

  สร้างโดย tools/build_installer.py — แก้ต้นฉบับที่ tools/installer/Install.ps1 เท่านั้น
#>
param(
    [string]$Password = "",
    [switch]$Silent,
    [switch]$NoShortcut,
    [switch]$NoLaunch
)
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$Src = $PSScriptRoot
$Install = Join-Path $env:LOCALAPPDATA "CRIMES-AUTO"
$AppName = "CRIMES AUTO"
$LogFile = Join-Path $env:TEMP "CRIMES-AUTO-install.log"

function Log($m) {
    Write-Host $m
    try { Add-Content -Path $LogFile -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8 } catch {}
}
function Finish($code) { if (-not $Silent) { Read-Host "กด Enter เพื่อปิด" | Out-Null }; exit $code }
function Fail($m) {
    Write-Host "[X] $m" -ForegroundColor Red
    try { Add-Content -Path $LogFile -Value ("[X] " + $m) -Encoding UTF8 } catch {}
    Finish 1
}

Write-Host ""
Write-Host "============================================"
Write-Host "   ติดตั้ง $AppName"
Write-Host "============================================"

# ---- ตรวจชุดติดตั้งว่าครบ ----
$metaPath = Join-Path $Src "install.json"
if (-not (Test-Path $metaPath)) { Fail "ไม่พบ install.json — ชุดติดตั้งไม่สมบูรณ์ (แตก zip ให้ครบก่อน แล้วรันจากโฟลเดอร์ที่แตกแล้ว)" }
try { $Meta = Get-Content $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Fail "install.json อ่านไม่ได้: $($_.Exception.Message)" }
foreach ($need in @("app\VERSION", "app\desktop.py", "app\backend\server.py", "runtime\pythonw.exe", "runtime\python.exe", "browsers")) {
    if (-not (Test-Path (Join-Path $Src $need))) { Fail "ชุดติดตั้งไม่ครบ: ไม่พบ $need (แตก zip ให้ครบก่อนติดตั้ง)" }
}
$newVer = (Get-Content (Join-Path $Src "app\VERSION") -Raw).Trim()
$curVer = ""
if (Test-Path (Join-Path $Install "app\VERSION")) { $curVer = (Get-Content (Join-Path $Install "app\VERSION") -Raw).Trim() }
if ($curVer) { Write-Host ("พบโปรแกรมเดิมเวอร์ชัน {0} → จะอัปเกรดเป็น {1} (เก็บบัญชี/ประวัติ/การตั้งค่าเดิมไว้ครบ)" -f $curVer, $newVer) }
else { Write-Host ("ติดตั้งใหม่ เวอร์ชัน {0} → {1}" -f $newVer, $Install) }
Write-Host ""

# ---- รหัสเริ่มติดตั้ง: PBKDF2-SHA256 เทียบกับแฮชใน install.json เท่านั้น ----
function ConvertFrom-Hex([string]$hex) {
    $b = New-Object byte[] ($hex.Length / 2)
    for ($i = 0; $i -lt $b.Length; $i++) { $b[$i] = [Convert]::ToByte($hex.Substring($i * 2, 2), 16) }
    return ,$b
}
function Test-GatePassword([string]$pw) {
    if (-not $pw) { return $false }
    $salt = ConvertFrom-Hex ([string]$Meta.gate.salt)
    $pwBytes = [System.Text.Encoding]::UTF8.GetBytes($pw)
    $iter = [int]$Meta.gate.iterations
    $kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($pwBytes, $salt, $iter, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    try { $got = ($kdf.GetBytes(32) | ForEach-Object { $_.ToString("x2") }) -join "" } finally { $kdf.Dispose() }
    return ($got -eq ([string]$Meta.gate.hash).ToLower())
}
function Read-Secret($prompt) {
    $s = Read-Host -Prompt $prompt -AsSecureString
    $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}
$ok = $false
if ($Password) { $ok = Test-GatePassword $Password }
elseif ($Silent) { Fail "โหมด -Silent ต้องระบุ -Password <รหัสเริ่มติดตั้ง>" }
else {
    for ($try = 1; $try -le 3; $try++) {
        $pw = Read-Secret "รหัสเริ่มติดตั้ง (ครั้งที่ $try/3)"
        $ok = Test-GatePassword $pw
        if ($ok) { break }
        Write-Host "   รหัสไม่ถูกต้อง" -ForegroundColor Yellow
    }
}
if (-not $ok) { Fail "รหัสเริ่มติดตั้งไม่ถูกต้อง — ยกเลิกการติดตั้ง" }
Log "รหัสเริ่มติดตั้งถูกต้อง · ติดตั้ง v$newVer (เดิม: '$curVer') → $Install"

# ---- ปิดโปรแกรมที่กำลังทำงาน (กันไฟล์ถูกล็อก) ----
Write-Host "  - ปิดโปรแกรมที่กำลังทำงาน (ถ้ามี)..."
try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        (($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -match 'CRIMES-AUTO') -or
        ($_.Name -eq 'chrome.exe' -and $_.CommandLine -match 'crimes_auto_profile') -or
        ($_.Name -eq 'msedgewebview2.exe' -and $_.CommandLine -match 'CRIMES-AUTO')
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Milliseconds 1500

# ---- สำรองฐานข้อมูลเดิม (ถ้ามี) ----
New-Item -ItemType Directory -Force -Path $Install | Out-Null
$dataDir = Join-Path $Install "app\backend\data"
$freshInstall = -not (Test-Path (Join-Path $dataDir "data.db"))
if (-not $freshInstall) {
    $bk = Join-Path $dataDir ("data.backup-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
    Copy-Item (Join-Path $dataDir "data.db") $bk -Force -ErrorAction SilentlyContinue
    Write-Host "  - สำรองฐานข้อมูลไว้: $(Split-Path $bk -Leaf)"
}

# ---- runtime\ และ browsers\ : แทนที่ทั้งชุด (/MIR — ของเก่าที่ไม่อยู่ในชุดนี้ถูกลบ · สองโฟลเดอร์นี้ไม่มีข้อมูลผู้ใช้) ----
function Copy-Tree($sub, $mirror) {
    Write-Host "  - ติดตั้ง $sub\ ..."
    $flag = "/E"
    if ($mirror) { $flag = "/MIR" }
    robocopy (Join-Path $Src $sub) (Join-Path $Install $sub) $flag /XD "__pycache__" /XF "*.pyc" /R:2 /W:2 /NFL /NDL /NJH /NJS /NP > $null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) { Fail "ก๊อปปี้ $sub ล้มเหลว (robocopy code $rc) — ปิดโปรแกรมที่ค้างแล้วลองใหม่" }
}
Copy-Tree "runtime" $true
Copy-Tree "browsers" $true

# ---- app\ : ก๊อปทับ โดยไม่แตะ data\ และ uploads\ (บัญชี/ประวัติ/ไฟล์งานของเครื่องนี้) ----
Write-Host "  - ติดตั้ง app\ (เก็บ data\ และ uploads\ เดิม)..."
$xd = @((Join-Path $Src "app\backend\data"), (Join-Path $Src "app\backend\uploads"), $dataDir, (Join-Path $Install "app\backend\uploads"), "__pycache__")
robocopy (Join-Path $Src "app") (Join-Path $Install "app") /E /XD @xd /XF "*.pyc" /R:2 /W:2 /NFL /NDL /NJH /NJS /NP > $null
$rc = $LASTEXITCODE
if ($rc -ge 8) { Fail "ก๊อปปี้ app ล้มเหลว (robocopy code $rc) — ปิดโปรแกรมที่ค้างแล้วลองใหม่" }

# ---- ลบไฟล์ที่รุ่นนี้เลิกใช้ (app\OBSOLETE.txt) + แคช .pyc เก่า + ของเหลือจากชุดติดตั้งรุ่นก่อน ----
$obs = Join-Path $Src "app\OBSOLETE.txt"
if (Test-Path $obs) {
    Get-Content $obs -Encoding UTF8 | ForEach-Object {
        $rel = $_.Trim()
        if ($rel -and -not $rel.StartsWith("#") -and $rel -notmatch '\.\.' -and $rel -notmatch '^(backend[\\/])?(data|uploads)([\\/]|$)') {
            $t = Join-Path (Join-Path $Install "app") $rel
            if (Test-Path $t -PathType Leaf) { Remove-Item $t -Force -ErrorAction SilentlyContinue; Write-Host "  - ลบไฟล์ที่เลิกใช้: $rel" }
        }
    }
}
Get-ChildItem (Join-Path $Install "app") -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
foreach ($old in @("build.ps1", "CRIMES-AUTO-cert.cer", "เชื่อถือใบรับรอง.bat", "ติดตั้งลงเครื่อง.bat")) {
    $p = Join-Path $Install $old
    if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue }
}

# ---- บัญชีเริ่มต้น (เฉพาะติดตั้งใหม่ที่ยังไม่มีฐานข้อมูล) — ไฟล์มีแค่แฮช โปรแกรมใช้แล้วลบทันทีตอนเปิดครั้งแรก ----
$seedSrc = Join-Path $Src "seed_account.json"
$seedDst = Join-Path $Install "app\backend\seed_account.json"
if ((Test-Path $seedSrc) -and $freshInstall) {
    New-Item -ItemType Directory -Force -Path (Split-Path $seedDst) | Out-Null
    Copy-Item $seedSrc $seedDst -Force
    Write-Host ("  - เตรียมบัญชีเริ่มต้น '{0}' (เข้าครั้งแรกแล้วเปลี่ยนรหัสผ่านทันที)" -f $Meta.seed_username)
} elseif (Test-Path $seedDst) {
    Remove-Item $seedDst -Force -ErrorAction SilentlyContinue
}

# ---- ไฟล์ประกอบ: ไอคอน · ตัวถอนการติดตั้ง · ข้อมูลการติดตั้ง ----
foreach ($f in @("icon.ico", "Uninstall.ps1", "ถอนการติดตั้ง.bat", "Uninstall.bat", "install.json")) {
    $p = Join-Path $Src $f
    if (Test-Path $p) { Copy-Item $p (Join-Path $Install $f) -Force }
}
@{ version = $newVer; installed_at = (Get-Date -Format "s"); previous = $curVer; source = $Src } |
    ConvertTo-Json | Set-Content (Join-Path $Install "install-info.json") -Encoding UTF8

# ---- ทางลัด + รายการใน Add/Remove Programs (Settings → Apps) ----
$exe = Join-Path $Install "runtime\pythonw.exe"
$script = Join-Path $Install "app\desktop.py"
$icon = Join-Path $Install "icon.ico"
$uninst = Join-Path $Install "Uninstall.ps1"
if (-not $NoShortcut) {
    try {
        $ws = New-Object -ComObject WScript.Shell
        $desk = [Environment]::GetFolderPath("Desktop")
        $startDir = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
        New-Item -ItemType Directory -Force -Path $startDir | Out-Null
        foreach ($lnk in @((Join-Path $desk "$AppName.lnk"), (Join-Path $startDir "$AppName.lnk"))) {
            $s = $ws.CreateShortcut($lnk)
            $s.TargetPath = $exe
            $s.Arguments = ('"{0}"' -f $script)
            $s.WorkingDirectory = (Join-Path $Install "app")
            if (Test-Path $icon) { $s.IconLocation = $icon }
            $s.Description = "$AppName v$newVer"
            $s.Save()
        }
        $u = $ws.CreateShortcut((Join-Path $startDir "ถอนการติดตั้ง $AppName.lnk"))
        $u.TargetPath = "powershell.exe"
        $u.Arguments = ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $uninst)
        $u.WorkingDirectory = $Install
        $u.Description = "ถอนการติดตั้ง $AppName ทั้งหมด"
        $u.Save()
        Write-Host "  - สร้างทางลัดบนเดสก์ท็อปและ Start Menu แล้ว"
    } catch { Write-Host "  ! สร้างทางลัดไม่ได้: $($_.Exception.Message)" -ForegroundColor Yellow }
}
try {
    $reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CRIMES-AUTO"
    New-Item -Path $reg -Force | Out-Null
    $size = [int]((Get-ChildItem $Install -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1KB)
    New-ItemProperty -Path $reg -Name DisplayName -Value $AppName -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name DisplayVersion -Value $newVer -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name Publisher -Value $AppName -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name InstallLocation -Value $Install -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name InstallDate -Value (Get-Date -Format "yyyyMMdd") -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name DisplayIcon -Value $icon -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name UninstallString -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $uninst) -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name QuietUninstallString -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Silent' -f $uninst) -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $reg -Name EstimatedSize -Value $size -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $reg -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $reg -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
} catch { Write-Host "  ! ลงทะเบียนใน Add/Remove Programs ไม่ได้: $($_.Exception.Message)" -ForegroundColor Yellow }

# ---- ตรวจว่า runtime ที่ติดตั้งใช้ได้จริง ----
Write-Host "  - ตรวจ runtime..."
$chk = & (Join-Path $Install "runtime\python.exe") -c "import flask, waitress, webview, playwright, openpyxl; print('runtime-ok')" 2>&1
if ("$chk" -notmatch "runtime-ok") { Fail "runtime ทดสอบไม่ผ่าน: $chk" }

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host ("   [OK] ติดตั้ง {0} เวอร์ชัน {1} สำเร็จ" -f $AppName, $newVer) -ForegroundColor Green
if ($freshInstall) {
    Write-Host ("   เข้าใช้งานครั้งแรกด้วยบัญชี '{0}' (รหัสผ่านตามที่ผู้ดูแลแจ้ง) แล้วเปลี่ยนรหัสผ่านทันที" -f $Meta.seed_username) -ForegroundColor Green
} else {
    Write-Host "   บัญชี/ประวัติ/การตั้งค่าเดิมยังอยู่ครบ" -ForegroundColor Green
}
Write-Host "   ถอนการติดตั้ง: Start Menu → CRIMES AUTO → ถอนการติดตั้ง · หรือ Settings → Apps" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Log "ติดตั้งสำเร็จ v$newVer"
if (-not $NoLaunch -and -not $Silent) {
    Start-Process -FilePath $exe -ArgumentList ('"{0}"' -f $script) -WorkingDirectory (Join-Path $Install "app")
    Write-Host "   กำลังเปิดโปรแกรม..."
}
Finish 0
