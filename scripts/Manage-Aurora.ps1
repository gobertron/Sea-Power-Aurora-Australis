[CmdletBinding()]
param(
    [ValidateSet('Install', 'Check', 'Uninstall')][string]$Mode = 'Install',
    [string]$GamePath,
    [switch]$NonInteractive
)

# Windows PowerShell 5.1+. Uses only Windows built-ins; no network downloads.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Version = '0.2.0'
$ModId = 'ran_aurora_australis'
$ModFolder = 'RAN-Aurora-Australis'
$MarkerName = '.aurora-australis-install.json'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PayloadRoot = Join-Path $ProjectRoot 'payload\RAN-Aurora-Australis'
$RunId = '{0}-{1}-{2}' -f $Mode, (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$LogBase = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [IO.Path]::GetTempPath() }
$LogDirectory = Join-Path $LogBase 'RAN-Aurora-Australis\Logs'
$LoggingError = $null
try { $null = New-Item -ItemType Directory -Path $LogDirectory -Force } catch {
    $LoggingError = $_.Exception.Message
    $LogDirectory = Join-Path ([IO.Path]::GetTempPath()) 'RAN-Aurora-Australis-Logs'
    try { $null = New-Item -ItemType Directory -Path $LogDirectory -Force } catch {
        $LoggingError += '; fallback log directory: ' + $_.Exception.Message
        Write-Warning 'Log files cannot be created. Keep this console output if the operation fails.'
    }
}
$LogFile = Join-Path $LogDirectory ($RunId + '.log')
$ResultFile = Join-Path $LogDirectory ($RunId + '.json')
$Checklist = New-Object System.Collections.Generic.List[object]
$Stage = $null
$Location = $null
$Target = $null
$Backup = $null
$Success = $false
$Failure = $null
$ExitCode = 1
$RunMutex = $null
$HasRunMutex = $false
$Operation = $Mode.ToLowerInvariant()
$InstalledVersion = $null
$RollbackStatus = 'not_needed'

function Write-Line([string]$Message) {
    Write-Host $Message
    try { Add-Content -LiteralPath $LogFile -Value $Message -Encoding UTF8 } catch {
        $script:LoggingError = $_.Exception.Message
        Write-Warning ('Could not append the log: ' + $script:LoggingError)
    }
}

function Write-Step([int]$Percent, [string]$Message) {
    Write-Line ('[{0,3}%] {1}' -f $Percent, $Message)
}

function Add-Check([string]$Message) {
    $Checklist.Add([ordered]@{ status = 'passed'; message = $Message })
    Write-Line ('[OK] ' + $Message)
}

function Get-Field([object]$Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) { return $null }
    return $Property.Value
}

function Read-Json([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required JSON file is missing: $Path" }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Get-ChildPath([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':')) {
        throw "Unsafe relative path: $Relative"
    }
    $Parts = @($Relative -split '[\\/]')
    if (@($Parts | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' }).Count -gt 0) {
        throw "Unsafe path component: $Relative"
    }
    $RootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $Resolved = [IO.Path]::GetFullPath((Join-Path $RootPath ($Relative.Replace('/', [IO.Path]::DirectorySeparatorChar))))
    if (-not $Resolved.StartsWith($RootPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes its directory: $Relative"
    }
    return $Resolved
}

function Assert-PlainDirectory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "Required directory is missing: $Path" }
    $Item = Get-Item -LiteralPath $Path -Force
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to modify a linked mod or staging directory: $Path"
    }
}

function Get-PlainFiles([string]$Root) {
    Assert-PlainDirectory $Root
    $Queue = New-Object 'System.Collections.Generic.Queue[string]'
    $Queue.Enqueue($Root)
    while ($Queue.Count -gt 0) {
        $Directory = $Queue.Dequeue()
        foreach ($Item in @(Get-ChildItem -LiteralPath $Directory -Force)) {
            if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked content is not accepted inside this mod: $($Item.FullName)" }
            if ($Item.PSIsContainer) { $Queue.Enqueue($Item.FullName) } else { $Item }
        }
    }
}

