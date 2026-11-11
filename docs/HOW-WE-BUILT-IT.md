# How we built Junon Colosseum

This is the story of the build, dead ends included. For the finished design in reference form, see
[HOW-IT-WORKS.md](HOW-IT-WORKS.md). To install and play, see the [README](../README.md).

## Why

Nobody is holding a controller here. This is Junon Colosseum, a mod for Final Fantasy VII Rebirth, and AI agents made
it. Codex, from OpenAI, started it. Claude Opus 5.5, from Anthropic, working in Claude Code, finished it: it researched
the game's code, built the mod, and played the game through our own test harness to try every build. A human gave the
brief, made the design calls and played it to judge how it felt.

The idea came from two places. Rebirth's combat is one of the best action combat systems around, and players who
finish the game want more of it. Roguelites, games like Slay the Spire and Monster Train, are built on runs that differ
every time, with choices along the way. The original Final Fantasy VII already had a hint of this: its Gold Saucer
battle arena applied a random buff or debuff after each round. So the brief was a post-game colosseum where every
attempt draws different fights, every course adds a rule, and between rounds you choose a buff that lasts until the
course ends.

It also had to belong in the world. Junon has an arena where Roche is fought, and a checkpoint with two Shinra guards
that the story leaves behind. So the Invitation comes from Roche, the guards let you in when you show it, and the
fights happen in that arena.

## Tools

| Tool | Used for |
| --- | --- |
| UE4SS 3.0.1 | Running our Lua scripts and our C++ helper inside the game |
| Our data-table builder | Reading and writing the game's data tables, row by row |
| retoc, with its patches for this game | Packing our archive |
| Ghidra and our own crash-dump reader | Reading the game's code and the state of a hung or crashed game |
| Our test harness | Letting the AI drive the game: travelling, talking, fighting with an autopilot, saving |
| Python and Lua | Generating the course data, and offline tests |

## Step 1: a door before a room

Codex began with the smallest thing that could fail: a new fast-travel destination. It added one map entry, cloned
from Bill's Ranch, at an existing anchor point in the Grasslands, and the game took it. The next step was the gate:
the destination appears only once a save is past a chapter milestone.

Then it moved to Junon. Travel straight into Roche's arena worked, but the arena is a place for a fight, not a lobby.
The design settled on a foyer beside it: the Junon Checkpoint guards get a new choice, *Show Colosseum Invitation*,
which takes you to the foyer, and the first entry earns the fast-travel point. A key item, the Invitation, was cloned
from an existing one. A full-size quest board replaced a redundant lever by the door, and checking it opened a course
menu with seven of our own courses.

Getting the guards right took several tries. The jump's destination sits in the sixth text slot of its action row,
not the first. A wrong slot crashed the game once, and twice dropped the player into an unloaded void.

## Step 2: the archive that wasn't

The courses needed a battle plan in the Junon arena, so Codex copied the prison colosseum's plan and moved it to
Junon. The new map never loaded. The packing tool said it had packed 29 files. Its output held 27, all of them tables
that already existed, and registered no new packages at all. The tables worked because the game already knew them; a
brand-new map was simply missing. An older compatibility step had also overwritten the first ten bytes of the
compressed archive, which corrupted every read-back we tried.

Codex rebuilt the packing. Every package now goes in raw, the new maps are registered in the game's own container
header, the archive is packed with retoc's build for this game, and the 16 bytes the game expects are added in front
rather than written over the data. Every build is unpacked again and compared chunk by chunk. With that, the map
loaded, and starting the first course moved Cloud into the Junon arena.

The screen then stayed black on "Get Ready", with no enemies, and that is where Codex handed over to Claude.

## Step 3: ruling things out

Claude's first days were spent ruling out causes, one game session at a time. Enemies from the prison colosseum, in
our copied arena: same black screen. The same without the intro camera: same. Soldier enemies that work in the Gold
Saucer: same. So the enemies weren't the problem; the copied arena was.

Reading the copied level more closely showed it was half of a pair. The prison arena is two levels, and the second
one holds every enemy spawn point. We copied that too, loaded it first as the game does, and saw its spawn actor alive
in battle with 413 spawn points per size. The screen still stayed black.

## Step 4: reading the game's code

