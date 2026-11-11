"""Combined rounds (owner idea 2026-11-11): a round that fights two existing
simulator rounds' enemies at once, so courses meet new fights without
hand-authored groups.

A combined round is one EnemyTerritory row whose enemy lists are the two rounds'
lists end to end (templates, counts, levels, field AI, flyer flags) plus one
EnemyTerritoryLevel row (the first round's: triggers, escape rules). The game
then builds one spawn entry per enemy and requests each enemy's CharaSpec pack
itself, exactly as for a vanilla five-enemy round. In the Junon arena every
round uses POS_Mod_JunonColosseum and the ServerBuild's spawn lists by size
class, so no position row is needed.

Pairing rules (each with its reason) are in `refusal()`. Difficulty: a pair's
score is the sum of its rounds' arena HP (make_round_pools.hp), and each
slot's pairs are drawn from that slot's own pool (pools are disjoint within a
course, so no round can appear in two slots of a run) and ranked by closeness
to PAIR_TARGET x the pool's median. Boss slots pair the boss with a small
group of adds. The balance rules cap them (slot_cap): a normal slot's pairs never
exceed the next boss slot's median, slot 9's never the encore's. The course's HP factor and its stat rank rules apply per
enemy, so they scale combined rounds exactly as single ones; the _JCnn clones
of the adds come from the combined round's specs (apply_difficulty.apply).

Integration (owner 2026-11-11, "Route A"): course-design.json's "combined"
setting gives the share of each slot's pool that is combined rounds (a course
may override it with "combined_share") and the mode:
- "repurpose" (T1): each combined round rewrites one of the spare simulator
  territories no vanilla course uses (SPARES), so no EnemyTerritory row is
  added; the share is limited by the 17 spares (a spare serves every course
  whose slot can draw the same pair);
- "new" (T2): each combined round is a new row terVR_COL30_MIX_<a>_<b>; the
  share is limited only by the candidates. A build option
  (apply_course_design.py --combined-mode new) until new rows are proven live.
Either way the round names start with terVR_COL30_, which is what the native
helper's RoundShuffle and buffwheel.lua expect. The pools mix single and
combined rounds, singles first, so every course ships its single rounds.

    python tools/make_combined_rounds.py     # candidates and both allocations -> data/combined-rounds.json
"""
import copy
import json
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_round_pools  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ROWS = ROOT / 'data/territory-rows.json'
OUT = ROOT / 'data/combined-rounds.json'
PREFIX = 'terVR_COL30_'
TERRITORY = 'DataObject/Resident/EnemyTerritory.uasset'
LEVEL = 'DataObject/Resident/EnemyTerritoryLevel.uasset'
MODES = ('repurpose', 'new')

MAX_ENEMIES = 6     # owner 2026-11-11: the cap (our arena has fought 5 at once; vanilla's most is 8)
MAX_TEMPLATES = 8   # vanilla's most in one simulator row
MAX_SPECS = 5       # distinct enemy specs: each is one CharaSpec pack request (lost loads are hangs 3 and 4)
LARGE = 3           # PhysiqueSize 3+ (Elphadunk, Dragon, Zuu, bosses): the arena floor is a 20 m circle
MAX_LARGE = 1       # at most one large enemy in a combined round
MAX_FLYERS = 2      # AerialEnemyFlag enemies: the fly lists share the same small sky
PAIR_TARGET = 1.5   # a pair aims at 1.5x the slot pool's median single-round score (owner: 1.5-2x a round)
BOSS_TARGET = 1.25  # a boss with adds: 1.25x the boss pool's median
PAIRS_PER_SLOT = 20  # candidates per slot (the allocation picks among them)
MAX_REUSE = 3       # a round appears in at most this many of a slot's pairs
TEST_SLOTS = 3      # the test switch forces course 1's first three rounds (two pairs, a boss with adds)
SCENES = ('', 'btsc_COMMON_ColosseumExcitement')  # the crowd scene only; others script the fight
# Spare simulator territories: in EnemyTerritory and EnemyTerritoryLevel, named by
# no vanilla course and by no other table (DataTableIndex Resident and Field CSVs).
# Training Dummy repurposes terVR_COL30_SUMMON_Gilgamesh_010_BtlTest_Hard (no
# level row), so it is never ours. Order is preference: the generic simulator
# test rows first, then our own earlier test rows (BatteTest, SummonsTest), and
# The Gilgamesh quest rows (SUMMON_GilQuest01-03_010, SUMMON_Gilgamesh_010) are
# left out (owner 2026-11-11): their story use outside the tables is not known.
SPARES = [PREFIX + r for r in (
    'Gen_00_010', 'Gen_00_020', 'Gen_00_030', 'Adv_00_010', 'Adv_00_020', 'Adv_00_030',
    'Beg_00_010', 'Beg_00_020', 'Beg_00_030', 'Int_00_010', 'Int_00_020', 'Int_00_030',
    'Cha_00_010', 'Cha_00_020', 'Cha_00_030', 'BatteTest_01_010', 'SUMMON_SummonsTest')]