function Get-HashMap([object]$Manifest) {
    if ((Get-Field $Manifest 'schema') -ne 1 -or (Get-Field $Manifest 'mod_id') -ne $ModId) {
        throw 'The manifest is not a recognised HMAS Rimehaven manifest.'
    }
    $FileObject = Get-Field $Manifest 'files'
    if ($null -eq $FileObject) { throw 'The manifest has no file list.' }
    $Properties = @($FileObject.PSObject.Properties)
    if ($Properties.Count -eq 0) { throw 'The manifest file list is empty.' }
    $Hashes = @{}
    foreach ($Property in $Properties) {
        $Name = [string]$Property.Name
        if ($Name -eq $MarkerName) { throw 'The marker must not hash itself.' }
        $null = Get-ChildPath $PayloadRoot $Name
        $Hash = [string]$Property.Value
        if ($Hash -notmatch '^[a-fA-F0-9]{64}$') { throw "Invalid SHA256 for: $Name" }
        if ($Hashes.ContainsKey($Name)) { throw "Duplicate file path in manifest: $Name" }
        $Hashes[$Name] = $Hash.ToLowerInvariant()
    }
    return $Hashes
}

function Get-ReleaseVersion([string]$Text) {
    if ($Text -notmatch '^\d+\.\d+\.\d+(?:\.\d+)?$') { throw "Invalid stable release version: $Text" }
    return [version]$Text
}

function Test-SameHashes([hashtable]$First, [hashtable]$Second) {
    if ($First.Count -ne $Second.Count) { return $false }
    foreach ($Relative in @($First.Keys)) {
        if (-not $Second.ContainsKey($Relative) -or $First[$Relative] -ne $Second[$Relative]) { return $false }
    }
    return $true
}

function Test-FileHashes([string]$Root, [hashtable]$Hashes, [switch]$AllowMarker, [switch]$PermitRepair) {
    $Intact = $true
    $Prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $AllFiles = @(Get-PlainFiles $Root)
    foreach ($File in $AllFiles) {
        $Relative = $File.FullName.Substring($Prefix.Length).Replace('\', '/')
        if ($AllowMarker -and $Relative -eq $MarkerName) { continue }
        if (-not $Hashes.ContainsKey($Relative)) { throw "Unexpected file in mod directory: $Relative. It has been preserved." }
    }
    foreach ($Relative in @($Hashes.Keys)) {
        $Path = Get-ChildPath $Root $Relative
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            if (-not $PermitRepair) { throw "Missing mod file: $Relative" }
            $Intact = $false
            continue
        }
        $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -ne $Hashes[$Relative]) {
            if (-not $PermitRepair) { throw "Changed mod file: $Relative" }
            $Intact = $false
        }
    }
    return $Intact
}

function Get-OwnedManifest([string]$Root) {
    Assert-PlainDirectory $Root
    $Marker = Read-Json (Join-Path $Root $MarkerName)
    if ((Get-Field $Marker 'mod_id') -ne $ModId) { throw "Refusing to replace or remove an unrecognised directory: $Root" }
    $null = Get-ReleaseVersion ([string](Get-Field $Marker 'version'))
    return $Marker
}

function Assert-Owned([string]$Root) {
    $Marker = Get-OwnedManifest $Root
    $null = Test-FileHashes $Root (Get-HashMap $Marker) -AllowMarker
    return $Marker
}

function Write-Marker([string]$Root, [hashtable]$Hashes) {
    $Marker = [ordered]@{ schema = 1; mod_id = $ModId; version = $Version; installed_at_utc = [DateTime]::UtcNow.ToString('o'); files = $Hashes }
    $Marker | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $Root $MarkerName) -Encoding UTF8
}

