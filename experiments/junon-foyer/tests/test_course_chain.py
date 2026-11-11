import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def spec():
    return json.loads((ROOT / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))


# Best-time slots the game's own 125 courses use (vanilla Colosseum table, 2026-07-10 export).
VANILLA_TIMER_SLOTS = set(range(1, 200)) - {22, 25, 27, 34, 40, 51, 54, 92, 100, 101, 102, 104, 105, 107, 108, 109,
    110, 111, 112, 113, 116, 117, 119, 120, 121, 122, 123, 124, 126, 127, 128, 130, 131, 133, 134, 135, 137, 138, 140,
    142, 143, 144, 145, 146, 148, 149, 152, 153, 154, 155, 156, 158, 161, 162, 165, 167, 168, 174, 175, 177, 178, 180,
    184, 185, 187, 188, 189, 190, 192, 194, 195, 196, 197, 198}


def table(asset):
    return next(t['rows'] for t in spec()['tables'] if t['asset'] == f'DataObject/Resident/{asset}.uasset')


def test_spec_matches_the_course_design():
    result = subprocess.run([sys.executable, str(ROOT / 'tools/apply_course_design.py'), '--check'])
    assert result.returncode == 0, 'run tools/apply_course_design.py after editing data/course-design.json'


def test_fourteen_courses_require_each_previous_victory_without_reusing_vanilla_progress():
    courses = table('Colosseum')
    assert len(courses) == 14  # owner design 2026-11-09
    assert len({r['set']['ClearFlagID'] for r in courses}) == 14
    assert len({r['set']['TimerSaveArrayIndex'] for r in courses}) == 14
    flags = {r['name']: r['set']['UniqueIndex'] for r in table('StoryFlag')}
    assert all(r['set']['ClearFlagID'] in flags for r in courses)
    assert len(set(flags.values())) == len(flags) and all(16233 <= int(i) for i in flags.values())
    for number, row in enumerate(courses, 1):
        fields = row['set']
        assert row['name'] == f'COL30_JUNON_{number:02}_Free_Col'
        assert fields['ClearFlagID'] == f'stfMod_JunonColosseum_{number:02}_Clear'
        expected = 'stfMod_JunonColosseum_AccessEnabled' if number == 1 else courses[number - 2]['set']['ClearFlagID']
        assert fields['OpenFlagID_Array'] == [expected]
        assert fields['DisplayFlagID_Array'] == ['stfMod_JunonColosseum_AccessEnabled']
        assert fields['PlayLogClearFlagID'] == ''
        assert fields['CourseExtra'] == '5'  # the noticeboard menu lists only CourseExtra 5
        assert 1 <= int(fields['TimerSaveArrayIndex']) <= 199
        assert int(fields['TimerSaveArrayIndex']) not in (196, 197, 198)  # composed Training Dummy slots
        assert int(fields['TimerSaveArrayIndex']) not in VANILLA_TIMER_SLOTS


def test_courses_are_multi_round_arena_battles_for_three():
    courses = table('Colosseum')
    rounds = [int(r['set']['BattleMax']) for r in courses]
    assert rounds[0] >= 3 and max(rounds) == 10 and rounds == sorted(rounds)  # native cap: round < 10 (0x14332d8c0)
    for row in courses:
        fields = row['set']
        n = int(fields['BattleMax'])
        assert len(fields['EnemyTerritoryID_Array']) == len(fields['BattleScenePosDataID_Array']) == n
        assert len(fields['UserBattleInSequencerNames_Array']) == n
        # native territories, fought in the Junon arena (owner design), not the simulator
        assert all(t.startswith('terVR_COL30_') for t in fields['EnemyTerritoryID_Array'])
        assert fields['IsVRMission'] == '0' and fields['UserLevelName']
        assert set(fields['BattleScenePosDataID_Array']) <= {r['name'] for r in table('ColosseumPositionData')} | {
            p for p in fields['BattleScenePosDataID_Array'] if p.startswith('POS_COL')}
        assert fields['PartyMax'] == '3' and fields['EntryMember_Array'] == []


def test_enemy_territories_are_only_new_combined_rows():
    # Appending EnemyTerritory clones hung simulator startup with the old writer
    # (Training Dummy 1.0.0); with ours, new rows were proven live on 2026-11-11
    # (combined rounds' T2 test). The shipped spec adds only combined rows
    # terVR_COL30_MIX_<a>_<b>, each a clone, and rewrites no vanilla, spare or
    # Training Dummy territory.
    sys.path.insert(0, str(ROOT / 'tools'))
    import make_combined_rounds as m
    tables = {t['asset']: t['rows'] for t in spec()['tables']}
    for asset in (m.TERRITORY, m.LEVEL):
        rows = tables.get(asset, [])
        assert rows and all('cloneFrom' in r for r in rows), asset
        assert all(r['name'].startswith(m.PREFIX + 'MIX_') for r in rows), asset
        assert m.NEVER not in {r['name'] for r in rows}
    assert {r['name'] for r in tables.get(m.TERRITORY, [])} == {r['name'] for r in tables.get(m.LEVEL, [])}


