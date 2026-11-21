"""Build the reusable Windows launcher with a verified native offline seed."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

TOOLS = Path(__file__).resolve().parent
DEFAULT_REPOSITORY = "gobertron/Sea-Power-Aurora-Australis"

HEADER = r"""@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "AURORA_LAUNCH_PATH=%~f0"
set "AURORA_GAME_PATH=%~1"
if /i "%~1"=="-GamePath" set "AURORA_GAME_PATH=%~2"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';$t=[IO.File]::ReadAllText($env:AURORA_LAUNCH_PATH);$m=[regex]::Match($t,'(?ms)^::AURORA_BOOTSTRAP::\r?\n(.*?)^::AURORA_PAYLOAD_BASE64::\r?$');if(-not $m.Success){throw 'Rimehaven launcher incomplete'};$global:AuroraResult=1;& ([scriptblock]::Create($m.Groups[1].Value));exit $global:AuroraResult"
set "AURORA_RESULT=%ERRORLEVEL%"
if not defined AURORA_NO_PAUSE pause
exit /b %AURORA_RESULT%
::AURORA_BOOTSTRAP::
"""


def build(package, repository, output):
    if not re.fullmatch(r"[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+", repository):
        raise ValueError("Expected repository owner/name")
    manifest = json.loads((package / "package-manifest.json").read_text("utf-8-sig"))
    version = manifest["version"]
    if manifest["mod_id"] != "ran_aurora_australis" or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Unexpected package manifest")
    installer_source = (package / "scripts/Manage-Aurora.ps1").read_text("utf-8-sig")
    if f"$Version = '{version}'" not in installer_source:
        raise ValueError("Installer manager and manifest versions differ")
    payload = package / "payload/RAN-Aurora-Australis"
    actual = {p.relative_to(payload).as_posix() for p in payload.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]):
        raise ValueError("Payload directory and manifest list different files")
    paths = ["package-manifest.json", "scripts/Manage-Aurora.ps1"]
    for relative, digest in sorted(manifest["files"].items()):
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts or "\\" in relative:
            raise ValueError(f"Invalid payload path: {relative}")
        path = "payload/RAN-Aurora-Australis/" + relative
        if hashlib.sha256((package / path).read_bytes()).hexdigest() != digest.lower():
            raise ValueError(f"Payload hash mismatch for {relative}")
        paths.append(path)
    packed = io.BytesIO()
    with ZipFile(packed, "w") as archive:
        for name in paths:
            entry = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, (package / name).read_bytes())
    data = packed.getvalue()
    seed_hash = hashlib.sha256(data).hexdigest()
    script = (TOOLS / "Bootstrap-Aurora.ps1").read_text().replace("@@VERSION@@", version)
    script = script.replace("@@REPOSITORY@@", repository).replace("@@SEED_SHA256@@", seed_hash)
    body = HEADER + script + "\n::AURORA_PAYLOAD_BASE64::\n"
    encoded = base64.b64encode(data).decode("ascii")
    body += "\n".join(encoded[i : i + 120] for i in range(0, len(encoded), 120)) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    release_zip = output.parent / f"RAN-Rimehaven-v{version}-Windows11.zip"
    release_zip.write_bytes(data)
    (output.parent / (release_zip.name + ".sha256")).write_bytes(
        f"{seed_hash}  {release_zip.name}\n".encode("ascii")
    )
    output.write_bytes(body.replace("\n", "\r\n").encode("ascii"))
    print(f"{output}: v{version}; {len(paths)} seed files; SHA256 {seed_hash}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=TOOLS.parent)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.root, args.repository, args.output)
