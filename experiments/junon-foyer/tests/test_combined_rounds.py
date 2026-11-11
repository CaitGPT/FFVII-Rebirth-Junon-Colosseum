"""Combined rounds (tools/make_combined_rounds.py and their place in the pools)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_course_design  # noqa: E402
import apply_difficulty  # noqa: E402
import make_combined_rounds as m  # noqa: E402

DATA, DESIGN, ROUNDS = m.load()
PAIRS = json.loads((ROOT / 'data/combined-rounds.json').read_text(encoding='utf-8'))
BUFFS = json.loads((ROOT / 'data/buffs.json').read_text(encoding='utf-8'))
SPEC = json.loads((ROOT / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))


def cands():
    m.ROUND_DATA.clear()
    m.ROUND_DATA.update(ROUNDS['rounds'])
    return m.candidates(DATA, DESIGN)


def generate(mode, design=DESIGN):
    return apply_course_design.generate(copy.deepcopy(SPEC), design, ROUNDS, BUFFS, combined_mode=mode)


def test_snapshot_covers_every_pooled_round_and_template():
    pooled = {r for c in DESIGN['courses'] for slot in c['slots'] for r in slot}
    assert {m.PREFIX + r for r in pooled} <= set(DATA['rows'])
    for name, row in DATA['rows'].items():
        for t in row['territory'].get('MobTemplateList_Array', []):
            assert DATA['templates'][t] in DATA['specs']


def test_candidate_file_is_current():
    cands()
    assert (ROOT / 'data/combined-rounds.json').read_text(encoding='utf-8') == m.report(DESIGN), \
        'run tools/make_combined_rounds.py after changing the pools, the rules or the combined setting'


def test_every_candidate_keeps_the_rules_and_its_slot():
    for course, entry in zip(DESIGN['courses'], PAIRS['courses']):
        drawn = {r for slot in course['slots'] for r in slot}
        for s, (pool, pairs) in enumerate(zip(course['slots'], entry['slots']), 1):
            boss = s in course['bosses']
            for a, b, score in pairs:
                ia, ib = m.info(DATA, a), m.info(DATA, b)
                assert m.refusal(ia, ib, boss_slot=boss) is None
                assert a in pool
                # The second half is from the slot's own pool (pools are disjoint within
                # a course) or a round the course never draws, so a run never meets
                # one round twice; boss adds always come from outside the course.
                assert (b not in drawn) if boss else (b in pool or b not in drawn)
                # Balance: never above the next boss slot's median (or the encore's).
                cap = m.slot_cap(course, s)
                assert cap is None or score <= cap, (course['title'], s, a, b)
                assert ia['enemies'] + ib['enemies'] <= m.MAX_ENEMIES == 6   # owner 2026-11-11: cap 6
                assert len(set(ia['specs']) | set(ib['specs'])) <= m.MAX_SPECS
                assert not set(ia['specs']) & set(ib['specs'])
                if boss:   # never two bosses outside the encore: boss plus small adds
                    assert ib['enemies'] <= 3 and not ib['large']


def test_combined_lists_stay_parallel():
    for entry in PAIRS['courses']:
        for pairs in entry['slots']:
            for a, b, _ in pairs:
                ia, ib = m.info(DATA, a), m.info(DATA, b)
                f = m.combine(ia, ib)
                n = len(ia['templates']) + len(ib['templates'])
                assert f['MobTemplateList_Array'] == ia['templates'] + ib['templates']
                for k in ('FieldAINameList_Array', 'MinPopList_Array', 'MaxPopList_Array'):
                    assert len(f[k]) == n, k
                assert len(f['MobLevelList_Array']) in (0, n)   # empty only when both are Lv Sync
                assert len(f['AerialEnemyFlag_Array']) in (0, n)
                waves = [w for w in f['WaveMobTemplateList_Array'] if w]
                assert waves == [w for w in (ia['row'] if ia['waves'] else ib['row']).get('WaveMobTemplateList_Array', []) if w] \
                    or not (ia['waves'] or ib['waves'])


def test_rules_refuse_what_cannot_fight_together():
    small = m.info(DATA, 'GOLDA_04_020')
    lv_sync = next(r for r in DATA['rows'] if r.endswith('_07_050') and m.info(DATA, r[len(m.PREFIX):])['lv_sync'])
    assert m.refusal(small, m.info(DATA, lv_sync[len(m.PREFIX):])) in ('Lv Sync with fixed levels', 'too many large enemies')
    assert m.refusal(small, small) == 'shared enemies (not a new fight)'
    mu = [r for r, row in DATA['rows'].items() if (row['level'] or {}).get('UsePopTargetPoint') == '1']
    for r in mu:
        assert m.unfit(m.info(DATA, r[len(m.PREFIX):])) is not None


def test_spares_are_unused_and_never_training_dummys():
    assert len(m.SPARES) == len(set(m.SPARES)) == 17
    assert not any("Gil" in s for s in m.SPARES)  # owner 2026-11-11: Gilgamesh quest rows stay untouched
    assert m.NEVER not in m.SPARES
    assert set(m.SPARES) <= set(DATA['spares'])
    pooled = {m.PREFIX + r for c in DESIGN['courses'] for slot in c['slots'] for r in slot}
    assert not pooled & set(m.SPARES)
    for name in m.SPARES:
        assert DATA['rows'][name]['level'] is not None   # a level row to rewrite too


@pytest.mark.parametrize('mode', m.MODES)
def test_allocation_serves_only_its_candidate_slots(mode):
    courses = cands()
    rows = m.allocate(DATA, DESIGN, courses, mode)
    assert rows and len({r['id'] for r in rows}) == len(rows)
    if mode == 'repurpose':
        assert len(rows) <= len(m.SPARES)
        assert [m.PREFIX + r['id'] for r in rows] == m.SPARES[:len(rows)]
    else:
        assert all(r['id'] == m.pair_id(r['a'], r['b']) for r in rows)
    for r in rows:
        assert r['slots']
        for c, s in r['slots']:
            assert [r['a'], r['b'], r['score']] in courses[c - 1][s - 1]
            assert s != 10   # the encore keeps its two-boss rounds
    # A course never holds one combined round, or one half, in two slots: a run
    # never meets the same group twice.
    for c in range(1, len(DESIGN['courses']) + 1):
        ids = [r['id'] for r in rows for cc, _ in r['slots'] if cc == c]
        assert len(ids) == len(set(ids))
        where = {}
        for r in rows:
            for cc, s in r['slots']:
                if cc == c:
                    for half in (r['a'], r['b']):
                        assert where.setdefault(half, s) == s, (c, half)
        drawn = {x: s for s, pool in enumerate(DESIGN['courses'][c - 1]['slots'], 1) for x in pool}
        assert all(drawn.get(h, s) == s for h, s in where.items())
    # Course 1's first three slots always get one (the test switch's rounds).
    assert m.test_rounds(rows) == [r['id'] for r in rows[:m.TEST_SLOTS]]
    assert len(m.test_rounds(rows)) == m.TEST_SLOTS


def test_share_sets_how_many_combined_rounds_a_slot_gets():
    courses = cands()
    assert m.wanted(0, 10) == 0 and m.wanted(0.25, 10) == 3 and m.wanted(0.5, 10) == 10 and m.wanted(0.01, 10) == 1
    assert m.allocate(DATA, DESIGN, courses, 'new', share=0) == []
    small = m.allocate(DATA, DESIGN, courses, 'new', share=0.1)
    big = m.allocate(DATA, DESIGN, courses, 'new', share=0.4)
    count = lambda rows: sum(len(r['slots']) for r in rows)  # noqa: E731
    assert count(small) < count(big)
    # A course's own combined_share overrides the global one.
    design = copy.deepcopy(DESIGN)
    design['courses'][1]['combined_share'] = 0
    rows = m.allocate(DATA, design, courses, 'new')
    assert not any(c == 2 for r in rows for c, _ in r['slots'])
    # T1 is limited by the spares, whatever the share.
    assert len(m.allocate(DATA, DESIGN, courses, 'repurpose', share=0.6)) <= len(m.SPARES)
    with pytest.raises(ValueError):
        m.settings({**DESIGN, 'combined': {'share': 1, 'mode': 'repurpose'}})
    with pytest.raises(ValueError):
        m.settings({**DESIGN, 'combined': {'share': 0.2, 'mode': 'runtime'}})


@pytest.mark.parametrize('mode', m.MODES)
def test_generated_build_draws_combined_rounds_like_any_round(mode):
    result, lua = generate(mode)
    tables = {t['asset']: t['rows'] for t in result['tables']}
    terr = {r['name']: r for r in tables[m.TERRITORY]}
    level = {r['name']: r for r in tables[m.LEVEL]}
    assert set(terr) == set(level) and terr
    for name, row in terr.items():
        assert name.startswith('terVR_COL30_')   # the helper's RoundShuffle and buffwheel.lua's round keys
        assert level[name]['set']['UsePopTargetPoint'] == '0'
        if mode == 'new':
            assert row['cloneFrom'].startswith(m.PREFIX) and int(row['set']['UniqueIndex']) not in DATA['unique_indices']
        else:
            assert 'cloneFrom' not in row and 'UniqueIndex' not in row['set'] and name in m.SPARES
    # Every course ships single rounds; combined rounds come after them in the pools.
    for course in tables['DataObject/Resident/Colosseum.uasset']:
        assert not set(course['set']['EnemyTerritoryID_Array']) & set(terr)
    for name in terr:
        rid = name[len(m.PREFIX):]
        assert f'["{rid}"] = {{parts = ' in lua
        assert f'    ["{rid}"] = {{"' in lua   # round_specs: the Lua knows its enemies
    assert 'combined_test = {"' in lua


@pytest.mark.parametrize('mode', m.MODES)
def test_combined_enemies_get_the_course_clones(mode):
    """The course's hidden HP factor and Twisted weaknesses swap every enemy to its
    _JCnn clone, so a combined round's adds need clones too."""
    design, rounds, _, _, rows = m.build(DESIGN, ROUNDS, mode)
    result, _ = generate(mode)
    clones = {r['name'] for t in result['tables'] if t['asset'] == apply_difficulty.SPEC for r in t['rows']}
    owners = apply_difficulty.clone_courses(design)
    ids = {r['id'] for r in rows}
    checked = 0
    for number, course in enumerate(design['courses'], 1):
        if number not in owners:
            continue
        for slot in course['slots']:
            for r in slot:
                if r in ids:
                    for s in rounds['rounds'][r]['specs']:
                        assert apply_difficulty.clone_name(s, owners[number]) in clones, (number, r, s)
                        checked += 1
    assert checked


def test_off_mode_ships_no_combined_rounds():
    result, lua = generate('off')
    assert not any(t['asset'] in (m.TERRITORY, m.LEVEL) for t in result['tables'])
    assert 'combined = {\n  },' in lua and 'combined_test = {},' in lua


def test_the_shipped_build_is_t2():
    # T2 (new rows) proven live 2026-11-11: course 2 control plus three forced rounds, no hang.
    assert m.settings(DESIGN)['mode'] == 'new'
    names = [r['name'] for t in SPEC['tables'] if t['asset'] == m.TERRITORY for r in t['rows']]
    assert names and all(n.startswith(m.PREFIX + 'MIX_') for n in names)
    assert not set(names) & (set(m.SPARES) | {m.NEVER})
