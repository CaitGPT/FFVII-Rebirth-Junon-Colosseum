"""Write data/course-design.json into the Colosseum, Reward and RewardRandom
rows of data/junon-arena.json. Run after editing the design; the tests fail
when the two disagree.

Courses fight in the Junon arena beside the foyer (battle mode "arena", the
owner's design), or in the game's own Combat Simulator arena (mode
"simulator"). Either way the foyer's noticeboard opens them.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_buff_wheel  # noqa: E402
import apply_difficulty  # noqa: E402
import make_combined_rounds  # noqa: E402
import extract_darkside_abilities  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'data/junon-arena.json'
DESIGN = ROOT / 'data/course-design.json'
BUFFS = ROOT / 'data/buffs.json'
ROUND_DATA = ROOT / 'data/round-data.json'
BUFF_LUA = ROOT / 'ue4ss/JunonColosseum/Scripts/buffwheel_data.lua'
# The abilities a Darkside use costs HP for (tools/extract_darkside_abilities.py).
DARKSIDE = ROOT / 'data/darkside-abilities.json'
COLOSSEUM = 'DataObject/Resident/Colosseum.uasset'
REWARD = 'DataObject/Resident/Reward.uasset'
RANDOM = 'DataObject/Resident/RewardRandom.uasset'
# Only our physical-arena experiments used these; simulator rounds need neither.
RETIRED = ('DataObject/Resident/EnemyTerritory.uasset',)
# Combined rounds' rows (make_combined_rounds.py), written fresh by every run.
TERRITORY_TABLES = (make_combined_rounds.TERRITORY, make_combined_rounds.LEVEL)
INVITATION_REWARD = 'rwrMod_JunonColosseum_Invitation'
ACTION = 'DataObject/Resident/Action.uasset'
POSITION = 'DataObject/Resident/ColosseumPositionData.uasset'
OPEN_MENU = 'actMod_JunonColosseum_OpenMenu'
STORY = 'DataObject/Resident/StoryFlag.uasset'
CLEAR_FLAG_INDEX = {1: 16235, 2: 16236, 3: 16237, 4: 16241, 5: 16242, 6: 16243, 7: 16244}  # existing rows
NEW_CLEAR_FLAG_START = 16248  # courses 8+ (vanilla StoryFlag indices end at 16232; ours 16233-16247)
# compat.lua sets it when Training Dummy is installed; merge_specs.py shows its courses through it.
TRAINING_DUMMY_FLAG = ('stfMod_JunonColosseum_TrainingDummyShown', 16255)


def shipped_rounds(design):
    """The rounds each course's row ships with, in course order. In game the
    native helper rewrites them with a fresh draw for every run (buffwheel.lua).
    It finds a course's round list in the loaded table by these names (the rows'
    arrays are not decoded there), so no two courses may ship the same list:
    courses with the same slot pools (02/03, 04/05, ...) once did, and one of each
    pair was never shuffled while the other fought the wrong draw (live
    2026-11-10, draw_mismatch). Each course ships the first candidate of its first
    slot that no earlier course ships first (so every list starts with its own
    round) and the first candidate of every other slot."""
    taken, out = set(), []
    for course in design['courses']:
        first = next((r for r in course['slots'][0] if r not in taken), None)
        if first is None:
            raise ValueError(f"{course['title']}: every first-slot round is another course's first round")
        taken.add(first)
        out.append([first] + [slot[0] for slot in course['slots'][1:]])
    if len({tuple(r) for r in out}) != len(out):
        raise ValueError('two courses ship the same round list')
    return out


def flavor(course, design):
    """The course text plus its repeat-clear materia: the board shows only the
    first-clear reward (owner 2026-11-10: say what else can be won)."""
    names = [design['approved_materia'][m]['name'].removesuffix(' Materia') for m, _ in course['pool']]
    listed = ', '.join(names[:-1]) + ' or ' + names[-1] if len(names) > 1 else names[0]
    return f"{course['flavor']} Repeat clears: {listed}."


def course_fields(number, course, design, previous_clear):
    rounds = shipped_rounds(design)[number - 1]
    if not 1 <= len(rounds) <= design['max_rounds']:
        raise ValueError(f"{course['title']}: 1 to {design['max_rounds']} rounds")
    if not 1 <= design['party_max'] <= 3:
        raise ValueError('party_max is 1 to 3')
    clear = f'stfMod_JunonColosseum_{number:02}_Clear'
    battle = {**design['battle'], **course.get('battle', {})}
    if battle['mode'] == 'simulator':
        place = {
            'IsVRMission': '1', 'BattleWarpPoint': 'Point_VRBattle', 'UserLevelName': '',
            'TerritoryActorName': 'VRBattle_TerritoryCmnActor',
            'BattleScenePosDataID_Array': [f'POS_COL30_{r}' for r in rounds],
            'UserBattleInSequencerNames_Array': ['CSA_VrCoBattleIn_Common'] + ['CSA_VrCoBattleIn_Common_R2'] * (len(rounds) - 1),
            'UserWinnerSequencerName': 'CSA_VrCoBattleClear_Common',
            'BattleBgm_Array': ['bgm_End2_vr_coliseum_098'],
        }
    elif battle['mode'] == 'arena':
        place = {
            'IsVRMission': '0', 'BattleWarpPoint': battle['warp_point'], 'UserLevelName': battle['user_level'],
            'TerritoryActorName': battle['territory_actor'],
            'BattleScenePosDataID_Array': [battle['position']] * len(rounds),
            'UserBattleInSequencerNames_Array': [battle['battle_in']] * len(rounds),
            'UserWinnerSequencerName': battle['winner'],
        }
    else:
        raise ValueError(f"battle mode {battle['mode']!r}")
    music = design.get('music')
    if music:
        # Owner 2026-11-10: every course plays the same list, a different track each
        # round; the last entry is the final course's encore round.
        place['BattleBgm_Array'] = [music['rounds'][i] for i in range(len(rounds))]
        if music.get('menu') or music.get('lose'):
            place['OverrideBGM_Array'] = [music.get('menu', ''), '', music.get('lose', ''), '']
        if music.get('fanfare'):
            place['OverrideFanfareID'] = music['fanfare']
    return clear, {**place,
        'CourseExtra': '5',
        'ItemName': course['title'],
        'DisplayItemName': course['title'],
        'FlavorTextID': flavor(course, design),
        'DisplayFlavorItemName': flavor(course, design),
        'EnemyTerritoryID_Array': [f'terVR_COL30_{r}' for r in rounds],
        'BattleMax': str(len(rounds)),
        'UserBattleInSequencerName': '',
        'BattleEntryCutID_Array': [],
        'PartyMax': str(design['party_max']),
        'EntryMember_Array': [],
        **team_fields(design),
        'RecommendedLevelID': course['recommended'],
        'RewardID': f'rwrdMod_JunonColosseum_{number:02}',
        'ClearFlagID': clear,
        'PlayLogClearFlagID': '',
        'DisplayFlagID_Array': ['stfMod_JunonColosseum_AccessEnabled'],
        'OpenFlagID_Array': [previous_clear or 'stfMod_JunonColosseum_AccessEnabled'],
        'OpenConditionClearCheckID': '', 'OpenConditionTextID': '',
        'OpenConditionClearCheckID01': '', 'OpenConditionTextID01': '',
        'OpenConditionClearCheckID02': '', 'OpenConditionTextID02': '',
        'PreNotifyActionOrActionGroupID': '',
        'PostNotifyActionOrActionGroupID': '',
        'CourseSelectStateTriggerID': '',
        'CourseStartStateTrigger_Array': [],
        'CourseClearStateTrigger_Array': [],
    }


def team_fields(design):
    """How many fighters the player picks. teams 2 is the Gold Saucer's two-team
    mode (pick two parties of party_max): one selection prompt per team plus
    ExtraRule 1, as on vanilla's COL30_GOLDA rows. Live 2026-11-09: without
    ExtraRule 1 the menu asks for one team only. ("Lv Sync" on the board comes
    from RecommendedLevel -2, not from this rule.)"""
    if design.get('teams', 1) == 2:
        return {'MemberSelectionTextID_Array': ['$menu_Colosseum_muscle_partyA_help', '$menu_Colosseum_muscle_partyB_help'],
                'MemberCountTextID': '$menu_Colosseum_SystemWord_MemberCount_TwoPair', 'ExtraRule_Array': ['1']}
    pair = design['party_max'] == 2
    return {'MemberSelectionTextID_Array': ['$menu_Colosseum_CourseRule_NumberLimit_Pair' if pair
                                            else '$menu_Chadrey_VR_CourseRule_NumberLimit'],
            'MemberCountTextID': '$menu_Colosseum_SystemWord_MemberCount_Pair' if pair
                                 else '$menu_Chadrey_VR_SystemWord_MemberCount',
            'ExtraRule_Array': []}


def reward_row(name, materia, level, index):
    """One materia at a set level (ItemAddType 1 = materia, IntegerArgument = level),
    cloned from a vanilla colosseum materia reward."""
    return {'name': name, 'cloneFrom': 'rwdCOL30_GRASA_05',
            'set': {'ItemID_Array': [materia], 'ItemCount_Array': ['1'], 'ItemAddType_Array': ['1'],
                    'IntegerArgument_Array': [str(level)], 'UniqueIndex': str(index)}}


def clear_flags(tables, count):
    """Clear flags for every course; rows for courses beyond the first seven are added."""
    rows = tables[STORY]['rows']
    names = {r['name'] for r in rows}
    for number in range(8, count + 1):
        name = f'stfMod_JunonColosseum_{number:02}_Clear'
        if name not in names:
            rows.append({'name': name, 'cloneFrom': 'stfCmnChapter12_Visited',
                         'set': {'UniqueIndex': str(NEW_CLEAR_FLAG_START + number - 8), 'ChapterID': 'Chapt_None'}})
    name, index = TRAINING_DUMMY_FLAG
    if index < NEW_CLEAR_FLAG_START + count - 7:
        raise ValueError('the Training Dummy flag index collides with a clear flag')
    if name not in names:
        rows.append({'name': name, 'cloneFrom': 'stfCmnChapter12_Visited',
                     'set': {'UniqueIndex': str(index), 'ChapterID': 'Chapt_None'}})


def apply(spec, design, rewards_enabled=True):
    tables = {t['asset']: t for t in spec['tables']}
    old = {r['name']: r for r in tables[COLOSSEUM]['rows']}
    courses, rewards, randoms = [], [], []
    approved = design['approved_materia']
    index = design['reward_index_start']
    if len(design['courses']) > 14:
        raise ValueError('at most 14 courses (free best-time slots and flags are planned for 14)')
    clear_flags(tables, len(design['courses']))
    previous = None
    for number, course in enumerate(design['courses'], 1):
        name = f'COL30_JUNON_{number:02}_Free_Col'
        timer = str(course['timer'])  # the course's best-time slot: one unused by the game
        drawn = [r for slot in course['slots'] for r in slot]
        if len(drawn) != len(set(drawn)):
            raise ValueError(f"{course['title']}: a round is in two of its slots (a run could draw it twice)")
        clear, fields = course_fields(number, course, design, previous)
        fields['TimerSaveArrayIndex'] = timer
        courses.append({'name': name, 'cloneFrom': 'COL30_UNDRS_01_Free_Col', 'set': fields})
        stem = f'rwdMod_JunonColosseum_{number:02}'
        pool = course['pool']
        if not 1 <= len(pool) <= 4 or sum(w for _, w in pool) != 1000:
            raise ValueError(f"{course['title']}: one to four pool entries whose weights total 1000")
        for materia in [course['first_clear']] + [m for m, _ in pool]:
            if materia not in approved:
                raise ValueError(f"{course['title']}: {materia} is not an approved materia")
        first = course['first_clear']
        rewards.append(reward_row(stem + '_First', first, approved[first]['max_level'], index)); index += 1
        for slot, (materia, _) in enumerate(pool, 1):
            rewards.append(reward_row(f'{stem}_{slot}', materia, approved[materia]['max_level'], index)); index += 1
        randoms.append({'name': f'rwrdMod_JunonColosseum_{number:02}', 'cloneFrom': 'rwrdCOL30_UNDRS_01',
                        'set': {'RewardID_Array': [f'{stem}_{slot}' for slot in range(1, len(pool) + 1)],
                                'RewardGetPercent_Array': [str(w) for _, w in pool],
                                'AbsoluteRewardID': stem + '_First',
                                'AbsoluteGetFlagID': clear}})
        previous = clear
    if index >= 65536:
        raise ValueError('reward UniqueIndex must stay below 65536')
    if not rewards_enabled:
        # Diagnostic builds: courses without their new reward rows.
        for row in courses:
            row['set']['RewardID'] = ''
        rewards, randoms = [], []
    tables[COLOSSEUM]['rows'] = courses
    menu = next(r for r in tables[ACTION]['rows'] if r['name'] == OPEN_MENU)
    menu['set']['IntegerArgumentList_Array'] = ['4', '1' if design['battle']['mode'] == 'simulator' else '0', '5']
    keep = [r for r in tables[REWARD]['rows'] if r['name'] == INVITATION_REWARD]
    tables[REWARD]['rows'] = keep + rewards
    out = [t for t in spec['tables'] if t['asset'] not in RETIRED and t['asset'] not in (RANDOM, POSITION)]
    # The arena's player and enemy start points, by their names in the owned battle plan (prison names, relocated).
    at = next(i for i, t in enumerate(out) if t['asset'] == COLOSSEUM)
    # Arrival spread: where the victory poses stand the team (owner request), not the
    # prison row's 150 cm line that put the two fighters almost on top of each other.
    offsets = design['battle'].get('party_offsets', [[0, 0], [150, 0], [-150, 0]])
    position = {'PlayerPosOffset_X_Array': [str(x) for x, _ in offsets],
                'PlayerPosOffset_Y_Array': [str(y) for _, y in offsets]}
    out.insert(at, {'asset': POSITION, 'rows': [{'name': 'POS_Mod_JunonColosseum', 'cloneFrom': 'POS_COL30_UNDRS_01_010', 'set': position}]})
    if randoms:
        at = next(i for i, t in enumerate(out) if t['asset'] == REWARD) + 1
        out.insert(at, {'asset': RANDOM, 'rows': randoms})
    return {'tables': out}


def generate(spec, design, round_data, buffs, rewards_enabled=True, combined_mode=None):
    """The spec and buffwheel_data.lua text for a design. combined_mode overrides
    the design's combined-round mode (repurpose, new or off)."""
    missing = {r for c in design['courses'] for slot in c['slots'] for r in slot} - set(round_data['rounds'])
    if missing:
        raise SystemExit(f'rounds missing from data/round-data.json (run tools/extract_round_data.py): {sorted(missing)}')
    # Combined rounds (tools/make_combined_rounds.py): the pools gain them, the
    # round data their enemy specs, and the spec their EnemyTerritory rows.
    if combined_mode == 'off':
        design = json.loads(json.dumps(design))
        design['combined'] = {**design.get('combined', {}), 'share': 0}
        for course in design['courses']:
            course.pop('combined_share', None)
        combined_mode = None
    design, round_data, territories, combined_lua, _ = make_combined_rounds.build(design, round_data, combined_mode)
    result = apply(spec, design, rewards_enabled=rewards_enabled)
    result['tables'] = [t for t in result['tables'] if t['asset'] not in TERRITORY_TABLES] + territories
    # Course difficulty: spec clones in the tables, the rest in Lua data.
    apply_difficulty.apply(result, design, round_data)
    # The between-round boons need only their Lua data, and Equipment rows for the
    # materia carriers the game lacks (Strength Up and others; apply_buff_wheel.py),
    # with the rank rules' carriers (Darkside's materia; apply_difficulty.rule_carriers).
    # Boss rounds per course: the offer after one favours epic infusions.
    apply_buff_wheel.add_carriers(result, buffs, apply_difficulty.rule_carriers(design))
    darkside = json.loads(DARKSIDE.read_text(encoding='utf-8'))
    buff_lua = apply_buff_wheel.lua(buffs,
                                    apply_difficulty.lua_courses(design, round_data, shipped_rounds(design)) + combined_lua
                                    + extract_darkside_abilities.lua_lines(darkside),
                                    [c.get('bosses', []) for c in design['courses']])
    return result, buff_lua


