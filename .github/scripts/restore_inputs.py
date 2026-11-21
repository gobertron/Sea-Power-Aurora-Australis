"""Restore the frozen metre-scale geometry, rebuild native meshes and verify the runtime."""
import argparse
import base64
import hashlib
import importlib.util
import io
import json
import re
import tarfile
import tempfile
from pathlib import Path

YEARS = (2000, 2010, 2020)


def load_builder(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode(folder, bundle, records):
    record = records[bundle]
    chunks = []
    for part in record["parts"]:
        if Path(part).name != part:
            raise ValueError(f"Invalid release input part {part!r}")
        chunks.append(b"".join((folder / part).read_bytes().split()))
    result = base64.b64decode(b"".join(chunks), validate=True)
    if hashlib.sha256(result).hexdigest() != record["sha256"]:
        raise ValueError(f"Corrupt release input {bundle}")
    return result


def member_files(archive_bytes, expected=None):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:xz") as archive:
        for entry in archive:
            if not entry.isfile() or Path(entry.name).name != entry.name or entry.name in files:
                raise ValueError(f"Unexpected packed file {entry.name!r}")
            if entry.size > 30_000_000 or len(files) > 100:
                raise ValueError("Input archive exceeds the package limits")
            files[entry.name] = archive.extractfile(entry).read()
    if expected is not None and set(files) != expected:
        raise ValueError("Release input archive contents do not match the expected files")
    return files


def materialize(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Conflicting local file {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def restore(root):
    folder = root / "release-inputs"
    records = json.loads((folder / "inputs.json").read_text("ascii"))
    source = root / "source/model"
    cfg = root / "payload/RAN-Aurora-Australis"
    native = load_builder("native_builder", root / "tools/build_native_aurora.py")
    model_files = {"Aurora-Model-Manifest.json"} | {
        f"aurora_{year}.{ext}" for year in YEARS for ext in ("mtl", "obj")
    }
    exports = {"Aurora-Class-Source.blend"} | {f"Aurora-{year}.glb" for year in YEARS}
    for archive, expected in (("native-source.tar.xz", model_files), ("editing-exports.tar.xz", exports)):
        for name, data in member_files(decode(folder, archive, records), expected).items():
            materialize(source / name, data)
    anchors = {}
    design = json.loads((source / "Aurora-Model-Manifest.json").read_text("utf-8"))
    for mount in design["mounts"]:
        anchors[mount["yaw_object"]] = mount["native_base_m"]
        anchors[mount["barrel_object"]] = mount["native_barrel_pivot_m"]
    for prefix, key in (("Propeller", "propeller_anchors_m"), ("Rudder", "rudder_anchors_m")):
        for i, point in enumerate(design[key], 1):
            anchors[prefix + str(i)] = point
    textures = member_files(decode(folder, "textures.tar.xz", records))
    for year in YEARS:
        target = cfg / "ships" / f"ran_agb_aurora_{year}"
        for name, data in textures.items():
            if not re.fullmatch(r"[a-z_]+\.png", name):
                raise ValueError(f"Invalid texture name {name!r}")
            materialize(target / name, data)
        meshes = native.read_obj(source / f"aurora_{year}.obj")
        with tempfile.TemporaryDirectory() as scratch:
            mesh = Path(scratch) / "native.obj"
            native.native_mesh(meshes, anchors, mesh)
            materialize(target / "aurora.obj", mesh.read_bytes().replace(b"\r\n", b"\n"))
    manifest = json.loads((root / "package-manifest.json").read_text("utf-8"))
    actual = {p.relative_to(cfg).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in cfg.rglob("*") if p.is_file()}
    if actual != manifest["files"]:
        wrong = sorted(k for k in set(actual) | set(manifest["files"]) if actual.get(k) != manifest["files"].get(k))
        raise ValueError(f"Native payload differs from the verified package: {wrong}")
    print(f"Restored all {len(actual)} verified game files.")
    # The frozen inset preserves WebP bytes across Pillow and libwebp releases.
    viewer_dir = root / "source/viewer"
    builder = load_builder("preview_builder", viewer_dir / "build_viewer.py")
    models = {str(year): builder.read_obj(source / f"aurora_{year}.obj") for year in YEARS}
    html = (viewer_dir / "viewer-template.html").read_text(encoding="utf-8")
    html = html.replace("__VIEWER_JS__", (viewer_dir / "viewer.js").read_text(encoding="utf-8"))
    html = html.replace("__MODELS__", json.dumps(models, separators=(",", ":")))
    inset = decode(folder, "reviewed-inset.webp", records)
    html = html.replace("__PLATE__", base64.b64encode(inset).decode("ascii"))
    materialize(root / "HMAS-Rimehaven-3D.html", html.encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    restore(parser.parse_args().root.resolve())