NEVER = PREFIX + 'SUMMON_Gilgamesh_010_BtlTest_Hard'
LISTS = ('MobTemplateList_Array', 'MobLevelList_Array', 'FieldAINameList_Array', 'MinPopList_Array', 'MaxPopList_Array')
WAVES = ('WaveMobTemplateList_Array', 'WaveMobLevelList_Array', 'WavePopSettingList_Array',
         'WaveBattleSceneAerialEnemyFlag_Array', 'WaveMobSpecialStatusChangeID_Array')
MUST_BE_EMPTY = ('SummonConditionID', 'BattleConditionTriggerGroupId_Array', 'ExternalEnemiesList_Array',
                 'DisableKillOnTerritoryFinishList_Array', 'DisableDeadDestroyList_Array',
                 'DisableSystemLogOnKillList_Array', 'ForceFinishBattleOnKill_Array')


def load():
    data = json.loads(ROWS.read_text(encoding='utf-8'))
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    rounds = json.loads((ROOT / 'data/round-data.json').read_text(encoding='utf-8'))
    make_round_pools.SPECS.update(rounds['specs'])
    ROUND_DATA.update(rounds['rounds'])
    return data, design, rounds


_INFO = {}


def info(data, r):
    """What the pairing rules need to know about round r (its id, without the prefix)."""
    key = (id(data), r)
    if key not in _INFO:
        _INFO[key] = _info(data, r)
    return _INFO[key]


def _info(data, r):
    row = data['rows'][PREFIX + r]
    t, lv = row['territory'], row['level'] or {}
    templates = t.get('MobTemplateList_Array', [])
    counts = [int(x) for x in t.get('MaxPopList_Array', [])][:len(templates)]
    aerial = [int(x) for x in t.get('AerialEnemyFlag_Array', [])]
    specs = [data['templates'][x] for x in templates]
    sizes = [data['specs'][s]['size'] for s in specs]
    return {
        'templates': templates, 'counts': counts, 'specs': specs,
        'enemies': sum(counts),
        'large': sum(c for c, z in zip(counts, sizes) if z >= LARGE),
        'flyers': sum(c for i, c in enumerate(counts) if i < len(aerial) and aerial[i]),
        'waves': any(t.get('WaveMobTemplateList_Array', [])),
        'lv_sync': not t.get('MobLevelList_Array'),   # no levels: the party's level ("Lv Sync")
        'row': t, 'level': lv,
    }


