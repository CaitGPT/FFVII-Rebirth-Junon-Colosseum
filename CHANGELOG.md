# Changelog

## 1.2.1: a clear message for the other 1.005 UE4SS settings

- With the 1.005 UE4SS build from RE-UE4SS FF7R's Files tab, the noticeboard appeared but had no Check point, so
  courses could not start. That build's `VTableLayout.ini` puts version 1.005's extra engine function in a different
  place from where we found it. Most mods never use the functions that affects, but one of them is how the mod's
  helper answers its requests to load the arena. The helper now notices when that happens and says what to change,
  in a window in the game and in UE4SS.log (code JC-UE4SS): in `VTableLayout.ini`'s `[UObject]` section, move the
  line `unk_FF7R_1005_ExtraVirtual` to directly below `FinishDestroy`, or use our
  [UE4SS 1.005 Fix](https://www.nexusmods.com/finalfantasy7rebirth/mods/2521) with the stock UE4SS. A player on the
  Steam version of 1.005 reports the mod works after that change; we reproduced the fault and the fix on the Epic
  Games Store version.

## 1.2.0: game versions we have not seen, and a noticeboard that is there when you arrive

- **Game versions we have not seen.** The mod's helper needs to find certain code in the game. It used to carry
  the addresses of that code for each game version we had looked at, and switch itself off on any other version,
  so courses did not start. It now finds that code in the game itself, by what the instructions are rather than
  where they sit, for everything the colosseum uses: the guards' entry, loading the arena's levels, the arena
  itself and the Mako infusions. A game version that is not in its table can now work. We can only test the two
  versions we have, so this is not a promise, but it is no longer a refusal.
- **It says why it stopped.** If the helper does switch itself off, it now says so in a window in the game, with a
  code to quote, and writes the same line to UE4SS.log. Before, the only sign was a noticeboard that never came.
- **The noticeboard is there when you arrive.** It used to wait for the arena's levels, which took 20 to 30 seconds
  after loading a save in the foyer. It now appears as you arrive, and the colosseum menu opens a second or two
  later. The mod also waits on the game's own loader rather than on a timer, which is both quicker and safer.

## 1.1.0: Epic Games Store version, shorter infusion text

- Works with game version 1.005, the current version on Steam and the Epic Games Store: the archive is rebuilt on
  its tables, and the helper finds its game functions per game version. Tested on the Epic Games Store version; the
  Steam version of 1.005 is not tested yet. On a version it does not recognise, the helper switches its features off
  instead of guessing, so courses do not start but the game runs normally (1.0.0 did not switch off).
- 1.0.0 was built on the January 2025 version of the game, not the current one as its notes said.
- On 1.005, UE4SS 3.0.1 needs a fix: the optional 1.005 file on RE-UE4SS FF7R's Nexus page, or the two UE4SS
  settings files we tested with, offered as a separate download.
- Infusion text is shorter: the tier reads "Rare:" or "Epic:", and materia infusions just name the materia, for
  example "Equip Fire next round" or "Rare: Equip Time next round". Materia reaches your fighters when the game
  rebuilds their stats between rounds, so materia infusions are no longer offered in a course's last round.

## 1.0.0: first public release

The first public release. Everything below is new.

- A post-game colosseum in the Junon arena, entered through the Junon Checkpoint guards with the Junon Colosseum
  Invitation. Roche drops the Invitation in Chapter 11; saves already past that fight receive it at the checkpoint.
  The first entry adds Junon Colosseum to fast travel.
- 14 courses named after Shinra ranks, from Shin'iri to Nandemoya-san. Nine rounds each, bosses in rounds 3, 6 and 9;
  course 14 adds a tenth round with two bosses.
- Fights drawn fresh for every attempt from pools of the game's late-game and legendary rounds. Some rounds combine
  two fights into one, with at most six enemies.
- Enemy health rises course by course, from a gentle opener to final courses with more total enemy health than the
  game's hardest Legendary challenges.
- 13 cumulative rank rules: Rivals, Rally, Riot rush, Bloodlust, Hall of mirrors, Twisted weaknesses, Arms race,
  Time trap, Short rest, Slim pickings, Second wind, Darkside and Encore.
- Darkside (courses 13 and 14) costs 5% of max HP, never below 1 HP, for each use of a weapon, folio or attacking
  command-materia ability; magic, items, limits, synergy and utility commands are free. The mod charges it, and the
  Darkside command switches it off until the next round.
- 77 Mako infusions in three tiers, offered early in every round in the game's own options window: party statuses,
  enemy debuffs, round effects, the effects of 26 real accessories, and materia spells, abilities and stat bonuses.
- Two teams of three, chosen from six, taking turns round by round.
- Maxed materia rewards: one for the first clear of each course, and a pool of up to four for repeat clears.
- A Junon-branded course menu and result screen.
- Works alongside our Training Dummy, Battle Meters and Biome Randomizer mods; the archive carries Training Dummy's
  courses and shows them only when Training Dummy is installed.

## Private playtest builds (not released)

- **0.9.25 (2026-11-11):** the mod charges Darkside's HP cost itself, since neither the status nor the materia did
  in play; checked in play by the owner.
- **0.9.21 to 0.9.24 (2026-11-11):** Darkside gives the Darkside materia, for its HP cost and potency; combined
  two-fight rounds; a balance pass (round pools by enemy health in our arena, two-boss rounds only in the encore, and
  enemy health that rises course by course); Rally replaces Tough hides, which the rising enemy health made redundant.
- **0.9.17 to 0.9.20 (2026-11-11):** stat-up materia infusions; tiers revised; Turbulent Spirit for 60 seconds each
  round; Short rest replaces Wounded; Arms race replaces Mirror match; Second wind restores enemies once instead of
  giving them Reraise, which held battles open; course 1 renamed Shin'iri; hang diagnostics in the helper. All 14
  courses cleared in testing with the development boost.
- **0.9.10 to 0.9.16 (2026-11-10 to 11):** each course ships a unique round list; arena levels stay loaded during a
  course; the helper does engine work only on the game thread at a safe point; level requests that stall are retried;
  infusion labels name what you gain.
- **0.9.5 to 0.9.9 (2026-11-10):** infusion tiers and a round-1 offer; real accessory infusions through the native
  helper; the foyer load crash fixed; the owner's final reward table and rule order.
- **0.9.0 to 0.9.4 (2026-11-10):** the first release-shaped packages: portable paths, no telemetry in player installs,
  compatibility with our other mods, rank names, the arena backdrop and the menu look.