function Test-GameCandidate([string]$Candidate) {
    if (-not (Test-Path -LiteralPath $Candidate -PathType Container)) { return $null }
    $Game = (Resolve-Path -LiteralPath $Candidate).ProviderPath.TrimEnd('\', '/')
    if ((Split-Path -Leaf $Game) -eq 'StreamingAssets') { $Game = Split-Path -Parent (Split-Path -Parent $Game) }
    $Assets = Join-Path $Game 'Sea Power_Data\StreamingAssets'
    $Executables = @('Sea Power.exe', 'SeaPower.exe')
    $Executable = $null
    foreach ($Name in $Executables) {
        $Path = Join-Path $Game $Name
        if (Test-Path -LiteralPath $Path -PathType Leaf) { $Executable = $Path; break }
    }
    if ($null -eq $Executable -or -not (Test-Path -LiteralPath (Join-Path $Assets 'original') -PathType Container)) { return $null }
    return @{ Game = $Game; Assets = $Assets; Executable = $Executable }
}

function Resolve-Game([string]$InputPath) {
    if (-not [string]::IsNullOrWhiteSpace($InputPath)) {
        $Match = Test-GameCandidate $InputPath
        if ($null -eq $Match) { throw "The specified -GamePath is not a Sea Power installation: $InputPath. No other installation was selected." }
        return $Match
    }
    $Candidates = New-Object System.Collections.Generic.List[string]
    $Libraries = New-Object System.Collections.Generic.List[string]
    if ($env:OS -eq 'Windows_NT') {
        foreach ($Registry in @('HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKLM:\SOFTWARE\Valve\Steam')) {
            if (Test-Path -LiteralPath $Registry) {
                $Entry = Get-ItemProperty -LiteralPath $Registry
                foreach ($Name in @('SteamPath', 'InstallPath')) {
                    $Value = Get-Field $Entry $Name
                    if ($Value) { $Libraries.Add([string]$Value) }
                }
            }
        }
        # Registered Steam roots supply custom library names on any drive. The
        # usual per-drive paths also cover detached/unregistered library roots.
        foreach ($Drive in @(Get-PSDrive -PSProvider FileSystem)) {
            if ($Drive.Root -match '^[A-Za-z]:\\$') {
                foreach ($Suffix in @('SteamLibrary', 'Steam', 'Program Files (x86)\Steam', 'Program Files\Steam')) {
                    $Libraries.Add((Join-Path $Drive.Root $Suffix))
                }
            }
        }
    }
    if (${env:ProgramFiles(x86)}) { $Libraries.Add((Join-Path ${env:ProgramFiles(x86)} 'Steam')) }
    if ($env:ProgramFiles) { $Libraries.Add((Join-Path $env:ProgramFiles 'Steam')) }
    $ReadRoots = @{}
    for ($Index = 0; $Index -lt $Libraries.Count; $Index++) {
        $Steam = $Libraries[$Index]
        if ($ReadRoots.ContainsKey($Steam)) { continue }
        $ReadRoots[$Steam] = $true
        $VdfPath = Join-Path $Steam 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $VdfPath -PathType Leaf) {
            $Vdf = Get-Content -LiteralPath $VdfPath -Raw
            # Current VDF uses path fields; old Steam uses numbered values.
            foreach ($Hit in [regex]::Matches($Vdf, '"(?:path|[0-9]+)"\s+"([^"\r\n]+)"')) {
                $Value = $Hit.Groups[1].Value.Replace('\\', '\')
                if ([IO.Path]::IsPathRooted($Value)) { $Libraries.Add($Value) }
            }
        }
    }
    foreach ($Library in @($Libraries | Select-Object -Unique)) {
        $ManifestPath = Join-Path $Library 'steamapps\appmanifest_1286220.acf'
        if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
            $Acf = Get-Content -LiteralPath $ManifestPath -Raw
            $Hit = [regex]::Match($Acf, '"installdir"\s+"([^"\r\n]+)"')
            if ($Hit.Success) { $Candidates.Add((Join-Path $Library ('steamapps\common\' + $Hit.Groups[1].Value))) }
        }
        $Candidates.Add((Join-Path $Library 'steamapps\common\Sea Power'))
    }
    $Matches = New-Object System.Collections.Generic.List[object]
    $Seen = @{}
    foreach ($Candidate in @($Candidates | Select-Object -Unique)) {
        $Match = Test-GameCandidate $Candidate
        if ($null -ne $Match -and -not $Seen.ContainsKey($Match.Game)) {
            $Seen[$Match.Game] = $true
            $Matches.Add($Match)
        }
    }
    if ($Matches.Count -eq 1) { return $Matches[0] }
    if ($NonInteractive) {
        $Details = @($Matches | ForEach-Object { $_.Game }) -join '; '
        throw "Sea Power detection is inconclusive ($($Matches.Count) installations). Pass -GamePath explicitly. Candidates: $Details"
    }
    if ($Matches.Count -gt 1) {
        Write-Line 'More than one Sea Power installation was found:'
        for ($Index = 0; $Index -lt $Matches.Count; $Index++) { Write-Line ('  {0}. {1}' -f ($Index + 1), $Matches[$Index].Game) }
        $Answer = Read-Host 'Enter the installation number, or paste another Sea Power folder; Enter cancels'
        $Choice = 0
        if ([int]::TryParse($Answer, [ref]$Choice) -and $Choice -ge 1 -and $Choice -le $Matches.Count) { return $Matches[$Choice - 1] }
    } else {
        Write-Line 'Sea Power was not found in the detected Steam libraries.'
        $Answer = Read-Host 'Paste the Sea Power game folder (or StreamingAssets folder); Enter cancels'
    }
    if ([string]::IsNullOrWhiteSpace($Answer)) { throw 'Game-folder selection cancelled. No mod files were changed.' }
    $Answer = $Answer.Trim().Trim('"')
    $Match = Test-GameCandidate $Answer
    if ($null -eq $Match) { throw "The selected folder is not a Sea Power installation: $Answer. No mod files were changed." }
    return $Match
}

function Assert-GameClosed {
    $Processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(Sea Power|SeaPower)$' })
    if ($Processes.Count -gt 0) { throw 'Close Sea Power before installing, checking or uninstalling this mod.' }
}

function Write-GameBuild([hashtable]$Game) {
    $SteamApps = Split-Path -Parent (Split-Path -Parent $Game.Game)
    $Path = Join-Path $SteamApps 'appmanifest_1286220.acf'
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $Text = Get-Content -LiteralPath $Path -Raw
        $Hit = [regex]::Match($Text, '"buildid"\s+"([^"\r\n]+)"')
        if ($Hit.Success) { Write-Line ('[GAME BUILD] ' + $Hit.Groups[1].Value) }
    }
    $FileVersion = (Get-Item -LiteralPath $Game.Executable).VersionInfo.FileVersion
    if ($FileVersion) { Write-Line ('[EXE VERSION] ' + $FileVersion) }
}

function Assert-Dependencies([string]$ModRoot, [string]$OriginalRoot) {
    $Path = Join-Path $ModRoot 'DEPENDENCIES.json'
    $Dependencies = Read-Json $Path
    if ((Get-Field $Dependencies 'schema') -ne 1) { throw 'Unsupported DEPENDENCIES.json schema.' }
    $Files = @(Get-Field $Dependencies 'files')
    foreach ($Entry in $Files) {
        if ($null -eq $Entry) { continue }
        $Relative = [string](Get-Field $Entry 'path')
        $FilePath = Get-ChildPath $OriginalRoot $Relative
        if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw "Required stock game file is missing: original/$Relative. The installer did not select a different substitute." }
    }
    $RegistryFiles = [ordered]@{ weapon = 'weapons.ini'; sensor = 'sensors.ini'; combat = 'combatsystems.ini' }
    foreach ($Kind in @($RegistryFiles.Keys)) {
        $Names = @(Get-Field $Dependencies ($Kind + '_systems'))
        if (@($Names | Where-Object { $null -ne $_ }).Count -eq 0) { continue }
        $RegistryPath = Join-Path $OriginalRoot ('systems\' + $RegistryFiles[$Kind])
        if (-not (Test-Path -LiteralPath $RegistryPath -PathType Leaf)) { throw "Required stock registry is missing: $RegistryPath" }
        $RegistryText = Get-Content -LiteralPath $RegistryPath -Raw
        foreach ($Name in $Names) {
            if ($null -eq $Name -or [string]::IsNullOrWhiteSpace([string]$Name)) { continue }
            $Pattern = '(?m)^\s*\[' + [regex]::Escape([string]$Name) + '\][^\r\n]*(?:\r?$)'
            if (-not [regex]::IsMatch($RegistryText, $Pattern)) { throw "Required stock $Kind system is missing: [$Name] in $RegistryPath" }
        }
    }
    Add-Check 'Declared stock ammunition, aircraft, weapon, sensor and combat-system dependencies exist'
}

function New-BackupPath([string]$GameRoot, [string]$Label) {
    $Root = Join-Path $GameRoot 'RAN-Aurora-Australis-Backups'
    if (Test-Path -LiteralPath $Root) { Assert-PlainDirectory $Root } else { $null = New-Item -ItemType Directory -Path $Root }
    return Join-Path $Root ('{0}-{1}-{2}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $Label, ([guid]::NewGuid().ToString('N').Substring(0, 8)))
}

try {
    Write-Step 0 ('HMAS Rimehaven v' + $Version + ' - ' + $Mode)
    Write-Line ('Log: ' + $LogFile)
    $RunMutex = New-Object -TypeName System.Threading.Mutex -ArgumentList @($false, 'Local\RAN-Aurora-Australis-Installer')
    try { $HasRunMutex = $RunMutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $HasRunMutex = $true }
    if (-not $HasRunMutex) { throw 'Another HMAS Rimehaven installer/checker is already running. Close it before retrying.' }
    $Location = Resolve-Game $GamePath
    $Target = Join-Path $Location.Assets $ModFolder
    Add-Check ('Sea Power found: ' + $Location.Game)
    Write-GameBuild $Location
    Assert-GameClosed
    Add-Check 'Sea Power is closed'
    if ($Mode -eq 'Install') {
        Write-Step 10 'Verifying the extracted native payload'
        $Manifest = Read-Json (Join-Path $ProjectRoot 'package-manifest.json')
        if ((Get-Field $Manifest 'version') -ne $Version) { throw 'The package and installer versions differ. Download the launcher again.' }
        $Hashes = Get-HashMap $Manifest
        $null = Test-FileHashes $PayloadRoot $Hashes
        $Count = $Hashes.Count
        if (-not $Hashes.ContainsKey('_info.ini') -or -not $Hashes.ContainsKey('DEPENDENCIES.json')) { throw 'Package manifest is missing required mod metadata.' }
        Add-Check ("$Count payload files match their SHA256 hashes")
        Write-Step 30 'Checking stock game dependencies'
        Assert-Dependencies $PayloadRoot (Join-Path $Location.Assets 'original')
        $UseInstalled = $false
        if (Test-Path -LiteralPath $Target) {
            $Old = Get-OwnedManifest $Target
            $InstalledVersion = [string](Get-Field $Old 'version')
            $OldHashes = Get-HashMap $Old
            $OldIntact = Test-FileHashes $Target $OldHashes -AllowMarker -PermitRepair
            $VersionOrder = (Get-ReleaseVersion $InstalledVersion).CompareTo((Get-ReleaseVersion $Version))
            if ($VersionOrder -gt 0) {
                if (-not $OldIntact) { throw "Installed v$InstalledVersion needs repair. A v$InstalledVersion or newer package is required." }
                $UseInstalled = $true
                $Operation = 'kept_newer'
            } elseif ($VersionOrder -eq 0 -and $OldIntact -and (Test-SameHashes $OldHashes $Hashes)) {
                $UseInstalled = $true
                $Operation = 'already_installed'
            } elseif ($VersionOrder -eq 0) {
                $Operation = 'repair'
            } else {
                $Operation = 'upgrade'
            }
        }
        if ($UseInstalled) {
            Write-Step 100 ("Installed v$InstalledVersion is intact. No files changed.")
        } else {
            Write-Step 45 'Staging the new mod outside StreamingAssets'
            $Stage = Join-Path $Location.Game ('.aurora-australis-stage-' + [guid]::NewGuid().ToString('N'))
            $null = New-Item -ItemType Directory -Path $Stage
            foreach ($Relative in @($Hashes.Keys)) {
                $Source = Get-ChildPath $PayloadRoot $Relative
                $Destination = Get-ChildPath $Stage $Relative
                $null = New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force
                Copy-Item -LiteralPath $Source -Destination $Destination
            }
            Write-Marker $Stage $Hashes
            $null = Assert-Owned $Stage
            Add-Check 'Staged mod passed the hash and ownership checks'
            Write-Step 75 'Installing the isolated HMAS Rimehaven folder'
            Assert-GameClosed
            if ($null -ne $InstalledVersion) {
                $Current = Get-OwnedManifest $Target
                $CurrentHashes = Get-HashMap $Current
                if ((Get-Field $Current 'version') -ne $InstalledVersion -or -not (Test-SameHashes $CurrentHashes $OldHashes)) {
                    throw 'Installed version changed while staging. Run the launcher again.'
                }
                $null = Test-FileHashes $Target $CurrentHashes -AllowMarker -PermitRepair
                $Backup = New-BackupPath $Location.Game 'previous-install'
                Move-Item -LiteralPath $Target -Destination $Backup
                Write-Line ('[BACKUP] ' + $Backup)
            }
            $MovedNew = $false
            try {
                if (Test-Path -LiteralPath $Target) { throw 'The target appeared during installation; it has been preserved. Retry after checking that no other installer is running.' }
                Move-Item -LiteralPath $Stage -Destination $Target
                $MovedNew = $true
                $Stage = $null
                $null = Assert-Owned $Target
            } catch {
                $InstallFailure = $_
                # Preserve any failed new install before restoring the previous folder.
                if ($MovedNew -and (Test-Path -LiteralPath $Target)) {
                    $Failed = New-BackupPath $Location.Game 'failed-new-install'
                    Move-Item -LiteralPath $Target -Destination $Failed
                    Write-Line ('[PRESERVED FAILED INSTALL] ' + $Failed)
                }
                if ($Backup -and (Test-Path -LiteralPath $Backup)) {
                    if (-not (Test-Path -LiteralPath $Target)) {
                        Move-Item -LiteralPath $Backup -Destination $Target
                        $RollbackStatus = 'restored'
                        Write-Line ('[RESTORED] Previous v' + $InstalledVersion + ': ' + $Target)
                    } else {
                        $RollbackStatus = 'backup_preserved'
                        Write-Line ('[PREVIOUS INSTALL PRESERVED] ' + $Backup)
                    }
                }
                throw $InstallFailure
            }
            $InstalledVersion = $Version
            Add-Check ('Installed v' + $Version + ': ' + $Target)
            Write-Step 100 'Installation and file checks passed. Live Sea Power testing is still required.'
            Write-Line 'Next: start Sea Power, enable the HMAS Rimehaven mod in Mod Manager, then restart the game.'
            Write-Line 'Open Mission Editor, place the White Meridian-class icebreaker and check the hull at the waterline.'
        }
    } elseif ($Mode -eq 'Check') {
        Write-Step 25 'Checking the installed HMAS Rimehaven folder'
        $Installed = Assert-Owned $Target
        $InstalledVersion = [string](Get-Field $Installed 'version')
        Add-Check ('Installed version: ' + [string](Get-Field $Installed 'version'))
        Write-Step 60 'Checking installed stock dependencies'
        Assert-Dependencies $Target (Join-Path $Location.Assets 'original')
        Add-Check 'Installed files match their recorded SHA256 hashes'
        Write-Step 100 'Installed file checks passed.'
    } else {
        Write-Step 30 'Verifying the owned installation before uninstalling'
        $null = Assert-Owned $Target
        Add-Check 'Owned installation is unchanged'
        Write-Step 70 'Moving the mod to a recoverable backup outside StreamingAssets'
        Assert-GameClosed
        $Backup = New-BackupPath $Location.Game 'uninstalled'
        Move-Item -LiteralPath $Target -Destination $Backup
        Add-Check ('Preserved uninstalled files: ' + $Backup)
        Write-Step 100 'HMAS Rimehaven uninstalled; its files are preserved in the backup folder.'
    }
    $Success = $true
    $ExitCode = 0
} catch {
    $Failure = $_.Exception.Message
    $Checklist.Add([ordered]@{ status = 'failed'; message = $Failure })
    Write-Line ('[FAILED] ' + $Failure)
    Write-Line 'Copy the checklist and log back for review.'
} finally {
    if ($Stage -and (Test-Path -LiteralPath $Stage)) {
        try { Remove-Item -LiteralPath $Stage -Recurse -Force } catch { Write-Line ('[STAGING CLEANUP] Preserved at: ' + $Stage) }
    }
    $Result = [ordered]@{
        schema = 1; mod_id = $ModId; package_version = $Version; mode = $Mode;
        success = $Success; live_game_tested = $false; ended_at_utc = [DateTime]::UtcNow.ToString('o');
        game_path = $(if ($null -ne $Location) { $Location.Game } else { $null });
        target_path = $Target; backup_path = $Backup; failure = $Failure;
        operation = $Operation; installed_version = $InstalledVersion; rollback = $RollbackStatus;
        checklist = @($Checklist.ToArray()); log_file = $LogFile
    }
    $Result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ResultFile -Encoding UTF8
    Write-Line ('Result: ' + $ResultFile)
    Write-Line ('Log: ' + $LogFile)
    if ($HasRunMutex -and $null -ne $RunMutex) { $RunMutex.ReleaseMutex() }
    if ($null -ne $RunMutex) { $RunMutex.Dispose() }
}
exit $ExitCode