def unfit(i):
    """Why a round cannot be half of any combined round, or None."""
    t, lv = i['row'], i['level']
    n = len(i['templates'])
    if not n:
        return 'no enemies'
    if t.get('BattleSceneBluePrint', '') not in SCENES:
        return 'battle scene ' + t['BattleSceneBluePrint']
    for f in MUST_BE_EMPTY:
        if t.get(f):
            return f + ' set'
    if lv.get('UsePopTargetPoint', '0') != '0':
        return 'named pop points (simulator only)'
    if lv.get('KillStateTrigger_Array', []) != ['trgCmn_colosseum_win'] or lv.get('BattleWinStateTrigger_Array'):
        return 'own win triggers'
    ragged = [f for f in LISTS if f in t and len(t[f]) != n and not (f == 'MobLevelList_Array' and not t[f])]
    if ragged or len(t.get('AerialEnemyFlag_Array', [])) > n:
        return 'ragged lists ' + ','.join(ragged)
    if any(x != 'Stay' for x in t.get('FieldAINameList_Array', [])):
        return 'field AI other than Stay'
    return None


def refusal(a, b, boss_slot=False, encore=False):
    """Why rounds a and b (info()) cannot fight together, or None."""
    for i in (a, b):
        why = unfit(i)
        if why:
            return why
    if len(a['templates']) + len(b['templates']) > MAX_TEMPLATES:
        return 'too many enemy kinds'
    if a['enemies'] + b['enemies'] > MAX_ENEMIES:
        return 'too many enemies'
    if len(set(a['specs']) | set(b['specs'])) > MAX_SPECS:
        return 'too many specs (pack loads)'
    if set(a['specs']) & set(b['specs']):
        return 'shared enemies (not a new fight)'
    if a['large'] + b['large'] > (MAX_LARGE if not encore else 2):
        return 'too many large enemies'
    if boss_slot and b['large']:
        return 'large adds'
    if a['flyers'] + b['flyers'] > MAX_FLYERS:
        return 'too many flyers'
    if a['waves'] and b['waves']:
        return 'both call waves (their AI owns the wave slot indices)'
    if a['lv_sync'] != b['lv_sync']:
        return 'Lv Sync with fixed levels'
    return None


def combine(a, b):
    """The combined EnemyTerritory fields: a's enemies, then b's."""
    ta, tb = a['row'], b['row']
    out = {}
    for f in LISTS:
        out[f] = ta.get(f, []) + tb.get(f, [])
    if not ta.get('MobLevelList_Array') and not tb.get('MobLevelList_Array'):
        out['MobLevelList_Array'] = []
    na, nb = len(a['templates']), len(b['templates'])
    fa, fb = ta.get('AerialEnemyFlag_Array', []), tb.get('AerialEnemyFlag_Array', [])
    out['AerialEnemyFlag_Array'] = (fa + ['0'] * (na - len(fa)) + fb + ['0'] * (nb - len(fb))) if fa or fb else []
    owner = ta if a['waves'] else tb  # at most one calls waves (refusal)
    for f in WAVES:
        out[f] = owner.get(f, []) if (a['waves'] or b['waves']) else []
    scene = ta.get('BattleSceneBluePrint', '') or tb.get('BattleSceneBluePrint', '')
    out['BattleSceneBluePrint'] = scene
    return out


def pair_id(a, b):
    return f'MIX_{a}_{b}'


def unique_index(name, used):
    value = zlib.crc32(name.encode()) & 0x7fffffff
    while value in used:
        value += 1
    used.add(value)
    return value


