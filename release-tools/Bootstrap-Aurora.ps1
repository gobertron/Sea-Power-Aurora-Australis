# Embedded in Install-Rimehaven.cmd. Windows PowerShell 5.1.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repository = '@@REPOSITORY@@'
$SeedVersion = '@@VERSION@@'
$SeedHash = '@@SEED_SHA256@@'
$LogRoot = Join-Path $env:LOCALAPPDATA 'RAN-Aurora-Australis\Logs'
$null = [IO.Directory]::CreateDirectory($LogRoot)
$Id = [Guid]::NewGuid().ToString('N')
$Log = Join-Path $LogRoot ('Launcher-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $Id.Substring(0,8) + '.log')
$Work = Join-Path ([IO.Path]::GetTempPath()) ('AuroraInstall-' + $Id)
$null = [IO.Directory]::CreateDirectory($Work)
$Headers = @{ 'User-Agent' = 'Rimehaven-Windows-Installer'; 'Accept' = 'application/vnd.github+json' }

function Report([string]$Message) {
    Write-Host $Message
    Add-Content -LiteralPath $Log -Value $Message -Encoding UTF8
}

function Read-LatestRelease {
    try {
        return Invoke-RestMethod -Uri "https://api.github.com/repos/$Repository/releases/latest" -Headers $Headers -TimeoutSec 15 -MaximumRedirection 0
    } catch {
        $problem = $_.Exception
        $response = if ($problem.PSObject.Properties['Response']) { $problem.Response } else { $null }
        if ($null -eq $response) {
            $networkErrors = @('ConnectFailure','NameResolutionFailure','ProxyNameResolutionFailure','Timeout','ConnectionClosed','ReceiveFailure','SendFailure')
            if ($problem -is [Net.WebException]) {
                if ($networkErrors -notcontains $problem.Status.ToString()) { throw }
            } elseif ($problem.GetType().FullName -notin @('System.Net.Http.HttpRequestException', 'System.Threading.Tasks.TaskCanceledException')) {
                throw
            }
            Report ('[OFFLINE] GitHub could not be reached. ' + $problem.Message)
        } else {
            $status = [int]$response.StatusCode
            if (@(403,404,429,500,502,503,504) -notcontains $status) { throw }
            Report ("[OFFLINE] A public stable release could not be read (HTTP $status).")
        }
        return $null
    }
}

function Write-Seed([string]$Destination) {
    $reader = [IO.File]::OpenText($env:AURORA_LAUNCH_PATH)
    try {
        $found = $false
        while (($line = $reader.ReadLine()) -ne $null) {
            if ($line -ceq '::AURORA_PAYLOAD_BASE64::') { $found = $true; break }
        }
        if (-not $found) { throw 'The bundled package marker is missing. Download the launcher again.' }
        [IO.File]::WriteAllBytes($Destination, [Convert]::FromBase64String($reader.ReadToEnd()))
    } finally { $reader.Dispose() }
    return $SeedHash
}

function Download-Package($Release, [string]$Number, [string]$Destination) {
    $name = "RAN-Rimehaven-v$Number-Windows11.zip"
    $base = "https://github.com/$Repository/releases/download/v$Number/"
    $archiveAsset = @($Release.assets | Where-Object { $_.name -ceq $name })
    $checksumAsset = @($Release.assets | Where-Object { $_.name -ceq ($name + '.sha256') })
    if ($archiveAsset.Count -ne 1 -or $checksumAsset.Count -ne 1) { throw "The stable release is missing its package or checksum: v$Number." }
    if ($archiveAsset[0].browser_download_url -cne ($base + $name) -or $checksumAsset[0].browser_download_url -cne ($base + $name + '.sha256')) { throw 'The release asset addresses do not match the configured repository and tag.' }
    $sumFile = Join-Path $Work 'download.sha256'
    Invoke-WebRequest -UseBasicParsing -Uri ($base + $name + '.sha256') -OutFile $sumFile -TimeoutSec 30
    $checksum = [IO.File]::ReadAllText($sumFile).Trim()
    $pattern = '^([A-Fa-f0-9]{64})(?:[ \t]+\*?' + [regex]::Escape($name) + ')?$'
    $match = [regex]::Match($checksum, $pattern)
    if (-not $match.Success) { throw 'Invalid SHA-256 checksum file for this release.' }
    Report ("[15%] Downloading Rimehaven v$Number.")
    Invoke-WebRequest -UseBasicParsing -Uri ($base + $name) -OutFile $Destination -TimeoutSec 300
    return $match.Groups[1].Value
}

function Assert-ZipPath([string]$Path) {
    if ($Path -match '[\x00-\x1f<>:"|?*\\]' -or $Path.StartsWith('/')) { throw "Invalid archive path: $Path" }
    foreach ($part in $Path.TrimEnd('/').Split('/')) {
        if ($part.Length -eq 0 -or $part -match '[. ]$' -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { throw "Invalid archive component in: $Path" }
    }
}

function Expand-Installer([string]$Archive, [string]$Destination, [string]$Number) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $allowedPrefix = "RAN-Rimehaven-v$Number-Windows11/"
        $manifests = @($zip.Entries | Where-Object { $_.FullName -ceq 'package-manifest.json' -or $_.FullName -ceq ($allowedPrefix + 'package-manifest.json') })
        if ($manifests.Count -ne 1) { throw 'The archive does not have the expected Rimehaven package layout.' }
        $prefix = $manifests[0].FullName.Substring(0, $manifests[0].FullName.Length - 'package-manifest.json'.Length)
        $seen = @{}
        [long]$total = 0
        foreach ($entry in $zip.Entries) {
            Assert-ZipPath $entry.FullName
            if (-not $entry.FullName.StartsWith($prefix,[StringComparison]::Ordinal)) { continue }
            $relative = $entry.FullName.Substring($prefix.Length)
            if ($relative -cne 'package-manifest.json' -and $relative -cne 'scripts/Manage-Aurora.ps1' -and -not $relative.StartsWith('payload/RAN-Aurora-Australis/',[StringComparison]::Ordinal)) { continue }
            if ($relative.EndsWith('/')) { continue }
            if ($seen.ContainsKey($relative)) { throw "Duplicate archive entry: $relative" }
            $seen[$relative] = $true
            $total += $entry.Length
            if ($seen.Count -gt 10000 -or $total -gt 1GB) { throw 'Archive exceeds the Rimehaven installation limits.' }
            $full = Join-Path $Destination $relative
            $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($full))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $full, $false)
        }
        foreach ($required in @('scripts/Manage-Aurora.ps1','package-manifest.json','payload/RAN-Aurora-Australis/_info.ini')) {
            if (-not $seen.ContainsKey($required)) { throw "Missing required file: $required" }
        }
        $manifest = Get-Content -LiteralPath (Join-Path $Destination 'package-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.mod_id -cne 'ran_aurora_australis' -or $manifest.version -cne $Number) { throw 'The release and the enclosed Rimehaven manifest disagree.' }
    } finally { $zip.Dispose() }
}

