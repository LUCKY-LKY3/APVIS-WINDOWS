<#
  Install APVIS for Windows for this user: copies the package to %LOCALAPPDATA%\Programs\APVIS and adds a
  Start-menu shortcut. -StartWithWindows also starts it at sign-in. -Uninstall removes it again
  (your APVIS data in %LOCALAPPDATA%\APVIS stays unless you delete it).

  usage (from the built dist\APVIS folder):
    powershell -ExecutionPolicy Bypass -File Install-APVIS.ps1 [-StartWithWindows] [-Uninstall]
#>
param([switch]$StartWithWindows, [switch]$Uninstall)
$ErrorActionPreference = "Stop"
$target = Join-Path $env:LOCALAPPDATA "Programs\APVIS"
$menu = Join-Path ([Environment]::GetFolderPath("Programs")) "APVIS.lnk"
$startup = Join-Path ([Environment]::GetFolderPath("Startup")) "APVIS.lnk"

if ($Uninstall) {
    Remove-Item -Force -ErrorAction SilentlyContinue $menu, $startup
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Write-Host "APVIS removed."
    return
}

$here = $PSScriptRoot
if (-not (Test-Path (Join-Path $here "runtime\pythonw.exe"))) { throw "Run this from the built APVIS folder (it needs runtime\ and app\)." }
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
robocopy $here $target /E /NFL /NDL /NJH /NJS | Out-Null

function New-Shortcut($path) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = Join-Path $target "runtime\pythonw.exe"
    $link.Arguments = '"' + (Join-Path $target "APVIS.pyw") + '"'
    $link.WorkingDirectory = $target
    $link.Description = "APVIS"
    $link.Save()
}
New-Shortcut $menu
if ($StartWithWindows) { New-Shortcut $startup }
Write-Host "APVIS installed. Start it from the Start menu (APVIS). Alt+F4 closes it."
