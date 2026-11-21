"""Export reproducible, editable model sources and documentation after restoring release inputs."""
import argparse
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def build(root, dist):
    version = json.loads((root / "package-manifest.json").read_text("utf-8-sig"))["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid package version")
    sources = set()
    for directory in ("source", "docs", "scripts", "tools", "release-tools", "validation"):
        sources.update(p for p in (root / directory).rglob("*") if p.is_file())
    for pattern in ("README*", "LICENSE*", "CHANGELOG*", "START-HERE*", "package-manifest.json"):
        sources.update(p for p in root.glob(pattern) if p.is_file())
    if not (root / "source/model/build_aurora.py").is_file() or not any(p.suffix == ".blend" for p in sources):
        raise ValueError("Missing editable Blender source or model generator")
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / f"Rimehaven-v{version}-Editable-Source.zip"
    with ZipFile(target, "w") as out:
        for path in sorted(sources):
            rel = path.relative_to(root)
            if "__pycache__" in rel.parts or path.suffix in (".pyc", ".blend1"):
                continue
            info = ZipInfo(rel.as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            out.writestr(info, path.read_bytes())
    print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    build(args.root, args.dist)
