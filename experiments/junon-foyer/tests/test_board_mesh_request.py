"""foyer.lua asks the native helper for the board mesh once, only when streaming
has not loaded it (a save made inside the foyer), and keeps waiting otherwise."""
import json
import math
from pathlib import Path
from lua_stubs import PATHS_STUB

import pytest

lupa = pytest.importorskip('lupa')

SCRIPTS = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts'

HARNESS = r'''
local helper_loads, mesh_streamed, bounds = ...
mesh_loaded = mesh_streamed
markers, spawned_points, receipt, point_t = 0, 0, nil, nil
local function valid() return true end
local function named(n)
    local o = {IsValid=valid, name=n}
    o.GetFName = function(self) return {ToString=function() return self.name end} end
    o.GetFullName = function(self) return self.name end
    o.SetActorHiddenInGame = function() end
    o.SetActorEnableCollision = function() end
    o.K2_DestroyActor = function() end
    return o
end
local mesh_object = named('StaticMesh Quest_Board_04A')
mesh_object.HasAnyFlags = function() return false end
local world = {IsValid=valid}
world.SpawnActor = function(self, class, pos, rot)
    local actor = named('StaticMeshActor_' .. markers)
    actor.StaticMeshComponent = {SetMobility=function() end, SetSimulatePhysics=function() end,
        SetCollisionEnabled=function() end, SetStaticMesh=function(_, m) return m == mesh_object end}
    actor.GetActorBounds = function(self, colliding, origin, extent)
        assert(colliding == false, 'the display has no collision')
        if not bounds then error('no bounds') end
        origin.X, origin.Y, origin.Z = bounds[1], bounds[2], bounds[3]
        extent.X, extent.Y, extent.Z = 60, 110, 130
    end
    actor.SetActorTickEnabled = function(self)
        if self.Tags and self.Tags[1] == 'ModJunonColosseum_LoadBoardMesh' then
            markers = markers + 1
            assert(pos.Z > 6000 and pos.Z < 6500, 'marker outside the native foyer box')
            if queue_mode then
                -- off the game thread: queued, answered by serve_mesh() later
                queued_marker = self
                self.original = self.name
                self.name = 'ModJunonQueued_' .. self.name
                self.K2_DestroyActor = function(m) m.destroyed = true end
            elseif helper_loads then
                mesh_loaded = true
                self.name = 'ModJunonBoardMeshLoaded_' .. self.name
            end
        end
    end
    return actor
end
local pawn = {IsValid=valid, GetWorld=function() return world end,
    K2_GetActorLocation=function() return {X=-122480, Y=32400, Z=6260} end}
local gameplay = {IsValid=valid}
gameplay.BeginDeferredActorSpawnFromClass = function(self, w, class, transform)
    spawned_points = spawned_points + 1
    point_t = transform.Translation
    local point = named('EndBulletinBoardPoint_0')
    point.SetActorTickEnabled = function(self) self.name = 'oblMod_JunonColosseum_Noticeboard' end
    return point
end
gameplay.FinishSpawningActor = function() end
EObjectFlags = {RF_NeedLoad=1, RF_NeedPostLoad=2, RF_NeedPostLoadSubobjects=4, RF_Transient=8}
EInternalObjectFlags = {RootSet=1}
FName = function(s) return s end
FindAllOf = function() return {} end
StaticConstructObject = function() return {IsValid=valid} end
StaticFindObject = function(path)
    if path:find('Quest_Board_04A', 1, true) then
        if mesh_loaded then return mesh_object end
        return {IsValid=function() return false end}
    end
    if path:find('Quest_Board_', 1, true) then return {IsValid=function() return false end} end
    if path == '/Script/Engine.Default__GameplayStatics' then return gameplay end
    if path == '/Script/EndGame.Default__EndFieldAPI' then
        return {IsValid=valid, IsDuringBattle=function() return false end}
    end
    return {IsValid=valid}
end
io.open = function() return {write=function(_, s) receipt = s end, close=function() end} end
os.remove = function() end
os.rename = function() end
package.preload.battle_plan = function() return {
    update=function() return true, 'loaded_visible' end,
    error=function() return '' end, package=function() return 'plan' end} end
foyer = foyer_chunk()
db = {GetItemNumBP=function() return 1 end}
function run_tick() foyer.tick(db, pawn, {board_enabled=true}) end
'''


def run(helper_loads, mesh_streamed, ticks=3, bounds=None):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PATHS_STUB)
    lua.globals().foyer_chunk = lua.eval('load')((SCRIPTS / 'foyer.lua').read_text())
    lua.execute(HARNESS, helper_loads, mesh_streamed, lua.table(*bounds) if bounds else None)
    for _ in range(ticks):
        lua.globals().run_tick()
    g = lua.globals()
    t = g.point_t
    return json.loads(g.receipt), g.markers, g.spawned_points, (t.X, t.Y, t.Z) if t else None


