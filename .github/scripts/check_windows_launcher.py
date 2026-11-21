"""Exercise the released CMD using cmd.exe and Windows PowerShell on a disposable fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "release-tools"))
from test_installer import fixture, tree_hash


def main():
    if os.name != "nt":
        raise RuntimeError("A Windows runner is required")
    version = json.loads((ROOT / "package-manifest.json").read_text("utf-8-sig"))["version"]
    mod = "RAN-Aurora-Australis"
    dependencies = json.loads((ROOT / "payload" / mod / "DEPENDENCIES.json").read_text("utf-8"))
    launcher = ROOT / "dist" / "Install-Rimehaven.cmd"
    with tempfile.TemporaryDirectory(prefix="Rimehaven CMD ") as tmp:
        work = Path(tmp)
        game = fixture(work / "Alternate Library" / "steamapps", dependencies)
        local = work / "Local AppData"
        logs = local / mod / "Logs"
        installed = game / "Sea Power_Data" / "StreamingAssets" / mod
        env = dict(os.environ, LOCALAPPDATA=str(local), AURORA_NO_PAUSE="1")
        for operation in ("install", "already_installed"):
            old_reports = set(logs.glob("*.json"))
            before = tree_hash(installed)
            subprocess.run([os.environ["COMSPEC"], "/d", "/c", "call", str(launcher), str(game)],
                           env=env, check=True, timeout=300)
            reports = set(logs.glob("*.json")) - old_reports
            if len(reports) != 1:
                raise RuntimeError("Expected one new installation report")
            report = json.loads(reports.pop().read_text("utf-8-sig"))
            if not (report["success"] and report["operation"] == operation and
                    report["installed_version"] == version and Path(report["game_path"]) == game):
                raise RuntimeError(f"Unexpected installer result for {operation}")
            if operation == "already_installed" and (report["backup_path"] or tree_hash(installed) != before):
                raise RuntimeError("Second CMD launch unexpectedly modified the fixture")
            print(f"Windows CMD, PowerShell 5.1, fixture, {operation}: passed", flush=True)


if __name__ == "__main__":
    main()
