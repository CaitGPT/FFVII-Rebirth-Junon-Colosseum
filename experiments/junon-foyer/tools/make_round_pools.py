"""Curated random rounds (owner design 2026-11-09): every round slot of every
course has its own pool of about ten candidate rounds, and each run draws one
from each pool. "Not utter chaos, curated randomisation": each slot's pool is
harder than the one before it, and each course's pools harder than the last
course's.

Owner 2026-11-09: this is post-game content for the strongest players, so it
must never be easier than vanilla's own end game (the Gold Saucer's Musclehead
courses and Chadley's Brutal and Legendary challenges). Only those rounds
(GOLDA_*, EXTRA_*) and the regional legendary fiends (*_07_050) are used.

Owner 2026-11-11 (balance): the Junon Colosseum must be harder than every
vanilla challenge. A round's difficulty is its enemies' HP in our arena
(hp(): spec HP x EnemyParameter Enemy_<level>.HPMax / 100 at level
max(listed, 67), verified live 2026-11-11; wave enemies are left out). Rules:
- slots: normal rounds in 1, 2, 4, 5, 7, 8; boss rounds in 3, 6, 9; course
  14's encore (10) fights two bosses at once. Two-boss rounds (two enemies of
  1500+ base HP each, and vanilla's own two-boss rounds, ENCORE) are drawn only
  by the encore ("never two bosses outside the encore"); a pair of enemies
  of 1200+ base HP each is a boss round; a pair below that is not (GOLDA_11_010,
  two Elfadunk subspecies). Normal rounds too big for every normal slot
  (HEAVY) may be drawn by slot 9.
- each slot aims at SHAPE[slot] x the course's step (STEP_FIRST on course 1
  to 1 on course 14) and takes the POOL (boss) or NORMAL_POOL rounds of its
  kind closest to that;
- no outliers: a normal slot never holds a round above the next boss slot's
  median; a boss slot's weakest round beats every earlier normal slot's
  median; the encore's weakest beats slot 9's median and slot 9 holds nothing
  above the encore's median;
- the medians rise: normal slots in order, boss slots in order, each boss
  slot above its neighbours, the encore above everything;
- the course's median total HP (with its HP factor) follows a smooth ramp
  from course 1's own total to TARGET_LAST on course 14 (about 1.3x vanilla's
  hardest course, Legendary "Bonds of Friendship", 1.25M at Lv70). Pools alone
  cannot reach it, so each course gets a hidden HP factor (course-design
  'hp_factor', never below 1 and never below the course before's, in steps of
  FACTOR_STEP, so courses share clone sets). It is the course's whole HP
  change (apply_difficulty course_rules; the _JCnn spec clones carry it):
  owner 2026-11-11, no rank rule names it (Rally replaced Tough hides' 25%,
  which the ladder keeps).
Rewrites courses[*].slots, bosses and hp_factor in data/course-design.json.
Run tools/apply_course_design.py after (and tools/make_combined_rounds.py).
"""
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'data/course-design.json'
ROUNDS = ROOT / 'data/round-data.json'
ROWS = ROOT / 'data/territory-rows.json'
PARTY_LEVEL = 60          # (old score) level-0 rounds fight at the party's level
ARENA_LEVEL = 67          # live 2026-11-11: enemies fight at max(listed level, this)
POOL = 10                 # candidates per boss slot
NORMAL_POOL = 8           # per normal slot: 68 normal rounds share six slots per course
MIN_POOL = 5              # a slot keeps at least this many after the outlier rules
ENCORE = ['EXTRA_05_030', 'EXTRA_04_010', 'EXTRA_05_040', 'EXTRA_05_100', 'EXTRA_05_060',
          'EXTRA_05_070', 'EXTRA_05_080', 'EXTRA_05_050', 'EXTRA_04_060', 'EXTRA_05_010']  # vanilla two-boss rounds