def main():
    """python tools/apply_course_design.py [--check] [--no-rewards]
        [--combined-mode repurpose|new|off] [--out <spec.json>] [--lua-out <buffwheel_data.lua>]

    --out/--lua-out write a diagnostic build's spec and Lua data beside the real
    ones (the build then needs both: Build-Foyer.ps1 -SpecPath and -LuaDataPath)."""
    spec = json.loads(SPEC.read_text(encoding='utf-8-sig'))
    design = json.loads(DESIGN.read_text(encoding='utf-8'))
    round_data = json.loads(ROUND_DATA.read_text(encoding='utf-8'))
    buffs = json.loads(BUFFS.read_text(encoding='utf-8'))
    mode = sys.argv[sys.argv.index('--combined-mode') + 1] if '--combined-mode' in sys.argv else None
    if mode not in (None, 'off', *make_combined_rounds.MODES):
        raise SystemExit(f'--combined-mode {mode}: repurpose, new or off')
    result, buff_lua = generate(spec, design, round_data, buffs, '--no-rewards' not in sys.argv, mode)
    text = json.dumps(result, indent=2, ensure_ascii=True) + '\n'
    if '--out' in sys.argv or '--lua-out' in sys.argv:  # a diagnostic build beside the real one
        if '--out' in sys.argv:
            Path(sys.argv[sys.argv.index('--out') + 1]).write_text(text, encoding='utf-8')
        if '--lua-out' in sys.argv:
            Path(sys.argv[sys.argv.index('--lua-out') + 1]).write_text(buff_lua, encoding='utf-8', newline='\n')
        return
    if '--check' in sys.argv:
        current = SPEC.read_text(encoding='utf-8-sig')
        lua_now = BUFF_LUA.read_text(encoding='utf-8') if BUFF_LUA.exists() else ''
        sys.exit(0 if current == text and lua_now == buff_lua else 1)
    SPEC.write_text(text, encoding='utf-8')
    BUFF_LUA.write_text(buff_lua, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
