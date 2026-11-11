"""Stat-up materia infusions (owner 2026-11-11) and the Equipment carrier rows the mod adds."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_buff_wheel  # noqa: E402
import apply_difficulty  # noqa: E402

# Every stat-up materia: its Materia row, the vanilla materia earrings (None: the
# mod adds a carrier) and its effect at its highest level, Lv 5 (Materia table
# EffectValue_Array, 2026-07-10 export; the earrings' text says HP Up +30% and
# Luck Up +50%, matching).
STAT_UPS = {
    'HP Up': ('M_IND_001', 'E_ACC_0238', 'max HP +30%'),
    'MP Up': ('M_IND_002', 'E_ACC_0248', 'max MP +30%'),
    'Luck Up': ('M_IND_004', 'E_ACC_0249', 'luck +50%'),
    'Strength Up': ('M_IND_106', None, 'strength +25%'),
    'Magic Up': ('M_IND_003', None, 'magic +25%'),
    'Vitality Up': ('M_IND_108', None, 'vitality +25%'),
    'Spirit Up': ('M_IND_107', None, 'spirit +25%'),
    'Speed Up': ('M_IND_105', None, 'speed +25%'),
}


def buffs():
    return json.loads((ROOT / 'data/buffs.json').read_text(encoding='utf-8'))


def spec_rows(asset):
    spec = json.loads((ROOT / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    return [r for t in spec['tables'] if t['asset'] == asset for r in t['rows']]


def test_every_stat_up_materia_is_a_common_infusion():
    by_label = {b['label']: b for b in buffs()['buffs']}
    for name, (materia, earrings, effect) in STAT_UPS.items():
        b = by_label[f'{name}: {effect}']
        assert b['tier'] == 'common' and b['target'] == 'party', name
        if earrings:
            assert b['accessory'] == earrings and 'materia' not in b, name
        else:
            assert b['materia'] == materia and re.fullmatch(apply_buff_wheel.CARRIER_ID, b['accessory']), name
        assert len(b['label']) <= apply_buff_wheel.LABEL_MAX


def design():
    return json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))


def test_the_spec_carries_one_hp_up_earrings_clone_per_carrier_infusion_and_rank_rule():
    wanted = {b['accessory']: b['materia'] for b in buffs()['buffs'] if 'materia' in b}
    assert len(wanted) == 5
    wanted.update(dict(apply_difficulty.rule_carriers(design())))
    assert wanted['E_ACC_7106'] == 'M_COM_106'                        # Darkside (rank rule, courses 13-14)
    rows = spec_rows(apply_buff_wheel.EQUIPMENT)
    assert len(rows) == len(wanted) == 6
    for row in rows:
        # Only the materia changes: the skill type (100, materia at its highest level) and
        # everyone-can-equip come from HP Up Materia Earrings.
        assert row == {'name': row['name'], 'cloneFrom': 'E_ACC_0238',
                       'set': {'SkillEffectName_Array': [wanted[row['name']]]}}
    assert {r['name'] for r in rows} == set(wanted)


def test_materia_goes_only_with_our_own_carrier_range():
    def design(**extra):
        b = {'id': 'X', 'tier': 'common', 'label': 'X', 'target': 'party'}
        b.update(extra)
        d = buffs()
        d['buffs'] = [b]
        d['per_offer'] = 1
        return d
    apply_buff_wheel.validate(design(accessory='E_ACC_8106', materia='M_IND_106'))
    apply_buff_wheel.validate(design(accessory='E_ACC_7106', materia='M_COM_106'))
    apply_buff_wheel.validate(design(accessory='E_ACC_0238'))
    for bad in (dict(accessory='E_ACC_8106'),                         # our range needs a materia
                dict(accessory='E_ACC_8106', materia='M_COM_106'),    # command materia: 7nnn
                dict(accessory='E_ACC_7106', materia='M_IND_106'),    # independent materia: 8nnn
                dict(accessory='E_ACC_8107', materia='M_IND_106'),    # the number follows the materia
                dict(accessory='E_ACC_8001', materia='M_MAG_001'),    # no carriers for magic materia
                dict(accessory='E_ACC_0238', materia='M_IND_001'),    # vanilla rows take no materia
                dict(accessory='E_ACC_8106', materia='Strength'),     # not a Materia row
                dict(materia='M_IND_106')):                           # a materia needs its carrier
        with pytest.raises(ValueError):
            apply_buff_wheel.validate(design(**bad))
    d = design(accessory='E_ACC_8106', materia='M_IND_106')
    d['buffs'].append(dict(d['buffs'][0], id='Y', accessory='E_ACC_8107'))
    d['per_offer'] = 2
    with pytest.raises(ValueError):
        apply_buff_wheel.validate(d)                                  # one carrier per materia


def test_no_carrier_infusion_means_no_equipment_table():
    d = buffs()
    d['buffs'] = [b for b in d['buffs'] if 'materia' not in b]
    spec = {'tables': [{'asset': apply_buff_wheel.EQUIPMENT, 'rows': [{'name': 'stale'}]}]}
    assert apply_buff_wheel.add_carriers(spec, d) == {'tables': []}


def test_seconds_goes_only_on_a_once_a_round_special():
    """Owner 2026-11-11: Turbulent Spirit lasts 60 s each round ('seconds'), and the
    Revival and Time materia infusions are rare."""
    def design(**extra):
        b = {'id': 'X', 'tier': 'epic', 'label': 'X', 'target': 'party'}
        b.update(extra)
        d = buffs()
        d['buffs'] = [b]
        d['per_offer'] = 1
        return d
    apply_buff_wheel.validate(design(special='ATBRegeneration', each_round=True, seconds=60))
    for bad in (dict(special='ATBRegeneration', seconds=60),                     # lasts the run anyway
                dict(statuses=['BSC_Haste'], seconds=60),                          # not a special
                dict(special='ATBRegeneration', each_round=True, seconds=0),
                dict(special='ATBRegeneration', each_round=True, seconds='60')):
        with pytest.raises(ValueError):
            apply_buff_wheel.validate(design(**bad))
    by_id = {b['id']: b for b in buffs()['buffs']}
    assert by_id['ATBRegen']['seconds'] == 60 and by_id['ATBRegen']['label'] == 'Turbulent Spirit for 60 s each round'
    assert 'seconds' not in by_id['ManaSurge']
    assert by_id['RevivalMateria']['tier'] == 'rare' and by_id['TimeMateria']['tier'] == 'rare'


def test_darkside_carries_the_darkside_materia_for_the_party_from_course_thirteen():
    """Research 2026-11-11: Darkside's HP cost (5% per ability) and potency (+20% at
    Lv 5) are effects of the Darkside materia M_COM_106 (EffectType 16,
    UseAbilityDarkness), not of BSC_Dark. Command materia earrings (Chakra, Prayer)
    are type-100 rows like HP Up's, so the rule's carrier clones HP Up Materia
    Earrings with M_COM_106, numbered 7106 beside Strength Up's 8106."""
    assert apply_buff_wheel.carrier_for('M_COM_106') == 'E_ACC_7106'
    assert apply_buff_wheel.carrier_for('M_IND_106') == 'E_ACC_8106'
    d = design()
    for number in range(1, 15):
        rules = apply_difficulty.course_rules(d, number)
        darkside = number >= 13
        assert rules['party_accessories'] == (['E_ACC_7106'] if darkside else []), number
        assert ('BSC_Dark' in rules['party_status']) == darkside, number
    text = next(m['text'] for m in d['modifiers'] if m.get('status') == 'BSC_Dark')
    assert '5% HP' in text and '20%' in text
    assert {'name': 'E_ACC_7106', 'cloneFrom': 'E_ACC_0238',
            'set': {'SkillEffectName_Array': ['M_COM_106']}} in spec_rows(apply_buff_wheel.EQUIPMENT)
    assert 'E_ACC_7106' not in {b.get('accessory') for b in buffs()['buffs']}   # a rule, never an infusion


def test_a_rule_carrier_needs_its_materia_and_the_matching_row():
    def rules_with(**extra):
        d = design()
        m = dict(next(m for m in d['modifiers'] if m.get('status') == 'BSC_Dark'))
        for k in ('materia', 'accessory'):
            m.pop(k, None)
        m.update(extra)
        d['modifiers'] = [m]
        return apply_difficulty.course_rules(d, 14)
    assert rules_with()['party_accessories'] == []
    for bad in (dict(materia='M_COM_106'), dict(accessory='E_ACC_7106'),
                dict(materia='M_COM_106', accessory='E_ACC_8106')):
        with pytest.raises(ValueError):
            rules_with(**bad)
    with pytest.raises(ValueError):                                     # one row, two materia
        apply_buff_wheel.carrier_rows(buffs(), [('E_ACC_8106', 'M_COM_106')])
