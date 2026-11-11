"""Darkside's HP cost (live 2026-11-11: neither BSC_Dark nor the Darkside materia's
carrier cost any HP): the abilities it charges (data/darkside-abilities.json, from
the vanilla BattleAbility table) and the rule's data."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest
from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_difficulty  # noqa: E402
import extract_darkside_abilities as dark  # noqa: E402

SNAP = json.loads((ROOT / 'data/darkside-abilities.json').read_text(encoding='utf-8'))
DESIGN = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))


def test_the_rules_classify_each_kind_of_action():
    rows = {
        'PC0000_AtkBurst01': ('1', '1'),            # Braver: a weapon ability
        'PC0001_AtkBurst02_ATB_2': ('1', '2'),      # Barret's variant row by ATB spent
        'PC0000_EleBurst01': ('1', '1'),            # a folio elemental ability
        'PC0002_AtkBurst10_B': ('1', '0'),          # a free follow-up
        'PC0001_SAtk_MAX': ('0', '0'),              # Barret's Overcharge (unique)
        'PC0000_NAtk_1': ('0', '0'),                # basic attack
        'M_MAG_001_heal001_01': ('2', '1'),         # Cure
        'PC0000_Limit001': ('3', '0'),
        'it_potion': ('4', '1'),
        'PC0000_PC0001_BurstChain01': ('5', '2'),   # a synergy ability
        'M_CMD_105_atk001_01': ('1', '2'),          # Jump
        'M_CMD_003_atk002_01_MoogleRide': ('1', '1'),  # Enemy Skill, Cait Sith's ride row
        'M_CMD_002_atk001_01': ('1', '1'),          # Assess
        'M_CMD_001_atk001_01': ('1', '1'),          # Steal
        'M_CMD_006_heal001_01': ('1', '2'),         # Prayer
        'M_CMD_106_atk001_01': ('1', '1'),          # Darkside
        'M_SMN_004_atk001_01': ('1', '1'),          # a summon
    }
    cost, toggle, excluded = dark.classify({k: {'CommandType': t, 'ATB': a} for k, (t, a) in rows.items()})
    assert cost == {'PC0000_AtkBurst01': 'PC0000_AtkBurst01', 'PC0001_AtkBurst02_ATB_2': 'PC0001_AtkBurst02',
                    'PC0000_EleBurst01': 'PC0000_EleBurst01', 'M_CMD_105_atk001_01': 'M_CMD_105_atk001',
                    'M_CMD_003_atk002_01_MoogleRide': 'M_CMD_003_atk002'}
    assert toggle == ['M_CMD_106_atk001_01']
    assert excluded['atb_free'] == ['PC0002_AtkBurst10_B']
    assert sorted(excluded['utility']) == ['M_CMD_001_atk001_01', 'M_CMD_002_atk001_01', 'M_CMD_006_heal001_01']
    assert (excluded['magic'], excluded['limit'], excluded['item'], excluded['synergy'], excluded['summon']) == (1, 1, 1, 1, 1)


def test_the_snapshot_holds_only_abilities_and_attack_commands():
    cost = SNAP['cost']
    assert len(cost) == 170 and len(set(cost.values())) == 114
    assert SNAP['toggle'] == ['M_CMD_106_atk001_01']
    for name, family in cost.items():
        assert dark.WEAPON.match(name) or re.match(r'^M_CMD_(003|101|102|105)_', name), name
        assert name.startswith(family), name
        assert not name.startswith(('M_MAG', 'M_SMN', 'M_CMD_106', 'IT_', 'it_')) and 'Limit' not in name
    # Live IDs (harness, 2026-11-11): Barret's, Tifa's and Aerith's abilities cost; the rest never.
    for name in ('PC0001_AtkBurst02_ATB_1', 'PC0002_AtkBurst07', 'PC0002_AtkBurst02', 'PC0003_AtkBurst03'):
        assert name in cost
    for name in ('PC0001_SAtk_MAX', 'PC0001_SAtk_RE', 'PC0003_Limit001', 'PC0001_PC0002_BurstChain01_B',
                 'M_MAG_004_atk002_01_SP', 'M_SMN_004_atk001_01', 'PC0003_ChainGuard1_UC', 'PC0001_NAtk_1'):
        assert name not in cost
    # Every party character's weapon abilities are there.
    for pc in ('PC0000', 'PC0001', 'PC0002', 'PC0003', 'PC0004', 'PC0005', 'PC0007'):
        assert any(n.startswith(pc + '_AtkBurst') for n in cost), pc


def test_buffwheel_data_carries_the_snapshot():
    lua = LuaRuntime(unpack_returned_tuples=True)
    data = lua.execute((ROOT / 'ue4ss/JunonColosseum/Scripts/buffwheel_data.lua').read_text(encoding='utf-8'))
    assert dict(data.darkside_cost.items()) == SNAP['cost']
    assert list(data.darkside_toggle.keys()) == SNAP['toggle']


def test_only_darkside_courses_cost_hp_per_ability():
    for number in range(1, len(DESIGN['courses']) + 1):
        cost = apply_difficulty.course_rules(DESIGN, number)['ability_cost']
        assert cost == ({'status': 'BSC_Dark', 'percent': 5} if number >= 13 else None), number


@pytest.mark.parametrize('change, message', [
    ({'hp_cost': 0}, 'whole percentage'),
    ({'hp_cost': 5.5}, 'whole percentage'),
    ({'materia': None}, 'needs the materia'),
])
def test_an_ability_cost_is_checked(change, message):
    design = copy.deepcopy(DESIGN)
    rule = next(m for m in design['modifiers'] if m.get('status') == 'BSC_Dark')
    for k, v in change.items():
        if v is None:
            rule.pop(k)
            rule.pop('accessory')
        else:
            rule[k] = v
    with pytest.raises(ValueError, match=message):
        apply_difficulty.course_rules(design, 13)
