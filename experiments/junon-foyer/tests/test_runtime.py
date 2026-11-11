import json
from pathlib import Path
from lua_stubs import PATHS_STUB

from lupa import LuaRuntime


def test_runtime_switches_saves_without_touching_vanilla_flags():
    scripts = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts'
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PATHS_STUB)
    lua.globals().gate_module = lua.execute((scripts / 'gate.lua').read_text())
    lua.execute('''
        own = 'stfMod_JunonColosseum_RocheDefeated'
        access_key = 'stfMod_JunonColosseum_AccessEnabled'
        access_stored = false
        guard_stored, exit_stored, discovered, item_count = false, false, true, 1
        needs_stored=false
        loaded, visited, cleared, stored = false, false, false, false
        battle, battle_queries, hidden = false, 0, 0
        progress = 2140
        writes = {}
        local valid = function() return true end
        local pawn = {IsValid=valid, GetClass=function() return {
            GetFName=function() return {ToString=function() return 'PC0000_Cloud_C' end} end
        } end, GetFullName=function() return 'Cloud' end}
        package.preload.UEHelpers = function() return {
            GetPlayer=function() if loaded then return pawn end end
        } end
        package.preload.gate = function() return gate_module end
        package.preload.foyer = function() return {tick=function() end, hide_for_battle=function() hidden=hidden+1 end} end
        package.preload.invitation = function() return {tick=function() end} end
        package.preload.flow = function() return {tick=function() end} end
        package.preload.buffwheel = function() return {tick=function() end} end
        package.preload.devtools = function() return {tick=function() end} end
        package.preload.branding = function() return {tick=function() end, register=function() end} end
        package.preload.compat = function() return {tick=function() end} end
        FName = function(s) return s end
        local db = {IsValid=valid, GetChapterProgress=function() return progress end,
            GetItemNumBP=function() return item_count end,
            IsStoryFlag=function(self, key)
                if key == own then return stored end
                if key == access_key then return access_stored end
                if key == 'stfMod_JunonColosseum_Discovered' then return discovered end
                if key == 'stfMod_JunonColosseum_GuardEnabled' then return guard_stored end
                if key == 'stfMod_JunonColosseum_ExitEnabled' then return exit_stored end
                if key == 'stfMod_JunonColosseum_NeedsInvitation' then return needs_stored end
                if key == 'stfCmnChapter12_Visited' then return visited end
                assert(key == 'stfComn_Release_ChapterSelect')
                return cleared
            end,
            SetStoryFlagBP=function(self,key,value)
                assert(key == own or key == access_key or key == 'stfMod_JunonColosseum_GuardEnabled' or key == 'stfMod_JunonColosseum_ExitEnabled' or key == 'stfMod_JunonColosseum_NeedsInvitation', 'vanilla flag must never be changed')
                writes[#writes+1]={key,value}
                if key == own then stored=value elseif key == access_key then access_stored=value elseif key == 'stfMod_JunonColosseum_ExitEnabled' then exit_stored=value elseif key == 'stfMod_JunonColosseum_NeedsInvitation' then needs_stored=value else guard_stored=value end
            end}
        StaticFindObject=function(path)
            if path == '/Script/EndGame.Default__EndDataBaseAPI' then return db end
            if path == '/Script/EndGame.Default__EndFieldAPI' then return {IsValid=valid,
                IsDuringBattle=function() battle_queries=battle_queries+1;return battle end} end
            return {IsValid=valid}
        end
        ExecuteInGameThread=function(f) f() end
        LoopAsync=function(ms,f) tick=f end
        io.open=function() return {
            write=function(self,s) receipt=s end, close=function() end
        } end
        os.remove=function() end
        os.rename=function() end
    ''')
    lua.execute((scripts / 'main.lua').read_text())
    tick = lua.globals().tick
    tick()
    assert len(lua.globals().writes) == 0
    assert json.loads(lua.globals().receipt)['verified'] is False
    assert lua.globals().battle_queries == 0  # no battle API at title/no first pawn
    lua.execute('loaded=true; visited=false; cleared=true; progress=12980')
    tick()
    assert json.loads(lua.globals().receipt)['enabled'] is True
    tick()
    assert len(lua.globals().writes) == 4  # history, access, guard and exit; no repeated stable writes
    lua.execute('visited=false; cleared=false; stored=true; progress=2140')  # stale flag on next loaded save
    tick()
    assert json.loads(lua.globals().receipt)['enabled'] is False
    assert len(lua.globals().writes) == 8
    lua.execute('progress=12000; visited=false; cleared=false')
    tick()
    assert json.loads(lua.globals().receipt)['enabled'] is True
    lua.execute('progress=4500; cleared=true')  # replay Junon after beating Roche
    tick()
    receipt = json.loads(lua.globals().receipt)
    assert receipt['enabled'] is False
    assert receipt['roche_defeated'] is True
    assert receipt['chapter4_replay'] is True
    assert lua.globals().stored is True  # invitation eligibility remains earned
    lua.execute('progress=12000')
    tick()
    assert json.loads(lua.globals().receipt)['enabled'] is True
    lua.execute('item_count=0')
    tick()
    assert json.loads(lua.globals().receipt)['invitation_needed'] is True
    assert lua.globals().guard_stored is False
    lua.execute('item_count=1')
    tick()
    assert json.loads(lua.globals().receipt)['invitation_needed'] is False
    assert lua.globals().guard_stored is True
    before = len(lua.globals().writes)
    lua.execute('loaded=false; battle=true')
    tick()
    assert lua.globals().hidden == 1  # battle unpossesses the field pawn
    assert len(lua.globals().writes) == before
    assert json.loads(lua.globals().receipt)['reason'] == 'battle_field_gate_writes_suspended'
