Junon Colosseum {VERSION}
FINAL FANTASY VII REBIRTH (PC)

A post-game colosseum in the Junon arena: 14 courses of fights drawn from
the game's late-game and legendary encounters. AI coding agents built this
mod, with the owner directing and playtesting. It is open source.

WHAT IT ADDS
- 14 courses. Each has 9 rounds; rounds 3, 6 and 9 are boss fights. The last
  course adds a 10th round with two bosses.
- Every round draws its fight from a short list of about ten, so a course
  differs each time you play it. Later rounds and later courses draw harder
  fights. Some rounds combine two fights into one (at most six enemies).
- Enemy health rises course by course, from a gentle opener to final
  courses with more total enemy health than the game's hardest Legendary
  challenges.
- Each course is a Shinra rank, from Shin'iri (newcomer) to SOLDIER First Class and
  beyond, and adds a rule to the ones before it: enemies with their own
  infusions, enemies that rally when one of them falls, hasted enemies,
  Berserk fighters, enemies that reflect spells, an arms race, Stop every
  30 seconds, Darkside fighters, and more.
- Mako infusions: about a second into each round, a window opens and the
  game pauses. Take one of three infusions (two from course 11), or refuse
  them all. Infusions last until the course ends.
- Teams: choose six party members. Two teams of three take turns, round by
  round.
- Rewards: maxed materia. The first clear of a course gives its listed
  materia; repeat clears give one of up to four, at random. Each course's
  description lists the materia it can give.
- A Junon-branded course menu and result screen.

REQUIREMENTS
- FINAL FANTASY VII REBIRTH for PC, Steam version, current patch.
- RE-UE4SS for FF7 Rebirth 1.0.2 (UE4SS 3.0.1) from Nexus Mods (mod 267),
  installed so that End\Binaries\Win64\ue4ss\UE4SS.dll exists.
- A save in Chapter 12 or later. The colosseum stays closed in earlier
  chapters, including chapter replays.

INSTALL
1. Close the game.
2. Copy the End folder from this zip into the game folder (the one that
   holds End). It adds:
     End\Content\Paks\~mods\JunonColosseum_999_P.pak/.ucas/.utoc
     End\Binaries\Win64\ue4ss\Mods\JunonColosseum\
3. If your Mods\mods.txt lists JunonColosseum with 0, change
   it to 1. The included enabled.txt turns the mod on otherwise.

GETTING IN
- Defeat Roche in Chapter 11 to receive the Junon Colosseum Invitation (Key
  Items). On a save already past that fight, walk up to the two Shinra guards
  at the Junon Checkpoint and one of them hands it over.
- In Chapter 12 or later, speak to either guard at the Junon Checkpoint and
  choose "Show Colosseum Invitation". The first entry also adds the colosseum to fast travel.
- The course board stands to the right of the foyer door. Course 1 is open;
  clearing a course opens the next. Courses can be replayed.

OUR OTHER MODS
Works alongside our Training Dummy, Battle Meters and Biome Randomizer
mods, in any install order.
- Training Dummy and this mod change the same colosseum tables. This mod's
  archive loads last and carries Training Dummy's three Combat Simulator
  courses too; they appear only while Training Dummy is installed and
  enabled. Keep Training Dummy's own files as they are.
- Biome Randomizer and Battle Meters change no tables this mod uses.

UNINSTALL
Close the game and delete the three JunonColosseum_999_P files
and the Mods\JunonColosseum folder. Back up your saves before
installing: a save keeps the Invitation and the mod's progress flags, and we
have not tested loading such a save without the mod.

KNOWN ISSUES
- Rarely, the game stops on a black "Get Ready" or loading screen and never
  continues. We have seen this in the game's own Combat Simulator fights
  too, without our courses. Restart the game; the course counts as not
  cleared.
- Every course has been cleared in our testing, but only with a development
  boost. Balance in later courses has had little unboosted testing; tell us
  where it is unfair.
- Darkside (courses 13 and 14): each use of a weapon, folio or attacking
  command-materia ability costs 5% of max HP, never below 1 HP; magic,
  items, limits, synergy and utility commands are free. The Darkside
  command switches it off until the next round. The command comes with the
  Darkside materia, which the game gives your fighters between rounds, so
  in round 1 a fighter may not have it yet.
- Opposite statuses cancel, as in the game: an enemy boon and one of your
  infusions can undo each other (Haste and Slow, for example).
- A game update can change the code the mod's helper relies on. The helper
  then turns itself off instead of guessing, and courses will not start
  until we update the mod.
- Don't use UE4SS hot reload (Ctrl+R): it crashes this game.

SOURCE AND LICENCE
Source, documentation and how we built it:
https://github.com/CaitGPT/FFVII-Rebirth-Junon-Colosseum
The code is MIT licensed (LICENSE.txt). CHANGELOG.md lists what changed.
FINAL FANTASY VII REBIRTH belongs to Square Enix. This is an unofficial fan
project, not affiliated with or endorsed by Square Enix.