def territory_rows(data, combos, mode):
    """Spec rows for combos [(row name, a id, b id)]: new rows (mode new) or
    spare rows rewritten (mode repurpose)."""
    used = set(data['unique_indices'])
    terr, levels = [], []
    for name, a_id, b_id in combos:
        a, b = info(data, a_id), info(data, b_id)
        why = refusal(a, b, boss_slot=True) and refusal(a, b)
        if why:
            raise ValueError(f'{a_id} + {b_id}: {why}')
        fields = combine(a, b)
        source = PREFIX + a_id
        if mode == 'new':
            fields['UniqueIndex'] = str(unique_index(name, used))
            terr.append({'name': name, 'cloneFrom': source, 'set': fields})
            levels.append({'name': name, 'cloneFrom': source, 'set': {'UsePopTargetPoint': '0'}})
        elif mode == 'repurpose':
            if name not in SPARES or name == NEVER:
                raise ValueError(f'{name} is not a spare territory')
            spare = data['rows'][name]
            # Every field the spare or a has: a's value (empty by default), the spare's UniqueIndex kept.
            keys = (set(spare['territory']) | set(a['row']) | set(fields)) - {'UniqueIndex'}
            full = {k: fields.get(k, a['row'].get(k, [] if k.endswith('_Array') else '')) for k in sorted(keys)}
            terr.append({'name': name, 'set': full})
            lkeys = set(spare['level'] or {}) | set(a['level'])
            level = {k: a['level'].get(k, [] if k.endswith('_Array') else '') for k in sorted(lkeys)}
            level['UsePopTargetPoint'] = '0'
            levels.append({'name': name, 'set': level})
        else:
            raise ValueError(f'mode {mode!r}')
    return terr, levels


def ranked_pairs(data, pool, target, boss_slot=False, adds=None, cap=None, partners=()):
    """Up to PAIRS_PER_SLOT pairs for one slot, closest to target first, each round
    in at most MAX_REUSE pairs. Boss slots pair each boss with adds; normal slots
    pair two of the slot's rounds, or one with a partner (a round the course
    never draws). cap: the most HP a pair may have (balance: never above the
    next boss slot's median)."""
    cand = []
    firsts = pool
    seconds = adds if boss_slot else list(pool) + [r for r in partners if r not in pool]
    for i, a in enumerate(firsts):
        for b in seconds:
            if a == b or (not boss_slot and b in pool and b <= a):
                continue
            ia, ib = info(data, a), info(data, b)
            if refusal(ia, ib, boss_slot=boss_slot):
                continue
            s = make_round_pools.hp(a) + make_round_pools.hp(b)
            if cap is not None and s > cap:
                continue
            cand.append((abs(s - target), s, a, b))
    cand.sort()
    out, uses = [], {}
    for _, s, a, b in cand:
        if uses.get(a, 0) >= MAX_REUSE or uses.get(b, 0) >= MAX_REUSE:
            continue
        uses[a] = uses.get(a, 0) + 1
        uses[b] = uses.get(b, 0) + 1
        out.append([a, b, s])
        if len(out) == PAIRS_PER_SLOT:
            break
    return sorted(out, key=lambda p: (p[2], p[0], p[1]))


ROUND_DATA = {}


def adds_for(course, design, data):
    """Boss adds: small groups (3 or fewer, no large enemy) from endgame rounds
    this course never draws, no harder than its first slot's hardest round."""
    taken = {r for slot in course['slots'] for r in slot}
    cap = max(make_round_pools.hp(r) for r in course['slots'][0])
    out = []
    for r in sorted(ROUND_DATA):
        if r in taken or not make_round_pools.endgame(r) or PREFIX + r not in data['rows']:
            continue
        i = info(data, r)
        if i['enemies'] <= 3 and not i['large'] and not unfit(i) and make_round_pools.hp(r) <= cap:
            out.append(r)
    return out


def partners_for(course, data):
    """Second halves for a normal slot's combined rounds besides the slot's own
    rounds: endgame rounds the course never draws (so a run never meets one
    twice), not two-boss rounds and not the oversized normal ones. Owner
    2026-11-11 (balance): a normal slot never holds a round above the next boss
    slot's median, and two of a slot's own rounds are about twice its median,
    so most normal pairs take a smaller round from outside the course."""
    taken = {r for slot in course['slots'] for r in slot}
    out = []
    for r in sorted(ROUND_DATA):
        if r in taken or not make_round_pools.endgame(r) or PREFIX + r not in data['rows']:
            continue
        if make_round_pools.kind(r, ROUND_DATA[r]) in ('encore', 'heavy') or unfit(info(data, r)):
            continue
        out.append(r)
    return out


def slot_median(pool):
    return make_round_pools.median([make_round_pools.hp(r) for r in pool])