The answer was in the game's code, not its data. Using Ghidra on the game's executable, Claude found that a colosseum
battle waits for its territory to be marked *Ready*. The game marks a territory ready only when its own level
registry lists the arena's spawn level, and levels streamed in by a mod are never added to that registry.

So our C++ helper does the game's two missing writes itself. Once per round, on the game thread, it links the
territory to its spawn actor with the game's own setter and marks it ready. It acts only on our own arena, and only
if the game's code at that spot is exactly what we read. Enemies spawned, and the first courses were won.

Then one enemy wouldn't appear: Mu. To find out why, Claude added a hardware watchpoint to the helper, a debug
register that reports which code writes to a chosen address. It found the function that builds each round's spawn
list. Three rounds in the game, the only three of 382, place their Mu at named points that exist only in the
simulator. The helper now switches that off for our courses and switches it back three seconds after a course ends.
Two Mu and a Toxirat spawned in Junon, and the course was won.

Enemies also spawned outside the walls, because the copied arena is the Gold Saucer's size, up to 26 metres across
from the centre, and Junon's floor is about 20. The mod now pulls every spawn list in to 12 metres, and a leash puts
an enemy that stays outside the ring back inside.

## Step 5: from seven battles to fourteen courses

With fights working, the owner set out the roguelite design. Fourteen courses, each a Shinra rank from newcomer to
SOLDIER First Class and beyond. Nine rounds, with bosses in rounds 3, 6 and 9. Every round slot drawing from its own
pool of about ten fights, harder slot by slot. A rule added by each course, kept for every course after it. Maxed
materia as rewards. And post-game content should use the whole party, so courses use the game's two-team mode: you
pick six, and two teams of three take turns.

All of it became data. One design file holds the courses, pools, rules and rewards, and a generator writes the table
rows and the script data from it. The pools came from scoring the game's own late-game rounds by total enemy health.
355 rounds of 94 species qualify; summons and Sephiroth were left out for the story's sake.

Drawing new fights for every attempt needed the helper again. The game's course table sits in memory as a frozen
image, so the helper finds each course's round list by its contents and overwrites it. That worked until two courses
shipped identical lists, and the helper shuffled the wrong one. Now every course ships a unique list.

The menus got their own look. The colosseum menu has four built-in themes; ours uses the Shinra Manor one, with our
own title, teal colours and a backdrop made from a photo the owner took of the arena floor.

## Step 6: Mako infusions

The first idea was a choice between rounds in the game's own dialogue. But between rounds there is only a black
loading screen, and every way of triggering the mod's dialogue from a script returned success and did nothing.

What did work was the game's own options window, opened from a script in the middle of a battle. Its pause setting
doesn't stop a fight, so the mod pauses the game itself while the window is open. Early in each round it offers three
infusions by tier: common, rare and epic, with epics far likelier after a boss round.

The owner wanted more than statuses. A Genji Gloves infusion should really give the Genji Gloves' effect. So the
helper adds a real accessory's skill rows to every fighter, under the mod's own key, using the game's own function,
and rebuilds their parameters between rounds. Materia earrings work the same way. A materia earring's spells showed
up in a fighter's spell list. For the stat-up materia the game has no earrings for, the mod adds its own copies of
the HP Up earrings, each naming a different materia.

## Step 7: rules that had to change

Several rules worked as code and failed as play.

Toad drill started every round with your fighters as toads for 15 seconds, and the owner found it no fun. It became Riot rush, hasted enemies.

Mirror match gave every infusion you took to the enemy too. Most infusions mean nothing on an enemy: spells, abilities
and accessories don't transfer. It became Arms race: every infusion you take gives the enemy a random boon.

Wounded started every round with your health capped at 75%. It became Short rest: between rounds you recover only 20% of your
health and 15% of your magic, instead of the colosseum's usual 50% and 30%. That needed the fighters'
live battle MP. The script that reads it looked frozen, so Claude checked the game's code and memory dumps, and found
it was the live value after all: the fighter being read simply hadn't cast anything.

Second wind first gave every enemy Reraise. The enemies died, never rose, and the battle never ended: the game waits
for an enemy with Reraise forever. Now the mod watches enemy health once a second and restores an enemy to half once,
the first time it drops below 20%.