def test_rewards_are_maxed_materia_from_the_approved_pool():
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    approved = design['approved_materia']
    rewards = {r['name']: r for r in table('Reward')}
    randoms = {r['name']: r for r in table('RewardRandom')}
    indexes = [int(r['set']['UniqueIndex']) for r in rewards.values()]
    assert len(set(indexes)) == len(indexes) and all(65347 <= i < 65536 for i in indexes)
    for course in table('Colosseum'):
        pool = randoms[course['set']['RewardID']]['set']
        assert pool['AbsoluteGetFlagID'] == course['set']['ClearFlagID']  # first clear only
        assert sum(int(w) for w in pool['RewardGetPercent_Array']) == 1000
        for name in pool['RewardID_Array'] + [pool['AbsoluteRewardID']]:
            fields = rewards[name]['set']
            item = fields['ItemID_Array']
            assert len(item) == 1 and item[0] in approved
            assert fields['ItemAddType_Array'] == ['1']  # materia
            assert fields['IntegerArgument_Array'] == [str(approved[item[0]]['max_level'])]  # maxed
    assert rewards['rwrMod_JunonColosseum_Invitation']['set']['ItemID_Array'] == ['key_Mod_JunonColosseumInvitation']


def test_every_owner_materia_can_be_won_and_each_course_lists_its_repeat_rewards():
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    winnable = {c['first_clear'] for c in design['courses']} | {m for c in design['courses'] for m, _ in c['pool']}
    assert set(design['owner_materia']) <= winnable
    for row, course in zip(table('Colosseum'), design['courses']):
        text = row['set']['FlavorTextID']
        assert 'Repeat clears:' in text
        for m, _ in course['pool']:
            assert design['approved_materia'][m]['name'].removesuffix(' Materia') in text


def test_each_course_text_names_the_rule_it_adds():
    """Rules are cumulative from their course ("from"); the board shows the new one."""
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    added = {m['from']: m['text'] for m in design['modifiers']}
    assert sorted(added) == list(range(2, len(design['courses']) + 1))
    for number, course in enumerate(design['courses'], 1):
        if number in added:
            assert f"Rank rule: {added[number]} " in course['flavor'], (number, course['flavor'])
        else:
            assert 'Rank rule:' not in course['flavor']


def test_every_course_ships_its_own_round_list():
    """The native helper finds each course's round list in the loaded table by
    the names it ships with, so no two courses may ship the same list (live
    2026-11-10: six course pairs did; one of each pair was never shuffled and
    the other fought the wrong draw). Each list starts with its own round, none
    is the start of another, and every shipped round is from its slot's pool."""
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    courses = table('Colosseum')
    lists = [tuple(r['set']['EnemyTerritoryID_Array']) for r in courses]
    assert len(lists) == 14 and len(set(lists)) == 14
    assert len({names[0] for names in lists}) == 14
    for i, a in enumerate(lists):
        for j, b in enumerate(lists):
            assert i == j or b[:len(a)] != a, (courses[i]['name'], courses[j]['name'])
    for names, course in zip(lists, design['courses']):
        assert len(names) == len(course['slots'])
        for name, slot in zip(names, course['slots']):
            assert name.startswith('terVR_COL30_') and name.removeprefix('terVR_COL30_') in slot


def test_enemies_shown_by_another_name_reach_their_clones():
    """Live 2026-11-11 the Cactuars (CharaSpec and model SU0008_*) and the ten
    Tonberries (model EN2017_00_Tonberry_Standard, spec ..._VR) kept their HP:
    every course spec that shows another name is in spec_names, and each has clones."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import apply_difficulty
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    rounds = json.loads((ROOT / 'data/round-data.json').read_text(encoding='utf-8'))
    charas, models = apply_difficulty.spec_names(design, rounds)
    assert charas['SU0008_05_Cactuar_JapoEnd2'] == 'EN2259_05_Cactuar_JapoEnd2'
    assert models['EN2017_00_Tonberry_Standard'] == ['EN2017_00_Tonberry_Standard_VR']
    assert models['EN0008_00_Vice_Standard'] == ['EN0008_00_Vice_Standard_Scimitar']
    assert 'FA0052_12_Dummy_AdamantaimaiMoss' not in charas  # its body's clone covers it
    clones = {r['name'] for r in table('BattleCharaSpec')}
    named = set(charas.values()) | {s for specs in models.values() for s in specs}
    owners = apply_difficulty.clone_courses(design)
    for number, course in enumerate(design['courses'], 1):
        met = {s for slot in course['slots'] for r in slot for s in rounds['rounds'][r]['specs']} & named
        assert number not in owners or all(f'{s}_JC{owners[number]:02}' in clones for s in met)