$code = 1
try {
    Report ('HMAS Rimehaven installer | Log: ' + $Log)
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Report ('[5%] Checking the latest public stable release from ' + $Repository)
    $release = Read-LatestRelease
    $archive = Join-Path $Work 'Aurora.zip'
    $number = $SeedVersion
    if ($null -ne $release) {
        if ($release.draft -or $release.prerelease -or [string]$release.tag_name -cnotmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw 'Invalid stable release metadata.' }
        $number = ([string]$release.tag_name).Substring(1)
    }
    if ($null -eq $release -or [version]$number -le [version]$SeedVersion) {
        $number = $SeedVersion
        Report ("[15%] Using the copy of v$number included in this launcher.")
        $expected = Write-Seed $archive
    } else {
        $expected = Download-Package $release $number $archive
    }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    if ($actual -ine $expected) { throw 'Package checksum mismatch. The installation was stopped.' }
    Report ("[30%] SHA-256 passed for v$number. Preparing the installer.")
    $extracted = Join-Path $Work 'verified'
    Expand-Installer $archive $extracted $number
    $manager = Join-Path $extracted 'scripts\Manage-Aurora.ps1'
    $arguments = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$manager,'-Mode','Install')
    if ($env:AURORA_GAME_PATH) { $arguments += @('-GamePath',$env:AURORA_GAME_PATH) }
    $engine = if ($PSVersionTable.PSEdition -eq 'Desktop') { 'powershell.exe' } else { (Get-Process -Id $PID).Path }
    if (-not [IO.Path]::IsPathRooted($engine)) { $engine = Join-Path $PSHOME $engine }
    & $engine @arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Rimehaven v$number installation failed (exit $code). See the installer's log path printed above." }
    Report ("[100%] Rimehaven v$number installer completed. See the installed version in its report.")
} catch {
    $code = 1
    Report ('[FAILED] ' + $_.Exception.Message)
} finally {
    if ([IO.Directory]::Exists($Work)) {
        try { Remove-Item -LiteralPath $Work -Recurse -Force } catch { Report ('Temporary files: ' + $Work) }
    }
    Report ('Launcher log: ' + $Log)
}
$global:AuroraResult = $code
