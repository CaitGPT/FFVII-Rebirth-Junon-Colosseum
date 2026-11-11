"""Write the enemy-setup diagnostic spec: four unlocked test courses.

The black Get Ready stall could come from the copied arena (battle plan,
points, intro camera) or from our enemy setup. Every native colosseum
territory uses enemy templates that some native course uses, and its
EnemyTerritoryLevel row has SituationType 1. Our two reused test rows have
SituationType 0, and the soldier templates AE used appear in no native
territory. Each test course changes one of these, so one build answers it:

  Test 1  native prison territory + native prison positions (arena control)
  Test 2  as Test 1 without the intro camera sequence
  Test 3  reused row, soldier templates proven in the Gold Saucer colosseum,
          level row unchanged (SituationType 0)
  Test 4  as Test 3 on the other reused row, with that row's level set like
          the Gold Saucer colosseum (SituationType 1, common win trigger)

Courses 5-7 keep their default rows (still locked). The default spec is not
changed. Usage: python make_enemy_diagnostic_spec.py <default spec> <output>
"""
import copy
import json
import sys
from pathlib import Path

COURSES = 'DataObject/Resident/Colosseum.uasset'
TERRITORY = 'DataObject/Resident/EnemyTerritory.uasset'
LEVEL = 'DataObject/Resident/EnemyTerritoryLevel.uasset'
PRISON = 'terVR_COL30_UNDRS_01_010'
PRISON_POS = 'POS_COL30_UNDRS_01_010'
OWN_POS = 'POS_Mod_JunonColosseum'
REUSED_A = 'terVR_COL30_BatteTest_01_010'
REUSED_B = 'terVR_COL30_SUMMON_SummonsTest'
# Both appear in native terVR_COL30_GOLDA_03_020 (Gold Saucer colosseum).
SOLDIERS = ['mobcolvr_EN0000_01_SecuritySoldier_Senior_00',
            'mobcolvr_EN0000_12_SecuritySoldier_SeniorVer1End2_00']
ACCESS = ['stfMod_JunonColosseum_AccessEnabled']

TESTS = {
    'COL30_JUNON_01_Free_Col': ('Test 1: Prison enemies', [PRISON], [PRISON_POS], True),
    'COL30_JUNON_02_Free_Col': ('Test 2: Prison, no intro', [PRISON], [PRISON_POS], False),
    'COL30_JUNON_03_Free_Col': ('Test 3: Soldiers, reused row', [REUSED_A], [OWN_POS], True),
    'COL30_JUNON_04_Free_Col': ('Test 4: Soldiers, colosseum row', [REUSED_B], [OWN_POS], True),
}


def main(source: str, output: str) -> None:
    spec = json.loads(Path(source).read_text(encoding='utf-8-sig'))
    spec = copy.deepcopy(spec)
    seen = set()
    for table in spec['tables']:
        for row in table['rows']:
            if table['asset'] == COURSES and row['name'] in TESTS:
                title, territories, positions, intro = TESTS[row['name']]
                s = row['set']
                assert s.get('UserLevelName') == '1300-JUNOA_BattlePlan_ModJunonColosseum', row['name']
                s.update({'ItemName': title, 'DisplayItemName': title,
                          'FlavorTextID': 'Junon Colosseum diagnostic: ' + title,
                          'DisplayFlavorItemName': 'Junon Colosseum diagnostic: ' + title,
                          'EnemyTerritoryID_Array': territories,
                          'BattleScenePosDataID_Array': positions,
                          'BattleMax': '1', 'DisplayFlagID_Array': ACCESS, 'OpenFlagID_Array': ACCESS})
                # One battle each, so exactly one intro entry (or none).
                s['UserBattleInSequencerNames_Array'] = ['CSA_VrCoBattleIn_Common_US'] if intro else []
                seen.add(row['name'])
            if table['asset'] == TERRITORY and row['name'] in (REUSED_A, REUSED_B):
                row['set'].update({'FieldAINameList_Array': ['Stay', 'Stay'],
                                   'MobTemplateList_Array': list(SOLDIERS),
                                   'MinPopList_Array': ['1', '1'], 'MaxPopList_Array': ['1', '1'],
                                   'MobLevelList_Array': ['30', '30']})
                seen.add(row['name'])
    if any(t['asset'] == LEVEL for t in spec['tables']):
        raise SystemExit('default spec already edits EnemyTerritoryLevel; review before adding Test 4')
    spec['tables'].append({'asset': LEVEL, 'rows': [{
        'name': REUSED_B,
        'set': {'SituationType': '1', 'KillStateTrigger_Array': ['trgCmn_colosseum_win']}}]})
    missing = set(TESTS) | {REUSED_A, REUSED_B}
    missing -= seen
    if missing:
        raise SystemExit(f'default spec rows not found: {sorted(missing)}')
    Path(output).write_text(json.dumps(spec, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