Darkside gave the party the Darkside status. The status was applied, and it did nothing that cost health. The game's
Darkside materia describes the cost, so the rule gave the party the materia too, through a carrier accessory. That
brought the Darkside command, but still no cost: the owner checked by hand, and a test with frozen enemies left Yuffie's
health unchanged after her abilities, both in Darkside and after switching it with the command.

So the mod charges the cost itself. Five times a second during a Darkside round, it reads which action each fighter is
performing. Each use of a weapon ability, a folio ability or an attacking command materia, such as Jump or Enemy Skill,
takes 5% of the fighter's maximum health, never below 1. Magic, items, limit breaks, synergy abilities and utility
commands are free, and the Darkside command switches the cost off for that fighter until the next round. Claude built
the list of abilities that cost from the game's own ability table: 170 entries in 114 families. The owner then checked
the cost in play.

That last one taught the most useful lesson of the project: a status being applied is not the same as it working.
After that, every rule was checked against what it actually does in a fight, not against the call that set it up.

## Step 8: harder than the game's own end game

The owner's next brief was plain: the Junon Colosseum must be harder than every challenge in the game. The first pools
ranked rounds by their enemies' base health, which ignores the level they fight at. Claude rewrote the pool generator
to weigh each round by the health its enemies really have in our arena: the enemy's base health times the game's own
level factor. That formula was checked against health read from enemies in a live fight.

The new pools follow a few rules. Every slot is harder than the one before it, and every course harder than the last.
A boss round always beats the normal rounds before it, and no normal round is bigger than the next boss. Rounds with
two bosses appear only in the last course's encore, which became the hardest round of all. Two weak encore pairs and
a few rounds that fit nowhere, such as ten Tonberries at once, were dropped.

Pools alone couldn't get there. The game's end-game rounds cluster between about 30,000 and 110,000 health, so the
last course could only be a little harder than the first. So each course got a hidden health factor, from the game's
own values on the first course to two and a half times on the last two, carried by cloned enemy specs that courses
share. A typical run of the first course now faces about half a million enemy health in total, and the last course
about two million. The game's hardest Legendary challenge, Bonds of Friendship, totals about one and a quarter
million.

The swap to the cloned specs had one bug of its own. On the last course, ten Tonberries and a Cactuar kept their
normal health. The mod had looked for each enemy's spec in its name, but an enemy is named after its model, which is
not always its spec. It now reads the spec itself.

That made course 3's old rule, Tough hides, redundant: it gave enemies 25% more health, which the hidden factor
already did, and its text no longer told the whole story. It became Rally: whenever an enemy falls, every surviving
enemy gains a random infusion of its own.

## Step 9: two fights at once

The owner also wanted rounds that feel like new fights. The idea was to fight two of the game's rounds at once.

The game names a round's enemies in one table row, and one row can hold both groups' lists. An older verdict, from
our Training Dummy mod, said new rows in that table hang every simulator battle. Claude found that the table writer
used at the time shifted every row when it added one, which would explain it; our current builder keeps every
existing row byte for byte. The build doesn't depend on that, though: it can either rewrite spare simulator rounds
that no course uses, or add new rows. Four spare rounds that belong to the
Gilgamesh quest were left alone, because a story use outside the tables couldn't be ruled out.

Not every pair works. Reinforcement waves are tied to slots in the enemies' own AI, so only one half of a pair may
call waves. Enemies that fight at the party's level can't mix with fixed-level rounds. And the game loads every enemy
type's package for the round, so a pair doubles the loading. The generator therefore caps a combined round at six
enemies and five enemy types, one large enemy and two flyers, and pairs a boss with a few adds, never a second boss.

In the first test, the first three rounds of course 1 were forced to combined rounds in spare rows, and both groups
were in the arena at once in each of them. A second test used new rows. Every battle started, each combined round
ended only when both groups were down, and nothing hung, so the old verdict on new rows no longer holds with our
builder. Some rounds in every course are now combined rounds.

## Step 10: crashes and hangs

About one load in three into the foyer crashed the game. A bisect showed it happened only when the mod requested its
arena levels. Waiting for the world's streaming to settle first fixed it in eight loads out of eight. The real cause
turned out to be threads. This game runs script callbacks on worker threads, and UE4SS hands our work to whichever
thread calls next. A level load started from a worker writes into loader state that only the game thread has. The
helper now checks which thread it is on, and does engine work only at a safe point on the game thread, one piece of
work per frame, while the loader is idle.

