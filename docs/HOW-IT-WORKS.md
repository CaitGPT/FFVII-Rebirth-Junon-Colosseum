# How Junon Colosseum works

The finished design, as a reference for modders. For the story of how it was built, see
[HOW-WE-BUILT-IT.md](HOW-WE-BUILT-IT.md). Every claim here comes from a dated observation in our development log;
anything not yet seen in the game is marked.

**How sure:** ✅ seen working in the game · 🟡 partly seen, or built and not yet checked in the game

## The parts

| Part | Where | What it does |
| --- | --- | --- |
| Data archive `JunonColosseum_999_P` | `experiments/junon-foyer/data/` (spec), `Build-Foyer.ps1` | New and changed table rows, a copy of an arena level pair, the menu backdrop texture |
| Lua scripts | `experiments/junon-foyer/ue4ss/JunonColosseum/Scripts/` | The gate, the foyer board, level loading, rank rules, infusions, branding |
| Native helper `dlls/main.dll` | `experiments/junon-foyer/native/src/main.cpp` | Game calls Lua can't make safely: level loads, arena readiness, round shuffles, accessory infusions |
| Generators | `experiments/junon-foyer/tools/` | Turn the design files into table rows and Lua data |
| Tests | `experiments/junon-foyer/tests/` | Offline tests of the Lua and generators (180 at the last count) |

The design lives in two files: `data/course-design.json` (courses, round pools, rank rules, rewards, music) and
`data/buffs.json` (the Mako infusions). `tools/apply_course_design.py` writes both into the table spec
`data/junon-arena.json` and the generated Lua data `Scripts/buffwheel_data.lua`. Edit the design files, never the
generated ones.

## Tables

The archive replaces whole tables, so any other mod that replaces one of these conflicts with it.

| Table | Our rows | What for |
| --- | --- | --- |
| `Colosseum` | 14 courses, `COL30_JUNON_01_Free_Col` to `_14_` | The courses, with their round lists, rewards and unlock flags. ✅ |
| `ColosseumPositionData` | `POS_Mod_JunonColosseum` | Where the party stands in the arena. ✅ |
| `Reward`, `RewardRandom` | 55 and 14 | First-clear materia and the repeat-clear pools, using the game's own weighted draw. ✅ every first clear; repeat draws seen on courses 1, 2 and 8 |
| `StoryFlag` | 23 | Clear flags, the Invitation, discovery, the Training Dummy display flag. ✅ |
| `Item` | `key_Mod_JunonColosseumInvitation` (index 3902) | The Invitation key item, with the Birdhouse Locations memo's look. ✅ |
| `BattleItemPossession` | `modJunon_Chapter11Roche_Drops` | Roche's Chapter 11 fight drops the Invitation. 🟡 |
| `BattleCharaSpec` | 929 | Two Roche variants carrying the drop, and 927 stat clones in six sets (`<spec>_JC02`, `_JC05`, `_JC07`, `_JC10`, `_JC11`, `_JC13`) carrying each course's HP factor and, from `_JC07`, Twisted weaknesses. ✅ |
| `EnemyTerritory`, `EnemyTerritoryLevel` | one pair per combined round | Combined rounds: two simulator rounds' enemy lists in one row. The build either rewrites spare simulator rows or adds new ones (`apply_course_design.py --combined-mode`). ✅ |
| `Equipment` | 6 carrier rows, `E_ACC_8xxx` and `E_ACC_7106` | Accessories that carry a materia for infusions and the Darkside rule. 🟡 |
| `Hub`, `MapIconInfo` | 1 each | The Junon Colosseum fast-travel destination. ✅ |
| `Action`, `ActionGroup`, `PlannerEvent`, `StateChange`, `StateTrigger` and their resident and Junon copies | about 80 | The guards' new choice, the entry fade and jump, the arrival grant of the Invitation. ✅ (the arrival grant 🟡) |
| `BulletinBoard` | `oblMod_JunonColosseum_Noticeboard` | The course board. ✅ |
| `Object`, `ResidentObject`, `ObjectEntryAttributeList` | 1 each | A resident flow object for the guard sequence. ✅ |
| `Field/1350-JNONT/ObjectEnemyTerritory`, `StateChange` | 1 and 2 | Keeps a story-only enemy group out of the post-game arena. ✅ |

The archive also carries Training Dummy's rows in the five tables both mods replace (`Colosseum`,
`ColosseumPositionData`, `EnemyTerritory`, `EnemyTerritoryLevel`, `EnemyParameter`). It holds 34 paths in all,
including five new package registrations: the copied arena level pair, staged under both Junon map folders, and the
backdrop texture.