def test_foyer_save_loads_the_board_mesh_through_the_helper_once():
    receipt, markers, points, _ = run(helper_loads=True, mesh_streamed=False)
    assert markers == 1
    assert receipt['mesh_request'] == 'loaded'
    assert receipt['mesh_cached'] is True
    assert receipt['state'] == 'native_identity_registered_smoke_test'
    assert points == 1


def test_a_queued_mesh_load_is_collected_on_a_later_tick():
    """Off the game thread the helper queues the load; foyer.lua keeps the marker
    and picks up the helper's answer without asking again."""
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PATHS_STUB)
    lua.globals().foyer_chunk = lua.eval('load')((SCRIPTS / 'foyer.lua').read_text())
    lua.execute('queue_mode = true')
    lua.execute(HARNESS, True, False, None)
    g = lua.globals()
    g.run_tick()
    g.run_tick()
    assert g.markers == 1 and json.loads(g.receipt)['mesh_request'] == 'queued'
    assert g.queued_marker.destroyed is None
    lua.execute("mesh_loaded = true; queued_marker.name = 'ModJunonBoardMeshLoaded_' .. queued_marker.original")
    g.run_tick()
    g.run_tick()  # the first spawn also writes a one-off field capture
    receipt = json.loads(g.receipt)
    assert g.markers == 1 and g.queued_marker.destroyed is True
    assert receipt['mesh_request'] == 'loaded' and receipt['state'] == 'native_identity_registered_smoke_test'


def test_a_queued_mesh_load_that_times_out_is_asked_again():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PATHS_STUB)
    lua.globals().foyer_chunk = lua.eval('load')((SCRIPTS / 'foyer.lua').read_text())
    lua.execute('queue_mode = true; clock = 1000; os.time = function() return clock end')
    lua.execute(HARNESS, True, False, None)
    g = lua.globals()
    g.run_tick()
    first = g.queued_marker
    lua.execute('clock = 1010')
    g.run_tick()
    assert first.destroyed is True and len(first.Tags) == 0  # untagged before destroying
    assert g.markers == 2 and json.loads(g.receipt)['mesh_request'] == 'queued'


def test_older_helper_is_asked_once_and_the_board_keeps_waiting():
    receipt, markers, points, _ = run(helper_loads=False, mesh_streamed=False)
    assert markers == 1
    assert receipt['mesh_request'] == 'refused'
    assert receipt['state'] == 'waiting_for_native_quest_board_mesh'
    assert points == 0


def test_streamed_mesh_needs_no_request():
    receipt, markers, points, _ = run(helper_loads=True, mesh_streamed=True)
    assert markers == 0
    assert receipt['mesh_request'] == 'not_requested'
    assert receipt['state'] == 'native_identity_registered_smoke_test'


def test_check_point_sits_at_the_board_centre():
    centre = (-122430.0, 32200.0, 6300.0)
    receipt, _, points, at = run(helper_loads=True, mesh_streamed=True, bounds=centre)
    assert points == 1 and receipt['point_source'] == 'board_bounds_centre'
    yaw = math.radians(60)
    assert at == pytest.approx((centre[0] + 20 * math.cos(yaw), centre[1] + 20 * math.sin(yaw), 6300.0))
    assert receipt['point_x'] == pytest.approx(at[0])


def test_unreadable_bounds_fall_back_to_the_fixed_offset():
    receipt, _, points, at = run(helper_loads=True, mesh_streamed=True)
    assert points == 1 and receipt['point_source'] == 'fixed_offset'
    assert at == pytest.approx((-122459.3125, 32287.3273, 6290.0))


def test_implausible_bounds_are_ignored():
    receipt, _, _, at = run(helper_loads=True, mesh_streamed=True, bounds=(-121000.0, 32274.0, 6300.0))
    assert receipt['point_source'] == 'fixed_offset'


def test_a_queued_mesh_load_the_helper_deferred_is_asked_again():
    """The helper answers ModJunonDeferred_ when no safe point came within 3 s."""
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PATHS_STUB)
    lua.globals().foyer_chunk = lua.eval('load')((SCRIPTS / 'foyer.lua').read_text())
    lua.execute('queue_mode = true; clock = 1000; os.time = function() return clock end')
    lua.execute(HARNESS, True, False, None)
    g = lua.globals()
    g.run_tick()
    first = g.queued_marker
    lua.execute("queued_marker.name = 'ModJunonDeferred_' .. queued_marker.original")
    g.run_tick()
    assert first.destroyed is True
    assert g.markers == 2 and json.loads(g.receipt)['mesh_request'] == 'queued'