def slot_target(course, s, pool):
    """The arena HP a slot's pairs aim at (s is 1-based), or None for the encore."""
    if s == 10:  # the encore already fights two bosses
        return None
    return (BOSS_TARGET if s in course.get('bosses', []) else PAIR_TARGET) * slot_median(pool)


NEXT_BOSS = {1: 3, 2: 3, 4: 6, 5: 6, 7: 9, 8: 9}


def slot_cap(course, s):
    """The most HP a combined round of slot s may have (make_round_pools' outlier
    rule): a normal slot's never above the next boss slot's median, slot 9's
    never above the encore's median; None when nothing caps it."""
    slots = course['slots']
    if s in NEXT_BOSS:
        return slot_median(slots[NEXT_BOSS[s] - 1])
    if s == 9 and len(slots) == 10:
        return slot_median(slots[9])
    return None


def candidates(data, design):
    """Per course, per slot: ranked pairs (the encore slot keeps its two-boss rounds)."""
    courses = []
    for course in design['courses']:
        slots = []
        adds = adds_for(course, design, data)
        partners = partners_for(course, data)
        for s, pool in enumerate(course['slots'], 1):
            target = slot_target(course, s, pool)
            if target is None:
                slots.append([])
                continue
            boss = s in course.get('bosses', [])
            slots.append(ranked_pairs(data, pool, target, boss_slot=boss, adds=adds, cap=slot_cap(course, s),
                                      partners=partners))
        courses.append(slots)
    return courses


# Integration into the course pools ------------------------------------------

def settings(design):
    """The design's combined-round setting: {'share': 0..<1, 'mode': repurpose|new}."""
    c = design.get('combined', {})
    out = {'share': float(c.get('share', 0)), 'mode': c.get('mode', 'repurpose')}
    if out['mode'] not in MODES:
        raise ValueError(f"combined mode {out['mode']!r}: one of {MODES}")
    if not 0 <= out['share'] < 1:
        raise ValueError('combined share must be at least 0 and below 1')
    for course in design['courses']:
        share = float(course.get('combined_share', out['share']))
        if not 0 <= share < 1:
            raise ValueError(f"{course['title']}: combined_share {share} must be at least 0 and below 1")
    return out


def wanted(share, singles):
    """Combined entries a slot of `singles` rounds needs so that a uniform draw
    meets a combined round with about this probability."""
    if share <= 0:
        return 0
    return max(1, round(share * singles / (1 - share)))


