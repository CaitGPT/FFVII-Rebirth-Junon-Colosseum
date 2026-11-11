"""Balance (owner 2026-11-11): harder than every vanilla challenge, no outliers,
rising slot medians, course 14 at about 1.3x vanilla's hardest course."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_difficulty  # noqa: E402
import make_combined_rounds as mc  # noqa: E402
import make_round_pools as mp  # noqa: E402

DESIGN, ROUNDS = mp.load()
ROUND_DATA = json.loads((ROOT / 'data/round-data.json').read_text(encoding='utf-8'))
SPEC = json.loads((ROOT / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
BONDS = 1_253_000   # Legendary "Bonds of Friendship" at Lv70 (main enemies), the hardest vanilla course


def factor(c):
    return apply_difficulty.course_rules(DESIGN, c)['hp']


def total(c):
    return mp.course_total(DESIGN['courses'][c - 1]['slots']) * factor(c)


def test_hp_model_matches_the_live_numbers():
    """Live 2026-11-11: HP = spec HP x Enemy_<level>.HPMax / 100 at max(listed, 67)."""
    factors = {int(k): v for k, v in mp.rows()['level_hp'].items()}
    assert factors[67] == 39.45 and factors[70] == 40.17
    assert round(mp.hp('GOLDA_21_020'), -3) == 237_000      # ten Tonberries
    assert round(mp.hp('EXTRA_05_040'), -3) == 46_000       # the weak encore pair


def test_the_design_is_what_the_generator_makes():
    pools, factors = mp.build(DESIGN, ROUNDS)
    assert [c['slots'] for c in DESIGN['courses']] == pools, 'run tools/make_round_pools.py'
    assert [c['hp_factor'] for c in DESIGN['courses']] == factors


def test_every_course_keeps_the_outlier_and_rising_rules():
    for c, course in enumerate(DESIGN['courses'], 1):
        assert mp.check(course['slots'], c == len(DESIGN['courses'])) is None, course['title']


def test_the_rules_hold_with_combined_rounds_in_the_pools():
    design, _, _, _, rows = mc.build(DESIGN, ROUND_DATA)
    for row in rows:
        mp.HPS[row['id']] = mp.hp(row['a']) + mp.hp(row['b'])
    for c, course in enumerate(design['courses'], 1):
        assert mp.check(course['slots'], c == len(design['courses'])) is None, course['title']


def test_two_boss_rounds_only_in_the_encore():
    kinds = {k: mp.kind(k, r) for k, r in ROUNDS.items()}
    for c, course in enumerate(DESIGN['courses'], 1):
        for s, pool in enumerate(course['slots'], 1):
            for r in pool:
                assert (kinds[r] == 'encore') == (s == 10), (c, s, r)
                if s in (1, 2, 4, 5, 7, 8):
                    assert kinds[r] == 'normal', (c, s, r)
    # Owner findings: GOLDA_11_010 (two Elfadunk subspecies) is not a boss; the
    # weak encore pairs are gone; the Elfadunk subspecies alone is not a slot 3 boss.
    assert kinds['GOLDA_11_010'] == 'normal'
    encore = DESIGN['courses'][-1]['slots'][9]
    assert 'EXTRA_05_040' not in encore and 'EXTRA_05_010' not in encore
    assert all('EXTRA_11_020' not in c['slots'][2] for c in DESIGN['courses'])


def test_course_14_is_well_above_vanillas_hardest():
    assert total(14) >= 1_600_000 and total(14) >= 1.3 * BONDS


def test_courses_ramp_smoothly():
    totals = [total(c) for c in range(1, 15)]
    assert totals == sorted(totals)
    for a, b in zip(totals, totals[1:]):
        assert b / a <= 1.35, (a, b)        # no course is a cliff over the one before
    factors = [factor(c) for c in range(1, 15)]
    assert factors == sorted(factors) and factors[0] == 1.0
    assert all(c.get('hp_factor', 1) >= 1 and 'hp_scale' not in c for c in DESIGN['courses'])


def test_the_clones_carry_the_course_hp_factor():
    clones = {r['name']: r for t in SPEC['tables'] if t['asset'] == apply_difficulty.SPEC for r in t['rows']}
    owners = apply_difficulty.clone_courses(DESIGN)
    for c in (2, 3, 14):
        spec = ROUND_DATA['rounds'][DESIGN['courses'][c - 1]['slots'][0][0]]['specs'][0]
        row = clones[apply_difficulty.clone_name(spec, owners[c])]
        assert int(row['set']['HP']) == round(int(ROUND_DATA['specs'][spec]['HP']) * factor(c))


# The HP ladder before Rally replaced Tough hides (acc061f: hp_scale x Tough hides'
# 1.25 from course 3): the whole factor per course, which course owns each clone
# set, the clone rows and the median course totals. Rally must change none of them.
LADDER = [1.0, 1.25, 1.25, 1.25, 1.5, 1.5, 1.75, 1.75, 1.75, 2.0, 2.25, 2.25, 2.5, 2.5]
CLONE_OWNERS = {2: 2, 3: 2, 4: 2, 5: 5, 6: 5, 7: 7, 8: 7, 9: 7, 10: 10, 11: 11, 12: 11, 13: 13, 14: 13}
CLONE_ROWS = 927
TOTALS = [522032, 652539, 675991, 689552, 827463, 841912, 984611, 988126, 1005568, 1159898,
          1304885, 1327457, 1505781, 1986610]


def clone_rows():
    return [r for t in SPEC['tables'] if t['asset'] == apply_difficulty.SPEC for r in t['rows'] if '_JC' in r['name']]


def test_the_hp_ladder_is_unchanged_by_rally():
    """Owner 2026-11-11: the hidden per-course HP factor keeps the 25% Tough hides
    gave, so balance numbers and clone sets are what they were."""
    assert [c['hp_factor'] for c in DESIGN['courses']] == LADDER
    assert [factor(c) for c in range(1, 15)] == LADDER
    assert apply_difficulty.clone_courses(DESIGN) == CLONE_OWNERS
    assert len(clone_rows()) == CLONE_ROWS
    assert [round(total(c)) for c in range(1, 15)] == TOTALS


def test_no_rank_rule_names_the_hp_factor():
    """The ladder is hidden: no modifier changes HP, and Tough hides is gone."""
    for m in DESIGN['modifiers']:
        assert 'hp' not in m or m['kind'] == 'party_recovery', m
        assert 'Tough hides' not in m['text'] and 'more HP' not in m['text']
    for c in DESIGN['courses']:
        assert 'Tough hides' not in c['flavor']
    bad = {**DESIGN, 'modifiers': [{'from': 3, 'kind': 'enemy_spec', 'hp': 1.25, 'text': 'x'}]}
    with pytest.raises(ValueError):
        apply_difficulty.course_rules(bad, 3)     # a rank rule may not add HP
    old = json.loads(json.dumps(DESIGN))
    old['courses'][2]['hp_scale'] = 1.0
    with pytest.raises(ValueError):
        apply_difficulty.course_rules(old, 3)     # the old partial scale is refused


def test_rally_is_course_threes_rule_and_holds_after():
    rally = [m for m in DESIGN['modifiers'] if m['kind'] == 'rally']
    assert rally == [{'from': 3, 'kind': 'rally', 'text':
                      'Rally: whenever an enemy falls, every surviving enemy gains a random Mako infusion.'}]
    assert DESIGN['courses'][2]['flavor'] == ('Rank rule: Rally: whenever an enemy falls, every surviving enemy '
                                              'gains a random Mako infusion. Every earlier rule still applies.')
    assert [apply_difficulty.course_rules(DESIGN, c)['rally'] for c in range(1, 15)] == [False, False] + [True] * 12
    bad = {**DESIGN, 'modifiers': [{'from': 3, 'kind': 'rally', 'count': 2, 'text': 'x'}]}
    with pytest.raises(ValueError):
        apply_difficulty.course_rules(bad, 3)


def test_the_clones_carry_only_the_hp_factor_and_twisted_weaknesses():
    """Each clone row changes HP by its course's factor and, from Twisted
    weaknesses (course 7), turns weaknesses into absorption; attack is unchanged,
    and no other field is set."""
    owners = sorted(set(CLONE_OWNERS.values()))
    seen = {o: 0 for o in owners}
    for row in clone_rows():
        spec, owner = row['cloneFrom'], int(row['name'][-2:])
        assert row['name'] == apply_difficulty.clone_name(spec, owner) and owner in seen
        seen[owner] += 1
        base = ROUND_DATA['specs'][spec]
        fields = row['set']
        assert int(fields['HP']) == round(int(base['HP']) * LADDER[owner - 1])
        assert fields['PhysicsAttack'] == str(int(base['PhysicsAttack']))
        assert fields['MagicAttack'] == str(int(base['MagicAttack']))
        if owner >= 7:
            want = ['5' if v == '1' else v for v in base['AttributeResist_Array']]
            assert fields['AttributeResist_Array'] == want
            assert set(fields) == {'HP', 'PhysicsAttack', 'MagicAttack', 'AttributeResist_Array'}
        else:
            assert set(fields) == {'HP', 'PhysicsAttack', 'MagicAttack'}
    assert all(seen.values()), seen
    # Twisted weaknesses still turns a weakness somewhere into absorption.
    assert any('1' in ROUND_DATA['specs'][r['cloneFrom']]['AttributeResist_Array']
               for r in clone_rows() if int(r['name'][-2:]) >= 7)
