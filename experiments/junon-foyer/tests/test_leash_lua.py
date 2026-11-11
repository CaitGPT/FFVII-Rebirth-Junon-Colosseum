import math
from pathlib import Path

from lupa import LuaRuntime

SCRIPTS = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts'

CX, CY = -123780, 28675

FAKE = r'''
now, lines, moves = 1000, {}, {}
-- A fake enemy actor whose position the leash can read and set.
function actor(name, x, y, z)
    local a = {name=name, x=x, y=y, z=z or 0, valid=true}
    a.IsValid = function() return a.valid end
    a.GetFullName = function() return 'Character /Game/'..name end
    a.GetFName = function() return {ToString=function() return name end} end
    a.K2_GetActorLocation = function() return {X=a.x, Y=a.y, Z=a.z} end
    a.K2_SetActorLocation = function(self, v, sweep, hit, teleport)
        assert(sweep == false and teleport == true and type(hit) == 'table')
        a.x, a.y, a.z = v.X, v.Y, v.Z
        moves[#moves+1] = name
    end
    return a
end
CX, CY = -123780, 28675
-- Place an actor at an offset from the arena centre.
function at(a, dx, dy, z) a.x, a.y = CX+dx, CY+dy; if z then a.z = z end end
leash = require('leash')
leash.set_log(function(line) lines[#lines+1] = line end)
function tick(foes, leader, seconds)
    for _ = 1, seconds or 1 do now = now + 1; leash.tick({}, foes, leader, now) end
end
'''


def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().package.path = str(SCRIPTS / '?.lua').replace('\\', '/') + ';' + lua.globals().package.path
    lua.execute(FAKE)
    return lua


def dist(lua, name):
    a = lua.globals()[name]
    return math.hypot(a.x - CX, a.y - CY)


def test_an_enemy_inside_never_moves():
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX+2200, CY, 50)
        tick({e}, nil, 20)
    ''')
    assert len(lua.globals().moves) == 0
    assert len(lua.globals().lines) == 0


def test_out_for_one_or_two_ticks_does_not_move():
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX, CY, 0)
        tick({e})
        at(e, 2400, 0); tick({e}, nil, 2)   -- out for two ticks
        at(e, 2000, 0); tick({e})           -- back in: the count restarts
        at(e, 2400, 0); tick({e}, nil, 2)
    ''')
    assert len(lua.globals().moves) == 0


def test_out_for_three_ticks_is_put_back_along_its_bearing_at_its_last_inside_height():
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX+1000, CY+1000, 321)
        tick({e})                           -- seen inside at Z 321
        at(e, 3000, 4000, 900)              -- teleported out and up: bearing (0.6, 0.8)
        tick({e}, nil, 3)
    ''')
    g = lua.globals()
    assert len(g.moves) == 1
    e = g.e
    assert abs(e.x - (CX + 720)) < 1e-6 and abs(e.y - (CY + 960)) < 1e-6
    assert e.z == 321
    assert abs(dist(lua, 'e') - 1200) < 1e-6
    assert g.lines[1] == f'leash\tEN1\t5000\t{CX + 720}\t{CY + 960}\t321\t1'


def test_an_enemy_straight_out_along_plus_x_lands_on_the_plus_x_axis():
    # (The no-bearing case at the exact centre cannot occur for an enemy out
    # of the ring, so it is not reachable from tick.)
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX+5000, CY, 0)
        tick({e}, nil, 3)
    ''')
    e = lua.globals().e
    assert (e.x, e.y) == (CX + 1200, CY)


def test_cooldown_after_a_move():
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX, CY, 10)
        tick({e})
        at(e, 5000, 0); tick({e}, nil, 3)   -- moved at the third tick
        assert(#moves == 1)
        at(e, 5000, 0); tick({e}, nil, 4)   -- out again, but within 5 s of the move
        assert(#moves == 1)
        tick({e}, nil, 3)                   -- cooldown over at +5; three ticks out
        assert(#moves == 2)
    ''')
    assert lua.globals().lines[2].endswith('\t2')


def test_ten_moves_per_enemy_per_round_then_it_stops():
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX, CY, 10)
        tick({e})
        for _ = 1, 30 do at(e, 5000, 0); tick({e}, nil, 8) end
    ''')
    g = lua.globals()
    assert len(g.moves) == 10
    assert g.lines[10].endswith('\t10')
    assert g.lines[11] == 'leash\tEN1\t5000\tcap\t10'
    assert len(g.lines) == 11                # the cap is logged once
    lua.execute('leash.reset(); at(e, 5000, 0); tick({e}, nil, 3)')
    assert len(g.moves) == 11                # a new round starts the count again


def test_enemies_are_tracked_separately():
    lua = runtime()
    lua.execute('''
        a = actor('EN1', CX, CY, 10); b = actor('EN2', CX, CY, 20)
        tick({a, b})
        at(a, 5000, 0); tick({a, b}, nil, 3)
        assert(#moves == 1 and moves[1] == 'EN1' and a.z == 10)
        at(b, 0, -5000); tick({a, b}, nil, 3)
        assert(#moves == 2 and moves[2] == 'EN2' and b.z == 20 and b.y == CY-1200)
    ''')


def test_invalid_actors_are_skipped():
    lua = runtime()
    lua.execute('''
        dead = actor('EN1', CX+5000, CY, 0); dead.valid = false
        dead.K2_GetActorLocation = function() error('touched an invalid actor') end
        e = actor('EN2', CX+5000, CY, 0)
        tick({dead, e}, nil, 3)
        tick(nil, nil, 3)                   -- no list at all
    ''')
    g = lua.globals()
    assert len(g.moves) == 1 and g.moves[1] == 'EN2'


def test_never_seen_inside_uses_the_leader_height_else_its_own():
    lua = runtime()
    lua.execute('''
        leader = actor('PC0000_Cloud', CX, CY, 500)
        e = actor('EN1', CX+5000, CY, 2000)
        tick({e}, leader, 3)
        assert(e.z == 600)
        gone = actor('PC0000_Cloud', CX, CY, 500); gone.valid = false
        f = actor('EN2', CX+5000, CY, 2000)
        tick({f}, gone, 3)
        assert(f.z == 2000)
        g = actor('EN3', CX+5000, CY, 2000)
        tick({g}, nil, 3)
        assert(g.z == 2000)
    ''')


def test_a_failed_move_still_counts_and_is_logged():
    lua = runtime()
    lua.execute('''
        e = actor('EN1', CX+5000, CY, 0)
        e.K2_SetActorLocation = function() error('no') end
        tick({e}, nil, 3)
    ''')
    assert lua.globals().lines[1] == 'leash\tEN1\t5000\tfailed\t1'