def allocate(data, design, cands, mode, share=None):
    """The combined rounds for every course slot.

    Returns rows [{'id', 'a', 'b', 'score', 'slots': [[course, slot], ...]}]
    (1-based), in row order. Within a course, a round is a half of combined
    rounds of one slot only, so a run never meets the same group twice. The
    test rounds (course 1's first TEST_SLOTS slots, each slot's easiest pair
    whose halves no earlier test round uses) come first, so the test switch can
    always force them. Then each step takes the pair that serves the most slots
    that still have no combined round, then the most slots short of their
    `wanted` count, then the closest to target; one row serves every slot whose
    candidates hold the same pair. Mode repurpose stops at len(SPARES) rows;
    mode new (a row per pair) when every slot has its count or no pair fits.
    `share` overrides the design's global share (a course's own combined_share
    still applies)."""
    base = settings(design)['share'] if share is None else share
    want, serves, close = {}, {}, {}
    for c, (course, slots) in enumerate(zip(design['courses'], cands), 1):
        course_share = float(course.get('combined_share', base))
        for s, (pool, pairs) in enumerate(zip(course['slots'], slots), 1):
            if not pairs:
                continue
            want[(c, s)] = min(len(pairs), wanted(course_share, len(pool)))
            target = slot_target(course, s, pool)
            for a, b, score in pairs:
                serves.setdefault((a, b), []).append((c, s))
                close[(a, b, c, s)] = abs(score - target) / target
    scores = {(a, b): score for slots in cands for pairs in slots for a, b, score in pairs}
    have = {k: [] for k in want}
    rows, chosen = [], set()

    halves = {}   # (course, round) -> the slot whose combined rounds hold it

    def clash(pair, k):
        """A run of the course could meet one of the pair's rounds in another
        combined round (a partner or boss adds shared between two slots)."""
        return any(halves.get((k[0], r), k[1]) != k[1] for r in pair)

    def take(pair):
        slots = [k for k in serves[pair] if len(have[k]) < want[k] and not clash(pair, k)]
        if not slots or pair in chosen:
            return False
        for k in slots:
            for r in pair:
                halves[(k[0], r)] = k[1]
        chosen.add(pair)
        for k in slots:
            have[k].append(pair)
        rows.append({'a': pair[0], 'b': pair[1], 'score': scores[pair], 'slots': [list(k) for k in slots]})
        return True

    if mode not in MODES:
        raise ValueError(f'mode {mode!r}')
    for s in range(1, TEST_SLOTS + 1):
        pairs = cands[0][s - 1] if want else []
        if want.get((1, s)):
            for a, b, _ in pairs:   # the easiest pair that meets no earlier test round's halves
                if not clash((a, b), (1, s)):
                    take((a, b))
                    break
    limit = len(SPARES) if mode == 'repurpose' else len(serves)
    while len(rows) < limit:
        best = None
        for p in sorted(serves):
            if p in chosen:
                continue
            short = [k for k in serves[p] if len(have[k]) < want[k] and not clash(p, k)]
            if not short:
                continue
            key = (-sum(1 for k in short if not have[k]), -len(short),
                   sum(close[(*p, *k)] for k in short) / len(short), p)
            if best is None or key < best[0]:
                best = (key, p)
        if best is None:
            break
        take(best[1])
    for n, row in enumerate(rows):
        row['id'] = SPARES[n][len(PREFIX):] if mode == 'repurpose' else pair_id(row['a'], row['b'])
    return [{'id': r['id'], 'a': r['a'], 'b': r['b'], 'score': r['score'], 'slots': r['slots']} for r in rows]


def round_entry(rounds, a, b):
    ra, rb = rounds['rounds'][a], rounds['rounds'][b]
    return {'specs': sorted(set(ra['specs']) | set(rb['specs'])), 'enemies': ra['enemies'] + rb['enemies'],
            'level': max(ra['level'], rb['level'])}


def expand(design, rounds, data, rows, mode):
    """The design and round data with combined rounds in the pools (copies), and
    the EnemyTerritory and EnemyTerritoryLevel tables they need. Each slot's pool
    keeps its single rounds first (shipped rounds stay single)."""
    design = copy.deepcopy(design)
    rounds = copy.deepcopy(rounds)
    for row in rows:
        rounds['rounds'][row['id']] = round_entry(rounds, row['a'], row['b'])
        for c, s in row['slots']:
            design['courses'][c - 1]['slots'][s - 1].append(row['id'])
    terr, levels = territory_rows(data, [(PREFIX + r['id'], r['a'], r['b']) for r in rows], mode)
    tables = [{'asset': TERRITORY, 'rows': terr}, {'asset': LEVEL, 'rows': levels}] if rows else []
    return design, rounds, tables


def test_rounds(rows):
    """The rounds the test switch forces as course 1's first rounds."""
    out = []
    for s in range(1, TEST_SLOTS + 1):
        row = next((r for r in rows if [1, s] in r['slots']), None)
        if row is None:
            break
        out.append(row['id'])
    return out


def lua_lines(rows, rounds):
    """buffwheel_data.lua entries: each combined round's halves and enemy count,
    and the rounds the test switch forces."""
    s = json.dumps
    lines = ['  combined = {']
    for r in rows:
        lines.append(f"    [{s(r['id'])}] = {{parts = {{{s(r['a'])}, {s(r['b'])}}}, "
                     f"enemies = {rounds['rounds'][r['a']]['enemies'] + rounds['rounds'][r['b']]['enemies']}}},")
    lines.append('  },')
    lines.append('  combined_test = {' + ', '.join(s(x) for x in test_rounds(rows)) + '},')
    return lines