TWO_BOSS_HP = 1500        # two enemies of at least this base HP each: two bosses (encore only)
BOSS_PAIR_HP = 1200       # two enemies of at least this base HP each: a boss round
HEAVY = 150_000           # normal rounds above this arena HP fit no normal slot; slot 9 may draw them
# Slot aims for course 14 (arena HP, thousands); course c aims at step(c) x these.
SHAPE = {1: 38, 2: 44, 3: 80, 4: 50, 5: 56, 6: 105, 7: 63, 8: 72, 9: 145, 10: 190}
STEP_FIRST = 0.75
TARGET_LAST = 1_650_000   # course 14's median total HP with its modifiers (Bonds of Friendship 1.25M x 1.3)
TARGET_FIRST = 0          # course 1's total at least this (0: its own pools' total; raise to make course 1 harder)
FACTOR_STEP = 0.25        # course HP factors are multiples of this (fewer clone sets)
VANILLA_HARDEST = {'COL30_EXTRA_15_Free_Col (Legendary, Bonds of Friendship)': 1_253_000,
                   'COL30_EXTRA_14_Free_Col (Legendary, To Be a Hero)': 1_205_000}


SPECS = {}
_ROWS = {}


def endgame(k):
    return k.startswith(('GOLDA_', 'EXTRA_')) or k.endswith('_07_050')


def base_hp(r):
    return sum(int(SPECS[s]['HP']) for s in r['specs']) / len(r['specs'])


def score(r):
    """The old score (round-data entry): base HP x count, weighted by listed level."""
    level = r['level'] or PARTY_LEVEL
    return round(base_hp(r) * r['enemies'] * (0.6 + 0.4 * level / 70))


def rows():
    if not _ROWS:
        _ROWS.update(json.loads(ROWS.read_text(encoding='utf-8')))
    return _ROWS


_HP = {}


def hp(rid, floor=ARENA_LEVEL):
    """A round's total enemy HP in our arena (main enemies; wave enemies left out)."""
    if (rid, floor) not in _HP:
        _HP[(rid, floor)] = _hp(rid, floor)
    return _HP[(rid, floor)]


def _hp(rid, floor):
    data = rows()
    factor = {int(k): v for k, v in data['level_hp'].items()}
    t = data['rows']['terVR_COL30_' + rid]['territory']
    pops, levels = t.get('MinPopList_Array', []), t.get('MobLevelList_Array', [])
    total = 0.0
    for i, template in enumerate(t.get('MobTemplateList_Array', [])):
        spec = data['templates'][template]
        n = int(pops[i]) if i < len(pops) and pops[i] else 1
        level = int(levels[i]) if i < len(levels) and levels[i] else 0
        total += data['specs'][spec]['hp'] * n * factor[min(99, max(level or floor, floor))]
    return round(total)


def kind(k, r):
    """'encore' (two bosses), 'boss' or 'normal' (HEAVY normals: 'heavy')."""
    if k in ENCORE or (r['enemies'] == 2 and len(r['specs']) <= 2 and base_hp(r) >= TWO_BOSS_HP):
        return 'encore'
    if r['enemies'] == 1 or r['level'] == 0 or (r['enemies'] == 2 and base_hp(r) >= BOSS_PAIR_HP):
        return 'boss'
    return 'heavy' if hp(k) > HEAVY else 'normal'


def step(c, courses):
    return STEP_FIRST + (1 - STEP_FIRST) * (c - 1) / max(1, courses - 1)


def median(xs):
    return statistics.median(xs) if xs else 0


def closest(cands, aim, n, used, lo=None, hi=None):
    """The n rounds closest to aim (by ratio) within (lo, hi], not yet used."""
    ok = [k for k in cands if k not in used and (lo is None or HPS[k] > lo) and (hi is None or HPS[k] <= hi)]
    ok.sort(key=lambda k: (abs(math.log(HPS[k] / aim)), k))
    return sorted(ok[:n], key=lambda k: (HPS[k], k))


