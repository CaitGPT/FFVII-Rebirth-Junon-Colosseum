from pathlib import Path
from lua_stubs import PATHS_STUB

from lupa import LuaRuntime


def test_guard_request_requires_eligible_observed_arrival_before_discovery():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PATHS_STUB)
    lua.execute('''
        now=0; pending=false; discovered=false; writes={}; grounded=true
        pos={X=-80626,Y=79712,Z=2706}
        FName=function(s) return s end
        os.time=function() return now end
        os.remove=function() end; os.rename=function() end
        io.open=function() return {write=function(self,s) receipt=s end,close=function() end} end
        db={IsStoryFlag=function(self,k)
            if k=='stfMod_JunonColosseum_EntryPending' then return pending end
            assert(k=='stfMod_JunonColosseum_Discovered');return discovered
        end,SetStoryFlagBP=function(self,k,v)
            writes[#writes+1]={k,v}
            if k=='stfMod_JunonColosseum_EntryPending' then pending=v
            else assert(k=='stfMod_JunonColosseum_Discovered');discovered=v end
        end}
        movement={IsValid=function() return true end,IsMovingOnGround=function() return grounded end}
        pawn={K2_GetActorLocation=function() return pos end,
            GetMovementComponent=function() return movement end,
            GetVelocity=function() return {X=0,Y=0,Z=0} end,
            K2_GetActorRotation=function() return {Yaw=-127.451088} end}
    ''')
    script = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts/flow.lua'
    flow = lua.execute(script.read_text())
    g = lua.globals()
    flow.tick(g.db, g.pawn, 12000, 1)
    assert not g.discovered and len(g.writes) == 0
    lua.execute('pending=true')
    flow.tick(g.db, g.pawn, 12000, 1)
    assert not g.discovered and g.pending  # requesting a warp proves nothing
    lua.execute('now=121')
    flow.tick(g.db, g.pawn, 12000, 1)
    assert not g.discovered and not g.pending
    lua.execute('pending=true; pos={X=-122488.4375,Y=32968.976562,Z=6257.788574}')
    flow.tick(g.db, g.pawn, 4500, 1)
    assert not g.discovered and not g.pending  # old Invitation does not bypass replay gate
    lua.execute('pending=true')
    flow.tick(g.db, g.pawn, 12000, 0)
    assert not g.discovered and not g.pending
    lua.execute('pending=true; pos.Z=7000')
    flow.tick(g.db, g.pawn, 12000, 1)
    assert not g.discovered and g.pending  # matching X/Y on another floor is insufficient
    lua.execute('pos.Z=6257.788574')
    lua.execute('grounded=false')
    for _ in range(4):
        flow.tick(g.db, g.pawn, 12000, 1)
    assert not g.discovered and g.pending  # S reached coordinates in an unloaded void
    lua.execute('grounded=true')
    for _ in range(2):
        flow.tick(g.db, g.pawn, 12000, 1)
    assert not g.discovered and g.pending  # require three settled samples
    flow.tick(g.db, g.pawn, 12000, 1)
    assert g.discovered and not g.pending