def build(design, rounds, mode=None):
    """What apply_course_design.py needs: (design, rounds, tables, lua lines, rows),
    the design and rounds being copies with the combined rounds added."""
    data = json.loads(ROWS.read_text(encoding='utf-8'))
    make_round_pools.SPECS.update(rounds['specs'])
    ROUND_DATA.clear()
    ROUND_DATA.update(rounds['rounds'])
    mode = mode or settings(design)['mode']
    rows = allocate(data, design, candidates(data, design), mode)
    expanded, more, tables = expand(design, rounds, data, rows, mode)
    return expanded, more, tables, lua_lines(rows, rounds), rows


def summary(design, rows):
    """Per course: combined rounds per slot and the expected number per run."""
    out = []
    for c, course in enumerate(design['courses'], 1):
        per = [sum(1 for r in rows if [c, s] in r['slots']) for s in range(1, len(course['slots']) + 1)]
        expect = sum(n / (len(pool) + n) for n, pool in zip(per, course['slots']))
        out.append({'title': course['title'], 'per_slot': per, 'total': sum(per), 'per_run': round(expect, 2)})
    return out


def report(design):
    """data/combined-rounds.json's content: candidates and both modes' allocations."""
    data = json.loads(ROWS.read_text(encoding='utf-8'))
    courses = candidates(data, design)
    refused = {}
    for r in sorted({r for c in design['courses'] for slot in c['slots'] for r in slot}):
        why = unfit(info(data, r))
        if why:
            refused[r] = why
    head = {'_about': __doc__.strip().split('\n\n')[0].replace('\n', ' '),
            'rules': {'max_enemies': MAX_ENEMIES, 'max_templates': MAX_TEMPLATES, 'max_specs': MAX_SPECS,
                      'max_large': MAX_LARGE, 'max_flyers': MAX_FLYERS, 'pair_target': PAIR_TARGET,
                      'boss_target': BOSS_TARGET},
            'setting': settings(design),
            'unfit': refused}
    lines = ['{']
    for k, v in head.items():
        lines.append(f'{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},')
    lines.append('"courses": [')
    for n, (c, slots) in enumerate(zip(design['courses'], courses)):
        lines.append(f' {{"title": {json.dumps(c["title"], ensure_ascii=False)}, "slots": [')
        for m, slot in enumerate(slots):
            lines.append('  ' + json.dumps(slot) + (',' if m < len(slots) - 1 else ''))
        lines.append(' ]}' + (',' if n < len(courses) - 1 else ''))
    lines.append('],')
    lines.append('"allocations": {')
    for n, m in enumerate(MODES):
        rows = allocate(data, design, courses, m)
        lines.append(f' {json.dumps(m)}: {{"rows": [')
        for k, r in enumerate(rows):
            lines.append('  ' + json.dumps(r) + (',' if k < len(rows) - 1 else ''))
        lines.append(' ], "summary": [')
        summ = summary(design, rows)
        for k, x in enumerate(summ):
            lines.append('  ' + json.dumps(x, ensure_ascii=False) + (',' if k < len(summ) - 1 else ''))
        lines.append(' ]}' + (',' if n < len(MODES) - 1 else ''))
    lines.append('}}')
    return '\n'.join(lines) + '\n'


def main():
    _, design, _ = load()
    text = report(design)
    OUT.write_text(text, encoding='utf-8')
    out = json.loads(text)
    for m, a in out['allocations'].items():
        print(m, len(a['rows']), 'rows')
        for x in a['summary']:
            print(f"  {x['title']:26} per slot {x['per_slot']}  total {x['total']:2}  per run {x['per_run']}")
    print(len(out['unfit']), 'pooled rounds cannot be combined ->', OUT)


if __name__ == '__main__':
    main()