HPS = {}


NORMAL_SLOTS = (1, 2, 4, 5, 7, 8)
BOSS_GAP = 1.1            # a boss slot aims at least this much above the slots it must beat


def course_slots(c, courses, kinds, encore):
    """One course's slot pools (lists sorted by HP).

    Normal slots: the 6 x NORMAL_POOL normal rounds nearest the course's normal
    aims (SHAPE x step), sorted by HP and cut into six consecutive bands, so the
    normal medians rise and no two slots share a round. Boss slots: the POOL
    boss rounds nearest their aim, raised where needed to stay BOSS_GAP above
    the slots they must beat, and only rounds above every earlier normal
    slot's median. The encore: the two-boss rounds nearest its aim; slot 9
    holds nothing above the encore's median."""
    g = step(c, courses)
    aim = {s: SHAPE[s] * 1000 * g for s in SHAPE}
    by = {x: [k for k, v in kinds.items() if v == x] for x in ('normal', 'heavy', 'boss', 'encore')}
    lo_aim, hi_aim = aim[NORMAL_SLOTS[0]], aim[NORMAL_SLOTS[-1]]

    def away(k):  # distance (by ratio) from the course's normal range
        h = HPS[k]
        return 0 if lo_aim <= h <= hi_aim else abs(math.log(h / (lo_aim if h < lo_aim else hi_aim)))
    window = sorted(sorted(by['normal'], key=lambda k: (away(k), abs(math.log(HPS[k] / math.sqrt(lo_aim * hi_aim))), k))
                    [:len(NORMAL_SLOTS) * NORMAL_POOL], key=lambda k: (HPS[k], k))
    size = len(window) // len(NORMAL_SLOTS)
    slots = {s: window[i * size:(i + 1) * size] for i, s in enumerate(NORMAL_SLOTS)}
    med = {s: median([HPS[k] for k in pool]) for s, pool in slots.items()}
    top = {s: max(HPS[k] for k in pool) for s, pool in slots.items()}
    used = set()
    if encore:
        slots[10] = closest(by['encore'], aim[10], POOL, used)
        used |= set(slots[10])
    before = {3: (1, 2), 6: (1, 2, 4, 5), 9: NORMAL_SLOTS}
    after = {3: 4, 6: 7, 9: None}
    # Hardest first: the few big single bosses go to slot 9, and each earlier boss
    # slot stays below the next one's median.
    ceiling = median([HPS[k] for k in slots[10]]) if encore else None
    for s in (9, 6, 3):
        lo = max(med[n] for n in before[s])
        want = max(aim[s], top[before[s][-1]] * BOSS_GAP, med[after[s]] * BOSS_GAP if after[s] else 0)
        if ceiling is not None:
            want = min(want, ceiling / BOSS_GAP)
        cands = by['boss'] + (by['heavy'] if s == 9 else [])
        slots[s] = closest(cands, want, POOL, used, lo=lo, hi=ceiling)
        used |= set(slots[s])
        ceiling = median([HPS[k] for k in slots[s]]) - 1
    return [slots[s] for s in sorted(slots)]


