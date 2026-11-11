"""Our archive carries Training Dummy's courses, shown only when that mod is installed."""
import json
import os
import sys
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'ue4ss/JunonColosseum/Scripts'
sys.path.insert(0, str(ROOT / 'tools'))
import merge_specs  # noqa: E402

FLAG = 'stfMod_JunonColosseum_TrainingDummyShown'


def run(files, vr_open=True, stored=False):
    """compat.lua against a fake Mods folder ({relative path: text})."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().files = lua.table_from({'mod/../' + k: v for k, v in files.items()})
    lua.execute('''
        package.preload.paths = function() return {mod = 'mod/'} end
        io.open = function(path) local text = files[path]
            if not text then return nil end
            return {read = function() return text end, close = function() end} end
        FName = function(s) return s end
        writes = {}
    ''')
    lua.globals().vr_open, lua.globals().stored = vr_open, stored
    compat = lua.execute((SCRIPTS / 'compat.lua').read_text())
    db = lua.execute('''return {
        IsStoryFlag = function(self, key)
            if key == 'stf1210_CHOFA_VROpen_Gras' then return vr_open end
            assert(key == '%s'); return stored end,
        SetStoryFlagBP = function(self, key, value)
            assert(key == '%s', 'only our flag'); stored = value; writes[#writes + 1] = value end}''' % (FLAG, FLAG))
    compat.tick(db)
    compat.tick(db)
    return compat.training_dummy, lua.globals().stored, len(list(lua.globals().writes.values()))


TD = 'TrainingDummy/Scripts/main.lua'


def test_courses_hidden_without_training_dummy():
    assert run({}) == (False, False, 0)
    assert run({}, stored=True) == (False, False, 1)  # uninstalled since: hide again


def test_courses_follow_mods_txt_and_enabled_txt():
    assert run({TD: '', 'mods.txt': 'Keybinds : 1\nTrainingDummy : 1\n'}) == (True, True, 1)
    assert run({TD: '', 'mods.txt': 'TrainingDummy : 0\n'})[0] is False
    assert run({TD: '', 'mods.txt': 'TrainingDummy : 0\n', 'TrainingDummy/enabled.txt': ''})[0] is True
    assert run({'mods.txt': 'TrainingDummy : 1\n'})[0] is False  # listed but not installed


def test_courses_keep_the_simulator_condition():
    assert run({TD: '', 'mods.txt': 'TrainingDummy : 1'}, vr_open=False) == (True, False, 0)


def training_dummy_spec():
    """Training Dummy's spec, if this machine names one: JUNON_TRAINING_DUMMY_SPEC, or
    TrainingDummySpec in build-config.local.json. Otherwise the test uses a stand-in row."""
    named = os.environ.get('JUNON_TRAINING_DUMMY_SPEC')
    config = ROOT / 'build-config.local.json'
    if not named and config.exists():
        named = json.loads(config.read_text(encoding='utf-8')).get('TrainingDummySpec')
    return Path(named) if named and Path(named).exists() else None


def test_merge_gates_only_training_dummy_courses():
    spec = training_dummy_spec()
    td = merge_specs.load(spec) if spec else \
        {'tables': [{'asset': merge_specs.COLOSSEUM, 'rows': [{'name': 'COL99_TrainingDummy_DPS_vr',
                     'set': {'DisplayFlagID_Array': ['stf1210_CHOFA_VROpen_Gras']}}]}]}
    own = merge_specs.load(ROOT / 'data/junon-arena.json')
    merged = merge_specs.merge(td, own, FLAG)
    rows = {r['name']: r for t in merged['tables'] if t['asset'] == merge_specs.COLOSSEUM for r in t['rows']}
    dummy = [n for n in rows if n.startswith('COL99_TrainingDummy')]
    assert dummy and all(rows[n]['set']['DisplayFlagID_Array'] == [FLAG] for n in dummy)
    assert all(FLAG not in json.dumps(rows[n]) for n in rows if n.startswith('COL30_JUNON'))
    # The original spec is untouched (copied before gating).
    assert all(FLAG not in json.dumps(t) for t in td['tables'])
