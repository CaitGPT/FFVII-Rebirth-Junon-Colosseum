import json
from pathlib import Path


def test_flow_triggers_reach_resident_controller_and_use_matching_registration():
    spec = json.loads((Path(__file__).resolve().parents[1] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    tables = {t['asset']: {r['name']: r for r in t['rows']} for t in spec['tables']}
    registered = tables['DataObject/Resident/ResidentStateTrigger.uasset']
    triggers = tables['DataObject/Resident/StateTrigger.uasset']
    assert len(registered) == 10
    for name, row in registered.items():
        # EndFieldStateTriggerScope: 0 Self, 1 Location, 2 ResidentAndLocation.
        # Location-only broadcasts cannot reach our resident Object controller.
        assert triggers[name]['set']['Target'] == '2'
        assert 'Target' not in row['set']  # registration table has no scope field
        assert row['set']['UniqueIndex'] == triggers[name]['set']['UniqueIndex']
    controller = 'objMod_JunonColosseum_Flow'
    obj = tables['DataObject/Resident/Object.uasset'][controller]['set']
    resident = tables['DataObject/Resident/ResidentObject.uasset'][controller]['set']
    assert obj['UniqueIndex'] == resident['UniqueIndex']
    states = tables['DataObject/Resident/StateChange.uasset']
    assert obj['StartStateChange'] in states
    for row in states.values():
        fields = row['set']
        assert len(fields['NextStateChange_Array']) == len(fields['StateTriggerList_Array'])
        assert set(fields['NextStateChange_Array']) <= states.keys()
        # trgCmn_OnWaitAction_Self is the game's own resident-registered wait trigger.
        assert set(fields['StateTriggerList_Array']) <= registered.keys() | {'trgCmn_OnWaitAction_Self'}
    state_index = tables['DataObject/Resident/ResidentStateChange.uasset']
    assert controller in tables['DataObject/Resident/ObjectEntryAttributeList.uasset']
    for asset, rows in tables.items():
        if asset.endswith('/StateChange.uasset'):
            for name, row in rows.items():
                if name.startswith('scgMod_'):
                    assert state_index[name]['set']['UniqueIndex'] == row['set']['UniqueIndex']


def test_both_owner_selected_guards_keep_vanilla_talk_unless_membership_is_enabled():
    spec = json.loads((Path(__file__).resolve().parents[1] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    tables = {t['asset']: {r['name']: r for r in t['rows']} for t in spec['tables']}
    rows = tables['DataObject/Field/1300-JUNOA/StateChange.uasset']
    for guard in (1, 2):
        original = f'scg1300_Gate_Soldier{guard:02}_TI_Stay_Talk'
        fields = rows[original]['set']
        assert set(fields) == {'SwapStateCondition_Array', 'SwapStateConditionNot_Array', 'SwapStateChange_Array'}
        assert fields['SwapStateCondition_Array'] == ['stfMod_JunonColosseum_GuardEnabled', 'stfMod_JunonColosseum_NeedsInvitation']
        assert fields['SwapStateConditionNot_Array'] == ['', '']
        request = rows[fields['SwapStateChange_Array'][0]]
        assert request['cloneFrom'] == original
        assert request['set']['EnterActionList_Array'] == ['actMod_JunonColosseum_AskGuard']
        assert request['set']['SwapStateCondition_Array'] == []
        assert request['set']['SwapStateChange_Array'] == []
        assert request['set']['StateTriggerList_Array'] == ['trgMod_JunonFlow_EntryYes', 'trgMod_JunonFlow_DialogueDone']
        entering = rows[request['set']['NextStateChange_Array'][0]]['set']
        assert entering['EnterActionList_Array'] == ['acgMod_JunonColosseum_Enter']
        assert entering['SwapStateChange_Array'] == []
        assert entering['NextStateChange_Array'] == [f'scg1300_Gate_Soldier{guard:02}_TI_Stay']
        grant = rows[fields['SwapStateChange_Array'][1]]['set']
        assert grant['EnterActionList_Array'] == ['actMod_JunonColosseum_GrantInvitation']
        wait_name = grant['NextStateChange_Array'][0]
        wait = rows[wait_name]['set']
        assert wait['EnterActionList_Array'] == ['actCmn_Wait0point5s']
        assert wait['StateTriggerList_Array'] == ['trgCmn_OnWaitAction_Self']
        assert wait['NextStateChange_Array'] == [wait_name]
        assert wait['SwapStateChange_Array'] == [fields['SwapStateChange_Array'][0], f'scg1300_Gate_Soldier{guard:02}_TI_Stay']
    assert 'DataObject/Field/1300-JUNOA/Action.uasset' not in tables  # original conversations unchanged


def test_native_condition_negation_uses_operators_not_boolean_numbers():
    spec = json.loads((Path(__file__).resolve().parents[1] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    for table in spec['tables']:
        for row in table['rows']:
            fields = row['set']
            for prefix in ('StartStateCondition', 'SwapStateCondition'):
                conditions = fields.get(prefix + '_Array')
                markers = fields.get(prefix + 'Not_Array')
                if conditions is not None and markers is not None:
                    assert len(markers) == len(conditions), row['name']
                    assert set(markers) <= {'', '!'}, row['name']


def test_choice_scenes_preserve_native_sparse_slots_and_branch_handoff():
    spec = json.loads((Path(__file__).resolve().parents[1] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    rows = {r['name']: r for t in spec['tables'] if t['asset'] == 'DataObject/Resident/PlannerEvent.uasset' for r in t['rows']}
    for kind in ('Guard', 'Exit'):
        root = f'PV_Mod_JunonColosseum_{kind}'
        assert rows[root]['cloneFrom'] == 'PV_MGCAP_1010'
        assert rows[root]['set']['NextPE'] == root + '_0010'
        args = rows[root + '_0010']['set']['CommandArgumentList_Array']
        assert len(args) == 18
        assert args[5] == root + '_0020' and args[17] == root + '_0040'
        assert [i for i, value in enumerate(args) if value] == [4, 5, 16, 17]
        assert rows[root + '_0020']['set']['NextPE'] == root + '_0030'
        assert rows[root + '_0040']['set']['NextPE'] == root + '_0050'
        assert rows[root + '_0050']['set']['CommandArgumentList_Array'] == ['trgMod_JunonFlow_DialogueDone']


def test_location_jump_preserves_native_destination_slot():
    # Binary inspection of native act1350_LocationJump_0005: destination is
    # StringArgument[6], not [1]. CSV display collapses the empty slots.
    spec = json.loads((Path(__file__).resolve().parents[1] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    rows = {r['name']: r for t in spec['tables'] if t['asset'] == 'DataObject/Resident/Action.uasset' for r in t['rows']}
    for action, target in (('Enter', 'Arrival'), ('Leave', 'ReturnGate')):
        fields = rows[f'actMod_JunonColosseum_{action}']['set']
        assert fields['Type'] == '17'
        # Native title/world-map jumps use the world root. 1300/1350 are
        # nested locations with BaseLocation=1000-EASTC, not standalone maps.
        location = '0001-WORLD'
        assert fields['StringArgumentList_Array'] == [location, '', '', '', '', '', f'tgpMod_JunonColosseum_{target}']
        assert fields['IntegerArgumentList_Array'] == ['0'] * 15 + ['2']


def test_guard_grants_the_invitation_on_arrival():
    """Owner 2026-11-10: a save past Roche gets the Invitation without a Talk. Guard 1's
    idle state grants it while the mod asks; the resident flow never polls (that crashed
    the game on load, 2026-11-10)."""
    spec = json.loads((Path(__file__).resolve().parents[1] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    tables = {t['asset']: {r['name']: r for r in t['rows']} for t in spec['tables']}
    flow = tables['DataObject/Resident/StateChange.uasset']['scgMod_JunonFlow_Wait']['set']
    assert flow['EnterActionList_Array'] == [] and 'SwapStateCondition_Array' not in flow
    field = tables['DataObject/Field/1300-JUNOA/StateChange.uasset']
    idle = field['scg1300_Gate_Soldier01_TI_Stay']['set']
    assert set(idle) == {'SwapStateCondition_Array', 'SwapStateConditionNot_Array', 'SwapStateChange_Array'}
    assert idle['SwapStateCondition_Array'] == ['stfMod_JunonColosseum_NeedsInvitation']
    grant = field[idle['SwapStateChange_Array'][0]]['set']
    assert grant['EnterActionList_Array'] == ['actMod_JunonColosseum_GrantInvitation']
    after = field[grant['NextStateChange_Array'][0]]['set']
    assert after['SwapStateConditionNot_Array'] == ['!'] and after['SwapStateChange_Array'] == ['scg1300_Gate_Soldier01_TI_Stay']
    assert 'scg1300_Gate_Soldier02_TI_Stay' not in field  # one guard grants, never two copies
    registered = tables['DataObject/Resident/ResidentStateChange.uasset']
    for name in (idle['SwapStateChange_Array'][0], grant['NextStateChange_Array'][0]):
        assert registered[name]['set']['UniqueIndex'] == field[name]['set']['UniqueIndex']
    action = tables['DataObject/Resident/Action.uasset']['actMod_JunonColosseum_GrantInvitation']['set']
    assert action['StartStateCondition_Array'] == ['stfMod_JunonColosseum_RocheDefeated']
    specs = tables['DataObject/Resident/BattleCharaSpec.uasset']
    for phase in ('EN0007_02_Soldier3rd_LoccheSEnd2', 'EN0007_02_Soldier3rd_LoccheSEnd2_Worse'):
        assert specs[phase]['set']['PossessionItemID'] == 'modJunon_Chapter11Roche_Drops'
    assert not any(name.startswith('EN0007_01') for name in specs)  # Chapter 4's Roche is untouched