def check(course_slots_list, encore):
    """Why a course's pools break the balance rules, or None."""
    med = [median([HPS[k] for k in pool]) for pool in course_slots_list]
    hi = [max(HPS[k] for k in pool) for pool in course_slots_list]
    lo = [min(HPS[k] for k in pool) for pool in course_slots_list]
    m = dict(zip(range(1, len(med) + 1), med))
    if any(len(p) < MIN_POOL for p in course_slots_list):
        return 'a slot has fewer than %d rounds' % MIN_POOL
    for s, b in ((1, 3), (2, 3), (4, 6), (5, 6), (7, 9), (8, 9)):
        if hi[s - 1] > m[b]:
            return f'slot {s} holds a round above slot {b} median'
    for b, normals in ((3, (1, 2)), (6, (1, 2, 4, 5)), (9, (1, 2, 4, 5, 7, 8))):
        if lo[b - 1] <= max(m[n] for n in normals):
            return f'slot {b} weakest does not beat the earlier normal medians'
    normals = [m[s] for s in (1, 2, 4, 5, 7, 8)]
    bosses = [m[s] for s in (3, 6, 9)]
    if normals != sorted(normals) or len(set(normals)) != len(normals):
        return 'normal medians do not rise'
    if bosses != sorted(bosses) or len(set(bosses)) != len(bosses):
        return 'boss medians do not rise'
    for b, (left, right) in ((3, (2, 4)), (6, (5, 7)), (9, (8, 8))):
        if m[b] <= max(m[left], m[right]):
            return f'boss slot {b} is not above its neighbours'
    if encore:
        if lo[9] <= m[9] or hi[8] > m[10] or m[10] <= max(med[:9]):
            return 'the encore is not the hardest round'
    return None


def course_total(pools):
    return sum(median([HPS[k] for k in pool]) for pool in pools)


def ramp(first, last, c, courses):
    return first * (last / first) ** ((c - 1) / max(1, courses - 1))


def factors(totals, rounds):
    """Per course: the hidden HP factor that brings its total to the ramp, a
    multiple of FACTOR_STEP, at least 1 and never below the course before's, so
    courses share spec clone sets (each distinct factor is one set of _JCnn
    rows). The ramp is per round (the encore's tenth round would otherwise make
    course 14 need less than course 13)."""
    n = len(totals)
    first = max(totals[0], TARGET_FIRST) / rounds[0]
    out, last = [], 1.0
    for c in range(1, n + 1):
        want = ramp(first, TARGET_LAST / rounds[-1], c, n) * rounds[c - 1]
        whole = math.ceil(round(want / totals[c - 1] / FACTOR_STEP, 6)) * FACTOR_STEP
        last = max(whole, last)
        out.append(round(last, 4))
    return out


def load():
    design = json.loads(DESIGN.read_text(encoding='utf-8'))
    data = json.loads(ROUNDS.read_text(encoding='utf-8'))
    SPECS.update(data['specs'])
    rounds = {k: v for k, v in data['rounds'].items() if endgame(k) and 'terVR_COL30_' + k in rows()['rows']}
    HPS.update({k: hp(k) for k in rounds})
    return design, rounds


def build(design, rounds):
    """The pools and HP factors for every course (design not changed)."""
    kinds = {k: kind(k, r) for k, r in rounds.items()}
    courses = design['courses']
    out = []
    for c, course in enumerate(courses, 1):
        encore = c == len(courses)
        pools = course_slots(c, len(courses), kinds, encore)
        why = check(pools, encore)
        if why:
            raise ValueError(f"course {c} {course['title']}: {why}")
        out.append(pools)
    return out, factors([course_total(p) for p in out], [len(p) for p in out])


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    design, rounds = load()
    pools, hp_factors = build(design, rounds)
    for c, (course, slots, factor) in enumerate(zip(design['courses'], pools, hp_factors), 1):
        course['slots'] = slots
        course.pop('rounds', None)
        course['bosses'] = [3, 6, 9] + ([10] if len(slots) == 10 else [])
        course.pop('hp_scale', None)
        course['hp_factor'] = factor
        total = course_total(slots)
        meds = ' '.join(f'{median([HPS[k] for k in p]) / 1000:.0f}' for p in slots)
        print(f"{c:2} {course['title']:24} raw {total / 1000:5.0f}k  x{factor:.2f} -> "
              f"{total * factor / 1000:5.0f}k  slots {meds}  sizes {[len(p) for p in slots]}")
    design['_slots'] = __doc__.strip().split('\n\n')[0]
    design['_balance'] = ' '.join(__doc__.strip().split('\n\n')[2].split())
    DESIGN.write_text(json.dumps(design, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
