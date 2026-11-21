"""Publish the checked-out Rimehaven version. Run after building dist/."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def run(*args):
    subprocess.run(args, check=True)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    version = json.loads(Path("package-manifest.json").read_text("utf-8-sig"))["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError(f"Invalid release version {version!r}")
    tag = f"v{version}"
    ref = os.environ["GITHUB_REF"]
    if ref not in ("refs/heads/main", "refs/tags/" + tag):
        raise ValueError(f"Ref {ref} does not match release {tag}")
    commit = output("git", "rev-parse", "HEAD")
    archive = f"RAN-Rimehaven-{tag}-Windows11.zip"
    assets = {name: Path("dist", name) for name in (
        "Install-Rimehaven.cmd", archive, archive + ".sha256", "HMAS-Rimehaven-3D.html",
        f"Rimehaven-{tag}-Editable-Source.zip", "Rimehaven-Hull-Study.png"
    )}
    if any(not p.is_file() or not p.stat().st_size for p in assets.values()):
        raise ValueError("Missing or empty release asset")
    if digest(assets[archive]) != assets[archive + ".sha256"].read_text("ascii").split()[0].lower():
        raise ValueError("Release archive checksum mismatch")

    refs = output("git", "ls-remote", "--tags", "origin", "refs/tags/" + tag, "refs/tags/" + tag + "^{}")
    targets = dict(line.split()[::-1] for line in refs.splitlines())
    target = targets.get("refs/tags/" + tag + "^{}", targets.get("refs/tags/" + tag))
    all_releases = output("gh", "api", "--paginate", "repos/" + repository + "/releases",
                          "--jq", ".[] | {tag_name, draft, prerelease, target_commitish} | @json")
    releases = [json.loads(line) for line in all_releases.splitlines()]
    release = next((r for r in releases if r["tag_name"] == tag), None)
    if release and not release["draft"] and target:
        if ref.startswith("refs/tags/") and target != commit:
            raise ValueError(f"{tag} points to another commit")
        print(f"{tag} already published at {target}.")
        return
    if target and target != commit:
        raise ValueError(f"{tag} points to another commit")
    if release and (not release["draft"] or release["target_commitish"] != commit):
        raise ValueError("Release target mismatch, or published release with a missing tag")

    if not target:
        run("gh", "api", "--method", "POST", "repos/" + repository + "/git/refs",
            "-f", "ref=refs/tags/" + tag, "-f", "sha=" + commit)
    if not release:
        changelog = Path("CHANGELOG.md").read_text("utf-8").splitlines()
        row = next(line for line in changelog if line.startswith(f"| {version} |"))
        _, changes, status = [cell.strip() for cell in row.strip("|").split("|")]
        qa = json.loads(Path("validation/RELEASE-CHECKS.json").read_text("utf-8"))
        notes = ("Install or update by double-clicking **Install-Rimehaven.cmd**.\n\n"
                 + changes + "\n\n" + status + " " + qa["game_target"]
                 + "\n\nIncluded downloads cover the game files, SHA-256 checksum, "
                   "interactive 3D model, illustrated hull study and editable Blender source.")
        run("gh", "release", "create", tag, "--draft", "--verify-tag", "--target", commit,
            "--title", f"HMAS Rimehaven {tag}", "--notes", notes)

    run("gh", "release", "upload", tag, *map(str, assets.values()), "--clobber")
    with tempfile.TemporaryDirectory() as directory:
        run("gh", "release", "download", tag, "--dir", directory)
        for name, path in assets.items():
            if digest(path) != digest(Path(directory, name)):
                raise ValueError(f"Uploaded asset checksum mismatch for {name}")

    newer = any(
        tuple(map(int, r["tag_name"][1:].split("."))) > tuple(map(int, version.split(".")))
        for r in releases
        if not r["draft"] and not r["prerelease"] and re.fullmatch(r"v\d+\.\d+\.\d+", r["tag_name"])
    )
    run("gh", "release", "edit", tag, "--draft=false", "--latest=" + str(not newer).lower())
    print(output("gh", "release", "view", tag, "--json", "url", "--jq", ".url"))


if __name__ == "__main__":
    main()
