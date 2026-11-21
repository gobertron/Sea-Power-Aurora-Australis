# HMAS Rimehaven

**White Meridian-class Antarctic patrol icebreaker for Sea Power · v0.2.0**

Rimehaven is a fictional Australian nuclear-electric patrol and support ship. Pick the 2000, 2010 or 2020 fit in the Mission Editor. Each uses the same 160 m hull with its own topside equipment. The repository and internal IDs retain the original mod identity for scenario and installer compatibility.

## Install on Windows 11

1. Close Sea Power. Download **Install-Rimehaven.cmd** from the latest release and double-click it. Keep this file and run it again for updates.
2. Open Sea Power, enable the Rimehaven mod in Mods and restart the game.
3. Open a disposable Mission Editor scenario dated 2020 or later. Under Australia, select the White Meridian-class icebreaker and the fit year you want. Place it and start the scenario.

The launcher searches Steam libraries across drives. If it prompts, select the directory containing Sea Power.exe. It checks the package, installed dependencies and staged files before replacing the platform. On failure, use the log path printed by the launcher. The previous mod folder name RAN-Aurora-Australis is intentional.

[Latest release](https://github.com/gobertron/Sea-Power-Aurora-Australis/releases/latest) · [Reusable Windows launcher](https://github.com/gobertron/Sea-Power-Aurora-Australis/releases/latest/download/Install-Rimehaven.cmd)

## Polar design

Underwater inspection shows how the rising forefoot meets the design waterline and how the shoulders broaden into the full beam. The flanks carry a visible ice belt. The enclosed bridge, boats, cargo-handling gear and aft helicopter facilities support the ship's fisheries, logistics and rescue roles.

The game files configure an 18-knot open-water maximum. Ice thickness, channel formation and level-ice speed have no working simulation in this mod. The SAR pad and hangar are visual facilities. The three era choices are prebuilt configurations selected before play.

See docs/DESIGN-BRIEF.txt for the real-ship comparisons, docs/GAME-TEST.txt for the outstanding in-game checks, and CHANGELOG.md for the version history.

## Editable files

Download the editable-source ZIP from the release for the Blender project and source meshes. From a Git checkout, run `python .github/scripts/restore_inputs.py` once with Python 3.12 or later to expand the archived model files. See docs/BUILD-SOURCE.txt to rebuild the runtime, launcher and viewer.
