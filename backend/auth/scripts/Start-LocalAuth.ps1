param([string]$DatabaseDirectory, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$authDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$mysqlBin = 'C:\Program Files\MySQL\MySQL Server 8.4\bin'

# Start an EXISTING instance only. Never initialise, migrate or delete data.
# Packaged desktop apps may redirect LocalAppData writes to LocalCache.
function Get-ExistingInstanceId([string]$Directory) {
    $autoConfig = Join-Path $Directory 'data\auto.cnf'
    if (!(Test-Path -LiteralPath $autoConfig -PathType Leaf)) { return $null }
    $line = Get-Content -LiteralPath $autoConfig | Where-Object { $_ -match '^\s*server-uuid\s*=' } | Select-Object -First 1
    if (!$line) { return $null }
    return ($line -split '=', 2)[1].Trim()
}

if ([string]::IsNullOrWhiteSpace($DatabaseDirectory)) {
    $profileDirectory = [Environment]::GetFolderPath('UserProfile')
    $candidates = @(
        (Join-Path $profileDirectory 'AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\HPT\mysql')
        (Join-Path $profileDirectory 'AppData\Local\HPT\mysql')
        ([IO.Path]::Combine([Environment]::GetFolderPath('LocalApplicationData'), 'HPT', 'mysql'))
    )
    if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA 'HPT\mysql' }
    $found = @()
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ([IO.File]::Exists((Join-Path $candidate 'my.ini')) -and
            [IO.File]::Exists((Join-Path $candidate 'admin.cnf'))) {
            $instanceId = Get-ExistingInstanceId $candidate
            if ($instanceId) { $found += [pscustomobject]@{ Directory=$candidate; InstanceId=$instanceId } }
        }
    }
    if ($found.Count -eq 0) {
        throw ('Cannot locate an existing database. Checked: ' + ($candidates -join '; ') + '. Supply -DatabaseDirectory with its existing my.ini, admin.cnf and data folder. Do not initialise a new database.')
    }
    if (@($found.InstanceId | Select-Object -Unique).Count -gt 1) {
        throw 'Multiple different existing MySQL instances were found. Specify -DatabaseDirectory explicitly; no database was started.'
    }
    # Prefer the explicit physical LocalCache path, usable from normal terminals.
    $DatabaseDirectory = $found[0].Directory
}
$DatabaseDirectory = [IO.Path]::GetFullPath($DatabaseDirectory)
$mysqlConfig = Join-Path $DatabaseDirectory 'my.ini'
$adminConfig = Join-Path $DatabaseDirectory 'admin.cnf'
$dataDirectory = Join-Path $DatabaseDirectory 'data'
$errorLog = Join-Path $DatabaseDirectory 'mysql-error.log'
foreach ($required in @($mysqlConfig, $adminConfig, (Join-Path $dataDirectory 'auto.cnf'),
    (Join-Path $dataDirectory 'mysql.ibd'), (Join-Path $authDirectory '.env'),
    "$mysqlBin\mysqld.exe", "$mysqlBin\mysql.exe", (Join-Path $authDirectory 'server.js'))) {
    if (![IO.File]::Exists($required)) { throw "Required existing file is missing: $required" }
}
$expectedId = Get-ExistingInstanceId $DatabaseDirectory
if (!$expectedId) { throw 'Missing existing MySQL instance ID. Refusing to initialise data.' }
Write-Output "Existing database: $DatabaseDirectory"
Write-Output "Existing data folder: $dataDirectory"
if ($CheckOnly) { Write-Output 'Configuration check passed; no services started.'; return }

function Test-LocalPort([int]$Port) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (!$pending.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

$server = $null
if (!(Test-LocalPort 3306)) {
    # Command-line paths override stale logical paths in my.ini without editing it.
    $arguments = @("--defaults-file=`"$mysqlConfig`"", "--datadir=`"$dataDirectory`"",
        "--log-error=`"$errorLog`"", '--bind-address=127.0.0.1', '--port=3306')
    $server = Start-Process -FilePath "$mysqlBin\mysqld.exe" -ArgumentList $arguments -WindowStyle Hidden -PassThru
}
$ready = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    if ($null -ne $server -and $server.HasExited) { throw "MySQL exited. Inspect $errorLog. Existing files were not reinitialised." }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = "$mysqlBin\mysql.exe"
    $start.Arguments = "--defaults-extra-file=`"$adminConfig`" --protocol=TCP --host=127.0.0.1 --port=3306 --connect-timeout=2 --batch --skip-column-names --execute=`"SELECT @@server_uuid`""
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $check = [Diagnostics.Process]::Start($start)
    $answer = $check.StandardOutput.ReadToEnd().Trim()
    $null = $check.StandardError.ReadToEnd()
    $check.WaitForExit()
    $ok = $check.ExitCode -eq 0
    $check.Dispose()
    if ($ok) {
        if ($answer -ne $expectedId) { throw 'Port 3306 belongs to a different MySQL instance. No accounts or data were changed.' }
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 500
}
if (!$ready) { throw "Cannot authenticate to the existing database. Inspect $errorLog and admin.cnf locally; do not publish credentials." }

if (!(Test-LocalPort 3000)) {
    if (!(Test-Path -LiteralPath (Join-Path $authDirectory 'node_modules'))) { throw 'Existing Node dependencies are missing. Run npm ci in backend/auth.' }
    $node = (Get-Command node -ErrorAction Stop).Source
    Start-Process -FilePath $node -ArgumentList "`"$authDirectory\server.js`"" -WorkingDirectory $authDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $DatabaseDirectory 'auth-output.log') -RedirectStandardError (Join-Path $DatabaseDirectory 'auth-error.log') | Out-Null
}
for ($attempt=0; $attempt -lt 20; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:3000/health' -TimeoutSec 2
        if ($health.database -eq 'connected' -and $health.message -eq 'Backend is running') {
            Write-Output 'MySQL: existing instance verified at 127.0.0.1:3306'
            Write-Output 'Login API: ready at http://127.0.0.1:3000/health'
            Write-Output 'Run this same script after restarting Windows. No database was initialised.'
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw "Login API is unavailable or port 3000 belongs to another service. Inspect $DatabaseDirectory\auth-error.log"
