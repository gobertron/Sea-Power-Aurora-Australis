"""Exercise the shipped PowerShell code against disposable Sea Power-shaped fixtures.

Requires PowerShell 5.1+ (powershell.exe or pwsh). Steam is not launched.
The HTTP functions return release metadata and local release bytes in a child
PowerShell process. All installer, archive and checksum checks run normally.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from build_launcher import build, DEFAULT_REPOSITORY
from verify_launcher import verify

MOD = "RAN-Aurora-Australis"
MARKER = ".aurora-australis-install.json"

BOOT = r"""
function Invoke-RestMethod {
    param($Uri,$Headers,$TimeoutSec,$MaximumRedirection)
    if ($Uri -cne "https://api.github.com/repos/gobertron/Sea-Power-Aurora-Australis/releases/latest") { throw "Unexpected repository: $Uri" }
    if ($env:TEST_RELEASE_MODE -eq 'offline') {
        throw [Net.WebException]::new('Test network offline', [Net.WebExceptionStatus]::NameResolutionFailure)
    }
    $n = $env:TEST_RELEASE_VERSION
    $name = "RAN-Rimehaven-v$n-Windows11.zip"
    $base = "https://github.com/gobertron/Sea-Power-Aurora-Australis/releases/download/v$n/"
    return @{draft=$false;prerelease=$false;tag_name="v$n";assets=@(
        @{name=$name;browser_download_url=($base + $name)},
        @{name=($name+'.sha256');browser_download_url=($base+$name+'.sha256')}
    )}
}
function Invoke-WebRequest {
    param([switch]$UseBasicParsing,$Uri,$OutFile,$TimeoutSec)
    $file = ([Uri]$Uri).Segments[-1]
    if ($file.EndsWith('.sha256') -and $env:TEST_RELEASE_MODE -eq 'bad-checksum') {
        [IO.File]::WriteAllText($OutFile,'0'*64)
    } else {
        Copy-Item -LiteralPath (Join-Path $env:TEST_RELEASE_DIR $file) -Destination $OutFile
    }
}
$t=[IO.File]::ReadAllText($env:AURORA_LAUNCH_PATH)
$m=[regex]::Match($t,'(?ms)^::AURORA_BOOTSTRAP::\r?\n(.*?)^::AURORA_PAYLOAD_BASE64::\r?$')
if (-not $m.Success) { throw 'Launcher could not be parsed' }
$global:AuroraResult=1
& ([scriptblock]::Create($m.Groups[1].Value))
exit $global:AuroraResult
"""

ROLLBACK = r"""
function Move-Item {
    param($LiteralPath,$Destination)
    if ((Split-Path -Leaf $LiteralPath).StartsWith('.aurora-australis-stage-')) { throw 'Test promotion failure' }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}
