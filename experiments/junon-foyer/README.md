# Building Junon Colosseum from source

This folder holds everything the mod is built from: the design data, the generators, the Lua scripts, the native
helper's source, our data-table builder and the offline tests. It contains no game files. The build reads the game
tables and packages it changes from your own copy of the game.

For what the mod does, see the [README](../../README.md). For how the parts fit together, see
[How it works](../../docs/HOW-IT-WORKS.md).

## What's here

| Path | What it is |
| --- | --- |
| `data/course-design.json` | The courses: round pools, rank rules, rewards, music, the HP factor per course |
| `data/buffs.json` | The Mako infusions |
| `data/junon-arena.json` | The table spec the archive is built from (generated: edit the design files, then regenerate) |
| `data/round-data.json`, `data/territory-rows.json`, `data/enemy-pool.json` | Names and numbers taken from the game's tables (IDs, levels, HP): the generators' input |
| `data/combined-rounds.json` | The combined rounds' pairs and their allocation to course slots (generated) |
| `data/*-pose.json`, `data/*-store.json` | Positions for the arrival point and the copied arena, and the native package facts the archive registers |
| `tools/` | Generators (`apply_course_design.py`, `make_round_pools.py`, `make_combined_rounds.py`, ...) and the extractors that read the game's tables |
| `tools/DataBuilder/` | Our DataObject table reader and writer, and the level, texture and container packers (C#, .NET 8) |
| `ue4ss/JunonColosseum/Scripts/` | The Lua runtime. `buffwheel_data.lua` is generated. `devtools.lua` is for development and never ships |
| `native/` | The native helper `main.dll` (C++, UE4SS 3.0.1 C++ API) |
| `tests/` | Offline tests of the Lua and the generators |
| `Build-Foyer.ps1`, `Build-Release.ps1`, `Build-NativeIdentity.ps1` | The archive build, the release zip and the helper build |
| `RELEASE-README.txt` | The README inside the release zip |

## Changing the design

1. Edit `data/course-design.json` or `data/buffs.json`.
2. If you changed round pools or HP targets, run `python tools/make_round_pools.py` (it rewrites the course slots
   and HP factors), then `python tools/make_combined_rounds.py`.
3. Run `python tools/apply_course_design.py`. It writes `data/junon-arena.json` and
   `ue4ss/JunonColosseum/Scripts/buffwheel_data.lua`. `--check` reports whether they are up to date without writing.
   `--combined-mode new|repurpose|off` with `--out` and `--lua-out` writes a variant for a test build.
4. Run the tests.

## Tests

The tests run offline, without the game:

```powershell
python -m pip install pytest lupa
cd experiments\junon-foyer
python -m pytest -q tests
```

One test merges our spec with Training Dummy's. It uses Training Dummy's real spec when
`JUNON_TRAINING_DUMMY_SPEC` or `TrainingDummySpec` in `build-config.local.json` names it, and a stand-in row
otherwise.

## What you need to build the archive

- Windows, PowerShell 5.1 or later, Python 3.11 or later, and the .NET 8 SDK.
- [retoc](https://github.com/trumank/retoc) built with its FINAL FANTASY VII REBIRTH patches. It writes the
  archive.
- UnrealReZen. The build takes only its empty `.pak` stub.
- Your own exports from the game:
  - raw `.uasset` exports (FModel) of every table named in `data/junon-arena.json` and in Training Dummy's spec,
    under `End/Content/DataObject/...`;
  - raw zen packages (`retoc get`) of `1300-JUNOA_LevelPlan_MapPoint_Resident`,
    `2360-UNDRS_BattlePlan_Resident`, `2360-UNDRS_BattlePlan_Resident_ServerBuild` and the Gold Saucer menu
    backdrop `U_Com_GoldSaucerArena_Bg1`. The builder checks each against the SHA-256 in the matching
    `data/*-store.json` and refuses a different file.
- Training Dummy's spec, `data/training-dummy.json` from
  [FFVII-Rebirth-Training-Dummy](https://github.com/CaitGPT/FFVII-Rebirth-Training-Dummy). Our archive carries its
  rows, so one package works with or without that mod.
- A 1920x1920 image for the menu backdrop, as BC7 pixels: `texconv -f BC7_UNORM -m 1` (DirectXTex), with the
  148-byte DDS header removed. Ours is a blurred, vignetted screenshot of the Junon arena; it isn't in this
  repository.

## What you need to build the native helper

- Visual Studio 2022 (C++ desktop workload) and its CMake.
- The UE4SS 3.0.1 C++ mod template: RE-UE4SS at v3.0.1 with its submodules, the matching UEPseudo headers (Epic-linked
  GitHub access), and the `imgui` and `ImGuiColorTextEdit` headers.
- `UE4SS.lib`, the import library of the UE4SS 3.0.1 DLL from RE-UE4SS for FF7 Rebirth 1.0.2.

## Build

1. Copy `build-config.example.json` to `build-config.local.json` (Git ignores it) and fill in your paths. Every key
   can also be passed as a parameter of the same name, and `-ConfigPath` points at a config elsewhere.
2. Build the helper:

   ```powershell
   .\Build-NativeIdentity.ps1 -BuildDirectory <new folder>
   ```

   It prints the SHA-256 of `<new folder>\Release\main.dll`.
3. Build the release zip:

   ```powershell
   .\Build-Release.ps1 -ArtifactRoot <new folder> -Version <version> -HelperDll <new folder>\Release\main.dll
   ```

   `Build-Release.ps1` runs `Build-Foyer.ps1` first. That compiles the data-table builder, merges Training Dummy's
   spec with ours, builds every table and checks that each vanilla row is unchanged and each new row is reachable
   through the table's hash buckets. It then adds the arrival point to the Junon layout, copies the prison arena's
   battle-plan pair to Junon, builds the backdrop texture, packs everything with retoc, adds the 16-byte prefix the
   game expects, and unpacks the result again to compare every chunk.

   `Build-Release.ps1` then lays out the zip:

   ```
   End/Content/Paks/~mods/JunonColosseum_999_P.pak, .ucas, .utoc
   End/Binaries/Win64/ue4ss/Mods/JunonColosseum/Scripts/*.lua   (without devtools.lua)
   End/Binaries/Win64/ue4ss/Mods/JunonColosseum/dlls/main.dll
   End/Binaries/Win64/ue4ss/Mods/JunonColosseum/enabled.txt
   README.txt, LICENSE.txt, CHANGELOG.md
   ```

   It refuses a `dev.txt` or `devtools.lua` in the package, a drive-letter path in the scripts and a telemetry path in
   the helper, and writes `JunonColosseum-<version>.zip`, `SHA256SUMS.txt` and `release-manifest.json` in the
   artifact root. The artifact root must be a new folder; the scripts never overwrite an earlier build.

## Development installs

A player install writes no files outside the mod folder except the files the Lua and the helper exchange beside the
scripts. For development, put a `dev.txt` in `Mods/JunonColosseum/` that names a telemetry folder, and copy
`devtools.lua` into `Scripts/`. The mod then writes its logs there (`junon-buffwheel.tsv`, `junon-branding.tsv` and
others) and reads test switches from that folder, such as `junon-testmode.on` (a boost that keeps fighters standing
and starts enemies at reduced health) and `junon-combined.on` (forces course 1's first rounds to combined rounds).

Don't use UE4SS hot reload (Ctrl+R): it crashes this game. Back up your saves before testing.
