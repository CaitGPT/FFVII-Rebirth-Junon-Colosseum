# FFVII Rebirth Junon Colosseum

A FINAL FANTASY VII REBIRTH PC mod that opens a post-game colosseum in Junon. Fourteen courses of nine rounds draw
their fights from pools of the game's toughest encounters, every course adds a rule to the ones before it, and in
every round you choose a Mako infusion: a buff, an enemy debuff or an accessory's effect that lasts until the course
ends. Clearing a course earns a maxed materia.

AI coding agents built this mod. Codex (OpenAI) started it with the Junon gate, the fast-travel entry and the
foyer; Claude Opus 5.5 (Anthropic, in Claude Code) took over, got battles running in the arena and built the courses,
rules, infusions and rewards. The channel owner set the design and playtested it. [How we built it](docs/HOW-WE-BUILT-IT.md)
tells the story, dead ends included.

[Nexus Mods page](https://www.nexusmods.com/finalfantasy7rebirth/mods/2511) ·
[Download from GitHub releases](https://github.com/CaitGPT/FFVII-Rebirth-Junon-Colosseum/releases) ·
Videos: [the mod](https://www.youtube.com/watch?v=a3EVJoSZH5w) and [how we built it](https://www.youtube.com/watch?v=8nV0J4ykAuc)

## What it adds

- **A colosseum in the Junon arena.** Fights take place in Junon's arena, where Roche is fought, the way Musclehead's
  fights take place in the Gold Saucer. The course menu and result screen carry our own Junon Colosseum look.
- **14 courses.** Each has 9 rounds, with bosses in rounds 3, 6 and 9. The last course adds a 10th round with two
  bosses at once.
- **Fights drawn fresh for every attempt.** Each round slot has its own pool of about ten fights, taken from the
  game's own late-game and legendary encounters. Later slots and later courses draw harder fights. Some rounds
  combine two fights into one: two of the game's encounters in the arena at once, never more than six enemies.
- **Rising difficulty.** Enemy health rises course by course, from a gentle opener to final courses with more total
  enemy health than the game's hardest Legendary challenges. The course board doesn't show this.
- **Rank rules.** Each course is a Shinra rank and adds one rule to all the rules before it (see the table below).
- **Mako infusions.** Early in every round the battle pauses and offers three infusions (two on course 11 and later).
  Take one, or refuse them all. An infusion lasts until the course ends and is never offered twice in one course.
- **Two teams.** Pick six party members. Two teams of three take turns, round by round.
- **Maxed materia rewards.** The first clear of a course gives its listed materia; later clears give one of up to
  four at random. Each course's description lists them.

## Requirements

- FINAL FANTASY VII REBIRTH for PC (Steam).
- [RE-UE4SS for FF7 Rebirth](https://www.nexusmods.com/finalfantasy7rebirth/mods/267) **1.0.2** (UE4SS 3.0.1). The
  mod includes a small native helper built for that loader. It checks the game code it relies on before acting and
  switches itself off if that code has changed (after a game update, for example).
- A save in **Chapter 12 or later**, past the Roche fight in Chapter 11. The colosseum stays closed in earlier
  chapters, including chapter replays.

## Install

1. Close the game. Back up your saves.
2. Extract the release zip into the game folder, the one that holds `End`. It adds:
   - `End/Content/Paks/~mods/JunonColosseum_999_P.pak`, `.ucas` and `.utoc`
   - `End/Binaries/Win64/ue4ss/Mods/JunonColosseum/` (scripts, the native helper `dlls/main.dll` and `enabled.txt`)
   - `README.txt`, `LICENSE.txt` and `CHANGELOG.md` beside `End`, which you can delete
3. If `End/Binaries/Win64/ue4ss/Mods/mods.txt` lists `JunonColosseum : 0`, change it to `1`. Otherwise the included
   `enabled.txt` turns the mod on.

## Uninstall

Close the game, then delete the three `JunonColosseum_999_P` files and the `Mods/JunonColosseum` folder.

A save made with the mod keeps the Invitation and the mod's progress flags. We have not tested loading such a save
without the mod, so keep a backup from before you installed it.

## How to play

1. **Get the Invitation.** Defeat Roche in Chapter 11 and the *Junon Colosseum Invitation* drops (Key Items). On a
   save already past that fight, walk up to the two Shinra guards at the Junon Checkpoint and one of them hands it
   over.
2. **Enter.** In Chapter 12 or later, talk to either guard at the Junon Checkpoint and choose *Show Colosseum
   Invitation*. The screen fades and you arrive in the arena foyer. The first entry adds **Junon Colosseum** to fast
   travel.
3. **Choose a course.** The course board stands to the right of the foyer door. Check it to open the course menu.
   Course 1 is open; clearing a course opens the next. Cleared courses can be replayed.
4. **Fight.** Pick six fighters for two teams of three. Items can't be used in courses. Early in each round a window
   offers Mako infusions; the game is paused while it is open.

## Courses

Every rule applies on its own course and on every course after it.

| # | Course | Rule it adds | First clear | Repeat clears (one at random) |
| --- | --- | --- | --- | --- |
| 1 | Shin'iri (新入り, "newcomer") | none | Chakra | Prayer, Revival, Reraise, Cleansing |
| 2 | Security Officer | **Rivals:** every enemy starts each round with a random Mako infusion | First Strike | Strength Up, Speed Up, Magic Up |
| 3 | Riot Trooper | **Rally:** whenever an enemy falls, every surviving enemy gains a random Mako infusion | Warding | Precision Defense Focus, Steadfast Block |
| 4 | Grenadier | **Riot rush:** enemies are hasted all course | ATK⇔MATK | Fire, Wind, Lightning, Ice |
| 5 | Elite Security Officer | **Bloodlust:** your fighters are berserk all course, dealing and taking more damage | ATB Stagger | Morph, Gambler, Jump |
| 6 | Elite Riot Officer | **Hall of mirrors:** enemies reflect spells for the first 60 seconds of each round | VIT⇔SPR | Vitality Up, Spirit Up |
| 7 | Elite Grenadier | **Twisted weaknesses:** enemies absorb the elements they were weak to | HP⇔MP | Fire and Ice, Lightning and Wind, Poison and Petrify, Gravity |
| 8 | Rookie Turk | **Arms race:** for every infusion you take, the enemies gain one too for the rest of the course | Limit Support | Empowerment, Time |
| 9 | Veteran Turk | **Time trap:** every 30 seconds, one of your fighters is stopped | ATB Assist | Limit Siphon, Synergy Support |
| 10 | Director of the Turks | **Short rest:** between rounds your fighters recover only 20% HP and 15% MP (the game's own colosseum restores 50% and 30%) | Enemy Skill | Subversion, Provoke, Poison, Steal |
| 11 | SOLDIER Third Class | **Slim pickings:** only two infusions to choose from | ATB Boost | HP Absorption, MP Absorption |
| 12 | SOLDIER Second Class | **Second wind:** every enemy recovers to half health once, the first time it drops below 20% HP | Swiftcast | Magic Focus, Magic Efficiency |
| 13 | SOLDIER First Class | **Darkside:** your fighters start every round in Darkside: abilities hit 20% harder but cost 5% HP each | Darkside | Comet, Skill Master, Magnify |
| 14 | Nandemoya-san (なんでも屋さん, "Mr. Anything-Shop") | **Encore:** a tenth round with two bosses at once | Synergy | Elemental, Swiftcast, Synergy |

Every reward is the materia at its maximum level. The round 9 pools include some of Chadley's regional legendary
fiends, which fight at your party's level.

Darkside gives every fighter the Darkside status at the start of every round, which makes abilities hit harder. The
game charged no HP for it here, so the mod charges the cost itself: each use of a weapon or folio ability, or of an
attacking command materia (Enemy Skill, Morph, Spare Change, Jump), takes 5% of the fighter's max HP, never below 1 HP.
Magic, items, limit breaks, synergy abilities and utility commands such as Steal, Assess, Chakra and Prayer cost
nothing. Every fighter also gets the game's Darkside materia, which brings its command, so a fighter can switch Darkside
and its cost off; the next round starts in Darkside again.

## Mako infusions

The infusion window uses the game's own message window and pauses the battle while it is open. Each offer draws
three infusions by tier: common (60%), rare (30%) and epic (10%). In the round after a boss round the odds become 20%,
40% and 40%. There are 77 in all: 43 common, 28 rare and 6 epic.

- **Party statuses:** Protect, Shell, Regen, Resist, Haste, Brave, Faith, Reflect, Critical hits up, Reraise.
- **Enemy debuffs:** Slow, weakened attacks or magic, broken armour or wards, Silence, Toxic, and enemies starting
  each round stopped or asleep.
- **Round effects:** full ATB at the start of each round, free spells for 40 seconds each round, Refocus, and
  Turbulent Spirit (ATB regeneration) for the first 60 seconds of each round.
- **Accessories:** the party gets the effect of a real accessory without equipping it, such as Genji Gloves, Ribbon,
  Götterdämmerung, Transference Module or Reclaimant Choker (26 in all).
- **Materia:** spells or abilities from a materia (Fire, Cure, Time, Revival, Chakra and more), and stat-up materia
  (HP Up, MP Up, Luck Up, Strength Up, Magic Up, Vitality Up, Spirit Up, Speed Up).

The epics are Reraise, Refocus, Turbulent Spirit, Götterdämmerung, Genji Gloves and Ribbon. Materia and accessory
infusions reach the fighters through the game's own equipment-skill rules, so most of them take effect from the next
round.

## Works with our other mods

Junon Colosseum works alongside our [Training Dummy](https://github.com/CaitGPT/FFVII-Rebirth-Training-Dummy),
[Battle Meters](https://github.com/CaitGPT/FFVII-Rebirth-Battle-Meters) and
[Biome Randomizer](https://github.com/CaitGPT/FFVII-Rebirth-Biome-Randomizer), in any install order.

- Training Dummy changes the same colosseum tables. Our archive loads after its archive and carries Training Dummy's
  three Combat Simulator courses too. They appear only while Training Dummy is installed and enabled, so one package
  works with or without it. Keep Training Dummy's own files as they are.
- Biome Randomizer and Battle Meters change no tables this mod uses.

Other mods that replace any of the tables listed in [How it works](docs/HOW-IT-WORKS.md#tables) will conflict.

## Known issues

<!-- Keep this list in step with the release notes; remove items as they are fixed. -->
- **Black "Get Ready" or loading screen.** Rarely, the game stops on a black "Get Ready" or loading screen and never
  continues. We have seen this in the game's own Combat Simulator fights too, without our courses. Restart the game;
  the course counts as not cleared.
- **Balance.** Every course has been cleared in our testing, but only with a development boost (fighters that couldn't
  fall, enemies that started at reduced HP). Unboosted difficulty beyond course 1 has had little testing. Tell us
  where it is unfair.
- **Darkside's command in round 1 (courses 13 and 14).** The command that switches Darkside off comes with the
  Darkside materia, which the game gives your fighters between rounds, so in round 1 a fighter may not have it yet.
  The mod charges the HP cost from round 1.
- **Opposite statuses cancel.** An enemy boon and one of your infusions can cancel each other out (Haste and Slow,
  or Regen and Toxic, for example). This is the game's own rule.
- **Game updates.** A game update can change the code the native helper relies on. The helper then switches itself
  off instead of guessing, and courses will not start until we update the mod.
- Don't use UE4SS hot reload (Ctrl+R): it crashes this game.

## Build from source

The release zip is built from your own copy of the game: this repository contains no game files. The build reads the
game tables and packages it changes from your exports, builds our archive with our data-table builder and retoc, and
lays out the zip. [Building from source](experiments/junon-foyer/README.md) lists the tools and steps. The tests run
offline: `python -m pip install pytest lupa`, then `python -m pytest -q tests` in `experiments/junon-foyer`.

## Documentation

- [How it works](docs/HOW-IT-WORKS.md): tables, scripts, the native helper, what was tested
- [How we built it](docs/HOW-WE-BUILT-IT.md): the whole story, dead ends included
- [Changelog](CHANGELOG.md)
- [Building from source](experiments/junon-foyer/README.md)

## Credits

- [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) and the FF7 Rebirth build of it on Nexus Mods
- [retoc](https://github.com/trumank/retoc) by Truman Kilen and Archengius, and its FF7R patches, which pack our
  archive
- FModel and CUE4Parse, for reading the game's files
- Microsoft's DirectXTex (`texconv`), for the menu backdrop's texture
- Ghidra, for reading the game's code
- CityHash (Google, MIT), in our data-table builder
- The Rebirth modding community

## Licence

The source code is MIT licensed ([LICENSE](LICENSE)). The repository contains no game files. The build reads the
game tables and level packages it changes from your own copy of the game.

FINAL FANTASY VII REBIRTH and its assets belong to Square Enix. This is an unofficial fan project, not affiliated with
or endorsed by Square Enix.