& $env:TEST_MANAGER -GamePath $env:TEST_GAME -NonInteractive
exit $LASTEXITCODE
"""


def fixture(apps, dependencies):
    game = apps / "common" / "Polar Test Install"
    original = game / "Sea Power_Data/StreamingAssets/original"
    original.mkdir(parents=True)
    (game / "Sea Power.exe").touch()
    (apps / "appmanifest_1286220.acf").write_text('"installdir" "Polar Test Install"\n"buildid" "TEST-FIXTURE"')
    for dep in dependencies["files"]:
        path = original / dep["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    for kind, filename in (("weapon", "weapons"), ("sensor", "sensors"), ("combat", "combatsystems")):
        path = original / f"systems/{filename}.ini"
        path.write_text("".join(f"[{s}]\n" for s in dependencies[kind + "_systems"]))
    return game


def tree_hash(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def run_tests(args, work):
    package = args.root.resolve()
    launcher = args.launcher.resolve()
    version = json.loads((package / "package-manifest.json").read_text("utf-8-sig"))["version"]
    verify(launcher, package)
    manager = package / "scripts/Manage-Aurora.ps1"
    scenario = work / "Steam Apps and Saves"
    deps = json.loads((package / "payload" / MOD / "DEPENDENCIES.json").read_text())
    game = fixture(scenario / "Custom Library/steamapps", deps)
    steam = work / "program-files/Steam/steamapps"
    steam.mkdir(parents=True)
    library = str(game.parents[2]).replace("\\", "\\\\")
    (steam / "libraryfolders.vdf").write_text(f'"libraryfolders"\n{{\n "0" {{ "path" "{library}" }}\n}}')
    assets = game / "Sea Power_Data/StreamingAssets"
    target = assets / MOD
    appdata = work / "local"
    logs = appdata / MOD / "Logs"
    env = dict(os.environ, LOCALAPPDATA=str(appdata), ProgramFiles=str(work / "program-files"),
               TEST_MANAGER=str(manager), TEST_GAME=str(game), TEST_RELEASE_VERSION=version,
               TEST_RELEASE_DIR=str(launcher.parent), AURORA_GAME_PATH=str(game))
    results = {}

    def invoke(body=None, call=(), fail=False, **extra):
        cmd = [args.powershell, "-NoProfile", "-NoLogo", "-NonInteractive"]
        if body is not None:
            cmd.extend(["-Command", body])
        else:
            cmd.extend(call)
        before = set(logs.glob("*.json"))
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           errors="replace", env=dict(env, **extra), timeout=240)
        if (p.returncode != 0) != fail:
            raise ValueError(f"Unexpected exit {p.returncode}\n{p.stdout}")
        reports = list(set(logs.glob("*.json")) - before)
        return json.loads(reports[0].read_text("utf-8-sig")) if reports else None, p.stdout

    def boot(path, mode="offline", **kwargs):
        return invoke(BOOT, AURORA_LAUNCH_PATH=str(path), TEST_RELEASE_MODE=mode, **kwargs)

    def expect(label, condition):
        if not condition:
            raise ValueError(label)
        results[label] = "passed"
        print("PASS", label, flush=True)

    # On a real Windows machine scope every install to the temporary fixture.
    # An isolated POSIX fixture has no host Steam registry or mounted drive roots.
    discovery = os.name != "nt"
    result, _ = boot(launcher, AURORA_GAME_PATH="" if discovery else str(game))
    clean_label = "Clean install via verified seed"
    if discovery:
        clean_label += " and Steam VDF/custom ACF discovery"
    expect(clean_label,
           result["installed_version"] == version and result["operation"] == "install"
           and Path(result["game_path"]) == game)
    installed = tree_hash(target)
    first_marker = (target / MARKER).stat().st_mtime_ns
    result, _ = boot(launcher)
    expect("Repeat install exits without rewriting the active copy or making a backup",
           result["operation"] == "already_installed" and result["backup_path"] is None
           and first_marker == (target / MARKER).stat().st_mtime_ns)
    (target / "_info.ini").write_text("corrupt managed test file")
    result, _ = boot(launcher)
    expect("Damaged owned install repaired with backup", result["operation"] == "repair"
           and (Path(result["backup_path"]) / "_info.ini").read_text() == "corrupt managed test file"
           and tree_hash(target)["_info.ini"] == installed["_info.ini"])
    (target / "my-private-note.txt").write_text("keep")
    result, _ = boot(launcher, fail=True)
    expect("Unmanaged file in the platform directory preserved", not result["success"] and
           (target / "my-private-note.txt").read_text() == "keep" and result["backup_path"] is None)
    (target / "my-private-note.txt").unlink()
    before = tree_hash(target)
    stock = assets / "original" / deps["files"][0]["path"]
    stock.rename(stock.with_suffix(".holding"))
    result, _ = boot(launcher, fail=True)
    expect("Missing stock dependency blocks changes", not result["success"] and tree_hash(target) == before)
    stock.with_suffix(".holding").rename(stock)
    if args.legacy:
        legacy = args.legacy.resolve()
        legacy_launcher_dir = work / "old-saved-launcher"
        old_launcher = legacy_launcher_dir / "Install-Rimehaven.cmd"
        build(legacy, DEFAULT_REPOSITORY, old_launcher)
        shutil.rmtree(target)
        result, _ = invoke(call=["-File", str(legacy / "scripts/Manage-Aurora.ps1"), "-Mode", "Install",
                                 "-GamePath", str(game)])
        old_hashes = tree_hash(target)
        expect("Real legacy v0.1.0 manager and payload installed in fixture", result["success"]
               and json.loads((target / MARKER).read_text("utf-8-sig"))["version"] == "0.1.0")
        result, _ = invoke(ROLLBACK, fail=True)
        expect("Promotion failure restores complete legacy tree byte for byte",
               result["rollback"] == "restored" and tree_hash(target) == old_hashes)
        result, stdout = boot(old_launcher, "bad-checksum", fail=True)
        expect("Corrupt remote checksum rejected before replacing active copy",
               result is None and "checksum mismatch" in stdout and tree_hash(target) == old_hashes)
        result, _ = boot(old_launcher, "latest")
        expect("Older saved launcher downloads stable update and upgrades in place",
               result["operation"] == "upgrade" and result["installed_version"] == version
               and tree_hash(Path(result["backup_path"])) == old_hashes)
        # A stale seed created before the updater existed has its own historical
        # manager. Test downgrade protection with the current manager instead.
        marker = target / MARKER
        newer = json.loads(marker.read_text("utf-8-sig"))
        newer["version"] = "99.0.0"
        marker.write_text(json.dumps(newer))
        result, _ = boot(launcher)
        expect("Offline launcher preserves an intact newer install", result["operation"] == "kept_newer"
               and result["installed_version"] == "99.0.0" and result["backup_path"] is None)
    release_name = f"RAN-Rimehaven-v{version}-Windows11.zip"
    return {"version": version,
            "runtime_sha256": hashlib.sha256((launcher.parent / release_name).read_bytes()).hexdigest(),
            "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
            "environment": f"{os.name}, PowerShell "
            + subprocess.check_output([args.powershell, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"], text=True).strip(),
            "fixture_only": True, "windows_cmd_or_registry_tested": False, "live_github_http_exercised": False,
            "sea_power_executed": False,
            "details": "Stock file names and sections are synthetic; bootstrap network responses and the promotion error are supplied by the test harness.",
            "checks": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("launcher", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--powershell", default="pwsh")
    parser.add_argument("--legacy", type=Path, help="Optional unpacked v0.1.0 package")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="rimehaven-test-") as temporary:
        evidence = run_tests(args, Path(temporary))
    if args.report:
        args.report.write_text(json.dumps(evidence, indent=2) + "\n")
