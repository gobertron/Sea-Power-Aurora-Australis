"""Verify the release launcher against the unpacked release before publishing."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile


def verify(launcher, package):
    raw = launcher.read_bytes()
    script = raw.decode("ascii")
    if b"\n" in raw.replace(b"\r\n", b""):
        raise ValueError("Launcher is missing Windows line endings")
    boot = re.search(r"(?ms)^::AURORA_BOOTSTRAP::\r?\n(.*?)^::AURORA_PAYLOAD_BASE64::\r?$", script)
    if boot is None or "@@" in boot.group(1):
        raise ValueError("Incomplete Windows bootstrap")
    content = base64.b64decode("".join(script[boot.end():].split()), validate=True)
    actual_digest = hashlib.sha256(content).hexdigest()
    if f"$SeedHash = '{actual_digest}'" not in boot.group(1):
        raise ValueError("Embedded zip hash does not match the bootstrap")
    with ZipFile(io.BytesIO(content)) as z:
        if z.testzip() is not None:
            raise ValueError("Invalid embedded archive CRC")
        manifest = json.loads(z.read("package-manifest.json").decode("utf-8-sig"))
        if f"$SeedVersion = '{manifest['version']}'" not in boot.group(1):
            raise ValueError("Embedded package version does not match bootstrap")
        names = set(z.namelist())
        data_names = {"payload/RAN-Aurora-Australis/" + path for path in manifest["files"]}
        expected_names = data_names | {"scripts/Manage-Aurora.ps1", "package-manifest.json"}
        if len(z.infolist()) != len(names) or names != expected_names:
            raise ValueError("Unexpected embedded archive structure")
        for name in names:
            actual_bytes = z.read(name)
            if actual_bytes != (package / name).read_bytes():
                raise ValueError(f"Archive differs from package at {name}")
            if name in data_names:
                key = name.removeprefix("payload/RAN-Aurora-Australis/")
                if hashlib.sha256(actual_bytes).hexdigest() != manifest["files"][key]:
                    raise ValueError(f"Invalid embedded manifest digest at {key}")
    release_zip = launcher.parent / f"RAN-Rimehaven-v{manifest['version']}-Windows11.zip"
    if release_zip.read_bytes() != content:
        raise ValueError("Published update ZIP differs from the verified seed")
    expected_sidecar = f"{actual_digest}  {release_zip.name}"
    if (launcher.parent / (release_zip.name + ".sha256")).read_text().strip() != expected_sidecar:
        raise ValueError("Release ZIP checksum sidecar differs from the offline seed")
    print(f"Launcher verified. v{manifest['version']}, {len(data_names)} payload files, {len(raw):,} bytes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("launcher", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    verify(args.launcher, args.root)