New rows are clones of existing rows with chosen fields changed. The builder, our DataObject reader and writer, checks
that every vanilla row is unchanged and every new row is reachable through the table's hash buckets.

## Getting in

- **The gate** (`gate.lua`). The colosseum opens on saves at chapter progress 12000 or more (Chapter 12). Saves past
  11805 (after Roche's Chapter 11 fight) or with chapter select unlocked count as having beaten Roche. Earlier
  chapters, including chapter replays, keep the story as it was. ✅
- **The Invitation.** Roche's two Chapter 11 specs (both phases) drop it. 🟡 not yet seen in play. On a save already past
  that fight without one, the first gate guard's idle state turns into a grant when the player arrives, with the
  game's own "Obtained" message. 🟡 Chapter 4's Roche uses other specs and never drops it.
- **The guards.** Both Shinra guards at the Junon Checkpoint get a new choice, *Show Colosseum Invitation*, through
  cloned Action rows. It fades to black and moves the player to the foyer. ✅
- **Fast travel.** A new Hub and map icon at an existing anchor point. The first entry earns it, and only once the
  player has landed and settled within 3 m of the arrival point (`flow.lua`). ✅
- **The board** (`foyer.lua`). A full-size quest board replaces a redundant lever to the right of the foyer door, with
  a Check point on its face. After a save made in the foyer the board's mesh isn't loaded yet, so the native helper
  loads it. ✅

## The arena

The game's colosseum fights need a *battle plan* level: a territory actor, spawn points and cameras. Junon's arena has
none for colosseum use, so the archive carries a copy of the prison colosseum's plan pair, moved to the Junon arena:

- `2360-UNDRS_BattlePlan_Resident`, copied as `1300-JUNOA_BattlePlan_ModJunonColosseum`, with its public World identity
  re-keyed and exactly 20 world positions moved (`tools/DataBuilder/BattlePlanPack.cs`).
- Its `_ServerBuild` partner, which holds the enemy spawn lists. Without it, no enemy can spawn.

`battle_plan.lua` asks the native helper to stream these levels (and Junon town's battle navigation) after the world
has finished streaming, and keeps them loaded while a course is in progress.

Three fixes make battles start there, all in the helper or Lua:

| Problem | Fix |
| --- | --- |
| The game never marks a level a mod streamed as *Ready* for battle, so every round waited on "Get Ready" | `ArenaReady` links the territory to its ServerBuild actor with the game's own weak-pointer setter, once per round ✅ |
| Three Mu rounds use fixed pop points that exist only in the simulator | `ArenaReady` clears `UsePopTargetPoint` on those rows during our courses and restores it 3 s after ✅ |
| Gold Saucer-sized spawn offsets (up to 26 m) put enemies outside Junon's 20 m ring | `foyer.lua` scales every spawn list to 12 m; `leash.lua` returns an enemy that stays outside the ring ✅ |

## Courses and rounds

- **Round pools.** `tools/make_round_pools.py` builds the pools from the game's own end-game rounds: the Gold
  Saucer's Musclehead courses, Chadley's Brutal and Legendary challenges and the regional legendary fiends. Summons,
  Sephiroth and simulator-staged rounds are left out. A round's weight is its enemies' total HP in our arena: each
  enemy's spec HP times the game's level factor (`EnemyParameter`) at its listed level or 67, whichever is higher;
  wave enemies don't count. Normal slots (1, 2, 4, 5, 7 and 8) hold 8 rounds and boss slots (3, 6 and 9) hold 10.
  Medians rise slot by slot and course by course, every boss slot sits above its neighbours, and no normal slot holds
  a round above the next boss slot's median. Rounds with two bosses are drawn only by course 14's encore. The pools
  use 109 different rounds.
- **Combined rounds.** Some rounds combine two fights into one: one `EnemyTerritory` row holds both rounds' enemy
  lists, and the first round's level row its settings (`tools/make_combined_rounds.py`). A pair has at most 6
  enemies, 5 distinct specs with none shared, 1 large enemy, 2 flyers and one half that calls waves, and never mixes
  level-synced fiends with fixed levels. A pair aims at 1.5 times its slot's median HP and never exceeds the next
  boss slot's median; a boss slot pairs its boss with a few adds, never a second boss. Combined rounds make up about
  a quarter of a slot's pool (`course-design.json` `combined.share`), after its single rounds. Their territory names
  look like any simulator round's, so the draw, the helper and the rank rules handle them unchanged. ✅
- **Rising enemy health.** Each course has a hidden HP factor (`hp_factor` in `course-design.json`): 1 on course 1,
  1.25 on courses 2 to 4, 1.5 on 5 and 6, 1.75 on 7 to 9, 2 on 10, 2.25 on 11 and 12, and 2.5 on 13 and 14. With
  it, a course's median total enemy health rises from about 0.52 million on course 1 to about 2 million on course 14.
  The game's hardest Legendary challenges, "Bonds of Friendship" and "To Be a Hero", total about 1.25 and 1.2
  million at level 70. The factor is carried by the `_JCnn` spec clones, which courses share in steps of 0.25. No
  rank rule names it.
- **Draws.** The Lua draws all 14 courses at start-up and after every course, and writes them to
  `junon-rounds.req`. The native helper (`RoundShuffle`) finds each course's round list in the loaded `Colosseum`
  table by its contents and overwrites it. Every course ships a unique list so they can't be confused. ✅
- **Round cap.** The game allows at most 10 rounds per course.
- **Two teams.** Courses use the game's two-team mode: pick six, teams of three alternate. A course ends on the result
  screen, not when a field pawn reappears, since the waiting team's leader is a field pawn between rounds. ✅
- **Music.** Every course uses the same per-round battle music list.

## Rank rules

Rules are cumulative and implemented in `buffwheel.lua`, from data in `buffwheel_data.lua`.

| Rule | How |
| --- | --- |
| Rivals | Each enemy gets one random status from the enemy boon list (Haste, Protect, Shell, Brave, Faith, Regen, Barrier, Manaward, Reflect, Critical up) 2 s after it appears, so its own set-up doesn't overwrite it ✅ |
| Rally | When the enemy count drops, every surviving enemy of the round gets one boon from the same list per fall, preferring one it doesn't have yet; an enemy not yet set up gets its boon when it is. The last enemy's fall rallies nobody ✅ (logged in play) |
| Course HP factor, Twisted weaknesses | `SetOverrideBattleCharaSpec` swaps each enemy, 2 s after it appears, to the course's cloned spec: HP times the course's factor, and from course 7 weaknesses turned to absorb ✅ |
| Riot rush, Bloodlust | Haste on enemies; Berserk on the party ✅ |
| Hall of mirrors | Reflect on enemies for the first 60 s of each round ✅ |
| Arms race | Each infusion taken adds one boon to a list every enemy gets for the rest of the course 🟡 |
| Time trap | Stop on one fighter every 30 fight seconds ✅ |
| Short rest | Records each fighter's HP and MP at the end of its round and caps the next start at that plus 20% HP and 15% MP, with `SetHPPercent` and `BPSetPlayerMP` ✅ (MP from logs; a spell after a cut took MP from the cut value) |
| Slim pickings | Two-infusion offers ✅ |
| Second wind | A once-a-second watcher: an enemy first seen below 20% HP is set to 50% once ✅ (courses 12 to 14 cleared with it) |
| Darkside | `BSC_Dark` at every round start, plus the Darkside materia at level 5 through the carrier accessory `E_ACC_7106`. The game puts Darkside's HP cost (5% per ability) and extra potency on the materia, not on the status. The materia also brings its command, so a fighter can switch Darkside off until the next round 🟡 (the carrier was sent in play; the HP cost and potency not yet measured) |
| Encore | Course 14's tenth round, two bosses ✅ |

## Mako infusions

- **The window.** `UEndMenuAPI.ShowMessageWindow` opens the game's own options window from Lua, in battle, with our
  text. Its pause flag doesn't stop a battle, so the Lua pauses the game with `SetGamePaused` while it is open. ✅
- **The offer.** About a second into each round. Each option draws a tier (common 60, rare 30, epic 10; after a boss
  round 20, 40, 40), then an infusion of that tier not taken or already offered. A refusal is allowed.
- **Statuses and specials** go on with `AddStatusChangeID`, again at every round start or whenever they lapse.
- **Accessory infusions** (`InfusionSkills` in the helper). The Lua writes the run's picks to `junon-infusions.req`.
  The helper adds each accessory's skill rows to every party member's equipment-skill map under our own key, with the
  game's own row function, and runs the game's parameter rebuild between rounds. A materia earring's spells appeared in
  a fighter's Spells list. ✅ Most other accessory effects aren't visible in our logs and haven't been checked one by
  one. 🟡
- **Materia carriers.** The game has earrings for only some materia. For the others the archive adds clones of the
  HP Up Materia Earrings naming another materia: `E_ACC_8nnn` for `M_IND_nnn`, `E_ACC_7nnn` for `M_COM_nnn`. Vanilla
  has no rows in those ranges.
- Nothing is saved. A course starts with no infusions and its end removes them all.

## Rewards and branding

- Rewards are `Reward` rows with materia at its `LvMax`, and `RewardRandom` pools for repeat clears. The board names the
  first-clear reward; each course text lists the repeat-clear materia.
- `branding.lua` re-themes the game's colosseum menu (`VR_Top_C`, theme 3) and result screen (`VR_Result_C`): our
  title, colours and an arena backdrop. The backdrop is a texture package cloned from the Gold Saucer's with new
  pixels (`TexturePack.cs`). Menus are branded from hooks on their own set-up calls so the old look doesn't flash. ✅

## The native helper

UE4SS 3.0.1 can't safely make some of the calls this mod needs from Lua, so a C++ helper makes them. Lua and the
helper talk through small files in the mod folder and through *markers*: transient actors whose names carry a request.

- **Thread safety.** This game calls ProcessEvent from task-graph worker threads, and UE4SS runs our Lua ticks and
  ProcessEvent callbacks on whichever thread calls next. A level load from a worker crashed the game. The helper
  checks the loader's per-thread state and serves engine work only on the game thread, at a safe point: the
  ProcessEvent of a Blueprint tick or a camera update, one unit of work per frame, and only while the package loader
  is idle. ✅
- **Version check.** Before patching or calling into game code, the helper compares the first bytes of each function it
  uses with this game build. On a mismatch it switches that feature off and says why in its acknowledgement file.
- **Level loads.** `LevelStreamingDynamic.LoadLevelInstance` through reflection, with its parameters read from the
  function's reflected layout. A Lua call fails in UE4SS 3.0.1 because of its `bool` out-parameter.

## Release package

`experiments/junon-foyer/Build-Release.ps1` runs the full archive build (`Build-Foyer.ps1`), then lays out
`End/Content/Paks/~mods/` and `End/Binaries/Win64/ue4ss/Mods/JunonColosseum/`. It leaves out development-only files
(`devtools.lua`, `dev.txt`), refuses machine paths in the scripts or a telemetry path in the helper, and writes the
zip, `SHA256SUMS.txt` and `release-manifest.json`.

The archive build stages every raw package, registers the new ones in the game's container header, packs with the
FF7R build of retoc, prepends the 16-byte prefix the game expects (shifting every block offset), then verifies and
unpacks the result and compares every chunk. Without a `dev.txt` the mod writes no telemetry and reads no test
switches.

## What was tested

- All 14 courses cleared in the game, on builds 0.9.17 to 0.9.20, with a development boost: fighters that couldn't
  fall and enemies that started at 30% HP and drained. First-clear rewards arrived on every course; repeat-clear draws
  were seen on courses 1, 2 and 8.
- Combined rounds (build 0.9.22, boosted): course 1's first three rounds forced to combined rounds; both groups were
  in the arena at once (the logs counted 6, 3 and 3 enemies, as expected).
- Combined rounds as new rows (build 0.9.24, boosted): course 2 played unforced, drawing one combined round, and
  course 1 with three forced combined rounds (6, 3 and 3 enemies); each round ended only when both groups were down,
  with no hang.
- Rally and the course HP factor (build 0.9.23, boosted): course 3 cleared, its first round a combined round with 6
  enemies, with one boon per survivor logged at each fall.
- Every enemy category in the game's 387 simulator rounds spawned in the arena in a survey, including Mu, Titan, Odin
  and Gilgamesh.
- Eight clean loads into the foyer in a row after the load-crash fix.
- Most later testing ran on a game install with Training Dummy 1.2.0, Battle Meters 1.1.0 and Biome Randomizer 1.1.0
  installed and enabled beside this mod.

Not yet checked in the game: Roche's Chapter 11 drop, the arrival grant, a Chapter 4 visit to the checkpoint, the
Darkside materia's HP cost and potency, Turbulent Spirit's 60 s, most accessory effects, and unboosted balance beyond
course 1.

## Limits

- Rarely, the game stops on a black "Get Ready" or loading screen and never continues. We have seen it in the game's
  own Combat Simulator fights too, without our courses. Restarting the game recovers. The helper logs the package
  loader's state when a round's enemies don't appear.
- A course has at most 10 rounds.
- The helper is tied to UE4SS 3.0.1 and this game build.
- Infusions don't carry between courses, by design.
