# Changelog

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
