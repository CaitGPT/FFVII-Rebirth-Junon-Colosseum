"""battle_plan.lua asks the native helper for Junon town's battle navigation
(ServerBuild first), then our arena's ServerBuild level and plan, each only
once the one before is loaded and visible."""
from pathlib import Path

from lupa import LuaRuntime

NAV = 'ModJunonColosseum_LoadJunonBtlNav'
ORDER = [NAV + 'ServerBuild', NAV, 'ModJunonColosseum_LoadOwnedServerBuild', 'ModJunonColosseum_LoadOwnedPlan']


def fixture():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        requests={}
        changes=0
        refuse={}
        world_id=77
        valid=function() return true end
        world={IsValid=valid,GetAddress=function() return world_id end}
        pawn={IsValid=valid,GetWorld=function() return world end}
        local function make(path)
            local s={IsValid=valid,loaded=false,visible=false,exists=false}
            s.GetLoadedLevel=function(self) if self.loaded then return world end end
            s.IsLevelLoaded=function(self) return self.loaded end
            s.IsLevelVisible=function(self) return self.visible end
            s.GetWorldAssetPackageFName=function() return {ToString=function() return path end} end
            s.SetShouldBeVisible=function(self,on) changes=changes+1;self.visible=on end
            s.SetShouldBeLoaded=function(self,on) changes=changes+1;self.loaded=on end
            return s
        end
        local nav='/Game/Level/Game/Field/1350-JNONT/Layout/1350-JNONT_Btl_Navigation_Mod'
        local owned='/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum'
        navserver=make(nav..'_ServerBuild'); navmain=make(nav)
        server=make(owned..'_ServerBuild'); plan=make(owned)
        all={navserver,navmain,server,plan}
        local by_tag={
            ModJunonColosseum_LoadJunonBtlNavServerBuild={navserver,'ModJunonBtlNavServerBuildAccepted_'},
            ModJunonColosseum_LoadJunonBtlNav={navmain,'ModJunonBtlNavAccepted_'},
            ModJunonColosseum_LoadOwnedServerBuild={server,'ModJunonServerBuildAccepted_'},
            ModJunonColosseum_LoadOwnedPlan={plan,'ModJunonPlanAccepted_'},
        }
        function ready(s) s.loaded=true;s.visible=true end
        FName=function(s) return s end
        world.SpawnActor=function(self,klass,pos,rot)
            assert(pos.X==-122488 and pos.Y==32969 and pos.Z==6170)
            local marker={IsValid=valid,SetActorEnableCollision=function() end,K2_DestroyActor=function() end,name='StaticMeshActor_1'}
            marker.SetActorTickEnabled=function(self,on)
                assert(on==false)
                local tag=self.Tags[1]
                requests[#requests+1]=tag
                if refuse[tag] then return end
                local entry=by_tag[tag]
                entry[1].exists=true;self.name=entry[2]..self.name
            end
            marker.GetFName=function(self) return {ToString=function() return self.name end} end
            return marker
        end
        StaticFindObject=function(path) assert(path=='/Script/Engine.StaticMeshActor');return world end
        FindAllOf=function(class) assert(class=='LevelStreamingDynamic')
            local out={}
            for _,s in ipairs(all) do if s.exists then out[#out+1]=s end end
            return out
        end
    ''')
    script = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts/battle_plan.lua'
    module = lua.execute(script.read_text())
    module.SETTLE = 0  # these tests are about order; the wait after a load has its own test
    module.QUIET = 0
    return lua, module


def tags(g):
    return [g.requests[i + 1] for i in range(len(g.requests))]


def test_each_level_is_requested_only_after_the_one_before_is_visible():
    lua, module = fixture()
    g = lua.globals()
    assert module.update(None, True, False)[0] is False
    assert module.update(g.pawn, False, False)[0] is False
    assert tags(g) == []
    states = ['loading_navigation_serverbuild', 'loading_navigation', 'loading_serverbuild', 'loading']
    for step, name in enumerate(['navserver', 'navmain', 'server', 'plan']):
        assert module.update(g.pawn, True, False) == (False, states[step])
        assert module.update(g.pawn, True, False) == (False, states[step])
        assert tags(g) == ORDER[:step + 1]  # nothing more until this one is visible
        lua.execute(f'ready({name})')
    assert module.update(g.pawn, True, False) == (True, 'loaded_visible')
    assert tags(g) == ORDER


def test_battle_keeps_every_level_and_leaving_unloads_them_all():
    lua, module = fixture()
    g = lua.globals()
    lua.execute('for _,s in ipairs(all) do ready(s) end')
    for _ in range(4):
        module.update(g.pawn, True, False)
    assert module.update(g.pawn, True, False) == (True, 'loaded_visible')
    lua.execute('changes=0')
    module.update(None, False, True)
    module.update(g.pawn, False, True)
    assert g.changes == 0  # battle unpossesses the pawn: do not unload the arena
    module.update(g.pawn, False, False)
    assert g.changes == 8  # leaving unloads all four
    lua.execute('for _,s in ipairs(all) do ready(s) end')
    assert module.update(g.pawn, True, False) == (True, 'loaded_visible')
    assert len(tags(g)) == 4  # the same streaming objects are reused on return
    lua.execute('world_id=78;for _,s in ipairs(all) do s.loaded=false;s.visible=false end')
    assert module.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    assert len(tags(g)) == 5  # another world makes its own requests


def test_return_reactivates_in_order():
    lua, module = fixture()
    g = lua.globals()
    lua.execute('for _,s in ipairs(all) do ready(s) end')
    for _ in range(4):
        module.update(g.pawn, True, False)
    module.update(g.pawn, False, False)
    lua.execute('changes=0;navserver.SetShouldBeVisible=function(self,on) changes=changes+1 end')  # stays hidden
    assert module.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    assert g.changes == 2 and g.plan.loaded is False  # only the first level was reactivated


def test_a_refused_level_is_not_repeated_and_nothing_after_it_is_asked():
    lua, module = fixture()
    lua.execute(f"refuse['{NAV}']=true;ready(navserver)")
    g = lua.globals()
    module.update(g.pawn, True, False)
    assert module.update(g.pawn, True, False) == (False, 'load_error')
    assert '1350-JNONT_Btl_Navigation_Mod' in module.error()
    for _ in range(5):
        assert module.update(g.pawn, True, False) == (False, 'load_error')
    assert tags(g) == ORDER[:2]


def test_nothing_is_requested_until_a_new_world_has_settled():
    """Live 2026-11-10: requests during a save's streaming crashed the async loader."""
    lua, plan = fixture()
    plan.SETTLE = 8
    plan.QUIET = 0
    lua.execute('clock = 1000; os.time = function() return clock end')
    g = lua.globals()
    ok, state = plan.update(g.pawn, True, False)
    assert not ok and state.startswith('settling_after_load') and len(tags(g)) == 0
    lua.execute('clock = 1007')
    assert plan.update(g.pawn, True, False)[1].startswith('settling_after_load') and len(tags(g)) == 0
    lua.execute('clock = 1008')
    plan.update(g.pawn, True, False)
    assert len(tags(g)) == 1  # the first level, once settled


def test_deleted_streams_are_requested_again():
    """Live 2026-11-10: after leaving and returning through the guard, the game had
    deleted our streaming objects in the same world, and the board never came back."""
    lua, plan = fixture()
    g = lua.globals()
    lua.execute('for _,s in ipairs(all) do ready(s) end')
    assert plan.update(g.pawn, True, False)[1] == 'loaded_visible'
    asked = len(tags(g))
    lua.execute('for _,s in ipairs(all) do s.IsValid=function() return false end end')
    plan.update(g.pawn, True, False)
    assert len(tags(g)) == asked + 1  # the first level is asked for again


def test_quiet_means_nothing_pending_for_six_seconds():
    """Live 2026-11-10 evening: a pending set that merely stopped changing let a request
    out while a big level still streamed (crash A). Never-done levels are ignored."""
    lua, plan = fixture()
    plan.SETTLE = 0
    plan.QUIET = 6
    plan.STUCK = 20
    lua.execute("""
        clock = 1000; os.time = function() return clock end
        streaming = {}
        local function lvl(name) return {IsValid=function() return true end,
            IsStreamingStatePending=function(self) return self.pending end, pending=true,
            GetWorldAssetPackageFName=function() return {ToString=function() return name end} end} end
        big = lvl('/Game/Level/Game/Field/1300-JUNOA/Big')
        strip = lvl('/Game/Level/Game/Field/1350-JNONT/1350-JNONT_Airport_Terrain_Strip')
        streaming = {big, strip}
        local plain = FindAllOf
        FindAllOf = function(class) if class == 'LevelStreaming' then return streaming end return plain(class) end
    """)
    g = lua.globals()
    for c in (1000, 1003, 1006, 1009):        # big keeps streaming: not quiet, though unchanged
        lua.execute(f'clock = {c}')
        assert plan.update(g.pawn, True, False)[1].startswith('settling_after_load') and len(tags(g)) == 0
    lua.execute('big.pending = false; clock = 1012')   # only the never-done strip is left
    assert plan.update(g.pawn, True, False)[1].startswith('settling_after_load')
    lua.execute('clock = 1015'); plan.update(g.pawn, True, False)
    assert len(tags(g)) == 0
    lua.execute('clock = 1018'); plan.update(g.pawn, True, False)
    assert len(tags(g)) == 1                  # six quiet seconds


def test_a_level_that_never_finishes_waits_for_stuck():
    lua, plan = fixture()
    plan.SETTLE = 0
    plan.QUIET = 6
    plan.STUCK = 20
    lua.execute("""
        clock = 1000; os.time = function() return clock end
        local s = {IsValid=function() return true end, IsStreamingStatePending=function() return true end,
            GetWorldAssetPackageFName=function() return {ToString=function() return '/Game/Other/Forever' end} end}
        local plain = FindAllOf
        FindAllOf = function(class) if class == 'LevelStreaming' then return {s} end return plain(class) end
    """)
    g = lua.globals()
    for c in range(1000, 1019, 3):
        lua.execute(f'clock = {c}'); plan.update(g.pawn, True, False)
    assert len(tags(g)) == 0
    lua.execute('clock = 1021'); plan.update(g.pawn, True, False)
    assert len(tags(g)) == 1


def test_a_level_the_game_already_loaded_is_borrowed_not_requested_or_unloaded():
    """Live 2026-11-10 evening: the game had streamed Junon's battle navigation itself;
    a second LoadLevelInstance returned nothing and the board never came."""
    lua, plan = fixture()
    g = lua.globals()
    lua.execute('navserver.exists = true; ready(navserver)')
    plan.update(g.pawn, True, False)
    assert 'ModJunonColosseum_LoadJunonBtlNavServerBuild' not in tags(g)
    assert tags(g)[0] == 'ModJunonColosseum_LoadJunonBtlNav'
    lua.execute('ready(navmain)')
    plan.update(g.pawn, True, False)
    plan.update(g.pawn, False, False)            # leaving: ours unloaded, the borrowed one kept
    assert lua.eval('navserver.loaded') is True and lua.eval('navmain.loaded') is False


def test_a_deferred_request_is_asked_again_not_failed():
    """Load crash A (2026-11-10): off the game thread the helper defers; Lua retries."""
    lua, plan = fixture()
    g = lua.globals()
    lua.execute("""
        defer_next = 2
        local spawn = world.SpawnActor
        world.SpawnActor = function(self, ...)
            local m = spawn(self, ...)
            local set = m.SetActorTickEnabled
            m.SetActorTickEnabled = function(mm, on)
                if defer_next > 0 then defer_next = defer_next - 1; mm.name = 'ModJunonDeferred_' .. mm.name; return end
                return set(mm, on)
            end
            return m
        end
    """)
    ok, state = plan.update(g.pawn, True, False)
    assert not ok and state == 'deferred_off_game_thread' and len(tags(g)) == 0
    plan.update(g.pawn, True, False)
    plan.update(g.pawn, True, False)
    assert tags(g)[0] == 'ModJunonColosseum_LoadJunonBtlNavServerBuild'
    assert plan.error() == ''


QUEUE = """
    clock = 1000; os.time = function() return clock end
    queue_next = 1
    queued_markers = {}
    local spawn = world.SpawnActor
    world.SpawnActor = function(self, ...)
        local m = spawn(self, ...)
        local set = m.SetActorTickEnabled
        m.destroyed = false
        m.K2_DestroyActor = function(mm) mm.destroyed = true end
        m.IsValid = function(mm) return not mm.gone end
        m.SetActorTickEnabled = function(mm, on)
            if queue_next > 0 then
                queue_next = queue_next - 1
                requests[#requests + 1] = mm.Tags[1]
                mm.original = mm.name; mm.name = 'ModJunonQueued_' .. mm.name
                queued_markers[#queued_markers + 1] = mm
                return
            end
            return set(mm, on)
        end
        return m
    end
"""


def queue_fixture():
    lua, plan = fixture()
    lua.execute(QUEUE)
    lua.execute("""
        local by_ack = {
            ModJunonColosseum_LoadJunonBtlNavServerBuild = {navserver, 'ModJunonBtlNavServerBuildAccepted_'},
            ModJunonColosseum_LoadJunonBtlNav = {navmain, 'ModJunonBtlNavAccepted_'},
        }
        function serve(m, refuse)
            if refuse then m.name = 'ModJunonRefused_' .. m.original; return end
            local entry = by_ack[m.Tags[1]]
            entry[1].exists = true
            m.name = entry[2] .. m.original
        end
    """)
    return lua, plan


def test_a_queued_request_is_collected_on_a_later_tick_without_asking_again():
    """2026-11-10: off the game thread the helper queues the load for its next
    game-thread call instead of deferring; Lua keeps the marker and waits."""
    lua, plan = queue_fixture()
    g = lua.globals()
    assert plan.update(g.pawn, True, False) == (False, 'queued_for_game_thread')
    assert tags(g) == ORDER[:1]
    marker = g.queued_markers[1]
    assert marker.destroyed is False  # kept for the helper's answer
    lua.execute('clock = 1001')
    assert plan.update(g.pawn, True, False) == (False, 'queued_for_game_thread')
    assert tags(g) == ORDER[:1]  # still waiting, not asked again
    lua.execute('serve(queued_markers[1])')
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    assert marker.destroyed is True and tags(g) == ORDER[:1]
    lua.execute('ready(navserver)')
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation')  # next level, synchronous
    assert tags(g) == ORDER[:2]
    assert plan.error() == ''


def test_a_queued_request_that_times_out_is_untagged_and_asked_again():
    lua, plan = queue_fixture()
    g = lua.globals()
    plan.update(g.pawn, True, False)
    marker = g.queued_markers[1]
    timeout = plan.QUEUE_TIMEOUT
    lua.execute(f'clock = {1000 + timeout - 1}')
    assert plan.update(g.pawn, True, False) == (False, 'queued_for_game_thread')
    lua.execute(f'clock = {1000 + timeout}')
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    # untagged before destroying, so a late helper call cannot serve it
    assert marker.destroyed is True and len(lua.eval('queued_markers[1].Tags')) == 0
    assert tags(g) == ORDER[:1] * 2  # asked again (synchronously this time)
    assert plan.error() == ''


def test_a_queued_marker_that_vanished_is_asked_again():
    lua, plan = queue_fixture()
    g = lua.globals()
    lua.execute('queue_next = 2')
    plan.update(g.pawn, True, False)
    lua.execute('queued_markers[1].gone = true')
    assert plan.update(g.pawn, True, False) == (False, 'queued_for_game_thread')
    assert tags(g) == ORDER[:1] * 2 and len(g.queued_markers) == 2
    lua.execute('serve(queued_markers[2])')
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')


def test_a_queued_request_the_helper_refused_fails_once():
    lua, plan = queue_fixture()
    g = lua.globals()
    plan.update(g.pawn, True, False)
    lua.execute('serve(queued_markers[1], true)')
    assert plan.update(g.pawn, True, False) == (False, 'load_error')
    assert 'Navigation_Mod_ServerBuild' in plan.error()
    assert g.queued_markers[1].destroyed is True
    for _ in range(3):
        assert plan.update(g.pawn, True, False) == (False, 'load_error')
    assert tags(g) == ORDER[:1]


def test_a_queued_request_the_helper_deferred_is_asked_again_not_failed():
    """2026-11-10 (0.9.13): the helper serves a queued request only at a safe
    point and answers ModJunonDeferred_ when none came within 3 s."""
    lua, plan = queue_fixture()
    g = lua.globals()
    plan.update(g.pawn, True, False)
    marker = g.queued_markers[1]
    lua.execute("queued_markers[1].name = 'ModJunonDeferred_' .. queued_markers[1].original")
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    assert marker.destroyed is True
    assert tags(g) == ORDER[:1] * 2  # asked again at once (synchronously here)
    assert plan.queue_deferred == 1 and plan.error() == ''


def test_queue_timeout_is_longer_than_the_helpers_own_answer():
    """Lua's give-up must not race a late serve: the helper never serves after 3 s."""
    lua, plan = fixture()
    assert plan.QUEUE_TIMEOUT > 3


STUCK = """
    clock = 1000; os.time = function() return clock end
    -- a second ServerBuild stream for the request made after the first got stuck
    local owned = '/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum'
    server2 = {IsValid=function() return true end, loaded=false, visible=false, exists=false}
    for k, v in pairs(server) do if type(v) == 'function' then server2[k] = v end end
    server.IsStreamingStatePending = function() return true end
    local set = world.SpawnActor
    second = false
    world.SpawnActor = function(self, ...)
        local m = set(self, ...)
        local enable = m.SetActorTickEnabled
        m.SetActorTickEnabled = function(mm, on)
            if mm.Tags[1] == 'ModJunonColosseum_LoadOwnedServerBuild' and second then
                requests[#requests + 1] = mm.Tags[1]
                server2.exists = true
                mm.name = 'ModJunonServerBuildAccepted_' .. mm.name
                return
            end
            if mm.Tags[1] == 'ModJunonColosseum_LoadOwnedServerBuild' then second = true end
            return enable(mm, on)
        end
        return m
    end
    table.insert(all, 4, server2)  -- after the stuck one: only the stale mark skips it
"""


def stuck_fixture():
    lua, plan = fixture()
    lua.execute(STUCK)
    g = lua.globals()
    lua.execute('ready(navserver); ready(navmain)')
    for _ in range(3):
        plan.update(g.pawn, True, False)
    assert tags(g) == ORDER[:3]
    return lua, plan, g


def test_a_stream_stuck_pending_is_unloaded_and_requested_once_more():
    """Live 2026-11-10 20:55: our ServerBuild stream stayed pending for minutes
    and the board never came. After STREAM_STUCK seconds it is unloaded and
    requested again; the new stream is used, never the stuck one."""
    lua, plan, g = stuck_fixture()
    stuck = plan.STREAM_STUCK
    lua.execute(f'clock = {1000 + stuck}')
    assert plan.update(g.pawn, True, False) == (False, 'loading_serverbuild')  # not yet
    lua.execute(f'clock = {1000 + stuck + 1}')
    assert plan.update(g.pawn, True, False) == (False, 'stream_stuck_requesting_again')
    assert g.server.loaded is False and g.server.visible is False  # unloaded
    assert plan.stuck_retries == 1 and 'pending=true' in plan.last_event
    assert plan.update(g.pawn, True, False) == (False, 'loading_serverbuild')
    assert tags(g) == ORDER[:3] + ORDER[2:3]  # requested once more
    lua.execute('ready(server2)')
    assert plan.update(g.pawn, True, False) == (False, 'loading')  # the new stream counts
    assert g.server.loaded is False  # the stuck one is left unloaded
    assert plan.error() == ''


def test_a_stream_stuck_again_fails_instead_of_waiting_forever():
    lua, plan, g = stuck_fixture()
    stuck = plan.STREAM_STUCK
    lua.execute(f'clock = {1000 + stuck + 1}')
    plan.update(g.pawn, True, False)
    plan.update(g.pawn, True, False)            # second request at clock 1021
    lua.execute(f'clock = {1000 + 2 * stuck + 3}')
    assert plan.update(g.pawn, True, False) == (False, 'load_error')
    assert 'stayed pending' in plan.error()
    assert len(tags(g)) == 4  # no third request
    for _ in range(3):
        assert plan.update(g.pawn, True, False) == (False, 'load_error')
    assert len(tags(g)) == 4


def test_a_stream_that_loads_in_time_is_not_touched():
    lua, plan, g = stuck_fixture()
    lua.execute(f'clock = {1000 + plan.STREAM_STUCK - 5}; ready(server)')
    assert plan.update(g.pawn, True, False) == (False, 'loading')
    lua.execute(f'clock = {1000 + 3 * plan.STREAM_STUCK}; ready(plan)')
    assert plan.update(g.pawn, True, False) == (True, 'loaded_visible')
    assert plan.stuck_retries is None and len(tags(g)) == 4


def test_a_borrowed_stream_is_never_unloaded_as_stuck():
    lua, plan = fixture()
    g = lua.globals()
    lua.execute("""clock = 1000; os.time = function() return clock end
        navserver.exists = true; navserver.loaded = true""")  # loaded by the game, not yet visible
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    lua.execute(f'clock = {1000 + 5 * plan.STREAM_STUCK}')
    assert plan.update(g.pawn, True, False) == (False, 'loading_navigation_serverbuild')
    assert g.navserver.loaded is True and plan.stuck_retries is None and len(tags(g)) == 0


def test_the_stuck_clock_restarts_when_returning_to_the_foyer():
    lua, plan, g = stuck_fixture()
    lua.execute(f'clock = {1000 + plan.STREAM_STUCK - 1}')
    plan.update(g.pawn, True, False)
    plan.update(g.pawn, False, False)            # left before it was stuck
    lua.execute('server.SetShouldBeVisible = function() end')  # comes back slowly
    lua.execute(f'clock = {1000 + plan.STREAM_STUCK + 5}')
    assert plan.update(g.pawn, True, False) == (False, 'loading_serverbuild')
    assert plan.stuck_retries is None


def test_a_stream_switched_back_on_after_leaving_is_not_treated_as_stuck():
    """Only a new request is watched: asking again for a package that had loaded
    (and may still be unloading) would be refused."""
    lua, plan = fixture()
    g = lua.globals()
    lua.execute('clock = 1000; os.time = function() return clock end; for _,s in ipairs(all) do ready(s) end')
    for _ in range(4):
        plan.update(g.pawn, True, False)
    assert plan.update(g.pawn, True, False) == (True, 'loaded_visible')
    plan.update(g.pawn, False, False)
    lua.execute('server.SetShouldBeVisible = function() end')  # comes back slowly
    assert plan.update(g.pawn, True, False) == (False, 'loading_serverbuild')
    lua.execute(f'clock = {1000 + 5 * plan.STREAM_STUCK}')
    assert plan.update(g.pawn, True, False) == (False, 'loading_serverbuild')
    assert plan.stuck_retries is None and len(tags(g)) == 4


def loaded(lua, plan):
    g = lua.globals()
    lua.execute('for _,s in ipairs(all) do ready(s) end')
    for _ in range(4):
        plan.update(g.pawn, True, False)
    assert plan.update(g.pawn, True, False) == (True, 'loaded_visible')
    return g


def test_between_rounds_present_levels_are_left_alone():
    lua, plan = fixture()
    g = loaded(lua, plan)
    lua.execute('changes=0')
    assert plan.course_check() == ''
    assert g.changes == 0


def test_between_rounds_an_unloaded_level_of_ours_is_switched_back_on():
    """Live 2026-11-11: a course stalled before round 7 with no round territory armed."""
    lua, plan = fixture()
    g = loaded(lua, plan)
    lua.execute('server.loaded=false;server.visible=false;changes=0')
    assert plan.course_check() == '1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild=unloaded_switched_on'
    assert g.server.loaded is True and g.server.visible is True and g.changes == 2
    assert plan.course_check() == ''


def test_between_rounds_a_level_still_loading_is_only_reported():
    lua, plan = fixture()
    g = loaded(lua, plan)
    lua.execute('plan.loaded=false;plan.IsStreamingStatePending=function() return true end;changes=0')
    assert plan.course_check() == '1300-JUNOA_BattlePlan_ModJunonColosseum=loading'
    assert g.changes == 0


def test_between_rounds_a_deleted_level_is_requested_again_without_a_pawn():
    lua, plan = fixture()
    g = loaded(lua, plan)
    asked = len(tags(g))
    lua.execute('for _,s in ipairs(all) do s.IsValid=function() return false end end')
    assert 'deleted' in plan.course_check()
    assert plan.update(None, True, False)[0] is False and len(tags(g)) == asked  # no world: nothing asked
    plan.update(None, True, False, g.world)                                       # the game's world
    assert len(tags(g)) == asked + 1
    assert plan.update(None, True, True, g.world)[0] is False                      # never in battle
