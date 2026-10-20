<#
  Build a ready-to-run APVIS for Windows folder: dist\APVIS (Python runtime + APVIS).
  The runtime is copied from a Python 3.12 folder that already has PySide6 and psutil
  (on Lucky's PC: E:\APVIS-OS-Builds\qt-dev\py312\tools). Nothing is downloaded.

  usage:  powershell -ExecutionPolicy Bypass -File scripts\build-package.ps1 [-Python <folder with python.exe>]
#>
param([string]$Python = "E:\APVIS-OS-Builds\qt-dev\py312\tools")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist\APVIS"
if (-not (Test-Path (Join-Path $Python "pythonw.exe"))) { throw "No pythonw.exe in $Python" }
& (Join-Path $Python "python.exe") -c "import PySide6, psutil"
if ($LASTEXITCODE -ne 0) { throw "That Python needs PySide6 and psutil" }
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
New-Item -ItemType Directory -Force $dist | Out-Null
Write-Host "Copying the Python runtime..."
robocopy $Python (Join-Path $dist "runtime") /E /NFL /NDL /NJH /NJS /XD __pycache__ Scripts include libs tcl | Out-Null
Write-Host "Copying APVIS..."
robocopy (Join-Path $root "app") (Join-Path $dist "app") /E /NFL /NDL /NJH /NJS /XD __pycache__ | Out-Null
Copy-Item (Join-Path $root "APVIS.pyw") $dist
Copy-Item (Join-Path $root "scripts\Install-APVIS.ps1") $dist
Write-Host "Done: $dist  (run Install-APVIS.ps1 from there, or double-click APVIS.pyw with runtime\pythonw.exe)"