The hitching we had blamed on the Biome Randomizer was ours too: its timer was measuring stalls that our level
requests caused.

Hangs on "Get Ready" between rounds had several causes. In a two-team course the waiting team's leader stands outside
the arena, so the mod once decided you had left and unloaded its own arena. Two courses shuffling the same list was
another. Both are fixed. Two more hangs had a different shape: in a full memory dump, the game's package loader
reported packages in flight while every loading thread sat idle. The engine had lost a load, once for an enemy and
once for a party member at a team swap. We haven't found what loses them, and no recovery is safe while loads are in
flight, so the helper now logs the loader's whole state when it happens. Later the same kind of stall, a black screen
that never ends, showed up in the game's own Combat Simulator fights, without our courses. Restarting the game
recovers.

One crash came from a single line: polling the mod's flow object with a half-second wait loop crashed the game right
after a load. Nothing ever reached that object, and the loop came out.

## Step 11: letting the agent play

The harness drove almost all of the testing. It loads saves, fast travels to the Junon Checkpoint, walks to the
guards, talks, picks the choice, checks the board and runs each course with a combat autopilot. Some harness fixes
came out of this work: the autopilot no longer tries items, which courses forbid, and save lists are read by slot
number.

To test fourteen courses in a day, a development switch made the fighters unable to fall and started enemies at a
fraction of their health, draining them. A script then ran courses back to back, picked infusions, relaunched the game
after a hang and wrote one line per course. On the last day it cleared all fourteen courses, and every first-clear
reward arrived.

While the main session played, other Claude sessions worked on their own branches in the background: reading crash
dumps, researching how the game stores battle MP, drafting the Darkside change, and building the combined rounds and
the balance pass.

## What we tested

- All fourteen courses cleared, with the development boost, on four playtest builds before the balance pass.
- Combined rounds, in spare rows and in new rows: both groups in the arena at once, each round ending only when both
  were down.
- Rally and the hidden health factor: course 3 cleared with the boost, with every survivor's boon logged at each fall.
- Darkside's health cost, charged by the mod, checked in play by the owner.
- Every first-clear reward arrived; repeat-clear draws were seen on three courses.
- Every enemy category in the game's simulator spawned in the Junon arena.
- Eight clean loads into the foyer in a row after the load-crash fix.
- The board, the guards, the fade and the fast-travel discovery, many times over.

## Known limits

- Rarely, the game stops on a black "Get Ready" or loading screen and never continues; restarting the game recovers.
  We have seen it in the game's own Combat Simulator fights too.
- Balance on later courses has been tested only with the development boost.
- Roche's Chapter 11 drop, the arrival grant and a Chapter 4 visit to the checkpoint have not been seen in play.
- Most accessory infusions haven't been checked one by one.
- The helper is tied to UE4SS 3.0.1 and this game build.

## Dead ends

| Tried | What happened |
| --- | --- |
| Packing new maps with UnrealReZen | Reported 29 files, held 27, registered none |
| Calling the level-load function from Lua | UE4SS 3.0.1 mishandles its true-or-false out-parameter; the call fails before it reaches the game |
| Dialogue choices between rounds | Between rounds there is only a loading screen, and script triggers never reached the mod's dialogue |
| Running the arena fix while levels load | Two loads in a row hung or crashed |
| Waiting a fixed eight seconds after a load | Still crashed one load in five; the cause was threads |
| Toad drill, Mirror match, Wounded | Not fun, or meaningless on enemies; replaced |
| Reraise on enemies | Battles never ended |
| Tough hides, 25% more enemy health | Redundant once every course had its own hidden health factor; replaced by Rally |
| Finding an enemy's spec from its name | Enemies are named after their model; ten Tonberries and a Cactuar kept their health |
| The Darkside status alone | No health cost |
| The Darkside materia through a carrier accessory | It brought the command, but still no health cost; the mod now charges it |
| Random three of six fighters per round | The game's party during a round holds only the current team; dropped by the owner |
| A wait loop on the mod's flow object | Crashed the game after a load |

## Credits

UE4SS and its authors; Truman Kilen and Archengius for retoc and its patches for this game; FModel and CUE4Parse;
Microsoft's DirectXTex; Ghidra; and the Rebirth modding community. Our own Training Dummy mod supplied the
data-table builder this mod grew from.
