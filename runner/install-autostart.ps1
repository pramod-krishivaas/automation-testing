<#
.SYNOPSIS
    Start this laptop's test runner automatically at Windows login.

.DESCRIPTION
    Registers a per-user scheduled task that runs `python -m runner` from this
    repo in a hidden window at every login, and starts it again if it crashes.
    Output goes to %USERPROFILE%\.test-automation-platform\runner.log.

    Run it once per laptop, from any folder. Run it again after moving the repo
    or changing Python. No admin rights are needed. Set BACKEND_URL (and
    optionally RUNNER_NAME) in the repo's .env first.

.PARAMETER Uninstall
    Remove the task and stop the runner it started.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File runner\install-autostart.ps1
#>
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$TaskName = "Automation Test Runner"
$Repo = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $env:USERPROFILE ".test-automation-platform"
$Log = Join-Path $LogDir "runner.log"
$User = "$env:USERDOMAIN\$env:USERNAME"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed '$TaskName'."
    } else {
        Write-Host "'$TaskName' is not installed."
    }
    return
}

# Prefer the repo's virtualenv, as the README setup creates one.
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }
if (-not (Test-Path (Join-Path $Repo ".env"))) {
    Write-Warning "No .env in $Repo, so the runner will use BACKEND_URL=http://localhost:8000. Create one first (see README)."
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# A hidden PowerShell hosts the runner so that neither it nor the adb, Appium and
# pytest processes it starts open console windows (they share its hidden one).
# The loop restarts the runner after a crash; exit code 0 means another runner
# is already active on this laptop, so it stops there.
$Command = ('$env:RUNNER_LOG_FILE = ''{0}''; Set-Location -LiteralPath ''{1}''; ' +
            'do {{ & ''{2}'' -X utf8 -m runner; $code = $LASTEXITCODE; ' +
            'if ($code -ne 0) {{ Start-Sleep -Seconds 10 }} }} while ($code -ne 0)') -f $Log, $Repo, $Python

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$Command`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed '$TaskName'. The runner is starting now, and will start at every login."
Write-Host "Log: $Log"
Write-Host "Remove it with: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Uninstall"
